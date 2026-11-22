# Dirty read, nonrepeatable read, phantom và các bất thường cần phân biệt trong PostgreSQL

Khi có nhiều kết nối cùng đọc và sửa cơ sở dữ liệu, tính đúng của từng câu SQL **không đủ** để bảo đảm tính đúng của toàn bộ nghiệp vụ. Hai yêu cầu có thể cùng kiểm tra tồn kho rồi cùng đặt hàng; một báo cáo có thể đọc số dư ở hai thời điểm khác nhau; hoặc hai nhân viên trực có thể cùng thấy vẫn còn người khác trực và cùng xin nghỉ, khiến cuối cùng không còn ai trực.

Những tình huống đó thuộc nhóm **bất thường đồng thời** (*concurrency anomalies*). Các tên thường gặp là **dirty read**, **nonrepeatable read**, **phantom read**, **lost update**, **read skew**, **write skew** và **serialization anomaly**. Mỗi hiện tượng có nguyên nhân và cách xử lý riêng. Đặc biệt, **PostgreSQL không triển khai mọi mức isolation giống cách mô tả tối thiểu của chuẩn SQL**: `READ UNCOMMITTED` hoạt động như `READ COMMITTED`, còn `REPEATABLE READ` của PostgreSQL ngăn phantom read kiểu truyền thống nhưng vẫn chưa bảo đảm serializability trong mọi tình huống.

Bài học thuộc chương **Giao dịch** của module *Database Engine Relational PostgreSQL*. Sau bài này, bạn sẽ có thể:

- Nhận diện từng hiện tượng bằng lịch xen kẽ của hai transaction T1 và T2.
- Phân biệt **giá trị chưa commit**, **giá trị đã commit nhưng thay đổi giữa các lần đọc**, và **số hàng phù hợp một điều kiện bị thay đổi**.
- Hiểu vai trò của MVCC, snapshot và ba mức isolation thực tế trong PostgreSQL.
- Thực hành các kịch bản bằng hai phiên `psql` độc lập.
- Phân tích lost update, read skew và write skew vốn thường bị nhầm với phantom.
- Biết khi nào dùng constraint, câu lệnh cập nhật nguyên tử, row lock, optimistic locking hoặc `SERIALIZABLE`.
- Thiết kế retry đúng cho `SQLSTATE 40001`, thay vì chỉ lặp lại câu SQL cuối.

> Quy tắc quan trọng: **Isolation level định nghĩa những gì transaction được nhìn thấy và những kết quả đồng thời nào được phép commit; nó không thay thế các bất biến nghiệp vụ, constraint và transaction protocol.**

## 1. Giao dịch và lịch thực thi xen kẽ

Một **transaction** là một nhóm thao tác có ranh giới commit/rollback:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Ví dụ này minh họa chuyển tiền giữa hai tài khoản, giả định bảng `accounts` đã tồn tại. Nếu hai phép UPDATE cùng nằm trong một transaction và transaction rollback, không có phần cập nhật nào được commit.

Nhưng khi T1 đang chạy, T2 cũng có thể đọc hoặc cập nhật dữ liệu. Một lịch xen kẽ có thể là:

~~~text
Thời gian  T1                              T2
---------  ------------------------------  -------------------------
t1         BEGIN
t2         SELECT balance ...
t3                                         BEGIN
t4                                         UPDATE balance ...
t5                                         COMMIT
t6         SELECT balance ...
t7         COMMIT
~~~

Kết quả T1 quan sát tại t2 và t6 phụ thuộc isolation level, snapshot và loại thao tác.

### 1.1. Các ký hiệu sẽ dùng

| Ký hiệu | Ý nghĩa |
|---|---|
| T1, T2 | Hai transaction độc lập |
| R1(X) | T1 đọc giá trị X |
| W2(X) | T2 ghi giá trị X |
| C1, C2 | T1 hoặc T2 commit |
| A1, A2 | T1 hoặc T2 rollback/abort |
| Snapshot | Ảnh chụp logic các phiên bản hàng mà một câu lệnh/giao dịch được nhìn thấy |
| Predicate | Điều kiện chọn tập hàng, ví dụ `WHERE status='confirmed'` |
| Serialization | Kết quả tương đương một cách chạy tuần tự các transaction |

Không cần thuộc lòng ký hiệu, nhưng nên tập mô tả chính xác **ai đọc gì, ai ghi gì, lúc nào commit** trước khi kết luận đã có anomaly.

### 1.2. Isolation khác Atomicity

- **Atomicity**: thao tác trong cùng transaction thành công cùng nhau hoặc rollback cùng nhau.
- **Isolation**: các transaction đồng thời ảnh hưởng đến quan sát và kết quả của nhau như thế nào.
- **Consistency**: các bất biến/constraint cần được giữ, kết hợp với logic đúng của ứng dụng.
- **Durability**: thay đổi đã commit được duy trì theo cơ chế độ bền của hệ thống.

Một transaction atomic vẫn có thể tham gia **write skew** hoặc **lost update** dưới isolation chưa đủ mạnh. Atomicity không tự làm các thao tác đồng thời thành một lịch tuần tự.

## 2. Dirty read: đọc thay đổi chưa commit

**Dirty read** xảy ra khi T1 đọc giá trị mà T2 đã ghi nhưng **T2 chưa commit**. Sau đó T2 có thể rollback, khiến T1 đã hành động dựa trên dữ liệu thực ra chưa từng trở thành dữ liệu đã commit.

Kịch bản khái niệm trong một hệ thống cho phép dirty read:

~~~text
Trạng thái ban đầu: balance = 1000

T2                                T1
--------------------------------  -------------------------------
BEGIN
UPDATE balance = 900
                                  SELECT balance -> 900
                                  T1 ra quyết định dựa trên 900
ROLLBACK

Giá trị đã commit thực tế vẫn là 1000.
~~~

Điểm nhận diện chính là **thời điểm đọc xảy ra trước COMMIT của transaction tạo ra giá trị đó**.

### 2.1. Dirty read nguy hiểm vì sao?

Nếu một tác vụ tính phí, cảnh báo hoặc điều phối kho dựa trên dữ liệu chưa commit, nó có thể thực hiện hành động ngoài đời mà không thể “rollback” cùng database.

Ví dụ:

- T2 đang giảm số dư nhưng sau đó rollback.
- T1 thấy số dư giảm, gửi cảnh báo sai.
- T2 rollback nhưng email cảnh báo đã gửi.

### 2.2. PostgreSQL có dirty read không?

**Không.** PostgreSQL không cho transaction thông thường đọc những phiên bản dữ liệu chưa commit của transaction khác. Điều này đúng **ngay cả khi khai báo `READ UNCOMMITTED`**: PostgreSQL xử lý mức đó như `READ COMMITTED`.

Đây là khác biệt quan trọng giữa **mức tối thiểu chuẩn SQL cho phép** và **hành vi cụ thể của PostgreSQL**.

### 2.3. Đọc thay đổi của chính mình không phải dirty read

Trong một transaction:

~~~sql
BEGIN;

UPDATE accounts
SET balance = 900
WHERE account_id = 1;

SELECT balance
FROM accounts
WHERE account_id = 1;

ROLLBACK;
~~~

T1 thấy thay đổi do **chính T1** thực hiện trước commit. Đó là hành vi bình thường (*read your own writes*), không phải dirty read giữa hai transaction.

## 3. Nonrepeatable read: đọc lại cùng hàng ra giá trị khác

**Nonrepeatable read** xảy ra khi T1 đọc một hàng, T2 commit một thay đổi trên hàng đó, sau đó T1 đọc lại **cùng hàng** trong **cùng transaction** và thấy giá trị khác.

~~~text
Ban đầu: account(1).balance = 1000

T1                                     T2
-------------------------------------  -------------------------
BEGIN
SELECT balance -> 1000
                                       BEGIN
                                       UPDATE balance = 900
                                       COMMIT
SELECT balance -> 900
COMMIT
~~~

Cả hai giá trị mà T1 đọc đều là dữ liệu đã commit tại thời điểm câu lệnh tương ứng. Vì vậy, **nonrepeatable read không phải dirty read**.

### 3.1. Phạm vi “cùng transaction” quan trọng

Nếu T1 đọc một hàng, commit, rồi khởi tạo transaction mới và đọc lại thấy giá trị mới, đó là dữ liệu thay đổi bình thường giữa **hai giao dịch khác nhau**, không phải ví dụ chuẩn của nonrepeatable read.

### 3.2. READ COMMITTED trong PostgreSQL cho phép hiện tượng này

Ở `READ COMMITTED`, mỗi câu lệnh truy vấn thông thường dùng snapshot phù hợp tại **lúc bắt đầu câu lệnh đó**. Hai câu SELECT khác nhau trong cùng transaction có thể thấy hai trạng thái đã commit khác nhau.

### 3.3. REPEATABLE READ của PostgreSQL ngăn nonrepeatable read

Với `REPEATABLE READ`, các lần đọc thông thường trong cùng transaction chia sẻ một snapshot giao dịch ổn định. Nếu T2 commit thay đổi sau khi snapshot của T1 được thiết lập, T1 vẫn thấy phiên bản cũ trong những lần SELECT tiếp theo.

Điều này không có nghĩa T2 bị ngăn sửa hàng hoặc toàn bộ database đứng yên. T2 có thể commit; T1 chỉ có **góc nhìn nhất quán của snapshot**.

## 4. Phantom read: tập hàng phù hợp điều kiện thay đổi

**Phantom read** là trường hợp T1 chạy một truy vấn theo **điều kiện tập hàng**, T2 commit một thay đổi khiến số lượng/thành viên của tập phù hợp thay đổi, sau đó T1 chạy lại truy vấn trong cùng transaction và thấy tập khác.

~~~text
Ban đầu:
  SELECT COUNT(*) FROM bookings
  WHERE room_id = 10 AND status = 'confirmed'
  -> 2

T1                                      T2
--------------------------------------  ----------------------------
BEGIN
COUNT(*) -> 2
                                        BEGIN
                                        INSERT booking phù hợp
                                        COMMIT
COUNT(*) -> 3
COMMIT
~~~

### 4.1. Phantom khác nonrepeatable read thế nào?

- **Nonrepeatable read:** giá trị của một hàng đã đọc thay đổi.
- **Phantom read:** **tập hàng** thỏa một predicate thay đổi do INSERT/DELETE/UPDATE phù hợp.

Ví dụ:

~~~sql
SELECT *
FROM bookings
WHERE room_id = 10
  AND status = 'confirmed';
~~~

Một hàng mới được thêm vào tập sau lần SELECT đầu là phantom.

### 4.2. Phantom không chỉ xuất hiện vì INSERT

Tập hàng có thể đổi vì:

- T2 INSERT hàng mới thỏa predicate.
- T2 DELETE một hàng vốn thỏa predicate.
- T2 UPDATE hàng không thỏa thành thỏa predicate.
- T2 UPDATE hàng đang thỏa thành không thỏa predicate.

Bản chất là **tập kết quả của điều kiện khác đi giữa hai lần đọc**.

