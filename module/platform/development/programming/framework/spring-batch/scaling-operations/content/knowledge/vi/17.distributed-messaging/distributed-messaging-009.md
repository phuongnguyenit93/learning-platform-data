# Version hóa message contract trong Spring Batch phân tán

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Định nghĩa **message contract** giữa manager, broker và worker trong remote partitioning hoặc remote chunking, phân biệt schema, semantics, delivery và transaction.
- Giải thích **backward compatibility**, **forward compatibility**, **full compatibility**, và rủi ro khi manager/worker chạy đồng thời nhiều phiên bản.
- Thiết kế envelope thông điệp có `messageType`, `schemaVersion`, định danh nghiệp vụ, correlation, payload và các trường tùy chọn rõ nghĩa.
- Phân loại thay đổi **tương thích** hoặc **breaking**: thêm field, đổi kiểu, đổi tên, enum mới, thay ý nghĩa đơn vị hoặc cách diễn giải checkpoint.
- Viết một codec JSON minh họa bằng Java 17/Jackson để worker đọc được hai phiên bản contract, từ chối phiên bản chưa biết và validate dữ liệu.
- Lập kế hoạch rolling deployment, rollback, xử lý backlog cũ, retry/DLQ, schema migration và kiểm thử hợp đồng liên phiên bản.
- Bảo vệ idempotency, restart và kết quả nghiệp vụ khi message bị giao lại, reply thất lạc hoặc hai worker chạy khác phiên bản.
- Đo throughput hữu ích, lỗi deserialize, backlog theo schema và tình trạng tài nguyên để chọn chiến lược scale phù hợp.

## 1. Vì sao version hóa message contract quan trọng?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, một job xử lý dữ liệu lớn có thể tăng thông lượng bằng parallel steps, partitioning hoặc các worker chạy trên nhiều JVM. Khi công việc chuyển qua broker, **manager và worker không còn gọi nhau bằng một method Java thông thường**: dữ liệu phải được mã hóa thành message, gửi qua mạng, giải mã và diễn giải lại.

Giả sử một job remote chunking đang chạy liên tục ba giờ:

1. Manager phiên bản **v1** phát các request chứa 200 đơn hàng/chunk.
2. RabbitMQ hoặc Kafka còn backlog gồm hàng nghìn request v1.
3. Nhóm triển khai worker **v2** để thêm mã phân loại dữ liệu.
4. Worker v2 không đọc được field đã đổi tên, hoặc dùng đơn vị tiền mới thay cho đơn vị cũ.
5. Các request cũ bị retry/DLQ; manager tiếp tục phát việc mới, khiến SLA trễ và khó restart.

Có trường hợp message deserialize được nhưng **diễn giải sai**: đây còn nguy hiểm hơn lỗi parse, vì worker có thể commit kết quả sai mà job vẫn báo thành công.

**Version hóa message contract** là quy trình định nghĩa, công bố, thay đổi và kiểm thử **định dạng lẫn ngữ nghĩa** thông điệp để nhiều phiên bản producer/consumer có thể vận hành an toàn trong cùng một thời gian.

~~~mermaid
flowchart LR
    M1["Manager v1"] --> Q["Broker: request cũ và mới"]
    M2["Manager v2"] --> Q
    Q --> W1["Worker v1"]
    Q --> W2["Worker v2"]
    W1 --> D["Business DB / API dùng chung"]
    W2 --> D
    W1 --> R["Reply channel"]
    W2 --> R
    R --> M2
    R --> M1
~~~

Đừng chỉ hỏi “JSON còn parse được không?”. Cần hỏi cả “worker có hiểu đúng cùng business operation không?”, “reply có được manager cũ hiểu không?” và “chạy lại message có tạo thêm side effect không?”.

## 2. Xác định ranh giới hợp đồng trước khi chọn công cụ

Một pipeline phân tán trong Spring Batch có nhiều hợp đồng, không phải một JSON duy nhất.

| Hợp đồng | Bên sản xuất / bên tiêu thụ | Nội dung | Cơ chế tương thích |
| --- | --- | --- | --- |
| **Request message** | Manager → worker | Phân công step/partition hoặc chunk item | Message serializer, schema, routing |
| **Reply message** | Worker → manager | Kết quả, correlation, trạng thái và thông tin lỗi | Reply decoder của manager |
| **`ExecutionContext` metadata** | Spring Batch ↔ `JobRepository` | Assignment, checkpoint, state job/step | `ExecutionContextSerializer`, JDBC metadata |
| **Business data contract** | Worker → DB/API/file | Business key, version và hiệu ứng cuối | Schema DB, API contract, idempotency |
| **Observability contract** | Manager/worker → monitoring | Mã lỗi, trace/correlation, version tags | Log/metric naming và compatibility |

Trong **remote partitioning**, manager thường giao **định danh của một `StepExecution`** hoặc metadata cần thiết để worker tra step và context. Worker thường tự đọc dữ liệu của partition.

Trong **remote chunking**, manager đọc input, tạo chunk và gửi **nội dung item** đến worker xử lý/ghi. Việc version hóa payload item có thể quan trọng hơn vì broker chứa dữ liệu nghiệp vụ thật.

~~~mermaid
flowchart TD
    A["Manager tạo work"] --> B["Message converter / wire schema"]
    B --> C["RabbitMQ / Kafka / Middleware"]
    C --> D["Worker message converter"]
    D --> E["Business operation"]
    E --> F["DB commit / idempotency"]
    E --> G["Reply converter / reply schema"]
    G --> H["Manager correlation"]
    A --> J["Spring Batch JobRepository"]
    E -. "Worker StepExecution state khi dùng" .-> J
    J --> K["ExecutionContextSerializer: định dạng metadata riêng"]
~~~

**Phân biệt quan trọng:** thay đổi `ExecutionContextSerializer` trong `JobRepository` **không tự đổi** message converter của broker. Ngược lại, đổi JSON/Avro/Protobuf trên request channel **không tự migration** các checkpoint đã lưu.

Khi bài học nói “version message contract”, mặc định đề cập **wire contract request/reply**. Những ảnh hưởng tới `JobRepository` và `ExecutionContext` cần được phân tích riêng vì cùng một worker có thể phải đọc cả hai loại state.

## 3. Message contract bao gồm gì?

Một hợp đồng tốt định nghĩa nhiều hơn tên field:

