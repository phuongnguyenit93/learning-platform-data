# REPEATABLE READ và ảnh chụp nhất quán trong giao dịch

InnoDB dùng MVCC (Multi-Version Concurrency Control) để cho phép giao dịch đọc một phiên bản dữ liệu nhất quán trong khi giao dịch khác vẫn có thể cập nhật hàng. Ở mức cô lập REPEATABLE READ, các consistent read không khóa trong cùng một giao dịch thường cùng nhìn vào một ảnh chụp dữ liệu (read view). Vì vậy, một truy vấn đọc lặp lại không bất ngờ thấy các thay đổi đã được giao dịch khác commit sau khi ảnh chụp được tạo.

Để dùng đúng REPEATABLE READ, cần phân biệt ba khái niệm:

- **Consistent read**: phép đọc không khóa, sử dụng read view của MVCC để đọc phiên bản hàng phù hợp với ảnh chụp.
- **Current read**: phép đọc phiên bản hiện hành của hàng, thường đi cùng cơ chế khóa để UPDATE, DELETE hoặc SELECT ... FOR UPDATE/ FOR SHARE.
- **Transaction snapshot**: ranh giới thời gian xác định những phiên bản đã commit nào được nhìn thấy bởi các consistent read trong giao dịch.

Bài viết tập trung vào hành vi của InnoDB trong MySQL 8.0 trở lên, cách tạo và tái sử dụng read view, sự khác nhau giữa consistent read và locking read, phantom, undo version và các cách kiểm tra hành vi bằng hai phiên giao dịch.

## 1. Chuẩn bị dữ liệu minh họa

Ta dùng bảng tài khoản có số dư:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (account_id),
    KEY idx_accounts_balance (balance)
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Binh',  500.00),
    (3, 'Chi',   250.00);
~~~

Mỗi tài khoản được định danh bởi account_id. Các ví dụ giả định hai kết nối MySQL độc lập, gọi là Session A và Session B. Hãy mở hai cửa sổ SQL hoặc hai kết nối riêng để quan sát thứ tự commit và đọc dữ liệu.

Kiểm tra mức cô lập hiện tại:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

Trong MySQL 8.0, mặc định của InnoDB là REPEATABLE READ, trừ khi cấu hình máy chủ hoặc session đã thay đổi.

## 2. MVCC tạo ảnh chụp nhất quán như thế nào?

MVCC cho phép InnoDB giữ nhiều phiên bản logic của cùng một hàng trong thời gian cần thiết. Khi giao dịch cập nhật hàng, InnoDB ghi thông tin undo để có thể khôi phục phiên bản cũ. Một consistent read có thể đi theo chuỗi phiên bản này để tìm phiên bản phù hợp với read view của giao dịch.

Ở mức khái niệm:

1. Mỗi thay đổi hàng được gắn với giao dịch thực hiện thay đổi.
2. Undo log giữ thông tin cần thiết để dựng lại phiên bản trước.
3. Read view ghi nhận trạng thái các giao dịch tại thời điểm tạo ảnh chụp.
4. Khi đọc, InnoDB xác định phiên bản nào nhìn thấy được theo read view.
5. Nếu phiên bản hiện tại chưa nhìn thấy được, InnoDB có thể lần theo undo record để tìm phiên bản cũ phù hợp.

Trong clustered index record của InnoDB có các thông tin hệ thống phục vụ MVCC, gồm transaction ID và rollback pointer. Rollback pointer liên kết đến thông tin undo để dựng phiên bản trước của hàng.

### 2.1. Phiên bản nào được nhìn thấy?

Một consistent read trong giao dịch thường nhìn thấy:

- Những thay đổi của giao dịch khác đã commit trước thời điểm read view được tạo.
- Những thay đổi mà chính giao dịch hiện tại đã thực hiện trước đó.

Nó không nhìn thấy:

- Thay đổi chưa commit của giao dịch khác tại thời điểm tạo read view.
- Thay đổi của giao dịch khác commit sau khi read view đã được tạo.

Quy tắc đọc thay đổi của chính giao dịch là ngoại lệ quan trọng: giao dịch luôn nhìn thấy các ghi của mình. Vì vậy, kết quả một truy vấn có thể kết hợp phiên bản snapshot của các hàng khác với thay đổi mới do chính giao dịch đó thực hiện.

