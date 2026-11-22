# Xử lý payload lớn qua claim check

> **Chương:** Claim check  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **đưa payload lớn ra khỏi luồng message, thay bằng một tham chiếu nhỏ và khôi phục nội dung ở đúng bước cần dùng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mẫu **Claim Check** của Enterprise Integration Patterns (EIP), vai trò của **check-in**, **claim token/reference** và **check-out**.
2. Nhận biết khi nào nên thay payload lớn bằng tham chiếu thay vì đẩy toàn bộ byte qua mọi Router, Channel, Transformer hoặc broker.
3. Phân biệt **Claim Check dựa trên Spring Integration MessageStore** với **tham chiếu object/blob storage** cho dữ liệu rất lớn; hiểu chúng cùng ý tưởng nhưng khác khả năng vận hành.
4. Thiết kế metadata tham chiếu an toàn: `tenantId`, `objectKey`, `contentLength`, `checksum`, `contentType`, `schemaVersion`, `businessCorrelationId`.
5. Viết một service Java thực hiện **streaming check-in/check-out**, rồi đưa nó vào flow Spring Integration, giữ rõ ranh giới giữa I/O, dispatch và nghiệp vụ.
6. Phân tích vòng đời tham chiếu: **ghi thành công nhưng không publish**, **publish nhưng mất object**, **redelivery**, **xóa quá sớm**, **TTL/reaper**, **late consumer** và **retry có side effect**.
7. Thiết kế kiểm thử và observability về toàn vẹn dữ liệu, phân quyền, dung lượng, thời gian lưu, idempotency và khôi phục khi hệ thống lỗi.

## 2. Vấn đề: payload 50 MiB đi qua một flow nhiều nhánh

Giả sử ứng dụng nhận tệp tài liệu nghiệp vụ có kích thước 50 MiB. Nó cần đi qua bước xác thực, phân loại, Router, kiểm tra chống trùng, gửi thông báo và một consumer cuối phân tích nội dung.

Nếu mỗi bước chuyển nguyên payload `byte[]`:

~~~text
HTTP upload 50 MiB
    |
    v
Validate -> Enrich -> Router -> Queue -> Analytics -> Archive
          (tất cả đều nhìn thấy payload lớn)
~~~

Một số vấn đề xuất hiện:

- **Bộ nhớ:** nhiều bản message trong RAM, nhất là khi queue giữ backlog, có thể làm tăng heap.
- **I/O và network:** serialization/copy dữ liệu giữa các channel, broker hoặc dịch vụ lặp lại nhiều lần.
- **Giới hạn broker:** một số transport áp kích thước message tối đa; payload quá lớn gây lỗi publish hoặc chi phí cấu hình cao.
- **Latency:** các bước chỉ cần metadata vẫn phải mang lượng byte lớn.
- **Bảo mật:** payload nhạy cảm có thể bị nhân bản sang nhiều nơi không cần quyền đọc toàn bộ.
- **Retry/replay:** gửi lại nguyên 50 MiB chỉ để thực thi một bước metadata rất lãng phí.

**Claim Check** thay nội dung lớn bằng **một “phiếu nhận” nhỏ**. Nơi thật sự cần nội dung sẽ dùng phiếu ấy để lấy dữ liệu từ kho được quản lý.

~~~mermaid
flowchart LR
    A["Inbound: payload lớn"] --> CK["Check-in: lưu dữ liệu"]
    CK --> ST[("Payload / Object Store")]
    CK --> REF["Message<ClaimReference> nhỏ"]
    REF --> F["Filter / Router / Enricher"]
    F --> Q["Queue / Broker"]
    Q --> CO["Check-out khi thực sự cần"]
    ST -.->|"Đọc theo key đã xác minh"| CO
    CO --> H["Consumer xử lý nội dung"]
    H --> CL["ACK / cleanup theo policy"]
~~~

**Điểm cần nhớ:** Claim Check **không làm dữ liệu nhỏ đi**. Nó **thay vị trí lưu** của phần lớn nội dung và chuyển trong message một tham chiếu đủ để truy xuất về sau. Tổng byte phải lưu và đọc vẫn tồn tại; chi phí được phân bổ cho nơi phù hợp hơn.

## 3. Claim Check của EIP hoạt động thế nào?

Trong EIP, Claim Check gồm ba khái niệm:

1. **Check-in:** nhận message/payload gốc, lưu phần cần giữ vào một kho và sinh claim token.
2. **Thay thế:** chuyển một message nhẹ mang token/reference đi qua các bước không cần nội dung lớn.
3. **Check-out:** dùng token để lấy lại message/payload khi đến đúng consumer; có chính sách giữ hay xóa dữ liệu sau đó.

~~~text
Original:
  payload = LargeDocument(50 MiB)
  headers = businessCorrelationId, tenant, contentType, ...

Check-in:
  store[key-123] = original payload or original message

Traveling message:
  payload = ClaimReference(key-123, length, digest, ...)
  headers = limited routing / tracing metadata

Check-out:
  retrieve store[key-123] -> original payload/message
  validate reference, permissions and integrity
  continue downstream processing
~~~

**Hai biến thể phải phân biệt:**

- **Message-store claim check:** lưu **cả Message** với những headers cần thiết; token thường tra theo ID message đã lưu. Nó gần sát mẫu built-in của Spring Integration.
- **Blob/object-store claim reference:** lưu **binary body** (hoặc tài liệu lớn) bên ngoài, message đi tiếp là một DTO metadata/tham chiếu. Đây là cách mở rộng cho file rất lớn, nhiều instance và consumer phân tán.

Cả hai đều theo EIP Claim Check, nhưng **không nên lấy một ví dụ MessageStore in-memory rồi tuyên bố nó phù hợp ngay cho payload hàng trăm MiB và tải production**.

### 3.1. Khác các EIP liên quan

| Pattern | Mục đích | Ví dụ |
| --- | --- | --- |
| **Claim Check** | Thay payload lớn bằng token, truy xuất khi cần | Tài liệu 50 MiB → `ClaimReference` |
| **Content Enricher** | Lấy thêm thông tin còn thiếu vào message | Tra hồ sơ khách hàng qua ID |
| **Transformer** | Chuyển biểu diễn/schema của payload | JSON đối tác → canonical DTO |
| **Filter** | Chặn message không đủ điều kiện | Chỉ xử lý file có loại dữ liệu cho phép |
| **Router** | Chọn nhánh xử lý | MIME hợp lệ → image/text pipeline |
| **Recipient List** | Gửi đến nhiều recipient | Metadata event → audit và indexing |
| **Splitter** | Chia dữ liệu thành các phần độc lập | Tách danh sách tài liệu thành các task |
| **Aggregator** | Tổng hợp các message con | Gom kết quả xử lý từng trang |
| **Gateway/Adapter** | Kết nối transport/hệ thống ngoài | HTTP upload, broker publish, object-store API |

**Không nhầm Claim Check với Content Enricher:** Enricher lấy dữ liệu để **bổ sung** cho một message; check-out dùng một token để **khôi phục phần đã chủ động cất đi**. Một flow có thể dùng cả hai pattern nhưng phải quản lý lifecycle riêng.

## 4. Khi nào Claim Check phù hợp — và khi nào không?

### 4.1. Nên cân nhắc Claim Check khi

- Payload lớn hơn hoặc tiệm cận giới hạn an toàn của transport/broker.
- Nhiều bước ở giữa chỉ cần metadata và **không cần nội dung byte**.
- Cùng payload được nhiều consumer đọc có kiểm soát, tránh gửi nhiều bản lớn.
- Cần tách tốc độ upload khỏi tốc độ xử lý để kiểm soát backlog.
- Cần kiểm toán việc **ai đã lấy nội dung, lúc nào, theo execution nào**.
- Muốn retry metadata/dispatch mà không upload lại toàn bộ payload.

### 4.2. Không nên dùng theo phản xạ

