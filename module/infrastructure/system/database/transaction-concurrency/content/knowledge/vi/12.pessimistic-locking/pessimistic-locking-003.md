# SELECT FOR UPDATE và các biến thể cần đối chiếu theo hệ quản trị

Khi một giao dịch cần đọc dữ liệu rồi quyết định cập nhật dữ liệu đó, chỉ đọc một snapshot nhất quán có thể chưa đủ. Một giao dịch khác có thể thay đổi hàng sau khi ta đọc nhưng trước khi ta ghi. `SELECT ... FOR UPDATE` giải quyết tình huống phổ biến này bằng cách đọc hàng và yêu cầu khóa ghi trên những hàng được chọn, để giao dịch khác phải chờ khi muốn cập nhật hoặc khóa xung đột với chúng.

Tuy nhiên, `SELECT FOR UPDATE` không phải cú pháp SQL có hành vi giống hệt trên mọi hệ quản trị. PostgreSQL, MySQL/InnoDB và Oracle hỗ trợ các dạng locking read với cú pháp riêng. SQL Server dùng table hints trong câu `SELECT`, còn SQLite không cung cấp khóa hàng qua `SELECT FOR UPDATE`. Phạm vi khóa, cách chờ, khả năng bỏ qua hàng đang bị khóa và cách xử lý hàng chưa tồn tại cũng khác nhau.

Bài học này tập trung vào cách dùng khóa chủ động trong transaction và những điểm phải kiểm tra khi chuyển câu lệnh giữa các hệ quản trị.

## 1. `SELECT FOR UPDATE` giải quyết vấn đề gì?

Giả sử một tài khoản có số dư 100. Hai yêu cầu đồng thời muốn rút tiền. Nếu cả hai giao dịch cùng đọc số dư 100 mà không khóa hàng, cả hai có thể cùng quyết định rằng số dư đủ, rồi ghi các kết quả dựa trên cùng một giá trị cũ.

Một lịch thực thi có vấn đề:

```text
T1: đọc balance = 100
T2: đọc balance = 100
T1: tính số dư sau khi rút 80 = 20
T2: tính số dư sau khi rút 70 = 30
T1: ghi balance = 20, COMMIT
T2: ghi balance = 30, COMMIT
```

Kết quả cuối cùng là 30, trong khi hai lần rút tổng cộng 150. Một phần cập nhật đã bị ghi đè. Đây là dạng lost update do quy trình đọc rồi ghi không được đồng bộ hóa.

Với locking read, T1 khóa hàng tài khoản trước khi kiểm tra số dư. T2 phải chờ lấy khóa xung đột. Sau khi T1 commit, T2 mới tiếp tục và kiểm tra dữ liệu theo hành vi đọc hiện hành của hệ quản trị. T2 sẽ thấy số dư mới hoặc nhận lỗi xung đột/serialization tùy isolation level và sản phẩm.

Ví dụ SQL mang tính khái quát:

```sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra balance rồi thực hiện UPDATE nếu đủ tiền.
UPDATE account
SET balance = balance - 80
WHERE account_id = 42;

COMMIT;
```

Điểm quan trọng là câu `SELECT ... FOR UPDATE` và câu `UPDATE` phải nằm trong cùng transaction. Nếu transaction kết thúc ngay sau câu SELECT, khóa sẽ được giải phóng trước khi phần cập nhật diễn ra và mục đích đồng bộ hóa không còn được bảo đảm.

## 2. Khóa nào được lấy và giữ trong bao lâu?

Trong mô hình khóa hàng, `FOR UPDATE` yêu cầu khóa loại trừ trên các hàng được chọn. Tên và cách cài đặt khóa nội bộ khác nhau, nhưng ý nghĩa chung là giao dịch khác không thể đồng thời lấy một khóa xung đột để cập nhật cùng hàng.

Thông thường:

1. Transaction bắt đầu.
2. Câu locking read tìm các hàng thỏa điều kiện và yêu cầu khóa.
3. Nếu hàng đang bị transaction khác giữ khóa xung đột, câu lệnh chờ hoặc trả lỗi tùy tùy chọn.
4. Transaction đọc giá trị, kiểm tra quy tắc nghiệp vụ và thực hiện thay đổi.
5. `COMMIT` hoặc `ROLLBACK` kết thúc transaction và giải phóng các khóa tương ứng.

Một giao dịch khác vẫn có thể đọc hàng bằng một cơ chế đọc không khóa, tùy isolation level và MVCC. `FOR UPDATE` chủ yếu điều phối những thao tác cần khóa xung đột; không nên hiểu rằng mọi câu SELECT khác đều phải chờ.

Khóa thường tồn tại đến cuối transaction, nhưng chi tiết về savepoint, cursor, autocommit và isolation level có thể khác nhau. Đặc biệt, nếu bật autocommit và chạy câu locking read như một statement độc lập, transaction có thể kết thúc ngay sau statement, khiến khóa không còn được giữ cho bước xử lý tiếp theo. Hãy chủ động mở transaction khi cần giữ khóa qua nhiều câu lệnh.

## 3. PostgreSQL

PostgreSQL hỗ trợ nhiều mức khóa hàng qua locking clause:

```sql
SELECT ...
FOR UPDATE;

SELECT ...
FOR NO KEY UPDATE;

SELECT ...
FOR SHARE;

SELECT ...
FOR KEY SHARE;
```

Các mức này có cường độ khác nhau:

- **`FOR UPDATE`:** khóa mạnh, ngăn transaction khác khóa hàng theo các chế độ xung đột, cập nhật hoặc xóa hàng đó.
- **`FOR NO KEY UPDATE`:** khóa cập nhật yếu hơn `FOR UPDATE`; phù hợp khi cập nhật không làm thay đổi khóa được tham chiếu bởi foreign key.
- **`FOR SHARE`:** cho phép các transaction khác cùng lấy khóa chia sẻ, nhưng chặn các thao tác cần khóa cập nhật xung đột.
- **`FOR KEY SHARE`:** khóa nhẹ hơn, chủ yếu bảo vệ khóa định danh khỏi bị xóa hoặc thay đổi theo cách ảnh hưởng đến tham chiếu khóa ngoại.

Có thể chỉ định bảng cần khóa trong truy vấn join bằng `OF`:

```sql
BEGIN;

SELECT o.order_id, o.status, c.customer_name
FROM orders AS o
JOIN customer AS c ON c.customer_id = o.customer_id
WHERE o.order_id = 9001
FOR UPDATE OF o;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

COMMIT;
```

`FOR UPDATE OF o` giới hạn khóa hàng vào bảng `orders` được đặt bí danh `o`. Nếu không chỉ định `OF`, locking clause có thể áp dụng lên các hàng của mọi bảng phù hợp trong truy vấn. Việc chỉ khóa bảng cần cập nhật giúp tránh chặn các thao tác không liên quan trên bảng được join.

### Không chờ hoặc bỏ qua hàng đang bị khóa

PostgreSQL hỗ trợ `NOWAIT` và `SKIP LOCKED`:

```sql
-- Trả lỗi ngay nếu hàng cần khóa đang bị transaction khác giữ.
SELECT *
FROM inventory
WHERE item_id = 12
FOR UPDATE NOWAIT;
```

```sql
-- Bỏ qua hàng đang bị khóa và lấy các hàng còn có thể khóa.
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE SKIP LOCKED;
```

- `NOWAIT` phù hợp khi ứng dụng muốn phản hồi ngay rằng tài nguyên đang bận, thay vì chờ.
- `SKIP LOCKED` hữu ích cho nhiều worker cùng lấy việc từ hàng đợi. Mỗi worker có thể lấy những hàng chưa bị worker khác khóa.

