# Đối chiếu cú pháp khóa, mã lỗi và yêu cầu thực thi lại

Các hệ quản trị cơ sở dữ liệu đều cung cấp khóa, isolation level và cơ chế phát hiện xung đột, nhưng cú pháp và hành vi khi lỗi xảy ra không giống nhau. PostgreSQL dùng `SELECT ... FOR UPDATE`, MySQL InnoDB có locking read và `SKIP LOCKED`, SQL Server thường dùng table hints, còn Oracle hỗ trợ `FOR UPDATE` với `NOWAIT`, `WAIT` hoặc `SKIP LOCKED`. Mã lỗi deadlock, timeout và serialization failure cũng khác nhau.

Vì vậy, lớp truy cập dữ liệu không nên giả định mọi database có cùng cách khóa hoặc cùng trạng thái transaction sau một lỗi. Cần ánh xạ lỗi theo driver và DBMS, xác định transaction còn commit được hay không, rồi mới quyết định rollback, retry hoặc trả lỗi nghiệp vụ. Quy tắc chung là chỉ retry khi lỗi có thể tạm thời, chạy lại toàn bộ đơn vị transaction và bảo vệ tác dụng phụ bằng idempotency.

## 1. Những điểm cần so sánh

Khi chuyển một chức năng giữa các hệ quản trị hoặc hỗ trợ nhiều DBMS, hãy so sánh ít nhất năm khía cạnh:

1. **Cú pháp lấy khóa:** câu lệnh khóa hàng, chế độ chờ, bỏ qua hàng đang khóa và khóa tư vấn.
2. **Phạm vi khóa:** hàng, index key, khoảng khóa, trang, bảng hoặc predicate.
3. **Isolation level:** tên mức có thể giống nhau nhưng ngữ nghĩa và mặc định khác nhau.
4. **Mã lỗi:** deadlock, lock timeout, serialization failure, query cancellation và lỗi constraint có mã riêng.
5. **Trạng thái transaction sau lỗi:** chỉ câu lệnh bị rollback, toàn transaction bị rollback, transaction bị đánh dấu lỗi hay kết quả commit chưa xác định.

Một câu SQL chạy được trên hai sản phẩm chưa chắc có cùng lock footprint. Tương tự, cùng một lỗi timeout có thể chỉ dừng câu lệnh ở một DBMS nhưng để transaction còn mở ở DBMS khác.

## 2. So sánh cú pháp khóa hàng

| Nhu cầu | PostgreSQL | MySQL InnoDB | SQL Server | Oracle Database |
|---|---|---|---|---|
| Khóa hàng để cập nhật | `SELECT ... FOR UPDATE` | `SELECT ... FOR UPDATE` | `WITH (UPDLOCK)` hoặc câu `UPDATE` thích hợp | `SELECT ... FOR UPDATE` |
| Không chờ khóa hàng | `FOR UPDATE NOWAIT` | `FOR UPDATE NOWAIT` (MySQL 8.0+) | `NOWAIT` table hint hoặc `SET LOCK_TIMEOUT 0` | `FOR UPDATE NOWAIT` |
| Bỏ qua hàng đang khóa | `FOR UPDATE SKIP LOCKED` | `FOR UPDATE SKIP LOCKED` (MySQL 8.0+) | `READPAST` kết hợp lock hints phù hợp | `FOR UPDATE SKIP LOCKED` |
| Chờ tối đa | `lock_timeout` hoặc timeout ở client | `innodb_lock_wait_timeout` | `SET LOCK_TIMEOUT <milliseconds>` | `FOR UPDATE WAIT n` |
| Khóa tư vấn do ứng dụng định danh | Có `pg_advisory_lock` và `pg_advisory_xact_lock` | Không có API advisory lock tương đương trực tiếp trong InnoDB; thường dùng hàng điều phối hoặc cơ chế khác | `sp_getapplock` | Có `DBMS_LOCK` nếu được cấp quyền và cấu hình phù hợp |

Các ví dụ trong bảng là điểm bắt đầu. Cú pháp chi tiết, giới hạn của locking clause và khả năng tương thích với isolation level phụ thuộc phiên bản và cấu hình. Không nên thay thế cơ học một câu `FOR UPDATE` bằng một hint cùng tên trên DBMS khác.

