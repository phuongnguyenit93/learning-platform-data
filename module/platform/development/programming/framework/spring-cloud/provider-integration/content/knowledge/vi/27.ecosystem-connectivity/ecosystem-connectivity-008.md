# Phối hợp lưu trữ đối tượng, hàng đợi và cơ sở dữ liệu trong một luồng

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết hợp các dịch vụ managed của AWS, Azure và Google Cloud để xây dựng workflow hoàn chỉnh. Một luồng phổ biến là nhận file, lưu file vào object storage, lưu metadata vào database và phát message để worker xử lý bất đồng bộ.

Ba dịch vụ đảm nhận ba trách nhiệm khác nhau:

- **Object storage** lưu nội dung lớn như ảnh, tài liệu, bản ghi âm hoặc kết quả xử lý. Ví dụ: Amazon S3, Azure Blob Storage và Google Cloud Storage.
- **Queue/event service** chuyển thông báo hoặc công việc giữa các thành phần, hấp thụ burst và hỗ trợ xử lý bất đồng bộ. Ví dụ: Amazon SQS, Azure Service Bus và Google Cloud Pub/Sub.
- **Database** lưu metadata, trạng thái nghiệp vụ, quan hệ, idempotency record và lịch sử xử lý. Ví dụ: Amazon RDS/Aurora, Azure Database for PostgreSQL và Google Cloud SQL.

Không nên đưa toàn bộ file vào queue hoặc dùng database làm kho blob mặc định khi object storage phù hợp hơn. Message thường chỉ mang định danh object, version, checksum và correlation ID; worker dùng pointer đó để tải object khi cần.

Bài học tập trung vào cách phối hợp ba dịch vụ thành một workflow nhất quán. Bạn sẽ thiết kế upload flow, transactional outbox, queue consumer, idempotency, retry/DLQ, xử lý lỗi giữa các hệ thống, ánh xạ dịch vụ theo provider và vận hành an toàn.

Sau bài học, bạn có thể:

1. Phân chia trách nhiệm object storage, queue và database.
2. Thiết kế data model và trạng thái vòng đời của một object.
3. Tổ chức upload trực tiếp hoặc qua pre-signed URL.
4. Phát message sau khi metadata đã được commit bằng transactional outbox.
5. Viết consumer đọc object, xử lý và cập nhật database an toàn.
6. Xử lý duplicate, retry, ordering, poison message và partial failure.
7. Đối chiếu S3/SQS/RDS, Blob/Service Bus/Azure Database và GCS/Pub/Sub/Cloud SQL.
8. Dùng workload identity, least privilege, encryption và secret management.
9. Kiểm thử integration và quan sát workflow end-to-end.
10. Xây dựng runbook, rollback và quy trình reconciliation.

> **Phạm vi:** Ví dụ dùng file upload và xử lý tài liệu để minh họa. Cùng kiến trúc có thể áp dụng cho ảnh, media, export, ingestion và event-driven data processing. Tên property, starter và API thay đổi theo release train; cần quản lý dependency qua BOM tương thích với Spring Boot và kiểm tra tài liệu provider trước khi triển khai.

## 2. Kiến trúc tổng thể

### 2.1. Workflow upload và xử lý bất đồng bộ

Giả sử một ứng dụng nhận tài liệu từ người dùng. API tạo upload intent trong database, cấp URL upload có thời hạn hoặc nhận stream file, sau đó xác minh object đã được lưu. Khi metadata chuyển sang trạng thái `STORED`, ứng dụng ghi một outbox event trong cùng transaction. Relay publish event lên queue. Worker nhận event, tải object, xử lý, lưu kết quả và cập nhật trạng thái database.

~~~mermaid
flowchart LR
    U["Client"] --> API["Spring Boot API"]
    API --> DB[("Metadata DB")]
    API --> OS[("Object Storage")]
    DB --> OB["Transactional Outbox"]
    OB --> RELAY["Outbox Relay"]
    RELAY --> Q[["Queue / Event Bus"]]
    Q --> W["Worker / Spring Boot Consumer"]
    W --> OS
    W --> DB
    W --> PROC["Processing / Validation"]
    PROC --> OS
~~~

Các bước:

1. Client yêu cầu tạo upload intent.
2. API ghi metadata `PENDING_UPLOAD` và tạo object key duy nhất.
3. API trả pre-signed URL hoặc nhận file qua backend.
4. Object storage lưu bytes và trả version/ETag/checksum tùy provider.
5. API xác minh object tồn tại, kích thước và checksum theo policy.
6. Transaction cập nhật metadata thành `STORED` và thêm outbox event.
7. Relay publish message chứa object pointer lên queue.
8. Worker nhận message, xác minh version/checksum và tải object.
9. Worker xử lý, lưu artifact/kết quả và cập nhật trạng thái `PROCESSED`.
10. Worker ack message sau khi commit kết quả hoặc để broker retry khi xử lý thất bại.

### 2.2. Vì sao cần cả ba dịch vụ?

| Thành phần | Dữ liệu chính | Trách nhiệm | Không nên dùng để |
| --- | --- | --- | --- |
| Object storage | Bytes, object metadata, version | Lưu file lớn, durable, lifecycle | Lưu quan hệ nghiệp vụ phức tạp |
| Queue/event | Event nhỏ, pointer, retry metadata | Buffer, decouple, delivery | Lưu file lớn hoặc làm source of truth nghiệp vụ |
| Database | Metadata, trạng thái, quan hệ, outbox/inbox | Transaction, query, concurrency control | Lưu blob lớn mặc định |

Database quyết định trạng thái nghiệp vụ; object storage giữ nội dung; queue giúp truyền công việc. Message có thể được giao lại hoặc đến chậm, vì vậy consumer cần đọc trạng thái/version từ database và xử lý idempotent.

### 2.3. Luồng đồng bộ và bất đồng bộ

Upload và xác minh object thường là phần đồng bộ với client. Xử lý virus scan, OCR, thumbnail, indexing hoặc phân tích dữ liệu thường là bất đồng bộ.

API có thể trả `202 Accepted` sau khi upload được xác nhận và công việc được ghi nhận bền vững. Client nhận `documentId` hoặc `operationId`, sau đó truy vấn trạng thái. Không trả thành công cuối cùng chỉ vì queue API đã nhận một message nếu business processing chưa hoàn tất.

### 2.4. Ranh giới source of truth

- Object key/version chỉ ra bytes cụ thể.
- Database lưu owner, trạng thái, object reference, checksum, size, processing result và thời điểm.
- Queue message là thông báo công việc, không phải trạng thái nghiệp vụ cuối cùng.
- Outbox là bản ghi bền vững về event cần publish.
- Inbox/idempotency record giúp consumer nhận biết event đã xử lý.

Không cho phép queue message ghi đè trạng thái database mà không kiểm tra version/state transition. Không suy ra object còn hợp lệ chỉ từ việc metadata row tồn tại.

## 3. Data model và state machine

### 3.1. Metadata record

Một bảng metadata có thể gồm:

| Field | Ý nghĩa |
| --- | --- |
| `document_id` | ID nghiệp vụ do ứng dụng sinh |
| `tenant_id` | Tenant/owner theo authorization model |
| `object_key` | Đường dẫn object trong bucket/container |
| `object_version` | Version/generation cụ thể nếu provider bật versioning |
| `content_type` | MIME type đã xác minh |
| `content_length` | Kích thước bytes |
| `checksum` | Checksum do ứng dụng/provider xác minh |
| `status` | Trạng thái workflow |
| `idempotency_key` | Khóa chống tạo upload intent trùng |
| `created_at`, `updated_at` | Thời điểm lifecycle |
| `failure_code` | Mã lỗi đã chuẩn hóa, không chứa secret |
| `processed_object_key` | Pointer tới artifact kết quả nếu có |

Object key nên chứa ID ngẫu nhiên hoặc identifier không thể đoán, không lấy nguyên tên file người dùng làm key duy nhất. Nếu cần giữ tên gốc, lưu ở database hoặc metadata đã được kiểm soát.

### 3.2. State machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_UPLOAD
    PENDING_UPLOAD --> STORED: object verified
    PENDING_UPLOAD --> UPLOAD_FAILED: upload expired or invalid
    STORED --> QUEUED: outbox published
    QUEUED --> PROCESSING: worker claims
    PROCESSING --> PROCESSED: result committed
    PROCESSING --> RETRY_WAIT: transient failure
    RETRY_WAIT --> PROCESSING: retry
    PROCESSING --> FAILED: permanent failure / attempts exhausted
    STORED --> DELETED: cancellation / retention
    PROCESSED --> DELETED: retention policy
~~~

Trạng thái `QUEUED` là quan sát tiện ích; outbox record vẫn là nguồn bền vững để relay xác định event đã publish. Nếu publish thành công nhưng relay chết trước khi đánh dấu outbox, event có thể được publish lại. Consumer phải chịu được duplicate.

