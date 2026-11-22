# Kiểm chứng từng mức cô lập bằng lịch thực thi của hai phiên

Mức cô lập transaction quyết định một transaction có thể nhìn thấy thay đổi nào từ transaction khác và những thao tác đọc nào cần khóa. Cách hiểu chắc chắn nhất là theo dõi **lịch thực thi**: câu lệnh nào chạy ở session A, câu lệnh nào chạy ở session B, thời điểm commit hoặc rollback, và kết quả mỗi lần đọc.

Bài học này thuộc phần **MVCC và mức cô lập** của MySQL. Bạn sẽ thực hành bốn mức `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` trên InnoDB; quan sát dirty read, non-repeatable read và phantom read; phân biệt consistent read với locking read; và nhận biết các bất thường như lost update và write skew.

## 1. Chuẩn bị môi trường thực hành

Các ví dụ dùng cú pháp MySQL 8.0 trở lên và storage engine InnoDB. Mở hai kết nối độc lập đến cùng một schema: gọi chúng là **session A** và **session B**. Mỗi session có transaction và cấu hình cô lập riêng.

Tạo hai bảng dành riêng cho bài thực hành. Chạy phần khởi tạo một lần, ngoài mọi transaction đang mở:

```sql
CREATE TABLE isolation_lab_accounts (
    account_id INT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE isolation_lab_orders (
    order_id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    KEY idx_customer_order (customer_id, order_id)
) ENGINE = InnoDB;

INSERT INTO isolation_lab_accounts (account_id, balance)
VALUES (1, 100.00);

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

Hai bảng không có khóa ngoại để các thí nghiệm tập trung vào hành vi đọc và khóa. Trước mỗi lịch thực thi, hãy xác nhận dữ liệu ở trạng thái khởi đầu được ghi trong phần tương ứng. Chỉ chạy các lệnh reset khi cả hai session đã kết thúc transaction trước đó.

Kiểm tra cấu hình của từng session:

```sql
SELECT
    @@SESSION.transaction_isolation AS isolation_level,
    @@SESSION.autocommit AS autocommit_mode;
```

Ghi lại hai giá trị ban đầu để khôi phục sau bài thực hành. Đặt mức cô lập bằng `SET SESSION TRANSACTION ISOLATION LEVEL ...` trước khi bắt đầu transaction. Lệnh này áp dụng cho các transaction tiếp theo trong session, không thay đổi session còn lại hay toàn máy chủ.

## 2. Bốn mức cô lập trong InnoDB

| Mức cô lập | Hành vi của consistent read thông thường | Điều cần quan sát |
| --- | --- | --- |
| `READ UNCOMMITTED` | Có thể đọc phiên bản chưa commit của transaction khác. | Dirty read có thể xảy ra. |
| `READ COMMITTED` | Mỗi câu consistent read tạo một read view mới. | Không đọc dữ liệu chưa commit, nhưng hai lần đọc trong một transaction có thể khác nhau; phantom có thể xuất hiện. |
| `REPEATABLE READ` | Các consistent read trong cùng transaction dùng chung read view. Đây là mặc định phổ biến của InnoDB. | Kết quả consistent read lặp lại ổn định; phantom không xuất hiện trong cùng snapshot. Locking read vẫn đọc dữ liệu hiện tại và có thể dùng next-key lock. |
| `SERIALIZABLE` | Khi `autocommit=0`, InnoDB chuyển câu `SELECT` thông thường thành locking read dùng khóa chia sẻ. | Các transaction xung đột phải chờ hoặc bị phát hiện deadlock để lịch thực thi có thể tuần tự hóa. |

Các mức cô lập chuẩn thường được mô tả bằng dirty read, non-repeatable read và phantom read. Cách InnoDB hiện thực `REPEATABLE READ` có điểm đáng chú ý: consistent read dùng snapshot cố định, còn locking read dùng phiên bản hiện tại và cơ chế khóa. Vì vậy, cần ghi rõ loại câu đọc khi kết luận một hiện tượng có xảy ra hay không.

## 3. READ UNCOMMITTED: đọc được thay đổi chưa commit

**Dirty read** xảy ra khi một transaction nhìn thấy dữ liệu mà transaction ghi vẫn chưa commit. Nếu transaction ghi rollback, dữ liệu mà transaction đọc đã quan sát thực tế chưa từng trở thành dữ liệu đã commit.

Đưa số dư về `100.00` trước khi chạy:

```sql
UPDATE isolation_lab_accounts
SET balance = 100.00
WHERE account_id = 1;
```

**Session A** — đặt mức cô lập và bắt đầu đọc:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Kết quả: 100.00
```

