# Thiết kế dữ liệu mẫu, trạng thái ban đầu và kết quả mong đợi

Thực nghiệm điều khiển đồng thời bằng hai phiên (two-session experiment) chỉ có giá trị khi người học có thể tái tạo cùng một lịch thực thi và giải thích được kết quả. Nếu dữ liệu ban đầu không rõ, hai phiên chạy sai thứ tự hoặc một transaction còn sót từ lần thử trước, kết quả quan sát được rất dễ bị hiểu nhầm.

Vì vậy, trước khi viết câu lệnh cho Session A và Session B, cần thiết kế ba thứ: **bộ dữ liệu mẫu**, **trạng thái ban đầu đã biết**, và **kết quả mong đợi cho từng bước**. Mỗi thực nghiệm phải trả lời được dữ liệu nào được đọc, hàng nào được thay đổi, transaction nào commit/rollback và trạng thái cuối nào chứng minh cơ chế đồng thời đang hoạt động.

Bài này xây dựng một bộ dữ liệu nhỏ để dùng cho nhiều thực nghiệm: dirty read, lost update, non-repeatable read, phantom read, write skew, lock wait, deadlock và unique-key conflict. Các ví dụ SQL dùng PostgreSQL làm cú pháp tham chiếu; những khác biệt quan trọng của SQL Server và MySQL/InnoDB được nêu riêng. Khi chạy trên DBMS khác, hãy điều chỉnh DDL và cú pháp isolation level theo đúng hệ quản trị.

## 1. Mục tiêu của một bộ dữ liệu thực nghiệm tốt

Một bộ dữ liệu thực nghiệm không cần giống dữ liệu production. Nó cần nhỏ, có thể đặt lại chính xác và làm lộ rõ hiện tượng đang nghiên cứu.

Các tiêu chí nên có:

1. **Trạng thái ban đầu tường minh:** biết chính xác mỗi hàng có giá trị gì trước khi Session A và B bắt đầu.
2. **Khóa nghiệp vụ dễ đọc:** ID nhỏ, cố định và có ý nghĩa như tài khoản 1, tài khoản 2, sản phẩm 101.
3. **Ít dữ liệu nhưng đủ tạo xung đột:** một hoặc hai hàng thường đủ cho lost update; phantom cần một tập hàng và một predicate; write skew cần ít nhất hai hàng cùng tham gia một invariant.
4. **Không phụ thuộc dữ liệu ngẫu nhiên:** tránh ID tự sinh khó đoán, timestamp hiện tại hoặc thứ tự không ổn định nếu chúng không phải nội dung thực nghiệm.
5. **Có thể reset:** trước mỗi lần chạy, đưa bảng về cùng một trạng thái đã định nghĩa.
6. **Kết quả có thể kiểm chứng:** dùng SELECT cuối cùng, số hàng bị ảnh hưởng, exception hoặc lock wait để xác nhận.
7. **Tách dữ liệu giữa các bài:** reset đúng các bảng liên quan và không để transaction trước còn mở.

Một thực nghiệm tốt mô tả được lịch chạy như sau:

```text
Trạng thái đầu S0
    |
    +--> Session A: bước A1
    |
    +--> Session B: bước B1
    |
    +--> Session A: bước A2
    |
    +--> Session B: bước B2
    |
    v
Commit / Rollback theo lịch
    |
    v
Trạng thái cuối S1 và kết quả cần quan sát
```

Không chạy toàn bộ script A rồi mới chạy toàn bộ script B nếu mục tiêu là tạo một interleaving cụ thể. Hai cửa sổ SQL cần được điều khiển từng bước theo lịch đã viết.

## 2. Chọn một DBMS tham chiếu và ghi rõ khác biệt

Các DBMS có cú pháp và semantics isolation khác nhau. Để kết quả không mơ hồ, tài liệu thực nghiệm nên ghi rõ:

- Tên DBMS và phiên bản.
- Storage engine (đặc biệt với MySQL, cần xác nhận bảng dùng InnoDB).
- Isolation level thực tế của từng session.
- Autocommit đang bật hay tắt.
- Cấu hình có ảnh hưởng đến đọc phiên bản, như RCSI/Snapshot của SQL Server.
- Câu lệnh reset đã chạy và trạng thái ban đầu đã được xác nhận.

Trong bài này, PostgreSQL là cú pháp tham chiếu cho các script `BEGIN`, `COMMIT`, `ROLLBACK`, `SET TRANSACTION` và `RETURNING`. Một số khác biệt quan trọng:

| Hệ quản trị | Điểm cần ghi nhớ khi thực nghiệm |
|---|---|
| PostgreSQL | `READ UNCOMMITTED` được xử lý như `READ COMMITTED`; `REPEATABLE READ` dùng snapshot và có thể cho phép write skew; `SERIALIZABLE` dùng SSI và có thể hủy transaction với serialization failure. |
| MySQL/InnoDB | Mặc định thường là `REPEATABLE READ`; consistent read và locking read có semantics khác nhau; `READ UNCOMMITTED` có thể đọc dữ liệu chưa commit; gap/next-key lock có thể ảnh hưởng phantom. |
| SQL Server | `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` và các mức Snapshot/RCSI có hành vi khác nhau; `READ COMMITTED` có thể dùng locking hoặc row versioning tùy cấu hình. |

