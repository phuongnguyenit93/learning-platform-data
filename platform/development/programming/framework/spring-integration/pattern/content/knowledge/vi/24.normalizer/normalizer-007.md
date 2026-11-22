# Normalizer và version của message

Trong hệ thống tích hợp, nhiều producer có thể gửi **cùng một ý nghĩa nghiệp vụ** bằng các cấu trúc message khác nhau. Một ứng dụng cũ gửi `orderNo`, bản mới gửi `orderId`; một nguồn dùng trường `amountMinorUnits`, nguồn khác dùng `totalMinorUnits`; một event chưa có `customerNote`, một event sau nâng cấp mới có. Nếu tất cả các handler downstream đều phải biết từng phiên bản, logic sẽ bị nhân bản và việc nâng cấp có thể làm hỏng các flow đang hoạt động.

**Normalizer** (EIP) giải quyết bằng cách **nhận nhiều biểu diễn đầu vào và chuyển chúng thành một biểu diễn chuẩn**. Trong Spring Integration, Normalizer thường là **một nhóm endpoint**, chẳng hạn **Router theo format/schema version**, sau đó là **Transformer riêng cho từng version**, và cuối cùng hội tụ về một channel chứa **canonical message**. Không nên mặc định có một class hoặc Java DSL method `.normalize()` của Spring Integration tự biết mọi schema; việc xác định phiên bản, ánh xạ trường, validation và semantics cần được thiết kế rõ ràng.

Bài **Normalizer và version của message** thuộc chương **Normalizer** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý.

**Nguyên tắc cốt lõi:** version là một **phần của hợp đồng dữ liệu**, không phải mẹo để né lỗi parse. Normalizer phải phân biệt **schema version của message đầu vào** với **schema version chuẩn ở output**, bảo toàn business identity/idempotency/correlation, chuyển đổi dữ liệu theo đúng semantics, và **không đoán im lặng** khi một version không được hỗ trợ.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích Normalizer EIP và lý do dùng Router + Transformers trước shared processing flow.
2. Phân biệt **wire format**, **message schema version**, **canonical schema version**, **business revision**, **event ID** và **trace ID**.
3. Nhận diện rủi ro khi nhiều producer nâng cấp khác thời điểm.
4. Thiết kế `OrderCreatedV1`, `OrderCreatedV2` và `OrderCreatedCanonical` với semantics rõ ràng.
5. Ánh xạ field được đổi tên mà không vô tình đổi đơn vị, scale hoặc ý nghĩa.
6. Xác thực version từ nguồn tin cậy và đối chiếu header/payload type.
7. Tạo Java DSL Router theo `schemaVersion`; mỗi route có Transformer riêng.
8. Gắn `sourceSchemaVersion` và `schemaVersion` mới để phục vụ debug và downstream.
9. Kiểm thử v1/v2 hội tụ cùng canonical DTO và unsupported version không đi vào business handler.
10. Phân biệt backward/forward compatibility với logic migration trong Normalizer.
11. Xử lý unknown/missing version, inconsistent headers, fields bắt buộc và lossy transformations.
12. Bảo toàn event identity, business correlation và idempotency khi version thay đổi.
13. Thiết kế rollout, canary, schema registry/contract test, replay và rollback.
14. Theo dõi tỷ lệ message theo phiên bản, lỗi mapping và độ trễ normalization.
15. Kết hợp Normalizer với Filter, Router, Aggregator, retry và error channel trong flow đáng tin cậy.

## 2. Vì sao version của message là bài toán tích hợp?

Giả sử hệ thống nhận event đơn hàng từ hai phiên bản producer chạy song song:

~~~json
{
  "schemaVersion": "1",
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMinorUnits": 250000,
  "currency": "VND"
}
~~~

Producer mới phát:

~~~json
{
  "schemaVersion": "2",
  "eventId": "evt-order-1002",
  "tenantId": "tenant-a",
  "orderId": "ORDER-102",
  "totalMinorUnits": 175000,
  "currency": "VND",
  "customerNote": "Giao trong giờ hành chính"
}
~~~

Hai message đều nói rằng **một đơn hàng được tạo**, nhưng trường ID/số tiền có tên khác nhau và v2 bổ sung ghi chú. Handler phía sau chỉ cần hợp đồng:

~~~text
OrderCreatedCanonical
  eventId
  tenantId
  orderId
  totalMinorUnits
  currency
  customerNote (nullable nếu source không có)
~~~

Thay vì mỗi handler có:

~~~java
if (version == 1) {
    // đọc orderNo
}
else if (version == 2) {
    // đọc orderId
}
~~~

ở nhiều vị trí, Normalizer đặt **version-specific knowledge tại boundary**.

~~~mermaid
flowchart LR
    V1["OrderCreated v1"] --> R{"Version Router"}
    V2["OrderCreated v2"] --> R
    R -->|"1"| T1["Transformer v1→canonical"]
    R -->|"2"| T2["Transformer v2→canonical"]
    T1 --> C["Canonical OrderCreated"]
    T2 --> C
    C --> F["Shared Filter/Router"]
    F --> B["Business handler"]
    R -->|"unsupported"| Q["Quarantine / error outcome"]
~~~

**Ý nghĩa của sơ đồ:** downstream được bảo vệ khỏi thay đổi cấu trúc của từng producer. Điều đó **không** có nghĩa canonical contract có thể thay đổi tùy ý — một bản canonical mới vẫn cần chính sách version/migration và contract tests riêng.

## 3. EIP Normalizer khác Transformer, Router và Enricher

Normalizer có thể được xem như **một phối hợp giữa Router và Message Translator/Transformer** để nhiều input formats hội tụ về một representation chung.

| Thành phần | Vấn đề giải quyết | Vai trò trong bài |
|---|---|---|
| **Normalizer EIP** | Nhiều biến thể cùng ý nghĩa về một chuẩn | Toàn bộ boundary v1/v2 → canonical |
| **Content-based Router** | Chọn endpoint theo thuộc tính/version | Gửi v1 tới transformer v1, v2 tới transformer v2 |
| **Header-based Router** | Chọn endpoint từ metadata | Dùng `schemaVersion` header đáng tin |
| **Transformer** | Đổi một representation sang representation khác | Map `orderNo→orderId`, kiểm tra money semantics |
| **Content Enricher** | Bổ sung thông tin từ nguồn khác | Có thể dùng nếu thật sự cần trường chưa có |
| **Filter** | Chấp nhận/bỏ message theo điều kiện | Chỉ làm eligibility sau khi normalized nếu hợp lý |
| **Aggregator** | Gom nhiều message theo group | Cần canonical IDs/correlation ổn định |
| **Schema validation** | Xác nhận input thuộc một contract | Thực hiện tại ingress/phiên bản tương ứng |

Một `.transform(...)` duy nhất có thể đủ nếu chỉ có hai phiên bản đơn giản, nhưng Normalizer EIP nhấn mạnh **việc quy tụ nhiều format đầu vào về một hợp đồng chung**, không chỉ một phép thay field. Không nên đặt tất cả logic version vào mọi business handler.

### 3.1. Không có một Java API `normalize` tự động đoán schema

Tên *Normalizer* là tên pattern, không bảo đảm một endpoint riêng trong framework có thể tự map arbitrary JSON versions. Với Spring Integration Java DSL, thường dùng:

~~~text
IntegrationFlow
  -> .route(...)
  -> channel v1/v2
  -> .transform(...)
  -> canonical channel
~~~

Hoặc implement một Transformer có dispatch theo version trong code. Chọn cách nào phải xét số phiên bản, mức độ độc lập, khả năng deploy và cách test.

## 4. Đừng nhầm các kiểu "version"

Từ `version` có nhiều ý nghĩa; nhầm chúng tạo ra lỗi dữ liệu khó thấy.

| Khái niệm | Ví dụ | Dùng để làm gì |
|---|---|---|
| **Wire format version** | JSON vs Avro; encoding revision | Chọn decoder/serializer |
| **Event type** | `OrderCreated` vs `OrderCancelled` | Chọn loại business event |
| **Source schema version** | `OrderCreated v1` hoặc `v2` | Chọn transformer |
| **Canonical schema version** | `OrderCreatedCanonical v3` | Contract nội bộ cho downstream |
| **Business aggregate revision** | `orderRevision=17` | Optimistic concurrency, ordering |
| **Event ID** | `evt-order-1001` | Dedup, audit, at-least-once replay |
| **MessageHeaders.ID** | UUID của một Spring Message | Nhận diện message instance |
| **Trace/span ID** | `trace-55` | Theo dõi distributed flow |
| **API version** | `/api/v2/orders` | Hợp đồng HTTP endpoint |
| **Application release** | `order-service 4.8.1` | Deployment/build |
| **Schema registry ID** | `subject/id=123` | Tra schema/decoder theo registry |

### 4.1. Schema version không phải business revision

Ví dụ một đơn trải qua:

~~~text
OrderCreated:   schemaVersion=2, orderRevision=1
OrderPaid:      schemaVersion=2, orderRevision=2
OrderCancelled: schemaVersion=2, orderRevision=3
~~~