## 3. PostgreSQL: FOR UPDATE, NOWAIT và SKIP LOCKED

PostgreSQL dùng locking clause trong câu `SELECT`:

```sql
BEGIN;

SELECT account_id, balance
FROM account
WHERE account_id = :account_id
FOR UPDATE;

UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id;

COMMIT;
```

`FOR UPDATE` khóa các hàng được chọn cho đến khi transaction kết thúc. PostgreSQL còn có `FOR NO KEY UPDATE`, `FOR SHARE` và `FOR KEY SHARE` để chọn mức xung đột phù hợp hơn.

Nếu không muốn chờ hàng đang bị khóa:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 20
FOR UPDATE NOWAIT;
```

Nếu xây dựng worker queue và muốn bỏ qua hàng đang được worker khác xử lý:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 20
FOR UPDATE SKIP LOCKED;
```

`NOWAIT` và `SKIP LOCKED` thay đổi cách xử lý khóa hàng. Các khóa ở cấp bảng vẫn được lấy theo quy tắc bình thường và vẫn có thể phải chờ. `SKIP LOCKED` tạo kết quả không đầy đủ có chủ ý, phù hợp cho phân phối công việc hơn là truy vấn báo cáo.

Để giới hạn thời gian chờ khóa, PostgreSQL có thể cấu hình theo transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT *
FROM account
WHERE account_id = :account_id
FOR UPDATE;

COMMIT;
```

`lock_timeout` giới hạn thời gian chờ một khóa; `statement_timeout` giới hạn thời gian thực thi câu lệnh. Nếu đặt cả hai, nên bảo đảm thời hạn chờ khóa không dài hơn thời hạn câu lệnh theo mục đích vận hành.

## 4. MySQL InnoDB: locking read và gap/next-key lock

Với InnoDB, locking read thường được dùng trong transaction tường minh:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM account
WHERE account_id = :account_id
FOR UPDATE;

UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id;

COMMIT;
```

Trong InnoDB, `SELECT ... FOR UPDATE` cần transaction đang hoạt động; nếu bật autocommit và không mở transaction phù hợp, khóa không được giữ qua một chuỗi câu lệnh như ứng dụng có thể mong đợi.

MySQL 8.0 hỗ trợ `NOWAIT` và `SKIP LOCKED` cho locking read:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Cập nhật claim trong cùng transaction.

COMMIT;
```

InnoDB khóa các index record mà đường truy cập sử dụng. Tùy isolation level, predicate và index, một truy vấn phạm vi có thể dùng gap lock hoặc next-key lock để ngăn chèn phantom. Vì vậy, index và kế hoạch truy vấn ảnh hưởng trực tiếp đến phạm vi khóa. Không có index phù hợp có thể khiến truy vấn quét và khóa nhiều mục hơn dự kiến.

Thời gian chờ khóa có thể được điều chỉnh bằng `innodb_lock_wait_timeout`. Timeout này không giống deadlock: deadlock detector có thể chọn một transaction làm nạn nhân ngay khi phát hiện vòng chờ, còn lock wait timeout xảy ra khi một yêu cầu chờ quá thời hạn cấu hình.

## 5. SQL Server: lock hints và isolation level

SQL Server thường dùng table hints thay cho cú pháp `SELECT ... FOR UPDATE`:

```sql
BEGIN TRANSACTION;

SELECT account_id, balance
FROM dbo.account WITH (UPDLOCK, ROWLOCK)
WHERE account_id = @account_id;

UPDATE dbo.account
SET balance = balance - @amount
WHERE account_id = @account_id;

