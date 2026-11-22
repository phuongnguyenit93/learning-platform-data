# BEGIN, COMMIT, ROLLBACK và vòng đời giao dịch trong PostgreSQL

## 1. Giao dịch giải quyết bài toán gì?

Giả sử hệ thống chuyển **100 đơn vị tiền** từ tài khoản A sang tài khoản B. Về nghiệp vụ, thao tác này không phải một lệnh cập nhật đơn lẻ:

1. Kiểm tra tài khoản A và B còn hợp lệ.
2. Trừ 100 khỏi số dư A.
3. Cộng 100 vào số dư B.
4. Lưu bản ghi lịch sử chuyển tiền.

Nếu ứng dụng dừng sau bước trừ tiền nhưng trước bước cộng tiền, một hệ thống không có cơ chế giao dịch có thể để lại dữ liệu sai: tổng tiền của hai tài khoản bị giảm, trong khi giao dịch nghiệp vụ chưa hoàn thành.

**Transaction (giao dịch)** gom những thay đổi có liên quan thành một đơn vị xử lý:

- **`BEGIN`**: mở giao dịch tường minh.
- **`COMMIT`**: yêu cầu PostgreSQL hoàn tất giao dịch và làm các thay đổi của nó có hiệu lực.
- **`ROLLBACK`**: hủy các thay đổi chưa commit của giao dịch.

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Đoạn trên chỉ minh họa ranh giới giao dịch; để chuyển tiền **an toàn thực tế** còn phải kiểm tra tồn tại tài khoản, số dư, số hàng được cập nhật, tình huống truy cập đồng thời và ghi nhận request trùng. Những bước đó sẽ được xây dựng dần trong bài.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `BEGIN`, `COMMIT`, `ROLLBACK` và chế độ autocommit.
2. Giải thích **vòng đời** của giao dịch từ lúc bắt đầu, chạy lệnh, thành công hoặc thất bại đến khi kết thúc.
3. Nhận biết trạng thái giao dịch **bị lỗi (aborted)** và xử lý thông báo `current transaction is aborted`.
4. Sử dụng `SAVEPOINT` để quay lui một phần hợp lệ.
5. Hiểu mối quan hệ giữa giao dịch, ACID, MVCC, khóa và các mức cô lập.
6. Thử hai phiên kết nối đồng thời, quan sát dữ liệu chưa commit và việc chờ khóa.
7. Xác định đúng nơi đặt giao dịch trong ứng dụng/JDBC và connection pool.
8. Tránh giao dịch quá dài, lỗi retry và mất tính nhất quán khi liên quan hệ thống ngoài database.
9. Dùng SQL thực hành để kiểm tra thay đổi sau COMMIT và ROLLBACK.

> **Phạm vi:** toàn bộ ví dụ ghi dữ liệu phải chạy trong database thực hành. Không dùng tài khoản sản xuất hoặc tài khoản ngân hàng thật; không thử giữ khóa/chặn giao dịch trên production.

---

## 2. Giao dịch và bốn thuộc tính ACID

Một giao dịch có thể được xem là **ranh giới thành công hoặc thất bại** của một đơn vị nghiệp vụ. Bốn tính chất ACID thường được dùng để mô tả các bảo đảm quan trọng:

| Thuộc tính | Ý nghĩa thực tế | Ví dụ |
|---|---|---|
| **Atomicity** – nguyên tử | Hoặc các thay đổi của giao dịch được chấp nhận, hoặc chúng không được giữ lại | Không được chỉ trừ A mà không cộng B |
| **Consistency** – nhất quán | Giao dịch phải đưa database từ trạng thái hợp lệ sang trạng thái hợp lệ theo **các ràng buộc đã được định nghĩa** | `CHECK(balance >= 0)` chặn số dư âm |
| **Isolation** – cô lập | Quy định các giao dịch đồng thời nhìn thấy và tương tác với nhau như thế nào | Một phiên khác không đọc được số dư chưa commit |
| **Durability** – bền vững | Sau commit thành công theo cấu hình bảo đảm của hệ thống, dữ liệu phải tồn tại trước các sự cố nằm trong phạm vi bảo đảm đó | Giao dịch được xác nhận commit không biến mất chỉ vì kết nối client đóng |

### 2.1. ACID không thay thế thiết kế nghiệp vụ

Một giao dịch chứa hai lệnh SQL **không tự chứng minh** logic chuyển tiền đã đúng. Nếu ứng dụng:

- Chuyển số tiền âm.
- Chuyển đến tài khoản không tồn tại.
- Bỏ qua kết quả `UPDATE 0`.
- Ghi hai yêu cầu trùng cùng một `request_key`.
- Đọc số dư không có khóa rồi cập nhật dựa trên dữ liệu đã cũ.

thì vẫn có thể vi phạm nghiệp vụ dù dùng `BEGIN` và `COMMIT`.

**Consistency** đòi ràng buộc ở database (PK, FK, CHECK, UNIQUE,...) kết hợp logic ứng dụng, mức cô lập và xử lý lỗi phù hợp. PostgreSQL không thể tự suy đoán mọi bất biến nghiệp vụ.

### 2.2. Isolation không đồng nghĩa mọi giao dịch đều SERIALIZABLE

Mức cô lập mặc định của PostgreSQL thường là **READ COMMITTED**. Nó ngăn dirty reads, nhưng hai câu `SELECT` trong cùng transaction có thể nhìn thấy kết quả khác nhau nếu phiên khác commit giữa hai lần đọc. Muốn bảo đảm mạnh hơn, cần chọn mức cô lập hoặc kỹ thuật khóa/kiểm soát đồng thời phù hợp.

### 2.3. Durability phụ thuộc cả cấu hình và hạ tầng

PostgreSQL dùng WAL và các cơ chế bền vững. Tuy nhiên chi tiết bảo đảm commit còn phụ thuộc những tùy chọn như `synchronous_commit`, replication, lưu trữ và chính sách failover. Đừng diễn giải một câu "COMMIT thành công" là **đã ghi đồng bộ vào mọi replica hay mọi hệ thống ngoài database**.

---

## 3. Tạo dữ liệu thực hành với tài khoản và nhật ký chuyển tiền

Tạo schema và các bảng độc lập trong database lab:

~~~sql
CREATE SCHEMA IF NOT EXISTS tx_lab;

CREATE TABLE tx_lab.accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    balance NUMERIC(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tx_lab.transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    from_account_id INTEGER NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_account_id <> to_account_id)
);
~~~

Nạp dữ liệu ban đầu **một lần**:

~~~sql
INSERT INTO tx_lab.accounts
    (account_id, account_name, balance)
VALUES
    (1, 'Tài khoản A', 1000.00),
    (2, 'Tài khoản B', 500.00),
    (3, 'Tài khoản C', 0.00);
~~~

Kiểm tra:

~~~sql
SELECT account_id, account_name, balance
FROM tx_lab.accounts
ORDER BY account_id;
~~~

| account_id | account_name | balance |
|---:|---|---:|
| 1 | Tài khoản A | 1000.00 |
| 2 | Tài khoản B | 500.00 |
| 3 | Tài khoản C | 0.00 |

Tổng ban đầu là **1500**:

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

> Những ví dụ sau được viết thành **các kịch bản riêng biệt**. Khi thử nhiều kịch bản, trạng thái sau kịch bản đã COMMIT có thể khác trạng thái ban đầu. Đừng tự giả định dữ liệu còn ở 1000/500 sau khi đã thực hành một giao dịch commit.

### 3.1. Ghi dữ liệu kiểm thử nhưng không thay đổi lâu dài

Để thử điều chỉnh một số dư rồi trả lại dữ liệu:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Trong transaction, phiên hiện tại có thể thấy số dư tăng 10. Sau `ROLLBACK`, thay đổi **không tồn tại**; số dư về giá trị trước transaction này.

---

## 4. Cú pháp BEGIN, COMMIT và ROLLBACK

### 4.1. BEGIN: mở khối giao dịch tường minh

~~~sql
BEGIN;
~~~

PostgreSQL cũng hỗ trợ:

~~~sql
START TRANSACTION;
~~~

Sau đó các câu SQL liên quan thuộc cùng transaction cho đến khi `COMMIT` hoặc `ROLLBACK` (hoặc một tình huống kết thúc bất thường).

Ví dụ:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 25
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

ROLLBACK;
~~~

### 4.2. COMMIT: hoàn tất giao dịch

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 3;

COMMIT;
~~~

Khi `COMMIT` thành công, thay đổi của transaction được xác nhận. Một transaction tiếp theo sẽ nhìn thấy thay đổi đó theo các quy tắc cô lập của nó. Không thể dùng `ROLLBACK` **sau khi commit** để hủy ngược chính transaction đã hoàn tất.

Trong tài liệu có thể gặp `END`, là cách viết tương đương `COMMIT` trong PostgreSQL. Nên ưu tiên `COMMIT` để diễn đạt rõ hành động.

### 4.3. ROLLBACK: kết thúc và hủy các thay đổi chưa commit

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
~~~

Không có thay đổi tăng 100 nào của transaction này được giữ lại. PostgreSQL cũng có từ khóa `ABORT` tương đương với `ROLLBACK` ở mức lệnh.

### 4.4. COMMIT/ROLLBACK làm gì với các lệnh SELECT?

Transaction chỉ đọc không thay đổi bảng nhưng vẫn có:

- Snapshot/khả năng nhìn thấy dữ liệu theo mức cô lập.
- Các tài nguyên, khóa hoặc trạng thái liên quan.
- Thời điểm bắt đầu và kết thúc rõ ràng.

`ROLLBACK` của transaction chỉ đọc không phải "xóa kết quả SELECT đã trả về"; nó kết thúc transaction và giải phóng tài nguyên tương ứng.

### 4.5. Không có nested BEGIN kiểu giao dịch lồng nhau

Không viết theo suy nghĩ:

~~~sql
BEGIN;
    UPDATE ...;
    BEGIN;
        UPDATE ...;
    COMMIT;
ROLLBACK;
~~~

Trong PostgreSQL, `BEGIN` ở bên trong transaction đang hoạt động **không tạo giao dịch lồng**. Có thể nhận cảnh báo "there is already a transaction in progress". Để đánh dấu một phần công việc có thể quay lui, dùng **`SAVEPOINT`**.

### 4.6. COMMIT AND CHAIN / ROLLBACK AND CHAIN

PostgreSQL hỗ trợ:

~~~sql
COMMIT AND CHAIN;
-- Hoặc
ROLLBACK AND CHAIN;
~~~

Khi dùng trong transaction, câu lệnh kết thúc transaction hiện tại và **bắt đầu một transaction tiếp theo** với các đặc tính giao dịch liên quan được giữ theo semantics của `AND CHAIN`. Đây là trường hợp chuyên biệt, không thay thế cách phổ biến `COMMIT; BEGIN;` trong phần lớn ứng dụng.

---

