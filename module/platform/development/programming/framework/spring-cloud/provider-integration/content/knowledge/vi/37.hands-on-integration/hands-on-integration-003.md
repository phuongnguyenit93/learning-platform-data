# Xử lý tệp bất đồng bộ qua sự kiện, hàng đợi và tiến trình xử lý

## 1. Bài toán và mục tiêu

Một ứng dụng nhận tài liệu, ảnh hoặc video không nên giữ HTTP request mở trong lúc quét virus, trích xuất nội dung, tạo thumbnail, OCR, lập chỉ mục hoặc gọi dịch vụ AI. Những công việc này có thời gian xử lý khác nhau, có thể tạm thời thất bại và cần mở rộng worker độc lập với API upload.

Một kiến trúc phù hợp là event-driven file processing:

1. Client upload object vào bucket/container.
2. Object storage phát event khi object được tạo hoặc hoàn tất.
3. Event được định tuyến vào một hàng đợi bền vững.
4. Spring Boot worker nhận message, kiểm tra event và tạo công việc xử lý.
5. Worker đọc đúng object version, chạy pipeline nghiệp vụ, lưu kết quả.
6. Message được ACK/complete sau khi công việc đã được tiếp nhận bền vững hoặc xử lý thành công theo mô hình đã chọn.

Bài thực hành triển khai cùng một nghiệp vụ trên ba provider:

- **AWS:** Amazon S3 Event Notifications hoặc EventBridge → Amazon SQS → Spring Cloud AWS @SqsListener.
- **Google Cloud:** Cloud Storage notifications → Pub/Sub → PubSubInboundChannelAdapter của Spring Integration.
- **Azure:** Blob Storage events → Event Grid → Azure Service Bus → Spring Cloud Azure @ServiceBusListener.

Mỗi provider có event envelope, cơ chế retry và cách xác nhận message khác nhau. Ta chuẩn hóa các event về cùng một mô hình công việc nội bộ, còn adapter chịu trách nhiệm chuyển đổi dữ liệu và giao tiếp với broker.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này kết hợp storage, messaging, identity, xử lý lỗi và kiểm thử thành một pipeline hoàn chỉnh.

Sau khi hoàn thành, bạn có thể:

- Phân biệt storage event, broker message và job nghiệp vụ.
- Thiết kế queue để tách tốc độ upload khỏi tốc độ xử lý file.
- Cấu hình S3 → SQS, GCS → Pub/Sub và Blob Storage → Event Grid → Service Bus.
- Viết Spring Boot listener/adapter nhận event từ từng broker.
- Chuẩn hóa event về một hợp đồng công việc nội bộ.
- Xử lý duplicate, event đến sai thứ tự và object bị ghi đè.
- Dùng inbox/idempotency key và job state để tránh chạy side effect lặp.
- Chọn thời điểm ACK/complete phù hợp với thời gian xử lý.
- Cấu hình retry, visibility timeout, lock renewal và dead-letter queue.
- Điều chỉnh concurrency, backpressure và worker capacity.
- Theo dõi queue backlog, processing latency, failure rate và DLQ.
- Kiểm thử end-to-end từ upload object đến kết quả xử lý.

> **Phạm vi:** Ví dụ tập trung vào event tạo object hoàn tất (ObjectCreated, OBJECT_FINALIZE, Microsoft.Storage.BlobCreated). Các event xóa/metadata update có thể đi qua cùng kiến trúc nhưng cần handler nghiệp vụ riêng. Version trong dependency được quản lý bằng BOM tương thích với Spring Boot đang dùng; không trộn BOM của ba provider.

## 2. Kiến trúc tổng thể

### 2.1. Các thành phần và trách nhiệm

~~~mermaid
flowchart LR
    CLIENT["Browser / upload API"] --> STORE["Object storage"]
    STORE --> EVENT["Storage event source"]
    EVENT --> BROKER["Durable message broker"]
    BROKER --> ADAPTER["Spring Boot message adapter"]
    ADAPTER --> INBOX["Inbox / job database"]
    INBOX --> WORKER["Processing workers"]
    WORKER --> READ["Read exact object version"]
    READ --> SCAN["Validate / scan / transform"]
    SCAN --> OUTPUT["Processed object storage"]
    SCAN --> RESULT["Database result"]
    RESULT --> DONE["Job completed"]
    BROKER -. "Retry / redelivery" .-> ADAPTER
    ADAPTER -. "Permanent failure" .-> DLQ["Dead-letter queue"]
~~~

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Object storage | Lưu bytes và phát event khi object thay đổi | Chạy toàn bộ pipeline nghiệp vụ |
| Event router | Lọc event và chuyển đến đúng queue/topic | Đọc file lớn hoặc xử lý đồng bộ |
| Broker | Lưu message, phân phối cho consumer, retry/redelivery | Lưu nội dung file lớn |
| Spring adapter | Nhận message, parse envelope, xác thực nguồn event | Tin mọi field do message cung cấp |
| Inbox/job database | Dedupe, lưu trạng thái, lease và lịch retry | Lưu bytes của file |
| Worker | Đọc object, xử lý, ghi kết quả | Giữ HTTP request upload mở |
| DLQ | Giữ message không thể xử lý sau policy retry | Trở thành nơi lưu lỗi không có người theo dõi |

### 2.2. Vì sao queue nằm giữa event và worker?

Storage event có thể đến theo burst. Một đợt upload hàng nghìn file có thể tạo hàng nghìn event trong vài giây, trong khi OCR hoặc quét virus chỉ xử lý được một số lượng nhỏ mỗi giây.

Queue giúp:

- Hấp thụ burst và giữ công việc trong thời gian worker bận hoặc tạm ngừng.
- Cho phép scale worker độc lập với API upload.
- Điều chỉnh concurrency theo CPU, memory, database connection và giới hạn downstream.
- Retry khi worker lỗi hoặc process bị restart.
- Tách producer storage khỏi consumer xử lý file.
- Theo dõi backlog để biết hệ thống đang xử lý chậm hơn tốc độ tiếp nhận hay không.

Không gửi bytes file vào message. Message chỉ nên chứa định danh object, version token, event type và metadata nhỏ. Worker tải file trực tiếp từ storage bằng workload identity.

### 2.3. Hai kiểu xử lý

**Kiểu A — xử lý ngay trong listener:** listener nhận message, tải file, chạy pipeline rồi ACK. Phù hợp với file nhỏ, thời gian xử lý ngắn và có thể giới hạn thời gian xử lý.

**Kiểu B — listener tiếp nhận job bền vững:** listener parse event, ghi inbox/job vào database rồi ACK; worker pool độc lập lấy job từ database và xử lý lâu dài. Phù hợp với OCR, video, AI inference, file lớn hoặc workflow nhiều bước.

Bài này dùng kiểu B làm kiến trúc chính. Nó rút ngắn thời gian giữ message lock/visibility và giúp broker chỉ chịu trách nhiệm đảm bảo job đã được tiếp nhận. Nếu muốn dùng kiểu A, cần cấu hình thời gian visibility/ack deadline/lock renewal lớn hơn thời gian xử lý và vẫn phải idempotent.

## 3. Phân biệt event, message và job

Ba khái niệm có liên quan nhưng không đồng nhất:

- **Storage event:** mô tả điều đã xảy ra với object, ví dụ object incoming/report.pdf đã được tạo.
- **Broker message:** bản event được broker giữ và giao cho subscriber; có delivery count, message ID, ack/lock state.
- **Processing job:** yêu cầu nghiệp vụ do ứng dụng tạo ra, ví dụ quét virus, OCR và tạo thumbnail cho một object generation cụ thể.

