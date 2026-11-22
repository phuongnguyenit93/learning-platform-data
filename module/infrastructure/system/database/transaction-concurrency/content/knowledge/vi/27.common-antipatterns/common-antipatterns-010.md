# Dùng SKIP LOCKED cho truy vấn cần tập kết quả đầy đủ

`SKIP LOCKED` là tùy chọn của một số hệ quản trị cơ sở dữ liệu cho phép truy vấn bỏ qua những hàng đang bị transaction khác khóa, thay vì chờ các khóa đó được giải phóng. Cách làm này hữu ích khi nhiều worker cùng lấy việc từ một queue: mỗi worker có thể nhận những hàng chưa được worker khác giữ.

Nhưng việc bỏ qua hàng bị khóa cũng có nghĩa kết quả truy vấn **không còn là toàn bộ tập hàng thỏa điều kiện**. Một truy vấn yêu cầu danh sách đầy đủ, báo cáo chính xác, đối soát, export hoặc kiểm tra bất biến nghiệp vụ có thể âm thầm bỏ sót dữ liệu nếu dùng `SKIP LOCKED`. Kết quả thiếu hàng không nhất thiết báo lỗi; truy vấn vẫn có thể trả về thành công với một tập con.

Vì vậy, cần phân biệt hai mục tiêu: lấy một số công việc hiện đang có thể claim, và đọc hoặc khóa đầy đủ mọi hàng thỏa điều kiện tại một snapshot. `SKIP LOCKED` phù hợp với mục tiêu thứ nhất; nó không phải cách tăng tốc an toàn cho mục tiêu thứ hai.

## 1. `SKIP LOCKED` thay đổi ý nghĩa kết quả như thế nào?

Giả sử bảng `orders` có 5 đơn hàng đang ở trạng thái `PENDING`. Transaction T1 đã khóa đơn hàng số 2 để cập nhật. T2 chạy truy vấn:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
ORDER BY order_id
FOR UPDATE SKIP LOCKED;
```

T2 có thể nhận các hàng 1, 3, 4 và 5, trong khi hàng 2 đang thỏa điều kiện nhưng bị bỏ qua vì T1 đang giữ khóa. Truy vấn không báo rằng kết quả thiếu một hàng; nó trả về những hàng T2 có thể khóa ngay.

```text
Các hàng thỏa điều kiện:  1   2   3   4   5
                             ^
                             T1 đang khóa

T2 dùng SKIP LOCKED:      1   -   3   4   5
                              bỏ qua
