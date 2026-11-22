# Xây hàng đợi công việc với khóa hàng và giới hạn bảo đảm trong PostgreSQL

Khi một API cần gửi email, đồng bộ dữ liệu, tạo thumbnail hoặc xuất báo cáo, xử lý tất cả trong HTTP request có thể khiến người dùng chờ lâu và làm request phụ thuộc vào những dịch vụ khác. Một giải pháp là **lưu công việc vào hàng đợi (job queue)** để các worker thực thi sau.

PostgreSQL có thể lưu queue bằng một bảng và cung cấp cơ chế **row-level locking**, đặc biệt là `SELECT ... FOR UPDATE SKIP LOCKED`, cho phép nhiều worker lấy công việc mà không cùng chờ một hàng đang được khóa.

Tuy nhiên, phải phân biệt:

- **Chọn job độc quyền trong một transaction** không có nghĩa job chỉ được thực thi đúng một lần.
- **Khóa hàng (row lock)** chỉ tồn tại theo transaction; nó không phải quyền xử lý kéo dài hàng phút.
- **Lease** chỉ là dữ liệu ứng dụng ghi trong bảng để quản lý quyền xử lý có hạn.
- **Retry** giúp không bỏ quên job sau crash nhưng có thể khiến side effect được thực hiện lặp.
- **Exactly-once effect** trong hệ thống ngoài PostgreSQL cần idempotency/fencing hoặc một giao thức tích hợp phù hợp, không tự có chỉ nhờ `SKIP LOCKED`.

Bài học thuộc chương **Khóa** của module *Database Engine Relational PostgreSQL*, hướng dẫn cách thiết kế bảng queue, claim nguyên tử, heartbeat, ack/fail/requeue, reaper, dead-letter, retry, quan sát hiệu năng và những giới hạn về thứ tự, tính công bằng và độ tin cậy.

## 1. Job queue làm gì?

Một kiến trúc đơn giản:

~~~text
                 PostgreSQL
HTTP request --> BEGIN
                 INSERT order
                 INSERT queue_job
                 COMMIT
                      |
                      v
                 jobs: pending
                      |
             +--------+--------+
             |        |        |
           Worker A Worker B Worker C
             |        |        |
             +--------+--------+
                      |
                External API
                      |
                ACK succeeded
~~~

API chỉ ghi một **mô tả công việc** đã được commit. Worker lấy công việc, xử lý và cập nhật kết quả.

### 1.1. Trạng thái tối thiểu

Một job có thể đi qua:

~~~text
          +---------+
enqueue ->| pending |<----+
          +----+----+     |
               | claim    | retry/backoff
               v          |
          +---------+     |
          | running |-----+
          +----+----+
               |
        +------+--------+
        |               |
        v               v
   succeeded           dead
~~~

Một trạng thái `cancelled` có thể dùng khi business workflow cho phép hủy công việc trước khi xử lý.

### 1.2. Job khác sự kiện

Một queue thường muốn **một worker xử lý một job ở một thời điểm**. Event log có thể cần nhiều consumer groups, mỗi nhóm đều nhận cùng sự kiện. Một bảng queue đơn giản không tự cung cấp đầy đủ consumer offsets, replay, fan-out hay ordering theo partition như một message broker chuyên dụng.

### 1.3. Khi nào PostgreSQL là lựa chọn phù hợp?

Đặc biệt hữu ích khi ứng dụng đã dùng PostgreSQL và muốn enqueue cùng transaction nghiệp vụ, với lượng việc phù hợp khả năng server và số nhóm consumer hạn chế.

## 2. Race condition khi chỉ SELECT pending

Mẫu không an toàn:

~~~sql
SELECT job_id, payload
FROM jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 1;
~~~

Hai worker có thể cùng SELECT trước khi bên nào UPDATE:

~~~text
T1 - Worker A                     T2 - Worker B
--------------------------------  -----------------------------
SELECT pending -> job 42          SELECT pending -> job 42
Gửi email job 42                  Gửi email job 42
UPDATE status = succeeded         UPDATE status = succeeded
~~~

Hàng đợi đã cho một công việc bị thực thi hai lần. SELECT thông thường không đổi quyền sở hữu job.

**Giải pháp:** chọn job dưới một row lock và cập nhật trạng thái trong cùng transaction, hoặc dùng một statement claim nguyên tử.

## 3. Row-level lock và FOR UPDATE

~~~sql
BEGIN;

SELECT job_id, payload
FROM jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 1
FOR UPDATE;

-- UPDATE trạng thái ngay trong transaction.

COMMIT;
~~~

`FOR UPDATE` yêu cầu row locks trên những hàng được chọn.

### 3.1. Khi worker khác chọn cùng hàng

Worker B cũng dùng FOR UPDATE trên cùng hàng có thể **phải đợi** Worker A nhả khóa. Với nhiều worker và một job đứng đầu, việc cùng chờ có thể gây tắc nghẽn.

### 3.2. Khóa không tự sửa dữ liệu

Nếu T1 SELECT FOR UPDATE rồi ROLLBACK, status vẫn pending; không có claim bền vững. Phải ghi `status='running'` trước khi COMMIT nếu cần ghi nhận quyền xử lý.

### 3.3. Khóa kết thúc theo transaction

Nếu worker SELECT FOR UPDATE trong chế độ autocommit rồi trả connection về pool, khóa có thể đã được nhả trước khi worker bắt đầu gọi API. Không thể dựa trên khóa đã hết để bảo vệ phần xử lý bên ngoài.

### 3.4. UPDATE cũng lấy khóa cần thiết

