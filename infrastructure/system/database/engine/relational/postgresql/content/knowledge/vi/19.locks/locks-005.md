# Thứ tự lấy khóa và phát sinh deadlock trong PostgreSQL

## 1. Vì sao hai giao dịch hợp lệ có thể khóa nhau mãi?

Trong hệ thống xử lý giao dịch, một request thường phải sửa **nhiều hàng**: trừ tiền tài khoản nguồn rồi cộng tiền tài khoản đích, giữ chỗ trên nhiều tài nguyên, cập nhật đơn hàng và tồn kho, hoặc sửa nhiều bản ghi theo lô.

Giả sử có hai tài khoản A và B:

- **Transaction T1:** chuyển tiền từ A sang B; sửa A trước, rồi sửa B.
- **Transaction T2:** chuyển tiền từ B sang A; sửa B trước, rồi sửa A.

Nếu hai transaction chạy đồng thời:

```text
T1 khóa A                       T2 khóa B
    |                               |
T1 cần khóa B                   T2 cần khóa A
    |                               |
    +---- chờ T2         chờ T1 ----+
                  \       /
                   VÒNG CHỜ
```

T1 không nhả A vì chưa kết thúc. T2 không nhả B vì chưa kết thúc. Cả hai đều cần tài nguyên mà bên kia giữ. Đây là **deadlock** (*bế tắc khóa*).

PostgreSQL không chờ vô hạn khi phát hiện vòng chờ kiểu này: hệ thống chọn một transaction để hủy, báo lỗi thường có SQLSTATE **`40P01`** (*deadlock_detected*), rồi cho transaction còn lại có cơ hội tiếp tục.

Điểm quan trọng: **cùng một kết quả nghiệp vụ có thể đạt được mà không cần deadlock** nếu các transaction lấy khóa theo **cùng một thứ tự xác định**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **lock wait**, **lock contention** và **deadlock**.
2. Giải thích các loại khóa thường gặp trong PostgreSQL ở mức hàng và bảng.
3. Dựng được **wait-for graph** với một vòng phụ thuộc.
4. Tái hiện deadlock bằng hai phiên PostgreSQL độc lập và đọc SQLSTATE `40P01`.
5. Hiểu PostgreSQL xử lý một transaction bị deadlock như thế nào.
6. Thiết kế quy tắc **thứ tự khóa nhất quán** cho chuyển tiền, đặt chỗ và sửa nhiều bảng.
7. Biết khi nào cần `SELECT ... FOR UPDATE` và vì sao khóa riêng lẻ không đủ.
8. Nhận diện deadlock do **nâng cấp khóa**, foreign key, trigger, DDL và advisory lock.
9. Dùng `pg_stat_activity`, `pg_locks` và `pg_blocking_pids()` để chẩn đoán phiên đang chờ.
10. Phân biệt `deadlock_timeout`, `lock_timeout` và `statement_timeout`.
11. Retry **toàn transaction** sau `40P01` và tránh lặp side effect ngoài database.
12. Thiết kế test đồng thời có barrier và quy trình vận hành giảm contention.

## 2. Khóa trong PostgreSQL: mục đích và vòng đời

PostgreSQL sử dụng **MVCC** để cho phép nhiều truy vấn đọc dữ liệu đồng thời mà không buộc mọi SELECT thông thường phải đợi mọi UPDATE. Nhưng những thao tác có thể xung đột vẫn cần cơ chế khóa.

Ví dụ:

- Hai câu UPDATE cùng sửa một hàng phải được phối hợp để không ghi tùy tiện trên cùng phiên bản.
- DELETE có thể xung đột với một transaction đang khóa hàng.
- SELECT ... FOR UPDATE yêu cầu khóa hàng để bảo vệ bước xử lý tiếp theo.
- Một số DDL cần khóa bảng mạnh hơn DML thông thường.
- Foreign key, unique constraint và trigger có thể tạo nhu cầu khóa bổ sung.

### 2.1. Khóa hàng và khóa bảng không giống nhau

PostgreSQL có nhiều nhóm khóa, trong đó hai nhóm quan trọng nhất ở bài này:

**Khóa hàng** (*row-level locks*): liên quan đến hàng cụ thể, ví dụ khi UPDATE hoặc SELECT FOR UPDATE.

**Khóa bảng** (*table-level locks*): liên quan toàn relation, với nhiều mode như `ACCESS SHARE`, `ROW SHARE`, `ROW EXCLUSIVE`, `SHARE`, `ACCESS EXCLUSIVE`.

Một câu UPDATE thường lấy khóa bảng `ROW EXCLUSIVE` để phối hợp DML/DDL, **đồng thời** khóa những hàng cần sửa. Hai UPDATE trên **hai hàng khác nhau** của cùng bảng thường không xung đột chỉ vì cả hai có `ROW EXCLUSIVE` table locks: mode đó tương thích với chính nó. Deadlock ví dụ chuyển tiền xảy ra chủ yếu do **khóa hàng**, không phải do tên mode bảng có chữ “EXCLUSIVE”.

### 2.2. Các kiểu khóa hàng khi SELECT

PostgreSQL cung cấp:

| Cú pháp | Ý nghĩa khái quát |
|---|---|
| `FOR UPDATE` | Khóa hàng mạnh cho thao tác có thể sửa/xóa hoặc cần độc quyền |
| `FOR NO KEY UPDATE` | Khóa hàng cho cập nhật không thay đổi khóa được xem là quan trọng với FK |
| `FOR SHARE` | Khóa chia sẻ, ngăn một số cập nhật/xóa xung đột |
| `FOR KEY SHARE` | Khóa nhẹ hơn, bảo vệ giá trị khóa khỏi thay đổi/xóa theo quy tắc phù hợp |

Các mode có **ma trận xung đột riêng**. Không chỉ so sánh chữ “SHARE/UPDATE” theo cảm tính; hãy đọc tài liệu PostgreSQL tương ứng khi quyết định chế độ khóa.

Một `UPDATE` có thể dùng khóa hàng tương ứng `FOR NO KEY UPDATE` hoặc `FOR UPDATE` tùy cột khóa được thay đổi. `DELETE` dùng khóa mạnh. Những khóa này có thể gây chờ khi hàng đã được transaction khác khóa với mode không tương thích.

### 2.3. Khóa được giữ bao lâu?

Khóa hàng do transaction lấy thường được giữ cho tới khi **transaction kết thúc** bằng COMMIT hoặc ROLLBACK. Với savepoint/subtransaction, một số khóa lấy sau savepoint có thể được nhả khi rollback về savepoint theo quy tắc PostgreSQL.

Vì thế:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Nếu để transaction mở lâu, khóa trên hàng đã sửa vẫn được giữ.

COMMIT;
```

Lệnh UPDATE kết thúc không có nghĩa khóa đã được nhả nếu transaction vẫn còn mở.

**Nguyên tắc vận hành:** transaction nên ngắn; không giữ transaction mở trong khi đợi người dùng, gọi HTTP API chậm hoặc làm công việc không cần thiết.

## 3. Wait, contention và deadlock: ba hiện tượng khác nhau

### 3.1. Lock wait thông thường

```text
T1 giữ khóa A
T2 cần A, phải chờ
T1 COMMIT
T2 tiếp tục
```

Đây là **chờ khóa** thông thường. Chưa có vòng chờ.

### 3.2. Lock contention

Nhiều transaction thường xuyên tranh chấp cùng một hàng hoặc tài nguyên, chẳng hạn một counter toàn hệ thống. Chúng có thể phải xếp hàng lâu dù không bao giờ tạo deadlock.

```text
T1 giữ A
T2 chờ A
T3 chờ A
T4 chờ A
...
```

Đây là vấn đề hiệu năng/độ trễ; không tự đồng nghĩa với deadlock.

### 3.3. Deadlock

```text
T1 giữ A -> chờ B do T2 giữ
T2 giữ B -> chờ A do T1 giữ
```

Có một **chu trình trong quan hệ chờ**, nên không transaction nào có thể tiếp tục bằng cách tự đợi transaction còn lại.

### 3.4. Vì sao phải phân biệt?

| Hiện tượng | Có vòng chờ? | Phản ứng thường thấy |
|---|---|---|
| Chờ khóa | Không bắt buộc | Hết chờ khi holder nhả khóa; hoặc timeout/cancel |
| Contention | Không bắt buộc | Độ trễ cao, throughput giảm |
| Deadlock | Có | PostgreSQL phát hiện và hủy một transaction |
| Serialization failure | Không nhất thiết có vòng chờ khóa | Transaction bị từ chối vì lịch không tuần tự hóa được |

Lỗi `40P01` là deadlock. Lỗi `40001` là serialization failure; hai loại có thể cùng được retry ở cấp transaction nhưng **khác nguyên nhân**.

## 4. Điều kiện hình thành deadlock

Một mô hình kinh điển mô tả deadlock qua bốn yếu tố:

1. **Mutual exclusion:** có tài nguyên/khóa không thể được giữ đồng thời bởi các request có mode xung đột.
2. **Hold and wait:** transaction giữ khóa đang có và đợi khóa khác.
3. **No preemption tùy ý:** PostgreSQL không thể đơn giản lấy khóa của transaction còn sống rồi giao cho transaction khác mà vẫn giữ nguyên semantics; cần kết thúc/hủy transaction để nhả.
4. **Circular wait:** tồn tại vòng giao dịch đợi lẫn nhau.

Trong ứng dụng SQL, điều dễ tác động nhất là **phá điều kiện circular wait** bằng một **thứ tự lấy khóa thống nhất**, hoặc giảm thời gian giữ khóa và xử lý retry khi xung đột vẫn xảy ra.

## 5. Chuẩn bị database lab

Chỉ chạy trong database thực hành. Ví dụ sau có thể thay đổi số dư và cố ý tạo deadlock; **không chạy trên dữ liệu tài chính thật**.

### 5.1. Tạo schema và bảng tài khoản

```sql
CREATE SCHEMA IF NOT EXISTS deadlock240;

CREATE TABLE deadlock240.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance bigint NOT NULL CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Dữ liệu ban đầu:

```sql
INSERT INTO deadlock240.accounts(account_id, owner_name, balance)
VALUES
    (10, 'Tài khoản A', 1000),
    (20, 'Tài khoản B', 1000);
```

