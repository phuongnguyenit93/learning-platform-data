# Tự động hóa script có kiểm soát lỗi, timeout và nhật ký trong PostgreSQL

## 1. Vì sao script quản trị cần cơ chế kiểm soát?

Các công việc PostgreSQL lặp lại thường được tự động hóa bằng SQL scripts, psql, shell, Python, scheduler hoặc CI/CD. Ví dụ: chạy migration, cấp quyền, kiểm tra replication, refresh dữ liệu, phân tích bảng, tạo báo cáo, dọn dữ liệu theo batch và thực hiện maintenance.

Tự động hóa giúp công việc nhất quán và giảm thao tác thủ công. Tuy nhiên, một script có thể gây ảnh hưởng lớn nếu chạy sai database, chạy đồng thời hai lần, chờ lock vô hạn, tiếp tục sau một câu SQL lỗi, ghi log chứa password hoặc báo thành công dù transaction đã rollback.

Một script vận hành đáng tin cậy cần xác định rõ:

- **Phạm vi:** cluster, database, schema, objects và identity nào được phép tác động?
- **Điều kiện trước khi chạy:** server version, role, topology, backup, disk headroom và trạng thái ứng dụng có đáp ứng không?
- **Tính an toàn:** thao tác có idempotent không, có transaction được không, có dry-run hoặc phương án hoàn tác không?
- **Lỗi:** SQL error, mất kết nối, permission denied, deadlock và lỗi hệ điều hành được phân loại thế nào?
- **Timeout:** kết nối, chờ lock, câu SQL và toàn bộ job có giới hạn riêng không?
- **Đồng thời:** làm sao tránh hai scheduler chạy cùng một tác vụ?
- **Quan sát:** ai chạy, chạy ở đâu, mất bao lâu, tác động bao nhiêu rows và kết quả ra sao?
- **Kết thúc:** exit code có phản ánh đúng kết quả để scheduler/CI nhận biết không?

Mục tiêu của bài này là xây dựng cách tự động hóa có thể kiểm soát, quan sát và khôi phục. Một script hoàn tất mà không có bằng chứng về kết quả chưa thể được xem là một lần chạy thành công.

```text
              SCHEDULE / OPERATOR
                      |
                      v
             Validate target and inputs
                      |
                      v
              Acquire job ownership
                      |
                      v
             Connect with bounded wait
                      |
                      v
              Run guarded SQL steps
                /             \
               v               v
             Success          Error
               |               |
               v               v
            Commit         Rollback/stop
               |               |
               +-------+-------+
                       |
                       v
             Write result and metrics
                       |
                       v
               Exit with status code
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế script PostgreSQL có preconditions, scope và exit criteria.
2. Dùng psql ở chế độ non-interactive và fail-fast.
3. Phân biệt exit codes của psql.
4. Quản lý transaction và hiểu giới hạn của transactional DDL.
5. Thiết lập connection timeout, lock timeout và statement timeout.
6. Đặt giới hạn thời gian cho toàn bộ job.
7. Phân biệt client timeout với server-side cancellation.
8. Xử lý lỗi SQL, mất kết nối, deadlock và serialization failure.
9. Thiết kế retry có giới hạn, backoff và idempotency.
10. Ngăn chạy đồng thời bằng advisory locks hoặc scheduler locks.
11. Ghi log có timestamp, run ID, target và kết quả.
12. Bảo vệ password, connection strings và dữ liệu nhạy cảm trong logs.
13. Dùng shell error handling và traps đúng cách.
14. Kiểm tra số rows và điều kiện sau mỗi bước quan trọng.
15. Thiết kế dry-run, batch processing và checkpoint.
16. Tách thao tác transactional khỏi thao tác không chạy trong transaction.
17. Theo dõi script qua application_name và PostgreSQL statistics.
18. Tổ chức job bằng cron, systemd hoặc CI/CD.
19. Xây runbook cho timeout, failure, retry và recovery.
20. Lưu evidence để audit và cải thiện automation.

## 3. Phân loại lỗi trước khi viết script

Không phải mọi lỗi đều có cùng cách xử lý. Cần phân loại để quyết định dừng, retry, rollback hay yêu cầu operator can thiệp.

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
| --- | --- | --- |
| Input/configuration | Thiếu database name, sai environment | Dừng trước khi kết nối |
| Authentication | Password hết hạn, auth rule sai | Dừng, sửa credential/config |
| Connection | Server không reachable, DNS lỗi | Retry giới hạn nếu phù hợp |
| Permission | SQLSTATE 42501 | Dừng, review quyền |
| Syntax/object | SQLSTATE 42601, 42P01 | Dừng, sửa script/schema |
| Constraint/data | Unique/FK/check violation | Dừng hoặc xử lý theo nghiệp vụ |
| Lock contention | SQLSTATE 55P03 hoặc lock timeout | Retry toàn transaction nếu idempotent |
| Deadlock | SQLSTATE 40P01 | Retry toàn transaction có giới hạn |
| Serialization | SQLSTATE 40001 | Retry toàn transaction |
| Statement timeout | SQLSTATE 57014 | Dừng hoặc điều tra; không retry mù quáng |
| Connection loss | SQLSTATE class 08 hoặc client disconnect | Xác định transaction outcome trước retry |
| Resource exhaustion | Disk full, OOM, too many connections | Dừng và xử lý capacity |
| External process | Scheduler, filesystem hoặc network error | Dừng và lưu exit code |

### 3.1. Fail fast

Lỗi cấu hình, thiếu quyền, sai object hoặc dữ liệu không hợp lệ thường không tự hết khi retry. Chạy lại nhiều lần chỉ tạo thêm tải và log nhiễu.

### 3.2. Retry có điều kiện

Deadlock và serialization failure có thể xảy ra do concurrency bình thường. PostgreSQL yêu cầu client retry toàn bộ transaction trong một số trường hợp này. Không chỉ chạy lại statement cuối cùng nếu transaction trước đã rollback.

### 3.3. Kết quả commit không rõ

Nếu kết nối đứt đúng lúc client gửi COMMIT hoặc đang chờ response, client có thể không biết transaction đã commit hay chưa. Không được giả định mất kết nối nghĩa là transaction rollback. Cần idempotency key, operation ledger hoặc truy vấn đối soát trước khi retry.

### 3.4. Không nuốt lỗi

Một script không nên in “success” sau khi đã bỏ qua SQL error. Mọi lỗi ảnh hưởng outcome phải tạo exit status khác 0 hoặc được ghi nhận như một kết quả có chủ đích.

## 4. Dùng psql ở chế độ tự động hóa

### 4.1. Các tùy chọn quan trọng

Ví dụ chạy file SQL:

```bash
psql -X -w -v ON_ERROR_STOP=1 -d appdb -f maintenance.sql
```

Ý nghĩa:

- **-X:** không đọc startup file psql của user, giúp hành vi ít phụ thuộc môi trường.
- **-w:** không hỏi password tương tác; thiếu credential thì fail.
- **-v ON_ERROR_STOP=1:** dừng script khi gặp lỗi SQL.
- **-d:** chọn database.
- **-f:** chạy file SQL.

Trong SQL file cũng có thể đặt:

```sql
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on
```

### 4.2. Vì sao cần ON_ERROR_STOP?

Mặc định psql có thể tiếp tục thực hiện các lệnh sau một lỗi trong script. Với automation, điều đó có thể tạo trạng thái dở dang: bước tạo bảng lỗi nhưng bước grant hoặc ghi version vẫn chạy.

ON_ERROR_STOP yêu cầu psql dừng khi một lệnh SQL hoặc meta-command bị lỗi. Nếu script có transaction đang mở, khi session đóng do lỗi thì transaction chưa commit sẽ rollback.

### 4.3. Exit codes của psql

Ở chế độ non-interactive, các mã thường gặp:

| Exit code | Ý nghĩa |
| ---: | --- |
| 0 | Hoàn tất bình thường |
| 1 | Lỗi fatal của chính psql |
| 2 | Kết nối server lỗi trong non-interactive mode |
| 3 | Script có lỗi khi ON_ERROR_STOP được bật |

Scheduler cần kiểm tra exit code, không chỉ kiểm tra stdout có chứa chữ “ERROR” hay không. Một số wrapper có thể biến đổi exit code; hãy kiểm tra toàn bộ chuỗi gọi lệnh.

### 4.4. Không dùng shell interpolation tùy tiện

Đặt SQL trong file được review hoặc heredoc có quoted delimiter. Ví dụ dùng cú pháp <<'SQL' ngăn shell mở rộng biến $VARIABLE trong SQL body.

Không ghép user input trực tiếp vào SQL string. Với psql variables, dùng cách quote đúng:

- **:'var'** để quote giá trị như SQL literal.
- **:"var"** để quote identifier.
- **:var** chỉ thay thế text thô và không an toàn cho dữ liệu tùy ý.

### 4.5. Single transaction option

psql có tùy chọn **--single-transaction** (hoặc **-1**) để bao các lệnh -c/-f phù hợp trong một transaction. Chỉ dùng khi toàn bộ commands có thể chạy trong transaction. Các lệnh như CREATE DATABASE, DROP DATABASE, VACUUM và CREATE INDEX CONCURRENTLY không thể chạy trong transaction block.

### 4.6. Tách file theo giai đoạn

Với deployment phức tạp, tách:

- Preflight.
- Transactional schema/data changes.
- Non-transactional operations.
- Postflight validation.

Mỗi giai đoạn có exit code, log và recovery step riêng. Không đặt tất cả lệnh vào một file rồi giả định có thể rollback toàn bộ.

## 5. Transaction và atomicity

### 5.1. Gom các thay đổi liên quan vào transaction

```sql
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

