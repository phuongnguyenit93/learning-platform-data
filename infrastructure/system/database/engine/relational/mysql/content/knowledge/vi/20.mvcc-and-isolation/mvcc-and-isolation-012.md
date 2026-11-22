# Giao dịch đọc kéo dài, undo history và hoạt động purge

InnoDB dùng MVCC (Multi-Version Concurrency Control) để một truy vấn đọc nhất quán có thể nhìn thấy phiên bản dữ liệu phù hợp với snapshot của nó trong khi transaction khác vẫn tiếp tục cập nhật. Khi một hàng bị cập nhật hoặc xóa, InnoDB giữ thông tin phiên bản cũ trong undo log để transaction đọc cũ có thể dựng lại dữ liệu mà nó được phép nhìn thấy.

Các phiên bản cũ không thể bị dọn ngay khi transaction ghi commit, vì vẫn có thể còn một read view cần chúng. Purge là tiến trình nền dọn các phiên bản và undo history đã không còn cần thiết. Một transaction đọc kéo dài có thể giữ read view cũ trong thời gian dài, khiến purge phải chờ, history list tăng và dung lượng undo cần thiết tiếp tục được giữ lại.

Trong module `DATABASE_MYSQL`, hiểu mối liên hệ giữa consistent read, read view, undo history và purge giúp chẩn đoán transaction tồn tại lâu, truy vấn chậm dần, undo tablespace tăng và DDL bị chờ metadata lock. Bài học tập trung vào InnoDB trên MySQL 8.0 trở lên.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao InnoDB cần lưu phiên bản hàng cũ trong undo log.
- Mô tả cách read view xác định phiên bản mà consistent read được phép nhìn thấy.
- Phân biệt transaction bắt đầu lâu với read view đã được tạo và đang giữ lâu.
- So sánh ảnh hưởng của `REPEATABLE READ` và `READ COMMITTED` tới thời gian tồn tại snapshot.
- Giải thích vì sao transaction chỉ đọc cũng có thể ngăn purge dọn undo history.
- Đọc `History list length` và thông tin transaction để nhận diện dấu hiệu purge lag.
- Hiểu tác động tới undo tablespace, hiệu năng đọc và metadata lock.
- Chọn biện pháp xử lý transaction dài và giảm nguy cơ tái diễn.

## 1. Vì sao InnoDB phải giữ phiên bản hàng cũ?

Giả sử một báo cáo bắt đầu đọc số dư tài khoản tại thời điểm T1. Trong lúc báo cáo chạy, một transaction khác cập nhật số dư và commit ở T2. Nếu InnoDB chỉ giữ giá trị mới, báo cáo đang dùng snapshot cũ có thể đọc một giá trị không thuộc thời điểm mà snapshot đại diện.

MVCC giải quyết vấn đề này bằng cách giữ đủ thông tin để tái dựng phiên bản cũ. Một truy vấn consistent read có thể đọc phiên bản phù hợp với read view của nó mà thường không cần khóa hàng để ngăn các transaction khác ghi.

Ví dụ khái niệm:

```text
Thời gian ------------------------------------------------------>

Transaction A (đọc):  tạo read view R1 -------- SELECT -------- COMMIT
                                              |
Transaction B (ghi):       UPDATE balance ---- COMMIT
                                              |
Phiên bản hàng:        balance = 100       balance = 80
Undo history:          giữ thông tin để R1 dựng lại balance = 100
Purge:                 chưa thể xóa phiên bản cũ khi R1 còn cần nó
```

Nếu transaction A còn giữ read view R1, purge không được xóa thông tin undo cần để dựng phiên bản `balance = 100`. Khi A kết thúc và không còn read view nào cần phiên bản đó, purge có thể dọn phần history tương ứng.

## 2. Undo log và các phiên bản hàng

Undo log lưu thông tin cần thiết để hoàn tác thay đổi và hỗ trợ MVCC. Với hàng InnoDB, record trong clustered index có các metadata nội bộ như transaction ID và con trỏ undo. Khi hàng được cập nhật, InnoDB ghi undo record mô tả trạng thái trước đó; chuỗi undo cho phép dựng lại phiên bản mà một read view cũ cần.

### 2.1. Undo phục vụ rollback và consistent read

Undo có hai vai trò liên quan:

- **Rollback:** nếu transaction ghi chưa commit và cần hủy, InnoDB dùng undo để phục hồi trạng thái trước thay đổi.
- **MVCC/consistent read:** sau khi transaction ghi commit, undo có thể vẫn cần để một read view cũ dựng lại phiên bản đã tồn tại trước lần cập nhật.

Vì vậy, commit không đồng nghĩa mọi undo record của transaction được xóa ngay. Một phần update undo vẫn cần tồn tại cho tới khi không còn read view nào có thể cần nó và purge xử lý được history đó.

### 2.2. Insert undo và update undo

InnoDB phân biệt undo phục vụ thao tác insert với undo phục vụ update/delete. Insert undo chủ yếu cần cho rollback khi transaction chưa commit; sau khi transaction commit, bản ghi insert không cần được tái dựng thành một phiên bản trước đó cho consistent read. Update undo có thể tiếp tục cần sau commit vì read view cũ phải nhìn thấy giá trị trước update hoặc hàng trước khi bị delete-mark.

Không cần quản lý từng undo record bằng tay. Điều quan trọng ở góc độ vận hành là transaction đọc cũ có thể kéo dài thời gian cần giữ update undo, làm purge không thể dọn history ở phía sau nó.

### 2.3. Undo tablespace không phải một bản sao lưu

Undo log là cấu trúc nội bộ phục vụ transaction, rollback và MVCC. Nó không thay thế backup, binary log hoặc cơ chế point-in-time recovery. Không xóa hay chỉnh sửa file undo tablespace thủ công để xử lý dung lượng; thao tác đó có thể làm hỏng database.

## 3. Read view và consistent read

Read view là tập thông tin InnoDB dùng để xác định transaction nào đã commit và phiên bản hàng nào có thể nhìn thấy tại snapshot. Khi consistent read gặp một phiên bản mới hơn snapshot, InnoDB lần theo undo để tìm phiên bản cũ phù hợp.

Read view không phải bản sao vật lý của toàn bộ database. Nó là mốc visibility để InnoDB quyết định phiên bản nào được truy vấn nhìn thấy.

### 3.1. Khi nào read view được tạo?

Với `REPEATABLE READ` (mức cô lập mặc định của InnoDB), một consistent read thông thường trong transaction tạo read view ở lần đọc consistent đầu tiên; các consistent read tiếp theo trong cùng transaction dùng lại snapshot đó. Có thể yêu cầu tạo snapshot ngay khi bắt đầu transaction bằng `START TRANSACTION WITH CONSISTENT SNAPSHOT` trong điều kiện isolation phù hợp.

Với `READ COMMITTED`, mỗi consistent read thông thường tạo một read view mới cho statement đó. Một transaction có thể nhìn thấy commit mới ở statement tiếp theo, dù transaction chưa kết thúc.

Ví dụ yêu cầu snapshot được tạo ngay lúc bắt đầu transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT account_id, balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` có hiệu lực để tạo snapshot nhất quán khi isolation level là `REPEATABLE READ`; không dùng nó như cách ép `READ COMMITTED` giữ cùng một snapshot qua nhiều statement.

Điều này có nghĩa `trx_started` lâu không tự chứng minh read view đã tồn tại suốt thời gian đó. Ví dụ, transaction RR bắt đầu nhưng chưa thực hiện consistent read thì read view thông thường chưa được tạo; transaction có `WITH CONSISTENT SNAPSHOT` là trường hợp khác. Khi điều tra, cần xem isolation level và các thao tác đọc thực tế.

### 3.2. Consistent read và locking read

Một `SELECT` thông thường trên InnoDB thường là consistent nonlocking read. `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là locking/current read, có quy tắc đọc dữ liệu hiện hành và khóa khác với consistent read thông thường.

Không nên suy luận rằng một locking read sẽ giải phóng read view cũ đã được tạo trước đó trong cùng transaction. Nếu transaction đã thực hiện consistent read dưới RR rồi giữ transaction mở, read view cũ vẫn có thể tiếp tục giữ undo history cần thiết cho tới khi transaction kết thúc.

## 4. Transaction đọc kéo dài giữ undo history như thế nào?

Một transaction đọc kéo dài có thể chỉ chạy một câu `SELECT` ban đầu rồi nằm idle, nhưng vẫn giữ snapshot nếu transaction chưa kết thúc. Trong thời gian đó, các transaction khác có thể cập nhật/xóa hàng và commit. Undo history mới được thêm vào; purge phải bảo toàn các phiên bản cần thiết cho read view cũ.

