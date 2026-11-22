# Thời điểm bắt đầu, kết thúc và ranh giới của một giao dịch trong Oracle

Trong Oracle Database, một câu lệnh DML có thể thay đổi nhiều hàng, nhưng các thay đổi đó không trở thành dữ liệu đã xác nhận ngay sau mỗi câu lệnh. Chúng thuộc về một **giao dịch** (*transaction*): một đơn vị công việc có thể được xác nhận cùng nhau bằng `COMMIT` hoặc hủy bằng `ROLLBACK`. Hiểu chính xác giao dịch bắt đầu lúc nào, kết thúc ở đâu và thao tác nào tự tạo ranh giới giao dịch là điều thiết yếu để tránh mất dữ liệu, commit nhầm và giữ khóa quá lâu.

Ví dụ, khi chuyển tiền giữa hai tài khoản, hệ thống cần trừ tiền ở tài khoản gửi và cộng tiền ở tài khoản nhận như một đơn vị. Nếu chỉ trừ tiền rồi ứng dụng gặp lỗi trước khi cộng tiền, giao dịch phải được rollback để dữ liệu không ở trạng thái dở dang. Nếu cả hai thao tác thành công, ứng dụng commit để xác nhận toàn bộ thay đổi.

Bài học thuộc chủ đề **Giao dịch** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Transaction bắt đầu ngầm định trong session và vai trò của `SET TRANSACTION`.
- Ranh giới kết thúc qua `COMMIT`, `ROLLBACK` và savepoint.
- Các lệnh DDL gây implicit commit.
- Phạm vi giao dịch trong session, PL/SQL và connection pool.
- Khả năng nhìn thấy dữ liệu, row lock và read consistency.
- Khác biệt giữa `READ COMMITTED`, `SERIALIZABLE` và `READ ONLY`.
- Các tình huống thực hành và lỗi thường gặp khi quản lý transaction.

## 1. Giao dịch là gì?

Giao dịch là một chuỗi thao tác cơ sở dữ liệu được xem như một đơn vị công việc. Oracle dùng transaction để bảo đảm những thay đổi của đơn vị đó được xác nhận hoặc hủy theo quy tắc nhất quán.

Bốn thuộc tính thường được mô tả bằng ACID:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Atomicity** | Các thay đổi của transaction được xác nhận cùng nhau; nếu rollback thì các thay đổi chưa commit bị hủy. |
| **Consistency** | Transaction phải đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác theo constraint và quy tắc nghiệp vụ. |
| **Isolation** | Các transaction đồng thời được điều phối để không đọc dữ liệu chưa commit của nhau và tuân theo mức cô lập được chọn. |
| **Durability** | Sau khi COMMIT thành công, Oracle bảo đảm thay đổi đã commit có thể được khôi phục sau sự cố theo cơ chế redo/recovery. |

ACID không có nghĩa mọi lỗi nghiệp vụ đều tự được phát hiện. Ứng dụng vẫn phải kiểm tra số dư, quyền, trạng thái và điều kiện nghiệp vụ trước khi commit.

### Ví dụ: chuyển tiền

Giả sử chuyển 100 từ tài khoản A sang tài khoản B:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
~~~

Hai UPDATE thuộc cùng transaction nếu không có ranh giới commit/rollback ở giữa. Nếu câu UPDATE thứ hai lỗi và ứng dụng quyết định hủy giao dịch:

~~~sql
ROLLBACK;
~~~

Oracle hủy cả thay đổi trừ tiền chưa commit ở câu UPDATE thứ nhất. Trong ứng dụng thật, cần kiểm tra đủ điều kiện (tài khoản tồn tại, số dư đủ, đúng một hàng được cập nhật, tài khoản đích hợp lệ) trước khi commit. Đoạn SQL trên chỉ minh họa ranh giới transaction, chưa phải một quy trình chuyển tiền hoàn chỉnh.

## 2. Khi nào một transaction bắt đầu?

Oracle quản lý transaction theo session. Sau khi transaction trước kết thúc, thao tác thay đổi dữ liệu đầu tiên thường mở một transaction mới. Các thao tác DML như `INSERT`, `UPDATE`, `DELETE` và `MERGE` tham gia transaction hiện tại; chúng không tự commit chỉ vì câu lệnh chạy thành công.

Ví dụ:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES (90, 'Research');

UPDATE departments
SET department_name = 'Research and Development'
WHERE department_id = 90;

-- Chưa commit: cả hai thay đổi vẫn thuộc transaction hiện tại.
COMMIT;
~~~

Transaction chứa cả INSERT và UPDATE. Khi COMMIT, cả hai thay đổi được xác nhận.

### Không cần viết BEGIN TRANSACTION như một số hệ quản trị khác

Trong Oracle SQL thông thường, không mở transaction bằng cú pháp `BEGIN TRANSACTION` như một số hệ quản trị. Transaction DML được quản lý ngầm định theo session; câu DML đầu tiên sau ranh giới trước đó bắt đầu đơn vị thay đổi mới.

Ví dụ:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;

-- Transaction đã có thay đổi chưa commit.
COMMIT;
~~~

### SELECT thông thường và transaction

Một SELECT thông thường không tạo thay đổi DML chưa commit và không giữ row lock chỉ vì đọc bảng. Oracle cung cấp read consistency cho câu SELECT, nghĩa là truy vấn đọc một ảnh dữ liệu nhất quán tại thời điểm thích hợp, không nhìn thấy thay đổi chưa commit của session khác.