Để giảm round trips, một câu `UPDATE ... FROM candidate</BT> với CTE SELECT FOR UPDATE thường là lựa chọn gọn hơn việc SELECT rồi UPDATE bằng hai câu từ ứng dụng.

## 4. FOR UPDATE, NOWAIT và SKIP LOCKED

| Cú pháp | Khi gặp hàng đã có row lock xung đột | Cách dùng |
|---|---|---|
| `FOR UPDATE` | Chờ được cấp khóa | Cần đúng hàng đã chọn |
| `FOR UPDATE NOWAIT` | Báo lỗi nhanh | Muốn phát hiện contention ngay |
| `FOR UPDATE SKIP LOCKED` | Bỏ qua hàng đang bị khóa | Queue cho phép nhận một job khác |

Ví dụ:

~~~sql
SELECT job_id
FROM jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

Nếu job 42 đang bị khóa, worker có thể lấy job 43 thay vì chờ.

### 4.1. SKIP LOCKED là một góc nhìn không nhất quán

Bằng việc bỏ qua hàng đang khóa, tập kết quả không còn là một danh sách đầy đủ theo snapshot/query thông thường. Đây là **đánh đổi có chủ đích** dành cho worker queue, không phải đặc tính mong muốn của báo cáo tổng hợp.

### 4.2. Không bảo đảm FIFO

Worker A claim job 42 trước nhưng mất 30 giây; Worker B claim job 43 sau nhưng hoàn tất sau 200ms. Thứ tự hoàn tất là 43 rồi 42.

Ngay cả thứ tự claim có thể khác thứ tự ưu tiên tại một thời điểm do SKIP LOCKED bỏ qua những hàng đang khóa.

### 4.3. Không bỏ qua mọi table lock

SKIP LOCKED áp dụng cho row-level locking theo cơ chế được hỗ trợ. SELECT/UPDATE vẫn có thể cần những table locks tương ứng và bị DDL giữ khóa mạnh chặn. Không nên nghĩ SKIP LOCKED làm queue miễn nhiễm với mọi lock wait.

## 5. Hai cách thực thi job

### 5.1. Giữ transaction và lock suốt lúc xử lý

~~~text
BEGIN
SELECT job FOR UPDATE
CALL email service (mất 5 giây)
UPDATE job succeeded
COMMIT
~~~

Vấn đề:

- Giữ row lock và connection nhiều giây/phút.
- Transaction dài gây áp lực MVCC/VACUUM.
- External HTTP side effect không rollback cùng PostgreSQL.
- Worker chết hoặc chờ mạng kéo dài khiến các transaction khác khó tiến.
- Connection pool cạn có thể gây lỗi hàng loạt.

Không nên mặc định giữ transaction qua một network call chậm.

### 5.2. Claim nhanh, xử lý ngoài, ack nhanh

~~~text
BEGIN -> claim pending thành running -> COMMIT
           |
           v
       HTTP / CPU work
           |
           v
BEGIN -> ack running thành succeeded -> COMMIT
~~~

Đây là mô hình chính trong bài. Row lock được giữ ngắn, nhưng cần **lease, token, heartbeat, retry và reaper** để phục hồi worker crash.

## 6. Schema queue có quản lý lease

Các ví dụ dùng **database thử nghiệm** và quyền CREATE SCHEMA. Nếu `queue_lab` đã tồn tại, hãy dùng tên khác; không DROP dữ liệu không thuộc bài học.

~~~sql
CREATE SCHEMA queue_lab;

CREATE TABLE queue_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_name TEXT NOT NULL DEFAULT 'default',
    dedupe_key TEXT,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'running', 'succeeded', 'dead', 'cancelled'
        )),

    priority INTEGER NOT NULL DEFAULT 0,
    run_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5
        CHECK (max_attempts >= 1),

    claimed_by TEXT,
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,

    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT uq_queue_dedupe
        UNIQUE (queue_name, dedupe_key),

    CONSTRAINT ck_claim_state
        CHECK (
            (
                status = 'running'
                AND claimed_by IS NOT NULL
                AND claim_token IS NOT NULL
                AND lease_until IS NOT NULL
            )
            OR
            (
                status <> 'running'
                AND claimed_by IS NULL
                AND claim_token IS NULL
                AND lease_until IS NULL
            )
        )
);
~~~

### 6.1. Giải thích các cột quan trọng

| Cột | Vai trò |
|---|---|
| `job_id` | Định danh job |
| `queue_name` | Nhóm worker/loại queue |
| `dedupe_key` | Khóa chống enqueue trùng |
| `job_type` | Handler thực thi |
| `payload` | Dữ liệu hoặc tham chiếu |
| `status` | Vòng đời công việc |
| `priority` | Ưu tiên chọn job |
| `run_at` | Mốc sẵn sàng xử lý |
| `attempts/max_attempts` | Quản lý số lượt thử |
| `claimed_by` | Worker sở hữu lượt claim |
| `claim_token` | Nhận dạng một lượt claim |
| `claim_version` | Số phiên bản quyền xử lý tăng dần |
| `lease_until` | Hạn của claim |
| `last_error` | Chẩn đoán lỗi |
| `created_at/updated_at/completed_at` | Quan sát và retention |

### 6.2. Constraint giúp gì?

Constraint bảo đảm một hàng running phải có worker/token/lease, còn hàng không running đã xóa các trường claim đó. Nhưng constraint không biết worker có thật sự còn sống, HTTP API đã được gọi chưa, hay job có được thực hiện đúng một lần không.

### 6.3. UNIQUE và NULL

Với unique constraint mặc định, nhiều hàng có `dedupe_key=NULL` vẫn được phép. Muốn bắt buộc idempotency ở bước enqueue, hợp đồng nghiệp vụ phải yêu cầu key tường minh hoặc thêm constraint phù hợp.

## 7. Chỉ mục cho worker

~~~sql
CREATE INDEX idx_jobs_ready
ON queue_lab.jobs (
    queue_name,
    priority DESC,
    run_at ASC,
    job_id ASC
)
WHERE status = 'pending';
~~~

Index giúp tìm job pending theo queue, ưu tiên và thời gian.

### 7.1. Trade-off thứ tự cột

`priority DESC</BT> trước `run_at</BT> có thể giúp ORDER BY, nhưng nếu có nhiều job ưu tiên cao **chưa đến hạn**, query có thể phải kiểm tra nhiều entries. Tùy dữ liệu, có thể cần index khác hoặc thay chiến lược ưu tiên.

### 7.2. Job running hết lease

~~~sql
CREATE INDEX idx_jobs_expired
ON queue_lab.jobs (lease_until)
WHERE status = 'running';
~~~

Hữu ích cho reaper tìm jobs running đã hết hạn.

### 7.3. Không dùng thời gian động trong partial index predicate

Không nên định nghĩa partial index theo `WHERE run_at <= now()`. Predicate index yêu cầu những biểu thức phù hợp tính bất biến; thời gian hiện tại thay đổi liên tục. Hãy index cột và so sánh với thời gian lúc query chạy.

### 7.4. Index có chi phí

Queue cập nhật status nhiều lần nên index thừa tăng WAL, dead tuples và thời gian maintenance. Chỉ tạo index phục vụ truy vấn thực tế và đo với EXPLAIN.

## 8. Enqueue job

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload, priority
)
VALUES (
    'emails',
    'welcome:user:1001',
    'send_welcome_email',
    '{"user_id":1001, "template":"welcome"}'::jsonb,
    10
)
RETURNING job_id, status, attempts, run_at;
~~~

Kết quả có status pending, attempts=0 và thời điểm chạy mặc định.

### 8.1. Job hẹn giờ

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload, run_at
)
VALUES (
    'reports',
    'monthly-report:2026-11',
    'generate_monthly_report',
    '{"month":"2026-11"}'::jsonb,
    TIMESTAMPTZ '2026-12-01 01:00:00+07'
);
~~~

Worker không claim trước `run_at` nếu query áp dụng đúng điều kiện sẵn sàng.

### 8.2. Ghi job cùng business transaction

~~~sql
BEGIN;

-- Ví dụ trong schema thực:
-- INSERT INTO orders (...) VALUES (...) RETURNING order_id;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails',
    'order-confirmation:ORD-1001',
    'send_order_confirmation',
    '{"order_code":"ORD-1001"}'::jsonb
);

COMMIT;
~~~

Nếu cả order và job được ghi trong **cùng transaction**, hai thay đổi cùng commit hoặc rollback. Đây là cơ sở của transactional outbox trong những tình huống thích hợp.

## 9. Tránh enqueue trùng với ON CONFLICT

Client có thể retry request vì mất response dù transaction đầu đã commit.

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails',
    'welcome:user:1001',
    'send_welcome_email',
    '{"user_id":1001}'::jsonb
)
ON CONFLICT (queue_name, dedupe_key)
DO NOTHING
RETURNING job_id;
~~~

Nếu key đã tồn tại, INSERT không tạo hàng mới và RETURNING không có hàng.

### 9.1. Dedupe key cần mang ý nghĩa nghiệp vụ

Ví dụ:

- `welcome:user:1001` — một email chào mừng theo user.
- `sync-order:1001:v3` — đồng bộ phiên bản đơn hàng.
- `report:2026-11` — báo cáo cho một kỳ.

Không dùng key `'email'` cho tất cả jobs.

### 9.2. Chống enqueue trùng khác chống execution trùng

Unique key chỉ giúp không tạo **hai hàng job** cùng key. Job duy nhất đó vẫn có thể được xử lý nhiều lần nếu worker crash trước ack rồi job được retry.

### 9.3. Retention của dedupe key

Nếu giữ succeeded row mãi, cùng key luôn bị chặn enqueue. Nếu xóa hàng sớm, key lại khả dụng. Thời gian giữ idempotency key phải khớp nghiệp vụ và retry window.

## 10. Câu claim nguyên tử với SKIP LOCKED

Một worker lấy một job của queue emails:

~~~sql
BEGIN;

WITH candidate AS MATERIALIZED (
    SELECT job_id
    FROM queue_lab.jobs
    WHERE queue_name = 'emails'
      AND status = 'pending'
      AND run_at <= statement_timestamp()
      AND attempts < max_attempts
    ORDER BY priority DESC, run_at ASC, job_id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_lab.jobs AS j
SET status = 'running',
    claimed_by = 'worker-A',
    claim_token = gen_random_uuid(),
    claim_version = j.claim_version + 1,
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    attempts = j.attempts + 1,
    updated_at = statement_timestamp()
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.payload,
    j.claim_token,
    j.claim_version,
    j.attempts,
    j.lease_until;

COMMIT;
~~~

Ví dụ dùng `MATERIALIZED` (PostgreSQL 12+) và `gen_random_uuid()</BT> (có sẵn trong PostgreSQL hiện đại; ở phiên bản cũ cần kiểm tra extension tương ứng).

