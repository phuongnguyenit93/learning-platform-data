# Giải phóng khóa, hủy truy vấn và chấm dứt phiên an toàn trong PostgreSQL

## 1. Tình huống: câu lệnh UPDATE bị treo vì một giao dịch khác

Một ứng dụng có bảng đơn hàng. Người vận hành nhìn thấy một câu `UPDATE` đã chạy gần một phút nhưng không hoàn tất:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

Phản ứng nóng vội có thể là tìm một PostgreSQL PID rồi gọi `pg_terminate_backend(pid)`. Nhưng điều gì sẽ xảy ra nếu PID đó đang xử lý giao dịch chuyển tiền chưa commit? Nếu PID bị hủy là một worker quan trọng? Nếu truy vấn đang chờ chỉ là **nạn nhân** còn khóa thực sự nằm ở một session khác đang `idle in transaction`?

Cần phân biệt ba việc:

1. **Giải phóng khóa**: kết thúc đúng transaction, nhả session-level advisory lock hoặc thực hiện cơ chế phù hợp với từng loại khóa.
2. **Hủy câu truy vấn đang chạy**: yêu cầu PostgreSQL ngừng statement hiện tại, thường bằng `pg_cancel_backend(pid)`.
3. **Chấm dứt phiên/backend**: yêu cầu ngắt hẳn kết nối và hủy transaction chưa commit, thường bằng `pg_terminate_backend(pid)`.

Ba việc này **không đồng nghĩa**.

Một phiên đang chờ khóa có thể bị hủy truy vấn, nhưng phiên đang giữ khóa vẫn tiếp tục. Một phiên đang giữ khóa ở transaction vẫn có thể giữ khóa sau khi câu truy vấn hiện tại kết thúc. Một **session-level advisory lock** còn có thể tồn tại sau cả `COMMIT` và `ROLLBACK` nếu không được mở khóa.

> **Nguyên tắc vận hành:** trước khi can thiệp, xác định **ai đang chờ, ai đang chặn, loại khóa gì, transaction nào còn mở và hậu quả của việc hủy/đóng kết nối**.

Bài học này giải thích các cơ chế đó trong ngữ cảnh PostgreSQL và cung cấp thí nghiệm có thể tái hiện trong một database thử nghiệm.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt vòng đời của table lock, row lock, transaction advisory lock và session advisory lock.
2. Hiểu khi nào `COMMIT`, `ROLLBACK`, `ROLLBACK TO SAVEPOINT`, `UNLOCK` hoặc ngắt backend giải phóng khóa.
3. Phân biệt `pg_cancel_backend` và `pg_terminate_backend` về đối tượng tác động, trạng thái transaction và kết quả.
4. Tra cứu `pg_stat_activity`, `pg_locks` và `pg_blocking_pids` để xác định blocker/waiter.
5. Nhận biết phiên `active` đang chờ khóa và phiên `idle in transaction` đang giữ khóa.
6. Dùng `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout` một cách có chủ đích.
7. Hiểu lỗi SQLSTATE thường gặp sau hủy câu lệnh, timeout, deadlock hoặc mất kết nối.
8. Thực hành hủy **waiter** mà không làm ảnh hưởng **blocker** và ngược lại.
9. Chọn hướng xử lý an toàn: chờ, yêu cầu client commit/rollback, cancel, terminate hay điều tra thêm.
10. Hiểu tác động đối với JDBC, connection pool, transaction nhiều bước và yêu cầu idempotency.
11. Nhận biết prepared transaction, backend đặc biệt và những trường hợp không thể “kill PID” đơn giản.
12. Thiết lập quy trình phản ứng sự cố có thể kiểm toán và tránh gây mất dữ liệu nghiệp vụ.

## 3. Khóa trong PostgreSQL tồn tại đến khi nào?

PostgreSQL có nhiều cơ chế khóa. Thời điểm nhả khóa phụ thuộc vào **khóa được lấy bằng cách nào** và **phạm vi sở hữu**.

| Loại khóa / cách lấy | Vòng đời thông thường | Cách giải phóng phù hợp |
| --- | --- | --- |
| Khóa bảng phát sinh từ `SELECT`, `INSERT`, `UPDATE`, `DELETE` | Theo transaction | `COMMIT` hoặc `ROLLBACK`; autocommit nhả khi statement kết thúc cùng transaction |
| Khóa hàng từ `UPDATE`/`DELETE`/`SELECT FOR UPDATE` | Theo transaction | Kết thúc transaction; có quy tắc savepoint riêng |
| `LOCK TABLE ... IN ... MODE` | Theo transaction | `COMMIT` hoặc `ROLLBACK` |
| `pg_advisory_xact_lock(...)` | Theo transaction | Kết thúc transaction, không có hàm unlock riêng |
| `pg_advisory_lock(...)` | Theo **session** | `pg_advisory_unlock(...)`, `pg_advisory_unlock_all()` trên chính session hoặc kết thúc session |
| `pg_advisory_lock_shared(...)` | Theo **session** | `pg_advisory_unlock_shared(...)` tương ứng hoặc kết thúc session |
| Khóa còn gắn với prepared transaction | Sau `PREPARE TRANSACTION`, có thể tiếp tục tồn tại không có backend thường trực | Xem xét `COMMIT PREPARED` hoặc `ROLLBACK PREPARED` theo quy trình 2PC |
| Khóa bên trong một subtransaction/savepoint | Phụ thuộc mốc lấy khóa và rollback đến savepoint | Một số khóa lấy sau savepoint được nhả nếu rollback về mốc đó |

Bảng trên mô tả các trường hợp phổ biến. Nội bộ lock manager có nhiều loại khóa và trường hợp đặc biệt, không nên suy luận chỉ từ một dòng `pg_locks` rằng toàn bộ khóa thuộc một statement hay một transaction duy nhất.

### 3.1. Autocommit dễ làm người mới học nhầm

Với client có autocommit bật:

```sql
UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 101;
```

statement thường chạy trong một transaction riêng. Khi statement kết thúc và transaction tự commit thành công, row/table locks của transaction đó được nhả.

Nếu client thực hiện:

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 101;

-- Không COMMIT hoặc ROLLBACK.
```

thì sau khi `UPDATE` trả kết quả, transaction vẫn mở và các khóa cần giữ tới cuối transaction **vẫn có thể tồn tại**.

Do đó, câu hỏi đúng không phải “lệnh UPDATE đã hoàn thành chưa?”, mà là **“transaction chứa UPDATE đã kết thúc chưa?”**.

### 3.2. Khóa không chỉ do lệnh LOCK tạo ra

`UPDATE` có thể gây row lock, các table-level locks cần thiết và chờ transaction khác. Một `SELECT` thông thường cũng lấy khóa bảng ở mức thích hợp để bảo vệ việc truy cập trước DDL không tương thích.

Vì vậy, người vận hành có thể gặp lock wait dù ứng dụng **không bao giờ viết `LOCK TABLE`**.

## 4. Thiết lập phòng thí nghiệm ba kết nối

Thực hành trong một database riêng; **không chạy thí nghiệm treo khóa, cancel hoặc terminate trên production**.

### 4.1. Tạo schema và dữ liệu

```sql
CREATE SCHEMA IF NOT EXISTS lock_ops_lab;

CREATE TABLE lock_ops_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12,2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO lock_ops_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

Tạo bảng công việc để minh họa tranh chấp khóa logic:

```sql
CREATE TABLE lock_ops_lab.jobs (
    job_id integer PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_ops_lab.jobs (job_id, status)
VALUES
    (1, 'PENDING'),
    (2, 'PENDING');
```

Các truy vấn kiểm tra:

```sql
SELECT * FROM lock_ops_lab.accounts ORDER BY account_id;
SELECT * FROM lock_ops_lab.jobs ORDER BY job_id;
```

Nếu chạy lại `INSERT` trên schema đã nạp sẽ có lỗi trùng khóa chính. Khởi tạo một database mới hoặc khôi phục có kiểm soát trước mỗi lần thử.

### 4.2. Mở ba session độc lập

- **Session A**: phiên giữ khóa (*holder*).
- **Session B**: phiên bị chặn (*waiter*).
- **Session C**: phiên theo dõi hoặc gửi tín hiệu.

Trong từng cửa sổ `psql`/SQL client, ghi lại PID:

```sql
SELECT
    pg_backend_pid() AS my_pid,
    current_database() AS db_name,
    current_user AS db_user;
```

Ba session cần có **PID backend khác nhau** để thử nghiệm việc một phiên khóa phiên khác. Nếu công cụ tự gộp các tab vào cùng connection, kết quả có thể sai do không có hai backend cạnh tranh thật sự.

### 4.3. Gắn tên ứng dụng cho dễ quan sát

Trên mỗi session thử nghiệm, có thể đặt:

```sql
SET application_name = 'lock-lab-A';
```

Thay `A` bằng `B` hoặc `C` ở cửa sổ tương ứng. `application_name` giúp đọc `pg_stat_activity`, nhưng **không thay thế** việc kiểm tra PID, user, database và thời điểm tạo backend.

Ở hệ thống thật, tên ứng dụng do client cung cấp và có thể bị đặt sai; không chỉ dựa vào một chuỗi tên để quyết định hủy phiên.

## 5. Thí nghiệm cơ bản: một UPDATE giữ khóa sau khi statement kết thúc

Đây là ví dụ tạo lock wait có kiểm soát bằng **row update**.

### 5.1. Session A cập nhật nhưng chưa commit

Đảm bảo tài khoản 101 đang có số dư phù hợp.

**Session A:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101
RETURNING account_id, balance;

-- DỪNG tại đây, KHÔNG COMMIT hoặc ROLLBACK ngay.
```

Statement UPDATE đã hoàn tất trong Session A, nhưng transaction A chưa kết thúc.

### 5.2. Session B thử cập nhật cùng hàng

**Session B:**

```sql
BEGIN;

SET LOCAL statement_timeout = '30s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20.00
WHERE account_id = 101
RETURNING account_id, balance;
```

Nếu A chưa giải phóng khóa, UPDATE của B có thể **chờ**.

Session B không nhất thiết nhìn thấy một thông báo “đang đợi khóa” trong UI; client có thể chỉ hiển thị câu SQL vẫn đang chạy.

### 5.3. Session C quan sát

**Session C:**

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.application_name IN ('lock-lab-A', 'lock-lab-B')
ORDER BY a.pid;
```

Kỳ vọng trong tình huống chờ:

- Session A có thể hiển thị `state = 'idle in transaction'` vì đã chạy UPDATE xong nhưng transaction còn mở.
- Session B có thể hiển thị `state = 'active'` và `wait_event_type = 'Lock'`.
- `pg_blocking_pids(B_PID)` có thể chứa PID của A.

### 5.4. Giải phóng từ Session A

**Session A:**

```sql
ROLLBACK;
```

Khi transaction A rollback, thay đổi `+10` bị hủy và khóa transaction được nhả. Session B có thể tiếp tục UPDATE, khi chưa bị statement timeout/cancel.

Nếu B hoàn thành và bạn muốn giữ dữ liệu lab ban đầu:

**Session B:**

```sql
ROLLBACK;
```

Lưu ý: nếu trước đó B đã hết `statement_timeout`, transaction B có thể ở trạng thái aborted; câu lệnh cần làm lúc này là `ROLLBACK`.

**Kết luận:** không phải UPDATE A chạy xong làm khóa mất đi; chính **transaction A kết thúc** mới giải phóng các khóa theo transaction.

## 6. `COMMIT` và `ROLLBACK` giải phóng khóa ra sao?

### 6.1. `COMMIT`

Khi transaction commit thành công:

- Những thay đổi được xác nhận theo quy tắc giao dịch.
- Các khóa có vòng đời transaction được nhả.
- Transaction khác có thể tiếp tục khi không còn blocker tương thích nào.

Ví dụ:

```sql
BEGIN;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101
FOR UPDATE;

COMMIT;
```

