# Phân biệt khóa đối tượng, khóa hàng và khóa nội bộ trong PostgreSQL

Trong PostgreSQL, từ **khóa** (*lock*) không chỉ nói tới một cơ chế. Một lệnh `UPDATE` thường vừa giữ một **khóa cấp quan hệ/bảng**, vừa tham gia cơ chế **khóa những hàng bị sửa**; bên trong database engine, nhiều tiến trình còn sử dụng **khóa nhẹ** và cơ chế đồng bộ để bảo vệ bộ đệm, bộ nhớ chung, cấu trúc điều khiển. Các cơ chế ấy khác nhau về **đối tượng được bảo vệ, thời gian giữ khóa, khả năng quan sát và cách xử lý khi tranh chấp**.

Một câu hỏi thường gặp:

> Vì sao transaction A đang cập nhật một tài khoản mà transaction B vẫn `SELECT` được tài khoản đó, nhưng một `UPDATE` khác lại phải chờ?

Đáp án đòi hỏi phân biệt **MVCC**, **khóa hàng**, **khóa đối tượng** và **khóa nội bộ**. Không thể giải thích bằng câu “PostgreSQL khóa cả bảng khi UPDATE” hoặc “PostgreSQL không khóa vì có MVCC”: cả hai đều bỏ sót những lớp quan trọng.

Bài này tập trung vào ba nhóm:

1. **Khóa đối tượng (object-level / relation-level locks):** phối hợp thao tác trên bảng, index và các đối tượng database. Ở cấp bảng, PostgreSQL có tám mode khóa chính, từ `ACCESS SHARE` đến `ACCESS EXCLUSIVE`.
2. **Khóa hàng (row-level / tuple locks):** điều phối nhiều transaction muốn khóa, sửa hoặc xóa **cùng hàng**, với bốn mode `FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`.
3. **Khóa nội bộ (internal synchronization):** chẳng hạn lightweight locks (**LWLocks**), spinlocks và buffer pins giúp các tiến trình PostgreSQL bảo vệ cấu trúc bên trong; chúng **không phải** những khóa mà ứng dụng chọn qua `LOCK TABLE` hoặc `SELECT FOR UPDATE`.

Ngoài ra còn có **transaction-ID locks**, **advisory locks**, và **predicate/SIRead locks** cho Serializable Snapshot Isolation. Chúng liên quan nhưng không nên bị nhầm với ba nhóm chính.

Bài học có schema thực hành, kịch bản hai session, bảng so sánh mode, truy vấn giám sát `pg_locks`/`pg_stat_activity`/`pg_blocking_pids()`, hướng dẫn phân tích deadlock, timeout và các bài tập có lời giải.

## 1. Mô hình tổng quan: một câu SQL có thể dùng nhiều lớp khóa

Hình dung hai session đang sửa dữ liệu:

~~~text
Ứng dụng A                         Ứng dụng B
    |                                  |
    v                                  v
 PostgreSQL backend A             PostgreSQL backend B
    |                                  |
    +------------+---------------------+
                 |
      Khóa đối tượng / relation
      (phối hợp DDL, DML, truy cập bảng)
                 |
      Khóa hàng / tuple
      (cạnh tranh trên cùng hàng)
                 |
      Đồng bộ nội bộ engine
      (LWLock, spinlock, buffer pin ...)
                 |
           Shared buffers
           WAL / bộ nhớ chung
           Trang dữ liệu / storage
~~~

Một transaction có thể giữ **nhiều khóa thuộc nhiều lớp đồng thời**. Chẳng hạn:

~~~sql
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
-- Chưa COMMIT.
~~~

Về mặt phối hợp concurrency, PostgreSQL có thể:

- Giữ một **`ROW EXCLUSIVE` table-level lock** trên quan hệ được cập nhật.
- Đánh dấu hàng liên quan theo cơ chế **tuple locking / MVCC**, khiến transaction khác muốn sửa cùng hàng phải chờ.
- Trong quá trình truy cập trang dữ liệu, sử dụng các cơ chế đồng bộ nội bộ trong khoảng thời gian ngắn hơn để bảo vệ cấu trúc shared-memory và buffer.

**Không có chuyện một khóa duy nhất được gọi chung là “khóa UPDATE” bao trùm cả ba lớp.**

## 2. Khóa và MVCC: điều cần hiểu trước

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)**. Một lần cập nhật hàng thường tạo phiên bản hàng mới và điều phối khả năng hiển thị theo snapshot của transaction.

Ví dụ:

~~~text
Đã commit: balance = 1000

Session A: BEGIN
Session A: UPDATE balance = 900    (chưa commit)

Session B: SELECT balance
           -> thường vẫn thấy 1000 ở READ COMMITTED

Session B: UPDATE balance = 800
           -> phải chờ transaction A nếu sửa cùng hàng
~~~

Đây không phải mâu thuẫn:

- **SELECT thông thường** có thể đọc phiên bản đã commit phù hợp với snapshot, không cần giành khóa hàng để đọc như `SELECT FOR UPDATE`.
- **UPDATE/DELETE/SELECT FOR UPDATE** tham gia cơ chế khóa và điều phối những thay đổi có thể xung đột trên cùng hàng.
- Một số lệnh DDL yêu cầu **khóa đối tượng mạnh** có thể chặn cả `SELECT` thông thường trên bảng liên quan.

### 2.1. Không đồng nhất “đọc được” với “không có khóa”

`SELECT` thông thường vẫn lấy `ACCESS SHARE` lock trên bảng, và backend vẫn sử dụng đồng bộ nội bộ khi đọc buffer. Câu “SELECT không khóa” chỉ là cách nói tắt gây hiểu lầm.

Cách nói chính xác hơn: **SELECT thông thường không lấy row-level lock để chặn những UPDATE bình thường**, nhưng vẫn tham gia cơ chế khóa quan hệ và các cơ chế nội bộ.

### 2.2. MVCC không loại bỏ mọi chờ khóa

Nếu hai transaction cùng sửa một hàng, chúng cần phối hợp để tránh lost update và xác định phiên bản/điều kiện cập nhật hợp lệ. PostgreSQL có thể chờ transaction trước kết thúc rồi đánh giá lại tùy isolation level và loại statement.

**MVCC làm giảm xung đột đọc–ghi thường gặp, không xóa xung đột ghi–ghi.**

## 3. Chuẩn bị schema thực hành

Chỉ chạy các lệnh sau trong **database lab**. Một số bài thực hành cố ý giữ transaction chưa commit hoặc tạo chờ khóa; không làm trực tiếp trên production.

### 3.1. Bảng tài khoản

~~~sql
CREATE SCHEMA lock_lab;

CREATE TABLE lock_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12, 2) NOT NULL CHECK (balance >= 0),
    note text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_lab.accounts (
    account_id, owner_name, balance, note
) VALUES
    (1, 'An',   1000.00, 'A'),
    (2, 'Binh',  500.00, 'B'),
    (3, 'Chi',   250.00, 'C'),
    (4, 'Dung',  300.00, 'D');
~~~

### 3.2. Bảng đơn hàng có khóa ngoại

~~~sql
CREATE TABLE lock_lab.orders (
    order_id integer PRIMARY KEY,
    account_id integer NOT NULL
        REFERENCES lock_lab.accounts(account_id),
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    status text NOT NULL CHECK (
        status IN ('new', 'paid', 'cancelled')
    )
);

INSERT INTO lock_lab.orders
    (order_id, account_id, amount, status)
VALUES
    (101, 1, 120.00, 'new'),
    (102, 1,  80.00, 'paid'),
    (201, 2,  50.00, 'new'),
    (301, 3, 200.00, 'paid');
~~~

### 3.3. Kiểm tra dữ liệu

~~~sql
SELECT account_id, owner_name, balance
FROM lock_lab.accounts
ORDER BY account_id;

SELECT order_id, account_id, status
FROM lock_lab.orders
ORDER BY order_id;
~~~

Các kịch bản bên dưới được thiết kế để kết thúc bằng `ROLLBACK` khi có thể, giúp khôi phục dữ liệu đầu vào. Nếu bạn tự `COMMIT` một thay đổi, giá trị lab sẽ thay đổi tương ứng.

### 3.4. Mở hai connection

Mở hai cửa sổ `psql` hoặc hai kết nối độc lập trong công cụ GUI:

~~~text
Session A: transaction thứ nhất
Session B: transaction thứ hai
~~~

Có thể xem PID của từng session:

~~~sql
SELECT pg_backend_pid();
~~~

Giá trị PID của A và B khác nhau. Việc kiểm tra PID giúp phân biệt **hai kết nối thực sự** với hai tab dùng chung connection.

## 4. Khóa đối tượng là gì?

Ở đây **khóa đối tượng** là những khóa PostgreSQL dùng để phối hợp thao tác trên một đối tượng database; loại dễ gặp nhất là **khóa cấp quan hệ/bảng** (*relation-level/table-level locks*).

Ví dụ:

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts IN SHARE MODE;
-- Giữ transaction mở.
~~~

Lệnh `LOCK TABLE` lấy mode `SHARE` trên bảng `accounts`. Các transaction muốn lấy một mode xung đột trên bảng sẽ chờ.

### 4.1. “Khóa bảng” không có nghĩa lúc nào cũng chặn mọi truy cập

PostgreSQL có **nhiều mode khóa bảng**. Một số mode có thể cùng tồn tại; mode khác xung đột và phải chờ.

Ví dụ:

- `SELECT` thông thường lấy `ACCESS SHARE`, tương thích với nhiều mode khác.
- `INSERT`/`UPDATE`/`DELETE` thường lấy `ROW EXCLUSIVE`.
- `ALTER TABLE` có thể yêu cầu `ACCESS EXCLUSIVE` trong nhiều trường hợp.

Không nên mô tả một câu `UPDATE` đơn giản là “khóa cả bảng, không ai dùng được”: mặc dù nó giữ table-level `ROW EXCLUSIVE`, **nhiều UPDATE trên các hàng khác nhau vẫn có thể chạy đồng thời**.

### 4.2. Khóa đối tượng bảo vệ điều gì?