Schema version không đổi dù state nghiệp vụ thay đổi. Ngược lại, một sự kiện lịch sử có thể được **serialize lại bằng schema v3** mà business revision vẫn là 1. Dùng schema version để resequence/optimistic locking là sai chức năng.

### 4.2. Event ID phải ổn định qua normalization

~~~text
Input v1:
  eventId = evt-order-1001

Output canonical:
  eventId = evt-order-1001
~~~

Normalizer **không tự tạo event ID mới** cho cùng một business event chỉ vì payload đổi schema. Nếu broker redeliver message rồi normalizer sinh `UUID.randomUUID()` làm eventId, Idempotent Receiver sau đó có thể xử lý trùng side effect.

### 4.3. Version cũng không phải Correlation ID

Ba sự kiện Order/Payment/Inventory có thể sử dụng các schema versions khác nhau nhưng **cùng business correlation key** `(tenantId,orderId)`. Nếu gom theo `schemaVersion`, Aggregator sẽ nhập nhiều đơn v2 thành một group và tách cùng đơn khi producer upgrade.

## 5. Ba chiều biến đổi cần phân biệt

### 5.1. Decoding: bytes → typed source DTO

~~~text
Raw JSON bytes
  -> JSON/Avro/Protobuf decoder đúng version
  -> OrderCreatedV1 hoặc OrderCreatedV2
~~~

Decoder xử lý cú pháp, kiểu JSON, required fields theo schema và encoding. Nếu JSON payload chưa được decode, một Transformer mong `OrderCreatedV1` sẽ không tự hiểu `byte[]` hoặc `String`.

### 5.2. Semantic normalization: source DTO → canonical DTO

~~~text
OrderCreatedV1
  orderNo
  amountMinorUnits

->

OrderCreatedCanonical
  orderId
  totalMinorUnits
~~~

Đây không chỉ là đổi tên: phải xác minh **cùng ý nghĩa, cùng đơn vị và cùng độ chính xác**.

### 5.3. Business processing sau normalization

~~~text
OrderCreatedCanonical
  -> validate business invariants
  -> Filter / Router / Enricher
  -> downstream business handler
~~~

Normalizer không nên tự gửi payment, ghi DB hoặc thay đổi trạng thái đơn hàng như một side effect **không được yêu cầu**. Một pure mapper dễ retry và dễ test hơn một mapper vừa decode vừa gọi nhiều dịch vụ.

## 6. Version policy: support matrix

Trước khi viết code, công bố version mà hệ thống có thể đọc:

| Input type | Source version | Status | Đích | Lý do |
|---|---|---|---|---|
| OrderCreated | 1 | Supported, legacy | Canonical v3 | Vẫn còn producer cũ |
| OrderCreated | 2 | Supported | Canonical v3 | Producer hiện hành |
| OrderCreated | 3 | Chưa hỗ trợ input | Quarantine/explicit rejection | Chưa có consumer adapter |
| PaymentCaptured | 1 | Không phải OrderCreated | Router của event type khác | Không được giả là OrderCreated v1 |
| OrderCreated | Không có version | Theo contract ingress | Reject hoặc legacy policy công bố | Không tự đoán từ tên trường |
| OrderCreated | Chưa nhận diện | Unsupported version | Error/quarantine | Tránh ghi business data sai |

**Canonical v3** trong bài là **quy ước ví dụ của ứng dụng**, không phải version hệ thống của Spring Integration. Input v1/v2 được chuyển trực tiếp thành canonical v3. Điều đó không nói rằng một external `OrderCreated v3` đã được hỗ trợ nếu chưa có adapter tương ứng.

### 6.1. Khác nhau giữa hỗ trợ format cũ và giữ backward compatibility

Một consumer có thể hỗ trợ schema v1 bằng một Transformer riêng ngay cả khi v2 có thay đổi không backward-compatible. **Compatibility của schema evolution** và **khả năng normalizer xử lý nhiều version** là hai chuyện khác nhau.

- Schema compatible: có thể cùng decoder/reader xử lý field thêm/bớt theo quy tắc format/registry.
- Version-specific transformer: có thể map hai schema không tương thích về cùng canonical contract.
- Canonical contract: vẫn có thể thay đổi độc lập, cần quy tắc rollout riêng.

## 7. Backward, forward và full compatibility

Thuật ngữ tương thích cần nêu theo **reader/writer** và serialization format; dưới đây là cách hiểu thường dùng của schema evolution:

| Loại | Ý nghĩa khái quát | Ví dụ tình huống |
|---|---|---|
| Backward compatibility | Reader mới đọc được dữ liệu do writer cũ tạo | Consumer mới xử lý event v1 |
| Forward compatibility | Reader cũ đọc được dữ liệu từ writer mới | Consumer cũ bỏ qua field mới của v2 |
| Full compatibility | Cả hai chiều được bảo đảm theo luật schema | Producer/consumer có thể lệch version an toàn |
| Breaking change | Có cặp reader/writer không tương thích | Đổi type/ý nghĩa trường mà không migration |

**Định nghĩa cụ thể phụ thuộc Avro/Protobuf/JSON Schema và policy của registry.** Một field mới được thêm vào không luôn tương thích nếu downstream strict JSON deserializer từ chối unknown fields; một field renamed không tự compatible chỉ vì cùng ý nghĩa nghiệp vụ.

### 7.1. Additive field chưa chắc vô hại

V2 thêm `customerNote`:

- Một consumer tolerant có thể bỏ qua field không biết.
- Một consumer strict có thể reject v2.
- Một transformer v1 không nên tự tạo `customerNote="N/A"` nếu nghiệp vụ coi đó là một ghi chú thật.
- Nếu ghi chú bắt buộc ở canonical, v1 sẽ không có đủ dữ liệu để map chính xác; cần policy rõ.

### 7.2. Rename không tự tương thích

V1 `orderNo` → V2 `orderId` là breaking nếu reader cũ chỉ tra `orderNo`. Normalizer có thể chủ động map hai field, thay vì sửa tất cả downstream handlers.

### 7.3. Đổi type hoặc unit là rủi ro lớn hơn rename

~~~text
v1 amount: integer minor units
v2 amount: decimal major units
~~~

Nếu chỉ đổi tên mà không chuyển đơn vị, số tiền có thể lệch hàng trăm lần. Cần định nghĩa conversion với `currency`, scale, rounding, overflow và test edge cases. Ví dụ bài này **giữ cả v1 và v2 ở minor units** để tập trung vào version routing.

## 8. Contract ví dụ: OrderCreated v1, v2 và canonical v3

### 8.1. Source payload v1

~~~java
public record OrderCreatedV1(
        String eventId,
        String tenantId,
        String orderNo,
        long amountMinorUnits,
        String currency
) {}
~~~

### 8.2. Source payload v2

~~~java
public record OrderCreatedV2(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String customerNote
) {}
~~~

### 8.3. Canonical payload v3

~~~java
public record OrderCreatedCanonical(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String customerNote
) {}
~~~

Đây là **ba public top-level Java types khác nhau**; khi đưa vào project, mỗi record phải nằm trong file `OrderCreatedV1.java`, `OrderCreatedV2.java` và `OrderCreatedCanonical.java` riêng. Dùng Java 17+ cho records.

### 8.4. Bảng mapping field-level

| Canonical field | V1 source | V2 source | Semantic rule |
|---|---|---|---|
| `eventId` | `eventId` | `eventId` | Giữ nguyên business event identity |
| `tenantId` | `tenantId` | `tenantId` | Xác thực ownership/tenant tại ingress |
| `orderId` | `orderNo` | `orderId` | Không thay đổi business identity |
| `totalMinorUnits` | `amountMinorUnits` | `totalMinorUnits` | Cùng minor units theo currency contract |
| `currency` | `currency` | `currency` | Kiểm tra ISO/currency allowlist theo domain |
| `customerNote` | Không tồn tại | `customerNote` | V1 → `null` = không có thông tin, không bịa dữ liệu |

**Không điền mặc định những giá trị có ý nghĩa tài chính hoặc quyền truy cập.** Trong demo, v1 thiếu `customerNote` nên kết quả `null` thể hiện *unknown/not provided*. Nếu v3 thật yêu cầu field không-null, không thể tự bịa note để đánh lừa downstream; cần thay contract, enrich từ nguồn đáng tin hoặc reject có reason.

### 8.5. Các field cốt lõi không được mất

- `eventId`: dùng chống duplicate.
- `tenantId`: scope business identity, nhưng phải được xác thực.
- `orderId`: dùng correlation với Payment/Inventory.
- `totalMinorUnits` và `currency`: tính đúng số tiền.
- Version provenance: để biết source transformation nào đã được dùng.
- Correlation/trace headers: theo hợp đồng transport nếu cần.

Không nhầm một message **được chuẩn hóa về canonical DTO** với một business event **đã được xử lý thành công**.

## 9. Những bất biến của Normalizer

Với hai source messages biểu đạt cùng logical event, output phải có semantics tương đương:

~~~text
Normalize(OrderCreatedV1(evt-1001, tenant-a, ORDER-101, 250000, VND))
    ==