### 2.2. MVCC giảm xung đột đọc và ghi

Một SELECT thông thường ở InnoDB là consistent read và không đặt khóa chia sẻ lên từng hàng chỉ để đọc. Nếu giao dịch B cập nhật một hàng trong khi giao dịch A đang đọc snapshot cũ, A vẫn có thể đọc phiên bản cũ qua undo; B có thể tiếp tục ghi và commit khi không vướng khóa khác.

Điều này giúp reader và writer ít chặn nhau hơn. MVCC không loại bỏ mọi khóa: UPDATE, DELETE, SELECT ... FOR UPDATE và SELECT ... FOR SHARE vẫn dùng cơ chế khóa phù hợp với thao tác.

## 3. Khi nào REPEATABLE READ tạo read view?

Một điểm dễ nhầm là START TRANSACTION không nhất thiết tạo read view ngay lập tức.

Với REPEATABLE READ:

- Nếu bắt đầu bằng START TRANSACTION thông thường, read view cho consistent read thường được tạo ở lần consistent read đầu tiên của giao dịch.
- Các consistent read tiếp theo trong cùng giao dịch tái sử dụng read view đó.
- Nếu dùng START TRANSACTION WITH CONSISTENT SNAPSHOT, InnoDB tạo consistent snapshot ngay khi bắt đầu giao dịch ở mức REPEATABLE READ.

Do đó, thời điểm đọc đầu tiên có ý nghĩa. Một giao dịch có thể đã chạy một số lệnh trước khi read view được tạo; các lệnh đó không tự động xác định snapshot cho consistent read nếu chúng không phải consistent read.

Ví dụ:

~~~sql
START TRANSACTION;

-- Chưa có consistent read nào ở đây.
UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- Consistent read đầu tiên tạo read view tại đây.
SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

UPDATE là thao tác ghi dùng cơ chế đọc/khóa phiên bản hiện hành để cập nhật. SELECT thông thường sau đó là consistent read đầu tiên; nó tạo read view khi chạy. Giao dịch cũng nhìn thấy thay đổi balance mà chính nó vừa thực hiện.

Nếu muốn ảnh chụp được tạo ngay tại lúc bắt đầu:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

WITH CONSISTENT SNAPSHOT chỉ có tác dụng ở REPEATABLE READ. Ở mức cô lập khác, MySQL bỏ qua tùy chọn này và có thể phát cảnh báo; hãy đặt isolation level trước khi bắt đầu giao dịch.

## 4. Ví dụ hai giao dịch: đọc lặp lại cùng một ảnh chụp

Giả sử account 1 có balance = 1000.00. Thực hiện các bước sau theo đúng thứ tự.

**Session A**

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Kết quả là 1000.00. Đây là consistent read đầu tiên, nên read view của Session A được tạo tại đây.

**Session B**

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE accounts
SET balance = 1200.00
WHERE account_id = 1;

COMMIT;
~~~

Session B đã commit balance mới là 1200.00.

**Quay lại Session A**

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Kết quả vẫn là 1000.00. Session A tái sử dụng read view được tạo ở lần SELECT đầu tiên, vì vậy không nhìn thấy commit mới của Session B.

Kết thúc Session A:

~~~sql
COMMIT;
~~~

Sau khi commit, một SELECT mới trong giao dịch tiếp theo sẽ dùng snapshot mới và có thể nhìn thấy 1200.00.

| Thời điểm | Session A | Session B | Giá trị A nhìn thấy |
|---|---|---|---:|
| T0 | Bắt đầu và SELECT lần đầu | Chưa cập nhật | 1000.00 |
| T1 | Giữ giao dịch mở | UPDATE thành 1200 và COMMIT | 1000.00 |
| T2 | SELECT lần hai | Đã commit | 1000.00 |
| T3 | COMMIT | Đã commit | Giao dịch A kết thúc |
| T4 | SELECT trong giao dịch mới | Đã commit | 1200.00 |

Đây là hành vi repeatable read của consistent reads: cùng một giao dịch, cùng một snapshot, cùng một hàng thì giá trị được đọc lặp lại ổn định, ngoại trừ thay đổi do chính giao dịch đó thực hiện.

## 5. START TRANSACTION không đồng nghĩa snapshot đã được tạo

