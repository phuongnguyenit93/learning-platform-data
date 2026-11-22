# Tính nguyên tử ở mức câu lệnh và mức giao dịch

Oracle Database xử lý thay đổi dữ liệu theo hai ranh giới quan trọng: **tính nguyên tử của câu lệnh (statement-level atomicity)** và **tính nguyên tử của giao dịch (transaction-level atomicity)**. Hai khái niệm liên quan nhưng không giống nhau. Một câu lệnh DML có thể thất bại và được hoàn tác riêng, trong khi những câu lệnh DML thành công trước đó vẫn còn trong giao dịch và chờ quyết định COMMIT hoặc ROLLBACK.

Hiểu đúng hai ranh giới này giúp tránh các lỗi nghiêm trọng như trừ tiền tài khoản nguồn nhưng không cộng được vào tài khoản đích, ghi một phần dữ liệu khi ứng dụng gặp lỗi, hoặc vô tình COMMIT công việc trước đó khi chạy DDL. Bài học trình bày cách Oracle bảo vệ một câu lệnh, cách nhóm nhiều câu lệnh thành một giao dịch, cách dùng SAVEPOINT, và cách các ứng dụng JDBC/PLSQL kiểm soát ranh giới giao dịch.

## 1. Atomicity trong ACID

ACID là bốn thuộc tính thường dùng để mô tả một giao dịch cơ sở dữ liệu:

| Thuộc tính | Ý nghĩa |
|---|---|
| Atomicity | Giao dịch được thực hiện trọn vẹn hoặc bị hoàn tác theo ranh giới giao dịch |
| Consistency | Giao dịch đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác theo các ràng buộc và quy tắc |
| Isolation | Các giao dịch đồng thời không nhìn thấy trạng thái trung gian theo cách vi phạm mức cô lập |
| Durability | Sau khi COMMIT thành công, thay đổi được lưu bền vững theo cơ chế phục hồi của Oracle |

Atomicity trả lời câu hỏi: **nếu một phần công việc thất bại, phần nào được giữ lại và phần nào phải bị hoàn tác?**

Trong Oracle, cần phân biệt:

- **Statement-level atomicity:** một câu lệnh DML thành công toàn bộ hoặc các thay đổi của chính câu lệnh đó bị hoàn tác.
- **Transaction-level atomicity:** một nhóm câu lệnh thuộc cùng giao dịch được COMMIT toàn bộ hoặc ROLLBACK toàn bộ.

Ví dụ một giao dịch chuyển tiền có thể gồm:

1. Trừ 500.000 đồng ở tài khoản A.
2. Cộng 500.000 đồng ở tài khoản B.
3. Ghi một dòng nhật ký giao dịch.

Nếu bước 2 thất bại, tính nguyên tử ở mức giao dịch yêu cầu bước 1 cũng phải được hoàn tác trước khi giao dịch kết thúc. Nếu chỉ dựa vào tính nguyên tử của từng câu lệnh, Oracle chỉ tự hoàn tác câu lệnh bước 2 bị lỗi; câu lệnh trừ tiền ở bước 1 vẫn là thay đổi đang chờ trong giao dịch.

## 2. Statement-level atomicity: một câu lệnh DML là một đơn vị

Oracle bảo đảm tính nguyên tử cho mỗi câu lệnh DML. Trước khi thực hiện DML, Oracle đặt một **implicit statement savepoint** (điểm lưu nội bộ của câu lệnh). Nếu câu lệnh thất bại, Oracle hoàn tác các thay đổi do câu lệnh đó tạo ra về điểm này.

Ví dụ:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;
~~~

Nếu câu lệnh thành công, thay đổi số lượng của hàng phù hợp trở thành một phần của giao dịch hiện tại. Nếu câu lệnh thất bại do lỗi ràng buộc, lỗi trigger hoặc một lỗi thực thi khác, Oracle hoàn tác các thay đổi của câu lệnh đó.

Điểm quan trọng: rollback nội bộ của một DML thất bại **không đồng nghĩa với ROLLBACK toàn bộ giao dịch**.

### 2.1 Một câu UPDATE nhiều hàng vẫn là một câu lệnh

Giả sử bảng có ràng buộc:

~~~sql
CREATE TABLE lab_salary (
    employee_id NUMBER PRIMARY KEY,
    salary      NUMBER(12,2),
    CONSTRAINT ck_lab_salary CHECK (salary <= 200000)
);

INSERT INTO lab_salary VALUES (1, 100000);
INSERT INTO lab_salary VALUES (2, 150000);
INSERT INTO lab_salary VALUES (3, 190000);
COMMIT;
~~~

Thử tăng lương tất cả nhân viên 10%:

~~~sql
UPDATE lab_salary
SET salary = salary * 1.10;
~~~

Hàng thứ ba sẽ vượt giới hạn CHECK. Khi câu UPDATE thất bại do ràng buộc, Oracle hoàn tác **toàn bộ thay đổi của câu UPDATE đó**. Hai hàng đầu không được giữ lại mức lương mới chỉ vì chúng được xử lý trước hàng thứ ba.

Kiểm tra:

~~~sql
SELECT employee_id, salary
FROM lab_salary
ORDER BY employee_id;
~~~

Các giá trị vẫn là 100.000, 150.000 và 190.000 như trước câu UPDATE. Nếu trước đó giao dịch có các câu DML thành công khác, những thay đổi trước đó vẫn còn pending và có thể được COMMIT hoặc ROLLBACK riêng.

### 2.2 Statement savepoint là nội bộ

Oracle tự tạo điểm lưu cho DML để có thể hoàn tác một câu lệnh thất bại. Người dùng không đặt tên, không truy vấn và không dùng trực tiếp implicit savepoint này trong SQL.

Nó khác với điểm lưu do ứng dụng tạo:

~~~sql
SAVEPOINT before_update;
~~~

`SAVEPOINT` có tên do người dùng quản lý và cho phép quay lại một vị trí trong giao dịch. Implicit statement savepoint là cơ chế nội bộ để Oracle bảo vệ một câu lệnh.

### 2.3 Thay đổi do trigger cũng thuộc câu lệnh gọi trigger

Nếu một trigger thông thường thực hiện INSERT/UPDATE/DELETE trên bảng khác trong cùng giao dịch, những thay đổi đó thuộc công việc của câu lệnh kích hoạt trigger. Nếu câu lệnh gốc thất bại và Oracle hoàn tác nó, các thay đổi transactional do trigger thực hiện cũng bị hoàn tác.

Ví dụ:

~~~sql
CREATE TABLE lab_salary_audit (
    employee_id NUMBER,
    old_salary  NUMBER(12,2),
    new_salary  NUMBER(12,2),
    changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE OR REPLACE TRIGGER trg_lab_salary_audit
AFTER UPDATE OF salary ON lab_salary
FOR EACH ROW
BEGIN
    INSERT INTO lab_salary_audit (
        employee_id, old_salary, new_salary
    )
    VALUES (
        :NEW.employee_id, :OLD.salary, :NEW.salary
    );
END;
/
~~~

Nếu câu UPDATE làm trigger chạy cho nhiều hàng nhưng sau đó câu lệnh thất bại, các dòng audit được ghi bởi trigger thông thường cũng bị hoàn tác cùng câu UPDATE. Điều này giúp bảng nghiệp vụ và bảng audit trong cùng transaction không bị lệch nhau chỉ vì một câu DML thất bại.

Điều kiện quan trọng là trigger không dùng cơ chế tạo giao dịch độc lập hoặc side effect ngoài transaction. Autonomous transaction và hệ thống bên ngoài được giải thích ở phần sau.

## 3. Điều gì xảy ra khi một câu lệnh thất bại?

Giả sử một giao dịch có ba câu lệnh:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

INSERT INTO transfer_log (
    transfer_id, from_account, to_account, amount
)
VALUES (9001, 10, 20, 100);
~~~

Nếu câu INSERT cuối thất bại do khóa chính bị trùng:

- Các thay đổi của câu INSERT bị hoàn tác.
- Hai câu UPDATE trước đó vẫn là thay đổi chưa COMMIT trong giao dịch.
- Ứng dụng có thể sửa nguyên nhân và tiếp tục, hoặc ROLLBACK toàn bộ giao dịch.

Oracle không tự động suy luận rằng lỗi ở câu INSERT có nghĩa toàn bộ nghiệp vụ chuyển tiền phải bị hủy. Ranh giới giao dịch do ứng dụng hoặc người gọi điều khiển bằng COMMIT/ROLLBACK.

### 3.1 Bảng so sánh

| Sự kiện | Điều Oracle tự động hoàn tác | Trạng thái giao dịch |
|---|---|---|
| Một câu INSERT thất bại | Các thay đổi của câu INSERT đó | Vẫn mở nếu chưa COMMIT/ROLLBACK |
| Một câu UPDATE nhiều hàng thất bại | Tất cả thay đổi của câu UPDATE đó | Các câu DML thành công trước đó vẫn pending |
| Một câu DELETE thất bại | Các thay đổi của câu DELETE đó | Vẫn mở nếu chưa kết thúc |
| Ứng dụng gọi ROLLBACK | Tất cả thay đổi chưa COMMIT trong giao dịch | Kết thúc giao dịch |
| Ứng dụng gọi COMMIT | Xác nhận tất cả thay đổi trong giao dịch | Kết thúc giao dịch |
| ROLLBACK TO SAVEPOINT | Thay đổi sau savepoint được chỉ định | Giao dịch vẫn mở |

### 3.2 Không dùng lỗi một câu lệnh để suy ra trạng thái toàn transaction

Sau khi bắt được exception, ứng dụng cần biết:

- Câu lệnh nào thất bại?
- Trước đó transaction đã thực hiện những DML nào?
- Có savepoint nghiệp vụ nào được đặt không?
- Quy tắc nghiệp vụ yêu cầu hủy cả giao dịch hay chỉ bỏ một phần?
- Có DDL hoặc client autocommit nào đã tạo ranh giới commit không?

Nếu ứng dụng chỉ log lỗi rồi tiếp tục chạy câu lệnh tiếp theo, các thay đổi trước lỗi vẫn có thể được COMMIT về sau. Đây là nguyên nhân phổ biến của trạng thái dữ liệu dở dang khi xử lý exception không đúng.

## 4. Transaction-level atomicity: nhóm câu lệnh thành một đơn vị nghiệp vụ

Một transaction có thể gồm nhiều câu SQL:

~~~sql
UPDATE accounts
SET balance = balance - 500
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500
WHERE account_id = 202;

INSERT INTO transfer_log (
    transfer_id, from_account, to_account, amount
)
VALUES (5001, 101, 202, 500);

COMMIT;
~~~

Khi COMMIT thành công, các thay đổi thuộc giao dịch được xác nhận cùng nhau. Nếu có lỗi trước COMMIT và nghiệp vụ yêu cầu hủy toàn bộ, ứng dụng gọi ROLLBACK:

~~~sql
ROLLBACK;
~~~

ROLLBACK hoàn tác mọi thay đổi của giao dịch hiện tại kể từ điểm bắt đầu giao dịch hoặc lần COMMIT/ROLLBACK gần nhất. Nó không hoàn tác dữ liệu đã COMMIT trong một giao dịch trước đó.

### 4.1 COMMIT

`COMMIT`:

- Xác nhận các thay đổi DML đang chờ của transaction.
- Làm các thay đổi trở thành dữ liệu đã commit.
- Kết thúc transaction hiện tại.
- Giải phóng các khóa giao dịch theo quy tắc Oracle.
- Xóa các savepoint của transaction.

Ví dụ:

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

COMMIT;
~~~

Sau COMMIT, ROLLBACK tiếp theo không thể đảo ngược câu UPDATE đã commit. Muốn khôi phục, cần một giao dịch mới ghi giá trị bù hoặc dùng cơ chế phục hồi phù hợp.

### 4.2 ROLLBACK

`ROLLBACK` không có savepoint:

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

DELETE FROM promotions
WHERE end_date < DATE '2026-01-01';

ROLLBACK;
~~~

Cả UPDATE và DELETE chưa commit đều bị hoàn tác. Transaction kết thúc; các savepoint của transaction cũng mất.

### 4.3 COMMIT không phải chỉ là “lưu câu lệnh cuối”

COMMIT áp dụng cho **toàn bộ transaction hiện tại**, không chỉ câu DML gần nhất. Nếu ứng dụng đã chạy năm câu UPDATE và sau đó COMMIT, cả năm câu thành công chưa commit đều được xác nhận.

Vì vậy, một lệnh COMMIT đặt sai trong stored procedure, script triển khai hoặc luồng ứng dụng có thể commit cả công việc trước đó của caller nếu chúng đang dùng cùng transaction/session.

## 5. SAVEPOINT và ROLLBACK TO SAVEPOINT

Không phải lúc nào cũng cần hủy toàn bộ transaction. SAVEPOINT đánh dấu một vị trí để có thể hoàn tác một phần:

~~~sql
UPDATE orders
SET status = 'READY'
WHERE order_id = 1001;

SAVEPOINT before_shipping;

INSERT INTO shipments (
    shipment_id, order_id, status
)
VALUES (7001, 1001, 'CREATED');

UPDATE inventory
SET reserved_qty = reserved_qty + 1
WHERE product_id = 55;

ROLLBACK TO SAVEPOINT before_shipping;
~~~

Sau ROLLBACK TO SAVEPOINT before_shipping:

- INSERT shipment bị hoàn tác.
- UPDATE inventory bị hoàn tác.
- UPDATE orders trước savepoint vẫn còn pending trong transaction.
- Transaction chưa kết thúc; ứng dụng có thể tiếp tục hoặc COMMIT/ROLLBACK sau đó.

### 5.1 SAVEPOINT không kết thúc transaction

`ROLLBACK TO SAVEPOINT` khác `ROLLBACK`:

| Lệnh | Phạm vi | Transaction còn mở? |
|---|---|---|
| `ROLLBACK` | Tất cả thay đổi chưa commit | Không |
| `ROLLBACK TO SAVEPOINT s` | Thay đổi sau savepoint s | Có |
| `COMMIT` | Xác nhận tất cả thay đổi chưa commit | Không |
| `SAVEPOINT s` | Đặt điểm quay lại | Có |

Savepoint không phải một transaction lồng nhau. Oracle không tạo một giao dịch độc lập mỗi khi gặp SAVEPOINT.

### 5.2 Savepoint cùng tên

Nếu tạo savepoint mới cùng tên với savepoint cũ, savepoint cũ cùng tên bị thay thế. Khi rollback tới một savepoint, các savepoint được tạo sau điểm đó bị xóa; savepoint đích vẫn có thể dùng lại cho tới khi transaction kết thúc hoặc bị thay thế.

### 5.3 COMMIT và ROLLBACK toàn phần xóa savepoint

Sau COMMIT hoặc ROLLBACK toàn phần, transaction kết thúc và savepoint cũ không còn hiệu lực. Không thể dùng savepoint từ transaction trước để rollback một transaction mới.

## 6. Ví dụ nghiệp vụ: chuyển tiền giữa hai tài khoản

Bài toán chuyển tiền cần bảo đảm:

1. Tài khoản nguồn tồn tại và đủ số dư.
2. Tài khoản đích tồn tại.
3. Tiền chỉ bị trừ khi có thể cộng vào tài khoản đích.
4. Nhật ký chuyển tiền được ghi cùng transaction.
5. Nếu bất kỳ bước bắt buộc nào thất bại, toàn bộ thay đổi của lần chuyển tiền phải được hoàn tác.

### 6.1 Bảng mẫu

~~~sql
CREATE TABLE lab_accounts (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_account_balance CHECK (balance >= 0)
);

CREATE TABLE lab_transfer_log (
    transfer_id   NUMBER(12) PRIMARY KEY,
    from_account  NUMBER(10) NOT NULL,
    to_account    NUMBER(10) NOT NULL,
    amount        NUMBER(14,2) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_lab_transfer_positive CHECK (amount > 0)
);

INSERT INTO lab_accounts VALUES (101, 2000);
INSERT INTO lab_accounts VALUES (202, 1000);
COMMIT;
~~~

### 6.2 Cách viết nhiều câu lệnh và kiểm tra số hàng

Ví dụ PL/SQL:

~~~sql
DECLARE
    l_amount NUMBER(14,2) := 500;
BEGIN
    SAVEPOINT transfer_start;

    UPDATE lab_accounts
    SET balance = balance - l_amount
    WHERE account_id = 101
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        ROLLBACK TO transfer_start;
        RAISE_APPLICATION_ERROR(
            -20001,
            'Tai khoan nguon khong ton tai hoac khong du so du'
        );
    END IF;

    UPDATE lab_accounts
    SET balance = balance + l_amount
    WHERE account_id = 202;

    IF SQL%ROWCOUNT <> 1 THEN
        ROLLBACK TO transfer_start;
        RAISE_APPLICATION_ERROR(
            -20002,
            'Tai khoan dich khong ton tai'
        );
    END IF;

    INSERT INTO lab_transfer_log (
        transfer_id, from_account, to_account, amount
    )
    VALUES (5001, 101, 202, l_amount);

    -- Caller quyết định COMMIT sau khi nghiệp vụ hoàn tất.
END;
/
~~~

Đây là ví dụ cho thấy:

- Mỗi UPDATE/INSERT có statement-level atomicity riêng.
- SAVEPOINT tạo ranh giới để hủy riêng các thay đổi của lần chuyển tiền.
- Khi một bước không đáp ứng điều kiện, ROLLBACK TO SAVEPOINT hủy phần chuyển tiền đã làm.
- Khi tất cả bước thành công, caller vẫn cần COMMIT để xác nhận transaction.

Nếu khối PL/SQL được gọi trong một transaction đã có công việc trước đó, savepoint giúp rollback phần chuyển tiền mà giữ lại công việc trước savepoint. Nếu yêu cầu là hủy toàn bộ transaction, caller có thể gọi ROLLBACK toàn phần.

### 6.3 Vì sao phải kiểm tra SQL%ROWCOUNT?

Một câu UPDATE có thể không lỗi nhưng vẫn cập nhật 0 hàng:

~~~sql
UPDATE lab_accounts
SET balance = balance + 500
WHERE account_id = 999;
~~~

Không có tài khoản 999 thì câu lệnh vẫn thực thi thành công về mặt SQL, nhưng SQL%ROWCOUNT bằng 0. Oracle không tự báo lỗi chỉ vì không có hàng khớp. Ứng dụng phải xác định 0 hàng có hợp lệ hay không.

### 6.4 Xử lý exception và rollback

Có thể bổ sung exception handler:

~~~sql
DECLARE
    l_amount NUMBER(14,2) := 500;
BEGIN
    SAVEPOINT transfer_start;

    UPDATE lab_accounts
    SET balance = balance - l_amount
    WHERE account_id = 101
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Insufficient source balance');
    END IF;

    UPDATE lab_accounts
    SET balance = balance + l_amount
    WHERE account_id = 202;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Destination account not found');
    END IF;

    INSERT INTO lab_transfer_log (
        transfer_id, from_account, to_account, amount
    )
    VALUES (5002, 101, 202, l_amount);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO transfer_start;
        RAISE;
END;
/
~~~

Handler rollback tới savepoint rồi ném lại lỗi để caller biết giao dịch thất bại. Không nuốt exception rồi trả về trạng thái thành công giả. Caller cần quyết định có tiếp tục transaction hay rollback toàn phần.

Trong code production, phải xác định cách tạo transfer ID, xử lý retry, khóa tài khoản và kiểm tra số dư theo yêu cầu đồng thời. Ví dụ trên minh họa ranh giới nguyên tử, không thay thế thiết kế chống giao dịch trùng hoặc quy trình đối soát.

## 7. Statement atomicity không thay thế kiểm soát đồng thời

Tính nguyên tử đảm bảo một câu lệnh không để lại một phần thay đổi khi câu lệnh thất bại. Nó không tự giải quyết mọi race condition giữa nhiều session.

Ví dụ hai session cùng đọc số dư 500 rồi cùng quyết định chuyển 400. Nếu ứng dụng đọc số dư ở một câu SELECT riêng, sau đó mới UPDATE không có điều kiện kiểm tra, cả hai session có thể đưa ra quyết định dựa trên dữ liệu cũ.

Một cách giảm rủi ro là đặt điều kiện nghiệp vụ trong chính UPDATE:

~~~sql
UPDATE lab_accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Sau đó kiểm tra SQL%ROWCOUNT. Oracle khóa hàng được cập nhật; các transaction đồng thời phải tuân theo cơ chế khóa và tính nhất quán đọc của Oracle. Với nghiệp vụ phức tạp cần đọc nhiều hàng trước khi quyết định, có thể dùng SELECT ... FOR UPDATE để khóa các hàng liên quan trong transaction.

Atomicity, isolation và locking có liên quan nhưng giải quyết các câu hỏi khác nhau:

- Atomicity: thay đổi được hoàn tác trong phạm vi nào?
- Isolation: giao dịch đồng thời nhìn thấy dữ liệu ra sao?
- Locking: session nào có thể thay đổi hàng đang bị session khác giữ khóa?

## 8. Ranh giới transaction trong SQL*Plus và công cụ SQL

Oracle Database quản lý transaction ở server. Công cụ client có thể tác động tới ranh giới đó bằng thiết lập autocommit.

### 8.1 Autocommit tắt

Trong một session SQL*Plus thông thường, DML thường được giữ pending cho tới khi người dùng gọi COMMIT hoặc ROLLBACK, trừ khi cấu hình/autocommit thay đổi:

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 202;

-- Chưa COMMIT: thay đổi vẫn thuộc transaction hiện tại.
ROLLBACK;
~~~

Cả hai UPDATE bị hoàn tác.

### 8.2 Autocommit bật

Một số client có tùy chọn autocommit hoặc lệnh cấu hình tương ứng. Khi bật, client có thể COMMIT sau mỗi câu DML thành công. Khi đó:

1. UPDATE đầu tiên hoàn tất và được commit.
2. UPDATE thứ hai là một transaction khác.
3. Nếu UPDATE thứ hai thất bại, UPDATE đầu tiên vẫn đã commit.

Điều này phá vỡ ý định gom nhiều câu lệnh thành một giao dịch nghiệp vụ. Khi cần transaction nhiều bước, phải kiểm tra rõ thiết lập autocommit của công cụ.

Tên menu và mặc định autocommit khác nhau giữa SQL Developer, SQLcl, SQL*Plus và công cụ bên thứ ba. Không suy luận hành vi chỉ từ việc nhấn nút Run; hãy kiểm tra cấu hình session/client.

### 8.3 DDL có implicit COMMIT

Các lệnh DDL như CREATE, ALTER, DROP và TRUNCATE có quy tắc commit ngầm trong Oracle. DDL thường commit transaction hiện tại trước khi thực thi; DDL thành công cũng commit sau khi thực thi.

Ví dụ:

~~~sql
UPDATE lab_accounts
SET balance = balance + 100
WHERE account_id = 101;

CREATE TABLE lab_temp_note (
    note_id NUMBER
);

ROLLBACK;
~~~

UPDATE trước DDL có thể đã được commit bởi implicit commit trước khi CREATE TABLE chạy. ROLLBACK cuối không thể hoàn tác UPDATE đó. Đây là lý do không nên trộn DDL vào giữa một transaction nghiệp vụ cần atomicity.

Nếu DDL thất bại, commit ngầm trước khi thực thi vẫn có thể đã kết thúc transaction trước đó. Không dùng DDL như một thao tác “thử” trong transaction mà muốn rollback toàn bộ khi có lỗi.

## 9. Transaction trong PL/SQL

PL/SQL block, procedure hoặc function chạy trong transaction của session gọi nó, trừ khi code chủ động điều khiển transaction. Việc một procedure kết thúc bình thường không tự động có nghĩa transaction đã COMMIT.

Ví dụ procedure chỉ thực hiện DML:

~~~sql
CREATE OR REPLACE PROCEDURE update_product_price (
    p_product_id IN NUMBER,
    p_new_price  IN NUMBER
) AS
BEGIN
    UPDATE products
    SET price = p_new_price
    WHERE product_id = p_product_id;
END;
/
~~~

Caller có thể:

~~~sql
BEGIN
    update_product_price(10, 250);
    -- Thực hiện thêm các bước nghiệp vụ khác.
    COMMIT;
END;
/
~~~

Nếu procedure tự gọi COMMIT, nó sẽ commit tất cả thay đổi pending trong cùng transaction/session, kể cả những thay đổi do caller thực hiện trước khi gọi procedure. Vì vậy, transaction ownership phải được thiết kế rõ ràng.

### 9.1 Exception không tự động có nghĩa rollback toàn bộ

Khi DML bên trong PL/SQL thất bại, Oracle áp dụng statement-level atomicity cho DML đó. Những DML thành công trước đó trong cùng transaction có thể vẫn còn pending. Exception handler có thể:

- ROLLBACK TO SAVEPOINT để hủy một phần.
- ROLLBACK để hủy toàn transaction.
- Xử lý lỗi và tiếp tục nếu nghiệp vụ cho phép.
- Ném lại exception cho caller quyết định.

Không nên viết:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

nếu điều đó khiến caller không biết thao tác đã thất bại. Nuốt lỗi có thể làm ứng dụng tiếp tục và COMMIT các thay đổi trước lỗi trong trạng thái nghiệp vụ không hoàn chỉnh.

### 9.2 COMMIT trong stored procedure

Một procedure dùng trong nhiều luồng nghiệp vụ thường nên để caller quản lý transaction, trừ khi hợp đồng của procedure quy định rõ nó là một đơn vị tự commit. Đặt COMMIT tùy tiện bên trong procedure làm caller khó kết hợp procedure với các bước khác theo atomicity.

Nếu procedure cần một phần log độc lập tồn tại kể cả khi transaction chính rollback, đó là một yêu cầu khác và phải được thiết kế có chủ đích bằng autonomous transaction hoặc hệ thống log phù hợp; không dùng COMMIT ngẫu nhiên để đạt hiệu ứng đó.

## 10. Transaction trong JDBC

JDBC cung cấp API điều khiển autocommit, commit và rollback.

### 10.1 Autocommit mặc định

Theo JDBC, connection mới thường ở chế độ autocommit. Khi autocommit bật, mỗi câu SQL được commit khi thực thi hoàn tất. Muốn nhiều câu lệnh thuộc cùng transaction, ứng dụng phải tắt autocommit.

~~~java
Connection connection = dataSource.getConnection();

try {
    connection.setAutoCommit(false);

    try (PreparedStatement debit = connection.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE account_id = ? AND balance >= ?")) {
        debit.setBigDecimal(1, amount);
        debit.setLong(2, sourceAccountId);
        debit.setBigDecimal(3, amount);

        int updated = debit.executeUpdate();
        if (updated != 1) {
            throw new SQLException("Source account missing or insufficient");
        }
    }

    try (PreparedStatement credit = connection.prepareStatement(
            "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
        credit.setBigDecimal(1, amount);
        credit.setLong(2, destinationAccountId);

        int updated = credit.executeUpdate();
        if (updated != 1) {
            throw new SQLException("Destination account not found");
        }
    }

    try (PreparedStatement log = connection.prepareStatement(
            "INSERT INTO transfer_log " +
            "(transfer_id, from_account, to_account, amount) " +
            "VALUES (?, ?, ?, ?)")) {
        log.setLong(1, transferId);
        log.setLong(2, sourceAccountId);
        log.setLong(3, destinationAccountId);
        log.setBigDecimal(4, amount);
        log.executeUpdate();
    }

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.close();
}
~~~

Ví dụ thể hiện một transaction gồm debit, credit và insert log. Nếu bất kỳ bước nào thất bại, catch gọi rollback để hủy mọi thay đổi chưa commit trong transaction. `setAutoCommit(false)` là bước quan trọng để các câu lệnh thực sự thuộc cùng transaction.

Trong code production dùng connection pool, cần tuân theo quy ước của pool/framework về trả connection, reset trạng thái và xử lý lỗi rollback. Không nên thay đổi autocommit tùy tiện rồi trả connection về pool khi transaction chưa được xử lý.

Không gọi §setAutoCommit(true)§ một cách vô điều kiện trong §finally§ sau một lần rollback có thể thất bại: JDBC có thể commit transaction hiện tại khi chuyển autocommit từ false sang true. Hãy xử lý kết quả commit/rollback trước, rồi để connection pool reset trạng thái theo cấu hình của nó hoặc thực hiện reset chỉ khi transaction đã được kết thúc chắc chắn.

### 10.2 Nếu quên setAutoCommit(false)

Khi autocommit vẫn bật:

~~~java
connection.setAutoCommit(true);
debitStatement.executeUpdate();   // có thể đã commit
creditStatement.executeUpdate();  // transaction riêng
~~~

Nếu credit thất bại, rollback sau đó không thể đảo ngược debit đã commit. Mỗi câu lệnh có statement atomicity, nhưng nghiệp vụ chuyển tiền không có transaction atomicity như mong muốn.

### 10.3 Không commit trong mọi nhánh thành công nhỏ

Trong một luồng nghiệp vụ nhiều bước, chỉ commit tại ranh giới mà toàn bộ đơn vị nghiệp vụ được xem là hoàn tất. Nếu một helper method tự commit sau khi cập nhật một bảng, caller không thể rollback helper đó khi bước tiếp theo thất bại.

## 11. SAVEPOINT trong JDBC

JDBC có API tạo và rollback savepoint:

~~~java
Savepoint beforeShipping = connection.setSavepoint("before_shipping");

try {
    createShipment(connection, orderId);
    reserveInventory(connection, productId);
} catch (SQLException ex) {
    connection.rollback(beforeShipping);
    throw ex;
}

// Transaction vẫn mở; caller còn quyết định commit hay rollback.
~~~

`connection.rollback(savepoint)` chỉ rollback phần thay đổi sau savepoint. Nó không commit phần trước savepoint và không kết thúc transaction. Sau đó caller có thể tiếp tục hoặc rollback toàn bộ.

Không phải mọi driver, database hoặc connection mode đều hỗ trợ mọi tính năng savepoint giống nhau. Với Oracle JDBC, cần dùng cùng connection đang sở hữu transaction và xử lý SQLException phù hợp.

## 12. DML Error Logging: chủ động cho phép một phần hàng thành công

Statement-level atomicity là hành vi mặc định khi một câu DML thất bại. Tuy nhiên Oracle có tính năng **DML error logging** cho phép một số lỗi ở cấp hàng được ghi vào bảng lỗi, trong khi câu DML tiếp tục xử lý các hàng khác.

Đây là một cơ chế có chủ đích để nạp dữ liệu không hoàn toàn sạch. Cần phân biệt:

- Không dùng error logging: lỗi DML làm câu lệnh thất bại và thay đổi của câu lệnh bị rollback.
- Dùng error logging: những hàng lỗi thuộc nhóm được hỗ trợ có thể được ghi vào error table; các hàng hợp lệ vẫn được xử lý, câu lệnh có thể hoàn tất thành công.

### 12.1 Tạo error logging table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'ORDERS',
        err_log_table_name  => 'ERR$_ORDERS'
    );
END;
/
~~~

Thủ tục tạo bảng lưu thông tin lỗi cho bảng mục tiêu. Cần tạo bảng lỗi trong schema phù hợp và kiểm tra quyền truy cập.

### 12.2 INSERT với LOG ERRORS

~~~sql
INSERT INTO orders (
    order_id, customer_id, order_amount
)
SELECT order_id, customer_id, order_amount
FROM staging_orders
LOG ERRORS INTO err$_orders ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

Các hàng hợp lệ có thể được insert; những hàng gặp lỗi được ghi vào error table theo phạm vi lỗi mà DML error logging hỗ trợ. Sau đó ứng dụng có thể xem:

~~~sql
SELECT ora_err_number$,
       ora_err_mesg$,
       ora_err_tag$,
       order_id,
       customer_id
FROM err$_orders
WHERE ora_err_tag$ = 'BATCH_20261114';
~~~

Các thay đổi thành công và bản ghi error log vẫn thuộc transaction hiện tại. Nếu ROLLBACK transaction, chúng cũng bị rollback; nếu COMMIT, cả dữ liệu được nạp và error log được xác nhận.

### 12.3 Error logging không áp dụng cho mọi lỗi

DML error logging có các giới hạn theo loại lỗi, thao tác, cột và cấu trúc bảng. Một số lỗi như lỗi cú pháp, lỗi mở rộng/khởi tạo, lỗi ràng buộc hoặc lỗi phát sinh trong một số đường thực thi có thể không được xử lý như lỗi từng hàng. Đọc SQL Language Reference của phiên bản mục tiêu trước khi thiết kế pipeline nạp dữ liệu.

Không dùng LOG ERRORS nếu nghiệp vụ yêu cầu tất cả hàng phải thành công hoặc tất cả phải bị hủy. Trong trường hợp đó, hãy để statement/transaction thất bại và rollback đúng phạm vi.

## 13. FORALL SAVE EXCEPTIONS trong PL/SQL

Với bulk DML trong PL/SQL, `FORALL ... SAVE EXCEPTIONS` cho phép tiếp tục các lần thực thi DML còn lại khi một số lần bị lỗi và thu thập lỗi trong `SQL%BULK_EXCEPTIONS`.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE products
        SET price = price * 1.05
        WHERE product_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
        -- Quyết định COMMIT/ROLLBACK thuộc logic transaction của ứng dụng.
END;
/
~~~

`SAVE EXCEPTIONS` là cơ chế xử lý lỗi cho các lần thực thi bulk; nó không tự quyết định nghiệp vụ có nên giữ các lần thành công hay hủy toàn bộ transaction. Ứng dụng phải đọc danh sách lỗi, xác định dữ liệu hợp lệ và quyết định COMMIT/ROLLBACK. Không nhầm nó với `SAVEPOINT` của transaction.

## 14. Constraint có thể được kiểm tra ở thời điểm COMMIT

Oracle hỗ trợ một số constraint có thể khai báo DEFERRABLE. Khi constraint được đặt ở chế độ DEFERRED, kiểm tra có thể được trì hoãn tới thời điểm COMMIT thay vì bắt buộc ngay sau từng câu lệnh.

Ví dụ về khóa ngoại có thể trì hoãn:

~~~sql
ALTER TABLE child_orders
ADD CONSTRAINT fk_child_parent
FOREIGN KEY (parent_id)
REFERENCES parent_orders(parent_id)
DEFERRABLE INITIALLY IMMEDIATE;
~~~

Trong transaction:

~~~sql
SET CONSTRAINTS fk_child_parent DEFERRED;

-- Thực hiện các thay đổi tạm thời có thể vi phạm quan hệ
-- trong quá trình chuyển đổi, nhưng phải hợp lệ khi COMMIT.

COMMIT;
~~~

Nếu constraint deferred vẫn bị vi phạm tại thời điểm COMMIT, COMMIT không hoàn tất thành công. Ứng dụng phải sửa trạng thái hoặc ROLLBACK theo quy tắc nghiệp vụ. Điều này cho thấy lỗi có thể xuất hiện ở ranh giới kết thúc transaction dù từng câu DML đã thực thi thành công.

Không phải mọi constraint đều có thể defer; cú pháp và khả năng áp dụng phụ thuộc loại constraint. Kiểm tra định nghĩa constraint và trạng thái hiện tại trước khi dùng.

## 15. DDL và implicit COMMIT: ngoại lệ quan trọng khi nói về transaction

Trong Oracle, DDL thường tạo ranh giới commit ngầm. Những lệnh như CREATE, ALTER, DROP, TRUNCATE và CREATE INDEX có thể commit transaction đang mở trước khi DDL thực thi; DDL thành công cũng commit sau khi thực thi.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 101;

TRUNCATE TABLE staging_data;

ROLLBACK;
~~~

ROLLBACK cuối không thể hoàn tác UPDATE đã bị commit ngầm trước khi TRUNCATE chạy. Bản thân TRUNCATE cũng không thể rollback như DELETE thông thường.

### 15.1 Tách triển khai schema khỏi transaction nghiệp vụ

Không nên đặt CREATE/ALTER/TRUNCATE giữa các bước của một transaction chuyển tiền, đặt hàng hoặc thanh toán. Tổ chức script thành:

1. Bước triển khai schema/migration có ranh giới DDL riêng.
2. Bước nạp/biến đổi dữ liệu.
3. Bước xác nhận nghiệp vụ bằng transaction DML.

Nếu cần thao tác DDL trong quy trình triển khai, hãy hiểu rõ commit boundary và có kế hoạch phục hồi riêng.

## 16. Autonomous transaction và side effect ngoài transaction cha

PL/SQL hỗ trợ autonomous transaction qua `PRAGMA AUTONOMOUS_TRANSACTION`. Đây là một transaction độc lập với transaction gọi nó. Nó có thể COMMIT hoặc ROLLBACK riêng; kết quả đã commit không bị rollback khi transaction cha rollback.

Ví dụ minh họa:

~~~sql
CREATE OR REPLACE PROCEDURE write_independent_log (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO independent_audit(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Nếu transaction cha gọi procedure này rồi ROLLBACK, dòng audit đã được autonomous transaction COMMIT vẫn còn. Đây có thể là mục đích khi ghi nhận lỗi cần tồn tại độc lập, nhưng cũng có thể làm mất tính nguyên tử của dữ liệu nếu dùng sai.

### 16.1 Không dùng autonomous transaction cho dữ liệu phải cùng commit

Nếu trigger ghi một dòng ledger qua autonomous transaction trong khi UPDATE tài khoản thuộc transaction cha, có thể xảy ra:

- Ledger đã commit.
- Transaction cha thất bại và rollback số dư.
- Nhật ký vẫn tồn tại như thể nghiệp vụ đã xảy ra.

Vì vậy, audit/ledger cần nhất quán với nghiệp vụ thường nên ở cùng transaction. Chỉ dùng autonomous transaction khi yêu cầu độc lập được xác định rõ.

### 16.2 Sequence không rollback

Giá trị lấy từ Oracle sequence qua `NEXTVAL` không được trả lại khi transaction rollback. Ví dụ:

~~~sql
INSERT INTO orders(order_id, customer_id)
VALUES (order_seq.NEXTVAL, 100);

ROLLBACK;
~~~

Hàng INSERT bị rollback, nhưng số sequence đã cấp vẫn được tiêu thụ. Lần NEXTVAL sau có thể tạo khoảng trống. Sequence được thiết kế để cấp số an toàn cho nhiều session, không phải bộ đếm liên tục không có khoảng trống.

Không dùng việc thiếu số sequence để kết luận có hàng đã commit hoặc giao dịch bị mất dữ liệu.

### 16.3 Side effect bên ngoài database

Gửi email, gọi HTTP API, ghi file hoặc gửi thông điệp sang hệ thống ngoài không tự động rollback cùng Oracle transaction. Nếu ứng dụng:

1. Cập nhật đơn hàng.
2. Gửi email xác nhận.
3. ROLLBACK transaction vì bước sau thất bại.

email đã gửi có thể vẫn tồn tại dù đơn hàng không được commit. Cần thiết kế tích hợp đáng tin cậy, chẳng hạn transactional outbox: ghi sự kiện vào bảng outbox cùng transaction nghiệp vụ, sau COMMIT một tiến trình khác gửi thông điệp và đánh dấu trạng thái.

## 17. Distributed transaction

Khi một transaction cập nhật nhiều database tham gia một giao dịch phân tán, Oracle có thể dùng cơ chế two-phase commit (2PC) để phối hợp các participant:

1. **Prepare:** các participant chuẩn bị và xác nhận có thể commit.
2. **Commit:** coordinator yêu cầu các participant commit sau khi tất cả đã prepare thành công.

Mục tiêu là giữ tính nguyên tử trên các database tham gia. Trong sự cố mạng hoặc coordinator, transaction phân tán có thể ở trạng thái in-doubt và cần cơ chế recovery/DBA xử lý.

2PC không làm cho mọi side effect bên ngoài trở thành transactional. Một email server hoặc REST API không tự động tham gia transaction Oracle chỉ vì được gọi từ ứng dụng.

## 18. Atomicity, isolation và read consistency

Không nên dùng từ “atomicity” để giải thích mọi hành vi đồng thời.

Oracle cung cấp read consistency để câu SELECT nhìn thấy một phiên bản dữ liệu nhất quán theo cơ chế MVCC. Ở mức READ COMMITTED mặc định, mỗi câu lệnh đọc có snapshot nhất quán tại thời điểm bắt đầu câu lệnh. Isolation/locking quyết định các transaction đồng thời tương tác như thế nào.

Ví dụ:

- Statement-level atomicity bảo đảm một UPDATE thất bại không để lại một nửa hàng đã cập nhật.
- Transaction-level atomicity bảo đảm debit và credit cùng commit hoặc cùng rollback nếu được gom trong một transaction.
- Isolation và locking giúp xử lý hai session cùng chuyển tiền hoặc cùng sửa một hàng.

Ba vấn đề phải được thiết kế cùng nhau nhưng không thay thế nhau.

## 19. Kiểm chứng bằng hai session

Có thể quan sát transaction atomicity bằng hai session SQL riêng.

### 19.1 Session A: thay đổi nhưng chưa commit

~~~sql
UPDATE lab_accounts
SET balance = balance - 100
WHERE account_id = 101;

-- Chưa COMMIT.
~~~

### 19.2 Session B: đọc dữ liệu

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 101;
~~~

Trong READ COMMITTED, session B không nhìn thấy thay đổi chưa commit của session A; nó đọc phiên bản đã commit phù hợp với snapshot của câu SELECT.

### 19.3 Session A kết thúc transaction

Thử:

~~~sql
COMMIT;
~~~

Chạy lại SELECT ở session B. Sau commit, câu SELECT mới có thể nhìn thấy số dư mới. Nếu thay COMMIT bằng ROLLBACK, giá trị trở về trạng thái trước transaction.

Thí nghiệm này kiểm tra tính hiển thị và ranh giới transaction; nó không phải phép đo hiệu năng hoặc bằng chứng đầy đủ cho mọi isolation level.

## 20. Kiểm chứng statement atomicity bằng lỗi ràng buộc

Thực hiện trong schema thử nghiệm:

~~~sql
CREATE TABLE lab_atomicity_test (
    id NUMBER PRIMARY KEY,
    value_num NUMBER,
    CONSTRAINT ck_lab_atomicity_value CHECK (value_num <= 100)
);

INSERT INTO lab_atomicity_test VALUES (1, 10);
INSERT INTO lab_atomicity_test VALUES (2, 20);
COMMIT;
~~~

Chạy một câu lệnh làm một hàng vi phạm:

~~~sql
UPDATE lab_atomicity_test
SET value_num = CASE
    WHEN id = 1 THEN 50
    WHEN id = 2 THEN 150
END;
~~~

Do hàng id 2 vi phạm CHECK, câu UPDATE thất bại và các thay đổi của chính câu UPDATE bị hoàn tác. Kiểm tra:

~~~sql
SELECT id, value_num
FROM lab_atomicity_test
ORDER BY id;
~~~

Hai hàng vẫn giữ 10 và 20. Tiếp theo thực hiện một câu UPDATE hợp lệ rồi một câu UPDATE lỗi khác; sau lỗi, câu hợp lệ trước đó vẫn pending cho tới khi COMMIT/ROLLBACK toàn transaction.

## 21. Ma trận quyết định: rollback ở đâu?

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Một câu DML vi phạm constraint và không có cơ chế partial error | Để statement thất bại; Oracle rollback thay đổi của câu lệnh |
| Câu DML thất bại nhưng các bước trước của nghiệp vụ phải bị hủy | ROLLBACK toàn transaction hoặc tới savepoint nghiệp vụ |
| Một bước tùy chọn thất bại, phần trước savepoint vẫn hợp lệ | ROLLBACK TO SAVEPOINT rồi tiếp tục theo quy tắc |
| Nạp batch và muốn giữ hàng hợp lệ, cách ly hàng lỗi | DML error logging hoặc bulk error handling phù hợp |
| Constraint deferred chỉ được kiểm tra ở COMMIT | Kiểm tra lỗi commit và xử lý transaction chưa hoàn tất |
| DDL chạy giữa các DML | Tách ranh giới; lưu ý implicit commit |
| Cần log lỗi tồn tại sau rollback nghiệp vụ | Cân nhắc autonomous transaction có chủ đích |
| Gọi API/email bên ngoài rồi transaction rollback | Dùng outbox/compensation; không giả định side effect tự rollback |
| Nhiều câu DML qua JDBC | Tắt autocommit, commit/rollback tại ranh giới nghiệp vụ |

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Câu UPDATE lỗi nhưng các câu trước vẫn còn | Nhầm statement rollback với transaction rollback | Gọi ROLLBACK hoặc ROLLBACK TO SAVEPOINT theo nghiệp vụ |
| Chuyển tiền bị trừ nguồn nhưng không cộng đích | Mỗi DML được chạy/commit riêng hoặc exception không rollback transaction | Gom debit, credit, log vào một transaction |
| JDBC rollback nhưng dữ liệu vẫn thay đổi | Autocommit đã commit câu trước | Gọi setAutoCommit(false) trước DML |
| ROLLBACK không hoàn tác UPDATE trước DDL | DDL đã implicit commit | Tách DDL khỏi transaction nghiệp vụ |
| Procedure lỗi nhưng thay đổi trước lỗi vẫn pending | Exception không tự động rollback toàn transaction | Quản lý savepoint/rollback rõ ràng |
| Procedure helper commit quá sớm | COMMIT trong procedure kết thúc cả transaction session | Để caller quản lý transaction hoặc định nghĩa contract rõ |
| Số sequence bị nhảy | NEXTVAL không rollback | Chấp nhận khoảng trống; không dùng sequence làm số liên tục |
| Audit còn dù nghiệp vụ rollback | Trigger/procedure dùng autonomous transaction | Chỉ dùng autonomous transaction cho log độc lập có chủ đích |
| Email đã gửi nhưng đơn hàng rollback | Side effect ngoài database không tham gia transaction | Dùng transactional outbox hoặc cơ chế bù trừ |
| Batch chỉ lưu một phần dữ liệu | Dùng LOG ERRORS/SAVE EXCEPTIONS có chủ đích hoặc transaction bị commit giữa chừng | Đọc error log và quyết định commit policy |
| COMMIT báo lỗi do deferred constraint | Constraint được kiểm tra ở thời điểm commit | Sửa dữ liệu hoặc rollback; kiểm tra DEFERRABLE |
| Không có hàng UPDATE nhưng ứng dụng nghĩ thành công | SQL không coi rowcount 0 là lỗi | Kiểm tra SQL%ROWCOUNT hoặc executeUpdate() |

## 23. Bài thực hành tự kiểm tra

### Bài 1 — Statement-level atomicity

Tạo bảng có CHECK constraint, chạy một UPDATE nhiều hàng trong đó một hàng vi phạm. Kiểm tra xem những hàng khác trong cùng UPDATE có được giữ thay đổi không. Giải thích vai trò của implicit statement savepoint.

### Bài 2 — Transaction-level atomicity

Chạy hai UPDATE thành công trong cùng session, sau đó ROLLBACK. Xác nhận cả hai thay đổi chưa commit đều bị hủy.

### Bài 3 — Một statement lỗi sau một statement thành công

Chạy UPDATE hợp lệ, sau đó INSERT trùng primary key. Kiểm tra dữ liệu trước khi gọi COMMIT/ROLLBACK. Vì sao UPDATE đầu tiên vẫn pending?

### Bài 4 — SAVEPOINT

Chạy UPDATE A, tạo SAVEPOINT, chạy UPDATE B, rồi ROLLBACK TO SAVEPOINT. Xác nhận A còn pending, B bị hủy. Sau đó gọi ROLLBACK toàn phần.

### Bài 5 — Chuyển tiền

Viết PL/SQL block gồm debit, credit và log insert. Kiểm tra SQL%ROWCOUNT sau từng DML. Nếu tài khoản đích không tồn tại, rollback tới savepoint và báo lỗi.

### Bài 6 — JDBC autocommit

Viết hai phiên bản JDBC: một phiên bản autocommit true và một phiên bản setAutoCommit(false). Cố ý làm câu thứ hai thất bại rồi so sánh trạng thái câu thứ nhất.

### Bài 7 — DDL implicit commit

Chạy một DML chưa commit, sau đó thực hiện CREATE TABLE trong schema thử nghiệm. Gọi ROLLBACK và quan sát vì sao DML trước DDL không được hoàn tác.

### Bài 8 — Error logging

Tạo error table bằng DBMS_ERRLOG, nạp một tập có cả hàng hợp lệ và hàng vi phạm constraint bằng LOG ERRORS. So sánh số hàng đích và số hàng lỗi. Thử ROLLBACK để xem cả hai nhóm thay đổi ra sao.

### Bài 9 — Autonomous transaction

Gọi một procedure có PRAGMA AUTONOMOUS_TRANSACTION để ghi audit rồi rollback transaction cha. Quan sát bản ghi audit. Giải thích vì sao không dùng kỹ thuật này cho ledger phải đồng bộ với nghiệp vụ.

### Bài 10 — Phân biệt ACID

Với ví dụ chuyển tiền, mô tả phần nào thuộc atomicity, isolation, consistency và durability. Nêu một race condition mà atomicity đơn thuần không giải quyết.

## 24. Checklist thiết kế ranh giới transaction

Trước khi triển khai một nghiệp vụ nhiều bước, hãy xác định:

- Những câu DML nào phải thành công cùng nhau?
- Câu lệnh nào có thể thất bại và lỗi đó cần hủy phạm vi nào?
- Có điểm nào phù hợp để đặt SAVEPOINT?
- Ai sở hữu transaction: procedure, service layer hay caller?
- JDBC autocommit có đang bật không?
- Có DDL nào vô tình commit transaction không?
- Trigger có autonomous transaction hoặc side effect bên ngoài không?
- Có sequence gap được chấp nhận không?
- Có deferred constraint chỉ kiểm tra tại COMMIT không?
- Batch có chủ ý dùng DML error logging hay SAVE EXCEPTIONS không?
- Mọi DML có kiểm tra số hàng cập nhật khi nghiệp vụ yêu cầu đúng một hàng không?
- Có retry hoặc xử lý giao dịch trùng khi client mất kết nối sau khi server đã commit không?

## 25. Ghi nhớ

| Khái niệm | Quy tắc thực hành |
|---|---|
| Statement atomicity | Một DML thất bại thì Oracle rollback thay đổi của chính DML đó |
| Transaction atomicity | COMMIT hoặc ROLLBACK áp dụng cho toàn bộ transaction hiện tại |
| Implicit statement savepoint | Cơ chế nội bộ Oracle dùng để rollback một câu DML lỗi |
| COMMIT | Xác nhận thay đổi pending và kết thúc transaction |
| ROLLBACK | Hủy mọi thay đổi chưa commit trong transaction |
| SAVEPOINT | Đánh dấu vị trí rollback một phần |
| ROLLBACK TO | Hủy thay đổi sau savepoint, transaction vẫn mở |
| PL/SQL exception | Không tự thay thế chính sách rollback của nghiệp vụ |
| JDBC autocommit | Bật autocommit có thể biến từng câu DML thành transaction riêng |
| DDL | Có implicit commit; không đặt tùy tiện giữa transaction DML |
| LOG ERRORS | Cơ chế chủ động cho phép xử lý lỗi một số hàng và giữ hàng hợp lệ |
| SAVE EXCEPTIONS | Thu thập lỗi trong bulk DML; ứng dụng quyết định transaction |
| Autonomous transaction | Commit độc lập, không bị rollback cùng transaction cha |
| Sequence | NEXTVAL không được trả lại khi rollback |
| External side effect | Email/API/file không tự rollback cùng Oracle transaction |

Tính nguyên tử ở mức câu lệnh bảo vệ một DML khỏi việc để lại thay đổi dở dang khi chính câu lệnh đó thất bại. Tính nguyên tử ở mức giao dịch bảo vệ toàn bộ đơn vị nghiệp vụ gồm nhiều câu lệnh. Khi thiết kế hệ thống, hãy gom các bước bắt buộc vào cùng transaction, dùng savepoint cho các nhánh cần rollback một phần, và để đúng tầng ứng dụng sở hữu quyết định COMMIT. Đồng thời, kiểm tra autocommit, DDL, autonomous transaction và side effect ngoài database vì chúng có thể tạo ranh giới mà người viết SQL không dự đoán.