Mục tiêu của relation-level lock không chỉ là dữ liệu của từng hàng. Nó phối hợp:

- Truy vấn và thay đổi dữ liệu.
- Tạo/sửa cấu trúc bảng, một số thao tác index.
- Bảo trì bảng hoặc thay đổi metadata có thể xung đột.
- Các operation cần ổn định cách sử dụng quan hệ trong transaction.

Những mode này là **heavyweight locks** do bộ quản lý khóa chính của PostgreSQL theo dõi. Khóa nhẹ nội bộ (LWLock) là cơ chế khác.

## 5. Tám mode khóa bảng PostgreSQL

Tên mode rất dễ gây nhầm: `ROW SHARE` và `ROW EXCLUSIVE` là **tên hai mode khóa cấp bảng**, **không phải** khóa một hàng cụ thể.

| Table-level mode | Một hoạt động thường liên quan | Ý nghĩa thực dụng |
| --- | --- | --- |
| `ACCESS SHARE` | `SELECT` thông thường | Đọc bảng; chủ yếu xung đột với ACCESS EXCLUSIVE |
| `ROW SHARE` | `SELECT ... FOR UPDATE/SHARE` | Đọc kết hợp yêu cầu khóa hàng |
| `ROW EXCLUSIVE` | `INSERT`, `UPDATE`, `DELETE` | DML ghi; không tự chặn mọi DML khác |
| `SHARE UPDATE EXCLUSIVE` | `VACUUM` thông thường, `ANALYZE`, một số thao tác bảo trì/DDL | Phối hợp bảo trì và các thay đổi cấu trúc |
| `SHARE` | `CREATE INDEX` thông thường, `LOCK TABLE ... IN SHARE MODE` | Có thể chặn DML ghi trong lúc xây index |
| `SHARE ROW EXCLUSIVE` | Một số thao tác DDL hoặc `LOCK TABLE` tường minh | Chặn nhiều loại ghi/bảo trì, tự xung đột |
| `EXCLUSIVE` | `LOCK TABLE ... IN EXCLUSIVE MODE` | Cho phép ACCESS SHARE nhưng chặn nhiều mode khác |
| `ACCESS EXCLUSIVE` | `TRUNCATE`, `DROP TABLE`, nhiều `ALTER TABLE` | Mode mạnh nhất; chặn cả SELECT thông thường |

**Mode được chọn phụ thuộc lệnh và phiên bản/cách thực thi cụ thể.** Không suy rằng mọi biến thể `ALTER TABLE` đều có cùng lock mode; cần xem tài liệu lệnh tương ứng khi đưa migration vào production.

### 5.1. ACCESS SHARE

~~~sql
SELECT *
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

Một `SELECT` thường lấy `ACCESS SHARE` trên quan hệ được truy cập. `ACCESS SHARE` **xung đột với ACCESS EXCLUSIVE**, nhưng tương thích với những mode cấp bảng còn lại.

Do vậy, trong nhiều tình huống, `SELECT` vẫn chạy khi transaction khác đang `UPDATE`, vì `UPDATE` giữ `ROW EXCLUSIVE` cấp bảng, **không xung đột với ACCESS SHARE**.

### 5.2. ROW SHARE

~~~sql
BEGIN;

