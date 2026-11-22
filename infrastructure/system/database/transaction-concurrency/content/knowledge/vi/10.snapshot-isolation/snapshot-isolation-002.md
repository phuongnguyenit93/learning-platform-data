# Xung đột ghi–ghi và chính sách xử lý phụ thuộc hệ quản trị

MVCC (Multi-Version Concurrency Control) cho phép transaction đọc một phiên bản phù hợp với snapshot của mình trong khi transaction khác đang cập nhật dữ liệu. Nhưng khi hai transaction cùng sửa một hàng, DBMS vẫn phải quyết định ai được ghi, transaction còn lại phải chờ hay bị hủy, và điều kiện cập nhật có được đánh giá lại trên phiên bản mới hay không.

Không có một chính sách ghi đồng thời giống nhau ở mọi hệ quản trị. PostgreSQL, MySQL InnoDB, SQL Server và Oracle đều dùng phiên bản dữ liệu và khóa theo những cách khác nhau. Thậm chí cùng một tên isolation level như REPEATABLE READ cũng không bảo đảm cùng một hành vi giữa các DBMS.

Điểm cần nắm là: **snapshot quyết định transaction nhìn thấy phiên bản nào khi đọc; chính sách xung đột ghi quyết định điều gì xảy ra khi transaction muốn cập nhật một hàng đã bị transaction khác thay đổi.**

## 1. Xung đột ghi–ghi là gì?

Xung đột ghi–ghi (write-write conflict) xuất hiện khi hai transaction cùng muốn thay đổi một hàng hoặc một tài nguyên dữ liệu theo cách không thể áp dụng độc lập. Ví dụ, hai transaction cùng cập nhật số dư tài khoản có id bằng 1.

Giả sử ban đầu:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL
);

INSERT INTO accounts (account_id, balance)
VALUES (1, 100.00);
~~~

Transaction A muốn cộng 10, transaction B muốn cộng 20. Cả hai cùng đọc số dư 100 trước khi ghi:

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| 1 | Đọc balance = 100 | |
| 2 | | Đọc balance = 100 |
| 3 | Tính kết quả 110 | Tính kết quả 120 |
| 4 | Ghi balance = 110 | |
| 5 | Commit | |
| 6 | | Thử ghi balance = 120 |
| 7 | | Commit hoặc nhận lỗi, tùy DBMS và isolation level |

Tại thời điểm B muốn ghi, hàng có thể đã được A thay đổi. DBMS phải xử lý tình huống này theo chính sách của nó. Hai kết quả thường gặp là B chờ rồi tiếp tục ghi, hoặc B bị hủy vì phiên bản mà B dựa vào đã cũ.

Cần phân biệt ba vấn đề có liên quan:

- **Write-write conflict**: hai transaction tranh chấp quyền cập nhật cùng một hàng.
- **Lost update**: một cập nhật bị ghi đè bởi giá trị được tính từ dữ liệu cũ, khiến thay đổi trước đó biến mất.
- **Write skew**: hai transaction đọc cùng một tập dữ liệu nhưng cập nhật các hàng khác nhau; từng thao tác ghi không đụng cùng hàng, nhưng kết quả kết hợp vi phạm một quy tắc nghiệp vụ.

Xung đột ghi–ghi là tình huống DBMS phải điều phối. Lost update là một dạng kết quả sai có thể xảy ra nếu cách ứng dụng đọc và ghi không giữ được ý định cập nhật. Write skew là vấn đề khác: chỉ khóa hoặc kiểm tra xung đột trên cùng một hàng có thể chưa đủ để ngăn nó.

## 2. Hai chính sách xử lý phổ biến

Khi một transaction muốn ghi hàng đã bị transaction khác thay đổi, có hai nhóm chính sách thường gặp.

### Chính sách 1: Chờ transaction trước rồi tiếp tục trên phiên bản mới

DBMS dùng khóa ghi để bảo đảm tại một thời điểm chỉ có một transaction nắm quyền cập nhật xung đột trên hàng. Transaction đến sau phải chờ.

