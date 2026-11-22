# Chọn và đánh dấu công việc trong cùng giao dịch

Trong hệ thống xử lý hàng đợi (*database-backed job queue*), nhiều worker có thể cùng tìm công việc đang chờ trong một bảng. Mỗi worker cần chọn một công việc, đánh dấu rằng mình đã nhận công việc đó, rồi mới xử lý. Nếu bước chọn và bước đánh dấu được thực hiện tách rời, hai worker có thể cùng nhìn thấy một hàng ở trạng thái `READY` và cùng xử lý nó.

Cách bảo vệ quan trọng là **chọn hàng và đánh dấu quyền sở hữu trong cùng một transaction**. Worker lấy khóa trên hàng được chọn, cập nhật trạng thái và thông tin claim, sau đó commit. Trong lúc transaction giữ khóa, worker khác không thể lấy cùng hàng theo cùng giao thức. Sau commit, trạng thái mới cho biết công việc đã được nhận.

Transaction claim nên ngắn: nó chỉ chọn và đánh dấu công việc. Sau khi commit, worker mới thực hiện xử lý dài hoặc gọi dịch vụ bên ngoài. Cơ chế lease, retry và idempotency sẽ giúp hệ thống phục hồi khi worker bị dừng hoặc thực hiện lại cùng công việc.

## 1. Vì sao chọn và đánh dấu phải đi cùng nhau?

Giả sử bảng `job_queue` có một công việc:

| id | status | payload |
|---:|---|---|
| 501 | READY | Gửi hóa đơn cho đơn hàng 9001 |

Nếu hai worker chỉ đọc công việc rồi cập nhật trạng thái trong hai transaction riêng, lịch thực thi có thể như sau:

```text
Worker A                              Worker B
----------------------------------------------------------------
SELECT job 501, thấy READY
                                      SELECT job 501, cũng thấy READY
UPDATE job 501 -> RUNNING
                                      UPDATE job 501 -> RUNNING
COMMIT                                COMMIT
Xử lý job 501                         Xử lý job 501
```

Cả hai worker đều có thể nghĩ rằng mình đã nhận công việc. Việc kiểm tra `status = 'READY'` ở bước đọc không bảo vệ được quyền sở hữu nếu không có khóa hoặc thao tác cập nhật nguyên tử bao trùm cả quá trình nhận việc.

Với transaction claim đúng cách:

```text
Worker A                              Worker B
----------------------------------------------------------------
BEGIN
SELECT job 501 FOR UPDATE
                                      BEGIN
                                      SELECT ... SKIP LOCKED
                                      Bỏ qua job 501 đang bị khóa
UPDATE job 501 -> RUNNING
COMMIT
Xử lý job 501
```

Worker B có thể nhận một hàng khác hoặc không nhận được công việc nào. Khi A commit, hàng 501 đã ở trạng thái `RUNNING`, nên không còn thỏa điều kiện chọn `READY`.

## 2. Mô hình dữ liệu hàng đợi

Một bảng hàng đợi có thể lưu trạng thái, thời điểm sẵn sàng, số lần thử và thông tin worker đang giữ quyền xử lý.

```sql
CREATE TABLE job_queue (
    id BIGINT PRIMARY KEY,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMP NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    claimed_by VARCHAR(100),
    claim_token VARCHAR(100),
    claimed_at TIMESTAMP,
    lease_until TIMESTAMP,
    completed_at TIMESTAMP,
    last_error_code VARCHAR(100),
    created_at TIMESTAMP NOT NULL
);
```

Các trạng thái thường dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| `READY` | Công việc sẵn sàng được worker nhận |
| `RUNNING` | Đã được một worker claim và đang xử lý |
| `SUCCEEDED` | Đã hoàn tất thành công |
| `RETRY_WAIT` | Thất bại tạm thời, chờ đến thời điểm retry |
| `DEAD` | Hết số lần thử hoặc lỗi không thể tự phục hồi |
| `CANCELLED` | Công việc đã bị hủy theo nghiệp vụ |

