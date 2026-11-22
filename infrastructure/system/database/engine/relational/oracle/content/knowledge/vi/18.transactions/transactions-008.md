# Undo, MVCC và tính nhất quán khi đọc trong Oracle Database

Oracle Database cho phép nhiều session cùng đọc và thay đổi dữ liệu. Một session có thể đang cập nhật một hàng trong khi session khác chạy truy vấn trên chính bảng đó. Để người đọc không nhìn thấy dữ liệu chưa commit hoặc một kết quả bị ghép từ nhiều trạng thái khác nhau, Oracle sử dụng **undo**, cơ chế **MVCC (Multi-Version Concurrency Control)** và **read consistency**.

Ba khái niệm này liên hệ chặt chẽ nhưng không đồng nghĩa:

- **Undo** lưu thông tin cần thiết để hoàn tác thay đổi và dựng lại phiên bản dữ liệu cũ.
- **MVCC** là cách Oracle cung cấp nhiều phiên bản logic của dữ liệu cho các reader và writer đồng thời.
- **Read consistency** bảo đảm một truy vấn nhìn thấy dữ liệu theo một thời điểm nhất quán, thay vì nhìn thấy những thay đổi đang diễn ra giữa lúc truy vấn chạy.

Trong Oracle, một truy vấn thông thường không phải chờ mọi transaction khác kết thúc mới đọc được dữ liệu. Khi một hàng đang bị session khác sửa nhưng chưa commit, reader có thể dùng undo để dựng lại phiên bản đã commit trước đó. Nhờ vậy, reader và writer thường không chặn nhau theo kiểu đọc phải đợi ghi hoặc ghi phải đợi đọc.

Bài học giải thích undo record và undo segment, SCN, consistent read, snapshot theo statement và transaction, tương tác giữa hai session, khác biệt undo/redo, quản lý thời gian lưu undo và lỗi ORA-01555.

## 1. Vì sao cần tính nhất quán khi đọc?

### 1.1. Vấn đề khi nhiều session cùng truy cập

Giả sử bảng tài khoản có số dư:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5.000 |
| 202 | 8.000 |

Session A chuyển 1.000 từ tài khoản 101 sang tài khoản 202. Trong transaction, A thực hiện hai thao tác:

1. Trừ 1.000 ở tài khoản 101.
2. Cộng 1.000 ở tài khoản 202.
3. COMMIT.

Trong lúc A mới hoàn thành bước 1, session B chạy truy vấn tổng số dư. Nếu B đọc được trạng thái chưa hoàn tất, nó có thể thấy tổng là 12.000 thay vì 13.000. Đây là trạng thái trung gian chưa commit, không nên được coi là dữ liệu đã xác nhận.

Oracle dùng read consistency để B nhìn thấy một trạng thái đã commit phù hợp với thời điểm truy vấn bắt đầu. B không đọc nửa transaction của A.

### 1.2. Các mục tiêu chính

Read consistency trong Oracle giúp bảo đảm:

- **Không đọc dữ liệu chưa commit của transaction khác** (dirty read).
- Một câu SELECT thông thường nhìn thấy dữ liệu theo cùng một snapshot logic trong suốt câu lệnh.
- Reader có thể đọc phiên bản đã commit trước đó trong khi writer đang cập nhật hàng.
- Một câu truy vấn nhiều bảng không ghép tùy tiện các phiên bản được commit ở những thời điểm khác nhau trong cùng một statement snapshot.

Điều này không có nghĩa mọi truy vấn trong một transaction READ COMMITTED đều nhìn thấy cùng một snapshot. Oracle mặc định cấp snapshot mới cho từng statement; phần này sẽ được giải thích ở mục 7.

### 1.3. Dirty read, non-repeatable read và phantom

| Hiện tượng | Ý nghĩa |
| --- | --- |
| Dirty read | Đọc thay đổi chưa commit của transaction khác |
| Non-repeatable read | Đọc cùng một hàng ở hai statement nhưng nhận giá trị khác vì transaction khác đã commit thay đổi |
| Phantom | Chạy lại điều kiện truy vấn và thấy thêm hoặc mất các hàng phù hợp vì transaction khác đã commit insert/delete/update |
| Read skew | Kết quả đọc các phần dữ liệu liên quan từ những thời điểm không nhất quán |

Oracle không cho phép dirty read trong các mức cô lập transaction thông thường. Với mặc định READ COMMITTED, các statement khác nhau có thể nhìn thấy snapshot khác nhau, do đó non-repeatable read và phantom có thể xảy ra giữa hai statement. SERIALIZABLE và READ ONLY cung cấp snapshot nhất quán ở cấp transaction theo quy tắc của Oracle.

## 2. Undo là gì?

### 2.1. Undo lưu thông tin để quay lại trạng thái trước

Khi một transaction thay đổi dữ liệu, Oracle tạo undo information mô tả cách khôi phục phiên bản trước của dữ liệu. Tùy thao tác:

- **UPDATE:** undo chứa giá trị cũ cần thiết để hoàn tác cập nhật.
- **DELETE:** undo chứa thông tin cần thiết để khôi phục hàng đã xóa.
- **INSERT:** undo cho phép hủy tác động của hàng mới được thêm vào khi rollback.

