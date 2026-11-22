# Mức cô lập Read Committed, Repeatable Read và Serializable trong PostgreSQL

Một ứng dụng đặt hàng có thể đọc số lượng tồn kho, kiểm tra xem còn hàng hay không rồi trừ kho; một hệ thống phân ca có thể kiểm tra còn ít nhất một người trực trước khi cho một người nghỉ; một báo cáo có thể đọc tổng doanh thu nhiều lần trong lúc các giao dịch khác đang ghi dữ liệu. Nếu các phiên làm việc chạy đồng thời, **cùng một đoạn SQL** có thể quan sát dữ liệu hoặc dẫn tới kết quả khác nhau tùy **mức cô lập giao dịch** (*transaction isolation level*).

PostgreSQL có ba mức cô lập với hành vi thực thi khác nhau đáng quan tâm:

- **Read Committed**: mặc định, mỗi câu lệnh đọc nhìn thấy một snapshot của dữ liệu đã commit trước khi câu lệnh bắt đầu.
- **Repeatable Read**: một transaction giữ snapshot ổn định trong suốt quá trình làm việc; PostgreSQL dùng *snapshot isolation*, ngăn cả nonrepeatable read lẫn phantom read, nhưng vẫn có thể gặp **write skew** và các bất thường không thể tuần tự hóa.
- **Serializable**: mức mạnh nhất, chỉ cho phép các transaction commit nếu kết quả tương đương một thứ tự chạy lần lượt; PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để phát hiện những quan hệ đọc–ghi nguy hiểm và có thể hủy một transaction với **SQLSTATE `40001`**, yêu cầu ứng dụng chạy lại **toàn bộ transaction**.

Không có mức nào là “đọc dữ liệu mới nhất mọi lúc và không bao giờ chờ hoặc lỗi”. Mức cô lập là một **hợp đồng về điều gì được phép quan sát và điều gì xảy ra khi cạnh tranh**, không phải lựa chọn chỉ để tối ưu tốc độ.

Bài học hướng dẫn lý thuyết, ví dụ có thể chạy bằng **hai cửa sổ `psql`/SQL client độc lập**, các hiện tượng cạnh tranh, cơ chế khắc phục, ví dụ Java/JDBC và bài tập. Nội dung đặt trong ngữ cảnh PostgreSQL, vì các hệ quản trị khác có thể định nghĩa mức tên giống nhau nhưng hành vi thực tế khác.

## 1. Giao dịch và tính cô lập

Một giao dịch (*transaction*) gom một hoặc nhiều câu SQL thành một đơn vị được xác nhận bằng `COMMIT` hoặc hủy bằng `ROLLBACK`:

~~~sql
BEGIN;

UPDATE some_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE some_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Ví dụ trên dùng bảng `some_accounts` giả định. Mục tiêu là hai cập nhật cùng thuộc một giao dịch. Nếu có lỗi và transaction bị rollback, các thay đổi có tính giao dịch sẽ được hoàn tác.

Trong bộ tính chất ACID:

- **Atomicity:** các thay đổi của một transaction được xác nhận hoặc hoàn tác theo quy tắc giao dịch.
- **Consistency:** những ràng buộc và bất biến được thể hiện/kiểm tra đúng phải được duy trì; database không tự biết mọi quy tắc nghiệp vụ chưa được mô tả.
- **Isolation:** các transaction chạy đồng thời không được quan sát hay tương tác với nhau theo những cách bị cấm ở mức cô lập đã chọn.
- **Durability:** dữ liệu đã commit có bảo đảm bền vững theo cấu hình/hệ thống lưu trữ.

Ở bài này, câu hỏi trọng tâm không phải “có commit không?” mà là **transaction A đang chạy được phép nhìn thấy gì khi transaction B ghi và commit?** và **các thay đổi của cả A/B có thể commit cùng nhau mà vi phạm bất biến nghiệp vụ không?**

### 1.1. Hai transaction cùng thao tác trên dữ liệu

~~~text
Thời gian →

Session A                           Session B
---------                           ---------
BEGIN
SELECT price = 100
                                    BEGIN
                                    UPDATE price = 120
                                    COMMIT
SELECT price = ?
COMMIT
~~~

Nếu A dùng **Read Committed**, câu `SELECT` thứ hai có thể thấy `120`. Nếu A dùng **Repeatable Read**, A vẫn nhìn `100` từ snapshot đã thiết lập. **Serializable** cũng giữ snapshot ổn định nhưng bổ sung kiểm soát tính tuần tự hóa khi có các phụ thuộc đọc–ghi nguy hiểm.

### 1.2. Isolation không đồng nghĩa chỉ khóa

PostgreSQL dùng **MVCC — Multi-Version Concurrency Control**. Khi cập nhật hàng, hệ thống có thể có nhiều phiên bản dữ liệu (*row versions*) được quản lý bằng thông tin transaction; snapshot quyết định phiên bản nào đang nhìn thấy được. Nhờ đó, các truy vấn `SELECT` thông thường có thể đọc dữ liệu đã commit mà không phải chờ mọi writer đang cập nhật cùng hàng.

MVCC không có nghĩa “không bao giờ có khóa”: `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE`, DDL và nhiều thao tác khác vẫn dùng khóa phù hợp. Serializable còn theo dõi quan hệ đọc–ghi bằng các **predicate locks/SIReadLock** phục vụ phát hiện serialization anomaly; bản thân các khóa SSI này **không khóa chặn writer theo kiểu row lock thông thường**.

## 2. Bốn hiện tượng phải nhận diện

### 2.1. Dirty read — đọc dữ liệu chưa commit

Session A thay giá từ 100 thành 120 nhưng **chưa commit**. Session B thấy 120 trước khi A commit; sau đó A rollback. B đã dựa vào một giá trị không bao giờ được xác nhận.

~~~text
A: UPDATE price=120      (chưa commit)
B: SELECT price -> 120  (dirty read)
A: ROLLBACK             (giá quay lại 100)
~~~

PostgreSQL **không cho dirty read** ở các mức cô lập được triển khai, kể cả khi yêu cầu `READ UNCOMMITTED`; mức này được xử lý như Read Committed.

### 2.2. Nonrepeatable read — đọc lại cùng hàng nhưng khác giá trị

~~~text
A: SELECT price -> 100
B: UPDATE price=120; COMMIT
A: SELECT price -> 120
~~~

Một transaction đọc cùng một hàng hai lần, nhận hai giá trị khác nhau do transaction khác commit ở giữa. **Read Committed cho phép** hiện tượng này; **Repeatable Read và Serializable ngăn** hiện tượng này trong PostgreSQL.

### 2.3. Phantom read — tập hàng thỏa điều kiện thay đổi

~~~text
A: SELECT COUNT(*) WHERE status='PAID' -> 1
B: INSERT một đơn PAID; COMMIT
A: SELECT COUNT(*) WHERE status='PAID' -> 2
~~~

Ở lần đọc thứ hai, một hàng mới thỏa điều kiện `WHERE` xuất hiện — gọi là **phantom**. Read Committed cho phép. PostgreSQL Repeatable Read **không cho phép phantom read**, dù tiêu chuẩn SQL chỉ yêu cầu tối thiểu rằng Repeatable Read phải ngăn dirty/nonrepeatable read và có thể cho phantom.

### 2.4. Serialization anomaly — kết quả không tương đương chạy tuần tự

Giả sử phải luôn có ít nhất một bác sĩ trực:

~~~text
Ban đầu: Bác sĩ An = đang trực, Bình = đang trực.

Transaction A:
    Đếm bác sĩ đang trực: 2.
    Cho An nghỉ.

Transaction B:
    Đếm bác sĩ đang trực: 2.
    Cho Bình nghỉ.
~~~

Nếu cả hai cùng dựa trên snapshot ban đầu và ghi **hai hàng khác nhau**, cả hai có thể commit ở **Repeatable Read**. Kết quả: **0 người trực**, vi phạm quy tắc. Đây là **write skew**, một dạng serialization anomaly.

Nếu chạy **tuần tự đúng logic**, transaction thứ hai phải thấy chỉ còn 1 người trực và không được cho người còn lại nghỉ. Serializable bảo đảm không thể có **cả hai transaction kiểu này commit cùng một kết quả không tuần tự hóa được**.

## 3. Ma trận hành vi của PostgreSQL

| Hiện tượng | Read Committed | Repeatable Read (PostgreSQL) | Serializable |
| --- | --- | --- | --- |
| Dirty read | Không | Không | Không |
| Nonrepeatable read | Có thể | Không | Không |
| Phantom read | Có thể | **Không** | Không |
| Serialization anomaly / write skew | Có thể | **Có thể** | Không ở những transaction cùng tuân thủ Serializable và commit thành công |
| Snapshot chính | Từng câu lệnh | Ổn định từ câu lệnh đầu thiết lập snapshot | Ổn định, cộng kiểm tra SSI |
| Có thể phải retry vì `40001`? | Không phải hành vi thông thường của mức này | **Có**, khi cạnh tranh cập nhật hàng đã thay đổi sau snapshot | **Có**, kể cả xung đột phụ thuộc đọc–ghi |

**Hai điểm đặc thù PostgreSQL phải nhớ:**

1. `READ UNCOMMITTED` được chấp nhận về cú pháp nhưng **hoạt động như Read Committed**, không mở dirty read.
2. PostgreSQL `REPEATABLE READ` là **snapshot isolation** và **ngăn phantom**, mạnh hơn yêu cầu tối thiểu của SQL standard; tuy nhiên **không tương đương Serializable** vì vẫn có write skew.

Các từ “có thể” phản ánh hiện tượng **được phép xảy ra**, không có nghĩa cứ hai transaction đồng thời là chắc chắn nhìn thấy hiện tượng đó. Kết quả còn tùy trình tự lệnh, thời điểm snapshot và điều kiện dữ liệu.

### 3.1. So sánh theo nhu cầu nghiệp vụ

| Nhu cầu | Hướng khởi đầu |
| --- | --- |
| CRUD phổ thông, mỗi câu SQL đọc snapshot mới | Read Committed |
| Báo cáo nhiều câu `SELECT` cần cùng snapshot | Repeatable Read, thường `READ ONLY` |
| Bất biến qua nhiều hàng/điều kiện phụ thuộc, nhiều writer đồng thời | Serializable **và retry toàn transaction**, hoặc cơ chế khóa/constraint đúng thiết kế |
| Trừ tồn kho của **một hàng cụ thể** có điều kiện đủ số lượng | Thường có thể dùng một `UPDATE ... WHERE quantity >= ...` nguyên tử tại Read Committed |
| Có thể chờ lúc đầu để được snapshot đọc an toàn, báo cáo dài | `SERIALIZABLE READ ONLY DEFERRABLE` khi phù hợp |

Không nên chọn Serializable chỉ theo khẩu hiệu “an toàn nhất” mà không xây **đường xử lý serialization failure**; cũng không nên mặc định Read Committed đủ cho bất kỳ thao tác nào chỉ vì đó là mức mặc định.

## 4. Cách thiết lập và kiểm tra isolation

### 4.1. Xem cấu hình hiện tại

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;

SELECT
    current_setting('default_transaction_isolation')
        AS session_default_isolation,
    current_setting('transaction_isolation')
        AS current_isolation;
~~~

Ở một PostgreSQL chưa điều chỉnh, session default thường là `read committed`.