`SKIP LOCKED` cố ý tạo ra một góc nhìn không nhất quán của tập hàng vì nó bỏ qua một số hàng. Đây là hành vi phù hợp với queue hoặc tác vụ phân phối công việc, nhưng thường không phù hợp với truy vấn báo cáo hay kiểm tra điều kiện nghiệp vụ cần nhìn thấy toàn bộ dữ liệu.

PostgreSQL khóa các hàng được trả về bởi truy vấn. Locking clause không thể áp dụng trực tiếp cho một số dạng truy vấn như truy vấn có `GROUP BY`, phép tổng hợp, `DISTINCT` hoặc set operation. Nếu cần khóa hàng nguồn, hãy thiết kế truy vấn chọn các hàng cụ thể trước, hoặc dùng một hàng điều phối phù hợp.

Ở mức `SERIALIZABLE`, PostgreSQL còn dùng Serializable Snapshot Isolation (SSI) để theo dõi phụ thuộc đọc/ghi. Cơ chế này có thể phát hiện một lịch có nguy cơ không tuần tự hóa và hủy một transaction, thay vì chỉ dựa vào `FOR UPDATE`. Khóa hàng chủ động và SSI giải quyết các vấn đề liên quan nhưng không thay thế hoàn toàn cho nhau.

## 4. MySQL với InnoDB

Trong MySQL dùng InnoDB, locking read thường có dạng:

```sql
START TRANSACTION;

SELECT balance
FROM account
WHERE account_id = 42
FOR UPDATE;

UPDATE account
SET balance = balance - 80
WHERE account_id = 42;

COMMIT;
```

Đối với khóa đọc chia sẻ, MySQL 8.0 hỗ trợ cú pháp:

```sql
SELECT *
FROM product
WHERE product_id = 12
FOR SHARE;
```

`LOCK IN SHARE MODE` là cú pháp cũ vẫn gặp trong mã nguồn và tài liệu trước đây. Khi viết mã mới trên phiên bản hỗ trợ, `FOR SHARE` là dạng nên xem xét. Hãy kiểm tra phiên bản MySQL thực tế trước khi dùng các tùy chọn mới.

### `NOWAIT` và `SKIP LOCKED`

MySQL 8.0 hỗ trợ hai tùy chọn này cho locking read:

```sql
SELECT *
FROM inventory
WHERE item_id = 12
FOR UPDATE NOWAIT;
```

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

`NOWAIT` trả lỗi nếu không lấy được khóa ngay. `SKIP LOCKED` bỏ qua hàng đang bị transaction khác khóa. Cũng như PostgreSQL, mẫu `SKIP LOCKED` phù hợp với queue nhiều worker, không phù hợp để tính tổng hoặc đưa ra kết luận cần bao quát toàn bộ hàng thỏa điều kiện.

### Khóa bản ghi chỉ mục, gap lock và next-key lock

InnoDB có điểm khác biệt quan trọng: phạm vi khóa có thể rộng hơn các hàng được trả về. Locking read khóa những bản ghi chỉ mục mà quá trình thực thi truy vấn đi qua. Với một truy vấn phạm vi ở isolation level mặc định `REPEATABLE READ`, InnoDB có thể dùng **next-key lock**, kết hợp khóa bản ghi chỉ mục và khoảng trống kế tiếp. Gap lock giúp ngăn transaction khác chèn một khóa chỉ mục mới vào khoảng được bảo vệ.

Ví dụ:

```sql
START TRANSACTION;

SELECT *
FROM reservation
WHERE room_id = 7
  AND start_time >= '2026-11-15 10:00:00'
  AND start_time <  '2026-11-15 11:00:00'
FOR UPDATE;

-- Kiểm tra và tạo reservation trong cùng transaction.
COMMIT;
```

