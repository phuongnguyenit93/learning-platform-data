# Consistent snapshot và thời điểm thiết lập ảnh chụp đọc

InnoDB dùng MVCC (Multi-Version Concurrency Control) để cho phép transaction đọc một phiên bản dữ liệu nhất quán mà không phải khóa mọi hàng đang đọc. Phiên bản dữ liệu mà một câu `SELECT` thông thường nhìn thấy được xác định bởi **read view** (ảnh chụp đọc). Thời điểm read view được tạo quyết định transaction nhìn thấy những thay đổi đã commit trước đó và bỏ qua những thay đổi commit sau đó.

Với isolation level `REPEATABLE READ`, các consistent read trong cùng transaction thường dùng chung read view được tạo ở lần consistent read đầu tiên. Vì vậy, `START TRANSACTION` thông thường chưa nhất thiết chụp snapshot ngay tại thời điểm câu lệnh chạy. Nếu muốn chụp ngay khi bắt đầu transaction, có thể dùng `START TRANSACTION WITH CONSISTENT SNAPSHOT` ở `REPEATABLE READ`. Với `READ COMMITTED`, mỗi consistent read tạo snapshot mới cho từng statement.

Hiểu đúng thời điểm snapshot giúp bạn giải thích vì sao hai lần SELECT trong cùng transaction có thể đọc dữ liệu cũ, vì sao transaction bắt đầu trước một lần UPDATE nhưng vẫn nhìn thấy UPDATE đó nếu chưa đọc snapshot, và vì sao locking read có thể trả về phiên bản mới hơn consistent read. Bài học này trình bày cách MVCC xác định dữ liệu nhìn thấy, các mốc tạo snapshot và cách kiểm chứng bằng hai session MySQL.

## 1. Consistent read và MVCC

InnoDB lưu thông tin phiên bản hàng và undo log để có thể dựng lại phiên bản cũ khi một transaction cần đọc snapshot trước đó. Với consistent read, InnoDB dùng read view để xác định transaction nào đã commit tại thời điểm snapshot và phiên bản nào được phép nhìn thấy.

Một `SELECT` thông thường trên bảng InnoDB là consistent nonlocking read trong các isolation level phù hợp. Nó không đặt shared lock trên mọi hàng chỉ vì đọc dữ liệu. Nhờ MVCC, một transaction có thể đọc phiên bản đã commit trước snapshot trong khi transaction khác cập nhật hàng và commit phiên bản mới.

Ví dụ, tài khoản có số dư 100 tại thời điểm snapshot:

```text
Thời gian       Transaction A                  Transaction B
----------------------------------------------------------------
t1              Tạo read view: balance = 100
t2                                             UPDATE balance = 150
t3                                             COMMIT
t4              SELECT balance -> 100
```

Transaction A tiếp tục đọc phiên bản cũ theo read view của nó, dù transaction B đã commit 150. Một transaction mới bắt đầu consistent read sau t3 sẽ nhìn thấy 150.

### Consistent read không phải bản sao vật lý của toàn database

Read view là quy tắc xác định phiên bản hàng nào được nhìn thấy khi đọc InnoDB. Nó không tạo một bản backup, không khóa database và không sao chép toàn bộ bảng ra một vùng dữ liệu độc lập. InnoDB kết hợp read view với phiên bản hàng và undo log để trả về kết quả nhất quán.

Read view thuộc transaction hiện tại. Khi transaction kết thúc, snapshot đó không còn là snapshot có thể dùng lại cho transaction mới. Muốn giữ một kết quả phục vụ phân tích lâu dài, hãy lưu kết quả hoặc dùng cơ chế snapshot/backup phù hợp; không thể giữ read view như một bản sao lưu độc lập.

## 2. Khi nào snapshot được tạo ở REPEATABLE READ?

Trong MySQL, isolation level mặc định của InnoDB thường là `REPEATABLE READ`. Với isolation level này, các consistent read trong cùng transaction dùng cùng một read view.

Nếu transaction được bắt đầu bằng `START TRANSACTION` thông thường, read view thường được tạo khi transaction thực hiện consistent read đầu tiên, không nhất thiết tại câu `START TRANSACTION`.

Ví dụ trình tự:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Lúc này transaction đã bắt đầu, nhưng chưa thực hiện consistent read.
-- Read view chưa nhất thiết được tạo.

SELECT balance
FROM accounts
WHERE account_id = 1;
-- Consistent read đầu tiên: tạo read view cho transaction.

