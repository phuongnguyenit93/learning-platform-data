# SAVEPOINT, ROLLBACK TO và xử lý lỗi từng phần trong PostgreSQL

Một giao dịch (*transaction*) trong PostgreSQL bảo đảm rằng một nhóm thao tác dữ liệu được xác nhận (*commit*) hoặc hủy bỏ (*rollback*) theo các quy tắc giao dịch. Nhưng ứng dụng thực tế thường cần xử lý một tình huống tinh tế hơn: **một bước không bắt buộc bị lỗi, trong khi các bước hợp lệ trước đó vẫn cần được giữ để giao dịch có thể tiếp tục**.

Ví dụ: một hệ thống nhập 100 dòng dữ liệu; trong đó 97 dòng hợp lệ, hai dòng trùng khóa và một dòng tham chiếu đến khách hàng không tồn tại. Nếu mọi dòng đều nằm trong một giao dịch, câu lệnh bị lỗi có thể làm transaction chuyển sang trạng thái không thể thực thi tiếp. Nếu rollback toàn bộ, 97 dòng hợp lệ cũng mất; nếu bỏ qua lỗi mà tiếp tục `INSERT`, PostgreSQL sẽ báo transaction đang bị hủy (*aborted*).

**`SAVEPOINT`** giải quyết bài toán này bằng cách đánh dấu một mốc bên trong giao dịch. Khi một thao tác sau mốc đó lỗi, ta có thể **`ROLLBACK TO SAVEPOINT`** để hủy các thay đổi sau mốc, phục hồi transaction về trạng thái có thể tiếp tục và giữ các thay đổi hợp lệ ở trước. Nếu bước xử lý thành công, ta có thể **`RELEASE SAVEPOINT`** để bỏ mốc không còn cần thiết.

Điểm quan trọng nhất:

> **SAVEPOINT cho phép rollback một phần công việc của transaction, nhưng không tạo một transaction độc lập và không commit riêng bất kỳ phần nào.** Tất cả thay đổi còn lại vẫn phụ thuộc `COMMIT` hoặc `ROLLBACK` cuối cùng.

Bài này trình bày cú pháp, vòng đời savepoint, hành vi khi SQL có lỗi, thao tác nhiều mốc lồng nhau, xử lý nhập dữ liệu từng dòng, cách dùng trong Java/JDBC và PL/pgSQL, tương tác với constraint, khóa, sequence và các lỗi buộc phải retry toàn bộ transaction.

## 1. Ôn lại vòng đời một transaction

PostgreSQL thường vận hành với hai cách nhóm statement:

- **Autocommit / giao dịch ngầm:** nếu client không mở transaction tường minh, mỗi SQL statement thường chạy trong một transaction riêng.
- **Transaction tường minh:** các statement nằm giữa `BEGIN` và `COMMIT` hoặc `ROLLBACK` thuộc cùng transaction, dùng cùng ranh giới xác nhận hoặc hủy bỏ.

Ví dụ:

```sql
BEGIN;

UPDATE some_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE some_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

`some_accounts` ở ví dụ trên là bảng giả định. Phần sau sẽ dựng schema thực hành chạy được.

Nếu cả hai lệnh `UPDATE` hợp lệ và `COMMIT` thành công, thay đổi được xác nhận cùng nhau. Nếu ứng dụng gọi `ROLLBACK` trước khi commit, toàn bộ thay đổi từ `BEGIN` sẽ bị hủy.

### 1.1. Điều gì xảy ra khi một SQL statement báo lỗi?

Trong PostgreSQL, khi một statement gây lỗi SQL thông thường **bên trong transaction tường minh**, transaction thường đi vào trạng thái **failed/aborted**. Các lệnh SQL tiếp theo không thể tiếp tục xử lý bình thường cho đến khi client rollback transaction hoặc rollback về savepoint hợp lệ.

Ví dụ trình tự:

```text
BEGIN
  |
  +-- INSERT hợp lệ                 -> OK
  |
  +-- INSERT trùng khóa duy nhất    -> ERROR 23505
  |
  +-- SELECT hoặc UPDATE tiếp       -> ERROR 25P02
  |
  +-- ROLLBACK                      -> hủy transaction
```

Lỗi thứ hai thường có thông điệp:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

SQLSTATE `25P02` có nghĩa **in_failed_sql_transaction**. Nó không nhất thiết là nguyên nhân ban đầu; nguyên nhân đầu tiên có thể là `unique_violation`, `foreign_key_violation` hoặc lỗi khác xảy ra trước đó.

**Đừng chỉ sửa câu SQL rồi gửi tiếp trong cùng transaction đã lỗi.** Phải phục hồi trạng thái giao dịch bằng `ROLLBACK TO SAVEPOINT` (khi có savepoint phù hợp), hoặc hủy cả giao dịch bằng `ROLLBACK`.

### 1.2. Statement atomicity khác rollback toàn transaction

Một lệnh `INSERT` chèn nhiều hàng thường là **một SQL statement**. Nếu một hàng trong statement ấy vi phạm constraint và không có cơ chế xử lý thích hợp, PostgreSQL không tự giữ các hàng trước đó trong cùng statement rồi chỉ bỏ hàng lỗi.

Savepoint đánh dấu ranh giới **giữa các thao tác trong transaction**. Nó không biến một `INSERT ... VALUES (...), (...), (...)` bị lỗi thành cơ chế tự động chèn thành công những hàng hợp lệ. Muốn xử lý riêng từng dòng, cần nhiều statement được bảo vệ thích hợp, hoặc thiết kế import/staging, `ON CONFLICT`, PL/pgSQL handler, v.v.

## 2. Cú pháp cơ bản của SAVEPOINT, ROLLBACK TO và RELEASE

Ba lệnh cần ghi nhớ:

```sql
SAVEPOINT savepoint_name;

ROLLBACK TO SAVEPOINT savepoint_name;

RELEASE SAVEPOINT savepoint_name;
```

PostgreSQL cũng chấp nhận dạng rút gọn `ROLLBACK TO name` và `RELEASE name`, nhưng dạng đầy đủ giúp người mới đọc rõ ý nghĩa.

### 2.1. SAVEPOINT: đặt mốc

```sql
BEGIN;
SAVEPOINT before_optional_step;
-- Thực hiện các thao tác có thể cần hủy.
```

`SAVEPOINT` tạo một điểm có tên trong transaction hiện tại. Nó **không commit** những thay đổi trước đó, cũng không bắt đầu một transaction độc lập.

### 2.2. ROLLBACK TO SAVEPOINT: quay về mốc

```sql
ROLLBACK TO SAVEPOINT before_optional_step;
```

PostgreSQL hủy tác động có thể rollback của những thao tác thực hiện **sau savepoint**, nhưng giữ những thay đổi được thực hiện **trước savepoint** trong transaction.

Sau khi rollback về mốc thành công, transaction lại có thể nhận lệnh SQL mới.

### 2.3. RELEASE SAVEPOINT: bỏ mốc, không commit

```sql
RELEASE SAVEPOINT before_optional_step;
```

`RELEASE` bỏ mốc savepoint và chấp nhận giữ các thay đổi đã thực hiện kể từ mốc ấy **trong transaction đang mở**. Nó **không xác nhận thay đổi ra bên ngoài**.

Nếu sau đó gọi `ROLLBACK;`, các thay đổi được “giữ lại” bằng `RELEASE` vẫn bị hủy cùng toàn transaction.

### 2.4. So sánh ba lệnh

| Lệnh | Thay đổi dữ liệu sau mốc | Savepoint | Transaction bên ngoài |
| --- | --- | --- | --- |
| `SAVEPOINT s` | Chưa có thay đổi chỉ vì đặt mốc. | Tạo mốc `s`. | Vẫn mở. |
| `ROLLBACK TO SAVEPOINT s` | Hủy các thay đổi có thể rollback sau `s`. | `s` **vẫn tồn tại**; các mốc mới hơn bị loại. | Được phục hồi để tiếp tục. |
| `RELEASE SAVEPOINT s` | Giữ lại các thay đổi trong transaction, không commit. | Bỏ `s` và các savepoint được tạo sau nó. | Vẫn mở. |
| `ROLLBACK` | Hủy toàn bộ thay đổi chưa commit của transaction. | Mọi savepoint hết hiệu lực. | Kết thúc theo hướng hủy bỏ. |
| `COMMIT` | Xác nhận các thay đổi còn lại nếu thành công. | Mọi savepoint hết hiệu lực. | Kết thúc theo hướng xác nhận. |

`ROLLBACK TO` và `RELEASE` chỉ có ý nghĩa khi có savepoint hợp lệ trong một transaction đang mở. Nếu không có, PostgreSQL báo lỗi thích hợp.

## 3. Sơ đồ rollback từng phần

Giả sử giao dịch xử lý ba bước, trong đó B là tùy chọn:

```text
BEGIN
  |
  +-- A: ghi đơn hàng chính                  [giữ]
  |
  +-- SAVEPOINT before_B                     [đặt mốc]
  |
  +-- B1: trừ tiền                           [hủy khi lỗi]
  +-- B2: ghi log tham chiếu trùng khóa      [ERROR]
  |
  +-- ROLLBACK TO SAVEPOINT before_B         [phục hồi]
  |
  +-- C: cập nhật thông tin hợp lệ            [giữ]
  |
  +-- COMMIT                                 [A và C được xác nhận]
```

Kết quả logic:

```text
Trước SAVEPOINT:   A  ----------- giữ lại -----------+
Sau SAVEPOINT:     B1 + B2 ----- hủy ----------------|
Sau ROLLBACK TO:   C  ----------- giữ lại -----------+
                                               COMMIT
```

Nếu cuối cùng lại gọi `ROLLBACK` thay vì `COMMIT`, **cả A và C cũng bị hủy**. Đây là lý do savepoint không được gọi là “mini-commit”.

## 4. Tạo dữ liệu thực hành độc lập

Ta dùng một hệ thống chuyển tiền mô phỏng để thấy rõ những thay đổi nào còn lại sau rollback từng phần.

**Phạm vi an toàn:** chỉ chạy DDL và DML dưới đây trong database thực hành. Đây là mô hình giảng dạy, **không phải triển khai chuyển tiền production**; sản phẩm tài chính thực cần kiểm soát concurrent updates, quyền, idempotency, đối soát, audit và cơ chế chuyển tiền chính xác hơn.

### 4.1. Tạo schema, bảng tài khoản và bảng lịch sử chuyển

```sql
CREATE SCHEMA IF NOT EXISTS savepoint_lab;

CREATE TABLE savepoint_lab.accounts (
    account_id bigint PRIMARY KEY,
    account_name text NOT NULL,
    balance numeric(14, 2) NOT NULL
        CHECK (balance >= 0)
);

CREATE TABLE savepoint_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key text NOT NULL UNIQUE,
    from_account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_account_id <> to_account_id)
);

INSERT INTO savepoint_lab.accounts
    (account_id, account_name, balance)
VALUES
    (1, 'Tài khoản An',   1000.00),
    (2, 'Tài khoản Bình',  500.00),
    (3, 'Tài khoản Chi',   100.00);
```

Bảng tài khoản ban đầu:

| account_id | account_name | balance |
| ---: | --- | ---: |
| 1 | Tài khoản An | 1000.00 |
| 2 | Tài khoản Bình | 500.00 |
| 3 | Tài khoản Chi | 100.00 |

Tổng số dư ban đầu là **1600.00**.

### 4.2. Kiểm tra trạng thái trước bài tập

```sql
SELECT account_id, account_name, balance
FROM savepoint_lab.accounts
ORDER BY account_id;

