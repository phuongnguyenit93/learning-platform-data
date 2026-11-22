# COMMIT, ROLLBACK và khả năng quan sát dữ liệu giữa các phiên

Trong Oracle Database, một phiên làm việc (*session*) có thể đọc và thay đổi dữ liệu trong khi những phiên khác cũng đang truy cập cùng bảng. Để dữ liệu không bị lộ khi chưa hoàn tất, Oracle quản lý thay đổi theo **transaction**. Các lệnh **COMMIT** và **ROLLBACK** xác định transaction kết thúc theo cách nào; cơ chế **read consistency** quyết định mỗi phiên nhìn thấy phiên bản dữ liệu nào tại thời điểm đọc.

Ba nguyên tắc cần nắm:

- Một session nhìn thấy các thay đổi chưa COMMIT của chính nó.
- Session khác không nhìn thấy thay đổi chưa COMMIT; khi đọc thông thường, nó nhìn thấy phiên bản đã COMMIT phù hợp với snapshot của câu lệnh hoặc transaction.
- COMMIT làm thay đổi của transaction trở nên đã xác nhận và có thể được các lần đọc sau nhìn thấy; ROLLBACK hủy các thay đổi chưa COMMIT của transaction.

Oracle dùng cơ chế **multi-version concurrency control (MVCC)** và dữ liệu UNDO để hỗ trợ đọc nhất quán. Vì vậy, một câu SELECT thông thường thường không phải chờ một transaction khác chỉ vì transaction đó đang cập nhật cùng hàng. Câu SELECT có thể đọc phiên bản đã COMMIT trước đó, trong khi câu UPDATE khác trên cùng hàng có thể phải chờ khóa.

Bài học này giải thích transaction boundary, COMMIT, ROLLBACK, SAVEPOINT, khả năng nhìn thấy dữ liệu giữa hai session, mức cô lập READ COMMITTED và SERIALIZABLE, khóa hàng, DDL implicit commit và cách quản lý transaction qua JDBC/Spring.

## 1. Session và transaction là gì?

**Session** là một kết nối logic của client tới Oracle Database. Ví dụ:
- Một cửa sổ SQL Developer có thể mở một hoặc nhiều connection.
- Một ứng dụng Java có thể mượn connection từ connection pool.
- Hai connection database độc lập thường tương ứng với hai session Oracle khác nhau.

**Transaction** là một đơn vị công việc gồm một hoặc nhiều thao tác thay đổi dữ liệu. Các thao tác DML phổ biến:
- INSERT
- UPDATE
- DELETE
- MERGE
- Một số thao tác PL/SQL thực hiện DML

Một transaction thường bắt đầu khi session thực hiện câu lệnh SQL đầu tiên thuộc transaction hoặc khi thiết lập transaction bằng SET TRANSACTION. Nó kết thúc khi COMMIT hoặc ROLLBACK toàn bộ transaction, hoặc khi có một sự kiện implicit commit theo quy tắc Oracle.

Ví dụ một đơn hàng cần cập nhật tồn kho và ghi nhận đơn:

~~~sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 100;

INSERT INTO orders(order_id, customer_id, status)
VALUES (5001, 200, 'NEW');

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (5001, 100, 2);

COMMIT;
~~~

Ba thay đổi tạo thành một đơn vị công việc. Nếu mọi thao tác thành công, COMMIT xác nhận toàn bộ. Nếu một bước phát hiện lỗi nghiệp vụ trước COMMIT, ROLLBACK có thể hủy toàn bộ thay đổi chưa xác nhận.

Nếu ứng dụng COMMIT sau từng câu lệnh, tính nguyên tử của nghiệp vụ bị phá vỡ: có thể tồn kho đã giảm nhưng đơn hàng chưa được ghi. Ranh giới transaction vì thế phải theo đơn vị nghiệp vụ cần thành công hoặc thất bại cùng nhau.

### 1.1. Một session có thể có nhiều transaction liên tiếp

Sau COMMIT, transaction hiện tại kết thúc. Session vẫn mở và có thể bắt đầu transaction tiếp theo:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

COMMIT;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
~~~

Transaction thứ nhất được xác nhận. Transaction thứ hai bị hủy. ROLLBACK không quay ngược transaction đã COMMIT trước đó.

### 1.2. Một transaction có thể gồm nhiều câu lệnh

~~~sql
INSERT INTO customer(customer_id, full_name)
VALUES (10, 'An');

INSERT INTO customer_address(customer_id, address_text)
VALUES (10, 'District 1');

UPDATE customer_counter
SET total_customers = total_customers + 1;

COMMIT;
~~~

Các câu lệnh thuộc cùng transaction nếu session chưa kết thúc transaction ở giữa. COMMIT xác nhận tất cả thay đổi của transaction đó.

Một câu SELECT thông thường không tự COMMIT các thay đổi DML đang chờ. SELECT đọc dữ liệu theo read consistency và transaction isolation hiện hành.

## 2. COMMIT: xác nhận transaction

Cú pháp cơ bản:

~~~sql
COMMIT;
~~~

COMMIT:
1. Kết thúc transaction hiện tại.
2. Xác nhận các thay đổi DML thuộc transaction.
3. Ghi nhận commit trong redo theo chính sách commit-write của database.
4. Giải phóng các khóa transaction mà session đang giữ.
5. Làm thay đổi đã COMMIT có thể được các câu lệnh đọc sau đó nhìn thấy theo mức cô lập của chúng.

Sau khi COMMIT thành công, ROLLBACK thông thường không thể hủy các thay đổi đó. Muốn sửa dữ liệu đã COMMIT, phải thực hiện một transaction mới để cập nhật ngược hoặc khôi phục từ cơ chế backup/flashback phù hợp.

### 2.1. COMMIT không đóng session

~~~sql
UPDATE products
SET price = price * 1.05
WHERE category_id = 10;

COMMIT;

SELECT product_id, price
FROM products
WHERE category_id = 10;
~~~

Sau COMMIT, session vẫn có thể SELECT, INSERT hoặc UPDATE tiếp. COMMIT kết thúc transaction, không đóng kết nối SQL Developer/JDBC.

### 2.2. COMMIT xác nhận tất cả thay đổi trong transaction

Giả sử session đã chạy:

~~~sql
INSERT INTO orders(order_id, status)
VALUES (9001, 'NEW');

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 50;

COMMIT;
~~~

COMMIT không chỉ xác nhận câu lệnh cuối. Nó xác nhận mọi thay đổi DML chưa COMMIT của transaction. Oracle không có lệnh COMMIT chỉ cho một câu UPDATE trong khi vẫn giữ INSERT trước đó ở trạng thái chưa xác nhận; muốn chia ranh giới, phải kết thúc transaction và bắt đầu transaction mới.

### 2.3. COMMIT và tính bền vững

Oracle ghi thông tin redo để có thể phục hồi thay đổi đã xác nhận khi xảy ra sự cố theo cơ chế recovery. Mặc định, COMMIT thường chờ redo commit record được ghi bền vững theo chính sách WAIT của hệ thống. Một số cấu hình COMMIT WRITE NOWAIT có thể thay đổi thời điểm client nhận xác nhận so với việc redo được flush.

