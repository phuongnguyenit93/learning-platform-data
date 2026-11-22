# Định tuyến invalid message sang quarantine

## 1. Bài toán: message không hợp lệ phải đi đâu?

Một hệ thống nhận sự kiện đơn hàng qua message broker. Mỗi sự kiện phải có mã đơn, mã sự kiện, số tiền hợp lệ và loại tiền tệ được hỗ trợ. Nhưng trong thực tế producer có thể gửi dữ liệu thiếu trường, sai cấu trúc, phiên bản schema không tương thích hoặc vi phạm quy tắc nghiệp vụ.

~~~text
OrderSubmitted(
  eventId = "EVT-101",
  orderId = "ORD-101",
  amountVnd = -100000,
  currency = "VND"
)
~~~

Nếu cho message này đi thẳng tới Payment Handler, handler có thể tính toán sai hoặc gọi hệ thống bên ngoài với dữ liệu không hợp lệ. Nếu dùng **Message Filter** rồi để message bị loại **mất dấu**, đội vận hành không biết producer nào sai, bao nhiêu đơn bị ảnh hưởng, hoặc làm cách nào khôi phục sau khi sửa lỗi.

**Quarantine** là một đường xử lý riêng dành cho dữ liệu không đạt điều kiện đã định. Thay vì tiếp tục vào luồng nghiệp vụ chính, message được chuyển tới một nơi được kiểm soát để **lưu bằng chứng, ghi nguyên nhân, giám sát và quyết định sửa/replay/loại bỏ**.

~~~mermaid
flowchart LR
    P["Producer / Adapter"] --> V["Validate"]
    V --> F{"Message Filter"}
    F -->|Valid| B["Business Flow"]
    F -->|Invalid| Q["Quarantine Flow"]
    Q --> S[("Quarantine Store")]
    S --> O["Review / Fix / Authorized Replay"]
    O -->|New controlled attempt| V
~~~

Trong module `SPRING_INTEGRATION_PATTERN`, bài này thuộc chương **Message filter và validation**. Phạm vi module là triển khai Enterprise Integration Patterns bằng Spring Integration để tạo message flow ít phụ thuộc và dễ mở rộng; kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát các nhánh xử lý.

### Mục tiêu

Sau bài học, bạn sẽ có khả năng:

1. Phân biệt **invalid message** với **technical failure**, **retryable failure**, **business rejection** và **poison message**.
2. Thiết kế validation tạo **reason code có cấu trúc**, không chỉ một giá trị `true/false`.
3. Dùng Spring Integration Java DSL để gửi message hợp lệ sang business flow và message không hợp lệ sang quarantine bằng **Filter + discard channel**.
4. Giữ đủ metadata để điều tra mà không làm lộ dữ liệu nhạy cảm.
5. Chọn store, acknowledgment, deduplication, retention và recovery thích hợp cho quarantine.
6. Xây dựng quy trình **review → sửa nguyên nhân → revalidate → replay** có quyền, audit và giới hạn.
7. Viết JUnit test xác nhận invalid message **không đến business handler** và **không bị drop âm thầm**.

## 2. “Invalid” có nhiều nghĩa khác nhau

Không phải mọi message thất bại đều nên bị đưa vào cùng một hàng đợi lỗi với cùng một retry policy.

| Tình huống | Ví dụ | Phân loại | Hướng xử lý điển hình |
|---|---|---|---|
| **Malformed wire payload** | JSON bị cắt, bytes không decode được. | Parse/deserialization error. | Error flow hoặc adapter/DLQ có lưu raw reference an toàn. |
| **Schema invalid** | Thiếu `orderId` hoặc field sai kiểu. | Contract/schema violation. | Quarantine để xem producer/schema version. |
| **Business validation invalid** | `amountVnd <= 0`, currency không hỗ trợ. | Dữ liệu không đạt rule. | Quarantine hoặc final rejection theo contract. |
| **Unauthorized** | Tenant không có quyền gửi sự kiện. | Security/authorization rejection. | Chặn trước business flow, audit bảo mật, giới hạn thông tin trả về. |
| **Transient dependency failure** | Database không kết nối được. | Infrastructure failure. | Retry/backoff/circuit breaker; không gắn nhãn payload invalid. |
| **Business outcome từ chối** | Tồn kho không đủ dù request hợp lệ. | Business result. | Trả rejected outcome theo flow; không mặc định quarantine. |
| **Poison message** | Luôn khiến consumer lỗi mỗi lần đọc. | Có thể malformed, unsupported schema hoặc bug. | DLQ/quarantine sau phân loại; có điều tra. |
| **Duplicate hợp lệ** | Broker giao lại một event đã xử lý. | Idempotency/delivery. | Trả stored outcome hoặc acknowledge an toàn; không mặc định invalid. |

**Điểm quyết định:** Quarantine chứa message **có vấn đề cần xử lý riêng**, không phải giải pháp mặc định cho mọi `Exception`. Một timeout khi gọi database không làm `amountVnd` trong message bỗng trở thành sai.

### 2.1. Validation ở các ranh giới khác nhau

~~~text
Raw bytes
   |
   v
Decode / schema validation
   |
   v
Authentication & authorization
   |
   v
Typed message
   |
   v
Business validation
   |
   +-- valid ----> business processing
   |
   +-- invalid --> quarantine
~~~

Thứ tự cụ thể có thể khác theo adapter và trust boundary. Ví dụ đôi khi phải xác thực chữ ký trên **raw bytes trước khi parse**. Không dùng sơ đồ này để bỏ qua security checks đã được yêu cầu.

### 2.2. Filter không thể lọc một payload chưa được deserialize

Nếu một JSON có field `amountVnd` mang giá trị kiểu object không thể ánh xạ sang `BigDecimal`, inbound adapter có thể ném lỗi **trước khi** tạo được message `OrderSubmitted`. Khi đó Filter nhận typed payload **chưa hề chạy**.

Vì vậy phải thiết kế **đường error** ở nơi parse/adapter, tách khỏi discard path của business Filter:

~~~mermaid
flowchart TD
    R["Raw broker record"] --> D{"Decode được?"}
    D -->|Không| E["Adapter / deserialization error handling"]
    E --> Q1["Raw-error quarantine / DLQ"]
    D -->|Có| V{"Business validation"}
    V -->|Valid| B["Business handler"]
    V -->|Invalid| Q2["Typed-message quarantine"]
~~~

`errorChannel` của Spring Integration có thể nhận `ErrorMessage` trong những execution contexts được cấu hình, nhưng **không được giả định tất cả lỗi parse đều tự chảy vào global errorChannel**. Adapter/container deserializer có thể có error handler, recoverer hoặc DLQ riêng. Phải kiểm tra cách lỗi xuất hiện ở chính transport mà dự án sử dụng.

## 3. Khác biệt giữa Filter, Router, error channel và quarantine

| Thành phần | Trách nhiệm | Điều không tự làm |
|---|---|---|
| **Message Filter** | Cho message đi tiếp hoặc từ chối theo predicate. | Không tự lưu durable quarantine record. |
| **Discard Channel** | Nhận message bị Filter từ chối khi được cấu hình. | Không tự định nghĩa retention/replay/audit. |
| **Content-Based Router** | Chọn một/nhiều channel từ nội dung. | Không tự biết message “invalid”. |
| **Transformer** | Đổi payload/định dạng; có thể tạo Validation Outcome. | Không tự retry lỗi hay ghi store. |
| **Error Channel** | Đường xử lý một số lỗi kỹ thuật theo cấu hình. | Không thay thế validation outcome/rejection policy. |
| **Dead-Letter Queue (DLQ)** | Giữ record không xử lý được ở tầng transport/consumer. | Không nhất thiết chứa field violations theo business rule. |
| **Quarantine Flow** | Lưu, cách ly, theo dõi và điều phối xử lý message không hợp lệ. | Không tự bảo đảm payload hợp lệ sau khi replay. |

Một cách xây dựng dễ kiểm thử là:

~~~text
Typed Input
   -> Transformer (tính violations + policyVersion đúng một lần)
   -> Filter (valid? YES/NO)
        YES -> accepted business flow
        NO  -> discardChannel("orders.quarantine")
~~~

Không cần gọi Filter là một error handler: **false** là quyết định phân luồng bình thường. Còn lỗi của chính validator hoặc quarantine store có thể là exception kỹ thuật, cần xử lý theo failure policy.

### 3.1. Không dùng `throwExceptionOnRejection` vô tình

Với Spring Integration Filter, **discard path** và **throw exception khi bị reject** là những lựa chọn có hành vi khác nhau. Nếu bật `throwExceptionOnRejection(true)`, một message invalid có thể tạo exception thay vì đi vào discard flow như dự định.

Trong bài này, Filter **không throw chỉ vì business validation trả false**; ta cấu hình discard channel rõ ràng. Những lỗi bất ngờ như quarantine persistence failure vẫn phải được nhận diện và không nên bị nuốt.

### 3.2. Quarantine không nhất thiết là một broker topic

Nó có thể là:

- Một channel trỏ đến service ghi **database record**.
- Một durable queue/topic có consumer quản lý quarantine.
- Một object store cho raw payload + metadata database.
- Một workflow review có trạng thái, quyền, audit, hạn dùng và replay tooling.

**Tên `quarantine` trên channel không tạo durability.** `DirectChannel` chỉ thực hiện dispatch theo semantics của nó; nếu handler chỉ ghi vào một `List` trong memory, thông tin sẽ mất khi JVM restart. Phần Java bên dưới dùng fake store để học và kiểm thử, không coi đó là thiết kế production hoàn chỉnh.

## 4. Hợp đồng validation cần nhiều hơn một Boolean

### 4.1. Chỉ trả `false` sẽ làm mất nguyên nhân

Một predicate đơn giản:

~~~java
boolean valid(OrderSubmitted order) {
    return order.amountVnd() != null
            && order.amountVnd().signum() > 0
            && "VND".equals(order.currency());
}
~~~

Filter từ chối được message, nhưng quarantine operator không biết **đã sai field nào**, rule version nào và có thể sửa/replay hay không. Giải pháp là xây **Validation Outcome** có cấu trúc rồi dùng Filter trên outcome.

### 4.2. Violation có mã ổn định

Một outcome hữu ích:

~~~json
{
  "policyVersion": "orders-v1",
  "valid": false,
  "issues": [
    {"code": "AMOUNT_MUST_BE_POSITIVE", "field": "amountVnd"},
    {"code": "UNSUPPORTED_CURRENCY", "field": "currency"}
  ]
}
~~~

**Không nhúng thông tin nhạy cảm vào reason string**. Ví dụ thay vì in nguyên `customerEmail`, token hay nội dung thanh toán vào violation, dùng field path và mã lỗi để UI/quy trình điều tra áp dụng quyền đọc phù hợp.

### 4.3. Những field cần giữ kèm message invalid

| Field | Vì sao cần? | Lưu ý |
|---|---|---|
| `quarantineId` | Định danh record của kho quarantine. | Không thay business event ID. |
| `sourceSystem` | Biết producer nào cần sửa. | Nguồn phải được xác thực, không chỉ tin payload. |
| `tenantScope` | Giữ isolation giữa tenant. | Lấy từ trusted ingress/security context. |
| `eventId` hoặc `ingressEnvelopeId` | Dedupe redelivery cùng đầu vào. | Phải ổn định qua retry theo policy. |
| `validationPolicyVersion` | Biết vì sao phiên bản cũ từ chối. | Revalidation có thể thay outcome khi policy đổi. |
| `issues` | Danh sách rule/field bị vi phạm. | Tránh PII/raw secret trong reason text. |
| `receivedAt` | Tính tuổi group/quarantine. | Dùng clock đáng tin, timezone thống nhất. |
| `payloadReference`/checksum | Giữ bản gốc để điều tra/replay. | Kiểm soát mã hóa, retention và integrity. |
| `state` | NEW, UNDER_REVIEW, FIXED, REPLAYED, DISCARDED… | Dùng transitions và audit có thẩm quyền. |
| `attemptId`, `replayOf` | Truy dấu lần revalidate/replay. | Không trộn attempt với event/business operation. |
| `traceId`/`correlationId` | Liên kết log xuyên flow. | Không dùng làm dedupe key duy nhất. |