Ví dụ:

```sql
UPDATE employees
SET salary = 25000
WHERE employee_id = 100;
```

Nếu giá trị cũ là 22000, undo giữ thông tin đủ để Oracle khôi phục salary về 22000 khi transaction rollback hoặc để dựng phiên bản đã commit trước đó cho consistent read.

Undo không đơn giản là một bản sao đầy đủ của cả bảng. Nó là các thông tin thay đổi được Oracle quản lý trong các undo segment.

### 2.2. Undo segment và undo tablespace

Undo record được lưu trong **undo segment**, các segment này nằm trong **undo tablespace** được database quản lý. Khi một transaction thực hiện DML, Oracle dùng undo segment để ghi thông tin cần thiết.

Một cách hình dung:

```text
Transaction
    |
    | UPDATE / INSERT / DELETE
    v
Undo segment
    |
    | undo records (before-image / rollback information)
    v
Undo tablespace

Data blocks  <---- thay đổi ---->  Database buffer cache
    ^
    |
    +---- undo được dùng để dựng lại phiên bản cũ
```

Trong cấu hình Automatic Undo Management, Oracle tự quản lý việc cấp phát và tái sử dụng undo space theo cấu hình undo tablespace và các chính sách retention.

### 2.3. Undo được dùng cho những việc nào?

Undo có nhiều vai trò:

1. **ROLLBACK:** hoàn tác các thay đổi của transaction chưa commit.
2. **Read consistency:** dựng lại phiên bản dữ liệu phù hợp với snapshot của câu SELECT.
3. **Flashback Query và một số tính năng Flashback:** truy xuất phiên bản dữ liệu trong khoảng undo còn khả dụng và theo giới hạn tính năng.
4. **Transaction recovery:** hỗ trợ khôi phục transaction chưa hoàn tất theo cơ chế Oracle.

Một transaction đã COMMIT không có nghĩa undo của nó bị xóa ngay lập tức. Undo cũ có thể vẫn cần cho các truy vấn đang chạy hoặc cho mục đích flashback trong thời gian retention.

### 2.4. Undo không phải redo

Undo và redo đều quan trọng nhưng phục vụ mục đích khác nhau:

| Đặc điểm | Undo | Redo |
| --- | --- | --- |
| Mục tiêu chính | Hoàn tác thay đổi, dựng phiên bản dữ liệu cũ | Phát lại thay đổi để phục hồi |
| Thông tin | Dữ liệu/metadata cần để rollback và consistent read | Mô tả thay đổi cần áp dụng lại |
| Nơi quản lý | Undo segments trong undo tablespace | Redo log buffer và online/archived redo logs |
| Dùng khi ROLLBACK | Có | Không phải cơ chế rollback |
| Dùng khi media recovery | Không thay thế redo | Là thành phần thiết yếu để roll forward |

Khi DML thay đổi block dữ liệu, Oracle cũng tạo redo để bảo vệ khả năng phục hồi. Các thay đổi đối với undo block cũng được ghi redo. Không nên hiểu rằng undo và redo là hai bản sao đối xứng hoặc một trong hai có thể thay thế bên còn lại.

## 3. MVCC trong Oracle hoạt động như thế nào?

### 3.1. Nhiều phiên bản logic của một hàng

MVCC là viết tắt của *Multi-Version Concurrency Control*. Thay vì bắt reader luôn chờ writer nhả khóa, Oracle có thể dùng undo để tái tạo phiên bản hàng phù hợp với thời điểm truy vấn cần đọc.

Ví dụ, hàng tài khoản ban đầu có balance 5.000. Session A cập nhật thành 4.000 nhưng chưa commit:

```text
Phiên bản đã commit trước đó: BALANCE = 5.000
Phiên bản đang được A cập nhật: BALANCE = 4.000 (chưa commit)

Reader B cần snapshot trước khi A commit:
    -> dùng undo để dựng lại BALANCE = 5.000
```

Oracle không nhất thiết giữ một bản copy hoàn chỉnh cho mỗi phiên bản trong một vùng version store riêng như một số hệ quản trị khác. Phiên bản nhất quán được dựng lại từ block dữ liệu hiện tại và undo records khi cần.

### 3.2. Consistent read

Một lần đọc nhất quán (*consistent read*) trả về dữ liệu như đã tồn tại tại một SCN snapshot. Nếu block hiện tại đã bị transaction khác sửa sau snapshot, Oracle có thể áp dụng chuỗi undo cần thiết để dựng block về trạng thái phù hợp với SCN đó.

Kết quả là câu SELECT thấy một trạng thái đã commit nhất quán, dù dữ liệu vật lý hiện tại có thể đang chứa thay đổi chưa commit hoặc thay đổi commit sau snapshot.

### 3.3. Reader và writer ít chặn nhau

Trong trường hợp SELECT thông thường:

- Reader không cần đợi writer commit để đọc phiên bản trước đó.
- Writer không cần đợi các SELECT thông thường kết thúc chỉ vì chúng đang đọc hàng.
- Writer vẫn cần khóa để bảo vệ thay đổi và xử lý xung đột với writer khác.
- Các lệnh như `SELECT ... FOR UPDATE` có ngữ nghĩa khóa khác với SELECT thông thường.

