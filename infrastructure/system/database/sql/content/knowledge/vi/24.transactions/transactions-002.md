# BEGIN hoặc START TRANSACTION, COMMIT và ROLLBACK

Trong một ứng dụng, một thao tác nghiệp vụ có thể cần **nhiều câu SQL** nhưng chỉ được xem là thành công khi **tất cả thay đổi liên quan đều thành công**. Ví dụ, chuyển 150.000 đồng từ tài khoản A sang tài khoản B bao gồm ít nhất hai thay đổi: trừ tiền ở A và cộng tiền ở B. Nếu câu thứ nhất thành công nhưng câu thứ hai thất bại mà không có cơ chế quản lý giao dịch, tổng tiền của hai tài khoản có thể sai.

**Giao dịch SQL (transaction)** là đơn vị công việc mà database xử lý theo các quy tắc nhất quán. Các lệnh then chốt:

- **`BEGIN` hoặc `START TRANSACTION`**: bắt đầu một phạm vi giao dịch tường minh ở những hệ quản trị hỗ trợ cú pháp đó.
- **`COMMIT`**: yêu cầu xác nhận các thay đổi của giao dịch; sau khi commit thành công, chúng không còn được hoàn tác bằng một `ROLLBACK` thông thường của giao dịch ấy.
- **`ROLLBACK`**: hủy các thay đổi chưa commit thuộc giao dịch, đưa trạng thái dữ liệu thuộc phạm vi quản lý của database về trước giao dịch.

Ví dụ dạng khái niệm:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 150
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 150
WHERE account_id = 2;

COMMIT;
```

Trong hệ thống thật, **chưa thể coi đoạn trên là đủ an toàn**: cần kiểm tra tài khoản tồn tại, số dư đủ, loại tiền phù hợp, cùng tenant, số hàng đã cập nhật, khóa đồng thời và mã giao dịch chống nhập lặp. Bài học sẽ lần lượt bổ sung những yếu tố ấy.

Nội dung thuộc **Database SQL → Giao dịch SQL**, dùng **PostgreSQL** làm hệ thực hành chính. Phần cuối phân biệt cú pháp và hành vi transaction của MySQL, SQL Server, SQLite, Oracle và một số môi trường truy cập từ ứng dụng. Không nên giả định rằng mọi hệ đều dùng `BEGIN` với cùng nghĩa hoặc rằng mọi lệnh DDL đều có thể rollback như nhau.

> **Quy tắc đầu tiên:** một transaction xác định **ranh giới xác nhận hoặc hủy bỏ thay đổi**. Nó không tự chứng minh các phép tính nghiệp vụ đúng, cũng không tự bảo vệ những tác dụng bên ngoài database như email, HTTP API hoặc thanh toán qua hệ khác.

## 1. Vì sao nhiều câu SQL cần chung một giao dịch?

Giả sử hai tài khoản có số dư:

| Tài khoản | Số dư trước chuyển |
| --- | ---: |
| A | 1.000.000 |
| B | 500.000 |
| **Tổng** | **1.500.000** |

Khi chuyển 150.000 từ A sang B, trạng thái mong muốn:

| Tài khoản | Số dư sau chuyển |
| --- | ---: |
| A | 850.000 |
| B | 650.000 |
| **Tổng** | **1.500.000** |

Nếu không có một transaction chung:

```text
UPDATE A -= 150.000   -> đã commit
Mất kết nối hoặc lỗi
UPDATE B += 150.000   -> chưa chạy
```

thì A có 850.000, B vẫn 500.000, tổng chỉ còn 1.350.000. Ngược lại, nếu cộng vào B rồi thất bại trước khi trừ A, tổng có thể tăng sai.

Một transaction giúp định nghĩa **đơn vị xác nhận**:

```text
BEGIN
  Trừ tiền A
  Cộng tiền B
  Ghi nhật ký chuyển tiền
COMMIT nếu mọi điều kiện đều đạt

ROLLBACK nếu có lỗi hoặc điều kiện không đạt
```

Điểm quan trọng: **hai câu UPDATE được đặt giữa BEGIN và COMMIT vẫn có thể cùng thành công nhưng tính toán sai**, ví dụ trừ 150 và cộng 160. Transaction bảo vệ tính nguyên tử, còn ứng dụng/database phải có quy tắc bảo vệ bất biến “tổng không tự tăng/giảm”.

### 1.1. Một transaction có thể gồm cả SELECT

Transaction không chỉ dành cho `INSERT`, `UPDATE`, `DELETE`. Nó có thể gồm:

```sql
BEGIN;

SELECT ...;      -- đọc dữ liệu để quyết định
UPDATE ...;      -- ghi thay đổi
INSERT ...;      -- ghi kết quả liên quan

COMMIT;
```

Các câu đọc và ghi cùng dùng một **kết nối/session** và cùng phạm vi transaction. Việc chúng nhìn thấy thay đổi đồng thời từ session khác phụ thuộc **mức cô lập** (*isolation level*) và cách lấy khóa.

### 1.2. Một transaction không đồng nghĩa một câu SQL

Một câu SQL riêng lẻ có thể được database xử lý dưới dạng transaction ngầm khi autocommit bật. Ngược lại, một transaction tường minh có thể chứa nhiều câu SQL. Người dùng cần phân biệt:

- **Statement**: một câu SQL như một `UPDATE`.
- **Transaction**: một đơn vị commit/rollback, có thể gồm nhiều statement.
- **Session/connection**: ngữ cảnh kết nối mà transaction thuộc về.

Không thể viết `BEGIN` ở kết nối số 1, `UPDATE` ở kết nối số 2 rồi mong COMMIT ở kết nối số 1 xác nhận cập nhật của kết nối số 2.

## 2. Ba lệnh quan trọng nhất

### 2.1. BEGIN: mở giao dịch

PostgreSQL:

```sql
BEGIN;
```

hoặc:

```sql
BEGIN TRANSACTION;
```

hoặc:

```sql
START TRANSACTION;
```

Trong PostgreSQL, ba cách trên đều có thể bắt đầu một giao dịch tường minh ở ngữ cảnh thông thường. `START TRANSACTION` gần với dạng tên đầy đủ theo SQL; `BEGIN` ngắn gọn thường gặp trong script PostgreSQL.

Sau `BEGIN`, các thay đổi được thực hiện trong transaction **chưa trở thành commit** cho tới khi có `COMMIT` thành công. Trong cùng transaction, một câu SELECT sau UPDATE thường thấy thay đổi vừa thực hiện bởi chính transaction đó.

### 2.2. COMMIT: xác nhận giao dịch

```sql
COMMIT;
```

COMMIT kết thúc transaction bằng việc **xác nhận** những thay đổi của transaction nếu mọi điều kiện cần thiết đều cho phép. Khi nó thành công, transaction này kết thúc. Một `ROLLBACK` sau đó không thể quay lại xóa những thay đổi **đã commit** ấy.

Không nên nói “COMMIT ghi toàn bộ dữ liệu từ RAM xuống ổ đĩa theo cùng một cách ở mọi hệ”: độ bền và cơ chế ghi log, replication, synchronous commit và cấu hình hạ tầng có khác biệt. Điều ứng dụng cần dựa vào là **hợp đồng durability của DBMS và cấu hình đang chạy**, không phải một mô tả triển khai duy nhất.

### 2.3. ROLLBACK: hủy giao dịch chưa commit

```sql
ROLLBACK;
```

ROLLBACK kết thúc transaction hiện tại và hủy các thay đổi **chưa commit** thuộc phạm vi transaction ấy, theo ngữ nghĩa database. Nó không hủy những transaction khác đã commit.

Ví dụ:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 150 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 150 WHERE account_id = 2;

-- Người vận hành phát hiện chọn sai tài khoản.
ROLLBACK;
```

Hai UPDATE chưa commit được hủy. Đây không phải thao tác “khôi phục database về hôm qua”; nó chỉ hủy **transaction đang mở**.

### 2.4. Bảng ý nghĩa nhanh

| Lệnh | Điều nó làm | Điều không được suy luận |
| --- | --- | --- |
| `BEGIN` / `START TRANSACTION` | Bắt đầu phạm vi transaction tường minh | Mọi thao tác sau đó chắc chắn đúng nghiệp vụ |
| `COMMIT` | Xác nhận và kết thúc transaction | Có thể ROLLBACK các thay đổi đã commit |
| `ROLLBACK` | Hủy và kết thúc transaction chưa commit | Hoàn tác email/API/sequence/những commit khác |
| `SAVEPOINT` | Đánh dấu một vị trí để có thể rollback một phần | Mở transaction độc lập |
| `ROLLBACK TO SAVEPOINT` | Quay về savepoint nhưng giữ transaction đang mở | Hủy toàn bộ transaction như ROLLBACK không kèm TO |

## 3. Autocommit và transaction tường minh

Nhiều công cụ hoặc driver vận hành ở **autocommit** theo mặc định: mỗi câu SQL thay đổi dữ liệu, nếu không nằm trong transaction tường minh, được xử lý như một transaction riêng và tự commit khi hoàn thành thành công.

Ví dụ minh họa:

```sql
UPDATE accounts SET balance = balance - 150 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 150 WHERE account_id = 2;
```

Nếu hai câu được gửi như **hai statement tự commit riêng**:

```text
Statement 1 -> transaction riêng -> COMMIT
Statement 2 -> transaction riêng -> COMMIT hoặc lỗi
```

Không còn khả năng rollback **cả hai như một đơn vị** sau khi statement 1 đã commit.

Với transaction tường minh:

```sql
BEGIN;
UPDATE ...;
UPDATE ...;
COMMIT;
```

hai statement thuộc cùng một transaction trên cùng connection.

### 3.1. Autocommit không phải một cú pháp SQL phổ quát

Phân biệt:

- PostgreSQL `psql`: thông thường mỗi câu chạy ngoài `BEGIN` được commit riêng; chế độ AUTOCOMMIT của **psql** có tùy chọn riêng.
- JDBC: `Connection` thông thường có `autoCommit` bật khi mới tạo; gọi `setAutoCommit(false)` để quản lý transaction qua API.
- MySQL: có biến session `autocommit` và `START TRANSACTION`.
- SQL Server: mặc định thường là implicit autocommit cho statement; có chế độ `IMPLICIT_TRANSACTIONS`.
- SQLite: `sqlite3` CLI/driver và DB engine có cơ chế tự bắt đầu/kết thúc transaction tùy API.

**Không suy luận chế độ giao dịch chỉ từ việc ứng dụng có hay không có dòng SQL BEGIN.** Framework có thể đã bắt đầu transaction qua driver. Ngược lại, một shell có thể đang dùng autocommit dù trong code không có COMMIT.

### 3.2. Chạy nhiều câu trong một request chưa chắc cùng transaction

Một request HTTP có thể gọi:

```text
DAO.updateSource()  -> connection A, tự commit
DAO.updateTarget()  -> connection B, tự commit
```

Nếu không có cơ chế truyền cùng connection/transaction, hai phương thức **không chung giao dịch**. Cần hiểu cách framework quản lý connection và ranh giới transaction ở application layer.

## 4. Dữ liệu PostgreSQL để thực hành