**Session B** — cập nhật nhưng chưa commit:

```sql
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 40.00
WHERE account_id = 1;

-- Chưa COMMIT hoặc ROLLBACK.
```

Quay lại **session A**:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Có thể thấy: 40.00, dù session B chưa commit.
```

Tiếp theo, tại **session B**:

```sql
ROLLBACK;
```

Đọc lại ở **session A**:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Giá trị trở lại: 100.00
```

Session A đã đọc một giá trị tạm thời do B ghi rồi rollback. Đó là dirty read. Kết thúc session A:

```sql
COMMIT;
```

`READ UNCOMMITTED` không phù hợp với nghiệp vụ cần số liệu đã xác nhận, chẳng hạn số dư, tồn kho, trạng thái thanh toán hoặc báo cáo tài chính. Các câu ghi vẫn phải lấy khóa cần thiết; mức này chủ yếu làm thay đổi khả năng nhìn thấy dữ liệu của consistent read.

## 4. READ COMMITTED: mỗi câu đọc có snapshot mới

Ở `READ COMMITTED`, một consistent read chỉ nhìn thấy dữ liệu đã commit trước khi câu đọc bắt đầu. Tuy nhiên, câu `SELECT` tiếp theo trong cùng transaction có thể tạo read view mới và nhìn thấy commit xảy ra giữa hai lần đọc. Đây là điều kiện để **non-repeatable read** xuất hiện.

Đưa số dư về `100.00` trước khi chạy. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Lần đọc thứ nhất: 100.00
```

**Session B** cập nhật và commit:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 75.00
WHERE account_id = 1;

COMMIT;
```

**Session A** đọc lại cùng dòng:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Lần đọc thứ hai: 75.00

COMMIT;
```

Hai câu đọc trong cùng transaction A trả về hai giá trị vì B commit ở giữa. Đây là non-repeatable read. `READ COMMITTED` ngăn dirty read nhưng không giữ cùng snapshot cho toàn transaction.

### Phantom read ở READ COMMITTED

**Phantom read** xảy ra khi cùng một điều kiện truy vấn trả về một tập dòng khác ở lần đọc sau vì transaction khác đã chèn hoặc xóa các dòng thỏa điều kiện và commit.

Đặt lại dữ liệu đơn hàng cho khách hàng 7. Chạy ngoài transaction đang mở:

```sql
DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

**Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Lần đầu: chỉ có order_id = 100.
```

**Session B** chèn một dòng thỏa cùng điều kiện:

```sql
START TRANSACTION;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 30.00);

COMMIT;
```

Quay lại **session A**:

```sql
SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Lần hai: có order_id = 100 và 101.

COMMIT;
```

Dòng `101` là phantom đối với lần đọc thứ hai. Cùng predicate `customer_id = 7`, nhưng read view mới ở `READ COMMITTED` nhìn thấy dòng vừa commit.

## 5. REPEATABLE READ: giữ snapshot cho consistent read

`REPEATABLE READ` là mức cô lập mặc định của InnoDB trong cấu hình MySQL phổ biến. Khi transaction thực hiện consistent read đầu tiên, InnoDB tạo read view. Các consistent read tiếp theo trong transaction đó tiếp tục dùng read view này.

Đặt số dư về `100.00`. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Lần đầu: 100.00. Read view được tạo.
```

**Session B** cập nhật và commit:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 60.00
WHERE account_id = 1;

COMMIT;
```

**Session A** đọc lại bằng consistent read thông thường:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Vẫn thấy: 100.00

COMMIT;
```

InnoDB dùng undo record để dựng lại phiên bản `100.00` phù hợp với read view của A. Phiên bản `60.00` đã commit vẫn chưa thuộc snapshot mà A đang sử dụng. Sau khi A kết thúc transaction, một transaction mới có thể nhìn thấy `60.00`.

### Phantom trong consistent read của REPEATABLE READ

Thử lại lịch chèn đơn hàng ở phần trước nhưng đặt session A ở `REPEATABLE READ`. Trước khi bắt đầu, xóa đơn hàng `101` và bảo đảm chỉ còn dòng `100` cho khách hàng 7:

```sql
DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

**Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Lần đầu: chỉ có order_id = 100. Read view được tạo.
```

**Session B**:

```sql
START TRANSACTION;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 30.00);

COMMIT;
```

**Session A** đọc lại cùng predicate:

```sql
SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Vẫn chỉ thấy order_id = 100 trong read view cũ.

COMMIT;
```

