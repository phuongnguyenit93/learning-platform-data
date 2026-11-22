# Snapshot theo câu lệnh và theo giao dịch trong PostgreSQL

## 1. Cùng một giao dịch, vì sao đọc lại có thể thấy kết quả khác?

Giả sử bảng tài khoản có số dư:

```text
account_id | owner_name | balance
-----------+------------+--------
101        | An         | 500.00
202        | Bình       | 200.00
```

Hai kết nối cùng truy cập PostgreSQL:

```text
Thời điểm     Session A                        Session B
----------------------------------------------------------------
t1            BEGIN
t2            SELECT balance -> 500
t3                                             UPDATE balance = 600
t4                                             COMMIT
t5            SELECT balance -> ?
t6            COMMIT
```

Câu hỏi: ở `t5`, Session A thấy **500** hay **600**?

Đáp án phụ thuộc **mức cô lập giao dịch (*transaction isolation level*)**, chính xác hơn là **thời điểm PostgreSQL chọn snapshot cho câu lệnh hay cho toàn giao dịch**.

- Với **`READ COMMITTED`**, hai câu `SELECT` của A thường dùng **hai snapshot khác nhau**. Câu thứ hai có thể thấy 600 vì B đã commit trước khi câu thứ hai bắt đầu.
- Với **`REPEATABLE READ`**, sau khi A đã thiết lập snapshot ở lần đọc đầu, các câu đọc thông thường tiếp theo trong cùng transaction tiếp tục dùng **snapshot đó**. A vẫn thấy 500 cho đến khi giao dịch kết thúc.
- Với **`SERIALIZABLE`**, các lần đọc thông thường cũng dùng snapshot ổn định như `REPEATABLE READ`, nhưng PostgreSQL còn kiểm soát các quan hệ phụ thuộc có thể gây bất thường serialization; một giao dịch có thể phải rollback và thử lại.

Đây là trọng tâm của bài **“Snapshot theo câu lệnh và theo giao dịch”** trong phần **MVCC** của PostgreSQL.

> **Cần nhớ ngay:** `BEGIN` không tự “đóng băng toàn bộ database” cho mọi mức cô lập. Snapshot của một câu lệnh và snapshot duy trì suốt giao dịch là hai mô hình nhìn dữ liệu khác nhau.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích MVCC và snapshot là gì, khác gì với bản sao dữ liệu vật lý.
2. Phân biệt dữ liệu **đã commit**, **chưa commit** và những thay đổi do **chính giao dịch hiện tại** tạo ra.
3. Hiểu snapshot ở **mức câu lệnh** với `READ COMMITTED`.
4. Hiểu snapshot ở **mức giao dịch** với `REPEATABLE READ` và `SERIALIZABLE`.
5. Biết snapshot cố định bắt đầu từ **câu lệnh truy cập dữ liệu đầu tiên**, không nhất thiết từ chính câu `BEGIN`.
6. Thực hành hai session để quan sát nonrepeatable read và phantom read.
7. Giải thích vì sao `SELECT` thông thường khác `UPDATE` hoặc `SELECT FOR UPDATE` khi có khóa và cập nhật đồng thời.
8. Nhận diện giới hạn của snapshot ổn định, đặc biệt **write skew**.
9. Dùng transaction read-only cho báo cáo nhiều truy vấn cần kết quả nhất quán.
10. Hiểu `pg_current_snapshot()`, `pg_export_snapshot()`, `SET TRANSACTION SNAPSHOT` và giới hạn sử dụng.
11. Nhận biết ảnh hưởng của transaction lâu đến VACUUM, bloat và vận hành.
12. Áp dụng đúng trong JDBC, kiểm soát autocommit và retry giao dịch.

## 3. Khái niệm: snapshot không phải một bản sao toàn bộ database

Một **MVCC snapshot** là thông tin PostgreSQL dùng để quyết định **phiên bản hàng nào được phép hiển thị** cho một câu truy vấn hoặc giao dịch tại thời điểm phù hợp.

Nó **không** có nghĩa PostgreSQL sao chép toàn bộ bảng sang một vùng bộ nhớ mới mỗi khi bạn chạy `SELECT`.

Về khái niệm, snapshot lưu thông tin liên quan đến các transaction ID và trạng thái transaction còn đang hoạt động, từ đó PostgreSQL xác định một phiên bản hàng có nằm trong tầm nhìn của snapshot không.

Hãy tưởng tượng một hàng được cập nhật:

```text
Trước khi cập nhật:
accounts(101) -> balance = 500
                  phiên bản cũ

Transaction B thực hiện UPDATE:
accounts(101) -> balance = 600
                  phiên bản mới
                  chưa COMMIT

Snapshot của A:
  +-- Không nhìn thấy thay đổi chưa commit từ B.
  +-- Vẫn thấy phiên bản cũ = 500 nếu hợp lệ theo snapshot.

B COMMIT:
  +-- Snapshot mới bắt đầu sau commit có thể thấy 600.
  +-- Snapshot cũ của REPEATABLE READ vẫn có thể thấy 500.
```

PostgreSQL quản lý nhiều **phiên bản hàng (*tuple versions*)** để các lượt đọc có thể quan sát dữ liệu phù hợp trong khi transaction khác đang ghi.

### 3.1. Một snapshot trả lời câu hỏi nào?

Ví dụ một hàng được tạo bởi transaction X:

- Nếu X **đã commit trước ranh giới snapshot** và không bị một thay đổi hiển thị hơn thay thế, phiên bản có thể được nhìn thấy.
- Nếu X **chưa commit** ở thời điểm snapshot cần xét, transaction khác thường không thấy phiên bản mới đó.
- Nếu X commit **sau khi snapshot cố định đã được chọn**, snapshot cũ không tự nhìn thấy phiên bản X mới commit.

Đây là mô tả khái niệm, không phải thuật toán đầy đủ của mọi trường hợp MVCC, vì còn nhiều yếu tố như xóa/cập nhật phiên bản, command ID, transaction hiện tại, tuple hint bits và các cơ chế đặc biệt khác.

### 3.2. Snapshot không có nghĩa một “mốc thời gian đồng hồ” đơn giản

Không nên hình dung snapshot chỉ là:

```text
SELECT ... AS OF '2026-11-14 10:00:00'
```

PostgreSQL thông thường **không cung cấp truy vấn lịch sử theo arbitrary timestamp** bằng cách thay đổi snapshot. MVCC snapshot gắn với **tính hiển thị transaction đang tồn tại**, không phải một hệ thống time travel giữ tất cả phiên bản hàng mãi mãi.

Phiên bản cũ có thể được `VACUUM` dọn khi không còn snapshot nào cần. Muốn truy vấn lịch sử lâu dài, cần thiết kế audit/history/temporal model riêng.

### 3.3. MVCC không loại bỏ mọi khóa

Một câu `SELECT` thông thường thường đọc từ MVCC snapshot mà không cần chờ transaction khác sửa một hàng chỉ để xem bản đã commit phù hợp. Tuy nhiên:

- `UPDATE` và `DELETE` cần phối hợp ghi lên cùng hàng.
- `SELECT ... FOR UPDATE` cố tình khóa hàng.
- Một số DDL dùng khóa cấp bảng.
- Các mức isolation cao hơn có thể phát hiện xung đột và hủy transaction.

Vì vậy, **MVCC giảm sự cản trở giữa đọc và ghi**, không phải tuyên bố “PostgreSQL không bao giờ khóa”.

## 4. Chuẩn bị schema thực hành

Chỉ chạy DDL và thử nghiệm hai phiên trên một **database dùng để học**, không dùng tài khoản thật hoặc workload production.

### 4.1. Tạo bảng tài khoản

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_snapshot_lab;

CREATE TABLE mvcc_snapshot_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO mvcc_snapshot_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

Dữ liệu ban đầu:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 101 | An | 500.00 |
| 202 | Bình | 200.00 |
| 303 | Chi | 100.00 |

### 4.2. Tạo bảng đơn hàng

```sql
CREATE TABLE mvcc_snapshot_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

INSERT INTO mvcc_snapshot_lab.orders
    (order_id, customer_name, amount, status)
VALUES
    (1001, 'An',   120.00, 'PAID'),
    (1002, 'Bình',  75.00, 'NEW'),
    (1003, 'Chi',  230.00, 'PAID');
```

Bảng đơn hàng giúp phân biệt hai hiện tượng:

- **Nonrepeatable read:** một hàng `orders` đổi giá trị.
- **Phantom read:** một hàng mới được chèn vào hoặc bị loại khỏi tập thỏa `WHERE`.

### 4.3. Chạy thí nghiệm có kiểm soát

Mở hai cửa sổ `psql` hoặc hai kết nối trong công cụ SQL, đặt tên:

- **Session A:** transaction đang quan sát snapshot.
- **Session B:** transaction sửa và commit dữ liệu.

Hai kết nối phải truy cập **cùng một database và schema**.

Các ví dụ B dùng `COMMIT` sẽ làm thay đổi dữ liệu lab. Vì vậy, trước **mỗi** thí nghiệm cần đưa các hàng về giá trị khởi tạo, đồng thời đảm bảo **không còn transaction thí nghiệm đang mở**.

Ví dụ thao tác khôi phục sau khi hai session đã kết thúc:

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = 500.00
WHERE account_id = 101;

UPDATE mvcc_snapshot_lab.orders
SET amount = 120.00, status = 'PAID'
WHERE order_id = 1001;

DELETE FROM mvcc_snapshot_lab.orders
WHERE order_id IN (1004, 1005);
```

Lệnh khôi phục chỉ dành cho schema bài học, không dùng cho dữ liệu thật. Nếu một thử nghiệm đã chèn ID khác, cần khôi phục theo những thay đổi thực tế của thử nghiệm đó.

## 5. `READ COMMITTED`: mỗi câu lệnh có snapshot phù hợp tại thời điểm nó bắt đầu

`READ COMMITTED` là mức cô lập mặc định phổ biến của PostgreSQL.

Đối với một `SELECT` thông thường:

- Nó thấy dữ liệu đã commit **trước khi câu truy vấn bắt đầu** theo snapshot của câu đó.
- Nó không đọc giá trị chưa commit của transaction khác.
- Nếu chạy thêm `SELECT` sau khi transaction khác commit, lần đọc mới có thể thấy giá trị vừa commit.

### 5.1. Thí nghiệm A/B: cùng transaction, đọc hai giá trị

Đưa tài khoản 101 về 500.00 trước khi thử.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Kết quả: 500.00.
```

Giữ transaction A đang mở.

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = 600.00
WHERE account_id = 101;

COMMIT;
```

Quay lại **Session A:**

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Kết quả: 600.00.

COMMIT;
```

Tại sao?

```text
A - READ COMMITTED
BEGIN
  |
  | SELECT #1 -> snapshot S1
  |                 thấy balance=500
  |
  |                   B: UPDATE balance=600
  |                   B: COMMIT
  |
  | SELECT #2 -> snapshot S2
  |                 thấy balance=600
  |
COMMIT
```

Đây là ví dụ **nonrepeatable read**: hai lần đọc cùng một hàng trong cùng transaction có thể trả giá trị khác nhau vì có transaction khác commit giữa hai câu lệnh.

### 5.2. READ COMMITTED không dirty-read

Nếu Session B mới chạy:

```sql
BEGIN;
UPDATE mvcc_snapshot_lab.accounts
SET balance = 650.00
WHERE account_id = 101;
-- Chưa COMMIT.
```

thì `SELECT` thông thường của Session A không được thấy **650.00 chưa commit** từ B. Nếu B cuối cùng `ROLLBACK`, giá trị đó không trở thành dữ liệu commit.

PostgreSQL còn xử lý mức `READ UNCOMMITTED` tương đương `READ COMMITTED`: viết tên mức `READ UNCOMMITTED` không bật dirty reads như một số ví dụ lý thuyết ở sản phẩm khác.