`available_at` cho phép lên lịch công việc hoặc retry trong tương lai. `attempt_count` đếm số lần worker đã nhận và bắt đầu xử lý theo quy ước của hệ thống. `claimed_by` cho biết worker nào đang giữ quyền xử lý. `claim_token` là token duy nhất cho lần claim hiện tại; nó giúp ngăn worker cũ cập nhật kết quả sau khi quyền sở hữu đã chuyển sang worker khác. `lease_until` là thời điểm quyền claim hết hạn nếu worker không gia hạn.

Không nhất thiết mọi queue đều cần tất cả các cột. Hãy chọn dữ liệu đủ để bảo vệ quyền claim, phục hồi worker bị dừng và theo dõi kết quả.

## 3. Quy trình claim trong một transaction

Quy trình cơ bản gồm các bước:

1. Mở transaction ngắn.
2. Chọn một hoặc một nhóm nhỏ hàng `READY` đến hạn xử lý, đồng thời khóa các hàng được chọn.
3. Cập nhật chúng thành `RUNNING`, tăng số lần thử và ghi worker/token/lease.
4. Commit để công bố quyền sở hữu.
5. Chỉ sau commit mới xử lý payload hoặc gọi dịch vụ bên ngoài.

```text
BEGIN
  chọn hàng READY và khóa hàng đó
  đánh dấu RUNNING, ghi claim token và lease
COMMIT
       |
       v
Worker thực hiện công việc bên ngoài transaction claim
       |
       +-- thành công --> cập nhật SUCCEEDED bằng claim token
       |
       +-- lỗi tạm thời --> RETRY_WAIT và đặt available_at
       |
       +-- lỗi vĩnh viễn --> DEAD
```

Nếu worker chết trước khi transaction claim commit, thay đổi trạng thái bị rollback và công việc vẫn có thể được worker khác nhận. Nếu claim đã commit nhưng worker chết khi đang xử lý, hàng có thể ở `RUNNING`; lease và quy trình phục hồi sẽ đưa công việc trở lại hàng đợi khi quyền claim hết hạn.

## 4. PostgreSQL: SELECT FOR UPDATE SKIP LOCKED rồi UPDATE

PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED`, phù hợp cho nhiều worker cùng lấy các hàng khác nhau từ một queue.

```sql
BEGIN;

-- Chọn và khóa một job đang sẵn sàng.
SELECT id, payload
FROM job_queue
WHERE status = 'READY'
  AND available_at <= clock_timestamp()
ORDER BY priority DESC, available_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Giả sử ứng dụng nhận được id đã chọn.
UPDATE job_queue
SET status = 'RUNNING',
    claimed_by = :worker_id,
    claim_token = :claim_token,
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '60 seconds',
    attempt_count = attempt_count + 1
WHERE id = :job_id
  AND status = 'READY';

COMMIT;
```

`SELECT ... FOR UPDATE` giữ khóa trên hàng được chọn đến khi transaction kết thúc. `SKIP LOCKED` cho phép worker bỏ qua hàng đang bị worker khác khóa thay vì chờ. Điều kiện `status = 'READY'` được kiểm tra lại ở câu `UPDATE` như một lớp bảo vệ bổ sung; ứng dụng nên xác nhận đúng một hàng được cập nhật trước khi commit.

Có thể gộp bước chọn và đánh dấu thành một câu lệnh PostgreSQL dùng CTE và `UPDATE ... RETURNING`:

```sql
BEGIN;