- Payload nhỏ và flow ngắn: kho ngoài có thể tăng độ phức tạp và latency mà không có lợi rõ.
- Payload phải đọc ở **mọi bước**: sẽ phát sinh check-out lặp và network round-trip, có thể chậm hơn truyền trực tiếp.
- Không có hệ thống lưu trữ bền, kiểm tra quyền và cleanup: token dễ thành **tham chiếu mồ côi** hoặc rò dữ liệu.
- Luồng cần xử lý streaming một lần, không có yêu cầu truy cập lại: có thể dùng stream trực tiếp với giới hạn và backpressure thay vì lưu rồi lấy.
- Tài liệu phải duy trì transaction xuyên hai hệ thống: Claim Check **không tự tạo atomic transaction** giữa object store và broker.

### 4.3. Bảng đánh đổi

| Tiêu chí | Mang payload trực tiếp | Claim Check |
| --- | --- | --- |
| Message trên broker | Có thể rất lớn | Nhỏ, chủ yếu metadata |
| Memory ở bước trung gian | Dễ cao nếu giữ nhiều bản | Thường thấp hơn |
| Số lần đọc payload | Có thể qua nhiều đoạn của flow | Đọc từ store khi cần |
| Độ phức tạp | Ít thành phần hơn | Cần store, ref lifecycle, cleanup |
| Latency của consumer cần bytes | Không cần fetch ngoài | Thêm thao tác check-out |
| Retry/replay | Có thể phát lại bytes lớn | Phát lại reference nhỏ |
| Bảo mật | Payload đi qua nhiều channel | Cần ACL/tenant scoping cho store |
| Rủi ro dữ liệu | Message/broker retention | Orphan, dangling reference, TTL, object corruption |
| Durability | Theo broker/transport | Theo cả message broker và payload store |

## 5. Thiết kế contract ClaimReference nhỏ và rõ ràng

Trong một hệ thống nhiều service, **đừng chỉ gửi một chuỗi ID tùy ý** nếu consumer cần biết và kiểm tra hợp đồng nguồn. Ví dụ:

~~~json
{
  "documentId": "DOC-1201",
  "tenantId": "tenant-a",
  "objectKey": "documents/tenant-a/4f...d2",
  "contentType": "application/pdf",
  "contentLength": 52428800,
  "sha256": "hex-digest-of-original-bytes",
  "schemaVersion": "claim-ref-v1"
}
~~~

Đây là **schema minh họa**, không phải JSON có khóa/digest hợp lệ thật. `objectKey` là định danh do **server sinh**, không nhận trực tiếp từ file name hoặc đường dẫn tùy ý của người dùng.

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| `documentId` | Business ID của tài liệu | Dùng correlation, không nhất thiết làm storage key |
| `tenantId` | Biên phân quyền | Phải so với identity xác thực, không chỉ tin metadata |
| `objectKey` | Khóa tra object | Random/opaque, không cho path traversal/IDOR |
| `contentType` | Biểu diễn dữ liệu nguồn | Không phải bằng chứng file an toàn |
| `contentLength` | Dung lượng kỳ vọng | Xác nhận khi ghi và khi đọc |
| `sha256` | Kiểm tra tính toàn vẹn | Digest không thay thế chữ ký hoặc authorization |
| `schemaVersion` | Phiên bản của claim reference | Tương thích khi phát triển service |
| `businessCorrelationId` | Truy vết end-to-end | Có thể đặt trong header có kiểm soát |
| `expiresAt` (nếu có) | Hạn truy xuất | Đừng cho hết hạn trước cửa sổ retry/replay |

### 5.1. Token không phải quyền truy cập

Một object key khó đoán **không tự động là quyền hợp lệ**. Consumer phải được xác thực và kiểm tra `tenantId`/vai trò/operation với dữ liệu có thẩm quyền. Tránh xây endpoint `GET /objects/{id}` chỉ kiểm tra ID tồn tại; đó là nguy cơ **IDOR** (Insecure Direct Object Reference).

Nếu dùng pre-signed URL, nó hoạt động gần như một **bearer credential** trong thời hạn hiệu lực. Chỉ cấp cho người/đích cần quyền, đặt TTL ngắn, hạn chế method/phạm vi, tránh log URL đầy đủ và kiểm soát khả năng chia sẻ.

### 5.2. Digest không đồng nghĩa chữ ký số

`SHA-256` hỗ trợ phát hiện bytes thay đổi khi check-out. Nhưng nếu kẻ tấn công có thể sửa **cả object và digest trên reference**, việc so sánh hai giá trị ấy không chứng minh tính xác thực nguồn. Với dữ liệu cần chống giả mạo, bổ sung **chữ ký/HMAC hoặc metadata bất biến được bảo vệ bởi nguồn tin cậy**, theo threat model cụ thể.

### 5.3. Content-Type vẫn cần xác minh

`contentType=application/pdf` là metadata mô tả; một file có thể được khai sai loại. Với file nhạy cảm, cần định dạng được phép, giới hạn kích thước, kiểm tra cấu trúc hoặc quét mã độc theo quy định trước khi chuyển đến parser, không chỉ dựa vào tên file hay MIME client gửi.

## 6. Một vòng đời mẫu: upload → store → reference → consume → cleanup

~~~mermaid
sequenceDiagram
    participant U as Upload Client
    participant I as Ingress
    participant S as Object Store
    participant B as Broker
    participant C as Consumer
    participant M as Metadata/State Store
    U->>I: Upload (stream)
    I->>I: AuthN/size/type validation
    I->>S: PUT (server-generated key)
    S-->>I: saved key, size, checksum
    I->>M: Record reference + lifecycle
    I->>B: Publish small ClaimReference
    B-->>C: Deliver ClaimReference
    C->>M: Validate tenant/state/claim
    C->>S: GET object by authorized key
    S-->>C: Content stream
    C->>C: Verify length/digest + process
    C->>M: Record result, ACK intent
    C-->>B: ACK per transport
    M->>S: Cleanup when retention allows
~~~

**Chú ý:** các thao tác PUT object, ghi metadata và publish broker **không mặc định nằm trong một transaction ACID chung**. Vì vậy phải có cách xử lý **partial failure**.

### 6.1. Tình huống dữ liệu được lưu nhưng reference chưa phát đi

~~~text
PUT object success
  |
  v
Process crashed before broker publish
  |
  v
Orphan object: dữ liệu có nhưng chưa có consumer biết key
~~~

Cách xử lý:

- Lưu `UploadState=STORED_NOT_PUBLISHED` cùng ID thao tác có thể retry.
- Dùng **outbox pattern** nếu metadata store và outbox có thể ghi atomic, sau đó publisher phát reference.
- Có job tìm object **không được tham chiếu** sau khoảng grace period và xóa an toàn, thay vì xóa ngay khi thấy “chưa publish”.
- Ghi metrics `orphanCandidates`, `outboxLag`, `publicationFailures`.

### 6.2. Reference đã publish nhưng object không thể đọc

~~~text
Broker delivers reference
  |
  v
Object GET -> 404 / expired / access denied / storage outage
~~~

Đây có thể là **dangling reference**, lỗi phân quyền, sự cố hạ tầng hoặc eventual consistency. Đừng tự đánh dấu tài liệu đã xử lý thành công.

- 404 vì object bị xóa quá sớm: cần reconciliation và sửa retention policy.
- Lỗi 403: kiểm tra principal/tenant authorization, không thử “bỏ kiểm tra quyền” để chạy tiếp.
- 5xx/timeout từ object store: retry có backoff giới hạn, giữ idempotency và message visibility đúng.
- Digest/size mismatch: quarantine, cảnh báo tính toàn vẹn, không đưa bytes sang handler nghiệp vụ.

### 6.3. Consumer ACK trước khi kết thúc xử lý

Nếu consumer ACK broker ngay sau khi nhận reference, rồi process crash trước check-out, message có thể **mất cơ hội retry**. Cần định nghĩa acknowledgment theo transport:

~~~text
Receive reference
    -> Validate + fetch + verify
    -> Execute business operation idempotently
    -> Persist outcome / checkpoint
    -> ACK (hoặc outbox/transaction theo transport)
~~~

Không có một thứ tự ACK duy nhất phù hợp mọi hệ thống, nhưng phải tránh “ACK thành công” trong khi chưa có gì bảo đảm downstream sẽ tiếp tục.

## 7. Spring Integration Claim Check và MessageStore

Spring Integration có các thành phần hỗ trợ **Claim Check In/Out** trên nền **MessageStore**. Về mặt ý tưởng:

~~~text
Message<LargePayload>
      |
      v