Khóa hàng từ `FOR UPDATE` không còn thuộc transaction sau `COMMIT`.

### 6.2. `ROLLBACK`

Khi rollback:

- Thay đổi dữ liệu chưa commit của transaction bị hủy.
- Các khóa có vòng đời transaction được nhả.
- Transaction khác có thể tiếp tục hoặc kiểm tra lại điều kiện phù hợp.

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance - 10
WHERE account_id = 101;

ROLLBACK;
```

Số dư trở về trạng thái trước transaction này, trừ khi có các thao tác khác đã commit độc lập.

### 6.3. Không nhầm “rollback transaction” với “hủy mọi tác dụng bên ngoài”

Giả sử ứng dụng:

1. Bắt đầu transaction PostgreSQL.
2. Cập nhật trạng thái đơn hàng.
3. Gọi API bên ngoài để gửi email.
4. Rollback vì một lỗi khác.

Dữ liệu PostgreSQL chưa commit bị rollback; **email đã gửi không tự thu hồi**. Việc chấm dứt backend trong lúc transaction đang thao tác hệ thống ngoài cũng không hoàn tác side effect đó.

Khi thiết kế khôi phục sau sự cố khóa, phải tính đến idempotency và điều phối side effect, không chỉ nhìn trạng thái bảng.

### 6.4. Đừng dùng `COMMIT` để “giải phóng khóa” khi nghiệp vụ chưa hoàn tất

Một transaction đang giữ khóa có thể đang chứa một nửa quy trình nghiệp vụ. Chạy `COMMIT` chỉ để hết chờ có nguy cơ **xác nhận trạng thái chưa hoàn chỉnh**.

Người vận hành nên yêu cầu ứng dụng hoàn tất/rollback đúng quy trình, thay vì buộc commit một transaction chưa hiểu.

## 7. `SAVEPOINT` và giải phóng khóa một phần

Trong PostgreSQL, rollback tới savepoint có thể giải phóng những khóa **được lấy sau savepoint**, trong phạm vi quy tắc subtransaction.

### 7.1. Thí nghiệm với khóa bảng

```sql
BEGIN;

SAVEPOINT before_extra_lock;

LOCK TABLE lock_ops_lab.jobs
IN SHARE ROW EXCLUSIVE MODE;

ROLLBACK TO SAVEPOINT before_extra_lock;

-- Khóa bảng vừa lấy sau savepoint được hoàn tác
-- theo quy tắc khóa/subtransaction.

ROLLBACK;
```

Điểm chính:

- Savepoint không phải transaction độc lập có thể commit vĩnh viễn.
- Những khóa có vòng đời transaction lấy **trước** savepoint không tự mất khi rollback về savepoint.
- Những khóa đủ điều kiện lấy **sau** savepoint thường được giải phóng khi rollback về mốc đó.

### 7.2. Khi có lỗi và `ROLLBACK TO SAVEPOINT`

```sql
BEGIN;

SAVEPOINT try_step;

UPDATE lock_ops_lab.accounts
SET balance = -1
WHERE account_id = 101;
-- Vi phạm CHECK (balance >= 0).

ROLLBACK TO SAVEPOINT try_step;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101;

ROLLBACK;
```

Lỗi ở câu UPDATE không bắt buộc phải hủy toàn transaction nếu ứng dụng đã đặt savepoint và xử lý `ROLLBACK TO SAVEPOINT` phù hợp.

### 7.3. Khác biệt quan trọng với session advisory lock

`pg_advisory_lock(...)` là khóa theo **session**, nên rollback transaction hoặc savepoint **không phải cơ chế nhả khóa session-level**.

Với `pg_advisory_xact_lock(...)`, khóa thuộc về transaction; phần rollback đến savepoint liên quan đến phạm vi khóa lấy trong subtransaction và các quy tắc giải phóng tương ứng.

**Trong code thực tế**, đừng dùng savepoint như một thủ thuật khó đoán để quản lý mọi advisory lock. Khi cần ownership theo transaction, để transaction manager quản lý biên giới commit/rollback; khi cần session-level, đặt cleanup tường minh.

## 8. Advisory lock: ngoại lệ lớn của câu “ROLLBACK sẽ nhả khóa”

Có hai loại advisory lock:

| Ví dụ | Phạm vi | Sau `ROLLBACK`? |
| --- | --- | --- |
| `pg_advisory_lock(247, 1)` | Session | **Vẫn giữ** nếu session chưa unlock |
| `pg_advisory_lock_shared(247, 1)` | Session | **Vẫn giữ** |
| `pg_advisory_xact_lock(247, 1)` | Transaction | **Nhả** khi transaction kết thúc |
| `pg_advisory_xact_lock_shared(247, 1)` | Transaction | **Nhả** khi transaction kết thúc |

### 8.1. Thử khóa theo phiên

**Session A:**

```sql
SELECT pg_advisory_lock(247, 1);

BEGIN;

UPDATE lock_ops_lab.jobs
SET status = 'RUNNING'
WHERE job_id = 1;

ROLLBACK;
```

Dù UPDATE đã rollback, session A **vẫn giữ** advisory lock `(247,1)`.

**Session B:**

```sql
SELECT pg_try_advisory_lock(247, 1) AS acquired;
-- false nếu A đang giữ khóa exclusive cùng key.
```

**Session A nhả khóa:**

```sql
SELECT pg_advisory_unlock(247, 1) AS released;
-- true nếu A đang giữ một lượt khóa tương ứng.
```

Sau đó B có thể thử lại. Nếu B nhận `true` từ `pg_try_advisory_lock`, B cũng cần unlock:

```sql
SELECT pg_try_advisory_lock(247, 1) AS acquired;
SELECT pg_advisory_unlock(247, 1);
```

### 8.2. Khóa session có thể được lấy lặp lại

Cùng một backend có thể lấy nhiều lần một session advisory key theo cơ chế reentrant. Phải nhả đủ số lượt khóa đã lấy:

```sql
SELECT pg_advisory_lock(247, 2);
SELECT pg_advisory_lock(247, 2);

SELECT pg_advisory_unlock(247, 2);
-- Có thể vẫn còn một lượt giữ khóa.

SELECT pg_advisory_unlock(247, 2);
-- Nhả lượt còn lại.
```

Một lời gọi unlock không bảo đảm key hoàn toàn được nhả nếu session đã acquire nhiều lần.

### 8.3. `pg_advisory_unlock_all()`

```sql
SELECT pg_advisory_unlock_all();
```

Hàm này giải phóng **session-level advisory locks của chính backend gọi nó**. Nó không phải công cụ tùy ý giải phóng khóa ở một backend khác và **không nhả transaction-level advisory locks**.

Đừng gọi `pg_advisory_unlock_all()` trong pooled connection mà không biết những thành phần khác đang sử dụng session đó, vì có thể phá vỡ quy ước khóa của thư viện khác.

### 8.4. Khóa theo giao dịch có thể phù hợp hơn trong connection pool

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 3);

SELECT status
FROM lock_ops_lab.jobs
WHERE job_id = 1;

COMMIT;
```

Khóa `(247,3)` được tự nhả khi transaction commit. Không có hàm `pg_advisory_xact_unlock` để gọi.

**Nhớ:** trong autocommit, transaction-level advisory lock có thể được lấy rồi tự nhả ngay sau statement chứa hàm; muốn bảo vệ nhiều câu SQL, cần mở transaction tường minh.

## 9. `pg_cancel_backend(pid)` thực sự làm gì?

Hàm:

```sql
SELECT pg_cancel_backend(12345);
```

yêu cầu PostgreSQL gửi tín hiệu **hủy câu lệnh hiện tại** tới backend có PID đó, trong phạm vi quyền cho phép.

Ở mức mô hình:

```text
Session B đang chạy SELECT/UPDATE và chờ khóa
            |
Session C gọi pg_cancel_backend(B_PID)
            |
            v
Session B nhận yêu cầu cancel
            |
            v
Statement hiện tại bị hủy
            |
            +-- Transaction tường minh có thể ở trạng thái lỗi
            |   cần ROLLBACK
            |
            +-- Transaction không tự biến mất nếu chỉ cancel
            |
            +-- Session B vẫn tồn tại để ứng dụng xử lý tiếp
```

### 9.1. Điểm cốt lõi

- **Cancel hướng vào statement đang thực thi**, không phải “nhả tất cả khóa của session”.
- **Backend vẫn tồn tại**; connection không bị đóng chỉ vì cancel.
- Nếu statement thuộc transaction tường minh, lỗi cancel thường đưa transaction vào trạng thái aborted; client phải `ROLLBACK` hoặc xử lý savepoint theo thiết kế.
- Các khóa transaction vẫn có thể tồn tại **cho tới khi transaction thực sự kết thúc**.
- Session-level advisory locks đã giữ vẫn có thể tồn tại sau cancel.

### 9.2. Kết quả boolean không có nghĩa nghiệp vụ đã phục hồi

`pg_cancel_backend(pid)` trả boolean thể hiện yêu cầu gửi tín hiệu có được thực hiện hay không. Giá trị `true` **không chứng minh** toàn bộ các khóa đã được nhả, transaction đã rollback, hay blocker biến mất.

Sau khi cancel, cần **quan sát lại** trạng thái phiên và danh sách blockers.

### 9.3. Cancel một backend đang idle có thể không giải quyết gì

Nếu phiên A đã chạy UPDATE rồi ở trạng thái:

```text
idle in transaction
```

thì tại thời điểm đó **không có câu query đang thực thi để cancel theo nghĩa thông thường**. Một yêu cầu `pg_cancel_backend(A_PID)` không phải cách đáng tin cậy để kết thúc transaction chưa commit của A.

Lối xử lý phù hợp thường là:

1. Yêu cầu ứng dụng/client sở hữu connection **COMMIT hoặc ROLLBACK** theo logic của nó.
2. Nếu không thể phối hợp, đánh giá mức độ an toàn rồi mới **terminate session** như biện pháp mạnh hơn.

Không coi một kết quả `true` của `pg_cancel_backend` là bằng chứng khóa của phiên idle đã biến mất.

## 10. Thí nghiệm: cancel waiter nhưng blocker vẫn giữ khóa

Đây là thí nghiệm quan trọng và tương đối an toàn khi thực hiện trên lab.

### 10.1. Session A giữ row lock

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

-- Giữ transaction A mở.
```

### 10.2. Session B ghi lại PID rồi bắt đầu chờ

**Session B:**

```sql
SELECT pg_backend_pid() AS waiter_pid;
```

Ghi lại PID do B trả về, ví dụ `34567`. Đây **chỉ là ví dụ**, không được dán con số mẫu vào production.

Tiếp tục:

```sql
BEGIN;

SET LOCAL statement_timeout = '60s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20
WHERE account_id = 101;
-- Có thể bị chặn bởi A.
```

### 10.3. Session C gửi yêu cầu cancel B

Trước khi gửi, xác nhận PID B trên bảng giám sát:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE pid = 34567;
```

Sau khi xác nhận đúng **PID của Session B trong lab**:

```sql
SELECT pg_cancel_backend(34567) AS signal_sent;
```

Thay `34567` bằng PID thật vừa ghi nhận và xác minh. Trong thí nghiệm B có thể nhận lỗi:

```text
ERROR: canceling statement due to user request
SQLSTATE: 57014
```

### 10.4. Session B xử lý transaction lỗi

**Session B:**

```sql
ROLLBACK;
```

