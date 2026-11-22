# Chống trùng yêu cầu tạo job và khôi phục sau khởi động lại

Một người dùng yêu cầu xuất báo cáo gồm hàng triệu giao dịch. API không thể trả tệp ngay nên nhận yêu cầu, tạo **job xuất báo cáo** và trả đường dẫn để kiểm tra tiến độ. Đúng lúc server lưu job thành công, kết nối HTTP bị ngắt. Người dùng bấm lại; nếu mỗi lần POST đều tạo một job mới, hệ thống sẽ xử lý cùng một báo cáo nhiều lần, chiếm tài nguyên hoặc phát sinh chi phí. Nếu ứng dụng còn lưu hàng đợi trong RAM, việc khởi động lại có thể làm job đã nhận biến mất.

Thiết kế đúng cần giải quyết **hai vấn đề độc lập nhưng liên quan**:

1. **Chống trùng khi tiếp nhận (submission idempotency):** nhiều request mang cùng ý định phải quy về **một logical job**, kể cả gửi đồng thời hoặc retry sau timeout.
2. **Khôi phục thực thi (durable recovery):** khi API, worker hoặc broker khởi động lại, những job đã được chấp nhận vẫn có thể tìm thấy, chạy lại có kiểm soát hoặc được đối soát.

Bài thuộc chương **Xử lý bất đồng bộ** của module **INTEGRATION_API_REST**. Ta kết hợp hợp đồng tài nguyên/URI, HTTP status, idempotency, Java/Spring, database, queue, bảo mật và kiểm thử sự cố. Ví dụ dùng **PostgreSQL**, nhưng nguyên tắc giao dịch và nhận diện operation áp dụng được cho công nghệ tương đương.

## 1. Mục tiêu và bất biến hệ thống

Sau bài này, bạn có thể thiết kế API tạo job với **POST + Idempotency-Key**, đọc trạng thái bằng **GET**, trả **202 Accepted + Location**, bảo đảm ghi nhận bền vững trước khi phản hồi; dùng **unique constraint/transaction/outbox** để chống trùng; sử dụng **lease + fencing** cho worker; và kiểm thử restart, crash, retry, phân quyền và tác động bên ngoài.

Ba bất biến cần viết thành tiêu chí kiểm chứng:

- **I1 — Một logical request, một job:** trong phạm vi khóa đã công bố, cùng idempotency key và payload tương đương không tạo job mới. Cùng key nhưng payload khác phải bị từ chối.
- **I2 — Accepted nghĩa là truy vết được:** sau khi server trả 202, job và thông tin khôi phục đã được **commit vào kho bền vững**. Worker có thể chưa chạy, nhưng không được chỉ nằm trong bộ nhớ một process.
- **I3 — Thử lại không nhân đôi tác động nghiệp vụ:** có thể có nhiều *attempt*, event delivery hoặc worker execution; hiệu ứng cần tính đúng phải được dedupe hoặc đối soát ở ranh giới thích hợp.

**I1 không suy ra I3.** Dedupe ở API ngăn tạo hai job nhưng không tự ngăn một worker chạy lại tác vụ gửi email hoặc gọi cổng thanh toán hai lần sau crash.

## 2. Hợp đồng HTTP: tạo job rồi theo dõi

Giả sử người dùng tạo báo cáo với bộ lọc:

~~~http
POST /v1/report-exports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: export-2026-11-customer-73

{"from":"2026-11-01","to":"2026-11-17","format":"csv"}
~~~

Sau khi **commit job**:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/j-73
Content-Type: application/json
Cache-Control: no-store

{
  "jobId": "j-73",
  "status": "QUEUED",
  "statusUrl": "/v1/jobs/j-73"
}
~~~

**202 Accepted** nói yêu cầu đã được nhận xử lý nhưng công việc **chưa hoàn tất**; nó không bảo đảm job chắc chắn sẽ thành công. **Location** ở đây là URI của job resource theo *hợp đồng của API*, để client tra cứu. Không nhầm 202 với **201 Created**: nếu API mô hình hóa việc tạo job resource đã hoàn tất ngay, 201 cũng có thể phù hợp, nhưng bài này chọn 202 để nhấn mạnh xử lý bất đồng bộ chưa xong.

