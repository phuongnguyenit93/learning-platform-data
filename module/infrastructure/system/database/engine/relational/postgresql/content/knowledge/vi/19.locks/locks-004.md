# NOWAIT, SKIP LOCKED và lựa chọn cách chờ trong PostgreSQL

Khi hai transaction muốn khóa hoặc sửa cùng một hàng, PostgreSQL thường để transaction đến sau **chờ** transaction đang giữ khóa. Cơ chế này bảo vệ tính nhất quán, nhưng không phải ứng dụng nào cũng muốn chờ vô thời hạn.

Trong một API đặt hàng, ứng dụng có thể muốn **phát hiện ngay** rằng tài nguyên đang bận để trả phản hồi và thử lại sau. Trong một hệ thống xử lý công việc nền, worker có thể muốn **bỏ qua job đang được worker khác giữ khóa**, chọn job khác đang rảnh và tiếp tục làm việc. Hai nhu cầu đó dẫn tới các lựa chọn rất quan trọng:

- **Chờ mặc định:** đợi khóa được nhả, trừ khi có deadlock hoặc timeout/cancel.
- **`NOWAIT`:** nếu không lấy được **khóa hàng** ngay, trả lỗi thay vì chờ.
- **`SKIP LOCKED`:** nếu một hàng không thể được khóa ngay, **bỏ qua hàng đó** và tiếp tục xét các hàng khác.
- **`lock_timeout`:** vẫn cho phép chờ, nhưng chỉ tới giới hạn thời gian được cấu hình.

Ví dụ:

```sql
-- Chờ hàng đang bị khóa theo hành vi mặc định.
SELECT *
FROM work_items
WHERE id = 10
FOR UPDATE;

-- Báo lỗi ngay nếu hàng không thể khóa.
SELECT *
FROM work_items
WHERE id = 10
FOR UPDATE NOWAIT;

-- Bỏ qua hàng đang bị khóa.
SELECT *
FROM work_items
WHERE status = 'PENDING'
ORDER BY id
LIMIT 5
FOR UPDATE SKIP LOCKED;
```

`work_items` là tên bảng minh họa; phần sau sẽ tạo bảng có thể chạy thực tế.

**Điểm cốt lõi:** `NOWAIT` và `SKIP LOCKED` thay đổi **cách xử lý xung đột khóa hàng** của các locking clauses như `FOR UPDATE`. Chúng không tự thay thế quản lý transaction, không tránh được mọi kiểu blocking, và đặc biệt `SKIP LOCKED` có thể tạo ra **tập kết quả không nhất quán với một truy vấn đọc thông thường**. Phải chọn theo mục tiêu nghiệp vụ.

## 1. Trước hết: row lock và table lock là hai tầng khác nhau

PostgreSQL có nhiều cơ chế khóa. Đối với chủ đề này, hãy tách:

1. **Khóa hàng (row-level lock):** bảo vệ việc cập nhật/xóa hoặc một số tương tác với hàng cụ thể.
2. **Khóa bảng (table-level lock):** bảo vệ quan hệ trước những thao tác không tương thích như một số DDL, `TRUNCATE`, lock table tường minh.
3. **Các khóa/tình trạng chờ khác:** transaction ID, advisory lock, predicate lock, I/O và nhiều tài nguyên nội bộ không đồng nghĩa với row lock.

Một câu:

```sql
SELECT *
FROM jobs
WHERE job_id = 101
FOR UPDATE;
```

không chỉ nói “khóa một hàng”. PostgreSQL còn lấy **`ROW SHARE` table-level lock** trên quan hệ được áp dụng locking clause, ngoài row-level locks đối với các hàng được chọn.

Hệ quả quan trọng:

> `NOWAIT` và `SKIP LOCKED` trong locking clause chỉ áp dụng cho **việc lấy khóa hàng**, không biến việc lấy **table-level lock** thành không chờ.

Nếu một transaction khác đang giữ khóa bảng `ACCESS EXCLUSIVE`, ví dụ do `TRUNCATE` hoặc một số DDL, câu `SELECT ... FOR UPDATE SKIP LOCKED` vẫn có thể phải **chờ ở tầng khóa bảng**, trước khi đến bước chọn và bỏ qua từng hàng.

### 1.1. Khóa SELECT thông thường

Một `SELECT` không có `FOR UPDATE` thông thường lấy `ACCESS SHARE` trên bảng và đọc dữ liệu theo MVCC. Nó không cố chiếm row-level locks để ngăn transaction khác cập nhật các hàng.

Ví dụ:

```sql
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1;
```

Khi một transaction khác đang giữ khóa hàng do `UPDATE`, truy vấn đọc bình thường thường vẫn đọc được **phiên bản đã commit** theo snapshot. Nó không phải “đợi cùng row lock” như `SELECT ... FOR UPDATE`.

### 1.2. Khóa hàng được giữ đến khi nào?

Thông thường, khóa hàng lấy bởi `SELECT ... FOR UPDATE` được giữ tới khi **transaction kết thúc** bằng `COMMIT` hoặc `ROLLBACK`.

```sql
BEGIN;

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Khóa vẫn tồn tại trong khi transaction đang mở.

COMMIT;
```

Đừng chạy một locking SELECT rồi giữ transaction mở trong lúc ứng dụng chờ người dùng, gọi API chậm hoặc tính toán bên ngoài hàng phút. Khóa có thể khiến những transaction khác bị chặn.

## 2. Các locking clauses của SELECT

PostgreSQL hỗ trợ bốn chế độ row-level locking thường gặp:

| Cú pháp | Ý nghĩa chính |
| --- | --- |
| `FOR UPDATE` | Khóa mạnh khi chuẩn bị thay đổi/xóa hàng |
| `FOR NO KEY UPDATE` | Khóa cho cập nhật mà không thay đổi những giá trị khóa quan trọng theo quy tắc PostgreSQL |
| `FOR SHARE` | Khóa chia sẻ, ngăn một số dạng thay đổi/xóa không tương thích |
| `FOR KEY SHARE` | Khóa chia sẻ yếu hơn, chủ yếu bảo vệ khóa được tham chiếu |

Ví dụ:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

Hoặc:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR NO KEY UPDATE;
```

Trong những bối cảnh phù hợp, các locking clauses đều có thể dùng biến thể `NOWAIT` hoặc `SKIP LOCKED`:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR SHARE SKIP LOCKED;
```

### 2.1. Không phải mọi khóa đều xung đột với nhau

Một số chế độ tương thích và một số xung đột:

| Khóa đang có / khóa muốn lấy | `FOR KEY SHARE` | `FOR SHARE` | `FOR NO KEY UPDATE` | `FOR UPDATE` |
| --- | :---: | :---: | :---: | :---: |
| `FOR KEY SHARE` | Có | Có | Có | Không |
| `FOR SHARE` | Có | Có | Không | Không |
| `FOR NO KEY UPDATE` | Có | Không | Không | Không |
| `FOR UPDATE` | Không | Không | Không | Không |

“Có” nghĩa là các chế độ có thể cùng tồn tại trên một hàng theo ma trận tương thích; “Không” nghĩa là có xung đột. Bảng này chỉ mô tả các **row-level lock modes**, không thay thế việc phân tích table locks, transaction isolation và các điều kiện khác.

### 2.2. Vì sao FOR NO KEY UPDATE hữu ích?

Nhiều `UPDATE` chỉ thay đổi cột thường, không thay đổi khóa được tham chiếu, và PostgreSQL có thể dùng chế độ khóa tương ứng yếu hơn `FOR UPDATE`. Trong mô hình có foreign key, điều này giúp một số kiểm tra khóa tham chiếu bằng `FOR KEY SHARE` không bị chặn không cần thiết.

Tuy nhiên, không chọn `FOR NO KEY UPDATE` chỉ vì tên nghe “nhẹ”: phải xác định **điều gì thực sự được bảo vệ** và có transaction khác thay đổi/xóa khóa hay không.

## 3. NOWAIT: báo ngay khi row lock không lấy được

Cú pháp:

```sql
SELECT column_list
FROM some_table
WHERE ...
FOR UPDATE NOWAIT;
```

Khi transaction gặp một hàng bị transaction khác giữ khóa không tương thích, `NOWAIT` yêu cầu PostgreSQL **không đợi khóa hàng đó**. PostgreSQL thường trả lỗi với SQLSTATE **`55P03`** (*lock_not_available*).

Ví dụ tình huống:

```text
Session A: BEGIN
Session A: SELECT account 1 FOR UPDATE
Session A: vẫn giữ transaction mở

Session B: SELECT account 1 FOR UPDATE NOWAIT
Session B: ERROR 55P03 (không lấy được row lock ngay)
```

**NOWAIT không có nghĩa câu SQL sẽ chạy trong 0 mili giây**. Database vẫn cần parse, plan, truy xuất dữ liệu, xử lý các bước khác, và có thể phải chờ loại khóa khác. “Không chờ” ở đây có nghĩa cụ thể là **không đợi khi gặp xung đột lấy row-level lock của locking clause**.

### 3.1. Dùng NOWAIT khi nào?

Ví dụ hợp lý:

- API quản lý một tài nguyên mà client muốn biết ngay “đang có thao tác khác”.
- Một job ưu tiên độ trễ thấp, sẵn sàng retry có backoff khi row bận.
- Transaction quản trị cần **thử lấy khóa** trước khi thực hiện một bước ngắn.
- Khi ứng dụng có thể trả trạng thái “resource busy” và thử lại an toàn.

Ví dụ **không hợp lý**: dùng `NOWAIT` để biến mọi tranh chấp ghi dữ liệu thành lỗi ngay cả khi chờ vài mili giây sẽ xử lý được. Điều đó có thể tạo retry storm, tốn CPU và giảm thông lượng.

### 3.2. Lỗi NOWAIT ảnh hưởng transaction

Nếu `SELECT ... FOR UPDATE NOWAIT` báo lỗi bên trong `BEGIN`, PostgreSQL đưa transaction hiện tại vào trạng thái lỗi. Các câu SQL sau đó thông thường không thể tiếp tục cho tới khi:

- `ROLLBACK` toàn bộ transaction, hoặc
- `ROLLBACK TO SAVEPOINT` phù hợp nếu có tạo savepoint trước câu lỗi.