SELECT *
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SELECT FOR UPDATE` lấy table-level `ROW SHARE` trên bảng liên quan, **đồng thời** khóa hàng được chọn theo mode row-level `FOR UPDATE`.

Phải phân biệt **ROW SHARE cấp bảng** với **FOR SHARE cấp hàng**: hai tên có chữ “SHARE”, nhưng ở **hai lớp khóa khác nhau**.

### 5.3. ROW EXCLUSIVE

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'changed'
WHERE account_id = 1;
ROLLBACK;
~~~

`UPDATE` thường lấy table-level `ROW EXCLUSIVE`. Tên nghe mạnh, nhưng mode này **tương thích với chính nó**: hai transaction cập nhật **hai hàng khác nhau** thường không chặn nhau chỉ bởi mode khóa bảng.

### 5.4. ACCESS EXCLUSIVE

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE;
-- Giữ transaction mở để quan sát.
~~~

Nếu B chạy `SELECT ... FROM lock_lab.accounts`, nó thường phải chờ mode mạnh ở A được thả.

Đây là ví dụ điển hình tại sao **DDL hoặc khóa đối tượng mạnh** có thể chặn cả các truy vấn đọc đơn giản.

## 6. Ma trận xung đột các mode cấp bảng

Ma trận dưới đây cho biết hai mode trên **cùng một quan hệ** có xung đột hay không. `X` là xung đột; `–` là tương thích.

| Đang giữ ↓ / Muốn lấy → | AS | RS | RX | SUE | S | SRE | X | AX |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AS** | – | – | – | – | – | – | – | X |
| **RS** | – | – | – | – | – | – | X | X |
| **RX** | – | – | – | – | X | X | X | X |
| **SUE** | – | – | – | X | X | X | X | X |
| **S** | – | – | X | X | – | X | X | X |
| **SRE** | – | – | X | X | X | X | X | X |
| **X** | – | X | X | X | X | X | X | X |
| **AX** | X | X | X | X | X | X | X | X |

Viết tắt:

- **AS** = `ACCESS SHARE`.
- **RS** = `ROW SHARE`.
- **RX** = `ROW EXCLUSIVE`.
- **SUE** = `SHARE UPDATE EXCLUSIVE`.
- **S** = `SHARE`.
- **SRE** = `SHARE ROW EXCLUSIVE`.
- **X** = `EXCLUSIVE`.
- **AX** = `ACCESS EXCLUSIVE`.

### 6.1. Đọc ma trận

**Trường hợp 1:** A giữ `ROW EXCLUSIVE`, B cũng muốn `ROW EXCLUSIVE` trên cùng bảng → **tương thích ở cấp bảng**. Nhưng hai transaction có thể vẫn chặn nhau ở **cấp hàng** nếu cùng sửa một hàng.

**Trường hợp 2:** A giữ `SHARE`, B muốn `ROW EXCLUSIVE` → **xung đột**. Một lệnh build index thông thường có thể khiến các transaction ghi phải chờ.

**Trường hợp 3:** A giữ `ACCESS EXCLUSIVE`, B muốn `ACCESS SHARE` → **xung đột**. Ngay cả SELECT thường cũng chờ.

### 6.2. Mode mạnh không luôn đồng nghĩa mọi đối tượng đều bị khóa

Khóa chỉ áp dụng cho **đối tượng cụ thể** và phạm vi phụ thuộc lệnh. `ACCESS EXCLUSIVE` trên bảng `accounts` không có nghĩa toàn database bị khóa. Các đối tượng liên quan (index, bảng tham chiếu, partition...) có thể có khóa riêng theo lệnh.

## 7. Thời điểm khóa đối tượng được giữ

Khóa table-level do statement yêu cầu thường được giữ **tới cuối transaction** (commit hoặc rollback), chứ không nhất thiết chỉ trong vài microsecond thực thi câu SQL.

~~~sql
-- Session A:
BEGIN;

LOCK TABLE lock_lab.accounts IN SHARE MODE;

-- Bây giờ A không chạy SQL thêm, nhưng transaction còn mở.
~~~

Session B:

~~~sql
-- Session B: DML cần ROW EXCLUSIVE và sẽ chờ.
UPDATE lock_lab.accounts
SET note = 'from B'
WHERE account_id = 1;
~~~

Sau khi A `COMMIT` hoặc `ROLLBACK`, B có cơ hội tiếp tục.

### 7.1. Autocommit ảnh hưởng thời gian giữ

Nếu bạn chạy riêng:

~~~sql
LOCK TABLE lock_lab.accounts IN SHARE MODE;
~~~

ngoài transaction tường minh ở chế độ autocommit, transaction của statement kết thúc ngay sau khi statement hoàn tất. Khóa không tiếp tục bảo vệ một bước xử lý ở câu SQL sau.

Muốn một khóa được giữ qua nhiều statement, phải dùng **cùng transaction và cùng connection**.

### 7.2. NOWAIT với LOCK TABLE

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE NOWAIT;
ROLLBACK;
~~~

`NOWAIT` yêu cầu **không chờ** nếu mode không thể lấy ngay. Trong một transaction, lỗi do không lấy được lock thường dẫn tới trạng thái cần rollback hoặc xử lý savepoint. Không xem NOWAIT là một cách “lấy lock bất chấp transaction khác”.

## 8. Khóa hàng là gì?

**Row-level lock** điều phối những transaction cạnh tranh với **cùng một hàng** khi muốn khóa, sửa hoặc xóa nó.

Ví dụ:

~~~sql
-- Session A:
BEGIN;
UPDATE lock_lab.accounts
SET note = 'A'
WHERE account_id = 1;
-- Chưa commit.
~~~

Session B:

~~~sql
-- Session B:
BEGIN;
UPDATE lock_lab.accounts
SET note = 'B'
WHERE account_id = 1;
-- Phải chờ transaction A trong tình huống thông thường.
~~~

Sau khi A kết thúc transaction, B có thể tiếp tục hoặc nhận lỗi tùy isolation và điều kiện. Nếu B sửa `account_id = 2` thay vì 1, thông thường nó có thể tiếp tục vì hai transaction đang sửa **hai hàng khác nhau**, dù đều giữ table-level `ROW EXCLUSIVE`.

### 8.1. Row-level lock không đồng nghĩa khóa nguyên table

Table-level `ROW EXCLUSIVE` do hai `UPDATE` lấy có thể tương thích. **Điểm xung đột của hai UPDATE cùng hàng thường nằm ở cơ chế tuple/transaction**, không phải do table-level ROW EXCLUSIVE tự xung đột.

### 8.2. Row locks được biểu diễn khác trong hệ thống

Thông tin khóa hàng có liên quan tới **tuple header** và trạng thái transaction/MultiXact, thay vì mọi khóa hàng đều xuất hiện như một entry “granted row lock” riêng biệt trong shared-memory lock table.

Vì vậy, `pg_locks` thường **không hiển thị đầy đủ mọi khóa hàng đang được giữ**. Khi một backend chờ hàng do transaction khác sửa, bạn thường thấy wait liên quan **`transactionid`** hoặc các lock manager entries khác, không phải một danh sách đơn giản “mỗi hàng đang khóa = một dòng pg_locks”.

## 9. Bốn mode khóa hàng

PostgreSQL hỗ trợ bốn mode row-level phổ biến:

| Row-level mode | Mục đích tiêu biểu | Độ mạnh tương đối |
| --- | --- | --- |
| `FOR KEY SHARE` | Bảo vệ khóa được tham chiếu, thường dùng trong kiểm tra FK | Nhẹ hơn FOR SHARE đối với update không đổi khóa |
| `FOR SHARE` | Giữ shared row lock khi đọc cần bảo vệ khỏi sửa/xóa | Cho nhiều reader cùng share |
| `FOR NO KEY UPDATE` | Khóa hàng khi update không thay đổi những khóa có liên quan đặc biệt | Mạnh hơn FOR SHARE, yếu hơn FOR UPDATE |
| `FOR UPDATE` | Khóa hàng mạnh nhất; dùng khi cần chống các thao tác cạnh tranh khác trên hàng | Xung đột với cả bốn mode |

Điểm quan trọng: đây là **row-level modes**, khác các tên mode cấp bảng.

### 9.1. FOR UPDATE

~~~sql
BEGIN;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Kiểm tra điều kiện, sau đó UPDATE trên cùng transaction.
ROLLBACK;
~~~

`FOR UPDATE` khóa các hàng được chọn bằng mode mạnh. Một transaction khác muốn `UPDATE`/`DELETE` hoặc lấy row lock xung đột trên cùng hàng thường phải chờ.

### 9.2. FOR NO KEY UPDATE

~~~sql
BEGIN;

SELECT account_id, note
FROM lock_lab.accounts
WHERE account_id = 1
FOR NO KEY UPDATE;

ROLLBACK;
~~~

Đây là mode yếu hơn `FOR UPDATE`: cho phép một số thao tác `FOR KEY SHARE` tương thích. PostgreSQL thường chọn mode phù hợp cho `UPDATE`, tùy việc cập nhật có thay đổi cột khóa đặc biệt hay không.

### 9.3. FOR SHARE

~~~sql
BEGIN;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR SHARE;

ROLLBACK;
~~~

Nhiều transaction có thể cùng giữ `FOR SHARE` trên một hàng. Tuy nhiên, chúng thường chặn một transaction muốn `UPDATE` hàng đó cho tới khi các khóa không còn.

### 9.4. FOR KEY SHARE

~~~sql
BEGIN;

SELECT account_id
FROM lock_lab.accounts
WHERE account_id = 1
FOR KEY SHARE;

ROLLBACK;
~~~

Mode này thường dùng để bảo vệ sự tồn tại/giá trị khóa tham chiếu; nó tương thích với `FOR NO KEY UPDATE` nhưng xung đột với `FOR UPDATE`. Đây là một nguyên nhân các thao tác kiểm tra FK và cập nhật cột không phải khóa có thể đồng thời trong nhiều trường hợp.

## 10. Ma trận xung đột khóa hàng

`X` = xung đột khi hai transaction khác nhau cùng yêu cầu mode trên **cùng hàng**; `–` = tương thích.

| Đang giữ ↓ / Muốn lấy → | KEY SHARE | SHARE | NO KEY UPDATE | UPDATE |
| --- | :---: | :---: | :---: | :---: |
| **FOR KEY SHARE** | – | – | – | X |
| **FOR SHARE** | – | – | X | X |
| **FOR NO KEY UPDATE** | – | X | X | X |
| **FOR UPDATE** | X | X | X | X |

Nhận xét:

1. Hai transaction cùng `FOR KEY SHARE` thường tương thích.
2. Hai transaction cùng `FOR SHARE` thường tương thích.
3. `FOR SHARE` chặn `FOR NO KEY UPDATE` và `FOR UPDATE` trên cùng hàng.
4. `FOR KEY SHARE` **không chặn** `FOR NO KEY UPDATE` nhưng chặn `FOR UPDATE`.
5. `FOR UPDATE` xung đột với tất cả mode hàng còn lại.

### 10.1. UPDATE không phải lúc nào cũng dùng mode mạnh nhất

Một `UPDATE` thay đổi cột **không phải khóa liên quan** thường sử dụng row-lock behavior tương ứng `FOR NO KEY UPDATE`. Khi update có thể thay đổi giá trị khóa được sử dụng theo quy tắc PostgreSQL, nó có thể đòi `FOR UPDATE`.

Không đồng nhất mọi `UPDATE` với `FOR UPDATE`; phân biệt này quan trọng khi có **foreign key** và `FOR KEY SHARE`.

### 10.2. DELETE

`DELETE` thường cần mode hàng mạnh tương đương `FOR UPDATE` vì loại bỏ hàng khiến những tham chiếu và thao tác giữ hàng khác không còn an toàn.

## 11. Thực hành 1: SELECT đọc được khi UPDATE chưa commit

Session A:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET balance = balance + 100
WHERE account_id = 1;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

A nhìn thấy **1100.00**, vì nó đọc được thay đổi chưa commit của chính transaction.

Session B:

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

Ở `READ COMMITTED` và không có thay đổi đã commit khác, B vẫn thấy **1000.00**. `SELECT` thông thường không bị khóa hàng đang sửa chặn theo cách `UPDATE` bị chặn.

Session A kết thúc:

~~~sql
ROLLBACK;
~~~

Tài khoản 1 trở về **1000.00**.

### 11.1. Đây không phải dirty read

PostgreSQL không cho Session B đọc giá trị 1100 chưa commit chỉ vì B sử dụng `READ UNCOMMITTED`; trong PostgreSQL, mức này thực tế được xử lý tương đương `READ COMMITTED` cho khả năng quan sát dữ liệu.

### 11.2. Cũng không có nghĩa B luôn đọc ngay

Nếu có **khóa đối tượng ACCESS EXCLUSIVE** trên bảng hoặc các chờ khác ở phía truy vấn, `SELECT` có thể bị chặn. Phải xem cả **loại chờ và đối tượng** thay vì suy chỉ từ MVCC.

## 12. Thực hành 2: hai UPDATE cùng hàng

Session A:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET note = 'session A'
WHERE account_id = 1;

-- Không COMMIT/ROLLBACK vội.
~~~

Session B:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET note = 'session B'
WHERE account_id = 1;
-- B thường đứng chờ transaction A.
~~~

Trong lúc B chờ, dùng **Session C** (connection thứ ba) để giám sát `pg_stat_activity` và `pg_locks` trong phần sau.

Session A:

~~~sql
ROLLBACK;
~~~

Lúc này B có thể tiếp tục `UPDATE`. Để giữ dữ liệu lab:

~~~sql
-- Session B:
ROLLBACK;
~~~

### 12.1. Đổi B sang hàng khác

Lặp lại nhưng B cập nhật:

~~~sql
UPDATE lock_lab.accounts
SET note = 'session B'
WHERE account_id = 2;
~~~

Nó thường tiếp tục mà **không phải chờ** row lock của A trên account 1. Cả hai transaction vẫn có thể đang giữ table-level `ROW EXCLUSIVE` trên bảng, nhưng mode đó **tương thích với chính nó**.

### 12.2. Lock wait không đồng nghĩa deadlock

Một chiều chờ:

~~~text
B chờ A
A không chờ B
~~~

chỉ là **lock contention** bình thường. Deadlock cần có **vòng phụ thuộc** như A chờ B đồng thời B chờ A.

## 13. Thực hành 3: SELECT FOR UPDATE so với SELECT thường

Session A:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
-- SELECT thường: thường đọc được.
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

Sau đó B thử:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;
-- B phải chờ hàng đang được A giữ.
~~~

Session A `ROLLBACK`, sau đó B `ROLLBACK`.

### 13.1. NOWAIT

Nếu không muốn B chờ:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
ROLLBACK;
~~~

Khi không lấy được row lock ngay, `NOWAIT` có thể trả lỗi thay vì đứng chờ. Nếu lỗi xảy ra trong transaction, cần rollback hoặc xử lý savepoint đúng cách.

### 13.2. SKIP LOCKED

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` có thể **bỏ qua những hàng đang bị khóa** thay vì chờ, hữu ích cho các mô hình **nhiều worker nhận việc từ queue**.

Nhưng kết quả là một góc nhìn **không đầy đủ và có thể thay đổi theo cạnh tranh**. Không dùng `SKIP LOCKED` tùy tiện cho báo cáo kiểm kê, thống kê tài chính hoặc truy vấn cần danh sách đầy đủ.

### 13.3. Phạm vi NOWAIT/SKIP LOCKED

Chúng chủ yếu điều khiển xử lý **row-level locking** của `SELECT FOR UPDATE/SHARE`. Chúng không biến mọi table-level lock wait thành “không chờ”; PostgreSQL vẫn cần lấy các khóa quan hệ liên quan.

## 14. Thực hành 4: khóa đối tượng mạnh chặn SELECT

Session A:

~~~sql
BEGIN;

LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE;

-- Giữ transaction mở.
~~~

Session B:

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
-- B thường phải chờ.
~~~

Không giống tình huống A chỉ `UPDATE` một hàng, lần này A giữ **ACCESS EXCLUSIVE relation lock**, xung đột với `ACCESS SHARE` mà B cần.

Session A:

~~~sql
ROLLBACK;
~~~

B tiếp tục. Đây là mô hình cơ bản của những lần **DDL hoặc lock mạnh làm query đọc bị đứng chờ**.

### 14.1. Lock queue và sự chờ lan truyền

Giả sử A giữ `ACCESS SHARE` trong một transaction dài, B đang chờ `ACCESS EXCLUSIVE`, rồi C bắt đầu `ACCESS SHARE`. Tùy hàng đợi và yêu cầu khóa, C cũng có thể bị chặn phía sau B để tránh bỏ đói yêu cầu khóa mạnh đang đợi.