**Lưu original là một quyết định bảo mật.** Chỉ giữ đủ dữ liệu cho mục đích điều tra/replay, theo đúng quyền, retention và xử lý dữ liệu cá nhân. Với nhiều loại invalid message, có thể chỉ cần payload reference được bảo vệ thay vì copy nội dung vào log.

## 5. Xác định đầu vào đủ tin cậy trước khi lọc

Ta tách **business payload** khỏi **metadata do trusted ingress cấp**. Việc tách này đặc biệt cần thiết khi payload sai hoặc không có `eventId`.

~~~text
IngressEnvelope
  envelopeId         = EV-ING-202
  authenticatedTenant= TENANT-A
  trustedSource      = oms
  payload            = OrderSubmitted(...)
~~~

Trong demo, `envelopeId` là ID ổn định **được cấp/khôi phục bởi trusted adapter** cho cùng một logical input. Khi broker redeliver message đó, envelopeId phải **được giữ nguyên** nếu muốn dedupe quarantine theo ID này. Nếu một adapter tạo UUID mới mỗi lần giao, đây không còn là dedupe identity đáng tin; cần nguồn event ID hoặc durable ingress mapping khác.

### 5.1. Không lấy nguồn tin cậy từ payload invalid

Sai:

~~~text
Incoming JSON: {"tenantId": "TENANT-B", ...}
Quarantine tenant scope: đọc thẳng từ JSON đó
~~~

Nếu attacker/bug ghi sai tenantId, record có thể bị lưu sang tenant khác. Tenant scope nên được suy ra từ principal, broker authentication, configured route hoặc một nguồn tin cậy khác; nội dung payload chỉ dùng đối chiếu khi cần.

### 5.2. Điều gì xảy ra nếu chưa có eventId?

Không thể tạo idempotency key chỉ từ một field `eventId` đã bị thiếu. Có thể dùng **trusted envelope identity** hoặc transport record coordinate được truyền bền vững, nhưng phải biết semantics:

- Một broker offset có thể ổn định khi redelivery **chính record đó**.
- Nếu một sự kiện được republish thành record mới, offset có thể khác.
- Hash payload có thể trùng giữa hai sự kiện hợp lệ giống nội dung hoặc thay đổi do canonicalization.
- UUID tạo tại mỗi lần consumer nhận **không dedupe được redelivery**.

Vì vậy cần định nghĩa **idempotency scope của quarantine** theo nguồn dữ liệu, không phỏng đoán từ JSON sai.

## 6. Domain model Java: outcome bất biến và reason code

Ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Integration 6.x**. Các type được hiểu là nằm trong cùng package; khi dùng thực tế, tách `public` class/record ra file đúng quy tắc Java. Chúng phục vụ học tập, không thay thế security policy hay schema registry của dự án.

### 6.1. Order có thể sai rule, nhưng message vẫn phải có payload khác null

~~~java
import java.math.BigDecimal;

record OrderSubmitted(
        String eventId,
        String orderId,
        BigDecimal amountVnd,
        String currency,
        String customerEmail) {
    // Không validate ở constructor để có thể biểu diễn
    // dữ liệu business invalid sau khi decode được.
}
~~~

Spring `Message` không dùng `null` làm payload hợp lệ, nhưng ta có thể biểu diễn **order object thiếu** bên trong một trusted envelope. Những trường có thể null ở `OrderSubmitted` là dữ liệu để validator quyết định, không phải lời khuyên cho domain entity đã được xác nhận.

### 6.2. Envelope có nguồn đáng tin

~~~java
record IngressOrder(
        String envelopeId,
        String authenticatedTenant,
        String trustedSource,
        OrderSubmitted order) {

    IngressOrder {
        if (envelopeId == null || envelopeId.isBlank()
                || authenticatedTenant == null
                || authenticatedTenant.isBlank()
                || trustedSource == null || trustedSource.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_TRUSTED_INGRESS_METADATA");
        }
    }
}
~~~

Trong demo, ta **giả định adapter đã xác thực** `authenticatedTenant` và `trustedSource`. Việc record Java nhận được một String không làm String ấy trở thành trusted. Production phải bind nguồn từ security principal/adapter configuration và kiểm tra cross-tenant access trước khi lưu hoặc replay.

### 6.3. Kết quả validation

~~~java
import java.util.List;
import java.util.Objects;

record ValidationIssue(String code, String field) {
    ValidationIssue {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_VALIDATION_REASON");
        }
    }
}

record ValidationOutcome(
        IngressOrder ingress,
        List<ValidationIssue> issues,
        String policyVersion) {

    ValidationOutcome {
        Objects.requireNonNull(ingress, "ingress");
        issues = List.copyOf(issues);
        if (policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_POLICY_VERSION");
        }
    }

    boolean valid() {
        return issues.isEmpty();
    }
}
~~~

Một `ValidationOutcome` giữ **original typed envelope** cùng danh sách issues. Khi Filter từ chối, discard channel nhận được **chính outcome** để lưu nguyên nhân. Nếu Filter chỉ nhận boolean và downstream lại tính lại validation, hai lần có thể khác khi policy thay đổi hoặc validator có lời gọi phụ thuộc trạng thái bên ngoài.

### 6.4. Validation policy xác định, dễ test

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

final class OrderValidationPolicy {
    static final String VERSION = "orders-v1";
    private static final Set<String> TRUSTED_SOURCES =
            Set.of("oms", "portal");
    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000000");

    ValidationOutcome validate(IngressOrder ingress) {
        List<ValidationIssue> issues = new ArrayList<>();

        // Source allowlist là policy dữ liệu minh họa,
        // KHÔNG thay Authentication của adapter.
        if (!TRUSTED_SOURCES.contains(ingress.trustedSource())) {
            issues.add(new ValidationIssue(
                    "UNSUPPORTED_SOURCE", "trustedSource"));
        }

        OrderSubmitted order = ingress.order();
        if (order == null) {
            issues.add(new ValidationIssue(
                    "ORDER_PAYLOAD_MISSING", "order"));
            return new ValidationOutcome(
                    ingress, issues, VERSION);
        }

        if (missing(order.eventId())) {
            issues.add(new ValidationIssue(
                    "EVENT_ID_REQUIRED", "eventId"));
        }
        if (missing(order.orderId())) {
            issues.add(new ValidationIssue(
                    "ORDER_ID_REQUIRED", "orderId"));
        }
        if (order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            issues.add(new ValidationIssue(
                    "AMOUNT_MUST_BE_POSITIVE", "amountVnd"));
        } else if (order.amountVnd().compareTo(MAX_AMOUNT) > 0) {
            issues.add(new ValidationIssue(
                    "AMOUNT_EXCEEDS_LIMIT", "amountVnd"));
        }
        if (!"VND".equals(order.currency())) {
            issues.add(new ValidationIssue(
                    "UNSUPPORTED_CURRENCY", "currency"));
        }

        return new ValidationOutcome(ingress, issues, VERSION);
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }
}
~~~

Các ngưỡng và allowlist trong demo chỉ nhằm minh họa. Không áp `MAX_AMOUNT=1_000_000_000` cho hệ thống thật khi chưa có business policy. Ở đây `customerEmail` không tham gia validation; nếu nghiệp vụ yêu cầu, thêm rule có version, nhưng **không ghi địa chỉ email thô vào violation code hoặc log**.

### 6.5. Ví dụ đầu vào tạo nhiều issues

~~~java
IngressOrder input = new IngressOrder(
        "ING-1001",
        "TENANT-A",
        "oms",
        new OrderSubmitted(
                "EVT-1001",
                "",
                new BigDecimal("-100000"),
                "USD",
                "sensitive@example.com"));

ValidationOutcome outcome =
        new OrderValidationPolicy().validate(input);

// outcome.valid() == false
// issues: ORDER_ID_REQUIRED,
//         AMOUNT_MUST_BE_POSITIVE,
//         UNSUPPORTED_CURRENCY
~~~

**Tại sao cần nhiều issues?** Một operator có thể sửa các field sai trong một lần thay vì sửa một trường rồi replay, phát hiện tiếp một lỗi khác. Tuy vậy, khi dữ liệu rất nhạy cảm hoặc có nguy cơ tấn công, có thể giới hạn số issues và thông tin trình bày theo quyền.

## 7. Lưu quarantine như một trạng thái điều phối, không chỉ một log

### 7.1. Record tối thiểu

~~~text
quarantineId:        Q-abc
ingressEnvelopeId:   ING-1001
tenant:              TENANT-A
source:              oms
policyVersion:       orders-v1
reasonCodes:         [ORDER_ID_REQUIRED, AMOUNT_MUST_BE_POSITIVE]
status:              NEW
firstSeenAt:         ...
payloadReference:    protected-ref
replayAttempt:       0
~~~

Một **quarantine record** có identity/metadata riêng. Không dùng `MessageHeaders.ID` làm record key duy nhất vì một message có thể được rebuild khi adapter redeliver; cũng không coi `quarantineId` là idempotency key cho thanh toán downstream.

### 7.2. Trạng thái của quarantine case

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> UNDER_REVIEW: take case
    UNDER_REVIEW --> FIX_APPROVED: authorized correction
    UNDER_REVIEW --> DISCARDED: approved permanent discard
    FIX_APPROVED --> REPLAY_REQUESTED: create controlled attempt
    REPLAY_REQUESTED --> REVALIDATING: send to validation ingress
    REVALIDATING --> REPLAYED: validation + business handoff accepted
    REVALIDATING --> UNDER_REVIEW: still invalid
    NEW --> EXPIRED: retention policy
    REPLAYED --> [*]
    DISCARDED --> [*]
    EXPIRED --> [*]
~~~

Đây là một state machine **do ứng dụng đề xuất**, không phải tính năng tự sinh của Spring Integration. “REPLAYED” nên được định nghĩa thật rõ: có thể chỉ là message đã được phát lại, **không có nghĩa business side effect đã commit**. Nếu cần chứng minh hoàn tất, thêm business outcome/receipt riêng.

### 7.3. Quarantine khác Dead Letter Queue

| Tiêu chí | Quarantine nghiệp vụ | DLQ transport |
|---|---|---|
| Nguồn vào | Validation false, rejected schema/rule. | Consumer/adapter xử lý thất bại theo retry policy. |
| Dữ liệu chính | Reason code, policy version, typed/raw reference. | Record, headers, exception/attempt metadata. |
| Người xử lý | Data steward, producer owner, workflow operator. | Messaging/platform operator và ứng dụng. |
| Replay | Revalidate sau sửa/ủy quyền. | Redrive theo broker/app policy; vẫn cần revalidate. |
| TTL/retention | Theo dữ liệu, tính riêng tư và quy trình review. | Theo broker/platform retention. |

Một DLQ có thể đóng vai trò hạ tầng **chứa quarantine** nếu có đủ metadata, bảo mật và workflow. Ngược lại, có thể lưu quarantine trong DB và chỉ sử dụng DLQ cho lỗi transport. Không chọn hai tên này như thể chúng có semantics cố định ở mọi hệ thống.

### 7.4. Vì sao không gửi toàn bộ payload vào log?

Quarantine phải phục vụ điều tra nhưng không nên trở thành kho rò rỉ thông tin:

- **Log:** key đã che, mã lý do, route, source, policy version, trace; tránh PII/raw credentials.
- **Protected storage:** payload gốc hoặc reference tới bản gốc, có mã hóa, quyền, retention và integrity.
- **Review UI:** chỉ hiển thị field cần thiết theo quyền; không mặc định cho mọi operator xem tất cả.
- **Replay:** dùng nguồn dữ liệu gốc/phiên bản đã sửa được xác thực, không copy nguyên error text thành payload.

Khi schema rất lớn, có thể giữ object reference và checksum thay vì copy nhiều lần. Nhưng reference đó cũng cần được bảo vệ như một capability trỏ đến dữ liệu nhạy cảm.

## 8. Quarantine repository minh họa: idempotency khi redelivery

Nếu broker giao lại cùng message invalid, không nên tạo vô hạn bản ghi quarantine mới. Ta cần một **khóa ổn định** và chính sách xử lý khi cùng khóa mang nội dung khác.

### 8.1. Khóa theo nguồn và envelope identity

~~~java
record QuarantineKey(
        String tenant,
        String source,
        String envelopeId) {}
~~~