### 4.3. PostgreSQL REPEATABLE READ ngăn phantom truyền thống

Trong PostgreSQL, `REPEATABLE READ` là mức snapshot isolation. Hai SELECT theo cùng predicate trong một transaction sẽ không nhìn thấy hàng mới do transaction khác commit sau snapshot.

Điều này **mạnh hơn mức bảo đảm tối thiểu mà chuẩn SQL truyền thống yêu cầu đối với REPEATABLE READ**. Nhưng vẫn **không đủ để loại bỏ mọi serialization anomaly**, đặc biệt là write skew.

## 5. Bảng phân biệt ba hiện tượng cơ bản

| Câu hỏi | Dirty read | Nonrepeatable read | Phantom read |
|---|---|---|---|
| Đọc dữ liệu của transaction khác chưa commit? | Có | Không bắt buộc; điển hình là đã commit | Không bắt buộc; điển hình là đã commit |
| Một hàng đã biết đổi giá trị giữa hai lần đọc? | Không phải đặc điểm chính | Có | Có thể nhưng trọng tâm là tập hàng |
| Tập hàng thỏa WHERE thay đổi? | Không phải đặc điểm chính | Không phải đặc điểm chính | Có |
| Ví dụ | Đọc balance=900 trước khi người ghi rollback | Đọc balance 1000 rồi 900 | COUNT(bookings) từ 2 thành 3 |
| PostgreSQL READ COMMITTED? | Ngăn | Có thể gặp | Có thể gặp |
| PostgreSQL REPEATABLE READ? | Ngăn | Ngăn với đọc snapshot | Ngăn với đọc snapshot |
| PostgreSQL SERIALIZABLE? | Ngăn | Ngăn | Ngăn trong các lịch commit hợp lệ |

**Phantom và nonrepeatable read có thể chồng lấn về cách mô tả khi UPDATE làm thay đổi predicate.** Phân loại để hiểu nguyên nhân và cách kiểm soát, không phải để ép mọi lịch xen kẽ phức tạp vào đúng một tên.

## 6. MVCC: nền tảng cách PostgreSQL cho phép đọc và ghi đồng thời

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)**. Khi cập nhật dữ liệu, hệ thống quản lý các phiên bản hàng phù hợp với trạng thái transaction và snapshot.

Mô hình khái niệm:

~~~text
Một tài khoản, hai phiên bản logic

Version A: balance=1000  [thấy bởi snapshot cũ]
Version B: balance=900   [thấy bởi snapshot mới sau commit]

T1 đã lấy snapshot trước COMMIT của T2 -> thấy A
T3 bắt đầu truy vấn sau COMMIT T2      -> thấy B
~~~

Đây là minh họa ngữ nghĩa; không phải sơ đồ vật lý đầy đủ của heap, transaction IDs, visibility map hay VACUUM.

### 6.1. Snapshot không phải bản sao vật lý của toàn database

PostgreSQL không sao chép toàn bộ dữ liệu vào RAM mỗi lần `BEGIN`. Snapshot là thông tin visibility cho phép xác định những phiên bản hàng nào được transaction/câu lệnh nhìn thấy.

### 6.2. MVCC giúp đọc không mặc định chặn ghi

Một SELECT thông thường thường có thể đọc phiên bản đã commit mà không chờ một transaction khác đang UPDATE cùng hàng.

Ngược lại, các thao tác cập nhật cùng hàng có thể chờ **row locks** và chịu kiểm tra đồng thời khác nhau theo isolation level.

### 6.3. Isolation quyết định phạm vi snapshot

- `READ COMMITTED`: snapshot mới cho từng câu lệnh thông thường.
- `REPEATABLE READ`: snapshot ổn định trong transaction kể từ khi được thiết lập.
- `SERIALIZABLE`: mô hình snapshot với cơ chế phát hiện phụ thuộc nguy hiểm để ngăn các lịch commit không thể tuần tự hóa.

### 6.4. Transaction dài có tác động vận hành

Một transaction giữ snapshot lâu có thể làm PostgreSQL phải giữ lại các phiên bản cũ, ảnh hưởng VACUUM và gây bloat. **REPEATABLE READ không nên bị biến thành transaction mở nhiều giờ chỉ để “giữ kết quả không đổi”.**

## 7. Các isolation level PostgreSQL thực sự hỗ trợ

PostgreSQL chấp nhận bốn tên isolation của SQL nhưng chỉ có **ba kiểu hành vi thực tế quan trọng**:

| Isolation yêu cầu | Hành vi PostgreSQL | Snapshot/đặc điểm chính |
|---|---|---|
| `READ UNCOMMITTED` | Tương đương READ COMMITTED | Không dirty read; snapshot theo câu lệnh |
| `READ COMMITTED` | READ COMMITTED | Có thể nonrepeatable/phantom giữa các câu lệnh |
| `REPEATABLE READ` | Snapshot isolation | Đọc snapshot ổn định; không phantom theo kiểu truyền thống; có thể write skew |
| `SERIALIZABLE` | Serializable Snapshot Isolation (SSI) | Chỉ cho phép transaction commit với kết quả tương đương lịch tuần tự; có thể abort 40001 |

### 7.1. Ma trận hiện tượng

| Hiện tượng | READ UNCOMMITTED trong PG | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|---|
| Dirty read | Không | Không | Không | Không |
| Nonrepeatable read | Có thể | Có thể | Không trong đọc snapshot | Không trong lịch commit hợp lệ |
| Phantom read truyền thống | Có thể | Có thể | Không trong đọc snapshot | Không trong lịch commit hợp lệ |
| Read skew giữa SELECT | Có thể | Có thể | Ngăn bằng snapshot ổn định | Ngăn trong lịch commit hợp lệ |
| Write skew/serialization anomaly | Có thể | Có thể | **Có thể** | Được phát hiện/ngăn bằng abort nếu cần |
| Stale read-modify-write không kiểm soát | Có thể | Có thể | Có kiểm tra xung đột cùng hàng nhưng không thay toàn bộ quy tắc nghiệp vụ | Cần transaction đúng và retry |

Không nên coi ma trận này là cam kết rằng **mọi thao tác** đều tự an toàn chỉ vì isolation cao: constraint, quản lý lỗi, retry và giao thức nhiều bước vẫn quan trọng.

### 7.2. READ COMMITTED là mặc định thường dùng

PostgreSQL mặc định dùng `READ COMMITTED` cho transaction thông thường, trừ khi cấu hình hoặc câu lệnh đã thay đổi.

Kiểm tra:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

`default_transaction_isolation` mô tả mức mặc định của transaction mới theo ngữ cảnh phiên; `transaction_isolation` cho biết mức của transaction hiện tại.

### 7.3. Cài đặt ở đầu transaction

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) FROM some_table;

COMMIT;
~~~

Ví dụ cấu trúc giả định `some_table` tồn tại.

Hoặc:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Các truy vấn thực hiện sau khi đặt isolation.
COMMIT;
~~~

Hãy đặt mức isolation **trước khi chạy các truy vấn dữ liệu** cần cùng snapshot. Không đổi isolation giữa chừng sau khi transaction đã thực hiện thao tác truy vấn/ghi không cho phép thay đổi nữa.

## 8. Chuẩn bị lab với hai phiên psql

Thực hành trên **database PostgreSQL thử nghiệm**, không chạy trên production. Bạn cần **hai kết nối/phiên riêng**, gọi là **Session A (T1)** và **Session B (T2)**. Trong `psql` có thể mở hai terminal kết nối cùng database.

Để tránh xung đột với dữ liệu thật, tạo một schema riêng. Nếu `isolation_lab` đã tồn tại, dùng database thử nghiệm khác hoặc đổi tên schema thay vì xóa dữ liệu không thuộc lab.

### 8.1. Tạo schema và bảng tài khoản

~~~sql
CREATE SCHEMA isolation_lab;

CREATE TABLE isolation_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance NUMERIC(12, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO isolation_lab.accounts (
    account_id, owner_name, balance
)
VALUES
    (1, 'Alice', 1000.00),
    (2, 'Bob',   1000.00);
~~~

### 8.2. Bảng booking để quan sát phantom

~~~sql
CREATE TABLE isolation_lab.bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL,
    booking_day DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'cancelled'))
);
~~~

### 8.3. Bảng tồn kho

~~~sql
CREATE TABLE isolation_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

INSERT INTO isolation_lab.inventory (sku, stock)
VALUES ('BOOK-001', 10);
~~~

### 8.4. Bảng lịch trực cho write skew

~~~sql
CREATE TABLE isolation_lab.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO isolation_lab.on_call (
    doctor_id, doctor_name, on_call
)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE);
~~~

Quy tắc nghiệp vụ giả định: **phải luôn còn ít nhất một bác sĩ trực**. Bảng trên **chưa có constraint nhiều hàng nào bảo đảm quy tắc đó**, có chủ đích để quan sát write skew.

### 8.5. Quy tắc vận hành lab

- Mỗi session mở transaction bằng `BEGIN`; không chạy tất cả bước tuần tự trong một kết nối.
- Theo đúng thứ tự A1 → B1 → A2... của từng ví dụ; chỉ tiếp tục khi bước trước đã hoàn thành.
- Nếu phiên đang chờ lock, để phiên kia COMMIT/ROLLBACK như hướng dẫn.
- Sau mỗi kịch bản, COMMIT hoặc ROLLBACK hết transaction mở.
- Chỉ reset dữ liệu khi không còn transaction thí nghiệm đang sử dụng nó.
- Một số kết quả phụ thuộc thứ tự commit; cố ý giữ interleaving để nhìn thấy hiện tượng.
- Trong công cụ GUI có connection pool, cần đảm bảo Session A/B thực sự là **hai backend connections độc lập**, không phải hai tab dùng chung connection.

## 9. Lab dirty read: PostgreSQL không nhìn thấy ghi chưa commit

Đảm bảo account 1 đang có balance=1000 bằng cách reset **ngoài các transaction thí nghiệm**:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 9.1. Session A / T1: ghi nhưng chưa commit

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

-- Chưa COMMIT hoặc ROLLBACK.
~~~

### 9.2. Session B / T2: đọc khi T1 còn mở

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
~~~

**Kết quả dự kiến:** T2 thấy **1000**, không phải 900. T2 đọc phiên bản đã commit phù hợp snapshot của câu SELECT.

### 9.3. Session A rollback

~~~sql
ROLLBACK;
~~~

### 9.4. Session B đọc lại

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

COMMIT;
~~~

Kết quả tiếp tục là 1000.

### 9.5. Thử READ UNCOMMITTED

Lặp tình huống A ghi 900 chưa commit, nhưng Session B dùng:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

COMMIT;
~~~

PostgreSQL vẫn **không cho dirty read**. Thực tế mức này hoạt động như READ COMMITTED.

**Đừng chuyển isolation xuống READ UNCOMMITTED với kỳ vọng thấy dữ liệu tạm của transaction khác trong PostgreSQL.**

## 10. Lab nonrepeatable read dưới READ COMMITTED