Nếu transaction trước commit, DBMS có thể tiếp tục câu lệnh ghi sau trên phiên bản mới nhất và đánh giá lại điều kiện WHERE. Nếu transaction trước rollback, transaction chờ có thể tiếp tục trên trạng thái còn lại.

Cách này thường thấy trong các thao tác DML của InnoDB và trong PostgreSQL ở mức READ COMMITTED. Cách đánh giá lại điều kiện và biểu thức cập nhật cần hiểu theo đúng ngữ nghĩa từng DBMS.

Điều quan trọng: **chờ rồi tiếp tục không đồng nghĩa DBMS biết phép tính nghiệp vụ mà ứng dụng định thực hiện.** Nếu B đã tính sẵn số 120 từ snapshot cũ rồi gửi câu UPDATE gán cố định 120, DBMS không thể tự suy ra B muốn cộng thêm 20 vào giá trị mới nhất.

### Chính sách 2: Hủy transaction có snapshot đã lỗi thời

Với snapshot isolation, transaction thường đọc từ một snapshot ổn định. Nếu transaction khác đã commit thay đổi cùng hàng mà transaction hiện tại muốn ghi, DBMS có thể từ chối thao tác để không cho transaction tiếp tục dựa trên snapshot cũ.

Đây thường được mô tả là chính sách first-updater-wins hoặc first-committer-wins, tùy thuật toán và DBMS:

- Transaction thắng được quyền ghi hàng và commit.
- Transaction còn lại phát hiện hàng đã thay đổi kể từ snapshot của mình.
- DBMS hủy transaction hoặc trả lỗi serialization/update conflict.
- Ứng dụng phải rollback và chạy lại toàn bộ transaction nếu nghiệp vụ cho phép.

PostgreSQL REPEATABLE READ, SQL Server SNAPSHOT và Oracle SERIALIZABLE có các dạng phát hiện xung đột snapshot theo cách riêng. Tên isolation level và chi tiết chính xác khác nhau, nên không nên coi chúng là một giao thức chung.

## 3. PostgreSQL: READ COMMITTED có thể chờ và cập nhật phiên bản mới

PostgreSQL dùng MVCC. Ở READ COMMITTED, mỗi câu lệnh thường có snapshot riêng. Khi một câu UPDATE gặp hàng đang bị transaction khác cập nhật, nó có thể phải chờ khóa hàng.

Sau khi transaction đang giữ khóa commit, PostgreSQL tìm phiên bản hàng mới và đánh giá lại điều kiện WHERE trên phiên bản đó. Nếu hàng vẫn thỏa điều kiện, UPDATE tiếp tục. Biểu thức SET được áp dụng cho phiên bản hàng mới.

Ví dụ, hai transaction thực hiện:

~~~sql
-- Transaction A
BEGIN;

UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
~~~

~~~sql
-- Transaction B
BEGIN;

UPDATE accounts
SET balance = balance + 20
WHERE account_id = 1;

COMMIT;
~~~

Nếu B phải chờ A, sau khi A commit, phép cộng của B được áp dụng lên số dư mới. Kết quả cuối là 130.

Nhưng nếu B gửi một giá trị tuyệt đối được tính từ lần đọc cũ:

~~~sql
-- B đã đọc balance = 100 từ trước đó.
UPDATE accounts
SET balance = 120
WHERE account_id = 1;
~~~

B có thể chờ A rồi ghi 120 lên phiên bản mới, làm mất phần cộng 10 của A. DBMS đã tuần tự hóa hai lần ghi, nhưng ứng dụng vẫn đưa ra giá trị dựa trên trạng thái cũ.

### PostgreSQL REPEATABLE READ

Trong PostgreSQL, REPEATABLE READ cung cấp snapshot ổn định ở cấp transaction. Nếu một transaction muốn cập nhật hàng đã được transaction khác thay đổi sau thời điểm snapshot của nó được thiết lập, PostgreSQL hủy thao tác với lỗi serialization, thường có SQLSTATE **40001**.

Ví dụ:

1. A và B bắt đầu transaction, cùng nhìn thấy balance = 100.
2. A cập nhật balance lên 110 rồi commit.
3. B thử cập nhật chính hàng đó.
4. Vì hàng đã bị thay đổi kể từ snapshot của B, PostgreSQL từ chối cập nhật của B.
5. B phải rollback; nếu nghiệp vụ còn hợp lệ, ứng dụng bắt đầu transaction mới, đọc lại số dư 110 rồi tính tiếp.