So sánh hai tình huống:

**Tình huống 1: snapshot được tạo ở lần SELECT đầu**

~~~sql
START TRANSACTION;
-- Session khác có thể commit thay đổi tại đây.
SELECT balance FROM accounts WHERE account_id = 1;
~~~

Nếu Session B commit trước SELECT đầu tiên, Session A có thể nhìn thấy giá trị mới vì read view chỉ được tạo khi SELECT chạy.

**Tình huống 2: snapshot được tạo ngay khi bắt đầu**

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
SELECT balance FROM accounts WHERE account_id = 1;
~~~

Nếu Session B commit sau khi Session A tạo consistent snapshot, SELECT của Session A vẫn đọc phiên bản thuộc snapshot cũ.

Khác biệt này quan trọng với báo cáo cần nhiều truy vấn đọc cùng một mốc dữ liệu. Nếu chỉ gọi START TRANSACTION rồi thực hiện công việc khác trước SELECT đầu tiên, mốc snapshot không nhất thiết là thời điểm START TRANSACTION.

## 6. Consistent read và current read không giống nhau

Đây là khác biệt quan trọng nhất khi làm việc với REPEATABLE READ.

| Đặc điểm | Consistent read | Current/locking read |
|---|---|---|
| Ví dụ | SELECT thông thường | SELECT ... FOR UPDATE, SELECT ... FOR SHARE |
| Phiên bản | Theo read view | Phiên bản hiện hành mà thao tác khóa cần đọc |
| Đặt khóa hàng để đọc | Không đặt khóa hàng chỉ vì đọc | Có khóa theo chế độ yêu cầu |
| Dùng snapshot cũ | Có | Không theo cách consistent read |
| Mục tiêu | Đọc nhất quán, ít chặn writer | Đọc để kiểm tra rồi khóa hoặc thay đổi an toàn |

SELECT thông thường:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

SELECT khóa hàng để cập nhật:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

SELECT ... FOR UPDATE là current read. Nó đọc phiên bản hiện hành và đặt khóa độc quyền phù hợp trên hàng được tìm thấy, để giao dịch có thể kiểm tra rồi cập nhật mà không bị giao dịch khác sửa hàng đó trước khi hoàn tất.

SELECT ... FOR SHARE (hoặc cú pháp cũ LOCK IN SHARE MODE) là locking read dùng khóa chia sẻ. Giao dịch khác có thể đọc tương thích nhưng không thể sửa hàng cho đến khi khóa được giải phóng.

### 6.1. Cùng một giao dịch có thể thấy hai giá trị khác nhau

Tiếp tục ví dụ Session A đã tạo read view khi balance là 1000. Session B cập nhật balance thành 1200 và commit.

Trong Session A:

~~~sql
-- Consistent read: snapshot cũ
SELECT balance
FROM accounts
WHERE account_id = 1;

-- Current read: phiên bản hiện hành
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

SELECT đầu có thể trả 1000.00, còn SELECT ... FOR UPDATE trả 1200.00. Điều này không mâu thuẫn: hai câu lệnh dùng hai cơ chế đọc khác nhau.

Locking read không thay thế read view cũ của giao dịch. Nếu sau đó chạy SELECT thông thường mà giao dịch chưa tự thay đổi hàng, consistent read vẫn có thể trả giá trị snapshot cũ.

Vì vậy, không nên trộn consistent read và current read trong cùng một phép kiểm tra nghiệp vụ mà không hiểu rõ sự khác nhau. Nếu quyết định cập nhật phụ thuộc vào giá trị hiện hành, hãy dùng locking read hoặc một câu UPDATE có điều kiện nguyên tử.

## 7. UPDATE và DELETE không phải consistent read thông thường

Các câu lệnh thay đổi dữ liệu phải xác định phiên bản hàng hiện hành để khóa và sửa. Chúng không dùng snapshot cũ theo cách SELECT thông thường.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;
~~~

Điều kiện và phép cập nhật được thực hiện theo cơ chế khóa/đọc hiện hành của InnoDB. Đây thường là cách tốt hơn việc SELECT balance bằng consistent read cũ, tính toán trong ứng dụng rồi UPDATE một giá trị tuyệt đối có thể ghi đè thay đổi của giao dịch khác.