Client không cần giữ kết nối HTTP mở đến khi báo cáo sẵn sàng:

~~~http
GET /v1/jobs/j-73 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "jobId": "j-73",
  "status": "SUCCEEDED",
  "result": {"href": "/v1/report-exports/j-73/file"},
  "finishedAt": "2026-11-18T09:20:00Z"
}
~~~

GET chỉ đọc trạng thái; job FAILED vẫn có thể được GET bằng HTTP 200. **HTTP status** mô tả request, còn **job.status** mô tả tiến trình.

### 2.1. Request lặp nhận gì?

| Trường hợp POST | Response đề xuất | Hiệu ứng |
|---|---|---|
| Key mới, payload hợp lệ | **202 + Location** của job mới | Tạo một job và ghi bền vững |
| Cùng key, cùng payload, job đang chờ/chạy | **202 + cùng Location** | Không tạo job mới |
| Cùng key, cùng payload, job đã xong | **200 + cùng Location** và trạng thái hiện tại | Không tạo job mới; status có thể khác lần đầu |
| Cùng key, payload khác | **409 Conflict** với mã **IDEMPOTENCY_KEY_REUSED** | Không sửa job cũ và không tạo job mới |
| Thiếu key mà endpoint yêu cầu | **400 Bad Request** | Không nhận job |
| Dữ liệu không hợp lệ | **400/422** theo contract | Không tạo job |
| Chưa xác thực/không được phép | **401/403**, hoặc **404** khi che giấu resource | Không tiết lộ job của người khác |
| Quá tải hoặc hạn mức | **429/503** tùy nguyên nhân; có thể kèm Retry-After | Không tuyên bố đã nhận job nếu chưa commit |

Đây là **chính sách ví dụ**, không phải mã bắt buộc của mọi API (một số dùng 422 khi key cũ đi với payload khác). Idempotency bảo đảm **không nhân đôi logical operation**, không bắt mọi response giống nhau.

Nếu client gặp timeout/502/504 khi tạo job, **không sinh key mới cho cùng thao tác**. Hãy retry **cùng key/cùng payload**, hoặc truy vấn theo operation ID nếu contract cung cấp. Một **504** từ gateway không chứng minh transaction tạo job đã rollback.

### 2.2. Thông tin lỗi có cấu trúc

Ví dụ theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/idempotency-key-reused",
  "title": "Idempotency key belongs to another request",
  "status": 409,
  "code": "IDEMPOTENCY_KEY_REUSED",
  "detail": "Use the original payload or a new key for a new operation."
}
~~~

**code** là extension của ứng dụng, không phải member bắt buộc của RFC 9457. Không trả nguyên payload, khóa bí mật hoặc stack trace trong detail.

## 3. Phạm vi của idempotency key và dấu vân tay request

**Idempotency-Key** chỉ có ý nghĩa khi server định nghĩa nó nhận diện điều gì và trong bao lâu.

Ví dụ khóa dữ liệu:

~~~text
scope = (tenantId, operationType, idempotencyKey)
operationType = "CREATE_REPORT_EXPORT"
payloadFingerprint = SHA-256(canonicalBusinessRequest)
~~~

Phạm vi phải **do server xác định từ principal/tenant đã xác thực**, không chỉ tin một trường tenantId do client khai báo. Hai tenant có thể vô tình dùng cùng một chuỗi key nhưng **không được đọc, sửa hoặc lấy job của nhau**.

### 3.1. Cùng payload nghĩa là gì?

JSON có thể khác dấu cách hoặc thứ tự key mà cùng ý nghĩa:

~~~json
{"from":"2026-11-01","to":"2026-11-17","format":"csv"}
~~~

~~~json
{"format":"csv","to":"2026-11-17","from":"2026-11-01"}
~~~