| Thành phần | Ví dụ | Câu hỏi cần khóa trước khi deploy |
| --- | --- | --- |
| **Message type** | `order-chunk-request`, `order-chunk-result` | Làm sao consumer chọn đúng handler? |
| **Schema version** | `schemaVersion=1` hoặc `2` | Phiên bản nào được chấp nhận? |
| **Business/work identity** | `snapshotId`, `operationKey` | Replay cùng công việc có giữ key ổn định không? |
| **Correlation** | `requestId`, `chunkKey` | Reply liên kết với request/step nào? |
| **Payload** | Danh sách item hoặc `stepExecutionId` | Kiểu, required fields, đơn vị và giới hạn kích thước? |
| **Headers** | Content type, trace, tenant, attempt | Header nào thực sự được broker chuyển tiếp? |
| **Status/result** | `SUCCESS`, `RETRYABLE_ERROR` | Manager cũ xử lý status mới thế nào? |
| **Validation** | Range hợp lệ, key không rỗng | Sai dữ liệu phải reject hay dùng default? |
| **Delivery semantics** | Ack, redelivery, retry, DLQ | Message có thể xử lý nhiều lần không? |
| **Security** | Auth, allowed type, payload size | Có ngăn deserialization nguy hiểm và replay trái phép không? |

Một số field đại diện cho **schema**, một số thuộc **protocol/lifecycle**. Ví dụ thêm `traceId` là thay đổi về quan sát; đổi ý nghĩa của `operationKey` từ “một chunk logic” sang “mỗi attempt” là **thay đổi semantics breaking** dù cả hai vẫn là String.

### Ba định danh nên tách riêng

- **`messageId`**: định danh một message được publish, có thể đổi nếu có attempt mới; hữu ích cho truy dấu transport.
- **`operationKey`**: định danh công việc logic cần bảo vệ khỏi việc thực hiện lặp, phải ổn định qua retry/redelivery của **cùng công việc**.
- **Business key**: ví dụ `(snapshotId, orderId, sourceVersion)` để ghi đúng kết quả nghiệp vụ ngay cả khi partition/chunk được chia lại.

Không dựa duy nhất vào `JobExecutionId` hoặc `StepExecutionId` để chống side effect trùng **xuyên những lần reprocess/instance khác nhau**: ID kỹ thuật có thể thay đổi, trong khi một order nghiệp vụ vẫn là order cũ.

## 4. Backward, forward và full compatibility

Hai chiều tương thích phải được phát biểu bằng **producer** và **consumer**.

- **Backward compatibility**: **consumer mới** có thể đọc/hiểu message do **producer cũ** tạo.
- **Forward compatibility**: **consumer cũ** có thể đọc/hiểu message do **producer mới** tạo.
- **Full compatibility**: cả hai chiều được bảo đảm trong phạm vi thay đổi đã công bố.
- **Breaking change**: có ít nhất một chiều không còn được hỗ trợ mà nếu triển khai sai thứ tự sẽ làm gián đoạn hoặc hỏng dữ liệu.

| Producer phát | Consumer nhận | Câu hỏi tương thích |
| --- | --- | --- |
| v1 | v1 | Baseline đã có |
| v1 | v2 | **Backward**: worker mới có đọc được backlog cũ? |
| v2 | v1 | **Forward**: worker cũ có đọc được request mới? |
| v2 | v2 | Phiên bản mới hoạt động độc lập có đúng không? |

Không phải cứ thêm một field tùy chọn là chắc chắn forward-compatible. Nếu decoder của v1 **từ chối unknown fields**, v2 thêm `traceId` vẫn khiến worker v1 lỗi. Nếu worker v1 kiểm tra `schemaVersion == 1`, nó cũng có thể từ chối message v2 dù mọi field cũ còn nguyên.

### Một ví dụ thay đổi tưởng như nhỏ

V1:

~~~json
{
  "messageType": "order-chunk-request",
  "schemaVersion": 1,
  "snapshotId": "orders-2026-11-25",
  "operationKey": "orders-2026-11-25:chunk-0042",
  "items": [
    { "orderId": 421, "amountMinor": 125000 }
  ]
}
~~~

V2 thêm `traceId`:

~~~json
{
  "messageType": "order-chunk-request",
  "schemaVersion": 2,
  "snapshotId": "orders-2026-11-25",
  "operationKey": "orders-2026-11-25:chunk-0042",
  "items": [
    { "orderId": 421, "amountMinor": 125000 }
  ],
  "traceId": "trace-bf35"
}
~~~

Worker v2 có thể được viết để hiểu **cả schema 1 và 2**; đó là backward compatibility. Worker v1 chỉ biết schema 1 có thể từ chối schema 2; khi đó **không có forward compatibility**. Cách triển khai an toàn là **nâng toàn bộ consumer cần thiết lên bản hiểu v2 trước khi producer bắt đầu phát v2**.

Nếu muốn một thay đổi additive thực sự đọc được bởi worker v1, cần thiết kế trước quy tắc unknown fields và chính sách version (chẳng hạn giữ major version của contract tương thích, hoặc worker v1 đã chấp nhận extension). Đừng giả định thay số version một cách tùy ý mà không cần thay decoder.

## 5. Phân loại thay đổi schema và thay đổi ngữ nghĩa

| Thay đổi | Khả năng tương thích | Điều kiện cụ thể |
| --- | --- | --- |
| Thêm field **optional** với default rõ | Thường có thể tương thích | Consumer cũ bỏ qua field lạ, consumer mới đọc message thiếu field |
| Thêm **required** field không có default | Thường breaking với dữ liệu cũ | Consumer mới không thể hiểu message cũ thiếu field |
| Đổi tên `snapshotId` thành `sourceId` | Thường breaking | Cần alias/migration và không đổi nghĩa |
| Đổi `orderId` từ `long` sang String | Có thể breaking | Decoder, precision, canonicalization và equality phải được kiểm thử |
| Thêm enum `PARTIALLY_APPLIED` | Có thể breaking | Consumer cũ không biết status mới, không được coi mặc định là success |
| Đổi `amountMinor` từ cent sang đồng | **Breaking về semantics** | JSON vẫn là số nhưng kết quả tiền bị sai |
| Đổi giờ từ giây sang mili-giây | **Breaking về semantics** | Cần field mới hoặc marker đơn vị rõ ràng |
| Thay nghĩa `operationKey` theo attempt | **Breaking về idempotency** | Replay có thể tạo hiệu ứng trùng |
| Bỏ field trước đây consumer bắt buộc | Breaking | Chỉ bỏ sau khi mọi consumer hỗ trợ field vắng |
| Thay thứ tự field trong JSON object | Thường không breaking nếu parser theo tên | Không dùng parser theo thứ tự chuỗi |
| Thêm phần tử vào mảng item | Có thể phù hợp với schema, nhưng khác **nội dung công việc** | Key/dedup, count và semantics chunk phải xét riêng |
| Thay cách mã hóa compression/content type | Breaking nếu receiver không hỗ trợ | Codec negotiation, header và rollout |
| Sửa đường dẫn reply/route | Breaking về protocol | Message cũ có thể gửi vào destination không còn consumer |