Nếu B cố chạy SELECT bình thường trước rollback, có thể nhận:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
```

### 10.5. Session A vẫn còn khóa

Sau khi C cancel B, A vẫn đang giữ transaction chưa commit. Bạn phải kết thúc A:

```sql
ROLLBACK;
```

**Kết luận quan sát:**

- Cancel **B** giúp bỏ câu UPDATE đang chờ của B.
- Nó **không** làm A tự rollback.
- Row lock của A chỉ nhả khi transaction A kết thúc (hoặc backend A bị kết thúc theo cơ chế khác).
- Sau khi B rollback, lock wait của B biến mất, nhưng transaction A có thể tiếp tục gây chặn cho người khác.

## 11. `pg_terminate_backend(pid)` khác `pg_cancel_backend(pid)` thế nào?

Hàm:

```sql
SELECT pg_terminate_backend(12345);
```

yêu cầu PostgreSQL **chấm dứt backend/session** thay vì chỉ hủy statement đang chạy.

Về hiệu ứng thông thường:

- Kết nối của client bị ngắt.
- Transaction chưa commit của session bị hủy trong quá trình backend kết thúc.
- Các transaction-level locks được giải phóng khi transaction/backend kết thúc.
- Session-level advisory locks cũng được giải phóng khi session thực sự kết thúc.
- Những transaction đã commit trước đó **không bị hoàn tác** chỉ vì session bị terminate sau đó.

### 11.1. Bảng so sánh trực tiếp

| Tiêu chí | `pg_cancel_backend` | `pg_terminate_backend` |
| --- | --- | --- |
| Mục tiêu | Dừng **statement hiện tại** | Kết thúc **backend/session** |
| Connection tiếp tục tồn tại? | Thông thường **có** | **Không**, sau khi backend kết thúc |
| Transaction chưa commit | Có thể chuyển sang aborted nhưng vẫn cần rollback | Bị rollback khi backend kết thúc |
| Transaction-level locks | Không bảo đảm đã nhả ngay | Được nhả khi transaction/backend kết thúc |
| Session-level advisory locks | Không tự nhả | Được nhả khi session thực sự kết thúc |
| Tác động với client | Lỗi statement, client có thể phục hồi bằng rollback | Lỗi mất kết nối, client phải reconnect |
| Khả năng ảnh hưởng nghiệp vụ | Thường nhỏ hơn nhưng vẫn có tác động | Lớn hơn; có thể hủy toàn bộ công việc chưa commit |
| Tình huống ưu tiên | Query chạy lâu hoặc đang chờ và cần dừng statement | Session không hợp tác, khóa giữ dài và cần chấm dứt hẳn |

### 11.2. Hàm terminate trả `true` có nghĩa gì?

Tùy phiên bản PostgreSQL và chữ ký hàm:

```sql
SELECT pg_terminate_backend(12345);
```

khi không truyền thời gian chờ có thể trả `true` nếu **tín hiệu terminate đã được gửi thành công**, không phải bằng chứng chắc chắn backend đã rời hệ thống ngay trước khi hàm trả kết quả.

Các phiên bản PostgreSQL hỗ trợ tham số timeout có thể cho phép:

```sql
SELECT pg_terminate_backend(12345, 5000);
```

Trong đó timeout được biểu diễn bằng **mili-giây**; kết quả có thể phản ánh việc chờ backend thực sự kết thúc trong khoảng thời gian đó. Cần đối chiếu cú pháp theo **phiên bản PostgreSQL đang chạy**.

**Sau terminate vẫn phải xác minh** PID không còn hoặc session thực sự đã kết thúc; đừng quyết định chỉ dựa trên một lần gọi trả true.

### 11.3. Hủy transaction khác với hủy công việc bên ngoài

Nếu backend A đang giữ khóa và gọi một hệ thống ngoài (qua logic ứng dụng), terminate A có thể rollback thay đổi PostgreSQL chưa commit; nó **không thu hồi** tin nhắn đã gửi, email đã gửi hay tác động của API ngoài database.

Client nhận lỗi mất kết nối có thể tự retry. Nếu thao tác chưa được thiết kế idempotent, retry còn có thể tạo tác động lặp.

## 12. Thí nghiệm: terminate holder để giải phóng transaction chưa commit

**Đây là thao tác phá hủy session**, chỉ thực hành trên backend lab với dữ liệu không quan trọng.

### 12.1. Session A bắt đầu transaction và giữ row lock

```sql
SELECT pg_backend_pid() AS holder_pid;

BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

-- Không COMMIT hoặc ROLLBACK.
```

### 12.2. Session B bắt đầu chờ

```sql
BEGIN;

SET LOCAL statement_timeout = '60s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20
WHERE account_id = 101;

-- Đang chờ A nếu A còn giữ khóa.
```

### 12.3. Session C xác nhận và terminate đúng holder A

Ví dụ sau chỉ minh họa; thay PID bằng giá trị thật từ lab:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    backend_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

Sau khi xác nhận chính xác đó là Session A trong môi trường thử nghiệm:

```sql
SELECT pg_terminate_backend(23456) AS signal_sent;
```

Session A sẽ mất kết nối khi backend bị chấm dứt. Transaction A chưa commit bị rollback. Các khóa thuộc A được nhả trong quá trình kết thúc, giúp B có thể tiếp tục nếu B chưa hết timeout/cancel.

### 12.4. Session B kết thúc

Nếu B hoàn thành thành công:

```sql
ROLLBACK;
```

Dùng rollback để không thay đổi dữ liệu lab.

Nếu B đã timeout, nó cần rollback transaction lỗi và có thể thực hiện lại từ đầu trong transaction mới theo mục đích thử nghiệm.

### 12.5. Điều không thể kết luận từ thí nghiệm

Terminate A **không có nghĩa** “tất cả query trong database sẽ hết chờ”. Có thể còn nhiều blockers khác hoặc các lock khác không phụ thuộc session vừa bị terminate.

Nó cũng không chứng minh terminate luôn an toàn trên production. Trong một transaction nhiều bảng, việc rollback có thể thay đổi kết quả nghiệp vụ đang chờ xử lý, ảnh hưởng ứng dụng và gây retry.

## 13. Khi nào cancel waiter, khi nào xử lý blocker?

Có hai đối tượng dễ nhầm:

- **Waiter**: phiên đang yêu cầu khóa nhưng chưa lấy được.
- **Blocker**: phiên/transaction đang giữ hoặc đứng trước trong hàng đợi khiến waiter chưa thể lấy khóa.

Sơ đồ:

```text
Holder A ----------------> giữ lock X
                              |
                              v
Waiter B ----------------> chờ lock X
                              |
                              v
Waiter C ----------------> có thể tiếp tục chờ sau B
```

### 13.1. Cancel waiter B

Kết quả:

- B ngừng statement đang chờ.
- Giảm bớt hàng đợi chờ.
- Không động trực tiếp tới transaction A.
- Các waiter khác có thể vẫn chờ A.

Thích hợp nếu request B đã quá SLA hoặc người dùng đã hủy tác vụ B.

### 13.2. Cancel query của blocker A

Nếu A **đang chạy một statement dài** và chưa vào trạng thái idle, cancel statement A có thể khiến statement thất bại. Nhưng nếu A ở trong transaction tường minh, phải xác nhận client **rollback** mới thực sự giải phóng khóa transaction.

Nếu A đã ở `idle in transaction`, thường không có statement đang chạy để cancel.

### 13.3. Terminate blocker A

Kết quả mạnh hơn:

- Transaction chưa commit của A bị rollback khi backend kết thúc.
- Các khóa của A được nhả.
- B và C có thể có cơ hội tiến lên.
- Ứng dụng sở hữu A nhận lỗi mất kết nối và phải quyết định retry/khôi phục.

Đây là **biện pháp có rủi ro lớn hơn**, nên chỉ thực hiện khi đã xác minh đúng phiên, hiểu giao dịch liên quan, quyền vận hành và hậu quả nghiệp vụ.

### 13.4. Ưu tiên giải quyết tận gốc, không chỉ xóa triệu chứng

Nếu A là một phiên thường xuyên ở `idle in transaction` do ứng dụng quên `COMMIT`, terminate một lần có thể khôi phục tạm thời. Nhưng lỗi sẽ tái diễn cho đến khi sửa transaction boundary, timeout, exception handling hoặc connection pool.

## 14. Truy vấn giám sát số một: tìm các phiên đang chờ

PostgreSQL cung cấp `pg_stat_activity` để quan sát session/backend.

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.application_name,
    a.client_addr,
    a.backend_start,
    a.state,
    a.xact_start,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.query_start AS query_age,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

Những cột có ích:

| Cột | Câu hỏi được trả lời |
| --- | --- |
| `pid` | Backend nào? |
| `datname` | Thuộc database nào? |
| `usename` | Đang dùng role nào? |
| `application_name` | Client khai báo tên gì? |
| `client_addr` | Kết nối từ địa chỉ nào, nếu có? |
| `backend_start` | Backend được tạo khi nào? |
| `state` | Active, idle, idle in transaction hay trạng thái khác? |
| `xact_start` | Transaction đang mở bắt đầu khi nào? |
| `query_start` | Statement hiện tại hoặc statement được ghi nhận bắt đầu khi nào? |
| `wait_event_type` / `wait_event` | Backend đang chờ loại sự kiện gì? |
| `pg_blocking_pids(pid)` | Những PID nào đang chặn theo lock manager? |

### 14.1. `state = 'active'` không có nghĩa đang dùng CPU

Một backend có `state = 'active'` và `wait_event_type = 'Lock'` có thể đang **chờ khóa** chứ không tính toán.

Một backend `active` và `wait_event_type = 'IO'` có thể đang chờ I/O. Không hủy một truy vấn chỉ vì thấy nó active lâu; trước hết xem **nó đang làm gì**.

### 14.2. `idle in transaction` đáng chú ý

Một backend ở `idle in transaction` có thể đã chạy xong statement cuối nhưng vẫn giữ transaction mở, kéo dài thời gian giữ các khóa thuộc transaction.

Truy vấn `query` trong `pg_stat_activity` lúc đó có thể là **statement gần nhất**, không phải câu SQL đang chạy. Không mặc định rằng dòng text hiển thị là “lệnh đang giữ toàn bộ khóa” theo cách trực tiếp.

### 14.3. `idle in transaction (aborted)`

Trạng thái này thường phản ánh transaction đã lỗi nhưng client **chưa rollback hoặc kết thúc transaction**. Một số tài nguyên/khóa vẫn có thể tồn tại cho đến khi transaction được cleanup đúng; hãy xem trạng thái thực và loại khóa, thay vì giả định mọi khóa đã biến mất.

Ứng dụng nên rollback ngay sau lỗi, không để connection chờ người dùng hoặc quay về pool trong trạng thái aborted.

### 14.4. Không dùng riêng `query_age` để chọn nạn nhân

Một câu truy vấn chạy lâu có thể là backup, migration hoặc tác vụ bảo trì đã được phê duyệt. Một query mới bắt đầu có thể đang gây blocker vì nó lấy khóa mạnh.

Cần kết hợp:

- Dữ liệu dependency từ `pg_blocking_pids`.
- Tuổi transaction từ `xact_start`.
- Role/application/client.
- Loại công việc và tác động nghiệp vụ.
- Trạng thái retry/khôi phục của client.

## 15. Dùng `pg_blocking_pids` để xác định người gây chặn

`pg_blocking_pids(pid)` trả mảng PID các backend đang chặn một backend cụ thể theo cơ chế khóa PostgreSQL. Đây thường là điểm xuất phát tốt hơn việc tự nối `pg_locks` theo điều kiện khóa phức tạp.

### 15.1. Chỉ liệt kê những phiên có blocker

```sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blockers,
    a.query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
```

Kết quả ví dụ:

| waiting_pid | application_name | blockers |
| ---: | --- | --- |
| 34567 | order-api | {23456} |
| 34568 | invoice-api | {23456} |

Điều này gợi ý backend 23456 đang chặn hai phiên; **vẫn phải xem bản thân backend 23456** trước khi quyết định can thiệp.

### 15.2. Hiển thị thông tin waiter và blocker cạnh nhau

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    w.state AS waiting_state,
    w.query AS waiting_query,
    p.blocking_pid,
    b.application_name AS blocking_app,
    b.usename AS blocking_user,
    b.state AS blocking_state,
    b.xact_start AS blocking_xact_start,
    b.query AS blocking_last_query
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
    ON b.pid = p.blocking_pid
ORDER BY w.pid, p.blocking_pid;
```

