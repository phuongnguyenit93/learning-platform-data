# Không gửi dữ liệu nhạy cảm trong message khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Xác định dữ liệu nhạy cảm có thể xuất hiện trong **message body, headers, metadata, log, retry queue, DLQ và trace** của một hệ thống Spring Batch phân tán.
- Giải thích vì sao nguyên tắc **data minimization** ưu tiên gửi **tham chiếu công việc** thay vì gửi nguyên bản ghi chứa thông tin cá nhân, token hoặc bí mật.
- Phân biệt tác động bảo mật giữa **remote partitioning**, **remote chunking** và local partitioning; hiểu khi nào kiến trúc cần thay đổi để giảm dữ liệu qua broker.
- Thiết kế một hợp đồng message ngắn gọn gồm định danh công việc, version và correlation, không biến opaque ID thành “mật khẩu truy cập dữ liệu”.
- Áp dụng xác thực, phân quyền, TLS, mã hóa lưu trữ, bảo vệ secret và kiểm tra phiên bản/snapshot ở đúng ranh giới manager–worker.
- Thiết kế retry, idempotency, DLQ, retention, audit và logging để dữ liệu không rò rỉ khi job lỗi hoặc restart.
- Đánh giá trade-off giữa bảo mật, throughput, network, DB connection và khả năng khôi phục đối với workload Spring Batch lớn.
- Xây dựng bộ kiểm thử bảo mật và runbook khi phát hiện message đã chứa dữ liệu nhạy cảm.

## 1. Bối cảnh: một message có thể được sao chép nhiều hơn bạn nghĩ

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, nhóm phát triển cần mở rộng Spring Batch từ một JVM sang nhiều worker trên các máy khác nhau. Một cách phổ biến là dùng middleware như RabbitMQ hoặc Kafka để gửi công việc tới worker.

Giả sử manager xử lý đơn hàng và gửi message:

~~~json
{
  "jobExecutionId": 1204,
  "chunkId": "chunk-0042",
  "customerName": "Example Customer",
  "phone": "0900000000",
  "email": "example.invalid@example.com",
  "paymentToken": "demo-token-not-real",
  "shippingAddress": "Example Address",
  "amountMinor": 250000
}
~~~

Các giá trị chỉ là **dữ liệu giả**, nhưng cấu trúc minh họa lỗi thiết kế: thông tin cá nhân và token thanh toán được gửi cùng một message dùng cho giao việc. Dù người phát triển chỉ muốn “worker xử lý nhanh hơn”, message có thể đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    M["Manager / source"] --> P["Publisher & serializer"]
    P --> Q["Broker request queue / log"]
    Q --> W["Worker JVM"]
    W --> R["Reply message"]
    Q -. "Retry / redelivery" .-> RT["Retry queue / topic"]
    Q -. "Failure" .-> DLQ["DLQ & replay tooling"]
    P -. "Debug / tracing" .-> LG["Logs / APM / metrics"]
    W -. "Exception / tracing" .-> LG
    RT -.-> BK["Backup / retention"]
    DLQ -.-> BK
    Q -.-> BK
~~~

Chỉ cần một phần hệ thống bật log body để debug hoặc DLQ giữ request lỗi quá lâu, dữ liệu nhạy cảm có thể tồn tại ở nơi ban đầu không được thiết kế để bảo vệ dữ liệu khách hàng.

**Nguyên tắc trung tâm:** *Không gửi dữ liệu nhạy cảm qua middleware nếu công việc có thể được mô tả bằng một định danh/manifest và worker tự lấy dữ liệu từ nguồn được kiểm soát.* Nếu kiến trúc bắt buộc chuyển dữ liệu nhạy cảm, phải có đánh giá rủi ro, giới hạn trường, cơ chế mã hóa/phân quyền, lưu giữ và xóa phù hợp; không tuyên bố “TLS đã đủ”.

## 2. Dữ liệu nào được xem là nhạy cảm?

Tùy miền nghiệp vụ, dữ liệu nhạy cảm có thể bao gồm cả bí mật kỹ thuật lẫn dữ liệu của người dùng:

| Nhóm | Ví dụ | Rủi ro khi đưa vào broker |
| --- | --- | --- |
| **Secrets/credentials** | DB password, API key, OAuth access/refresh token, private key, bearer token | Chiếm quyền truy cập hệ khác; rủi ro rất cao |
| **Thông tin nhận dạng cá nhân** | Họ tên, email, điện thoại, địa chỉ, số giấy tờ | Tiết lộ danh tính, vi phạm nghĩa vụ bảo vệ dữ liệu |
| **Dữ liệu tài chính** | Số tài khoản, token thanh toán, thông tin giao dịch chi tiết | Gian lận, lộ giao dịch, rủi ro tuân thủ |
| **Dữ liệu sức khỏe hoặc nhạy cảm theo miền** | Kết quả xét nghiệm, hồ sơ chăm sóc | Rò rỉ thông tin có tác động lớn tới cá nhân |
| **Dữ liệu nội bộ quan trọng** | Công thức định giá, dữ liệu chiến lược, khóa phân vùng nhạy cảm | Rò rỉ bí mật kinh doanh |
| **Định danh liên kết được** | Customer ID, tenant ID, order ID, object key chứa tên khách hàng | Vẫn có thể liên kết tới cá nhân hoặc tiết lộ cấu trúc hệ thống |
| **Metadata vận hành** | Hostname, stack trace, DB URL, đường dẫn file, trace attributes | Lộ cấu trúc hạ tầng hoặc dữ liệu từ exception |

Dữ liệu được gọi là **pseudonymized** hoặc được thay bằng ID không có nghĩa đã được ẩn danh. Một `customerId` có thể được tra ngược thành khách hàng trong một hệ thống khác; một `orderId` có thể tiết lộ quan hệ nghiệp vụ khi được liên kết với log.

Đặc biệt tránh đưa **credential** vào message dưới mọi hình thức. “Mã hóa password rồi gửi cho worker” thường là sai hướng: worker nên nhận quyền qua **workload identity và secret manager** của chính nó, thay vì nhận credential từ từng request.

### Nhạy cảm phụ thuộc ngữ cảnh

Một chuỗi `orders/2026-11-25/shard-0002` có thể ít nhạy cảm hơn danh sách khách hàng thật, nhưng vẫn tiết lộ ngày chạy và cấu trúc dữ liệu. Một tham chiếu chứa tên tenant hoặc email trong path lại là thông tin nhận dạng. Vì vậy khi đánh giá message cần xét **khả năng liên kết, phạm vi người có quyền đọc và thời gian lưu**, không chỉ kiểm tra tên trường `password`.

## 3. Đường đi của dữ liệu và mô hình đe dọa

Trước khi chọn JSON/Avro/Protobuf hay bật TLS, cần lập bản đồ **nơi dữ liệu đi qua và tồn tại**:

| Ranh giới | Ai có thể thấy dữ liệu? | Kiểm soát cần có |
| --- | --- | --- |
| Manager heap → serializer | Code, debug agent, heap dump | Data minimization, hạn chế dump, không log payload |
| Publisher → broker | Network path, endpoint của broker | TLS, certificate verification, authn |
| Broker queue/log/disk | Admin broker, storage/backup operator, service principal | ACL, encryption at rest, retention, audit |
| Broker → worker | Consumer theo subscription/queue binding | Consumer ACL, mTLS/SASL khi phù hợp, topic/queue isolation |
| Worker deserialize → DB/API | Process worker và dependency | Authz theo principal/tenant, input validation, least privilege |
| Retry/DLQ/replay | Vận hành và công cụ điều tra | Masking, bảo vệ quyền, hạn chế lưu lâu, kiểm soát replay |
| Logs, metrics, traces, alerts | Observability stack và bên nhận thông báo | Không đưa raw payload, secrets hoặc PII vào label/span |
| Backup/snapshot/export | Backup operator, object storage, môi trường test | Mã hóa, phân quyền, thời hạn lưu và xóa |

**Threat model thực tế** cần xét các trường hợp: consumer cấu hình nhầm subscription, account service bị lộ, broker admin có quyền quá rộng, message lỗi bị dump ra ticket, DLQ được copy sang staging, backup tồn tại quá lâu, worker bị replay request cũ và object storage path không còn trỏ snapshot ban đầu.

### Một câu hỏi thiết kế bắt buộc

Nếu **đội vận hành broker** có thể xem trực tiếp payload, họ có cần quyền nhìn thấy tên khách hàng, token thanh toán hoặc hồ sơ nhạy cảm để phục vụ công việc không?

- Nếu **không**, ưu tiên không đưa những field đó vào broker.
- Nếu **bắt buộc**, cần biện pháp kỹ thuật ngăn người không được phép xem nội dung, đồng thời xác định rõ ai giữ khóa giải mã và lúc nào giải mã xảy ra.
- Nếu chỉ cần biết **đã xử lý tới partition nào**, một `workRef` hoặc `stepExecutionId` đủ thông tin điều phối và giảm đáng kể bề mặt lộ dữ liệu.

## 4. Data minimization: gửi “công việc cần làm”, không gửi dữ liệu gốc

Thay vì gửi toàn bộ đơn hàng, manager gửi **reference** để worker tra dữ liệu từ một nguồn được phân quyền:

~~~json
{
  "messageType": "partition-work-request",
  "schemaVersion": 1,
  "workRef": "39166b71-09d9-4eb9-9b68-1df0d0f40566",
  "operationKey": "snapshot-20261125:partition-0042",
  "stepExecutionId": 5678
}
~~~

Đây là **contract minh họa do ứng dụng tự định nghĩa**, **không phải wire format mặc định** của `StepExecutionRequest` trong Spring Batch Integration.

Một message tối giản có thể chứa:

- **`messageType`**: để handler hiểu loại công việc.
- **`schemaVersion`**: để kiểm soát decoder và rolling upgrade.
- **`workRef`**: ID opaque trỏ tới assignment/manifest trong nguồn lưu bền vững.
- **`operationKey`**: khóa logic cho dedup/correlation của **cùng công việc**, không dùng như mật khẩu truy cập.
- **`stepExecutionId`**: định danh kỹ thuật nếu protocol thực sự cần.

Nó **không** mang tên khách hàng, địa chỉ, payment token, connection string, DB password, tài liệu PDF hoặc blob dữ liệu lớn.

### Nhưng “reference” có thật sự an toàn?

**Không tự động.** Nếu bất kỳ worker nào biết `workRef` cũng đọc được mọi hồ sơ, reference trở thành **bearer capability** và hệ thống có nguy cơ IDOR/broken object-level authorization.

Một thiết kế đúng cần:

1. ID opaque không dễ đoán **để giảm lộ thông tin**, nhưng **không xem tính ngẫu nhiên là cơ chế phân quyền**.
2. Worker được xác thực bằng **service identity độc lập với message**.
3. Nguồn dữ liệu kiểm tra quyền đọc `workRef` với principal, tenant/scope và trạng thái assignment.
4. `workRef` thuộc snapshot/manifest đã chốt và còn hiệu lực khi restart theo policy.
5. Trả về đúng dữ liệu mà worker có quyền; không tự chấp nhận một `customerId`/`path` gửi trong message để mở quyền.
6. Ghi audit truy cập ở mức đủ để điều tra, nhưng không log nội dung nhạy cảm.

Một **opaque ID không có quyền tự thân** nếu server luôn kiểm tra authorization. Nếu hệ thống dùng URL ký hoặc token mang quyền truy cập, token đó là **credential** cần có TTL ngắn, scope hạn chế và chính sách xử lý riêng; không thể gọi nó là “an toàn vì chỉ là một URL”.

## 5. Remote partitioning và remote chunking khác nhau về bảo mật payload

| Mô hình Spring Batch | Ai đọc item từ nguồn? | Message điển hình | Khả năng giảm PII trong broker |
| --- | --- | --- | --- |
| Local partitioning | Worker thread cùng JVM | Không cần broker để giao partition | Tránh network broker cho assignment |
| **Remote partitioning** | Worker JVM của từng partition | StepExecution ID hoặc assignment range/ref | **Thường dễ hơn**: gửi metadata, worker tự đọc từ nguồn |
| **Remote chunking** | Manager đọc, gửi chunk item | Payload chứa item và reply | Khó hơn nếu item chứa PII; cần thay thiết kế hoặc bảo vệ payload |
| Tự xây giao thức reference-based | Worker tra object/manifest sau khi nhận ID | Work reference rất nhỏ | Có thể giảm lộ payload, nhưng cần tự quản lý auth/restart |

### Remote partitioning: ưu thế khi muốn không truyền payload nhạy cảm

~~~mermaid
flowchart LR
    P["Manager / Partitioner"] --> Q["Broker: stepExecutionId / workRef"]
    Q --> W1["Worker A"]
    Q --> W2["Worker B"]
    W1 --> A["Manifest / source API có authZ"]
    W2 --> A
    A --> DB["Nguồn dữ liệu nhạy cảm"]
    W1 --> O["DB đích"]
    W2 --> O
~~~

Manager giao miền dữ liệu và worker **tự đọc nguồn**. Các thông điệp giao việc có thể chỉ chứa ID/biên đã được xử lý phù hợp; dữ liệu nhạy cảm không cần đi qua broker request. Tuy nhiên, worker nào được giao miền nào phải được kiểm chứng bằng `StepExecutionContext` và quyền nguồn; nếu mọi worker dùng cùng một service credential có quyền đọc toàn bộ tenant, **đường ranh giới bảo mật vẫn rộng**.

### Remote chunking: item thực sự đi qua middleware