Phạm vi khóa thực tế phụ thuộc chỉ mục, điều kiện tìm kiếm, execution plan và isolation level. Một chỉ mục phù hợp giúp InnoDB giới hạn số bản ghi cần quét và khóa. Nếu truy vấn quét phạm vi lớn hoặc không dùng được chỉ mục thích hợp, nó có thể khóa nhiều bản ghi hơn dự kiến.

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho tìm kiếm và quét chỉ mục thông thường; vẫn có ngoại lệ như kiểm tra foreign key và duplicate key. Vì vậy, không thể mặc định rằng một locking read trên predicate sẽ luôn chặn mọi insert thỏa điều kiện. Hãy kiểm tra isolation level và tài liệu phiên bản đang chạy.

Một locking read trong InnoDB cũng là một **current read**: nó được dùng để đọc phiên bản hiện hành phù hợp với quy tắc khóa, khác với consistent nonlocking read đọc snapshot. Điều này có ý nghĩa khi transaction đã thực hiện một truy vấn snapshot trước đó rồi mới lấy `FOR UPDATE`.

### Phạm vi khóa trong truy vấn lồng nhau

Trong MySQL, locking clause của truy vấn ngoài không tự động khóa hàng được đọc trong một subquery. Nếu subquery cũng cần khóa, cần đặt locking clause ở đúng truy vấn con. Tương tự, khi join nhiều bảng, hãy xem rõ bảng nào được khóa và bảng nào chỉ được đọc.

## 5. Oracle Database

Oracle dùng cú pháp `SELECT ... FOR UPDATE` với các tùy chọn chờ riêng:

```sql
SELECT balance
FROM account
WHERE account_id = 42
FOR UPDATE;
```

Mặc định, câu lệnh có thể chờ khi hàng đang bị transaction khác khóa. Oracle hỗ trợ:

```sql
-- Không chờ nếu hàng đang bị khóa.
SELECT *
FROM inventory
WHERE item_id = 12
FOR UPDATE NOWAIT;
```

```sql
-- Chờ tối đa số giây được chỉ định.
SELECT *
FROM inventory
WHERE item_id = 12
FOR UPDATE WAIT 5;
```

```sql
-- Bỏ qua hàng đang bị khóa.
SELECT *
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
```

Oracle cũng hỗ trợ `FOR UPDATE OF ...` để chỉ định cột thuộc bảng mà hàng cần được khóa trong truy vấn join:

```sql
SELECT o.order_id, o.status, c.customer_name
FROM orders o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.order_id = 9001
FOR UPDATE OF o.status NOWAIT;
```

Danh sách sau `OF` xác định bảng có hàng cần khóa; nó không có nghĩa chỉ khóa riêng giá trị cột `status`. Khi làm việc với join, hãy dùng cú pháp này để làm rõ bảng mục tiêu.

Oracle có các giới hạn đối với `FOR UPDATE`. Không thể tùy ý kết hợp locking clause với các cấu trúc như `DISTINCT`, phép tổng hợp, `GROUP BY`, set operator hoặc một số view phức tạp. Nếu câu truy vấn cần tổng hợp dữ liệu, hãy tách việc tính toán khỏi việc khóa hàng nguồn hoặc khóa một hàng điều phối.

`SKIP LOCKED` thường được dùng để xây dựng queue nhiều consumer. Mỗi consumer chọn và khóa các hàng sẵn sàng, bỏ qua hàng consumer khác đang xử lý. Cần cập nhật trạng thái và commit trong cùng transaction để worker khác không lấy lại cùng công việc.

## 6. SQL Server: dùng table hints thay cho `FOR UPDATE`

SQL Server không hỗ trợ cú pháp `SELECT ... FOR UPDATE`. Cách tiếp cận tương đương thường dùng table hints trong `FROM`:

```sql
BEGIN TRANSACTION;

SELECT balance
FROM dbo.Account WITH (UPDLOCK, ROWLOCK)
WHERE account_id = 42;

UPDATE dbo.Account
SET balance = balance - 80
WHERE account_id = 42;

COMMIT TRANSACTION;
```