Ưu điểm:

- Không cần tự suy đoán từ tên bảng hoặc SQL text.
- Thấy một blocker có thể chặn **nhiều waiter**.
- Thấy blocker đang `idle in transaction` hay đang chạy.
- Có thể xác định đúng ứng dụng/role cần liên hệ để xử lý.

### 15.3. Blocker cũng có thể đang chờ một blocker khác

Ví dụ:

```text
Session C chờ khóa của B
Session B chờ khóa của A
Session A đang giữ khóa và idle
```

Nếu chỉ terminate B, C có thể hết chờ B nhưng lại phải đối mặt với tác động khác; nguyên nhân gốc là A. Trước quyết định, hãy theo chuỗi `pg_blocking_pids` để tìm **root blocker** và hiểu quan hệ.

### 15.4. Soft blocker và hàng đợi chờ

Một PID có thể xuất hiện trong `pg_blocking_pids` không chỉ vì nó đang giữ khóa xung đột, mà còn do vị trí/quan hệ trong **hàng đợi** của lock manager. Vì vậy, không nên luôn diễn giải mọi PID trả về là một session chắc chắn đang giữ khóa đã cấp.

Hãy quan sát cả `pg_locks.granted`, `wait_event` và các phiên liên quan.

### 15.5. Prepared transaction có thể không có PID thường

Một prepared transaction có thể giữ khóa trong khi không còn backend xử lý câu truy vấn thông thường. Với những trường hợp đó, công cụ xác định blockers có thể cho kết quả đặc biệt (chẳng hạn PID 0 đại diện prepared transaction).

Nếu không tìm thấy row tương ứng trong `pg_stat_activity`, **đừng tự kết luận blocker đã biến mất**; xem thêm phần prepared transactions.

## 16. `pg_locks`: xem loại khóa, chế độ và trạng thái cấp

`pg_locks` là view của lock manager.

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    l.classid,
    l.objid,
    l.objsubid
FROM pg_locks AS l
WHERE l.pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE datname = current_database()
)
ORDER BY l.pid NULLS LAST, l.granted, l.locktype;
```

Các cột trọng tâm:

- `locktype`: loại đối tượng khóa, như `relation`, `transactionid`, `virtualxid`, `advisory`.
- `mode`: chế độ khóa, ví dụ `RowExclusiveLock`, `AccessExclusiveLock`, `ShareLock`, `ExclusiveLock`.
- `granted = true`: khóa đã được cấp.
- `granted = false`: yêu cầu khóa vẫn đang chờ.
- `waitstart`: thời điểm chờ được ghi nhận, có thể NULL trong một khoảng ngắn hoặc trường hợp khác.
- Các trường định danh khóa: `relation`, `transactionid`, `classid/objid/objsubid` tùy loại.

### 16.1. Không chỉ tìm `locktype = 'tuple'`

Khi một transaction chờ cập nhật hàng do transaction khác sửa, trạng thái chờ có thể hiển thị dưới dạng **transaction ID lock**, chứ không phải luôn là một dòng `tuple` đơn giản biểu diễn hàng bị chặn.

PostgreSQL thường không hiển thị mọi row-level lock đang giữ như một danh sách hàng trong `pg_locks`.

Vì thế, nếu không thấy `locktype = 'tuple'`, không được kết luận “không có row lock contention”.

### 16.2. Quan sát khóa của session đang dùng

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation,
    transactionid
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
```

Query này hiển thị cả một số khóa liên quan bản thân SELECT/truy cập catalog, nên không phải mọi dòng đều là “rò rỉ khóa”.

### 16.3. Xem tên bảng cho relation locks trong database hiện tại

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.database = (
      SELECT oid
      FROM pg_database
      WHERE datname = current_database()
  )
  AND l.relation IS NOT NULL
ORDER BY l.relation, l.pid;
```

Điều kiện lọc database giúp việc chuyển `relation OID` sang `regclass` có ngữ nghĩa phù hợp trong database đang kết nối.

### 16.4. `mode` không tự cho biết cách nhả khóa

Một `AccessExclusiveLock` do `ALTER TABLE` lấy trong transaction có thể được nhả khi transaction kết thúc. Một `ExclusiveLock` với `locktype='advisory'` có thể là khóa theo session hoặc transaction.

Muốn xác định lifecycle, cần biết **nguồn gốc lấy khóa**, transaction/session ownership và cách ứng dụng chạy.

## 17. Nhận diện table lock và DDL đang chặn giao dịch

Không chỉ các câu `UPDATE` mới gây chờ. Một số thao tác DDL cần khóa mạnh.

Ví dụ trên lab:

### 17.1. Session A cố tình giữ khóa bảng

```sql
BEGIN;

LOCK TABLE lock_ops_lab.jobs
IN ACCESS EXCLUSIVE MODE;

-- Để transaction mở trong lab.
```

### 17.2. Session B thử SELECT

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';

SELECT COUNT(*) FROM lock_ops_lab.jobs;
```

`ACCESS EXCLUSIVE` xung đột với các lock modes khác, bao gồm `ACCESS SHARE` do SELECT thông thường cần. Session B có thể chờ rồi nhận lỗi `lock_timeout`.

### 17.3. Kết thúc và cleanup

**Session B:**

```sql
ROLLBACK;
```

**Session A:**

```sql
ROLLBACK;
```

Sau khi A rollback, khóa bảng mạnh được giải phóng.

### 17.4. Vì sao DDL nên có kế hoạch khóa riêng?

Một thay đổi schema có thể chờ một transaction đọc/ghi dài. Trong một số trường hợp, khi DDL đang chờ khóa mạnh, các query mới tới cũng có thể bị ảnh hưởng bởi hàng đợi khóa.

Với migration production, nên cân nhắc:

- Lock mode của DDL cụ thể.
- `lock_timeout` thích hợp.
- Cửa sổ bảo trì và khối lượng request.
- Khả năng rollback/khôi phục.
- Trạng thái transaction mở lâu.
- Chiến lược online/concurrent khi câu lệnh hỗ trợ.
- Kế hoạch retry thay vì giữ khóa DDL chờ vô hạn.

Không chạy DDL có khả năng lấy khóa mạnh trong giờ cao điểm mà không biết hệ quả.

## 18. Timeout giúp tránh phải can thiệp thủ công

Một biện pháp phòng ngừa tốt là thiết lập giới hạn phù hợp **trước khi sự cố xảy ra**.

### 18.1. `lock_timeout`

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

COMMIT;
```

Nếu statement phải chờ khóa lâu hơn ngưỡng phù hợp, PostgreSQL có thể hủy statement với lỗi lock timeout.

Nếu đang ở transaction tường minh và statement lỗi, ứng dụng phải xử lý transaction (thường `ROLLBACK`) thay vì để phiên ở trạng thái aborted.

### 18.2. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT COUNT(*) FROM lock_ops_lab.accounts;

COMMIT;
```

`statement_timeout` đặt giới hạn thời gian thực thi **statement**, có thể bao gồm thời gian chờ khóa.

Khi có cả hai:

```sql
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
```

thì lock timeout có thể cắt một statement đang chờ khóa trước tổng thời gian statement timeout.

Đặt `lock_timeout` bằng hoặc lớn hơn `statement_timeout` thường không mang lại nhiều lợi ích nếu statement timeout luôn có thể xảy ra trước.

### 18.3. `idle_in_transaction_session_timeout`

```sql
SHOW idle_in_transaction_session_timeout;
```

Cấu hình này cho phép PostgreSQL kết thúc một **session idle trong transaction** quá lâu, giúp giảm nguy cơ transaction bỏ quên giữ khóa/snapshot và cản trở VACUUM.

Không nhầm nó với `statement_timeout`:

- `statement_timeout` xử lý statement chạy lâu.
- `idle_in_transaction_session_timeout` xử lý khoảng thời gian **không có statement đang chạy** nhưng transaction vẫn mở.
- Một session không ở trạng thái idle trong transaction không chịu cùng kiểu giới hạn.

### 18.4. `idle_session_timeout`

Một số phiên bản PostgreSQL còn có `idle_session_timeout` để kết thúc session idle ngoài transaction. Trong môi trường connection pool, cấu hình này cần đánh giá kỹ vì pool có thể mong giữ physical connections để tái sử dụng.

Không bật các timeout quá ngắn trên toàn hệ thống rồi coi việc các ứng dụng bị ngắt kết nối bất ngờ là chuyện không đáng kể.

### 18.5. `SET LOCAL` giảm rủi ro rò cấu hình theo session

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

-- Các truy vấn của riêng transaction.

ROLLBACK;
```

`SET LOCAL` có hiệu lực trong transaction hiện tại, sau đó cấu hình trở lại theo scope phù hợp. Điều này thường tốt hơn `SET` cấp session khi connection được pool tái sử dụng và ứng dụng không cleanup session state đầy đủ.

## 19. Phân biệt lỗi cancel, timeout, deadlock và transaction aborted

Những lỗi thường gặp:

| SQLSTATE | Ý nghĩa thường gặp | Hướng phản ứng |
| --- | --- | --- |
| `57014` | `query_canceled`, bao gồm user cancel hoặc statement timeout | Xem nguyên nhân, rollback transaction lỗi nếu có, đánh giá retry |
| `55P03` | `lock_not_available`, ví dụ `NOWAIT` hoặc lock timeout | Xem loại chờ, retry/bỏ lượt theo nghiệp vụ |
| `40P01` | `deadlock_detected` | Rollback và cân nhắc retry toàn transaction |
| `40001` | `serialization_failure` | Retry **toàn transaction** từ bước đọc điều kiện |
| `25P02` | `in_failed_sql_transaction` | Transaction đã lỗi, cần rollback hoặc rollback đến savepoint hợp lệ |
| `08006` | `connection_failure` | Kết nối bị lỗi; phải đánh giá trạng thái transaction và khả năng commit không rõ kết quả |

### 19.1. Cancel không phải deadlock

Nếu Session B chờ A và bạn gửi `pg_cancel_backend(B_PID)`, lỗi thường liên quan cancel. Đây là quyết định dừng một câu truy vấn.

Nếu hai transaction giữ khóa của nhau tạo vòng chờ, PostgreSQL có deadlock detection và có thể hủy một transaction với `40P01`.

Hai tình huống cần điều tra khác nhau:

- Cancel do vận hành hoặc timeout: vì sao statement chạy/chờ quá lâu?
- Deadlock: vì sao các transaction lấy khóa theo thứ tự không nhất quán?

### 19.2. Không retry mù quáng mọi lỗi

Nếu một transaction bị hủy khi đang thực hiện thanh toán, retry sai có thể tạo thanh toán lặp, gửi email hai lần hoặc làm side effect ngoài database nhiều lần.

Chính sách retry phải dựa trên SQLSTATE, bản chất nghiệp vụ, idempotency và khả năng xác định commit đã thành công hay chưa.

## 20. Khi cancel query trong transaction, tại sao cần `ROLLBACK`?

Một transaction tường minh có thể gồm:

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 202;

-- Một câu SQL tiếp theo bị hủy hoặc timeout.
SELECT pg_sleep(60);

-- Transaction chưa được kết thúc.
```

Nếu câu `pg_sleep(60)` bị cancel, PostgreSQL thường đánh dấu transaction tường minh thất bại. Khi ứng dụng gửi:

```sql
SELECT * FROM lock_ops_lab.accounts;
```

nó có thể nhận:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Cần:

```sql
ROLLBACK;
```

Lúc đó các thay đổi chưa commit của transaction, kể cả `+5` trước đó, bị hoàn tác và các khóa transaction được giải phóng.

### 20.1. Tại sao không chỉ hủy SELECT rồi bỏ qua?

Vì transaction có thể vẫn mở, làm:

- Giữ connection trong trạng thái không lành mạnh.
- Giữ hoặc ảnh hưởng các tài nguyên liên quan transaction.
- Chặn những câu SQL mới trong cùng session.
- Kéo dài tuổi transaction trong giám sát.
- Gây lỗi request tiếp theo nếu pool trả connection chưa reset.