## 5. Vòng đời giao dịch: một state machine

Về mặt ứng dụng, có thể hình dung:

~~~mermaid
flowchart TD
    A["Kết nối chưa ở trong transaction tường minh"] -->|"BEGIN"| B["Transaction đang hoạt động"]
    B -->|"SQL hợp lệ"| B
    B -->|"COMMIT thành công"| C["Committed: thay đổi có hiệu lực"]
    B -->|"ROLLBACK"| D["Rolled back: hủy thay đổi chưa commit"]
    B -->|"Lỗi SQL khi vẫn ở trong transaction"| E["Aborted: transaction đã lỗi"]
    E -->|"ROLLBACK"| D
    E -->|"ROLLBACK TO SAVEPOINT hợp lệ"| B
    E -->|"COMMIT"| D
    B -->|"Kết nối đóng bất ngờ trước COMMIT"| D
    C --> A
    D --> A
~~~

Sơ đồ minh họa **trạng thái logic**. Việc socket mất ở thời điểm đã gửi COMMIT có thể khiến **client không biết** commit đã thành công hay chưa; trường hợp "kết nối đóng trước COMMIT" chỉ áp dụng khi commit thật sự **chưa được xử lý**.

### 5.1. Các giai đoạn

1. **Chưa mở transaction tường minh:** ứng dụng có thể chạy từng statement trong chế độ autocommit.
2. **BEGIN:** transaction bắt đầu, cấu hình isolation/access mode có hiệu lực.
3. **Thực thi câu lệnh:** SELECT, INSERT, UPDATE, DELETE và nhiều DDL hợp lệ có thể nằm trong transaction; khóa, snapshot và ghi WAL được quản lý theo nhu cầu.
4. **Có lỗi:** nếu câu SQL báo lỗi làm transaction vào trạng thái aborted, những câu SQL thông thường tiếp theo sẽ bị từ chối cho đến khi rollback thích hợp.
5. **COMMIT:** PostgreSQL kiểm tra và hoàn tất việc chấp nhận các thay đổi; commit cũng có thể thất bại (ví dụ lỗi ràng buộc deferred hoặc serialization).
6. **ROLLBACK:** hủy các thay đổi chưa commit và kết thúc giao dịch.
7. **Trở về trạng thái sẵn sàng:** có thể bắt đầu transaction mới.

### 5.2. Các trạng thái thường thấy trong pg_stat_activity

Khi có quyền quan sát, cột `state` có thể cho thấy:

| `state` | Ý nghĩa thực hành |
|---|---|
| `active` | Backend đang thực thi một câu lệnh |
| `idle` | Đang chờ lệnh, hiện không trong transaction |
| `idle in transaction` | Đang chờ lệnh nhưng transaction vẫn mở |
| `idle in transaction (aborted)` | Transaction đã lỗi và session chưa rollback |

Đặc biệt, `idle in transaction` kéo dài có thể giữ tài nguyên/snapshot/khóa, cản trở các phiên khác và việc dọn dữ liệu cũ. Đây là một trạng thái **cần tránh** trong ứng dụng.

---

## 6. Autocommit và transaction tường minh

### 6.1. Không có BEGIN thì PostgreSQL có giao dịch không?

PostgreSQL vẫn thực thi mỗi câu lệnh trong **một transaction**, kể cả khi client không phát lệnh `BEGIN`. Trong chế độ autocommit thường thấy ở `psql`, từng statement độc lập được bắt đầu và kết thúc ngầm.

~~~sql
UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 2;
~~~

Trong autocommit thông thường, đây là **hai transaction riêng**. Nếu câu thứ nhất thành công mà câu thứ hai lỗi, câu thứ nhất **không tự bị rollback**.

### 6.2. BEGIN gom nhiều statement thành một transaction

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 2;

COMMIT;
~~~

Hai statement thuộc **cùng transaction**, có thể được chấp nhận/hủy cùng nhau. Đây là ranh giới cần thiết nếu nghiệp vụ yêu cầu hai thay đổi có quan hệ nguyên tử.

### 6.3. Autocommit là hành vi client, không phải "tắt transaction"

- `psql` thường chạy autocommit nếu không có `BEGIN` hoặc cấu hình khác.
- Ứng dụng JDBC có thể dùng `Connection.setAutoCommit(false)` để bắt đầu quản lý giao dịch bằng API connection; lúc đó không nhất thiết phải gửi chuỗi `BEGIN` thủ công.
- Framework/ORM có thể quản lý transaction qua annotation, context hoặc unit-of-work riêng.

**Không** dùng đồng thời nhiều cơ chế transaction một cách thiếu nhất quán. Cần biết ai là chủ sở hữu vòng đời transaction: thư viện, framework hay mã nghiệp vụ.

### 6.4. Transaction gắn với kết nối

Một transaction PostgreSQL thuộc **một database session/backend connection**. Ví dụ:

~~~text
Connection A: BEGIN → UPDATE → COMMIT
Connection B: SELECT ...
~~~

Connection B không được tự động "tham gia" transaction của A chỉ vì cùng request HTTP. Nếu lấy hai connection từ pool rồi chạy hai UPDATE trên hai connection, bạn **không** có một transaction chung.

---

## 7. Thực hành COMMIT và ROLLBACK với một kịch bản an toàn

### 7.1. Kịch bản ROLLBACK

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;
~~~

Nếu hai số dư trước transaction là 1000 và 500 thì **bên trong** transaction sẽ thấy 900 và 600; **sau ROLLBACK** trở lại 1000 và 500. Nếu số dư đã thay đổi từ bài thực hành trước, hãy so **giá trị trước và sau ROLLBACK**, không cố mong đúng các số ban đầu.

### 7.2. Kịch bản COMMIT

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (request_key, from_account_id, to_account_id, amount)
VALUES
    ('lab-transfer-0001', 1, 2, 100);

COMMIT;
~~~

Các thay đổi được giữ khi commit thành công. Lệnh INSERT `request_key='lab-transfer-0001'` có ràng buộc UNIQUE; chạy lại y nguyên sau khi đã COMMIT sẽ báo lỗi trùng request key. Đây là chủ ý bảo vệ chống ghi hai bản ghi lịch sử trùng, nhưng một ứng dụng thật phải có logic **kiểm tra trước/đối soát và retry** phù hợp, sẽ trình bày sau.

### 7.3. Đo số tiền được bảo toàn

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

Hai UPDATE `-100` và `+100` không làm đổi tổng tiền giữa các tài khoản. Nhưng **chỉ kiểm tra tổng** chưa đủ: có thể chuyển nhầm tài khoản mà tổng vẫn đúng. Cần thêm FK, request key, amount dương, kiểm soát số dư và xác minh các dòng đã cập nhật.

---

## 8. Transaction khi xảy ra lỗi SQL

### 8.1. Lỗi constraint khiến transaction bị aborted

Vì `balance` có CHECK không âm:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = -10
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

UPDATE báo lỗi vi phạm `CHECK(balance >= 0)`. Trong một transaction tường minh, sau lỗi SQL chưa được xử lý bằng savepoint, các lệnh bình thường tiếp theo thường báo:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
~~~

Đây không phải lỗi của câu SELECT sau; transaction **đã bị đánh dấu thất bại** từ lệnh trước.

Phục hồi:

~~~sql
ROLLBACK;
~~~

### 8.2. Không tiếp tục "cố COMMIT" sau lỗi

Nếu transaction đang trong trạng thái aborted, việc gửi `COMMIT` không biến các thay đổi lỗi thành hợp lệ; PostgreSQL sẽ kết thúc bằng rollback (phản hồi có thể là `ROLLBACK`). Ứng dụng phải xử lý lỗi **ngay từ câu SQL gây lỗi**, không xem việc gửi COMMIT như cách ép thành công.

### 8.3. Constraint không cần áp dụng vào mọi lệnh?

Một transaction có thể thực hiện nhiều lệnh và một constraint có thể được kiểm tra **ngay khi statement chạy** hoặc **muộn khi COMMIT** nếu constraint phù hợp được cấu hình `DEFERRABLE`. Vì vậy, thành công của mọi `UPDATE` chưa bảo đảm `COMMIT` luôn thành công; cần kiểm tra kết quả commit.

### 8.4. Cần kết thúc transaction trong mọi nhánh xử lý lỗi

Trên client:

~~~text
BEGIN
  |
  +-- câu lệnh thành công --> ... --> COMMIT
  |
  +-- lỗi ở bất kỳ bước nào ------> ROLLBACK
~~~

Nếu ứng dụng nuốt exception rồi trả connection còn trong transaction aborted vào pool, request sau có thể tiếp tục gặp lỗi `25P02` hoặc giữ tài nguyên không cần thiết.

---

## 9. SAVEPOINT: quay lui một phần giao dịch

`SAVEPOINT` không tạo transaction độc lập hoàn toàn. Nó đánh dấu vị trí trong transaction hiện tại để có thể hủy những thay đổi sau dấu mốc đó mà vẫn giữ các thay đổi trước đó.

### 9.1. Ví dụ thành công/không thành công

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT optional_step;

UPDATE tx_lab.accounts
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT optional_step;

-- Phần +20 ở B đã bị hủy, còn +10 ở A vẫn trong transaction.
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;
~~~

Cuối ví dụ dùng ROLLBACK toàn transaction để không giữ thay đổi trong lab. Nếu thay bằng COMMIT, thay đổi `+10` trước savepoint sẽ được commit.

### 9.2. Phục hồi sau lỗi constraint

~~~sql
BEGIN;

SAVEPOINT before_risky_update;

UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 3;

-- Sau lỗi, xử lý bằng cách quay về savepoint hợp lệ:
ROLLBACK TO SAVEPOINT before_risky_update;

-- Transaction có thể tiếp tục:
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

RELEASE SAVEPOINT before_risky_update;

ROLLBACK;
~~~

Trong kịch bản trên, thực hiện `ROLLBACK TO SAVEPOINT` sau lỗi giúp transaction trở lại trạng thái có thể tiếp tục. Nếu không có savepoint hợp lệ để rollback về, cần `ROLLBACK` toàn transaction.

### 9.3. RELEASE SAVEPOINT không phải COMMIT

~~~sql
RELEASE SAVEPOINT before_risky_update;
~~~

Chỉ xóa dấu mốc savepoint và kết hợp các thay đổi liên quan vào transaction ngoài. Các thay đổi **chưa được commit ra ngoài** cho đến khi `COMMIT` thành công. Sau `RELEASE`, không thể `ROLLBACK TO` savepoint vừa release.

### 9.4. SAVEPOINT có giới hạn