Trong code demo, `envelopeId` do trusted ingress cấp và giữ nguyên khi cùng message được giao lại. Key không gồm deliveryAttempt vì mỗi retry phải thuộc **cùng một quarantine case**.

Nếu cố tình revalidate dưới policy mới hoặc sửa payload được phê duyệt, nên tạo **attempt/revision mới có lineage rõ**; không âm thầm ghi đè record cũ cùng key. Trạng thái/payload của bản gốc cần còn để audit theo retention.

### 8.2. Case record không mất original typed data

~~~java
import java.time.Instant;

record QuarantineCase(
        String quarantineId,
        QuarantineKey key,
        ValidationOutcome originalOutcome,
        String state,
        Instant createdAt) {}
~~~

Trong production, `originalOutcome` có thể được thay bằng **protected payload reference** và structured violations đã được sanitize; việc demo giữ original object trong memory không phải phương án bảo mật hoặc durability cho dữ liệu nhạy cảm.

### 8.3. In-memory store cho unit/integration test

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class InMemoryQuarantineStore {
    private final ConcurrentMap<QuarantineKey, QuarantineCase> cases =
            new ConcurrentHashMap<>();
    private final Clock clock;

    InMemoryQuarantineStore(Clock clock) {
        this.clock = clock;
    }

    QuarantineCase store(ValidationOutcome outcome) {
        if (outcome.valid()) {
            throw new IllegalArgumentException(
                    "VALID_MESSAGE_CANNOT_BE_QUARANTINED");
        }
        IngressOrder ingress = outcome.ingress();
        QuarantineKey key = new QuarantineKey(
                ingress.authenticatedTenant(),
                ingress.trustedSource(),
                ingress.envelopeId());

        return cases.compute(key, (ignored, existing) -> {
            if (existing != null) {
                if (!existing.originalOutcome().equals(outcome)) {
                    throw new IllegalStateException(
                            "QUARANTINE_IDENTITY_CONFLICT");
                }
                return existing; // Redelivery giống hệt case cũ.
            }
            return new QuarantineCase(
                    UUID.randomUUID().toString(),
                    key,
                    outcome,
                    "NEW",
                    Instant.now(clock));
        });
    }

    int count() {
        return cases.size();
    }

    List<QuarantineCase> snapshot() {
        return List.copyOf(cases.values());
    }
}
~~~

**Tại sao so `originalOutcome`?** Một producer có bug có thể tái sử dụng envelopeId cho **hai payload khác nhau**. Nếu cứ `putIfAbsent` rồi trả case cũ, record thứ hai sẽ biến mất không dấu vết. Demo ném `QUARANTINE_IDENTITY_CONFLICT` để phát hiện rủi ro. Production có thể ghi case conflict riêng và quarantine cả hai, không chỉ throw; cần bảo vệ quyền và lưu đủ chứng cứ.

**Giới hạn của fake:** `ConcurrentHashMap.compute` có tính nguyên tử theo key trong một JVM, nhưng không hỗ trợ durable storage, DB transaction, concurrency giữa pods, encryption, status workflow, cleanup hoặc replay. Production nên dùng unique constraint/CAS và transactional inbox/outbox theo ranh giới transport thật.

### 8.4. Tại sao không xóa invalid ngay sau khi lưu log?

Nếu inbound record đã bị ack sau khi một dòng log xuất hiện, log bị xoay/xóa hoặc mất khi node chết thì dữ liệu điều tra có thể biến mất. Với yêu cầu không mất sự kiện, nên ack **sau khi** quarantine store hoặc durable queue xác nhận theo policy đã chọn.

Nếu quarantine store lỗi, đừng catch exception rồi trả `send=true` như thể đã lưu thành công. Cần đường retry/backpressure/transport redelivery có giới hạn và khả năng điều tra failure.

## 9. Spring Integration Java DSL: Filter với discard channel

### 9.1. Các thành phần trong demo

~~~text
orders.validation.input
  -> OrderValidationPolicy.validate(...)
  -> ValidationOutcome
  -> Message Filter [outcome.valid()]
       true  -> orders.valid      -> AcceptedOrderProbe
       false -> orders.quarantine -> InMemoryQuarantineStore
~~~

Nhờ Transformer tạo `ValidationOutcome` **một lần**, quarantine nhận đủ violations. Predicate của Filter chỉ nhìn `outcome.valid()` và không cần gọi lại validation rule.

### 9.2. Probe ở nhánh hợp lệ

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class AcceptedOrderProbe {
    private final List<IngressOrder> accepted =
            new CopyOnWriteArrayList<>();

    void record(IngressOrder envelope) {
        accepted.add(envelope);
    }

    List<IngressOrder> snapshot() {
        return List.copyOf(accepted);
    }
}
~~~

Probe chỉ để test. Nó **không phải payment/order business handler production** và không có transaction. Khi thay bằng handler thật, áp dụng idempotency theo event/operation, retry và acknowledgment phù hợp.

### 9.3. Cấu hình flow đầy đủ

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class QuarantineRoutingConfiguration {

    @Bean(name = "orders.validation.input")
    MessageChannel validationInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.valid")
    MessageChannel validOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.quarantine")
    MessageChannel quarantineOrders() {
        return new DirectChannel();
    }

    @Bean
    OrderValidationPolicy orderValidationPolicy() {
        return new OrderValidationPolicy();
    }

    @Bean
    AcceptedOrderProbe acceptedOrderProbe() {
        return new AcceptedOrderProbe();
    }

    @Bean
    InMemoryQuarantineStore quarantineStore() {
        return new InMemoryQuarantineStore(Clock.systemUTC());
    }

    @Bean
    IntegrationFlow validateAndRouteOrders(
            OrderValidationPolicy validator) {
        return IntegrationFlow.from("orders.validation.input")
                .transform(IngressOrder.class, validator::validate)
                .filter(
                        ValidationOutcome.class,
                        ValidationOutcome::valid,
                        spec -> spec.discardChannel(
                                "orders.quarantine"))
                .channel("orders.valid")
                .get();
    }

    @Bean
    IntegrationFlow processValidOrders(AcceptedOrderProbe probe) {
        return IntegrationFlow.from("orders.valid")
                .handle(ValidationOutcome.class,
                        (outcome, headers) -> {
                            probe.record(outcome.ingress());
                            return null; // Terminal demo handler.
                        })
                .get();
    }

    @Bean
    IntegrationFlow captureInvalidOrders(
            InMemoryQuarantineStore store) {
        return IntegrationFlow.from("orders.quarantine")
                .handle(ValidationOutcome.class,
                        (outcome, headers) -> {
                            store.store(outcome);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

### 9.4. Cách hiểu chính xác DSL

1. `IntegrationFlow.from("orders.validation.input")` nhận `IngressOrder` đã qua trusted adapter.
2. `transform(IngressOrder.class, validator::validate)` tạo `ValidationOutcome` có payload gốc và danh sách issues.
3. `filter(ValidationOutcome.class, ValidationOutcome::valid, ...)` đánh giá đúng **outcome đã tính**.
4. Nếu valid, Filter cho message đi tới `orders.valid`.
5. Nếu invalid, `discardChannel("orders.quarantine")` chuyển message bị từ chối sang channel quarantine.
6. `captureInvalidOrders` ghi một case vào fake store, không gọi business handler.
7. Các channel `DirectChannel` giúp demo có dispatch đồng bộ và test đơn giản; không có độ bền qua restart.

Đối với Spring Integration 6.x, ví dụ dùng các overload phổ biến của Java DSL. Khi tích hợp vào phiên bản cụ thể, cần kiểm tra chữ ký overload, `FilterEndpointSpec` và behavior của adapter/channel đang sử dụng, nhất là discard, error handling và transaction. **Chưa có bằng chứng build/test cho dự án tại STEP 4 này.**

### 9.5. Vì sao không dùng `filter(order -> valid(order))` rồi bỏ qua discard?

Nếu chỉ:

~~~java
// Anti-pattern nếu ứng dụng bắt buộc phải lưu invalid.
.filter(IngressOrder.class, order ->
        validator.validate(order).valid())
~~~

thì predicate false có thể làm message bị loại khỏi business flow mà **không đi vào kho quarantine** nếu không cấu hình discard. Ngoài ra, chỉ còn boolean, không mang reason codes. Trong luồng yêu cầu audit/replay, cần một discard route có handler lưu bền và quan sát được.

### 9.6. Discard không phải exception mặc định

Một invalid order là **dữ liệu có lỗi đã được phân loại**, không nhất thiết là failure của Java handler. Không cần ném exception để tạo quarantine record. Exception có thể phù hợp với contract validation khác, nhưng sẽ đi vào error flow **tùy execution model**, không tự tạo các trường như policyVersion/issues.

### 9.7. Nếu discard/quarantine handler ném exception?

Với `DirectChannel` trong demo, exception từ `store.store(outcome)` có thể lan về caller của `send(...)`. Trong một broker consumer/poller, lỗi có thể được chuyển đến error handler theo adapter config. Dù ở đâu, không được coi message đã được quarantine bền vững nếu write thất bại.

Nếu muốn cách ly latency, có thể đặt durable queue trước quarantine writer. Nhưng **enqueue thành công khác persist case thành công**: cần định nghĩa mốc acknowledgment, retry/DLQ và monitoring của từng tầng.

## 10. Unit test validator trước khi kết nối framework

### 10.1. Một order hợp lệ không có violation

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderValidationPolicyHappyPathTest {
    private final OrderValidationPolicy validator =
            new OrderValidationPolicy();

    @Test
    void acceptedOrderHasNoIssues() {
        IngressOrder incoming = new IngressOrder(
                "ING-1",
                "TENANT-A",
                "oms",
                new OrderSubmitted(
                        "EVT-1",
                        "ORD-1",
                        new BigDecimal("100000"),
                        "VND",
                        "private@example.com"));

        ValidationOutcome result = validator.validate(incoming);

        assertTrue(result.valid());
        assertTrue(result.issues().isEmpty());
    }
}
~~~

Unit test này chỉ chứng minh rule của Java validator, **không** chứng minh Spring Filter đã route đúng hay quarantine record đã lưu.

### 10.2. Một input có thể có nhiều reason codes

~~~java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class OrderValidationPolicyInvalidTest {
    private final OrderValidationPolicy validator =
            new OrderValidationPolicy();

    @Test
    void returnsAllKnownViolations() {
        IngressOrder incoming = new IngressOrder(
                "ING-2", "TENANT-A", "oms",
                new OrderSubmitted(
                        "", "", new BigDecimal("-500"),
                        "USD", "private@example.com"));

        ValidationOutcome result = validator.validate(incoming);

        assertFalse(result.valid());
        Set<String> reasonCodes = result.issues().stream()
                .map(ValidationIssue::code)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                "EVENT_ID_REQUIRED",
                "ORDER_ID_REQUIRED",
                "AMOUNT_MUST_BE_POSITIVE",
                "UNSUPPORTED_CURRENCY"), reasonCodes);
        assertEquals("orders-v1", result.policyVersion());
    }
}
~~~

### 10.3. Missing business payload nhưng trusted envelope vẫn tồn tại

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class OrderMissingPayloadTest {
    @Test
    void missingOrderInEnvelopeHasStructuredReason() {
        IngressOrder incoming = new IngressOrder(
                "ING-3", "TENANT-A", "oms", null);

        ValidationOutcome result =
                new OrderValidationPolicy().validate(incoming);

        assertFalse(result.valid());
        assertEquals("ORDER_PAYLOAD_MISSING",
                result.issues().get(0).code());
    }
}
~~~

Đây là một object Java có envelope chứa trường `order=null`. Với **raw JSON hoàn toàn không decode được**, không thể tạo typed `IngressOrder` để chạy test này; phải kiểm thử error handler ở inbound adapter.

## 11. Integration test: message invalid được cách ly thật

### 11.1. Test qua Filter và hai handler

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineRoutingIntegrationTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe accepted;

    @Autowired
    InMemoryQuarantineStore quarantine;

    private void send(IngressOrder envelope) {
        assertTrue(input.send(
                MessageBuilder.withPayload(envelope).build(),
                1_000));
    }

    @Test
    void validOrderGoesToBusinessButNotQuarantine() {
        send(new IngressOrder(
                "ING-11", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-11", "ORD-11",
                        new BigDecimal("200000"),
                        "VND", "private@example.com")));

        assertEquals(1, accepted.snapshot().size());
        assertEquals(0, quarantine.count());
    }

    @Test
    void invalidOrderGoesToQuarantineNotBusiness() {
        send(new IngressOrder(
                "ING-12", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-12", "ORD-12",
                        new BigDecimal("-1000"),
                        "VND", "private@example.com")));

        assertEquals(0, accepted.snapshot().size());
        assertEquals(1, quarantine.count());

        QuarantineCase stored = quarantine.snapshot().get(0);
        assertEquals("ING-12", stored.key().envelopeId());
        assertEquals("orders-v1",
                stored.originalOutcome().policyVersion());
        assertEquals("AMOUNT_MUST_BE_POSITIVE",
                stored.originalOutcome()
                        .issues().get(0).code());
    }
}
~~~