Nếu mục tiêu là so sánh nhiều DBMS, hãy chạy cùng một lịch logic trên từng hệ thống nhưng ghi kết quả riêng. Không lấy kết quả PostgreSQL rồi giả định MySQL hoặc SQL Server phải cho cùng một kết quả.

## 3. Tạo schema thực nghiệm

Các bảng dưới đây được thiết kế để dùng lại trong nhiều bài. ID được khai báo tường minh để reset dễ dàng; không cần dựa vào sequence hoặc identity.

```sql
CREATE TABLE lab_account (
    account_id INTEGER PRIMARY KEY,
    owner_name VARCHAR(50) NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_lab_account_balance CHECK (balance >= 0)
);

CREATE TABLE lab_inventory (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(100) NOT NULL,
    stock INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_lab_inventory_stock CHECK (stock >= 0)
);

CREATE TABLE lab_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE lab_doctor_duty (
    doctor_id INTEGER PRIMARY KEY,
    department_id INTEGER NOT NULL,
    doctor_name VARCHAR(50) NOT NULL,
    on_call BOOLEAN NOT NULL
);

CREATE TABLE lab_booking (
    booking_id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL,
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT ck_lab_booking_interval CHECK (start_at < end_at)
);
```

Các bảng cố ý có những đặc điểm khác nhau:

- `lab_account`: dùng cho cập nhật cùng hàng, lost update, version check, lock wait và deadlock.
- `lab_inventory`: dùng cho điều kiện cập nhật tồn kho và unique-key conflict.
- `lab_order`: dùng cho truy vấn theo predicate, non-repeatable/phantom read.
- `lab_doctor_duty`: dùng cho invariant nhiều hàng và write skew.
- `lab_booking`: dùng để minh họa predicate theo khoảng thời gian. Bảng này chưa có constraint ngăn overlap vì một số bài cần quan sát lỗi khi chỉ kiểm tra bằng SELECT.

Nếu DBMS không hỗ trợ kiểu `BOOLEAN`, thay bằng `BIT`, `SMALLINT` hoặc kiểu tương ứng. Với SQL Server, dùng `DATETIME2` thay cho `TIMESTAMP` vì `TIMESTAMP` trong SQL Server là synonym cũ của `rowversion`, không phải kiểu ngày giờ. Tên bảng `lab_order` được dùng để tránh từ khóa `ORDER`.

## 4. Dữ liệu mẫu và trạng thái ban đầu chuẩn

Sau khi tạo bảng, nạp dữ liệu cố định:

```sql
INSERT INTO lab_account (account_id, owner_name, balance, version) VALUES
(1, 'An', 1000.00, 0),
(2, 'Binh', 1000.00, 0);

INSERT INTO lab_inventory (product_id, sku, product_name, stock, version) VALUES
(101, 'SKU-101', 'Keyboard', 5, 0),
(102, 'SKU-102', 'Mouse', 2, 0);

INSERT INTO lab_order (order_id, customer_id, status, created_at) VALUES
(1001, 7, 'OPEN',      TIMESTAMP '2026-11-01 09:00:00'),
(1002, 7, 'OPEN',      TIMESTAMP '2026-11-02 09:00:00'),
(1003, 7, 'CANCELLED', TIMESTAMP '2026-11-03 09:00:00'),
(1004, 8, 'OPEN',      TIMESTAMP '2026-11-04 09:00:00');

INSERT INTO lab_doctor_duty
    (doctor_id, department_id, doctor_name, on_call) VALUES
(1, 10, 'Doctor A', TRUE),
(2, 10, 'Doctor B', TRUE),
(3, 10, 'Doctor C', FALSE);

INSERT INTO lab_booking
    (booking_id, room_id, start_at, end_at, status) VALUES
(501, 20, TIMESTAMP '2026-11-20 09:00:00',
          TIMESTAMP '2026-11-20 10:00:00', 'CONFIRMED'),
(502, 20, TIMESTAMP '2026-11-20 11:00:00',
          TIMESTAMP '2026-11-20 12:00:00', 'CONFIRMED'),
(503, 21, TIMESTAMP '2026-11-20 09:00:00',
          TIMESTAMP '2026-11-20 10:00:00', 'CONFIRMED');
```

Trạng thái ban đầu cần được ghi lại trước khi thực nghiệm:

**Tài khoản**

| account_id | owner_name | balance | version |
|---:|---|---:|---:|
| 1 | An | 1000.00 | 0 |
| 2 | Binh | 1000.00 | 0 |

**Tồn kho**

| product_id | sku | product_name | stock | version |
|---:|---|---|---:|---:|
| 101 | SKU-101 | Keyboard | 5 | 0 |
| 102 | SKU-102 | Mouse | 2 | 0 |