### 4.2. Thiết lập cho một transaction

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT current_setting('transaction_isolation');

COMMIT;
~~~

Tương tự:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- Những SELECT/UPDATE của transaction này...
COMMIT;
~~~

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
-- Những SELECT/UPDATE của transaction này...
COMMIT;
~~~

Hoặc xác định ngay lúc mở transaction:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT current_setting('transaction_isolation');
COMMIT;
~~~

### 4.3. SET TRANSACTION phải đặt sớm

PostgreSQL không cho thay đổi isolation level **sau câu lệnh truy vấn hoặc sửa dữ liệu đầu tiên** trong transaction, chẳng hạn `SELECT`, `INSERT`, `UPDATE` hay `DELETE`. Nên dùng:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT ...;
-- ...
COMMIT;
~~~

Không viết:

~~~sql
-- CẢNH BÁO: thứ tự sai, có thể lỗi.
-- BEGIN;
-- SELECT ...;
-- SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Tính chất `SET TRANSACTION` áp dụng **chỉ cho transaction hiện tại**, không thay đổi các transaction sau.

### 4.4. Thiết lập mặc định cho các transaction mới của session

~~~sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL REPEATABLE READ;

SHOW default_transaction_isolation;

BEGIN;
SELECT current_setting('transaction_isolation');
COMMIT;

-- Trả về mặc định phục vụ bài lab/session:
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL READ COMMITTED;
~~~

Khi dùng connection pool, **cấu hình ở cấp session có thể còn tồn tại trên kết nối được tái sử dụng** nếu pool/driver không khôi phục. Ứng dụng cần áp dụng và phục hồi connection state một cách có kiểm soát, tốt nhất thiết lập rõ isolation cho những transaction có yêu cầu đặc biệt.

### 4.5. READ ONLY và READ WRITE

Isolation level và chế độ đọc/ghi là **hai chiều khác nhau**:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ
    READ ONLY;

SELECT COUNT(*) FROM pg_catalog.pg_class;

COMMIT;
~~~

`READ ONLY` không phải “mức cô lập thứ tư”: nó giới hạn các loại thao tác ghi được phép trong transaction. Cơ chế read-only của PostgreSQL có các ngoại lệ/chi tiết như bảng tạm; không xem nó là biện pháp phân quyền thay role/GRANT/RLS.

## 5. Chuẩn bị môi trường thực hành hai phiên

Để quan sát cạnh tranh, mở **hai kết nối riêng biệt** tới cùng database PostgreSQL:

- **Session A:** cửa sổ `psql` hoặc SQL editor thứ nhất.
- **Session B:** cửa sổ thứ hai, dùng connection riêng.
- Mỗi session tự chạy `BEGIN`/`COMMIT`/`ROLLBACK` theo kịch bản.
- Không ghép toàn bộ các lệnh của A/B vào **một connection**, vì khi đó không có hai transaction đồng thời.

**An toàn:** chỉ dùng database lab; không chạy ví dụ deadlock/chờ lock trên production. Một câu SQL có thể bị chặn để đợi transaction bên kia; hãy làm theo thứ tự được mô tả và kết thúc mọi transaction trước khi reset. Khi một transaction lỗi, dùng `ROLLBACK` để đưa connection về trạng thái dùng được.

### 5.1. Schema và bảng lab

~~~sql
CREATE SCHEMA iso_lab_216;

CREATE TABLE iso_lab_216.price_tags (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0)
);

CREATE TABLE iso_lab_216.orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'NEW', 'CANCELLED')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0)
);

CREATE TABLE iso_lab_216.counters (
    counter_id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
        CHECK (value >= 0)
);

CREATE TABLE iso_lab_216.stock (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity >= 0)
);

CREATE TABLE iso_lab_216.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_duty BOOLEAN NOT NULL
);

CREATE TABLE iso_lab_216.duty_guard (
    guard_id INTEGER PRIMARY KEY
);
~~~

### 5.2. Nạp dữ liệu ban đầu

~~~sql
INSERT INTO iso_lab_216.price_tags
    (item_id, item_name, price)
VALUES
    (1, 'Sách SQL', 100.00);

INSERT INTO iso_lab_216.orders
    (order_id, status, amount)
VALUES
    (101, 'PAID', 200.00),
    (102, 'NEW',  50.00);

INSERT INTO iso_lab_216.counters
    (counter_id, value)
VALUES (1, 10);

INSERT INTO iso_lab_216.stock
    (sku, quantity)
VALUES ('SKU-A', 5);

INSERT INTO iso_lab_216.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'Bác sĩ An', TRUE),
    (2, 'Bác sĩ Bình', TRUE);

INSERT INTO iso_lab_216.duty_guard(guard_id)
VALUES (1);
~~~

Các giá trị đầu quan trọng:

| Bảng | Khóa | Dữ liệu |
| --- | --- | --- |
| `price_tags` | item_id=1 | price=100.00 |
| `orders` | 101 | PAID |
| `orders` | 102 | NEW |
| `counters` | counter_id=1 | value=10 |
| `stock` | SKU-A | quantity=5 |
| `on_call` | doctor_id=1,2 | Cả hai đang trực |
| `duty_guard` | guard_id=1 | Một hàng dùng làm điểm khóa chung |

### 5.3. Reset giữa các bài

Sau khi **cả A và B đều đã `COMMIT` hoặc `ROLLBACK`** và không còn transaction mở, chạy trên một session:

~~~sql
UPDATE iso_lab_216.price_tags
SET price = 100.00
WHERE item_id = 1;

DELETE FROM iso_lab_216.orders
WHERE order_id = 103;

UPDATE iso_lab_216.counters
SET value = 10
WHERE counter_id = 1;

UPDATE iso_lab_216.stock
SET quantity = 5
WHERE sku = 'SKU-A';

UPDATE iso_lab_216.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
~~~

**Không reset khi session A/B vẫn giữ transaction**: việc đó có thể chờ lock, làm lệch snapshot hoặc làm kịch bản cạnh tranh khó hiểu. `ROLLBACK` của session A **không hoàn tác** những thay đổi mà session B đã `COMMIT`; cần reset chính những thay đổi đó.

## 6. Read Committed: snapshot theo từng câu lệnh

Read Committed là mức mặc định của PostgreSQL. Với `SELECT` thông thường:

1. Câu lệnh không nhìn thấy những thay đổi chưa commit của transaction khác.
2. Câu lệnh nhìn thấy các thay đổi đã commit **trước lúc câu lệnh bắt đầu**.
3. Hai câu lệnh `SELECT` trong cùng một transaction có thể nhận snapshot khác nhau.
4. Transaction **vẫn nhìn thấy những thay đổi của chính nó**, kể cả trước `COMMIT`.

### 6.1. Thí nghiệm nonrepeatable read

**Điều kiện đầu:** `item_id=1` có `price=100`.

<escape>**Session A — mở transaction và đọc lần 1:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

Giữ A chưa commit, chuyển sang B.

<escape>**Session B — thay giá rồi commit:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Quay lại Session A — đọc lần 2:**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 120.00

ROLLBACK;
~~~

Kết quả:

| Thời điểm | Giá A nhìn thấy |
| --- | ---: |
| Trước B commit | 100 |
| Sau B commit | 120 |

Đây là **nonrepeatable read được phép ở Read Committed**. A vẫn ở trong cùng transaction nhưng câu `SELECT` thứ hai nhận **snapshot mới**.

Sau đó reset `price=100` trước thí nghiệm tiếp theo.

### 6.2. Snapshot của một SELECT không thay đổi giữa chừng

Read Committed **không** có nghĩa mỗi hàng trong một `SELECT` được lấy từ thời điểm hoàn toàn tùy ý. Một `SELECT` bình thường dùng snapshot của **lúc bắt đầu chính câu lệnh**, nên commit của session khác trong lúc `SELECT` đang chạy thường **không tự xuất hiện giữa chừng** trong kết quả của câu đó.

Tuy nhiên, các lệnh ghi như `UPDATE`, `DELETE` và `SELECT FOR UPDATE` có quy tắc chờ và kiểm tra lại hàng đích sau cập nhật đồng thời; đây là ngoại lệ quan trọng sẽ học ở phần sau.

### 6.3. Đọc thay đổi của chính mình

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.price_tags
SET price = 140.00
WHERE item_id = 1;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 140.00: cùng transaction nhìn thấy thay đổi của mình.

ROLLBACK;
~~~

Sau rollback, nếu không có session khác thay đổi giá thì giá trở lại như trước transaction (trong bài lab, 100). Quy tắc “thấy thay đổi của chính mình” cũng áp dụng ở Repeatable Read và Serializable, không mâu thuẫn với snapshot ổn định cho các thay đổi từ **transaction khác**.

## 7. Read Committed: phantom read

**Điều kiện đầu:** bảng `orders` chỉ có một đơn `PAID`, `order_id=101`. Đơn `102` là `NEW`.

<escape>**Session A — đếm các đơn PAID lần đầu:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 1
~~~

<escape>**Session B — chèn thêm đơn PAID:**</escape>

~~~sql
BEGIN;

INSERT INTO iso_lab_216.orders
    (order_id, status, amount)
VALUES
    (103, 'PAID', 300.00);

COMMIT;
~~~

<escape>**Session A — đếm lần thứ hai:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 2

ROLLBACK;
~~~

Kết quả tăng từ 1 lên 2 trong cùng transaction A. Đây là **phantom read**: **tập hàng thỏa điều kiện** đã thay đổi, không chỉ giá trị của một hàng cũ.

**Nhớ reset:** sau khi A kết thúc, chạy `DELETE FROM iso_lab_216.orders WHERE order_id=103;` để đưa dữ liệu về trạng thái đầu.

### 7.1. UPDATE hoặc DELETE cũng có thể làm thay đổi tập hàng

Phantom không nhất thiết đến từ `INSERT`. Nếu B đổi một đơn `NEW` thành `PAID` hoặc đổi `PAID` thành `CANCELLED`, số hàng thỏa `WHERE status='PAID'` cũng có thể thay đổi. Bản chất vấn đề là **tập kết quả theo predicate không ổn định giữa hai câu lệnh** ở Read Committed.

## 8. PostgreSQL không có dirty read, kể cả READ UNCOMMITTED

SQL standard có tên mức cô lập `READ UNCOMMITTED`, nhưng PostgreSQL ánh xạ nó tới **Read Committed**.

<escape>**Session A — thay giá nhưng chưa commit:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 999.00
WHERE item_id = 1;

-- Giữ transaction mở, CHƯA COMMIT.
~~~

<escape>**Session B — yêu cầu READ UNCOMMITTED:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00 trong dữ liệu reset ban đầu.

ROLLBACK;
~~~

<escape>**Session A — hoàn tác:**</escape>

~~~sql
ROLLBACK;
~~~

Session B **không thấy `999`** vì đó là dữ liệu chưa commit của A. Lưu ý `SHOW transaction_isolation` có thể hiển thị tên mức đã yêu cầu, nhưng hiệu lực đọc của `READ UNCOMMITTED` trong PostgreSQL vẫn giống Read Committed.

### 8.1. Những thứ không được bảo đảm rollback như bản ghi bảng

Không suy từ ví dụ rằng **mọi** hiệu ứng đều bị rollback. Chẳng hạn `nextval()` của sequence trong PostgreSQL không hoàn tác số sequence đã phát khi transaction rollback. Sequence có các quy tắc đặc biệt không giống hàng MVCC thông thường; **số ID bị bỏ trống không phải bằng chứng dirty read**.

