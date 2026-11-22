# Phân biệt lỗi tiếp nhận với lỗi phát sinh trong lúc chạy

## 1. Một HTTP request thành công chưa có nghĩa công việc đã thành công

Ứng dụng yêu cầu tạo báo cáo doanh thu gồm hàng triệu giao dịch. API xác thực người gọi, kiểm tra tham số, ghi một **job** vào database rồi trả **202 Accepted**. Mười phút sau, worker đọc dữ liệu và phát hiện tệp nguồn bị hỏng; báo cáo không thể hoàn tất.

Nếu chỉ nhìn HTTP status của lần gọi đầu, client có thể nhầm **202** thành “đã tạo xong báo cáo”. Nếu backend cố trả **500** sau mười phút trên cùng request, nó cũng sai về mô hình giao tiếp: response HTTP ban đầu đã kết thúc. Lỗi phát sinh sau đó phải được thể hiện qua **trạng thái công việc**, API truy vấn trạng thái hoặc một kênh thông báo đã thỏa thuận.

Bài học trong chương **Xử lý bất đồng bộ** của module **INTEGRATION_API_REST** tập trung vào ranh giới này. Người học vận dụng thiết kế resource/URI, phương thức và mã trạng thái HTTP, hợp đồng JSON/Problem Details, idempotency, xác thực/phân quyền, OpenAPI và kiểm thử với Java/Spring.

Mục tiêu là thiết kế được một API trả lời chính xác hai câu hỏi **khác nhau**:

1. **Tiếp nhận:** “Hệ thống có chấp nhận chịu trách nhiệm xử lý yêu cầu này không?”
2. **Thực thi:** “Công việc đã hoàn tất, thất bại, bị hủy hay vẫn đang chạy?”

> **Nguyên tắc:** **Lỗi tiếp nhận** được trả trong response của request tạo job. **Lỗi thực thi** xảy ra sau khi job đã được nhận và phải trở thành **trạng thái/kết quả bền vững của job**. Đừng biến 202 thành lời hứa hoàn tất, cũng đừng biến mọi job FAILED thành HTTP 500 khi đọc trạng thái.

## 2. Hai đường thời gian và điểm cam kết tiếp nhận

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant D as Database + Outbox
    participant W as Worker
    participant X as Data source
    C->>A: POST /api/exports + Idempotency-Key
    A->>A: Auth, quota, validate admission
    A->>D: Ghi job + outbox trong transaction
    D-->>A: COMMIT
    A-->>C: 202 Accepted + Location: /api/export-jobs/J1
    Note over C,A: HTTP request tạo job đã kết thúc
    D-->>W: Event xử lý (có thể giao lại)
    W->>X: Đọc dữ liệu, tạo báo cáo
    X-->>W: Lỗi định dạng tệp nguồn
    W->>D: Ghi FAILED + lỗi có cấu trúc
    C->>A: GET /api/export-jobs/J1
    A->>D: Đọc trạng thái theo quyền
    D-->>A: FAILED
    A-->>C: 200 OK, body state=FAILED + error
~~~

Trên đường thời gian này có **hai cam kết độc lập**:

- **Admission commitment:** sau khi trả 202 theo **hợp đồng ví dụ**, server đã ghi bền vững job và có cơ chế xử lý/khôi phục nó.
- **Execution outcome:** chỉ khi state chuyển thành **SUCCEEDED** và kết quả dùng được, hệ thống mới nói công việc đã thành công.

HTTP **202 Accepted theo RFC 9110** có ý nghĩa **đã được chấp nhận để xử lý nhưng chưa hoàn tất**; HTTP không tự yêu cầu mọi server phải lưu job vào một DB cụ thể. Tuy nhiên, để thiết kế API đáng tin cậy, bài này chọn hợp đồng **chỉ trả 202 sau khi lưu bền vững**. Nếu không tạo được cam kết đó, server phải báo lỗi tiếp nhận, không phát 202 giả.

### Hai loại lỗi nhìn giống nhau nhưng khác trách nhiệm