**Đơn hàng của customer 7**

| order_id | customer_id | status | Có được tính là đang mở? |
|---:|---:|---|---|
| 1001 | 7 | OPEN | Có |
| 1002 | 7 | OPEN | Có |
| 1003 | 7 | CANCELLED | Không |

**Lịch trực khoa 10**

| doctor_id | doctor_name | on_call |
|---:|---|---|
| 1 | Doctor A | TRUE |
| 2 | Doctor B | TRUE |
| 3 | Doctor C | FALSE |

**Booking phòng 20**

| booking_id | Khoảng thời gian | status |
|---:|---|---|
| 501 | 09:00–10:00 | CONFIRMED |
| 502 | 11:00–12:00 | CONFIRMED |

Những giá trị này được chọn có chủ đích. Ví dụ, customer 7 có đúng hai đơn OPEN và một đơn CANCELLED; điều này giúp truy vấn phantom có kết quả ban đầu là 2 thay vì một con số khó nhớ.

## 5. Kiểm tra trạng thái trước khi mở hai phiên

Sau khi nạp dữ liệu, chạy các truy vấn sau trong một session quản trị:

```sql
SELECT * FROM lab_account ORDER BY account_id;
SELECT * FROM lab_inventory ORDER BY product_id;
SELECT order_id, customer_id, status
FROM lab_order
ORDER BY order_id;
SELECT doctor_id, department_id, on_call
FROM lab_doctor_duty
ORDER BY doctor_id;
SELECT booking_id, room_id, start_at, end_at, status
FROM lab_booking
ORDER BY booking_id;
```

Kết quả phải khớp các bảng trạng thái ban đầu ở trên. Nếu không khớp, chưa nên bắt đầu Session A/B. Hãy reset trước.

### Script reset cho lần chạy tiếp theo

Khi thực nghiệm đã kết thúc và không còn transaction nào mở trên các bảng lab, có thể reset dữ liệu bằng:

```sql
DELETE FROM lab_booking;
DELETE FROM lab_doctor_duty;
DELETE FROM lab_order;
DELETE FROM lab_inventory;
DELETE FROM lab_account;

INSERT INTO lab_account (account_id, owner_name, balance, version) VALUES
(1, 'An', 1000.00, 0),
(2, 'Binh', 1000.00, 0);

INSERT INTO lab_inventory (product_id, sku, product_name, stock, version) VALUES
(101, 'SKU-101', 'Keyboard', 5, 0),
(102, 'SKU-102', 'Mouse', 2, 0);

INSERT INTO lab_order (order_id, customer_id, status, created_at) VALUES
(1001, 7, 'OPEN',      TIMESTAMP '2026-11-01 09:00:00'),
(1002, 7, 'OPEN',      TIMESTAMP '2026-11-02 09:00:00'),
(1003, 7, 'CANCELLED', TIMESTAMP '2026-11-03 09:00:00'),
(1004, 8, 'OPEN',      TIMESTAMP '2026-11-04 09:00:00');

INSERT INTO lab_doctor_duty
    (doctor_id, department_id, doctor_name, on_call) VALUES
(1, 10, 'Doctor A', TRUE),
(2, 10, 'Doctor B', TRUE),
(3, 10, 'Doctor C', FALSE);

INSERT INTO lab_booking
    (booking_id, room_id, start_at, end_at, status) VALUES
(501, 20, TIMESTAMP '2026-11-20 09:00:00',
          TIMESTAMP '2026-11-20 10:00:00', 'CONFIRMED'),
(502, 20, TIMESTAMP '2026-11-20 11:00:00',
          TIMESTAMP '2026-11-20 12:00:00', 'CONFIRMED'),
(503, 21, TIMESTAMP '2026-11-20 09:00:00',
          TIMESTAMP '2026-11-20 10:00:00', 'CONFIRMED');
```

Nếu một lần chạy kết thúc bằng deadlock hoặc serialization failure, transaction victim có thể đã tự rollback theo DBMS. Vẫn cần kiểm tra trạng thái tất cả bảng trước khi reset; không giả định mọi câu lệnh trước lỗi đã commit.

## 6. Quy tắc điều khiển hai session

Mở hai cửa sổ kết nối độc lập đến cùng database và cùng schema: gọi là **Session A** và **Session B**. Không dùng chung một connection cho hai cửa sổ.

Trước khi bắt đầu:

- Tắt chế độ tự động commit nếu công cụ SQL có tùy chọn đó, hoặc dùng `BEGIN`/`COMMIT` rõ ràng.
- Đảm bảo cả hai session không còn transaction cũ. PostgreSQL có thể dùng `ROLLBACK;` ở mỗi cửa sổ trước bài mới.
- Chạy reset bằng session quản trị khi A/B đã kết thúc.
- Không chạy một script chứa toàn bộ bước A1, A2, A3 liên tục nếu giữa chúng cần B thực hiện bước xen kẽ.
- Ghi lại isolation level thực tế của từng session.
- Khi một câu lệnh bị block, để nó chờ đúng thời điểm cần quan sát; không bấm chạy lại nhiều lần.