## 9. Repeatable Read: snapshot ổn định trong transaction

Ở PostgreSQL, Repeatable Read nhìn thấy các hàng đã commit trước **snapshot của transaction** và luôn thấy các thay đổi chính transaction ấy đã thực hiện. Snapshot được cố định khi transaction chạy **câu lệnh đầu tiên không phải lệnh điều khiển transaction** (theo tài liệu: thực tế là truy vấn/thao tác dữ liệu đầu tiên), **không nhất thiết đúng thời điểm gõ `BEGIN`**.

### 9.1. So sánh trực tiếp với thí nghiệm Read Committed

**Điều kiện đầu:** `price=100`. Chạy A trước, B sau như hướng dẫn.

<escape>**Session A — tạo snapshot bằng SELECT:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

<escape>**Session B — commit giá mới:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Session A — đọc lại trong transaction cũ:**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- Vẫn 100.00

COMMIT;
~~~

<escape>**Session A — bắt đầu transaction mới (hoặc SELECT ngoài transaction):**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 120.00
~~~

Trong transaction Repeatable Read cũ, B commit không làm snapshot của A thay đổi. **A không đọc dữ liệu chưa commit; A đang đọc một phiên bản dữ liệu cũ nhưng nhất quán với snapshot đã chọn.**

Reset `price=100` sau khi cả hai session kết thúc.

### 9.2. BEGIN không phải thời điểm snapshot cố định ngay lập tức

Phân biệt hai lịch trình:

~~~text
Kịch bản 1:
A: BEGIN REPEATABLE READ
A: SELECT price -> 100   (snapshot được thiết lập)
B: UPDATE price=120; COMMIT
A: SELECT price -> 100
~~~

~~~text
Kịch bản 2:
A: BEGIN REPEATABLE READ
B: UPDATE price=120; COMMIT
A: SELECT price -> 120   (đây mới là đọc tạo snapshot)
A: SELECT price -> 120
~~~

**Không dùng `BEGIN` như một dấu mốc snapshot tuyệt đối** nếu chưa có thao tác đọc/ghi tạo snapshot. Để có kết quả nhất quán, hiểu rõ thời điểm transaction thực sự bắt đầu nhìn dữ liệu.

### 9.3. Không nhầm snapshot ổn định với “khóa toàn bảng”

Session B vẫn có thể cập nhật và commit hàng `price_tags` dù A đang thực hiện `SELECT` Repeatable Read. A không cần giữ khóa độc quyền trên hàng đó để tiếp tục nhìn phiên bản cũ. Đây là ưu điểm của MVCC: **reader và writer không nhất thiết phải chặn nhau** cho các thao tác thông thường.

## 10. Repeatable Read cũng chặn phantom trong PostgreSQL

**Điều kiện đầu:** một đơn `PAID`, chưa có `order_id=103`.

<escape>**Session A — mở RR và đếm:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 1
~~~

<escape>**Session B — chèn đơn mới và commit:**</escape>

~~~sql
BEGIN;
INSERT INTO iso_lab_216.orders(order_id, status, amount)
VALUES (103, 'PAID', 300.00);
COMMIT;
~~~

<escape>**Session A — vẫn cùng transaction:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- Vẫn 1.

COMMIT;
~~~

<escape>**Sau khi A commit:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 2 trong transaction mới.
~~~

Trong PostgreSQL Repeatable Read, hai truy vấn đọc cùng snapshot, nên **hàng phantom do B thêm không xuất hiện trong transaction A**. Điều này **không chứng minh Repeatable Read là Serializable**: write skew vẫn có thể xảy ra vì các transaction có thể dựa trên những snapshot cũ nhưng cập nhật **những hàng khác nhau**.

Reset bằng cách xóa `order_id=103` sau khi hai session đã xong.

## 11. Repeatable Read: vẫn có thể lỗi khi cố UPDATE hàng đã bị thay đổi

Snapshot ổn định **không đồng nghĩa transaction có quyền ghi đè mọi hàng dựa trên giá trị cũ**. PostgreSQL Repeatable Read có thể từ chối cập nhật khi một transaction khác đã commit thay đổi **cùng hàng** sau snapshot của transaction hiện tại.

**Điều kiện đầu:** `price=100`.

<escape>**Session A — RR, tạo snapshot trước:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

<escape>**Session B — thay đúng hàng đó rồi commit:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Session A — thử cập nhật hàng đã thay đổi:**</escape>

~~~sql
UPDATE iso_lab_216.price_tags
SET price = 130.00
WHERE item_id = 1;

-- Dự kiến lỗi:
-- ERROR: could not serialize access due to concurrent update
-- SQLSTATE: 40001

ROLLBACK;
~~~

PostgreSQL sẽ không đơn giản cho A ghi đè lên phiên bản B vừa commit như thể không có xung đột. Sau `40001`, A phải **rollback và chạy lại toàn bộ transaction** nếu nghiệp vụ cần tiếp tục.

### 11.1. Có phải lỗi 40001 chỉ xuất hiện ở Serializable?

**Không.** Repeatable Read cũng có thể nhận serialization failure khi tranh chấp cập nhật/khóa hàng đã bị thay đổi sau snapshot. Khác biệt là Serializable còn có thể phát hiện **quan hệ phụ thuộc đọc–ghi giữa các hàng khác nhau** dẫn đến write skew/serialization anomaly.

### 11.2. Read-only Repeatable Read không cần loại retry này

Nếu A chỉ `SELECT` trên snapshot Repeatable Read, B cập nhật và commit hàng đó không khiến A mắc lỗi vì “cần ghi hàng đã đổi”. Theo tài liệu PostgreSQL, read-only transactions ở mức Repeatable Read không có serialization conflicts kiểu này. Nhưng khi thêm `UPDATE` hoặc `SELECT FOR UPDATE`, tình huống có thể thay đổi.

## 12. Read Committed: UPDATE chờ rồi kiểm tra lại điều kiện WHERE

Một trường hợp khác biệt quan trọng giữa Read Committed và Repeatable Read là xử lý **cập nhật cạnh tranh trên cùng hàng**.

Trong Read Committed, nếu một `UPDATE` nhắm tới hàng mà transaction khác đang giữ khóa ghi, nó có thể **chờ**. Nếu transaction kia commit, PostgreSQL có thể thử áp dụng câu lệnh lên **phiên bản mới nhất của hàng đích** và **kiểm tra lại điều kiện `WHERE`**.

### 12.1. Trừ tồn kho bằng một UPDATE có điều kiện

**Điều kiện đầu:** `SKU-A` còn `quantity=5`. Hai khách đồng thời muốn mua **4 sản phẩm**; chỉ một người được phép mua thành công.

<escape>**Session A — bắt đầu và trừ 4:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING sku, quantity;
-- 1 hàng, quantity mới = 1.

-- Giữ A chưa commit.
~~~

<escape>**Session B — gửi cùng yêu cầu:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING sku, quantity;
-- Có thể CHỜ Session A kết thúc.
~~~

Trong lúc B đang chờ, quay lại A:

<escape>**Session A — commit:**</escape>

~~~sql
COMMIT;
~~~

Khi B được chạy tiếp, PostgreSQL thấy phiên bản mới của `SKU-A` có `quantity=1`. Điều kiện `quantity >= 4` **không còn đúng**, nên B cập nhật **0 hàng**.

<escape>**Session B — kết thúc:**</escape>

~~~sql
COMMIT;
~~~

Kết quả cuối:

- Chỉ một yêu cầu trừ 4 thành công.
- `quantity=1`, không thành số âm.
- Ứng dụng phải xem **rowcount/RETURNING** để quyết định “đã giữ hàng” hay “không đủ hàng”.

**Nếu A rollback thay vì commit**, B có thể tiếp tục trên phiên bản ban đầu và cập nhật thành công. Hai kết quả tương ứng với hai lịch sử commit khác nhau, không phải bug.

### 12.2. Vì sao đây là mẫu tốt?

Phép kiểm tra và trừ số lượng diễn ra trong **cùng một statement trên đúng hàng**, dưới sự bảo vệ của khóa ghi và cơ chế recheck. Không phải:

~~~text
SELECT quantity
→ ứng dụng kiểm tra
→ chờ vài giây
→ UPDATE quantity = giá_trị_cũ - 4
~~~

Khoảng thời gian giữa read và write trong mẫu thứ hai có thể làm quyết định dựa trên dữ liệu cũ.

### 12.3. Không suy rộng thành mọi bất biến đều được bảo vệ

Một lệnh `UPDATE stock SET quantity=quantity-4 WHERE quantity>=4` bảo vệ một ràng buộc **trên một hàng stock xác định**. Bất biến như “tổng tồn kho trên tất cả chi nhánh ít nhất 10” hoặc “luôn còn một bác sĩ trực trong nhiều hàng” phức tạp hơn; nó có thể cần Serializable, khóa phối hợp hoặc thiết kế constraint/transaction khác.

## 13. Lost update ở tầng ứng dụng: đọc rồi ghi giá trị đã tính sẵn

Không phải mọi lỗi cập nhật mất dữ liệu đều do PostgreSQL thực hiện hai lệnh `UPDATE` cùng lúc. Một lỗi phổ biến xuất hiện khi **ứng dụng đọc giá trị về bộ nhớ, tự tính giá mới, rồi gửi một hằng số để ghi đè**.

### 13.1. Hai worker cùng tăng bộ đếm từ 10

**Điều kiện đầu:** `counters.value=10`.

<escape>**Session A — đọc:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM iso_lab_216.counters
WHERE counter_id = 1;
-- 10
~~~

<escape>**Session B — cũng đọc trước khi A commit:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM iso_lab_216.counters
WHERE counter_id = 1;
-- 10
~~~

Cả hai chương trình đều tính trong bộ nhớ: `newValue = 10 + 1 = 11`.

<escape>**Session A — gửi giá trị cố định:**</escape>

~~~sql
UPDATE iso_lab_216.counters
SET value = 11
WHERE counter_id = 1;
COMMIT;
~~~

<escape>**Session B — gửi giá trị cũ đã tính:**</escape>

~~~sql
UPDATE iso_lab_216.counters
SET value = 11
WHERE counter_id = 1;
COMMIT;
~~~

Kết quả cuối **11** thay vì **12**. Hai lần tăng logic đã xảy ra, nhưng giá trị tăng thứ hai bị **mất** bởi phép ghi lại một hằng số cũ.

### 13.2. Sửa bằng phép cập nhật nguyên tử trong database

Sau reset value=10, mỗi worker gửi:

~~~sql
UPDATE iso_lab_216.counters
SET value = value + 1
WHERE counter_id = 1
RETURNING value;
~~~

Tại Read Committed, khi hai statement này tranh chấp cùng hàng, một transaction sẽ chờ transaction kia và thao tác trên phiên bản đã cập nhật sau khi khóa được giải phóng (theo quy tắc mức này). Nếu cả hai commit thành công, **giá trị cuối là 12**.

### 13.3. Nếu logic ứng dụng phải dùng giá trị đọc

Có thể dùng:

- `SELECT ... FOR UPDATE` để khóa hàng trước khi đọc–tính–ghi trong transaction;
- Optimistic locking bằng cột `version`: `UPDATE ... SET value=?, version=version+1 WHERE id=? AND version=?`, kiểm tra rowcount và retry khi không khớp;
- Isolation cao hơn với **retry khi `40001`**;
- Thiết kế lại thành một statement SQL nguyên tử nếu có thể.

**Không mặc định chuyển tất cả transaction lên Serializable** nếu chỉ cần tăng một counter đúng; một phép `UPDATE SET value=value+1` có thể đơn giản và hiệu quả hơn.

## 14. Repeatable Read vẫn có thể write skew

Đây là thí nghiệm phân biệt Repeatable Read với Serializable rõ nhất.

**Quy tắc nghiệp vụ:** luôn có ít nhất **một** bác sĩ trực. Bảng `on_call` có hai hàng ban đầu:

| doctor_id | doctor_name | on_duty |
| ---: | --- | --- |
| 1 | Bác sĩ An | TRUE |
| 2 | Bác sĩ Bình | TRUE |

Mỗi bác sĩ được nghỉ **chỉ nếu đang có ít nhất hai người trực**. Hai transaction cùng muốn cho **hai người khác nhau** nghỉ.

### 14.1. Lịch trình hai session ở Repeatable Read

<escape>**Session A — đọc số người trực:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session B — cũng đọc trước khi A ghi/commit:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

Cả hai đã thiết lập snapshot riêng, đều nhìn thấy hai bác sĩ đang trực.

<escape>**Session A — cho An nghỉ:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
-- 1 hàng.
~~~

<escape>**Session B — cho Bình nghỉ:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
-- 1 hàng.
~~~

Hai lệnh ghi **hai hàng khác nhau**, nên không nhất thiết đụng nhau ở row lock.

<escape>**Lần lượt commit hai session:**</escape>

~~~sql
-- Session A:
COMMIT;
~~~

~~~sql
-- Session B:
COMMIT;
~~~

<escape>**Kiểm tra bằng transaction mới:**</escape>

~~~sql
SELECT
    COUNT(*) FILTER (WHERE on_duty) AS doctors_remaining,
    COUNT(*) AS total_doctors
FROM iso_lab_216.on_call;
-- doctors_remaining = 0, total_doctors = 2.
~~~

**Cả hai có thể commit thành công tại Repeatable Read**, và kết quả là không còn người trực. Mỗi transaction riêng lẻ thấy quy tắc có vẻ được thỏa tại lúc quyết định, nhưng **tập hợp hai commit** vi phạm bất biến.

### 14.2. Vì sao đây là write skew chứ không phải lost update cùng hàng?

- Transaction A đọc tình trạng của **tập bác sĩ**, ghi hàng bác sĩ 1.
- Transaction B đọc cùng tập, ghi hàng bác sĩ 2.
- Không có cùng một hàng đích cần cả hai cập nhật; cập nhật A và B **không đè trực tiếp lên nhau**.
- Vấn đề là **cả hai quyết định trên snapshot cũ** về một điều kiện tổng hợp toàn tập.

Đây là *write skew*: hai transaction ghi lệch sang hai hàng khác nhau, tạo kết quả không phù hợp với một thứ tự tuần tự của hai quyết định “nếu còn ít nhất hai người thì cho một người nghỉ”.

### 14.3. Không thể chữa chỉ bằng cách đọc snapshot lần hai

Ở Repeatable Read, nếu A/B đọc lại `COUNT(*) WHERE on_duty` trước khi commit, mỗi transaction vẫn thấy snapshot của mình cùng thay đổi của chính nó:

- A thấy bác sĩ 1 đã nghỉ, bác sĩ 2 vẫn trực → còn **1** người.
- B thấy bác sĩ 2 đã nghỉ, bác sĩ 1 vẫn trực → còn **1** người.

Mỗi transaction riêng biệt vẫn tưởng còn một người trực, nhưng **tổng hợp hai commit** tạo 0. Đọc lại cùng snapshot không phát hiện thay đổi do transaction kia sau snapshot.

### 14.4. Kết thúc và reset

Sau khi đã xem kết quả, chạy:

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
~~~

Chỉ reset khi A/B đều đã kết thúc; những transaction đã commit không bị đảo bằng `ROLLBACK` của một transaction mới.

## 15. Serializable: thêm kiểm tra tuần tự hóa bằng SSI

**Serializable** trong PostgreSQL cung cấp kết quả commit tương đương việc các transaction Serializable liên quan chạy **lần lượt theo một thứ tự nào đó** (*serial execution*). Nó không nhất thiết thực sự chạy các transaction lần lượt, mà dùng **Serializable Snapshot Isolation (SSI)** để cho phép cạnh tranh ở mức phù hợp và phát hiện những phụ thuộc đọc–ghi có thể dẫn tới anomaly.

### 15.1. SSI xây trên snapshot isolation

Ở Serializable, các truy vấn vẫn đọc snapshot ổn định giống cách đọc của Repeatable Read. Điểm khác là PostgreSQL còn theo dõi các phụ thuộc giữa các transaction, ví dụ:

~~~text
Transaction A đọc hàng/điều kiện X.
Transaction B ghi thứ có thể thay đổi kết quả A đã đọc.
Transaction B cũng đọc một điều kiện mà A có thể thay đổi.
      |
      v
Có thể hình thành vòng phụ thuộc không tuần tự hóa được.
      |
      v
SSI từ chối ít nhất một transaction khi cần,
trả SQLSTATE 40001.
~~~

PostgreSQL không bắt buộc phải chặn mọi writer bằng khóa predicate. Những **`SIReadLock`** trong Serializable chủ yếu phục vụ **phát hiện quan hệ đọc–ghi**, bản thân chúng không chặn writer giống `SELECT ... FOR UPDATE`.

### 15.2. Tính tuần tự hóa chỉ áp dụng cho những transaction commit thành công

Khi có xung đột, một transaction có thể:

~~~text
ERROR: could not serialize access due to
       read/write dependencies among transactions
SQLSTATE: 40001
~~~

Thông báo lỗi chính xác có thể khác tùy nguyên nhân. Transaction lỗi **không được coi là đã hoàn thành nghiệp vụ**. Ứng dụng phải rollback, **đọc lại từ đầu và thực hiện lại toàn bộ quyết định** trong một transaction mới.

### 15.3. Serializable không tự hiểu quy tắc kinh doanh

Giả sử ứng dụng cứ cập nhật `on_duty=FALSE` mà **không đọc/kiểm tra số bác sĩ còn trực**. Serializable chỉ bảo đảm các transaction commit có thể tương đương một lịch chạy tuần tự; một chuỗi lệnh **bản thân đã sai khi chạy tuần tự** vẫn có thể làm dữ liệu sai. Muốn bất biến “luôn còn ít nhất một người trực”, transaction phải có **logic kiểm tra**, hoặc dùng ràng buộc/cơ chế dữ liệu được thiết kế để áp dụng bất biến ấy.

## 16. Thí nghiệm write skew ở Serializable

**Điều kiện đầu:** reset để cả hai bác sĩ đang trực.

<escape>**Session A — Serializable, đọc count:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session B — Serializable, đọc cùng tập trước khi A commit:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session A — tắt duty bác sĩ 1:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
~~~

<escape>**Session B — tắt duty bác sĩ 2:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
~~~

<escape>**Cố gắng commit hai transaction:**</escape>

~~~sql
-- Session A:
COMMIT;
~~~

~~~sql
-- Session B:
COMMIT;
~~~

**Kỳ vọng:** với lịch trình hai transaction Serializable cùng đọc count=2 và ghi hai hàng khác nhau như trên, PostgreSQL sẽ không để **cả hai commit thành công** thành kết quả không tuần tự hóa được. Một transaction sẽ bị từ chối với `serialization_failure` (`40001`), có thể tại `UPDATE` hoặc `COMMIT` tùy tình huống. **Không giả định A hay B chắc chắn là bên thất bại.**

### 16.1. Kiểm tra trạng thái sau khi có transaction thất bại

~~~sql
SELECT
    doctor_id,
    doctor_name,
    on_duty
FROM iso_lab_216.on_call
ORDER BY doctor_id;
~~~

Trong lịch trình chuẩn, một bác sĩ được cho nghỉ, một bác sĩ vẫn trực, vì chỉ một transaction cập nhật thành công và commit.

### 16.2. Retry transaction bị thất bại

Ví dụ transaction B thất bại:

~~~sql
ROLLBACK;

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 1 (nếu A đã commit và chỉ bác sĩ 2 còn trực).
~~~

Ứng dụng thấy `COUNT(*)=1` và **không chạy `UPDATE on_duty=FALSE`** nữa. Khi đó:

~~~sql
COMMIT;
~~~

Quy tắc nghiệp vụ được bảo vệ. **Đây là ví dụ lý do phải retry cả transaction**: nếu chỉ thử chạy lại câu `UPDATE` với kết quả `COUNT=2` đã đọc từ lần trước, bạn có thể phá vỡ bất biến.

### 16.3. Serializable không có nghĩa mỗi lần đều phải chờ toàn bộ transaction khác

SSI có thể cho nhiều transaction không xung đột cùng thực thi và commit. Khi quan hệ phụ thuộc nguy hiểm xảy ra, nó **hủy một transaction** thay vì khóa chặn tất cả các đường đi. Vì vậy Serializable thường dễ viết logic đúng hơn nhưng đổi lại là chi phí theo dõi và yêu cầu retry.

### 16.4. Tất cả writer liên quan phải tuân thủ cùng chính sách

Nếu một ứng dụng bảo vệ quy tắc bằng Serializable nhưng **ứng dụng khác** có thể thay đổi những hàng liên quan ở mức yếu hơn hoặc cập nhật không kiểm tra quy tắc, không nên coi toàn bộ hệ thống tự động được bảo vệ chỉ nhờ một transaction Serializable. Cần quy định rõ **mọi luồng ghi ảnh hưởng bất biến**, hoặc dùng khóa/constraint/procedure tập trung thích hợp.

Reset cả hai bác sĩ thành `on_duty=TRUE` sau khi mọi session đã kết thúc.

## 17. SQLSTATE 40001: tại sao phải retry toàn transaction?

Khi một transaction PostgreSQL đang thực hiện logic:

~~~text
Đọc dữ liệu
    ↓
Kiểm tra bất biến
    ↓
Chọn quyết định
    ↓
Ghi dữ liệu
    ↓
COMMIT
~~~

thì kết quả đã đọc, điều kiện đã kiểm tra và giá trị được tính **chỉ có giá trị trong lịch sử thực thi của transaction ấy**. Nếu transaction bị PostgreSQL từ chối do xung đột tuần tự hóa, ứng dụng không được giữ lại một quyết định từ snapshot cũ rồi chỉ chạy lại câu `UPDATE`/`COMMIT`.

### 17.1. Mẫu retry đúng

~~~text
for attempt = 1..MAX_ATTEMPTS:
    lấy connection
    BEGIN SERIALIZABLE
    thử:
        ĐỌC LẠI tất cả dữ liệu cần thiết
        TÍNH LẠI quyết định nghiệp vụ
        THỰC HIỆN tất cả thao tác ghi trong transaction
        COMMIT
        trả thành công
    nếu SQLSTATE = 40001:
        ROLLBACK nếu còn cần
        giải phóng connection/nguồn lực
        chờ một khoảng ngắn có giới hạn
        thử TOÀN BỘ transaction từ đầu
    nếu lỗi khác:
        ROLLBACK
        báo lỗi theo chính sách
    nếu hết lượt:
        báo xung đột để xử lý hoặc thử lại sau
