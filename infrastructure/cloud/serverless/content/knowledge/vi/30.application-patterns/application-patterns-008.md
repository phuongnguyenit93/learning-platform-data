# Kích hoạt suy luận AI qua API và điều phối tác vụ nền

Ứng dụng Java serverless có thể cung cấp một API để nhận yêu cầu suy luận AI, gọi model provider và trả kết quả cho caller. Với tác vụ ngắn, function có thể gọi model đồng bộ rồi trả response ngay. Với tác vụ kéo dài như phân tích tài liệu, xử lý nhiều ảnh, tạo báo cáo, embedding theo lô hoặc pipeline nhiều bước, giữ HTTP request mở trong suốt quá trình thường làm tăng timeout, chiếm concurrency và khiến caller khó phục hồi khi mạng bị ngắt.

Một mẫu phổ biến là **API tiếp nhận job, lưu trạng thái bền vững, đưa job vào queue và để worker xử lý nền**. Caller nhận mã job cùng URL kiểm tra trạng thái; worker gọi model, lưu kết quả và cập nhật trạng thái. Workflow engine có thể điều phối các bước dài, retry, nhánh xử lý và callback. Mẫu này tách thời gian tiếp nhận khỏi thời gian hoàn tất, đồng thời cho phép kiểm soát concurrency, quota, chi phí và phục hồi.

Bài học trình bày cách thiết kế API suy luận AI đồng bộ và bất đồng bộ, cách dùng queue hoặc workflow để điều phối tác vụ nền, lưu trạng thái job, triển khai Java function, bảo vệ dữ liệu và quản lý retry, idempotency, observability cùng chi phí.

## 1. Bức tranh tổng thể

Một yêu cầu suy luận AI thường đi qua các bước:

1. Caller gửi input và thông tin tùy chọn như model, task type hoặc output format.
2. API xác thực caller, kiểm tra quyền, giới hạn kích thước và validate input.
3. Hệ thống quyết định chạy đồng bộ hay tạo job nền.
4. Worker gọi model provider hoặc inference endpoint.
5. Kết quả được kiểm tra, chuẩn hóa và lưu trữ.
6. Caller nhận kết quả trực tiếp hoặc truy vấn job status.
7. Log, metric và trace liên kết toàn bộ hành trình.

~~~mermaid
flowchart TD
    Client[Client / application]
    Gateway[API Gateway]
    Handler[Java serverless API]
    Auth[Identity and validation]
    DB[(Job database)]
    Outbox[(Transactional outbox)]
    Queue[Queue / event bus]
    Worker[Java inference worker]
    Model[AI model API]
    Storage[(Object storage)]
    Status[Job status API]

    Client --> Gateway --> Handler --> Auth
    Auth -->|Short task| Model
    Model --> Handler
    Handler -->|Immediate result| Client
    Auth -->|Long task| DB
    DB --> Outbox --> Queue --> Worker
    Worker --> Model
    Worker --> Storage
    Worker --> DB
    Client --> Status
    Status --> DB
    Status --> Client
~~~

API nhận job và worker có thể là hai function độc lập. Điều này cho phép cấu hình timeout, memory, concurrency, IAM và scaling khác nhau theo từng loại workload.

## 2. Chọn suy luận đồng bộ hay bất đồng bộ

Không phải mọi lời gọi model đều cần queue. Chọn mô hình theo thời gian xử lý, trải nghiệm caller và khả năng phục hồi.

| Tiêu chí | Synchronous inference | Asynchronous job |
|---|---|---|
| Thời gian xử lý | Ngắn và có giới hạn rõ | Dài, biến động hoặc nhiều bước |
| HTTP response | Trả kết quả ngay | Trả 202 Accepted và job ID |
| Caller phải chờ | Có | Không |
| Timeout | Phải nằm trong ngân sách HTTP và function | Mỗi bước có timeout riêng; job có deadline |
| Retry | Caller/client và function cần phối hợp | Queue/workflow quản lý retry bền vững |
| Scale | Theo request concurrency | Theo queue backlog và worker capacity |
| Phù hợp | Classification ngắn, prompt nhỏ, query/answer nhanh | Document processing, batch embedding, report generation, multi-step agent workflow |

Một rule of thumb là chỉ chạy đồng bộ khi có thể đáp ứng latency budget của API trong điều kiện bình thường lẫn tail latency. Không chọn đồng bộ chỉ vì model thường trả kết quả nhanh trong lúc thử nghiệm.