SELECT transfer_id, request_key, amount
FROM savepoint_lab.transfers
ORDER BY transfer_id;
```

Nếu `transfers` không rỗng hoặc số dư không như dữ liệu mẫu, kết quả dự đoán trong phần tiếp theo sẽ khác. Nên dùng schema lab mới hoặc một bản dữ liệu được reset bằng quy trình có kiểm soát; không dùng các lệnh xóa hàng loạt tùy tiện trong database đang có dữ liệu thật.

## 5. Thí nghiệm hoàn chỉnh: một bước lỗi nhưng transaction vẫn commit

Yêu cầu mô phỏng:

1. Chuyển 100 từ tài khoản 1 sang 2 (bắt buộc, thành công).
2. Thử chuyển thêm 100 từ tài khoản 1 sang 3 nhưng cố ý dùng `request_key` trùng (bước không hợp lệ, phải hủy).
3. Chuyển 50 từ tài khoản 2 sang 3 (bước hợp lệ).
4. Commit chỉ những thao tác hợp lệ.

### 5.1. Bước A: mở transaction và chuyển 100 từ 1 sang 2

Chạy trong **cùng một kết nối/session**:

```sql
BEGIN;

UPDATE savepoint_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE savepoint_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 2, 100.00);
```

Trong transaction đang mở, số dư tạm thời là:

```text
Account 1: 900
Account 2: 600
Account 3: 100
```

Các thay đổi này **chưa commit**. Các transaction khác không được coi là đã thấy chúng ngay chỉ vì lệnh `UPDATE` hoặc `INSERT` thành công.

### 5.2. Bước B: đặt mốc ngay trước thao tác rủi ro

```sql
SAVEPOINT before_optional_transfer;

UPDATE savepoint_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE savepoint_lab.accounts
SET balance = balance + 100
WHERE account_id = 3;
```

Số dư tạm thời trong transaction lúc này:

```text
Account 1: 800
Account 2: 600
Account 3: 200
```

Tiếp theo **cố ý thực hiện một statement bị lỗi**:

```sql
INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 3, 100.00);
```

`transfer-A` đã được chèn ở bước A, nên unique constraint của `request_key` bị vi phạm:

```text
ERROR: duplicate key value violates unique constraint ...
SQLSTATE: 23505 (unique_violation)
```

Vì lỗi xảy ra **sau savepoint**, ta có thể quay lại mốc và loại cả hai thay đổi số dư đã làm ở B.

### 5.3. Bước phục hồi: ROLLBACK TO SAVEPOINT

Sau khi client đã nhận lỗi ở câu INSERT, chạy:

```sql
ROLLBACK TO SAVEPOINT before_optional_transfer;
```

Transaction phục hồi trạng thái hoạt động; hai `UPDATE` được thực hiện sau savepoint bị hủy. Lúc này:

```sql
SELECT account_id, balance
FROM savepoint_lab.accounts
ORDER BY account_id;
```

Kết quả:

| account_id | balance |
| ---: | ---: |
| 1 | 900.00 |
| 2 | 600.00 |
| 3 | 100.00 |

Quan sát thấy **bước A vẫn còn**, còn các thay đổi ở B đã biến mất. Chưa cần rollback cả transaction.

### 5.4. Bước C: tiếp tục thao tác hợp lệ

```sql
UPDATE savepoint_lab.accounts
SET balance = balance - 50
WHERE account_id = 2;

UPDATE savepoint_lab.accounts
SET balance = balance + 50
WHERE account_id = 3;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-B', 2, 3, 50.00);

RELEASE SAVEPOINT before_optional_transfer;

COMMIT;
```

`RELEASE` ở đây là một bước dọn mốc để thể hiện vòng đời. Nếu không `RELEASE` trước khi `COMMIT` thì savepoint vẫn tự kết thúc cùng transaction.

### 5.5. Kết quả sau khi COMMIT

```sql
SELECT account_id, balance
FROM savepoint_lab.accounts
ORDER BY account_id;

SELECT request_key, from_account_id, to_account_id, amount
FROM savepoint_lab.transfers
ORDER BY request_key;
```

Kết quả số dư:

| account_id | balance |
| ---: | ---: |
| 1 | 900.00 |
| 2 | 550.00 |
| 3 | 150.00 |

Chỉ có hai request key hợp lệ: `transfer-A` và `transfer-B`. Tổng số dư vẫn là **1600.00**.

Thí nghiệm cho thấy:

- Các cập nhật trước savepoint vẫn có thể commit.
- Các cập nhật sau savepoint bị rollback nếu bước liên quan lỗi.
- Các cập nhật sau lần rollback-to vẫn có thể tiếp tục và commit.
- Không có một lần commit độc lập nào của savepoint.

### 5.6. Cách chạy thí nghiệm trong client thực tế

**Quan trọng:** đừng gửi toàn bộ chuỗi từ `BEGIN` đến `COMMIT` như một khối duy nhất cho một công cụ có chế độ “dừng khi gặp lỗi”, hoặc dự đoán client sẽ luôn thực thi mọi statement sau lỗi.

Nên làm lần lượt trong cùng session: chạy bước A → đặt savepoint và hai UPDATE → chạy riêng INSERT cố ý lỗi → nhận thông báo → chạy `ROLLBACK TO SAVEPOINT` → bước C → commit.

- Với `psql`, tùy cấu hình `ON_ERROR_STOP`, một script có thể dừng ngay khi câu SQL lỗi.
- Nếu bật `ON_ERROR_ROLLBACK` của `psql`, client có thể tự tạo savepoint trước mỗi lệnh trong transaction, làm hành vi hiển thị khác thí nghiệm thủ công.
- GUI/IDE có thể tự rollback hoặc tự commit tùy chế độ. Cần kiểm tra công cụ đang dùng để bảo đảm các lệnh thực sự thuộc **cùng connection và transaction**.

Nếu client đã tự hủy toàn transaction sau lỗi, không thể dùng savepoint từ transaction cũ để tiếp tục; hãy khởi tạo lại lab và thử trong chế độ giao dịch có kiểm soát.

## 6. Không có SAVEPOINT sẽ xảy ra gì?

Ví dụ độc lập, chỉ thử khi đã biết bảng chứa request key `transfer-A`:

```sql
BEGIN;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 3, 50.00);
```

Statement báo `23505`. Nếu ngay sau đó chạy:

```sql
SELECT COUNT(*) FROM savepoint_lab.accounts;
```

PostgreSQL sẽ báo transaction đang aborted, thường với SQLSTATE `25P02`.

Để thoát:

```sql
ROLLBACK;
```

Không có mốc savepoint hợp lệ trước lỗi nên không thể chọn cách `ROLLBACK TO ...` để phục hồi riêng phần đó.

### 6.1. Phân biệt lỗi gốc và lỗi tiếp diễn

| Lần thực thi | SQLSTATE có thể gặp | Ý nghĩa |
| --- | --- | --- |
| `INSERT` trùng `request_key` | `23505` | Unique constraint bị vi phạm. |
| `SELECT` ngay sau lỗi khi chưa rollback | `25P02` | Transaction đã ở trạng thái aborted. |
| `ROLLBACK` | Thành công nếu connection vẫn hoạt động. | Hủy toàn transaction và về trạng thái có thể bắt đầu transaction mới. |

Trong log ứng dụng, **đừng chỉ giữ lỗi 25P02**. Nên tìm lỗi ban đầu ở statement đã gây thất bại, vì 25P02 thường là hệ quả.

## 7. SAVEPOINT phải nằm bên trong transaction

Ví dụ đúng:

```sql
BEGIN;
SAVEPOINT step_one;
SELECT 1;
RELEASE SAVEPOINT step_one;
COMMIT;
```

Ví dụ không hợp lệ về phạm vi:

```sql
-- Không có transaction tường minh đang mở:
-- SAVEPOINT outside_tx;
```

PostgreSQL không có ý nghĩa lưu một savepoint vượt ra khỏi ranh giới transaction hiện hành. Sau `COMMIT` hoặc `ROLLBACK`, savepoint cũ không thể sử dụng trong transaction tiếp theo.

### 7.1. Tên savepoint và phạm vi

Tên savepoint là identifier SQL. Những tên đơn giản như `before_import_row` hoặc `before_optional_invoice` dễ đọc hơn một chữ `s` khi câu SQL dài.

```sql
BEGIN;
SAVEPOINT before_import_row;
-- ...
ROLLBACK TO SAVEPOINT before_import_row;
RELEASE SAVEPOINT before_import_row;
COMMIT;
```

Nếu tên cần chữ hoa/ký tự đặc biệt, PostgreSQL áp dụng quy tắc identifier có quote tương tự các đối tượng SQL khác. Ví dụ:

```sql
BEGIN;
SAVEPOINT "BeforeStep";
RELEASE SAVEPOINT "BeforeStep";
ROLLBACK;
```

Không xây tên savepoint từ chuỗi người dùng chưa kiểm tra rồi nối trực tiếp vào SQL; identifier không được xử lý giống value parameter thông thường.

## 8. ROLLBACK TO giữ chính savepoint được chọn

Một chi tiết ít người chú ý: sau:

```sql
ROLLBACK TO SAVEPOINT s1;
```

savepoint `s1` **vẫn tồn tại**. Bạn có thể quay lại mốc ấy thêm lần nữa:

```sql
BEGIN;

SAVEPOINT s1;

SELECT 'thử lần 1' AS attempt;
ROLLBACK TO SAVEPOINT s1;

SELECT 'thử lần 2' AS attempt;
ROLLBACK TO SAVEPOINT s1;

RELEASE SAVEPOINT s1;
COMMIT;
```

Các câu `SELECT` chỉ minh họa phạm vi; để quan sát rollback dữ liệu, hãy sử dụng `INSERT`/`UPDATE` trong schema lab như phần 5.

### 8.1. RELEASE làm mất khả năng quay về mốc đó

```sql
BEGIN;
SAVEPOINT s1;
SELECT 1;
RELEASE SAVEPOINT s1;

-- Không hợp lệ vì s1 không còn:
-- ROLLBACK TO SAVEPOINT s1;

COMMIT;
```

Một khi đã release, **không thể phục hồi điểm đó** bằng tên cũ, trừ khi vẫn còn một savepoint cùng tên ở mức trước theo quy tắc đặt tên lặp (phần 10).

### 8.2. Không thể RELEASE savepoint khi transaction đang lỗi

Nếu một statement sau savepoint gây SQL error và transaction ở trạng thái aborted, `RELEASE SAVEPOINT s` không phải cách phục hồi. Hãy dùng `ROLLBACK TO SAVEPOINT s` trước.

`RELEASE` thích hợp khi bước xử lý thành công và không còn cần khả năng quay lại mốc. Sau lỗi, trước hết phải xử lý trạng thái failed của transaction.

## 9. Savepoint lồng nhau và các mốc theo thứ tự

Bạn có thể tạo nhiều savepoint trong cùng transaction.

```sql
BEGIN;

SAVEPOINT s1;
-- Nhóm thao tác A

SAVEPOINT s2;
-- Nhóm thao tác B

SAVEPOINT s3;
-- Nhóm thao tác C

ROLLBACK TO SAVEPOINT s2;
-- Hủy B và C; s3 không còn, s2 vẫn tồn tại.

RELEASE SAVEPOINT s2;
-- s1 vẫn còn.

RELEASE SAVEPOINT s1;
COMMIT;
```

Sơ đồ:

```text
BEGIN
  |
  +-- SAVEPOINT s1
       |
       +-- thao tác A
       |
       +-- SAVEPOINT s2
            |
            +-- thao tác B
            |
            +-- SAVEPOINT s3
                 |
                 +-- thao tác C
                 |
                 +-- ROLLBACK TO s2

