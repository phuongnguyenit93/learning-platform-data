# Nhận diện đọc bẩn, đọc không lặp lại và hàng ảo

Một truy vấn `SELECT` có thể hoàn toàn đúng về cú pháp nhưng vẫn trả những kết quả gây bất ngờ khi **hai giao dịch (transaction) cùng truy cập dữ liệu**. Chẳng hạn, giao dịch A đọc số dư tài khoản, trong khi giao dịch B sửa số dư rồi hủy thay đổi; hoặc A đọc danh sách đơn hàng hai lần nhưng giữa hai lần B đã thêm đơn mới.

Ba hiện tượng quan trọng cần nhận diện trong SQL là:

1. **Đọc bẩn (*dirty read*):** đọc một thay đổi của giao dịch khác khi thay đổi đó **chưa được commit**.
2. **Đọc không lặp lại (*non-repeatable read*):** đọc lại **cùng một hàng** trong cùng giao dịch và thấy giá trị khác do giao dịch khác đã **commit** thay đổi.
3. **Hàng ảo (*phantom read*):** chạy lại truy vấn với **cùng điều kiện lọc** trong cùng giao dịch nhưng thấy **tập hàng thỏa điều kiện thay đổi**, ví dụ xuất hiện thêm một hàng mới đã được giao dịch khác commit.

Các hiện tượng này không chỉ phụ thuộc hai câu `SELECT` viết gì, mà còn phụ thuộc **thời điểm chạy từng câu, ranh giới giao dịch, cách commit/rollback và mức cô lập (*isolation level*)** mà hệ quản trị đang áp dụng.

Bài học thuộc **Database SQL → Giao dịch SQL → Nhận diện đọc bẩn, đọc không lặp lại và hàng ảo**. Chúng ta sẽ phân tích các lịch thực thi A/B bằng ví dụ cụ thể, thực hành ở PostgreSQL và SQL Server, so sánh với MySQL/InnoDB, sau đó chọn mức cô lập và cách thiết kế câu lệnh theo yêu cầu nghiệp vụ.

> **Phạm vi an toàn:** Những bài thực hành dùng bảng riêng trong **database thử nghiệm**, không dùng dữ liệu sản xuất. Các ví dụ có hai kết nối phải được chạy **xen kẽ đúng thứ tự**, không dán liền tất cả vào một cửa sổ SQL.

---

## 1. Ôn lại transaction, COMMIT và ROLLBACK

Một giao dịch là một đơn vị công việc gồm một hoặc nhiều câu SQL, với những ràng buộc về **tính nguyên tử, nhất quán, cô lập và bền vững** (ACID) theo khả năng của DBMS và storage engine.

Mẫu đơn giản:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

`COMMIT` xác nhận thay đổi để chúng trở thành một phần trạng thái đã được giao dịch ghi chấp nhận. Nếu thay `COMMIT` bằng `ROLLBACK`, các thay đổi trong giao dịch được hoàn tác theo quy tắc của DBMS.

### Trạng thái chưa commit và đã commit

Giả sử hàng nguồn có `balance = 1000`:

```text
Thời điểm       Giao dịch B                Trạng thái thay đổi
---------       ------------------------   -------------------
t0              --                         1000 đã commit
t1              BEGIN                      bắt đầu transaction
t2              UPDATE balance = 900       900 chưa commit
t3              ROLLBACK                   hủy 900
t4              --                         1000 vẫn là giá trị đã commit
```

Một giao dịch A đọc số dư ở **t2** có được nhìn thấy **900** hay không? Câu trả lời phụ thuộc mức cô lập và cách DBMS thực thi.

### Cùng một transaction nghĩa là gì?

Hai câu `SELECT` chỉ tạo ví dụ **non-repeatable read** hay **phantom read** đúng nghĩa khi chúng được chạy **trong cùng một giao dịch A**, với một giao dịch B can thiệp ở giữa.

Nếu kết nối chạy chế độ tự động commit (*autocommit*) và mỗi `SELECT` là một giao dịch riêng, việc kết quả khác nhau chỉ đơn giản phản ánh dữ liệu đã thay đổi **giữa hai giao dịch khác nhau**. Không nên gọi điều đó là non-repeatable read trong **một transaction** khi không có transaction bao trùm.

### Hai kết nối mới là hai giao dịch độc lập

Trong công cụ như MySQL Workbench, DBeaver, psql, SSMS hoặc một ứng dụng Java, hãy dùng **hai kết nối thực sự khác nhau**:

```text
Kết nối A — reader                       Kết nối B — writer
-------------------                      -------------------
BEGIN                                    BEGIN
SELECT ...             ← giá trị cũ
                                         UPDATE/INSERT ...
                                         COMMIT hoặc ROLLBACK
SELECT ...             ← so sánh
COMMIT
```

**Hai tab cùng dùng một connection chưa chắc là hai transaction độc lập.** Nếu công cụ tái sử dụng connection cho nhiều tab, phải mở hai session riêng.

---

## 2. Bảng so sánh nhanh ba hiện tượng

| Hiện tượng | Bên B làm gì? | B đã commit khi A thấy khác biệt? | A quan sát gì? |
| --- | --- | --- | --- |
| **Dirty read** | Sửa hoặc tạo dữ liệu | **Chưa** | A đọc được dữ liệu tạm thời, có thể bị B rollback |
| **Non-repeatable read** | Sửa một hàng đã đọc | **Rồi** | A đọc lại **cùng hàng theo khóa** và thấy giá trị khác |
| **Phantom read** | Thêm/xóa hàng hoặc thay đổi điều kiện thành viên | **Rồi** | A chạy lại **cùng bộ lọc** và thấy số/tập hàng thỏa điều kiện khác |

Ba câu hỏi để phân loại:

1. **A có đọc dữ liệu B chưa commit không?** Nếu có, đó là dấu hiệu của dirty read.
2. **A có đọc lại đúng một hàng, theo cùng khóa định danh, và thấy giá trị thay đổi sau khi B commit không?** Đó là biểu hiện điển hình của non-repeatable read.
3. **A có chạy lại cùng truy vấn tập hợp và thấy xuất hiện/biến mất hàng thỏa điều kiện không?** Đó là biểu hiện của phantom read.

Một kết quả thay đổi **không tự nó cho biết hiện tượng gì**. Phải quan sát thêm trạng thái commit của B, tập khóa được đọc và điều kiện lọc.

## 3. Đọc bẩn: A nhìn thấy dữ liệu B chưa xác nhận

### 3.1. Lịch thực thi

Ban đầu, tài khoản 1 có số dư 1000.

| Bước | Giao dịch A — reader | Giao dịch B — writer | Ghi chú |
| ---: | --- | --- | --- |
| 1 | — | `BEGIN` | B bắt đầu |
| 2 | — | `UPDATE balance = 900 WHERE id=1` | B chưa commit |
| 3 | `SELECT balance WHERE id=1` → **900** | — | A đã đọc thay đổi tạm thời của B |
| 4 | — | `ROLLBACK` | B hủy cập nhật |
| 5 | `SELECT balance WHERE id=1` → **1000** | — | 900 chưa từng trở thành giá trị được commit |

Bước **3** là dirty read: A đọc 900 khi giao dịch B vẫn có thể hủy nó.

### 3.2. Vì sao dirty read nguy hiểm?

Nếu ứng dụng A dựa vào số dư 900 để báo khách hàng đã bị trừ tiền hoặc từ chối thanh toán, nhưng B rollback, A đã đưa ra quyết định dựa trên **một trạng thái không được xác nhận**.

Ví dụ khác:

- Báo cáo doanh thu đọc một đơn hàng chưa commit, tính cả đơn sẽ bị rollback.
- Dịch vụ gửi email “đơn hàng đã hoàn thành” dựa trên trạng thái đang được giao dịch khác chỉnh sửa.
- Chương trình kiểm tra hạn mức đọc giá trị tạm thời chưa được phê duyệt.
- Quy trình tổng hợp đọc nhiều thay đổi của một giao dịch chưa xong, tạo kết quả không phù hợp trạng thái cuối cùng.

Đọc bẩn không chỉ là “đọc hơi cũ”. Nó là **đọc dữ liệu chưa chắc sẽ tồn tại sau commit/rollback**.

### 3.3. Phân biệt dirty read với đọc dữ liệu đã commit rồi bị thay đổi

Nếu B **COMMIT** giá trị 900 trước khi A đọc, A nhìn thấy 900 là đọc trạng thái đã được xác nhận, **không phải dirty read**.

Dù B có sửa thành 1000 trong một transaction khác sau đó, bản đọc 900 đầu tiên vẫn không bẩn chỉ vì giá trị về sau thay đổi. Từ khóa phân biệt là **chưa commit tại thời điểm A đọc**.

---

## 4. Thực hành dirty read trên SQL Server

**Lưu ý rất quan trọng:** PostgreSQL **không cho đọc bẩn theo cách của mức READ UNCOMMITTED cổ điển**; trong PostgreSQL, `READ UNCOMMITTED` hoạt động như `READ COMMITTED`. Vì thế, phần thực hành đọc bẩn dùng **SQL Server** để minh họa rõ một hệ cho phép mức `READ UNCOMMITTED`.

### 4.1. Chuẩn bị trong database thử nghiệm của SQL Server

Chạy **một lần trước khi mở hai giao dịch**:

```sql
-- SQL Server, không phải PostgreSQL.
CREATE TABLE dbo.tx_dirty_lab_303 (
    account_id INT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO dbo.tx_dirty_lab_303 (account_id, balance)
VALUES (1, 1000.00);
```

Đảm bảo hai kết nối A và B đang cùng trỏ đến database thử nghiệm chứa bảng trên.

### 4.2. B — writer: thay đổi nhưng chưa commit

Trên **kết nối B**:

```sql
BEGIN TRANSACTION;

UPDATE dbo.tx_dirty_lab_303
SET balance = 900.00
WHERE account_id = 1;

-- DỪNG TẠI ĐÂY.
-- Giữ transaction B đang mở, KHÔNG COMMIT.
```

### 4.3. A — reader: dùng READ UNCOMMITTED

Trên **kết nối A**:

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

BEGIN TRANSACTION;

SELECT account_id, balance
FROM dbo.tx_dirty_lab_303
WHERE account_id = 1;

-- Ở lịch thực thi này, A có thể thấy 900.00
-- dù B chưa commit.
```

`READ UNCOMMITTED` của SQL Server cho phép đọc những thay đổi chưa commit trong các trường hợp như ví dụ.

### 4.4. B rollback, A đọc lại

Quay lại **kết nối B**:

```sql
ROLLBACK TRANSACTION;
```

Sau đó ở **kết nối A**:

```sql
SELECT account_id, balance
FROM dbo.tx_dirty_lab_303
WHERE account_id = 1;

