# Thiết kế pipeline xử lý tài liệu với storage, queue và Java worker

Một pipeline xử lý tài liệu serverless thường bắt đầu khi người dùng tải file lên object storage. Sự kiện tạo object kích hoạt một luồng xử lý; queue giữ công việc bền vững và điều tiết tốc độ; Java worker đọc file, kiểm tra an toàn, trích xuất nội dung, xử lý nghiệp vụ rồi lưu kết quả. API có thể cung cấp trạng thái để người dùng theo dõi mà không phải giữ một HTTP request mở trong suốt thời gian xử lý.

Thiết kế cần xử lý được các tình huống thực tế: storage event có thể đến lặp hoặc sai thứ tự, queue có thể giao message nhiều lần, worker có thể dừng giữa chừng, file có thể độc hại hoặc quá lớn, database có thể chậm, và một tenant không được đọc tài liệu của tenant khác. Vì vậy, pipeline cần định danh job ổn định, trạng thái bền vững, idempotency, retry có giới hạn, dead-letter queue, kiểm soát concurrency và quan sát xuyên suốt.

Bài học xây dựng một kiến trúc end-to-end dùng object storage, queue và Java worker; mô tả contract giữa các thành phần, triển khai các bước xử lý, xử lý lỗi và bảo mật, rồi vận hành pipeline với scaling, monitoring và cost controls.

## 1. Mục tiêu và phạm vi dự án

Xây dựng một dịch vụ nhận tài liệu và xử lý nền. Người dùng có thể tải PDF, ảnh hoặc tài liệu văn phòng lên storage; hệ thống kiểm tra file, trích xuất text/OCR, chuẩn hóa metadata và tạo kết quả để caller truy vấn.

Các mục tiêu kỹ thuật:

- API tiếp nhận yêu cầu nhanh và không chờ toàn bộ quá trình xử lý.
- File được lưu bền vững trong object storage.
- Storage event khởi tạo pipeline thông qua queue.
- Java worker xử lý theo từng bước độc lập.
- Trạng thái job được lưu trong database để phục hồi sau restart.
- Duplicate delivery không tạo tác dụng phụ nghiệp vụ lặp.
- Retry và DLQ cô lập lỗi tạm thời và poison document.
- Quyền truy cập, tenant isolation và dữ liệu nhạy cảm được kiểm soát.
- Có metric, log, trace và cost attribution theo job.
- Worker scale theo backlog nhưng không làm quá tải database hoặc dịch vụ OCR/AI.

Phạm vi này phù hợp với Java serverless function xử lý HTTP, message và storage event. Provider cụ thể có thể là Amazon S3/SQS/Lambda, Google Cloud Storage/Pub/Sub/Cloud Run functions hoặc Azure Blob Storage/Queue/Functions. Tên cấu hình khác nhau, nhưng các nguyên tắc về identity, durability, idempotency và backpressure vẫn tương tự.

## 2. Kiến trúc tổng thể

~~~mermaid
flowchart TD
    Client[Web / mobile client]
    API[Java upload API]
    DB[(Job database)]
    Storage[(Object storage: quarantine)]
    Event[Storage event notification]
    Router[Event adapter / router]
    Queue[Work queue]
    Worker[Java document worker]
    Scan[Malware and file validation]
    Extract[Text extraction / OCR]
    Process[Business enrichment]
    Result[(Processed object storage)]
    Status[Job status API]
    DLQ[Dead-letter queue]

    Client --> API
    API --> DB
    API -->|Presigned upload URL| Client
    Client -->|Upload bytes| Storage
    Storage --> Event --> Router --> Queue
    Queue --> Worker
    Worker --> Scan --> Extract --> Process
    Process --> Result
    Worker --> DB
    Worker -->|Retry exhausted| DLQ
    Client --> Status --> DB
~~~

Các thành phần và trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Upload API | Xác thực caller, tạo job, cấp upload URL có giới hạn |
| Object storage | Lưu file gốc và kết quả với versioning/encryption |
| Storage event adapter | Chuẩn hóa notification thành event contract nội bộ |
| Queue | Buffer công việc, điều tiết tải và giao lại khi xử lý thất bại |
| Java worker | Claim job, đọc object, xử lý từng stage và lưu kết quả |
| Job database | Lưu state, lease, attempt, object reference và error |
| Result storage | Lưu text/OCR output hoặc artifact lớn |
| Status API | Cho caller xem tiến độ và tải kết quả sau khi kiểm tra quyền |
| DLQ | Cách ly message không thể xử lý sau retry policy |

Storage event không nên chứa toàn bộ file. Event chỉ mang reference và metadata cần thiết; worker đọc bytes trực tiếp từ storage bằng workload identity.

## 3. Luồng nghiệp vụ từ upload đến kết quả

Luồng cơ bản:

1. Caller gọi API tạo document job.
2. API xác thực caller, xác định tenant từ identity tin cậy và tạo job ở trạng thái UPLOAD_PENDING.
3. API cấp presigned URL hoặc cơ chế upload có giới hạn vào quarantine prefix.
4. Caller upload file trực tiếp lên object storage.
5. Storage phát object-created event.
6. Event adapter kiểm tra event và gửi message chuẩn hóa vào queue.
7. Java worker nhận message, kiểm tra job và object version, rồi claim stage.
8. Worker xác thực file, quét malware, trích xuất text/OCR và thực hiện enrichment.
9. Worker lưu output, cập nhật trạng thái và tạo event cho stage tiếp theo nếu cần.
10. Status API trả kết quả hoặc trạng thái terminal.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java Upload API
    participant D as Job DB
    participant S as Object Storage
    participant Q as Queue
    participant W as Java Worker

    C->>A: POST /documents
    A->>D: Create UPLOAD_PENDING job
    A-->>C: 201 jobId + uploadUrl
    C->>S: PUT file using uploadUrl
    S-->>Q: ObjectCreated event
    Q->>W: DocumentUploaded message
    W->>D: Claim validation stage
    W->>S: Read exact object version
    W->>W: Scan, extract, process
    W->>S: Write result artifact
    W->>D: Commit stage + SUCCEEDED
    C->>A: GET /documents/{jobId}
    A->>D: Read status
    D-->>A: SUCCEEDED + resultRef
    A-->>C: 200 result metadata
~~~

Tạo job trước khi cấp upload URL giúp worker luôn có record để xác thực event. Nếu upload thất bại hoặc caller bỏ dở, job vẫn ở UPLOAD_PENDING và có thể hết hạn theo cleanup policy.

## 4. API contract cho upload và status

API nên tách việc tạo upload session khỏi upload bytes. File lớn không nên đi qua Java function nếu object storage hỗ trợ upload trực tiếp.

Tạo document:

~~~http
POST /v1/documents
Authorization: Bearer <access-token>
Idempotency-Key: 6f40b5...
Content-Type: application/json