UPDATE app.orders
SET source_code = 'legacy'
WHERE source_code IS NULL;

COMMIT;
```

Nếu một câu lệnh lỗi trước COMMIT, transaction ở trạng thái aborted và các thay đổi transactional chưa commit sẽ không được giữ lại.

### 5.2. SET LOCAL

SET LOCAL chỉ có hiệu lực trong transaction hiện tại. Khi transaction commit hoặc rollback, setting trở về giá trị trước đó. Điều này hữu ích để giới hạn timeout riêng cho một migration.

### 5.3. Transaction không làm mọi thao tác trở nên rollbackable

Một số lệnh không được phép chạy trong transaction block; một số thao tác bên ngoài database như gửi file, gọi API hoặc restart service không thể được PostgreSQL rollback. Thiết kế workflow theo các bước có thể đối soát và bù trừ.

### 5.4. Không để transaction mở trong lúc chờ bên ngoài

Tránh bắt đầu transaction rồi gọi HTTP, chờ người dùng hoặc xử lý file lâu. Transaction dài giữ locks/snapshots, tăng bloat pressure và có thể làm vacuum bị cản trở.

### 5.5. Kiểm tra số rows bị tác động

Trong psql, biến ROW_COUNT có thể đọc sau một lệnh SQL:

```sql
UPDATE app.orders
SET status = 'archived'
WHERE created_at < current_date - interval '2 years';

\echo Updated rows: :ROW_COUNT
```

Trong production script, cần so số rows với expected range. Nếu vượt giới hạn hoặc bằng 0 ngoài dự kiến, dừng transaction hoặc yêu cầu review.

### 5.6. Dùng constraint và điều kiện trước

Không chỉ kiểm tra kết quả sau. Dùng preconditions như schema version, object existence, expected owner và row counts để ngăn script chạy trên sai trạng thái.

## 6. Các loại timeout cần phân biệt

Một automation thường cần nhiều timeout độc lập. Một giá trị timeout duy nhất không bảo vệ được mọi giai đoạn.

| Timeout | Điều giới hạn | Cấu hình |
| --- | --- | --- |
| Connection timeout | Thời gian thiết lập kết nối | PGCONNECT_TIMEOUT hoặc libpq connect_timeout |
| Lock timeout | Thời gian chờ lock | lock_timeout |
| Statement timeout | Thời gian một statement | statement_timeout |
| Idle transaction timeout | Thời gian session idle trong transaction | idle_in_transaction_session_timeout |
| Idle session timeout | Thời gian session idle | idle_session_timeout |
| Job timeout | Tổng thời gian process/job | Scheduler hoặc OS timeout |
| Retry budget | Tổng thời gian/số lần retry | Logic wrapper |

### 6.1. Connection timeout

Đặt thời gian kết nối có giới hạn:

```bash
export PGCONNECT_TIMEOUT=5
psql -X -w -d appdb -c 'SELECT 1;'
```

Giá trị tính bằng giây. Với nhiều host trong connection string, tổng thời gian thực tế có thể lớn hơn một lần timeout đơn lẻ do libpq thử nhiều địa chỉ.

### 6.2. Lock timeout

lock_timeout giới hạn thời gian một statement chờ lock. Ví dụ:

```sql
SET lock_timeout = '5s';
```

Nếu một migration cần lock mà không lấy được trong 5 giây, PostgreSQL hủy statement với lock-not-available behavior. Đây là cách tránh DDL chờ vô hạn và làm nghẽn traffic.

### 6.3. Statement timeout

```sql
SET statement_timeout = '2min';
```

Nếu một statement chạy quá thời gian, PostgreSQL hủy statement. Timeout tính theo thời gian thực thi phía server; nó không phải giới hạn toàn bộ job.

Không đặt statement_timeout quá thấp cho backup, index build hoặc batch job hợp lệ. Có thể dùng SET LOCAL riêng cho các bước cần budget khác nhau.

### 6.4. Idle in transaction timeout

```sql
SET idle_in_transaction_session_timeout = '1min';
```

Setting này đóng session nếu nó ở trạng thái idle trong một transaction quá lâu. Nó giúp hạn chế transaction bị bỏ quên, nhưng có thể ngắt ứng dụng nếu ứng dụng giữ transaction trong lúc chờ thao tác bên ngoài.

### 6.5. Idle session timeout

idle_session_timeout có thể đóng session idle không nằm trong transaction. Thận trọng với connection pools, proxy và middleware vì chúng có thể không mong đợi server chủ động đóng idle connection.

### 6.6. Job timeout

Một process wrapper có thể giới hạn tổng thời gian:

```bash
timeout --signal=TERM --kill-after=30s 15m \
  psql -X -w -v ON_ERROR_STOP=1 -d appdb -f maintenance.sql