Điều này là một trong các lợi ích quan trọng của MVCC: tăng khả năng đồng thời mà vẫn giữ tính nhất quán khi đọc.

### 3.4. MVCC không có nghĩa mọi thao tác đều không chờ

Một câu `UPDATE` có thể phải chờ nếu hàng đang bị transaction khác khóa. `SELECT ... FOR UPDATE` có thể chờ khóa hàng. DDL, khóa bảng, tài nguyên dùng chung hoặc tranh chấp khác cũng có thể tạo wait.

Vì vậy, phát biểu chính xác là **SELECT thông thường thường đọc phiên bản nhất quán mà không phải chờ row lock của DML**, chứ không phải Oracle không bao giờ có blocking.

## 4. SCN và snapshot

### 4.1. SCN là gì?

SCN (*System Change Number*) là một số thứ tự logic Oracle dùng để đánh dấu thứ tự các sự kiện thay đổi trong database. SCN không đơn giản là đồng hồ thời gian theo giây. Oracle dùng SCN trong recovery, read consistency và nhiều tính năng khác.

Khi một query cần snapshot, Oracle xác định một SCN phù hợp với thời điểm bắt đầu của statement hoặc transaction tùy isolation level.

### 4.2. Query snapshot

Có thể hình dung:

```text
Thời gian ---------------------------------------------------->

SCN 100       SCN 110       SCN 120       SCN 130
   |             |             |             |
   |             |             |             +-- Transaction B COMMIT
   |             |             +---------------- Transaction A COMMIT
   |             +------------------------------ Query Q bắt đầu
   +-------------------------------------------- Trạng thái cũ

Query Q đọc snapshot tại SCN 110:
- Thấy thay đổi đã commit trước snapshot.
- Không thấy thay đổi được commit sau SCN 110.
```

Oracle sử dụng undo để dựng lại các phiên bản cần thiết khi block hiện tại đã thay đổi sau SCN snapshot.

### 4.3. Một statement nhìn thấy một snapshot

Với READ COMMITTED, một câu SELECT dài bắt đầu tại một snapshot logic. Nếu transaction khác commit trong khi SELECT đang chạy, câu SELECT hiện tại vẫn đọc theo snapshot của chính nó; statement tiếp theo có thể thấy thay đổi vừa commit.

Điều này quan trọng với truy vấn join hoặc aggregate nhiều hàng. Oracle không để phần đầu của cùng một statement đọc trạng thái cũ rồi phần sau đọc trạng thái mới chỉ vì transaction khác commit giữa chừng.

## 5. Thực hành hai session: reader và writer

Ví dụ này dùng bảng demo nhỏ để quan sát hành vi. Mở hai cửa sổ SQL hoặc hai session độc lập trong SQL Developer/SQLcl.

### 5.1. Tạo bảng và dữ liệu

Chạy một lần trong schema học tập:

```sql
CREATE TABLE demo_mvcc_accounts (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO demo_mvcc_accounts VALUES (101, 5000);
INSERT INTO demo_mvcc_accounts VALUES (202, 8000);
COMMIT;
```

Giá trị ban đầu của tài khoản 101 là 5000.

### 5.2. Session A: cập nhật nhưng chưa commit

Trong session A:

```sql
UPDATE demo_mvcc_accounts
SET balance = 4000
WHERE account_id = 101;

-- Chưa COMMIT.
```

Session A đã tạo undo cho giá trị cũ 5000 và đang giữ thay đổi mới trong transaction chưa commit.

### 5.3. Session B: SELECT thông thường

Trong session B:

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Kết quả:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5000 |

Session B không đọc giá trị chưa commit 4000 của A. Oracle dùng undo để trả về phiên bản đã commit trước đó.

### 5.4. Session B: thử cập nhật cùng hàng

Trong khi A vẫn chưa commit, thử ở B:

```sql
UPDATE demo_mvcc_accounts
SET balance = 4500
WHERE account_id = 101;
```

Lệnh này có thể phải chờ vì A đang giữ row lock. Đây là thao tác ghi cạnh tranh với một transaction ghi khác, khác với SELECT thông thường.

Không cần để lệnh chờ vô thời hạn trong bài thực hành. Có thể hủy statement ở client hoặc rollback session B nếu nó đã mở transaction và đang chờ.

### 5.5. Session A: COMMIT

Quay lại session A:

```sql
COMMIT;
```

Thay đổi 4000 được commit và khóa của transaction A được giải phóng.

### 5.6. Session B: chạy SELECT mới

Chạy lại trong session B:

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Kết quả mới:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 4000 |

Session B bắt đầu một statement mới dưới READ COMMITTED, nên snapshot mới thấy commit của A.

### 5.7. Điều rút ra

- SELECT thông thường không thấy dữ liệu chưa commit của A.
- SELECT có thể đọc phiên bản cũ bằng undo khi A đang sửa hàng.
- UPDATE của B trên cùng hàng có thể chờ khóa do A nắm giữ.
- Sau khi A commit, statement mới của B thấy giá trị mới.
- Reader/writer và writer/writer có hành vi đồng thời khác nhau.

## 6. Statement-level read consistency

### 6.1. READ COMMITTED là mức mặc định