COMMIT TRANSACTION;
```

A đọc lại **1000.00**. Giá trị **900.00** ở lần đầu là một thay đổi B đã bỏ đi.

Sau thực hành, đưa mức cô lập của kết nối A về giá trị phù hợp với ứng dụng, ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

### 4.5. Vì sao cùng lịch chạy ở READ COMMITTED có thể bị chặn?

Với SQL Server dùng READ COMMITTED kiểu **khóa** truyền thống, khi B đang giữ khóa ghi trên hàng, A thường phải **chờ B commit hoặc rollback** trước khi đọc hàng đó. Nếu database bật **READ_COMMITTED_SNAPSHOT**, A có thể đọc phiên bản **đã commit trước đó** thay vì chờ. Cả hai cách đều ngăn A đọc giá trị chưa commit của B.

Không nên khẳng định mọi cơ chế READ COMMITTED đều chặn reader bằng cùng một loại lock: điều này tùy DBMS và cấu hình snapshot/versioning.

### 4.6. NOLOCK không phải cách "tăng tốc miễn phí"

SQL Server có table hint `WITH (NOLOCK)`, thường tương ứng ý tưởng đọc không giữ các khóa chia sẻ dữ liệu và cho phép dirty read:

```sql
-- Chỉ minh họa cú pháp SQL Server, không khuyến khích cho báo cáo tiền:
SELECT balance
FROM dbo.tx_dirty_lab_303 WITH (NOLOCK)
WHERE account_id = 1;
```

Ngoài dirty read, việc đọc khi dữ liệu đang thay đổi còn có thể dẫn đến các kết quả quét không ổn định tùy tình huống. `NOLOCK` không có nghĩa tuyệt đối không bị khóa và không biến số liệu thành chính xác.

**Với tiền, kiểm toán, đơn hàng và tồn kho, không nên chọn NOLOCK chỉ để tránh chờ mà bỏ qua tính đúng đắn.**

---

## 5. Đọc không lặp lại: cùng hàng, hai giá trị sau COMMIT

Non-repeatable read xảy ra khi một giao dịch A đọc **một hàng xác định**, B commit thay đổi của hàng đó, rồi A đọc lại cùng hàng và nhận giá trị khác.

### 5.1. Lịch thực thi

Ban đầu, mặt hàng 101 có giá 100.

| Bước | A — reader | B — writer |
| ---: | --- | --- |
| 1 | `BEGIN` | — |
| 2 | `SELECT price WHERE item_id=101` → **100** | — |
| 3 | — | `BEGIN` |
| 4 | — | `UPDATE price=130 WHERE item_id=101` |
| 5 | — | `COMMIT` |
| 6 | `SELECT price WHERE item_id=101` → **130** | — |
| 7 | `COMMIT` | — |

Lần đọc thứ hai của A cho kết quả khác trong **cùng transaction A**.

### 5.2. Dirty read và non-repeatable read không phải một

Ở đây B **đã commit** trước khi A quan sát 130. Vì vậy đây **không phải** dirty read.

Điều đáng chú ý là transaction A không có **góc nhìn cố định** về giá trị của cùng một hàng qua hai lần `SELECT`.

### 5.3. Đọc lại cùng khóa, không chỉ cùng câu SELECT bất kỳ

Một ví dụ rõ ràng:

```sql
SELECT price
FROM catalog
WHERE item_id = 101;
```

Nếu lần đầu trả 100, lần sau trả 130 (và B đã commit thay đổi giữa hai lần), ta dễ nhận diện non-repeatable read.

Nếu query đổi điều kiện, ví dụ lần hai có thêm `WHERE price > 120`, ta không còn so sánh hai lần đọc cùng điều kiện. Cần giữ **khóa và câu hỏi nghiệp vụ giống nhau** để xác định hiện tượng.

---

## 6. Chuẩn bị bộ dữ liệu PostgreSQL để thực hành hai hiện tượng sau

Các ví dụ về **non-repeatable read** và **phantom read** có thể thực hiện rõ ràng trên PostgreSQL ở mức `READ COMMITTED`.

**Lưu ý về bảng dùng chung:** hai kết nối độc lập cần nhìn thấy **cùng bảng dữ liệu**. Vì vậy bài học sử dụng một **bảng thường trong database thử nghiệm**, không phải `CREATE TEMP TABLE`; bảng tạm PostgreSQL thuộc về từng session và không dùng chung cho kịch bản hai kết nối.

Trên database thử nghiệm, tạo bảng:

```sql
CREATE TABLE tx_orders_lab_303 (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    amount       NUMERIC(12, 2) NOT NULL,
    status       TEXT NOT NULL
);

INSERT INTO tx_orders_lab_303 (
    order_id, customer_id, amount, status
)
VALUES
    (101, 1, 100.00, 'PAID'),
    (102, 1, 200.00, 'PAID'),
    (103, 1,  50.00, 'DRAFT'),
    (201, 2,  75.00, 'PAID');
```

Xem dữ liệu:

```sql
SELECT order_id, customer_id, amount, status
FROM tx_orders_lab_303
ORDER BY order_id;
```

Bảng lúc đầu:

| order_id | customer_id | amount | status |
| ---: | ---: | ---: | --- |
| 101 | 1 | 100.00 | PAID |
| 102 | 1 | 200.00 | PAID |
| 103 | 1 | 50.00 | DRAFT |
| 201 | 2 | 75.00 | PAID |

Câu hỏi báo cáo mẫu:

```sql
SELECT order_id, amount
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
ORDER BY order_id;
```

Ban đầu, khách hàng 1 có **hai đơn PAID** là 101 và 102; tổng tiền PAID là **300.00**.

### Những quy tắc khi thực hành

- Tạo bảng **một lần**, sau đó dùng **hai kết nối A/B** đến cùng database.
- Không mở transaction A và B trong cùng một connection.
- Không đặt `BEGIN` và `COMMIT` của tất cả bước vào một lần thực thi liên tục; chạy xen kẽ theo chỉ dẫn.
- Sau mỗi tình huống phải đóng cả hai transaction trước khi dọn dữ liệu.
- Nếu thấy dữ liệu đã đổi vì thử nghiệm trước, hãy khôi phục `order_id=101` về 100 và xóa `order_id=104` **sau khi mọi transaction đã kết thúc**.
- Không chạy `TRUNCATE` hoặc thay đổi schema trong lúc transaction A/B của bài thực hành vẫn mở.

---

## 7. Thực hành non-repeatable read trong PostgreSQL READ COMMITTED

### Bước 1: A bắt đầu READ COMMITTED và đọc lần đầu

Trên **kết nối A**:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT amount
FROM tx_orders_lab_303
WHERE order_id = 101;

-- Kết quả: 100.00
-- Giữ transaction A đang mở.
```

### Bước 2: B cập nhật rồi COMMIT

Trên **kết nối B**:

```sql
BEGIN;

UPDATE tx_orders_lab_303
SET amount = 130.00
WHERE order_id = 101;

COMMIT;
```

B đã commit giá trị mới 130.

### Bước 3: A đọc lại trong cùng transaction

Trở lại **kết nối A**:

```sql
SELECT amount
FROM tx_orders_lab_303
WHERE order_id = 101;

-- Kết quả: 130.00

COMMIT;
```

Bảng kết quả cho hai lần đọc của A:

| Câu đọc của A | Dữ liệu B đã commit đến đâu? | amount |
| --- | --- | ---: |
| Lần 1 | Trước thay đổi của B | 100.00 |
| Lần 2 | Sau khi B commit | 130.00 |

Đây là **non-repeatable read** của cùng hàng `order_id=101`.

### Vì sao READ COMMITTED cho phép?

Ở PostgreSQL, một `SELECT` thông thường trong giao dịch `READ COMMITTED` thấy **snapshot dữ liệu đã commit tại thời điểm câu lệnh bắt đầu**. Hai câu `SELECT` khác nhau trong cùng transaction có thể bắt đầu vào hai thời điểm khác nhau và nhận hai snapshot khác nhau.

`READ COMMITTED` bảo vệ khỏi việc đọc thay đổi **chưa commit**, nhưng **không cam kết** rằng mỗi lần đọc lại cùng hàng sẽ nhận cùng giá trị.

### Dọn dữ liệu sau ví dụ

Sau khi cả A và B đã kết thúc:

```sql
UPDATE tx_orders_lab_303
SET amount = 100.00
WHERE order_id = 101;
```

Lệnh dọn này chạy **ngoài** hai transaction đang dùng để minh họa, với autocommit bật hoặc tự commit nếu môi trường yêu cầu.

---

## 8. Thực hành ngăn non-repeatable read bằng PostgreSQL REPEATABLE READ

Chạy lại kịch bản trên nhưng đặt transaction A ở mức `REPEATABLE READ`.

### Bước 1: A mở transaction và đọc

Kết nối **A**:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT amount
FROM tx_orders_lab_303
WHERE order_id = 101;

-- 100.00
-- Giữ transaction A mở.
```

Trong PostgreSQL, snapshot của `REPEATABLE READ` được thiết lập khi transaction chạy câu truy vấn thích hợp đầu tiên, không nên suy rằng mọi snapshot luôn được chụp ngay tại lệnh `BEGIN`.

### Bước 2: B cập nhật, COMMIT

Kết nối **B**:

```sql
BEGIN;

UPDATE tx_orders_lab_303
SET amount = 130.00
WHERE order_id = 101;

COMMIT;
```

### Bước 3: A đọc lại

Kết nối **A**:

```sql
SELECT amount
FROM tx_orders_lab_303
WHERE order_id = 101;

-- PostgreSQL REPEATABLE READ, SELECT thông thường: 100.00