Sau ROLLBACK TO s2:
  - A còn trong transaction
  - B và C bị hủy
  - s1 còn
  - s2 còn
  - s3 bị hủy
```

**Rollback tới mốc cũ hơn sẽ làm mất các savepoint được tạo sau mốc đó.** Không thể rollback về `s3` sau khi đã rollback về `s2`.

### 9.1. RELEASE mốc ngoài cũng giải phóng các mốc trong

Nếu bạn tạo `s1` rồi `s2` sau đó `RELEASE SAVEPOINT s1`, PostgreSQL giải phóng `s1` và những savepoint được tạo sau nó. Các thay đổi dữ liệu vẫn còn trong transaction, nhưng không thể dùng các mốc đã bị release.

Không xem savepoint như một ngăn xếp các transaction được commit từ trong ra ngoài. Nó là các **mốc phục hồi bên trong cùng transaction**, với hành vi loại bỏ mốc khi rollback-to/release.

### 9.2. Vì sao cần cấu trúc rõ?

Trong một ứng dụng lớn:

```text
Transaction cấp service
  +-- Savepoint xử lý invoice
         +-- Savepoint kiểm tra attachment
  +-- Savepoint gửi audit tùy chọn
```

Nếu một thư viện tự tạo và release savepoint cấp ngoài, nó có thể ảnh hưởng các savepoint con. Vì vậy các tầng code dùng chung một JDBC connection cần thống nhất **ai sở hữu ranh giới savepoint**, tránh thư viện phụ tự ý release một mốc không thuộc quyền quản lý của nó.

## 10. PostgreSQL cho phép dùng lại tên savepoint

PostgreSQL cho phép tạo một savepoint mới với tên đã được sử dụng trong cùng transaction:

```sql
BEGIN;

SAVEPOINT checkpoint;
-- Một số thay đổi ở giai đoạn đầu.

SAVEPOINT checkpoint;
-- Một số thay đổi ở giai đoạn sau.

ROLLBACK TO SAVEPOINT checkpoint;
-- Quay về checkpoint được tạo gần nhất.

RELEASE SAVEPOINT checkpoint;
-- Giải phóng checkpoint gần nhất, checkpoint cũ có thể lộ ra.

RELEASE SAVEPOINT checkpoint;
COMMIT;
```

Khác với việc “ghi đè” và xóa mốc cũ, PostgreSQL **giữ mốc trùng tên trước đó nhưng tạm che khuất**. Khi mốc mới hơn được release, mốc cùng tên cũ có thể lại được tham chiếu.

Đây là điểm có thể gây bất ngờ cho code tạo tên savepoint tự động. Để dễ bảo trì, thường nên chọn tên mô tả riêng cho từng phạm vi hoặc để driver quản lý đối tượng `Savepoint`, thay vì phụ thuộc hành vi tên trùng.

## 11. SAVEPOINT không phải “nested transaction” độc lập

Các hệ quản trị và ORM đôi khi mô tả savepoint là **subtransaction** hoặc “nested transaction”. Cách gọi đó có ích về cơ chế phục hồi nhưng dễ bị hiểu sai ở nghiệp vụ.

| Thuộc tính | Transaction chính | Savepoint |
| --- | --- | --- |
| Có thể `COMMIT` độc lập? | Có, với toàn transaction. | **Không**. |
| Có thể rollback phạm vi của nó? | Có, toàn transaction. | Có, về mốc savepoint. |
| Thay đổi được transaction khác nhìn thấy sau RELEASE? | Không phải do RELEASE. | **Không**. |
| Có identity/sequence scope riêng hoàn toàn? | Không; một số hiệu ứng ngoài rollback tồn tại. | Không. |
| Sống qua COMMIT/ROLLBACK của transaction ngoài? | Transaction kết thúc. | Không. |
| Phù hợp xử lý bước tùy chọn trong một giao dịch? | Có thể qua savepoint. | **Có**. |

Một savepoint được release **không làm dữ liệu bền vững**. Khi transaction ngoài rollback, mọi thay đổi chưa commit ở các bước đã release cũng bị hủy.

### 11.1. Hai chiều nhìn về tính atomic

- Toàn giao dịch là đơn vị atomic đối với dữ liệu được commit.
- Savepoint cung cấp khả năng **chọn giữ hoặc hủy một số thao tác trước khi quyết định commit toàn giao dịch**.

Vì thế “xử lý lỗi từng phần” không làm PostgreSQL mất tính atomic của transaction cuối cùng. Nó chỉ giúp quyết định **tập các thao tác hợp lệ** sẽ được xác nhận cùng nhau.

## 12. Một statement lỗi không có nghĩa toàn bộ dữ liệu đã rollback

Một hiểu lầm:

> PostgreSQL đã báo lỗi unique constraint, vậy những lệnh UPDATE trước đó trong transaction chắc đã bị hủy.

Không nên suy luận như vậy. Sau statement lỗi, transaction thường bị đánh dấu aborted. Các thay đổi chưa commit trước đó không tự trở thành dữ liệu đã commit hay đã bị rollback toàn bộ ngay tại thời điểm lỗi; transaction cần được **kết thúc hoặc phục hồi về savepoint** theo quy tắc.

Nếu rollback về savepoint ở giữa:

- Các thay đổi trước savepoint vẫn có thể tiếp tục tồn tại trong transaction.
- Các thay đổi sau savepoint bị hủy.

Nếu rollback toàn bộ:

- Tất cả thay đổi chưa commit của transaction bị hủy.

Chỉ khi `COMMIT` thành công mới có thể nói transaction đã xác nhận những thay đổi còn lại.

## 13. Xử lý nhập dữ liệu từng phần bằng savepoint

Một trường hợp sử dụng rõ nhất: nhập dữ liệu từ file hoặc dịch vụ bên ngoài.

Giả sử có bốn hàng:

```text
row 1: source_key = new-1     account_id = 1    -> hợp lệ
row 2: source_key = dup-A     account_id = 2    -> trùng khóa
row 3: source_key = bad-ref   account_id = 999  -> sai foreign key
row 4: source_key = new-2     account_id = 3    -> hợp lệ
```

Yêu cầu: nhập các hàng hợp lệ, ghi lỗi của các hàng bị bỏ qua, cuối cùng commit một transaction chứa **kết quả được chấp nhận**.

### 13.1. Tạo bảng nhập dữ liệu và bảng ghi lỗi

```sql
CREATE TABLE savepoint_lab.import_records (
    import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key text NOT NULL UNIQUE,
    account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id)
);

CREATE TABLE savepoint_lab.import_errors (
    error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_row_no integer NOT NULL,
    source_key text,
    sqlstate_code text NOT NULL,
    error_message text NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT statement_timestamp()
);

INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1);
```

Bảng `import_records` có khóa duy nhất trên `source_key`. `account_id` có foreign key. `import_errors` chỉ là bảng minh họa log lỗi; hệ thống thực tế có thể cần `batch_id`, kiểu lỗi, payload được che dữ liệu nhạy cảm, số lần thử và thời điểm nhận dữ liệu.

### 13.2. Quy trình ở tầng ứng dụng

Pseudocode:

```text
BEGIN

FOR EACH input_row:
    SAVEPOINT before_row

    TRY:
        INSERT input_row
        RELEASE SAVEPOINT before_row

    CATCH recoverable_db_error:
        ROLLBACK TO SAVEPOINT before_row
        RELEASE SAVEPOINT before_row
        INSERT import_errors (... thông tin lỗi ...)

    CATCH unexpected_error:
        ROLLBACK toàn transaction
        báo lỗi để xử lý

COMMIT nếu chính sách cho phép kết quả xử lý từng phần
```

Đây là mô tả logic, không phải cú pháp PL/pgSQL chạy trực tiếp. Điểm quan trọng là **lỗi phải được client bắt**, rồi thực hiện `ROLLBACK TO SAVEPOINT` trước khi gửi SQL tiếp theo. Nếu gửi lệnh ghi log lỗi **trước khi rollback-to**, PostgreSQL có thể trả `25P02` thay vì ghi log.

### 13.3. Với dữ liệu ít, SQL thử tay

```sql
BEGIN;

SAVEPOINT before_row_1;
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('new-1', 1);
RELEASE SAVEPOINT before_row_1;

SAVEPOINT before_row_2;
-- Chạy riêng lệnh này; sẽ lỗi unique_violation:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

Sau lỗi, chạy:

```sql
ROLLBACK TO SAVEPOINT before_row_2;
RELEASE SAVEPOINT before_row_2;

INSERT INTO savepoint_lab.import_errors (
    source_row_no, source_key, sqlstate_code, error_message
)
VALUES (
    2, 'dup-A', '23505', 'Trùng source_key; bỏ qua hàng nhập'
);
```

Tiếp:

```sql
SAVEPOINT before_row_3;

-- Chạy riêng, dự đoán lỗi foreign_key_violation:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('bad-ref', 999);
```

Phục hồi:

```sql
ROLLBACK TO SAVEPOINT before_row_3;
RELEASE SAVEPOINT before_row_3;

INSERT INTO savepoint_lab.import_errors (
    source_row_no, source_key, sqlstate_code, error_message
)
VALUES (
    3, 'bad-ref', '23503', 'account_id không tồn tại'
);

SAVEPOINT before_row_4;
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('new-2', 3);
RELEASE SAVEPOINT before_row_4;

COMMIT;
```

Kết quả:

- Hàng `new-1` và `new-2` được lưu.
- `dup-A` chỉ còn bản ghi hạt giống ban đầu.
- `bad-ref` không được lưu.
- Có hai hàng trong `import_errors` cho nguồn 2 và 3.

**Lưu ý:** câu SQL cố ý gây lỗi phải được chạy trong client tiếp tục phiên tương tác; không phải mọi script runner đều tự làm được bước phục hồi sau lỗi. Nếu ứng dụng cần tự động hóa, dùng transaction API của driver hoặc cơ chế `EXCEPTION` trong PL/pgSQL.

## 14. Cách khác: PL/pgSQL EXCEPTION và subtransaction tự động

Trong PL/pgSQL, khối `BEGIN ... EXCEPTION ... END` có thể xử lý lỗi của một phần công việc. PostgreSQL thực hiện phần có handler bằng cơ chế subtransaction tương tự savepoint: khi có exception, thay đổi database thực hiện trong phạm vi khối bị hủy trước khi handler chạy, trong khi công việc ở bên ngoài khối vẫn có thể tiếp tục.

Điểm thuận tiện là bạn **không cần viết thủ công `SAVEPOINT` và `ROLLBACK TO` bên trong mỗi khối PL/pgSQL**.

### 14.1. Ví dụ nhập từng hàng với EXCEPTION

Để có ví dụ độc lập với những hàng `new-1`/`new-2` ở phần trước, dùng khóa mới:

```sql
BEGIN;

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT *
        FROM (
            VALUES
                (11, 'batch2-A'::text, 1::bigint),
                (12, 'dup-A'::text,    2::bigint),
                (13, 'batch2-B'::text, 999::bigint),
                (14, 'batch2-C'::text, 3::bigint)
        ) AS input(source_row_no, source_key, account_id)
        ORDER BY source_row_no
    LOOP
        BEGIN
            INSERT INTO savepoint_lab.import_records (
                source_key, account_id
            )
            VALUES (item.source_key, item.account_id);

        EXCEPTION
            WHEN unique_violation OR foreign_key_violation THEN
                INSERT INTO savepoint_lab.import_errors (
                    source_row_no,
                    source_key,
                    sqlstate_code,
                    error_message
                )
                VALUES (
                    item.source_row_no,
                    item.source_key,
                    SQLSTATE,
                    SQLERRM
                );
        END;
    END LOOP;
END;
$$;

SELECT source_key, account_id
FROM savepoint_lab.import_records
WHERE source_key LIKE 'batch2-%'
ORDER BY source_key;

SELECT source_row_no, source_key, sqlstate_code
FROM savepoint_lab.import_errors
WHERE source_row_no BETWEEN 11 AND 14
ORDER BY source_row_no;

ROLLBACK;
```