Trong ứng dụng thông thường, hãy coi COMMIT thành công là ranh giới xác nhận transaction. Việc thay đổi chính sách COMMIT WRITE là quyết định vận hành có ảnh hưởng đến độ bền vững và cần DBA đánh giá, không phải thủ thuật tối ưu tùy tiện trong code.

### 2.4. COMMIT giải phóng khóa

DML thường khóa hàng mà transaction thay đổi. Các khóa này được giữ cho đến khi transaction kết thúc. COMMIT giải phóng chúng để transaction khác có thể tiếp tục ghi.

Nếu session A UPDATE một hàng mà chưa COMMIT, session B UPDATE cùng hàng có thể phải chờ. Khi A COMMIT, B có thể tiếp tục theo quy tắc locking và isolation hiện hành.

COMMIT cũng giải phóng các khóa do SELECT FOR UPDATE đã lấy trong transaction.

## 3. ROLLBACK: hủy thay đổi chưa COMMIT

Cú pháp:

~~~sql
ROLLBACK;
~~~

ROLLBACK toàn bộ transaction:
- Hủy các thay đổi DML chưa COMMIT.
- Khôi phục trạng thái dữ liệu logic về điểm bắt đầu transaction gần nhất.
- Kết thúc transaction hiện tại.
- Giải phóng các khóa do transaction giữ.

Ví dụ:

~~~sql
UPDATE products
SET price = 999999
WHERE product_id = 10;

-- Kiểm tra lại giá trị trong chính session.
SELECT product_id, price
FROM products
WHERE product_id = 10;

ROLLBACK;

-- Thay đổi vừa thực hiện đã bị hủy.
SELECT product_id, price
FROM products
WHERE product_id = 10;
~~~

Trước ROLLBACK, session của chính bạn nhìn thấy giá 999999. Sau ROLLBACK, thay đổi đó không còn trong dữ liệu.

### 3.1. ROLLBACK không xóa thay đổi đã COMMIT

~~~sql
UPDATE products
SET price = 100
WHERE product_id = 10;

COMMIT;

UPDATE products
SET price = 200
WHERE product_id = 10;

ROLLBACK;
~~~

Giá cuối cùng là 100. ROLLBACK chỉ hủy UPDATE thứ hai, không đảo ngược UPDATE đã COMMIT.

Nếu muốn đổi giá từ 100 về giá cũ sau khi đã COMMIT, cần biết giá cũ và thực hiện một UPDATE mới; hoặc sử dụng giải pháp khôi phục dữ liệu phù hợp.

### 3.2. ROLLBACK khi câu lệnh gặp lỗi

Một lỗi SQL không nhất thiết tự động hủy toàn bộ transaction. Tùy loại lỗi và ngữ cảnh:
- Câu lệnh lỗi thường bị rollback ở phạm vi câu lệnh đó.
- Những thay đổi thành công trước đó trong cùng transaction có thể vẫn còn.
- Ứng dụng phải quyết định tiếp tục, rollback về savepoint hay rollback toàn transaction.

Ví dụ:

~~~sql
INSERT INTO demo_table(id, value_text)
VALUES (1, 'first');

-- Giả sử ID 1 đã tồn tại và câu INSERT này lỗi unique constraint.
INSERT INTO demo_table(id, value_text)
VALUES (1, 'duplicate');

-- Thay đổi INSERT đầu tiên có thể vẫn đang chờ COMMIT.
ROLLBACK;
~~~

Đừng giả định một lỗi constraint đã tự động rollback mọi thao tác trước đó. Nếu transaction không còn hợp lệ theo logic ứng dụng, hãy chủ động ROLLBACK.

### 3.3. ROLLBACK không đảo ngược mọi loại tác động

ROLLBACK chỉ hoàn tác những thay đổi transactional mà Oracle quản lý trong transaction hiện tại. Một số tác động không được hoàn tác như DML thông thường:

- DDL gây implicit commit.
- Giá trị NEXTVAL của sequence đã cấp không quay lại khi rollback.
- Giao dịch autonomous transaction đã COMMIT độc lập.
- Email, HTTP request, ghi file hoặc tác động hệ thống bên ngoài database.
- Tác động đã COMMIT trong transaction trước.

Khi một nghiệp vụ phối hợp database và hệ thống ngoài, cần thiết kế cơ chế bù trừ/retry/outbox phù hợp thay vì giả định ROLLBACK database sẽ thu hồi tác động bên ngoài.

## 4. SAVEPOINT và ROLLBACK TO

SAVEPOINT đánh dấu một vị trí bên trong transaction để có thể quay lui một phần.

Cú pháp:

~~~sql
SAVEPOINT savepoint_name;
ROLLBACK TO savepoint_name;
~~~

Ví dụ:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

SAVEPOINT before_discount;

UPDATE orders
SET discount_amount = 50000
WHERE order_id = 1001;

-- Nếu bước áp dụng chiết khấu không hợp lệ:
ROLLBACK TO before_discount;

-- Thay đổi trạng thái PROCESSING vẫn còn trong transaction.
COMMIT;
~~~

ROLLBACK TO:
- Hủy những thay đổi sau savepoint được chọn.
- Không kết thúc toàn bộ transaction.
- Giữ lại những thay đổi trước savepoint.
- Cho phép session tiếp tục thực hiện DML và COMMIT/ROLLBACK sau đó.

### 4.1. SAVEPOINT không phải transaction con độc lập

~~~sql
INSERT INTO audit_demo(id, note) VALUES (1, 'before');
SAVEPOINT s1;

INSERT INTO audit_demo(id, note) VALUES (2, 'after');
ROLLBACK TO s1;

COMMIT;
~~~

Sau COMMIT, hàng ID=1 tồn tại, hàng ID=2 bị hủy. SAVEPOINT chỉ đánh dấu vị trí trong cùng transaction, không tạo một transaction riêng có thể COMMIT độc lập.

### 4.2. ROLLBACK TO không kết thúc transaction

~~~sql
SAVEPOINT s1;

UPDATE accounts
SET balance = balance - 10
WHERE account_id = 1;

ROLLBACK TO s1;

UPDATE accounts
SET balance = balance - 20
WHERE account_id = 1;

COMMIT;
~~~

UPDATE đầu bị hủy; UPDATE sau savepoint vẫn được thực hiện và COMMIT. Sau ROLLBACK TO, transaction vẫn mở.

### 4.3. Savepoint cùng tên

Nếu đặt lại SAVEPOINT với cùng tên, vị trí savepoint cũ được thay bằng vị trí mới. Một ROLLBACK TO savepoint cũng loại bỏ những savepoint được tạo sau savepoint mục tiêu. Không dùng tên savepoint như một ID giao dịch toàn cục; phạm vi của nó chỉ nằm trong transaction/session hiện hành.

### 4.4. SAVEPOINT trong xử lý lỗi PL/SQL

Có thể dùng savepoint để hủy phần công việc của một bước:

~~~sql
BEGIN
    SAVEPOINT before_optional_step;

    UPDATE orders
    SET status = 'READY'
    WHERE order_id = 1001;

    -- Các bước tùy chọn tiếp theo có thể phát sinh lỗi.
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_step;
        RAISE;
END;
~~~

Ví dụ minh họa kỹ thuật. Trong PL/SQL thực tế, cần quyết định exception được xử lý hay ném lại, và ai chịu trách nhiệm COMMIT/ROLLBACK transaction ở tầng gọi. Không nuốt lỗi rồi tiếp tục nếu transaction đang ở trạng thái không đáp ứng điều kiện nghiệp vụ.