Chạy trong một phiên PostgreSQL để tạo hai bảng tạm: tài khoản và nhật ký chuyển tiền. Bảng tạm tồn tại trong **phiên hiện tại**, nên các truy vấn thực hành cần chạy trên cùng session.

```sql
CREATE TEMP TABLE demo_tx_accounts (
    tenant_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0),
    PRIMARY KEY (tenant_id, account_id)
);

CREATE TEMP TABLE demo_tx_transfers (
    transfer_ref TEXT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    from_account_id INTEGER NOT NULL,
    to_account_id INTEGER NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account_id <> to_account_id),
    FOREIGN KEY (tenant_id, from_account_id)
        REFERENCES demo_tx_accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, to_account_id)
        REFERENCES demo_tx_accounts (tenant_id, account_id)
);

INSERT INTO demo_tx_accounts (
    tenant_id, account_id, owner_name, balance
)
VALUES
    (10, 101, 'Lan',  1000.00),
    (10, 102, 'Minh',  500.00),
    (10, 103, 'Huy',   200.00),
    (20, 101, 'Lan thuộc tenant khác', 900.00);
```

Kiểm tra trạng thái ban đầu:

```sql
SELECT tenant_id, account_id, owner_name, balance
FROM demo_tx_accounts
ORDER BY tenant_id, account_id;
```

| tenant_id | account_id | owner_name | balance |
| ---: | ---: | --- | ---: |
| 10 | 101 | Lan | 1000.00 |
| 10 | 102 | Minh | 500.00 |
| 10 | 103 | Huy | 200.00 |
| 20 | 101 | Lan thuộc tenant khác | 900.00 |

Tổng số dư ban đầu của **tenant 10** là **1700.00**:

```sql
SELECT SUM(balance) AS tenant_balance_total
FROM demo_tx_accounts
WHERE tenant_id = 10;
-- 1700.00
```

### 4.1. Vì sao khóa chính gồm tenant_id và account_id?

Tenant 10 và tenant 20 đều có account_id 101 nhưng là hai tài khoản khác nhau. Nếu thao tác:

```sql
UPDATE demo_tx_accounts
SET balance = balance - 100
WHERE account_id = 101;
```

thì **cả hai tenant** có thể bị ảnh hưởng, và transaction vẫn có thể COMMIT thành công nếu không vi phạm constraint. Đây là lỗi nghiệp vụ/phân quyền, không phải lỗi SQL transaction.

Trong các ví dụ, dùng:

```sql
WHERE tenant_id = 10 AND account_id = 101
```

và kiểm tra **số hàng tác động** để bảo đảm chọn đúng tài khoản.

### 4.2. Đọc kết quả mà không thay đổi dữ liệu

Các ví dụ thử `BEGIN ... ROLLBACK` sẽ giữ bộ dữ liệu gốc. Một ví dụ `COMMIT` được ghi rõ là **thực sự làm thay đổi dữ liệu**: nếu chạy, các kết quả ở những mục sau có thể khác so với mốc ban đầu. Có thể tạo lại bảng tạm trong phiên mới hoặc đặt các thao tác thử trong transaction kết thúc bằng ROLLBACK.

## 5. Thực hành BEGIN → UPDATE → ROLLBACK

Đây là ví dụ an toàn để quan sát thay đổi **bên trong transaction** nhưng **không giữ lại**:

```sql
BEGIN;

UPDATE demo_tx_accounts
SET balance = balance - 100
WHERE tenant_id = 10
  AND account_id = 101;

UPDATE demo_tx_accounts
SET balance = balance + 100
WHERE tenant_id = 10
  AND account_id = 102;

SELECT account_id, balance
FROM demo_tx_accounts
WHERE tenant_id = 10
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM demo_tx_accounts
WHERE tenant_id = 10
ORDER BY account_id;
```

Trước ROLLBACK, **cùng transaction** thấy:

| account_id | balance trong transaction |
| ---: | ---: |
| 101 | 900.00 |
| 102 | 600.00 |
| 103 | 200.00 |

Sau ROLLBACK:

| account_id | balance sau rollback |
| ---: | ---: |
| 101 | 1000.00 |
| 102 | 500.00 |
| 103 | 200.00 |

Các UPDATE đã được thực thi nhưng **không được commit**. ROLLBACK đưa dữ liệu thuộc transaction về trạng thái trước khi bắt đầu transaction ấy.

### 5.1. Vì sao SELECT ở trong transaction thấy giá trị chưa commit?

Một transaction thông thường có thể **đọc chính thay đổi của nó** (*read your own writes*). Điều này không có nghĩa mọi transaction khác cũng nhìn thấy thay đổi chưa commit. Ở PostgreSQL, các transaction khác không đọc được các giá trị chưa commit của transaction này theo các mức isolation thông dụng của PostgreSQL.

### 5.2. ROLLBACK không xóa “dấu vết” mọi hoạt động

Rollback hủy thay đổi transaction đối với dữ liệu thuộc phạm vi giao dịch, nhưng:

- Một giá trị **sequence** đã lấy qua `nextval()` ở PostgreSQL có thể vẫn tăng sau rollback.
- Log hệ thống có thể ghi nhận câu lệnh hoặc lỗi đã xảy ra.
- Lock đã được giữ trong transaction được giải phóng khi transaction kết thúc.
- Email/HTTP request đã gửi ra ngoài không tự được thu hồi.

**Không dùng tính liên tục của số ID để suy đoán rằng transaction đã commit.** Khoảng trống trong sequence/auto-increment là điều có thể xảy ra hợp lệ.

## 6. Thực hành BEGIN → UPDATE → COMMIT

Ví dụ đơn giản (chỉ chạy một lần nếu muốn giữ mốc kết quả):

```sql
BEGIN;

UPDATE demo_tx_accounts
SET balance = balance - 150
WHERE tenant_id = 10
  AND account_id = 101
  AND balance >= 150
RETURNING account_id, balance;

UPDATE demo_tx_accounts
SET balance = balance + 150
WHERE tenant_id = 10
  AND account_id = 102
RETURNING account_id, balance;

INSERT INTO demo_tx_transfers (
    transfer_ref, tenant_id,
    from_account_id, to_account_id, amount
)
VALUES ('demo-transfer-001', 10, 101, 102, 150.00);

COMMIT;
```

Nếu mọi điều kiện đều thỏa và chạy đúng một lần từ dữ liệu ban đầu:

| account_id | balance sau commit |
| ---: | ---: |
| 101 | 850.00 |
| 102 | 650.00 |
| 103 | 200.00 |

Bảng `demo_tx_transfers` có một hàng ghi nhận 150.00. Tổng số dư tenant 10 vẫn là **1700.00**.

**Cảnh báo quan trọng:** đây là ví dụ về **ranh giới COMMIT**, không phải hàm chuyển tiền production hoàn chỉnh. Nếu UPDATE đầu **tác động 0 hàng** vì thiếu tiền hoặc không tồn tại account, các statement sau trong script có thể vẫn chạy và COMMIT, khiến tiền được cộng vào người nhận mà không bị trừ ở người gửi. Trong application, **phải kiểm tra số hàng debit/credit và chỉ COMMIT khi mọi điều kiện thành công**; phần tiếp theo cho mẫu kiểm soát.

Nếu chạy lại toàn đoạn sau khi đã commit, `transfer_ref` trùng có thể gây lỗi unique và transaction bị rollback trong PostgreSQL, nhưng điều này **không thay thế thiết kế idempotency** và xử lý kết quả COMMIT chưa rõ của client.

## 7. Cần kiểm tra số hàng cập nhật trước COMMIT

Trường hợp tài khoản người gửi không tồn tại:

```sql
UPDATE demo_tx_accounts
SET balance = balance - 150
WHERE tenant_id = 10
  AND account_id = 999
  AND balance >= 150;
```

Câu SQL **không có lỗi cú pháp**. Nó cập nhật **0 hàng**. Nếu chương trình vẫn cộng tiền vào account 102 và COMMIT, cơ sở dữ liệu có thể giữ một trạng thái sai nghiệp vụ.

Ngay cả với `CHECK(balance >= 0)`, điều kiện `balance >= 150` có thể khiến UPDATE của người gửi chỉ cập nhật 0 hàng chứ không tự báo lỗi. Transaction không thể tự biết chương trình yêu cầu **chính xác một debit và một credit**.

### 7.1. Một mẫu PostgreSQL có kiểm tra lỗi tường minh

Để thực hành một giao dịch chuyển tiền có các kiểm tra quan trọng, dùng một khối PL/pgSQL bên trong transaction. Ví dụ dưới đây **được rollback ở cuối** để không làm thay đổi bộ dữ liệu:

```sql
BEGIN;

DO $$
DECLARE
    v_rows INTEGER;
BEGIN
    UPDATE demo_tx_accounts
    SET balance = balance - 150
    WHERE tenant_id = 10
      AND account_id = 101
      AND balance >= 150;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'Debit failed: expected 1 row, got %', v_rows;
    END IF;

    UPDATE demo_tx_accounts
    SET balance = balance + 150
    WHERE tenant_id = 10
      AND account_id = 102;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'Credit failed: expected 1 row, got %', v_rows;
    END IF;

    INSERT INTO demo_tx_transfers (
        transfer_ref, tenant_id,
        from_account_id, to_account_id, amount
    )
    VALUES ('demo-transfer-sandbox', 10, 101, 102, 150.00);
END
$$;

-- Có thể SELECT trạng thái trong transaction để quan sát.
SELECT account_id, balance
FROM demo_tx_accounts
WHERE tenant_id = 10
ORDER BY account_id;

ROLLBACK;
```

`GET DIAGNOSTICS ... ROW_COUNT` là cú pháp PL/pgSQL của PostgreSQL để lấy số hàng mà câu lệnh vừa ảnh hưởng. Nếu số hàng không đúng, `RAISE EXCEPTION` báo lỗi, và transaction ngoài cần được **ROLLBACK**. Với ứng dụng thật, driver thường cung cấp row count và quản lý rollback khi gặp exception.

**Lưu ý khi chạy ví dụ:** nếu câu DO báo lỗi, transaction PostgreSQL có thể chuyển sang trạng thái lỗi (*aborted*). Khi đó không thể tiếp tục SELECT như bình thường: hãy `ROLLBACK` transaction rồi sửa nguyên nhân. Mẫu này chưa bao quát xác thực người dùng, khóa chống replay và tất cả vấn đề ledger/tài chính thực.

### 7.2. Vì sao đặt `balance >= 150` ngay trong UPDATE?

Một cách thiếu an toàn dưới concurrency:

```text
SELECT balance;  -- thấy 100
Ứng dụng nghĩ đủ để trừ 80
Trong khi đó, request khác cũng đọc balance = 100
Cả hai cùng trừ ...
```

Điều kiện nguyên tử:

```sql
UPDATE demo_tx_accounts
SET balance = balance - 80
WHERE tenant_id = 10
  AND account_id = 101
  AND balance >= 80;
```

cho phép database kiểm tra điều kiện tại thao tác UPDATE và lấy khóa phù hợp, giảm nguy cơ đọc số dư cũ rồi trừ quá mức. **Vẫn phải kiểm tra row count** và hiểu mức isolation/transaction của hệ quản trị; một điều kiện atomic không thay thế mọi kiểm soát khi nghiệp vụ trải qua nhiều hàng/tables.