### 10.1. Diễn biến

1. Chọn job pending đúng queue và đã đến hạn.
2. Bỏ qua job đã vượt max_attempts.
3. Sắp theo ưu tiên, thời gian, job_id.
4. Lấy row lock và bỏ qua hàng đang khóa.
5. Chọn một candidate.
6. Đổi thành running, sinh token, tăng attempt/version.
7. Trả payload và thông tin ownership.
8. COMMIT nhanh để nhả row lock.

### 10.2. Vì sao cần RETURNING?

Worker phải nhận **claim_token** đúng lượt và dùng nó khi heartbeat/ack. Không tự suy ra token từ job_id hoặc luôn gửi một token cố định.

### 10.3. Khi không có job sẵn sàng

UPDATE trả 0 hàng. Đây là kết quả bình thường; worker có thể ngủ một khoảng ngắn rồi polling tiếp, không cần busy loop liên tục.

### 10.4. Vì sao dùng statement_timestamp()?

`now()</BT> là thời điểm bắt đầu transaction; một transaction mở từ lâu có thể cho timestamp quá cũ. `statement_timestamp()</BT> cung cấp mốc của câu SQL đang chạy, thường phù hợp hơn cho claim/heartbeat được thực hiện qua transaction rất ngắn.

## 11. Lab hai worker và khóa cùng hàng

Mở **hai kết nối PostgreSQL riêng**.

### 11.1. Chuẩn bị thêm hai jobs

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES
    ('emails', 'lab:mail:A', 'send_mail', '{"to":"A"}'::jsonb),
    ('emails', 'lab:mail:B', 'send_mail', '{"to":"B"}'::jsonb);
~~~

### 11.2. Session A

~~~sql
BEGIN;

SELECT job_id, dedupe_key
FROM queue_lab.jobs
WHERE queue_name = 'emails'
  AND status = 'pending'
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE;

-- Đừng COMMIT ngay.
~~~

### 11.3. Session B

~~~sql
BEGIN;

SELECT job_id, dedupe_key
FROM queue_lab.jobs
WHERE queue_name = 'emails'
  AND status = 'pending'
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

Nếu còn job phù hợp khác, B thường nhận hàng **khác hàng A đang khóa** thay vì chờ.

### 11.4. Dọn dẹp

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

Vì chỉ SELECT FOR UPDATE rồi ROLLBACK, đây là thí nghiệm locking chứ chưa phải claim bền vững.

### 11.5. Thử claim thật

Cho mỗi session chạy câu UPDATE claim phần 10 với `claimed_by` khác nhau. Kiểm tra hai jobs được claim riêng hoặc một worker nhận 0 khi hết job pending.

## 12. Claim và execution là hai transaction khác nhau

Một worker điển hình:

~~~text
Transaction A:
  claim pending -> running
  COMMIT

Không có DB transaction mở:
  gọi HTTP API / xử lý file

Transaction B:
  ack running -> succeeded bằng token
  COMMIT
~~~

### 12.1. Vì sao không giữ lock qua HTTP call?

Row lock/transaction dài giữ connection, làm tăng contention và gây áp lực MVCC. External side effect cũng không rollback cùng PostgreSQL nếu HTTP đã thành công.

### 12.2. Vì sao cần trạng thái running?

Sau claim COMMIT, row lock hết hiệu lực. Nếu job vẫn pending, worker khác có thể lấy nó. `status='running'` là dữ liệu bền vững ghi nhận job đã được giao.

### 12.3. Nếu worker chết ngay sau claim?

Job sẽ kẹt running nếu không có lease/reaper. Vì vậy claim cần ghi hạn xử lý và hệ thống cần cơ chế phục hồi.

## 13. Lease: quyền xử lý có thời hạn

Lease là thông tin:

~~~text
job_id:       42
status:       running
claimed_by:   worker-A
claim_token:  token của lần claim này
lease_until:  thời điểm claim hết hạn
~~~

### 13.1. Lease không phải PostgreSQL row lock

Lease không giữ khóa sau khi transaction claim commit; nó chỉ là quy tắc ứng dụng dựa trên cột timestamp và token.

### 13.2. Lease không chứng minh worker đã chết

Worker có thể bị pause, mất mạng tạm thời, GC pause hoặc quá tải CPU. Lease hết hạn không có nghĩa external API call cũ chắc chắn đã dừng.

### 13.3. Độ dài lease

- Quá ngắn: công việc còn chạy đã bị requeue, tăng execution trùng.
- Quá dài: worker crash thì job phục hồi chậm.
- Phù hợp: tính theo P95/P99 thời lượng công việc, nhịp heartbeat và recovery SLA.

## 14. Heartbeat gia hạn lease

Sau khi nhận job_id/token thực từ RETURNING, worker có thể gọi:

~~~sql
UPDATE queue_lab.jobs
SET lease_until = statement_timestamp() + INTERVAL '2 minutes',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, lease_until;
~~~

**UUID và job_id trong ví dụ chỉ là giá trị minh họa**; phải bind đúng dữ liệu claim trả về. Không dùng token cố định cho mọi job.

### 14.1. Vì sao kiểm tra token?

Nếu A mất lease và B claim lại job, B có token khác. A không được phép gia hạn quyền của lượt xử lý cũ.

### 14.2. Vì sao kiểm tra lease_until còn hạn?

Một worker thức dậy sau khi lease hết không nên tự gia hạn mà không có giao thức reclaim, vì reaper/worker khác có thể đã bắt đầu phục hồi.

### 14.3. Heartbeat trả 0 hàng

Đó là dấu hiệu worker **không còn ownership hợp lệ** hoặc job đã đổi trạng thái. Worker phải kiểm tra lại chứ không tiếp tục ack tùy ý.

## 15. Ack thành công có kiểm tra claim

~~~sql
UPDATE queue_lab.jobs
SET status = 'succeeded',
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    completed_at = statement_timestamp(),
    updated_at = statement_timestamp(),
    last_error = NULL
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, status, completed_at;
~~~

Một lần nữa: dùng ID/token thực của lượt claim, không giữ nguyên UUID giả.

### 15.1. UPDATE trả 1 hàng