### 20.2. Savepoint trong ứng dụng

Nếu đã chủ động đặt savepoint, việc rollback đến savepoint có thể phục hồi transaction cho một bước tùy chọn bị cancel/lỗi, nhưng:

- Không được dùng nó để bỏ qua một bước bắt buộc của nghiệp vụ.
- Cần hiểu những lock nào có trước/sau savepoint.
- Cần quyết định có nên tiếp tục transaction hay rollback toàn bộ.

Với thao tác nhiều bảng quan trọng, rollback toàn transaction và thử lại có kiểm soát thường dễ chứng minh tính đúng hơn là cố giữ transaction sau một lỗi không rõ trạng thái.

## 21. `pg_terminate_backend` và trạng thái commit mơ hồ

Một trường hợp phức tạp:

```text
Ứng dụng                       PostgreSQL
   |                               |
   | COMMIT ----------------------> |
   |                               | Có thể đã ghi nhận commit
   |  (mất kết nối tại đây)         |
   X                               |
   | Không nhận được phản hồi       |
```

Ứng dụng không thể chỉ suy từ lỗi kết nối rằng transaction **chắc chắn chưa commit**.

Khi backend đã hoàn tất `COMMIT` trước thời điểm bị ngắt, thay đổi đã commit vẫn tồn tại. Khi backend bị terminate trước commit và transaction còn mở, thay đổi chưa commit được rollback.

### 21.1. Vì sao điều này quan trọng với vận hành?

Nếu một operator terminate một backend gần thời điểm commit, client có thể nhận lỗi mất kết nối rồi tự gửi lại request.

Nếu request là “chuyển 100.00” mà thiếu idempotency key, retry mù quáng có thể tạo **hai giao dịch khác nhau** dù mỗi giao dịch riêng đều ACID.

### 21.2. Cách thiết kế an toàn

Với workflow quan trọng:

1. Mỗi hành động nghiệp vụ có **request ID ổn định**.
2. Database lưu được trạng thái xử lý theo request ID, có ràng buộc duy nhất.
3. Khi kết nối mất hoặc commit không rõ kết quả, ứng dụng **tra cứu/đối soát** trước khi tạo hành động mới.
4. Việc retry phải giữ nguyên request ID và kiểm tra payload trùng khớp.
5. Side effect bên ngoài dùng idempotency hoặc outbox/fencing thích hợp.

### 21.3. Không dùng terminate như một API rollback được bảo đảm tuyệt đối

`pg_terminate_backend` yêu cầu dừng backend. Nó không cung cấp một giao thức “rollback tất cả thay đổi liên quan nghiệp vụ xuyên các dịch vụ” và không hứa giúp client phân biệt chắc chắn commit thành công hay thất bại khi mất phản hồi.

## 22. Nguyên tắc can thiệp an toàn vào PID

Trước khi gửi tín hiệu, cần xác minh **ít nhất**:

- PID hiện tại đúng backend cần xử lý.
- Database/role/application/client tương ứng với incident.
- `backend_start` để giảm nhầm lẫn PID được tái sử dụng.
- Backend có phải client session thông thường hay tiến trình hệ thống đặc biệt.
- `state`: active, idle, idle in transaction, aborted?
- `xact_start` và `query_start`.
- Query thật sự đang chờ gì.
- `pg_blocking_pids` cho waiter nào.
- Blocker có những transaction quan trọng nào chưa commit.
- Ảnh hưởng với ứng dụng, connection pool, retry và dữ liệu bên ngoài.

### 22.1. Kiểm tra riêng một PID

Ví dụ **chỉ đọc**, không gửi tín hiệu:

```sql
SELECT
    pid,
    backend_start,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

Thay `23456` bằng PID bạn đã thu thập từ giám sát; con số trong bài chỉ là ví dụ.

### 22.2. Vì sao phải kiểm tra `backend_start`?

PID của hệ điều hành có thể được **tái sử dụng** sau khi một backend kết thúc. Một PID bạn lấy từ ảnh chụp cũ có thể không còn trỏ tới đúng session khi chuẩn bị terminate.

So lại PID + `backend_start` và thông tin owner **ngay trước khi hành động**. Điều này giảm rủi ro, dù không thể xóa bỏ hoàn toàn mọi race giữa kiểm tra và gửi tín hiệu.

### 22.3. Tránh thao tác hàng loạt theo điều kiện quá rộng

Rất nguy hiểm nếu chạy một câu kiểu:

```sql
-- KHÔNG CHẠY TRONG PRODUCTION:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active';
```

Nó có thể ngắt những tác vụ hợp lệ, migration, thao tác quan trọng hoặc chính những backend cần giữ để hệ thống hoạt động.

Thậm chí điều kiện `state = 'idle in transaction'` cũng chưa đủ để terminate hàng loạt: có thể có transaction hợp lệ, prepared work hoặc hoạt động đã được quản lý theo một giao thức riêng.

### 22.4. Không tự terminate hệ thống/replication/autovacuum

`pg_stat_activity.backend_type` giúp phân biệt client backend và những loại backend khác. Hủy nhầm một tiến trình replication, autovacuum hoặc cơ chế quản trị có thể gây hệ quả ngoài incident hiện tại.

Chỉ thao tác trên backend **được xác định cụ thể** và nằm trong phạm vi quyền/phê duyệt vận hành phù hợp.

## 23. Quyền cần thiết để cancel hoặc terminate

Không phải mọi user có quyền SELECT đều có quyền gửi tín hiệu tới một backend khác.

Trong PostgreSQL, quyền signal bị kiểm soát theo role và quyền quản trị. Những role có đặc quyền phù hợp, như role được cấp `pg_signal_backend` hoặc superuser trong phạm vi quy định, có thể signal những backend được phép.

Các điểm cần nhớ:

- Một user thường không được phép tùy ý ngắt session của role khác.
- `pg_signal_backend` không có nghĩa được phép hủy mọi backend superuser mà không có giới hạn.
- Quy tắc chính xác về quyền có thể phụ thuộc phiên bản và loại backend.
- Quyền SELECT `pg_stat_activity` không tự cấp quyền terminate.

### 23.1. Không cấp quyền terminate rộng cho ứng dụng web

Một HTTP request thông thường không nên được phép gửi `pg_terminate_backend` lên bất kỳ PID nào mà người dùng cung cấp.

Nếu cần quản trị sự cố, sử dụng role và quy trình riêng với:

- Xác thực, phân quyền.
- Audit logs.
- Xác minh mục tiêu.
- Giới hạn đối tượng được phép.
- Quy trình escalation khi ảnh hưởng production.

### 23.2. Tách vai trò giám sát với vai trò can thiệp

Một role giám sát có thể chỉ cần quyền quan sát các session trong phạm vi được phép. Hành động cancel/terminate nên được giới hạn hơn.

Tránh lưu credential superuser trong service chỉ để dừng một query chậm theo request người dùng.

## 24. Prepared transaction: khóa không gắn với một PID còn sống

Đây là trường hợp nâng cao nhưng rất quan trọng khi xử lý tình huống “không thấy blocker trong pg_stat_activity”.

PostgreSQL hỗ trợ **two-phase commit (2PC)**, trong đó một transaction có thể đi vào trạng thái prepared:

```sql
PREPARE TRANSACTION 'some-gid';
```

Sau khi đã prepared, transaction có thể giữ những khóa cần thiết trong khi không còn backend đang trực tiếp chạy transaction đó.

### 24.1. Quan sát prepared transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
```

Nếu hệ thống có prepared transaction tồn tại lâu, nó có thể giữ các khóa cần thiết và chặn workload khác.

### 24.2. Không có PID để cancel/terminate đơn giản

Một prepared transaction có thể được đại diện trong lock manager theo cách không gắn với một PID client đang chạy thông thường. Vì vậy:

- Không thể chỉ tìm PID trong `pg_stat_activity` rồi cancel.
- Không nên suy đoán một `pg_locks.pid IS NULL` là lỗi hiển thị.
- Cần tìm hiểu xem blocker có phải prepared transaction hay không.

### 24.3. Kết thúc 2PC cần quyết định nghiệp vụ

Hai lệnh:

```sql
COMMIT PREPARED 'some-gid';
ROLLBACK PREPARED 'some-gid';
```

**Không phải câu lệnh cleanup có thể thử tùy tiện.**

- `COMMIT PREPARED` xác nhận những thay đổi của prepared transaction.
- `ROLLBACK PREPARED` hủy những thay đổi đó.
- Với giao thức 2PC, quyết định commit/rollback có thể thuộc về **transaction coordinator** bên ngoài và những tài nguyên khác.

Một operator không có đầy đủ thông tin về coordinator tuyệt đối không nên tự chọn commit hay rollback chỉ để giải phóng khóa. Cần điều tra owner, GID, trạng thái coordinator, tính nhất quán các hệ thống tham gia, và xin quyết định vận hành thích hợp.

### 24.4. Không cần tự bật 2PC để làm bài thí nghiệm

`max_prepared_transactions` có thể được cấu hình bằng 0 nếu hệ thống không dùng prepared transactions. Không chỉnh cấu hình hay tạo prepared transaction trong môi trường dùng chung chỉ để thử bài này.

Trong thực tế, **prepared transaction tồn đọng** là một tình huống cần quan sát và xử lý riêng, không thuộc cùng nhóm với một HTTP session bình thường bị treo.

## 25. Mẫu quy trình xử lý sự cố lock wait

Một quy trình rõ ràng giúp tránh hủy nhầm backend:

<escape>**Bước 1. Xác nhận triệu chứng.**</escape>

- Request nào bị chậm hoặc timeout?
- Có `wait_event_type = 'Lock'` không?
- Có thông báo `55P03`, `57014` hay `40P01` không?
- Có bao nhiêu user/job bị ảnh hưởng và SLA nào đang bị vi phạm?

<escape>**Bước 2. Thu thập bằng chứng trước khi can thiệp.**</escape>

- `pg_stat_activity` của các backend liên quan.
- `pg_blocking_pids` để xác định waiters/blockers.
- `pg_locks` và lock modes/granted.
- PID, database, user, application, backend_start, xact_start.
- Query và connection owner nếu có.

<escape>**Bước 3. Xác định loại blocker.**</escape>

- Statement đang chạy?
- `idle in transaction`?
- Session advisory lock?
- Prepared transaction?
- DDL/migration có kế hoạch?
- Vòng deadlock đã được PostgreSQL xử lý?

<escape>**Bước 4. Chọn biện pháp ít phá hủy nhất.**</escape>

- Nếu request chờ đã bị người dùng hủy, cancel **waiter** có thể đủ.
- Nếu app sở hữu transaction vẫn hoạt động, yêu cầu nó commit/rollback.
- Nếu có transaction bị bỏ quên, sửa/khôi phục client và cân nhắc timeout.
- Nếu session không hợp tác và ảnh hưởng nghiêm trọng, **cân nhắc terminate đúng backend** sau khi đánh giá rủi ro.
- Nếu là prepared transaction, theo quy trình 2PC.
- Nếu là session advisory lock còn sống, ưu tiên chính owner unlock.

<escape>**Bước 5. Xác minh hậu quả.**</escape>

- Lock wait có giảm không?
- Backend mong muốn đã kết thúc chưa?
- Các transaction bị ảnh hưởng có rollback/commit theo ý định không?
- Ứng dụng đã retry hoặc phục hồi ra sao?
- Có transaction/lock mới tiếp tục chặn không?

<escape>**Bước 6. Khắc phục nguyên nhân gốc.**</escape>

- Transaction quá dài?
- Exception không rollback?
- Session advisory lock leak?
- Migration dùng lock mode quá mạnh?
- Query thiếu index khiến khóa kéo dài?
- Có deadlock do thứ tự khóa?
- Connection pool trả connection chưa reset?
- Retry không có idempotency?

Quy trình này giúp can thiệp có kiểm soát, thay vì “kill hết query lâu” và để nguyên bug.