## 5. Vì sao session khác không nhìn thấy thay đổi chưa COMMIT?

Oracle bảo đảm **không có dirty read** trong các mức cô lập thông thường được hỗ trợ. Một session không đọc dữ liệu chưa COMMIT của transaction khác bằng SELECT thông thường.

Giả sử bảng có hàng:

~~~text
ACCOUNT_ID = 1
BALANCE    = 1000
~~~

Session A:

~~~sql
UPDATE accounts
SET balance = 900
WHERE account_id = 1;
-- Chưa COMMIT.
~~~

Session A nhìn thấy BALANCE = 900 khi SELECT lại hàng đó. Session B chạy:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Session B vẫn nhìn thấy BALANCE = 1000, là phiên bản đã COMMIT trước đó.

Điều này không có nghĩa UPDATE của A chưa xảy ra. A đã thay đổi phiên bản dữ liệu trong transaction của chính mình và giữ khóa ghi; B đọc một phiên bản nhất quán đã COMMIT.

### 5.1. Session nhìn thấy thay đổi của chính nó

Sau UPDATE chưa COMMIT, session A:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

trả 900. Một session thường nhìn thấy các thay đổi do chính transaction của nó tạo ra.

### 5.2. Session khác nhìn thấy phiên bản đã COMMIT trước

Trong lúc A chưa COMMIT, B:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

trả 1000. Oracle có thể dùng UNDO để tái tạo phiên bản trước khi A thay đổi. Đây là nền tảng của consistent read.

### 5.3. Sau COMMIT, câu lệnh đọc mới có thể nhìn thấy thay đổi

Session A:

~~~sql
COMMIT;
~~~

Sau đó session B chạy một SELECT mới trong READ COMMITTED:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

B nhìn thấy 900 vì transaction A đã COMMIT trước khi câu SELECT mới của B bắt đầu.

**Mốc quan trọng là thời điểm snapshot của câu lệnh đọc**, không đơn giản là thời điểm session mở kết nối hoặc thời điểm một hàng được fetch.

### 5.4. Nếu A ROLLBACK thay vì COMMIT

Session A:

~~~sql
UPDATE accounts
SET balance = 800
WHERE account_id = 1;

ROLLBACK;
~~~

Thay đổi 800 bị hủy. Session B tiếp tục nhìn thấy giá trị đã COMMIT trước đó, ví dụ 900 nếu A đã COMMIT 900 ở transaction trước.

Không có thời điểm nào B nhìn thấy giá trị 800 bằng SELECT thông thường khi A chưa COMMIT.

## 6. Hai session thực hành: quan sát COMMIT và ROLLBACK

Có thể mở hai connection độc lập trong SQL Developer hoặc hai cửa sổ SQLcl/SQL*Plus. Đặt tên quy ước:
- **Session A**: thực hiện thay đổi.
- **Session B**: quan sát dữ liệu.

Chạy phần chuẩn bị một lần trong một session:

~~~sql
CREATE TABLE tx_visibility_demo (
    id     NUMBER(6) PRIMARY KEY,
    amount NUMBER(12,2)
);

INSERT INTO tx_visibility_demo(id, amount)
VALUES (1, 100);

COMMIT;
~~~

### 6.1. Bước 1: A UPDATE nhưng chưa COMMIT

Session A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 120
WHERE id = 1;

SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Kết quả ở A là 120. Transaction vẫn mở.

### 6.2. Bước 2: B SELECT khi A chưa COMMIT

Session B:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Kết quả ở B vẫn là 100. B không đọc được 120 vì đó là thay đổi chưa COMMIT của A.

### 6.3. Bước 3: A COMMIT

Session A:

~~~sql
COMMIT;
~~~

Transaction kết thúc và thay đổi 120 được xác nhận.

### 6.4. Bước 4: B chạy SELECT mới

Session B:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Trong READ COMMITTED mặc định, câu SELECT mới bắt đầu sau COMMIT của A sẽ thấy 120.

### 6.5. Bước 5: A UPDATE rồi ROLLBACK

Session A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 150
WHERE id = 1;

ROLLBACK;
~~~

Session A hủy thay đổi 150. Session B chạy SELECT mới:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Kết quả là 120, giá trị đã COMMIT trước đó.

### 6.6. Bảng kết quả quan sát

| Thời điểm | Session A | Session B (SELECT mới) |
| --- | ---: | ---: |
| Ban đầu | 100 | 100 |
| A UPDATE 120, chưa COMMIT | 120 | 100 |
| A COMMIT | 120 | 120 |
| A UPDATE 150, chưa COMMIT | 150 | 120 |
| A ROLLBACK | 120 | 120 |

Bảng này mô tả READ COMMITTED và mỗi hàng trong cột B là một câu SELECT mới được bắt đầu tại thời điểm ghi. Nếu B đang chạy một SELECT từ trước khi A COMMIT, kết quả của câu SELECT đó không đổi giữa chừng; xem phần read consistency tiếp theo.

## 7. Read consistency: một câu SELECT nhìn thấy một snapshot

Oracle cung cấp **statement-level read consistency** ở mức READ COMMITTED. Mỗi câu SQL đọc dữ liệu từ một snapshot nhất quán tại thời điểm bắt đầu câu lệnh (một SCN phù hợp), thay vì đọc phiên bản mới nhất độc lập cho từng hàng.

Điều này quan trọng khi:
- Một truy vấn JOIN nhiều bảng.
- Một truy vấn đọc nhiều block dữ liệu.
- Một câu SELECT chạy lâu trong khi session khác COMMIT.
- Một truy vấn dùng subquery hoặc aggregate trên nhiều hàng.

Oracle cố gắng để toàn bộ một câu SELECT nhìn thấy dữ liệu nhất quán theo cùng mốc đọc, không trộn tùy tiện một số hàng trước COMMIT và một số hàng sau COMMIT.

### 7.1. Câu SELECT đang chạy không đổi snapshot giữa chừng

Giả sử:
1. B bắt đầu một SELECT dài khi giá trị đã COMMIT là 100.
2. Trong lúc B đang chạy, A UPDATE thành 120 và COMMIT.
3. B tiếp tục đọc các block còn lại.

Câu SELECT của B vẫn dựa trên snapshot được xác định khi câu lệnh bắt đầu; nó không tự chuyển sang snapshot mới ở giữa chừng. Tùy thời gian thực thi và dữ liệu UNDO còn sẵn, Oracle tái tạo phiên bản cần thiết để giữ consistent read.

Sau khi câu SELECT của B kết thúc, một SELECT mới trong READ COMMITTED sẽ lấy snapshot mới và nhìn thấy 120.

### 7.2. JOIN nhiều bảng vẫn nhất quán trong một statement

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 5001;
~~~

Nếu một transaction khác đang cập nhật ORDER và CUSTOMER, câu SELECT thông thường vẫn đọc một tập phiên bản nhất quán theo snapshot của statement. Nó không chủ động chờ từng hàng được COMMIT chỉ để lấy giá trị mới nhất.

### 7.3. Subquery và aggregate cũng dùng snapshot của statement

~~~sql
SELECT e.employee_id,
       e.salary,
       (SELECT AVG(salary) FROM employees) AS company_avg
FROM employees e;
~~~

