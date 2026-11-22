# Xây dựng hàng đợi cơ sở dữ liệu có quyền xử lý và nhận diện yêu cầu trùng

Một hàng đợi dùng database có thể giúp nhiều worker cùng nhận và xử lý công việc mà không cần một broker riêng. Tuy nhiên, chỉ có bảng `jobs` với cột `status` là chưa đủ. Khi nhiều worker chạy đồng thời, hệ thống phải bảo đảm một job không bị hai worker cùng nhận theo cùng một quyền sở hữu; khi worker chết, job phải có thể được nhận lại; khi client gửi lại cùng yêu cầu, hệ thống phải nhận diện đó là cùng một ý định và không tạo job mới.

Bài tập này xây dựng một hàng đợi database có ba cơ chế phối hợp:

1. **Claim nguyên tử:** worker lấy quyền xử lý một hoặc nhiều job bằng một transaction ngắn và câu lệnh khóa phù hợp.
2. **Lease và fencing token:** quyền xử lý có thời hạn; worker cũ không thể ghi kết quả sau khi quyền đã được chuyển sang worker khác.
3. **Idempotency key:** cùng một yêu cầu enqueue được nhận diện qua nhiều lần gửi; cùng key với payload khác bị từ chối.

Hàng đợi được thiết kế theo mô hình *at-least-once processing*: một job có thể được thực hiện nhiều attempt nếu worker crash hoặc lease hết hạn. Hệ thống bảo vệ quyền sở hữu và trạng thái job trong database; tác dụng phụ bên ngoài cần thêm idempotency key ổn định theo job để tránh thực hiện nghiệp vụ trùng.

## 1. Mục tiêu và bất biến cần bảo vệ

Giả sử ứng dụng nhận yêu cầu tạo thumbnail, gửi báo cáo, đồng bộ dữ liệu hoặc xử lý một đơn hàng. API ghi một job vào database; nhiều worker đọc job sẵn sàng và xử lý song song.

Hệ thống cần giữ các bất biến:

- Một `(queue_name, idempotency_key)` chỉ đại diện cho một yêu cầu nghiệp vụ trong thời hạn lưu deduplication.
- Cùng idempotency key với cùng nội dung trả về cùng `job_id`.
- Cùng idempotency key với payload khác phải trả conflict, không âm thầm đổi nội dung job.
- Một job chỉ có một lease generation hiện hành tại một thời điểm.
- Worker chỉ được gia hạn lease, hoàn tất hoặc báo lỗi nếu vẫn sở hữu đúng generation.
- Worker không giữ transaction database mở trong suốt thời gian thực hiện công việc dài.
- Job hết lease có thể được phục hồi; job vượt số attempt tối đa được chuyển sang dead-letter/terminal state.
- Một lần giao lại hoặc xử lý lại cùng job không được nhân đôi tác dụng nghiệp vụ bên ngoài.
- Mọi chuyển trạng thái đều có điều kiện và được database kiểm tra nguyên tử.

Hai khái niệm cần tách biệt:

- **Job ownership:** worker nào đang có quyền xử lý job trong database.
- **Business idempotency:** một ý định nghiệp vụ đã gây tác dụng bao nhiêu lần ở hệ thống nhận.

Lease giải quyết ownership; idempotency key giải quyết side effect trùng. Một cơ chế không thay thế cơ chế kia.

## 2. State machine của job

Một state machine nhỏ giúp giới hạn các chuyển đổi hợp lệ:

```text
                    claim
             +------------------+
             |                  v
          READY ------------> RUNNING
             ^                  |
             |                  | xử lý thành công + ACK
             |                  v
             |              SUCCEEDED
             |
             | lỗi tạm thời / lease hết hạn
             |
             +------------------+

RUNNING -- lỗi permanent hoặc hết attempt --> DEAD
```

Ý nghĩa:

| Trạng thái | Ý nghĩa |
|---|---|
| `READY` | Có thể được worker claim khi `available_at` đã đến. |
| `RUNNING` | Đang được một worker sở hữu bằng lease còn hiệu lực. |
| `SUCCEEDED` | Công việc đã hoàn tất và kết quả đã được ghi nhận. |
| `DEAD` | Không được tự động thử lại; cần điều tra hoặc replay có kiểm soát. |

Một lỗi tạm thời không nhất thiết chuyển sang `DEAD`. Nếu còn attempt và deadline, job trở lại `READY` với `available_at` ở tương lai để backoff. Lỗi permanent hoặc hết attempt chuyển sang `DEAD`.

Không nên dùng một cột boolean `processed` để đại diện toàn bộ vòng đời. Boolean không thể diễn đạt worker đang giữ lease, thời điểm retry, số attempt, lỗi cuối hoặc job bị đưa vào dead-letter.

## 3. Thiết kế schema

Ví dụ dưới đây dùng PostgreSQL để trình bày đầy đủ. Ứng dụng tạo `job_id` bằng UUID trước khi insert. Payload được lưu dạng `JSONB`; request hash là SHA-256 của nội dung nghiệp vụ đã chuẩn hóa.

### Bảng queue_jobs

```sql
CREATE TABLE queue_jobs (
    job_id UUID PRIMARY KEY,
    queue_name TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY',
    priority INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 8,
    lease_owner TEXT,
    lease_generation BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_queue_jobs_status
        CHECK (status IN ('READY', 'RUNNING', 'SUCCEEDED', 'DEAD')),
    CONSTRAINT ck_queue_jobs_attempts
        CHECK (attempt_count >= 0 AND max_attempts > 0),
    CONSTRAINT ck_queue_jobs_lease
        CHECK (
            (status = 'RUNNING'
             AND lease_owner IS NOT NULL
             AND lease_until IS NOT NULL)
            OR
            (status <> 'RUNNING'
             AND lease_owner IS NULL
             AND lease_until IS NULL)
        )
);
```

`lease_generation` là fencing token tăng dần mỗi khi job được claim. Worker nhận generation từ câu claim và phải gửi lại generation đó khi heartbeat, ACK hoặc báo lỗi. Khi job được claim lần sau, generation mới lớn hơn; worker cũ không thể cập nhật trạng thái bằng generation cũ.