| Trường hợp | Giai đoạn | Nơi biểu diễn | Client cần làm |
|---|---|---|---|
| JSON sai cú pháp | Trước tiếp nhận | **400 Bad Request** của POST | Sửa request |
| Không có quyền tạo export | Trước tiếp nhận | **401/403** của POST | Xác thực hoặc xin quyền |
| Tenant vượt hạn mức job | Trước tiếp nhận | **429** của POST, có thể Retry-After | Giảm tốc độ hoặc đợi theo policy |
| Database không thể lưu job | Trước tiếp nhận | **503/500** tùy nguyên nhân; không trả 202 | Retry an toàn theo idempotency/tra trạng thái |
| Tệp dữ liệu hỏng phát hiện ở phút thứ 3 | Sau tiếp nhận | **GET job: 200, state=FAILED, error=...** | Hiểu nguyên nhân, sửa nguồn và tạo intent mới nếu phù hợp |
| Data provider 503 tạm thời khi worker chạy | Sau tiếp nhận | **RUNNING/RETRYING**, sau đó SUCCEEDED hoặc FAILED | Theo dõi job; không tự gửi lại POST |
| Chính endpoint đọc status bị ngừng hoạt động | Trong request đọc status | **503 của GET status** | Retry GET có backoff; chưa được suy job FAILED |

**Điểm phân biệt:** Mã trạng thái của **GET status** mô tả **lần đọc status có thành công không**; trường **state** trong JSON mô tả **kết quả của công việc**. Hai tầng không được nhập làm một.

## 3. Thiết kế hợp đồng POST: từ chối trước khi nhận hay nhận để xử lý?

Ví dụ nghiệp vụ tạo báo cáo:

~~~http
POST /api/exports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: export-tenant27-20261118-01
Content-Type: application/json
Accept: application/json

{
  "reportType": "REVENUE",
  "from": "2026-11-01",
  "to": "2026-11-18"
}
~~~

Tầng tiếp nhận cần quyết định nhanh, trước khi cam kết:

1. **Đọc request:** method, Content-Type, JSON, kích thước, các trường bắt buộc.
2. **Authentication và authorization:** ai được tạo báo cáo, thuộc tenant/tập dữ liệu nào?
3. **Validation tại thời điểm nhận:** khoảng ngày, loại báo cáo, quyền truy cập nguồn và quy tắc có thể kiểm tra với chi phí hợp lý.
4. **Rate limit/admission control:** quota theo tenant, số job đang chạy/chờ, công suất lưu bền vững và mức backlog được phép.
5. **Chống trùng intent:** cùng Idempotency-Key và fingerprint có operation cũ không?
6. **Lưu trạng thái ban đầu:** job **PENDING/QUEUED** và dấu vết để worker nhận việc; commit xong mới trả nhận.

### Ma trận status của request tạo job

| HTTP status của POST | Ví dụ | Ý nghĩa |
|---|---|---|
| **400 Bad Request** | JSON sai cú pháp, parameter không đúng định dạng | Request chưa được chấp nhận |
| **401 Unauthorized** | Thiếu credential hợp lệ | Chưa được chấp nhận |
| **403 Forbidden** | Không có quyền trên dữ liệu/tenant | Chưa được chấp nhận |
| **409 Conflict** | Cùng khóa idempotency nhưng operation đang tranh chấp theo policy; xung đột trạng thái nghiệp vụ | Chưa tạo job mới; cần hiểu contract |
| **413 Content Too Large** | Upload/request body quá lớn | Chưa được chấp nhận |
| **415 Unsupported Media Type** | Gửi XML khi endpoint chỉ nhận JSON | Chưa được chấp nhận |
| **422 Unprocessable Content** | Request đúng cú pháp nhưng vi phạm quy tắc được kiểm tra ngay | Chưa được chấp nhận |
| **429 Too Many Requests** | Vượt rate/quota của bên gọi | Không ghi job mới; có thể hướng dẫn chờ |
| **503 Service Unavailable** | Hệ thống tạm không thể nhận bền vững công việc mới | Không hứa sẽ chạy |
| **202 Accepted** | Job đã được ghi bền vững để xử lý sau | **Đã nhận**, không có nghĩa thành công |