Cả hàng ngoài và subquery aggregate thuộc cùng câu SQL. Oracle bảo đảm read consistency cho statement, nên truy vấn không cố ý lấy hàng ngoài ở một thời điểm và AVG ở một thời điểm khác giữa lúc chạy.

### 7.4. UNDO hỗ trợ đọc phiên bản cũ

Oracle lưu thông tin UNDO để:
- Rollback thay đổi chưa COMMIT.
- Tái tạo phiên bản dữ liệu cũ cho consistent read.
- Hỗ trợ một số hoạt động Flashback.

Khi transaction ghi đè dữ liệu, session đọc có thể cần UNDO để nhìn phiên bản tại SCN của nó. Nếu một truy vấn chạy quá lâu và thông tin UNDO cần thiết không còn sẵn do bị ghi đè, truy vấn có thể gặp ORA-01555: snapshot too old.

UNDO không phải bản backup lâu dài và không bảo đảm mọi phiên bản cũ được giữ vô hạn. Retention, tốc độ DML và thời gian truy vấn ảnh hưởng khả năng tái tạo phiên bản cũ.

## 8. READ COMMITTED: mặc định của Oracle

Oracle Database mặc định dùng mức cô lập **READ COMMITTED**. Đặc điểm:
- Không đọc thay đổi chưa COMMIT của transaction khác.
- Mỗi statement có snapshot riêng.
- Hai câu SELECT liên tiếp trong cùng transaction có thể nhìn thấy hai snapshot khác nhau.
- Một transaction khác COMMIT giữa hai câu SELECT có thể làm câu SELECT thứ hai nhìn thấy dữ liệu mới.
- DML trên cùng hàng có thể phải chờ khóa.

Ví dụ session B:

~~~sql
-- SELECT thứ nhất.
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;

-- Trong lúc đó session A UPDATE và COMMIT.

-- SELECT thứ hai trong cùng session B.
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Trong READ COMMITTED, SELECT thứ hai có thể thấy giá trị mới mà A vừa COMMIT. Transaction B không giữ một snapshot duy nhất cho toàn bộ thời gian sống của transaction.

### 8.1. Non-repeatable read

Một transaction đọc cùng hàng hai lần nhưng nhận giá trị khác nhau vì transaction khác COMMIT ở giữa:

~~~text
B: SELECT amount -> 100
A: UPDATE amount = 120; COMMIT
B: SELECT amount -> 120
~~~

Đây là non-repeatable read ở mức transaction. Mỗi câu SELECT riêng vẫn nhất quán.

### 8.2. Phantom rows

Một câu SELECT thứ nhất trả các hàng thỏa điều kiện; transaction khác INSERT một hàng mới thỏa điều kiện rồi COMMIT; câu SELECT thứ hai có thể trả thêm hàng đó:

~~~text
B: SELECT * FROM orders WHERE status = 'NEW' -> 5 hàng
A: INSERT một đơn NEW; COMMIT
B: SELECT * FROM orders WHERE status = 'NEW' -> 6 hàng
~~~

Mỗi statement vẫn đọc một snapshot nhất quán riêng. READ COMMITTED không cam kết cùng tập hàng cho mọi statement trong một transaction.

### 8.3. READ COMMITTED không có dirty read

Dù có thể thấy thay đổi đã COMMIT giữa hai câu SELECT, session B không thấy giá trị tạm thời mà session A chưa COMMIT. Đây là điểm khác với mức READ UNCOMMITTED trong một số hệ quản trị khác.

Oracle không cung cấp mức READ UNCOMMITTED theo cách cho phép dirty read thông thường. Không dùng thuật ngữ “đọc bẩn” cho việc một SELECT mới thấy giá trị sau COMMIT; đó là đọc dữ liệu đã xác nhận.

## 9. SERIALIZABLE: snapshot ở cấp transaction

Có thể yêu cầu transaction dùng mức cô lập SERIALIZABLE:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Lệnh SET TRANSACTION phải được thực hiện ở đầu transaction, trước các câu lệnh khác của transaction. Ở mức này, các câu đọc trong transaction nhìn một snapshot nhất quán ở cấp transaction, dựa trên thời điểm transaction bắt đầu.

Ví dụ:

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

Giả sử kết quả là 120.

Session B:

~~~sql
UPDATE tx_visibility_demo
SET amount = 130
WHERE id = 1;

COMMIT;
~~~

Session A chạy SELECT lần nữa:

~~~sql
SELECT amount
FROM tx_visibility_demo
WHERE id = 1;
~~~

A vẫn nhìn thấy 120 trong transaction SERIALIZABLE hiện tại, dù B đã COMMIT 130 sau khi transaction A bắt đầu.

### 9.1. SERIALIZABLE không có nghĩa transaction khác bị khóa toàn bộ

SERIALIZABLE cung cấp snapshot transaction-level và kiểm tra xung đột ghi theo quy tắc Oracle. Nó không có nghĩa mọi session khác bị dừng hoặc mọi SELECT đều khóa bảng.

Các transaction khác vẫn có thể đọc và ghi. Nếu transaction hiện tại cố sửa một hàng đã bị transaction khác thay đổi sau thời điểm snapshot của nó, Oracle có thể báo:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Khi gặp lỗi, ứng dụng thường cần ROLLBACK transaction hiện tại rồi thử lại toàn bộ đơn vị công việc theo chính sách retry an toàn.

### 9.2. Ví dụ xung đột ghi

1. A bắt đầu SERIALIZABLE và đọc hàng ID=1 ở giá trị 120.
2. B cập nhật hàng ID=1 thành 130 và COMMIT.
3. A cố UPDATE chính hàng ID=1 trong snapshot cũ.

~~~sql
-- Session A đã bắt đầu SERIALIZABLE.
UPDATE tx_visibility_demo
SET amount = 125
WHERE id = 1;
~~~

Vì hàng đã được transaction khác thay đổi sau khi A bắt đầu, Oracle có thể trả ORA-08177 thay vì cho A ghi đè một cách không thể tuần tự hóa.

Không nên tiếp tục COMMIT phần công việc còn lại như thể transaction không có lỗi. Xử lý lỗi theo transaction boundary: ROLLBACK và retry nếu nghiệp vụ cho phép.

### 9.3. SERIALIZABLE phải được đặt trước câu lệnh transaction

Ví dụ đúng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM orders;

UPDATE orders
SET status = 'CHECKED'
WHERE order_id = 1001;

COMMIT;
~~~

Không đặt SET TRANSACTION sau khi đã chạy SELECT/UPDATE trong transaction. Oracle yêu cầu thiết lập isolation level ở đầu transaction.

### 9.4. Khi nào dùng SERIALIZABLE?

Có thể cân nhắc khi nghiệp vụ cần các lần đọc trong một transaction nhìn cùng snapshot và chấp nhận xử lý xung đột ghi/retry. Tuy nhiên, SERIALIZABLE không tự thay thế mọi chiến lược khóa hoặc kiểm soát nghiệp vụ.

Đánh giá:
- Transaction có dài không?
- Có nhiều session cập nhật cùng tập hàng không?
- Retry toàn transaction có an toàn không?
- Có side effect ngoài database trước khi COMMIT không?
- Có thể dùng khóa tường minh hoặc thiết kế dữ liệu khác đơn giản hơn không?

