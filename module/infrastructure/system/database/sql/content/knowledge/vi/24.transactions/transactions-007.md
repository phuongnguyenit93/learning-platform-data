# Thiết lập mức cô lập và chế độ chỉ đọc

Một giao dịch SQL (*transaction*) có thể đọc và thay đổi nhiều hàng trong khi các giao dịch khác đang chạy. Nếu hai người cùng xem số dư, tồn kho hoặc doanh thu, kết quả họ nhìn thấy phụ thuộc vào **mức cô lập** (*isolation level*) của giao dịch. Ngoài ra, khi làm báo cáo hoặc kiểm toán, ta thường muốn giao dịch **chỉ đọc** (*read-only*) để tránh vô ý sửa dữ liệu.

Hai lựa chọn này giải quyết **hai câu hỏi khác nhau**:

- **Mức cô lập:** Giao dịch được quan sát những thay đổi nào của các giao dịch khác? Những thao tác đồng thời nào có thể ảnh hưởng đến tính nhất quán?
- **Chế độ chỉ đọc:** Giao dịch có được phép thực hiện các thao tác ghi dữ liệu hay không?

Một giao dịch có thể vừa `REPEATABLE READ` vừa `READ ONLY`, hoặc `SERIALIZABLE` nhưng `READ WRITE`. **Chỉ đọc không tự động đồng nghĩa với cô lập cao**, và **cô lập cao không tự động làm giao dịch chỉ đọc**.

Bài học thuộc chương **Giao dịch SQL** của Database SQL. Phần thực hành sử dụng **PostgreSQL**; những khác biệt với MySQL/InnoDB, SQL Server, Oracle và SQLite được giải thích riêng. Để quan sát hiện tượng đồng thời, cần **hai phiên kết nối thật sự riêng biệt** vào cùng cơ sở dữ liệu thử nghiệm.

## 1. Ôn lại giao dịch và tính chất ACID

Một giao dịch thường được mô tả bằng bốn tính chất **ACID**:

| Thuộc tính | Nội dung |
| --- | --- |
| **Atomicity** | Các thay đổi của một giao dịch thành công cùng nhau hoặc bị hoàn tác cùng nhau |
| **Consistency** | Giao dịch hợp lệ duy trì những ràng buộc dữ liệu mà hệ thống thực sự định nghĩa và thực thi |
| **Isolation** | Các giao dịch chạy đồng thời được quan sát và tương tác theo mức cô lập đã chọn |
| **Durability** | Những thay đổi đã commit được lưu bền vững theo bảo đảm của DBMS và cấu hình |

Ở đây, **Isolation** là trọng tâm. Một cơ sở dữ liệu có thể chấp nhận nhiều giao dịch cùng lúc để tận dụng tài nguyên, nhưng mỗi giao dịch không nhất thiết nhìn thấy cùng một tập dữ liệu.

Một vòng đời PostgreSQL đơn giản:

```sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id = 10;

UPDATE accounts
SET balance = balance - 50
WHERE account_id = 10;

COMMIT;
```

`BEGIN` bắt đầu transaction, `COMMIT` xác nhận các thay đổi. Nếu cần hủy, dùng `ROLLBACK`.

Đoạn trên chỉ là ví dụ cấu trúc; ở phần thực hành ta tạo bảng riêng. Trong nghiệp vụ chuyển tiền thực, phải kiểm tra đủ số dư, điều kiện cập nhật và các ràng buộc khác, không chỉ trừ tiền rồi commit.

### 1.1. Transaction không có nghĩa mọi SELECT đều nhìn một snapshot

Một người có thể nghĩ:

> Tôi đã `BEGIN`, vậy mọi `SELECT` trong giao dịch phải trả kết quả từ cùng một thời điểm.

Điều đó **không đúng ở mọi mức cô lập**. Trong PostgreSQL, ở `READ COMMITTED`, mỗi câu lệnh đọc thông thường có thể lấy một snapshot mới. Hai lần `SELECT` trong cùng transaction có thể nhìn thấy hai trạng thái đã commit khác nhau.

Ngược lại, `REPEATABLE READ` trong PostgreSQL dùng một snapshot nhất quán cho các phép đọc thông thường trong giao dịch, được thiết lập khi giao dịch thực hiện truy vấn hoặc câu lệnh thay đổi dữ liệu đầu tiên, không nhất thiết ngay tại `BEGIN`.

### 1.2. MVCC là cơ chế quan trọng nhưng không phải tên mức cô lập

PostgreSQL dùng *multi-version concurrency control* (**MVCC**): nhiều phiên bản hàng có thể cùng được quản lý để một giao dịch đọc snapshot phù hợp mà không nhất thiết chặn mọi giao dịch ghi.

```text
Dòng thời gian:
T0: stock = 10 đã COMMIT
T1: phiên A đọc stock
T2: phiên B sửa stock = 7 và COMMIT
T3: phiên A đọc stock lần nữa
```

Ở T3, A thấy 10 hay 7 tùy mức cô lập và thời điểm snapshot của nó. MVCC là **cơ chế triển khai**, còn `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` là **hợp đồng quan sát và an toàn đồng thời** với ứng dụng.

## 2. Những bất thường cần hiểu trước khi chọn mức cô lập

### 2.1. Dirty read — đọc dữ liệu chưa commit

Giả sử B đang cập nhật tồn kho từ 10 xuống 7 nhưng **chưa commit**. A đọc thấy 7; sau đó B rollback, khiến giá trị 7 chưa bao giờ trở thành trạng thái đã xác nhận.

```text
Phiên B                     Phiên A
-------------------------   ------------------------
BEGIN
UPDATE stock = 7
                            SELECT stock → 7 (nếu dirty read được phép)
ROLLBACK
                            A đã tin vào dữ liệu bị hủy
```

Đây là **dirty read**. PostgreSQL **không cho phép dirty read**, kể cả khi yêu cầu `READ UNCOMMITTED`; trong PostgreSQL mức đó hoạt động như `READ COMMITTED`.

### 2.2. Non-repeatable read — cùng hàng, hai giá trị khác nhau

```text
A: BEGIN
A: SELECT stock → 10
B: UPDATE stock = 7; COMMIT
A: SELECT stock → 7
A: COMMIT
```

Hai lần đọc **cùng hàng** trong một giao dịch A trả hai giá trị vì thay đổi của B đã commit ở giữa. Đây là tình huống có thể xảy ra ở `READ COMMITTED`.

Nếu ứng dụng lấy giá trị lần đầu để quyết định rồi dùng lại giá trị đó sau nhiều thao tác, cần hiểu rủi ro thay đổi giữa chừng.

### 2.3. Phantom read — tập hàng thỏa điều kiện thay đổi

```text
A: SELECT COUNT(*) FROM orders WHERE status = 'new' → 1
B: INSERT thêm đơn status='new'; COMMIT
A: SELECT COUNT(*) FROM orders WHERE status = 'new' → 2
```

A đọc **cùng một điều kiện tìm kiếm**, nhưng hàng mới xuất hiện sau khi B commit. Đây là *phantom read*.

Phân biệt:

- *Non-repeatable read*: một hàng đã đọc có giá trị thay đổi.
- *Phantom*: tập hàng thỏa một điều kiện lọc thay đổi vì có hàng xuất hiện, biến mất hoặc chuyển vào/ra điều kiện đó.

### 2.4. Lost update — cập nhật làm mất thay đổi khác

Một ví dụ nguy hiểm ở tầng ứng dụng:

```text
A đọc số dư 100
B đọc số dư 100
A tính 100 - 10 = 90 và ghi 90
B tính 100 - 20 = 80 và ghi 80
```

Nếu cả hai thao tác ghi đều được chấp nhận theo cách này, kết quả cuối 80 làm **mất** thay đổi trừ 10 của A. Đây là lỗi *read–modify–write* dùng giá trị cũ.

Không phải mọi câu `UPDATE` đều bị vậy. Câu lệnh nguyên tử kiểu:

```sql
UPDATE accounts
SET balance = balance - 20
WHERE account_id = 10;
```

thường được DBMS xử lý với khóa ghi phù hợp, khác với ứng dụng đọc 100 rồi gửi `UPDATE ... SET balance = 80`. Tuy nhiên, một phép cập nhật nguyên tử trên một hàng **không tự bảo vệ mọi bất biến nhiều hàng**. Có thể cần điều kiện `WHERE`, khóa hàng, kiểm soát phiên bản hoặc cô lập mạnh hơn tùy nghiệp vụ.

### 2.5. Write skew — mỗi giao dịch ghi một hàng khác nhau nhưng cùng phá bất biến

Giả sử quy tắc: “Trong hai bác sĩ trực A và B, **phải luôn còn ít nhất một người trực**.”

Cả hai giao dịch đều đọc thấy **2 người đang trực**. A bỏ trực cho bác sĩ A; B bỏ trực cho bác sĩ B. Vì mỗi bên ghi **một hàng khác nhau**, một số cơ chế snapshot isolation có thể cho cả hai commit, khiến không còn ai trực.

```text
Trước: A = TRUE, B = TRUE

Giao dịch 1 đọc COUNT(on_call) = 2
Giao dịch 2 đọc COUNT(on_call) = 2
Giao dịch 1 đổi A = FALSE
Giao dịch 2 đổi B = FALSE

Sau: A = FALSE, B = FALSE  ← vi phạm quy tắc toàn tập
```