### Luồng đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API function
    participant M as Model API

    C->>A: POST /v1/inference
    A->>A: Authenticate + validate
    A->>M: Inference request
    M-->>A: Model response
    A-->>C: 200 result
~~~

### Luồng bất đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API function
    participant D as Job database
    participant Q as Queue
    participant W as Worker function
    participant M as Model API

    C->>A: POST /v1/inference-jobs
    A->>D: Insert job + outbox
    D-->>A: Commit
    A-->>C: 202 + jobId + status URL
    D->>Q: Publish job event
    Q->>W: Deliver job
    W->>M: Inference
    M-->>W: Result
    W->>D: Save result + SUCCEEDED
    C->>A: GET /v1/inference-jobs/{id}
    A->>D: Read status
    D-->>A: SUCCEEDED + result reference
    A-->>C: 200 status/result
~~~

## 3. Thiết kế API contract

API cần thể hiện rõ caller đang yêu cầu kết quả ngay hay tạo một job có thể hoàn tất sau.

Một contract đồng bộ:

~~~http
POST /v1/inference
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "task": "classify-document",
  "model": "approved-model-alias",
  "input": {
    "text": "Nội dung cần phân loại"
  }
}
~~~

Response khi hoàn tất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "requestId": "req-72c1",
  "modelVersion": "model-release-12",
  "output": {
    "label": "invoice",
    "confidence": 0.97
  }
}
~~~

Một contract bất đồng bộ:

~~~http
POST /v1/inference-jobs
Authorization: Bearer <access-token>
Idempotency-Key: 3b7a8d1e-...
Content-Type: application/json

{
  "task": "summarize-document",
  "model": "approved-model-alias",
  "input": {
    "objectRef": "uploads/doc-918"
  },
  "callback": null
}
~~~

Response tiếp nhận:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/inference-jobs/job-918
Retry-After: 3
Content-Type: application/json

{
  "jobId": "job-918",
  "status": "QUEUED",
  "statusUrl": "/v1/inference-jobs/job-918"
}
~~~

202 chỉ nên được trả sau khi job và ý định dispatch đã được lưu bền vững. Nếu chỉ ghi vào memory rồi trả 202, function restart có thể làm mất job.

### Status endpoint

~~~http
GET /v1/inference-jobs/job-918
Authorization: Bearer <access-token>
~~~

Khi job đang chạy:

~~~json
{
  "jobId": "job-918",
  "status": "RUNNING",
  "createdAt": "2026-11-17T09:00:00Z",
  "updatedAt": "2026-11-17T09:00:12Z",
  "progress": {
    "stage": "MODEL_INFERENCE",
    "completedUnits": 1,
    "totalUnits": 3
  }
}
~~~

Khi hoàn tất:

~~~json
{
  "jobId": "job-918",
  "status": "SUCCEEDED",
  "result": {
    "url": "/v1/inference-jobs/job-918/result",
    "expiresAt": "2026-11-18T09:00:00Z"
  }
}
~~~

Khi thất bại, trả error code ổn định và thông điệp an toàn cho caller. Không trả raw stack trace, provider secret hoặc prompt nội bộ.

## 4. Xác định job và idempotency key

Job ID định danh một lần thực thi được lưu trong hệ thống. Idempotency key định danh ý định tạo job từ caller. Hai khái niệm này không nên bị trộn lẫn.

Nếu caller gửi lại cùng request do timeout:

- Cùng idempotency key và cùng request payload: trả lại job đã tạo.
- Cùng key nhưng payload khác: trả 409 Conflict theo contract.
- Key mới: có thể tạo một job mới.

Lưu request hash để phát hiện reuse key sai mục đích. Unique constraint cần bao gồm tenant hoặc caller scope để hai khách hàng không vô tình chia sẻ namespace.

~~~sql
CREATE TABLE inference_jobs (
    job_id            VARCHAR(128) PRIMARY KEY,
    tenant_id         VARCHAR(128) NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      VARCHAR(128) NOT NULL,
    task_type         VARCHAR(64) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    model_alias       VARCHAR(128) NOT NULL,
    model_version     VARCHAR(128) NULL,
    input_ref         TEXT NULL,
    result_ref        TEXT NULL,
    error_code        VARCHAR(64) NULL,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP NULL,
    UNIQUE (tenant_id, idempotency_key)
);
~~~

Không dùng job ID ngẫu nhiên mới cho mỗi lần retry của cùng một HTTP submission. Nếu không, caller timeout rồi gửi lại có thể tạo hai job và trả hai hóa đơn inference.