Normalize(OrderCreatedV2(evt-1001, tenant-a, ORDER-101, 250000, VND, null))
~~~

Bất biến quan trọng:

1. **Stable event identity:** `eventId` không đổi.
2. **Stable tenant/business key:** `tenantId/orderId` không đổi.
3. **Preserved money semantics:** số tiền/đơn vị không đổi ngoài conversion được contract cho phép.
4. **Determinism:** cùng input và mapping version → cùng canonical payload.
5. **Fail-fast:** version không biết hoặc field bắt buộc thiếu không được im lặng map.
6. **No hidden business side effects:** normalize không tự charge, reserve stock hoặc thay status.
7. **Provenance:** biết source version và canonical target version.
8. **No accidental secret propagation:** headers qua trust boundary được kiểm soát.
9. **Testable replay:** một event redelivery không biến thành event ID mới.
10. **Explicit lossy rule:** trường bị bỏ hoặc thông tin thiếu có ý nghĩa phải được ghi hợp đồng.

### 9.1. Chuẩn hóa không phải thay đổi dữ liệu nghiệp vụ

Nếu source `totalMinorUnits=250000`, normalizer không được tùy ý chiết khấu còn 240000 rồi gọi đó là "format canonical". Discount là **business transformation** khác, cần rules/versioning/approval riêng.

### 9.2. Idempotent transformation và idempotent receiver khác nhau

Một pure transformer cùng input cho cùng output là **deterministic/idempotent về mapping**, nhưng **không tự bảo đảm** downstream side effect chỉ xảy ra một lần. Broker có thể redeliver cả hai bản sau normalization; Idempotent Receiver vẫn cần stable event ID và business uniqueness.

## 10. Version detection: header, envelope hay registry?

Có ba kiểu phổ biến:

| Nguồn version | Ví dụ | Ưu điểm | Rủi ro |
|---|---|---|---|
| Message header | `schemaVersion="1"` | Router dễ đọc, ít đụng payload | Header có thể thiếu/bị giả mạo |
| Event envelope | `{"eventType":"OrderCreated","schemaVersion":"1","data":...}` | Contract rõ, dễ audit | Cần decoder parse envelope trước |
| Binary schema/registry ID | Avro/Protobuf registry ID | Có luật schema/codec cụ thể | Cần registry access/cache/version policy |

### 10.1. Header phải đáng tin

Nếu client tự gửi:

~~~text
schemaVersion=2
payload=OrderCreatedV1
~~~

một Router chỉ dựa vào header có thể gọi nhầm transformer v2. **Phải đối chiếu version và payload type/schema** tại boundary; không để untrusted header quyết định hoàn toàn phép cast.

### 10.2. Không tự đoán version chỉ vì có field mới

Một message v1 có thể có unknown field do producer bật feature thử nghiệm; một v2 có thể không có optional field. Tự suy `v1` hay `v2` từ sự tồn tại của `customerNote` dễ sai. Hãy dùng explicit metadata và schema validation.

### 10.3. Version không phải hệ số để so sánh tùy tiện

Không áp dụng `if(version >= 2)` như thể version lớn luôn chứa tất cả fields cũ. Một major version có thể breaking. Cần **support matrix** cho từng event type và mapping được kiểm chứng, không chỉ so sánh số nguyên.
## 11. Java implementation: một Normalizer rõ ràng và không đoán dữ liệu

Ta triển khai **một bean có hai method chuyên biệt** `fromV1` và `fromV2`. Mỗi method nhận message, đối chiếu metadata version với payload thực, validate và tạo `Message<OrderCreatedCanonical>` mới.

### 11.1. Exception dành cho contract/schema không hợp lệ