Với consistent read, A không nhìn thấy phantom `101` vì snapshot không đổi. Đây là điểm khác biệt quan trọng giữa `REPEATABLE READ` của InnoDB và cách mô tả tối thiểu của mức `REPEATABLE READ` trong tiêu chuẩn SQL, vốn cho phép phantom read.

### Locking read không dùng snapshot cũ

Không được suy ra rằng mọi câu đọc trong `REPEATABLE READ` đều trả về dữ liệu cũ. `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là locking read (current read): chúng đọc phiên bản hiện tại phù hợp để khóa và phối hợp với thao tác ghi.

Ví dụ ở session A:

```sql
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id
FOR UPDATE;
```

Với index phù hợp, InnoDB có thể dùng record lock và gap/next-key lock cho phạm vi được quét. Một thao tác chèn vào phạm vi đang bị khóa có thể phải chờ đến khi A commit hoặc rollback. Phạm vi khóa thực tế phụ thuộc index được chọn, điều kiện truy vấn và execution plan; hãy dùng `EXPLAIN` và kiểm tra lock khi cần xác minh.

Kết thúc transaction ở session A trước khi chuyển sang thí nghiệm tiếp theo:

```sql
COMMIT;
```

## 6. SERIALIZABLE: phối hợp đọc và ghi bằng khóa

`SERIALIZABLE` yêu cầu lịch thực thi tương đương một thứ tự tuần tự của các transaction. InnoDB đạt điều này bằng cách áp dụng khóa nghiêm ngặt hơn. Một chi tiết dễ bỏ qua là cách xử lý `SELECT` phụ thuộc chế độ autocommit.

Khi `autocommit=0`, InnoDB ngầm chuyển câu `SELECT` thông thường thành locking read dùng khóa chia sẻ (`FOR SHARE`). Để quan sát, cấu hình cả hai session trước khi bắt đầu thí nghiệm:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET SESSION autocommit = 0;
```

Đưa số dư về `100.00` trước khi chạy. **Session A** thực hiện câu đọc:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Đọc 100.00 và giữ khóa chia sẻ trong transaction.
```

Trong **session B**, chạy:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET SESSION autocommit = 0;

UPDATE isolation_lab_accounts
SET balance = 80.00
WHERE account_id = 1;
```

Lệnh `UPDATE` ở B phải chờ vì A đang giữ khóa chia sẻ trên dòng cần cập nhật. Khi B đang chờ, quay lại **session A** và chạy:

```sql
COMMIT;
```

Sau khi A nhả khóa, câu `UPDATE` ở B tiếp tục. Khi lệnh kết thúc, commit ở B:

```sql
COMMIT;
```

Đọc lại kết quả rồi khôi phục chế độ autocommit ở cả hai session:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;

SET SESSION autocommit = 1;
```

Khóa buộc thao tác ghi của B chờ thao tác đọc trong A hoàn tất. Với các truy vấn phạm vi, khóa khoảng (gap/next-key) còn có thể ngăn transaction khác chèn phantom vào phạm vi đang được bảo vệ. SERIALIZABLE có thể làm giảm mức đồng thời, tăng thời gian chờ và khả năng deadlock; ứng dụng phải xử lý lỗi deadlock bằng cách retry transaction phù hợp.

Khi `autocommit=1`, một câu `SELECT` đơn lẻ là transaction đọc riêng và có thể chạy như consistent read không khóa. Vì vậy, muốn kiểm chứng lịch nhiều câu lệnh được bảo vệ bởi khóa chia sẻ như trên, hãy chủ động đặt `autocommit=0` và kết thúc transaction bằng `COMMIT` hoặc `ROLLBACK`.

## 7. Bảng tổng hợp hiện tượng

Bảng sau mô tả các lịch đọc thông thường trong InnoDB. Với `REPEATABLE READ`, kết luận về phantom áp dụng cho consistent read dùng cùng read view; locking read có quy tắc khóa riêng.

| Hiện tượng | READ UNCOMMITTED | READ COMMITTED | REPEATABLE READ (InnoDB) | SERIALIZABLE |
| --- | --- | --- | --- | --- |
| Dirty read | Có thể | Không | Không | Không |
| Non-repeatable read giữa hai consistent read | Có thể | Có thể | Không, cùng snapshot | Không trong lịch tuần tự hóa |
| Phantom giữa hai consistent read cùng điều kiện | Có thể | Có thể | Không, cùng snapshot | Không trong lịch tuần tự hóa |
| Đọc có thể phải chờ khóa ghi | Thường không với plain SELECT | Thường không với plain SELECT | Thường không với plain SELECT | Có, khi autocommit tắt và SELECT được chuyển thành locking read |

Đừng dùng bảng này để kết luận rằng `REPEATABLE READ` và `SERIALIZABLE` giống nhau. `REPEATABLE READ` giữ snapshot cho consistent read nhưng vẫn cho phép một số lịch ghi không thể sắp xếp thành thứ tự tuần tự. `SERIALIZABLE` thêm ràng buộc khóa để ngăn các lịch đó.

## 8. Lost update và write skew: các vấn đề cần kiểm soát thêm

### Lost update do ghi giá trị tính từ dữ liệu cũ

Giả sử số dư ban đầu là `100.00`. A đọc số dư và tính giá trị mới `110.00`; B cũng đọc `100.00` và tính giá trị mới `90.00`. Nếu cả hai sau đó gửi các câu `UPDATE ... SET balance = <giá trị đã tính ở ứng dụng>`, câu ghi chạy sau có thể ghi đè kết quả của câu trước. Việc câu `UPDATE` tự lấy khóa không sửa được giá trị cũ mà ứng dụng đã tính.

Lịch minh họa ở `REPEATABLE READ` (đặt lại số dư về `100.00` trước khi chạy):

**Session A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Ứng dụng đọc 100.00 và tính giá trị mới là 110.00.
```