## 5. Lưu job và dispatch event bằng transactional outbox

Tạo job trong database rồi publish message riêng có thể gặp dual-write problem:

- Database commit thành công nhưng publish queue thất bại: job nằm ở trạng thái QUEUED nhưng không có worker nhận.
- Publish queue thành công nhưng database rollback: worker nhận event tham chiếu đến job không tồn tại.

Dùng transactional outbox để ghi job và event cần dispatch trong cùng transaction.

~~~sql
CREATE TABLE inference_outbox (
    outbox_id       VARCHAR(128) PRIMARY KEY,
    aggregate_id    VARCHAR(128) NOT NULL,
    event_type      VARCHAR(128) NOT NULL,
    payload         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
~~~

Trong một transaction:

1. Insert inference_jobs.
2. Insert inference_outbox với event inference.job.requested.
3. Commit.

Một dispatcher đọc các outbox row chưa publish, gửi message và đánh dấu published. Dispatcher có thể gửi lặp nếu crash sau publish trước khi cập nhật published_at; worker vì vậy vẫn cần idempotency.

Không giữ transaction database mở trong khi gọi queue hoặc model provider. Outbox tách commit dữ liệu khỏi network call.

## 6. State machine cho job

Job nền cần trạng thái rõ ràng để API, worker, support và scheduler hiểu nó đang ở đâu.

Một state machine tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> QUEUED
    RUNNING --> FAILED
    QUEUED --> CANCELLED
    RETRY_WAIT --> CANCELLED
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> CANCELLED
    CANCEL_REQUESTED --> SUCCEEDED
~~~

Các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| QUEUED | Job đã được lưu và đang chờ worker |
| RUNNING | Worker đang giữ lease và xử lý |
| RETRY_WAIT | Lỗi tạm thời, chờ lần thử sau |
| SUCCEEDED | Kết quả đã lưu bền vững |
| FAILED | Lỗi terminal hoặc hết retry policy |
| CANCEL_REQUESTED | Caller yêu cầu hủy, worker cần dừng an toàn |
| CANCELLED | Hệ thống xác nhận job đã hủy |

Cần định nghĩa transition hợp lệ và kiểm tra bằng conditional update/version. Không để bất kỳ worker nào cập nhật job sang SUCCEEDED nếu job đã bị hủy hoặc đã được worker khác claim bằng lease mới.

### Lease và worker recovery

Worker có thể bị dừng giữa lúc gọi model. Dùng lease gồm owner, expiration và generation/fencing token để tránh hai worker cùng ghi kết quả. Nếu lease hết hạn, scheduler hoặc worker khác có thể claim lại. Worker cũ phải kiểm tra token trước khi ghi kết quả cuối.

Không giữ trạng thái RUNNING vô thời hạn. Một sweeper định kỳ tìm job quá lease hoặc quá deadline, sau đó đưa vào retry, FAILED hoặc reconciliation theo policy.

## 7. Java API: tiếp nhận job

Ví dụ Spring Boot minh họa cách API lưu job và outbox trong cùng transaction. Các repository được giả định sử dụng cùng transaction manager/database.

~~~java
public record InferenceJobRequest(
        String task,
        String model,
        String objectRef) {}

public record AcceptedJob(
        String jobId,
        String status,
        String statusUrl) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/v1/inference-jobs")
public class InferenceJobController {

    private final InferenceJobService service;

    public InferenceJobController(InferenceJobService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<AcceptedJob> submit(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody InferenceJobRequest request,
            Authentication authentication) {

        String tenantId = tenantFromTrustedAuthentication(authentication);
        AcceptedJob accepted = service.submit(tenantId, key, request);

        URI statusUri = URI.create(accepted.statusUrl());
        return ResponseEntity.accepted()
                .location(statusUri)
                .body(accepted);
    }

    private String tenantFromTrustedAuthentication(
            Authentication authentication) {
        // Resolve tenant from verified identity/membership context.
        throw new UnsupportedOperationException("Application-specific");
    }
}
~~~

Service:

~~~java
@Service
public class InferenceJobService {

    private final InferenceJobRepository jobs;
    private final OutboxRepository outbox;
    private final RequestHasher hasher;
    private final JobIdGenerator ids;

    public InferenceJobService(
            InferenceJobRepository jobs,
            OutboxRepository outbox,
            RequestHasher hasher,
            JobIdGenerator ids) {
        this.jobs = jobs;
        this.outbox = outbox;
        this.hasher = hasher;
        this.ids = ids;
    }

    @Transactional
    public AcceptedJob submit(
            String tenantId,
            String idempotencyKey,
            InferenceJobRequest request) {

        validate(request);
        String requestHash = hasher.hashCanonical(request);

        var existing = jobs.findByTenantAndKey(
                tenantId, idempotencyKey);

        if (existing.isPresent()) {
            var job = existing.get();
            if (!job.requestHash().equals(requestHash)) {
                throw new IdempotencyConflictException();
            }
            return accepted(job.jobId(), job.status());
        }

        String jobId = ids.newId();
        jobs.insertQueued(
                jobId, tenantId, idempotencyKey,
                requestHash, request.task(), request.model(),
                request.objectRef());

        outbox.insertJobRequested(jobId, tenantId);

        return accepted(jobId, "QUEUED");
    }

    private void validate(InferenceJobRequest request) {
        if (request == null || request.task() == null
                || request.model() == null) {
            throw new IllegalArgumentException("Invalid request");
        }
    }

    private AcceptedJob accepted(String jobId, String status) {
        return new AcceptedJob(
                jobId,
                status,
                "/v1/inference-jobs/" + jobId);
    }
}
~~~

Ví dụ cần bổ sung xử lý race khi hai submission cùng idempotency key đến đồng thời: unique constraint là nguồn quyết định cuối cùng. Khi insert bị conflict, service đọc lại row đã commit, so request hash và trả job hiện có hoặc 409. Không chỉ dựa vào SELECT trước INSERT.

Tenant ID phải được lấy từ identity đã xác thực và membership đã kiểm tra, không tin tenantId caller tự gửi trong JSON.

## 8. Java worker gọi model provider

Worker nhận job ID, claim job bằng lease, đọc input đã được kiểm tra quyền rồi gọi model provider. Client cần timeout rõ ràng và chỉ retry lỗi tạm thời theo policy.

Ví dụ dùng JDK HttpClient:

~~~java
public final class ModelApiClient {

    private final HttpClient client;
    private final URI endpoint;
    private final Duration requestTimeout;

    public ModelApiClient(
            URI endpoint,
            Duration connectTimeout,
            Duration requestTimeout) {
        this.endpoint = endpoint;
        this.requestTimeout = requestTimeout;
        this.client = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public HttpResponse<String> infer(
            String bearerToken,
            String jsonBody) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(requestTimeout)
                .header("Authorization", "Bearer " + bearerToken)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Token nên được lấy từ secret manager hoặc workload identity credential flow. Không hard-code token trong source, image hoặc environment file. Production code cần parse response, kiểm tra status, validate output schema và phân loại lỗi provider.

### Phân loại lỗi model API

| Tình huống | Hành động gợi ý |
|---|---|
| 400 / invalid input | FAILED, không retry cùng payload |
| 401 / 403 | Dừng và cảnh báo credential/IAM |
| 429 / rate limit | Backoff, jitter và tôn trọng Retry-After |
| 5xx tạm thời | Retry có giới hạn |
| Connect/read timeout | Outcome có thể chưa rõ; kiểm tra idempotency/provider request ID |
| Output không đúng schema | Validation failure hoặc retry có giới hạn nếu contract cho phép |
| Content/policy refusal | Lưu outcome theo contract, không retry mù quáng |

Model API có thể tính phí dù client timeout hoặc worker bị dừng sau khi provider đã bắt đầu xử lý. Nếu provider hỗ trợ request idempotency hoặc operation lookup, dùng chúng. Nếu không, lưu provider request ID và trạng thái attempt để reconciliation trước khi gửi lại một request có thể tạo chi phí lần hai.

## 9. Điều phối tác vụ nhiều bước

Một job AI có thể gồm nhiều bước:

1. Lấy tài liệu từ object storage.
2. Kiểm tra loại file và malware.
3. Trích xuất text/OCR.
4. Chia đoạn và tạo embedding.
5. Gọi model để tóm tắt hoặc phân loại.
6. Kiểm tra output theo schema/business rule.
7. Lưu kết quả và thông báo caller.

Có ba cách điều phối thường gặp:

### Queue và worker

Phù hợp khi mỗi message đại diện cho một công việc độc lập, xử lý theo kiểu cạnh tranh giữa nhiều worker và không cần state machine phức tạp. Queue quản lý buffering, delivery và retry; database giữ trạng thái nghiệp vụ.

### Workflow orchestration

Phù hợp khi có nhiều bước, branch, wait, callback, retry theo từng bước, timeout và compensation. Workflow engine giữ trạng thái điều phối và có thể gọi function/service theo từng bước.

### Event choreography

Mỗi service phát event khi hoàn tất và service tiếp theo phản ứng. Phù hợp khi các bước tương đối độc lập và hệ thống chấp nhận eventual consistency. Cần correlation ID, event contract và cơ chế quan sát end-to-end.

| Nhu cầu | Mẫu phù hợp |
|---|---|
| Một job độc lập, xử lý nền | Queue + worker |
| Nhiều bước có thứ tự và nhánh | Workflow/state machine |
| Nhiều service phản ứng với domain event | Event choreography |
| Fan-out nhiều tài liệu độc lập | Queue/parallel map với giới hạn concurrency |
| Có bước chờ người dùng duyệt | Workflow có human task/callback |

Không tạo workflow engine riêng bằng các function tự gọi nhau qua HTTP nếu nền tảng đã có cơ chế orchestration bền vững phù hợp.

## 10. Fan-out, batch và giới hạn concurrency

Với tác vụ xử lý nhiều tài liệu, API có thể tạo một parent job rồi chia thành nhiều child task. Mỗi child xử lý một tài liệu hoặc một batch nhỏ.

Cần xác định:

- Maximum child jobs cho một parent.
- Batch size và payload limit.
- Concurrency cap theo tenant và toàn hệ thống.
- Model provider quota theo request/token.
- Database write capacity.
- Thứ tự xử lý nếu kết quả phụ thuộc nhau.
- Quy tắc tổng hợp kết quả và trạng thái parent.

Không để một request lớn tạo hàng chục nghìn invocation không giới hạn. Dùng admission control, queue và quota để bảo vệ provider và database.

Parent job chỉ SUCCEEDED khi toàn bộ child task bắt buộc hoàn tất theo policy. Nếu một phần thất bại, trạng thái có thể là PARTIALLY_SUCCEEDED hoặc FAILED tùy contract; không âm thầm bỏ qua child lỗi.

## 11. Streaming response cho inference

Một số trải nghiệm chat cần stream token để người dùng thấy nội dung dần xuất hiện. Có thể dùng Server-Sent Events (SSE), WebSocket hoặc streaming response nếu API gateway, runtime và provider đều hỗ trợ.

Streaming phù hợp khi:

- Caller giữ kết nối mở.
- Model phát output tăng dần.
- Thời gian tổng vẫn nằm trong giới hạn của gateway/runtime.
- Client có thể xử lý disconnect và resume policy rõ ràng.

Streaming không tương đương với durable background job. Nếu client ngắt kết nối, function có thể bị hủy hoặc vẫn tiếp tục tùy nền tảng. Cần xác định liệu inference có được tiếp tục, kết quả có được lưu và caller có thể truy vấn sau hay không.

Với tác vụ dài, có thể kết hợp: API tạo job, client subscribe vào event stream để nhận progress, còn database vẫn là nguồn trạng thái chuẩn. Nếu stream mất, caller reconnect và đọc status/result từ API.

## 12. Callback và webhook khi job hoàn tất

Thay vì polling liên tục, caller có thể đăng ký callback URL. Khi job kết thúc, hệ thống gửi webhook thông báo.

Webhook phải có:

- Chữ ký hoặc cơ chế xác thực mạnh.
- Timestamp và chống replay.
- Event ID ổn định.
- Retry policy và timeout.
- Idempotency ở phía receiver.
- Allowlist domain hoặc kiểm soát SSRF khi nhận callback URL.
- Quy trình rotate secret và xác minh endpoint.

Không gọi callback URL tùy ý do caller cung cấp mà không kiểm soát SSRF. Chỉ cho phép HTTPS, chặn địa chỉ private/link-local/metadata theo policy, kiểm tra DNS resolution và redirect, hoặc dùng danh sách endpoint đã đăng ký.

Webhook delivery có thể lặp. Receiver cần deduplicate event ID và trả 2xx sau khi đã lưu bền vững event. Không gửi payload nhạy cảm trực tiếp nếu có thể gửi event reference và yêu cầu caller truy vấn qua API có authorization.

## 13. Retry, DLQ và xử lý job lỗi

Worker có thể lỗi vì provider rate limit, timeout, network, quota hoặc output validation. Phân loại lỗi:

- **Retryable:** throttling, 5xx tạm thời, network interruption.
- **Permanent:** input sai, model không được phép, authorization thất bại.
- **Ambiguous:** provider có thể đã xử lý nhưng response bị mất.
- **Business/policy outcome:** model từ chối hoặc output không đạt điều kiện nghiệp vụ.

Dùng capped exponential backoff và jitter. Giới hạn max attempts, max elapsed time và job deadline. Với retry dài, lưu RETRY_WAIT và lên lịch lần thử sau thay vì giữ function chạy và sleep.

DLQ giữ job event vượt retry policy để điều tra. Redrive phải giữ nguyên job ID và idempotency identity. Nếu provider đã hoàn tất request trước khi worker crash, cần reconciliation để tránh gọi model và tính phí lần nữa.

## 14. Hủy job và deadline

Caller có thể muốn hủy job khi không còn cần kết quả. API có thể cung cấp:

~~~http
POST /v1/inference-jobs/job-918/cancel
Authorization: Bearer <access-token>
~~~

Hủy là yêu cầu có tính best-effort. Nếu worker đang gọi provider, việc hủy request phụ thuộc khả năng cancel của HTTP client/provider. Một số inference đã bắt đầu có thể không dừng được và vẫn phát sinh chi phí.

Thiết kế:

- Chuyển state sang CANCEL_REQUESTED bằng conditional update.
- Worker kiểm tra cancellation trước bước tiếp theo và trước khi lưu kết quả.
- Nếu provider hỗ trợ cancel operation, gọi endpoint tương ứng.
- Ghi rõ outcome nếu provider không thể hủy.
- Không chuyển CANCELLED khi side effect hoặc inference vẫn đang chạy mà hệ thống chưa xác nhận.
- Job hết deadline phải được đưa vào terminal state hoặc reconciliation.

Mỗi job nên có deadline tuyệt đối. Worker không được bắt đầu bước mới nếu remaining time không đủ cho timeout và cleanup dự kiến.

## 15. Bảo mật input, prompt và model output

Input cho model có thể chứa dữ liệu cá nhân, tài liệu nội bộ, mã nguồn hoặc nội dung độc hại. Model output cũng là dữ liệu không tin cậy cho đến khi được kiểm tra.

Các nguyên tắc:

- Xác thực caller và kiểm tra quyền theo tenant/job/object.
- Lấy tenant context từ identity đáng tin cậy.
- Kiểm tra quyền đọc objectRef trước khi worker tải dữ liệu.
- Không cho caller chọn model tùy ý; dùng allowlist model alias và policy.
- Giới hạn input size, file type, token budget và output size.
- Redact dữ liệu nhạy cảm trước khi gửi provider nếu cần.
- Không đưa secret hoặc system prompt nội bộ vào log.
- Xử lý prompt injection trong tài liệu như input không tin cậy.
- Không thực thi trực tiếp code, SQL, URL hoặc tool call do model sinh ra.
- Validate output theo schema và business rules.
- Dùng human approval cho hành động có tác động cao.

Prompt instruction không phải ranh giới bảo mật. Quyền gọi tool, truy cập database hoặc gửi email phải được kiểm tra ở code/service layer độc lập với nội dung model trả về.

## 16. Quản lý model, prompt và reproducibility

Kết quả AI có thể thay đổi theo model version, prompt template, decoding parameters và provider behavior. Để điều tra hoặc tái tạo kết quả, lưu metadata:

- Model alias và model version/provider revision nếu có.
- Prompt template ID và version.
- Input schema version.
- Temperature, top-p, max tokens hoặc tham số liên quan.
- Provider request ID.
- Token usage và latency.
- Safety/policy outcome.
- Code release ID.
- Thời điểm thực thi.

Không nhất thiết lưu toàn bộ prompt và response nếu dữ liệu nhạy cảm hoặc retention không cho phép. Có thể lưu hash, redacted metadata và object reference có kiểm soát.

Nếu model alias tự động trỏ sang version mới, quyết định model thực tế cần được ghi lại trong job record. Với job đang chờ, xác định dùng version tại thời điểm submit hay tại thời điểm worker chạy; không để hành vi thay đổi ngầm mà không có contract.

## 17. Quota, rate limit và admission control

AI provider thường có quota theo request/second, token/second, model, project hoặc account. Function scale-out nhanh có thể vượt quota dù API nội bộ chưa đạt max concurrency.

Quản lý tải ở nhiều lớp:

- Per-user/per-tenant request rate.
- Global request rate theo provider/model.
- Token budget theo tenant hoặc task.
- Maximum queued jobs và queue age.
- Worker maximum concurrency.
- Per-model concurrency.
- Maximum input/output token.
- Daily/monthly spend limit hoặc budget alert.

Có thể dùng token bucket hoặc distributed limiter. Nếu provider trả 429, worker backoff và queue tiếp tục giữ job. Không để nhiều worker cùng retry tức thì.

Trả 429 khi caller vượt quota cá nhân; trả 503 hoặc trạng thái queued khi hệ thống tạm không nhận thêm workload theo contract. Không chấp nhận vô hạn rồi để backlog vượt retention hoặc budget.

## 18. Multi-tenant isolation

Mỗi job phải gắn với tenant/caller scope. Khi đọc status hoặc result, API kiểm tra quyền trên chính job đó; biết job ID không có nghĩa là có quyền truy cập.

Các kiểm soát:

- Unique idempotency key theo tenant.
- Job row có tenant_id và index phù hợp.
- Query status/result luôn lọc theo tenant.
- Object storage path hoặc metadata có tenant scope.
- Worker chỉ đọc input và secret thuộc workload được phép.
- Callback endpoint được gắn với tenant và owner.
- Quota/cost attribution theo tenant.
- Log/trace không làm lộ payload giữa tenant.

Không tin tenantId trong event payload nếu event có thể đến từ nguồn không tin cậy. Producer hoặc gateway phải ký/xác thực context; worker kiểm tra source identity và quyền truy cập object trước khi xử lý.

## 19. Observability end-to-end

Một job có thể qua API, outbox dispatcher, queue, worker, model provider và callback. Dùng các ID khác nhau cho các mục đích khác nhau:

- requestId: một HTTP request.
- jobId: một business job.
- eventId: một message/event.
- traceId: một distributed trace.
- providerRequestId: request gửi tới model provider.

Propagate trace context qua message attributes nếu broker hỗ trợ. Gắn jobId và release/model version vào structured logs và traces. Không dùng các ID cardinality cao làm metric labels.

Metric quan trọng:

- Job accepted, queued, running, succeeded, failed và cancelled.
- Queue age và thời gian chờ trước khi worker bắt đầu.
- End-to-end completion latency.
- Model API latency, 429, 5xx và timeout.
- Retry count và DLQ depth.
- Token input/output và cost estimate.
- Per-tenant quota rejection.
- Job lease expiry và stuck RUNNING.
- Callback delivery success/failure.
- Cost per successful job.

Dashboard cần tách thời gian queue wait, preprocessing, model inference, post-processing và callback. Nếu chỉ đo tổng duration, khó biết bottleneck nằm ở queue hay provider.

## 20. Chi phí và unit economics

Chi phí inference không chỉ là compute của Java function. Tổng chi phí có thể gồm:

~~~text
Total job cost =
  API/function compute
  + queue/event operations
  + model input/output tokens or provider compute
  + storage and data transfer
  + logs, metrics and traces
  + retry and duplicate attempts
  + workflow/orchestration charges
~~~

Model provider có thể tính theo input token, output token, image/audio unit, model compute time hoặc provisioned throughput. Worker retry sau timeout có thể làm phát sinh phí model dù job chưa ghi nhận kết quả.

Theo dõi:

- Cost per submitted job.
- Cost per successful job.
- Input/output tokens per task type.
- Retry cost và duplicate inference.
- Storage bytes và retention.
- Cost theo model, tenant và business unit.
- Tỷ lệ job thất bại sau khi đã tiêu thụ token.

Dùng model nhỏ/nhanh cho tác vụ đơn giản, giới hạn max output tokens, cắt input không cần thiết, cache kết quả khi semantics cho phép và batch embedding nếu provider hỗ trợ. Không cache output nhạy cảm giữa tenant hoặc khi prompt/context làm thay đổi kết quả.

## 21. Kiểm thử API và workflow

Cần test cả API contract lẫn failure window của tác vụ nền.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Request hợp lệ đồng bộ | Trả kết quả theo latency contract |
| Request dài | Trả 202 sau khi job/outbox commit |
| Cùng idempotency key, cùng payload | Trả cùng job ID |
| Cùng key, payload khác | 409 Conflict |
| DB commit thành công, publish thất bại | Outbox dispatcher sẽ publish lại |
| Queue giao duplicate | Worker không tạo side effect trùng |
| Worker crash sau provider response | Reconciliation/idempotency xử lý outcome chưa rõ |
| Provider 429 | Backoff và không vượt quota |
| Provider 5xx | Retry có giới hạn |
| Provider 401/403 | Dừng retry và cảnh báo cấu hình |
| Job quá deadline | Chuyển trạng thái terminal/reconciliation |
| Caller đọc job tenant khác | 403 hoặc 404 theo security contract |
| Callback bị gửi lặp | Receiver deduplicate event ID |
| Cancel trong lúc RUNNING | Best-effort cancel và state transition hợp lệ |
| Model output sai schema | Không lưu như kết quả thành công |
| Queue backlog tăng | Admission/concurrency control bảo vệ provider |

Dùng fake model provider cho unit/integration test để kiểm soát latency, status và output. Contract test với provider thật nên chạy có giới hạn, không dùng dữ liệu nhạy cảm và kiểm soát ngân sách.

## 22. Những lỗi thiết kế thường gặp

- **Giữ HTTP request mở cho tác vụ dài:** dễ timeout và giữ concurrency; chuyển sang job nền.
- **Trả 202 trước khi lưu job bền vững:** restart có thể làm mất công việc; commit job/outbox trước.
- **Publish queue và ghi database riêng rẽ:** tạo dual-write inconsistency; dùng transactional outbox.
- **Không có idempotency:** caller retry tạo nhiều job; dùng key và request hash.
- **Tin job ID là authorization:** có thể lộ kết quả giữa tenant; kiểm tra quyền mỗi lần đọc.
- **Worker không có lease:** nhiều worker có thể xử lý cùng job; dùng conditional claim/fencing.
- **Retry mọi lỗi model API:** lãng phí token và tăng tải; phân loại lỗi.
- **Không xử lý timeout outcome unknown:** provider có thể đã xử lý; lưu provider request ID và reconcile.
- **Không giới hạn token/concurrency:** bill tăng và quota bị vượt; admission control.
- **Dùng model alias mà không ghi version thực:** khó điều tra thay đổi kết quả; lưu model metadata.
- **Tin prompt là security boundary:** model có thể bị prompt injection; kiểm tra quyền trong code.
- **Lưu prompt/response đầy đủ vào log:** có thể rò dữ liệu; redact và áp dụng retention.
- **Polling quá dày:** tăng API/database cost; dùng Retry-After, backoff hoặc callback.
- **Hủy job nhưng vẫn báo CANCELLED ngay:** worker/provider có thể còn chạy; dùng CANCEL_REQUESTED và xác nhận.
- **Không theo dõi queue age:** job có thể bị chậm dù worker invocation vẫn thành công; đo end-to-end latency.

## 23. Quy trình xây dựng ứng dụng Java serverless có AI inference

1. Xác định task type, latency budget và input/output contract.
2. Chọn synchronous hoặc asynchronous theo thời gian xử lý và trải nghiệm caller.
3. Thiết kế API, authentication, tenant authorization và idempotency.
4. Với async, lưu job và outbox trong cùng transaction trước khi trả 202.
5. Thiết kế state machine, lease, deadline, retry và cancellation.
6. Đưa job event vào queue hoặc workflow engine.
7. Giới hạn worker concurrency theo provider quota và downstream capacity.
8. Gọi model bằng HTTP client có timeout, credential và error classification.
9. Validate output, lưu result an toàn và ghi model/prompt version.
10. Dùng callback hoặc status polling để trả kết quả cho caller.
11. Bảo vệ data, prompt, tool access và object reference theo tenant.
12. Instrument trace, queue age, token usage, retry, DLQ và cost per successful job.
13. Kiểm thử duplicate, timeout, provider 429/5xx, crash và redrive.
14. Triển khai canary, theo dõi latency/cost và điều chỉnh quota.
15. Định kỳ rà soát model version, retention, spend limit và policy.

## 24. Ghi nhớ

Suy luận AI đồng bộ phù hợp với request ngắn có latency budget rõ. Tác vụ dài hoặc nhiều bước nên được tiếp nhận thành job bền vững, trả 202 cùng job ID, sau đó xử lý qua queue hoặc workflow. Job database giữ trạng thái chuẩn; transactional outbox bảo đảm ý định dispatch không bị mất giữa database và broker.

Worker cần lease, idempotency, timeout, retry có giới hạn và xử lý outcome chưa rõ từ model provider. API status/result phải kiểm tra quyền theo tenant. Prompt và model output đều là dữ liệu không tin cậy; quyền tool và truy cập dữ liệu phải được enforce ở code.

Theo dõi queue wait, inference latency, token usage, retry, DLQ và cost per successful job. Kiến trúc tốt giúp API phản hồi nhanh, worker scale theo tải, tác vụ có thể phục hồi sau lỗi và chi phí AI được kiểm soát khi số lượng job tăng.