Một storage event có thể tạo nhiều job nghiệp vụ. Ví dụ một file được upload có thể tạo job VIRUS_SCAN, OCR và THUMBNAIL. Ngược lại, một job có thể được retry nhiều lần nhưng vẫn là cùng một job logic.

~~~mermaid
flowchart TD
    E["ObjectCreated event"] --> M["Broker message"]
    M --> N["Normalize + deduplicate"]
    N --> J1["Job: virus scan"]
    N --> J2["Job: OCR"]
    N --> J3["Job: thumbnail"]
    J1 --> R["Document state"]
    J2 --> R
    J3 --> R
~~~

Không dùng broker message ID làm idempotency key duy nhất cho event storage. Cùng một storage event có thể được phát lại với broker message ID khác nhau.

## 4. Hợp đồng công việc nội bộ

### 4.1. Chuẩn hóa event từ ba provider

Các provider có envelope khác nhau:

| Provider | Event identity | Object identity/version | Event type |
| --- | --- | --- | --- |
| S3 | eventName, eventTime, sequencer; EventBridge có id | bucket, key, versionId, ETag | s3:ObjectCreated:* |
| GCS | notificationConfig, eventTime, attributes | bucketId, objectId, objectGeneration, metageneration | OBJECT_FINALIZE |
| Azure Blob | Event Grid id, eventTime, subject | container/blob trong subject, ETag, sequencer | Microsoft.Storage.BlobCreated |

Chuẩn hóa thành một record:

~~~java
import java.time.Instant;

public record FileWorkItem(
        String provider,
        String eventKey,
        String eventType,
        String bucketOrContainer,
        String objectKey,
        String versionToken,
        String eTag,
        String sequencer,
        String contentType,
        Long sizeBytes,
        Instant occurredAt,
        String correlationId) {
}
~~~

Ý nghĩa:

- eventKey: khóa dedupe ổn định do adapter tạo từ dữ liệu provider.
- versionToken: version ID hoặc generation nếu provider cung cấp.
- eTag: token để kiểm tra object chưa bị thay đổi.
- sequencer: hỗ trợ nhận biết thứ tự event trên cùng object nếu provider có.
- correlationId: liên kết upload request, event, job và log.

Không ép versionToken, ETag và sequencer vào cùng một semantics. Adapter giữ dữ liệu gốc và chỉ chuyển đổi khi có quy tắc tương đương.

### 4.2. Tạo event key

Một số gợi ý:

| Provider | Event key gợi ý |
| --- | --- |
| S3 notification | bucket + key + versionId (nếu bật versioning) + eventName + sequencer |
| S3 EventBridge | EventBridge id; lưu thêm bucket/key/versionId để truy vết |
| GCS | bucketId + objectId + objectGeneration + eventType; thêm metageneration với metadata update |
| Azure Event Grid | Event Grid id; lưu thêm source + subject + eTag + sequencer |

Có thể hash chuỗi chuẩn hóa thành SHA-256 để tạo khóa ngắn. Nếu cùng object event được phát từ nhiều notification configurations và nghiệp vụ chỉ muốn xử lý một lần, đừng thêm notification configuration ID vào khóa. Nếu mỗi subscription là một workflow độc lập, thêm workflow name vào khóa job.

### 4.3. Job message nhỏ, object pointer rõ ràng

Một job nội bộ có thể chứa:

~~~json
{
  "jobId": "7d9f9e36-3d91-4c2b-9c11-1d8b7c9c5a20",
  "eventKey": "sha256:...",
  "provider": "gcs",
  "bucketOrContainer": "training-documents",
  "objectKey": "incoming/report.pdf",
  "versionToken": "1730000000000000",
  "operation": "DOCUMENT_INGEST",
  "attempt": 0,
  "correlationId": "upload-req-9c3f"
}
~~~

Message không chứa file bytes, access token, signed URL hoặc credential. Không đưa URL do event gửi vào một HTTP client tùy ý. Backend cần map bucket/container và endpoint từ cấu hình được tin cậy, sau đó validate object key theo prefix allowlist.

## 5. Thiết kế inbox và job state

### 5.1. Inbox table

Inbox lưu event đã được tiếp nhận để chống duplicate:

~~~sql
CREATE TABLE storage_event_inbox (
    event_key          VARCHAR(128) PRIMARY KEY,
    provider           VARCHAR(32) NOT NULL,
    event_type         VARCHAR(128) NOT NULL,
    bucket_name        VARCHAR(255) NOT NULL,
    object_key         VARCHAR(1024) NOT NULL,
    version_token      VARCHAR(256),
    e_tag              VARCHAR(256),
    sequencer          VARCHAR(256),
    occurred_at        TIMESTAMP WITH TIME ZONE,
    received_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    status             VARCHAR(32) NOT NULL,
    last_error         VARCHAR(2000)
);
~~~

### 5.2. Job table

~~~sql
CREATE TABLE file_processing_jobs (
    job_id             UUID PRIMARY KEY,
    event_key          VARCHAR(128) NOT NULL,
    job_type           VARCHAR(64) NOT NULL,
    status             VARCHAR(32) NOT NULL,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMP WITH TIME ZONE,
    lease_owner        VARCHAR(128),
    lease_until        TIMESTAMP WITH TIME ZONE,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at         TIMESTAMP WITH TIME ZONE,
    completed_at       TIMESTAMP WITH TIME ZONE,
    last_error         VARCHAR(2000),
    CONSTRAINT uq_file_job UNIQUE (event_key, job_type)
);
~~~

Trạng thái thường dùng:

| Status | Ý nghĩa |
| --- | --- |
| PENDING | Đã tiếp nhận, chờ worker |
| RUNNING | Worker đã claim job bằng lease |
| RETRY_WAIT | Lỗi tạm thời, chờ next_attempt_at |
| COMPLETED | Xử lý thành công |
| REJECTED | File hoặc event không hợp lệ, không retry |
| DEAD | Hết retry policy, cần điều tra hoặc replay |
| CANCELLED | Công việc bị hủy theo nghiệp vụ |

### 5.3. Tiếp nhận event trong một transaction

Listener thực hiện:

1. Parse và validate event envelope.
2. Kiểm tra source account/project/bucket/container nằm trong allowlist.
3. Tạo event key.
4. Insert inbox row.
5. Insert job row với unique constraint.
6. Commit transaction.
7. ACK/complete broker message.

Nếu message được giao lại sau khi commit nhưng trước ACK, unique constraint khiến lần tiếp nhận sau trở thành no-op. Listener có thể ACK bản duplicate sau khi xác nhận event đã được lưu bền vững.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventInboxService {

    private final StorageEventInboxRepository inbox;
    private final FileProcessingJobRepository jobs;

    public EventInboxService(
            StorageEventInboxRepository inbox,
            FileProcessingJobRepository jobs) {
        this.inbox = inbox;
        this.jobs = jobs;
    }

    @Transactional
    public void accept(FileWorkItem item) {
        if (inbox.existsByEventKey(item.eventKey())) {
            return;
        }

        inbox.insertReceived(item);
        jobs.insertPending(
                item.eventKey(),
                "DOCUMENT_INGEST");
    }
}
~~~

Các repository minh họa cần thực thi insert có unique constraint một cách an toàn khi hai listener nhận duplicate đồng thời. Có thể dùng INSERT ... ON CONFLICT DO NOTHING trên PostgreSQL hoặc bắt unique violation theo cách phù hợp với database.

## 6. Worker pool và state machine

### 6.1. Claim job bằng lease

Worker không giữ transaction database mở trong suốt thời gian đọc và xử lý file. Nó claim một job, ghi RUNNING và lease, commit transaction, sau đó mới xử lý.

Với PostgreSQL, một cách claim là:

~~~sql
WITH candidate AS (
    SELECT job_id
    FROM file_processing_jobs
    WHERE
        (status IN ('PENDING', 'RETRY_WAIT')
         AND COALESCE(next_attempt_at, now()) <= now())
        OR
        (status = 'RUNNING' AND lease_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE file_processing_jobs j
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    lease_owner = :worker_id,
    lease_until = now() + interval '5 minutes',
    started_at = now()
FROM candidate c
WHERE j.job_id = c.job_id
RETURNING j.*;
~~~

Lease cho phép worker khác nhận lại job khi process chết giữa chừng. Thời gian lease phải lớn hơn một khoảng xử lý dự kiến hoặc được gia hạn heartbeat trong khi xử lý.

### 6.2. Pipeline xử lý

~~~mermaid
flowchart TD
    A["Claim PENDING job"] --> B["Validate object reference"]
    B --> C["Read exact object version"]
    C --> D["Check size / content type"]
    D --> E["Virus scan / file signature"]
    E --> F["Parse / OCR / transform"]
    F --> G["Write output to processed/"]
    G --> H["Persist metadata and result"]
    H --> I["Mark COMPLETED"]
    C -->|Transient error| R["RETRY_WAIT"]
    D -->|Invalid file| X["REJECTED"]
    E -->|Malware detected| X
    F -->|Transient error| R
    G -->|Transient error| R
~~~

Một worker service có thể được viết như sau:

~~~java
import org.springframework.stereotype.Service;

@Service
public class FileProcessingWorker {

    private final ObjectVersionReader objectReader;
    private final DocumentPipeline pipeline;
    private final FileProcessingJobRepository jobs;

    public FileProcessingWorker(
            ObjectVersionReader objectReader,
            DocumentPipeline pipeline,
            FileProcessingJobRepository jobs) {
        this.objectReader = objectReader;
        this.pipeline = pipeline;
        this.jobs = jobs;
    }

    public void process(ClaimedFileJob job) {
        try {
            try (var input = objectReader.open(job.objectReference())) {
                pipeline.process(job, input);
            }

            jobs.markCompleted(job.jobId());
        }
        catch (PermanentFileException ex) {
            jobs.markRejected(job.jobId(), ex.getMessage());
        }
        catch (Exception ex) {
            jobs.scheduleRetry(job.jobId(), ex.getMessage());
        }
    }
}
~~~

ObjectVersionReader, DocumentPipeline, ClaimedFileJob và repository là abstraction nghiệp vụ minh họa. scheduleRetry cần tính backoff, tăng attempt count và chuyển sang DEAD khi hết số lần thử.

### 6.3. Vì sao cần lease thay vì khóa transaction dài?

Một file lớn có thể mất nhiều phút để quét hoặc chuyển đổi. Nếu giữ transaction database mở trong thời gian này:

- Connection pool nhanh cạn.
- Row lock tồn tại lâu.
- Database vacuum/maintenance chịu thêm áp lực.
- Worker crash có thể giữ transaction đến khi timeout.
- Khó scale worker độc lập.

Claim lease rồi commit giúp database chỉ giữ khóa trong khoảng ngắn. Worker heartbeat cập nhật lease khi cần; nếu worker mất kết nối, lease hết hạn để job được claim lại.

## 7. AWS — S3 Event Notifications và SQS

### 7.1. Luồng event

~~~mermaid
flowchart LR
    S3["Amazon S3 bucket"] -->|ObjectCreated| SQS["SQS Standard queue"]
    SQS --> LISTENER["@SqsListener"]
    LISTENER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|GetObject| S3
    SQS -. "maxReceiveCount exceeded" .-> DLQ["SQS dead-letter queue"]
~~~

Amazon S3 có thể gửi notification tới SQS Standard, SNS hoặc Lambda. Nếu cần EventBridge rule, có thể bật S3 events to EventBridge rồi route tới SQS. S3 không gửi trực tiếp notification tới SQS FIFO; nếu cần FIFO, dùng EventBridge làm lớp định tuyến.

S3 event notification được thiết kế theo at-least-once delivery và không đảm bảo thứ tự. Event thường đến trong vài giây nhưng đôi khi có thể trễ hơn. Vì vậy worker phải dedupe và kiểm tra version/sequencer.

### 7.2. Cấu hình notification

Ví dụ cấu hình notification theo prefix incoming/:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "document-created",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:123456789012:file-events",
      "Events": [
        "s3:ObjectCreated:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "incoming/"
            }
          ]
        }
      }
    }
  ]
}
~~~

Áp dụng cấu hình bằng put-bucket-notification-configuration sau khi queue và queue policy đã sẵn sàng. Queue policy phải cho phép principal dịch vụ S3 gửi message và giới hạn aws:SourceArn vào đúng bucket, đồng thời giới hạn aws:SourceAccount.

S3 bucket và SQS queue đích phải ở cùng AWS Region. S3 notification trực tiếp dùng SQS Standard queue; nếu cần FIFO, route qua EventBridge như phần kiến trúc đã nêu.

Ví dụ policy statement:

~~~json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "s3.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:file-events",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:s3:::training-documents"
    },
    "StringEquals": {
      "aws:SourceAccount": "123456789012"
    }
  }
}
~~~

Nếu dùng EventBridge làm nguồn, cấu hình target và IAM role của EventBridge theo tài liệu EventBridge; event envelope sẽ khác S3 notification JSON.

### 7.3. Dependency và cấu hình Spring Cloud AWS

Dùng Spring Cloud AWS BOM tương thích với Spring Boot, thêm SQS và S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình queue:

~~~yaml
app:
  queue:
    file-events: file-events
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Ứng dụng dùng AWS SDK default credentials provider. Runtime identity cần sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes trên queue; nếu dùng SQS encryption với KMS, cần quyền KMS phù hợp. Worker cần s3:GetObject trên prefix xử lý; chỉ cấp s3:ListBucket nếu thật sự liệt kê object.

### 7.4. Listener nhận S3 event

S3 notification body thường chứa Records. Object key trong record được URL-encoded; cần decode trước khi gọi S3 API. Event kiểm tra s3:TestEvent có thể không có Records, nên parser cần xử lý riêng.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class S3NotificationNormalizer {

    private final ObjectMapper mapper;

    public S3NotificationNormalizer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public List<FileWorkItem> parse(String body) throws Exception {
        JsonNode root = mapper.readTree(body);
        JsonNode records = root.path("Records");

        List<FileWorkItem> result = new ArrayList<>();

        for (JsonNode record : records) {
            String eventName = record.path("eventName").asText();
            if (!eventName.startsWith("ObjectCreated:")) {
                continue;
            }

            JsonNode s3 = record.path("s3");
            JsonNode object = s3.path("object");

            String bucket = s3.path("bucket").path("name").asText();
            String encodedKey = object.path("key").asText();
            String key = URLDecoder.decode(
                    encodedKey, StandardCharsets.UTF_8);

            String versionId = object.path("versionId").asText(null);
            String eTag = object.path("eTag").asText(null);
            String sequencer = object.path("sequencer").asText(null);
            String eventTime = record.path("eventTime").asText();

            String eventKey = bucket + "|" + key + "|"
                    + (versionId != null ? versionId : sequencer)
                    + "|" + eventName;

            result.add(new FileWorkItem(
                    "aws-s3",
                    eventKey,
                    eventName,
                    bucket,
                    key,
                    versionId,
                    eTag,
                    sequencer,
                    null,
                    null,
                    java.time.Instant.parse(eventTime),
                    record.path("responseElements")
                            .path("x-amz-request-id").asText(null)));
        }

        return result;
    }
}
~~~

Nếu dùng EventBridge, tạo normalizer riêng cho EventBridge schema; không đưa EventBridge event vào parser S3 notification như thể hai payload giống nhau.