- Không có "nested commit" độc lập: transaction ngoài rollback thì mọi thay đổi còn chưa commit đều bị hủy, kể cả phần đã `RELEASE SAVEPOINT`.
- Một số tài nguyên/khóa có cơ chế được giải phóng khi rollback về savepoint theo semantics của PostgreSQL, nhưng không nên tự dựa vào savepoint để giải phóng mọi loại tài nguyên ngoài database.
- Quản lý nhiều savepoint phức tạp có thể làm ứng dụng khó hiểu và dễ nhầm logic nghiệp vụ.
- Cần phân biệt lỗi có thể bỏ qua ở bước phụ với lỗi mà giao dịch phải hủy toàn bộ (ví dụ chuyển tiền thất bại không thể chỉ bỏ bước trừ mà vẫn cộng).

### 9.5. Savepoint và exception trong PL/pgSQL

Trong PL/pgSQL, các block có `EXCEPTION` sử dụng cơ chế subtransaction để xử lý lỗi ở phạm vi block. Điều này liên quan nhưng không đồng nghĩa được phép phát `COMMIT` tùy ý từ mọi function. Quy tắc điều khiển transaction của function/procedure và hoàn cảnh gọi có giới hạn riêng.

---

## 10. DDL và transaction trong PostgreSQL

Một ưu điểm quan trọng: nhiều thay đổi schema của PostgreSQL hỗ trợ transaction, khác một số hệ quản trị có implicit commit cho nhiều DDL.

### 10.1. CREATE TABLE có thể rollback

Trong database lab:

~~~sql
BEGIN;

CREATE TABLE tx_lab.experimental_table (
    id INTEGER PRIMARY KEY,
    note TEXT NOT NULL
);

INSERT INTO tx_lab.experimental_table(id, note)
VALUES (1, 'chỉ dùng trong transaction');

ROLLBACK;
~~~

Sau khi rollback thành công, bảng `tx_lab.experimental_table` không tồn tại (nếu trước đó chưa có). Đây là điểm thuận tiện khi thử migration DDL có thể transaction hóa.

### 10.2. Nhiều DDL có thể chạy trong transaction