COMMIT TRANSACTION;
```

- `UPDLOCK` yêu cầu update lock khi đọc, giúp giảm tình huống hai transaction cùng đọc rồi cùng cố nâng cấp khóa.
- `ROWLOCK` gợi ý dùng khóa hàng, nhưng không phải cam kết tuyệt đối rằng engine sẽ không dùng page hoặc table lock.
- `HOLDLOCK` tương đương ngữ nghĩa `SERIALIZABLE` cho tham chiếu bảng được chỉ định trong câu lệnh.
- `READPAST` cho phép bỏ qua một số hàng đang bị khóa, thường dùng trong hàng đợi; có giới hạn theo isolation level và cấu hình `READ_COMMITTED_SNAPSHOT`.
- `NOWAIT` yêu cầu lỗi ngay nếu phải chờ khóa trên tài nguyên liên quan.

Ví dụ worker queue:

```sql
;WITH picked AS (
    SELECT TOP (@batch_size) *
    FROM dbo.job_queue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE status = 'PENDING'
    ORDER BY available_at, job_id
)
UPDATE picked
SET status = 'PROCESSING',
    claimed_by = @worker_id,
    claimed_at = SYSUTCDATETIME()
OUTPUT inserted.job_id, inserted.payload;
```

Đây là mẫu SQL Server; cần xác nhận hint và isolation level trong cấu hình triển khai. `READPAST` không phải bản sao hoàn toàn tương đương `SKIP LOCKED` của PostgreSQL hoặc InnoDB. `ROWLOCK` cũng không bảo đảm không có lock escalation.

SQL Server có thể giới hạn chờ bằng:

```sql
SET LOCK_TIMEOUT 2000; -- milliseconds
```

Giá trị áp dụng cho session, nên ứng dụng dùng connection pool phải reset session setting trước khi trả connection về pool hoặc đặt lại theo chuẩn của ứng dụng.

## 6. Oracle: FOR UPDATE với NOWAIT, WAIT và SKIP LOCKED

Oracle hỗ trợ locking clause trong `SELECT`:

```sql
SELECT account_id, balance
FROM account
WHERE account_id = :account_id
FOR UPDATE;
```

Có thể chọn cách chờ:

```sql
-- Lỗi ngay nếu hàng đang bị khóa
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
FOR UPDATE NOWAIT;

-- Chờ tối đa 5 giây
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
FOR UPDATE WAIT 5;