Oracle mặc định dùng isolation level **READ COMMITTED**. Mỗi câu SQL có snapshot nhất quán riêng tại thời điểm statement bắt đầu.

Ví dụ session A:

```sql
SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Session B cập nhật balance và COMMIT. Khi A chạy lại câu SELECT, A có thể thấy giá trị mới vì đó là statement mới với snapshot mới.

Một transaction có thể gồm nhiều câu SELECT và mỗi câu có thể thấy dữ liệu commit mới từ session khác.

### 6.2. Hai SELECT trong cùng transaction có thể khác kết quả

Session A:

```sql
SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;

-- Chờ Session B cập nhật và COMMIT.

SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

Nếu B đã commit thay đổi giữa hai câu lệnh, A có thể thấy giá trị khác ở lần SELECT thứ hai. Đây là non-repeatable read ở cấp transaction dưới READ COMMITTED, và là hành vi được thiết kế của isolation level này.

### 6.3. Một câu SELECT dài không đổi snapshot giữa chừng

Giả sử session A mở một cursor SELECT có nhiều hàng và đang fetch kết quả. Session B cập nhật rồi commit một số hàng trong bảng trong lúc A vẫn đang đọc.

Cursor đang chạy của A tiếp tục trả kết quả theo snapshot khi statement được mở. Sau khi A hoàn tất và chạy một SELECT mới, statement mới có thể thấy các thay đổi B đã commit.

Đây là điểm khác biệt giữa:
- Nhiều lần SELECT riêng biệt: mỗi statement có thể có snapshot khác.
- Một statement đang chạy: dữ liệu được đọc nhất quán theo snapshot của statement đó.

### 6.4. Truy vấn join cũng có snapshot của statement

Ví dụ:

```sql
SELECT o.order_id,
       o.customer_id,
       c.customer_name,
       o.total_amount
FROM   orders o
JOIN   customers c
       ON c.customer_id = o.customer_id
WHERE  o.order_date >= DATE '2026-01-01';
```

Oracle bảo đảm các bảng được đọc trong statement theo cùng read-consistent snapshot. Một truy vấn join không nên thấy hàng orders ở thời điểm mới nhưng hàng customers ở thời điểm cũ chỉ vì transaction khác commit giữa lúc scan hai bảng.

## 7. Transaction-level read consistency

### 7.1. SERIALIZABLE

Khi cần nhiều statement trong cùng transaction nhìn thấy một snapshot ổn định, có thể dùng isolation level SERIALIZABLE:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;

-- Các statement tiếp theo trong transaction dùng snapshot transaction.
```

`SET TRANSACTION` phải được đặt ở đầu transaction, trước các câu lệnh khác thuộc transaction đó.

Trong SERIALIZABLE, transaction nhìn thấy dữ liệu đã commit trước khi transaction bắt đầu (cùng với thay đổi của chính transaction), theo snapshot transaction. Nếu transaction khác thay đổi dữ liệu mà transaction SERIALIZABLE cần cập nhật theo cách gây xung đột serialization, Oracle có thể trả lỗi `ORA-08177: can't serialize access for this transaction`.

SERIALIZABLE không có nghĩa Oracle khóa toàn bộ bảng cho transaction. Nó cung cấp ngữ nghĩa snapshot và phát hiện xung đột cần thiết; ứng dụng phải có chiến lược retry phù hợp khi nhận lỗi serialization.

### 7.2. READ ONLY transaction

Nếu transaction chỉ cần đọc một snapshot ổn định, có thể dùng:

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT SUM(total_amount) FROM orders;
SELECT AVG(total_amount) FROM orders;

COMMIT;
```

`SET TRANSACTION READ ONLY` cũng cần đặt ở đầu transaction. Các truy vấn đọc trong transaction dùng transaction-level snapshot; transaction không được thực hiện DML thông thường trong chế độ này.

### 7.3. So sánh isolation level

| Đặc điểm | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Snapshot | Mỗi statement | Cấp transaction | Cấp transaction |
| Thấy commit mới giữa hai SELECT trong cùng transaction | Có thể | Không, theo snapshot transaction | Không, theo snapshot transaction |
| DML của chính transaction | Có | Có | Không |
| Xung đột serialization | Không theo mô hình snapshot serializable này | Có thể gặp ORA-08177 | Không có DML của transaction |
| Mục đích thường gặp | Giao dịch ứng dụng thông thường | Nhiều statement cần snapshot nhất quán | Báo cáo đọc nhất quán |

Chọn isolation level theo yêu cầu nghiệp vụ. READ COMMITTED thường phù hợp cho phần lớn giao dịch OLTP; SERIALIZABLE hoặc READ ONLY dùng khi cần snapshot ổn định qua nhiều statement và chấp nhận chi phí/giới hạn tương ứng.

### 7.4. Thay đổi của chính transaction vẫn nhìn thấy

Dù dùng read consistency, một transaction vẫn nhìn thấy các thay đổi mà chính nó đã thực hiện. Snapshot không có nghĩa session bị đóng băng khỏi mọi thao tác của bản thân. Oracle kết hợp phiên bản đã commit tại snapshot với các thay đổi riêng của transaction hiện tại theo ngữ nghĩa SQL.

## 8. SELECT thông thường và SELECT FOR UPDATE

### 8.1. SELECT thông thường

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101;
```