~~~mermaid
flowchart LR
    M["Manager: ItemReader → Chunk"] --> B["Broker request: item chunk"]
    B --> W["Worker: process/write"]
    W --> R["Reply channel"]
    R --> M
~~~

Nếu `ItemReader` của manager trả về `CustomerRecord` chứa tên, số giấy tờ, email hoặc token và gửi cả object, **payload nhạy cảm đã đi qua broker**. Không thể “chữa” chỉ bằng việc xóa field ở reply.

Các lựa chọn:

1. **Giảm dữ liệu tại nguồn:** worker chỉ cần `orderId`, loại bỏ các field không dùng trước khi serialize. Đoạn minimization phải được test, không truyền raw entity và trông chờ converter tự lọc.
2. **Thiết kế lại thành reference:** nếu worker có thể tra nguồn theo ID, cân nhắc **remote partitioning** hoặc giao thức reference-based; khi thay đổi, phải thiết kế lại ownership của reader, checkpoint và transaction.
3. **Chấp nhận payload nhạy cảm có kiểm soát khi bất khả kháng:** giới hạn field, dùng TLS, ACL, encryption at rest và khi cần **application-level payload encryption**, kiểm soát thời gian lưu, log và DLQ.
4. **Xem xét xử lý cục bộ:** nếu môi trường không cho phép dữ liệu rời vùng an toàn, local partitioning/multi-threaded processing có thể phù hợp hơn scale-out qua broker.

Remote chunking có thể có throughput cao nếu worker xử lý CPU/IO nặng, nhưng thay đổi mô hình chỉ để “né message chứa PII” cần đánh giá khả năng chia nguồn và chi phí truy vấn từ nhiều worker.

## 6. Thiết kế reference architecture có phân quyền

Một kiến trúc tham chiếu:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant W as Worker
    participant A as Manifest API / DB
    participant D as Business DB
    M->>A: Tạo assignment trong snapshot bất biến
    A-->>M: workRef (opaque UUID)
    M->>Q: Publish workRef + operationKey (không có PII)
    Q->>W: Deliver workRef
    W->>A: Resolve(workRef, worker principal)
    A->>A: Kiểm tra authZ/scope/version/expiry
    A-->>W: Source locator và metadata hợp lệ
    W->>D: Đọc nguồn, process/write có transaction
    W-->>M: Result ID / status không có dữ liệu nhạy cảm
~~~

**Bốn ranh giới bảo vệ**:

- **Manager → broker:** payload chỉ chứa metadata nhỏ được phép public cho phạm vi consumer.
- **Broker → worker:** worker chỉ nhận định danh, không nhận secrets từ request.
- **Worker → source:** nguồn kiểm tra quyền của worker theo `workRef` và tenant/assignment, không chỉ kiểm tra rằng key tồn tại.
- **Worker → destination:** write có transaction, business-key idempotency và phạm vi được phép, không mở quyền ghi mọi tenant.

### Ví dụ schema manifest PostgreSQL