Listener chỉ tiếp nhận event và lưu job:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class S3FileEventListener {

    private final S3NotificationNormalizer normalizer;
    private final EventInboxService inbox;

    public S3FileEventListener(
            S3NotificationNormalizer normalizer,
            EventInboxService inbox) {
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @SqsListener("${app.queue.file-events}")
    public void receive(String body) throws Exception {
        for (FileWorkItem item : normalizer.parse(body)) {
            inbox.accept(item);
        }
    }
}
~~~

Với acknowledgement mode mặc định ON_SUCCESS, Spring Cloud AWS ACK message sau khi listener hoàn tất thành công. Nếu listener ném exception, message không bị xóa khỏi queue và có thể được giao lại sau visibility timeout. Không bắt exception rồi bỏ qua nếu chưa lưu được job bền vững.

### 7.5. Đọc object đúng version

Nếu bucket bật versioning, dùng versionId trong S3 event khi gọi GetObject. Nếu không có version ID, dùng ETag làm điều kiện If-Match để tránh xử lý bytes đã bị thay thế:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import java.io.InputStream;

public InputStream openS3Object(
        S3Client client,
        String bucket,
        String key,
        String versionId,
        String eTag) {

    GetObjectRequest.Builder request = GetObjectRequest.builder()
            .bucket(bucket)
            .key(key);

    if (versionId != null) {
        request.versionId(versionId);
    }
    else if (eTag != null) {
        request.ifMatch(eTag);
    }

    return client.getObject(request.build());
}
~~~

Đóng stream sau khi worker xử lý xong. Không tải file lớn vào một byte[] nếu pipeline có thể xử lý streaming.

### 7.6. Visibility timeout, retry và DLQ

SQS giữ message ở trạng thái invisible trong thời gian visibility timeout sau khi consumer nhận. Nếu worker không ACK/delete message trước khi timeout, message có thể được giao lại. Cấu hình visibility timeout lớn hơn thời gian xử lý dự kiến nếu xử lý trực tiếp trong listener; với file rất lớn, nên lưu job rồi ACK sớm và xử lý bằng worker pool.

Cấu hình redrive policy trên queue:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:123456789012:file-events-dlq",
  "maxReceiveCount": 5
}
~~~

maxReceiveCount xác định số lần message được nhận trước khi chuyển DLQ. Tách lỗi transient và permanent ở tầng job:

- Lỗi network, throttling hoặc database tạm thời: retry có backoff.
- File hỏng, định dạng không hỗ trợ hoặc malware: đánh dấu REJECTED, ghi lý do và không retry vô hạn.
- Event sai schema hoặc bucket ngoài allowlist: đưa vào quarantine/DLQ để điều tra.

Spring Cloud AWS 3.4 cung cấp ExponentialBackoffErrorHandler để tăng visibility timeout theo số lần nhận. Có thể cấu hình backoff với jitter để tránh nhiều message retry đồng thời. Khi listener chỉ lưu job database, retry của SQS chủ yếu bảo vệ bước tiếp nhận event; retry xử lý file được quản lý bằng job state.

## 8. Google Cloud — Cloud Storage notifications và Pub/Sub

### 8.1. Luồng event

~~~mermaid
flowchart LR
    GCS["Cloud Storage bucket"] -->|OBJECT_FINALIZE| TOPIC["Pub/Sub topic"]
    TOPIC --> SUB["Subscription"]
    SUB --> ADAPTER["PubSubInboundChannelAdapter"]
    ADAPTER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|Read exact generation| GCS
    SUB -. "Delivery attempts exceeded" .-> DLQ["Dead-letter topic"]
~~~

Cloud Storage notification gắn với bucket và publish object event lên Pub/Sub topic. Mỗi message có attributes mô tả event và payload metadata theo JSON_API_V1 nếu được cấu hình.

Các event quan trọng:

| Event | Ý nghĩa |
| --- | --- |
| OBJECT_FINALIZE | Object mới hoặc generation mới đã được tạo hoàn tất |
| OBJECT_METADATA_UPDATE | Metadata object thay đổi |
| OBJECT_DELETE | Object bị xóa vĩnh viễn |
| OBJECT_ARCHIVE | Live generation trở thành noncurrent khi bật Object Versioning |

Khi object cùng tên bị ghi đè, GCS có thể phát OBJECT_FINALIZE cho generation mới và OBJECT_ARCHIVE hoặc OBJECT_DELETE cho generation cũ. Event không đảm bảo thứ tự; generation là token quan trọng để đọc đúng bytes.

### 8.2. Tạo topic, subscription và notification

Ví dụ:

~~~bash
gcloud services enable pubsub.googleapis.com \
  --project=training-platform-dev

gcloud pubsub topics create file-object-events \
  --project=training-platform-dev

gcloud pubsub subscriptions create file-object-events-sub \
  --topic=file-object-events \
  --project=training-platform-dev

gcloud storage buckets notifications create \
  gs://training-documents \
  --topic=projects/training-platform-dev/topics/file-object-events \
  --event-types=OBJECT_FINALIZE \
  --payload-format=json \
  --object-prefix=incoming/
~~~

Cloud Storage service agent của project chứa bucket cần roles/pubsub.publisher trên topic. Ứng dụng Spring Boot cần roles/pubsub.subscriber trên subscription; worker đọc object cần storage.objects.get ở bucket scope.

Không cấp roles/storage.admin chỉ để nhận notification. Tách service agent publish event khỏi service account runtime consume event.

### 8.3. Dependency và adapter

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình project:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
app:
  pubsub:
    file-events-subscription: file-object-events-sub
~~~

Dùng ADC và workload identity cho production. Không đóng gói service account JSON key vào container.

### 8.4. Nhận message qua Spring Integration

PubSubInboundChannelAdapter nhận message từ subscription và chuyển thành Spring Message. Ví dụ dùng MANUAL ACK để chỉ xác nhận sau khi event đã được lưu bền vững:

~~~java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class GcsPubSubConfiguration {

    @Bean
    MessageChannel gcsFileEvents() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter gcsFileEventAdapter(
            @Qualifier("gcsFileEvents") MessageChannel output,
            PubSubTemplate pubSubTemplate,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.pubsub.file-events-subscription}") String subscription) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        subscription);

        adapter.setOutputChannel(output);
        adapter.setPayloadType(byte[].class);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
~~~

Xử lý message:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class GcsFileEventHandler {

    private final ObjectMapper mapper;
    private final GcsEventNormalizer normalizer;
    private final EventInboxService inbox;

    public GcsFileEventHandler(
            ObjectMapper mapper,
            GcsEventNormalizer normalizer,
            EventInboxService inbox) {
        this.mapper = mapper;
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @ServiceActivator(inputChannel = "gcsFileEvents")
    public void handle(Message<byte[]> message) throws Exception {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            JsonNode payload = mapper.readTree(message.getPayload());

            FileWorkItem item = normalizer.fromNotification(
                    message.getHeaders(),
                    payload);

            inbox.accept(item);
            original.ack();
        }
        catch (Exception ex) {
            original.nack();
            throw ex;
        }
    }
}
~~~

GcsEventNormalizer đọc headers eventType, bucketId, objectId, objectGeneration, eventTime, payloadFormat; JSON payload chứa object metadata. Chỉ nhận event type mà ứng dụng hỗ trợ và bucket nằm trong allowlist.

### 8.5. Đọc đúng generation

Không chỉ dùng bucket và object name. Nếu event generation 100 được giao sau khi object đã bị thay bằng generation 101, đọc object live sẽ xử lý nhầm bytes.

Dùng generation từ event:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob readExactGeneration(
        Storage storage,
        String bucket,
        String objectKey,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectKey, generation));
}
~~~

Nếu generation cũ đã bị xóa do lifecycle hoặc không bật versioning, object có thể không còn đọc được. Hãy đánh dấu event stale hoặc xử lý theo policy; không tự động thay bằng live generation mới.

