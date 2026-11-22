# Tính nguyên tử, nhất quán, cô lập và bền vững trong PostgreSQL

## 1. Một lần chuyển tiền phải thành công như một đơn vị công việc

Giả sử ứng dụng ngân hàng có hai tài khoản:

| Tài khoản | Chủ tài khoản | Số dư ban đầu |
| --- | --- | ---: |
| 101 | An | 500.00 |
| 202 | Bình | 200.00 |

An muốn chuyển 100.00 cho Bình. Ứng dụng phải thực hiện ba thay đổi liên quan:

1. Trừ 100.00 khỏi tài khoản của An.
2. Cộng 100.00 vào tài khoản của Bình.
3. Ghi một bản ghi lịch sử chuyển tiền.

Nếu hệ thống chỉ thực hiện bước 1 rồi lỗi mạng trước bước 2, dữ liệu sẽ sai: tài khoản nguồn đã mất tiền nhưng tài khoản đích chưa nhận. Nếu cả hai bước hoàn thành mà lịch sử giao dịch không được ghi, báo cáo và đối soát có thể không nhất quán. Nếu hai người cùng rút tiền từ một tài khoản tại cùng thời điểm, một cách cập nhật thiếu an toàn có thể cho phép chi vượt số dư.

PostgreSQL giải quyết phần lớn những vấn đề này bằng **giao dịch (*transaction*)**. Một giao dịch nhóm các thao tác SQL liên quan thành một đơn vị xử lý.

Bốn tính chất thường được viết tắt thành **ACID**:

| Chữ | Tên tiếng Anh | Ý nghĩa thực hành |
| --- | --- | --- |
| **A** | **Atomicity** – Tính nguyên tử | Hoặc các thay đổi thuộc giao dịch được xác nhận như một đơn vị, hoặc không có thay đổi nào của giao dịch được giữ lại |
| **C** | **Consistency** – Tính nhất quán | Giao dịch cần chuyển dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ khác, tuân thủ các ràng buộc và bất biến nghiệp vụ |
| **I** | **Isolation** – Tính cô lập | Các giao dịch chạy đồng thời được kiểm soát để hạn chế/loại bỏ những tương tác không mong muốn theo mức cô lập được chọn |
| **D** | **Durability** – Tính bền vững | Sau khi `COMMIT` được xác nhận theo cấu hình bền vững thích hợp, thay đổi có thể được phục hồi qua sự cố theo cơ chế lưu trữ/WAL |

ACID không có nghĩa “mọi lệnh SQL luôn đúng”, “mọi ứng dụng tự động không có race condition” hay “không bao giờ mất dữ liệu trong mọi thảm họa”. Mỗi chữ có phạm vi bảo đảm, điều kiện cấu hình và trách nhiệm thiết kế riêng.

> **Tư duy nền tảng:** giao dịch đảm bảo một đơn vị công việc của database có biên giới rõ ràng. Nhưng ứng dụng vẫn phải định nghĩa đúng những gì cần thay đổi, những gì là trạng thái hợp lệ và cách xử lý xung đột đồng thời.

## 2. Mục tiêu sau bài học

Sau bài này, bạn có thể:

1. Giải thích bốn tính chất ACID bằng những tình huống nghiệp vụ cụ thể.
2. Dùng `BEGIN`, `COMMIT` và `ROLLBACK` để quản lý giao dịch PostgreSQL.
3. Viết một phép chuyển tiền có kiểm tra thành công từng bước.
4. Phân biệt lỗi câu lệnh, lỗi giao dịch và cơ chế `SAVEPOINT`.
5. Phân biệt ràng buộc database với bất biến nghiệp vụ không thể tự bảo đảm bằng một `CHECK` đơn giản.
6. Giải thích MVCC và hành vi đọc dữ liệu của nhiều phiên đồng thời.
7. Phân biệt `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` của PostgreSQL.
8. Hiểu các bất thường như dirty read, nonrepeatable read, phantom read, lost update và write skew.
9. Biết khi nào cần khóa hàng, điều kiện cập nhật nguyên tử hoặc retry toàn giao dịch.
10. Hiểu vai trò của WAL, `fsync`, `synchronous_commit`, sao lưu và replication đối với tính bền vững.
11. Áp dụng giao dịch trong Java/JDBC và nhận biết giới hạn khi thao tác vượt ra ngoài một database.
12. Kiểm tra transaction còn mở, khóa chờ và các thói quen vận hành gây rủi ro.

## 3. Thiết lập bộ dữ liệu thực hành

Chạy các ví dụ trong một **database thử nghiệm**. Một số phần yêu cầu mở **hai kết nối độc lập** hoặc cố ý tạo lỗi/rollback; không thực hiện trực tiếp trên dữ liệu production.

### 3.1. Tạo schema và bảng tài khoản

```sql
CREATE SCHEMA IF NOT EXISTS acid_lab;

CREATE TABLE acid_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0)
);
```

Các quyết định quan trọng:

- `account_id` là khóa chính, xác định tài khoản duy nhất.
- `balance` dùng `numeric(14,2)` để mô tả số tiền thập phân, không dùng `float`.
- `NOT NULL` không cho phép thiếu số dư.
- `CHECK (balance >= 0)` ngăn một hàng có số dư âm theo quy tắc bảng.
- Các ràng buộc bảo vệ từng phần dữ liệu, nhưng chưa thể hiện toàn bộ quy tắc chuyển tiền.

Nạp dữ liệu:

```sql
INSERT INTO acid_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

Có tài khoản thứ ba để luyện tình huống nhiều giao dịch đồng thời.

### 3.2. Bảng nhật ký chuyển tiền

```sql
CREATE TABLE acid_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    from_account_id bigint NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    CONSTRAINT chk_distinct_accounts
        CHECK (from_account_id <> to_account_id)
);
```

Bảng `transfers` lưu lịch sử, còn `accounts` lưu số dư. Hai bảng phải được cập nhật **cùng một giao dịch** nếu quy tắc nghiệp vụ yêu cầu chúng nhất quán.

Để xem số dư:

```sql
SELECT account_id, owner_name, balance
FROM acid_lab.accounts
ORDER BY account_id;
```

Với dữ liệu mới nạp, tổng số dư là 800.00:

```sql
SELECT SUM(balance) AS total_balance
FROM acid_lab.accounts;
```

**Lưu ý về thử nghiệm:** các ví dụ sau có chỗ dùng `ROLLBACK` nhằm giữ dữ liệu mẫu, có chỗ dùng `COMMIT` để minh họa trạng thái được xác nhận. Nếu muốn so kết quả đúng như ví dụ ban đầu, hãy dùng một database thử nghiệm mới hoặc chủ động khôi phục dữ liệu trước mỗi kịch bản.

## 4. Vòng đời của một giao dịch PostgreSQL

Một giao dịch tường minh có dạng:

```sql
BEGIN;

-- Một hoặc nhiều lệnh SQL thuộc cùng giao dịch.
UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

COMMIT;
```

Hoặc, để hủy những thay đổi chưa commit:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

ROLLBACK;
```

Các lệnh quan trọng:

| Lệnh | Tác dụng |
| --- | --- |
| `BEGIN` hoặc `START TRANSACTION` | Bắt đầu giao dịch tường minh |
| `COMMIT` | Yêu cầu xác nhận giao dịch |
| `ROLLBACK` | Hủy những thay đổi chưa được commit của giao dịch |
| `SAVEPOINT name` | Đặt mốc phục hồi một phần trong giao dịch |
| `ROLLBACK TO SAVEPOINT name` | Quay lại mốc mà không hủy toàn bộ giao dịch |
| `RELEASE SAVEPOINT name` | Bỏ mốc savepoint không còn cần |
| `SET TRANSACTION ISOLATION LEVEL ...` | Chỉ định mức cô lập khi còn hợp lệ để thiết lập |

### 4.1. Khi không viết `BEGIN` thì sao?

Với nhiều công cụ và driver ở chế độ **autocommit**, một lệnh SQL riêng lẻ được xử lý trong giao dịch riêng và được commit khi thành công. Ví dụ:

```sql
UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 202;
```

Nếu công cụ chạy từng lệnh bằng autocommit, **hai UPDATE này không tạo thành một giao dịch chung**. Nếu lệnh thứ hai lỗi, lệnh thứ nhất có thể đã commit.

Do đó, không thể suy ra “vì hai câu SQL được đặt cạnh nhau trong một tệp” nên chúng tự động nguyên tử cùng nhau.

### 4.2. `COMMIT` khác với lệnh `UPDATE` chạy thành công

Một câu `UPDATE` báo cập nhật một hàng nghĩa là câu lệnh đã chạy thành công **trong transaction hiện tại**. Điều đó không có nghĩa transaction đã được commit.

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101
RETURNING account_id, balance;

-- Kết quả ở cùng phiên đã nhìn thấy thay đổi.
ROLLBACK;
```

Sau `ROLLBACK`, thay đổi 50.00 không được giữ lại.

### 4.3. Transaction thuộc về một kết nối

Một transaction tường minh gắn với **một session/kết nối PostgreSQL**. Không thể mở `BEGIN` trên kết nối A, rồi kỳ vọng một lệnh `UPDATE` chạy trên kết nối B tự nằm trong cùng transaction đó.

Đây là điều rất quan trọng khi ứng dụng dùng **connection pool**, nhiều luồng Java hoặc nhiều dịch vụ. Toàn bộ các thao tác cần nguyên tử cùng nhau phải được thực hiện trong **phạm vi giao dịch được quản lý đúng**.

### 4.4. Giao dịch có thể thất bại ở lúc `COMMIT`

Không phải lệnh `UPDATE` nào chạy thành công cũng bảo đảm `COMMIT` sẽ thành công. Một số lỗi chỉ được phát hiện ở cuối transaction, ví dụ:

- Vi phạm ràng buộc `DEFERRABLE` được trì hoãn đến `COMMIT`.
- Lỗi serialization khi các giao dịch `SERIALIZABLE` xung đột.
- Một số tình huống lỗi I/O hoặc mất kết nối khi xác nhận.

Ứng dụng phải xử lý **kết quả COMMIT** chứ không chỉ kết quả của các lệnh SQL trước đó.

## 5. Atomicity: hoặc toàn bộ, hoặc không có gì

**Tính nguyên tử** yêu cầu các thay đổi của một transaction được nhìn nhận như **một đơn vị** khi quyết định commit hay rollback.

Với chuyển tiền, ba thay đổi:

```text
Trừ tiền nguồn
     |
     v
Cộng tiền đích
     |
     v
Ghi lịch sử chuyển tiền
     |
     +--> COMMIT: xác nhận các thay đổi cùng nhau
     |
     +--> ROLLBACK: không giữ các thay đổi của transaction
```

### 5.1. Ví dụ đơn giản dùng một transaction

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 202;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, 100.00);

-- Dùng ROLLBACK trong bài thực hành để không làm đổi dữ liệu mẫu.
ROLLBACK;
```

Ba thao tác trên cùng transaction, nên `ROLLBACK` hủy cả ba.

**Nhưng ví dụ này vẫn chưa đủ an toàn cho production.** Nếu mã tài khoản không tồn tại, `UPDATE` có thể ảnh hưởng **0 hàng** mà không tự báo lỗi. Một transaction có thể commit dù điều kiện nghiệp vụ chưa được thực hiện, nếu lập trình viên không kiểm tra.

### 5.2. Chuyển tiền có kiểm tra từng bước bằng PL/pgSQL

Ví dụ dưới đây thực hiện giao dịch và cố ý rollback khi thực hành:

```sql
BEGIN;

DO $transfer$
DECLARE
    v_amount numeric(14,2) := 100.00;
BEGIN
    -- Bước 1: trừ tiền nguồn, không cho số dư xuống dưới 0.
    UPDATE acid_lab.accounts
    SET balance = balance - v_amount
    WHERE account_id = 101
      AND balance >= v_amount;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Tài khoản nguồn không tồn tại hoặc không đủ tiền';
    END IF;

    -- Bước 2: cộng tiền vào đúng tài khoản đích.
    UPDATE acid_lab.accounts
    SET balance = balance + v_amount
    WHERE account_id = 202;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Tài khoản đích không tồn tại';
    END IF;

    -- Bước 3: lưu lịch sử.
    INSERT INTO acid_lab.transfers
        (from_account_id, to_account_id, amount)
    VALUES
        (101, 202, v_amount);
END;
$transfer$;

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

ROLLBACK;
```