COMMIT;
```

Mặc dù B đã commit giá trị 130, A vẫn quan sát **100** qua snapshot của transaction mình. Một transaction mới sau đó có thể thấy 130.

### Ý nghĩa: snapshot nhất quán, không phải khóa vĩnh viễn mọi hàng

A không cần chặn B cập nhật chỉ để tiếp tục đọc bản cũ. PostgreSQL dùng cơ chế phiên bản hàng (*MVCC*) để cung cấp góc nhìn phù hợp của mỗi transaction.

Nhưng nếu A sau đó **thử cập nhật chính hàng mà B đã sửa sau snapshot**, PostgreSQL `REPEATABLE READ` có thể hủy một transaction với lỗi concurrent update/serialization theo quy tắc tương ứng. Không được suy rằng "đã đọc được bản cũ" nghĩa là "được phép ghi đè không xung đột".

Dọn dữ liệu sau khi transaction hoàn tất:

```sql
UPDATE tx_orders_lab_303
SET amount = 100.00
WHERE order_id = 101;
```

---

## 9. Hàng ảo (phantom read): tập hàng phù hợp điều kiện thay đổi

Phantom read không cần một hàng cũ đổi số tiền. Nó thường xảy ra khi B **INSERT** một hàng mới thỏa điều kiện mà A đã dùng, và A chạy lại **cùng truy vấn tập hợp**.

### 9.1. Lịch thực thi

Ban đầu, khách 1 có hai đơn `PAID`: 101 và 102.

| Bước | A — reader | B — writer |
| ---: | --- | --- |
| 1 | `BEGIN` | — |
| 2 | `SELECT order_id WHERE customer_id=1 AND status='PAID'` → **101,102** | — |
| 3 | — | `BEGIN` |
| 4 | — | `INSERT order_id=104, customer_id=1, status='PAID'` |
| 5 | — | `COMMIT` |
| 6 | Chạy lại **cùng SELECT** → **101,102,104** | — |
| 7 | `COMMIT` | — |

Hàng 104 **xuất hiện như một hàng mới trong tập kết quả** ở lần đọc thứ hai: đó là hiện tượng phantom.

### 9.2. Tại sao gọi là "hàng ảo"?

Tên tiếng Anh *phantom* nói đến một hàng **xuất hiện hoặc biến mất khi lặp lại truy vấn theo điều kiện**. Nó không có nghĩa bản ghi này là giả, chưa commit hoặc không tồn tại trên đĩa.

Trong ví dụ, đơn 104 là một hàng **đã được B commit hợp lệ**. Hiện tượng là **tập kết quả A nhìn thấy không ổn định trong cùng transaction**.

### 9.3. Phantom có thể do nhiều thao tác

Một tập truy vấn như:

```sql
WHERE customer_id = 1 AND status = 'PAID'
```

có thể thay đổi khi B commit:

- **INSERT** một đơn mới có `status='PAID'` → hàng xuất hiện.
- **DELETE** một đơn đã `PAID` → hàng biến mất.
- **UPDATE status='DRAFT' → 'PAID'` trên đơn cũ → hàng trước đây ngoài tập nay đi vào tập.
- **UPDATE status='PAID' → 'CANCELLED'` → hàng rời khỏi tập.

Vì vậy, phantom không nhất thiết chỉ do `INSERT`; cốt lõi là **thành viên của tập thỏa predicate thay đổi**.

---

## 10. Thực hành phantom read trong PostgreSQL READ COMMITTED

Đảm bảo đơn `order_id=104` chưa tồn tại. Nếu còn từ lần trước, sau khi đóng các transaction cũ:

```sql
DELETE FROM tx_orders_lab_303
WHERE order_id = 104;
```

### Bước 1: A đọc tập và tổng tiền

Kết nối **A**:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT order_id, amount
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
ORDER BY order_id;

SELECT COUNT(*) AS paid_order_count,
       SUM(amount) AS paid_total
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID';

-- Danh sách: 101,102
-- COUNT = 2, SUM = 300.00
-- Giữ transaction A mở.
```

### Bước 2: B thêm một hàng phù hợp và COMMIT

Kết nối **B**:

```sql
BEGIN;

INSERT INTO tx_orders_lab_303 (
    order_id, customer_id, amount, status
)
VALUES (104, 1, 40.00, 'PAID');

COMMIT;
```

### Bước 3: A lặp lại đúng điều kiện

Kết nối **A**:

```sql
SELECT order_id, amount
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
ORDER BY order_id;

SELECT COUNT(*) AS paid_order_count,
       SUM(amount) AS paid_total
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID';

-- Danh sách: 101,102,104
-- COUNT = 3, SUM = 340.00

COMMIT;
```

Kết quả có thể diễn giải:

| Lần đọc của A | order_id trong kết quả | COUNT | SUM |
| --- | --- | ---: | ---: |
| Trước khi B commit | 101, 102 | 2 | 300.00 |
| Sau khi B commit | 101, 102, 104 | 3 | 340.00 |

**Chính sự xuất hiện của ID 104** khiến đây là ví dụ phantom rõ ràng, không chỉ là tổng tiền thay đổi.

Dọn dữ liệu sau khi A/B kết thúc:

```sql
DELETE FROM tx_orders_lab_303
WHERE order_id = 104;
```

### Vì sao chỉ so sánh SUM chưa đủ?

Giả sử B **chỉ cập nhật amount của order 101 từ 100 lên 140**. Lúc đó:

- Tổng tăng từ 300 lên 340.
- Nhưng danh sách hàng có thể vẫn là 101 và 102.

Kết quả `SUM` thay đổi **chưa chứng minh có phantom**; có thể là non-repeatable read của giá trị cột trong hàng có sẵn. Để phân biệt, nên quan sát **tập khóa `order_id`** và cột cần đo.

---

## 11. Thực hành ngăn phantom ở PostgreSQL REPEATABLE READ

Đặt A ở mức `REPEATABLE READ` và giữ nguyên lịch chèn hàng của B.

### A: snapshot đầu tiên

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT order_id
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
ORDER BY order_id;

-- 101,102
-- Giữ A mở.
```

### B: chèn đơn mới và COMMIT

```sql
BEGIN;

INSERT INTO tx_orders_lab_303 (
    order_id, customer_id, amount, status
)
VALUES (104, 1, 40.00, 'PAID');

COMMIT;
```

### A: đọc lại

```sql
SELECT order_id
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
ORDER BY order_id;

-- PostgreSQL REPEATABLE READ: vẫn 101,102

COMMIT;
```

Sau khi A kết thúc và bắt đầu **transaction khác**, đơn 104 đã commit có thể xuất hiện.

Dọn dữ liệu:

```sql
DELETE FROM tx_orders_lab_303
WHERE order_id = 104;
```

### Một khác biệt quan trọng giữa chuẩn và PostgreSQL

Theo **bảng mức cô lập cổ điển của chuẩn SQL**, `REPEATABLE READ` được yêu cầu ngăn dirty read và non-repeatable read, nhưng **phantom read vẫn có thể được phép**.

Tuy nhiên, PostgreSQL triển khai `REPEATABLE READ` bằng một snapshot nhất quán cho transaction và **cũng ngăn phantom đối với các câu SELECT thông thường**. Vì thế, không được nói “REPEATABLE READ chắc chắn có phantom” khi đang mô tả PostgreSQL.

Mức bảo vệ trên thực tế có thể **mạnh hơn mức tối thiểu trong bảng chuẩn**.

---

## 12. Phân biệt theo khóa hàng và predicate

Ba hiện tượng dễ bị nhầm nếu chỉ nói chung chung “đọc hai lần không giống nhau”.

### 12.1. Cùng hàng, cột thay đổi

```sql
SELECT amount
FROM tx_orders_lab_303
WHERE order_id = 101;
```

Lần 1 là 100; B commit `UPDATE amount=130`; lần 2 là 130. Đây là **non-repeatable read** điển hình.

### 12.2. Hàng mới phù hợp điều kiện

```sql
SELECT order_id
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID';
```

Lần 1 có 101,102; B commit `INSERT 104`; lần 2 có 101,102,104. Đây là **phantom read** điển hình.

### 12.3. Hàng cũ đổi status rồi đi vào tập

Giả sử order 103 đã tồn tại nhưng `status='DRAFT'`, nên không nằm trong tập `PAID`. B commit:

```sql
UPDATE tx_orders_lab_303
SET status = 'PAID'
WHERE order_id = 103;
```

A chạy lại predicate `status='PAID'` và thấy thêm order 103. Đây có thể được mô tả là **phantom theo thay đổi thành viên của tập**, dù cơ chế nguồn là UPDATE chứ không phải INSERT.

### 12.4. Hai hiện tượng có thể cùng xảy ra

B có thể vừa cập nhật amount của order 101 vừa thêm order 104 rồi commit. A đọc lần hai sẽ thấy:

- `amount` của order 101 đổi: non-repeatable read.
- order 104 xuất hiện: phantom read.

Không cần buộc một lịch nhiều thay đổi chỉ thuộc **một** loại. Hãy chỉ ra từng quan sát cụ thể.

### 12.5. Một hàng bị xóa thì xếp loại thế nào?

Nếu A đọc theo **khóa cụ thể**, B xóa và commit, lần đọc sau A không tìm thấy hàng, đây là thay đổi đối với bản ghi đã đọc; một số tài liệu phân loại hiện tượng theo cách mô tả non-repeatable read rộng.

Nếu A đọc **tập hàng theo điều kiện** và một thành viên biến mất, ta nhìn thấy sự **thay đổi tập kết quả** theo predicate, thường dùng để giải thích phantom.

Điều quan trọng trong bài thực hành là mô tả **đúng lịch thao tác và tiêu chí quan sát**, không tranh luận tên gọi dựa trên một dòng ví dụ mơ hồ.

---

## 13. Ma trận isolation level theo cách diễn đạt cổ điển

Chuẩn SQL thường giới thiệu bốn mức cô lập:

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| **READ UNCOMMITTED** | Có thể | Có thể | Có thể |
| **READ COMMITTED** | Không | Có thể | Có thể |
| **REPEATABLE READ** | Không | Không | Có thể theo mô hình cổ điển |
| **SERIALIZABLE** | Không | Không | Không |

**Cách đọc bảng:** “Có thể” nghĩa là mức này **không có bảo đảm phải ngăn** hiện tượng đó theo mô hình; không có nghĩa cứ đặt mức đó là anomaly sẽ luôn xuất hiện. “Không” nghĩa là mức đó được kỳ vọng ngăn loại hiện tượng tương ứng.

Bảng trên là cách giảng giải **cổ điển**. DBMS thực tế có thể dùng MVCC, statement snapshot, transaction snapshot, khóa phạm vi hoặc kiểm tra xung đột để cung cấp hành vi khác mức tối thiểu.

### READ UNCOMMITTED

Cho phép mức cô lập thấp nhất trong bảng cổ điển. Nó có thể đọc dữ liệu chưa commit ở DBMS hỗ trợ dirty read. Không phù hợp cho số liệu cần tính chính xác dựa trên giao dịch hoàn tất.

### READ COMMITTED

Chỉ đọc dữ liệu đã commit theo ngữ nghĩa DBMS. Dữ liệu có thể đổi giữa **hai câu SELECT trong một transaction**, vì các câu lệnh có thể thấy những commit khác nhau.

### REPEATABLE READ

Nhắm tới ổn định khi đọc lại dữ liệu đã đọc. Tuy nhiên, cách xử lý **predicate/range và các hàng mới** khác nhau theo sản phẩm: một hệ bảo vệ bằng khóa hàng và vẫn có phantom, hệ khác cung cấp transaction snapshot nên không thấy phantom trong các consistent reads.

### SERIALIZABLE

Nhắm tới kết quả **tương đương một thứ tự chạy tuần tự** của các transaction, dù thực tế chúng có thể chồng lấn. Đây là mức bảo vệ mạnh nhất trong nhóm mức cô lập phổ biến, nhưng có thể phát sinh **chờ khóa, deadlock hoặc lỗi serialization** cần ứng dụng xử lý và retry.

**Không nên hiểu SERIALIZABLE là mọi transaction luôn được chạy từng cái một theo thứ tự cứng.** DBMS có thể cho phép chạy song song rồi phát hiện một lịch không thể tuần tự hóa.

---

## 14. PostgreSQL: cách mức cô lập hoạt động thực tế

Ở PostgreSQL, cần ghi nhớ các quy tắc thực hành sau:

| Mức khai báo | Hành vi đáng chú ý của SELECT thông thường |
| --- | --- |
| `READ UNCOMMITTED` | Được PostgreSQL xử lý như `READ COMMITTED`; **không dirty read** |
| `READ COMMITTED` | Mỗi câu lệnh đọc thấy một snapshot phù hợp của dữ liệu đã commit; non-repeatable/phantom có thể xuất hiện giữa các câu lệnh |
| `REPEATABLE READ` | Snapshot ổn định trong transaction; ngăn non-repeatable/phantom cho các consistent reads; vẫn có thể có serialization anomaly khác |
| `SERIALIZABLE` | Cung cấp kiểm tra tuần tự hóa; có thể hủy transaction với lỗi serialization, ứng dụng cần retry |

### Vì sao READ UNCOMMITTED không cho dirty read trong PostgreSQL?

PostgreSQL áp dụng cơ chế MVCC và hiện không triển khai chế độ cho transaction đọc dữ liệu chưa commit theo cách dirty read cổ điển. Vì thế:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT ...
```