Khi dữ liệu lab ban đầu còn đúng:

- Hai hàng `batch2-A` và `batch2-C` được chèn thành công, có thể nhìn thấy trong cùng transaction trước `ROLLBACK`.
- Hàng `dup-A` gây `23505`; handler ghi log.
- Hàng `batch2-B` có account 999 gây `23503`; handler ghi log.
- `ROLLBACK` ở cuối là để **thử mà không lưu** thay đổi của bài tập vào database.

Nếu thay `ROLLBACK` bằng `COMMIT`, các hàng thành công và error log sẽ được xác nhận cùng transaction, giả sử không có lỗi khác.

### 14.2. SQLSTATE và SQLERRM trong handler

Trong nhánh `EXCEPTION` của PL/pgSQL:

- `SQLSTATE` biểu diễn mã lỗi SQLSTATE hiện hành.
- `SQLERRM` chứa thông điệp lỗi.

Mã lỗi hữu ích để phân loại theo chương trình, còn chuỗi thông điệp phù hợp để giúp con người điều tra. Không nên điều khiển logic bằng cách so sánh chính xác chuỗi English error message vì bản dịch/cấu hình/phiên bản có thể khác.

Các mã thường gặp:

| SQLSTATE | Tên lỗi | Ví dụ |
| --- | --- | --- |
| `23505` | `unique_violation` | `request_key` trùng. |
| `23503` | `foreign_key_violation` | Tham chiếu account 999. |
| `23502` | `not_null_violation` | Thiếu cột bắt buộc. |
| `23514` | `check_violation` | `balance < 0` hoặc amount không hợp lệ. |
| `22P02` | `invalid_text_representation` | Cast `'abc'` thành integer. |
| `25P02` | `in_failed_sql_transaction` | Tiếp tục gửi SQL khi transaction đã aborted. |
| `40001` | `serialization_failure` | Xung đột mức cô lập serializable. |
| `40P01` | `deadlock_detected` | Deadlock giữa transactions. |

Không phải lỗi nào cũng nên được “nuốt” trong `EXCEPTION`. Các lỗi thể hiện hỏng invariant, cạnh tranh giao dịch hoặc sự cố hệ thống cần chính sách khác.

### 14.3. Khối EXCEPTION tạo ranh giới rollback

Ví dụ không cần bảng:

```sql
DO $$
DECLARE
    value_before integer := 1;
BEGIN
    BEGIN
        value_before := 2;
        PERFORM 1 / 0;
    EXCEPTION WHEN division_by_zero THEN
        RAISE NOTICE 'Caught; variable value = %', value_before;
    END;
END;
$$;
```

Khi exception được bắt, các thay đổi **database** trong phần khối có lỗi được rollback theo subtransaction; tuy nhiên biến PL/pgSQL như `value_before` giữ giá trị đã được gán (trong ví dụ là 2) tại thời điểm lỗi.

**Phân biệt trạng thái biến trong PL/pgSQL với thay đổi của bảng database.** Không dùng giá trị biến sau handler để giả định một `UPDATE` trước lỗi chắc đã được giữ.

### 14.4. Cẩn trọng khi dùng WHEN OTHERS

```sql
-- Ví dụ khung minh họa; không nên nuốt mọi lỗi tùy tiện:
-- EXCEPTION
--     WHEN OTHERS THEN
--         RAISE NOTICE 'Có lỗi: %', SQLERRM;
```

`WHEN OTHERS` quá rộng có thể che lỗi lập trình hoặc tình trạng dữ liệu nguy hiểm. Nên bắt **những nhóm lỗi được xác định có thể phục hồi**, ghi log đầy đủ và để lỗi bất ngờ lan ra để toàn transaction được xử lý ở tầng sở hữu transaction.

Trong PL/pgSQL, `OTHERS` còn có các ngoại lệ cụ thể đối với một số lỗi như `QUERY_CANCELED` và `ASSERT_FAILURE` theo quy tắc PostgreSQL. Không dựa vào `OTHERS` như cách bắt mọi sự cố hệ thống bằng mọi giá.

### 14.5. Không mở COMMIT trong EXCEPTION block

Trong PL/pgSQL, khối có `EXCEPTION` tạo ranh giới subtransaction; PostgreSQL không cho kết thúc transaction bằng `COMMIT` hoặc `ROLLBACK` **ngay bên trong phạm vi exception handler/subtransaction đó** như một cách “commit từng dòng”.

Nếu cần quyền điều khiển transaction từ procedure hoặc top-level `DO`, còn phải tuân thủ các điều kiện ngữ cảnh gọi riêng của PostgreSQL. Trong ví dụ này, transaction bên ngoài được điều khiển bằng `BEGIN`/`COMMIT`/`ROLLBACK` tại client; handler chỉ quyết định rollback tiểu phần và tiếp tục xử lý.

## 15. Java/JDBC: Savepoint API và SQLSTATE

Trong ứng dụng Java, không nên quản lý savepoint bằng cách ghép chuỗi SQL thủ công khi JDBC đã có API phù hợp:

- `Connection.setAutoCommit(false)` để quản lý transaction tường minh.
- `Connection.setSavepoint()` hoặc `setSavepoint(name)` để đặt mốc.
- `Connection.rollback(savepoint)` để quay lại mốc.
- `Connection.releaseSavepoint(savepoint)` để giải phóng.
- `Connection.commit()` hoặc `Connection.rollback()` để kết thúc toàn transaction.

### 15.1. Ví dụ hàm xử lý một INSERT không bắt buộc

Giả định connection đã mở transaction do service bên ngoài quản lý:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;

public final class OptionalImport {
    public static boolean tryInsert(
            Connection connection,
            String sourceKey,
            long accountId
    ) throws SQLException {
        if (connection.getAutoCommit()) {
            throw new SQLException(
                "Call inside a transaction with autoCommit=false"
            );
        }

        Savepoint savepoint = connection.setSavepoint("optional_import");

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "INSERT INTO savepoint_lab.import_records " +
                     "(source_key, account_id) VALUES (?, ?)"
                 )) {
            statement.setString(1, sourceKey);
            statement.setLong(2, accountId);
            statement.executeUpdate();

            connection.releaseSavepoint(savepoint);
            return true;

        } catch (SQLException error) {
            String sqlState = error.getSQLState();
            boolean recoverable =
                "23505".equals(sqlState) ||
                "23503".equals(sqlState);

            if (!recoverable) {
                // Caller must rollback entire transaction.
                throw error;
            }

            // Restore connection to a usable transaction state.
            connection.rollback(savepoint);
            connection.releaseSavepoint(savepoint);

            // Caller may record the rejected row if policy allows.
            return false;
        }
    }
}
```

Đoạn code minh họa:

1. Đặt savepoint trước statement rủi ro.
2. Thành công thì release và báo `true`.
3. Với hai mã lỗi được phép bỏ qua, rollback về savepoint rồi release và báo `false`.
4. Lỗi khác được ném ra để tầng trên xử lý toàn transaction.

**Không nên nuốt lỗi từ `connection.rollback(savepoint)`.** Nếu rollback tới mốc thất bại, trạng thái connection có thể không còn phù hợp để tiếp tục; hàm cần để ngoại lệ lan ra và tầng quản lý transaction rollback toàn bộ hoặc loại bỏ connection.

### 15.2. Tầng sở hữu transaction quyết định COMMIT

Ví dụ khung:

```java
connection.setAutoCommit(false);

try {
    // Các thao tác bắt buộc trước bước tùy chọn.
    // ...

    boolean imported = OptionalImport.tryInsert(
        connection, "new-request", 1L
    );

    if (!imported) {
        // Có thể ghi nhận trạng thái xử lý từng phần.
        // Không được tự xem bước optional là thành công.
    }

    // Các thao tác bắt buộc sau bước tùy chọn.
    // ...

    connection.commit();
} catch (SQLException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
} finally {
    connection.setAutoCommit(true);
}
```

`connection` ở đoạn này giả định được lấy từ nguồn có quản lý lifecycle; trong ứng dụng thật cần bảo đảm connection được đóng/trả pool đúng cách và rollback trên mọi đường lỗi. `setAutoCommit(true)` khi transaction còn dang dở có thể tác động tới transaction tùy driver; vì vậy khối `try/catch` phải bảo đảm đường đi kết thúc giao dịch trước khi trả connection về pool.

Điểm thiết kế quan trọng: **hàm `tryInsert` không tự gọi `commit()`**. Transaction cấp service quyết định cuối cùng tất cả kết quả có được xác nhận hay không.

### 15.3. Đừng catch mọi SQLException rồi tiếp tục

Ví dụ chống chỉ định:

```java
// Không nên:
// try {
//     insertSomething();
// } catch (SQLException ignored) {
//     // bỏ qua, không rollback savepoint
// }
// insertNextSomething(); // có thể gặp SQLSTATE 25P02
```

Nếu PostgreSQL đã đánh dấu transaction failed, việc Java bắt exception **không tự phục hồi trạng thái transaction phía server**. Phải gọi `rollback(savepoint)` hoặc `rollback()`.

### 15.4. ORM và framework quản lý nested transaction

Một số framework có cơ chế transaction nested được triển khai qua JDBC savepoint; framework khác chỉ hỗ trợ propagation kiểu tạo transaction riêng trên connection khác, hoặc không hỗ trợ nested ở ngữ cảnh hiện tại.

Không thể mặc định một annotation tên `NESTED` sẽ giống mọi hệ quản trị và mọi transaction manager. Cần kiểm tra cụ thể:

- Transaction manager có JDBC savepoint support không?
- Connection đang được dùng chung hay đã mở connection mới?
- Framework rollback về savepoint hay đánh dấu transaction ngoài rollback-only?
- Exception đã bị xử lý ở tầng đúng chưa?
- Savepoint có bị release trước khi code bên ngoài cần dùng?

Đặc biệt, một framework có thể đặt transaction **rollback-only** khi có lỗi dù code phía dưới đã catch; khi đó `COMMIT` cuối vẫn thất bại hoặc bị rollback. Hãy hiểu semantics của transaction manager, không chỉ SQL raw.

## 16. Savepoint và INSERT ... ON CONFLICT

Nếu một lỗi trùng khóa là **tình huống bình thường, dự kiến thường xuyên**, sử dụng savepoint cho từng dòng có thể phức tạp và tốn chi phí hơn cần thiết.

PostgreSQL hỗ trợ xử lý xung đột duy nhất qua `INSERT ... ON CONFLICT`.

### 16.1. Bỏ qua hàng trùng theo unique key

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1)
ON CONFLICT (source_key) DO NOTHING;
```

Nếu `source_key='dup-A'` đã tồn tại, PostgreSQL bỏ qua row này theo nhánh conflict, **không làm transaction aborted** chỉ vì lỗi unique conflict được xử lý như vậy.

Không cần đặt savepoint riêng cho trường hợp xung đột này.

### 16.2. Khi nào ON CONFLICT không thay thế SAVEPOINT?

`ON CONFLICT` chủ yếu xử lý các xung đột unique/exclusion phù hợp với cú pháp của lệnh. Nó **không tự xử lý mọi lỗi** như:

- Foreign key vi phạm.
- Check constraint vi phạm.
- Not null vi phạm.
- Cast kiểu dữ liệu không hợp lệ.
- Một lỗi phát sinh từ trigger hoặc chức năng khác.

Nếu luồng nhập phải ghi nhận từng hàng lỗi thuộc nhiều loại và tiếp tục, savepoint hoặc exception handler vẫn có vai trò.

### 16.3. Tình huống DO UPDATE

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2)
ON CONFLICT (source_key)
DO UPDATE SET account_id = EXCLUDED.account_id;
```

Câu này cố ý **cập nhật bản ghi đã có** theo quy tắc upsert, không phải chỉ bỏ qua hàng trùng. Phải cân nhắc tính đúng đắn của việc ghi đè account ID. `DO UPDATE` vẫn có thể gây lỗi khác và không mặc nhiên giải quyết mọi constraint.

Trong lab giữ nguyên dữ liệu dự đoán, không chạy ví dụ upsert cập nhật trừ khi bạn muốn kiểm tra đúng tác động đó.

## 17. Khi nào nên chọn savepoint, ON CONFLICT hay staging?

| Tình huống | Hướng xử lý thường phù hợp |
| --- | --- |
| Chỉ muốn bỏ qua `INSERT` trùng unique key | `INSERT ... ON CONFLICT DO NOTHING`. |
| Trùng unique key thì cập nhật theo quy tắc rõ ràng | `ON CONFLICT DO UPDATE`. |
| Một bước tùy chọn có thể lỗi và cần hủy mọi DML của bước | `SAVEPOINT` / `ROLLBACK TO` hoặc PL/pgSQL `EXCEPTION`. |
| Import rất nhiều dòng có các loại lỗi khác nhau | Staging, validation theo set và nạp dữ liệu hợp lệ; có thể kết hợp savepoint khi cần. |
| Lỗi làm transaction không còn đáng tin hoặc invariant quan trọng bị phá | Rollback toàn transaction và xử lý ở tầng service. |
| Deadlock/serialization failure | Retry **toàn bộ transaction** theo chính sách, không chỉ bỏ qua bước lỗi. |
| Cần thao tác phụ độc lập phải commit dù transaction chính rollback | Thiết kế transaction riêng, outbox hoặc workflow phù hợp; savepoint **không** cung cấp independent commit. |

Một hệ thống throughput cao nhập hàng triệu dòng thường nên ưu tiên xử lý **theo tập** với staging/constraint và logic idempotent thay vì tạo một savepoint mỗi dòng; điều đó cần đo trên workload thật.

## 18. Xử lý lỗi từng phần không đồng nghĩa bỏ qua lỗi nghiệp vụ

Không nên nhìn `23505` rồi tự động xem mọi lần trùng khóa là chấp nhận được. Một unique violation có thể là:

- Client retry cùng một request đã thành công trước đó → có thể xử lý idempotent.
- Hai request thực sự khác nhau nhưng dùng chung request key → có thể là lỗi logic nghiêm trọng.
- Một hàm sinh ID bị lỗi → cần dừng và điều tra.

Tương tự, `23503` có thể là:

- Một hàng staging tham chiếu mã chưa tồn tại → có thể đưa vào hàng đợi chờ xác minh.
- Một hoạt động chuyển tiền tham chiếu tài khoản không tồn tại → không nên tiếp tục một giao dịch tài chính như thể thành công.

**Quy tắc lựa chọn:** chỉ rollback-to và tiếp tục khi nhóm lỗi đã được nghiệp vụ cho phép phục hồi và kết quả còn lại vẫn bảo toàn invariant.

### 18.1. Ghi nhận kết quả xử lý từng phần

Một API nhập dữ liệu có thể trả:

```json
{
  "batchId": "batch-2026-11-14-A",
  "received": 4,
  "accepted": 2,
  "rejected": 2,
  "rejections": [
    {"row": 2, "code": "DUPLICATE_SOURCE_KEY"},
    {"row": 3, "code": "UNKNOWN_ACCOUNT"}
  ]
}
```

Đây là ví dụ cấu trúc phản hồi, không phải kết quả chạy SQL tự sinh. Hãy công bố rõ **toàn batch có được commit hay không**, vì “hàng hợp lệ” trước khi commit vẫn có thể bị rollback nếu một bước bắt buộc sau đó thất bại.

### 18.2. Không gửi thông báo thành công trước commit

Nếu application gửi email hoặc webhook “đã nhập thành công” ngay sau khi release savepoint, nhưng transaction cuối cùng rollback, bên nhận đã nhận một thông báo sai.

Với event phát ra ngoài database, cân nhắc transaction outbox hoặc luồng chỉ phát sau khi commit thành công. Savepoint không thể rollback email đã gửi hoặc request HTTP đã được đối tác xử lý.

## 19. Những tác dụng phụ không được rollback giống DML

Phần lớn thay đổi transactional trên bảng PostgreSQL được rollback theo transaction/savepoint. Nhưng không phải **mọi hiệu ứng quan sát được** đều quay lại.

### 19.1. Sequence và identity không rollback số đã cấp

`nextval(...)` tăng sequence và việc cấp số **không tự hoàn nguyên** khi transaction hoặc savepoint bị rollback.

Đó là lý do ID của bảng sử dụng `GENERATED ... AS IDENTITY` có thể **bị khuyết** sau một lần INSERT thất bại.

Ví dụ minh họa với bảng `transfers` dùng identity:

```sql
BEGIN;
SAVEPOINT before_probe;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('temporary-probe', 1, 2, 1.00)
RETURNING transfer_id;

ROLLBACK TO SAVEPOINT before_probe;
RELEASE SAVEPOINT before_probe;

ROLLBACK;
```

Hàng `temporary-probe` đã được rollback. Nhưng giá trị identity được cấp khi INSERT có thể khiến số kế tiếp **không liên tục**.

**Không dùng ID liên tục để chứng minh một transaction/savepoint không từng gặp lỗi**. Sequence ưu tiên cấp giá trị theo cơ chế phù hợp với concurrency, không hứa khoảng ID không có lỗ.

### 19.2. Hiệu ứng bên ngoài database

Các thao tác như gửi HTTP request, email, ghi tệp ngoài hoặc gọi dịch vụ từ application **không được PostgreSQL tự rollback** khi gọi `ROLLBACK TO SAVEPOINT`.

Đừng đặt một thao tác external side effect vào giữa các câu SQL rồi mong savepoint bảo đảm atomic xuyên mọi hệ thống. Nếu cần tính nhất quán nhiều hệ thống, phải thiết kế event/outbox, idempotency và cơ chế bù trừ (*compensation*) ở tầng workflow.

### 19.3. Khóa được lấy sau savepoint

Khi rollback về savepoint, PostgreSQL nói chung giải phóng những khóa được lấy sau savepoint theo quy tắc subtransaction, trong khi những khóa đã giữ trước savepoint vẫn có thể tiếp tục tồn tại tới khi transaction kết thúc.

Ví dụ:

```text
BEGIN
  |
  +-- UPDATE account 1       -> có thể giữ khóa trước savepoint
  |
  +-- SAVEPOINT s
  |
  +-- UPDATE account 2       -> lấy khóa sau savepoint
  |
  +-- ROLLBACK TO s          -> hủy thay đổi account 2
  |
  +-- transaction vẫn mở     -> account 1 chưa commit
```

Savepoint không phải công cụ để dọn sạch mọi khóa của transaction. **Transaction dài vẫn có thể gây blocking**, ngay cả khi nhiều bước đã rollback-to.

## 20. Deferred constraints: lỗi có thể xuất hiện muộn

Một số constraint trong PostgreSQL có thể khai báo `DEFERRABLE`, cho phép kiểm tra ở thời điểm muộn hơn trong transaction. Điều này ảnh hưởng trực tiếp đến nơi bạn đặt savepoint và nơi lỗi xuất hiện.

### 20.1. Tạo foreign key kiểm tra trì hoãn

```sql
CREATE TABLE savepoint_lab.parent_keys (
    parent_id bigint PRIMARY KEY
);