```text
Thời gian -------------------------------------------------------------->

Session A: START TRANSACTION; SELECT ... (tạo read view R1) -------- COMMIT
                 |                                                 |
                 |       Session A idle nhưng transaction vẫn mở  |
                 |                                                 |
Session B:       UPDATE/DELETE -- COMMIT -- UPDATE -- COMMIT -- ...
                       |                 |                 |
Undo history:         U1                U2                U3
                       \_______________________________   |
Purge:                  không thể dọn phiên bản cần R1  -> dọn sau khi A kết thúc
```

Transaction A không cần liên tục chạy truy vấn để tiếp tục giữ read view. Nếu ứng dụng quên `COMMIT`/`ROLLBACK`, hoặc giữ transaction mở trong lúc chờ người dùng hay gọi dịch vụ ngoài, read view có thể tồn tại lâu hơn nhiều so với thời gian thực thi SQL.

### 4.1. Transaction chỉ đọc vẫn có thể giữ snapshot

`START TRANSACTION READ ONLY` ngăn các thao tác ghi thông thường trong transaction và có thể giúp InnoDB tối ưu một số công việc nội bộ. Tuy nhiên, read-only không có nghĩa là snapshot tự hết hạn sau câu SELECT đầu tiên. Một read-only transaction dùng consistent read rồi giữ mở vẫn có thể ngăn purge loại bỏ phiên bản cũ mà snapshot cần.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION READ ONLY;

SELECT account_id, balance
FROM account_balance
WHERE account_id = 100;

-- Ứng dụng có thể đang idle tại đây.
-- Read view vẫn có thể được giữ trong transaction.