SELECT thông thường đọc phiên bản nhất quán và không khóa hàng chỉ để đọc. Nó có thể đọc phiên bản cũ qua undo trong khi transaction khác đang sửa hàng.

### 8.2. SELECT FOR UPDATE

```sql
SELECT account_id, balance
FROM   demo_mvcc_accounts
WHERE  account_id = 101
FOR UPDATE;
```

`FOR UPDATE` yêu cầu khóa các hàng được chọn để session hiện tại có thể cập nhật an toàn. Nó có thể phải chờ transaction khác đang giữ khóa trên các hàng đó. Sau khi lấy khóa, transaction có thể cập nhật các hàng đã chọn.

Một số biến thể điều khiển việc chờ:
- `NOWAIT`: không chờ nếu hàng đang bị khóa; trả lỗi.
- `WAIT n`: chờ tối đa n giây theo cú pháp Oracle.
- `SKIP LOCKED`: bỏ qua các hàng đang bị khóa, thường dùng cho queue/work-distribution có kiểm soát.

Các tùy chọn này thay đổi hành vi lấy khóa; chúng không thay thế cơ chế consistent read của SELECT thông thường.

### 8.3. Khi nào cần FOR UPDATE?

Dùng khi logic ứng dụng cần:
1. Đọc một hàng để quyết định cập nhật.
2. Giữ khóa hàng đó trong transaction.
3. Thực hiện cập nhật dựa trên giá trị đã đọc.
4. COMMIT hoặc ROLLBACK để giải phóng khóa.

Không dùng `FOR UPDATE` cho mọi SELECT. Việc khóa không cần thiết có thể làm tăng blocking và giảm concurrency.

## 9. Undo retention và vòng đời undo

### 9.1. Undo không bị xóa ngay sau COMMIT

Sau COMMIT, undo record không còn cần để rollback transaction đó, nhưng vẫn có thể cần cho:
- Query đang chạy với snapshot cũ.
- Transaction READ COMMITTED/Serializable cần consistent read.
- Flashback Query trong khoảng dữ liệu undo còn khả dụng.

Oracle có thể tái sử dụng undo space khi cần theo chính sách retention và áp lực dung lượng.

### 9.2. UNDO_RETENTION

Tham số `UNDO_RETENTION` đặt mục tiêu thời gian giữ undo (tính bằng giây) trong Automatic Undo Management. Giá trị này là mục tiêu, không phải lời hứa tuyệt đối trong mọi cấu hình.

Khi undo tablespace chịu áp lực, Oracle có thể tái sử dụng undo hết hạn hoặc trong một số trường hợp cần thiết tái sử dụng undo chưa hết hạn nếu không có cơ chế retention guarantee và không đủ dung lượng.

Có thể kiểm tra cấu hình bằng:

```sql
SHOW PARAMETER undo;
```

Hoặc truy vấn tham số:

```sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN ('undo_management', 'undo_tablespace', 'undo_retention');
```

Cần quyền phù hợp để đọc dynamic performance views.

### 9.3. RETENTION GUARANTEE

Undo tablespace có thể được cấu hình retention guarantee để Oracle không ghi đè undo chưa hết thời gian retention chỉ vì thiếu chỗ. Điều này hữu ích khi yêu cầu flashback/long query cần retention nghiêm ngặt.

Tuy nhiên, nếu tablespace hết dung lượng và không thể cấp thêm extent, DML có thể thất bại do không còn undo space. Vì vậy, RETENTION GUARANTEE cần đi kèm sizing, monitoring và kế hoạch mở rộng dung lượng; không bật tùy tiện.

### 9.4. Automatic Undo Management

Trong cấu hình phổ biến, Oracle quản lý undo tự động. DBA cần theo dõi:
- Dung lượng undo tablespace và autoextend.
- Tốc độ phát sinh undo của workload.
- Thời lượng các truy vấn dài.
- Thời gian retention thực tế đạt được.
- Các lỗi snapshot too old và lỗi không cấp phát được undo.

Không nên tăng UNDO_RETENTION một cách đơn lẻ mà không kiểm tra dung lượng và mức tạo undo.

## 10. ORA-01555: snapshot too old

### 10.1. Nguyên nhân

Lỗi phổ biến:

```text
ORA-01555: snapshot too old
```

Lỗi này xảy ra khi Oracle cần undo để dựng lại phiên bản dữ liệu tại snapshot của query nhưng undo cần thiết đã bị ghi đè hoặc không còn khả dụng.

Ví dụ:
1. Query A bắt đầu và cần đọc snapshot cũ.
2. Query A chạy lâu.
3. Các session khác liên tục UPDATE/DELETE và tạo nhiều undo.
4. Undo cũ cần cho query A bị tái sử dụng trước khi query A đọc tới block tương ứng.
5. Query A không thể dựng lại phiên bản cần thiết và báo ORA-01555.

### 10.2. Các nguyên nhân thường gặp