Mẫu lịch trong tài liệu:

| Ký hiệu | Ý nghĩa |
|---|---|
| A1, A2, ... | Bước tiếp theo cần chạy trong Session A |
| B1, B2, ... | Bước tiếp theo cần chạy trong Session B |
| A-commit / B-commit | Commit transaction của session tương ứng |
| A-rollback / B-rollback | Rollback transaction của session tương ứng |
| `BLOCKED` | Câu lệnh chưa hoàn tất vì đang chờ tài nguyên |
| `ERROR` | DBMS từ chối câu lệnh/transaction; ghi lại mã lỗi |

Mỗi bài thực nghiệm cần có bốn phần: reset, lịch thao tác, kết quả dự kiến và truy vấn xác nhận.

## 7. Thực nghiệm 1: Dirty read

**Mục tiêu:** quan sát liệu Session B có thể đọc giá trị chưa commit do Session A ghi hay không.

Trạng thái đầu: `lab_account.account_id = 1` có `balance = 1000.00`.

### Lịch thực hiện

**Session A**

```sql
BEGIN;

UPDATE lab_account
SET balance = 700.00
WHERE account_id = 1;

-- Chưa COMMIT hoặc ROLLBACK.
```

**Session B**

Ở DBMS hỗ trợ `READ UNCOMMITTED`:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT balance
FROM lab_account
WHERE account_id = 1;
```

Sau khi quan sát kết quả, kết thúc transaction B:

```sql
COMMIT;
```

Quay lại **Session A**:

```sql
ROLLBACK;
```

### Kết quả mong đợi

| DBMS/isolation | Giá trị B có thể đọc khi A chưa commit |
|---|---:|
| PostgreSQL `READ UNCOMMITTED` | 1000.00; PostgreSQL xử lý mức này như `READ COMMITTED` |
| MySQL/InnoDB `READ UNCOMMITTED` | Có thể đọc 700.00 chưa commit |
| SQL Server `READ UNCOMMITTED` hoặc hint `NOLOCK` | Có thể đọc 700.00 chưa commit |
| `READ COMMITTED` thông thường | Không đọc dirty value; có thể chờ hoặc đọc giá trị đã commit tùy cơ chế DBMS |

Sau khi A rollback, trạng thái cuối phải là `balance = 1000.00`. Nếu B đã đọc 700.00 nhưng A rollback, B đã quan sát một giá trị không bao giờ được commit: đó là dirty read.

Không kết luận “DBMS không hỗ trợ dirty read” chỉ vì truy vấn không trả về ngay; hãy xác định session đang block hay đã đọc một phiên bản đã commit.

## 8. Thực nghiệm 2: Lost update khi ghi giá trị tuyệt đối

**Mục tiêu:** chứng minh hai transaction cùng đọc một giá trị, tính toán riêng rồi ghi giá trị tuyệt đối có thể làm mất một thay đổi.

Trạng thái đầu: account 1 có `balance = 1000.00`.

### Lịch thực hiện

**A1 — Session A đọc số dư**

```sql
BEGIN;
SELECT balance FROM lab_account WHERE account_id = 1;
```

Kết quả A đọc: `1000.00`. Ứng dụng tính `1000 + 100 = 1100`.

**B1 — Session B cũng đọc số dư**

```sql
BEGIN;
SELECT balance FROM lab_account WHERE account_id = 1;
```

Kết quả B đọc: `1000.00`. Ứng dụng tính `1000 + 200 = 1200`.

**A2 — Session A ghi kết quả đã tính và commit**

```sql
UPDATE lab_account
SET balance = 1100.00
WHERE account_id = 1;

COMMIT;
```

**B2 — Session B ghi kết quả đã tính từ snapshot cũ và commit**

```sql
UPDATE lab_account
SET balance = 1200.00
WHERE account_id = 1;

COMMIT;
```

### Kết quả mong đợi

| Mốc | balance |
|---|---:|
| Ban đầu | 1000.00 |
| Sau A commit | 1100.00 |
| Sau B commit | 1200.00 |
| Kết quả đúng nếu cộng cả hai khoản | 1300.00 |

Giá trị cuối `1200.00` cho thấy khoản cộng 100 của A bị ghi đè. Đây là lost update do ứng dụng gửi giá trị tuyệt đối được tính từ dữ liệu cũ.

### Biến thể an toàn: cập nhật tương đối trong SQL

Reset account 1 về 1000.00. Sau đó chạy:

**Session A**

```sql
BEGIN;
UPDATE lab_account
SET balance = balance + 100.00
WHERE account_id = 1;
COMMIT;
```

**Session B**

```sql
BEGIN;
UPDATE lab_account
SET balance = balance + 200.00
WHERE account_id = 1;
COMMIT;
```

Kết quả cuối phải là `1300.00`, bất kể transaction nào được chạy trước. DBMS điều phối hai cập nhật trên cùng hàng và phép cộng được thực hiện trên giá trị hiện tại khi mỗi UPDATE được áp dụng.

## 9. Thực nghiệm 3: Optimistic version check

**Mục tiêu:** dùng cột version để phát hiện transaction đang ghi dựa trên trạng thái cũ.

Trạng thái đầu sau reset: account 1 có `balance = 1000.00`, `version = 0`.

**A1 — Session A đọc**

```sql
BEGIN;
SELECT balance, version
FROM lab_account
WHERE account_id = 1;
```

A nhận `(1000.00, 0)`.

**B1 — Session B đọc cùng phiên bản**

```sql
BEGIN;
SELECT balance, version
FROM lab_account
WHERE account_id = 1;
```

B cũng nhận `(1000.00, 0)`.

**A2 — A cập nhật có điều kiện**

```sql
UPDATE lab_account
SET balance = 1100.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0;
```

Kết quả mong đợi: affected rows = 1. A commit.

**B2 — B dùng version đã đọc trước đó**

```sql
UPDATE lab_account
SET balance = 1200.00,
    version = version + 1