- **`UPDLOCK`:** yêu cầu update lock khi đọc. Update lock giúp tránh một số deadlock do nhiều transaction cùng lấy shared lock rồi cùng nâng cấp lên exclusive lock. Khóa được giữ theo phạm vi transaction.
- **`ROWLOCK`:** yêu cầu ưu tiên khóa ở mức hàng. Đây là gợi ý cho lock manager, không phải cam kết tuyệt đối rằng chỉ có row lock.
- **`HOLDLOCK`:** giữ khóa theo ngữ nghĩa `SERIALIZABLE` cho bảng được gắn hint trong phạm vi transaction. Nó có thể dẫn đến key-range lock để bảo vệ predicate nếu chỉ mục và kế hoạch truy vấn hỗ trợ.
- **`READPAST`:** bỏ qua một số hàng đang bị khóa, thường dùng cho queue; nó không bỏ qua mọi loại khóa, ví dụ page lock.
- **`NOWAIT`:** trả lỗi ngay nếu phải chờ khóa trên bảng có hint này; có thể dùng `SET LOCK_TIMEOUT 0` để thiết lập hành vi chờ ở mức session.

Ví dụ lấy việc từ queue:

```sql
BEGIN TRANSACTION;

;WITH next_job AS (
    SELECT TOP (1) job_id, status
    FROM dbo.JobQueue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE status = 'READY'
    ORDER BY created_at
)
UPDATE next_job
SET status = 'PROCESSING'
OUTPUT inserted.job_id;

COMMIT TRANSACTION;
```

Mẫu này dùng update lock để worker khác không cùng nhận hàng đã chọn, `READPAST` để bỏ qua hàng bị khóa và cập nhật trạng thái ngay trong transaction. Cú pháp và khả năng kết hợp table hints cần được kiểm tra theo phiên bản SQL Server và cấu trúc truy vấn thực tế.

Nếu cần bảo vệ điều kiện trên một phạm vi, có thể cân nhắc `HOLDLOCK` hoặc isolation level `SERIALIZABLE`. Chỉ thêm `UPDLOCK` trên các hàng hiện có không tự động bảo vệ mọi hàng chưa tồn tại. Key-range lock phụ thuộc điều kiện tìm kiếm và chỉ mục được sử dụng.

## 7. SQLite: không có khóa hàng qua `SELECT FOR UPDATE`

SQLite không hỗ trợ cú pháp `SELECT ... FOR UPDATE` và không cung cấp row-level locking như PostgreSQL hay InnoDB. SQLite điều phối ghi ở phạm vi database/file; tại một thời điểm chỉ có một writer thực hiện ghi.

Nếu transaction biết trước sẽ đọc rồi ghi, có thể bắt đầu bằng:

```sql
BEGIN IMMEDIATE;

SELECT balance
FROM account
WHERE account_id = 42;

UPDATE account
SET balance = balance - 80
WHERE account_id = 42;

COMMIT;
```

`BEGIN IMMEDIATE` yêu cầu quyền bắt đầu transaction ghi ngay từ đầu. Nếu writer khác đang hoạt động, câu lệnh có thể chờ theo busy timeout hoặc trả `SQLITE_BUSY`. Việc này tránh tình huống transaction bắt đầu đọc ở chế độ deferred rồi không thể nâng cấp sang writer vì một transaction khác đã giành quyền ghi.

SQLite cũng có `BEGIN EXCLUSIVE`. Khác biệt với `BEGIN IMMEDIATE` phụ thuộc journal mode: trong rollback-journal mode, exclusive transaction ngăn cả reader khác; trong WAL mode, `IMMEDIATE` và `EXCLUSIVE` có hành vi tương tự về việc giành quyền writer. Dù dùng chế độ nào, đây vẫn là điều phối writer ở phạm vi database, không phải khóa một hàng riêng lẻ.

## 8. So sánh nhanh theo hệ quản trị