- Truy vấn đọc kéo dài.
- DML tạo undo với tốc độ cao.
- Undo tablespace nhỏ so với workload.
- UNDO_RETENTION không đủ so với thời gian query.
- Undo bị tái sử dụng trước khi query cần đọc.
- Một số pattern xử lý cursor và commit trong vòng lặp có thể làm tăng nguy cơ lỗi trong workload nhất định.

Không nên kết luận ORA-01555 chỉ do “query chạy lâu” hoặc chỉ do “UNDO_RETENTION thấp”. Cần đối chiếu thời lượng truy vấn, tốc độ tạo undo, dung lượng, retention thực tế và thời điểm lỗi.

### 10.3. Hướng xử lý

1. Xác định SQL và thời điểm xảy ra lỗi.
2. Đo thời gian truy vấn, khối lượng dữ liệu và tần suất DML đồng thời.
3. Kiểm tra cấu hình undo tablespace, UNDO_RETENTION và khả năng autoextend.
4. Xem lịch sử undo qua các view giám sát nếu có quyền.
5. Giảm thời gian truy vấn hoặc chia công việc thành các phần có snapshot/logic phù hợp.
6. Tăng dung lượng hoặc retention khi có đủ tài nguyên và yêu cầu vận hành.
7. Đánh giá lại transaction pattern, đặc biệt commit trong vòng lặp xử lý cursor.

Không phải mọi truy vấn dài đều gây ORA-01555. Nếu undo đủ và retention phù hợp, query dài vẫn có thể hoàn tất bình thường.

### 10.4. Không chữa bằng COMMIT tùy tiện

COMMIT thường xuyên trong một vòng lặp fetch cursor không phải giải pháp chung cho undo. Với một số cách xử lý, việc commit liên tục có thể khiến undo cần cho cursor dài bị tái sử dụng và làm tăng nguy cơ ORA-01555. Hãy thiết kế transaction theo đơn vị nghiệp vụ, không commit chỉ để “giải phóng undo” khi chưa hiểu tác động.

### 10.5. Theo dõi undo

DBA có thể xem thống kê undo:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Các cột giúp quan sát số block undo phát sinh, số transaction, độ dài query tối đa, retention được điều chỉnh và số lỗi snapshot too old/không gian. Tên cột và khả năng truy cập phụ thuộc phiên bản/quyền; cần đối chiếu tài liệu release đang vận hành.

## 11. Undo và Flashback Query

### 11.1. Đọc dữ liệu ở một SCN trước đó

Oracle có thể dùng undo cho Flashback Query để truy vấn dữ liệu như tại một thời điểm trong quá khứ, trong giới hạn dữ liệu undo còn giữ và các yêu cầu tính năng.

Ví dụ cú pháp:

```sql
SELECT account_id,
       balance
FROM   demo_mvcc_accounts
AS OF SCN :snapshot_scn
WHERE  account_id = 101;
```

`AS OF SCN` yêu cầu Oracle dựng phiên bản hàng tại SCN được chỉ định. Nếu undo cần thiết không còn, truy vấn flashback có thể thất bại.

### 11.2. Flashback theo timestamp

```sql
SELECT account_id,
       balance
FROM   demo_mvcc_accounts
AS OF TIMESTAMP
       (SYSTIMESTAMP - INTERVAL '5' MINUTE)
WHERE  account_id = 101;
```

Đây là ví dụ đọc phiên bản khoảng năm phút trước. Thời gian thực tế có thể chịu giới hạn undo retention, độ chính xác ánh xạ timestamp sang SCN và các điều kiện cấu hình.

### 11.3. Flashback không thay thế backup

Flashback Query là cách đọc phiên bản lịch sử dựa trên dữ liệu undo còn có thể sử dụng. Nó không thay thế backup, archived redo, Data Guard hoặc chiến lược disaster recovery. Nếu cần khôi phục sau thời gian dài hoặc mất dữ liệu vật lý, phải dùng giải pháp recovery phù hợp.

## 12. Tình huống thực tế và cách chọn isolation

### 12.1. Ứng dụng OLTP

Một ứng dụng bán hàng thường dùng READ COMMITTED:
- Mỗi statement nhìn thấy dữ liệu đã commit tại thời điểm statement bắt đầu.
- Reader không đọc dữ liệu chưa commit.
- Transaction ngắn giảm thời gian giữ khóa.
- DML cạnh tranh cùng hàng có thể chờ hoặc gặp lỗi tùy tình huống.

Đây là mức mặc định của Oracle và thường phù hợp với phần lớn ứng dụng giao dịch.

### 12.2. Báo cáo gồm nhiều câu SELECT cần cùng snapshot

Nếu báo cáo chạy nhiều SELECT và cần các câu đó nhìn thấy cùng một trạng thái dữ liệu, READ COMMITTED có thể không đủ vì mỗi statement có snapshot riêng.

Có thể cân nhắc:
- Một transaction READ ONLY.
- Một transaction SERIALIZABLE nếu cần cả logic transaction tương ứng.
- Flashback Query với cùng SCN cho các câu truy vấn nếu kiến trúc phù hợp.

Chọn cách triển khai dựa trên thời lượng báo cáo, retention undo, workload DML và yêu cầu nghiệp vụ.

### 12.3. Kiểm tra số dư và cập nhật