WHERE account_id = 1
  AND version = 0;
```

Kết quả mong đợi: affected rows = 0 vì version hiện tại đã là 1. B rollback hoặc kết thúc transaction theo quy tắc ứng dụng.

### Trạng thái cuối mong đợi

| account_id | balance | version |
|---:|---:|---:|
| 1 | 1100.00 | 1 |

Ứng dụng cần coi affected rows = 0 là xung đột hoặc không tìm thấy, không được báo cập nhật thành công. Câu lệnh này bảo vệ cập nhật trên hàng account 1; nó không tự bảo vệ invariant tổng hợp nhiều hàng.

## 10. Thực nghiệm 4: Non-repeatable read

**Mục tiêu:** Session A đọc cùng một hàng hai lần nhưng nhận giá trị khác vì Session B đã commit cập nhật.

Trạng thái đầu: account 1 có balance 1000.00.

### Lịch ở READ COMMITTED

**A1 — Session A**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM lab_account WHERE account_id = 1;
```

Kết quả lần đọc đầu: `1000.00`.

**B1 — Session B**

```sql
BEGIN;
UPDATE lab_account
SET balance = 1250.00
WHERE account_id = 1;
COMMIT;
```

**A2 — Session A đọc lại cùng hàng**

```sql
SELECT balance FROM lab_account WHERE account_id = 1;
COMMIT;
```

Trong PostgreSQL `READ COMMITTED`, mỗi statement có snapshot mới; lần đọc thứ hai thường thấy `1250.00`. Đây là non-repeatable read.

### Biến thể REPEATABLE READ

Reset account 1 về 1000.00. Mở A với `BEGIN ISOLATION LEVEL REPEATABLE READ;`, đọc lần đầu, rồi cho B cập nhật và commit. Khi A đọc lại, PostgreSQL thường tiếp tục thấy snapshot ban đầu là `1000.00`. Trong DBMS khác, cách thực thi `REPEATABLE READ` có thể khác; hãy ghi rõ hệ quản trị và loại read (consistent read hay locking read).

Kết quả cần so sánh là giá trị A đọc lần một và lần hai, không chỉ nhìn trạng thái cuối của bảng.

## 11. Thực nghiệm 5: Phantom read theo predicate

**Mục tiêu:** Session A truy vấn một tập hàng theo điều kiện; Session B chèn một hàng mới thỏa điều kiện; A chạy lại cùng predicate.

Trạng thái đầu của customer 7: hai đơn `OPEN` (1001, 1002), một đơn `CANCELLED` (1003).

### Lịch READ COMMITTED

**A1 — Session A**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS open_orders
FROM lab_order
WHERE customer_id = 7
  AND status = 'OPEN';
```

Kết quả đầu: `2`.

**B1 — Session B**

```sql
BEGIN;

INSERT INTO lab_order (order_id, customer_id, status, created_at)
VALUES (1005, 7, 'OPEN', TIMESTAMP '2026-11-05 09:00:00');

COMMIT;
```

**A2 — Session A chạy lại đúng predicate**

```sql
SELECT COUNT(*) AS open_orders
FROM lab_order
WHERE customer_id = 7
  AND status = 'OPEN';

COMMIT;
```

Ở PostgreSQL `READ COMMITTED`, kết quả lần hai là `3`. Hàng 1005 là phantom đối với truy vấn của A.

### Biến thể REPEATABLE READ/SERIALIZABLE

Reset `lab_order` về trạng thái ban đầu. Chạy lại cùng lịch nhưng bắt đầu A ở isolation level cần khảo sát. PostgreSQL `REPEATABLE READ` giữ snapshot nên truy vấn lặp lại thường vẫn thấy 2; `SERIALIZABLE` có thể phát hiện phụ thuộc và hủy một transaction tùy lịch đầy đủ. SQL Server `SERIALIZABLE` có thể dùng key-range lock và làm B chờ; MySQL/InnoDB `REPEATABLE READ` có snapshot semantics cho consistent read, trong khi locking read và range lock có quy tắc riêng.

Không chỉ ghi “phantom bị ngăn” hay “phantom xuất hiện”. Hãy ghi rõ transaction nào bị block, transaction nào commit và A có nhận serialization error hay không.

## 12. Thực nghiệm 6: Write skew trên invariant nhiều hàng

**Mục tiêu:** chứng minh hai transaction có thể cập nhật hai hàng khác nhau nhưng cùng phá một quy tắc nghiệp vụ.

Invariant: khoa 10 phải luôn có ít nhất một bác sĩ trực. Trạng thái đầu có bác sĩ 1 và 2 đang trực, bác sĩ 3 không trực.

### Lịch trên snapshot isolation / PostgreSQL REPEATABLE READ

**A1 — Session A**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM lab_doctor_duty
WHERE department_id = 10
  AND on_call = TRUE;
```