Kiểm tra:

```sql
SELECT account_id, owner_name, balance
FROM deadlock240.accounts
ORDER BY account_id;
```

| account_id | owner_name | balance |
|---:|---|---:|
| 10 | Tài khoản A | 1000 |
| 20 | Tài khoản B | 1000 |

Để tập trung vào khóa, cột `balance` là số nguyên minh họa theo **đơn vị tiền nhỏ nhất**. Hệ thống tiền thật cần mô hình tiền tệ, precision, trạng thái giao dịch, audit và ràng buộc nghiệp vụ riêng; không được xem hai UPDATE ví dụ là toàn bộ hệ thống chuyển tiền production.

### 5.2. Hai session độc lập

Mở hai cửa sổ `psql` hoặc hai SQL connection độc lập trong cùng database:

- **Session A:** mã giao dịch T1, chuyển 100 từ account 10 sang 20.
- **Session B:** mã giao dịch T2, chuyển 50 từ account 20 sang 10.

Có thể đặt tên phiên để quan sát:

**Session A:**

```sql
SET application_name = 'deadlock240_A';
SELECT pg_backend_pid() AS pid_a;
```

**Session B:**

```sql
SET application_name = 'deadlock240_B';
SELECT pg_backend_pid() AS pid_b;
```

Lưu lại PID nếu muốn đối chiếu với `pg_stat_activity`/`pg_locks`.

### 5.3. Những quy tắc an toàn khi thực hành

- Hai session phải thực sự là **hai connection**; một connection không thể chạy đồng thời hai transaction độc lập theo cách này.
- Không mở script tự động “chạy hết tất cả lệnh” ngay từ đầu, vì cần **xen kẽ thủ công**.
- Sau khi gặp deadlock, một session có thể nằm trong transaction bị lỗi; chạy `ROLLBACK` trước khi tiếp tục.
- Chỉ reset dữ liệu sau khi cả hai transaction thí nghiệm đã kết thúc.
- Không cố hủy tiến trình PostgreSQL bằng công cụ hệ điều hành để tái hiện; server có cơ chế tự phát hiện deadlock.

## 6. Hiểu chuyển tiền đúng khi chạy tuần tự

Một giao dịch chuyển 100 từ A sang B:

```sql
BEGIN;

UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100;

UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20;

COMMIT;
```

Trên trạng thái ban đầu, số dư sẽ thành:

```text
A (10) = 900
B (20) = 1100
Tổng A+B = 2000
```

Transaction chuyển ngược 50 từ B sang A nếu chạy **sau đó**:

```sql
BEGIN;

UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50;

UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10;

COMMIT;
```

Kết quả cuối:

```text
A (10) = 950
B (20) = 1050
Tổng A+B = 2000
```

Cả hai giao dịch đều hợp lệ khi chạy tuần tự. **Thứ tự cập nhật khác nhau** chỉ trở thành vấn đề khi chúng chồng lấp trong thời gian và giữ khóa riêng.

Trong production, sau câu trừ tiền phải kiểm tra số hàng thực sự bị cập nhật; nếu 0 hàng (không đủ tiền/không có tài khoản), transaction phải rollback thay vì tiếp tục cộng tiền ở tài khoản đích.

## 7. Thí nghiệm deadlock: T1 khóa A trước, T2 khóa B trước

Đây là phần quan trọng nhất. Bắt đầu từ trạng thái mỗi tài khoản có 1000 và hai session chưa mở transaction.

### Bước 1 — Session A mở transaction, khóa A

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100
RETURNING account_id, balance;
```

Kết quả dự kiến: một hàng account 10 với balance=900.

**Không COMMIT.** Session A vẫn giữ khóa cập nhật trên hàng account 10.

### Bước 2 — Session B mở transaction, khóa B

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50
RETURNING account_id, balance;
```

Kết quả: một hàng account 20 với balance=950 trong transaction B.

**Không COMMIT.** B đang giữ khóa trên account 20.

Tình hình:

| Transaction | Đang giữ khóa hàng |
|---|---|
| A | account 10 |
| B | account 20 |

Chưa có deadlock vì chưa ai đợi ai.

### Bước 3 — Session A cố khóa B và bị chặn

**Session A:**

```sql
UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20
RETURNING account_id, balance;
```

Lệnh này thông thường **chưa trả kết quả ngay** vì hàng 20 đang bị session B khóa bằng UPDATE chưa commit.

Bây giờ:

```text
A giữ account 10
A đợi account 20 (B đang giữ)
B giữ account 20
```

Đây mới là **lock wait**, chưa đủ thành deadlock.

**Quan trọng khi thao tác:** terminal A đang bị block ở câu UPDATE. Bạn cần chuyển qua **terminal B** để tiếp tục bước 4.

### Bước 4 — Session B cố khóa A, tạo vòng chờ

**Session B:**

```sql
UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10
RETURNING account_id, balance;
```

Hàng 10 đang bị A khóa. B phải đợi A, trong khi A đang đợi B.

```text
A giữ account 10  ---- cần account 20 ----> B
^                                             |
|                                             |
+---- cần account 10 ---- B giữ account 20 ---+
```

Vòng chờ đã hoàn chỉnh.

### Bước 5 — PostgreSQL phát hiện và phá deadlock

Sau một khoảng chờ kiểm tra, PostgreSQL có thể báo ở **một** session:

```text
ERROR: deadlock detected
DETAIL: Process ... waits for ShareLock on transaction ...
SQLSTATE: 40P01
```

Tên lock/DETAIL và PID sẽ khác theo môi trường. Đây là thông điệp mẫu, không phải kết quả chạy thực tế của bài.

**Không có bảo đảm A hay B luôn là nạn nhân**. PostgreSQL chọn một transaction để hủy nhằm phá vòng chờ. Transaction bị lỗi sẽ không được coi là đã commit thành công.

Session còn lại có thể tiếp tục khi khóa được nhả sau rollback của transaction nạn nhân.

### Bước 6 — Kết thúc hai transaction cho rõ ràng

Nếu Session B là session bị lỗi, hãy chạy trong B:

```sql
ROLLBACK;
```

Khi đó A có thể hoàn thành UPDATE đang chờ và sau đó:

```sql
COMMIT;
```

Nếu A là session bị lỗi thì **đảo vai trò**: A ROLLBACK, B hoàn tất câu UPDATE và COMMIT.

Trong `psql`, sau lỗi bên trong transaction, prompt có thể báo transaction đang ở trạng thái lỗi và những statement tiếp theo trả:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Cần `ROLLBACK` (hoặc rollback tới savepoint thích hợp nếu đã thiết kế savepoint) rồi mới bắt đầu transaction khác.

### Bước 7 — Kiểm tra dữ liệu sau khi cả hai kết thúc

```sql
SELECT account_id, balance
FROM deadlock240.accounts
ORDER BY account_id;

SELECT SUM(balance) AS total_balance
FROM deadlock240.accounts;
```

Nếu chỉ giao dịch A commit, kết quả là A=900, B=1100. Nếu chỉ B commit, kết quả A=1050, B=950. **Tổng vẫn bằng 2000** với các transaction hợp lệ.

Đừng mong cả hai transfer chắc chắn đã xảy ra; transaction bị `40P01` phải được ứng dụng **retry từ đầu** nếu nghiệp vụ cần tiếp tục chuyển tiền.

## 8. Wait-for graph: mô hình hóa deadlock

Một **wait-for graph** biểu diễn:

- Mỗi node là một transaction.
- Mỗi cạnh `T1 → T2` nghĩa là **T1 đang đợi một khóa bị T2 giữ** với mode xung đột.

Ở bước 3:

```text
T1 ---- waits for ----> T2

T2 chưa đợi T1
=> Không có vòng, chỉ là lock wait.
```

Ở bước 4:

```text
         waits
    T1 ---------> T2
     ^             |
     |             |
     +-------------+
         waits

=> Có chu trình T1 -> T2 -> T1.
=> Deadlock.
```

Cách tư duy này áp dụng cho cả khóa hàng, khóa bảng và advisory lock nếu các transaction chờ trên các tài nguyên liên quan.

### 8.1. Bảng theo dõi tài nguyên

| Thời điểm | T1 giữ | T1 đợi | T2 giữ | T2 đợi | Kết luận |
|---|---|---|---|---|---|
| Sau bước 1 | A | — | — | — | Chưa đợi |
| Sau bước 2 | A | — | B | — | Chưa đợi |
| Sau bước 3 | A | B | B | — | Chờ một chiều |
| Sau bước 4 | A | B | B | A | Deadlock |
| Sau khi hủy nạn nhân | Tùy nạn nhân | Được giải phóng | Tùy nạn nhân | Được giải phóng | Không còn vòng |

### 8.2. Điều gì tạo ra thứ tự khóa bất nhất?

T1 cần tài nguyên theo thứ tự:

```text
A -> B
```

T2 cần:

```text
B -> A
```

Thứ tự ngược chiều tạo điều kiện cho vòng chờ. Nếu mọi transaction đều lấy:

```text
A -> B
```

thì transaction đến sau có thể phải **đợi ngay tại A**, nhưng sẽ không thể đồng thời giữ B rồi đợi A theo cùng protocol.

Đây là nền tảng của quy tắc **total order** trong thiết kế locking.

## 9. Giải pháp chính: lấy khóa theo một thứ tự cố định

Khi một transaction cần nhiều account, quy định:

> Với mọi transfer, **khóa account_id nhỏ trước, account_id lớn sau**, bất kể tài khoản nào là nguồn và tài khoản nào là đích.

Trong lab:

```text
account_id 10 trước
account_id 20 sau
```

Transfer 10 → 20 và transfer 20 → 10 đều phải lấy khóa theo **10 → 20**. Phần tính toán số dư vẫn theo hướng chuyển tiền thật; **thứ tự khóa không đồng nghĩa thứ tự dòng tiền**.

### 9.1. T1 khóa 10 rồi 20

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 20
FOR UPDATE;
```

A hiện giữ cả hai khóa. Sau khi kiểm tra đủ tiền, làm DML:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100
RETURNING balance;

UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20
RETURNING balance;

COMMIT;
```

Trong ứng dụng thật, phải kiểm tra `RETURNING` hoặc update count của câu trừ. Nếu 0 hàng, ROLLBACK và **không thực hiện câu cộng**.