| Hệ quản trị | Cách khóa chủ động thường dùng | Không chờ / bỏ qua hàng | Điểm cần chú ý |
| --- | --- | --- | --- |
| PostgreSQL | `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE` | `NOWAIT`, `SKIP LOCKED` | `OF table` giới hạn bảng bị khóa; SSI ở Serializable phát hiện phụ thuộc nguy hiểm; khóa hàng không tự khóa hàng chưa tồn tại |
| MySQL/InnoDB | `FOR UPDATE`, `FOR SHARE` | `NOWAIT`, `SKIP LOCKED` trên phiên bản hỗ trợ | Locking read cần transaction; current read; phạm vi khóa phụ thuộc chỉ mục, isolation level và next-key/gap lock |
| Oracle | `FOR UPDATE` và `OF` | `NOWAIT`, `WAIT n`, `SKIP LOCKED` | Có giới hạn khi kết hợp với aggregate, `DISTINCT`, `GROUP BY` và một số view |
| SQL Server | `UPDLOCK`, kết hợp `ROWLOCK`, `HOLDLOCK` hoặc `READPAST` tùy mục tiêu | `NOWAIT`, `READPAST` | Không có cú pháp `FOR UPDATE`; table hints và key-range locks phụ thuộc transaction, isolation và chỉ mục |
| SQLite | `BEGIN IMMEDIATE` trước khi đọc/ghi | Busy timeout / `SQLITE_BUSY` | Không có row lock; chỉ một writer tại một thời điểm |

Đừng sao chép nguyên câu lệnh giữa các hệ quản trị chỉ vì chúng đều có từ khóa `UPDATE` hoặc `LOCK`. Cần đối chiếu cú pháp, isolation level, phạm vi khóa và điều kiện giải phóng khóa.

## 9. Hàng chưa tồn tại và điều kiện tìm kiếm

Một nhầm lẫn thường gặp là cho rằng `SELECT ... FOR UPDATE` khóa cả điều kiện tìm kiếm. Thực tế, ở nhiều hệ quản trị, locking read khóa những hàng đã tìm thấy. Nếu kết quả rỗng, không có row lock nào trên một hàng cụ thể.

Ví dụ kiểm tra email:

```sql
BEGIN;

SELECT user_id
FROM app_user
WHERE email = 'mai@example.com'
FOR UPDATE;

-- Nếu không có hàng, ứng dụng chèn người dùng mới.
INSERT INTO app_user(email)
VALUES ('mai@example.com');

COMMIT;
```

Hai transaction có thể cùng thấy không có hàng email đó rồi cùng thử insert. Cách bảo vệ phù hợp là ràng buộc `UNIQUE(email)` và xử lý lỗi duplicate/unique violation. `FOR UPDATE` trên kết quả rỗng không thay thế constraint duy nhất.

Phạm vi khóa khoảng trống là khác biệt lớn giữa các engine:

- PostgreSQL row lock không khóa một giá trị chưa tồn tại. Ở `SERIALIZABLE`, SSI có thể phát hiện phụ thuộc predicate và hủy transaction; cơ chế predicate lock của SSI không phải row lock chặn insert theo cách thông thường.
- InnoDB có thể dùng gap hoặc next-key lock cho range scan, đặc biệt ở `REPEATABLE READ`, tùy chỉ mục và execution plan. Đây không phải bảo đảm chung cho mọi truy vấn và mọi isolation level.
- Oracle `FOR UPDATE` khóa các hàng được chọn; nếu không có hàng, không có row lock cho một hàng tương lai. Có thể cần constraint hoặc cơ chế điều phối khác.
- SQL Server `SERIALIZABLE`/`HOLDLOCK` có thể dùng key-range lock để ngăn insert thỏa predicate khi truy vấn và chỉ mục cho phép.
- SQLite giành quyền writer ở cấp database bằng `BEGIN IMMEDIATE`, nên transaction writer khác phải chờ, nhưng không có row-level predicate lock.