Một `CHECK` trên từng hàng không đủ diễn đạt ràng buộc “ít nhất một hàng có `on_call=TRUE`”. Ở PostgreSQL `REPEATABLE READ`, write skew giữa hai hàng khác nhau có thể xảy ra. `SERIALIZABLE` có khả năng phát hiện chu trình phụ thuộc không thể tuần tự hóa và từ chối một giao dịch để giữ ngữ nghĩa tuần tự.

**Điều quan trọng:** “Cùng snapshot ổn định” không đồng nghĩa “mọi bất biến nghiệp vụ nhiều hàng đều an toàn”.

## 3. Bốn mức cô lập SQL thường được nhắc đến

Các tên mức cô lập chuẩn:

1. `READ UNCOMMITTED`
2. `READ COMMITTED`
3. `REPEATABLE READ`
4. `SERIALIZABLE`

Mức cô lập càng mạnh thường hạn chế thêm những hiện tượng đồng thời, nhưng có thể tăng chi phí khóa, lưu phiên bản, chờ hoặc retry. Không nên mặc định một mức là tối ưu cho mọi truy vấn.

### 3.1. Bảng hiện tượng theo mô hình SQL tiêu chuẩn

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Có thể theo phân loại tiêu chuẩn |
| `SERIALIZABLE` | Không | Không | Không |

Đây là **bảng hiện tượng trong mô hình SQL truyền thống**, không phải lời hứa về toàn bộ hành vi cụ thể của mọi DBMS. Các hệ có MVCC, snapshot isolation và nhiều loại khóa có thể ngăn nhiều hiện tượng hơn nhưng vẫn cho một số bất thường khác như write skew.

### 3.2. PostgreSQL thực tế khác điều gì?

| Mức yêu cầu trong PostgreSQL | Đặc tính cần nhớ |
| --- | --- |
| `READ UNCOMMITTED` | Hoạt động như `READ COMMITTED`, không đọc dữ liệu chưa commit |
| `READ COMMITTED` | Snapshot cho mỗi câu lệnh đọc thông thường; một transaction có thể thấy commit mới ở SELECT tiếp theo |
| `REPEATABLE READ` | Snapshot ổn định trong transaction; PostgreSQL cũng không có phantom read kiểu đọc snapshot thông thường; có thể có write skew |
| `SERIALIZABLE` | Bảo đảm kết quả tương đương một thứ tự thực thi tuần tự của những transaction commit; có thể hủy một giao dịch vì xung đột serialization |

`REPEATABLE READ` của PostgreSQL mạnh hơn yêu cầu tối thiểu ở khía cạnh phantom, nhưng **không thay thế `SERIALIZABLE`** cho các bất biến nhiều hàng.

### 3.3. SERIALIZABLE không có nghĩa mọi transaction phải xếp hàng chạy lần lượt

PostgreSQL sử dụng cơ chế **Serializable Snapshot Isolation (SSI)**. Nhiều transaction vẫn có thể chạy song song. Nếu những phụ thuộc đọc/ghi dẫn tới nguy cơ kết quả không thể sắp thành một lịch tuần tự hợp lệ, một transaction có thể bị hủy với lỗi serialization, thường có SQLSTATE `40001`.

Ứng dụng phải **retry toàn bộ transaction** khi phù hợp. Một hệ thống chỉ đặt `SERIALIZABLE` nhưng không xử lý khả năng thất bại/retry có thể không đạt mục tiêu vận hành mong muốn.

## 4. Chọn chế độ READ ONLY hay READ WRITE

Mức cô lập và chế độ ghi là hai trục độc lập:

| | `READ WRITE` | `READ ONLY` |
| --- | --- | --- |
| `READ COMMITTED` | Giao dịch xử lý đọc/ghi thường gặp | Đọc báo cáo; vẫn có thể thấy commit mới giữa các câu SELECT |
| `REPEATABLE READ` | Đọc snapshot ổn định và có thể ghi theo quy tắc DBMS | Đọc báo cáo nhiều câu SELECT trên snapshot ổn định |
| `SERIALIZABLE` | Giao dịch nghiệp vụ cần tránh bất thường không thể tuần tự hóa | Đọc dữ liệu với yêu cầu ngữ nghĩa serializable, có thể dùng `DEFERRABLE` trong PostgreSQL |

**`READ ONLY` kiểm soát kiểu thao tác được phép trong transaction**, không xác định snapshot cố định. Một transaction `READ COMMITTED, READ ONLY` vẫn có thể đọc hai lần ra hai giá trị nếu có writer khác commit ở giữa.

Ngược lại, `REPEATABLE READ, READ WRITE` có thể ghi dữ liệu, dù các câu đọc sử dụng snapshot ổn định theo cơ chế của PostgreSQL.

## 5. Thiết lập mức cô lập khi bắt đầu transaction PostgreSQL

Cách ngắn nhất là khai báo trên câu `BEGIN`:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT *
FROM some_existing_table;

COMMIT;
```

Trong ví dụ này, `some_existing_table` là bảng minh họa cần có sẵn. Phần thực hành sẽ cung cấp bảng cụ thể.

Các tổ hợp khác:

```sql
-- Giao dịch đọc/ghi, mỗi SELECT thông thường có snapshot mới:
BEGIN TRANSACTION
    ISOLATION LEVEL READ COMMITTED,
    READ WRITE;

-- SQL xử lý nghiệp vụ ở đây.
COMMIT;
```

```sql
-- Giao dịch đọc/ghi theo ngữ nghĩa serializable:
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ WRITE;

-- Các SELECT và DML hợp lệ ở đây.
COMMIT;
```

```sql
-- Giao dịch chỉ đọc cần snapshot serializable an toàn:
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT ...;
COMMIT;
```

Hai khối có dấu `...` là **cấu trúc minh họa**, không chạy nguyên dạng. Chỉ cần thay bằng các câu truy vấn thật.

### 5.1. Dùng SET TRANSACTION ngay sau BEGIN

Có thể tách thành hai lệnh:

```sql
BEGIN;

SET TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT current_setting('transaction_isolation') AS isolation,
       current_setting('transaction_read_only') AS read_only;

COMMIT;
```

Kết quả trong PostgreSQL tương ứng `repeatable read` và `on`.

`SET TRANSACTION` thay đổi **transaction hiện tại**; không tự thay đổi mặc định của những transaction sau.

### 5.2. Thời điểm gọi SET TRANSACTION là quan trọng

Trong PostgreSQL, việc đổi mức cô lập qua `SET TRANSACTION` phải diễn ra **trước câu truy vấn hoặc câu lệnh thay đổi dữ liệu đầu tiên của transaction**. Không nên:

```sql
-- Ví dụ sai quy trình: không chạy như một script hoàn chỉnh.
BEGIN;

SELECT COUNT(*)
FROM demo_tx_inventory_302;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

COMMIT;
```

Sau câu `SELECT`, bạn không thể giả định có thể nâng cấp isolation cho cùng giao dịch. Hãy chọn transaction mode **trước khi đọc hoặc ghi**. Nếu đã bắt đầu một chuỗi thao tác với mức sai, rollback và bắt đầu transaction mới đúng yêu cầu.

### 5.3. Kiểm tra isolation và read-only hiện tại

PostgreSQL:

```sql
SHOW transaction_isolation;
SHOW transaction_read_only;
```

Hoặc:

```sql
SELECT
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('transaction_read_only') AS is_read_only;
```

Lưu ý: kiểm tra ở **bên trong transaction đang quan tâm**. Nếu chạy một câu `SHOW` sau `COMMIT`, bạn đang quan sát giá trị của transaction khác hoặc mặc định của phiên, không phải transaction đã kết thúc.

## 6. Phạm vi cấu hình: transaction, session và database

Có nhiều lớp cấu hình, dễ bị nhầm lẫn.

### 6.1. Chỉ giao dịch hiện tại

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE, READ ONLY;
SELECT ...;
COMMIT;
```

Mode chỉ có hiệu lực với transaction hiện tại.

### 6.2. Mặc định cho các transaction sau trên cùng kết nối

Trong PostgreSQL:

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;
```

Các transaction **sau đó trên cùng session** mặc định dùng `REPEATABLE READ, READ ONLY`, trừ khi được ghi đè bằng mode cụ thể.

Khi cần trở lại thiết lập thông thường:

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL READ COMMITTED,
    READ WRITE;
```

Các lệnh này có phạm vi **session**, không thay đổi cấu hình cho mọi người dùng hay mọi kết nối.

### 6.3. Tham số default_transaction_*

PostgreSQL có các cấu hình như:

```sql
SHOW default_transaction_isolation;
SHOW default_transaction_read_only;
```

Chúng mô tả **mặc định** áp dụng cho transaction mới trong phạm vi cấu hình tương ứng. Không được nhầm:

- `default_transaction_isolation`: mức mặc định.
- `transaction_isolation`: mức đang có hiệu lực.
- `default_transaction_read_only`: mặc định chế độ đọc/ghi.
- `transaction_read_only`: mode transaction hiện tại.

Trong connection pool, việc đặt session mặc định rồi không reset có thể khiến **yêu cầu kế tiếp của người dùng khác trên cùng kết nối** vô tình chạy read-only hoặc isolation cao. Do đó, một luồng báo cáo nên xác định rõ chính sách cấu hình/hoàn trả kết nối khi dùng pool.