COMMIT;
```

Nếu chỉ cần một câu đọc độc lập, để autocommit xử lý transaction statement-level thường tránh giữ snapshot lâu. Nếu cần nhiều câu đọc cùng một snapshot, phải giữ transaction mở có chủ đích và đặt giới hạn thời gian phù hợp.

### 4.2. Một statement dài cũng có thể giữ read view trong thời gian chạy

Ngay cả khi autocommit bật, một câu SELECT mất nhiều phút vẫn cần snapshot trong suốt thời gian statement chạy. Khi statement hoàn tất, transaction tự động kết thúc theo autocommit và read view của statement không còn bị giữ bởi transaction đó.

Do đó, có hai dạng cần phân biệt:

- **Statement dài:** read view tồn tại trong thời gian truy vấn đang chạy.
- **Transaction dài:** read view có thể tồn tại sau khi statement kết thúc, kể cả khi connection đang idle, cho tới khi transaction commit/rollback.

## 5. Isolation level ảnh hưởng thời gian giữ snapshot

### 5.1. REPEATABLE READ

Trong InnoDB RR, consistent read đầu tiên tạo snapshot và các consistent read sau trong cùng transaction dùng lại snapshot đó. Nếu transaction tồn tại lâu, read view cũng có thể tồn tại lâu.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE account_id = 100;

-- Các consistent read sau tiếp tục dùng cùng snapshot.
SELECT balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

RR phù hợp khi nhiều lần đọc trong một transaction cần nhìn cùng một snapshot. Đổi lại, một read view lâu đời có thể giữ lại undo history lâu hơn.

### 5.2. READ COMMITTED

Trong RC, mỗi consistent read tạo read view mới. Transaction không giữ một snapshot chung cho mọi SELECT thông thường; mỗi statement có thể thấy các thay đổi đã commit trước khi statement đó bắt đầu.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE account_id = 100;

-- Một transaction khác cập nhật và commit.

SELECT balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

SELECT thứ hai có thể thấy giá trị mới đã commit. Snapshot của statement đầu không cần được giữ làm snapshot của statement sau, nên RC thường giảm tác động giữ read view xuyên nhiều statement. Tuy nhiên, một statement RC chạy lâu vẫn giữ read view trong lúc nó thực thi; RC không loại bỏ chi phí của statement dài.

### 5.3. So sánh nhanh

| Đặc điểm | REPEATABLE READ | READ COMMITTED |
|---|---|---|
| Read view của consistent read | Tạo ở lần đọc consistent đầu tiên trong transaction, trừ khi yêu cầu snapshot sớm | Tạo mới cho từng consistent read statement |
| Hai SELECT trong cùng transaction | Thường thấy cùng snapshot | Có thể thấy commit mới giữa hai statement |
| Read view cũ bị giữ qua nhiều statement | Có, cho tới khi transaction kết thúc | Thường không; mỗi statement có snapshot riêng |
| Statement đọc kéo dài | Giữ read view trong lúc chạy | Giữ read view trong lúc chạy |
| Tác động của transaction idle sau SELECT | Có thể tiếp tục giữ snapshot cũ | Snapshot của statement trước không phải snapshot dùng cho statement kế tiếp, nhưng transaction vẫn có thể giữ tài nguyên/metadata lock khác |

Không đổi isolation level chỉ để làm purge chạy nhanh hơn mà chưa đánh giá semantics nghiệp vụ. Thay đổi RR sang RC có thể làm hai lần đọc trong cùng transaction thấy dữ liệu khác nhau.

## 6. Purge là gì?

Purge là tiến trình nền của InnoDB dọn các phiên bản hàng và undo log record không còn cần thiết cho rollback hoặc bất kỳ read view đang hoạt động nào. Nó xử lý history do các transaction ghi tạo ra sau khi commit, khi những phiên bản cũ đã trở nên an toàn để loại bỏ.

Purge không phải thao tác `DELETE` do ứng dụng gọi, cũng không phải một lệnh SQL mà người dùng phải chạy thủ công sau mỗi transaction. InnoDB tự quản lý các purge thread.

### 6.1. Điều kiện để một phiên bản được purge

Về mặt khái niệm, một phiên bản cũ chỉ có thể được dọn khi không còn read view nào cần nó. Nếu có một read view lâu đời vẫn có thể nhìn thấy phiên bản đó, purge phải giữ lại undo cần thiết. Sau khi transaction giữ read view kết thúc, purge có thể tiếp tục xử lý history nếu tốc độ dọn đủ nhanh.

Ngoài read view, purge còn phải xử lý các delete-marked record và các ràng buộc nội bộ khác. Vì vậy, việc transaction cũ kết thúc không có nghĩa mọi undo history lập tức biến mất ngay tại thời điểm commit; purge chạy bất đồng bộ.

### 6.2. Purge thread và khả năng bắt kịp

InnoDB có các purge thread để xử lý history nền. Nếu tốc độ transaction ghi tạo undo vượt tốc độ purge dọn, history list có thể tăng ngay cả khi không có một transaction đọc duy nhất nào giữ snapshot quá lâu.

Vì vậy, khi thấy history list lớn, cần kiểm tra cả hai khả năng:

- Một read view cũ đang ngăn purge đi qua phần history cần giữ.
- Workload ghi tạo undo nhanh hơn khả năng purge xử lý.

Không vội tăng `innodb_purge_threads` hoặc thay đổi các biến purge lag chỉ dựa trên một lần đọc metric. Trước tiên xác định nguồn giữ history, mức tạo undo, CPU/I/O và cấu hình thực tế.

## 7. History list length và cách đọc

`SHOW ENGINE INNODB STATUS` hiển thị thông tin transaction và purge. Trong phần TRANSACTIONS thường có dòng tương tự:

```text
History list length 12500
```

History list length là chỉ số về lượng undo log page nằm trong history list đang chờ purge xử lý. Nó hữu ích để theo dõi xu hướng, nhưng không phải số hàng bị xóa, số transaction đang mở, số byte chính xác hay tuổi của transaction.

### 7.1. Kiểm tra trạng thái InnoDB

Trong MySQL CLI:

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `TRANSACTIONS`, `History list length`, trạng thái purge và thông tin transaction đang hoạt động. So sánh nhiều lần theo thời gian:

- History list length tăng liên tục: purge đang bị chặn hoặc không theo kịp workload.
- History list length giảm: purge đang xử lý được backlog.
- Chỉ số dao động: có thể là trạng thái bình thường theo workload; cần xem xu hướng và thời gian duy trì.

Không đặt một ngưỡng duy nhất cho mọi hệ thống. Mức có thể chấp nhận phụ thuộc tốc độ ghi, kích thước dữ liệu, latency, dung lượng undo và thời gian snapshot dài nhất.

### 7.2. Kiểm tra metric InnoDB nếu được bật

Một số phiên bản/cấu hình cung cấp metric `trx_rseg_history_len` trong `INFORMATION_SCHEMA.INNODB_METRICS`:

```sql
SELECT NAME, COUNT
FROM INFORMATION_SCHEMA.INNODB_METRICS
WHERE NAME = 'trx_rseg_history_len';
```

Nếu metric không xuất hiện hoặc không được bật trong môi trường hiện tại, dùng `SHOW ENGINE INNODB STATUS` và hệ thống monitoring hiện có. Không diễn giải `COUNT` thành byte hoặc số row version.

## 8. Tìm transaction đang mở lâu

`INFORMATION_SCHEMA.INNODB_TRX` cung cấp thông tin về transaction InnoDB hiện tại. Có thể sắp xếp theo thời điểm bắt đầu để tìm transaction lâu nhất:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_isolation_level,
    trx_is_read_only,
    trx_rows_locked,
    trx_rows_modified,
    trx_mysql_thread_id,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
```