WITH candidate AS (
    SELECT id
    FROM job_queue
    WHERE status = 'READY'
      AND available_at <= clock_timestamp()
    ORDER BY priority DESC, available_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS q
SET status = 'RUNNING',
    claimed_by = :worker_id,
    claim_token = :claim_token,
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '60 seconds',
    attempt_count = q.attempt_count + 1
FROM candidate
WHERE q.id = candidate.id
RETURNING q.id, q.payload, q.claim_token, q.lease_until;

COMMIT;
```

Ứng dụng nhận hàng được claim qua `RETURNING`. Nếu không có hàng nào được trả về, hiện tại không có công việc đủ điều kiện và chưa bị worker khác khóa để lấy. Có thể đợi một khoảng ngắn hoặc nhận công việc khác.

`clock_timestamp()` trả thời điểm thực tại lúc gọi, phù hợp khi muốn lease bắt đầu gần thời điểm cập nhật. `CURRENT_TIMESTAMP` trong PostgreSQL phản ánh thời điểm bắt đầu transaction; nếu transaction kéo dài, giá trị này không thay đổi trong transaction đó. Với transaction claim ngắn, khác biệt thường nhỏ, nhưng cần hiểu rõ khi tính lease.

## 5. MySQL InnoDB: locking read trong transaction

MySQL InnoDB hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED` trong các phiên bản phù hợp. Cần đặt câu lệnh đọc khóa và cập nhật trạng thái trong cùng transaction.

```sql
START TRANSACTION;

SELECT id, payload
FROM job_queue
WHERE status = 'READY'
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY priority DESC, available_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Ứng dụng lấy job_id từ kết quả SELECT.
UPDATE job_queue
SET status = 'RUNNING',
    claimed_by = ?,
    claim_token = ?,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 60 SECOND),
    attempt_count = attempt_count + 1
WHERE id = ?
  AND status = 'READY';

COMMIT;
```

InnoDB giữ khóa hàng cho đến khi transaction kết thúc. Khi `SKIP LOCKED` được dùng, worker bỏ qua hàng bị khóa và tiếp tục tìm hàng khác. Cần kiểm tra phiên bản MySQL, engine của bảng và mức cô lập thực tế; cú pháp này không áp dụng cho mọi storage engine.

Nếu `SELECT` không trả hàng nào, worker không có job để claim trong lượt này. Nếu `UPDATE` không ảnh hưởng đúng một hàng, không nên coi claim là thành công; hãy rollback và điều tra trạng thái hoặc logic cập nhật.

## 6. SQL Server: UPDATE với UPDLOCK và READPAST

SQL Server có thể chọn và đánh dấu công việc bằng một câu `UPDATE` trên CTE. `UPDLOCK` yêu cầu update lock trong lúc chọn, `READPAST` cho phép bỏ qua một số hàng đang bị khóa, còn `OUTPUT` trả về hàng vừa được claim.

```sql
BEGIN TRANSACTION;

;WITH candidate AS (
    SELECT TOP (1) *
    FROM dbo.JobQueue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE Status = 'READY'
      AND AvailableAt <= SYSUTCDATETIME()
    ORDER BY Priority DESC, AvailableAt, Id
)
UPDATE candidate
SET Status = 'RUNNING',
    ClaimedBy = @WorkerId,
    ClaimToken = @ClaimToken,
    ClaimedAt = SYSUTCDATETIME(),
    LeaseUntil = DATEADD(SECOND, 60, SYSUTCDATETIME()),
    AttemptCount = AttemptCount + 1
OUTPUT inserted.Id, inserted.Payload, inserted.ClaimToken, inserted.LeaseUntil;

COMMIT TRANSACTION;
```

Đây là mẫu dành cho SQL Server; cần kiểm tra điều kiện isolation level và cấu hình `READ_COMMITTED_SNAPSHOT` trước khi áp dụng `READPAST`. Trong một số cấu hình, `READPAST` cần kết hợp hint `READCOMMITTEDLOCK`. `READPAST` bỏ qua row lock nhưng không nhất thiết bỏ qua page lock; `ROWLOCK` chỉ là yêu cầu gợi ý cho bộ máy khóa, không phải bảo đảm tuyệt đối rằng chỉ khóa hàng.

## 7. Điều gì xảy ra nếu chỉ SELECT rồi đánh dấu ở transaction khác?

Tách hai bước sang hai transaction tạo ra khoảng trống mà worker khác có thể lấy cùng một công việc.

```text
Transaction A                         Transaction B
----------------------------------------------------------------
BEGIN
SELECT job 501 WHERE READY
COMMIT
                                       BEGIN
                                       SELECT job 501 WHERE READY
                                       COMMIT
BEGIN
UPDATE job 501 SET RUNNING
COMMIT
                                       BEGIN
                                       UPDATE job 501 SET RUNNING
                                       COMMIT
```

Thêm điều kiện `WHERE status = 'READY'` ở câu `UPDATE` giúp phát hiện một worker đã claim trước, nhưng nếu ứng dụng bỏ qua số hàng bị cập nhật hoặc vẫn xử lý payload đã đọc, worker thua cuộc vẫn có thể thực thi công việc. Vì vậy, phải kiểm tra kết quả cập nhật và chỉ xử lý khi transaction claim thành công.

Quy tắc là: **không xử lý payload chỉ vì đã đọc được nó; chỉ xử lý sau khi đã đánh dấu quyền sở hữu thành công và commit transaction claim.**

## 8. Vì sao không nên giữ transaction mở trong lúc xử lý job?

Một worker có thể cần vài giây hoặc vài phút để gửi email, tạo báo cáo, gọi API hoặc xử lý tệp. Nếu giữ transaction claim mở trong toàn bộ thời gian đó, hàng vẫn bị khóa và connection database bị chiếm dụng.

Hậu quả có thể gồm:

- Worker khác phải chờ hoặc bỏ qua hàng lâu hơn cần thiết.
- Khóa được giữ lâu, làm tăng nguy cơ deadlock và lock timeout.
- Connection pool cạn khi nhiều job chạy song song.
- Transaction dài giữ snapshot cũ hoặc làm chậm quá trình dọn dẹp phiên bản trong hệ quản trị MVCC.
- Worker chết có thể giữ transaction và khóa đến khi database phát hiện session mất kết nối.

Vì vậy, hãy tách thành hai giai đoạn:

1. **Claim transaction:** chọn và đánh dấu `RUNNING`, ghi lease/token, commit nhanh.
2. **Processing phase:** thực hiện công việc sau commit; khi hoàn tất, mở transaction mới để ghi kết quả.

Ngoại lệ có thể tồn tại khi toàn bộ công việc chỉ là thao tác database rất ngắn và cần cùng transaction với việc claim. Nhưng với queue worker thực hiện tác vụ dài hoặc gọi dịch vụ ngoài, giữ transaction mở trong lúc xử lý thường là lựa chọn không phù hợp.

## 9. Claim token bảo vệ quyền sở hữu khi worker cũ quay lại

Giả sử worker A claim job 501 với token `token-A`. A bị treo lâu hơn lease. Hệ thống phục hồi job và worker B claim lại với token `token-B`. Sau đó A hoạt động trở lại và cố đánh dấu job thành công.

Nếu chỉ kiểm tra `id = 501 AND status = 'RUNNING'`, A có thể ghi đè kết quả của B. Cần kiểm tra cả token hiện hành:

```sql
UPDATE job_queue
SET status = 'SUCCEEDED',
    completed_at = CURRENT_TIMESTAMP,
    claimed_by = NULL,
    claim_token = NULL,
    lease_until = NULL
WHERE id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Worker chỉ được xem là đã hoàn tất nếu câu `UPDATE` ảnh hưởng đúng một hàng. Nếu không có hàng nào, claim token đã hết hiệu lực hoặc job đã chuyển trạng thái; worker cũ không còn quyền cập nhật.

Token phải được tạo mới cho mỗi lần claim. Không tái sử dụng token cũ sau khi job được đưa trở lại `READY`.

Với hệ thống cần ngăn cả tác động ghi ở dịch vụ ngoài từ worker cũ, token ngẫu nhiên chỉ bảo vệ cập nhật trong database queue. Dịch vụ đích cần hỗ trợ idempotency hoặc fencing token có thứ tự tăng dần để từ chối thao tác từ worker có quyền sở hữu cũ.

## 10. Lease, heartbeat và phục hồi công việc bị bỏ dở

Lease là khoảng thời gian worker được phép giữ quyền claim mà không cần xác nhận lại. Ví dụ lease 60 giây: nếu worker không hoàn tất hoặc gia hạn trong 60 giây, job có thể được hệ thống phục hồi.

```text
Worker A claim job, lease_until = 10:01:00
       |
       +-- hoàn tất trước 10:01:00 -> đánh dấu SUCCEEDED
       |
       +-- vẫn chạy, heartbeat gia hạn -> lease_until mới
       |
       +-- worker chết, không heartbeat
              |
              v
         lease hết hạn
              |
              v
         recovery worker claim lại job
```

Heartbeat nên gia hạn lease có điều kiện theo token hiện tại:

```sql
UPDATE job_queue
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds'
WHERE id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Cú pháp cộng thời gian phụ thuộc hệ quản trị. Điểm quan trọng là câu cập nhật phải xác nhận worker vẫn giữ đúng claim token. Nếu số hàng cập nhật bằng 0, worker không còn sở hữu job và nên dừng các bước có thể gây tác động mới.

Recovery worker có thể tìm các hàng `RUNNING` đã hết lease, khóa chúng và đưa về `READY` hoặc `DEAD` nếu đã hết số lần thử. Quy trình phục hồi cũng cần cập nhật trạng thái trong transaction để hai recovery worker không cùng xử lý một hàng.

## 11. Retry và số lần thử

Khi job thất bại, cần phân loại lỗi trước khi quyết định retry:

- Lỗi tạm thời như deadlock, timeout hoặc dịch vụ ngoài tạm ngừng có thể retry.
- Lỗi nghiệp vụ như payload sai hoặc đối tượng không tồn tại thường không nên retry vô hạn.
- Khi đạt `max_attempts`, có thể chuyển sang `DEAD` hoặc dead-letter queue để điều tra.

Ví dụ cập nhật lịch retry sau khi worker đã xác định lỗi có thể thử lại:

```sql
UPDATE job_queue
SET status = CASE
        WHEN attempt_count >= max_attempts THEN 'DEAD'
        ELSE 'RETRY_WAIT'
    END,
    available_at = :next_retry_at,
    last_error_code = :error_code,
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL
WHERE id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Nếu còn lượt thử, scheduler hoặc worker có thể chuyển `RETRY_WAIT` thành `READY` khi `available_at` đến hạn, hoặc query claim có thể chọn trực tiếp các trạng thái đến hạn theo thiết kế queue. Cần thống nhất một cách biểu diễn để không có job bị bỏ quên giữa hai trạng thái.

Backoff tăng dần và jitter giúp nhiều worker không cùng retry một dịch vụ đang quá tải. Ghi nhận `attempt_count`, `last_error_code`, `available_at` và thời điểm retry để có thể theo dõi nguyên nhân và thời gian chờ.

## 12. Chọn và đánh dấu theo lô

Một worker có thể claim nhiều job trong một transaction để giảm số lần round-trip tới database. Ví dụ PostgreSQL:

```sql
BEGIN;

WITH candidates AS (
    SELECT id
    FROM job_queue
    WHERE status = 'READY'
      AND available_at <= clock_timestamp()
    ORDER BY priority DESC, available_at, id
    LIMIT 10
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS q
SET status = 'RUNNING',
    claimed_by = :worker_id,
    claim_token = :batch_claim_token,
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '60 seconds',
    attempt_count = q.attempt_count + 1
FROM candidates
WHERE q.id = candidates.id
RETURNING q.id, q.payload, q.claim_token, q.lease_until;

COMMIT;
```

Batch size nên được chọn theo tốc độ xử lý và khả năng của worker. Claim quá nhiều job có thể khiến các job nằm trong bộ nhớ chờ xử lý đến khi lease hết hạn trước khi worker bắt đầu chúng. Với batch, thường nên có claim token riêng cho từng job hoặc một cơ chế định danh batch kết hợp job ID để kiểm soát quyền sở hữu chính xác.

## 13. Tính lũy đẳng: claim một lần không đồng nghĩa thực thi đúng một lần

Transaction claim bảo đảm một job không được hai worker cùng nhận theo cùng một giao thức tại cùng thời điểm. Nó không thể bảo đảm tác động bên ngoài chỉ xảy ra đúng một lần.

Ví dụ worker gửi email thành công, nhưng chết trước khi cập nhật `status = 'SUCCEEDED'`. Lease hết hạn và job được claim lại. Worker mới có thể gửi email lần nữa.

Do đó, queue thường cung cấp ngữ nghĩa **at-least-once delivery**: một công việc có thể được giao lại khi hệ thống không xác định được worker trước đã hoàn tất hay chưa. Tác vụ cần được thiết kế lũy đẳng (*idempotent*) hoặc có cơ chế chống thực thi trùng.

Một cách là dùng job ID hoặc business operation ID làm idempotency key ổn định:

```text
Job ID: 501
Idempotency key: invoice-email:order-9001

Attempt 1 -> gửi yêu cầu với cùng key
Attempt 2 -> gửi lại với cùng key
Attempt 3 -> gửi lại với cùng key

Dịch vụ nhận yêu cầu nhận diện key đã xử lý và trả lại kết quả cũ
thay vì tạo tác động nghiệp vụ lần thứ hai.
```

Không dùng claim token hoặc attempt ID làm idempotency key, vì các giá trị đó thay đổi mỗi lần claim. Idempotency key phải đại diện cho cùng một tác động nghiệp vụ xuyên suốt các lần retry.

Nếu tác động và queue nằm trong cùng database, có thể ghi kết quả nghiệp vụ và đánh dấu job hoàn tất trong cùng transaction. Nếu tác động nằm ở dịch vụ ngoài, cần idempotency API, inbox/deduplication table, transactional outbox hoặc quy trình đối soát phù hợp.

## 14. `SKIP LOCKED` và tính công bằng của hàng đợi

`SKIP LOCKED` tăng khả năng xử lý song song vì worker không phải chờ hàng đang bị khóa. Tuy nhiên, kết quả truy vấn không phải danh sách đầy đủ của mọi job đủ điều kiện tại thời điểm đó.

Một job có thể liên tục bị bỏ qua nếu nó bị khóa lâu hoặc nằm sau các hàng thường xuyên được chọn. Hệ thống cần theo dõi:

- Tuổi của job `READY` lâu nhất.
- Số job `RUNNING` quá hạn lease.
- Số lần job được claim và retry.
- Job có priority cao nhưng không được xử lý.
- Thời gian từ `available_at` đến lúc claim thực tế.

Sắp xếp theo `priority`, `available_at` và `id` giúp thứ tự chọn ổn định hơn, nhưng không bảo đảm tuyệt đối công bằng khi có `SKIP LOCKED`. Nếu nghiệp vụ yêu cầu FIFO nghiêm ngặt, cần cân nhắc cơ chế điều phối khác vì worker song song và bỏ qua hàng bị khóa có thể làm thứ tự hoàn tất khác thứ tự tạo.

Không nên dùng `SKIP LOCKED` cho truy vấn báo cáo cần nhìn thấy tất cả hàng. Nó dành cho tác vụ lấy việc, nơi bỏ qua hàng đang được worker khác xử lý là hành vi mong muốn.

## 15. Chỉ mục và kích thước transaction claim

Queue thường được truy vấn theo trạng thái và thời điểm sẵn sàng. Một chỉ mục phù hợp có thể giảm số hàng phải quét trước khi chọn job:

```sql
-- Ví dụ định hướng cho PostgreSQL; thiết kế thực tế phụ thuộc query plan.
CREATE INDEX idx_job_queue_ready
ON job_queue (status, available_at, priority DESC, id);
```

Chỉ mục này chỉ là điểm bắt đầu. Thứ tự cột tối ưu phụ thuộc điều kiện lọc, thứ tự ưu tiên, phân bố trạng thái và hệ quản trị. Hãy kiểm tra execution plan với dữ liệu đại diện. Nếu phần lớn hàng đã ở `SUCCEEDED` hoặc `DEAD`, partial index trên hàng đang hoạt động có thể hữu ích ở hệ quản trị hỗ trợ.

Giữ transaction claim ngắn và batch size vừa phải. Một câu truy vấn claim quét quá nhiều hàng hoặc khóa một batch lớn có thể làm worker khác khó tìm việc và tạo tranh chấp không cần thiết.

## 16. Các lỗi triển khai thường gặp

- **Đọc trước rồi mới khóa:** tạo khoảng trống để worker khác claim cùng job.
- **Đánh dấu sau khi xử lý:** worker khác có thể nhận cùng job trong lúc worker đầu đang chạy.
- **Không kiểm tra số hàng cập nhật:** worker thua cuộc vẫn xử lý payload dù claim thất bại.
- **Giữ transaction mở trong lúc gọi API:** giữ khóa và connection quá lâu.
- **Không dùng claim token:** worker cũ có thể ghi đè kết quả của worker mới sau khi lease hết hạn.
- **Lease quá ngắn:** job hợp lệ thường xuyên bị reclaim khi worker vẫn đang xử lý.
- **Lease quá dài:** phục hồi worker chết bị chậm.
- **Không có heartbeat cho job dài:** worker đang hoạt động có thể mất lease.
- **Giả định claim đồng nghĩa exactly-once:** tác động ngoài có thể lặp nếu worker chết sau tác động nhưng trước khi ghi hoàn tất.
- **Retry không giới hạn:** job lỗi liên tục chiếm tài nguyên và che khuất lỗi dữ liệu hoặc lỗi nghiệp vụ.
- **Dùng SKIP LOCKED cho báo cáo:** kết quả bị thiếu các hàng đang khóa.

## 17. Quy trình thiết kế queue an toàn

Khi xây dựng worker queue dựa trên database, hãy xác định rõ:

1. **Điều kiện chọn:** trạng thái, thời điểm sẵn sàng, priority và thứ tự chọn.
2. **Cơ chế khóa:** `FOR UPDATE SKIP LOCKED`, `UPDLOCK/READPAST` hoặc câu lệnh cập nhật nguyên tử phù hợp hệ quản trị.
3. **Cập nhật claim:** trạng thái `RUNNING`, worker ID, claim token, thời điểm claim, lease và attempt count.
4. **Ranh giới transaction:** chọn và đánh dấu cùng transaction; commit trước khi xử lý công việc dài.
5. **Xác nhận quyền sở hữu:** mọi heartbeat, completion và failure update đều kiểm tra claim token hiện tại.
6. **Phục hồi lease:** phát hiện claim hết hạn, reclaim hoặc đưa job vào dead-letter theo số lần thử.
7. **Tác động lũy đẳng:** dùng idempotency key ổn định và cơ chế deduplication cho side effect.
8. **Quan sát:** theo dõi tuổi job, attempt count, lock wait, lease expiry, retry và final outcome.
9. **Tải thực tế:** chọn batch size, index và lease duration dựa trên thời gian xử lý đo được.

## 18. Những điểm cần nhớ

- Chọn hàng và đánh dấu `RUNNING` phải nằm trong cùng transaction để hai worker không cùng nhận một hàng theo cùng giao thức.
- Khóa hàng trong lúc chọn giúp worker khác bỏ qua hoặc chờ; `SKIP LOCKED` thường phù hợp với queue nhiều worker.
- Chỉ xử lý job sau khi cập nhật claim thành công và transaction đã commit.
- Transaction claim nên ngắn; xử lý dài và gọi dịch vụ ngoài diễn ra sau commit.
- Claim token bảo vệ cập nhật kết quả khỏi worker cũ sau khi lease đã chuyển sang worker khác.
- Lease và heartbeat cho phép phục hồi job khi worker chết hoặc bị treo.
- Queue thường có ngữ nghĩa at-least-once; idempotency cần bảo vệ tác động nghiệp vụ khỏi thực thi trùng.
- `SKIP LOCKED` có thể bỏ qua hàng lâu và không bảo đảm FIFO nghiêm ngặt; cần theo dõi job bị trì hoãn.
- Mọi bước completion, retry hoặc heartbeat phải xác nhận worker vẫn sở hữu claim hiện tại.

Một queue an toàn không chỉ tìm được công việc đang chờ; nó phải ghi nhận quyền sở hữu một cách nguyên tử trước khi worker bắt đầu xử lý. Khi chọn và đánh dấu cùng transaction, kết hợp lease, claim token và idempotency, hệ thống có thể chạy nhiều worker song song mà vẫn phục hồi được khi worker dừng giữa chừng hoặc một công việc cần được thử lại.