### 6.4. Autocommit và giao dịch nhiều câu

Nếu driver hoặc công cụ SQL ở chế độ autocommit, mỗi statement có thể được thực thi trong transaction riêng. Khi đó, hai `SELECT` liên tiếp có thể **không thuộc cùng một giao dịch**, dù session có mức mặc định `REPEATABLE READ`.

Nếu muốn nhiều truy vấn dùng cùng snapshot, phải gom chúng trong **một transaction tường minh** và giữ cùng kết nối.

## 7. Thiết lập dữ liệu để thử với hai phiên PostgreSQL

Để hai kết nối cùng nhìn thấy dữ liệu, dùng **bảng thường trong một database thử nghiệm**, không phải `TEMP TABLE` (bảng tạm PostgreSQL chỉ hiện trong session sở hữu).

Chỉ chạy DDL này ở **database/sandbox dành cho thực hành**, không chạy trực tiếp ở hệ production có tên bảng tương tự.

```sql
CREATE TABLE demo_tx_inventory_302 (
    product_id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

INSERT INTO demo_tx_inventory_302 (product_id, stock)
VALUES (1, 10);

CREATE TABLE demo_tx_orders_302 (
    order_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL
);

INSERT INTO demo_tx_orders_302 (order_id, status)
VALUES (1, 'new');

CREATE TABLE demo_tx_oncall_302 (
    doctor_id INTEGER PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO demo_tx_oncall_302 (doctor_id, on_call)
VALUES (10, TRUE), (20, TRUE);
```

Ba bảng lần lượt phục vụ:

- `demo_tx_inventory_302`: non-repeatable read và snapshot.
- `demo_tx_orders_302`: phantom read.
- `demo_tx_oncall_302`: write skew và serializable.

Hãy dùng **hai cửa sổ psql/SQL client**, gọi là **Phiên A** và **Phiên B**, cùng kết nối vào database chứa các bảng. Trước mỗi kịch bản phải đưa dữ liệu về trạng thái đã nêu; không đặt các câu của A và B liên tiếp trong **một** cửa sổ rồi coi là hai transaction đồng thời.

## 8. Thực hành READ COMMITTED: cùng giao dịch thấy commit mới

PostgreSQL thường dùng `READ COMMITTED` làm mức cô lập mặc định.

Trước khi bắt đầu, chạy ngoài transaction A/B:

```sql
UPDATE demo_tx_inventory_302
SET stock = 10
WHERE product_id = 1;
```

### 8.1. Phiên A — mở transaction và đọc

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL READ COMMITTED,
    READ ONLY;

SELECT stock
FROM demo_tx_inventory_302
WHERE product_id = 1;
-- Nhìn thấy 10.
```

Giữ A **chưa commit**.

### 8.2. Phiên B — cập nhật và commit

```sql
BEGIN;

UPDATE demo_tx_inventory_302
SET stock = 7
WHERE product_id = 1;

COMMIT;
```

### 8.3. Phiên A — đọc lại

```sql
SELECT stock
FROM demo_tx_inventory_302
WHERE product_id = 1;
-- Nhìn thấy 7.

COMMIT;
```

Phiên A đã ở `READ ONLY` nên tự nó không sửa dữ liệu, nhưng vẫn thấy **commit mới của B** ở lần `SELECT` tiếp theo. Đó là ví dụ rõ ràng cho việc:

> **READ ONLY không bảo đảm đọc lặp lại cùng giá trị.**

Trong PostgreSQL `READ COMMITTED`, mỗi câu truy vấn thông thường nhận snapshot phù hợp với các transaction đã commit tại thời điểm câu truy vấn bắt đầu.

### 8.4. Nếu B chưa commit thì sao?

Nếu B cập nhật stock thành 7 nhưng **chưa commit**, A không đọc giá trị 7 của B trong PostgreSQL. A vẫn đọc phiên bản đã commit phù hợp với snapshot câu lệnh. Khi B rollback, A không nhìn thấy giá trị bẩn bị hủy.

## 9. Thực hành REPEATABLE READ: cùng snapshot qua nhiều SELECT

Đưa dữ liệu về 10 trước khi bắt đầu lại:

```sql
UPDATE demo_tx_inventory_302
SET stock = 10
WHERE product_id = 1;
```

### 9.1. Phiên A

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT stock
FROM demo_tx_inventory_302
WHERE product_id = 1;
-- 10; snapshot cho giao dịch được thiết lập.
```

Giữ giao dịch A đang mở.

### 9.2. Phiên B

```sql
BEGIN;

UPDATE demo_tx_inventory_302
SET stock = 7
WHERE product_id = 1;

COMMIT;
```

### 9.3. Phiên A

```sql
SELECT stock
FROM demo_tx_inventory_302
WHERE product_id = 1;
-- Vẫn là 10 theo snapshot của A.

COMMIT;
```

Sau `COMMIT` của A, một transaction mới có thể đọc 7. `REPEATABLE READ` không có nghĩa dữ liệu bị “đóng băng mãi mãi”; nó giữ một snapshot nhất quán **trong thời gian giao dịch đó còn hiệu lực**.

### 9.4. Snapshot bắt đầu khi nào?

Trong PostgreSQL, `BEGIN` không nhất thiết ngay lập tức lấy snapshot dùng cho `REPEATABLE READ`. Snapshot thường được xác lập tại câu truy vấn/câu lệnh thay đổi dữ liệu đầu tiên cần snapshot.

Do đó, nếu A chỉ `BEGIN` rồi để yên; B commit; sau đó A mới `SELECT` lần đầu, A có thể thấy trạng thái B đã commit. Không nên suy luận mốc snapshot từ thời điểm nhập lệnh `BEGIN` mà không xét câu đọc đầu tiên.

## 10. Thực hành phantom read với COUNT theo điều kiện

Đưa bảng đơn về trạng thái chỉ có một hàng:

```sql
DELETE FROM demo_tx_orders_302
WHERE order_id <> 1;

UPDATE demo_tx_orders_302
SET status = 'new'
WHERE order_id = 1;
```

### 10.1. READ COMMITTED

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED, READ ONLY;

SELECT COUNT(*) AS new_orders
FROM demo_tx_orders_302
WHERE status = 'new';
-- 1
```

**Phiên B:**

```sql
INSERT INTO demo_tx_orders_302 (order_id, status)
VALUES (2, 'new');
-- Nếu client autocommit, lệnh này đã commit.
-- Nếu đang trong transaction thủ công, cần COMMIT.
```

**Phiên A:**

```sql
SELECT COUNT(*) AS new_orders
FROM demo_tx_orders_302
WHERE status = 'new';
-- 2 khi B đã commit.

COMMIT;
```

Tập hàng thỏa `status = 'new'` đã thay đổi trong một transaction A: có phantom read.

### 10.2. REPEATABLE READ

Trước thử lại, xóa đơn 2 ngoài các transaction đang mở:

```sql
DELETE FROM demo_tx_orders_302 WHERE order_id = 2;
```

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;

SELECT COUNT(*)
FROM demo_tx_orders_302
WHERE status = 'new';
-- 1
```

**Phiên B:**

```sql
INSERT INTO demo_tx_orders_302 (order_id, status)
VALUES (2, 'new');
-- COMMIT nếu không dùng autocommit.
```

**Phiên A:**

```sql
SELECT COUNT(*)
FROM demo_tx_orders_302
WHERE status = 'new';
-- Vẫn 1 theo snapshot.

COMMIT;
```

Trong PostgreSQL, `REPEATABLE READ` ngăn phantom cho các phép đọc snapshot thông thường, dù bảng phân loại mức cô lập tối thiểu trong một số tài liệu SQL cho phép phantom ở mức này.

## 11. Thực hành READ UNCOMMITTED trên PostgreSQL

PostgreSQL chấp nhận tên mức `READ UNCOMMITTED`, nhưng về hành vi đọc nó tương đương `READ COMMITTED`.

Chuẩn bị stock = 10 ngoài transaction, rồi:

**Phiên B:**

```sql
BEGIN;

UPDATE demo_tx_inventory_302
SET stock = 4
WHERE product_id = 1;

-- Chưa COMMIT.
```

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED, READ ONLY;

SHOW transaction_isolation;

SELECT stock
FROM demo_tx_inventory_302
WHERE product_id = 1;
-- Không nhìn thấy 4 chưa commit; thấy bản đã commit phù hợp.
COMMIT;
```

**Phiên B:**

```sql
ROLLBACK;
```

Đừng nhầm từ khóa `READ UNCOMMITTED` được chấp nhận cú pháp với bảo đảm sẽ quan sát dirty read. Phải đọc tài liệu của DBMS cụ thể, không suy luận từ tên mức cô lập.

## 12. SERIALIZABLE bảo vệ bất biến giữa nhiều hàng

Xét hai bác sĩ có thể trực:

```sql
SELECT * FROM demo_tx_oncall_302 ORDER BY doctor_id;
```

Ban đầu cả `doctor_id=10` và `doctor_id=20` đều `on_call=TRUE`. Yêu cầu: **không bao giờ để cả hai cùng nghỉ trực**.

Khôi phục dữ liệu trước thử nghiệm:

```sql
UPDATE demo_tx_oncall_302
SET on_call = TRUE;
```

### 12.1. Write skew có thể xảy ra dưới REPEATABLE READ

**Phiên A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ, READ WRITE;

SELECT COUNT(*) AS doctors_on_call
FROM demo_tx_oncall_302
WHERE on_call;
-- 2
```