~~~java
public final class InvalidOrderSchemaException
        extends RuntimeException {

    private final String reasonCode;

    public InvalidOrderSchemaException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

Reason code ngắn và ổn định giúp error flow phân loại. Không ném raw JSON chứa thông tin cá nhân vào exception message.

### 11.2. OrderVersionNormalizer

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class OrderVersionNormalizer {

    public Message<OrderCreatedCanonical> fromV1(
            Message<?> original) {

        requireVersion(original, "1");

        if (!(original.getPayload() instanceof OrderCreatedV1 v1)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_PAYLOAD_MISMATCH");
        }

        OrderCreatedCanonical normalized =
                new OrderCreatedCanonical(
                        v1.eventId(),
                        v1.tenantId(),
                        v1.orderNo(),
                        v1.amountMinorUnits(),
                        v1.currency(),
                        null);

        return toCanonicalMessage(
                original, normalized, "1");
    }

    public Message<OrderCreatedCanonical> fromV2(
            Message<?> original) {

        requireVersion(original, "2");

        if (!(original.getPayload() instanceof OrderCreatedV2 v2)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_PAYLOAD_MISMATCH");
        }

        OrderCreatedCanonical normalized =
                new OrderCreatedCanonical(
                        v2.eventId(),
                        v2.tenantId(),
                        v2.orderId(),
                        v2.totalMinorUnits(),
                        v2.currency(),
                        v2.customerNote());

        return toCanonicalMessage(
                original, normalized, "2");
    }

    private void requireVersion(
            Message<?> message,
            String expected) {

        Object actual = message.getHeaders()
                .get("schemaVersion");

        if (!expected.equals(actual)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_HEADER_MISMATCH");
        }
    }

    private Message<OrderCreatedCanonical> toCanonicalMessage(
            Message<?> original,
            OrderCreatedCanonical normalized,
            String sourceVersion) {

        validateCanonical(normalized);

        MessageBuilder<OrderCreatedCanonical> builder =
                MessageBuilder.withPayload(normalized)
                        .setHeader("schemaVersion", "3")
                        .setHeader(
                                "sourceSchemaVersion",
                                sourceVersion)
                        .setHeader(
                                "eventId",
                                normalized.eventId());

        // Chỉ copy metadata được phép tại boundary này.
        copyIfPresent(original, builder, "traceId");
        copyIfPresent(
                original, builder, "businessCorrelationId");

        return builder.build();
    }

    private static void copyIfPresent(
            Message<?> original,
            MessageBuilder<?> builder,
            String name) {

        Object value = original.getHeaders().get(name);
        if (value != null) {
            builder.setHeader(name, value);
        }
    }

    private static void validateCanonical(
            OrderCreatedCanonical order) {

        if (blank(order.eventId())) {
            throw new InvalidOrderSchemaException(
                    "EVENT_ID_REQUIRED");
        }

        if (blank(order.tenantId())) {
            throw new InvalidOrderSchemaException(
                    "TENANT_ID_REQUIRED");
        }

        if (blank(order.orderId())) {
            throw new InvalidOrderSchemaException(
                    "ORDER_ID_REQUIRED");
        }

        if (order.totalMinorUnits() <= 0) {
            throw new InvalidOrderSchemaException(
                    "INVALID_AMOUNT");
        }

        if (blank(order.currency())
                || !order.currency().matches("[A-Z]{3}")) {
            throw new InvalidOrderSchemaException(
                    "INVALID_CURRENCY_FORMAT");
        }
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

**Giới hạn có chủ đích của ví dụ:**

- `currency.matches("[A-Z]{3}")` chỉ kiểm tra *hình dạng* mã, **không chứng minh** đây là currency được business hỗ trợ. Production cần ISO 4217/domain allowlist và logic đơn vị tiền tương ứng.
- `totalMinorUnits > 0` là quy tắc cho event order có tiền dương trong ví dụ; không được áp dụng máy móc cho credit/zero-amount order nếu domain cho phép.
- `customerNote=null` khi v1 không có field là chính sách *không suy diễn thông tin*. Nếu downstream yêu cầu note không-null, cần đổi contract hoặc enrich đáng tin cậy.
- Hàm `requireVersion` yêu cầu header có kiểu `String`. Nếu ingress adapter nhận integer JSON version, phải chuẩn hóa **trước router**, không đổi kiểu ngẫu nhiên ở nhiều endpoint.
- Code không validate quyền sử dụng `tenantId` so với principal; việc đó thuộc adapter/security boundary.
- Không copy tất cả message headers, tránh lan truyền `Authorization`, `contentType` cũ hoặc nội dung nhạy cảm. Nhưng vì không copy `replyChannel` và `errorChannel`, ví dụ phù hợp với **one-way event flow**; Gateway request-reply cần header handling theo hợp đồng riêng.

### 11.3. Vì sao không dùng `copyHeaders` mù quáng?

Một cách viết ngắn:

~~~java
MessageBuilder.withPayload(normalized)
        .copyHeaders(original.getHeaders())
        .setHeader("schemaVersion", "3")
        .build();
~~~

có thể vô tình tiếp tục mang:

- `contentType` của raw JSON/Avro v1 dù payload hiện là Java DTO canonical;
- `authorization` hoặc PII của nguồn ngoài;
- `replyChannel` tham chiếu đối tượng chỉ tồn tại trong JVM cũ;
- Version metadata mâu thuẫn, nếu không ghi đè đúng;
- Header kỹ thuật không được phép ra trust boundary.

Vì vậy ví dụ dùng **allowlist** `traceId` và `businessCorrelationId` sau khi đã xác định chúng đến từ kênh tin cậy. Tùy hệ thống, có thể cần thêm các headers khác, nhưng phải được kiểm soát và kiểm thử.

### 11.4. Version provenance rõ ràng

Message sau khi chuẩn hóa từ v1 có thể là:

~~~text
payload:
  OrderCreatedCanonical(
    eventId=evt-order-1001,
    tenantId=tenant-a,
    orderId=ORDER-101,
    totalMinorUnits=250000,
    currency=VND,
    customerNote=null)

headers:
  schemaVersion="3"
  sourceSchemaVersion="1"
  eventId="evt-order-1001"
  traceId="trace-1001"
~~~

Trong đó:

- `schemaVersion` mô tả **payload hiện tại** của message.
- `sourceSchemaVersion` mô tả **hợp đồng nguồn** đã được dùng để map.
- `eventId` không thay đổi.
- Trường ghi chú v1 là `null`, thể hiện nguồn chưa cung cấp.

Nếu dùng một header chung `schemaVersion=1` để truyền tiếp vào canonical channel, downstream có thể hiểu nhầm payload là v1 và deserialize sai. Bởi vậy sau biến đổi nên cập nhật current version và giữ provenance ở trường riêng.

## 12. Spring Integration Java DSL: Router + hai Transformers

Cấu hình minh họa:

~~~text
orders.in
  -> route by headers['schemaVersion']
       "1" -> orders.v1 -> normalizeV1 -> orders.canonical
       "2" -> orders.v2 -> normalizeV2 -> orders.canonical
       other -> orders.unsupported
~~~

### 12.1. Toàn bộ cấu hình với channels tách biệt

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class VersionAwareNormalizerConfiguration {

    @Bean
    public OrderVersionNormalizer orderVersionNormalizer() {
        return new OrderVersionNormalizer();
    }

    @Bean(name = "orders.in")
    public MessageChannel inbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.v1")
    public MessageChannel versionOne() {
        return new DirectChannel();
    }

    @Bean(name = "orders.v2")
    public MessageChannel versionTwo() {
        return new DirectChannel();
    }

    @Bean(name = "orders.canonical")
    public PollableChannel canonicalOutput() {
        return new QueueChannel();
    }

    @Bean(name = "orders.unsupported")
    public PollableChannel unsupportedOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow schemaVersionRouter() {
        return IntegrationFlow.from("orders.in")
                .route(
                        "headers['schemaVersion']",
                        router -> router
                                .channelMapping(
                                        "1", "orders.v1")
                                .channelMapping(
                                        "2", "orders.v2")
                                .defaultOutputChannel(
                                        "orders.unsupported"))
                .get();
    }

    @Bean
    public IntegrationFlow normalizerV1Flow(
            OrderVersionNormalizer normalizer) {
        return IntegrationFlow.from("orders.v1")
                .transform(normalizer, "fromV1")
                .channel("orders.canonical")
                .get();
    }

    @Bean
    public IntegrationFlow normalizerV2Flow(
            OrderVersionNormalizer normalizer) {
        return IntegrationFlow.from("orders.v2")
                .transform(normalizer, "fromV2")
                .channel("orders.canonical")
                .get();
    }
}
~~~

**Đây là ví dụ Java DSL dành cho flow event nội bộ**:

- Router dùng `ExpressionEvaluatingRouter`/SpEL expression để đọc header.
- `channelMapping` đưa version được hỗ trợ vào channel riêng.
- `defaultOutputChannel` nhận version không có mapping; production cần **error/quarantine handler có policy**, không để queue đầy vô hạn.
- Cả hai Transformers cùng phát `Message<OrderCreatedCanonical>` vào canonical output.
- `QueueChannel` là test fixture để nhận output và unsupported input. Khi chuyển sang production, chọn persistent/broker channels theo SLA, không mặc định QueueChannel có tính bền vững.
- Tên bean endpoint phải tránh trùng trong cùng Spring context.
- Router không đảm bảo correctness nếu header bị giả mạo: `fromV1` và `fromV2` vẫn kiểm tra payload runtime type và header version.

### 12.2. Vì sao tách nhiều flows thay vì một if/else rất dài?

Lợi ích:

1. Mỗi version có test contract riêng.
2. Có thể deprecate v1 độc lập khi publisher cũ đã hết.
3. Metrics theo version dễ quan sát.
4. Mapping của v2 không bị các điều kiện v1 làm phức tạp.
5. Việc thêm v3 input có quy trình rõ: route mới, transformer mới, tests mới.

Nếu số phiên bản ít và mapping ngắn, một Transformer có dispatch cũng hợp lệ; quan trọng là **mỗi source version có semantics rõ ràng**.

### 12.3. Khi nào dùng annotation thay Java DSL?

Có thể dùng `@Transformer(inputChannel="orders.v1",outputChannel="orders.canonical")` trên một method với adapter chịu trách nhiệm chuẩn hóa. Không nên đồng thời tạo Java DSL flow và annotation endpoint cùng subscribe vào một input nếu bạn kỳ vọng mỗi message đi qua cả hai: `DirectChannel` là point-to-point dispatch, không phải broadcast.

### 12.4. Không tự map version không biết sang gần nhất

~~~java
// Anti-pattern: version 5 có thể breaking.
String effective = version.equals("1")
        ? "1"
        : "2";
~~~

Điều này đưa v3/v4/v5 hoặc header bị sai sang transformer v2 rồi có thể đọc nhầm dữ liệu. Version chưa hỗ trợ phải đi vào **explicit unsupported path** hoặc fail-fast, không mặc nhiên chọn "phiên bản mới nhất".

## 13. Unit test mapper: v1/v2 hội tụ về canonical semantics

Ta dùng `JUnit 5` và `MessageBuilder`. Unit test thuần này không khởi động Spring Integration context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderVersionNormalizerTest {

    private final OrderVersionNormalizer normalizer =
            new OrderVersionNormalizer();

    @Test
    void versionOneMapsLegacyNamesAndPreservesIdentity() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-order-1001", "tenant-a",
                "ORDER-101", 250000, "VND");

        Message<OrderCreatedV1> input =
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "1")
                        .setHeader("traceId", "trace-1001")
                        .build();

        Message<OrderCreatedCanonical> normalized =
                normalizer.fromV1(input);

        assertEquals(
                new OrderCreatedCanonical(
                        "evt-order-1001", "tenant-a",
                        "ORDER-101", 250000, "VND", null),
                normalized.getPayload());

        assertEquals(
                "3", normalized.getHeaders().get("schemaVersion"));
        assertEquals(
                "1", normalized.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "trace-1001", normalized.getHeaders().get("traceId"));
    }

    @Test
    void versionTwoMapsCurrentFields() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-order-1002", "tenant-a",
                "ORDER-102", 175000, "VND",
                "Giao giờ hành chính");

        Message<OrderCreatedCanonical> normalized =
                normalizer.fromV2(
                        MessageBuilder.withPayload(event)
                                .setHeader("schemaVersion", "2")
                                .build());

        assertEquals(
                "ORDER-102", normalized.getPayload().orderId());
        assertEquals(
                175000, normalized.getPayload().totalMinorUnits());
        assertEquals(
                "Giao giờ hành chính",
                normalized.getPayload().customerNote());
        assertEquals(
                "2", normalized.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "3", normalized.getHeaders().get("schemaVersion"));
    }

    @Test
    void sameBusinessEventHasSameCanonicalPayloadInBothVersions() {
        String id = "evt-order-shared";

        OrderCreatedV1 v1 = new OrderCreatedV1(
                id, "tenant-a", "ORDER-900",
                99000, "VND");

        OrderCreatedV2 v2 = new OrderCreatedV2(
                id, "tenant-a", "ORDER-900",
                99000, "VND", null);

        OrderCreatedCanonical canonicalV1 =
                normalizer.fromV1(
                        MessageBuilder.withPayload(v1)
                                .setHeader("schemaVersion", "1")
                                .build())
                        .getPayload();

        OrderCreatedCanonical canonicalV2 =
                normalizer.fromV2(
                        MessageBuilder.withPayload(v2)
                                .setHeader("schemaVersion", "2")
                                .build())
                        .getPayload();

        assertEquals(canonicalV1, canonicalV2);
        assertEquals(id, canonicalV1.eventId());
    }

    @Test
    void wrongVersionHeaderIsRejected() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-order-3", "tenant-a",
                "ORDER-103", 10000, "VND");

        Message<OrderCreatedV1> mismatched =
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "2")
                        .build();

        InvalidOrderSchemaException error = assertThrows(
                InvalidOrderSchemaException.class,
                () -> normalizer.fromV1(mismatched));

        assertEquals(
                "SCHEMA_VERSION_HEADER_MISMATCH",
                error.reasonCode());
    }

    @Test
    void invalidAmountDoesNotProduceCanonicalEvent() {
        OrderCreatedV2 invalid = new OrderCreatedV2(
                "evt-order-bad", "tenant-a",
                "ORDER-BAD", -1, "VND", null);

        InvalidOrderSchemaException error = assertThrows(
                InvalidOrderSchemaException.class,
                () -> normalizer.fromV2(
                        MessageBuilder.withPayload(invalid)
                                .setHeader("schemaVersion", "2")
                                .build()));

        assertEquals("INVALID_AMOUNT", error.reasonCode());
    }
}
~~~