**Session B**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Ứng dụng cũng đọc 100.00 và tính giá trị mới là 90.00.
```

Cho A ghi và commit trước:

```sql
UPDATE isolation_lab_accounts
SET balance = 110.00
WHERE account_id = 1;

COMMIT;
```

Sau đó B ghi giá trị tuyệt đối đã tính từ lần đọc cũ:

```sql
UPDATE isolation_lab_accounts
SET balance = 90.00
WHERE account_id = 1;

COMMIT;
```

Kết quả cuối là `90.00`; phần cập nhật của A đã bị ghi đè. Đây là lỗi phối hợp read-modify-write ở tầng ứng dụng, không phải dirty read.

Một cách an toàn hơn cho phép cộng/trừ là thực hiện phép tính ngay trong SQL:

```sql
UPDATE isolation_lab_accounts
SET balance = balance + 10.00
WHERE account_id = 1;
```

Hoặc khóa dòng trước khi đọc rồi mới tính:

```sql
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1
FOR UPDATE;

-- Ứng dụng tính toán từ giá trị vừa khóa và cập nhật.
UPDATE isolation_lab_accounts
SET balance = 110.00
WHERE account_id = 1;

COMMIT;
```

Với dữ liệu có thể được sửa bởi nhiều luồng, cũng có thể dùng cột version và câu `UPDATE ... WHERE version = ?` để phát hiện cập nhật dựa trên phiên bản cũ.

### Write skew dưới REPEATABLE READ

Giả sử có hai bác sĩ trực và quy tắc nghiệp vụ yêu cầu luôn có ít nhất một người đang trực. Tạo bảng thực hành:

```sql
CREATE TABLE isolation_lab_doctors (
    doctor_id INT PRIMARY KEY,
    is_on_call BOOLEAN NOT NULL
) ENGINE = InnoDB;

INSERT INTO isolation_lab_doctors (doctor_id, is_on_call)
VALUES (1, TRUE), (2, TRUE);
```

Ở `REPEATABLE READ`, bắt đầu transaction ở cả hai session trước khi đọc. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM isolation_lab_doctors
WHERE is_on_call = TRUE;
-- Kết quả: 2.
```

**Session B**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM isolation_lab_doctors
WHERE is_on_call = TRUE;
-- Kết quả: 2.
```

Sau đó A tắt bác sĩ 1:

```sql
UPDATE isolation_lab_doctors
SET is_on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
```

B tắt bác sĩ 2:

```sql
UPDATE isolation_lab_doctors
SET is_on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
```

Hai transaction cập nhật hai dòng khác nhau nên có thể cùng commit, dù mỗi transaction đã quyết định dựa trên snapshot thấy hai bác sĩ đang trực. Kết quả là không còn ai trực. Đây là write skew: mỗi transaction riêng lẻ tuân theo điều kiện mà nó quan sát, nhưng kết hợp lại vi phạm quy tắc toàn cục.

Để bảo vệ quy tắc này, có thể khóa tập dòng liên quan trước khi kiểm tra:

```sql
START TRANSACTION;

SELECT doctor_id, is_on_call
FROM isolation_lab_doctors
ORDER BY doctor_id
FOR UPDATE;

-- Chỉ tắt một bác sĩ nếu sau thay đổi vẫn còn ít nhất một người trực.
-- Thực hiện UPDATE sau khi đã kiểm tra dữ liệu được khóa.