Reset dữ liệu khi không còn transaction mở:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 10.1. Session A / T1 đọc lần đầu

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Kỳ vọng: 1000
~~~

### 10.2. Session B / T2 commit thay đổi

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

### 10.3. Session A / T1 đọc lại

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Kỳ vọng: 900

COMMIT;
~~~

Hai SELECT trong **cùng transaction T1** cho hai giá trị khác nhau. Đây là **nonrepeatable read**.

### 10.4. Có phải T1 đã đọc dữ liệu bẩn?

Không. Giá trị 900 đã được T2 COMMIT trước lần SELECT thứ hai. T1 không đọc dữ liệu chưa commit.

### 10.5. Tại sao một câu SELECT có thể khác câu SELECT tiếp theo?

Vì ở READ COMMITTED, mỗi câu SELECT thông thường thiết lập một snapshot mới phù hợp với các transaction đã commit khi câu lệnh bắt đầu. BEGIN không “đóng băng” dữ liệu cho toàn bộ transaction.

## 11. Lab nonrepeatable read dưới REPEATABLE READ

Reset lại account 1 về 1000 trước khi chạy:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 11.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Kỳ vọng: 1000
~~~

### 11.2. Session B / T2

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

### 11.3. Session A / T1 đọc lại

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Vẫn là 1000 theo snapshot T1.

COMMIT;
~~~

Đọc lặp lại vẫn thấy 1000. Tuy nhiên, **sau khi T1 kết thúc và mở transaction mới**, truy vấn có thể thấy 900.

### 11.4. Snapshot được lấy lúc nào?

Với REPEATABLE READ, snapshot được thiết lập khi transaction thực hiện câu lệnh cần snapshot đầu tiên theo cơ chế PostgreSQL, **không nhất thiết chính xác tại thời điểm gửi BEGIN**. Nếu cần dàn dựng một thí nghiệm, hãy chạy SELECT đầu tiên ở T1 trước khi T2 commit để cố định snapshot mong muốn.

### 11.5. Nếu T1 cố UPDATE chính hàng đã bị T2 thay đổi?

Trong REPEATABLE READ, PostgreSQL có thể từ chối transaction với lỗi dạng:

~~~text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
~~~

Như vậy “T1 đọc được snapshot cũ” **không có nghĩa** T1 được tự ý ghi đè phiên bản mới của cùng hàng rồi vẫn commit bình thường. Đọc MVCC và ghi đồng thời có các quy tắc khác nhau.

## 12. Lab phantom read dưới READ COMMITTED

Đảm bảo không có booking thí nghiệm từ kịch bản trước (chỉ chạy khi hai phiên đã kết thúc transaction):

~~~sql
DELETE FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14';
~~~

### 12.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Kỳ vọng: 0
~~~

### 12.2. Session B / T2

~~~sql
BEGIN;

INSERT INTO isolation_lab.bookings (
    room_id, booking_day, status
)
VALUES (10, DATE '2026-11-14', 'confirmed');

COMMIT;
~~~

### 12.3. Session A / T1 đọc cùng predicate

~~~sql
SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Kỳ vọng: 1

COMMIT;
~~~

Tập hàng thỏa `WHERE room_id=10 AND booking_day=... AND status='confirmed'` đã có thêm một thành viên. Đây là **phantom read**.

### 12.4. Cách nhận ra phantom trong báo cáo

Một báo cáo có thể:

1. Đếm 10 đơn đã duyệt.
2. T2 thêm một đơn đã duyệt.
3. T1 đọc danh sách và thấy 11 đơn.
4. T1 ghép “count=10” với “danh sách có 11” trong cùng kết quả báo cáo.

Nếu báo cáo gồm **nhiều SELECT** phải cùng một lát cắt dữ liệu, READ COMMITTED có thể không đủ. Có thể cân nhắc REPEATABLE READ cho giao dịch chỉ đọc, với phạm vi transaction ngắn.

## 13. Lab phantom read dưới REPEATABLE READ

Reset dữ liệu booking thí nghiệm sau khi mọi transaction cũ hoàn tất:

~~~sql
DELETE FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14';
~~~

### 13.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Kỳ vọng: 0
~~~

### 13.2. Session B / T2

~~~sql
BEGIN;

INSERT INTO isolation_lab.bookings (
    room_id, booking_day, status
)
VALUES (10, DATE '2026-11-14', 'confirmed');

COMMIT;
~~~

### 13.3. Session A / T1 đọc lại

~~~sql
SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Vẫn là 0 trong snapshot của T1.

COMMIT;
~~~

Đây là ví dụ thực tế cho thấy **PostgreSQL REPEATABLE READ không có phantom theo kiểu quan sát tập hàng mới**.

### 13.4. Có phải câu SELECT đầu đã khóa predicate?

Không. SELECT thông thường ở REPEATABLE READ **không có nghĩa** T2 bị chặn INSERT. T2 có thể commit bình thường; T1 chỉ không nhìn thấy hàng của T2 qua snapshot cũ.

Đây là điểm quan trọng giúp phân biệt **snapshot isolation** với cách tưởng tượng “khóa tất cả những hàng có thể thỏa WHERE”.

## 14. Phantom do DELETE hoặc UPDATE

Không chỉ INSERT tạo sự khác biệt tập kết quả.

Giả sử T1 đọc:

~~~sql
SELECT booking_id
FROM isolation_lab.bookings
WHERE status = 'confirmed';
~~~

Sau đó T2:

~~~sql
UPDATE isolation_lab.bookings
SET status = 'cancelled'
WHERE booking_id = 1;

COMMIT;
~~~

Nếu T2 đã commit và T1 chạy lại SELECT dưới READ COMMITTED, booking đó có thể **biến mất** khỏi tập kết quả.

Tương tự, một UPDATE từ `status='draft'` sang `'confirmed'` có thể khiến hàng **xuất hiện** trong predicate đã quan sát trước đó.

### 14.1. Đừng chỉ định nghĩa phantom là “một hàng mới được INSERT”

Bất kỳ thay đổi đã commit nào khiến tập thỏa predicate đổi giữa hai lần đọc đều phù hợp với ý tưởng về phantom.

### 14.2. Cần tách semantics quan sát và semantics ghi

Ở REPEATABLE READ, T1 có thể vẫn thấy tập cũ nhưng một thao tác UPDATE cố ghi vào hàng bị transaction khác thay đổi sau snapshot có thể phát sinh conflict. Sự ổn định của SELECT không phải giấy phép ghi đè dữ liệu mới.

## 15. Read skew: đọc nhiều giá trị không thuộc cùng một lát cắt

**Read skew** (*inconsistent analysis*) xảy ra khi một transaction đọc những dữ liệu có quan hệ logic ở **những thời điểm snapshot khác nhau**, tạo một kết quả tổng hợp chưa từng tồn tại trong một trạng thái commit nhất quán.

Giả sử:

~~~text
Alice balance = 1000
Bob balance   = 1000
Tổng hệ thống = 2000
~~~

T2 thực hiện chuyển 100 từ Alice sang Bob **trong một transaction**:

~~~text
Alice = 900
Bob   = 1100
Tổng  = 2000
~~~

### 15.1. Interleaving gây read skew ở READ COMMITTED

~~~text
Thời gian   T1 đọc báo cáo             T2 chuyển tiền
----------  ------------------------   --------------------------
t1          BEGIN READ COMMITTED
t2          SELECT Alice -> 1000
t3                                     BEGIN
t4                                     UPDATE Alice -> 900
t5                                     UPDATE Bob -> 1100
t6                                     COMMIT
t7          SELECT Bob -> 1100
t8          T1 cộng 1000 + 1100 = 2100
t9          COMMIT
~~~

Không có thời điểm nào mà trạng thái đã commit của cả hai tài khoản có tổng 2100. T1 đã đọc **Alice trước chuyển tiền** và **Bob sau chuyển tiền**.

### 15.2. Đây có phải dirty read?

Không. Cả Alice=1000 và Bob=1100 đều là những giá trị đã commit ở thời điểm mỗi SELECT của T1.

### 15.3. Đây có liên quan nonrepeatable read?

Có. Cơ chế gốc là nhiều statement trong cùng transaction thấy các snapshot khác nhau. Nhưng read skew nhấn mạnh rằng **nhiều phần của một kết quả tổng hợp không cùng thời điểm**, dù T1 chưa nhất thiết đọc lại cùng một hàng.

### 15.4. Dùng một SELECT nhất quán hoặc REPEATABLE READ

Nếu báo cáo chỉ cần tổng số dư một lần, có thể để PostgreSQL tính trong **một câu lệnh**:

~~~sql
SELECT SUM(balance) AS total_balance
FROM isolation_lab.accounts;
~~~

Một SELECT thông thường dưới READ COMMITTED có một snapshot nhất quán cho câu lệnh đó.

Nếu báo cáo cần nhiều truy vấn/các bước ứng dụng riêng nhưng phải cùng một lát cắt, REPEATABLE READ thường phù hợp hơn:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 2;

COMMIT;
~~~

Hai SELECT dùng cùng snapshot giao dịch, tránh trộn trạng thái trước/sau commit của T2.

## 16. Lost update: cập nhật của một tác vụ bị ghi đè

**Lost update** là tình huống hai tác vụ cùng dựa vào một giá trị ban đầu, nhưng một bản cập nhật về sau **ghi đè** kết quả của tác vụ kia làm mất thay đổi mong muốn.

Ví dụ tồn kho ban đầu 10. Hai request cùng muốn bán một đơn vị.

### 16.1. Cách không an toàn: SELECT rồi ghi số tuyệt đối

~~~text
Ban đầu: stock=10

T1                                 T2
---------------------------------  -----------------------------
SELECT stock -> 10                 SELECT stock -> 10
Tính stock mới = 9                 Tính stock mới = 9
UPDATE stock = 9
COMMIT
                                   UPDATE stock = 9
                                   COMMIT

Kết quả: stock=9, dù đã có hai lần bán.
~~~

Điểm sai là mỗi request **tính giá trị mới trong ứng dụng từ ảnh chụp cũ**, rồi ghi lại một giá trị tuyệt đối.

### 16.2. Lost update không phải nonrepeatable read

- Nonrepeatable read nói về **những gì được đọc thấy**.
- Lost update nói về **thay đổi bị mất** sau hai thao tác ghi.

Hai hiện tượng có thể cùng xuất hiện trong một workflow, nhưng không phải cùng định nghĩa.

### 16.3. PostgreSQL READ COMMITTED không mặc định ngăn stale assignment

Nếu hai request dùng logic “đọc stock=10, tính 9, ghi `SET stock=9`”, request thứ hai ở READ COMMITTED có thể chờ lock rồi ghi 9, dẫn tới mất một lần giảm.

### 16.4. PostgreSQL REPEATABLE READ có bảo vệ thêm cho cập nhật cùng hàng

Nếu hai transaction REPEATABLE READ bắt đầu với snapshot trước khi một transaction sửa hàng, rồi cả hai cố UPDATE cùng một hàng, PostgreSQL có cơ chế phát hiện cập nhật đồng thời và có thể báo lỗi serialization failure cho transaction đến sau.