~~~

**Không viết vòng lặp vô hạn**: nên có số lần thử tối đa, backoff/jitter hợp lý, log đầy đủ và cơ chế trả lỗi khi cạnh tranh quá mức.

### 17.2. Không chỉ retry statement gây lỗi

**Sai về mặt nghiệp vụ:**

~~~text
Đọc count=2 ở transaction đã thất bại.
ROLLBACK.
BEGIN transaction mới.
UPDATE doctor_2 SET on_duty=FALSE.  -- dùng lại quyết định cũ
COMMIT.
~~~

Nếu transaction khác đã cho doctor 1 nghỉ, câu `UPDATE` trong transaction mới có thể phá quy tắc “luôn còn một bác sĩ trực”. Phải **đọc count lại** trong transaction mới.

### 17.3. Lỗi 40001 có thể xuất hiện ở UPDATE hoặc COMMIT

Ứng dụng cần bao vùng xử lý bao gồm **cả `COMMIT`**. Không phải cứ mọi câu `SELECT`/`UPDATE` đã trả về thành công là transaction chắc chắn được xác nhận. SSI có thể phát hiện cần rollback ở giai đoạn commit.

Tại PostgreSQL, SQLSTATE chuẩn để nhận diện serialization failure là **`40001`**; nên kiểm tra **SQLSTATE** thay vì khớp chuỗi thông báo lỗi, vì thông báo có thể thay đổi theo phiên bản, locale hoặc tình huống.

### 17.4. Các lỗi khác không nên retry mù

| SQLSTATE điển hình | Tên/ý nghĩa | Cách tiếp cận |
| --- | --- | --- |
| `40001` | `serialization_failure` | Retry **toàn transaction**, có giới hạn |
| `40P01` | `deadlock_detected` | Thường có thể retry **toàn transaction** nếu thao tác an toàn và có giới hạn |
| `23505` | `unique_violation` | Phân tích xung đột khóa; không mặc định retry tất cả |
| `23514` | `check_violation` | Sửa dữ liệu/logic vi phạm CHECK |
| `23503` | `foreign_key_violation` | Sửa quan hệ dữ liệu hoặc thứ tự nghiệp vụ |
| `55P03` | `lock_not_available` | Xem chính sách timeout/NOWAIT, tránh lặp mù |

Ở mức Serializable, một số race insert khóa duy nhất có thể dẫn tới `23505` ngay cả khi application đã kiểm tra trước. Điều đó **không làm mọi lỗi `23505` trở thành lỗi có thể retry tự động**: cần hiểu invariant, quy ước khóa và liệu request có an toàn để lặp lại.

### 17.5. Những hiệu ứng ngoài database cần quản lý riêng

Không gửi email, gọi API thanh toán, phát sự kiện không-idempotent hoặc ghi file bên ngoài **mỗi lần thử** như thể transaction chắc chắn sẽ commit:

~~~text
Try 1:
    Gửi email xác nhận
    UPDATE trong PostgreSQL
    COMMIT -> 40001

Try 2:
    Gửi lại email xác nhận
    UPDATE
    COMMIT thành công

Hậu quả: có thể gửi email hai lần.
~~~

Một thiết kế thường dùng **transactional outbox**: ghi bản ghi sự kiện vào database trong cùng transaction, chỉ phát bên ngoài sau khi transaction đã commit, và consumer có cơ chế idempotency. Cách này không giải quyết hết mọi bài toán phân tán nhưng giúp tách rõ **retry database transaction** khỏi **hiệu ứng không thể rollback**.

### 17.6. Mất kết nối tại COMMIT là tình huống riêng

Nếu mất kết nối mạng đúng lúc `COMMIT`, ứng dụng có thể **không biết chắc** transaction đã commit hay chưa. Không tự coi đó là `40001` và thực hiện lại thao tác tài chính không-idempotent. Cần khóa idempotency, mã yêu cầu duy nhất, đối soát kết quả hoặc workflow khôi phục phù hợp.

## 18. Ví dụ Java/JDBC: transaction Serializable có retry

Ứng dụng Java dùng `Connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE)` trước câu SQL đầu tiên, sau đó bắt `SQLException.getSQLState()` để xử lý `40001`.

Ví dụ sau dùng schema lab để **yêu cầu một bác sĩ nghỉ trực nếu còn ít nhất hai bác sĩ đang trực**. Nó minh họa luồng retry và không thực hiện hiệu ứng bên ngoài. Giả định các thao tác liên quan tới bất biến này đều tuân theo giao thức Serializable hoặc cơ chế tương đương.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OnCallService {
    public static boolean requestOffDuty(
            DataSource dataSource,
            int doctorId
    ) throws SQLException, InterruptedException {
        final int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            boolean retry = false;

            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );

                try {
                    int onDutyCount;
                    try (PreparedStatement query = connection.prepareStatement(
                            "SELECT COUNT(*) FROM iso_lab_216.on_call "
                            + "WHERE on_duty"
                         );
                         ResultSet rs = query.executeQuery()) {
                        rs.next();
                        onDutyCount = rs.getInt(1);
                    }

                    if (onDutyCount <= 1) {
                        connection.commit();
                        return false; // Không thể cho nghỉ.
                    }

                    int changedRows;
                    try (PreparedStatement update = connection.prepareStatement(
                            "UPDATE iso_lab_216.on_call "
                            + "SET on_duty = FALSE "
                            + "WHERE doctor_id = ? AND on_duty"
                         )) {
                        update.setInt(1, doctorId);
                        changedRows = update.executeUpdate();
                    }

                    connection.commit();
                    return changedRows == 1;

                } catch (SQLException ex) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < maxAttempts) {
                        retry = true;
                    } else {
                        throw ex;
                    }
                }
            }

            if (retry) {
                // Minh họa backoff đơn giản.
                // Hệ thống thật nên có jitter và chính sách timeout.
                Thread.sleep(20L * attempt);
            }
        }

        throw new SQLException("Retry limit exhausted");
    }
}
~~~

### 18.1. Tại sao đọc trong vòng thử?

Mỗi lần retry lấy connection/transaction mới và chạy lại `SELECT COUNT(*)`. Nhờ đó, sau khi một người đã nghỉ, lần tiếp theo biết chỉ còn một người trực và không cho người còn lại nghỉ.

### 18.2. Tại sao xử lý COMMIT trong try/catch?

`COMMIT` ở mức Serializable cũng có thể thất bại với `40001`. Nếu chỉ bao `UPDATE` trong khối retry rồi gọi commit bên ngoài, ứng dụng sẽ bỏ sót một lớp lỗi quan trọng.

### 18.3. Những điều ứng dụng thật còn phải làm

- Có timeout, backoff/jitter, giới hạn retry và đo số lần `40001`.
- Đảm bảo connection pool phục hồi trạng thái isolation/autocommit khi kết nối được trả về.
- Phân biệt lỗi nghiệp vụ, không tìm thấy bác sĩ, bác sĩ đã nghỉ và lỗi cạnh tranh.
- Bảo vệ toàn bộ luồng ghi ảnh hưởng tới số bác sĩ đang trực, không chỉ một method.
- Quy định rõ lúc nào phát thông báo ra ngoài hoặc ghi audit.
- Với request mà kết quả có thể không rõ do mất kết nối ở commit, bổ sung idempotency/reconciliation.

Đoạn code trên là **bài học về giao dịch và retry**, không phải mã nghiệp vụ hoàn chỉnh dành cho hệ thống y tế thực tế.

## 19. Một hướng khác: khóa phối hợp với SELECT FOR UPDATE

Serializable không phải cách duy nhất để bảo vệ bất biến liên quan nhiều hàng. Có thể **tuần tự hóa riêng thao tác nghiệp vụ** bằng cách yêu cầu mọi writer lấy khóa trên **cùng một hàng điều phối** trước khi đọc và thay đổi dữ liệu.

Trong schema lab, bảng `duty_guard` có đúng một hàng `guard_id=1`.

### 19.1. Session A lấy khóa trước

**Điều kiện đầu:** cả hai bác sĩ đang trực.

<escape>**Session A:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT guard_id
FROM iso_lab_216.duty_guard
WHERE guard_id = 1
FOR UPDATE;
-- A giữ row lock đến cuối transaction.

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2.

UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;

-- Chưa commit để Session B thử lấy khóa.
~~~

### 19.2. Session B phải chờ cùng khóa

<escape>**Session B:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT guard_id
FROM iso_lab_216.duty_guard
WHERE guard_id = 1
FOR UPDATE;
-- CHỜ Session A COMMIT/ROLLBACK.
~~~

Khi B đang chờ, cho A `COMMIT`:

~~~sql
-- Session A:
COMMIT;
~~~

Sau khi khóa được giải phóng, B tiếp tục:

~~~sql
-- Session B:
SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 1 (nếu A đã commit việc cho bác sĩ 1 nghỉ).

-- Vì chỉ còn 1, ứng dụng KHÔNG chạy
-- UPDATE doctor_id=2 SET on_duty=FALSE.

COMMIT;
~~~

**Vì sao có tác dụng:** mọi transaction thay đổi duty cùng lấy khóa `duty_guard(1)` trước khi kiểm tra số người trực. Việc kiểm tra/ghi được thực hiện **từng lượt**, nên tại Read Committed, sau khi B lấy được khóa, `SELECT COUNT(*)` mới nhìn thấy commit của A.

### 19.3. Giới hạn của cách khóa điều phối

- **Mọi writer phải cùng tuân thủ giao thức.** Nếu có một job khác bỏ qua khóa guard, invariant không còn được đảm bảo chỉ nhờ ví dụ này.
- Khóa chung có thể trở thành **điểm nghẽn** khi nhiều request cùng tranh chấp.
- Nên giữ transaction ngắn, lấy khóa theo thứ tự nhất quán để giảm deadlock.
- Nếu phân vùng quy tắc theo bệnh viện/ca, có thể cân nhắc **một hàng guard cho mỗi phạm vi** thay vì một khóa toàn hệ thống.
- Kiểm soát quyền và cách truy cập bảng guard để tránh thao tác ngoài ý muốn.

Không nên dùng một khóa chung quá rộng nếu workload lớn, nhưng đây là ví dụ cho thấy **một invariant qua nhiều hàng có thể được bảo vệ bằng serialization ở cấp nghiệp vụ** mà không cần mọi thao tác trong hệ thống cùng tranh chấp một row dữ liệu.

### 19.4. Khác với SELECT FOR UPDATE chỉ khóa hàng của từng bác sĩ

Nếu A chỉ khóa hàng bác sĩ 1 và B chỉ khóa hàng bác sĩ 2, hai transaction vẫn có thể ghi hai hàng riêng biệt mà không tranh chấp nhau. Bất biến liên quan **tổng số người trực**, nên phải khóa **đúng tài nguyên chung** hoặc dùng SSI phát hiện xung đột đọc–ghi trên tập đó.

## 20. SELECT FOR UPDATE và Repeatable Read: vẫn có thể lỗi

`SELECT ... FOR UPDATE` đặt khóa lên những hàng mà truy vấn chọn. Nó khác `SELECT` thông thường:

~~~sql
BEGIN;