**Điều test chứng minh:** Filter từ chối đúng message, discard channel có handler, handler quarantine nhận outcome kèm reason code, còn accepted probe không được gọi.

**Điều test chưa chứng minh:** store bền vững qua restart, broker ack, adapter header mapping, encryption, retention, replay hoặc tenant authorization. Fake store chỉ ở memory.

### 11.2. Redelivery cùng invalid envelope không tạo hai cases

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineDuplicateIntegrationTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    InMemoryQuarantineStore quarantine;

    @Autowired
    AcceptedOrderProbe accepted;

    @Test
    void duplicateInvalidEnvelopeKeepsOneCase() {
        IngressOrder same = new IngressOrder(
                "ING-20", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-20", "ORD-20",
                        BigDecimal.ZERO,
                        "VND", null));

        assertTrue(input.send(
                MessageBuilder.withPayload(same).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(same).build()));

        assertEquals(1, quarantine.count());
        assertEquals(0, accepted.snapshot().size());
    }
}
~~~

Lưu ý: test gửi hai **Spring Messages khác nhau** cùng một trusted envelope ID. Nó mô phỏng duplicate/redelivery cùng đầu vào; **không** mặc định mọi broker giữ nguyên `MessageHeaders.ID` khi giao lại.

### 11.3. Same envelope ID với nội dung khác phải bị phát hiện

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineIdentityConflictTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    InMemoryQuarantineStore quarantine;

    @Test
    void sameEnvelopeIdWithDifferentPayloadIsNotSilentDuplicate() {
        IngressOrder first = new IngressOrder(
                "ING-30", "TENANT-A", "oms",
                new OrderSubmitted("EVT-30", "ORD-30",
                        new BigDecimal("-1"), "VND", null));

        IngressOrder conflicting = new IngressOrder(
                "ING-30", "TENANT-A", "oms",
                new OrderSubmitted("EVT-30", "ORD-30",
                        new BigDecimal("-2"), "VND", null));

        assertTrue(input.send(
                MessageBuilder.withPayload(first).build()));

        // Spring có thể bọc lỗi store trong messaging exception;
        // test kiểm tra có lỗi, không phụ thuộc wrapper text.
        assertThrows(RuntimeException.class, () ->
                input.send(
                        MessageBuilder.withPayload(conflicting).build()));

        assertEquals(1, quarantine.count());
    }
}
~~~

Trong production, phải **lưu được bằng chứng của bản conflict** để điều tra, không chỉ throw và retry vô hạn. Có thể tạo conflict case riêng bằng một khóa khác, gửi qua secure error route, hoặc dùng bảng history/version với unique constraint. Code demo chọn **fail closed** để tránh âm thầm ghi đè.

### 11.4. Tại sao test cần `@DirtiesContext`?

`AcceptedOrderProbe` và `InMemoryQuarantineStore` giữ state giữa các message trong Spring context. Mỗi integration test nên có context riêng hoặc reset store/probe có chủ đích. Nếu không, một test có thể thấy case từ test trước và báo kết quả sai.

### 11.5. Nếu muốn kiểm thử async

Với `ExecutorChannel`, broker hoặc poller:

- Không assert ngay sau `send` rằng quarantine store đã ghi bền vững.
- Dùng `CountDownLatch`, `BlockingQueue.poll(timeout)` hoặc cơ chế await có deadline.
- Xác minh **mốc**: accepted, persisted, acked, reviewed, replayed là những trạng thái khác nhau.
- Test queue full, dispatcher không có subscriber, worker throw và retry behavior.
- Dọn executor và giải phóng latch trong `finally`, tránh test treo do `Thread.sleep` không ổn định.

## 12. Malformed JSON: lỗi có thể xảy ra trước Filter

### 12.1. Khi deserializer không tạo được `IngressOrder`

Ví dụ producer gửi:

~~~json
{
  "eventId": "EVT-40",
  "orderId": "ORD-40",
  "amountVnd": {"unexpected": "object"},
  "currency": "VND"
}
~~~

Nếu inbound adapter cố deserialize `amountVnd` thành `BigDecimal` và thất bại, **typed Filter sẽ không nhìn thấy `OrderSubmitted`**. Việc cấu hình `discardChannel("orders.quarantine")` ở Filter **không tự bắt lỗi deserialization**.

Các lựa chọn tùy adapter:

1. Bắt lỗi ở **deserializer/error handler** của inbound consumer.
2. Đưa raw record reference, transport coordinates, schema version, error code đã sanitize sang **raw-error quarantine** hoặc DLQ.
3. Quy định ack/retry để không mất record trước khi error record được ghi bền vững.
4. Có policy giới hạn kích thước raw payload và dữ liệu nhạy cảm.
5. Nếu sửa được schema/producer, replay từ nguồn có thẩm quyền qua chính validation ingress.

### 12.2. Đừng tự suy rằng mọi exception đều đi vào `errorChannel`

Spring Integration có cơ chế `ErrorMessage` và các error channels khi endpoint/adapter được cấu hình phù hợp. Nhưng lỗi ở:

- Kafka deserializer/container,
- JMS message conversion,
- HTTP request-body binding,
- Spring Integration Transformer,
- Quarantine handler,
- hoặc business endpoint

có thể có **đường xử lý khác nhau**. Không nên viết một global error handler rồi khẳng định nó bao phủ toàn bộ. Cần integration test cho từng adapter cụ thể.

### 12.3. Error payload và thông tin an toàn

Định dạng nên hướng tới:

~~~text
quarantineKind = RAW_PARSE_ERROR
sourceSystem   = configured producer identity
tenantScope    = derived from trusted security context
transportRef   = topic/partition/offset (hoặc ID tương đương)
rawPayloadRef  = encrypted object reference
errorCode      = JSON_TO_ORDER_DESERIALIZATION_FAILED
parserVersion  = v2
receivedAt     = ...
~~~

Tránh:

~~~text
reason = "Cannot deserialize full payload: {...full customer data...}"
~~~

Lỗi parser/stack trace có thể vô tình chứa thông tin cá nhân và secret. Có thể lưu exception chi tiết trong một secure diagnostics store có retention, nhưng metrics/log thông thường nên dùng **error class và code hữu hạn**.

### 12.4. Một đường lỗi kỹ thuật riêng

~~~mermaid
flowchart LR
    A["Inbound Adapter"] -->|typed message| V["Validation Flow"]
    A -->|conversion exception| H["Adapter error handler"]
    H --> E["Safe parse failure metadata"]
    E --> Q[("Raw Quarantine Store / DLQ")]
    V -->|invalid rule| B[("Business Quarantine Store")]
    V -->|valid| P["Business Handler"]
~~~

Không buộc hai store phải tách hẳn; chúng có thể là hai nhóm case trong cùng hệ thống quarantine. Điều bắt buộc là **reason, provenance, replay strategy và access control không bị nhập nhằng**.

## 13. Durable quarantine: ghi nhận lỗi cũng là một side effect

### 13.1. Điều gì xảy ra khi store không sẵn sàng?

~~~text
T1  Broker giao message invalid.
T2  Validator phát hiện AMOUNT_MUST_BE_POSITIVE.
T3  Filter chuyển vào discard channel.
T4  Quarantine DB timeout.
T5  Consumer phải quyết định ack hay retry.
~~~

Nếu consumer **ack mặc dù quarantine write thất bại**, message có thể mất ở cả business flow lẫn quarantine. Nếu consumer **không ack và retry vô hạn**, backlog có thể lớn và producer/consumer bị nghẽn. Cần một chính sách rõ:

- Retry có giới hạn cho lỗi **transient persistence**.
- Backoff, circuit breaker hoặc tạm dừng intake khi store hỏng.
- Error/DLQ route dự phòng được bảo vệ khi phù hợp.
- Quan sát số message **đã validate invalid nhưng chưa persist**.
- Không tự chuyển invalid thành valid để “cứu” throughput.
- Nếu không có nơi lưu an toàn, fail closed/reject intake theo SLO đã thống nhất.

### 13.2. Thứ tự ack/persist theo hướng at-least-once

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant F as Validation/Filter
    participant Q as Durable Quarantine
    B->>C: Invalid message
    C->>F: Validate
    F-->>C: INVALID + reason codes
    C->>Q: Persist case (idempotency key)
    Q-->>C: Durable commit acknowledged
    C-->>B: Ack original delivery
    Note over B,C: Crash trước ack có thể redeliver
    B->>C: Duplicate delivery
    C->>Q: Upsert same quarantine identity
    Q-->>C: Existing case
    C-->>B: Ack duplicate
~~~

Đây là **mẫu thứ tự logic**, không phải transaction bảo đảm giữa DB và broker. Nếu DB đã commit nhưng broker ack bị mất, duplicate sẽ đến: quarantine writer phải **idempotent**. Nếu queue/adapter có transaction riêng hoặc offset commit khác, behavior cần kiểm tra theo adapter.

### 13.3. Persistent quarantine record: thiết kế bảng ví dụ

~~~sql
CREATE TABLE invalid_message_cases (
    quarantine_id      VARCHAR(100) PRIMARY KEY,
    tenant_scope       VARCHAR(100) NOT NULL,
    source_system      VARCHAR(100) NOT NULL,
    ingress_event_id   VARCHAR(200) NOT NULL,
    validation_version VARCHAR(80) NOT NULL,
    reason_codes_json  TEXT NOT NULL,
    payload_reference  TEXT,
    payload_sha256     VARCHAR(64),
    case_status        VARCHAR(40) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    UNIQUE (tenant_scope, source_system, ingress_event_id)
);
~~~

**Đây là skeleton SQL minh họa**, không phải schema production hoàn chỉnh. Tùy DB, JSON column, transaction isolation, tenant row-level security và index strategy sẽ khác. Nếu cần nhiều **payload revisions/revalidations** cho cùng ingress event, nên tách bảng **case identity** với bảng **attempt/history** thay vì để unique key ngăn mọi lần replay hợp lệ.

### 13.4. Unique key không tự giải quyết mọi vấn đề

Một unique constraint giúp giảm duplicate cases, nhưng chưa trả lời:

- Cùng key mang payload khác thì conflict được giữ ở đâu?
- Hai transactions đồng thời tạo case có xử lý race không?
- Nếu payload object đã lưu nhưng DB insert thất bại, object rác được dọn ra sao?
- Nếu DB case commit nhưng object reference chưa sẵn sàng, có consumer nào đọc được payload?
- Một business replay đã sửa có giữ bản gốc theo retention không?

Khi dữ liệu được lưu ở **object store và database**, đó cũng là một bài toán **dual-write**. Có thể cần staging/object version, checksum, outbox/reconciler và cleanup orphans để tránh case chỉ có metadata nhưng thiếu dữ liệu gốc.

### 13.5. Retention phải phản ánh mức độ nhạy cảm

| Trạng thái | Retention gợi ý cần quyết định |
|---|---|
| NEW, chưa review | Có SLA review và cảnh báo gần hết hạn. |
| UNDER_REVIEW | Giữ đủ dữ liệu theo chính sách review, không vô hạn. |
| REPLAYED | Có thể giữ metadata/tombstone và receipt, giảm payload nếu được phép. |
| DISCARDED | Lưu lý do/phê duyệt tối thiểu, xóa payload theo policy. |
| EXPIRED | Có cleanup và audit, không tự replay sau expiration. |
| Security rejected | Retention và quyền riêng, tránh hiển thị payload cho operator phổ thông. |

