# Tạo job bất đồng bộ, theo dõi trạng thái và tải kết quả

Một API xuất lịch sử đơn hàng có thể cần vài phút để tổng hợp hàng trăm nghìn bản ghi. Nếu **POST /v1/report-jobs** giữ kết nối HTTP mở tới khi xuất xong, client/proxy dễ timeout; người dùng bấm thử lại tạo thêm tác vụ, hệ thống tiêu tốn nhiều CPU và có nguy cơ tải nhầm dữ liệu của tenant khác. Bài thực hành này xây một **REST API nhận job bền vững, cho phép theo dõi trạng thái và chỉ tải kết quả sau khi sẵn sàng**.

Đây là bài thuộc chương **Thực hành tổng hợp** của module **INTEGRATION_API_REST**. Nó kết hợp thiết kế resource/URI, method và HTTP status, hợp đồng JSON, phân trang dữ liệu nguồn, idempotency, cache, OpenAPI, OAuth2/JWT, phân quyền, Problem Details, observability và kiểm thử bằng **Java 17+, Spring Boot 3+, PostgreSQL** (hoặc công nghệ tương đương). Các mã nguồn là **mẫu triển khai có những thành phần cần tích hợp**, không phải một project tự chạy khi sao chép từng khối riêng lẻ.

## 1. Kết quả cần đạt và ranh giới bài tập

Sau khi hoàn thành, người học cần tạo được một luồng end-to-end:

1. Client gửi **POST /v1/report-jobs** kèm tiêu chí lọc và **Idempotency-Key**; server ghi job vào DB trước khi trả **202 Accepted**.
2. Client gọi **GET /v1/report-jobs/{jobId}** để xem **QUEUED → RUNNING → SUCCEEDED** hoặc **FAILED/CANCELLED**, có thời gian và tiến độ hợp lý.
3. Worker claim job từ DB, đọc dữ liệu theo từng lô, sinh tệp **CSV** có giới hạn và lưu vào private object storage; xử lý crash/retry không phát nhiều kết quả sai.
4. Khi SUCCEEDED, client dùng **GET /v1/report-jobs/{jobId}/result** để tải tệp, không đoán URL object storage.
5. API enforce **tenant/owner/scope**, phân biệt **401/403/404/409/410/429/5xx**, có TTL, deadline, retry/backoff, idempotency và cancellation theo chính sách.
6. Tài liệu hóa OpenAPI, chạy kiểm thử REST + DB + worker + object storage, tái hiện **timeout, crash sau upload, retry cùng key và truy cập xuyên tenant**.

### 1.1. Tình huống nghiệp vụ và dữ liệu đầu vào

Đối tượng cần xuất là **đơn hàng trong tenant của người gọi**, từ thời điểm bắt đầu đến kết thúc, và một status tùy chọn. Tệp kết quả có tối đa **100.000 dòng** và tối đa **50 MiB** (giá trị bài tập; có thể thay bằng quota do hệ thống thật công bố). Mỗi tenant có tối đa **3 job đang QUEUED/RUNNING**, job phải kết thúc hoặc timeout trong **15 phút**. Tệp thành công có **TTL 24 giờ**; metadata job lưu lâu hơn theo policy audit. Không triển khai thao tác thanh toán hoặc side effect tài chính.

Request mẫu:

~~~http
POST /v1/report-jobs HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 9a2d49a1-c3e5-41be-a859-1c8bbaec85c2
Content-Type: application/json
Accept: application/json

{
  "format": "CSV",
  "from": "2026-11-01T00:00:00Z",
  "to": "2026-11-15T00:00:00Z",
  "status": "PAID"
}
~~~

**Phạm vi:** một REST API, một database transaction manager, worker riêng và private object storage giả lập hoặc thật. Không cần thiết kế hệ distributed workflow engine tổng quát. Với các yêu cầu nặng hơn, có thể chuyển sang broker/outbox nhưng phải giữ nguyên hợp đồng client.

### 1.2. Sản phẩm người học phải nộp

| Deliverable | Bằng chứng kiểm chứng |
|---|---|
| **API contract** | OpenAPI, request/response examples, status/error matrix |
| **Schema & migrations** | Jobs, idempotency records hoặc khóa duy nhất, lease/fencing, result metadata |
| **REST controller/service** | POST 202, GET status 200, GET result 200 hoặc lỗi phù hợp |
| **Worker và storage adapter** | Claim, heartbeat/deadline, stream CSV, publish result có thể retry |
| **Security** | JWT validation, scope, row-level tenant/owner isolation, signed download policy |
| **Testing** | MockMvc/WebTestClient, PostgreSQL/Testcontainers, storage fake, fault injection |
| **Vận hành** | Metrics, trace/log correlation, cleanup TTL, runbook cho stuck jobs |

**Tiêu chí quan trọng:** 202 không phải bằng chứng báo cáo đã xuất xong; job phải được **persist bền vững** trước khi API công nhận “Accepted”. Số lần client gửi HTTP có thể lớn hơn một, nhưng **một logical request với cùng idempotency key/payload chỉ tạo một job**.

## 2. Thiết kế tài nguyên và HTTP contract trước khi viết Java

Ta dùng resource **report-job**, không coi việc chạy ngầm là một thread duy nhất của request HTTP. URI công khai:

| Method + URI | Ý nghĩa | Thành công thường thấy |
|---|---|---|
| **POST /v1/report-jobs** | Tạo yêu cầu xuất báo cáo bền vững | **202 Accepted**, Location tới job |
| **GET /v1/report-jobs/{id}** | Đọc trạng thái/tiến độ hiện tại | **200 OK**, JSON state |
| **GET /v1/report-jobs/{id}/result** | Tải tệp khi SUCCEEDED | **200 OK**, text/csv hoặc redirect có điều kiện |
| **DELETE /v1/report-jobs/{id}** | Yêu cầu hủy (mở rộng tùy chọn) | **202 Accepted** nếu cancellation chưa hoàn tất |

Đừng dùng GET để **khởi động** job hay DELETE để xóa file ngay khi worker chưa ngừng an toàn. Endpoint **GET result** chỉ cung cấp biểu diễn đã hoàn tất; nếu chưa xong, có thể trả **409 Conflict** với mã ổn định **RESULT_NOT_READY** và link status, thay vì trả 200 chứa tệp trống. Khi TTL đã hết, **410 Gone** có thể dùng nếu resource/result đã từng tồn tại và policy muốn công bố sự hết hạn; với resource không thuộc quyền truy cập vẫn phải áp chính sách **404/403 không tiết lộ thông tin**.

### 2.1. Tạo job: 202 + Location + Retry-After

~~~http
HTTP/1.1 202 Accepted
Location: /v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{
  "id": "572aa218-a183-4a15-820c-d18a65451a10",
  "state": "QUEUED",
  "createdAt": "2026-11-18T09:00:00Z",
  "progress": {
    "processed": 0,
    "total": null
  },
  "links": {
    "self": "/v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10"
  }
}
~~~

**202 nghĩa là request đã được nhận để xử lý, chưa hứa outcome.** Trong bài tập, việc nhận bền vững được chứng minh bằng **DB commit của job record**, không chỉ đặt Runnable vào bộ nhớ. **Location** trỏ tới job status resource; nó **không phải** URI tệp kết quả chưa có. **Retry-After: 3** là khuyến nghị thời gian polling tính bằng giây, **không** phải lời cam kết job sẽ hoàn thành trong 3 giây.

### 2.2. Theo dõi: 200 và trạng thái có thể kiểm chứng

~~~http
GET /v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Retry-After: 5
Content-Type: application/json

{
  "id": "572aa218-a183-4a15-820c-d18a65451a10",
  "state": "RUNNING",
  "createdAt": "2026-11-18T09:00:00Z",
  "startedAt": "2026-11-18T09:00:04Z",
  "progress": {"processed": 1500, "total": null},
  "links": {
    "self": "/v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10"
  }
}
~~~