**Không nên nói rằng lost update kiểu ghi đè cùng hàng luôn commit thành công ở mọi isolation level.** Cần chỉ rõ hệ quản trị, mức isolation và cách thực hiện update.

## 17. Tránh lost update bằng UPDATE nguyên tử

Đối với tồn kho, mẫu an toàn hơn là **đưa phép tính vào một UPDATE có điều kiện**:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING sku, stock;
~~~

Nếu trả một hàng, thao tác trừ một đơn vị đã được áp dụng trong transaction của câu lệnh. Nếu trả 0 hàng, sản phẩm không tồn tại hoặc điều kiện tồn kho không thỏa.

### 17.1. Vì sao mẫu này khác SELECT rồi SET stock=9?

`SET stock = stock - 1` dùng giá trị hàng phù hợp tại lúc thực hiện UPDATE theo cơ chế locking/concurrency của PostgreSQL.

Ở READ COMMITTED, nếu UPDATE bị chờ một transaction khác đang sửa hàng, PostgreSQL xử lý row update và đánh giá lại điều kiện phù hợp trước khi tiếp tục trong trường hợp thích hợp. Vì thế hai UPDATE giảm một đơn vị có thể lần lượt cho 9 rồi 8, thay vì cả hai ghi cùng số 9.

### 17.2. CHECK vẫn quan trọng

Lab dùng:

~~~sql
stock INTEGER NOT NULL CHECK (stock >= 0)
~~~

Constraint giúp từ chối số âm nếu một writer khác bỏ điều kiện `stock >= 1`. Nhưng CHECK không tự biết **đơn hàng nào đã được cấp phát**, có retry bị lặp hay chưa và tồn kho có nhiều kho khác nhau không.

### 17.3. Đưa nhiều thay đổi vào một transaction

Nếu cấp phát tồn kho phải đi kèm tạo order và ghi lịch sử cấp phát, cần transaction:

~~~sql
BEGIN;

UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;

-- Kiểm tra có hàng được cập nhật trước khi ghi order.
-- Tạo order/lịch sử bằng lệnh phù hợp với schema thật.

COMMIT;
~~~

Không được commit order “thành công” khi UPDATE tồn kho trả 0 hàng.

### 17.4. Cập nhật nguyên tử không thay mọi isolation

UPDATE đơn hàng an toàn không tự bảo đảm một bất biến phức tạp liên quan nhiều bảng và nhiều hàng. Với những điều kiện như “còn ít nhất một bác sĩ trực”, cần giải pháp khác.

## 18. Optimistic locking: dùng version để chống ghi đè cũ

Một kỹ thuật phổ biến là thêm **cột version**. Lab đã có:

~~~sql
version BIGINT NOT NULL DEFAULT 0
~~~

Ứng dụng đọc:

~~~sql
SELECT sku, stock, version
FROM isolation_lab.inventory
WHERE sku = 'BOOK-001';
~~~

Giả sử nhận `stock=10</BT> và `version=0</BT>. Khi ghi thay đổi dựa trên thông tin đã đọc:

~~~sql
UPDATE isolation_lab.inventory
SET stock = 9,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND version = 0
RETURNING stock, version;
~~~

Nếu transaction khác đã tăng version trước, UPDATE sẽ trả **0 hàng** thay vì ghi đè một giá trị cũ.

### 18.1. Đường ghi phải tôn trọng version

Optimistic locking chỉ có tác dụng nếu **mọi writer cần bảo vệ** đều duy trì và kiểm tra version theo protocol. Một job khác trực tiếp ghi stock mà không tăng version có thể phá hợp đồng.

### 18.2. Trả 0 hàng thì làm gì?

- Tải lại dữ liệu.
- Đánh giá lại nghiệp vụ với giá trị mới.
- Quyết định retry hoặc báo conflict.
- Không tự gửi lại cùng stock=9 vô hạn.

### 18.3. Version khác identity