Nếu hợp đồng coi hai request tương đương, fingerprint nên tính từ **đối tượng nghiệp vụ đã validate/normalize** (trường, timezone, ngày, định dạng, tùy chọn mặc định, version schema), không phải đơn giản hash raw JSON bytes. Trường nào ảnh hưởng kết quả phải có mặt trong fingerprint; không được bỏ qua filter, account hay định dạng xuất.

Hash chỉ dùng để **so sánh tính nhất quán của yêu cầu**; nó không thay quyền truy cập và không bảo đảm bí mật. Không ghi raw request chứa dữ liệu nhạy cảm vào access log để phục vụ dedupe.

### 3.2. Thời hạn lưu key

Nếu chính sách lưu key **72 giờ**, client phải được thông báo rằng gửi lại sau thời hạn đó có thể không còn được suy ra là cùng operation. Nhưng nếu job đã chạy và có tác động không thể lặp, **xóa bản ghi chống trùng trước khi hết khả năng replay thực tế là nguy hiểm**.

Trong hệ thống báo cáo, có thể giữ job/status 30 ngày và idempotency mapping theo cùng vòng đời hoặc lưu tombstone tối thiểu lâu hơn. Với nghiệp vụ thanh toán/hoàn tiền, cần thêm **business operation ID và ràng buộc duy nhất bền vững**, không chỉ TTL của Redis. Nếu user cố tình tạo **yêu cầu mới**, họ dùng key mới; cùng payload + key mới **không mặc nhiên bị chặn** trừ khi nghiệp vụ có một constraint riêng.

## 4. Thiết kế dữ liệu: unique constraint là điểm chống trùng đáng tin cậy

Một ví dụ PostgreSQL tối giản:

~~~sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    operation_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request_payload JSONB NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    result_uri TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT jobs_dedup UNIQUE
        (tenant_id, operation_type, idempotency_key)
);

CREATE INDEX jobs_recovery_idx
    ON jobs (status, next_run_at, lease_until);