Một job hoàn tất thành công:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "572aa218-a183-4a15-820c-d18a65451a10",
  "state": "SUCCEEDED",
  "progress": {"processed": 2381, "total": 2381},
  "finishedAt": "2026-11-18T09:01:12Z",
  "expiresAt": "2026-11-19T09:01:12Z",
  "result": {
    "contentType": "text/csv",
    "byteSize": 189420,
    "sha256": "8b7f94f9249c1716e1b7967b877d0e558020f96fe5d607bb4beae1475b09a",
    "href": "/v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10/result"
  }
}
~~~

**progress.total=null** có nghĩa tổng số dòng chưa được biết đáng tin, không phải 0. Khi total biết được, phần trăm có thể được tính; không đoán **progress=100%** từ số byte upload trước khi DB commit trạng thái SUCCEEDED. Trạng thái SUCCEEDED chỉ được công bố **sau khi tệp cuối đã tồn tại và metadata tải đã được commit**.

### 2.3. Tải kết quả: 200 với header an toàn

~~~http
GET /v1/report-jobs/572aa218-a183-4a15-820c-d18a65451a10/result HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="orders-report.csv"
Cache-Control: private, no-store
X-Content-Type-Options: nosniff

order_id,created_at,status,total
o-001,2026-11-03T10:01:00Z,PAID,125000
~~~

Ở bài tập, **GET result** được proxy/stream từ private object storage sau khi đã kiểm quyền, không trả nội dung file nhạy cảm trong status JSON. API cần **phát Content-Length khi biết**, hỗ trợ streaming/backpressure để không nạp toàn bộ tệp vào heap; nếu dùng **Range/206 Partial Content**, phải triển khai đúng validators/byte ranges chứ không tự quảng bá hỗ trợ. **CSV phải phòng formula injection** khi người dùng mở bằng spreadsheet: xử lý các trường bắt đầu bằng ký tự công thức theo policy mà không làm mất tính toàn vẹn dữ liệu gốc; mô tả format/escaping chính xác cho client.

### 2.4. Hợp đồng lỗi và retry

| Trường hợp | HTTP | Response/điều client nên làm |
|---|---|---|
| JSON sai schema, from ≥ to, phạm vi quá rộng | **400 Bad Request** | Problem Details với code hợp lệ |
| Không có hoặc sai access token | **401 Unauthorized** | WWW-Authenticate; lấy token đúng issuer/audience |
| Token hợp lệ nhưng thiếu scope | **403 Forbidden** | Không retry cùng token vô hạn |
| Job không tồn tại hoặc thuộc tenant khác | **404 Not Found** theo policy | Không tiết lộ tồn tại job tenant khác |
| Cùng Idempotency-Key, payload khác | **409 Conflict** | Sửa client key; không tạo job mới |
| GET result trước SUCCEEDED | **409 Conflict** | RESULT_NOT_READY; poll status |
| Vượt quota job/RPS đã công bố | **429 Too Many Requests** | Retry-After/backoff có giới hạn |
| Job đã bị dọn theo TTL | **410 Gone** nếu policy cho phép | Tạo job mới nếu còn nhu cầu |
| Worker/dependency tạm hỏng | **503/5xx** khi HTTP không phục vụ được | Không kết luận job đã mất; tra status trước khi POST lại |

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/result-not-ready",
  "title": "Report result is not ready",
  "status": 409,
  "code": "RESULT_NOT_READY",
  "jobId": "572aa218-a183-4a15-820c-d18a65451a10"
}
~~~

Không trả **500** chỉ vì job business FAILED: **GET status vẫn 200** với trạng thái FAILED và mã lỗi an toàn. 500/503 thể hiện **dịch vụ đọc/trả HTTP đang hỏng**. Với job lỗi cuối cùng, trạng thái có thể là FAILED với errorCode như **DATA_SOURCE_UNAVAILABLE** và thông điệp không chứa SQL/stack trace; retry bằng job mới chỉ khi contract cho phép.

## 3. Máy trạng thái: không đoán job đã chạy đến đâu

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED: POST accepted and committed
    QUEUED --> RUNNING: Worker claims lease
    RUNNING --> SUCCEEDED: Object published + DB commit
    RUNNING --> QUEUED: Retryable failure, bounded attempts
    RUNNING --> FAILED: Terminal failure or attempts exhausted
    QUEUED --> CANCELLED: Cancel before claim
    RUNNING --> CANCEL_REQUESTED: Cancel accepted
    CANCEL_REQUESTED --> CANCELLED: Worker stops safely
    SUCCEEDED --> EXPIRED: Result TTL and cleanup
    FAILED --> EXPIRED: Retention policy
    CANCELLED --> EXPIRED: Retention policy
~~~

**Máy trạng thái là hợp đồng công khai**, không chỉ tên enum nội bộ. Đối với version đầu, có thể yêu cầu **QUEUED/RUNNING/SUCCEEDED/FAILED/EXPIRED**; cancellation là mở rộng. Khi cancel và finalize đua nhau, thao tác nào **commit chuyển trạng thái trước** sẽ thắng: nếu finalize đã ghi SUCCEEDED, yêu cầu hủy đến sau không chuyển nó về CANCEL_REQUESTED; nếu cancel đã ghi CANCEL_REQUESTED, finalize chỉ cho phép state RUNNING sẽ bị từ chối. Cần **compare-and-set/fencing** trong DB, không hứa hủy chắc chắn nếu job đã xong.

### 3.1. Invariant của job

| Invariant | Ý nghĩa và cách thực thi |
|---|---|
| **Một job / một logical submit** | Unique theo tenant, actor, idempotency key và fingerprint |
| **Chỉ worker sở hữu lease được finalize** | Lease token/generation + conditional UPDATE |
| **SUCCEEDED có tệp tải được** | Chỉ set SUCCEEDED sau khi storage xác nhận object và hash/metadata khớp |
| **FAILED/CANCELLED không có public result** | GET result trả lỗi phù hợp; object tạm không được công bố |
| **Tiến độ không vượt thực tế** | processed ≥ 0; không phát 100% trước finalize |
| **Mọi read/write đều kiểm tenant** | Không dùng riêng UUID khó đoán như quyền truy cập |
| **Deadline/TTL có nghĩa rõ** | Job execution timeout khác result retention |
| **Không có side effect tài chính** | Retry có thể xử lý lại thao tác đọc/xuất, không charge customer |

**Worker at-least-once** là mặc định thực tế: một job có thể được chạy lại sau crash. **Exactly-once execution** là mục tiêu khó nếu tính cả object storage/network; nên bảo đảm **một kết quả logic được công bố** bằng idempotent output path, fencing và DB state, chấp nhận upload tạm trùng rồi dọn.

### 3.2. Điều kiện chuyển trạng thái và mã lỗi

Nếu input sai **trước khi nhận job**, POST trả 400 và không tạo row. Nếu data source lỗi **sau khi job được nhận**, job chuyển **FAILED** khi hết retry; API status vẫn 200 với error.code đã được allowlist. Không để exception nội bộ biến thành payload có SQL/password:

~~~json
{
  "id": "572aa218-a183-4a15-820c-d18a65451a10",
  "state": "FAILED",
  "error": {
    "code": "REPORT_GENERATION_FAILED",
    "retryable": false,
    "message": "Report generation could not be completed"
  },
  "finishedAt": "2026-11-18T09:04:12Z"
}
~~~

**retryable=false** mô tả **job hiện tại đã kết thúc**, không có nghĩa tạo logical job mới luôn bị cấm. Client cần xem policy. Timeout HTTP khi POST chưa có response thì **retry cùng key**, không coi job mất.

## 4. Mô hình dữ liệu bền vững, idempotency và lease

Chọn PostgreSQL để có transaction, row locks, unique constraints và conditional updates. Đơn giản hóa bằng bảng report_jobs chứa idempotency key; trong hệ thống nhiều operation types có thể tách bảng idempotent_operations. Dữ liệu orders ở schema nghiệp vụ riêng; worker chỉ đọc theo quyền và filter của tenant.

### 4.1. Schema minh họa