-- Bỏ qua hàng đang bị session khác khóa
SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
FOR UPDATE SKIP LOCKED;
```

Với batch lớn, có thể dùng cursor `FOR UPDATE SKIP LOCKED` trong PL/SQL và fetch theo từng nhóm. Cú pháp `FOR UPDATE` có giới hạn với một số truy vấn phức tạp như truy vấn tổng hợp, `DISTINCT`, `GROUP BY` hoặc một số dạng view/join; cần tham khảo tài liệu Oracle cho câu lệnh cụ thể.

Oracle có `DBMS_LOCK` để phối hợp khóa logic do ứng dụng định danh, nhưng việc dùng package có thể cần quyền cấp rõ ràng và cần quản lý vòng đời khóa. Đừng nhầm nó với row lock tự động của `FOR UPDATE`.

## 7. So sánh cú pháp isolation level

Tên isolation level giống nhau không bảo đảm cùng cách triển khai hoặc cùng mặc định:

| DBMS | Bắt đầu transaction Serializable | Ghi chú |
|---|---|---|
| PostgreSQL | `BEGIN ISOLATION LEVEL SERIALIZABLE;` | Dùng SSI để phát hiện phụ thuộc nguy hiểm; có thể trả lỗi `40001`. |
| MySQL InnoDB | `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; START TRANSACTION;` | InnoDB dùng khóa và MVCC tùy isolation level; mặc định thường là `REPEATABLE READ`. |
| SQL Server | `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; BEGIN TRANSACTION;` | Có thể kết hợp row/page/key locks và range locks; `SNAPSHOT` là lựa chọn riêng, cần bật cấu hình database. |
| Oracle | `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;` trước câu lệnh đầu tiên của transaction | Oracle dùng consistent reads và phát hiện xung đột cập nhật; có thể trả `ORA-08177`. |

Các mặc định phổ biến cũng khác: PostgreSQL và Oracle thường mặc định `READ COMMITTED`; MySQL InnoDB thường mặc định `REPEATABLE READ`; SQL Server thường mặc định `READ COMMITTED`, nhưng hành vi đọc có thể khác khi `READ_COMMITTED_SNAPSHOT` được bật. Hãy đọc cấu hình thực tế thay vì dựa vào mặc định của một môi trường khác.

## 8. Bảng đối chiếu mã lỗi thường gặp

Mã lỗi dưới đây giúp phân loại nguyên nhân và chọn hành động. Với PostgreSQL, SQLSTATE là mã chuẩn có cấu trúc; MySQL thường cung cấp cả số lỗi và SQLSTATE; SQL Server thường được ứng dụng xử lý theo native error number; Oracle dùng mã `ORA-xxxxx`.

| Tình huống | PostgreSQL | MySQL InnoDB | SQL Server | Oracle |
|---|---|---|---|---|
| Deadlock | SQLSTATE `40P01` | Error `1213`, SQLSTATE `40001` | Error `1205` | `ORA-00060` |
| Serialization/update conflict | SQLSTATE `40001` | Tùy isolation/cơ chế; thường cần phân biệt với deadlock `1213` | Error `3960` cho snapshot update conflict | `ORA-08177` |
| Lock wait timeout | SQLSTATE `55P03` khi timeout/không lấy được khóa theo cấu hình phù hợp | Error `1205`, SQLSTATE thường `HY000` | Error `1222` | `ORA-30006` với `WAIT` timeout; `ORA-00054` cho resource busy/NOWAIT |
| Hủy câu lệnh/query timeout | SQLSTATE `57014` | Có thể gặp lỗi timeout/cancel theo driver hoặc lệnh quản trị; mã phụ thuộc cách hủy | Client timeout thường được driver báo riêng; lock timeout là `1222` | `ORA-01013` |
| Unique constraint | SQLSTATE `23505` | Error `1062`, SQLSTATE `23000` | Error `2601` hoặc `2627` | `ORA-00001` |
| Foreign key | SQLSTATE `23503` | Error `1451`/`1452`, SQLSTATE `23000` | Error `547` | `ORA-02291`/`ORA-02292` |

Mã lỗi và trạng thái sau lỗi có thể thay đổi theo phiên bản, driver, loại câu lệnh và cấu hình. Hãy xác nhận bằng tài liệu của đúng phiên bản đang chạy. Đặc biệt, đừng gom mọi lỗi trong bảng thành một nhóm “retryable”.

## 9. Ý nghĩa các lỗi cạnh tranh và hành động phù hợp

### 9.1. Deadlock

Deadlock có nghĩa một vòng chờ đã hình thành. Hệ quản trị chọn một transaction hoặc câu lệnh làm nạn nhân để phá vòng chờ.

- PostgreSQL: `40P01` (`deadlock_detected`). Transaction bị lỗi và cần rollback trước khi dùng lại connection.
- MySQL InnoDB: `1213` (`ER_LOCK_DEADLOCK`), InnoDB thường rollback toàn bộ transaction nạn nhân.
- SQL Server: `1205`, transaction được chọn làm deadlock victim và bị rollback.
- Oracle: `ORA-00060`; Oracle thường rollback câu lệnh gây deadlock, transaction có thể vẫn còn mở.

Ứng dụng thường nên rollback đơn vị transaction và retry toàn bộ công việc nếu thao tác có thể lặp an toàn. Retry chỉ câu lệnh cuối có thể dùng lại những quyết định dựa trên dữ liệu đã cũ.

### 9.2. Lock wait timeout hoặc NOWAIT

Timeout có nghĩa không lấy được khóa trong thời hạn cho phép; nó không nhất thiết là deadlock.

- PostgreSQL: `lock_timeout` có thể tạo `55P03`; transaction đang ở trạng thái lỗi sau exception và cần rollback hoặc rollback về savepoint.
- MySQL InnoDB: `1205` mặc định thường rollback câu lệnh bị timeout, không nhất thiết rollback toàn transaction. Cấu hình `innodb_rollback_on_timeout` có thể thay đổi hành vi; ứng dụng nên rollback toàn bộ đơn vị công việc nếu nó không còn hợp lệ.
- SQL Server: `1222`; kiểm tra trạng thái transaction bằng `XACT_STATE()` và `@@TRANCOUNT`, sau đó rollback nếu cần.
- Oracle: `ORA-00054` hoặc `ORA-30006`; câu lệnh thất bại, transaction có thể vẫn còn mở.

Nếu nghiệp vụ cho phép chờ, tăng timeout có thể phù hợp. Nếu người dùng cần phản hồi nhanh, dùng `NOWAIT`/try-lock và trả trạng thái bận. Không retry liên tục ngay lập tức vì có thể làm tăng contention.

### 9.3. Serialization failure hoặc snapshot conflict

Các lỗi này báo rằng transaction không thể commit theo isolation guarantee đã chọn:

- PostgreSQL: `40001`; thường phải chạy lại toàn bộ transaction trong `SERIALIZABLE`.
- SQL Server: `3960` khi transaction ở snapshot isolation gặp update conflict; cần rollback và thực hiện lại logic từ đầu.
- Oracle: `ORA-08177` khi transaction Serializable không thể tiếp tục do dữ liệu đã bị transaction khác thay đổi theo cách xung đột; thường retry toàn transaction.
- MySQL InnoDB: không có một mã lỗi duy nhất tương ứng với mọi dạng serialization conflict; deadlock `1213` và lock wait `1205` cần được phân loại riêng theo cơ chế thực tế.

Không retry một câu lệnh cập nhật đơn lẻ với cùng dữ liệu đã đọc. Transaction mới phải đọc lại và đánh giá lại invariant.

## 10. Transaction còn ở trạng thái nào sau lỗi?

Đây là khác biệt quan trọng nhất khi viết lớp truy cập dữ liệu dùng chung:

| DBMS | Hành vi cần lưu ý sau lỗi câu lệnh |
|---|---|
| PostgreSQL | Phần lớn lỗi SQL trong transaction block làm transaction chuyển sang trạng thái aborted. Các câu lệnh tiếp theo bị từ chối cho đến `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT`. |
| MySQL InnoDB | Deadlock thường rollback toàn transaction; lock wait timeout mặc định thường chỉ rollback statement; nhiều lỗi constraint chỉ hủy statement. Ứng dụng phải biết cấu hình và chủ động rollback đơn vị công việc khi cần. |
| SQL Server | Tùy lỗi và `SET XACT_ABORT`, transaction có thể còn commit được, đã rollback hoặc ở trạng thái không thể commit. `XACT_STATE()` cho biết trạng thái hiện tại. |
| Oracle | Nhiều lỗi chỉ rollback statement; transaction vẫn có thể tiếp tục. Deadlock thường rollback statement bị chọn, không mặc định rollback toàn transaction. Ứng dụng phải rollback nếu toàn bộ nghiệp vụ cần nguyên tử. |

### 10.1. PostgreSQL: transaction aborted

Sau một lỗi như deadlock hoặc lock timeout trong transaction, PostgreSQL thường không cho chạy tiếp câu lệnh bình thường. Cần rollback:

```sql
BEGIN;