DB đã áp dụng ack trong statement. Nếu dùng explicit transaction, chỉ coi kết quả cuối cùng thành công sau COMMIT.

### 15.2. UPDATE trả 0 hàng

Có thể vì token sai, job đã thành succeeded/dead/cancelled, lease hết, worker khác đã reclaim hoặc job_id không tồn tại. Không bỏ điều kiện ownership để “ép ack”.

### 15.3. Ack không chứng minh email chỉ được gửi một lần

Job có thể đã gọi external service hai lần rồi mới ack một lần. Bảng chỉ ghi nhận trạng thái job, không tự chứng minh số side effects ngoài DB.

## 16. Retry và dead-letter

Nếu công việc gặp lỗi tạm thời, worker có thể trả job về pending với `run_at` tương lai; nếu hết số lượt thử, chuyển sang dead.

~~~sql
UPDATE queue_lab.jobs
SET status = CASE
        WHEN attempts >= max_attempts THEN 'dead'
        ELSE 'pending'
    END,
    run_at = CASE
        WHEN attempts >= max_attempts THEN run_at
        ELSE statement_timestamp() + INTERVAL '15 seconds'
    END,
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'HTTP 503 from external service',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, status, attempts, max_attempts, run_at;
~~~

### 16.1. attempts được tăng khi claim