### 5.3. Mỗi câu lệnh có tính nhất quán snapshot trong phạm vi đọc

Một câu `SELECT` không tự đổi snapshot giữa chừng chỉ vì transaction khác commit khi câu lệnh đang chạy.

Ví dụ một báo cáo duy nhất:

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
```

Hai biểu thức aggregate được tính trong phạm vi **một câu SELECT**, sử dụng tầm nhìn phù hợp của câu đó. Không có chuyện một aggregate ở cùng câu SELECT đọc snapshot S1 còn aggregate kia tự chuyển sang S2 chỉ vì một giao dịch khác commit.

Tuy nhiên, **hai câu SELECT tách rời** dù nằm trong một transaction `READ COMMITTED` có thể đọc hai snapshot khác nhau.

### 5.4. Cẩn trọng với hàm gọi SQL bên trong câu lệnh

Giải thích “mỗi statement một snapshot” là quy tắc nền cho truy vấn thông thường. Trong PostgreSQL, một hàm do người dùng định nghĩa, đặc biệt với độ biến động `VOLATILE`, có thể thực thi những lệnh SQL nội bộ với quy tắc snapshot khác với hàm `STABLE`/`IMMUTABLE`.

Đây là chủ đề nâng cao: không nên suy ra mọi SQL nằm sâu bên trong một hàm VOLATILE đều bị buộc vào đúng một snapshot của câu lệnh bên ngoài. Khi cần đọc nhất quán nhiều bảng, hãy hiểu semantics của hàm và isolation level đang dùng.

## 6. Snapshot của READ COMMITTED và phạm vi tự động commit

Mặc định, nhiều client chạy PostgreSQL với **autocommit** bật. Khi không có transaction tường minh, mỗi statement sẽ chạy trong transaction riêng.

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
```

Nếu không có `BEGIN` và autocommit bật, hai câu lệnh là hai transaction độc lập. Vì thế chúng có thể thấy khác nhau khi transaction khác commit giữa chúng.

Nhưng một điều rất dễ nhầm:

> Gộp hai câu SELECT vào một transaction `READ COMMITTED` **không** tự làm hai snapshot giống nhau.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

SELECT balance FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

COMMIT;
```

Hai SELECT vẫn có thể thấy hai ảnh khác nhau của database nếu transaction khác commit ở giữa.

Đây là lý do một dashboard gồm **nhiều query riêng** có thể hiển thị:

```text
Query 1: Đơn PAID = 200
Query 2: Tổng doanh thu = 19.000
```

mà hai số liệu không cùng một thời điểm logic, dù cả hai được gọi trong một transaction READ COMMITTED.

Muốn cả hai truy vấn đọc một snapshot nhất quán trong cả transaction, cân nhắc `REPEATABLE READ READ ONLY`.

## 7. `REPEATABLE READ`: một snapshot ổn định cho toàn transaction

Trong PostgreSQL, `REPEATABLE READ` sử dụng một snapshot được giữ lại cho những câu đọc thông thường trong transaction sau khi snapshot đã được thiết lập.

### 7.1. Thí nghiệm hai session

Đưa `account_id = 101` về 500.00 rồi thử.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- 500.00, thiết lập snapshot S1.
```

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = 600.00
WHERE account_id = 101;

COMMIT;
```

**Session A:**

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Vẫn 500.00 trong snapshot S1.

SELECT SUM(balance) AS total_balances
FROM mvcc_snapshot_lab.accounts;
-- Tổng dựa trên snapshot S1 (cùng với thay đổi của chính A nếu có).

COMMIT;
```

Sau khi A kết thúc transaction, một transaction mới có thể thấy 600.00.

Sơ đồ:

```text
A - REPEATABLE READ
BEGIN
  |
  | SELECT #1 -> snapshot S1
  |               thấy 500
  |
  |                 B: UPDATE thành 600
  |                 B: COMMIT
  |
  | SELECT #2 -> vẫn dùng S1
  |               thấy 500
  |
COMMIT

Transaction mới -> snapshot mới -> thấy 600
```

### 7.2. “Snapshot theo giao dịch” không nhất thiết bắt đầu đúng lúc `BEGIN`

Đây là chi tiết rất quan trọng của PostgreSQL.

Trong `REPEATABLE READ`/`SERIALIZABLE`, snapshot thường được thiết lập khi câu lệnh thực sự cần snapshot đầu tiên chạy, chẳng hạn `SELECT` hoặc câu sửa dữ liệu, **không đơn thuần ngay khi client gửi `BEGIN`**.

Thử lịch khác:

```text
t1   A: BEGIN ISOLATION LEVEL REPEATABLE READ
t2   B: UPDATE account 101 -> 600
t3   B: COMMIT
t4   A: SELECT balance lần đầu
```

Ở `t4`, A thường thấy **600**, vì snapshot đọc đầu tiên được chọn **sau** commit của B.

Vì vậy:

- `BEGIN`: bắt đầu biên giới transaction.
- `SELECT`/DML đầu tiên cần snapshot: thiết lập tầm nhìn ổn định của transaction ở mức `REPEATABLE READ`.
- Các SELECT tiếp theo: tiếp tục sử dụng tầm nhìn đó, cộng với những thay đổi do chính A thực hiện.

**Không suy ra rằng BEGIN lúc 10:00 nghĩa là mọi đọc trong REPEATABLE READ chỉ thấy dữ liệu trước 10:00.**

### 7.3. Một snapshot không có nghĩa transaction hoàn toàn “đóng băng”

Nếu Session A tự cập nhật một hàng thành công, những câu lệnh sau **trong chính A** có thể thấy thay đổi đó. Snapshot ổn định là về **tầm nhìn đối với thay đổi từ các transaction khác**, không cấm một transaction thấy những thay đổi của mình.

## 8. Transaction luôn nhìn thấy các thay đổi đã thực hiện của chính nó

Ví dụ trên database thử nghiệm:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;
-- 200.00 nếu dữ liệu vẫn ban đầu.

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 25.00
WHERE account_id = 202
RETURNING balance;
-- 225.00.

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;
-- 225.00: transaction thấy own write.

ROLLBACK;
```

`ROLLBACK` cuối đảm bảo dữ liệu không bị thay đổi bởi ví dụ.

Điều tương tự về khả năng nhìn thấy *own writes* cũng áp dụng ở `READ COMMITTED`.

### 8.1. Không nhầm snapshot cố định với chế độ read-only

`REPEATABLE READ` không mặc định chỉ đọc. Một transaction ở mức đó có thể thực hiện `INSERT`, `UPDATE` và `DELETE`, với các quy tắc xung đột tương ứng.

Nếu mục tiêu là báo cáo không sửa dữ liệu, hãy chỉ định thêm:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
SELECT SUM(amount) FROM mvcc_snapshot_lab.orders;

COMMIT;
```

`READ ONLY` mô tả **loại transaction được phép thực hiện**, còn `REPEATABLE READ` mô tả **tầm nhìn và một số quy tắc cạnh tranh**. Đó là hai thuộc tính khác nhau.

### 8.2. Những hàng do transaction khác tạo sau snapshot

Giả sử A đã chọn snapshot rồi B chèn một hàng mới và commit. A `REPEATABLE READ` sẽ không thấy hàng mới đó trong những lần đọc thông thường tiếp theo của cùng transaction.

Nhưng nếu **A tự INSERT** một hàng, A có thể đọc hàng đó trong các statement sau dù snapshot ban đầu được chọn trước lúc A INSERT.

## 9. So sánh chi tiết hai mô hình snapshot

| Câu hỏi | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| Snapshot dùng để đọc thông thường được chọn khi nào? | Theo từng statement | Snapshot cố định cho transaction khi được thiết lập lần đầu |
| Có thấy commit của transaction khác giữa hai SELECT? | **Có thể** | Không, nếu commit xảy ra sau snapshot |
| Hai SELECT giống nhau có thể ra hai kết quả? | Có | Thường không do thay đổi bên ngoài |
| Có dirty read không? | Không | Không |
| Có nonrepeatable read không? | Có thể | Không theo MVCC visibility thông thường |
| Có phantom read không? | Có thể | Không theo snapshot isolation PostgreSQL |
| Có thể thấy chính UPDATE của mình? | Có | Có |
| UPDATE trùng hàng bị sửa sau snapshot? | Có thể chờ rồi đánh giá lại điều kiện theo hàng mới | Có thể lỗi `40001` |
| Có thể write skew? | Có thể | Vẫn có thể |
| Phù hợp báo cáo nhiều câu SELECT cần cùng tầm nhìn? | Cần thận trọng | **Phù hợp**, nhất là READ ONLY |
| Có tự loại mọi serialization anomaly không? | Không | Không |

Một bảng khác cho ý nghĩa tên:

| Cụm từ | Ý nghĩa đúng |
| --- | --- |
| *Statement snapshot* | Một statement đọc từ tầm nhìn đã xác định của statement đó |
| *Transaction snapshot* | Nhiều statement đọc từ cùng một tầm nhìn ổn định của transaction |
| *Committed data* | Dữ liệu của transaction đã được xác nhận; vẫn cần biết commit xảy ra trước hay sau snapshot |
| *Consistent snapshot* | Tầm nhìn dữ liệu tuân thủ quy tắc MVCC của một snapshot, không chứng minh mọi bất biến nghiệp vụ tự được thỏa |
| *Fresh snapshot* | Một snapshot mới có thể thấy các commit gần đây hơn snapshot cũ |
| *Old snapshot* | Snapshot trước những commit mới; không tự gây sai mà là một đặc tính isolation được yêu cầu |

## 10. Phantom read: cùng điều kiện WHERE nhưng tập hàng thay đổi

Một **phantom** là hàng mới xuất hiện hoặc biến mất khỏi kết quả lọc khi transaction lặp truy vấn do transaction khác commit.

### 10.1. Ví dụ ở READ COMMITTED

Giả sử bảng `orders` ban đầu có **hai đơn PAID**: 1001 và 1003.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 2.
```

**Session B:**

```sql
BEGIN;

INSERT INTO mvcc_snapshot_lab.orders
    (order_id, customer_name, amount, status)
VALUES
    (1004, 'Dung', 160.00, 'PAID');

COMMIT;
```

**Session A:**

```sql
SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 3.

COMMIT;
```

Câu query không đổi nhưng kết quả từ **2 sang 3** vì snapshot thứ hai nhìn thấy hàng đã commit mới.

### 10.2. Lặp lại ở REPEATABLE READ

Khôi phục dữ liệu (xóa đơn 1004 khi mọi transaction thí nghiệm đã kết thúc), rồi thay Session A bằng:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 2, thiết lập snapshot.
```

Session B chèn 1004 và commit như trên.

Session A:

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- Vẫn 2 trong snapshot của A.

COMMIT;
```

Trong PostgreSQL, `REPEATABLE READ` **không cho phantom read kiểu này** vì snapshot không thay đổi giữa các statement. Đây là điểm đáng lưu ý khi so với một số bảng mô tả isolation chỉ dựa trên mức tối thiểu của chuẩn SQL.

### 10.3. Không có phantom không đồng nghĩa không có write skew

Snapshot ổn định giữ **tập hàng nhìn thấy** của transaction, nhưng **không tự ngăn** hai transaction đồng thời đọc cùng một điều kiện rồi cập nhật **hai hàng khác nhau** khiến một bất biến toàn cục bị phá vỡ.

Chúng ta sẽ xem ví dụ với `SERIALIZABLE` ở phần sau.

## 11. Snapshot của statement là một tầm nhìn ổn định, không phải từng hàng cập nhật liên tục

Hãy hình dung một câu `SELECT` quét một bảng lớn trong vài giây. Nếu transaction B commit ở giữa quá trình quét, một SELECT thông thường ở `READ COMMITTED` không “đổi snapshot giữa nửa bảng” để nửa đầu thấy trạng thái cũ còn nửa sau thấy trạng thái mới chỉ vì thời gian trôi.

Đó là lợi ích của **statement-level consistency**.

### 11.1. Khi chạy nhiều truy vấn liên tiếp

Ngược lại, dashboard có thể chạy:

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
```