### 3.3. Object key và version

Object key cần ổn định cho một upload intent, ví dụ:

~~~text
tenant/{tenantId}/documents/{documentId}/source/{uploadId}
tenant/{tenantId}/documents/{documentId}/derived/{processorVersion}/preview.webp
~~~

Dùng key mới cho mỗi lần upload/revision để tránh worker đọc nhầm bytes khi cùng key bị ghi đè. Nếu provider hỗ trợ versioning, lưu version ID/generation vào database và message. ETag không phải lúc nào cũng là MD5 checksum, đặc biệt với multipart upload hoặc encryption; dùng checksum API/metadata có semantics rõ theo provider.

### 3.4. Idempotency key khi tạo upload

Client có thể gửi idempotency key cho yêu cầu tạo upload. Database đặt unique constraint theo tenant và operation scope. Nếu client retry do mất response, API trả lại upload intent cũ thay vì tạo nhiều object key và nhiều workflow.

Không dùng file name làm idempotency key. Hai lần upload cùng tên có thể là hai nội dung khác nhau; cùng idempotency key phải gắn với cùng payload/request semantics theo contract.

## 4. Thiết kế upload an toàn

### 4.1. Upload qua Spring Boot

Backend nhận multipart stream rồi upload lên object storage. Cách này cho phép kiểm tra authorization và giới hạn file trước khi ghi, nhưng tăng network traffic, memory/disk pressure và throughput requirement của ứng dụng.

Không đọc toàn bộ file lớn vào byte array. Dùng streaming/multipart API của provider, đặt max size, timeout và giới hạn concurrent uploads. Khi upload thất bại giữa chừng, abort multipart upload và dọn part theo lifecycle policy.

### 4.2. Upload trực tiếp bằng pre-signed URL

Với file lớn, backend có thể tạo pre-signed URL hoặc upload token có thời hạn. Client upload trực tiếp lên object storage, giảm tải cho Spring Boot.

Quy trình:
1. Backend xác thực user/tenant và tạo upload intent.
2. Backend sinh object key duy nhất, giới hạn method, key, expiry và header được ký.
3. Client upload bytes trực tiếp.
4. Client gọi finalize endpoint.
5. Backend gọi HEAD/metadata API để xác minh object, size, content type và version/checksum.
6. Backend chuyển state và ghi outbox event trong transaction.

Pre-signed URL là bearer capability: ai có URL có thể thực hiện operation trong phạm vi và thời hạn được ký. Không log URL, không đặt nó trong analytics/referrer, không cấp quyền bucket rộng và không dùng URL không hết hạn. Giới hạn content length/content type nếu cơ chế provider hỗ trợ; backend vẫn phải xác minh object sau upload.

### 4.3. Upload intent và finalize

Không publish processing event ngay khi tạo upload intent. Worker chỉ nên nhận event khi object đã tồn tại và metadata đã được xác minh. Nếu client không finalize, intent hết hạn và cleanup job xóa object chưa hoàn tất theo policy.

Finalize cần idempotent: nhiều request cùng document/upload ID không tạo nhiều event logic. Dùng state transition có điều kiện, ví dụ chỉ đổi `PENDING_UPLOAD` sang `STORED` một lần và tạo outbox event trong cùng transaction.

### 4.4. Validate file và chống nội dung độc hại

Không tin extension hoặc Content-Type do client gửi. Xác minh magic bytes/file signature, kích thước, checksum và policy loại file. File không tin cậy nên được quarantine trước khi xử lý downstream. Antivirus/malware scan và content disarm/reconstruction có thể là bước đầu tiên trong workflow.

Không render HTML/SVG hoặc mở macro document trực tiếp trong môi trường có quyền cao. Worker chạy với quyền tối thiểu và sandbox phù hợp. Giới hạn archive expansion/decompression ratio để tránh zip bomb.

### 4.5. Lifecycle và cleanup

Đặt lifecycle policy cho multipart upload dở dang, quarantine object, temporary artifact và file hết retention. Cleanup job phải đối chiếu database state và object version; không xóa chỉ dựa trên prefix nếu có thể chứa object đang xử lý.

Dùng soft delete/tombstone hoặc retention/legal hold khi yêu cầu nghiệp vụ/pháp lý cần. Object versioning giúp khôi phục nhưng tăng storage cost; xác định rõ retention và delete marker behavior.

## 5. Transaction boundary và transactional outbox

### 5.1. Vì sao không có transaction chung?

Object storage, queue và relational database thường không tham gia cùng một distributed ACID transaction. Có thể xảy ra các trạng thái:

- Object upload thành công nhưng database commit thất bại.
- Database commit thành công nhưng publish message thất bại.
- Queue nhận message nhưng relay không ghi nhận publish thành công.
- Worker xử lý object thành công nhưng database update thất bại.
- Database update thành công nhưng consumer chết trước khi ack message.

Không giải quyết bằng cách bọc mọi lời gọi trong `@Transactional`. Spring transaction manager cho database không rollback được S3/Blob/GCS hoặc queue call trừ khi có distributed transaction protocol được hỗ trợ rõ ràng; các dịch vụ cloud thường không tham gia một XA transaction chung.

### 5.2. Transactional outbox

Trong một database transaction, ghi business state và outbox event:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentFinalizationService {

    private final DocumentRepository documents;
    private final OutboxRepository outbox;

    public DocumentFinalizationService(
            DocumentRepository documents,
            OutboxRepository outbox) {
        this.documents = documents;
        this.outbox = outbox;
    }

    @Transactional
    public void markStoredAndQueue(
            UUID documentId,
            String objectVersion,
            String checksum) {

        Document document = documents.findByIdForUpdate(documentId)
                .orElseThrow();

        if (document.isAlreadyStored()) {
            return;
        }

        document.markStored(objectVersion, checksum);
        documents.save(document);

        outbox.save(OutboxEvent.documentStored(
                document.id(),
                objectVersion,
                checksum));
    }
}
~~~

Business row và outbox row commit cùng lúc. Nếu transaction rollback, cả hai đều không xuất hiện. Relay chỉ publish các outbox row đã commit.

Ví dụ entity/repository ở trên là khung minh họa; phương thức lock, unique constraint và mapping phụ thuộc persistence layer của ứng dụng.

### 5.3. Vì sao không chỉ dùng TransactionalEventListener?

`@TransactionalEventListener(phase = AFTER_COMMIT)` hữu ích để chạy hành động sau commit trong cùng process. Tuy nhiên, nếu process chết sau database commit nhưng trước khi listener publish message, event trong memory bị mất. Outbox lưu event bền vững trong database, nên relay có thể tiếp tục sau restart.

Có thể dùng listener để đánh thức relay sớm, nhưng outbox row vẫn là durable source of truth. Không phụ thuộc listener như cơ chế lưu event duy nhất.

### 5.4. Outbox relay

Relay có thể poll theo batch hoặc dùng CDC. Với polling:
1. Chọn outbox row chưa publish, đã đến thời điểm retry.
2. Claim row bằng lease/lock để nhiều relay không xử lý cùng lúc.
3. Publish message tới queue/event bus.
4. Chỉ sau khi broker xác nhận, đánh dấu row đã publish.
5. Nếu publish timeout không rõ kết quả, retry có thể tạo duplicate.

Không đánh dấu published trước khi gửi vì crash có thể làm mất event. Publish trước rồi đánh dấu sau tạo at-least-once behavior; consumer cần idempotency.

### 5.5. Outbox schema và vận hành

Outbox row thường có event ID, aggregate/document ID, event type, schema version, payload, created time, attempts, next attempt time, published time và lease owner/expiry. Payload nên nhỏ và không chứa secret hoặc bytes.

Giữ outbox table có giới hạn retention. Xóa/archive row đã publish sau thời gian đủ cho audit/replay. Theo dõi backlog age, publish failures, retry count và số row đang lease quá hạn.

### 5.6. CDC và polling

| Cách relay | Ưu điểm | Chi phí/đánh đổi |
| --- | --- | --- |
| Polling | Đơn giản, ít hạ tầng, dễ hiểu | Query định kỳ, cần lock/lease và batch |
| CDC | Độ trễ thấp, tận dụng transaction log | Cần connector/stream platform, vận hành phức tạp |
| DB trigger trực tiếp publish queue | Có thể gần realtime | Tạo coupling, khó quản lý retry/secret; không phải outbox thuần |

Với hệ thống vừa/nhỏ, polling outbox theo batch thường dễ vận hành. Với throughput cao, CDC có thể phù hợp nhưng cần quản lý schema evolution, offset, replay và connector availability.

## 6. Queue contract và event design

### 6.1. Message mang pointer, không mang file bytes

Một message **DocumentStored** có thể gồm:

~~~json
{
  "eventId": "evt-01J9Q5K3",
  "eventType": "document.stored",
  "schemaVersion": 1,
  "documentId": "doc-1001",
  "tenantId": "tenant-42",
  "object": {
    "provider": "aws",
    "bucket": "rental-documents",
    "key": "tenant/tenant-42/documents/doc-1001/source/up-01",
    "version": "3Lg...abc",
    "contentLength": 524288,
    "checksumSha256": "base64-or-hex-digest"
  },
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "req-8a3d"
}
~~~

Payload trên là ví dụ contract nội bộ; không phải schema bắt buộc của SQS, Service Bus hay Pub/Sub. Trong hệ thống đa cloud, có thể chuẩn hóa event envelope của ứng dụng rồi chuyển sang message attributes/headers theo provider.

Message không nên chứa bytes, pre-signed URL sống lâu, database password, access token hoặc toàn bộ metadata nhạy cảm. Worker dùng object reference và identity của chính nó để tải file.

### 6.2. Event ID, schema version và correlation

- **eventId** duy nhất dùng deduplication.
- **eventType** xác định loại sự kiện.
- **schemaVersion** hỗ trợ evolution payload.
- **documentId** định danh aggregate nghiệp vụ.
- **object.version** trỏ tới bytes cụ thể.
- **occurredAt** là thời điểm nghiệp vụ phát sinh, không phải thời điểm consumer nhận.
- **correlationId** nối log/trace qua API, relay và worker.

Không dùng queue message ID làm event ID nghiệp vụ chung. Broker có thể tạo message ID khác nhau cho mỗi lần publish duplicate. Event ID phải được tạo và lưu cùng outbox record.

### 6.3. Queue hay event bus?

| Cơ chế | Dùng khi | Đặc điểm |
| --- | --- | --- |
| Work queue | Một worker group xử lý mỗi công việc | Competing consumers, visibility/lock/ack |
| Pub/sub topic | Nhiều consumer độc lập cần cùng event | Fan-out, subscription riêng |
| Event bus | Route event theo type/source/filter tới nhiều target | Routing rule và integration |
| Stream | Cần ordering theo partition, replay hoặc throughput lớn | Offset/checkpoint, retention |

Một workflow xử lý tài liệu thường dùng queue để phân phối task tới worker pool. Nếu nhiều bounded context cần nhận cùng **document.stored**, publish event lên topic/event bus rồi route tới subscription/queue riêng. Tránh để nhiều consumer độc lập cùng poll một queue khi tất cả đều phải nhận event.

### 6.4. Ordering và partition key

Không mặc định message tới đúng thứ tự publish. Nếu một document có các event **stored**, **scan.completed**, **indexed**, worker có thể nhận event cũ sau event mới. Dùng aggregate version/sequence và state transition có điều kiện để bỏ qua event stale.

Nếu cần ordering:
- AWS SQS FIFO dùng **MessageGroupId** theo document/aggregate và deduplication phù hợp.
- Azure Service Bus có sessions để xử lý theo session key.
- Google Pub/Sub hỗ trợ ordering key khi subscription/topic được cấu hình phù hợp.

Ordering có thể giảm throughput vì cùng group/session/partition bị tuần tự hóa. Chỉ bật khi business invariant thực sự yêu cầu.

### 6.5. Kích thước message và schema evolution

Giữ message nhỏ. Payload lớn nên lưu ở object storage và message chỉ chứa pointer; bảo đảm worker có quyền đọc object và version không bị xóa trước khi xử lý. Khi đổi schema:
- Thêm field optional có default rõ.
- Consumer chấp nhận phiên bản trước trong rollout window.
- Không đổi ý nghĩa field hiện hữu mà không version.
- Không dùng Java class serialization phụ thuộc classpath giữa producer và consumer.
- Contract test payload JSON/CloudEvents giữa các service.

### 6.6. Native object event hay application outbox?

Object storage có thể phát event khi object được tạo. Ví dụ S3 notification, Azure Event Grid với Blob Storage, hoặc Cloud Storage notification/Eventarc. Có hai lựa chọn:

1. **Application outbox:** application xác minh object, commit metadata và outbox trong cùng DB transaction. Phù hợp khi cần bảo đảm event gắn với trạng thái nghiệp vụ.
2. **Native storage event:** provider phát event khi object thay đổi. Phù hợp khi object được tạo bởi nhiều nguồn hoặc workflow bắt đầu từ storage.

Không xử lý cả hai nguồn như hai event khác nhau cho cùng một document nếu không có deduplication. Storage event có thể duplicate, delay hoặc khác thứ tự; consumer vẫn phải kiểm tra database state, object version và event identity.

## 7. Queue consumer và cập nhật database

### 7.1. Consumer flow

Một consumer an toàn thường làm theo các bước:

1. Parse và validate event envelope.
2. Kiểm tra schema version, event ID và object pointer.
3. Đọc metadata database để xác minh tenant, document state và object version.
4. Claim công việc bằng lease/state transition có điều kiện.
5. Tải đúng object version và xác minh checksum.
6. Xử lý bytes ngoài database transaction dài.
7. Upload artifact kết quả bằng object key deterministic hoặc version riêng.
8. Trong một DB transaction, cập nhật trạng thái, ghi inbox/dedup record và outbox event kế tiếp nếu có.
9. Chỉ ack message sau khi transaction commit.
10. Nếu lỗi tạm thời, để queue retry theo policy; lỗi vĩnh viễn chuyển sang DLQ/quarantine.

Không giữ transaction database mở trong suốt thời gian tải file hoặc OCR/virus scan. Transaction dài giữ lock/connection, làm tăng deadlock và pool exhaustion.

### 7.2. Inbox và idempotency

Consumer có thể dùng bảng inbox với unique key **(consumer_name, event_id)**. Insert inbox record và cập nhật business state trong cùng transaction. Nếu event được giao lại, unique constraint phát hiện duplicate và consumer có thể ack an toàn sau khi xác minh event trước đã commit.

Nếu processing dài, không insert inbox "completed" trước khi side effect xong. Có thể dùng bảng job/lease để claim và theo dõi trạng thái **PROCESSING**, **RETRY_WAIT**, **COMPLETED**; inbox completed chỉ được ghi trong transaction commit kết quả.

### 7.3. Claim bằng lease

Để tránh hai worker xử lý cùng document đồng thời, dùng conditional update hoặc row lock ngắn:

~~~sql
UPDATE document
SET status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = :lease_until,
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = :document_id
  AND status IN ('STORED', 'RETRY_WAIT')
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP);
~~~

Kiểm tra affected row count. Nếu bằng 0, worker khác đã claim, document đã hoàn tất hoặc trạng thái không hợp lệ. Lease phải có expiry và được gia hạn nếu xử lý dài; worker chết thì job có thể được reclaim sau timeout.

Dùng optimistic version hoặc fencing token để worker cũ không ghi kết quả sau khi lease đã được worker mới nhận. Chỉ kiểm tra lease owner ở đầu process là chưa đủ nếu worker cũ vẫn chạy sau khi lease hết hạn.

### 7.4. Transaction hoàn tất

Ví dụ pseudo-code của application service:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCompletionService {

    private final DocumentRepository documents;
    private final InboxRepository inbox;
    private final OutboxRepository outbox;

    @Transactional
    public void complete(
            UUID documentId,
            String eventId,
            String resultKey,
            String resultChecksum) {

        if (inbox.exists("document-worker", eventId)) {
            return;
        }

        Document document = documents.findByIdForUpdate(documentId)
                .orElseThrow();

        if (document.isProcessed()) {
            inbox.save(InboxRecord.completed("document-worker", eventId));
            return;
        }

        document.markProcessed(resultKey, resultChecksum);
        documents.save(document);
        inbox.save(InboxRecord.completed("document-worker", eventId));
        outbox.save(OutboxEvent.documentProcessed(
                documentId, resultKey, resultChecksum));
    }
}
~~~

Trong production, tránh race giữa exists và insert bằng unique constraint ở inbox. Nếu insert trùng, xử lý unique violation theo transaction boundary phù hợp. Kết quả object phải được upload và xác minh trước transaction hoàn tất; nếu transaction thất bại, cleanup/reconciliation xử lý artifact mồ côi.

### 7.5. Ack sau commit

Nếu ack message trước DB commit, process crash có thể làm mất công việc. Nếu commit trước ack, process crash có thể khiến message được giao lại. Vì vậy chọn commit trước ack và làm consumer idempotent.

Một queue adapter cần xác định rõ thời điểm ack/complete/acknowledge theo framework. Không bắt đầu xử lý bất đồng bộ rồi trả khỏi listener trước khi hoàn thành nếu runtime tự ack khi listener return.

### 7.6. Kết quả object và side effect ngoài database