Nếu ứng dụng đọc số dư rồi quyết định trừ tiền, SELECT thông thường không giữ khóa hàng. Một transaction khác có thể thay đổi số dư trước khi cập nhật. Cần dùng thiết kế transaction phù hợp, ví dụ:
- Dùng UPDATE có điều kiện nguyên tử như `WHERE balance >= :amount`.
- Hoặc đọc hàng bằng SELECT FOR UPDATE rồi cập nhật trong cùng transaction.
- Kiểm tra số hàng bị ảnh hưởng và xử lý lỗi cạnh tranh.

MVCC bảo đảm đọc nhất quán, nhưng không tự biến chuỗi thao tác đọc–quyết định–ghi của ứng dụng thành một thao tác nguyên tử.

### 12.4. Một query có thể đọc trong khi dữ liệu đang được cập nhật

Đây là tình huống bình thường trong Oracle. Reader thấy phiên bản đã commit tại snapshot; writer tiếp tục cập nhật và commit. Nếu query cần phiên bản cũ mà undo đã bị tái sử dụng trước khi query hoàn tất, query có thể gặp ORA-01555.

Do đó, tính nhất quán khi đọc phụ thuộc cả vào cơ chế MVCC lẫn khả năng duy trì undo trong thời gian cần thiết.

## 13. Lỗi và nhầm lẫn thường gặp

| Hiểu nhầm hoặc dấu hiệu | Giải thích |
| --- | --- |
| SELECT thấy giá trị cũ khi session khác đang UPDATE | Hành vi đúng: consistent read dùng undo |
| SELECT không chờ UPDATE | Reader thường không cần row lock của writer |
| UPDATE chờ UPDATE khác | Writer cần khóa cùng hàng |
| SELECT thứ hai thấy giá trị mới trong cùng transaction | Có thể xảy ra dưới READ COMMITTED vì mỗi statement có snapshot mới |
| Query dài báo ORA-01555 | Undo cần cho snapshot không còn khả dụng |
| COMMIT xong undo biến mất ngay | Sai; undo có thể còn cần cho consistent read/flashback |
| UNDO_RETENTION là cam kết tuyệt đối | Sai nếu không có retention guarantee và đủ dung lượng |
| MVCC nghĩa là không bao giờ blocking | Sai; FOR UPDATE, DML, DDL và các tài nguyên khác vẫn có thể chờ |
| Undo và redo giống nhau | Undo phục vụ rollback/consistent read; redo phục vụ recovery |
| READ COMMITTED cho cùng snapshot suốt transaction | Sai; snapshot được cấp theo statement |

### 13.1. Phân biệt ORA-01555 và lỗi khóa

- **ORA-01555:** không còn undo cần thiết để dựng phiên bản snapshot.
- **Chờ khóa:** session cần một khóa đang được session khác giữ.
- **ORA-08177:** transaction SERIALIZABLE gặp xung đột khiến không thể tiếp tục theo ngữ nghĩa serializable.

Đây là ba vấn đề khác nhau. Tăng undo tablespace không giải quyết một row lock đang bị giữ; tăng timeout không khôi phục undo đã mất; retry transaction SERIALIZABLE cần được thiết kế đúng ở tầng ứng dụng.

### 13.2. COMMIT và ROLLBACK

- `COMMIT` xác nhận thay đổi của transaction, giải phóng các khóa liên quan và làm thay đổi trở nên nhìn thấy với các statement snapshot bắt đầu sau commit.
- `ROLLBACK` hoàn tác thay đổi chưa commit bằng undo và giải phóng khóa.
- Một transaction khác không thấy thay đổi chưa commit của session hiện tại.
- Undo đã commit vẫn có thể được giữ lại cho consistent read và flashback.

## 14. Checklist thiết kế transaction và báo cáo

Trước khi triển khai một quy trình có nhiều session, hãy xác định:

1. **Câu hỏi nghiệp vụ:** cần snapshot nhất quán cho một statement hay cả transaction?
2. **Isolation level:** READ COMMITTED, SERIALIZABLE hay READ ONLY?
3. **Thời lượng:** query/transaction có thể kéo dài bao lâu?
4. **Undo workload:** DML tạo undo với tốc độ nào?
5. **Retention:** undo có được giữ đủ lâu cho query và flashback không?
6. **Khóa:** thao tác nào cần SELECT FOR UPDATE hoặc UPDATE có điều kiện?
7. **Xung đột:** ứng dụng xử lý row lock wait và ORA-08177 thế nào?
8. **Commit boundary:** transaction có được chia theo đơn vị nghiệp vụ hợp lý không?
9. **Giám sát:** theo dõi undo tablespace, V$UNDOSTAT và lỗi snapshot too old.
10. **Recovery:** backup và redo log có đáp ứng mục tiêu phục hồi không?

Một số nguyên tắc:
- Giữ transaction ngắn khi nghiệp vụ cho phép.
- Tránh commit từng hàng trong cursor loop mà không có lý do rõ ràng.
- Không dùng FOR UPDATE nếu chỉ cần đọc.
- Không giả định nhiều statement READ COMMITTED có cùng snapshot.
- Không tăng retention mà không đánh giá dung lượng undo.
- Không dùng Flashback như một bản backup dài hạn.

## 15. Bài tập thực hành

### Bài 1 — Quan sát consistent read