Claim Check In Transformer
      |-- store original Message in MessageStore
      |-- emit claim-check identifier
      v
Message<ClaimId>
      |
   ... routing, delivery ...
      |
      v
Claim Check Out Transformer
      |-- lookup original Message by identifier
      v
Message<LargePayload>
~~~

Có thể sử dụng `ClaimCheckInTransformer` / `ClaimCheckOutTransformer` hoặc các cấu hình DSL tương ứng tùy **phiên bản Spring Integration**. Trong thực tế, cần xác minh API và chính sách remove khi check-out trên phiên bản project đang dùng.

**Giới hạn quan trọng:** một MessageStore đơn giản **in-memory** chỉ chuyển payload khỏi message đang lưu thông, **không giảm tổng dữ liệu resident trong JVM** và không khôi phục dữ liệu sau process restart. Nó hữu ích để hiểu pattern hoặc cho những trường hợp vừa phải, nhưng **không tự giải quyết payload 50 MiB trên nhiều node**.

### 7.1. MessageStore thông thường lưu message như thế nào?

Ví dụ minh họa API lõi của Spring Integration MessageStore với một message payload nhỏ để hiểu semantics — đây không phải cách khuyến nghị lưu file 50 MiB trong RAM:

~~~java
import java.util.UUID;
import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

MessageStore store = new SimpleMessageStore();
Message<String> original = MessageBuilder
    .withPayload("sample-payload")
    .setHeader("businessCorrelationId", "DOC-1201")
    .build();

// Lưu message nguyên gốc.
store.addMessage(original);

// Một ID của message đã lưu dùng để claim lại.
UUID id = original.getHeaders().getId();
Message<?> restored = store.getMessage(id);

if (restored == null) {
    throw new IllegalStateException("CLAIM_NOT_FOUND");
}
~~~

Ví dụ chỉ minh họa **store/lookup**; chưa có bảo mật token, multi-tenant isolation, expiration và ACK/retry. Khi cần **giữ hay xóa** sau claim, phải có chính sách và thao tác theo API MessageStore tương ứng, không xóa trước khi downstream xác nhận có thể phục hồi kết quả.

### 7.2. MessageStore khác object storage

| Khía cạnh | MessageStore-based Claim Check | External blob/object store |
| --- | --- | --- |
| Đơn vị lưu | Spring `Message<?>` và metadata | Binary object/stream, metadata lưu riêng |
| Claim ID | Thường gắn với message ID | Server-generated object key/ref |
| Phù hợp | Pattern nội bộ, payload vừa phải, group/message persistence | File lớn, dữ liệu binary, nhiều service |
| Header restore | Có thể lấy lại message đã lưu | Cần định nghĩa metadata/header projection |
| Bảo mật | ACL của store + caller boundary | IAM/ACL, tenant scoping, encryption |
| Nút nghẽn | Heap/DB/message serialization | Storage I/O, GET/PUT, request costs |
| Retention | Theo store lifecycle | Object lifecycle + metadata/outbox |
| Khả năng chia sẻ | Phụ thuộc store được cấu hình | Có thể đọc đa node theo quyền |

**Không** coi `JDBC MessageStore` là object store tối ưu cho mọi loại file lớn. Có thể lưu vào database nếu contract và tải phù hợp, nhưng với dữ liệu rất lớn cần đánh giá dung lượng, serialization, indexes, transaction, backup, replication và chi phí.

## 8. Thiết kế Java 17 cho external object store

Với payload lớn, thiết kế service **streaming** phù hợp hơn việc gọi `Files.readAllBytes(...)` rồi nhét mảng 50 MiB vào một message.

Một ranh giới minh họa:

~~~java
import java.io.IOException;
import java.io.InputStream;

record IncomingDocument(
    String documentId,
    String tenantId,
    String contentType,
    InputStream content
) {}

record StoredObject(
    String objectKey,
    long contentLength,
    String sha256
) {}

record ClaimReference(
    String documentId,
    String tenantId,
    String objectKey,
    String contentType,
    long contentLength,
    String sha256,
    String schemaVersion
) {}

interface LargePayloadStore {
    // Implementation phải giới hạn bytes trong lúc stream,
    // kiểm tra object size/digest và commit object an toàn.
    StoredObject put(String tenantId, InputStream content,
                     String contentType, long maxBytes) throws IOException;

    // Lookup phải bị ràng buộc theo tenant đã xác thực.
    InputStream open(String tenantId, String objectKey) throws IOException;

    // Chỉ cleanup khi lifecycle/retention cho phép.
    void delete(String tenantId, String objectKey) throws IOException;
}
~~~

**Giới hạn của abstraction:** interface không tự bảo đảm các yêu cầu trên. Implementation object store phải chịu trách nhiệm **upload an toàn**, metadata bền, key do server sinh, access control, hashing/verification và chính sách ghi đè. `InputStream` là tài nguyên thường **chỉ đọc một lần**, không được đẩy nó qua queue bất đồng bộ rồi hy vọng stream còn mở khi consumer dùng.

### 8.1. Metadata và giá trị bất biến

Các record trên giúp truyền DTO nhẹ, nhưng vẫn cần validation:

~~~java
import java.util.Objects;

final class ClaimValidation {
    static void validate(ClaimReference ref) {
        Objects.requireNonNull(ref, "claim");
        if (ref.documentId() == null || ref.documentId().isBlank()
            || ref.tenantId() == null || ref.tenantId().isBlank()
            || ref.objectKey() == null || ref.objectKey().isBlank()) {
            throw new IllegalArgumentException("CLAIM_IDENTITY_MISSING");
        }
        if (ref.contentLength() <= 0
            || ref.sha256() == null || !ref.sha256().matches("[0-9a-fA-F]{64}")
            || !"claim-ref-v1".equals(ref.schemaVersion())) {
            throw new IllegalArgumentException("INVALID_CLAIM_METADATA");
        }
    }
}
~~~

Ví dụ yêu cầu `contentLength > 0` vì nghiệp vụ tài liệu không cho phép file rỗng. Nếu một hệ thống có object rỗng hợp lệ, thay quy tắc theo contract. Regex digest chỉ kiểm tra **định dạng 64 hex digits**, không kiểm chứng bytes thật.

### 8.2. Service check-in không buffer toàn bộ payload

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

final class DocumentClaimService {
    private static final long MAX_UPLOAD_BYTES = 100L * 1024 * 1024;
    private final LargePayloadStore store;

    DocumentClaimService(LargePayloadStore store) {
        this.store = Objects.requireNonNull(store);
    }

    public ClaimReference checkIn(IncomingDocument incoming) {
        if (incoming == null
            || incoming.documentId() == null
            || incoming.documentId().isBlank()
            || incoming.tenantId() == null
            || incoming.tenantId().isBlank()
            || incoming.content() == null) {
            throw new IllegalArgumentException("INVALID_UPLOAD");
        }
        if (!"application/pdf".equals(incoming.contentType())) {
            throw new IllegalArgumentException("UNSUPPORTED_CONTENT_TYPE");
        }

        // InputStream chỉ sống trong lời gọi đồng bộ này.
        // Implementation store.put phải stream và enforce giới hạn thật.
        try (InputStream source = incoming.content()) {
            StoredObject saved = store.put(
                incoming.tenantId(), source,
                incoming.contentType(), MAX_UPLOAD_BYTES);

            if (saved == null || saved.contentLength() <= 0
                || saved.contentLength() > MAX_UPLOAD_BYTES) {
                throw new IllegalStateException("INVALID_STORED_OBJECT");
            }

            ClaimReference ref = new ClaimReference(
                incoming.documentId(),
                incoming.tenantId(),
                saved.objectKey(),
                incoming.contentType(),
                saved.contentLength(),
                saved.sha256(),
                "claim-ref-v1");

            ClaimValidation.validate(ref);
            return ref;
        } catch (IOException ex) {
            throw new UncheckedIOException("CLAIM_CHECK_IN_FAILED", ex);
        }
    }
}
~~~

**Điều được minh họa:** sau check-in, output là DTO nhỏ; payload lớn đã được gửi vào `LargePayloadStore` bằng stream. `DocumentClaimService` chưa tích hợp authentication, metadata transaction, outbox hay cleanup. Trong production, **caller tenant không được tin trực tiếp từ một DTO do client tự tạo**; nó phải được so với principal/context đáng tin trước `store.put`.