Worker có thể upload thumbnail/OCR JSON vào object storage trước khi commit database. Nếu DB commit lỗi, object kết quả trở thành orphan. Dùng key deterministic theo document ID, source version và processor version để retry có thể ghi cùng logical result; hoặc dùng attempt-specific key rồi cleanup attempt không được tham chiếu.

Nếu upload cùng key có thể ghi đè, bật versioning hoặc dùng conditional write phù hợp để ngăn worker stale ghi đè kết quả mới. Database chỉ trỏ tới result version đã xác minh.

## 8. Retry, DLQ và phục hồi

### 8.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Hành vi |
| --- | --- | --- |
| Transient | Timeout, throttling, temporary network error | Retry với exponential backoff và jitter |
| Dependency unavailable | Database failover, storage API outage | Retry giới hạn, circuit breaker và alert |
| Permanent input | Unsupported format, checksum mismatch | Đánh dấu FAILED/quarantine; không retry vô hạn |
| Authorization | IAM/RBAC denied, secret access denied | Alert và sửa policy; retry chỉ sau khi policy được sửa |
| Poison message | Payload malformed hoặc schema không hỗ trợ | DLQ/quarantine, giữ event ID và error code |
| Concurrency conflict | Lease/version đã thay đổi | Reload state; không xử lý như lỗi provider |

Không retry mọi exception. Retry lỗi permanent làm tăng cost và backlog; không retry lỗi transient làm mất khả năng phục hồi.

### 8.2. Exponential backoff và jitter

Backoff tăng thời gian giữa các lần retry, ví dụ 1s, 2s, 4s, 8s tới max delay; jitter ngẫu nhiên giúp tránh tất cả worker retry cùng thời điểm. Giới hạn max attempts và tổng tuổi công việc theo SLO.

Queue visibility timeout/lock duration phải lớn hơn thời gian xử lý dự kiến hoặc được gia hạn. Với batch consumer, định nghĩa rõ partial failure để một record poison không làm retry toàn batch không cần thiết.

### 8.3. Dead-letter queue

DLQ giữ message đã vượt retry policy hoặc không thể xử lý. DLQ cần:
- Alert khi message đầu tiên xuất hiện hoặc age vượt ngưỡng.
- Retention đủ cho điều tra.
- Quy trình xem payload đã mask và correlation ID.
- Công cụ redrive có kiểm soát sau khi sửa nguyên nhân.
- Kiểm tra idempotency trước khi replay.
- Giới hạn quyền đọc/redrive vì payload có thể chứa metadata nhạy cảm.

Không redrive toàn bộ DLQ liên tục khi dependency vẫn outage. Điều đó tạo retry storm và có thể làm quá tải downstream.

### 8.4. Reconciliation job

Queue không phải nơi duy nhất phát hiện công việc chưa xử lý. Một reconciliation job định kỳ có thể tìm:
- Document STORED nhưng không có outbox event hoặc event chưa publish.
- Document PROCESSING có lease đã hết hạn.
- Outbox row chưa publish quá lâu.
- Object tồn tại nhưng metadata intent đã expired.
- Metadata trỏ tới object/version không còn tồn tại.
- Result object không được database tham chiếu.
- DLQ event có document vẫn ở trạng thái retryable.

Reconciliation sửa trạng thái theo policy và ghi audit. Không tự động xóa object chỉ vì không tìm thấy metadata trong một lần query; cần grace period và xác minh version/retention.

### 8.5. Compensation và saga

Workflow nhiều bước không có distributed transaction có thể dùng saga/compensation:
- Upload object thành công nhưng metadata không thể commit: ghi orphan candidate hoặc cleanup sau grace period.
- Metadata đã STORED nhưng publish lỗi: outbox relay retry.
- Worker tạo artifact nhưng DB update thất bại: retry với deterministic key hoặc cleanup artifact.
- Processing thất bại vĩnh viễn: đánh dấu FAILED, giữ source object theo retention/quarantine policy.
- User hủy trước khi worker claim: chuyển state và bỏ qua event stale; nếu worker đang xử lý, dùng cancellation flag/compensation.

Compensation là hành động nghiệp vụ bù trừ, không phải rollback ACID. Xóa object có thể không đảo ngược được nếu object đã được tải xuống hoặc downstream đã dùng; xác định rõ side effect và retention trước khi thiết kế.

## 9. Provider mapping: AWS, Azure và Google Cloud

### 9.1. AWS: S3 + SQS/EventBridge + RDS/Aurora

| Vai trò | Dịch vụ | Spring integration |
| --- | --- | --- |
| Object storage | Amazon S3 | AWS SDK for Java v2, Spring Cloud AWS S3 |
| Work queue | Amazon SQS | AWS SDK v2, Spring Cloud AWS SQS |
| Event routing | Amazon EventBridge | AWS SDK v2/AWSpring integration phù hợp |
| Relational database | Amazon RDS/Aurora | Spring JDBC/JPA, PostgreSQL/MySQL driver |
| Secret | AWS Secrets Manager/SSM Parameter Store | AWS SDK/AWSpring integration |

Một flow thường gặp: API upload object lên S3; transaction database ghi metadata và outbox; relay gửi SQS message; worker đọc S3 bằng IAM role, xử lý và cập nhật RDS. Nếu dùng S3 event notification thay cho application outbox, cần thiết kế event deduplication và state verification.

IAM role của API có quyền PutObject vào prefix upload; worker có quyền GetObject ở prefix source và PutObject ở prefix result; queue publisher/consumer có quyền SendMessage/ReceiveMessage/DeleteMessage; database identity riêng. Không cấp một role full S3/SQS/RDS cho tất cả component.

### 9.2. Azure: Blob Storage + Service Bus/Event Grid + Azure Database

| Vai trò | Dịch vụ | Spring integration |
| --- | --- | --- |
| Object storage | Azure Blob Storage | Azure Storage Blob SDK, Spring Cloud Azure |
| Work queue | Azure Service Bus Queue | Azure Service Bus SDK/Spring Cloud Azure |
| Event routing | Azure Event Grid | Event Grid SDK/integration |
| Relational database | Azure Database for PostgreSQL hoặc Azure SQL | Spring JDBC/JPA và driver |
| Secret | Azure Key Vault | Azure Identity + Key Vault SDK/Spring integration |

Flow có thể upload Blob, ghi metadata/outbox vào Azure Database, publish Service Bus message và worker tải Blob để xử lý. Nếu Blob event đi qua Event Grid rồi route tới Service Bus, event envelope khác với message do application tự tạo; adapter cần normalize về event contract nội bộ.

Dùng Managed Identity/Workload Identity với role data-plane phù hợp cho Blob, Service Bus, Key Vault và database auth khi được hỗ trợ. Nếu dùng SAS connection string, giới hạn scope/expiry và có rotation plan. Azure RBAC management-plane role không tự động đồng nghĩa quyền đọc/ghi Blob data-plane.

### 9.3. Google Cloud: Cloud Storage + Pub/Sub/Eventarc + Cloud SQL

| Vai trò | Dịch vụ | Spring integration |
| --- | --- | --- |
| Object storage | Google Cloud Storage | Google Cloud Storage Java client/Spring Cloud GCP |
| Work queue/pub-sub | Pub/Sub | Google Cloud Pub/Sub client/Spring Cloud GCP |
| Event routing | Eventarc | Eventarc trigger và Cloud Run/Functions target |
| Relational database | Cloud SQL | JDBC driver/Cloud SQL Java Connector, Spring JDBC/JPA |
| Secret | Secret Manager | Google Cloud Secret Manager client/Spring Cloud GCP |

Flow có thể upload object lên GCS, ghi metadata/outbox vào Cloud SQL, publish Pub/Sub message và worker tải đúng object generation. Nếu dùng Cloud Storage notification/Eventarc, xác minh event type, bucket/object generation và CloudEvent envelope trước khi chuyển sang internal event.

Workload Identity cấp principal cho API/worker. Cấp role storage object create cho uploader, object viewer cho worker, Pub/Sub publisher/subscriber theo component và Cloud SQL connectivity/database permission riêng. Không lưu service account JSON key trong container hoặc queue message.

### 9.4. Khác biệt cần giữ trong adapter

Không ép ba provider vào một abstraction quá nghèo. Các khác biệt quan trọng:

- Version/generation và checksum semantics của object.
- Pre-signed URL/SAS/signed URL và header/expiry.
- Message ack, visibility/lock, ordering và retry.
- Event envelope và notification delivery.
- IAM/RBAC role, identity token và network model.
- Database connectivity, IAM authentication và connection pool.
- Native encryption, retention, lifecycle và audit.

Có thể tạo application ports như **ObjectStore**, **WorkQueue** và **DocumentRepository**; mỗi provider adapter chuyển đổi contract nội bộ sang SDK/provider API. Không expose provider SDK types vào domain model nếu muốn giữ domain độc lập.