### 9.2. T2 cũng khóa 10 rồi 20

**Session B**, dù chuyển tiền **từ 20 sang 10**, vẫn làm:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 20
FOR UPDATE;
```

Nếu A còn giữ account 10, B bị chặn **ngay khi cố lấy khóa 10**. Vì B chưa khóa account 20 nên nó không giữ tài nguyên mà A cần. Không tạo chu trình T1↔T2 theo cặp tài khoản này.

Khi A commit, B lấy lần lượt 10 rồi 20, đọc trạng thái mới và sau đó mới:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50
RETURNING balance;

UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10
RETURNING balance;

COMMIT;
```

Với trạng thái ban đầu 1000/1000 và cả hai transfer hợp lệ, kết quả cuối là 950/1050.

### 9.3. Vì sao nên dùng hai SELECT FOR UPDATE riêng trong ví dụ?

Hai statement sau minh họa thứ tự khóa **tường minh**, độc lập với hướng chuyển tiền:

```sql
SELECT ... WHERE account_id = 10 FOR UPDATE;
SELECT ... WHERE account_id = 20 FOR UPDATE;
```

Ứng dụng thực tế có thể dùng truy vấn khóa tập nhiều hàng theo thứ tự, nhưng cần hiểu cách planner, join, LIMIT và locking clause ảnh hưởng thời điểm khóa. Đối với một giao thức cần **chứng minh thứ tự lấy khóa**, gọi tuần tự theo danh sách khóa đã sắp xếp là cách dễ diễn đạt và kiểm thử.

**Nhớ:** trong hai statement trên, không bắt đầu giao dịch thứ hai với account 20 chỉ vì nó là nguồn; mọi writer phải tuân theo cùng quy tắc.

## 10. Thứ tự khóa không phải thứ tự nghiệp vụ

Giả sử transfer 20 → 10:

- **Thứ tự khóa:** 10 rồi 20.
- **Thứ tự sửa số dư:** có thể trừ 20 rồi cộng 10, miễn cả hai hàng đã được khóa trước và transaction bảo đảm nguyên tử.

Sự khác nhau này giúp tránh một sai lầm rất thường gặp:

> “Tôi luôn khóa tài khoản nguồn trước vì phải trừ nguồn trước.”

Nếu hai transfer ngược chiều nhau, “nguồn trước” làm thứ tự khóa đảo chiều và dễ tạo deadlock.

Một quy tắc ổn định:

```text
lock_order = sort(unique(all_accounts_in_transaction))
for account in lock_order:
    SELECT account FOR UPDATE

sau khi giữ đủ khóa:
    validate business rules
    apply debits/credits
    COMMIT
```

Giá trị `unique` còn tránh thử khóa một account hai lần khi nguồn và đích trùng nhau. Trường hợp tự chuyển tiền cần chính sách nghiệp vụ riêng.

## 11. Cẩn trọng với IN (...), JOIN và thứ tự planner

Có thể viết:

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;
```

Trong trường hợp đơn giản, `ORDER BY account_id` giúp xác định thứ tự hiển thị, và kế hoạch thường có thể khóa theo thứ tự đã sắp. Đây là cách hữu ích trong nhiều bài toán thực tế.

Tuy nhiên, có các giới hạn cần hiểu:

1. `IN (10,20)` **không tự quy định** thứ tự xử lý 10 trước 20.
2. Chỉ viết `UPDATE ... WHERE id IN (...)` **không bảo đảm** các hàng sẽ được cập nhật/khóa theo thứ tự trong danh sách IN.
3. PostgreSQL không có cú pháp `UPDATE ... ORDER BY id` tổng quát như nhiều người suy đoán.
4. Nếu có JOIN, subquery, trigger, FK hoặc nhiều bảng đích, thứ tự lock thực tế có thể khác cách đọc SQL đơn giản.
5. Dưới `READ COMMITTED`, `SELECT ... ORDER BY ... FOR UPDATE` còn có những lưu ý khi cột sắp xếp bị transaction khác thay đổi trong lúc câu lệnh chờ; thứ tự dữ liệu trả về có thể không đúng như trực giác nếu dùng các cột mutable.

**Khuyến nghị:** dùng **khóa ổn định/không đổi** như primary key làm lock order. Khi correctness yêu cầu thứ tự khóa nghiêm ngặt giữa nhiều bước, tổ chức việc lấy khóa **từng khóa theo thứ tự đã sắp** hoặc kiểm chứng rõ execution plan/protocol thay vì mặc định câu UPDATE nhiều hàng sẽ tuân theo `ORDER BY` tưởng tượng.

### 11.1. Khuôn mẫu khóa nhiều tài nguyên trong application

```text
ids = distinct([fromAccountId, toAccountId])
ids = sortAscending(ids)

BEGIN
for id in ids:
    SELECT ... FROM accounts WHERE account_id = id FOR UPDATE

Đọc/kiểm tra dữ liệu sau khi giữ đủ khóa
Thực hiện các UPDATE cần thiết
COMMIT
```

Với số lượng khóa rất lớn, việc gửi từng SELECT riêng có thể tạo round-trip cao. Khi đó cần cân nhắc thiết kế batch lock, thứ tự thực tế, khả năng tranh chấp và retry; nhưng không nên đánh đổi tính đúng chỉ để giảm vài lượt mạng.

## 12. Khi SELECT FOR UPDATE chưa đủ

`SELECT ... FOR UPDATE` là công cụ khóa hàng, **không phải bảo đảm mọi transaction sẽ không deadlock**.

### 12.1. Khóa theo thứ tự đối nghịch vẫn deadlock

Nếu A:

```sql
SELECT * FROM deadlock240.accounts
WHERE account_id = 10 FOR UPDATE;

SELECT * FROM deadlock240.accounts
WHERE account_id = 20 FOR UPDATE;
```

trong khi B làm 20 rồi 10, vòng chờ vẫn xảy ra. Thay UPDATE đầu tiên bằng SELECT FOR UPDATE **không sửa thứ tự khóa sai**.

### 12.2. Khóa hàng chưa chắc bảo vệ tập hàng có thể xuất hiện mới

Nếu transaction đọc một predicate như “tất cả booking đang xác nhận”, các transaction khác có thể INSERT thêm hàng mới. Chỉ khóa các hàng hiện hữu bằng FOR UPDATE không tự khóa “sự không tồn tại của hàng” ở mọi mô hình.

Bài toán này liên quan phantom/write skew và có thể cần `SERIALIZABLE`, unique/ exclusion constraint, quota row hoặc guard lock theo resource.

### 12.3. Không lock khi chưa chắc cần

Khóa quá rộng tạo nhiều contention, ảnh hưởng throughput và tăng nguy cơ vòng chờ giữa các thao tác phức tạp. Chỉ khóa đúng hàng/cấp dữ liệu cần thiết, trong transaction ngắn và với thứ tự nhất quán.

## 13. Deadlock do nâng cấp khóa trên cùng một hàng

Deadlock không chỉ xảy ra với hai hàng A/B. Hai transaction có thể **cùng giữ khóa chia sẻ**, rồi mỗi bên muốn nâng cấp sang khóa mạnh hơn.

### 13.1. Thí nghiệm với FOR SHARE

Sau khi tất cả transaction trước đã kết thúc, giữ nguyên một hàng account 10.

**Session A:**

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR SHARE;
```

**Session B:**

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR SHARE;
```

Hai `FOR SHARE` có thể tương thích với nhau nên cả A và B đều giữ share locks trên cùng hàng.

**A** thử cập nhật:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id = 10;
```

A có thể chờ B nhả share lock.

**B** cũng thử UPDATE hàng ấy:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id = 10;
```

B lại cần khóa không tương thích với A. Hai transaction cùng giữ share locks rồi cùng muốn nâng cấp, tạo nguy cơ deadlock.

### 13.2. Giải pháp cho read-then-update

Nếu transaction **biết trước** rằng nó cần cập nhật một hàng, thường nên lấy khóa phù hợp ngay từ đầu:

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

-- Kiểm tra nghiệp vụ, sau đó UPDATE.

COMMIT;
```

Transaction thứ hai đợi ngay từ lúc SELECT FOR UPDATE, thay vì cả hai cùng giữ SHARE rồi nâng cấp.

**Không phải lúc nào cũng cần FOR UPDATE**. Chọn khóa theo thao tác và mức tương tranh thực tế; dùng khóa quá mạnh cũng có chi phí.

## 14. Deadlock với nhiều bảng

Giả sử một nghiệp vụ chạm hai bảng:

```text
orders
inventory
```

Một endpoint:

```text
T1:
    khóa order
    khóa inventory
```

Một job khác:

```text
T2:
    khóa inventory
    khóa order
```

Dù mỗi bảng có các khóa chính rõ ràng, sự đảo thứ tự giữa **loại tài nguyên** cũng tạo vòng chờ.

### 14.1. Quy định thứ tự toàn cục

Ví dụ một quy ước trong dự án:

```text
1. tenant guard
2. order header
3. inventory rows, SKU tăng dần
4. order items, item_id tăng dần
5. audit/outbox rows
```

Không có thứ tự chung đúng cho mọi hệ thống; hãy chọn theo workflow và mức tranh chấp. Điều quan trọng là **mọi đường code** liên quan dùng cùng thứ tự.

### 14.2. Cân nhắc trigger và foreign key

Ngay cả khi application viết:

```text
update orders trước
update inventory sau
```

một trigger hoặc foreign key có thể làm PostgreSQL đọc/khóa thêm hàng ở bảng khác. Khi điều tra deadlock, xem **toàn bộ quan hệ ràng buộc và trigger**, không chỉ hai câu UPDATE được nhìn thấy trong service.

### 14.3. Cùng khóa nhưng thứ tự trong từng bảng vẫn quan trọng

Nếu sửa hai order hoặc nhiều SKU, quy tắc theo bảng chưa đủ. Cần quy định thêm:

- Order ID tăng dần.
- SKU tăng dần trong một bảng inventory.
- Nếu khóa nhiều tenant, tenant ID trước rồi ID tài nguyên.
- Các hàng có thể trùng cần deduplicate trước khi khóa.

Một **thứ tự toàn cục đủ chi tiết** mới giúp loại những vòng chờ do chính protocol của bạn tạo ra.