Một quarantine store chứa đầy PII/credentials là rủi ro lớn. Việc lưu lâu không tự tốt hơn: phải tuân thủ nguyên tắc giảm thiểu dữ liệu, mã hóa, kiểm soát truy cập, audit và chính sách xóa.

## 14. Replay không phải “đẩy lại message là xong”

### 14.1. Năm bước của replay có kiểm soát

Một quy trình an toàn:

1. **Review:** xác định nguyên nhân invalid và chủ sở hữu dữ liệu.
2. **Correction:** sửa ở producer/source hoặc tạo bản sửa có provenance, không sửa âm thầm record gốc.
3. **Authorization:** kiểm tra operator/service có quyền replay đúng tenant/business operation.
4. **Revalidation:** chạy policy hiện hành hoặc policy được chỉ định có version; lưu **kết quả mới**.
5. **Dispatch:** chỉ nếu validation pass mới gửi vào business flow, với idempotency key, audit và acknowledgment phù hợp.

~~~mermaid
flowchart TD
    Q[("Quarantine Case")] --> R{"Authorized review?"}
    R -->|Không| STOP["Keep quarantined / deny"]
    R -->|Có| F["Correct source or versioned payload"]
    F --> V["Revalidate under selected policy"]
    V -->|Invalid| AGAIN["New review attempt with reasons"]
    V -->|Valid| I{"Business operation already processed?"}
    I -->|Yes| OLD["Record existing outcome; no duplicate effect"]
    I -->|No / safe| D["Controlled dispatch"]
    D --> AUDIT["Audit attempt and result"]
~~~

### 14.2. Không trực tiếp gọi business handler để bỏ qua validation

Một anti-pattern:

~~~text
Quarantine UI -> "Force replay"
  -> BusinessHandler.handle(rawOriginal)
~~~

Điều này có thể đưa cùng dữ liệu sai quay vào xử lý, hoặc tạo side effect trùng. Nếu workflow có chức năng **override có phê duyệt**, quyền override, lý do, snapshot dữ liệu và phạm vi tác động phải được định nghĩa rõ; không coi nó là replay mặc định.

### 14.3. Phân biệt original event, correction và replay attempt

~~~text
originalEventId = EVT-200
quarantineId    = Q-200
originalVersion = 1

authorizedCorrection:
  correctedRevisionId = REV-2
  replayAttemptId     = ATT-2
  replayOf            = Q-200
  validationPolicy    = orders-v2
~~~

Các ID phục vụ:

- **Original identity:** truy nguyên dữ liệu đã bị từ chối.
- **Correction version:** biết nội dung nào được sửa và bởi ai.
- **Replay attempt:** theo dõi từng lần đưa lại vào luồng.
- **Business idempotency key:** bảo vệ side effect nếu operation đã từng hoàn tất.

**Không nên dùng replayAttemptId làm operationId mới** nếu đây chỉ là thử lại cùng payment/order operation. Ngược lại, nếu correction thực sự tạo một operation mới, phải có business approval và key mới rõ ràng.

### 14.4. Replay vào policy mới có thể thay outcome

Ví dụ:

~~~text
T1: orders-v1 không chấp nhận currency USD
    -> Quarantine: UNSUPPORTED_CURRENCY

T2: orders-v2 cho phép USD với FX validation mới
    -> Revalidate cùng original ở policy v2
    -> Có thể valid, nếu đầy đủ field/authorization mới
~~~

Không được giả định “quarantine invalid” là trạng thái vĩnh viễn bất kể policy thay đổi. Nhưng cũng không được âm thầm **đổi chính sách của bản ghi cũ** mà không lưu version: cần biết ở thời điểm nhận, rule nào đã được áp dụng và vì sao.

### 14.5. Không tạo vòng lặp quarantine → replay → quarantine vô hạn

Đặt:

- Maximum replay attempts và backoff thích hợp.
- Điều kiện chờ correction hoặc policy change thật.
- Trạng thái `REPLAY_REJECTED`/`STILL_INVALID` khi chưa sửa.
- Quota/operator permissions và cảnh báo poison messages.
- Một **quarantineOf** hoặc lineage field giúp phân biệt original case với attempts.

**Invalid deterministic payload** được replay không sửa gì thường vẫn invalid. Retry vô hạn không tạo ra dữ liệu thiếu.

## 15. Ví dụ revalidation có ràng buộc nguồn gốc

### 15.1. Một policy nhỏ để kiểm tra correction

Ví dụ chỉ kiểm tra **điều kiện chuẩn bị replay**. Nó **không tự ghi DB**, **không tự dispatch đến business flow** và **không thay thực thi authorization production**.

~~~java
final class ReplayReviewPolicy {
    private final OrderValidationPolicy validator;

    ReplayReviewPolicy(OrderValidationPolicy validator) {
        this.validator = validator;
    }

    ValidationOutcome revalidate(
            QuarantineCase original,
            IngressOrder corrected,
            boolean authorizationGranted) {

        // Flag này là kết quả của một bước authorization đáng tin
        // trong bài tập, KHÔNG được lấy từ input JSON/client.
        if (!authorizationGranted) {
            throw new SecurityException("REPLAY_NOT_AUTHORIZED");
        }
        if (!original.key().tenant().equals(
                    corrected.authenticatedTenant())
                || !original.key().source().equals(
                    corrected.trustedSource())) {
            throw new SecurityException("REPLAY_SCOPE_MISMATCH");
        }
        if (!"NEW".equals(original.state())
                && !"UNDER_REVIEW".equals(original.state())) {
            throw new IllegalStateException(
                    "REPLAY_STATE_NOT_ALLOWED");
        }

        // Validation lại; không tự đổi originalOutcome.
        return validator.validate(corrected);
    }
}
~~~

Trong production, `authorizationGranted` phải đến từ **trusted authorization service**, có actor ID và permission được xác nhận. Ngoài ra cần CAS/state transition để hai operator không cùng replay một case, đảm bảo correction gắn đúng original event, tenant và business operation, lưu audit rồi mới dispatch.

### 15.2. Sửa sai số tiền rồi revalidate

~~~java
import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class QuarantineRevalidationTest {
    @Test
    void approvedCorrectionCanPassValidation() {
        OrderValidationPolicy validator =
                new OrderValidationPolicy();
        IngressOrder originalInput = new IngressOrder(
                "ING-100", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-100", "ORD-100",
                        new BigDecimal("-10"),
                        "VND", null));

        InMemoryQuarantineStore store =
                new InMemoryQuarantineStore(Clock.systemUTC());
        QuarantineCase originalCase =
                store.store(validator.validate(originalInput));

        IngressOrder corrected = new IngressOrder(
                "ING-100-REV-2", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-100", "ORD-100",
                        new BigDecimal("100000"),
                        "VND", null));

        ValidationOutcome result =
                new ReplayReviewPolicy(validator)
                        .revalidate(originalCase, corrected, true);

        assertTrue(result.valid());
        // Đây mới là revalidation: business handler chưa được gọi.
    }
}
~~~

### 15.3. Không có quyền thì không có replay

~~~java
import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class QuarantineReplayAuthorizationTest {
    @Test
    void correctionFromDifferentTenantIsRejected() {
        OrderValidationPolicy validator =
                new OrderValidationPolicy();
        InMemoryQuarantineStore store =
                new InMemoryQuarantineStore(Clock.systemUTC());

        QuarantineCase originalCase = store.store(
                validator.validate(new IngressOrder(
                        "ING-200", "TENANT-A", "oms",
                        new OrderSubmitted(
                                "EVT-200", "ORD-200",
                                BigDecimal.ZERO,
                                "VND", null))));

        IngressOrder otherTenant = new IngressOrder(
                "ING-200-REV-2", "TENANT-B", "oms",
                new OrderSubmitted(
                        "EVT-200", "ORD-200",
                        new BigDecimal("10"),
                        "VND", null));

        assertThrows(SecurityException.class, () ->
                new ReplayReviewPolicy(validator)
                        .revalidate(originalCase, otherTenant, true));
    }
}
~~~

Test này chỉ chứng minh một **scope check thuần Java**. Security review đầy đủ phải xác thực actor, case ownership, payload provenance, action permission và audit tại server.

## 16. Tương tác với các Enterprise Integration Patterns

### 16.1. Filter trước hay sau Transformer?

~~~text
Option A:
  Ingress -> Basic Filter -> Transformer -> Business Handler

Option B:
  Ingress -> Validation Transformer -> Filter -> Business Handler
                                         |
                                         +-> Quarantine
~~~

**Option B** phù hợp khi quarantine cần giữ **reason codes** và policy version. Nhưng nếu có nguy cơ đầu vào độc hại khiến Transformer throw (chẳng hạn payload deserialization), cần **giới hạn dữ liệu, error boundary trước Transformer** hoặc bước validation sơ bộ. Không bắt mọi exception rồi coi là business invalid.

### 16.2. Router: không cho invalid lọt sang business channel

Một hệ thống có thể dùng Content-Based Router thay Filter:

~~~text
ValidationOutcome
   -> route(valid ? "orders.valid" : "orders.quarantine")
~~~

Điều này cũng hợp lý. Ưu điểm Filter + discardChannel là thể hiện đúng quyết định **chấp nhận/từ chối** của Message Filter. Ưu điểm Router là dễ phát triển nhiều nhánh: `VALID`, `INVALID_SCHEMA`, `INVALID_BUSINESS`, `SECURITY_REJECTED`.

Tuy nhiên, nếu Router có `defaultOutputChannel` trỏ về business flow, lỗi thiếu mapping có thể khiến invalid vô tình lọt vào nhánh chính. Hãy chọn **fail closed**, route không xác định nên đi quarantine/error flow có kiểm soát.

### 16.3. Splitter: mỗi phần invalid có identity riêng

~~~text
Batch B-1
  -> Splitter
      -> Item I-1 valid
      -> Item I-2 invalid
      -> Item I-3 valid
~~~

Nếu Filter chỉ cho I-1 và I-3 đi tiếp, một **Aggregator** chờ đủ ba phần theo `sequenceSize=3` có thể bị kẹt. Cần định nghĩa:

1. Quarantine cho **item I-2** có `batchProcessingId + itemId` hoặc stable child key.
2. Một **failure outcome/placeholder** được phát về Aggregator nếu business contract yêu cầu kết quả mỗi item.
3. Release strategy dựa trên **tập child IDs**, không chỉ số message.
4. Có timeout và chính sách partial/final failure cho batch.

**Không đếm message I-1 lặp hai lần thay cho I-2**. Quarantine ID của một child cũng không thay correlation ID của batch.

### 16.4. Aggregator: quarantine không mặc nhiên là reply

Một event bị chuyển sang quarantine là dấu hiệu cần điều tra, không đồng nghĩa aggregator nhận một **business result hợp lệ**. Nếu downstream cần một kết luận cuối, có thể thiết kế:

~~~text
Item I-1 -> Outcome(SUCCESS)
Item I-2 -> Outcome(INVALID, reasonCode=...)
Item I-3 -> Outcome(SUCCESS)
   -> Aggregator -> BatchResult(PARTIAL_FAILURE)
~~~

Đây là contract ứng dụng. Không nên tạo `SUCCESS` giả cho I-2 để lấp sequence; nếu có một rejection outcome thì nó phải ghi đúng lý do.

### 16.5. Scatter–Gather: một nhánh invalid ảnh hưởng quyết định cuối

~~~text
REQ-1
  -> Inventory check: PASS
  -> Fraud request invalid: QUARANTINED
~~~

Nếu Fraud là điều kiện bắt buộc, Gatherer **không được xác nhận đơn** chỉ nhờ Inventory PASS. Cần outcome/timeout cho nhánh Fraud theo business contract, và có idempotency/correlation để không trộn reply của request khác hoặc replay muộn.

### 16.6. Resequencer: invalid tạo gap

Giả sử một sequence `1,2,3`:

~~~text
seq=1 valid
seq=2 invalid -> quarantine
seq=3 valid
~~~

Resequencer phía sau Filter có thể chờ `#2` mãi nếu hợp đồng cần đầy đủ sequence. Một cách xử lý là **placeholder outcome** có `sequenceNumber=2` và reason code, hoặc quarantine cả group, hoặc release theo policy có gap được cho phép. Không được **tăng sequenceNumber** tùy tiện trên từng message để che mất phần thiếu.