## 10. Thiết kế application ports và provider adapters

### 10.1. Giữ domain model độc lập với SDK

Application service nên làm việc với contract của nghiệp vụ. Adapter chuyển đổi contract sang AWS SDK, Azure SDK hoặc Google Cloud client. Một cấu trúc package minh họa:

~~~text
document/
  domain/
    Document.java
    DocumentStatus.java
    DocumentStoredEvent.java
  application/
    UploadDocumentUseCase.java
    ProcessDocumentUseCase.java
    port/
      ObjectStore.java
      WorkQueue.java
      DocumentRepository.java
      OutboxRepository.java
  adapter/
    in/
      http/
      queue/
    out/
      s3/
      sqs/
      rds/
      azure-blob/
      service-bus/
      gcs/
      pubsub/
      cloud-sql/
~~~

Không để domain entity phụ thuộc provider SDK type như S3Object, BlobClient hoặc Storage.Blob. Adapter chịu trách nhiệm mapping error, retryable status, version ID, checksum và metadata.

### 10.2. ObjectStore port

Một contract có thể biểu diễn các thao tác cần cho workflow:

~~~java
import java.io.InputStream;

public interface ObjectStore {

    StoredObject put(
            ObjectKey key,
            InputStream content,
            long contentLength,
            String contentType,
            String checksum);

    ObjectMetadata head(ObjectKey key, String version);

    InputStream get(ObjectKey key, String version);

    void delete(ObjectKey key, String version);
}
~~~

StoredObject nên trả key, version/generation, checksum và content length đã được xác minh. Không dùng ETag thay checksum nếu semantics provider không đảm bảo. delete cần version cụ thể khi object versioning bật để tránh xóa nhầm revision.

### 10.3. WorkQueue port

Application có thể phát event qua một port:

~~~java
public interface WorkQueue {

    PublishReceipt publish(DocumentStoredEvent event);

}
~~~

Outbox relay gọi port này. Adapter serialize event theo schema nội bộ rồi map sang SQS message, Service Bus message hoặc Pub/Sub message. PublishReceipt chỉ ghi nhận broker đã chấp nhận publish; nó không có nghĩa worker đã xử lý xong.

Không expose queue URL, subscription name, receipt handle hoặc provider SDK type vào business logic. Những thông tin cần cho ack/settlement thuộc inbound adapter.

### 10.4. Orchestrator không giữ transaction qua network call

Một upload use case có thể điều phối các bước:

~~~java
import java.io.InputStream;

import org.springframework.stereotype.Service;

@Service
public class UploadDocumentUseCase {

    private final UploadIntentService intents;
    private final ObjectStore objectStore;
    private final DocumentFinalizationService finalization;

    public UploadDocumentUseCase(
            UploadIntentService intents,
            ObjectStore objectStore,
            DocumentFinalizationService finalization) {
        this.intents = intents;
        this.objectStore = objectStore;
        this.finalization = finalization;
    }

    public UploadReceipt upload(UploadCommand command, InputStream stream) {
        UploadIntent intent = intents.create(command);

        StoredObject stored = objectStore.put(
                intent.objectKey(),
                stream,
                command.contentLength(),
                command.contentType(),
                command.checksum());

        finalization.markStoredAndQueue(
                intent.documentId(),
                stored.version(),
                stored.checksum());

        return new UploadReceipt(intent.documentId(), "STORED");
    }
}
~~~

Intent creation, object upload và finalization là ba boundary. Không đặt một transaction bao trùm method này để giữ transaction trong lúc truyền file. Nếu object upload thành công nhưng finalization thất bại, reconciliation sẽ tìm orphan object sau grace period.

### 10.5. Consumer adapter và application service

Inbound adapter đọc message, validate envelope rồi gọi application service. Application service không cần biết message đến từ SQS, Service Bus hay Pub/Sub.

~~~java
import org.springframework.stereotype.Service;

public interface DocumentStoredHandler {
    void handle(DocumentStoredEvent event);
}

@Service
public class DocumentStoredHandlerImpl implements DocumentStoredHandler {

    private final DocumentProcessor processor;

    public DocumentStoredHandlerImpl(DocumentProcessor processor) {
        this.processor = processor;
    }

    @Override
    public void handle(DocumentStoredEvent event) {
        processor.process(event.documentId(), event.object());
    }
}
~~~

Inbound adapter chỉ ack/complete message sau khi handler trả thành công và transaction hoàn tất theo contract framework. Nếu listener framework auto-ack khi method return, không dispatch processing vào background thread rồi return sớm.

### 10.6. Error mapping

Chuẩn hóa lỗi ở adapter boundary:

| Provider error class | Application category | Hành vi |
| --- | --- | --- |
| Throttling/rate exceeded | TRANSIENT | Backoff và retry |
| Service unavailable/timeout | TRANSIENT hoặc UNKNOWN_OUTCOME | Retry idempotent |
| Not found | NOT_FOUND | Kiểm tra state/version; có thể permanent |
| Access denied | AUTHORIZATION | Alert, không retry vô hạn |
| Invalid checksum/unsupported content | INVALID_INPUT | Quarantine/FAILED |
| Precondition/ETag conflict | CONCURRENCY_CONFLICT | Reload metadata và quyết định retry |
| Quota exceeded | CAPACITY | Alert, backpressure và retry có giới hạn |

Không bắt mọi SDK exception rồi đổi thành HTTP 500 chung. Giữ provider error code trong log có kiểm soát, nhưng không ghi credential hoặc full request headers.

## 11. Cấu hình tích hợp theo provider

### 11.1. AWS SDK và Spring Cloud AWS

Spring Boot có thể tạo S3/SQS client từ AWS SDK v2. Region và credential provider lấy từ runtime/default chain; endpoint override chỉ dành cho local emulator hoặc test environment.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration
public class AwsStorageConfiguration {

    @Bean
    S3Client s3Client(AwsProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .build();
    }

    @Bean
    SqsClient sqsClient(AwsProperties properties) {
        return SqsClient.builder()
                .region(Region.of(properties.region()))
                .build();
    }
}
~~~

Ví dụ này dựa vào default credentials provider chain. Trong ECS/EKS/EC2, gắn task role, Pod Identity/IRSA hoặc instance profile tương ứng. Không tạo static access key trong configuration properties.

Spring Cloud AWS có integration cho S3 và SQS theo release. Dùng starter tương ứng nếu muốn Spring-managed template/listener; dùng SDK trực tiếp khi cần API đặc thù. Không khai báo đồng thời hai listener cho cùng queue khiến message bị xử lý ngoài ý muốn.

### 11.2. S3 upload và SQS publish

Ví dụ adapter upload object:

~~~java
import java.io.InputStream;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ChecksumAlgorithm;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

public StoredObject put(
        String bucket,
        String key,
        InputStream input,
        long length,
        String contentType) {

    PutObjectResponse response = s3Client.putObject(
            PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .contentType(contentType)
                    .checksumAlgorithm(ChecksumAlgorithm.SHA256)
                    .build(),
            RequestBody.fromInputStream(input, length));

    return new StoredObject(
            key,
            response.versionId(),
            response.checksumSHA256(),
            length);
}
~~~

Đoạn mã minh họa yêu cầu SDK/provider hỗ trợ checksum SHA-256 cho request; ứng dụng vẫn nên đối chiếu checksum với giá trị mong đợi và lưu checksum đã xác minh. Không coi ETag là SHA-256/MD5 cho mọi upload mode. Bổ sung multipart strategy cho file lớn, server-side encryption và metadata policy khi triển khai thực tế.

SQS relay có thể gửi JSON event bằng SendMessageRequest; message body chứa pointer và event ID. Với FIFO queue, set message group/deduplication fields theo aggregate/event semantics. Worker cần quyền nhận/xóa message và đọc đúng object prefix.

### 11.3. Azure Blob Storage và Service Bus

Azure SDK có client riêng cho Blob và Service Bus. Blob adapter có thể dùng BlobContainerClient/BlobClient; queue adapter dùng ServiceBusSenderClient hoặc processor client. Dùng DefaultAzureCredential để resolve Managed Identity/Workload Identity trong runtime được hỗ trợ.

Ví dụ cấu hình khái niệm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