## 15. Table-level locks cũng có thể tạo deadlock

Không nên nghĩ deadlock chỉ do hàng.

PostgreSQL có nhiều table lock modes:

| Tình huống | Lock mode thường gặp |
|---|---|
| SELECT thông thường | `ACCESS SHARE` |
| SELECT FOR UPDATE/SHARE | `ROW SHARE` ở bảng được khóa, ngoài khóa hàng |
| INSERT / UPDATE / DELETE | `ROW EXCLUSIVE` |
| Một số thao tác tạo index/maintenance | Các mode như `SHARE`/`SHARE UPDATE EXCLUSIVE` tùy câu lệnh |
| Một số DDL mạnh như thay cấu trúc bảng | Có thể cần `ACCESS EXCLUSIVE` |

Tên mode không đủ để kết luận xung đột; PostgreSQL có **bảng ma trận conflict** cho các mode.

Ví dụ hai tiến trình migration khóa bảng A rồi B, trong khi tiến trình khác khóa B rồi A bằng mode xung đột. Dù không sửa chung hàng nghiệp vụ nào, chúng vẫn có thể deadlock.

### 15.1. Migrations cần phối hợp riêng

- Không chạy nhiều migration có thay đổi lock mạnh theo thứ tự bảng ngược nhau nếu có thể tránh.
- Xác định các statement DDL có thể lấy `ACCESS EXCLUSIVE` hoặc mode xung đột với workload.
- Dùng maintenance window, lock timeout hợp lý hoặc công cụ migration có cơ chế serialize.
- DDL có thể chờ các transaction đọc/ghi đang mở; một transaction `idle in transaction` giữ khóa lâu làm vấn đề khó thấy.

**Quy tắc:** không mặc định câu `ALTER TABLE` đơn giản về cú pháp sẽ không đụng đến khóa quan trọng.

## 16. Thời gian phát hiện deadlock

PostgreSQL có tham số `deadlock_timeout`: khi chờ khóa đủ lâu, hệ thống bắt đầu kiểm tra xem có deadlock hay không.

Kiểm tra giá trị hiện tại:

```sql
SHOW deadlock_timeout;
```

Trong cấu hình thông thường, giá trị mặc định hay gặp là khoảng **1 giây**; giá trị thực tế có thể đã được quản trị viên thay đổi.

### 16.1. Vì sao không kiểm tra vòng chờ ngay lập tức cho mọi lock wait?

Kiểm tra deadlock có chi phí. Nhiều lock wait rất ngắn và tự hết khi transaction khác commit. Việc chờ một khoảng ngắn trước khi chạy detector tránh tốn tài nguyên kiểm tra liên tục cho những lock wait bình thường.

### 16.2. deadlock_timeout không phải deadline bắt buộc cho một query

Tham số này chủ yếu ảnh hưởng **thời điểm kiểm tra deadlock**, không có nghĩa một câu SQL sẽ tự hủy nếu chỉ đợi khóa lâu hơn giá trị đó mà **không có deadlock**.

Ví dụ T1 giữ một khóa 30 giây còn T2 chờ khóa ấy: nếu không có vòng chờ, T2 có thể tiếp tục đợi dù đã vượt deadlock_timeout.

### 16.3. Không tự hạ deadlock_timeout trên toàn server

Điều chỉnh quá thấp có thể tăng overhead vì kiểm tra deadlock nhiều lần. Trong production, thay đổi tham số và logging cần dựa trên workload, quyền cấu hình và quy trình vận hành của DBA.

## 17. lock_timeout, statement_timeout và NOWAIT

Các cơ chế giới hạn thời gian/không chờ có ý nghĩa khác nhau:

| Cơ chế | Mục tiêu |
|---|---|
| `deadlock_timeout` | Khi nào chạy kiểm tra deadlock sau thời gian chờ |
| `lock_timeout` | Giới hạn thời gian chờ để lấy một khóa |
| `statement_timeout` | Giới hạn thời gian thực thi toàn câu SQL |
| `NOWAIT` | Một số câu locking trả lỗi ngay nếu không lấy được khóa |
| `SKIP LOCKED` | Với locking row selection phù hợp, bỏ qua những hàng đang bị khóa |

### 17.1. Cấu hình timeout trong transaction lab

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';

SELECT account_id
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

COMMIT;
```

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Nếu không lấy được khóa trong thời gian giới hạn, statement có thể lỗi. Với transaction đã lỗi, ứng dụng cần rollback thích hợp.

### 17.2. NOWAIT

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
```

Nếu hàng đang bị khóa xung đột, câu truy vấn có thể trả lỗi `lock_not_available` với SQLSTATE `55P03`, thay vì đợi.

Đây không phải lỗi deadlock 40P01. Application phải quyết định trả “bận, thử lại” hay áp dụng lịch retry theo nghiệp vụ.

### 17.3. SKIP LOCKED

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

Nếu một account đang khóa, câu truy vấn có thể **bỏ qua account đó**. Điều này hữu ích cho một số mô hình **hàng đợi công việc**, nhưng **không phù hợp để âm thầm bỏ một tài khoản** trong transaction chuyển tiền cần đủ cả nguồn và đích.

`SKIP LOCKED` cố ý tạo cách nhìn không đầy đủ so với tập hàng mong muốn. Không dùng nó để “chữa deadlock” cho một giao dịch mà mọi tài nguyên đều bắt buộc.

## 18. Work queue: trường hợp SKIP LOCKED hữu ích

Ví dụ bảng job:

```sql
CREATE TABLE deadlock240.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('READY', 'RUNNING', 'DONE')),
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO deadlock240.jobs(status, payload)
VALUES
    ('READY', 'job-A'),
    ('READY', 'job-B'),
    ('READY', 'job-C');
```

Một worker có thể lấy một job chưa bị worker khác khóa:

```sql
WITH picked AS (
    SELECT job_id
    FROM deadlock240.jobs
    WHERE status = 'READY'
    ORDER BY job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE deadlock240.jobs AS j
SET status = 'RUNNING'
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING j.job_id, j.payload, j.status;
```

Các worker độc lập có thể lấy những job khác nhau thay vì cùng đợi một job đã bị giữ lock.

Nhưng:

- Cần cơ chế lease/recovery nếu worker chết sau khi nhận job.
- `SKIP LOCKED` không bảo đảm fairness tuyệt đối; job có thể bị bỏ qua nhiều lần.
- Không thay thế idempotency của tác vụ.
- Vẫn có thể phát sinh deadlock nếu sau đó worker lấy thêm lock khác theo thứ tự ngược nhau.
- Work queue cần thiết kế retry, trạng thái và transaction boundary riêng.

## 19. Quan sát phiên đang chờ bằng pg_stat_activity

Mở **session thứ ba** làm observer khi A hoặc B đang bị block. Có thể xem:

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Một phiên đang chờ khóa có thể hiển thị:

```text
wait_event_type = Lock
wait_event      = transactionid / tuple / ... (tùy tình huống)
blocking_pids   = {PID của phiên đang chặn}
```

Đây là các giá trị **minh họa**, không phải kết quả đo thực tế.

### 19.1. Tại sao application_name hữu ích?

Nếu trong lab đặt:

```sql
SET application_name = 'deadlock240_A';
```

thì ở observer dễ nhận diện transaction nào thuộc phiên A/B hơn là chỉ có PID vô danh.

Trong production, `application_name` nên phản ánh service/workload có kiểm soát, không chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.

### 19.2. idle in transaction

Một session có thể không chạy SQL nào ngay lúc quan sát nhưng vẫn ở trạng thái:

```text
state = idle in transaction
```

Nó có thể đang giữ các khóa của statement trước, khiến session khác chờ lâu. Kiểm tra `xact_start` và thời gian transaction khi chẩn đoán:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Không tự động hủy mọi transaction lâu mà chưa đánh giá tác động nghiệp vụ và quyền vận hành.

## 20. pg_blocking_pids(): tìm ai đang chặn ai

Hàm `pg_blocking_pids(pid)` trả danh sách PID đang chặn backend được hỏi theo logic lock manager PostgreSQL.

Ví dụ tìm các phiên hiện có blocker:

```sql
SELECT
    a.pid AS waiting_pid,
    a.application_name AS waiting_app,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 120) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
```

Có thể mở rộng bằng `LATERAL unnest(...)` để hiển thị từng cặp waiter/blocker:

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    b.pid AS blocking_pid,
    b.application_name AS blocking_app,
    w.wait_event,
    left(w.query, 100) AS waiting_sql,
    left(b.query, 100) AS blocker_last_sql
FROM pg_stat_activity AS w
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(w.pid)
) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
    ON b.pid = p.blocking_pid
WHERE w.datname = current_database()
ORDER BY w.pid, b.pid;
```

Cần hiểu `query` ở phiên đang giữ khóa có thể là **câu SQL gần đây nhất**, không nhất thiết chính xác câu đầu tiên đã lấy lock; một transaction có thể lấy khóa ở statement trước rồi nằm idle.

### 20.1. Chẩn đoán không phải phép chứng minh toàn bộ lịch sử

Một vòng deadlock có thể tồn tại rất ngắn trước khi detector hủy một transaction. Observer query có thể **không kịp bắt** hai cạnh cùng lúc.

Vì vậy, kết hợp:

- Database logs khi deadlock detected.
- PID/application_name.
- Query và transaction timeline.
- Lock wait metrics.
- SQLSTATE từ application.

Không kết luận “không có deadlock” chỉ vì lần SELECT `pg_stat_activity` tình cờ không thấy vòng chờ.

## 21. pg_locks: quan sát loại khóa

`pg_locks` chứa thông tin lock do PostgreSQL quản lý. Một truy vấn điều tra:

```sql
SELECT
    l.pid,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.pid, l.granted, l.locktype, l.mode;