A đọc `2`.

**B1 — Session B**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM lab_doctor_duty
WHERE department_id = 10
  AND on_call = TRUE;
```

B cũng đọc `2`.

**A2 — A tắt bác sĩ 1**

```sql
UPDATE lab_doctor_duty
SET on_call = FALSE
WHERE doctor_id = 1;
```

**B2 — B tắt bác sĩ 2**

```sql
UPDATE lab_doctor_duty
SET on_call = FALSE
WHERE doctor_id = 2;
```

Hai UPDATE tác động hai hàng khác nhau. Trong PostgreSQL `REPEATABLE READ`, cả hai transaction có thể commit vì không có write-write conflict trên cùng hàng:

```sql
-- Session A
COMMIT;

-- Session B
COMMIT;
```

Trạng thái cuối có thể là 0 bác sĩ đang trực, vi phạm invariant. Đây là write skew.

### Biến thể SERIALIZABLE

Reset bảng duty. Chạy cùng lịch với `SERIALIZABLE` cho cả hai session. PostgreSQL SSI có thể cho một transaction commit và hủy transaction còn lại bằng serialization failure. Ghi lại session nào commit và session nào nhận lỗi; thứ tự victim có thể thay đổi.

Nếu DBMS dùng locking serializable, transaction có thể block hoặc deadlock thay vì trả cùng loại lỗi. Kết quả mong đợi ở cấp nghiệp vụ là không được commit trạng thái có 0 bác sĩ trực.

## 13. Thực nghiệm 7: Lock wait trên cùng một hàng

**Mục tiêu:** quan sát một transaction giữ khóa ghi và transaction khác phải chờ.

Trạng thái đầu: account 1 có balance 1000.00.

**A1 — Session A**

```sql
BEGIN;

UPDATE lab_account
SET balance = balance + 100.00
WHERE account_id = 1;

-- Giữ transaction mở, chưa commit.
```

**B1 — Session B**

```sql
BEGIN;

UPDATE lab_account
SET balance = balance + 200.00
WHERE account_id = 1;
```

B thường ở trạng thái `BLOCKED` khi A vẫn giữ khóa xung đột.

**A2 — Session A**

```sql
COMMIT;
```

Sau khi A commit, B được tiếp tục. **B2 — Session B**:

```sql
COMMIT;
```

Trạng thái cuối phải là `balance = 1300.00`. Ghi nhận thời gian B bắt đầu chờ và thời điểm B tiếp tục. Nếu B không chờ, kiểm tra xem hai session có thực sự kết nối cùng database, cùng hàng và transaction A còn mở hay không.

## 14. Thực nghiệm 8: Deadlock bằng thứ tự cập nhật ngược nhau

**Mục tiêu:** tạo chu trình chờ trên hai hàng tài khoản.

Trạng thái đầu: account 1 và account 2 đều có balance 1000.00.

**A1 — Session A khóa hàng 1**

```sql
BEGIN;
UPDATE lab_account
SET balance = balance + 10
WHERE account_id = 1;
```

**B1 — Session B khóa hàng 2**

```sql
BEGIN;
UPDATE lab_account
SET balance = balance + 20
WHERE account_id = 2;
```

**A2 — Session A yêu cầu hàng 2**

```sql
UPDATE lab_account
SET balance = balance + 10
WHERE account_id = 2;
```

A phải chờ B.

**B2 — Session B yêu cầu hàng 1**

```sql
UPDATE lab_account
SET balance = balance + 20
WHERE account_id = 1;
```

Lúc này DBMS có thể phát hiện deadlock và hủy một transaction. Ghi lại session bị chọn làm victim và mã lỗi. Session còn lại có thể tiếp tục sau khi khóa được giải phóng; nếu không tự tiếp tục, kiểm tra transaction state và kết thúc nó đúng cách.

### Kết quả mong đợi

- Có một transaction bị deadlock victim/rollback.
- Transaction còn lại có thể commit cả hai cập nhật mà nó thực hiện.
- Không được giả định cả A và B đều commit.
- Trạng thái cuối phụ thuộc transaction nào bị hủy; hãy đọc giá trị thực tế và đối chiếu với log deadlock.

Sau bài, reset account 1 và 2 về 1000.00 trước khi chạy bài tiếp theo. Không chạy lại một bên trong khi transaction của bên kia vẫn còn mở.

## 15. Thực nghiệm 9: Unique-key conflict khi hai phiên cùng tạo một khóa

**Mục tiêu:** kiểm tra ràng buộc duy nhất là hàng rào cuối cùng cho cùng một khóa nghiệp vụ.

Dùng `lab_inventory.sku`, hiện có `SKU-101` và `SKU-102`. Chọn một SKU chưa tồn tại như `SKU-NEW`.

**A1 — Session A**

```sql
BEGIN;
INSERT INTO lab_inventory
    (product_id, sku, product_name, stock, version)