SELECT balance
FROM accounts
WHERE account_id = 1;
-- Dùng lại read view đã tạo.

COMMIT;
```

Nếu một transaction khác commit thay đổi sau `START TRANSACTION` nhưng trước câu SELECT đầu tiên, transaction hiện tại có thể nhìn thấy thay đổi đó vì snapshot chưa được tạo. Nếu thay đổi commit sau consistent read đầu tiên, các consistent read tiếp theo trong cùng transaction vẫn nhìn thấy phiên bản theo snapshot cũ.

Đây là điểm khác biệt quan trọng giữa **thời điểm bắt đầu transaction** và **thời điểm tạo read view**.

## 3. Tạo snapshot ngay khi bắt đầu transaction

Nếu cần xác định snapshot ngay ở đầu transaction, MySQL hỗ trợ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT balance
FROM accounts
WHERE account_id = 1;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` yêu cầu InnoDB tạo consistent read view khi transaction bắt đầu. Vì vậy, các transaction khác commit sau thời điểm này sẽ không xuất hiện trong các consistent read của transaction hiện tại.

Có thể kết hợp với `READ ONLY` cho transaction chỉ đọc:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT account_id, balance
FROM accounts
ORDER BY account_id;

SELECT COUNT(*) AS account_count
FROM accounts;

COMMIT;
```

Hai câu SELECT dùng chung snapshot, phù hợp khi cần đọc nhiều bảng hoặc nhiều truy vấn để tạo một báo cáo nhất quán. `READ ONLY` khai báo ý định không ghi dữ liệu trong transaction và có thể giúp InnoDB tối ưu một số thao tác.

### Điều kiện về isolation level

`WITH CONSISTENT SNAPSHOT` chỉ có ý nghĩa với `REPEATABLE READ`. Ở isolation level khác, MySQL bỏ qua tùy chọn này và phát cảnh báo theo hành vi của phiên bản. Không dùng nó để giả định rằng `READ COMMITTED` sẽ giữ một snapshot xuyên suốt transaction.

Kiểm tra isolation level và cấu hình session:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.autocommit AS autocommit_value;
```

`transaction_isolation` là tên biến trên các bản MySQL hiện đại. Một số phiên bản cũ dùng tên `tx_isolation`; hãy kiểm tra phiên bản server khi làm việc với hệ thống cũ.

## 4. Ví dụ hai session: snapshot được tạo ở lần đọc đầu tiên

Để quan sát chính xác thời điểm tạo snapshot, mở hai connection độc lập đến cùng database. Tạo dữ liệu thử nghiệm một lần:

```sql
CREATE TABLE snapshot_demo (
    id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO snapshot_demo (id, balance)
VALUES (1, 100.00);
```

### Session A

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Chưa đọc snapshot ở thời điểm START TRANSACTION.
```

### Session B

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

### Quay lại Session A

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

Kết quả là `150.00`. Đây là consistent read đầu tiên của transaction A, nên read view được tạo sau khi B đã commit.

Tiếp theo, trong Session B cập nhật lần nữa:

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 200.00
WHERE id = 1;

COMMIT;
```

Trong Session A, đọc lại:

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

Kết quả vẫn là `150.00` vì transaction A đã có read view từ lần SELECT trước. Kết thúc:

```sql
COMMIT;
```

Một transaction mới sẽ nhìn thấy `200.00`.

## 5. Ví dụ hai session: WITH CONSISTENT SNAPSHOT chụp ngay lúc bắt đầu

Reset dữ liệu về một giá trị dễ quan sát:

```sql
UPDATE snapshot_demo
SET balance = 100.00
WHERE id = 1;
```

### Session A

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;
```

Ngay khi transaction bắt đầu, read view được tạo.

### Session B

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

### Quay lại Session A

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

Kết quả là `100.00`, vì snapshot đã được tạo trước khi Session B commit 150. Các consistent read tiếp theo trong Session A tiếp tục nhìn thấy 100 cho tới khi transaction kết thúc.

```sql
COMMIT;
```

Transaction mới sau đó sẽ nhìn thấy 150.

## 6. REPEATABLE READ và READ COMMITTED khác nhau ở thời điểm snapshot

Hai isolation level này đều dùng consistent read của InnoDB, nhưng khác nhau về tuổi thọ read view:

| Isolation level | Thời điểm tạo snapshot cho consistent read | Hai SELECT trong cùng transaction |
|---|---|---|
| `REPEATABLE READ` | Read view đầu tiên được tạo ở consistent read đầu tiên; hoặc ngay lúc bắt đầu nếu dùng `WITH CONSISTENT SNAPSHOT`. | Dùng chung read view, nên có thể đọc cùng phiên bản đã commit. |
| `READ COMMITTED` | Mỗi consistent read tạo read view mới khi statement bắt đầu. | Có thể nhìn thấy commit mới giữa hai statement. |
| `READ UNCOMMITTED` | Không bảo đảm consistent snapshot theo cách trên; SELECT có thể đọc phiên bản chưa commit. | Có thể thấy dữ liệu chưa commit và kết quả không lặp lại ổn định. |

Ví dụ với `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Snapshot cho statement thứ nhất.

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Snapshot mới cho statement thứ hai.