```

Những trường quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `pid` | Backend đang giữ/chờ khóa |
| `locktype` | Kiểu đối tượng khóa như relation, transactionid, tuple |
| `mode` | Chế độ khóa |
| `granted` | TRUE đã cấp, FALSE đang đợi |
| `relation` | OID bảng/index khi lock liên quan relation |
| `transactionid` | Transaction ID khi lock liên quan transaction |
| `virtualxid` | Virtual transaction ID trong một số kiểu lock |

### 21.1. Tại sao không luôn thấy khóa hàng trong pg_locks?

PostgreSQL có thể biểu diễn việc khóa hàng trên chính phiên bản tuple, không hiển thị mọi row lock đã được giữ như một dòng riêng trong `pg_locks`.

Khi một transaction chờ hàng bị transaction khác sửa, observer thường thấy **chờ transactionid** hoặc các lock khác trong quá trình phối hợp, thay vì một dòng “row X đang thuộc về T1” dễ đọc.

Do đó:

- `pg_locks` rất hữu ích để chẩn đoán.
- `pg_blocking_pids()` thường tiện để tìm blocker hiện hành.
- Không suy luận “không có row lock” chỉ vì không thấy một dòng tuple lock.
- Không dựa vào một join đơn giản của các dòng pg_locks để luôn suy ra toàn bộ đồ thị chờ chính xác.

## 22. Log deadlock và deadlock_timeout

Khi phát hiện deadlock, PostgreSQL thường ghi/log thông tin các process và câu SQL liên quan tùy cấu hình.

Ví dụ dạng thông điệp:

```text
ERROR: deadlock detected
DETAIL:
  Process 1111 waits for ShareLock on transaction ...;
  blocked by process 2222.
  Process 2222 waits for ShareLock on transaction ...;
  blocked by process 1111.
HINT: See server log for query details.
SQLSTATE: 40P01
```

Các PID và lock modes chỉ mang tính minh họa. Đừng copy chúng vào runbook như số cố định.

### 22.1. log_lock_waits

Tham số `log_lock_waits` có thể hỗ trợ ghi lại lock waits kéo dài theo cấu hình.

```sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
```

Thay đổi các tham số này trong production có thể cần quyền quản trị và đánh giá overhead/log volume. Không tự thay đổi cấu hình toàn server khi chỉ đang phân tích một sự cố ứng dụng.

### 22.2. Ghi log đủ để ghép các sự kiện

Ứng dụng nên log có kiểm soát:

- Transaction/request correlation ID.
- Account IDs hoặc resource keys đã chuẩn hóa/ẩn danh khi cần.
- Danh sách khóa dự kiến và thứ tự lấy.
- Isolation level.
- SQLSTATE và loại exception.
- Số lần retry.
- Thời gian giữ transaction, thời gian chờ lock.
- Kết quả commit/rollback.

Tránh log số tài khoản ngân hàng thật, token, payload nhạy cảm hoặc toàn bộ SQL chứa PII.

## 23. Deadlock còn xuất hiện ở foreign key và unique constraint

Ngay cả khi application nhìn thấy một câu INSERT hoặc UPDATE “chỉ đụng một bảng”, PostgreSQL có thể cần khóa/kiểm tra ở nhiều đối tượng.

### 23.1. Foreign key

Khi INSERT một hàng con tham chiếu hàng cha, PostgreSQL phải kiểm tra hàng cha tồn tại với trạng thái phù hợp. Quá trình kiểm tra có thể dùng các khóa hàng như `FOR KEY SHARE` trên đối tượng tham chiếu.

Trong transaction khác, DELETE/UPDATE khóa của hàng cha có thể xung đột. Nếu mỗi bên đồng thời đang giữ thêm khóa khác theo thứ tự ngược, một vòng deadlock có thể hình thành.

**Bài học:** khi điều tra, xem cả khóa ngoại, ON UPDATE/ON DELETE và các statement thực sự được kích hoạt.

### 23.2. Unique constraint / ON CONFLICT

Hai transaction INSERT những giá trị khóa duy nhất cạnh tranh có thể phải chờ kết quả transaction kia. Một UPSERT cũng có thể lấy các khóa cập nhật hàng đã tồn tại.

Nếu mỗi transaction ghi nhiều khóa unique theo **thứ tự khác nhau**, nguy cơ deadlock có thể tăng.

Ví dụ minh họa với hai keys:

```text
T1: insert key X, sau đó key Y
T2: insert key Y, sau đó key X
```

Nếu các kiểm tra uniqueness tạo chờ chéo, có thể xuất hiện deadlock. Khi thao tác batch keys, sort danh sách một cách nhất quán và thiết kế retry, thay vì chỉ tin `ON CONFLICT` giải quyết mọi xung đột concurrency.

### 23.3. Trigger

Một trigger có thể UPDATE bảng audit, counter hoặc parent resource mà code service không trực tiếp gọi. Hai workflow có thứ tự bảng khác nhau **qua trigger** vẫn có thể deadlock.

Do đó, không chỉ đọc SQL của endpoint; phải xem cả trigger và quan hệ phụ thuộc đang chạy trong transaction.

## 24. Advisory locks cũng cần thứ tự

PostgreSQL hỗ trợ advisory lock do ứng dụng tự gán khóa logic.

Ví dụ khóa cấp transaction:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(240, 10);
SELECT pg_advisory_xact_lock(240, 20);

-- Xử lý tài nguyên tương ứng.

COMMIT;
```

Cặp `(240, account_id)` chỉ là khóa minh họa. Transaction-level advisory lock được nhả khi transaction kết thúc.

### 24.1. Advisory lock không miễn nhiễm deadlock

Nếu A lấy:

```text
advisory(240,10) -> advisory(240,20)
```

và B lấy:

```text
advisory(240,20) -> advisory(240,10)
```

thì vẫn có thể có vòng chờ. PostgreSQL có khả năng phát hiện deadlock đối với advisory locks, nhưng ứng dụng phải tránh giao thức khóa ngược chiều.

### 24.2. Transaction-level và session-level

- `pg_advisory_xact_lock(...)`: vòng đời transaction.
- `pg_advisory_lock(...)`: vòng đời session cho tới khi unlock hoặc connection kết thúc, không tự nhả chỉ vì COMMIT.

Với connection pool, session-level advisory locks rất dễ gây lỗi nếu không quản lý release rõ ràng. Ưu tiên transaction-level khi bảo vệ một workflow ngắn.

### 24.3. Try-lock

```sql
SELECT pg_try_advisory_xact_lock(240, 10);
```

Hàm trả boolean báo có lấy được lock ngay không. Nhưng việc không đợi không tự bảo đảm đúng nghiệp vụ; ứng dụng phải xử lý trường hợp không lấy được lock và không làm nửa workflow.

## 25. Kết hợp thứ tự khóa với isolation level

### 25.1. READ COMMITTED

Ở mức mặc định phổ biến của PostgreSQL, transaction có thể chờ một hàng vừa được transaction khác sửa. Sau khi hàng được nhả, UPDATE thường phải đánh giá lại điều kiện phù hợp trên phiên bản hàng hiện hành.

Ví dụ:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 100
WHERE account_id = 10
  AND balance >= 100
RETURNING balance;
```

Dùng câu UPDATE có điều kiện giúp tránh một số lỗi read–modify–write khi nhiều request cùng tranh tài khoản.

Nhưng nếu mỗi transfer cần hai hàng, **khóa theo thứ tự nhất quán** vẫn cần thiết để tránh deadlock.

### 25.2. REPEATABLE READ

Snapshot ổn định của transaction có thể dẫn tới lỗi serialization nếu hàng muốn cập nhật đã bị transaction khác thay đổi kể từ snapshot. Điều này **không loại bỏ** khả năng deadlock trong mọi lịch lấy khóa.

Không được coi “đã bật REPEATABLE READ” là một chiến lược sắp xếp lock.

### 25.3. SERIALIZABLE

PostgreSQL có thể hủy transaction với `40001` để bảo vệ tính tuần tự hóa. Nhưng `SERIALIZABLE` **không bảo đảm không xuất hiện `40P01`** nếu ứng dụng vẫn lấy các khóa theo thứ tự gây vòng chờ.

Có thể cần xử lý cả:

- `40001` — serialization failure.
- `40P01` — deadlock detected.

Hai loại thường nên retry **toàn transaction** khi nghiệp vụ cho phép, nhưng cần log/đo riêng để biết lỗi do thứ tự lock hay do dependency SSI.

## 26. Retry sau deadlock phải bao gồm toàn bộ transaction

Khi PostgreSQL báo `40P01` trong transaction thông thường, transaction bị lỗi phải được rollback. **Không chỉ retry câu UPDATE vừa lỗi** trong cùng transaction đã hỏng.

Ví dụ giao dịch chuyển tiền:

```text
BEGIN
    trừ 100 từ A      <-- thành công tạm thời
    cộng 100 vào B    <-- gặp 40P01
ROLLBACK
```

Sau ROLLBACK, phần trừ tạm thời cũng không được commit. Retry cần thực hiện lại:

```text
BEGIN mới
    khóa A/B theo thứ tự nhất quán
    kiểm tra đủ số dư
    trừ nguồn
    cộng đích