Các cột hữu ích:

- `trx_started`: thời điểm transaction bắt đầu.
- `age_seconds`: tuổi transaction tính tại lúc chạy truy vấn giám sát.
- `trx_isolation_level`: isolation level của transaction.
- `trx_is_read_only`: transaction có được đánh dấu read-only hay không.
- `trx_rows_locked`: số hàng đang bị transaction khóa theo thông tin InnoDB.
- `trx_rows_modified`: số hàng transaction đã sửa.
- `trx_mysql_thread_id`: connection ID, có thể đối chiếu với process list.
- `trx_query`: statement hiện tại; có thể `NULL` nếu transaction đang idle.

Transaction có `trx_query IS NULL` nhưng `trx_started` rất cũ có thể là session idle trong transaction. Đây là dấu hiệu đáng điều tra, đặc biệt khi history list length đang tăng.

### 8.1. Đối chiếu connection ID với process list

```sql
SHOW FULL PROCESSLIST;
```

Đối chiếu `trx_mysql_thread_id` với cột `Id` để xem user, host, database, command, thời gian và trạng thái connection. Tìm các session `Sleep` nhưng vẫn có transaction trong `INNODB_TRX`; chúng thường là ứng viên cần kiểm tra kỹ.

Không kết luận transaction nào gây purge lag chỉ dựa vào tuổi. Cần xác định nó đã tạo read view chưa, isolation level nào, có đang giữ metadata lock hay không và history list thay đổi thế nào trong cùng khoảng thời gian.

## 9. Tác động của transaction đọc kéo dài

### 9.1. Undo history tăng và purge bị chặn

Nếu read view cũ cần các phiên bản trước một mốc thời gian, purge không thể dọn các undo record có thể cần cho snapshot đó. Workload update/delete vẫn tiếp tục tạo history mới, làm backlog tăng.

### 9.2. Consistent read phải đi qua chuỗi phiên bản dài hơn

Khi một hàng bị cập nhật nhiều lần, một truy vấn cần phiên bản rất cũ có thể phải lần qua nhiều undo version. Chuỗi phiên bản dài làm tăng công việc dựng lại row version, có thể làm consistent read chậm hơn.

### 9.3. Undo tablespace và dung lượng đĩa

Undo pages cần được giữ lại hoặc tái sử dụng. Khi backlog tăng, không gian undo có thể tăng và không gian đã cấp phát có thể chưa trả ngay cho hệ điều hành sau khi purge bắt kịp. Việc giải phóng dung lượng file undo tablespace phụ thuộc cấu hình undo tablespace và cơ chế truncate; purge backlog giảm không đồng nghĩa file luôn thu nhỏ ngay.

Không xóa file undo tablespace hoặc sửa file hệ thống bằng tay. Kiểm tra cấu hình và tài liệu phiên bản MySQL trước khi thay đổi chính sách truncate.

### 9.4. Metadata lock có thể khiến DDL bị chờ

Transaction giữ bảng đã truy cập có thể giữ metadata lock tới khi transaction kết thúc. Một transaction đọc kéo dài vì thế có thể làm `ALTER TABLE`, `RENAME TABLE` hoặc DDL cần metadata lock độc quyền phải chờ. Khi DDL đang chờ, các truy vấn mới vào bảng cũng có thể bị xếp hàng sau yêu cầu metadata lock tùy tình huống.

Đây là cơ chế khác với việc giữ undo history, dù cả hai có thể cùng xuất hiện trong một transaction dài. Chẩn đoán DDL bị chờ cần xem metadata lock và process list, không chỉ xem history list length.