```

Ví dụ dùng GNU coreutils trên Linux. Cú pháp và khả năng timeout khác trên Windows hoặc scheduler khác. Job timeout là lớp bảo vệ ngoài; vẫn cần statement_timeout để server chủ động hủy SQL.

### 6.7. Timeout không phải rollback mọi thứ

Client process bị kill không bảo đảm mọi thao tác ngoài transaction được hoàn tác. Kết nối bị đóng thường khiến transaction đang mở rollback, nhưng lệnh đã commit, external side effects và non-transactional operations vẫn tồn tại. Sau timeout, phải kiểm tra state trước khi chạy lại.

## 7. Thiết kế timeout theo từng bước

### 7.1. Preflight ngắn

Kết nối và đọc trạng thái server nên có connect timeout thấp. Query preflight nên nhẹ, không scan bảng lớn.

### 7.2. Chờ lock ngắn hơn statement budget

Ví dụ lock_timeout = 5s, statement_timeout = 2min. Nếu không lấy được lock sớm, script dừng trước khi làm người dùng chờ lâu.

### 7.3. Dành thời gian cho rollback/cleanup

Job budget nên có khoảng dự phòng để ghi log, rollback, đóng session và báo kết quả. Đừng đặt job timeout đúng bằng statement timeout lớn nhất nếu còn nhiều bước phía sau.

### 7.4. Timeout phải phù hợp workload

Một report truy vấn dữ liệu lớn có thể cần vài phút; migration thêm constraint trên bảng lớn có thể cần kế hoạch riêng; health check chỉ nên mất vài giây. Ghi rõ lý do của từng timeout.

### 7.5. Tránh timeout chồng lấn khó hiểu

Nếu statement_timeout là 2 phút nhưng job timeout là 30 giây, process có thể bị kill trước khi PostgreSQL trả lỗi statement timeout. Đặt thứ tự hợp lý giữa statement, retry budget và job budget.

## 8. Idempotency và chạy lại an toàn

### 8.1. Idempotent là gì?

Một thao tác idempotent có thể được thực hiện lặp lại mà trạng thái cuối vẫn tương đương với thực hiện một lần, trong phạm vi điều kiện xác định.

Ví dụ:

```sql
CREATE TABLE IF NOT EXISTS app.job_runs (
    job_name text PRIMARY KEY,
    last_success_at timestamptz
);
```

Tuy nhiên, IF NOT EXISTS chỉ tránh lỗi khi tên object đã tồn tại; nó không chứng minh object hiện có có đúng schema, owner hoặc constraints. Vẫn cần kiểm tra catalog.

### 8.2. UPSERT với khóa nghiệp vụ

```sql
INSERT INTO app.job_runs (job_name, last_success_at)
VALUES ('daily_aggregate', clock_timestamp())
ON CONFLICT (job_name)
DO UPDATE
SET last_success_at = EXCLUDED.last_success_at;
```

Dùng unique key đại diện operation/business identity để tránh tạo duplicate khi retry.

### 8.3. Migration ledger

Lưu migration version, checksum và applied timestamp. Trước khi chạy migration, kiểm tra:

- Version đã tồn tại chưa?
- Checksum có khớp file đã review không?
- Có migration trước đang ở trạng thái incomplete không?
- Có phiên bản mới hơn đã được apply không?

Không đánh dấu migration hoàn tất trước khi transaction thay đổi schema commit thành công.

### 8.4. Không nhầm IF EXISTS với an toàn

DROP TABLE IF EXISTS có thể thành công dù object đã bị xóa nhầm từ trước. Idempotency cần kiểm tra target, owner, schema và expected state; cú pháp IF EXISTS chỉ xử lý một loại lỗi tên object.

### 8.5. DML có điều kiện

Dùng unique constraint, upsert, operation ID và predicates để đảm bảo retry không tạo duplicate. Tránh logic “đọc xem có chưa rồi insert” nếu không có constraint bảo vệ concurrency.

### 8.6. External side effects

Nếu script vừa cập nhật PostgreSQL vừa gửi email/API hoặc ghi file, database transaction không thể rollback external action. Dùng outbox pattern, idempotency key ở hệ thống nhận hoặc bước reconciliation.

## 9. Retry có giới hạn và backoff

### 9.1. Retry không sửa lỗi logic

Không retry syntax error, permission denied, missing relation hoặc invalid input. Những lỗi này cần sửa script/configuration.

### 9.2. SQLSTATE cần nhận diện

Một số mã đáng chú ý:

| SQLSTATE | Ý nghĩa | Hành động |
| --- | --- | --- |
| 40001 | Serialization failure | Retry toàn transaction nếu idempotent |
| 40P01 | Deadlock detected | Retry toàn transaction có giới hạn |
| 55P03 | Lock not available | Có thể retry sau backoff nếu policy cho phép |
| 57014 | Query canceled | Xác định nguyên nhân; không retry tự động vô điều kiện |
| 42501 | Insufficient privilege | Dừng và sửa quyền |
| 42601 | Syntax error | Dừng và sửa script |
| 23505 | Unique violation | Xử lý theo business logic |
| 08xxx | Connection exception class | Kiểm tra kết quả transaction trước retry |

### 9.3. Exponential backoff

Ví dụ delay tăng dần: 1s, 2s, 4s, 8s, có jitter và giới hạn số lần. Jitter giúp nhiều jobs không cùng retry vào một thời điểm.

### 9.4. Retry toàn transaction

Khi nhận serialization failure hoặc deadlock, transaction hiện tại không còn hiệu lực. Bắt đầu lại toàn transaction từ đầu, gồm cả các lần đọc mà quyết định ghi phụ thuộc vào chúng.

### 9.5. Đặt retry budget

Ví dụ tối đa 4 attempts hoặc tổng thời gian 2 phút. Khi hết budget, log lỗi cuối cùng và trả exit code khác 0.

### 9.6. Không retry kết nối mù quáng sau COMMIT

Nếu client mất kết nối trong lúc COMMIT, transaction có thể đã thành công. Dùng operation ID và truy vấn trạng thái từ một kết nối mới để xác minh. Nếu không thể xác định, báo trạng thái UNKNOWN để operator xử lý.

## 10. Ngăn job chạy đồng thời

### 10.1. Vì sao cần concurrency control?

Cron, systemd timer hoặc CI pipeline có thể khởi chạy job mới khi lần trước chưa hoàn tất. Hai script cùng archive dữ liệu, rotate partition hoặc thay đổi schema có thể xung đột.

### 10.2. Advisory transaction lock

Với một transaction đơn:

```sql
BEGIN;

DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'maintenance job is already running';
    END IF;
END
$$;

-- Thực hiện các thao tác thuộc cùng transaction.
ANALYZE app.orders;

COMMIT;
```

Hai integer keys tạo namespace cho job. Nếu lock đã được giữ, script lỗi và transaction rollback. Transaction-level advisory lock tự giải phóng khi commit/rollback.

### 10.3. Advisory session lock

Với job gồm nhiều transactions, có thể dùng pg_try_advisory_lock và pg_advisory_unlock để giữ lock theo session. Nếu connection đóng, session lock được giải phóng.

Phải bảo đảm mọi nhánh kết thúc đều unlock hoặc đóng session; không dùng cùng key cho các job không liên quan.

### 10.4. Advisory lock là cơ chế hợp tác

PostgreSQL không tự bắt mọi DDL/DML tuân theo advisory lock. Chỉ các scripts có cùng convention mới bị serialize. Lock không thay thế row/table locks và không phải cơ chế authorization.

### 10.5. OS-level lock

Trên Linux có thể dùng flock để ngăn hai process trên cùng host chạy đồng thời. Nó không bảo vệ khi job chạy trên nhiều hosts hoặc container khác nhau nếu lock file không nằm trên filesystem có semantics phù hợp.

### 10.6. Dùng hai lớp khi cần

Một scheduler lock có thể chặn duplicate trên cùng host; advisory lock trong PostgreSQL bảo vệ giữa các hosts cùng database. Chọn một cơ chế chính và ghi rõ phạm vi.

## 11. Logging: lưu điều gì?

### 11.1. Log phải trả lời được ai, cái gì và khi nào

Mỗi run nên có:

- UTC timestamp.
- Run ID và change/job ID.
- Environment, host/cluster và database.
- Script name và version/checksum.
- Application name hoặc service identity.
- Attempt number.
- Event start/step/success/failure.
- Duration và rows affected.
- SQLSTATE và exit code khi lỗi.
- Kết quả postcondition.
- Người hoặc scheduler khởi chạy.

### 11.2. Structured logs

Dạng key-value hoặc JSON giúp tìm kiếm:

```text
timestamp=2026-11-14T08:00:00Z level=INFO run_id=run-104 job=analyze_orders database=appdb event=start
timestamp=2026-11-14T08:00:03Z level=INFO run_id=run-104 job=analyze_orders rows=0 event=complete
timestamp=2026-11-14T08:00:03Z level=INFO run_id=run-104 job=analyze_orders exit_code=0 result=success
```

Không cần log mọi giá trị SQL; log metadata đủ để trace run.

### 11.3. Không ghi secrets

Tránh:
- Password/connection string có password.
- Access tokens, private keys.
- PII hoặc full query parameters nhạy cảm.
- Nội dung file credential.
- Environment dumps toàn bộ.

Không bật shell xtrace trong script có secrets hoặc connection data.

### 11.4. Ghi SQLSTATE thay vì chỉ message

SQLSTATE ổn định hơn text message khi phân loại lỗi. Lưu message đã redact nếu hữu ích, nhưng không để message chứa dữ liệu nhạy cảm lọt vào log.

### 11.5. Log ở client và server

Client log cho biết job, attempt, duration và exit code. PostgreSQL server log cho biết backend, query duration, lock wait, error context và session identity. Kết hợp hai phía bằng timestamp, database, user và application_name.

### 11.6. Quyền và retention

Log file có thể chứa schema names và query samples. Dùng file permissions chặt, rotation, retention và access control. Không lưu log vô hạn trên volume đầy.

## 12. Shell wrapper có error handling

Ví dụ Bash dưới đây minh họa một wrapper cho Linux. Thay service/database/change ID theo môi trường lab và cấu hình .pg_service.conf/credential store trước khi chạy.

```bash
#!/usr/bin/env bash
set -Ee -o pipefail
umask 077