Với nghiệp vụ chuyển tiền, cần cập nhật cả hai tài khoản trong cùng một transaction và kiểm tra số dư:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

-- Ứng dụng phải kiểm tra số hàng bị ảnh hưởng.
-- Nếu không có hàng nào được cập nhật, ROLLBACK.

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

COMMIT;
~~~

Đây là khung minh họa, ứng dụng phải kiểm tra kết quả từng UPDATE và rollback nếu bất kỳ điều kiện nào thất bại. Với hệ thống thực tế, cần thêm mã giao dịch, ràng buộc nghiệp vụ, xử lý lỗi và thứ tự khóa nhất quán.

## 8. REPEATABLE READ và phantom rows

Phantom là tình huống một truy vấn theo điều kiện phạm vi được chạy lại và xuất hiện thêm hoặc mất đi các hàng thỏa điều kiện do giao dịch khác thay đổi dữ liệu.

Với consistent read trong cùng một transaction REPEATABLE READ, read view không đổi. Vì vậy, hàng mới được giao dịch khác insert và commit sau khi snapshot được tạo sẽ không xuất hiện khi chạy lại cùng truy vấn snapshot.

Ví dụ Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
ORDER BY account_id;
~~~

Session B:

~~~sql
START TRANSACTION;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES (4, 'Dung', 700.00);

COMMIT;
~~~

Session A chạy lại SELECT thông thường:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
ORDER BY account_id;
~~~

Session A vẫn không thấy account 4 vì hàng đó không thuộc read view đã tạo trước khi Session B commit. Session A kết thúc transaction bằng COMMIT hoặc ROLLBACK.

Đây là cách consistent snapshot tránh phantom đối với các consistent reads. Không cần khóa khoảng để giữ kết quả đọc snapshot ổn định.

### 8.1. Locking range read dùng next-key lock

Nếu mục tiêu là ngăn giao dịch khác chèn hàng mới vào phạm vi đang kiểm tra, hãy dùng locking read trên điều kiện phạm vi:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE balance >= 400.00
FOR UPDATE;
~~~

InnoDB có thể đặt next-key lock trên các bản ghi index và khoảng khóa liên quan đến phạm vi được quét. Next-key lock kết hợp khóa record với khóa gap, nhờ đó có thể ngăn insert vào gap thuộc phạm vi đang bị khóa.

Trong lúc Session A vẫn giữ transaction và khóa phạm vi, Session B thử chèn một tài khoản có balance thuộc phạm vi đó:

~~~sql
INSERT INTO accounts (account_id, owner_name, balance)
VALUES (5, 'Em', 650.00);
~~~

Nếu kế hoạch của Session A quét và khóa các khoảng tương ứng trên idx_accounts_balance, INSERT của Session B có thể phải chờ đến khi Session A COMMIT hoặc ROLLBACK.

Khả năng khóa cụ thể phụ thuộc index được dùng và access path. Điều kiện tìm kiếm không có index phù hợp có thể khiến InnoDB phải quét và khóa nhiều bản ghi hơn dự kiến. Locking range read vì thế có thể làm giảm concurrency và gây lock wait hoặc deadlock.

Phân biệt:

- Consistent read dùng snapshot để giữ kết quả đọc ổn định, không khóa hàng chỉ vì đọc.
- Locking range read dùng khóa record/gap/next-key để ngăn thay đổi xung đột trong phạm vi cần bảo vệ.

## 9. REPEATABLE READ so với READ COMMITTED

Hai mức cô lập thường được so sánh khi thiết kế ứng dụng:

| Hành vi | READ COMMITTED | REPEATABLE READ |
|---|---|---|
| Dirty read | Không | Không |
| Snapshot của consistent read | Snapshot mới cho mỗi câu SELECT nhất quán | Snapshot được tái sử dụng trong transaction sau lần consistent read đầu |
| Đọc lặp cùng hàng | Có thể thấy commit mới ở câu SELECT sau | Thường giữ cùng phiên bản snapshot |
| Phantom trong consistent read | Có thể thấy hàng mới ở câu SELECT sau | Không thấy hàng commit sau snapshot trong cùng read view |
| Gap locking | Thường tắt, trừ một số kiểm tra ràng buộc | Được dùng cho nhiều locking range scan |

Ví dụ ở READ COMMITTED:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;

-- Session khác cập nhật và COMMIT.