```

Nếu T2 dùng truy vấn khóa thông thường, nó có thể phải chờ T1 kết thúc rồi mới khóa và đọc hàng 2. Nếu T2 dùng `NOWAIT`, truy vấn có thể thất bại ngay khi gặp xung đột khóa, thay vì bỏ qua hàng đó.

### Ba hành vi khác nhau

| Cách truy vấn | Khi gặp hàng bị khóa | Ý nghĩa kết quả |
| --- | --- | --- |
| Lock mặc định, chờ khóa | Chờ transaction giữ khóa kết thúc | Có thể tiếp tục lấy hàng sau khi khóa được giải phóng; độ trễ tăng |
| `NOWAIT` | Báo lỗi ngay khi không lấy được khóa | Caller biết lần đọc/claim không hoàn tất và có thể retry hoặc báo bận |
| `SKIP LOCKED` | Bỏ qua hàng không khóa được | Trả về tập con những hàng khóa được; không bảo đảm đầy đủ |

Điểm quan trọng: `SKIP LOCKED` không chỉ thay đổi thời gian chờ. Nó thay đổi tập hàng mà truy vấn trả về. Ứng dụng phải coi đây là một kết quả best-effort có thể thiếu hàng.

## 2. Vì sao kết quả có thể thiếu dù truy vấn không báo lỗi?

Khóa hàng tồn tại để bảo vệ thao tác đồng thời. Khi một transaction giữ khóa độc quyền trên hàng, transaction khác không thể lấy một khóa xung đột trên cùng hàng ngay lập tức.

Với truy vấn `FOR UPDATE SKIP LOCKED`, database xử lý từng hàng phù hợp. Nếu hàng đó bị khóa bởi transaction khác, database bỏ qua hàng và tiếp tục tìm những hàng khác. Truy vấn có thể kết thúc bình thường với số hàng ít hơn số hàng thỏa điều kiện ban đầu.

Ví dụ một báo cáo cần tất cả hóa đơn chưa thanh toán:

```sql
SELECT invoice_id, amount
FROM invoice
WHERE status = 'UNPAID'
FOR UPDATE SKIP LOCKED;
```

Nếu một transaction khác đang khóa một hóa đơn, báo cáo có thể không nhận được hóa đơn đó. Nếu ứng dụng cộng tổng `amount` từ kết quả trả về và dùng tổng đó cho đối soát tài chính, tổng sẽ thấp hơn thực tế.

Không có exception để báo rằng dữ liệu bị thiếu. Đây là hành vi có chủ đích của `SKIP LOCKED`, không phải lỗi thực thi của database.

## 3. `SKIP LOCKED` phù hợp với hàng đợi công việc

Mẫu sử dụng điển hình là nhiều worker cùng lấy các job ở trạng thái `READY`. Mỗi worker muốn claim một batch nhỏ mà không phải chờ job đã được worker khác giữ.

Giả sử bảng queue:

```sql
CREATE TABLE job_queue (
    job_id       BIGINT PRIMARY KEY,
    status       VARCHAR(20) NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL,
    worker_id    VARCHAR(80),
    claimed_at   TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0
);
```

Hai worker có thể cùng truy vấn job `READY`. T1 khóa một số hàng trước; T2 bỏ qua các hàng đó và lấy các hàng khác. Nhờ vậy, worker không cần chờ chỉ vì job đầu danh sách đang được worker khác claim.

### Ví dụ PostgreSQL: claim và cập nhật trong một transaction

```sql
BEGIN;

WITH candidates AS (
    SELECT job_id
    FROM job_queue
    WHERE status = 'READY'
    ORDER BY priority DESC, created_at, job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 10
)
UPDATE job_queue AS j
SET status = 'PROCESSING',
    worker_id = :worker_id,
    claimed_at = clock_timestamp(),
    attempt_count = attempt_count + 1
FROM candidates AS c
WHERE j.job_id = c.job_id
RETURNING j.job_id, j.priority, j.created_at;

COMMIT;
```

Truy vấn chọn tối đa 10 job có thể khóa, cập nhật trạng thái trong cùng transaction và trả danh sách đã claim. Khi commit, worker khác nhìn thấy những job đó không còn ở trạng thái `READY`.

Kết quả có thể có 0 đến 10 hàng. Nếu 10 job đầu đang bị khóa, worker có thể lấy những job tiếp theo chưa bị khóa; nếu không còn job nào có thể claim, kết quả có thể rỗng dù vẫn có job `READY` đang bị worker khác giữ.

Việc chọn và cập nhật phải cùng transaction. Nếu ứng dụng SELECT danh sách ID, commit hoặc nhả khóa, rồi mới UPDATE ở transaction khác, hai worker có thể cùng nhìn thấy và cùng claim một job.

### Ví dụ MySQL/InnoDB: locking read rồi cập nhật

Trong MySQL 8.0 với InnoDB, có thể dùng locking read:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Ứng dụng giữ danh sách ID trên cùng connection/transaction.
UPDATE job_queue
SET status = 'PROCESSING',
    worker_id = :worker_id,
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE job_id IN (:claimed_ids)
  AND status = 'READY';

COMMIT;
```

Ứng dụng phải chạy SELECT và UPDATE trên cùng connection, cùng transaction; kiểm tra số hàng cập nhật và chỉ xử lý các ID đã thực sự claim. Nếu SELECT trả danh sách rỗng, không tạo câu UPDATE với danh sách ID không hợp lệ.

`SKIP LOCKED` trong InnoDB dành cho locking read và cố ý trả về view không nhất quán; nó phù hợp với queue-like table. Nó không làm cho truy vấn báo cáo hoặc nghiệp vụ cần tập đầy đủ trở nên an toàn. Cần kiểm tra tài liệu đúng phiên bản MySQL và kiểu replication đang dùng; locking read và các câu lệnh dựa vào nó có các giới hạn riêng.