Mã cụ thể của một lỗi validation hoặc xung đột vẫn là **quyết định có tài liệu hóa của API**; bảng không thay thế toàn bộ HTTP semantics. Với một service có tải cao, **quá tải toàn hệ thống** thường phù hợp với 503, trong khi **tenant vượt rate limit** thường là 429.

### Phản hồi tiếp nhận

~~~http
HTTP/1.1 202 Accepted
Location: /api/export-jobs/6f71b7d0-38a4-4de6-9d97-1e87d02bb122
Content-Type: application/json
Cache-Control: no-store

{
  "jobId": "6f71b7d0-38a4-4de6-9d97-1e87d02bb122",
  "state": "PENDING",
  "statusUrl": "/api/export-jobs/6f71b7d0-38a4-4de6-9d97-1e87d02bb122",
  "pollAfterSeconds": 3
}
~~~

**Location** trỏ tới resource theo dõi job. **pollAfterSeconds** là trường **do API này tự định nghĩa** để gợi ý nhịp polling; không phải trường bắt buộc của HTTP. Chỉ tiêu thụ **202** như một thông báo tiếp nhận, không tự động hiển thị “Đã xuất báo cáo thành công”.

Nếu client timeout **ngay sau khi DB đã commit nhưng trước khi nhận 202**, kết quả là **không rõ đối với client**. Hãy retry cùng **Idempotency-Key** theo contract hoặc tra cứu operation, **không tạo key mới** để tránh hai job.

## 4. Thiết kế resource trạng thái: lỗi thực thi đi đâu?

Server công bố **GET /api/export-jobs/{jobId}** để đọc trạng thái. Một mô hình nhỏ đủ dùng:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Admission commit
    PENDING --> RUNNING: Worker claim
    RUNNING --> RETRYING: Lỗi tạm thời
    RETRYING --> RUNNING: Backoff xong
    RUNNING --> SUCCEEDED: Result persisted
    RUNNING --> FAILED: Lỗi terminal
    RETRYING --> FAILED: Hết retry budget
    PENDING --> CANCELLED: Hủy trước khi chạy
    RUNNING --> CANCELLED: Hủy được xác nhận
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

Mô hình trên là **hợp đồng minh họa**; hệ thống có thể bỏ state RETRYING nếu chỉ công bố PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED. Quy tắc cần công bố: **trạng thái terminal**, quy tắc chuyển state và cách client hành động.

### Khi job đang chạy

GET status thành công trả **200 OK** với **state=RUNNING**, tiến độ nếu có, **resultUrl=null** và **error=null**. Chưa được coi là kết quả cuối.

### Job thất bại trong lúc chạy: GET vẫn có thể trả 200

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "jobId": "6f71b7d0-38a4-4de6-9d97-1e87d02bb122",
  "state": "FAILED",
  "progressPercent": 65,
  "resultUrl": null,
  "error": {
    "type": "https://api.example.test/problems/source-schema-unsupported",
    "title": "Source data cannot be processed",
    "code": "SOURCE_SCHEMA_UNSUPPORTED",
    "detail": "Một tệp đầu vào có phiên bản schema chưa được hỗ trợ.",
    "clientAction": "CORRECT_SOURCE_AND_RESUBMIT"
  }
}
~~~

**Vì sao GET trả 200?** Request đọc trạng thái **thành công**. Field **FAILED** nói công việc trước đó thất bại. Nếu server trả 500 khi đọc một job FAILED, HTTP client có thể retry GET liên tục như thể endpoint status bị lỗi, trong khi trạng thái nghiệp vụ terminal đã biết.

Trong ví dụ, **error** là **object lỗi lồng trong representation trạng thái**, lấy cảm hứng từ cấu trúc Problem Details. Vì response mang media type **application/json** cho job resource, nó **không phải một HTTP Problem Details response độc lập**. Nếu API muốn trả **application/problem+json**, phải gắn nó với status HTTP phù hợp của **request hiện tại**, chẳng hạn endpoint GET kết quả không khả dụng hoặc POST bị từ chối.