Điều này lý giải vì sao một thay đổi schema đang **chờ** cũng có thể kéo theo nhiều SELECT mới bị chờ, dù bản thân các SELECT thường tương thích với khóa đọc của A.

Khi điều tra, đừng chỉ hỏi “ai đang giữ ACCESS EXCLUSIVE?”; hãy xem cả **request đang đợi** trong hàng đợi khóa.

## 15. Thực hành 5: khóa bảng SHARE chặn DML nhưng không chặn SELECT

Session A:

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts IN SHARE MODE;
~~~

Session B:

~~~sql
SELECT COUNT(*) FROM lock_lab.accounts;
-- Thường thực thi được vì ACCESS SHARE tương thích SHARE.
~~~

Nhưng:

~~~sql
UPDATE lock_lab.accounts
SET note = 'test'
WHERE account_id = 1;
-- Yêu cầu ROW EXCLUSIVE; xung đột với SHARE.
~~~

Session A `ROLLBACK` giải phóng SHARE lock.

Ý chính: **khóa đối tượng có nhiều mức mạnh yếu và ma trận xung đột**, không phải một công tắc “khóa bảng/không khóa bảng”.

## 16. Khóa hàng và FOREIGN KEY

Foreign key không chỉ là một constraint kiểm tra tồn tại. Để bảo vệ tính toàn vẹn tham chiếu khi có concurrent changes, PostgreSQL có thể dùng cơ chế row lock phù hợp trên hàng được tham chiếu.

Trong lab:

~~~sql
CREATE TABLE lock_lab.orders (
    -- ...
    account_id integer NOT NULL
        REFERENCES lock_lab.accounts(account_id)
);
~~~

Khi chèn đơn mới tham chiếu `account_id = 1`, PostgreSQL phải bảo đảm hàng account tham chiếu còn hợp lệ. Một cơ chế liên quan là khóa hàng được tham chiếu theo mức **`FOR KEY SHARE`**.

### 16.1. Vì sao FOR KEY SHARE yếu hơn FOR SHARE?

Giả sử transaction A cập nhật `note` của account 1 nhưng **không đổi khóa**:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'updated without changing key'
WHERE account_id = 1;
~~~

`UPDATE` không đổi khóa thường dùng row-lock semantics tương tự `FOR NO KEY UPDATE`; mode này **tương thích với `FOR KEY SHARE`**. Vì vậy, trong nhiều tình huống, transaction khác chèn hàng con tham chiếu account 1 vẫn có thể tiếp tục.

Nếu A **xóa hàng cha** hoặc thay đổi khóa được tham chiếu, xung đột với việc bảo vệ khóa tham chiếu quan trọng hơn, và transaction phải được điều phối để không vi phạm FK.

### 16.2. Không tự suy tất cả FK đều chờ giống nhau

Hành vi còn phụ thuộc:

- Thao tác đang làm là `INSERT` hàng con, `UPDATE` khóa hay `DELETE` hàng cha.
- Constraint `NOT DEFERRABLE` hay `DEFERRABLE`, và thời điểm kiểm tra.
- Index/khóa trên hàng tham chiếu.
- Thứ tự thực hiện của các transaction.

**Mode `FOR KEY SHARE` không thay thế thiết kế FK**, và một lệnh SQL thực tế có thể lấy nhiều loại khóa trên cả bảng cha và bảng con.

## 17. Khóa đối tượng và bảo trì: VACUUM, ANALYZE, CREATE INDEX

Các công việc bảo trì cần phối hợp với DML/DDL, nhưng không phải tác vụ bảo trì nào cũng khóa bảng giống nhau.

| Hoạt động | Cơ chế khóa đáng chú ý |
| --- | --- |
| `VACUUM` thông thường | Liên quan `SHARE UPDATE EXCLUSIVE` trên bảng được xử lý |
| `ANALYZE` | Thường dùng mode bảo trì như `SHARE UPDATE EXCLUSIVE` |
| `VACUUM FULL` | Cần khóa rất mạnh, thường `ACCESS EXCLUSIVE` |
| `CREATE INDEX` thông thường | Liên quan `SHARE`, có thể chặn ghi |
| `CREATE INDEX CONCURRENTLY` | Quy trình/khóa khác để hạn chế chặn ghi, nhưng có yêu cầu chạy ngoài transaction block |
| Một số `ALTER TABLE` | Có thể yêu cầu `ACCESS EXCLUSIVE` tùy lệnh |

### 17.1. VACUUM thường và VACUUM FULL

~~~sql
VACUUM (ANALYZE) lock_lab.accounts;
~~~

khác rất nhiều về mức tác động khóa so với:

~~~sql
VACUUM FULL lock_lab.accounts;
~~~

`VACUUM FULL` viết lại bảng và đòi khóa mạnh, dễ chặn truy cập. Khi lên kế hoạch vận hành, phải phân biệt **loại VACUUM** thay vì dùng một tên chung.

### 17.2. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_account_status
ON lock_lab.orders(account_id, status);
~~~

Lệnh này được thiết kế giảm chặn ghi trong một số bối cảnh, nhưng có nhiều giai đoạn xử lý, yêu cầu chờ các transaction/snapshot liên quan và **không được chạy bên trong transaction block tường minh thông thường**.

Đừng kết luận “CONCURRENTLY nghĩa là không có lock hay không thể chờ”. Nó vẫn phối hợp với các tiến trình khác và có các hạn chế vận hành.

## 18. Khóa nội bộ là gì?

Ngoài những khóa điều khiển truy cập **logic tới quan hệ/hàng**, PostgreSQL cần đồng bộ các backend cùng hoạt động trên:

- Buffer trong `shared_buffers`.
- Các cấu trúc shared memory.
- Metadata của buffer manager và các cấu trúc kiểm soát.
- Một số cấu trúc liên quan WAL và quản lý tài nguyên nội bộ.

Các cơ chế nội bộ có thể gồm **lightweight locks (LWLocks)**, **spinlocks**, **buffer pins** và những cơ chế đồng bộ khác.

### 18.1. LWLock

**Lightweight lock** bảo vệ cấu trúc dữ liệu nội bộ hoặc vùng tài nguyên dùng chung trong các khoảng xử lý ngắn/phù hợp. Backend cần lấy LWLock khi thao tác trên một cấu trúc nhất định; nếu backend khác giữ mode xung đột, nó có thể phải đợi.

Khác với `LOCK TABLE`:

- Ứng dụng **không chọn** một LWLock cụ thể qua SQL `LOCK TABLE`.
- LWLock **không đại diện cho khóa hàng nghiệp vụ**.
- Thời gian giữ và quy tắc sở hữu được engine quản lý theo hoạt động nội bộ, không phải “từ BEGIN đến COMMIT” theo mọi trường hợp.
- Một truy vấn đọc bình thường cũng có thể gặp contention LWLock nếu nhiều backend cùng truy cập tài nguyên nội bộ.

### 18.2. Spinlock

Spinlock là cơ chế đồng bộ mức thấp dùng để bảo vệ một số trạng thái shared memory trong **đoạn mã rất ngắn**. Khi tranh chấp, thao tác lấy spinlock có thể phải quay vòng chờ trong một khoảng ngắn theo triển khai.

Không dùng spinlock như một thuật ngữ đồng nghĩa với `FOR UPDATE`. Spinlock thuộc **nội bộ database engine**, không phải “khóa bản ghi” mà nhà phát triển ứng dụng bật/tắt bằng SQL.

### 18.3. Buffer pin

**Buffer pin** là cách một backend giữ tham chiếu tới buffer để bảo vệ việc dùng buffer khỏi những hoạt động như loại/thay thế không phù hợp trong thời gian còn tham chiếu.

Một backend có thể chờ `BufferPin` nếu hoạt động yêu cầu buffer không bị pin nhưng backend khác vẫn giữ pin. `BufferPin` được giám sát như **wait_event_type riêng**, không nên gộp thành `LWLock`.

### 18.4. Khóa trang/buffer không phải khóa hàng

Khi đọc/ghi một trang dữ liệu, PostgreSQL có thể cần đồng bộ ngắn hạn ở mức trang/buffer. Nhưng **row-level locks** điều phối giao dịch sửa cùng hàng theo một cơ chế khác.

Không nên nói “PostgreSQL chỉ khóa page” thay cho khóa hàng: PostgreSQL có thể đồng thời sử dụng **đồng bộ trang/buffer nội bộ** và **khóa row/transaction**.

## 19. So sánh khóa đối tượng, hàng và nội bộ

| Tiêu chí | Khóa đối tượng / relation | Khóa hàng / tuple | Khóa nội bộ / LWLock, spinlock... |
| --- | --- | --- | --- |
| Bảo vệ | Quyền truy cập/phối hợp thao tác trên quan hệ và đối tượng | Cạnh tranh trên hàng cụ thể | Cấu trúc engine, shared memory, buffer... |
| Ví dụ SQL tạo nhu cầu | `SELECT`, `UPDATE`, `ALTER TABLE`, `LOCK TABLE` | `UPDATE`, `DELETE`, `SELECT FOR UPDATE` | Bất kỳ query nào cần engine truy cập cấu trúc liên quan |
| Người dùng chọn mode trực tiếp? | Có thể với `LOCK TABLE`; nhiều lệnh tự lấy | Có thể với `FOR UPDATE/SHARE`; DML tự chọn phù hợp | Không qua SQL thông thường |
| Thời gian giữ điển hình | Thường tới cuối transaction | Thường tới cuối transaction | Theo đoạn thao tác nội bộ, thường ngắn hơn |
| Có entry đầy đủ trong `pg_locks`? | Nhiều heavyweight locks có thể thấy | **Không** có danh sách đầy đủ mọi granted row lock | **Không** biểu diễn bằng các row `pg_locks` tương ứng |
| Dấu hiệu chờ thường gặp | `wait_event_type = 'Lock'` | `Lock`, thường trên `transactionid` hoặc các lock entries liên quan | `LWLock`, `BufferPin` hoặc nhóm wait event khác |
| Cách điều tra | Ma trận mode, `pg_locks`, blocker PID | Hai session, transactionid, `pg_blocking_pids` | `pg_stat_activity.wait_event_type/wait_event`, workload/internal contention |
| Hướng xử lý | Rút ngắn transaction, lên lịch DDL, chọn lock mode phù hợp | Thứ tự cập nhật, index, NOWAIT/SKIP LOCKED đúng chỗ, rollback | Phân tích workload, phiên bản, IO/buffer/WAL, số connection và kế hoạch thực thi |