## 10. Hai-session lab: RR giữ snapshot lâu

Thực hiện trong database lab riêng. Tạo dữ liệu:

```sql
CREATE TABLE mvcc_demo_account (
    account_id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO mvcc_demo_account (account_id, balance)
VALUES (100, 1000.00);
```

### Session A: mở transaction RR và đọc lần đầu

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
-- Kết quả: 1000.00
```

Sau SELECT đầu tiên, read view của RR được tạo. Để transaction A mở và không commit.

### Session B: cập nhật và commit nhiều lần

```sql
START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 900.00
WHERE account_id = 100;
COMMIT;

START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 800.00
WHERE account_id = 100;
COMMIT;
```

### Quay lại Session A

```sql
SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Trong RR, consistent read của A vẫn nhìn thấy `1000.00`, mặc dù B đã commit `800.00`. InnoDB dùng undo để dựng phiên bản cũ phù hợp với read view A.

Kết thúc Session A:

```sql
COMMIT;
```

Sau khi không còn read view nào cần các phiên bản cũ, purge có thể tiếp tục dọn history đó. Quá trình diễn ra nền, nên không nhất thiết history list giảm ngay tại thời điểm commit.

## 11. Hai-session lab: READ COMMITTED tạo snapshot mới cho từng statement

Đặt Session A ở RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Giả sử kết quả ban đầu là `800.00`. Session B cập nhật và commit `700.00`:

```sql
START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 700.00
WHERE account_id = 100;
COMMIT;
```

Chạy lại SELECT ở Session A:

```sql
SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Trong RC, statement thứ hai có thể thấy `700.00` vì nó tạo read view mới. Transaction A vẫn mở, nhưng snapshot của statement đầu không được tái sử dụng cho statement thứ hai như RR.

Kết thúc Session A:

```sql
COMMIT;
```

## 12. Tình huống transaction idle trong ứng dụng

Một lỗi phổ biến trong ứng dụng JDBC hoặc connection pool là bắt đầu transaction, chạy SELECT rồi chờ xử lý ngoài database mà quên kết thúc transaction:

```java
connection.setAutoCommit(false);