### 7.3. Kiểm tra bất biến tổng tiền

Một phép kiểm tra số học đơn giản trong ví dụ:

```sql
SELECT SUM(balance) AS tenant_total
FROM demo_tx_accounts
WHERE tenant_id = 10;
```

Tổng trước và sau chuyển nội bộ phải bằng **1700.00** trong mô hình không có phí, lãi hay các khoản khác. Tuy nhiên, chỉ tổng không đổi chưa chứng minh đúng tài khoản nhận, đúng số tiền, đúng tenant hoặc đúng bản ghi transfer. Cần kiểm tra **cả tính nguyên tử và ngữ nghĩa nghiệp vụ**.

## 8. ACID: bốn đặc tính thường dùng để nói về transaction

Giao dịch của database quan hệ thường được mô tả bằng **ACID**:

| Thuộc tính | Ý nghĩa | Liên hệ ví dụ |
| --- | --- | --- |
| **Atomicity** (nguyên tử) | Các thay đổi thuộc transaction được commit như một đơn vị, hoặc bị rollback | Trừ A, cộng B và ghi transfer phải cùng thành công |
| **Consistency** (nhất quán) | Transaction hợp lệ phải đưa database từ trạng thái thỏa bất biến sang trạng thái thỏa bất biến | Số dư không âm, FK đúng, tổng chuyển nội bộ bảo toàn |
| **Isolation** (cô lập) | Các transaction đồng thời tương tác theo mức cô lập được cấu hình | Hai yêu cầu không được trừ sai do đọc số dư cũ |
| **Durability** (bền vững) | Sau commit thành công, thay đổi được duy trì theo bảo đảm của DBMS và cấu hình | Dữ liệu đã xác nhận không mất chỉ vì session người dùng kết thúc |

### 8.1. ACID không có nghĩa mọi lỗi nghiệp vụ đều bị phát hiện

Nếu chương trình trừ 150 ở A nhưng cộng **170** ở B, transaction vẫn có thể commit nếu schema và kiểm tra của database không ngăn. **Consistency** phụ thuộc những bất biến được khai báo hoặc kiểm tra đúng. DBMS bảo đảm các constraint nó biết, không tự biết toàn bộ quy tắc kinh doanh.

### 8.2. Atomicity không bao gồm mọi hệ thống bên ngoài

Một transaction PostgreSQL không tự rollback:

- Email đã gửi qua SMTP.
- Tiền đã chuyển qua một nhà cung cấp thanh toán ngoài DB.
- File đã được ghi vào object storage.
- HTTP request đã gọi một dịch vụ khác và được dịch vụ ấy commit.

Nếu nghiệp vụ liên quan nhiều hệ thống, cần thiết kế **outbox, idempotency, saga hoặc cơ chế phối hợp** thích hợp. Chỉ viết BEGIN/COMMIT quanh SQL không tạo một transaction nguyên tử xuyên nhiều dịch vụ.

### 8.3. Durability có điều kiện cấu hình

Database có write-ahead log, replication, cơ chế đồng bộ đĩa và các mức bảo đảm khác nhau. Ví dụ, một cấu hình chấp nhận xác nhận commit trước khi một số bản sao đã ghi có thể có hồ sơ rủi ro khác cấu hình chờ đồng bộ. Khi hệ thống đòi hỏi độ bền đặc biệt, phải xét **cấu hình durability và kiến trúc sao lưu/phục hồi thực tế**, không chỉ từ khóa COMMIT.

## 9. Transaction nhìn thấy dữ liệu như thế nào?

Giả sử có hai session PostgreSQL độc lập:

```text
SESSION A                             SESSION B
---------                             ---------
BEGIN;
UPDATE accounts SET balance=900
WHERE account_id=101;

SELECT balance; -- A thấy 900       SELECT balance; -- B thường vẫn
                                    -- thấy giá trị đã commit trước

COMMIT;

                                    SELECT balance; -- B có thể thấy 900
```

Đây là minh họa lý thuyết, không phải câu SQL đầy đủ với tenant và bảng demo. Từ **“có thể”** quan trọng: sau COMMIT, việc session B thấy giá trị mới tại lần SELECT tiếp theo phụ thuộc mức isolation, snapshot và cách thực thi.

### 9.1. Dirty read

*Dirty read* là khi transaction B đọc giá trị transaction A **chưa commit**. Nếu A rollback, B đã đọc dữ liệu không bao giờ trở thành trạng thái đã xác nhận.

PostgreSQL không cho dirty read trong các mức cô lập thông dụng của nó; tên mức `READ UNCOMMITTED` được xử lý như `READ COMMITTED` trong PostgreSQL. Một số DBMS khác cho phép read uncommitted với hành vi/giới hạn riêng.

### 9.2. Non-repeatable read

Session A đọc một hàng, session B cập nhật và commit, session A đọc lại **cùng hàng** nhưng nhận giá trị khác trong cùng transaction của A. Đây là non-repeatable read.

Trong PostgreSQL `READ COMMITTED`, mỗi statement thường có snapshot riêng, nên hiện tượng này có thể xảy ra.

### 9.3. Phantom read

Session A chạy một truy vấn điều kiện, ví dụ:

```sql
SELECT COUNT(*) FROM bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-10-15';
```

Session B chèn một booking phù hợp rồi commit. Nếu A chạy lại câu COUNT và thấy thêm một hàng, đó là một dạng **phantom** trong những mức cô lập cho phép.

Không nhầm phantom với lỗi SQL parser hoặc việc đọc một hàng thay đổi. Phantom nói về **tập hàng thỏa predicate** thay đổi giữa các lần đọc.

### 9.4. Lost update và write skew

- **Lost update**: kết quả ghi của một transaction bị ghi đè vì hai phía cập nhật dựa trên cùng giá trị cũ mà không bảo vệ thích hợp.
- **Write skew**: hai transaction đọc một tập điều kiện chung rồi sửa các hàng khác nhau, mỗi transaction tự thấy hợp lệ nhưng trạng thái kết hợp sau cả hai có thể vi phạm một bất biến.

Một transaction bao quanh nhiều câu SQL **không mặc nhiên loại bỏ mọi anomaly**. Mức isolation, khóa, điều kiện UPDATE, constraint và việc retry là những thành phần quan trọng.

## 10. Các mức cô lập giao dịch

Những tên thường gặp theo SQL:

| Isolation level | Tinh thần chính | Điều cần lưu ý |
| --- | --- | --- |
| `READ UNCOMMITTED` | Có thể cho phép nhìn dữ liệu chưa commit ở một số DBMS | PostgreSQL xử lý như READ COMMITTED |
| `READ COMMITTED` | Không đọc thay đổi chưa commit; một statement đọc snapshot phù hợp | Hai statement trong cùng transaction có thể thấy các commit khác nhau |
| `REPEATABLE READ` | Bảo vệ tính lặp lại của các lần đọc theo cơ chế engine | Ngữ nghĩa chống phantom và xử lý conflict khác giữa DBMS |
| `SERIALIZABLE` | Kết quả tương đương một lịch thực thi tuần tự nào đó khi giao dịch thành công | Có thể abort transaction do serialization failure, ứng dụng phải retry |

Không nên khẳng định tên mức cô lập giống nhau thì các chi tiết thực thi **hoàn toàn giống nhau** ở PostgreSQL, MySQL/InnoDB, SQL Server, Oracle và SQLite. Các engine dùng MVCC, lock, snapshot hoặc kết hợp theo cách khác.

### 10.1. PostgreSQL đặt isolation khi bắt đầu

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) FROM demo_tx_accounts;

COMMIT;
```

Hoặc:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT SUM(balance)
FROM demo_tx_accounts
WHERE tenant_id = 10;

COMMIT;
```

`SET TRANSACTION ...` nên được thực hiện **trước các query liên quan** trong transaction theo giới hạn của PostgreSQL. Không đổi isolation giữa chừng rồi mong nó sửa lại những thao tác đã thực thi.

### 10.2. Serializable không có nghĩa không cần retry

Trong PostgreSQL, mức SERIALIZABLE dùng cơ chế phát hiện xung đột có thể kết thúc một transaction bằng lỗi **serialization failure**. Đây là một phần của bảo đảm cô lập: database chọn hủy một giao dịch để ngăn lịch thực thi không tương đương với tuần tự.

Ứng dụng cần **rollback và thử lại toàn bộ logic nghiệp vụ** (với điều kiện thao tác có thể retry an toàn), thường có giới hạn số lần và backoff. Thử lại chỉ câu UPDATE cuối mà không lặp lại các kiểm tra trước đó có thể không đúng.

### 10.3. Isolation không thay thế quyền truy cập

Một transaction serializable vẫn có thể UPDATE sai tenant nếu WHERE chỉ có account_id. Isolation giải quyết tương tác đồng thời, **không thay thế authorization, tenant scoping hoặc business validation**.

## 11. Khóa hàng với SELECT ... FOR UPDATE trong PostgreSQL

Khi cần đọc trạng thái để quyết định một thay đổi, đôi khi phải **khóa hàng** trước khi thao tác.

```sql
BEGIN;

SELECT account_id, balance
FROM demo_tx_accounts
WHERE tenant_id = 10
  AND account_id IN (101, 102)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng kiểm tra đúng 2 tài khoản,
-- số dư đủ, quyền và trạng thái hợp lệ.

UPDATE demo_tx_accounts
SET balance = balance - 50
WHERE tenant_id = 10
  AND account_id = 101
  AND balance >= 50;

UPDATE demo_tx_accounts
SET balance = balance + 50
WHERE tenant_id = 10
  AND account_id = 102;

ROLLBACK;
```

`FOR UPDATE` yêu cầu khóa hàng được chọn trong phạm vi transaction. Những transaction khác muốn cập nhật các hàng xung đột có thể phải **chờ** hoặc nhận lỗi tùy hành vi NOWAIT/timeout/isolation. `ROLLBACK` cuối ví dụ giải phóng khóa và hoàn tác các UPDATE.

### 11.1. Khóa không nên giữ lâu

Không bắt đầu transaction, khóa tài khoản rồi chờ người dùng xác nhận trên giao diện trong vài phút. Việc giữ transaction mở có thể:

- Chặn request khác cần sửa cùng hàng.
- Tăng nguy cơ deadlock hoặc timeout.
- Giữ snapshot/version cũ lâu hơn cần thiết.
- Gây áp lực tài nguyên và làm chậm hệ thống.

Thông thường nên lấy dữ liệu để hiển thị **trước**, còn transaction ghi thực sự bắt đầu **ngay khi đã có quyết định**, kiểm tra lại điều kiện và commit/rollback nhanh.

### 11.2. Một lock không thay thế mọi kiểm tra

`FOR UPDATE` khóa những hàng **thực sự được chọn**. Nếu row không tồn tại, không có hàng ấy để khóa. Với các bất biến trên **tập hàng chưa tồn tại** hoặc predicate phức tạp, có thể cần unique/exclusion constraint, mức SERIALIZABLE, khóa khác hoặc mô hình nghiệp vụ tương ứng.

### 11.3. Hướng khóa nhất quán giảm rủi ro deadlock