@Configuration
public class AzureStorageConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(AzureProperties properties) {
        return new BlobServiceClientBuilder()
                .endpoint(properties.blobEndpoint())
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

Service Bus sender/processor có thể dùng cùng identity nhưng role cần phân biệt sender và receiver. Nếu dùng connection string, lấy từ Key Vault/secret source và rotate; không đưa vào YAML commit. Azure Blob version ID/ETag và Service Bus message lock/session cần được giữ trong adapter contract khi business flow cần.

### 11.4. Google Cloud Storage và Pub/Sub

Google Cloud client libraries dùng Application Default Credentials. Trên GKE, Cloud Run hoặc workload được cấu hình identity, ADC resolve credential theo runtime. Không lưu service account JSON key trong image.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

@Configuration
public class GoogleStorageConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Publisher adapter dùng Publisher và PubsubMessage; subscription consumer cần ack sau khi handler hoàn tất. Với ordering, configure ordering key và subscription semantics phù hợp. GCS object generation phải được lưu để worker tải đúng version nếu object có thể bị ghi đè.

### 11.5. Database và connection pool

Datasource dùng Spring Boot JDBC/JPA hoặc R2DBC. Pool size phải tính tổng trên mọi replica/worker:

**maximum connections = pool size per instance × maximum instances + migration/admin reserve**

Nếu 20 worker mỗi worker có pool 10, database có thể nhận tới 200 connection từ worker chưa kể API/monitoring. Scale queue consumer mà không tính connection limit sẽ làm database quá tải.

Dùng connection timeout, max lifetime, idle timeout và leak detection theo database/provider. Nếu dùng IAM/database token ngắn hạn, pool phải có cách lấy credential mới khi tạo connection mới. Không giữ token hết hạn làm password cố định.

## 12. Security và data governance

### 12.1. Tách identity theo trách nhiệm

Không dùng một identity có toàn quyền cho API, relay và worker. Tách permission theo action:

| Component | Object storage | Queue | Database |
| --- | --- | --- | --- |
| Upload API | Create/upload vào source prefix; HEAD object cần xác minh | Không cần publish trực tiếp nếu dùng outbox | Tạo intent, cập nhật metadata, ghi outbox |
| Outbox relay | Không cần đọc file | Publish/send message | Đọc và cập nhật outbox |
| Processing worker | Read source version, write result prefix | Receive/ack message | Claim job, ghi inbox, cập nhật state |
| Reconciliation job | List/head/delete theo scope được duyệt | Có thể kiểm tra DLQ metadata | Đọc state, sửa trạng thái có audit |
| Admin/support | Quyền vận hành có kiểm soát | Inspect/redrive theo role | Read-only hoặc break-glass |

Một component không cần quyền thì không cấp quyền đó. Ví dụ outbox relay không cần đọc file; worker không cần quyền tạo bucket hoặc thay đổi IAM policy.

### 12.2. AWS IAM

Dùng ECS task role, EKS Pod Identity/IRSA hoặc EC2 instance profile. Policy giới hạn bucket/prefix và queue ARN:
- Uploader: `s3:PutObject` trên prefix upload.
- Worker: `s3:GetObject` trên source prefix và `s3:PutObject` trên result prefix.
- Relay: `sqs:SendMessage` trên queue đích.
- Consumer: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility` nếu cần.
- Secret reader: `secretsmanager:GetSecretValue` và `kms:Decrypt` chỉ khi secret/KMS policy yêu cầu.

S3 bucket policy, KMS key policy và IAM identity policy phải cho phép nhất quán. Không cấp `s3:*` trên mọi bucket hoặc `sqs:*` trên mọi queue.

### 12.3. Azure RBAC và Managed Identity

Dùng Managed Identity hoặc Workload Identity. Phân biệt management-plane role với data-plane role. Ví dụ:
- Upload API nhận quyền tạo blob trong container/prefix cần thiết.
- Worker nhận quyền đọc blob và ghi kết quả.
- Relay nhận quyền Service Bus Data Sender.
- Consumer nhận quyền Service Bus Data Receiver.
- Secret reader nhận quyền đọc đúng secret trong Key Vault.

Role assignment nên scope nhỏ nhất có thể. SAS token là bearer secret; giới hạn resource, permission, protocol và expiry. Không dùng account key dài hạn trong application config nếu identity-based auth được hỗ trợ.

### 12.4. Google Cloud IAM

Dùng service account/workload identity riêng cho API, relay và worker:
- Uploader có quyền tạo object trong bucket/prefix.
- Worker có quyền đọc source object và tạo result object.
- Relay có Pub/Sub Publisher trên topic.
- Consumer có Pub/Sub Subscriber trên subscription.
- Workload có quyền Cloud SQL connection và database user privilege riêng.
- Secret reader có Secret Accessor trên secret cụ thể.

IAM permission mở kết nối Cloud SQL không tự cấp quyền SQL. Database role vẫn phải giới hạn schema/table/operation.

### 12.5. Encryption và private networking

Bảo vệ dữ liệu khi truyền bằng TLS và khi lưu bằng server-side encryption/KMS phù hợp. Dùng private endpoint/VPC endpoint khi yêu cầu network isolation; xác minh DNS, route, firewall, NAT và security group/NSG.

Nếu dùng customer-managed key, tách quyền dùng key khỏi quyền quản trị key. Rotation key, disable key hoặc mất key có thể làm object không đọc được; runbook phải tính tới dependency này.

### 12.6. Không để secret trong object metadata hoặc message

Object metadata và queue message có thể bị hiển thị trong log, console, event archive hoặc support tool. Không lưu password, access token, pre-signed URL, private key hoặc PII không cần thiết ở đó. Chỉ lưu resource reference và identifier đã được phân loại.

### 12.7. Tenant isolation và object authorization

Không tin tenant ID trong message nếu chưa đối chiếu với database/identity. Worker phải xác minh document thuộc tenant hợp lệ và object key nằm trong namespace/prefix được phép. Không tạo object key bằng cách nối trực tiếp input path của client; canonicalize và chặn path traversal.

Pre-signed URL chỉ cấp quyền cho object key cụ thể, operation cụ thể và thời gian ngắn. Không trả URL đọc source object cho user nếu chưa kiểm tra authorization; signed URL không thay thế policy nghiệp vụ.

### 12.8. Retention, legal hold và data deletion

Database row bị xóa không có nghĩa object và các version đã bị xóa. Xây dựng deletion workflow:
1. Đánh dấu document `DELETE_PENDING`.
2. Ngăn worker mới claim và phát cancellation event nếu cần.
3. Xóa object version/result theo retention policy.
4. Xác minh provider trả kết quả phù hợp.
5. Ghi trạng thái `DELETED` và audit.
6. Retry/reconcile khi một phần delete thất bại.

Tôn trọng legal hold, backup, retention và object lock. Không xóa ngay source object sau khi worker xử lý thành công nếu cần replay, audit hoặc điều tra.

## 13. Performance, capacity và cost

### 13.1. Không chuyển bytes qua queue

Queue message chỉ chứa object pointer và metadata nhỏ. Việc này tránh giới hạn payload, giảm network overhead và cho phép worker tải theo stream/range. Đảm bảo object không bị lifecycle policy xóa trước khi message được xử lý.

### 13.2. Multipart upload và streaming

File lớn cần multipart/resumable upload. Chọn part size, concurrency và retry theo provider. Hạn chế số upload đồng thời để không làm cạn connection, file descriptor hoặc temporary disk.

Nếu worker chỉ cần đọc một phần object, dùng range request khi format hỗ trợ. Với gzip/archive, cân nhắc streaming decompression và giới hạn expanded size.

### 13.3. Queue backpressure

Scale consumer theo backlog/oldest message age nhưng giữ giới hạn database connection, object API quota và downstream capacity. Không scale theo queue depth đơn lẻ nếu mỗi message tiêu tốn rất nhiều memory/CPU hoặc kết nối database.

Có thể giới hạn:
- Max concurrent messages.
- Batch size.
- Worker replica count.
- Max in-flight processing per tenant.
- Per-provider request rate.
- Database pool size và transaction duration.

Khi downstream chậm, giảm consumer concurrency hoặc pause subscription theo khả năng provider; để queue buffer thay vì tạo retry storm.

### 13.4. Database capacity

Tổng connection là tổng của API replicas, worker replicas, relay, migration và monitoring. Pool per instance phải tính theo maximum autoscale count, không chỉ số replica bình thường.

Dùng index cho trạng thái/lease/outbox query; partition/archive outbox khi tăng volume. Polling relay nên dùng batch nhỏ và index phù hợp, không full table scan mỗi chu kỳ.

### 13.5. Cost model

Chi phí gồm:
- Storage capacity, object version, request PUT/GET/LIST, retrieval tier và egress.
- Queue request, message retention, subscription/throughput unit hoặc event routing.
- Database compute, storage, IOPS, backup và connection capacity.
- KMS operation, private networking/NAT, logging, tracing và data transfer giữa AZ/region.
- Worker execution time, memory/CPU và retry duplicate.

Không chỉ so sánh giá mỗi GB. Một thiết kế có quá nhiều HEAD/LIST, polling hoặc duplicate processing có thể tốn hơn storage. Theo dõi cost theo tenant/workflow/resource tag nếu cardinality và privacy policy cho phép.

### 13.6. Region và data residency

Đặt bucket/container, queue và database gần nhau để giảm latency/egress. Xác định data residency, replication, backup region và disaster recovery. Cross-region event delivery có thể tăng latency/cost và có yêu cầu pháp lý riêng.

Không giả định object replication tự replicate database metadata hoặc queue state. Disaster recovery phải định nghĩa cách khôi phục ba thành phần và cách replay/reconcile event sau failover.

## 14. Kiểm thử end-to-end

### 14.1. Unit test

Kiểm tra domain/state transition:
- Upload intent chỉ tạo một document cho cùng idempotency key.
- Finalize chỉ đổi `PENDING_UPLOAD` sang `STORED` một lần.
- Message được tạo với object version/checksum đúng.
- Event stale không làm lùi state.
- Consumer duplicate không chạy side effect lần hai.
- Permanent input error chuyển sang `FAILED`; transient error giữ retryable state.

Mock ObjectStore/WorkQueue ở unit test của application service. Kiểm tra interaction như publish outbox sau commit ở integration test thay vì chỉ verify mock call trong cùng transaction.

### 14.2. Database integration test

Dùng PostgreSQL Testcontainers hoặc database tương thích để kiểm tra:
- Transaction rollback không để lại business row/outbox row nửa vời.
- Unique constraint idempotency/inbox.
- Lock/lease và optimistic version.
- Outbox relay claim nhiều worker.
- Transaction commit trước ack.
- Reconciliation query và index.

Testcontainers kiểm tra database thật trong container; nó không chứng minh IAM, object storage hoặc queue semantics của cloud provider.

### 14.3. Provider emulator và fake service

Có thể dùng:
- LocalStack cho một số S3/SQS flows.
- Azurite cho Azure Blob Storage; Service Bus emulator có giới hạn và không thay thế mọi tính năng cloud.
- Pub/Sub emulator cho publisher/subscriber flow.
- Fake ObjectStore/WorkQueue để test business logic.

Emulator không chứng minh permission thật, encryption key policy, private endpoint, lifecycle, quota, cross-region behavior hoặc provider retry semantics. Đọc giới hạn emulator trước khi coi test là contract pass.

### 14.4. Staging contract test

Trên mỗi provider staging, kiểm tra:
1. Workload identity có đúng role cho từng resource.
2. Upload tạo đúng object metadata/version/checksum.
3. Finalize tạo một metadata row và một outbox event.
4. Relay publish đúng event envelope.
5. Consumer tải đúng object version.
6. DB state, inbox và outbox commit cùng transaction.
7. Duplicate message không lặp side effect.
8. Retry/DLQ/redrive hoạt động theo policy.
9. Object lifecycle không xóa file đang xử lý.
10. Logs/metrics không lộ secret và có correlation ID.

Dùng resource riêng có tag và cleanup policy. Không chạy test destructive trên bucket, queue hoặc database production.

### 14.5. Failure injection

Mô phỏng crash tại các boundary:
- Sau upload object nhưng trước DB finalize.
- Sau DB commit nhưng trước outbox publish.
- Sau queue publish nhưng trước mark-published.
- Sau object download nhưng trước xử lý.
- Sau result upload nhưng trước DB commit.
- Sau DB commit nhưng trước queue ack.
- Trong lúc lease hết hạn và worker thứ hai claim.
- Trong lúc database failover hoặc provider throttling.

Mỗi test cần chứng minh trạng thái cuối có thể reconcile, không mất dữ liệu đã xác nhận và không tạo side effect nghiệp vụ lặp.

## 15. Observability và runbook vận hành

### 15.1. Correlation xuyên suốt workflow

Một request upload có thể đi qua API, object storage, database, outbox relay, queue, worker và downstream service. Tạo correlation ID và propagate qua event/message. Ghi event ID, document ID, provider request ID và processing attempt để có thể nối các bước.

Log nên ghi:
- document ID và event ID.
- object key đã mask hoặc logical reference theo policy.
- object version/generation và checksum đã phân loại.
- queue/topic/subscription logical name.
- processing attempt, lease owner và duration.
- state transition, error category và provider request ID.
- correlation/trace ID.

Không log pre-signed URL, SAS token, authorization header, database connection string hoặc file content. Nếu document ID/tenant ID có tính nhạy cảm, dùng hashing/masking phù hợp.

### 15.2. Metrics

| Metric | Ý nghĩa |
| --- | --- |
| Upload success/failure | Tỷ lệ upload và finalize thành công |
| Upload duration/bytes | Latency và throughput object storage |
| Orphan object count/age | Object không được metadata tham chiếu |
| Outbox backlog/oldest age | Event chờ publish |
| Publish retry/error | Queue unavailable hoặc permission/quota |
| Queue depth/oldest message age | Worker có theo kịp producer không |
| Consumer success/failure/duration | Hiệu quả xử lý |
| Duplicate/inbox hit count | Mức redelivery hoặc duplicate publish |
| Lease expired/reclaimed | Worker crash hoặc processing lâu |
| DLQ depth/age | Poison message và lỗi chưa phục hồi |
| DB pool active/pending | Database connection pressure |
| Reconciliation corrections | Mức lệch trạng thái giữa các store |

Metric label cần cardinality thấp. Không dùng object key, user ID, tenant ID tùy ý hoặc event ID làm label. Dùng trace/log để tra cứu chi tiết.

### 15.3. Distributed tracing

Tạo span cho:
- HTTP upload/finalize.
- Object storage PUT/HEAD/GET.
- DB transaction.
- Outbox relay publish.
- Queue receive/ack.
- Worker processing và downstream call.

Queue không phải lúc nào cũng propagate W3C trace context tự động. Nếu cần, đưa trace context qua message attributes/headers theo provider và kiểm soát kích thước. Không đưa secret hoặc PII vào baggage.

### 15.4. Runbook: object đã upload nhưng document vẫn PENDING_UPLOAD

1. Kiểm tra upload intent, expiry và upload ID.
2. HEAD object key/version để xác minh object tồn tại.
3. Kiểm tra checksum, size và content type theo policy.
4. Xác định finalize API có timeout hoặc DB transaction rollback không.
5. Nếu object hợp lệ, chạy finalize idempotent theo document/upload ID.
6. Nếu object không hợp lệ hoặc intent expired, quarantine/xóa theo cleanup policy.
7. Ghi audit và xác minh outbox event chỉ được tạo một lần.

Không đổi trạng thái database thành STORED chỉ vì object key tồn tại; phải xác minh đúng tenant, version và checksum.

### 15.5. Runbook: document STORED nhưng queue không có message

1. Kiểm tra outbox row và published timestamp.
2. Kiểm tra relay health, lease và retry schedule.
3. Kiểm tra queue/topic destination và provider API error.
4. Xác minh relay identity có quyền publish.
5. Kiểm tra throttling/quota và network/DNS/TLS.
6. Cho relay retry từ outbox; không tự tạo event ID mới.
7. Xác minh consumer nhận đúng event sau khi publish.

Nếu publish có kết quả không rõ do timeout, relay có thể gửi duplicate. Consumer phải dùng event ID deduplication.

### 15.6. Runbook: queue backlog tăng

1. Kiểm tra oldest message age, queue depth và DLQ.
2. Kiểm tra worker replica/concurrency và processing duration.
3. Kiểm tra database pool, lock wait và query latency.
4. Kiểm tra object GET latency, throttling và network egress.
5. Xác định message lỗi theo schema, authorization hay dependency.
6. Giảm producer rate hoặc worker concurrency nếu downstream đang quá tải.
7. Tăng consumer capacity có giới hạn nếu DB/object service còn headroom.
8. Theo dõi backlog drain rate và cost sau khi phục hồi.

Không scale worker vô hạn khi bottleneck là database connection hoặc provider quota.

### 15.7. Runbook: DLQ có message

1. Lấy event ID, document ID, failure category và delivery count.
2. Kiểm tra state database và object version còn hợp lệ không.
3. Xác định lỗi permanent hay transient.
4. Sửa schema/permission/data/dependency trước khi redrive.
5. Dùng redrive tool có audit và giới hạn batch.
6. Giữ nguyên event ID hoặc idempotency key khi replay.
7. Xác minh document hoàn tất và DLQ giảm.
8. Lưu nguyên nhân gốc để sửa producer/consumer hoặc policy.

Không chỉnh payload thủ công để ép message qua xử lý nếu chưa xác minh tính toàn vẹn và audit.

### 15.8. Runbook: object mồ côi hoặc metadata thiếu

Chạy reconciliation theo object inventory và database reference với grace period. Phân loại orphan:
- Upload intent chưa finalize.
- Result object upload thành công nhưng DB commit thất bại.
- Object version cũ không còn được tham chiếu.
- Object bị xóa thủ công hoặc lifecycle policy xóa sớm.

Chỉ xóa sau khi kiểm tra version, retention, legal hold, in-flight lease và backup. Với object inventory lớn, dùng batch/inventory report thay vì LIST toàn bucket trên mỗi lần chạy.

## 16. Failure matrix và trạng thái phục hồi

| Điểm lỗi | Trạng thái có thể còn lại | Cách phục hồi |
| --- | --- | --- |
| Upload object thất bại | Intent PENDING_UPLOAD, object thiếu/partial | Retry upload hoặc expire intent; abort multipart |
| Upload xong, DB finalize lỗi | Object tồn tại, metadata chưa STORED | Retry finalize hoặc cleanup orphan sau grace period |
| DB finalize commit, relay chưa chạy | STORED + outbox unpublished | Relay tiếp tục publish |
| Publish thành công, relay chưa mark | Message có thể tồn tại, outbox vẫn pending | Publish lại; consumer deduplicate |
| Worker crash trước claim | Message redelivery, document chưa PROCESSING | Worker khác claim |
| Worker crash sau claim | Lease PROCESSING hết hạn | Reclaim với fencing/version check |
| Result upload xong, DB commit lỗi | Result object orphan | Retry deterministic key hoặc cleanup |
| DB commit xong, ack lỗi | State completed, message redelivery | Inbox/state check rồi ack |
| Source object bị xóa sớm | Metadata trỏ tới object missing | Alert, restore version/backup hoặc FAILED |
| Database outage | Queue backlog tăng, outbox relay dừng | Restore DB, giới hạn consumer, replay/reconcile |

Mỗi hàng cần có alert, owner, runbook và recovery objective. Định nghĩa rõ dữ liệu nào đã được xác nhận với client và trạng thái nào có thể retry.

## 17. Các quyết định kiến trúc quan trọng

### 17.1. Outbox hay storage event?

Dùng outbox khi metadata database và business event phải nhất quán. Dùng native storage event khi object creation từ nhiều producer là trigger chính. Có thể kết hợp: storage event kích hoạt ingest service; ingest service xác minh object rồi ghi metadata/outbox. Tránh publish cùng logical event từ hai nguồn mà không có deduplication key chung.

### 17.2. Queue hay pub/sub?

Dùng work queue cho competing worker pool. Dùng topic/pub-sub/event bus khi nhiều consumer độc lập cần nhận event. Một event có thể được route tới nhiều subscription; mỗi subscription cần idempotency riêng vì mỗi consumer có tiến độ và retry khác nhau.

### 17.3. Một database hay database riêng cho từng service?

Một database có thể đơn giản hóa transaction outbox và metadata trong service nhỏ. Khi tách bounded context, mỗi service sở hữu database riêng; không dùng cross-service database transaction. Trao đổi qua event/API và dùng saga/reconciliation cho workflow liên service.

### 17.4. Upload direct hay proxy qua backend?

Direct upload phù hợp file lớn, nhiều client và throughput cao; cần pre-signed URL, finalize verification và CORS policy. Proxy qua backend phù hợp file nhỏ hoặc cần streaming validation trước khi lưu; cần capacity, timeout và backpressure. Có thể dùng hybrid theo size/policy.

### 17.5. Lưu metadata trong object hay database?

Object metadata phù hợp thuộc tính kỹ thuật nhỏ, không cần query quan hệ. Database phù hợp owner, status, ACL, lifecycle, business state và query. Tránh hai source of truth cho cùng một business field. Nếu duplicate metadata để phục vụ search, xác định cách cập nhật và reconcile.

## 18. Checklist trước production

1. **Ownership:** xác định owner của object, queue, database, outbox và consumer.
2. **Data model:** document ID, object key/version, checksum, tenant và status có schema rõ.
3. **Upload:** direct/proxy flow, size limit, streaming, multipart abort và finalize idempotent.
4. **Verification:** HEAD/version/checksum/content type được xác minh trước khi phát event.
5. **Transaction:** metadata state và outbox row commit cùng transaction.
6. **Relay:** polling/CDC, lease, retry, idempotent publish và retention được thiết kế.
7. **Message:** payload nhỏ, event ID, schema version, correlation ID và object pointer.
8. **Consumer:** claim/lease, inbox unique key, state transition và ack sau commit.
9. **Object result:** key/version deterministic hoặc attempt-specific; cleanup orphan có grace period.
10. **Retry:** phân loại transient/permanent, backoff/jitter, max attempts và DLQ.
11. **Ordering:** aggregate sequence/session/FIFO chỉ bật khi business invariant yêu cầu.
12. **Identity:** API, relay, worker và reconciliation có role riêng theo resource.
13. **Secrets:** không có static key, SAS/pre-signed URL hoặc credential trong code/log/message.
14. **Network:** TLS, private endpoint, DNS, firewall, egress và data residency được kiểm tra.
15. **Capacity:** worker concurrency, queue backlog, database pool và object API quota có giới hạn.
16. **Lifecycle:** retention, versioning, legal hold, delete và multipart cleanup được định nghĩa.
17. **Testing:** unit, database integration, emulator và staging contract/failure injection.
18. **Observability:** correlation, outbox age, queue age, DLQ, orphan và reconciliation metrics.
19. **Recovery:** runbook cho upload gap, publish gap, backlog, DLQ, lease expiry và orphan.
20. **Cost:** request, storage version, egress, queue, DB, KMS, logs và worker retries được theo dõi.

## 19. Bài tập tự luyện

1. Vẽ sequence upload file qua Spring Boot, object storage, database và queue; xác định transaction boundary.
2. Thiết kế bảng document, outbox và inbox có unique constraint phù hợp.
3. Viết upload intent/finalize flow dùng pre-signed URL; kiểm tra checksum và object version.
4. Triển khai transactional outbox polling relay; mô phỏng crash sau publish nhưng trước mark-published.
5. Viết consumer dùng lease và inbox; chứng minh message duplicate không tạo side effect lặp.
6. Thiết kế result object key deterministic theo source version và processor version.
7. Triển khai AWS flow S3 + SQS + RDS; cấp IAM policy riêng cho API, relay và worker.
8. Triển khai Azure flow Blob + Service Bus + Azure Database; dùng Managed Identity và role data-plane.
9. Triển khai Google Cloud flow GCS + Pub/Sub + Cloud SQL; dùng Workload Identity và Pub/Sub IAM.
10. So sánh native storage event với application outbox; xử lý duplicate và out-of-order event.
11. Mô phỏng object upload thành công nhưng database finalize lỗi; xây reconciliation cleanup.
12. Mô phỏng database commit thành công nhưng queue publish lỗi; chứng minh outbox relay khôi phục.
13. Mô phỏng worker crash sau DB commit nhưng trước ack; chứng minh inbox/state check.
14. Thiết kế DLQ redrive có audit, batch limit và giữ event ID.
15. Tính database connection budget khi API và worker autoscale tới maximum replica.
16. Xây dashboard cho outbox backlog, oldest queue message, DLQ, orphan object và processing latency.
17. Thiết kế deletion workflow tôn trọng versioning, retention và legal hold.
18. Viết runbook phục hồi khi object, queue và database có trạng thái không đồng nhất.

**Tiêu chí hoàn thành:** người học xây dựng được một workflow Spring Boot phối hợp object storage, queue và database; đảm bảo metadata/outbox atomic trong database; xử lý duplicate/retry bằng inbox/idempotency; phân biệt đúng behavior của AWS, Azure và Google Cloud; kiểm thử được các failure boundary và vận hành workflow bằng metric/runbook.

## Tài liệu tham khảo

- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/current/reference/html/index.html): tích hợp S3, SQS và AWS SDK trong Spring.
- [Amazon S3 User Guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html): object, multipart upload, versioning, lifecycle và event notification.
- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html): visibility timeout, delivery, FIFO, DLQ và redrive.
- [AWS RDS Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html): database connectivity, backup và operational practices.
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): Spring integration với Blob Storage, Service Bus và Azure identity.
- [Azure Blob Storage documentation](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction): object/container, upload và lifecycle.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview): queue/topic, lock, settlement, duplicate detection và DLQ.
- [Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/): connectivity, identity và database operations.
- [Spring Cloud GCP Reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html): tích hợp Cloud Storage, Pub/Sub và Cloud SQL.
- [Google Cloud Storage documentation](https://cloud.google.com/storage/docs/introduction): object, generation, upload và lifecycle.
- [Google Cloud Pub/Sub documentation](https://cloud.google.com/pubsub/docs/overview): topic, subscription, acknowledgment, retry và dead-letter.
- [Cloud SQL documentation](https://cloud.google.com/sql/docs/introduction): database connectivity và Cloud SQL connectors.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): lưu business state và event trong cùng database transaction.
- [Idempotent Consumer pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html): xử lý message delivery lặp an toàn.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): quản lý cấu hình và secret reference.