### 16.7. Idempotent Receiver: invalid duplicate vẫn cần audit

Một invalid event có thể bị broker redeliver nhiều lần. Quarantine writer nên dedupe theo stable identity; nhưng **idempotency key dùng để tạo quarantine case** không nhất thiết là **business operation ID** dùng khi authorized replay đã valid.

~~~text
quarantineKey = tenant + source + originalEventIdentity
businessOperationKey = tenant + businessOperationType + operationId
~~~

Nếu dùng cùng một khóa cho cả hai với semantics không rõ, có thể xảy ra:

- Mark invalid as `SEEN` rồi replay hợp lệ bị chặn vô cớ.
- Replay với envelope ID mới làm bypass business idempotency và tạo side effect trùng.
- Two independent consumer branches dùng chung key, nhánh sau bị coi duplicate.

### 16.8. Claim Check: quarantine token khác quarantine payload

Nếu message chỉ chứa **claim check ID** tham chiếu payload gốc, lưu token vào quarantine mà **dữ liệu trong Claim Store đã hết hạn/xóa** có thể khiến replay không thể khôi phục được.

Khi thiết kế:

- Xem xét claim TTL so với quarantine review/replay horizon.
- Giữ protected snapshot/reference nếu chính sách bảo mật cho phép.
- Ghi trạng thái `CLAIM_EXPIRED`/`CLAIM_MISSING` thay vì biến thành business invalid giả.
- Không cấp claim ID mới để vượt qua revoke/authorization.

### 16.9. Gateway và yêu cầu đồng bộ

Nếu một Gateway cần reply, message bị Filter discard vào quarantine có thể khiến caller **chờ đến timeout** vì không có reply trên đường cũ.

Hãy định nghĩa hợp đồng rõ:

~~~text
Request valid   -> ACCEPTED / business result
Request invalid -> REJECTED_VALIDATION (issues, quarantineRef)
Request pending -> PENDING (operationId)
Technical error -> RETRYABLE_ERROR / INTERNAL_ERROR theo policy
~~~

**Không mặc định `discardChannel` tự trả một reply cho Gateway**. Nếu cần một kết quả đồng bộ, thiết kế reply path/gateway output rõ và kiểm thử; có thể dùng Router/handler trả `ValidationResponse` thay vì một one-way quarantine writer.

## 17. Error channel, retry và quarantine: tránh vòng lặp vô hạn

### 17.1. Lỗi validation và lỗi của validator là hai chuyện khác nhau

~~~text
Case A:
  validator.validate(order) returns issues=[AMOUNT_MUST_BE_POSITIVE]
  -> Normal invalid route -> Quarantine

Case B:
  validator.validate(order) throws due to unhandled bug
  -> Technical error, needs error handling

Case C:
  validator returns invalid, quarantine DB unavailable
  -> Persistence failure, case not durably stored
~~~

**Không gom Case B/C thành `INVALID_BUSINESS`**. Một validator có thể hỏng do bug, null pointer hoặc không truy cập được reference data. Nếu cứ quarantine toàn bộ như bad input, ta sẽ trách nhầm producer và bỏ lỡ incident của hệ thống.

### 17.2. Retry policy theo lớp lỗi

| Lỗi | Retry tự động cùng payload? | Vì sao? |
|---|---|---|
| Missing `orderId` | Không hữu ích nếu input bất biến. | Cần producer correction hoặc authorized replay. |
| Negative amount | Không hữu ích. | Deterministic rule failure. |
| Unsupported schema version | Không cho đến khi parser/schema tương thích. | Retry ngay thường chỉ lặp lỗi. |
| Quarantine DB tạm không sẵn sàng | Có giới hạn. | Dữ liệu có thể lưu sau khi store hồi phục. |
| Broker publish/ack timeout | Có thể, theo delivery semantics. | Có thể đã publish; cần stable identity/dedupe. |
| Validator code bug | Không replay vô hạn. | Cần sửa code/deploy và revalidation có kiểm soát. |
| Unknown tenant/security denied | Không với cùng quyền hiện tại. | Tránh retry tấn công. |
| Business handler timeout sau valid | Retry/reconcile đúng operation. | Không tự đưa vào business-invalid quarantine. |
| Same quarantine key, payload conflict | Quarantine conflict/manual review. | Không âm thầm overwrite. |

### 17.3. Không đặt error flow quay về chính Filter vô hạn

~~~mermaid
flowchart TD
    V["Validation Endpoint"] -->|invalid| Q["Quarantine Writer"]
    Q -->|DB failure| ER["Error Recovery"]
    ER -->|bounded retry| Q
    ER -->|retry exhausted| ALT["Fallback durable route / alert"]
    ALT --> MAN["Manual recovery"]
~~~

Một anti-pattern:

~~~text
Validation -> Quarantine -> DB exception
  -> errorChannel -> Validation -> Quarantine -> DB exception -> ...
~~~

Nếu error handler không có giới hạn retry hoặc không phân loại, cùng invalid event có thể chạy vòng mãi, chiếm tài nguyên và gây flood logs. Cần max attempts, backoff, dead-letter/fallback hoặc tạm dừng intake theo policy.

### 17.4. Nếu business handler lỗi sau khi validation pass

Đừng định tuyến lại bằng cách gán lý do `VALIDATION_FAILED` chỉ vì handler throw. Một dữ liệu đã pass validation vẫn có thể gặp:

- Dependency timeout.
- Concurrency conflict trong DB.
- Stale state hoặc optimistic locking.
- Business outcome như inventory unavailable.
- Payment already completed và duplicate redelivery.

Những lỗi đó cần **error handling/retry/idempotency** riêng. Quarantine có thể giữ một case “processing failure” nếu workflow muốn, nhưng phải ghi **kind khác** với “invalid input”.

### 17.5. Poison message và nguồn lỗi

Một raw record khiến deserializer ném exception ngay có thể cần DLQ hoặc raw quarantine. Một typed message có field sai deterministic nên đi business quarantine. Một message hợp lệ nhưng liên tục làm service khác throw có thể cần technical DLQ sau retry. **Không dùng một công thức chung retry N lần rồi vứt mọi loại message vào cùng hàng đợi mà không có lý do và ownership**.

## 18. Observability: phân biệt received, rejected và persisted

### 18.1. Structured logs theo mốc

~~~text
event=INGRESS_RECEIVED
  envelopeRef=ING-100
  source=oms
  traceRef=...

event=VALIDATION_COMPLETED
  envelopeRef=ING-100
  policyVersion=orders-v1
  outcome=INVALID
  reasonCodes=[AMOUNT_MUST_BE_POSITIVE]

event=QUARANTINE_WRITE_REQUESTED
  envelopeRef=ING-100

event=QUARANTINE_PERSISTED
  quarantineRef=Q-100
  source=oms
  status=NEW

event=INGRESS_ACKNOWLEDGED
  envelopeRef=ING-100

event=REPLAY_APPROVED
  quarantineRef=Q-100
  correctionRevision=REV-2
  actorRef=...

event=REVALIDATION_COMPLETED
  quarantineRef=Q-100
  outcome=VALID
~~~

Đây là **schema log của ứng dụng đề xuất**, không phải các sự kiện mặc định của Spring Integration. Ghi `QUARANTINE_PERSISTED` chỉ sau khi nhận được bằng chứng commit từ storage theo contract; `MessageChannel.send()` không nhất thiết là bằng chứng lưu bền vững.

### 18.2. Metrics cần tách đúng mốc

| Metric gợi ý | Mục đích |
|---|---|
| `validation_messages_received_total` | Bao nhiêu delivery đi vào validation flow? |
| `validation_passed_total` | Bao nhiêu message pass policy? |
| `validation_rejected_total{reason,policy}` | Bao nhiêu invalid theo lý do/version? |
| `quarantine_persisted_total{kind}` | Bao nhiêu case được lưu bền? |
| `quarantine_duplicate_total` | Bao nhiêu lần redelivery được dedupe? |
| `quarantine_conflict_total` | Có reused identity với payload khác? |
| `quarantine_write_failed_total{reason}` | Store failures. |
| `quarantine_cases_open` | Backlog NEW/UNDER_REVIEW. |
| `quarantine_case_age_seconds` | Case nào tồn tại quá lâu? |
| `quarantine_replay_attempt_total{result}` | Revalidate/replay thành công hay thất bại? |
| `quarantine_replay_loop_prevented_total` | Có chặn replay thiếu sửa đổi? |
| `validation_deserialization_failed_total` | Lỗi decode trước typed Filter. |
| `quarantine_raw_bytes_total` | Dung lượng raw payload được giữ. |
| `quarantine_cleanup_failed_total` | Xóa hết retention thất bại. |
| `validation_filter_latency_seconds` | Độ trễ validation/filter. |

Các tên này chỉ là **gợi ý đo lường**. Spring Integration/Micrometer có thể có meter riêng theo version và cấu hình; không mặc định framework tự phát mọi metric trên.

**Tránh high-cardinality labels:** Không dùng `quarantineId`, `eventId`, `orderId`, `traceId`, email hoặc ID người dùng làm metric label. Có thể lưu chúng trong log/tracing/audit có retention và quyền phù hợp.

### 18.3. Những con số cần được đối chiếu

Một dashboard chất lượng nên giúp trả lời:

~~~text
ingress received:        10,000 deliveries
passed validation:        9,700
rejected invalid:           300
quarantine persisted:       295
quarantine write failed:      5
~~~

Số liệu minh họa trên cho thấy **5 invalid messages chưa có bằng chứng lưu bền**. Nếu metric chỉ đếm `validation_rejected_total=300` rồi báo “đã quarantine 300”, thông tin sẽ sai. Phải theo dõi cả retry, persisted acknowledgment và những record đang pending.

Không nhất thiết tổng phải khớp tức thì trong flow async vì có in-flight/retries; dùng time window/correlation và states phù hợp thay vì lấy hiệu số thô ở mọi thời điểm.

### 18.4. Cảnh báo có ích

| Tín hiệu | Vì sao đáng chú ý |
|---|---|
| Invalid rate tăng đột ngột theo source/schema | Producer deploy lỗi hoặc hợp đồng thay đổi. |
| Quarantine persistence failures tăng | Có nguy cơ mất hoặc backlog invalid messages. |
| Cases NEW quá SLA review | Đội sở hữu dữ liệu không xử lý kịp. |
| Repeat invalid từ cùng policy | Correction/replay chưa sửa nguyên nhân hoặc producer không cập nhật. |
| Raw parse errors tăng | Schema conversion/adapter config mismatch. |
| Replay approvals tăng bất thường | Rủi ro abuse hoặc quy trình tự động sai. |
| Retention cleanup quá hạn | Rủi ro dữ liệu và storage. |
| Unknown tenant/security errors | Có thể là cấu hình sai hoặc tấn công. |

### 18.5. Message History không đủ làm audit

Spring Integration Message History, khi được bật, giúp quan sát message qua các component. Nhưng nó không tự chứng minh:

- Quarantine case đã commit bền vào DB.
- Payload đã được mã hóa/quyền truy cập đúng.
- Một operator có quyền đã sửa case nào.
- Revalidation theo policy version nào và business outcome ra sao.
- Raw message bị decode lỗi đã tới discard channel của Filter.

Cần kết hợp **integration logs, case store, broker delivery state, tracing và audit trail của review/replay**.

## 19. Chẩn đoán khi invalid message “biến mất”

Giả sử producer báo đã gửi `EVT-300`, business handler không xử lý, nhưng đội vận hành cũng không tìm thấy quarantine case.

Một quy trình điều tra:

1. **Nguồn:** producer đã phát record thành công hay chỉ trả kết quả enqueue cục bộ?
2. **Broker:** record còn tồn tại ở partition/queue nào? Ack/offset commit diễn ra lúc nào?
3. **Deserialize:** inbound adapter có đọc/parse được message không? Có lỗi trước typed Filter không?
4. **Trusted context:** security context, tenant, source mapping có hợp lệ hay message bị chặn trước validation?
5. **Validator:** policy version nào chạy, outcome là valid/invalid/exception?
6. **Filter:** discard channel có được cấu hình? `throwExceptionOnRejection` có đang làm flow chạy sang error path khác?
7. **Discard handler:** `orders.quarantine` có subscriber đang chạy không? Channel có bị stop?
8. **Store:** có ghi thành công không, hay DB timeout/unique conflict/serialization error?
9. **Dedupe:** record đã tồn tại dưới quarantine ID khác nhưng cùng stable ingress key không?
10. **Retention:** record đã expired/cleaned/archived chưa? Có kiểm tra tombstone và audit không?
11. **Replay:** case từng được correction/replayed rồi chuyển trạng thái? Có lineage?
12. **Authorization:** operator đang tìm đúng tenant/source và có quyền xem case không?
13. **Observability:** log nào xác nhận `VALIDATION_COMPLETED`, `QUARANTINE_PERSISTED`, `INGRESS_ACKNOWLEDGED`?
14. **Regression:** lập test tái hiện đúng điểm message bị mất và sửa ack/error route.