**Hạn chế retry:** `InputStream` đã đọc xong thường không thể mở lại. Nếu check-in thất bại và cần retry, hệ thống phải có nguồn có thể mở lại stream (file đã được spool an toàn, multipart upload session, durable staging area...) chứ không gọi lại cùng một đối tượng `InputStream` đã consumed.

### 8.3. Tính toàn vẹn trong implementation store

`LargePayloadStore.put(...)` phải tính `sha256` khi upload và chỉ trả `StoredObject` sau khi xác nhận object đã commit. Nên dùng **stream copy** với bộ đệm nhỏ có giới hạn:

~~~text
InputStream → bounded byte buffer → digest + count → object storage PUT
                                               |
                                    reject if > maxBytes

After durable commit:
  return key, countedLength, computedSha256
~~~

Không nên tin `Content-Length` do client cung cấp như biện pháp duy nhất chống upload lớn; một request streaming có thể thiếu header đó hoặc khai gian. Giới hạn phải được kiểm **trong lúc đọc**.

Với multipart upload, object store implementation cần xử lý **abort/cleanup** các part dở dang khi lỗi, và có giới hạn số part/độ dài/TTL.

## 9. Spring Integration Java DSL: phân ranh giới check-in và dispatch

Có thể triển khai check-in service như một endpoint `Service Activator` trong IntegrationFlow. Cách này dùng **Java DSL** và làm rõ bước I/O bên ngoài, không giả vờ `LargePayloadStore` là MessageStore built-in.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ClaimCheckFlowConfiguration {

    @Bean("documents.large.in")
    DirectChannel uploadInput() {
        return new DirectChannel();
    }

    @Bean("documents.claims.out")
    QueueChannel referencesOutput() {
        // Điểm quan sát trong test; production thay bằng broker adapter.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow checkInDocuments(DocumentClaimService claims) {
        return IntegrationFlow.from("documents.large.in")
            .handle(claims, "checkIn")
            .channel("documents.claims.out")
            .get();
    }
}
~~~

~~~text
documents.large.in
     |
     v
Service Activator: DocumentClaimService.checkIn
     |-- validate MIME/tenant ở boundary đáng tin
     |-- streaming PUT vào LargePayloadStore
     |-- trả ClaimReference
     v
documents.claims.out (QueueChannel demo)
     |
     v
Router / Broker / Consumer nhận ClaimReference
~~~

**Đây là cách hiện thực Claim Check bằng service riêng.** Nó không dùng `ClaimCheckInTransformer` built-in; việc tách I/O thành `.handle(...)` giúp ví dụ rõ ranh giới với object store. Phần EIP là **lưu nội dung rồi chuyển token**, không phụ thuộc endpoint Java nhất thiết mang tên Transformer.

### 9.1. Vì sao input không nên là QueueChannel chứa InputStream?

`IncomingDocument.content` là một InputStream có thể bị đóng khi HTTP request kết thúc hoặc bị consume một lần. Nếu đặt `IncomingDocument` lên queue rồi handler chạy sau, stream có thể không còn hợp lệ. Hãy:

- Thực hiện check-in trong **ranh giới đồng bộ** khi stream còn mở.
- Hoặc spool vào một nguồn bền có thể mở lại, rồi queue **tham chiếu của spool/object**.
- Chỉ enqueue `ClaimReference` sau khi object đã lưu xong và metadata hợp lệ.

### 9.2. Nếu downstream chỉ cần metadata

Sau check-in, nhiều bước có thể đọc `contentType`, `contentLength`, `documentId` mà **không check-out**. Ví dụ:

~~~mermaid
flowchart LR
    C["ClaimReference"] --> V{"Filter: size/type/policy"}
    V -->|"OK"| R{"Router"}
    R --> A["Metadata indexer"]
    R --> D["Document processor"]
    D --> O["Check-out stream"]
    O --> P["Parse/scan document"]
    V -->|"Invalid"| E["Reject / audit"]
~~~

**Không đưa key của object vào log/metric công khai**, đặc biệt nếu key có thể dùng để truy cập tài liệu. Dùng mã correlation không tiết lộ quyền hoặc thông tin nhạy cảm khi cần theo dõi.

## 10. Check-out: lấy payload đúng lúc và đúng quyền

Một consumer cần nội dung sẽ:

1. Nhận `ClaimReference`.
2. Xác thực nguồn message/claim và kiểm tra quyền tenant/operation với state đáng tin cậy.
3. Kiểm tra ref version, kích thước/loại tệp và trạng thái object.
4. Dùng store client đọc **stream**.
5. Kiểm tra tổng bytes/digest, giải mã/scan/parse theo policy.
6. Ghi kết quả nghiệp vụ theo idempotency key.
7. ACK và cleanup theo retention, không xóa tùy tiện khi mới đọc được bytes.

### 10.1. Pseudocode Java có kiểm tra tài nguyên

Để tránh đưa `InputStream` đã mở sang message bất đồng bộ, thực hiện check-out và xử lý nội dung **trong cùng scope**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

interface DocumentAuthorizer {
    // authenticatedTenant lấy từ principal/workflow trusted context.
    void requireRead(String authenticatedTenant, ClaimReference ref);
}

interface DocumentProcessor {
    // Consumer phải xử lý an toàn; chỉ commit business side effect
    // sau khi đã xác minh payload theo contract.
    void processVerified(ClaimReference ref, InputStream content)
        throws IOException;
}

final class DocumentClaimConsumer {
    private final LargePayloadStore store;
    private final DocumentAuthorizer authorizer;
    private final DocumentProcessor processor;

    DocumentClaimConsumer(
            LargePayloadStore store,
            DocumentAuthorizer authorizer,
            DocumentProcessor processor) {
        this.store = Objects.requireNonNull(store);
        this.authorizer = Objects.requireNonNull(authorizer);
        this.processor = Objects.requireNonNull(processor);
    }

    void consume(String authenticatedTenant, ClaimReference ref) {
        ClaimValidation.validate(ref);
        authorizer.requireRead(authenticatedTenant, ref);

        try (InputStream stream =
                 store.open(authenticatedTenant, ref.objectKey())) {
            processor.processVerified(ref, stream);
        } catch (IOException ex) {
            throw new UncheckedIOException("CLAIM_CHECK_OUT_FAILED", ex);
        }
    }
}
~~~

**Đây là abstraction**, không phải khẳng định rằng `processVerified(...)` tự xác minh checksum. Implementation của `DocumentProcessor` phải thực hiện **giới hạn byte, digest, schema/malware validation** trước khi commit side effect. Nếu consumer thực thi side effect **trong lúc vẫn đang stream** và chỉ phát hiện checksum sai ở cuối, việc phát hiện lỗi có thể đã quá muộn.

Với các nghiệp vụ không cho phép xử lý dữ liệu chưa xác minh, có thể dùng **staging/quarantine stream**: tải và kiểm tra checksum/AV/schema vào vùng tạm an toàn, sau đó mới mở nguồn đã kiểm chứng cho bước tạo side effect. Cách này giữ mức tiêu thụ heap thấp mà vẫn có điểm kiểm tra toàn vẹn trước commit.

### 10.2. Tránh lấy nhầm tenant khi check-out

Trong ví dụ, `LargePayloadStore.open(authenticatedTenant, ref.objectKey())` nhận **tenant đã được xác thực**, không lấy từ `ref.tenantId()` để vượt qua authorization. Implementation phải so khớp tenant của reference/object với identity và policy trước GET.

Một claim có `tenantId=tenant-b` được đưa cho consumer của `tenant-a` phải bị từ chối, kể cả object key tồn tại.

### 10.3. Check-out không mặc nhiên đồng nghĩa delete

Nếu hai consumers cùng dùng reference cho audit và indexing, consumer A xóa object ngay khi đọc xong sẽ làm consumer B gặp 404. Đừng dùng “check-out một lần là xóa” khi có:

- Fan-out tới nhiều recipients.
- Broker redelivery hoặc replay dài ngày.
- Gateway cần truy vấn lại sau lỗi.
- Quy định audit/retention.
- Consumer xử lý chậm hoặc offline.