Ví dụ `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `CREATE INDEX` thông thường và nhiều thao tác schema khác có thể thuộc transaction, tùy câu lệnh cụ thể. Nhưng **không phải mọi lệnh quản trị** đều hỗ trợ bên trong transaction block.

Ví dụ:

~~~sql
-- Ví dụ câu lệnh không cho chạy trong transaction block:
BEGIN;
CREATE DATABASE should_not_run_inside_transaction;
ROLLBACK;
~~~

`CREATE DATABASE` không được thực thi trong transaction block. Không chạy lệnh này trong môi trường thật; nó chỉ minh họa giới hạn.

Một số thao tác như `CREATE INDEX CONCURRENTLY` hoặc `VACUUM` cũng có yêu cầu vận hành ngoài transaction block tương ứng.

### 10.3. DDL có thể giữ khóa mạnh

`ALTER TABLE` có thể lấy khóa ảnh hưởng đến đọc/ghi đồng thời, tùy thao tác. Bao bọc một migration lớn bằng BEGIN không tự đảm bảo "không downtime". Cần đánh giá loại lock, thời gian thực thi, `lock_timeout`, bảng lớn và kế hoạch rollback.

### 10.4. Migration nên có chiến lược rõ ràng

- Xác định câu lệnh nào hỗ trợ transaction.
- Tránh giữ transaction mở khi chờ kiểm tra thủ công.
- Không chạy `CREATE INDEX CONCURRENTLY` trong block BEGIN.
- Dự đoán khóa và kiểm tra trên staging.
- Có phương án triển khai từng bước với schema lớn.
- Đảm bảo kết nối không bị trả về pool khi migration còn transaction.

---

## 11. Tại sao thay đổi chưa commit không hiện với phiên khác?

PostgreSQL dùng **MVCC (Multi-Version Concurrency Control)** để quản lý khả năng nhìn thấy các phiên bản hàng. Khi một phiên thay đổi số dư nhưng chưa commit:

- Chính phiên đó thông thường **nhìn thấy thay đổi của mình**.
- Một phiên độc lập đọc bình thường ở `READ COMMITTED` sẽ **không đọc bẩn (dirty read)** thay đổi chưa commit của phiên thứ nhất.
- Các transaction khác có thể đọc phiên bản cũ phù hợp snapshot; một thao tác ghi/khóa trên cùng hàng có thể phải chờ.

### 11.1. Hai connection để kiểm chứng

Mở **hai cửa sổ psql hoặc hai connection độc lập** vào cùng database lab.

**Phiên A:**

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 77
WHERE account_id = 1;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Ghi nhớ số dư mới ở A, **chưa COMMIT**.

**Phiên B:**

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Ở READ COMMITTED thông thường, B thấy **số dư đã commit trước đó**, không phải phần `+77` chưa commit của A.

**Quay lại phiên A:**

~~~sql
ROLLBACK;
~~~

**Phiên B đọc lại:**

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Phần `+77` không xuất hiện vì đã rollback.

### 11.2. COMMIT rồi phiên B thấy gì?

Nếu lặp lại kịch bản nhưng phiên A COMMIT thay vì ROLLBACK, các statement SELECT mới trong B ở READ COMMITTED có thể thấy số dư đã commit. Nếu B đang ở mức REPEATABLE READ với snapshot cũ, kết quả nhìn thấy có thể khác cho đến khi transaction của B kết thúc.

### 11.3. MVCC không có nghĩa cập nhật đồng thời không bao giờ bị chặn

SELECT bình thường thường đọc qua snapshot mà không cần chờ row lock trên phiên bản cũ, nhưng `UPDATE`, `DELETE` hoặc `SELECT FOR UPDATE` trên cùng hàng có thể **đợi transaction đang giữ khóa**. "Người đọc không chặn người ghi" không nên hiểu thành "không tồn tại lock waits".

---

## 12. Mức cô lập giao dịch: READ COMMITTED đến SERIALIZABLE

Isolation level xác định các quy tắc nhìn thấy thay đổi từ những transaction đồng thời. PostgreSQL hỗ trợ các mức chuẩn SQL, nhưng có một số đặc điểm triển khai riêng.

### 12.1. Các mức chính

| Isolation level | Hành vi trọng tâm trong PostgreSQL | Tình huống thường dùng |
|---|---|---|
| `READ UNCOMMITTED` | PostgreSQL xử lý thực tế tương đương `READ COMMITTED`; không cho dirty read | Tương thích cú pháp, không có dirty read |
| `READ COMMITTED` | Mỗi statement có snapshot phù hợp khi statement bắt đầu; statement sau có thể thấy commit mới | Mặc định, nhiều tác vụ OLTP |
| `REPEATABLE READ` | Các lần đọc trong transaction thấy snapshot nhất quán của transaction (theo ngữ nghĩa PostgreSQL); ngăn nonrepeatable reads, nhưng chưa bảo đảm serializable hoàn toàn | Báo cáo nhiều câu SQL cần góc nhìn ổn định |
| `SERIALIZABLE` | PostgreSQL phát hiện các tương tác có thể không tương đương lịch chạy tuần tự; một số transaction có thể bị hủy với lỗi `40001` | Bất biến liên giao dịch cần tính tuần tự |

**Điểm then chốt:** isolation mạnh hơn không tự làm mất nhu cầu xử lý lỗi. `SERIALIZABLE` có thể yêu cầu ứng dụng **retry toàn bộ transaction** sau serialization failure.

### 12.2. Mức mặc định READ COMMITTED

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;

-- Nếu một transaction khác commit giữa hai lần SELECT:

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

Hai lần SELECT có thể thấy giá trị khác nhau vì PostgreSQL lấy snapshot phù hợp cho **mỗi statement** ở READ COMMITTED.

### 12.3. REPEATABLE READ

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT SUM(balance) AS total_1
FROM tx_lab.accounts;

-- Một transaction khác có thể commit thay đổi tại đây.

SELECT SUM(balance) AS total_2
FROM tx_lab.accounts;

COMMIT;
~~~

Trong transaction REPEATABLE READ này, những lần SELECT bình thường vẫn dựa trên **cùng snapshot của transaction**, nên không tự chuyển sang thấy các commit mới sau khi snapshot đã được thiết lập. Nhớ rằng snapshot thường được thiết lập khi **câu lệnh không phải transaction-control đầu tiên yêu cầu snapshot**, không nhất thiết đúng khoảnh khắc gửi ký tự BEGIN.

### 12.4. SERIALIZABLE và retry

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Đọc những ràng buộc liên quan.
-- Thực thi UPDATE/INSERT cần thiết.

COMMIT;
~~~

Khi PostgreSQL phát hiện lịch chạy xung đột với tính tuần tự, transaction có thể kết thúc với lỗi:

~~~text
SQLSTATE 40001: serialization_failure
~~~

Không nên chỉ retry câu UPDATE cuối: quyết định nghiệp vụ có thể dựa vào các lần SELECT trước. **Retry toàn bộ transaction** với snapshot mới và giới hạn số lần thử.

### 12.5. READ ONLY và DEFERRABLE

Với báo cáo cần snapshot ổn định, có thể dùng:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT account_id, balance
FROM tx_lab.accounts
ORDER BY account_id;

COMMIT;
~~~

Ở dạng phù hợp `SERIALIZABLE READ ONLY DEFERRABLE`, transaction có thể **chờ** để lấy snapshot an toàn nhằm giảm nguy cơ serialization failure của loại truy vấn này. Nó không có nghĩa mọi transaction READ ONLY hoặc mọi SELECT tự động không chờ.

### 12.6. Kiểm tra mức cô lập hiện tại

~~~sql
SHOW transaction_isolation;
SHOW transaction_read_only;
~~~

Trong transaction trước khi thực thi truy vấn dữ liệu, có thể dùng:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT current_setting('transaction_isolation');
ROLLBACK;
~~~

Không đổi isolation sau khi đã chạy những truy vấn cần snapshot rồi mong toàn bộ transaction được áp dụng quy tắc mới từ đầu.

---

## 13. Khóa dòng: khi hai transaction cập nhật cùng tài khoản

Để thử, mở hai connection riêng đến **cùng database lab**. Dùng các bước theo thứ tự, không chạy tự động toàn bộ khi chưa có khả năng dừng phiên.

### 13.1. Phiên A mở giao dịch và sửa một dòng

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 1;

-- Giữ giao dịch mở tạm thời để quan sát từ B.
~~~

Phiên A giữ những khóa liên quan đến thao tác UPDATE trong khi chưa commit/rollback.

### 13.2. Phiên B cố sửa cùng dòng

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

UPDATE tx_lab.accounts
SET balance = balance + 2
WHERE account_id = 1;
~~~

Phiên B có thể phải **chờ khóa** đang được A giữ. Sau khoảng thời gian đã định, nếu vẫn bị chặn, PostgreSQL báo lỗi timeout của thao tác lock. Vì lỗi xuất hiện trong transaction, B cần:

~~~sql
ROLLBACK;
~~~

### 13.3. Phiên A giải phóng khóa

~~~sql
ROLLBACK;
~~~

Trong ví dụ này, cả A và B đều rollback, nên không có thay đổi `+1` hoặc `+2` được giữ.

### 13.4. Tại sao cần lock_timeout trong lab?

Nếu không đặt giới hạn chờ và vô tình để phiên A `idle in transaction`, phiên B có thể chờ rất lâu. Dùng `SET LOCAL lock_timeout` trong bài giúp quan sát có kiểm soát, sau đó cấu hình timeout tự mất khi transaction kết thúc.

### 13.5. SELECT FOR UPDATE

Để khóa những hàng sẽ được sửa:

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Thực hiện các cập nhật liên quan.

ROLLBACK;
~~~

`FOR UPDATE` yêu cầu row locks trên những hàng được chọn. Những transaction khác muốn khóa/sửa cùng hàng theo chế độ xung đột có thể phải chờ.

**Không** dùng `SELECT FOR UPDATE` trên phạm vi lớn nếu chỉ cần báo cáo, vì nó tăng tranh chấp và có thể chặn công việc khác.

---

## 14. Tránh deadlock bằng thứ tự khóa ổn định

Deadlock có thể xảy ra khi hai transaction giữ những khóa khác nhau và chờ khóa của nhau.

~~~text
Transaction A                       Transaction B
-------------                       -------------
Giữ lock account 1                  Giữ lock account 2
Muốn lock account 2  ------X------> Giữ account 2
Giữ account 1        <------X------ Muốn lock account 1

=> Chu trình chờ khóa
~~~

PostgreSQL phát hiện deadlock và hủy một transaction để phá vòng chờ; ứng dụng có thể thấy:

~~~text
SQLSTATE 40P01: deadlock_detected
~~~

### 14.1. Chiến lược thứ tự khóa

Khi chuyển tiền giữa hai tài khoản:

1. Xác định các account ID liên quan.
2. Luôn khóa theo **thứ tự ID tăng dần**.
3. Kiểm tra đã lấy đủ hai hàng và đủ số dư.
4. Thực hiện debit, credit, ghi transfer.
5. COMMIT ngay khi đơn vị công việc hoàn tất.

Ví dụ:

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

ROLLBACK;
~~~

Một truy vấn lấy khóa theo thứ tự ổn định có thể giúp giảm deadlock trong thiết kế này, nhưng **không bảo đảm mọi loại deadlock biến mất**: transaction có thể còn đụng nhiều bảng, index, foreign key hoặc đường truy cập khác.

### 14.2. NOWAIT và SKIP LOCKED không phải phép màu

PostgreSQL có các dạng:

~~~sql
SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

Nếu không lấy được row lock ngay, lệnh có thể báo lỗi thay vì chờ.

~~~sql
SELECT account_id
FROM tx_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

Có thể bỏ qua hàng đang khóa. `SKIP LOCKED` phù hợp cho **queue/worker tranh việc** trong một số thiết kế, **không** phù hợp nếu chuyển tiền bắt buộc phải lấy đúng cả hai tài khoản. Bỏ qua hàng mục tiêu có thể biến giao dịch bắt buộc thành thao tác thiếu dữ liệu.

---

## 15. Xây dựng giao dịch chuyển tiền có kiểm soát

Mục tiêu: từ tài khoản 1 chuyển 100 sang tài khoản 2 và ghi một bản lịch sử với request key không trùng.

### 15.1. Những ràng buộc đã có ở database

Schema lab quy định:

- `accounts.account_id` là PRIMARY KEY.
- `accounts.balance` không được âm.
- `transfers.amount > 0`.
- `transfers.from_account_id` và `to_account_id` là foreign keys.
- Hai đầu chuyển tiền không được cùng ID.
- `transfers.request_key` là UNIQUE.

Các ràng buộc bảo vệ dữ liệu khi có lỗi ứng dụng, nhưng ứng dụng vẫn cần kiểm tra **số hàng bị tác động** và **kết quả transaction**.

### 15.2. Một giao dịch thực hành

~~~sql
BEGIN;

-- Chọn và khóa 2 account theo một thứ tự ổn định.
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Yêu cầu UPDATE đúng 1 hàng; nếu UPDATE 0 thì ROLLBACK.
UPDATE tx_lab.accounts
SET balance = balance - 100,
    updated_at = now()
WHERE account_id = 1
  AND balance >= 100;

-- Yêu cầu UPDATE đúng 1 hàng; nếu UPDATE 0 thì ROLLBACK.
UPDATE tx_lab.accounts
SET balance = balance + 100,
    updated_at = now()
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (request_key, from_account_id, to_account_id, amount)
VALUES ('lab-transfer-0002', 1, 2, 100);

COMMIT;
~~~

**Quan trọng:** khối SQL trên chỉ nên chạy khi người thực hiện/ứng dụng **đã kiểm tra**:

1. `SELECT FOR UPDATE` trả đủ **hai tài khoản** cần thiết.
2. Debit `UPDATE` trả `UPDATE 1`; `UPDATE 0` nghĩa là không đủ số dư hoặc không tìm thấy tài khoản.
3. Credit `UPDATE` trả `UPDATE 1`.
4. INSERT transfer thành công và request key đúng.

Nếu bất kỳ điều kiện nào không đạt, phải **ROLLBACK ngay**, không tiếp tục COMMIT. Một script gửi tất cả câu lệnh liên tục mà **không kiểm tra số hàng** có thể làm sai nghiệp vụ trong trường hợp debit không khớp nhưng credit vẫn khớp. Trong ứng dụng, các kiểm tra đó là bắt buộc.

### 15.3. Vì sao UPDATE có điều kiện balance >= amount?

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
~~~

Đây là **conditional update**. Nếu số dư dưới 100, PostgreSQL không cập nhật hàng đó, trả `UPDATE 0`. Nhờ điều kiện kiểm tra tại thời điểm UPDATE, thao tác chặt chẽ hơn kiểu đọc trước một số dư ở client rồi cập nhật mà không kiểm tra lại.

Thêm `CHECK(balance >= 0)` giúp chặn số dư âm nếu logic ứng dụng thiếu điều kiện. Tuy nhiên CHECK chỉ chặn giá trị âm; nó không tự hủy những cập nhật khác trong transaction khi debit trả 0 **mà không có lỗi**. Đó là lý do ứng dụng phải kiểm tra affected rows rồi quyết định rollback.

### 15.4. Kiểm tra request idempotent

~~~sql
SELECT transfer_id, request_key,
       from_account_id, to_account_id, amount
FROM tx_lab.transfers
WHERE request_key = 'lab-transfer-0002';
~~~

Đừng tái sử dụng `request_key` cho một yêu cầu nghiệp vụ mới. Nếu client retry cùng yêu cầu sau timeout, cần tra transaction có request key đó và so đúng từ/đến/số tiền, thay vì tự động chuyển thêm lần nữa.

### 15.5. Tách giao dịch nghiệp vụ với xử lý phía client

Ranh giới an toàn:

~~~text
BEGIN
  ├─ Khóa các account cần thiết
  ├─ Kiểm tra số dư và sự tồn tại
  ├─ Debit, kiểm tra đúng một hàng
  ├─ Credit, kiểm tra đúng một hàng
  ├─ Ghi record request_key UNIQUE
  └─ COMMIT nếu tất cả bước hợp lệ

Bất kỳ bước nào thất bại ──> ROLLBACK
~~~

Không cần commit giữa debit và credit. Làm như vậy sẽ phá nguyên tử của chuyển tiền.

---

## 16. SQLSTATE và cách phân loại lỗi transaction

PostgreSQL cung cấp SQLSTATE giúp ứng dụng nhận biết loại lỗi thay vì chỉ so chuỗi thông báo có thể thay đổi ngôn ngữ.

| SQLSTATE | Ý nghĩa phổ biến | Hướng xử lý |
|---|---|---|
| `25P02` | Transaction đã aborted, lệnh sau bị từ chối | `ROLLBACK` hoặc rollback về savepoint hợp lệ |
| `23505` | Vi phạm UNIQUE | Phân biệt request trùng với lỗi dữ liệu; kiểm tra tính idempotent |
| `23503` | Vi phạm FOREIGN KEY | Kiểm tra tài khoản/thực thể tham chiếu |
| `23514` | Vi phạm CHECK | Dữ liệu không thỏa ràng buộc |
| `40001` | Serialization failure | Retry **toàn transaction** nếu phù hợp |
| `40P01` | Deadlock detected | ROLLBACK, retry toàn transaction với giới hạn |
| `55P03` | Lock not available/lock timeout | Xử lý chờ lock, cân nhắc retry hoặc báo bận |
| `57014` | Query canceled, bao gồm statement timeout | ROLLBACK transaction bị lỗi; xem chi phí và timeout |

### 16.1. Không retry mọi lỗi

Một `23514` do số dư âm không biến thành hợp lệ chỉ nhờ chạy lại, trong khi `40001` có thể thành công khi transaction được tính lại trên snapshot mới.

Viết chính sách riêng cho:

- **Retryable concurrency errors:** serialization failure, deadlock, một số timeout tùy nghiệp vụ.
- **Business validation errors:** không đủ số dư, request trùng với payload khác, thiếu tài khoản.
- **Infrastructure/connection errors:** có thể không biết COMMIT đã thành công hay chưa.

### 16.2. Retry phải có giới hạn

Nếu retry vô hạn khi hệ thống quá tải, bạn có thể làm tăng tranh chấp và chi phí. Cần:

1. Giới hạn số lần.
2. Dùng backoff/jitter phù hợp.
3. Tính lại mọi quyết định phụ thuộc dữ liệu trong transaction mới.
4. Giữ đúng request key để tránh hiệu ứng nghiệp vụ lặp.
5. Ghi log và giám sát tỷ lệ lỗi, thay vì che giấu sự cố.

### 16.3. COMMIT có thể thất bại

Ngay cả khi các statement trước COMMIT không báo lỗi, commit có thể bị từ chối vì:

- Một ràng buộc DEFERRABLE chỉ kiểm tra cuối transaction.
- Serialization conflict trong transaction SERIALIZABLE.
- Sự cố I/O/cấu hình/hạ tầng.

Chỉ thông báo cho caller "đã hoàn thành" khi đã nhận được kết quả commit phù hợp, hoặc khi đã xử lý trạng thái **không chắc chắn** bằng cơ chế đối soát.

---

## 17. Khi mất kết nối đúng lúc COMMIT

Đây là tình huống quan trọng trong hệ thống thực:

~~~text
Client                            PostgreSQL
  |                                  |
  |------------ COMMIT ------------->|
  |                                  |  Commit có thể đã hoàn tất
  X  mất mạng trước khi nhận phản hồi|
  |                                  |
  ?  Không biết kết quả cuối cùng    |
~~~

Nếu client **không nhận được phản hồi COMMIT**, không thể khẳng định giao dịch chắc chắn đã rollback. Có thể:

1. PostgreSQL chưa xử lý commit và giao dịch bị hủy khi connection mất.
2. PostgreSQL đã commit thành công, nhưng phản hồi bị mất.
3. Tình huống hạ tầng khác cần được xác minh theo cơ chế vận hành.

### 17.1. Không tự động chạy lại mù quáng

Với chuyển tiền, retry "chuyển tiếp 100" bằng một request mới có thể **chuyển hai lần**.

Thay vào đó, thiết kế một **idempotency key/request_key** do client gắn cho yêu cầu nghiệp vụ. Sau khi kết nối lại:

~~~sql
SELECT transfer_id, from_account_id, to_account_id, amount
FROM tx_lab.transfers
WHERE request_key = 'lab-transfer-0002';
~~~

Nếu đã có và payload khớp, có cơ sở xác nhận yêu cầu đã được ghi. Nếu không có, cần xác minh trạng thái transaction/retry theo giao thức idempotent và tính đến replication lag, failover hoặc các loại side effect khác; không suy ra chỉ từ một SELECT trên replica có thể đang trễ.

### 17.2. UNIQUE request_key là một phần của thiết kế, không phải tất cả

Ràng buộc UNIQUE chống **hai record cùng key** trong bảng; nhưng cần đặt **toàn bộ thay đổi số dư và record key trong cùng transaction**, và xử lý conflict đúng cách. Nếu phát hiện trùng key sau khi đã thay đổi số dư trong transaction, lỗi UNIQUE có thể khiến transaction bị aborted và rollback những thay đổi đó.

Nếu hệ thống phải phục vụ retry đồng thời, nên thiết kế việc đăng ký request/claim key ngay trong transaction với trạng thái rõ ràng, xử lý chờ/khóa đúng và xác nhận kết quả. Đừng chỉ dựa vào check-then-insert không có UNIQUE vì hai request đồng thời có thể cùng thấy "chưa có".

---

## 18. Transaction và các hệ thống ngoài PostgreSQL

Giao dịch database **không tự bao gồm** những thao tác ngoài PostgreSQL như:

- Gửi email/SMS.
- Gọi API thanh toán từ xa.
- Ghi file vào object storage.
- Đẩy sự kiện vào message broker.
- Xóa hoặc sửa dữ liệu ở database khác.

### 18.1. Tại sao gửi email trước COMMIT có thể sai?

~~~text
BEGIN
  UPDATE đơn hàng → status = PAID
  GỬI EMAIL "Đã thanh toán!"
  UPDATE khác gặp lỗi
ROLLBACK
~~~

Email đã được gửi nhưng dữ liệu đơn hàng đã rollback; người dùng nhận thông báo sai.

### 18.2. Transactional outbox (mẫu ý tưởng)

Một mẫu thiết kế thường dùng:

~~~text
BEGIN
  Cập nhật dữ liệu nghiệp vụ
  INSERT outbox event cùng transaction
COMMIT
          |
          v
Worker độc lập đọc outbox đã commit
          |
          v
Gửi message/email; đánh dấu processed với retry/idempotency
~~~

Ưu điểm: record outbox và trạng thái DB được commit/rollback **cùng nhau**. Nhưng hệ thống gửi ngoài vẫn cần cơ chế **at-least-once/idempotency**, deduplication hoặc protocol khác để tránh xử lý lặp.

### 18.3. Không nhầm database transaction với distributed transaction

`BEGIN` trên một connection PostgreSQL không mở transaction nguyên tử trên mọi dịch vụ. PostgreSQL có các cơ chế two-phase commit (`PREPARE TRANSACTION`, `COMMIT PREPARED`) khi được cấu hình, nhưng đó là một chủ đề quản trị và điều phối riêng, có rủi ro giữ prepared transactions/locks nếu không hoàn tất. Không tự dùng 2PC để giải quyết mọi workflow microservices.

---

## 19. Ví dụ JDBC quản lý transaction trong ứng dụng Java

Khi kết nối qua JDBC, một cách phổ biến là **một connection cho cả đơn vị nghiệp vụ**, tắt autocommit và gọi commit/rollback qua API. Không phải tự gửi `BEGIN` ở mỗi PreparedStatement.

### 19.1. Ví dụ minh họa kiểm tra số hàng

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            int fromAccountId,
            int toAccountId,
            BigDecimal amount,
            String requestKey) throws SQLException {

        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException("Tài khoản nguồn và đích trùng nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        if (requestKey == null || requestKey.isBlank()) {
            throw new IllegalArgumentException("Thiếu requestKey");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // Lock đúng hai tài khoản, theo thứ tự ID tăng dần.
                int locked = 0;
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT account_id FROM tx_lab.accounts " +
                        "WHERE account_id IN (?, ?) " +
                        "ORDER BY account_id FOR UPDATE")) {
                    ps.setInt(1, fromAccountId);
                    ps.setInt(2, toAccountId);
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            locked++;
                        }
                    }
                }
                if (locked != 2) {
                    throw new SQLException("Thiếu tài khoản chuyển tiền");
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE tx_lab.accounts " +
                        "SET balance = balance - ?, updated_at = now() " +
                        "WHERE account_id = ? AND balance >= ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setInt(2, fromAccountId);
                    ps.setBigDecimal(3, amount);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Không đủ số dư");
                    }
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE tx_lab.accounts " +
                        "SET balance = balance + ?, updated_at = now() " +
                        "WHERE account_id = ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setInt(2, toAccountId);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Không tìm thấy tài khoản đích");
                    }
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO tx_lab.transfers " +
                        "(request_key, from_account_id, to_account_id, amount) " +
                        "VALUES (?, ?, ?, ?)")) {
                    ps.setString(1, requestKey);
                    ps.setInt(2, fromAccountId);
                    ps.setInt(3, toAccountId);
                    ps.setBigDecimal(4, amount);
                    ps.executeUpdate();
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Chỉ trả connection về trạng thái hợp lệ theo chính sách pool.
                connection.setAutoCommit(previousAutoCommit);
            }
        }
    }
}
~~~

### 19.2. Ý nghĩa các bước

- `setAutoCommit(false)` để một loạt SQL trở thành một transaction do API quản lý.
- `SELECT ... FOR UPDATE` khóa các tài khoản theo thứ tự ID.
- `executeUpdate() == 1` xác nhận mỗi thay đổi chỉ tác động đúng một hàng.
- `balance >= amount` chặn trừ vượt số dư tại chính câu UPDATE.
- `INSERT` ghi request key trong cùng transaction.
- `commit()` chỉ chạy sau khi tất cả điều kiện thành công.
- Trong catch, `rollback()` hủy những thay đổi chưa commit.
- `PreparedStatement` bind tham số, tránh ghép input không tin cậy vào chuỗi SQL.

**Giới hạn ví dụ:** đây là mẫu giáo dục cho một transaction, **không phải triển khai chuyển tiền production hoàn chỉnh**. Nó chưa xử lý toàn bộ chiến lược idempotency khi nhiều retry đồng thời, chuyển đổi exception nghiệp vụ, timeout/SQLSTATE, trạng thái commit không chắc chắn, outbox, reconciliation hay vận hành pool khi rollback/restore state lỗi.

### 19.3. Cẩn thận trong finally

Một số JDBC driver coi việc chuyển autocommit từ `false` sang `true` khi transaction vẫn còn mở là hành động kết thúc transaction. Trong ví dụ bình thường, `commit()` hoặc `rollback()` đã chạy trước khi khôi phục.

Nhưng **nếu rollback thất bại do lỗi kết nối**, không được đơn giản giả định connection an toàn để trả về pool. Triển khai production cần chính sách **evict/invalidate connection lỗi** của pool và không để bước khôi phục trạng thái che mất exception gốc. Framework transaction manager thường xử lý phần này; tránh tự xây trùng với cơ chế đang có.

### 19.4. Không lấy hai connection cho một giao dịch

Sai về mặt ranh giới transaction:

~~~text
connA.execute("UPDATE tài khoản nguồn")
connB.execute("UPDATE tài khoản đích")
connA.commit()
connB.commit()
~~~

Hai commit độc lập có thể thành công/thất bại khác nhau. Một transaction PostgreSQL phải sử dụng **cùng connection** từ lúc bắt đầu đến khi kết thúc.

---

## 20. Transaction trong ORM/framework và connection pool

### 20.1. Một request có thể sử dụng nhiều transaction

Trong ứng dụng web:

~~~text
HTTP request
  |
  +-- Kiểm tra input, xác thực (không cần giữ DB transaction lâu)
  |
  +-- Lấy connection từ pool
  |     BEGIN / setAutoCommit(false)
  |     SELECT, UPDATE, INSERT
  |     COMMIT hoặc ROLLBACK
  |   Trả connection về pool
  |
  +-- Trả response hoặc phát công việc sau commit
~~~

Transaction nên bao đúng **đơn vị database** cần nguyên tử; không nên giữ trong lúc chờ người dùng nhấp nút, gọi mạng ngoài chậm hoặc xử lý CPU kéo dài.

### 20.2. Framework annotation không phải phép màu

Một annotation như `@Transactional` trong Spring (nếu có trong stack) phụ thuộc proxy, propagation, exception rules, cấu hình transaction manager và nguồn kết nối. Ví dụ self-invocation hoặc ngoại lệ bị catch/nuốt có thể làm rollback không như tác giả tưởng. Trong ứng dụng cụ thể, cần kiểm tra cách framework thực sự thiết lập transaction và điều kiện rollback.

### 20.3. Trả connection về pool trong trạng thái aborted

Nếu request gặp lỗi SQLSTATE 25P02 rồi bỏ qua rollback, backend còn trong transaction aborted. Connection kế tiếp có thể gặp lỗi liên tiếp. Pool hoặc transaction manager cần chủ động **rollback/reset connection** trước khi tái sử dụng.

### 20.4. Transaction không đi theo thread một cách thần kỳ

Một transaction không tự lan sang thread khác, event handler khác hoặc service khác nếu công nghệ/framework không có cơ chế truyền context/connection phù hợp. Đừng chạy một phần nghiệp vụ trên thread khác rồi tin nó nằm trong cùng transaction của request gốc.

---

## 21. Timeout và giao dịch bị bỏ quên

### 21.1. lock_timeout: giới hạn chờ khóa

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SET LOCAL` có hiệu lực **trong transaction hiện tại**, hữu ích để tránh thay đổi cấu hình phiên lâu dài trong connection pool.

