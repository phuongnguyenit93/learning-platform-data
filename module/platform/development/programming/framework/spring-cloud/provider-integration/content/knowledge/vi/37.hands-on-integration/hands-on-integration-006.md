# Mô phỏng lỗi quyền, timeout, thông điệp trùng và phục hồi

## 1. Mục tiêu bài thực hành

Bài lab xây dựng và kiểm thử một workflow Spring Boot tích hợp object storage, queue và relational database. Trong quá trình chạy, ta chủ động tạo ba nhóm lỗi thường gặp:

1. **Lỗi quyền (AccessDenied):** workload không có quyền đọc object hoặc publish/consume message.
2. **Timeout:** thao tác gọi storage/database/queue vượt quá thời hạn client hoặc thời hạn xử lý message.
3. **Thông điệp trùng (duplicate delivery):** cùng một event được giao nhiều lần và có thể khiến nghiệp vụ bị thực hiện lặp.

Sau mỗi lỗi, ta quan sát log/metric, xác định đúng identity và transaction boundary, sửa nguyên nhân rồi phục hồi công việc. Mục tiêu là chứng minh hệ thống có thể tiếp tục sau lỗi mà không làm mất công việc đã xác nhận hoặc tạo side effect nghiệp vụ trùng.

Bài học thuộc module **Spring Cloud Provider Integration**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Các ví dụ dùng một workflow chung, sau đó đối chiếu cơ chế quyền, timeout và message settlement của từng provider.

Kết quả cần đạt:

- Nhận diện được caller identity, worker identity và service identity đang gây lỗi.
- Phân biệt lỗi authorization với lỗi network, timeout hoặc resource not found.
- Đặt timeout theo từng lớp và đồng bộ với queue visibility/lock/ack deadline.
- Xử lý duplicate bằng event ID, unique constraint và idempotent side effect.
- Biết khi nào retry, khi nào chuyển DLQ và khi nào cần operator intervention.
- Replay một message sau khi sửa lỗi mà vẫn giữ correlation/event ID.
- Dùng test tự động để tái hiện và xác minh recovery.

## 2. Kịch bản và kiến trúc lab

### 2.1. Kịch bản Document Processing

Một API nhận tài liệu, lưu file vào object storage, ghi metadata và phát event `document.stored`. Worker nhận event, tải đúng object version, tính checksum, xử lý file, lưu kết quả và cập nhật database.

~~~mermaid
flowchart LR
    C["Client"] --> API["Spring Boot Upload API"]
    API --> S[("Object Storage")]
    API --> DB[("Metadata DB")]
    DB --> O["Outbox"]
    O --> R["Outbox Relay"]
    R --> Q[["Queue"]]
    Q --> W["Spring Boot Worker"]
    W --> S
    W --> DB
    W --> P["Document Processor"]
    P --> S
    W --> DLQ[["Dead-letter Queue"]]
~~~

Luồng bình thường:

1. API tạo upload intent và object key ngẫu nhiên.
2. Client/backend upload file lên bucket/container.
3. API xác minh object key, version/generation, size và checksum.
4. Một DB transaction chuyển document sang `STORED` và ghi outbox event.
5. Relay publish event lên queue.
6. Worker nhận message, kiểm tra document state và tải object.
7. Worker xử lý và lưu kết quả theo object key deterministic.
8. DB transaction ghi inbox/event ID, cập nhật `PROCESSED` và outbox event kế tiếp nếu có.
9. Worker ack/delete/complete message sau khi transaction commit.

Queue message chỉ mang `eventId`, `documentId`, `objectKey`, `objectVersion`, checksum và correlation ID. Không gửi file bytes, access token hoặc pre-signed URL trong message.

### 2.2. Thành phần và ranh giới lỗi

| Thành phần | Trách nhiệm | Lỗi sẽ mô phỏng |
| --- | --- | --- |
| Upload API | Tạo intent, upload, finalize metadata | Object PUT denied/timeout |
| Outbox relay | Publish event sau DB commit | Queue Send/Publish denied/timeout |
| Worker | Nhận message, tải object và xử lý | Object GET denied/timeout |
| Database | Metadata, outbox, inbox, lease | Connection/query timeout, unique conflict |
| Queue | Buffer, delivery, visibility/lock, DLQ | Redelivery, lock expiry, poison message |
| Reconciliation job | Tìm trạng thái chưa hoàn tất | Phục hồi orphan/outbox/lease |

Không dùng một identity toàn quyền cho mọi thành phần. API, relay và worker cần quyền riêng theo hành động và resource.

### 2.3. Provider mapping cho lab

| Chức năng | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object storage | S3 | Blob Storage | Cloud Storage |
| Queue | SQS | Service Bus Queue | Pub/Sub subscription |
| Database | RDS/Aurora | Azure Database for PostgreSQL/SQL | Cloud SQL |
| Workload identity | Task role, Pod Identity/IRSA, instance role | Managed Identity/Workload Identity | Service account, Workload Identity |
| Dead letter | SQS DLQ/redrive | Service Bus DLQ | Dead-letter topic/subscription policy |
| Object version | S3 VersionId | Blob version ID | GCS generation |

Các provider không có cùng semantics. Đặc biệt, message visibility/lock/ack deadline, event retry và IAM/RBAC action phải được kiểm tra theo đúng dịch vụ đang dùng.

## 3. Chuẩn bị môi trường và dữ liệu thử

### 3.1. Cấu hình ứng dụng

Ví dụ cấu hình khái niệm cho Spring Boot:

~~~yaml
app:
  document:
    bucket: lab-documents
    source-prefix: source/
    result-prefix: processed/
  queue:
    name: document-processing
    dlq-name: document-processing-dlq
    max-attempts: 5
  processing:
    object-read-timeout: 3s
    overall-timeout: 20s
    lease-duration: 30s
~~~

Các property trên là cấu hình application tự định nghĩa, không phải property chuẩn của Spring Cloud. Map chúng sang AWS SDK, Azure SDK, Google Cloud client và queue adapter của dự án. Không đưa credential vào YAML.

Dùng profile riêng cho lab và staging. Fault injection phải bị vô hiệu hóa ở production; không cho client request tùy ý bật lỗi trong runtime thật.

### 3.2. Event mẫu

~~~json
{
  "eventId": "evt-doc-1001-v1",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "tenantId": "tenant-42",
  "object": {
    "bucket": "lab-documents",
    "key": "source/doc-1001/upload-1.pdf",
    "version": "object-version-1",
    "checksumSha256": "expected-checksum"
  },
  "correlationId": "req-lab-001"
}
~~~