CREATE TABLE job_outbox (
    event_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    event_type TEXT NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Production cần CHECK/enum, retention, index theo tenant và phân quyền; UUID không phải authorization.

### 4.1. Một transaction cho job + tín hiệu giao việc

~~~mermaid
sequenceDiagram
    actor C as Client
    participant A as Orders/Exports API
    participant D as Durable DB
    participant W as Dispatcher/Worker
    C->>A: POST /report-exports + key K
    A->>D: BEGIN
    A->>D: INSERT jobs (unique tenant,operation,K)
    A->>D: INSERT outbox(event for job)
    A->>D: COMMIT
    D-->>A: Commit OK
    A-->>C: 202 + Location /jobs/J
    W->>D: Đọc outbox / quét pending jobs
    W->>D: Claim job J
    Note over W,D: Worker có thể bắt đầu sau khi API restart
~~~

**Chỉ trả 202 khi transaction đã commit.** Nếu DB không thể ghi bền vững, đừng gửi 202 rồi giữ một job duy nhất trong bộ nhớ. Outbox được ghi cùng transaction để không rơi vào khoảng trống “đã có job nhưng sự kiện enqueue bị mất”. Worker vẫn cần **quét job ở DB** để có đường khôi phục nếu outbox publisher hoặc broker hỏng.

### 4.2. Hai POST đồng thời cùng key

Không dùng cách:

~~~text
if not exists(key):
    insert(job)
~~~

trên hai request đồng thời nếu không có lock/unique constraint. Cả hai có thể thấy “chưa có” rồi tạo hai job.

Trên PostgreSQL có thể dùng:

~~~sql
INSERT INTO jobs (
    job_id, tenant_id, operation_type, idempotency_key,
    request_hash, request_payload, status
) VALUES (
    :job_id, :tenant_id, 'CREATE_REPORT_EXPORT', :key,
    :hash, CAST(:payload AS jsonb), 'QUEUED'
)
ON CONFLICT (tenant_id, operation_type, idempotency_key)
DO NOTHING
RETURNING job_id;
~~~

Nếu INSERT trả job_id, ghi outbox rồi commit. Nếu không, ở **READ COMMITTED** dùng SELECT mới tìm key đã commit, so request_hash rồi trả URI cũ hoặc 409. Nếu bản ghi cạnh tranh chưa hiển thị, retry truy vấn có giới hạn; **unique constraint** chống race.

**Không enqueue trước commit:** worker có thể nhận event rồi không tìm thấy job hoặc job rollback. **Không gọi broker trực tiếp trong transaction rồi tưởng đã atomic:** commit DB và publish mạng không chia sẻ một transaction chuẩn; dùng outbox hoặc một thiết kế giao dịch được chứng minh tương đương.

## 5. Vòng đời job và khôi phục sau restart

Một state machine đủ dùng:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED: Commit create-job
    QUEUED --> RUNNING: Claim với lease
    RUNNING --> SUCCEEDED: Kết quả đã lưu
    RUNNING --> RETRY_WAIT: Lỗi tạm thời
    RETRY_WAIT --> RUNNING: Đến hạn và claim
    RUNNING --> FAILED: Lỗi vĩnh viễn hoặc hết attempts
    RUNNING --> RUNNING: Lease hết hạn và worker khác claim lại
    QUEUED --> CANCELLED: Hủy trước khi chạy
    RETRY_WAIT --> CANCELLED: Hủy trước khi retry
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

Trong thực tế, nhánh RUNNING → RUNNING là **một attempt mới**, không phải worker cũ tự biết mình đã bị thay thế. Có thể thêm **CANCEL_REQUESTED** cho tác vụ đang chạy, heartbeat, timeout công việc và cơ chế operator retry. Job **FAILED** nên ghi errorCode an toàn và thời điểm thất bại; không biến lỗi tạm thời thành vòng lặp vô hạn.

### 5.1. Claim job bằng lease, không bằng biến RAM

Worker lấy quyền xử lý bằng một thao tác **nguyên tử**, đặt:

- **lease_token:** ID riêng cho attempt hiện tại.
- **lease_until:** thời điểm hết quyền xử lý nếu không gia hạn.
- **attempt_count:** số lần bắt đầu xử lý, để giới hạn retry và phát cảnh báo.

PostgreSQL hỗ trợ một mẫu claim theo kiểu:

~~~sql
WITH candidate AS (
    SELECT job_id
    FROM jobs
    WHERE (
        status IN ('QUEUED', 'RETRY_WAIT')
        OR (status = 'RUNNING' AND lease_until < now())
    )
      AND next_run_at <= now()
    ORDER BY next_run_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE jobs j
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    lease_token = :new_lease_token,
    lease_until = now() + interval '120 seconds',
    updated_at = now()
FROM candidate c
WHERE j.job_id = c.job_id
RETURNING j.*;
~~~

**SKIP LOCKED** là cơ chế cụ thể của PostgreSQL, hữu ích khi nhiều worker tranh quyền. Cần giới hạn số worker, số lease, thời gian xử lý và cách **renew lease/heartbeat**; một tác vụ 10 phút không thể hoàn thành an toàn nếu lease chỉ 2 phút mà không gia hạn.

Khi lưu kết quả, dùng **fencing** để worker cũ không ghi đè trạng thái sau khi lease đã thuộc về worker khác:

~~~sql
UPDATE jobs
SET status = 'SUCCEEDED',
    result_uri = :result_uri,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :my_lease_token
  AND lease_until > now();
~~~

**Số hàng cập nhật bằng 0** nghĩa là worker này không còn quyền finalize theo policy. Không được tiếp tục xuất kết quả như đã thành công; cần kiểm tra lease và trạng thái hiện tại. Ở production, có thể dùng **lease_epoch tăng đơn điệu** làm fencing token, quan trọng khi hệ thống đích cần so sánh thứ tự attempt.

### 5.2. Worker restart tìm lại job ở đâu?

**Nguồn sự thật là durable job store**, không phải số phần tử còn trong thread pool:

1. Worker hoặc bộ scheduler khởi động, đọc các job **QUEUED/RETRY_WAIT** đã đến hạn.
2. Tìm các job **RUNNING có lease hết hạn** để reclaim theo quy tắc.
3. Claim nguyên tử, nhận lease token mới, kiểm tra giới hạn attempts.
4. Xử lý lại từ checkpoint hoặc chạy lại tác vụ có hiệu ứng idempotent.
5. Commit kết quả có điều kiện; nếu lỗi tạm thời, ghi **RETRY_WAIT + next_run_at** có backoff/jitter.

Queue/broker giúp **đánh thức nhanh** worker; nó không nhất thiết là nguồn sự thật duy nhất. Nếu outbox event bị gửi hai lần, cả hai worker vẫn phải tranh claim an toàn. Nếu broker tạm mất, scanner định kỳ vẫn tìm được job đã commit.

### 5.3. Lease không chặn tác động bên ngoài lặp

Worker A có thể đã yêu cầu PSP hoàn tiền rồi **pause quá lâu**; lease hết hạn, worker B nhận cùng job. Cơ chế fencing ở **bảng jobs** chỉ ngăn A ghi đè status; nó **không tự hủy giao dịch PSP đã gửi**.

Đối với email, thanh toán, ERP hoặc phân bổ tài nguyên bên ngoài, cần một **external operation ID ổn định** (ví dụ refundId hay reportArtifactId) cùng idempotency được dịch vụ đích hỗ trợ. Nếu downstream không hỗ trợ, worker phải **tra cứu/đối soát trước khi thử lại** hoặc chấp nhận và quản trị khả năng at-least-once. Không hứa “exactly-once execution” chỉ vì có lease và UNIQUE key.

## 6. Các điểm crash phải kiểm chứng

| Thời điểm lỗi | Điều có thể đã xảy ra | Cách khôi phục an toàn |
|---|---|---|
| Trước transaction commit | Chưa có job được nhận | POST retry cùng key có thể tạo job |
| Commit thành công, response 202 bị mất | Job đã tồn tại, client tưởng thất bại | Retry cùng key tìm lại **cùng job ID** |
| Commit job, API khởi động lại trước khi phát queue event | Job vẫn nằm trong DB/outbox | Dispatcher đọc outbox; scanner phát hiện QUEUED |
| Outbox publisher gửi event rồi mất ACK | Event có thể đã tới broker | Phát lại event được phép; worker claim/dedupe |
| Worker claim xong rồi crash | RUNNING có lease, chưa hoàn tất | Lease hết hạn và worker khác reclaim |
| Worker đã ghi tệp, chưa ghi SUCCEEDED | Artifact có thể tồn tại | Ghi artifact bằng ID/tên ổn định; kiểm tra trước khi tạo lại |
| PSP hoàn tất tác động nhưng worker crash trước khi lưu kết quả | Kết quả ngoài hệ thống chưa rõ | Tra cứu PSP bằng external operation ID; không tạo key mới |
| Worker cũ sống lại sau khi lease bị thay | Có hai attempt cùng lúc | Fencing khi ghi DB; downstream dedupe/đối soát |
| DB hoặc storage mất tính bền vững | Không thể xác minh job đã commit | Cần backup/replication/restore, RPO/RTO; không thể giải quyết chỉ bằng retry |

Phân biệt **retry request tạo job** (chống trùng bằng key của client) với **retry execution** (claim/lease, trạng thái, side effect). Chúng là hai ranh giới cần bảo vệ riêng.

**Retry execution** cần exponential backoff, jitter, max attempts và tổng deadline theo SLO; lỗi vĩnh viễn đưa vào FAILED/dead-letter workflow để điều tra. Khi shutdown, worker ngừng claim mới và chuyển giao có kiểm soát; nhưng crash vẫn có thể xảy ra nên **durable job store và lease recovery**, không phải graceful shutdown, là bảo đảm chính.

## 7. Java/Spring: controller mỏng, transaction ở dịch vụ

Ví dụ dùng **Spring Boot 3 / Java 17**. API/controller hoàn chỉnh về ý tưởng, nhưng các interface lưu trữ, xác thực và worker là thành phần phải triển khai thêm; SQL PostgreSQL ở mục 4 là cơ sở cho repository.

### 7.1. Tạo job và tra trạng thái

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.net.URI;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

record ExportRequest(
        @NotNull LocalDate from,
        @NotNull LocalDate to,
        @NotBlank @Pattern(regexp = "csv|json") String format) {}

record Submission(UUID jobId, String status, boolean created) {}
record JobView(UUID jobId, String status, String resultUri) {}

interface TenantResolver {
    UUID tenantId(Authentication authentication);
}

interface JobQueries {
    // Luôn lọc theo tenant và quyền đọc của principal hiện tại.
    JobView findVisible(UUID tenantId, UUID jobId);
}

@RestController
@RequestMapping("/v1")
class AsyncJobController {
    private final ExportSubmissionService submissions;
    private final TenantResolver tenants;
    private final JobQueries queries;

    AsyncJobController(ExportSubmissionService submissions,
            TenantResolver tenants, JobQueries queries) {
        this.submissions = submissions;
        this.tenants = tenants;
        this.queries = queries;
    }

    @PostMapping("/report-exports")
    ResponseEntity<JobView> create(
            @Valid @RequestBody ExportRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false)
                String key,
            Authentication authentication) {

        if (key == null || key.isBlank() || key.length() > 128) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Valid Idempotency-Key required");
        }
        UUID tenant = tenants.tenantId(authentication);
        Submission s = submissions.submit(tenant, key, request);
        URI location = URI.create("/v1/jobs/" + s.jobId());
        boolean active = switch (s.status()) {
            case "QUEUED", "RUNNING", "RETRY_WAIT" -> true;
            default -> false;
        };
        return ResponseEntity
                .status(active ? HttpStatus.ACCEPTED : HttpStatus.OK)
                .location(location)
                .cacheControl(CacheControl.noStore())
                .body(new JobView(s.jobId(), s.status(), null));
    }

    @GetMapping("/jobs/{jobId}")
    ResponseEntity<JobView> status(
            @PathVariable UUID jobId, Authentication authentication) {
        UUID tenant = tenants.tenantId(authentication);
        JobView view = queries.findVisible(tenant, jobId);
        if (view == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view);
    }
}
~~~