Tuy vậy, không nên hiểu rằng SELECT và transaction hoàn toàn không liên quan. `SET TRANSACTION READ ONLY`/`SERIALIZABLE` thiết lập chế độ transaction và phải được thực hiện trước statement khác trong transaction. `SELECT ... FOR UPDATE` khóa các hàng được chọn để chuẩn bị cập nhật và các khóa đó được giữ đến khi transaction kết thúc.

### SET TRANSACTION: cấu hình transaction ngay từ đầu

Oracle cho phép đặt chế độ transaction bằng `SET TRANSACTION`. Lệnh này phải là statement đầu tiên của transaction:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT department_id, COUNT(*)
FROM employees
GROUP BY department_id;

COMMIT;
~~~

Ví dụ khác:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT ...
FROM ...

UPDATE ...
SET ...
WHERE ...;

COMMIT;
~~~

Các lựa chọn quan trọng gồm `READ WRITE` (mặc định), `READ ONLY` và `ISOLATION LEVEL SERIALIZABLE`. Không đặt `SET TRANSACTION` sau khi đã chạy DML hoặc một statement khác trong transaction; Oracle sẽ báo lỗi vì transaction đã bắt đầu.

### BEGIN và END trong PL/SQL không phải ranh giới transaction

Một khối PL/SQL:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 'A';

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 'B';
END;
/
~~~

`BEGIN`/`END` chỉ đánh dấu phạm vi khối PL/SQL. Chúng không tự commit ở cuối block. Nếu block chạy thành công mà không có COMMIT/ROLLBACK hoặc DDL gây implicit commit, các thay đổi vẫn thuộc transaction của session và caller có thể commit hoặc rollback sau đó.

Đây là điểm quan trọng khi gọi stored procedure: một procedure không nên tự commit tùy tiện nếu caller cần kết hợp nhiều procedure thành một transaction nghiệp vụ.

## 3. COMMIT: kết thúc và xác nhận transaction

`COMMIT` kết thúc transaction hiện tại và xác nhận mọi thay đổi chưa commit của session:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100;

COMMIT;
~~~

Sau COMMIT thành công:

- Các thay đổi của transaction trở thành thay đổi đã xác nhận.
- Session khác có thể nhìn thấy dữ liệu mới theo read consistency của chúng.
- Các row lock do transaction giữ được giải phóng.
- Savepoint của transaction bị xóa.
- Transaction hiện tại kết thúc; DML tiếp theo sẽ thuộc transaction mới.

Oracle tạo commit record và SCN tương ứng. Cơ chế redo bảo đảm tính bền vững của commit; không cần hiểu rằng mọi data block đã được DBWR ghi ngay xuống datafile trước khi COMMIT trả về. Redo/log recovery bảo vệ các thay đổi đã commit, còn việc ghi data block có thể diễn ra sau.

### COMMIT không phải chỉ xác nhận câu lệnh cuối

~~~sql
INSERT INTO audit_events(event_id, event_type)
VALUES (1001, 'STARTED');

UPDATE jobs
SET status = 'DONE'
WHERE job_id = 55;

COMMIT;
~~~

COMMIT xác nhận **tất cả thay đổi chưa commit trong transaction hiện tại**, bao gồm INSERT và UPDATE. Nó không giới hạn ở câu lệnh ngay trước đó.

### COMMIT WORK

~~~sql
COMMIT WORK;
~~~

Đây là cách viết đầy đủ hợp lệ. Trong sử dụng thông thường, `COMMIT` và `COMMIT WORK` có cùng mục tiêu kết thúc transaction hiện tại. Các tùy chọn nâng cao như `WRITE WAIT/NOWAIT` hoặc `IMMEDIATE/BATCH` ảnh hưởng chính sách ghi redo và cần được dùng theo yêu cầu độ bền vững; không thay đổi chúng chỉ để thử tăng tốc nếu chưa hiểu rủi ro.

## 4. ROLLBACK: hủy thay đổi chưa commit

`ROLLBACK` không có savepoint hủy toàn bộ thay đổi chưa commit trong transaction hiện tại:

~~~sql
UPDATE products
SET unit_price = unit_price * 1.10
WHERE category_id = 7;

-- Phát hiện cập nhật nhầm phạm vi.
ROLLBACK;
~~~

Sau ROLLBACK:

- Các thay đổi DML chưa commit trong transaction bị hoàn tác.
- Các row lock do transaction giữ được giải phóng.
- Savepoint của transaction bị xóa.
- Transaction hiện tại kết thúc.
- Các thay đổi đã commit trước đó không bị ảnh hưởng.

ROLLBACK không thể đảo ngược transaction đã COMMIT. Nếu đã commit nhầm, cần một giao dịch bù (compensating transaction), khôi phục từ backup/flashback phù hợp hoặc quy trình sửa dữ liệu được kiểm soát.

### ROLLBACK WORK

~~~sql
ROLLBACK WORK;
~~~

Đây là dạng viết đầy đủ tương ứng với ROLLBACK thông thường.

### DML lỗi không có nghĩa toàn transaction tự rollback