`attempts</BT> trong schema này là số **lượt claim**, không nhất thiết số lần HTTP call. Một worker có thể thử gọi service nhiều lần trong một lượt claim.

### 16.2. Backoff và jitter

Ví dụ:

~~~text
Lượt 1 lỗi -> retry sau 10s
Lượt 2 lỗi -> retry sau 30s
Lượt 3 lỗi -> retry sau 2 phút
Lượt 4 lỗi -> retry sau 10 phút
Hết max_attempts -> dead
~~~

Jitter giúp tránh nhiều jobs thất bại đồng loạt rồi cùng retry vào một thời điểm.

### 16.3. Lỗi tạm và lỗi vĩnh viễn

- HTTP 429/503, timeout: có thể retry.
- Payload không hợp lệ, dữ liệu cần thiết không tồn tại vĩnh viễn: dead sớm khi phù hợp.
- Network timeout khi gọi payment: **kết quả không rõ**, không đơn giản retry mà không có idempotency/reconciliation.

### 16.4. Dead-letter không phải xóa ngay

Giữ thông tin lỗi vừa đủ để điều tra, cảnh báo và replay có kiểm soát. Không lặp vô hạn một job gây lỗi để chiếm hết worker capacity.

## 17. Reaper phục hồi jobs hết lease

Nếu worker chết sau claim mà không ack, job running có thể tồn tại mãi. Reaper cần chạy định kỳ:

~~~sql
UPDATE queue_lab.jobs
SET status = CASE
        WHEN attempts >= max_attempts THEN 'dead'
        ELSE 'pending'
    END,
    run_at = CASE
        WHEN attempts >= max_attempts THEN run_at
        ELSE statement_timestamp() + INTERVAL '5 seconds'
    END,
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = COALESCE(
        last_error,
        'Lease expired before acknowledgement'
    ),
    updated_at = statement_timestamp()
WHERE status = 'running'
  AND lease_until <= statement_timestamp()
RETURNING job_id, status, attempts, run_at;
~~~

### 17.1. Vì sao phải có reaper?

Row locks từ claim đã hết sau COMMIT. Lease hết hạn **không tự làm hàng đổi trạng thái**. Cần UPDATE chủ động để job trở lại pending hoặc dead.

### 17.2. Tranh chấp heartbeat và reaper

Nếu heartbeat gia hạn trước khi reaper xử lý hàng, reaper cần đánh giá điều kiện hết hạn với trạng thái cập nhật. Nếu reaper đã reset hàng, heartbeat cũ với token/status không còn khớp sẽ trả 0.

### 17.3. Chạy reaper theo batch

Với hàng triệu jobs, không nên giữ một transaction UPDATE tất cả expired rows. Có thể dùng CTE chọn batch `LIMIT n FOR UPDATE SKIP LOCKED`, rồi UPDATE, COMMIT và lặp có giới hạn.

### 17.4. Reaper không biết external effect

Một email có thể đã gửi thành công nhưng worker crash trước ack. Reaper retry job nên có thể gửi email lần nữa. Đây là lý do idempotency phải được thiết kế ở handler/đích.

## 18. Stale worker và fencing

Timeline:

~~~text
t0: Worker A claim job 42, token A1, version 7.
t1: A bị pause hoặc mất mạng, không heartbeat.
t2: Lease A hết, reaper requeue.
t3: Worker B claim job 42, token B1, version 8.
t4: A thức dậy và cố ack hoặc gọi API.
~~~

### 18.1. Token chặn ack cũ trong PostgreSQL

Ack có `WHERE claim_token=A1` trả 0 sau khi B claim với token B1. Điều đó bảo vệ dữ liệu trạng thái job.

### 18.2. Version là fencing number

`claim_version` tăng từ 7 lên 8. Nếu external resource hỗ trợ so sánh số phiên bản và từ chối phiên bản cũ, nó có thể ngăn A thực hiện side effect stale sau khi B đã tiếp nhận.

### 18.3. Token không tự chặn API ngoài

Nếu API đích không hỗ trợ idempotency/fencing, A vẫn có thể hoàn tất request ngoài DB mặc dù DB từ chối ack. Không nhầm database ownership với quyền kiểm soát vật lý trên tiến trình/HTTP call.

### 18.4. Worker nên làm gì khi mất quyền?

Ngừng những bước có thể dừng an toàn, đánh giá tác động đã phát sinh, và không commit trạng thái DB bằng token cũ. Với tác vụ không thể hủy, cần protocol idempotency/reconciliation.

## 19. Delivery semantics: at-most-once, at-least-once, exactly-once

| Thuật ngữ | Ý nghĩa thực hành | Đánh đổi |
|---|---|---|
| At-most-once attempt | Không retry sau khi đã giao | Có thể mất job nếu worker crash |
| At-least-once attempt | Retry khi không ack, trong giới hạn/policy | Có thể xử lý trùng |
| Exactly-once effect | Tác động cuối chỉ xảy ra một lần | Cần phối hợp toàn bộ hệ thống đích |

### 19.1. Cửa sổ crash quan trọng

~~~text
Claim job -> COMMIT
Gọi payment API -> provider đã charge
Worker crash trước ACK
Reaper -> pending
Worker B gọi payment API lại
~~~

Nếu provider không có idempotency key, có nguy cơ charge hai lần.

### 19.2. Tại sao row lock không giải quyết được?

Database transaction không bao gồm commit của provider bên ngoài. Lock trên row jobs không thể rollback hoặc chặn một request đã gửi tới provider.

### 19.3. “At-least-once” cũng có điều kiện

Một thiết kế cần durable storage, worker tiếp tục polling, reaper, retry policy, năng lực xử lý và monitoring. Nếu tất cả worker ngừng vĩnh viễn hoặc job bị dead sau max_attempts, không thể hứa mọi job chắc chắn hoàn tất.

### 19.4. Dedupe enqueue khác idempotency execution

Unique dedupe key chỉ ngăn tạo job trùng. Job đó có thể được claim lại nhiều lần. Handler phải biết cùng operation đã được thực hiện hay chưa.

## 20. Handler idempotent

Một thao tác idempotent cho cùng **logical operation ID** có kết quả cuối không nhân đôi khi lặp.

### 20.1. Mẫu sai: trừ số dư trực tiếp

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
~~~

Nếu retry, số dư có thể bị trừ lần nữa.

### 20.2. Ghi ledger với unique operation key

~~~sql
CREATE TABLE queue_lab.debit_ledger (
    debit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_key TEXT NOT NULL UNIQUE,
    account_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu account balance cũng nằm trong cùng PostgreSQL database, có thể xây transaction để INSERT ledger rồi chỉ khi operation key mới thực hiện UPDATE balance. Bản ghi ledger và thay đổi balance phải commit cùng nhau; khi conflict, không trừ thêm.

Đây là nguyên tắc, không phải bài toán kế toán đã được giải quyết chỉ bằng một bảng.

### 20.3. Idempotency key phải ổn định qua retry

Dùng `operation_key` hoặc `dedupe_key` ổn định theo nghiệp vụ để truyền sang external API. Không dùng `claim_token` làm idempotency key nếu token thay đổi mỗi lần claim khiến provider coi là giao dịch mới.

### 20.4. Kiểm tra retention của key

Một provider có thể chỉ lưu idempotency key trong thời gian hạn chế. Nếu job retry sau thời hạn đó, side effect vẫn có thể xảy ra lần nữa. Recovery window và TTL key phải tương thích.

## 21. Transactional outbox

Một lỗi thường gặp:

~~~text
COMMIT order
Ứng dụng crash
Không kịp INSERT job gửi email
~~~

Nếu job được INSERT trong cùng transaction với business data, không có khoảng trống commit giữa hai bước đó.

~~~sql
BEGIN;

-- INSERT INTO orders ... RETURNING order_id;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'events',
    'order-created:ORD-1001',
    'publish_order_created',
    '{"order_code":"ORD-1001"}'::jsonb
);

COMMIT;
~~~

### 21.1. Outbox không tự thành exactly-once publishing

Worker gửi message ra broker rồi crash trước ack vẫn có thể publish lại. Consumer hoặc hệ đích cần idempotency.

### 21.2. Khi nào tách outbox và jobs?

Nếu ứng dụng có nhiều consumer groups, replay/retention dài hoặc workflow broadcast, outbox và worker queue có thể cần hai mô hình tách biệt.

## 22. Priority, fairness và ordering

Câu claim:

~~~sql
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED
~~~

chỉ đặt **thứ tự xét candidate**.

### 22.1. Không có strict FIFO

Job đầu có thể đang khóa, job sau được claim trước. Worker nhanh có thể hoàn tất trước worker chậm. Retry có thể đưa job cũ quay lại sau.

### 22.2. Starvation

Nếu liên tục có jobs priority cao, jobs priority thấp có thể chờ vô hạn. Có thể cần aging, quotas, worker pools riêng theo queue/priority, hoặc SLA cho tuổi job.

### 22.3. Thứ tự theo customer

Nếu job B của cùng một customer **phải** chạy sau job A, SKIP LOCKED trên toàn queue không bảo đảm. Cần protocol per-key: sharding/partition workers, một guard row, sequence watermark, hoặc một cấu trúc dependency phù hợp.

### 22.4. Job_id không phải thứ tự hoàn tất

IDENTITY/sequence có thể có gaps, và thứ tự cấp ID không chứng minh thứ tự COMMIT hoặc completion.

## 23. Isolation level phù hợp

### 23.1. READ COMMITTED

Queue claim thường dùng `READ COMMITTED` với transaction ngắn. Khi nhiều writers tranh chấp, row locks và điều kiện trong UPDATE phối hợp để tránh hai worker cùng commit claim một pending row.

### 23.2. REPEATABLE READ

Giữ snapshot transaction ổn định có thể không hữu ích cho polling queue; concurrent updates sau snapshot có thể dẫn tới lỗi serialization/concurrent update. Không mặc định mức này làm queue an toàn hơn theo mọi nghĩa.

### 23.3. SERIALIZABLE

Khi các transaction cần giữ invariant nhiều hàng, Serializable Snapshot Isolation có thể cần thiết, nhưng SQLSTATE `40001` phải được retry **toàn transaction**.

### 23.4. SKIP LOCKED không thay isolation

Nó quyết định cách xử lý **một yêu cầu row lock bị cản trở**, không thay thế snapshot semantics hay bảo đảm serializability.

## 24. Claim một batch

Để giảm round trips:

~~~sql
BEGIN;

WITH picked AS MATERIALIZED (
    SELECT job_id
    FROM queue_lab.jobs
    WHERE queue_name = 'emails'
      AND status = 'pending'
      AND run_at <= statement_timestamp()
      AND attempts < max_attempts
    ORDER BY priority DESC, run_at, job_id
    LIMIT 10
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_lab.jobs AS j
SET status = 'running',
    claimed_by = 'worker-B',
    claim_token = gen_random_uuid(),
    claim_version = j.claim_version + 1,
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    attempts = j.attempts + 1,
    updated_at = statement_timestamp()
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING j.job_id, j.job_type, j.payload,
          j.claim_token, j.claim_version;

COMMIT;
~~~

### 24.1. Batch size giới hạn bởi lease

Nếu claim 100 jobs, mỗi job mất 10s và chỉ xử lý tuần tự, những jobs ở cuối có thể hết lease trước khi tới lượt. Claim số job phù hợp số worker slots và nhịp heartbeat.

### 24.2. RETURNING không phải promise về thứ tự

UPDATE RETURNING không tự bảo đảm trả rows theo đúng ORDER BY trong picked. Nếu cần sắp thứ tự payload sau claim, hãy xử lý thứ tự đó rõ trong ứng dụng.

## 25. Polling và LISTEN/NOTIFY

Worker có thể polling:

~~~text
while running:
    claim up to N jobs
    if no job:
        sleep with bounded backoff
    else:
        process jobs
~~~

Không nên chạy vòng SELECT không nghỉ trên queue rỗng, vì sẽ tốn CPU/database connections.

### 25.1. LISTEN/NOTIFY để đánh thức nhanh hơn

Worker có thể:

~~~sql
LISTEN job_wakeup;
~~~

Producer có thể:

~~~sql
BEGIN;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails', 'lab:wakeup:1',
    'send_mail', '{"to":"demo"}'::jsonb
);

SELECT pg_notify('job_wakeup', 'emails');

COMMIT;
~~~

### 25.2. NOTIFY không bền vững như queue

Nếu worker mất kết nối hoặc chưa LISTEN, nó có thể bỏ lỡ notify. Hàng job vẫn được lưu trong bảng nếu transaction enqueue đã commit.

**NOTIFY là tín hiệu đánh thức; polling định kỳ vẫn phải tồn tại để phục hồi.**

### 25.3. Một NOTIFY không tương ứng chính xác một job

Có thể có nhiều jobs trước khi worker thức dậy, hoặc worker thức dậy nhưng không có job phù hợp do worker khác đã claim. Worker vẫn cần truy vấn queue và xử lý trạng thái thực tế.

## 26. Các cửa sổ crash

| Điểm crash | Trạng thái có thể có | Điều cần xử lý |
|---|---|---|
| Trước COMMIT enqueue | Job chưa được commit | Retry producer có idempotency |
| Sau COMMIT enqueue | Pending | Worker có thể claim |
| Trong transaction claim trước COMMIT | Claim rollback | Job có thể được claim lại |
| Sau COMMIT claim, trước external call | Running | Lease hết và reaper |
| Trong external call | Running | Outcome có thể không rõ |
| Sau external effect, trước ack | Running | Retry có thể lặp effect |
| Trong transaction ack, trước COMMIT | Có thể rollback ack | Idempotency vẫn cần |
| Sau COMMIT ack | Succeeded | Monitoring và retention |

### 26.1. Crash sau side effect là kịch bản trọng tâm

Không thể “khóa thêm một hàng” để bảo đảm email provider hoặc payment provider không xử lý trùng trong mọi kịch bản. Cần operation ID ổn định và cơ chế dedupe ở đích.

### 26.2. Kết quả ack không rõ

Kết nối có thể rớt sau COMMIT ack thành công nhưng trước response. Worker không nên suy ra ack thất bại chỉ từ việc mất gói; phải đọc trạng thái hoặc xử lý idempotent.

## 27. Hủy job

~~~sql
UPDATE queue_lab.jobs
SET status = 'cancelled',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'pending'
RETURNING job_id, status;
~~~

### 27.1. Pending job

Nếu job chưa claim, điều kiện status giúp cancel an toàn theo trạng thái hiện tại.

### 27.2. Running job

Nếu job đang gọi API ngoài, đổi status trong DB không tự dừng thread hoặc hủy HTTP request. Cần cancellation protocol: worker kiểm tra flag, hợp đồng hủy an toàn với provider, hoặc xử lý compensate nếu không thể hủy.

### 27.3. Concurrent cancel và claim

Hai transaction tranh chấp cùng hàng. Cả hai phải kiểm tra số hàng UPDATE/RETURNING; không được coi mọi nhánh cùng thành công.

## 28. Dead-letter và replay

Một job lỗi liên tục cần có ngưỡng retry, ví dụ `max_attempts=5`. Sau đó:

~~~text
status = dead
~~~

### 28.1. Không xóa dead jobs ngay

Giữ trong thời gian phù hợp để điều tra, phân loại lỗi, kiểm tra external outcome và sửa payload/handler.

### 28.2. Replay thủ công cần được kiểm soát

Không đơn giản chuyển mọi job dead sang pending khi chưa kiểm tra đã có side effect hay chưa. Đặc biệt nhạy cảm với payment, email marketing và những tác vụ không thể hoàn tác.

### 28.3. Quyền và audit

Replay cần quyền tối thiểu, lý do hành động, dấu vết người thực hiện và giới hạn số lần thử. Payload/last_error có thể chứa dữ liệu nhạy cảm.

## 29. Hiệu năng: update churn và VACUUM

Queue thường có nhiều chuyển trạng thái:

~~~text
pending -> running -> succeeded
pending -> running -> pending -> running -> dead
~~~

Với MVCC, UPDATE tạo những phiên bản hàng mới trong nhiều trường hợp. Bảng queue có thể tăng dead tuples, WAL và index churn.

### 29.1. HOT updates không phải lúc nào cũng có

Khi UPDATE cột tham gia index hoặc thay trạng thái khiến hàng ra/vào partial index, nhiều trường hợp không tận dụng HOT. Không coi mọi UPDATE status là miễn phí.

### 29.2. Retention

Không nên giữ vô hạn tất cả succeeded rows nếu chúng làm bảng chính quá lớn. Có thể archive/delete theo batch, tránh transaction dọn dẹp khổng lồ.

### 29.3. Large payload

JSONB lớn gây chi phí I/O, backup và xử lý. Có thể lưu tham chiếu tới dữ liệu lưu trữ khác, với các quy tắc nhất quán và quyền truy cập riêng.

### 29.4. Partitioning

Queue cực lớn có thể cần phân vùng theo thời gian/tenant hoặc cách khác, nhưng partitioning không miễn phí. Partition theo status có thể làm update status trở thành chuyển hàng giữa partitions; phải đánh giá constraints, lock và tốc độ thực tế.

### 29.5. Broker chuyên dụng

Nếu cần hàng trăm consumer groups, replay dài hạn, fan-out lớn hoặc routing phức tạp, broker có thể phù hợp hơn. Nhưng broker cũng không tự giải quyết exactly-once side effects ngoài hệ thống.

## 30. Timestamps và đồng hồ

### 30.1. TIMESTAMPTZ

Dùng `TIMESTAMPTZ` cho run_at, claimed_at, lease_until, created_at, vì chúng biểu diễn instant, không phải giờ địa phương mơ hồ.

### 30.2. now() khác statement_timestamp()

`now()</BT> là thời điểm bắt đầu transaction. Nếu BEGIN rồi để chờ lâu, việc tính lease với now() có thể sử dụng mốc cũ. `statement_timestamp()</BT> cho mốc bắt đầu statement hiện tại.

### 30.3. clock_timestamp()

`clock_timestamp()</BT> có thể thay đổi ngay trong một statement. Cần dùng có chủ đích; dùng một thời điểm statement nhất quán thường giúp query claim dễ hiểu.