### Bảng queue_requests để nhận diện yêu cầu trùng

Giữ idempotency ledger riêng giúp hệ thống duy trì dấu nhận yêu cầu ngay cả khi job đã được archive hoặc dọn khỏi bảng queue. Bảng này không cần xóa cùng lúc với job:

```sql
CREATE TABLE queue_requests (
    queue_name TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash BYTEA NOT NULL,
    job_id UUID NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (queue_name, idempotency_key),
    UNIQUE (job_id)
);
```

`queue_requests` lưu ánh xạ từ ý định gửi đến job được tạo. Không đặt foreign key cascade từ ledger sang `queue_jobs` nếu muốn giữ dedup record sau khi archive job. Nếu hệ thống giữ toàn bộ job trong cùng bảng suốt thời hạn dedup, có thể thiết kế foreign key theo chính sách lưu trữ.

### Index cho claim và phục hồi lease

```sql
CREATE INDEX ix_queue_jobs_ready
    ON queue_jobs (queue_name, priority DESC, available_at, created_at)
    WHERE status = 'READY';

CREATE INDEX ix_queue_jobs_expired_lease
    ON queue_jobs (lease_until)
    WHERE status = 'RUNNING';
```

Index partial của PostgreSQL chỉ chứa hàng ở trạng thái tương ứng. Nó giúp worker tìm job sẵn sàng và reaper tìm lease hết hạn mà không quét toàn bộ bảng. Index cụ thể cần được kiểm tra bằng execution plan và workload thực tế; thêm index cũng làm tăng chi phí insert/update.

### Vì sao cần request hash?

Idempotency key chỉ đại diện cho cùng một ý định khi payload không đổi. Ứng dụng nên chuẩn hóa những trường nghiệp vụ ảnh hưởng đến kết quả, chẳng hạn loại công việc, tenant, tài nguyên đích và tham số xử lý, rồi tính SHA-256.

Không hash JSON thô nếu thứ tự thuộc tính hoặc khoảng trắng có thể thay đổi giữa các lần serialize. Cùng nội dung logic cần tạo cùng hash. Không đưa trace ID, thời điểm request hoặc header ngẫu nhiên vào hash nếu chúng không làm thay đổi ý nghĩa nghiệp vụ.

## 4. Enqueue: tạo job một lần và trả lại cùng job cho request trùng

API enqueue nhận:

- `queue_name` để xác định loại hàng đợi.
- `idempotency_key` ổn định do client hoặc tầng nghiệp vụ cung cấp.
- `request_hash` được tính từ payload chuẩn hóa.
- `job_id` mới được tạo cho lần enqueue đầu tiên.
- `payload` của công việc.

Việc tạo idempotency record và job phải nằm trong cùng transaction. Nếu insert job thất bại, request ledger cũng rollback; không để lại key trỏ tới job chưa tồn tại.

### Luồng xử lý

```text
BEGIN
  INSERT queue_requests(queue, key, hash, job_id)
    ON CONFLICT DO NOTHING

  Nếu insert thành công:
    INSERT queue_jobs(job_id, queue_name, payload, READY)
    COMMIT
    trả job_id mới

  Nếu key đã tồn tại:
    đọc request_hash và job_id hiện có
    nếu hash khác: ROLLBACK và trả 409 Conflict
    nếu hash giống: COMMIT và trả job_id đã có
```

### Ví dụ PostgreSQL

```sql
BEGIN;

INSERT INTO queue_requests (
    queue_name, idempotency_key, request_hash, job_id
)
VALUES (
    :queueName, :idempotencyKey, :requestHash, :newJobId
)
ON CONFLICT (queue_name, idempotency_key) DO NOTHING
RETURNING job_id;
```

Nếu câu lệnh trả về một hàng, request mới đã claim được key. Tiếp tục tạo job:

```sql
INSERT INTO queue_jobs (
    job_id, queue_name, payload, status,
    priority, available_at, max_attempts
)
VALUES (
    :newJobId, :queueName, CAST(:payload AS JSONB), 'READY',
    :priority, clock_timestamp(), :maxAttempts
);

COMMIT;
```

Nếu câu lệnh đầu không trả hàng, key đã tồn tại. Trong transaction `READ COMMITTED`, truy vấn tiếp theo lấy record đã commit:

```sql
SELECT request_hash, job_id
FROM queue_requests
WHERE queue_name = :queueName
  AND idempotency_key = :idempotencyKey;
```

Ứng dụng so sánh hash:

- Hash giống: trả lại `job_id` cũ và trạng thái hiện tại nếu cần.
- Hash khác: rollback và trả lỗi conflict; không tạo job mới.

Ở mức isolation có snapshot cố định, xử lý cạnh tranh và snapshot có thể khác; ứng dụng cần bắt serialization/retry transaction enqueue theo đúng semantics của PostgreSQL. Không thay thế unique constraint bằng `SELECT` kiểm tra trước rồi mới `INSERT`: hai request đồng thời có thể cùng thấy key chưa tồn tại.

### Kết quả API

| Trường hợp | Kết quả gợi ý |
|---|---|
| Key mới, job được tạo | `202 Accepted` cùng `job_id` và URL tra cứu trạng thái. |
| Cùng key, cùng hash | Trả cùng `job_id`; có thể trả `200` hoặc `202` theo trạng thái job và hợp đồng API. |
| Cùng key, hash khác | `409 Conflict`; caller phải dùng key mới cho ý định nghiệp vụ mới. |
| Payload không hợp lệ | `400`/`422`; không tạo request ledger hoặc job. |

Nếu job đã `SUCCEEDED`, request trùng vẫn phải nhận diện là cùng job và không enqueue lại. Nếu job đã `DEAD`, API nên trả trạng thái của job cũ; việc replay cần một thao tác quản trị hoặc ý định mới có quy tắc rõ ràng.

## 5. Claim job nguyên tử bằng PostgreSQL

Nhiều worker có thể cùng chạy câu tìm job `READY`. Cách sai là đọc danh sách job rồi cập nhật status bằng câu lệnh riêng mà không giữ khóa giữa hai bước:

```text
Worker A: SELECT job 10 là READY
Worker B: SELECT job 10 là READY
Worker A: UPDATE job 10 -> RUNNING
Worker B: UPDATE job 10 -> RUNNING
```

Cả hai worker có thể tin rằng mình sở hữu cùng job. Cần claim trong một transaction với row lock và `SKIP LOCKED`, sau đó cập nhật trạng thái ngay trong transaction đó.

```sql
BEGIN;

WITH picked AS (
    SELECT job_id
    FROM queue_jobs
    WHERE queue_name = :queueName
      AND status = 'READY'
      AND available_at <= clock_timestamp()
      AND attempt_count < max_attempts
    ORDER BY priority DESC, available_at, created_at
    LIMIT :batchSize
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_jobs AS q
SET status = 'RUNNING',
    lease_owner = :workerId,
    lease_generation = q.lease_generation + 1,
    lease_until = clock_timestamp() + (:leaseSeconds * INTERVAL '1 second'),
    attempt_count = q.attempt_count + 1,
    updated_at = clock_timestamp()
FROM picked
WHERE q.job_id = picked.job_id
RETURNING q.job_id,
          q.queue_name,
          q.payload,
          q.attempt_count,
          q.max_attempts,
          q.lease_generation,
          q.lease_until;

COMMIT;
```

`FOR UPDATE SKIP LOCKED` khóa những hàng được chọn. Worker khác bỏ qua các hàng đang bị worker trước khóa và có thể claim các job khác. `UPDATE ... RETURNING` trả payload và generation mới để worker lưu lại làm lease token.

### Claim phải là transaction ngắn

Commit ngay sau khi claim. Worker xử lý payload bên ngoài transaction đó. Không giữ row lock hoặc connection trong lúc gọi HTTP, xử lý file hay chạy thuật toán dài.

```text
Transaction claim: khóa hàng -> RUNNING + lease -> COMMIT
                          |
                          v
                 Xử lý công việc ngoài transaction
                          |
                          v
Transaction ACK/fail: kiểm tra lease generation -> cập nhật -> COMMIT
```

`SKIP LOCKED` ưu tiên throughput cho nhiều worker; nó không bảo đảm thứ tự FIFO tuyệt đối. Một job có thể bị bỏ qua trong lúc worker khác giữ khóa, và job ưu tiên thấp có thể chờ lâu nếu luôn có job ưu tiên cao. Cần theo dõi tuổi job lâu nhất và thiết kế fairness nếu nghiệp vụ yêu cầu.

### Vì sao tăng lease_generation?

Giả sử worker A claim job 10 với generation `4`, sau đó bị pause lâu hơn lease. Reaper đưa job về `READY`, worker B claim lại với generation `5`. Nếu A tỉnh lại và gửi ACK với generation `4`, database từ chối vì generation hiện tại là `5`.

Generation là fencing token đơn điệu theo từng job. Nó không thay thế idempotency key của side effect; hai giá trị phục vụ hai mục tiêu khác nhau.

## 6. Claim bằng MySQL InnoDB

MySQL 8.0 hỗ trợ `SKIP LOCKED` cho locking read. Có thể chọn job và cập nhật chúng trong cùng transaction, trên cùng một connection:

```sql
START TRANSACTION;

SELECT job_id
FROM queue_jobs
WHERE queue_name = :queueName
  AND status = 'READY'
  AND available_at <= UTC_TIMESTAMP(6)
  AND attempt_count < max_attempts
ORDER BY priority DESC, available_at, created_at
LIMIT :batchSize
FOR UPDATE SKIP LOCKED;
```

Ứng dụng đọc các `job_id` được chọn nhưng chưa commit transaction. Sau đó cập nhật đúng các ID trên cùng connection:

```sql
UPDATE queue_jobs
SET status = 'RUNNING',
    lease_owner = :workerId,
    lease_generation = lease_generation + 1,
    lease_until = DATE_ADD(UTC_TIMESTAMP(6), INTERVAL :leaseSeconds SECOND),
    attempt_count = attempt_count + 1,
    updated_at = UTC_TIMESTAMP(6)
WHERE job_id IN (:selectedJobIds)
  AND status = 'READY';
```

Đọc lại các job vừa claim để lấy `payload`, `attempt_count`, `lease_generation` và `lease_until`, rồi commit:

```sql
SELECT job_id, payload, attempt_count, max_attempts,
       lease_generation, lease_until
FROM queue_jobs
WHERE job_id IN (:selectedJobIds)
  AND lease_owner = :workerId
  AND status = 'RUNNING';

COMMIT;
```

Các bước chọn, cập nhật và đọc lại phải nằm trong cùng transaction và cùng connection để row lock được giữ cho đến khi claim hoàn tất. Cú pháp bind danh sách ID tùy driver; có thể dùng temporary table hoặc batch statement nếu batch size lớn.

Không dùng `SKIP LOCKED` như một cơ chế đọc báo cáo nhất quán: nó cố ý bỏ qua hàng đang bị khóa. Kiểm tra phiên bản MySQL, engine InnoDB, isolation level và cấu hình replication trước khi dùng trong production.

## 7. Claim bằng SQL Server

SQL Server không dùng `FOR UPDATE SKIP LOCKED`. Một mẫu phổ biến là `UPDLOCK` kết hợp `READPAST` để worker đọc và khóa các hàng có thể claim, bỏ qua hàng đang bị khóa:

```sql
BEGIN TRANSACTION;

;WITH picked AS (
    SELECT TOP (@batchSize) job_id
    FROM dbo.queue_jobs WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE queue_name = @queueName
      AND status = 'READY'
      AND available_at <= SYSUTCDATETIME()
      AND attempt_count < max_attempts
    ORDER BY priority DESC, available_at, created_at
)
UPDATE q
SET status = 'RUNNING',
    lease_owner = @workerId,
    lease_generation = lease_generation + 1,
    lease_until = DATEADD(second, @leaseSeconds, SYSUTCDATETIME()),
    attempt_count = attempt_count + 1,
    updated_at = SYSUTCDATETIME()
OUTPUT inserted.job_id,
       inserted.payload,
       inserted.attempt_count,
       inserted.max_attempts,
       inserted.lease_generation,
       inserted.lease_until
FROM dbo.queue_jobs AS q
JOIN picked AS p ON p.job_id = q.job_id;

COMMIT TRANSACTION;
```