## 26. Khi nào không nên cancel hoặc terminate?

### 26.1. Query chỉ chậm nhưng không chờ khóa

Nếu `wait_event_type` không phải `Lock`, có thể query đang chờ I/O, tính toán, gửi dữ liệu cho client hoặc làm công việc hợp lệ.

Không xem mọi “query hơn 30 giây” là lỗi khóa.

### 26.2. Transaction của người dùng đang ở điểm commit nhạy cảm

Việc terminate gần thời điểm commit có thể làm client không biết kết quả đã commit hay chưa.

Với hệ thống thanh toán, đối soát hoặc tạo chứng từ, cần hiểu idempotency và quy trình phục hồi trước khi can thiệp.

### 26.3. Backup, migration, bảo trì đang chạy theo kế hoạch

Một backend có query dài có thể là một phần của quy trình được phê duyệt. Nếu cần ngừng, nên phối hợp với owner/công cụ triển khai có rollback/cleanup phù hợp.

### 26.4. Không hiểu khóa thuộc loại nào

Nếu đang thấy `pg_locks` với `locktype = 'transactionid'`, chưa đủ để suy luận câu lệnh chính xác gây chặn. Cần tìm wait graph và context.

Nếu thấy prepared transaction, không thể thay bằng việc terminate một PID ngẫu nhiên.

### 26.5. Chưa có bằng chứng về quyền sở hữu session

Một connection có thể đã được pool tái sử dụng; một PID từ log cũ không nhất thiết vẫn là backend của cùng request. Cần xác minh lại ở thời điểm can thiệp.

## 27. Dùng `NOWAIT` và `SKIP LOCKED` để tránh chờ không cần thiết

Trong một số workflow, tốt hơn là **không chờ**, thay vì để chờ lâu rồi phải cancel thủ công.

### 27.1. `FOR UPDATE NOWAIT`

```sql
BEGIN;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;

ROLLBACK;
```

Nếu hàng đang bị khóa không tương thích, PostgreSQL có thể trả lỗi `lock_not_available` ngay thay vì chờ lâu.

Ứng dụng phải có chính sách xử lý `NOWAIT` không lấy được khóa.

### 27.2. `FOR UPDATE SKIP LOCKED`

Phù hợp với một số hàng đợi công việc:

```sql
BEGIN;

SELECT job_id, status
FROM lock_ops_lab.jobs
WHERE status = 'PENDING'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;

ROLLBACK;
```

Một worker có thể bỏ qua hàng đang bị worker khác khóa và chọn hàng khác.

### 27.3. Không dùng SKIP LOCKED trong mọi nghiệp vụ

Nếu bạn cần tổng tiền của **tất cả tài khoản**, bỏ qua tài khoản đang khóa có thể cho kết quả sai.

`SKIP LOCKED` tạo một tầm nhìn không đầy đủ có chủ đích đối với tập hàng đang chờ; nó thích hợp cho worker queue hơn là báo cáo tài chính cần đủ hàng.

### 27.4. Phân biệt `NOWAIT` với timeout

- `NOWAIT`: không chờ để lấy row lock tương ứng.
- `lock_timeout`: cho phép một khoảng chờ có giới hạn.
- `pg_cancel_backend`: tác động bên ngoài tới backend đang chạy.
- `pg_terminate_backend`: ngắt backend, mạnh hơn cancel.

Chọn cơ chế kiểm soát ngay trong truy vấn/ứng dụng thường hiệu quả hơn một quy trình chữa cháy bằng signal.

## 28. Connection pool: vì sao rò transaction làm nhiều request bị chặn?

Một connection pool giữ physical PostgreSQL connections để tái sử dụng. Nếu code ứng dụng:

```text
getConnection()
setAutoCommit(false)
UPDATE ...
exception xảy ra
không rollback
return connection to pool
```

thì connection có thể quay về pool trong trạng thái transaction chưa hoàn tất hoặc không lành mạnh, tùy thư viện/pool và cách sử dụng.

Kết quả:

- Request khác dùng connection đó có thể thấy transaction đang aborted.
- Backend vẫn giữ tài nguyên/khóa không mong muốn.
- `pg_stat_activity` xuất hiện `idle in transaction`.
- Workload khác phải chờ những khóa do request trước để lại.

### 28.1. Phải rollback trong nhánh lỗi

Mẫu Java/JDBC:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountService {
    private final DataSource dataSource;

    public AccountService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void applyChange() throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                // Các PreparedStatement sử dụng đúng conn
                // và thực hiện workflow trong transaction này.
                executeBusinessStatements(conn);

                conn.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    private void executeBusinessStatements(Connection conn)
            throws SQLException {
        try (var ps = conn.prepareStatement(
                "UPDATE lock_ops_lab.accounts " +
                "SET balance = balance + 1 " +
                "WHERE account_id = ?")) {
            ps.setInt(1, 101);
            int updated = ps.executeUpdate();
            if (updated != 1) {
                throw new SQLException(
                    "Không tìm thấy đúng một tài khoản"
                );
            }
        }
    }
}
```

Ví dụ này mô tả **cleanup transaction**. Trong production cần kiểm tra logic nghiệp vụ và ứng dụng quản lý transaction của framework; không trộn commit thủ công với transaction manager khác trên cùng connection nếu không hiểu hợp đồng framework.

### 28.2. JDBC cancellation khác backend termination

`Statement.cancel()` trong JDBC có thể yêu cầu driver hủy statement đang chạy theo cơ chế nó hỗ trợ. `Connection.close()` với pooled connection có thể **chỉ trả connection về pool**, không đồng nghĩa ngắt physical backend ngay lập tức.

Đừng xem `close()` ở client như bằng chứng một session PostgreSQL và mọi session-level advisory locks đã biến mất. Phải hiểu contract của pool/driver và cách reset connection.

### 28.3. JDBC transaction timeout và lock timeout

Framework có thể có transaction timeout riêng. Nhưng:

- Timeout của HTTP request không tự bảo đảm SQL trên PostgreSQL đã cancel.
- Timeout của pool checkout không đồng nghĩa lock timeout trên server.
- Transaction timeout của framework có thể đánh dấu rollback-only hoặc hủy kết nối theo cấu hình.
- Muốn bảo vệ lock wait, vẫn cần thiết kế và giám sát server-side phù hợp.

### 28.4. Sau `pg_terminate_backend`, pool phải bỏ connection chết

Nếu operator terminate một backend đang được pool quản lý, driver sẽ nhận lỗi kết nối. Pool phải phát hiện connection đó không còn hợp lệ và cung cấp connection mới.

Không cố tiếp tục dùng transaction cũ sau một backend termination. Bất kỳ retry nào cũng phải mở transaction mới, đọc lại trạng thái nghiệp vụ và xử lý commit mơ hồ khi có.

## 29. Advisory locks với connection pool và transaction pooling

### 29.1. Session advisory lock không gắn với request HTTP

`pg_advisory_lock(...)` gắn với **physical backend**. Request HTTP đã trả response nhưng backend pool vẫn sống thì khóa vẫn có thể tồn tại.

Ví dụ:

```text
Request A mượn connection #7
A gọi pg_advisory_lock(247,1001)
A gặp exception nhưng quên unlock
Pool trả connection #7 về danh sách rảnh

Request B mượn connection #7
Backend vẫn có session advisory lock
```

Một lần `ROLLBACK` không sửa được vấn đề nếu khóa là session-level. Cần unlock trong cleanup trên đúng backend.

### 29.2. Transaction-level advisory lock rõ vòng đời hơn

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 1001);

-- Các thao tác database cần độc quyền.

COMMIT;
```

Khi transaction thực sự kết thúc, xact advisory lock được nhả. Điều này thường phù hợp hơn với các workflow transaction ngắn dùng pool.

### 29.3. PgBouncer transaction pooling

Khi pool theo transaction, cùng client logic có thể sử dụng **nhiều PostgreSQL backend** ở hai transaction khác nhau.

Vì vậy, mẫu:

```text
Transaction 1: session lock được lấy trên backend A
Transaction 2: unlock chạy trên backend B
```

là không an toàn. Backend B không giữ session advisory lock của A.

Dùng transaction-level locks **trong cùng transaction** khi cơ chế pooling hỗ trợ, hoặc thiết kế ownership bên ngoài/đổi cấu hình kết nối theo yêu cầu.

### 29.4. Không dùng terminate để “dọn pool” hàng loạt

Nếu pool gây leak transaction hoặc session lock, xử lý root cause ở ứng dụng/pool. Terminate mọi connection theo tên ứng dụng trong production có thể gây đứt hàng loạt request đang hợp lệ, tạo retry storm và tăng tải database.

Một quy trình có kiểm soát có thể cần drain traffic, rollback/cancel theo owner, xác minh trạng thái rồi mới giải phóng những session cụ thể.

## 30. Deadlock: PostgreSQL có thể tự hủy một transaction

Deadlock là vòng chờ khóa:

```text
T1 giữ row A ------> muốn row B
    ^                    |
    |                    v
T2 muốn row A <------ giữ row B
```

PostgreSQL có cơ chế phát hiện deadlock và có thể hủy một transaction để phá vòng chờ, thường báo:

```text
SQLSTATE 40P01: deadlock_detected
```

### 30.1. Thí nghiệm hai session

**Session A:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

**Session B:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;
```

Sau đó A cố cập nhật tài khoản 202, còn B cố cập nhật tài khoản 101, theo thứ tự thao tác được điều phối:

```sql
-- A:
UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;

-- B:
UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

Một trong hai transaction có thể nhận lỗi deadlock. Kết thúc/rollback những transaction còn lại theo kế hoạch thử nghiệm.

### 30.2. Vì sao không cần operator terminate cả hai?

PostgreSQL có deadlock detector. Khi phát hiện vòng chờ thật sự, hệ thống có thể tự chọn một giao dịch làm nạn nhân để các giao dịch khác tiếp tục.

Người vận hành cần:

- Kiểm tra log và SQLSTATE.
- Xem các transaction lấy khóa theo thứ tự nào.
- Giảm thời gian giữ khóa.
- Thêm retry toàn transaction có giới hạn cho `40P01` khi nghiệp vụ an toàn.
- Không can thiệp hàng loạt chỉ vì thấy một deadlock đã được xử lý.

### 30.3. `deadlock_timeout` không phải timeout chờ khóa thông thường

`deadlock_timeout` ảnh hưởng thời gian chờ trước khi PostgreSQL kiểm tra deadlock (và liên quan log lock waits). Nó **không phải** một giới hạn tổng thời gian chờ khóa như `lock_timeout`.

Không đặt `deadlock_timeout` rồi cho rằng mọi truy vấn chờ khóa sẽ bị hủy sau thời gian đó.

## 31. Logging và theo dõi sự cố khóa

Các cài đặt đáng biết:

```sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
SHOW lock_timeout;
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
```

### 31.1. `log_lock_waits`

Khi cấu hình ghi log chờ khóa và thời gian chờ vượt ngưỡng liên quan, PostgreSQL có thể ghi thông tin lock wait hữu ích để điều tra.

Điều này giúp thấy:

- Truy vấn nào chờ.
- Thời điểm/độ dài chờ.
- Đối tượng và mode khóa liên quan.
- Các chi tiết blocker tùy log/config.

Không nên bật logging quá chi tiết trên hệ thống bận mà không đánh giá dung lượng, tính nhạy cảm của câu SQL và chi phí vận hành.

### 31.2. Tìm transaction lâu

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Một transaction lâu chưa chắc đang chặn ai, nhưng là **đối tượng cần quan sát**, nhất là nếu `idle in transaction` hoặc giữ snapshot cũ làm ảnh hưởng VACUUM.

### 31.3. Không chỉ nhìn số lượng locks

Một backend có nhiều relation locks hợp lệ trong một query phức tạp. Một backend giữ **một khóa duy nhất** nhưng là `ACCESS EXCLUSIVE` trên bảng quan trọng có thể gây ảnh hưởng lớn hơn.