Identity là mã định danh bản ghi. Version là **số phiên bản logic của bản ghi** giúp phát hiện cập nhật cũ. Không dùng identity làm version hoặc dùng `MAX(id)</BT> để suy luận bản ghi có bị thay đổi không.

## 19. SELECT FOR UPDATE: khóa hàng khi quyết định dựa trên dữ liệu đọc

Có workflow cần đọc nhiều cột của một hàng, kiểm tra logic rồi cập nhật. Khi đó có thể dùng:

~~~sql
BEGIN;

SELECT sku, stock
FROM isolation_lab.inventory
WHERE sku = 'BOOK-001'
FOR UPDATE;

-- Áp dụng logic trên hàng đã khóa.
-- Sau đó UPDATE trong cùng transaction.

COMMIT;
~~~

`FOR UPDATE` yêu cầu row lock đối với những hàng được chọn. Transaction khác muốn cập nhật cùng hàng có thể phải chờ khóa được nhả.

### 19.1. Cần giữ cùng transaction

Nếu SELECT FOR UPDATE chạy trong một transaction nhưng UPDATE lại chạy sau khi transaction đã commit, khóa đã được nhả. Cơ chế bảo vệ bị mất.

### 19.2. Không giữ khóa khi gọi API ngoài

Không nên giữ row lock trong lúc chờ payment provider, email service hoặc tác vụ có thể mất nhiều giây. Điều đó tăng tranh chấp và nguy cơ deadlock/timeout.

### 19.3. Row lock không khóa “mọi hàng sẽ xuất hiện trong tương lai”

Nếu query:

~~~sql
SELECT *
FROM isolation_lab.bookings
WHERE room_id = 10
FOR UPDATE;
~~~

chỉ chọn những hàng đang tồn tại và nhìn thấy, row locks trên những hàng đó **không tự ngăn transaction khác INSERT một booking mới** cùng room_id.

Vì vậy, `SELECT ... FOR UPDATE` không phải công cụ tổng quát thay thế predicate locking hay serializability để bảo vệ những điều kiện kiểu “không có hàng nào thỏa X”.

### 19.4. Khóa một hàng điều phối chung

Một mô hình có thể dùng bảng parent/guard row đại diện tài nguyên cần bảo vệ. Nếu **mọi writer** cùng khóa hàng điều phối đó trước khi kiểm tra và ghi, các thao tác có thể được tuần tự hóa theo protocol.

Nhưng chi tiết vẫn phụ thuộc isolation: khi ở REPEATABLE READ, snapshot đã cố định có thể không thấy thay đổi dù vừa chờ một guard row chưa bị cập nhật. Khi dùng protocol guard row ở READ COMMITTED, nên lấy khóa **trước bước đọc quyết định**; ở các mức snapshot cao hơn cần thiết kế cập nhật guard row hoặc retry phù hợp, không suy luận chỉ việc chờ khóa luôn làm snapshot mới.

## 20. Write skew: hai transaction sửa hai hàng khác nhau nhưng phá bất biến chung

**Write skew** là một serialization anomaly điển hình dưới **snapshot isolation**.

Giả sử bệnh viện có hai bác sĩ, An và Bình. Chính sách: **ít nhất một người phải trực**. Cả hai đang trực.

~~~text
doctor_id=1, An,   on_call=true
doctor_id=2, Bình, on_call=true

Invariant: COUNT(*) WHERE on_call=true >= 1
~~~

Mỗi bác sĩ được nghỉ nếu vẫn có **một bác sĩ khác** đang trực. Hai transaction đồng thời thực hiện:

~~~text
T1 / An                               T2 / Bình
-----------------------------------   --------------------------------
BEGIN REPEATABLE READ                 BEGIN REPEATABLE READ
COUNT(on_call) -> 2                   COUNT(on_call) -> 2
UPDATE doctor_id=1 -> false           UPDATE doctor_id=2 -> false
COMMIT                                COMMIT

Kết quả: cả hai on_call=false.
~~~

Hai UPDATE tác động **hai hàng khác nhau** nên không nhất thiết có xung đột cập nhật cùng hàng. Cả hai đã đọc cùng snapshot hợp lệ, mỗi người đều tưởng người kia sẽ ở lại.

### 20.1. Đây không phải dirty read

Không ai đọc giá trị chưa commit của người kia.

### 20.2. Đây không phải nonrepeatable read hoặc phantom trong snapshot

Mỗi transaction có thể chỉ đọc một lần, hoặc đọc lại và vẫn thấy snapshot cũ. Hai transaction riêng rẽ đều thấy dữ liệu có vẻ nhất quán.

### 20.3. Đây không phải lost update cùng hàng

Không có giá trị cùng một hàng bị ghi đè bởi hai UPDATE. Mỗi transaction sửa hàng của chính mình. **Bất biến nhiều hàng** mới là thứ bị phá.

### 20.4. Vì sao REPEATABLE READ vẫn có thể cho phép?

REPEATABLE READ của PostgreSQL là snapshot isolation, mạnh hơn READ COMMITTED nhưng không tương đương full serializability. Một lịch gồm hai giao dịch đọc trạng thái chung rồi ghi vào **những hàng khác nhau** có thể tạo kết quả không tương đương bất kỳ thứ tự tuần tự hợp lệ nào.

## 21. Lab write skew dưới REPEATABLE READ

Reset dữ liệu khi không có transaction đang mở:

~~~sql
UPDATE isolation_lab.on_call
SET on_call = TRUE
WHERE doctor_id IN (1, 2);
~~~

### 21.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Kỳ vọng: 2

-- Chưa UPDATE/COMMIT.
~~~

### 21.2. Session B / T2

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Kỳ vọng: 2
~~~

**Hai SELECT cần hoàn thành trước khi bất kỳ transaction nào commit**, để T1 và T2 đều có snapshot thấy hai người trực.

### 21.3. Session A tắt lịch trực của An

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 21.4. Session B tắt lịch trực của Bình

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

Hai transaction sửa hàng khác nhau. Trong thí nghiệm này dưới REPEATABLE READ, chúng có thể đều commit thành công.

### 21.5. Kiểm tra kết quả

Sau khi cả hai kết thúc:

~~~sql
SELECT doctor_id, doctor_name, on_call
FROM isolation_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining_on_call
FROM isolation_lab.on_call
WHERE on_call;
~~~

Kỳ vọng `remaining_on_call = 0`: **bất biến “ít nhất một người trực” đã bị vi phạm**.

Đây là ví dụ rất quan trọng để tránh kết luận sai rằng “REPEATABLE READ không có phantom nên mọi nghiệp vụ đa hàng đều an toàn”.

## 22. SERIALIZABLE: bảo vệ kết quả tương đương thực thi tuần tự

Trong PostgreSQL, mức isolation **`SERIALIZABLE`** bảo đảm rằng kết quả của các transaction **đã commit** tương đương với một lịch thực thi tuần tự nào đó, với điều kiện ứng dụng thực hiện các bước kiểm tra và cập nhật đúng trong transaction.

PostgreSQL dùng **Serializable Snapshot Isolation (SSI)**, theo dõi những phụ thuộc đọc/ghi có thể dẫn đến lịch không thể tuần tự hóa.

### 22.1. Không phải khóa toàn database

Không nên hiểu SERIALIZABLE là mọi transaction lần lượt chạy từng cái một và không có concurrency. PostgreSQL vẫn cho nhiều transaction chạy đồng thời; khi phát hiện phụ thuộc nguy hiểm, một transaction có thể bị abort thay vì cho cả hai commit.

### 22.2. Serialization failure là một kết quả dự kiến

Trong một lịch xung đột, PostgreSQL có thể báo:

~~~text
ERROR: could not serialize access due to read/write dependencies
       among transactions
SQLSTATE: 40001
~~~

Thông báo chi tiết có thể khác theo đường thực thi và phiên bản; **SQLSTATE 40001** là cơ sở quan trọng để ứng dụng nhận diện serialization failure.

### 22.3. Không phải mọi SERIALIZABLE transaction đều báo lỗi

Nếu không có chuỗi phụ thuộc gây nguy hiểm, các transaction có thể commit bình thường. Khi xảy ra conflict phù hợp, một transaction bị abort để phần còn lại có kết quả serializable.

### 22.4. SERIALIZABLE không sửa logic sai bên trong một transaction

Nếu ứng dụng **không kiểm tra** còn ai trực và chỉ chạy UPDATE tắt cả hai bác sĩ, database không thể tự suy ra invariant “ít nhất một bác sĩ” từ ngôn ngữ nghiệp vụ chưa được biểu diễn.

Isolation bảo vệ tính tương đương lịch, không thay thế quy tắc nghiệp vụ mà code/constraint phải hiện thực.

## 23. Lab write skew với SERIALIZABLE

Reset bảng:

~~~sql
UPDATE isolation_lab.on_call
SET on_call = TRUE
WHERE doctor_id IN (1, 2);
~~~

Chạy hai phiên, lần này đổi isolation level.

### 23.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Kỳ vọng: 2
~~~

### 23.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Kỳ vọng: 2
~~~

### 23.3. Session A cập nhật An

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 23.4. Session B cập nhật Bình

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

Trong lịch có cả hai lần đọc trước khi các cập nhật được commit, PostgreSQL **không cho cả hai transaction commit thành công theo cách phá bất biến write skew này**. Một transaction có thể gặp SQLSTATE `40001` tại UPDATE hoặc COMMIT tùy interleaving.

### 23.5. Xử lý transaction thất bại

Nếu phiên B gặp lỗi, thực hiện ROLLBACK khi cần để đưa kết nối về trạng thái sử dụng bình thường. Sau đó bắt đầu **transaction mới**, đọc lại số bác sĩ còn trực:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;

-- Nếu kết quả chỉ còn 1 thì không được cho người cuối cùng nghỉ.
ROLLBACK;
~~~

Nếu ứng dụng đọc lại và áp dụng đúng rule, người thứ hai không thể nghỉ, nên invariant được giữ.

### 23.6. Điều kiện quan trọng: tất cả đường ghi phải tham gia protocol

Nếu một service thực hiện kiểm tra trong SERIALIZABLE nhưng job khác cập nhật trực tiếp và không kiểm tra cùng invariant, kết quả có thể vẫn trái quy tắc sản phẩm dù các transaction được tuần tự hóa. Các writer cần tuân thủ cùng hợp đồng; khi có thể, dùng constraint biểu diễn invariant trực tiếp.

## 24. SSI và predicate locks trong PostgreSQL

Một điểm dễ nhầm: PostgreSQL Serializable Snapshot Isolation sử dụng thông tin về **xung đột đọc/ghi**, có thể ghi nhận qua các **predicate locks** dạng `SIReadLock`.

### 24.1. SIReadLock không giống row lock FOR UPDATE

- `SELECT ... FOR UPDATE`: chủ yếu dùng row lock có thể khiến thao tác ghi khác phải chờ.
- `SIReadLock`: theo dõi dữ liệu hoặc vùng predicate đã đọc để phát hiện phụ thuộc serialization; không đơn giản ngăn mọi writer INSERT/UPDATE vào vùng đó.

### 24.2. Predicate lock có thể ở các mức chi tiết khác nhau

Tùy kế hoạch truy vấn và tài nguyên, PostgreSQL có thể theo dõi xung đột ở cấp hàng, trang hoặc quan hệ. Vì vậy, kế hoạch truy vấn và indexing có thể ảnh hưởng tần suất abort serialization trong một workload.

### 24.3. Index có giúp tránh serialization failures?

Index phù hợp có thể giúp truy vấn truy cập tập hàng hẹp hơn, từ đó trong một số trường hợp giảm xung đột không cần thiết và tăng hiệu năng. Nhưng nó **không loại bỏ nhu cầu retry** và không bảo đảm không bao giờ có `40001`.

### 24.4. Tránh “đổi SERIALIZABLE thành FOR UPDATE mọi thứ”

Khóa hàng có thể thích hợp cho một số quy tắc, nhưng không thay thế được mọi predicate, đặc biệt là khi hàng cần bảo vệ **chưa tồn tại**. PostgreSQL SSI giúp phát hiện các lịch read/write xung đột phức tạp hơn một row lock đơn lẻ.

## 25. Retry toàn bộ transaction khi gặp SQLSTATE 40001

Đây là bước **bắt buộc về thiết kế** khi ứng dụng dựa vào SERIALIZABLE và muốn giao dịch có thể thành công sau một serialization failure.

### 25.1. Vì sao phải retry toàn transaction?

Giả sử transaction ban đầu:

1. Đọc số bác sĩ đang trực = 2.
2. Quyết định cho bác sĩ A nghỉ.
3. UPDATE A.
4. COMMIT gặp `40001`.

Nếu chỉ chạy lại UPDATE ở bước 3, quyết định “vẫn còn bác sĩ khác trực” vẫn dựa trên snapshot cũ. Đây chính là nguyên nhân cần abort.

Retry đúng phải:

1. Bắt đầu transaction **mới**.
2. Đọc lại dữ liệu hiện tại theo snapshot mới.
3. Kiểm tra lại điều kiện nghiệp vụ.
4. Quyết định lại thao tác.
5. Thực hiện SQL và COMMIT.
6. Retry có giới hạn nếu lại gặp `40001`.

### 25.2. Pseudocode

~~~text
for attempt = 1 .. MAX_ATTEMPTS:
    begin SERIALIZABLE transaction
    try:
        read current state
        verify business preconditions
        apply changes
        COMMIT
        return success
    catch SQLSTATE 40001:
        ROLLBACK if needed
        backoff with jitter
        continue with a NEW transaction
    catch other error:
        ROLLBACK
        propagate or handle as appropriate

raise "transaction could not complete after retries"
~~~

### 25.3. Retry có giới hạn

Không lặp vô hạn trong môi trường nhiều contention. Cần:

- Giới hạn số lần thử.
- Backoff/jitter phù hợp.
- Deadline tổng cho request.
- Theo dõi tỷ lệ `40001`.
- Xem lại transaction quá dài hoặc workload tranh chấp nặng.

### 25.4. Bắt lỗi ở COMMIT

Serialization failure có thể xảy ra **khi commit**, dù các câu SELECT/UPDATE trước đó không báo lỗi. Code quản lý transaction phải bắt lỗi bao quanh **toàn bộ transaction gồm COMMIT**.

### 25.5. Không retry cả side effect ngoài database một cách mù quáng

Nếu trong transaction đã gửi email, gọi payment provider hoặc phát một event không idempotent rồi COMMIT thất bại, retry toàn workflow có thể lặp hành động ngoài DB.

Dùng những cơ chế như:

- Idempotency key.
- Outbox/inbox pattern.
- Đẩy external side effect sau commit khi phù hợp.
- Xử lý webhook và retry có khóa nghiệp vụ.
- Reconciliation giữa PostgreSQL và hệ thống bên ngoài.

Giao dịch PostgreSQL rollback **không tự rollback** một email đã gửi hoặc một khoản thanh toán bên ngoài.

## 26. Deadlock khác serialization failure

Một tình huống khác là **deadlock**:

~~~text
T1 giữ lock hàng A, chờ hàng B.
T2 giữ lock hàng B, chờ hàng A.
Không ai có thể tiếp tục nếu không có can thiệp.
~~~

PostgreSQL có cơ chế phát hiện deadlock và chọn một transaction để abort.

### 26.1. SQLSTATE khác nhau

| Tình huống | SQLSTATE | Ý nghĩa |
|---|---|---|
| Serialization failure | `40001` | Không thể cho transaction commit mà giữ serializability/đảm bảo snapshot tương ứng |
| Deadlock detected | `40P01` | Chu trình chờ lock khiến transaction không thể tiến |
| Lock not available | `55P03` | Không lấy được lock theo yêu cầu NOWAIT/lock timeout phù hợp |
| Unique violation | `23505` | Trùng constraint/index duy nhất |
| Exclusion violation | `23P01` | Vi phạm exclusion constraint |

### 26.2. Deadlock có thể xảy ra ở nhiều isolation levels

Không phải cứ dùng READ COMMITTED là không có deadlock. Hai UPDATE lấy khóa theo thứ tự đối nghịch có thể deadlock.

### 26.3. Giảm deadlock bằng thứ tự khóa nhất quán

Trong chuyển tiền A→B và B→A đồng thời, một protocol có thể yêu cầu luôn khóa account có ID nhỏ trước, rồi ID lớn. Điều này giảm một nguồn deadlock phổ biến.

### 26.4. Retry deadlock

Ứng dụng cũng thường cần khả năng retry toàn transaction cho `40P01` khi thao tác idempotent và phù hợp. Tuy nhiên, **đừng coi mọi SQLSTATE đều retry**: một unique violation do mã cố ý trùng cần xử lý nghiệp vụ thay vì lặp vô hạn.

## 27. Dirty write: hai transaction ghi đè dữ liệu chưa commit

**Dirty write** xảy ra nếu T2 ghi đè một giá trị **đang được T1 ghi nhưng T1 chưa commit**, làm rối việc rollback hoặc thứ tự ghi.

Trong PostgreSQL, các UPDATE/DELETE cùng hàng được điều phối bằng row locking. Một transaction không đơn giản ghi đè phiên bản chưa commit của transaction khác rồi cả hai tự do commit/rollback.

### 27.1. Kịch bản chờ khóa

~~~text
T1: BEGIN
T1: UPDATE account(1)
    (giữ row lock)

T2: BEGIN
T2: UPDATE account(1)
    (có thể phải chờ T1)

T1: COMMIT hoặc ROLLBACK
T2: tiếp tục hoặc gặp lỗi theo isolation/concurrency
~~~

### 27.2. Dirty write không đồng nghĩa lost update

- **Dirty write:** liên quan ghi đè dữ liệu **chưa commit**.
- **Lost update:** một thay đổi đã thực hiện bị mất khi một tác vụ dùng giá trị cũ và ghi đè kết quả mong muốn.

PostgreSQL ngăn dirty write trực tiếp qua locking, nhưng logic read-modify-write không an toàn ở READ COMMITTED vẫn có thể gây lost update.

## 28. Read-only transaction cũng cần chọn isolation phù hợp

Không phải transaction chỉ SELECT thì không có vấn đề đồng thời.

### 28.1. READ COMMITTED cho một truy vấn độc lập

Nếu một API chỉ chạy:

~~~sql
SELECT SUM(balance)
FROM isolation_lab.accounts;
~~~

và trả một kết quả, snapshot theo statement của READ COMMITTED thường cung cấp một lát cắt nhất quán cho truy vấn đó.

### 28.2. REPEATABLE READ cho báo cáo nhiều bước

Nếu API chạy nhiều câu SELECT để dựng một báo cáo phải nhất quán cùng thời điểm:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*)
FROM isolation_lab.accounts;

SELECT SUM(balance)
FROM isolation_lab.accounts;

COMMIT;
~~~

Hai câu dùng cùng snapshot nên tránh read skew giữa các statement.

### 28.3. READ ONLY không có nghĩa transaction không ảnh hưởng vận hành

Transaction read-only dài vẫn có thể giữ snapshot lâu và ảnh hưởng VACUUM. Nếu cần báo cáo dài, cân nhắc thiết kế dữ liệu, batching và giải pháp analytics phù hợp.

### 28.4. SERIALIZABLE READ ONLY DEFERRABLE

PostgreSQL hỗ trợ chế độ:

~~~sql
BEGIN TRANSACTION
ISOLATION LEVEL SERIALIZABLE
READ ONLY
DEFERRABLE;

SELECT COUNT(*)
FROM isolation_lab.accounts;

COMMIT;
~~~

Một transaction như vậy có thể **chờ tới khi có snapshot an toàn**. Sau khi snapshot an toàn được thiết lập, nó có thể thực hiện các truy vấn read-only theo đảm bảo serializable mà không chịu những serialization failures thông thường dành cho transaction kiểu này.

Đây không phải tùy chọn cần bật cho mọi SELECT. Nó phù hợp một số báo cáo read-only cần serializable snapshot, chấp nhận chờ lúc bắt đầu.

## 29. READ COMMITTED và hành vi UPDATE khi có tranh chấp

Ở READ COMMITTED, SELECT và UPDATE không phải lúc nào cũng xử lý các hàng giống một vòng đọc snapshot bất động.

Ví dụ hai transaction cùng muốn trừ kho:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;
~~~

Khi một UPDATE bị chờ vì hàng đang được transaction khác sửa, PostgreSQL có thể xử lý phiên bản mới đã commit và **kiểm tra lại điều kiện WHERE** cho hàng đó trước khi quyết định cập nhật.

Điều này giúp mẫu cập nhật nguyên tử khác với:

~~~text
1. SELECT stock vào ứng dụng.
2. Tính new_stock từ số đã đọc.
3. UPDATE stock = new_stock.
~~~

### 29.1. Không suy luận “READ COMMITTED bảo vệ mọi update”

Nó giúp điều phối cập nhật cùng hàng nhưng không biết mục đích nghiệp vụ. `SET stock=9` vẫn có thể ghi đè số đã giảm bởi transaction khác nếu code dựa trên giá trị cũ.

### 29.2. Không suy luận mọi phần của một statement UPDATE nhìn chung một snapshot mới

Các câu UPDATE có ngữ nghĩa visibility và xử lý row conflict đặc thù. Nếu query trộn đọc dữ liệu nhiều bảng, subquery và cập nhật những hàng đang tranh chấp, hãy xem kỹ semantics PostgreSQL và thử nghiệm interleaving thực.

Trong những nghiệp vụ nhạy cảm, chọn một protocol đơn giản, có constraint, khóa và test concurrency rõ ràng thay vì dựa trên suy đoán planner.

## 30. Khi constraint mạnh hơn việc chỉ tăng isolation

Nhiều bất biến dữ liệu có thể được PostgreSQL giữ bằng constraint:

### 30.1. Không trùng mã đơn

~~~sql
CREATE TABLE isolation_lab.external_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT NOT NULL UNIQUE
);
~~~

Nếu hai transaction cùng thêm một `external_code`, UNIQUE constraint giúp bảo vệ không trùng. Pre-check ở ứng dụng không thay được UNIQUE dưới concurrency.

### 30.2. Kho không âm

Lab đã có:

~~~sql
stock INTEGER NOT NULL CHECK (stock >= 0)
~~~

CHECK bảo vệ phạm vi, nhưng không thay atomic UPDATE và quản lý số lượng đã hứa cho đơn nào.

### 30.3. Quan hệ tồn tại

Foreign key giúp bảo đảm order tham chiếu customer tồn tại, ngay cả khi nhiều writer chạy đồng thời. Nhưng FK không tự xác nhận authorization hoặc toàn bộ workflow.

### 30.4. Không trùng khoảng booking

PostgreSQL có **exclusion constraints** với range types/GiST để bảo vệ quy tắc “hai booking confirmed không chồng lấn cho cùng phòng” khi dữ liệu có cấu trúc thích hợp.

Một câu `SELECT COUNT(*) WHERE NOT EXISTS ...` ở ứng dụng không tự chống race. Constraint loại trừ phù hợp có thể tốt hơn một protocol tự viết bằng SELECT rồi INSERT.

### 30.5. Không có constraint một hàng đơn giản cho mọi bất biến nhiều hàng

“Ít nhất một bác sĩ trực” phụ thuộc **tổng nhiều hàng**. Một CHECK trên cột `on_call</BT> riêng lẻ không biểu đạt trực tiếp được toàn bộ bất biến.