### 21.2. statement_timeout: giới hạn thời gian câu lệnh

~~~sql
BEGIN;
SET LOCAL statement_timeout = '5s';

SELECT SUM(balance)
FROM tx_lab.accounts;

ROLLBACK;
~~~

Timeout hủy **statement** vượt giới hạn và có thể đưa transaction hiện tại vào trạng thái aborted nếu không được xử lý theo savepoint thích hợp. Không đơn giản tiếp tục gửi SQL bình thường sau timeout.

### 21.3. idle_in_transaction_session_timeout

PostgreSQL có cấu hình `idle_in_transaction_session_timeout` nhằm chấm dứt session ở trạng thái **idle in transaction** quá lâu. Đây là lưới an toàn vận hành, không phải thay thế cho code luôn commit/rollback và trả connection đúng cách.

### 21.4. Gợi ý thiết lập theo workload

- Đặt timeout ở tầng ứng dụng cho một request.
- Đặt `lock_timeout` hợp lý nếu tranh chấp cần fail fast.
- Đặt `statement_timeout` cho câu SQL có khả năng chạy quá lâu.
- Giám sát transaction dài và idle in transaction.
- Không cố tăng timeout vô hạn để "giải quyết" một deadlock hay thiếu index.

### 21.5. Các loại thời gian không giống nhau