### 30.4. Đồng hồ worker

Nếu nhiều máy worker có clock drift, tự tính lease_until ở từng host dễ gây lệch. Thường nên để PostgreSQL tính mốc lease trong SQL.

### 30.5. Clock drift không thay thế token

Dù thời gian chính xác, một worker cũ vẫn có thể gửi side effect sau khi lease hết. Claim token, fencing hoặc idempotency vẫn cần thiết.

## 31. Timeouts và isolation cho queue

Có thể đặt guardrails cho transaction claim:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '400ms';
SET LOCAL statement_timeout = '3s';

-- Claim một hoặc một batch jobs tại đây.

COMMIT;
~~~

- `lock_timeout`: giới hạn chờ lấy lock, không phải tổng thời gian xử lý job.
- `statement_timeout`: giới hạn một câu SQL, không phải lease.
- `lease_until`: dữ liệu nghiệp vụ về quyền xử lý giữa các transaction.
- `idle_in_transaction_session_timeout`: bảo vệ khỏi session idle nhưng giữ transaction lâu.

### 31.1. Error codes cần phân biệt

| SQLSTATE | Ngữ cảnh |
|---|---|
| `55P03` | Lock not available/lock timeout/NOWAIT |
| `57014` | Query canceled, trong đó có statement timeout |
| `40P01` | Deadlock |
| `40001` | Serialization failure |
| `23505` | Unique violation |

Retry cần phân loại lỗi, rollback transaction lỗi, đánh giá lại điều kiện và giới hạn attempts. Không retry mọi lỗi ngay lập tức.

## 32. Quan sát queue và worker

### 32.1. Số job theo trạng thái

~~~sql
SELECT queue_name, status, COUNT(*) AS jobs
FROM queue_lab.jobs
GROUP BY queue_name, status
ORDER BY queue_name, status;
~~~

### 32.2. Số job pending đã sẵn sàng

~~~sql
SELECT queue_name, COUNT(*) AS ready_jobs
FROM queue_lab.jobs
WHERE status = 'pending'
  AND run_at <= statement_timestamp()
GROUP BY queue_name;
~~~

### 32.3. Tuổi job pending

~~~sql
SELECT
    queue_name,
    MIN(created_at) AS oldest_created_at,
    MAX(statement_timestamp() - created_at) AS max_pending_age
FROM queue_lab.jobs
WHERE status = 'pending'
GROUP BY queue_name;
~~~

Số này tính từ khi tạo, bao gồm jobs hẹn tương lai; nếu cần **quá hạn run_at**, phải tính metric riêng.

### 32.4. Jobs đã hết lease

~~~sql
SELECT COUNT(*) AS expired_running
FROM queue_lab.jobs
WHERE status = 'running'
  AND lease_until <= statement_timestamp();
~~~

### 32.5. Dead jobs gần đây

~~~sql
SELECT
    job_id, queue_name, job_type,
    attempts, max_attempts,
    LEFT(last_error, 200) AS error_excerpt,
    updated_at