Khi cần, có thể dùng serializable transactions, guard row lock protocol hoặc tái thiết kế mô hình để biểu diễn invariant bằng một hàng/constraint mạnh hơn.

## 31. SERIALIZABLE không thay authorization hoặc idempotency

Một lịch serializable chỉ nói về kết quả tương đương với một thứ tự tuần tự hợp lệ. Nó **không khẳng định người dùng được phép thực hiện thao tác**.

Ví dụ, nếu service cho bất kỳ người dùng nào cập nhật `account_id</BT> của người khác, SERIALIZABLE vẫn có thể commit một thao tác trái phép nếu không có kiểm tra quyền.

Tương tự, retry request “tạo đơn” có thể tạo hai đơn riêng nếu không có idempotency key hoặc unique business key phù hợp.

### 31.1. Authorization

Kiểm tra user/tenant/role ở API/domain service và có thể bổ sung bằng RLS/GRANT của PostgreSQL.

### 31.2. Idempotency

Khi một request được gửi lại do timeout, cần cách nhận diện “đã xử lý yêu cầu này chưa” để tránh ghi lặp. Một unique constraint trên `idempotency_key` có thể là một phần giải pháp.

### 31.3. External systems

Payment provider, email, message bus và API khác nằm ngoài phạm vi commit/rollback thông thường của PostgreSQL. Có thể cần outbox, event replay và reconciliation.

### 31.4. Độ đúng nghiệp vụ

Một transaction serializable vẫn có thể áp dụng công thức giảm giá sai. Isolation không thay kiểm thử domain logic.

## 32. Isolation level và latency/throughput

Mức isolation mạnh hơn có thể tăng độ an toàn cho một loại workload, nhưng không có nghĩa tăng isolation luôn miễn phí.

| Mức | Lợi ích chính | Chi phí/rủi ro cần tính |
|---|---|---|
| READ COMMITTED | Linh hoạt, phổ biến, snapshot theo statement | Dễ gặp nonrepeatable/phantom/read skew giữa statements |
| REPEATABLE READ | Lát cắt ổn định cho transaction; ngăn phantom truyền thống | Snapshot dài; xung đột UPDATE; write skew vẫn có thể xảy ra |
| SERIALIZABLE | Phát hiện serialization anomalies, cho kết quả commit tuần tự hóa được | Có thể abort 40001; cần retry; contention và overhead SSI |
| SERIALIZABLE READ ONLY DEFERRABLE | Snapshot an toàn cho báo cáo read-only | Có thể chờ lấy snapshot an toàn |

### 32.1. SERIALIZABLE có thể tăng retry

Khi workload gồm nhiều transaction cùng kiểm tra một predicate rồi ghi những hàng liên quan, SSI có thể abort nhiều giao dịch. Nếu ứng dụng không retry, người dùng sẽ thấy lỗi tạm thời.

### 32.2. Transaction quá dài dễ gây tranh chấp

Một transaction đọc và xử lý nhiều phút có thể tích lũy nhiều phụ thuộc đọc/ghi, làm tăng rủi ro contention và ảnh hưởng VACUUM. Hãy giữ giao dịch **ngắn, xác định rõ bước cần atomic và tránh gọi dịch vụ ngoài khi đang giữ khóa**.

### 32.3. Không dùng isolation thấp để chữa lỗi data race

Đổi từ REPEATABLE READ sang READ COMMITTED có thể làm một workload ít báo 40001 hơn, nhưng nếu nghiệp vụ cần serializable correctness thì việc đó chỉ che lỗi bằng cách cho những kết quả không mong muốn commit.

Phải quyết định dựa trên yêu cầu bất biến và chiến lược đồng thời, không chỉ dựa trên số lỗi hiện tại.

## 33. Quan sát lock và transaction trong PostgreSQL

Trong môi trường có quyền phù hợp, có thể xem thông tin hoạt động:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

### 33.1. Những dấu hiệu cần xem

- `state='idle in transaction'` kéo dài.
- `wait_event_type='Lock'` cho thấy backend đang chờ một loại lock.
- Nhiều transaction mở quá lâu.
- Tần suất SQLSTATE `40001` hoặc `40P01` ở log/application metrics.

### 33.2. pg_locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
~~~

Đây chỉ là cái nhìn đơn giản về lock của **backend hiện tại**, không phải trình phân tích đầy đủ mọi quan hệ chờ khóa.

### 33.3. Xác định backend đang chặn một phiên

PostgreSQL có hàm:

~~~sql
SELECT pg_blocking_pids(pg_backend_pid()) AS blockers;
~~~

Nếu chạy trong một phiên **đang không bị block**, kết quả thường là mảng rỗng. Khi debug, gọi nó trong ngữ cảnh phiên cần quan sát hoặc với PID thích hợp được quyền truy cập.

### 33.4. Deadlock counter

~~~sql
SELECT
    datname,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`deadlocks` là số liệu deadlock tích lũy theo thống kê, không phải bộ đếm trực tiếp cho mọi serialization failure. Muốn theo dõi 40001, nên ghi nhận SQLSTATE ở ứng dụng/log phù hợp.

### 33.5. Không hiểu nhầm pg_stat_database_conflicts

Các thống kê xung đột liên quan recovery/standby không phải một phép đếm tổng quát mọi SSI serialization failure trên primary. Cần dùng nguồn quan sát đúng với câu hỏi.

## 34. Kịch bản kiểm thử concurrency đáng có

Unit test chạy từng request tuần tự có thể không phát hiện anomalies. Nên có **integration tests với ít nhất hai kết nối PostgreSQL thật**.

### 34.1. Dirty read test

T1 ghi thay đổi nhưng chưa commit; T2 thử SELECT ở READ UNCOMMITTED/READ COMMITTED. Kỳ vọng T2 không thấy thay đổi của T1.

### 34.2. Nonrepeatable read test

T1 READ COMMITTED đọc hàng; T2 UPDATE+COMMIT; T1 đọc lại. Kỳ vọng hai giá trị có thể khác nhau.

Lặp với REPEATABLE READ và cùng thứ tự snapshot: T1 không thấy phiên bản mới qua SELECT thông thường.

### 34.3. Phantom test

T1 đếm hàng theo predicate; T2 INSERT+COMMIT hàng thỏa predicate; T1 đếm lại. Kỳ vọng READ COMMITTED thấy thay đổi, REPEATABLE READ không thấy thay đổi trong snapshot.

### 34.4. Lost update test

Hai worker cùng đọc stock=10 rồi cùng ghi stock=9. Kỳ vọng test phát hiện nguy cơ còn stock=9 sau hai đơn được chấp nhận nếu protocol không an toàn.

Sau đó thay bằng atomic UPDATE + điều kiện stock và xác minh stock=8 hoặc một request thất bại do không đủ hàng, tùy số lượng ban đầu.

### 34.5. Write skew test

T1/T2 đều đọc số bác sĩ trực =2 rồi sửa hai hàng khác nhau. Kỳ vọng REPEATABLE READ có thể cho cả hai commit; SERIALIZABLE không cho phép cả hai commit lịch phá invariant đó.

### 34.6. Retry test

Tạo lịch có thể sinh 40001; ứng dụng phải retry toàn transaction và đánh giá lại precondition. Kiểm tra giới hạn retries, idempotency và COMMIT exception.

### 34.7. Test deadlock

Hai transaction cố lấy khóa hai hàng theo thứ tự trái ngược nhau, xem hệ thống xử lý 40P01 đúng. Không giữ deadlock thí nghiệm trên database chung hoặc production.

## 35. Một quy trình chọn giải pháp cho nghiệp vụ thật

Khi gặp dữ liệu sai dưới concurrency, không chọn isolation bằng cảm giác. Hãy lần lượt:

1. **Mô tả invariant.** Ví dụ stock không âm, booking không trùng, ít nhất một người trực.
2. **Xác định đơn vị quan sát.** Một hàng, một tập hàng hay nhiều bảng?
3. **Vẽ lịch T1/T2.** Ai đọc gì, ai sửa gì, commit lúc nào?
4. **Phân loại anomaly.** Dirty/nonrepeatable/phantom, lost update, read skew hay write skew?
5. **Tìm constraint trực tiếp.** UNIQUE, FK, CHECK, EXCLUDE nếu phù hợp.
6. **Cân nhắc một SQL statement nguyên tử.** `UPDATE ... WHERE condition RETURNING` thường đơn giản cho tồn kho cùng hàng.
7. **Cân nhắc optimistic version** khi UI/service đọc một bản rồi chỉnh sửa lâu.
8. **Cân nhắc row locks** khi cần kiểm tra rồi sửa một tập hàng đã biết, với protocol giữa mọi writer.
9. **Dùng REPEATABLE READ** khi cần snapshot ổn định cho báo cáo hoặc các phép đọc lặp.
10. **Dùng SERIALIZABLE** khi bất biến nhiều hàng có thể bị write skew và giải pháp trực tiếp khác không phù hợp.
11. **Thiết kế retry** cho 40001/40P01, gồm COMMIT và external side effects.
12. **Đo hiệu năng/tranh chấp** và giới hạn thời gian transaction.
13. **Viết integration test hai phiên** để cố định mong đợi.
14. **Kiểm soát tất cả đường ghi**: API, worker, batch import, admin script.
15. **Quan sát production** và cảnh báo khi retries/deadlocks/idle transactions tăng.

Một giải pháp tốt không phải “mức isolation cao nhất ở mọi nơi”, mà là **giải pháp đơn giản nhất bảo vệ được invariant với tải và cách vận hành thực tế**.

## 36. Những hiểu lầm thường gặp

### 36.1. “READ UNCOMMITTED trong PostgreSQL cho đọc dữ liệu chưa commit”

**Sai.** PostgreSQL xử lý nó như READ COMMITTED; dirty read giữa transaction không xảy ra.

### 36.2. “Không đọc bẩn thì mọi báo cáo đã nhất quán”

**Sai.** READ COMMITTED vẫn có nonrepeatable read, phantom và read skew qua nhiều SELECT.

### 36.3. “Nonrepeatable read là đọc giá trị chưa commit”

**Sai.** Hiện tượng điển hình là lần đọc thứ hai thấy giá trị **đã commit** từ transaction khác.

### 36.4. “Phantom chỉ xảy ra do INSERT”

**Không đầy đủ.** DELETE hoặc UPDATE thay đổi tập thỏa predicate cũng có thể tạo phantom.

### 36.5. “REPEATABLE READ của PostgreSQL vẫn có phantom như bảng tối thiểu của chuẩn SQL”

**Sai với PostgreSQL.** Snapshot isolation của nó ngăn phantom truyền thống.

### 36.6. “REPEATABLE READ đã ngăn phantom nên tương đương SERIALIZABLE”

**Sai.** Write skew vẫn có thể xảy ra.

### 36.7. “Một SELECT dưới READ COMMITTED đọc các hàng ở các commit time tùy ý”

**Sai trong cách hiểu thông thường.** Một SELECT sử dụng snapshot của câu lệnh; vấn đề read skew thường xuất hiện giữa **nhiều statements**.

### 36.8. “BEGIN REPEATABLE READ luôn cố định snapshot ngay trước câu SELECT đầu”

**Không nhất thiết.** Snapshot được xác lập khi transaction thực hiện thao tác cần snapshot theo semantics PostgreSQL.

### 36.9. “READ COMMITTED ngăn lost update vì có row locks”

**Không đủ.** Stale read-modify-write với UPDATE gán giá trị tuyệt đối vẫn có thể mất thay đổi.

### 36.10. “READ COMMITTED luôn làm hai SET stock=stock-1 ghi đè nhau”

**Không.** UPDATE nguyên tử dùng giá trị hàng và recheck phù hợp dưới row locking, khác với ghi giá trị cũ đã tính ở ứng dụng.

### 36.11. “SELECT FOR UPDATE khóa cả những hàng chưa tồn tại”

**Sai.** Row locks trên hàng hiện tại không phải predicate lock chặn mọi INSERT tương lai.

### 36.12. “Dirty write và lost update là cùng hiện tượng”

**Sai.** Dirty write liên quan ghi đè thay đổi chưa commit; lost update là thay đổi bị mất do protocol cập nhật không an toàn.

### 36.13. “Write skew bắt buộc phải có hai transaction ghi cùng hàng”

**Sai.** Một đặc trưng của write skew là đọc phụ thuộc chung nhưng ghi **những hàng khác nhau**.

### 36.14. “SERIALIZABLE làm mọi transaction chạy tuần tự vật lý”

**Sai.** PostgreSQL vẫn chạy đồng thời và dùng SSI/abort khi cần.

### 36.15. “SQLSTATE 40001 là bug PostgreSQL”

**Sai.** Đây là tình huống concurrency dự kiến mà ứng dụng phải xử lý khi sử dụng mức isolation phù hợp.

### 36.16. “Gặp 40001 chỉ cần chạy lại UPDATE cuối”

**Sai.** Quyết định nghiệp vụ được đưa ra từ snapshot cũ; phải retry **toàn transaction**.

### 36.17. “Serialization failure và deadlock giống nhau”

**Sai.** Thường tương ứng 40001 và 40P01, có nguyên nhân khác nhau dù cả hai có thể cần retry.

### 36.18. “Transaction read-only không cần nghĩ về isolation”

**Sai.** Báo cáo nhiều SELECT có thể gặp read skew dưới READ COMMITTED.

### 36.19. “Constraint không còn cần thiết khi bật SERIALIZABLE”

**Sai.** Isolation không tự biết tập giá trị hợp lệ, khóa duy nhất hoặc foreign key nghiệp vụ.

### 36.20. “Retry transaction có nghĩa có thể gọi payment API lại vô hạn”

**Sai.** External side effects cần idempotency và chiến lược tích hợp riêng.

### 36.21. “Tăng isolation luôn tăng throughput và giảm lock waits”

**Không.** Mức isolation mạnh hơn có thể tăng abort/retry và overhead. Phải đo workload thật.

### 36.22. “Phát hiện lỗi concurrency chỉ cần chạy unit test một connection”

**Không.** Cần interleaving nhiều kết nối để tái hiện anomalies.

## 37. Bài tập thực hành

### Bài 1 — Phân loại dirty read

T2 UPDATE balance=900 nhưng chưa COMMIT. T1 đọc được 900, rồi T2 ROLLBACK. Hiện tượng này tên gì?

**Đáp án:** Dirty read.

### Bài 2 — Dirty read trong PostgreSQL

Dùng `BEGIN ISOLATION LEVEL READ UNCOMMITTED` có làm T1 nhìn thấy UPDATE chưa commit của T2 không?

**Đáp án:** Không. Trong PostgreSQL, mức đó hoạt động như READ COMMITTED.

### Bài 3 — Nonrepeatable read

T1 đọc balance=1000. T2 UPDATE+COMMIT balance=900. T1 đọc lại balance=900 trong cùng transaction. Hiện tượng gì?

**Đáp án:** Nonrepeatable read.

### Bài 4 — Phân biệt với đọc giữa hai transaction

T1 SELECT rồi COMMIT; sau đó một transaction mới SELECT thấy giá trị khác. Có phải ví dụ chuẩn của nonrepeatable read không?

**Gợi ý:** Không, vì lần đọc diễn ra trong transaction khác.

### Bài 5 — Phantom

T1 SELECT COUNT(bookings WHERE confirmed)=5. T2 thêm một booking confirmed và COMMIT. T1 chạy lại thấy 6. Hiện tượng gì?

**Đáp án:** Phantom read.

### Bài 6 — Phantom do UPDATE

T2 đổi status của booking từ draft thành confirmed khiến T1 SELECT theo predicate confirmed tăng số hàng. Có thể là phantom không?

**Gợi ý:** Có.

### Bài 7 — REPEATABLE READ PostgreSQL

PostgreSQL REPEATABLE READ có nhìn thấy booking mới đã commit sau snapshot T1 ở lần SELECT thứ hai không?

**Đáp án:** Không trong SELECT thông thường cùng transaction.

### Bài 8 — Phân biệt REPEATABLE READ và SERIALIZABLE

REPEATABLE READ không có phantom truyền thống; vì sao vẫn chưa đủ để bảo vệ bất biến nhiều hàng?

**Gợi ý:** Write skew/serialization anomalies vẫn có thể xảy ra.

### Bài 9 — Read skew

T1 đọc số dư Alice trước giao dịch, số dư Bob sau giao dịch; tổng ra một giá trị chưa từng tồn tại ở trạng thái commit nhất quán. Tên hiện tượng?

**Đáp án:** Read skew.

### Bài 10 — Một SELECT hay hai SELECT?

Với báo cáo tổng số dư, vì sao `SELECT SUM(balance)</BT> trong một câu có thể tránh read skew vốn xuất hiện khi ứng dụng đọc từng tài khoản bằng hai câu riêng?