CREATE TABLE savepoint_lab.child_keys (
    child_id bigint PRIMARY KEY,
    parent_id bigint NOT NULL,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES savepoint_lab.parent_keys(parent_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Foreign key ở đây có thể được kiểm tra vào cuối transaction thay vì lập tức tại mỗi INSERT, tùy chế độ constraint hiện hành.

### 20.2. Lỗi không lộ ra ngay tại INSERT

```sql
BEGIN;

SAVEPOINT before_child;

INSERT INTO savepoint_lab.child_keys (child_id, parent_id)
VALUES (1, 999);

-- Nếu constraint đang deferred, INSERT có thể chưa báo lỗi.
```

Giả sử parent 999 không tồn tại, bước chèn có thể được PostgreSQL **tạm chấp nhận trong transaction** vì foreign key deferred.

Nếu bạn `RELEASE SAVEPOINT before_child;` rồi tiếp tục đến `COMMIT`, constraint có thể chỉ bị phát hiện lỗi vào thời điểm commit. Khi `COMMIT` thất bại, **đã quá muộn để quay về savepoint như thể transaction vẫn hoạt động**.

### 20.3. Buộc kiểm tra trước khi release

Muốn lỗi rơi vào phạm vi có thể rollback về mốc, dùng `SET CONSTRAINTS ... IMMEDIATE` trong transaction:

```sql
SET CONSTRAINTS ALL IMMEDIATE;
```

Với hàng child trỏ 999 chưa có parent, câu này có thể báo `23503`. Khi lỗi xuất hiện và savepoint `before_child` vẫn còn, phục hồi:

```sql
ROLLBACK TO SAVEPOINT before_child;
RELEASE SAVEPOINT before_child;
COMMIT;
```

Do `SET CONSTRAINTS ALL IMMEDIATE` tác động rộng đến các constraint deferrable trong phạm vi phù hợp, thực tế nên dùng đúng tên constraint khi có thể và hiểu tác động với các bảng khác trong transaction.

**Lưu ý:** việc chuyển constraint sang immediate cũng là thay đổi transactional về chế độ kiểm tra. Nếu lệnh `SET CONSTRAINTS` gặp lỗi, chế độ cũ được giữ theo quy tắc PostgreSQL; rollback tới savepoint còn khôi phục những thay đổi trong phạm vi savepoint.

### 20.4. Không phải constraint nào cũng có thể deferred

PostgreSQL không hỗ trợ trì hoãn mọi kiểu constraint như nhau. Ví dụ, `CHECK` và `NOT NULL` nói chung được kiểm tra ngay; các loại `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE` có cơ chế deferrable khi được định nghĩa phù hợp, với một số hạn chế liên quan đến `ON CONFLICT`.

Vì vậy, không giả định mọi lỗi sẽ được phát hiện ở `COMMIT` hay mọi lỗi sẽ xuất hiện ngay tại câu `INSERT`. Cần đọc DDL thực tế của bảng và constraint.

## 21. Khi gặp deadlock hoặc serialization failure

Một lỗi nhập liệu dự kiến như trùng `source_key` khác về bản chất với **lỗi điều phối giữa transactions đồng thời**.

Ví dụ hai mã:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

Trong các trường hợp này, phương án xử lý phổ biến là **rollback và retry toàn bộ transaction**, không phải chỉ rollback về một savepoint rồi bỏ qua statement gây lỗi.

### 21.1. Vì sao retry toàn transaction?

Ở mức isolation `SERIALIZABLE`, các quyết định nghiệp vụ trước lỗi có thể đã dựa trên một tập dữ liệu/quan sát không còn hợp lệ với lịch sử thực thi đồng thời. Để giữ đúng ngữ nghĩa serializable, cần chạy lại **logic quyết định của giao dịch** trên một transaction mới với snapshot phù hợp, không chỉ phát lại câu SQL cuối.

Đối với deadlock, PostgreSQL có thể chủ động hủy một transaction để phá vòng chờ; ứng dụng nên retry transaction một cách có giới hạn và có backoff.

### 21.2. Mô hình retry ở service

```text
for attempt = 1..maxRetries:
    BEGIN transaction
    try:
        đọc dữ liệu
        kiểm tra nghiệp vụ
        ghi các thay đổi
        COMMIT
        return SUCCESS
    catch SQLSTATE 40001 hoặc 40P01:
        ROLLBACK nếu connection còn dùng được
        chờ backoff có jitter
        thử lại TOÀN BỘ logic với transaction mới
    catch lỗi không retryable:
        ROLLBACK
        báo lỗi
```

Đây là pseudocode ở tầng ứng dụng, không phải cú pháp PostgreSQL hoàn chỉnh. Số lần thử, backoff, idempotency và cách phát sự kiện phải phù hợp workload.

**Quan trọng:** không retry mù những giao dịch có external side effects đã xảy ra mà không có khóa idempotency. Retry toàn transaction ở database vẫn cần thiết kế chống gửi email/thanh toán hai lần.

### 21.3. Connection failure

Nếu connection bị mất, ứng dụng có thể không biết server đã commit hay chưa trong một số tình huống gần ranh giới `COMMIT`. Khi đó không thể đơn giản gửi `ROLLBACK TO` trên connection cũ.

Hệ thống cần request key/idempotency và cơ chế tra cứu trạng thái sau reconnect. Savepoint không giải quyết tình trạng **kết quả commit không rõ** qua mất kết nối.

## 22. Lỗi timeout và hủy câu lệnh

Trong PostgreSQL có các tình huống như:

- `statement_timeout`: statement chạy quá lâu và bị hủy.
- `lock_timeout`: chờ lấy khóa vượt giới hạn.
- Người dùng/client hủy một query.

Những trường hợp này có thể tạo lỗi statement và làm transaction hiện tại rơi vào trạng thái failed, trừ khi được xử lý trong ranh giới phù hợp như savepoint/exception.

Nhưng có nên rollback-to rồi chạy tiếp không?

**Tùy mục tiêu và sức khỏe của transaction.** Nếu đó là một bước tùy chọn độc lập và client vẫn kết nối tốt, một số lỗi có thể được phục hồi theo thiết kế. Nếu timeout cho thấy hệ thống đang quá tải hoặc thao tác là bắt buộc, thường nên hủy transaction và retry/từ chối theo chính sách rõ ràng.

Không đồng nhất “SQL error có thể rollback-to” với “ứng dụng nên tiếp tục bất chấp mọi lỗi”.

## 23. Kiểm chứng savepoint bằng thay đổi dữ liệu

Muốn phân biệt `ROLLBACK TO` với `ROLLBACK`, bạn có thể dùng một bảng test nhỏ:

```sql
CREATE TABLE savepoint_lab.test_marks (
    mark_id integer PRIMARY KEY,
    note text NOT NULL
);
```

Chạy:

```sql
BEGIN;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (1, 'Trước mốc');

SAVEPOINT s1;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (2, 'Sau mốc');

ROLLBACK TO SAVEPOINT s1;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (3, 'Sau rollback-to');

SELECT mark_id, note
FROM savepoint_lab.test_marks
ORDER BY mark_id;

ROLLBACK;
```

Trong transaction, ngay trước `ROLLBACK` cuối, kết quả là:

| mark_id | note |
| ---: | --- |
| 1 | Trước mốc |
| 3 | Sau rollback-to |

Không có mark 2. Sau `ROLLBACK` cuối, cả mark 1 và mark 3 cũng không còn trong bảng (giả sử bảng ban đầu rỗng).

### 23.1. Thử RELEASE rồi ROLLBACK

```sql
BEGIN;

SAVEPOINT s;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (4, 'Đã release, chưa commit');

RELEASE SAVEPOINT s;

ROLLBACK;
```

Mark 4 **không tồn tại sau rollback**. Điều này trực tiếp bác bỏ nhầm lẫn “release savepoint bằng commit riêng”.

### 23.2. Thử rollback lại cùng một mốc

```sql
BEGIN;

SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (5, 'Lần đầu');
ROLLBACK TO SAVEPOINT s;

INSERT INTO savepoint_lab.test_marks VALUES (6, 'Lần hai');
ROLLBACK TO SAVEPOINT s;

SELECT * FROM savepoint_lab.test_marks
WHERE mark_id IN (5, 6);

RELEASE SAVEPOINT s;
ROLLBACK;
```

Không có mark 5 hoặc 6 trong câu `SELECT` vì hai lần rollback đều quay về cùng mốc `s`.

## 24. Rollback từng phần và tính nhất quán nghiệp vụ

Một transaction có thể gồm các thao tác:

```text
A. Lưu đơn hàng             (bắt buộc)
B. Giữ tồn kho              (bắt buộc)
C. Ghi audit phụ trợ         (tùy chọn)
D. Tạo ghi chú nội bộ        (tùy chọn)
E. Xác nhận đơn             (bắt buộc)
```

Nếu `B` thất bại vì không đủ tồn kho, ta **không** nên rollback-to riêng B rồi commit A và E như thể đơn hợp lệ.

Ngược lại, nếu `C` chỉ ghi một dòng thống kê phụ và policy cho phép thất bại mà không ảnh hưởng đơn, có thể đặt savepoint trước C rồi rollback-to khi lỗi, sau đó tiếp tục D/E.

### 24.1. Mức độ quan trọng của bước

| Bước | Có thể bỏ qua khi lỗi? | Cách xử lý |
| --- | --- | --- |
| Xác thực đủ tiền trước chuyển khoản | Không | Rollback toàn transaction nếu điều kiện bắt buộc không đạt. |
| Giữ tồn kho khi bán hàng | Thường không | Rollback toàn bộ workflow ghi đơn nếu thất bại. |
| Ghi một trường thống kê không bắt buộc | Có thể | Savepoint trước bước, rollback-to rồi ghi nhận lỗi. |
| Nhập một hàng độc lập trong batch cho phép partial success | Có thể | Savepoint hoặc PL/pgSQL exception theo từng hàng. |
| Gửi email bên ngoài database | Không rollback được bằng savepoint | Outbox/workflow sau commit/idempotency. |

**Tính đúng đắn của giao dịch không chỉ là không có SQL error.** Cần bảo toàn invariant của nghiệp vụ đối với kết quả mà bạn chọn commit.

### 24.2. Có thể coi mọi hàng là độc lập không?

Giả sử các dòng nhập có phụ thuộc:

```text
Dòng 1: tạo customer
Dòng 2: tạo order cho customer dòng 1
Dòng 3: tạo order_item cho order dòng 2
```

Nếu dòng 2 thất bại nhưng dòng 3 vẫn tiếp tục, không thể áp dụng chính sách “bỏ qua riêng dòng lỗi” mà không xét quan hệ phụ thuộc.

Hãy chọn đơn vị rollback đúng với **đơn vị nghiệp vụ độc lập**: cả order và order_items có thể là một nhóm cần cùng thành công hoặc cùng bị hủy, thay vì mỗi SQL statement là một savepoint tách rời.

## 25. Savepoint trong các batch lớn: chi phí và vận hành

Tạo nhiều savepoint/subtransaction có chi phí quản lý. Khi số lần sử dụng rất lớn, chúng có thể làm tăng overhead quản lý transaction và ảnh hưởng tốc độ xử lý.

### 25.1. Một savepoint cho từng dòng có luôn tốt?

Không. Nếu nhập hàng triệu dòng, cách “một dòng → SAVEPOINT → INSERT → RELEASE” có thể chậm và phức tạp.

Hãy cân nhắc:

1. Nạp dữ liệu thô vào staging với `COPY` hoặc batch insert theo chính sách.
2. Kiểm tra dữ liệu bằng truy vấn theo tập, phát hiện lỗi định dạng và tham chiếu.
3. Tách các hàng hợp lệ, có chiến lược `ON CONFLICT` nếu dự kiến trùng.
4. Ghi log hàng bị từ chối.
5. Chèn dữ liệu hợp lệ vào bảng đích trong transaction có giới hạn thời gian và kích thước phù hợp.

Savepoint vẫn hữu ích cho một số bước nhỏ hoặc ranh giới nghiệp vụ rõ ràng, nhưng **không tự thay thế chiến lược bulk load tối ưu**.

### 25.2. Transaction kéo dài có chi phí riêng

Ngay cả khi rollback từng phần, transaction ngoài vẫn có thể giữ khóa và ảnh hưởng MVCC/vacuum theo điều kiện thực tế. Một batch kéo dài hàng giờ với hàng chục nghìn savepoint không phải kiến trúc mặc định tốt.

Nếu nghiệp vụ cho phép commit theo chunk, cân nhắc chia thành nhiều transaction, mỗi chunk có idempotency và khả năng retry. Đánh đổi: không còn atomic toàn bộ batch; đó là **thay đổi hợp đồng nghiệp vụ**, cần được chấp nhận rõ.

### 25.3. Ghi log có cấu trúc

Một log xử lý lỗi từng phần nên ghi:

- Batch/request ID.
- Đơn vị công việc bị từ chối.
- SQLSTATE và mã lỗi nghiệp vụ.
- Số lần retry.
- Trạng thái transaction commit cuối cùng.
- Context cần thiết nhưng tránh log bí mật hoặc dữ liệu nhạy cảm không cần thiết.

Không nên chỉ ghi `ERROR` chung chung rồi không biết bước nào đã rollback, bước nào cuối cùng được commit.

## 26. SAVEPOINT và isolation level

PostgreSQL hỗ trợ những mức isolation như `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Savepoint **không tự thay đổi isolation level** của transaction.

### 26.1. Snapshot và rollback-to

`ROLLBACK TO SAVEPOINT` hủy những thay đổi sau mốc, nhưng không biến transaction đang ở `REPEATABLE READ` thành một transaction mới có snapshot độc lập.

Nếu một phép đọc thấy dữ liệu theo snapshot hiện hành, rollback tới savepoint không đồng nghĩa mọi quyết định trước đó đã được đánh giá lại với trạng thái committed mới nhất của database.

### 26.2. Serializable và nguy cơ retry

Ở `SERIALIZABLE`, khi PostgreSQL báo `40001`, ứng dụng thường phải bắt đầu lại toàn transaction. Một savepoint có thể giúp tổ chức thao tác, nhưng không thay thế yêu cầu retry logic nghiệp vụ dưới một transaction mới.

### 26.3. Visibility ra session khác

Sau `ROLLBACK TO` và trước `COMMIT`, những thay đổi trước savepoint còn lại vẫn **chưa commit**. Session khác không xem chúng là đã bền vững/visible theo cách một transaction đã commit.

Tương tự, `RELEASE SAVEPOINT` không làm thay đổi mức độ hiển thị ra các session khác. Ranh giới quyết định việc xác nhận dữ liệu vẫn là transaction ngoài.

## 27. Các câu hỏi thực tế khi thiết kế savepoint

**Có được tạo savepoint trước mọi UPDATE không?** Được khi phù hợp, nhưng thường không cần. Đặt savepoint ở ranh giới **bước nghiệp vụ có thể hủy độc lập**, thay vì cơ học trước mọi SQL.

**Một savepoint có thể tồn tại giữa hai lần lấy connection từ pool không?** Không mặc nhiên. Savepoint thuộc transaction trên một connection; nếu lần thứ hai nhận connection khác hoặc transaction đã kết thúc, mốc cũ không còn.

**Sau RELEASE có commit một phần được không?** Không. RELEASE chỉ bỏ mốc rollback, còn transaction ngoài vẫn có thể rollback toàn bộ.

**Sau ROLLBACK TO có phải tạo lại savepoint không?** Không bắt buộc; mốc được rollback tới vẫn tồn tại. Có thể release sau khi quyết định xong.

**Khi lỗi unique constraint có nên luôn rollback-to rồi continue?** Chỉ khi business policy cho phép bỏ qua hoặc xử lý riêng bước đó; nếu là invariant của thao tác chính, rollback toàn bộ.

**Khi COMMIT báo lỗi constraint deferred thì có rollback-to được không?** Thông thường lúc đó transaction đã thất bại/đã bị hủy khi `COMMIT` không thành công; muốn xử lý từng phần phải chủ động phát hiện trước commit, ví dụ `SET CONSTRAINTS ... IMMEDIATE` khi savepoint vẫn còn.

**Lỗi trong transaction có khiến toàn bộ DML trước đó tự commit không?** Không. Lỗi SQL không phải commit; thay đổi trước đó vẫn phụ thuộc rollback/recovery và commit transaction.

**Có thể dùng ROLLBACK TO để hoàn nguyên số identity đã cấp không?** Không. Sequence/identity có thể để lại khoảng trống.

**Tại sao JDBC bắt SQLException rồi vẫn gặp 25P02?** Vì bắt exception ở Java không rollback trạng thái transaction bị lỗi ở PostgreSQL server.

**Có nên xử lý HTTP/email trong cùng khối savepoint không?** Savepoint chỉ quản lý thay đổi transactional trong PostgreSQL, không rollback được tác động đã xảy ra ở hệ thống bên ngoài.

## 28. Lỗi thường gặp

### Lỗi 1. Tạo SAVEPOINT ngoài transaction

Không có transaction block hợp lệ thì mốc không thể sống như mong đợi. Mở transaction tường minh hoặc dùng transaction API của driver.

### Lỗi 2. Quên rollback-to sau câu SQL lỗi

Ứng dụng bắt lỗi rồi tiếp tục gửi `SELECT`/`INSERT`, dẫn đến `25P02`. Phải rollback về savepoint hợp lệ hoặc rollback toàn transaction.

### Lỗi 3. Dùng RELEASE để sửa trạng thái aborted

`RELEASE` không phục hồi transaction lỗi. Dùng `ROLLBACK TO SAVEPOINT` trước.

### Lỗi 4. Nghĩ RELEASE nghĩa là commit

Một lần `ROLLBACK` cuối có thể hủy cả thay đổi đã release. Savepoint không có independent commit.

### Lỗi 5. Rollback về mốc cũ rồi vẫn cố dùng mốc mới hơn

`ROLLBACK TO s1` làm mất những savepoint được tạo sau `s1`. Nếu cần phân tầng, hiểu rõ thứ tự mốc còn sống.

### Lỗi 6. Tên savepoint trùng nhau gây nhầm

PostgreSQL có thể giữ nhiều mốc cùng tên và ưu tiên mốc mới nhất. Dùng tên/ownership rõ để tránh thao tác trên mốc không dự kiến.

### Lỗi 7. Nuốt mọi SQL exception

Lỗi dữ liệu dự kiến khác deadlock/serialization/system failure. Chỉ bỏ qua nhóm lỗi đã được chính sách cho phép, không catch mọi trường hợp.

### Lỗi 8. Xem SQLSTATE 25P02 là nguyên nhân đầu tiên

Hãy tìm statement đầu tiên báo lỗi; 25P02 thường là hậu quả của transaction đã aborted.

### Lỗi 9. Ghi lỗi vào bảng trước khi rollback-to

Trong transaction failed, lệnh ghi log cũng có thể bị từ chối. Rollback-to trước, rồi mới INSERT log hoặc dùng PL/pgSQL exception handler.

### Lỗi 10. Cố giữ các hàng hợp lệ trong một INSERT nhiều hàng bị lỗi

Một SQL statement lỗi không tự phân chia thành các statement con. Dùng import/validation theo tập, `ON CONFLICT` hoặc xử lý từng dòng khi cần.

### Lỗi 11. Dùng savepoint để chữa thiếu transaction locking

Nếu hai client cùng chuyển tiền, phải có chiến lược khóa/update/isolation phù hợp. Savepoint không thay thế concurrency control.

### Lỗi 12. Không kiểm tra constraint deferred trước commit

Lỗi có thể chỉ xuất hiện tại `COMMIT` khi savepoint không còn hữu dụng. Phải hiểu thời điểm kiểm tra constraint và phát hiện trước khi release nếu cần phục hồi từng phần.

### Lỗi 13. Cho rằng sequence rollback đồng bộ cùng hàng

`nextval`/identity có thể tiến dù hàng bị rollback, tạo lỗ trong dãy ID.

### Lỗi 14. Dùng nhiều savepoint vô hạn trong batch

Overhead có thể lớn. Nên cân nhắc staging, bulk load, xử lý theo tập hoặc chia chunk phù hợp.

### Lỗi 15. Giả định client chạy tiếp mọi câu lệnh sau một SQL error

Script runner có thể dừng, framework có thể tự rollback. Các bài thử có lỗi cố ý cần điều khiển kết nối và chính sách lỗi của client.

### Lỗi 16. Đặt savepoint sau thao tác có thể lỗi

Nếu lỗi xảy ra **trước khi savepoint được tạo**, không thể rollback về một mốc được đặt sau lỗi. Đặt savepoint **trước** đơn vị rủi ro.

### Lỗi 17. ROLLBACK TO nhưng không giữ nguyên invariant

Hủy một nửa thao tác chuyển tiền rồi giữ nửa kia ở trước savepoint có thể làm tổng tiền sai. Đặt ranh giới theo nhóm thao tác **phải thành công cùng nhau**.

### Lỗi 18. Bỏ qua lỗi rollback(savepoint) ở driver

Nếu thao tác phục hồi thất bại, không tiếp tục như transaction vẫn bình thường. Chuyển sang hủy transaction và báo lỗi.

### Lỗi 19. Trộn transaction chính với side effect ngoài DB

Rollback không hủy email, HTTP request hay hệ thống thanh toán khác. Cần idempotency, outbox và quy tắc bù trừ.

### Lỗi 20. Coi savepoint là cách tránh retry toàn transaction

Với `40001`/`40P01`, thường phải retry toàn transaction sau rollback có kiểm soát. Lỗi đồng thời không giống lỗi trùng hàng nhập có thể bỏ qua.

## 29. Bài tập thực hành

Các bài sau dùng schema `savepoint_lab` đã tạo ở phần 4, 13 và 23. Nên chạy trên bản lab sạch hoặc tự đổi ID/key nếu đã thực hiện các ví dụ ghi trước đó. Với bài tạo lỗi, nên chạy từng câu SQL trong **cùng session tương tác**, không nhờ client tự bỏ qua mọi lỗi.

### Bài 1. Đặt một savepoint

Mở transaction, tạo mốc `before_test`, thực hiện một `SELECT 1`, release mốc rồi rollback transaction. Giải thích vì sao không có dữ liệu nào được commit.

### Bài 2. Rollback từng phần

Chèn mark 11 trước savepoint; chèn mark 12 sau savepoint; rollback tới mốc; chèn mark 13; chọn các mark rồi rollback toàn transaction. Mark nào xuất hiện trong kết quả SELECT trước rollback cuối?

### Bài 3. Bước lỗi unique

Trong bảng `import_records` đã có `source_key='dup-A'`. Đặt savepoint trước khi chèn lại key này, quan sát `23505`, rollback-to và chạy một SELECT hợp lệ.

### Bài 4. Không có savepoint

Mở transaction, thực hiện một INSERT trùng unique key không có savepoint, sau đó thử SELECT. Giải thích `25P02` và cách phục hồi.

### Bài 5. RELEASE không phải COMMIT

Chèn mark 21 sau savepoint, release, rollback toàn transaction. Kiểm tra mark 21 sau đó; vì sao bị mất?

### Bài 6. Dùng lại một savepoint

Đặt `s`, chèn mark 31, rollback-to, chèn mark 32, rollback-to lần nữa. Savepoint `s` còn không, và những mark nào được giữ?

### Bài 7. Savepoint lồng nhau

Tạo `s1`, ghi mark 41; tạo `s2`, ghi mark 42; tạo `s3`, ghi mark 43; rollback tới `s2`. Các mark còn lại là gì? Savepoint nào bị loại?

### Bài 8. Tên mốc trùng

Tạo hai savepoint cùng tên `checkpoint`. Rollback-to theo tên đó về mốc nào? Điều gì xảy ra sau khi release mốc mới nhất?

### Bài 9. Xử lý nhập từng hàng

Nhập bốn hàng `new-X`, `dup-A`, `bad-ref` và `new-Y`, với account lần lượt 1, 2, 999, 3. Dùng savepoint mỗi hàng hoặc PL/pgSQL exception. Hàng nào được chấp nhận?

### Bài 10. Phân loại SQLSTATE

Ghép các mã `23505`, `23503`, `23514`, `25P02`, `40001`, `40P01` với tên lỗi và đề xuất ứng xử ban đầu.

### Bài 11. ON CONFLICT

Viết `INSERT ... ON CONFLICT (source_key) DO NOTHING` để bỏ qua key `dup-A`. Trường hợp này có cần rollback-to không? Cách đó có tự xử lý foreign key 999 không?

### Bài 12. Biến PL/pgSQL và rollback dữ liệu

Trong khối `BEGIN ... EXCEPTION`, gán biến `x:=2` rồi gây division by zero. Sau handler, biến còn giá trị nào? DML trên bảng thực hiện trước lỗi trong cùng khối được giữ hay hủy?

### Bài 13. JDBC savepoint

Viết trình tự `setAutoCommit(false)` → `setSavepoint()` → chạy INSERT → `rollback(savepoint)` khi lỗi dự kiến → `releaseSavepoint()` → `commit()`. Ai phải quyết định commit cuối?

### Bài 14. Deferred foreign key

Trong bảng `child_keys` có FK deferred, chèn child trỏ parent không tồn tại sau savepoint. Tại sao INSERT có thể không báo lỗi ngay? Làm sao phát hiện lỗi trước khi release?

### Bài 15. Sequence và identity

Trong savepoint, chèn một hàng dùng identity rồi rollback-to. Có được kỳ vọng lần INSERT sau nhận lại đúng ID vừa bị hủy không?

### Bài 16. Chọn đúng phạm vi rollback

Một order và order_item phải được ghi cùng nhau, nhưng thao tác ghi thống kê phụ có thể thất bại. Nên đặt savepoint trước thao tác nào? Khi order_item thất bại thì nên xử lý ra sao?

### Bài 17. Serializable retry

Transaction `SERIALIZABLE` báo SQLSTATE `40001` sau một số truy vấn đọc và ghi. Có nên rollback tới savepoint rồi tiếp tục với các dữ liệu đã đọc cũ không?

### Bài 18. Đối soát sau partial rollback

Sau ví dụ chuyển tiền ở phần 5, dự đoán số dư ba tài khoản, tổng số dư và danh sách request key được commit.

### Bài 19. Transaction đổi connection

Vì sao không thể đặt savepoint trên connection A rồi rollback-to savepoint ấy trên connection B do pool cung cấp?

### Bài 20. Log lỗi an toàn

Một ứng dụng muốn ghi vào `import_errors` ngay sau khi INSERT lỗi foreign key. Vì sao phải rollback-to savepoint trước khi ghi log? Nếu log error cũng lỗi, hệ thống nên làm gì?

## 30. Gợi ý lời giải

### Đáp án 1

```sql
BEGIN;
SAVEPOINT before_test;
SELECT 1;
RELEASE SAVEPOINT before_test;
ROLLBACK;
```

`RELEASE` chỉ giải phóng mốc, không commit dữ liệu.

### Đáp án 2

```sql
BEGIN;

INSERT INTO savepoint_lab.test_marks VALUES (11, 'Trước');

SAVEPOINT before_optional;
INSERT INTO savepoint_lab.test_marks VALUES (12, 'Bị hủy');
ROLLBACK TO SAVEPOINT before_optional;

INSERT INTO savepoint_lab.test_marks VALUES (13, 'Sau mốc');

SELECT mark_id, note
FROM savepoint_lab.test_marks
WHERE mark_id IN (11, 12, 13)
ORDER BY mark_id;

ROLLBACK;
```

Trước rollback cuối, kết quả có mark 11 và 13, không có mark 12. Sau rollback cuối, nếu chúng chưa có trước đó thì không còn.

### Đáp án 3

```sql
BEGIN;
SAVEPOINT before_duplicate;

-- Chạy riêng để quan sát lỗi 23505:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

Sau khi nhận lỗi:

```sql
ROLLBACK TO SAVEPOINT before_duplicate;
SELECT COUNT(*) FROM savepoint_lab.import_records;
RELEASE SAVEPOINT before_duplicate;
ROLLBACK;
```

SELECT chạy được trở lại vì transaction đã được phục hồi về savepoint.

### Đáp án 4

```sql
BEGIN;
-- Lệnh sau lỗi 23505 nếu dup-A đã tồn tại:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

Sau lỗi, SELECT không tiếp tục bình thường và có thể trả `25P02`. Không có mốc để rollback-to; gọi `ROLLBACK;` để kết thúc transaction.

### Đáp án 5

```sql
BEGIN;
SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (21, 'Tạm');
RELEASE SAVEPOINT s;
ROLLBACK;
```

Mark 21 bị hủy vì release không phải commit.

### Đáp án 6

```sql
BEGIN;
SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (31, 'Đầu');
ROLLBACK TO SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (32, 'Sau');
ROLLBACK TO SAVEPOINT s;
RELEASE SAVEPOINT s;
ROLLBACK;
```

`s` vẫn tồn tại sau mỗi lần `ROLLBACK TO` cho đến khi được release; mark 31 và 32 đều bị hủy.

### Đáp án 7

```sql
BEGIN;
SAVEPOINT s1;
INSERT INTO savepoint_lab.test_marks VALUES (41, 'A');
SAVEPOINT s2;
INSERT INTO savepoint_lab.test_marks VALUES (42, 'B');
SAVEPOINT s3;
INSERT INTO savepoint_lab.test_marks VALUES (43, 'C');
ROLLBACK TO SAVEPOINT s2;
SELECT mark_id FROM savepoint_lab.test_marks
WHERE mark_id IN (41,42,43);
ROLLBACK;
```

Chỉ mark 41 còn trước rollback toàn transaction; `s3` bị loại, `s1` và `s2` còn.

### Đáp án 8

PostgreSQL ưu tiên `checkpoint` mới nhất; khi release mốc mới, mốc cũ có thể dùng lại. Tránh phụ thuộc tên trùng trong code có nhiều tầng.

### Đáp án 9

Hai hàng hợp lệ `new-X`, `new-Y` được chấp nhận nếu không trùng với dữ liệu có sẵn; `dup-A` bị từ chối vì unique, `bad-ref` vì foreign key. Transaction vẫn phải được commit cuối cùng để những hàng được chấp nhận tồn tại bền vững.

### Đáp án 10

| SQLSTATE | Nghĩa | Phản ứng gợi ý |
| --- | --- | --- |
| `23505` | Unique violation | Nếu thực sự dự kiến, có thể xử lý `ON CONFLICT`/rollback-to. |
| `23503` | Foreign key violation | Xem quan hệ thiếu và policy; có thể từ chối hàng staging. |
| `23514` | Check violation | Dữ liệu vi phạm bất biến; thường không được bỏ qua mù. |
| `25P02` | Transaction already aborted | Tìm lỗi gốc, rollback-to hoặc rollback toàn transaction. |
| `40001` | Serialization failure | Retry toàn transaction theo chính sách. |
| `40P01` | Deadlock detected | Retry toàn transaction theo chính sách. |

### Đáp án 11

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1)
ON CONFLICT (source_key) DO NOTHING;
```

Unique conflict phù hợp đã được xử lý, không cần savepoint chỉ để bắt trường hợp đó. Câu lệnh không tự xử lý lỗi foreign key của một hàng mới trỏ 999.

### Đáp án 12

```sql
DO $$
DECLARE
    x integer := 1;
BEGIN
    BEGIN
        x := 2;
        PERFORM 1 / 0;
    EXCEPTION WHEN division_by_zero THEN
        RAISE NOTICE 'x=%', x;
    END;
END;
$$;
```

Biến có giá trị 2; các thay đổi database trong phần khối có lỗi đã rollback theo subtransaction. Phải phân biệt trạng thái biến với trạng thái các hàng.

### Đáp án 13

```java
connection.setAutoCommit(false);
Savepoint savepoint = connection.setSavepoint();

try {
    // Execute optional SQL with this connection.
    connection.releaseSavepoint(savepoint);
} catch (SQLException error) {
    connection.rollback(savepoint);
    connection.releaseSavepoint(savepoint);
    // Continue only if this error is explicitly recoverable.
}

// The outer service owns connection.commit() or connection.rollback().
```

Đây là khung mô tả API; code production phải phân loại lỗi và bảo đảm rollback toàn transaction khi lỗi bất ngờ, như ví dụ đầy đủ ở phần 15.

### Đáp án 14

FK `DEFERRABLE INITIALLY DEFERRED` có thể chỉ được kiểm tra ở thời điểm muộn. Gọi `SET CONSTRAINTS ALL IMMEDIATE` khi savepoint còn tồn tại để buộc kiểm tra, nếu có lỗi thì `ROLLBACK TO SAVEPOINT`.

### Đáp án 15

Không. Sequence/identity không được hứa hoàn nguyên sau rollback-to, nên số ID có thể nhảy.

### Đáp án 16

Order và order_item là một nhóm bắt buộc, cần rollback toàn bộ đơn vị công việc nếu một phần thất bại. Savepoint có thể bao phần **thống kê tùy chọn**; nếu bước thống kê lỗi thì rollback-to bước đó rồi tiếp tục khi policy cho phép.

### Đáp án 17

Không. Với `40001`, cần retry toàn transaction và đọc lại dữ liệu/ra quyết định lại theo một transaction mới; không dựa vào kết quả đọc cũ sau savepoint.

### Đáp án 18

Số dư sau commit là account 1 = 900.00, account 2 = 550.00, account 3 = 150.00; tổng 1600.00. Chỉ request `transfer-A` và `transfer-B` được lưu.

### Đáp án 19

Savepoint gắn với transaction của connection A, không phải một đối tượng global của database hoặc JVM. Connection B có transaction khác nên không thể rollback về mốc của A.

### Đáp án 20

Phải `ROLLBACK TO SAVEPOINT` trước để transaction thoát trạng thái aborted, rồi mới ghi `import_errors`. Nếu ghi log lỗi cũng gặp lỗi, cần xử lý theo policy của transaction ngoài: thường rollback toàn bộ hoặc chuyển sang cơ chế ghi lỗi bên ngoài transaction theo thiết kế an toàn. Không được âm thầm giả vờ đã lưu log.

## 31. Checklist trước khi dùng SAVEPOINT trong ứng dụng

1. **Ranh giới nghiệp vụ:** bước được rollback có thực sự độc lập với phần đã thành công không?
2. **Transaction scope:** có chắc tất cả statement đang dùng cùng connection và transaction?
3. **Mốc đặt trước lỗi:** savepoint đã được tạo trước mọi statement rủi ro chưa?
4. **Recovery đúng thứ tự:** khi có lỗi SQL, rollback-to trước khi gửi DML tiếp theo.
5. **SQLSTATE:** có xác định chính xác nhóm lỗi được phép xử lý từng phần?
6. **Invariant:** sau rollback-to, tiền/tồn kho/quan hệ dữ liệu còn đúng không?
7. **Mốc lồng nhau:** rollback tới mốc cũ có xóa mốc mà tầng khác còn cần không?
8. **Release vs commit:** tầng code nào có quyền commit transaction ngoài?
9. **Constraint timing:** có lỗi deferred có thể chỉ xuất hiện ở COMMIT không?
10. **Sequence/gap:** có tránh giả định ID liên tục hoặc rollback external side effects không?
11. **Concurrency:** deadlock/serialization failure có đường retry toàn transaction không?
12. **Connection pool:** code có trả connection về pool sau khi transaction đã kết thúc/rollback đúng không?
13. **Observability:** có log batch ID, row ID, SQLSTATE và kết quả commit cuối cùng?
14. **Bulk performance:** savepoint mỗi dòng có cần thiết hay nên dùng staging/ON CONFLICT?
15. **Client behavior:** GUI/psql/framework có tự dừng hoặc tự rollback khi lỗi không?
16. **Kiểm thử:** đã thử cả trường hợp thành công, lỗi dự kiến, lỗi bất ngờ và commit thất bại chưa?

## 32. Tổng kết

Trong PostgreSQL, `SAVEPOINT`, `ROLLBACK TO SAVEPOINT` và `RELEASE SAVEPOINT` giúp ứng dụng **xử lý thất bại của một bước mà không nhất thiết phải hủy cả transaction**:

- **`SAVEPOINT s`** tạo mốc trước một nhóm thao tác có thể cần phục hồi.
- **`ROLLBACK TO SAVEPOINT s`** hủy những thay đổi có thể rollback sau mốc, phục hồi transaction khỏi lỗi trong phạm vi thích hợp và **giữ mốc `s` để có thể dùng tiếp**.
- **`RELEASE SAVEPOINT s`** giải phóng mốc khi không còn cần rollback riêng; nó **không commit**.
- Các mốc có thể lồng nhau; rollback hoặc release mốc cũ có thể loại những mốc được tạo sau nó. PostgreSQL cho phép mốc trùng tên nhưng cần dùng thận trọng.
- Một SQL error thông thường trong transaction có thể khiến những SQL tiếp theo trả **`25P02`** cho đến khi transaction được phục hồi hoặc rollback. Bắt exception ở Java một mình không đủ.
- **PL/pgSQL `EXCEPTION`** sử dụng subtransaction để xử lý lỗi theo phạm vi khối; **JDBC `Savepoint`** cung cấp API tương ứng ở tầng ứng dụng.
- **`INSERT ... ON CONFLICT`** có thể đơn giản hơn cho lỗi unique trùng lặp dự kiến; staging/validation theo tập phù hợp với batch lớn.
- Savepoint không bảo đảm rollback sequence, email, HTTP call, không thay thế kiểm soát concurrency và không tự cho phép partial commit độc lập.
- Với lỗi **`40001`/`40P01`**, thường phải retry toàn bộ transaction; với constraint deferred cần hiểu khi nào lỗi được phát hiện trước `COMMIT`.

Câu hỏi quan trọng nhất khi thiết kế là: **“Nếu bước này thất bại và tôi quay về savepoint, phần công việc còn lại có vẫn đúng về nghiệp vụ và có thể commit an toàn không?”** Nếu không thể trả lời chắc chắn, rollback toàn transaction thường là lựa chọn đúng hơn việc cố giữ lại dữ liệu từng phần.