### Ví dụ SQL Server: `READPAST` là cơ chế tương tự, không hoàn toàn giống

SQL Server thường dùng các table hint cho queue:

```sql
BEGIN TRANSACTION;

;WITH candidates AS (
    SELECT TOP (@batch_size) *
    FROM dbo.job_queue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE status = 'READY'
    ORDER BY priority DESC, created_at, job_id
)
UPDATE candidates
SET status = 'PROCESSING',
    worker_id = @worker_id,
    claimed_at = SYSUTCDATETIME(),
    attempt_count = attempt_count + 1
OUTPUT inserted.job_id, inserted.priority, inserted.created_at;

COMMIT TRANSACTION;
```

`READPAST` bỏ qua một số row-level lock thay vì chờ; `UPDLOCK` yêu cầu update lock khi đọc để phối hợp việc claim; `ROWLOCK` yêu cầu ưu tiên khóa hàng. Đây là mẫu queue thường gặp, nhưng `READPAST` không giống hoàn toàn cú pháp `SKIP LOCKED` của PostgreSQL/MySQL.

Đặc biệt, `READPAST` không bỏ qua page-level lock. Điều kiện sử dụng cũng phụ thuộc isolation level và cấu hình `READ_COMMITTED_SNAPSHOT`; một số cấu hình yêu cầu `READCOMMITTEDLOCK` để dùng đúng tổ hợp hint. `ROWLOCK` là hint, không phải bảo đảm tuyệt đối rằng engine sẽ luôn khóa từng hàng. Hãy kiểm tra tài liệu SQL Server theo phiên bản và isolation level của database.

### Oracle

Oracle hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED` cho các mô hình nhiều consumer lấy hàng từ queue. Ý nghĩa cốt lõi vẫn là bỏ qua hàng không thể khóa ngay, do đó tập kết quả có thể thiếu một số hàng thỏa predicate. Hãy dùng nó cho việc claim công việc có thể xử lý độc lập, không dùng cho truy vấn cần đầy đủ dữ liệu.

## 4. Truy vấn cần tập kết quả đầy đủ không được bỏ qua hàng khóa

Một truy vấn cần đầy đủ thường có một trong các mục tiêu sau:

- Đối soát tất cả giao dịch, hóa đơn hoặc ledger entry.
- Xuất toàn bộ dữ liệu cho báo cáo, audit hoặc migration.
- Tính tổng số tiền, số lượng tồn hoặc số bản ghi thỏa điều kiện.
- Kiểm tra bất biến nghiệp vụ trên mọi hàng trong một nhóm.
- Lấy danh sách đầy đủ để người dùng duyệt hoặc xử lý.
- Chọn toàn bộ hàng cần khóa trước khi thực hiện một thay đổi nguyên tử.

Nếu truy vấn dùng `SKIP LOCKED`, các hàng đang bị khóa có thể bị loại khỏi kết quả. Khi đó:

- Tổng tiền có thể thấp hơn thực tế.
- Số lượng bản ghi có thể nhỏ hơn số thực.
- Một hàng cần xử lý có thể không xuất hiện trong export.
- Kiểm tra điều kiện có thể kết luận sai vì bỏ qua hàng quan trọng.
- Pagination có thể bỏ qua hàng đang bị khóa và không bảo đảm một lượt duyệt đầy đủ.

Ví dụ kiểm tra tổng số tiền hóa đơn chưa thanh toán:

```sql
-- Không dùng SKIP LOCKED cho phép tính cần đầy đủ.
SELECT COALESCE(SUM(amount), 0) AS unpaid_total
FROM invoice
WHERE status = 'UNPAID';
```

Với một consistent read thông thường, MVCC cho phép database trả phiên bản phù hợp với snapshot mà không cần bỏ hàng chỉ vì transaction khác đang cập nhật chúng. Nếu nghiệp vụ cần khóa các hàng để xử lý, hãy dùng locking read có chờ khóa hoặc một cơ chế cô lập phù hợp.

## 5. Phân biệt đọc snapshot đầy đủ và locking read đầy đủ

Không phải mọi truy vấn đầy đủ đều cần khóa hàng. Cần xác định truy vấn muốn đọc một snapshot hay muốn giành quyền ghi trên các hàng.

### Chỉ cần đọc đầy đủ tại một snapshot

Dùng `SELECT` thông thường với isolation level phù hợp. Trong các engine MVCC, reader có thể đọc phiên bản đã commit phù hợp với snapshot dù writer đang cập nhật hàng. Reader không cần `SKIP LOCKED` để tránh chờ row lock trong trường hợp đọc snapshot thông thường.

Ví dụ:

```sql
SELECT invoice_id, amount, status
FROM invoice
WHERE status = 'UNPAID'
ORDER BY invoice_id;
```

Nếu cần nhiều statement nhìn cùng một snapshot, chọn transaction isolation level cung cấp semantics đó trong engine đang dùng. `READ COMMITTED` thường tạo snapshot theo statement; `REPEATABLE READ` hoặc snapshot isolation có thể giữ snapshot ổn định hơn, tùy hệ quản trị.

### Cần khóa mọi hàng sẽ được xử lý

Dùng locking read không có `SKIP LOCKED` để chờ các khóa xung đột được giải phóng:

```sql
BEGIN;