Chính sách này tránh việc B âm thầm ghi dựa trên phiên bản cũ trong cùng transaction snapshot. Ứng dụng cần xử lý lỗi và retry toàn bộ transaction, bao gồm các câu SELECT và quyết định nghiệp vụ trước đó.

### PostgreSQL SERIALIZABLE

SERIALIZABLE bổ sung cơ chế Serializable Snapshot Isolation (SSI). DBMS theo dõi các phụ thuộc đọc/ghi có thể tạo ra một lịch không tương đương với bất kỳ thứ tự tuần tự nào. Một transaction có thể bị hủy với lỗi serialization ngay cả khi hai transaction không cùng cập nhật một hàng.

Điều này quan trọng với write skew. Ví dụ, quy tắc nghiệp vụ yêu cầu luôn có ít nhất một bác sĩ trực. Hai transaction cùng đọc thấy hai bác sĩ đều đang trực, rồi mỗi transaction cập nhật trạng thái của một bác sĩ khác nhau thành nghỉ. Vì chúng ghi hai hàng khác nhau, xung đột ghi trên cùng hàng không phát hiện được vấn đề. SERIALIZABLE có thể phát hiện chuỗi phụ thuộc nguy hiểm và hủy một transaction.

## 4. MySQL InnoDB: consistent read và current read có vai trò khác nhau

InnoDB kết hợp MVCC với khóa. Ở REPEATABLE READ, một câu SELECT thông thường là consistent read: nó đọc phiên bản phù hợp với read view của transaction. Những lần SELECT thông thường trong cùng transaction có thể tiếp tục nhìn thấy snapshot đã thiết lập.

Các câu lệnh cập nhật và locking read như SELECT ... FOR UPDATE có hành vi current read: chúng làm việc với phiên bản hiện tại phù hợp với thao tác khóa, không đơn giản dùng lại phiên bản cũ mà SELECT thông thường đã nhìn thấy.

Ví dụ:

~~~sql
-- Transaction A
START TRANSACTION;

UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- Chưa commit.
~~~

~~~sql
-- Transaction B
START TRANSACTION;

UPDATE accounts
SET balance = balance + 20
WHERE account_id = 1;

-- Nếu A đang giữ khóa ghi, B phải chờ.
~~~

Khi A commit, B có thể tiếp tục cập nhật hàng hiện tại. Với biểu thức **balance = balance + 20**, kết quả có thể cộng tiếp trên giá trị mới nhất.

Tuy nhiên, nếu B đã đọc balance = 100 bằng consistent read, tính ra 120 ở phía ứng dụng và gửi giá trị tuyệt đối:

~~~sql
UPDATE accounts
SET balance = 120
WHERE account_id = 1;
~~~

B có thể ghi 120 sau khi chờ A, khiến cập nhật của A bị ghi đè. Snapshot của câu SELECT trước đó không tự biến thành một điều kiện kiểm tra version cho câu UPDATE sau.

Khi nghiệp vụ phải đọc rồi quyết định cập nhật, có thể dùng locking read:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Đọc trạng thái sau khi lấy được khóa.
-- Kiểm tra quy tắc nghiệp vụ và cập nhật trong cùng transaction.

UPDATE accounts
SET balance = balance - 20
WHERE account_id = 1;

COMMIT;
~~~

InnoDB còn có các chi tiết khóa như record lock, gap lock và next-key lock. Những khóa này ảnh hưởng đến cách ngăn xung đột và phantom trong các truy vấn cụ thể. Hành vi phụ thuộc isolation level, chỉ mục và điều kiện truy vấn; không nên suy ra chỉ từ việc bảng đang dùng MVCC.

## 5. SQL Server: locking READ COMMITTED, RCSI và SNAPSHOT

SQL Server có nhiều chế độ đọc dữ liệu phiên bản, cần phân biệt rõ:

- **Locking READ COMMITTED**: chế độ truyền thống dùng khóa để bảo vệ lượt đọc và ghi theo thời gian cần thiết. Writer cập nhật cùng hàng có thể phải chờ khóa độc quyền của writer trước.
- **READ_COMMITTED_SNAPSHOT (RCSI)**: khi bật ở cấp database, các câu SELECT ở READ COMMITTED đọc phiên bản nhất quán theo thời điểm bắt đầu câu lệnh. Các thao tác ghi vẫn phải phối hợp bằng khóa; RCSI không làm hai writer cùng sửa một hàng mà không điều phối.
- **SNAPSHOT isolation**: transaction đọc từ snapshot ổn định ở cấp transaction. Nếu transaction muốn cập nhật hàng đã bị transaction khác thay đổi kể từ snapshot, SQL Server có thể hủy transaction với update conflict, thường là lỗi 3960.

Có thể hình dung khác biệt giữa RCSI và SNAPSHOT như sau:

| Chế độ | Snapshot áp dụng cho | Xử lý writer cùng sửa một hàng |
|---|---|---|
| Locking READ COMMITTED | Không dùng row version cho lượt đọc thông thường | Writer chờ khóa xung đột |
| READ_COMMITTED_SNAPSHOT | Mỗi câu SELECT | Writer vẫn được điều phối bằng khóa; reader dùng phiên bản |
| SNAPSHOT | Toàn bộ transaction | Transaction ghi trên phiên bản đã bị thay đổi có thể bị hủy vì update conflict |

RCSI chủ yếu thay đổi cách reader và writer tương tác. Nó không biến thao tác ghi thành một phép cập nhật không khóa. SNAPSHOT cung cấp snapshot ổn định hơn, đồng thời yêu cầu ứng dụng xử lý update conflict.

Nếu ứng dụng cần đọc hàng rồi cập nhật dựa trên dữ liệu đó, có thể sử dụng locking hint như **UPDLOCK** trong một transaction phù hợp, hoặc thiết kế optimistic concurrency với cột **rowversion**. Cột rowversion của SQL Server là giá trị nhị phân được DBMS tạo để nhận diện phiên bản thay đổi của hàng; nó không phải timestamp ngày giờ và không tự động ngăn cập nhật nếu câu UPDATE không so sánh giá trị đã đọc.

## 6. Oracle: READ COMMITTED theo câu lệnh, SERIALIZABLE theo transaction

Oracle dùng consistent read dựa trên undo để cung cấp ảnh chụp nhất quán cho truy vấn. READ COMMITTED là isolation mặc định; một câu lệnh nhìn thấy dữ liệu đã commit tại thời điểm bắt đầu câu lệnh. Transaction khác cập nhật cùng hàng có thể phải chờ khóa hàng.

Khi transaction cần đọc một hàng rồi chắc chắn rằng hàng không bị transaction khác thay đổi trước khi cập nhật, có thể khóa hàng bằng SELECT FOR UPDATE:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Transaction giữ khóa cho đến khi commit hoặc rollback. Các transaction khác muốn cập nhật hàng đó phải chờ hoặc dùng tùy chọn WAIT, NOWAIT hay SKIP LOCKED theo nhu cầu xử lý.

Ở SERIALIZABLE, Oracle cung cấp snapshot ở cấp transaction. Nếu transaction cần cập nhật một hàng đã bị transaction khác thay đổi kể từ khi transaction hiện tại bắt đầu, Oracle có thể trả lỗi **ORA-08177: can't serialize access for this transaction**. Ứng dụng cần rollback và thực hiện lại transaction trên trạng thái mới.

Giống các hệ quản trị khác, SERIALIZABLE không có nghĩa mọi transaction bị xếp hàng chạy tuần tự hoàn toàn. DBMS vẫn có thể thực thi đồng thời và từ chối một transaction khi không thể bảo đảm ngữ nghĩa tuần tự.

## 7. So sánh chính sách xử lý giữa các DBMS

Bảng dưới đây mô tả xu hướng phổ biến với các cấu hình mặc định hoặc chế độ được nêu. Cấu hình database, isolation level, loại truy vấn và phiên bản có thể làm thay đổi hành vi cụ thể.