Event ID được tạo một lần và lưu trong outbox. Nếu relay publish lại sau timeout không rõ kết quả, nó phải dùng lại event ID cũ. Không tạo event ID mới cho mỗi lần retry.

### 3.3. Database schema tối thiểu

~~~sql
CREATE TABLE document (
    document_id       VARCHAR(100) PRIMARY KEY,
    tenant_id         VARCHAR(100) NOT NULL,
    object_key        VARCHAR(1024) NOT NULL,
    object_version    VARCHAR(256),
    checksum_sha256   VARCHAR(128),
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(128),
    lease_until       TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE processed_event (
    consumer_name     VARCHAR(128) NOT NULL,
    event_id          VARCHAR(128) NOT NULL,
    document_id       VARCHAR(100) NOT NULL,
    processed_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong hệ thống thật, bổ sung outbox, lease/fencing token, error category, created time, schema version, index cho state/lease và retention policy. Unique key `(consumer_name, event_id)` là hàng rào cuối cùng chống xử lý cùng event nhiều lần trong database.

### 3.4. Cách tạo lỗi an toàn

Có hai cách:

- **Test tự động:** thay adapter bằng fake/mock có thể phát lỗi `AccessDenied`, delay hoặc trả duplicate event. Cách này deterministic và phù hợp CI.
- **Staging cloud:** dùng một bucket/container/queue/database riêng và workload identity thử nghiệm có policy giới hạn. Thay policy, timeout hoặc message theo từng bài lab rồi khôi phục sau khi đo.

Không cố tình sửa IAM của production hoặc dùng credential admin để chạy lab. Trước mỗi thử nghiệm phải biết resource ARN/ID, identity và thao tác sẽ bị ảnh hưởng.

## 4. Instrumentation trước khi tạo lỗi

### 4.1. Correlation và log

Mỗi bước ghi log có cấu trúc với các trường:

- `correlationId`, `eventId`, `documentId`.
- `component`, `operation`, `attempt`.
- `principal` hoặc identity alias đã mask.
- `resource`/bucket/queue logical name.
- `durationMs`, `errorCategory`, `providerRequestId`.
- `messageDeliveryCount` hoặc receive count nếu provider cung cấp.

Không log authorization header, access key, SAS token, pre-signed URL hoặc file content. Log provider error code và request ID đủ để tra cứu nhưng phải loại bỏ secret.

### 4.2. Metrics

| Metric | Ý nghĩa |
| --- | --- |
| `storage_access_denied_total` | Số lần storage từ chối quyền |
| `queue_publish_failed_total` | Số lần publish thất bại |
| `dependency_timeout_total` | Timeout theo dependency |
| `document_processing_duration` | Thời gian xử lý document |
| `message_delivery_count` | Số lần message được giao |
| `duplicate_event_total` | Số event bị inbox chặn |
| `document_retry_total` | Số lần retry nghiệp vụ |
| `dlq_message_count` | Message trong DLQ |
| `outbox_oldest_age_seconds` | Tuổi event chưa publish |
| `expired_lease_total` | Số lease hết hạn |
| `reconciliation_repaired_total` | Số trạng thái được reconciliation sửa |

Không gắn `documentId`, object key hoặc event ID làm metric label vì cardinality không giới hạn. Dùng log/trace để tra cứu từng request.

### 4.3. Baseline trước fault injection

Chạy ít nhất một document thành công và lưu lại:

- Event ID, object version và checksum.
- State transitions từ `PENDING_UPLOAD` tới `PROCESSED`.
- Số lần message được giao.
- Thời gian upload, queue wait và processing.
- Log correlation giữa API, relay và worker.

Baseline giúp phân biệt lỗi do fault injection với lỗi cấu hình đã tồn tại trước đó.

## 5. Lab 1 — Mô phỏng lỗi quyền AccessDenied

### 5.1. Mục tiêu và triệu chứng

Tạo tình huống worker có quyền nhận message nhưng không có quyền đọc object source. Kết quả mong đợi:

- Queue giao message thành công.
- Worker bắt đầu xử lý và gọi object storage.
- Storage trả lỗi `AccessDenied` hoặc HTTP 403.
- Worker phân loại lỗi là authorization, ghi log/metric và không ack thành công.
- Message được retry theo policy hoặc chuyển DLQ nếu vượt giới hạn; không retry vô hạn.

Phân biệt identity: quyền `ReceiveMessage` không cấp quyền `GetObject`. Một worker có thể đọc queue nhưng không được đọc bucket.

### 5.2. Tạo lỗi trong unit/integration test

Định nghĩa exception ở application boundary:

~~~java
public class StorageAccessDeniedException extends RuntimeException {

    public StorageAccessDeniedException(String message) {
        super(message);
    }
}
~~~

Fake adapter có thể chủ động từ chối đọc:

~~~java
public class FaultInjectingObjectStore implements ObjectStore {

    private final ObjectStore delegate;
    private final FaultProfile faults;

    public FaultInjectingObjectStore(
            ObjectStore delegate,
            FaultProfile faults) {
        this.delegate = delegate;
        this.faults = faults;
    }

    @Override
    public InputStream get(ObjectKey key, String version) {
        if (faults.isEnabled("object-read-denied")) {
            throw new StorageAccessDeniedException(
                    "Simulated object read permission denied");
        }
        return delegate.get(key, version);
    }

    // Các phương thức put/head/delete ủy quyền cho delegate.
}
~~~

Đây là adapter test; triển khai thực tế cần implement đầy đủ interface `ObjectStore`. Chỉ đăng ký bean fault-injection trong profile `fault-lab` hoặc test configuration.

### 5.3. Tạo lỗi quyền trên AWS staging

Tạo bucket/prefix và role thử nghiệm riêng. Worker role cần được phép đọc queue nhưng thiếu quyền đọc object. Ví dụ policy giới hạn cho lab:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLabQueueReceive",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT_ID:document-processing-lab"
    },
    {
      "Sid": "DenyLabSourceRead",
      "Effect": "Deny",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::lab-documents/source/*"
    }
  ]
}
~~~

Gắn policy vào role của worker lab. Explicit deny chỉ áp dụng bucket/prefix lab; không chỉnh policy production. Nếu role có nhiều policy khác, explicit deny giúp kết quả thử nghiệm rõ vì deny ưu tiên allow.

### 5.3.1. Tạo lỗi quyền trên Azure staging

Tạo một Managed Identity riêng cho worker lab. Gán quyền Service Bus Data Receiver để worker nhận được message, nhưng không gán Storage Blob Data Reader trên container source. Dùng một identity khác có quyền upload để chuẩn bị file. Khi worker gọi Blob download, thao tác đọc phải thất bại vì thiếu data-plane permission.

Sau khi ghi nhận principal và resource scope, gán Storage Blob Data Reader cho đúng identity trên container lab. Chạy lại GET với cùng object key/version rồi redrive message. Không dùng Storage Account Key để né RBAC vì điều đó làm sai mục tiêu kiểm thử.

### 5.3.2. Tạo lỗi quyền trên Google Cloud staging

Tạo service account cho worker và cấp Pub/Sub Subscriber trên subscription lab nhưng chưa cấp quyền đọc bucket. Worker nhận event thành công, sau đó `storage.objects.get` bị từ chối. Sau khi lưu error/request context, gán role phù hợp như Storage Object Viewer ở bucket lab hoặc custom role chỉ có permission cần thiết; chạy lại GET rồi replay cùng event ID.

### 5.3.3. Mở rộng: lỗi quyền publish của relay

Để mô phỏng lỗi ở producer, bỏ quyền publish của relay identity: AWS `sqs:SendMessage`, Azure Service Bus Data Sender hoặc Google Pub/Sub Publisher. Outbox row phải còn unpublished và relay ghi nhận lỗi; không đánh dấu event published trước khi broker xác nhận. Cấp lại quyền đúng scope, để relay tiếp tục với event ID đã lưu và xác minh consumer nhận event.

### 5.4. Quan sát và xác định principal

Khi nhận 403, kiểm tra theo thứ tự:

1. Principal thực tế của worker là role/service account nào?
2. Resource đang được gọi là bucket, container hay object key nào?
3. Operation bị từ chối là `GetObject`, `Get Blob`, `storage.objects.get` hay operation khác?
4. Policy identity, resource policy, KMS/key policy và boundary có chặn không?
5. Worker có dùng đúng account/project/subscription/region không?

Không suy ra thiếu quyền từ HTTP status đơn lẻ. Một số gateway/proxy có thể trả 403 vì network policy hoặc token audience; lấy provider error code và request ID để phân biệt.

### 5.5. Sửa lỗi và phục hồi

Sau khi xác nhận đúng principal và resource, cấp đúng quyền đọc object source:

- AWS: cho worker `s3:GetObject` trên source prefix; nếu object dùng customer-managed KMS key, cấp quyền decrypt phù hợp theo key policy.
- Azure: gán data-plane role cho phép đọc blob trên container cần thiết; kiểm tra Managed Identity/Workload Identity đang được chọn.
- Google Cloud: cấp `storage.objects.get` trên bucket cần thiết, ví dụ role phù hợp hoặc custom role tối thiểu.

Sau khi policy có hiệu lực:
1. Xác minh worker identity bằng cơ chế của runtime/provider.
2. Chạy một HEAD/GET kiểm tra với object test.
3. Retry message còn trong queue hoặc redrive từ DLQ theo batch nhỏ.
4. Giữ nguyên event ID và document ID.
5. Xác minh document chuyển tiếp đúng state, không tạo result trùng.

Không đánh dấu document `PROCESSED` chỉ vì đã sửa quyền. Chỉ consumer sau khi đọc, xử lý và commit mới được hoàn tất state.

### 5.6. Tiêu chí PASS

- Log chỉ ra đúng operation, resource và identity alias.
- Metric `storage_access_denied_total` tăng đúng một lần cho lần thử.
- Document chưa bị đánh dấu hoàn tất.
- Message không bị ack như thành công.
- Sau khi cấp quyền, cùng event được xử lý thành công.
- Không có policy rộng kiểu `s3:*`, Storage Account Key hoặc project Editor.

## 6. Lab 2 — Mô phỏng timeout và phục hồi

### 6.1. Phân biệt timeout theo từng lớp

Một workflow có nhiều deadline khác nhau. Không đặt một timeout duy nhất cho toàn bộ hệ thống:

| Timeout | Bảo vệ điều gì | Ví dụ |
| --- | --- | --- |
| SDK attempt timeout | Một lần gọi provider API | S3 GET hoặc Blob GET |
| SDK API call timeout | Tổng thời gian một API call gồm retry | S3 PUT có retry |
| Database query/transaction timeout | Query hoặc transaction giữ connection/lock | Claim document, commit state |
| HTTP client timeout | Request tới downstream service | Gọi OCR API |
| Processing deadline | Tổng thời gian worker xử lý một event | Download + scan + persist |
| Queue visibility/lock/ack deadline | Thời gian message bị ẩn/khóa trước redelivery | SQS visibility, Service Bus lock, Pub/Sub ack deadline |
| Database lease | Thời gian worker sở hữu một job | Lease document đang PROCESSING |

Đặt các deadline có quan hệ rõ ràng. Processing deadline phải nhỏ hơn giới hạn tối đa mà worker được phép chạy. Queue visibility/lock cần lớn hơn thời gian xử lý dự kiến cộng safety margin, hoặc được gia hạn khi worker vẫn hoạt động. Database lease cần được gia hạn hoặc dùng fencing token nếu job có thể chạy lâu.

Nếu queue message được giao lại trong khi worker cũ vẫn chạy, hai worker có thể cùng xử lý. Timeout/lease không thay thế idempotency.

### 6.2. Fault injection bằng fake adapter

Mô phỏng object storage chậm hơn deadline:

~~~java
import java.io.InputStream;
import java.time.Duration;

public class StorageTimeoutException extends RuntimeException {

    public StorageTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class DelayedObjectStore implements ObjectStore {

    private final ObjectStore delegate;
    private final Duration delay;
    private final Duration allowedDelay;

    public DelayedObjectStore(
            ObjectStore delegate,
            Duration delay,
            Duration allowedDelay) {
        this.delegate = delegate;
        this.delay = delay;
        this.allowedDelay = allowedDelay;
    }

    @Override
    public InputStream get(ObjectKey key, String version) {
        try {
            Thread.sleep(Math.min(delay.toMillis(), allowedDelay.toMillis()));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new StorageTimeoutException(
                    "Object read interrupted", ex);
        }
        if (delay.compareTo(allowedDelay) > 0) {
            throw new StorageTimeoutException(
                    "Simulated object read timeout", null);
        }
        return delegate.get(key, version);
    }

    // Các phương thức khác ủy quyền cho delegate.
}
~~~

Trong test thực tế nên dùng fake clock, controllable future hoặc mock server để không làm test suite chậm. Ví dụ trên minh họa lỗi ở application boundary; adapter production vẫn cần timeout thực của SDK/HTTP client.

### 6.3. Cấu hình timeout cho AWS SDK

AWS SDK for Java v2 cho phép cấu hình attempt timeout và API call timeout:

~~~java
import java.time.Duration;

import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3Client = S3Client.builder()
        .region(Region.of(region))
        .overrideConfiguration(
                ClientOverrideConfiguration.builder()
                        .apiCallAttemptTimeout(Duration.ofSeconds(2))
                        .apiCallTimeout(Duration.ofSeconds(6))
                        .build())
        .build();
~~~

Attempt timeout giới hạn một lần gọi; API call timeout giới hạn toàn bộ call gồm retry. Giá trị cần dựa trên latency SLO và kích thước file. Với upload lớn/multipart, dùng transfer manager hoặc API phù hợp và tính timeout cho từng part cũng như tổng transfer.

Không đặt API call timeout nhỏ hơn attempt timeout. Tránh nhân đôi retry ở SDK, Resilience4j, Spring Retry và queue delivery mà không tính tổng budget.

### 6.4. Timeout ở queue

Mỗi queue có cơ chế giữ message khác nhau:

- **SQS:** message trở nên invisible trong visibility timeout. Nếu worker xử lý lâu, có thể gia hạn bằng `ChangeMessageVisibility`. Nếu timeout hết trước khi xử lý/ack xong, message có thể được giao lại.
- **Azure Service Bus:** receiver giữ message lock. Với xử lý dài, dùng auto lock renewal hoặc renew lock thủ công; lock expiry dẫn tới message có thể được giao lại.
- **Google Pub/Sub:** subscriber có ack deadline; client có thể tự động extend deadline khi xử lý. Nếu không ack/extend đúng, message có thể được redeliver.

Không giả định một giá trị visibility/lock/ack deadline có cùng semantics giữa các provider. Adapter phải map rõ deadline, renewal và settlement.

### 6.5. Mô phỏng timeout ở staging

Dùng một trong các cách:
- Toxiproxy/network fault proxy để thêm latency hoặc cắt kết nối tới endpoint test.
- Mock HTTP server trả chậm cho downstream service.
- Fault profile làm object adapter delay trước khi trả kết quả.
- Giảm client timeout có kiểm soát để request hợp lệ vượt ngưỡng.
- Tạm thời giảm worker concurrency để tạo queue backlog và quan sát age/visibility.

Chỉ áp dụng với resource lab. Không cố tình gây packet loss hoặc tăng latency cho endpoint production.

### 6.6. Phân biệt timeout với kết quả không rõ

Timeout không chứng minh provider chưa thực hiện thao tác. Ví dụ PUT object có thể đã thành công nhưng response bị mất; publish queue có thể đã được broker nhận nhưng caller hết thời gian chờ.

Trước khi retry:
- Với object PUT: HEAD object key/version, so checksum và size; dùng key deterministic hoặc conditional write.
- Với queue publish: retry cùng event ID; consumer phải deduplicate.
- Với database commit timeout: đọc lại state bằng document/event ID trước khi chạy lại command.
- Với downstream API: truyền idempotency key nếu API hỗ trợ.

Đây là trạng thái `UNKNOWN_OUTCOME`. Không biến nó thành failure chắc chắn và tạo operation mới ngay.

### 6.7. Retry policy và deadline budget

Phân loại timeout là transient/unknown outcome. Retry có giới hạn với exponential backoff và jitter, ví dụ delay 1s, 2s, 4s, 8s tới max delay; giới hạn tổng elapsed time và số lần thử.

Một policy cần xác định:
- Attempt timeout.
- Tổng API timeout.
- Max attempts ở SDK/client.
- Queue delivery count hoặc redelivery limit.
- Tổng processing deadline.
- DLQ và redrive policy.
- Circuit breaker/open duration nếu dependency outage.

Nếu SDK retry 3 lần, application retry 3 lần và queue redeliver 5 lần, một event có thể tạo rất nhiều API call. Tính tổng retry budget thay vì cấu hình từng lớp độc lập.

### 6.8. Phục hồi sau timeout

1. Kiểm tra dependency latency, throttling, connection pool và provider request ID.
2. Xác định outcome có chắc chắn thất bại hay chưa rõ.
3. Đọc lại object/database/outbox state trước khi tạo side effect mới.
4. Nếu lỗi transient, để queue retry hoặc schedule retry có giới hạn.
5. Nếu worker có thể tiếp tục, gia hạn visibility/lock/ack deadline và DB lease.
6. Nếu hết attempts, chuyển DLQ và phát alert.
7. Sau khi dependency ổn định, redrive theo batch nhỏ, giữ nguyên event ID.
8. Kiểm tra document cuối cùng và không có artifact/result trùng.

### 6.9. Tiêu chí PASS

- Timeout ở SDK không làm worker giữ connection/transaction vô hạn.
- Log ghi dependency, operation, timeout budget và elapsed time.
- Message không bị ack trước khi business transaction commit.
- Message không bị redeliver liên tục do visibility/lock quá ngắn.
- Unknown outcome được kiểm tra bằng state/checksum trước khi retry.
- Sau phục hồi, cùng event hoàn tất một lần về mặt nghiệp vụ.

## 7. Lab 3 — Mô phỏng duplicate message delivery

### 7.1. Vì sao message bị giao trùng?

Queue/event system thường ưu tiên at-least-once delivery. Duplicate có thể xuất hiện khi:
- Worker commit database nhưng chết trước khi ack/delete/complete.
- Ack response bị mất hoặc client timeout.
- Visibility timeout/lock/ack deadline hết hạn trong khi worker vẫn chạy.
- Outbox relay publish thành công nhưng chết trước khi đánh dấu outbox row.
- Operator redrive message từ DLQ.
- Provider/event source gửi lại notification.

Duplicate là một tình huống bình thường của distributed system. Không giả định mỗi event chỉ được nhận một lần.

### 7.2. Gửi cùng event hai lần

Dùng cùng event ID và document ID để mô phỏng:

~~~json
{
  "eventId": "evt-doc-1001-v1",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "object": {
    "key": "source/doc-1001/upload-1.pdf",
    "version": "object-version-1"
  }
}
~~~

Publish payload này hai lần hoặc để worker xử lý xong rồi cố ý bỏ ack lần đầu. Hai message có thể có broker message ID khác nhau nhưng event ID nghiệp vụ vẫn giống nhau.

### 7.3. Hàng rào unique trong database

Dùng unique key cho consumer và event:

~~~sql
INSERT INTO processed_event (
    consumer_name,
    event_id,
    document_id,
    processed_at
)
VALUES (
    :consumer_name,
    :event_id,
    :document_id,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Cú pháp trên dành cho PostgreSQL. Với database khác, dùng unique constraint và câu lệnh atomic insert/merge tương ứng. Repository cần trả kết quả cho biết row mới được insert hay event đã tồn tại.

Không thực hiện mô hình `SELECT trước rồi INSERT` mà không có unique constraint: hai worker đồng thời có thể cùng thấy event chưa tồn tại và cùng thực hiện side effect.

### 7.4. Commit inbox cùng business state

Pseudo-code của application service:

~~~java
@Transactional
public ProcessingResult complete(
        DocumentStoredEvent event,
        ProcessedArtifact artifact) {

    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "document-worker",
            event.eventId(),
            event.documentId());

    if (!firstDelivery) {
        duplicateCounter.increment();
        return ProcessingResult.alreadyProcessed();
    }

    Document document = documentRepository
            .findByIdForUpdate(event.documentId())
            .orElseThrow();

    document.markProcessed(
            artifact.objectKey(),
            artifact.checksum());

    documentRepository.save(document);
    outboxRepository.save(
            OutboxEvent.documentProcessed(
                    event.documentId(),
                    artifact.objectKey()));

    return ProcessingResult.completed();
}
~~~

`insertIfAbsent` phải là thao tác atomic dựa trên unique constraint. Inbox row, document state và outbox event commit trong cùng DB transaction. Nếu transaction rollback, cả ba thay đổi rollback và message có thể được xử lý lại.

Đoạn code giả định artifact đã được upload và xác minh trước khi gọi `complete`. Dùng output key deterministic theo document ID, source version và processor version; không gọi external side effect không idempotent trước khi có deduplication strategy.

### 7.5. Không đánh dấu inbox completed quá sớm

Nếu ghi inbox completed trước khi tải object hoặc xử lý, worker crash có thể khiến message retry nhưng consumer thấy event đã xử lý và bỏ qua vĩnh viễn.

Với xử lý dài, tách hai khái niệm:
- **Job claim/lease:** worker tạm sở hữu công việc; có trạng thái `PROCESSING` và lease expiry.
- **Inbox completed:** event đã commit side effect nghiệp vụ.

Chỉ ghi completed cùng transaction cập nhật document/result/outbox. Lease hết hạn có thể reclaim; fencing/version check ngăn worker cũ ghi kết quả sau worker mới.

### 7.6. Idempotency cho object output và external API

Unique inbox chỉ bảo vệ transaction database. Nó không tự rollback:
- Object PUT đã thành công.
- Email/webhook đã gửi.
- Payment/third-party API đã nhận request.
- Downstream service đã thực hiện side effect.

Dùng deterministic object key và conditional write/versioning cho result. Với external API, truyền idempotency key là event ID hoặc operation ID nếu endpoint hỗ trợ. Nếu không có idempotency ở hệ thống đích, dùng outbox + reconciliation/compensation và chấp nhận rằng cần xử lý trạng thái `UNKNOWN_OUTCOME`.

### 7.7. Queue-specific behavior

| Provider | Duplicate source | Hàng rào bổ sung |
| --- | --- | --- |
| SQS Standard | At-least-once delivery, visibility expiry | Inbox unique key; FIFO deduplication chỉ hỗ trợ trong phạm vi cấu hình/window |
| Azure Service Bus | Lock expiry, abandon, retry, redelivery | Duplicate detection khi cấu hình; inbox vẫn cần cho business idempotency |
| Google Pub/Sub | Redelivery khi ack deadline hết hoặc ack không được ghi nhận | Exactly-once delivery có giới hạn và điều kiện; vẫn giữ inbox cho side effect DB/external |

Tính năng duplicate detection hoặc exactly-once của broker không biến transaction database + object storage + external API thành exactly-once distributed transaction.

### 7.8. Tiêu chí PASS

- Hai lần nhận cùng event ID không làm document xử lý hoàn tất hai lần.
- Unique constraint chặn race khi hai worker cùng insert.
- Duplicate được ack an toàn sau khi xác nhận event đã commit.
- Event ID được giữ nguyên qua retry và DLQ redrive.
- Object output/external side effect có idempotency strategy riêng.
- Metric duplicate tăng nhưng không bị tính là processing failure.

## 8. Lab 4 — Phục hồi tổng hợp và replay an toàn

### 8.1. Chuỗi fault injection

Chạy cùng một document qua ba lỗi theo thứ tự:

1. **AccessDenied:** worker nhận event nhưng không đọc được source object.
2. **Timeout:** sau khi cấp quyền, object GET hoặc downstream processor vượt timeout.
3. **Duplicate:** sau khi xử lý thành công, gửi lại cùng event ID hoặc để message redeliver do ack response bị mất.

Giữ nguyên document ID, event ID, object version và correlation ID xuyên suốt. Chỉ thay đổi fault profile/policy để biết mỗi lần thử đang kiểm tra điều gì.

### 8.2. Recovery decision table

| Triệu chứng | Phân loại | Hành động đầu tiên | Cách phục hồi |
| --- | --- | --- | --- |
| Storage trả AccessDenied | Authorization/permanent until policy changes | Xác định principal, action, resource | Sửa role/policy tối thiểu, rồi retry/redrive |
| Queue publish AccessDenied | Authorization | Kiểm tra relay identity và destination | Cấp Send/Publish đúng topic/queue; relay tiếp tục từ outbox |
| Storage GET timeout | Transient hoặc unknown outcome | Kiểm tra timeout budget, provider request ID | Retry bounded; kiểm tra version/checksum |
| DB commit timeout | Unknown outcome | Query lại document/inbox/outbox theo ID | Tiếp tục từ state đã commit, không tạo command mới |
| Queue publish timeout | Unknown outcome | Kiểm tra outbox và event ID | Publish lại cùng event ID; consumer deduplicate |
| Message redelivered | Duplicate delivery | Kiểm tra inbox và document state | Ack nếu event đã commit; xử lý nếu chưa hoàn tất |
| Message vào DLQ | Retry exhausted/poison | Đọc failure category và delivery count | Sửa nguyên nhân, redrive có kiểm soát |
| Lease hết hạn | Worker crash/processing quá lâu | Kiểm tra worker cũ và fencing token | Reclaim job, ngăn worker cũ ghi kết quả |

### 8.3. Trình tự recovery chuẩn

**Bước 1 — Dừng retry storm.** Nếu lỗi quyền hoặc dependency outage đang tạo backlog lớn, giảm consumer concurrency hoặc pause consumer theo khả năng provider. Không xóa queue để giảm số liệu.

**Bước 2 — Xác định failure boundary.** Dùng event ID/correlation ID để tìm bước cuối đã thành công: object PUT, DB finalize, outbox publish, message receive, object GET, result PUT, DB commit hay ack.

**Bước 3 — Kiểm tra outcome.** Với timeout, đọc lại object/database/outbox state trước khi gửi lại command. Với duplicate, kiểm tra inbox unique key và document state.

**Bước 4 — Sửa nguyên nhân.** Cấp đúng IAM/RBAC, sửa DNS/network/secret, điều chỉnh timeout/visibility/lock hoặc khắc phục schema/payload.

**Bước 5 — Phục hồi có giới hạn.** Retry message đang chờ hoặc redrive DLQ theo batch nhỏ; giữ event ID. Theo dõi backlog drain rate, DB pool và provider throttling.

**Bước 6 — Xác minh kết quả.** Document ở state đúng, output object version/checksum hợp lệ, inbox/outbox nhất quán và không có side effect lặp.

**Bước 7 — Đóng sự cố.** Lưu audit, nguyên nhân gốc, policy/config thay đổi, số message replay và các document cần xử lý thủ công.

### 8.4. Không xóa message hoặc outbox để "làm sạch"

Xóa message đang lỗi có thể làm mất công việc đã được xác nhận với client. Xóa outbox row unpublished làm mất event. Nếu payload poison, chuyển DLQ/quarantine và giữ metadata để điều tra. Nếu event không còn hợp lệ, thực hiện transition nghiệp vụ có audit thay vì xóa record.

### 8.5. Replay một message

Redrive cần:
- Giữ event ID gốc và document ID.
- Kiểm tra source object version còn tồn tại và checksum đúng.
- Xác minh consumer code/schema tương thích.
- Kiểm tra inbox để biết event đã hoàn tất hay chưa.
- Dùng batch limit và tốc độ replay thấp lúc đầu.
- Ghi actor, thời điểm, DLQ source và redrive batch ID.
- Theo dõi duplicate counter và side effect downstream.

Nếu event đã được commit nhưng ack thất bại, replay phải đi qua nhánh duplicate và kết thúc bằng ack, không chạy lại business operation.

## 9. Provider-specific recovery

### 9.1. AWS: S3, SQS và RDS

**Quyền:**
- Worker role cần `s3:GetObject` trên source prefix; quyền queue nhận/xóa message là các action SQS riêng.
- Nếu S3 object dùng SSE-KMS với customer-managed key, worker cần quyền decrypt theo key policy và IAM policy.
- Relay role cần `sqs:SendMessage`; không dùng worker role cho relay nếu không cần.
- Database credential/role của worker chỉ có quyền đọc/ghi bảng workflow cần thiết.

**Timeout và duplicate:**
- Cấu hình AWS SDK v2 `apiCallAttemptTimeout` và `apiCallTimeout`.
- SQS visibility timeout phải đủ cho processing deadline và buffer; gia hạn bằng `ChangeMessageVisibility` nếu cần.
- SQS Standard có at-least-once delivery; FIFO deduplication có phạm vi/window cụ thể và không thay inbox DB.
- Redrive SQS DLQ sau khi policy/worker đã sửa; giữ event ID trong message body.

### 9.2. Azure: Blob Storage, Service Bus và Azure Database

**Quyền:**
- Dùng Managed Identity/Workload Identity đúng của Function App, Container Apps, AKS hoặc VM.
- Worker cần data-plane role đọc Blob, ví dụ Storage Blob Data Reader trên scope phù hợp.
- Service Bus receiver cần role Data Receiver; relay cần Data Sender.
- Azure Database cần network access và database principal/role riêng; RBAC của Azure resource không tự cấp quyền SQL.

**Timeout và duplicate:**
- Blob SDK có retry/network timeout riêng; Service Bus processor cần xử lý lock renewal.
- Message lock expiry có thể khiến message redeliver. Không xử lý lâu hơn lock mà không renew.
- Duplicate detection của Service Bus cần cấu hình và có time window; vẫn dùng inbox unique key cho business side effect.
- Message lỗi vĩnh viễn có thể dead-letter; sau khi sửa nguyên nhân, dùng quy trình resubmit/redrive có audit.

### 9.3. Google Cloud: Cloud Storage, Pub/Sub và Cloud SQL

**Quyền:**
- Dùng service account/workload identity riêng cho uploader, relay và worker.
- Worker cần `storage.objects.get` trên bucket source; uploader cần quyền tạo object.
- Relay cần Pub/Sub Publisher; consumer cần Pub/Sub Subscriber trên topic/subscription tương ứng.
- Cloud SQL cần quyền kết nối theo IAM/connector và database user grants riêng.

**Timeout và duplicate:**
- Cấu hình timeout/retry của Google Cloud client theo operation và deadline của worker.
- Pub/Sub subscriber phải ack hoặc gia hạn ack deadline khi còn xử lý; nếu deadline hết, message có thể redeliver.
- Dead-letter topic và max delivery attempts phải được cấu hình trên subscription phù hợp.
- Exactly-once delivery chỉ có phạm vi hỗ trợ/điều kiện cụ thể; inbox DB vẫn cần cho transaction và external side effect.

### 9.4. Bảng đối chiếu hành động

| Failure | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object read denied | IAM `s3:GetObject`, bucket/KMS policy | Blob data-plane role | IAM `storage.objects.get` |
| Queue publish denied | `sqs:SendMessage` | Service Bus Data Sender | Pub/Sub Publisher |
| Queue receive denied | Receive/Delete/Visibility actions | Service Bus Data Receiver | Pub/Sub Subscriber |
| Queue timeout | Visibility timeout/change visibility | Message lock/renewal | Ack deadline/extension |
| Duplicate | SQS redelivery/FIFO window + inbox | Lock expiry/dedup window + inbox | Redelivery/exactly-once scope + inbox |
| Dead letter | SQS DLQ/redrive | Service Bus DLQ/resubmit | Dead-letter topic/max delivery attempts |
| Database access | DB security group + DB user | Firewall/private endpoint + DB role | Cloud SQL connector/IAM + DB user |

## 10. Kiểm thử tự động

### 10.1. Unit test lỗi quyền

Test xác minh lỗi authorization không bị đổi thành success:

~~~java
@Test
void keepsDocumentUnprocessedWhenObjectReadIsDenied() {
    when(objectStore.get(any(), any()))
            .thenThrow(new StorageAccessDeniedException("denied"));

    assertThatThrownBy(() -> processor.process(event))
            .isInstanceOf(StorageAccessDeniedException.class);

    verify(documentRepository, never()).markProcessed(any());
    verify(messageAcker, never()).acknowledge(any());
}
~~~

Tên method/repository ở đây là pseudocode theo application port. Điều quan trọng là exception được phân loại đúng, document không hoàn tất và message không được ack thành công.

### 10.2. Unit test timeout

~~~java
@Test
void retriesTransientStorageTimeoutWithinBudget() {
    when(objectStore.get(any(), any()))
            .thenThrow(new StorageTimeoutException("timeout", null))
            .thenReturn(validObjectStream());

    processor.processWithRetry(event);

    verify(objectStore, times(2)).get(any(), any());
    verify(documentRepository).markProcessed(any());
}
~~~

Test không nên dùng sleep thật. Dùng fake clock/scheduler hoặc retry policy có backoff strategy có thể thay thế trong test. Xác minh số lần thử không vượt max attempts.

### 10.3. Integration test duplicate

~~~java
@Test
void processesSameEventOnlyOnce() {
    processor.process(event);
    processor.process(event);

    assertThat(documentRepository.findStatus(event.documentId()))
            .isEqualTo(DocumentStatus.PROCESSED);

    assertThat(processedEventRepository.count(
            "document-worker", event.eventId()))
            .isEqualTo(1);

    assertThat(processorMetrics.duplicateCount()).isEqualTo(1);
}
~~~

Test này cần database thật hoặc database test tương thích để xác minh unique constraint/transaction. Nếu hai invocation chạy đồng thời, thêm test concurrency với hai transaction cùng event ID và xác minh chỉ một transaction ghi completed event.

### 10.4. Failure injection test matrix

| Test | Fault injection | Assertion |
| --- | --- | --- |
| Permission denied | ObjectStore ném AccessDenied | State chưa PROCESSED; không ack |
| Timeout trước response | Adapter delay vượt client timeout | Retry bounded; outcome được kiểm tra |
| Publish timeout | Queue adapter timeout sau khi broker có thể đã nhận | Outbox retry cùng event ID |
| Duplicate sequential | Gửi cùng event hai lần | Chỉ một processed_event |
| Duplicate concurrent | Hai worker xử lý cùng event | Unique constraint chỉ cho một commit |
| Crash before ack | Commit DB rồi mô phỏng process chết | Redelivery đi vào duplicate path |
| DLQ redrive | Replay event sau khi sửa policy | Event hoàn tất, không side effect lặp |
| Lease expiry | Worker A chậm, worker B reclaim | Fencing token ngăn worker A ghi stale result |

### 10.5. Local integration và staging

Có thể dùng Testcontainers cho database, LocalStack cho một số S3/SQS flows, Azurite cho Blob và Pub/Sub emulator cho message flow. Các emulator không chứng minh IAM/RBAC thật, private networking, KMS, lock/ack semantics đầy đủ hoặc provider quota.

Staging test phải dùng workload identity và resource tách biệt. Ít nhất một lần cho mỗi provider, xác minh AccessDenied thật, timeout/lock renewal và duplicate redelivery bằng service thật hoặc test harness được provider hỗ trợ.

## 11. Observability và alerting

### 11.1. Dashboard theo workflow

Tạo dashboard có:
- Upload success/failure và object PUT/GET latency.
- AccessDenied theo provider/resource/operation.
- Timeout theo dependency và attempt.
- Outbox backlog và oldest event age.
- Queue depth, oldest message age, receive count và DLQ depth.
- Processing success/error/duration.
- Duplicate event count và inbox conflict.
- Expired lease, reclaim và reconciliation repair.
- Database connection pool, lock wait và query latency.

Không dùng document ID, event ID hoặc object key làm label metric. Dùng trace/log với correlation ID để drill down.

### 11.2. Alert có hành động

| Alert | Ngưỡng gợi ý | Hành động |
| --- | --- | --- |
| AccessDenied tăng | Bất kỳ spike bất thường | Xác định principal/action/resource; kiểm tra policy rollout |
| Timeout tăng | p95/p99 vượt SLO | Kiểm tra dependency latency, retry và timeout budget |
| Oldest queue age tăng | Vượt processing SLO | Kiểm tra worker capacity/downstream bottleneck |
| DLQ có message | > 0 hoặc age vượt ngưỡng | Điều tra failure category; không auto-redrive |
| Outbox backlog tăng | Tuổi event vượt SLA | Kiểm tra relay/queue permission/network |
| Duplicate rate tăng | Vượt baseline | Kiểm tra ack/lock/visibility và relay uncertainty |
| Lease hết hạn tăng | Spike | Kiểm tra worker crash, timeout và fencing |

Ngưỡng cụ thể phụ thuộc SLO và volume; không dùng một threshold chung cho mọi môi trường.

## 12. Troubleshooting theo triệu chứng

### 12.1. AccessDenied nhưng policy có vẻ đúng

- Xác minh identity thực tế trong runtime, tránh nhầm local credential với workload identity.
- Kiểm tra resource ARN/ID, account/project, region và object prefix.
- Kiểm tra deny từ bucket policy, KMS key policy, Azure scope/RBAC condition hoặc Google IAM condition.
- Kiểm tra token expiry/audience và private endpoint policy.
- Kiểm tra service account/role binding của pod hoặc function.
- Thử operation nhỏ trên resource test với đúng principal.

### 12.2. Timeout dù provider khỏe

- Kiểm tra DNS, proxy, NAT, route, TLS handshake và connection pool.
- Kiểm tra SDK retry có tiêu hết API call timeout không.
- Kiểm tra payload/file size và multipart/chunk configuration.
- Kiểm tra database pool pending/lock wait.
- Kiểm tra worker có giữ transaction trong lúc gọi network không.
- Kiểm tra queue lock/visibility/ack deadline và lease có hết trước khi xử lý xong không.

### 12.3. Message lặp dù consumer đã ack

Ack response có thể bị mất hoặc broker không ghi nhận settlement. Kiểm tra event ID/inbox trước; nếu đã commit, duplicate path phải ack mà không chạy lại business side effect. Kiểm tra auto-ack/auto-complete mode và việc listener có return trước khi xử lý hoàn tất không.

### 12.4. Document ở PROCESSING mãi mãi

Kiểm tra lease expiry, worker heartbeat, attempt count và process termination. Reconciliation có thể reclaim lease hết hạn sau khi xác minh worker cũ không còn chạy hoặc fencing token đã thay đổi. Không tự đổi state thành STORED khi chưa biết artifact đã được tạo hay chưa.

### 12.5. DLQ tăng sau khi sửa quyền

Có thể message trong DLQ đã hết retry trước khi policy được sửa. Sửa policy không tự đưa message về queue chính. Kiểm tra role bằng một operation test, sau đó redrive batch nhỏ, giữ event ID và quan sát kết quả.

## 13. Bài thực hành tổng hợp có hướng dẫn

### 13.1. Chuẩn bị

- Tạo bucket/container, queue, DLQ và database riêng cho lab.
- Tạo role/service account cho upload API, relay và worker.
- Seed một document với object version/checksum.
- Bật log/metric và ghi lại baseline.
- Đặt retry tối đa 3-5 lần trong môi trường lab để quan sát DLQ nhanh.

### 13.2. Thực hiện ba lỗi

**Lượt A — Quyền:** bỏ quyền đọc object khỏi worker hoặc bật fake fault `object-read-denied`. Gửi event, xác minh AccessDenied và state không hoàn tất. Cấp lại quyền đúng scope rồi retry cùng event.

**Lượt B — Timeout:** đặt object read timeout thấp hơn delay test hoặc dùng proxy tạo latency. Xác minh timeout được phân loại transient, worker không ack sớm, queue deadline được gia hạn hợp lý. Khôi phục timeout và replay.

**Lượt C — Duplicate:** publish cùng event ID hai lần; tiếp tục mô phỏng crash sau DB commit trước ack. Xác minh lần sau đi vào inbox duplicate path và không tạo kết quả nghiệp vụ lần hai.

### 13.3. Bảng ghi kết quả

| Lượt | Fault | State sau lỗi | Recovery action | State cuối | Side effect count |
| --- | --- | --- | --- | --- | --- |
| A | AccessDenied | Chưa PROCESSED | Cấp quyền và retry | PROCESSED | 1 |
| B | Timeout | Retryable/lease hết hạn | Điều chỉnh timeout, replay | PROCESSED | 1 |
| C | Duplicate | Inbox đã có event | Ack duplicate | PROCESSED | 1 |

Ghi provider request ID, event ID, correlation ID, delivery count, attempt count và thời gian recovery. Nếu side effect count lớn hơn 1, kiểm tra inbox transaction, lease/fencing và idempotency của object/external API.

### 13.4. Điều kiện hoàn thành lab

- Có thể tái hiện AccessDenied mà không dùng quyền admin.
- Có thể tái hiện timeout mà không gây ảnh hưởng production.
- Có thể tạo duplicate bằng publish hai lần hoặc crash trước ack.
- Log chỉ ra đúng component, principal, operation và correlation ID.
- Retry có giới hạn, DLQ hoạt động và replay có audit.
- Cùng event ID chỉ tạo một business completion.
- Reconciliation tìm được outbox/object/lease còn dang dở.
- Sau phục hồi, queue backlog giảm và document ở state hợp lệ.

## 14. Checklist trước production

1. **Identity:** API, relay, worker và trigger có principal riêng.
2. **Least privilege:** quyền gắn với đúng bucket/prefix, queue/topic và database operation.
3. **Error mapping:** AccessDenied, timeout, throttling, not found và conflict được phân loại riêng.
4. **Timeout budget:** SDK attempt/API, processing deadline, DB lease và queue visibility/lock/ack deadline tương thích.
5. **Retry:** có max attempts, backoff/jitter và tránh nhân retry ở nhiều lớp.
6. **Unknown outcome:** PUT/publish/DB timeout có bước đọc lại state trước khi retry.
7. **Idempotency:** event ID, inbox unique key và deterministic output key.
8. **Ack:** chỉ ack sau business transaction commit.
9. **DLQ:** có alert, retention, redrive policy và audit.
10. **Recovery:** có runbook sửa permission, xử lý timeout, replay duplicate và reconcile.
11. **Observability:** correlation ID, provider request ID, delivery count và state transition.
12. **Testing:** unit, database concurrency, emulator và staging fault injection.
13. **Isolation:** fault profile, IAM test role và resource lab không dùng ở production.
14. **Data protection:** không log token, SAS, pre-signed URL, secret hoặc file bytes.
15. **Ownership:** mỗi alert/DLQ/reconciliation có owner và recovery objective.

## 15. Bài tập tự luyện

1. Tạo worker role chỉ có quyền nhận SQS nhưng bị deny đọc S3; quan sát principal và action bị từ chối.
2. Tạo Azure Managed Identity chỉ có quyền Service Bus receive nhưng không có Blob read; xác minh lỗi data-plane.
3. Tạo Google service account có Pub/Sub Subscriber nhưng thiếu `storage.objects.get`; so sánh IAM error và cách cấp role.
4. Dùng fake adapter mô phỏng storage timeout; chứng minh SDK/API timeout và worker deadline được phân biệt.
5. Làm message visibility/lock/ack deadline hết hạn khi worker đang chạy; quan sát redelivery.
6. Gửi cùng event ID hai lần và kiểm tra unique constraint trong inbox.
7. Mô phỏng worker crash sau DB commit nhưng trước ack; xác minh duplicate path.
8. Mô phỏng publish timeout sau khi broker đã nhận event; xác minh outbox retry cùng event ID.
9. Chuyển message vào DLQ, sửa policy rồi redrive theo batch có audit.
10. Viết reconciliation job tìm document PROCESSING có lease hết hạn.
11. Tạo test concurrency với hai worker cùng claim document và kiểm tra fencing token.
12. Xây dashboard phân biệt AccessDenied, timeout, duplicate, backlog và DLQ.

**Tiêu chí hoàn thành:** người học có thể tái hiện ba nhóm lỗi quyền/timeout/duplicate trong môi trường cô lập, xác định đúng identity và failure boundary, phục hồi message an toàn, chứng minh idempotency bằng database constraint, và vận hành được retry/DLQ/reconciliation trên ít nhất một provider cloud.

## Tài liệu tham khảo

- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html): S3/SQS integration và AWS SDK.
- [AWS SDK for Java 2.x — Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html): API call và attempt timeout.
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html): visibility và message redelivery.
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html): DLQ và redrive.
- [AWS IAM policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html): identity/resource policy và explicit deny.
- [Azure Service Bus message locks](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement): lock, renewal và settlement.
- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues): DLQ và resubmit.
- [Azure Blob Storage authorization](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory): Microsoft Entra ID và data-plane RBAC.
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview): acknowledgment và redelivery.
- [Google Cloud Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics): delivery attempts và dead-letter.
- [Google Cloud Storage IAM](https://cloud.google.com/storage/docs/access-control/iam): object permissions và bucket scope.
- [Testcontainers documentation](https://testcontainers.com/guides/getting-started-with-testcontainers-for-java/): integration test với dependency thật trong container.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): lưu business state và event cùng transaction.
- [Idempotent Consumer pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html): xử lý message delivery lặp an toàn.