### 19.1. Cùng một query có thể chờ nhiều nguyên nhân

Một lệnh `UPDATE` chậm có thể vì:

- Bị transaction khác giữ **row lock** trên cùng hàng.
- Bị một **relation lock** xung đột do DDL.
- Đang chờ **LWLock** nội bộ.
- Đang chờ **IO**.
- Có plan chậm, quét quá nhiều hàng, hoặc CPU bận.

**Không chẩn đoán tất cả bằng cách tìm “locked rows”.**

## 20. Heavyweight locks không chỉ có relation

Trong `pg_locks`, PostgreSQL còn có những loại khóa/đối tượng chờ như:

- `relation`: quan hệ (bảng, index, v.v. theo thao tác).
- `transactionid`: chờ hoặc giữ quyền liên quan một transaction ID.
- `virtualxid`: liên quan virtual transaction ID.
- `tuple` và `page`: một số entry trong quá trình điều phối khóa/đợi.
- `object` và các locktype khác phục vụ loại đối tượng/cơ chế cụ thể.
- `advisory`: khóa do ứng dụng chủ động yêu cầu, theo ID logic.

**Khóa theo transaction ID** rất quan trọng: khi B chờ A sửa một hàng, B có thể chờ transaction ID của A hoàn tất. Truy vấn chỉ tìm `locktype = 'tuple'` thường **bỏ sót** dạng chờ này.

### 20.1. Transaction-ID wait khác relation-level conflict

Mẫu:

~~~text
A giữ thay đổi chưa commit trên account 1
B muốn UPDATE account 1
B chờ transaction của A kết thúc
~~~

`pg_locks` có thể hiển thị B đang chờ `ShareLock` trên `transactionid` của A, trong khi A giữ quyền tương ứng cho transaction đó.

**Không kết luận B không bị khóa hàng chỉ vì không thấy một granted `tuple` entry trong `pg_locks`.**

### 20.2. Row-level locks có dấu vết trong tuple

Khóa hàng dùng thông tin trong tuple/header và có thể liên quan `MultiXactId` khi nhiều transaction cùng chia sẻ trạng thái khóa một hàng. Đây là lý do không xem row locks như một mảng entry đơn giản giống khóa relation trong shared-memory lock table.

Người viết ứng dụng thường không cần xử lý trực tiếp tuple headers hoặc MultiXact; khi vận hành, cần nhận ra biểu hiện qua `transactionid` waits và kết quả xung đột row-level.

## 21. Advisory locks: khóa do ứng dụng đặt ra

PostgreSQL cung cấp **advisory locks** để ứng dụng đồng bộ theo một khóa số logic, chẳng hạn “chỉ một worker xử lý job 42”.

~~~sql
BEGIN;

SELECT pg_advisory_xact_lock(42);

-- Công việc cần độc quyền theo khóa 42 trong transaction.

ROLLBACK;
~~~

`pg_advisory_xact_lock` gắn với transaction và được thả khi transaction kết thúc. Cũng có các dạng **session-level advisory locks** được giữ theo phiên cho tới khi mở khóa hoặc session kết thúc.

### 21.1. Advisory lock khác FK/row lock

Advisory lock **không tự buộc mọi SQL sửa account 42 phải tôn trọng khóa 42**. Chỉ những đoạn code có quy ước cùng lấy advisory lock liên quan mới phối hợp theo cách ấy.

Với row locks, PostgreSQL thực thi xung đột khi các transaction thao tác trên cùng hàng theo ngữ nghĩa SQL. Với advisory lock, **quy tắc ứng dụng** quyết định ý nghĩa ID.

### 21.2. TRY lock

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(42) AS acquired;

ROLLBACK;
~~~

Hàm trả boolean: nếu không lấy được ngay thì `false`, thay vì chờ. Với workflow thật, code phải kiểm tra `acquired` trước khi thực hiện công việc được bảo vệ.

### 21.3. Không xem advisory lock là transaction

Advisory lock giúp phối hợp concurrency; nó **không tự tạo tính nguyên tử** cho những thay đổi ngoài phạm vi transaction hoặc các side effects bên ngoài.

## 22. Predicate locks và SERIALIZABLE

PostgreSQL có **Serializable Snapshot Isolation (SSI)** ở mức `SERIALIZABLE`. Để phát hiện những mẫu xung đột đọc–ghi có thể phá tính tuần tự hóa, PostgreSQL sử dụng cơ chế **predicate/SIRead locks** và theo dõi các phụ thuộc.

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM lock_lab.orders
WHERE amount > 100;

-- Các lệnh khác...
COMMIT;
~~~

Trong `pg_locks` có thể thấy mode `SIReadLock` liên quan cơ chế SSI trong những tình huống nhất định.

### 22.1. SIReadLock không giống ACCESS EXCLUSIVE

Predicate/SIRead lock **không nhằm chặn ngay mọi writer** có thao tác khớp điều kiện như một row lock mạnh. PostgreSQL có thể để transactions chạy rồi **hủy một transaction bằng serialization failure** khi phát hiện chuỗi phụ thuộc không tuần tự hóa an toàn.

Đây là nhóm khác với:

- `FOR UPDATE` dùng để khóa hàng trực tiếp.
- Relation-level `ACCESS EXCLUSIVE` chặn mode xung đột.
- LWLock nội bộ dùng bảo vệ shared-memory structures.

### 22.2. Xử lý SQLSTATE 40001

Nếu một transaction ở `SERIALIZABLE` bị lỗi `40001`, ứng dụng thường cần **retry toàn bộ transaction** (không chỉ statement lỗi) theo chiến lược có giới hạn và idempotency phù hợp.

Không tăng isolation rồi giả định sẽ không còn thất bại concurrency; chi phí kiểm tra và khả năng retry là một phần thiết kế.

## 23. Quan sát lock bằng pg_stat_activity

`pg_stat_activity` cho biết trạng thái backend, query đang chạy, thời điểm bắt đầu transaction, cùng loại chờ hiện tại.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - xact_start AS transaction_age,
    LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
~~~

### 23.1. Các giá trị wait_event_type thường gặp

| wait_event_type | Gợi ý điều tra |
| --- | --- |
| `Lock` | Backend đang chờ một heavyweight lock hoặc cơ chế lock-manager liên quan |
| `LWLock` | Đang chờ lightweight lock nội bộ |
| `BufferPin` | Đang chờ buffer pin được thả |
| `IO` | Đang chờ hoạt động I/O |
| `Client` | Đang chờ hoạt động giao tiếp client |
| `IPC` | Đang chờ một tín hiệu/sự kiện phối hợp tiến trình |
| `Timeout` | Đang chờ timeout/timer theo một hoạt động cụ thể |

Các giá trị/event chi tiết phụ thuộc phiên bản PostgreSQL và trạng thái thực tế. `wait_event_type IS NULL` không đủ để kết luận query có hay không có vấn đề.

### 23.2. Đừng nhầm state với wait_event_type

`state = 'active'` cho biết backend đang thực thi query hoặc đang hoạt động trong ngữ cảnh query. Nó **vẫn có thể đang chờ** với `wait_event_type = 'Lock'`.

`state = 'idle in transaction'` nghĩa là transaction vẫn mở nhưng backend đang chờ lệnh từ client; session này có thể **giữ khóa và chặn người khác**, dù bản thân nó không ở trạng thái active.

### 23.3. Quyền đọc thông tin

Session thường chỉ có quyền nhìn đầy đủ query/thông tin của chính mình nếu không được cấp quyền giám sát. Các vai trò quản trị hoặc `pg_read_all_stats` có thể được dùng trong chính sách quyền phù hợp. Không tăng quyền tùy tiện chỉ để chạy truy vấn giám sát.

## 24. Quan sát heavyweight locks bằng pg_locks

~~~sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    CASE
        WHEN l.locktype = 'relation'
        THEN l.relation::regclass::text
        ELSE NULL
    END AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_locks AS l
WHERE l.database = (
    SELECT oid FROM pg_database
    WHERE datname = current_database()
)
   OR l.database IS NULL
ORDER BY l.pid NULLS LAST, l.locktype, l.mode;
~~~

Những cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | Backend PID nếu lock gắn với backend đang hoạt động; một số trường hợp có thể null |
| `locktype` | Loại đối tượng của khóa: relation, transactionid, virtualxid, advisory... |
| `mode` | Mode cụ thể, ví dụ `AccessShareLock` hoặc `RowExclusiveLock` |
| `granted` | `true` nếu đã được cấp; `false` nếu đang chờ |
| `waitstart` | Thời điểm bắt đầu đợi, khi có dữ liệu phù hợp |
| `relation` | OID của relation khi locktype tương ứng |
| `transactionid` | Transaction ID liên quan nếu locktype phù hợp |

Tên mode trong `pg_locks` thường có cách viết như `AccessShareLock`, khác kiểu có khoảng trắng trong câu `LOCK TABLE ... IN ACCESS SHARE MODE`.

### 24.1. Không dùng pg_locks như danh sách mọi row lock

`pg_locks` biểu diễn **các khóa do lock manager và các cơ chế quan sát tương ứng cung cấp**, không phải một bảng liệt kê mọi tuple đang bị `FOR UPDATE`.

Để điều tra chờ sửa hàng, kết hợp:

1. `pg_stat_activity.wait_event_type = 'Lock'`.
2. `pg_blocking_pids(pid)`.
3. Các dòng `transactionid`/`tuple` liên quan trong `pg_locks`.
4. Thông tin query, transaction age và hành vi của hai session.

### 24.2. Chuyển relation OID thành tên

`l.relation::regclass` hữu ích khi relation thuộc database hiện tại. Với lock liên quan database khác, không nên giả định OID luôn có thể diễn giải giống database của session đang truy vấn.