Trong chuyển tiền qua hai tài khoản, transaction A có thể khóa 101 trước rồi muốn 102; transaction B lại khóa 102 trước rồi muốn 101. Hai phía có thể chờ nhau thành **deadlock**.

Một chiến lược là lấy khóa nhiều tài khoản theo **thứ tự khóa định danh nhất quán** trong mọi luồng. `ORDER BY account_id FOR UPDATE` là một cách diễn đạt thứ tự trong PostgreSQL, nhưng việc thiết kế khóa chắc chắn cần xem execution plan, mức isolation và các luồng cập nhật khác; không coi chỉ một ORDER BY là bảo đảm tuyệt đối hệ thống không deadlock.

## 12. SAVEPOINT: quay lại một phần nhưng vẫn giữ transaction

**`SAVEPOINT`** đánh dấu một vị trí trong transaction để có thể hủy **một phần** thay đổi sau đó mà không nhất thiết hủy mọi bước trước.

Ví dụ PostgreSQL:

```sql
BEGIN;

UPDATE demo_tx_accounts
SET balance = balance - 10
WHERE tenant_id = 10
  AND account_id = 101;

SAVEPOINT after_debit;

UPDATE demo_tx_accounts
SET balance = balance + 20
WHERE tenant_id = 10
  AND account_id = 102;

-- Phát hiện cộng nhầm 20 thay vì 10:
ROLLBACK TO SAVEPOINT after_debit;

UPDATE demo_tx_accounts
SET balance = balance + 10
WHERE tenant_id = 10
  AND account_id = 102;

RELEASE SAVEPOINT after_debit;

-- Đây là ví dụ học tập, không giữ thay đổi:
ROLLBACK;
```

Diễn biến:

1. UPDATE đầu trừ 10 ở tài khoản 101.
2. Đặt savepoint.
3. UPDATE tiếp cộng nhầm 20 ở 102.
4. `ROLLBACK TO` hủy phần cộng nhầm **sau savepoint**, nhưng vẫn giữ thay đổi trừ 10 trước savepoint trong transaction.
5. UPDATE lại cộng đúng 10.
6. `RELEASE SAVEPOINT` bỏ điểm khôi phục trung gian.
7. `ROLLBACK` cuối hủy **toàn bộ transaction**, gồm cả phần trừ 10 và cộng 10.

### 12.1. ROLLBACK và ROLLBACK TO khác nhau

| Câu lệnh | Transaction kết thúc? | Phạm vi bị hoàn tác |
| --- | --- | --- |
| `ROLLBACK;` | Có | Toàn bộ thay đổi chưa commit của transaction |
| `ROLLBACK TO SAVEPOINT name;` | Không | Những thay đổi sau savepoint được chỉ định |
| `RELEASE SAVEPOINT name;` | Không | Không rollback; giải phóng điểm đánh dấu |

`SAVEPOINT` **không tạo transaction độc lập** và `RELEASE SAVEPOINT` **không có nghĩa COMMIT một phần**. Nếu sau RELEASE mà transaction ngoài ROLLBACK, các thay đổi trước đó vẫn bị hủy.

### 12.2. Dùng savepoint khi một statement có thể thất bại

Một mẫu ở PostgreSQL:

```sql
BEGIN;

SAVEPOINT before_risky_step;

-- Giả sử statement tiếp theo có thể vi phạm UNIQUE/ CHECK.
-- Nếu nó lỗi, transaction đang ở trạng thái lỗi:
-- ROLLBACK TO SAVEPOINT before_risky_step;

-- Sau khi xử lý, có thể tiếp tục các statement hợp lệ.
ROLLBACK;
```

Điều quan trọng là **lệnh ROLLBACK TO SAVEPOINT phải thực sự được ứng dụng gửi khi câu lỗi**, thay vì coi comment SQL là một bộ xử lý ngoại lệ. Các framework thường cung cấp savepoint API hoặc nested transaction giả lập bằng savepoint, nhưng cách dùng phụ thuộc driver.

### 12.3. SAVEPOINT không hỗ trợ giống nhau ở mọi DBMS

PostgreSQL/MySQL/SQLite có cú pháp savepoint tương tự. SQL Server dùng `SAVE TRANSACTION` và `ROLLBACK TRANSACTION savepoint_name`, với quy tắc nested transaction và trạng thái lỗi riêng. Không được copy trực tiếp mọi lệnh của PostgreSQL sang T-SQL.

## 13. PostgreSQL: xử lý lỗi khiến transaction bị aborted

Giả sử một transaction thực thi statement vi phạm `CHECK(balance >= 0)`:

```sql
BEGIN;

UPDATE demo_tx_accounts
SET balance = -1
WHERE tenant_id = 10
  AND account_id = 101;

-- PostgreSQL báo lỗi CHECK constraint.
```

Sau lỗi, PostgreSQL thường đánh dấu transaction là **aborted**. Các statement thông thường tiếp theo sẽ bị từ chối với thông báo kiểu “current transaction is aborted...” cho tới khi rollback transaction hoặc rollback về một savepoint phù hợp.

### 13.1. Cách xử lý đúng khi không có savepoint

```sql
ROLLBACK;
```

Sau đó mở transaction mới nếu cần. Không tiếp tục COMMIT những thay đổi một cách mù quáng; trong PostgreSQL, COMMIT trên transaction đã thất bại có thể dẫn tới rollback thay vì xác nhận theo mong muốn của ứng dụng.

### 13.2. Cách cô lập đoạn có nguy cơ lỗi

Một quy trình theo lời:

```text
BEGIN
  cập nhật an toàn
  SAVEPOINT s1
  thử statement có thể gây lỗi
     nếu lỗi -> ROLLBACK TO SAVEPOINT s1
     nếu thành công -> RELEASE SAVEPOINT s1
  tiếp tục hợp lệ
COMMIT
```

Không nên dùng savepoint để **nuốt** mọi lỗi. Nếu lỗi cho biết bất biến nghiệp vụ bị vi phạm (thiếu tiền, sai tenant, giao dịch trùng), thường phải **hủy toàn giao dịch nghiệp vụ** chứ không chỉ bỏ qua statement lỗi rồi COMMIT các phần còn lại.

## 14. COMMIT thành công rồi có ROLLBACK lại được không?

Không. Xem:

```sql
BEGIN;
UPDATE demo_tx_accounts
SET balance = balance + 10
WHERE tenant_id = 10
  AND account_id = 103;
COMMIT;
```

Sau khi COMMIT thành công, thay đổi **đã được xác nhận**. Một câu:

```sql
ROLLBACK;
```

ngoài transaction đang hoạt động không thể hủy lần COMMIT vừa rồi.

Muốn “hoàn tác nghiệp vụ” sau commit, cần **một giao dịch mới** thực hiện thay đổi bù (*compensating transaction*) theo quy tắc đã thiết kế, ví dụ ghi một bút toán điều chỉnh có audit. Không phải lúc nào cũng hợp lệ để viết `UPDATE balance = balance - 10` vì sau đó có thể đã xảy ra giao dịch khác, giới hạn số dư hoặc yêu cầu kế toán.

### 14.1. Undo kỹ thuật khác undo nghiệp vụ

```text
Trước COMMIT:  ROLLBACK -> DB hủy thay đổi chưa commit.
Sau COMMIT:    Giao dịch mới -> ghi bù/điều chỉnh nếu nghiệp vụ cho phép.
```

Việc khôi phục từ backup hoặc point-in-time recovery là một **quy trình quản trị dữ liệu khác**, có thể ảnh hưởng nhiều giao dịch, không phải cách thông thường để undo một câu lệnh đã commit trong ứng dụng.

### 14.2. Transaction không đảo được thứ đã phát ra bên ngoài

Nếu ứng dụng gửi email “đã chuyển tiền” **trước COMMIT**, rồi transaction rollback, email vẫn đã tới người dùng. Đó là lý do những side effect quan trọng thường nên gắn với **trạng thái đã commit**, theo pattern outbox/queue đáng tin, chứ không gọi ngay giữa transaction mà mong ROLLBACK xử lý giúp.

## 15. Deadlock và timeout: hai kết quả cần xử lý

Hai transaction đồng thời có thể khóa tài nguyên theo thứ tự ngược nhau:

```text
Session A: khóa tài khoản 101
Session B: khóa tài khoản 102
Session A: chờ khóa tài khoản 102
Session B: chờ khóa tài khoản 101
           -> vòng chờ DEADLOCK
```

DBMS thường có cơ chế phát hiện deadlock và chọn một transaction làm **nạn nhân** để hủy, giúp transaction còn lại có thể tiếp tục. Ứng dụng phải xử lý lỗi và quyết định retry an toàn.

### 15.1. Deadlock khác chờ khóa thông thường

- **Lock wait:** một transaction chờ transaction khác nhả khóa; nếu bên giữ khóa commit nhanh, bên chờ có thể tiếp tục.
- **Deadlock:** các transaction chờ nhau tạo vòng không thể tự giải quyết chỉ bằng chờ; DBMS có thể hủy một bên.
- **Lock timeout:** quá thời hạn chờ đã cấu hình; statement/transaction có thể bị hủy tùy DBMS.
- **Statement timeout:** câu SQL chạy quá thời hạn được cấu hình, không nhất thiết liên quan deadlock.

Không gom tất cả thành “SQL chậm”. Cần log mã lỗi, thời gian chờ, truy vấn và transaction liên quan để tìm nguyên nhân.

### 15.2. Cách giảm nguy cơ

- Giữ transaction **ngắn** và không chờ UI/API bên ngoài khi đang giữ lock.
- Truy cập các thực thể theo **thứ tự ổn định** giữa các luồng nghiệp vụ.
- Dùng index phù hợp để giảm số hàng bị quét/khóa không cần thiết.
- Hạn chế khóa trên phạm vi quá rộng.
- Đảm bảo thao tác retry **không ghi trùng**.
- Giám sát số transaction “idle in transaction” và lock wait.

Không thể hứa loại bỏ tuyệt đối deadlock trong hệ thống có concurrency. Mục tiêu là **giảm xác suất và xử lý lỗi đúng**.

## 16. Retry một transaction an toàn

Trong PostgreSQL, hai mã lỗi cần biết:

- **`40001`**: serialization failure.
- **`40P01`**: deadlock detected.

Các lỗi này thường là ứng viên retry **toàn bộ transaction**, nếu thao tác nghiệp vụ có khả năng chạy lại an toàn. Không retry vô hạn; dùng số lần giới hạn và backoff/jitter tùy nhu cầu.

Mẫu ứng dụng khái niệm:

```text
for attempt in 1..max_attempts:
    begin transaction
    try:
        kiểm tra quyền + dữ liệu hiện tại
        thay đổi các bảng liên quan
        ghi mã giao dịch duy nhất
        commit
        return success
    catch serialization_failure or deadlock:
        rollback nếu còn transaction
        backoff
        retry toàn bộ nghiệp vụ
    catch lỗi khác:
        rollback nếu còn transaction
        return error
```

### 16.1. Không retry mọi lỗi

Một lỗi thiếu tiền, FK sai, tenant không có quyền hoặc unique conflict có thể yêu cầu **thông báo nghiệp vụ**, không retry liên tục. Lỗi kết nối cũng cần phân biệt trước hay sau COMMIT; nếu không biết COMMIT đã thành công hay chưa, retry mù có thể tạo chuyển tiền lần hai.