### Job hoàn tất

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "jobId": "6f71b7d0-38a4-4de6-9d97-1e87d02bb122",
  "state": "SUCCEEDED",
  "progressPercent": 100,
  "resultUrl": "/api/export-results/r-8472",
  "error": null
}
~~~

Chỉ đặt **SUCCEEDED** khi result đã được **ghi bền vững, kiểm tra và có thể truy xuất** theo contract. Việc worker tính xong trong RAM hoặc upload file chưa commit không đủ để client được hứa tải kết quả.

Với **GET /api/export-results/{resultId}**, nếu file chưa sẵn sàng, API có thể trả **409 Conflict + Problem Details RESULT_NOT_READY** theo contract; khi tải file vẫn phải kiểm tra quyền. Điều đó không thay cách **GET job status** trả state trong JSON.

## 5. Các bất biến kiến trúc để không hứa thành công giả

### Tiếp nhận bền vững trước 202

Một cách triển khai tin cậy là **database transaction + transactional outbox**:

~~~text
POST /api/exports
  → authenticate + authorize + validate + quota
  → transaction:
       INSERT job(PENDING, tenant, request fingerprint)
       INSERT outbox(JobRequested, jobId)
       COMMIT
  → 202 + Location /api/export-jobs/{jobId}

Outbox relay → durable queue → worker → update job state/result
~~~

Nếu ứng dụng **ghi job xong nhưng crash trước khi gửi queue**, outbox giữ sự kiện để relay phát lại. Nếu relay phát trùng, worker phải chống lặp theo **jobId/eventId**. Nếu queue đang lỗi nhưng outbox đã commit, API **có thể** tiếp tục nhận và trả 202 miễn nó còn bảo đảm xử lý sau và có capacity/boundaries đã công bố. Khi backlog/storage vượt khả năng nhận an toàn, admission control phải **từ chối job mới** thay vì tiếp tục trả 202.

**202 không được dùng như cách “đẩy lỗi đi chỗ khác”** khi không có cơ chế bền vững, retry hoặc người chịu trách nhiệm xử lý. Một background task chỉ nằm trong memory của web process có thể biến mất khi deploy/restart.

### Cập nhật state có kiểm soát

- Chỉ worker/dispatcher có quyền được phép chuyển **PENDING → RUNNING**.
- Các worker cạnh tranh phải có **atomic claim/lease/version** để không cùng hoàn tất một job theo hai kết quả trái nhau.
- **SUCCEEDED/FAILED/CANCELLED** là terminal trong hợp đồng này; không âm thầm chuyển FAILED về RUNNING nếu chưa định nghĩa retry nghiệp vụ mới.
- Việc ghi terminal state và metadata kết quả phải **nhất quán**: không công bố SUCCEEDED khi file chưa thể đọc; không báo FAILED khi downstream đã hoàn tất side effect nhưng server chưa đối soát.
- Audit/metrics phản ánh chính xác stage, reason và số lần thử, tránh dùng HTTP status của polling để đếm job thành công.

### Lỗi mạng sau khi đã tiếp nhận

Giả sử DB commit thành công nhưng connection mất trước response. Client không biết có job hay không. Với endpoint có side effect hoặc chi phí lớn:

~~~http
Idempotency-Key: export-tenant27-20261118-01
~~~

Server ràng buộc key với **tenant + loại operation + fingerprint request**, lưu kết quả admission và trả **cùng jobId** cho retry cùng intent. Cùng key nhưng payload khác phải bị từ chối theo hợp đồng. **Idempotency-Key không phải authorization**; mọi request mới và status lookup vẫn phải kiểm tra quyền.

## 6. Security: trạng thái job không phải dữ liệu công khai

Đường dẫn **/api/export-jobs/{jobId}** có thể chứa tiến độ, báo cáo, lỗi và đường dẫn tải dữ liệu nhạy cảm. **UUID khó đoán không thay authorization**.