Đừng bắt exception trong Java rồi tiếp tục cùng connection/transaction như thể lỗi không ảnh hưởng trạng thái transaction.

## 4. SKIP LOCKED: bỏ qua hàng đang bị khóa

Cú pháp:

```sql
SELECT column_list
FROM some_table
WHERE ...
ORDER BY ...
LIMIT ...
FOR UPDATE SKIP LOCKED;
```

Khi một hàng đáp ứng điều kiện nhưng đang bị row lock không tương thích, PostgreSQL **bỏ qua hàng đó** thay vì đợi. Các hàng khác có thể được chọn và khóa bình thường.

Ví dụ:

```text
Job #1: PENDING, worker A đang giữ khóa
Job #2: PENDING, không bị khóa
Job #3: PENDING, không bị khóa

Worker B SELECT ... LIMIT 2 FOR UPDATE SKIP LOCKED
    -> chọn #2 và #3
    -> không chờ #1
```

### 4.1. Vì sao đây là “góc nhìn không nhất quán”?

Một truy vấn đọc thông thường có thể thấy các hàng #1, #2, #3 ở snapshot. Nhưng `SKIP LOCKED` quyết định **không trả #1 vì tại thời điểm thử khóa hàng, hàng đang bị khóa**.

Do đó, kết quả phụ thuộc vào tranh chấp đồng thời, không chỉ nội dung dữ liệu đã commit. Hai lần chạy cùng điều kiện có thể trả **các tập hàng khác nhau**.

Điều này là chủ đích cho **hàng đợi công việc**: worker không cần mọi job đang chờ, chỉ cần **những job có thể nhận ngay**. Nhưng nó thường **không phù hợp cho báo cáo tài chính, tính tổng tồn kho, kiểm tra đủ hàng hoặc truy vấn cần một tập dữ liệu đầy đủ và nhất quán**.

### 4.2. SKIP LOCKED không phải “SELECT không khóa”

Những hàng **được chọn** vẫn bị khóa theo chế độ `FOR UPDATE` hoặc locking clause đã khai báo.

```sql
BEGIN;

SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;

-- Hai hàng đã chọn vẫn bị khóa cho tới COMMIT/ROLLBACK.

COMMIT;
```

Nếu worker chỉ SELECT rồi commit mà **không đánh dấu job là đã nhận**, job đó vẫn ở trạng thái PENDING và worker khác có thể nhận nó sau commit. Một hàng đợi đúng cần **đổi trạng thái nhận việc trong cùng transaction**.

## 5. Ba phương án xử lý cạnh tranh khóa

| Phương án | Khi hàng mục tiêu đang bị khóa | Kết quả thường gặp | Dùng khi |
| --- | --- | --- | --- |
| `FOR UPDATE` | Chờ tới khi có thể lấy khóa | Sau chờ, đọc/khóa hàng phù hợp hoặc có lỗi khác | Cần đúng hàng mục tiêu, chấp nhận chờ |
| `FOR UPDATE NOWAIT` | Không chờ row lock | Lỗi `55P03` nếu xung đột | Cần “thử ngay”, thất bại nhanh |
| `FOR UPDATE SKIP LOCKED` | Bỏ qua hàng khóa | Nhận hàng khác, có thể trả 0 hàng | Worker có thể xử lý phần việc khác |
| Chờ với `lock_timeout` | Chờ tới ngưỡng | Lấy khóa nếu nhả kịp, lỗi khi quá hạn | Muốn chờ có giới hạn |

Không có phương án nào mặc định tốt nhất. **Đúng hay sai phụ thuộc việc “bỏ qua đối tượng đang bận” có phù hợp nghiệp vụ hay không**.

Ví dụ, người dùng rút tiền từ đúng tài khoản #1 không thể tự chuyển sang tài khoản #2 chỉ vì #1 đang bị khóa. Với nghiệp vụ đó, `SKIP LOCKED` rất dễ sai. Nhưng một worker xử lý nhiều email chờ gửi có thể chọn job khác nếu một job đã được worker khác giữ.

## 6. Tạo database thử nghiệm: bảng tài khoản

Tất cả ví dụ có thể chạy trong PostgreSQL trên **database học tập riêng**. Không tạo dữ liệu/giữ khóa trên hệ thống sản xuất.