## 25. Tìm session bị chặn và blocker thực sự

Hàm `pg_blocking_pids(pid)` trả danh sách PID đang **chặn** session được chỉ định theo cơ chế khóa PostgreSQL.

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS query_age,
    now() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 200) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start NULLS LAST;
~~~

Khi Session B bị chặn bởi UPDATE chưa commit của A, `blocking_pids` có thể chứa PID của A.

### 25.1. Ghép để thấy query của blocker

~~~sql
SELECT
    waiter.pid AS waiting_pid,
    waiter.state AS waiting_state,
    waiter.wait_event_type AS waiting_type,
    waiter.wait_event AS waiting_event,
    LEFT(waiter.query, 160) AS waiting_query,
    b.blocker_pid,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    LEFT(blocker.query, 160) AS blocker_last_query
FROM pg_stat_activity AS waiter
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiter.pid))
    AS b(blocker_pid)
LEFT JOIN pg_stat_activity AS blocker
    ON blocker.pid = b.blocker_pid
WHERE waiter.datname = current_database()
ORDER BY waiter.pid, b.blocker_pid;
~~~

Chú ý:

- Blocker có thể đang `idle in transaction`, nghĩa là nó không chạy SQL nữa nhưng vẫn giữ khóa.
- Thông tin `query` ở blocker idle thường là **câu SQL gần nhất**, không nhất thiết câu gây ra tất cả khóa còn giữ.
- Một số blocker đặc biệt (ví dụ prepared transaction) không có backend PID đang hoạt động; kết quả quan sát cần được diễn giải theo bối cảnh.
- `pg_blocking_pids()` tập trung vào quan hệ blocker trong hệ thống lock manager, **không phải công cụ giải thích mọi loại IO/LWLock wait**.

### 25.2. Không tự kết luận blocker là thủ phạm duy nhất

Một transaction đang giữ khóa lâu có thể là nguyên nhân trực tiếp, nhưng gốc vấn đề có thể là code mở transaction rồi gọi HTTP, migration chạy sai thời điểm, hoặc truy vấn đã làm việc lâu và không commit.

Hướng khắc phục thường thuộc **quy trình giao dịch và workload**, không chỉ “kill PID bị nhìn thấy”.

## 26. Phân tích một chuỗi chờ theo bước

Giả sử:

~~~text
Session A: BEGIN; UPDATE account_id=1;  (chưa COMMIT)
Session B: BEGIN; UPDATE account_id=1;  (đang chờ)
Session C: query pg_stat_activity / pg_locks
~~~

Khi quan sát có thể thấy:

1. Session B có `state = 'active'`, `wait_event_type = 'Lock'` và event phù hợp cơ chế chờ transaction.
2. `pg_blocking_pids(B_PID)` trả PID của A.
3. Session A có `state = 'idle in transaction'` nếu đang chờ người dùng nhập lệnh.
4. `pg_locks` có các entry khóa relation tương thích của cả A và B, nhưng B vẫn chờ **transactionid/tuple-level conflict**.
5. Khi A `ROLLBACK`/`COMMIT`, B được đánh thức để tiếp tục/đánh giá lại.

### 26.1. Vì sao chỉ xem khóa bảng dễ chẩn đoán sai?

Nếu bạn chỉ kiểm tra:

~~~sql
SELECT *
FROM pg_locks
WHERE locktype = 'relation'
  AND relation = 'lock_lab.accounts'::regclass;
~~~

có thể thấy A và B đều giữ `RowExclusiveLock` với `granted = true`. Vì mode table-level này tương thích, bạn sẽ thắc mắc vì sao B chờ.

**Lý do là chờ khóa hàng/transaction**, không phải xung đột giữa hai `RowExclusiveLock` của bảng.

### 26.2. Quan sát lock đang đợi

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    transactionid,
    relation::regclass AS relation_name
FROM pg_locks
WHERE NOT granted
ORDER BY pid, locktype, mode;
~~~

Truy vấn này hướng tới những lock request chưa được cấp, nhưng không mô tả tất cả các loại chờ khác `Lock`. Không đòi mỗi lần block phải có `relation_name`: locktype `transactionid` có thể không liên quan một OID bảng trong chính entry đó.

## 27. Deadlock: vòng chờ, không chỉ chờ lâu

Hai transaction cùng muốn sửa hai tài khoản theo **thứ tự ngược nhau**:

~~~text
Session A                         Session B
BEGIN                             BEGIN
UPDATE account 1                  UPDATE account 2
      |                                 |
UPDATE account 2  (chờ B)         UPDATE account 1 (chờ A)
      |                                 |
      +------------ vòng chờ -----------+
~~~

### 27.1. Tái hiện trong lab

Session A:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'A1'
WHERE account_id = 1;
~~~

Session B:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'B2'
WHERE account_id = 2;
~~~

Session A tiếp tục:

~~~sql
UPDATE lock_lab.accounts
SET note = 'A2'
WHERE account_id = 2;
-- Chờ B.
~~~

Session B tiếp tục:

~~~sql
UPDATE lock_lab.accounts
SET note = 'B1'
WHERE account_id = 1;
-- Tạo vòng chờ.
~~~

PostgreSQL có cơ chế phát hiện deadlock và thường hủy một transaction để phá vòng. Lỗi thường có SQLSTATE **`40P01`**.

Kết thúc bài thực hành bằng `ROLLBACK` ở hai session khi có thể.

### 27.2. Tránh deadlock bằng thứ tự khóa nhất quán

Trong một nghiệp vụ phải sửa nhiều tài khoản, nên dùng **quy tắc thứ tự lấy khóa**, chẳng hạn theo `account_id` tăng dần, để giảm trường hợp A khóa 1→2 còn B khóa 2→1.

Cũng nên:

- Giữ transaction ngắn.
- Hạn chế cập nhật nhiều bảng theo thứ tự khác nhau giữa các luồng.
- Có retry **toàn transaction** với giới hạn cho `40P01` khi nghiệp vụ cho phép.
- Tránh gọi mạng và chờ người dùng trong khi đang giữ khóa.

### 27.3. Deadlock detector không thay lock timeout

PostgreSQL tự phát hiện **vòng chờ**, nhưng một session chờ transaction khác rất lâu **mà không có vòng chờ** có thể tiếp tục đợi. Đó là lý do `lock_timeout` và quan sát vận hành vẫn quan trọng.

## 28. Timeout: kiểm soát chờ khóa

Ba timeout thường gặp:

| Tham số | Mục đích |
| --- | --- |
| `lock_timeout` | Giới hạn thời gian chờ một lock |
| `statement_timeout` | Giới hạn thời gian chạy statement tổng thể |
| `idle_in_transaction_session_timeout` | Ngắt session idle quá lâu khi còn transaction |

### 28.1. SET LOCAL lock_timeout

~~~sql
BEGIN;

SET LOCAL lock_timeout = '1500ms';

UPDATE lock_lab.accounts
SET note = 'timeout_demo'
WHERE account_id = 1;

ROLLBACK;
~~~

Nếu statement phải chờ lock quá 1,5 giây, PostgreSQL có thể báo lỗi timeout. `SET LOCAL` chỉ có hiệu lực trong transaction hiện tại.

Lưu ý: sau lỗi timeout trong transaction, transaction có thể **aborted**; cần rollback hoặc xử lý savepoint trước khi chạy lệnh khác.

### 28.2. statement_timeout khác lock_timeout

`statement_timeout` đo thời gian thực thi statement và có thể bao gồm thời gian chờ khóa. `lock_timeout` nhắm riêng **thời gian đợi lock**. Đặt `lock_timeout` dài hơn `statement_timeout` thường không thêm lợi ích vì statement có thể bị hủy trước.

### 28.3. deadlock_timeout là gì?

`deadlock_timeout` liên quan thời điểm PostgreSQL tiến hành kiểm tra deadlock sau khi chờ khóa đủ lâu, và cũng ảnh hưởng một số hành vi log chờ khóa khi cấu hình. Đây không phải “thời gian tối đa cho phép một lock được giữ”.

Không thay đổi cấu hình này tùy tiện trên production; điều tra lock contention bằng thông số chờ thực tế và giám sát.

## 29. Idle in transaction: blocker không chạy SQL vẫn giữ khóa

Session A:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'still locked'
WHERE account_id = 1;

-- Bây giờ người dùng rời bàn, không COMMIT/ROLLBACK.
~~~

Session có thể trở thành `idle in transaction`. Nó **không active**, nhưng lock của transaction vẫn được giữ.

Session B muốn sửa account 1 sẽ chờ. Nếu A giữ snapshot hoặc transaction horizon lâu, tác động còn có thể lan tới VACUUM và bloat.

### 29.1. Tìm transaction lâu

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    LEFT(query, 160) AS last_query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
~~~

### 29.2. Vì sao cần xử lý từ ứng dụng?

Nguyên nhân thường là:

- Code mở transaction rồi quên commit/rollback ở nhánh lỗi.
- Connection pool nhận lại connection chưa được dọn đúng.
- Công cụ SQL để chế độ manual commit.
- Ứng dụng gọi HTTP hoặc làm việc lâu trong transaction.
- Một script interative dừng sau UPDATE để chờ người dùng.

Giải pháp lâu dài là **định nghĩa ranh giới transaction rõ**, cleanup mọi nhánh lỗi, giảm thời gian giữ connection và khóa. Timeout chỉ là lớp bảo vệ bổ sung.

## 30. Có nên hủy backend đang chặn?

PostgreSQL có các hàm quản trị:

~~~sql
SELECT pg_cancel_backend(<pid>);
SELECT pg_terminate_backend(<pid>);
~~~

Đây là **cú pháp minh họa**, `<pid>` phải được thay bằng PID thực và đòi quyền phù hợp.

- `pg_cancel_backend` yêu cầu hủy query hiện tại của backend đích; không nhất thiết kết thúc session hoặc tự xóa transaction đang idle.
- `pg_terminate_backend` yêu cầu kết thúc backend/session, thường khiến transaction chưa commit bị rollback và connection bị đóng.