Thay vào đó, dùng lifecycle/retention policy riêng, có thể gồm **reference counting, per-consumer ACK, lease hoặc deadline**, kết hợp garbage collection an toàn.

## 11. Message headers: giữ thứ cần thiết, loại thứ không nên phát tán

Sau check-in, output không còn là bytes tài liệu. Vì vậy `contentType` gốc cần được mô hình hóa rõ:

~~~text
Original:
  payload: byte[] (application/pdf)
  headers: businessCorrelationId, sourceSystem, contentType

After check-in:
  payload: ClaimReference(...)
  headers: businessCorrelationId, trustedSource, refSchemaVersion
  payload.contentType: application/pdf (metadata của object)

At check-out:
  payload: stream/verified document
  headers: correlation, processingContext theo contract
~~~

Nếu tiếp tục giữ `MessageHeaders.CONTENT_TYPE = application/pdf` trong message mà payload là `ClaimReference` DTO, downstream có thể **đọc nhầm payload là PDF binary**. Hãy phân biệt **content type của object gốc** với **content type của envelope/ref**; ví dụ đặt `originalContentType` hoặc field `ClaimReference.contentType`, và để transport serializer khai báo media type của reference thật.

**Không bắt buộc mọi header ở message gốc phải quay lại sau check-out.** Chỉ giữ headers được contract cho phép: correlation, source đã xác minh, policy version, tenant security context phù hợp. Token, Authorization header, internal debug data hoặc secret không nên lan truyền tùy tiện.

### 11.1. Header propagation qua broker

Spring Integration message headers có thể chứa object không serialize được, như `replyChannel` trỏ tới bean/channel trong JVM. Nếu reference đi qua Kafka/AMQP/JMS, header mapper có thể bỏ hoặc chuyển kiểu. Với cross-service request/reply, hãy dùng **message IDs/correlation IDs có định dạng ổn định** và một reply address theo hợp đồng, không trông chờ copy nguyên Java channel object ra ngoài.

### 11.2. Correlation khác object key

`businessCorrelationId` kết nối các bước xử lý; `objectKey` trỏ nội dung; `MessageHeaders.id` định danh envelope; `operationId` dùng chống side effect trùng. Không gộp cả bốn thành một trường nếu lifecycle và quyền hạn khác nhau.

## 12. Check-in và publish: tính nhất quán giữa hai hệ thống

Đây là rủi ro quan trọng nhất khi dùng Claim Check với broker:

~~~text
Step A: PUT large object into ObjectStore
Step B: INSERT metadata/state into database
Step C: PUBLISH ClaimReference to broker
~~~

Các bước thường **không atomic** nếu không có cơ chế phối hợp.

| Trạng thái sau lỗi | Hậu quả | Khôi phục |
| --- | --- | --- |
| PUT thành công, DB insert lỗi | Object mồ côi | Job phát hiện orphan sau grace period |
| DB ghi STAGED, PUT lỗi | Metadata trỏ object chưa tồn tại | Mark failed, retry upload có điều kiện |
| PUT+DB thành công, broker publish lỗi | Reference chưa được xử lý | Outbox/publisher retry; không upload lại mù quáng |
| Publish thành công, consumer crash | Có thể redelivery | Store giữ object; consumer idempotent |
| Object bị xóa trong lúc message còn queued | Dangling reference | Retention + lease/visibility |
| Consumer xử lý xong nhưng ACK mất | Redelivery cùng reference | Stable operation ID và idempotency ở business handler |

### 12.1. Mô hình state machine

~~~mermaid
flowchart TD
    S["RECEIVING"] -->|PUT durable| ST["STORED"]
    ST -->|Metadata+outbox| PB["PUBLISH_PENDING"]
    PB -->|Publish confirmed| AV["AVAILABLE"]
    AV -->|Consumer lease| PR["PROCESSING"]
    PR -->|Outcome committed| DN["PROCESSED"]
    PR -->|Retryable failure| AV
    AV -->|Retention reached| GC["ELIGIBLE_FOR_CLEANUP"]
    DN -->|Retention reached| GC
    GC -->|Safe delete| DE["DELETED"]
    S -->|Upload error| ER["FAILED / ABORT"]
~~~

**Đây là state machine đề xuất**, không phải trạng thái có sẵn của Spring Integration Claim Check. Mọi state transition cần được thiết kế theo storage/broker thực tế. Một ứng dụng có thể đơn giản hóa, nhưng phải giữ bất biến:

> Không phát reference được coi là sẵn sàng khi object chưa commit; không xóa object khi consumer hợp lệ còn quyền retry hoặc replay trong cửa sổ đã cam kết.

### 12.2. Outbox và cleanup phải có idempotency

Nếu outbox publisher chạy lại, cùng reference có thể được publish hai lần. Consumer nên dedup theo `(documentId, operationId, consumerName)` hoặc một khóa nghiệp vụ đã duyệt. Object store upload cũng nên có cách phát hiện upload retry cùng logical document thay vì tạo hàng trăm bản không có owner.

Không nên giả định “đúng một message trong queue” đồng nghĩa “đúng một side effect ở consumer”.

## 13. TTL, retention và garbage collection

### 13.1. Vì sao TTL 5 phút có thể gây mất dữ liệu?

Giả sử consumer offline 20 phút, broker giữ reference 24 giờ, nhưng object store tự xóa payload sau 5 phút:

~~~text
T0:   Upload object; publish reference
T+5:  Object lifecycle deletes object
T+20: Consumer receives reference -> 404
~~~

Message vẫn tồn tại nhưng **không còn nội dung**. Retention của object phải đủ cho:

- Thời gian queue backlog tối đa.
- Số lần retry và backoff dự kiến.
- Consumer downtime được hỗ trợ.
- Replay/audit window.
- Yêu cầu pháp lý về giữ hoặc xóa dữ liệu.
- Thời gian xử lý của nhiều recipients.

### 13.2. Cleanup theo điều kiện, không chỉ theo đồng hồ

Một chính sách thường gồm:

~~~text
EligibleForDeletion =
    ProcessingFinalized
    AND AllRequiredConsumersAcked (nếu fan-out)
    AND MinimumRetentionReached
    AND NoActiveLease
    AND NoLegalHold
~~~

Đây là logic nghiệp vụ vận hành, không phải cú pháp Spring Integration. Khi TTL bắt buộc phải cắt sớm vì chính sách bảo mật, cần thiết kế rằng message đến muộn **sẽ bị từ chối có lý do** thay vì được retry mãi.

### 13.3. Orphan sweeper và race condition

Job xóa object mồ côi không được kết luận “không có metadata ở thời điểm quét” rồi xóa ngay, vì publisher/metadata service có thể đang hoàn thành transaction. Dùng grace period, trạng thái upload, lease/CAS và kiểm tra lại trước xóa.

**Đừng trộn MessageGroupStoreReaper với cleanup của object store.** Reaper thuộc lifecycle message groups (Aggregator/Resequencer), còn Claim Check object cleanup là lifecycle của blob/reference riêng.

## 14. Fan-out và nhiều consumer dùng cùng reference

Khi một claim reference được gửi tới `audit`, `indexing` và `document-analysis`, chỉ một consumer cần tải toàn bộ file; hai consumer khác có thể xử lý metadata.

~~~mermaid
flowchart LR
    REF["ClaimReference"] --> RL{"Recipient List"}
    RL --> A["Audit: metadata only"]
    RL --> I["Index: metadata only"]
    RL --> D["Analysis: needs payload"]
    D --> CO["Check-out"]
    CO --> ST[("Object Store")]
~~~

Đây là một lợi ích quan trọng: **chỉ consumer cần nội dung mới check-out**.

Nếu cả ba cần payload, mỗi consumer có thể fetch riêng:

- Tăng read I/O và GET costs.
- Có thể dùng cache có giới hạn theo key/digest nếu dữ liệu được phép cache.
- Phải giải quyết quyền truy cập từng recipient, không chỉ một token chung vô hạn.
- Cleanup chỉ sau khi các điều kiện của tất cả recipients được giải quyết.

### 14.1. Không đặt toàn bộ bytes trong mỗi child