### 8.6. ACK deadline, retry và dead-letter topic

Pub/Sub subscription có ack deadline. Subscriber library có thể tự gia hạn deadline trong khi xử lý; tuy nhiên, không nên giữ một message trong listener hàng chục phút nếu có thể ghi job bền vững rồi ACK.

- ack() sau khi inbox/job đã commit.
- nack() hoặc để ack deadline hết hạn khi không thể tiếp nhận event.
- Cấu hình retry policy exponential backoff cho lỗi tạm thời.
- Cấu hình dead-letter topic trên subscription để giữ message không xử lý được.
- Cấp quyền Publisher cho Pub/Sub service agent trên dead-letter topic và Subscriber cho consumer DLQ.

Maximum delivery attempts cho dead-letter topic nằm trong khoảng 5–100 và được thực thi theo best effort; không xem đây là bộ đếm chính xác tuyệt đối. Khi replay DLQ, giữ nguyên event key để inbox tiếp tục dedupe.

Spring Integration adapter hỗ trợ AUTO, AUTO_ACK và MANUAL. Với MANUAL, ứng dụng phải gọi ACK/NACK; không quên cả hai thao tác vì message có thể được giao lại sau ack deadline.

## 9. Azure — Blob Storage, Event Grid và Service Bus

### 9.1. Luồng event

~~~mermaid
flowchart LR
    BLOB["Azure Blob Storage"] -->|BlobCreated| GRID["Event Grid"]
    GRID -->|Managed identity| SB["Service Bus queue"]
    SB --> LISTENER["@ServiceBusListener"]
    LISTENER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|Conditional read| BLOB
    GRID -. "Delivery failure" .-> EGDLQ["Event Grid dead-letter storage"]
    SB -. "Max delivery count" .-> SBDLQ["Service Bus DLQ"]
~~~

Storage account phải là loại hỗ trợ Event Grid như StorageV2, BlockBlobStorage hoặc BlobStorage. Event Microsoft.Storage.BlobCreated được phát khi blob được tạo hoặc thay thế hoàn tất. Với Data Lake Storage Gen2, nếu muốn chỉ xử lý khi file đã commit hoàn chỉnh, cần lọc theo API FlushWithClose phù hợp với cách upload.

Event Grid có thể route trực tiếp event vào Service Bus queue để tạo lớp buffering. Đây là hai tầng dead-letter khác nhau:

- **Event Grid dead-letter:** sự kiện không giao được tới queue/endpoint.
- **Service Bus DLQ:** message đã vào queue nhưng worker liên tục không xử lý/settle được.

### 9.2. Event schema và filter

Event Grid schema thường là một JSON array, mỗi phần tử có các field:

| Field | Ý nghĩa |
| --- | --- |
| id | Event ID |
| eventType | Ví dụ Microsoft.Storage.BlobCreated |
| subject | Đường dẫn container/blob |
| eventTime | Thời điểm event |
| data.url | URL blob |
| data.eTag | ETag tại thời điểm event |
| data.sequencer | Logical sequence cho cùng một blob |
| data.contentLength | Kích thước object |

Dùng subject filter để chỉ nhận blob trong container/prefix incoming/ và filter event type Microsoft.Storage.BlobCreated. Không nhận event từ output prefix processed/ để tránh vòng lặp.

### 9.3. Route Event Grid tới Service Bus

Tạo Service Bus queue, sau đó tạo Event Grid subscription với endpoint type Service Bus queue. Bật managed identity cho Event Grid và cấp role Azure Service Bus Data Sender ở scope queue hoặc namespace. Worker identity cần Azure Service Bus Data Receiver trên queue và Storage Blob Data Reader trên container chứa file.

Ví dụ CLI minh họa với resource ID đã được lấy từ Azure:

~~~bash
az eventgrid event-subscription create \
  --name file-created-to-servicebus \
  --source-resource-id "$EVENT_GRID_SYSTEM_TOPIC_RESOURCE_ID" \
  --delivery-identity-endpoint-type servicebusqueue \
  --delivery-identity systemassigned \
  --delivery-identity-endpoint "$SERVICE_BUS_QUEUE_RESOURCE_ID"
~~~

Ví dụ giả định bạn đã tạo Event Grid system topic cho Storage account và bật system-assigned identity trên system topic. Gán Azure Service Bus Data Sender cho identity đó tại queue/namespace scope trước khi tạo subscription. Tên tham số và khả năng cấu hình identity phụ thuộc loại Event Grid topic/subscription và API version; hãy kiểm tra command reference của Azure CLI đang dùng. Nếu không bật managed identity cho delivery, Event Grid có thể dùng cơ chế xác thực khác theo cấu hình; production nên ưu tiên Microsoft Entra và RBAC.

### 9.4. Dependency và cấu hình Spring Cloud Azure

Spring Cloud Azure hỗ trợ Spring Messaging cho Service Bus:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-messaging-azure-servicebus</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình namespace và entity type:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo client-id nếu dùng user-assigned managed identity.
        # client-id: ${AZURE_CLIENT_ID}
      servicebus:
        namespace: YOUR_SERVICE_BUS_NAMESPACE
        entity-type: queue
app:
  servicebus:
    file-events-queue: file-events
~~~

Dùng managed identity hoặc DefaultAzureCredential thay cho connection string có SAS key. Các version Spring Cloud Azure mới có thể auto-enable messaging infrastructure; với version cũ hơn, cần khai báo EnableAzureMessaging theo tài liệu tương ứng.

### 9.5. Listener nhận Event Grid message

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.azure.spring.messaging.servicebus.annotation.ServiceBusListener;
import org.springframework.stereotype.Component;

@Component
public class AzureFileEventListener {

    private final ObjectMapper mapper;
    private final AzureBlobEventNormalizer normalizer;
    private final EventInboxService inbox;

    public AzureFileEventListener(
            ObjectMapper mapper,
            AzureBlobEventNormalizer normalizer,
            EventInboxService inbox) {
        this.mapper = mapper;
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @ServiceBusListener(destination = "file-events")
    public void receive(String body) throws Exception {
        JsonNode events = mapper.readTree(body);

        if (events.isArray()) {
            for (JsonNode event : events) {
                FileWorkItem item = normalizer.fromEventGrid(event);
                inbox.accept(item);
            }
        }
        else {
            inbox.accept(normalizer.fromEventGrid(events));
        }
    }
}
~~~

Event Grid mặc định thường giao một event trong một array, nhưng subscription có thể bật batching. Listener nên xử lý cả một event và array nhiều event. Nếu một phần tử lỗi, message batch có thể được giao lại; inbox unique key giúp các event đã được commit trở thành no-op ở lần giao lại.

Trong Service Bus Peek-Lock mode, message bị khóa khi nhận và chỉ bị xóa sau khi được complete. Nếu listener thất bại hoặc lock hết hạn, broker có thể giao lại. Không nuốt exception trước khi listener container hoàn tất settlement. Kiểm tra acknowledgement/settlement mode của version Spring Cloud Azure đang dùng.

### 9.6. Dùng ETag và sequencer

Event Grid không bảo đảm thứ tự. Với cùng một blob, sequencer là chuỗi biểu diễn thứ tự logic; có thể so sánh chuỗi theo quy tắc ordinal để biết event nào mới hơn. ETag là version token tại thời điểm event.

Khi worker đọc blob, dùng điều kiện If-Match để đảm bảo nội dung vẫn có ETag được event mô tả:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.options.BlobInputStreamOptions;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.io.InputStream;

public InputStream openBlobAtExpectedEtag(
        BlobClient blobClient,
        String eventETag) {

    BlobInputStreamOptions options = new BlobInputStreamOptions()
            .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(eventETag));