**Phiên B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ, READ WRITE;

SELECT COUNT(*) AS doctors_on_call
FROM demo_tx_oncall_302
WHERE on_call;
-- 2
```

**Phiên A:**

```sql
UPDATE demo_tx_oncall_302
SET on_call = FALSE
WHERE doctor_id = 10;

COMMIT;
```

**Phiên B:**

```sql
UPDATE demo_tx_oncall_302
SET on_call = FALSE
WHERE doctor_id = 20;

COMMIT;
```

Vì mỗi giao dịch ghi một hàng khác nhau, PostgreSQL `REPEATABLE READ` có thể cho cả hai commit. Kết quả còn **0 người trực**, vi phạm bất biến cấp tập hợp.

### 12.2. Thử lại bằng SERIALIZABLE

Đặt cả hai về TRUE ngoài transaction:

```sql
UPDATE demo_tx_oncall_302
SET on_call = TRUE;
```

Lặp lại thứ tự đọc và cập nhật như trên, nhưng dùng ở **cả hai phiên**:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE, READ WRITE;
```

Với lịch đồng thời hai bên đều đã đọc 2 người trực rồi ghi hai hàng khác nhau, PostgreSQL sẽ phát hiện xung đột serialization không thể chấp nhận; **ít nhất một transaction không thể commit thành công** theo lịch đó và có thể nhận SQLSTATE `40001`.

Không giả định lỗi nhất định xuất hiện ở cùng một statement trên mọi phiên/lần chạy: tùy lịch, lỗi có thể xuất hiện khi UPDATE hoặc COMMIT.

### 12.3. Retry phải đọc lại, không chỉ lặp UPDATE

Sau lỗi serialization:

1. `ROLLBACK` transaction thất bại nếu cần.
2. Bắt đầu **transaction mới** ở `SERIALIZABLE`.
3. **Đọc lại** số bác sĩ đang trực.
4. Chỉ cho một người nghỉ nếu còn ít nhất hai người.
5. Commit hoặc retry có giới hạn nếu gặp lỗi serialization nữa.

Nếu một giao dịch đã cho bác sĩ 10 nghỉ, giao dịch còn lại khi retry sẽ thấy chỉ còn bác sĩ 20 và **không được cho người cuối nghỉ**.

`SERIALIZABLE` bảo đảm các giao dịch được commit tương đương với một thứ tự tuần tự, nhưng ứng dụng vẫn phải lập trình **quy tắc nghiệp vụ** trong mỗi transaction. Isolation không tự sinh ra điều kiện “còn ít nhất một bác sĩ”.

## 13. Cú pháp và phạm vi chế độ READ ONLY trong PostgreSQL

Chế độ chỉ đọc có thể được chỉ định:

```sql
BEGIN TRANSACTION READ ONLY;

SELECT product_id, stock
FROM demo_tx_inventory_302;

COMMIT;
```

Hoặc kết hợp mức cô lập:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT COUNT(*) FROM demo_tx_orders_302;
SELECT SUM(stock) FROM demo_tx_inventory_302;

COMMIT;
```

Khi transaction chỉ đọc trong PostgreSQL, các thao tác sửa bảng **thông thường không phải bảng tạm** như `INSERT`, `UPDATE`, `DELETE`, `MERGE` bị chặn; nhiều lệnh DDL như `CREATE`, `ALTER`, `DROP` cũng bị chặn.

### 13.1. Ví dụ UPDATE bị từ chối

```sql
-- Dùng riêng để xem lỗi, đừng chạy nối với các câu demo khác.
BEGIN READ ONLY;

UPDATE demo_tx_inventory_302
SET stock = 999
WHERE product_id = 1;
-- PostgreSQL báo lỗi: không được thực thi UPDATE trong read-only transaction.

ROLLBACK;
```

Sau lỗi SQL trong một transaction PostgreSQL, giao dịch có thể ở trạng thái bị đánh dấu lỗi và cần `ROLLBACK`. Không tiếp tục gửi truy vấn khác rồi nghĩ transaction còn bình thường.

### 13.2. READ ONLY không phải ranh giới phân quyền

Chế độ transaction chỉ đọc **không thay thế**:

- `GRANT SELECT` và `REVOKE` theo vai trò.
- Phân quyền trên schema và các bảng.
- Row-level security (RLS) khi cần hạn chế hàng được xem.
- Tách tài khoản báo cáo và tài khoản ghi.
- Kiểm soát các hàm có tác dụng phụ hoặc thao tác qua hệ thống ngoài.

Trong PostgreSQL, một số thao tác với **bảng tạm đã có sẵn** có thể được cho phép dù transaction ở chế độ `READ ONLY`; đây không phải cam kết tuyệt đối rằng “không byte dữ liệu nào được ghi vào đĩa”. Một `SELECT` gọi hàm hoặc dịch vụ ngoài cũng cần được đánh giá riêng về side effect và quyền.

Nếu mục tiêu là ngăn người dùng báo cáo thay đổi dữ liệu production, cần **tài khoản chỉ có quyền đọc** và chính sách truy cập, không chỉ `BEGIN READ ONLY`.

### 13.3. SELECT ... FOR UPDATE có hợp với READ ONLY không?

`SELECT ... FOR UPDATE` yêu cầu khóa các hàng với ý định có thể cập nhật. PostgreSQL không cho dùng kiểu khóa hàng này trong transaction `READ ONLY`.

Nếu một ứng dụng cần khóa hàng để thực hiện giao dịch ghi, hãy dùng transaction `READ WRITE` với isolation và quyền thích hợp; đừng dùng `READ ONLY` rồi ngầm mong khóa ghi vẫn hoạt động.

### 13.4. READ ONLY vẫn có thể chiếm tài nguyên và khóa

Một transaction chỉ đọc dài có thể:

- Giữ snapshot cũ trong thời gian dài, ảnh hưởng việc dọn các phiên bản hàng cũ.
- Giữ một số khóa đọc quan hệ/metadata, có thể tương tác với DDL cần khóa mạnh.
- Tiêu thụ CPU, bộ nhớ, I/O, temp work files khi chạy truy vấn lớn.
- Làm các thống kê báo cáo chậm hoặc gây tải lớn cho hệ thống.

**READ ONLY ngăn nhiều thao tác sửa dữ liệu; nó không bảo đảm chi phí hoặc tác động vận hành bằng 0.**

## 14. SERIALIZABLE READ ONLY DEFERRABLE: snapshot an toàn cho báo cáo

PostgreSQL hỗ trợ một tổ hợp đặc biệt:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT COUNT(*) AS orders_count
FROM demo_tx_orders_302;

SELECT SUM(stock) AS stock_total
FROM demo_tx_inventory_302;

COMMIT;
```

### 14.1. DEFERRABLE nghĩa là gì trong trường hợp này?

Với một transaction **`SERIALIZABLE READ ONLY DEFERRABLE`**, PostgreSQL có thể **chờ ở lần lấy snapshot đầu tiên** cho đến khi có một snapshot được coi là an toàn theo cơ chế SSI.

Đổi lại, khi đã có snapshot an toàn và bắt đầu chạy, transaction báo cáo chỉ đọc có thể tránh chi phí theo dõi xung đột serializable thông thường và không phải bị hủy do lỗi serialization liên quan đến snapshot của nó theo bảo đảm của chế độ này.

Đây là sự đánh đổi:

| Loại báo cáo | Lợi ích | Điểm cần lưu ý |
| --- | --- | --- |
| `READ COMMITTED READ ONLY` | Dễ dùng, quan sát commit mới ở mỗi statement | Nhiều SELECT có thể không cùng thời điểm dữ liệu |
| `REPEATABLE READ READ ONLY` | Nhiều SELECT đọc trên snapshot ổn định | Không bảo đảm tương đương lịch tuần tự của các giao dịch đọc–ghi trong mọi tình huống |
| `SERIALIZABLE READ ONLY` | Yêu cầu ngữ nghĩa serializable | Có thể phát sinh xung đột và cần xử lý retry |
| `SERIALIZABLE READ ONLY DEFERRABLE` | Chờ snapshot an toàn rồi chạy báo cáo ổn định | Có thể **trễ lúc bắt đầu** khi có transaction đồng thời |

Chế độ `DEFERRABLE` **chỉ có tác dụng thực tế trong PostgreSQL khi giao dịch vừa `SERIALIZABLE` vừa `READ ONLY`**. Viết `DEFERRABLE` bên cạnh mức khác hoặc `READ WRITE` không khiến DBMS tự hoãn các câu lệnh tùy ý.

### 14.2. Không phải chỉ cần DEFERRABLE là truy vấn luôn nhanh

Nếu báo cáo tự thực hiện một `JOIN` cực lớn, sort hàng triệu hàng hoặc quét dữ liệu không có index phù hợp, nó vẫn tốn CPU, RAM và I/O. `DEFERRABLE` nói về **cách nhận snapshot serializable an toàn**, không phải một bộ tăng tốc SQL.