Nếu Splitter tạo 1.000 message con và copy nguyên byte[] 50 MiB vào mọi header, phần bộ nhớ/I/O có thể tăng cực lớn. Thay vì đó, gửi **tham chiếu đến object + thông tin phạm vi**:

~~~json
{
  "objectKey": "objects/opaque-123",
  "part": 17,
  "range": {"start": 1048576, "endExclusive": 1114112}
}
~~~

Trong production, chỉ dùng range reads khi storage/format hỗ trợ và integrity/checksum theo phạm vi đã được thiết kế; đừng tùy tiện xem mỗi byte range là một tài liệu độc lập hợp lệ.

### 14.2. Aggregator cần biết đúng tình trạng từng consumer

Khi xử lý tài liệu phân trang, Splitter tạo nhiều tasks tham chiếu cùng object. Aggregator có thể đợi đủ `N` kết quả, nhưng một child lỗi hoặc check-out 404 có thể khiến nhóm treo. Cần release/timeout/partial result policy, correlation theo execution và trạng thái lỗi được mô hình hóa rõ, không để exception biến thành “không có reply” không thể giải thích.

## 15. Error channel, retry và phân loại lỗi Claim Check

| Lỗi | Vị trí | Có nên retry? | Hướng xử lý |
| --- | --- | --- | --- |
| Upload quá kích thước | Ingress/check-in | Không với cùng dữ liệu | Reject có mã `SIZE_LIMIT_EXCEEDED` |
| MIME/schema không được phép | Validate | Không | Reject/quarantine |
| AuthN/AuthZ thất bại | Ingress/check-out | Không bypass quyền | 401/403 hoặc error tương đương |
| ObjectStore 5xx/timeout | PUT/GET | Có, hữu hạn | Exponential backoff, stable operation ID |
| Object 404 do TTL | Check-out | Không retry vô hạn | Dangling reference/reconcile |
| Digest mismatch | Check-out | Không xử lý payload | Quarantine/cảnh báo integrity |
| Broker publish lỗi | Sau check-in | Có qua outbox | Không upload lại không kiểm soát |
| Consumer side effect timeout | Sau check-out | Tra cứu trạng thái trước | Idempotency/reconciliation |
| Delete thất bại | Cleanup | Retry có điều kiện | Không làm hỏng business outcome đã commit |

Với `DirectChannel`, exception ở check-in có thể truyền ngược tới caller; với poller/executor/broker, lỗi có thể đi qua `ErrorMessage`/error channel theo cấu hình. **Không mặc định một error channel tên `errorChannel` xử lý tất cả lỗi cho mọi adapter và mọi ranh giới**.

### 15.1. Retry GET không giống retry POST nghiệp vụ

Check-out GET thường chỉ đọc object, nhưng xử lý nội dung có thể gây side effect. Nếu consumer crash sau khi ghi database nhưng trước ACK, redelivery cùng reference sẽ gọi lại consumer. Cần **idempotency** ở business operation, không chỉ ở storage GET.

### 15.2. Gateway request–reply

Nếu Gateway chờ kết quả phân tích tài liệu mà check-in chỉ trả ClaimReference, phải xác định **reply contract**: Gateway nhận `UploadAccepted(claimId)` sớm hay chờ `DocumentProcessed`? Hai lựa chọn có SLA và trạng thái khác nhau.

Không trả “đã xử lý xong” chỉ vì object đã lưu thành công hoặc message reference đã publish. Thường phù hợp trả **202 Accepted/processing ID** (nếu API contract cho phép) rồi báo hoàn tất bằng event/status endpoint.

## 16. Kiểm thử unit của check-in service

Để test luồng logic mà không phụ thuộc cloud thật, có thể dùng một **fake store** với payload nhỏ. Nó **chỉ dành cho test**, không phải chứng minh in-memory storage giải quyết payload 50 MiB.

### 16.1. Fake store đơn giản cho JUnit

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

final class FakeLargePayloadStore implements LargePayloadStore {
    private final Map<String, byte[]> data = new HashMap<>();

    @Override
    public StoredObject put(String tenant, InputStream input,
                            String contentType, long maxBytes)
            throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int count;
        while ((count = input.read(buf)) != -1) {
            if (output.size() + (long) count > maxBytes) {
                throw new IOException("SIZE_LIMIT_EXCEEDED");
            }
            output.write(buf, 0, count);
        }

        byte[] bytes = output.toByteArray();
        String key = tenant + "/" + UUID.randomUUID();
        data.put(key, bytes);
        return new StoredObject(
            key, bytes.length, sha256(bytes));
    }

    @Override
    public InputStream open(String tenant, String key) throws IOException {
        if (!key.startsWith(tenant + "/")) {
            throw new IOException("ACCESS_DENIED");
        }
        byte[] bytes = data.get(key);
        if (bytes == null) {
            throw new IOException("OBJECT_NOT_FOUND");
        }
        return new ByteArrayInputStream(bytes);
    }

    @Override
    public void delete(String tenant, String key) throws IOException {
        if (!key.startsWith(tenant + "/")) {
            throw new IOException("ACCESS_DENIED");
        }
        data.remove(key);
    }

    private static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(data));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

**Giới hạn của fake:** nó dùng `ByteArrayOutputStream` và `HashMap` vì test fixture nhỏ; **không được dùng cho tài liệu lớn production**, không có bảo mật thực, concurrency, transactions, persistence hay TTL.

### 16.2. JUnit 5: check-in, reference và dữ liệu nguyên vẹn

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class DocumentClaimServiceTest {

    @Test
    void checkInStoresPayloadAndReturnsSmallReference()
            throws Exception {
        FakeLargePayloadStore store = new FakeLargePayloadStore();
        DocumentClaimService claims = new DocumentClaimService(store);

        byte[] content = "%PDF-demo-content".getBytes(
            StandardCharsets.UTF_8);

        ClaimReference ref = claims.checkIn(
            new IncomingDocument(
                "DOC-1201", "tenant-a", "application/pdf",
                new ByteArrayInputStream(content)));

        assertEquals("DOC-1201", ref.documentId());
        assertEquals("tenant-a", ref.tenantId());
        assertEquals("application/pdf", ref.contentType());
        assertEquals(content.length, ref.contentLength());
        assertEquals("claim-ref-v1", ref.schemaVersion());

        try (var fromStore =
                 store.open("tenant-a", ref.objectKey())) {
            byte[] restored = fromStore.readAllBytes();
            assertArrayEquals(content, restored);
            String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(restored));
            assertEquals(digest, ref.sha256());
        }
    }

    @Test
    void rejectsWrongContentTypeBeforeUploading() {
        DocumentClaimService claims =
            new DocumentClaimService(new FakeLargePayloadStore());

        assertThrows(IllegalArgumentException.class, () ->
            claims.checkIn(new IncomingDocument(
                "DOC-1202", "tenant-a", "text/plain",
                new ByteArrayInputStream(new byte[] {1, 2, 3}))));
    }

    @Test
    void refusesReadingAnotherTenantsObject() throws Exception {
        FakeLargePayloadStore store = new FakeLargePayloadStore();
        ClaimReference ref =
            new DocumentClaimService(store).checkIn(
                new IncomingDocument(
                    "DOC-1203", "tenant-a", "application/pdf",
                    new ByteArrayInputStream(new byte[] {1, 2, 3})));

        assertThrows(java.io.IOException.class, () ->
            store.open("tenant-b", ref.objectKey()));
    }
}
~~~

Ví dụ `"%PDF-demo-content"` không phải file PDF hợp lệ. Unit test chỉ kiểm tra **cách store/restore bytes và metadata**, không kiểm tra PDF parser hoặc antivirus. Với ứng dụng thực, cần fixture PDF hợp lệ và kiểm thử scan/validation riêng.

### 16.3. Kiểm thử size limit và stream lỗi giữa chừng

Fake store test có thể tạo mảng nhỏ rồi đặt maxBytes thấp khi gọi store trực tiếp. Các case cần có:

- Đúng bằng `maxBytes`: theo policy, nhận nếu hợp lệ.
- Vượt `maxBytes` 1 byte: reject và **không commit object hoàn chỉnh**.
- `InputStream.read(...)` ném `IOException` sau một số bytes: upload phải abort/cleanup.
- Store PUT thành công nhưng metadata/audit ghi lỗi: có orphan reconciliation.
- Digest được tính từ **bytes thực sự lưu**, không chỉ từ `Content-Length` client khai.