Trong ngôn ngữ PL/pgSQL, biến `FOUND` sau `UPDATE` phản ánh có hàng nào được cập nhật không. Nếu trừ tiền hoặc cộng tiền không cập nhật được hàng cần thiết, `RAISE EXCEPTION` làm câu lệnh thất bại và transaction rơi vào trạng thái lỗi; ứng dụng/phiên phải rollback thay vì commit như thể thành công.

Nếu tất cả bước hợp lệ và bạn thay `ROLLBACK` bằng `COMMIT`:

- An từ 500.00 còn 400.00.
- Bình từ 200.00 thành 300.00.
- Bảng `transfers` thêm một hàng.
- Tổng số dư hai tài khoản vẫn bằng 700.00.

**Cần bảo đảm ứng dụng không gửi cùng yêu cầu chuyển tiền nhiều lần ngoài ý muốn.** Một transaction nguyên tử không tự có khả năng nhận ra hai yêu cầu HTTP trùng nhau; phần về idempotency sẽ giải thích thêm.

### 5.3. Điều kiện `balance >= amount` giải quyết điều gì?

Giả sử tài khoản nguồn chỉ có 100.00, hai yêu cầu cùng muốn chuyển 80.00.

Nếu ứng dụng đọc số dư rồi tự tính:

```text
SELECT balance --> 100
Ứng dụng tự tính --> 20
UPDATE balance = 20
```

cả hai yêu cầu có thể đều đọc 100 trước khi ghi, rồi dẫn tới lỗi logic, đặc biệt nếu phần ghi không có điều kiện và cơ chế khóa phù hợp.

Một dạng an toàn hơn:

```sql
UPDATE acid_lab.accounts
SET balance = balance - 80.00
WHERE account_id = 101
  AND balance >= 80.00
RETURNING balance;
```

PostgreSQL kiểm tra điều kiện và thay đổi hàng **trong một statement**. Khi nhiều transaction cạnh tranh trên cùng hàng, cơ chế khóa hàng và đánh giá lại điều kiện theo mức cô lập phù hợp có thể giúp ngăn trường hợp trừ vượt số dư. Ứng dụng vẫn phải kiểm tra **có đúng một hàng được trả về hay không**.

### 5.4. Atomicity không làm câu SQL tự đúng nghiệp vụ

Một transaction như sau vẫn có thể commit:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

-- Lập trình viên quên cộng tài khoản đích.
COMMIT;
```

Database không thể tự biết rằng ứng dụng “đáng lẽ còn một bước nữa”. Tính nguyên tử bảo đảm **những câu lệnh được thực hiện trong transaction** commit/rollback cùng nhau; nó không tự thêm những bước bị bỏ quên.

## 6. Atomicity khi câu lệnh xảy ra lỗi

### 6.1. Lỗi ràng buộc làm giao dịch không thể tiếp tục bình thường

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 5.00
WHERE account_id = 101;

-- Vi phạm CHECK (balance >= 0).
UPDATE acid_lab.accounts
SET balance = -1.00
WHERE account_id = 202;

-- Trong cùng transaction, các câu SQL tiếp theo thường báo:
-- current transaction is aborted, commands ignored ...
SELECT * FROM acid_lab.accounts;

ROLLBACK;
```

Sau lỗi của câu `UPDATE` thứ hai, transaction ở trạng thái thất bại. Không thể tiếp tục các lệnh bình thường rồi commit thành công chỉ bằng cách bỏ qua lỗi.

`ROLLBACK` kết thúc transaction và hủy cả thay đổi `+5.00` trước đó.

### 6.2. `ROLLBACK` và `COMMIT` không phải hai tùy chọn tùy tiện

Ứng dụng nên:

- `COMMIT` khi **mọi điều kiện hoàn tất thành công** và transaction không ở trạng thái lỗi.
- `ROLLBACK` khi có lỗi hoặc không đạt yêu cầu nghiệp vụ.
- Không phát lệnh `COMMIT` một cách máy móc trong khối `finally` mà không biết các bước trước đó thành công hay thất bại.

Nếu connection bị đứt khi gửi `COMMIT`, ứng dụng thậm chí có thể rơi vào tình trạng **chưa biết transaction đã commit trên server hay chưa**. Đây là lý do nghiệp vụ quan trọng cần idempotency và khả năng đối soát, thay vì tự giả định “mất kết nối nghĩa là chưa commit”.

## 7. `SAVEPOINT`: hoàn tác một phần trong transaction

`SAVEPOINT` tạo mốc để rollback các thay đổi sau mốc đó mà vẫn giữ những thay đổi hợp lệ trước mốc.

Ví dụ:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

SAVEPOINT before_optional_step;

-- Thao tác tùy chọn bị lỗi vì CHECK:
UPDATE acid_lab.accounts
SET balance = -5.00
WHERE account_id = 202;

-- Sau lỗi, đưa transaction về savepoint:
ROLLBACK TO SAVEPOINT before_optional_step;

-- Giờ có thể chạy tiếp:
SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

-- Giữ dữ liệu lab ban đầu.
ROLLBACK;
```

Ở ví dụ này:

- Thay đổi `+10.00` xảy ra **trước** savepoint.
- Lệnh sai xảy ra **sau** savepoint.
- `ROLLBACK TO SAVEPOINT` phục hồi về trạng thái sau thay đổi `+10.00`.
- `ROLLBACK` cuối cùng hủy toàn transaction, nên bộ dữ liệu thử nghiệm không đổi.

Trong một quy trình thật, có thể dùng `RELEASE SAVEPOINT` để bỏ mốc khi không cần. Tuy nhiên, **savepoint không tạo một transaction độc lập được commit riêng**: nếu transaction cha rollback thì những thay đổi đã “được giữ qua savepoint” cũng bị hủy.

### 7.1. Không cố dùng savepoint để che lỗi nghiệp vụ bắt buộc

Với chuyển tiền, không được xem việc **cộng tiền vào tài khoản đích** là bước tùy chọn. Nếu bước đó lỗi, phải hủy cả giao dịch chuyển tiền. Savepoint phù hợp cho một thao tác thực sự có thể bỏ qua theo yêu cầu nghiệp vụ, ví dụ một ghi chú phụ không bắt buộc, chứ không phải cách bỏ qua vi phạm tính nhất quán.

### 7.2. Phân biệt rollback của statement và rollback của transaction

PostgreSQL bảo đảm một câu lệnh dữ liệu thông thường không để lại **thay đổi bảng từng phần** khi câu lệnh thất bại. Nhưng nếu lỗi xảy ra bên trong transaction tường minh, transaction có thể trở nên aborted cho đến khi rollback hoặc rollback về savepoint phù hợp.

Trong ứng dụng có transaction manager, việc bắt ngoại lệ không tự làm connection trở lại trạng thái khỏe mạnh; phải phối hợp cơ chế rollback đúng.

## 8. Một số thao tác không tuân theo rollback theo cách người mới học kỳ vọng

Atomicity áp dụng cho **thay đổi dữ liệu transactional**, nhưng không nên hiểu rằng *mọi* tác dụng phụ hoặc bộ đếm đều quay về như cũ.

### 8.1. Sequence không hoàn lại số đã cấp

PostgreSQL dùng sequence, chẳng hạn qua `GENERATED ... AS IDENTITY`, để cấp ID. Giá trị đã lấy từ sequence **không được trả lại** chỉ vì transaction rollback.

Ví dụ bảng `transfers` dùng identity:

```sql
BEGIN;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES (101, 202, 1.00)
RETURNING transfer_id;

ROLLBACK;
```

Hàng vừa chèn bị hủy. Nhưng số identity đã được cấp có thể **không được dùng lại**, khiến ID xuất hiện khoảng trống.

**Không dùng dãy ID như bằng chứng rằng không có giao dịch rollback** và không yêu cầu ID phải liên tiếp. Nếu nghiệp vụ cần số chứng từ liên tục theo quy định, phải thiết kế cơ chế cấp số riêng với yêu cầu tuân thủ rõ ràng.

### 8.2. Nhiều câu DDL có thể rollback, nhưng không phải tất cả

PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác:

```sql
BEGIN;

CREATE TABLE acid_lab.temporary_demo (
    id integer PRIMARY KEY
);

ROLLBACK;
```

Sau `ROLLBACK`, bảng vừa tạo trong giao dịch không được giữ lại.

Nhưng một số câu lệnh như `CREATE DATABASE`, `VACUUM` hoặc `CREATE INDEX CONCURRENTLY` **không được chạy trong transaction block tường minh**. Không suy rộng rằng mọi thay đổi cấu trúc/quản trị hệ thống đều rollback như một `INSERT`.

### 8.3. Tác dụng ngoài database không tự rollback

Nếu một transaction gửi email, gọi API thanh toán hoặc ghi file qua hệ thống bên ngoài trước khi commit, `ROLLBACK` của PostgreSQL **không tự thu hồi email**, đảo ngược API hoặc xóa file đó.

Giao dịch PostgreSQL bảo đảm phạm vi mà database quản lý. Những side effect bên ngoài phải được phối hợp qua thiết kế hệ thống, ví dụ **transactional outbox**, idempotency hoặc các bước bù trừ (*compensating actions*).

## 9. Consistency: trạng thái dữ liệu hợp lệ trước và sau giao dịch

**Tính nhất quán** không đơn giản là “mọi người thấy cùng dữ liệu ở mọi thời điểm”. Trong ACID, **Consistency** nói về việc tuân thủ **ràng buộc và bất biến** của dữ liệu khi transaction thành công.

Một số ví dụ bất biến:

- Mỗi tài khoản có khóa chính duy nhất.
- Số dư không âm.
- Giao dịch chuyển tiền có số tiền dương.
- Tài khoản nguồn/đích được tham chiếu thật sự tồn tại.
- Trong một phép chuyển nội bộ, tổng tiền nguồn + đích phải không thay đổi.
- Một đơn hàng đã thanh toán không được xử lý thành một trạng thái trái quy tắc.

PostgreSQL giúp thực thi nhiều bất biến bằng:

- Kiểu dữ liệu chính xác.
- `PRIMARY KEY`.
- `UNIQUE`.
- `NOT NULL`.
- `CHECK`.
- `FOREIGN KEY`.
- Ràng buộc loại trừ `EXCLUDE` trong các bài toán phù hợp.
- Cơ chế khóa, trigger hoặc logic giao dịch khi một quy tắc không diễn đạt được bằng ràng buộc đơn giản.

### 9.1. Ràng buộc `CHECK` ngăn số dư âm

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = -100.00
WHERE account_id = 101;

-- PostgreSQL báo vi phạm CHECK.
ROLLBACK;
```

`CHECK (balance >= 0)` ngăn một hàng sai được lưu thành công. Nhưng nó không tự biết giữa hai tài khoản cần có phép cộng/trừ cân bằng.

### 9.2. Ràng buộc `FOREIGN KEY` ngăn tham chiếu không tồn tại

```sql
BEGIN;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 999999, 10.00);

-- Vi phạm khóa ngoại to_account_id.
ROLLBACK;
```

Nếu tài khoản 999999 không tồn tại, PostgreSQL từ chối dòng lịch sử chuyển tiền tham chiếu đến nó.

### 9.3. Không thể lấy một `CHECK` trên từng hàng để bảo đảm mọi bất biến nhiều bảng

Một quy tắc kiểu:

```text
SUM(balance của tất cả tài khoản)
phải bằng
tổng số tiền đã được hệ thống ghi nhận có căn cứ.
```

liên quan nhiều hàng và có thể nhiều bảng. Bạn không thể coi `CHECK (balance >= 0)` là đã bảo vệ quy tắc tổng đó.

Thậm chí một transaction có thể tự cập nhật sai số tiền nhưng vẫn thỏa mọi `CHECK` đơn lẻ.