Cần kết hợp lock mode, wait graph, thời gian, tần suất, nghiệp vụ và quy mô tác động.

### 31.4. Snapshot quan sát không vĩnh viễn chính xác

`pg_stat_activity` và `pg_locks` phản ánh trạng thái tại thời điểm quan sát, vốn có thể thay đổi ngay sau đó. Query text có thể bị cắt bớt theo `track_activity_query_size` và quyền xem bị giới hạn.

Vì vậy, thu thập bằng chứng và xác minh lại ngay trước can thiệp. Đừng tạo quyết định terminate từ một screenshot cũ.

## 32. Lập kịch bản vận hành an toàn theo cấp độ tác động

Không có một “lệnh thần kỳ” phù hợp mọi tình huống. Có thể tổ chức các mức phản ứng:

| Mức | Hành động | Rủi ro |
| --- | --- | --- |
| 0 | Chỉ quan sát `pg_stat_activity` / `pg_locks` | Thấp |
| 1 | Chờ ngắn, liên hệ owner, yêu cầu client kết thúc transaction | Thường thấp nếu workflow được quản lý |
| 2 | Cancel **đúng statement của waiter** đã vượt SLA | Ảnh hưởng request bị hủy |
| 3 | Yêu cầu owner rollback transaction blocker theo quy trình | Có thể hoàn tác việc chưa commit |
| 4 | Cancel statement đang chạy của blocker và xác minh rollback | Ảnh hưởng transaction/blocker |
| 5 | Terminate backend blocker đã xác minh | Ngắt kết nối, rollback chưa commit, tác động đến retry/side effect |
| Đặc biệt | Xử lý prepared transaction 2PC | Cần quyết định coordinator, rủi ro nhất quán phân tán |

**Không tự động nâng cấp mức chỉ vì một lệnh không đổi trạng thái ngay**. Ví dụ cancel một blocker `idle in transaction` không phù hợp về bản chất; cần xác định lại nguyên nhân.

### 32.1. Sau khi terminate, đừng kết luận sự cố kết thúc ngay

Kiểm tra:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

Đối chiếu số waiter còn bị chặn, backend cũ còn tồn tại không, ứng dụng có mở lại transaction gây chặn ngay không.

### 32.2. Ghi lại dấu vết

Với sự cố production, nên ghi:

- Thời điểm phát hiện và tác động.
- Waiting PID, blocking PID, backend_start.
- Database/role/application.
- Loại khóa/mode.
- Bằng chứng trước can thiệp.
- Người hoặc quy trình cho phép hành động.
- Lệnh cancel/terminate được thực hiện.
- Kết quả sau can thiệp.
- Kế hoạch sửa root cause.

Đây là hoạt động vận hành bình thường giúp phân biệt một thao tác hợp lệ với sự cố phát sinh sau đó.

## 33. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Thấy query chậm là terminate ngay | Hủy công việc hợp lệ, tăng retry | Xem wait events và blockers |
| Chỉ xem waiter mà không xem blocker | Sự cố lặp do root blocker còn giữ khóa | Dùng `pg_blocking_pids` |
| Cancel waiter rồi tưởng khóa của blocker đã nhả | Các request khác vẫn chờ | Kết thúc/điều tra holder |
| Cancel `idle in transaction` để nhả lock | Transaction vẫn có thể mở | Yêu cầu rollback/commit hoặc cân nhắc terminate |
| `pg_cancel_backend` trả true là lock đã nhả | Chỉ xác nhận yêu cầu signal | Recheck `pg_locks`/`pg_stat_activity` |
| `pg_terminate_backend` trả true nghĩa session chắc chắn đã biến mất | Signal có thể chưa được backend xử lý | Xác minh backend thực sự kết thúc |
| Terminate PID lấy từ log cũ | PID có thể được tái sử dụng | Recheck PID + backend_start |
| Terminate hàng loạt tất cả backend active | Ngắt workload hợp lệ | Chỉ can thiệp PID đã xác minh |
| Chỉ dựa vào `application_name` | Tên có thể trùng hoặc do client đặt sai | Xem database/user/backend_start |
| Thấy `state='active'` là dùng CPU | Có thể đang đợi Lock/IO | Đọc `wait_event_type` |
| Thấy `idle in transaction` là luôn có khóa nguy hiểm | Cần xem loại lock và impact thực tế | Phân tích wait graph |
| Không rollback sau query canceled | Transaction bị aborted và giữ tài nguyên | Rollback/savepoint phù hợp |
| COMMIT transaction chưa hoàn tất chỉ để nhả lock | Xác nhận dữ liệu nghiệp vụ sai | Yêu cầu workflow commit/rollback đúng |
| Nghĩ `ROLLBACK` nhả session advisory lock | Khóa session vẫn tồn tại | Unlock trên đúng backend |
| Một lần unlock luôn nhả sạch advisory lock | Khóa có thể reentrant | Theo dõi số lần acquire/unlock |
| Gọi `pg_advisory_unlock_all` trên connection dùng chung | Nhả khóa không thuộc mình | Cleanup đúng key |
| Kỳ vọng `pg_advisory_unlock` nhả xact lock | Hàm chỉ tác động session advisory | Commit/rollback transaction |
| `COMMIT` sau `pg_advisory_xact_lock` trong autocommit riêng | Khóa nhả trước phần việc tiếp theo | Gộp critical section trong một transaction |
| Tưởng `pg_locks` có mọi row lock dưới dạng `tuple` | Bỏ sót wait trên transactionid | Dùng blocker graph và xem nhiều locktype |
| Tự JOIN `pg_locks` quá đơn giản | Ghép nhầm lock modes/IDs | Ưu tiên `pg_blocking_pids` |
| Cố terminate prepared transaction bằng PID bất kỳ | Không nhắm đúng 2PC owner | Xem `pg_prepared_xacts` và coordinator |
| Tự `ROLLBACK PREPARED` để hết khóa | Có thể phá giao thức 2PC | Quy trình quyết định nghiệp vụ |
| Dùng `deadlock_timeout` như lock timeout | Query vẫn có thể chờ lâu | Dùng `lock_timeout` |
| `SKIP LOCKED` cho truy vấn cần đủ hàng | Bỏ sót dữ liệu | Chỉ dùng khi bỏ qua hàng là hợp lệ |
| Retry request thanh toán ngay khi mất kết nối | Có thể thực hiện hai lần | Idempotency và đối soát |
| Dùng timeout nhưng không cleanup JDBC | Pool giữ transaction lỗi | Rollback và trả connection đúng |
| Hủy query xong không kiểm tra lại | Root cause còn tồn tại | Re-observe, điều tra và sửa |

## 34. Bài tập thực hành và đáp án

Các bài dưới dùng schema `lock_ops_lab`, trừ nơi ghi rõ cần kiến thức vận hành. Không chạy cancel/terminate trên môi trường ngoài lab.

### Bài 1. Khi nào row lock từ `UPDATE` được nhả?

**Đáp án:** thông thường khi transaction sở hữu nó kết thúc bằng `COMMIT` hoặc `ROLLBACK`, không phải ngay sau khi `UPDATE` hoàn thành nếu transaction tường minh vẫn mở.

### Bài 2. Chuyển từ autocommit sang transaction tường minh làm khác điều gì?

**Đáp án:** ở autocommit, mỗi statement riêng thường kết thúc transaction của nó; trong transaction tường minh, khóa theo transaction có thể được giữ qua nhiều statement cho tới commit/rollback.

### Bài 3. Khóa bảng trong transaction có thể giải phóng bằng gì?

```sql
BEGIN;

LOCK TABLE lock_ops_lab.jobs
IN SHARE ROW EXCLUSIVE MODE;

ROLLBACK;
```

**Đáp án:** rollback kết thúc transaction và giải phóng khóa bảng do transaction này giữ.

### Bài 4. Cancel statement có tự COMMIT không?

**Đáp án:** không. Cancel ngừng statement hiện tại; nó không tự xác nhận những thay đổi đang chờ commit.

### Bài 5. `pg_cancel_backend` khác `pg_terminate_backend` thế nào?

**Đáp án:** cancel yêu cầu hủy statement đang chạy và giữ connection tồn tại; terminate yêu cầu kết thúc session, dẫn đến ngắt connection và rollback transaction chưa commit khi backend chấm dứt.

### Bài 6. Session B đang chờ A. Cancel B có giải phóng khóa của A không?

**Đáp án:** không. B không còn đợi statement bị hủy, nhưng A vẫn là holder cho đến khi transaction/session sở hữu khóa được kết thúc hoặc unlock đúng cơ chế.

### Bài 7. A đã UPDATE, giờ `idle in transaction`. Cancel A có bảo đảm nhả row lock không?

**Đáp án:** không. Không có statement đang chạy để cancel theo ý nghĩa thông thường; transaction A phải commit/rollback hoặc backend thực sự kết thúc.

### Bài 8. Một câu `pg_cancel_backend(pid)` trả true có đủ kết luận backend đã giải phóng khóa chưa?

**Đáp án:** không. Nó không đảm bảo transaction đã kết thúc. Kiểm tra lại `pg_stat_activity`, `pg_locks` và blockers.

### Bài 9. Terminate backend có rollback những transaction đã commit hôm qua không?

**Đáp án:** không. Nó ảnh hưởng session hiện tại và transaction chưa commit khi backend kết thúc; những transaction đã commit trước đó vẫn được lưu theo bảo đảm hệ thống.

### Bài 10. Nếu client mất kết nối đúng lúc COMMIT thì luôn chắc chắn rollback?

**Đáp án:** không. COMMIT có thể đã thành công trên server trước khi phản hồi mất; cần idempotency/đối soát trước khi retry nghiệp vụ.

### Bài 11. Tìm PID của chính kết nối

```sql
SELECT pg_backend_pid();
```

**Đáp án:** hàm trả PID PostgreSQL backend hiện tại. Hai connection độc lập cần có PID khác nhau khi thực hành tranh chấp.

### Bài 12. Tìm các backend chờ khóa

```sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

**Đáp án:** query liệt kê các session đang chờ sự kiện thuộc nhóm Lock tại thời điểm quan sát.

### Bài 13. Xem PID nào chặn một waiter

```sql
SELECT pg_blocking_pids(34567);
```

**Đáp án:** thay 34567 bằng PID waiter thật; kết quả là mảng PID blockers theo lock manager.

### Bài 14. Xem thông tin của một blocker

```sql
SELECT
    pid,
    backend_start,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

**Đáp án:** truy vấn giúp xác minh đúng phiên trước khi quyết định xử lý; cần kiểm tra lại sát thời điểm gửi tín hiệu.

### Bài 15. Vì sao nên xem `backend_start`?

**Đáp án:** PID có thể được tái sử dụng sau khi backend cũ kết thúc. Kết hợp PID với thời điểm tạo backend và owner giúp giảm rủi ro thao tác nhầm session.

### Bài 16. `pg_locks.granted = false` nói lên điều gì?

**Đáp án:** yêu cầu khóa chưa được cấp, thường là đang chờ; cần kết hợp `locktype`, `mode`, `waitstart` và blocker graph.

### Bài 17. Vì sao không luôn thấy row-level lock trong `pg_locks`?

**Đáp án:** PostgreSQL không biểu diễn tất cả khóa hàng đã cấp thành các dòng `tuple` dễ đọc. Waiter có thể thể hiện chờ `transactionid` của transaction đang sửa hàng.

### Bài 18. SQLSTATE khi statement bị user cancel?

**Đáp án:** thường `57014` (`query_canceled`).

### Bài 19. SQLSTATE khi transaction đã lỗi mà tiếp tục SELECT?

**Đáp án:** `25P02` (`in_failed_sql_transaction`). Cần rollback hoặc xử lý savepoint hợp lệ.

### Bài 20. SQLSTATE khi deadlock?

**Đáp án:** `40P01`. PostgreSQL có thể hủy một transaction để phá vòng chờ; ứng dụng thường rollback/retry toàn transaction khi nghiệp vụ cho phép.