Nếu quy tắc nghiệp vụ phụ thuộc vào một khoảng thời gian, tổng số hàng hoặc một tập dữ liệu, hãy xem thêm bài toán predicate và aggregate. Có thể cần Serializable, constraint phù hợp hoặc một hàng điều phối chung thay vì chỉ khóa những hàng hiện có.

## 10. Mẫu sử dụng an toàn trong ứng dụng

### Đọc rồi cập nhật một hàng

Mẫu cơ bản cho một hàng đã tồn tại:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 501
FOR UPDATE;

-- Ứng dụng xác nhận quantity đủ lớn.
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501;

COMMIT;
```

Nếu không có hàng, ứng dụng phải xử lý trường hợp sản phẩm không tồn tại. Nếu quy tắc là không cho số lượng âm, nên bổ sung constraint như `CHECK (quantity >= 0)` nếu hệ quản trị hỗ trợ và biểu diễn được điều kiện.

### Khóa nhiều hàng theo cùng một thứ tự

Nếu một transaction cần khóa nhiều tài khoản, mọi luồng chuyển tiền nên khóa theo thứ tự nhất quán, ví dụ account ID tăng dần:

```sql
BEGIN;

SELECT account_id, balance
FROM account
WHERE account_id IN (100, 200)
ORDER BY account_id
FOR UPDATE;

-- Kiểm tra và cập nhật cả hai tài khoản.
COMMIT;
```

Thứ tự khóa nhất quán làm giảm nguy cơ hai transaction giữ các khóa theo thứ tự ngược nhau rồi chờ nhau. Cách viết và mức độ bảo đảm thứ tự khóa phụ thuộc engine; nếu cần kiểm soát chặt, có thể khóa từng hàng theo thứ tự trong transaction.

### Dùng `SKIP LOCKED` cho queue

Với queue, một worker có thể lấy một hàng sẵn sàng, khóa nó, chuyển trạng thái và commit:

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE SKIP LOCKED;

UPDATE job_queue
SET status = 'PROCESSING'
WHERE job_id = :job_id;

COMMIT;
```

Đây là mẫu khái quát cho PostgreSQL, MySQL/InnoDB hoặc Oracle với các điều chỉnh cú pháp và cách lấy một hàng theo engine. SQL Server thường dùng `UPDLOCK` kết hợp `READPAST`; SQLite cần mô hình queue khác vì chỉ có một writer.

Hãy cập nhật trạng thái ngay trong transaction khóa hàng. Nếu chỉ đọc ID rồi commit, worker khác có thể lấy cùng ID sau khi khóa được giải phóng. Sau commit, xử lý công việc bên ngoài transaction nếu có thể; tránh giữ khóa trong khi gọi dịch vụ lâu hoặc chờ người dùng.

## 11. Chờ khóa, timeout, deadlock và retry

Khóa chủ động làm tăng tính có thể dự đoán của thao tác đọc rồi ghi, nhưng nó cũng tạo ra thời gian chờ. Một transaction giữ khóa càng lâu thì các transaction khác càng có thể bị chặn.

Một số nguyên tắc thực tế:

1. Mở transaction ngay trước phần đọc/ghi cần đồng bộ hóa và commit sớm khi hoàn tất.
2. Không giữ khóa trong lúc gọi API, gửi email, chờ người dùng hoặc thực hiện công việc tốn thời gian bên ngoài cơ sở dữ liệu.
3. Khóa các hàng theo cùng một thứ tự trong tất cả luồng xử lý để giảm deadlock.
4. Chọn chỉ mục phù hợp để truy vấn khóa đúng phạm vi cần thiết, đặc biệt với InnoDB và SQL Server.
5. Dùng `NOWAIT` khi ứng dụng có thể báo bận ngay; dùng `SKIP LOCKED` cho queue khi bỏ qua hàng đang được xử lý là đúng nghiệp vụ.
6. Theo dõi lock wait, transaction chạy lâu, deadlock và timeout trong môi trường thật.