try {
    readReportRows(connection);

    // Không nên giữ transaction mở trong lúc chờ người dùng,
    // gọi HTTP service hoặc xử lý file dài.
    callExternalService();

    connection.commit();
} catch (Exception failure) {
    connection.rollback();
    throw failure;
}
```

Nếu `readReportRows()` đã tạo consistent read view trong RR, thời gian gọi dịch vụ ngoài cũng kéo dài tuổi snapshot. Connection có thể xuất hiện ở trạng thái `Sleep` trong process list nhưng transaction vẫn mở.

Thiết kế tốt hơn thường là:

- Chỉ mở transaction ngay trước các thao tác database cần tính nhất quán.
- Kết thúc transaction ngay sau khi các thao tác đó hoàn tất.
- Không giữ transaction qua thời gian chờ mạng, nhập liệu hoặc tương tác người dùng.
- Đảm bảo mọi nhánh exception đều rollback và trả connection sạch về pool.
- Với truy vấn chỉ đọc độc lập, cân nhắc autocommit hoặc transaction read-only ngắn.

Nếu cần xử lý một báo cáo rất dài trên một snapshot duy nhất, đó là quyết định kiến trúc có chủ đích. Hãy đo tác động undo history, chạy ở replica phù hợp nếu có, giới hạn thời gian và lên kế hoạch kết thúc snapshot.

## 13. Giảm tác động của truy vấn đọc kéo dài

### 13.1. Giữ transaction ngắn

Đây là biện pháp quan trọng nhất. Tránh mở transaction ở đầu request rồi giữ qua nhiều bước không cần database. Commit/rollback ngay khi công việc transactional hoàn tất.

### 13.2. Phân trang theo keyset

Với báo cáo có thể đọc theo từng đợt, keyset pagination giúp tránh một SELECT duy nhất quét và giữ cursor quá lâu:

```sql
SELECT account_id, updated_at, balance
FROM account_balance
WHERE account_id > 1000
ORDER BY account_id
LIMIT 500;
```

Trang kế tiếp dùng khóa cuối trang trước làm mốc. Mỗi trang có thể là một statement/transaction ngắn. Tuy nhiên, nếu commit giữa các trang, dữ liệu có thể thay đổi giữa các lần đọc; kết quả không còn là một snapshot thống nhất. Cần quyết định rõ báo cáo chấp nhận dữ liệu mới giữa các trang hay yêu cầu snapshot nhất quán toàn bộ.

### 13.3. Chỉ lấy cột cần thiết và dùng index

Giảm số hàng/cột đọc giúp statement kết thúc nhanh hơn, qua đó giảm thời gian giữ read view. Chọn index phù hợp, tránh đọc toàn bảng không cần thiết và xem `EXPLAIN` để hiểu access path.

### 13.4. Không dùng isolation level cao hơn nhu cầu

Nếu nghiệp vụ cho phép mỗi SELECT thấy một snapshot mới, RC có thể giảm thời gian giữ snapshot xuyên nhiều statement so với RR. Nhưng RC không làm statement dài biến mất và có thể thay đổi kết quả khi cùng transaction đọc nhiều lần.

### 13.5. Đặt giới hạn vận hành

Theo dõi transaction age, history list length và query latency. Có thể đặt timeout ở tầng ứng dụng hoặc cơ chế kiểm soát transaction để phát hiện session idle trong transaction. Chọn ngưỡng dựa trên workload; không cắt mọi transaction chỉ vì tuổi vượt một con số chung.

## 14. Quy trình điều tra history list tăng

Khi history list length tăng kéo dài, thực hiện theo thứ tự:

1. Ghi lại history list length và thời điểm; kiểm tra xu hướng qua nhiều mẫu.
2. Liệt kê transaction trong `INFORMATION_SCHEMA.INNODB_TRX`, sắp xếp theo `trx_started`.
3. Xác định transaction idle (`trx_query IS NULL`), transaction read-only và isolation level.
4. Đối chiếu connection ID với `SHOW FULL PROCESSLIST` để tìm ứng dụng, host và trạng thái.
5. Xác định transaction nào đã thực hiện consistent read và có thể đang giữ read view lâu.
6. Kiểm tra tốc độ update/delete và tải I/O/CPU để xem purge có đang không theo kịp workload ngay cả khi không có snapshot cũ.
7. Kiểm tra metadata lock nếu DDL hoặc truy vấn mới đang chờ.
8. Trao đổi với chủ sở hữu ứng dụng để kết thúc transaction đúng cách hoặc lên lịch xử lý.
9. Sau khi transaction kết thúc, theo dõi purge bắt kịp và history list giảm dần.
10. Điều chỉnh code hoặc vận hành để không tái diễn; chỉ tinh chỉnh purge sau khi xác định nguyên nhân.

Không kết thúc connection tùy tiện chỉ dựa trên tuổi transaction. Một transaction có thể là báo cáo đang chạy hợp lệ hoặc công việc vận hành quan trọng.

### 14.1. KILL QUERY và KILL CONNECTION

`KILL QUERY <id>` dừng statement đang chạy của connection nhưng không nhất thiết kết thúc transaction. Nếu session đang idle trong transaction, không có statement nào để dừng và transaction vẫn có thể giữ read view.

`KILL CONNECTION <id>` ngắt connection; transaction chưa commit của connection đó sẽ được rollback. Rollback có thể mất thời gian nếu transaction đã sửa nhiều dữ liệu. Chỉ DBA/người có thẩm quyền nên thực hiện sau khi xác nhận chủ sở hữu, tác động nghiệp vụ và kế hoạch phục hồi.

Sau khi kết thúc transaction, purge vẫn cần thời gian để xử lý backlog; không kỳ vọng KILL làm history list về 0 tức thì.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Transaction read-only không ảnh hưởng purge | Read-only consistent read vẫn có thể giữ read view và undo history |
| COMMIT của transaction ghi xóa mọi undo ngay | Update undo có thể còn cần cho read view cũ |
| History list length là số hàng cũ | Đây là chỉ số undo history/page, không phải số row version hoặc byte chính xác |
| `trx_started` lâu luôn có nghĩa read view cũ | Cần xác định transaction đã thực hiện consistent read hay chưa và isolation level |
| Transaction idle không giữ tài nguyên | Transaction idle sau consistent read có thể vẫn giữ snapshot và metadata lock |
| READ COMMITTED loại bỏ mọi purge lag | Statement RC chạy lâu vẫn giữ read view; workload ghi cũng có thể vượt tốc độ purge |
| KILL QUERY kết thúc transaction | Nó dừng statement, không đảm bảo đóng transaction/connection |
| Purge giảm backlog thì file undo lập tức nhỏ lại | Trang có thể được tái sử dụng; truncate tablespace là cơ chế riêng |
| Long read luôn khóa writer | Consistent read thường không khóa hàng theo cách locking read, nhưng có thể giữ undo history và metadata lock |

## 16. Bài thực hành

Thực hiện trong MySQL lab có ít nhất hai session và bảng InnoDB:

1. Tạo bảng số dư và nạp một hàng mẫu.
2. Mở Session A ở RR, chạy SELECT đầu tiên rồi để transaction mở.
3. Dùng Session B cập nhật cùng hàng và commit nhiều lần.
4. Chạy lại SELECT ở Session A; giải thích vì sao vẫn thấy phiên bản cũ.
5. Commit Session A rồi theo dõi `SHOW ENGINE INNODB STATUS` qua nhiều lần để quan sát purge xử lý history.
6. Lặp lại thí nghiệm với RC và xác nhận statement đọc thứ hai thấy commit mới.
7. Mở một transaction read-only, thực hiện consistent read rồi để session idle; tìm nó trong `INNODB_TRX` và process list.
8. So sánh `trx_started`, `trx_query`, `trx_is_read_only` và `trx_isolation_level`; giải thích vì sao `trx_query` có thể NULL.
9. Tạo workload update/delete trong lab trong khi giữ read view cũ; quan sát xu hướng history list length. Dừng workload trước khi tạo tải quá mức.
10. Chạy một SELECT autocommit dài và so sánh thời gian giữ snapshot với transaction nhiều statement.
11. Mở transaction đọc bảng rồi thử DDL từ session khác; quan sát metadata lock wait trong môi trường lab.
12. Dùng keyset pagination để chia truy vấn lớn; giải thích đánh đổi về tính nhất quán khi commit giữa các trang.
13. Phân biệt hành vi của `KILL QUERY` và `KILL CONNECTION` trên transaction lab; xác nhận transaction có kết thúc hay không.
14. Viết checklist điều tra history list tăng, gồm transaction age, read view, purge throughput, undo tablespace và metadata lock.

Bạn hoàn thành bài khi giải thích được vì sao một transaction đọc idle có thể giữ undo history, đọc được dấu hiệu purge backlog và chọn được cách giảm thời gian snapshot mà vẫn giữ đúng yêu cầu nhất quán của báo cáo.

## 17. Nguyên tắc cần ghi nhớ

- InnoDB giữ undo để rollback và để consistent read dựng lại phiên bản hàng cũ.
- Read view quyết định transaction nhìn thấy phiên bản nào; nó không phải bản sao vật lý của database.
- Trong RR, consistent read đầu tiên tạo snapshot dùng lại cho các consistent read tiếp theo trong transaction; `WITH CONSISTENT SNAPSHOT` có thể tạo snapshot ngay khi bắt đầu.
- Trong RC, mỗi consistent read statement tạo read view mới; statement dài vẫn giữ snapshot trong lúc chạy.
- Transaction chỉ đọc vẫn có thể giữ read view và ngăn purge dọn phiên bản cũ.
- Transaction idle sau SELECT có thể tiếp tục giữ snapshot nếu chưa commit/rollback.
- Purge dọn undo history và delete-marked record khi không còn read view cần chúng; purge chạy nền, không đồng bộ ngay với COMMIT.
- History list length là chỉ số backlog undo history, không phải số hàng hay số byte chính xác.
- Dùng `INFORMATION_SCHEMA.INNODB_TRX`, `SHOW FULL PROCESSLIST` và `SHOW ENGINE INNODB STATUS` để điều tra.
- Transaction dài có thể làm consistent read tốn công dựng phiên bản cũ và làm undo tablespace cần thêm dung lượng.
- Transaction truy cập bảng có thể giữ metadata lock tới cuối transaction, khiến DDL phải chờ.
- `KILL QUERY` dừng statement; `KILL CONNECTION` kết thúc connection và rollback transaction chưa commit.
- Purge bắt kịp không đồng nghĩa file undo tablespace lập tức thu nhỏ.
- Giữ transaction ngắn, không chờ dịch vụ ngoài trong transaction và chỉ đổi isolation level khi semantics nghiệp vụ cho phép.