### Bài 21. SQLSTATE khi lock timeout/NOWAIT không lấy được khóa?

**Đáp án:** thường `55P03` (`lock_not_available`), cần xử lý theo SLA và loại nghiệp vụ.

### Bài 22. Khóa session advisory có tự nhả khi ROLLBACK không?

```sql
SELECT pg_advisory_lock(247, 11);

BEGIN;
SELECT 1;
ROLLBACK;
```

**Đáp án:** không. Trong chính session sở hữu khóa phải gọi:

```sql
SELECT pg_advisory_unlock(247, 11);
```

### Bài 23. Transaction advisory lock có tự nhả khi COMMIT không?

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 12);

COMMIT;
```

**Đáp án:** có. Không cần `pg_advisory_xact_unlock`.

### Bài 24. `pg_advisory_unlock_all()` có giải phóng session lock của backend khác không?

**Đáp án:** không. Nó chỉ áp dụng cho session-level advisory locks của chính backend gọi hàm, và có thể nguy hiểm nếu backend đang dùng nhiều locks thuộc các thư viện khác nhau.

### Bài 25. Vì sao một lần `pg_advisory_unlock` có thể chưa nhả hết khóa?

**Đáp án:** session có thể acquire cùng key nhiều lần; mỗi lượt unlock chỉ giải phóng một mức ownership tương ứng.

### Bài 26. Khi rollback về savepoint, tất cả khóa transaction luôn mất?

**Đáp án:** không. Những khóa lấy trước savepoint có thể vẫn thuộc transaction cha; một số khóa lấy sau savepoint được giải phóng khi rollback về mốc đó.

### Bài 27. `lock_timeout` khác `statement_timeout`?

**Đáp án:** lock timeout giới hạn thời gian chờ khóa, statement timeout giới hạn thời gian thực thi statement, có thể gồm thời gian chờ. Hai cấu hình không phải một.

### Bài 28. `idle_in_transaction_session_timeout` giúp gì?

**Đáp án:** có thể chấm dứt phiên idle trong transaction quá lâu, hạn chế transaction bỏ quên giữ khóa/snapshot và cản trở VACUUM; cần cấu hình cẩn thận với ứng dụng/pool.

### Bài 29. `deadlock_timeout` có phải timeout để hủy mọi lock wait?

**Đáp án:** không. Nó liên quan thời điểm kiểm tra deadlock và logging; muốn giới hạn chờ khóa cần `lock_timeout` hoặc cơ chế phù hợp khác.

### Bài 30. Khi nào nên dùng `FOR UPDATE NOWAIT`?

**Đáp án:** khi ứng dụng cần biết ngay rằng một hàng đang bị khóa và muốn xử lý “bận” thay vì chờ. Nếu không lấy được, phải xử lý lỗi nghiệp vụ.

### Bài 31. Khi nào `SKIP LOCKED` phù hợp?

**Đáp án:** worker queue có thể bỏ qua những hàng đang được worker khác xử lý và chọn công việc khác. Không thích hợp với truy vấn cần đủ hàng chính xác.

### Bài 32. Nguyên nhân thường gặp của `idle in transaction` kéo dài?

**Đáp án:** ứng dụng mở transaction nhưng quên commit/rollback, giữ connection trong khi chờ người dùng/API, hoặc nhánh exception không cleanup connection.

### Bài 33. Vì sao không chỉ gọi `Connection.close()` rồi tin rằng PostgreSQL session đã chết?

**Đáp án:** với connection pool, close có thể chỉ trả physical connection về pool. Cần hiểu pool reset/rollback thế nào và session-level locks có được cleanup không.

### Bài 34. Prepared transaction đang giữ lock nhưng không có PID thường thì xử lý sao?

**Đáp án:** xem `pg_prepared_xacts` và coordinator. Không tự gửi `pg_terminate_backend` tới PID ngẫu nhiên; `COMMIT PREPARED`/`ROLLBACK PREPARED` phải theo quyết định 2PC đã xác minh.

### Bài 35. Có nên tự động terminate mọi `idle in transaction` hơn 60 giây?

**Đáp án:** không nên làm mù quáng. Cần phân loại workload, SLA, owner, ảnh hưởng nghiệp vụ, và có thể dùng timeout/server policy phù hợp sau khi đánh giá; không thay thế việc sửa bug transaction boundary.

### Bài 36. Vì sao cancel waiter thường ít phá hủy hơn terminate blocker?

**Đáp án:** cancel waiter chủ yếu dừng request đang chờ; terminate blocker có thể ngắt một kết nối khác và rollback transaction chưa commit của công việc quan trọng. Tác động thực tế vẫn cần đánh giá theo từng incident.

### Bài 37. Nếu B bị cancel nhưng A vẫn giữ khóa thì có xem là xử lý xong sự cố?

**Đáp án:** chưa. Cần kiểm tra các waiter khác, quyết định xử lý A theo owner và sửa nguyên nhân khiến A giữ khóa quá lâu.

### Bài 38. Vì sao không nên retry thanh toán mù quáng sau khi terminate backend?

**Đáp án:** nếu mất kết nối sát COMMIT, client có thể không rõ transaction đã commit hay chưa. Retry không có idempotency có thể xử lý hai lần.

### Bài 39. Tại sao phải theo root blocker thay vì chỉ nhìn một query đang chờ?

**Đáp án:** nhiều waiter có thể chờ cùng một holder hoặc có chuỗi chặn nhau. Xóa một waiter không giải quyết transaction gốc đang giữ khóa.

### Bài 40. Viết thứ tự xử lý cho một sự cố chờ khóa production

**Đáp án gợi ý:**

1. Xác minh triệu chứng/ảnh hưởng.
2. Thu thập `pg_stat_activity`, `pg_locks`, `pg_blocking_pids`.
3. Xác minh đúng PID, backend_start, role/application và transaction state.
4. Xác định waiter, blocker, root blocker, lock type.
5. Liên hệ owner/ưu tiên chờ hoặc rollback hợp lệ.
6. Cancel đúng statement khi phù hợp.
7. Chỉ terminate backend đã xác minh và đánh giá rủi ro khi cần.
8. Kiểm tra lại lock graph, xử lý commit mơ hồ/retry và root cause.

## 35. Checklist can thiệp an toàn

| Câu hỏi | Điều cần xác định |
| --- | --- |
| Đây thật sự là lock wait? | `wait_event_type` / `pg_blocking_pids` |
| Backend nào đang chờ? | Waiting PID, query, SLA |
| Backend nào đang chặn? | Blocker/root blocker |
| PID có còn là session đúng không? | `backend_start`, role, database, app |
| Blocker có đang chạy statement không? | `state` và `wait_event` |
| Có `idle in transaction`? | Client cần commit/rollback |
| Có transaction aborted chưa cleanup? | Rollback/savepoint |
| Loại khóa đang giữ? | Relation/transactionid/advisory/... |
| Khóa thuộc vòng đời nào? | Transaction hay session |
| Có session advisory lock leak? | Unlock đúng backend |
| Có prepared transaction? | `pg_prepared_xacts`/coordinator |
| Lệnh CANCEL sẽ tác động tới ai? | Statement mục tiêu |
| Cancel có đủ nhả khóa không? | Thường không nếu transaction vẫn mở |
| Lệnh TERMINATE có thể rollback gì? | Transaction chưa commit và work của app |
| Có quyền signal đúng scope? | Role/permissions |
| Đây có phải backend hệ thống? | `backend_type` |
| Có giao dịch đã commit nhưng client chưa biết? | Idempotency/đối soát |
| Có external side effect? | Email/API/broker |
| Có thể dùng timeout thay signal? | `lock_timeout`/`statement_timeout` |
| Có nên `NOWAIT`/`SKIP LOCKED`? | Ngữ nghĩa nghiệp vụ |
| Transaction có đang giữ lâu vì HTTP/UI? | Thu nhỏ phạm vi transaction |
| Có deadlock? | SQLSTATE `40P01`, thứ tự khóa |
| Có lock chain nhiều tầng? | Theo dõi `pg_blocking_pids` |
| Có migration đang chạy? | Phối hợp change owner |
| Có nhiều waiter cùng blocker? | Đánh giá blast radius |
| Sau can thiệp có phục hồi? | Kiểm tra backend/lock waits |
| Có log và audit? | Ghi nhận lý do/hành động/kết quả |
| Có bug connection pool? | Cleanup rollback/reset |
| Cần sửa thiết kế? | Ràng buộc, isolation, index, transaction |
| Có kiểm thử hai session sau sửa? | Xác minh không tái diễn |

## 36. Tổng kết

**Giải phóng khóa, hủy truy vấn và chấm dứt phiên là ba hành động khác nhau** trong PostgreSQL:

1. Khóa row/table và transaction advisory locks thường được giải phóng khi **transaction kết thúc** bằng `COMMIT` hoặc `ROLLBACK`.
2. **Session-level advisory locks** tồn tại xuyên commit/rollback và cần `pg_advisory_unlock` tương ứng, `pg_advisory_unlock_all()` trên chính session, hoặc kết thúc session.
3. **`pg_cancel_backend(pid)`** chủ yếu yêu cầu hủy **statement hiện tại**, không đảm bảo transaction đã rollback hoặc khóa đã biến mất.
4. **`pg_terminate_backend(pid)`** yêu cầu kết thúc **backend/session**, ngắt connection và hủy transaction chưa commit khi backend thực sự kết thúc. Nó có tác động rộng hơn cancel.
5. **`idle in transaction`** là một dấu hiệu cần điều tra: statement có thể kết thúc nhưng transaction vẫn giữ khóa/snapshot. Cancel statement không giải quyết được mọi trường hợp.
6. **`pg_blocking_pids`** giúp xác định ai đang chặn ai. Kết hợp với `pg_stat_activity`, `pg_locks` và quyền/owner để hiểu đúng tình huống.
7. **Hủy waiter khác hủy blocker.** Cancel waiter có thể giảm số query đang chờ nhưng không giải quyết holder gây chặn nhiều request.
8. **SQLSTATE 57014/55P03/40P01/40001/25P02** phản ánh những vấn đề khác nhau; cần xử lý transaction và retry đúng loại.
9. **`lock_timeout`, `statement_timeout` và `idle_in_transaction_session_timeout`** giúp hệ thống tự giới hạn thời gian, nhưng không thay thế thiết kế transaction và connection pool.
10. **Prepared transactions** có thể giữ khóa không thuộc PID backend thông thường; phải xử lý theo giao thức 2PC, không terminate bừa.
11. **Sau signal phải quan sát lại**: lệnh trả true không tự chứng minh phiên đã kết thúc hay mọi khóa đã nhả.
12. **Ưu tiên giải pháp ít phá hủy nhất**, xác minh PID + backend_start, hiểu tác động nghiệp vụ, chỉ dùng terminate khi cần và trong phạm vi quyền được cấp.

Một bộ ba truy vấn chẩn đoán đáng nhớ:

```sql
-- 1. Ai đang chờ và ai đang chặn?
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();

-- 2. Khóa nào đang có và khóa nào đang chờ?
SELECT pid, locktype, mode, granted, waitstart
FROM pg_locks
WHERE locktype IN ('relation', 'transactionid', 'advisory');

-- 3. Backend đích có đúng là session cần can thiệp?
SELECT
    pid,
    backend_start,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

Câu thứ ba dùng PID **mẫu**; trong thực tế phải thay bằng PID vừa xác nhận và không gửi tín hiệu từ một kết quả quan sát đã cũ.

**Quy tắc cốt lõi:** trước khi dùng `pg_cancel_backend` hoặc `pg_terminate_backend`, hãy trả lời: **đang chờ ai, khóa thuộc transaction hay session, và nếu can thiệp thì dữ liệu/nghiệp vụ nào bị hủy?** Khi chưa có câu trả lời, hãy **quan sát và xác minh trước**, thay vì tăng mức phá hủy.