`statement_timeout` giới hạn thời gian statement, `lock_timeout` giới hạn thời gian chờ lock, còn thời gian sống của transaction gồm cả khoảng giữa các statement (ứng dụng idle). Một transaction có thể có từng SQL rất nhanh nhưng vẫn giữ mở hàng phút vì code chờ mạng ngoài.

---

## 22. Quan sát transaction và khóa trong PostgreSQL

### 22.1. Xem trạng thái của phiên hiện tại

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

`pg_backend_pid()` cho biết PID backend của connection. Khi chính query này đang chạy, `state` có thể là `active`; để thấy session đang `idle in transaction`, thường quan sát từ **connection quản trị khác**.

### 22.2. Xem các transaction mở lâu

Với quyền phù hợp:

~~~sql
SELECT
    pid, usename, application_name, state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type, wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Truy vấn hỗ trợ nhận diện backend có transaction đang mở, nhưng không tự cho biết nó **an toàn để kill**. Quyền xem toàn bộ thông tin các session khác có thể bị giới hạn với user thông thường.

### 22.3. Xem session nào bị chặn bởi PID nào

~~~sql
SELECT
    a.pid AS blocked_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
~~~

`pg_blocking_pids` giúp nhìn các backend đang chặn khóa của một PID. Nếu xem các session trong production, cần quyền truy cập, xử lý dữ liệu query nhạy cảm và thận trọng trước thao tác cancel/terminate.

### 22.4. pg_locks

~~~sql
SELECT
    pid, locktype, mode, granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
~~~

Một số lock không gắn relation cụ thể (ví dụ lock transaction ID), nên `relation_name` có thể NULL. Không tự suy luận từ một dòng `pg_locks` rằng toàn bộ hệ thống bị chặn; cần đối chiếu backend và query.

### 22.5. Transaction mở lâu ảnh hưởng vacuum

Một transaction sống lâu có thể giữ snapshot cũ hoặc làm trì hoãn việc PostgreSQL dọn các tuple version không còn cần thiết, gây phình dữ liệu, tăng công việc VACUUM hoặc chậm bảo trì. Ngay cả session "không làm gì" nhưng `idle in transaction` vẫn có thể gây tác động. Vì vậy vòng đời giao dịch là **vấn đề vận hành**, không chỉ đúng/sai của dữ liệu.

---

## 23. psql và script migration

### 23.1. psql mặc định thực thi từng lệnh độc lập

Nếu không mở transaction tường minh, `psql` thường ở autocommit mode, mỗi statement được commit riêng khi thành công. Để chạy các thay đổi cần nguyên tử:

~~~sql
BEGIN;
ALTER TABLE tx_lab.accounts
    ADD COLUMN IF NOT EXISTS description TEXT;
UPDATE tx_lab.accounts
SET description = 'lab account'
WHERE description IS NULL;
COMMIT;
~~~

Đây là ví dụ migration lab; nếu chỉ muốn xem có thể rollback DDL thì thay `COMMIT` bằng `ROLLBACK`.

### 23.2. Chạy file psql trong một transaction

`psql` có chế độ như:

~~~bash
psql -X --set=ON_ERROR_STOP=1 --single-transaction --file=migration.sql
~~~

Trong ngữ cảnh thích hợp, `--single-transaction` bọc các lệnh file bằng một transaction. Tuy nhiên:

- File không nên tự chứa các lệnh giao dịch xung đột với cơ chế bọc.
- File không được chứa những lệnh PostgreSQL **không cho chạy trong transaction block**, ví dụ `CREATE DATABASE` hoặc `CREATE INDEX CONCURRENTLY`.
- `ON_ERROR_STOP` giúp dừng script khi có lỗi thay vì âm thầm đi tiếp; vẫn phải kiểm tra exit status và trạng thái deploy.
- Không dùng trên production khi chưa xác định loại DDL, khóa, thời gian và phương án rollback.

### 23.3. Transaction cho seed/test

Một kỹ thuật thực hành:

~~~sql
BEGIN;

INSERT INTO tx_lab.accounts (account_id, account_name, balance)
VALUES (99, 'Tài khoản thử', 123);

SELECT *
FROM tx_lab.accounts
WHERE account_id = 99;

ROLLBACK;
~~~

Kết thúc ROLLBACK giúp không để lại tài khoản test. Nhưng **sequence/identity allocation** không nhất thiết quay lui theo ROLLBACK. Nếu INSERT vào bảng dùng `GENERATED ... AS IDENTITY` hoặc `SERIAL`, bạn có thể quan sát **khoảng trống ID** sau transaction rollback; đừng dùng tính liên tục của ID làm invariant nghiệp vụ.

---

## 24. Các sai lầm phổ biến với transaction

| Sai lầm | Rủi ro | Cách khắc phục |
|---|---|---|
| Hai UPDATE autocommit nhưng tưởng cùng một đơn vị | Một UPDATE commit, cái kia lỗi | Dùng một transaction trên cùng connection |
| Quên COMMIT/ROLLBACK | Khóa/snapshot giữ lâu, backend idle in transaction | Kết thúc trong mọi nhánh code |
| Bắt exception rồi bỏ qua | Connection còn aborted, SQLSTATE 25P02 | Rollback hoặc savepoint hợp lệ |
| Gửi COMMIT sau SQL lỗi và coi là thành công | Transaction có thể rollback | Kiểm tra kết quả từng bước và commit |
| Không kiểm tra `UPDATE 0` | Credit có thể chạy dù debit không xảy ra | Kiểm tra affected rows, rollback khi sai |
| Kiểm tra số dư ngoài transaction rồi cập nhật | Race, số dư đọc đã cũ | Khóa/conditional update phù hợp |
| Thay đổi dữ liệu ở hai connection khác nhau | Không nguyên tử | Dùng một connection mỗi transaction |
| Nói nested BEGIN là nested transaction | Hiểu sai ranh giới commit | Dùng SAVEPOINT |
| Dùng SAVEPOINT để "commit một phần" | Phần đó vẫn rollback khi transaction ngoài rollback | Hiểu RELEASE không phải COMMIT |
| Giữ transaction khi gọi API chậm | Lock và snapshot kéo dài | Outbox hoặc tách side effect sau commit |
| Retry mọi SQLSTATE | Che lỗi nghiệp vụ, gây tải | Phân loại retryable/nonretryable |
| Retry riêng câu UPDATE cuối sau 40001 | Dựa trên dữ liệu cũ, sai quyết định | Retry toàn transaction |
| Mất phản hồi COMMIT rồi retry bằng request mới | Có thể nhân đôi chuyển tiền | Idempotency key và đối soát |
| Tin UNIQUE đủ xử lý idempotency | Không xác nhận payload/outcome | Thiết kế trạng thái request và reconciliation |
| Dùng READ COMMITTED mà tin snapshot cố định cả transaction | Hai SELECT thấy commit mới | Chọn isolation phù hợp |
| Cho rằng SERIALIZABLE không thể lỗi | Transaction bị hủy do xung đột | Có retry policy giới hạn |
| Lock hai hàng ngược thứ tự | Deadlock | Thứ tự khóa ổn định |
| Dùng SKIP LOCKED cho tài khoản bắt buộc | Bỏ qua dòng cần cập nhật | Chỉ dùng cho workload queue phù hợp |
| Bao CREATE INDEX CONCURRENTLY trong BEGIN | PostgreSQL từ chối | Chạy theo quy tắc quản trị riêng |
| Không giám sát idle in transaction | Bloat, nghẽn lock, chậm VACUUM | pg_stat_activity/timeout/code cleanup |
| Nghĩ COMMIT đã gửi nghĩa là thành công | Mất kết nối, kết quả không xác định | Chờ ack hoặc đối soát theo request key |
| Dùng transaction DB để bảo đảm email gửi đúng một lần | Side effect ngoài DB không rollback | Outbox và consumer idempotent |

---

## 25. Checklist thiết kế vòng đời transaction

~~~mermaid
flowchart TD
    A["Đơn vị nghiệp vụ cần nguyên tử"] --> B["Lấy một connection"]
    B --> C["BEGIN / setAutoCommit(false)"]
    C --> D["Đọc và khóa dữ liệu cần thiết"]
    D --> E["Kiểm tra điều kiện nghiệp vụ"]
    E --> F{"Điều kiện hợp lệ?"}
    F -- "Không" --> G["ROLLBACK"]
    F -- "Có" --> H["Ghi UPDATE/INSERT"]
    H --> I{"Mọi SQL và row count đều hợp lệ?"}
    I -- "Không" --> G
    I -- "Có" --> J["COMMIT"]
    J --> K{"Có xác nhận thành công?"}
    K -- "Có" --> L["Trả kết quả thành công"]
    K -- "Báo lỗi rõ ràng" --> M["Rollback / retry nếu thích hợp"]
    K -- "Mất kết nối, outcome không chắc" --> N["Đối soát bằng request key"]
    G --> O["Đóng/reset connection"]
    L --> O
    M --> O
    N --> O
~~~

Trước khi đưa vào môi trường thật, trả lời:

1. Một transaction gồm những SQL nào, và **khi nào** bắt đầu/kết thúc?
2. Mỗi SQL có yêu cầu số hàng bị tác động chính xác không?
3. Có cần bảo vệ dữ liệu bằng UNIQUE, CHECK, FK, trigger hay conditional update?
4. Có tranh chấp trên những hàng nào? Các khóa được lấy theo thứ tự ổn định không?
5. Mức isolation nào phù hợp? Có khả năng `40001` hay `40P01` không?
6. Có `SAVEPOINT` vì lỗi phụ được phép bỏ qua, hay phải hủy toàn bộ?
7. Có dùng cùng một connection suốt đơn vị nghiệp vụ không?
8. Có gọi hệ thống ngoài khi transaction chưa kết thúc không?
9. Có request key/idempotency để xử lý commit outcome không chắc chắn không?
10. Có timeout và giám sát `idle in transaction` không?
11. Có trả connection về pool sạch trạng thái không?
12. Có test mất kết nối, duplicate request, insufficient funds và concurrent updates không?

---

## 26. Bài tập thực hành