| Hệ quản trị / chế độ | Reader nhìn snapshot | Writer cùng sửa một hàng | Khi transaction dựa trên snapshot cũ |
|---|---|---|---|
| PostgreSQL READ COMMITTED | Snapshot theo câu lệnh | Writer sau có thể chờ, sau đó đánh giá lại WHERE trên phiên bản mới | Có thể tiếp tục trên hàng mới; giá trị tuyệt đối do ứng dụng gửi vẫn có thể gây lost update |
| PostgreSQL REPEATABLE READ | Snapshot ổn định theo transaction | Writer xung đột có thể bị từ chối | Serialization failure, cần rollback và retry toàn bộ transaction |
| PostgreSQL SERIALIZABLE | Snapshot transaction và SSI | Có thể chờ hoặc bị hủy do phụ thuộc nguy hiểm | Serialization failure để bảo vệ tính tuần tự |
| MySQL InnoDB REPEATABLE READ | SELECT thường dùng consistent read view | DML dùng current read và khóa ghi; writer sau có thể chờ rồi cập nhật phiên bản hiện tại | Có thể ghi đè nếu gửi giá trị tuyệt đối tính từ consistent read cũ |
| SQL Server READ COMMITTED | Thường dùng locking read, trừ khi bật RCSI | Writer chờ khóa xung đột | Khóa điều phối writer; vẫn cần bảo vệ phép tính phía ứng dụng |
| SQL Server READ_COMMITTED_SNAPSHOT | Snapshot theo câu SELECT | Writer vẫn dùng khóa để điều phối ghi | Reader ít chặn writer hơn, nhưng không thay đổi nguyên tắc xung đột ghi |
| SQL Server SNAPSHOT | Snapshot ổn định theo transaction | Transaction cập nhật phiên bản đã bị thay đổi có thể bị hủy | Update conflict, thường lỗi 3960 |
| Oracle READ COMMITTED | Snapshot theo câu lệnh | Writer chờ khóa hàng xung đột | Cần kiểm tra điều kiện và thiết kế thao tác cập nhật theo dữ liệu hiện tại |
| Oracle SERIALIZABLE | Snapshot ổn định theo transaction | Có thể từ chối cập nhật hàng đã thay đổi sau khi transaction bắt đầu | ORA-08177, cần rollback và retry nếu phù hợp |

Không nên chỉ nhìn vào tên READ COMMITTED hoặc REPEATABLE READ để dự đoán chính sách. Ví dụ, PostgreSQL REPEATABLE READ có hành vi snapshot isolation và hủy transaction khi cập nhật hàng đã thay đổi. InnoDB REPEATABLE READ lại cho phép các câu DML dùng current read để chờ và cập nhật phiên bản hiện tại trong nhiều tình huống. Cùng tên isolation level nhưng chính sách có thể khác đáng kể.

## 8. Vì sao chờ rồi cập nhật vẫn có thể gây lost update?

Giả sử cả A và B đều đọc balance = 100. A cộng 10 và B cộng 20. Nếu cả hai gửi giá trị tuyệt đối, câu UPDATE tương ứng là:

~~~sql
-- A
UPDATE accounts
SET balance = 110
WHERE account_id = 1;

-- B
UPDATE accounts
SET balance = 120
WHERE account_id = 1;
~~~

Trong hệ quản trị dùng chính sách chờ rồi tiếp tục, B có thể chờ A commit rồi ghi 120. DBMS điều phối hai lần ghi đúng quy tắc khóa, nhưng ứng dụng đã biến phép cộng thành hai lần gán giá trị tuyệt đối.

Nếu ý định nghiệp vụ là cộng thêm, hãy biểu diễn trực tiếp ý định đó trong SQL:

~~~sql
-- A
UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- B
UPDATE accounts
SET balance = balance + 20
WHERE account_id = 1;
~~~

Với cách cập nhật nguyên tử này, DBMS tính toán trên giá trị hàng hiện tại theo ngữ nghĩa cập nhật của hệ quản trị. Trong các hệ quản trị dùng chính sách chờ, B có thể cộng tiếp trên giá trị A vừa commit.