COMMIT
```

### 26.1. Quy tắc retry

1. Bắt SQLSTATE `40P01`.
2. Rollback toàn bộ transaction.
3. Nhả connection/khởi tạo transaction mới theo transaction manager.
4. Đọc lại dữ liệu nghiệp vụ vì nó có thể đã đổi.
5. Chạy lại mọi bước cần thiết.
6. Dùng retry giới hạn, backoff có jitter khi phù hợp.
7. Nếu quá số lần, trả lỗi tạm thời hoặc đưa việc xử lý vào hàng đợi theo yêu cầu.
8. Không lặp lại side effect đã phát ra bên ngoài transaction.

### 26.2. Các mã lỗi thường thấy

| SQLSTATE | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `40P01` | Deadlock detected | Rollback, thường retry toàn transaction |
| `40001` | Serialization failure | Rollback, retry toàn transaction |
| `55P03` | Lock not available | Xem NOWAIT/lock_timeout; có chính sách retry phù hợp |
| `57014` | Query canceled | Có thể do statement_timeout hoặc hủy chủ động; chẩn đoán nguyên nhân |
| `23505` | Unique violation | Kiểm tra dữ liệu/logic; không retry mù |
| `23514` | Check violation | Điều kiện dữ liệu sai; thường sửa logic/input |

**Không dựa vào văn bản của exception** để phân biệt deadlock với timeout vì thông báo có thể khác phiên bản/ngôn ngữ. Dùng SQLSTATE.

## 27. JDBC/Java: khóa theo thứ tự và retry

Mẫu dưới dùng `DataSource` đã được ứng dụng cấu hình. Hai account IDs được sắp **trước khi lấy khóa**. Cần Java hỗ trợ text block.

### 27.1. Hàm chuyển tiền có thứ tự khóa rõ ràng

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(int sourceId, int targetId, long amount)
            throws SQLException {
        if (sourceId == targetId || amount <= 0) {
            throw new IllegalArgumentException(
                "Nguồn/đích hoặc số tiền không hợp lệ");
        }

        int[] ids = {sourceId, targetId};
        Arrays.sort(ids);

        try (Connection c = dataSource.getConnection()) {
            c.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);

            try {
                // Khóa theo ID, không theo hướng dòng tiền.
                String lockSql = """
                    SELECT account_id
                    FROM deadlock240.accounts
                    WHERE account_id = ?
                    FOR UPDATE
                    """;

                for (int id : ids) {
                    try (PreparedStatement ps =
                             c.prepareStatement(lockSql)) {
                        ps.setInt(1, id);
                        try (ResultSet rs = ps.executeQuery()) {
                            if (!rs.next()) {
                                throw new SQLException(
                                    "Không tìm thấy account " + id);
                            }
                        }
                    }
                }

                String debitSql = """
                    UPDATE deadlock240.accounts
                    SET balance = balance - ?,
                        updated_at = now()
                    WHERE account_id = ?
                      AND balance >= ?
                    RETURNING balance
                    """;

                try (PreparedStatement ps =
                         c.prepareStatement(debitSql)) {
                    ps.setLong(1, amount);
                    ps.setInt(2, sourceId);
                    ps.setLong(3, amount);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException(
                                "Không đủ tiền hoặc account không tồn tại");
                        }
                    }
                }

                String creditSql = """
                    UPDATE deadlock240.accounts
                    SET balance = balance + ?,
                        updated_at = now()
                    WHERE account_id = ?
                    """;

                try (PreparedStatement ps =
                         c.prepareStatement(creditSql)) {
                    ps.setLong(1, amount);
                    ps.setInt(2, targetId);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                            "Không cập nhật được account đích");
                    }
                }

                c.commit();

            } catch (SQLException | RuntimeException ex) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }
}
```

Ở đây:

- Thứ tự lock theo **min(account_id) rồi max(account_id)**.
- Mỗi account được khóa trước khi chạy UPDATE.
- Điều kiện trừ tiền kiểm tra đủ số dư ở cùng câu UPDATE.
- Nếu bất kỳ bước nào lỗi, rollback cả giao dịch.
- Chỉ báo thành công sau `commit()`.

Đây là **mẫu học về khóa**, chưa phải triển khai hệ thống tiền thật. Sản phẩm thực tế cần ledger kế toán, idempotency key, chống double-spending nhiều nguồn, kiểm soát overflow, phân quyền và đối soát.

### 27.2. Cần thêm retry ngoài hàm giao dịch

Một service có thể bao bọc toàn bộ nghiệp vụ bằng:

```java
public void transferWithRetry(
        int sourceId, int targetId, long amount)
        throws SQLException {

    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            // Hàm này mở một transaction mới mỗi lần gọi.
            transfer(sourceId, targetId, amount);
            return;
        } catch (SQLException ex) {
            String state = ex.getSQLState();
            boolean retryable =
                "40P01".equals(state) || "40001".equals(state);

            if (!retryable || attempt == maxAttempts) {
                throw ex;
            }

            // Trong production: backoff/jitter có giới hạn.
            // Không giữ transaction mở khi chờ retry.
        }
    }
}
```

Cấu trúc này minh họa retry ở lớp ngoài transaction. Khi dùng Spring hoặc framework transaction, nên để framework quản lý mở/rollback/commit một transaction mới trên mỗi lần thử; tránh vô tình retry trong **cùng transaction đã thất bại**.

### 27.3. Side effect ngoài PostgreSQL

Không làm:

```text
BEGIN
  trừ tiền
  gửi email "chuyển tiền thành công"
  cộng tiền -> deadlock 40P01
ROLLBACK
```

Email đã được gửi nhưng DB đã rollback.

Nếu cần publish event, cân nhắc **transactional outbox**: ghi bản ghi nghiệp vụ và outbox trong cùng transaction, publish sau commit. Retry cần idempotency để tránh xử lý request hai lần khi client mất kết nối quanh COMMIT.

## 28. Spring và transaction boundary

Khi dùng Spring hoặc framework tương tự:

- Xác định rõ **một lần retry = một transaction mới**.
- Không bắt ngoại lệ `40P01` rồi nuốt lỗi trong một transaction đã đánh dấu rollback-only.
- Tránh self-invocation làm annotation transaction/retry không được áp dụng đúng proxy.
- Chỉ retry các lỗi đã được phân loại và có **ngữ nghĩa idempotent**.
- Không giữ khóa khi gọi API mạng.
- Kiểm tra SQLSTATE bên dưới các lớp exception nếu framework bọc lại SQLException.

Một cấu trúc ý tưởng:

```text
retry boundary
    |
    +-- begin transaction
          |
          +-- sort keys
          +-- lock keys in order
          +-- validate
          +-- update source and target
          |
       commit
    |
if 40P01/40001:
    retry new transaction
```

Trường hợp service nằm trong transaction khác cần xem lại thứ tự lock **toàn bộ transaction ngoài**, không chỉ method chuyển tiền. Một method được viết đúng thứ tự riêng nhưng transaction cha đã khóa resource khác theo thứ tự ngược vẫn có thể deadlock.

## 29. Lock ordering cho các workflow phức tạp

### 29.1. Đặt hàng

Một hệ thống có thể chạm:

```text
customer
order
inventory
coupon
payment_intent
outbox
```

Hãy quy định thứ tự theo **loại resource** và **khóa trong từng resource**, ví dụ:

```text
(tenant_id)
    -> customer_id
    -> order_id
    -> SKU tăng dần
    -> coupon_id
    -> outbox
```

Đây chỉ là **ví dụ chính sách**, không phải thứ tự PostgreSQL bắt buộc. Thực tế cần thiết kế tương thích với foreign keys, trigger và workload.

### 29.2. Chuyển nhiều sản phẩm

Nếu hai đơn cùng cần SKU X và Y:

```text
Order 1: X -> Y
Order 2: Y -> X
```

có thể tạo vòng chờ. Sort SKU:

```text
Order 1: X -> Y
Order 2: X -> Y
```

sẽ giảm nguy cơ deadlock do đảo thứ tự trong phần inventory.

### 29.3. Cập nhật bảng cha/con

Nếu một transaction khóa hàng cha rồi con, transaction khác khóa con rồi cha, rủi ro deadlock tăng. Đưa các thao tác vào một quy ước toàn cục và kiểm tra những khóa gián tiếp do FK/trigger.

### 29.4. Bulk update

Không nên giả định:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id IN (10, 20);
```

lấy khóa theo thứ tự 10 rồi 20 chỉ vì danh sách IN được viết như vậy. Với những batch cạnh tranh cao, cần thiết kế rõ cách thu thập/khóa các khóa chính theo thứ tự hoặc chia batch sao cho các worker tránh tranh chấp chéo.

### 29.5. Tránh giao dịch quá lớn

Transaction giữ càng nhiều khóa và càng lâu, xác suất gặp một resource đang bị giữ bởi transaction khác càng cao. Hãy:

- Giới hạn batch có thể kiểm soát.
- Không mở transaction từ đầu quá trình xử lý nếu nhiều bước chưa cần DB.
- Đọc và tính toán không nhạy concurrency trước khi bắt đầu phần critical section nếu có thể.
- Không phân mảnh một bất biến cần atomicity thành các commit độc lập chỉ để né khóa.
- Giữ thứ tự lock ổn định trong từng batch.

## 30. Deadlock khác write skew

Cả hai liên quan transaction đồng thời nhưng bản chất khác:

**Deadlock:**

```text
A giữ row 10, chờ row 20
B giữ row 20, chờ row 10
=> PostgreSQL phát hiện vòng chờ
=> Một transaction lỗi 40P01
```

**Write skew:**

```text
A đọc "còn 2 bác sĩ", sửa DR_A
B đọc "còn 2 bác sĩ", sửa DR_B
A và B sửa hai hàng khác nhau
=> Có thể không chờ nhau
=> Cả hai commit ở REPEATABLE READ
=> Bất biến "ít nhất 1 người trực" sai
```

Sự khác nhau:

| Thuộc tính | Deadlock | Write skew |
|---|---|---|
| Có vòng chờ lock | Có | Không bắt buộc |
| SQLSTATE điển hình | `40P01` | Có thể không lỗi ở REPEATABLE READ |
| Hậu quả trực tiếp | Một transaction bị hủy để phá vòng | Có thể commit dữ liệu sai bất biến |
| Giải pháp chính | Thứ tự khóa nhất quán, transaction ngắn, retry | SERIALIZABLE+retry, guard lock, constraint phù hợp |
| Phát hiện bằng logs | Thường có deadlock error | Có thể hoàn toàn không có error |

**Không có deadlock không chứng minh giao dịch đúng.** Hệ thống còn phải kiểm tra các bất biến nghiệp vụ và isolation phù hợp.

## 31. Kiểm thử tái hiện deadlock một cách xác định

Một unit test chạy hai phương thức lần lượt sẽ không tái hiện deadlock. Cần **hai transaction đồng thời** và một barrier ép lịch:

```text
Test runner
    |
    +--- Conn A: BEGIN
    |
    +--- Conn B: BEGIN
    |
    +--- A: UPDATE account 10 -----+
    |                              |
    +--- B: UPDATE account 20 -----+--> BARRIER
                                           |
                                  release both
                                           |
                       A UPDATE 20   B UPDATE 10
                             |              |
                          waits             waits
                             \              /
                         one gets 40P01
                                           |
                              rollback victim
                              commit winner
                                           |
                              assert total = 2000