Nếu hai lệnh chạy ở `READ COMMITTED`, giữa chúng có thể có một transaction khác commit. Vì vậy một tỷ lệ được tính bằng cách ghép **hai kết quả của hai query riêng** có nguy cơ trộn những tầm nhìn khác nhau.

Có hai hướng giải quyết phổ biến:

- **Gom các số liệu trong một statement** nếu nghiệp vụ cho phép.
- Nếu cần nhiều statement riêng, dùng transaction `REPEATABLE READ READ ONLY`.

### 11.2. Gom metric thành một câu SELECT

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount,
    COUNT(*) AS all_orders
FROM mvcc_snapshot_lab.orders;
```

Ba metric được tính trong cùng một statement và cùng tầm nhìn MVCC thích hợp.

Đây là lựa chọn tốt khi các chỉ số cùng xuất phát từ một dữ liệu nguồn và không cần các query quá phức tạp.

### 11.3. CTE không tự tạo transaction mới

```sql
WITH paid AS (
    SELECT *
    FROM mvcc_snapshot_lab.orders
    WHERE status = 'PAID'
),
metrics AS (
    SELECT COUNT(*) AS total, SUM(amount) AS revenue
    FROM paid
)
SELECT *
FROM metrics;
```

Đây vẫn là **một SQL statement**. Không nên nhầm hai CTE là hai transaction độc lập.

**Chú ý nâng cao:** câu lệnh sửa dữ liệu bên trong data-modifying CTE có quy tắc snapshot, thứ tự và `RETURNING` riêng; bài này tập trung vào SELECT thông thường. Không dùng CTE lồng nhau để mặc định các UPDATE độc lập sẽ nhìn thấy nhau như những statement tuần tự.

## 12. `UPDATE` tại READ COMMITTED có một ngoại lệ thực hành quan trọng

Quy tắc “mỗi statement có snapshot” rất hữu ích cho `SELECT` thông thường. Nhưng các lệnh **có khóa hàng** như `UPDATE`, `DELETE` và `SELECT ... FOR UPDATE` cần giải quyết trường hợp một hàng được transaction khác cập nhật đồng thời.

Ở `READ COMMITTED`, nếu câu lệnh cần cập nhật một hàng nhưng hàng đó đang bị transaction khác khóa, PostgreSQL có thể:

1. Chờ transaction đang giữ khóa.
2. Khi transaction đó kết thúc, xét phiên bản hàng thích hợp.
3. **Đánh giá lại điều kiện WHERE** trên phiên bản đã commit mới trước khi quyết định cập nhật.

Cơ chế đánh giá lại điều kiện thường được gọi trong tài liệu PostgreSQL là **EvalPlanQual** trong những bối cảnh tương ứng.

### 12.1. Ví dụ giảm tồn kho với điều kiện

Tạo bảng:

```sql
CREATE TABLE mvcc_snapshot_lab.inventory (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0)
);

INSERT INTO mvcc_snapshot_lab.inventory
    (product_id, available)
VALUES (701, 1);
```

Có hai transaction cùng muốn bán một sản phẩm với tồn kho chỉ còn 1.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING product_id, available;
-- Trả hàng product_id=701, available=0.
-- Chưa COMMIT nên vẫn đang giữ khóa hàng.
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING product_id, available;
-- Có thể chờ khóa của A.
```

Sau khi **A COMMIT**, B tiếp tục. PostgreSQL xem lại hàng có `available = 0`, nên điều kiện `available >= 1` không đúng. B **cập nhật 0 hàng** thay vì giảm tiếp xuống -1.

**Điểm chính:**

- Đây vẫn là READ COMMITTED.
- `UPDATE` có xử lý cạnh tranh ghi và đánh giá lại hàng sau khi chờ.
- `CHECK available >= 0` là một lớp bảo vệ nữa.
- Ứng dụng phải xem số hàng của `RETURNING` hoặc affected row count; không được coi “UPDATE không báo lỗi” là chắc chắn bán thành công.

### 12.2. Không suy rộng rằng mọi UPDATE luôn có ảnh nhất quán toàn bảng

Tại READ COMMITTED, một câu lệnh cập nhật phức tạp có thể **nhìn thấy trạng thái được cập nhật mới cho các hàng mục tiêu xung đột** trong khi các hàng khác vẫn theo snapshot của statement. Tài liệu PostgreSQL cảnh báo điều này có thể tạo tầm nhìn không hoàn toàn tự nhất quán cho các lệnh cập nhật phức tạp.

Vì thế, với bất biến phụ thuộc nhiều hàng, cần thiết kế **transaction và isolation** phù hợp thay vì tin rằng một `UPDATE` có WHERE phức tạp luôn mô phỏng một ảnh chụp toàn hệ thống không đổi trong mọi cạnh tranh.

### 12.3. `SELECT ... FOR UPDATE` khác SELECT thông thường

```sql
BEGIN;

SELECT *
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101
FOR UPDATE;

ROLLBACK;
```

Câu `SELECT FOR UPDATE` cố khóa hàng. Nếu có transaction khác đang cập nhật hàng đó, nó có thể phải chờ, rồi ở READ COMMITTED xử lý phiên bản hàng mới tương ứng.

Ngược lại, một `SELECT` thuần túy thường chỉ đọc phiên bản nhìn thấy theo snapshot mà không cố chiếm quyền cập nhật hàng.

**Vì vậy:** đừng áp dụng máy móc sơ đồ “statement snapshot” của SELECT bình thường để đoán mọi kết quả `SELECT FOR UPDATE` khi đang chờ khóa.

## 13. Khi có xung đột ghi ở REPEATABLE READ

Ở `REPEATABLE READ`, PostgreSQL **không** đơn giản dùng lại cơ chế nhìn thấy phiên bản mới theo cách READ COMMITTED đối với một hàng đã bị thay đổi sau snapshot.

Một transaction có thể bị từ chối khi cố sửa hàng đã được transaction khác cập nhật và commit sau snapshot của nó.

### 13.1. Thí nghiệm hai phiên

Giả sử tài khoản 101 có 500.00.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- 500.00: thiết lập snapshot S1.
```

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
-- Database bây giờ có 550.00.
```

**Session A:**

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

-- Có thể báo:
-- ERROR: could not serialize access due to concurrent update
-- SQLSTATE: 40001

ROLLBACK;
```

Tại sao A không được tùy ý ghi thêm lên phiên bản 550 sau khi đã sử dụng snapshot S1 thấy 500? Vì điều đó phá vỡ tính nhất quán của mô hình snapshot/ghi ở mức này.

### 13.2. Lỗi 40001 có nghĩa gì?

SQLSTATE **`40001`** là `serialization_failure`. Nó không giới hạn chỉ ở isolation `SERIALIZABLE`; ở PostgreSQL, một số xung đột cập nhật trong `REPEATABLE READ` cũng có thể phát sinh lỗi có mã này.

Ứng dụng nên:

1. Rollback transaction thất bại.
2. Tạo một transaction **mới**.
3. Đọc lại dữ liệu và tính lại quyết định.
4. Thực hiện câu lệnh phù hợp.
5. Commit hoặc retry có giới hạn nếu xung đột tiếp tục.

Không retry một câu `UPDATE` bị lỗi **ngay trong transaction đã thất bại** với snapshot cũ.

### 13.3. Nếu A không UPDATE thì sao?

Nếu A chỉ SELECT lại tài khoản 101 trong cùng transaction REPEATABLE READ sau B commit, A vẫn thấy 500.00. Nó không tự nhận `40001` chỉ vì có một transaction khác đã commit một thay đổi.

Nhưng khi A cần thực hiện một thao tác xung đột ghi hoặc có kiểm tra serializable khác, có thể phát sinh lỗi tùy tình huống.

## 14. Mức cô lập và hiện tượng đọc bất thường

Bảng dưới dựa trên hành vi PostgreSQL:

| Mức cô lập | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Không | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Không theo MVCC snapshot | Vẫn có thể |
| `SERIALIZABLE` | Không | Không | Không | Hệ thống ngăn lịch không tuần tự hóa được; có thể rollback/retry |

`READ UNCOMMITTED` trong PostgreSQL hoạt động như `READ COMMITTED`, nên không có dirty reads chỉ vì yêu cầu mức đó.

### 14.1. `SERIALIZABLE` không chỉ là REPEATABLE READ “đọc ổn hơn”

Cả hai có snapshot cố định cho những lần đọc thông thường. Khác biệt quan trọng là `SERIALIZABLE` còn đảm bảo các transaction commit có thể được giải thích bằng một **thứ tự thực thi tuần tự hợp lệ**, khi các transaction liên quan dùng isolation và quy tắc truy cập phù hợp.

PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để phát hiện những mẫu phụ thuộc có thể tạo bất thường. Khi cần, nó hủy một transaction bằng lỗi `40001`.

Do đó:

- `REPEATABLE READ`: tầm nhìn ổn định, nhưng **write skew** còn có thể xảy ra.
- `SERIALIZABLE`: có kiểm soát thêm các bất thường không thể tuần tự hóa, đổi lại phải sẵn sàng **retry**.

### 14.2. Isolation không thay thế kiểm tra nghiệp vụ

Ngay cả ở SERIALIZABLE, một transaction chạy:

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 999999.00
WHERE account_id = 101;
```

vẫn có thể hợp lệ về mặt cô lập nếu schema/logic không cấm. Isolation giải quyết tương tác giữa các transaction; nó không tự biết một khoản cộng tiền có nguồn hợp lệ hay không.

## 15. Write skew: giới hạn của snapshot ổn định

Hãy xét một phòng khám có hai bác sĩ A và B. Quy tắc là **phải luôn có ít nhất một bác sĩ trực**.

### 15.1. Tạo dữ liệu

```sql
CREATE TABLE mvcc_snapshot_lab.doctors_on_call (
    doctor_id bigint PRIMARY KEY,
    doctor_name text NOT NULL,
    on_call boolean NOT NULL
);

INSERT INTO mvcc_snapshot_lab.doctors_on_call
    (doctor_id, doctor_name, on_call)
VALUES
    (1, 'Bác sĩ A', TRUE),
    (2, 'Bác sĩ B', TRUE);
```

Mỗi bác sĩ muốn nghỉ nếu thấy vẫn còn người khác trực.

### 15.2. Hai transaction REPEATABLE READ cùng nhìn snapshot hợp lệ

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS people_on_call
FROM mvcc_snapshot_lab.doctors_on_call
WHERE on_call = TRUE;
-- 2.
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS people_on_call
FROM mvcc_snapshot_lab.doctors_on_call
WHERE on_call = TRUE;
-- 2.
```

**Session A:**

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = FALSE
WHERE doctor_id = 1;
```

**Session B:**

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = FALSE
WHERE doctor_id = 2;
```

Hai transaction sửa **hai hàng khác nhau**, nên chúng có thể cùng commit ở REPEATABLE READ:

```sql
COMMIT;
```

Kết quả cuối: không còn ai trực.

### 15.3. Vì sao snapshot ổn định vẫn không đủ?

Mỗi transaction đọc từ một snapshot có **hai bác sĩ trực** và tưởng rằng khi mình nghỉ vẫn còn một người. Nhưng chúng **không thấy quyết định chưa commit của nhau**. Do cập nhật hai hàng khác nhau, có thể không xảy ra xung đột ghi trực tiếp để buộc một bên thất bại.

Đây là **write skew**, một dạng serialization anomaly.

### 15.4. SERIALIZABLE xử lý khác thế nào?

Khôi phục cả hai bác sĩ thành `TRUE` sau khi đã đóng hai transaction:

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = TRUE;
```

Thử lại cùng lịch đọc–cập nhật nhưng mở:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