Ngoài ra, thời gian chờ snapshot có thể khiến tổng thời gian phản hồi lớn hơn. Với dashboard cần phản hồi tức thì, người thiết kế phải cân nhắc thời gian chờ và mức nhất quán thật sự cần thiết.

## 15. Read-only phù hợp với dạng báo cáo nào?

### 15.1. Một câu SELECT đơn giản

```sql
SELECT COUNT(*) AS paid_orders
FROM orders
WHERE status = 'paid';
```

Trong PostgreSQL `READ COMMITTED`, một câu lệnh SELECT thông thường chạy trên một snapshot nhất quán của chính câu lệnh đó. Nếu chỉ có một truy vấn, chi phí mở transaction read-only lặp nhiều câu có thể không cần thiết.

Tuy nhiên, ý nghĩa “nhất quán” vẫn cần làm rõ: khi dữ liệu được cập nhật từ nhiều hệ bên ngoài không đồng bộ, snapshot database không tự bảo đảm các hệ nguồn ngoài đang ở cùng thời điểm kinh doanh.

### 15.2. Báo cáo nhiều SELECT phải đối chiếu lẫn nhau

Giả sử một API chạy ba câu:

```sql
SELECT COUNT(*) FROM orders WHERE status = 'paid';

SELECT SUM(total_amount) FROM orders WHERE status = 'paid';

SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE status = 'paid';
```

Nếu các câu chạy dưới những snapshot khác nhau, có thể một đơn mới xuất hiện ở câu số 2 nhưng chưa được tính trong câu số 1. Báo cáo có thể tự mâu thuẫn dù từng câu đều đúng ở thời điểm riêng.

Nếu nghiệp vụ yêu cầu **ba chỉ số cùng thời điểm nhìn dữ liệu**, dùng một transaction `REPEATABLE READ READ ONLY` trong PostgreSQL:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT COUNT(*) FROM orders WHERE status = 'paid';
SELECT SUM(total_amount) FROM orders WHERE status = 'paid';
SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE status = 'paid';

COMMIT;
```

Đây là ví dụ cấu trúc với bảng ứng dụng `orders`, không thuộc ba bảng demo đã tạo. Cần kiểm tra tên và quyền bảng trên database thật.

### 15.3. Có thể tính nhiều chỉ số trong một câu SELECT

Nếu các chỉ số cùng cấp dữ liệu và không cần round trip riêng, dùng **một câu tổng hợp**:

```sql
SELECT
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_revenue,
    COUNT(DISTINCT customer_id) AS paid_customers
FROM orders
WHERE status = 'paid';
```

Một câu có thể dễ duy trì tính nhất quán và giảm số round trip. Dù vậy, việc chọn một hay nhiều câu còn phụ thuộc mô hình truy vấn, hiệu năng và ứng dụng.

### 15.4. Báo cáo phân trang

Một API thường chạy `COUNT(*)` để biết tổng bản ghi, sau đó `SELECT ... LIMIT ... OFFSET ...` để lấy một trang. Ở `READ COMMITTED`, dữ liệu có thể thay đổi giữa hai câu: tổng số dòng không còn khớp với trang vừa đọc.

Nếu cần snapshot chung trong một request, dùng `REPEATABLE READ READ ONLY`. Với người dùng chuyển qua nhiều trang trong **nhiều request HTTP riêng biệt**, giữ một transaction mở suốt thời gian duyệt nhiều phút thường không phù hợp. Cần chiến lược khác như keyset pagination, snapshot định danh, dữ liệu báo cáo đã materialize hoặc quy tắc chấp nhận sự thay đổi.

**Isolation một transaction không tự kéo dài tính nhất quán qua nhiều kết nối hoặc request.**

## 16. Chọn mức cô lập theo nghiệp vụ

Không có công thức “mọi transaction đều phải SERIALIZABLE”.

| Bối cảnh | Điểm xuất phát nên cân nhắc | Điều kiện bổ sung |
| --- | --- | --- |
| Một truy vấn đọc đơn giản | `READ COMMITTED` | Quyền đọc và index phù hợp |
| Báo cáo nhiều SELECT cần cùng snapshot | `REPEATABLE READ READ ONLY` trong PostgreSQL | Transaction ngắn, không giữ idle |
| Báo cáo chỉ đọc cần serializable | `SERIALIZABLE READ ONLY` | Xử lý retry nếu cần |
| Báo cáo serializable dài, có thể chờ lúc đầu | `SERIALIZABLE READ ONLY DEFERRABLE` | Cho phép độ trễ lấy snapshot |
| Chỉnh sửa một hàng theo điều kiện | `READ COMMITTED` có thể đủ | UPDATE nguyên tử với predicate, version/lock khi cần |
| Ràng buộc nghiệp vụ trên nhiều hàng | `SERIALIZABLE` hoặc cơ chế khóa/ràng buộc riêng | Retry toàn transaction, thiết kế invariant |
| Giao dịch rất ngắn, độ trễ thấp | Mức thấp đủ theo nhu cầu | Không tự hy sinh tính đúng đắn |
| Bảo vệ production khỏi tài khoản báo cáo | Tài khoản chỉ có `SELECT` / RLS | `READ ONLY` là lớp bổ sung, không thay quyền |

Một mức cô lập thấp không phải lỗi nếu bài toán **chấp nhận** các hiện tượng tương ứng hoặc có cơ chế bảo vệ khác. Ngược lại, đặt mức cao chỉ để “an toàn hơn” mà không hiểu chi phí có thể làm tăng lỗi retry hoặc thời gian chờ.

### 16.1. Khi mức cô lập không thay thế ràng buộc

Ví dụ số lượng tồn kho không được âm:

```sql
UPDATE inventory
SET stock = stock - 1
WHERE product_id = 1
  AND stock >= 1;
```

Sau đó kiểm tra số hàng được cập nhật. Đây là mẫu **kiểm tra điều kiện và cập nhật nguyên tử trên một hàng** có thể giúp tránh bán vượt tồn trong nhiều thiết kế, kể cả không nâng toàn bộ giao dịch lên serializable.

Nếu doanh nghiệp có quy tắc nhiều hàng, nhiều bảng hoặc nhiều bước phân bổ, cần phân tích thêm. `CHECK (stock >= 0)` ngăn tồn âm nhưng không thay thế việc giải thích lý do giao dịch không cập nhật được hàng nào.

### 16.2. Chỉ đọc không đảm bảo có dữ liệu mới nhất

Một transaction `REPEATABLE READ READ ONLY` có thể giữ một snapshot cũ trong suốt thời gian chạy. Điều này **tốt cho tính nhất quán**, nhưng **không tốt** nếu ứng dụng cần quan sát ngay commit mới ở mỗi câu lệnh.

Cần phân biệt:

- **Consistency:** các chỉ số có thuộc cùng snapshot không?
- **Freshness:** snapshot có mới tới thời điểm mong muốn không?
- **Latency:** hệ thống trả lời nhanh đến mức nào?

Ba mục tiêu không hoàn toàn đồng nhất.

## 17. Quản lý transaction chỉ đọc trên PostgreSQL

### 17.1. Không để transaction idle quá lâu

Ví dụ quy trình không nên làm:

```text
BEGIN REPEATABLE READ READ ONLY
SELECT báo cáo
Để kết nối mở, chờ người dùng thao tác giao diện 15 phút
SELECT báo cáo khác
COMMIT
```

Một transaction mở quá lâu có thể giữ snapshot cũ, làm chậm việc thu hồi phiên bản hàng chết và tương tác với DDL/lock.

Nên mở transaction **khi bắt đầu khối công việc nhất quán**, thực hiện các truy vấn cần thiết, rồi `COMMIT` hoặc `ROLLBACK` sớm nhất hợp lý.

### 17.2. SET LOCAL cho giới hạn tài nguyên

Trong PostgreSQL, có thể thiết lập một số giới hạn chỉ cho transaction hiện tại:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

SELECT COUNT(*)
FROM demo_tx_orders_302;

COMMIT;
```

`SET LOCAL` có hiệu lực trong transaction và được hoàn nguyên khi transaction kết thúc. Giới hạn ví dụ chỉ nhằm minh họa cú pháp; ngưỡng thực phải được chọn theo workload.

- `statement_timeout` giới hạn thời gian thực thi statement.
- `lock_timeout` giới hạn thời gian chờ lấy khóa khi có chờ.
- `idle_in_transaction_session_timeout` là cấu hình liên quan đến những phiên **đang idle nhưng còn transaction mở**.

Timeout không thay thế index, plan tốt, phạm vi dữ liệu rõ và transaction ngắn.

### 17.3. Sau lỗi nên ROLLBACK

Trong PostgreSQL, nếu một câu SQL lỗi bên trong transaction (ví dụ vi phạm read-only), những statement tiếp theo có thể bị từ chối vì transaction đã ở trạng thái aborted:

```text
BEGIN
UPDATE ...   → ERROR
SELECT ...   → ERROR: current transaction is aborted
ROLLBACK     → trở về trạng thái có thể tiếp tục
```

Đừng tiếp tục dùng một transaction đã lỗi để tạo ra báo cáo rồi tin rằng mọi câu lệnh đều chạy đúng.

### 17.4. Read-only có thể chạy trên replica không?

Một read replica hoặc standby có thể phục vụ truy vấn đọc, nhưng **replica có thể chậm so với primary** vì độ trễ sao chép.