```

### 31.1. Tiêu chí kiểm thử deadlock

Trong **kịch bản cố ý đảo thứ tự**:

- Hai connection độc lập.
- Cả hai cập nhật hàng đầu thành công và giữ transaction mở trước barrier.
- Hai thao tác thứ hai cạnh tranh tạo vòng chờ.
- Một transaction có thể nhận `40P01`.
- Không có số dư âm nếu CHECK và điều kiện UPDATE đúng.
- Transaction nạn nhân rollback, transaction thắng có thể commit.
- Tổng tiền vẫn bảo toàn theo dữ liệu lab.

Trong **kịch bản đã sửa bằng cùng thứ tự khóa**:

- Có thể phát sinh lock wait.
- Không nên phát sinh vòng deadlock A↔B do riêng hai account này.
- Hai transfer có thể thành công lần lượt nếu đủ tiền.
- Kết quả cuối và tổng tiền đúng.

### 31.2. Vì sao không chỉ dùng pg_sleep?

`pg_sleep(0.2)` có thể làm tăng xác suất hai transaction chạy chồng lấp nhưng không bảo đảm từng phiên đã lấy xong khóa đầu. Barrier ở test runner (đợi cả A/B báo “đã khóa account đầu tiên”) đáng tin hơn.

### 31.3. Kiểm thử sau retry

Sau khi một transaction bị 40P01, hãy cho application retry toàn transaction và kiểm tra:

- Chỉ số dư sau hai transfer thành công đúng.
- Không có transfer audit ghi trùng.
- Không có email/event xác nhận bị phát cho transaction rollback.
- Không có connection trả về pool trong trạng thái transaction aborted.
- Retry kết thúc khi đạt giới hạn.

## 32. Khi có nhiều loại khóa: thứ tự toàn cục và giới hạn

Một quy tắc khóa theo thứ tự tăng dần thường **giảm mạnh** nguy cơ deadlock, nhưng không phải một câu thần chú bảo đảm zero deadlock trong mọi PostgreSQL transaction.

Tại sao vẫn có thể deadlock?

1. Một trigger lấy khóa bảng/hàng phụ ngoài thứ tự application dự kiến.
2. Foreign key và unique checks có thể tạo khóa gián tiếp.
3. Các code path khác chưa tuân thủ quy tắc.
4. Một transaction đã giữ khóa từ bước trước khi gọi service.
5. DDL/migration xen kẽ với DML.
6. Lock upgrade từ SHARE sang UPDATE.
7. Advisory lock được lấy theo thứ tự khác.
8. Một số kế hoạch thực thi nhiều hàng có thứ tự khóa khác dự kiến.
9. Một transaction dài cùng lúc cần nhiều resource không thể sắp xếp đơn giản nếu business process không được thiết kế lại.

Do đó chiến lược production nên có **hai lớp**:

- **Phòng ngừa:** ordering, transaction ngắn, khóa đúng phạm vi và quy trình nhất quán.
- **Phục hồi:** xử lý `40P01`, rollback và retry idempotent có giới hạn.

## 33. Câu hỏi thực tế: có nên tự giết phiên đang chặn?

Khi đang điều tra, một query có thể chỉ ra PID đang chặn. Nhưng tự gọi:

```sql
SELECT pg_cancel_backend(<pid>);
```

hoặc:

```sql
SELECT pg_terminate_backend(<pid>);
```

là **thao tác vận hành có tác động**, không phải phần xử lý deadlock thông thường của application. Trong ví dụ trên, `<pid>` chỉ là placeholder, không phải SQL chạy trực tiếp.

- `pg_cancel_backend` yêu cầu hủy query đang chạy của backend.
- `pg_terminate_backend` yêu cầu chấm dứt session, có thể rollback transaction của session.
- Quyền thực hiện bị giới hạn theo vai trò/permission.
- Việc hủy nhầm một transaction có thể làm gián đoạn request hoặc hệ thống.

PostgreSQL đã có deadlock detector. Khi gặp 40P01, **ưu tiên sửa lock ordering và retry**; chỉ can thiệp PID thủ công khi có quy trình DBA xác định rõ blocker và tác động.

## 34. Các lỗi phổ biến

### Lỗi 1 — Khóa “nguồn trước, đích sau”

Hai transfer ngược chiều tạo thứ tự A→B và B→A.

**Sửa:** khóa theo khóa định danh bất biến (min ID rồi max ID), không theo vai trò nguồn/đích.

### Lỗi 2 — Nghĩ chỉ UPDATE một hàng mỗi câu thì không deadlock

Một transaction có thể thực hiện nhiều UPDATE và giữ khóa từ các câu trước.

**Sửa:** xét toàn bộ transaction, không chỉ một statement.

### Lỗi 3 — Dùng SELECT FOR UPDATE nhưng lấy theo thứ tự ngược

FOR UPDATE cũng có thể chờ và tạo vòng.

**Sửa:** thứ tự nhất quán giữa mọi writer.

### Lỗi 4 — Dùng WHERE id IN (...) và mặc định thứ tự IN là thứ tự lock

SQL không cam kết như vậy.

**Sửa:** thiết kế kế hoạch khóa tường minh theo khóa đã sắp.

### Lỗi 5 — Nhầm deadlock_timeout với lock_timeout

deadlock_timeout quy định mốc kiểm tra deadlock; lock_timeout giới hạn chờ lấy khóa.

### Lỗi 6 — Nghĩ mọi lock wait dài đều là deadlock

Một transaction giữ khóa lâu nhưng không chờ ai khác vẫn có thể làm nhiều phiên khác đợi mà không có vòng chờ.

**Sửa:** dùng `pg_blocking_pids`, `pg_stat_activity` và logs để phân biệt.

### Lỗi 7 — Chỉ retry câu UPDATE báo 40P01

Sau lỗi, transaction cần rollback; những quyết định đọc trước đó có thể đã lỗi thời.

**Sửa:** retry toàn transaction.

### Lỗi 8 — Gửi sự kiện ngoài DB trước COMMIT

Transaction có thể rollback sau deadlock.

**Sửa:** xác nhận sau COMMIT, dùng outbox/idempotency.

### Lỗi 9 — Nâng cấp từ FOR SHARE sang UPDATE ở nhiều phiên

Hai phiên cùng giữ SHARE rồi cùng muốn lock mạnh hơn có thể tạo vòng chờ.

**Sửa:** nếu biết cần sửa, lấy FOR UPDATE phù hợp ngay từ đầu.

### Lỗi 10 — Không xem trigger/foreign key

Application khóa theo đúng thứ tự nhưng trigger lại sửa bảng khác ngoài protocol.

**Sửa:** điều tra mọi khóa trong cả transaction.

### Lỗi 11 — Dùng SKIP LOCKED cho chuyển tiền

Bỏ qua một account đang bị khóa làm thiếu nguồn/đích của thao tác.

**Sửa:** chỉ SKIP LOCKED với workload chấp nhận bỏ qua phần việc tạm thời, ví dụ job queue.

### Lỗi 12 — Kéo dài transaction khi chờ API mạng

Làm khóa bị giữ lâu, tăng lock wait và rủi ro deadlock.

**Sửa:** phần critical section ngắn; external effects sau commit/outbox.

### Lỗi 13 — Xem pg_locks không thấy tuple lock rồi kết luận không có row lock

Khóa hàng không phải lúc nào được liệt kê như một dòng dễ đọc.

**Sửa:** kết hợp blocker PID, transactionid waits và logs.

### Lỗi 14 — Chỉ test một connection

Không tạo được hai transaction độc lập đồng thời.

**Sửa:** hai connection và barrier.

### Lỗi 15 — Nuốt 40P01 như thành công

Transaction đã thất bại, không được trả kết quả thành công.

**Sửa:** rollback, retry hoặc báo lỗi sau khi hết retry.

### Lỗi 16 — Nghĩ SERIALIZABLE không có deadlock

SERIALIZABLE có thể báo 40001, nhưng transaction vẫn có thể có lock waits và deadlock 40P01.

### Lỗi 17 — Dùng khóa global thay vì theo resource

Mọi transfer hoặc ca trực độc lập cũng phải chờ nhau.

**Sửa:** khóa theo account/resource/tenant thích hợp, không lạm dụng một điểm nóng.

### Lỗi 18 — Không log SQLSTATE và transaction ID

Không phân biệt deadlock với timeout hoặc serialization failure.

**Sửa:** log an toàn theo correlation ID, lock order và SQLSTATE.

### Lỗi 19 — Sắp xếp theo giá trị có thể thay đổi

Nếu thứ tự lock dựa trên cột mutable, transaction khác có thể sửa giá trị làm cách chọn thứ tự khó dự đoán.

**Sửa:** dùng khóa định danh ổn định như primary key.

### Lỗi 20 — Không kiểm tra số hàng bị trừ trước khi cộng

Ngay cả khi đã tránh deadlock, một transfer có thể cộng tiền mà không trừ nếu không xử lý 0 rows.

**Sửa:** kiểm tra ROW COUNT/RETURNING và rollback toàn transaction nếu nghiệp vụ không thỏa.

## 35. Bài tập có lời giải

Các bài dưới đây dùng bảng `deadlock240.accounts`. Một số câu làm thay đổi dữ liệu; hãy thực hành trong transaction lab hoặc reset fixture khi đã kết thúc mọi phiên.

### Bài 1. Phân biệt lock wait và deadlock

**Đề:** T1 giữ A; T2 chờ A; T1 không chờ tài nguyên nào.

**Đáp án:** Đây là lock wait, chưa có deadlock vì không có vòng chờ.

### Bài 2. Vẽ wait-for graph

**Đề:** T1 giữ A chờ B; T2 giữ B chờ A.

**Đáp án:**

```text
T1 -> T2 -> T1
```

Có chu trình, deadlock.

### Bài 3. Tái hiện deadlock trên hai hàng

**Đáp án ngắn:**

```text
Session A: BEGIN; UPDATE account 10;
Session B: BEGIN; UPDATE account 20;
Session A: UPDATE account 20;  -- chờ
Session B: UPDATE account 10;  -- vòng chờ
```

PostgreSQL có thể hủy một transaction với `40P01`.

### Bài 4. Có chắc Session B là nạn nhân?

**Đáp án:** Không. Không dựa vào thứ tự terminal để dự đoán nạn nhân; ứng dụng phải xử lý lỗi ở bất kỳ transaction nào.

### Bài 5. Lỗi 40P01 là gì?

**Đáp án:** `deadlock_detected`. Thường cần rollback và retry toàn transaction nếu nghiệp vụ cho phép.

### Bài 6. Sửa thứ tự khóa cho transfer 20 → 10

**Đáp án:** vẫn khóa account 10 trước, account 20 sau, rồi thực hiện phép trừ ở 20 và cộng ở 10.

### Bài 7. Tại sao “nguồn trước” sai?

**Đáp án:** transfer ngược chiều có hai nguồn khác nhau, tạo thứ tự khóa A→B và B→A.

### Bài 8. Có nên viết UPDATE ... ORDER BY account_id?

**Đáp án:** PostgreSQL không cung cấp cú pháp UPDATE ORDER BY tổng quát như SELECT. Thiết kế thứ tự khóa riêng bằng FOR UPDATE hoặc protocol có kiểm soát.

### Bài 9. SELECT FOR UPDATE có nhả lock ngay sau SELECT không?

**Đáp án:** trong transaction thông thường, lock được giữ đến khi COMMIT/ROLLBACK, không tự nhả chỉ vì SELECT đã trả về.

### Bài 10. Vì sao hai FOR SHARE rồi UPDATE có thể deadlock?

**Đáp án:** hai transaction giữ shared locks tương thích; khi cả hai muốn nâng cấp sang mode update xung đột, mỗi bên cần bên kia nhả SHARE.

### Bài 11. Đặt giới hạn chờ khóa trong transaction

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT account_id
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

COMMIT;
```