- **Quyền theo object:** mọi GET status/result, tải error report, cancel và retry kiểm tra **tenant/owner/role**; UUID khó đoán không thay authorization.
- **Identity và khóa:** tenant được lấy từ security context, không tin body tự khai; Idempotency-Key có scope, không được dùng để xem response của người khác.
- **Thông tin lỗi:** che stack trace, token, connection string và dữ liệu tenant khác; lưu chi tiết trong log phân quyền.
- **Artifact:** result URL dùng HTTPS, không gắn bearer token vào query; signed URL phải có scope, TTL và quyền phù hợp.
- **HTTP client:** với response riêng tư, dùng **Cache-Control: no-store** theo policy; CORS chỉ cho origin được phép đọc, không thay quyền truy cập.

Webhook là kênh thông báo tùy chọn; thông điệp có thể **đến trùng, muộn hoặc sai thứ tự**. Client phải xác minh chữ ký/timestamp/event ID và tra lại status khi cần; server phải kiểm soát callback URL, redirect/egress để tránh SSRF.

## 7. Java/Spring Boot: controller trả 202 và status endpoint

Ví dụ dùng Spring MVC/Spring Boot 3, tập trung vào HTTP contract. Lớp **ExportJobService** ở đây là interface của ứng dụng; implementation phải ghi job/outbox bền vững và kiểm tra quyền. Mã minh họa không bao gồm schema database, worker hay security configuration hoàn chỉnh.

~~~java
import java.net.URI;
import java.time.LocalDate;
import java.util.UUID;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record CreateExportRequest(
        @NotNull LocalDate from,
        @NotNull LocalDate to,
        @NotNull String reportType) {}

record JobAccepted(UUID jobId, String state) {}
record JobError(String type, String code, String detail, String clientAction) {}
record ExportJobView(
        UUID jobId, String state, Integer progressPercent,
        String resultUrl, JobError error) {}

interface ExportJobService {
    // Transactional: admit idempotent job + outbox, commit before return.
    JobAccepted accept(
            Authentication principal, String key, CreateExportRequest input);
    // Always authorize job against the authenticated principal.
    ExportJobView findVisible(Authentication principal, UUID jobId);
}

@RestController
@RequestMapping("/api")
class ExportJobController {
    private final ExportJobService jobs;

    ExportJobController(ExportJobService jobs) {
        this.jobs = jobs;
    }

    @PostMapping("/exports")
    ResponseEntity<ExportJobView> create(
            Authentication principal,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateExportRequest input) {

        JobAccepted accepted = jobs.accept(principal, key, input);
        URI statusUrl = URI.create(
                "/api/export-jobs/" + accepted.jobId());
        ExportJobView body = jobs.findVisible(
                principal, accepted.jobId());
        boolean terminal = switch (body.state()) {
            case "SUCCEEDED", "FAILED", "CANCELLED",
                 "PARTIALLY_SUCCEEDED" -> true;
            default -> false;
        };
        return ResponseEntity.status(
                    terminal ? HttpStatus.OK : HttpStatus.ACCEPTED)
                .location(statusUrl)
                .cacheControl(CacheControl.noStore())
                .body(body);
    }

    @GetMapping("/export-jobs/{jobId}")
    ResponseEntity<ExportJobView> getStatus(
            Authentication principal, @PathVariable UUID jobId) {
        ExportJobView body = jobs.findVisible(principal, jobId);
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(body); // Kể cả body.state() == "FAILED"
    }
}
~~~

**Điểm cần xem xét khi dùng thật:**

1. **Authentication** đến từ Spring Security; **không** dùng name/tenantId client tự gửi mà không xác minh. **findVisible** phải bảo vệ quyền object-level ở mỗi request.
2. **accept** phải từ chối dữ liệu sai ngay (400/422), kiểm tra hạn mức (429) và **commit job + outbox trước 202**. Method này không được làm công việc xuất báo cáo mất nhiều phút ngay trên request thread.
3. Lần retry POST cùng key/fingerprint phải nhận lại **cùng jobId**; key mismatch cần lỗi riêng; ví dụ controller chưa thể hiện các exception handlers đó.
4. **GET status** trả **200** khi tìm thấy job, kể cả state FAILED. Nếu status store bị lỗi, khi ấy mới có thể dùng **5xx** cho chính GET.
5. Ví dụ chọn **202** khi operation còn xử lý và **200** khi POST trùng key tra lại được job terminal. Body được đọc từ nguồn trạng thái có thẩm quyền, không tự dựng tiến độ bằng 0 cho job đã hoàn tất.