**Gợi ý:** Một SELECT thông thường dùng một statement snapshot.

### Bài 11 — Lost update

Hai request cùng đọc stock=10, cùng tính stock_new=9, rồi ghi 9. Vì sao cuối cùng stock=9 là sai nếu cả hai bán thành công?

**Gợi ý:** Một lần giảm bị mất.

### Bài 12 — Cập nhật nguyên tử

Viết SQL giảm stock một đơn vị chỉ nếu còn đủ:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;
~~~

**Gợi ý:** Dựa vào số hàng RETURNING, không giả định mọi UPDATE đều thành công.

### Bài 13 — Optimistic locking

Ứng dụng đọc version=2. Một writer khác đã nâng version=3. UPDATE với `WHERE version=2` sẽ làm gì?

**Gợi ý:** Trả 0 hàng nếu không còn hàng khớp, để ứng dụng xử lý conflict.

### Bài 14 — FOR UPDATE

Câu `SELECT ... FOR UPDATE</BT> có ngăn một INSERT mới tạo hàng phù hợp predicate nếu trước đó hàng chưa tồn tại không?

**Đáp án:** Không tự động.

### Bài 15 — Dirty write

T1 đang UPDATE một hàng nhưng chưa commit; T2 muốn UPDATE cùng hàng. PostgreSQL cho T2 ghi đè trực tiếp không chờ bất chấp lock không?

**Gợi ý:** Không; row locking điều phối cập nhật đồng thời.

### Bài 16 — Write skew lịch trực

An và Bình đều đang trực. Mỗi người đọc số bác sĩ trực=2 rồi sửa riêng hàng mình thành false. Vì sao hai COMMIT ở REPEATABLE READ có thể làm bất biến sai?

**Gợi ý:** Hai transaction cùng dựa trên snapshot cũ và ghi khác hàng.

### Bài 17 — SERIALIZABLE write skew

Lặp bài 16 ở SERIALIZABLE. Điều gì phải xảy ra để PostgreSQL không cho cả hai commit một lịch không tuần tự hóa được?

**Gợi ý:** Ít nhất một transaction có thể bị abort với 40001.

### Bài 18 — Retry đúng

Nếu gặp 40001 tại COMMIT sau khi đã đọc dữ liệu rồi UPDATE, chỉ retry UPDATE có đủ không?

**Đáp án:** Không. Phải retry toàn transaction, đọc lại và quyết định lại.

### Bài 19 — External side effect

Transaction gửi email rồi COMMIT thất bại 40001. Vì sao retry không kiểm soát có thể gửi hai email?

**Gợi ý:** Email không rollback cùng database; cần outbox/idempotency.

### Bài 20 — Deadlock

T1 khóa A chờ B; T2 khóa B chờ A. Hiện tượng gì và SQLSTATE phổ biến?

**Đáp án:** Deadlock, SQLSTATE 40P01.

### Bài 21 — UNIQUE

Hai transaction cùng kiểm tra mã đơn chưa tồn tại rồi INSERT. Vì sao chỉ SELECT kiểm tra trước chưa đủ?

**Gợi ý:** Race condition; cần UNIQUE constraint và xử lý 23505.

### Bài 22 — SSI

SIReadLock dưới SERIALIZABLE có phải luôn chặn transaction khác INSERT hàng phù hợp predicate ngay lập tức không?

**Gợi ý:** Không; nó phục vụ theo dõi phụ thuộc xung đột và phát hiện lịch không serializable.

### Bài 23 — READ ONLY DEFERRABLE

Khi nào cân nhắc `SERIALIZABLE READ ONLY DEFERRABLE`?

**Gợi ý:** Báo cáo chỉ đọc cần snapshot serializable an toàn và chấp nhận chờ lúc đầu.

### Bài 24 — Transaction dài

Vì sao một transaction REPEATABLE READ mở lâu có thể ảnh hưởng VACUUM?

**Gợi ý:** Snapshot cũ có thể buộc giữ những phiên bản hàng còn cần nhìn thấy.

### Bài 25 — Thứ tự khóa

Nếu hai transaction chuyển tiền giữa tài khoản 1 và 2, vì sao thống nhất luôn khóa ID nhỏ trước có thể giúp?

**Gợi ý:** Giảm nguy cơ vòng chờ khóa gây deadlock.

### Bài 26 — Isolation level theo mục tiêu

Chọn giải pháp chính cho từng tình huống:

| Tình huống | Gợi ý |
|---|---|
| Một UPDATE trừ tồn kho một hàng | Atomic UPDATE + CHECK |
| Đọc nhiều phần của báo cáo cùng lát cắt | REPEATABLE READ READ ONLY |
| Hai giao dịch bảo vệ bất biến phức tạp nhiều hàng | SERIALIZABLE hoặc protocol khóa đúng |
| Cấm email trùng | UNIQUE |
| UI gửi bản sửa từ dữ liệu cũ | Optimistic version |
| Gọi provider thanh toán ngoài DB | Idempotency + workflow/outbox |

### Bài 27 — Phân biệt SQLSTATE

Ghép mã `40001`, `40P01`, `23505` và `55P03` với serialization, deadlock, unique violation và lock not available.

### Bài 28 — Viết lịch

Viết một timeline T1/T2 minh họa nonrepeatable read ở READ COMMITTED, có đủ BEGIN, SELECT, UPDATE, COMMIT. Đánh dấu mốc T2 commit trước SELECT thứ hai của T1.

### Bài 29 — Hai phiên thật

Vì sao chạy các câu A1, B1, A2 tuần tự trong **cùng một connection** không thể minh họa đúng hai transaction đồng thời độc lập?

**Gợi ý:** Một connection không đại diện cho hai transaction đồng thời theo cách cần để tạo interleaving này.

### Bài 30 — Bảo vệ mọi writer

Nếu API dùng SERIALIZABLE nhưng một script admin không kiểm tra invariant rồi UPDATE trái phép, bài toán đã được bảo vệ hoàn toàn chưa?

**Gợi ý:** Chưa. Các đường ghi phải tuân thủ cùng quy tắc và quyền; constraints nếu biểu diễn được nên được đặt tại DB.

## 38. Bảng ghi nhớ nhanh

| Chủ đề | Ghi nhớ |
|---|---|
| Dirty read | Đọc dữ liệu của transaction khác chưa commit |
| PostgreSQL có dirty read? | Không, kể cả READ UNCOMMITTED |
| Nonrepeatable read | Cùng một hàng được đọc lại khác giá trị trong một transaction |
| Phantom read | Tập hàng thỏa một predicate thay đổi giữa các lần đọc |
| Read skew | Nhiều giá trị được đọc từ các lát cắt commit khác nhau |
| Lost update | Một thay đổi bị mất do ghi đè từ dữ liệu cũ |
| Dirty write | Ghi đè thay đổi đang chưa commit của transaction khác |
| Write skew | Các transaction đọc điều kiện chung, ghi những hàng khác và phá invariant |
| PostgreSQL READ UNCOMMITTED | Hoạt động như READ COMMITTED |
| PostgreSQL READ COMMITTED | Snapshot theo statement |
| PostgreSQL REPEATABLE READ | Snapshot giao dịch, ngăn phantom truyền thống |
| PostgreSQL REPEATABLE READ có write skew? | Có thể |
| PostgreSQL SERIALIZABLE | SSI, không cho lịch commit trái serializability |
| Serialization failure | SQLSTATE 40001 |
| Deadlock | SQLSTATE 40P01 |
| Lock not available | SQLSTATE 55P03 |
| Unique violation | SQLSTATE 23505 |
| Row lock FOR UPDATE | Khóa hàng đã chọn, không tự khóa mọi phantom tương lai |
| Atomic stock update | UPDATE stock=stock-qty WHERE stock>=qty RETURNING |
| Optimistic locking | WHERE version=old_version, kiểm tra row count |
| Báo cáo nhiều SELECT nhất quán | REPEATABLE READ READ ONLY |
| Serializable read-only safe snapshot | SERIALIZABLE READ ONLY DEFERRABLE |
| Retry sau 40001 | Retry **toàn transaction** và quyết định lại |
| External effects | Idempotency/outbox/reconciliation |
| Bảo vệ tính duy nhất | UNIQUE constraint, không chỉ pre-check |
| Bảo vệ nhiều hàng phức tạp | SERIALIZABLE hoặc protocol đồng bộ phù hợp |
| Transaction dài | Snapshot/lock contention/VACUUM |
| Kiểm thử anomalies | Hai phiên thực với interleaving có chủ đích |

---

## Kết luận

**Dirty read, nonrepeatable read và phantom read** mô tả ba vấn đề khác nhau về **quan sát dữ liệu** khi nhiều transaction xen kẽ. Dirty read đọc giá trị chưa commit; nonrepeatable read thấy cùng một hàng thay đổi giữa hai lần đọc; phantom read thấy **tập hàng** thỏa predicate thay đổi. PostgreSQL không cho dirty read ngay cả ở READ UNCOMMITTED, nhưng READ COMMITTED vẫn cho phép nonrepeatable read và phantom giữa các câu lệnh.

Ở **REPEATABLE READ**, PostgreSQL cung cấp snapshot nhất quán cho transaction, ngăn nonrepeatable read và phantom truyền thống. Tuy nhiên, điều đó **không đồng nghĩa SERIALIZABLE**: **write skew** có thể xảy ra khi hai transaction đọc cùng bất biến rồi cập nhật những hàng khác nhau. **SERIALIZABLE/SSI** giải quyết lớp serialization anomaly đó bằng cách cho các transaction chạy đồng thời nhưng abort một transaction khi cần, thường thông qua **SQLSTATE 40001**.

Trong ứng dụng thực tế, hãy kết hợp isolation với **constraint, UPDATE nguyên tử, optimistic version, row locks, retry toàn transaction và idempotency**. Đối với một số quy tắc cùng hàng, câu SQL có điều kiện có thể đơn giản và hiệu quả hơn việc đẩy toàn bộ workload lên SERIALIZABLE; với bất biến nhiều hàng khó biểu diễn bằng constraint, SERIALIZABLE hoặc một giao thức đồng bộ chặt chẽ có thể cần thiết.

Điều quan trọng nhất là **xác định dữ liệu nào phải luôn đúng sau COMMIT, vẽ lịch các transaction có thể xen kẽ, và kiểm thử trên các kết nối độc lập**. Khi hiểu rõ MVCC, snapshot và những bất thường ngoài ba tên quen thuộc, bạn mới có thể chọn đúng cơ chế để PostgreSQL và ứng dụng giữ được tính nhất quán dưới tải đồng thời.