    return blobClient.openInputStream(options);
}
~~~

Nếu blob đã bị thay thế, Storage trả lỗi precondition thay vì âm thầm cho worker đọc bytes mới. Nếu bật blob versioning và cần xử lý phiên bản cũ, hãy lưu version ID trong metadata nghiệp vụ hoặc tra cứu version phù hợp; Event Grid BlobCreated payload cơ bản cung cấp ETag và sequencer, không nên tự giả định luôn có version ID trong mọi schema.

### 9.7. Retry, lock renewal và DLQ

Event Grid delivery có at-least-once và không đảm bảo thứ tự. Retry policy mặc định có thể thử tối đa 30 lần hoặc 24 giờ. Một số loại endpoint xem lỗi cấu hình như 400/403 là non-retryable; nếu không cấu hình dead-letter, event có thể bị drop. Hãy kiểm tra bảng retry theo đúng endpoint type và cấu hình Event Grid dead-letter destination để giữ event không giao được.

Service Bus có Peek-Lock và DLQ riêng:

- Lock duration mặc định là 1 phút; có thể cấu hình cao hơn, tối đa 5 phút.
- Worker xử lý lâu hơn lock duration cần renew lock.
- Khi message bị abandon hoặc lock hết hạn nhiều lần, delivery count tăng.
- Mặc định max delivery count là 10; vượt ngưỡng thì message chuyển vào Service Bus DLQ.
- Complete xóa message; Abandon mở khóa để giao lại; DeadLetter chuyển message vào DLQ.

Nếu listener chỉ lưu job vào database rồi hoàn tất nhanh, lock thường không phải vấn đề. Nếu xử lý file trực tiếp trong listener, cần cấu hình auto lock renewal và thời gian xử lý hợp lý.

## 10. Xử lý duplicate và event đến sai thứ tự

### 10.1. At-least-once là bình thường

Ba provider đều có thể giao lại event:

- S3 notifications at-least-once, có thể duplicate và out-of-order.
- GCS notifications at-least-once; một event có thể được gửi nhiều lần với Pub/Sub message ID khác nhau.
- Event Grid at-least-once; duplicate và out-of-order có thể xuất hiện.

Đây không phải lỗi hiếm cần bỏ qua. Worker phải được thiết kế idempotent từ đầu.

### 10.2. Inbox unique constraint

Một transaction nên ghi cả inbox và job:

~~~sql
INSERT INTO storage_event_inbox (
    event_key, provider, event_type, bucket_name,
    object_key, version_token, e_tag, sequencer,
    occurred_at, received_at, status
)
VALUES (
    :eventKey, :provider, :eventType, :bucket,
    :objectKey, :versionToken, :eTag, :sequencer,
    :occurredAt, now(), 'RECEIVED'
)
ON CONFLICT (event_key) DO NOTHING;
~~~

Chỉ khi insert mới thành công thì tạo job. Nếu event đã tồn tại, listener ACK message vì công việc tương ứng đã được tiếp nhận trước đó.

### 10.3. Không dùng eventTime làm thứ tự duy nhất

Timestamp có thể trễ, có độ chính xác khác nhau và event có thể đến sai thứ tự. Dùng version token của object:

- S3: versionId nếu bật versioning; nếu không, so sánh sequencer cho cùng object key. Sequencer là chuỗi hex có độ dài khác nhau; khi so sánh cần chuẩn hóa độ dài trước khi so sánh giá trị.
- GCS: generation cho nội dung object; metageneration cho metadata. Không ghi trạng thái database lùi về generation/metageneration cũ.
- Azure: sequencer để so sánh thứ tự event của cùng blob; ETag để kiểm tra object còn đúng phiên bản.

Không so sánh sequencer của hai object khác nhau.

### 10.4. Side effect idempotent

Nếu pipeline tạo thumbnail, output key nên được xác định từ document ID và source version:

~~~text
processed/{documentId}/{sourceVersion}/thumbnail.webp
~~~

Nếu worker retry, output của cùng source version có thể được ghi đè có kiểm soát hoặc dùng create-only precondition. Không tạo output key ngẫu nhiên mỗi lần retry vì sẽ để lại file trùng.

Khi gọi downstream API, truyền idempotency key nếu dịch vụ hỗ trợ. Khi cập nhật database, dùng unique constraint hoặc optimistic locking. Không giả định broker ACK và database commit nằm trong cùng một distributed transaction.

## 11. Retry, poison message và dead-letter

### 11.1. Phân loại lỗi

| Lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Transient infrastructure | Timeout, 429, 5xx, database unavailable | Retry với exponential backoff và jitter |
| Permission/config | 403 do thiếu IAM/RBAC | Alert và sửa quyền; không retry vô hạn |
| Object stale | Version không còn tồn tại hoặc ETag không khớp | Mark stale, reconcile hoặc xử lý theo policy |
| Invalid event | Thiếu bucket/key/version/event type | Quarantine hoặc DLQ |
| Invalid file | Sai format, quá lớn, malware | Mark REJECTED; lưu lý do và audit |
| Duplicate | Event key đã được tiếp nhận | ACK/complete sau khi xác nhận inbox |
| Permanent business failure | Document bị hủy hoặc tenant không hợp lệ | Mark rejected/cancelled; không retry |

### 11.2. Phân biệt broker retry và job retry

Nếu listener ghi job vào database rồi ACK, retry của broker chỉ bảo vệ bước tiếp nhận. Worker job runner quản lý retry xử lý file bằng attempt_count, next_attempt_at và trạng thái RETRY_WAIT.

Nếu listener xử lý file trực tiếp, retry broker phụ thuộc:

- SQS visibility timeout và redrive policy.
- Pub/Sub ack deadline, nack và subscription retry policy.
- Service Bus lock duration, abandon và max delivery count.

Không cấu hình hai tầng retry mà không giới hạn tổng số lần. Ví dụ, 5 lần broker retry nhân với 5 lần job retry có thể tạo 25 lần chạy cùng một file.

### 11.3. Dead-letter là nơi điều tra

DLQ cần có dashboard/alert và quy trình replay:

1. Phát hiện message vào DLQ.
2. Đọc event metadata và error category.
3. Xác định lỗi transient, permission hay payload.
4. Sửa nguyên nhân.
5. Kiểm tra idempotency key và trạng thái job.
6. Replay có kiểm soát.
7. Ghi audit người replay, thời điểm và số lần.

Không tự động replay toàn bộ DLQ theo vòng lặp ngắn. Một poison message có thể làm worker liên tục xử lý thất bại và gây tốn tài nguyên.

## 12. Concurrency, backpressure và scale worker

### 12.1. Điều chỉnh concurrency

Worker concurrency bị giới hạn bởi nhiều tài nguyên:

- CPU cho OCR, image processing và virus scan.
- Memory cho parser hoặc file cần buffer.
- Số kết nối database.
- Storage request rate và throughput.
- Rate limit của dịch vụ OCR/AI.
- Network bandwidth và disk I/O.

Không đặt maxConcurrentMessages bằng số CPU nhân với một hệ số tùy ý rồi bỏ qua downstream. Đo p95 processing time và resource usage trước khi tăng concurrency.

### 12.2. AWS SQS

Spring Cloud AWS @SqsListener hỗ trợ maxConcurrentMessages, maxMessagesPerPoll, pollTimeoutSeconds và messageVisibilitySeconds. maxConcurrentMessages mặc định là 10. Bắt đầu ở mức nhỏ, tăng dần và theo dõi queue backlog.

~~~java
@SqsListener(
        value = "${app.queue.file-events}",
        maxConcurrentMessages = "8",
        messageVisibilitySeconds = "120")
public void receive(String body) throws Exception {
    // Normalize and persist jobs.
}
~~~