và cho cả hai transaction đọc điều kiện rồi ghi như trước.

PostgreSQL có thể phát hiện phụ thuộc đọc–ghi tạo lịch không thể tuần tự hóa, và **một transaction phải thất bại** với `40001` thay vì cả hai cùng commit làm quy tắc sai.

Sau rollback và retry toàn transaction, giao dịch được chạy lại sẽ đọc số người trực mới và phải **từ chối cho người cuối cùng nghỉ**.

**Điều quan trọng:** PostgreSQL SERIALIZABLE không tự biết quy tắc “ít nhất một người trực”; **ứng dụng vẫn phải thực hiện kiểm tra đó trong transaction**. SERIALIZABLE bảo vệ tính tương đương tuần tự của những transaction thực sự được viết.

## 16. Snapshot ổn định không đồng nghĩa dữ liệu đã “mới nhất”

Một báo cáo mở transaction REPEATABLE READ lúc gần 10:00 và giữ đến 10:30 có thể tiếp tục thấy dữ liệu tương ứng với snapshot ở lần truy cập đầu.

Đó là hành vi **đúng theo isolation**, không phải lỗi cache.

Ví dụ:

```text
10:00  A: BEGIN REPEATABLE READ
10:01  A: SELECT doanh thu -> snapshot S1
10:05  B: COMMIT nhiều đơn mới
10:10  A: SELECT doanh thu -> vẫn S1
10:20  B: COMMIT thêm đơn
10:30  A: SELECT doanh thu -> vẫn S1
10:31  A: COMMIT
10:32  A: transaction mới -> snapshot mới
```

Một tầm nhìn nhất quán qua nhiều truy vấn là lợi thế của reporting, nhưng nếu giữ transaction quá lâu, dashboard có thể hiển thị **dữ liệu cũ hơn thực tế**.

### 16.1. Chọn đúng hợp đồng dữ liệu

Một số nhu cầu khác nhau:

| Nhu cầu | Hướng xử lý |
| --- | --- |
| “Mỗi màn hình cần số mới nhất tại lúc request chạy” | Có thể chấp nhận READ COMMITTED; hiểu query nào có snapshot nào |
| “Ba metric trong một query phải nhất quán” | Gom trong một SELECT nếu phù hợp |
| “Nhiều query của một báo cáo phải cùng một trạng thái dữ liệu” | Transaction REPEATABLE READ READ ONLY |
| “Transaction vừa đọc điều kiện nhiều hàng vừa ra quyết định ghi an toàn trước concurrent writes” | Xem SERIALIZABLE, khóa/ràng buộc hoặc thiết kế khác |
| “Báo cáo phải tuyệt đối mới đến thời điểm hiện tại” | Snapshot cố định dài không phù hợp; cần định nghĩa độ trễ chấp nhận |
| “Đọc lại khi có commit mới theo thời gian thực” | Transaction mới hoặc READ COMMITTED theo từng statement |

Không có một isolation level tốt nhất cho mọi loại ứng dụng.

## 17. Transaction read-only cho báo cáo nhiều câu SELECT

Giả sử cần xây báo cáo gồm:

- Số đơn thanh toán.
- Tổng tiền đơn thanh toán.
- Danh sách đơn thanh toán để xuất CSV.

Nếu chạy ba query độc lập bằng READ COMMITTED, chúng có thể nhận các snapshot khác nhau. Cách có chủ đích:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT COALESCE(SUM(amount), 0::numeric) AS paid_amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID'
ORDER BY order_id;

COMMIT;
```

Các SELECT này đọc từ tầm nhìn **cùng một transaction**, nên danh sách đơn không tự nhận thêm một đơn mới do transaction khác commit giữa ba câu SELECT.

### 17.1. READ ONLY có phải là khóa bảng để ngăn người khác ghi?

**Không.** Transaction đọc có snapshot ổn định nhưng không nhất thiết khóa toàn bảng để ngăn writer.

Transaction khác vẫn có thể cập nhật/chèn dữ liệu. Những thay đổi đó chỉ không được tự thêm vào snapshot đọc đã thiết lập của transaction REPEATABLE READ.

### 17.2. Lưu ý với thứ tự và phân trang

Snapshot ổn định bảo đảm tầm nhìn dữ liệu, nhưng `LIMIT`/`OFFSET` không tự tạo thứ tự ổn định nếu query thiếu `ORDER BY`.

Ví dụ xuất dữ liệu theo trang:

```sql
SELECT order_id, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 0;
```

Cần dùng một thứ tự xác định như khóa chính `order_id`. Nếu không, các trang có thể không nhất quán về thứ tự trình bày dù dữ liệu nguồn dùng cùng một snapshot.

### 17.3. Báo cáo kéo dài cần chú ý chi phí giữ snapshot

Một transaction đọc toàn dữ liệu có thể vẫn giữ MVCC horizon, làm VACUUM chưa thể dọn một số phiên bản hàng cũ đang được snapshot tham chiếu. Do đó, đừng giữ transaction REPEATABLE READ mở trong lúc người dùng xem trang hoặc chờ thao tác UI nhiều phút.

Quy trình tốt là:

1. Mở transaction.
2. Thực thi những SELECT thực sự cần.
3. Kết thúc transaction.
4. Trả kết quả/định dạng dữ liệu ngoài transaction nếu có thể.

## 18. `SERIALIZABLE READ ONLY DEFERRABLE`: snapshot an toàn cho báo cáo phức tạp

PostgreSQL có một cách đặc biệt:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

Ý nghĩa:

- `SERIALIZABLE`: yêu cầu ngữ nghĩa tuần tự hóa.
- `READ ONLY`: transaction không sửa dữ liệu.
- `DEFERRABLE`: transaction có thể **chờ trước khi thực thi truy vấn đầu** cho đến khi tìm được một snapshot an toàn phù hợp.

Điều này hữu ích cho một số báo cáo read-only dài, nơi muốn tránh phải rollback/retry vì xung đột serialization sau khi đã tính toán nhiều.

### 18.1. Không coi DEFERRABLE là “đọc ngay không bao giờ chờ”

Ngược lại, transaction **có thể chờ ở đầu** để đạt safe snapshot. Nếu ứng dụng có SLA rất ngắn, phải cân nhắc thời gian chờ đó.

### 18.2. DEFERRABLE không thay thế READ ONLY/SERIALIZABLE

Tùy chọn `DEFERRABLE` có ý nghĩa đặc biệt đối với transaction **SERIALIZABLE READ ONLY**. Không thể chỉ bật nó ở một READ COMMITTED writer rồi kỳ vọng có safe snapshot như trên.

### 18.3. Khi nào nên dùng?

Ví dụ phù hợp:

- Xuất báo cáo kế toán lớn cần một tầm nhìn nhất quán.
- Tính đối soát nhiều bảng trong một quy trình chỉ đọc.
- Công việc phân tích read-only có thể chấp nhận chờ lúc bắt đầu để hạn chế nguy cơ lỗi serialization về sau.

Không cần áp dụng cho mọi request API nhỏ; đây là một công cụ khi **mô hình cô lập và chi phí vận hành** thực sự yêu cầu.

## 19. `BEGIN`, `SET TRANSACTION` và thời điểm thay đổi isolation

Có thể đặt isolation ngay khi bắt đầu:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
```

Hoặc đặt trong transaction **trước khi đã chạy truy vấn không cho phép đổi isolation**:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

### 19.1. Không đổi isolation sau khi đã đọc và mong snapshot được làm lại

Sai ý tưởng:

```sql
BEGIN;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- Quá muộn để chuyển mô hình snapshot cho các truy vấn đã chạy.

COMMIT;
```

Trong PostgreSQL, thay đổi isolation bằng `SET TRANSACTION ISOLATION LEVEL` cần được thực hiện trước câu lệnh truy vấn/sửa dữ liệu đầu tiên của transaction.

### 19.2. `SET SESSION CHARACTERISTICS` khác `SET TRANSACTION`

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL REPEATABLE READ;
```

Lệnh trên thay đổi **mặc định cho các transaction tương lai trong session**, không nhất thiết làm thay đổi transaction đã bắt đầu hoặc các session khác.

Đối với connection pool, cần đặc biệt cẩn trọng với cấu hình mức session: một connection có thể được tái sử dụng cho request sau. Ưu tiên transaction manager hoặc cách đặt isolation rõ ràng theo request và chính sách pool.

### 19.3. Isolation được chọn không phải công tắc toàn database

Nếu hai service có connection riêng, service A tự chọn `REPEATABLE READ` không ép service B cũng chuyển mức isolation. Mỗi transaction có cấu hình của nó.

Để bảo vệ một bất biến nhiều transaction, cần xem toàn bộ các luồng tham gia, không chỉ một SELECT đơn lẻ.

## 20. `now()` và `statement_timestamp()` không phải định danh snapshot

Khi viết báo cáo, nhiều người nhầm:

- `now()`.
- `transaction_timestamp()`.
- `statement_timestamp()`.
- `clock_timestamp()`.
- MVCC snapshot.

Chúng **không đồng nghĩa**.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `now()` | Thời điểm bắt đầu transaction theo quy tắc PostgreSQL |
| `transaction_timestamp()` | Tương đương `now()` |
| `statement_timestamp()` | Thời điểm bắt đầu statement hiện tại |
| `clock_timestamp()` | Thời gian đồng hồ thực tại thời điểm gọi; có thể thay đổi ngay trong một statement |
| `pg_current_snapshot()` | Thông tin snapshot MVCC, không phải timestamp đơn |

### 20.1. Thử trong một transaction

```sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

-- Chạy một câu SELECT khác sau đó:
SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

Trong cùng transaction:

- `now()` giữ thời điểm bắt đầu transaction.
- `statement_timestamp()` có thể khác giữa các statement.
- `clock_timestamp()` phản ánh thời điểm gọi.

### 20.2. Một điểm dễ gây nhầm

Trong `REPEATABLE READ`, snapshot có thể chỉ được chọn lúc **SELECT đầu tiên**, sau `BEGIN`. Do đó, `now()` là transaction start time **không phải bằng chứng chính xác snapshot được chọn khi nào**.

Trong `READ COMMITTED`, `now()` vẫn có thể cố định trong toàn transaction dù mỗi statement có một snapshot mới.

Vì vậy, dùng:

```sql
SELECT now();
```

không chứng minh transaction đã đọc một snapshot cố định như REPEATABLE READ.

### 20.3. Không dùng mốc đồng hồ để tự suy luận commit ordering

Hai session có đồng hồ không cùng thứ tự như cách transaction được xác nhận, và timestamp của transaction có thể không trùng với thời điểm commit. Khi cần một thứ tự nghiệp vụ bền vững, phải thiết kế khóa, sequence/commit pipeline hoặc mô hình sự kiện rõ ràng; `now()` đơn lẻ không phải commit ID.

## 21. Quan sát snapshot bằng các hàm PostgreSQL

PostgreSQL cung cấp các hàm để quan sát thông tin snapshot, hữu ích khi học và chẩn đoán.

### 21.1. `pg_current_snapshot()`

```sql
SELECT pg_current_snapshot();
```

Kết quả thuộc kiểu `pg_snapshot`, thể hiện thông tin giúp xác định các transaction ID nhìn thấy/không nhìn thấy theo tầm nhìn hiện tại.

Dạng hiển thị có thể như:

```text
xmin:xmax:xip_list
```

Trong đó, ở mức khái niệm:

- `xmin` là biên dưới liên quan đến các transaction còn được theo dõi.
- `xmax` là giới hạn trên của một tập transaction ID được snapshot xem xét.
- Danh sách các transaction đang hoạt động tại thời điểm snapshot đóng vai trò quyết định transaction nào **chưa được coi đã commit trong tầm nhìn đó**.

Đây là thông tin nội bộ của MVCC, **không phải** kết quả “database ở thời điểm 10:15:00”.