UPDATE account SET balance = balance - 10 WHERE account_id = 1;

-- Giả sử câu lệnh tiếp theo lỗi.

ROLLBACK;
```

Nếu chỉ muốn hủy một bước tùy chọn, có thể đặt savepoint trước bước đó và rollback về savepoint khi lỗi. Transaction vẫn phải kết thúc bằng commit hoặc rollback.

### 10.2. MySQL: phân biệt rollback statement và transaction

Với InnoDB, deadlock thường khiến toàn bộ transaction nạn nhân bị rollback. Nhưng lock wait timeout mặc định thường chỉ rollback statement đang chờ. Ví dụ, nếu câu đầu đã cập nhật một hàng rồi câu thứ hai timeout, câu đầu có thể vẫn còn trong transaction.

Ứng dụng không nên tiếp tục commit một nửa nghiệp vụ chỉ vì connection vẫn nhận câu lệnh mới. Nếu toàn bộ thao tác cần nguyên tử, hãy rollback transaction sau timeout rồi mới quyết định retry.

### 10.3. SQL Server: XACT_STATE

Trong `TRY/CATCH`, `XACT_STATE()` cho biết transaction còn commit được hay không:

- `1`: có transaction đang hoạt động và còn có thể commit.
- `-1`: transaction đang ở trạng thái uncommittable; chỉ có thể đọc hoặc rollback, không thể commit.
- `0`: không có transaction người dùng đang hoạt động.

Ví dụ xử lý:

```sql
BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.account
    SET balance = balance - @amount
    WHERE account_id = @account_id;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