**Nguyên tắc:** tương thích ở mức schema chỉ là điều kiện cần. Một thay đổi khiến cùng business key cho kết quả khác, hoặc khiến retry mất idempotency, vẫn là breaking change cho hệ batch phân tán.

### Không “nuốt lỗi” khi thiếu field quan trọng

- Thiếu `traceId`: có thể cho phép null nếu field chỉ phục vụ tracing.
- Thiếu `snapshotId` hoặc `operationKey`: phải reject/fail rõ vì không xác định được data scope hoặc dedup.
- `orderId=0` do parser trả default cho một trường required bị thiếu: nên coi là message không hợp lệ nếu domain yêu cầu ID dương.
- Enum unknown: không tự gán `SUCCESS` hoặc `COMPLETED`.

Đặt default chỉ khi nó đúng về nghiệp vụ cho **tất cả dữ liệu lịch sử cần hỗ trợ**.

## 6. Chiến lược đánh số version và contract envelope

Không có một sơ đồ số version bắt buộc cho mọi broker. Điều quan trọng là thống nhất **cách phát và cách nhận**.

Một contract có thể có:

~~~json
{
  "messageType": "order-chunk-request",
  "schemaVersion": 2,
  "messageId": "pub-001f",
  "operationKey": "orders-2026-11-25:chunk-0042",
  "snapshotId": "orders-2026-11-25",
  "traceId": "trace-bf35",
  "items": [
    { "orderId": 421, "amountMinor": 125000 }
  ]
}
~~~

Quy ước gợi ý:

1. `messageType` xác định **loại request/reply**, không dựa vào class name của JVM.
2. `schemaVersion` mô tả **hợp đồng payload của message type ấy**, không phải version của ứng dụng hay `JobRepository`.
3. `messageId` phục vụ transport/tracing, có thể khác ở mỗi publish attempt.
4. `operationKey` và business key phục vụ xử lý lại an toàn.
5. `snapshotId` phải trỏ input có version/manifest ổn định.
6. `traceId` là optional; v1 thiếu vẫn phải diễn giải được bởi decoder mới.
7. `amountMinor` có đơn vị rõ ngay trong tên; tránh field `amount` không định nghĩa currency/scale.
8. Những dữ liệu nhạy cảm, access token hoặc secret không nên nằm trong envelope.

Nếu dùng `major.minor`, có thể quy ước **major** cho thay đổi breaking, **minor** cho additive compatible. Tuy nhiên, điều này chỉ có ý nghĩa nếu serializer/decoder và registry thực sự biết version nào được chấp nhận. Ví dụ Java ở mục sau dùng `schemaVersion` là **số nguyên**, với v1 và v2 được xử lý có chủ đích; không ngầm áp dụng Semantic Versioning của thư viện vào wire format.

### Version đặt trong payload hay header?

| Vị trí | Điểm thuận lợi | Rủi ro |
| --- | --- | --- |
| Payload `schemaVersion` | Di chuyển cùng bytes khi lưu lại/replay | Consumer phải đọc envelope để biết codec |
| Broker header | Có thể chọn converter/handler trước khi parse payload | Header có thể không được copy qua bridge/retry/DLQ |
| Schema Registry ID | Quản lý Avro/Protobuf/JSON Schema tập trung | Cần registry/quy trình triển khai và cache/availability |
| Topic/queue theo version | Cách ly consumer incompatible | Tăng routing, migration và theo dõi backlog |

Có thể phối hợp hai nơi (ví dụ header `contentType` và payload `schemaVersion`), nhưng phải định nghĩa **nguồn sự thật** nếu hai giá trị mâu thuẫn. Nếu thông tin schema chỉ nằm ở header, cần xác minh mọi adapter/middleware giữ header khi redelivery, bridge sang topic khác và DLQ.

## 7. Ví dụ Java 17: decoder đọc V1 và V2 có kiểm soát

Đây là **ví dụ ứng dụng tự định nghĩa contract** cho một request remote chunking; **không phải JSON mặc định** của `ChunkRequest` hoặc `StepExecutionRequest` bên trong Spring Batch Integration.

Chúng ta dùng Jackson Databind phiên bản hỗ trợ Java record. Decoder v2 chấp nhận cả message v1, v2; version khác bị từ chối rõ ràng. `traceId` chỉ có ở v2.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class OrderChunkCodec {

    private static final int MAX_BYTES = 1024 * 1024; // Chỉ là ví dụ.
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    public record Item(long orderId, long amountMinor) {}

    public record RequestV1(
            String messageType,
            int schemaVersion,
            String snapshotId,
            String operationKey,
            List<Item> items) {}

    public record RequestV2(
            String messageType,
            int schemaVersion,
            String snapshotId,
            String operationKey,
            List<Item> items,
            String traceId) {}

    // Shape nội bộ ổn định của worker sau khi decode từng version.
    public record CanonicalRequest(
            String snapshotId,
            String operationKey,
            List<Item> items,
            String traceId) {}

    public static CanonicalRequest decode(byte[] bytes)
            throws JsonProcessingException {

        if (bytes == null || bytes.length == 0
                || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid message size");
        }

        JsonNode root = MAPPER.readTree(bytes);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Expected JSON object");
        }

        if (!"order-chunk-request".equals(
                root.path("messageType").asText(null))) {
            throw new IllegalArgumentException("Unsupported messageType");
        }

        int version = root.path("schemaVersion").asInt(-1);

        CanonicalRequest request = switch (version) {
            case 1 -> {
                RequestV1 v1 = MAPPER.treeToValue(
                        root, RequestV1.class);
                yield new CanonicalRequest(
                        v1.snapshotId(), v1.operationKey(),
                        v1.items(), null);
            }
            case 2 -> {
                RequestV2 v2 = MAPPER.treeToValue(
                        root, RequestV2.class);
                yield new CanonicalRequest(
                        v2.snapshotId(), v2.operationKey(),
                        v2.items(), v2.traceId());
            }
            default -> throw new IllegalArgumentException(
                    "Unsupported schemaVersion: " + version);
        };

        validate(request);
        return request;
    }

    private static void validate(CanonicalRequest request) {
        if (request.snapshotId() == null
                || request.snapshotId().isBlank()
                || request.operationKey() == null
                || request.operationKey().isBlank()
                || request.items() == null
                || request.items().isEmpty()) {
            throw new IllegalArgumentException(
                    "Required message fields missing");
        }

        Set<Long> seenOrderIds = new HashSet<>();
        for (Item item : request.items()) {
            if (item == null || item.orderId() <= 0
                    || item.amountMinor() < 0
                    || !seenOrderIds.add(item.orderId())) {
                throw new IllegalArgumentException("Invalid order item");
            }
        }
    }
}
~~~