### 16.2. Nếu mất kết nối ngay sau khi gửi COMMIT

```text
Client gửi COMMIT
DB có thể đã commit
Mạng bị ngắt trước khi client nhận phản hồi
```

Client có trạng thái **không chắc kết quả** (*commit outcome unknown*). Không thể luôn suy ra “không nhận được OK” nghĩa là database đã rollback.

Với thao tác như chuyển tiền, cần một **mã nghiệp vụ idempotent** duy nhất (`transfer_ref`, `request_id`). Khi kết nối phục hồi, tra cứu mã ấy trên nguồn dữ liệu tin cậy để biết giao dịch đã ghi nhận chưa, rồi quyết định retry/đối soát. Cách này quan trọng ngang với BEGIN/COMMIT.

## 17. Mã giao dịch duy nhất và chống thực hiện hai lần

Bảng demo có:

```sql
transfer_ref TEXT PRIMARY KEY
```

Một request chuyển tiền có thể mang một **transfer_ref ổn định**. Khi client retry cùng request, hệ thống phải trả về **kết quả đã ghi** hoặc xử lý xung đột an toàn, chứ không trừ tiền lại chỉ vì HTTP request được gửi hai lần.

### 17.1. Một thiết kế khái niệm

```text
Request: transfer_ref = T-2026-0001
          tenant 10, source 101, target 102, amount 150

Transaction:
  xác định quyền
  dành chỗ / ghi claim cho transfer_ref T-2026-0001
  nếu đã tồn tại:
      đối chiếu payload gốc
      trả trạng thái đã xử lý, không chuyển lần nữa
  nếu mới:
      debit + credit + ledger atomically
  COMMIT
```

Trong cùng một transaction, một `INSERT ... ON CONFLICT` hoặc UNIQUE có thể làm **điểm tuyến tính hóa** để ngăn hai request cùng mã thực hiện hai lần. Nhưng thứ tự claim, chuyển tiền và cách xử lý request trùng/đang chạy cần được thiết kế cẩn thận, đặc biệt khi request đầu chưa commit.

### 17.2. Không chỉ kiểm tra tồn tại rồi mới chuyển

Một mẫu thiếu an toàn:

```text
SELECT transfer_ref -> chưa có
request khác cũng SELECT -> chưa có
cả hai chuyển tiền
sau đó mới INSERT transfer_ref
```

Hai request đã có thể làm thay đổi số dư trước khi một INSERT bị unique conflict, trừ khi tất cả nằm trong transaction được rollback đúng và cơ chế đồng thời được bảo vệ. **UNIQUE ở bảng nhật ký cùng transaction** và logic xử lý conflict là phần thiết kế, không chỉ là kiểm tra SELECT trước.

## 18. Transaction và kết quả của một INSERT nhiều hàng

Một câu:

```sql
INSERT INTO demo_tx_accounts (
    tenant_id, account_id, owner_name, balance
)
VALUES
    (10, 201, 'Khách mới A', 100.00),
    (10, 202, 'Khách mới B', 200.00);
```

được xử lý như một statement. Với DBMS giao dịch như PostgreSQL, nếu một phần của statement vi phạm constraint khiến statement thất bại, các hàng của statement ấy không nên được xem là đã được commit một phần như một kết quả bình thường.

Nhưng **nhiều câu INSERT tách rời** ngoài BEGIN có thể tự commit riêng:

```sql
INSERT INTO ...;  -- thành công và commit riêng
INSERT INTO ...;  -- thất bại
```

Câu đầu đã commit không được hủy chỉ bằng ROLLBACK sau câu hai. Nếu cần **all-or-nothing của cả lô nhiều statement**, đặt chúng trong một transaction hoặc dùng một cơ chế bulk import có ranh giới xác nhận phù hợp.

### 18.1. Batch có thể chứa bản ghi lỗi

Khi nạp nhiều hàng, cần chọn:

- **Cả lô phải thành công:** lỗi một hàng dẫn tới ROLLBACK toàn lô.
- **Chấp nhận một phần:** dùng staging, bảng reject, savepoint hoặc chia batch theo chính sách; ghi rõ hàng đã commit và hàng lỗi.

Không nói “bulk import là atomic” nếu công cụ thực tế đang commit từng chunk.

## 19. DELETE và ROLLBACK: thử thao tác nguy hiểm an toàn

Ví dụ PostgreSQL:

```sql
BEGIN;

DELETE FROM demo_tx_transfers
WHERE tenant_id = 10;

SELECT COUNT(*) AS transfer_rows_left
FROM demo_tx_transfers
WHERE tenant_id = 10;

ROLLBACK;
```

Trong transaction, các transfer bị xóa khỏi tập hàng mà transaction thấy. Sau ROLLBACK, các hàng đó **trở lại** ở trạng thái đã commit trước transaction.

### 19.1. Nhưng cần chú ý điều kiện và FK

Nếu câu DELETE không có WHERE:

```sql
DELETE FROM demo_tx_transfers;
```

nó có thể xóa **mọi hàng** trong bảng nếu không bị ràng buộc khác ngăn. BEGIN không phải một cơ chế tự động xác nhận an toàn: nếu người vận hành gõ COMMIT sau khi xóa nhầm, dữ liệu sẽ được xác nhận bị xóa.

Một quy trình thận trọng cho thay đổi lớn:

```sql
BEGIN;

SELECT COUNT(*) FROM ... WHERE ...;
DELETE FROM ... WHERE ... RETURNING ...;

-- Đối chiếu các hàng tác động, điều kiện nghiệp vụ.
-- COMMIT nếu chắc chắn; ROLLBACK nếu không đúng.
```

Trong sản xuất, chỉ dùng RETURNING cho lượng dữ liệu phù hợp, tránh vô tình trả hàng triệu bản ghi chứa dữ liệu nhạy cảm vào console/log.

### 19.2. `TRUNCATE` không giống DELETE trong mọi hệ

PostgreSQL cho phép TRUNCATE trong transaction và có thể rollback thay đổi dữ liệu của lệnh đó theo ngữ nghĩa PostgreSQL, nhưng MySQL có DDL implicit commit nên không thể suy diễn tương tự. `TRUNCATE` còn có tác động khóa, trigger và identity/sequence khác DELETE. Không thay DELETE bằng TRUNCATE chỉ vì tốc độ mà chưa xét khả năng rollback của hệ đích.

## 20. DDL trong transaction: khác nhau đáng kể giữa DBMS

**DDL** là lệnh định nghĩa đối tượng, như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `TRUNCATE TABLE`. Tính giao dịch của DDL **không thống nhất tuyệt đối**.

### 20.1. PostgreSQL

Nhiều DDL thông dụng có thể nằm trong transaction:

```sql
BEGIN;

CREATE TABLE demo_tx_created_in_transaction (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
```

Sau ROLLBACK, bảng vừa tạo **không còn** nếu chỉ được tạo trong transaction ấy. Nhưng một số lệnh có hạn chế, ví dụ `CREATE DATABASE` không được thực hiện trong một transaction block theo cú pháp PostgreSQL thông thường; các thao tác đặc biệt khác cũng có giới hạn.

Không suy luận “PostgreSQL có transactional DDL” nghĩa **mọi câu lệnh quản trị đều được phép trong BEGIN**.

### 20.2. MySQL

Nhiều DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `TRUNCATE TABLE` gây **implicit commit** trong MySQL theo quy tắc của engine. Ví dụ tưởng rằng:

```sql
START TRANSACTION;
ALTER TABLE orders ADD COLUMN note TEXT;
ROLLBACK;
```

sẽ hủy mọi thứ như PostgreSQL **có thể không đúng**. Những phiên bản MySQL hiện đại có khái niệm **atomic DDL** cho một số thao tác, nhưng atomic DDL không đồng nghĩa với việc DDL sẽ rollback theo transaction bao ngoài của người dùng.

### 20.3. Oracle

Oracle cũng có các DDL thực hiện implicit commit theo quy tắc của hệ. Đặc biệt, từ `BEGIN` trong PL/SQL mở một **khối thủ tục**, **không phải lệnh BEGIN TRANSACTION** tương đương PostgreSQL.

### 20.4. SQL Server và SQLite

SQL Server có nhiều DDL hỗ trợ transaction nhưng một số thao tác bị hạn chế hoặc có cơ chế khác. SQLite hỗ trợ DDL trong transaction trong nhiều trường hợp, nhưng vẫn phải xét lệnh đặc biệt và API/driver. Cách an toàn là **đối chiếu tài liệu phiên bản DBMS đang dùng** trước khi thiết kế migration dựa trên rollback.

## 21. PostgreSQL: READ ONLY và thời gian giữ transaction

Nếu cần một giao dịch chỉ đọc:

```sql
BEGIN TRANSACTION READ ONLY;

SELECT SUM(balance) AS total_balance
FROM demo_tx_accounts
WHERE tenant_id = 10;

COMMIT;
```

READ ONLY ngăn những thay đổi dữ liệu không phù hợp với chế độ read-only của transaction theo quy tắc PostgreSQL. Nhưng nó không tự tạo quyền truy cập dữ liệu nhạy cảm: người dùng vẫn cần **SELECT privilege** thích hợp và tenant scoping.

### 21.1. Có cần BEGIN cho một SELECT đơn giản?

Không luôn cần. Một SELECT đơn lẻ trong chế độ autocommit đã có một phạm vi statement transaction do DBMS quản lý. BEGIN hữu ích khi cần **nhiều SELECT có snapshot/điều kiện cô lập chung** hoặc phối hợp đọc/ghi.

### 21.2. Đừng để transaction mở qua tương tác người dùng

```text
BEGIN
SELECT nhiều dữ liệu
  [người dùng đi ăn trưa, session vẫn mở]
COMMIT
```

có thể giữ snapshot và tài nguyên không cần thiết. PostgreSQL có thể báo trạng thái **idle in transaction**. Với database dùng MVCC, transaction dài có thể cản việc dọn phiên bản hàng cũ và gây áp lực hiệu năng.

Hãy quản lý transaction trong một vùng code có thời gian sống rõ, luôn có đường commit/rollback và trả connection về pool trong trạng thái thích hợp.

## 22. Transaction trong ứng dụng Java/JDBC

Trong JDBC, transaction thường được điều khiển qua **Connection API**, không nhất thiết bằng cách gửi chuỗi `"BEGIN"` thủ công.

Ví dụ minh họa:

```java
Connection conn = dataSource.getConnection();
boolean oldAutoCommit = conn.getAutoCommit();

try {
    conn.setAutoCommit(false);

    try (PreparedStatement debit = conn.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE tenant_id = ? AND account_id = ? AND balance >= ?");
         PreparedStatement credit = conn.prepareStatement(
            "UPDATE accounts " +
            "SET balance = balance + ? " +
            "WHERE tenant_id = ? AND account_id = ?")) {

        BigDecimal amount = new BigDecimal("150.00");

        debit.setBigDecimal(1, amount);
        debit.setInt(2, 10);
        debit.setInt(3, 101);
        debit.setBigDecimal(4, amount);
        if (debit.executeUpdate() != 1) {
            throw new SQLException("Nguồn không tồn tại hoặc không đủ tiền");
        }

        credit.setBigDecimal(1, amount);
        credit.setInt(2, 10);
        credit.setInt(3, 102);
        if (credit.executeUpdate() != 1) {
            throw new SQLException("Đích không tồn tại");
        }

        // Bổ sung ghi ledger/idempotency key trong cùng connection
        // theo chính sách nghiệp vụ, rồi mới commit.
        conn.commit();
    }
} catch (Exception ex) {
    try {
        conn.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    try {
        conn.setAutoCommit(oldAutoCommit);
    } finally {
        conn.close();
    }
}
```