```

`SET XACT_ABORT ON` có thể làm nhiều lỗi runtime khiến transaction bị hủy toàn bộ, nhưng không thay thế việc kiểm tra trạng thái trong `CATCH`. Cần xác định cấu hình session và loại lỗi cụ thể.

### 10.4. Oracle: statement-level rollback

Oracle thường đảm bảo tính nguyên tử ở cấp câu lệnh: nếu một câu lệnh thất bại, thay đổi của chính câu lệnh đó bị rollback, trong khi các câu lệnh trước trong transaction có thể vẫn còn. Điều này không có nghĩa ứng dụng nên commit phần trước nếu quy trình nghiệp vụ đã thất bại. Hãy rollback toàn transaction khi các bước phải cùng thành công.

## 11. Phân loại lỗi trước khi quyết định retry

Một lớp truy cập dữ liệu có thể phân lỗi thành các nhóm sau:

| Nhóm | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Xung đột tạm thời | Deadlock, serialization failure, snapshot update conflict | Rollback đơn vị transaction và retry toàn bộ với giới hạn/backoff. |
| Không lấy được khóa đúng hạn | NOWAIT, lock timeout | Trả trạng thái bận hoặc retry sau backoff nếu nghiệp vụ cho phép. |
| Lỗi dữ liệu/ràng buộc | Unique, foreign key, check constraint | Thường không retry mù; kiểm tra đầu vào hoặc xử lý xung đột nghiệp vụ. |
| Bị người dùng hủy | Query cancellation hoặc request cancellation | Dừng công việc, rollback nếu cần và xác minh transaction đã kết thúc. |
| Mất kết nối trong lúc commit | Client không nhận được kết quả commit | Kết quả chưa xác định; đối soát bằng operation ID/idempotency key trước khi retry. |
| Lỗi lập trình/cấu hình | SQL sai, quyền thiếu, object không tồn tại | Sửa nguyên nhân; retry thường không giúp ích. |

Unique violation có thể là xung đột dự kiến trong một thao tác “tạo nếu chưa có”. Khi đó, ứng dụng có thể đọc bản ghi đã tồn tại và trả kết quả phù hợp. Nhưng với một lệnh tạo đơn hàng hoặc chuyển tiền, không được tự coi duplicate key là thành công nếu chưa xác minh nó thuộc cùng idempotency key và cùng payload nghiệp vụ.

## 12. Retry toàn transaction thay vì retry riêng câu lệnh

Giả sử transaction thực hiện:

1. Đọc số dư hai tài khoản.
2. Kiểm tra hạn mức.
3. Trừ tài khoản nguồn.
4. Cộng tài khoản đích.
5. Ghi lịch sử chuyển tiền.

Nếu bước 4 gặp deadlock, retry riêng bước 4 sẽ giữ lại quyết định và kết quả đọc từ trước. Một transaction mới phải đọc lại số dư, kiểm tra hạn mức và thực hiện tất cả bước trong cùng một đơn vị nguyên tử.

Pseudocode:

```text
for attempt in 1..MAX_RETRIES:
    begin transaction
    try:
        read current state
        validate business rules
        apply all database changes
        commit
        return success
    catch retryable concurrency error:
        rollback if transaction is still active
        wait with bounded exponential backoff and jitter