Để bảo vệ bất biến nhiều bảng, có thể cần:

- Logic ứng dụng trong **một transaction**.
- Điều kiện cập nhật nguyên tử.
- Khóa hàng/khóa nghiệp vụ thích hợp.
- Mức cô lập phù hợp, đôi khi `SERIALIZABLE`.
- Trigger hoặc thiết kế dữ liệu phát sinh ít trạng thái dư thừa.
- Quy trình đối soát để phát hiện sai khác do hệ thống bên ngoài.

### 9.4. ACID Consistency phụ thuộc quy tắc được khai báo và thực thi

PostgreSQL không biết định nghĩa “một đơn hàng hợp lệ” của doanh nghiệp nếu quy tắc đó không nằm trong schema hoặc logic được chạy.

Hai tình huống khác nhau:

- **Database từ chối** một giá trị vi phạm `CHECK`/`FK`: ràng buộc được bảo vệ.
- **Ứng dụng quên** một bước đối soát nhưng vẫn commit những thay đổi hợp lệ theo schema: nghiệp vụ có thể sai dù database không báo lỗi.

Vì thế, **Consistency là trách nhiệm chung của mô hình dữ liệu, transaction và ứng dụng**, không chỉ là một công tắc cấu hình.

## 10. Ràng buộc có thể trì hoãn đến `COMMIT`

PostgreSQL cho phép **một số loại ràng buộc** được khai báo `DEFERRABLE`, nghĩa là thời điểm kiểm tra có thể được chuyển đến cuối transaction.

Ví dụ:

```sql
CREATE TABLE acid_lab.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE acid_lab.employees (
    employee_id integer PRIMARY KEY,
    employee_name text NOT NULL,
    department_id integer NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES acid_lab.departments(department_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Sau đó thử một transaction:

```sql
BEGIN;

SET CONSTRAINTS fk_employee_department DEFERRED;

-- Tạm thời tham chiếu phòng ban 50 chưa tồn tại:
INSERT INTO acid_lab.employees
    (employee_id, employee_name, department_id)
VALUES
    (1, 'An', 50);

-- Tạo phòng ban đó trong cùng transaction:
INSERT INTO acid_lab.departments
    (department_id, department_name)
VALUES
    (50, 'Research');

-- Trước COMMIT, FK đã được thỏa.
ROLLBACK;
```

Dùng `ROLLBACK` để giữ dữ liệu lab. Nếu thay bằng `COMMIT` và mọi ràng buộc đều hợp lệ ở thời điểm kiểm tra, giao dịch có thể thành công.

**Lưu ý quan trọng:**

- Chỉ những ràng buộc **được khai báo DEFERRABLE** mới có thể được trì hoãn.
- `CHECK` và `NOT NULL` không chuyển thành deferred theo cách này trong PostgreSQL.
- Với FK, `NO ACTION` có thể trì hoãn khi ràng buộc là DEFERRABLE; `RESTRICT` có đặc tính kiểm tra ngay, không tương đương với NO ACTION deferred.
- Khi ràng buộc deferred thất bại ở `COMMIT`, transaction không được xác nhận.

Ví dụ này cho thấy **một trạng thái trung gian** trong transaction có thể chưa thỏa FK deferred, nhưng trạng thái được commit phải thỏa quy tắc cuối cùng. Không dùng deferred constraints nếu ứng dụng không kiểm soát được những trạng thái trung gian.

## 11. Isolation: vì sao giao dịch đồng thời khó hơn giao dịch đơn lẻ?

Giả sử hai giao dịch cùng làm việc với một bảng. Vấn đề không chỉ là mỗi giao dịch có thể rollback hay commit, mà còn là **mỗi giao dịch nhìn thấy thay đổi của giao dịch kia lúc nào** và **những kết quả cuối có thể tương tác như thế nào**.

Ví dụ:

```text
T1: Đọc số dư 100
T2: Đọc số dư 100
T1: Quyết định rút 80
T2: Quyết định rút 80
T1: Ghi thay đổi
T2: Ghi thay đổi
```

Nếu ứng dụng coi hai lần đọc 100 là bằng chứng độc lập rằng cả hai lượt rút hợp lệ, thiết kế có thể sai.

**Isolation** là tập quy tắc về khả năng quan sát và xung đột giữa những transaction chạy đồng thời. PostgreSQL cung cấp nhiều mức cô lập; mức cao hơn có thể ngăn thêm bất thường nhưng cũng có chi phí và khả năng phải **retry**.

### 11.1. Những bất thường thường được nhắc đến

| Bất thường | Mô tả ngắn |
| --- | --- |
| Dirty read | T1 đọc thay đổi của T2 khi T2 chưa commit |
| Nonrepeatable read | T1 đọc cùng một hàng ở hai thời điểm và thấy giá trị khác do T2 đã commit |
| Phantom read | T1 lặp một truy vấn theo điều kiện và thấy tập hàng phù hợp thay đổi vì T2 commit |
| Lost update | Một cập nhật dựa trên dữ liệu cũ ghi đè hoặc làm mất ý định cập nhật khác |
| Write skew | Hai transaction đọc một bất biến chung, cập nhật **những hàng khác nhau**, và cùng commit thành trạng thái vi phạm bất biến |
| Serialization anomaly | Kết quả chạy đồng thời không tương đương với một thứ tự chạy tuần tự hợp lệ của các transaction |

Không phải mọi bất thường đều xảy ra giống nhau ở mọi mức cô lập; các hệ quản trị cũng có khác biệt so với ví dụ lý thuyết.

### 11.2. PostgreSQL dùng MVCC

**Multi-Version Concurrency Control (MVCC)** giúp PostgreSQL quản lý nhiều phiên bản dữ liệu để các lệnh đọc có thể quan sát một snapshot phù hợp mà không luôn phải chờ mọi giao dịch ghi.

Một cách trực quan:

```text
T1 đang đọc dữ liệu tại snapshot A
                |
                v
    [Giá trị đã commit trước A]

T2 cập nhật cùng hàng
                |
                v
          [Phiên bản mới]
                |
                +-- Chưa COMMIT: T1 không dirty-read phiên bản này
                |
                +-- Đã COMMIT: lần đọc sau của T1 có thấy hay không
                    phụ thuộc isolation level
```

MVCC không có nghĩa transaction không cần khóa. Các câu `UPDATE`, `DELETE` và `SELECT ... FOR UPDATE` vẫn sử dụng cơ chế khóa phù hợp; chúng có thể chờ hoặc phát sinh xung đột.

## 12. Các mức cô lập của PostgreSQL

PostgreSQL công bố bốn tên trong SQL, nhưng `READ UNCOMMITTED` **được xử lý tương tự `READ COMMITTED`**.

| Mức PostgreSQL | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` (hoạt động như READ COMMITTED) | Không | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | Không trong PostgreSQL | Vẫn có thể, như write skew |
| `SERIALIZABLE` | Không | Không | Không | Được ngăn bằng kiểm soát SSI; một transaction có thể phải rollback/retry |

Đây là bảng **khả năng xảy ra**, không có nghĩa mọi lịch thực thi nhất định sẽ tạo bất thường. Cách ứng dụng sử dụng khóa, điều kiện cập nhật và ràng buộc cũng quyết định kết quả thực tế.

### 12.1. Mức mặc định

Trong PostgreSQL, mức cô lập thường mặc định là **`READ COMMITTED`**.

Kiểm tra:

```sql
SHOW default_transaction_isolation;
```

Lệnh đọc cấu hình không tự thay đổi isolation của giao dịch đang chạy.

### 12.2. Thiết lập mức cô lập ngay từ đầu giao dịch

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT account_id, balance
FROM acid_lab.accounts
ORDER BY account_id;

ROLLBACK;
```

Hoặc:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM acid_lab.accounts;

ROLLBACK;
```

Mức cô lập phải được thiết lập **trước khi transaction đã thực hiện những thao tác không cho phép thay đổi isolation**; trong PostgreSQL, `SET TRANSACTION ISOLATION LEVEL` cần thực hiện trước truy vấn hoặc sửa dữ liệu đầu tiên của transaction. Đừng mở transaction, đọc dữ liệu rồi mới kỳ vọng nâng isolation cho những lần đọc đã qua.

### 12.3. Mỗi transaction chọn mức cô lập của nó

Mức isolation không phải một “bật/tắt” áp dụng cho toàn bộ hệ thống theo mong muốn của một request. Nếu một workflow đòi bảo đảm serializable giữa nhiều bên, bạn phải bảo đảm các transaction liên quan cùng tuân thủ mô hình tương ứng; một transaction riêng lẻ ở `SERIALIZABLE` không thể tự làm cho mọi transaction khác được viết theo nghiệp vụ an toàn.

## 13. `READ COMMITTED`: mỗi câu lệnh thường thấy snapshot mới

Ở `READ COMMITTED`, một lệnh `SELECT` thông thường nhìn thấy các thay đổi **đã commit trước khi câu lệnh bắt đầu** theo snapshot của lệnh đó.

Trong cùng transaction, hai lệnh `SELECT` chạy ở thời điểm khác nhau có thể thấy kết quả khác nếu có transaction khác commit giữa chúng.

### 13.1. Thí nghiệm hai phiên: nonrepeatable read

Mở **Session A** và **Session B** bằng hai kết nối `psql` hoặc hai connection riêng.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- Giả sử kết quả ban đầu là 500.00.
```

Giữ Session A đang mở.

**Session B:**

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
```

Trở lại **Session A:**

```sql
SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- Lần đọc này có thể thấy 550.00.

ROLLBACK;
```

Nếu A đọc đầu tiên trước B commit, rồi đọc lại sau B commit, hai lần đọc trong A có thể khác nhau.

**Đó là nonrepeatable read**, không phải dirty read. A chỉ nhìn thấy thay đổi của B **sau khi B đã commit**.

Thí nghiệm này **cố ý thay đổi dữ liệu** ở Session B. Để thử lại với số ban đầu 500.00, hãy thực hiện trong database thử nghiệm mới hoặc hoàn tác có kiểm soát phần thay đổi +50.00 sau khi các session thí nghiệm đã kết thúc.

### 13.2. Read committed không dirty-read

Nếu Session B mới cập nhật mà **chưa commit**, Session A không nhìn thấy giá trị chưa xác nhận đó chỉ bằng `SELECT` thông thường.

PostgreSQL không cung cấp mức dirty read thực sự qua việc chỉ viết `READ UNCOMMITTED`. Trong PostgreSQL, nó có hành vi của `READ COMMITTED`.

### 13.3. Read committed cũng có thể thấy phantom

Giả sử A đếm:

```sql
SELECT COUNT(*)
FROM acid_lab.accounts
WHERE balance >= 200.00;
```

B sau đó chèn một tài khoản hợp lệ hoặc cập nhật tài khoản khiến nó chuyển vào vùng điều kiện và commit. A chạy lại câu `COUNT` trong cùng transaction `READ COMMITTED` có thể thấy số lượng khác.

Đó là một ví dụ **phantom read**: tập hàng thỏa điều kiện thay đổi giữa hai lần đọc.

### 13.4. Snapshot của câu lệnh không có nghĩa toàn bộ transaction ổn định

`READ COMMITTED` phù hợp với nhiều ứng dụng thông thường, nhưng nếu một nghiệp vụ cần đọc nhiều bảng và suy luận trên **một ảnh chụp thống nhất dài xuyên suốt các lệnh**, mức này có thể không đáp ứng đủ.

Đừng chọn mức cô lập dựa trên cảm giác “mặc định chắc chắn an toàn cho mọi báo cáo” mà không xác định những bất biến cần bảo vệ.

## 14. `REPEATABLE READ`: snapshot ổn định hơn

Trong PostgreSQL, transaction ở `REPEATABLE READ` có snapshot ổn định cho các lần đọc thông thường trong transaction, bắt đầu khi snapshot được thiết lập theo quy tắc của PostgreSQL.

### 14.1. Thí nghiệm hai phiên

Bắt đầu từ trạng thái dữ liệu đã biết, ví dụ tài khoản 101 có 500.00.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- 500.00
```

**Session B:**

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
```