trong PostgreSQL vẫn không trở thành phép đọc các UPDATE chưa commit của session khác.

Nếu B đang cập nhật 100 thành 130 nhưng chưa commit, một `SELECT` thường của A ở `READ UNCOMMITTED` theo PostgreSQL thấy **phiên bản đã commit phù hợp**, không phải 130 chưa commit.

### PostgreSQL REPEATABLE READ vẫn có giới hạn gì?

Nó giữ snapshot nhất quán, nhưng **snapshot isolation không tự đồng nghĩa serializable**.

Ví dụ có hai bác sĩ A và B đều đang trực. Quy tắc: phải có ít nhất một bác sĩ trực. Hai transaction đồng thời:

1. Cùng đọc snapshot thấy **2** người trực.
2. Transaction T1 cho A nghỉ.
3. Transaction T2 cho B nghỉ.
4. Mỗi transaction sửa **một hàng khác nhau** và có thể đều commit ở mức snapshot isolation.
5. Kết quả cuối có **0** người trực, vi phạm quy tắc “ít nhất một người”.

Đây là dạng **write skew/serialization anomaly**, khác với ba hiện tượng đọc đơn giản trong bài. Nó cho thấy **ngăn dirty/non-repeatable/phantom chưa đủ chứng minh mọi nghiệp vụ liên quan nhiều hàng đều an toàn**.

PostgreSQL `SERIALIZABLE` có thể phát hiện các lịch không tuần tự hóa được và hủy một transaction. Ứng dụng phải có chiến lược retry toàn transaction khi gặp lỗi phù hợp.

---

## 15. MySQL/InnoDB: phân biệt consistent read và locking/current read

Với **InnoDB** của MySQL, ví dụ mặc định thường dùng `REPEATABLE READ` và MVCC. Nhưng trong InnoDB cần phân biệt:

- **Consistent nonlocking read:** `SELECT` thông thường đọc theo phiên bản/snapshot phù hợp.
- **Locking/current read:** `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE` và các thao tác cập nhật/khóa theo quy tắc hiện hành.

### 15.1. Consistent read ở READ COMMITTED

Trong InnoDB `READ COMMITTED`, các `SELECT` thông thường có thể nhận snapshot mới ở các câu lệnh khác nhau. Vì vậy, lịch A đọc 100 → B commit 130 → A đọc 130 là non-repeatable read điển hình.

### 15.2. Consistent read ở REPEATABLE READ

Trong InnoDB `REPEATABLE READ`, sau khi read view được thiết lập cho các consistent reads, những lần `SELECT` tiếp theo trong cùng transaction thường giữ góc nhìn phù hợp đó. Với bảng nguồn ví dụ, A có thể tiếp tục thấy 100 dù B đã commit 130.

Tương tự, nếu B chèn một hàng mới sau khi A có snapshot, các consistent reads của A thường không thấy hàng mới đó, nên phantom theo cách lặp `SELECT` đơn giản không xuất hiện.

### 15.3. Nhưng UPDATE và SELECT FOR UPDATE không đơn thuần dùng snapshot cũ

Không nên suy ra: “MySQL REPEATABLE READ nghĩa là mọi câu lệnh đều mãi thấy một snapshot y hệt nhau”.

Trong InnoDB, các locking/current reads và thao tác ghi có cơ chế xác định, khóa và nhìn dữ liệu khác với consistent nonlocking reads. Một transaction có thể nhìn thấy kết quả khác giữa:

```sql
SELECT * FROM inventory WHERE sku = 'A';
```

và:

```sql
SELECT * FROM inventory WHERE sku = 'A' FOR UPDATE;
```

tùy lịch thực thi và trạng thái khóa. Với truy vấn theo dải, InnoDB có các cơ chế **next-key/gap locking** trong những điều kiện và mức cô lập thích hợp để bảo vệ việc khóa phạm vi.

### 15.4. Không đánh đồng gap lock với mọi cách ngăn phantom

Gap/next-key locking phụ thuộc index, predicate, mức cô lập và kiểu đọc. Một `SELECT` thông thường dùng snapshot không nhất thiết khóa mọi vị trí mà hàng mới có thể được chèn. Cơ chế chống phantom cho **consistent read** và cơ chế khóa dải cho **locking read** là hai ý tưởng khác nhau.

Khi làm bài thực hành MySQL, nên ghi rõ:

- Storage engine **InnoDB**.
- Mức isolation của **session**.
- `SELECT` là nonlocking hay `FOR UPDATE`.
- Read view được tạo tại thời điểm nào.
- Có transaction nào đang giữ khóa và liệu một statement đang **chờ** không.

### 15.5. Thiết lập isolation trong MySQL

Có thể thiết lập isolation cho session trước khi bắt đầu transaction:

```sql
-- MySQL, chạy ở kết nối thực hành.
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

-- SELECT ở đây.

COMMIT;
```

Thay bằng `REPEATABLE READ` khi muốn khảo sát consistent snapshot. Để thấy dirty read ở một hệ hỗ trợ, MySQL/InnoDB có mức `READ UNCOMMITTED`, nhưng không nên dùng dữ liệu nghiệp vụ thật để thử đọc những thay đổi chưa commit.

---

## 16. SQL Server: locking READ COMMITTED và RCSI

Trong SQL Server, **READ COMMITTED** có thể dựa vào **khóa** hoặc cơ chế **row versioning**, tùy cấu hình database.

### 16.1. READ COMMITTED dùng khóa

Một reader có thể chờ writer đang giữ khóa chưa commit. Khi writer commit, câu lệnh đọc có thể tiếp tục và đọc giá trị đã commit. Điều đó ngăn dirty read nhưng không giữ một snapshot xuyên suốt transaction cho mọi câu `SELECT`.

### 16.2. READ_COMMITTED_SNAPSHOT (RCSI)

Nếu database bật `READ_COMMITTED_SNAPSHOT`, nhiều lần đọc ở READ COMMITTED dùng row versioning theo **statement-level snapshot**. Reader có thể không cần chờ writer chỉ để đọc một phiên bản đã commit trước đó.

Tuy nhiên, **snapshot ở mức câu lệnh** khác **snapshot ở mức transaction**:

- Câu `SELECT` 1 bắt đầu trước commit của B → có thể thấy giá trị cũ.
- Câu `SELECT` 2 bắt đầu sau commit của B → có thể thấy giá trị mới.

Vì vậy, RCSI **không tự ngăn non-repeatable read hay phantom giữa hai câu lệnh** trong cùng transaction.

### 16.3. SNAPSHOT isolation

SQL Server có mức `SNAPSHOT` riêng, với điều kiện cấu hình database phù hợp. Mức này cho các thao tác đọc phiên bản một góc nhìn nhất quán theo transaction và có cơ chế xử lý xung đột khi ghi. Nó không đồng nhất với `READ COMMITTED` chỉ vì cả hai đều có thể dùng row versioning.

### 16.4. REPEATABLE READ và SERIALIZABLE kiểu locking

Theo hành vi khóa phổ biến của SQL Server:

- `REPEATABLE READ` giữ các khóa cần thiết để những hàng đã đọc không bị giao dịch khác sửa trong lúc transaction còn mở. Nhưng các hàng **mới phù hợp predicate** có thể được chèn nếu không có bảo vệ phạm vi phù hợp.
- `SERIALIZABLE` có thể dùng khóa phạm vi khóa (*key-range locking*) cùng cơ chế khác để bảo vệ tính tuần tự hóa của truy vấn.

Cơ chế cụ thể phụ thuộc kế hoạch truy vấn, index và cấu hình. Không nên suy rằng một `SELECT FOR UPDATE` kiểu PostgreSQL hoặc một table hint SQL Server là “bản dịch cú pháp” hoàn toàn tương đương của nhau.

---

## 17. Oracle và SQLite: một số khác biệt cần nhớ

### Oracle Database

Oracle có cơ chế multi-version read consistency. Ở mức `READ COMMITTED`, mỗi câu truy vấn thông thường có góc nhìn nhất quán của chính câu lệnh; vì vậy có thể thấy kết quả khác giữa hai câu `SELECT` trong một transaction.

Oracle còn hỗ trợ `SERIALIZABLE` với hành vi snapshot/kiểm soát xung đột riêng. Không nên áp bảng khóa của SQL Server trực tiếp lên Oracle mà không kiểm tra cấu trúc transaction và lỗi có thể phát sinh.

Ở Oracle, cần phân biệt:

- **Statement-level read consistency**: ổn định trong một câu truy vấn.
- **Transaction-level consistency**: góc nhìn ổn định qua nhiều câu ở mức/cấu hình phù hợp.
- **Serializability thực tế**: không chỉ suy từ việc các câu `SELECT` lặp lại trả cùng hàng.

### SQLite

SQLite có cơ chế transaction, journaling/WAL và khóa đọc/ghi khác các hệ client-server truyền thống. Theo mặc định, các connection độc lập thường không thấy thay đổi chưa commit của nhau.

Một ngoại lệ đặc biệt có thể liên quan đến **shared-cache mode** kết hợp `PRAGMA read_uncommitted`, nhưng đây **không phải mặc định** để suy rằng mọi SQLite đều hỗ trợ dirty read qua hai kết nối bình thường.

Với SQLite, hiện tượng một reader giữ snapshot trong WAL, hoặc gặp khóa/`SQLITE_BUSY_SNAPSHOT` khi chuyển từ đọc sang ghi, không nên giải thích bằng cách chép nguyên lịch khóa của SQL Server.

**Bài học chung:** cùng nhãn isolation chưa chắc có cách thực thi hoàn toàn giống nhau. Luôn xác định **DBMS, storage engine, phiên bản, cài đặt và kiểu truy vấn** khi chẩn đoán.

---

## 18. Một câu SELECT thường có tính nhất quán riêng, dù giao dịch không lặp lại được

Một hiểu lầm phổ biến là: “READ COMMITTED cho phép dữ liệu thay đổi, vậy một câu `SELECT` dài có thể thấy nửa dữ liệu cũ, nửa dữ liệu mới bất kỳ”.