return retryable failure
```

Chỉ các lỗi đã được xác định là retryable mới đi vào nhánh này. Mỗi lần thử phải dùng transaction mới và connection ở trạng thái sạch.

## 13. Không để retry nhân đôi tác dụng phụ

Retry toàn transaction có thể thực hiện lại logic ứng dụng. Nếu logic gửi email, gọi API thanh toán hoặc phát message trước commit, lần retry có thể tạo tác dụng phụ trùng.

Hai kỹ thuật thường dùng:

- **Idempotency key:** mỗi yêu cầu nghiệp vụ có một ID ổn định; hệ thống nhận yêu cầu lưu ID và từ chối xử lý trùng.
- **Transactional outbox:** transaction ghi dữ liệu nghiệp vụ và một bản ghi sự kiện trong cùng commit; worker riêng gửi sự kiện sau commit, có retry và consumer idempotent.

Đặc biệt, mất kết nối trong lúc gửi `COMMIT` là trường hợp không thể suy ra chắc chắn từ timeout. Server có thể đã commit nhưng response bị mất. Không retry thao tác không idempotent cho đến khi đối soát được operation ID hoặc kết quả bền vững.

## 14. Thiết kế abstraction đa DBMS

Nếu ứng dụng hỗ trợ nhiều hệ quản trị, không nên để business logic phụ thuộc trực tiếp vào một mã lỗi hoặc cú pháp khóa cụ thể. Có thể tạo lớp adapter cho từng DBMS và ánh xạ lỗi về một nhóm chung:

```text
DatabaseErrorCategory:
    DEADLOCK
    SERIALIZATION_CONFLICT
    LOCK_TIMEOUT
    LOCK_NOT_AVAILABLE
    QUERY_CANCELLED
    CONSTRAINT_VIOLATION
    CONNECTION_LOST
    UNKNOWN
