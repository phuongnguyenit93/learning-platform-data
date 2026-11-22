# Reject malformed message

## 1. Bài toán: message lỗi không được đi vào nghiệp vụ

Hệ thống xử lý đơn hàng nhận một JSON event từ HTTP hoặc broker. Luồng bình thường:

~~~text
OrderSubmitted
  → Inbound Adapter
  → Validate
  → Router
  → Transformer
  → Splitter
  → Inventory / Pricing
  → Aggregator
  → OrderAccepted
~~~

Nhưng producer có thể gửi dữ liệu thiếu trường bắt buộc, sai kiểu, sai schema hoặc vượt kích thước cho phép:

~~~json
{
  "schemaVersion": "1",
  "eventId": "EV-501",
  "tenantId": "tenant-a",
  "orderId": "",
  "revision": 2,
  "items": [
    {"sku": "", "quantity": -3}
  ]
}
~~~

Nếu Filter bỏ qua validation, dữ liệu có thể đi sâu vào Router hoặc Transformer rồi mới ném `NullPointerException`, vào retry nhiều lần, giữ Aggregator chờ một result không bao giờ tới, hoặc tệ hơn tạo side effect từ một đơn hàng không hợp lệ.

**Reject malformed message** nghĩa là **phát hiện sớm dữ liệu không tuân thủ hợp đồng, từ chối có chủ đích và đưa vào đường xử lý lỗi đúng ngữ nghĩa**, thay vì cho dữ liệu sai tiếp tục đi qua business flow. Từ chối có thể là trả HTTP 400/422, một rejection result, hoặc một DLQ/quarantine record; không phải lúc nào cũng là âm thầm drop.

~~~mermaid
flowchart TD
    IN["Incoming bytes / message"] --> PARSE{"Decode + schema check"}
    PARSE -->|"JSON/schema sai"| RAW["Ingress rejection / quarantine"]
    PARSE -->|"OK"| VAL{"Validate payload + metadata"}
    VAL -->|"Malformed / policy invalid"| REJ["Reject path: reason code + safe context"]
    VAL -->|"Well-formed"| ROUTE["Router / Transformer / business handler"]
    ROUTE --> OUT["Business outcome"]
    RAW --> OBS["Metrics + audit + delivery decision"]
    REJ --> OBS
~~~

Bài thuộc chương **Message filter và validation** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns bằng Spring Integration, kết hợp **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát các nhánh xử lý.

**Sau bài học**, bạn sẽ biết phân loại lỗi input, chọn nơi validation, cấu hình Spring Integration Filter và discard/error flow, bảo toàn correlation khi reject, xử lý HTTP/broker phù hợp, viết validation Java, và kiểm thử malformed messages không gây retry vô tận hoặc business side effect.

## 2. Malformed khác business rejection và transient error

Không phải message nào “không xử lý được” cũng là malformed.

| Nhóm | Ví dụ | Chính sách điển hình |
|---|---|---|
| **Malformed bytes** | JSON thiếu dấu ngoặc, encoding không hợp lệ | Reject tại ingress trước khi dựng `Message<?>` |
| **Schema/type invalid** | `quantity="abc"` thay vì integer, thiếu `eventId` bắt buộc | Reject vì vi phạm contract |
| **Field constraints invalid** | `quantity=-3`, `items=[]`, `sku=""` | Reject theo Bean Validation/business input policy |
| **Unsupported schema version** | Consumer hỗ trợ v1/v2, nhận v9 | Reject/quarantine có mã lỗi riêng |
| **Untrusted identity/header** | Tenant từ payload trái với principal | Authorization/security rejection, không coi là lỗi mạng |
| **Valid request nhưng bị business rule từ chối** | Hàng hết, credit limit không đủ | Trả **business outcome** như `OUT_OF_STOCK`; không nhất thiết “malformed” |
| **Transient infrastructure error** | Database timeout, broker unavailable, HTTP 503 | Retry có giới hạn/backoff |
| **Unknown remote outcome** | HTTP timeout sau khi remote có thể đã commit | Reconciliation/idempotency, không tự coi malformed |

Nếu đưa mọi lỗi vào cùng một exception/retry path, một malformed JSON không bao giờ sửa được sẽ bị phát lại liên tục. Ngược lại, nếu xem mọi exception là invalid input và ACK/drop, một lỗi database tạm thời có thể làm **mất công việc hợp lệ**.

**Nguyên tắc:** phân loại theo khả năng sửa chữa và trách nhiệm: producer phải sửa dữ liệu hay consumer cần retry dependency? Sự khác biệt đó quyết định reject, retry, DLQ, ACK và status trả Gateway.

## 3. Có ba lớp validation trước khi vào business handler

| Lớp | Kiểm tra | Vị trí |
|---|---|---|
| **Transport & decoding** | Kích thước bytes, encoding, JSON syntax, JSON type, Content-Type | HTTP controller, message converter, deserializer, inbound adapter |
| **Contract/schema** | Version, trường bắt buộc, enum, nested object, field format, bounds | Validator trước Router/Transformer |
| **Business admissibility** | Quyền tenant, trạng thái đơn, giới hạn nghiệp vụ, duplicate conflict | Boundary service/domain validation |

Các lớp có thể chồng lắp nhưng không giống nhau. Một JSON có syntax đúng vẫn có thể thiếu `items`; một `OrderCommand` đúng cấu trúc vẫn có thể yêu cầu cập nhật đơn thuộc tenant khác; một order hợp lệ vẫn có thể không đủ tồn kho.

**Filter chỉ nhìn thấy message đã được tạo thành công.** Nếu Jackson/Avro/Protobuf deserialization thất bại **trước khi adapter phát Spring Message**, Filter chưa hề được gọi. Phải thiết kế **ingress error handling** riêng; không thể tuyên bố “đã có Filter nên mọi malformed JSON sẽ vào discardChannel”.

## 4. Hợp đồng quyết định cho mọi message đầu vào

Một flow nên kết thúc mỗi input trong một trong các trạng thái có ngữ nghĩa rõ:

1. **ACCEPTED:** đủ điều kiện đi vào pipeline xử lý nghiệp vụ.
2. **REJECTED_PERMANENT:** input vi phạm contract hoặc quyền, không thể sửa bằng retry cùng payload.
3. **RETRYABLE_FAILURE:** chưa quyết định được do lỗi hạ tầng tạm thời; không được ACK như thành công nếu chưa có durable recovery.

Có thể có **BUSINESS_REJECTED** sau validation, ví dụ không đủ tồn kho; kết quả này khác `MALFORMED_MESSAGE`.

~~~text
eventId=EV-501
validation=REJECTED_PERMANENT
reasonCode=INVALID_QUANTITY
field=items[0].quantity
retryable=false
~~~