CHANGE_ID="CHG-2026-0001"
PGSERVICE="app_admin"
PGDATABASE="appdb"
LOG_DIR="./logs"

if [ -z "$PGSERVICE" ] || [ -z "$PGDATABASE" ] || [ -z "$CHANGE_ID" ]; then
    printf '%s\n' "Missing required configuration" >&2
    exit 64
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pg-admin-$(date -u +%Y%m%dT%H%M%SZ).log"
printf 'Log file: %s\n' "$LOG_FILE" >&2
exec >>"$LOG_FILE" 2>&1

log() {
    printf '%s level=%s change_id=%s %s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$CHANGE_ID" "$2"
}

on_error() {
    rc=$?
    log ERROR "line=$1 exit_code=$rc"
    exit "$rc"
}

on_exit() {
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log INFO "result=success exit_code=0"
    else
        log ERROR "result=failure exit_code=$rc"
    fi
}

trap 'on_error "$LINENO"' ERR
trap on_exit EXIT

export PGCONNECT_TIMEOUT=5
export PGAPPNAME="pg-admin-$CHANGE_ID"

log INFO "event=start database=$PGDATABASE service=$PGSERVICE"

psql -X -w -v ON_ERROR_STOP=1 \
    -d "service=$PGSERVICE dbname=$PGDATABASE" <<'SQL'
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on

SET lock_timeout = '5s';
SET statement_timeout = '2min';
SET idle_in_transaction_session_timeout = '1min';

BEGIN;

DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'maintenance job is already running';
    END IF;
END
$$;

ANALYZE app.orders;

COMMIT;
SQL

log INFO "event=psql_completed"
```

### 12.1. Vì sao dùng set -Ee -o pipefail?

- **-e:** thoát khi một command lỗi trong các ngữ cảnh shell mà errexit áp dụng.
- **-E:** kế thừa ERR trap trong function/subshell ở các trường hợp Bash hỗ trợ.
- **pipefail:** pipeline trả lỗi nếu một thành phần thất bại, không chỉ command cuối.

set -e có các ngoại lệ trong if, while, &&, ||, pipelines và functions. Không xem nó là thay thế cho kiểm tra exit code tường minh.

### 12.2. Error trap và exit trap

ERR trap ghi line number và exit code khi command lỗi. EXIT trap ghi kết quả cuối cùng. Không log raw command hoặc toàn bộ environment vì có thể chứa secret.

### 12.3. Log file permissions

umask 077 giới hạn quyền file mới cho user chạy script. Directory log hiện có vẫn cần được quản lý permission/ownership riêng.

### 12.4. Service file và password

Ví dụ dùng libpq service name. Cấu hình service trong .pg_service.conf hoặc vị trí được quản lý; password lấy từ secret manager, .pgpass với quyền file phù hợp hoặc cơ chế authentication được tổ chức hỗ trợ. Tùy chọn -w bảo đảm psql không dừng chờ nhập password tương tác.

### 12.5. Không bật xtrace

Không thêm set -x vào wrapper nếu lệnh có thể chứa connection data hoặc credentials. Nếu cần debug, log các giá trị đã whitelist và redact.

### 12.6. Wrapper cần kiểm tra log rotation

Ví dụ tạo một file theo timestamp. Với job chạy thường xuyên, dùng logrotate hoặc centralized logging; kiểm tra disk capacity và retention.

## 13. Script SQL có guardrails

Một SQL file nên thể hiện rõ điều kiện và phạm vi tác động.

```sql
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on

-- Chỉ áp dụng timeout cho session này.
SET lock_timeout = '5s';
SET statement_timeout = '2min';

BEGIN;

-- Ngăn một run cùng job chạy đồng thời.
DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'another run owns this job';
    END IF;
END
$$;

-- Kiểm tra target trước khi thay đổi.
DO $$
BEGIN
    IF current_database() <> 'appdb' THEN
        RAISE EXCEPTION 'unexpected database target';
    END IF;
END
$$;

ANALYZE app.orders;