### Đọc kỹ ý nghĩa của ví dụ

- `decode` là **boundary** giữa dữ liệu transport không tin cậy hoàn toàn và logic nghiệp vụ. Chỉ sau khi decode/validate mới đưa vào worker.
- V1 không có `traceId` được chuẩn hóa thành null. Không tự coi các required field khác là optional.
- Mọi version được liệt kê rõ. V3 chưa biết sẽ bị từ chối có chủ đích.
- `FAIL_ON_UNKNOWN_PROPERTIES=false` là **quyết định tương thích cho các field bổ sung** trong hai version đã nhận; vẫn cần kiểm tra field bắt buộc và giới hạn payload. Nó không được dùng để im lặng chấp nhận mọi version hoặc dữ liệu sai.
- Đoạn code giới hạn message ở 1 MiB để minh họa. Giới hạn thực tế phải dựa trên broker, payload p95/p99, bộ nhớ và SLA.
- Ví dụ coi `orderId` dương, `amountMinor` không âm; domain thật có thể cần trạng thái refund/signed amount, currency và phép kiểm tra bổ sung.
- Các record DTO là **wire schema có version**, không nên dùng thay thế trực tiếp business entity/JPA entity.

**Không sao chép bean Spring Batch vào chính codec này.** Trong hệ thống thật, adapter Spring Integration hoặc consumer gọi codec, chuyển sang `CanonicalRequest` rồi mới thực hiện service/worker logic.

### Tại sao V1 chưa chắc đọc được V2?

Worker v1 có thể chỉ chấp nhận `schemaVersion=1`. Worker v2 như ví dụ chấp nhận cả 1 và 2. Vì vậy muốn phát `schemaVersion=2`, cần nâng consumer trước. `FAIL_ON_UNKNOWN_PROPERTIES=false` của worker v2 **không quyết định** worker v1 có chấp nhận V2 hay không.

Nếu muốn tiếp tục dùng v1 wire cho đến khi rollout xong, producer v2 có thể **tạm phát V1** theo cờ cấu hình. Đừng dùng `dual-publish` tự phát hai bản của cùng operation lên hai queue mà không có định danh/dedup/owner rõ ràng: hai worker có thể cùng ghi một business effect.

## 8. Hợp đồng reply phải được version hóa độc lập

Nhiều nhóm chỉ version hóa request, rồi quên rằng manager cũng là một **consumer của reply**.

Ví dụ reply logic:

~~~json
{
  "messageType": "order-chunk-result",
  "schemaVersion": 1,
  "operationKey": "orders-2026-11-25:chunk-0042",
  "status": "SUCCESS",
  "processedCount": 1,
  "workerId": "worker-pod-07"
}
~~~

Một phiên bản mới có thể thêm `resultChecksum`, `retryAfterMs` hoặc trạng thái `PARTIAL`. Khi đó:

- Manager cũ có thể không hiểu `PARTIAL`. Không được mặc định unknown status = `SUCCESS`.
- `processedCount` phải chỉ rõ là số item đọc, item được ghi hay business effect duy nhất được commit.
- `operationKey` trong reply phải khớp request logic; không thay bằng publish attempt ID.
- Reply bị trễ có thể đến **sau** timeout hoặc khi manager đã xử lý lại K. Correlation và dedup phải chấp nhận reply duplicate/out-of-order theo contract.
- `schemaVersion` của reply có thể phát triển với nhịp khác request. Dùng **type + version** để quyết định decoder.

~~~mermaid
sequenceDiagram
    participant M as Manager v2
    participant Q as Middleware
    participant W as Worker v2
    participant DB as Business DB
    M->>Q: Request v1 (operationKey K)
    Q->>W: Deliver K
    W->>DB: Commit effect K
    W->>Q: Reply v1 / K / SUCCESS
    Note over Q,M: Reply chậm hoặc thất lạc
    Q-->>M: Reply K (có thể duplicate)
    M->>M: Dedup / correlate theo K và trạng thái step
~~~

Sơ đồ chỉ minh họa **contract tự định nghĩa**, không khẳng định Spring Batch sử dụng chính xác các trường JSON đó. Nếu dùng framework adapter có protocol riêng, phải giữ giao thức và message converter phù hợp release.

## 9. Tương tác với remote partitioning, remote chunking và JobRepository

### 9.1. Remote partitioning

Một worker remote thường được giao `StepExecution` chứa thông tin partition. Với các triển khai Spring Batch Integration quen thuộc, manager gửi request có định danh như `stepExecutionId` và worker truy cập `JobRepository` để lấy metadata.

Khi version hóa hệ thống này:

- Không tự sửa schema của `StepExecutionRequest` mà không bảo đảm adapter manager/worker đều hiểu.
- Kiểm tra version framework, serializer/converter của transport, header/correlation và khả năng worker đọc repository.
- Đảm bảo các key ứng dụng trong `StepExecutionContext` (`inputKey`, `startId`, `endExclusive`) không bị đổi type/ngữ nghĩa khi restart.
- Kiểm tra **`ExecutionContextSerializer` của metadata** độc lập với message converter.
- Nếu manager cũ còn request chờ trong broker, worker mới phải hiểu **request cũ** hoặc đợi queue cũ hoàn tất trước khi thay giao thức.

### 9.2. Remote chunking

Manager thường đọc và tạo chunk, worker xử lý và ghi. Do message mang item, sự thay đổi `OrderV1 → OrderV2` có thể tác động trực tiếp lên:

- Deserialization của chunk trong broker.
- Business validation và mapping.
- Đơn vị tiền, timezone, nullability, thứ tự và version nguồn.
- Batch writer và constraint ở DB đích.
- Reply protocol và checkpoint của manager.

**Manager đọc xong không có nghĩa chunk đã commit.** Một request có thể được giao lại khi worker ghi DB xong nhưng ack/reply thất lạc. Vì vậy contract mới phải giữ được business key và semantics idempotency, không chỉ giữ kiểu JSON.

### 9.3. Không trộn version của các loại state

| Version | Quản lý ở đâu | Có phải cùng version? |
| --- | --- | --- |
| Message wire schema | Request/reply adapter, registry hoặc payload | **Không** |
| `ExecutionContext` application state | `JobRepository`, worker metadata | **Không** |
| Business snapshot version | Manifest/JobParameters/source DB | **Không** |
| Service/app release | Artifact/container image | **Không** |
| DB schema migration | Flyway/Liquibase hoặc vận hành DB | **Không** |

Một ứng dụng release 2.3 có thể cần đọc message contract v1/v2, metadata checkpoint v1 và snapshot v7. Gắn mọi thứ thành “version 2” duy nhất sẽ làm triển khai cuốn chiếu và rollback khó hơn.