Sử dụng `tx_lab.accounts` và `tx_lab.transfers` trong phần 3. **Không chạy đồng thời các bài làm thay đổi dữ liệu trên cùng database lab**, vì một bài commit có thể làm thay đổi số dư mà bài sau đang giả định. Khi cần chỉ thử rồi bỏ thay đổi, kết thúc bằng `ROLLBACK`.

### Bài 1 — Xác định ranh giới transaction

Một chương trình ở autocommit mode thực hiện:

~~~sql
UPDATE tx_lab.accounts SET balance = balance + 10 WHERE account_id = 1;
UPDATE tx_lab.accounts SET balance = balance - 10 WHERE account_id = 2;
~~~

Nếu UPDATE đầu thành công nhưng UPDATE sau lỗi, điều gì xảy ra? Viết lại để cả hai thay đổi thành **một đơn vị nguyên tử**.

### Bài 2 — Thử thay đổi không giữ lại

Viết SQL tăng 100 vào tài khoản 3, xem số dư trong transaction, sau đó **hủy** thay đổi. Dùng một SELECT sau đó chứng minh số dư không giữ phần +100.

### Bài 3 — COMMIT và ROLLBACK sau commit

Nếu một UPDATE đã COMMIT thành công, liệu gọi `ROLLBACK` trong transaction **mới** có hủy UPDATE cũ không? Giải thích.

### Bài 4 — Transaction bị aborted

Viết kịch bản làm `CHECK(balance >= 0)` thất bại. Sau khi PostgreSQL báo lỗi, vì sao `SELECT` tiếp theo có thể trả `25P02`? Khắc phục thế nào?

### Bài 5 — SAVEPOINT

Viết transaction:

1. Tăng A thêm 10.
2. Tạo savepoint `s1`.
3. Tăng B thêm 20.
4. Rollback về `s1`.
5. Kiểm tra A còn thay đổi trong transaction, B thì không.
6. Rollback toàn transaction để trả dữ liệu lab về trạng thái cũ.

### Bài 6 — RELEASE SAVEPOINT

`RELEASE SAVEPOINT s1` có làm thay đổi sau `s1` bền vững không? Nếu sau đó transaction ngoài ROLLBACK thì điều gì xảy ra?

### Bài 7 — Nested BEGIN

Khi đã `BEGIN`, gọi tiếp `BEGIN` có tạo một transaction con thật sự trong PostgreSQL không? Lệnh nào dùng để đánh dấu một phần có thể hoàn tác?

### Bài 8 — Hai phiên đọc dữ liệu chưa commit

Phiên A tăng A thêm 77 và chưa commit. Phiên B ở READ COMMITTED chạy `SELECT balance`. Phiên B có thấy phần +77 không? Điều gì khác khi A COMMIT rồi B chạy một SELECT mới?

### Bài 9 — Chờ khóa

Viết hai đoạn SQL cho hai phiên A/B để A UPDATE account 1 chưa commit, B dùng `SET LOCAL lock_timeout = '2s'` rồi cố UPDATE cùng account. Sau timeout, phải làm gì ở cả hai phiên để lab trở lại bình thường?

### Bài 10 — Isolation mức mặc định

Ở READ COMMITTED, một transaction chạy SELECT số dư hai lần, trong lúc đó transaction khác commit số dư mới. Hai SELECT có chắc giống nhau không? So sánh với REPEATABLE READ.

### Bài 11 — READ UNCOMMITTED

PostgreSQL có cho một transaction READ UNCOMMITTED đọc dirty writes từ transaction chưa commit không? Nêu hành vi thực tế.

### Bài 12 — SERIALIZABLE

Truy vấn có thể báo `SQLSTATE 40001` ở đâu? Khi bị lỗi đó, nên retry **câu UPDATE cuối** hay **toàn transaction**?

### Bài 13 — Kiểm tra số dư

Viết conditional update để trừ 200 từ tài khoản 1 **chỉ khi số dư còn ít nhất 200**. Nếu lệnh trả `UPDATE 0`, ứng dụng xử lý gì khi còn đang ở transaction chuyển tiền?

### Bài 14 — Ghi chuyển tiền

Nêu thứ tự SQL/kiểm tra bắt buộc để chuyển 100 từ A sang B và ghi `request_key` trong cùng transaction. Tại sao không COMMIT ngay sau khi trừ A?

### Bài 15 — Mất tài khoản đích

Trong transaction chuyển tiền, debit account 1 thành công nhưng credit account 999 trả `UPDATE 0`. Lệnh UPDATE 0 có tự tạo SQL error không? Phải làm gì để không mất tiền?

### Bài 16 — Request trùng

Một request `request_key='payment-42'` đã commit. Nếu gửi lại INSERT cùng key, ràng buộc nào bị kích hoạt? Vì sao client không nên tạo `request_key` mới rồi chuyển tiền lại?

### Bài 17 — Mất mạng lúc COMMIT

Client đã gửi COMMIT nhưng socket đóng trước khi nhận phản hồi. Có được kết luận giao dịch chắc chắn rollback không? Đề xuất cách đối soát.

### Bài 18 — Deadlock

Transaction A khóa account 1 rồi muốn account 2; transaction B khóa account 2 rồi muốn account 1. Có thể xảy ra hiện tượng gì và SQLSTATE nào? Nêu hai biện pháp thiết kế.

### Bài 19 — DDL transaction

Viết SQL tạo bảng thử, INSERT một dòng rồi ROLLBACK để bảng không còn tồn tại. Nêu hai loại lệnh quản trị không được đặt trong transaction block tương ứng.

### Bài 20 — Transaction trong JDBC

Nêu thứ tự các API cơ bản: lấy connection, `setAutoCommit(false)`, PreparedStatement, kiểm tra row count, `commit()`, `rollback()` và xử lý connection pool.

### Bài 21 — SELECT FOR UPDATE

Viết query khóa đúng hai account `1,2` theo thứ tự ID tăng dần trong transaction. Khi nào nên tránh dùng `SKIP LOCKED` ở bài toán này?

### Bài 22 — Idle in transaction

Một connection đã BEGIN và SELECT, sau đó ứng dụng chờ gọi HTTP API 4 phút mà không COMMIT. Nêu các tác hại tiềm tàng và những cách sửa.

### Bài 23 — Giới hạn thời gian

Viết một transaction có `SET LOCAL lock_timeout='2s'` và `SET LOCAL statement_timeout='5s'`. Hai timeout này khác nhau về phạm vi nào?

### Bài 24 — Quan sát backend

Viết SQL xem PID phiên hiện tại và trạng thái `pg_stat_activity` của chính PID đó. Làm sao tìm PID đang chặn một session khác khi có quyền quan sát?

### Bài 25 — Email và database transaction

Một đơn hàng được UPDATE thành `PAID`, ứng dụng gửi email, rồi SQL tiếp theo thất bại và ROLLBACK. Vì sao email đã gửi không tự biến mất? Nêu giải pháp kiến trúc giảm tình trạng không nhất quán.

### Bài 26 — Bài tổng hợp

Thiết kế một quy trình chuyển tiền trong PostgreSQL bảo đảm:

- Không có số dư âm.
- Không ghi credit khi debit không diễn ra.
- Không ghi cùng `request_key` hai lần.
- Tránh deadlock ở cặp tài khoản.
- Có thể phục hồi khi gặp SQLSTATE 40001/40P01.
- Không chuyển tiền hai lần nếu client mất phản hồi COMMIT.
- Không trả connection còn trong trạng thái aborted vào pool.

Trình bày ranh giới transaction, điều kiện kiểm tra, kỹ thuật khóa, rollback, retry và đối soát.

---

## 27. Gợi ý lời giải

### Bài 1

Ở autocommit, câu đầu có thể **đã commit** dù câu thứ hai lỗi. Để xử lý như một đơn vị:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance - 10
WHERE account_id = 2 AND balance >= 10;

-- Ứng dụng xác nhận cả hai lệnh tác động đúng một hàng.
-- Nếu không đúng, phát ROLLBACK thay vì COMMIT.
ROLLBACK;
~~~

Ví dụ kết thúc ROLLBACK để không thay đổi lab. Trong code thực, khi tất cả điều kiện hợp lệ, dùng COMMIT; nếu bất kỳ bước nào không hợp lệ, rollback.

### Bài 2

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 3;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
ROLLBACK;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
~~~

SELECT trong transaction thấy +100; SELECT sau rollback trở về số dư trước transaction.

### Bài 3

Không. `ROLLBACK` chỉ hủy thay đổi **chưa được commit của transaction hiện tại**; transaction cũ đã hoàn tất không được "undo" bằng ROLLBACK của một transaction mới. Muốn đảo một thay đổi đã commit phải có **giao dịch bù** phù hợp nghiệp vụ, không giả vờ rằng rollback quay ngược lịch sử.

### Bài 4

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 3;
-- Vi phạm CHECK, transaction bị aborted.
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
-- Có thể báo 25P02.
ROLLBACK;
~~~

Lỗi ban đầu đặt transaction vào aborted. Các câu SQL sau không được xử lý bình thường cho đến ROLLBACK hoặc rollback về savepoint hợp lệ.

### Bài 5

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = balance + 10 WHERE account_id = 1;
SAVEPOINT s1;
UPDATE tx_lab.accounts SET balance = balance + 20 WHERE account_id = 2;
ROLLBACK TO SAVEPOINT s1;
SELECT account_id, balance FROM tx_lab.accounts
WHERE account_id IN (1,2) ORDER BY account_id;
ROLLBACK;
~~~

Trong transaction, A giữ +10 từ trước savepoint, B không giữ +20. ROLLBACK cuối hủy cả +10.

### Bài 6

`RELEASE SAVEPOINT` không commit transaction ngoài. Nếu sau RELEASE transaction ngoài ROLLBACK, những thay đổi chưa commit vẫn bị hủy. RELEASE chỉ bỏ dấu mốc rollback một phần.

### Bài 7

Không. `BEGIN` bên trong transaction đã bắt đầu không tạo subtransaction theo kiểu nested transaction. Dùng `SAVEPOINT`, `ROLLBACK TO SAVEPOINT` và `RELEASE SAVEPOINT`.

### Bài 8

Phiên B không thấy +77 chưa commit ở READ COMMITTED. Sau khi A COMMIT, một statement SELECT mới của B ở READ COMMITTED có thể thấy giá trị mới. Nếu B đang REPEATABLE READ và đã có snapshot, nó có thể tiếp tục thấy phiên bản cũ đến khi kết thúc transaction.

### Bài 9

**Phiên A:**

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 1;
-- Để A mở tạm, chuyển sang B.
~~~

**Phiên B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
UPDATE tx_lab.accounts
SET balance = balance + 2
WHERE account_id = 1;
-- Nếu báo timeout:
ROLLBACK;
~~~

**Quay lại A:**

~~~sql
ROLLBACK;
~~~

Không để A mở transaction sau khi quan sát xong.

### Bài 10