### 13.1. Equality test không chứng minh hoàn toàn schema compatibility

Test hai DTO có cùng canonical payload xác nhận **mapping của các giá trị chọn lọc**, không chứng minh mọi schema trong registry đều tương thích. Cần bổ sung:

- Contract/schema validation test với bản payload thật.
- Test optional/unknown fields.
- Test money units, overflow và currency behavior.
- Test null/blank/invalid IDs.
- Test serialized envelope và metadata provenance.
- Test trong cùng runtime/framework version được deploy.

### 13.2. Metadata không được biến source event thành event mới

Trong test, `eventId` không đổi. Điều này cần đặc biệt khi downstream dùng `eventId` để chống duplicate sau broker redelivery. `MessageHeaders.ID` của Spring Message có thể khác sau transform; đó **không phải** là lý do tạo business event ID mới.

## 14. Integration test: hai source versions, cùng canonical channel

Unit test mapper không thể phát hiện sai wiring channel, sai expression routing hoặc đặt nhầm transformer. Test này khởi động Spring Integration context thật:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes =
        VersionAwareNormalizerConfiguration.class)
class VersionAwareNormalizerFlowTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.canonical")
    PollableChannel canonical;

    @Autowired
    @Qualifier("orders.unsupported")
    PollableChannel unsupported;

    @Test
    void versionOneIsRoutedAndNormalized() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-v1", "tenant-a",
                "ORDER-101", 250000, "VND");

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "1")
                        .setHeader("traceId", "trace-v1")
                        .build()));

        Message<?> output = canonical.receive(1000);
        assertNotNull(output);
        assertInstanceOf(
                OrderCreatedCanonical.class, output.getPayload());

        OrderCreatedCanonical normalized =
                (OrderCreatedCanonical) output.getPayload();

        assertEquals("evt-v1", normalized.eventId());
        assertEquals("ORDER-101", normalized.orderId());
        assertEquals(250000, normalized.totalMinorUnits());
        assertNull(normalized.customerNote());

        assertEquals(
                "3", output.getHeaders().get("schemaVersion"));
        assertEquals(
                "1", output.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "trace-v1", output.getHeaders().get("traceId"));
        assertNull(unsupported.receive(0));
    }

    @Test
    void versionTwoIsRoutedAndNormalized() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-v2", "tenant-a",
                "ORDER-102", 175000, "VND",
                "Giao giờ hành chính");

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "2")
                        .build()));

        Message<?> output = canonical.receive(1000);
        assertNotNull(output);
        assertInstanceOf(
                OrderCreatedCanonical.class, output.getPayload());

        OrderCreatedCanonical normalized =
                (OrderCreatedCanonical) output.getPayload();

        assertEquals("ORDER-102", normalized.orderId());
        assertEquals(
                "Giao giờ hành chính", normalized.customerNote());
        assertEquals(
                "2", output.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "3", output.getHeaders().get("schemaVersion"));
        assertNull(unsupported.receive(0));
    }

    @Test
    void unknownVersionIsNotSentToCanonicalHandler() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-unknown", "tenant-a",
                "ORDER-999", 10000, "VND", null);

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "99")
                        .build()));

        Message<?> rejected = unsupported.receive(1000);
        assertNotNull(rejected);
        assertEquals(event, rejected.getPayload());
        assertNull(canonical.receive(0));
    }
}
~~~

Test trên xác minh:

- Input v1 và v2 đều tạo **canonical DTO cùng kiểu**.
- Cả hai đi qua **đúng version route** và hội tụ về `orders.canonical`.
- Current `schemaVersion` được cập nhật thành `"3"`.
- `sourceSchemaVersion` giúp biết v1 hay v2 đã được nhận.
- Unknown version không được đưa vào business canonical channel.

### 14.1. Integration test cho header/payload không khớp

Thêm test tạo một `OrderCreatedV1` nhưng đặt header `schemaVersion="2"`. Router sẽ đưa tới channel `orders.v2`; `fromV2` phải từ chối do payload không phải `OrderCreatedV2`. Với `DirectChannel`, exception có thể lan về caller của `send()`, có thể được Spring messaging layer bọc lại.

~~~java
@Test
void forgedVersionHeaderIsRejected() {
    OrderCreatedV1 payload = new OrderCreatedV1(
            "evt-mismatch", "tenant-a",
            "ORDER-104", 10000, "VND");

    assertThrows(
            RuntimeException.class,
            () -> input.send(
                MessageBuilder.withPayload(payload)
                        .setHeader("schemaVersion", "2")
                        .build()));

    assertNull(canonical.receive(0));
}
~~~

Đoạn là **phương thức bổ sung bên trong test class** ở trên. Nếu cần assert reason code, duyệt cause chain tìm `InvalidOrderSchemaException` vì framework có thể wrap exception.

### 14.2. Test isolation

Khi test class dùng shared ApplicationContext, `QueueChannel` có thể còn message từ một test trước nếu test thất bại chưa drain. Dùng unique event IDs, drain queues trong `@AfterEach` hoặc cô lập context. Không chạy kiểm thử song song trên cùng named channels nếu chưa kiểm soát state.

### 14.3. Test chưa bao gồm broker thực tế

Các channels ở ví dụ dùng in-memory DirectChannel/QueueChannel. Test không chứng minh:

- Payload JSON được decode đúng ở adapter thực tế.
- Schema registry lookup hoạt động.
- Broker retry, offset, ACK hoặc DLQ.
- Cross-JVM serialization của headers.
- Hành vi khi producer nâng cấp đúng lúc consumer restart.

Các vấn đề đó cần contract/integration tests riêng với transport và schema registry dùng thật.

## 15. Unknown, missing và conflicting versions

Một hệ thống chịu lỗi tốt **không default unknown version thành v2** và không drop im lặng message cần audit.

| Input | Hành động khuyến nghị | Có retry nguyên message không? |
|---|---|---|
| Version "1" + payload v1 hợp lệ | Normalize vào canonical | Không cần |
| Version "2" + payload v2 hợp lệ | Normalize vào canonical | Không cần |
| Version "9" không hỗ trợ | Unsupported-version path, cảnh báo | Không, trừ khi rollout sắp có adapter |
| Thiếu version | Reject hoặc legacy policy **được công bố** | Thường không nếu contract yêu cầu version |
| Header "2", payload v1 | Reject/contract violation | Không tự đoán |
| Version "2", field bắt buộc thiếu | Validation error/quarantine | Không retry vô hạn |
| Registry unavailable | Infrastructure failure | Bounded retry/backoff |
| Decoder gặp loại sai | Format/schema error | Không retry y nguyên |
| TenantId không khớp auth | Security denial | Không bypass bằng đổi version |
| Chuyển unit money bị overflow | Reject, audit | Không clamp im lặng |

### 15.1. Fallback có chủ đích khác suy đoán

Một legacy producer thực sự không có version có thể được hỗ trợ bằng **hợp đồng ingress riêng**:

~~~text
legacy-queue-v1 (chỉ producer v1)
  -> adapter xác thực nguồn
  -> gắn schemaVersion="1"
  -> normalizer
~~~

Đó là một **policy rõ** dựa trên endpoint đáng tin; nó khác việc nhận arbitrary external message thiếu version rồi đoán từ field names.

### 15.2. Không tự coerce version "2.0" hoặc số 2 thành "2"

Nếu contract ghi String `"2"`, hãy chọn một điểm **adapter normalization** để chuyển các biểu diễn đã được chấp nhận, hoặc reject. Không để router dùng `"2"` nhưng Transformer chấp nhận `2` tùy nơi: lúc ấy một message có thể route đúng nhưng validate sai hoặc ngược lại.

### 15.3. Unsupported channel cần bounded capacity

`orders.unsupported` trong ví dụ chỉ là `QueueChannel` cho test. Trong production, queue phải có capacity, retention/expiry và consumer/quarantine flow. Nếu không, unknown version xuất hiện liên tục có thể làm nghẽn bộ nhớ.

Một unsupported message nên có **version, event type, producer ID, reason code, nhận diện event theo policy**, không cần lưu toàn bộ PII vào log.

## 16. Normalizer và Content-based Router/Filter

Nếu Filter/Router được đặt **trước Normalizer** và trực tiếp đọc field version-specific:

~~~java
// Code này không chạy được trên OrderCreatedV1.
boolean eligible(OrderCreatedV2 v2) {
    return v2.totalMinorUnits() > 100000;
}
~~~

nó sẽ không xử lý được payload v1. Thông thường:

~~~text
Version-aware decoding
  -> Normalizer
  -> Canonical validation
  -> Filter business eligibility
  -> Router xử lý tiếp
~~~

### 16.1. Trường hợp phải Filter trước Normalizer

Có thể muốn chặn malformed message, oversized payload hoặc unauthorized tenant **trước** khi deserialize và normalize. Đó là **security/ingress validation** — không phải business Filter phụ thuộc vào canonical fields.