Ví dụ cho thấy các ý cốt lõi:

- Dùng **cùng một Connection** cho debit và credit.
- Tắt autocommit khi cần nhiều statement cùng transaction.
- Dùng `PreparedStatement`/tham số, không nối giá trị người dùng thành SQL.
- **Kiểm tra chính xác một hàng** được cập nhật ở mỗi bước.
- COMMIT chỉ sau khi hoàn tất các thao tác bắt buộc.
- ROLLBACK khi có exception và trả connection về trạng thái phù hợp.
- Dùng `BigDecimal` cho số tiền khi mô hình dùng decimal chính xác.

Đây là **mẫu giảng dạy**, chưa phải hệ thống chuyển tiền production: cần bảo vệ idempotency, lock/order, validation, audit, ledger và phân biệt kết quả commit khi mất kết nối. Trong framework có transaction manager, có thể quản lý BEGIN/COMMIT/ROLLBACK bằng annotation/transaction API thay cho code JDBC trực tiếp; phải hiểu proxy và phạm vi phương thức.

### 22.1. Không dùng hai Connection cho một transaction đơn

```java
Connection c1 = dataSource.getConnection();
Connection c2 = dataSource.getConnection();
```

Nếu debit dùng c1, credit dùng c2, `c1.rollback()` **không rollback** phần credit đã commit trong c2. Transaction của mỗi connection thông thường là riêng biệt. Những transaction phân tán cần cơ chế phối hợp khác, không tự xuất hiện nhờ cùng một `DataSource`.

### 22.2. Connection pool và trạng thái bỏ sót

Nếu code mở transaction rồi không commit/rollback trước khi trả connection về pool, request sau có thể gặp lock, isolation hoặc trạng thái chưa được dọn đúng. Connection pool/driver có thể có cơ chế reset, nhưng application **không nên phụ thuộc mù quáng** vào việc pool cứu một transaction bị bỏ dở.

### 22.3. Framework transaction và self-invocation

Một số framework triển khai transaction bằng proxy/annotation. Nếu một phương thức gọi nội bộ một phương thức khác trong cùng object, lời gọi có thể **bỏ qua proxy** và transaction không được áp dụng như mong đợi, tùy cấu hình framework. Cần kiểm tra cơ chế transaction thực tế; thấy một annotation không bảo đảm mọi lời gọi đã nằm trong cùng giao dịch.

## 23. Outbox pattern khi cần gửi sự kiện sau COMMIT

Một transaction chuyển tiền có thể cần:

```text
1. Debit account nguồn.
2. Credit account đích.
3. Ghi ledger.
4. Gửi event TransferCompleted cho dịch vụ thông báo.
```

Nếu gửi event trước commit, rồi transaction rollback, downstream đã nhận thông báo sai. Nếu commit xong rồi mới gửi event nhưng process crash trước khi gửi, downstream có thể **không bao giờ nhận event**.

**Transactional outbox** giúp xử lý mối liên hệ đó:

```text
BEGIN
  UPDATE account A
  UPDATE account B
  INSERT transfer_ledger
  INSERT outbox_event(status = 'PENDING')
COMMIT

Worker độc lập:
  đọc outbox đã commit
  publish event
  đánh dấu đã gửi theo cơ chế retry/idempotency
```

Điểm quan trọng:

- Ledger và outbox được ghi **trong cùng transaction database**.
- Nếu ROLLBACK, cả thay đổi tài khoản, ledger và event chờ đều bị hủy.
- Nếu COMMIT, event chờ đã được lưu và worker có thể tiếp tục gửi sau khi process ứng dụng khởi động lại.
- Worker có thể gửi lặp khi retry, nên consumer cần **idempotency/dedup**.

Outbox không tự tạo exactly-once end-to-end và không thay thế một thiết kế hệ thống phân tán đầy đủ. Nhưng nó giải quyết khoảng trống phổ biến giữa **COMMIT database** và **publish message**.

## 24. Transaction và thao tác qua nhiều database

Nếu A nằm trong database X còn B nằm trong database Y, một `BEGIN` trên connection X **không tự quản lý** thay đổi ở Y.

Một số môi trường có transaction phân tán/two-phase commit với cơ chế và giới hạn riêng, nhưng việc sử dụng đòi hỏi hạ tầng phối hợp và xử lý lỗi phức tạp. Trong kiến trúc microservices, nhiều luồng chọn saga/compensating actions hoặc các mô hình thiết kế khác.

### 24.1. Không giả định transaction “lan truyền” qua HTTP

```text
BEGIN tại Service A
  UPDATE database A
  POST /pay tại Service B
COMMIT tại A
```

Nếu POST thành công nhưng COMMIT A lỗi, thao tác tại B **không tự rollback**. Nếu B có transaction riêng, nó có phạm vi COMMIT/ROLLBACK riêng. Cần cơ chế idempotency, trạng thái trung gian, retry hoặc bù trừ theo nghiệp vụ.

### 24.2. Giữ transaction DB ngắn khi gọi hệ khác

Không nên giữ lock hàng tài khoản mở suốt nhiều giây để gọi dịch vụ thứ ba khi có thể thiết kế workflow tách pha. Việc này tăng chờ khóa, deadlock và rủi ro timeout. Khi business cần tính nguyên tử xuyên nhiều bước, hãy xác định **ranh giới nhất quán** thay vì kéo dài transaction đơn một cách tùy tiện.

## 25. Khác biệt cú pháp BEGIN/START TRANSACTION theo DBMS

| Hệ quản trị | Mở transaction tường minh | Kết thúc xác nhận/hủy | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **PostgreSQL** | `BEGIN` hoặc `START TRANSACTION` | `COMMIT` / `ROLLBACK` | Nhiều DDL transactional; statement lỗi có thể làm transaction aborted |
| **MySQL/InnoDB** | `START TRANSACTION` hoặc `BEGIN` trong ngữ cảnh SQL thích hợp | `COMMIT` / `ROLLBACK` | `autocommit`, implicit commit với nhiều DDL; engine bảng phải hỗ trợ transaction |
| **SQL Server** | `BEGIN TRANSACTION` / `BEGIN TRAN` | `COMMIT TRANSACTION` / `ROLLBACK TRANSACTION` | `BEGIN ... END` là khối T-SQL, **không mở transaction** |
| **SQLite** | `BEGIN [DEFERRED/IMMEDIATE/EXCLUSIVE] TRANSACTION` | `COMMIT` / `ROLLBACK` | Một writer tại một thời điểm theo cơ chế khóa; API/driver có hành vi autocommit riêng |
| **Oracle Database** | Transaction thường bắt đầu ngầm khi chạy DML; có `SET TRANSACTION` để cấu hình | `COMMIT` / `ROLLBACK` | PL/SQL `BEGIN ... END` **không phải BEGIN TRANSACTION** |

Đối với các hệ khác (MariaDB, Firebird, DuckDB, data warehouse), cần đối chiếu tài liệu và phiên bản cụ thể. Một số kho dữ liệu có hạn chế riêng với transaction nhiều statement hoặc các thao tác load/DDL.

### 25.1. PostgreSQL

```sql
BEGIN;
UPDATE ...;
COMMIT;
```

và:

```sql
START TRANSACTION;
UPDATE ...;
ROLLBACK;
```

là hai mẫu tường minh thường gặp.

### 25.2. MySQL/InnoDB

```sql
START TRANSACTION;
UPDATE accounts SET ...;
UPDATE accounts SET ...;
COMMIT;
```

Hoặc dùng `BEGIN` trong ngữ cảnh statement SQL thích hợp. Với MySQL, `BEGIN ... END` trong stored program dùng để xác định **compound statement**, không nhất thiết có cùng nghĩa mở transaction; trong stored program có thể dùng `START TRANSACTION` để chỉ rõ ý định.

`ROLLBACK` có hiệu lực với thay đổi trên những storage engine hỗ trợ giao dịch, thường là **InnoDB**. Nếu một bảng dùng engine không hỗ trợ transaction, không được mặc định dữ liệu bảng ấy sẽ rollback theo mong muốn.

### 25.3. SQL Server

```sql
BEGIN TRANSACTION;

UPDATE dbo.accounts SET ...;
UPDATE dbo.accounts SET ...;

COMMIT TRANSACTION;
```

Một mẫu T-SQL xử lý exception:

```sql
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    -- Kiểm tra/UPDATE/INSERT ở đây.
    -- Nếu điều kiện nghiệp vụ không đạt, THROW phù hợp.

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
```

`XACT_STATE()` cho biết có transaction và khả năng commit hay không theo ngữ nghĩa SQL Server. `XACT_ABORT ON` có ảnh hưởng tới cách một số lỗi làm hủy transaction; cần hiểu tính tương tác với TRY/CATCH và loại lỗi, không coi mọi câu SQL bất kỳ đều trở nên an toàn tự động.

Trong T-SQL:

```sql
BEGIN
    SELECT 1;
END
```

chỉ là một **khối lệnh**, không tương đương `BEGIN TRANSACTION;`. Đây là khác biệt rất thường gây nhầm lẫn khi chuyển SQL từ PostgreSQL sang SQL Server.

### 25.4. SQLite

```sql
BEGIN IMMEDIATE TRANSACTION;

UPDATE accounts SET ...;

COMMIT;
```

Các kiểu bắt đầu thường gặp:

- `BEGIN DEFERRED`: mặc định; chưa nhất thiết lấy khóa ghi ngay.
- `BEGIN IMMEDIATE`: bắt đầu transaction và cố gắng đặt trước quyền ghi theo cơ chế SQLite; có thể nhận `SQLITE_BUSY` nếu không thể.
- `BEGIN EXCLUSIVE`: mức khóa mạnh hơn trong một số chế độ journal; tương tác với WAL có khác biệt.

SQLite hỗ trợ transaction và rollback, nhưng concurrency writer và lock model khác hệ client–server như PostgreSQL. Cần xử lý busy timeout/retry theo SQLite thay vì sao chép cách khóa hàng `SELECT ... FOR UPDATE` của PostgreSQL.

### 25.5. Oracle Database

Một chuỗi DML Oracle thường:

```sql
UPDATE accounts SET ...;
UPDATE accounts SET ...;
COMMIT;
```

Transaction được bắt đầu ngầm khi có thao tác phù hợp, không cần SQL `BEGIN TRANSACTION` giống PostgreSQL. Nếu cần cấu hình:

```sql
SET TRANSACTION READ ONLY;
```

phải được sử dụng theo giới hạn của Oracle và ngữ cảnh session. Trong PL/SQL:

```sql
BEGIN
    UPDATE accounts SET ...;
    COMMIT;
END;
```