**Session A:**

```sql
SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- Trong snapshot của A vẫn là 500.00.

ROLLBACK;
```

Một transaction mới được mở sau đó có thể thấy 550.00.

**Điểm quan trọng:** A phải thực hiện lần đọc xác lập snapshot **trước khi B commit**. Chỉ gửi `BEGIN` rồi không đọc cho đến sau B commit không bảo đảm snapshot của A là trạng thái cũ.

### 14.2. Repeatable Read của PostgreSQL ngăn phantom read

Trong PostgreSQL, `REPEATABLE READ` dựa trên snapshot isolation, nên các truy vấn lặp của transaction không tự nhìn thấy các hàng mới được transaction khác commit sau khi snapshot đã được thiết lập. Điều này mạnh hơn mức tối thiểu mà một số tài liệu SQL lý thuyết gắn với tên Repeatable Read.

Nhưng `REPEATABLE READ` vẫn **chưa tương đương `SERIALIZABLE`** trong mọi tình huống.

### 14.3. Xung đột khi ghi cùng một hàng

Nếu transaction A ở `REPEATABLE READ` đã có snapshot, rồi transaction B sửa một hàng và commit, A sau đó cố `UPDATE` chính hàng đó, PostgreSQL có thể báo lỗi:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

A phải rollback/retry theo quy trình. Không nên tự nghĩ “vì snapshot của A ổn định nên PostgreSQL cứ ghi đè giá trị mới”.

Mặt khác, một số bất thường liên quan đến **nhiều hàng khác nhau** vẫn có thể xuất hiện, như write skew.

## 15. Write skew: hai transaction cùng đúng khi đọc nhưng cùng sai khi commit

Đây là tình huống quan trọng giúp phân biệt `REPEATABLE READ` với `SERIALIZABLE`.

Giả sử phòng trực luôn phải có **ít nhất một bác sĩ đang trực**.

### 15.1. Tạo bảng minh họa

```sql
CREATE TABLE acid_lab.on_call (
    doctor_id bigint PRIMARY KEY,
    doctor_name text NOT NULL,
    on_duty boolean NOT NULL
);

INSERT INTO acid_lab.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'Bác sĩ A', TRUE),
    (2, 'Bác sĩ B', TRUE);
```

Bất biến nghiệp vụ:

```text
Số bác sĩ có on_duty = TRUE phải >= 1
```

Một `CHECK (on_duty IN (TRUE,FALSE))` chỉ kiểm tra từng hàng và **không bảo đảm được tổng số bác sĩ đang trực**.

### 15.2. Hai transaction ở `REPEATABLE READ`

Giả sử hai bác sĩ cùng muốn nghỉ, mỗi người chỉ đồng ý nghỉ nếu **người còn lại vẫn trực**.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS available_doctors
FROM acid_lab.on_call
WHERE on_duty = TRUE;
-- 2
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS available_doctors
FROM acid_lab.on_call
WHERE on_duty = TRUE;
-- 2
```

**Session A** cập nhật bác sĩ 1:

```sql
UPDATE acid_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
```

**Session B** cập nhật bác sĩ 2:

```sql
UPDATE acid_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
```

Sau đó hai session cùng `COMMIT`.

Vì chúng cập nhật **hai hàng khác nhau**, kiểu thực thi này có thể cho phép cả hai commit ở `REPEATABLE READ`, khiến bảng cuối cùng là:

| doctor_id | on_duty |
| ---: | --- |
| 1 | FALSE |
| 2 | FALSE |

Cả hai bác sĩ nghỉ dù quy tắc đòi ít nhất một người trực.

### 15.3. Vì sao đây không phải lost update thông thường?

Không có một hàng bị hai transaction ghi đè. Mỗi giao dịch sửa một hàng khác nhau, nhưng cả hai cùng dựa vào **kết luận từ một tập hàng**: “hiện có hai bác sĩ trực”.

Mỗi transaction nhìn snapshot hợp lệ theo cách đọc của mình, nhưng kết quả chung **vi phạm bất biến nhiều hàng**.

Đây là **write skew**, một dạng serialization anomaly mà snapshot isolation có thể cho phép.

### 15.4. Thử lại với `SERIALIZABLE`

Khôi phục bảng thực hành về trạng thái hai bác sĩ đều trực, rồi cho cả hai transaction chạy ở:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

với cùng mẫu: cả hai đọc số người trực, A cập nhật hàng 1, B cập nhật hàng 2.

PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để theo dõi những phụ thuộc đọc/ghi có thể tạo bất thường serialization. Trong lịch xung đột như trên, hệ thống sẽ phải tránh việc cả hai transaction commit thành kết quả không thể giải thích như một thứ tự tuần tự hợp lệ. Một transaction có thể bị hủy với lỗi `SQLSTATE 40001`.

**Sau lỗi, ứng dụng phải retry toàn bộ transaction**, bắt đầu từ bước đọc số bác sĩ trực. Lượt retry sẽ thấy một người đã nghỉ và không được cho người còn lại nghỉ nếu bất biến vẫn được kiểm tra đúng.

**Đừng hiểu rằng `SERIALIZABLE` tự suy ra “phải có ít nhất một bác sĩ trực”.** PostgreSQL ngăn lịch tương tranh không tuần tự hóa được; ứng dụng vẫn phải **thực hiện kiểm tra bất biến** trong transaction.

### 15.5. Một cách khác: khóa theo quy tắc nghiệp vụ

Nếu không muốn dựa hoàn toàn vào retry SSI, có thể thiết kế một hàng điều phối hoặc dùng `SELECT ... FOR UPDATE` khóa những hàng liên quan theo một thứ tự nhất quán trước khi quyết định thay đổi.

Tuy nhiên, đừng viết một `SELECT COUNT(*)` thông thường rồi nghĩ nó đã khóa toàn bộ tập hàng. `COUNT` không tự tạo khóa hàng ngăn những bác sĩ khác cập nhật. Với một quy tắc phạm vi nhiều hàng, phải xác định rõ **tập khóa** hoặc chọn `SERIALIZABLE` phù hợp.

## 16. `SERIALIZABLE`: kết quả phải tương đương một thứ tự tuần tự

Định nghĩa thực hành:

> Nếu tất cả giao dịch liên quan thực thi ở `SERIALIZABLE` và xử lý retry đúng cách, PostgreSQL điều phối để những transaction **được commit** có kết quả tương đương với một lịch chạy tuần tự hợp lệ, dù thực tế chúng có thể xen kẽ.

Điều này không có nghĩa PostgreSQL chạy mỗi transaction một mình. Nó vẫn dùng MVCC và SSI để cho phép nhiều transaction đồng thời; khi phát hiện mẫu phụ thuộc nguy hiểm, hệ thống có thể **hủy một transaction** để giữ tính đúng.

### 16.1. Ví dụ bắt đầu transaction serializable

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM acid_lab.on_call
WHERE on_duty = TRUE;

-- Kiểm tra điều kiện nghiệp vụ rồi thực hiện UPDATE phù hợp.

COMMIT;
```

Câu trên là **khung minh họa**. Nếu có logic nghiệp vụ cụ thể, nó phải nằm trong transaction và không được tách thành một `SELECT` ở transaction A, rồi `UPDATE` ở transaction B.

### 16.2. Lỗi serialization là một phần của hợp đồng

Một transaction serializable có thể thất bại với:

```text
SQLSTATE 40001: serialization_failure
```

Đây không nhất thiết là bug của PostgreSQL. Nó thường là cơ chế bảo vệ tính nhất quán khi các giao dịch đồng thời cạnh tranh.

Ứng dụng cần:

1. Nhận biết SQLSTATE.
2. Rollback transaction hiện tại.
3. Bắt đầu **transaction mới**.
4. Đọc lại dữ liệu và tính lại quyết định.
5. Thử commit lại.
6. Giới hạn số lần thử, dùng backoff/jitter và báo lỗi phù hợp nếu xung đột kéo dài.

### 16.3. Không chỉ retry riêng câu lệnh bị lỗi

Sai ý tưởng:

```text
BEGIN
SELECT số bác sĩ còn trực
UPDATE bác sĩ A
COMMIT -> serialization_failure
Chỉ chạy lại UPDATE bác sĩ A
```

Lượt cập nhật thứ hai không còn dựa trên snapshot/điều kiện vừa được kiểm tra. Phải retry **toàn bộ logic nghiệp vụ** từ đầu.

### 16.4. SERIALIZABLE không thay thế điều kiện dữ liệu

Nếu một transaction serializable cố tình thực hiện:

```sql
UPDATE acid_lab.accounts
SET balance = balance + 1000000
WHERE account_id = 101;
```

thì mức cô lập không biết khoản tiền đó hợp lệ hay không. Nó chỉ kiểm soát các bất thường do **chạy đồng thời**, không tự đánh giá nguồn tiền.

Vẫn cần ràng buộc, quyền, kiểm tra nghiệp vụ và quy trình kiểm toán.

## 17. Retry, SQLSTATE và cách xử lý lỗi

Trong ứng dụng giao dịch, cần phân biệt nhiều loại lỗi.

| Mã/nhóm | Ví dụ | Hướng xử lý khái quát |
| --- | --- | --- |
| `40001` | Serialization failure | Thường retry **toàn transaction** sau rollback |
| `40P01` | Deadlock detected | Thường rollback/retry toàn transaction nếu thao tác idempotent và chính sách cho phép |
| `23505` | Unique violation | Có thể do input sai hoặc tranh chấp; **không** retry mù quáng |
| `23503` | Foreign key violation | Xem dữ liệu tham chiếu và quy tắc nghiệp vụ |
| `23514` | Check constraint violation | Sửa input/logic khiến bất biến bị vi phạm |
| `55P03` | Lock not available | Xem tình huống `NOWAIT`/lock timeout, xác định chính sách thử lại |
| `57014` | Query canceled | Có thể do timeout hoặc yêu cầu cancel; không tự coi là xung đột serialization |

**Lưu ý:** lỗi `23505` trong một số tình huống cạnh tranh có thể được xử lý bằng retry ở tầng nghiệp vụ, nhưng không nên gom tất cả lỗi unique thành “thử lại chắc sẽ thành công”. Có thể một giá trị đã tồn tại vĩnh viễn và người dùng phải nhận thông báo trùng.

### 17.1. Retry cần có giới hạn

```text
for attempt = 1..maxAttempts:
    mở transaction mới
    đọc lại điều kiện nghiệp vụ
    thực hiện thay đổi
    COMMIT
    nếu thành công: kết thúc
    nếu SQLSTATE 40001/40P01:
        ROLLBACK
        backoff + jitter rồi thử lại
    nếu lỗi khác:
        ROLLBACK
        xử lý theo loại lỗi
sau maxAttempts: trả lỗi có thể quan sát và điều tra
```

Đây là **pseudocode**, không phải SQL chạy trực tiếp. Nếu trong workflow có gọi hệ thống ngoài, phải tách side effect khỏi vòng retry hoặc bảo đảm idempotency; nếu không, retry có thể gửi email/thu tiền nhiều lần dù database chỉ commit một lần.

### 17.2. Lỗi xảy ra sau khi client mất kết nối

Nếu kết nối mất đúng lúc `COMMIT`, client có thể không biết server đã xác nhận hay chưa. Đừng tự động gửi lại một giao dịch chuyển tiền theo cách tạo thêm bản ghi tiền mới. Dùng một **business request ID duy nhất** để tra cứu/kết hợp lại trước khi tạo tác động khác.

Đây là ranh giới quan trọng giữa **giao dịch ACID** và **exactly-once semantics** ở tầng ứng dụng phân tán.

## 18. Khóa hàng: `SELECT ... FOR UPDATE`

Không phải mọi bài toán cần `SERIALIZABLE`. Với một số thao tác cần phối hợp trên **một tập hàng cụ thể**, khóa hàng có thể giúp thiết kế dễ hiểu hơn.

Ví dụ:

```sql
BEGIN;

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Sau khi khóa các hàng cần thay đổi, kiểm tra số dư
-- và thực hiện UPDATE tương ứng trong cùng transaction.

ROLLBACK;
```