## 10. Chọn JSON Schema, Avro, Protobuf hay DTO tự quản lý?

Mỗi lựa chọn có trade-off, không có một định dạng đúng cho mọi job:

| Lựa chọn | Ưu điểm | Rủi ro / điều kiện |
| --- | --- | --- |
| JSON + DTO có decoder rõ | Dễ đọc/log, dễ thử bằng fixture | Phải tự quản lý required fields, enum, units và compatibility |
| JSON Schema | Có validation contract độc lập ứng dụng | Phải chuẩn hóa versioning/validator và kiểm thử consumer thực |
| Avro + Schema Registry | Schema evolution và compatibility checks có công cụ hỗ trợ | Cần registry/quy trình, producer/consumer dùng đúng subject và policy |
| Protobuf | Payload gọn, schema fields được định số, codegen | Không tái sử dụng field number, cần quản lý unknown/default semantics |
| Java native serialization | Dễ dùng object Java trong cùng hệ | Ràng buộc classpath, bảo mật/compatibility, ít phù hợp với message không tin cậy |
| DTO protocol riêng của Spring Batch Integration | Tích hợp sẵn với flow Batch | Không sửa trường/codec nội bộ tùy tiện; phụ thuộc version framework |

Schema Registry có thể chặn một số thay đổi phá compatibility theo luật cấu hình, nhưng **không thể tự phát hiện** bạn đã đổi `amountMinor` từ cent sang một đơn vị khác hoặc đổi ý nghĩa của `operationKey`. Vẫn cần contract test và review nghiệp vụ.

Với Protobuf, giữ nguyên **field number** và reserve number/name của field đã xóa để tránh tái sử dụng mang ý nghĩa khác. Với Avro, cần hiểu reader/writer schema, default và thứ tự evolution. Với JSON, cần chốt cách xử lý unknown/null/missing fields và kiểu số lớn.

Không chỉ dựa vào việc “schema check PASS” để tuyên bố an toàn trong distributed transaction/retry.

## 11. Kế hoạch rolling deployment an toàn

Một job batch đang chạy dài có thể có message tồn tại **trước, trong và sau** đợt deploy. Vì vậy phải thiết kế rollout theo các giai đoạn có kiểm chứng.

**Pha 0 — Inventory:** ghi nhận producer/consumer đang chạy, danh sách topic/queue, message types/versions còn trong backlog và reply channel. Kiểm tra `JobInstance` nào còn cần restart với metadata cũ.

**Pha 1 — Expand-read:** triển khai worker mới **đọc được cả v1 và v2**, nhưng manager **tiếp tục chỉ phát v1**. Kiểm tra worker mới xử lý backlog v1, xử lý error/retry và ghi dữ liệu đúng.

**Pha 2 — Kiểm tra năng lực:** khi mọi consumer có thể nhận message mới (bao gồm worker quay lại từ autoscaling, standby và môi trường rollback), phát canary v2 vào luồng có kiểm soát. Kiểm tra reply manager cũng hiểu phiên bản worker phát.

**Pha 3 — Switch-write:** bật producer phát v2. Theo dõi lỗi decode, tỷ lệ version, backlog, DLQ, throughput hữu ích và reconciliation. Có feature flag/rollback plan thực tế.

**Pha 4 — Contract-read:** chỉ ngừng hỗ trợ v1 khi **không còn message v1 đang đợi, in-flight, retry, DLQ cần replay, hoặc `JobInstance` phải phục hồi theo contract cũ**. Quy trình lưu trữ/retention và nghiệp vụ quyết định thời hạn này.

~~~mermaid
flowchart TD
    A["Đo backlog v1 và inventory"] --> B["Deploy consumers đọc v1 + v2"]
    B --> C["Giữ producer phát v1, test rollback"]
    C --> D["Canary phát v2"]
    D --> E{"Consumer/reply/DB đều ổn?"}
    E -->|"Có"| F["Switch-write v2, giám sát"]
    E -->|"Không"| G["Quay producer về v1, xử lý v2 đã phát"]
    F --> H["Drain v1 + retry/DLQ/restart còn tồn"]
    H --> I["Khi không còn phụ thuộc, bỏ support v1"]
~~~

### Bẫy rollback

Nếu manager đã phát nhiều message v2, **rollback tất cả worker về v1** có thể làm backlog v2 không consumer nào đọc được. Một kế hoạch rollback an toàn thường phải giữ ít nhất một nhóm worker đọc được v2 để drain/đối soát, hoặc có migration/replay đã kiểm thử. “Quay Docker image về bản cũ” chưa phải rollback hoàn chỉnh.

Tương tự, **dual-publish** một operation vào hai topic v1 và v2 không phải free upgrade: có nguy cơ xử lý song song hai lần. Nếu thật sự cần dual-run để so sánh, tách đường shadow không ghi effect hoặc dùng idempotency/correlation/owner rõ ràng.

## 12. Retry, redelivery và idempotency xuyên version

Messaging thường có tình huống **at-least-once delivery**: cùng request có thể được xử lý nhiều lần. Contract phải giữ khóa xác định hiệu ứng giống nhau qua retry, qua worker version và qua những bước chuyển đổi wire format.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant A as Worker v1
    participant B as Worker v2
    participant D as Business DB
    M->>Q: Request v1, operation K
    Q->>A: Deliver K
    A->>D: Commit order 421
    Note over A,M: ACK/reply mất
    Q->>B: Redeliver v1 / K
    B->>D: Thử ghi order 421
    D-->>B: PK/UPSERT/ledger ngăn side effect trùng
    B-->>M: Reply đã hoàn tất K
~~~

Để an toàn:

- **Business key** phải bền vững và có định nghĩa giống nhau giữa worker v1/v2.
- `operationKey` không được sinh UUID mới chỉ vì request được retry.
- Cơ sở dữ liệu nên có unique constraint/ledger/idempotency guard đủ cho nghiệp vụ.
- Cùng schemaVersion không bảo đảm transaction chung giữa broker và DB.
- Không đổi ý nghĩa phép cộng dồn, version, đơn vị tiền hoặc outbox event trong khi chỉ cập nhật schema.
- Reply cũ đến trễ vẫn phải được manager nhận diện theo correlation và trạng thái hiện tại.
- Khi business effect đã commit nhưng metadata/ack chưa được cập nhật, worker mới có thể xử lý lại; phải **đối soát** chứ không chỉ tin offset/queue depth.

Ví dụ PostgreSQL bảo vệ bản ghi theo business key và source version:

~~~sql
CREATE TABLE imported_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    amount_minor BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