### 21.2. Lấy các trường thông tin snapshot

Trong các phiên bản PostgreSQL hỗ trợ các hàm `pg_snapshot`:

```sql
SELECT
    pg_snapshot_xmin(pg_current_snapshot()) AS snapshot_xmin,
    pg_snapshot_xmax(pg_current_snapshot()) AS snapshot_xmax;
```

Những số này là transaction ID boundaries, không phải thứ tự giao dịch ngân hàng hay ngày giờ.

Nếu đang học trên phiên bản cũ, tên các hàm liên quan snapshot và kiểu dữ liệu có thể khác; cần đối chiếu tài liệu của đúng phiên bản PostgreSQL được sử dụng.

### 21.3. Không coi hai chuỗi snapshot giống/khác là phép kiểm thử isolation tuyệt đối

Một snapshot là một cấu trúc phức tạp hơn một con số. Hai câu `SELECT pg_current_snapshot()` liên tiếp có thể trả **cùng biểu diễn** dù chúng thuộc **hai statement snapshots khác nhau**, nếu trạng thái transaction đang hoạt động không thay đổi.

Ngược lại, snapshot hiển thị các transaction ID không phải “dấu thời gian” ổn định cho người dùng cuối.

Để minh họa isolation, bài tập hai session với **giá trị bảng cụ thể được commit giữa hai SELECT** thường dễ hiểu và có ý nghĩa hơn chỉ so chuỗi snapshot.

## 22. `xmin` và `xmax`: dấu vết MVCC trên hàng

PostgreSQL có các cột hệ thống liên quan đến phiên bản hàng, bao gồm `xmin` và `xmax`.

Bạn có thể quan sát trong lab:

```sql
SELECT
    account_id,
    balance,
    xmin,
    xmax,
    ctid
FROM mvcc_snapshot_lab.accounts
ORDER BY account_id;
```

Ý nghĩa đơn giản:

- `xmin`: thông tin transaction đã tạo ra phiên bản hàng đang được đọc.
- `xmax`: trường hệ thống có liên quan đến xóa/cập nhật/khóa hàng theo cơ chế MVCC.
- `ctid`: vị trí vật lý của phiên bản hàng trong bảng, có thể đổi khi update hoặc sắp xếp lại vật lý.

### 22.1. Vì sao UPDATE tạo phiên bản mới?

Ở mức khái niệm, PostgreSQL thường không sửa trực tiếp một phiên bản hàng theo cách khiến những reader cũ lập tức mất dữ liệu cần đọc. Thay vào đó, UPDATE có thể tạo **phiên bản hàng mới**, còn phiên bản cũ tồn tại cho những snapshot còn cần nó.

```text
Snapshot S1  ---> phiên bản accounts(101, balance=500)
                  [old tuple]

B UPDATE + COMMIT
               \
                \--> phiên bản accounts(101, balance=600)
                     [new tuple]

Snapshot S2  ---> thấy phiên bản mới = 600
```

### 22.2. Không dùng `xmin/xmax/ctid` làm API nghiệp vụ

Các cột hệ thống giúp học và debug. Nhưng:

- `xmax` có thể chứa thông tin liên quan đến **khóa** chứ không chỉ xóa hẳn.
- Cấu trúc và ý nghĩa chi tiết cần hiểu theo nội bộ PostgreSQL.
- `ctid` có thể thay đổi khi cập nhật hàng và không phải ID ổn định.
- Transaction ID có vòng đời và cơ chế wraparound/freeze.

Không dùng `xmin <> ...` hoặc `xmax <> 0` như một bộ lọc nghiệp vụ để khẳng định hàng chắc chắn đã bị xóa hay commit.

Để xây ứng dụng, dùng khóa chính, version column, timestamp nghiệp vụ, CDC hoặc cơ chế audit phù hợp.

## 23. Snapshot theo câu lệnh và transaction trong một timeline đầy đủ

Đặt ba transaction khác nhau vào sơ đồ:

```text
                    Thời gian ------------------------------------------------>

Session A             BEGIN -------------------------------------------- COMMIT
                      SELECT #1                SELECT #2           SELECT #3

Session B                        BEGIN
                                      UPDATE rows
                                      COMMIT

Session C                                                      BEGIN
                                                              INSERT row
                                                              COMMIT
```

**Nếu A ở READ COMMITTED:**

- SELECT #1 có snapshot S1 trước B commit.
- SELECT #2 có snapshot S2 sau B commit nhưng có thể trước C commit.
- SELECT #3 có snapshot S3 sau C commit.
- Ba câu lệnh có thể thấy **ba trạng thái dữ liệu khác nhau**.

**Nếu A ở REPEATABLE READ:**

- SELECT #1 thiết lập snapshot S1.
- SELECT #2 và SELECT #3 vẫn dùng S1 đối với thay đổi của B và C.
- Những thay đổi do B/C commit sau S1 không tự xuất hiện trong A.
- Khi A kết thúc và mở transaction mới, query mới có thể thấy chúng.

**Nếu A ở SERIALIZABLE:**

- Các SELECT thường cũng quan sát snapshot ổn định.
- PostgreSQL theo dõi thêm phụ thuộc cần thiết để ngăn lịch không tuần tự hóa được, bằng cách hủy/retry một số transaction khi cần.

### 23.1. Đừng gộp “độ mới” và “độ nhất quán” thành một tiêu chí

- READ COMMITTED: cho phép các statement tiếp theo cập nhật tầm nhìn về commit mới hơn.
- REPEATABLE READ: giữ một tầm nhìn ổn định xuyên suốt nhiều statement.
- SERIALIZABLE: thêm bảo đảm về tính tương đương tuần tự của những transaction commit.

Mức cao hơn không có nghĩa báo cáo luôn nhận dữ liệu **mới hơn**. Đôi khi nó có chủ đích thấy dữ liệu **cũ hơn nhưng cùng một snapshot**.

## 24. Export/import snapshot giữa nhiều connection

Một transaction snapshot thường gắn với **một transaction**, không tự chia sẻ giữa các connection.

Nhưng PostgreSQL có cơ chế **xuất và nhập snapshot** để nhiều transaction cùng tham chiếu một tầm nhìn phù hợp.

Các hàm/lệnh:

- `pg_export_snapshot()`.
- `SET TRANSACTION SNAPSHOT 'snapshot_id'`.

Đây là công cụ nâng cao, hữu ích cho một số luồng đọc đồng bộ trên nhiều connection.

### 24.1. Session A xuất snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

Kết quả ví dụ là một chuỗi định danh snapshot:

```text
00000003-0000001B-1
```

**Chuỗi chỉ là ví dụ**, không được hardcode như một ID luôn hợp lệ; kết quả thực tế phải lấy từ Session A vừa chạy.

Session A phải **giữ transaction mở** cho đến khi các transaction khác đã import xong snapshot. Không được COMMIT ngay nếu Session B chưa sử dụng nó.

### 24.2. Session B nhập snapshot trước truy vấn đầu tiên

Trong một connection **khác**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

Thay `'00000003-0000001B-1'` bằng **ID thật được Session A trả về**.

Điều kiện quan trọng:

1. Transaction nhập phải dùng isolation **`REPEATABLE READ` hoặc `SERIALIZABLE`** theo yêu cầu PostgreSQL.
2. Phải nhập snapshot **trước khi transaction nhập chạy truy vấn hoặc thay đổi dữ liệu**.
3. Transaction xuất phải còn mở **cho đến khi việc import hoàn thành**.
4. Import snapshot **không chia sẻ các thay đổi chưa commit của transaction xuất**.
5. Với `SERIALIZABLE` có thêm các điều kiện tương thích giữa transaction xuất và nhập; cần xem hướng dẫn phiên bản cụ thể, không trộn tùy tiện với snapshot xuất từ transaction khác mức/loại.

Sau khi Session B đã import thành công, Session A có thể kết thúc; các transaction nhập vẫn có tầm nhìn của chúng theo ngữ nghĩa đã thiết lập.

### 24.3. Không biến export/import snapshot thành cơ chế time travel

Bạn không thể lưu token snapshot vào một bảng, chờ một tuần rồi dùng nó để đọc dữ liệu “như tuần trước”. Snapshot export chỉ khả dụng trong thời gian transaction xuất còn hiệu lực cho việc nhập.

Muốn lịch sử lâu dài, dùng backup/PITR trong bối cảnh vận hành hoặc mô hình lịch sử nghiệp vụ. Exported snapshot giải quyết **đọc cùng tầm nhìn giữa nhiều transaction đang phối hợp**, không phải kho lưu snapshot vĩnh viễn.

### 24.4. Trường hợp sử dụng

Ví dụ có ba worker đọc các tập dữ liệu khác nhau để làm một báo cáo cùng kỳ. Nếu mỗi worker mở `REPEATABLE READ` riêng vào các thời điểm khác nhau, mỗi worker có thể chọn snapshot khác nhau. Import cùng snapshot giúp thống nhất tầm nhìn trong những điều kiện hợp lệ.

PostgreSQL `pg_dump` khi sử dụng nhiều job song song cũng liên quan đến cách đồng bộ snapshot cho quá trình dump nhất quán.

## 25. Transaction lâu và VACUUM: chi phí của snapshot cũ

MVCC cho phép nhiều phiên bản hàng tồn tại để reader cũ tiếp tục đọc dữ liệu phù hợp. Nhưng những phiên bản cũ không thể giữ mãi vô hạn.

PostgreSQL sử dụng `VACUUM` để thu hồi không gian và dọn các phiên bản không còn cần thiết theo quy tắc visibility.

### 25.1. Vì sao snapshot lâu cản trở dọn phiên bản cũ?

Giả sử:

```text
t1   A bắt đầu REPEATABLE READ, SELECT account 101 = 500
t2   B UPDATE account 101 = 600; COMMIT
t3   B UPDATE account 101 = 700; COMMIT
t4   B UPDATE account 101 = 800; COMMIT
t5   A vẫn đang mở và cần nhìn thấy 500
```

Tại `t5`, PostgreSQL cần giữ phiên bản phù hợp với snapshot cũ của A. Nếu VACUUM xóa tất cả những phiên bản đó khi A còn cần, A sẽ không thể đọc đúng snapshot của mình.

Khi nhiều transaction giữ snapshot lâu, PostgreSQL có thể chưa thu hồi được một số phiên bản cũ, dẫn đến:

- Tăng số lượng dead tuples.
- Tăng kích thước bảng/index theo thời gian (*bloat*).
- Tăng chi phí truy vấn và VACUUM.
- Áp lực lưu trữ hoặc độ trễ vận hành.

### 25.2. READ COMMITTED cũng có thể gây vấn đề

Đừng kết luận chỉ REPEATABLE READ mới ảnh hưởng VACUUM.

Một statement SELECT chạy lâu ở READ COMMITTED vẫn có snapshot cần giữ trong suốt statement đó. Một số transaction còn mở hoặc trạng thái chờ khác cũng có thể duy trì các ràng buộc về cleanup.

Tuy nhiên, nhiều câu lệnh ngắn ở READ COMMITTED thường có cơ hội dùng snapshot mới, thay vì cố định một snapshot từ truy vấn đầu đến cuối transaction như REPEATABLE READ.

### 25.3. `idle in transaction` đặc biệt nguy hiểm

Một ứng dụng mở transaction rồi để connection ở trạng thái idle:

```text
BEGIN REPEATABLE READ
SELECT ... -> thiết lập snapshot
Ứng dụng chờ người dùng phản hồi 20 phút
COMMIT
```

có thể giữ snapshot/khóa/tài nguyên không cần thiết.

Giao dịch nên ngắn và có biên giới rõ ràng. Không giữ snapshot của báo cáo trong khi chờ người dùng xem hoặc cuộn giao diện.

## 26. Quan sát transaction lâu bằng `pg_stat_activity`

Một truy vấn theo dõi trong PostgreSQL:

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Những cột quan trọng:

| Cột | Ý nghĩa khái quát |
| --- | --- |
| `pid` | ID tiến trình backend |
| `state` | Tình trạng session: active, idle in transaction... |
| `xact_start` | Thời điểm transaction bắt đầu |
| `transaction_age` | Khoảng thời gian transaction đã mở |
| `backend_xmin` | Mốc transaction ID liên quan đến snapshot horizon mà backend đang giữ, khi có |
| `wait_event_type` / `wait_event` | Thông tin đang chờ điều gì |
| `query` | Câu SQL gần đây/đang chạy, phụ thuộc trạng thái và quyền |

**Cảnh báo:** `xact_start` không chứng minh snapshot bắt đầu đúng lúc đó. Ở REPEATABLE READ, snapshot có thể chỉ xuất hiện khi câu truy vấn đầu tiên thực sự cần nó.

`backend_xmin` có thể là NULL khi backend không giữ mốc snapshot theo tình huống hiện tại. Không dùng riêng một giá trị NULL/khác NULL để kết luận toàn bộ nguyên nhân bloat.

### 26.1. Quyền giám sát

Tùy quyền truy cập, bạn có thể không xem đầy đủ thông tin của mọi session. Cột `query` có thể chứa dữ liệu nhạy cảm. Chỉ dùng thông tin giám sát theo quyền và chính sách hệ thống.

### 26.2. Timeout cho transaction idle

Kiểm tra:

```sql
SHOW idle_in_transaction_session_timeout;
```

PostgreSQL có thể cấu hình timeout để kết thúc session ở trạng thái idle trong transaction quá lâu.

Một ví dụ đặt giới hạn cục bộ cho câu SQL trong transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

`statement_timeout` giới hạn statement, còn `lock_timeout` giới hạn thời gian chờ khóa; chúng **không tương đương** `idle_in_transaction_session_timeout`. Cần chọn cấu hình theo nhu cầu vận hành, không bật tùy tiện mức quá thấp gây nhiều lỗi.

## 27. Snapshot và transaction trong Java/JDBC

Một ứng dụng Java dùng JDBC thường có nhiều query chạy qua cùng một `Connection`.

Điều quan trọng là:

- `Connection` có trạng thái autocommit.
- Isolation level cần được cấu hình trước khi transaction bắt đầu đọc/sửa dữ liệu.
- Nhiều query cần dùng **cùng connection và cùng transaction** nếu phải dùng chung snapshot.