Ví dụ:

- Giới hạn kích thước raw input.
- Xác thực nguồn và tenant.
- Chỉ cho phép event types được đăng ký.
- Kiểm tra magic bytes/format marker.
- Từ chối schemaVersion ngoài allowlist.

Sau đó Normalizer mới map những source payload hợp lệ về contract chung.

### 16.2. Nếu cùng business rule nhưng hai cách biểu diễn?

Thay vì viết hai `Filter` cho v1/v2, chuyển cả hai về canonical rồi dùng **một Filter**. Tuy nhiên nếu v1 không mang một field bắt buộc cho Filter, không tự fill field đó; phải có legacy rule riêng, enrich đáng tin hoặc không nhận loại message ấy theo business contract.

## 17. Correlation và Aggregator khi source versions trộn lẫn

Một order có thể được tạo bằng schema v1, PaymentCaptured phát v2, InventoryReserved phát v3. Aggregator cần gom theo **business group identity**, chẳng hạn `(tenantId, orderId)` — không phải theo schemaVersion.

~~~mermaid
flowchart LR
    O1["OrderCreated v1"] --> N1["Order Normalizer"]
    P2["PaymentCaptured v2"] --> N2["Payment Normalizer"]
    I3["InventoryReserved v3"] --> N3["Inventory Normalizer"]
    N1 --> A["Aggregator by tenantId+orderId"]
    N2 --> A
    N3 --> A
    A --> OUT["OrderReady"]
~~~

### 17.1. Không dùng source version làm correlation key

~~~text
Group(schemaVersion=1):
  OrderCreated for 100 orders

Group(schemaVersion=2):
  PaymentCaptured for 100 orders
~~~

Đây là một cách **trộn nhiều nghiệp vụ** rất nguy hiểm. Version dùng để chọn decoder/transformer, còn correlation key dùng để định danh **những message thuộc cùng một business unit**.

### 17.2. Normalization phải giữ ổn định IDs

Nếu v1 `orderNo="ORDER-101"` và v2 `orderId="ORDER-101"` cùng nói về một đơn, canonical `orderId` phải như nhau. Không chuẩn hóa bằng cách tự tạo order ID mới từ random, timestamp hoặc email. Nếu external ID cần mapping sang canonical internal ID, dùng trusted mapping trước aggregation và kiểm thử key consistency.

### 17.3. Sequence metadata không phải schema version

Splitter tạo `sequenceNumber` và `sequenceSize` theo số part; chúng không phải schema version. Normalizer không được thay các sequence headers hoặc `correlationId` bằng source schema version. Nếu Transformer tạo Message mới, cần giữ headers cần thiết theo hợp đồng và không làm mất sequence metadata khi downstream Resequencer/Aggregator cần.

## 18. Idempotent Receiver và replay khi Normalizer nâng cấp

Một event có thể được broker phát lại sau khi producer hoặc consumer đã upgrade.

~~~text
First delivery:
  OrderCreatedV1(eventId=evt-1001)
  -> Canonical v3
  -> Business action

Redelivery:
  OrderCreatedV1(eventId=evt-1001)
  -> Canonical v3
  -> Idempotent receiver skips already applied event
~~~

**Đừng tạo eventId mới trong normalizer.** Nếu một consumer tính dedup key từ serialized canonical JSON, thay đổi mapping hoặc source version có thể tạo key khác dù cùng business event. Nên dùng stable `(tenantId, sourceId, eventId, operationType)` và fingerprint contract để so nội dung nghiệp vụ.

### 18.1. Same event ID nhưng source schema thay đổi

Một event có thể được republish thành schema v2 nhưng giữ business event ID. Khi đó:

- Normalizer cần tạo canonical result có cùng ý nghĩa.
- Idempotent Receiver cần nhận ra đây là **cùng event**, không xử lý lại side effect.
- Nếu cùng event ID nhưng amount khác, cần **conflict/reconciliation** chứ không silent skip.
- Có thể lưu canonical business fingerprint và normalized schema target version để audit.

### 18.2. Không kết luận pure mapping là exactly-once

Normalizer không tự xử lý broker redelivery, local/remote transaction hay ACK. Dù mapping deterministic, side effect downstream vẫn có thể chạy hai lần nếu thiếu idempotency.

## 19. Versioned normalization và error handling

Một Normalizer có thể thất bại theo những loại khác nhau:

| Lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Unsupported source version | "9" chưa hỗ trợ | Quarantine/reject rõ, không giả version khác |
| Payload/header mismatch | Header 2, object v1 | Non-retryable validation error |
| Missing required ID | eventId trống | Non-retryable contract failure |
| Unit conversion failure | Vượt giới hạn số nguyên | Reject, không làm tròn âm thầm |
| Schema registry outage | Không tải được schema | Bounded retry |
| Mapping service timeout | Không resolve được external ID | Retry hoặc reconcile theo SLA |
| Authorization failure | Tenant không hợp principal | Deny/audit |
| Programming defect | ClassCastException ngoài kiểm soát | Alert, rollback, fix |
| Downstream business failure | DB/transient external API | Error flow riêng, idempotent retry |

### 19.1. DirectChannel vs async channels

Trong cấu hình `VersionAwareNormalizerConfiguration`, các route/transformer chạy qua `DirectChannel`. Exception từ Transformer có thể nổi về sender của `send()` (có thể được bọc trong `MessagingException`).

Khi dùng `ExecutorChannel`/poller/broker listener, lỗi xảy ra trên thread khác, có thể được error handler chuyển thành `ErrorMessage` qua error channel được cấu hình. Không mặc định mọi exception sync tự đi vào global error channel.

### 19.2. Unsupported version khác Filter discard bình thường

Một version ngoài support matrix thường là **contract/rollout issue**, không phải expected business skip. Nếu chỉ drop silently, producer có thể đã phát hàng nghìn events không ai xử lý. Nên có quarantine với reason `UNSUPPORTED_SCHEMA_VERSION` và cảnh báo theo producer/event type.

### 19.3. Không retry vô hạn lỗi deterministic

Nếu transform v2 luôn fail vì field bắt buộc thiếu, retry y nguyên payload không tự sửa schema. Dùng non-retryable rejection/DLQ và thông báo producer. Chỉ retry errors tạm thời như registry/database unavailable; giới hạn attempts/backoff.
## 20. Triển khai nhiều version không gián đoạn

Normalizer hữu ích khi producer và consumer **không thể deploy đồng thời**. Một chiến lược an toàn thường là **expand → migrate → contract**.

~~~mermaid
flowchart TD
    A["T0: Reader hỗ trợ v1"] --> B["T1: Deploy reader hỗ trợ v1 và v2"]
    B --> C["T2: Contract tests và observability"]
    C --> D["T3: Producer bắt đầu phát v2"]
    D --> E["T4: Theo dõi backlog v1/v2"]
    E --> F["T5: Producer ngừng phát v1"]
    F --> G["T6: Hết replay window v1, bỏ adapter"]
~~~

Các bước:

1. **Mở rộng consumer trước:** bảo đảm consumer đọc được v1 và v2 trước khi producer phát v2.
2. **Contract test:** gửi message serialized thực của từng source version.
3. **Canary writer v2:** bật ở một phần traffic nếu phù hợp.
4. **Theo dõi:** source version share, mapping errors và consumer lag.
5. **Ngừng producer v1:** nhưng vẫn giữ adapter đọc v1 khi còn backlog.
6. **Xem xét DLQ/history:** chỉ xóa converter v1 khi replay window không còn yêu cầu.
7. **Rollback plan:** nếu producer phải quay lại v1, consumer vẫn có khả năng đọc nó.

### 20.1. Vì sao chưa thể xóa normalizer v1 ngay?

Một message v1 có thể còn ở broker, DLQ hoặc event archive dù producer đã nâng cấp. Xóa v1 adapter quá sớm có thể khiến **reprocessing dữ liệu lịch sử** thất bại.

| Điều kiện trước khi deprecate | Cần xác minh |
|---|---|
| Không còn live writer v1 | Inventory và metrics |
| Broker backlog v1 không còn | Consumer lag/queue |
| DLQ v1 đã giải quyết hoặc có migration | DLQ report |
| Historical replay v1 hết hạn hoặc có reader thay thế | Retention policy |
| Rollback không còn yêu cầu v1 | Deployment runbook |
| Late v1 có outcome rõ | Reject/quarantine contract |

### 20.2. Shadow normalization

Có thể phát một bản **chỉ đọc/so sánh** sang shadow converter để đối chiếu mapping, nhưng shadow branch **không được ghi business DB hay gọi payment API**. Nếu so output bằng hash, cần quy tắc canonical fields và quyền truy cập phù hợp; tránh log dữ liệu cá nhân.

## 21. Schema registry và serialization

Với Avro/Protobuf/JSON Schema, pipeline thường là:

~~~text
Wire bytes + schema metadata
  -> Deserialize bằng schema/reader phù hợp
  -> OrderCreatedV1 / OrderCreatedV2
  -> Version-aware Normalizer
  -> OrderCreatedCanonical
~~~

### 21.1. Schema registry ID khác source schema version