Trong ứng dụng thực tế, **@Valid** chưa thay kiểm tra **from ≤ to**, giới hạn độ dài khoảng thời gian, quyền xuất dữ liệu và quota. Ví dụ còn thiếu controller advice chuẩn Problem Details và trả result URI ở POST khi job đã xong; GET cung cấp trạng thái/kết quả hiện hành. **Idempotency-Key** cần kiểm tra charset/độ dài theo contract trước khi dùng làm dữ liệu lưu.

### 7.2. Transaction tiếp nhận dùng chung một job

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

record StoredJob(UUID jobId, String requestHash, String status) {}

interface DurableJobStore {
    // Dùng INSERT ... ON CONFLICT DO NOTHING RETURNING job_id.
    Optional<StoredJob> tryCreate(
            UUID tenant, String operation, String key,
            String requestHash, ExportRequest payload);

    // SELECT theo tenant + operation + key sau khi conflict được giải quyết.
    StoredJob findByKey(UUID tenant, String operation, String key);

    // Ghi outbox trong CÙNG transaction với job mới.
    void insertOutbox(UUID eventId, UUID jobId, String eventType);
}

@Service
class ExportSubmissionService {
    private static final String OPERATION = "CREATE_REPORT_EXPORT";
    private final DurableJobStore store;