Không bật SERIALIZABLE toàn hệ thống chỉ để tránh non-repeatable read mà chưa đo tải và phân tích xung đột.

## 10. READ ONLY transaction

Oracle cho phép bắt đầu transaction chỉ đọc:

~~~sql
SET TRANSACTION READ ONLY;
~~~

Các câu SELECT trong transaction READ ONLY nhìn snapshot nhất quán ở cấp transaction. Transaction không được thực hiện INSERT, UPDATE hoặc DELETE.

Ví dụ:

~~~sql
SET TRANSACTION READ ONLY;

SELECT SUM(amount)
FROM orders;

SELECT COUNT(*)
FROM order_items;

COMMIT;
~~~

Hai câu SELECT nhìn cùng snapshot transaction-level. Một session khác có thể COMMIT thay đổi giữa hai câu, nhưng transaction READ ONLY hiện tại vẫn đọc snapshot đã bắt đầu.

READ ONLY phù hợp cho một số báo cáo cần nhiều truy vấn nhất quán trong cùng transaction. Nó không phải cách khóa bảng cho người khác; session khác vẫn có thể ghi theo quy tắc locking bình thường.

Nếu cần kết thúc transaction chỉ đọc mà không có thay đổi, COMMIT kết thúc transaction. ROLLBACK cũng có thể kết thúc transaction đọc, nhưng COMMIT thường diễn đạt rõ hơn mục tiêu kết thúc thành công.

## 11. So sánh các mức đọc và khả năng nhìn thấy dữ liệu

| Đặc điểm | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Mặc định Oracle | Có | Không | Không |
| Dirty read | Không | Không | Không |
| Snapshot | Mỗi statement | Cấp transaction | Cấp transaction |
| SELECT mới sau COMMIT của session khác | Có thể thấy thay đổi mới | Vẫn thấy snapshot transaction cũ | Vẫn thấy snapshot transaction cũ |
| DML trong transaction | Có | Có, nhưng có thể gặp ORA-08177 | Không |
| Có thể gặp xung đột ghi serialization | Theo locking/wait và quy tắc READ COMMITTED | Có thể ORA-08177 | Không có DML của chính transaction |
| Mục đích điển hình | Giao dịch ứng dụng thông thường | Cần snapshot ổn định và kiểm soát xung đột | Báo cáo nhiều câu SELECT nhất quán |

Lưu ý: Bảng mô tả hành vi cốt lõi. Các chi tiết khóa và kết quả DML còn phụ thuộc câu lệnh, hàng bị tranh chấp, constraint và execution plan.

## 12. SELECT thông thường và SELECT FOR UPDATE

Một SELECT thông thường không khóa hàng theo cách ngăn transaction khác UPDATE. Nó đọc snapshot nhất quán.

Nếu ứng dụng cần đọc hàng rồi khóa để cập nhật an toàn, có thể dùng SELECT FOR UPDATE:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Câu lệnh lấy khóa hàng phù hợp cho transaction hiện tại. Transaction khác muốn UPDATE cùng hàng có thể phải chờ cho đến khi khóa được giải phóng.

### 12.1. NOWAIT

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

Nếu hàng đang bị session khác khóa, câu lệnh không chờ mà báo lỗi resource busy, thường là ORA-00054.

### 12.2. WAIT n

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE WAIT 5;
~~~

Câu lệnh chờ tối đa số giây được chỉ định trước khi báo lỗi nếu không lấy được khóa.

### 12.3. SKIP LOCKED

~~~sql
SELECT job_id, status
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua hàng đang bị session khác khóa. Mẫu này hữu ích trong hệ thống nhiều worker cùng lấy công việc từ queue, nhưng phải thiết kế cập nhật trạng thái và commit hợp lý để tránh xử lý trùng hoặc bỏ sót.

### 12.4. SELECT FOR UPDATE vẫn cần COMMIT/ROLLBACK

Khóa lấy bởi SELECT FOR UPDATE được giữ đến khi transaction kết thúc. Nếu ứng dụng đọc hàng, xử lý lâu rồi quên COMMIT/ROLLBACK, session khác có thể bị chặn lâu.

Chỉ khóa những hàng thực sự cần và giữ transaction ngắn. Không thực hiện gọi HTTP, gửi email hoặc chờ người dùng trong lúc đang giữ khóa database nếu có thể tránh.

## 13. Writer và reader: ai chờ ai?

Oracle MVCC giúp SELECT thông thường và DML phối hợp mà không buộc mọi reader phải chờ writer.

| Session A | Session B | Hành vi điển hình |
| --- | --- | --- |
| UPDATE hàng, chưa COMMIT | SELECT hàng | B đọc phiên bản đã COMMIT trước đó |
| UPDATE hàng, chưa COMMIT | UPDATE cùng hàng | B chờ khóa của A |
| UPDATE hàng, chưa COMMIT | SELECT FOR UPDATE cùng hàng | B chờ hoặc NOWAIT/SKIP LOCKED theo cú pháp |
| COMMIT | SELECT mới trong READ COMMITTED | B thấy thay đổi đã COMMIT |
| ROLLBACK | SELECT mới | B thấy dữ liệu đã COMMIT trước transaction A |
| SELECT dài đang chạy | A COMMIT giữa lúc B chạy | B giữ snapshot của statement đã bắt đầu |

### 13.1. Một SELECT không nhất thiết bị chặn bởi UPDATE

Giả sử A cập nhật hàng 1 nhưng chưa commit. B SELECT hàng 1 thường có thể đọc phiên bản cũ từ UNDO. Đây là lợi ích quan trọng của read consistency.

### 13.2. Hai UPDATE cùng hàng có thể chờ nhau

A:

~~~sql
UPDATE tx_visibility_demo
SET amount = 140
WHERE id = 1;
-- Chưa COMMIT.
~~~

B:

~~~sql
UPDATE tx_visibility_demo
SET amount = 160
WHERE id = 1;
~~~

B có thể bị chặn cho đến khi A COMMIT hoặc ROLLBACK. Nếu A COMMIT, B tiếp tục theo trạng thái hàng và điều kiện câu lệnh. Nếu A ROLLBACK, B có thể tiếp tục trên dữ liệu còn lại. Ứng dụng cần timeout và xử lý chờ khóa phù hợp.

### 13.3. Tránh giữ khóa trong lúc xử lý ngoài database

Mẫu không tốt:

~~~text
BEGIN TRANSACTION
  UPDATE inventory
  Gọi dịch vụ thanh toán qua HTTP (mất 20 giây)
  Chờ người dùng xác nhận
  INSERT order
COMMIT
~~~

Trong thời gian chờ, khóa database có thể bị giữ lâu. Cách thiết kế tốt hơn thường là chia nghiệp vụ thành các bước transaction ngắn, dùng trạng thái trung gian, outbox hoặc cơ chế bù trừ để phối hợp hệ thống ngoài.

## 14. DDL và implicit COMMIT

Một điểm đặc biệt của Oracle: các câu DDL như CREATE, ALTER, DROP, TRUNCATE có quy tắc **implicit commit**.

Ví dụ:

~~~sql
INSERT INTO demo_table(id, note)
VALUES (1, 'pending');

CREATE TABLE another_demo(id NUMBER);

ROLLBACK;
~~~