`FOR UPDATE` yêu cầu khóa các hàng được chọn; một transaction khác muốn cập nhật/khóa xung đột những hàng này có thể phải chờ.

### 18.1. Khóa hàng không khóa “mọi hàng sẽ được chèn trong tương lai”

Nếu một quy tắc nghiệp vụ nói về một tập động như “không được có quá N đơn đang mở”, việc khóa **những hàng hiện đang có** chưa chắc chặn transaction khác **chèn hàng mới** thỏa cùng điều kiện.

Điều đó liên quan đến phantom và predicate-level business invariants. Có thể cần ràng buộc độc lập, serializable hoặc một hàng điều phối có khóa rõ.

### 18.2. `FOR UPDATE` không phải `LOCK TABLE`

`SELECT ... FOR UPDATE` khóa **các hàng được chọn** theo cơ chế PostgreSQL, không phải tự khóa mọi hàng của bảng. PostgreSQL vẫn có những table-level locks đi kèm việc thực hiện query, nhưng không nên coi một truy vấn khóa hàng là khóa độc quyền cả bảng.

Để hiểu đúng, hãy phân biệt **row-level locks**, **table-level locks** và cơ chế đọc MVCC.

### 18.3. Tránh deadlock bằng thứ tự khóa nhất quán

Giả sử giao dịch A chuyển từ 101 sang 202, còn giao dịch B chuyển từ 202 sang 101. Nếu A khóa 101 trước, B khóa 202 trước rồi cả hai tìm cách khóa hàng còn lại, có thể hình thành deadlock.

Một chiến lược phổ biến là khóa các tài khoản theo **cùng thứ tự khóa ổn định**, chẳng hạn `account_id` tăng dần, rồi mới thực hiện cập nhật. Điều này giúp giảm nguy cơ deadlock khi được áp dụng nhất quán ở toàn bộ luồng xử lý liên quan.

Tuy nhiên, thứ tự khóa và kế hoạch truy vấn phức tạp cần được đánh giá trong hệ thống thực tế; không xem một `ORDER BY` đơn lẻ là lời hứa tuyệt đối rằng mọi workflow không thể deadlock.

### 18.4. `NOWAIT` và `SKIP LOCKED`

PostgreSQL cho phép biến thể:

```sql
SELECT account_id
FROM acid_lab.accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;
```

Nếu hàng đang bị khóa không tương thích, `NOWAIT` có thể báo lỗi thay vì chờ.

`SKIP LOCKED` cho phép bỏ qua hàng đang khóa và thường hữu ích cho **worker queue** chọn một công việc chưa ai nhận.

Nhưng với chuyển tiền, **không được dùng SKIP LOCKED rồi lặng lẽ bỏ tài khoản đang khóa**, vì lúc đó hệ thống có thể xử lý sai tập dữ liệu. Chọn cơ chế khóa theo ngữ nghĩa nghiệp vụ.

## 19. Lost update: cách viết SQL ảnh hưởng kết quả

Một ứng dụng có thể đọc số lượng hàng trong kho:

```text
T1 đọc quantity = 10
T2 đọc quantity = 10
T1 tính quantity = 9
T2 tính quantity = 9
T1 ghi quantity = 9
T2 ghi quantity = 9
```

Sau hai lượt bán, tồn kho vẫn 9 thay vì 8. Đây là ví dụ ý định cập nhật bị mất do **đọc–sửa–ghi trên giá trị cũ** ở một thiết kế thiếu kiểm soát tương tranh.

### 19.1. Tạo bảng kho

```sql
CREATE TABLE acid_lab.inventory (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0)
);

INSERT INTO acid_lab.inventory
    (product_id, available)
VALUES (1001, 10);
```

### 19.2. Tránh gửi một giá trị cũ tính từ ứng dụng

Cách dễ bị race:

```sql
-- Ở transaction A:
SELECT available
FROM acid_lab.inventory
WHERE product_id = 1001;

-- Ở ứng dụng: lấy 10 - 1 = 9.
UPDATE acid_lab.inventory
SET available = 9
WHERE product_id = 1001;
```

Nếu nhiều request cùng đọc 10 rồi ghi 9, kết quả không phản ánh hai lượt bán.

### 19.3. Cập nhật tương đối và kiểm tra điều kiện trong cùng statement

```sql
BEGIN;

UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING product_id, available;

ROLLBACK;
```

Ở `READ COMMITTED`, PostgreSQL dùng khóa hàng khi UPDATE; transaction thứ hai phải xử lý xung đột thích hợp và có thể đánh giá lại điều kiện với phiên bản hàng mới sau khi chờ.

Khi số lượng chỉ còn 1, hai request cùng giảm 1 sẽ không được phép cả hai giảm xuống âm và commit với điều kiện `available >= 1`. Một request có thể cập nhật 1 hàng, request còn lại cập nhật **0 hàng**, mà ứng dụng phải nhận biết để trả “hết hàng”.

### 19.4. Optimistic concurrency bằng cột version

Một chiến lược khác là lưu `version` rồi cập nhật nếu phiên bản chưa đổi:

```sql
CREATE TABLE acid_lab.stock_versions (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0),
    version bigint NOT NULL DEFAULT 0
);

INSERT INTO acid_lab.stock_versions
    (product_id, available, version)
VALUES
    (1001, 10, 0);
```

Sau khi ứng dụng đọc `available = 10, version = 0`:

```sql
UPDATE acid_lab.stock_versions
SET available = 9,
    version = version + 1
WHERE product_id = 1001
  AND version = 0
RETURNING available, version;
```

Nếu request khác đã tăng version, câu UPDATE sẽ ảnh hưởng 0 hàng; ứng dụng phải đọc lại và quyết định thử lại, không tự coi “0 hàng” là thành công.

Cách version hữu ích khi logic cập nhật phức tạp, nhưng không thay thế transaction khi một thao tác ảnh hưởng nhiều bảng.

## 20. Durability: vì sao `COMMIT` cần Write-Ahead Log?

**Tính bền vững** nói về khả năng giữ những thay đổi đã được commit qua sự cố theo các bảo đảm hệ thống lưu trữ và cấu hình đã chọn.

PostgreSQL dùng **Write-Ahead Logging (WAL)**:

1. Trước khi những thay đổi dữ liệu được xem là bền vững, thông tin cần cho phục hồi được ghi vào WAL.
2. Khi transaction commit, PostgreSQL ghi nhận commit trong log theo quy tắc liên quan.
3. Với cấu hình bền vững mặc định phù hợp, server chờ các bản ghi WAL cần thiết được đưa xuống lưu trữ bền vững trước khi xác nhận commit với client.
4. Sau crash, PostgreSQL dùng WAL để phục hồi trạng thái nhất quán; không cần mọi trang dữ liệu đã được ghi xuống data files ngay tại đúng thời điểm commit.

Sơ đồ khái quát:

```text
Ứng dụng gửi COMMIT
         |
         v
PostgreSQL ghi WAL cho những thay đổi/commit
         |
         v
Đồng bộ WAL xuống lưu trữ theo cấu hình
         |
         v
Phản hồi COMMIT thành công
         |
         v
Sau crash: phục hồi dữ liệu từ WAL cần thiết
```

**Không nhầm WAL với bản sao lưu:** WAL là một thành phần của phục hồi crash và PITR khi được cấu hình, nhưng một WAL directory trên cùng ổ bị mất hoàn toàn không tự cung cấp backup an toàn.

### 20.1. Tại sao không ghi thẳng mọi data page trước COMMIT?

Một transaction có thể thay đổi nhiều page nằm ở nhiều tệp. Việc ép tất cả data page xuống ổ trước mỗi commit có thể tốn chi phí lớn. WAL cho phép PostgreSQL đảm bảo có đủ thông tin phục hồi khi crash, dù các data page được ghi xuống đĩa ở những thời điểm khác.

`CHECKPOINT` giúp đưa những thay đổi page và thông tin liên quan vào trạng thái phục hồi thuận tiện hơn, nhưng không phải điều kiện để **một transaction vừa commit** được coi bền vững theo cơ chế WAL mặc định.

### 20.2. `fsync`

Kiểm tra:

```sql
SHOW fsync;
```

Với `fsync = on` và phần cứng/hệ điều hành tôn trọng lời hứa đồng bộ dữ liệu, PostgreSQL thực hiện các thao tác flush cần thiết để bảo vệ dữ liệu khỏi nhiều loại sự cố nguồn điện/hệ điều hành.

Nếu tắt `fsync`, hệ thống có thể mất khả năng phục hồi nhất quán sau sự cố, thậm chí gây hỏng dữ liệu. **Không tắt fsync trong production chỉ để tăng throughput** nếu chưa chấp nhận rõ rủi ro mất/hỏng dữ liệu.

### 20.3. `synchronous_commit`

Kiểm tra:

```sql
SHOW synchronous_commit;
```

Giá trị thường gặp là `on`. Khi không có cấu hình synchronous replication đặc biệt, chế độ đồng bộ commit phù hợp đợi WAL commit được flush ở server cục bộ trước khi xác nhận giao dịch.

Nếu cấu hình `synchronous_commit = off`, PostgreSQL có thể xác nhận commit trước khi WAL commit được flush xuống ổ. Điều này tăng throughput/giảm độ trễ trong một số tình huống, nhưng **một số transaction đã được client nhận báo thành công gần thời điểm crash có thể bị mất**.

**Phân biệt:** `synchronous_commit = off` không có nghĩa cứ crash là database sẽ hỏng; rủi ro chính là mất một số giao dịch gần nhất dù trước đó đã được xác nhận. Còn tắt `fsync` có thể gây mức rủi ro nghiêm trọng hơn, bao gồm trạng thái không nhất quán/hỏng dữ liệu sau sự cố.

### 20.4. Durability là bảo đảm có điều kiện về phần cứng và cấu hình

Không hệ quản trị đơn lẻ nào bảo đảm dữ liệu tồn tại bất chấp mọi thảm họa, chẳng hạn:

- Mất đồng thời tất cả ổ đĩa chứa database và WAL.
- Lỗi phần cứng không tuân thủ thao tác flush.
- Sai sót vận hành xóa dữ liệu đã commit.
- Ransomware hoặc mất toàn bộ site.
- Backup không tồn tại hoặc không thể khôi phục.

Để đạt mục tiêu kinh doanh về RPO/RTO, còn cần **backup, replication, kiểm tra phục hồi và thiết kế hạ tầng**.

## 21. Durability, replication và backup không phải một khái niệm

### 21.1. Async replication có thể trễ

Trong PostgreSQL, hệ thống có thể dùng streaming replication để gửi WAL đến một hoặc nhiều standby.

Với **asynchronous replication**, transaction có thể được xác nhận trên primary trước khi standby nhận/áp dụng WAL đó. Nếu primary mất vĩnh viễn ngay sau commit và failover sang standby chưa theo kịp, một số transaction đã được client biết là thành công **có thể không xuất hiện trên standby**.

Như vậy, commit bền vững **trên primary** không tự đồng nghĩa với “mọi replica đều đã có dữ liệu”.

### 21.2. Synchronous replication phụ thuộc cấu hình

Các tùy chọn như `synchronous_standby_names` kết hợp với những chế độ `synchronous_commit` có thể yêu cầu mức xác nhận từ standby trước khi primary trả lời commit.

Nhưng:

- Chờ standby **nhận WAL** khác chờ nó **flush WAL**.
- Chờ WAL **flush** khác chờ standby **apply** và cho đọc thấy thay đổi.
- Mức bảo đảm cụ thể phụ thuộc cách triển khai replication, quorum và cấu hình.

Không chỉ nhìn `synchronous_commit = on` rồi kết luận mọi replica đã áp dụng transaction. Cần xem toàn bộ cấu hình synchronous replication.

### 21.3. Backup và Point-in-Time Recovery

Để phục hồi khi có lỗi logic hoặc mất hệ thống, một kế hoạch backup có thể gồm:

- Base backup nhất quán.
- WAL archiving phù hợp nếu cần khôi phục tới một thời điểm.
- Retention chính sách lưu giữ.
- Kiểm tra restore định kỳ.
- Kiểm tra quyền truy cập, mã hóa và tính toàn vẹn backup.
- Quy trình phục hồi được thực hành trước khi xảy ra sự cố.