SELECT *
FROM iso_lab_216.stock
WHERE sku = 'SKU-A'
FOR UPDATE;

-- Các thao tác trên hàng đã khóa.

COMMIT;
~~~

Ở Read Committed, nếu hàng đang được transaction khác khóa/ghi, truy vấn có thể chờ rồi khóa **phiên bản đã được cập nhật** sau khi transaction kia commit.

Ở Repeatable Read hoặc Serializable, nếu hàng cần khóa **đã bị transaction khác cập nhật sau snapshot của transaction hiện tại**, PostgreSQL có thể báo lỗi `could not serialize access due to concurrent update` thay vì lặng lẽ khóa phiên bản mới.

### 20.1. FOR UPDATE không ngăn mọi phantom

Khóa vài hàng hiện có không tự động ngăn transaction khác chèn thêm **một hàng mới thỏa predicate** trong Read Committed. Ví dụ khóa hai bác sĩ hiện tại không có nghĩa mọi thao tác thêm/xóa bác sĩ tương lai đều bị chặn theo một quy tắc nghiệp vụ tổng hợp.

Nếu bất biến phụ thuộc cả **tập hàng có thể thay đổi**, hãy cân nhắc:

- Serializable với logic kiểm tra và retry;
- Khóa điều phối đúng phạm vi, tất cả writer tuân thủ;
- Constraint/trigger/procedure được thiết kế cho invariant;
- Thiết kế lại dữ liệu để invariant có thể kiểm tra bằng ràng buộc trên một đối tượng rõ ràng.

### 20.2. NOWAIT và SKIP LOCKED không thay isolation

PostgreSQL có:

~~~sql
SELECT *
FROM iso_lab_216.stock
WHERE sku = 'SKU-A'
FOR UPDATE NOWAIT;
~~~

hoặc:

~~~sql
SELECT *
FROM iso_lab_216.stock
FOR UPDATE SKIP LOCKED;
~~~

`NOWAIT` trả lỗi thay vì chờ row lock; `SKIP LOCKED` bỏ qua những hàng đang bị khóa. Chúng hữu ích trong một số mô hình hàng đợi/worker, nhưng **không mang tới snapshot nhất quán cho mọi quyết định nghiệp vụ**. `SKIP LOCKED` còn cố ý cho cái nhìn không đầy đủ về những hàng đang bị khóa, nên không nên dùng để tính tổng tồn kho hay xác minh invariant toàn bảng.

## 21. SERIALIZABLE READ ONLY DEFERRABLE cho báo cáo dài

Một giao dịch chỉ đọc nhưng chạy lâu có thể cần **snapshot phù hợp với tuần tự hóa** mà không muốn phải retry nhiều lần. PostgreSQL hỗ trợ:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_amount
FROM iso_lab_216.orders;

SELECT
    COUNT(*) FILTER (WHERE on_duty) AS active_doctors
FROM iso_lab_216.on_call;

COMMIT;
~~~

Khi kết hợp đủ **`SERIALIZABLE READ ONLY DEFERRABLE`**, transaction có thể **chờ lúc lấy snapshot ban đầu** cho tới khi PostgreSQL xác định được một snapshot an toàn. Sau đó nó có thể đọc theo bảo đảm tương ứng mà không phải chịu nguy cơ bị hủy vì serialization anomaly, và tránh một số overhead theo dõi của transaction Serializable thông thường.

### 21.1. DEFERRABLE không tự có tác dụng trong mọi tình huống

Theo PostgreSQL, thuộc tính `DEFERRABLE` chỉ có tác dụng khi transaction **đồng thời** là `SERIALIZABLE` và `READ ONLY`. Dùng nó với Read Committed hoặc transaction đọc–ghi không mang lại cùng cơ chế chờ snapshot an toàn.

### 21.2. Snapshot an toàn không đồng nghĩa dữ liệu mới nhất tức thời

Báo cáo này vẫn đọc **một snapshot**. Những transaction khác commit **sau thời điểm snapshot** sẽ không tự xuất hiện trong các câu SELECT của báo cáo. DEFERRABLE ưu tiên tính an toàn về tuần tự hóa, không phải tính cập nhật “real-time”.

### 21.3. Khi nào cân nhắc?

- Xuất báo cáo tài chính tổng hợp dài.
- Backup/đọc snapshot lâu cần bảo đảm serializable.
- Tính chỉ số phân tích từ nhiều bảng mà không muốn phải retry vì SSI.

Đổi lại, **có thể có thời gian chờ trước truy vấn đầu tiên**. Cần đo latency và kiểm soát transaction mở lâu; không coi đây là lựa chọn mặc định cho mọi request HTTP.

## 22. READ ONLY Repeatable Read hay Serializable?

Nếu mục tiêu chỉ là “mỗi lần SELECT trong một báo cáo nhìn cùng một snapshot”, Repeatable Read Read Only thường đáp ứng yêu cầu:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ
    READ ONLY;

SELECT COUNT(*) FROM iso_lab_216.orders;
SELECT SUM(amount) FROM iso_lab_216.orders;

COMMIT;
~~~

Nhưng **snapshot ổn định** không đồng nghĩa **tổng thể tương đương mọi lịch thực thi tuần tự** khi xét các quan hệ phụ thuộc giữa nhiều transaction. Một báo cáo có các điều kiện logic phức tạp trên dữ liệu vừa được nhiều writer xây dựng có thể cần bảo đảm Serializable.

**Phân biệt ba câu hỏi:**

1. Có muốn hai SELECT nhìn **cùng snapshot** không? → Repeatable Read.
2. Có cần lịch sử các transaction commit tương đương một **thứ tự tuần tự** không? → Serializable, với retry.
3. Có chấp nhận **chờ ban đầu** để có snapshot chỉ đọc an toàn và tránh serialization failure không? → Serializable Read Only Deferrable.

## 23. Mức cô lập không thay thế constraint

Isolation xử lý sự tương tác giữa các transaction; **constraint** định nghĩa cấu trúc hợp lệ của dữ liệu. Hai nhóm công cụ bổ sung cho nhau.

Ví dụ:

~~~sql
CREATE TABLE iso_lab_216.wallets (
    wallet_id INTEGER PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL
        CHECK (balance >= 0)
);
~~~

`CHECK (balance >= 0)` bảo vệ dữ liệu của **mỗi hàng ví tiền** không âm. Nó có tác dụng ở mọi isolation level. Tương tự:

- `PRIMARY KEY`/`UNIQUE` ngăn khóa trùng.
- `FOREIGN KEY` bảo vệ mối quan hệ tham chiếu.
- `NOT NULL` buộc giá trị có mặt.

Nhưng không có một `CHECK` trên hàng `on_call` riêng lẻ nào đơn giản để diễn đạt “**ít nhất một trong toàn bảng** phải đang trực”. Bất biến liên hàng yêu cầu thiết kế thêm. Isolation Serializable giúp bảo vệ logic đọc–ghi phù hợp trong các transaction cùng tuân thủ, nhưng **không tạo constraint thay ứng dụng**.

### 23.1. Một lỗi thiết kế: chỉ SELECT trước, rồi INSERT không kiểm soát

~~~text
Transaction A: SELECT "có mã này chưa?" -> chưa.
Transaction B: SELECT "có mã này chưa?" -> chưa.
A và B cùng INSERT mã đó.
~~~

Ở Read Committed hoặc Repeatable Read, chỉ kiểm tra bằng SELECT trước **không thay** unique constraint. Đặt `UNIQUE` lên khóa cần duy nhất là rào chắn đáng tin cậy; ứng dụng phải xử lý xung đột phù hợp. Ngay cả Serializable cũng không thay nhu cầu đặt constraint cho những bất biến quan trọng của schema.

### 23.2. Business invariant phải ở phạm vi đầy đủ

Nếu một bất biến là “tổng số dư của các account trong nhóm không được âm” hoặc “ít nhất một người trực trong ca”, việc chỉ khóa/cập nhật **một hàng** không nhất thiết đủ. Phải xác định **tập dữ liệu nào tham gia quyết định** và **tất cả đường ghi nào có thể thay đổi tập đó**.

## 24. Deadlock khác serialization failure

Deadlock xảy ra khi các transaction chờ nhau theo vòng:

~~~text
Transaction A giữ khóa hàng 1, muốn hàng 2.
Transaction B giữ khóa hàng 2, muốn hàng 1.

A đợi B; B đợi A.
~~~

PostgreSQL phát hiện deadlock và hủy một transaction để phá vòng, thường với `SQLSTATE 40P01`.

Serializable failure `40001` có thể phát sinh **không cần deadlock row lock**, do SSI phát hiện lịch sử đọc–ghi không tuần tự hóa được.

| Điểm phân biệt | Deadlock | Serialization failure |
| --- | --- | --- |
| Tình huống điển hình | Vòng chờ khóa | Phụ thuộc đọc–ghi/cập nhật xung đột |
| SQLSTATE thường thấy | `40P01` | `40001` |
| Có cần transaction giữ khóa chờ nhau? | Có, theo vòng chờ | Không nhất thiết |
| Hướng xử lý | Rollback/retry an toàn, thứ tự khóa nhất quán | Retry **toàn transaction** với dữ liệu mới |
| Có thể gặp ở Read Committed? | Có | Không phải lỗi đặc trưng nhưng vẫn có lỗi tranh chấp khác |

### 24.1. Thứ tự khóa nhất quán giúp giảm deadlock

Nếu cần cập nhật nhiều account, nên thiết kế mọi transaction lấy khóa theo cùng thứ tự khóa tăng dần, thay vì transaction này xử lý 1→2 còn transaction kia xử lý 2→1. Tuy nhiên, **thứ tự khóa không thay thế logic tuần tự hóa** cho các invariant dựa trên snapshot nhiều hàng.

## 25. Tài nguyên và độ trễ của các mức cô lập

Không có công thức “Serializable luôn chậm gấp N lần” hoặc “Read Committed luôn nhanh nhất” áp dụng cho mọi workload.

### 25.1. Read Committed

Ưu điểm:

- Mức mặc định quen thuộc, phù hợp nhiều thao tác đơn giản.
- Snapshot theo câu lệnh, đọc các commit mới ở những lệnh sau.
- Kết hợp tốt với atomic `UPDATE ... WHERE` cho một số invariant trên từng hàng.

Đánh đổi:

- Cùng transaction có thể thấy giá trị/tập hàng thay đổi giữa hai SELECT.
- Logic đọc nhiều bước rồi quyết định ghi có nguy cơ dùng dữ liệu đã cũ.
- Có thể thấy kết quả cập nhật không hoàn toàn nhất quán của một số câu lệnh ghi với điều kiện phức tạp khi gặp writer đồng thời.

### 25.2. Repeatable Read

Ưu điểm:

- Snapshot ổn định, thích hợp đọc/báo cáo nhiều câu lệnh.
- PostgreSQL ngăn dirty, nonrepeatable và phantom read.
- Có thể cho writer khác tiếp tục thao tác nhờ MVCC, thay vì khóa toàn bộ dữ liệu chỉ để đọc snapshot.

Đánh đổi:

- Có thể gặp `40001` khi muốn cập nhật/khóa hàng bị transaction khác sửa sau snapshot.
- Có thể gặp write skew/serialization anomaly trên nhiều hàng khác nhau.
- Transaction giữ snapshot lâu có thể làm tăng áp lực lưu các phiên bản hàng cũ.