INSERT trước DDL có thể đã được COMMIT ngầm trước khi CREATE TABLE chạy. ROLLBACK sau đó không thể hủy INSERT đã được implicit commit.

Oracle thực hiện implicit commit trước DDL; DDL thành công cũng được commit theo quy tắc DDL. Vì vậy, không trộn DDL vào giữa transaction DML nếu mong muốn rollback toàn bộ.

### 14.1. TRUNCATE không thể rollback như DELETE

~~~sql
TRUNCATE TABLE staging_data;
~~~

TRUNCATE là DDL, có implicit commit và không thể hoàn tác bằng ROLLBACK như DELETE. Nếu cần xóa hàng có thể rollback, dùng DELETE trong transaction phù hợp:

~~~sql
DELETE FROM staging_data;
-- Có thể kiểm tra rồi COMMIT hoặc ROLLBACK.
~~~

DELETE có thể tạo nhiều UNDO/REDO hơn và có hành vi khóa khác; lựa chọn phải dựa trên yêu cầu nghiệp vụ và vận hành.

### 14.2. CREATE TABLE AS SELECT cũng là DDL

~~~sql
CREATE TABLE archive_orders AS
SELECT *
FROM orders
WHERE created_at < DATE '2024-01-01';
~~~

Đây là DDL. Không coi nó là một INSERT thông thường có thể ROLLBACK sau khi câu lệnh thành công.

### 14.3. DDL lỗi và transaction trước đó

Vì Oracle thực hiện implicit commit trước DDL, một transaction DML đang mở có thể đã bị COMMIT ngay cả khi câu DDL sau đó thất bại. Do đó, không chạy thử CREATE/ALTER/DROP giữa một transaction chưa hoàn tất nếu còn cần khả năng ROLLBACK các DML trước đó.

## 15. Sequence và những giá trị không quay lại khi ROLLBACK

Sequence cấp giá trị độc lập với transaction:

~~~sql
INSERT INTO orders(order_id, status)
VALUES (orders_seq.NEXTVAL, 'NEW');

ROLLBACK;
~~~

Hàng INSERT bị hủy nhưng giá trị sequence đã cấp không được trả lại. Lần NEXTVAL tiếp theo sẽ lấy giá trị tiếp theo theo cấu hình sequence.

Vì vậy:
- Có khoảng trống trong ID là bình thường.
- Không dùng sequence để tạo số hóa đơn liên tục tuyệt đối nếu nghiệp vụ yêu cầu không có khoảng trống.
- Cache, instance RAC, restart và rollback đều có thể góp phần tạo gap.
- Không giả định ID tăng liên tục phản ánh số hàng đã COMMIT.

Sequence được thiết kế để cấp giá trị duy nhất/hiệu quả, không phải bộ đếm transaction có thể rollback.

## 16. Autonomous transaction và tác động ngoài transaction cha

Một PL/SQL routine có thể khai báo autonomous transaction. Transaction này độc lập với transaction gọi nó và có thể COMMIT/ROLLBACK riêng.

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit_independent (
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Nếu transaction cha sau đó ROLLBACK, hàng audit đã COMMIT trong autonomous transaction vẫn tồn tại.

Autonomous transaction hữu ích trong một số trường hợp ghi log độc lập, nhưng phải thiết kế cẩn thận:
- Transaction con không nhìn thấy thay đổi chưa COMMIT của transaction cha.
- Tránh khóa tài nguyên mà transaction cha đang giữ vì có thể gây deadlock.
- Audit độc lập có thể ghi nhận một thao tác cuối cùng bị rollback ở transaction cha; nội dung log phải diễn đạt đúng trạng thái.
- Không dùng autonomous transaction để né ranh giới transaction nghiệp vụ.

Tương tự, ROLLBACK database không thu hồi email đã gửi, HTTP request đã hoàn tất hoặc file đã ghi. Các side effect ngoài database cần idempotency, outbox hoặc compensating action.

## 17. Giao dịch trong JDBC

Trong JDBC, một Connection có chế độ auto-commit. Theo JDBC, auto-commit mặc định là true; với Oracle JDBC, ứng dụng có thể thay đổi chế độ để gom nhiều câu lệnh vào một transaction.

### 17.1. Auto-commit bật

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Mặc định auto-commit thường là true.
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE inventory SET quantity = quantity - ? WHERE product_id = ?")) {
        ps.setInt(1, 1);
        ps.setLong(2, 100L);
        ps.executeUpdate();
    }
}
~~~

Khi auto-commit bật, câu lệnh được thực hiện như transaction riêng và JDBC commit khi statement hoàn thành theo quy tắc driver. Hai câu DML riêng lẻ không tự động trở thành một transaction nghiệp vụ chung.

### 17.2. Tắt auto-commit để gom nhiều câu lệnh

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement updateInventory =
                 connection.prepareStatement(
                     "UPDATE inventory " +
                     "SET quantity = quantity - ? " +
                     "WHERE product_id = ?")) {
            updateInventory.setInt(1, 2);
            updateInventory.setLong(2, 100L);
            updateInventory.executeUpdate();
        }

        try (PreparedStatement insertOrder =
                 connection.prepareStatement(
                     "INSERT INTO orders(order_id, customer_id, status) " +
                     "VALUES (?, ?, ?)")) {
            insertOrder.setLong(1, 5001L);
            insertOrder.setLong(2, 200L);
            insertOrder.setString(3, "NEW");
            insertOrder.executeUpdate();
        }

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Hai DML dùng cùng Connection nên thuộc cùng transaction khi auto-commit false. Nếu cả hai thành công, commit. Nếu lỗi, rollback phần thay đổi chưa xác nhận.

Trong code thật, cần xử lý ngoại lệ khi rollback cũng thất bại; có thể thêm rollback exception làm suppressed exception hoặc ghi log phù hợp. Không nuốt lỗi rồi trả thành công cho caller.

### 17.3. Không dựa vào close() để quyết định transaction

Khi Connection có transaction đang mở, đừng dựa vào việc đóng connection để tự commit. Hãy gọi commit hoặc rollback một cách tường minh trước khi trả connection về pool. Hành vi khi close một Connection còn transaction phụ thuộc API/driver/pool; explicit boundary giúp tránh giữ trạng thái ngoài ý muốn.

Với connection pool, Connection mà ứng dụng nhận thường là proxy của một physical connection/session. Sau khi close proxy, physical connection có thể được trả về pool để tái sử dụng. Một transaction chưa kết thúc có thể gây rò rỉ trạng thái và khóa nếu pool/driver không xử lý đúng.

### 17.4. Không bật lại auto-commit giữa transaction một cách tùy tiện

Thay đổi auto-commit trong lúc transaction đang mở có thể kết thúc transaction hiện tại theo hành vi JDBC. Thiết kế rõ ràng:
1. Mượn connection.
2. Đặt auto-commit false.
3. Thực hiện toàn bộ đơn vị công việc.
4. COMMIT hoặc ROLLBACK.
5. Trả connection.

Không bật/tắt auto-commit sau từng câu lệnh nếu muốn nhiều DML nằm trong cùng transaction.

## 18. Spring transaction boundary

Với Spring, có thể quản lý transaction bằng @Transactional:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void createOrder(OrderRequest request) {
        inventoryRepository.decrease(
            request.productId(),
            request.quantity()
        );

        orderRepository.insert(request);
    }
}
~~~