Registry ID có thể định danh một schema cụ thể trong registry, còn subject version là lịch sử evolution. Không tự coi `schemaId=123` là `schemaVersion="123"` hay dùng arithmetic compare để chọn converter.

### 21.2. Decoder và Normalizer có trách nhiệm khác nhau

Một method `fromV1(Message<?>)` đang chờ payload kiểu `OrderCreatedV1`; nó không tự giải mã `byte[]` hay JSON String. Decoder phải kiểm tra schema/format trước, sau đó Router và transformer xử lý semantic mapping.

### 21.3. Compatible schema chưa chắc đúng business meaning

Một thay đổi có thể qua được schema compatibility check nhưng vẫn sai nghiệp vụ:

- Đổi amount từ **major** sang **minor units** mà không thay tên field.
- Trường status có nghĩa mới.
- Default không đúng với event lịch sử.
- Giá trị enum cũ bị diễn giải khác.
- Field optional ở cú pháp nhưng thực tế business handler cần nó.

Cần cả **schema validation** lẫn **semantic normalization tests**.

### 21.4. Canonical version thay đổi là một lần migration khác

~~~text
Source v1 -> Canonical v3
Source v2 -> Canonical v3

Sau này:
Source v1 -> Canonical v4
Source v2 -> Canonical v4
Source v3 -> Canonical v4
~~~

Khi canonical v3 đổi thành v4, **mọi converter và downstream consumer** có thể cần cập nhật. Việc hỗ trợ nhiều source versions không tự bảo đảm canonical contract mới tương thích.

## 22. Lossy transformation và mapping không đủ thông tin

Một Normalizer không phải lúc nào có thể biến đổi lossless.

| Loại field | Ví dụ | Quy tắc |
|---|---|---|
| Required ở mọi version | eventId, orderId | Validate; thiếu thì reject |
| Optional | customerNote | Dùng null/optional theo contract |
| Đổi tên | orderNo → orderId | Map đúng danh tính |
| Đổi đơn vị | major → minor amount | Conversion có scale/rounding |
| Deprecated | displayName cũ | Không dùng thay business ID |
| Security-sensitive | accessToken/PII | Không copy tùy tiện |
| Technical metadata | contentType/schemaVersion | Cập nhật theo output format |

### 22.1. Không tự bịa business defaults

Nếu source v1 không có `customerNote`, không được tự đặt `"Khách muốn giao sớm"` để làm output thỏa validation. Trong ví dụ, v1 map sang `null` để bảo toàn ý nghĩa "không có thông tin".

Nếu canonical bắt buộc có một field mà source không cung cấp, có thể:

1. Thay canonical contract để biểu diễn unknown.
2. Enrich từ nguồn tin cậy nếu nghiệp vụ cho phép.
3. Backfill/migrate dữ liệu.
4. Reject với reason `UNMAPPABLE_REQUIRED_FIELD`.

### 22.2. Money semantics và overflow

Ví dụ bài dùng **minor units** cho cả v1/v2. Nếu thực tế một schema gửi major units dạng decimal, conversion phải xét currency scale và kiểm tra overflow, không dùng phép ép float tùy tiện:

~~~java
// Anti-pattern: double có sai số, currency scale không thống nhất.
long minor = (long) (majorAsDouble * 100);
~~~

USD thường có 2 chữ số thập phân, JPY và VND không giống USD. Không nhân tất cả currency với 100. Đây là thay đổi **ngữ nghĩa**, cần test boundary, rounding và overflow theo hợp đồng.

### 22.3. Records và mutable nested payload

Một Java record chứa `String` và `long` là minh họa tốt. Nhưng record có `byte[]`, `Map` hoặc list mutable không tự có deep immutability. Khi lưu vào store hoặc chuyển qua nhiều handler, cân nhắc defensive copy/snapshot.

## 23. Security và provenance của version/header

**Version header không phải bằng chứng được phép gửi event.** Một client gửi `schemaVersion=2` vẫn có thể có payload sai hoặc quyền tenant sai.

Tại ingress cần:

- Authenticate nguồn, kiểm tra tenant.
- Verify event type và schema/serializer metadata.
- Validate header/payload version.
- Enforce authorization trước side effects.
- Có replay/idempotency protection.
- Không log raw payload, Authorization hoặc access tokens.

### 23.1. Header allowlist

Ví dụ input:

~~~text
headers:
  schemaVersion=1
  contentType=application/legacy-order-json
  Authorization=Bearer SECRET
  traceId=trace-1001
  businessCorrelationId=ORDER-101
~~~

Sau khi chuyển payload thành Java DTO canonical, `contentType` gốc có thể không còn đúng; `Authorization` không nên được copy qua mọi channel. Normalizer ở mục 11 chỉ giữ **các headers được chọn**, cập nhật current version và source provenance.

Trong Gateway request-reply, các header như `replyChannel`/`errorChannel` có thể cần xử lý khác. Không chuyển đối tượng channel nội bộ qua broker cross-JVM một cách mù quáng.

### 23.2. Unsupported không đồng nghĩa bỏ an toàn

Khi nhận một unknown version, log dạng tối thiểu:

~~~text
flow=order-normalizer
eventType=OrderCreated
sourceSchemaVersion=9
producer=order-service
outcome=REJECTED_UNSUPPORTED
reasonCode=UNSUPPORTED_SCHEMA_VERSION
traceId=trace-2001
~~~

Quarantine payload gốc (nếu bắt buộc) cần encryption, retention, access control và redaction thích hợp. Một error message chứa nguyên JSON có PII không nên nằm ở dashboard công khai.

## 24. Hiệu năng, backpressure và độ bền

Các chi phí trong Normalizer có thể nằm ở:

- Deserialize payload lớn.
- Lookup schema registry lặp.
- Tra external business ID qua network.
- Validation/transform phức tạp.
- Copy nhiều headers/collections.
- Unsupported queue bị backlog.
- Canonical downstream xử lý chậm.

Hướng thiết kế:

1. Cache schema lookup có kiểm soát version.
2. Pure converter, tránh remote calls không cần.
3. Bounded queues và backpressure/rate limiting.
4. Encode canonical DTO tại outbound boundary phù hợp.
5. Unsupported/quarantine flow có capacity, expiry và consumer.
6. Metrics độ trễ theo source schema version.
7. Nếu parallelize, bảo toàn business ordering/correlation bằng cơ chế riêng.

### 24.1. Schema version không phải ordering key

Nếu v1 và v2 được xử lý ở hai executors, output có thể ra không đúng thứ tự đến. Không sắp message theo `schemaVersion` vì đó là version *format*. Khi cần thứ tự business, sử dụng `aggregateRevision`, `sequenceNumber` và correlation phù hợp.

### 24.2. Retry và durability

`DirectChannel`/`QueueChannel` ở demo không tự mang durability qua restart. Production cần broker/persistent storage và ACK theo transaction phù hợp nếu thông điệp không được phép mất. Normalizer deterministic giúp replay được nhưng không thay idempotency của downstream.

## 25. Observability cho migration nhiều version

| Metric | Nội dung | Label nên dùng |
|---|---|---|
| `normalizer_received_total` | Số input theo source version | eventType, version |
| `normalizer_success_total` | Normalize thành công | source, canonical version |
| `normalizer_unsupported_total` | Version không hỗ trợ | producer, source version |
| `normalizer_schema_mismatch_total` | Header/payload không khớp | version, reason |
| `normalizer_invalid_payload_total` | Field sai contract | reasonCode |
| `normalizer_latency_seconds` | Thời gian transform | source version |
| `normalizer_output_total` | Canonical messages | canonical version |
| `normalizer_quarantine_total` | Messages cần sửa | reason |
| `normalizer_replay_total` | Message được phát lại | event type |
| `normalizer_downstream_error_total` | Lỗi sau normalization | outcome |

Cần cảnh báo khi:

- Version mới xuất hiện trước khi consumer hỗ trợ.
- `SCHEMA_VERSION_PAYLOAD_MISMATCH` tăng sau đổi decoder.
- V1 và V2 không còn hội tụ cùng business example.
- Event IDs thay đổi khi normalize làm dedup thất bại.
- Backlog v1 còn lớn khi sắp remove legacy adapter.
- Unsupported queue tới ngưỡng dung lượng.

Không dùng `eventId`, `orderId`, `customerId` hay `traceId` làm **metric labels có cardinality vô hạn**. Giữ trong logs/traces có access control, hoặc redaction/hash theo policy.