SELECT balance
FROM accounts
WHERE account_id = 1;

COMMIT;
~~~

Hai SELECT thông thường có thể trả hai giá trị khác nhau vì mỗi consistent read lấy snapshot mới. Ở REPEATABLE READ, hai SELECT trong cùng transaction thường đọc cùng read view.

READ COMMITTED vẫn ngăn dirty read. Nó chỉ cho phép một transaction nhìn thấy các thay đổi đã commit mới hơn giữa các câu SELECT.

## 10. REPEATABLE READ không đồng nghĩa SERIALIZABLE

REPEATABLE READ của InnoDB cung cấp consistent snapshot cho các consistent reads và dùng khóa để bảo vệ các thao tác ghi/locking read. Tuy vậy, không nên xem nó như mức SERIALIZABLE trong mọi tình huống.

Một vấn đề cần lưu ý là write skew: hai giao dịch cùng đọc một snapshot nhất quán, mỗi giao dịch cập nhật một hàng khác nhau, và cả hai có thể commit dù tổng thể làm vi phạm một quy tắc nghiệp vụ liên quan nhiều hàng.

Ví dụ bảng phân công trực:

~~~sql
CREATE TABLE on_call_staff (
    staff_id BIGINT UNSIGNED NOT NULL,
    on_call BOOLEAN NOT NULL,
    PRIMARY KEY (staff_id)
) ENGINE = InnoDB;

INSERT INTO on_call_staff (staff_id, on_call)
VALUES (1, TRUE), (2, TRUE);
~~~

Quy tắc nghiệp vụ: luôn phải có ít nhất một người trực. Có thể xảy ra lịch thao tác sau.

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT COUNT(*) FROM on_call_staff WHERE on_call = TRUE;
-- Trả về 2.
~~~

Session B:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT COUNT(*) FROM on_call_staff WHERE on_call = TRUE;
-- Cũng trả về 2 trong snapshot của B.
~~~

Sau đó Session A tắt người 1 và commit:

~~~sql
UPDATE on_call_staff SET on_call = FALSE WHERE staff_id = 1;
COMMIT;
~~~

Session B tắt người 2 và commit:

~~~sql
UPDATE on_call_staff SET on_call = FALSE WHERE staff_id = 2;
COMMIT;
~~~

Vì hai transaction cập nhật hai hàng khác nhau, không nhất thiết có xung đột ghi trực tiếp; cả hai có thể commit và kết quả cuối là không còn ai trực.

Khi bảo vệ invariant nhiều hàng, có thể:

- Khóa một hàng điều phối chung trước khi đọc và cập nhật.
- Dùng SELECT ... FOR UPDATE trên tập hàng phù hợp và kiểm tra lại sau khi lấy khóa.
- Thiết kế ràng buộc dữ liệu hoặc mô hình cập nhật để xung đột được phát hiện.
- Dùng SERIALIZABLE nếu ngữ nghĩa và chi phí khóa phù hợp.

Không nên dựa vào một SELECT snapshot thông thường để bảo vệ điều kiện mà nhiều giao dịch có thể đồng thời thay đổi.

## 11. Undo log, purge và giao dịch đọc quá lâu

MVCC cần giữ phiên bản cũ trong undo log khi vẫn có transaction có thể cần đọc chúng. InnoDB chỉ có thể purge những phiên bản không còn cần thiết cho bất kỳ read view đang hoạt động nào.

Một transaction mở lâu, dù chỉ đọc, có thể giữ read view cũ và ngăn purge loại bỏ các phiên bản cũ hơn mốc đó.

Hậu quả có thể gồm:

- History list length tăng.
- Undo tablespace và dữ liệu phiên bản cũ chiếm thêm dung lượng.
- Purge không theo kịp lượng thay đổi.
- Một số truy vấn và thao tác bảo trì chịu thêm chi phí.
- Áp lực I/O và thời gian phục hồi có thể tăng khi lượng undo tồn đọng lớn.

Ví dụ transaction báo cáo mở nhiều giờ:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*)
FROM accounts;

-- Ứng dụng xử lý hoặc chờ rất lâu trước khi kết thúc.

COMMIT;
~~~