### 27.1. Ví dụ báo cáo đọc cùng snapshot

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SnapshotReportService {
    private final DataSource dataSource;

    public SnapshotReportService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printPaidOrdersReport() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            connection.setReadOnly(true);
            connection.setAutoCommit(false);

            try {
                long paidCount;
                try (PreparedStatement statement =
                         connection.prepareStatement(
                             "SELECT COUNT(*) FROM " +
                             "mvcc_snapshot_lab.orders " +
                             "WHERE status = 'PAID'"
                         );
                     ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    paidCount = rs.getLong(1);
                }

                BigDecimal paidAmount;
                try (PreparedStatement statement =
                         connection.prepareStatement(
                             "SELECT COALESCE(SUM(amount), 0) FROM " +
                             "mvcc_snapshot_lab.orders " +
                             "WHERE status = 'PAID'"
                         );
                     ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    paidAmount = rs.getBigDecimal(1);
                }

                System.out.println("Paid orders: " + paidCount);
                System.out.println("Paid amount: " + paidAmount);

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Hai SELECT được chạy trên **một connection** với `TRANSACTION_REPEATABLE_READ` và autocommit tắt, nên chúng chia sẻ tầm nhìn MVCC đã được thiết lập cho transaction.

### 27.2. Chú ý thứ tự cấu hình JDBC

Nên cấu hình isolation, chế độ read-only và autocommit **trước khi chạy query**. Một số driver/pool có những quy tắc riêng về việc đặt isolation khi transaction đã bắt đầu.

Trong một framework transaction management, thường cần dùng annotation/configuration của transaction manager thay vì tự gọi `setAutoCommit` hoặc `commit` bên trong một transaction đã được framework quản lý.

### 27.3. Hai connection không tự dùng chung snapshot

Sai về kỳ vọng:

```text
Connection A -> SELECT COUNT(*) (REPEATABLE READ)
Connection B -> SELECT SUM(*)   (REPEATABLE READ)
```

Nếu A/B mở hai transaction riêng, mỗi transaction có thể thiết lập snapshot tại thời điểm khác nhau. Cùng isolation level **không đảm bảo cùng snapshot giữa hai connection**.

Nếu thật sự cần một snapshot chia sẻ giữa nhiều connection, xem **export/import snapshot** ở phần 24; nếu không, dùng cùng một connection thường đơn giản hơn.

### 27.4. Không giữ transaction mở khi gọi API bên ngoài

Nếu sau câu SELECT đầu tiên ứng dụng gọi một HTTP API kéo dài 30 giây rồi mới chạy câu SELECT thứ hai, transaction REPEATABLE READ sẽ giữ snapshot trong thời gian chờ đó.

Thường tốt hơn là **hoàn thành các lần đọc cần thiết trước**, commit rồi gọi API/định dạng tài liệu ngoài transaction, trừ khi kiến trúc nghiệp vụ yêu cầu khác và có biện pháp kiểm soát.

## 28. Một snapshot cho nhiều trang kết quả: điều kiện và giới hạn

Một ứng dụng export hàng triệu bản ghi theo nhiều trang có thể dùng transaction REPEATABLE READ để tránh dữ liệu thay đổi giữa các trang.

### 28.1. Ví dụ phân trang có thứ tự xác định

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 0;

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 100;

COMMIT;
```

Nếu cùng một snapshot và một `ORDER BY` ổn định, việc transaction khác INSERT đơn mới sau snapshot không tự làm dịch tập dữ liệu nhìn thấy giữa hai SELECT trong transaction này.

### 28.2. Nhưng OFFSET có chi phí

Ở bảng lớn, `OFFSET` sâu có thể khiến PostgreSQL phải xử lý nhiều hàng để bỏ qua. **Keyset pagination** theo `order_id` thường hữu ích:

```sql
SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
WHERE order_id > 1000
ORDER BY order_id
LIMIT 100;
```

Nhưng khi ứng dụng phát **nhiều HTTP request độc lập** theo thời gian, chúng thường là **nhiều transaction khác nhau**. Keyset pagination giúp ổn định thứ tự theo khóa nhưng **không tự bảo đảm cùng snapshot** qua các request.

Nếu cần export nhất quán toàn bộ và thời gian chạy dài, cân nhắc streaming cursor, backup/export chuyên dụng hoặc quy trình batch được thiết kế cho snapshot và chi phí duy trì transaction.

### 28.3. Không phải giữ một transaction suốt nhiều giờ là tối ưu

Snapshot ổn định giúp tránh lệch trang do ghi đồng thời, nhưng giữ transaction mở lâu có thể ảnh hưởng VACUUM và tài nguyên. Hãy cân bằng:

- Độ nhất quán yêu cầu.
- Dung lượng dữ liệu.
- Thời gian export.
- Khả năng restart/resume.
- Chi phí giữ snapshot.
- Kiến trúc đọc từ replica hoặc snapshot/materialization.

## 29. Đọc từ standby/replica có một ngữ cảnh snapshot khác

Nếu ứng dụng đọc dữ liệu từ **read replica**, cần phân biệt:

1. Snapshot MVCC được thiết lập **trên node đang chạy query**.
2. Tiến độ WAL được replica **nhận và áp dụng**.
3. Mức độ trễ so với primary.

Một snapshot REPEATABLE READ trên replica có thể nhất quán với trạng thái replica, nhưng **không đồng nghĩa replica đã nhận mọi transaction vừa commit ở primary**.

### 29.1. Ví dụ về độ trễ replication

```text
Primary:
  COMMIT đơn hàng #1005

Standby:
  Chưa replay WAL tương ứng

Ứng dụng:
  BEGIN REPEATABLE READ trên Standby
  SELECT ... -> chưa thấy #1005
```

Đó có thể là hành vi bình thường của replica bất đồng bộ, không nhất thiết là bug MVCC.

### 29.2. Xung đột với cleanup trên standby

Trên hot standby, truy vấn đọc lâu có thể xung đột với việc replay một số hoạt động cleanup WAL từ primary. PostgreSQL có các chính sách và cấu hình để giải quyết xung đột replay, có thể dẫn đến việc hủy query trên standby.

Vì thế một giao dịch read-only trên replica không tự có quyền giữ snapshot vô thời hạn. Cần xem thời lượng report và các chính sách vận hành như `max_standby_streaming_delay` hoặc `hot_standby_feedback` nếu phù hợp.

### 29.3. Đọc nhất quán không có nghĩa đọc mới nhất

Một báo cáo trên replica có thể là:

- Nhất quán **trong snapshot**.
- Nhưng chậm **về thời điểm phản ánh dữ liệu primary**.

Khi thiết kế dashboard hoặc hệ thống đọc sau ghi (*read-your-writes*) qua nhiều node, phải xét cả replication lag và routing, không chỉ isolation level.

## 30. Snapshot theo transaction và giới hạn đối với nghiệp vụ cập nhật

Có một ngộ nhận: “Chỉ cần REPEATABLE READ thì mọi nghiệp vụ nhiều bước tự an toàn”.

Không đúng.

### 30.1. Snapshot cố định không bảo vệ mọi bất biến nhiều hàng

Ví dụ write skew cho hai bác sĩ cho thấy hai transaction REPEATABLE READ có thể cùng quan sát trạng thái hợp lệ và sửa hai hàng khác nhau để tạo kết quả cuối vi phạm quy tắc.

### 30.2. Đọc snapshot cũ rồi quyết định cập nhật có thể không còn phù hợp

Giả sử ứng dụng đọc “số lượng đơn đang mở” tại snapshot cũ rồi dựa vào đó cho phép mở đơn mới. Nếu một transaction khác cũng làm tương tự, hai giao dịch có thể cùng đưa ra quyết định sai đối với giới hạn tổng số đơn.

Các hướng thường dùng:

- Ràng buộc database thể hiện được bất biến, nếu có.
- Cập nhật điều kiện nguyên tử trên một hàng điều phối.
- Khóa những tài nguyên cần bảo vệ theo quy tắc phù hợp.
- `SERIALIZABLE` cùng retry toàn transaction.
- Thiết kế dữ liệu để hạn chế trạng thái dư thừa khó bảo vệ.

### 30.3. Không dùng `SELECT FOR UPDATE` trên query tổng hợp rồi mặc định đã khóa phạm vi

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'NEW';
```

Đây là một phép đếm. Nó **không khóa tất cả các hàng tương lai** có thể được chèn và thỏa điều kiện.

Nếu quy tắc nghiệp vụ là “không được quá N đơn NEW”, chỉ đếm hiện tại rồi INSERT trong READ COMMITTED hoặc REPEATABLE READ chưa đủ để ngăn hai transaction cùng đọc dưới ngưỡng rồi cùng chèn.

Cần một cơ chế phối hợp thực sự, thường là ràng buộc mô hình khác, hàng giữ bộ đếm có khóa hoặc SERIALIZABLE.

## 31. Retry transaction khi có `40001`

Một transaction ở `REPEATABLE READ` hoặc `SERIALIZABLE` có thể báo:

```text
SQLSTATE 40001: serialization_failure
```

Ứng dụng không nên coi lỗi này là một “SELECT thất bại, cứ đọc lại trong transaction cũ”.

### 31.1. Thuật toán retry đúng

```text
attempt = 0

while attempt < max_attempts:
    attempt += 1
    mở transaction MỚI
    chọn isolation thích hợp
    đọc dữ liệu từ snapshot MỚI
    kiểm tra bất biến nghiệp vụ
    thực hiện thay đổi
    COMMIT

    nếu thành công:
        trả kết quả

    nếu SQLSTATE = 40001:
        ROLLBACK transaction cũ
        chờ một khoảng backoff/jitter
        thử lại TOÀN BỘ logic từ đầu

    nếu lỗi không thể retry:
        ROLLBACK
        trả lỗi phù hợp

nếu quá số lần cho phép:
    trả lỗi có thể quan sát và điều tra
```

Đây là **pseudocode**, không phải PL/pgSQL hoặc SQL thực thi trực tiếp.

### 31.2. Không retry mỗi câu UPDATE

Nếu A đọc số liệu và ra quyết định trên snapshot S1, rồi bị `40001`, việc chỉ chạy lại câu `UPDATE` có thể bỏ qua các quyết định dựa trên dữ liệu cũ. Retry phải bao gồm **đọc lại** và **tính lại quyết định**.

### 31.3. Giới hạn tác dụng phụ bên ngoài transaction

Nếu logic transaction gửi email hoặc gọi API thanh toán giữa lúc đọc và commit, retry có thể làm các side effect đó xảy ra nhiều lần. PostgreSQL rollback **không tự rollback email**.

Dùng transactional outbox, idempotency key hoặc mô hình phù hợp nếu cần phối hợp hệ thống ngoài.

### 31.4. Deadlock có thể cần retry tương tự

Ngoài `40001`, `40P01` là lỗi **deadlock detected**. Khi nghiệp vụ cho phép, có thể retry toàn transaction sau rollback theo chính sách có giới hạn.

Không retry mù quáng mọi SQLSTATE: lỗi vi phạm CHECK, foreign key hoặc input sai thường cần sửa dữ liệu/quy tắc, không tự hết sau vài lần chờ.

## 32. Những lỗi thường gặp khi hiểu snapshot PostgreSQL

| Ngộ nhận / lỗi | Vì sao không đúng? | Cách nghĩ hoặc xử lý |
| --- | --- | --- |
| `BEGIN` luôn cố định snapshot tại thời điểm BEGIN | Snapshot REPEATABLE READ thường thiết lập ở truy vấn cần snapshot đầu tiên | Xác định mốc query đầu thực tế |
| `READ COMMITTED` dùng một snapshot cho cả transaction | Nó thường dùng snapshot theo từng statement | Dùng REPEATABLE READ khi cần nhiều SELECT nhất quán |
| `READ UNCOMMITTED` cho phép dirty read | PostgreSQL triển khai như READ COMMITTED | Không kỳ vọng đọc dữ liệu chưa commit |
| Cùng transaction thì hai SELECT luôn giống nhau | Ở READ COMMITTED có thể có commit giữa hai statement | Hiểu mức isolation và snapshot |
| Cùng một SELECT có thể đọc hai snapshot khi B commit giữa chừng | SELECT thông thường đọc từ tầm nhìn statement phù hợp | Tách biệt một statement với nhiều statement |
| `REPEATABLE READ` là “đóng băng dữ liệu, kể cả own writes” | Transaction vẫn thấy thay đổi của chính nó | Phân biệt own writes với commit từ transaction khác |
| Snapshot của REPEATABLE READ luôn thấy dữ liệu mới nhất | Nó cố ý giữ tầm nhìn đã thiết lập | Mở transaction mới nếu cần snapshot mới |
| Không có phantom nghĩa là SERIALIZABLE | PostgreSQL REPEATABLE READ ngăn phantom nhưng có thể write skew | Dùng SERIALIZABLE/khóa/ràng buộc khi cần |
| SERIALIZABLE không bao giờ lỗi | SSI có thể hủy transaction để tránh anomaly | Chuẩn bị rollback và retry toàn transaction |
| UPDATE trong READ COMMITTED luôn thao tác đúng bản snapshot đầu câu mà không xét lại | Hàng khóa/cập nhật đồng thời có thể được đánh giá lại sau khi chờ | Hiểu DML, row locking và WHERE recheck |
| REPEATABLE READ cập nhật hàng do B vừa đổi vẫn tự thành công | Có thể báo `40001` | Retry transaction mới |
| `SELECT FOR UPDATE` giống SELECT thường | Nó cần khóa và có quy tắc xung đột | Dùng đúng khi muốn phối hợp ghi |
| Cứ đọc `now()` là biết snapshot đang dùng | `now()` là transaction timestamp, không phải MVCC snapshot | Phân biệt thời gian và visibility |
| `pg_current_snapshot()` có cùng chuỗi nghĩa hai câu dùng một object snapshot | Biểu diễn có thể giống khi trạng thái XID không đổi | Test bằng visibility hai session |
| `xmin` là thời gian tạo hàng | Là thông tin transaction ID, không phải datetime | Không dùng làm timestamp nghiệp vụ |
| `xmax != 0` chắc chắn hàng đã xóa | `xmax` còn liên quan locking và chi tiết MVCC | Không dùng làm bộ lọc nghiệp vụ |
| Snapshot giữ được để đọc lại sau một tuần | Exported snapshot chỉ có hiệu lực nhập trong thời gian exporter còn mở | Dùng history/backup cho dữ liệu quá khứ |
| Hai connection REPEATABLE READ luôn dùng cùng snapshot | Chúng là hai transaction riêng | Cùng connection hoặc export/import snapshot |
| Báo cáo read-only giữ snapshot cả giờ không có chi phí | Transaction lâu có thể giữ MVCC horizon/cản trở VACUUM | Giữ transaction ngắn |
| Snapshot trên replica luôn có mọi commit primary | Replica có thể trễ WAL | Xem replication lag và consistency requirement |
| Isolation đủ để bảo vệ mọi bất biến nghiệp vụ | Transaction vẫn cần kiểm tra, ràng buộc và cập nhật đúng | Thiết kế nguyên tử/cô lập theo bất biến |
| Chỉ retry câu bị lỗi 40001 | Quyết định trên snapshot cũ không còn hợp lệ | Retry toàn transaction |
| Read-only transaction tự khóa bảng ngăn writer | MVCC giúp đọc mà không cần khóa writer trong nhiều tình huống | Đọc nhất quán không đồng nghĩa chặn ghi |
| Dùng `ORDER BY` cuối SELECT để chọn snapshot | ORDER BY sắp kết quả, không quyết định visibility | Snapshot do transaction/isolation quyết định |

## 33. Bài tập thực hành có đáp án

Các bài tập dùng schema `mvcc_snapshot_lab`. Những bài cần hai session chỉ nên chạy trên database thử nghiệm và khôi phục dữ liệu trước mỗi lần so sánh.

### Bài 1. READ COMMITTED: cùng transaction, hai lần đọc

A đọc balance 500. B cập nhật thành 600 rồi commit. A đọc lại trong cùng transaction READ COMMITTED. Kết quả?

**Đáp án:** A có thể thấy **600** ở SELECT thứ hai, vì statement mới lấy snapshot mới sau commit B.

### Bài 2. REPEATABLE READ: cùng lịch giao dịch

A mở REPEATABLE READ, SELECT balance 500, sau đó B commit balance 600. A SELECT lại. Kết quả?

**Đáp án:** vẫn **500**, vì A đã chọn snapshot trước khi B commit.

### Bài 3. BEGIN trước B COMMIT, nhưng A chưa SELECT

```text
A: BEGIN ISOLATION LEVEL REPEATABLE READ
B: UPDATE balance=600; COMMIT
A: SELECT balance lần đầu
```

**Đáp án:** A thường thấy **600**, vì snapshot REPEATABLE READ được thiết lập khi A chạy câu truy vấn cần snapshot đầu tiên, không mặc định đúng lúc BEGIN.

### Bài 4. B chưa COMMIT thì A thấy gì?

B đã UPDATE 600 nhưng chưa COMMIT, A SELECT từ một transaction khác.

**Đáp án:** không dirty-read 600. A nhìn phiên bản phù hợp theo snapshot, ví dụ 500 đã commit.

### Bài 5. PostgreSQL READ UNCOMMITTED có đọc được dữ liệu chưa commit không?

**Đáp án:** không. PostgreSQL xử lý mức này như READ COMMITTED.

### Bài 6. READ COMMITTED có phantom không?

A đếm hai đơn PAID; B chèn một đơn PAID rồi commit; A đếm lại.

**Đáp án:** A có thể thấy **ba đơn**, vì statement thứ hai dùng snapshot mới.

### Bài 7. REPEATABLE READ có phantom read như vậy không?

**Đáp án:** không với các truy vấn đọc thông thường theo snapshot PostgreSQL: A vẫn thấy hai đơn trong transaction đã thiết lập snapshot trước B commit.

### Bài 8. Transaction REPEATABLE READ có thấy chính UPDATE của mình không?

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 25.00
WHERE account_id = 202;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;

ROLLBACK;
```

**Đáp án:** có, câu SELECT thấy giá trị do chính transaction cập nhật, ví dụ 225.00 nếu bắt đầu từ 200.00. ROLLBACK hủy thay đổi.

### Bài 9. Tại sao UPDATE trong REPEATABLE READ có thể lỗi `40001`?

A đã thiết lập snapshot rồi B cập nhật cùng hàng và commit; sau đó A muốn UPDATE hàng đó.

**Đáp án:** vì phiên bản hàng mới được commit sau snapshot của A. PostgreSQL có thể từ chối cập nhật xung đột bằng serialization failure thay vì tự ghép trạng thái ngoài snapshot.

### Bài 10. UPDATE tồn kho một đơn vị bằng READ COMMITTED

```sql
UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING available;
```

Nếu hai transaction cùng bán một sản phẩm còn 1, điều gì cần kiểm tra?

**Đáp án:** một transaction có thể giảm còn 0, transaction còn lại sau khi chờ/đánh giá lại điều kiện cập nhật **0 hàng**. Ứng dụng phải kiểm tra `RETURNING` hoặc số hàng cập nhật để biết bán thành công.

### Bài 11. Vì sao `SELECT FOR UPDATE` không giống SELECT thông thường?

**Đáp án:** nó yêu cầu khóa hàng, nên có thể chờ transaction ghi khác và xử lý hàng sau khi khóa được giải phóng; SELECT thông thường đọc từ MVCC snapshot mà thường không chờ khóa ghi chỉ để đọc.

### Bài 12. REPEATABLE READ có phải SERIALIZABLE không?

**Đáp án:** không. Nó giữ snapshot ổn định nhưng vẫn có thể write skew. SERIALIZABLE thêm cơ chế SSI để ngăn lịch không tuần tự hóa được.

### Bài 13. Hai bác sĩ cùng nghỉ là loại bất thường nào?

**Đáp án:** **write skew**: hai transaction cùng đọc số bác sĩ đang trực là 2, nhưng cập nhật hai hàng khác nhau thành FALSE, khiến kết quả cuối không còn người trực dù mỗi transaction từng thấy trạng thái hợp lệ.

### Bài 14. Vì sao SERIALIZABLE có thể báo 40001?

**Đáp án:** PostgreSQL phát hiện lịch phụ thuộc có thể dẫn đến serialization anomaly, nên hủy một transaction để giữ tính tương đương tuần tự.

### Bài 15. Khi gặp `40001`, có thể retry riêng câu UPDATE không?

**Đáp án:** không. Phải rollback và chạy lại **toàn bộ transaction** từ bước đọc điều kiện nghiệp vụ, vì snapshot và quyết định trước đó có thể đã cũ.

### Bài 16. Có thể đọc ba metric nhất quán trong một SELECT không?

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount,
    COUNT(*) AS all_count
FROM mvcc_snapshot_lab.orders;
```

**Đáp án:** các metric thuộc cùng một statement và đọc từ snapshot phù hợp của statement đó.

### Bài 17. Ba SELECT riêng trong READ COMMITTED có cùng snapshot không?

**Đáp án:** không được bảo đảm. Nếu transaction khác commit giữa các SELECT, chúng có thể thấy các tập dữ liệu khác nhau.

### Bài 18. Mẫu transaction để chạy nhiều báo cáo từ một snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
SELECT SUM(amount) FROM mvcc_snapshot_lab.orders;

COMMIT;
```

**Đáp án:** đây là mẫu phù hợp để hai SELECT có tầm nhìn chung trong một transaction read-only.

### Bài 19. `READ ONLY` có làm transaction ngăn mọi UPDATE từ session khác không?

**Đáp án:** không. Nó hạn chế thao tác ghi của transaction hiện tại; các session khác vẫn có thể ghi theo cơ chế lock/MVCC.

### Bài 20. `SERIALIZABLE READ ONLY DEFERRABLE` có tác dụng gì?

**Đáp án:** transaction có thể chờ ở đầu để lấy một safe snapshot phù hợp, giúp tránh phải retry một transaction read-only dài vì xung đột serialization. Nó không phải tùy chọn cần bật cho mọi query.

### Bài 21. `now()` có phải MVCC snapshot timestamp không?

**Đáp án:** không. `now()` là transaction timestamp; `statement_timestamp()` và `clock_timestamp()` có ý nghĩa khác. MVCC snapshot dựa trên thông tin transaction visibility, không phải chỉ một timestamp.

### Bài 22. `pg_current_snapshot()` trả cái gì?

```sql
SELECT pg_current_snapshot();
```

**Đáp án:** giá trị kiểu `pg_snapshot` mô tả tầm nhìn transaction ID đang dùng. Nó không trả một thời điểm lịch hoặc bản sao bảng.

### Bài 23. Có thể dùng `xmin` làm ngày tạo đơn không?

**Đáp án:** không. `xmin` liên quan transaction ID tạo tuple, không phải `created_at` nghiệp vụ. Dùng cột timestamp do schema/ứng dụng quản lý.

### Bài 24. Có nên dựa vào `xmax != 0` để kết luận hàng đã xóa?

**Đáp án:** không. `xmax` có các ý nghĩa nội bộ gồm cả thông tin khóa hàng, nên không phải cờ xóa đơn giản cho ứng dụng.

### Bài 25. Export snapshot có dùng lại được sau một tháng?

**Đáp án:** không. Snapshot export chỉ còn khả dụng để import trong thời gian transaction xuất chưa kết thúc. Muốn lịch sử lâu dài cần cơ chế khác.

### Bài 26. Import snapshot phải làm trước hay sau SELECT đầu tiên?

**Đáp án:** phải làm **trước** câu truy vấn đầu trong transaction nhập và dùng isolation phù hợp, ví dụ REPEATABLE READ.

### Bài 27. Vì sao hai connection REPEATABLE READ có thể đọc khác nhau?

**Đáp án:** mỗi connection mở transaction riêng và chọn snapshot ở thời điểm khác nhau. Cùng isolation level không có nghĩa cùng snapshot. Có thể dùng cùng connection hoặc cơ chế export/import nếu thực sự cần đồng bộ.

### Bài 28. Snapshot lâu ảnh hưởng VACUUM thế nào?

**Đáp án:** nó có thể giữ những phiên bản hàng cũ vẫn cần cho reader, khiến VACUUM chưa dọn được và tạo áp lực bloat/tài nguyên.

### Bài 29. `xact_start` có bằng thời điểm snapshot không?

**Đáp án:** không nhất thiết. Transaction có thể BEGIN trước khi SELECT đầu tiên thiết lập snapshot REPEATABLE READ.

### Bài 30. Đọc trên replica REPEATABLE READ có luôn thấy commit mới ở primary không?

**Đáp án:** không. Replica có thể chậm replay WAL; snapshot nhất quán trên replica có thể không chứa commit gần đây ở primary.

### Bài 31. Tại sao READ COMMITTED có thể hiển thị số dashboard lệch giữa hai truy vấn?

**Đáp án:** hai câu SELECT riêng có thể dùng hai snapshot khác nhau. Có thể gom metric trong một SELECT hoặc dùng REPEATABLE READ READ ONLY cho cả báo cáo.

### Bài 32. Một transaction REPEATABLE READ mở lâu có luôn tốt hơn không?

**Đáp án:** không. Nó có thể làm báo cáo nhìn dữ liệu cũ trong thời gian dài, đồng thời giữ snapshot gây áp lực VACUUM. Nên giữ transaction ngắn và giới hạn thời lượng báo cáo.

### Bài 33. Làm thế nào thay đổi isolation an toàn?

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
COMMIT;
```

**Đáp án:** cấu hình isolation phải diễn ra trước khi transaction đã chạy câu truy vấn/sửa dữ liệu đầu tiên. Một cách khác là chỉ định ngay trong `BEGIN`.

### Bài 34. READ COMMITTED UPDATE có thể cập nhật 0 hàng dù WHERE đúng lúc bắt đầu không?

**Đáp án:** có thể. Nếu transaction khác cập nhật hàng trong lúc giữ khóa, PostgreSQL có thể chờ rồi đánh giá lại WHERE trên phiên bản mới được commit. Điều kiện trước kia đúng có thể trở thành sai.

### Bài 35. Sự khác nhau giữa consistency của một query và của một workflow là gì?

**Đáp án:** một SELECT thông thường nhìn dữ liệu theo statement snapshot; nhưng một workflow có nhiều SELECT riêng trong READ COMMITTED có thể trộn nhiều tầm nhìn. Nếu yêu cầu cả workflow dùng cùng snapshot, cần mô hình transaction phù hợp.

## 34. Checklist khi thiết kế truy vấn cần snapshot chính xác

| Câu hỏi | Cần xác định |
| --- | --- |
| Mục tiêu là một statement hay nhiều statement? | Ảnh hưởng lựa chọn READ COMMITTED/REPEATABLE READ |
| Có dùng autocommit không? | Hai SELECT có thể nằm trong hai transaction khác nhau |
| Mức isolation đang dùng? | Kiểm tra/đặt trước truy vấn đầu |
| Snapshot phải mới hay phải ổn định? | Hai mục tiêu không đồng nghĩa |
| Transaction REPEATABLE READ đã SELECT chưa? | Snapshot có thể chưa được thiết lập tại BEGIN |
| Có session khác commit giữa hai SELECT? | READ COMMITTED có thể thấy thay đổi |
| Có cần chống phantom? | REPEATABLE READ giữ tập nhìn thấy theo snapshot |
| Transaction có tự UPDATE? | Own writes vẫn nhìn thấy |
| Có UPDATE hàng mà session khác đã sửa? | Có thể chờ/recheck hoặc `40001` tùy isolation |
| Có bất biến nhiều hàng cần bảo vệ? | REPEATABLE READ có thể write skew |
| Có dùng SERIALIZABLE? | Chuẩn bị retry toàn transaction |
| READ ONLY đã được đặt? | Nên dùng nếu báo cáo thực sự chỉ đọc |
| Có cần safe snapshot cho báo cáo dài? | Cân nhắc SERIALIZABLE READ ONLY DEFERRABLE |
| Có nhiều connection cùng đọc? | Cùng isolation không có nghĩa cùng snapshot |
| Có export/import snapshot? | Kiểm soát thứ tự import và lifetime exporter |
| Có phân trang với ORDER BY ổn định? | Snapshot không tự quyết định thứ tự |
| Query chạy trên standby? | Độ trễ replication là yếu tố độc lập |
| Transaction đọc có giữ quá lâu? | Ảnh hưởng VACUUM, bloat và snapshot age |
| Có giám sát long-running transaction? | `pg_stat_activity` và các metric liên quan |
| Có cần lịch sử dữ liệu lâu dài? | Snapshot không phải time travel |
| Có dùng cột hệ thống cho nghiệp vụ? | Tránh dùng `xmin/xmax/ctid` như dữ liệu business |
| Có test với hai session? | Xác minh tầm nhìn ở các mốc commit cụ thể |
| Có xử lý mất kết nối/lỗi commit? | Không tự kết luận commit thành công/thất bại khi mơ hồ |
| Có side effect ngoài database khi retry? | Cần outbox/idempotency nếu thích hợp |

## 35. Tổng kết

Trong PostgreSQL, MVCC cho phép mỗi truy vấn hoặc giao dịch đọc dữ liệu theo một **snapshot visibility** thích hợp mà không cần sao chép cả database cho từng phiên đọc.

Các điểm quan trọng nhất:

1. **Snapshot không phải một bản sao vật lý hay timestamp lịch.** Nó là thông tin quyết định những phiên bản hàng nào hiển thị.
2. **`READ COMMITTED` đọc theo snapshot của từng statement**. Hai SELECT trong cùng transaction có thể khác nhau nếu transaction khác commit giữa hai lệnh.
3. **`REPEATABLE READ` đọc theo snapshot ổn định cho toàn transaction** sau khi snapshot được thiết lập. Nó không tự chuyển sang dữ liệu mới được commit từ các transaction khác.
4. **`BEGIN` không nhất thiết là lúc snapshot REPEATABLE READ được chọn**; truy vấn dữ liệu đầu tiên mới là mốc cần chú ý.
5. **Transaction nhìn thấy chính những thay đổi của mình**, ngay cả khi snapshot đối với transaction khác đã cố định.
6. PostgreSQL **không dirty-read** ở READ COMMITTED hoặc READ UNCOMMITTED. READ UNCOMMITTED hoạt động như READ COMMITTED.
7. **READ COMMITTED có thể có nonrepeatable read và phantom**, còn REPEATABLE READ trong PostgreSQL không có những hiện tượng này theo snapshot thông thường.
8. **UPDATE và SELECT FOR UPDATE có cơ chế khóa/xung đột**, không thể suy luận hoàn toàn theo SELECT thông thường. READ COMMITTED có thể đánh giá lại điều kiện sau khi chờ; REPEATABLE READ có thể báo `40001` nếu hàng bị thay đổi sau snapshot.
9. **REPEATABLE READ không tự bảo vệ mọi bất biến nhiều hàng**; write skew vẫn có thể xảy ra. SERIALIZABLE dùng SSI để ngăn lịch không tuần tự hóa được và có thể yêu cầu retry.
10. **Nhiều query báo cáo cần cùng tầm nhìn** có thể dùng `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`.
11. **`SERIALIZABLE READ ONLY DEFERRABLE`** có thể chờ safe snapshot cho những báo cáo read-only có yêu cầu serializable đặc biệt.
12. **`pg_current_snapshot()`** giúp quan sát thông tin snapshot, còn `xmin/xmax` là metadata MVCC, không thay thế các cột nghiệp vụ.
13. **`pg_export_snapshot()` và `SET TRANSACTION SNAPSHOT`** hỗ trợ phối hợp nhiều connection nhưng có điều kiện thời điểm và vòng đời chặt chẽ.
14. **Snapshot lâu có chi phí**, nhất là giữ phiên bản cũ cần cho VACUUM và ảnh hưởng bloat.
15. **Snapshot nhất quán không đồng nghĩa dữ liệu mới nhất**, đặc biệt khi đọc trên replica có replication lag.

Mẫu ghi nhớ ngắn:

```sql
-- Nhiều statement có thể thấy các commit mới giữa hai lần đọc:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT ...;
SELECT ...;
COMMIT;

-- Nhiều statement đọc cùng tầm nhìn đã được thiết lập:
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT ...;
SELECT ...;
COMMIT;
```

Hai đoạn là **mẫu cú pháp**, cần thay dấu `...` bằng truy vấn thực tế.

**Quy tắc cốt lõi:** khi thiết kế một báo cáo hoặc nghiệp vụ nhiều câu SQL, đừng chỉ hỏi “có dùng transaction không?”. Hãy hỏi thêm **“mỗi câu lệnh đọc snapshot nào, snapshot được chọn khi nào, và các transaction đồng thời có thể thay đổi những bất biến nào?”**. Trả lời đúng ba câu hỏi này là nền tảng để tận dụng MVCC của PostgreSQL một cách chính xác.