Deadlock vẫn có thể xảy ra. Ví dụ T1 khóa hàng A rồi cần B, trong khi T2 khóa B rồi cần A. Hệ quản trị thường phát hiện vòng chờ và chọn một transaction làm nạn nhân rollback. Ứng dụng nên xử lý lỗi deadlock hoặc serialization failure bằng cách rollback và thử lại toàn bộ transaction khi thao tác có thể retry an toàn.

Không nên retry vô hạn. Dùng số lần thử có giới hạn và backoff phù hợp. Với tác dụng phụ bên ngoài database, cần idempotency hoặc cơ chế phát sự kiện sau commit để retry không tạo tác dụng phụ trùng lặp.

## 12. Danh sách kiểm tra khi chuyển giữa các hệ quản trị

Trước khi chuyển một luồng dùng `SELECT FOR UPDATE` sang engine khác, hãy trả lời các câu hỏi sau:

- Engine đích có hỗ trợ cú pháp `FOR UPDATE` không, hay cần table hints hoặc transaction mode khác?
- Transaction có thực sự mở và giữ qua toàn bộ thao tác đọc, kiểm tra và cập nhật không? Autocommit có làm khóa bị giải phóng quá sớm không?
- Câu truy vấn khóa hàng nào trong join? Có cần chỉ định `OF table` hoặc hint cho đúng bảng không?
- Nếu kết quả rỗng, có cơ chế nào bảo vệ predicate hoặc khoảng trống không? Có cần `UNIQUE`, exclusion constraint, Serializable hoặc hàng guard không?
- Isolation level hiện tại là gì? Engine dùng snapshot read, current read, row lock, gap/next-key lock hay key-range lock như thế nào?
- Khi không lấy được khóa, ứng dụng sẽ chờ, nhận lỗi ngay hay bỏ qua hàng? Có cần `NOWAIT`, `WAIT n`, `SKIP LOCKED`, `READPAST` hoặc timeout không?
- Truy vấn có aggregate, `DISTINCT`, `GROUP BY`, subquery hoặc view khiến locking clause bị giới hạn không?
- Deadlock, lock timeout, serialization failure và unique violation được chuyển thành hành vi ứng dụng nào?

## 13. Những điểm cần ghi nhớ

- `SELECT FOR UPDATE` là locking read dùng để giữ quyền khóa trên các hàng đã chọn trong transaction, thường phục vụ quy trình đọc rồi cập nhật.
- Khóa được giữ qua các câu lệnh cho đến khi transaction commit hoặc rollback; cần tránh autocommit làm transaction kết thúc quá sớm.
- PostgreSQL, MySQL/InnoDB và Oracle có cú pháp `FOR UPDATE` nhưng khác nhau về lock mode, phạm vi khóa, timeout và giới hạn truy vấn.
- SQL Server dùng table hints như `UPDLOCK`, `HOLDLOCK`, `READPAST` và `ROWLOCK`; SQLite dùng `BEGIN IMMEDIATE` và không có row-level `FOR UPDATE`.
- `NOWAIT` trả lỗi khi không thể lấy khóa ngay; `SKIP LOCKED` bỏ qua hàng đang bị khóa và thường phù hợp với queue.
- Khóa hàng hiện có không tự động bảo vệ hàng chưa tồn tại hoặc mọi predicate. Gap/next-key lock và key-range lock phụ thuộc engine, isolation level, chỉ mục và execution plan.
- Constraint, Serializable hoặc hàng điều phối chung có thể cần thiết để bảo vệ điều kiện nghiệp vụ trên nhiều hàng.
- Khóa chủ động không loại bỏ deadlock. Transaction nên ngắn, thứ tự khóa nhất quán và ứng dụng cần xử lý retry có giới hạn.