    ExportSubmissionService(DurableJobStore store) {
        this.store = store;
    }

    @Transactional
    public Submission submit(UUID tenant, String key, ExportRequest req) {
        if (req.from().isAfter(req.to())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid date range");
        }
        String normalizedFormat = req.format().toLowerCase(Locale.ROOT);
        String canonical = req.from() + "|" + req.to()
                + "|" + normalizedFormat;
        String hash = sha256(canonical);

        Optional<StoredJob> inserted = store.tryCreate(
                tenant, OPERATION, key, hash,
                new ExportRequest(req.from(), req.to(), normalizedFormat));

        if (inserted.isPresent()) {
            StoredJob job = inserted.get();
            store.insertOutbox(
                    UUID.randomUUID(), job.jobId(), "JOB_SUBMITTED");
            return new Submission(job.jobId(), job.status(), true);
        }

        StoredJob existing = store.findByKey(tenant, OPERATION, key);
        if (!existing.requestHash().equals(hash)) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "Idempotency key reused");
        }
        return new Submission(
                existing.jobId(), existing.status(), false);
    }

    private static String sha256(String input) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

**Điểm then chốt:** transaction của method submit kết thúc/commit khi lời gọi service qua Spring proxy trả về cho controller; chỉ sau đó controller mới tạo response **202**. Không gọi một method @Transactional qua **self-invocation** rồi tưởng proxy đã mở transaction. Repository phải thật sự enforce unique constraint, SELECT bản ghi theo phạm vi tenant và ghi outbox cùng datasource/transaction.