`READ ONLY` là mode của transaction hoặc khả năng của kết nối; nó **không tự bảo đảm dữ liệu mới nhất**, cũng không có nghĩa backend đang chạy trên replica.

Nếu báo cáo yêu cầu “đã thấy tất cả những commit trước một mốc nhất định”, cần kiểm tra khả năng và độ trễ replication. Một transaction chỉ đọc ở replica không thể bù dữ liệu chưa được sao chép tới nơi ấy bằng cách nâng isolation.

## 18. Java JDBC: thiết lập isolation và read-only qua Connection

Khi ứng dụng Java dùng JDBC, các thao tác liên quan gồm:

- `Connection.setTransactionIsolation(...)`
- `Connection.setReadOnly(true)`
- `Connection.setAutoCommit(false)`
- `commit()` hoặc `rollback()`

### 18.1. Ví dụ đọc báo cáo bằng cùng một transaction

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class ReportRepository {
    private final DataSource dataSource;

    public ReportRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long readCountAndInspectStock() throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            // Thiết lập trước khi bắt đầu thực hiện câu SQL.
            conn.setReadOnly(true);
            conn.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            conn.setAutoCommit(false);

            try {
                long count;
                try (PreparedStatement ps = conn.prepareStatement(
                        "SELECT COUNT(*) FROM demo_tx_orders_302");
                     ResultSet rs = ps.executeQuery()) {
                    rs.next();
                    count = rs.getLong(1);
                }

                try (PreparedStatement ps = conn.prepareStatement(
                        "SELECT stock FROM demo_tx_inventory_302 " +
                        "WHERE product_id = ?");
                ) {
                    ps.setInt(1, 1);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            int stock = rs.getInt(1);
                            System.out.println("Observed stock: " + stock);
                        }
                    }
                }

                conn.commit();
                return count;
            } catch (SQLException e) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    e.addSuppressed(rollbackError);
                }
                throw e;
            }
        }
    }
}
```

Ví dụ cho thấy thứ tự:

1. Lấy một `Connection`.
2. Chọn read-only và isolation **trước khi phát sinh truy vấn/transaction cần dùng**.
3. Tắt autocommit để các câu SQL có thể thuộc **một transaction**.
4. Thực hiện truy vấn trên **cùng kết nối**.
5. Commit khi xong hoặc rollback khi có lỗi.
6. Đóng/hoàn trả connection.

Trong JDBC, `setReadOnly(true)` là **yêu cầu/hint theo API JDBC và hành vi phụ thuộc driver/database**; không được mặc định nó luôn được server thực thi thành một mode ngăn mọi DML. Với PostgreSQL, nên xác minh cấu hình kết nối và mode thực tế bằng truy vấn `SHOW transaction_read_only` nếu việc chặn ghi là yêu cầu quan trọng.

### 18.2. Không đổi isolation giữa chừng

Một số driver có thể thay đổi transaction hiện tại, commit ngầm hoặc từ chối việc gọi `setTransactionIsolation` khi transaction đã hoạt động. Đừng đọc dữ liệu trước rồi mới đổi mức cô lập.

Thứ tự an toàn về ý định là: **cấu hình connection → bắt đầu công việc transaction → truy vấn → commit/rollback**. Hành vi chi tiết phải theo driver và framework đang dùng.

### 18.3. Connection pool phải khôi phục trạng thái

Trong pool, `close()` thường **trả kết nối về pool**, không đóng TCP connection thật. Nếu một yêu cầu đổi:

```java
conn.setReadOnly(true);
conn.setTransactionIsolation(
    Connection.TRANSACTION_SERIALIZABLE
);
```

mà pool/framework không reset, yêu cầu tiếp theo có thể vô tình thừa hưởng `READ ONLY` hoặc `SERIALIZABLE`.

Nên dùng cấu hình transaction ở lớp framework hoặc bảo đảm pool **reset/isolate**: autocommit, read-only, isolation và các session settings khi trả connection. Không giả định việc `close()` tự động reset mọi biến session trong mọi implementation.

### 18.4. Spring transaction là một lớp cấu hình khác

Trong ứng dụng dùng Spring, annotation như:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.REPEATABLE_READ
)
public ReportDto loadReport() {
    // Các câu truy vấn tham gia cùng transaction nếu được cấu hình đúng.
}
```

là cách truyền **ý định transaction** qua framework. Mức độ áp dụng thực tế phụ thuộc transaction manager, driver, cách gọi method (proxy/self-invocation), cấu hình pool và DBMS.

Đừng tự kết luận `readOnly=true` luôn ngăn mọi `UPDATE` nếu chưa xác minh đường đi từ framework xuống database; trên một số hệ nó chỉ là tối ưu/hint.

### 18.5. Retry lỗi serialization trong ứng dụng

PostgreSQL thường báo SQLSTATE `40001` khi transaction không thể serialize. Với JDBC, có thể kiểm tra:

```java
boolean isSerializationFailure(SQLException ex) {
    return "40001".equals(ex.getSQLState());
}
```

Nếu gặp lỗi này, ứng dụng có thể bắt đầu **transaction mới**, đọc lại dữ liệu và chạy lại **toàn bộ thao tác nghiệp vụ** với số lần thử hữu hạn và backoff phù hợp.

Không retry chỉ câu `COMMIT` hoặc câu `UPDATE` ở cuối với dữ liệu đã đọc từ transaction thất bại: các quyết định dựa trên snapshot cũ phải được thực hiện lại.

Trong PostgreSQL, deadlock thường có SQLSTATE `40P01` và có thể cần retry theo chính sách riêng.

## 19. So sánh cú pháp giữa các hệ quản trị

### 19.1. PostgreSQL

Mặc định thường là `READ COMMITTED`. `READ UNCOMMITTED` hoạt động như `READ COMMITTED`; `REPEATABLE READ` dùng snapshot ổn định; `SERIALIZABLE` dùng SSI.

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT * FROM demo_tx_inventory_302;

COMMIT;
```

Ngoài cách đặt trực tiếp trên `BEGIN`, có `SET TRANSACTION` và `SET SESSION CHARACTERISTICS AS TRANSACTION`.

### 19.2. MySQL / InnoDB

InnoDB thường mặc định `REPEATABLE READ` trong các cấu hình phổ biến.

Đặt mức cô lập cho transaction **kế tiếp** theo cú pháp MySQL:

```sql
-- MySQL:
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION READ ONLY;

SELECT *
FROM products;

COMMIT;
```

Có thể đặt session default:

```sql
-- MySQL:
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Lưu ý: trong MySQL, `SET TRANSACTION ISOLATION LEVEL ...` không có `SESSION` thường đặt đặc tính cho **transaction kế tiếp**, thay vì được sử dụng giống hoàn toàn `SET TRANSACTION` bên trong một transaction PostgreSQL.

InnoDB `REPEATABLE READ` có **consistent reads** và **locking reads** với đặc điểm khác nhau; `SELECT ... FOR UPDATE` có thể quan sát/khóa hàng theo quy tắc khác với một `SELECT` snapshot thông thường. Không chuyển nguyên suy luận từ PostgreSQL sang MySQL khi dùng locking reads hoặc cập nhật đồng thời.

### 19.3. SQL Server

SQL Server hỗ trợ:

```sql
-- SQL Server:
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

BEGIN TRANSACTION;

SELECT * FROM dbo.products;

COMMIT TRANSACTION;

SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Mặc định thường là `READ COMMITTED`, nhưng cơ chế đọc có thể dựa trên **locking** hoặc **row versioning** nếu `READ_COMMITTED_SNAPSHOT` được bật. SQL Server còn có `SNAPSHOT` isolation, cần cấu hình database hỗ trợ phù hợp.

**Không có một cú pháp `SET TRANSACTION READ ONLY` tương đương trực tiếp cho transaction SQL Server phổ biến như PostgreSQL/Oracle.** Để bảo vệ truy vấn đọc, nên dùng vai trò chỉ có quyền `SELECT`, database/replica chỉ đọc khi thích hợp và quy tắc trong ứng dụng.

Không nhầm `READ UNCOMMITTED` hoặc `WITH (NOLOCK)` là “chỉ đọc an toàn”; chúng có thể cho phép đọc dữ liệu chưa commit và các bất thường khác.

### 19.4. Oracle Database

Oracle hỗ trợ transaction chỉ đọc với snapshot nhất quán:

```sql
-- Oracle:
SET TRANSACTION READ ONLY;

SELECT * FROM products;
SELECT * FROM categories;

COMMIT;
```

Oracle thường mặc định `READ COMMITTED`; cũng hỗ trợ `SERIALIZABLE`. Nó không cung cấp bốn mức giống hệt PostgreSQL cho mọi transaction. `SET TRANSACTION` thường phải thực hiện ngay từ đầu transaction trước các câu SQL cần quản lý.

Ví dụ mức serializable trong Oracle:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

Cơ chế Oracle có thể báo lỗi khi một transaction không thể được thực thi theo ngữ nghĩa serializable dự kiến; ứng dụng cần phương án xử lý/retry theo hệ quản trị.

### 19.5. SQLite

SQLite có mô hình transaction và locking khác. Ví dụ:

```sql
-- SQLite:
PRAGMA query_only = ON;

BEGIN;
SELECT * FROM products;
COMMIT;