```

Adapter cần đọc đúng trường lỗi của driver:

- PostgreSQL JDBC: SQLSTATE từ `SQLException.getSQLState()` và vendor code nếu cần.
- MySQL Connector/J: SQLSTATE và vendor error number.
- Microsoft JDBC/SqlClient: SQL Server error number, SQLSTATE và trạng thái transaction.
- Oracle JDBC: vendor error code và SQLState nếu driver cung cấp.

Không chỉ so sánh chuỗi message vì thông điệp có thể thay đổi theo phiên bản hoặc ngôn ngữ. Cũng không nên chỉ so sánh SQLSTATE nếu DBMS có nhiều lỗi dùng cùng SQLSTATE nhưng yêu cầu xử lý khác nhau. Hãy kết hợp vendor code, SQLSTATE, loại exception và trạng thái transaction.

Ví dụ ánh xạ ở mức khái niệm:

```text
PostgreSQL 40P01       -> DEADLOCK
PostgreSQL 40001       -> SERIALIZATION_CONFLICT
MySQL 1213             -> DEADLOCK
MySQL 1205             -> LOCK_TIMEOUT
SQL Server 1205        -> DEADLOCK
SQL Server 3960        -> SERIALIZATION_CONFLICT
Oracle ORA-00060       -> DEADLOCK
Oracle ORA-08177       -> SERIALIZATION_CONFLICT
```

Sau khi phân loại, policy chung vẫn cần quyết định rollback, retry và backoff. Adapter không thể tự quyết định mọi nghiệp vụ; ví dụ một lock timeout có thể trả “tài nguyên đang bận” thay vì retry tự động.

## 15. Timeout và cancellation không giống deadlock

Deadlock là vòng chờ đã được phát hiện. Timeout chỉ nói rằng thời hạn chờ hoặc thực thi đã hết; có thể không có vòng chờ nào.

Một số timeout phổ biến:

- PostgreSQL `lock_timeout`: giới hạn thời gian chờ khóa; `statement_timeout`: giới hạn thời gian thực thi câu lệnh.
- MySQL `innodb_lock_wait_timeout`: giới hạn chờ khóa InnoDB.
- SQL Server `SET LOCK_TIMEOUT`: giới hạn chờ khóa; command timeout ở driver là một cơ chế khác.
- Oracle `WAIT n` trong locking clause: giới hạn thời gian chờ; `NOWAIT` trả lỗi ngay.

Khi người dùng hủy hoặc client timeout, driver có thể gửi tín hiệu cancel nhưng server chưa chắc đã dừng ngay. Sau đó transaction có thể vẫn mở. Cần kết thúc transaction, xác minh connection sạch và phân biệt kết quả chưa xác định nếu lỗi xảy ra trong lúc commit.

## 16. Kiểm thử cùng một nghiệp vụ trên nhiều DBMS

Một bộ kiểm thử tương thích nên kiểm tra hành vi, không chỉ kiểm tra câu SQL có parse được.

### Kịch bản deadlock

1. Tạo hai hàng A và B.
2. Transaction T1 khóa A rồi yêu cầu B.
3. Transaction T2 khóa B rồi yêu cầu A.
4. Xác nhận DBMS phát hiện deadlock và một transaction nhận đúng mã lỗi.
5. Xác nhận ứng dụng rollback/cleanup connection rồi retry toàn transaction.

### Kịch bản lock timeout/NOWAIT

1. T1 khóa một hàng và giữ transaction mở.
2. T2 yêu cầu khóa cùng hàng bằng NOWAIT hoặc timeout ngắn.
3. Xác nhận mã lỗi đúng với DBMS.
4. Kiểm tra transaction T2 còn mở, bị đánh dấu lỗi hay đã rollback.
5. Xác nhận connection được làm sạch trước khi tái sử dụng.

### Kịch bản serialization conflict

1. Tạo invariant phụ thuộc nhiều hàng.
2. Hai transaction đọc cùng trạng thái rồi ghi những hàng khác nhau.
3. Chạy với isolation level tương ứng của từng DBMS.
4. Xác nhận lịch không hợp lệ bị ngăn bằng lỗi serialization, khóa hoặc cơ chế engine phù hợp.
5. Xác nhận retry đọc lại dữ liệu và kiểm tra invariant từ đầu.

### Kịch bản mất phản hồi commit

1. Gửi một thao tác có idempotency key.
2. Mô phỏng mất kết nối ngay sau khi gửi commit.
3. Dùng connection mới đối soát operation ID.
4. Xác nhận lần retry không tạo hiệu ứng nghiệp vụ thứ hai.

## 17. Checklist khi viết code hỗ trợ nhiều DBMS

- [ ] Đã xác định cú pháp khóa riêng cho từng hệ quản trị và phiên bản.
- [ ] Đã xác nhận isolation level và cấu hình mặc định thực tế.
- [ ] Đã hiểu `NOWAIT`, `SKIP LOCKED`, lock hints và timeout có khác biệt gì.
- [ ] Đã ánh xạ mã lỗi deadlock, serialization, timeout và cancellation bằng vendor code/SQLSTATE.
- [ ] Đã biết lỗi nào rollback statement, lỗi nào rollback transaction và lỗi nào để transaction ở trạng thái không thể commit.
- [ ] Đã dùng `XACT_STATE()` cho nhánh xử lý lỗi SQL Server khi cần.
- [ ] Đã rollback transaction và làm sạch connection trước khi trả về pool.
- [ ] Đã retry toàn bộ transaction với giới hạn, backoff và jitter.
- [ ] Đã phân biệt lỗi cạnh tranh tạm thời với lỗi constraint/nghiệp vụ.
- [ ] Đã dùng idempotency key hoặc outbox cho tác dụng phụ có thể bị chạy lại.
- [ ] Đã đối soát kết quả khi mất kết nối trong lúc commit.
- [ ] Đã kiểm thử deadlock, timeout, serialization conflict và cancellation trên từng DBMS được hỗ trợ.

## 18. Quy tắc thực thi lại an toàn

Một chiến lược retry đa DBMS đáng tin cậy cần giữ ba ranh giới rõ ràng:

1. **Ranh giới lỗi:** chỉ retry lỗi cạnh tranh được phân loại là tạm thời; lỗi dữ liệu, quyền hoặc nghiệp vụ cần được xử lý theo nguyên nhân.
2. **Ranh giới transaction:** rollback hoặc xác nhận transaction đã kết thúc, lấy trạng thái sạch rồi chạy lại toàn bộ đơn vị công việc.
3. **Ranh giới tác dụng phụ:** mọi hiệu ứng bên ngoài phải idempotent hoặc được phát qua outbox sau commit; kết quả commit chưa xác định phải được đối soát trước khi retry.

Đối chiếu cú pháp khóa và mã lỗi giúp lớp truy cập dữ liệu hiểu sự khác biệt giữa PostgreSQL, MySQL InnoDB, SQL Server và Oracle. Điều quan trọng hơn là giữ cùng một nguyên tắc nghiệp vụ: khóa đúng tài nguyên, nhận diện đúng loại lỗi, biết transaction đang ở trạng thái nào và chỉ thực thi lại toàn bộ công việc khi có thể chứng minh thao tác an toàn để lặp.