FROM queue_lab.jobs
WHERE status = 'dead'
ORDER BY updated_at DESC
LIMIT 100;
~~~

## 33. Quan sát lock và bloat

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

### 33.1. pg_locks

~~~sql
SELECT pid, locktype, mode, granted,
       relation::regclass AS relation_name
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

`pg_locks` hiển thị locks hiện tại, không phải lịch sử ai đã xử lý job nào.

### 33.2. Statistics bảng queue

~~~sql
SELECT
    schemaname, relname,
    n_live_tup, n_dead_tup,
    n_tup_ins, n_tup_upd, n_tup_del,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'queue_lab';
~~~

Các thống kê gồm ước lượng/tổng tích lũy, không phải COUNT chính xác theo trạng thái tại mọi thời điểm.

### 33.3. Những metrics cần alert

- Pending count/ready age vượt ngưỡng.
- Expired running count tăng.
- Dead jobs tăng.
- Worker throughput giảm.
- Retry và failures tăng.
- DB connection pool cạn.
- 55P03/57014/40001/40P01 tăng.
- Dead tuples/index size tăng nhanh.
- P95/P99 enqueue-to-ack vượt SLA.

## 34. Bảo mật và multi-tenancy

### 34.1. Quyền tối thiểu

Producer thường cần INSERT, worker cần SELECT/UPDATE có kiểm soát, reaper cần quyền phục hồi, operator có quyền replay và DBA quyền migration. Không cho mọi worker superuser.

### 34.2. Tenant isolation

Nếu nhiều tenant chia sẻ bảng, nên lưu tenant_id và giới hạn claim theo tenant/queue; dùng authorization và có thể Row-Level Security theo thiết kế.

### 34.3. Payload có thể nhạy cảm

Đừng đưa password hoặc access token dài hạn vào JSONB payload nếu không có cơ chế bảo vệ. Payload có thể xuất hiện trong backups, logs, metrics và truy vấn debug.

### 34.4. Handler registration

Ánh xạ `job_type` vào handler đã đăng ký trong code. Không nối payload tùy ý thành shell command hoặc SQL không kiểm soát.

## 35. Những hiểu lầm phổ biến

### 35.1. “SKIP LOCKED bảo đảm exactly-once”

Sai. Nó giúp tránh chọn cùng hàng đang khóa trong giai đoạn claim, không ngăn retry sau crash.

### 35.2. “Claim COMMIT rồi lock vẫn giữ đến hết lease”

Sai. Row lock kết thúc theo transaction; lease chỉ là trạng thái trong bảng.

### 35.3. “Lease hết chắc chắn worker đã chết”

Sai. Worker có thể bị pause hoặc mất mạng rồi hoạt động lại.

### 35.4. “Có token là email không bao giờ trùng”

Sai. Token trong DB không ngăn HTTP side effect cũ nếu provider không hỗ trợ idempotency/fencing.

### 35.5. “Unique dedupe_key là đủ để không gửi email trùng”

Sai. Nó ngăn enqueue trùng nhưng job có thể retry nhiều lần.

### 35.6. “SKIP LOCKED giữ đúng FIFO”

Sai. Job đang khóa có thể bị bỏ qua; thứ tự hoàn tất còn khác vì thời lượng job.

### 35.7. “Running tự về pending sau khi lease hết”

Sai. Cần reaper hoặc một tác vụ phục hồi chủ động.

### 35.8. “LISTEN/NOTIFY là hàng đợi bền vững”

Sai. Notification là tín hiệu; job nằm trong bảng. Worker cần polling dự phòng.

### 35.9. “Mọi lỗi nên retry ngay”

Sai. Có lỗi vĩnh viễn, dữ liệu không hợp lệ và external outcome không rõ. Cần phân loại, backoff, dead-letter và reconciliation.

### 35.10. “Bật SERIALIZABLE giúp đúng một lần ngoài DB”

Sai. SSI bảo vệ tính tuần tự hóa giao dịch PostgreSQL, không commit nguyên tử với payment/email service.

### 35.11. “Worker có thể giữ một transaction trong suốt 30 phút xuất báo cáo”

Có thể về mặt kỹ thuật nhưng thường là thiết kế kém cho queue, tăng locks, connection occupation và MVCC pressure.

### 35.12. “Batch càng lớn càng tốt”

Sai. Claim quá nhiều jobs có thể khiến lease hết trước khi thực thi.

### 35.13. “Hàng đã UPDATE status không tạo chi phí lớn”

Sai. Queue churn tạo nhiều WAL, dead tuples, index writes và nhu cầu VACUUM.

### 35.14. “Một job có job_id nhỏ hơn chắc chắn xử lý xong trước”

Sai. Priority, SKIP LOCKED, retries và tốc độ worker làm thay đổi thứ tự.

### 35.15. “Client HTTP timeout nghĩa là enqueue thất bại”

Không chắc. Transaction có thể đã COMMIT nhưng response bị mất; cần idempotency key và tra cứu trạng thái.

## 36. Bài tập thực hành

### Bài 1 — Race condition

Hai workers cùng SELECT một hàng pending mà không khóa. Vì sao có thể xử lý trùng?

**Gợi ý:** Cả hai cùng nhìn thấy status pending trước khi có UPDATE claim.

### Bài 2 — FOR UPDATE

FOR UPDATE bảo vệ hàng trong bao lâu?

**Đáp án:** Trong phạm vi transaction còn giữ row lock.

### Bài 3 — SKIP LOCKED

Worker A khóa job đầu, worker B muốn lấy job kế tiếp mà không chờ. Cú pháp gì?

**Đáp án:** FOR UPDATE SKIP LOCKED.

### Bài 4 — NOWAIT

Nếu phải thao tác đúng hàng bị khóa và không muốn chờ, dùng gì?

**Đáp án:** FOR UPDATE NOWAIT khi phù hợp.

### Bài 5 — Claim nguyên tử

Vì sao nên kết hợp SELECT FOR UPDATE SKIP LOCKED trong CTE với UPDATE trạng thái?

**Gợi ý:** Chọn và nhận job dưới cùng transaction.

### Bài 6 — COMMIT claim

Vì sao không giữ transaction trong lúc gọi email provider?

**Gợi ý:** Không giữ locks/connections kéo dài; external effect cũng không rollback cùng DB.

### Bài 7 — Lease

Lease khác row lock ở điểm nào?

**Gợi ý:** Lease là dữ liệu thời hạn; row lock do PostgreSQL quản lý theo transaction.

### Bài 8 — Stale ack

Worker A mất lease, B claim lại. WHERE nào ngăn A ack?

**Gợi ý:** Kiểm tra token/status/worker ID và lease.

### Bài 9 — Heartbeat

Nếu heartbeat UPDATE trả 0 hàng, worker nên làm gì?

**Gợi ý:** Coi quyền sở hữu có thể đã mất, không ack mù quáng.

### Bài 10 — Reaper

Một job running hết lease có tự về pending không?

**Đáp án:** Không, cần reaper.

### Bài 11 — Crash

Worker gửi email thành công rồi crash trước ack. Điều gì xảy ra khi retry?

**Gợi ý:** Có thể gửi email lần nữa.

### Bài 12 — Exactly-once

SKIP LOCKED có bảo đảm exactly-once external effect không?

**Đáp án:** Không.

### Bài 13 — At-most-once

Không retry để tránh trùng có rủi ro gì?

**Gợi ý:** Mất job nếu worker crash.

### Bài 14 — At-least-once

Retry khi thiếu ack có đánh đổi gì?