SELECT invoice_id, amount
FROM invoice
WHERE status = 'UNPAID'
ORDER BY invoice_id
FOR UPDATE;

-- Xử lý đầy đủ các hàng đã khóa.

COMMIT;
```

Truy vấn có thể phải chờ nếu transaction khác đang giữ khóa. Đây là chi phí phù hợp khi tính đầy đủ quan trọng hơn việc trả kết quả ngay. Cần thiết kế transaction ngắn, thứ tự khóa ổn định và timeout/deadlock handling.

Lưu ý rằng khóa các hàng hiện có không tự bảo vệ mọi predicate trước INSERT mới. Nếu bất biến là “không có hàng nào được thêm vào khoảng này” hoặc tổng của mọi hàng không vượt ngưỡng, cần hiểu range/predicate locking và isolation level; có thể cần `SERIALIZABLE`, guard row hoặc constraint phù hợp.

### Muốn thất bại ngay thay vì chờ

`NOWAIT` hữu ích khi caller cần biết ngay rằng không thể lấy đủ khóa:

```sql
SELECT invoice_id, amount
FROM invoice
WHERE status = 'UNPAID'
ORDER BY invoice_id
FOR UPDATE NOWAIT;
```

Nếu gặp xung đột, database báo lỗi thay vì trả một tập con. Ứng dụng có thể rollback và retry toàn bộ thao tác sau, hoặc trả trạng thái “đang bận”. Đây là lựa chọn rõ ràng hơn `SKIP LOCKED` khi thiếu bất kỳ hàng nào cũng khiến nghiệp vụ không thể tiếp tục.

## 6. `SKIP LOCKED` không phải cách thay thế cho pagination

Một lỗi phổ biến là dùng `LIMIT` và `SKIP LOCKED` để phân trang một danh sách mà người dùng cần duyệt đầy đủ. Nhưng các hàng bị khóa có thể bị bỏ qua trong trang hiện tại; trạng thái khóa có thể thay đổi giữa các lần truy vấn.

Ví dụ:

```sql
SELECT order_id
FROM orders
WHERE status = 'PENDING'
ORDER BY order_id
LIMIT 20
FOR UPDATE SKIP LOCKED;
```

Nếu 5 hàng đầu đang bị khóa, truy vấn có thể trả 20 hàng tiếp theo. Ở trang kế tiếp, khi dùng offset hoặc cursor không tính đến những hàng bị bỏ qua, kết quả có thể thiếu, trùng hoặc thay đổi thứ tự tùy cách phân trang và trạng thái concurrent.

Ngay cả khi một lượt quét sau này có thể nhìn thấy các hàng vừa được mở khóa, điều đó không bảo đảm một export cụ thể đã chứa đủ mọi hàng trong một snapshot. `SKIP LOCKED` được thiết kế để phân phối công việc khả dụng, không phải để tạo một snapshot đầy đủ và ổn định.

Với export hoặc báo cáo dài, hãy cân nhắc:

- Dùng snapshot/transaction phù hợp để các trang nhìn cùng một tập dữ liệu.
- Dùng keyset pagination theo khóa ổn định thay vì offset lớn.
- Tạo danh sách ID hoặc snapshot dữ liệu tại thời điểm bắt đầu export nếu yêu cầu nghiệp vụ cần một mốc rõ ràng.
- Đóng transaction/cursor đúng lúc để tránh giữ snapshot lâu và gây áp lực MVCC.
- Nếu cần xử lý từng hàng, dùng queue/claim riêng và theo dõi trạng thái hoàn tất thay vì coi một lần `SKIP LOCKED` là một lượt duyệt đầy đủ.

## 7. `SKIP LOCKED` có thể tạo starvation

Giả sử job có priority cao luôn bị một worker giữ rất lâu. Các worker khác liên tục dùng `SKIP LOCKED` và xử lý những job phía sau. Job ưu tiên cao đó có thể bị bỏ qua nhiều vòng và chờ rất lâu trước khi được xử lý.

Đây là starvation: một hàng liên tục không được chọn dù vẫn thỏa điều kiện.

Các nguyên nhân thường gặp:

- Worker claim job rồi chết hoặc treo, transaction/lock được giữ lâu.
- Job ưu tiên cao luôn bị khóa khi worker khác quét.
- Một nhóm job có thời gian xử lý rất dài.
- Ordering ưu tiên cố định khiến các hàng ít ưu tiên liên tục bị lùi.
- Nhiều worker quét cùng một vùng key và thường xuyên bỏ qua cùng các hàng.

Các biện pháp giảm starvation:

1. Giữ transaction claim ngắn; commit trạng thái `PROCESSING` rồi xử lý ngoài transaction.
2. Dùng lease (`claimed_at`, `lease_until`) để phục hồi job bị worker bỏ dở.
3. Tăng priority theo thời gian chờ (aging) nếu nghiệp vụ cho phép.
4. Giới hạn thời gian xử lý và số lần retry.
5. Theo dõi tuổi job `READY` lâu nhất, không chỉ throughput tổng.
6. Chia queue theo loại công việc hoặc tenant nếu một nhóm job nóng làm nghẽn nhóm khác.

`SKIP LOCKED` không tự bảo đảm fairness hoặc thứ tự xử lý toàn cục. `ORDER BY` xác định thứ tự ưu tiên trong những hàng truy vấn có thể khóa, nhưng hàng bị khóa vẫn có thể bị bỏ qua.

## 8. Không giữ row lock trong suốt thời gian xử lý job

Một thiết kế queue thường chỉ cần khóa để claim job, sau đó commit trạng thái claim. Không nên giữ transaction và row lock trong lúc worker gọi HTTP, xử lý file hoặc chạy công việc kéo dài.

Mẫu nên dùng:

```text
Transaction ngắn:
  chọn job chưa claim bằng SKIP LOCKED
  cập nhật status = PROCESSING, worker_id, lease_until