`BEGIN ... END` đánh dấu **khối PL/SQL**, còn `COMMIT` là lệnh transaction bên trong. Không nhầm hai vai trò. Oracle còn có implicit COMMIT liên quan DDL như đã nói, cần đặc biệt cẩn thận khi trộn migration với thao tác DML.

## 26. Transaction lồng nhau: không phải hai lớp COMMIT độc lập

Một lập trình viên có thể kỳ vọng:

```text
BEGIN transaction A
    BEGIN transaction B
    COMMIT B
ROLLBACK A
```

sẽ giữ các thay đổi của B vì B đã COMMIT. Trong nhiều hệ quan hệ thông dụng, **nested transaction thực sự độc lập theo nghĩa đó không có sẵn** trong phạm vi cùng một connection:

- PostgreSQL không hỗ trợ `BEGIN` mở một top-level transaction lồng độc lập; dùng **SAVEPOINT** cho rollback một phần.
- SQL Server có bộ đếm transaction `@@TRANCOUNT`, nhưng COMMIT ở cấp trong không nhất thiết khiến thay đổi bền vững nếu transaction ngoài vẫn còn; ROLLBACK transaction ngoài có thể hủy tất cả.
- Một số framework cung cấp “nested” qua SAVEPOINT hoặc tạo connection/transaction **khác**, và hai cơ chế có semantics khác nhau.

### 26.1. RELEASE SAVEPOINT không phải COMMIT

```sql
BEGIN;
SAVEPOINT inner_step;
UPDATE ...;
RELEASE SAVEPOINT inner_step;
ROLLBACK;
```

Mọi thay đổi chưa commit trong transaction ngoài vẫn bị ROLLBACK dù savepoint đã RELEASE. Khi thiết kế abstraction ở tầng ứng dụng, đừng gọi RELEASE là “commit giao dịch con độc lập”.

### 26.2. Giao dịch độc lập trên connection khác

Nếu một service cố ý ghi audit bằng connection thứ hai và COMMIT trước, audit có thể còn tồn tại dù transaction nghiệp vụ trên connection thứ nhất ROLLBACK. Điều này có thể là lựa chọn thiết kế, nhưng nó **không còn cùng đơn vị nguyên tử**. Cần quyết định rõ audit nào phải commit cùng nghiệp vụ, audit nào được ghi độc lập để theo dõi cả thất bại.

## 27. Kiểm soát lỗi trong transaction bằng ứng dụng

Một flow thực tế nên phân biệt ít nhất ba loại kết quả:

1. **Thành công nghiệp vụ:** tất cả statement và validation thành công → COMMIT.
2. **Từ chối nghiệp vụ:** không đủ tiền, tài khoản không tồn tại, sai tenant, request trùng → ROLLBACK hoặc trả trạng thái hiện có theo thiết kế.
3. **Lỗi kỹ thuật:** deadlock, timeout, mất kết nối, constraint violation → ROLLBACK khi có thể, log mã lỗi, cân nhắc retry nếu an toàn.

Ví dụ pseudocode:

```text
begin transaction

try:
    assert source_account and destination_account belong to tenant
    assert actor authorized
    assert amount > 0 and currency matches
    debit source with balance guard
    if affected_rows != 1:
        raise InsufficientFundsOrMissingSource
    credit destination
    if affected_rows != 1:
        raise MissingDestination
    insert ledger with unique transfer_ref
    commit
    return success
catch business_rejection:
    rollback
    return controlled error
catch transient_db_error:
    rollback if possible
    retry safely with same transfer_ref
catch unexpected_error:
    rollback if possible
    report/log and investigate
```

**Không commit trong nhánh `finally`.** `finally` chạy cả khi có exception, nên dùng nó để cleanup connection/trạng thái, không để tự động xác nhận thay đổi khi một điều kiện nghiệp vụ thất bại.

### 27.1. Lỗi COMMIT cũng phải được xử lý

Không phải COMMIT luôn thành công. Unique/deferred constraints, serialization conflicts, I/O và sự cố kết nối có thể khiến COMMIT thất bại hoặc kết quả không chắc chắn. Ứng dụng cần chỉ trả thành công cho client sau khi có **kết quả commit được xác nhận phù hợp**, hoặc dùng cơ chế truy vết idempotent khi không rõ.

## 28. Isolation và locking trong một tình huống đặt chỗ

Giả sử nhà hát có một ghế chưa bán. Hai người cùng mua gần như đồng thời:

```text
Session A: SELECT seat WHERE status = 'AVAILABLE'
Session B: SELECT seat WHERE status = 'AVAILABLE'
```

Nếu cả hai cùng thấy AVAILABLE rồi mỗi bên `INSERT booking` mà không có khóa/ràng buộc, hệ thống có thể bán trùng ghế.

Một thiết kế có thể:

```sql
BEGIN;

UPDATE seats
SET status = 'SOLD'
WHERE seat_id = :seat_id
  AND status = 'AVAILABLE';

-- Chỉ nếu affected_rows = 1:
INSERT INTO bookings (...);

COMMIT;
```

Và/hoặc unique constraint trên khóa `(show_id, seat_id)` đối với booking còn hiệu lực theo mô hình nghiệp vụ. Nếu UPDATE tác động 0 hàng, phải rollback và báo ghế không còn. **BEGIN riêng nó không đủ ngăn bán trùng**, vì vấn đề còn ở điều kiện kiểm tra và ràng buộc.

### 28.1. Tránh phó mặc dữ liệu lịch sử cho một cờ trạng thái

Khi booking có thể hủy hoặc đổi ghế, UNIQUE toàn bộ bảng có thể không phù hợp. Có thể cần unique/filtered index theo trạng thái còn hiệu lực hoặc mô hình reservation với version và expiration. Đó là bài toán ràng buộc nghiệp vụ đi cùng transaction, không phải chỉ BEGIN/COMMIT.

## 29. Giao dịch đọc trong dashboard và báo cáo

Một dashboard có thể thực hiện:

```text
SELECT COUNT(*) FROM orders;
SELECT SUM(amount) FROM orders WHERE status='PAID';
```

Nếu một transaction khác thêm đơn và commit giữa hai SELECT, số lượng và tổng tiền có thể phản ánh **hai thời điểm khác nhau** khi dùng mức cô lập cho phép mỗi statement có snapshot mới.

Nếu báo cáo cần một **ảnh chụp nhất quán** của nhiều câu đọc, có thể chọn một transaction read-only với mức isolation phù hợp, ví dụ PostgreSQL:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM demo_tx_accounts WHERE tenant_id = 10;
SELECT SUM(balance) FROM demo_tx_accounts WHERE tenant_id = 10;

COMMIT;
```

Trong PostgreSQL, REPEATABLE READ cung cấp snapshot ổn định cho các câu đọc theo quy tắc của engine. **Không giữ transaction snapshot lâu không cần thiết**: report xuất file hàng giờ có thể ảnh hưởng việc dọn version cũ trong MVCC.

### 29.1. Read-only không có nghĩa không cần isolation

Hai SELECT đọc từ dữ liệu đang được cập nhật vẫn có thể cần cùng snapshot để đối soát. Mặt khác, một SELECT đơn dùng READ COMMITTED thường đã đủ cho nhiều dashboard mang tính gần thời gian thực. Chọn theo yêu cầu consistency, không mặc định mọi trang web đều cần SERIALIZABLE.

## 30. Một số sai lầm nghiêm trọng cần tránh

| Sai lầm | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Hai UPDATE cùng request được cho là một transaction | Nếu autocommit bật, mỗi câu có thể commit riêng | BEGIN/driver transaction trên cùng connection |
| COMMIT dù UPDATE nguồn tác động 0 hàng | Cộng tiền đích mà không trừ nguồn | Kiểm tra affected rows và rollback khi không đủ |
| Quên WHERE trong UPDATE/DELETE | Đổi/xóa cả bảng nếu không bị ngăn | Khóa + tenant + điều kiện, kiểm tra row count |
| `BEGIN` tự bảo đảm đúng nghiệp vụ | COMMIT vẫn có thể xác nhận số tiền/đích sai | Constraint và validation đúng |
| ROLLBACK có thể hủy COMMIT trước đó | Không thể | Giao dịch bù hoặc cơ chế restore phù hợp |
| ROLLBACK sẽ thu hồi email đã gửi | Tác dụng ngoài DB không thuộc transaction | Outbox/idempotency |
| Chạy nhiều connection rồi COMMIT một connection | Transaction không tự chia sẻ giữa connection | Dùng chung connection hoặc cơ chế phân tán |
| Một lỗi SQL rồi cứ chạy tiếp trong PostgreSQL | Transaction có thể đã aborted | ROLLBACK hoặc ROLLBACK TO SAVEPOINT |
| `RELEASE SAVEPOINT` là COMMIT giao dịch con | Transaction ngoài vẫn có thể rollback hết | Hiểu savepoint chỉ là mốc phụ |
| SERIALIZABLE nghĩa là không cần retry | Có thể có serialization failure | Retry toàn transaction có giới hạn |
| SELECT rồi UPDATE mà không kiểm tra concurrency | Race và lost update | UPDATE có điều kiện, lock, version, unique |
| Mọi deadlock đều do thiếu index | Có nhiều nguyên nhân vòng chờ | Thứ tự khóa, transaction ngắn, phân tích lock |
| Mọi lỗi database đều nên retry | Lỗi nghiệp vụ/constraint có thể tồn tại lâu dài | Phân loại mã lỗi |
| Không nhận ACK COMMIT nghĩa là rollback | COMMIT có thể thành công trước khi mất mạng | Idempotency key và đối soát |
| `BEGIN` của SQL Server giống `BEGIN TRAN` | BEGIN...END chỉ là khối T-SQL | Dùng BEGIN TRANSACTION |
| `BEGIN` PL/SQL mở transaction giống PostgreSQL | BEGIN...END đánh dấu khối thủ tục | DML mở transaction ngầm; COMMIT/ROLLBACK |
| Mọi DDL đều rollback được | MySQL/Oracle có implicit commit; các hệ có ngoại lệ | Kiểm tra DBMS/version và loại lệnh |
| MySQL ROLLBACK áp dụng mọi storage engine | Bảng nontransactional có thể không rollback | Dùng engine phù hợp như InnoDB |
| Giữ lock khi chờ phản hồi HTTP | Chặn request, tăng timeout/deadlock | Transaction ngắn, workflow tách pha |
| ID sequence phải liền mạch nếu rollback | Sequence/identity có thể có gap | Không dùng ID gap làm bằng chứng commit |
| COMMIT của DB đồng nghĩa downstream đã cập nhật | Cache/queue/search không cùng transaction | Outbox và cơ chế đồng bộ |
| Đóng kết nối không cần cleanup transaction | Có thể leak trạng thái/lock tùy driver/pool | finally cleanup, rollback đúng |

## 31. Bài tập thực hành

Các bài đầu dùng bảng `demo_tx_accounts` và `demo_tx_transfers` ở mục 4. Nếu một bài kết thúc bằng `COMMIT`, kết quả lưu lại trong phiên và có thể ảnh hưởng bài sau; khi chỉ thử logic, dùng `ROLLBACK` hoặc tạo phiên/bảng demo mới.

### Bài 1 — ROLLBACK chuyển tiền

Viết:

```text
BEGIN
  A(101) -= 100
  B(102) += 100
  SELECT số dư trong transaction
