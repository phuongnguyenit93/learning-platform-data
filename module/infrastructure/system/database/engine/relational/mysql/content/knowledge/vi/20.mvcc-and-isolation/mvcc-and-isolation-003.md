# Consistent read so với locking/current read

InnoDB có hai cách đọc dữ liệu quan trọng trong transaction: **consistent read** (đọc nhất quán, thường là `SELECT` thông thường) và **locking read/current read** (đọc có khóa, như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE`). Hai cách đọc có thể trả về phiên bản dữ liệu khác nhau ngay trong cùng một transaction, đặc biệt ở mức cô lập `REPEATABLE READ`.

Consistent read dùng MVCC để đọc một snapshot mà không khóa các hàng dữ liệu được đọc. Locking read đọc phiên bản hiện hành mà InnoDB có thể sử dụng và đặt khóa trên các bản ghi/phạm vi phù hợp để điều phối transaction cạnh tranh. Chọn sai loại đọc có thể gây race condition, đọc dữ liệu cũ khi cần quyết định cập nhật, hoặc giữ khóa lâu hơn cần thiết.

Bài học này tập trung vào InnoDB trên MySQL 8.0 trở lên: cách snapshot được tạo, khác biệt giữa `REPEATABLE READ` và `READ COMMITTED`, ngữ nghĩa `FOR UPDATE`/`FOR SHARE`, phạm vi khóa, `NOWAIT`/`SKIP LOCKED` và cách chọn chiến lược đọc cho từng đơn vị nghiệp vụ.

## 1. Hai cách đọc phục vụ hai mục tiêu khác nhau

| Loại đọc | Cú pháp tiêu biểu | Phiên bản dữ liệu | Khóa hàng |
| --- | --- | --- | --- |
| Consistent read | `SELECT ...` thông thường | Snapshot theo isolation level | Không đặt khóa record/gap để bảo vệ hàng được đọc |
| Locking read | `SELECT ... FOR UPDATE` | Phiên bản hiện hành mà locking read có thể đọc | Đặt khóa phù hợp với chế độ đọc và access path |
| Locking read chia sẻ | `SELECT ... FOR SHARE` | Phiên bản hiện hành mà locking read có thể đọc | Đặt shared lock trên hàng/phạm vi được đọc |
| DML ghi dữ liệu | `UPDATE`, `DELETE` | Kiểm tra và thao tác trên phiên bản hiện hành | Lấy khóa cần thiết để thay đổi dữ liệu |

Một `SELECT` thông thường thường phù hợp cho báo cáo, hiển thị hoặc đọc dữ liệu theo snapshot. `SELECT ... FOR UPDATE` phù hợp khi transaction cần đọc một hàng rồi dựa vào giá trị đó để cập nhật an toàn. `FOR SHARE` phù hợp khi cần đọc và giữ shared lock để ngăn transaction khác sửa/xóa hàng trong phần còn lại của transaction.

Không nên hiểu “consistent read không khóa” là câu lệnh hoàn toàn không dùng bất kỳ loại khóa nào. Nó không khóa record/gap như locking read để bảo vệ hàng dữ liệu; câu lệnh vẫn chịu các cơ chế khác như metadata lock và các giới hạn vận hành của server.

## 2. Consistent read và MVCC

InnoDB dùng MVCC (Multi-Version Concurrency Control) để giữ các phiên bản dữ liệu cần thiết cho những transaction đang đọc snapshot. Khi một transaction cập nhật hàng, InnoDB ghi thông tin undo để có thể dựng lại phiên bản cũ cho consistent read phù hợp.

Một `SELECT` thông thường trong transaction có thể đọc phiên bản đã commit tại thời điểm snapshot được xác định, thay vì phải chờ mọi transaction đang sửa hàng kết thúc. Nhờ vậy, nhiều truy vấn đọc có thể tiếp tục trong lúc transaction khác ghi dữ liệu.

Ví dụ, tài khoản có số dư 500.00:

1. Transaction A đọc số dư 500.00 bằng consistent read.
2. Transaction B cập nhật số dư thành 450.00 và commit.
3. Transaction A đọc lại bằng consistent read.

Ở `REPEATABLE READ`, nếu snapshot của A đã được tạo ở bước 1, lần đọc thứ hai vẫn có thể thấy 500.00. Đây là hành vi có chủ đích: A tiếp tục đọc cùng một snapshot.

MVCC không có nghĩa mọi transaction luôn thấy cùng một giá trị. Snapshot phụ thuộc isolation level và thời điểm tạo read view. Locking read và DML có ngữ nghĩa khác consistent read.

## 3. Khi nào snapshot của consistent read được tạo?

Ở mức `REPEATABLE READ` của InnoDB, các consistent read thông thường trong cùng transaction dùng cùng read view. Read view được tạo tại lần consistent read đầu tiên của transaction, chứ không nhất thiết ngay khi chạy `START TRANSACTION`.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Chưa có consistent read nào ở thời điểm START TRANSACTION.
-- Một transaction khác có thể commit trước câu SELECT này.
SELECT balance
FROM accounts
WHERE account_id = 101;

-- Các consistent read tiếp theo trong transaction dùng cùng snapshot.
SELECT balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

Nếu cần một snapshot nhất quán ngay từ đầu transaction trước khi thực hiện nhiều thao tác đọc, có thể dùng `START TRANSACTION WITH CONSISTENT SNAPSHOT` ở mức cô lập phù hợp. Lệnh này yêu cầu InnoDB tạo consistent snapshot khi bắt đầu transaction; nó không biến các locking read thành consistent read và cũng không thay thế `FOR UPDATE` khi cần khóa để cập nhật.

Trong InnoDB, tùy chọn `WITH CONSISTENT SNAPSHOT` có ý nghĩa ở mức `REPEATABLE READ`. Nếu session dùng mức cô lập khác, MySQL không tạo snapshot theo cách này; hãy đặt isolation level trước khi bắt đầu transaction nếu cần hành vi snapshot đó.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM orders;
SELECT SUM(total_amount) FROM orders;

COMMIT;
```

Hai truy vấn đọc thông thường trong transaction này dùng cùng snapshot, giúp các phép đọc báo cáo có thể nhất quán với nhau.

## 4. REPEATABLE READ và READ COMMITTED

Khác biệt quan trọng nhất với consistent read là thời điểm lấy snapshot:

| Isolation level | Snapshot của consistent read |
| --- | --- |
| `REPEATABLE READ` | Các consistent read trong cùng transaction dùng read view được tạo ở lần consistent read đầu tiên |
| `READ COMMITTED` | Mỗi consistent read thông thường lấy snapshot mới tại thời điểm câu lệnh bắt đầu |

Giả sử Transaction A thực hiện hai câu `SELECT` và giữa hai câu, Transaction B cập nhật rồi commit:

- Ở `REPEATABLE READ`, A có thể thấy cùng giá trị cũ ở cả hai lần đọc.
- Ở `READ COMMITTED`, câu `SELECT` thứ hai của A có thể thấy giá trị mới đã commit bởi B.

Kiểm tra và thay đổi mức cô lập trong session:

```sql
SELECT @@SESSION.transaction_isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Thay đổi session ảnh hưởng các transaction tiếp theo trên connection đó. Với connection pool, cần bảo đảm từng connection được khởi tạo với isolation level mong muốn.

`READ COMMITTED` không cho phép consistent read nhìn thấy dữ liệu chưa commit. Nó chỉ làm mới snapshot ở mỗi câu đọc, nên một transaction có thể quan sát các commit mới giữa các câu lệnh.

## 5. Locking read: đọc phiên bản hiện hành và đặt khóa

Locking read được dùng khi transaction cần bảo vệ dữ liệu mà nó vừa đọc khỏi thay đổi xung đột trước khi hoàn tất công việc.

Hai cú pháp chính trong MySQL 8.0:

```sql
SELECT ... FOR UPDATE;
SELECT ... FOR SHARE;
```

- `FOR UPDATE` lấy exclusive lock trên các bản ghi/phạm vi phù hợp. Transaction khác không thể lấy khóa xung đột để cập nhật hoặc locking-read cùng dữ liệu cho đến khi khóa được giải phóng.
- `FOR SHARE` lấy shared lock. Nhiều transaction có thể cùng giữ shared lock tương thích, nhưng transaction khác không thể sửa/xóa hàng bằng exclusive lock cho đến khi shared lock được giải phóng.

Locking read đọc phiên bản hiện hành mà InnoDB có thể sử dụng, thay vì quay lại snapshot cũ của consistent read. Nếu một transaction khác đang giữ khóa xung đột, câu lệnh có thể phải chờ, trả lỗi với `NOWAIT`, hoặc bỏ qua hàng đang bị khóa với `SKIP LOCKED`.

Các khóa được giữ đến `COMMIT` hoặc `ROLLBACK` của transaction. Vì vậy, locking read chỉ có ý nghĩa bảo vệ các thao tác tiếp theo nếu chúng nằm trong cùng transaction và cùng connection.

## 6. FOR UPDATE: đọc để chuẩn bị cập nhật

Ví dụ kiểm tra tồn kho trước khi trừ số lượng:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 501
FOR UPDATE;

-- Ứng dụng kiểm tra quantity đủ lớn và số lượng đặt mua hợp lệ.

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501
  AND quantity >= 2;

-- Ứng dụng kiểm tra affected rows = 1; nếu không thì ROLLBACK.

COMMIT;
```

`FOR UPDATE` bảo vệ hàng tồn kho trong lúc ứng dụng kiểm tra và cập nhật. Một transaction khác muốn cập nhật cùng hàng phải chờ hoặc nhận lỗi theo cách xử lý lock wait. Nếu hàng không tồn tại, locking read không trả hàng; phạm vi gap lock có thể phụ thuộc isolation level, index và điều kiện tìm kiếm.

Nếu logic chỉ cần trừ kho và không cần đọc số lượng về ứng dụng, một câu lệnh cập nhật có điều kiện thường ngắn gọn hơn:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501
  AND quantity >= 2;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu bằng 1, thao tác trừ kho thành công; nếu bằng 0, sản phẩm không tồn tại hoặc không đủ số lượng theo điều kiện. Trong hệ thống thật, có thể cần truy vấn bổ sung để phân biệt hai nguyên nhân. Cập nhật có điều kiện giúp phép kiểm tra và thay đổi diễn ra nguyên tử trong một statement.

## 7. FOR SHARE: đọc và ngăn sửa/xóa trong thời gian transaction

`FOR SHARE` lấy shared lock để bảo đảm hàng được đọc không bị transaction khác sửa hoặc xóa trước khi transaction hiện tại hoàn tất.

Ví dụ, kiểm tra trạng thái cấu hình hoặc hạn mức trước khi ghi một nghiệp vụ liên quan:

```sql
START TRANSACTION;

SELECT account_id, account_status, daily_limit
FROM accounts
WHERE account_id = 101
FOR SHARE;

-- Ứng dụng kiểm tra trạng thái và hạn mức.
-- Các transaction khác không thể sửa/xóa hàng này khi shared lock còn giữ.

INSERT INTO account_audit (account_id, action_name)
VALUES (101, 'CHECKED_FOR_OPERATION');

COMMIT;
```

`FOR SHARE` không có nghĩa các transaction khác không thể đọc hàng; shared lock tương thích với shared lock khác. Nó ngăn thao tác cần exclusive lock như cập nhật/xóa cho đến khi transaction hiện tại kết thúc.

Nếu transaction sau đó cần sửa chính hàng vừa đọc, dùng `FOR UPDATE` ngay từ đầu thường rõ ràng hơn. Nhiều transaction cùng lấy shared lock rồi cùng nâng cấp lên exclusive lock có thể tạo deadlock.

## 8. Vì sao consistent read và current read có thể thấy giá trị khác nhau?

Ở `REPEATABLE READ`, một transaction có thể vừa thấy phiên bản snapshot cũ qua `SELECT` thông thường, vừa thấy phiên bản hiện hành qua `SELECT ... FOR UPDATE`:

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Tạo snapshot và đọc số dư 500.00
SELECT balance
FROM accounts
WHERE account_id = 101;

-- Sau khi Session B commit, câu này vẫn có thể thấy 500.00
SELECT balance
FROM accounts
WHERE account_id = 101;

-- Locking/current read đọc phiên bản hiện hành, ví dụ 450.00
SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

COMMIT;
```

**Session B, chạy giữa hai lần đọc của A:**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = 450.00
WHERE account_id = 101;

COMMIT;
```

Kết quả khác nhau không phải lỗi dữ liệu. Hai câu lệnh dùng hai ngữ nghĩa đọc khác nhau: câu `SELECT` thường dùng snapshot của A; `FOR UPDATE` đọc phiên bản hiện hành và khóa hàng để A có thể quyết định thao tác tiếp theo.

Khi một transaction đã tự thay đổi một hàng, consistent read của chính transaction đó vẫn thấy các thay đổi của nó (read-your-own-writes), kết hợp với các phiên bản phù hợp trong snapshot cho các hàng khác. Vì vậy, không nên mô hình hóa consistent read đơn giản là “luôn trả dữ liệu cũ”; nó là một view nhất quán theo quy tắc MVCC và có tính đến thay đổi của chính transaction.

## 9. UPDATE và DELETE cũng là current read

Các câu lệnh `UPDATE` và `DELETE` cần tìm hàng hiện hành để thay đổi hoặc xóa, vì vậy chúng sử dụng cơ chế khóa và đọc phiên bản hiện hành phù hợp với thao tác ghi. Không nên giả định chúng bị giới hạn bởi snapshot của consistent `SELECT` trước đó.

Ví dụ:

```sql
START TRANSACTION;

-- Consistent read có thể thấy số lượng từ snapshot.
SELECT quantity
FROM inventory
WHERE product_id = 501;

-- UPDATE tìm và khóa hàng hiện hành để ghi.
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501
  AND quantity > 0;

COMMIT;
```

Nếu ứng dụng lấy giá trị từ câu SELECT rồi tự tính số mới trong bộ nhớ và ghi đè mà không có điều kiện/khóa phù hợp, nó có thể ghi dựa trên dữ liệu cũ. Ưu tiên phép cập nhật nguyên tử như `quantity = quantity - 1` kèm điều kiện, hoặc dùng `FOR UPDATE` khi cần đọc nhiều trường rồi mới quyết định.

## 10. Locking read chỉ bảo vệ trong transaction

Để khóa còn tồn tại qua nhiều câu lệnh, cần transaction tường minh:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 501
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501;

COMMIT;
```

Nếu `autocommit = 1` và câu `SELECT ... FOR UPDATE` chạy như một statement độc lập ngoài transaction tường minh, transaction của statement kết thúc ngay sau câu lệnh; khóa không được giữ để bảo vệ một câu `UPDATE` chạy sau đó.

Kiểm tra:

```sql
SELECT @@SESSION.autocommit;
```

Không tắt autocommit toàn cục chỉ để dùng locking read. Thông thường, bắt đầu transaction tường minh cho đơn vị nghiệp vụ là cách dễ kiểm soát hơn.

## 11. Phạm vi khóa phụ thuộc index và access path

InnoDB thường khóa các index record mà câu locking read hoặc DML quét qua, cùng các gap cần thiết theo isolation level và điều kiện. Vì vậy, phạm vi khóa không nhất thiết chỉ gồm những hàng cuối cùng được trả về.

Ví dụ truy vấn theo primary key duy nhất:

```sql
SELECT *
FROM inventory
WHERE product_id = 501
FOR UPDATE;
```

Nếu `product_id` là unique index và tìm thấy đúng một hàng, InnoDB thường chỉ cần record lock cho hàng đó, không cần khóa gap liền kề như một range scan.

Ngược lại, truy vấn phạm vi:

```sql
SELECT *
FROM inventory
WHERE product_id BETWEEN 500 AND 520
FOR UPDATE;
```

Ở `REPEATABLE READ`, InnoDB có thể dùng next-key locks (record lock kết hợp gap lock) trên các index record được quét để ngăn transaction khác chèn hàng vào phạm vi phù hợp. Ở `READ COMMITTED`, gap locking thường được tắt cho tìm kiếm và quét index thông thường, ngoại trừ các trường hợp như kiểm tra foreign key và duplicate key.

Nếu thiếu index phù hợp, MySQL có thể phải quét nhiều record hơn, làm tăng số khóa và khả năng xung đột. Index tốt không chỉ giúp truy vấn nhanh mà còn giúp giới hạn phạm vi cần khóa. Hãy kiểm tra `EXPLAIN` và index được dùng khi điều tra lock wait.

## 12. NOWAIT và SKIP LOCKED

MySQL 8.0 hỗ trợ tùy chọn `NOWAIT` và `SKIP LOCKED` cho locking reads:

- `NOWAIT`: nếu hàng cần khóa đang bị transaction khác giữ khóa xung đột, câu lệnh trả lỗi ngay thay vì chờ.
- `SKIP LOCKED`: bỏ qua các hàng đang bị khóa xung đột và trả về những hàng khác có thể khóa.

Ví dụ dùng `NOWAIT`:

```sql
START TRANSACTION;

SELECT *
FROM inventory
WHERE product_id = 501
FOR UPDATE NOWAIT;

COMMIT;
```

Nếu hàng đang bị khóa bởi transaction khác, câu lệnh thất bại ngay. Ứng dụng có thể trả thông báo bận hoặc thử lại theo chính sách phù hợp.

Ví dụ dùng `SKIP LOCKED` cho hàng đợi công việc:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE status = 'ready'
ORDER BY priority DESC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Nếu chọn được job, cập nhật trạng thái ngay trong transaction.
UPDATE job_queue
SET status = 'running'
WHERE job_id = ?;

COMMIT;
```

Nhiều worker có thể lấy các job khác nhau mà không phải chờ job đang bị worker khác khóa. Trong ứng dụng thực tế, cần kiểm tra số hàng được chọn, cập nhật trạng thái bằng điều kiện phù hợp và có cơ chế phục hồi job bị bỏ dở nếu worker chết sau commit.

`SKIP LOCKED` tạo một view không nhất quán của dữ liệu vì các hàng đang khóa bị bỏ qua. Nó phù hợp cho queue hoặc workload phân phối công việc, không phù hợp cho truy vấn nghiệp vụ cần nhìn thấy toàn bộ tập hàng như báo cáo số dư hoặc tồn kho.

## 13. Locking clause trong subquery và join

Đặt locking clause ở query block nào thì khóa áp dụng theo phạm vi của query block đó. Một locking clause ở truy vấn ngoài không tự động khóa hàng được đọc bên trong một subquery độc lập.

Ví dụ:

```sql
-- Khóa hàng của t1; subquery đọc t2 không tự động bị khóa bởi clause ngoài.
SELECT *
FROM t1
WHERE c1 = (SELECT c1 FROM t2)
FOR UPDATE;
```

Nếu cần khóa hàng được đọc trong subquery, phải đặt locking clause trong subquery tương ứng:

```sql
SELECT *
FROM t1
WHERE c1 = (
    SELECT c1
    FROM t2
    WHERE id = 10
    FOR UPDATE
)
FOR UPDATE;
```

Khi dùng join, locking clause có thể khóa các hàng được đọc từ các bảng liên quan theo phạm vi và quy tắc của MySQL. Cần kiểm tra chính xác bảng nào cần khóa, access path và kế hoạch thực thi; tránh khóa rộng hơn yêu cầu.

## 14. FOR SHARE và nguy cơ deadlock khi nâng cấp khóa

Hai transaction có thể cùng đọc một hàng bằng `FOR SHARE` vì shared lock tương thích. Nhưng nếu cả hai sau đó cùng muốn cập nhật hàng đó, mỗi transaction cần exclusive lock. Cả hai có thể chờ khóa của transaction còn lại và tạo deadlock.

Mô phỏng tình huống:

1. Session A chạy `SELECT ... FOR SHARE` trên hàng X.
2. Session B cũng chạy `SELECT ... FOR SHARE` trên hàng X.
3. Session A muốn `UPDATE` hàng X và cần exclusive lock.
4. Session B cũng muốn `UPDATE` hàng X.
5. Hai transaction có thể rơi vào tình trạng chờ nâng cấp khóa.

Nếu biết ngay từ đầu transaction sẽ đọc rồi cập nhật cùng hàng, dùng `FOR UPDATE` thường phù hợp hơn. Nếu chỉ cần bảo đảm hàng không thay đổi trong lúc kiểm tra, `FOR SHARE` có thể phù hợp. Dù chọn loại nào, ứng dụng vẫn phải xử lý deadlock.

## 15. Consistent read không phải locking read: chọn theo mục tiêu

| Mục tiêu | Nên bắt đầu với | Vì sao |
| --- | --- | --- |
| Hiển thị danh sách hoặc trang chi tiết theo snapshot | `SELECT` thông thường | Không cần giữ khóa hàng chỉ để đọc |
| Tạo báo cáo cần nhiều truy vấn cùng snapshot ở RR | Consistent read trong một transaction | Các truy vấn đọc dùng cùng read view |
| Đọc số dư rồi quyết định trừ tiền | `SELECT ... FOR UPDATE` hoặc UPDATE có điều kiện | Cần tránh quyết định dựa trên hàng đã bị thay đổi đồng thời |
| Đọc cấu hình và bảo đảm không bị sửa trong transaction | `SELECT ... FOR SHARE` | Shared lock ngăn cập nhật/xóa xung đột |
| Nhiều worker nhận job khác nhau | `FOR UPDATE SKIP LOCKED` | Bỏ qua job worker khác đang khóa |
| Muốn thất bại ngay nếu tài nguyên đang bận | `FOR UPDATE NOWAIT` | Không chờ lock wait |
| Chỉ cần cập nhật theo điều kiện đơn giản | Một câu `UPDATE ... WHERE ...` | Kiểm tra và thay đổi trong cùng statement |

Đừng dùng `FOR UPDATE` cho mọi câu SELECT. Khóa không cần thiết làm giảm khả năng đồng thời, tăng lock wait và nguy cơ deadlock. Ngược lại, đừng dùng consistent read khi logic read-modify-write cần bảo vệ dữ liệu trước transaction cạnh tranh.

## 16. Thí nghiệm hai session: snapshot và current read

Tạo bảng thử nghiệm:

```sql
CREATE TABLE mvcc_demo_accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO mvcc_demo_accounts (account_id, balance)
VALUES (1, 500.00);
```

Chọn `REPEATABLE READ` ở cả hai session.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Kết quả: 500.00; snapshot được tạo.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 450.00
WHERE account_id = 1;

COMMIT;
```

**Quay lại Session A:**

```sql
-- Consistent read vẫn thấy snapshot cũ.
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Kết quả: 500.00

-- Current/locking read thấy phiên bản hiện hành và khóa hàng.
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;
-- Kết quả: 450.00

COMMIT;
```

Thí nghiệm cho thấy hai loại đọc có thể trả về hai phiên bản khác nhau trong cùng transaction. Sau khi A commit, một transaction mới sẽ đọc giá trị đã commit là 450.00.

## 17. Thí nghiệm READ COMMITTED

Lặp lại thí nghiệm trên nhưng đặt Session A ở `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
```

Sau khi Session B cập nhật và commit, chạy lại câu `SELECT` thông thường trong A. Lần đọc thứ hai có thể thấy giá trị mới vì `READ COMMITTED` tạo snapshot mới cho mỗi consistent read.

`FOR UPDATE` vẫn là locking read/current read; thay đổi isolation level không biến nó thành consistent snapshot read. Isolation level ảnh hưởng cách InnoDB xử lý snapshot và khóa phạm vi, nhưng mục tiêu của locking read vẫn là đọc và bảo vệ phiên bản hiện hành.

## 18. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `SELECT` thông thường luôn đọc giá trị mới nhất | Ở RR, nó có thể đọc snapshot cũ | Dùng current/locking read nếu cần giá trị hiện hành để cập nhật |
| Consistent read khóa hàng để ngăn thay đổi | Nó dùng MVCC snapshot và không khóa record/gap như locking read | Không dùng SELECT thường để bảo vệ read-modify-write |
| `FOR UPDATE` chỉ thay đổi cách trả kết quả | Nó lấy khóa và có thể làm transaction khác chờ | Dùng đúng phạm vi, commit/rollback sớm |
| `FOR SHARE` ngăn mọi transaction đọc hàng | Shared lock tương thích với shared lock khác | Hiểu shared/exclusive lock và nguy cơ nâng cấp |
| Snapshot RR được tạo ngay tại START TRANSACTION | Thông thường được tạo ở consistent read đầu tiên | Dùng `WITH CONSISTENT SNAPSHOT` nếu cần tạo snapshot ngay |
| READ COMMITTED cho phép dirty read | Nó vẫn không đọc dữ liệu chưa commit | Phân biệt fresh snapshot với dirty read |
| FOR UPDATE khóa chỉ đúng hàng trả về | Index record/gap được quét có thể nằm trong phạm vi khóa | Kiểm tra index và EXPLAIN |
| FOR UPDATE có tác dụng qua nhiều câu lệnh khi autocommit bật | Statement độc lập kết thúc transaction và nhả khóa | Dùng transaction tường minh trên cùng connection |
| Locking clause ngoài khóa cả subquery | Query block con cần locking clause riêng nếu cần khóa hàng ở đó | Đặt clause đúng query block |
| SKIP LOCKED là cách đọc dữ liệu tổng quát | Nó bỏ qua hàng đang khóa và tạo view không nhất quán | Chỉ dùng cho queue/work distribution phù hợp |

## 19. Quy trình chọn consistent read hay locking read

Trước khi viết truy vấn, hãy xác định:

1. Chỉ cần đọc để hiển thị/báo cáo hay sẽ dùng kết quả để cập nhật?
2. Có cần mọi truy vấn đọc trong transaction nhìn cùng snapshot không?
3. Có cần đọc phiên bản hiện hành sau khi transaction khác commit không?
4. Có cần ngăn transaction khác sửa/xóa hàng trước khi mình hoàn tất không?
5. `FOR UPDATE` hay `FOR SHARE` phù hợp với ý định khóa?
6. Có thể thay read-modify-write bằng một câu DML có điều kiện không?
7. Index có giới hạn phạm vi record/gap bị khóa không?
8. Transaction có bắt đầu và kết thúc trên cùng connection không?
9. Có cần `NOWAIT` hoặc `SKIP LOCKED`, và ứng dụng đã xử lý lỗi/thiếu hàng chưa?
10. Có xử lý deadlock, lock wait timeout và rollback trước khi trả connection về pool không?

## 20. Bài tập thực hành

1. Tạo bảng `mvcc_demo_accounts` dùng InnoDB và thêm một tài khoản có số dư 500.00.
2. Mở hai session; ở Session A dùng `REPEATABLE READ` và chạy consistent SELECT để tạo snapshot.
3. Ở Session B cập nhật số dư rồi commit; chạy lại SELECT thường ở A và ghi nhận giá trị.
4. Ở A chạy `SELECT ... FOR UPDATE`; so sánh giá trị current read với consistent read.
5. Lặp lại với `READ COMMITTED`; quan sát mỗi consistent read có snapshot mới.
6. Thử `SELECT ... FOR SHARE` ở hai session, sau đó thử cập nhật cùng hàng để quan sát chờ khóa/nâng cấp khóa.
7. So sánh một truy vấn equality trên unique key với truy vấn range dưới `REPEATABLE READ`; xem tác động của record/gap/next-key locks.
8. Chạy locking read với `NOWAIT` khi session khác đang giữ khóa; ghi nhận lỗi ứng dụng cần xử lý.
9. Tạo bảng `job_queue` và dùng `FOR UPDATE SKIP LOCKED` từ hai worker để nhận hai job khác nhau.
10. Dùng `EXPLAIN` để kiểm tra index và access path của truy vấn locking; đánh giá phạm vi khóa có thể bị ảnh hưởng.

## 21. Ghi nhớ

Consistent read của InnoDB dùng MVCC để đọc snapshot và không đặt record/gap lock nhằm bảo vệ các hàng được đọc. Ở `REPEATABLE READ`, các consistent read trong cùng transaction thường dùng read view được tạo tại lần đọc nhất quán đầu tiên; ở `READ COMMITTED`, mỗi consistent read có snapshot mới. `START TRANSACTION WITH CONSISTENT SNAPSHOT` có thể tạo snapshot ngay khi bắt đầu transaction ở mức hỗ trợ.

`SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là locking/current reads: chúng đọc phiên bản hiện hành mà InnoDB có thể sử dụng và đặt exclusive/shared lock phù hợp. Khóa được giữ đến commit/rollback và chỉ bảo vệ các thao tác tiếp theo khi cùng transaction, cùng connection. `UPDATE`/`DELETE` cũng thao tác trên phiên bản hiện hành. Phạm vi khóa phụ thuộc index, access path và isolation level; range scan ở RR có thể dùng next-key/gap locks. `NOWAIT` và `SKIP LOCKED` hữu ích cho tình huống cạnh tranh cụ thể, nhưng `SKIP LOCKED` không phù hợp với truy vấn cần một view đầy đủ, nhất quán. Hãy chọn loại đọc theo mục tiêu nghiệp vụ, giữ transaction ngắn và kiểm tra kế hoạch/index khi cần điều tra lock wait.