Trong khoảng chờ, các giao dịch khác vẫn có thể cập nhật dữ liệu. Tuy nhiên, read view cũ của báo cáo có thể buộc InnoDB giữ những phiên bản mà báo cáo còn có khả năng cần đọc.

Thực hành tốt:

- Giữ transaction ngắn nhất có thể.
- Không mở transaction trước khi người dùng thao tác hoặc chờ nhập liệu.
- Đọc theo lô có thiết kế snapshot rõ ràng nếu báo cáo rất lớn.
- Đảm bảo ứng dụng luôn COMMIT hoặc ROLLBACK kể cả khi lỗi.
- Theo dõi transaction lâu và history list length.

## 12. Theo dõi transaction đang mở

Có thể xem transaction InnoDB đang hoạt động:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Các cột hữu ích:

- trx_started: thời điểm transaction bắt đầu.
- trx_state: trạng thái transaction.
- trx_mysql_thread_id: connection ID tương ứng.
- trx_rows_locked: số hàng đang khóa theo thống kê của InnoDB.
- trx_rows_modified: số hàng transaction đã thay đổi.
- trx_query: câu lệnh hiện tại nếu có.

Để xem thông tin tổng thể về InnoDB, bao gồm History list length:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

History list length là chỉ báo độ dài history list và lượng undo history còn chờ purge xử lý theo cách InnoDB báo cáo. Không nên đồng nhất con số này với số hàng đang tồn tại hoặc xem một giá trị riêng lẻ là kết luận chắc chắn về sự cố; hãy đặt nó trong ngữ cảnh tốc độ ghi, thời gian transaction và khả năng purge.

## 13. Cấu hình isolation level đúng phạm vi

Kiểm tra isolation level của session:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

Đặt mức cô lập cho các transaction tiếp theo trong session:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
~~~

Đặt mức cô lập chỉ cho transaction kế tiếp:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
~~~

Lệnh SET TRANSACTION không có SESSION hoặc GLOBAL áp dụng cho transaction kế tiếp của session hiện tại. Cần đặt trước START TRANSACTION.

Trong ứng dụng dùng connection pool, mỗi connection có session state riêng. Nếu ứng dụng thay đổi isolation level theo yêu cầu, cần khôi phục hoặc thiết lập rõ ràng khi connection được tái sử dụng; nếu không, request sau có thể nhận session với mức cô lập ngoài dự kiến.

Không thay đổi GLOBAL isolation level chỉ để sửa một truy vấn hoặc một luồng nghiệp vụ. Thay đổi global ảnh hưởng các session mới và cần được quản trị có chủ đích.

## 14. Các mẫu giao dịch thực tế

### 14.1. Báo cáo cần một ảnh chụp thống nhất

Một báo cáo đọc nhiều bảng cần số liệu nhất quán tại cùng một mốc:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS account_count
FROM accounts;

SELECT SUM(balance) AS total_balance
FROM accounts;

COMMIT;
~~~

Hai SELECT dùng cùng consistent snapshot. READ ONLY mô tả transaction không dự định ghi dữ liệu; nó giúp làm rõ mục đích của giao dịch.

Nếu báo cáo cần đọc nhiều bảng, các SELECT thông thường trong cùng transaction cũng nhìn theo cùng read view. Hãy tránh dùng locking read trừ khi thực sự cần khóa dữ liệu.

### 14.2. Đọc rồi cập nhật một hàng theo giá trị mới nhất

Nếu quyết định phụ thuộc vào số dư hiện hành, dùng locking read:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Ứng dụng kiểm tra balance và quyết định số tiền cần trừ.

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

COMMIT;
~~~

FOR UPDATE lấy current read và giữ khóa đến khi transaction kết thúc. Giao dịch khác muốn sửa cùng hàng phải chờ hoặc có thể gặp deadlock tùy thứ tự khóa.

### 14.3. Dùng UPDATE có điều kiện thay cho read-modify-write ở ứng dụng

Nếu quy tắc đơn giản, có thể gộp kiểm tra và thay đổi vào một câu lệnh:

~~~sql
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;
~~~

Ứng dụng kiểm tra affected rows:

- 1 hàng: điều kiện đúng và cập nhật thành công.
- 0 hàng: tài khoản không tồn tại hoặc số dư không đủ; cần xác định nguyên nhân theo yêu cầu nghiệp vụ.