Canonical string chỉ phù hợp với ba trường đã validate; JSON phức tạp cần chuẩn hóa có version và bao phủ mọi tham số. Repository phải xử lý race bằng retry truy vấn giới hạn, **không tạo job thứ hai**.

### 7.3. Không dùng @Async làm nguồn lưu trữ job

**@Async**, executor hay CompletableFuture chỉ chạy việc trong process, **không tự lưu job/lease/dedupe**. Chỉ dùng chúng sau durable commit và vẫn cần scanner khi restart.

## 8. Bảo mật, phân quyền và giới hạn tài nguyên

Một job xuất báo cáo có thể chứa thông tin tài chính hoặc dữ liệu của tenant. Bảo vệ **submission** và **status/result** bằng những ranh giới sau:

- **Tenant/owner từ authentication:** scope của unique key, truy vấn job và quyền tải kết quả phải được lấy từ principal đáng tin. Job ID hoặc Idempotency-Key không phải secret cấp quyền.
- **Không lộ tồn tại:** GET job của tenant khác trả 404 hoặc 403 theo policy nhất quán. Không cho client suy đoán tồn tại từ thời gian response hay thông báo key trùng.
- **Cache-Control: no-store:** phù hợp cho phản hồi trạng thái/kết quả cá nhân; URL tải tệp cần quyền, hạn sử dụng và lưu trữ phù hợp.
- **Giới hạn abuse:** max jobs đang chạy theo user/tenant, rate limit POST, kích thước request, phạm vi ngày, thời gian chạy, dung lượng tệp và số lần polling.
- **Payload và artifact:** encrypt at rest khi cần, retention rõ, tránh ghi filter nhạy cảm và signed download URL vào log. Nếu có webhook/callback URL, chống SSRF và xác thực đích.
- **Quyền không bất biến mãi:** nếu user bị thu hồi quyền trước khi tải kết quả, endpoint tải phải kiểm tra lại; không dựa vào quyền từ lúc tạo job.

**Idempotency không thay authorization**. Một user không được xem job của người khác chỉ vì biết cùng một key; response trùng key phải được lọc theo scope đã xác thực trước khi hiển thị metadata.

## 9. Kiểm thử hành vi dưới lỗi thật

| Test | Cách thực hiện | Tiêu chí PASS |
|---|---|---|
| Retry POST | Gửi 10 request cùng key/payload | Một job ID, một bản ghi job, không nhân số artifact |
| Race | Gửi 20 POST đồng thời cùng key | Unique constraint chỉ cho một INSERT thắng |
| Key khác payload | Retry với khoảng ngày khác | 409, không thay đổi job cũ |
| Commit rồi mất response | Proxy cắt response sau commit | Retry trả cùng job, không tạo mới |
| API restart | Restart ngay sau 202 | GET tìm được job từ DB |
| Mất broker | Commit job khi broker tắt | Outbox/scanner phục hồi việc xử lý |
| Worker chết sau claim | Kill worker khi RUNNING | Lease hết hạn, worker khác reclaim |
| Worker cũ hoàn thành muộn | Cho A hết lease, B claim, rồi A finalize | Update có fencing của A thất bại |
| External side effect | PSP/ERP thành công nhưng mất ACK | Đối soát, không nhân đôi giao dịch |
| Cross-tenant | Tenant B đoán key/job ID của A | Không đọc được status, payload hay artifact |
| Retry limit | Dependency liên tục lỗi | RETRY_WAIT/backoff rồi FAILED có thể điều tra |