## 26. Các anti-pattern thường gặp

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Không công bố source schema version | Đoán theo tên field | Version envelope/header đáng tin |
| Header nói v2, payload v1 | Cast sai, data corruption | Validate type/schema |
| Unknown version default sang v2 | Breaking schema bị hiểu sai | Unsupported path |
| Payload canonical v3 nhưng header schemaVersion=1 | Downstream decode sai | Ghi target version + source provenance |
| Lẫn app release và schema version | Đổi deploy là đổi route | Version contract độc lập |
| Dùng order revision làm source version | Business update gây route khác | Tách hai khái niệm |
| Tạo eventId mới trong transform | Replay chạy duplicate | Giữ stable event ID |
| Dùng schemaVersion làm correlation key | Trộn hoặc tách nhóm sai | Business key |
| Bịa field bắt buộc khi v1 thiếu | Sai dữ liệu | Optional/enrich/reject |
| Convert amount bằng double | Lệch tiền | Minor units/BigDecimal |
| Copy toàn bộ headers | Lộ secrets/stale contentType | Allowlist |
| Reader có decoder v2 nhưng không có mapper | Không hội tụ canonical | End-to-end test |
| Writer phát v2 trước reader support | Unsupported events | Expand consumer first |
| Xóa v1 converter quá sớm | DLQ/replay lịch sử fail | Retention-aware removal |
| Chỉ test happy path v2 | Không bắt schema drift | Version matrix |
| Silent drop unknown version | Mất nghiệp vụ | Quarantine, audit, alert |
| Nghĩ Normalizer tự dedup | Replay có side effects trùng | Idempotent Receiver |
| Remote lookup trong mọi transformer | Latency, state drift | Trusted mapping ở ingress |
| Canonical v4 đổi mà không migrate consumer | Downstream break | Canonical rollout |

## 27. Thực hành, bài tập và test matrix

**Bài 1 — Hai schema:** xác định field rename/optional giữa `OrderCreatedV1` và `OrderCreatedV2`.

**Bài 2 — Pure mapper:** chạy `OrderVersionNormalizerTest`, kiểm tra v1/v2 về cùng canonical DTO và eventId không đổi.

**Bài 3 — Router theo version:** chạy `VersionAwareNormalizerFlowTest`, xác nhận cả hai source versions đi tới canonical channel.

**Bài 4 — Unknown version:** gửi header `"9"` và xác nhận không có canonical output, unsupported channel nhận message.

**Bài 5 — Header mismatch:** đặt version 2 trên DTO v1, test non-retryable contract failure.

**Bài 6 — Missing version:** thiết kế policy explicit cho legacy queue đáng tin và public inbound không version.

**Bài 7 — Invalid IDs:** tạo eventId hoặc orderId blank, mong exception có reasonCode.

**Bài 8 — Optional note:** v1 map note null; v2 giữ note đã gửi. Không tự bịa mặc định.

**Bài 9 — Currency conversion:** giả sử v3 source dùng decimal major units; thiết kế converter theo currency scale/rounding và test USD/VND.

**Bài 10 — Idempotency:** gửi cùng eventId hai lần với MessageHeaders.ID khác; bảo đảm downstream side effect chỉ một lần.

**Bài 11 — Aggregator:** cho Order/Payment/Inventory có source versions khác nhau và group theo tenantId/orderId.

**Bài 12 — Replay v1:** sau producer upgrade, gửi event v1 từ DLQ; chứng minh reader còn hỗ trợ.

**Bài 13 — Schema registry:** test registry unavailable và unknown schema ID, phân biệt retryable/non-retryable.

**Bài 14 — Security:** payload tenantId khác authenticated tenant phải bị reject trước business flow.

**Bài 15 — Header allowlist:** input có Authorization và contentType cũ; canonical output không giữ secrets, có traceId hợp lệ.

**Bài 16 — Performance:** đo độ trễ từng source transformer và backlog unsupported queue.

### Ma trận kiểm thử tối thiểu

| Input | Expected |
|---|---|
| V1 hợp lệ | Canonical v3, rename đúng, note null |
| V2 hợp lệ | Canonical v3, note giữ nguyên |
| V1/V2 cùng logical event | Canonical payload tương đương |
| Version không hỗ trợ | Explicit unsupported outcome |
| Header v2, DTO v1 | Reject, không business side effect |
| Missing version | Reject hoặc explicit trusted legacy policy |
| Thiếu eventId | Validation error |
| Amount âm | Validation error, không sửa mù |
| Currency không hợp lệ | Validation error |
| Tenant không được phép | Security denial |
| Duplicate delivery | Stable eventId, downstream idempotent |
| Replay v1 sau upgrade | Được đọc hoặc có documented migration |
| Registry unavailable | Bounded retry, không drop như invalid |
| Two orders cùng version | Không bị group chung |
| Header có secret | Không copy qua canonical boundary |

### Câu hỏi tự kiểm tra

1. Normalizer EIP thường ghép từ những loại endpoint nào?
2. Vì sao Transformer đơn lẻ chưa chắc đủ giải quyết multi-version inputs?
3. Source schema version và canonical schema version khác nhau thế nào?
4. Business revision có được dùng để route schema không?
5. Vì sao eventId phải giữ nguyên sau normalize?
6. Version header từ client có đáng tin tuyệt đối không?
7. Vì sao không default unknown version sang newest adapter?
8. Khi nào v1 và v2 có thể cùng map về canonical DTO?
9. Source không có note nên làm gì?
10. Field rename khác field đổi unit thế nào?
11. Backward và forward compatibility liên quan reader/writer thế nào?
12. Schema compatible có thể sai business meaning không?
13. Vì sao reader phải mở rộng trước writer upgrade?
14. Khi nào có thể xóa legacy normalizer?
15. DLQ replay liên quan deprecation thế nào?
16. Normalizer có tự đảm bảo exactly-once không?
17. SchemaVersion khác correlationId ở vai trò nào?
18. Filter trước Normalizer có nguy cơ gì?
19. Stale contentType có thể làm gì sai?
20. Registry ID có luôn là version number không?
21. Metric nào chứng minh v1 đã hết?
22. Test nào phát hiện version header và payload type mâu thuẫn?

## 28. Checklist thiết kế

- [ ] Xác định event type, source versions hỗ trợ và canonical target version.
- [ ] Tách wire format/schema version khỏi business revision/event ID.
- [ ] Có version metadata từ nguồn được xác thực.
- [ ] Có support matrix cho unknown/missing versions.
- [ ] Đối chiếu version header và payload type/schema.
- [ ] Mỗi version có mapping, validation và tests riêng.
- [ ] Outputs cùng canonical contract, không để downstream cast source DTO.
- [ ] Current schemaVersion cập nhật đúng và source provenance được giữ.
- [ ] Business eventId và tenantId/orderId không bị thay mới ngẫu nhiên.
- [ ] Money/currency/units/rounding/overflow được định nghĩa.
- [ ] Không bịa default critical business field.
- [ ] Optional/required/deprecated fields có semantics rõ.
- [ ] Header allowlist tránh Authorization/PII/stale contentType.
- [ ] Authentication/tenant authorization diễn ra trước business side effect.
- [ ] Unknown version vào quarantine/error rõ, không silent drop.
- [ ] Transient registry/network failures được retry có giới hạn.
- [ ] Unsupported queue có capacity, retention, consumer và alerts.
- [ ] Có samples serialized v1/v2 để contract test.
- [ ] Có JUnit mapper tests và integration tests đúng channel.
- [ ] Test null/blank IDs, amount, currency, missing version, mismatch.
- [ ] Test two versions của cùng logical event cho canonical equality.
- [ ] Downstream có idempotency cho redelivery.
- [ ] Aggregator/Resequencer dùng business correlation/sequence, không dùng source version.
- [ ] Canonical evolution có rollout riêng.
- [ ] Reader mở rộng trước writer upgrade.
- [ ] Xóa converter v1 chỉ sau backlog/DLQ/replay window hợp lý.
- [ ] Metrics theo eventType/sourceVersion/canonicalVersion/reason.
- [ ] Không dùng event/order/trace IDs làm metric labels cardinality cao.
- [ ] Có owner và tài liệu contract của từng schema/adapter.

## 29. Tổng kết

**Normalizer và version của message** là bài toán giúp **nhiều phiên bản biểu diễn của cùng nghiệp vụ** hội tụ về **một canonical contract**. Trong Spring Integration, một thiết kế rõ ràng dùng Router theo version đã kiểm chứng, Transformer chuyên biệt từng source schema và một canonical channel để downstream không phải rẽ nhánh theo v1/v2.

Cần phân biệt source schema version dùng cho decoder/transformer, canonical version dùng cho contract nội bộ, business revision dùng cho thứ tự/trạng thái nghiệp vụ và eventId dùng cho idempotency. Không lấy version làm correlation key; không tạo business ID mới khi normalize. Khi đổi tên/kiểu/đơn vị field, phải bảo toàn **ý nghĩa** chứ không chỉ tạo DTO compile được.

Để nâng cấp đáng tin trong **SPRING_INTEGRATION_PATTERN**, hãy triển khai theo **expand consumer → migrate producer → drain old data → remove old adapter**, có policy rõ cho unknown/missing versions, bảo vệ headers, kiểm thử replay và quan sát version distribution. Normalizer đúng giúp Router, Filter, Transformer, Aggregator, Gateway, retry và error channel phối hợp qua các lần nâng cấp mà không làm mất business events hoặc hiểu sai dữ liệu.

### Tài liệu tham khảo

- Enterprise Integration Patterns — Normalizer: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Apache Avro Specification: https://avro.apache.org/docs/current/specification/
- Protocol Buffers — Proto3 Guide: https://protobuf.dev/programming-guides/proto3/
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/