PRAGMA query_only = OFF;
```

`PRAGMA query_only` là **thiết lập kết nối** hạn chế những thay đổi database nhất định, không phải một mức transaction isolation theo cú pháp PostgreSQL. Để kết nối chỉ đọc thật sự, SQLite còn có chế độ mở database kiểu `mode=ro` phù hợp.

SQLite mặc định cung cấp sự cô lập mạnh cho các kết nối độc lập; `PRAGMA read_uncommitted` chỉ có tác dụng đọc bẩn trong những trường hợp shared-cache cụ thể. Trong WAL mode, đọc snapshot và nâng cấp transaction đang đọc thành transaction ghi có những quy tắc riêng.

`BEGIN DEFERRED`, `BEGIN IMMEDIATE`, `BEGIN EXCLUSIVE` điều khiển thời điểm/kiểu khóa transaction theo SQLite; đừng coi chúng là các alias của `READ COMMITTED` hay `SERIALIZABLE`.

### 19.6. Bảng đối chiếu

| DBMS | Chọn isolation | Chế độ read-only transaction | Điểm đặc biệt |
| --- | --- | --- | --- |
| PostgreSQL | `BEGIN ISOLATION LEVEL ...`, `SET TRANSACTION` | `READ ONLY` trong `BEGIN`/`SET TRANSACTION` | `READ UNCOMMITTED` ≈ `READ COMMITTED`; `SERIALIZABLE READ ONLY DEFERRABLE` |
| MySQL/InnoDB | `SET TRANSACTION ISOLATION LEVEL ...` | `START TRANSACTION READ ONLY` | Snapshot reads và locking reads khác nhau |
| SQL Server | `SET TRANSACTION ISOLATION LEVEL ...` | Thường qua quyền/đích chỉ đọc thay vì mode tương đương | READ_COMMITTED_SNAPSHOT và SNAPSHOT có cấu hình riêng |
| Oracle | `SET TRANSACTION ISOLATION LEVEL ...` | `SET TRANSACTION READ ONLY` | Read consistency theo ngữ nghĩa Oracle |
| SQLite | Cơ chế BEGIN/locking riêng | `PRAGMA query_only` hoặc kết nối read-only | Không phải cùng hệ bốn mức isolation như SQL server truyền thống |

**Hãy xác minh theo phiên bản DBMS, driver và cấu hình cụ thể**: cùng tên mức cô lập không nhất thiết đồng nghĩa mọi hiện tượng đồng thời đều giống nhau.

## 20. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Coi `READ ONLY` là một mức cô lập | Nó là transaction access mode | Chọn riêng isolation và READ ONLY/WRITE |
| Coi `READ ONLY` là snapshot bất biến | `READ COMMITTED READ ONLY` vẫn có thể thấy commit mới | Dùng REPEATABLE READ nếu cần snapshot chung trong PostgreSQL |
| Đặt `SET TRANSACTION` sau câu SELECT | Mode có thể không còn được phép đổi cho transaction hiện tại | Thiết lập trước truy vấn đầu tiên |
| Dùng hai kết nối khác nhau cho hai phần báo cáo | Không thể mặc nhiên chia sẻ cùng snapshot | Dùng cùng transaction/kết nối khi cần |
| Dùng autocommit cho nhiều SELECT rồi nói cùng transaction | Mỗi câu có thể ở transaction riêng | Tắt autocommit và quản lý BEGIN/COMMIT đúng |
| Coi `REPEATABLE READ` là serializable tuyệt đối | PostgreSQL còn có thể xảy ra write skew | SERIALIZABLE hoặc khóa/ràng buộc nghiệp vụ |
| Coi PostgreSQL `READ UNCOMMITTED` là dirty read | PostgreSQL thực thi như READ COMMITTED | Hiểu hành vi cụ thể của engine |
| Không retry khi SERIALIZABLE lỗi 40001 | Transaction nghiệp vụ thất bại có thể bị bỏ dở | Retry toàn transaction có giới hạn |
| Retry chỉ UPDATE sau lỗi serialization | Quyết định trước đó dựa trên snapshot cũ | Đọc lại và thực hiện lại toàn bộ logic |
| Giữ read-only transaction mở trong lúc người dùng nghỉ | Giữ snapshot/khóa và tiêu thụ tài nguyên | Kết thúc transaction sớm |
| Đặt session default rồi không reset trong pool | Request sau thừa hưởng read-only/isolation | Quản lý/reset trạng thái connection |
| Coi `setReadOnly(true)` JDBC là phân quyền | Tùy driver/framework, có thể là hint | Dùng quyền SELECT/RLS và kiểm chứng server mode |
| Coi read replica là mới nhất | Có thể có replication lag | Xem chính sách freshness/watermark |
| Thử `UPDATE` bị lỗi rồi tiếp tục trong cùng transaction | PostgreSQL có thể giữ trạng thái aborted | ROLLBACK và bắt đầu transaction mới |
| Cho rằng `DEFERRABLE` làm mọi mức cô lập an toàn | Chỉ có ý nghĩa với PG SERIALIZABLE READ ONLY | Dùng đúng tổ hợp và hiểu chi phí chờ |
| Dùng `NOLOCK` để “tối ưu báo cáo an toàn” | Có thể dirty read và bất thường khác | Chọn mức phù hợp và tối ưu query/index |
| Tưởng read-only không lấy khóa hoặc không ghi file tạm | Vẫn có lock, I/O và ngoại lệ | Giám sát thời gian/tài nguyên, kiểm soát quyền |
| Coi statement snapshot đảm bảo toàn bộ quy trình ngoài DB | Không bao quát nhiều database hay API khác | Thiết kế điểm đồng bộ liên hệ thống |

## 21. Bài tập thực hành và đáp án

Các bài dùng những bảng demo của phần 7 trong một database thử nghiệm, trừ khi ghi rõ là câu hỏi lý thuyết. Nếu dùng hai phiên, luôn bắt đầu từ trạng thái dữ liệu đã được thiết lập cho bài.

### Bài 1 — Phân biệt hai trục cấu hình

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL READ COMMITTED,
    READ ONLY;
```

Giao dịch này có thể sửa bảng thường không? Hai câu SELECT có luôn nhìn cùng snapshot không?

**Đáp án:** Không được thực hiện DML trên bảng thường ở PostgreSQL trong read-only transaction. Hai `SELECT` ở READ COMMITTED có thể thấy commit mới ở giữa nên không nhất thiết cùng snapshot.

### Bài 2 — Đổi mức cô lập trước khi đọc

Hoàn thiện transaction chỉ đọc và ổn định snapshot:

```sql
BEGIN;

SET TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

SELECT COUNT(*)
FROM demo_tx_orders_302;

COMMIT;
```

**Đáp án:** Đúng kiểu cấu trúc. `SET TRANSACTION` được đặt trước câu SELECT đầu tiên.

### Bài 3 — Cùng một hàng thay đổi giữa hai lần đọc

A mở READ COMMITTED rồi đọc stock=10; B cập nhật stock=7 và commit; A đọc lại. A thấy gì?

**Đáp án:** A có thể thấy 7 ở lần đọc thứ hai vì PostgreSQL READ COMMITTED lấy snapshot mới cho từng câu SELECT thông thường.

### Bài 4 — Cùng kịch bản ở REPEATABLE READ

A đã đọc stock=10 trong transaction REPEATABLE READ; B commit stock=7; A đọc lại trước khi commit.

**Đáp án:** A vẫn thấy 10 theo snapshot ổn định của mình; transaction mới sau khi A commit có thể thấy 7.

### Bài 5 — READ UNCOMMITTED ở PostgreSQL

B ghi stock=4 nhưng chưa commit; A mở READ UNCOMMITTED rồi đọc. A có nhìn thấy 4 chưa commit không?

**Đáp án:** Không. PostgreSQL thực thi mức READ UNCOMMITTED tương đương READ COMMITTED, nên không có dirty read.

### Bài 6 — Phantom read trong bảng orders

A COUNT đơn `status='new'` được 1; B thêm một đơn `new` và commit; A COUNT lại. Dưới READ COMMITTED và REPEATABLE READ, kết quả khác nhau thế nào?

**Đáp án:** READ COMMITTED có thể trả 2; REPEATABLE READ PostgreSQL tiếp tục trả 1 trên snapshot đã được thiết lập.

### Bài 7 — Vì sao write skew nguy hiểm?

Hai bác sĩ đều on-call, hai transaction REPEATABLE READ đọc thấy count=2 rồi mỗi bên bỏ trực cho một bác sĩ. Có thể có 0 bác sĩ trực không?

**Đáp án:** Có thể, vì hai giao dịch ghi hai hàng khác nhau và PostgreSQL REPEATABLE READ không đảm bảo ngăn mọi write skew. SERIALIZABLE có thể hủy một transaction để tránh lịch không tuần tự hóa được.

### Bài 8 — READ ONLY nhưng SERIALIZABLE

Viết một transaction chỉ đọc có ngữ nghĩa serializable và được phép chờ snapshot an toàn trên PostgreSQL.

**Đáp án:**

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT SUM(stock)
FROM demo_tx_inventory_302;