Reason code nên **ổn định, có whitelist** và phù hợp contract; không để exception message raw từ JDBC/JSON parser trở thành nội dung công khai. API có thể trả chi tiết field cho caller đã được xác thực, còn logs/quarantine có mức dữ liệu riêng.

## 5. Vì sao reject sớm giảm lỗi lan truyền?

~~~mermaid
flowchart LR
    A["Malformed order"] --> F{"Ingress Filter"}
    F -->|"Reject"| R["Safe rejection"]
    F -->|"Accept"| T["Transformer"]
    T --> S["Splitter"]
    S --> W["Workers"]
    W --> G["Aggregator"]
    G --> O["Order result"]
~~~

Nếu invalid message được nhận từ đầu:

- Router có thể chọn route dựa trên field null hoặc header giả mạo.
- Transformer ném exception với thông điệp khó truy vết.
- Splitter tạo một số child rồi mới thấy một item lỗi.
- Worker có thể tạo side effect từ những child đã được phát.
- Aggregator không nhận đủ expected outcomes.
- Gateway timeout, dù nguyên nhân thật là dữ liệu đầu vào không hợp lệ.
- Broker redeliver liên tục vì handler ném exception không được phân loại.

Vì vậy ưu tiên validate **những bất biến có thể kiểm tra từ payload gốc trước bất kỳ side effect hoặc fan-out nào**. Không nhất thiết kiểm tra mọi nghiệp vụ đắt đỏ ở Filter; nhưng những điều kiện cơ bản như schema, ID, kiểu dữ liệu, giới hạn danh sách và required fields phải được kiểm tra sớm.

## 6. Java 17+: định nghĩa input contract bằng record

Ví dụ dùng Bean Validation với Jakarta API (Spring Framework 6/Boot 3+):

~~~java
record OrderLine(
    @NotBlank String sku,
    @Positive int quantity
) {}

record OrderCommand(
    @NotBlank String schemaVersion,
    @NotBlank String eventId,
    @NotBlank String tenantId,
    @NotBlank String orderId,
    @Positive int revision,
    @NotNull @Size(min = 1, max = 100)
    List<@Valid OrderLine> items
) {}
~~~

Các annotation cần import `jakarta.validation.Valid` và các constraint trong `jakarta.validation.constraints`. Tùy phiên bản Spring cũ hơn, package tương ứng có thể khác; hãy giữ dependency/provider Bean Validation đúng phiên bản dự án.

| Annotation | Điều kiện |
|---|---|
| `@NotBlank` | String không null, không rỗng/toàn whitespace |
| `@Positive` | Số lớn hơn 0 |
| `@NotNull` | Field phải có giá trị khác null |
| `@Size(min=1,max=100)` | Số line items trong giới hạn |
| `@Valid` | Áp validation xuống object con |

**Bẫy:** Java record có primitive `int`. Một JSON thiếu `quantity` có thể được deserializer gán giá trị mặc định `0` tùy cấu hình; `@Positive` sẽ bắt được trường hợp đó, nhưng nếu muốn phân biệt **missing** với **explicit zero**, hãy dùng `Integer` cùng `@NotNull` và cấu hình deserializer/schema phù hợp.

**Các annotation không tự được áp dụng cho mọi Spring Integration message.** Phải có Validator được gọi thật tại endpoint hoặc cơ chế method validation đã được cấu hình; chỉ thêm `@Valid` vào DTO chưa bảo đảm message bị reject.

## 7. Bean Validation trong một service có thể kiểm thử độc lập

Một validation service:

~~~java
@Service
class OrderValidationService {
    private final Validator validator;

    OrderValidationService(Validator validator) {
        this.validator = validator;
    }

    boolean isWellFormed(OrderCommand command) {
        if (command == null) {
            return false;
        }
        return validator.validate(command).isEmpty();
    }
}
~~~

`Validator` là `jakarta.validation.Validator`, được ứng dụng cung cấp qua provider như Hibernate Validator (ví dụ Spring Boot validation starter). Predicate này **thuần, nhanh và deterministic** nếu constraints không truy vấn hệ thống ngoài.

Với production, validation có thể cần thêm:

- `eventId` phải có format được công bố.
- Tổng số bytes và số items được giới hạn từ adapter.
- `orderId` không được trùng/không phù hợp tenant theo business policy.
- `sku` có chiều dài tối đa; `@NotBlank` một mình chưa chặn string hàng megabytes.
- Kiểm tra `items` không có duplicate line ID nếu hợp đồng yêu cầu.
- Schema version và allowed fields từ wire contract.

**Không đưa một HTTP/DB lookup có thể timeout vào predicate rồi kết luận mọi lỗi lookup là malformed.** Dependency outage là `RETRYABLE_FAILURE`, không phải input invalid.

## 8. Java DSL: Filter chuyển message sai sang discard channel

Với một `OrderCommand` đã deserialize thành công:

~~~java
@Configuration
@EnableIntegration
class OrderValidationFlow {

    @Bean
    IntegrationFlow filterMalformedOrders(
            OrderValidationService validation) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderCommand.class,
                validation::isWellFormed,
                spec -> spec.discardChannel("orders.rejected"))
            .channel("orders.valid")
            .get();
    }
}
~~~

**Ý nghĩa:**

- Predicate trả `true` → message tiếp tục qua `orders.valid`.
- Predicate trả `false` → message được đưa tới `orders.rejected` theo cấu hình discard channel.
- Không có lý do để gửi malformed payload sang Router hoặc business handler.

Đoạn code là mẫu Java DSL, cần import và các channel/consumer phù hợp với phiên bản Spring Integration đang sử dụng. `orders.rejected` phải có subscriber đủ khả năng lưu/quản lý rejection; đừng tạo discard channel mà không có nơi nhận kết quả.

Đây là **đường business rejection chủ động**, không mặc nhiên là `ErrorMessage` trong `errorChannel`. Nếu bạn cần ném exception thay vì gửi discard, xem phương án riêng ở mục 11.

## 9. `@Filter` annotation: cách viết tương đương

Có thể dùng annotation endpoint:

~~~java
@MessageEndpoint
class OrderMessageFilter {
    private final OrderValidationService validation;

    OrderMessageFilter(OrderValidationService validation) {
        this.validation = validation;
    }

    @Filter(
        inputChannel = "orders.filter.input",
        outputChannel = "orders.valid",
        discardChannel = "orders.rejected")
    public boolean accept(OrderCommand command) {
        return validation.isWellFormed(command);
    }
}
~~~

Ví dụ này dùng **một input channel khác** so với Java DSL ở mục 8. Chúng là **hai phương án độc lập**, không đăng ký cả hai cho cùng dữ liệu nếu không có chủ đích về dispatch/competing consumers.

Predicate phải trả Boolean đúng ngữ nghĩa. `false` là **rejection được dự kiến**, khác exception do lỗi hạ tầng trong method. Khi validation cần trả danh sách mã lỗi, một Boolean không đủ; có thể sử dụng validator/service làm bước tạo `ValidationResult` trước Filter hoặc để rejection handler chạy validation deterministic lần nữa.