Nếu một câu DML lỗi, Oracle thường rollback statement bị lỗi về trạng thái trước khi statement đó bắt đầu; các statement trước đó trong cùng transaction vẫn còn hiệu lực chưa commit. Ứng dụng cần quyết định tiếp tục sửa và commit hay rollback toàn transaction.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

-- Câu lệnh sau có thể lỗi do vi phạm constraint.
INSERT INTO departments (department_id, department_name)
VALUES (10, 'Duplicate department');

-- UPDATE đầu tiên vẫn còn trong transaction nếu chưa rollback.
ROLLBACK;
~~~

Đừng giả định một lỗi SQL bất kỳ tự hủy mọi thay đổi trước đó. Hãy xử lý exception và ranh giới transaction một cách rõ ràng.

## 5. SAVEPOINT và ROLLBACK TO SAVEPOINT

`SAVEPOINT` đặt một mốc bên trong transaction để có thể quay lui một phần công việc mà không hủy toàn bộ transaction.

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 500;

SAVEPOINT after_order_status;

INSERT INTO order_audit(order_id, action_name)
VALUES (500, 'PROCESSING');

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE product_id = 900;

-- Nếu bước xử lý inventory không đúng, quay về savepoint.
ROLLBACK TO SAVEPOINT after_order_status;

-- Transaction vẫn còn hoạt động; có thể thực hiện bước khác.
INSERT INTO order_audit(order_id, action_name)
VALUES (500, 'PROCESSING_RETRY');

COMMIT;
~~~

Sau `ROLLBACK TO SAVEPOINT after_order_status`, các thay đổi sau savepoint bị hủy, còn thay đổi trạng thái đơn hàng trước savepoint vẫn nằm trong transaction và sẽ được COMMIT cuối cùng. Lệnh này **không kết thúc transaction**.

### Tạo và sử dụng nhiều savepoint

~~~sql
SAVEPOINT step_a;
UPDATE accounts SET status = 'REVIEW' WHERE account_id = 'A';

SAVEPOINT step_b;
UPDATE accounts SET status = 'HOLD' WHERE account_id = 'B';

ROLLBACK TO SAVEPOINT step_a;
~~~

Quay về `step_a` sẽ hủy các thay đổi sau mốc đó, bao gồm thay đổi tại step_b. Các savepoint được tạo sau mốc quay lui bị xóa; savepoint đích vẫn có thể được sử dụng lại trong transaction. Tên savepoint có phạm vi trong transaction hiện tại; đặt lại cùng tên sẽ thay mốc trước đó.

### Savepoint không phải transaction lồng nhau

Oracle không cung cấp nested transaction thông thường theo kiểu một transaction con có thể commit độc lập bên trong transaction cha. Savepoint chỉ tạo mốc rollback trong cùng transaction. Khi COMMIT, mọi thay đổi còn lại trong transaction được xác nhận; khi ROLLBACK toàn bộ, mọi thay đổi chưa commit bị hủy.

## 6. DDL và implicit commit: ranh giới dễ gây mất thay đổi

Một trong những quy tắc quan trọng nhất của Oracle là **DDL gây implicit commit**. Với DDL hợp lệ về cú pháp, Oracle thực hiện commit ngầm trước khi chạy DDL; nếu DDL thành công, Oracle commit ngầm sau khi hoàn thành DDL.

Các lệnh thường gặp:

- `CREATE TABLE`, `CREATE INDEX`, `CREATE VIEW`.
- `ALTER TABLE`, `ALTER INDEX`.
- `DROP TABLE`, `DROP INDEX`.
- `TRUNCATE TABLE`.
- `GRANT`, `REVOKE` và các thao tác DDL khác.

Điều này có nghĩa DDL có thể kết thúc transaction DML đang mở của session. Ví dụ:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 100;

CREATE TABLE lab_notes (
    note_id NUMBER PRIMARY KEY,
    note_text VARCHAR2(100)
);

ROLLBACK;
~~~

UPDATE trước CREATE TABLE đã được commit ngầm trước khi DDL chạy. Vì vậy ROLLBACK cuối cùng **không thể hoàn tác** thay đổi salary đó. Nếu CREATE TABLE thành công, DDL cũng được commit sau khi hoàn tất.

### DDL thất bại vẫn có thể đã commit DML trước đó

Quy tắc commit trước DDL là điều cần nhớ ngay cả khi DDL không hoàn tất. Nếu câu DDL hợp lệ về cú pháp nhưng thất bại trong lúc thực thi, transaction trước đó vẫn có thể đã được commit ở bước trước DDL. Không dùng ROLLBACK sau lỗi DDL với kỳ vọng lấy lại những DML đã bị implicit commit.

### DELETE khác TRUNCATE

~~~sql
DELETE FROM staging_orders
WHERE load_date < DATE '2025-01-01';

ROLLBACK;
~~~

DELETE là DML; nếu chưa commit thì có thể rollback.

~~~sql
TRUNCATE TABLE staging_orders;
~~~

TRUNCATE là DDL; nó gây implicit commit và không thể rollback như DELETE. Hãy phân biệt rõ trước khi chạy thao tác dọn bảng.