Khi phương thức transactional hoàn tất bình thường, transaction manager commit. Khi exception thuộc chính sách rollback mặc định xảy ra, transaction manager rollback.

### 18.1. Quy tắc rollback mặc định của Spring

Theo mặc định phổ biến của Spring:
- RuntimeException và Error kích hoạt rollback.
- Checked exception không tự động kích hoạt rollback nếu không cấu hình.
- Có thể khai báo rollbackFor để chỉ định loại exception cần rollback.

Ví dụ:

~~~java
@Transactional(rollbackFor = Exception.class)
public void createOrder(OrderRequest request) throws Exception {
    // Thực hiện nhiều thao tác repository.
}
~~~

Cần kiểm tra phiên bản Spring và transaction manager cụ thể. Annotation chỉ có hiệu lực khi lời gọi đi qua proxy/interceptor phù hợp; self-invocation trong cùng object có thể không kích hoạt proxy transaction như mong đợi.

### 18.2. Không COMMIT thủ công trong phương thức được Spring quản lý

Nếu Spring transaction manager sở hữu transaction, hãy để transaction manager quyết định commit/rollback. Không lấy connection bên dưới rồi COMMIT tùy tiện giữa phương thức, vì có thể phá vỡ transaction boundary do framework quản lý.

### 18.3. Transaction database không bao trùm mặc nhiên hệ thống ngoài

Một phương thức @Transactional gọi database rồi gửi email:
- Database có thể rollback.
- Email đã gửi không tự biến mất.

Nếu cần phối hợp chắc chắn, cân nhắc transactional outbox, message relay, idempotency và compensating action. Không coi @Transactional là distributed transaction tự động cho mọi HTTP service.

## 19. Kiểm tra transaction và session

Một số truy vấn hữu ích trong môi trường có quyền phù hợp:

### 19.1. Xác định SID của session hiện tại

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

Mở hai connection và chạy câu này để xác nhận chúng là hai session khác nhau.

### 19.2. Xem transaction ID của session

~~~sql
SELECT DBMS_TRANSACTION.LOCAL_TRANSACTION_ID
FROM dual;
~~~

Kết quả có thể NULL nếu session chưa có transaction cục bộ đang hoạt động. Quyền và cách gọi có thể phụ thuộc môi trường.

### 19.3. Xem session và transaction đang hoạt động

DBA hoặc user có quyền phù hợp có thể truy vấn dynamic performance views như V$SESSION, V$TRANSACTION và V$LOCK. Ví dụ:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.addr = s.taddr;
~~~

Các view này thường cần quyền SELECT_CATALOG_ROLE hoặc quyền truy cập cụ thể do DBA cấp. Không cấp quyền rộng cho tài khoản ứng dụng chỉ để chạy báo cáo thông thường.

### 19.4. Xem khóa đang chờ

DBA có thể kiểm tra V$SESSION.BLOCKING_SESSION, V$LOCK và các view liên quan để tìm session chặn/chờ. Khi chẩn đoán:
- Xác định SID/serial của blocker.
- Xác định SQL đang giữ khóa.
- Kiểm tra transaction đã mở bao lâu.
- Xác định ứng dụng có quên COMMIT/ROLLBACK không.
- Chỉ kết thúc session sau khi hiểu tác động nghiệp vụ.

Không kill session chỉ dựa trên việc thấy nó đang giữ khóa; rollback transaction lớn có thể mất thời gian và ảnh hưởng người dùng.

## 20. Bộ dữ liệu thực hành tổng hợp

Ví dụ sau tạo bảng riêng để quan sát commit, rollback và locking. Chạy trong schema sandbox có quyền CREATE TABLE và DML.

### 20.1. Tạo bảng và dữ liệu ban đầu