VALUES
    (201, 'SKU-NEW', 'New Product A', 3, 0);
-- Chưa commit.
```

**B1 — Session B**

```sql
BEGIN;
INSERT INTO lab_inventory
    (product_id, sku, product_name, stock, version)
VALUES
    (202, 'SKU-NEW', 'New Product B', 4, 0);
```

B có thể chờ quyết định của A vì cùng tranh chấp unique key. Nếu A commit, B nhận unique violation. Nếu A rollback, B có thể chèn thành công.

Để quan sát nhánh đầu:

```sql
-- Session A
COMMIT;
```

Sau khi B nhận lỗi, rollback transaction B nếu DBMS yêu cầu:

```sql
-- Session B
ROLLBACK;
```

Trạng thái cuối phải có đúng một hàng `SKU-NEW`, cụ thể là hàng product 201 nếu A commit. Không được có hai hàng cùng SKU.

## 16. Ghi kết quả theo một mẫu thống nhất

Mỗi thực nghiệm nên có một phiếu ghi nhận ngắn. Ví dụ:

```text
Experiment ID:
DBMS / version:
Storage engine:
Isolation A:
Isolation B:
Autocommit:
Initial fixture/reset time:

Initial state:
  account 1 balance/version:
  account 2 balance/version:
  inventory 101 stock/version:
  customer 7 OPEN order count:
  department 10 active doctor count:

Interleaving:
  A1:
  B1:
  A2:
  B2:
  A commit/rollback:
  B commit/rollback:

Observed behavior:
  blocked session:
  SQL error / SQLSTATE:
  affected rows:
  values read by each session:

Final state:
  exact rows/values:
  invariant satisfied? yes/no

Conclusion:
  expected result:
  actual result:
  explanation:
```

Ghi cả kết quả mong đợi và kết quả thực tế. Nếu khác nhau, trước tiên xác minh reset, isolation level, autocommit và thứ tự bước; không vội kết luận DBMS vi phạm semantics.

## 17. Những lỗi làm thực nghiệm không tái lập được

| Lỗi chuẩn bị | Hậu quả | Cách phòng tránh |
|---|---|---|
| Không reset dữ liệu trước bài | Kết quả phụ thuộc lần chạy trước | Dùng fixture cố định và truy vấn xác nhận S0 |
| Dùng chung connection cho A và B | Không có hai transaction độc lập như dự kiến | Mở hai session/connection riêng |
| Autocommit bật ngoài ý muốn | UPDATE được commit ngay, không giữ khóa qua bước sau | Dùng transaction rõ ràng và kiểm tra cài đặt client |
| Chạy hết Session A rồi mới chạy B | Không tạo được interleaving cần quan sát | Chạy từng bước theo lịch A1/B1/A2/B2 |
| Không ghi isolation level | Khó giải thích dirty read/phantom/write skew | Đặt isolation tường minh ở đầu transaction |
| Dùng thời gian hiện tại hoặc dữ liệu ngẫu nhiên | Kết quả thay đổi giữa các lần chạy | Dùng ID và timestamp cố định |
| Không phân biệt hàng bị block với hàng đã lỗi | Diễn giải sai lock wait thành deadlock | Ghi trạng thái câu lệnh và mã lỗi |
| Không rollback transaction sau lỗi | Session có thể ở trạng thái failed transaction | Rollback trước khi reset hoặc chạy bài mới |
| Dùng một expected result cho mọi DBMS | Bỏ qua khác biệt isolation/engine | Ghi DBMS, phiên bản và semantics thực tế |
| Chỉ kiểm tra trạng thái cuối | Bỏ lỡ giá trị mà session đã đọc trong lúc transaction chưa commit | Ghi kết quả từng SELECT và thời điểm commit |

## 18. Reset và dọn dẹp sau thực nghiệm

Sau mỗi bài:

1. Commit hoặc rollback rõ ràng cả hai session.
2. Nếu một transaction bị deadlock/serialization failure, xác nhận trạng thái transaction và rollback nếu còn cần.
3. Kiểm tra không còn session nào đang giữ transaction trên bảng lab.
4. Chạy truy vấn xác nhận kết quả cuối trước khi reset để lưu bằng chứng.
5. Chạy script reset trong một session quản trị.
6. Chạy lại các SELECT trạng thái ban đầu và xác nhận khớp fixture chuẩn.

Nếu dùng SQL Server, có thể cần `SET XACT_ABORT` hoặc xử lý `XACT_STATE()` trong một số script để dọn transaction sau lỗi. Trong PostgreSQL, sau một lỗi statement trong transaction, transaction thường ở trạng thái aborted cho đến khi `ROLLBACK` hoặc rollback đến savepoint. Trong MySQL, một số lỗi chỉ rollback statement trong khi lỗi khác có thể ảnh hưởng transaction; hãy kiểm tra trạng thái theo đúng loại lỗi.

Không dùng `DROP DATABASE` hoặc xóa dữ liệu ngoài schema lab để reset. Tốt nhất chạy bài trong database riêng hoặc schema riêng dành cho thực nghiệm.

## 19. Kết quả mong đợi tổng hợp

Bảng sau giúp kiểm tra nhanh trạng thái cuối hoặc hiện tượng cần quan sát:

| Thực nghiệm | Trạng thái đầu | Lịch chính | Kết quả mong đợi |
|---|---|---|---|
| Dirty read | Account 1 = 1000 | A ghi 700 chưa commit; B đọc ở RU; A rollback | Chỉ DBMS hỗ trợ RU mới có thể để B thấy 700; cuối cùng DB vẫn 1000 |
| Lost update | Account 1 = 1000 | A/B cùng đọc; A ghi 1100; B ghi 1200 | Cuối 1200, trong khi kết quả cộng cả hai phải là 1300 |
| Atomic increment | Account 1 = 1000 | A cộng 100; B cộng 200 | Cuối 1300 |
| Optimistic version | Balance 1000, version 0 | A update version 0 thành 1; B vẫn dùng version 0 | A affected rows 1; B affected rows 0; cuối 1100/version 1 |
| Non-repeatable read | Account 1 = 1000 | A đọc; B cập nhật 1250 commit; A đọc lại | Ở RC có thể thấy 1000 rồi 1250; RR snapshot thường thấy 1000 cả hai lần |
| Phantom | Customer 7 có 2 OPEN orders | A count; B insert OPEN; A count lại | RC có thể thấy 2 rồi 3; mức cao hơn phụ thuộc DBMS/isolation |
| Write skew | Department 10 có 2 bác sĩ trực | A/B cùng đếm 2; mỗi bên tắt một người khác nhau | Snapshot isolation có thể để cả hai commit và còn 0; serializable phải ngăn trạng thái không tuần tự hóa |
| Lock wait | Account 1 = 1000 | A update và giữ transaction; B update cùng hàng | B chờ; sau A commit, B tiếp tục; cuối 1300 |
| Deadlock | Account 1/2 đều 1000 | A khóa 1 rồi đòi 2; B khóa 2 rồi đòi 1 | DBMS chọn một victim; không được giả định cả hai commit |
| Unique conflict | SKU-NEW chưa tồn tại | A insert chưa commit; B insert cùng SKU | Nếu A commit, B không thể tạo thêm hàng cùng SKU |

Các kết quả có chữ “có thể” cần được ghi kèm DBMS và isolation cụ thể. Chúng mô tả semantics cần kiểm chứng, không phải cam kết mọi sản phẩm phải có cùng lịch block hoặc cùng mã lỗi.

## 20. Cách mở rộng bộ dữ liệu cho bài thực nghiệm mới

Khi cần thêm một bài, hãy bổ sung dữ liệu tối thiểu để làm lộ đúng điều kiện:

- Nếu cần xung đột trên một hàng, chỉ cần một ID chung được hai session cập nhật.
- Nếu cần deadlock, cần ít nhất hai tài nguyên và hai transaction lấy chúng theo thứ tự ngược nhau.
- Nếu cần phantom, cần một predicate có thể nhận thêm hàng mới, cùng một hàng được chèn thỏa điều kiện.
- Nếu cần write skew, cần ít nhất hai hàng cùng tham gia một invariant nhưng mỗi transaction ghi một hàng khác nhau.
- Nếu cần unique conflict, cần một unique key chưa tồn tại và hai lần INSERT cùng giá trị.
- Nếu cần range/gap lock, cần dữ liệu có các giá trị bao quanh khoảng trống để xác định index range đang được bảo vệ.

Tránh thêm nhiều hàng không liên quan vì chúng làm truy vấn và execution plan khó dự đoán. Khi một bài cần chứng minh ảnh hưởng của index, hãy tạo một biến thể fixture riêng có/không có index và ghi rõ kế hoạch thực thi; không thay đổi index giữa chừng mà không reset và ghi lại cấu hình.

Một thiết kế thực nghiệm có thể tái lập luôn bắt đầu từ trạng thái S0 đã biết, chạy hai session theo một lịch cụ thể và kết thúc bằng trạng thái S1 có thể kiểm tra. Khi ghi lại cả giá trị từng session đọc, câu lệnh từng session chạy, số hàng bị ảnh hưởng, kết quả commit/rollback và trạng thái cuối, người học có thể phân biệt hiện tượng thực sự do điều khiển đồng thời với lỗi chuẩn bị dữ liệu hoặc thao tác sai thứ tự.