| Thao tác | Phân loại | Có thể ROLLBACK trước COMMIT? |
| --- | --- | --- |
| `INSERT` | DML | Có |
| `UPDATE` | DML | Có |
| `DELETE` | DML | Có |
| `MERGE` | DML | Có |
| `CREATE TABLE` | DDL | Không theo cơ chế transaction DML thông thường |
| `ALTER TABLE` | DDL | Không theo cơ chế transaction DML thông thường |
| `DROP TABLE` | DDL | Không theo cơ chế transaction DML thông thường |
| `TRUNCATE TABLE` | DDL | Không theo cơ chế transaction DML thông thường |
| `GRANT` / `REVOKE` | DDL trong Oracle | Không theo cơ chế transaction DML thông thường |

Một số thao tác quản trị có cơ chế riêng, nhưng không nên suy ra rằng có thể gom DDL thông thường vào transaction DML rồi rollback toàn bộ. Hãy hoàn tất hoặc hủy DML trước khi chạy DDL.

### DDL trong script triển khai

~~~sql
UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'mode';

ALTER TABLE orders ADD source_code VARCHAR2(20);

UPDATE orders
SET source_code = 'LEGACY'
WHERE source_code IS NULL;

COMMIT;
~~~

UPDATE cấu hình có thể đã được commit ngầm trước ALTER TABLE. Nếu UPDATE thứ hai lỗi, ROLLBACK cuối không thể đưa cấu hình về giá trị cũ. Hãy chia migration thành các bước có ranh giới rõ ràng, có kế hoạch phục hồi và kiểm tra sau mỗi DDL.

## 7. Ranh giới transaction và session

Transaction thuộc về **database session**, không thuộc riêng một câu SQL hay một biến trong ứng dụng. Mỗi session có transaction hiện tại, các thay đổi chưa commit và các khóa do transaction giữ.

### Hai session nhìn thấy dữ liệu khác nhau

Giả sử Session A chạy:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 'A';
~~~

Session A thấy giá trị mới của chính mình trong session đó. Session B chạy SELECT thông thường trước khi A commit vẫn thấy phiên bản đã commit trước đó; B không đọc được giá trị 900 chưa commit của A.

Khi A chạy:

~~~sql
COMMIT;
~~~

Các truy vấn mới của B theo READ COMMITTED có thể nhìn thấy giá trị đã commit. Một truy vấn B đã bắt đầu trước commit của A vẫn tiếp tục đọc ảnh dữ liệu nhất quán tại thời điểm bắt đầu câu truy vấn đó.

### Row lock được giữ đến ranh giới transaction

Khi UPDATE một hàng, Oracle khóa hàng đó để ngăn session khác ghi đè xung đột. Khóa thường được giữ cho tới COMMIT hoặc ROLLBACK:

~~~sql
UPDATE accounts
SET balance = balance - 50
WHERE account_id = 'A';

-- Hàng A vẫn bị khóa trong transaction.
-- Chưa COMMIT hoặc ROLLBACK.
~~~

Session khác muốn UPDATE cùng hàng có thể phải chờ. Transaction mở quá lâu có thể làm tăng blocking, timeout và deadlock risk. Hãy giữ transaction ngắn, không chờ người dùng nhập liệu hoặc gọi dịch vụ mạng trong khi đang giữ khóa.

### SELECT FOR UPDATE

Nếu cần đọc một hàng rồi cập nhật nó mà không để session khác thay đổi trong khoảng giữa, có thể dùng `SELECT ... FOR UPDATE`:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 'A'
FOR UPDATE;
~~~

Oracle khóa các hàng được chọn. Khóa tiếp tục được giữ cho đến COMMIT/ROLLBACK. Các tùy chọn như `NOWAIT`, `WAIT n` hoặc `SKIP LOCKED` thay đổi cách xử lý khi hàng đang bị session khác khóa; chọn theo nghiệp vụ, không dùng SKIP LOCKED nếu việc bỏ qua hàng sẽ làm mất công việc cần xử lý.

### Session kết thúc và transaction chưa commit

Nếu session bị chấm dứt bất thường, Oracle rollback các thay đổi chưa commit của session đó trong quá trình cleanup/recovery. Tuy nhiên, hành vi khi client thoát bình thường có thể phụ thuộc client/driver: một số ứng dụng tự commit, một số rollback hoặc yêu cầu xử lý rõ. Không dựa vào việc đóng cửa sổ, đóng connection hay trả connection về pool để quyết định dữ liệu được commit.

Quy tắc an toàn: ứng dụng phải gọi COMMIT hoặc ROLLBACK rõ ràng trước khi trả connection về pool hoặc kết thúc đơn vị công việc. Connection pool thường tái sử dụng session; transaction chưa kết thúc có thể làm request sau kế thừa trạng thái và lock không mong muốn.

## 8. Autocommit là cấu hình của client

Oracle Database không có một quy tắc chung rằng mọi câu DML tự commit ngay sau khi chạy. Việc tự commit sau mỗi statement có thể do client hoặc driver bật **autocommit**.

Ví dụ trong JDBC, thuộc tính auto-commit thường mặc định là true theo JDBC API; ứng dụng có thể tắt để gom nhiều câu lệnh thành một transaction:

~~~java
connection.setAutoCommit(false);