### 19.1. Một vài chẩn đoán nhanh

| Triệu chứng | Nơi nên kiểm tra trước |
|---|---|
| Không có log validator nhưng có lỗi conversion | Deserializer/inbound adapter error route. |
| Có validation invalid, không có log discard handler | Filter discardChannel/subscriber/throwExceptionOnRejection. |
| Discard handler được gọi, store không có case | DB write/transaction/unique conflict/TTL. |
| Case có tồn tại nhưng operator không nhìn thấy | Tenant scope, review UI query/authorization/retention. |
| Quarantine case tăng gấp nhiều lần sau broker retry | Stable ingress identity và idempotent write. |
| Replay xong vẫn invalid cùng mã lỗi | Correction không được áp dụng hoặc policy không đổi. |
| Một item bị quarantine khiến Aggregator kẹt | Missing child outcome/sequence/release strategy. |
| Gateway timeout với invalid request | Discard path không có response contract. |
| Technical outage bị tính vào invalid rate | Error classification đang sai. |

### 19.2. Runbook khi kho quarantine không ghi được

~~~text
Detect:
  quarantine_write_failed_total increases

Protect:
  stop silent acknowledgment of invalid inputs
  apply bounded retry/backpressure

Contain:
  send to approved durable fallback if available
  avoid logging raw sensitive payload

Recover:
  restore store / repair schema / free capacity
  redeliver with same stable ingress identity
  dedupe and reconcile completed writes

Verify:
  number of rejected vs durably stored cases
  failed messages no longer in-flight without ownership
~~~

**Không được chuyển toàn bộ invalid messages sang business handler** chỉ vì kho quarantine gặp sự cố. Đó là fail-open và có thể làm phát sinh tác động nghiệp vụ sai.

## 20. Ma trận kiểm thử Message Filter → Quarantine

| ID | Kịch bản | Điều cần xác minh | Không được xảy ra |
|---|---|---|---|
| QF-01 | Typed order hợp lệ | Đi vào business handler, không có case quarantine. | Bị reject nhầm. |
| QF-02 | Amount bằng 0 | Quarantine với `AMOUNT_MUST_BE_POSITIVE`. | Gọi business handler. |
| QF-03 | Amount âm | Quarantine đúng reason. | Silent drop. |
| QF-04 | Amount null | Quarantine, không ném NPE từ validator. | Lỗi mơ hồ. |
| QF-05 | Amount vượt giới hạn demo | `AMOUNT_EXCEEDS_LIMIT`. | Chấp nhận ngoài policy. |
| QF-06 | Currency không hỗ trợ | `UNSUPPORTED_CURRENCY`. | Gửi tới payment. |
| QF-07 | orderId trống | `ORDER_ID_REQUIRED`. | Quarantine thiếu reason. |
| QF-08 | eventId trống | `EVENT_ID_REQUIRED`, vẫn có trusted envelope ID. | Không thể tạo quarantine case. |
| QF-09 | Nhiều field sai cùng lúc | Lưu đủ issues đã kiểm tra. | Chỉ báo lỗi đầu nếu contract yêu cầu nhiều lỗi. |
| QF-10 | Order payload null trong envelope | `ORDER_PAYLOAD_MISSING`. | Business handler nhận null order. |
| QF-11 | Trusted source không thuộc allowlist | `UNSUPPORTED_SOURCE`. | Bỏ qua rule nguồn. |
| QF-12 | Envelope metadata không hợp lệ | Reject ở trusted ingress boundary. | Coi untrusted tenant là đã xác thực. |
| QF-13 | JSON sai kiểu amount trước deserialization | Adapter error route/raw quarantine. | Tin typed Filter đã chạy. |
| QF-14 | Malformed JSON không decode được | Raw reference + safe error code. | Log toàn raw payload nhạy cảm. |
| QF-15 | Adapter authorization denied | Security rejection/audit. | Lưu sai tenant scope. |
| QF-16 | Filter false, discardChannel cấu hình đúng | Handler quarantine nhận `ValidationOutcome`. | Message mất âm thầm. |
| QF-17 | Filter false nhưng bật throwExceptionOnRejection | Behavior theo config được kiểm thử. | Giả định tự đi discard như thường. |
| QF-18 | Discard channel không có subscriber | Error/handling theo channel contract. | Ack rồi mất message. |
| QF-19 | Quarantine store unavailable | Bounded retry/fallback/alert. | Ghi persisted giả. |
| QF-20 | DB ghi case nhưng ack broker bị mất | Redelivery dedupe cùng case. | Tạo thêm case trùng. |
| QF-21 | Hai invalid deliveries cùng envelope identity | Store một case hoặc idempotent update. | Hai cases trùng vô hạn. |
| QF-22 | Cùng envelope identity, payload khác | Phát hiện conflict và lưu chứng cứ. | Overwrite im lặng. |
| QF-23 | Hai tenants dùng cùng local envelope ID | Isolation theo tenant scope. | Gộp hai cases. |
| QF-24 | Hai source systems dùng cùng ID | Isolation theo source scope. | Gộp hai cases. |
| QF-25 | In-memory quarantine store restart | Giới hạn demo được ghi nhận. | Tuyên bố durable. |
| QF-26 | Durable DB + restart | Case phục hồi/đọc được. | Mất case khi node chết. |
| QF-27 | Object payload saved, metadata DB fail | Orphan cleanup/reconciliation. | Thất thoát dữ liệu không kiểm soát. |
| QF-28 | Metadata case saved, object missing | Detect inaccessible payload. | Replay payload rỗng. |
| QF-29 | Payload quá lớn | Size cap/protected reference. | OOM/ghi log khổng lồ. |
| QF-30 | Quarantine record chứa PII | Encryption/access/retention đúng. | Người không có quyền đọc raw. |
| QF-31 | Replay không có authorization | Deny/audit. | Đẩy vào business handler. |
| QF-32 | Correction từ tenant khác | Reject scope mismatch. | Cross-tenant replay. |
| QF-33 | Correction hợp lệ rồi revalidate | Pass policy có version. | Gọi handler trước khi validate. |
| QF-34 | Replay không sửa payload | Still invalid + bounded attempts. | Vòng lặp không giới hạn. |
| QF-35 | Policy đổi từ v1 sang v2 | Outcome mới có audit/lineage. | Ghi đè lý do cũ. |
| QF-36 | Replay cùng business operation đã completed | Idempotency trả kết quả cũ. | Side effect trùng. |
| QF-37 | Filter loại child của Splitter | Batch có failure outcome hoặc timeout. | Aggregator chờ vô hạn. |
| QF-38 | Resequencer chờ seq đã quarantine | Gap/placeholder/recovery được định nghĩa. | Phát sai thứ tự. |
| QF-39 | Scatter–Gather có nhánh invalid | Không tạo final success thiếu nhánh. | Confirm đơn sớm. |
| QF-40 | Claim Check token hết hạn khi review | Protected replay source/expired handling. | Tự đoán payload. |
| QF-41 | Invalid request qua Gateway | Có response contract. | Caller chờ vô hạn do discard. |
| QF-42 | Technical DB timeout sau valid | Phân loại technical failure. | Đánh dấu payload invalid. |
| QF-43 | Cleanup quá retention deadline | Alert/audit/cleanup retries. | Dữ liệu tồn tại vô hạn. |
| QF-44 | Message duplicate nhưng hợp lệ | Idempotent business handling. | Quarantine chỉ vì redelivery. |
| QF-45 | Operator replay hai lần đồng thời | State CAS/fencing hoặc workflow locking. | Hai side effects. |
| QF-46 | Store overloaded/queue full | Backpressure và loss prevention. | Silent drop. |
| QF-47 | Error handler lỗi lần nữa | Bounded recovery/fallback. | Recursive loop vô hạn. |
| QF-48 | Số rejected khác số persisted | Dashboard chỉ đúng pending/failed count. | Báo tất cả đã lưu dù chưa commit. |

### 20.1. Từng cấp test chứng minh điều gì?

| Cấp | Nên kiểm tra | Chưa chứng minh |
|---|---|---|
| **Unit validator** | Rule, issue codes, policy version và null safety. | Filter đã route đúng. |
| **Spring Integration** | Transformer → Filter → discard channel → handler. | Persistence qua restart nếu chỉ fake store. |
| **Database integration** | Unique key, transactions, case identity, concurrent writes. | Broker ack semantics nếu không có broker. |
| **Adapter integration** | Deserialization errors, header mapping, DLQ, retry, ack. | Business side effect nếu chỉ mock handler. |
| **Replay workflow** | Auth, revalidation, versioned correction, audit. | Payment idempotency nếu không dùng provider/ledger thật. |
| **System/chaos test** | DB outage, process crash, throughput, backpressure, retention. | Mọi tình huống production bên ngoài test. |
| **Security test** | Cross-tenant access, PII redaction, replay permissions. | Toàn bộ risk nếu chưa review trust boundary. |

**Unit test validator pass không chứng minh invalid message đã được quarantine an toàn.** Phải có ít nhất một test đi qua channel/adapter và persistent quarantine writer của hệ thống thật ở những ranh giới production cần tin cậy.

## 21. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách phù hợp |
|---|---|---|
| Chỉ gọi `filter(...)` mà không có discard path. | Invalid message biến mất. | Cấu hình discard channel/flow và assert persisted. |
| Dùng một boolean, không lưu reason codes. | Không biết sửa gì, không truy nguyên policy. | ValidationOutcome chứa issues và version. |
| Gọi lại validator ở quarantine handler. | Kết quả khác khi policy/time/state đổi. | Giữ outcome đã tính ở bước validation. |
| Gộp mọi exception thành invalid. | Đổ lỗi cho producer khi DB/adapter hỏng. | Phân loại technical/business/security. |
| Nghĩ Filter bắt được malformed JSON. | Bỏ sót lỗi trước deserializer. | Adapter error route và raw quarantine. |
| Đặt `throwExceptionOnRejection` mà vẫn trông đợi discard bình thường. | Message đi đường lỗi khác. | Chọn semantics và test đúng config. |
| Đặt tên channel `quarantine` là coi như bền vững. | Mất case khi restart. | Persistent store/queue và ack policy. |
| Ack broker trước khi case commit. | Không có record ở cả hai nhánh. | Persist rồi ack theo delivery contract. |
| Coi `send=true` là đã lưu bền. | Theo dõi sai mốc. | Kiểm tra transaction/commit hoặc durable enqueue. |
| Dedupe theo Spring message ID mỗi lần tạo mới. | Redelivery tạo nhiều cases. | Stable trusted ingress identity. |
| Coi hai payload khác nhau cùng ID là duplicate. | Mất chứng cứ và nhầm dữ liệu. | Conflict detection + audit. |
| Dùng tenant ID lấy thẳng từ invalid payload. | Ghi sai tenant/rò rỉ dữ liệu. | Trusted identity từ authentication context. |
| Lưu raw payload trong log và exception message. | Rò rỉ PII/secrets. | Protected store + redacted metadata. |
| Replay bằng cách gọi thẳng business handler. | Bỏ qua validation và quyền. | Correction → auth → revalidation → dispatch. |
| Tạo operationId mới cho mọi replay. | Idempotency bị vô hiệu hóa. | Giữ stable business operation identity. |
| Revalidate overwrite issues/history cũ. | Mất bằng chứng rule ban đầu. | Versioned attempts/audit. |
| Auto replay invalid deterministic data vô hạn. | Poison loop/bão hòa queue. | Bounded retry, đòi correction/policy change. |
| Filter một child mà không báo Aggregator. | Message group chờ mãi. | Failure outcome/placeholder và timeout. |
| Discard Gateway request không gửi reply. | Caller timeout khó hiểu. | Response contract riêng cho invalid. |
| Đếm rejected là persisted. | Báo sai mức độ mất message. | Separate received/invalid/persisted/acked metrics. |
| Chỉ giữ token Claim Check đã hết hạn. | Không replay được original. | Protected replay source và TTL phù hợp. |
| Cleanup xoá mọi evidence trước replay horizon. | Late retry không có lineage/dedupe. | Tombstone/retention phù hợp. |
| Để operator bất kỳ replay cross-tenant. | Lộ hoặc làm thay đổi dữ liệu trái quyền. | Principal-bound authorization/audit. |
| Dùng `quarantineId` làm metrics label. | Cardinality cao, ảnh hưởng monitoring. | Code/outcome/policy labels hữu hạn. |