**PITR** (Point-in-Time Recovery) có thể khôi phục database đến một thời điểm trong quá khứ khi có chuỗi backup/WAL cần thiết. Nó không phải công tắc “tự bật vì PostgreSQL có WAL”. Cần cấu hình và kiểm thử cụ thể.

### 21.4. RPO và RTO

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| RPO – Recovery Point Objective | Mức dữ liệu tối đa được chấp nhận mất tính theo thời gian |
| RTO – Recovery Time Objective | Thời gian tối đa mục tiêu để khôi phục dịch vụ |

Một transaction ACID đúng không tự chọn được RPO/RTO cho doanh nghiệp. Chính sách replication, backup và disaster recovery quyết định khả năng đáp ứng mục tiêu.

## 22. ACID trong Java/JDBC

Trong ứng dụng Java, PostgreSQL thường được truy cập qua JDBC driver. Một điểm quan trọng là **JDBC Connection có cơ chế autocommit**.

### 22.1. Không dùng nhiều connection cho một lần chuyển tiền

Sai về thiết kế:

```java
// Ý tưởng không an toàn:
try (Connection a = dataSource.getConnection()) {
    // Trừ tài khoản nguồn.
}
try (Connection b = dataSource.getConnection()) {
    // Cộng tài khoản đích.
}
```

Nếu mỗi connection autocommit độc lập, hai bước không nằm trong cùng một transaction.

Phải đảm bảo **một transaction manager hoặc một connection** quản lý cả ba thao tác.

### 22.2. Ví dụ JDBC kiểm tra số hàng cập nhật

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            long fromAccountId,
            long toAccountId,
            BigDecimal amount
    ) throws Exception {

        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException(
                "Tài khoản nguồn và đích phải khác nhau"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Số tiền phải lớn hơn 0"
            );
        }

        try (Connection conn = dataSource.getConnection()) {
            conn.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
            );
            conn.setAutoCommit(false);

            try {
                int changedSource;
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE acid_lab.accounts " +
                        "SET balance = balance - ? " +
                        "WHERE account_id = ? AND balance >= ?"
                )) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, fromAccountId);
                    ps.setBigDecimal(3, amount);
                    changedSource = ps.executeUpdate();
                }

                if (changedSource != 1) {
                    throw new IllegalStateException(
                        "Nguồn không tồn tại hoặc không đủ số dư"
                    );
                }

                int changedTarget;
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE acid_lab.accounts " +
                        "SET balance = balance + ? " +
                        "WHERE account_id = ?"
                )) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, toAccountId);
                    changedTarget = ps.executeUpdate();
                }

                if (changedTarget != 1) {
                    throw new IllegalStateException(
                        "Tài khoản đích không tồn tại"
                    );
                }

                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO acid_lab.transfers " +
                        "(from_account_id, to_account_id, amount) " +
                        "VALUES (?, ?, ?)"
                )) {
                    ps.setLong(1, fromAccountId);
                    ps.setLong(2, toAccountId);
                    ps.setBigDecimal(3, amount);
                    ps.executeUpdate();
                }

                conn.commit();
            } catch (Exception ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
```

Những điểm đáng chú ý:

1. `setAutoCommit(false)` làm các bước trên cùng connection thuộc một transaction.
2. `PreparedStatement` truyền dữ liệu bằng bind parameters, không ghép giá trị người dùng vào SQL.
3. `BigDecimal` phù hợp với `numeric` cho số tiền chính xác thập phân.
4. `executeUpdate()` phải ảnh hưởng đúng một hàng ở cả nguồn và đích.
5. `commit()` chỉ chạy sau khi **tất cả** bước thành công.
6. Khi có lỗi, `rollback()` hủy giao dịch; nếu rollback cũng lỗi, ngoại lệ bổ sung được giữ để điều tra.
7. `try-with-resources` đóng các statement và connection khi rời scope.

Đây là ví dụ kiến thức về transaction, **không phải hệ thống thanh toán production hoàn chỉnh**: nó chưa có idempotency key, chống gửi trùng request, cơ chế retry phân biệt SQLSTATE, khóa theo thứ tự thống nhất, audit bảo mật hoặc xử lý sự cố “commit không rõ kết quả”.

### 22.3. Connection pool phải có chính sách trả connection sạch

Một connection đang ở transaction lỗi hoặc còn chưa commit không được vô tình giao lại cho request khác. Thư viện connection pool thường cung cấp cơ chế reset/rollback khi trả connection, nhưng ứng dụng vẫn nên tuân thủ transaction boundary rõ ràng và không phụ thuộc vào một hành vi không được kiểm chứng.

Với framework quản lý transaction, việc mở/commit/rollback thường do transaction manager thực hiện; không nên đồng thời quản lý thủ công trên cùng connection nếu không hiểu cách framework hoạt động.

### 22.4. Retry trong Java phải bao quanh toàn bộ logic

Khi nhận `SQLException` có SQLSTATE `40001` hoặc `40P01`, ứng dụng có thể chạy lại phương thức **giao dịch nguyên khối** với connection/transaction mới, sau backoff và trong giới hạn retry.

Nhưng nếu transaction đã làm side effect ngoài database, retry không được tự gửi side effect lần nữa. Khi commit mơ hồ, cần tra theo idempotency key trước khi tạo một lần chuyển tiền mới.

## 23. Transactional outbox: phối hợp database với hệ thống bên ngoài

Giả sử ứng dụng cần:

1. Đánh dấu đơn đã thanh toán trong PostgreSQL.
2. Phát sự kiện `OrderPaid` đến message broker.

Nếu làm:

```text
UPDATE orders
COMMIT
publish OrderPaid
```

thì có thể commit database xong nhưng service crash trước khi publish: không có sự kiện.

Nếu làm:

```text
publish OrderPaid
UPDATE orders
COMMIT
```

thì message có thể đã phát nhưng database rollback: event thông báo trạng thái không tồn tại.

**PostgreSQL transaction không tự bao trùm broker.**

### 23.1. Transactional outbox lưu cả thay đổi và ý định phát sự kiện

Ví dụ schema minh họa:

```sql
CREATE TABLE acid_lab.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID'))
);

CREATE TABLE acid_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz
);

INSERT INTO acid_lab.orders (order_id, status)
VALUES (5001, 'NEW');
```

Cập nhật trạng thái và ghi outbox trong **cùng transaction**:

```sql
BEGIN;

UPDATE acid_lab.orders
SET status = 'PAID'
WHERE order_id = 5001
  AND status = 'NEW'
RETURNING order_id, status;

-- Trong ứng dụng thật: chỉ INSERT event nếu UPDATE
-- xác nhận chuyển trạng thái thành công.
INSERT INTO acid_lab.outbox_events
    (event_type, aggregate_id, payload)
VALUES
    (
        'OrderPaid',
        5001,
        '{"order_id":5001,"status":"PAID"}'::jsonb
    );