Cần phân biệt **sự nhất quán trong một câu lệnh** với **sự nhất quán giữa nhiều câu lệnh**.

Trong PostgreSQL READ COMMITTED, một `SELECT` thông thường dựa trên snapshot phù hợp tại thời điểm câu lệnh bắt đầu. Nó không tự động cập nhật snapshot giữa chừng chỉ vì B commit trong lúc câu `SELECT` đó đang chạy.

Ví dụ:

```sql
SELECT order_id, amount
FROM tx_orders_lab_303
WHERE customer_id = 1;
```

được hiểu trong snapshot của câu `SELECT` đó. Nếu chạy **một câu SELECT khác** sau commit của B, câu mới có thể thấy snapshot khác.

Các cơ chế khóa, current read, DML và những ngoại lệ theo DBMS có quy tắc riêng; không nên nâng mệnh đề trên thành một cam kết chung cho mọi sản phẩm, mọi câu SQL hoặc mọi mức cô lập.

---

## 19. MVCC, khóa và snapshot: cơ chế đứng sau các kết quả

Ba hiện tượng đọc dễ hiểu hơn khi tách **kết quả người dùng quan sát** khỏi **cách DBMS ngăn hiện tượng**.

### MVCC — Multi-Version Concurrency Control

Trong MVCC, một hàng có thể có nhiều phiên bản logic trong hệ thống. Một transaction đọc phiên bản phù hợp với snapshot mà nó được phép quan sát.

Hình dung:

```text
Bảng giao dịch / row versions

order 101:
  version V1: amount=100, đã commit tại t0
  version V2: amount=130, B commit tại t2

SELECT A ở READ COMMITTED:
  bắt đầu t1 → snapshot thấy V1 → amount=100
  bắt đầu t3 → snapshot thấy V2 → amount=130

SELECT A ở PostgreSQL REPEATABLE READ:
  snapshot được chốt trước t2
  đọc tại t1 và t3 → đều thấy V1 → amount=100
```

MVCC có thể cho phép reader tiếp tục đọc phiên bản cũ mà không chặn mọi writer. Nhưng nó không bảo đảm giải quyết tất cả xung đột ghi hay yêu cầu nghiệp vụ nhiều hàng.

### Khóa hàng và khóa phạm vi

Một cơ chế locking có thể:

- Giữ khóa để ngăn thay đổi hàng đã đọc trước khi transaction kết thúc.
- Khóa các phạm vi index để hạn chế các hàng mới lọt vào predicate.
- Khi xảy ra tranh chấp, buộc transaction khác **chờ** hoặc kết thúc với lỗi.

Khóa **hàng hiện có** không đồng nghĩa khóa **mọi vị trí có thể chèn hàng mới**. Đây là nguyên nhân mà một số triển khai `REPEATABLE READ` theo khóa có thể ngăn non-repeatable read nhưng vẫn có phantom.

### Snapshot có thể ổn định mà vẫn chưa serializable

Một transaction snapshot có thể đọc lặp lại cùng dữ liệu nhưng hai transaction khác nhau vẫn có thể cùng đưa ra quyết định dựa trên thông tin cũ, tạo **write skew**. Mức `SERIALIZABLE` của DBMS phải xử lý những chu kỳ phụ thuộc đó bằng cơ chế phù hợp, không chỉ bằng việc giữ các giá trị đọc ổn định.

---

## 20. "Phantom" không nhất thiết là hàng được INSERT mới

Hãy xét tập đơn đã thanh toán:

```sql
WHERE customer_id = 1
  AND status = 'PAID'
```

Ban đầu có:

```text
101 PAID
102 PAID
103 DRAFT
```

Nếu B đổi 103 thành PAID:

```sql
UPDATE tx_orders_lab_303
SET status = 'PAID'
WHERE order_id = 103;
```

sau B commit, A đọc lại tập và thấy thêm 103. Về mặt quan sát predicate, đây là một **hàng mới lọt vào tập kết quả**.

Nếu B đổi 101 từ PAID thành CANCELLED, A thấy 101 biến mất khỏi tập. Nếu A đọc hàng 101 theo khóa riêng, nó cũng có thể thấy cột `status` đổi.

### Phân biệt câu hỏi "hàng nào" và "tập nào"

| Câu hỏi của A | Điều cần quan sát |
| --- | --- |
| `SELECT status FROM orders WHERE order_id=103` | Giá trị `status` của **một hàng định danh cố định** |
| `SELECT order_id FROM orders WHERE status='PAID'` | **Tập khóa** hiện thỏa predicate |
| `SELECT COUNT(*) FROM orders WHERE status='PAID'` | Số phần tử của **tập khóa** |
| `SELECT SUM(amount) FROM orders WHERE status='PAID'` | Giá trị tổng hợp; có thể đổi do nhiều nguyên nhân |

Trong bài kiểm tra hiện tượng, đừng chỉ nhìn tổng hợp mà không quan sát **danh sách khóa** hoặc **diễn biến commit**.

---

## 21. Hành vi khi một transaction tự sửa dữ liệu của nó

Câu hỏi: “Nếu A tự UPDATE giữa hai lần SELECT của chính A, lần đọc thứ hai khác, vậy có phải non-repeatable read?”

Trong phân tích anomaly giữa transaction, **không**. Các định nghĩa được dùng trong bài này nói tới việc **một giao dịch khác** gây ra thay đổi mà A quan sát trong cùng giao dịch.

Ví dụ:

```sql
BEGIN;

SELECT amount FROM tx_orders_lab_303 WHERE order_id = 101;

UPDATE tx_orders_lab_303
SET amount = amount + 5
WHERE order_id = 101;

SELECT amount FROM tx_orders_lab_303 WHERE order_id = 101;

ROLLBACK;
```

Nếu A tự sửa 100 thành 105, việc A nhìn thấy 105 là **đọc thay đổi của chính mình** (*read your own writes*) theo quy tắc DBMS, không phải ví dụ non-repeatable read do B commit.

Tương tự, nếu A tự INSERT order 104 rồi truy vấn lại và thấy 104, đó không phải phantom gây ra bởi transaction khác.

**Trong lịch thực hành, phải đánh dấu rõ ai ghi, ai commit và ai đọc.**

---

## 22. Một số dấu hiệu đánh lừa khi làm bài tập

### 22.1. Hai SELECT đặt ở hai transaction khác nhau

```sql
SELECT amount FROM orders WHERE id=1; -- transaction tự động 1
SELECT amount FROM orders WHERE id=1; -- transaction tự động 2
```

Nếu giá khác nhau, không đủ thông tin để nói đó là **non-repeatable read trong cùng transaction**. Hãy kiểm tra autocommit và ranh giới `BEGIN/COMMIT`.

### 22.2. B chỉ UPDATE nhưng chưa COMMIT

Nếu A đọc giá mới **trước commit** và DBMS cho phép điều đó, đây là dirty read. Không nên gọi nó là non-repeatable read chỉ vì số tiền khác lần đọc trước.

### 22.3. A bị chặn bởi lock, không trả dữ liệu ngay

Một câu `SELECT` đang **chờ** không đồng nghĩa A đã đọc dirty/non-repeatable/phantom. Hiện tượng phải được xác định từ **giá trị hoặc tập hàng thật sự được trả**, không chỉ từ việc truy vấn chưa hoàn tất.

### 22.4. A dùng ORDER BY khác nhau

Lần đầu `ORDER BY amount DESC` và lần sau `ORDER BY order_id` có thể đổi **thứ tự hiển thị** mà tập hàng không đổi. Thứ tự hàng khác không tự chứng minh có phantom.

Muốn so sánh tập hàng, hãy dùng khóa và `ORDER BY` cố định hoặc phép so sánh tập hợp.

### 22.5. LIMIT/OFFSET khiến hàng “xuất hiện” vì phân trang

Nếu A dùng `LIMIT 10 OFFSET 10`, B chèn một hàng ở đầu thứ tự, tập hàng trên trang 2 có thể dịch. Hiện tượng nhìn thấy ở **trang** không tự chứng minh rằng một hàng mới thỏa **predicate nghiệp vụ**, vì điều kiện phân trang cũng thay đổi vị trí. Cần kiểm tra câu truy vấn đầy đủ, keyset pagination và snapshot phù hợp.

### 22.6. Đồng hồ của ứng dụng không quyết định thứ tự commit

Hai request có timestamp ứng dụng khác nhau không đủ để biết DBMS commit transaction nào trước. Khi làm lịch anomaly, dùng **thứ tự thực thi/commit quan sát trong DBMS**, không chỉ thời điểm request được gửi.

---

## 23. READ COMMITTED không đồng nghĩa một báo cáo nhiều câu có cùng snapshot

Giả sử dịch vụ lập báo cáo bằng ba câu:

```sql
SELECT COUNT(*) FROM orders WHERE status='PAID';
SELECT SUM(amount) FROM orders WHERE status='PAID';
SELECT COUNT(*) FROM orders WHERE status='DRAFT';
```

Ở `READ COMMITTED` theo kiểu snapshot mỗi statement, nếu B commit thay đổi giữa những câu này, các kết quả có thể phản ánh **những thời điểm khác nhau**.

Ví dụ:

1. A đếm `PAID = 10`.
2. B chuyển một đơn `DRAFT → PAID` rồi commit.
3. A tính tổng PAID với **11 đơn**.
4. A đếm DRAFT sau chuyển trạng thái.

Báo cáo có thể tự mâu thuẫn nếu ứng dụng muốn toàn bộ các chỉ tiêu tương ứng **một thời điểm logic**.

### Cách nghĩ để thiết kế báo cáo

- Nếu từng câu chỉ cần dữ liệu đã commit ở thời điểm chạy, `READ COMMITTED` có thể đủ.
- Nếu nhiều câu phải đọc **một ảnh chụp dữ liệu nhất quán**, cân nhắc một transaction với isolation/snapshot phù hợp DBMS.
- Nếu báo cáo tạo quyết định ghi phức tạp, snapshot ổn định chưa đủ; cần phân tích xung đột và tính tuần tự hóa.

Một cách khác là gộp các chỉ tiêu trong **một câu SELECT** nếu ngữ nghĩa phù hợp, ví dụ:

```sql
SELECT
    COUNT(*) FILTER (WHERE status='PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status='PAID') AS paid_total,
    COUNT(*) FILTER (WHERE status='DRAFT') AS draft_count
FROM tx_orders_lab_303;
```

Ví dụ này dùng cú pháp `FILTER` của PostgreSQL. Các chỉ tiêu được tính trong **một statement**, nên có cùng snapshot của câu lệnh trong những điều kiện đọc đã nêu, thay vì có nguy cơ snapshot khác nhau giữa ba statement.

**Nhưng** một SELECT lớn không tự chứng minh mọi quyết định ghi tiếp theo sẽ an toàn; phạm vi bảo đảm phải dựa trên nghiệp vụ và isolation.

---

## 24. Vì sao chỉ dùng SELECT FOR UPDATE không giải quyết tất cả phantom?