COMMIT

Xử lý job ngoài transaction

Transaction ngắn:
  xác nhận worker/lease còn hợp lệ
  ghi kết quả và status = DONE
COMMIT
```

Nếu worker chết sau khi claim nhưng trước khi hoàn tất, lease hết hạn cho phép worker khác claim lại. Vì job có thể chạy hơn một lần, tác dụng nghiệp vụ của job phải idempotent hoặc có idempotency key riêng.

Nếu xử lý job và cập nhật kết quả nằm trong một transaction dài, worker có thể giữ khóa lâu, làm worker khác phải bỏ qua nhiều hàng và tăng nguy cơ starvation. Cũng có thể gây áp lực lock, undo/version và connection pool.

## 9. Cần phân biệt “đang bị khóa” với “không thỏa điều kiện”

Kết quả không có hàng từ một truy vấn `SKIP LOCKED` không có nghĩa không còn dữ liệu phù hợp. Có ít nhất ba khả năng:

- Không có hàng nào thỏa predicate.
- Có hàng thỏa predicate nhưng tất cả đều đang bị khóa.
- Có một số hàng thỏa predicate và một số hàng bị khóa; truy vấn trả về phần khóa được.

Vì vậy, API lấy job không nên diễn giải kết quả rỗng thành “queue đã hoàn toàn trống” nếu hệ thống có thể có job đang được worker khác giữ. Có thể trả trạng thái “hiện không có job khả dụng” hoặc chờ/backoff rồi thử lại.

Nếu nghiệp vụ cần biết chính xác queue còn bao nhiêu job chưa hoàn tất, dùng truy vấn thống kê riêng với semantics đọc phù hợp; không suy ra tổng queue từ batch claim trả về.

## 10. `SKIP LOCKED` không bảo vệ bất biến tổng hoặc predicate

Một truy vấn dùng `SKIP LOCKED` chỉ tránh chờ các row lock mà nó gặp. Nó không cung cấp một cơ chế khóa toàn bộ predicate, không bảo vệ hàng chưa tồn tại và không bảo đảm mọi hàng trong nhóm đều đã được xem xét.

Ví dụ kiểm tra số lượng reservation:

```sql
SELECT reservation_id
FROM reservation
WHERE room_id = 7
FOR UPDATE SKIP LOCKED;
```

Nếu một reservation đang bị khóa, truy vấn bỏ qua nó. Nếu ứng dụng đếm các hàng trả về rồi kết luận phòng còn chỗ, quyết định có thể sai vì số lượng reservation thực tế lớn hơn số hàng đã nhận.

Để bảo vệ bất biến sức chứa, cân nhắc:

- Khóa hàng guard đại diện cho phòng rồi tính tổng theo snapshot phù hợp.
- Dùng một hàng tổng hợp `reserved_count` và UPDATE có điều kiện.
- Dùng constraint phù hợp nếu quy tắc có thể biểu diễn ở database.
- Dùng `SERIALIZABLE` khi bất biến phụ thuộc predicate nhiều hàng và cần database phát hiện lịch không tuần tự hóa được.

Nếu nghiệp vụ cần khóa đầy đủ mọi reservation hiện tại, hãy dùng locking read có chờ khóa và thiết kế cả việc ngăn INSERT mới vào predicate bằng cơ chế thích hợp. `SKIP LOCKED` không thể thay thế bước này.

## 11. Khác biệt giữa các hệ quản trị

Không nên giả định cú pháp và hành vi `SKIP LOCKED` giống nhau giữa mọi engine.

| Hệ quản trị | Cơ chế | Lưu ý quan trọng |
| --- | --- | --- |
| PostgreSQL | `FOR UPDATE SKIP LOCKED` và các locking clause liên quan | Trả view không nhất quán, phù hợp queue; vẫn có thể chờ table-level lock |
| MySQL/InnoDB | `SELECT ... FOR UPDATE SKIP LOCKED` hoặc locking read phù hợp | Chỉ áp dụng cho locking read; bỏ qua row lock nhưng table-level lock vẫn có thể chờ; kiểm tra version/replication |
| Oracle | `SELECT ... FOR UPDATE SKIP LOCKED` | Dùng cho nhiều consumer queue; kết quả có thể bỏ qua hàng bị khóa |
| SQL Server | `READPAST` kết hợp `UPDLOCK` và thường `ROWLOCK` | Không giống hoàn toàn; không bỏ qua page lock và có điều kiện isolation/RCSI |
| SQLite | Không có cú pháp row-level `SKIP LOCKED` tương đương | Mô hình khóa ghi khác; SQLite chỉ có một writer tại một thời điểm |

Một số engine có thể vẫn phải chờ table-level lock, metadata lock hoặc tài nguyên khác dù dùng `SKIP LOCKED`. Tùy chọn này chỉ xử lý một loại xung đột row lock; không phải cam kết truy vấn sẽ không bao giờ chờ.

## 12. Chọn cách truy vấn theo yêu cầu nghiệp vụ

| Yêu cầu | Cách tiếp cận phù hợp | Vì sao |
| --- | --- | --- |
| Nhiều worker lấy job độc lập, mỗi worker nhận phần khả dụng | `SKIP LOCKED` hoặc cơ chế tương đương | Không cần chờ job worker khác đang giữ |
| Đọc tất cả hóa đơn trong một snapshot | SELECT thông thường với isolation phù hợp | MVCC cung cấp phiên bản snapshot; không loại hàng bị khóa |
| Khóa tất cả hàng đang thỏa predicate để cập nhật | Locking read có chờ khóa | Không âm thầm bỏ hàng; cần xử lý lock wait/deadlock |
| Không thể chờ khi khóa bận | `NOWAIT` và retry/fail rõ ràng | Caller biết không thể lấy đủ tập khóa |
| Kiểm tra bất biến tổng trên nhiều hàng | Guard, conditional update hoặc SERIALIZABLE | Cần bảo vệ predicate/tổng, không chỉ lấy các hàng khóa được |
| Export đầy đủ và ổn định | Snapshot, materialized ID set hoặc export mechanism | Tránh bỏ sót và thay đổi tập dữ liệu giữa các trang |
| Queue cần biết chính xác số job còn lại | Truy vấn thống kê riêng; không dùng số hàng claim được | Batch claim có thể bỏ qua job đang khóa |

## 13. Kiểm thử để thấy sự khác nhau

Hãy dùng hai connection độc lập để tạo lock conflict có kiểm soát.

### Kiểm thử `SKIP LOCKED` trả tập con

1. Tạo 5 hàng có cùng trạng thái `READY`.
2. T1 bắt đầu transaction và khóa hàng số 2 bằng `FOR UPDATE`.
3. T2 chạy truy vấn `FOR UPDATE SKIP LOCKED` trên cả 5 hàng.
4. Xác nhận T2 trả 4 hàng, không có hàng 2 và không báo lỗi vì hàng đó bị khóa.
5. Rollback hoặc commit T1.
6. Chạy truy vấn mới và xác nhận hàng 2 có thể được lấy khi không còn bị khóa.

### Kiểm thử truy vấn khóa có chờ

1. T1 khóa hàng số 2.
2. T2 chạy `FOR UPDATE` không có `SKIP LOCKED`.
3. Xác nhận T2 chờ theo lock timeout.
4. Commit T1.
5. Xác nhận T2 tiếp tục và lấy được hàng số 2.

### Kiểm thử `NOWAIT`

1. T1 khóa hàng số 2.
2. T2 chạy locking read với `NOWAIT`.
3. Xác nhận T2 nhận lỗi lock conflict ngay thay vì trả tập con.
4. Rollback transaction T2 nếu engine đánh dấu transaction lỗi.

### Kiểm thử báo cáo cần đầy đủ

1. T1 khóa và cập nhật một hàng nhưng chưa commit.
2. T2 chạy SELECT thông thường để đọc snapshot.
3. Xác nhận T2 nhìn thấy phiên bản đã commit phù hợp với isolation level, hoặc chờ theo semantics engine.
4. Chạy truy vấn có `SKIP LOCKED` trong test riêng và xác nhận tập kết quả có thể thiếu hàng.
5. Đảm bảo code báo cáo không dùng kết quả tập con đó để tính tổng chính thức.

### Kiểm thử starvation và lease

1. Giữ một job ở đầu danh sách trong transaction lâu.
2. Cho nhiều worker khác claim các job phía sau bằng `SKIP LOCKED`.
3. Quan sát tuổi job bị bỏ qua và số lần retry.
4. Giải phóng hoặc cho lease hết hạn.
5. Xác nhận job cuối cùng được claim và xử lý đúng một lần theo idempotency.

Kiểm thử cần chạy trên engine/version thực tế. Cơ chế lock, isolation, hint và thời điểm báo lỗi khác nhau giữa các hệ quản trị.

## 14. Những lỗi thiết kế thường gặp

- **Dùng `SKIP LOCKED` cho báo cáo:** kết quả có thể thiếu hàng nhưng truy vấn vẫn thành công.
- **Dùng số hàng claim được làm tổng số job:** batch có thể bỏ qua job đang bị khóa.
- **Dùng nó cho kiểm tra tồn kho hoặc sức chứa:** hàng bị khóa có thể chứa dữ liệu cần thiết để bảo vệ bất biến.
- **Dùng nó cho export/pagination:** trạng thái khóa thay đổi giữa các trang, khiến lượt duyệt không đầy đủ hoặc không ổn định.
- **Nghĩ rằng không có kết quả nghĩa là queue trống:** có thể mọi hàng phù hợp đang được worker khác giữ.
- **Giữ transaction mở trong lúc xử lý job:** lock bị giữ lâu, worker khác bỏ qua hàng và có thể gây starvation.
- **Cho rằng `SKIP LOCKED` không bao giờ chờ:** table-level, metadata hoặc lock khác vẫn có thể khiến truy vấn chờ.
- **Coi SQL Server `READPAST` giống hệt:** nó có giới hạn với page lock và isolation/RCSI.
- **Không có lease hoặc recovery:** worker chết có thể làm job bị giữ hoặc mắc kẹt nếu transaction/claim không được thiết kế phục hồi.
- **Không có idempotency:** job có thể được xử lý lại sau lease expiry hoặc worker crash.

## 15. Quy trình ra quyết định

Trước khi thêm `SKIP LOCKED`, hãy trả lời lần lượt:

1. Kết quả có được phép thiếu những hàng đang bị khóa không?
2. Nếu trả về 0 hàng, ứng dụng có phân biệt được queue trống với queue đang bận không?
3. Có cần một snapshot đầy đủ và ổn định không?
4. Có cần khóa tất cả hàng thỏa predicate hay chỉ claim một phần công việc?
5. Nếu cần đầy đủ, có thể dùng SELECT snapshot, locking read có chờ hoặc `NOWAIT` không?
6. Nếu dùng cho queue, claim và cập nhật trạng thái có nằm trong cùng transaction không?
7. Worker chết thì lease/recovery hoạt động thế nào?
8. Job retry có idempotent không?
9. Có nguy cơ starvation hoặc ưu tiên cố định làm một hàng bị bỏ qua lâu không?
10. Engine/version có hỗ trợ đúng cú pháp và semantics đang giả định không?

Nếu câu trả lời cho câu đầu là “không, bắt buộc phải có đầy đủ mọi hàng”, không dùng `SKIP LOCKED` cho truy vấn đó. Nếu mục tiêu là “lấy một batch công việc hiện có thể claim mà không chờ worker khác”, `SKIP LOCKED` có thể là lựa chọn phù hợp.

## 16. Những điểm cần ghi nhớ

- `SKIP LOCKED` bỏ qua hàng đang bị khóa xung đột và trả về những hàng còn lại có thể khóa; truy vấn có thể thành công nhưng trả tập con.
- Nó phù hợp với queue nhiều worker khi mỗi worker chỉ cần claim một phần công việc khả dụng.
- Không dùng nó cho báo cáo, export, đối soát, tổng hợp hoặc kiểm tra bất biến cần tập kết quả đầy đủ.
- `NOWAIT` báo lỗi khi không lấy được khóa; locking read mặc định chờ; `SKIP LOCKED` bỏ qua. Ba lựa chọn có semantics khác nhau.
- Nếu chỉ cần đọc snapshot, SELECT thông thường với isolation phù hợp thường không cần bỏ hàng chỉ vì writer đang giữ row lock.
- Nếu cần khóa tất cả hàng, dùng locking read có chờ hoặc `NOWAIT` và xử lý lỗi; với predicate nhiều hàng cần thêm guard/range/predicate lock hoặc SERIALIZABLE phù hợp.
- `LIMIT` kết hợp `SKIP LOCKED` có thể trả ít hơn giới hạn và không bảo đảm pagination đầy đủ.
- Hàng bị bỏ qua có thể bị starvation; theo dõi tuổi job, dùng lease và chính sách fairness phù hợp.
- Claim job và đổi trạng thái phải nằm trong cùng transaction; không giữ row lock trong lúc xử lý công việc kéo dài.
- Worker có thể chạy lại job sau crash/lease expiry, vì vậy tác dụng nghiệp vụ cần idempotent.
- SQL Server `READPAST` là cơ chế tương tự nhưng có giới hạn khác, đặc biệt với page lock và RCSI.
- Một số engine vẫn có thể chờ table-level hoặc loại khóa khác; `SKIP LOCKED` không phải bảo đảm truy vấn không bao giờ chờ.