COMMIT;
```

### Bài 9 — DEFERRABLE có giúp mọi loại transaction không?

`BEGIN ISOLATION LEVEL READ COMMITTED, READ ONLY, DEFERRABLE;` có cùng lợi ích snapshot an toàn như SERIALIZABLE READ ONLY DEFERRABLE không?

**Đáp án:** Không. Trong PostgreSQL, tác dụng đặc biệt của DEFERRABLE chỉ áp dụng khi transaction đồng thời là SERIALIZABLE và READ ONLY.

### Bài 10 — Phân biệt session và transaction

`SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;` ảnh hưởng những connection nào?

**Đáp án:** Nó thay đổi mặc định của các transaction tiếp theo **trong cùng session**, không tự cấu hình những session khác. Trong connection pool cần reset nếu không muốn request sau kế thừa.

### Bài 11 — Lỗi sau UPDATE trong read-only transaction

A chạy:

```sql
BEGIN READ ONLY;
UPDATE demo_tx_inventory_302 SET stock = 20 WHERE product_id = 1;
```

Phải làm gì để phiên A trở lại trạng thái bình thường?

**Đáp án:** DML trên bảng thường bị từ chối; chạy `ROLLBACK` để kết thúc transaction đã lỗi rồi bắt đầu transaction mới nếu cần.

### Bài 12 — JDBC setReadOnly là đủ để chặn ghi?

Một ứng dụng dùng `connection.setReadOnly(true)` nhưng cùng tài khoản vẫn có `UPDATE` permission. Có thể coi dữ liệu được bảo vệ tuyệt đối không?

**Đáp án:** Không. Đây là API request/hint với hành vi phụ thuộc driver/DBMS; cần quyền database phù hợp và kiểm tra mode máy chủ. Không dùng nó thay tài khoản chỉ có quyền đọc.

### Bài 13 — Đổi transaction isolation giữa chừng

A mở transaction, đọc một hàng rồi gọi `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`. Có nên tin rằng toàn bộ công việc trước/sau là serializable không?

**Đáp án:** Không. Trong PostgreSQL, mức cô lập phải được đặt trước câu đọc/ghi đầu tiên. Nếu đã chạy với mức sai, rollback và làm lại trên transaction mới được cấu hình đúng.

### Bài 14 — Báo cáo COUNT và SUM trong hai câu

A chạy COUNT ở READ COMMITTED, B thêm một đơn rồi commit, A chạy SUM. Các chỉ số có thể không đồng bộ không?

**Đáp án:** Có. Hai câu có thể dùng hai snapshot khác nhau. Nếu yêu cầu cùng snapshot, gom trong REPEATABLE READ READ ONLY hoặc tính trong cùng một câu aggregate khi phù hợp.

### Bài 15 — Transaction trong connection pool

Một request đặt SERIALIZABLE và READ ONLY, sau đó trả connection về pool nhưng không reset. Request sau có thể gặp chuyện gì?

**Đáp án:** Có thể thừa hưởng isolation hoặc read-only không mong muốn, dẫn đến lỗi ghi hoặc tăng chi phí/retry. Framework/pool phải quản lý và hoàn trả trạng thái.

### Bài 16 — Lỗi SERIALIZABLE và retry

PostgreSQL trả SQLSTATE `40001` trong giao dịch chuyển tiền. Có nên chỉ gửi lại câu `COMMIT` không?

**Đáp án:** Không. Transaction thất bại cần được khởi tạo lại, **đọc lại dữ liệu và chạy lại toàn bộ logic** theo chính sách retry có giới hạn.

### Bài 17 — Replica với dữ liệu trễ

Báo cáo chạy trên read replica ở SERIALIZABLE READ ONLY nhưng replica chậm 30 giây so với primary. Isolation có tự cho báo cáo thấy dữ liệu primary vừa commit không?

**Đáp án:** Không. Isolation chỉ điều khiển quan sát và xung đột trên dữ liệu mà DBMS tại kết nối đang có; không khắc phục replication lag.

### Bài 18 — Ứng dụng cần dữ liệu mới ở mỗi lần xem

Người dùng cứ 10 giây refresh một dashboard. Có nên giữ nguyên một transaction REPEATABLE READ từ lúc mở dashboard cho tới khi đóng tab?

**Đáp án:** Thường không. Nó giữ snapshot cũ, làm dữ liệu không fresh và có thể gây chi phí vận hành. Mỗi lần refresh nên dùng transaction ngắn, có thể là READ COMMITTED nếu các câu trong lần refresh không cần chung snapshot, hoặc REPEATABLE READ READ ONLY cho một lần refresh gồm nhiều câu.

### Bài 19 — Isolation trong SQL Server

Một nhóm dùng SQL Server với `READ_COMMITTED_SNAPSHOT` bật. Có được mặc định mọi hành vi READ COMMITTED giống PostgreSQL không?

**Đáp án:** Không. SQL Server có thể dùng row versioning hoặc locking theo cấu hình; transaction và khóa/reads có đặc tính khác. Cần kiểm tra DBMS và cấu hình thực tế.

### Bài 20 — Chọn cấu hình phù hợp

Một báo cáo cuối ngày chạy ba SELECT từ cùng database PostgreSQL, yêu cầu số liệu cùng thời điểm, không ghi, nhưng không cần serializable cho các bất biến đọc–ghi phức tạp. Chọn cấu hình khởi đầu nào?

**Đáp án gợi ý:**

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ,
    READ ONLY;

-- Ba câu SELECT báo cáo.

COMMIT;
```

Nếu chỉ một SELECT, READ COMMITTED có thể đủ; nếu cần bảo đảm serializable cho tương tác đọc–ghi và sẵn sàng trả giá chờ, cân nhắc SERIALIZABLE READ ONLY DEFERRABLE.

## 22. Checklist khi thiết lập mức cô lập và chế độ chỉ đọc

1. **Xác định transaction gồm những statement nào.** Một câu SELECT hay nhiều câu cần cùng snapshot?
2. **Tách hai mục tiêu:** cần nhất quán đọc ở mức nào và có cần chặn thao tác ghi không?
3. **Xác định DBMS, phiên bản và cấu hình.** `READ COMMITTED`, `REPEATABLE READ` và snapshot có thể khác giữa engine.
4. **Đặt mode trước câu SQL đầu tiên.** Không sửa isolation sau khi đã đọc/ghi mà tưởng truy vấn cũ được nâng cấp.
5. **Biết thời điểm snapshot được thiết lập.** Trong PostgreSQL REPEATABLE READ, mốc này không nhất thiết là lúc gõ `BEGIN`.
6. **Hiểu các hiện tượng đồng thời:** dirty read, non-repeatable read, phantom, lost update, write skew.
7. **Nếu có bất biến nhiều hàng, đánh giá SERIALIZABLE hoặc cơ chế khóa/ràng buộc chuyên biệt.**
8. **Chuẩn bị retry toàn transaction** cho lỗi serialization/deadlock, với giới hạn và backoff.
9. **Không dùng READ ONLY thay phân quyền.** Dùng role chỉ đọc, RLS và chính sách dữ liệu phù hợp.
10. **Nếu chọn SERIALIZABLE READ ONLY DEFERRABLE, chấp nhận khả năng chờ lấy snapshot ban đầu.**
11. **Không giữ transaction lâu hơn cần thiết.** Tránh giữ snapshot/khóa trong thời gian người dùng không thao tác.
12. **Xem xét autocommit của driver/công cụ.** Nhiều SELECT có thể ở những transaction khác nhau.
13. **Reset trạng thái session khi dùng connection pool.** Isolation/read-only/session settings không được rò sang request khác.
14. **Phân biệt snapshot nhất quán với dữ liệu mới nhất.** Replica có thể chậm; snapshot cũ không tự cập nhật theo primary.
15. **Kiểm soát chi phí truy vấn.** READ ONLY không ngăn tải cao, khóa đọc hoặc dùng bộ nhớ.
16. **Thử với hai phiên thật sự.** Quan sát các mốc BEGIN, SELECT, COMMIT và ROLLBACK.
17. **Sau lỗi, kết thúc transaction đúng cách.** PostgreSQL có thể yêu cầu ROLLBACK trước khi dùng tiếp.
18. **Đối chiếu kết quả với yêu cầu nghiệp vụ.** Mức cô lập cao không tự sửa một quy tắc kiểm tra sai hoặc dữ liệu nguồn không nhất quán.

## 23. Tổng kết

**Mức cô lập quyết định transaction được quan sát và tương tác với các giao dịch khác như thế nào; chế độ `READ ONLY` quyết định phạm vi thao tác ghi được phép, không tự tạo snapshot cố định và cũng không thay thế quyền database.**

Trên PostgreSQL, `READ COMMITTED` thường phù hợp cho thao tác ngắn cần thấy các commit mới theo từng statement; `REPEATABLE READ READ ONLY` là lựa chọn thực dụng cho báo cáo nhiều câu trên một snapshot; `SERIALIZABLE` phù hợp khi cần ngăn các lịch ghi/đọc không tuần tự hóa được và ứng dụng có khả năng retry; `SERIALIZABLE READ ONLY DEFERRABLE` hữu ích cho báo cáo có thể chờ đến khi nhận snapshot an toàn.

Khi thiết kế đúng, cần đặt transaction mode **trước khi truy vấn**, giữ giao dịch ngắn, xử lý lỗi và retry có kiểm soát, bảo vệ bằng quyền truy cập thật sự và kiểm chứng hành vi trên chính DBMS đang vận hành.