ROLLBACK
SELECT số dư sau rollback
```

Vì sao sau ROLLBACK số dư trở lại 1000, 500, 200 trong tenant 10?

### Bài 2 — COMMIT hai UPDATE

Từ dữ liệu ban đầu, chuyển 150 từ 101 sang 102 với BEGIN/COMMIT. Số dư kỳ vọng là 850, 650, 200. Tổng tenant 10 còn bao nhiêu? Nếu muốn có log giao dịch, INSERT bảng transfer phải nằm ở đâu để cùng atomic?

### Bài 3 — UPDATE không tác động hàng nào

Trừ 5000 từ account 101 với điều kiện `balance >= 5000`. SQL có lỗi không? Số hàng cập nhật bằng bao nhiêu? Nếu chương trình vẫn cộng 5000 vào account 102 và COMMIT, bất biến nào bị vi phạm?

### Bài 4 — Tại sao phải lọc tenant?

Trong dữ liệu mẫu, account_id 101 xuất hiện ở tenant 10 và tenant 20. Điều gì xảy ra nếu UPDATE chỉ có `WHERE account_id=101`? Transaction có tự phát hiện lỗi authorization không?

### Bài 5 — SAVEPOINT

Trong transaction, trừ 10 ở 101, đặt SAVEPOINT, cộng nhầm 20 vào 102, ROLLBACK TO SAVEPOINT, sau đó cộng đúng 10. Kết thúc bằng ROLLBACK để không thay đổi demo. Giải thích khác nhau giữa ROLLBACK TO và ROLLBACK toàn bộ.

### Bài 6 — Constraint error

Trong transaction PostgreSQL, cố UPDATE balance thành `-1` để tạo lỗi CHECK. Hành vi của SELECT tiếp theo trong transaction lỗi là gì? Vì sao cần ROLLBACK, hoặc thiết lập savepoint **trước** câu có thể lỗi?

### Bài 7 — Autocommit

Viết hai câu UPDATE trên hai tài khoản **không có BEGIN** trong một client bật autocommit. Nếu câu thứ hai lỗi, câu thứ nhất có thể đã commit không? So sánh với khi hai câu thuộc một transaction rõ ràng.

### Bài 8 — SQL Server và PostgreSQL

Viết tương đương:

```sql
BEGIN;
UPDATE ...;
COMMIT;
```

trong T-SQL. Vì sao `BEGIN ... END` đơn thuần chưa mở transaction SQL Server? Nêu vai trò `XACT_STATE()` khi xử lý exception.

### Bài 9 — MySQL và DDL

Một script MySQL/InnoDB:

```sql
START TRANSACTION;
UPDATE orders SET ...;
ALTER TABLE orders ADD COLUMN note TEXT;
ROLLBACK;
```

Có thể khẳng định ALTER TABLE và UPDATE trước đó đều bị rollback không? Vì sao cần hiểu implicit commit của DDL theo MySQL?

### Bài 10 — Oracle PL/SQL

Phân biệt `BEGIN ... END` của PL/SQL với `BEGIN TRANSACTION` trong PostgreSQL. Nếu thực thi hai UPDATE trong Oracle rồi ROLLBACK trước khi COMMIT, kết quả mong đợi với DML transactional là gì?

### Bài 11 — Isolation và hai phiên

Mô tả kịch bản PostgreSQL READ COMMITTED trong đó Session A SELECT balance, Session B UPDATE + COMMIT, A SELECT lại và thấy giá trị mới. Đó là anomaly gì? REPEATABLE READ thay đổi cách đọc như thế nào?

### Bài 12 — SELECT FOR UPDATE

Trong Session A, BEGIN, SELECT account 101 FOR UPDATE rồi chưa COMMIT. Session B muốn UPDATE cùng hàng; điều gì có thể xảy ra? Vì sao không nên giữ transaction khi người dùng đi ra khỏi trang web?

### Bài 13 — Deadlock

Hai transaction khóa hai account theo thứ tự ngược. Vẽ vòng chờ và giải thích cách DBMS xử lý. Đề xuất thứ tự lấy lock nhất quán và chiến lược retry có giới hạn.

### Bài 14 — Serialization failure

Trong PostgreSQL, một transaction SERIALIZABLE bị lỗi SQLSTATE 40001. Nên retry statement cuối hay **toàn bộ transaction**? Cần điều kiện gì để retry không tạo thanh toán lặp?

### Bài 15 — Commit outcome unknown

Client gửi COMMIT rồi mạng ngắt trước khi nhận OK. Có được tự kết luận “chưa chuyển tiền” không? Thiết kế `transfer_ref` và bước tra cứu trạng thái để quyết định hành động tiếp.

### Bài 16 — Outbox

Một giao dịch cập nhật đơn hàng và phải gửi email xác nhận. Vì sao gửi email **trước COMMIT** và **sau COMMIT nhưng không có cơ chế tin cậy** đều có rủi ro? Hãy mô tả outbox lưu event trong cùng transaction.

### Bài 17 — Hai database

Một UPDATE ghi vào database X, một UPDATE ghi vào database Y. Có thể dùng BEGIN trên connection X để rollback cả Y không? Nêu những mô hình có thể dùng: transaction phân tán nếu hỗ trợ, saga hoặc bù trừ.

### Bài 18 — DELETE trong transaction

Tạo một bảng demo riêng, chạy `BEGIN; DELETE FROM ... WHERE ... RETURNING ...; ROLLBACK;`. Kiểm tra hàng trở lại. Nếu đã COMMIT, việc chạy ROLLBACK sau đó có khôi phục không?

### Bài 19 — READ ONLY report

Một dashboard cần hai SELECT thấy cùng một snapshot dù dữ liệu đổi liên tục. Trên PostgreSQL, viết transaction `REPEATABLE READ READ ONLY`. Vì sao nên tránh giữ transaction này nhiều giờ?

### Bài 20 — Đối soát bất biến

Với chuyển tiền nội bộ tenant 10, tổng ban đầu 1700. Nếu A bị trừ 150 nhưng B chỉ được cộng 140 và transaction COMMIT thành công, transaction có bảo đảm nhất quán nghiệp vụ không? Hãy đề xuất cách kiểm tra số tiền ghi ledger, số hàng debit/credit và bất biến.

### Bài 21 — JDBC

Viết pseudocode Java/JDBC dùng `setAutoCommit(false)`, `PreparedStatement`, `commit`, `rollback`, `finally`/close và kiểm tra affected rows. Những lỗi nào xảy ra nếu một câu chạy trên connection khác hoặc nếu quên rollback khi exception?

### Bài 22 — Transaction lồng

Trong một transaction ngoài, tạo SAVEPOINT, UPDATE, RELEASE SAVEPOINT, rồi ROLLBACK transaction ngoài. Những thay đổi sau RELEASE có được giữ lại không? Giải thích tại sao savepoint không tương đương COMMIT độc lập.

### Bài 23 — Bài thiết kế hoàn chỉnh

Hãy phác thảo API chuyển tiền với:

1. Mã request idempotent.
2. Quyền truy cập tenant và tài khoản nguồn/đích.
3. Kiểm tra amount/currency và số dư.
4. Transaction ngắn với khóa hoặc UPDATE có điều kiện.
5. Debit/credit/ledger/outbox trong cùng transaction.
6. Kiểm tra affected rows.
7. COMMIT, ROLLBACK, xử lý deadlock/serialization và retry.
8. Xử lý tình trạng không chắc COMMIT vì mất kết nối.

Giải thích ranh giới nào do **database** bảo đảm và ranh giới nào vẫn cần **ứng dụng/hệ thống phân tán** giải quyết.

## 32. Mẫu tư duy khi viết transaction

```text
                  YÊU CẦU NGHIỆP VỤ
                           |
                           v
               Xác thực quyền + tenant
                           |
                           v
                    BEGIN TRANSACTION
                           |
                           v
              Đọc/khóa dữ liệu cần thiết
                           |
                           v
                UPDATE/INSERT/DELETE
                           |
                           v
              Kiểm tra số hàng + constraint
                           |
                  +--------+--------+
                  |                 |
               Hợp lệ             Lỗi / thiếu
                  |                 |
                  v                 v
           Ghi ledger/outbox     ROLLBACK
                  |
                  v
                COMMIT
                  |
          +-------+--------+
          |                |
        Đã xác nhận    Chưa rõ kết quả
          |                |
          v                v
      Trả thành công    Tra idempotency key,
      cho request       đối soát rồi quyết định
```

### 32.1. Những câu hỏi cần có trước khi COMMIT

1. **Có đúng các hàng cần cập nhật không?** Mỗi UPDATE ảnh hưởng đúng số hàng dự kiến?
2. **Trạng thái dữ liệu có hợp lệ không?** Constraint, quyền, tenant, số tiền, trạng thái và bất biến đều đúng?
3. **Các bước bắt buộc đã cùng một transaction chưa?** Cùng connection, cùng phạm vi commit?
4. **Có tác dụng ngoài database nào đã xảy ra không?** Nếu có, cần xử lý bù hay idempotency?
5. **Có request trùng hoặc dữ liệu thay đổi đồng thời không?** Có khóa/unique/version/retry phù hợp?
6. **Nếu COMMIT lỗi hoặc client mất kết nối, có cơ chế xác định kết quả thật không?**

Nếu một điều kiện bắt buộc chưa đạt, cách đúng thường là **ROLLBACK** và trả kết quả phù hợp, chứ không COMMIT “phần đã chạy được”.

## 33. Tổng kết

`BEGIN` hoặc `START TRANSACTION` mở một phạm vi giao dịch tường minh ở các DBMS hỗ trợ; `COMMIT` xác nhận thay đổi; `ROLLBACK` hủy những thay đổi chưa được commit. **Cùng một connection, một ranh giới giao dịch rõ ràng, kiểm tra kết quả từng bước và xử lý lỗi đúng** là nền tảng để nhiều câu SQL tạo thành một đơn vị nghiệp vụ đáng tin cậy.

`SAVEPOINT` giúp quay lại một phần trong một transaction, nhưng không phải COMMIT độc lập. Isolation level, row locks, constraint và optimistic concurrency giải quyết những vấn đề đồng thời khác nhau; không có một từ khóa BEGIN nào tự ngăn tất cả race condition, deadlock hoặc lỗi nghiệp vụ. Khi database trả serialization/deadlock failure, ứng dụng thường phải rollback rồi thử lại **toàn bộ transaction** một cách có giới hạn và idempotent.

Cuối cùng, **cú pháp và phạm vi giao dịch phụ thuộc hệ quản trị**: PostgreSQL dùng `BEGIN`/`START TRANSACTION`, SQL Server dùng `BEGIN TRANSACTION`, MySQL có `START TRANSACTION` và implicit commit với nhiều DDL, SQLite có các chế độ BEGIN, Oracle thường bắt đầu transaction ngầm với DML. Một thiết kế SQL vững chắc cần hiểu rõ khi nào COMMIT thực sự xảy ra, ROLLBACK có thể hoàn tác điều gì, transaction thuộc connection nào và cách bảo đảm an toàn cho những thao tác diễn ra **bên ngoài database**.