Tạo bảng `DEMO_MVCC_ACCOUNTS` và dữ liệu theo mục 5. Trong session A UPDATE balance từ 5000 xuống 4000 nhưng chưa commit. Chạy SELECT ở session B.

**Kỳ vọng:** session B thấy 5000, không thấy 4000 chưa commit.

### Bài 2 — Quan sát writer blocking

Trong khi session A chưa commit, session B UPDATE cùng account_id.

**Kỳ vọng:** B có thể chờ khóa do A giữ. Sau khi A commit hoặc rollback, B mới có thể tiếp tục tùy trạng thái.

### Bài 3 — So sánh statement snapshot

Session B chạy SELECT, sau đó session A UPDATE và COMMIT, rồi B chạy SELECT lần nữa dưới READ COMMITTED.

**Kỳ vọng:** hai câu SELECT có thể trả giá trị khác nhau vì mỗi statement có snapshot mới.

### Bài 4 — Snapshot trong một cursor dài

Mở một query đọc nhiều hàng ở session A và bắt đầu fetch. Trong lúc cursor vẫn đang chạy, session B cập nhật rồi commit các hàng liên quan.

**Kỳ vọng:** cursor A tiếp tục theo snapshot lúc statement mở; một SELECT mới sau đó có thể thấy thay đổi B đã commit.

### Bài 5 — SERIALIZABLE

Bắt đầu transaction:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT balance
FROM demo_mvcc_accounts
WHERE account_id = 101;
```

Sau đó session khác cập nhật và commit. Chạy lại SELECT ở transaction serializable.

**Kỳ vọng:** transaction tiếp tục nhìn snapshot transaction thay vì snapshot mới theo từng statement. Thử cập nhật xung đột để tìm hiểu ORA-08177 trong môi trường thử nghiệm.

### Bài 6 — READ ONLY

```sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM demo_mvcc_accounts;
SELECT SUM(balance) FROM demo_mvcc_accounts;
SELECT AVG(balance) FROM demo_mvcc_accounts;

COMMIT;
```

**Mục tiêu:** quan sát nhiều statement đọc theo snapshot transaction. Thử DML trong transaction READ ONLY để thấy giới hạn của chế độ.

### Bài 7 — So sánh SELECT và SELECT FOR UPDATE

Chạy SELECT thường rồi SELECT FOR UPDATE trên một hàng. Dùng session khác để UPDATE cùng hàng.

**Kỳ vọng:** SELECT thường không khóa hàng để đọc; SELECT FOR UPDATE yêu cầu khóa và có thể chờ.

### Bài 8 — Xem cấu hình undo

```sql
SELECT name, value
FROM v$parameter
WHERE name IN ('undo_management',
               'undo_tablespace',
               'undo_retention');
```

**Mục tiêu:** đọc các tham số undo nếu tài khoản có quyền. Nếu không có quyền, yêu cầu DBA cung cấp thông tin cấu hình; không cấp quyền rộng chỉ để làm bài tập.

### Bài 9 — Xem thống kê undo

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

**Mục tiêu:** nhận biết mức sử dụng undo, query dài và lỗi snapshot too old. Kết quả là dữ liệu giám sát của instance, không phải dữ liệu bảng nghiệp vụ.

### Bài 10 — Flashback Query

Lấy SCN phù hợp từ môi trường thử nghiệm rồi chạy:

```sql
SELECT account_id, balance
FROM demo_mvcc_accounts AS OF SCN :snapshot_scn
WHERE account_id = 101;
```

**Mục tiêu:** đọc phiên bản cũ nếu undo còn khả dụng và tài khoản có quyền cần thiết.

### Bài 11 — Phân biệt undo và redo

Giải thích vai trò của undo khi ROLLBACK và consistent read, sau đó giải thích redo được dùng trong recovery như thế nào.

### Bài 12 — Chẩn đoán ORA-01555

Một báo cáo chạy 40 phút trên bảng lớn, trong khi hệ thống có nhiều transaction UPDATE. Hãy liệt kê dữ liệu cần thu thập trước khi thay đổi UNDO_RETENTION hoặc kích thước undo tablespace.

**Gợi ý:** SQL gây lỗi, thời gian query, V$UNDOSTAT, undo tablespace, tốc độ DML, tuned retention, cấu hình guarantee và khả năng mở rộng.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): cơ chế concurrency, read consistency và transaction.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo.html): undo records, undo segments và cách sử dụng undo.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, undo retention và cấu hình undo tablespace.
- [Oracle Database SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): isolation level READ ONLY và SERIALIZABLE.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT, FOR UPDATE và Flashback Query.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): theo dõi hiệu năng và chẩn đoán vấn đề database.

Khi đọc và ghi đồng thời trong Oracle, undo cung cấp thông tin để khôi phục phiên bản trước, MVCC cho phép reader quan sát dữ liệu nhất quán mà không phải chờ mọi writer, còn read consistency xác định snapshot mà statement hoặc transaction được nhìn thấy. Hãy phân biệt snapshot theo statement của READ COMMITTED với snapshot theo transaction của SERIALIZABLE/READ ONLY, hiểu vai trò của khóa khi ghi và theo dõi undo retention để tránh lỗi snapshot too old.