Ở READ COMMITTED, mỗi SELECT có thể lấy snapshot mới và thấy commit phát sinh giữa hai câu SQL. Ở REPEATABLE READ, các SELECT thông thường trong transaction dùng snapshot ổn định của transaction sau khi snapshot được thiết lập.

### Bài 11

Không. PostgreSQL xử lý `READ UNCOMMITTED` về cơ bản như `READ COMMITTED` và không cho dirty read thông qua mức cô lập đó.

### Bài 12

`40001` có thể xuất hiện trong quá trình thực thi hoặc khi COMMIT ở Serializable. Phải retry **toàn bộ logic transaction**, gồm những SELECT đã đưa ra quyết định trước đó, với snapshot mới và chính sách retry có giới hạn. Không chỉ retry câu lệnh cuối.

### Bài 13

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance - 200
WHERE account_id = 1 AND balance >= 200;
-- Nếu UPDATE 0 thì ROLLBACK.
ROLLBACK;
~~~

`UPDATE 0` không tự là lỗi SQL, nhưng là **không thỏa điều kiện nghiệp vụ** nếu debit được yêu cầu. Ứng dụng phải hủy transaction, không ghi credit.

### Bài 14

Thứ tự:

1. BEGIN một connection.
2. Khóa hai account theo thứ tự ID ổn định.
3. Kiểm tra có đúng hai hàng.
4. Debit có điều kiện và kiểm tra UPDATE 1.
5. Credit và kiểm tra UPDATE 1.
6. INSERT transfer với request key UNIQUE.
7. COMMIT nếu mọi bước thành công, ngược lại ROLLBACK.

Không COMMIT ngay sau debit vì nếu credit lỗi, tiền đã trừ không được hủy nguyên tử nữa.

### Bài 15

`UPDATE 0` là lệnh SQL **chạy thành công nhưng không khớp hàng**, không tự chuyển transaction sang aborted. Application phải kiểm tra affected rows và **ROLLBACK** toàn transaction để hủy debit.

### Bài 16

UNIQUE trên `transfers.request_key` tạo lỗi `23505` khi INSERT key trùng. Nếu retry cùng yêu cầu, phải tra request key và xác nhận payload/outcome; tự tạo key mới có nguy cơ chuyển tiền thêm một lần.

### Bài 17

Không thể biết từ việc socket mất rằng COMMIT đã rollback. Phải đối soát trên nguồn có dữ liệu đủ mới và kiểm tra `request_key`/kết quả nghiệp vụ; nếu không có, retry theo **cùng idempotency key** với quy trình chống trùng.

### Bài 18

Đó là deadlock, PostgreSQL có thể báo `40P01` và hủy một transaction. Giảm rủi ro bằng **khóa theo thứ tự ID nhất quán** và transaction ngắn; có thể retry toàn transaction với giới hạn sau deadlock.

### Bài 19

~~~sql
BEGIN;
CREATE TABLE tx_lab.rollback_demo (
    id INTEGER PRIMARY KEY
);
INSERT INTO tx_lab.rollback_demo(id) VALUES (1);
ROLLBACK;
~~~

Bảng mới được tạo trong transaction sẽ bị hủy khi rollback. Ví dụ các lệnh cần chạy ngoài transaction block: `CREATE DATABASE` và `CREATE INDEX CONCURRENTLY`.

### Bài 20

Một connection duy nhất:

~~~text
getConnection()
  → setAutoCommit(false)
  → SELECT/UPDATE/INSERT bằng PreparedStatement
  → kiểm tra đủ row count/ràng buộc
  → commit() nếu mọi bước đúng
  → rollback() nếu SQLException/RuntimeException
  → reset/close hoặc invalidate connection theo trạng thái pool
~~~

Không để lỗi khôi phục pool state che exception gốc; khi connection/rollback đã lỗi, loại khỏi pool theo cơ chế phù hợp.

### Bài 21

~~~sql
BEGIN;
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1,2)
ORDER BY account_id
FOR UPDATE;
ROLLBACK;
~~~

`SKIP LOCKED` có thể bỏ qua một trong hai account đang bị khóa; không chấp nhận trong giao dịch bắt buộc phải kiểm tra/cập nhật **đúng hai tài khoản**.

### Bài 22

Transaction chờ HTTP 4 phút có thể giữ khóa, snapshot, làm chậm VACUUM và làm backend ở `idle in transaction`. Sửa bằng cách rút ngắn transaction, không chờ network ngoài trong transaction, timeout phù hợp, outbox khi có side effect cần đồng bộ trạng thái và rollback trong mọi nhánh.

### Bài 23

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;
ROLLBACK;
~~~

`lock_timeout` giới hạn **thời gian chờ lấy khóa**, còn `statement_timeout` giới hạn **thời gian thực hiện một statement** nói chung.

### Bài 24

~~~sql
SELECT pid, state, xact_start, wait_event_type, wait_event
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

Nếu có quyền:

~~~sql
SELECT
    pid AS blocked_pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Không tự terminate backend khi chưa xác định chủ sở hữu/ảnh hưởng.

### Bài 25

COMMIT/ROLLBACK chỉ điều khiển các thay đổi thuộc **transaction database**. Email gửi qua hệ thống ngoài không tự quay lui khi database rollback. Dùng **transactional outbox** (ghi event cùng DB transaction, gửi sau commit), consumer retry/idempotency và quy trình đối soát.

### Bài 26

Một thiết kế tổng hợp:

~~~text
Client gửi request_key ổn định
        |
        v
Lấy một connection, BEGIN
        |
        v
Đảm bảo request_key UNIQUE/idempotent
        |
        v
Khóa account theo ID tăng dần
        |
        v
Kiểm tra đủ hai account và số tiền dương
        |
        v
UPDATE debit WHERE balance >= amount
   ├─ UPDATE 0 → ROLLBACK
   └─ UPDATE 1
        |
        v
UPDATE credit, yêu cầu UPDATE 1
   ├─ không đúng → ROLLBACK
   └─ đúng
        |
        v
Ghi transfer/request key, kiểm tra thành công
        |
        v
COMMIT
   ├─ thành công → trả kết quả
   ├─ 40001/40P01 → retry toàn transaction có giới hạn
   └─ kết nối mất khi commit → đối soát request_key trước retry
~~~

Database có CHECK số dư không âm, FK hai account, UNIQUE request key. Trả connection về pool chỉ khi đã kết thúc transaction và reset hợp lệ; nếu connection lỗi nghiêm trọng hoặc rollback không xác nhận được, pool cần discard/invalidate.

Đây là **thiết kế logic**. Với yêu cầu tài chính thật, còn cần ledger bất biến, số dư chính xác, xử lý retry đồng thời, thứ tự lock nhiều tài khoản, audit, reconcile và đảm bảo vận hành tương ứng.

---

## 28. Các tình huống cần nhớ

### 28.1. Một lệnh SQL cũng nằm trong transaction

Autocommit không phải "không có transaction"; nó là **transaction mỗi statement**. Chỉ khi bạn cần nhiều statement thành một đơn vị, mới cần kiểm soát ranh giới rõ bằng BEGIN/COMMIT hoặc API giao dịch.

### 28.2. Một transaction không được đảm bảo thành công chỉ vì không có lỗi trước COMMIT

Constraint deferred, serialization conflict, sự cố I/O hoặc mất kết nối có thể ảnh hưởng đến kết quả cuối. Luôn có nhánh lỗi khi commit.

### 28.3. ROLLBACK chỉ xử lý thay đổi chưa commit

Không gọi rollback để hủy một sự kiện đã commit hoặc email đã gửi. Việc đảo nghiệp vụ cần **transaction bù** và chính sách audit.

### 28.4. SQL lỗi có thể làm toàn transaction unusable

Sau lỗi, message `25P02` chỉ báo transaction đã aborted; lỗi gốc nằm ở statement trước. Xác định nguyên nhân gốc rồi ROLLBACK hoặc quay về savepoint hợp lệ.

### 28.5. Không ghi "COMMIT thành công" khi chưa biết

Trong lỗi mất socket ngay sau khi gửi COMMIT, kết quả có thể không chắc chắn. Thiết kế phải có request key và cách đối soát đáng tin, không coi timeout là chắc chắn rollback.

### 28.6. Giao dịch càng ngắn càng tốt, nhưng phải đủ nghĩa nghiệp vụ

Cắt transaction thành hai phần có thể giảm thời gian giữ khóa nhưng **phá atomicity** nếu nghiệp vụ bắt buộc cả hai phần cùng thành công. Ngược lại, giữ transaction trong lúc gọi API ngoài kéo dài khóa và rủi ro. Cần định nghĩa phạm vi database atomic cùng kiến trúc outbox/saga khi vượt một database.

---

## 29. Tổng kết

Trong PostgreSQL, **`BEGIN` mở giao dịch tường minh, `COMMIT` xác nhận các thay đổi hợp lệ, `ROLLBACK` hủy những thay đổi chưa commit**. Ba lệnh này tạo ranh giới cho một đơn vị công việc và quyết định thời điểm các thay đổi trở nên có hiệu lực với các transaction khác.

Vòng đời giao dịch phải được hiểu đầy đủ:

- Transaction bắt đầu → thực hiện SQL → **COMMIT** hoặc **ROLLBACK**.
- Nếu một SQL thất bại trong transaction, giao dịch thường chuyển sang **aborted**; `25P02` yêu cầu rollback hoặc quay về savepoint hợp lệ trước khi tiếp tục.
- **SAVEPOINT** hỗ trợ rollback một phần, nhưng `RELEASE SAVEPOINT` không phải commit độc lập.
- PostgreSQL dùng **MVCC**, isolation levels và row locks để phối hợp giao dịch đồng thời. READ COMMITTED không phải SERIALIZABLE, và SERIALIZABLE có thể cần retry.
- Một transaction chỉ thuộc **một connection**. Khi dùng JDBC hoặc connection pool, phải đảm bảo commit/rollback trong mọi nhánh, không trả session bị lỗi về pool.
- Với nghiệp vụ như chuyển tiền, phải kiểm tra **số hàng cập nhật**, constraint, thứ tự khóa, request key và xử lý trường hợp COMMIT không nhận được phản hồi.
- Không giữ transaction mở trong khi chờ gọi mạng ngoài; dùng outbox/idempotency hoặc quy trình phân tán thích hợp nếu cần.
- Theo dõi `pg_stat_activity`, lock waits, timeouts và transaction dài để bảo vệ hệ thống.

Tư duy triển khai vững chắc: **xác định đơn vị nghiệp vụ nguyên tử → lấy một connection → BEGIN → kiểm tra dữ liệu và khóa phù hợp → thực hiện mọi thay đổi với kiểm tra kết quả → COMMIT nếu hoàn toàn hợp lệ, ROLLBACK khi thất bại → xử lý retry/outcome không chắc chắn → giải phóng connection và quan sát vận hành**.