Cách này giảm khoảng thời gian giữa đọc và ghi, đồng thời tránh dùng giá trị snapshot cũ làm căn cứ cập nhật.

## 15. Các lỗi thường gặp

**“START TRANSACTION tạo snapshot ngay lập tức.”** Không nhất thiết. Với REPEATABLE READ, consistent read đầu tiên thường tạo read view. Dùng WITH CONSISTENT SNAPSHOT nếu cần tạo snapshot ngay khi bắt đầu.

**“Hai SELECT trong REPEATABLE READ luôn thấy dữ liệu mới nhất.”** Không. Các consistent read trong cùng transaction tái sử dụng snapshot và có thể tiếp tục thấy phiên bản cũ.

**“SELECT ... FOR UPDATE cũng đọc snapshot cũ.”** Không. Đây là current/locking read, đọc phiên bản hiện hành cần thiết cho thao tác khóa.

**“Một transaction chỉ có một kiểu nhìn dữ liệu.”** Không. Consistent read và current read có thể xuất hiện trong cùng transaction và cho kết quả khác nhau.

**“MVCC có nghĩa là không cần khóa.”** Không. MVCC hỗ trợ consistent reads; thao tác ghi và locking read vẫn cần khóa để điều phối xung đột.

**“REPEATABLE READ luôn tương đương SERIALIZABLE.”** Không. Snapshot nhất quán không tự bảo vệ mọi invariant nghiệp vụ trải qua nhiều hàng; cần khóa, ràng buộc hoặc mức cô lập phù hợp.

**“Transaction đọc lâu không ảnh hưởng hệ thống.”** Không. Read view cũ có thể trì hoãn purge và làm undo history tăng.

**“Autocommit bật vẫn giữ snapshot qua nhiều câu SELECT.”** Không. Khi autocommit bật, mỗi câu lệnh độc lập thường là một transaction riêng. Muốn nhiều SELECT dùng cùng snapshot, phải mở transaction rõ ràng.

**“Chỉ cần đổi isolation level ở một connection là cả ứng dụng thay đổi.”** Không. SESSION áp dụng cho connection hiện tại; connection pool có nhiều session độc lập.

## 16. Checklist khi sử dụng REPEATABLE READ

- [ ] Đã xác định transaction cần snapshot nhất quán hay cần đọc phiên bản hiện hành để cập nhật.
- [ ] Đã kiểm tra isolation level thực tế của connection.
- [ ] Đã hiểu snapshot được tạo ở consistent read đầu tiên hay tại START TRANSACTION WITH CONSISTENT SNAPSHOT.
- [ ] Đã mở transaction tường minh nếu nhiều câu SELECT cần cùng read view.
- [ ] Không dùng kết quả consistent read cũ để ra quyết định cập nhật dữ liệu hiện hành mà không có khóa hoặc điều kiện nguyên tử.
- [ ] Đã phân biệt SELECT thông thường với SELECT ... FOR UPDATE và SELECT ... FOR SHARE.
- [ ] Đã kiểm tra điều kiện phạm vi và index khi dùng locking range read.
- [ ] Đã tính đến lock wait, deadlock và thứ tự lấy khóa.
- [ ] Đã bảo đảm transaction kết thúc bằng COMMIT hoặc ROLLBACK.
- [ ] Đã theo dõi transaction lâu, undo history và purge khi workload đọc kéo dài.
- [ ] Đã kiểm tra hành vi với hai session độc lập, có thứ tự commit rõ ràng.

## Kết luận

Trong InnoDB REPEATABLE READ, consistent read đầu tiên thường tạo read view và các consistent read tiếp theo trong cùng transaction tái sử dụng ảnh chụp đó. Đây là cơ chế giúp báo cáo đọc lặp lại cùng một trạng thái dữ liệu mà không cần khóa hàng chỉ để đọc.

SELECT ... FOR UPDATE, SELECT ... FOR SHARE và các câu lệnh thay đổi dữ liệu dùng current read/locking để làm việc với phiên bản hiện hành. Vì vậy, một transaction có thể thấy snapshot cũ qua SELECT thông thường nhưng thấy dữ liệu mới hơn qua locking read. Hiểu sự khác biệt này, giữ transaction ngắn và kiểm tra bằng hai session là nền tảng để xây dựng giao dịch MySQL đúng và có khả năng chịu tải.