COMMIT;
```

Nếu transaction khác commit giữa hai câu SELECT, câu thứ hai có thể thấy giá trị mới. Đây là hành vi mong đợi của READ COMMITTED, không phải lỗi MVCC.

### Thiết lập isolation level

Đặt cho transaction tiếp theo:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Đặt mặc định cho các transaction trong session hiện tại:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Đặt mặc định cho các session mới (cần quyền phù hợp):

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Thay đổi GLOBAL không đổi isolation level của những session đã kết nối. Khi dùng connection pool, phải kiểm tra session thực tế thay vì giả định mọi connection đã nhận cấu hình mới.

## 7. Consistent read và current read là hai cách đọc khác nhau

Không phải mọi câu SELECT trong transaction đều đọc theo snapshot. InnoDB phân biệt:

- **Consistent read:** SELECT thông thường, đọc phiên bản phù hợp với read view, không đặt row lock theo cách của locking read.
- **Current read:** locking read như `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE` và các thao tác ghi như UPDATE/DELETE cần tìm phiên bản hiện tại để khóa và thay đổi.

Trong `REPEATABLE READ`, current read có thể nhìn thấy phiên bản mới nhất đã commit tại thời điểm đọc, trong khi consistent read vẫn dùng snapshot cũ. Do đó, trộn hai kiểu đọc trong cùng transaction có thể tạo kết quả trông không đồng nhất nếu không hiểu ngữ nghĩa.

Ví dụ:

```sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Giả sử snapshot trả về 100.
```

Trong lúc đó Session B cập nhật và commit balance thành 150:

```sql
-- Session B
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

Sau đó Session A chạy:

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1
FOR UPDATE;
```

Đây là locking/current read, có thể đọc phiên bản hiện tại là 150 và khóa hàng để bảo vệ thao tác ghi tiếp theo. Một câu SELECT thông thường tiếp theo trong Session A vẫn có thể trả về 100 theo read view ban đầu.

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Consistent read vẫn dùng snapshot cũ.

COMMIT;
```

Không dùng `FOR UPDATE` chỉ để “làm mới snapshot”. Nó thay đổi semantics bằng cách khóa hàng và có thể gây chờ khóa hoặc deadlock. Nếu cần dữ liệu mới, thường hãy kết thúc transaction hiện tại rồi bắt đầu transaction mới.

## 8. Transaction nhìn thấy các thay đổi do chính nó thực hiện

Read view không có nghĩa transaction luôn nhìn thấy một phiên bản bất biến tuyệt đối của mọi hàng. Một transaction luôn nhìn thấy các thay đổi mà chính nó đã thực hiện trước đó.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Snapshot ban đầu.

UPDATE snapshot_demo
SET balance = balance + 10.00
WHERE id = 1;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Thấy thay đổi của chính transaction này.

ROLLBACK;
```

Transaction thấy phiên bản mà chính nó vừa ghi. Những thay đổi của transaction khác vẫn bị đánh giá theo read view của nó trong consistent read. Khi đọc nhiều hàng sau khi đã ghi một số hàng, kết quả có thể bao gồm thay đổi của chính transaction cùng với phiên bản snapshot cũ của các hàng chưa được transaction đó sửa.

Điều này là một phần ngữ nghĩa của InnoDB MVCC. Nếu cần một báo cáo chỉ đọc nhất quán, tránh vừa sửa dữ liệu vừa dùng cùng transaction để giả định mọi hàng đều đại diện cho một thời điểm toàn cục thuần túy.

## 9. Autocommit và tuổi thọ snapshot

MySQL thường bật `autocommit` mặc định. Khi `autocommit = 1`, mỗi statement độc lập được thực thi như một transaction riêng nếu không mở transaction tường minh. Một câu SELECT độc lập có snapshot phục vụ chính statement đó; câu SELECT tiếp theo là transaction/statement khác và có thể nhìn thấy commit mới.

Kiểm tra:

```sql
SELECT @@SESSION.autocommit;
```

Muốn nhiều SELECT chia sẻ cùng snapshot, mở transaction rõ ràng:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) FROM accounts;
SELECT SUM(balance) FROM accounts;
SELECT account_id, balance FROM accounts ORDER BY account_id;

COMMIT;
```