Khi listener chỉ tiếp nhận job vào database, visibility 120 giây là ví dụ minh họa; chọn giá trị phù hợp với thời gian parse/commit và retry. Khi xử lý file trực tiếp, visibility phải theo thời gian xử lý và cần gia hạn nếu vượt ngưỡng.

### 12.3. Google Pub/Sub

Streaming subscriber quản lý flow control và có thể tự gia hạn ack deadline trong giới hạn cấu hình. Điều chỉnh maximum outstanding messages và worker executor theo capacity. Nếu xử lý dài, persist job rồi ACK; tránh để subscriber nhận quá nhiều message trong khi worker chưa có slot.

### 12.4. Azure Service Bus

Service Bus listener có thể cấu hình concurrency và client processor options. Lock renewal cần đủ dài so với thời gian xử lý nếu listener làm việc dài. Prefetch quá lớn có thể khiến message bị giữ lock trước khi worker bắt đầu xử lý, làm tăng khả năng lock hết hạn.

### 12.5. Backpressure theo queue depth

Một số tín hiệu nên dùng để scale:

- Queue depth / active message count.
- Age of oldest message.
- Processing time p95/p99.
- Worker CPU/memory.
- Downstream 429/5xx.
- Database connection pool utilization.

Scale-out khi backlog tăng và worker còn capacity. Nếu downstream đang bị rate-limit, scale-out quá nhanh có thể làm lỗi tăng thêm; giảm concurrency và backoff là lựa chọn tốt hơn.

## 13. Tránh event loop và event không mong muốn

Một worker có thể ghi output vào cùng bucket/container. Nếu notification filter theo toàn bucket, output mới sẽ tạo event và worker lại xử lý output đó.

Cách tránh:

- Upload input vào incoming/.
- Ghi output vào processed/.
- Lọc event chỉ theo incoming/.
- Dùng bucket riêng cho output nếu workflow lớn.
- Kiểm tra object metadata marker để loại file do worker tạo.

Ngoài ra, chỉ nhận event type mà workflow hỗ trợ. Ví dụ OBJECT_METADATA_UPDATE không nên tự động chạy lại OCR nếu metadata không ảnh hưởng nội dung. Event delete có thể cập nhật index hoặc hủy job đang chờ, nhưng không nên gọi download object đã bị xóa.

## 14. Bảo mật và IAM

### 14.1. Tách principal theo vai trò

| Provider | Event publisher/router | Worker consumer | Object reader |
| --- | --- | --- | --- |
| AWS | S3 service principal hoặc EventBridge role gửi vào SQS | IAM role có sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes | s3:GetObject trên prefix cần xử lý |
| GCP | Cloud Storage service agent có roles/pubsub.publisher | Service account có roles/pubsub.subscriber trên subscription | storage.objects.get trên bucket |
| Azure | Event Grid managed identity có Azure Service Bus Data Sender | Workload identity có Azure Service Bus Data Receiver | Storage Blob Data Reader ở container scope |

Tách principal Event Grid gửi queue khỏi worker đọc queue. Không cấp quyền quản trị storage hoặc broker cho worker nếu không cần.

### 14.2. Xác thực event source

Không tin bucket/container/object URL trong event chỉ vì message đến từ queue:

- Allowlist account/project/bucket/container.
- Kiểm tra event type.
- Kiểm tra object prefix.
- Không cho event chỉ định host hoặc URL tùy ý.
- Tạo client từ cấu hình đáng tin cậy, không khởi tạo endpoint từ payload.
- Validate object key trước khi dùng trong path local.
- Không chạy command hoặc URL fetch theo metadata tùy ý.

### 14.3. Bảo vệ file và kết quả

- Giữ bucket/container private.
- Dùng workload identity thay cho long-lived key.
- Scan file trước khi công bố kết quả.
- Giới hạn file size, content type và tenant quota.
- Không log file bytes, signed URL, SAS token hoặc access token.
- Lưu output ở prefix/bucket có policy riêng nếu dữ liệu đã được xử lý.
- Dùng encryption at rest và TLS theo policy của tổ chức.

## 15. Observability và vận hành

### 15.1. Metrics

Theo dõi tối thiểu:

| Metric | Mục đích |
| --- | --- |
| Events received | Đo tốc độ event đầu vào |
| Events deduplicated | Phát hiện duplicate delivery |
| Jobs pending/running/retry/dead | Quan sát state machine |
| Queue depth | Đo backlog |
| Age of oldest message | Phát hiện worker tụt lại |
| Processing latency p50/p95/p99 | Đo thời gian pipeline |
| Retry count | Phát hiện lỗi lặp |
| DLQ count/rate | Phát hiện poison message |
| Object read errors | Theo dõi 403/404/412/429/5xx |
| Stale version count | Phát hiện event cũ hoặc object bị thay thế |
| Worker lease expired | Phát hiện process chết hoặc xử lý quá lâu |

### 15.2. Structured logging

Log các field:

- eventKey, jobId, correlationId.
- Provider, bucket/container, object key đã được bảo vệ.
- Version ID/generation/ETag/sequencer khi phù hợp.
- Event type và event time.
- Worker ID, attempt count và job state.
- Processing duration, bytes read và kết quả.

Không log payload nhạy cảm, file content, access token, signed URL hoặc toàn bộ message nếu có thể chứa metadata không tin cậy.

### 15.3. Tracing

Giữ correlation ID từ upload API đến event, queue, job và output. Broker có message ID riêng; lưu message ID như metadata quan sát, không dùng thay event key.

Tách span cho các bước: receive-event, persist-job, read-object, scan, transform, write-output, persist-result. Điều này giúp xác định pipeline đang chậm ở storage, parser hay downstream service.

## 16. Kiểm thử tích hợp

### 16.1. Unit test

Kiểm tra:

- Parser S3 decode object key URL-encoded đúng.
- Parser GCS đọc attributes và JSON payload.
- Parser Event Grid hỗ trợ array nhiều event.
- Event type không hỗ trợ bị bỏ qua hoặc quarantine.
- Event key giống nhau không tạo job thứ hai.
- Generation/ETag/sequencer cũ không làm lùi trạng thái.
- Worker đọc đúng version token.
- Lỗi transient lên RETRY_WAIT.
- File không hợp lệ lên REJECTED.
- Worker output không phát sinh event loop.

### 16.2. Integration test với emulator

Có thể dùng LocalStack cho S3/SQS và Azurite cho Blob Storage ở mức kiểm thử API storage. Pub/Sub emulator kiểm tra subscriber, message payload và ACK/NACK. Emulator không chứng minh đầy đủ event notification service thật hoặc IAM policy production.

Test adapter bằng cách publish synthetic event message vào queue/topic. Test worker bằng object storage test hoặc mock client có hỗ trợ version/ETag condition.

### 16.3. End-to-end test trên cloud test account

1. Tạo bucket/container private và prefix incoming/.
2. Tạo broker queue/topic/subscription và DLQ.
3. Cấp IAM/RBAC cho event source và worker.
4. Cấu hình notification/event subscription theo prefix.
5. Upload một file nhỏ.
6. Xác minh event xuất hiện trong broker.
7. Xác minh Spring listener tiếp nhận job và ACK/complete.
8. Xác minh worker đọc đúng version và tạo output.
9. Upload lại cùng object key và xác minh event mới không làm trùng side effect.
10. Tạo lỗi tạm thời và xác minh retry.
11. Gửi event sai schema hoặc file invalid và xác minh quarantine/DLQ.
12. Restart worker khi đang xử lý và xác minh lease/redelivery phục hồi job.
13. Kiểm tra event output prefix không quay lại pipeline.
14. Kiểm tra queue backlog và metrics.
15. Dọn queue, DLQ, notification config và object test.

### 16.4. Failure matrix