try {
    updateDebit(connection);
    updateCredit(connection);
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

Nếu autocommit bật, mỗi statement thành công có thể được commit riêng theo cơ chế driver. Khi đó hai UPDATE chuyển tiền có thể không còn thuộc một transaction chung. Hãy kiểm tra cấu hình thực tế của JDBC pool, ORM hoặc công cụ SQL đang dùng.

Trong SQL Developer, SQL*Plus, ứng dụng Java và công cụ ETL, trạng thái autocommit và cách đóng session có thể khác nhau. Đừng suy ra hành vi client chỉ từ cú pháp Oracle SQL.

## 9. Stored procedure và transaction của caller

Stored procedure chạy trong session của caller. Nếu procedure không tự COMMIT/ROLLBACK, các DML trong procedure tham gia transaction hiện tại của session:

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_name (
    p_employee_id IN NUMBER,
    p_new_name    IN VARCHAR2
) AS
BEGIN
    UPDATE employees
    SET employee_name = p_new_name
    WHERE employee_id = p_employee_id;
END;
/
~~~

Caller có thể điều phối nhiều bước:

~~~sql
BEGIN
    update_employee_name(100, 'New Name');
    update_employee_department(100, 20);
END;
/

-- Caller quyết định transaction boundary.
COMMIT;
~~~

Nếu một procedure tự COMMIT, nó kết thúc transaction hiện tại của session, bao gồm cả các thay đổi trước đó do caller thực hiện trong cùng transaction. Đây là lý do nhiều API nghiệp vụ để transaction boundary ở tầng gọi cao nhất.

### Exception không tự động thay thế ROLLBACK

Khi exception thoát khỏi PL/SQL block, Oracle không mặc định rollback toàn bộ transaction của session. Statement lỗi được xử lý theo cơ chế statement-level rollback; các thay đổi trước đó có thể vẫn chưa commit. Caller cần quyết định rollback hoặc xử lý tiếp.

Mẫu xử lý:

~~~sql
BEGIN
    perform_step_one;
    perform_step_two;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Mẫu này phù hợp nếu block sở hữu toàn bộ transaction. Nếu block là một phần của transaction do caller quản lý, ROLLBACK toàn bộ có thể hủy cả công việc trước khi gọi block. Trong trường hợp đó, cân nhắc savepoint và quy ước rõ ràng giữa caller/callee; không nuốt exception mà không thông báo lỗi.

## 10. Isolation level và read consistency

Transaction boundary quyết định thay đổi nào được xác nhận; isolation level quyết định cách một transaction nhìn thấy thay đổi đồng thời từ session khác. Oracle hỗ trợ các chế độ chính:

| Chế độ | Ảnh dữ liệu được đọc | Có cho phép DML? |
| --- | --- | --- |
| READ COMMITTED (mặc định) | Mỗi câu SELECT đọc dữ liệu đã commit tại thời điểm câu lệnh bắt đầu, cộng với thay đổi của chính transaction | Có |
| SERIALIZABLE | Các câu lệnh trong transaction đọc theo ảnh nhất quán tại thời điểm transaction bắt đầu, cộng với thay đổi của chính transaction | Có, nhưng có thể gặp lỗi xung đột ghi |
| READ ONLY | Ảnh nhất quán ở thời điểm transaction bắt đầu | Không cho DML trong transaction |

Oracle không cho session đọc dữ liệu chưa commit của session khác (dirty read). Mức READ COMMITTED mặc định cung cấp **statement-level read consistency**; SERIALIZABLE và READ ONLY cung cấp ảnh nhất quán ở cấp transaction.

### READ COMMITTED: mặc định của Oracle

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE account_id = 'A';

-- Session khác có thể commit thay đổi ở đây.

SELECT balance
FROM accounts
WHERE account_id = 'A';
~~~

Hai câu SELECT riêng có thể nhìn thấy hai phiên bản đã commit khác nhau nếu session khác commit ở giữa. Điều này không phải dirty read: mỗi câu vẫn đọc một ảnh nhất quán tại thời điểm câu lệnh bắt đầu.

Đặc điểm này phù hợp với phần lớn ứng dụng OLTP vì transaction ngắn và mỗi statement nhìn thấy dữ liệu mới đã commit. Nếu nghiệp vụ cần nhiều câu SELECT cùng đọc một snapshot ổn định, cần cân nhắc READ ONLY hoặc SERIALIZABLE.

### SERIALIZABLE: ảnh nhất quán cho toàn transaction

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 'A';

-- Các truy vấn sau vẫn đọc snapshot tại thời điểm transaction bắt đầu.
SELECT COUNT(*)
FROM accounts
WHERE status = 'ACTIVE';

COMMIT;
~~~

SERIALIZABLE phù hợp khi một đơn vị công việc cần kết quả đọc nhất quán giữa nhiều statement. Nếu transaction cố cập nhật một hàng đã bị transaction khác thay đổi kể từ lúc transaction SERIALIZABLE bắt đầu, Oracle có thể báo ORA-08177: can't serialize access for this transaction. Ứng dụng cần xử lý bằng cách rollback và thử lại toàn bộ đơn vị công việc khi nghiệp vụ cho phép.

SERIALIZABLE không có nghĩa mọi transaction chạy tuần tự vật lý. Oracle dùng read consistency và kiểm tra xung đột để bảo đảm kết quả tương đương một thứ tự tuần tự hợp lệ; ứng dụng vẫn phải xử lý lỗi xung đột và constraint.

### READ ONLY: chỉ đọc trên một snapshot

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT department_id, SUM(salary)
FROM employees
GROUP BY department_id;

SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-01-01';

COMMIT;
~~~

Các SELECT trong transaction đọc cùng một snapshot nhất quán. Không thể thực hiện INSERT/UPDATE/DELETE trong transaction READ ONLY. Chế độ này hữu ích cho báo cáo cần nhiều truy vấn mà không muốn các câu sau nhìn thấy dữ liệu mới commit giữa chừng.

### Đặt isolation level đúng thời điểm

Các lệnh SET TRANSACTION phải là statement đầu tiên của transaction. Nếu session đang có transaction trước đó, hãy kết thúc nó trước:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;
~~~

Không chạy SELECT, DML hoặc statement khác rồi mới đặt isolation level cho transaction đó. Khi transaction kết thúc, chế độ thiết lập theo transaction cũng kết thúc; transaction tiếp theo trở lại chế độ mặc định hoặc chế độ được ứng dụng thiết lập.

## 11. Khóa và deadlock liên quan đến ranh giới transaction

Oracle dùng row-level locking cho DML. Hai session có thể cùng đọc một hàng, nhưng khi cùng muốn sửa một hàng đã bị session khác khóa, một session phải chờ hoặc nhận lỗi tùy câu lệnh và timeout.

### Ví dụ blocking

Session A:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Chưa commit.
~~~

Session B:

~~~sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 100;
~~~

Session B có thể chờ Session A kết thúc transaction. Khi A COMMIT, B tiếp tục theo trạng thái dữ liệu mới; khi A ROLLBACK, B có thể tiếp tục trên trạng thái trước thay đổi. Nếu A để transaction mở trong thời gian dài, B và các session khác có thể bị chặn.

### Deadlock

Deadlock xảy ra khi hai hoặc nhiều session giữ các khóa mà session kia cần, tạo thành vòng chờ. Ví dụ:

1. Session A khóa hàng tài khoản A.
2. Session B khóa hàng tài khoản B.
3. Session A muốn khóa hàng B và phải chờ B.
4. Session B muốn khóa hàng A và phải chờ A.

Oracle phát hiện deadlock và báo ORA-00060: deadlock detected while waiting for resource; statement liên quan trong một session bị rollback để phá vòng chờ. Ứng dụng phải xử lý lỗi và quyết định rollback transaction/try again theo quy tắc nghiệp vụ. Không giả định mọi thay đổi trước đó trong transaction đã tự động bị rollback toàn bộ.

### Cách giảm blocking và deadlock

- Cập nhật các hàng theo cùng một thứ tự khóa ở mọi luồng nghiệp vụ.
- Giữ transaction ngắn và commit/rollback sớm sau khi hoàn thành.
- Không giữ transaction trong lúc chờ nhập liệu hoặc gọi dịch vụ bên ngoài.
- Dùng điều kiện WHERE đủ chọn lọc và index phù hợp để tránh khóa/đọc nhiều hàng ngoài ý muốn.
- Xử lý timeout, deadlock và lỗi xung đột bằng logic retry có giới hạn.
- Không tự động retry một giao dịch không idempotent nếu chưa xác định liệu lần chạy trước có thể đã hoàn thành hay chưa.

## 12. Các hành vi dễ bị nhầm với transaction

### Sequence NEXTVAL không rollback

Giá trị sequence được cấp không phải là thay đổi DML có thể rollback:

~~~sql
SELECT order_seq.NEXTVAL
FROM dual;

ROLLBACK;
~~~

Giá trị đã lấy từ sequence không được trả lại khi rollback. Vì vậy sequence có thể có khoảng trống; không dùng sequence để tạo số thứ tự liên tục tuyệt đối cho chứng từ nếu nghiệp vụ yêu cầu không có gap.

### DDL có thể kết thúc transaction của caller

Một stored procedure hoặc script gọi DDL có thể gây implicit commit, dù caller không viết COMMIT. Vì vậy không đặt DDL vào giữa chuỗi DML mà kỳ vọng caller rollback toàn bộ.

### COMMIT trong procedure ảnh hưởng transaction của session

Procedure không sở hữu riêng một transaction thông thường. COMMIT trong procedure kết thúc transaction hiện tại của session, có thể bao gồm thay đổi do caller thực hiện trước khi gọi procedure. Quy ước transaction boundary nên được thiết kế rõ giữa tầng ứng dụng và stored procedure.

### Autonomous transaction là ngoại lệ có chủ đích

PL/SQL hỗ trợ autonomous transaction bằng pragma `AUTONOMOUS_TRANSACTION`. Transaction này độc lập với transaction chính; nó phải tự COMMIT hoặc ROLLBACK:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Nếu transaction chính sau đó ROLLBACK, bản ghi log của autonomous transaction vẫn tồn tại vì nó đã commit độc lập. Điều này hữu ích cho log lỗi cần tồn tại ngay cả khi nghiệp vụ thất bại, nhưng phải dùng có chủ đích: autonomous transaction không nhìn thấy thay đổi chưa commit của transaction chính và có thể gây xung đột nếu cố truy cập tài nguyên đang bị transaction chính khóa.

Autonomous transaction không phải cách chung để “commit một phần” transaction cha. Savepoint phù hợp cho rollback một phần trong cùng transaction; autonomous transaction là một transaction độc lập với vòng đời riêng.

## 13. Mẫu quản lý transaction trong ứng dụng

Một đơn vị công việc nên có điểm bắt đầu và kết thúc rõ ràng ở tầng sở hữu nghiệp vụ.

### Mẫu DML thành công hoặc rollback khi lỗi

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 'A'
      AND balance >= 100;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Insufficient funds or account missing');
    END IF;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 'B';

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Destination account missing');
    END IF;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Đoạn ví dụ kiểm tra số hàng cập nhật ở cả hai phía. Nếu bất kỳ điều kiện nào không đạt, exception làm block đi vào handler và rollback toàn transaction. Trong hệ thống thật, còn cần kiểm tra tài khoản gửi/nhận khác nhau, tiền tệ, giới hạn giao dịch, audit, idempotency và xử lý retry.

### Mẫu dùng savepoint cho một bước tùy chọn

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 500;

SAVEPOINT before_optional_note;

BEGIN
    INSERT INTO order_notes(order_id, note_text)
    VALUES (500, 'Optional note');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_note;
        -- Ghi nhận lỗi hoặc xử lý nhánh tùy chọn.
END;

COMMIT;
~~~

Mẫu này giữ thay đổi xác nhận đơn hàng nhưng cho phép hủy riêng bước thêm ghi chú. Nếu nghiệp vụ yêu cầu ghi chú là bắt buộc, không nên nuốt lỗi rồi vẫn commit đơn hàng.

### Ranh giới transaction trong JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        debitAccount(connection, sourceId, amount);
        creditAccount(connection, targetId, amount);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Trong ứng dụng có connection pool, cần trả connection về pool ở trạng thái sạch và khôi phục cấu hình connection nếu ứng dụng tự thay đổi isolation/autocommit. Không giả định đóng connection là một lệnh COMMIT an toàn.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ROLLBACK không hủy UPDATE trước đó | Một DDL đã implicit commit transaction trước nó | Xác định DDL trong script; tách DML/DDL thành các bước triển khai rõ ràng. |
| Hai UPDATE chỉ commit một phần | Client bật autocommit hoặc có COMMIT giữa các câu | Kiểm tra driver/client và đặt autocommit false khi cần transaction nhiều câu. |
| Session khác không thấy dữ liệu vừa UPDATE | Transaction chưa COMMIT | Commit sau khi đơn vị nghiệp vụ hoàn tất. |
| Session khác bị chờ khi UPDATE | Session trước giữ row lock chưa kết thúc transaction | Kết thúc transaction sớm; kiểm tra session/blocking. |
| SET TRANSACTION báo lỗi | Đã chạy statement khác trong transaction | Đặt SET TRANSACTION ngay đầu transaction, sau khi kết thúc transaction trước. |
| Procedure commit thay đổi không mong muốn | COMMIT trong procedure kết thúc transaction của caller | Để caller quản lý commit hoặc quy định rõ ownership. |
| Lỗi DML nhưng thay đổi trước đó vẫn còn | Statement lỗi không tự rollback toàn transaction | Xử lý exception và rollback toàn bộ hoặc quay về savepoint theo yêu cầu. |
| Không thể rollback TRUNCATE | TRUNCATE là DDL và implicit commit | Dùng DELETE nếu cần khả năng rollback; xác nhận phạm vi trước khi chạy. |
| Sequence bị nhảy số sau rollback | NEXTVAL không transactional | Chấp nhận gap; không dùng sequence làm số liên tục tuyệt đối. |
| ORA-08177 | Xung đột ghi trong SERIALIZABLE | Rollback và retry toàn transaction nếu an toàn. |
| ORA-00060 | Deadlock do vòng chờ khóa | Chuẩn hóa thứ tự cập nhật, giữ transaction ngắn, xử lý retry có giới hạn. |
| Connection pool giữ trạng thái transaction cũ | Trả connection khi transaction chưa kết thúc | Luôn COMMIT/ROLLBACK và khôi phục connection state trước khi trả pool. |

## 15. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE và quota phù hợp. DDL có implicit commit trong Oracle; không chạy các lệnh tạo/xóa bảng trên schema nghiệp vụ thật.

### Bước 1: tạo bảng tài khoản

~~~sql
CREATE TABLE lab_accounts (
    account_id VARCHAR2(10) PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO lab_accounts VALUES ('A', 1000);
INSERT INTO lab_accounts VALUES ('B', 500);
COMMIT;
~~~

### Bước 2: thực hiện DML rồi ROLLBACK

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 'A';

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

Quan sát giá trị trong cùng session trước rollback và sau rollback. Sau ROLLBACK, số dư trở về dữ liệu đã commit trước đó.

### Bước 3: thực hiện hai thay đổi rồi COMMIT

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 'B';

COMMIT;
~~~

Kiểm tra tổng số dư của hai tài khoản trước và sau. Tổng số dư phải được bảo toàn trong ví dụ này.

### Bước 4: dùng SAVEPOINT

~~~sql
UPDATE lab_accounts
SET balance = balance - 50
WHERE account_id = 'A';

SAVEPOINT after_debit;

UPDATE lab_accounts
SET balance = balance + 50
WHERE account_id = 'B';

ROLLBACK TO SAVEPOINT after_debit;

SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

ROLLBACK;
~~~

Quan sát: thay đổi trước savepoint vẫn còn trong transaction sau ROLLBACK TO SAVEPOINT; ROLLBACK cuối cùng hủy cả transaction.

### Bước 5: chứng minh DDL tạo implicit commit

~~~sql
UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 'A';

CREATE TABLE lab_ddl_marker (
    marker_id NUMBER PRIMARY KEY
);

ROLLBACK;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 'A';
~~~

UPDATE trước CREATE TABLE đã được commit ngầm. Vì vậy ROLLBACK cuối không đưa balance về giá trị cũ. Không dùng ví dụ này trên dữ liệu thật.

### Bước 6: thử read consistency bằng hai session

Mở hai session riêng trong SQL client.

Session A:

~~~sql
UPDATE lab_accounts
SET balance = 700
WHERE account_id = 'A';

-- Chưa COMMIT.
~~~

Session B:

~~~sql
SELECT balance
FROM lab_accounts
WHERE account_id = 'A';
~~~

Session B đọc giá trị đã commit trước đó, không đọc giá trị 700 chưa commit của A. Sau khi A COMMIT, chạy một SELECT mới ở B để quan sát giá trị đã commit.

### Bước 7: quan sát blocking

Session A:

~~~sql
UPDATE lab_accounts
SET balance = balance + 1
WHERE account_id = 'A';

-- Giữ transaction mở.
~~~

Session B:

~~~sql
UPDATE lab_accounts
SET balance = balance + 1
WHERE account_id = 'A';
~~~

Quan sát B chờ khóa. Quay lại A chạy COMMIT hoặc ROLLBACK; B sẽ tiếp tục theo kết quả của transaction A.

### Bước 8: dọn bảng thực hành

~~~sql
DROP TABLE lab_ddl_marker PURGE;
DROP TABLE lab_accounts PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu. DROP TABLE là DDL có implicit commit; PURGE bỏ qua Recycle Bin.

## 16. Câu hỏi tự kiểm tra

1. **Transaction trong Oracle thường bắt đầu khi nào?** Khi session thực hiện thao tác thay đổi dữ liệu đầu tiên sau ranh giới transaction trước đó; chế độ transaction đặc biệt phải được đặt trước statement đầu tiên.
2. **Có cần viết BEGIN TRANSACTION trong Oracle SQL không?** Không; transaction DML được quản lý ngầm định theo session.
3. **BEGIN/END của PL/SQL có tự commit không?** Không; đó là ranh giới block, không phải transaction boundary.
4. **COMMIT xác nhận những thay đổi nào?** Tất cả thay đổi chưa commit trong transaction hiện tại của session.
5. **ROLLBACK không có savepoint làm gì?** Hủy mọi thay đổi chưa commit của transaction hiện tại và kết thúc transaction.
6. **ROLLBACK TO SAVEPOINT có kết thúc transaction không?** Không; nó hủy thay đổi sau savepoint và transaction vẫn tiếp tục.
7. **Vì sao DDL nguy hiểm khi đang có DML chưa commit?** DDL gây implicit commit trước khi chạy và commit sau khi thành công.
8. **DELETE và TRUNCATE khác nhau thế nào về transaction?** DELETE là DML có thể rollback trước commit; TRUNCATE là DDL gây implicit commit.
9. **SELECT thông thường có khóa hàng không?** Không; SELECT thông thường đọc theo read consistency, còn SELECT FOR UPDATE khóa các hàng được chọn.
10. **Row lock được giữ đến khi nào?** Thông thường đến COMMIT hoặc ROLLBACK của transaction giữ khóa.
11. **Autocommit thuộc Oracle server hay client?** Là cấu hình của client/driver; cần kiểm tra trong công cụ hoặc connection pool thực tế.
12. **READ COMMITTED đọc snapshot ở mức nào?** Mỗi câu lệnh đọc ảnh nhất quán tại thời điểm statement bắt đầu.
13. **SERIALIZABLE khác READ COMMITTED thế nào?** Các câu trong transaction SERIALIZABLE dùng ảnh nhất quán ở thời điểm transaction bắt đầu; xung đột ghi có thể gây ORA-08177.
14. **READ ONLY cho phép DML không?** Không; nó cung cấp snapshot nhất quán để đọc trong transaction.
15. **Sequence NEXTVAL có rollback không?** Không; giá trị đã cấp không được trả lại khi rollback.
16. **Procedure có COMMIT ảnh hưởng gì tới caller?** Nó kết thúc transaction hiện tại của session, kể cả thay đổi do caller thực hiện trước khi gọi procedure.
17. **Autonomous transaction khác savepoint thế nào?** Autonomous transaction độc lập và có commit/rollback riêng; savepoint chỉ là mốc rollback trong transaction cha.
18. **Đóng connection có phải cách an toàn để commit không?** Không; hành vi phụ thuộc client/driver. Ứng dụng phải commit/rollback rõ ràng trước khi trả connection.

Ranh giới transaction trong Oracle được quyết định chủ yếu bởi COMMIT, ROLLBACK và các thao tác như DDL gây implicit commit. Transaction DML thường bắt đầu ngầm định trong session, còn SET TRANSACTION phải được đặt ngay đầu transaction khi cần isolation đặc biệt. Hãy quản lý transaction ở tầng sở hữu đơn vị nghiệp vụ, giữ transaction ngắn, xử lý lỗi rõ ràng và kiểm tra autocommit của client. Đặc biệt, đừng để một DDL, procedure tự commit hoặc connection pool vô tình kết thúc hay mang tiếp transaction mà ứng dụng chưa dự định.