Các câu SELECT InnoDB dùng cùng read view trong `REPEATABLE READ`. Nếu không mở transaction, mỗi statement riêng có thể nhìn thấy một trạng thái khác nhau do dữ liệu thay đổi giữa các câu lệnh.

Không nên tắt autocommit toàn session một cách tùy tiện trong connection pool. Khi `autocommit = 0`, transaction có thể tiếp tục mở qua nhiều statement nếu không commit/rollback đúng lúc, giữ snapshot và khóa lâu hơn dự kiến.

## 10. Consistent snapshot trên nhiều bảng

Một lợi ích của read view là nhiều consistent read trong cùng transaction có thể quan sát các bảng InnoDB theo cùng mốc snapshot. Điều này hữu ích cho báo cáo tổng hợp cần đọc tài khoản, giao dịch và lịch sử trong một transaction.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS account_count
FROM accounts;

SELECT COUNT(*) AS transaction_count
FROM account_transactions;

SELECT SUM(amount) AS total_amount
FROM account_transactions;

COMMIT;
```

Nếu các bảng đều dùng InnoDB và các câu lệnh là consistent read, chúng cùng được đánh giá theo snapshot của transaction. Nhờ đó, một báo cáo không lấy số lượng tài khoản từ mốc thời gian này nhưng tổng giao dịch từ mốc khác do transaction khác commit giữa các câu SELECT.

### Lưu ý về storage engine

MVCC consistent snapshot là cơ chế của InnoDB. Nếu transaction đọc bảng không hỗ trợ transaction/MVCC như MyISAM, không thể giả định bảng đó tuân theo cùng snapshot hoặc rollback semantics. Khi báo cáo cần tính nhất quán xuyên bảng, nên dùng InnoDB cho các bảng liên quan và xác minh storage engine thực tế.

Kiểm tra engine:

```sql
SELECT
    table_name,
    engine
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('accounts', 'account_transactions');
```

## 11. Snapshot lâu và chi phí undo/purge

Một transaction giữ read view lâu có thể ngăn InnoDB loại bỏ một số phiên bản hàng cũ mà snapshot đó vẫn có thể cần đọc. Các phiên bản cũ được duy trì trong undo history cho đến khi không còn read view nào cần chúng và purge có thể dọn dẹp.

Transaction đọc lâu có thể dẫn đến:

- Undo history tăng và purge bị chậm lại.
- Tablespace undo hoặc vùng lưu trữ tăng.
- Tốn I/O và CPU để giữ, tìm hoặc dọn phiên bản cũ.
- Các truy vấn khác chịu tác động gián tiếp khi history list dài.
- Connection pool bị chiếm dụng bởi transaction không kết thúc.

Ví dụ rủi ro:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*)
FROM very_large_table;

-- Ứng dụng giữ transaction mở trong nhiều phút hoặc nhiều giờ.
-- Các transaction khác vẫn cập nhật dữ liệu liên tục.

-- Chỉ kết thúc khi đã đọc xong:
COMMIT;
```

`READ ONLY` không có nghĩa transaction không giữ snapshot hoặc không gây chi phí undo/purge. Nếu transaction cần đọc lâu, cân nhắc chia nhỏ công việc, tạo bảng staging/report snapshot, xuất dữ liệu theo lô hoặc dùng giải pháp báo cáo chuyên biệt.

### Theo dõi transaction và history list

Có thể kiểm tra transaction đang mở:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_isolation_level,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Để xem thêm trạng thái InnoDB:

```sql
SHOW ENGINE INNODB STATUS;
```

Trong phần TRANSACTIONS, xem thông tin transaction đang chạy và history list length. Đây là tín hiệu cần điều tra cùng với thời gian transaction mở, tải ghi và tốc độ purge; không dùng một con số đơn lẻ làm kết luận rằng hệ thống đã gặp sự cố.

## 12. Đọc nhất quán và locking không thay thế nhau

Hãy chọn kiểu đọc theo mục tiêu:

| Mục tiêu | Cách tiếp cận |
|---|---|
| Báo cáo cần cùng một trạng thái đã commit trên nhiều SELECT | Transaction `REPEATABLE READ` với consistent read; cân nhắc `WITH CONSISTENT SNAPSHOT`. |
| Mỗi statement cần nhìn thấy commit mới nhất trước khi statement bắt đầu | `READ COMMITTED`. |
| Đọc hàng rồi cập nhật chính hàng đó, cần tránh transaction khác sửa đồng thời | Locking read `SELECT ... FOR UPDATE`. |
| Chỉ đọc dữ liệu mà không cần khóa hàng | SELECT thông thường dùng consistent read. |
| Cần đọc dữ liệu mới sau một snapshot cũ | Kết thúc transaction và bắt đầu transaction mới. |

Không dùng locking read để giải quyết mọi vấn đề về dữ liệu cũ. Locking read có thể chặn transaction khác, tạo deadlock và làm giảm throughput. Ngược lại, consistent read không khóa hàng nên không thể thay thế khóa khi cần bảo vệ một quyết định ghi.

## 13. Quy trình kiểm chứng thời điểm snapshot

Khi một ứng dụng báo rằng dữ liệu đọc “bị cũ”, hãy kiểm tra theo thứ tự:

1. Xác định storage engine của bảng; xác nhận các bảng liên quan dùng InnoDB.
2. Kiểm tra isolation level thực tế của connection, không chỉ global default.
3. Xác định autocommit và transaction có được mở tường minh không.
4. Tìm thời điểm `START TRANSACTION` hoặc `BEGIN`.
5. Tìm consistent read đầu tiên trong transaction.
6. Kiểm tra transaction có dùng `WITH CONSISTENT SNAPSHOT` không.
7. Kiểm tra có locking read (`FOR UPDATE`, `FOR SHARE`) hoặc DML xen giữa các SELECT không.
8. Đối chiếu thời điểm commit của transaction ghi với thời điểm tạo read view.
9. Kiểm tra transaction có bị giữ mở bởi ứng dụng hoặc connection pool không.
10. Kết thúc transaction đúng lúc và xác minh transaction mới nhìn thấy dữ liệu mới.

Một log ứng dụng hữu ích nên ghi connection/transaction boundary, isolation level, thời điểm bắt đầu, thời điểm query và thời điểm commit/rollback. Tránh chỉ ghi SQL text mà thiếu thông tin transaction vì rất khó tái dựng read view đã được tạo khi nào.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `START TRANSACTION` luôn tạo snapshot ngay | Bỏ sót commit xảy ra trước consistent read đầu tiên | Phân biệt transaction start và read-view creation; dùng `WITH CONSISTENT SNAPSHOT` khi cần. |
| Nghĩ mọi SELECT trong RR luôn thấy dữ liệu mới nhất | Lần đọc sau vẫn dùng snapshot cũ | Kết thúc transaction và bắt đầu transaction mới nếu cần snapshot mới. |
| Dùng `WITH CONSISTENT SNAPSHOT` ở READ COMMITTED rồi kỳ vọng snapshot cố định | Tùy chọn bị bỏ qua ở isolation level không hỗ trợ | Đặt RR trước khi bắt đầu transaction. |
| Nhầm consistent read với `SELECT ... FOR UPDATE` | Không hiểu vì sao locking read thấy phiên bản mới | Phân biệt snapshot read và current/locking read. |
| Dùng `FOR UPDATE` chỉ để làm mới dữ liệu | Khóa không cần thiết, tăng chờ khóa và deadlock | Commit/rollback transaction cũ rồi mở transaction mới. |
| Nghĩ READ ONLY không giữ undo history | Transaction đọc lâu vẫn giữ read view | Kết thúc transaction sớm và theo dõi purge/history list. |
| Giữ transaction mở qua nhiều request trong connection pool | Snapshot cũ kéo dài, connection bị chiếm | Đặt transaction boundary rõ ràng và luôn commit/rollback trong finally/try-with-resources. |
| Giả định MyISAM có MVCC snapshot như InnoDB | Kết quả không có cùng semantics transaction | Dùng InnoDB cho dữ liệu cần consistent read. |
| Dùng autocommit và mong nhiều SELECT chia sẻ một snapshot | Mỗi statement có transaction/snapshot riêng | Mở transaction tường minh khi cần đọc nhiều câu cùng mốc. |
| Không kiểm tra session isolation trong pool | Một số connection chạy isolation khác nhau | Thiết lập/reset isolation cho từng connection và kiểm tra `@@SESSION.transaction_isolation`. |