Nếu nghiệp vụ cần ghi giá trị được người dùng chỉnh sửa từ một màn hình đã mở lâu, không nên tự động cộng vào giá trị mới. Hãy phát hiện version đã thay đổi và yêu cầu người dùng tải lại hoặc giải quyết xung đột.

## 9. Các chiến lược ứng dụng có thể sử dụng

### Cập nhật nguyên tử bằng biểu thức

Dùng khi nghiệp vụ là cộng, trừ, tăng bộ đếm hoặc thay đổi giá trị dựa trên trạng thái hiện tại:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity > 0;
~~~

DBMS điều phối việc ghi hàng và đánh giá điều kiện trong câu lệnh. Ứng dụng cần kiểm tra số hàng bị ảnh hưởng để biết có giữ được sản phẩm hay không.

### Khóa hàng trước khi đọc

Dùng khi phải đọc nhiều trường, kiểm tra quy tắc rồi mới cập nhật:

~~~sql
BEGIN;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.

COMMIT;
~~~

Cú pháp và chi tiết khóa có khác biệt giữa DBMS. Hãy dùng locking read đúng theo hệ quản trị đang vận hành và giữ transaction ngắn.

### Optimistic locking với version

Thêm một cột version hoặc dùng cơ chế tương đương của DBMS. Khi đọc, ứng dụng ghi nhớ version; khi cập nhật, chỉ cho phép ghi nếu version vẫn khớp:

~~~sql
UPDATE accounts
SET balance = 120,
    version = version + 1
WHERE account_id = 1
  AND version = 7;
~~~

Nếu số hàng cập nhật bằng 0, dữ liệu đã bị thay đổi hoặc hàng không tồn tại. Ứng dụng cần đọc lại và giải quyết xung đột. Mọi đường ghi liên quan phải tăng version; nếu có đường ghi bỏ qua bước này, cơ chế optimistic locking không còn đáng tin cậy.

SQL Server có thể dùng kiểu **rowversion** làm token phiên bản. Với các DBMS khác, có thể dùng cột số tự tăng do ứng dụng cập nhật hoặc token phiên bản tương đương.

### SERIALIZABLE khi quy tắc phụ thuộc nhiều hàng

Dùng khi kết quả nghiệp vụ phụ thuộc nhiều lần đọc và ghi mà không thể dễ dàng khóa hoặc biểu diễn thành một câu lệnh. DBMS có thể hủy transaction để bảo đảm tính tuần tự. Ứng dụng phải nhận diện lỗi serialization và retry toàn bộ transaction.

SERIALIZABLE có chi phí tranh chấp và retry. Hãy đo lường tải thực tế, xác định các truy vấn tạo phụ thuộc và giữ transaction ngắn.

## 10. Xử lý lỗi và retry đúng ranh giới

Một transaction bị hủy do xung đột không thể được xem là đã hoàn tất một phần. Khi DBMS báo serialization failure hoặc update conflict, ứng dụng thường phải rollback và bắt đầu transaction mới.

Quy trình retry nên tuân theo các nguyên tắc:

1. Phân loại lỗi. Serialization failure, deadlock, lock timeout và optimistic version mismatch có ý nghĩa khác nhau.
2. Rollback transaction hiện tại. Không tiếp tục dùng transaction đã bị đánh dấu lỗi.
3. Chạy lại toàn bộ phần đọc, kiểm tra và ghi trong một transaction mới. Snapshot mới có thể cho kết quả khác.
4. Giới hạn số lần retry, dùng backoff và jitter để tránh nhiều request va chạm liên tục.
5. Bảo vệ side effect bên ngoài như gửi email, gọi API thanh toán hoặc publish message. Những hành động này không tự rollback cùng database transaction; cần idempotency, outbox hoặc bước thực hiện sau commit phù hợp.

Một số mã lỗi thường gặp:

| Hệ quản trị | Mã lỗi | Ý nghĩa thường gặp |
|---|---|---|
| PostgreSQL | SQLSTATE 40001 | Serialization failure |
| PostgreSQL | SQLSTATE 40P01 | Deadlock detected |
| SQL Server | Error 3960 | Snapshot update conflict |
| Oracle | ORA-08177 | Không thể serialize transaction |
| MySQL InnoDB | Error 1213 | Deadlock found; transaction bị rollback |
| MySQL InnoDB | Error 1205 | Lock wait timeout exceeded |