## 22. Bài tập thực hành

1. **Cơ bản:** dùng `OrderValidationPolicy` để trả `ValidationOutcome` cho một order với amount âm và currency sai. Kiểm tra hai reason codes.
2. **Valid route:** cấu hình `validateAndRouteOrders` và xác minh một input hợp lệ chỉ đi vào `orders.valid`.
3. **Invalid route:** gửi amount bằng 0, xác minh `InMemoryQuarantineStore` có một case và `AcceptedOrderProbe` không nhận message.
4. **Discard thiếu cấu hình:** tạm bỏ `discardChannel` trong môi trường test, quan sát invalid không có case; giải thích tại sao flow này không đạt yêu cầu.
5. **Throw vs discard:** cấu hình `throwExceptionOnRejection`, so sánh exception/error path với discard channel.
6. **Nhiều validation issues:** gửi order thiếu eventId/orderId và amount âm, assert các mã lỗi đã xác định.
7. **Malformed JSON:** dùng inbound adapter phù hợp để gửi raw record sai kiểu, kiểm tra lỗi xảy ra ở deserializer và không đi qua typed Filter.
8. **Raw quarantine:** thiết kế bản ghi raw-error có source, transport reference, error code an toàn và protected payload reference.
9. **Policy version:** thêm `orders-v2` cho một currency mới; lưu kết quả revalidation mà không sửa lịch sử v1.
10. **Duplicate redelivery:** gửi lại cùng `IngressOrder.envelopeId` hai lần, xác minh chỉ một quarantine case.
11. **Identity conflict:** cùng envelope ID với payload khác; kiểm tra conflict được phát hiện và không overwrite.
12. **Tenant scope:** cùng envelopeId ở hai tenants; kiểm tra tạo hai cases độc lập và quyền đọc case riêng biệt.
13. **Source scope:** hai producers dùng cùng local event ID; kiểm tra quarantine key không gộp nhầm.
14. **Persistent store:** thay fake map bằng JDBC repository có unique constraint; test hai transactions lưu cùng case.
15. **Ack window:** mô phỏng DB commit thành công nhưng broker ack thất lạc; redelivery phải dedupe mà không mất case.
16. **Quarantine DB unavailable:** làm write throw; kiểm tra consumer không báo persisted, có bounded retry/error handling phù hợp.
17. **Capacity:** giới hạn số case pending và payload size; kiểm tra overload không silent drop.
18. **Correction:** sửa amount trong bản được phê duyệt rồi gọi `ReplayReviewPolicy.revalidate`; xác minh pass nhưng business handler chưa được gọi tự động.
19. **Authorization:** thử replay case tenant A dưới principal tenant B, xác minh bị từ chối và có audit.
20. **Replay loop:** gửi lại original invalid ba lần không sửa; thiết kế trạng thái `STILL_INVALID` và giới hạn attempts.
21. **Gateway:** tạo contract `ValidationResponse` cho invalid, bảo đảm caller không chờ reply vô hạn khi Filter discard.
22. **Splitter/Aggregator:** một batch có child I-2 invalid; gửi rejection outcome thay vì làm Aggregator thiếu mãi.
23. **Resequencer:** cho sequence #2 invalid; kiểm tra gap và placeholder/recovery theo contract, không phát #3 trước.
24. **Scatter–Gather:** Fraud request invalid; kiểm tra kết luận chung không được CONFIRMED chỉ vì Inventory PASS.
25. **Claim Check:** token bị quarantine lâu hơn claim TTL; thiết kế protected replay source và test expired claim.
26. **Metrics:** đếm received, invalid, persisted, failed và dedupe như các mốc khác nhau; không gắn eventId làm metric label.
27. **Security:** che customerEmail trong logs, hạn chế đọc original payload bằng quyền tenant/operator.
28. **Retention:** cleanup case đã xử lý theo policy, vẫn giữ metadata tối thiểu đủ chống replay trùng khi được phép.
29. **System test:** restart consumer giữa validation và quarantine write, rồi giữa quarantine commit và ack; xác minh recovery đúng.
30. **Runbook:** viết checklist khi invalid message không có case, từ adapter đến discardChannel, DB, retention và quyền review.

### Tiêu chí hoàn thành

Một implementation đạt mục tiêu khi:

- Invalid typed message **không** tới business handler, nhưng **có đường cách ly và truy nguyên rõ**.
- Reason codes và policy version được lưu trong outcome/case, không phải chỉ boolean.
- Malformed raw data có adapter error route riêng, không bị nhầm rằng Filter đã xử lý.
- Quarantine persisted và ingress ack có order/delivery semantics được kiểm thử.
- Redelivery cùng trusted event identity không nhân đôi cases; conflicting payload không bị ghi đè im lặng.
- Replay có quyền, correction/version, revalidation, audit, idempotency và giới hạn.
- Data minimization, retention, encryption, tenant isolation và logs an toàn được xác định.
- Unit/integration/adapter tests kiểm tra đúng ranh giới cần tin cậy.

## 23. Câu hỏi tự kiểm tra

**Câu 1:** Message Filter trả false nhưng không có discard channel. Điều gì có thể xảy ra?

Message bị loại khỏi luồng nghiệp vụ mà không có quarantine record. Nếu hệ thống bắt buộc lưu invalid, đây là lỗi thiết kế cần cấu hình discard route và kiểm thử.

**Câu 2:** Quarantine khác DLQ thế nào?

Quarantine là **một quy trình cách ly, phân loại, điều tra và replay** theo policy. DLQ thường là nơi giữ record sau lỗi xử lý/transport; DLQ có thể làm storage cho quarantine nếu có đủ metadata, quyền, retention và workflow.

**Câu 3:** JSON sai kiểu khiến inbound adapter không deserialize được. Filter có nhận được typed `OrderSubmitted` không?

**Không.** Lỗi xảy ra trước Filter. Cần error handling tại adapter/deserializer hoặc raw-error route.

**Câu 4:** Invalid message có nên bị ném exception luôn không?

**Không bắt buộc.** Business validation false có thể là một kết quả phân luồng bình thường: tạo outcome có issues rồi gửi qua discardChannel. Technical errors là chuyện khác.

**Câu 5:** Vì sao chỉ lưu boolean valid/invalid là chưa đủ?

Không có reason codes, field paths và policy version để truy nguyên, sửa lỗi hoặc revalidate có kiểm soát.

**Câu 6:** `MessageChannel.send()` trả true có chứng minh quarantine đã lưu bền không?

**Không mặc định.** Channel có thể chỉ accepted/dispatch message. Cần dựa vào commit/ack semantics của store hoặc durable queue.

**Câu 7:** Broker đã giao message invalid hai lần. Có nên tạo hai quarantine cases không?

Thường không nếu đó là **cùng logical input**: nên dùng stable ingress identity để dedupe. Nhưng phải phát hiện nếu cùng key mang payload khác.

**Câu 8:** Cùng eventId nhưng hai tenants khác nhau có phải cùng quarantine case không?

**Không.** Quarantine key cần scope theo trusted tenant/source/identity và được kiểm tra quyền.

**Câu 9:** Có thể lấy tenantId trong invalid JSON làm scope đáng tin không?

**Không.** Tenant phải đến từ authentication/trusted ingress context và được đối chiếu với payload nếu cần.

**Câu 10:** Quarantine DB ghi lỗi, nhưng consumer vẫn ack broker. Rủi ro gì?

Message có thể biến mất khỏi cả business processing và quarantine. Cần retry/backpressure/fallback có kiểm soát và ack sau durable handoff.

**Câu 11:** Khi replay, có thể gọi trực tiếp business handler mà bỏ qua validation không?

Không theo quy trình mặc định. Phải review, xác thực/ủy quyền, sửa dữ liệu hoặc policy theo version, revalidate rồi dispatch có audit/idempotency.

**Câu 12:** Nếu message invalid được replay không sửa gì, retry vô hạn có giúp không?

Thường không với lỗi deterministic. Cần correction hoặc rule change được phê duyệt; retry vô hạn chỉ tạo poison loop.

**Câu 13:** Một policy mới chấp nhận input cũ từng bị quarantine; có thể xóa lịch sử lý do cũ không?

Không nên. Giữ policy version và outcome cũ; thêm revalidation attempt mới với lineage.

**Câu 14:** Filter bỏ child #2 của Splitter, Aggregator chờ đủ ba. Rủi ro nào?

Aggregator có thể chờ vô hạn. Cần rejection outcome/placeholder hoặc release/timeout policy rõ, không coi child bị loại là thành công.

**Câu 15:** Resequencer nhận #1, #3, còn #2 bị quarantine. Có được phát #3 trước #2 không?

Không nếu ordering contract yêu cầu đủ trình tự. Cần gap/placeholder/recovery hoặc chính sách partial được phê duyệt.

**Câu 16:** Gateway request bị Filter discard. Caller có chắc nhận một kết quả rejected không?

Không. Discard channel không tự trả reply cho Gateway; cần response/error contract phù hợp để tránh chờ timeout.

**Câu 17:** Quarantine chỉ giữ claim ID, trong lúc review claim đã hết hạn. Có thể tự lấy lại original không?

Không. Cần protected replay source hợp lệ hoặc trả trạng thái không khôi phục; không tự đoán payload.

**Câu 18:** Một invalid message có technical store error. Có nên đánh dấu nó là business valid để tránh backlog?

**Không.** Đó là fail-open nguy hiểm. Xử lý lỗi store bằng retry/fallback/stop intake phù hợp, không thay đổi validation outcome.

**Câu 19:** Tại sao không đưa `quarantineId` vào Prometheus metric labels?

Đó là giá trị có cardinality rất cao, làm tăng chi phí và tải monitoring. Dùng outcome/reason/policy labels hữu hạn, còn ID cụ thể ở log/audit.

**Câu 20:** Một message đã được quarantine có nghĩa nghiệp vụ đã xử lý xong chưa?

Chưa. Quarantine chỉ xác nhận một dạng tiếp nhận/cách ly theo contract. Revalidation, business acceptance và business completion là những mốc khác nhau.

## 24. Kết luận

**Định tuyến invalid message sang quarantine** là cách bảo vệ business flow mà vẫn giữ khả năng **quan sát, điều tra và phục hồi dữ liệu**. Với Spring Integration, mô hình rõ ràng là **Validation Transformer tạo `ValidationOutcome` → Message Filter đánh giá valid/invalid → discardChannel gửi invalid sang Quarantine Handler**. Những message không deserialize được cần **đường lỗi ở adapter**, vì typed Filter chưa được gọi.

Một hệ thống đáng tin không dừng ở `filter(false)` hay một channel tên “quarantine”. Nó cần reason codes, policy version, trusted source/tenant metadata, durable storage, idempotent writes, ack/retry đúng thứ tự, quản lý TTL/bảo mật và replay có kiểm soát. Invalid **khác** transient technical failure, business rejection hoặc duplicate redelivery; mỗi loại có hướng xử lý và trách nhiệm rõ ràng.

Trong `SPRING_INTEGRATION_PATTERN`, hãy kiểm thử theo các tầng: **validator unit tests → Spring Integration Filter/discard integration tests → adapter/deserializer error tests → durable store/ack/replay system tests**. Khi kết hợp Router, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway, retry và error channel, luôn trả lời được ba câu: **“Message bị từ chối vì sao?”, “Nó đã được giữ an toàn ở đâu?”, và “Ai có quyền sửa rồi đưa nó trở lại luồng xử lý như thế nào?”**