~~~sql
INSERT INTO imported_order(
    snapshot_id, order_id, source_version, amount_minor
)
VALUES (:snapshotId, :orderId, :sourceVersion, :amountMinor)
ON CONFLICT (snapshot_id, order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    amount_minor = EXCLUDED.amount_minor
WHERE imported_order.source_version < EXCLUDED.source_version;
~~~

Điều kiện trên tránh replay phiên bản cũ ghi đè phiên bản mới. Nó **không tự xử lý** một khoản thanh toán API, trigger audit, email hoặc event outbox nếu mỗi lần gọi lại tạo side effect. Những hệ đó cần idempotency key riêng, transactional outbox/inbox hoặc phép bù theo contract.

**Lưu ý:** khi một chunk có nhiều item, `operationKey` cấp chunk giúp correlation/dedup request, nhưng writer vẫn nên chống duplicate **theo từng business item**, vì cách chia chunk có thể thay đổi trong một reprocess có chủ đích.

## 13. Backlog, retry topic, DLQ và message cũ

Không phải mọi message cũ đều nằm trong ready queue:

| Nơi có message | Tình huống khi nâng version | Hành động |
| --- | --- | --- |
| Request ready queue | Producer v1 tạo backlog chưa được giao | Worker mới phải đọc được v1 |
| Unacked / in-flight | Worker cũ đang xử lý, có thể redelivery | Không cắt bỏ worker cũ mà không hiểu ownership/ack |
| Retry/delayed queue | Message v1 chờ backoff nhiều giờ | Giữ decoder cũ cho đến khi xử lý xong |
| DLQ | Poison message cũ có thể cần replay sau nhiều ngày | Giữ fixture/codec và chính sách replay được kiểm thử |
| Reply channel | Reply v1 đến sau khi manager nâng version | Manager phải đọc reply cũ |
| Kafka retained log | Record v1 còn trong partition/log theo retention | Consumer mới phải hiểu record cần đọc theo offset |
| `JobRepository` | Checkpoint cũ tồn tại sau khi queue trống | Metadata codec và state migration là bài toán riêng |

Nếu consumer v2 chỉ đọc schema v2, một message v1 có thể bị coi là poison và retry vô hạn. Ngược lại, consumer có thể **đọc được v1 nhưng mapping sai**, âm thầm commit dữ liệu sai. Cả hai đều phải được kiểm tra bằng fixture.

### Phân loại lỗi ngay tại boundary

1. **Transport transient**: broker/network timeout; retry có backoff và giới hạn.
2. **Dependency transient**: DB deadlock, API 429; retry có quota/backoff, giữ business key.
3. **Schema unknown**: `schemaVersion=3` khi worker chỉ biết 1/2; fail rõ, chuyển tới compatibility/DLQ workflow, không retry nóng.
4. **Message malformed**: thiếu `snapshotId`, sai kiểu, payload quá lớn; reject/quarantine tùy policy.
5. **Business permanent**: source record vi phạm quy tắc; đưa vào kênh xử lý dữ liệu, không coi là lỗi serialization tạm thời.
6. **Reply/correlation mismatch**: worker có thể đã commit nhưng manager không ghép được reply; đối soát trước khi phát lại.

**DLQ không có nghĩa job đã thành công.** Nếu message trong DLQ là business item bắt buộc, step/job phải có cơ chế báo lỗi hoặc không cho bước publish cuối hoàn tất. Khi replay DLQ, đừng cấp `operationKey` mới để tránh guard chống trùng.

RabbitMQ có ready/unacked và dead-letter semantics theo queue/exchange; Kafka có consumer group offsets, partition lag và retry topic theo ứng dụng/framework. **Đừng dùng một metric backlog chung** mà bỏ qua sự khác nhau của middleware.

## 14. Bảo mật và validation của schema

Khi worker deserialize message, nó xử lý dữ liệu đến từ một trust boundary qua mạng hoặc broker. Dù producer là service nội bộ, payload vẫn có thể lỗi do cấu hình, bug, retry cũ hoặc kênh bị lạm dụng.

Một số nguyên tắc:

- Chỉ chấp nhận `messageType` và `schemaVersion` thuộc **allowlist** được triển khai rõ.
- Hạn chế kích thước bytes, số item/chunk, độ sâu JSON, độ dài String và giới hạn object graph.
- Không sử dụng Java native serialization với dữ liệu từ nguồn không tin cậy nếu không có kiểm soát phù hợp; tránh deserialization gadget/rủi ro thực thi mã.
- Không bật Jackson default typing không giới hạn để nhận bất kỳ tên class nào từ payload.
- Với Avro/Protobuf, kiểm tra schema ID/subject, loại message, compatibility policy và giới hạn kích thước.
- Dùng TLS, xác thực broker, ACL topic/queue, quyền tối thiểu để ngăn worker giả mạo kết quả.
- Không gửi access token, password, private key, `DataSource` hoặc object Spring runtime như một phần contract.
- Không để `inputKey`/URL từ message tùy ý làm worker đọc file ngoài phạm vi hoặc gọi nội bộ gây SSRF/path traversal.
- Log lỗi có thể in `schemaVersion`, `messageType`, hash/correlation và mã lỗi; không dump toàn bộ payload khách hàng.
- Kiểm soát bí mật và quyền truy cập của DLQ; message thất bại vẫn có thể chứa dữ liệu nhạy cảm.

**Không dùng unknown-field tolerance thay cho validation.** Ví dụ codec mục 7 bỏ qua trường mới trong *version đã hỗ trợ*, nhưng vẫn bắt buộc `snapshotId`, `operationKey` và items hợp lệ.

## 15. Monitoring: theo dõi contract chứ không chỉ CPU

Một lần đổi message contract có thể làm throughput nghiệp vụ giảm dù worker pod vẫn khỏe, vì consumer chuyển sang retry/DLQ hoặc manager không xử lý được reply.

| Số đo logic | Mục đích |
| --- | --- |
| `messages_consumed_total{type,version}` | Biết phiên bản thật còn được nhận |
| `messages_published_total{type,version}` | Kiểm tra producer đã bật write version mới chưa |
| `decode_failure_total{type,version,reason}` | Phát hiện lỗi schema/field/size |
| `unknown_schema_version_total` | Biết có producer phát version worker không hiểu |
| `retry_attempts_total` / `dlq_count` | Phát hiện poison message hoặc rollout sai |
| `request_ready` / `inflight` / `reply_backlog` | Xác định công việc đang kẹt ở đâu |
| `message_oldest_age_seconds` | Biết backlog cũ đã được drain chưa |
| `chunk_end_to_end_seconds` p95/p99 | Từ publish tới manager xác nhận |
| `business_items_committed_unique_per_second` | Throughput **hữu ích**, không đếm retry thành công mới |
| `step_execution_failed_by_contract_version` | Liên kết lỗi schema với trạng thái batch |
| `reconciliation_missing_or_duplicate` | Phát hiện mất/ghi trùng business key |

Tên metric là **gợi ý**, không phải metric có sẵn trong tất cả bản Spring Batch, RabbitMQ, Kafka hay Micrometer. Label nên dùng tập giá trị **nhỏ và có kiểm soát** (`type`, `major version`, `reason`), tránh label `messageId`/`orderId` vì cardinality lớn.

### SLO/alert gợi ý

- Chặn phát v2 khi chưa đạt tỷ lệ consumer sẵn sàng và test canary.
- Cảnh báo ngay khi `unknown_schema_version_total` tăng.
- Cảnh báo khi số lượng message v1 **không giảm** trong giai đoạn drain.
- Cảnh báo reply backlog tăng dù request backlog giảm.
- Đo số business item thực đã commit sau upsert/dedup, không lấy delivery attempts/s thay thông lượng.
- Dự báo drain-time của retry queue/DLQ so với deadline job; một message quan trọng còn kẹt vẫn có thể làm business window chưa hoàn tất.

## 16. Bộ kiểm thử contract và compatibility

Cần kiểm tra cả **wire format**, **semantics** và **khả năng phục hồi**.

| Nhóm test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| V1 → consumer v2 | Golden JSON v1 từ production-like fixture | Decode thành canonical request đúng dữ liệu |
| V2 → consumer v2 | JSON v2 hợp lệ có optional trace | Decode và bảo toàn required fields |
| V2 → consumer v1 | Worker cũ trong rolling deploy | Có hỗ trợ thực sự hoặc deployment phải ngăn đường này |
| Unknown v3 | Worker v2 chỉ hỗ trợ 1/2 | Reject có mã lỗi, không retry vô hạn |
| Unknown field | Request thêm trace/metadata | Xử lý theo policy, không làm mất required validation |
| Missing `snapshotId` | Message malformed | Fail, không đọc mọi shard |
| New enum status | Manager cũ | Không coi unknown = success |
| Unit change | `amountMinor` đổi ý nghĩa | Contract test phát hiện sai semantics |
| Big payload | Vượt max bytes/items | Reject trước khi tiêu tốn quá nhiều memory |
| Duplicate items | Cùng `orderId` trong một chunk | Phát hiện hoặc xử lý theo domain contract |
| Commit rồi mất reply | Worker v1/v2 nhận lại cùng business item | Không có side effect trùng |
| Broker backlog cũ | Message v1 còn trong retry/DLQ | Worker mới vẫn xử lý hoặc có migration |
| Metadata cũ | JobInstance cần restart | `ExecutionContext` đọc lại được riêng với wire codec |
| Rolling deploy | Manager/worker hai phiên bản | Matrix compatibility PASS theo thứ tự rollout |
| Rollback | Đã phát message v2 | Có worker đủ mới để drain v2 hoặc kế hoạch xử lý |
| End-to-end reconciliation | Nhiều version cùng xử lý snapshot | Đủ business keys, đúng payload/version |

### Java: một số test contract bằng JUnit 5

Giả sử `OrderChunkCodec` ở mục 7 nằm trong test classpath:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class OrderChunkCodecTest {

    private static byte[] utf8(String json) {
        return json.getBytes(StandardCharsets.UTF_8);
    }

    @Test
    void newConsumerReadsOldV1Message() throws Exception {
        String json = """
            {
              "messageType":"order-chunk-request",
              "schemaVersion":1,
              "snapshotId":"orders-2026-11-25",
              "operationKey":"run:chunk-42",
              "items":[{"orderId":421,"amountMinor":125000}]
            }
            """;

        var request = OrderChunkCodec.decode(utf8(json));

        assertEquals("orders-2026-11-25", request.snapshotId());
        assertEquals("run:chunk-42", request.operationKey());
        assertEquals(421L, request.items().get(0).orderId());
        assertNull(request.traceId());
    }

    @Test
    void readsV2WithOptionalTrace() throws Exception {
        String json = """
            {
              "messageType":"order-chunk-request",
              "schemaVersion":2,
              "snapshotId":"orders-2026-11-25",
              "operationKey":"run:chunk-42",
              "items":[{"orderId":421,"amountMinor":125000}],
              "traceId":"trace-abc"
            }
            """;

        assertEquals("trace-abc",
                OrderChunkCodec.decode(utf8(json)).traceId());
    }

    @Test
    void rejectsUnknownVersion() {
        String json = """
            {
              "messageType":"order-chunk-request",
              "schemaVersion":3,
              "snapshotId":"orders-2026-11-25",
              "operationKey":"run:chunk-42",
              "items":[{"orderId":421,"amountMinor":125000}]
            }
            """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderChunkCodec.decode(utf8(json)));
    }

    @Test
    void rejectsMissingOperationKey() {
        String json = """
            {
              "messageType":"order-chunk-request",
              "schemaVersion":1,
              "snapshotId":"orders-2026-11-25",
              "items":[{"orderId":421,"amountMinor":125000}]
            }
            """;

        assertThrows(IllegalArgumentException.class,
                () -> OrderChunkCodec.decode(utf8(json)));
    }
}
~~~