`UPDLOCK` lấy update lock khi đọc candidate; `READPAST` cho phép bỏ qua một số row lock đang được giữ; `ROWLOCK` là hint ưu tiên khóa hàng chứ không bảo đảm tuyệt đối engine không dùng page/table lock.

Nếu database bật `READ_COMMITTED_SNAPSHOT`, `READPAST` có các điều kiện sử dụng riêng; ở một số cấu hình cần thêm `READCOMMITTEDLOCK` và kiểm tra isolation level. Lock escalation hoặc page lock cũng có thể ảnh hưởng khả năng bỏ qua. Hãy kiểm thử trên đúng cấu hình SQL Server thực tế.

## 8. Worker xử lý job ngoài transaction

Sau khi claim, worker giữ một đối tượng lease chứa:

```text
job_id
queue_name
payload
attempt_count
max_attempts
lease_owner
lease_generation
lease_until
```

Worker thực hiện công việc mà không giữ transaction claim. Một vòng xử lý khái niệm:

```java
while (!stopping) {
    List<JobLease> jobs = queueRepository.claimBatch(
        queueName,
        workerId,
        batchSize,
        leaseDuration
    ); // Transaction claim commit trước khi trả về.

    if (jobs.isEmpty()) {
        waitBrieflyOrUntilSignalled();
        continue;
    }

    for (JobLease job : jobs) {
        processOne(job);
    }
}
```

`processOne` gọi handler và sau đó ACK hoặc báo lỗi bằng transaction riêng:

```java
void processOne(JobLease job) {
    try {
        handler.execute(job.payload(), job.jobId().toString());
        boolean acknowledged = queueRepository.acknowledge(
            job.jobId(), job.leaseOwner(), job.leaseGeneration()
        );

        if (!acknowledged) {
            recordStaleWorker(job);
        }
    } catch (RetryableJobException ex) {
        queueRepository.scheduleRetry(job, ex);
    } catch (Exception ex) {
        queueRepository.failOrDeadLetter(job, ex);
    }
}
```

Đây là cấu trúc minh họa. `claimBatch`, `acknowledge` và `scheduleRetry` phải có transaction boundary riêng; handler chạy ngoài transaction database của queue. Nếu handler cần thay đổi dữ liệu cùng database một cách nguyên tử với trạng thái job, cần thiết kế transaction cụ thể để cùng tham gia một transaction ngắn, nhưng không kéo dài transaction đó qua external call.

## 9. Heartbeat: gia hạn lease khi công việc còn chạy

Nếu một job có thể chạy lâu hơn lease duration, worker cần heartbeat để gia hạn quyền sở hữu. Ví dụ lease dài 60 giây, worker có thể gia hạn mỗi 15–20 giây.

```sql
UPDATE queue_jobs
SET lease_until = clock_timestamp() + INTERVAL '60 seconds',
    updated_at = clock_timestamp()
WHERE job_id = :jobId
  AND status = 'RUNNING'
  AND lease_owner = :workerId
  AND lease_generation = :leaseGeneration
  AND lease_until > clock_timestamp();
```

Nếu row count là `1`, lease đã được gia hạn. Nếu là `0`, worker không còn sở hữu lease hợp lệ: có thể lease đã hết hạn hoặc job đã được claim lại. Worker phải ngừng ghi kết quả vào queue và không được ACK bằng token cũ.

### Dùng đồng hồ database

So sánh lease bằng thời gian của database để tránh clock skew giữa các worker. Nếu worker A và B có đồng hồ lệch nhau, việc mỗi worker tự quyết định lease còn hạn có thể tạo hành vi không nhất quán. Worker có thể dùng local monotonic clock để lập lịch heartbeat, nhưng điều kiện quyền sở hữu cuối cùng phải được database kiểm tra.

### Chọn lease duration

Lease quá ngắn làm job bị reclaim khi worker chỉ tạm dừng GC hoặc network chậm. Lease quá dài làm phục hồi sau crash chậm. Chọn duration theo phân phối thời gian xử lý, thời gian pause, heartbeat interval và thời gian phục hồi chấp nhận được.

Heartbeat phải xảy ra đủ sớm trước expiry và có timeout riêng. Nếu heartbeat thất bại vì database tạm thời không truy cập được, worker nên xem quyền sở hữu là không chắc chắn; không tiếp tục thực hiện side effect mới nếu có thể tránh.

## 10. ACK: chỉ owner hiện hành mới được hoàn tất job

Sau khi handler thành công, worker cập nhật trạng thái:

```sql
UPDATE queue_jobs
SET status = 'SUCCEEDED',
    completed_at = clock_timestamp(),
    updated_at = clock_timestamp(),
    lease_owner = NULL,
    lease_until = NULL
WHERE job_id = :jobId
  AND status = 'RUNNING'
  AND lease_owner = :workerId
  AND lease_generation = :leaseGeneration
  AND lease_until > clock_timestamp();
```

Nếu row count là `1`, job đã được ACK. Nếu là `0`, worker đã mất quyền sở hữu hoặc lease hết hạn. Không được coi việc handler trả thành công là bằng chứng job đã được ghi `SUCCEEDED`.

### Vì sao cần generation nếu đã có lease_owner?

Worker ID có thể được tái sử dụng sau restart, hoặc cùng một worker process có thể claim lại job. Một owner string đơn lẻ không phân biệt lần claim cũ và lần claim mới. `lease_generation` tăng mỗi lần claim giúp phân biệt từng quyền sở hữu.

Một worker cũ có thể tỉnh lại sau pause dài và gửi ACK. Generation cũ không còn khớp nên update bị từ chối. Đây là fencing ở tầng queue database.

## 11. Báo lỗi và lên lịch retry

Khi handler thất bại, phân loại lỗi:

- **Retryable:** timeout tạm thời, lỗi kết nối, rate limit hoặc dependency unavailable theo hợp đồng.
- **Permanent:** payload sai, dữ liệu không hợp lệ, thao tác không được phép hoặc lỗi nghiệp vụ không thể tự phục hồi.
- **Ambiguous:** side effect có thể đã xảy ra nhưng worker không biết kết quả; cần tra cứu hoặc retry cùng idempotency key, không tạo operation mới.

Với lỗi retryable, nếu còn attempt, đưa job về `READY` và đặt `available_at` trong tương lai. Ví dụ PostgreSQL:

```sql
UPDATE queue_jobs
SET status = CASE
        WHEN attempt_count >= max_attempts THEN 'DEAD'
        ELSE 'READY'
    END,
    available_at = CASE
        WHEN attempt_count >= max_attempts THEN available_at
        ELSE clock_timestamp() + (:delaySeconds * INTERVAL '1 second')
    END,
    last_error = :errorText,
    updated_at = clock_timestamp(),
    lease_owner = NULL,
    lease_until = NULL
WHERE job_id = :jobId
  AND status = 'RUNNING'
  AND lease_owner = :workerId
  AND lease_generation = :leaseGeneration;
```

Nếu lỗi permanent, có thể chuyển thẳng `DEAD` bất kể số attempt. Mọi update phải kiểm tra owner và generation để worker cũ không ghi đè kết quả của worker mới.

### Exponential backoff có jitter

Một cách tính delay:

\[
cap_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

Với full jitter, chọn ngẫu nhiên:

\[
delay_n \sim Uniform(0, cap_n)
\]

Ví dụ `d0 = 1 giây`, `dmax = 5 phút`. Worker không nên retry ngay lập tức sau lỗi transient vì nhiều job có thể cùng quay lại và tạo retry storm.

`attempt_count` tăng khi claim, nên attempt đầu tiên có giá trị `1`. Sau khi attempt thứ `max_attempts` thất bại, job chuyển `DEAD`; không lên lịch thêm attempt. Nếu cần retry budget hoặc deadline tổng, lưu thêm `expires_at` và không claim job đã hết hạn.

## 12. Phục hồi job khi worker chết hoặc mất lease

Worker có thể crash sau khi claim, mất kết nối hoặc bị pause lâu. Job ở `RUNNING` không thể nằm đó mãi. Một tiến trình reaper định kỳ tìm lease hết hạn:

```sql
WITH expired AS (
    SELECT job_id
    FROM queue_jobs
    WHERE status = 'RUNNING'
      AND lease_until <= clock_timestamp()
    ORDER BY lease_until
    LIMIT :batchSize
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_jobs AS q
SET status = CASE
        WHEN q.attempt_count >= q.max_attempts THEN 'DEAD'
        ELSE 'READY'
    END,
    available_at = CASE
        WHEN q.attempt_count >= q.max_attempts THEN q.available_at
        ELSE clock_timestamp() + (:recoveryDelaySeconds * INTERVAL '1 second')
    END,
    last_error = COALESCE(q.last_error, 'Lease expired before acknowledgement'),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = clock_timestamp()
FROM expired
WHERE q.job_id = expired.job_id
  AND q.status = 'RUNNING'
  AND q.lease_until <= clock_timestamp()
RETURNING q.job_id, q.status, q.attempt_count;
```

Reaper chỉ cập nhật job còn `RUNNING` và lease đã hết tại thời điểm update. Điều kiện được kiểm tra lại để tránh đụng một worker vừa heartbeat gia hạn lease.

Khi job trở về `READY`, worker khác có thể claim và generation tăng. Nếu attempt đã đạt giới hạn, job chuyển `DEAD` để không lặp vô hạn.

### Race giữa heartbeat và reaper

Heartbeat và reaper có thể chạy gần như đồng thời. Cả hai cập nhật cùng một hàng; row lock và điều kiện `lease_until` quyết định kết quả. Nếu heartbeat gia hạn trước, reaper kiểm tra lại và không reclaim lease còn hạn. Nếu reaper chuyển job về `READY` trước, heartbeat không còn khớp `status='RUNNING'` và phải thất bại.

Không để reaper đọc danh sách lease hết hạn trong một transaction rồi cập nhật sau khi đã nhả khóa. Chọn và cập nhật candidate trong cùng transaction với locking clause.

## 13. Lease không bảo đảm side effect chỉ chạy một lần

Một tình huống quan trọng:

```text
1. Worker A claim job J, generation 7.
2. A gọi payment provider; provider thu tiền thành công.
3. A bị pause/crash trước khi ACK.
4. Lease hết hạn; reaper đưa J về READY.
5. Worker B claim J, generation 8.
6. B gọi payment provider lần nữa.
```

Generation bảo vệ trạng thái queue: A không thể ACK job bằng generation 7 sau khi B đã claim generation 8. Nhưng generation không ngăn provider thu tiền lần thứ hai. Provider không biết fencing token của queue trừ khi API của provider hỗ trợ cơ chế đó.

Với cùng một job, dùng một **side-effect idempotency key ổn định**, ví dụ:

```text
payment-charge:<job_id>
```

Mọi attempt của cùng job dùng lại key này. Không dùng `lease_generation` làm idempotency key vì generation thay đổi mỗi lần reclaim; làm vậy sẽ biến mỗi attempt thành một ý định mới đối với provider.

Nếu một job tạo nhiều tác dụng phụ khác nhau, tạo key ổn định theo từng bước:

```text
<job_id>:create-invoice
<job_id>:send-notification
<job_id>:reserve-shipment
```

Mỗi side effect có một identity riêng nhưng không đổi qua retry của chính bước đó.

## 14. Fencing token và stale worker

`lease_generation` là fencing token tăng dần. Mọi thay đổi vào database do worker thực hiện cần được bảo vệ bằng generation hoặc một cơ chế version tương đương.

Ví dụ một bảng kết quả có thể lưu generation cuối đã chấp nhận:

```sql
UPDATE job_results
SET result_payload = :result,
    accepted_generation = :generation,
    updated_at = clock_timestamp()
WHERE job_id = :jobId
  AND accepted_generation < :generation;
```

Điều kiện này chỉ phù hợp nếu mô hình kết quả cho phép so sánh generation và `job_results` đã có hàng tương ứng; có thể cần `INSERT ... ON CONFLICT` hoặc một transaction phối hợp khác. Ý tưởng là hệ thống nhận kết quả phải từ chối generation cũ hơn generation đã chấp nhận.

Nếu worker gọi một dịch vụ ngoài không hỗ trợ fencing token, hãy dùng idempotency key ở dịch vụ đó. Fencing bảo vệ thứ tự quyền sở hữu; idempotency bảo vệ tác dụng lặp. Với một số hệ thống, cần cả hai.

## 15. Xử lý kết quả không xác định của side effect

Nếu worker gọi provider rồi timeout, không được mặc định job thất bại chắc chắn. Đưa operation vào trạng thái cần tra cứu hoặc dùng cùng idempotency key để hỏi provider.

Một state machine nghiệp vụ có thể tách khỏi trạng thái queue:

```text
Queue job: READY -> RUNNING -> SUCCEEDED
                         |
                         +-> retry/reclaim khi lease hết

External operation: NEW -> IN_PROGRESS -> SUCCEEDED
                                  |
                                  +-> UNKNOWN -> RECONCILIATION
```

Job queue chỉ cho biết worker đã hoàn thành phần xử lý theo hợp đồng của nó. Nó không tự chứng minh provider đã thực hiện hay chưa nếu response bị mất. Worker có thể hoàn thành job bằng cách lưu operation ở `UNKNOWN` và chuyển sang queue reconciliation riêng, tùy yêu cầu nghiệp vụ.

Không chuyển một operation `UNKNOWN` thành operation mới với key mới. Tra cứu theo provider reference hoặc gửi lại cùng key theo hợp đồng idempotency của provider.

## 16. Dead-letter queue và thao tác quản trị

Job chuyển `DEAD` khi:

- Đạt `max_attempts`.
- Handler xác định lỗi permanent.
- Payload/schema không thể xử lý.
- Job hết deadline nghiệp vụ.
- Quy tắc vận hành yêu cầu dừng retry và chờ con người can thiệp.

Một màn hình hoặc API quản trị nên cho phép:

- Xem payload đã được che dữ liệu nhạy cảm.
- Xem attempt count, last error, thời điểm claim và worker cuối.
- Xem lịch sử lease generation và retry.
- Xem correlation ID, operation ID và provider reference.
- Replay job sau khi nguyên nhân được sửa.
- Hủy job nếu nghiệp vụ cho phép.
- Đánh dấu job cần reconciliation nếu side effect có kết quả chưa xác định.

Replay cần được kiểm soát. Nếu replay cùng một ý định nghiệp vụ, giữ stable job/operation idempotency key để tránh side effect trùng. Nếu đó là một ý định nghiệp vụ mới, tạo request key mới và ghi rõ quan hệ với job cũ.

## 17. Tối ưu truy vấn và fairness

Queue table có thể tăng nhanh. Cần tối ưu theo trạng thái và thời gian sẵn sàng:

- Index riêng cho job `READY` để claim không quét toàn bảng.
- Index cho `RUNNING` theo `lease_until` để reaper tìm job hết hạn.
- Chỉ trả payload cần thiết khi claim; payload lớn có thể lưu ở object storage và queue chỉ chứa reference.
- Claim theo batch vừa phải để worker không giữ quá nhiều lease trong lúc chưa xử lý.
- Giữ transaction claim ngắn và commit ngay.
- Xóa/archive terminal jobs theo retention policy, đồng thời giữ idempotency ledger đủ lâu.
- Theo dõi queue depth, oldest ready age, expired lease count và dead-letter count.

### Priority và starvation

`ORDER BY priority DESC` ưu tiên job có priority cao. Nếu job ưu tiên cao liên tục đến, job thấp có thể không bao giờ được claim. Có thể dùng aging (tăng effective priority theo thời gian chờ), nhiều queue riêng hoặc quota giữa priority class.

`SKIP LOCKED` cũng có thể làm một job bị bỏ qua trong khi worker khác đang giữ nó. Đây là tradeoff để tăng throughput, không phải FIFO nghiêm ngặt. Nếu thứ tự tuyệt đối là yêu cầu nghiệp vụ, cần một thiết kế tuần tự hóa theo partition/key thay vì kỳ vọng queue song song vẫn giữ thứ tự toàn cục.

## 18. Bảo vệ queue khi enqueue đồng thời

Hai request cùng idempotency key có thể đến hai API instance cùng lúc. Unique constraint của `queue_requests` là điểm phân xử.

Test lịch:

```text
Request A                         Request B
---------                         ---------
BEGIN                             BEGIN
INSERT key K                      INSERT key K
thành công                        chờ unique conflict
INSERT job J                      ...
COMMIT                            INSERT không tạo row
                                  SELECT ledger K
                                  hash giống -> trả job J
```

Nếu hash khác, request B trả conflict. Không được cập nhật payload của job J theo request B; nếu làm vậy, một client có thể thay đổi công việc đã được chấp nhận bởi client khác.

Một unique constraint trên `(queue_name, idempotency_key)` phải tồn tại trong database. Chỉ kiểm tra bằng application cache hoặc `SELECT` trước insert không bảo vệ được nhiều instance.

### Idempotency key cần có scope

Nếu nhiều tenant dùng cùng một key, khóa duy nhất phải bao gồm tenant hoặc scope tương ứng, ví dụ `(tenant_id, queue_name, idempotency_key)`. Đảm bảo caller không thể dò trạng thái job của tenant khác bằng cách đoán key; xác thực quyền truy cập trước khi trả `job_id` và trạng thái.

## 19. Retention của job và idempotency ledger

Nếu xóa `queue_requests` ngay khi job hoàn tất, request cũ được gửi lại sau đó có thể tạo job mới. Thời hạn lưu dedup cần bao phủ:

- Retry của client/API gateway.
- Message redelivery hoặc replay từ DLQ nếu enqueue đến từ broker.
- Thời gian worker có thể phục hồi sau outage.
- Cửa sổ replay vận hành.
- Thời gian nghiệp vụ cần chống tạo tác dụng phụ trùng.

Có thể archive `queue_jobs` sau khi terminal nhưng giữ `queue_requests` lâu hơn. Nếu duplicate request đến sau khi job đã archive, API vẫn trả lại cùng `job_id`; muốn trả trạng thái chi tiết, cần lưu terminal summary trong ledger hoặc tra cứu archive.

Với thanh toán, ledger hoặc hành động không thể lặp, nên có unique business reference bền vững trong bảng domain, không chỉ dựa vào TTL ngắn của queue dedup.

## 20. Quan sát và cảnh báo

Các metric nên đo:

| Metric | Ý nghĩa |
|---|---|
| `queue_ready_jobs` | Số job sẵn sàng hiện tại. |
| `queue_running_jobs` | Số job đang có lease. |
| `queue_oldest_ready_age_seconds` | Tuổi của job READY lâu nhất. |
| `queue_claim_total` | Tổng số lần claim. |
| `queue_attempt_total` | Tổng số attempt xử lý. |
| `queue_success_total` | Tổng số job hoàn tất. |
| `queue_retry_total` | Số lần job được lên lịch retry. |
| `queue_lease_expired_total` | Số lease hết hạn và được phục hồi. |
| `queue_dead_total` | Số job chuyển DEAD. |
| `queue_duplicate_enqueue_total` | Số request enqueue được nhận diện là duplicate. |
| `queue_idempotency_mismatch_total` | Số lần cùng key nhưng payload hash khác. |
| `queue_processing_duration_seconds` | Thời gian xử lý từng attempt. |
| `queue_claim_wait_seconds` | Thời gian lấy connection/claim nếu đo được. |

Không dùng `job_id`, tenant ID hoặc idempotency key làm label metric có cardinality cao. Đưa định danh chi tiết vào log/trace. Metric labels nên giới hạn ở `queue_name`, `outcome`, `error_class` hoặc worker pool đã chuẩn hóa.

Log/trace nên chứa:

- `job_id` và correlation ID.
- `queue_name` và worker ID.
- `lease_generation` và attempt number.
- Claim/lease/heartbeat/ACK timestamps.
- Error class, retry delay và provider reference nếu có.
- Idempotency key đã che một phần, không ghi secret hoặc payload nhạy cảm.

Cảnh báo khi oldest ready age tăng, lease expiry tăng đột biến, queue depth không giảm, dead-letter count tăng, worker không heartbeat hoặc idempotency mismatch xuất hiện.

## 21. Bài tập thực hành

Hãy triển khai queue trong một database thật mà ứng dụng sử dụng. Có thể dùng PostgreSQL làm mặc định; nếu dự án dùng MySQL InnoDB hoặc SQL Server, thay phần claim bằng cú pháp tương ứng ở trên và chạy test trên đúng engine đó.

### Phần A: schema và enqueue

1. Tạo `queue_jobs` và `queue_requests` cùng các constraint.
2. Tạo index cho job READY và lease hết hạn.
3. Viết API enqueue nhận queue name, idempotency key và payload.
4. Tính request hash từ payload đã chuẩn hóa.
5. Tạo request ledger và job trong cùng transaction.
6. Nếu cùng key/hash, trả cùng `job_id`; nếu cùng key/hash khác, trả conflict.

### Phần B: claim và ownership

1. Viết `claimBatch(queueName, workerId, batchSize, leaseDuration)`.
2. Dùng `SKIP LOCKED` hoặc locking hint tương đương để nhiều worker claim song song.
3. Tăng `attempt_count` và `lease_generation` trong claim.
4. Trả lease token cho worker và commit ngay.
5. Viết heartbeat chỉ gia hạn đúng owner/generation còn hạn.
6. Viết ACK chỉ thành công với owner/generation hiện hành.

### Phần C: retry và phục hồi

1. Phân loại lỗi retryable/permanent/ambiguous.
2. Tính exponential backoff có jitter.
3. Đưa job lỗi tạm thời về READY nếu còn attempt.
4. Chuyển job hết attempt hoặc lỗi permanent sang DEAD.
5. Viết reaper tìm lease hết hạn và phục hồi job.
6. Bảo đảm worker cũ không ACK được sau khi job đã được claim lại.

### Phần D: side effect idempotent

1. Tạo fake provider có bảng ledger và hỗ trợ idempotency key.
2. Dùng `job_id` hoặc operation ID ổn định làm key cho cùng side effect.
3. Mô phỏng provider thành công nhưng worker crash trước ACK.
4. Cho job được claim lại và chạy lại handler.
5. Xác nhận provider chỉ ghi một side effect.

### Phần E: quan sát và vận hành

1. Ghi log job ID, worker ID, generation và attempt.
2. Đo queue depth, oldest ready age, expired lease và dead-letter.
3. Tạo API xem trạng thái job có kiểm tra quyền truy cập.
4. Tạo quy trình replay DEAD có kiểm soát.
5. Định nghĩa retention cho job và request idempotency ledger.

## 22. Bộ kiểm thử bắt buộc

### Test 1: hai worker không claim cùng lease generation

Chuẩn bị một job READY và hai connection. Cho hai worker claim đồng thời. Xác nhận chỉ một worker nhận job đó trong lần claim hiện tại; worker còn lại nhận job khác hoặc không có job. Nếu batch có nhiều job, tổng tập job được claim giữa hai worker không giao nhau.

### Test 2: hai request enqueue cùng key và cùng payload

Gửi đồng thời hai request với cùng `(queue_name, idempotency_key, request_hash)`. Xác nhận chỉ có một job được tạo, cả hai response chứa cùng `job_id` và `queue_requests` chỉ có một record.

### Test 3: cùng key nhưng payload khác

Gửi request thứ hai với cùng key nhưng hash khác. Xác nhận API trả conflict và payload/job đã tạo ban đầu không thay đổi.

### Test 4: worker crash sau claim

Worker A claim job rồi dừng mà không ACK. Đợi lease hết hạn, chạy reaper và cho worker B claim lại. Xác nhận generation của B lớn hơn generation của A.

### Test 5: stale worker không thể ACK

Sau khi B claim generation mới, gửi ACK từ A bằng generation cũ. Xác nhận row count bằng `0` và trạng thái job vẫn thuộc quyền B.

### Test 6: side effect thành công nhưng ACK bị mất

Fake provider nhận stable idempotency key và ghi một side effect. Worker crash trước ACK. Sau reclaim, worker gọi provider cùng key. Xác nhận ledger của provider vẫn chỉ có một tác dụng và job cuối cùng được ACK.

### Test 7: retry có giới hạn

Cho handler luôn trả lỗi retryable. Xác nhận attempt count tăng đúng, available_at được đặt trong tương lai và sau `max_attempts` job chuyển DEAD.

### Test 8: heartbeat cạnh tranh với reaper

Chạy heartbeat gần thời điểm lease hết hạn đồng thời với reaper. Xác nhận chỉ một chuyển đổi thắng theo điều kiện thời gian và row lock; không có hai lease generation cùng hợp lệ.

### Test 9: job permanent failure

Cho handler trả lỗi permanent. Xác nhận job chuyển DEAD ngay, không quay lại READY.

### Test 10: retention và replay

Archive job terminal nhưng giữ request idempotency ledger trong cửa sổ retention. Gửi lại cùng key và xác nhận không tạo job mới. Sau khi retention hết, hành vi phải tuân theo chính sách đã định nghĩa và được kiểm thử riêng.

Test concurrency phải dùng connection/session độc lập và barrier/latch thay vì `Thread.sleep()` để đoán thứ tự. Ghi session ID hoặc transaction ID khi cần chứng minh database thực sự nhận nhiều transaction.

## 23. Những lỗi thiết kế thường gặp

- **SELECT READY rồi UPDATE ở transaction khác:** hai worker có thể cùng claim một job. Dùng row lock và update trong cùng transaction.
- **Giữ transaction mở khi xử lý payload:** connection và lock bị giữ lâu, pool dễ cạn. Commit claim trước khi gọi handler.
- **Chỉ lưu worker ID, không có generation:** worker cũ có thể ghi đè trạng thái sau khi job được reclaim. Dùng fencing token tăng dần.
- **Lease hết hạn nhưng worker cũ vẫn tiếp tục side effect:** có thể xử lý trùng. Dùng stable idempotency key ở hệ thống nhận và dừng worker khi mất lease.
- **Dùng generation làm idempotency key:** mỗi lần reclaim trở thành một ý định mới. Dùng job/operation ID ổn định cho side effect.
- **ACK trước khi tác dụng nghiệp vụ được lưu:** job có thể bị đánh dấu xong dù công việc chưa hoàn tất.
- **Không có reaper:** job RUNNING bị kẹt vĩnh viễn sau worker crash.
- **Retry không giới hạn:** job lỗi cố định quay lại queue liên tục. Dùng max attempts, backoff và DEAD.
- **Tạo key mới khi client retry enqueue:** một ý định có thể tạo nhiều job. Client phải gửi lại cùng idempotency key.
- **Cùng key nhưng payload khác vẫn trả job cũ:** che giấu lỗi caller và có thể trả kết quả sai. So sánh request hash.
- **Xóa dedup record cùng job ngay lập tức:** request cũ được gửi lại có thể tạo job mới. Retain ledger đủ lâu.
- **Cho rằng lease tạo exactly-once:** lease chỉ quản lý quyền sở hữu trong database; side effect ngoài cần idempotency riêng.
- **Dùng SKIP LOCKED nhưng giả định FIFO tuyệt đối:** hàng bị khóa có thể bị bỏ qua và job ưu tiên thấp có thể starvation.
- **Không phân biệt lỗi permanent và ambiguous:** timeout có thể đã gây side effect; retry mù có thể nhân tác dụng.
- **Không kiểm tra row count của heartbeat/ACK:** worker stale có thể tưởng mình vẫn sở hữu job.

## 24. Quy trình triển khai theo thứ tự

Một thứ tự triển khai giúp từng cơ chế có thể kiểm chứng:

1. Tạo schema, constraint và index.
2. Viết enqueue idempotent với request hash và unique key.
3. Kiểm thử hai request enqueue đồng thời trước khi thêm worker.
4. Viết claim batch nguyên tử và kiểm thử hai connection claim song song.
5. Thêm lease owner, generation và heartbeat.
6. Thêm ACK/fail có điều kiện theo owner/generation.
7. Thêm reaper phục hồi lease hết hạn.
8. Thêm bounded retry, backoff, permanent failure và dead-letter.
9. Tách handler ra ngoài transaction claim.
10. Thêm idempotency key ổn định cho side effect bên ngoài.
11. Kiểm thử crash sau claim, sau side effect và trước ACK.
12. Thêm metric, log, dashboard và retention.

Không coi test đơn lẻ “hai worker claim thành công” là đủ. Cần kiểm tra các cửa sổ crash, stale worker, duplicate enqueue và tác dụng phụ trùng.

## 25. Kết luận

Một database-backed queue đáng tin cậy cần phối hợp idempotent enqueue, atomic claim, lease ownership, fencing token, ACK/fail có điều kiện, lease recovery và retry có giới hạn. Unique constraint trên request key bảo đảm cùng một ý định enqueue không tạo nhiều job; request hash phát hiện cùng key bị dùng với nội dung khác. Row locking với `SKIP LOCKED` hoặc hint tương đương cho phép nhiều worker nhận các job khác nhau mà không cùng claim một hàng.

Worker chỉ giữ transaction trong lúc claim hoặc cập nhật trạng thái. Nó xử lý công việc ngoài transaction, heartbeat khi cần và chỉ ACK nếu generation vẫn còn hiệu lực. Reaper phục hồi job khi lease hết hạn; retry có backoff và dead-letter khi hết attempt. Lease không tạo exactly-once cho side effect: worker có thể đã gọi provider rồi crash trước ACK. Vì vậy, dùng job/operation ID ổn định làm idempotency key cho cùng tác dụng, lưu kết quả bền vững và có quy trình reconciliation cho outcome chưa xác định. Khi kiểm thử bằng nhiều connection thật, các bất biến về ownership, dedup và phục hồi có thể được xác nhận rõ ràng trước khi đưa queue vào vận hành.