| Tình huống | Kỳ vọng |
| --- | --- |
| Event giao hai lần | Một event key, một job logic |
| Worker crash sau khi claim | Lease hết hạn, worker khác claim lại |
| Worker crash sau khi output đã ghi | Retry không tạo output trùng |
| Event cũ đến sau event mới | Không xử lý lùi version |
| Object bị ghi đè | Đọc version token hoặc đánh dấu stale |
| Broker unavailable | Storage event được giữ/retry theo provider; quan sát backlog |
| Worker mất quyền đọc object | Job retry có giới hạn và alert IAM |
| DLQ tăng | Alert và quy trình replay có kiểm soát |
| Downstream rate-limit | Backoff/jitter, giảm concurrency |
| Output ghi vào input prefix | Test phát hiện event loop |

## 17. So sánh ba provider

| Khía cạnh | AWS | Google Cloud | Azure |
| --- | --- | --- | --- |
| Object event source | S3 Event Notifications / EventBridge | Cloud Storage notifications | Blob Storage events |
| Durable broker | SQS | Pub/Sub | Service Bus |
| Spring consumer | @SqsListener | PubSubInboundChannelAdapter | @ServiceBusListener |
| Event envelope | S3 Records hoặc EventBridge event | Pub/Sub attributes + JSON metadata payload | Event Grid event array / CloudEvents |
| Object version guard | Version ID, ETag, sequencer | Generation, metageneration | ETag, sequencer, blob versioning nếu có |
| Delivery | At-least-once, không đảm bảo thứ tự | At-least-once, không đảm bảo thứ tự | At-least-once, không đảm bảo thứ tự |
| Retry | Visibility timeout, redrive policy | Ack deadline, retry policy | Event Grid retry, Service Bus lock/abandon |
| Dead-letter | SQS DLQ | Pub/Sub dead-letter topic | Event Grid dead-letter storage và Service Bus DLQ |
| IAM | SQS receive/delete + S3 get | Pub/Sub subscriber + Storage get | Service Bus Data Receiver + Blob Data Reader |

Khác biệt lớn nằm ở event envelope, version token và cách settlement:

- SQS ACK thực chất là xóa message khỏi queue.
- Pub/Sub ACK báo broker rằng subscriber đã xử lý xong message.
- Service Bus Complete xác nhận message đã được xử lý và xóa khỏi queue; Abandon mở khóa để giao lại.

Không chuẩn hóa các thao tác này thành một hàm ACK mà không hiểu semantics của adapter. Hãy giữ contract nghiệp vụ chung và triển khai settlement trong provider adapter.

## 18. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây document processing service nhận PDF từ prefix incoming/, quét virus, trích xuất metadata và tạo thumbnail. API upload chỉ trả về sau khi storage xác nhận upload; quá trình xử lý chạy bất đồng bộ và frontend có thể truy vấn trạng thái.

### Nhiệm vụ A — Thiết kế event pipeline

1. Chọn AWS S3/SQS, GCS/Pub/Sub hoặc Azure Blob/Event Grid/Service Bus.
2. Vẽ sơ đồ storage event → broker → Spring listener → inbox/job DB → worker.
3. Định nghĩa FileWorkItem và event key.
4. Giải thích vì sao queue message chỉ chứa object reference, không chứa file bytes.

### Nhiệm vụ B — Cấu hình provider

1. Tạo bucket/container private và prefix incoming/.
2. Tạo queue/topic/subscription và DLQ.
3. Cấu hình event filter theo prefix và event type.
4. Cấp quyền publish/send cho event source.
5. Cấp quyền consume và đọc object cho workload identity.

### Nhiệm vụ C — Viết Spring Boot adapter

1. Thêm provider BOM và starter.
2. Viết parser event envelope.
3. Viết listener nhận broker message.
4. Chuẩn hóa event thành FileWorkItem.
5. Lưu inbox/job trong transaction.
6. ACK/complete sau khi job được commit.

### Nhiệm vụ D — Viết worker

1. Claim job bằng lease.
2. Đọc object theo version ID/generation/ETag.
3. Kiểm tra size, content type và file signature.
4. Quét virus.
5. Trích xuất metadata và tạo thumbnail.
6. Ghi output vào prefix processed/.
7. Cập nhật database và đánh dấu job COMPLETED.

### Nhiệm vụ E — Retry và quan sát

- Test duplicate và event đến sai thứ tự.
- Test worker crash trước và sau output write.
- Test object bị overwrite trước khi worker đọc.
- Test broker visibility/ack deadline/lock expiry.
- Test retry và DLQ.
- Theo dõi queue depth, oldest message age và processing latency.
- So sánh semantics settlement của ba provider.

**Tiêu chí đạt:** Hệ thống tiếp nhận object event qua broker bền vững; Spring Boot listener tạo job idempotent; worker xử lý file độc lập; đọc đúng object version; retry lỗi transient có giới hạn; file invalid được quarantine/DLQ; và có integration test chứng minh toàn bộ pipeline.

## 19. Ghi nhớ

- Storage event mô tả thay đổi object; broker message là bản giao nhận; processing job là yêu cầu nghiệp vụ.
- Queue chỉ chứa object pointer và metadata nhỏ, không chứa file bytes.
- AWS dùng S3 Event Notifications/EventBridge với SQS; GCS dùng Cloud Storage notifications với Pub/Sub; Azure dùng Event Grid với Service Bus.
- S3 direct notification không hỗ trợ SQS FIFO; dùng EventBridge nếu cần FIFO target.
- Spring Boot có @SqsListener, PubSubInboundChannelAdapter và @ServiceBusListener cho từng broker.
- At-least-once là bình thường; luôn thiết kế inbox/idempotency.
- Dùng version ID/generation/ETag/sequencer để tránh xử lý sai phiên bản hoặc event cũ.
- ACK/complete sau khi job đã được lưu bền vững hoặc xử lý xong; không ACK trước commit.
- Visibility timeout, ack deadline và message lock phải phù hợp với thời gian xử lý.
- Retry cần backoff, jitter và giới hạn; DLQ cần alert, điều tra và replay có kiểm soát.
- Worker cần concurrency/backpressure phù hợp với storage, database và downstream capacity.
- Output prefix phải được tách khỏi input prefix để tránh event loop.
- Không tin bucket/object URL từ event; validate source, resource scope và object key.
- Quan sát backlog, oldest message age, processing latency, retries, DLQ và stale-version count.

### Tài liệu tham khảo

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [S3 event notification types and destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html)
- [Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Spring Cloud AWS — SQS integration and listeners](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Spring Cloud AWS — SQS acknowledgement, error handling and backpressure](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Cloud Storage Pub/Sub notifications](https://docs.cloud.google.com/storage/docs/pubsub-notifications)
- [Spring Framework on Google Cloud — Spring Integration and Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html)
- [Pub/Sub subscription retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub subscription properties](https://docs.cloud.google.com/pubsub/docs/subscription-properties)
- [Azure Blob Storage as an Event Grid source](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-blob-storage)
- [Reacting to Azure Blob storage events](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-event-overview)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [Configure Service Bus as an Event Grid handler](https://learn.microsoft.com/en-us/azure/event-grid/handler-service-bus)
- [Enable managed identities for Event Grid delivery](https://learn.microsoft.com/en-us/azure/event-grid/managed-service-identity)
- [Spring Cloud Azure — Spring Messaging for Service Bus](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-messaging-service-bus-support)
- [Azure Service Bus message transfers, locks and settlement](https://learn.microsoft.com/en-us/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Azure Blob Java — BlobInputStreamOptions](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.options.blobinputstreamoptions?view=azure-java-stable)
- [Azure Blob Java — BlobRequestConditions](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.models.blobrequestconditions?view=azure-java-stable)