**Lời giải:** nếu vượt giới hạn chờ lấy lock có thể lỗi; không nhầm với việc phát hiện deadlock theo 40P01.

### Bài 12. Xem PID nào đang chặn

```sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

**Lời giải:** hàm trả danh sách blocker hiện hành; không dùng một snapshot pg_stat_activity để suy ra toàn bộ lịch sử.

### Bài 13. Vì sao pg_locks không liệt kê mọi row lock?

**Đáp án:** PostgreSQL có thể lưu thông tin khóa hàng trên phiên bản tuple; lock wait có thể được thể hiện qua transactionid/tuple và cơ chế lock manager, không phải mỗi hàng đều là một dòng riêng trong pg_locks.

### Bài 14. deadlock_timeout = 1s nghĩa gì?

**Đáp án:** khoảng chờ trước khi PostgreSQL kiểm tra deadlock; không tự hủy mọi lock wait dài hơn 1 giây.

### Bài 15. SERIALIZABLE có tự hết deadlock không?

**Đáp án:** Không. SERIALIZABLE bảo vệ tính tuần tự hóa và có thể gây `40001`, nhưng vẫn có thể có lock waits/deadlock `40P01`.

### Bài 16. ON CONFLICT có bảo đảm không deadlock?

**Đáp án:** Không. Các transaction UPSERT nhiều khóa theo thứ tự ngược nhau có thể chờ chéo. Cần ordering và retry phù hợp.

### Bài 17. Foreign key làm tăng lock footprint thế nào?

**Đáp án:** kiểm tra/hành động liên quan khóa ngoại có thể cần khóa hàng cha/con, khiến một statement tác động thêm tài nguyên ngoài bảng application nhìn trực tiếp.

### Bài 18. Có dùng SKIP LOCKED cho job queue được không?

**Đáp án:** Có thể, nếu worker được phép tạm bỏ qua job đang bị khóa; vẫn cần retry, lease/recovery và idempotency.

### Bài 19. SKIP LOCKED có dùng cho chuyển tiền hai tài khoản được không?

**Đáp án:** Không nên. Nếu một tài khoản bị bỏ qua, workflow không có đủ tài nguyên bắt buộc để chuyển tiền đúng.

### Bài 20. Vì sao retry cần transaction mới?

**Đáp án:** transaction bị `40P01` đã thất bại; dữ liệu và quyết định cũ có thể không còn đúng. Phải rollback và bắt đầu lại.

### Bài 21. Khi nào lock ordering không đủ?

**Đáp án:** khi còn trigger/FK/DDL/advisory lock hoặc code path khác lấy khóa ngoài protocol; ứng dụng vẫn phải xử lý deadlock.

### Bài 22. Sửa một transaction dài

**Đề:** BEGIN → gọi HTTP 10 giây → SELECT FOR UPDATE → cập nhật → gọi email → COMMIT.

**Lời giải:** thực hiện hoạt động mạng/chuẩn bị ngoài critical section khi có thể, mở transaction chỉ khi cần đọc/khóa/ghi, COMMIT sớm; dùng outbox để gửi email sau commit.

### Bài 23. Vì sao cùng thứ tự khóa có thể chỉ tạo wait?

**Đáp án:** transaction sau đợi khóa đầu tiên, chưa giữ khóa sau mà transaction trước cần, nên không tạo vòng chờ do cặp tài nguyên đó.

### Bài 24. Tổng số dư sau một transaction bị deadlock rollback nên là bao nhiêu?

**Đáp án:** nếu fixture có 1000+1000 và một transfer nguyên tử hợp lệ commit còn một transfer rollback, tổng vẫn là 2000; kết quả từng tài khoản phụ thuộc giao dịch nào thành công.

## 36. Checklist thiết kế, test và vận hành

| Câu hỏi | Rủi ro nếu bỏ qua |
|---|---|
| Một transaction có thể khóa bao nhiêu tài nguyên? | Không nhìn thấy chu trình tiềm ẩn |
| Có quy tắc khóa toàn cục theo loại tài nguyên? | Endpoint lấy khóa ngược chiều |
| Có thứ tự tăng dần theo khóa định danh ổn định? | Batch/transfer dễ đảo thứ tự |
| Có khóa trước khi tính toán dựa trên dữ liệu cần giữ nhất quán? | Quyết định stale |
| Có kiểm tra số hàng UPDATE/RETURNING? | Ghi một phía của nghiệp vụ |
| Trigger và FK có lấy khóa gián tiếp không? | Lock order thực tế khác dự kiến |
| Có transaction idle in transaction? | Giữ khóa lâu |
| Có timeout phù hợp? | Request chờ quá lâu |
| Có retry 40P01/40001 toàn transaction? | Một xung đột gây lỗi vĩnh viễn |
| Có idempotency cho request retry? | Side effect trùng |
| Có log SQLSTATE và application_name? | Khó chẩn đoán |
| Có giám sát pg_blocking_pids và lock waits? | Không thấy điểm nóng |
| Có test hai session với barrier? | Test tuần tự bỏ sót deadlock |
| Có test lock upgrade? | Bỏ sót deadlock cùng một hàng |
| Migrations có được phối hợp với DML? | Table lock conflict |
| Đã kiểm chứng các bất biến nghiệp vụ sau commit? | Tránh deadlock nhưng dữ liệu vẫn sai |

## 37. Tài liệu PostgreSQL chính thức để tra cứu theo phiên bản

- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): các mode khóa, bảng conflict, row-level locking, deadlock, advisory locks.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, quan sát backend và chờ.
- [System View pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): diễn giải `pg_locks`.
- [Lock Management Functions](https://www.postgresql.org/docs/current/functions-admin.html): các hàm trợ giúp, gồm `pg_blocking_pids()`.
- [Runtime Configuration: Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html): các tham số deadlock/lock monitoring phù hợp.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): `lock_timeout` và `statement_timeout`.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): MVCC, READ COMMITTED, REPEATABLE READ, SERIALIZABLE.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `40P01`, `40001`, `55P03` và mã lỗi liên quan.

Kiểm tra phiên bản và cấu hình ở môi trường của bạn:

```sql
SHOW server_version;
SHOW transaction_isolation;
SHOW deadlock_timeout;
SHOW lock_timeout;
SHOW statement_timeout;
```

## 38. Tổng kết

Deadlock xảy ra khi các transaction **giữ khóa và đợi lẫn nhau theo vòng**. Ví dụ transfer:

```text
T1 chuyển 10 -> 20:
    khóa account 10
    chờ account 20

T2 chuyển 20 -> 10:
    khóa account 20
    chờ account 10

T1 <---- chờ chéo ----> T2
=> Deadlock
=> PostgreSQL hủy một transaction (40P01)
```

Thay vì khóa theo “nguồn trước, đích sau”, ứng dụng chọn quy tắc:

```text
Mọi transfer:
    khóa min(account_id)
    khóa max(account_id)
    kiểm tra nghiệp vụ
    cập nhật nguồn/đích
    COMMIT
```

Khi mọi writer thực sự tuân thủ cùng thứ tự, nguy cơ vòng chờ do chính cặp tài khoản đó giảm rõ rệt. Nhưng vẫn phải quan sát các khóa gián tiếp từ FK/trigger/DDL và **chuẩn bị retry**.

Các nguyên tắc cốt lõi:

1. **Lock wait không phải deadlock.** Chỉ có vòng chờ mới là bế tắc; một transaction đợi lâu có thể chỉ là contention.
2. **Khóa sống trong transaction.** Statement UPDATE kết thúc không có nghĩa khóa nhả nếu chưa COMMIT/ROLLBACK.
3. **Thứ tự khóa quan trọng hơn thứ tự dòng tiền.** Khóa theo key ổn định, không theo role nguồn/đích.
4. **FOR UPDATE không tự chữa thứ tự khóa ngược.** Nó giúp khóa chủ động, nhưng cũng có thể tạo deadlock nếu dùng sai.
5. **Không tin IN(...) hay UPDATE tự khóa theo thứ tự bạn viết.** Thiết kế protocol rõ cho các khóa nhiều hàng.
6. **Deadlock có thể đến từ nhiều bảng, trigger, foreign key, UNIQUE, advisory lock và nâng cấp khóa.**
7. **PostgreSQL phá deadlock bằng cách hủy một transaction.** Bắt SQLSTATE `40P01`, rollback và retry **toàn bộ transaction**.
8. **SERIALIZABLE không loại bỏ mọi deadlock**, và serialization failure `40001` là hiện tượng khác.
9. **Quan sát bằng pg_stat_activity, pg_blocking_pids(), pg_locks và logs**, đừng đoán từ thời gian phản hồi.
10. **Phòng ngừa cộng phục hồi:** khóa đúng thứ tự, transaction ngắn, giới hạn thời gian chờ, kiểm thử concurrency và retry có idempotency.

**Một câu để nhớ:** hai giao dịch cùng cần A và B sẽ dễ deadlock nếu một bên lấy A→B còn bên kia lấy B→A; hãy thống nhất một thứ tự lấy khóa cho mọi giao dịch và luôn xử lý được trường hợp PostgreSQL báo `40P01`.