Mã lỗi có thể phụ thuộc phiên bản, driver và ngữ cảnh. Ứng dụng nên phân loại theo mã lỗi do driver cung cấp, không chỉ so sánh chuỗi thông báo. Đặc biệt, lock wait timeout không phải lúc nào cũng có cùng phạm vi rollback như deadlock; hãy kiểm tra cấu hình và hành vi của phiên bản DBMS đang dùng.

## 11. Cách tái hiện và quan sát xung đột

Có thể mở hai connection độc lập để thấy chính sách ghi của DBMS.

**Connection A**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 10
WHERE account_id = 1;

-- Chưa commit để giữ khóa ghi.
~~~

**Connection B**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 20
WHERE account_id = 1;

-- Quan sát xem câu lệnh chờ hay trả lỗi.
~~~

Quay lại Connection A:

~~~sql
COMMIT;
~~~

Quan sát Connection B:

- Nếu B tiếp tục sau khi A commit, DBMS đang cho phép thao tác ghi tiếp trên trạng thái mới theo isolation level hiện tại.
- Nếu B nhận serialization/update conflict, DBMS đang từ chối transaction dựa trên snapshot đã lỗi thời.
- Nếu B nhận deadlock hoặc lock timeout, hãy xem thêm các transaction khác và thứ tự lấy khóa; hai writer cùng chờ một hàng thường chỉ tạo chờ, chưa đủ để thành deadlock.

Để phân biệt lost update, chạy lại thử nghiệm với B dùng **SET balance = 120** sau khi đã đọc 100 trước đó. So sánh kết quả với phép cộng nguyên tử **SET balance = balance + 20**.

Khi quan sát trên môi trường thật, hãy kiểm tra transaction giữ khóa, transaction đang chờ, thời gian chờ, isolation level và câu SQL cụ thể. Một câu SELECT có thể đang đọc phiên bản cũ mà không chờ, trong khi UPDATE trên cùng hàng lại đang đợi khóa ghi. Đây là hành vi bình thường ở hệ thống dùng MVCC kết hợp khóa.

## 12. Cách lựa chọn chính sách cho từng nghiệp vụ

| Nhu cầu | Hướng xử lý |
|---|---|
| Cộng/trừ số lượng hoặc số dư theo giá trị hiện tại | UPDATE nguyên tử bằng biểu thức và điều kiện trong SQL |
| Đọc hàng rồi thực hiện nhiều bước quyết định trên hàng đó | Locking read như SELECT FOR UPDATE trong transaction ngắn |
| Người dùng sửa dữ liệu từ màn hình có thể đã cũ | Optimistic locking bằng version; báo xung đột khi version không khớp |
| Quy tắc phụ thuộc nhiều hàng hoặc nhiều lần đọc/ghi | Xem xét SERIALIZABLE và retry toàn bộ transaction |
| Chỉ một công việc nghiệp vụ được chạy trên một tài nguyên | Có thể dùng advisory lock bổ sung, nhưng vẫn cần constraint và khóa dữ liệu phù hợp |
| Bảo đảm dữ liệu luôn thỏa quy tắc | Dùng UNIQUE, CHECK, khóa ngoại hoặc điều kiện cập nhật ở DBMS |

Trước khi triển khai, hãy xác định DBMS và isolation level thật sự đang dùng; kiểm tra cấu hình như RCSI hoặc snapshot isolation trên SQL Server; xác định câu SELECT là consistent read hay locking read trong InnoDB; và kiểm tra transaction có thể bị retry hay không.

Xung đột ghi–ghi là một phần bình thường của xử lý đồng thời. Điều quan trọng là biết DBMS đang chờ để cập nhật phiên bản mới hay hủy transaction vì snapshot đã lỗi thời, đồng thời bảo đảm ứng dụng không ghi đè dữ liệu bằng kết quả tính từ một lần đọc cũ. Khi chọn đúng chính sách cho từng nghiệp vụ và xử lý retry ở ranh giới transaction, ứng dụng có thể tận dụng MVCC mà vẫn giữ được tính đúng đắn của dữ liệu.