~~~sql
CREATE TABLE account_tx_demo (
    account_id NUMBER(6)
        CONSTRAINT pk_account_tx_demo PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_tx_demo
VALUES (1, 'An', 1000);

INSERT INTO account_tx_demo
VALUES (2, 'Binh', 500);

COMMIT;
~~~

### 20.2. Session A thay đổi chưa COMMIT

~~~sql
UPDATE account_tx_demo
SET balance = balance - 100
WHERE account_id = 1;

SELECT account_id, balance
FROM account_tx_demo
WHERE account_id = 1;
~~~

Session A thấy 900.

### 20.3. Session B đọc phiên bản đã COMMIT

~~~sql
SELECT account_id, balance
FROM account_tx_demo
WHERE account_id = 1;
~~~

Session B thấy 1000.

### 20.4. Session A xác nhận

~~~sql
COMMIT;
~~~

Session B chạy SELECT mới sẽ thấy 900 trong READ COMMITTED.

### 20.5. Chuyển tiền trong một transaction

~~~sql
UPDATE account_tx_demo
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_tx_demo
SET balance = balance + 100
WHERE account_id = 2;

-- Kiểm tra cả hai hàng trước khi xác nhận.
SELECT account_id, balance
FROM account_tx_demo
ORDER BY account_id;

COMMIT;
~~~

Hai UPDATE thuộc cùng transaction. Session khác chỉ nhìn thấy cả trạng thái đã COMMIT theo snapshot, không nhìn thấy một nửa transaction chưa xác nhận.

Trong code thực tế, cần kiểm tra số hàng bị ảnh hưởng của từng UPDATE. Nếu tài khoản không tồn tại hoặc số dư không đủ, phải quyết định ROLLBACK thay vì COMMIT một giao dịch không hợp lệ.

### 20.6. Dùng SAVEPOINT cho bước tùy chọn

~~~sql
UPDATE account_tx_demo
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account_tx_demo
SET balance = balance + 50
WHERE account_id = 2;

-- Giả sử bước credit cần hủy:
ROLLBACK TO after_debit;

-- Chọn hủy toàn transaction:
ROLLBACK;
~~~

Câu lệnh đầu cũng bị hủy bởi ROLLBACK cuối. Nếu thay ROLLBACK cuối bằng COMMIT, khoản trừ 50 ở tài khoản 1 sẽ được xác nhận, còn khoản cộng 50 sau savepoint bị hủy. Điều đó có thể tạo mất cân bằng nghiệp vụ, nên savepoint chỉ nên dùng khi quy tắc nghiệp vụ cho phép phần công việc trước savepoint được giữ độc lập.

### 20.7. Dọn bảng sandbox

~~~sql
DROP TABLE account_tx_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL và có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 21. Những nhầm lẫn thường gặp

**UPDATE xong là session khác nhìn thấy ngay.** Không đúng. Thay đổi chỉ có thể được session khác nhìn thấy sau COMMIT và theo snapshot/isolation của câu đọc.

**Session A cũng không nhìn thấy thay đổi của chính nó khi chưa COMMIT.** Không đúng. Session A nhìn thấy thay đổi của transaction hiện tại.

**SELECT thông thường luôn chờ transaction đang UPDATE.** Không đúng. Oracle thường dùng UNDO để trả phiên bản đã COMMIT cho consistent read; SELECT FOR UPDATE là trường hợp khóa rõ ràng.

**COMMIT đóng connection.** Không đúng. COMMIT kết thúc transaction; session vẫn hoạt động.

**ROLLBACK hủy cả những transaction đã COMMIT trước đó.** Không đúng. ROLLBACK chỉ hủy transaction hiện tại chưa xác nhận.

**Một lỗi SQL luôn rollback toàn transaction.** Không đúng. Phạm vi rollback phụ thuộc loại lỗi và ngữ cảnh; các thao tác trước có thể vẫn đang chờ COMMIT.

**SAVEPOINT tạo transaction con.** Không đúng. Nó chỉ đánh dấu vị trí trong cùng transaction.

**ROLLBACK TO savepoint kết thúc transaction.** Không đúng. Transaction tiếp tục hoạt động.

**READ COMMITTED giữ cùng snapshot cho cả transaction.** Không đúng. Mỗi statement có snapshot riêng.

**SERIALIZABLE khóa mọi session khác.** Không đúng. Nó cung cấp snapshot transaction-level và có thể phát hiện xung đột ghi bằng ORA-08177.

**READ ONLY chỉ là một câu SELECT.** Không đúng. SET TRANSACTION READ ONLY xác định chế độ transaction chỉ đọc và snapshot transaction-level cho các statement trong transaction.

**DDL có thể rollback cùng DML trước nó.** Không đúng. DDL gây implicit commit; cần tách DDL khỏi transaction DML cần rollback.

**Sequence NEXTVAL quay lại khi ROLLBACK.** Không đúng. Sequence không transactional; gap là bình thường.

**Rollback database thu hồi email đã gửi.** Không đúng. Side effect ngoài database cần cơ chế bù trừ riêng.

**JDBC close() luôn commit transaction.** Không đúng. Ứng dụng phải gọi commit/rollback tường minh.

**@Transactional tự rollback mọi loại exception.** Không đúng theo mặc định phổ biến của Spring; checked exception cần cấu hình rollbackFor nếu muốn rollback.

## 22. Quy trình xử lý transaction an toàn

Khi thiết kế một nghiệp vụ cập nhật nhiều bảng:

1. Xác định đơn vị nghiệp vụ nào phải thành công/thất bại cùng nhau.
2. Bắt đầu transaction trước các DML liên quan.
3. Kiểm tra số hàng bị ảnh hưởng và các điều kiện nghiệp vụ.
4. Giữ transaction ngắn; tránh gọi dịch vụ ngoài hoặc chờ người dùng khi đang giữ khóa.
5. Dùng SAVEPOINT nếu thực sự cần khả năng hủy một phần mà giữ phần trước đó.
6. COMMIT chỉ sau khi mọi điều kiện thành công.
7. Khi có lỗi, ROLLBACK đúng phạm vi và truyền lỗi cho tầng gọi.
8. Trong READ COMMITTED, nhớ mỗi statement có snapshot riêng.
9. Dùng SERIALIZABLE hoặc READ ONLY chỉ khi cần transaction-level snapshot và hiểu cách xử lý xung đột.
10. Dùng SELECT FOR UPDATE khi cần khóa tường minh; chọn WAIT/NOWAIT/SKIP LOCKED theo yêu cầu.
11. Không chạy DDL giữa transaction DML đang cần rollback.
12. Không giả định sequence hoặc side effect ngoài database có thể rollback.
13. Với JDBC, đặt auto-commit false, gọi commit/rollback tường minh rồi trả connection.
14. Với Spring, để transaction manager sở hữu ranh giới @Transactional.
15. Nếu retry sau ORA-08177 hoặc lỗi tạm thời, retry toàn bộ đơn vị công việc với thao tác idempotent phù hợp.

## 23. Bài tập tự luyện

1. Một session UPDATE số dư nhưng chưa COMMIT. Session khác SELECT cùng hàng sẽ nhìn thấy giá trị nào? Giải thích bằng read consistency.
2. Vì sao session thực hiện UPDATE có thể SELECT và thấy giá trị mới dù chưa COMMIT?
3. Sau COMMIT, session khác đang chạy một SELECT dài có tự chuyển sang giá trị mới giữa chừng không?
4. Phân biệt statement-level snapshot trong READ COMMITTED với transaction-level snapshot trong SERIALIZABLE.
5. Hai câu SELECT trong cùng transaction READ COMMITTED có thể trả kết quả khác nhau không? Tạo kịch bản hai session minh họa.
6. Phantom rows là gì? Mô tả bằng một câu SELECT có WHERE STATUS = 'NEW'.
7. Vì sao Oracle không cần chặn SELECT thông thường khi session khác UPDATE cùng hàng?
8. UNDO có vai trò gì trong rollback và consistent read?
9. Khi nào truy vấn dài có thể gặp ORA-01555?
10. Viết transaction chuyển tiền giữa hai tài khoản sao cho cả hai UPDATE được COMMIT cùng nhau.
11. Nếu bước thứ hai của giao dịch chuyển tiền lỗi, ứng dụng cần làm gì?
12. SAVEPOINT khác COMMIT như thế nào? Vì sao SAVEPOINT không tạo transaction con?
13. Một transaction đã COMMIT rồi mới phát hiện sai dữ liệu. Có thể ROLLBACK transaction cũ không?
14. Mức SERIALIZABLE có thể gặp ORA-08177 trong tình huống nào?
15. Sau ORA-08177, vì sao thường phải ROLLBACK và retry toàn bộ transaction?
16. SET TRANSACTION ISOLATION LEVEL SERIALIZABLE phải được gọi ở thời điểm nào?
17. Khi nào SET TRANSACTION READ ONLY hữu ích cho báo cáo nhiều câu SELECT?
18. So sánh SELECT thông thường và SELECT FOR UPDATE.
19. NOWAIT, WAIT n và SKIP LOCKED giải quyết những nhu cầu nào?
20. Vì sao DDL giữa một transaction DML có thể làm mất khả năng ROLLBACK những thay đổi trước đó?
21. Vì sao TRUNCATE không thể thay thế DELETE nếu cần rollback?
22. Tại sao sequence có thể tạo khoảng trống dù transaction INSERT đã rollback?
23. Một autonomous transaction ghi audit rồi COMMIT. Transaction cha ROLLBACK thì audit có còn không?
24. JDBC autoCommit true khác false ở ranh giới transaction thế nào?
25. Vì sao không nên dựa vào close Connection để commit?
26. Spring @Transactional mặc định xử lý RuntimeException và checked exception khác nhau thế nào?
27. Database transaction rollback có thu hồi được email hoặc HTTP request đã gửi không?
28. Thiết kế một bài test hai session chứng minh B chỉ thấy dữ liệu đã COMMIT của A.
29. Thiết kế một bài test chứng minh SELECT đang chạy giữ snapshot của statement dù A COMMIT giữa lúc B đọc.
30. Khi ứng dụng gặp khóa chờ lâu, cần kiểm tra thông tin session/transaction nào trước khi kết thúc session blocker?

**COMMIT xác nhận transaction và làm thay đổi có thể được các lần đọc sau nhìn thấy; ROLLBACK hủy thay đổi chưa xác nhận.** Oracle dùng MVCC và UNDO để một SELECT thông thường đọc phiên bản nhất quán mà không phải đọc dữ liệu chưa COMMIT của session khác. READ COMMITTED tạo snapshot cho từng statement, còn SERIALIZABLE và READ ONLY giữ snapshot ở cấp transaction. Hiểu rõ các mốc này giúp thiết kế transaction ngắn, xử lý khóa đúng cách và tránh nhầm lẫn khi nhiều session cùng làm việc trên một dữ liệu.