**Gợi ý:** Có thể thực thi lặp.

### Bài 15 — Dedupe key

Vì sao unique dedupe_key chưa đủ bảo đảm external effect duy nhất?

**Gợi ý:** Dedupe enqueue khác retry execution.

### Bài 16 — Token với external API

Nên dùng claim_token hay operation_key ổn định làm idempotency key cho provider?

**Đáp án:** Operation key ổn định.

### Bài 17 — Fencing version

claim_version tăng qua các lượt claim giúp gì?

**Gợi ý:** Đích hỗ trợ fencing có thể từ chối thao tác phiên bản cũ.

### Bài 18 — Max attempts

Nếu attempts đã đạt max_attempts sau lỗi, job nên chuyển sang trạng thái nào?

**Gợi ý:** Dead-letter/dead theo policy.

### Bài 19 — Backoff

Vì sao cần jitter?

**Gợi ý:** Tránh hàng nghìn jobs retry đồng loạt.

### Bài 20 — Transactional outbox

Tại sao enqueue job và INSERT order nên nằm trong cùng transaction khi cần tính nguyên tử?

**Gợi ý:** Không mất job nếu ứng dụng crash giữa hai COMMIT.

### Bài 21 — Scheduling

Query claim cần điều kiện gì để không chạy job trước giờ?

**Đáp án:** run_at <= thời gian hiện tại của statement.

### Bài 22 — Partial index

Index với `WHERE status='pending'` có mục đích gì?

**Gợi ý:** Giảm tập dữ liệu cần truy cập khi claim.

### Bài 23 — Dynamic index

Vì sao không tạo partial index với `WHERE run_at <= now()`?

**Gợi ý:** Predicate yêu cầu tính bất biến, now() thay đổi theo thời gian.

### Bài 24 — Fairness

Priority cao xuất hiện liên tục có thể gây chuyện gì cho jobs ưu tiên thấp?

**Đáp án:** Starvation.

### Bài 25 — FIFO

Hai worker có bảo đảm job_id 10 hoàn tất trước job_id 11 không?

**Đáp án:** Không.

### Bài 26 — Queue theo customer

Nếu các jobs cùng customer bắt buộc tuần tự, cần gì thêm?

**Gợi ý:** Per-key serialization protocol/partition/guard row.

### Bài 27 — Batch

Worker claim 100 jobs mỗi job mất 20s với lease 1 phút. Rủi ro gì?

**Gợi ý:** Lease hết trước khi job được xử lý.

### Bài 28 — LISTEN/NOTIFY

Nếu worker bỏ lỡ notification, job đã commit có mất không?

**Đáp án:** Không; polling tìm được trong bảng.

### Bài 29 — Cancel

Đổi status cancelled của job running có tự dừng HTTP request không?

**Đáp án:** Không.

### Bài 30 — Clock

Tại sao statement_timestamp() có thể thích hợp hơn now() khi transaction mở từ lâu?

**Gợi ý:** now() giữ mốc bắt đầu transaction.

### Bài 31 — Monitoring

Nêu năm metrics cần theo dõi.

**Gợi ý:** Ready count, pending age, expired leases, dead jobs, throughput/retry.

### Bài 32 — MVCC

Vì sao queue cập nhật trạng thái liên tục có thể tạo bloat?

**Gợi ý:** Dead tuples, index churn và WAL.

### Bài 33 — RLS

Queue multi-tenant cần bảo vệ điều gì?

**Gợi ý:** Worker không được đọc/claim payload tenant khác.

### Bài 34 — Idempotency khi timeout

Client không nhận response enqueue nhưng DB có thể đã commit. Làm sao tránh job trùng?

**Gợi ý:** Stable dedupe_key + UNIQUE + tra cứu trạng thái.

### Bài 35 — Chọn kiến trúc

Khi nào nên cân nhắc message broker thay vì queue thuần PostgreSQL?

**Gợi ý:** Nhiều consumer groups, fan-out lớn, replay/retention, throughput/routing vượt khả năng DB.

## 37. Bảng ghi nhớ nhanh

| Mục tiêu | Công cụ hoặc nguyên tắc |
|---|---|
| Chọn job có khóa | SELECT ... FOR UPDATE |
| Không chờ hàng đang khóa | FOR UPDATE SKIP LOCKED |
| Fail fast khi khóa bị giữ | FOR UPDATE NOWAIT |
| Claim nguyên tử | CTE candidate + UPDATE ... RETURNING |
| Nhả DB lock sớm | COMMIT ngay sau claim |
| Ghi nhận worker đang xử lý | status='running' |
| Phục hồi sau crash | Lease + reaper |
| Gia hạn lease | Heartbeat có ownership guard |
| Chặn stale ack | WHERE claim_token + status |
| Chặn stale external effect | Fencing/idempotency tại đích |
| Ngăn enqueue trùng | UNIQUE(queue_name,dedupe_key) |
| Retry có kiểm soát | run_at, attempts, max_attempts, backoff |
| Hỏng vĩnh viễn | Dead-letter |
| Order và job cùng commit | Transactional outbox |
| Đánh thức worker | LISTEN/NOTIFY + polling |
| Bảo đảm FIFO tuyệt đối | SKIP LOCKED không tự bảo đảm |
| Bảo đảm exactly-once bên ngoài | Không do row lock tự cấp |
| Tránh starvation | Aging/quotas/capacity allocation |
| Tránh DB bloat | Index phù hợp, VACUUM, retention |
| Đo tình trạng queue | Status count, lag, expired lease, dead count |
| Quan sát locks | pg_stat_activity, pg_locks, pg_blocking_pids |
| Phân biệt DB timeout với lease | statement_timeout/lock_timeout khác lease_until |
| Bảo vệ payload | Least privilege, RLS, secrets policy |

---

## Kết luận

PostgreSQL có thể xây dựng một hàng đợi công việc hiệu quả bằng **bảng jobs, transaction ngắn và `SELECT ... FOR UPDATE SKIP LOCKED`**. Một câu claim nguyên tử chọn job phù hợp, bỏ qua hàng đang khóa, chuyển trạng thái sang running và trả token/lease cho worker. Sau COMMIT, worker thực hiện tác vụ ngoài database rồi ghi ack có kiểm tra quyền sở hữu.

Điều quan trọng là **khóa hàng chỉ bảo vệ giai đoạn claim**. Lease giúp phát hiện lượt xử lý bị bỏ dở, reaper giúp đưa job trở lại pending và retry giúp phục hồi sau crash. Đổi lại, worker cũ có thể vẫn chạy sau khi lease hết, và job có thể bị thực thi lại. Vì vậy cần **claim token, fencing khi được hỗ trợ, idempotency key ổn định, heartbeat, dead-letter và monitoring**.

`SKIP LOCKED` cũng cố ý đánh đổi khả năng quan sát đầy đủ các hàng đang khóa để tăng throughput. Nó không bảo đảm strict FIFO, sự công bằng giữa các độ ưu tiên hay thứ tự hoàn tất. Đối với những tác vụ có side effect bên ngoài PostgreSQL, **không thể suy ra exactly-once chỉ từ row locks hoặc transaction DB**.

Một thiết kế queue đúng cần giải quyết đồng thời hai câu hỏi: **“Làm sao không hai worker claim cùng một job tại cùng thời điểm?”** và **“Nếu worker crash sau khi đã thực hiện tác vụ, lần retry phải xử lý thế nào?”**. PostgreSQL row locks giải quyết phần đầu; retry protocol, idempotency và phối hợp với hệ thống đích mới giải quyết được phần sau.