~~~sql
CREATE TABLE batch_work_manifest (
    work_ref UUID PRIMARY KEY,
    snapshot_id VARCHAR(100) NOT NULL,
    source_resource VARCHAR(400) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    allowed_principal VARCHAR(200) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE INDEX idx_work_manifest_principal
    ON batch_work_manifest(allowed_principal, snapshot_id, status);
~~~

Bảng là ví dụ hợp đồng **assignment**, không thay thế metadata `JobRepository`. `source_resource` có thể là một location nhạy cảm nên **chỉ lưu trong DB được bảo vệ**, không tự động copy nó vào message/log. `source_version`/checksum bảo đảm nội dung không đổi khi restart.

Một truy vấn resolve có kiểm tra scope:

~~~sql
SELECT snapshot_id, source_resource, source_version, tenant_id
FROM batch_work_manifest
WHERE work_ref = :workRef
  AND allowed_principal = :authenticatedPrincipal
  AND status IN ('ASSIGNED', 'RUNNING')
  AND expires_at > CURRENT_TIMESTAMP;
~~~

`:authenticatedPrincipal` phải lấy từ **identity đã xác thực của worker**, không lấy một field `workerName` do chính message cung cấp. Trong môi trường đa tenant/role phức tạp, bảng ACL/row-level security hoặc policy service cần phản ánh quyền thực tế.

**Giới hạn của expiry:** một assignment hết TTL trong lúc job cần restart có thể không khôi phục được. TTL phải đi cùng chính sách lưu giữ snapshot, refresh assignment có audit và lifecycle `JobInstance`; không tự tăng TTL vô hạn vì “batch có thể chạy lâu”.

## 7. Java 17: message DTO tối giản và validate trước khi publish

Ví dụ sau chỉ dùng Java 17 cho validation, không chứa tên/địa chỉ/token. Message này là **hợp đồng do ứng dụng định nghĩa**, không được giả định là JSON gốc của Spring Batch Integration.

~~~java
import java.util.Objects;
import java.util.UUID;

public record SafeWorkRequest(
        String messageType,
        int schemaVersion,
        UUID workRef,
        UUID operationId,
        long stepExecutionId) {

    public SafeWorkRequest {
        if (!"partition-work-request".equals(messageType)) {
            throw new IllegalArgumentException("Unexpected message type");
        }
        if (schemaVersion != 1) {
            throw new IllegalArgumentException("Unsupported schema version");
        }
        Objects.requireNonNull(workRef, "workRef");
        Objects.requireNonNull(operationId, "operationId");
        if (stepExecutionId <= 0) {
            throw new IllegalArgumentException(
                    "Invalid stepExecutionId");
        }
    }

    public static SafeWorkRequest create(
            UUID persistedWorkRef,
            UUID persistedOperationId,
            long stepExecutionId) {
        return new SafeWorkRequest(
                "partition-work-request",
                1,
                persistedWorkRef,
                persistedOperationId,
                stepExecutionId);
    }
}
~~~

`workRef` được tạo và lưu khi **assignment** được chốt, không tạo mới tùy ý mỗi khi broker redeliver. `operationId` đại diện cho một **operation logic đã persist**, không phải UUID mới ở mỗi lần retry. `stepExecutionId` dùng để liên hệ metadata Batch nếu framework/protocol cần.

Ví dụ serialize message bằng Jackson, không thêm business payload:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Objects;
import java.util.UUID;

public final class SafeWorkMessageCodec {
    private static final ObjectMapper JSON = new ObjectMapper();

    public static byte[] encode(SafeWorkRequest request) throws Exception {
        Objects.requireNonNull(request, "request");
        byte[] bytes = JSON.writeValueAsBytes(request);

        // Ngưỡng minh họa, phải đo và chọn theo middleware thực tế.
        if (bytes.length > 4096) {
            throw new IllegalArgumentException(
                    "Unexpectedly large work message");
        }
        return bytes;
    }

    public static SafeWorkRequest decode(byte[] bytes) throws Exception {
        if (bytes == null || bytes.length == 0
                || bytes.length > 4096) {
            throw new IllegalArgumentException(
                    "Invalid work message size");
        }
        return JSON.readValue(bytes, SafeWorkRequest.class);
    }
}
~~~

Snippet thứ hai dùng record `SafeWorkRequest` ở snippet thứ nhất. Trong hệ thống thật, consumer còn cần xác thực nguồn message và **authorization** của `workRef` khi resolve; validation ở DTO không thể thay cho chúng. Nếu xây producer/consumer bằng Spring Integration, converter tương ứng phải dùng đúng version/codec và xử lý malformed message không lặp retry vô hạn.

**Quan trọng:** chỉ cần ghi `System.out.println(request)` là đã lộ toàn bộ field của record. Dù request minh họa không chứa PII, vẫn nên dùng log có whitelist trường; đừng mặc định rằng mọi `toString()` của DTO tương lai đều an toàn.

### Những điều tuyệt đối không đưa vào DTO

~~~java
// Anti-pattern mang tính minh họa; không sử dụng trong ứng dụng.
record UnsafeWorkRequest(
        UUID workRef,
        String dbPassword,
        String customerEmail,
        String paymentToken,
        byte[] fullDocumentBytes) {}
~~~

Không gửi `dbPassword` hoặc `paymentToken` trong message ngay cả khi chúng được mã hóa sơ sài bằng Base64. **Base64 là encoding, không phải encryption.**

## 8. Worker phải tự xác thực và kiểm tra quyền đọc dữ liệu

Một worker không thể mặc định rằng mọi `workRef` từ một queue “nội bộ” đều được phép đọc. Queue/topic có thể bị publish nhầm, account khác có thể bị cấp quyền thừa, hoặc replay một message cũ trong sai môi trường.

Thiết kế worker nên tách ba bước:

1. **Authenticate**: xác định danh tính process thông qua workload identity, mTLS hoặc service principal được tin cậy.
2. **Authorize**: xác minh principal được phép xử lý `workRef`, tenant/snapshot và resource tương ứng.
3. **Execute**: resolve nguồn, validate version/checksum, mở transaction và thực hiện business logic.

Một phác họa contract ứng dụng:

~~~java
import java.util.UUID;

record WorkAssignment(
        String snapshotId,
        String sourceResource,
        String sourceVersion) {}

interface AssignmentResolver {
    WorkAssignment resolveAuthorized(
            UUID workRef,
            String authenticatedPrincipal);
}

final class WorkerDispatcher {
    private final AssignmentResolver resolver;

    WorkerDispatcher(AssignmentResolver resolver) {
        this.resolver = resolver;
    }

    WorkAssignment prepare(
            SafeWorkRequest request,
            String authenticatedPrincipal) {
        if (authenticatedPrincipal == null
                || authenticatedPrincipal.isBlank()) {
            throw new SecurityException("Worker is not authenticated");
        }

        return resolver.resolveAuthorized(
                request.workRef(), authenticatedPrincipal);
    }
}
~~~

`authenticatedPrincipal` phải đến từ tầng bảo mật/runtime, **không được nhận trực tiếp từ JSON payload**. Implementation của `AssignmentResolver` phải kiểm tra theo DB/ACL/RLS tương ứng như truy vấn ở mục 6.

Nếu `sourceResource` là object key hoặc URL, resolver còn phải kiểm tra đúng bucket/host/prefix cho phép và object version, tránh path traversal và SSRF. Worker chỉ nên được cấp quyền đọc nhóm nguồn của nó; **mã định danh khó đoán không thay thế kiểm tra quyền**.

## 9. Khi sử dụng Spring Batch StepExecutionContext

Trong remote partitioning, manager có thể đặt input key/range vào `StepExecutionContext` để worker bind bằng `@StepScope`. Điều này tiện cho restart nhưng cần phân loại thông tin lưu trong context:

| Nên đưa vào context | Cần cân nhắc hoặc tránh |
| --- | --- |
| `workRef`, `inputKey` logic không chứa PII, range ID đã được đánh giá | `accessToken`, `dbPassword`, signed URL có quyền rộng |
| `snapshotId`/`manifestVersion` | Họ tên khách hàng, email, địa chỉ |
| Checkpoint nhỏ của `ItemStream` | List hàng triệu bản ghi hoặc blob tài liệu |
| Số thứ tự file/offset hoặc version | Object `Connection`, HTTP client, Spring bean |
| Correlation ID có semantics rõ | Raw exception stack chứa SQL parameter nhạy cảm |

Ví dụ worker đọc `workRef` từ context:

~~~java
@Bean
@StepScope
MyPartitionReader partitionReader(
        @Value("#{stepExecutionContext['workRef']}") String ref,
        AssignmentResolver resolver,
        WorkerIdentity identity) {

    if (ref == null || ref.isBlank()) {
        throw new IllegalArgumentException("Missing workRef");
    }

    UUID workRef = UUID.fromString(ref);
    WorkAssignment assignment =
            resolver.resolveAuthorized(
                    workRef, identity.authenticatedPrincipal());

    // MyPartitionReader là component ứng dụng minh họa.
    return new MyPartitionReader(assignment);
}
~~~

Đây là **snippet kết nối ý tưởng**, giả định `MyPartitionReader`/`WorkerIdentity` do ứng dụng định nghĩa, không phải class có sẵn trong Spring Batch. Một bean reader thực tế phải implement `ItemReader`/`ItemStream` phù hợp để checkpoint. Cần thêm các import Spring/UUID theo dự án.

**Lưu ý:** `ExecutionContext` được serialize và lưu bền vững ở `JobRepository`, nên không có lý do an toàn để đặt secret tại đây rồi cho rằng nó “không qua broker”. Metadata DB, backup, JobExplorer và các công cụ vận hành cũng phải được bảo vệ.

## 10. TLS, mã hóa lưu trữ và mã hóa payload: ba lớp khác nhau

| Kiểm soát | Bảo vệ điều gì? | Không giải quyết điều gì? |
| --- | --- | --- |
| **TLS** giữa client và broker | Nghe lén/sửa đổi dữ liệu khi truyền trên kết nối được bảo vệ | Broker vẫn có thể thấy payload sau khi nhận |
| **Encryption at rest** của broker/storage/backup | Dữ liệu nằm trên đĩa và thiết bị lưu trữ | Tài khoản broker có quyền đọc message hợp lệ vẫn có thể thấy plaintext |
| **Application-level authenticated encryption** | Payload được mã hóa trước khi publish, giải mã chỉ ở worker được cấp khóa | Không ngăn worker hợp lệ log plaintext; không sửa ACL hoặc idempotency |
| **Tokenization/reference-only** | Tránh đưa giá trị thật vào message | Token/ID vẫn có thể liên kết hoặc trở thành capability nếu không kiểm tra quyền |
| **Broker ACL/authorization** | Ai publish/subscribe/replay trên queue/topic | Không xóa dữ liệu đã rò rỉ sang log/backup |
| **Data retention/deletion** | Giới hạn thời gian message tồn tại | Không bảo vệ message khi còn được phép truy cập |

Khi payload nhạy cảm **không thể loại bỏ**, cần cân nhắc mã hóa ở ứng dụng bằng thuật toán AEAD được thư viện đáng tin cậy hỗ trợ (ví dụ AES-GCM) với **nonce không tái sử dụng cho cùng key**, quản lý key bằng KMS/vault và luân chuyển khóa có version. Không tự xây thuật toán mã hóa hoặc dùng Base64/XOR như “bảo mật”.

Một thiết kế envelope encryption thường gồm:

~~~text
Producer:
  - Lấy data key từ KMS/secret infrastructure theo policy
  - AEAD-encrypt payload nhỏ đã giảm field, gắn context phù hợp
  - Publish ciphertext + key identifier + metadata không nhạy cảm

Broker:
  - Chỉ lưu/vận chuyển ciphertext
  - Vẫn cần TLS, ACL, retention và bảo vệ metadata

Worker:
  - Xác thực service identity
  - Kiểm tra quyền lấy/decrypt key
  - Xác thực AEAD tag, reject payload bị sửa
  - Giải mã trong phạm vi xử lý tối thiểu, không log plaintext
~~~

Chính sách lưu khóa phải đủ cho **retry, DLQ replay và restart**. Xóa khóa quá sớm có thể làm message lịch sử không giải mã được; giữ khóa vô hạn lại tăng rủi ro. Bảo vệ và xóa dữ liệu cần cân đối theo thời hạn nghiệp vụ và chính sách áp dụng.

Mã hóa payload không có nghĩa là broker, consumer hay JobRepository được miễn khỏi quản lý quyền. Headers, timing, message size, partition name và correlation vẫn có thể là metadata nhạy cảm.

## 11. Secrets phải đến từ runtime identity, không phải message

Sai lầm thường gặp:

~~~json
{
  "workRef": "39166b71-09d9-4eb9-9b68-1df0d0f40566",
  "databaseUsername": "batch_worker",
  "databasePassword": "demo-password-not-real",
  "apiToken": "demo-token-not-real"
}
~~~

Dù ví dụ dùng chuỗi giả, kiểu thiết kế trên tạo hai bề mặt lộ mới: **broker storage** và **mọi consumer có quyền đọc queue**. Tất cả retry/replay cũng mang theo credential, khiến việc thu hồi khó hơn.

Hướng phù hợp:

- **Worker service account / workload identity** nhận quyền hạn theo môi trường.
- **Secret manager / KMS** hoặc cấu hình runtime đã bảo vệ cung cấp credential cần thiết.
- **RBAC/ACL** hạn chế worker nào được gọi API, đọc bucket, tra manifest, ghi bảng đích.
- **Rotating credentials** không đòi gửi lại message; worker lấy bản mới theo cơ chế runtime hỗ trợ.
- **Short-lived credentials** được cấp trong ranh giới xác thực phù hợp; không copy credential vào broker, `ExecutionContext` hoặc log.

Trong Kubernetes, secret hoặc service account không tự an toàn chỉ vì được đặt vào pod. Cần kiểm soát API permissions, mount, env exposure, audit và quyền truy cập của workload. Không để mọi worker trên cluster dùng cùng một service account có quyền admin đối với tất cả dữ liệu nếu không cần.

## 12. Headers, correlation, logs và traces cũng có thể rò rỉ

Đôi khi đội phát triển đã xóa PII khỏi JSON body nhưng lại đặt `customerEmail` vào header `correlationId` hoặc log trong exception:

~~~text
# Không nên:
correlationId = customer-12345@example.com
metric label  = orderId:987654321
log message   = "Failed order " + entireOrder.toString()

# Nên:
correlationId = opaque operation UUID
metric label  = messageType + schemaVersion + errorCategory
log fields    = event, operationId, partitionName, status, duration
~~~

Đặc biệt không gắn `customerId`, `orderId`, email hoặc `workRef` có cardinality lớn thành **nhãn metric time-series** theo từng item. Nó vừa tạo rủi ro rò rỉ, vừa làm bùng số lượng time series.

### Logging có whitelist và không gọi toString của payload

~~~java
import java.util.logging.Logger;

public final class SafeWorkLog {
    private static final Logger LOG =
            Logger.getLogger(SafeWorkLog.class.getName());

    public static void accepted(SafeWorkRequest work) {
        // Chỉ log các trường đã đánh giá; không log body/toString.
        LOG.info(() -> String.format(
                "event=work_accepted type=%s schema=%d step=%d",
                work.messageType(),
                work.schemaVersion(),
                work.stepExecutionId()));
    }
}
~~~

Ngay cả `stepExecutionId` có thể được liên hệ tới job nhạy cảm trong một tổ chức. Hãy phân quyền log và định nghĩa whitelist phù hợp. Trong các môi trường có mức nhạy cảm cao, có thể chỉ log một request correlation opaque hoặc hashed reference được kiểm soát.

### Exception và APM

- Không log payload JSON thô trong `JsonProcessingException` nếu exception có thể kèm đoạn input.
- Không tự ghi SQL với toàn bộ bind values khi chúng chứa PII.
- Tắt hoặc giới hạn “capture HTTP request body”/“capture messaging payload” của APM trên đường dữ liệu nhạy cảm.
- Với tracing, chỉ truyền trace context cần thiết; đừng cho các field PII thành span attributes hoặc baggage.
- Với alert/ticket/email, dùng mã lỗi và link tới công cụ có quyền thay vì đính kèm raw DLQ payload.

## 13. Retry queue và Dead Letter Queue là bề mặt rò rỉ lớn

Một message lỗi không biến mất khi worker throw exception. Theo middleware và policy, nó có thể:

1. Được requeue/redeliver nhiều lần.
2. Được copy sang retry queue/topic có delay.
3. Được chuyển sang **Dead Letter Queue/Topic (DLQ)**.
4. Được export để debug hoặc replay.
5. Nằm trên disk/backup lâu hơn tuổi của job.

Nếu message ban đầu chứa PII, **mọi đường nhánh đó đều có thể giữ PII**.

| Bước | Biện pháp |
| --- | --- |
| Publish request | Không gửi payload nhạy cảm nếu có thể; whitelist trường |
| Retry | Giữ workRef và operation key, giới hạn số lần và delay |
| DLQ | ACL riêng, không public qua dashboard/ticket, retention phù hợp |
| Replay | Chỉ operator có quyền, có audit, không tạo operation key mới tùy tiện |
| Debug | Dùng synthetic/redacted fixture, không copy payload thật |
| Backup | Mã hóa, quyền tối thiểu, retention và quy trình xóa |
| Cleanup | Xem cả original queue/log, retry, DLQ, backup và downstream exports |

**Đừng xóa DLQ vô điều kiện để “dọn PII” nếu message đại diện công việc chưa xử lý**: sẽ có nguy cơ mất dữ liệu nghiệp vụ. Cần xác định message nào đã commit, message nào cần replay, có thể thay payload bằng reference hay cần xử lý riêng, rồi thực hiện theo runbook và audit.

### Quan sát backlog an toàn

Metric nên tập trung vào:

- `request_ready_messages`, `request_inflight_messages`.
- `retry_attempts_total`, `dlq_messages`.
- `oldest_message_age_seconds`.
- `unique_business_items_committed_per_second`.
- `worker_db_connection_pending`, `broker_storage_usage`.

Tên là **gợi ý**, không bảo đảm Spring Batch, RabbitMQ, Kafka hay Micrometer xuất sẵn. Dashboard không cần in customer profile để đo throughput hay xác định bottleneck.

## 14. Retention, quyền được biết và vòng đời dữ liệu

Không có một ngưỡng lưu giữ chung đúng cho tất cả doanh nghiệp. Tuy nhiên, hệ batch phân tán cần có câu trả lời cụ thể:

- Request/reply được giữ bao lâu ở broker? Retry/DLQ giữ bao lâu?
- Kafka retention có giữ record cũ sau khi consumer đã commit offset không?
- Backup/snapshot lưu ở đâu và bao lâu, ai có quyền khôi phục?
- Khi khách hàng yêu cầu sửa/xóa dữ liệu, message cũ và bản sao trong pipeline được xử lý theo chính sách nào?
- Worker dùng reference tới object đã xóa hoặc hết quyền thì fail theo policy nào?
- Job có thể restart sau nhiều ngày không; snapshot/manifest phải còn tới thời điểm nào?
- Có cần rút ngắn retention cho các nguồn dữ liệu nhạy cảm hoặc dùng reference-only để giảm bản sao?

Một dữ liệu **không còn trong ready queue** vẫn có thể tồn tại trong Kafka retained log, reply queue, DLQ hoặc backup. Xóa một message theo offset hoặc “commit consumer” không nhất thiết xóa bytes vật lý ngay lập tức.

Nếu chọn reference-only, việc thu hồi quyền đọc ở nguồn có thể giảm rủi ro dù broker còn ID, nhưng ID vẫn cần được quản lý và có thể tiết lộ quan hệ nghiệp vụ. Xóa/revoke nguồn khi job chưa hoàn thành lại có thể làm restart thất bại; cần lifecycle business và retention rõ ràng.

## 15. Retry, idempotency và tính đúng khi worker mất kết nối

Bảo vệ thông tin không thể tách khỏi tính đúng: khi worker đã commit dữ liệu nhưng mất reply, manager có thể gửi lại cùng workRef/partition.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant W as Worker A
    participant D as Business DB
    participant W2 as Worker B
    M->>Q: workRef K / operationId O
    Q->>W: Deliver K
    W->>D: Commit business effects của K
    Note over W,M: Worker chết / reply hoặc ACK mất
    Q->>W2: Redeliver cùng K, O
    W2->>D: Thử ghi lại record
    D-->>W2: Unique key / UPSERT / ledger chống lặp
    W2-->>M: Status của K / O
~~~

Nếu mỗi lần retry tạo một reference/operationId mới, việc bảo vệ trùng lặp theo khóa kỹ thuật có thể không còn hiệu quả. Do đó:

- `workRef` và `operationId` phải được lưu và tái dùng cho cùng công việc logic.
- Writer dùng **business key** ổn định; một `stepExecutionId` có thể đổi khi restart/reprocess, không đủ làm khóa nghiệp vụ duy nhất.
- Không dùng `UPDATE total = total + :amount` mà không có ledger/dedup khi replay có thể xảy ra.
- Khi timeout, xác minh worker cũ đã dừng hoặc dùng ownership/fencing nếu nguy cơ hai worker ghi đồng thời.
- Một reply “SUCCESS” không thay thế đối soát thực tế của output nghiệp vụ.
- Không vì muốn loại PII khỏi broker mà cắt mất `snapshotId`/correlation cần thiết cho dedup/restart; thay bằng ID logic không nhạy cảm và một mapping persist.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    result_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

~~~sql
INSERT INTO processed_order(
    snapshot_id, order_id, source_version, result_code
)
VALUES (:snapshotId, :orderId, :sourceVersion, :resultCode)
ON CONFLICT (snapshot_id, order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    result_code = EXCLUDED.result_code
WHERE processed_order.source_version < EXCLUDED.source_version;
~~~

Mã này minh họa idempotent **final row state theo version**; nếu còn trigger, outbox, API payment hay email, cần bảo vệ riêng các hiệu ứng đó. Dữ liệu nhạy cảm cần được tra ở nguồn bảo vệ và chỉ lưu đúng trường business thực sự yêu cầu.

## 16. Sizing: giảm payload giúp gì và phải đánh đổi gì?

Giả sử manager đang phát **150 chunk request/s**, mỗi request khi chứa raw records có trung bình **256 KiB**. Nếu chỉ gửi workRef/ID trong một thiết kế reference-based, payload trung bình có thể khoảng **512 byte** (số minh họa).

~~~text
Raw payload rate      = 150 × 256 KiB/s = 38.400 KiB/s
                      ≈ 37,5 MiB/s

Reference payload rate = 150 × 512 B/s
                       = 76.800 B/s ≈ 75 KiB/s

Trong 10 phút backlog tăng 30.000 message:
Raw request payload    ≈ 30.000 × 256 KiB ≈ 7,32 GiB
Reference payload      ≈ 30.000 × 512 B ≈ 14,65 MiB
~~~

Đây là **ước lượng payload** chưa tính broker metadata, replication, retry copies, compression, retention và index. Mức giảm có thể rất lớn nhưng **không miễn phí**:

- Worker phải gọi source/manifest để lấy dữ liệu.
- Nếu mỗi workRef gây nhiều truy vấn nhỏ, source DB/API có thể bị quá tải.
- Object storage/network giữa worker và nguồn có thể tăng traffic.
- Worker có thể cần mở connection mới hoặc tải dữ liệu theo batch.
- Snapshot/version phải được giữ để mọi worker và lần restart đọc được cùng dữ liệu.
- Cần thêm authorization checks và audit tại nguồn.

Bởi vậy, không chỉ đo broker message size rồi kết luận hệ thống nhanh hơn. Phải đo **throughput business item hữu ích**, end-to-end latency, broker usage, source I/O, DB pool pending và khả năng restart.

### Khi nào giữ remote chunking?

Nếu manager chỉ có một reader mà nhiều worker không thể trực tiếp truy cập nguồn, remote chunking có thể vẫn là lựa chọn hợp lý. Khi bắt buộc gửi item, hãy giảm field bằng DTO chuyên dụng, đánh giá dữ liệu tối thiểu, mã hóa/policy vận hành phù hợp; **không xóa các trường nghiệp vụ cần thiết** để rồi tạo kết quả sai.

Nếu nguồn chia theo range/file/tenant và worker truy cập được, **remote partitioning** thường là hướng tự nhiên để broker chỉ vận chuyển ID/assignment.

## 17. Kiểm thử bảo mật bắt buộc trước khi production

Một hệ thống chỉ “không gửi password” chưa đủ. Cần chứng minh bằng thử nghiệm:

| Test | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| **Payload allowlist** | Serialize request mẫu có PII ở source | Broker request không chứa field PII/secret |
| **Header audit** | Đặt trace/correlation | Không chứa email, số giấy tờ, token |
| **DLQ/retry** | Cố tình tạo poison message | Bản sao không tự chứa dữ liệu cấm; ACL/retention đúng |
| **Logging** | Deserialize fail, DB timeout, worker crash | Không dump raw payload, SQL bind hoặc credentials |
| **Worker authZ** | Worker tenant A gửi workRef tenant B | Bị từ chối dù UUID đúng |
| **IDOR** | Thử workRef hợp lệ nhưng không được phân quyền | Không lộ source locator hoặc dữ liệu |
| **TLS/authn** | Client không tin certificate hoặc sai identity | Không kết nối/không được cấp quyền |
| **At-rest/backup** | Kiểm tra broker storage và backup policy | Mã hóa/quyền truy cập/retention phù hợp |
| **Secrets** | Rotate credentials khi có backlog | Worker vẫn lấy secret qua runtime, message không chứa secret |
| **Reference expiry** | Restart sau thời gian chờ dài | Có cơ chế renew theo policy hoặc báo lỗi phục hồi rõ |
| **Idempotency** | Commit DB rồi mất reply | Replay không tạo effect trùng |
| **Source drift** | Object tại key bị thay, version khác | Worker phát hiện mismatch, không âm thầm xử lý dữ liệu mới |
| **Scaling** | Tăng 1 → 2 → 4 → 8 worker | Không vượt DB/source quota, không mở rộng quyền vô cớ |
| **Observability** | Dashboard, error tracker, trace, ticket | Không có secrets/PII trong label/baggage/body |
| **Disaster recovery** | Khôi phục broker/repository backup | Access controls vẫn đúng, không lộ bản sao vào môi trường test |

### Test tự động để ngăn payload chứa trường cấm

Ví dụ JUnit 5 cho JSON được serialize từ `SafeWorkRequest`. Test dùng danh sách trường đại diện; trong dự án thật, nên quản lý **schema allowlist** thay vì chỉ tìm chuỗi:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SafeWorkRequestTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void payloadUsesOnlyApprovedFields() throws Exception {
        SafeWorkRequest request = SafeWorkRequest.create(
                UUID.fromString("39166b71-09d9-4eb9-9b68-1df0d0f40566"),
                UUID.fromString("fc71ef82-ad2e-497f-968a-52ff0e43a6d1"),
                5678);

        JsonNode root = mapper.readTree(
                mapper.writeValueAsBytes(request));

        Set<String> approved = Set.of(
                "messageType", "schemaVersion",
                "workRef", "operationId", "stepExecutionId");

        root.fieldNames().forEachRemaining(
                name -> assertTrue(approved.contains(name)));

        assertEquals(approved.size(), root.size());
        assertFalse(root.has("customerEmail"));
        assertFalse(root.has("dbPassword"));
        assertFalse(root.has("paymentToken"));
    }
}
~~~

Bộ test chứng minh **shape của DTO minh họa**, không bảo đảm mọi giá trị nội dung là không nhạy cảm. Trong thực tế còn cần schema reviews, redaction, dependency scanner, thử nghiệm end-to-end qua broker thật và kiểm soát mọi request/reply/DLQ converter.

### Thử nghiệp vụ và hiệu năng sau khi đổi kiến trúc

1. Chạy baseline với một worker và snapshot cố định, ghi `JobExecution` time, throughput và checksum.
2. Chạy thiết kế mới với workRef, xác nhận mọi partition đọc đúng nguồn bằng authorization.
3. Inject lỗi giữa DB commit và broker reply; restart cùng identifying `JobParameters`, writer phải idempotent.
4. Kiểm tra worker mới vẫn resolve được manifest/version sau crash và rolling deploy.
5. Tăng concurrency, đo DB pool, source I/O, broker backlog và CPU để tìm nút thắt mới.
6. Đối soát output bằng business key/version, không chỉ nhìn status `COMPLETED`.

## 18. Runbook khi phát hiện message đã chứa dữ liệu nhạy cảm

Nếu phát hiện một production topic/queue hoặc DLQ đang giữ password, token hay PII ngoài phạm vi được phê duyệt, cần có xử lý sự cố rõ:

1. **Xác định dữ liệu và mức độ ảnh hưởng:** trường nào, bao nhiêu message, môi trường, queue/topic, version và khoảng thời gian.
2. **Dừng phát sinh bản sao mới có kiểm soát:** tắt đường publish nguy hiểm hoặc chuyển sang payload tối giản; không làm rơi công việc chưa commit.
3. **Bảo vệ bằng chứng và quyền truy cập:** giới hạn operator/consumer, audit các lần truy cập, không copy raw payload vào chat/ticket không bảo mật.
4. **Nếu có credential bị lộ:** thu hồi/rotate qua hệ quản lý secret và kiểm tra log truy cập; không chỉ xóa message.
5. **Theo dấu các bản sao:** primary queue/log, in-flight, retry, DLQ, broker backup, object export, observability và môi trường staging.
6. **Xác định chính sách remediation:** retention, xóa/thu hồi, migration sang workRef hoặc re-encryption theo quy trình an toàn.
7. **Bảo toàn tính đúng job:** với mỗi message, biết đã commit chưa, có cần replay không, operation key và checkpoint có còn hợp lệ không.
8. **Kiểm tra worker cũ:** tránh hai worker đồng thời xử lý cùng workRef khi thay đổi route/consumer.
9. **Đối soát nghiệp vụ:** unique keys, version, side effects, missing/duplicate result.
10. **Ngăn tái diễn:** contract allowlist, test serializer, logging sanitization, DLQ ACL/retention, review khi thêm field DTO.

Không nên hứa rằng “xóa queue là đã xóa mọi bản sao”: broker disk/retention, backup và log có thể vẫn chứa thông tin. Việc thông báo sự cố hoặc yêu cầu xử lý pháp lý phải dựa trên chính sách tổ chức và luật áp dụng; bài học này không thay thế tư vấn tuân thủ chuyên ngành.

## 19. Bài tập tình huống

Một hệ thống Spring Batch remote chunking chạy job nhập **4 triệu giao dịch trong 2 giờ**. Manager gửi 100 chunk/s, mỗi chunk có 250 item. Mỗi item chứa `customerEmail`, `shippingAddress`, `bankAccount`, `amountMinor` và `orderId`. RabbitMQ có retry queue và DLQ; worker dùng cùng một DB service account có quyền đọc mọi tenant.

Nhóm đề xuất ba phương án:

- **A:** Giữ nguyên message nhưng bật TLS giữa manager và broker.
- **B:** Xóa email khỏi log, nhưng vẫn gửi toàn bộ item vào broker/DLQ.
- **C:** Nếu nguồn chia được, chuyển sang remote partitioning để manager gửi workRef, worker tra snapshot bằng identity được phân quyền. Với trường hợp vẫn cần remote chunking, chỉ gửi các field tối thiểu, bảo vệ payload và mọi hàng đợi theo policy.

**Câu hỏi:**

1. Vì sao phương án A chưa đáp ứng nguyên tắc không gửi dữ liệu nhạy cảm trong message?
2. B sửa được loại rủi ro nào, còn thiếu rủi ro nào?
3. C giảm payload qua broker như thế nào, và làm phát sinh bottleneck gì?
4. Một UUID `workRef` khó đoán có đủ để worker được phép đọc mọi dữ liệu không?
5. Nếu DLQ giữ bản sao 30 ngày, có thể tuyên bố request đã biến mất sau khi consumer ACK không?
6. Khi worker đã commit nhưng mất reply, việc replay workRef phải được bảo vệ thế nào?
7. Nếu một chunk có kích thước serialized trung bình 128 KiB, 10.000 message tồn đọng chiếm bao nhiêu MiB payload?
8. Nếu chỉ gửi 512 B/reference, 10.000 message chiếm khoảng bao nhiêu MiB payload?
9. Thiết kế test nào chứng minh không có `bankAccount` trong **body, header, DLQ và log**?

### Gợi ý lời giải

- **(1)** TLS chỉ bảo vệ **in transit**; broker vẫn nhận/lưu plaintext, admin/consumer/DLQ vẫn có thể thấy.
- **(2)** B giúp giảm lộ qua log, nhưng broker, retry/DLQ, backup, headers và quyền consumer vẫn cần kiểm soát.
- **(3)** C giảm payload broker, nhưng tăng nhu cầu worker truy cập nguồn/manifest, authZ, DB/API I/O và quản lý snapshot.
- **(4)** Không. Reference chỉ định danh; worker phải được xác thực và phân quyền tới resource/snapshot/tenant.
- **(5)** Không. ACK không có nghĩa DLQ, Kafka retention, disk backup hoặc trace đã bị xóa.
- **(6)** Dùng operation ID/business key ổn định, writer idempotent, xác minh worker cũ và đối soát dữ liệu.
- **(7)** `10.000 × 128 KiB = 1.280.000 KiB = 1.250 MiB` payload, chưa tính overhead.
- **(8)** `10.000 × 512 B = 5.120.000 B ≈ 4,88 MiB` payload, chưa tính overhead.
- **(9)** Dùng schema allowlist test + integration test broker/retry/DLQ, kiểm tra tracing và log bằng synthetic sensitive markers; xác minh cả quyền truy cập/retention.

## Checklist trước khi phát hành

- [ ] Message body/request/reply chỉ có những trường đã được phê duyệt; không có token, password hoặc PII không cần thiết.
- [ ] Headers, correlation, trace baggage và metric labels được kiểm tra cùng mức nghiêm ngặt với body.
- [ ] Đã xem xét remote partitioning hoặc reference-only khi remote chunking phải chuyển item nhạy cảm.
- [ ] `workRef`/`inputKey` có snapshot/manifest bất biến và không chứa URL token/secret nhạy cảm.
- [ ] Worker kiểm tra authorization từ **principal đã xác thực**, không tin tenant/role do payload tự khai.
- [ ] Broker dùng TLS, authentication, topic/queue ACL, encryption at rest và backup policy tương ứng.
- [ ] Khi bắt buộc chuyển payload nhạy cảm, có đánh giá và giải pháp mã hóa/retention phù hợp.
- [ ] Worker lấy credentials từ runtime identity/secret manager, không từ message hoặc `ExecutionContext`.
- [ ] Retry, DLQ, replay và backup đều có quyền, thời gian lưu, audit và xử lý sự cố rõ.
- [ ] Writer chống replay theo business key; mất ACK/reply không tạo hiệu ứng trùng.
- [ ] Test secret/PII leakage bao phủ payload, headers, DLQ, log, trace, export và test environment.
- [ ] Đã đo throughput toàn job, broker backlog, source I/O, JDBC connection và tính đúng dữ liệu sau khi đổi kiến trúc.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): phân biệt multi-threaded step, remote partitioning và remote chunking.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): message channels, request/reply giữa manager và worker.
- [Spring Batch Reference – JobRepository và ExecutionContext](https://docs.spring.io/spring-batch/reference/domain.html): state/checkpoint, job/step lifecycle.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message conversion, headers và middleware adapters.
- [RabbitMQ – Access Control](https://www.rabbitmq.com/docs/access-control): authentication/authorization, user permissions.
- [RabbitMQ – TLS Support](https://www.rabbitmq.com/docs/ssl): TLS giữa client và broker.
- [Apache Kafka – Security](https://kafka.apache.org/documentation/#security): authentication, authorization và encryption in transit.
- [OWASP Cheat Sheet – Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý bí mật ngoài mã nguồn/message.
- [OWASP Cheat Sheet – Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh ghi dữ liệu bí mật/nhạy cảm vào log.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): lỗi phân quyền ở mức đối tượng, bảo vệ API tra nguồn dữ liệu.

## Ghi nhớ

**Không gửi dữ liệu nhạy cảm trong message là một quyết định kiến trúc và vòng đời dữ liệu, không chỉ là cấu hình TLS hay xóa vài trường log.** Khi có thể, manager chỉ gửi **work reference** tới snapshot/manifest bền vững; worker tự xác thực, kiểm tra quyền và lấy dữ liệu từ nguồn được bảo vệ. Remote partitioning thường giúp giảm dữ liệu item đi qua broker, trong khi remote chunking cần kiểm tra nghiêm ngặt payload và có thể phải đổi mô hình. Nếu không thể tránh payload nhạy cảm, áp dụng data minimization, mã hóa, ACL, retention, quản lý secrets và bảo vệ mọi bản sao retry/DLQ/log. Đặc biệt, reference không phải quyền truy cập, TLS không bảo vệ dữ liệu khỏi broker hợp lệ và security không thay thế retry/restart idempotent. Chỉ tăng worker khi cả **bảo mật, tính đúng và giới hạn tài nguyên** đều đã được kiểm chứng.