### Xử lý lỗi admission trong Spring

Cấu hình **@RestControllerAdvice** để ánh xạ validation/quota/capacity thành **400/422/429/503 + Problem Details**. Khi trả 429, chỉ gửi **Retry-After** nếu có khoảng chờ hợp lý. Exception của worker chạy sau 202 **không đi qua handler của request POST**; worker phải ghi **job.state/error** và correlation ID.

## 8. State transition và xử lý lỗi của worker

Pseudo-code worker để thấy chỗ quyết định lỗi:

~~~text
run(jobId):
    if !atomicClaimJob(jobId, workerLease):
        return                     # Worker khác đang giữ quyền
    mark RUNNING
    try:
        input = loadAuthorizedSourceSnapshot(jobId)
        result = generateExport(input)
        persistResultAndMetadata(result)
        transition RUNNING -> SUCCEEDED
    catch PermanentInputError e:
        transition RUNNING -> FAILED
            error = (SOURCE_SCHEMA_UNSUPPORTED, sanitizedDetail)
    catch TransientDependencyError e:
        if retryBudgetRemaining(jobId):
            scheduleBackoffWithJitter(jobId)
            transition RUNNING -> RETRYING
        else:
            transition RUNNING -> FAILED
                error = (DEPENDENCY_UNAVAILABLE, sanitizedDetail)
    finally:
        releaseLeaseIfStillOwner(jobId)
~~~

Trong triển khai thật, **chuyển state phải có điều kiện trên version/lease**, nếu không worker cũ có thể ghi đè trạng thái mới. **persistResultAndMetadata** và việc công bố SUCCEEDED phải được phối hợp để không có khoảng trống “SUCCEEDED nhưng file tải không được”.

**Phân loại permanent/transient không chỉ dựa vào HTTP 4xx/5xx của downstream.** Một 404 từ nguồn dữ liệu có thể là permanent nếu object đã bị xóa; một 429 từ provider có thể retryable với hạn mức. Cần xét hợp đồng downstream, deadline và rủi ro side effect.

### Khi cần lưu kết quả lỗi

Lưu các trường tối thiểu như **jobId, state, error.code/type, thời điểm, số lần thử, correlationId**, và mã tham chiếu đến logs nội bộ. Giữ dữ liệu nhạy cảm theo retention và phân quyền. Nếu một job thất bại do bug không lường trước, body dành cho client chỉ nên có **INTERNAL_PROCESSING_ERROR**, không phơi stack trace hoặc SQL.

## 9. OpenAPI 3.1: tách admission và execution state

~~~yaml
openapi: 3.1.0
info: {title: Exports API, version: 1.0.0}
paths:
  /api/exports:
    post:
      summary: Tiếp nhận tạo báo cáo
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [reportType, from, to]
              properties:
                reportType: {type: string}
                from: {type: string, format: date}
                to: {type: string, format: date}
      responses:
        '200':
          description: Request trùng key của job đã ở trạng thái cuối
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ExportJob'}
        '202':
          description: Job đã được ghi nhận, chưa hoàn tất
          headers:
            Location:
              schema: {type: string}
              description: URI resource theo dõi trạng thái
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ExportJob'}
        '400': {description: Request sai}
        '403': {description: Không có quyền}
        '422': {description: Validation ở thời điểm tiếp nhận thất bại}
        '429': {description: Vượt quota tiếp nhận}
        '503': {description: Không thể tiếp nhận an toàn}
  /api/export-jobs/{jobId}:
    get:
      summary: Đọc state của job, kể cả FAILED
      parameters:
        - name: jobId
          in: path
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Đã đọc được trạng thái job
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ExportJob'}
        '404': {description: Job không tồn tại hoặc không được tiết lộ}
        '503': {description: Status service tạm không khả dụng}
components:
  schemas:
    ExportJob:
      type: object
      required: [jobId, state]
      properties:
        jobId: {type: string, format: uuid}
        state:
          type: string
          enum: [PENDING, RUNNING, RETRYING, SUCCEEDED, FAILED,
                 CANCEL_REQUESTED, CANCELLED, PARTIALLY_SUCCEEDED,
                 REQUIRES_RECONCILIATION]
        progressPercent: {type: [integer, 'null']}
        resultUrl: {type: [string, 'null']}
        error: {type: [object, 'null']}