ROLLBACK;
```

Ví dụ dùng `ROLLBACK` để không thay đổi dữ liệu lab. Nếu logic xác nhận thành công và `COMMIT`:

- Đơn ở trạng thái PAID.
- Hàng outbox tồn tại.

Cả hai được commit/rollback cùng nhau. Một worker riêng đọc outbox rồi gửi broker, sau đó đánh dấu `delivered_at` theo chính sách.

### 23.2. Outbox không tự cung cấp exactly-once delivery

Worker có thể publish event thành công nhưng crash trước khi ghi trạng thái delivered. Khi chạy lại, nó có thể gửi **cùng event lần nữa**.

Vì vậy, outbox thường đi kèm:

- `event_id` hoặc `request_id` ổn định.
- Consumer **idempotent**.
- Retry có backoff.
- Giám sát backlog/số lần thử.
- Cơ chế xử lý message lỗi lâu dài.

**ACID trong PostgreSQL** bảo đảm thay đổi đơn và hàng outbox cùng transaction; còn việc broker và consumer xử lý event là vấn đề **phối hợp hệ thống phân tán**.

## 24. Idempotency: tránh thực hiện cùng yêu cầu hai lần

Đối với API chuyển tiền, client có thể gửi lại request khi timeout. Dù request đầu đã commit, client có thể chưa nhận được phản hồi.

Nếu mỗi lần request tạo một lần chuyển tiền mới, hai giao dịch ACID riêng biệt vẫn có thể trừ tiền **hai lần**. Atomicity không ngăn chuyện đó.

### 24.1. Dùng khóa yêu cầu duy nhất

Có thể bổ sung một bảng theo dõi idempotency:

```sql
CREATE TABLE acid_lab.transfer_requests (
    request_id text PRIMARY KEY,
    from_account_id bigint NOT NULL,
    to_account_id bigint NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    transfer_id bigint UNIQUE
        REFERENCES acid_lab.transfers(transfer_id),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Một request có `request_id` cố định, ví dụ `'req-abc-123'`. Mọi lần thử lại của **cùng hành động nghiệp vụ** phải dùng cùng ID và cùng nội dung.

### 24.2. Yêu cầu thiết kế đúng

Một quy trình production cần:

1. Quy định `request_id` do ai sinh ra và nó có phạm vi duy nhất thế nào.
2. Kiểm tra có request đã xử lý chưa trong transaction thích hợp.
3. Bảo vệ `request_id` bằng `UNIQUE/PRIMARY KEY` để các request đồng thời không cùng xử lý như hai hành động khác nhau.
4. Nếu request cũ đã xử lý, trả lại **kết quả đã lưu** thay vì chuyển tiền thêm lần nữa.
5. Nếu trùng ID nhưng payload khác, trả lỗi rõ ràng.
6. Kết hợp chuyển tiền và ghi kết quả idempotency **trong một transaction**.

Chỉ tạo bảng trên chưa tự hoàn thành thuật toán idempotency. Cần xử lý race condition, commit không rõ kết quả và retry đúng cách.

**Nhớ:** PostgreSQL bảo vệ tính nguyên tử của **một transaction**; idempotency bảo vệ ý nghĩa “một yêu cầu nghiệp vụ” khi có **nhiều transaction/retry**.

## 25. Tính cô lập của một câu lệnh và nhiều câu lệnh

Một số quy tắc có thể được bảo đảm tốt hơn bằng cách gói chúng trong **một câu lệnh SQL**.

Ví dụ giảm tồn kho:

```sql
UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING available;
```

Đây là một statement nguyên tử và có điều kiện, nên trong nhiều trường hợp đơn giản, bạn không cần một transaction nhiều bước chỉ để thực hiện đúng **một update**.

Nhưng nếu giảm kho đồng thời phải:

- Tạo đơn hàng.
- Trừ tồn kho.
- Ghi lịch sử xuất kho.
- Tạo outbox event.

thì những thao tác này cần được phối hợp trong **một transaction** hoặc một thiết kế phân tán phù hợp.

### 25.1. Một statement nguyên tử không nghĩa toàn workflow nguyên tử

```text
INSERT order        -> autocommit thành công
UPDATE inventory    -> autocommit thành công
INSERT outbox       -> lỗi
```

Mỗi statement có thể tự nguyên tử nhưng **toàn workflow** vẫn không nguyên tử khi chúng là ba transaction riêng.

### 25.2. Một transaction nhiều statement chưa chắc cô lập đủ

```text
BEGIN READ COMMITTED
SELECT một bất biến nhiều hàng
UPDATE vài hàng
COMMIT
```

Các bước nằm trong một transaction, nhưng vẫn có thể có race/anomaly nếu mức cô lập và khóa không đáp ứng bất biến. Cần phân biệt **Atomicity** với **Isolation**.

## 26. Deadlock và các transaction chờ nhau

Một deadlock xảy ra khi các transaction tạo một chu kỳ chờ khóa.

Ví dụ:

```text
T1 đã khóa hàng 101
T2 đã khóa hàng 202

T1 muốn khóa 202 -> chờ T2
T2 muốn khóa 101 -> chờ T1

Không bên nào tự tiến lên.
```

PostgreSQL có cơ chế phát hiện deadlock và có thể hủy một transaction với:

```text
SQLSTATE 40P01: deadlock_detected
```

### 26.1. Kịch bản hai session

**Session A:**

```sql
BEGIN;
UPDATE acid_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

**Session B:**

```sql
BEGIN;
UPDATE acid_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;
```

Sau đó A cố cập nhật 202, B cố cập nhật 101. Cả hai có thể chờ nhau và server phát hiện deadlock.

**Không nên tạo deadlock trên production chỉ để học.** Thử với dữ liệu lab và hai phiên độc lập; sau khi server hủy một giao dịch, xử lý rollback phù hợp rồi kết thúc phiên còn lại.

### 26.2. Phòng ngừa

Các cách thường dùng:

- Giữ transaction **ngắn**.
- Khóa tài nguyên theo **thứ tự nhất quán**.
- Tránh query không cần thiết khi đang giữ khóa.
- Tạo index phù hợp để UPDATE/DELETE tránh quét và khóa quá nhiều hàng.
- Tránh gọi API bên ngoài khi đang giữ transaction.
- Thiết kế retry cho `40P01` nếu nghiệp vụ hỗ trợ.

Deadlock không đồng nghĩa database bị lỗi; nó là hiện tượng có thể xảy ra trong hệ thống cạnh tranh khóa. Quan trọng là **giảm tần suất và xử lý lỗi đúng**.

## 27. Vận hành: tránh `idle in transaction`

Một kết nối mở `BEGIN` rồi chờ quá lâu mà không commit/rollback có thể giữ snapshot, khóa và tài nguyên lâu hơn cần thiết.

Ví dụ hành vi xấu:

```text
BEGIN
SELECT/UPDATE ...
Ứng dụng chờ người dùng bấm nút trong 15 phút
COMMIT
```

Trong khoảng chờ, database có thể bị ảnh hưởng:

- Các transaction khác chờ khóa.
- VACUUM không thể loại bỏ một số phiên bản hàng cũ còn cần thiết cho snapshot dài.
- Kết nối bị chiếm dụng.
- Hệ thống khó xác định request nào đang giữ transaction.

### 27.1. Xem các transaction đang mở

Truy vấn giám sát mẫu:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    now() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Tùy quyền, bạn có thể không xem được đầy đủ query hoặc trạng thái của phiên khác.

Trong môi trường nhiều người dùng, `query` có thể chứa thông tin nhạy cảm; đừng sao chép/log nguyên truy vấn khi chưa kiểm soát quyền.

### 27.2. Timeout hữu ích

Các cấu hình đáng biết:

- `statement_timeout`: giới hạn thời gian thực hiện một statement.
- `lock_timeout`: giới hạn thời gian chờ một khóa.
- `idle_in_transaction_session_timeout`: có thể kết thúc session idle trong transaction quá lâu.

Ví dụ trong transaction lab:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '2s';

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id = 101;

ROLLBACK;
```

`SET LOCAL` chỉ có hiệu lực trong transaction. Đặt timeout quá thấp có thể tạo nhiều lỗi giả khi tải tăng; phải thiết kế theo SLA và loại truy vấn.

### 27.3. Đo tổng commit/rollback

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
```

Các bộ đếm giúp quan sát xu hướng vận hành, nhưng `xact_rollback` tăng không tự chứng minh lỗi nghiệp vụ; rollback cũng có thể là hành vi chủ đích. Tương tự, số commit cao không chứng minh mọi transaction đúng.

## 28. Kiểm tra cấu hình liên quan đến ACID

Một số lệnh đọc cấu hình:

```sql
SHOW default_transaction_isolation;
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
SHOW idle_in_transaction_session_timeout;
```

Ý nghĩa khái quát:

| Cấu hình | Liên quan |
| --- | --- |
| `default_transaction_isolation` | Mức isolation mặc định của transaction |
| `fsync` | Khả năng bảo đảm đồng bộ dữ liệu xuống lưu trữ |
| `synchronous_commit` | Khi nào commit được xác nhận đối với WAL/standby theo cấu hình |
| `full_page_writes` | Bảo vệ chống một số dạng page write không hoàn chỉnh trong WAL recovery |
| `wal_level` | Lượng thông tin WAL cần cho các nhu cầu như replication/khôi phục |
| `idle_in_transaction_session_timeout` | Giảm nguy cơ phiên idle trong transaction giữ tài nguyên quá lâu |

**Không chỉnh cấu hình chỉ vì đọc thấy một giá trị “có vẻ chậm”.** Một số thay đổi có thể giảm độ bền vững hoặc ảnh hưởng đến khả năng khôi phục. Cần đánh giá yêu cầu RPO/RTO, replication, tải thực tế, phiên bản PostgreSQL và quy trình vận hành.

## 29. Các ngộ nhận phổ biến về ACID

| Ngộ nhận | Thực tế trong PostgreSQL |
| --- | --- |
| “BEGIN là mọi thứ tự động an toàn” | Cần đúng câu SQL, ràng buộc và mức cô lập |
| “Atomicity = mọi lệnh tự được viết đúng” | Chỉ commit/rollback những thao tác thực sự được đưa vào transaction |
| “Một UPDATE thành công tức là đã commit” | Còn phụ thuộc transaction có COMMIT thành công hay không |
| “Một file SQL gồm nhiều lệnh luôn là một transaction” | Có thể mỗi lệnh autocommit nếu không BEGIN |
| “SAVEPOINT là transaction riêng được commit độc lập” | Savepoint chỉ là mốc rollback trong transaction cha |
| “Rollback sẽ trả lại sequence ID” | Sequence thường không rollback |
| “Consistency nghĩa là mọi session luôn thấy cùng giá trị” | Đó là vấn đề isolation/visibility; consistency ACID nói về bất biến dữ liệu |
| “CHECK balance >= 0 bảo đảm mọi chuyển tiền cân bằng” | Nó không kiểm tra tổng tiền hoặc các bước bên bảng khác |
| “READ UNCOMMITTED cho dirty reads trong PostgreSQL” | PostgreSQL xử lý tương đương READ COMMITTED |
| “REPEATABLE READ luôn serializable” | Có thể còn write skew/serialization anomaly |
| “SERIALIZABLE không bao giờ lỗi” | Có thể báo `40001` và cần retry |
| “Retry lại mỗi UPDATE là đủ sau serialization failure” | Phải retry toàn bộ transaction và mọi quyết định dựa trên snapshot cũ |
| “Không có lost update nếu đã SELECT trước UPDATE” | Đọc–tính–ghi với giá trị cũ có thể vẫn sai |
| “SELECT FOR UPDATE khóa toàn bảng” | Nó chủ yếu khóa những hàng được chọn |
| “SKIP LOCKED phù hợp cho mọi thao tác đồng thời” | Nó bỏ qua hàng khóa, thường không phù hợp chuyển tiền |
| “COMMIT luôn đồng nghĩa mọi replica đã áp dụng” | Phụ thuộc synchronous/asynchronous replication và chế độ chờ |
| “Có WAL là có backup tự động” | Backup/PITR cần cấu hình và kiểm thử riêng |
| “synchronous_commit = off an toàn như on” | Có thể mất một số commit mới được xác nhận gần lúc crash |
| “fsync = off chỉ ảnh hưởng tốc độ” | Có thể gây mất/hỏng dữ liệu sau sự cố |
| “ACID bảo vệ cả broker/email/API bên ngoài” | Transaction PostgreSQL không tự rollback side effect ngoài database |
| “ACID bảo đảm một request HTTP không chạy hai lần” | Cần idempotency riêng |
| “Mất kết nối khi COMMIT nghĩa là chắc chắn rollback” | Kết quả commit có thể mơ hồ với client |
| “Transaction mở càng lâu càng an toàn” | Giữ khóa/snapshot lâu có thể gây chờ và ảnh hưởng VACUUM |

## 30. Bài tập thực hành có hướng dẫn và đáp án

Các bài sử dụng schema `acid_lab` và bảng đã tạo. Với bài hai session, làm trên hai kết nối khác nhau và kiểm tra dữ liệu ban đầu trước khi đối chiếu giá trị.

### Bài 1. Viết transaction cập nhật hai tài khoản rồi rollback

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 20.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 20.00
WHERE account_id = 202;

ROLLBACK;
```

**Đáp án:** hai số dư không đổi sau rollback. Đây là ví dụ tính nguyên tử, nhưng chưa có kiểm tra số hàng nếu tài khoản không tồn tại.

### Bài 2. Vì sao hai UPDATE có autocommit riêng không tạo một lần chuyển tiền nguyên tử?

**Đáp án:** mỗi statement có thể đã commit trước khi statement sau bắt đầu. Nếu lệnh cộng tiền thất bại, lệnh trừ tiền đã commit không tự được rollback. Cần một transaction chung và xử lý lỗi.

### Bài 3. Tại sao `UPDATE` ảnh hưởng 0 hàng vẫn nguy hiểm?

```sql
UPDATE acid_lab.accounts
SET balance = balance + 100
WHERE account_id = 999999;
```

**Đáp án:** câu lệnh có thể chạy thành công nhưng không thay đổi hàng nào. Nếu hệ thống chuyển tiền không kiểm tra `ROW_COUNT` hoặc `RETURNING`, nó có thể ghi lịch sử thành công dù tài khoản đích không có.

### Bài 4. Kiểm tra tài khoản không đủ tiền trong một UPDATE

```sql
UPDATE acid_lab.accounts
SET balance = balance - 1000.00
WHERE account_id = 101
  AND balance >= 1000.00
RETURNING balance;
```

**Đáp án:** với dữ liệu ban đầu 500.00, không có hàng nào được trả về, và số dư không bị trừ. Ứng dụng phải hiểu “0 hàng” là không đáp ứng điều kiện.

### Bài 5. Dùng SAVEPOINT khi thao tác tùy chọn lỗi

```sql
BEGIN;

SAVEPOINT optional_step;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, -1.00);

ROLLBACK TO SAVEPOINT optional_step;

SELECT COUNT(*) FROM acid_lab.accounts;

ROLLBACK;
```

**Đáp án:** INSERT số tiền âm vi phạm CHECK, nhưng sau `ROLLBACK TO SAVEPOINT` có thể chạy SELECT tiếp. Không có transfer sai được lưu.

### Bài 6. Khi nào rollback không trả lại identity/sequence?

**Đáp án:** số sequence đã cấp bằng `nextval` hoặc identity có thể bị tiêu thụ dù transaction chứa INSERT rollback. ID có khoảng trống là bình thường.

### Bài 7. Consistency khác Atomicity như thế nào?

**Đáp án:** Atomicity đảm bảo thay đổi của transaction commit/rollback cùng nhau; Consistency yêu cầu dữ liệu ở trạng thái hợp lệ theo ràng buộc và bất biến. Một transaction có thể nguyên tử nhưng commit một quy tắc nghiệp vụ sai do lập trình viên quên kiểm tra.

### Bài 8. `CHECK (balance >= 0)` đã bảo đảm chuyển tiền không tạo thêm tiền chưa?

**Đáp án:** chưa. Nó chỉ ngăn số dư một hàng âm; vẫn có thể cộng sai hoặc quên trừ nguồn. Cần logic chuyển tiền và cơ chế kiểm tra tổng/liên kết phù hợp.

### Bài 9. `CHECK` và `NOT NULL` có thể luôn trì hoãn đến COMMIT không?

**Đáp án:** không. PostgreSQL hỗ trợ deferrable đối với một số loại constraint như FK/UNIQUE khi khai báo phù hợp; `CHECK` và `NOT NULL` không dùng cơ chế `SET CONSTRAINTS ... DEFERRED` theo cách đó.

### Bài 10. Dirty read có xảy ra ở PostgreSQL `READ UNCOMMITTED` không?

**Đáp án:** không. PostgreSQL triển khai `READ UNCOMMITTED` với hành vi của `READ COMMITTED` nên các câu SELECT thông thường không dirty-read thay đổi chưa commit của transaction khác.

### Bài 11. Lặp SELECT trong `READ COMMITTED`

Session A đọc balance 500; Session B cộng 50 và commit; A đọc lại.

**Đáp án:** A có thể thấy 550 ở lần đọc sau vì mỗi statement có snapshot mới trong `READ COMMITTED`. Đây là nonrepeatable read.

### Bài 12. Lặp SELECT trong `REPEATABLE READ`

Session A đọc balance 500 để thiết lập snapshot; Session B cộng 50 và commit; A đọc lại.

**Đáp án:** A tiếp tục thấy 500 trong snapshot của transaction; sau khi A kết thúc, transaction mới có thể thấy 550.

### Bài 13. Vì sao `REPEATABLE READ` ở PostgreSQL không còn phantom read thông thường?

**Đáp án:** snapshot của transaction ổn định, nên truy vấn lặp không tự thấy hàng mới được transaction khác commit sau snapshot. Nhưng nó vẫn có thể cho write skew, nên chưa tương đương SERIALIZABLE.

### Bài 14. Hai bác sĩ cùng nghỉ có thể vi phạm bất biến nào?

**Đáp án:** “luôn có ít nhất một bác sĩ trực”. Ở REPEATABLE READ, hai transaction có thể cùng đọc hai bác sĩ trực rồi cập nhật hai hàng khác nhau thành FALSE, cùng commit và làm bất biến sai. Đây là write skew.

### Bài 15. Vì sao SERIALIZABLE cần retry?

**Đáp án:** để loại trừ lịch thực thi không tương đương một thứ tự tuần tự, PostgreSQL có thể hủy transaction với `40001`. Ứng dụng phải rollback và chạy lại **toàn transaction**, đọc lại điều kiện và tính lại quyết định.

### Bài 16. `40001` và `40P01` khác nhau thế nào?

**Đáp án:** `40001` liên quan serialization failure; `40P01` liên quan deadlock. Cả hai thường có thể dẫn tới rollback/retry toàn transaction khi nghiệp vụ an toàn và có giới hạn retry, nhưng nguyên nhân xung đột khác nhau.

### Bài 17. `SELECT ... FOR UPDATE` giải quyết điều gì?

**Đáp án:** khóa những hàng được chọn để phối hợp với các transaction muốn thực hiện thao tác xung đột trên cùng hàng. Nó không tự khóa mọi hàng tương lai đáp ứng một điều kiện và không thay thế logic bất biến nhiều hàng.

### Bài 18. Vì sao dùng `SKIP LOCKED` cho chuyển tiền có thể sai?

**Đáp án:** nó bỏ qua các hàng đang bị khóa. Nếu một tài khoản quan trọng bị bỏ qua, ứng dụng có thể xử lý một tập tài khoản không đầy đủ; `SKIP LOCKED` phù hợp hơn với các worker queue mà bỏ qua công việc đang được giữ là có chủ đích.

### Bài 19. Phòng tránh lost update khi giảm kho

```sql
UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING available;
```

**Đáp án:** điều kiện và cập nhật nằm trong cùng statement. Khi hai transaction cạnh tranh, PostgreSQL xử lý khóa hàng và điều kiện phù hợp; ứng dụng kiểm tra số hàng cập nhật để biết còn kho hay không.

### Bài 20. Viết transaction chuyển tiền trong JDBC cần điều gì?

**Đáp án:** một `Connection`, `setAutoCommit(false)`, các `PreparedStatement`, kiểm tra số hàng, `commit()` chỉ khi mọi bước thành công, `rollback()` khi lỗi. Cần thêm idempotency/retry nếu workflow quan trọng và có tranh chấp.

### Bài 21. WAL có giống backup không?

**Đáp án:** không. WAL giúp phục hồi crash và có thể kết hợp backup cho PITR, nhưng backup/retention/khôi phục cần thiết kế riêng. Nếu mất toàn bộ data và WAL cùng nơi lưu, không thể coi WAL tại đó là bản sao dự phòng.

### Bài 22. `synchronous_commit = off` đánh đổi điều gì?

**Đáp án:** có thể giảm thời gian chờ flush WAL, nhưng một số transaction mới được xác nhận có thể mất nếu server crash trước khi WAL được flush bền vững. Nó không tương đương với `fsync = off`; tắt fsync có rủi ro rộng và nghiêm trọng hơn.

### Bài 23. Replica bất đồng bộ có chắc chắn đã nhận mọi commit mới?

**Đáp án:** không. Replica có thể trễ; failover sang replica chưa nhận WAL mới nhất có thể mất các transaction đã commit trên primary. Cần mục tiêu RPO và cấu hình replication thích hợp.

### Bài 24. Transaction PostgreSQL có rollback được email đã gửi không?

**Đáp án:** không. Email là side effect ở hệ thống ngoài. Có thể dùng transactional outbox để ghi ý định phát email/event trong cùng transaction rồi xử lý gửi sau.

### Bài 25. Vì sao outbox vẫn cần idempotent consumer?

**Đáp án:** worker có thể publish thành công rồi crash trước khi đánh dấu delivered, khiến event được gửi lại. Consumer cần nhận biết cùng `event_id` để không áp dụng side effect nhiều lần.

### Bài 26. Mất kết nối đúng lúc COMMIT có nghĩa chắc chắn transaction rollback chưa?

**Đáp án:** không. Có thể server đã commit nhưng client chưa nhận được phản hồi. Cần truy vấn theo idempotency/request ID hoặc cơ chế đối soát để xác định kết quả trước khi thực hiện lại.

### Bài 27. `idle in transaction` gây vấn đề gì?

**Đáp án:** có thể giữ khóa, snapshot, connection và cản trở việc dọn phiên bản cũ của VACUUM. Nên giữ transaction ngắn và dùng timeout phù hợp.

### Bài 28. Cách xem transaction đang mở?

```sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

**Đáp án:** truy vấn giúp quan sát các phiên có transaction đang mở, tùy quyền hệ thống. Cần bảo vệ thông tin giám sát và tránh kết luận từ một ảnh chụp duy nhất.

### Bài 29. Khi nào nên dùng một UPDATE thay cho SELECT rồi UPDATE?

**Đáp án:** khi có thể biểu diễn toàn bộ điều kiện và thay đổi an toàn trong một statement, ví dụ giảm tồn kho hoặc trừ số dư có điều kiện. Cách này thường giảm cửa sổ race condition và số lượt mạng, nhưng workflow nhiều bảng vẫn cần transaction.

### Bài 30. Cho một định nghĩa ngắn của cả ACID

**Đáp án:**

- **Atomicity:** commit/rollback như một đơn vị.
- **Consistency:** trạng thái được commit thỏa bất biến/ràng buộc.
- **Isolation:** kiểm soát tương tác của những transaction đồng thời theo mức đã chọn.
- **Durability:** những thay đổi được commit có thể phục hồi sau sự cố theo bảo đảm WAL/lưu trữ/cấu hình tương ứng.

## 31. Checklist khi thiết kế giao dịch production

| Câu hỏi | Điều cần làm |
| --- | --- |
| Một nghiệp vụ gồm mấy thay đổi database? | Xác định transaction boundary rõ |
| Có dùng nhiều connection không? | Giữ các bước cần nguyên tử trong một transaction được quản lý |
| Có yêu cầu kiểm tra số hàng UPDATE? | Kiểm tra `RETURNING` hoặc affected row count |
| Có trường hợp thiếu hàng hoặc không đủ tiền? | Diễn đạt điều kiện và báo lỗi nghiệp vụ |
| Có ràng buộc schema thích hợp? | PK, FK, UNIQUE, NOT NULL, CHECK, loại phù hợp |
| Có bất biến liên quan nhiều hàng? | Đánh giá khóa, SSI hoặc kiến trúc dữ liệu |
| Có transaction khác cập nhật cùng hàng? | Kiểm soát lost update, lock contention |
| Có write skew tiềm ẩn? | Cân nhắc SERIALIZABLE/khóa điều phối |
| Mức isolation đang dùng là gì? | Kiểm tra cấu hình và đặt rõ khi cần |
| Có logic retry 40001/40P01? | Retry toàn transaction, backoff và giới hạn |
| Có gọi API/email/broker trong transaction? | Tránh side effect không rollback, cân nhắc outbox |
| Request từ client có thể gửi lại không? | Thêm idempotency key và đối soát |
| Nếu COMMIT mất phản hồi thì sao? | Xử lý trạng thái chưa biết thay vì gửi lại mù |
| Có giữ transaction trong lúc chờ người dùng? | Không; giữ transaction ngắn |
| Có thống nhất thứ tự khóa? | Giảm deadlock trong workflow liên quan |
| Có index cho điều kiện UPDATE/DELETE? | Đánh giá index và số hàng bị ảnh hưởng |
| `fsync`/`synchronous_commit` đang cấu hình ra sao? | Hiểu độ bền vững và đánh đổi độ trễ |
| Replication là sync hay async? | Hiểu rủi ro mất commit khi failover |
| Có backup/PITR đã thử restore chưa? | Đảm bảo RPO/RTO thực tế |
| Có giám sát transaction lâu và deadlock? | Theo dõi pg_stat_activity, log, metrics |
| Đã thử failure giữa nhiều bước chưa? | Kiểm thử rollback và tính đúng |
| Đã thử hai session chạy đồng thời chưa? | Kiểm thử race và conflict |
| Có xử lý constraint violation đúng? | Không retry mù quáng mọi SQLSTATE |
| Dữ liệu tiền dùng kiểu chính xác không? | Ưu tiên numeric/BigDecimal theo quy tắc tiền tệ |
| Có ghi rõ giới hạn ACID của workflow không? | Database transaction không bao phủ hệ thống bên ngoài |

## 32. Tổng kết: hiểu ACID để thiết kế, không chỉ để ghi nhớ

Bốn chữ ACID là nền tảng của giao dịch trong PostgreSQL:

1. **Atomicity – Nguyên tử:** một giao dịch được commit/rollback như một đơn vị. Dùng `BEGIN`, `COMMIT`, `ROLLBACK` và `SAVEPOINT` có chủ đích; kiểm tra lỗi từng bước.
2. **Consistency – Nhất quán:** trạng thái được xác nhận phải tuân thủ ràng buộc và bất biến. PostgreSQL cung cấp PK, FK, UNIQUE, CHECK... nhưng ứng dụng phải định nghĩa và thực thi đúng những quy tắc nhiều hàng/nhiều bảng.
3. **Isolation – Cô lập:** transaction đồng thời cần được kiểm soát. `READ COMMITTED` là mặc định phổ biến, `REPEATABLE READ` cho snapshot ổn định nhưng vẫn có thể write skew, còn `SERIALIZABLE` sử dụng cơ chế SSI để ngăn lịch không tuần tự hóa được bằng cách yêu cầu retry khi cần.
4. **Durability – Bền vững:** WAL, cơ chế flush và cấu hình như `fsync`/`synchronous_commit` giúp phục hồi những thay đổi đã commit qua crash theo mức bảo đảm tương ứng. Replication và backup giải quyết những rủi ro hạ tầng bổ sung, không đồng nghĩa riêng với một lệnh COMMIT.

Một transaction có thể vừa **nguyên tử** vừa **sai nghiệp vụ** nếu logic thiếu bước; có thể vừa **nhất quán trên từng hàng** vừa **sai do tranh chấp** nếu không kiểm soát bất biến nhiều hàng; và có thể **commit thành công trên primary** nhưng chưa có trên replica bất đồng bộ.

Đối với một nghiệp vụ quan trọng, hãy đặt năm câu hỏi trước khi triển khai:

1. **Đơn vị công việc nào phải commit/rollback cùng nhau?**
2. **Những ràng buộc và bất biến nào phải luôn đúng?**
3. **Những transaction nào có thể chạy đồng thời và xung đột với nhau?**
4. **Khi commit lỗi hoặc mất phản hồi, ứng dụng sẽ rollback, retry hay đối soát thế nào?**
5. **Dữ liệu đã commit được bảo vệ ra sao trước crash, mất ổ, mất máy và lỗi vận hành?**

Trả lời được năm câu hỏi này giúp bạn sử dụng ACID như một **công cụ thiết kế tính đúng của hệ thống**, thay vì chỉ thuộc bốn định nghĩa lý thuyết.