Bộ test trên kiểm tra **một codec ứng dụng minh họa**. Với môi trường thật, cần lưu **golden fixtures** từ các bản producer đang sử dụng (request và reply), kiểm tra các cặp version thực tế và xác minh adapter/broker cũng preserve header/correlation. Chỉ unit test JSON không chứng minh transaction/restart của Spring Batch đúng.

### Các kịch bản tích hợp bắt buộc

1. Tạo một `JobInstance` từ snapshot cố định; để một partition `COMPLETED` và một partition `FAILED` rồi restart.
2. Worker v1 commit business DB, mất ACK/reply; worker v2 nhận redelivery và writer vẫn idempotent.
3. Manager v2 đọc reply v1 tồn đọng; thử cả duplicate reply và reply trễ.
4. Giữ message v1 trong retry/DLQ rồi deploy v2, sau đó replay đúng business key.
5. Đổi codec `ExecutionContext` trên bản sao `JobRepository` để chứng minh metadata migration là bài toán độc lập.
6. Chạy tải đại diện với 1, 2, 4, 8 worker; đo broker lag, DB lock, pool pending, p95 latency và throughput hữu ích.
7. Dừng một worker khi nó còn work in-flight; xác minh owner/lease/fencing hoặc takeover theo protocol.
8. Đối soát nguồn–đích bằng business key/version và side effect ngoài DB trước khi kết luận job thành công.

## 17. Checklist phát hành contract mới

Trước khi bật producer phát schema mới, nhóm triển khai nên trả lời được:

- [ ] Message types, request/reply versions, required fields, semantics và units được ghi thành contract có version.
- [ ] Có **compatibility matrix** cho manager cũ/mới và worker cũ/mới.
- [ ] Consumer mới đọc được **golden fixtures cũ**, kể cả message còn trong retry/DLQ.
- [ ] Producer chỉ chuyển sang version mới khi mọi consumer liên quan có decoder phù hợp.
- [ ] Unknown schema/status bị reject rõ, không tự suy luận thành success.
- [ ] Correlation, `operationKey` và business key có semantics ổn định xuyên retry/version.
- [ ] JobRepository/`ExecutionContextSerializer` đã được kiểm tra **riêng** khỏi broker codec.
- [ ] Có chiến lược rollback **sau khi v2 đã được publish**, không chỉ rollback container image.
- [ ] Thử nghiệm commit rồi mất reply, redelivery, worker crash và restart cùng `JobInstance`.
- [ ] DLQ/replay có người sở hữu, metric, retention và kế hoạch xử lý payload cũ.
- [ ] Đã đo giới hạn byte message, chunk size, DB connection, broker backlog và SLA.
- [ ] Có đối soát output nghiệp vụ và quan sát lỗi schema theo version.
- [ ] Trường nhạy cảm không bị dump vào log/DLQ ngoài chính sách; deserialization bị giới hạn loại/size.

Nếu một trong các điều kiện bắt buộc chưa xác nhận, nên giữ producer ở contract cũ và tiếp tục mở rộng phía consumer/test. **Tốc độ rollout không được đánh đổi bằng việc làm mất khả năng restart.**

## 18. Bài tập tình huống

Một hệ thống Spring Batch remote chunking nhập **5 triệu đơn hàng trong 90 phút** qua RabbitMQ. Manager v1 gửi JSON:

~~~json
{
  "messageType": "order-chunk-request",
  "schemaVersion": 1,
  "snapshotId": "orders-2026-11-25",
  "operationKey": "orders-2026-11-25:chunk-0200",
  "items": [
    {"orderId": 20001, "amountMinor": 129900}
  ]
}
~~~

Nhóm chuẩn bị worker v2 với các thay đổi:

- Thêm `traceId` optional.
- Đổi tên `amountMinor` thành `amount` và bắt đầu coi giá trị là **đồng** thay vì **đơn vị nhỏ nhất**.
- Thêm reply status `PARTIAL`.
- Dự định đổi `operationKey` thành UUID mới mỗi lần retry.
- Khi triển khai, còn 10.000 request v1 trong request queue, một số request v1 đang retry; manager v1 vẫn tiêu thụ reply v1.
- `JobRepository` vẫn giữ metadata của những partition/step chưa hoàn tất.

**Câu hỏi:**

1. Thay đổi nào có thể additive compatible nếu decoder được chuẩn bị đúng? Thay đổi nào breaking về semantics?
2. Nếu chỉ deploy worker v2 mà không nâng manager, reply status `PARTIAL` có rủi ro gì?
3. Vì sao phải giữ khả năng xử lý request v1 trong cả ready, in-flight, retry và DLQ?
4. Đổi `operationKey` thành UUID mới trên mỗi retry có tác động gì tới idempotency?
5. Nếu worker v2 đã commit order 20001 nhưng reply mất, hành vi đúng khi message v1 được giao lại là gì?
6. Có nên sửa serializer của `ExecutionContext` chỉ vì JSON request đổi schema không?
7. Nếu producer đã phát request v2, cần kiểm tra gì trước khi rollback worker về v1?
8. Đề xuất thứ tự triển khai an toàn và ít rủi ro nhất.

### Gợi ý lời giải

- **(1)** `traceId` optional có thể tương thích khi old consumer chấp nhận unknown field và new consumer chấp nhận absent field. Đổi tên `amountMinor` và **đổi đơn vị** là breaking; phải tạo field mới có định nghĩa rõ hoặc một adapter chuyển đổi có kiểm thử.
- **(2)** Manager v1 có thể không hiểu `PARTIAL` và xử lý sai trạng thái; cần version reply/manager decoder trước hoặc giữ reply status cũ cho đến khi tương thích.
- **(3)** Backlog không chỉ nằm trong ready; message cũ có thể xuất hiện lại sau timeout hoặc nhiều ngày trong DLQ.
- **(4)** UUID mới phá khóa dedup logic; cùng tác dụng có thể bị thực hiện nhiều lần.
- **(5)** Dùng cùng business key để upsert/dedup hoặc ledger, xác minh kết quả rồi reply/correlate; không coi mất reply là chưa commit.
- **(6)** Không. Wire codec và metadata `ExecutionContextSerializer` là hai lớp độc lập.
- **(7)** Worker v1 có đọc được v2 và reply liên quan không? Nếu không, giữ nhóm worker đọc v2 để drain hoặc có migration/replay an toàn.
- **(8)** Giữ producer v1, deploy consumer đọc v1/v2, cập nhật manager reply decoder, chạy canary, chuyển producer sang v2, giám sát/reconcile, đợi hết v1 trong mọi kênh rồi mới bỏ support v1.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): remote partitioning, remote chunking và giới hạn mô hình.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): message channels, manager/worker adapters và request/reply.
- [Spring Batch Reference – ExecutionContext / JobRepository](https://docs.spring.io/spring-batch/reference/domain.html): state, `JobInstance`, `StepExecution` và checkpoint.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): cấu hình message conversion, routing và retry.
- [RabbitMQ Documentation – Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): ACK/confirm và các trường hợp redelivery.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): consumer offsets, partitions, record format và delivery semantics.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): schema resolution, default values và schema evolution.
- [Protocol Buffers – Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): quy tắc bổ sung/xóa field, field number và compatibility.
- [Jackson Databind Documentation](https://github.com/FasterXML/jackson-databind): mapping JSON sang DTO Java và kiểm soát cấu hình decoder.

## Ghi nhớ

**Version hóa message contract là giữ cho producer cũ/mới và consumer cũ/mới trao đổi đúng dữ liệu lẫn đúng ngữ nghĩa trong suốt vòng đời batch phân tán.** Cần version hóa request và reply, kiểm soát field required/optional, enum, đơn vị, correlation và business key; phân biệt wire schema với `ExecutionContext` metadata. Khi rollout, triển khai consumer đọc nhiều version **trước**, chuyển producer **sau**, và chỉ xóa decoder cũ khi backlog/retry/DLQ cùng yêu cầu restart cũ đã được giải quyết. Cuối cùng, schema tương thích không thay thế transaction, idempotency, backpressure và đối soát: **một message có thể được xử lý lại, nhưng hiệu ứng nghiệp vụ vẫn phải đúng**.