### 30.1. Không kill chỉ vì thấy wait

Trước khi can thiệp phải xác định:

1. PID đang chờ hay đang **giữ khóa**?
2. Transaction của blocker có chứa công việc quan trọng chưa commit không?
3. Blocker là request nghiệp vụ, migration, batch hay maintenance?
4. Có thể yêu cầu ứng dụng commit/rollback an toàn không?
5. Việc terminate có gây retry hàng loạt hoặc sự cố kết nối không?

Không hủy bừa các tiến trình PostgreSQL hoặc các backend không rõ vai trò. Với hệ thống production, hành động dừng session cần theo quy trình vận hành và quyền được phê duyệt.

## 31. Một số hiểu lầm phổ biến

### Hiểu lầm 1: PostgreSQL không có khóa vì đã có MVCC

Sai. MVCC hỗ trợ visibility theo snapshot, còn DML/DDL vẫn dùng locks để điều phối cạnh tranh và cấu trúc.

### Hiểu lầm 2: UPDATE khóa toàn bảng nên mọi UPDATE phải chạy tuần tự

Sai. `UPDATE` thường giữ table-level `ROW EXCLUSIVE`, mode này tương thích với chính nó; những transaction sửa các hàng khác nhau có thể cùng chạy.

### Hiểu lầm 3: ROW EXCLUSIVE là row-level lock

Sai. `ROW EXCLUSIVE` thuộc **tám mode khóa bảng**. `FOR NO KEY UPDATE` hoặc `FOR UPDATE` mới là **mode khóa hàng**.

### Hiểu lầm 4: SELECT không bao giờ bị chặn

Sai. `SELECT` bình thường thường không bị row lock của một UPDATE khác chặn, nhưng `ACCESS EXCLUSIVE` relation lock có thể chặn cả SELECT.

### Hiểu lầm 5: Đọc dữ liệu chưa commit vì SELECT không bị chặn

Sai. MVCC bảo đảm visibility theo isolation; đọc được phiên bản cũ **không phải dirty read** của phiên bản chưa commit.

### Hiểu lầm 6: pg_locks liệt kê mọi hàng đang bị FOR UPDATE

Sai. Granted tuple locks không xuất hiện đầy đủ như các relation locks. Row contention có thể hiện thành chờ `transactionid`.

### Hiểu lầm 7: wait_event_type = Lock luôn là khóa bảng

Sai. Heavyweight lock waits có thể liên quan relation, transactionid, tuple, object, advisory và những loại khác.

### Hiểu lầm 8: LWLock là một mode của LOCK TABLE

Sai. LWLock bảo vệ cấu trúc nội bộ, không do SQL `LOCK TABLE` chọn.

### Hiểu lầm 9: BufferPin chính là LWLock

Sai. PostgreSQL báo `BufferPin` như một loại chờ riêng; cần phân biệt nguyên nhân và cách tối ưu.

### Hiểu lầm 10: FOR SHARE và ROW SHARE là một

Sai. `FOR SHARE` là mode **khóa hàng**; `ROW SHARE` là mode **khóa bảng**.

### Hiểu lầm 11: FOR KEY SHARE ngăn mọi UPDATE

Sai. `FOR KEY SHARE` tương thích với `FOR NO KEY UPDATE` trên cùng hàng, nhưng xung đột với `FOR UPDATE`.

### Hiểu lầm 12: SKIP LOCKED cho kết quả báo cáo đầy đủ

Sai. Nó bỏ qua những hàng đang bị khóa, phù hợp một số queue worker nhưng không phù hợp thống kê đòi tất cả hàng.

### Hiểu lầm 13: Một session chờ là deadlock

Sai. Deadlock là **vòng chờ**, không phải chỉ một chiều chờ giữa hai transaction.

### Hiểu lầm 14: Thêm timeout là đã sửa nguyên nhân

Timeout giới hạn thời gian chờ, không thay thế transaction ngắn, lock ordering và thiết kế nghiệp vụ đúng.

### Hiểu lầm 15: CREATE INDEX CONCURRENTLY không dùng khóa

Sai. Lệnh vẫn phải phối hợp với các transaction và có những giai đoạn chờ; nó chỉ giảm một số kiểu chặn ghi so với CREATE INDEX thường.

### Hiểu lầm 16: Advisory lock tự bảo vệ mọi hàng có cùng ID

Sai. Advisory lock phối hợp những đoạn code **tự thỏa thuận dùng cùng key**; nó không tự áp row lock lên một account.

## 32. Bài tập thực hành

Các bài sau dùng schema `lock_lab`. Với bài hai session, hãy chú ý giao dịch nào còn mở và kết thúc bằng `ROLLBACK`. Không chạy `LOCK TABLE ... ACCESS EXCLUSIVE` trên production để thử.

### Bài 1. Phân loại khóa

Cho ba tình huống: (a) `ALTER TABLE` cần khóa mạnh; (b) hai UPDATE cùng account; (c) hai backend tranh chấp buffer metadata. Mỗi tình huống liên quan chủ yếu loại khóa nào?

### Bài 2. ACCESS SHARE

Một `SELECT` thường lấy mode khóa bảng nào? Nó xung đột với mode cấp bảng nào trong ma trận?

### Bài 3. ROW EXCLUSIVE

Vì sao A và B có thể cùng UPDATE hai account khác nhau dù mỗi transaction đều giữ table-level `ROW EXCLUSIVE`?

### Bài 4. ROW SHARE khác FOR SHARE

Giải thích sự khác nhau giữa tên khóa `ROW SHARE` và `FOR SHARE`.

### Bài 5. Hai session đọc–ghi

A BEGIN rồi UPDATE balance của account 1 nhưng chưa commit. B chạy SELECT bình thường ở READ COMMITTED; B thấy giá trị mới hay cũ?

### Bài 6. Hai UPDATE cùng hàng

A giữ UPDATE account 1 chưa commit. B UPDATE account 1. Mô tả hiện tượng và cách thả khóa.

### Bài 7. ACCESS EXCLUSIVE

A chạy `BEGIN; LOCK TABLE lock_lab.accounts IN ACCESS EXCLUSIVE MODE;`. B chạy SELECT bảng ấy. Vì sao có thể phải chờ?

### Bài 8. SHARE table lock

Vì sao `LOCK TABLE ... IN SHARE MODE` có thể cho phép SELECT nhưng chặn UPDATE?

### Bài 9. Bốn row lock modes

Liệt kê bốn row-level lock modes. `FOR KEY SHARE` có xung đột với `FOR NO KEY UPDATE` không? Có xung đột `FOR UPDATE` không?

### Bài 10. FK

Vì sao PostgreSQL cần bảo vệ hàng cha khi insert hàng con tham chiếu FK? Điều gì khác nếu transaction khác chỉ sửa một cột note không liên quan khóa?

### Bài 11. pg_locks

Tại sao truy vấn chỉ tìm `locktype='tuple'` không đủ để phát hiện mọi transaction đang chờ row lock?

### Bài 12. Tìm blocker

Viết truy vấn trả `pid`, `wait_event_type`, `wait_event` và `pg_blocking_pids(pid)` cho các backend đang có blocker.

### Bài 13. LWLock

`wait_event_type = 'LWLock'` nên được diễn giải như thế nào? Có cần tìm một hàng cụ thể bị `FOR UPDATE` ngay không?

### Bài 14. BufferPin

Vì sao `BufferPin` không nên đồng nhất với `LWLock` hoặc row-level lock?

### Bài 15. Deadlock

A cập nhật account 1 rồi đợi account 2; B cập nhật account 2 rồi đợi account 1. Đây là chờ thông thường hay deadlock? SQLSTATE thường gặp?

### Bài 16. NOWAIT

`FOR UPDATE NOWAIT` làm gì khi hàng đã bị transaction khác giữ lock xung đột? Nếu câu lệnh lỗi trong transaction thì phải xử lý thế nào?

### Bài 17. SKIP LOCKED

Vì sao có thể dùng `SKIP LOCKED` cho queue worker nhưng không nên dùng để kiểm đếm chính xác tất cả đơn hàng?

### Bài 18. VACUUM

So sánh tác động khóa của `VACUUM` thông thường và `VACUUM FULL`.

### Bài 19. Advisory lock

Viết một ví dụ dùng `pg_try_advisory_xact_lock` và giải thích vì sao nó không tự khóa hàng account cùng ID.

### Bài 20. Serializable predicate lock

`SIReadLock` có mục tiêu giống `FOR UPDATE` để chặn writer ngay lập tức không? Lỗi nào có thể xảy ra khi SSI phát hiện lịch sử không serializable?

### Bài 21. Idle in transaction

Một session có `state='idle in transaction'` trong 20 phút. Nó có thể chặn UPDATE khác không? Viết truy vấn tìm session dạng này.

### Bài 22. Lock timeout

Viết `SET LOCAL lock_timeout = '2s'` trong transaction. Timeout này khác `statement_timeout` như thế nào?

### Bài 23. Phân biệt relation và transactionid waits

Trong `pg_locks`, A và B đều có `RowExclusiveLock` trên bảng với `granted=true` nhưng B vẫn chờ. Hãy nêu một nguyên nhân.

### Bài 24. Thiết kế tránh deadlock

Ứng dụng chuyển tiền giữa hai account với nhiều transaction đồng thời. Đề xuất nguyên tắc thứ tự lấy khóa và cách xử lý khi vẫn có deadlock.

## 33. Gợi ý lời giải

### Bài 1. Ba lớp

(a) Chủ yếu khóa đối tượng/relation; (b) cơ chế khóa hàng/transaction coordination, kèm khóa bảng DML; (c) đồng bộ nội bộ như LWLock/spinlock/buffer control.

### Bài 2. SELECT

`ACCESS SHARE`, xung đột với `ACCESS EXCLUSIVE` trên cùng relation.

### Bài 3. Hai UPDATE khác hàng

`ROW EXCLUSIVE` là **mode cấp bảng** tương thích với chính nó. Nếu hai transaction không sửa cùng hàng và không có xung đột khác, chúng có thể tiếp tục đồng thời.