Một lời khuyên phổ biến là: “Thêm `FOR UPDATE` vào truy vấn thì hết mọi vấn đề đồng thời”. Điều này quá đơn giản.

Trong PostgreSQL:

```sql
BEGIN;

SELECT *
FROM tx_orders_lab_303
WHERE customer_id = 1
  AND status = 'PAID'
FOR UPDATE;

-- ...
COMMIT;
```

`FOR UPDATE` giúp khóa **những hàng thực sự được chọn** để hạn chế transaction khác sửa/xóa các hàng đó trong lúc khóa còn hiệu lực.

Tuy nhiên, ở `READ COMMITTED`, việc khóa **những hàng đã có** không tự bảo vệ toàn bộ **predicate** khỏi một transaction khác chèn **một hàng mới** phù hợp. Do đó `SELECT ... FOR UPDATE` một vài hàng không phải cách ngăn phantom tổng quát trên PostgreSQL.

Các DBMS khác có cách dùng range/gap locks và mức cô lập khác. Không được bê một lời giải locking của MySQL hoặc SQL Server sang PostgreSQL rồi kết luận hành vi như nhau.

### Khi nào cần khóa?

Khóa hữu ích khi nghiệp vụ yêu cầu:

- Không cho hai giao dịch cùng thay đổi một hàng theo cách xung đột.
- Đọc một hàng rồi cập nhật chính hàng đó một cách có kiểm soát.
- Bảo vệ một invariant với cơ chế locking phù hợp.

Nhưng để bảo vệ một điều kiện liên quan **những hàng chưa tồn tại**, cần suy nghĩ về **phạm vi predicate, serialization, ràng buộc dữ liệu và chiến lược transaction**, không chỉ về khóa các hàng đã tìm thấy.

---

## 25. Serializability và yêu cầu giao dịch phải retry

Một lịch chạy **serializable** là lịch có kết quả tương đương một thứ tự chạy các transaction **tuần tự**, theo mô hình bảo đảm của DBMS.

Ví dụ hai giao dịch:

- T1 đọc rằng còn một suất đặt chỗ rồi giữ suất.
- T2 cũng đọc rằng còn một suất rồi giữ suất.

Nếu cả hai cùng commit theo logic thiếu bảo vệ, hệ thống có thể bán hai suất cho một chỗ. Mức SERIALIZABLE hoặc một ràng buộc/thiết kế ghi dữ liệu thích hợp có thể phát hiện và ngăn lịch sai.

### Trong PostgreSQL, có thể gặp lỗi serialization

```text
SQLSTATE 40001 — serialization_failure
```

Ứng dụng khi gặp lỗi loại này thường cần **retry toàn bộ transaction**, không chỉ retry câu SQL cuối cùng một cách tùy ý, bởi kết quả đọc và quyết định đã được tính theo snapshot trước đó.

Mẫu tư duy:

```text
Bắt đầu transaction
  → đọc dữ liệu liên quan
  → kiểm tra điều kiện nghiệp vụ
  → ghi thay đổi
  → COMMIT
       ├── thành công → hoàn tất
       └── serialization failure
              → ROLLBACK
              → retry TOÀN transaction có giới hạn
```

### Cẩn trọng khi retry

- Chỉ retry lỗi có chính sách phù hợp, không nuốt mọi lỗi dữ liệu.
- Giới hạn số lần và dùng backoff khi cần.
- Bảo đảm tác dụng phụ bên ngoài transaction, như gửi email hoặc thanh toán, không bị thực hiện trùng.
- Với dữ liệu số dư/tồn kho, đặt ràng buộc và quy tắc idempotency bên cạnh isolation.
- Log và theo dõi tỉ lệ serialization failure để phát hiện contention bất thường.

**SERIALIZABLE không phải lựa chọn miễn phí về hiệu năng.** Nó cung cấp bảo đảm mạnh hơn, đổi lại có thể tăng chờ hoặc số transaction phải retry tùy DBMS và tải hệ thống.

---

## 26. Cách chọn isolation theo nhu cầu nghiệp vụ

Không có một mức cô lập “tốt nhất cho mọi câu SQL”. Hãy bắt đầu từ **điều gì cần giữ ổn định**.

| Nhu cầu | Điều cần bảo vệ | Hướng tiếp cận |
| --- | --- | --- |
| Hiển thị danh mục sản phẩm từng trang độc lập | Dữ liệu đọc đã commit | `READ COMMITTED` thường đủ, tùy yêu cầu |
| Đọc số dư không chấp nhận giá trị có thể rollback | Ngăn dirty read | Không dùng `READ UNCOMMITTED`/`NOLOCK` ở hệ cho phép |
| Một báo cáo dùng nhiều SELECT phải cùng góc nhìn | Ngăn non-repeatable/phantom trong các lần đọc | Transaction snapshot phù hợp, ví dụ PostgreSQL `REPEATABLE READ` |
| Đọc tập hàng rồi bảo đảm predicate không bị thay đổi trước khi ghi | Bảo vệ invariant nhiều hàng | `SERIALIZABLE` hoặc locking/ràng buộc được thiết kế đúng |
| Đếm lượt tăng thêm dưới concurrency | Không mất cập nhật, không đếm retry | Update nguyên tử + event dedup/idempotency; isolation phù hợp |
| Tạo một mã duy nhất | Không chèn trùng | `UNIQUE`/`PRIMARY KEY` là ràng buộc chính |
| Chỉ đọc analytics không làm thay đổi bảng | Góc nhìn thống nhất, chi phí hợp lý | Read-only transaction snapshot, hoặc snapshot phân tích theo hệ |

### Isolation không thay thế khóa duy nhất

Nếu nghiệp vụ không cho hai người đăng ký cùng email, hãy đặt `UNIQUE(email)` theo chính sách thích hợp. Việc chỉ chọn SERIALIZABLE mà không thiết kế ràng buộc dữ liệu có thể gây phức tạp và dễ sót các đường ghi khác.

### Isolation không thay thế điều kiện cập nhật đúng

Đoạn:

```sql
UPDATE inventory
SET qty = 0
WHERE sku = 'A';
```

vẫn có thể sai nghiệp vụ dù chạy ở SERIALIZABLE nếu yêu cầu thực tế là **trừ đúng số lượng bán** chứ không phải đặt về 0.

### Isolation không sửa lỗi thứ tự sự kiện

Một sự kiện cập nhật bản cũ đến muộn có thể ghi đè bản mới nếu không có versioning. Đây là vấn đề **quy tắc dữ liệu và thứ tự nghiệp vụ**, ngoài việc chọn isolation level.

---

## 27. Viết lịch thực thi A/B để phân tích hiện tượng

Một cách học hiệu quả là vẽ bảng thời gian. Ví dụ:

```text
A: BEGIN READ COMMITTED
A: SELECT amount WHERE id=101          → 100

B: BEGIN
B: UPDATE id=101 SET amount=130
B: COMMIT

A: SELECT amount WHERE id=101          → 130
A: COMMIT
```

Để nhận diện, hãy ghi lại:

1. A bắt đầu transaction lúc nào?
2. A đọc lần 1: **câu SELECT nào, khóa nào, điều kiện gì, kết quả gì?**
3. B thay đổi hàng nào? `INSERT`, `UPDATE` hay `DELETE`?
4. B đã `COMMIT` hay còn mở transaction khi A đọc lần 2?
5. A đọc lần 2 có **cùng điều kiện và cùng transaction** không?
6. Thay đổi là **giá trị trên hàng cũ** hay **thành viên của tập hàng**?
7. Mức isolation/DBMS có cho phép quan sát đó hay không?

### Mẫu ghi kết quả

| Trường quan sát | Câu trả lời ví dụ |
| --- | --- |
| DBMS | PostgreSQL |
| Mức cô lập của A | READ COMMITTED |
| Câu đọc đầu | `SELECT amount WHERE order_id=101` |
| Giá trị đầu | 100 |
| Tác động của B | UPDATE amount=130 |
| B commit? | Có, trước lần đọc thứ hai |
| Câu đọc thứ hai | Giống câu đầu |
| Giá trị sau | 130 |
| Hiện tượng | Non-repeatable read |

Một bảng ghi như vậy giúp phân biệt **dự đoán theo lý thuyết** và **kết quả được quan sát thật**.

---

## 28. Các ví dụ dự đoán kết quả theo PostgreSQL

Với bảng `tx_orders_lab_303` ban đầu, xem các lịch sau.

### Tình huống A: B sửa nhưng chưa commit

```text
A: BEGIN READ COMMITTED
A: SELECT amount WHERE order_id=101    → 100
B: BEGIN
B: UPDATE order 101 amount=150         (chưa COMMIT)
A: SELECT amount WHERE order_id=101    → ?
B: ROLLBACK
```

Trong PostgreSQL, `SELECT` thông thường của A **không đọc** 150 chưa commit. Nó tiếp tục nhận phiên bản đã commit phù hợp là **100**. Do đó **không dirty read**.

### Tình huống B: B commit giữa hai SELECT

```text
A: BEGIN READ COMMITTED
A: SELECT amount WHERE order_id=101    → 100
B: BEGIN
B: UPDATE order 101 amount=150
B: COMMIT
A: SELECT amount WHERE order_id=101    → ?
```

A có thể thấy **150** ở lần sau: non-repeatable read.

### Tình huống C: transaction snapshot

```text
A: BEGIN REPEATABLE READ
A: SELECT amount WHERE order_id=101    → 100
B: BEGIN
B: UPDATE order 101 amount=150
B: COMMIT
A: SELECT amount WHERE order_id=101    → ?
```

Ở PostgreSQL, A vẫn thấy **100** qua consistent read trong snapshot của transaction.

### Tình huống D: hàng được chèn thỏa predicate

```text
A: BEGIN READ COMMITTED
A: SELECT COUNT(*) FROM orders
   WHERE customer_id=1 AND status='PAID' → 2
B: INSERT order 104, customer=1, PAID
B: COMMIT
A: SELECT COUNT(*) ... cùng predicate    → ?
```

A thấy **3**: phantom read.

### Tình huống E: cùng lịch, khác mức cô lập

Đổi A sang PostgreSQL `REPEATABLE READ` và tạo snapshot bằng SELECT trước khi B commit. Lần đếm thứ hai của A vẫn là **2**. Đây là điểm phân biệt thực tế giữa PostgreSQL `READ COMMITTED` và `REPEATABLE READ`.

---

## 29. Những bẫy khi tự xây bài thực hành

### 29.1. Dùng bảng tạm ở hai connection

Nếu tạo `CREATE TEMP TABLE lab (...)` trong session A, session B PostgreSQL **không nhìn thấy bảng đó**. Vì vậy, thực hành hai session phải dùng bảng thường trong database lab hoặc một nguồn dữ liệu thực sự được hai connection cùng truy cập.

### 29.2. Quên commit ở B

Nếu B chỉ UPDATE mà chưa COMMIT, A ở READ COMMITTED PostgreSQL không thể đọc giá mới. Nếu bạn chờ thấy 130 nhưng chỉ thấy 100, cần kiểm tra B đã commit chưa — không nên kết luận PostgreSQL tự chuyển sang REPEATABLE READ.