## 17. Integration test Spring Integration: payload đổi thành reference

Với `ClaimCheckFlowConfiguration` (mục 9), kiểm tra rằng flow nhận một `IncomingDocument` ở channel đầu vào, gửi ra `ClaimReference` chứ **không phát byte[] lớn** vào channel tiếp theo.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringJUnitConfig(classes = {
    ClaimCheckFlowConfiguration.class,
    DocumentClaimFlowTest.FakeStoreConfig.class
})
class DocumentClaimFlowTest {
    @Configuration
    static class FakeStoreConfig {
        @Bean LargePayloadStore store() {
            return new FakeLargePayloadStore();
        }
        @Bean DocumentClaimService claims(LargePayloadStore store) {
            return new DocumentClaimService(store);
        }
    }

    @Autowired @Qualifier("documents.large.in")
    MessageChannel input;

    @Autowired @Qualifier("documents.claims.out")
    PollableChannel output;

    @Test
    void flowReplacesLargeBodyWithSmallClaimReference() {
        byte[] payload = "document bytes".getBytes(
            StandardCharsets.UTF_8);

        IncomingDocument upload = new IncomingDocument(
            "DOC-1301", "tenant-a", "application/pdf",
            new ByteArrayInputStream(payload));

        assertTrue(input.send(MessageBuilder.withPayload(upload)
            .setHeader("businessCorrelationId", "DOC-1301")
            .build()));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(ClaimReference.class, message.getPayload());

        ClaimReference ref = (ClaimReference) message.getPayload();
        assertEquals("DOC-1301", ref.documentId());
        assertEquals(payload.length, ref.contentLength());
        assertEquals("DOC-1301",
            message.getHeaders().get("businessCorrelationId"));

        assertNull(output.receive(0), "No duplicate reference");
    }
}
~~~

**Giới hạn của integration test:** đây là demo một JVM dùng fake store, không chứng minh broker publish/ACK, authN/authZ thực, độ bền khi restart hoặc PDF bytes đã được kiểm tra. Nó chỉ chứng minh **wiring và shape của message sau check-in**.

Với các flow dùng MessageStore built-in, cần integration test tương tự cho **Claim Check In → claim token → Claim Check Out**, xác minh message restore đúng và xác định rõ **remove/retain policy** theo phiên bản framework.

## 18. Ma trận kiểm thử toàn diện

| Kịch bản | Input/trạng thái | Điều cần kiểm tra |
| --- | --- | --- |
| Happy path | Payload hợp lệ, store hoạt động | Reference nhỏ, object đọc lại đúng |
| 0-byte input | File rỗng | Reject hoặc accept theo contract rõ |
| Size đúng ngưỡng | `maxBytes` | Hành vi tại biên |
| Size vượt ngưỡng | `maxBytes + 1` | Upload abort, không commit object |
| Content-Type sai | Claim PDF nhưng bytes không hợp lệ | Validation/scan đúng tầng |
| SHA mismatch | Object bị sửa | Không commit side effect |
| Wrong tenant | Consumer A lấy object tenant B | Từ chối truy cập |
| Unknown/ref forged | Key không tồn tại | Error/quarantine, không đoán object khác |
| ObjectStore outage | PUT hoặc GET 5xx | Retry hữu hạn, không mất workflow |
| Stale object | Object đã bị TTL xóa | Dangling reference/reconcile |
| Upload crash | PUT xong, publish chưa xong | Orphan/outbox recovery |
| Publish duplicate | Outbox retry | Consumer idempotent |
| Consumer crash | Đọc xong, ACK chưa xong | Redelivery không tạo side effect trùng |
| Fan-out | Hai consumers dùng cùng ref | Không xóa object khi còn consumer cần |
| Multi-instance | Consumer ở node khác ingress | Có shared store, đúng ACL |
| Broker header mapper | Ref đi qua Kafka/AMQP | Correlation/serialization contract đúng |
| Stream close | HTTP InputStream đóng sớm | Check-in đồng bộ hoặc staging |
| Retry InputStream | Attempt thứ hai với stream đã đọc | Reopen nguồn, không dùng lại stream cũ |
| Object delete race | Cleanup đúng lúc consumer GET | Lease/retention chống xóa sớm |
| Legal hold | Tài liệu cần lưu | Lifecycle policy không xóa trái quy định |
| Metadata leakage | Logs/metrics/outbound response | Không lộ object key/token/PII |
| Restart | Reference queued, process restart | Object tồn tại và recovery đúng |
| Integrity + malware | PDF độc hại | Scan/validation trước xử lý nguy hiểm |

### 18.1. Test theo **hành vi không được phép xảy ra**

Đừng chỉ assert reference đã được gửi. Cần assert:

~~~text
After check-in:
  output message payload is ClaimReference
  no raw large byte[] goes to broker-facing channel
  unauthorized tenant cannot check-out
  invalid digest does not reach business processor
  repeated delivery does not run side effect twice
  deletion cannot happen before required retention/ACK
~~~

Một test chỉ kiểm tra `output != null` có thể bỏ sót lỗ hổng nghiêm trọng nếu payload lớn vẫn bị copy vào header phụ hoặc log.

## 19. Observability và tính toán dung lượng

### 19.1. Một phép tính gần đúng

Giả sử 1.000 uploads/giờ, mỗi upload 50 MiB:

~~~text
Object bytes/hour
  = 1,000 × 50 MiB
  = 50,000 MiB ≈ 48.8 GiB/hour

If references are ~1 KiB:
  broker payload/hour
  ≈ 1,000 × 1 KiB
  ≈ 0.98 MiB/hour

Total storage/GET traffic still depends on
retention, read count, retry and consumer fan-out.
~~~

Đây là phép tính **minh họa** chưa tính object metadata, replication, compression, network protocol, broker overhead và số lần GET. Claim Check có thể giảm đáng kể **bytes đi qua broker**, nhưng không làm giảm dung lượng object store cần lưu.

### 19.2. Chỉ số nên đo

| Thành phần | Metric / log gợi ý | Mục đích |
| --- | --- | --- |
| Ingress | Upload count, bytes, rejected-size | Thấy nhu cầu thực |
| Check-in | PUT latency, size, checksum failure | Phát hiện storage bottleneck |
| Object store | Capacity, GET/PUT error rate, lifecycle deletes | Theo dõi độ bền và chi phí |
| Reference publisher | Outbox lag, publish retries | Phát hiện stored-not-published |
| Broker | Backlog, age, redelivery count | Đánh giá retention an toàn |
| Check-out | Fetch latency, 403/404/5xx, checksum mismatch | Phát hiện dangling/corrupt data |
| Business consumer | Success/error, idempotency duplicates | Không nhầm GET thành success |
| Cleanup job | Orphans, retention-expired, delete failures | Tránh leak/xóa quá sớm |
| Security audit | Principal, tenant, operation, decision | Truy vết truy cập dữ liệu |
| End-to-end | Document processing SLA, stuck claims | Kiểm tra workflow hoàn tất |

**Không** dùng `objectKey`, `documentId`, `tenantId` hoặc `businessCorrelationId` tự do làm metric tags có cardinality cao. Với log/trace, hạn chế trường nhạy cảm, kiểm soát quyền truy cập và định dạng không tiết lộ pre-signed URL hoặc token.

### 19.3. Báo “upload accepted” không phải “document processed”

Tối thiểu phân biệt:

- **RECEIVED:** nguồn upload đã bắt đầu/tiếp nhận.
- **STORED:** object đã lưu và xác minh.
- **PUBLISHED:** reference đã được đưa vào kênh xử lý theo broker semantics.
- **PROCESSING:** consumer đang fetch/parse.
- **PROCESSED:** nghiệp vụ đã commit theo hợp đồng.
- **FAILED/QUARANTINED:** có lỗi cần xử lý.
- **DELETED:** retention cleanup hoàn tất.

Một `postSend(sent=true)` ở reference channel **không chứng minh consumer đã đọc bytes hoặc hoàn thành nghiệp vụ**.