## 15. Bài tập thực hành

### Bài tập A — Snapshot ở lần đọc đầu tiên

1. Tạo bảng `snapshot_demo` dùng InnoDB và chèn balance 100.
2. Session A đặt `REPEATABLE READ` rồi chạy `START TRANSACTION` nhưng chưa SELECT.
3. Session B cập nhật balance thành 150 và commit.
4. Session A SELECT lần đầu và ghi lại kết quả.
5. Session B cập nhật thành 200 và commit; Session A SELECT lần nữa.
6. Giải thích vì sao Session A thấy 150 ở cả hai lần đọc.

### Bài tập B — WITH CONSISTENT SNAPSHOT

1. Reset balance về 100.
2. Session A chạy `START TRANSACTION WITH CONSISTENT SNAPSHOT`.
3. Session B cập nhật balance thành 150 và commit.
4. Session A SELECT và ghi lại kết quả.
5. So sánh với bài tập A để giải thích snapshot được tạo ở hai thời điểm khác nhau.

### Bài tập C — READ COMMITTED

1. Session A đặt isolation level `READ COMMITTED` và mở transaction.
2. Session A SELECT balance lần đầu.
3. Session B cập nhật balance và commit.
4. Session A SELECT lần thứ hai.
5. Giải thích vì sao câu thứ hai có thể nhìn thấy commit mới.

### Bài tập D — Consistent read và current read

1. Session A mở transaction `REPEATABLE READ` và SELECT thông thường.
2. Session B cập nhật và commit.
3. Session A chạy `SELECT ... FOR UPDATE`.
4. Session A chạy lại SELECT thông thường.
5. So sánh phiên bản nhìn thấy và giải thích vì sao hai kiểu đọc khác nhau.

### Bài tập E — Transaction dài và undo history

1. Mở transaction read-only có consistent snapshot.
2. Trong session khác, cập nhật cùng bảng nhiều lần rồi commit.
3. Quan sát transaction trong `information_schema.innodb_trx`.
4. Xem `SHOW ENGINE INNODB STATUS` và history list length.
5. Commit transaction đọc và quan sát quá trình purge tiếp tục.

Bạn hoàn thành bài khi có thể xác định thời điểm read view được tạo, dự đoán kết quả giữa hai session ở REPEATABLE READ/READ COMMITTED, phân biệt consistent read với current read và giải thích tác động của transaction giữ snapshot quá lâu.

## 16. Nguyên tắc cần ghi nhớ

- InnoDB dùng MVCC và read view để cung cấp consistent nonlocking read.
- Trong `REPEATABLE READ`, read view thông thường được tạo ở consistent read đầu tiên; các consistent read tiếp theo trong transaction dùng lại view đó.
- `START TRANSACTION` không nhất thiết tạo snapshot ngay; `START TRANSACTION WITH CONSISTENT SNAPSHOT` tạo snapshot ngay khi bắt đầu ở `REPEATABLE READ`.
- `WITH CONSISTENT SNAPSHOT` bị bỏ qua ở isolation level khác; không dùng nó để tạo snapshot cố định trong READ COMMITTED.
- Trong `READ COMMITTED`, mỗi consistent read tạo snapshot mới ở đầu statement.
- `SELECT ... FOR UPDATE`, `FOR SHARE` và DML dùng current/locking read theo semantics của InnoDB, khác với consistent read.
- Transaction luôn nhìn thấy thay đổi do chính nó thực hiện.
- Autocommit khiến mỗi statement độc lập kết thúc transaction riêng; muốn nhiều SELECT cùng snapshot phải mở transaction tường minh.
- Consistent snapshot hữu ích cho nhiều truy vấn trên các bảng InnoDB cùng một mốc đọc.
- Transaction giữ snapshot lâu có thể giữ undo history và làm chậm purge, kể cả khi transaction là READ ONLY.
- Kiểm tra isolation level thực tế, transaction boundary, `innodb_trx` và InnoDB status khi điều tra dữ liệu đọc cũ.
- Kết thúc transaction sớm sau khi hoàn thành công việc đọc để giải phóng read view.

Khi nắm được thời điểm InnoDB tạo read view và phân biệt consistent read với current read, bạn có thể dự đoán chính xác dữ liệu mà mỗi transaction nhìn thấy. Điều này giúp xây dựng báo cáo nhất quán, xử lý hiện tượng dữ liệu cũ và tránh giữ snapshot lâu gây áp lực lên undo/purge.