### 29.3. Bị autocommit phá ranh giới của A

Nếu A không mở transaction, mỗi SELECT có thể thuộc một transaction riêng. Dữ liệu khác nhau giữa hai lệnh không phải minh chứng rằng **cùng một transaction** đọc không lặp lại.

### 29.4. Đặt isolation level sau khi đã đọc

Trong PostgreSQL, `SET TRANSACTION ISOLATION LEVEL ...` phải được thiết lập **trước câu truy vấn hoặc thao tác dữ liệu thích hợp đầu tiên của transaction**. Không thể đọc xong rồi đổi isolation để diễn giải lần đọc trước như một snapshot khác.

### 29.5. Giữ transaction mở quá lâu

Transaction dài có thể giữ snapshot cũ, cản trở việc thu gom phiên bản cũ, giữ khóa hoặc tăng contention tùy DBMS. Trong môi trường sản xuất, không dùng transaction dài chỉ để cố giữ một màn hình báo cáo “đứng yên”.

### 29.6. Cleanup trước khi A kết thúc

Nếu dọn bảng bằng `DELETE` hoặc `TRUNCATE` trong lúc A còn mở transaction, bạn đã thêm một writer khác vào lịch và có thể làm thực hành khó giải thích hoặc bị chờ khóa. Hãy kết thúc cả A/B rồi mới reset dữ liệu.

### 29.7. SELECT từ hai database khác nhau

Nếu A kết nối database thử nghiệm 1, B kết nối database thử nghiệm 2, không có cùng dữ liệu để quan sát can thiệp. Hãy kiểm tra database và schema của hai connection.

### 29.8. Dùng số hàng thay đổi mà không xác nhận điều kiện

Một hàng được chèn nhưng có `status='DRAFT'` sẽ **không tạo phantom** cho câu `WHERE status='PAID'`. Sự thay đổi phải ảnh hưởng **predicate mà A thực sự truy vấn**.

---

## 30. Phát hiện vấn đề trong log ứng dụng và báo cáo

Trong thực tế, ta thường không có log ghi từng bước A/B rõ ràng. Các dấu hiệu ban đầu có thể là:

- Một màn hình báo cáo hiển thị chi tiết A nhưng tổng tiền theo thời điểm B.
- Cùng một transaction đọc lại cấu hình và nhận hai phiên bản khác nhau.
- Một câu kiểm tra “còn bao nhiêu suất?” và câu kiểm tra lặp lại thấy thêm/bớt đơn.
- Chương trình đọc dữ liệu mà transaction nguồn về sau rollback.
- Một báo cáo đọc các tài khoản riêng lẻ ở các thời điểm khác nhau và tổng không khớp.

Nhưng từ triệu chứng tới kết luận vẫn cần bằng chứng.

### Các thông tin nên thu thập

1. ID giao dịch/connection hoặc correlation ID.
2. Thời điểm bắt đầu và kết thúc transaction A.
3. SQL/điều kiện lọc của những lần đọc cần so sánh.
4. Mức isolation của session và cấu hình DBMS.
5. ID các hàng B đã sửa, tạo hoặc xóa.
6. Thời điểm B commit/rollback.
7. Các câu truy vấn có dùng locking read, hints, view hay function tạo tác dụng phụ không.
8. Kết quả ở hai lần đọc: **giá trị cột**, **tập khóa**, **count**.
9. Có retry, transaction tự động hoặc pool connection thay đổi trạng thái không.
10. Có replication lag, cache ứng dụng hoặc dữ liệu từ nhiều nguồn khác nhau không.

**Không phải mọi số liệu thay đổi đều do isolation anomaly.** Một ứng dụng đọc từ replica chậm, cache chưa cập nhật hoặc hai môi trường khác nhau cũng có thể thấy kết quả lệch. Cần loại trừ các nguyên nhân đó trước khi đổi isolation.

---

## 31. Cách xử lý khi yêu cầu ổn định nhiều lần đọc

Tùy mục tiêu, có thể chọn một hoặc nhiều hướng:

### Một câu SQL tổng hợp

Nếu mọi chỉ tiêu có thể được lấy bằng **một statement**, việc dùng một snapshot cho cả câu truy vấn (theo DBMS phù hợp) có thể tránh việc từng câu lấy số liệu tại những thời điểm khác nhau.

### Một transaction snapshot

Với báo cáo nhiều câu cần nhất quán, dùng mức isolation và cơ chế snapshot phù hợp, chẳng hạn PostgreSQL `REPEATABLE READ READ ONLY` khi đúng yêu cầu:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM tx_orders_lab_303 WHERE status='PAID';

SELECT SUM(amount) FROM tx_orders_lab_303 WHERE status='PAID';

COMMIT;
```

Hai SELECT đọc theo một snapshot transaction phù hợp. `READ ONLY` giúp diễn đạt rõ ý định không ghi dữ liệu trong transaction này.

### Ràng buộc dữ liệu và câu ghi nguyên tử

Nếu vấn đề là hai giao dịch cùng ghi một đối tượng duy nhất, `UNIQUE`, `CHECK`, update có điều kiện và các cơ chế ghi nguyên tử có thể quan trọng hơn việc chỉ tăng isolation.

### SERIALIZABLE cho invariant phức tạp

Nếu nhiều transaction phải đưa ra quyết định phụ thuộc **tập hàng đang thay đổi**, tính tuần tự hóa có thể cần thiết. Nhưng phải chuẩn bị cho retry và kiểm thử concurrency.

### Cơ chế optimistic concurrency

Khi sửa cùng một hàng, có thể thêm cột version:

```sql
-- Minh họa mẫu cập nhật có kiểm tra phiên bản:
UPDATE documents
SET content = 'new content',
    version = version + 1
WHERE document_id = 10
  AND version = 7;
```

Nếu 0 hàng được cập nhật, version có thể đã đổi và ứng dụng phải xử lý xung đột. Đây là **optimistic concurrency control**, giúp tránh ghi đè âm thầm, nhưng không đồng nhất với việc ngăn phantom ở mọi câu SELECT.

---

## 32. Bộ nhớ nhanh: ba hình ảnh so sánh

### Dirty read — đọc trang giấy còn đang tẩy xóa

```text
B viết "900" bằng bút chì, chưa nộp bài.
A nhìn thấy "900".
B xóa đi và giữ "1000".
→ A đã dùng dữ liệu chưa được xác nhận.
```

### Non-repeatable read — đọc lại cùng dòng, thấy phiên bản mới

```text
A đọc dòng #101: amount=100.
B sửa dòng #101 thành 130 rồi xác nhận.
A đọc lại dòng #101: amount=130.
→ Cùng hàng, giá trị không lặp lại.
```

### Phantom read — đọc lại cùng danh sách, thêm một dòng

```text
A hỏi: "Những order nào đang PAID?"
Lần 1: 101, 102.

B thêm order 104 PAID rồi xác nhận.