{
  "fileName": "invoice-2026-041.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 284100,
  "checksumSha256": "optional-client-checksum"
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /v1/documents/doc-918

{
  "documentId": "doc-918",
  "status": "UPLOAD_PENDING",
  "upload": {
    "method": "PUT",
    "url": "https://storage.example/short-lived-signed-url",
    "expiresAt": "2026-11-17T10:10:00Z",
    "requiredHeaders": {
      "Content-Type": "application/pdf"
    }
  }
}
~~~

API cần giới hạn thời gian sống, method, object key, content length và checksum nếu provider hỗ trợ. Không cho caller tự chọn bucket, tenant prefix hoặc object key tùy ý.

Truy vấn trạng thái:

~~~http
GET /v1/documents/doc-918
Authorization: Bearer <access-token>
~~~

Response đang xử lý:

~~~json
{
  "documentId": "doc-918",
  "status": "EXTRACTING",
  "createdAt": "2026-11-17T10:00:00Z",
  "updatedAt": "2026-11-17T10:01:22Z",
  "progress": {
    "stage": "TEXT_EXTRACTION",
    "completedUnits": 2,
    "totalUnits": 4
  }
}
~~~

Response hoàn tất:

~~~json
{
  "documentId": "doc-918",
  "status": "SUCCEEDED",
  "result": {
    "contentType": "application/json",
    "url": "/v1/documents/doc-918/result"
  }
}
~~~

Status API phải kiểm tra tenant và quyền trên document trước khi trả metadata hoặc result URL. Biết document ID không có nghĩa caller được phép đọc tài liệu.

## 5. Object key và tổ chức storage

Không dùng tên file do người dùng gửi làm object key trực tiếp. Tên file có thể chứa path traversal, ký tự đặc biệt, dữ liệu cá nhân hoặc bị trùng.

Một cấu trúc key tham khảo:

~~~text
quarantine/{tenantOpaqueId}/{documentId}/{uploadId}/source
processed/{tenantOpaqueId}/{documentId}/{pipelineVersion}/extracted.json
processed/{tenantOpaqueId}/{documentId}/{pipelineVersion}/preview.pdf
~~~

Nguyên tắc:

- Dùng ID opaque do backend tạo.
- Tách quarantine và processed prefix hoặc bucket theo trust boundary.
- Bật versioning hoặc ghi rõ object version ID trong job.
- Bật encryption at rest và TLS.
- Không public bucket/container.
- Không dùng object key như bằng chứng authorization.
- Lưu original filename như metadata đã làm sạch trong database.
- Đặt lifecycle policy cho file tạm và kết quả theo retention.
- Dùng checksum để phát hiện upload thiếu hoặc hỏng.

Nếu bật versioning, worker nên đọc đúng version đã phát sinh event. Nếu chỉ đọc key hiện tại, một upload mới có thể ghi đè key trước khi worker xử lý, khiến event cũ đọc nhầm bytes mới.

### Quarantine trước khi xử lý

File mới upload cần được coi là untrusted. Đặt file vào quarantine prefix; chỉ chuyển sang processed/approved prefix sau khi kiểm tra thành công. Worker cần quyền đọc quarantine và ghi output riêng. API caller không nên có quyền ghi trực tiếp vào processed prefix.

Copy object sang prefix approved không tự làm file an toàn; chỉ thực hiện sau khi validation, malware scan và policy checks hoàn tất.

## 6. Storage event và chuẩn hóa message

Provider storage notification có schema khác nhau. Nên có một adapter chuẩn hóa thành contract nội bộ để worker không phụ thuộc trực tiếp vào từng provider.

Message nội bộ ví dụ:

~~~json
{
  "schemaVersion": 1,
  "eventId": "storage-event-72c1",
  "eventType": "document.uploaded",
  "occurredAt": "2026-11-17T10:00:12Z",
  "documentId": "doc-918",
  "object": {
    "bucket": "document-quarantine",
    "key": "quarantine/t-42/doc-918/up-1/source",
    "versionId": "3Lg...x9",
    "etag": "provider-etag",
    "sizeBytes": 284100,
    "checksumSha256": "..."
  }
}
~~~

Queue payload nên nhỏ, không nhúng file bytes hoặc nội dung tài liệu. Worker dùng object reference để đọc file. Với file lớn, payload chỉ nên chứa document ID, object version và metadata cần thiết.

### Tin cậy event source

Không lấy tenant ID từ message làm nguồn quyền duy nhất. Worker tra document record theo documentId, kiểm tra object reference có khớp bucket/key/version đã cấp cho job hay không, rồi lấy tenant và classification từ database.

Event adapter cần xác thực nguồn phát nếu provider hỗ trợ resource policy, service identity hoặc signed event. Không cho Internet caller gửi trực tiếp một message giả vào queue.

## 7. Event delivery có thể lặp và sai thứ tự

Object storage notifications và queue thường có semantics giao ít nhất một lần hoặc có thể phát lại. Cùng object event có thể đến nhiều lần. Sự kiện upload cũ cũng có thể đến sau sự kiện mới nếu một key được ghi nhiều lần.

Thiết kế phải xử lý:

- Duplicate notification.
- Event đến chậm.
- Event out-of-order.
- Queue redelivery sau visibility/ack timeout.
- Worker crash sau khi ghi output nhưng trước khi ACK.
- Upload multipart chỉ được coi là hoàn tất khi provider phát sự kiện phù hợp.
- Delete event hoặc overwrite event không bị hiểu nhầm thành upload mới.

Dùng object version ID hoặc upload ID để xác định đúng input. Nếu versioning không có, tạo object key duy nhất cho mỗi upload session để tránh overwrite. Đừng chỉ dùng ETag làm checksum SHA-256; semantics ETag thay đổi theo provider và multipart upload.

## 8. Job database và state machine

Job database là nguồn trạng thái chuẩn. Queue chỉ mang yêu cầu xử lý; không nên là nơi duy nhất lưu trạng thái tiến độ.

Schema tham khảo:

~~~sql
CREATE TABLE document_jobs (
    document_id       VARCHAR(128) PRIMARY KEY,
    tenant_id         VARCHAR(128) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    source_bucket     VARCHAR(256) NULL,
    source_key        TEXT NULL,
    source_version    VARCHAR(256) NULL,
    source_checksum   VARCHAR(128) NULL,
    pipeline_version  VARCHAR(64) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(128) NULL,
    lease_until       TIMESTAMP NULL,
    lease_generation  BIGINT NOT NULL DEFAULT 0,
    result_ref        TEXT NULL,
    error_code        VARCHAR(64) NULL,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP NULL
);
~~~

State machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> UPLOAD_PENDING
    UPLOAD_PENDING --> UPLOADED
    UPLOADED --> VALIDATING
    VALIDATING --> EXTRACTING
    EXTRACTING --> PROCESSING
    PROCESSING --> SUCCEEDED
    VALIDATING --> RETRY_WAIT
    EXTRACTING --> RETRY_WAIT
    PROCESSING --> RETRY_WAIT
    RETRY_WAIT --> VALIDATING
    VALIDATING --> REJECTED
    EXTRACTING --> FAILED
    PROCESSING --> FAILED
    UPLOAD_PENDING --> EXPIRED
~~~

Ý nghĩa trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| UPLOAD_PENDING | Đã tạo upload session, chưa nhận file hoàn chỉnh |
| UPLOADED | Object đã được xác minh và gắn với job |
| VALIDATING | Kiểm tra file type, size, checksum và malware |
| EXTRACTING | Trích xuất text hoặc OCR |
| PROCESSING | Enrichment, phân loại hoặc xử lý nghiệp vụ |
| RETRY_WAIT | Chờ retry sau lỗi tạm thời |
| SUCCEEDED | Kết quả đã lưu bền vững |
| REJECTED | File không đáp ứng policy hoặc không an toàn |
| FAILED | Lỗi terminal hoặc retry đã hết |
| EXPIRED | Upload session hết hạn mà không có object hợp lệ |

Với pipeline nhiều stage, có thể lưu parent job cùng bảng stage executions. Như vậy một stage thất bại không làm mất trạng thái của các stage đã hoàn tất.

## 9. Idempotency và inbox cho Java worker

Worker có thể nhận cùng message nhiều lần. Deduplicate theo một identity ổn định, chẳng hạn:

~~~text
consumerName + documentId + pipelineVersion + stage + sourceVersion
~~~

Ví dụ bảng inbox:

~~~sql
CREATE TABLE document_inbox (
    consumer_name     VARCHAR(128) NOT NULL,
    document_id       VARCHAR(128) NOT NULL,
    pipeline_version  VARCHAR(64) NOT NULL,
    stage             VARCHAR(64) NOT NULL,
    source_version    VARCHAR(256) NOT NULL,
    payload_hash      VARCHAR(128) NOT NULL,
    processed_at      TIMESTAMP NULL,
    PRIMARY KEY (
        consumer_name,
        document_id,
        pipeline_version,
        stage,
        source_version
    )
);
~~~

Nếu business update nằm trong cùng database, ghi inbox và cập nhật trạng thái stage trong một transaction. Nếu worker phải chạy lâu hoặc gọi service ngoài, dùng claim/lease và fencing token. Không dùng static Set hoặc local cache làm deduplication chuẩn vì serverless scale-out tạo nhiều execution environment độc lập.

Một duplicate đã hoàn tất có thể được ACK mà không chạy lại side effect. Nếu một worker khác đang giữ lease, chỉ ACK duplicate khi có recovery process bảo đảm lease hết hạn sẽ được quét và enqueue lại; nếu không, hãy để message retry theo policy.

### Kết quả ghi ra storage

Object storage và database không có transaction chung. Dùng output key deterministic theo document, stage, pipeline version và input version. Nếu worker crash sau khi ghi object nhưng trước khi commit DB, lần chạy sau có thể xác minh object đó và tiếp tục commit. Orphan output cần lifecycle/garbage collection.

Không ghi đè result của pipeline version mới bằng worker cũ. Dùng immutable key và fencing/version check trước khi cập nhật result_ref.

## 10. Claim job bằng lease và fencing token

Một worker có thể bị timeout khi đang OCR hoặc gọi AI. Nếu job mãi ở RUNNING, không ai tiếp tục được. Lease giúp một worker khác reclaim sau khi lease hết hạn.

Khi claim:

- Dùng conditional update hoặc row lock để chỉ một worker thắng.
- Ghi lease owner và lease_until.
- Tăng lease_generation làm fencing token.
- Gia hạn lease khi stage còn chạy.
- Chỉ cho owner với generation hiện tại cập nhật trạng thái.
- Sweeper tìm lease hết hạn để enqueue lại hoặc đánh dấu cần reconciliation.

Không chỉ kiểm tra timestamp trong Java rồi update. Việc claim phải atomic tại database. Dùng thời gian database để tránh lệch clock giữa các execution environment.

Nếu worker cũ tỉnh lại sau khi lease đã được cấp cho worker mới, fencing token ngăn worker cũ ghi đè trạng thái mới. Downstream side effect cũng cần idempotency hoặc version condition.

## 11. Java worker: message contract và handler

Một message có thể được biểu diễn bằng record:

~~~java
public record DocumentUploaded(
        int schemaVersion,
        String eventId,
        String documentId,
        String bucket,
        String objectKey,
        String versionId,
        String checksumSha256) {}
~~~

Handler minh họa theo hướng framework-neutral:

~~~java
public final class DocumentWorker {

    private final JobRepository jobs;
    private final ObjectStore objectStore;
    private final DocumentPipeline pipeline;
    private final ResultStore results;
    private final TransactionRunner transactions;
    private final OutboxRepository outbox;

    public DocumentWorker(
            JobRepository jobs,
            ObjectStore objectStore,
            DocumentPipeline pipeline,
            ResultStore results,
            TransactionRunner transactions,
            OutboxRepository outbox) {
        this.jobs = jobs;
        this.objectStore = objectStore;
        this.pipeline = pipeline;
        this.results = results;
        this.transactions = transactions;
        this.outbox = outbox;
    }

    public void handle(DocumentUploaded message) {
        DocumentJob job = jobs.require(message.documentId());
        verifyObjectReference(job, message);

        Claim claim = jobs.tryClaim(
                job.documentId(),
                "VALIDATE_AND_PROCESS",
                workerIdentity(),
                leaseDuration());

        if (claim.completed()) {
            return; // Duplicate of a completed stage.
        }
        if (!claim.acquired()) {
            throw new RetryableProcessingException(
                    "Stage is owned by another worker");
        }

        try {
            StoredObject source = objectStore.get(
                    message.bucket(),
                    message.objectKey(),
                    message.versionId());

            ProcessingResult result = pipeline.process(source, job);

            String resultRef = results.putImmutable(
                    job.documentId(),
                    job.pipelineVersion(),
                    message.versionId(),
                    result);

            transactions.execute(() -> {
                jobs.completeIfLeaseOwner(
                        job.documentId(),
                        claim.leaseGeneration(),
                        resultRef);

                outbox.insertDocumentProcessed(
                        job.documentId(),
                        resultRef);
            });
        } catch (PermanentDocumentException error) {
            jobs.rejectIfLeaseOwner(
                    job.documentId(),
                    claim.leaseGeneration(),
                    error.safeCode());
        } catch (Exception error) {
            jobs.releaseForRetryIfLeaseOwner(
                    job.documentId(),
                    claim.leaseGeneration(),
                    classify(error));
            throw new RetryableProcessingException(error);
        }
    }

    private void verifyObjectReference(
            DocumentJob job,
            DocumentUploaded message) {
        // Compare bucket, key and version with the upload session
        // recorded by the trusted API. Never trust tenant data
        // supplied only by the queue payload.
    }

    private String workerIdentity() {
        return "runtime-instance";
    }

    private Duration leaseDuration() {
        return Duration.ofMinutes(3);
    }

    private RetryDecision classify(Exception error) {
        return RetryDecision.from(error);
    }
}
~~~

Đây là skeleton minh họa; các interface và model cần được định nghĩa trong ứng dụng. Trong production, cần bảo đảm việc hoàn tất stage, ghi outbox và chuyển job state nằm trong cùng transaction. Nếu xử lý nhiều stage, mỗi stage có thể có worker/queue riêng thay vì một function làm tất cả.

Nếu message đến khi stage đang được worker khác xử lý, cách xử lý phụ thuộc recovery model. Có thể retry message hoặc ACK duplicate nếu sweeper bền vững sẽ phát lại job khi lease hết hạn. Không được ACK và bỏ qua khi không có cơ chế recovery.

## 12. Các bước xử lý tài liệu

Một pipeline an toàn nên tách bước kiểm tra file khỏi bước xử lý nghiệp vụ.

### Bước 1: Xác minh object

- Kiểm tra bucket/key/version khớp upload session.
- Kiểm tra kích thước thực tế và checksum.
- Kiểm tra content type dựa trên bytes/signature, không chỉ dựa extension.
- Giới hạn số trang, kích thước ảnh và tỷ lệ nén.
- Từ chối file rỗng hoặc vượt giới hạn.
- Ghi metadata của object vào job record.

### Bước 2: Malware scan và quarantine

- Quét malware bằng dịch vụ hoặc engine được phê duyệt.
- Không mở file bằng parser nghiệp vụ trước khi qua kiểm tra cần thiết.
- Cách ly file nghi ngờ.
- Lưu scan result, engine version và timestamp.
- Chỉ tiếp tục khi policy cho phép.

### Bước 3: Trích xuất nội dung

- PDF: trích xuất text; dùng OCR cho trang ảnh.
- Ảnh: OCR hoặc nhận diện loại tài liệu.
- DOCX: trích xuất nội dung và metadata.
- CSV: kiểm tra encoding, delimiter, row/column limit.
- Archive: giới hạn nesting, số entry và tổng kích thước giải nén.

### Bước 4: Chuẩn hóa và enrichment

- Chuẩn hóa Unicode và whitespace.
- Trích xuất metadata như invoice number hoặc date.
- Phân loại tài liệu.
- Kiểm tra schema/business rule.
- Có thể gọi AI model cho summary hoặc classification.
- Ghi confidence và model/prompt version nếu có AI.

### Bước 5: Lưu kết quả

- Lưu output lớn trong object storage.
- Lưu reference, checksum và metadata trong database.
- Chuyển job sang SUCCEEDED chỉ sau khi output đã bền vững.
- Phát document.processed event qua outbox nếu downstream cần.

## 13. Không tin filename, extension và MIME type

Caller có thể gửi filename là report.pdf trong khi bytes thực tế là executable hoặc archive. Content-Type header cũng do caller cung cấp và có thể giả mạo.

Cần kiểm tra nhiều lớp:

- File signature/magic bytes.
- Parser phù hợp với định dạng được allowlist.
- Kích thước trước và sau giải nén.
- Số trang, dimension ảnh, pixel count và recursion depth.
- Giới hạn CPU, memory và wall-clock time.
- Từ chối macro hoặc embedded object nếu nghiệp vụ không cần.
- Không thực thi script hoặc nội dung nhúng.
- Đặt parser trong runtime/container có quyền tối thiểu và resource limit.

### Zip bomb và parser exhaustion

Một file nén nhỏ có thể bung ra kích thước rất lớn hoặc chứa hàng triệu entry. Không chỉ kiểm tra compressed size; cần giới hạn expanded size, entry count, nesting depth và thời gian giải nén. Dừng xử lý khi vượt ngưỡng và ghi error code an toàn.

## 14. Chia stage hay dùng một worker?

Có thể triển khai một worker thực hiện toàn bộ pipeline hoặc chia thành nhiều stage.

| Thiết kế | Ưu điểm | Đánh đổi |
|---|---|---|
| Single worker | Ít thành phần, dễ triển khai cho pipeline ngắn | Timeout dài, retry lại nhiều công việc, scale theo stage khó |
| Multi-stage queues | Mỗi stage có timeout, memory và concurrency riêng | Cần state transition, outbox và correlation giữa stage |
| Workflow engine | Quản lý state, wait, branch, retry và callback | Có chi phí orchestration và giới hạn provider |
| Container job cho bước nặng | Phù hợp file lớn, CPU/RAM cao hoặc chạy lâu | Cần quản lý image, capacity và job runtime |

Một cách thực tế là bắt đầu với validation + extraction worker nếu tổng thời gian ngắn và dễ phục hồi. Khi OCR, AI enrichment hoặc conversion có profile tài nguyên khác nhau, tách stage để scale và giới hạn độc lập.

Không tách quá nhỏ đến mức mỗi thao tác đơn giản tạo một invocation, nhiều queue hop và nhiều lần ghi database không cần thiết.

## 15. Queue, retry và dead-letter queue

Queue hấp thụ burst và tách tốc độ upload khỏi tốc độ xử lý. Consumer concurrency cần được giới hạn theo database, OCR service và model provider capacity.

Retry policy:

- Lỗi transient như network timeout hoặc provider 429/503: retry có giới hạn.
- File sai định dạng hoặc malware: terminal reject/quarantine, không retry mù quáng.
- Database conflict: retry ngắn nếu transaction có thể chạy lại an toàn.
- Outcome chưa rõ sau khi gọi provider: tra cứu/idempotency trước khi gửi lại.
- Hết attempts hoặc elapsed deadline: chuyển DLQ hoặc FAILED theo policy.

Dùng capped exponential backoff với jitter. Không sleep nhiều phút trong function; lưu RETRY_WAIT và dùng queue delay, scheduler hoặc workflow timer.

### Visibility/ack timeout

Với queue có visibility timeout hoặc ack deadline, thời gian này phải đủ cho thời gian xử lý và cleanup theo semantics của provider. Nếu message xuất hiện lại trong khi worker cũ vẫn chạy, hai worker có thể cùng xử lý. Inbox/lease/fencing và idempotent output là lớp bảo vệ.

DLQ cần giữ đủ metadata để điều tra, nhưng không nên chứa dữ liệu nhạy cảm dư thừa. Redrive theo batch nhỏ, giữ nguyên document ID và object version, giới hạn tốc độ để tránh tạo burst mới.

## 16. Bảo mật và tenant isolation

Tài liệu thường chứa dữ liệu cá nhân, hợp đồng, hóa đơn hoặc thông tin nội bộ. Bảo mật phải được áp dụng xuyên suốt.

### Identity và quyền truy cập

- API xác thực caller và lấy tenant từ identity đáng tin cậy.
- Upload URL chỉ có quyền ghi đúng object key và thời hạn ngắn.
- Worker dùng workload identity riêng, không dùng credential nhúng.
- Worker chỉ đọc quarantine prefix cần thiết và ghi processed prefix.
- Status API lọc theo tenant và authorization policy.
- Queue policy chỉ cho phép storage event adapter hoặc publisher được duyệt.
- Result download dùng authorization hoặc URL ngắn hạn có scope.

### Data protection

- TLS khi truyền và encryption at rest.
- Key policy theo environment và data classification.
- Không ghi nội dung tài liệu vào log.
- Redact PII trong telemetry.
- Retention và deletion policy theo yêu cầu nghiệp vụ.
- Audit ai tải lên, ai đọc, ai tải kết quả và thời điểm.
- Tách bucket/key namespace hoặc access policy giữa tenant.
- Kiểm tra quyền ở backend, không dựa vào việc caller biết object key.

### Parser và SSRF

Nếu pipeline tải nội dung từ URL do caller cung cấp, cần chống SSRF: chặn loopback, private, link-local và metadata endpoint; kiểm tra DNS resolution và redirect; giới hạn scheme/port; hoặc chỉ cho phép domain đã đăng ký. Ưu tiên upload qua presigned URL do hệ thống tạo thay vì worker tự fetch URL tùy ý.

## 17. Quan sát pipeline end-to-end

Mỗi document job cần correlation identity ổn định. Dùng documentId/jobId để nối API, storage event, queue message, worker stage và result. Propagate trace context qua message attributes nếu hỗ trợ.

Metric gợi ý:

| Metric | Mục đích |
|---|---|
| Upload accepted/rejected | Theo dõi trải nghiệm upload |
| Queue depth và oldest message age | Đo backlog |
| Stage duration p50/p95/p99 | Tìm stage chậm |
| End-to-end completion time | Đo SLO người dùng |
| Worker concurrency/throttle | Theo dõi capacity |
| Retry count và DLQ depth | Phát hiện lỗi xử lý |
| Lease expiry/stuck RUNNING | Phát hiện worker chết hoặc bị treo |
| Malware/validation rejection | Theo dõi file không hợp lệ |
| Object read/write errors | Phát hiện storage issue |
| Database pool wait | Phát hiện DB bottleneck |
| Cost per successful document | Theo dõi unit economics |

Log có cấu trúc nên có documentId, stage, attempt, pipelineVersion, objectVersion và errorCode. Không dùng documentId, tenantId hoặc object key làm metric labels cardinality cao; dùng log/trace để drill down.

Dashboard nên phân biệt queue wait, validation, extraction, enrichment và persistence. Nếu chỉ đo tổng thời gian, khó tìm bottleneck.

### SLO cho pipeline

Một SLI có thể là tỷ lệ document hợp lệ được xử lý thành công trong thời gian mục tiêu:

~~~text
Completion SLI =
  eligible documents completed within deadline
  / eligible documents accepted
~~~

Ví dụ SLO minh họa: 99% tài liệu hợp lệ dưới 20 MB hoàn tất trong 3 phút trong rolling 30 ngày. Định nghĩa phải nói rõ file nào eligible, cách tính tài liệu bị reject, thời điểm bắt đầu và kết quả terminal.

## 18. Scaling và backpressure

Worker có thể scale theo queue backlog, nhưng scale vô hạn có thể làm cạn database connections hoặc vượt OCR/model API quota.

Cần đặt:

- Maximum worker concurrency.
- Batch size phù hợp memory.
- Per-tenant rate limit.
- Global provider rate limit.
- Database connection budget.
- Queue retention và maximum age.
- Admission control cho upload/job creation.
- Separate queues cho loại tài liệu có tài nguyên khác nhau.

Nếu queue age tăng trong khi worker đã chạm max concurrency, cần kiểm tra processing throughput và downstream saturation trước khi tăng giới hạn. Nếu database connection wait tăng, tăng worker concurrency có thể làm tình hình tệ hơn.

Có thể tách queue theo workload class: small text documents, large PDF/OCR, AI enrichment. Mỗi queue có worker configuration và concurrency cap riêng.

## 19. Cost model

Tổng chi phí một document có thể gồm:

~~~text
Cost per document =
  storage write/read + retained bytes
  + queue/event operations
  + Java worker compute
  + OCR/AI provider usage
  + database reads/writes
  + network transfer
  + logs/metrics/traces
  + retry and duplicate processing
~~~

Các yếu tố cần đo:

- File size và thời gian lưu source/result.
- Số lần đọc/ghi object.
- Worker memory/duration.
- Số queue messages và stage transitions.
- OCR pages hoặc AI input/output tokens.
- Retry rate và DLQ redrive.
- Egress và cross-region transfer.
- Observability volume.

Tối ưu bằng cách không truyền file qua queue, dùng object reference; chọn memory theo benchmark; batch thao tác nhỏ khi phù hợp; tránh OCR/AI lặp khi retry; lifecycle file tạm; và theo dõi cost per successful document thay vì chỉ cost per invocation.

Không xóa source ngay khi worker hoàn tất nếu yêu cầu audit, replay hoặc retention cần giữ file. Deletion policy phải khớp contract và compliance.

## 20. Provider mapping

| Nền tảng | Storage | Queue/event | Java compute |
|---|---|---|---|
| AWS | S3 | SQS, EventBridge, S3 notifications | Lambda |
| Google Cloud | Cloud Storage | Pub/Sub, Eventarc | Cloud Run functions / Cloud Run |
| Azure | Blob Storage | Queue Storage, Service Bus, Event Grid | Azure Functions |

Mapping này chỉ là lựa chọn kiến trúc tương đương. Cần xác minh event delivery, retry, ordering, dead-letter, identity và timeout theo provider/service generation cụ thể. Không giả định mọi storage notification có cùng semantics.

Một số provider có thể giao trực tiếp storage event đến function; vẫn nên dùng queue hoặc event bus khi cần buffering, retry control, fan-out hoặc tách producer khỏi consumer.

## 21. Kiểm thử pipeline

Kiểm thử không chỉ là upload một PDF rồi thấy status SUCCEEDED. Cần kiểm tra failure window và tải.

| Tình huống | Kết quả mong đợi |
|---|---|
| Upload hợp lệ | Tạo job, storage event và xử lý thành công |
| Upload URL hết hạn | Storage từ chối upload |
| Upload quá size | Bị chặn ở upload policy hoặc validation |
| MIME giả mạo | Content sniffing phát hiện và reject |
| Storage event duplicate | Chỉ một stage tạo side effect |
| Event sai thứ tự | Worker xác minh đúng object version |
| Worker crash trước DB commit | Transaction rollback và message retry |
| Worker crash sau output write | Retry dùng output identity ổn định, không ghi đè kết quả mới |
| Queue redelivery | Inbox/lease ngăn xử lý đồng thời sai |
| Database unavailable | Retry có giới hạn, backlog được giữ |
| OCR/provider 429 | Backoff và giới hạn concurrency |
| File malware | Quarantine, không đưa sang processed |
| Zip bomb/huge page count | Dừng theo resource limit |
| Tenant khác truy vấn job | Không trả metadata/result |
| Lease hết hạn | Sweeper reclaim hoặc enqueue lại |
| DLQ redrive | Giữ document ID và source version |
| Storage version mới xuất hiện | Job cũ vẫn đọc đúng version đã ghi nhận |
| Retention hết hạn | Lifecycle xóa đúng object theo policy |

### Load và recovery test

- Ramp-up upload rate để xác định throughput worker.
- Spike test để kiểm tra queue buffer và scale-out.
- Soak test để tìm memory leak hoặc parser resource leak.
- Dừng worker giữa các stage.
- Làm database chậm và provider rate limit.
- Tạo backlog rồi đo thời gian drain.
- Redrive một batch DLQ nhỏ.
- Khôi phục database/object reference trong môi trường test và xác minh consistency.

Không chạy thử file độc hại thực trên production. Dùng test fixture an toàn và môi trường cô lập.

## 22. Triển khai và vận hành

Một lộ trình triển khai thực tế:

1. Tạo bucket/container quarantine và processed với encryption, versioning và lifecycle.
2. Tạo job database và schema migration.
3. Tạo upload API với authentication, tenant scope, idempotency và signed URL.
4. Cấu hình storage event chỉ phát từ đúng bucket/prefix.
5. Đưa event vào queue có retention, retry và DLQ.
6. Deploy Java worker với workload identity và concurrency cap.
7. Tạo inbox/lease/outbox và sweeper cho job bị kẹt.
8. Tạo status/result API với authorization.
9. Cấu hình dashboard, alert và trace propagation.
10. Kiểm thử duplicate, timeout, malformed file và redrive.
11. Canary theo tenant hoặc tỷ lệ traffic.
12. Theo dõi queue age, completion SLO, provider quota và cost.
13. Rà soát retention, access log và deletion policy định kỳ.

Nên dùng Infrastructure as Code để version hóa bucket, queue, policy, role, function và alarm. Mỗi environment có config riêng; không dùng cùng bucket/queue production cho test.

## 23. Những lỗi thiết kế thường gặp

- **Gửi file bytes qua queue:** tăng payload, chi phí và rủi ro giới hạn message; gửi object reference.
- **Dùng filename làm object key:** dễ collision và path manipulation; dùng opaque document ID.
- **Đọc key hiện tại thay vì object version:** worker có thể đọc nhầm file bị overwrite; pin version.
- **Tin Content-Type do client gửi:** file giả định dạng; kiểm tra signature và parser.
- **Trả 202 trước khi tạo job bền vững:** công việc có thể mất; commit job trước khi trả.
- **Không xử lý storage event duplicate:** worker chạy lặp; dùng inbox và idempotency.
- **ACK trước khi commit state:** message có thể mất; commit trước ACK.
- **Không có lease recovery:** job RUNNING bị kẹt; dùng lease và sweeper.
- **Ghi output và DB không có chiến lược:** tạo orphan hoặc state sai; dùng immutable output key, transaction và cleanup.
- **Scale worker không giới hạn:** làm quá tải DB/OCR provider; đặt concurrency và rate limit.
- **Đưa file độc hại vào parser:** có thể gây exploit/resource exhaustion; quarantine và scan.
- **Không giới hạn giải nén/OCR:** zip bomb hoặc file nhiều trang gây cạn tài nguyên; đặt hard limits.
- **Dùng queue làm nguồn trạng thái:** khó trả progress và phục hồi; dùng database.
- **Không có DLQ/redrive:** poison message lặp vô hạn; quarantine và quy trình xử lý.
- **Không kiểm tra tenant trên status/result:** lộ tài liệu giữa khách hàng; authorize mọi request.
- **Log payload đầy đủ:** rò rỉ dữ liệu; log metadata đã redacted.

## 24. Quy trình xây dựng pipeline Java serverless

1. Xác định document type, size limit, retention và completion SLO.
2. Thiết kế API tạo upload session và idempotency key.
3. Tạo job record trước khi cấp signed upload URL.
4. Lưu file vào quarantine với object key opaque và versioning.
5. Nhận storage event, chuẩn hóa thành message schema có version.
6. Đưa message vào queue và giữ payload nhỏ.
7. Worker tra job record, xác minh object reference và claim stage.
8. Validate bytes, checksum, malware và resource limits.
9. Extract/OCR và xử lý nghiệp vụ theo stage.
10. Ghi output immutable, cập nhật state và outbox trong transaction phù hợp.
11. ACK message sau khi state bền vững.
12. Retry lỗi transient; reject/quarantine lỗi permanent; dùng DLQ cho message exhausted.
13. Dùng lease/fencing và sweeper để phục hồi worker chết.
14. Bảo vệ tenant, secret, network và result access.
15. Theo dõi end-to-end latency, queue age, retry, DLQ và cost per successful document.
16. Load test, fault injection và kiểm thử redrive trước production.

## 25. Ghi nhớ

Pipeline tài liệu serverless tách upload, lưu trữ, điều phối và xử lý. Object storage giữ file bền vững; storage event thông báo có object mới; queue hấp thụ burst và giao công việc; Java worker thực hiện validation, scan, extraction và enrichment; database giữ trạng thái job; result storage lưu output.

Thiết kế phải giả định event/message có thể lặp, sai thứ tự và worker có thể dừng ở bất kỳ thời điểm nào. Dùng object version, event identity, inbox/idempotency, lease/fencing, immutable output và retry/DLQ để phục hồi an toàn. Chỉ ACK sau khi trạng thái cần thiết đã commit.

Bảo mật tài liệu từ lúc upload đến lúc tải kết quả: quarantine, content validation, malware scan, tenant authorization, encryption, retention và log redaction. Giới hạn worker concurrency theo database và provider capacity; quan sát queue age và completion SLO để điều tiết tải. Khi các thành phần có contract rõ ràng và state bền vững, pipeline có thể scale theo nhu cầu mà vẫn kiểm soát được tính đúng đắn, bảo mật và chi phí.