### 25.3. Serializable

Ưu điểm:

- Những transaction Serializable **commit thành công** có kết quả tương đương một lịch chạy tuần tự.
- Giảm nhu cầu tự thiết kế nhiều loại khóa thủ công cho các bất biến dựa trên kiểm tra dữ liệu, khi toàn bộ writer liên quan được kiểm soát đúng.

Đánh đổi:

- Overhead theo dõi phụ thuộc đọc–ghi/predicate.
- Tăng khả năng phải retry với `40001` khi có cạnh tranh.
- Query plan và số lượng hàng được đọc có thể ảnh hưởng tới phạm vi SIReadLock; đôi khi scan lớn làm nhiều transaction xung đột hơn.
- Cần thiết kế idempotency, retry và giám sát.

### 25.4. Transaction dài có thể ảnh hưởng VACUUM

Một snapshot tồn tại quá lâu có thể khiến PostgreSQL phải giữ những phiên bản hàng cũ lâu hơn để phục vụ transaction đang hoạt động. Điều này có thể làm tăng bloat và áp lực autovacuum. Không để ứng dụng mở transaction rồi chờ người dùng lâu, nhất là ở những transaction giữ snapshot lâu.

### 25.5. Đừng đẩy mọi lỗi ứng dụng thành lựa chọn isolation

Ví dụ mất cập nhật vì ứng dụng dùng hằng số từ stale read có thể sửa bằng `UPDATE SET counter=counter+1`. Vấn đề SKU trùng có thể đặt `UNIQUE`. Bất biến giữa nhiều hàng có thể cần Serializable hoặc khóa điều phối. **Chọn đúng công cụ cho đúng lớp vấn đề** thường hiệu quả hơn việc tăng isolation một cách hàng loạt.

## 26. Giám sát transaction và khóa trong PostgreSQL

### 26.1. Xem transaction đang mở

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Quyền xem thông tin chi tiết của những session khác phụ thuộc role/cấu hình PostgreSQL. Hãy quan tâm đặc biệt đến kết nối ở trạng thái **`idle in transaction`** quá lâu và các transaction đang chờ khóa.

### 26.2. Xem các khóa SSI

~~~sql
SELECT
    pid,
    locktype,
    mode,
    relation::regclass AS relation_name,
    granted
FROM pg_catalog.pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
~~~

`SIReadLock` là thông tin theo dõi predicate cho cơ chế Serializable; **không hiểu nó như một khóa `FOR UPDATE` đang chặn mọi người ghi**. Phạm vi chính xác của khóa phụ thuộc truy vấn, index, plan và cách PostgreSQL quản lý bộ nhớ lock.

### 26.3. Tìm session đang chờ người khác

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_catalog.pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

Khi B ở thí nghiệm `SELECT FOR UPDATE`/`UPDATE` đang chờ A, có thể thấy một sự kiện chờ liên quan khóa. Nếu chỉ có SIReadLock dùng cho SSI, không nhất thiết có writer bị chặn bởi predicate lock.

### 26.4. Thời gian chờ và timeout

Trong môi trường lab, có thể giới hạn cho một transaction:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

SELECT COUNT(*)
FROM iso_lab_216.orders;

ROLLBACK;
~~~

- `lock_timeout` giới hạn thời gian chờ lấy một khóa.
- `statement_timeout` giới hạn thời gian một statement được phép chạy.
- `idle_in_transaction_session_timeout` có thể được cấu hình ở server/session để xử lý session nằm chờ trong transaction quá lâu.

Timeout **không giải quyết tính đúng** của một invariant. Khi có statement lỗi/timeout trong transaction PostgreSQL, transaction có thể ở trạng thái aborted; cần rollback trước khi tiếp tục.

### 26.5. Đo những chỉ số nào ở production?

Một dashboard vận hành có thể theo dõi:

- Số lượng và tỷ lệ transaction kết thúc bằng `40001`.
- Số lần retry trung bình và tỷ lệ retry hết giới hạn.
- Thời gian giữ transaction, thời gian chờ lock, deadlock.
- Số kết nối `idle in transaction`.
- Throughput/latency khi chuyển mức cô lập.
- Mức độ bloat và hoạt động autovacuum nếu có transaction đọc lâu.

**Đừng tối ưu bằng cách tắt SSI hoặc hạ isolation chỉ để giảm 40001 mà chưa có giải pháp thay thế giữ tính đúng nghiệp vụ.**

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế trong PostgreSQL |
| --- | --- |
| Read Committed đọc được dữ liệu chưa commit | Không; PostgreSQL không có dirty read |
| READ UNCOMMITTED sẽ tăng tốc bằng cách đọc “bẩn” | Nó hoạt động như Read Committed |
| Read Committed có một snapshot cho cả transaction | Mỗi statement đọc thường có snapshot riêng |
| Repeatable Read luôn thấy commit của transaction khác sau mỗi SELECT | Nó giữ snapshot ổn định |
| Repeatable Read trong PostgreSQL có phantom như mức tối thiểu SQL standard | PostgreSQL **ngăn phantom** tại Repeatable Read |
| Repeatable Read tương đương Serializable | **Write skew** vẫn có thể xảy ra |
| Hai transaction sửa hai hàng khác nhau thì chắc chắn an toàn | Có thể cùng vi phạm bất biến liên hàng |
| Serializable bắt mọi transaction chạy tuần tự bằng row lock | PostgreSQL dùng SSI, có thể cho chạy đồng thời rồi abort khi nguy hiểm |
| Serializable không bao giờ có lỗi cạnh tranh | Có thể trả `40001` |
| Chỉ retry UPDATE lỗi là đủ | Phải retry **toàn bộ logic giao dịch**, kể cả đọc lại |
| 40001 chỉ xảy ra ở Serializable | Repeatable Read cũng có thể lỗi vì concurrent update |
| SELECT FOR UPDATE có thể dùng để khóa mọi hàng tương lai thỏa điều kiện | Nó khóa các hàng được chọn, không phải mọi phantom mới ở Read Committed |
| Đọc COUNT lần nữa ở Repeatable Read sẽ thấy commit mới | Vẫn cùng snapshot |
| Một UPDATE nguyên tử không giúp gì về cạnh tranh | Với điều kiện phù hợp trên một hàng, nó có thể giải quyết an toàn hơn read-then-write |
| Serializable tự đảm bảo mọi quy tắc nghiệp vụ | Quy tắc vẫn phải được diễn đạt/kiểm tra |
| Retry có thể gửi lại email/thanh toán vô tư | Hiệu ứng ngoài database cần idempotency/outbox |
| COMMIT đã gửi nên chắc chắn thành công dù kết nối mất | Trạng thái có thể không rõ, cần đối soát |
| READ ONLY có nghĩa không cấp quyền ghi cho user | Chế độ transaction khác với phân quyền SQL |
| DEFERRABLE hoạt động ở mọi mức | Chỉ có hiệu lực khi kết hợp Serializable + Read Only |
| SIReadLock là khóa luôn chặn writer | Nó phục vụ phát hiện xung đột SSI, không chặn như row lock |
| Transaction dài luôn vô hại nhờ MVCC | Có thể giữ phiên bản cũ, tăng áp lực vacuum/bloat |

## 28. Bài tập thực hành

### Bài 1 — Xác định mức mặc định

Chạy:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

**Câu hỏi:** database của bạn đang dùng mặc định gì? Nếu cấu hình chưa thay đổi, PostgreSQL thường dùng mức nào?

**Gợi ý đáp án:** mặc định thường là `read committed`. Đừng mặc định mọi server đều giữ nguyên cấu hình.

### Bài 2 — Nonrepeatable read

Theo thứ tự ở mục 6.1, chạy hai cửa sổ A/B và ghi lại giá nhìn thấy.

**Kỳ vọng:** tại Read Committed, A đọc `100` trước B commit, rồi `120` sau B commit. Giải thích hai snapshot theo câu lệnh.

### Bài 3 — Không dirty read

Session A cập nhật giá thành `999` nhưng không commit. Session B dùng `READ UNCOMMITTED` và đọc giá.

**Kỳ vọng:** B không thấy `999` chưa commit. Vì sao PostgreSQL khác một số hệ quản trị cho dirty read?

### Bài 4 — Phantom ở Read Committed

Session A đếm đơn `PAID`, B chèn `order_id=103` PAID rồi commit, A đếm lại.

**Kỳ vọng:** `1 → 2`. Reset sau khi kết thúc.

### Bài 5 — Repeatable Read giữ giá cũ

Lặp bài 2, nhưng A dùng `REPEATABLE READ` ngay trước `SELECT` đầu.

**Kỳ vọng:** hai SELECT trong A đều trả `100`; sau commit và transaction mới mới thấy `120`.

### Bài 6 — Snapshot bắt đầu lúc nào?

So sánh:

~~~text
A: BEGIN RR
A: SELECT price
B: UPDATE/COMMIT
A: SELECT price
~~~

với:

~~~text
A: BEGIN RR
B: UPDATE/COMMIT
A: SELECT price lần đầu
~~~

**Kỳ vọng:** ở lịch thứ hai, SELECT đầu của A có thể thấy giá mới vì snapshot chưa được cố định ở thời điểm `BEGIN`.

### Bài 7 — Phantom tại PostgreSQL Repeatable Read

Lặp bài 4 nhưng A dùng Repeatable Read. Dự đoán kết quả hai lần `COUNT(*)` trước khi chạy.

**Đáp án:** vẫn `1` trong transaction A; sau transaction mới mới thấy `2`. Đây là điểm PostgreSQL mạnh hơn yêu cầu tối thiểu của SQL standard.

### Bài 8 — UPDATE cùng hàng tại Repeatable Read

A mở RR, đọc `price=100`; B cập nhật cùng hàng thành `120` và commit; A cố cập nhật thành `130`.

**Kỳ vọng:** `SQLSTATE 40001`, không phải một lần ghi đè thành công. A phải rollback/retry.

### Bài 9 — Trừ tồn kho với READ COMMITTED

Dùng hai session trừ `4` từ `quantity=5` bằng:

~~~sql
UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING quantity;
~~~

Cho A cập nhật trước, giữ transaction, B gửi cùng câu lệnh và chờ, rồi A commit.

**Kỳ vọng:** một UPDATE trả một hàng; một UPDATE trả **0 hàng**; tồn cuối là **1**.

### Bài 10 — Lost update ở ứng dụng

Hai transaction đọc counter=10, tính 11 trong ứng dụng rồi lần lượt ghi `SET value=11`.

**Đáp án:** cuối cùng là 11 dù có hai yêu cầu tăng. Chuyển sang `SET value=value+1` và giải thích vì sao kết quả có thể đúng là 12 khi cả hai transaction commit.

### Bài 11 — Viết optimistic locking

Giả sử bảng có `version INTEGER NOT NULL`. Thiết kế statement:

~~~sql
UPDATE some_table
SET value = :new_value,
    version = version + 1
WHERE id = :id
  AND version = :version_read_before;
~~~

Giải thích vì sao **0 hàng cập nhật** báo rằng giá trị/version có thể đã thay đổi và cần đọc/tính lại. Phương án này liên quan concurrency nhưng không thay đổi isolation level của session.

### Bài 12 — Write skew ở Repeatable Read

Khôi phục hai bác sĩ `on_duty=TRUE`, chạy kịch bản ở mục 14.