### 6.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS lock_wait_lab;
```

### 6.2. Bảng tài khoản

```sql
CREATE TABLE lock_wait_lab.accounts (
    account_id   INTEGER PRIMARY KEY,
    owner_name   TEXT NOT NULL,
    balance      NUMERIC(14, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO lock_wait_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Bình', 500.00),
    (3, 'Chi', 750.00);
```

Kỳ vọng:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | An | 1000.00 |
| 2 | Bình | 500.00 |
| 3 | Chi | 750.00 |

Trong bài, chỉ dùng `accounts` để quan sát lock. Đây **không phải ledger tài chính thật**; các nghiệp vụ tiền phải kiểm tra số hàng ảnh hưởng, bảo vệ số dư, idempotency và sổ giao dịch bất biến phù hợp.

## 7. Thực hành hai phiên: chờ mặc định

Mở **Session A** và **Session B** kết nối tới **cùng một database**, nhưng dùng hai connection khác nhau. Không chạy nhiều bước của hai phiên trong cùng một transaction.

**Session A – giữ khóa hàng #1:**

```sql
BEGIN;

SELECT
    account_id,
    balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Chưa COMMIT/ROLLBACK; A đang giữ row lock của account #1.
```

**Session B – thử lấy cùng khóa:**

```sql
BEGIN;

SELECT
    account_id,
    balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- B có thể chờ vì A chưa nhả khóa.
```

Tại thời điểm này, B đang đợi. Quay lại **Session A**:

```sql
COMMIT;
```

B có thể tiếp tục và lấy khóa hàng #1. Cuối cùng tại **Session B**:

```sql
COMMIT;
```

**Đừng quên kết thúc cả hai transaction** trước khi thử ví dụ tiếp theo.

### 7.1. Dùng SELECT thường thay FOR UPDATE

Lặp lại bước A, nhưng tại B chạy:

```sql
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1;
```

Thông thường câu này **không chờ khóa hàng** của `FOR UPDATE` ở A, vì SELECT không khóa có thể đọc phiên bản phù hợp với snapshot MVCC.

Điều đó không có nghĩa đọc không bao giờ chờ bất cứ thứ gì: table-level lock `ACCESS EXCLUSIVE` hoặc các tài nguyên khác vẫn có thể chặn SELECT.

## 8. Thực hành hai phiên: NOWAIT

**Session A – giữ khóa:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

**Session B – yêu cầu không chờ:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
```

Vì A đang giữ khóa không tương thích, B nhận lỗi tương tự:

```text
ERROR:  could not obtain lock on row in relation "accounts"
SQLSTATE: 55P03
```

Thông báo văn bản có thể khác theo phiên bản và điều kiện, nhưng SQLSTATE `55P03` là điểm hữu ích để ứng dụng phân loại trường hợp khóa không sẵn sàng.

**Session B – dọn transaction lỗi:**

```sql
ROLLBACK;
```

**Session A – nhả khóa:**

```sql
COMMIT;
```

Sau đó chạy lại ở B:

```sql
BEGIN;
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
COMMIT;
```

Khi không còn transaction khác giữ khóa xung đột, câu NOWAIT có thể thành công.

### 8.1. Nếu muốn xử lý lỗi rồi tiếp tục cùng transaction

Có thể dùng savepoint:

```sql
BEGIN;
SAVEPOINT before_try_lock;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

-- Nếu câu SELECT ở trên báo 55P03:
ROLLBACK TO SAVEPOINT before_try_lock;

-- Sau rollback về savepoint, transaction có thể tiếp tục.
SELECT current_database();
COMMIT;
```

**Chỉ thực thi `ROLLBACK TO SAVEPOINT` trong nhánh có lỗi.** Nếu câu SELECT thành công, ứng dụng có thể `RELEASE SAVEPOINT before_try_lock` và tiếp tục hoặc commit, tùy workflow.

Trong Java/JDBC, khi catch `SQLException` có SQLSTATE `55P03`, cần rollback transaction hoặc rollback về savepoint đã tạo trước đó, không tiếp tục chạy SQL tùy ý trong transaction bị đánh dấu lỗi.

## 9. Thực hành hai phiên: SKIP LOCKED

**Session A – giữ khóa account #1:**

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

**Session B – thử lấy tất cả các account có thể khóa ngay:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

Khi A đang giữ khóa account #1, B thường nhận:

| account_id | balance |
| ---: | ---: |
| 2 | 500.00 |
| 3 | 750.00 |

Account #1 **không xuất hiện** trong tập kết quả của B vì khóa không sẵn sàng. B đang giữ khóa trên hàng #2 và #3 cho tới khi kết thúc transaction.

**Session B:**

```sql
COMMIT;
```

**Session A:**

```sql
COMMIT;
```

Thử lại truy vấn `FOR UPDATE SKIP LOCKED` sau khi A đã commit, lần này có thể lấy được cả ba hàng.

**Lưu ý:** `SKIP LOCKED` không trả cờ “bỏ qua 1 hàng”; nó chỉ **không trả hàng đó**. Không dùng số hàng trả về để suy ra tổng số hàng thực sự thỏa `WHERE`.

## 10. NOWAIT và SKIP LOCKED không áp dụng trực tiếp cho UPDATE/DELETE

PostgreSQL hỗ trợ cú pháp khóa hàng thông qua các locking clauses của `SELECT`. Không thể gắn tùy ý:

```sql
-- KHÔNG PHẢI cú pháp PostgreSQL hợp lệ:
-- UPDATE lock_wait_lab.accounts
-- SET balance = balance + 1
-- WHERE account_id = 1
-- NOWAIT;

-- KHÔNG PHẢI cú pháp PostgreSQL hợp lệ:
-- DELETE FROM lock_wait_lab.accounts
-- WHERE account_id = 1
-- SKIP LOCKED;
```

Muốn **thử lấy khóa trước rồi UPDATE**, làm trong cùng transaction:

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

-- Chỉ đến đây nếu SELECT lấy khóa thành công.
UPDATE lock_wait_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
```

Nếu SELECT báo lỗi, ứng dụng phải rollback/rollback to savepoint và không tiếp tục UPDATE. Khi không có xung đột sau SELECT, khóa hàng được giữ tới commit nên transaction khác không thể chen vào sửa cùng hàng trước UPDATE theo cách thông thường.

### 10.1. Khóa càng lâu càng giảm concurrency

Không nên:

```text
BEGIN
SELECT ... FOR UPDATE NOWAIT
gọi HTTP API bên ngoài trong 20 giây
UPDATE ...
COMMIT
```

Trong 20 giây, nhiều request khác có thể phải chờ hoặc thất bại NOWAIT trên cùng hàng. Nếu cần liên hệ hệ thống ngoài, hãy cân nhắc phân tách workflow thành những transaction ngắn với trạng thái/reservation bền vững thay vì giữ row locks qua I/O chậm.

## 11. Lựa chọn chờ có giới hạn: lock_timeout

Không phải ứng dụng nào cũng muốn lỗi **ngay** hoặc bỏ qua hàng. Có thể muốn chờ tối đa một khoảng:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

COMMIT;
```

Nếu khóa được nhả trước giới hạn, lệnh có thể tiếp tục. Nếu thời gian chờ lấy khóa vượt giới hạn, PostgreSQL báo lỗi khóa không sẵn sàng, thường với SQLSTATE `55P03`.

`SET LOCAL` chỉ áp dụng trong transaction hiện tại. Một `SET lock_timeout = '2s'` ở cấp session có thể ảnh hưởng các statement tiếp theo của connection pool nếu không reset đúng; vì thế dùng local setting hoặc cấu hình quản lý rõ ràng thường an toàn hơn.

### 11.1. lock_timeout không đồng nghĩa NOWAIT

- `NOWAIT`: không đợi **row lock** xung đột trong locking clause.
- `lock_timeout`: cho phép đợi tới giới hạn **khi cố lấy một lock**, bao gồm các loại lock theo quy tắc PostgreSQL.
- Một statement có thể phải lấy **nhiều lock khác nhau**; `lock_timeout` áp dụng cho **mỗi lần đợi lấy lock**, không nhất thiết là ngân sách tổng thời gian của cả statement.

Ví dụ muốn tránh đợi quá lâu ở **table-level lock**, `lock_timeout` có ích hơn chỉ dựa vào `NOWAIT` trên row lock.

### 11.2. statement_timeout

`statement_timeout` giới hạn **thời gian thực thi của một statement** theo quy tắc PostgreSQL, không chỉ thời gian chờ khóa:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

COMMIT;
```

Nếu query chạy lâu do I/O, join/sort hoặc nhiều nguyên nhân khác, `statement_timeout` cũng có thể áp dụng. Lỗi thường dùng SQLSTATE `57014` (*query_canceled*), khác với lỗi lock timeout.

**Thứ tự ưu tiên:** nếu đặt `lock_timeout` lớn hơn hoặc bằng `statement_timeout`, tác dụng độc lập của lock_timeout có thể ít hoặc không phát huy trong cùng statement, vì giới hạn statement có thể xảy ra trước.

### 11.3. idle_in_transaction_session_timeout

Một session có transaction đang mở nhưng **đang idle** có thể giữ khóa không cần thiết. PostgreSQL có tham số `idle_in_transaction_session_timeout` để hủy connection idle-in-transaction quá lâu theo chính sách cấu hình.

Nó **không phải timeout riêng cho một lần chờ row lock** và không nên dùng làm phương án thay thế `lock_timeout`. Một session đang thực thi query và chờ lock không nhất thiết là “idle in transaction”.

### 11.4. deadlock_timeout

`deadlock_timeout` liên quan tới thời điểm PostgreSQL tiến hành kiểm tra deadlock sau một khoảng chờ, không phải “timeout tự hủy mọi truy vấn đang đợi khóa”. Thường do quản trị viên điều chỉnh theo workload và yêu cầu log; ứng dụng không nên dùng nó thay `lock_timeout` hoặc `statement_timeout`.

## 12. Khi NOWAIT vẫn có thể phải chờ: khóa bảng

Một chi tiết dễ bỏ sót:

```sql
SELECT *
FROM lock_wait_lab.accounts
FOR UPDATE NOWAIT;
```

Lệnh này cần lấy table-level `ROW SHARE` lock, và `NOWAIT` **không áp dụng** cho bước lấy table lock đó. Nếu session khác đang giữ `ACCESS EXCLUSIVE`:

```sql
-- Session A (demo riêng, không thực hiện trên production):
BEGIN;
LOCK TABLE lock_wait_lab.accounts IN ACCESS EXCLUSIVE MODE;
-- Chưa COMMIT.
```

thì Session B có thể phải chờ ở mức bảng trước khi đến bước NOWAIT ở từng hàng.

### 12.1. LOCK TABLE ... NOWAIT

Khi muốn thử lấy table-level lock mà không chờ, PostgreSQL hỗ trợ:

```sql
BEGIN;

LOCK TABLE lock_wait_lab.accounts
IN ROW SHARE MODE NOWAIT;

SELECT *
FROM lock_wait_lab.accounts
FOR UPDATE NOWAIT;

COMMIT;
```

Ở đây:

- `LOCK TABLE ... IN ROW SHARE MODE NOWAIT` thử lấy **table-level lock** tương ứng mà không đợi.
- `FOR UPDATE NOWAIT` thử lấy **row-level locks** mà không đợi.
- Cả hai cần được xét nếu muốn “fail fast” khi có contention ở nhiều tầng.

**Không hiểu cách này là bảo đảm transaction không bao giờ bị chặn ở bất kỳ hoạt động nào**: DDL khác, I/O, sự kiện mạng, truy cập quan hệ phụ, trigger và các khóa khác vẫn có thể ảnh hưởng.

### 12.2. Giải pháp thường thực dụng

Nếu không muốn tách thành hai câu lock rõ ràng, có thể kết hợp:

```sql
BEGIN;
SET LOCAL lock_timeout = '1s';

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

COMMIT;
```

Lúc này row lock xung đột được xử lý theo NOWAIT, còn table-level lock acquisition có giới hạn chờ theo lock_timeout. Đó là **hai cơ chế bổ sung**, không phải hai từ khóa đồng nghĩa.

## 13. Tạo bảng hàng đợi công việc

Ứng dụng điển hình của `SKIP LOCKED` là **nhiều worker cùng lấy công việc từ bảng PostgreSQL**. Bảng thử nghiệm sau có trạng thái, độ ưu tiên, thời điểm sẵn sàng, số lần thử và lease.

### 13.1. Định nghĩa bảng jobs

```sql
CREATE TABLE lock_wait_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    priority INTEGER NOT NULL DEFAULT 0,
    ready_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    lease_token BIGINT NOT NULL DEFAULT 0,
    completed_at TIMESTAMPTZ,
    last_error TEXT
);
```

Giải thích các cột:

| Cột | Mục đích |
| --- | --- |
| `job_id` | Định danh duy nhất |
| `job_type`, `payload` | Loại công việc và dữ liệu |
| `status` | Trạng thái chờ, đang chạy, thành công, thất bại |
| `priority` | Ưu tiên chọn job cao hơn trước |
| `ready_at` | Job chỉ được nhận khi đến thời điểm sẵn sàng |
| `attempt_count` / `max_attempts` | Quản lý retry có giới hạn |
| `claimed_by` | Worker đang được ghi nhận là chủ job |
| `claimed_at` / `lease_until` | Thời điểm nhận và hạn xử lý |
| `lease_token` | Số phiên bản tăng mỗi lần claim, giúp chặn worker cũ hoàn tất nhầm |
| `completed_at`, `last_error` | Trạng thái hoàn tất và chẩn đoán |

**Khóa hàng** chỉ bảo vệ giai đoạn claim bên trong transaction. **Lease và trạng thái bền vững** mới giúp worker tiếp tục xử lý sau commit mà không phải giữ transaction mở suốt thời gian chạy job.

### 13.2. Nạp sáu job

```sql
INSERT INTO lock_wait_lab.jobs
    (job_type, payload, priority, ready_at)
VALUES
    ('email', '{"recipient":"a@example.test"}'::jsonb,
     10, clock_timestamp() - INTERVAL '1 minute'),
    ('email', '{"recipient":"b@example.test"}'::jsonb,
      9, clock_timestamp() - INTERVAL '1 minute'),
    ('report', '{"month":"2026-10"}'::jsonb,
      8, clock_timestamp() - INTERVAL '1 minute'),
    ('email', '{"recipient":"c@example.test"}'::jsonb,
      5, clock_timestamp() - INTERVAL '1 minute'),
    ('report', '{"month":"2026-09"}'::jsonb,
      5, clock_timestamp() - INTERVAL '1 minute'),
    ('cleanup', '{"scope":"demo"}'::jsonb,
      2, clock_timestamp() - INTERVAL '1 minute');
```

Trên bảng mới tạo với identity chưa sử dụng, job nhận ID 1–6. Nếu bạn đã nạp nhiều lần hoặc sequence thay đổi, hãy **đọc lại các ID thực tế** thay vì mặc định ID vẫn là 1–6.

### 13.3. Index phục vụ worker

```sql
CREATE INDEX idx_lock_wait_jobs_ready
ON lock_wait_lab.jobs
    (priority DESC, ready_at, job_id)
WHERE status = 'PENDING';
```

Index partial này giúp giới hạn tìm kiếm trên các job PENDING và cung cấp các khóa thường dùng. Tuy nhiên, do quy tắc `ORDER BY priority DESC, ready_at, job_id` và điều kiện `ready_at <= now()`, planner có thể cần sort hoặc chọn kế hoạch khác theo kích thước bảng và phân bố dữ liệu.

Một index không bảo đảm `SKIP LOCKED` luôn nhanh, vì row lock, heap access, bloat, số worker, trạng thái job và concurrency đều ảnh hưởng. Cần đo workload thật.

## 14. Ví dụ hai worker dùng SKIP LOCKED

Giả sử bảng job vừa nạp và mọi job đều ở `PENDING`.

**Session A – worker A khóa job ưu tiên cao nhất:**

```sql
BEGIN;

SELECT job_id, priority, status
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, ready_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Trong schema vừa nạp, thường chọn job #1.
-- Chưa COMMIT để quan sát tranh chấp.
```

**Session B – worker B lấy job khác:**

```sql
BEGIN;

SELECT job_id, priority, status
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, ready_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Khi A đang giữ #1, B thường chọn #2.

ROLLBACK;
```

**Session A – dọn ví dụ:**

```sql
ROLLBACK;
```

Vì cả A/B chỉ SELECT và sau đó rollback, **không có job nào được chuyển trạng thái RUNNING**. Đây là thí nghiệm row-lock, không phải bộ xử lý công việc hoàn chỉnh.

### 14.1. Vì sao B không thấy job #1?

`SKIP LOCKED` bỏ qua hàng có khóa không tương thích từ A, dù trạng thái của job #1 trong dữ liệu đã commit vẫn là PENDING.

### 14.2. Vì sao không chỉ SELECT rồi trả job cho worker?

Nếu A SELECT và COMMIT trước khi đổi trạng thái, worker C có thể nhận cùng job #1 ngay sau khi khóa được nhả. Vì vậy, **việc chọn job và đánh dấu “đã nhận” phải xảy ra trong một transaction**, tốt nhất thể hiện như một thao tác claim nguyên tử.

## 15. Mẫu claim nguyên tử: CTE + UPDATE ... RETURNING

Mục tiêu: nhiều worker cùng chạy, mỗi worker lấy **tối đa hai job chưa bị khóa và sẵn sàng**, đánh dấu `RUNNING` trong cùng transaction, trả payload và token cần thiết.

```sql
BEGIN;

WITH candidates AS (
    SELECT job_id
    FROM lock_wait_lab.jobs
    WHERE status = 'PENDING'
      AND ready_at <= now()
      AND attempt_count < max_attempts
    ORDER BY priority DESC, ready_at, job_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_wait_lab.jobs AS j
SET
    status = 'RUNNING',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '2 minutes',
    attempt_count = j.attempt_count + 1,
    lease_token = j.lease_token + 1,
    last_error = NULL
FROM candidates AS c
WHERE j.job_id = c.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.payload,
    j.priority,
    j.attempt_count,
    j.lease_token,
    j.lease_until;

COMMIT;
```

### 15.1. Tại sao mẫu này tránh hai worker nhận cùng job?

1. CTE chọn những hàng `PENDING` đủ điều kiện.
2. `FOR UPDATE SKIP LOCKED` thử lấy row lock cho hàng được chọn; job đang do worker khác giữ khóa sẽ bị bỏ qua.
3. `UPDATE ... FROM candidates` đổi trạng thái các hàng **đã được khóa trong cùng transaction** sang RUNNING.
4. `RETURNING` trả danh sách công việc đã được claim cùng token.
5. `COMMIT` công bố trạng thái RUNNING; các worker khác tìm `status='PENDING'` sẽ không nhận các hàng đó khi nhìn thấy commit.

Giữa câu SELECT trong CTE và UPDATE không có “khoảng trống không khóa” để một worker khác tùy ý claim cùng hàng; khóa được giữ tới commit.

### 15.2. Tại sao phải COMMIT trước khi xử lý payload bên ngoài?

Một thiết kế dễ sai:

```text
BEGIN
SELECT job FOR UPDATE SKIP LOCKED
gửi email 30 giây
UPDATE job thành DONE
COMMIT
```

Trong suốt 30 giây, connection và row lock bị giữ. Nếu số worker lớn hoặc job xử lý lâu, transaction dài có thể làm chậm VACUUM và tăng contention.

Phương án thường tốt hơn:

```text
Transaction ngắn:
    chọn job + UPDATE status RUNNING + lease_token
    COMMIT

Xử lý bên ngoài transaction:
    gọi API / gửi email / tạo báo cáo

Transaction ngắn khác:
    UPDATE status DONE nếu worker và token còn hợp lệ
    COMMIT
```

Đây là cơ chế **claim + lease**, không phải đảm bảo exactly-once delivery. Một worker có thể crash sau khi đã thực hiện tác dụng phụ nhưng trước khi ghi DONE; cần idempotency.

### 15.3. Vì sao có attempt_count và lease_token?

- `attempt_count` tăng mỗi lần claim để giới hạn retry.
- `lease_token` tăng mỗi lần claim để xác định **phiên nhận việc**. Worker cũ với token 3 không được phép ghi DONE sau khi job đã được worker mới nhận với token 4.

Nếu job có độ trễ hoặc retry phức tạp, token nên được truyền tới downstream nơi có thể thực hiện **fencing** hoặc dùng idempotency key; chỉ kiểm tra token trong DB không tự hủy một email/API call đã được worker cũ gửi đi.

## 16. Hoàn tất job bằng token đúng

Giả sử `RETURNING` của bước claim báo:

```text
job_id = 1
claimed_by = worker-A
lease_token = 1
```

Sau khi xử lý thành công:

```sql
UPDATE lock_wait_lab.jobs
SET
    status = 'DONE',
    completed_at = clock_timestamp(),
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
RETURNING job_id, status, completed_at;
```

Kỳ vọng **đúng một hàng** nếu worker vẫn sở hữu claim hợp lệ. Nếu `RETURNING` trả **0 hàng**, worker không được coi đó là success mặc định. Có thể:

- Job đã được worker khác claim lại.
- Lease/token đã được thay đổi.
- Job đã được hoàn tất hoặc chuyển FAILED.
- Worker dùng nhầm job_id/token.

Ứng dụng cần kiểm tra trạng thái và áp quy trình retry/đối soát phù hợp.

### 16.1. Không dựa vào worker ID một mình

Một worker ID có thể được tái sử dụng sau restart, hoặc cùng worker claim lại một job lần thứ hai. Khi đó `claimed_by='worker-A'` không đủ phân biệt hai lượt.

Kiểm tra `(job_id, claimed_by, lease_token)` giúp tránh một số **stale completion**. Đối với tác dụng phụ bên ngoài, còn cần cơ chế idempotent processing và đồng bộ fencing phù hợp.

### 16.2. Heartbeat kéo dài lease

Nếu job xử lý lâu hơn dự kiến, worker có thể gia hạn lease theo định kỳ khi vẫn có quyền sở hữu:

```sql
UPDATE lock_wait_lab.jobs
SET lease_until = clock_timestamp() + INTERVAL '2 minutes'
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
  AND lease_until > clock_timestamp()
RETURNING job_id, lease_until;
```

Điều kiện chưa hết hạn chỉ là một chính sách lease minh họa; hệ thống thật phải định nghĩa giờ chuẩn, độ trễ heartbeat, failover và cách xử lý network partition.

**Không kéo dài lease vô hạn** nếu worker đã không còn thực sự chạy công việc.

## 17. Khi worker crash: thu hồi lease và nhận lại job

Nếu worker A đã commit trạng thái RUNNING rồi crash trước khi ghi DONE, row lock đã được nhả từ lâu; `SKIP LOCKED` **không tự thu hồi job** vì nó không còn thỏa `status='PENDING'`.

Do đó, hệ thống cần một **reaper/recovery job** kiểm tra lease hết hạn và chuyển job sang trạng thái có thể nhận lại.

```sql
BEGIN;

WITH expired AS (
    SELECT job_id
    FROM lock_wait_lab.jobs
    WHERE status = 'RUNNING'
      AND lease_until < clock_timestamp()
    ORDER BY lease_until, job_id
    LIMIT 50
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_wait_lab.jobs AS j
SET
    status = CASE
        WHEN j.attempt_count >= j.max_attempts THEN 'FAILED'
        ELSE 'PENDING'
    END,
    ready_at = clock_timestamp() + INTERVAL '10 seconds',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'Lease expired before completion'
FROM expired AS e
WHERE j.job_id = e.job_id
RETURNING
    j.job_id,
    j.status,
    j.attempt_count,
    j.max_attempts,
    j.lease_token;

COMMIT;
```

### 17.1. Tại sao reaper cũng dùng SKIP LOCKED?

Có thể có nhiều reaper hoặc worker cùng cập nhật một job. `SKIP LOCKED` giúp reaper **không đợi các hàng đang được transaction khác bảo vệ**, xử lý những hàng hết hạn khác trước.

Nếu một worker vừa gia hạn lease trong transaction và chưa commit, reaper không nên chiếm lock của job đó; việc bỏ qua giúp giảm tranh chấp. Ở lượt sau, điều kiện thời gian và trạng thái được đọc lại.

### 17.2. Token chống worker cũ ghi DONE, nhưng không chống được mọi side effect

Ví dụ:

1. Worker A claim job với token 3 và bắt đầu gửi email.
2. A bị mất kết nối, lease hết hạn.
3. Reaper đưa job về PENDING.
4. Worker B claim job với token 4.
5. A gửi email thành công rồi cố UPDATE DONE với token 3.

UPDATE DONE của A không được phép thay đổi hàng vì token không khớp. **Nhưng email do A gửi đã tồn tại ngoài database.** Nếu B cũng gửi email, người nhận có thể nhận hai thư.

Muốn hạn chế trùng side effect, cần **idempotency key**, hỗ trợ dedup từ external provider nếu có, hoặc thiết kế thao tác bên ngoài có thể kiểm tra/fencing. `SKIP LOCKED` chỉ giải quyết **chọn và khóa hàng trong PostgreSQL**, không đem lại exactly-once processing qua mọi hệ thống.

### 17.3. Lease time không phải transaction lock time

Hai khoảng thời gian khác nhau:

- **Row lock:** từ khi SELECT FOR UPDATE chọn job tới khi transaction claim COMMIT/ROLLBACK; nên rất ngắn.
- **Lease:** khoảng thời gian ứng dụng ghi trong cột `lease_until`, có thể dài hơn để worker xử lý công việc; nó không phải PostgreSQL row lock.

Nhầm hai loại thời gian này là nguyên nhân thường gặp của transaction kéo dài và nghẽn database.

## 18. Retry khi xử lý thất bại có kiểm soát

Nếu một worker xử lý job thất bại tạm thời, thay vì chờ lease tự hết, nó có thể cập nhật ngay:

```sql
UPDATE lock_wait_lab.jobs
SET
    status = CASE
        WHEN attempt_count >= max_attempts THEN 'FAILED'
        ELSE 'PENDING'
    END,
    ready_at = clock_timestamp() + INTERVAL '30 seconds',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'Temporary provider failure'
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
RETURNING job_id, status, attempt_count, max_attempts;
```

Nếu trả 0 hàng, có thể worker không còn sở hữu claim, hoặc job đã đổi trạng thái. Không tự ghi đè trạng thái mới của worker khác.

### 18.1. Retry có backoff và jitter

Nếu nhiều worker cùng gặp lỗi với một dịch vụ ngoài, retry tất cả sau đúng 30 giây có thể gây **thundering herd**. Trong hệ thống thật, cân nhắc exponential backoff, jitter, giới hạn concurrency và dead-letter/FAILED policy.

Ví dụ công thức ý tưởng:

```text
retry_delay = min(base_delay * 2^(attempt-1), max_delay)
             + jitter
```

Không dùng PostgreSQL `^` như phép XOR khi chuyển công thức từ Java hoặc ngôn ngữ khác. Công thức này là mô tả chiến lược; những giá trị thực phải được giới hạn để không tràn số hoặc gây retry quá lâu.

### 18.2. Tránh phát hiện timeout rồi lập tức retry nghiệp vụ không idempotent

Một worker timeout khi gọi hệ thống ngoài **không chứng minh hệ thống ngoài chưa xử lý**. Cần sử dụng idempotency key hoặc khả năng tra cứu trạng thái external operation trước khi gửi lại một thao tác có side effect.

## 19. Fairness và starvation: SKIP LOCKED không bảo đảm FIFO tuyệt đối

`ORDER BY priority DESC, ready_at, job_id` diễn đạt thứ tự ưu tiên **trong tập hàng có thể được chọn**, nhưng `SKIP LOCKED` có quyền bỏ qua hàng đang bị khóa.

Ví dụ:

```text
Job #1: priority 100, đang bị khóa nhiều phút
Job #2: priority  90, rảnh
Job #3: priority  80, rảnh
```

Worker dùng `SKIP LOCKED` có thể xử lý #2 và #3 trước #1. Thứ tự xử lý thực tế không còn là FIFO/priority tuyệt đối.

Điều đó thường **có lợi cho throughput**, nhưng không thích hợp nếu quy định nghiệp vụ buộc job trước phải hoàn tất trước job sau.

### 19.1. Starvation

Một hàng bị khóa lặp đi lặp lại hoặc job ưu tiên thấp luôn đứng sau các job ưu tiên cao mới được thêm có thể bị trì hoãn rất lâu.

Các kỹ thuật có thể cân nhắc:

- Giới hạn thời gian transaction giữ lock.
- Theo dõi tuổi job PENDING và tuổi lease RUNNING.
- Aging priority theo thời gian chờ, nhưng cần định nghĩa công bằng.
- Chia hàng đợi thành nhiều lớp hoặc partition/work queue riêng.
- Worker dành quota cho job ưu tiên thấp.
- Giới hạn batch size để không chiếm nhiều hàng một lúc.

Không giả định `SKIP LOCKED` tự đảm bảo **eventual fairness** cho mọi hàng.

### 19.2. ORDER BY và locking read trong READ COMMITTED

Trong PostgreSQL ở `READ COMMITTED`, một locking SELECT có `ORDER BY` có thể sắp xếp theo dữ liệu nhìn thấy ở một thời điểm nhưng sau khi chờ khóa lại quan sát giá trị cột đã được transaction khác cập nhật, dẫn tới kết quả cuối **không còn tuyệt đối theo thứ tự giá trị mới** trong một số tình huống.

Với `SKIP LOCKED`, vấn đề nghiệp vụ còn trực tiếp hơn: các hàng ưu tiên cao đang bị khóa được bỏ qua, vì vậy thứ tự job được claim **không phải bảng xếp hạng toàn cục bất biến**.

Nếu ứng dụng cần thứ tự nghiêm ngặt, phải thiết kế **cơ chế serialize/partition ownership hoặc transaction isolation và retry thích hợp**, chứ không thể chỉ thêm `ORDER BY` rồi coi như đảm bảo.

## 20. LIMIT, OFFSET và tính đúng của batch selection

Một queue worker thường dùng:

```sql
ORDER BY priority DESC, ready_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED
```

Ý nghĩa là **chọn tối đa 10 hàng có thể khóa** theo quy tắc của query, không có cam kết luôn đúng 10 hàng và không có cam kết đó là 10 hàng đầu tiên trong toàn database khi có contention.

### 20.1. OFFSET trong locking query là bẫy

Ví dụ:

```sql
SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY job_id
OFFSET 10
LIMIT 5
FOR UPDATE SKIP LOCKED;
```

Trong PostgreSQL, các hàng được đi qua để đáp ứng `OFFSET` **vẫn có thể bị khóa** dù không xuất hiện trong output. Điều này làm tăng contention và không có ý nghĩa tốt cho worker queue.

Vì thế, **không dùng OFFSET để chia việc theo trang** trong hệ thống claim job. Mỗi worker nên chọn một batch từ đầu tập hàng đủ điều kiện, claim rồi commit; ở lượt sau những job đã RUNNING không còn thỏa `status='PENDING'`.

### 20.2. LIMIT không ngăn mọi chi phí

PostgreSQL có thể vẫn phải đọc, lọc hoặc sắp xếp nhiều hàng để tìm được N hàng không bị khóa, đặc biệt nếu nhiều hàng bị tranh chấp hoặc index chưa phù hợp. `LIMIT 10` không có nghĩa mọi trường hợp query chỉ chạm đúng 10 tuple.

### 20.3. Khóa một số hàng rồi LIMIT ở tầng ngoài

Khi đặt locking clause **bên trong subquery** và đặt LIMIT ở một tầng ngoài khác, có thể làm thay đổi số hàng bị khóa. Ví dụ một subquery khóa rộng rồi query ngoài mới giới hạn không tương đương với `ORDER BY ... LIMIT ... FOR UPDATE SKIP LOCKED` ở cùng tầng.

Hãy dùng locking clause và LIMIT **cùng với bước chọn candidates** như mẫu claim; kiểm tra plan và số hàng khóa nếu phải viết truy vấn nhiều tầng.

## 21. JOIN nhiều bảng: FOR UPDATE OF table_alias

Một query có thể nối nhiều bảng, nhưng chỉ cần khóa hàng của bảng job.

Ví dụ tạo bảng cấu hình worker group:

```sql
CREATE TABLE lock_wait_lab.job_types (
    job_type TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO lock_wait_lab.job_types (job_type, enabled)
VALUES
    ('email', TRUE),
    ('report', TRUE),
    ('cleanup', FALSE);
```

Worker muốn claim job thuộc loại đang bật:

```sql
SELECT
    j.job_id,
    j.job_type,
    j.priority
FROM lock_wait_lab.jobs AS j
JOIN lock_wait_lab.job_types AS t
  ON t.job_type = j.job_type
WHERE j.status = 'PENDING'
  AND t.enabled = TRUE
ORDER BY j.priority DESC, j.job_id
LIMIT 5
FOR UPDATE OF j SKIP LOCKED;
```

`FOR UPDATE OF j` chỉ rõ **khóa các hàng từ bảng alias j**, không yêu cầu row locks trên `job_types` chỉ vì bảng đó xuất hiện trong JOIN.

### 21.1. Không thêm khóa mọi bảng nếu không cần

Nếu thiếu `OF j` trong một số câu JOIN, locking clause có thể áp dụng tới **nhiều bảng trong SELECT**, tạo contention ngoài ý định.

Ví dụ một hàng cấu hình `job_types('email')` được đọc bởi nhiều worker: không nên khóa độc quyền nó chỉ để claim những job email khác nhau. Dùng `OF j` giúp thể hiện đúng phạm vi hàng cần bảo vệ.

### 21.2. Với OUTER JOIN cần xem bảng nào được khóa

PostgreSQL không cho phép áp một số `FOR UPDATE` trực tiếp vào **phía nullable của outer join** vì hàng ở phía đó có thể không tồn tại thật. Khi cần khóa, hãy chỉ rõ quan hệ phù hợp bằng `OF`, hoặc tính tập candidates từ bảng chính trước rồi JOIN thông tin phụ ở bước sau.

Không dùng `LEFT JOIN` phức tạp như một cách “giấu” việc cần xác định bảng nào thực sự được khóa.

## 22. Không áp dụng locking clause tùy ý sau aggregate

Các locking clauses như `FOR UPDATE` không phù hợp ở cùng cấp truy vấn với một số cấu trúc làm mất ý nghĩa “hàng nguồn nào được khóa”, chẳng hạn `GROUP BY`, aggregate hoặc `DISTINCT` theo các hạn chế của PostgreSQL.

Ví dụ sai ý tưởng:

```sql
-- Không phải cách khóa từng job:
-- SELECT status, COUNT(*)
-- FROM lock_wait_lab.jobs
-- GROUP BY status
-- FOR UPDATE SKIP LOCKED;
```

Một hàng kết quả nhóm `COUNT(*)` có thể đại diện cho hàng nghìn hàng nguồn. PostgreSQL không thể coi hàng tổng hợp đó tương đương một row lock của một job cụ thể.

### 22.1. Đúng: chọn khóa trong truy vấn con, tổng hợp ở ngoài nếu cần

Nếu bài toán thật sự cần khóa một tập hàng rồi tính thông tin về chúng, có thể chọn **các hàng gốc có khóa định danh** trong CTE:

```sql
BEGIN;

WITH selected_jobs AS (
    SELECT
        job_id,
        job_type
    FROM lock_wait_lab.jobs
    WHERE status = 'PENDING'
    ORDER BY priority DESC, job_id
    LIMIT 5
    FOR UPDATE SKIP LOCKED
)
SELECT
    job_type,
    COUNT(*) AS selected_count
FROM selected_jobs
GROUP BY job_type;

ROLLBACK;
```

Ví dụ này đếm **các job được chọn và khóa trong transaction**, không đếm mọi job PENDING của database. Đừng dùng nó làm dashboard tổng số job đang chờ.

## 23. READ COMMITTED, REPEATABLE READ và SERIALIZABLE

Hầu hết hàng đợi công việc SQL kiểu này được thiết kế để hoạt động với **READ COMMITTED**, kết hợp claim nguyên tử, kiểm tra trạng thái và retry.

### 23.1. READ COMMITTED

Ở PostgreSQL, mỗi statement trong transaction `READ COMMITTED` có snapshot theo quy tắc riêng. Một worker:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Chọn và claim job với SKIP LOCKED.

COMMIT;
```

có thể thấy các thay đổi đã commit từ worker khác ở lượt statement tiếp theo. Khi row bị transaction khác giữ, SKIP LOCKED bỏ qua nó.

### 23.2. REPEATABLE READ và SERIALIZABLE

Ở mức cô lập cao hơn, nếu một hàng đã thay đổi kể từ snapshot và transaction cố khóa/sửa hàng đó, PostgreSQL có thể báo lỗi serialization thay vì đợi rồi tiếp tục như mong muốn.

SQLSTATE **`40001`** (*serialization_failure*) là tín hiệu ứng dụng cần **retry toàn bộ transaction** theo chiến lược idempotent phù hợp.

Không giả định SKIP LOCKED ngăn mọi serialization failure hoặc deadlock khi transaction có nhiều thao tác.

### 23.3. Vì sao không chọn SERIALIZABLE chỉ để “queue an toàn hơn”?

SERIALIZABLE là công cụ cho ràng buộc isolation, không phải phép màu làm job queue exactly-once. Nó có thể tăng transaction abort/retry trong workload tranh chấp cao; vấn đề worker crash sau side effect vẫn cần idempotency.

Chọn isolation theo bất biến của toàn transaction, sau đó kiểm chứng claim algorithm dưới load thực tế.

## 24. NOWAIT không thay thế deadlock detection

Deadlock xảy ra khi các transaction giữ khóa và chờ lẫn nhau theo chu trình.

Ví dụ:

```text
Transaction A giữ account #1, muốn khóa #2
Transaction B giữ account #2, muốn khóa #1
```

Nếu cả hai cứ chờ, PostgreSQL có deadlock detector để phát hiện và hủy một transaction, thường với SQLSTATE **`40P01`** (*deadlock_detected*).

### 24.1. Phòng deadlock bằng thứ tự khóa ổn định

Khi cần khóa nhiều tài khoản, ưu tiên lấy khóa **theo thứ tự khóa chính cố định**:

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Chỉ sau khi đã lấy những khóa cần thiết, thực hiện thay đổi.

COMMIT;
```

Thứ tự khóa ổn định giúp giảm khả năng vòng chờ khi mọi transaction tuân thủ cùng quy ước. Tuy nhiên, dưới concurrency, row locks khác, trigger/FK hoặc query plan, vẫn phải thiết kế xử lý deadlock/serialization failure.

### 24.2. NOWAIT giúp thất bại sớm, không đảm bảo không deadlock ở mọi chỗ

Nếu tất cả lần lấy row lock đều dùng NOWAIT đúng cách, các xung đột ở những bước đó thường trả lỗi thay vì đợi. Nhưng transaction vẫn có thể cần những khóa **khác** ngoài locking clause, và deadlock có thể phát sinh ở các bước update, FK hoặc DDL.

Vì vậy, vẫn cần bắt các mã lỗi `40P01` và `40001` khi phù hợp, rollback và retry có giới hạn.

## 25. Retry đúng cách khi nhận 55P03

Khi NOWAIT hoặc lock_timeout trả `55P03`, một ứng dụng có thể:

1. Rollback transaction (hoặc rollback về savepoint phù hợp).
2. Chọn **retry** hoặc trả “tài nguyên đang bận” tùy use case.
3. Nếu retry, dùng exponential backoff, jitter và giới hạn số lần.
4. Gắn idempotency key với nghiệp vụ có side effect.
5. Ghi metrics về contention, nhưng không log payload nhạy cảm vô điều kiện.

### 25.1. Pseudo-code Java/JDBC

```java
int maxAttempts = 3;
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        connection.setAutoCommit(false);

        try (PreparedStatement lockStmt =
                 connection.prepareStatement("""
                     SELECT account_id
                     FROM lock_wait_lab.accounts
                     WHERE account_id = ?
                     FOR UPDATE NOWAIT
                     """)) {
            lockStmt.setInt(1, 1);
            try (ResultSet rs = lockStmt.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalStateException("Account not found");
                }
            }
        }

        try (PreparedStatement updateStmt =
                 connection.prepareStatement("""
                     UPDATE lock_wait_lab.accounts
                     SET balance = balance + ?
                     WHERE account_id = ?
                     """)) {
            updateStmt.setBigDecimal(
                1, new java.math.BigDecimal("10.00")
            );
            updateStmt.setInt(2, 1);
            if (updateStmt.executeUpdate() != 1) {
                throw new IllegalStateException("Unexpected row count");
            }
        }

        connection.commit();
        break;
    } catch (java.sql.SQLException ex) {
        connection.rollback();
        if (!"55P03".equals(ex.getSQLState())
                || attempt == maxAttempts) {
            throw ex;
        }
        // Ứng dụng thực tế: backoff + jitter trước lượt sau.
    } catch (RuntimeException ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.setAutoCommit(true);
    }
}
```

Đoạn code giả định đã có `java.sql.Connection`, các imports JDBC và connection do ứng dụng quản lý. Đây là ví dụ minh họa phân loại `55P03`, **không phải framework retry production hoàn chỉnh**:

- Không tự gửi lại một nghiệp vụ đã có side effect bên ngoài mà thiếu idempotency.
- Khôi phục connection state cần tương thích với pool/transaction manager đang sử dụng.
- Nếu ứng dụng dùng Spring/JTA transaction management, không tự gọi `setAutoCommit`/`commit` trái với quy tắc của framework.
- Quy tắc retry `40P01`/`40001` có thể khác và thường cần retry toàn bộ transaction.

### 25.2. Có nên trả HTTP 409 hoặc 423?

Đó là **hợp đồng API** của ứng dụng, không phải quy tắc PostgreSQL bắt buộc. Có thể trả 409 Conflict, 423 Locked hoặc một mã domain cụ thể tùy thiết kế, kèm Retry-After khi phù hợp. Không lộ tên bảng/SQL/chi tiết lock nội bộ nếu client không cần.

## 26. Giám sát lock waits

Khi thấy worker queue chậm hoặc API báo nhiều `55P03`, đừng chỉ tăng timeout. Hãy xem **ai đang giữ khóa và transaction nào đang chờ**.

### 26.1. pg_stat_activity và pg_blocking_pids

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocked_by,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

`pg_blocking_pids(pid)` trả danh sách PID đang chặn backend theo thông tin PostgreSQL, hữu ích hơn việc tự suy đoán blocker chỉ từ câu SQL của session. Quyền quan sát hệ thống có thể hạn chế dữ liệu nhìn thấy.

### 26.2. pg_locks

```sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation_name,
    mode,
    granted,
    waitstart
FROM pg_locks
WHERE database = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY granted, relation::text, pid;
```

`pg_locks` ghi nhận nhiều loại khóa, nhưng **row-level lock information không phải lúc nào cũng xuất hiện như một dòng tuple lock dễ đọc**. Khi một transaction chờ hàng đã bị khóa, hệ thống có thể biểu diễn sự chờ qua `transactionid`, nên không thể chỉ dựa vào danh sách những dòng `locktype='tuple'`.

### 26.3. Các tín hiệu nên đo

| Chỉ số | Câu hỏi |
| --- | --- |
| Số 55P03 theo endpoint/job | NOWAIT hoặc lock_timeout thất bại nhiều tới mức nào? |
| Lock wait duration | Mỗi request chờ bao lâu? |
| Số hàng PENDING/RUNNING | Hàng đợi có đang tồn đọng không? |
| Tuổi job PENDING lâu nhất | Có starvation không? |
| Lease hết hạn và job bị claim lại | Worker có crash hoặc chậm không? |
| Số lần retry / FAILED | Downstream có lỗi kéo dài không? |
| Số connection idle in transaction | Có khóa bị giữ khi client không làm việc không? |
| Deadlocks / serialization failures | Cần xem lại thứ tự khóa hoặc transaction design không? |

Các chỉ số này giúp phân biệt **lỗi lock do contention bình thường** với **thiết kế giữ transaction quá lâu**.

## 27. Hiệu năng của SKIP LOCKED: không chỉ có index

Một queue có hàng trăm worker có thể gặp áp lực:

- Rất nhiều worker cùng chọn đầu index ưu tiên cao.
- Các hàng được chọn nằm trên cùng page hoặc bị cập nhật liên tục.
- CTE claim batch quá lớn làm giữ khóa nhiều hàng.
- Trạng thái RUNNING/PENDING thay đổi thường xuyên, sinh dead tuples và index maintenance.
- Nhiều job hết hạn lease cùng lúc tạo đỉnh tải reaper.
- Query dùng ORDER BY và predicate không phù hợp index.
- Transaction xử lý claim giữ mở trong khi worker làm I/O ngoài DB.

### 27.1. EXPLAIN trên locking query

```sql
EXPLAIN
SELECT job_id, priority
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
  AND ready_at <= now()
ORDER BY priority DESC, ready_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

Trong plan có thể xuất hiện node `LockRows`, `Limit`, `Sort`, `Index Scan` hoặc `Seq Scan` theo dữ liệu và thống kê. Với bảng demo chỉ vài hàng, `Seq Scan` có thể là lựa chọn tối ưu của planner.

**Lưu ý khi đo:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`EXPLAIN ANALYZE` **thực thi SELECT và cơ chế khóa**, không chỉ vẽ plan. Trên lab có thể dùng để học, nhưng không chạy tùy tiện trên production nếu query sẽ giữ row locks, tạo contention hoặc tác động đến workload.

### 27.2. B-tree không “index hóa” trạng thái khóa của từng hàng

Index giúp tìm candidate rows theo điều kiện, nhưng **row lock ownership là trạng thái đồng thời** không đơn giản là cột trong index B-tree.

Ngay cả với index rất tốt, worker vẫn có thể phải bỏ qua nhiều hàng đang bị khóa. Vì vậy, capacity planning cần xét tỷ lệ lock contention, batch size, transaction duration và số worker.

### 27.3. Batch size

- Batch quá nhỏ: nhiều round trip và transaction overhead.
- Batch quá lớn: một worker chiếm nhiều job, giảm công bằng và có thể trì hoãn worker khác.
- Claim 1–20 job có thể hợp lý ở vài workload, nhưng **không có con số đúng cho mọi hệ thống**.

Chọn batch size bằng benchmark và SLA, tránh giữ row locks qua thời gian xử lý job.

## 28. Advisory locks và NOWAIT/SKIP LOCKED

PostgreSQL còn hỗ trợ **advisory locks**, do ứng dụng tự gán ý nghĩa khóa bằng một số nguyên hoặc cặp số:

```sql
SELECT pg_try_advisory_xact_lock(12345);
```

Hàm này trả Boolean:

- `TRUE` nếu lấy được advisory lock theo yêu cầu.
- `FALSE` nếu có xung đột phù hợp và không lấy được ngay.

Đây là cơ chế “thử khóa” ở cấp advisory lock, **không phải cú pháp `NOWAIT` của `FOR UPDATE`**, và không tự khóa một hàng dựa vào PK.

### 28.1. Khi nào advisory lock phù hợp?

Ví dụ chỉ cho một worker duy nhất thực hiện **một nhiệm vụ bảo trì theo khóa logic** mà không có một hàng cụ thể cần UPDATE.

Nhưng advisory locks đòi các thành phần ứng dụng **tự tuân thủ cùng quy ước**, không thay thế constraint hoặc row locking để bảo vệ dữ liệu khỏi mọi transaction khác.

### 28.2. Không trộn nhiều loại khóa nếu chưa có thiết kế

Một hệ thống vừa sử dụng advisory locks, vừa dùng `FOR UPDATE NOWAIT`, vừa sửa nhiều bảng có FK có thể tạo những thứ tự chiếm khóa phức tạp. Nếu các transaction lấy khóa theo thứ tự khác nhau, deadlock vẫn có thể xảy ra.

Hãy chọn cơ chế đơn giản nhất bảo vệ đúng bất biến; viết thứ tự lấy khóa và quy trình retry rõ ràng.

## 29. NOWAIT/SKIP LOCKED với nghiệp vụ tài chính và tồn kho

### 29.1. Tài khoản có số dư

Nếu mục tiêu là **rút 80 từ đúng account #1**, câu:

```sql
SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE SKIP LOCKED;
```

có thể trả **0 hàng** khi account #1 đang bị transaction khác khóa. Điều đó **không có nghĩa tài khoản không tồn tại** hoặc không có tiền.

Nếu ứng dụng trả “account not found” sau khi thấy 0 hàng, đó là lỗi nghiệp vụ. Nên dùng `NOWAIT` để phát hiện bận, hoặc chờ có giới hạn nếu yêu cầu chính xác tài khoản đó.

### 29.2. Tồn kho

Một truy vấn kiểu:

```sql
SELECT product_id, stock
FROM inventory
WHERE product_id = 100
FOR UPDATE SKIP LOCKED;
```

không có nghĩa “sản phẩm hết hàng” khi kết quả rỗng. Sản phẩm có thể **đang bị khóa**. Bỏ qua hàng tồn kho bị khóa và tiếp tục cho phép đặt hàng mà không kiểm soát inventory có thể dẫn tới sai lệch.

Trong nghiệp vụ cần giữ tồn kho, có thể dùng `UPDATE ... WHERE stock >= quantity RETURNING ...` nguyên tử, hoặc khóa hàng + kiểm tra với NOWAIT/timeout theo quy tắc đã xác định.

### 29.3. Một thao tác UPDATE có điều kiện có thể đơn giản hơn

Ví dụ trừ tồn kho với schema giả định:

```sql
UPDATE inventory
SET stock = stock - 2
WHERE product_id = 100
  AND stock >= 2
RETURNING product_id, stock;
```

Khi xử lý đúng trên một bảng và transaction phù hợp, cách update có điều kiện như vậy có thể không cần một câu SELECT FOR UPDATE trước đó. Cần kiểm tra **số hàng ảnh hưởng**; không xem 0 hàng là bằng chứng duy nhất rằng product không tồn tại vì có thể không đủ stock.

**SKIP LOCKED thường hợp với “chọn việc khác thay thế được”, không phải “bỏ qua một thực thể bắt buộc phải xử lý”.**

## 30. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `NOWAIT` là “không bao giờ block” | Chỉ thay đổi chờ row lock của locking clause | Xét table locks; dùng `LOCK TABLE ... NOWAIT` hoặc lock_timeout nếu cần |
| Nghĩ `SKIP LOCKED` không lấy lock | Những hàng được chọn vẫn bị khóa | Kết thúc transaction nhanh |
| Dùng `SKIP LOCKED` cho báo cáo tổng số hàng | Bỏ mất hàng đang bị khóa | Dùng SELECT snapshot bình thường |
| Dùng SKIP LOCKED để kiểm tra “tài khoản không tồn tại” | Hàng bị khóa cũng có thể không trả về | Chọn NOWAIT/chờ; phân biệt busy và missing |
| Chỉ SELECT job rồi COMMIT | Sau commit job vẫn PENDING, worker khác nhận lại | Chọn và UPDATE RUNNING trong cùng transaction |
| Giữ transaction mở suốt thời gian gửi email | Khóa lâu, ảnh hưởng VACUUM | Claim+commit, xử lý ngoài, finalize trong transaction mới |
| Nghĩ SKIP LOCKED bảo đảm exactly-once | Worker crash sau side effect có thể gây retry | Idempotency và lease/fencing |
| Dùng OFFSET để phân trang queue | Hàng OFFSET có thể vẫn bị khóa | Claim batch không OFFSET |
| Tin ORDER BY đảm bảo FIFO tuyệt đối | Hàng ưu tiên cao bị khóa có thể bị bỏ qua | Thiết kế yêu cầu thứ tự/ownership rõ |
| Cho rằng LIMIT 10 chỉ chạm 10 tuple | Có thể phải xét nhiều tuple bị khóa | Đo trên workload thực |
| Dùng FOR UPDATE trên mọi bảng JOIN | Khóa cả dữ liệu cấu hình không cần thiết | `FOR UPDATE OF j` |
| Locking clause sau GROUP BY | Không còn một hàng nguồn để khóa | Chọn row IDs trong CTE trước |
| Bắt 55P03 rồi tiếp tục transaction đang lỗi | PostgreSQL từ chối SQL sau lỗi | ROLLBACK hoặc savepoint |
| Chỉ retry ngay lập tức vô hạn | Retry storm, tăng contention | Backoff, jitter, retry limit |
| Coi 55P03, 40P01, 40001 là cùng lỗi | Cần xử lý khác nhau | Phân loại SQLSTATE và retry đúng phạm vi |
| Tăng lock_timeout vô hạn | Che transaction giữ khóa quá lâu | Theo dõi blocker và sửa quy trình |
| Dùng lock_timeout như giới hạn toàn statement | Chỉ giới hạn từng lần đợi lock | Thêm statement_timeout nếu cần |
| Nghĩ idle-in-transaction timeout xử lý mọi lock wait | Chỉ nhắm session idle trong transaction | Hiểu trạng thái session và loại timeout |
| Coi lease_until là row lock PostgreSQL | Lease chỉ là cột dữ liệu | Kiểm tra token và trạng thái khi finalize |
| Chỉ dùng worker ID để xác nhận ownership | Worker ID có thể được tái sử dụng | Dùng claim token/phiên bản |
| Cho rằng token DB ngăn được email gửi lặp | Side effect ngoài DB không rollback | Fencing/idempotency downstream |
| Chạy EXPLAIN ANALYZE trên locking query production bừa bãi | Thực thi và lấy khóa thật | Đo trên lab/staging hoặc bảo trì có kiểm soát |
| Dùng advisory lock như thay thế PK/FK | Khóa chỉ được ứng dụng tự nguyện tuân thủ | Dùng constraint và row locks đúng chỗ |

## 31. Quy trình lựa chọn cách chờ khóa

Khi thiết kế một truy vấn cạnh tranh khóa, hãy xác định lần lượt:

1. **Bạn cần đúng hàng đó, hay một hàng khác cũng được?** Nếu cần đúng, không dùng SKIP LOCKED để giả vờ hàng không tồn tại.
2. **Có cho phép chờ không?** Nếu có, thời gian chờ tối đa?
3. **Không lấy được lock thì ứng dụng làm gì?** Retry, trả busy, chọn job khác hay đưa vào queue?
4. **Loại khóa nào có thể gây chờ?** Row lock, table lock, advisory lock, FK/DDL?
5. **Locking clause phù hợp?** FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE, FOR KEY SHARE?
6. **Có cần `OF alias` trong JOIN?** Tránh khóa thêm những bảng không cần thiết.
7. **Isolation level nào đang dùng?** READ COMMITTED, REPEATABLE READ hay SERIALIZABLE?
8. **Có kiểm tra số hàng ảnh hưởng không?** 0 hàng có thể là “không tìm thấy”, “không đủ điều kiện” hoặc “đã bị skip”.
9. **Transaction sẽ giữ khóa bao lâu?** Có I/O ngoài DB trong transaction không?
10. **Có giới hạn lock_timeout/statement_timeout không?** Có code rollback khi lỗi?
11. **Nếu job crash thì sao?** Có lease, reaper và claim token không?
12. **Side effect bên ngoài có idempotent không?** Có nguy cơ xử lý trùng không?
13. **Có yêu cầu thứ tự tuyệt đối hoặc công bằng không?** SKIP LOCKED có thể gây starvation.
14. **Có index phù hợp không?** Query plan và dead tuples có ổn không?
15. **Có đủ metrics/alert để quan sát contention không?** Biết ai giữ khóa và ai đang đợi?

### 31.1. Bảng chọn nhanh

| Mục tiêu | Lựa chọn thường phù hợp |
| --- | --- |
| Cần sửa một hàng xác định, có thể đợi | UPDATE nguyên tử hoặc SELECT FOR UPDATE mặc định |
| Cần một hàng xác định, thất bại ngay nếu bận | SELECT FOR UPDATE NOWAIT |
| Chấp nhận chờ ngắn, nhưng không vô hạn | SET LOCAL lock_timeout rồi locking SELECT/UPDATE |
| Nhiều worker chọn job bất kỳ đủ điều kiện | SELECT FOR UPDATE SKIP LOCKED + UPDATE trong cùng transaction |
| Chỉ cần đọc báo cáo nhất quán theo snapshot | SELECT thông thường, không SKIP LOCKED |
| Cần thử khóa bảng không chờ | LOCK TABLE ... IN ... MODE NOWAIT |
| Cần giữ reservation lâu vài phút | Trạng thái/lease đã commit, không giữ row lock dài |
| Cần giới hạn chạy một nhiệm vụ logic theo khóa ứng dụng | Cân nhắc pg_try_advisory_xact_lock và thiết kế riêng |

## 32. Bài tập thực hành

Sử dụng schema `lock_wait_lab`. Các bài hai phiên cần kết nối tới cùng database và **kết thúc mọi transaction thử nghiệm bằng COMMIT/ROLLBACK**; không để session giữ khóa rồi rời đi.

1. **Khóa cơ bản:** tạo ba account và giải thích một câu `SELECT ... FOR UPDATE` lấy những loại khóa chính nào.
2. **Chờ mặc định:** Session A khóa account 1, B dùng `FOR UPDATE`. Vì sao B chờ? Điều gì làm B tiếp tục?
3. **NOWAIT:** thay lệnh ở B thành `FOR UPDATE NOWAIT`. Ghi SQLSTATE nhận được và trạng thái transaction.
4. **Dọn sau lỗi:** B gặp 55P03, thử chạy thêm SELECT trước ROLLBACK; quan sát vì sao transaction cần rollback.
5. **Savepoint:** dùng SAVEPOINT trước NOWAIT, khi lỗi rollback về savepoint rồi tiếp tục một SELECT khác.
6. **SKIP LOCKED:** A khóa account 1, B chạy `FOR UPDATE SKIP LOCKED` trên ba accounts. Dự đoán các account trả về.
7. **SELECT bình thường:** A giữ FOR UPDATE; B dùng SELECT không locking clause. Tại sao B thường vẫn đọc được?
8. **Chế độ khóa:** so khả năng tương thích của FOR SHARE và FOR KEY SHARE với FOR NO KEY UPDATE.
9. **Chờ có giới hạn:** B đặt `SET LOCAL lock_timeout='1s'` rồi chờ account 1; so với NOWAIT.
10. **statement_timeout:** đặt cả lock_timeout và statement_timeout, giải thích mỗi giới hạn kiểm soát điều gì.
11. **Khóa bảng:** A giữ ACCESS EXCLUSIVE trên accounts; B chạy FOR UPDATE NOWAIT. Vì sao B vẫn có thể chờ?
12. **LOCK TABLE NOWAIT:** thử lấy ROW SHARE table lock với NOWAIT ở B khi A có ACCESS EXCLUSIVE.
13. **DDL và lock:** mô tả vì sao một transaction giữ row lock lâu có thể làm chậm maintenance/ALTER TABLE.
14. **Hàng đợi:** tạo `jobs` và nạp sáu job với priority khác nhau. Viết query liệt kê job PENDING theo priority.
15. **Hai worker:** A lấy job cao nhất FOR UPDATE SKIP LOCKED và giữ transaction; B lấy một job theo cùng tiêu chí. Hai job khác nhau thế nào?
16. **Claim nguyên tử:** viết CTE chọn hai job PENDING có `FOR UPDATE SKIP LOCKED` rồi UPDATE trạng thái RUNNING với RETURNING.
17. **Tranh chấp claim:** cho hai worker đồng thời chạy claim. Giải thích vì sao chúng không ghi RUNNING cho cùng hàng trong cùng thời điểm.
18. **Không chỉ SELECT:** giải thích vì sao chỉ SELECT job rồi COMMIT mà chưa UPDATE RUNNING có thể khiến job bị nhận lại.
19. **Lease:** sau claim, vì sao cần commit ngay rồi mới xử lý payload? `lease_until` khác row lock ở điểm nào?
20. **Token:** hoàn tất job bằng WHERE gồm job_id, claimed_by, lease_token; điều gì xảy ra nếu token cũ?
21. **Heartbeat:** viết UPDATE gia hạn lease chỉ khi đúng owner/token và lease còn hiệu lực.
22. **Worker crash:** job RUNNING hết lease, viết reaper chọn tối đa 50 job và đưa về PENDING hoặc FAILED.
23. **Retry:** khi lỗi tạm thời, dùng attempt_count/max_attempts quyết định PENDING hay FAILED với backoff.
24. **Exactly-once:** mô tả một trường hợp email đã gửi nhưng DB chưa ghi DONE. Vì sao SKIP LOCKED không tự ngăn email lặp?
25. **Starvation:** tạo một job ưu tiên thấp và liên tục thêm job ưu tiên cao. Nêu cách giảm starvation.
26. **Ordering:** A khóa job có priority cao nhất, B dùng ORDER BY priority DESC SKIP LOCKED. Vì sao không đảm bảo FIFO tuyệt đối?
27. **OFFSET:** thử OFFSET 2 LIMIT 2 FOR UPDATE SKIP LOCKED và giải thích vì sao các hàng OFFSET vẫn có thể bị khóa.
28. **JOIN OF:** nối jobs với job_types và dùng `FOR UPDATE OF j SKIP LOCKED`. Vì sao không nên khóa row của job_types?
29. **GROUP BY:** vì sao SELECT COUNT(*) GROUP BY status FOR UPDATE không phù hợp? Sửa bằng CTE khóa row IDs.
30. **SQLSTATE:** phân biệt 55P03, 40P01, 40001 và 57014; lỗi nào cần retry toàn transaction?
31. **pg_stat_activity:** tạo một lock wait trong lab rồi dùng `pg_blocking_pids` tìm blocker.
32. **pg_locks:** vì sao không thấy một tuple lock rõ ràng không chứng minh không có tranh chấp row lock?
33. **EXPLAIN:** xem plan của SELECT job với LIMIT 10 FOR UPDATE SKIP LOCKED. Những node LockRows/Sort/Scan nào xuất hiện?
34. **Index:** tạo partial index cho status PENDING rồi xem tác động với dữ liệu đủ lớn; tại sao index không loại bỏ contention?
35. **READ COMMITTED:** nếu một worker commit trạng thái RUNNING, worker khác sẽ thấy điều gì trong câu claim tiếp theo?
36. **SERIALIZABLE:** nếu nhận SQLSTATE 40001, vì sao nên retry toàn transaction thay vì chỉ một câu UPDATE?
37. **API bận:** thiết kế cách trả response khi NOWAIT báo busy trên tài khoản được yêu cầu; không nhầm busy với not found.
38. **Inventory:** vì sao dùng SKIP LOCKED để kiểm tra hết hàng có thể sai? Đề xuất UPDATE có điều kiện hoặc transaction locking phù hợp.
39. **Advisory lock:** so `pg_try_advisory_xact_lock` với `SELECT ... FOR UPDATE NOWAIT` về phạm vi và khả năng cưỡng chế.
40. **Thiết kế production:** một queue có 100 worker, job chạy 30 giây và đôi lúc timeout. Đề xuất batch size, lease, heartbeat, retry/idempotency, metrics và quy trình recovery.

## 33. Tổng kết

Trong PostgreSQL, việc lựa chọn cách chờ khóa phải dựa trên **ý nghĩa của kết quả khi có tranh chấp**, không chỉ dựa vào tốc độ một câu SQL.

```text
Một hàng cần lấy đang bị transaction khác khóa
    |
    +--> FOR UPDATE (mặc định)
    |       Chờ khóa được nhả
    |
    +--> FOR UPDATE NOWAIT
    |       Không đợi row lock
    |       Trả lỗi 55P03 nếu không lấy được ngay
    |
    +--> FOR UPDATE SKIP LOCKED
    |       Bỏ qua hàng bị khóa
    |       Có thể chọn hàng khác hoặc trả 0 hàng
    |
    +--> Chờ với lock_timeout
            Đợi tối đa giới hạn tại mỗi lần đợi lock
            Không chỉ riêng row-level lock
```

Những nguyên tắc phải nhớ:

- **`NOWAIT` và `SKIP LOCKED` ảnh hưởng đến row-level locks của locking clause**, không biến mọi table-level lock hay mọi bước thực thi thành không chờ.
- **`NOWAIT` hợp khi cần đúng hàng và có thể báo bận ngay**. Cần xử lý SQLSTATE `55P03` và rollback/savepoint đúng cách.
- **`SKIP LOCKED` hợp khi có nhiều hàng công việc có thể thay thế nhau**. Nó **không phù hợp với báo cáo cần tập dữ liệu đầy đủ** và không chứng minh hàng bị bỏ qua không tồn tại.
- **Một queue worker đúng phải chọn và đánh dấu nhận việc trong cùng transaction**; dùng `WITH candidates AS (... FOR UPDATE SKIP LOCKED) UPDATE ... RETURNING` là một mẫu PostgreSQL hữu ích.
- **Sau claim, commit nhanh; xử lý bên ngoài với lease và token**. Đừng giữ row locks suốt thời gian gọi API hoặc đợi người dùng.
- **`SKIP LOCKED` không bảo đảm FIFO, fairness hoặc exactly-once side effects**. Retry, reaper, backoff, fencing và idempotency cần được thiết kế riêng.
- **`lock_timeout`, `statement_timeout` và deadlock detection có vai trò khác nhau**; không dùng một tham số để thay mọi cơ chế kiểm soát thời gian.
- **Giám sát ai chờ ai bằng `pg_stat_activity`, `pg_blocking_pids` và `pg_locks`**, sau đó tối ưu transaction duration, index và concurrency dựa trên thực tế.

Quy tắc chọn nhanh: **cần đúng hàng thì chờ hoặc NOWAIT; chấp nhận làm việc khác thì SKIP LOCKED; cần chờ có giới hạn thì dùng lock_timeout; cần xử lý lâu thì lưu trạng thái/lease rồi commit khóa ngắn**. Khi phân biệt rõ các trường hợp đó, PostgreSQL có thể đồng thời giữ được tính nhất quán dữ liệu và thông lượng xử lý dưới tải cạnh tranh.