~~~

Đây là **hợp đồng minh họa**: API thật cần định nghĩa đầy đủ **JobError**, security schemes, quyền theo tenant, TTL/retention, idempotency mismatch, điều kiện cancel và webhook nếu có. Quan trọng: **FAILED là giá trị của state trong response 200 của GET status**, không phải một status 500 của request đọc trạng thái.

## 10. Kiểm thử contract và fault injection

### Ma trận nên có

| Test | Request / tác động | Bất biến cần xác nhận |
|---|---|---|
| **Sai JSON / validation** | POST request sai | 400/422, **không có job/outbox** |
| **Không có quyền** | POST bằng tenant khác | 403/404 theo policy, không tiếp nhận |
| **Quota đầy** | POST vượt hạn mức | 429, không có job mới, Retry-After nếu tính được |
| **DB rollback** | Lỗi khi ghi job/outbox | Không trả 202, không có job mồ côi |
| **Commit thành công** | POST hợp lệ | 202 + Location, job PENDING đã lưu |
| **Mất response sau commit** | Cắt kết nối sau COMMIT | Retry cùng Idempotency-Key trả **cùng jobId** |
| **Queue/broker outage** | Dừng relay sau COMMIT | Outbox còn, job vẫn tra được; retry khi phục hồi |
| **Worker thất bại vĩnh viễn** | Nguồn có schema sai | GET job **200 + FAILED**, error.code đúng |
| **Status service lỗi** | DB đọc status không khả dụng | GET trả 503; **không thay state job thành FAILED** |
| **Hai worker cùng nhận job** | Redelivery/lease race | Một terminal outcome, không nhân đôi side effect |
| **Cross-tenant** | Đọc/cancel/tải job khác tenant | Không lộ metadata, body, result hay lỗi |

### Ví dụ MockMvc kiểm tra lỗi thực thi không thành HTTP 500

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ExportJobContractTest {
    @Autowired MockMvc mvc;

    @Test
    void failedJobIsReadableStatusNotHttp500() throws Exception {
        // Fixture: tạo job thuộc principal thử nghiệm, terminal FAILED,
        // error.code=SOURCE_SCHEMA_UNSUPPORTED; cấu hình auth nếu cần.
        String jobId = "6f71b7d0-38a4-4de6-9d97-1e87d02bb122";

        mvc.perform(get("/api/export-jobs/{jobId}", jobId))
           .andExpect(status().isOk())
           .andExpect(content().contentTypeCompatibleWith("application/json"))
           .andExpect(jsonPath("$.state").value("FAILED"))
           .andExpect(jsonPath("$.error.code")
                   .value("SOURCE_SCHEMA_UNSUPPORTED"));
    }
}
~~~

Đây là **khung test phụ thuộc fixture**, không phải test đã chạy. Cần seed job, auth mock/token, error record và repository để test hoạt động. Bổ sung integration test thật qua database/broker và **test sau commit**; MockMvc đơn độc không thể chứng minh outbox/recovery.

### Kiểm tra trải nghiệm client

Client nên xem **202** là “Đang xử lý”, dùng **Location** để poll với giới hạn, hiển thị **SUCCEEDED + resultUrl** khi hoàn tất, hoặc **FAILED + message/clientAction** khi cần sửa. Nếu status GET trả **503**, chỉ tạm không đọc được trạng thái: UI nên giữ “Không thể cập nhật tiến độ”, không hiển thị “Job thất bại”.

## 11. Bài tập: batch nhập 1.000 đơn hàng

Một API **POST /api/import-jobs** nhận URL tới tệp CSV của tenant. API kiểm tra caller có quyền, cấu trúc request và quota trước khi ghi job. Worker sẽ tải tệp, validate từng dòng và tạo đơn hàng. Giả sử:

- Request A thiếu quyền đọc dữ liệu nguồn ngay ở bước tiếp nhận.
- Request B hợp lệ, job J1 được commit và trả 202. Worker sau đó phát hiện 70/1.000 dòng có mã sản phẩm sai.
- Request C hợp lệ, job J2 được nhận. Sau khi tạo 500 đơn, worker gọi downstream timeout; không chắc 500 đơn đã được xác nhận bởi đối tác.
- Client gửi lại B cùng Idempotency-Key khi chưa thấy phản hồi của lần đầu.
- Trong lúc tra J1, status database của API bị gián đoạn trong 10 giây.

**Câu hỏi:** (1) Chọn status cho A và B; (2) trình bày hai cách hợp đồng xử lý 70 dòng lỗi; (3) với J2, có được đánh FAILED rồi retry toàn bộ mà không có item-level dedupe không; (4) request retry của B tạo job nào; (5) GET J1 khi status DB lỗi có được trả 200/FAILED không; (6) đề xuất 5 test và 4 metrics để chứng minh đúng hợp đồng.

### Đáp án định hướng

1. **A:** 403 nếu đã xác thực nhưng không có quyền; **B:** 202 sau commit, chưa khẳng định import xong.
2. **70 dòng lỗi:** chọn all-or-nothing (FAILED, có transaction/compensation) hoặc PARTIALLY_SUCCEEDED với **930 thành công/70 lỗi**, báo cáo lỗi và cơ chế chạy lại an toàn.
3. **J2:** không retry toàn bộ khi downstream timeout; cần item-level dedupe, business reference và đối soát. Nếu chưa rõ side effect, dùng trạng thái yêu cầu reconciliation.
4. **Retry B:** cùng key/scope/fingerprint phải nhận lại **J1**, không tạo J3; payload khác bị từ chối.
5. **Status DB lỗi:** GET status có thể trả **503**; không được tự chuyển J1 thành FAILED.
6. **Kiểm thử:** 403 không tạo job; 202 sau commit; terminal/partial status; retry key cùng job; timeout sau side effect; status outage; cross-tenant. **Metrics:** admission rejects, queue age, job failure rate/code, outbox lag, reconciliation backlog, status GET 5xx.

## 12. Checklist và kết luận

- [ ] POST trả **202 chỉ sau commit** của job/outbox theo hợp đồng; không nhận được thì trả đúng lỗi admission (400/403/422/429/503).
- [ ] Response 202 có **Location/status URL**, không tuyên bố kết quả đã hoàn tất; retry cùng Idempotency-Key trả cùng job.
- [ ] GET status trả **200 với state FAILED** khi đọc job thành công; status storage lỗi thì GET mới có thể trả 5xx.
- [ ] Error admission dùng HTTP status và Problem Details; error execution được lưu trong **job error code/detail** không lộ bí mật.
- [ ] Worker có state transition có kiểm soát, bounded retry, outbox, dedupe/đối soát khi side effect không rõ; partial/cancel có hợp đồng riêng.
- [ ] Mỗi endpoint tạo/đọc/hủy/tải kết quả kiểm tra tenant/owner; artifact, webhook và callback URL được bảo vệ.
- [ ] OpenAPI và contract/failure tests kiểm tra cả admission, execution, broker outage, status outage, partial và cross-tenant.
- [ ] Metrics tách **accepted/rejected**, queue age, job success/failure, retry, outbox lag, lỗi status GET và reconciliation.

**Kết luận:** Một REST API bất đồng bộ có **hai kết quả khác nhau**: tiếp nhận thành công nghĩa là đã nhận trách nhiệm theo cam kết; thực thi thành công chỉ được khẳng định khi job đạt trạng thái cuối có kết quả dùng được. **Lỗi sau 202** phải được ghi nhận trong job và truy vấn qua status resource, không thể hồi tố biến response POST thành 500.

### Tài liệu nền

- **RFC 9110 — HTTP Semantics:** 202 Accepted và cách diễn giải HTTP status.
- **RFC 9457 — Problem Details:** biểu diễn lỗi của request hiện tại.
- **OpenAPI 3.1:** response 202, Location, job state và lỗi admission.
- **Spring Framework/Spring Boot:** MVC, ProblemDetail, transaction, validation và security.