**Kỳ vọng:** hai transaction cùng đọc count=2, mỗi transaction tắt một hàng khác nhau và cả hai có thể commit, để lại **0 người trực**. Tại sao không có lost update cùng hàng?

### Bài 13 — Serializable bảo vệ invariant

Reset cả hai bác sĩ đang trực rồi lặp bài 12 với **SERIALIZABLE** ở cả A và B.

**Kỳ vọng:** không thể cả hai commit thành công như lịch không tuần tự hóa; một transaction có thể nhận `40001`.

### Bài 14 — Retry đúng ở Serializable

Sau khi transaction bị `40001`, bắt đầu transaction mới, đọc `COUNT(*) WHERE on_duty` lại.

**Kỳ vọng:** nếu chỉ còn một người trực, không được cho người đó nghỉ. Giải thích tại sao retry riêng câu `UPDATE` là sai.

### Bài 15 — Khóa điều phối

Dùng `duty_guard` và `SELECT ... FOR UPDATE` như mục 19.

**Câu hỏi:** transaction B chờ lúc nào? Sau khi A commit, ở Read Committed B nhìn thấy bao nhiêu người trực? Nếu job C không lấy khóa guard thì có rủi ro gì?

### Bài 16 — Read Committed và WHERE recheck

A giữ khóa và cập nhật tồn từ 5 xuống 1; B gửi `UPDATE ... WHERE quantity>=4` khi A chưa commit.

**Đáp án:** sau khi A commit, B kiểm tra lại điều kiện trên phiên bản mới và cập nhật 0 hàng. Nếu A rollback, điều gì khác?

### Bài 17 — REPORT snapshot

Một báo cáo đọc tổng đơn và tổng tiền bằng hai câu `SELECT` trong cùng transaction, trong lúc B thêm đơn.

So sánh:

- A dùng `READ COMMITTED`.
- A dùng `REPEATABLE READ READ ONLY`.

**Đáp án:** RC có thể thấy hai snapshot khác nhau; RR dùng cùng snapshot cho cả hai SELECT. Điều này quan trọng khi tổng các KPI phải cùng thời điểm.

### Bài 18 — READ ONLY DEFERRABLE

Viết transaction:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT COUNT(*) FROM iso_lab_216.orders;

COMMIT;
~~~

**Câu hỏi:** tại sao có thể chờ trước khi đọc? Dùng `DEFERRABLE` mà không `SERIALIZABLE READ ONLY` có cùng hiệu quả không?

### Bài 19 — Phân biệt lỗi

Giải thích khác biệt của:

- `40001` — serialization failure.
- `40P01` — deadlock.
- `23505` — duplicate unique key.

Lỗi nào nên retry cả transaction? Lỗi nào cần phân tích dữ liệu/logic thay vì retry mù?

### Bài 20 — Thiết kế retry an toàn

Một request tạo đơn, trừ tồn và gửi email xác nhận. Nếu Serializable transaction bị `40001` sau khi email đã gửi, điều gì xảy ra khi retry?

**Gợi ý:** không gửi email bên trong mỗi lần thử database transaction; cân nhắc outbox/idempotency và phát sự kiện sau commit.

### Bài 21 — Kiểm tra giám sát

Viết query dùng `pg_stat_activity` để tìm transaction có `xact_start` quá 5 phút:

~~~sql
SELECT
    pid,
    state,
    now() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
  AND now() - xact_start > INTERVAL '5 minutes';
~~~

**Câu hỏi:** tại sao transaction giữ snapshot quá lâu có thể ảnh hưởng VACUUM? Khi nào `idle in transaction` là dấu hiệu nguy hiểm?

### Bài 22 — Quan sát SIReadLock

Trong một giao dịch Serializable đang mở, đọc bảng `on_call` rồi quan sát `pg_locks` từ một session khác.

**Câu hỏi:** `SIReadLock` dùng để làm gì? Vì sao không được hiểu nó giống `FOR UPDATE`?

### Bài 23 — Xác định biện pháp đúng

Ghép tình huống với hướng giải quyết:

| Tình huống | Hướng nên cân nhắc |
| --- | --- |
| Tăng bộ đếm một hàng | Atomic `UPDATE SET value=value+1` |
| Trừ tồn một SKU | `UPDATE ... WHERE quantity>=requested`, kiểm tra rowcount |
| Báo cáo đa câu SELECT cần snapshot ổn định | Repeatable Read Read Only |
| Không được cho cả hai bác sĩ nghỉ | Serializable + retry hoặc khóa điều phối đúng |
| Cấm trùng SKU | `UNIQUE` constraint |
| Cấm số dư âm trên một hàng | `CHECK` và atomic update |
| Batch báo cáo dài cần serializable snapshot an toàn | Serializable Read Only Deferrable |

Không có một phương án duy nhất phù hợp mọi ứng dụng.

### Bài 24 — Code review

Một developer viết:

~~~sql
BEGIN;
SELECT COUNT(*) FROM iso_lab_216.on_call WHERE on_duty;
-- Nếu count >= 2, ứng dụng chạy:
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = :chosen_doctor;
COMMIT;
~~~

Hãy nêu ít nhất sáu câu hỏi:

1. Transaction dùng isolation nào?
2. Có nhiều writer kiểm tra cùng predicate không?
3. Có write skew nếu cập nhật hai hàng khác nhau không?
4. Tất cả writer có cùng chính sách/khóa phối hợp không?
5. Ứng dụng có xử lý `40001` và retry **cả transaction** không?
6. Nếu transaction thất bại, có hiệu ứng ngoài database nào đã xảy ra không?
7. Nếu bác sĩ đã nghỉ hoặc không tồn tại, có kiểm tra rowcount không?
8. Có cần audit, quyền truy cập và bảo vệ transaction dài không?

### Bài 25 — So sánh Read Committed và Serializable

Một hệ thống có 10.000 request/s chỉ cập nhật số lần xem trên một row bằng `SET view_count=view_count+1`. Một hệ thống khác duy trì nhiều invariant liên bảng trên các transaction có điều kiện.

**Câu hỏi:** hai hệ thống có nên dùng cùng isolation chỉ vì hệ thống thứ hai cần Serializable? Giải thích chi phí retry, tính đúng và phương án atomic SQL/constraint.

## 29. Checklist chọn và vận hành isolation

Trước khi lựa chọn mức cô lập cho một workflow, hãy trả lời:

1. **Một transaction cần đọc nhất quán bao nhiêu câu lệnh?** Một snapshot mỗi câu hay một snapshot cả transaction?
2. **Bất biến nằm trên một hàng hay nhiều hàng?** Có ràng buộc tổng hợp theo tập/predicate không?
3. **Có nhiều writer cùng ra quyết định trên dữ liệu đọc không?** Nếu có, có nguy cơ write skew?
4. **Có thể viết một câu SQL nguyên tử thay vì read–then–write không?** Ví dụ `UPDATE quantity=quantity-n WHERE quantity>=n`.
5. **Có constraint cho những điều kiện xác định được không?** `UNIQUE`, `CHECK`, `FOREIGN KEY`?
6. **Nếu dùng Serializable/Repeatable Read và gặp `40001`, ứng dụng retry toàn transaction ra sao?**
7. **Có nguồn side effect bên ngoài database không?** Email, payment, event bus, file?
8. **Có transaction nào trộn isolation khác nhau nhưng cùng ảnh hưởng invariant không?**
9. **Khi chờ khóa hoặc retry nhiều lần, request có timeout/backoff và log phù hợp không?**
10. **Thời gian transaction có bị kéo dài do tương tác người dùng, I/O mạng hay báo cáo lớn không?**
11. **Đã kiểm thử bằng hai session thực sự, không chỉ chạy SQL tuần tự trong một console chưa?**
12. **Đã đo tỷ lệ `40001`, deadlock, latency, lock wait và ảnh hưởng VACUUM trong workload đại diện chưa?**

Nếu câu trả lời không rõ, đừng tự nâng/hạ isolation với kỳ vọng nó sẽ “tự xử lý cạnh tranh”. Hãy mô tả **lịch trình hai transaction có thể xảy ra**, rồi quyết định cơ chế tối thiểu đủ bảo vệ nghiệp vụ.

## 30. Tài liệu PostgreSQL chính thức

Các trang tham khảo quan trọng:

- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): ma trận các hiện tượng, hành vi Read Committed, Repeatable Read và Serializable, `40001` và SSI.
- [PostgreSQL — SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): thiết lập isolation, READ ONLY/READ WRITE, DEFERRABLE và thời điểm được đổi mức.
- [PostgreSQL — Concurrency Control / MVCC](https://www.postgresql.org/docs/current/mvcc.html): cách PostgreSQL kiểm soát đồng thời.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): khóa hàng, `SELECT FOR UPDATE`, deadlock và các loại khóa.
- [PostgreSQL — BEGIN](https://www.postgresql.org/docs/current/sql-begin.html): mở transaction với các transaction mode.
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW): quan sát session/transaction đang hoạt động.
- [PostgreSQL — pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): quan sát lock, trong đó có `SIReadLock` phục vụ Serializable.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `40001`, `40P01`, `23505` và những lỗi khác.

Các URL `/docs/current/` trỏ tới tài liệu phiên bản PostgreSQL ổn định hiện hành. Khi môi trường sử dụng một major version cụ thể (ví dụ PostgreSQL 14, 15, 16, 17 hoặc 18), hãy tham khảo **đúng bộ tài liệu phiên bản đó** để xác nhận các chi tiết cú pháp và hành vi mới.

## 31. Tổng kết

Ba mức cô lập trong PostgreSQL có những mục tiêu rõ ràng:

- **Read Committed** là mặc định, tránh dirty read và tạo snapshot **theo từng câu lệnh**. Nó thích hợp cho nhiều thao tác thông thường, nhất là khi dùng atomic `UPDATE` với điều kiện đúng. Đổi lại, hai câu lệnh trong cùng transaction có thể thấy những commit khác nhau, xuất hiện nonrepeatable read và phantom.
- **Repeatable Read** giữ snapshot **ổn định** và trong PostgreSQL ngăn cả nonrepeatable read lẫn phantom. Tuy nhiên, nó vẫn cho phép **write skew** giữa những transaction ghi các hàng khác nhau dựa trên snapshot cũ. Transaction muốn sửa/khóa một hàng đã bị thay đổi sau snapshot còn có thể nhận `40001`.
- **Serializable** thêm kiểm soát **SSI** để những transaction Serializable **commit thành công** tương đương một lịch chạy tuần tự. Đây là công cụ mạnh cho những invariant dựa trên nhiều hàng và điều kiện đọc, nhưng ứng dụng phải có **retry toàn transaction khi `SQLSTATE 40001`**, có giới hạn, quan sát được và không lặp các side effect bên ngoài một cách mù quáng.

**Bài học quan trọng nhất:** chọn isolation không chỉ dựa vào tên mức. Hãy xác định **snapshot cần ổn định đến đâu, bất biến nằm trên một hay nhiều hàng, SQL có nguyên tử không, ai có thể cùng ghi và ứng dụng sẽ làm gì khi transaction không commit**. Kết hợp mức cô lập với atomic statement, constraint, khóa phù hợp, retry/idempotency và kiểm thử hai phiên thực tế sẽ giúp dữ liệu PostgreSQL đúng ngay cả khi nhiều người dùng và worker hoạt động đồng thời.