Trong integration test Spring, có thể dùng **MockMvc** kiểm tra 202/Location/409/GET, nhưng chỉ test controller **không chứng minh** durable commit hay recovery. Cần PostgreSQL thật hoặc môi trường tương đương, fault injection **sau commit**, và kiểm tra số bản ghi/result thực tế. Không mô phỏng “mất response” bằng exception trước khi INSERT.

## 10. Bài tập thiết kế

Hệ thống nhận yêu cầu **POST /v1/invoice-exports** của 500 khách hàng. Mỗi job mất 2–5 phút, worker có thể chết giữa chừng; kết quả là một PDF trên object storage. Khách retry khi 504, có thể tải lại sau một ngày. Một số khách dùng hai tab gửi cùng key.

**Yêu cầu:** (1) Viết response 202 và GET status; (2) chọn scope/key/fingerprint/retention; (3) đề xuất unique constraint và transaction outbox; (4) mô tả claim lease, heartbeat, fencing và restart scanner; (5) thiết kế artifact name, phân quyền tải, quota; (6) chọn ít nhất sáu test ở mục 9.

**Gợi ý:** scope gồm tenant + loại export + key; fingerprint bao gồm bộ lọc, thời gian, format và version schema. Commit job/outbox trước 202. Worker ghi tệp vào **object key ổn định theo jobId**, xác minh checksum, rồi finalize bằng lease token; thao tác upload lại không tạo hai artifact có ý nghĩa độc lập. Tenant chỉ tải qua endpoint kiểm tra quyền hoặc signed URL ngắn hạn. Giữ key ít nhất qua cửa sổ retry đã công bố và thêm chính sách lưu job/artifact có thể kiểm chứng. Nếu storage báo timeout sau khi upload, kiểm tra object trước khi upload lại.

## 11. Checklist và tài liệu tham khảo

- [ ] 202 chỉ phát sau durable commit; GET job có trạng thái và quyền rõ ràng.
- [ ] Unique constraint chống race, same key/different payload bị từ chối.
- [ ] Job/outbox cùng transaction, broker event có thể phát lại an toàn.
- [ ] Worker có lease, heartbeat, fencing, retry budget và scanner sau restart.
- [ ] Side effect ngoài DB có operation ID, dedupe hoặc reconciliation.
- [ ] Có quota, TTL/retention, no-store, isolation theo tenant và quyền tải artifact.
- [ ] Test bao phủ timeout sau commit, restart, concurrency và crash giữa external call.

Tài liệu: **RFC 9110 HTTP Semantics** (202 và ngữ nghĩa phương thức), https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **PostgreSQL INSERT/ON CONFLICT**, https://www.postgresql.org/docs/current/sql-insert.html; **PostgreSQL SELECT / SKIP LOCKED**, https://www.postgresql.org/docs/current/sql-select.html; **Spring Transaction Management**, https://docs.spring.io/spring-framework/reference/data-access/transaction.html.

**Kết luận:** chống trùng POST là **bảo đảm ở ranh giới tiếp nhận**, còn khôi phục sau restart là **bảo đảm ở ranh giới thực thi**. Cần khóa operation bền vững, commit job/outbox trước 202, worker lease/fencing và đối soát side effect. Khi đó retry có thể gây nhiều attempt nhưng vẫn hướng về **một job có thể truy vết**, không mất việc đã nhận hoặc nhân đôi kết quả nghiệp vụ.