A hỏi lại cùng câu.
Lần 2: 101, 102, 104.
→ Tập hàng thỏa điều kiện xuất hiện hàng mới.
```

Mẹo nhớ ngắn:

- **Dirty** hỏi: “B đã COMMIT chưa?”
- **Non-repeatable** hỏi: “Cùng **hàng** có đổi giá trị không?”
- **Phantom** hỏi: “Cùng **điều kiện**, tập **hàng** có đổi không?”

---

## 33. Bài tập tự luyện

Các bài dưới đây dùng khái niệm transaction và bảng `tx_orders_lab_303` của PostgreSQL, trừ khi đề ghi rõ SQL Server hoặc MySQL. Hãy suy luận theo **lịch A/B**, không chỉ nhìn kết quả cuối.

### Bài 1. Nhận diện dữ liệu chưa commit

B bắt đầu transaction và đổi `balance` của account 1 từ 1000 thành 600, nhưng chưa COMMIT. A đọc 600. B ROLLBACK.

Hãy cho biết hiện tượng, điểm mấu chốt để nhận diện, và vì sao ứng dụng tài chính không nên dựa vào giá trị A vừa đọc.

### Bài 2. B đã commit trước lần đọc

A đọc `amount` của order 101 là 100 trong transaction. B cập nhật thành 130 rồi COMMIT. A đọc lại cùng order và nhận 130.

Đây là hiện tượng gì? Tại sao không gọi nó là dirty read?

### Bài 3. Thêm một đơn mới vào tập

A ở READ COMMITTED có danh sách đơn PAID của khách 1 là `101,102`. B chèn `104` PAID cho khách 1 rồi COMMIT. A chạy lại cùng điều kiện và nhận `101,102,104`.

Phân loại hiện tượng và chỉ ra bằng chứng.

### Bài 4. Thay đổi tổng nhưng không đổi số hàng

A đọc tổng của hai đơn PAID là 300. B chỉ cập nhật `amount` của order 101 từ 100 thành 140 rồi COMMIT. A đọc lại tổng là 340 nhưng danh sách `order_id` vẫn `101,102`.

Có đủ căn cứ nói phantom không? Giải thích.

### Bài 5. Chưa COMMIT trong PostgreSQL

A dùng PostgreSQL `READ UNCOMMITTED`, B UPDATE `amount` của order 101 thành 130 nhưng chưa COMMIT. A dùng `SELECT` thường đọc lại.

A có thấy 130 chưa commit không? Vì sao?

### Bài 6. Snapshot ở PostgreSQL REPEATABLE READ

A bắt đầu `REPEATABLE READ` và đọc order 101 amount=100. B cập nhật amount=130 rồi COMMIT. A đọc lại bằng SELECT thường.

A nhận 100 hay 130? Một transaction mới của A sau đó có thể thấy gì?

### Bài 7. Phantom ở PostgreSQL REPEATABLE READ

A có snapshot khi số đơn PAID của khách 1 là 2. B INSERT một đơn PAID rồi COMMIT. A đọc lại cùng predicate trong transaction.

A thấy 2 hay 3? So sánh với bảng mô hình cô lập cổ điển.

### Bài 8. UPDATE làm hàng đi vào predicate

Order 103 có trạng thái DRAFT. A tìm tất cả đơn PAID, lần đầu không có 103. B đổi 103 thành PAID rồi COMMIT. A đọc lại và thấy 103.

Đây có thể xem là hiện tượng gì ở cấp tập kết quả, dù B không INSERT?

### Bài 9. Transaction tự sửa dữ liệu

A trong cùng transaction tự UPDATE order 101 từ 100 lên 105 rồi đọc lại thấy 105. Có phải non-repeatable read do transaction khác không?

### Bài 10. READ COMMITTED và autocommit

Hai câu SELECT độc lập do autocommit chạy ở hai transaction khác nhau thấy giá 100 rồi 130 sau khi có một COMMIT của B.

Có đủ điều kiện gọi đây là non-repeatable read **trong một transaction** chưa?

### Bài 11. Vẽ lịch A/B cho dirty read

Hãy sắp xếp: `B BEGIN`, `B UPDATE`, `A SELECT`, `B ROLLBACK` để tạo dirty read. Điều kiện isolation nào cần có ở A trong DBMS hỗ trợ?

### Bài 12. SQL Server READ COMMITTED với RCSI

A chạy hai SELECT trong cùng READ COMMITTED transaction. B commit một UPDATE giữa hai SELECT. Database bật `READ_COMMITTED_SNAPSHOT`.

Liệu A chắc chắn giữ nguyên snapshot đầu tiên cho cả transaction không? Vì sao?

### Bài 13. InnoDB REPEATABLE READ và locking read

Một bạn nói: “MySQL InnoDB REPEATABLE READ có snapshot, nên cả SELECT thường, SELECT FOR UPDATE và UPDATE luôn nhìn cùng phiên bản”.

Nhận định đó có chính xác không? Nêu khác biệt cần xem.

### Bài 14. SELECT FOR UPDATE chống phantom?

Trong PostgreSQL READ COMMITTED, A khóa những đơn PAID hiện có bằng `SELECT ... FOR UPDATE`. B muốn chèn một đơn PAID mới.

Có thể khẳng định chỉ cần khóa các hàng cũ là ngăn được mọi hàng mới phù hợp predicate không?

### Bài 15. Mức isolation theo bảng chuẩn

Điền “có thể” hoặc “không” cho dirty/non-repeatable/phantom ở READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Sau đó nêu ít nhất một khác biệt của PostgreSQL thực tế.

### Bài 16. Báo cáo có hai câu SELECT

Một báo cáo cần lấy `COUNT(*)` và `SUM(amount)` của đơn PAID với điều kiện phải dựa trên **cùng một trạng thái dữ liệu**.

Nêu ít nhất hai cách thiết kế trên PostgreSQL; giải thích vì sao nhiều SELECT ở READ COMMITTED có thể cho dữ liệu lệch thời điểm.

### Bài 17. Serialization failure

Một transaction PostgreSQL `SERIALIZABLE` báo `SQLSTATE 40001` khi hai transaction đồng thời cập nhật theo một quy tắc nhiều hàng.

Ứng dụng nên xử lý ra sao? Có nên retry độc lập chỉ câu UPDATE cuối mà không chạy lại các SELECT đưa ra quyết định không?

### Bài 18. Chẩn đoán từ log

Hệ thống ghi nhận “giá đọc lần 1 là 100, lần 2 là 130”. Hãy liệt kê những thông tin tối thiểu còn thiếu trước khi kết luận non-repeatable read: transaction, isolation, trạng thái commit, hàng được đọc và nguyên nhân khác có thể có.

---

## 34. Gợi ý lời giải

### Bài 1

**Dirty read.** A đã đọc 600 khi B **chưa COMMIT**, và B về sau ROLLBACK nên 600 không trở thành giá trị được xác nhận. Ứng dụng có thể quyết định dựa trên dữ liệu bị hủy.

### Bài 2

**Non-repeatable read.** A đọc lại đúng hàng 101 trong cùng transaction và thấy giá trị khác sau khi B đã COMMIT. Vì B đã commit trước lần đọc thứ hai nên không phải dirty read.

### Bài 3

**Phantom read.** Tập hàng thỏa predicate thay đổi từ `{101,102}` thành `{101,102,104}`; hàng 104 xuất hiện sau một INSERT đã commit.

### Bài 4

Chưa đủ căn cứ gọi phantom. Các khóa của tập kết quả vẫn là `101,102`; tổng đổi do giá trị `amount` của hàng 101 đã được cập nhật và commit. Đây phù hợp với **non-repeatable read** của một thuộc tính trên hàng đã có.

### Bài 5

Trong PostgreSQL, `READ UNCOMMITTED` được thực thi như `READ COMMITTED`; A **không** thấy giá trị 130 chưa commit qua SELECT thường. Nó có thể tiếp tục thấy 100.

### Bài 6

A ở PostgreSQL `REPEATABLE READ` thấy **100** theo snapshot transaction. Sau khi A kết thúc và bắt đầu transaction mới, nó có thể thấy giá trị mới **130** của B.

### Bài 7

A tiếp tục thấy **2** theo snapshot PostgreSQL REPEATABLE READ. Mô hình cổ điển cho phép phantom ở REPEATABLE READ, nhưng PostgreSQL triển khai hành vi mạnh hơn đối với consistent reads thông thường.

### Bài 8

Ở cấp predicate `WHERE status='PAID'`, order 103 trở thành **thành viên mới của tập kết quả**. Có thể mô tả là phantom do thay đổi phạm vi thỏa điều kiện, dù hàng đã tồn tại từ trước và B dùng UPDATE.

### Bài 9

Không phải ví dụ non-repeatable read do **transaction khác**. A tự sửa dữ liệu của chính mình và đọc lại thay đổi đó.

### Bài 10

Chưa. Hai SELECT ở hai transaction độc lập không thỏa điều kiện “đọc lại trong cùng transaction”. Cần kiểm tra autocommit, BEGIN/COMMIT và connection.

### Bài 11

Lịch:

```text
B: BEGIN
B: UPDATE balance = 600       -- chưa commit
A: SELECT balance            -- đọc 600
B: ROLLBACK
```

A cần ở một DBMS và mức cho phép đọc chưa commit, chẳng hạn SQL Server `READ UNCOMMITTED`. PostgreSQL không tái hiện dirty read chỉ bằng cách đặt tên mức này.

### Bài 12

Không. SQL Server RCSI cung cấp snapshot **ở cấp statement** cho READ COMMITTED, không giữ một snapshot cố định cho toàn transaction như mức SNAPSHOT riêng. SELECT thứ hai có thể thấy commit mới của B.

### Bài 13

Không chính xác. Trong InnoDB, **consistent nonlocking reads** dùng snapshot theo quy tắc mức cô lập, còn **locking/current reads** như `FOR UPDATE` và các thao tác ghi có ngữ nghĩa và cơ chế khóa khác. Không nên cho rằng tất cả đọc y hệt một phiên bản.

### Bài 14

Không thể khẳng định. Khóa những hàng cũ không tự khóa mọi khoảng trống/predicate có thể tạo một hàng mới, đặc biệt với PostgreSQL READ COMMITTED. Cần giải pháp ở cấp transaction/predicate phù hợp.

### Bài 15

| Isolation cổ điển | Dirty | Non-repeatable | Phantom |
| --- | --- | --- | --- |
| READ UNCOMMITTED | Có thể | Có thể | Có thể |
| READ COMMITTED | Không | Có thể | Có thể |
| REPEATABLE READ | Không | Không | Có thể |
| SERIALIZABLE | Không | Không | Không |

PostgreSQL không hỗ trợ dirty read dù khai báo READ UNCOMMITTED và PostgreSQL REPEATABLE READ cũng ngăn phantom đối với SELECT thường.

### Bài 16

Hai hướng:

1. Gộp các chỉ số thành **một SELECT** với nhiều hàm tổng hợp, để chúng cùng thuộc snapshot của một câu.
2. Mở một transaction **REPEATABLE READ READ ONLY** trên PostgreSQL và chạy những SELECT cần thiết trong cùng transaction.

READ COMMITTED dùng snapshot riêng cho từng statement nên có thể thấy các commit khác nhau giữa hai SELECT.

### Bài 17

Khi `SQLSTATE 40001`, cần **ROLLBACK** transaction thất bại và **retry toàn transaction**, trong đó có bước đọc, kiểm tra và quyết định ghi. Retry độc lập câu UPDATE cuối có thể dùng những quyết định dựa trên snapshot cũ. Cần giới hạn retry và bảo vệ tác dụng phụ ngoài database khỏi lặp.

### Bài 18

Cần kiểm tra:

- Hai SELECT có nằm trong **cùng transaction** và cùng connection không?
- Isolation thực tế là gì?
- Cùng `WHERE`, cùng `order_id`, cùng nguồn dữ liệu không?
- Transaction B có `UPDATE` hàng đó và đã **COMMIT** trước lần đọc thứ hai chưa?
- Hai lần đọc có đi qua cache, replica hoặc hai môi trường khác nhau không?
- A có tự thay đổi dữ liệu ở giữa không?

Chỉ từ hai con số 100 và 130 không đủ để gán chắc nhãn non-repeatable read.

---

## 35. Dọn môi trường thực hành

Chỉ thực hiện khi đã đóng hết transaction A/B và không còn session dùng bảng thử nghiệm.

### PostgreSQL

Nếu bảng được tạo riêng cho bài và không cần giữ lại:

```sql
DROP TABLE tx_orders_lab_303;
```

### SQL Server

Nếu bảng `dbo.tx_dirty_lab_303` là đối tượng thử nghiệm do bạn tạo:

```sql
DROP TABLE dbo.tx_dirty_lab_303;
```

**Không chạy DROP trên bảng có tên giống ví dụ nhưng thuộc hệ thống khác hoặc không do bài thực hành tạo.** Trong môi trường dùng chung, nên được cấp schema/database lab riêng.

---

## 36. Tổng kết: nhận diện bằng trạng thái commit và loại thay đổi

Khi có một lịch SQL gồm nhiều transaction, đừng vội hỏi “isolation level này cho phép anomaly nào?” trước khi xác định **A thực sự nhìn thấy gì**.

Hãy phân tích theo thứ tự:

1. **Hai lần đọc có thuộc cùng transaction A không?** Nếu không, chưa phải một ví dụ đọc không lặp lại/hàng ảo trong cùng transaction.
2. **B đã commit tại thời điểm A đọc giá trị thay đổi chưa?** Nếu chưa mà A vẫn thấy thay đổi, đó là dirty read.
3. **Khóa của hàng A đọc có giữ nguyên không?** Nếu cùng hàng có giá trị khác sau khi B commit, đây là non-repeatable read điển hình.
4. **Tập khóa thỏa cùng predicate có thay đổi không?** Nếu có thêm/bớt hàng sau commit, đó là phantom read điển hình.
5. **DBMS có triển khai đúng bảng cổ điển không?** PostgreSQL READ UNCOMMITTED hoạt động như READ COMMITTED và REPEATABLE READ giữ snapshot tránh phantom của SELECT thường; SQL Server và MySQL/InnoDB có các cơ chế locking/versioning khác.
6. **Nghiệp vụ cần bảo vệ điều gì?** Một lần đọc chính xác, nhiều SELECT cùng snapshot, hay một invariant nhiều hàng cần serializable/ràng buộc và retry?

**Nhớ ba dấu hiệu cốt lõi: đọc bẩn = dữ liệu *chưa commit*; đọc không lặp lại = *cùng hàng* đổi giá trị sau commit; hàng ảo = *tập hàng thỏa điều kiện* đổi sau commit.** Hiểu đúng ba quan sát này, cùng với snapshot và cơ chế khóa của DBMS đang dùng, sẽ giúp bạn đọc các lịch giao dịch, chẩn đoán báo cáo bất nhất và chọn mức cô lập phù hợp thay vì chỉ học thuộc một bảng lý thuyết.