### Bài 4. Hai tên dễ nhầm

`ROW SHARE` là table-level mode khi dùng `SELECT FOR UPDATE/SHARE`; `FOR SHARE` là row-level mode trên từng hàng được chọn.

### Bài 5. MVCC

Ở READ COMMITTED, B thấy **giá trị đã commit trước đó**, không thấy sửa đổi chưa commit của A. B không bị row update của A chặn trong một SELECT bình thường.

### Bài 6. UPDATE cùng hàng

B chờ A commit/rollback do xung đột row/transaction. Trong lab, A `ROLLBACK` rồi B tiếp tục; cuối cùng B `ROLLBACK` để giữ nguyên dữ liệu.

### Bài 7. ACCESS EXCLUSIVE

`ACCESS EXCLUSIVE` xung đột với `ACCESS SHARE` mà SELECT cần, nên B đợi A kết thúc transaction.

### Bài 8. SHARE

`SHARE` tương thích `ACCESS SHARE` của SELECT nhưng xung đột `ROW EXCLUSIVE` của UPDATE.

### Bài 9. Row-level modes

`FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`. KEY SHARE tương thích NO KEY UPDATE nhưng xung đột UPDATE.

### Bài 10. FK

FK cần bảo đảm hàng cha còn hợp lệ khi hàng con được ghi. Kiểm tra FK có thể dùng mode `FOR KEY SHARE` trên hàng cha; cập nhật note không đổi khóa thường có mode `FOR NO KEY UPDATE` tương thích.

### Bài 11. pg_locks

Row locks không được liệt kê đầy đủ dưới dạng granted tuple entries; một backend chờ hàng do transaction khác sửa có thể chờ `transactionid`.

### Bài 12. Tìm PID blocker

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

### Bài 13. LWLock

Đó là chờ đồng bộ cấu trúc PostgreSQL nội bộ. Cần tìm event cụ thể, pattern tải và tài nguyên; không tự suy có một hàng đang bị `FOR UPDATE`.

### Bài 14. BufferPin

`BufferPin` là trạng thái chờ liên quan buffer pin; PostgreSQL ghi nhận khác `LWLock` và khác khóa tuple nghiệp vụ.

### Bài 15. Deadlock

Vòng A→B→A là deadlock; PostgreSQL thường phát hiện và hủy một transaction với `40P01`.

### Bài 16. NOWAIT

`NOWAIT` báo lỗi nếu không lấy được row lock ngay. Trong transaction có lỗi, rollback hoặc rollback tới savepoint hợp lệ trước khi tiếp tục.

### Bài 17. SKIP LOCKED

Nó có thể bỏ qua hàng đang bị lock, giúp worker khác lấy job còn rảnh. Vì dữ liệu trả ra **thiếu hàng bị khóa**, không thích hợp báo cáo phải đếm đủ mọi đơn.

### Bài 18. VACUUM

`VACUUM` thường liên quan `SHARE UPDATE EXCLUSIVE` và cho phép nhiều hoạt động thông thường tiếp tục; `VACUUM FULL` cần khóa mạnh `ACCESS EXCLUSIVE` và có thể chặn SELECT/DML.

### Bài 19. Advisory try-lock

~~~sql
BEGIN;
SELECT pg_try_advisory_xact_lock(42) AS acquired;
-- Chỉ thực hiện công việc bảo vệ nếu acquired = true.
ROLLBACK;
~~~

Advisory lock hoạt động theo **quy ước ID của ứng dụng**, không tự buộc mọi SQL cập nhật hàng có ID 42 phải lấy cùng lock.

### Bài 20. SSI

`SIReadLock` hỗ trợ theo dõi phụ thuộc đọc–ghi, không phải khóa writer trực tiếp như `FOR UPDATE`; PostgreSQL có thể hủy transaction với `40001` serialization failure.

### Bài 21. Idle session

~~~sql
SELECT
    pid, application_name, state,
    now() - xact_start AS xact_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

Session idle có thể vẫn giữ row/relation locks và chặn transaction khác.

### Bài 22. Timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SELECT * FROM lock_lab.accounts
WHERE account_id = 1 FOR UPDATE;
ROLLBACK;
~~~

`lock_timeout` giới hạn **thời gian chờ lock**, `statement_timeout` giới hạn **thời gian statement**.

### Bài 23. Transactionid wait

Hai `RowExclusiveLock` cấp bảng tương thích. B có thể chờ transaction ID của A vì chúng cùng cập nhật **một hàng**; không phải xung đột ở hai relation locks đã granted.

### Bài 24. Giảm deadlock

Lấy các khóa theo **thứ tự ID nhất quán**, giữ transaction ngắn, kiểm tra số hàng cập nhật, xử lý `40P01` bằng rollback và retry toàn transaction có giới hạn với idempotency phù hợp.

## 34. Bảng tra cứu nhanh

| Mục tiêu | Cú pháp / dấu hiệu |
| --- | --- |
| Chọn một hàng để khóa mạnh | `SELECT ... FOR UPDATE` |
| Khóa hàng không thay đổi khóa chính | `SELECT ... FOR NO KEY UPDATE` |
| Khóa hàng ở chế độ chia sẻ | `SELECT ... FOR SHARE` |
| Bảo vệ khóa tham chiếu | `SELECT ... FOR KEY SHARE` |
| Không chờ khóa hàng | `FOR UPDATE NOWAIT` |
| Bỏ qua hàng đang khóa | `FOR UPDATE SKIP LOCKED` |
| Lấy khóa bảng tường minh | `LOCK TABLE ... IN SHARE MODE` |
| Khóa bảng mạnh nhất | `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE` |
| Tìm các lock cấp bởi manager | `SELECT ... FROM pg_locks` |
| Tìm wait type | `pg_stat_activity.wait_event_type` |
| Tìm event cụ thể | `pg_stat_activity.wait_event` |
| Tìm các PID đang chặn | `pg_blocking_pids(pid)` |
| Tìm tuổi transaction | `now() - pg_stat_activity.xact_start` |
| Giới hạn thời gian chờ lock | `SET LOCAL lock_timeout = '2s'` |
| Giới hạn statement | `statement_timeout` |
| Ngắt idle transaction quá lâu | `idle_in_transaction_session_timeout` |
| Advisory lock theo transaction | `pg_advisory_xact_lock(key)` |
| Advisory try-lock | `pg_try_advisory_xact_lock(key)` |
| Deadlock detected | SQLSTATE `40P01` |
| Serialization failure | SQLSTATE `40001` |
| Internal lightweight wait | `wait_event_type = 'LWLock'` |
| Buffer pin wait | `wait_event_type = 'BufferPin'` |

## 35. Checklist khi gặp truy vấn bị chặn

1. **Xác định PID, query và thời điểm:** dùng `pg_stat_activity`.
2. **Phân loại wait:** `Lock`, `LWLock`, `BufferPin`, `IO` hay loại khác?
3. **Nếu là Lock:** dùng `pg_blocking_pids(pid)` để tìm blocker; tránh tự ghép `pg_locks` như một giả định đơn giản.
4. **Nhìn mode và đối tượng:** relation `ACCESS EXCLUSIVE` hay transactionid row conflict?
5. **Xác định blocker có idle in transaction không:** có transaction lâu chưa commit?
6. **Đọc query/transaction age:** phân biệt migration, API, batch, maintenance, truy vấn trực tuyến.
7. **Xác nhận xung đột cấp bảng hay hàng:** hai `ROW EXCLUSIVE` đã granted không chứng minh không có row contention.
8. **Đánh giá ảnh hưởng tới dữ liệu:** trước khi cancel/terminate, hiểu transaction sẽ bị rollback hay job sẽ retry.
9. **Xử lý nguyên nhân lâu dài:** transaction ngắn, lock ordering, kế hoạch DDL, index phù hợp và timeout có chủ đích.
10. **Nếu là LWLock/BufferPin:** phân tích bottleneck nội bộ, tải hệ thống và event cụ thể; không tùy tiện áp dụng “kill blocker row lock”.

## 36. Tổng kết

Trong PostgreSQL, **khóa đối tượng**, **khóa hàng** và **khóa nội bộ** trả lời ba câu hỏi khác nhau:

- **Khóa đối tượng / relation-level locks:** một transaction có được phép thao tác trên bảng/đối tượng khi transaction khác đang DDL, bảo trì hoặc truy cập không? Chúng có **tám table-level modes** và ma trận xung đột. `ROW EXCLUSIVE` là **mode khóa bảng**, không phải khóa một hàng.
- **Khóa hàng / row-level locks:** hai transaction có thể cùng khóa/sửa **một hàng** hay phải chờ? Chúng có **bốn mode** `FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`, phối hợp với MVCC và trạng thái transaction.
- **Khóa nội bộ:** PostgreSQL làm sao bảo vệ shared buffers và cấu trúc bộ nhớ khi nhiều backend chạy song song? Đây là nhiệm vụ của **LWLocks, spinlocks, buffer pins** cùng các cơ chế khác; không phải thứ ứng dụng điều khiển qua `LOCK TABLE`.

Chìa khóa vận hành là **phân loại đúng loại chờ trước khi tối ưu**. `pg_locks` rất hữu ích với heavyweight locks nhưng không liệt kê đầy đủ mọi row lock; `pg_stat_activity` cho biết trạng thái và kiểu chờ; `pg_blocking_pids()` giúp truy tìm chuỗi blocker khi có lock-manager contention. Một `SELECT` thông thường có thể đọc phiên bản MVCC đã commit trong khi một `UPDATE` khác phải chờ row lock, nhưng `ACCESS EXCLUSIVE` vẫn có thể chặn cả hai.

Khi gặp câu SQL “bị khóa”, hãy hỏi theo thứ tự: **“Đang chờ loại tài nguyên nào? Chờ transaction/hàng nào hay chờ đối tượng? Có phải contention nội bộ không? Ai giữ tài nguyên, và bao lâu?”**. Trả lời đúng những câu hỏi đó giúp sửa **nguyên nhân thực** thay vì chỉ tăng timeout hoặc hủy session thiếu kiểm soát.