## 20. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách tránh |
| --- | --- | --- |
| Lưu 100 MiB trong `SimpleMessageStore` rồi nghĩ heap đã nhẹ | Payload vẫn nằm trong JVM | Dùng durable external store khi phù hợp |
| Đưa `InputStream` vào queue bất đồng bộ | Stream bị đóng/consumed trước khi đọc | Check-in đồng bộ, gửi reference |
| Copy payload vào header “để tiện debug” | Mất hết lợi ích Claim Check, tăng rủi ro rò rỉ | Chỉ gửi metadata tối thiểu |
| Dùng file name client làm object key | Traversal/collision/IDOR | Key opaque do server sinh |
| Tin token là authorization | Ai có token cũng có thể đọc dữ liệu | AuthN/AuthZ theo tenant/operation |
| Check-out là xóa ngay | Consumer khác hoặc retry nhận 404 | Lifecycle + retention + per-consumer completion |
| TTL object ngắn hơn broker retention | Dangling reference | Đồng bộ retention/replay policy |
| PUT xong, publish lỗi rồi bỏ qua | Object mồ côi, workflow mất sự kiện | Metadata/outbox + sweeper |
| Publish trước khi object commit | Consumer fetch 404 hoặc partial bytes | Publish khi durable commit đã xác nhận |
| Retry upload với InputStream đã consumed | Retry rỗng/sai dữ liệu | Mở lại nguồn hoặc staging có thể replay |
| Chỉ so length, không kiểm digest | Dữ liệu sai có thể cùng độ dài | Digest + protected metadata |
| Digest mismatch nhưng tiếp tục side effect | Xử lý nội dung không toàn vẹn | Quarantine trước commit |
| Giữ `contentType=application/pdf` khi payload là DTO ref | Consumer hiểu sai định dạng | Tách object MIME và envelope MIME |
| Dùng `MessageHeaders.id` làm business idempotency | Retry tạo message ID mới | Stable operation/document key |
| Quét và xóa orphan ngay khi chưa thấy DB record | Race với in-flight metadata commit | Grace period, lease, recheck |
| Lạm dụng Claim Check cho payload 2 KiB | Tăng complexity và latency không cần thiết | Đo thực tế rồi chọn chiến lược |
| Test fake store rồi coi như production verified | Không có durability/auth/concurrency thực | Contract/integration/failure tests với backend thật |

## 21. Checklist triển khai

- [ ] Có **lý do đo được** để đưa payload ra khỏi message: size, queue backlog, broker limit hoặc bảo mật.
- [ ] Chọn rõ **MessageStore claim check** hay **object-store reference**, không đánh đồng dung lượng và durability.
- [ ] Payload large được upload **streaming với giới hạn bytes thực**, không cần giữ toàn bộ ở heap.
- [ ] Reference chỉ chứa metadata cần thiết, nhỏ và có schema version rõ.
- [ ] Storage key do server sinh; quyền truy cập xác thực theo tenant/operation.
- [ ] Có content type validation, SHA/length integrity check và scan theo nghiệp vụ.
- [ ] Có contract khi object không tìm thấy, sai hash, timeout hoặc access denied.
- [ ] Object được commit bền trước khi reference có thể được consumer xử lý.
- [ ] Có metadata/outbox hoặc cơ chế khôi phục khi PUT/DB/publish chỉ thành công một phần.
- [ ] Có correlation/idempotency key ổn định qua retry/redelivery.
- [ ] Có ranh giới ACK rõ: check-in thành công khác xử lý nghiệp vụ thành công.
- [ ] Fan-out có chính sách nhiều consumer; không xóa object khi một consumer mới xong.
- [ ] Retention của object >= retry/queue/replay window cần bảo đảm, trừ ngoại lệ pháp lý được thiết kế.
- [ ] Cleanup/orphan sweeper có grace period, TTL, lease và audit.
- [ ] Header mapping, MIME của envelope và metadata gốc được phân biệt đúng.
- [ ] Có unit/integration tests, failure tests, security tests và quan sát chi phí GET/PUT/storage.
- [ ] Không để token, pre-signed URL hoặc payload nhạy cảm xuất hiện trong logs, metrics hoặc error messages công khai.
- [ ] Có playbook xử lý dangling reference, corrupted object, broker redelivery và xóa quá sớm.

## 22. Bài tập vận dụng

Một nền tảng tiếp nhận **hồ sơ PDF 100 MiB** để trích xuất văn bản, kiểm tra tuân thủ và lưu trữ. Hệ thống có ba consumer:

- **Audit:** chỉ cần metadata, không được đọc toàn bộ tài liệu.
- **Extraction:** cần tải PDF, kiểm tra tính toàn vẹn rồi trích xuất văn bản.
- **Compliance:** chỉ đọc nội dung khi hồ sơ được đánh dấu cần xem xét.

**Yêu cầu:**

1. Vẽ flow `HTTP upload → Claim Check In → Broker → Recipient List → Check Out khi cần → Consumer`.
2. Thiết kế `ClaimReference` chứa document ID, tenant, object key, size, SHA-256, content type và version; chỉ ra trường nào không được tin từ client.
3. Chọn object store, MessageStore hay kết hợp; giải thích vì sao không nên giữ 100 MiB vào heap của mọi service.
4. Viết abstraction Java `LargePayloadStore` và một service check-in streaming với giới hạn 100 MiB.
5. Mô tả cách xác minh digest **trước** khi tiến hành side effect có rủi ro (ví dụ ghi kết quả phân tích chính thức).
6. Thiết kế outbox và orphan cleanup khi PUT đã thành công nhưng publish reference thất bại.
7. Với ba consumer có tốc độ khác nhau, thiết kế retention/lease/ref count hoặc policy tương đương để Audit không làm payload bị xóa trước Extraction/Compliance.
8. Viết unit tests cho fake store và integration test Spring Integration xác minh output là reference.
9. Thiết kế failure tests: sai tenant, object 404, digest mismatch, upload quá ngưỡng, timeout GET, broker redelivery, cleanup race.
10. Nếu compliance quyết định **không cần đọc payload**, hãy chứng minh nó không thực hiện check-out (giảm I/O và tối thiểu quyền).
11. Giải thích vì sao retry xử lý tài liệu không được nhân đôi **một bản ghi nghiệp vụ đã commit**, dù fetch lại cùng object.
12. Đề xuất metrics về `storedBytes`, `objectAge`, `danglingRef`, `orphanCandidates`, `fetchLatency` và `processingOutcome`.

**Gợi ý:** dùng một **object key opaque**, kiểm tra quyền theo tenant từ principal, và một **execution/operation ID** tách khỏi key. Khi fan-out, đối tượng lưu trữ không nên bị xóa bởi consumer đầu tiên. Với file lớn, ưu tiên streaming và staging có xác minh thay vì truyền bytes qua message headers.

## 23. Tổng kết

**Claim Check** là giải pháp EIP để **cất payload lớn ở một kho được quản lý và mang tham chiếu nhỏ qua luồng message**, sau đó khôi phục dữ liệu đúng nơi cần. Trong Spring Integration, có các thành phần Claim Check In/Out dựa trên MessageStore; với dữ liệu rất lớn, một biến thể dùng **external object/blob storage** thường phù hợp hơn, nếu được thiết kế đầy đủ quyền, integrity, retention và cleanup.

Lợi ích chính là **giảm lượng byte đi qua các bước trung gian và broker, giới hạn phạm vi dữ liệu nhạy cảm và tách tốc độ upload khỏi xử lý**. Nhưng Claim Check không tự bảo đảm transaction giữa object store và broker, không tự cấp quyền an toàn, không tự giải quyết object mồ côi hoặc retry có side effect. Cần phối hợp Filter, Router, Transformer/Enricher, Gateway, Recipient List, Splitter/Aggregator, retry, error channel, correlation, idempotency và observability để bảo đảm **tham chiếu hợp lệ, payload toàn vẹn, không mất dữ liệu vì cleanup quá sớm và không xử lý trùng nghiệp vụ**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Claim Check, Message Store, Content Enricher, Message Translator); Spring Integration Reference về [Claim Check](https://docs.spring.io/spring-integration/reference/claim-check.html), Message Stores, Transformers, Java DSL, Error Handling và Testing; Spring Messaging về `MessageHeaders`; Java SE về `InputStream`, `MessageDigest`, `BigDecimal` và cơ chế resource management.