## 10. Các cách phản ứng khi Filter reject

| Cấu hình/chính sách | Hành vi mong muốn | Cần thận trọng |
|---|---|---|
| Không có discard channel, không throw | Message bị dừng tại Filter | Có thể **mất thông tin** nếu không có metric/audit |
| `discardChannel` | Gửi message bị reject sang flow riêng | Flow đó phải thực sự xử lý và lưu/trả kết quả |
| `throwExceptionOnRejection(true)` | Ném `MessageRejectedException` với message không hợp lệ | Caller/container có thể retry nếu không phân loại |
| Service Activator validation | Có thể ném exception cụ thể kèm reason | Cần error handling và mapping đúng |
| Trả `RejectedOrder` dạng payload | Tạo response có cấu trúc thay vì exception | Không gửi rejection như một `OrderAccepted` |

Đừng cấu hình throw và discard cùng lúc rồi **tự giả định** hai đường đều nhận một bản. Chính xác thứ tự/xử lý phụ thuộc cơ chế Filter/configuration và cần kiểm thử; để học và vận hành dễ hơn, hãy chọn **một chiến lược chính rõ ràng** rồi xử lý từ đó.

**Discard không đồng nghĩa broker DLQ.** Discard channel là khái niệm **trong Spring Integration flow**, còn DLQ là kênh/đích lưu thất bại của transport; muốn đẩy ra DLQ phải cấu hình publisher/handler tương ứng.

## 11. Java DSL: throw exception khi caller cần fail-fast

Nếu contract yêu cầu caller nhận lỗi ngay:

~~~java
@Bean
IntegrationFlow failFastOrderFilter(
        OrderValidationService validation) {
    return IntegrationFlow.from("orders.failfast.in")
        .filter(OrderCommand.class,
            validation::isWellFormed,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("orders.failfast.valid")
        .get();
}
~~~

Một `false` sẽ gây `MessageRejectedException` tại Filter theo cấu hình. Trong flow đồng bộ dùng `DirectChannel`, exception có thể lan ngược về Gateway/HTTP adapter. Nhưng với `ExecutorChannel`, poller hoặc broker listener, nó phát sinh trong **worker/error boundary**, không nhất thiết trở về thread gửi ban đầu.

**Quan trọng:** throw là tín hiệu kỹ thuật, **không tự quyết định status HTTP hoặc broker ACK**. Nếu broker listener mặc định retry mọi exception, malformed event có thể bị xử lý vô hạn. Cần classifier/recoverer cho lỗi input vĩnh viễn, khác với retryable failures.

## 12. Làm sao giữ mã lỗi cụ thể khi predicate chỉ trả Boolean?

Predicate đơn giản:

~~~java
boolean isWellFormed(OrderCommand command)
~~~

chỉ trả `true/false`. Để biết tại sao message bị reject, sử dụng một dạng kết quả có cấu trúc:

~~~java
record ValidationIssue(
    String fieldPath,
    String reasonCode
) {}

record ValidationResult(
    boolean valid,
    List<ValidationIssue> issues
) {
    static ValidationResult accepted() {
        return new ValidationResult(true, List.of());
    }

    static ValidationResult rejected(List<ValidationIssue> issues) {
        return new ValidationResult(false, List.copyOf(issues));
    }
}
~~~

Mỗi issue chứa mã lỗi **ổn định** như `MISSING_ORDER_ID`, `INVALID_ITEM_QUANTITY`, `TOO_MANY_ITEMS`, không phải một raw exception message có stack trace. Một validator có thể chuyển `ConstraintViolation<OrderCommand>` thành `ValidationIssue` bằng cách ánh xạ tên constraint/field path sang catalog mã lỗi của API.

**Không phản chiếu tùy ý giá trị trường invalid ra response/log.** Những giá trị ấy có thể chứa PII hoặc payload được tạo với mục tiêu tấn công log.

## 13. Tạo rejection envelope có thể audit, không phải exception raw

Một record trả về đường lỗi:

~~~java
record RejectedOrder(
    String eventId,
    String orderId,
    String correlationKey,
    String outcome,
    List<ValidationIssue> issues,
    boolean retryable
) {}
~~~

Ví dụ:

~~~json
{
  "eventId": "EV-501",
  "orderId": null,
  "correlationKey": "batch-Q-501",
  "outcome": "REJECTED_PERMANENT",
  "issues": [
    {"fieldPath": "orderId", "reasonCode": "MISSING_ORDER_ID"},
    {"fieldPath": "items[0].sku", "reasonCode": "MISSING_SKU"},
    {"fieldPath": "items[0].quantity", "reasonCode": "INVALID_QUANTITY"}
  ],
  "retryable": false
}
~~~

Đối với malformed raw bytes, có thể **không có eventId hoặc correlationKey**. Không tự tạo một key `UNKNOWN` chung rồi đưa nhiều rejected messages vào cùng aggregation group. Dùng **transport message identity/quarantine record ID** cho audit; correlation business chỉ có khi đủ dữ liệu đáng tin.

Quy tắc logging: giới hạn số issues, độ dài field path và payload được giữ; mã hóa/che giấu dữ liệu nhạy cảm; log theo cấu trúc có quyền truy cập và retention rõ.

## 14. Rejection handler: lưu an toàn trước khi kết thúc delivery

Một Service Activator cho discard channel:

~~~java
@MessageEndpoint
class RejectedOrderHandler {
    private final RejectionStore rejectionStore;

    RejectedOrderHandler(RejectionStore rejectionStore) {
        this.rejectionStore = rejectionStore;
    }

    @ServiceActivator(inputChannel = "orders.rejected")
    public void handleRejected(Message<OrderCommand> message) {
        // Store sẽ kiểm tra lại deterministic validator,
        // tạo reason codes và lưu metadata đã được sanitize.
        rejectionStore.recordMalformedOrder(message);
    }
}
~~~

`RejectionStore` là interface ứng dụng **tự triển khai**, không phải API mặc định. Nếu nó ghi vào DB hoặc đẩy sang DLQ, cần chắc chắn record đã được lưu hoặc durable responsibility đã chuyển trước khi coi input xử lý xong.

**Không đưa original payload chứa credential/PII vào DLQ công khai** mà không có kiểm soát. Đặt giới hạn dung lượng/quota cho quarantine; một producer lỗi có thể gửi hàng triệu malformed messages và làm đầy storage.

**Không để discard flow lặp vô hạn về input Filter**, trừ khi có một bước sửa dữ liệu có contract và được kiểm soát. Retry cùng malformed payload không làm nó tự trở nên hợp lệ.

## 15. Lỗi JSON syntax xảy ra trước Filter

Một raw message:

~~~text
{"orderId": "O-501", "items": [
~~~

Jackson/JSON decoder có thể ném exception vì chuỗi chưa đóng. Khi đó Spring Integration `filter(OrderCommand.class, ...)` **chưa có `OrderCommand` để kiểm tra**.

Lựa chọn tại ingress:

- HTTP: mapping lỗi parse/deserialization thành response 400 theo API contract.
- Kafka: deserializer/error-handling deserializer và listener recoverer phù hợp với phiên bản adapter.
- AMQP/JMS: message converter, error handler/container và DLQ/quarantine policy.
- File ingest: ghi record lỗi/safe raw reference và chuyển sang thư mục quarantine có retention.

**Không khẳng định message malformed luôn vào `errorChannel`**: với một số adapter, lỗi xảy ra trong conversion trước khi Spring message được publish; xử lý nằm tại container/adapter boundary. Phải kiểm thử lỗi parse bằng **bytes thực**, không chỉ tạo một Java object invalid rồi gửi vào channel.

## 16. Schema version và tiến hóa hợp đồng

Một consumer chấp nhận v1/v2 nhưng nhận:

~~~json
{
  "schemaVersion": "9",
  "eventId": "EV-502",
  "orderId": "O-502",
  "items": [{"sku": "SKU-1", "quantity": 2}]
}
~~~

Đây là **unsupported schema version**, khác `INVALID_QUANTITY`. Chính sách có thể:

1. Reject với `UNSUPPORTED_SCHEMA_VERSION`, nêu versions được hỗ trợ.
2. Quarantine để cập nhật consumer/schema registry có kiểm soát.
3. Route qua converter phiên bản cụ thể **nếu contract hỗ trợ**.

Không đoán rằng một schema mới có cùng ý nghĩa chỉ vì Jackson deserialize được phần lớn fields. Thay đổi semantics của amount/currency, quyền hoặc nullable fields có thể tạo kết quả sai mà code không ném exception.

**Unknown fields** có thể được cho phép để tương thích tiến hóa hoặc bị reject trong strict mode; chọn **có chủ đích** và kiểm thử. Nếu thiếu trường bắt buộc, luôn phát hiện ở schema/validation layer, không dựa vào việc getter trả null ở business handler.

## 17. Validation headers: thông tin vận chuyển và identity

Một message có payload hợp lệ nhưng header không hợp lệ:

~~~text
headers.contentType = "application/octet-stream"
headers.tenantId    = "tenant-b"   // payload thuộc tenant-a
headers.schemaVer   = "2"          // payload schema v1
headers.correlation = very-long-untrusted-string
~~~

Cần phân biệt:

- Headers do **adapter tin cậy** gắn vào sau khi xác thực.
- Headers do **client/producer tự khai**, có thể sai hoặc giả mạo.
- Framework headers như `replyChannel`, `errorChannel`, `MessageHeaders.ID` có semantics nội bộ.

**Không dùng raw tenant header để quyết định quyền hoặc correlation** trước khi xác minh principal/credential. Nếu payload/header mâu thuẫn, reject hoặc áp chính sách canonical từ nguồn đã xác thực; đừng tùy ý chọn một bản.

Giới hạn số lượng/độ dài headers và whitelist tên cho broker mapping. Tránh mang untrusted expression, channel name hoặc bean name vào Router/Control Bus.

## 18. Đặt Filter trước hay sau Transformer và Router?

| Vị trí | Ưu điểm | Rủi ro |
|---|---|---|
| Ngay sau ingress decoding | Chặn malformed sớm, ít side effect | Chưa có đầy đủ dữ liệu enriched để kiểm tra một số business rule |
| Sau canonicalization Transformer | Validate model chuẩn, ít branch khác nhau | Transformer có thể ném exception nếu payload quá sai |
| Trước Router | Router không thấy field null hoặc schema sai | Phải có route rejection rõ |
| Sau Router, trước business handler | Validation riêng cho từng operation | Dễ thiếu nhánh cần validate |
| Sau Splitter | Validate từng child | Có thể đã phát các child khác rồi; Aggregator thiếu member |

**Khuyến nghị phân tầng:** validate **bytes/schema/basic constraints ở ingress**, canonicalize một cách an toàn, validate **domain-specific rules tại đúng service boundary**, và giữ validation trên output/contract nếu cần. Không phải mọi check đều nằm trong duy nhất một Filter.

Tránh một Transformer gọi `value.trim()` trên null rồi mới validate: lỗi sẽ là `NullPointerException` không có reason code. Với field nullable, dùng converter an toàn rồi đưa lỗi vào catalog.

## 19. Validator không được biến lỗi hạ tầng thành malformed

Một anti-pattern:

~~~java
boolean isValid(OrderCommand order) {
    try {
        return inventoryApi.productExists(order.items().get(0).sku());
    } catch (Exception unavailable) {
        return false; // Sai: biến outage thành invalid input.
    }
}
~~~

Nếu Inventory service timeout, `false` khiến một order hợp lệ bị reject vĩnh viễn. Thay vào đó:

- Filter dùng **pure validation** cho shape/format/size/range.
- Bước business validation riêng có thể gọi dependency.
- Timeout/network errors được phân loại `RETRYABLE_FAILURE`.
- Business negative (SKU thực sự không tồn tại) tạo reason `UNKNOWN_SKU` hoặc business rejection **sau khi đã xác minh dependency trả kết quả đáng tin**.

Một exception vì storage/network lỗi không nên được đưa vào discard flow chỉ để tránh retry, và một malformed input cũng không nên bị retry như database outage.

## 20. Filter khác Router, Transformer và Bean Validation

| Thành phần | Câu hỏi chính | Đầu ra |
|---|---|---|
| **Message Filter** | Có cho message này tiếp tục không? | Forward hoặc reject/discard/exception |
| **Content-Based Router** | Message hợp lệ nên đến nhánh nào? | Một/nhiều channel theo policy |
| **Transformer** | Payload cần biểu diễn bằng kiểu gì? | Payload/message khác |
| **Bean Validation** | Object có vi phạm constraints không? | Constraint violations |
| **Service Activator** | Thực thi nghiệp vụ gì? | Reply/side effect hoặc exception |
| **Aggregator** | Những message nào cùng group và khi nào đủ? | Kết quả tổng hợp |

Filter không phải một **JSON parser**, **schema registry**, **transaction manager**, hoặc **authorization framework**. Nó có thể gọi một predicate xác định điều kiện nhận, nhưng các trách nhiệm khác cần được tổ chức ở đúng nơi.

**Một request bị reject không tự được chuyển thành response.** Muốn Gateway trả lý do từ chối phải có đường reply hoặc exception mapper phù hợp. Muốn broker biết permanent failure phải có container recoverer/DLQ/ACK policy.

## 21. Gateway: drop message có thể biến validation error thành timeout

Một Gateway đồng bộ mong **một reply**:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.gateway.in")
interface OrderGateway {
    OrderAccepted submit(OrderCommand command);
}
~~~

Nếu Filter trả `false` rồi **âm thầm drop**, không có reply cho caller. Caller có thể chờ tới `replyTimeout` và nhận timeout, dù nguyên nhân thật chỉ là `orderId` rỗng.

Hai cách rõ ràng:

**A — ném exception (fail fast):**

~~~text
Gateway request
  → Filter throwExceptionOnRejection=true
  → MessageRejectedException
  → Controller/HTTP error mapper
  → 400/422 + validation reasonCode
~~~

**B — trả typed rejection:**

~~~text
Gateway request
  → validation decision
  → invalid: OrderRejected(eventId, issues)
  → valid: OrderAccepted(orderId)
  → Gateway nhận một OrderDecision
~~~

Cách B cần bước tạo rejection reply **thực sự** và một return type phù hợp, không phải mặc nhiên có chỉ vì Filter có `discardChannel`. Với async Gateway, cần xác minh reply headers/channel và timeout policy. Không trả `SUCCESS` giả chỉ để tránh timeout.

## 22. Typed rejection result cho request–reply

Một contract Java:

~~~java
sealed interface OrderDecision
    permits OrderAccepted, OrderRejectedDecision {}

record OrderAccepted(
    String eventId,
    String orderId
) implements OrderDecision {}

record OrderRejectedDecision(
    String eventId,
    String reasonCode,
    List<ValidationIssue> issues
) implements OrderDecision {}
~~~

Gateway:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.decide")
interface DecisionGateway {
    OrderDecision decide(OrderCommand command);
}
~~~

Đây là **hợp đồng ứng dụng**, không phải API tự sinh từ `.filter()`. Một decision service/Transformer hoặc rejection reply flow cần tạo `OrderRejectedDecision` với header reply phù hợp. Khi JSON syntax sai trước lúc tạo DTO, controller hoặc adapter phải map lỗi parse riêng vào cùng catalog reason codes.

## 23. Broker: một malformed message có thể trở thành poison pill

Kafka/AMQP consumer nhận:

~~~text
eventId=EV-900
quantity="many"    // sai kiểu, không phải integer
~~~

Redelivery cùng bytes không tự làm message đúng hơn. Nếu container retry vô hạn, partition/queue có thể bị **kẹt bởi poison pill**, logging tăng mạnh và messages hợp lệ phía sau bị trì hoãn.

~~~mermaid
flowchart TD
    IN["Broker message"] --> DECODE{"Deserialize + validate"}
    DECODE -->|"Malformed vĩnh viễn"| D["Durable DLQ / quarantine"]
    DECODE -->|"Valid"| WORK["Business handler"]
    WORK -->|"Success"| ACK["ACK / commit offset"]
    WORK -->|"Transient failure"| RETRY["Bounded retry + backoff"]
    RETRY --> WORK
    D --> DUR{"DLQ đã lưu chắc chắn?"}
    DUR -->|"Có"| ACK
    DUR -->|"Chưa"| RETAIN["Giữ trách nhiệm recovery; không mất source"]
~~~

Đây là **workflow khái niệm**: Kafka, AMQP, JMS có những transaction/ACK semantics riêng. “Publish DLQ rồi commit source” không mặc nhiên là atomic. Khi DLQ unavailable, cần retry/quarantine durable phù hợp; không ACK im lặng và đánh mất input.

**Không giả định `MessageRejectedException` mặc nhiên không retry**. Container error classifier/recoverer phải phân biệt permanent validation errors với transient exceptions.

## 24. Discard channel, error channel và DLQ là các ranh giới khác nhau

| Khái niệm | Bối cảnh | Trách nhiệm |
|---|---|---|
| `discardChannel` | Spring Integration Filter | Nhận message bị predicate từ chối |
| `errorChannel` | Spring Integration error messaging | Nhận `ErrorMessage` khi lỗi thuộc boundary có error handling |
| Broker DLQ/DLT | Kafka/AMQP/JMS | Lưu message lỗi ngoài luồng tiêu thụ chính |
| Quarantine database/object store | Ứng dụng | Lưu metadata/reason và safe raw reference để review/replay |
| Rejection reply | Gateway/HTTP | Thông báo caller để sửa input |

Một discard handler có thể publish tới DLQ, nhưng **cấu hình `discardChannel("orders.rejected")` chưa hề tạo DLQ**. Lỗi parse trong message converter có thể đi vào adapter/container recoverer **mà không qua Filter**.

Quarantine nên lưu:

~~~text
quarantineId, sourceSystem, receivedAt
transportReference, schemaVersion (nếu có)
eventId (nếu đủ tin cậy), reasonCode
sanitizedIssues, payloadHashOrProtectedReference
reviewStatus, replayPolicy
~~~

Giới hạn payload, quyền truy cập, encryption, retention và quota. Không đưa raw body chứa PII/credentials tới một DLQ công khai.

## 25. Permanent vs retryable: phân loại trước khi ACK

| Outcome | Có retry tự động cùng bytes không? | Hành động |
|---|---|---|
| Malformed JSON | Không | Reject ở decoder, quarantine |
| Thiếu required field | Không | Field reason code |
| Unsupported schema | Không retry nóng | Quarantine/migration khi có converter |
| Unauthorized tenant | Không | Security rejection và audit |
| Database timeout | Có thể | Bounded retry, transaction mới |
| Remote 503 | Có điều kiện | Backoff, deadline, circuit breaker |
| HTTP timeout, unknown side effect | Không retry mù | Reconcile/idempotency |
| Duplicate completed event | Không chạy lại side effect | ACK/cached result |

**Message Filter chỉ là một nơi có thể từ chối**. Nếu validator của Filter tự gọi dependency rồi gặp network exception, đó không phải bằng chứng payload malformed. Tách validation thuần với checks cần I/O để không gắn sai `retryable=false`.

Reprocess DLQ sau khi producer sửa schema **là workflow có kiểm soát**, không phải retry nóng cùng payload lỗi vô hạn.

## 26. Filter sau Splitter có thể khiến Aggregator chờ mãi

Ví dụ:

~~~text
Order O-101 → Splitter → L1, L2, L3

L1 valid → Inventory reply
L2 invalid quantity → Filter drops
L3 valid → Inventory reply

Aggregator expectedMembers={L1,L2,L3}
Aggregator receivedMembers={L1,L3}
→ group thiếu L2
~~~

~~~mermaid
flowchart TD
    S["Splitter: L1,L2,L3"] --> F{"Per-line Filter"}
    F -->|"L1,L3 valid"| W["Workers"]
    F -->|"L2 invalid"| REJ["Line rejection outcome"]
    W --> AG["Aggregator"]
    REJ --> AG
    AG --> O["OrderResult / PARTIAL / FAILED"]
~~~

Hai phương án:

1. **Validate toàn bộ collection trước Splitter:** nếu có một line malformed thì reject cả request, không phát bất kỳ child nào.
2. **Per-item rejection outcome:** nếu partial processing hợp lệ, chuyển lỗi thành `LineOutcome(success=false, reasonCode="INVALID_QUANTITY")` với đúng **group ID, member ID và sequence metadata** để Aggregator kết luận có chủ đích.

Không tùy ý giảm expectedMembers từ 3 xuống 2 rồi báo thành công. Một member không hợp lệ phải được biểu diễn bằng **outcome/skip policy rõ ràng** hoặc fail whole batch.

## 27. Java: child rejection cần mang đúng correlation

~~~java
record LineOutcome(
    String orderGroupId,
    String lineId,
    boolean success,
    String reasonCode
) {}

LineOutcome invalidLine = new LineOutcome(
    "tenant-a|O-101|rev-2",
    "L2",
    false,
    "INVALID_QUANTITY");
~~~

Khi Aggregator nhận outcome này:

- `orderGroupId` phải chỉ đúng một logical processing group.
- `lineId` phải thuộc **manifest member IDs** dự kiến.
- Duplicate không được xem là member mới.
- Một failure outcome là **kết luận cho một member**, không phải exception làm mất reply.
- Final summary phải là `FAILED`/`PARTIAL` nếu bất kỳ member cần thiết nào không thành công.

Nếu toàn request bị reject **trước Splitter**, trả một rejection result trực tiếp thường tốt hơn việc tạo Aggregator group giả chỉ để gom lỗi.

## 28. Malformed message và idempotency key

Một message bị reject đôi khi có event ID hợp lệ, nhưng cũng có thể thiếu hoặc bị sửa:

~~~text
Message 1: eventId=EV-501, orderId missing
Message 2: eventId=EV-501, orderId=O-502, payload changed
~~~

Nếu record duplicate của message 1 được đánh dấu là **business completed**, lần producer sửa rồi gửi lại có thể bị chặn. Nhưng nếu không lưu gì, cùng malformed bytes redeliver liên tục lại có thể gây nhiễu. Cần **hai loại record** có contract:

- **Quarantine/rejection record:** theo dõi input bị lỗi và việc sửa/replay.
- **Business idempotency record:** theo dõi logical operation đã được xử lý.

Same key + different payload cần fingerprint/validation/version policy, không âm thầm chấp nhận. Producer phải xác định bản đã sửa dùng **event revision mới** hay cùng logical event theo quy ước cho phép. Reprocess cần audit và bảo vệ khỏi double side effect.

Khi không lấy được eventId đáng tin từ raw bytes, dùng một **transport/quarantine reference** riêng để truy vết, không gom tất cả vào key `UNKNOWN`.

## 29. Giới hạn tài nguyên ngay cả trước Filter

Payload có JSON syntax đúng nhưng quá lớn:

~~~text
Content-Length: 120 MiB
items: 1_000_000 entries
nestingDepth: 100_000
header businessKey: 10 MiB string
~~~

Filter chạy **sau deserialize** nên nó không thể bảo vệ khỏi mọi chi phí parser. Cần:

- Max request/message bytes ở adapter.
- Parser giới hạn depth, token count và field length.
- Max array length và số line items.
- Timeout/concurrency quota cho parse/validation.
- Tránh regex validation có độ phức tạp cao từ untrusted input.
- Không log raw payload lớn hoặc giữ vô hạn các bản bị reject.

Giới hạn trước **Splitter fan-out** để một message không tạo hàng triệu tasks. Chặn input quá lớn sớm thường rẻ hơn kiểm tra sau khi tạo toàn bộ object graph.

## 30. Security: reasonCode hữu ích mà không rò PII

Một malformed message có thể chứa credentials, token, email hay payload cố tình chèn log. Không copy nguyên giá trị vào error body:

~~~text
Sai:
  reason="Invalid payment.cardNumber=4111...; Bearer secret..."

Đúng:
  reasonCode=INVALID_CARD_FORMAT
  fieldPath=payment.cardNumber
  eventId=EV-501
~~~

Validation không thay parameterized SQL, authorization hay output encoding. Nhưng nó là chốt đầu tiên loại contract-violating input.

Trong multi-tenant, xác minh tenant từ principal/credential đáng tin; mismatch với payload/header phải bị reject theo security policy. Không dùng raw `tenantId` từ client để cấp quyền chỉ vì nó qua Bean Validation.

Không trả exception nội bộ chứa tên bảng, địa chỉ hệ thống, stack trace hoặc raw secrets cho caller. Chọn catalog reason codes ổn định, log sanitization và retention theo mức nhạy cảm.

## 31. Unit test Bean Validation: cả object lẫn nested items

JUnit 5 với Bean Validation provider:

~~~java
@Test
void rejectsBlankOrderAndInvalidNestedItem() {
    ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
    try {
        Validator validator = factory.getValidator();
        OrderCommand malformed = new OrderCommand(
            "1", "EV-501", "tenant-a", " ",
            2, List.of(new OrderLine("", -3)));

        Set<ConstraintViolation<OrderCommand>> violations =
            validator.validate(malformed);

        assertFalse(violations.isEmpty());
        assertTrue(violations.stream().anyMatch(v ->
            v.getPropertyPath().toString()
                .contains("orderId")));
        assertTrue(violations.stream().anyMatch(v ->
            v.getPropertyPath().toString()
                .contains("quantity")));
    } finally {
        factory.close();
    }
}

@Test
void acceptsWellFormedOrder() {
    ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
    try {
        OrderCommand valid = new OrderCommand(
            "1", "EV-502", "tenant-a", "O-502",
            1, List.of(new OrderLine("SKU-1", 2)));
        assertTrue(factory.getValidator()
            .validate(valid).isEmpty());
    } finally {
        factory.close();
    }
}
~~~

Code lược bỏ imports; có thể dùng Spring-managed `Validator` thay vì tự tạo factory từng test. Để test bắt được `quantity` nested, phải có provider Bean Validation và cascade `@Valid` được áp dụng đúng.

**Unit test trên object không chứng minh deserializer reject JSON sai kiểu**, vì Java object đã được tạo sẵn. Cũng không chứng minh message đi đúng discard channel hoặc broker ACK.

## 32. Integration test: Filter đẩy malformed object vào discard channel

Spring test context độc lập:

~~~java
@Configuration
@EnableIntegration
class OrderFilterTestConfig {

    @Bean
    IntegrationFlow validationFlow(
            OrderValidationService validation) {
        return IntegrationFlow.from("test.orders.in")
            .filter(OrderCommand.class,
                validation::isWellFormed,
                spec -> spec.discardChannel("test.orders.rejected"))
            .channel("test.orders.valid")
            .get();
    }

    @Bean("test.orders.valid")
    PollableChannel validOutput() {
        return new QueueChannel();
    }

    @Bean("test.orders.rejected")
    PollableChannel rejectedOutput() {
        return new QueueChannel();
    }
}
~~~

Kiểm thử:

~~~java
@Autowired
ApplicationContext context;

@Test
void malformedOrderGoesOnlyToRejectChannel() {
    MessageChannel input = context.getBean(
        "test.orders.in", MessageChannel.class);
    PollableChannel valid = context.getBean(
        "test.orders.valid", PollableChannel.class);
    PollableChannel rejected = context.getBean(
        "test.orders.rejected", PollableChannel.class);

    OrderCommand malformed = new OrderCommand(
        "1", "EV-501", "tenant-a", "",
        1, List.of(new OrderLine("SKU-1", 2)));

    assertTrue(input.send(new GenericMessage<>(malformed)));
    Message<?> rejectedMessage = rejected.receive(1_000);
    assertNotNull(rejectedMessage);
    assertEquals(malformed, rejectedMessage.getPayload());
    assertNull(valid.receive(0));
}
~~~

Chạy trong context riêng, không có consumer cạnh tranh lấy test output. Test cho thấy **Filter từ chối và route nội bộ chính xác**, không thay thế một test broker DLQ durability hoặc raw JSON error handling.

## 33. Integration test: fail-fast ném exception đúng boundary

Một flow test đồng bộ riêng:

~~~java
@Bean
IntegrationFlow failFastTestFlow(OrderValidationService validation) {
    return IntegrationFlow.from("test.failfast.in")
        .filter(OrderCommand.class,
            validation::isWellFormed,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("test.failfast.valid")
        .get();
}
~~~

Một assertion định hướng:

~~~java
@Test
void failFastFilterRejectsMalformedOrder() {
    MessageChannel input = context.getBean(
        "test.failfast.in", MessageChannel.class);
    OrderCommand bad = new OrderCommand(
        "1", "EV-503", "tenant-a", "",
        1, List.of(new OrderLine("SKU-1", 2)));

    assertThrows(MessagingException.class,
        () -> input.send(new GenericMessage<>(bad)));
}
~~~

Với Spring Integration, lỗi do Filter từ chối thường là `MessageRejectedException` (một subtype của messaging exception), nhưng caller/adapters có thể bọc exception; test đầy đủ nên assert **root cause và failed message** theo topology thật.

Với `ExecutorChannel`, Filter chạy ở worker thread, nên không giả định `input.send()` lập tức ném exception trên thread test. Khi đó kiểm tra error channel hoặc recoverer tương ứng.

## 34. Test raw bytes và lỗi trước khi Filter được gọi

Những trường hợp này không thể mô phỏng chỉ bằng `GenericMessage<OrderCommand>`:

~~~text
{ "items": [

{"quantity": "two"}

{"schemaVersion": "9", ...}

<JSON nesting depth rất lớn>

Body có encoding không được hỗ trợ.
~~~

Test ở boundary thực:

- **HTTP:** gửi raw body với Content-Type thích hợp; assert error status, response code và max-size behavior.
- **Kafka:** gửi bytes bằng serializer/deserializer thực; test listener error handler, DLT và offset policy.
- **AMQP/JMS:** gửi message có content-type/converter metadata sai; kiểm tra reject/nack/DLQ.
- **File ingest:** test quarantine path/retention cho file không parse được.

Một JSON có duplicate keys có thể bị parser xử lý theo giá trị cuối nếu strict duplicate detection chưa bật. Nếu contract **cấm duplicate property names**, phải bật parser setting/schema validation phù hợp và test riêng; một object Java đã deserialize không còn thông tin rằng key từng xuất hiện hai lần.

**Phân biệt:** lỗi decode có thể xảy ra trước khi có Spring Integration message, vì vậy test Filter trực tiếp không xác minh được recovery của adapter.

## 35. Ma trận kiểm thử end-to-end

| Case | Input/fault | Điều phải chứng minh |
|---|---|---|
| Valid order | Đúng schema và required fields | Vào business route |
| Malformed syntax | JSON thiếu dấu đóng | Reject tại ingress |
| Wrong JSON type | Quantity là string | Schema/type rejection |
| Missing ID | `eventId=""` | Không vào handler |
| Empty items | `items=[]` | Vi phạm `@Size` |
| Invalid nested item | `sku=""`, `quantity=-3` | Nhận field issues |
| Unsupported schema | Version 9 | Mã `UNSUPPORTED_SCHEMA_VERSION` |
| Unexpected fields | Strict/compatible mode | Kết quả theo contract đã chọn |
| Header/tenant mismatch | Tenant trái principal | Security rejection |
| Overlarge body | Vượt bytes/array limit | Reject trước fan-out |
| Filter discard | Predicate false | Chỉ tới discard channel |
| Fail-fast Filter | Throw enabled | Exception/response đúng |
| Gateway invalid input | Thiếu order ID | Không timeout vô nghĩa |
| Broker poison pill | Same malformed bytes redelivery | Không retry vô hạn |
| DLQ publish unavailable | Quarantine destination down | Không mất message chưa durable |
| Database outage | External validation dependency lỗi | Retryable path, không permanent reject |
| Invalid child | Filter reject L2 sau Splitter | Reject whole group hoặc outcome giữ correlation |
| Aggregator duplicate | L1 tới hai lần | Không đạt expectedCount giả |
| Same key/different payload | Input được sửa nhưng event ID cũ | Conflict/revision policy |
| Async exception | Worker throw sau khi send | Đúng error boundary |
| Cross-tenant collision | IDs giống, tenant khác | Không trộn/rò data |
| DLQ replay | Input được sửa có kiểm soát | Idempotency và audit đúng |

Đừng chỉ assert có một DLQ message. Hãy xác minh **business handler không chạy**, không có side effect, reasonCode chính xác, retries bounded, và recovery vẫn đúng khi consumer restart.

## 36. Observability: biết reject do dữ liệu hay do hạ tầng

Các tên metric đề xuất:

| Metric | Ý nghĩa |
|---|---|
| `ingress.messages.received.count` | Messages đến |
| `ingress.decode.failure.count` | Lỗi syntax/encoding/type |
| `validation.rejected.count` | Message bị reject sau deserialize |
| `validation.issues.count` | Số field violations |
| `validation.rejected.by_reason.count` | Mã lỗi phổ biến |
| `validation.duration` | Validator latency và CPU |
| `validation.payload.too_large.count` | Input vượt limits |
| `rejection.channel.failure.count` | Không đưa được message vào rejection path |
| `quarantine.pending.count` | Messages cần review |
| `quarantine.storage.bytes` | Storage pressure |
| `broker.poison.retry.count` | Redelivery của malformed messages |
| `broker.dlq.publish.failure.count` | DLQ không khả dụng |
| `gateway.invalid.timeout.count` | Caller timeout do thiếu rejection reply |
| `aggregator.missing.member.count` | Group thiếu child sau Filter |

Đây là **metric gợi ý**, không phải meter mặc định của Spring Integration. Dùng labels có cardinality thấp như `flowName`, `reasonCode`, `outcome` và schemaVersion thuộc tập hữu hạn; không dùng full event ID, order ID hay raw exception string làm metric tag.

Structured logs/quarantine có thể chứa:

~~~text
quarantineId=Q-9001
source=orders.kafka
schemaVersion=9
reasonCode=UNSUPPORTED_SCHEMA_VERSION
transportReference=partition-2/offset-183
eventId=EV-501
retryable=false
businessHandlerInvoked=false
~~~

Đặt quyền truy cập, che PII và retention. Đừng dùng các trường có cardinality vô hạn làm metric labels hoặc gửi raw malformed payload lên monitoring system không kiểm soát.

## 37. Runbook khi malformed event làm consumer kẹt

1. **Xác định boundary lỗi:** decode, Filter, Transformer hay business handler?
2. **Kiểm tra contract:** syntax, schema version, required fields, Content-Type, payload size.
3. **Phân loại:** permanent malformed, business rejection hay transient infrastructure failure?
4. **Kiểm tra retry policy:** có retry nóng mãi cùng bytes không?
5. **Xem Filter:** discard, throw hay drop im lặng?
6. **Xem broker ACK/offset:** đã lưu DLQ/quarantine chắc chắn trước khi kết thúc source message chưa?
7. **Xem reject handler:** channel có consumer, storage còn capacity và quyền ghi?
8. **Xem Gateway:** caller nhận rejection hay chỉ timeout?
9. **Xem Aggregator:** một child bị Filter loại khiến group thiếu outcome?
10. **Xem security:** tenant/header do ai cấp; raw data có lọt vào log?
11. **Khắc phục:** sửa producer, schema adapter hoặc đưa message lỗi sang quarantine theo policy.
12. **Regression test:** gửi raw bytes lỗi và xác minh không có side effect.

Không ACK/drop hàng loạt khi chưa xác định phần nào là permanent invalid và phần nào đang gặp outage. Không replay toàn bộ DLQ sau nâng schema nếu chưa có rate limiting, quyền, audit và idempotency.

## 38. Bài thực hành: pipeline từ chối malformed orders

Xây ứng dụng **ValidatedOrderFlow**:

1. Định nghĩa `OrderCommand` với Jakarta Bean Validation và giới hạn items/payload bytes.
2. Viết `OrderValidationService` thuần, deterministic cho required fields/format.
3. Cấu hình `orders.in → Filter → orders.valid` với `discardChannel=orders.rejected`.
4. Viết reject handler tạo `reasonCode` và lưu metadata đã sanitize.
5. Tạo flow fail-fast riêng với `throwExceptionOnRejection(true)`, so sánh hai behavior.
6. Test Gateway để invalid input có reply/exception, không chờ timeout vô nghĩa.
7. Test HTTP raw malformed JSON và type errors xảy ra trước Filter.
8. Nối một broker adapter, cấu hình permanent failure/DLQ phù hợp.
9. Mô phỏng DLQ unavailable, xác minh không mất source khi chưa durable recover.
10. Thêm Splitter với ba items, item 2 invalid; chọn whole-order rejection hoặc failure outcome.
11. Test correlation, duplicate, late reply, transient failure để không double side effect.
12. Theo dõi rejects, reason codes, poison pills và quarantine backlog.

**Tiêu chí hoàn thành:** malformed input bị từ chối đúng boundary; không tạo side effect; error path có reasonCode; không retry vô hạn; transient outage không bị đánh thành malformed; Gateway trả kết quả có nghĩa; Aggregator không mất child âm thầm; test bao phủ cả raw bytes và Spring messages.

## 39. Những hiểu lầm thường gặp

**“Message Filter bắt được mọi malformed JSON.”** Sai. Deserializer có thể lỗi trước khi tạo Spring Message.

**“Filter trả false nghĩa là vào errorChannel.”** Không. Nó có thể drop, gửi discard hoặc ném exception tùy cấu hình.

**“discardChannel là broker DLQ.”** Không. Đây là channel trong IntegrationFlow; DLQ cần adapter/publisher.

**“Bật throwExceptionOnRejection sẽ tự trả HTTP 400.”** Không tự động. Cần Gateway/controller mapper phù hợp.

**“Drop im lặng làm request kết thúc sạch.”** Gateway có thể timeout, broker có thể ACK mất input chưa audit.

**“Mọi lỗi validation đều nên retry.”** Permanent malformed không được sửa bằng retry cùng bytes.

**“Database timeout trong validator nghĩa là input invalid.”** Sai. Outage là một failure category khác.

**“Thêm @Valid vào DTO là đủ để message tự bị reject.”** Không. Validator phải được gọi thật.

**“Filter sau Splitter loại một line thì Aggregator vẫn đủ member.”** Không. Group có thể thiếu vô hạn.

**“Đủ ba messages là đủ ba lines.”** Sai khi duplicate; dùng manifest và distinct member IDs.

**“Raw tenant header có thể dùng để authorize.”** Không. Tenant phải được xác minh từ principal/credentials.

**“Log toàn bộ raw payload giúp debug tốt nhất.”** Có thể rò PII/secrets và gây log injection/storage abuse.

**“Schema mới parse được nghĩa là tương thích.”** Chưa chắc; cần xét semantics, constraints và version.

**“Mọi DLQ message có thể replay bất kỳ lúc nào.”** Cần quyền, version, idempotency, quotas và audit.

**“Filter thay thế transaction, retry và idempotency.”** Không. Nó chỉ quyết định forward/reject theo predicate.

## 40. Ghi nhớ

**Reject malformed message** là một **quy trình từ chối có chủ đích**, không chỉ một predicate `true/false`. Phân tầng **decode → schema/Bean Validation → domain/security checks**, phân biệt permanent malformed với business rejection và transient failures, rồi chọn **discard channel, typed rejection hoặc exception** theo hợp đồng caller/transport.

Trong **Spring Integration**, Filter chỉ kiểm tra **message đã được tạo thành công**; lỗi JSON parse cần xử lý tại inbound adapter. Filter có thể đưa rejected message sang discard channel hoặc ném exception, nhưng **không tự sinh HTTP 400, broker DLQ hay ACK policy**. Những điều đó phải được thiết kế và kiểm thử độc lập.

Validate **trước side effects và Splitter khi có thể**; nếu cần reject từng child thì giữ correlation và tạo failure outcome cho Aggregator hoặc fail whole batch. Kết hợp reasonCode ổn định, logging an toàn, bounded resource usage, idempotency, retry classification và tests xuyên wire/message boundary để đảm bảo dữ liệu sai bị từ chối **đúng chỗ, đúng lý do mà không làm mất công việc hợp lệ**.

### Tài liệu tham khảo

- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Framework Reference, **Bean Validation**: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Enterprise Integration Patterns, **Message Filter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Filter.html