COMMIT;
```

### 13.1. Kiểm tra database target

Một script nên tự xác minh current_database() và có thể kiểm tra server identity, schema version hoặc application environment. Không chỉ tin rằng scheduler đã truyền đúng tham số.

### 13.2. Kiểm tra role

Dùng current_user và session_user để xác minh identity. Nếu script yêu cầu owner role, thực hiện SET ROLE rõ ràng và xác minh trước DDL.

### 13.3. Kiểm tra object owner

Có thể kiểm tra pg_class.relowner, pg_namespace.nspowner hoặc pg_get_userbyid() để chắc chắn target có owner mong muốn.

### 13.4. Kiểm tra affected rows

Với DML quan trọng, ghi số rows và dừng nếu số lượng ngoài expected range. Nếu dùng psql ROW_COUNT, phải đọc ngay sau statement cần đo.

### 13.5. Không dùng assertion chỉ để trang trí

Một precondition cần thực sự dừng script khi không thỏa mãn. RAISE EXCEPTION trong DO block tạo lỗi SQL; với ON_ERROR_STOP, psql trả exit code lỗi.

## 14. Chạy batch lớn có checkpoint

### 14.1. Vì sao không cập nhật hàng triệu rows trong một transaction duy nhất?

Một transaction dài có thể:
- Giữ locks lâu.
- Tăng WAL và replication lag.
- Giữ snapshot cũ, cản vacuum.
- Tạo lượng rollback lớn khi lỗi.
- Làm recovery sau crash lâu hơn.

### 14.2. Chia batch có giới hạn

Dùng khóa ổn định và điều kiện để xử lý từng phần. Ví dụ minh họa một batch theo primary key:

```sql
WITH batch AS (
    SELECT order_id
    FROM app.orders
    WHERE archived_at IS NULL
      AND created_at < current_date - interval '2 years'
    ORDER BY order_id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.orders AS o
SET archived_at = clock_timestamp()
FROM batch
WHERE o.order_id = batch.order_id;
```

Ứng dụng lặp statement cho tới khi không còn rows phù hợp. SKIP LOCKED hữu ích cho worker queue/batch concurrency nhưng có thể bỏ qua rows đang bị lock; cần lượt xử lý sau để bảo đảm hoàn tất.

### 14.3. Ghi checkpoint

Lưu job ID, last processed key, batch number, rows affected và timestamp trong bảng control. Checkpoint phải commit cùng batch hoặc có semantics phục hồi rõ ràng.

### 14.4. Đảm bảo retry không bỏ sót hoặc nhân đôi

Điều kiện chọn rows cần loại trừ rows đã xử lý. Dùng unique key, status transition và transaction để cập nhật dữ liệu cùng checkpoint atomically.

### 14.5. Giới hạn WAL và replication impact

Theo dõi WAL bytes, replica replay lag, disk headroom và archive throughput. Giảm batch size hoặc sleep giữa batches nếu workload production cần được ưu tiên.

### 14.6. Batch job có thể resume

Khi job bị timeout, đọc checkpoint và xác minh trạng thái rows. Không reset checkpoint hoặc chạy lại toàn bộ chỉ vì process trả lỗi.

## 15. Dry-run và review trước thay đổi

### 15.1. Dry-run có nghĩa gì?

Dry-run hiển thị target, rows dự kiến, objects bị ảnh hưởng và kế hoạch thao tác mà không commit thay đổi. Không phải mọi SQL operation đều có thể mô phỏng hoàn toàn.

### 15.2. Dùng transaction rollback trong lab

Với các thay đổi transactional, có thể chạy thử trong transaction rồi ROLLBACK để xem SQL có hợp lệ và ước lượng affected rows. Điều này không mô phỏng đầy đủ lock duration, commit behavior hoặc external side effects.

### 15.3. SELECT preview trước UPDATE/DELETE

```sql
SELECT count(*) AS candidate_rows
FROM app.orders
WHERE created_at < current_date - interval '2 years'
  AND archived_at IS NULL;
```

Sau đó kiểm tra sample rows và expected range trước khi chạy DML.

### 15.4. Có limit/guardrail cho destructive operation

Ví dụ yêu cầu affected rows nhỏ hơn một ngưỡng đã duyệt. Nếu vượt ngưỡng, raise exception và dừng để operator review.

### 15.5. Review target

Log database, host/service name, schema và change ID trước khi bắt đầu. Có thể yêu cầu allowlist target cho production automation.

### 15.6. Dry-run không thay backup

Trước thao tác destructive, xác minh backup/PITR và recovery procedure. Một transaction rollback không bảo vệ được thao tác non-transactional hoặc sai logic đã commit.

## 16. Thao tác không thể chạy trong transaction block

Một số công việc quản trị cần quy trình riêng:

| Lệnh/thao tác | Transaction block |
| --- | --- |
| CREATE DATABASE | Không |
| DROP DATABASE | Không |
| VACUUM | Không |
| CREATE INDEX CONCURRENTLY | Không |
| REINDEX CONCURRENTLY | Không |
| Một số thao tác quản trị khác | Kiểm tra tài liệu/version |

### 16.1. Tách non-transactional step

Chạy preflight và backup checks trước; thực hiện lệnh riêng; sau đó postflight kiểm tra trạng thái. Nếu lỗi giữa chừng, dùng recovery procedure của chính command.

### 16.2. CREATE INDEX CONCURRENTLY

Lệnh này tránh khóa ghi dài theo cách thông thường của CREATE INDEX nhưng có thể mất nhiều giai đoạn và để lại invalid index nếu thất bại. Kiểm tra pg_index.indisvalid và xử lý index state trước khi retry.

### 16.3. VACUUM

VACUUM cần chạy ngoài transaction block. Đừng bao nó trong BEGIN/COMMIT hoặc dùng --single-transaction cho file có VACUUM.

### 16.4. CREATE/DROP DATABASE

Các lệnh này thay đổi cluster-level state. Chạy trong một session autocommit riêng, kiểm tra database name, active connections và dependencies. Không đặt chúng cùng transaction migration thông thường.

### 16.5. External operations

Restart PostgreSQL, thay file config, đổi firewall hoặc update DNS không thuộc database transaction. Workflow cần step state và compensating actions rõ ràng.

## 17. Logging phía PostgreSQL

### 17.1. application_name

Đặt application_name theo job/change ID để nhận diện session:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    query_start,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE application_name LIKE 'pg-admin-%';
```

Có thể đặt qua libpq PGAPPNAME hoặc connection parameter application_name.

### 17.2. log_line_prefix

Một log prefix có thể chứa timestamp, PID, user, database, application name và client address. Ví dụ cấu hình phụ thuộc PostgreSQL version:

```conf
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%h '
```

Giữ format thống nhất để correlate client và server logs.

### 17.3. Slow statement logging

log_min_duration_statement có thể ghi các statements vượt ngưỡng. Chọn ngưỡng để cân bằng khả năng điều tra với log volume. Parameter values có thể chứa thông tin nhạy cảm tùy query/logging configuration.

### 17.4. Connection logs

log_connections và log_disconnections có thể giúp theo dõi lifecycle sessions. Trên hệ thống có connection churn lớn, log volume có thể tăng đáng kể.

### 17.5. pgaudit và audit trail

pgaudit có thể ghi các hoạt động cần audit theo policy. Thiết lập audit phải cân nhắc volume, retention, overhead và quyền truy cập logs. Không bật ghi mọi statement mà không có kế hoạch lưu trữ.

### 17.6. Server logs không thay application logs

PostgreSQL log cho biết server thấy gì; scheduler/application log cho biết job được khởi chạy ra sao và đã nhận response nào. Cần cả hai để xác định lỗi.

## 18. Theo dõi job trong lúc chạy

### 18.1. Active sessions

Tìm job qua application_name:

```sql
SELECT
    pid,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE application_name = 'pg-admin-CHG-2026-0001';
```

### 18.2. Lock waits

Dùng pg_blocking_pids(pid) để xác định backend đang block job. Trước khi cancel/terminate, xem transaction owner và business impact.

### 18.3. Cancel và terminate khác nhau

- pg_cancel_backend(pid) yêu cầu hủy query hiện tại; session có thể tiếp tục sau đó.
- pg_terminate_backend(pid) kết thúc session, khiến transaction đang mở rollback khi connection đóng.

Đây là thao tác quản trị có tác động; kiểm tra PID, user, database và application_name trước.

### 18.4. Progress views

Một số operation có progress views như pg_stat_progress_create_index, pg_stat_progress_vacuum, pg_stat_progress_analyze và các view khác tùy version. Dùng chúng để biết operation đang ở phase nào thay vì chỉ chờ timeout.

### 18.5. Metrics ngoài database

Theo dõi process CPU/memory, disk I/O, network, scheduler runtime, queue depth và replica lag. Một query đang chạy lâu có thể đang chờ storage hoặc lock chứ không tiêu thụ CPU.

## 19. Retry wrapper và nguyên tắc thực hiện

Một retry wrapper cần:

1. Chỉ retry các lỗi đã được phân loại.
2. Retry toàn bộ transaction khi transaction đã abort.
3. Có maximum attempts.
4. Dùng exponential backoff và jitter.
5. Có tổng retry budget.
6. Ghi attempt, SQLSTATE và delay.
7. Không retry nếu commit outcome chưa rõ mà không có reconciliation.
8. Trả lỗi cuối cùng về scheduler.

### 19.1. Pseudocode

```text
for attempt in 1..MAX_ATTEMPTS:
    start a fresh database transaction
    execute the complete idempotent unit of work

    if committed:
        record success
        stop

    if error is retryable and budget remains:
        rollback/close the failed transaction
        wait with exponential backoff plus jitter
        continue

    record failure
    return non-zero
```

### 19.2. Không retry từng câu lệnh độc lập nếu logic phụ thuộc

Nếu transaction gồm đọc số dư, kiểm tra điều kiện rồi cập nhật, retry chỉ UPDATE cuối có thể phá invariant. Retry toàn transaction để đọc lại state mới.

### 19.3. Backoff có jitter

Một công thức đơn giản:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
actual_delay = random(0, delay)
```

Đặt max attempts và max elapsed time để job không kéo dài vô hạn.

### 19.4. Retry không thay xử lý sự cố

Nếu mọi attempt đều timeout do lock blocker tồn tại, retry chỉ lặp lại cùng failure. Log blocker, điều tra transaction lâu và dừng job khi budget hết.

## 20. Scheduler: cron, systemd và CI/CD

### 20.1. Cron

Cron phù hợp cho job đơn giản theo lịch. Cần:
- Dùng absolute paths.
- Khai báo environment cần thiết.
- Đặt working directory rõ.
- Ghi stdout/stderr vào log.
- Kiểm tra exit code/alert.
- Ngăn overlap bằng lock.
- Không phụ thuộc interactive shell profile.

### 20.2. systemd timer

Systemd service/timer có thể quản lý:
- Timeout tổng thể.
- Restart policy có giới hạn.
- User/group chạy job.
- Environment file có permission phù hợp.
- Standard output/error vào journal.
- Dependencies và ordering.

Không dùng restart policy để lặp vô hạn một job destructive.

### 20.3. CI/CD

Migration pipeline nên có:
- Artifact/version cố định.
- Target environment được xác nhận.
- Secret injection an toàn.
- Approval gate theo policy.
- Preflight và backup checks.
- Fail-fast.
- Postflight verification.
- Artifact logs và exit status.
- Không in secrets trong command trace.

### 20.4. Scheduler không phải lock

Một cron schedule không bảo đảm job trước đã kết thúc. Dùng scheduler concurrency setting, OS lock hoặc PostgreSQL advisory lock theo phạm vi.

### 20.5. Múi giờ và daylight saving

Lịch chạy nên được xác định timezone rõ ràng. Nếu job chạy theo UTC, ghi UTC trong logs; nếu chạy theo local time, xem daylight saving và thay đổi lịch ở môi trường triển khai.

## 21. Security của automation

### 21.1. Least privilege

Mỗi job dùng role riêng chỉ có quyền cần thiết. Job đọc metrics không cần SUPERUSER; job chạy ANALYZE cần quyền phù hợp trên objects; migration role chỉ có DDL quyền cần thiết trong schema được giao.

### 21.2. Credential handling

Ưu tiên secret manager, libpq service file và .pgpass được bảo vệ. Tránh:
- PGPASSWORD tồn tại lâu trong environment nếu có lựa chọn tốt hơn.
- Password trong command-line arguments.
- Password trong URL được log.
- Secret trong source control.
- Debug trace in toàn bộ command.

### 21.3. Identity và attribution

Đặt user/application_name riêng cho job. Không dùng chung superuser account cho tất cả automation.

### 21.4. Target allowlist

Production script nên xác minh host/database/cluster identity thuộc allowlist. Một biến môi trường sai có thể khiến job chạy trên production thay vì staging hoặc ngược lại.

### 21.5. Destructive command protection

Với DROP, TRUNCATE, DELETE lớn hoặc role revocation, cần preflight, expected row count, target validation và approval theo change process. Không cho phép script tự suy đoán target từ tên database mơ hồ.

## 22. Postconditions và xác minh thành công

### 22.1. Exit code 0 chưa đủ

Một process có thể exit 0 nhưng thao tác không tạo ra trạng thái mong muốn vì logic script sai hoặc không có rows phù hợp.

### 22.2. Postcondition

Sau mỗi operation, xác minh trạng thái cần đạt. Ví dụ:
- Schema version đã cập nhật.
- Index tồn tại và indisvalid = true.
- Role có owner/privileges mong muốn.
- Bảng có constraint cần thiết.
- Replication state phù hợp.
- Job checkpoint đã tiến lên.
- Số rows đã xử lý nằm trong expected range.

### 22.3. Không đánh dấu success trước commit

Ghi job success vào ledger trong cùng transaction với công việc nếu có thể. Nếu ledger nằm ngoài transaction, ghi trạng thái STARTED/RUNNING trước và SUCCEEDED sau khi commit cùng postcondition.

### 22.4. Exactly-once thường cần thiết kế thêm

Scheduler có thể chạy lại sau crash hoặc không nhận được response dù transaction đã commit. Exactly-once behavior không tự đến từ một job scheduler; dùng operation key, unique constraints, idempotency và reconciliation.

### 22.5. Lưu outcome rõ ràng

Có thể phân biệt:
- SUCCEEDED.
- FAILED.
- RETRYABLE_FAILURE.
- TIMED_OUT.
- UNKNOWN_OUTCOME.
- SKIPPED_ALREADY_APPLIED.

Không ghi SUCCEEDED khi trạng thái commit chưa xác định.

## 23. Runbook xử lý timeout

1. Xác định timeout ở lớp nào: connect, lock, statement hay job.
2. Ghi run ID, database, application_name và timestamp.
3. Kiểm tra pg_stat_activity để xác định backend còn chạy không.
4. Xem wait_event và pg_blocking_pids() nếu query đang chờ.
5. Kiểm tra PostgreSQL logs để tìm SQLSTATE và server cancellation.
6. Xác định transaction đã commit, rollback hay outcome chưa rõ.
7. Nếu client bị kill, kiểm tra backend đã đóng và transaction đã rollback chưa.
8. Không retry destructive operation khi chưa xác minh state.
9. Điều chỉnh timeout/batch size chỉ sau khi hiểu nguyên nhân.
10. Lưu evidence và cập nhật runbook.

## 24. Runbook xử lý job thất bại

### 24.1. Dừng retry tự động khi lỗi không retryable

Permission, syntax, missing object và data constraint cần điều tra. Không tăng số lần retry để che lỗi logic.

### 24.2. Thu thập evidence

Lưu:
- Script version/checksum.
- Run/change ID.
- Exit code.
- SQLSTATE.
- Client/server logs.
- Target identity.
- Last successful step.
- Transaction/job ledger state.
- Rows affected và checkpoint.

### 24.3. Kiểm tra trạng thái một phần

Với workflow có non-transactional steps, xác định bước nào đã hoàn tất. Đừng chạy lại toàn bộ script nếu bước trước đã tạo object hoặc index thành công một phần.

### 24.4. Chọn resume hay rollback

Nếu thao tác idempotent và checkpoint hợp lệ, resume từ điểm an toàn. Nếu trạng thái không rõ, dừng để đối soát. Nếu có compensating action, thực hiện theo runbook đã review.

### 24.5. Đóng incident/change

Chỉ đánh dấu hoàn tất khi postconditions đạt, logs được lưu và partial state đã được xử lý.

## 25. Ví dụ: migration có preflight và postflight

### 25.1. Preflight

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    current_setting('server_version_num') AS server_version_num,
    pg_postmaster_start_time() AS server_started_at;
```

Kiểm tra database và identity đúng với deployment target.

### 25.2. Migration

```sql
\set ON_ERROR_STOP on

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
BEGIN
    IF current_database() <> 'appdb' THEN
        RAISE EXCEPTION 'wrong database';
    END IF;
END
$$;

ALTER TABLE app.orders
    ADD COLUMN IF NOT EXISTS source_code text;

COMMIT;
```

IF NOT EXISTS tránh lỗi nếu column đã tồn tại, nhưng vẫn cần kiểm tra datatype, nullability, default và owner của column/table để xác nhận schema đúng.

### 25.3. Postflight

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders'
  AND column_name = 'source_code';
```

Nếu query không trả row hoặc datatype không đúng, job không được đánh dấu thành công.

## 26. Ví dụ: job ANALYZE có timeout và lock

```sql
\set ON_ERROR_STOP on
\timing on

SET lock_timeout = '5s';
SET statement_timeout = '10min';

ANALYZE VERBOSE app.orders;
```

ANALYZE có thể tạo workload I/O/CPU và cần quyền phù hợp. Nó không nên chạy cùng --single-transaction nếu file chứa các lệnh maintenance không được phép trong transaction. Ghi runtime, output và kết quả vào log.

## 27. Ví dụ: kiểm tra index sau CREATE INDEX CONCURRENTLY

CREATE INDEX CONCURRENTLY không chạy trong transaction block. Sau khi lệnh kết thúc, kiểm tra catalog:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisready,
    x.indisvalid
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
  ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
  ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
  AND t.relname = 'orders';
```

Nếu index invalid sau failure, xác định nguyên nhân và cleanup/retry theo runbook. Không chỉ kiểm tra object name tồn tại.

## 28. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không bật ON_ERROR_STOP | psql tiếp tục sau SQL error | Bật fail-fast |
| Chỉ kiểm tra stdout | Bỏ sót process failure | Kiểm tra exit code |
| Không đặt connect timeout | Job chờ kết nối lâu | PGCONNECT_TIMEOUT |
| Không đặt lock_timeout | DDL chờ lock kéo dài | Lock budget rõ |
| Chỉ đặt client job timeout | Server query có thể chưa bị hủy theo ý muốn | Kết hợp statement_timeout |
| Retry mọi lỗi | Tăng tải và lặp lỗi vĩnh viễn | Phân loại SQLSTATE |
| Retry một statement cuối | Phá logic transaction | Retry toàn transaction |
| Retry sau mất kết nối COMMIT | Duplicate operation | Reconcile bằng operation ID |
| Không có advisory lock | Job chạy chồng lấn | Concurrency control |
| Không kiểm tra target | Chạy nhầm production/database | Preflight và allowlist |
| Log password | Credential leakage | Secret store, redaction |
| Bật set -x | In command/secret | Không xtrace trong production |
| Transaction quá dài | Lock/bloat/WAL pressure | Batch/checkpoint |
| Dùng --single-transaction với VACUUM | Lệnh lỗi | Tách non-transactional step |
| Dùng IF NOT EXISTS làm validation | Object sai schema vẫn được chấp nhận | Postcondition/catalog checks |
| Đánh dấu success trước COMMIT | Ledger sai | Ghi sau commit |
| Chỉ log message | Khó phân loại lỗi | SQLSTATE + exit code |
| Không rotate logs | Disk đầy | Retention/logrotate |
| Không có postcondition | Exit 0 nhưng state sai | Verify kết quả |
| Không ghi run ID | Khó correlate | Correlation ID |
| Không có resume plan | Chạy lại gây duplicate | Checkpoint/idempotency |

## 29. Checklist thiết kế một automation mới

Trước khi triển khai, xác nhận:

1. Target cluster/database/schema được chỉ định rõ.
2. Login role có least privilege.
3. Credentials lấy từ secret manager hoặc secure libpq configuration.
4. Script version/checksum được cố định.
5. Preflight kiểm tra version, role và expected state.
6. Có transaction boundary hợp lý.
7. Non-transactional operations được tách riêng.
8. ON_ERROR_STOP được bật cho psql scripts.
9. Connection, lock, statement và job timeouts được đặt.
10. Job có idempotency hoặc operation ledger.
11. Có concurrency lock nếu job không được chạy đồng thời.
12. Retry chỉ áp dụng lỗi transient được xác định.
13. Retry budget và backoff có giới hạn.
14. Logging có UTC timestamp, run ID, SQLSTATE và exit code.
15. Logs không chứa credentials/PII nhạy cảm.
16. Affected rows nằm trong expected range.
17. Postconditions được kiểm tra.
18. Scheduler nhận đúng exit code.
19. Có resume/rollback/compensation plan.
20. Log retention và alert owner được xác định.

## 30. Bài tập thực hành có đáp án

Các bài tập giả định bạn có PostgreSQL lab hoặc staging. Không dùng script ví dụ để thay đổi production khi chưa xác định target, quyền và recovery procedure.

### Bài 1. Vì sao script quản trị cần fail-fast?

**Đáp án:** Để lỗi ở bước trước ngăn các bước sau chạy trên trạng thái dở dang.

### Bài 2. psql option nào ngăn đọc startup file?

**Đáp án:** -X.

### Bài 3. psql option nào bật dừng khi SQL lỗi?

**Đáp án:** -v ON_ERROR_STOP=1, hoặc \set ON_ERROR_STOP on trong script.

### Bài 4. psql option nào ngăn hỏi password tương tác?

**Đáp án:** -w.

### Bài 5. Exit code 0 có nghĩa gì?

**Đáp án:** psql hoàn tất bình thường; vẫn cần postcondition để chứng minh trạng thái mong muốn.

### Bài 6. Exit code 3 của psql thường chỉ điều gì?

**Đáp án:** Script gặp lỗi khi ON_ERROR_STOP được bật.

### Bài 7. PGCONNECT_TIMEOUT dùng để làm gì?

**Đáp án:** Giới hạn thời gian thiết lập kết nối tới server.

### Bài 8. lock_timeout khác statement_timeout thế nào?

**Đáp án:** lock_timeout giới hạn thời gian chờ lock; statement_timeout giới hạn thời gian một statement chạy.

### Bài 9. idle_in_transaction_session_timeout bảo vệ gì?

**Đáp án:** Đóng session bị bỏ idle trong transaction quá lâu.

### Bài 10. Job timeout khác statement timeout thế nào?

**Đáp án:** Job timeout giới hạn toàn process; statement timeout giới hạn từng statement ở server.

### Bài 11. Client bị kill có chắc transaction rollback?

**Đáp án:** Transaction chưa commit thường rollback khi connection đóng, nhưng commit outcome và external/non-transactional side effects phải được xác minh.

### Bài 12. Vì sao cần ON_ERROR_STOP khi dùng psql -f?

**Đáp án:** Để psql không tiếp tục thực hiện các lệnh sau lỗi SQL.

### Bài 13. --single-transaction có dùng với VACUUM được không?

**Đáp án:** Không. VACUUM không chạy trong transaction block.

### Bài 14. CREATE DATABASE có chạy trong BEGIN/COMMIT không?

**Đáp án:** Không.

### Bài 15. CREATE INDEX CONCURRENTLY có chạy trong transaction block không?

**Đáp án:** Không.

### Bài 16. SET LOCAL có hiệu lực bao lâu?

**Đáp án:** Trong transaction hiện tại; kết thúc transaction thì giá trị trở về trước đó.

### Bài 17. Vì sao không để transaction mở khi gọi API bên ngoài?

**Đáp án:** Có thể giữ locks/snapshots lâu và tăng bloat/lock contention.

### Bài 18. Idempotent operation là gì?

**Đáp án:** Thực hiện lặp lại vẫn đưa hệ thống về trạng thái tương đương trong điều kiện được xác định.

### Bài 19. IF NOT EXISTS có chứng minh object đúng schema không?

**Đáp án:** Không. Nó chỉ tránh lỗi khi object name đã tồn tại.

### Bài 20. Vì sao cần migration ledger checksum?

**Đáp án:** Để phát hiện migration file bị thay đổi sau khi đã áp dụng và tránh chạy sai version.

### Bài 21. SQLSTATE 40001 là gì?

**Đáp án:** Serialization failure; thường cần retry toàn transaction.

### Bài 22. SQLSTATE 40P01 là gì?

**Đáp án:** Deadlock detected; có thể retry toàn transaction có giới hạn.

### Bài 23. SQLSTATE 42501 là gì?

**Đáp án:** Insufficient privilege; dừng và xử lý quyền.

### Bài 24. SQLSTATE 57014 thường liên quan điều gì?

**Đáp án:** Query canceled, có thể do statement timeout hoặc cancel từ client/operator.

### Bài 25. Vì sao không retry mọi lỗi connection?

**Đáp án:** Kết nối có thể mất đúng lúc COMMIT và outcome không rõ; retry có thể tạo duplicate.

### Bài 26. Exponential backoff có tác dụng gì?

**Đáp án:** Tăng khoảng chờ giữa các lần retry để giảm áp lực lên hệ thống đang lỗi.

### Bài 27. Jitter là gì?

**Đáp án:** Thành phần ngẫu nhiên trong thời gian backoff để tránh nhiều clients retry đồng thời.

### Bài 28. Advisory transaction lock được giải phóng khi nào?

**Đáp án:** Khi transaction commit hoặc rollback.

### Bài 29. Advisory session lock được giải phóng khi nào?

**Đáp án:** Khi unlock hoặc session kết thúc.

### Bài 30. Advisory lock có tự chặn mọi SQL không?

**Đáp án:** Không. Đây là cooperative lock; scripts cần tuân theo cùng convention.

### Bài 31. application_name dùng để làm gì?

**Đáp án:** Gắn session với service/job/change để quan sát trong pg_stat_activity và logs.

### Bài 32. Vì sao cần run ID?

**Đáp án:** Liên kết các logs, metrics, retries và scheduler events của cùng một lần chạy.

### Bài 33. Vì sao không log password?

**Đáp án:** Logs thường có nhiều readers và retention dài; secret có thể bị lộ ngoài phạm vi cần thiết.

### Bài 34. psql -w có tác dụng gì?

**Đáp án:** Không prompt nhập password; thiếu credential thì fail thay vì treo job.

### Bài 35. .pgpass cần permission thế nào trên Unix?

**Đáp án:** File cần được bảo vệ, thường permission 0600 để libpq chấp nhận và tránh user khác đọc.

### Bài 36. Vì sao không dùng shell set -x với secret?

**Đáp án:** Xtrace in command sau expansion và có thể lộ credential/connection data.

### Bài 37. pipefail làm gì?

**Đáp án:** Khi pipeline có command lỗi, pipeline có thể trả non-zero thay vì chỉ theo exit status command cuối.

### Bài 38. set -e có bắt mọi lỗi trong Bash không?

**Đáp án:** Không. Nó có ngoại lệ theo ngữ cảnh; vẫn cần kiểm tra exit code và error handling rõ.

### Bài 39. ERR trap và EXIT trap khác nhau thế nào?

**Đáp án:** ERR trap xử lý một số command failures; EXIT trap chạy khi shell thoát để ghi kết quả cuối.

### Bài 40. Vì sao log file cần rotation?

**Đáp án:** Để tránh logs tăng vô hạn và làm đầy filesystem.

### Bài 41. PostgreSQL log_line_prefix có thể chứa gì?

**Đáp án:** Timestamp, PID, user, database, application_name và client address.

### Bài 42. log_min_duration_statement dùng để làm gì?

**Đáp án:** Ghi các statements vượt ngưỡng thời gian được cấu hình.

### Bài 43. pg_cancel_backend khác pg_terminate_backend thế nào?

**Đáp án:** Cancel hủy query hiện tại; terminate đóng session.

### Bài 44. Vì sao phải kiểm tra pg_stat_activity trước khi terminate?

**Đáp án:** Để xác minh đúng PID, user, database, application và tác động transaction.

### Bài 45. Postcondition là gì?

**Đáp án:** Điều kiện trạng thái cần đúng sau operation để xác nhận kết quả.

### Bài 46. Vì sao exit code 0 chưa đủ?

**Đáp án:** Script có thể chạy thành công về mặt process nhưng không tạo ra state mong muốn.

### Bài 47. Exactly-once có tự được scheduler bảo đảm không?

**Đáp án:** Không. Cần operation key, unique constraints, idempotency và reconciliation.

### Bài 48. Batch checkpoint nên commit cùng dữ liệu thế nào?

**Đáp án:** Cập nhật checkpoint trong cùng transaction với batch để dữ liệu và tiến độ nhất quán.

### Bài 49. SKIP LOCKED có trade-off gì?

**Đáp án:** Bỏ qua rows đang bị lock; cần worker/retry sau để bảo đảm rows đó cuối cùng được xử lý.

### Bài 50. Vì sao không xử lý hàng triệu rows trong một transaction dài?

**Đáp án:** Tăng lock duration, WAL, rollback cost, snapshot retention và vacuum pressure.

### Bài 51. Dry-run có thay backup không?

**Đáp án:** Không. Dry-run không bảo vệ khỏi thao tác destructive hoặc non-transactional đã commit.

### Bài 52. Vì sao CREATE INDEX CONCURRENTLY cần postflight?

**Đáp án:** Lệnh có thể thất bại và để lại index invalid; cần kiểm tra indisready/indisvalid.

### Bài 53. Vì sao không retry ngay khi job timeout?

**Đáp án:** Cần xác định server operation còn chạy không và trạng thái commit/partial effects trước khi chạy lại.

### Bài 54. Job timeout trên client có bảo đảm server query dừng ngay?

**Đáp án:** Không. Cần statement_timeout server-side và kiểm tra backend state sau khi client bị kill.

### Bài 55. Vì sao phải phân biệt warning với failure?

**Đáp án:** Một warning có thể chấp nhận được theo policy; failure phải làm job trả status không thành công hoặc cần xử lý rõ.

### Bài 56. Vì sao cần preflight target?

**Đáp án:** Ngăn script chạy nhầm cluster/database hoặc role.

### Bài 57. Retry transaction nào khi deadlock?

**Đáp án:** Retry toàn bộ transaction với logic đọc/ghi từ đầu.

### Bài 58. Khi nào cần outcome UNKNOWN?

**Đáp án:** Khi mất kết nối quanh thời điểm commit và chưa thể xác định transaction đã commit hay rollback.

### Bài 59. Scheduler cần nhận tín hiệu nào?

**Đáp án:** Exit code rõ ràng, log/run ID và trạng thái success/failure/timeout phù hợp.

### Bài 60. Lập checklist trước khi bật một job quản trị định kỳ

**Đáp án gợi ý:**

1. Xác định owner, target cluster/database và least-privilege role.
2. Cấu hình credentials qua secret manager/service file.
3. Kiểm tra preconditions và target allowlist.
4. Bật psql ON_ERROR_STOP và kiểm tra exit codes.
5. Đặt connection, lock, statement và job timeouts.
6. Thiết kế transaction boundary và tách non-transactional operations.
7. Bảo đảm idempotency, operation ledger và checkpoint.
8. Ngăn overlap bằng scheduler/advisory lock.
9. Ghi run ID, UTC timestamps, SQLSTATE, duration và rows affected.
10. Xác minh postconditions, retry budget, alerting và recovery procedure.

## 31. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Job owner | Có team/operator chịu trách nhiệm |
| Target | Cluster, database và schema được xác minh |
| Identity | Role riêng, least privilege |
| Credentials | Secret manager/service file, không log password |
| psql mode | -X, -w và ON_ERROR_STOP |
| Exit codes | Scheduler kiểm tra kết quả process |
| Transaction | Boundary và rollback behavior rõ |
| Non-transactional steps | Được tách khỏi transaction |
| Connection timeout | Có giới hạn |
| Lock timeout | Phù hợp lock budget |
| Statement timeout | Phù hợp từng operation |
| Idle transaction timeout | Có policy |
| Job timeout | Có budget tổng |
| Retry | SQLSTATE allowlist và max attempts |
| Backoff | Exponential + jitter |
| Unknown commit | Có reconciliation |
| Idempotency | Operation key/ledger/constraints |
| Concurrency | Advisory/scheduler lock |
| Batch | Size và checkpoint rõ |
| Dry-run | Preview và target validation |
| Logging | UTC, run ID, change ID, SQLSTATE |
| Log security | Redaction, permissions, retention |
| application_name | Correlate với pg_stat_activity |
| Server logs | Prefix/slow statement policy |
| Postconditions | Kiểm tra state sau commit |
| Affected rows | Expected range |
| Alerting | Có owner và failure notification |
| Resume | Có checkpoint và recovery steps |
| Rollback | Có compensating action đã review |
| Version | Script/SQL được version hóa |
| Evidence | Raw logs, metrics và exit code |
| Scheduler | Environment, timezone và overlap policy |
| Review | Job được kiểm tra định kỳ |

## 32. Tổng kết

Tự động hóa PostgreSQL đáng tin cậy cần kiểm soát target, quyền, transaction, lỗi, timeout, concurrency, retry và logs. psql phải dừng khi SQL lỗi; scheduler phải nhận đúng exit code; server-side timeouts phải giới hạn query; client/job timeouts phải giới hạn tổng thời gian; logs phải đủ để truy vết nhưng không làm lộ secrets.

Những nguyên tắc quan trọng:

1. **Xác minh target trước khi chạy.** Một script đúng trên sai database vẫn là sự cố.
2. **Bật fail-fast.** Dùng ON_ERROR_STOP và kiểm tra exit code.
3. **Đặt timeout theo lớp.** Connect, lock, statement, idle transaction và job timeout giải quyết các vấn đề khác nhau.
4. **Gom thay đổi transactional hợp lý.** Biết rõ lệnh nào không thể chạy trong transaction.
5. **Thiết kế idempotency.** Retry không được tạo duplicate hoặc làm sai dữ liệu.
6. **Retry có phân loại.** Deadlock/serialization khác permission/syntax error.
7. **Đối soát commit outcome.** Mất kết nối quanh COMMIT có thể tạo trạng thái chưa rõ.
8. **Ngăn chạy đồng thời.** Dùng scheduler lock hoặc advisory lock theo phạm vi.
9. **Ghi log có cấu trúc.** Có UTC, run ID, SQLSTATE, duration và rows affected.
10. **Bảo vệ credentials.** Không log password hoặc bật xtrace với secret.
11. **Dùng postconditions.** Exit 0 cần đi kèm xác minh trạng thái.
12. **Batch và checkpoint.** Giảm transaction dài và hỗ trợ resume.
13. **Tách non-transactional operations.** Có preflight, postflight và recovery riêng.
14. **Quan sát từ cả client và server.** application_name, pg_stat_activity và PostgreSQL logs giúp correlate.
15. **Chuẩn bị recovery trước automation.** Biết khi nào retry, resume, rollback hoặc yêu cầu operator.

Mô hình kết thúc job:

```text
Input and target validated?
            |
            v
Connection within budget?
            |
            v
Concurrency lock acquired?
            |
            v
SQL completed and committed?
            |
            v
Postconditions verified?
            |
            v
Logs and metrics persisted?
            |
            v
Exit code accurately returned?
        /              \
       Yes              No
        |                |
        v                v
    SUCCEEDED      FAILED / UNKNOWN
```

**Câu hỏi review cuối cùng:** “Nếu job mất kết nối ngay sau khi gửi COMMIT, liệu nó có thể xác định operation đã thành công mà không tạo duplicate? Nếu một migration chờ lock quá lâu, timeout nào sẽ dừng nó? Nếu psql gặp lỗi giữa file, scheduler có nhận exit code khác 0 không? Và sau một lần chạy, chúng ta có run ID, SQLSTATE, duration cùng postcondition để chứng minh trạng thái cuối không?” Một automation tốt phải trả lời được các câu hỏi đó trước khi được đưa vào lịch chạy production.