COMMIT;
```

Transaction thứ hai phải chờ khóa và sau đó kiểm tra trạng thái hiện tại. Một cách khác là thiết kế constraint hoặc dòng khóa đại diện để biến quy tắc liên dòng thành điều kiện có thể đồng bộ hóa. `SERIALIZABLE` cũng có thể ngăn lịch write skew, nhưng cần chấp nhận khả năng chờ và deadlock.

## 9. Cách đọc một lịch thực thi

Khi phân tích một tình huống đồng thời, hãy ghi lại theo thứ tự thời gian:

1. Mức cô lập và `autocommit` của từng session.
2. Thời điểm transaction bắt đầu và câu consistent read đầu tiên tạo snapshot (nếu có).
3. Câu `SELECT` là consistent read hay locking/current read.
4. Transaction nào thay đổi dòng, transaction nào commit hoặc rollback trước mỗi lần đọc.
5. Kết quả thực tế của câu đọc và khóa nào khiến một câu lệnh phải chờ.

Ví dụ ký hiệu `A1`, `B1` là các bước theo thứ tự:

| Thứ tự | Session A | Session B |
| --- | --- | --- |
| 1 | `START TRANSACTION` | |
| 2 | `SELECT balance` → 100 | |
| 3 | | `UPDATE balance = 75` |
| 4 | | `COMMIT` |
| 5 | `SELECT balance` → 75 ở READ COMMITTED; 100 ở REPEATABLE READ | |
| 6 | `COMMIT` | |

Khi so sánh các mức cô lập, giữ nguyên dữ liệu ban đầu và thứ tự câu lệnh; chỉ thay đổi mức cô lập. Nếu thay đổi đồng thời cả truy vấn, index, autocommit và thứ tự commit, kết quả không còn cô lập được nguyên nhân.

## 10. Dọn dữ liệu và kết thúc session

Sau khi hoàn tất các thí nghiệm, bảo đảm không còn transaction mở. Khôi phục dữ liệu mẫu và xóa bảng bác sĩ nếu không cần dùng tiếp:

```sql
UPDATE isolation_lab_accounts
SET balance = 100.00
WHERE account_id = 1;

DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);

DROP TABLE isolation_lab_doctors;
```

Nếu đang ở `autocommit=0`, hãy `COMMIT` hoặc `ROLLBACK` trước khi chạy phần dọn dữ liệu, sau đó khôi phục:

```sql
-- Thay REPEATABLE READ bằng isolation_level đã ghi ở đầu bài,
-- nếu giá trị ban đầu của session khác mức này.
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

-- Khôi phục autocommit_mode đã ghi ở đầu bài; ví dụ thông dụng là 1.
SET SESSION autocommit = 1;
```

Thực hiện khôi phục trên cả session A và B. Nếu ban đầu `autocommit=0`, hãy đặt lại `0` sau khi đã khôi phục mức cô lập. Không đóng kết nối khi vẫn còn transaction chưa kết thúc.

## 11. Bài tập tự kiểm tra

1. Trong lịch `READ UNCOMMITTED`, vì sao session A có thể đọc `40.00` rồi sau đó lại đọc `100.00`?
2. Ở `READ COMMITTED`, điều gì khiến hai câu `SELECT` cùng transaction nhìn thấy hai giá trị khác nhau?
3. Tại sao consistent read trong `REPEATABLE READ` không thấy dòng mới được session B commit sau khi snapshot của A đã được tạo?
4. Phân biệt kết quả của `SELECT` thông thường và `SELECT ... FOR UPDATE` trong một transaction `REPEATABLE READ`.
5. Vì sao phải đặt `autocommit=0` để quan sát plain `SELECT` của `SERIALIZABLE` giữ khóa chia sẻ qua nhiều câu lệnh?
6. Mô tả một lịch write skew và giải thích vì sao hai transaction cập nhật hai dòng khác nhau vẫn có thể vi phạm một quy tắc nghiệp vụ chung.
7. Với một phép cộng số dư, vì sao `SET balance = balance + 10` an toàn hơn việc đọc số dư về ứng dụng rồi gửi lại một giá trị tuyệt đối đã tính từ trước?

Khi kiểm chứng, hãy luôn phân biệt **snapshot mà consistent read nhìn thấy** với **phiên bản hiện tại mà locking read hoặc câu ghi cần xử lý**. Sự phân biệt này giúp giải thích đúng kết quả của từng lịch hai phiên và chọn mức cô lập, khóa cùng chiến lược cập nhật phù hợp cho nghiệp vụ.