~~~sql
CREATE TABLE report_jobs (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    idempotency_key varchar(128) NOT NULL,
    request_hash char(64) NOT NULL,
    request_json jsonb NOT NULL,
    state varchar(24) NOT NULL,
    attempt int NOT NULL DEFAULT 0,
    lease_generation bigint NOT NULL DEFAULT 0,
    lease_owner varchar(96),
    leased_until timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    deadline_at timestamptz NOT NULL,
    processed_rows bigint NOT NULL DEFAULT 0,
    result_object_key varchar(512),
    result_sha256 char(64),
    result_byte_size bigint,
    error_code varchar(64),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    expires_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_report_job_state CHECK (
        state IN ('QUEUED','RUNNING','CANCEL_REQUESTED',
                  'SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
    CONSTRAINT uq_report_idem
        UNIQUE (tenant_id, actor_id, idempotency_key)
);

CREATE INDEX ix_report_jobs_poll
    ON report_jobs(state, next_attempt_at, created_at)
    WHERE state IN ('QUEUED', 'RUNNING');

CREATE INDEX ix_report_jobs_actor
    ON report_jobs(tenant_id, actor_id, created_at DESC);
~~~

Đây là **DDL chạy trong migration**, không chạy ở mỗi request. Cần thêm constraint về state/result tương ứng, retention/audit, tránh để JSON yêu cầu chứa credential. **request_hash** phải là fingerprint của **request chuẩn hóa**, gồm format, thời gian/filter và version hợp đồng; tránh coi khác thứ tự trường JSON là payload khác.

**Không nhầm expires_at với deadline_at:** deadline giới hạn xử lý; expires_at quy định thời điểm kết quả không còn tải được. Metadata có thể giữ thêm để audit, nhưng không trả object key khi tệp đã xóa.

### 4.2. Chấp nhận job: commit rồi mới trả 202

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API client
    participant A as Spring REST API
    participant D as PostgreSQL
    participant W as Worker
    C->>A: POST /v1/report-jobs + Idempotency-Key
    A->>A: JWT/scope/tenant, validate, fingerprint
    A->>D: BEGIN; INSERT job QUEUED (unique key)
    A->>D: COMMIT
    D-->>A: Commit acknowledged
    A-->>C: 202 + Location /v1/report-jobs/{id}
    W->>D: Claim durable QUEUED job
    D-->>W: Lease generation, job filter
    Note over C,W: 202 không hứa worker đã bắt đầu
~~~

Các bước server:

1. Xác thực token và kiểm **reports:export**; lấy tenantId/actorId từ principal đã kiểm chứng.
2. Validate filter, định dạng, khoảng thời gian, quota và fingerprint. Không chấp nhận tenantId từ body làm quyền truy cập.
3. Trong transaction, **tạo job QUEUED** có unique key và lưu payload canonical.
4. Nếu key tồn tại, đọc row đã commit bằng transaction riêng, so fingerprint: **cùng payload → job cũ**, **khác payload → 409**; không tạo job thứ hai.
5. Dựng 202 **sau khi transaction commit được xác nhận**. Nếu HTTP mất sau commit, client retry **cùng key** và nhận cùng ID.

**Race:** SELECT trước rồi INSERT không chống hai request đồng thời; unique constraint là rào chắn cuối cùng. Nếu INSERT thua unique ở commit, kết thúc transaction lỗi rồi tra record đã commit bằng transaction đọc mới. Nếu COMMIT không xác định vì đứt kết nối DB, phải đối soát theo idempotency key thay vì khẳng định job chưa tạo.

### 4.3. Quota đồng thời không thể đếm ngoài transaction

Cách sai: SELECT count theo tenant thấy 2, hai request cùng insert, tổng thành 4 dù max=3. Cần **atomic reservation**: lock hàng tenant_report_budget và cập nhật counter khi nhận/release job trong cùng transaction, hoặc thiết kế constraint/serialization tương đương. Worker crash và retry cần đối soát **không decrement hai lần**. **Idempotency replay** không giữ slot quota mới.

**429** mô tả rate/quota theo chính sách; khi DB lỗi không xác định quota, đừng trả 429 như thể caller lạm dụng. Có thể trả 503 và không commit nhận job khi không reserve được capacity.

### 4.4. Claim job an toàn khi nhiều worker

~~~sql
-- PostgreSQL, thực thi trong một transaction ngắn.
WITH candidate AS (
  SELECT id
    FROM report_jobs
   WHERE state = 'QUEUED'
     AND next_attempt_at <= now()
     AND deadline_at > now()
   ORDER BY next_attempt_at, created_at, id
   LIMIT 1
   FOR UPDATE SKIP LOCKED
)
UPDATE report_jobs j
   SET state = 'RUNNING',
       attempt = j.attempt + 1,
       lease_generation = j.lease_generation + 1,
       lease_owner = :worker_id,
       leased_until = now() + interval '30 seconds',
       started_at = COALESCE(j.started_at, now()),
       version = j.version + 1
  FROM candidate
 WHERE j.id = candidate.id
RETURNING j.*;
~~~

**FOR UPDATE SKIP LOCKED** giúp worker cạnh tranh không claim cùng row đã khóa. Transaction claim phải **COMMIT ngay**, không giữ DB transaction xuyên việc xuất CSV/upload. **lease_generation** là fencing token tăng qua mỗi lần claim: worker cũ không được finalize sau khi lease đã trao cho worker mới.

Worker chỉ update progress/heartbeat/finalize khi **id, lease_owner, lease_generation, state** khớp. Sweeper chuyển **RUNNING có lease hết hạn** về QUEUED nếu còn deadline/attempt budget, hoặc FAILED khi vượt giới hạn. Heartbeat không được gia hạn vượt deadline tuyệt đối.

### 4.5. Heartbeat và finalize có fencing

~~~sql
-- Gia hạn lease khi worker vẫn sở hữu thế hệ hiện tại.
UPDATE report_jobs
   SET leased_until = LEAST(
         now() + interval '30 seconds', deadline_at),
       processed_rows = GREATEST(processed_rows, :processed_rows),
       version = version + 1
 WHERE id = :job_id
   AND state = 'RUNNING'
   AND lease_owner = :worker_id
   AND lease_generation = :generation
   AND leased_until > now()
   AND deadline_at > now();
-- affected_rows=0: dừng xử lý, không công bố result.

-- Chỉ sau khi object upload đã hoàn tất và checksum được kiểm tra:
UPDATE report_jobs
   SET state = 'SUCCEEDED',
       result_object_key = :key,
       result_sha256 = :sha256,
       result_byte_size = :size_bytes,
       finished_at = now(),
       expires_at = now() + interval '24 hours',
       lease_owner = NULL,
       leased_until = NULL,
       version = version + 1
 WHERE id = :job_id
   AND state = 'RUNNING'
   AND lease_owner = :worker_id
   AND lease_generation = :generation
   AND leased_until > now()
   AND deadline_at > now();
-- affected_rows=0: worker đã mất lease, không được finalize.
~~~

**Cửa sổ lỗi:** storage PUT thành công nhưng DB finalize thất bại. Khi retry, worker có thể upload lại tệp tạm và chỉ một bản được **DB tham chiếu sau finalize**. Dùng object key gắn **job ID + generation + attempt** để worker cũ không ghi đè bản mới; dọn orphan objects định kỳ. Không giả vờ blob store và DB có chung ACID transaction.

## 5. Thực hành Java/Spring: controller mỏng, service có ranh giới commit

Thiết kế ba lớp: **controller** nhận HTTP và principal; **application service** kiểm quyền/quota, tạo/đọc job trong transaction; **worker** xử lý ngoài HTTP request. Các đoạn Java dưới đây giả định Java 17+, Spring Boot 3 và Spring Security OAuth2 Resource Server; chúng dùng interface cho những thành phần cần tích hợp, không phải project độc lập.

### 5.1. DTO và chủ thể xác thực

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.List;
import jakarta.validation.constraints.NotNull;

record CreateReportJob(
        @NotNull String format,
        @NotNull Instant from,
        @NotNull Instant to,
        String status) {}

record AuthenticatedActor(UUID tenantId, UUID userId) {}
record Progress(long processed, Long total) {}
record ResultLink(String contentType, long byteSize,
                  String sha256, String href) {}
record JobView(UUID id, String state, Instant createdAt,
               Instant startedAt, Instant finishedAt,
               Instant expiresAt, Progress progress,
               ResultLink result, String errorCode) {}

interface ActorResolver {
    AuthenticatedActor fromValidatedJwt(
            org.springframework.security.oauth2.jwt.Jwt jwt);
}
~~~

**Không lấy tenant ID từ body.** Scope reports:export là điều kiện cần, không có nghĩa được xuất dữ liệu tenant khác. Nếu hệ thống có service principal không đại diện userId, mô hình actor phải bổ sung type/delegation thay vì ép client ID thành user ID.

### 5.2. Controller: 202 sau service commit, status là nguồn sự thật

~~~java
import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

interface ReportJobUseCases {
    // Implementation: atomic insert/replay, tenant quota and DB commit.
    JobView submit(AuthenticatedActor actor, String idem,
                   CreateReportJob request);
    JobView getVisible(AuthenticatedActor actor, UUID id);
    void requestCancellation(AuthenticatedActor actor, UUID id);
}

@RestController
@RequestMapping("/v1/report-jobs")
class ReportJobController {
    private final ReportJobUseCases jobs;
    private final ActorResolver actors;

    ReportJobController(ReportJobUseCases jobs, ActorResolver actors) {
        this.jobs = jobs;
        this.actors = actors;
    }

    @PostMapping
    ResponseEntity<JobView> submit(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateReportJob input) {
        AuthenticatedActor actor = actors.fromValidatedJwt(jwt);
        JobView job = jobs.submit(actor, key, input);
        return ResponseEntity.accepted()
                .location(URI.create("/v1/report-jobs/" + job.id()))
                .header("Retry-After", "3")
                .cacheControl(CacheControl.noStore())
                .body(job);
    }

    @GetMapping("/{id}")
    ResponseEntity<JobView> status(
            @AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        JobView job = jobs.getVisible(
                actors.fromValidatedJwt(jwt), id);
        var response = ResponseEntity.ok()
                .cacheControl(CacheControl.noStore());
        if ("QUEUED".equals(job.state())
                || "RUNNING".equals(job.state())) {
            response.header("Retry-After", "5");
        }
        return response.body(job);
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> cancel(
            @AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        jobs.requestCancellation(
                actors.fromValidatedJwt(jwt), id);
        return ResponseEntity.accepted()
                .location(URI.create("/v1/report-jobs/" + id))
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
~~~

**DELETE là phần mở rộng:** khi cancel RUNNING, service chỉ nhận yêu cầu hủy và worker phải hợp tác xử lý; 202 không có nghĩa đã dừng. Nếu không triển khai cancel, bỏ method và cập nhật OpenAPI. Controller **không tạo new Thread hoặc CompletableFuture trong request để thay bền vững**, và không trả 202 trước khi service transaction COMMIT. Cần exception handler RFC 9457 cùng input validation và idempotency key format checks.

### 5.3. Service ranh giới giao dịch và replay

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

interface DurableJobRepository {
    // Atomic insert-or-replay; handle unique constraint races.
    // Reserve quota only for a NEW job within same DB transaction.
    JobView createOrReplay(
            AuthenticatedActor actor, String key, String fingerprint,
            CreateReportJob request, java.time.Instant deadline);
    JobView getAuthorized(AuthenticatedActor actor, UUID jobId);
    void requestCancelAuthorized(AuthenticatedActor actor, UUID jobId);
}
interface RequestFingerprinter {
    String canonicalSha256(CreateReportJob input);
}
class InvalidReportRequest extends RuntimeException {}

@Service
class ReportJobApplicationService implements ReportJobUseCases {
    private final DurableJobRepository repository;
    private final RequestFingerprinter fingerprints;
    private final Clock clock;

    ReportJobApplicationService(DurableJobRepository repository,
             RequestFingerprinter fingerprints, Clock clock) {
        this.repository = repository;
        this.fingerprints = fingerprints;
        this.clock = clock;
    }

    @Override
    @Transactional
    public JobView submit(AuthenticatedActor actor, String key,
                          CreateReportJob input) {
        if (key == null || key.length() < 8 || key.length() > 128) {
            throw new InvalidReportRequest();
        }
        if (!"CSV".equals(input.format())
                || input.from() == null || input.to() == null
                || !input.from().isBefore(input.to())
                || input.to().isAfter(
                     input.from().plus(Duration.ofDays(31)))) {
            throw new InvalidReportRequest();
        }
        String hash = fingerprints.canonicalSha256(input);
        return repository.createOrReplay(
            actor, key, hash, input,
            clock.instant().plus(Duration.ofMinutes(15)));
    }

    @Override
    @Transactional(readOnly = true)
    public JobView getVisible(AuthenticatedActor actor, UUID id) {
        return repository.getAuthorized(actor, id);
    }

    @Override
    @Transactional
    public void requestCancellation(AuthenticatedActor actor, UUID id) {
        repository.requestCancelAuthorized(actor, id);
    }
}
~~~

**Chú ý:** implementation createOrReplay phải so fingerprint **trước khi reserve quota**; reserve và INSERT của job mới cùng transaction. Nếu quota bị reserve trước khi replay, người dùng gửi lại POST sẽ bị trừ hai lần. Nếu unique violation ở COMMIT, không đọc tiếp trong transaction đã rollback-only; kết thúc rồi tra lại theo key ở transaction mới. Fingerprint cần canonical JSON, filter đã chuẩn hóa và version hợp đồng.

### 5.4. Download: tách authorization khỏi truyền bytes

~~~java
import java.io.InputStream;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

record DownloadInfo(String privateObjectKey, String sha256, long size) {}
interface DownloadAuthorization {
    // Verify tenant/owner, SUCCEEDED and not expired before returning key.
    DownloadInfo resolve(AuthenticatedActor actor, UUID jobId);
}
interface PrivateObjectStore {
    InputStream openVerified(String privateObjectKey);
}

@RestController
@RequestMapping("/v1/report-jobs")
class ReportDownloadController {
    private final DownloadAuthorization downloads;
    private final PrivateObjectStore objects;
    private final ActorResolver actors;

    ReportDownloadController(DownloadAuthorization downloads,
                             PrivateObjectStore objects,
                             ActorResolver actors) {
        this.downloads = downloads;
        this.objects = objects;
        this.actors = actors;
    }

    @GetMapping("/{id}/result")
    ResponseEntity<StreamingResponseBody> download(
            @AuthenticationPrincipal Jwt jwt, @PathVariable UUID id) {
        DownloadInfo info = downloads.resolve(
                actors.fromValidatedJwt(jwt), id);
        StreamingResponseBody stream = output -> {
            try (InputStream input = objects.openVerified(
                    info.privateObjectKey())) {
                input.transferTo(output);
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .contentLength(info.size())
                .header("Content-Disposition",
                        "attachment; filename=\"orders-report.csv\"")
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(stream);
    }
}
~~~

**Rủi ro tải tệp:** nếu storage lỗi khi stream bắt đầu, headers/status có thể đã gửi và server không thể đổi 200 sang 503; client nhận dữ liệu dở. Cần kiểm tra object/metadata trước khi trả response, phát checksum/Content-Length đúng, quan sát streaming errors, giới hạn số download song song và cấu hình bounded async executor. Một GET tải lại là an toàn nếu result immutable và chưa hết TTL.

**Signed URL** (nếu dùng thay stream) phải có TTL ngắn, giới hạn object/method; không public bucket ACL. URL ký sẵn cũng là bearer credential, có thể lộ qua log/history/referrer; chỉ cấp sau khi kiểm tenant/owner và ghi nhận hạn chế về thu hồi, CDN caching, download audit.

## 6. Worker thực thi, giới hạn tài nguyên và phục hồi

Worker không chạy trực tiếp trong HTTP controller. Có thể dùng **Spring @Scheduled**, một consumer message broker, hoặc job worker framework. Với bài học này dùng PostgreSQL queue có lease; mỗi worker nhận tối đa một số job đồng thời đã cấu hình, không tạo thread vô hạn. Claim và finalize là **các transaction ngắn**, còn việc tạo tệp nằm ngoài transaction.

### 6.1. Bộ điều phối worker có thể dừng/khôi phục

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record ClaimedJob(UUID id, long generation,
                  AuthenticatedActor actor, CreateReportJob request) {}

interface JobLeaseManager {
    // @Transactional: SKIP LOCKED claim and COMMIT before returning.
    Optional<ClaimedJob> claimNext(String workerId);
    // @Transactional: progress/heartbeat only for current generation.
    boolean heartbeat(ClaimedJob job, String workerId, long processed);
    // @Transactional: mark result only if current lease/fence is valid.
    boolean finalizeSuccess(
            ClaimedJob job, String workerId, StoredResult result);
    // @Transactional: retry or terminal FAILED according to policy.
    void recordFailure(
            ClaimedJob job, String workerId, String safeErrorCode);
}
record StoredResult(String objectKey, String sha256, long byteSize) {}
interface ReportGenerator {
    // May upload a private staging object. No DB transaction is kept open.
    StoredResult generate(ClaimedJob job,
                          ProgressReporter progress) throws Exception;
}
interface ProgressReporter {
    void report(long rowsProcessed);
}

@Component
class ReportWorker {
    private final JobLeaseManager leases;
    private final ReportGenerator generator;
    private final String workerId = UUID.randomUUID().toString();

    ReportWorker(JobLeaseManager leases, ReportGenerator generator) {
        this.leases = leases;
        this.generator = generator;
    }

    @Scheduled(fixedDelayString = "2000")
    public void runOne() {
        var maybe = leases.claimNext(workerId);
        if (maybe.isEmpty()) return;
        ClaimedJob job = maybe.get();
        try {
            StoredResult file = generator.generate(job,
                count -> {
                    if (!leases.heartbeat(job, workerId, count)) {
                        throw new LostJobLease();
                    }
                });
            if (!leases.finalizeSuccess(job, workerId, file)) {
                throw new LostJobLease();
            }
        } catch (LostJobLease lost) {
            // Stop; another worker may own the job. Sweep temp objects.
        } catch (Exception error) {
            leases.recordFailure(
                job, workerId, "REPORT_GENERATION_FAILED");
        }
    }
}
class LostJobLease extends RuntimeException {}
~~~

Đây là **bộ khung**, không phải đầy đủ implementation: cần bật scheduling, định nghĩa schema/repository, storage adapter, logger/metrics, bounded executor và **heartbeat định kỳ độc lập với số dòng**. Nếu datasource bị treo 45 giây giữa hai lần gọi report(), lease 30 giây có thể hết dù worker chưa lỗi; production phải có watchdog/heartbeat với deadline và kiểm tra cancellation giữa các batch.

**@Scheduled fixedDelay ở ví dụ chỉ có một tác vụ mỗi lần gọi** khi dùng scheduler mặc định; scale-out bằng nhiều worker replicas hoặc cấu hình concurrency có giới hạn. Không xử lý 100.000 bản ghi trong một DB transaction lock row job; claim → COMMIT → xử lý → finalize. RecordFailure cũng phải kiểm lease token và không làm worker cũ chuyển một job đã SUCCEEDED sang FAILED.

### 6.2. Giới hạn thời gian, retry và cancellation

- **Retryable errors:** timeout khi đọc orders, storage tạm không phản hồi, lỗi kết nối ngắn; delay theo exponential backoff có jitter, giới hạn attempts và deadline. Không retry liên tục một tệp 50 MiB khiến storage nghẽn.
- **Terminal errors:** input không còn phù hợp business rules, vượt row/file limits, dữ liệu không được phép xuất; ghi error code an toàn và FAILED nếu policy không cho chạy lại.
- **Deadline:** khi now vượt deadline_at, sweeper kết thúc job theo policy **FAILED** với code TIMEOUT; worker mất lease không được finalize dù upload vừa thành công.
- **Cancellation:** thao tác DELETE chỉ ghi **CANCEL_REQUESTED** nếu RUNNING; worker kiểm token/cancel flag giữa các batch. Nếu CANCEL_REQUESTED thắng trước finalize, worker phải dừng và dọn tệp tạm; nếu finalize thắng trước, DELETE không thể khẳng định “đã hủy”.
- **Quota:** slot QUEUED/RUNNING phải được release đúng một lần bằng transaction khi job rời state active; không decrement hai lần ở race giữa sweeper và worker.

Nếu dùng broker thay DB polling, ghi **job + outbox event** trong một DB transaction; dispatcher publish có retry; consumer idempotent dựa trên **job ID/lease generation**. Không ghi job vào DB rồi gửi message một cách không nguyên tử mà vẫn hứa không bao giờ mất event.

### 6.3. Mốc nhất quán của dữ liệu được xuất

**Một chuỗi SELECT phân trang trên dữ liệu live có thể lặp/bỏ sót hàng** khi order được thêm/xóa/đổi sort/filter trong quá trình xuất. Với báo cáo cần tái lập, chọn mốc:

1. **As-of worker materialization**: worker tạo một **snapshot các row/giá trị** ở thời điểm bắt đầu xuất, sau đó tuần tự tạo CSV từ snapshot này; đây là chính sách bài tập đề xuất.
2. **As-of request acceptance**: mạnh hơn; nếu nghiệp vụ yêu cầu chính xác dữ liệu tại lúc POST được nhận, phải có temporal/versioned data hoặc snapshot được ghi trong transaction tiếp nhận, không chỉ ghi thời gian from/to.

Một cách materialize bounded dataset dưới PostgreSQL là thực hiện **INSERT ... SELECT** trong một statement/transaction, sao chép các trường cần export vào bảng staging theo job:

~~~sql
CREATE TABLE report_snapshot_rows (
    job_id uuid NOT NULL,
    row_number bigint NOT NULL,
    order_id uuid NOT NULL,
    exported_record jsonb NOT NULL,
    PRIMARY KEY (job_id, row_number)
);

-- Chạy ở transaction riêng khi worker materialize.
-- Câu INSERT...SELECT nhìn một statement snapshot nhất quán.
INSERT INTO report_snapshot_rows
       (job_id, row_number, order_id, exported_record)
SELECT :job_id,
       row_number() OVER (ORDER BY o.created_at, o.id),
       o.id,
       jsonb_build_object(
           'id', o.id, 'createdAt', o.created_at,
           'status', o.status, 'total', o.total)
  FROM orders o
 WHERE o.tenant_id = :tenant_id
   AND o.owner_id = :actor_id
   AND o.created_at >= :from_time
   AND o.created_at < :to_time
   AND (:status IS NULL OR o.status = :status);
~~~

Đây là **định hướng**: production cần phân vùng/cleanup snapshot rows, enforce row limit **trước hoặc trong quá trình materialize** và kiểm soát chi phí transaction, storage, index. **Sao chép exported_record** cố định cả membership và các giá trị tại snapshot; nếu chỉ lưu order IDs rồi đọc lại từ orders, row bị xóa/đổi status sẽ làm kết quả không còn snapshot. Với dữ liệu nhiều triệu hàng, thiết kế **versioned/as-of data source** hoặc export engine hỗ trợ snapshot phù hợp thay cho transaction lớn.

**Read consistency quan trọng:** nếu chụp từ read replica đang lag thì snapshot phản ánh trạng thái của replica, không nhất thiết dữ liệu vừa commit trên primary. Công bố nguồn và freshness policy. Với CSV tăng dần, không ghi một file đang upload dở vào public result; object chỉ được công bố sau finalize.

### 6.4. Tạo CSV mà không gây OOM hoặc formula injection

CSV cần ghi header/row bằng UTF-8 stream; escape dấu phẩy, CR, LF và dấu nháy kép theo CSV convention. Nếu giá trị được mở bằng Excel/Sheets, các cell bắt đầu bằng **=, +, -, @, tab hoặc ký tự điều khiển** có thể bị diễn giải thành công thức sau khi import. Chọn policy: prefix escape cho field không tin cậy khi dành cho spreadsheet, hoặc cung cấp file dữ liệu máy đọc được kèm cảnh báo; **biến đổi để an toàn có thể thay nghĩa dữ liệu gốc**, vì vậy phải công bố và kiểm thử.

Giới hạn **max rows, max output bytes, execution deadline và streaming batch size**; nếu vượt giới hạn, chuyển FAILED với code REPORT_TOO_LARGE, không trả CSV đã cắt mà gắn SUCCEEDED. Hash SHA-256 và byteSize phải được tính trên **bytes cuối cùng** sau khi encode. Tệp nên có Content-Disposition filename đã cố định/escape an toàn, không lấy raw tên người dùng để tránh response splitting hoặc path traversal.

### 6.5. Dọn TTL, tránh xóa trước khi hết hạn

Sweeper quét SUCCEEDED có **expires_at ≤ now()**, đánh dấu EXPIRED bằng update có điều kiện, sau đó xóa object được tham chiếu theo cơ chế retry idempotent. Nếu xóa object trước khi thay state và worker khác đang phục vụ GET, client có thể thấy 200 nhưng file mất. Cần policy nhất quán cho **download đang hoạt động**: giới hạn TTL, ngăn bắt đầu download mới khi hết hạn; một lần download đã bắt đầu trước expiry có thể được hoàn tất theo lựa chọn hệ thống. Với object storage có lifecycle tự động, bảo đảm TTL thực tế không **ngắn hơn** thời hạn mà API đã công bố.

Không lưu signed URL dài hạn trong DB, không làm cache public kết quả riêng tư. Metadata audit có thể giữ lâu hơn file theo retention/compliance; trạng thái hết hạn và response **410** không được tiết lộ tên/tenant khác khi caller không có quyền.

## 7. Bảo mật, quota và observability xuyên vòng đời job

**Không có “quyền một lần” chỉ vì client đã được phép tạo job.** Mọi GET status, GET result và DELETE cancellation cần xác thực lại và kiểm **tenant/owner/role** hiện thời. Nếu quyền export bị thu hồi sau khi job đã tạo, chính sách hợp lý là chặn tải (hoặc hủy job) theo yêu cầu compliance, không coi URI/jobId là bearer token.

### 7.1. Route và domain authorization

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportApiSecurity {
    @Bean
    SecurityFilterChain reportApi(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/v1/report-jobs")
                .hasAuthority("SCOPE_reports:export")
            .requestMatchers(HttpMethod.GET, "/v1/report-jobs/**")
                .hasAuthority("SCOPE_reports:read")
            .requestMatchers(HttpMethod.DELETE, "/v1/report-jobs/*")
                .hasAuthority("SCOPE_reports:export")
            .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .sessionManagement(s -> s.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(c -> c.disable())
            .build();
    }
}
~~~

Trong ví dụ, POST cần **reports:export**, còn status/download cần **reports:read**. Vì vậy test principal phải có **cả hai** nếu muốn hoàn thành toàn bộ quickstart; docs/issuer cần hỗ trợ cấp scopes này. Việc tắt CSRF chỉ phù hợp **bearer-only API không xác thực write bằng cookie**. Nếu BFF/session cookie được dùng, giữ CSRF protection. JWT resource server phải validate **signature, issuer, audience, exp/nbf, scopes và accepted algorithms**; security filter không thay truy vấn job có điều kiện tenant/owner. Lỗi authentication dùng **401 + WWW-Authenticate**, thiếu scope dùng 403, job không nhìn thấy có thể dùng 404.

**Giới hạn tài nguyên:** gateway rate limit theo verified principal, service giữ quota per-tenant có transaction, worker giới hạn concurrency, result download có bandwidth/egress limits. Một request idempotency replay không làm tăng slot quota. Không cho caller nhập object key hoặc đường dẫn lưu file để tránh **path traversal/SSRF**.

### 7.2. Metrics và trace ID giúp debug

| Metric hoặc log event | Ý nghĩa |
|---|---|
| **report_jobs_submitted_total** | Logical job được commit, không phải số lần HTTP POST |
| **report_jobs_in_state{state}** | Số job theo trạng thái có cardinality hữu hạn |
| **report_job_execution_seconds** | Histogram thời gian chạy thành công/thất bại |
| **report_job_retries_total{reason}** | Attempt phải retry; reason dùng allowlist |
| **report_jobs_lease_expired_total** | Worker chết/chậm heartbeat hoặc mất quyền sở hữu |
| **report_result_bytes_total** | Tổng byte được xuất/tải, phục vụ capacity plan |
| **report_expired_objects_pending** | Độ trễ cleanup sau TTL |

Log nên có **traceId, requestId, jobId (hạn chế truy cập), generation, safe error code**, deadline và trạng thái chuyển tiếp. **Không gắn jobId, tenantId, userId, idempotency key, CSV row hoặc object key** làm metric labels; tránh cardinality cao và rò dữ liệu. Với job xử lý ngoài HTTP context, worker phải liên kết bằng **jobId/operationId được lưu** hoặc trace link mới, không giả định trace span từ request POST sống suốt 15 phút.

Alert hữu ích: số RUNNING có lease hết hạn tăng, hàng QUEUED chờ quá SLA, ratio FAILED tăng, storage 5xx kéo dài hoặc cleanup lag lớn. Runbook: đối chiếu DB state/generation, queue age, object manifest; **không đánh dấu SUCCEEDED bằng tay** nếu chưa xác minh file, hash và quyền tải.

## 8. OpenAPI trích đoạn và quickstart kiểm thử hợp đồng

Một mô tả OpenAPI cần ghi rõ **202 chỉ tiếp nhận**, status/result URLs, scopes, header idempotency, errors, caching và TTL. Ví dụ rút gọn, dùng URL **example.test chỉ để minh họa**, chưa phải spec đủ schema cho production:

~~~yaml
openapi: 3.1.0
info:
  title: Report Jobs API
  version: 1.0.0
servers:
  - url: https://api.example.test
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateReportJob:
      type: object
      required: [format, from, to]
      additionalProperties: false
      properties:
        format: { type: string, enum: [CSV] }
        from: { type: string, format: date-time }
        to: { type: string, format: date-time }
        status: { type: string }
    JobState:
      type: string
      enum: [QUEUED, RUNNING, CANCEL_REQUESTED,
             SUCCEEDED, FAILED, CANCELLED, EXPIRED]
paths:
  /v1/report-jobs:
    post:
      operationId: submitReportJob
      security:
        - bearerAuth: []
      summary: Accept a durable asynchronous report job
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema: { type: string, minLength: 8, maxLength: 128 }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateReportJob'
      responses:
        '202':
          description: Job accepted, processing not yet complete
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
            Retry-After:
              schema: { type: string }
        '400': { description: Invalid request }
        '401': { description: Missing or invalid token }
        '403': { description: Insufficient permission }
        '409': { description: Idempotency key conflict }
        '429': { description: Tenant quota reached }
  /v1/report-jobs/{id}:
    get:
      operationId: getReportJob
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200': { description: Current job state }
        '401': { description: Missing or invalid token }
        '403': { description: Insufficient permission }
        '404': { description: Job not visible }
        '410': { description: Job retention expired }
  /v1/report-jobs/{id}/result:
    get:
      operationId: downloadReport
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200':
          description: Download completed CSV report
          content:
            text/csv:
              schema: { type: string, format: binary }
        '409': { description: Result not yet ready }
        '410': { description: Result expired }
~~~

**Lỗ hổng cố ý cần bổ sung khi nộp bài:** với HTTP Bearer scheme thuần, security requirement **không biểu diễn OAuth2 scopes** trong OpenAPI. Khi publish, dùng **OAuth2/OIDC securitySchemes** và khai báo **reports:export/reports:read** theo từng operation nếu cần machine-readable scopes; hoặc mô tả quyền trong prose khi scheme không hỗ trợ scope. Bổ sung **JobView/result schema, Problem Details, Content-Disposition, Cache-Control, 401 challenge, DELETE cancellation, request limits** và errors đầy đủ trước khi coi spec hoàn chỉnh.

### 8.1. Quickstart bằng HTTP

1. Lấy **access token có đúng issuer/audience và reports:export + reports:read**, không dùng ID token hoặc token môi trường khác.
2. Gửi POST có **Idempotency-Key** ổn định; kiểm tra **202, Location và body QUEUED**.
3. GET đúng Location theo **Retry-After và exponential backoff với jitter**, có deadline phía client. Trong khi QUEUED/RUNNING, không tạo POST mới.
4. Khi SUCCEEDED, GET result.href để nhận **text/csv**, xác minh byte size/checksum nếu được công bố. Khi FAILED, hiển thị safe error code; nếu EXPIRED, yêu cầu tạo job mới.
5. Sau timeout khi POST hoặc GET result, **không phỏng đoán kết quả**; retry cùng key hoặc đọc status theo operation ID đã biết.

Đừng **poll 10 lần/giây** vì một client có thể tạo ra hàng trăm request trong vài phút. API nên rate-limit GET status khi cần và tài liệu hóa Retry-After; client phải dừng khi deadline hết, bị 401/403/404 không recoverable hoặc job terminal, không polling vô hạn.

## 9. Kiểm thử: những lỗi bắt buộc phải tái hiện

Không đủ nếu unit test chỉ chứng minh DTO được serialize. Cần **HTTP contract tests**, **integration tests với PostgreSQL thật hoặc Testcontainers**, worker/storage fake, và **fault injection tại các mốc transaction/upload**. Không chạy Gradle/Java trong bước biên soạn tài liệu này; các test là yêu cầu người học thực hiện trong project của họ.

### 9.1. Ma trận test end-to-end

| Case | Setup/action | Assertion cần có |
|---|---|---|
| **1. Happy path** | POST hợp lệ → worker chạy → GET status → GET result | 202, 200 state SUCCEEDED, 200 CSV có đúng row và checksum |
| **2. Replay** | POST cùng actor/key/payload hai lần | Cùng job ID; 1 row job, chỉ reserve quota một lần |
| **3. Key conflict** | Cùng key nhưng khác date/status/format | 409; không sửa job gốc |
| **4. Parallel submit** | Hai POST cùng key chạy đồng thời | Unique constraint chỉ cho một logical job |
| **5. Worker race** | Hai worker claim một QUEUED job | Chỉ một claim thành công; generation tăng đúng |
| **6. Crash sau claim** | Worker tắt khi RUNNING | Sau lease expiry job được reclaim nếu còn deadline |
| **7. Crash sau upload** | Tệp được PUT, fail trước finalize | Không có SUCCEEDED giả; retry publish bản hợp lệ, orphan được dọn |
| **8. Stale worker** | Lease generation=1 hết, generation=2 được claim | Gen=1 không heartbeat/finalize được |
| **9. Hết attempts/deadline** | Repeated transient failures | Job FAILED có error code an toàn, không treo RUNNING |
| **10. Polling** | GET khi QUEUED/RUNNING/SUCCEEDED | 200 states, Retry-After khi thích hợp, result link chỉ khi ready |
| **11. Download chưa sẵn** | GET /result khi QUEUED | 409 RESULT_NOT_READY, không có CSV partial |
| **12. Cross-tenant** | JWT tenant B dùng ID tenant A | 404/403 theo policy, không lộ object key hay metadata A |
| **13. Scope/credential** | Thiếu token, sai aud, thiếu reports:read | 401/403, backend vẫn kiểm tenant/owner |
| **14. TTL** | Fake clock vượt expiresAt, sweeper chạy | GET result 410 theo policy, object bị xóa an toàn |
| **15. Cancellation race** | DELETE khi worker gần finalize | Một terminal state hợp lệ, không công bố file bị hủy |
| **16. Report consistency** | Ghi thêm/xóa orders khi worker export | CSV khớp snapshot policy, không lặp/thiếu row |
| **17. CSV an toàn** | Text có comma/newline/quotes/formula-like prefix | CSV escaping đúng và policy spreadsheet injection được áp dụng |
| **18. Limits** | >100k rows, >50MiB, >3 active jobs | FAILED/429 đúng contract, không OOM và không leak slot |

**Các bước test phải quan sát trạng thái DB và object storage**, không chỉ mock rằng service trả SUCCEEDED. Khi một lỗi được tạo sau DB commit nhưng trước HTTP response, client thấy timeout vẫn phải có thể **retry cùng key** để tìm job cũ. Với concurrency, dùng **barrier/transaction độc lập**, không dùng Thread.sleep để đoán khi nào đã commit.

### 9.2. Test HTTP với MockMvc

Test skeleton dưới đây giả định project đã cấu hình JWT mock principal, job repository thực/fixture và một test database. Với Spring Security test hỗ trợ postprocessor jwt(), cần xây principal phù hợp ActorResolver:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportJobContractIT {
    @Autowired MockMvc mvc;

    @Test
    void postReturnsDurableJobUri() throws Exception {
        UUID tenant = UUID.randomUUID();
        UUID user = UUID.randomUUID();
        String json = """
            {"format":"CSV","from":"2026-11-01T00:00:00Z",
             "to":"2026-11-15T00:00:00Z","status":"PAID"}
            """;
        var result = mvc.perform(post("/v1/report-jobs")
            .with(jwt().jwt(t -> t.subject(user.toString())
                .claim("tenant_id", tenant.toString()))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports:export")))
            .header("Idempotency-Key",
                    "625af9f7-9c0f-4cab-91b1-7e9f523f5631")
            .contentType(MediaType.APPLICATION_JSON)
            .content(json))
            .andExpect(status().isAccepted())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.state").value("QUEUED"))
            .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertNotNull(location);
        // Đọc bằng token có reports:read, không ngầm dùng write scope.
        mvc.perform(get(location).with(jwt()
            .jwt(t -> t.subject(user.toString())
                .claim("tenant_id", tenant.toString()))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_reports:read"))))
            .andExpect(status().isOk());
    }
}
~~~

Đây là **test skeleton**: repository, JWT actor mapping, transaction manager, DB migration/fixture và job runner cần được dựng trong project thật. **Không đặt @Transactional trên toàn test** rồi kết luận job đã commit từ cùng connection; phải đọc bằng transaction khác sau khi nhận 202. **Mock JWT không xác minh chữ ký/issuer/audience thật**; cần test resource server riêng với token có chữ ký sai, issuer sandbox ở production, token hết hạn hoặc aud khác.

### 9.3. Fault-injection sequence giúp tái lập

~~~text
CASE: Crash after upload
  1. Seed order source snapshot; create job, assert 202.
  2. Worker #1 claims generation=1.
  3. Worker #1 uploads file to private staging object.
  4. Inject DB finalize failure / terminate worker.
  5. Assert job != SUCCEEDED; GET result != 200.
  6. Expire lease under controlled test clock.
  7. Worker #2 claims generation=2, reruns or reuses safe snapshot.
  8. Worker #1 tries finalize -> affected_rows=0.
  9. Worker #2 finalizes; GET result=200, checksum valid.
 10. Sweeper removes orphan from generation=1.

CASE: Retry POST after lost response
  1. POST commits job, proxy drops HTTP response.
  2. Client retries same Idempotency-Key and canonical payload.
  3. Assert same jobId, one quota slot, no duplicate row.
~~~

Đối với report snapshot, nếu retry tạo **snapshot mới theo thời điểm thực thi khác**, nội dung CSV có thể khác giữa attempts. Phải giữ/cố định **snapshot ID + dữ liệu/version** khi đã materialize thành công; hoặc công bố rõ contract chỉ bảo đảm **một bản final consistent ở attempt thành công**. Không nói kết quả “as-of POST request” nếu không có nguồn versioned data đáp ứng được.

## 10. Runbook, theo dõi và khả năng triển khai

Khi số job QUEUED tăng hoặc người dùng nói “job stuck”, không thay đổi trạng thái thủ công trước khi có bằng chứng:

1. **Tìm job trong phạm vi được phép:** trạng thái, attempt, lease_generation, deadline, last heartbeat, processed_rows; không gửi raw CSV/credential lên kênh support.
2. **Phân biệt nguyên nhân:** no workers, DB pool cạn, job vượt quota, source read chậm, object storage 5xx, orphan upload hoặc lease bị worker khác giành lại.
3. **Kiểm tra quãng thời gian sự cố:** queue age p95/p99, worker CPU/memory, object bytes/error, DB lock, số generation thay đổi và thời điểm deploy.
4. **Mitigation an toàn:** tăng worker trong budget tài nguyên, giảm concurrency nếu DB nghẽn, retry bằng lease hợp lệ, tạm dừng job mới nếu quota hạ tầng cạn. Không tắt tenant filter, không bỏ checksum và không reset generation để ép finalize.
5. **Đối soát:** SUCCEEDED luôn có object tải được; FAILED/CANCELLED không có result công khai, active quota slots không bị kẹt, orphan objects được dọn.
6. **Đóng sự cố:** chạy lại test happy path + crash + cross-tenant, theo dõi queue age/FAILED rate, cập nhật runbook và cảnh báo.

**Vận hành retention:** document TTL cho metadata và file riêng, cron/sweeper chạy với quyền least privilege, object lifecycle không xóa sớm hơn API TTL. Cân nhắc giới hạn downloads, access audit và chi phí egress. Tách secret management của DB/storage/JWT issuer; không dùng bucket public chỉ để đơn giản hóa bài demo.

## 11. Đề bài tổng hợp có thể chấm và mở rộng

**Đề bài:** xây dịch vụ **Report Export Jobs** theo các mục 1–10. Cho một bảng orders chứa dữ liệu của hai tenant, nhiều thời điểm và status. Hệ thống chạy **hai API replicas và hai worker replicas** để chứng minh idempotency/lease không phụ thuộc RAM của một instance. Dùng PostgreSQL (Testcontainers cho integration test), private filesystem/object-store test adapter, Spring MVC và OAuth2 Resource Server mock JWT ở HTTP test; có ít nhất một test xác minh token thực ở trust boundary.

### 11.1. Các mốc triển khai đề xuất

| Mốc | Yêu cầu hoàn thành | Cách kiểm tra |
|---|---|---|
| **A — Contract** | OpenAPI cho POST/status/result, state machine, errors và scopes | Lint spec và review HTTP examples |
| **B — Durable acceptance** | POST 202 sau COMMIT; idempotency + quota nguyên tử | Hai POST cùng key, crash sau COMMIT |
| **C — Worker** | Claim lease, progress, retry có giới hạn, finalize có fencing | Hai worker cạnh tranh, lease expiry và stale finalize |
| **D — Result** | Snapshot hợp đồng rõ, CSV streaming, private object + checksum | Tệp đúng dòng, tải khi SUCCEEDED, chưa ready 409 |
| **E — Security** | Tenant isolation, scope read/export, safe errors và TTL | JWT tenant B/role viewer không thấy result tenant A |
| **F — Operations** | Metrics, cancellation (tùy chọn), sweeper, runbook | Stuck job + expired object drill |

**Mốc tối thiểu bắt buộc:** A–E. Cancellation và signed URL có thể xem là mở rộng nếu thời gian hạn chế, nhưng vẫn phải mô tả rõ xử lý TTL và job stuck. Không dùng một demo luôn chuyển state thành SUCCEEDED ngay trong controller để giả kiểm thử.

### 11.2. Thang đánh giá 100 điểm

| Hạng mục | Điểm | Tiêu chí |
|---|---:|---|
| REST/OpenAPI contract | 20 | 202+Location, 200 status/result, Retry-After, lỗi đúng, examples nhất quán |
| Transaction/idempotency/quota | 20 | Job durable, replay same key, conflict payload khác, concurrency đúng |
| Worker/recovery | 20 | Claim atomic, lease fencing, retry/deadline và không công bố partial |
| Storage và consistency | 15 | Private file, hash/bytes/TTL, snapshot policy, CSV escaping |
| Authentication/authorization | 15 | JWT/scope, tenant/owner, negative tests, không lộ dữ liệu |
| Testing/observability/runbook | 10 | Integration/fault matrix, metrics và quy trình vận hành |

**Fail ngay cả khi tổng điểm cao** nếu một trong những lỗi sau còn tồn tại: cho phép tenant A tải tệp của tenant B; trả SUCCEEDED khi file chưa tồn tại; hai POST cùng key tạo side effect trùng; upload tệp lên public bucket không được kiểm soát; đọc dữ liệu từ tenant khác vào CSV; hoặc tắt JWT validation để test “chạy xanh”.

### 11.3. Câu hỏi tự kiểm tra sau khi nộp

1. Client gửi POST, DB COMMIT xong nhưng proxy trả 504. **Client cần làm gì?** — Retry cùng key hoặc tra operation đã biết; 504 không chứng minh job chưa tạo.
2. Worker ghi tệp vào storage thành công, rồi mất điện trước khi DB SUCCEEDED. **Tệp có nên tải được?** — Không, chưa có kết quả đã publish và được phân quyền; retry/sweeper xử lý object tạm.
3. Worker A giữ generation 1, lease hết và B claim generation 2. A hoàn thành trước B. **Ai được finalize?** — Chỉ worker còn giữ lease/generation hiện hành theo CAS và deadline.
4. Status JSON nói progress 100% nhưng upload còn dở. **Hợp đồng đã đúng chưa?** — Chưa, 100% phải phản ánh mức được công bố; final readiness chỉ khi object cuối tồn tại + DB commit.
5. Tenant khác biết UUID job của bạn. **Có tải CSV được không?** — Không; mỗi GET kiểm actor, tenant, scope và policy, không tin UUID như credential.
6. Report đang đọc orders theo offset, order mới xuất hiện giữa các trang. **Điều gì xảy ra?** — Có thể lặp/bỏ sót; cần snapshot materialization hoặc versioned read, không đơn thuần tăng page size.
7. Result hết TTL trong lúc client đang tải. **Cần định nghĩa gì?** — Quy tắc giữa download đã bắt đầu và download mới, object lifecycle và status 410.
8. Kết quả job FAILED, GET status trả 500. **Sai ở đâu?** — Job đã kết thúc business FAILED nhưng HTTP status resource vẫn có thể đọc 200; 500 nói service đọc trạng thái hỏng.

## 12. Checklist cuối bài và tài liệu tham khảo

- [ ] Tạo một **job resource bền vững**, chỉ trả 202 sau DB COMMIT.
- [ ] **Idempotency-Key** scope theo tenant/actor; fingerprint so payload; unique constraint bảo vệ race.
- [ ] Quota tenant dùng **atomic reservation**, replay không chiếm thêm slot.
- [ ] GET status phản ánh state machine, Retry-After và deadline; lỗi có **Problem Details**.
- [ ] Worker claim với **FOR UPDATE SKIP LOCKED** hoặc cơ chế tương đương; lease và fencing chống stale finalize.
- [ ] Worker không giữ transaction DB suốt upload; retry/backoff/deadline/cancel được quy định.
- [ ] Tệp cuối chỉ được công bố khi **upload + checksum + DB finalize** thành công.
- [ ] CSV có giới hạn row/bytes, escaping, formula-injection policy và snapshot consistency rõ ràng.
- [ ] Status/result/cancel đều kiểm **JWT issuer/audience/scope và tenant/owner**.
- [ ] GET result không lộ object key; private storage, no-store, TTL và content headers đúng.
- [ ] Test crash/retry/parallel claims, cross-tenant, timeout sau commit, cleanup và expired result.
- [ ] Có metrics/trace/runbook cho queue age, lease expired, FAILED và storage errors.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **OpenAPI Specification 3.1**, https://spec.openapis.org/oas/v3.1.0.html; **Spring MVC**, https://docs.spring.io/spring-framework/reference/web/webmvc.html; **Spring Security OAuth2 Resource Server**, https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html; **Spring Transaction Management**, https://docs.spring.io/spring-framework/reference/data-access/transaction.html; **PostgreSQL SELECT FOR UPDATE SKIP LOCKED**, https://www.postgresql.org/docs/current/sql-select.html; **Testcontainers PostgreSQL**, https://java.testcontainers.org/modules/databases/postgres/; **Transactional Outbox Pattern**, https://microservices.io/patterns/data/transactional-outbox.html.

**Kết luận:** Thiết kế REST job bất đồng bộ đúng không dừng ở việc trả 202 rồi chạy một thread. Hệ thống phải có **job record đã commit**, **idempotency và quota an toàn**, **worker lease/fencing**, **trạng thái trung thực**, **kết quả chỉ tải sau khi publish**, **tenant authorization** và **khả năng khôi phục sau crash**. Khi các điều kiện này được chứng minh bằng HTTP, database, storage và fault tests, người dùng mới có thể tạo job, theo dõi và tải báo cáo một cách đáng tin cậy.
