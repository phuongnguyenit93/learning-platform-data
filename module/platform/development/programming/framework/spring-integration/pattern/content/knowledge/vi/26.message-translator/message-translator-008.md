# Lỗi mapping và thông tin chẩn đoán

## 1. Bài toán: một lỗi chuyển đổi bị che khuất bởi exception chung

Hệ thống nhận sự kiện đơn hàng từ đối tác và chuyển thành message chuẩn cho Pricing/Inventory:

~~~json
{
  "schemaVersion": "2",
  "eventId": "EV-701",
  "orderId": "O-701",
  "currency": "USD",
  "totalAmount": "129.99",
  "createdAt": "2026-11-20T09:30:00Z"
}
~~~

Message Translator chuyển dữ liệu về `CanonicalOrder`. Nhưng producer thỉnh thoảng gửi:

~~~json
{
  "schemaVersion": "2",
  "eventId": "EV-702",
  "orderId": "O-702",
  "currency": "USD",
  "totalAmount": "one hundred",
  "createdAt": "2026-11-20T09:30:00Z"
}
~~~

Nếu Transformer chỉ ném `NumberFormatException`, dashboard có thể ghi:

~~~text
ERROR: Message handling failed
Caused by: NumberFormatException
~~~

Thông tin trên không đủ để biết **source/schema nào lỗi, field nào sai, lỗi có retry được không, message được xử lý ở endpoint nào và cần sửa dữ liệu gì**. Ngược lại, log toàn bộ payload để chẩn đoán có thể làm lộ email, địa chỉ, thông tin thanh toán hoặc token.

Một thông tin lỗi hữu ích hơn:

~~~text
outcome=REJECTED_PERMANENT
stage=FIELD_CONVERSION
reasonCode=INVALID_AMOUNT_FORMAT
fieldPath=totalAmount
sourceSystem=PARTNER_A
sourceSchemaVersion=2
eventId=EV-702
endpoint=translator.partner.v2
retryable=false
~~~

**Message Translator** là thành phần chuyển biểu diễn của message, thường bằng một **Transformer** trong Spring Integration. Nó nên chuyển đổi **đúng hợp đồng hoặc báo lỗi có cấu trúc**; tuyệt đối không biến dữ liệu sai thành giá trị hợp lệ giả, hoặc retry vô hạn khi lỗi không thể tự sửa.

~~~mermaid
flowchart TD
    SRC["Partner event"] --> DEC{"Decode + validate source contract"}
    DEC -->|"Lỗi raw/schema"| INGRESS["Ingress rejection"]
    DEC -->|"Hợp lệ"| TRANS["Message Translator / Transformer"]
    TRANS -->|"Mapping OK"| CAN["CanonicalOrder"]
    TRANS -->|"Mapping lỗi"| CLASS{"Phân loại"}
    CLASS -->|"Permanent input"| REJECT["Reject / quarantine / typed error"]
    CLASS -->|"Transient dependency"| RETRY["Retry bounded"]
    CLASS -->|"Mapper defect"| ALERT["Error channel + alert"]
    CAN --> DOWN["Business flow"]
~~~

Bài thuộc chương **Message translator** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng message flow ít phụ thuộc và dễ mở rộng, thực hành **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý.

**Mục tiêu:** nhận diện từng loại lỗi mapping, tạo diagnostic contract an toàn, triển khai Transformer Java và Spring Integration Java DSL, hiểu `MessagingException`/`ErrorMessage` và các ranh giới đồng bộ–bất đồng bộ, quyết định retry/DLQ/Gateway response, giữ correlation, và kiểm thử được cả lỗi lẫn thông tin chẩn đoán.

## 2. Message Translator chuyển gì, và không giải quyết gì?

Theo Enterprise Integration Patterns, **Message Translator** chuyển một message sang định dạng mà receiver hiểu được. Ví dụ:

~~~text
PartnerOrderV2
  orderId
  currency
  totalAmount: "129.99"
  createdAt: ISO string

→ Message Translator

CanonicalOrder
  businessId
  money(currency, BigDecimal)
  orderedAt: Instant
~~~

Chuyển đổi có thể gồm **đổi tên field, đổi kiểu, chuẩn hóa đơn vị, cấu trúc nested object, enum, timestamp**, và có thể duy trì metadata cần thiết.

**Không phải nhiệm vụ tự động của Translator:**

- Xác thực mọi quyền nghiệp vụ thay cho security layer.
- Sửa data sai bằng cách tự đoán amount/currency.
- Retry external service không giới hạn.
- Tạo một correlation ID mới cho mỗi attempt.
- Đảm bảo exactly-once cho side effect sau Transformer.
- Tự gom nhiều messages như Aggregator.
- Tự chọn route khi có nhiều input schema nếu chưa cấu hình Router.

**Với nhiều source formats**, pattern **Normalizer** thường là **Router + nhiều Message Translators/Transformers** cùng xuất một canonical contract. Lỗi mapping cần được gắn với **source và version chính xác**, không chỉ tên class Transformer.

## 3. Một taxonomy lỗi mapping có thể vận hành

| Nhóm lỗi | Ví dụ | Giai đoạn | Retry cùng message? |
|---|---|---|---|
| **DECODE** | JSON syntax sai, bytes/encoding hỏng | Trước hoặc tại inbound adapter | Không, nếu bytes không đổi |
| **UNSUPPORTED_SCHEMA** | `schemaVersion=9`, chỉ hỗ trợ 1/2 | Router/contract validation | Không retry nóng |
| **MISSING_REQUIRED_FIELD** | Không có `orderId` | Field extraction | Không |
| **EXPLICIT_NULL_NOT_ALLOWED** | `currency:null` | Source contract validation | Không |
| **INVALID_FIELD_TYPE** | `totalAmount: []` | Decode/field extraction | Không |
| **INVALID_FIELD_FORMAT** | `"one hundred"` là amount | Conversion | Không |
| **OUT_OF_RANGE** | Quantity âm, amount vượt giới hạn | Conversion/validation | Không |
| **UNKNOWN_ENUM_VALUE** | Currency/code không được chấp nhận | Mapping/domain contract | Không, trừ khi contract được nâng cấp |
| **AMBIGUOUS_MAPPING** | Hai field cùng có nhưng mâu thuẫn | Schema migration | Không đoán |
| **ENRICHMENT_UNAVAILABLE** | Lookup service 503 | Phụ thuộc ngoại vi | Có điều kiện, có backoff |
| **UNKNOWN_REMOTE_OUTCOME** | Lookup/remote mutation timeout sau commit khả dĩ | Boundary ngoại vi | Reconcile trước khi retry mù |
| **MAPPER_DEFECT** | `NullPointerException` do bug mapping | Code/application | Không gán nhầm thành input lỗi |
| **RESOURCE_EXHAUSTED** | Message quá lớn/CPU limit | Ingress/quota/infrastructure | Phân loại theo nguyên nhân |

**Permanent** nghĩa là retry **cùng payload, cùng mapper version** không thể tự sửa được; điều đó không có nghĩa bị cấm reprocess sau khi producer sửa dữ liệu hoặc ứng dụng cập nhật schema.

**Transient** nghĩa là nguyên nhân có thể phục hồi mà không đổi payload. Nhưng kết quả của một call có side effect đôi khi là **unknown**, không thể chỉ nhìn timeout rồi gửi lại thao tác nguy hiểm.

## 4. Lỗi xảy ra trước hay bên trong Translator?

Một raw JSON body có thể hỏng:

~~~text
{"orderId":"O-701","totalAmount":
~~~

Jackson hoặc message converter có thể ném lỗi **trước khi Spring Integration phát được `Message<?>`**. Khi đó `@Transformer` và `errorChannel` của một IntegrationFlow có thể **chưa hề được gọi**.

Phân tầng:

~~~mermaid
flowchart LR
    BYTES["Raw bytes"] --> CONV["Deserializer / Converter"]
    CONV --> OBJ["Source DTO / JsonNode"]
    OBJ --> MAP["Translator / Transformer"]
    MAP --> CAN["Canonical DTO"]
    CAN --> HANDLER["Business handler"]
    CONV --> ERR1["Adapter/container error handling"]
    MAP --> ERR2["Messaging exception boundary"]
    HANDLER --> ERR3["Business/error boundary"]
~~~

Đọc lỗi tại **đúng ranh giới**:

- HTTP: controller/converter error mapping.
- Kafka/AMQP/JMS: deserializer, listener container và recoverer của adapter.
- Spring Integration `Transformer`: message-handling exception tại endpoint.
- Business handler: lỗi nghiệp vụ hoặc hạ tầng sau mapping.

Một test chỉ gọi mapper bằng Java object hợp lệ **không chứng minh** cách adapter xử lý malformed raw bytes.

## 5. Chẩn đoán phải trả lời được sáu câu hỏi

Một diagnostic hữu ích phải cho biết:

1. **Lỗi ở đâu?** Endpoint, stage, source schema/version.
2. **Lỗi gì?** Reason code ổn định, nhóm lỗi và field path.
3. **Input nào?** Event ID và transport reference đáng tin, nếu có.
4. **Logical work nào?** Tenant, business correlation ID, group/member ID (khi đã xác minh).
5. **Có xử lý tiếp được không?** Retryable/permanent/unknown outcome.
6. **Hệ thống đã làm gì?** Rejected, retried, quarantined, failed, acked, hoặc chuyển sang reconciliation.

Không nhất thiết mọi lỗi đều có đủ field. Raw bytes chưa deserialize có thể không có `eventId`; đừng đặt `eventId="UNKNOWN"` rồi dùng nó làm idempotency/correlation key cho hàng nghìn messages lỗi.

**Reason code và metadata đủ dùng** là mục tiêu. Raw payload và stack trace đầy đủ thuộc **logs/quarantine được bảo vệ**, không nên tự động đẩy vào mọi reply hoặc metric tag.

## 6. Catalog reason codes thay vì chỉ dựa vào exception text

Một tập reason codes ví dụ:

| Mã lỗi | Ý nghĩa | Stage |
|---|---|---|
| `UNSUPPORTED_SCHEMA_VERSION` | Version không được hỗ trợ | Contract |
| `MISSING_ORDER_ID` | Không có ID đơn bắt buộc | Extraction |
| `NULL_CURRENCY` | Currency null nhưng contract bắt buộc | Extraction |
| `INVALID_AMOUNT_TYPE` | Amount không phải kiểu được phép | Extraction |
| `INVALID_AMOUNT_FORMAT` | String amount không parse được | Conversion |
| `AMOUNT_OUT_OF_RANGE` | Giá trị tiền vượt range | Validation |
| `INVALID_TIMESTAMP` | Timestamp sai ISO/offset | Conversion |
| `CURRENCY_NOT_SUPPORTED` | Currency không nằm trong allowlist nghiệp vụ | Domain mapping |
| `CONFLICTING_FIELDS` | Field cũ/mới có nội dung mâu thuẫn | Migration |
| `UNTRUSTED_SOURCE_IDENTITY` | Metadata source/tenant không đáng tin | Security boundary |
| `MAPPING_DEPENDENCY_TIMEOUT` | Service phụ thuộc timeout | Enrichment |
| `MAPPING_INTERNAL_ERROR` | Lỗi code không dự kiến | Translator |

**Cách đặt mã** nên độc lập tên Java exception, Jackson implementation và ngôn ngữ hiển thị. Có thể bản địa hóa thông điệp cho người dùng, còn `reasonCode` vẫn ổn định cho integration và dashboard.

Catalog cần versioning khi consumer ngoài hệ thống dựa vào mã lỗi. Đừng tự ghép mã từ tên field người dùng cung cấp mà không validate (có thể tạo cardinality cao hoặc làm lộ dữ liệu).

## 7. Model dữ liệu ví dụ: source và canonical

Java 17+:

~~~java
record PartnerOrderV2(
    String schemaVersion,
    String eventId,
    String orderId,
    String currency,
    String totalAmount,
    String createdAt
) {}

record CanonicalMoney(
    Currency currency,
    BigDecimal amountMajor
) {}

record CanonicalOrder(
    String tenantId,
    String eventId,
    String orderId,
    CanonicalMoney total,
    Instant orderedAt,
    String sourceSystem,
    String sourceSchemaVersion
) {}
~~~

Đây là **DTO ứng dụng**, không phải class có sẵn của Spring Integration. `totalAmount` ở wire dạng string để ví dụ format error rõ; nếu producer gửi JSON number, deserializer/schema cần quy định cách xử lý type (không tự cast array/object thành string).

`tenantId` không lấy tùy ý từ một header client khai báo. Ví dụ sẽ dùng `verifiedTenantId` đã được inbound adapter/authentication xác minh; với multi-tenant, lỗi định danh phải được tách khỏi lỗi mapping format.

## 8. Diagnostic record không chứa raw payload

~~~java
enum MappingStage {
    CONTRACT, FIELD_EXTRACTION, FIELD_CONVERSION,
    CANONICAL_VALIDATION, ENRICHMENT, INTERNAL
}

record MappingDiagnostic(
    String reasonCode,
    MappingStage stage,
    String sourceSystem,
    String sourceSchemaVersion,
    String eventId,
    String fieldPath,
    String endpoint,
    boolean retryable
) {}
~~~

Một diagnostic:

~~~java
new MappingDiagnostic(
    "INVALID_AMOUNT_FORMAT",
    MappingStage.FIELD_CONVERSION,
    "PARTNER_A",
    "2",
    "EV-702",
    "totalAmount",
    "translator.partner.v2",
    false
);
~~~

Trường `fieldPath` là **tên field theo contract** như `totalAmount` hoặc `items[2].quantity`, không phải **giá trị** field. Tránh lưu `rawEmail`, `cardNumber`, `authorizationHeader` hoặc entire original exception vào record public.

Trong distributed flow, có thể thêm `businessCorrelationId`, `quarantineId`, `attemptCount` hoặc `transportReference` ở **log context/metadata bảo vệ**, không nhất thiết đưa mọi thứ vào DTO trả đối tác.

## 9. Exception có kiểu riêng, giữ nguyên reason và cause

Một exception ứng dụng:

~~~java
final class MappingFailure extends RuntimeException {
    private final MappingDiagnostic diagnostic;

    MappingFailure(MappingDiagnostic diagnostic) {
        super(diagnostic.reasonCode());
        this.diagnostic = diagnostic;
    }

    MappingFailure(
            MappingDiagnostic diagnostic, Throwable cause) {
        super(diagnostic.reasonCode(), cause);
        this.diagnostic = diagnostic;
    }

    MappingDiagnostic diagnostic() {
        return diagnostic;
    }
}
~~~

Ưu điểm:

- `getMessage()` chứa **mã lỗi đã kiểm soát**, không phải raw value.
- `getCause()` giữ exception kỹ thuật để điều tra ở logs có quyền.
- `diagnostic()` cung cấp stage, field và retry flag cho Gateway/error handler.

Không biến mọi exception thành `MappingFailure("INVALID_INPUT")`. Với `NullPointerException` do lỗi code, nguyên nhân không nên bị che bằng mã lỗi “khách hàng nhập sai”. Với transient dependency failure, không ép `retryable=false` chỉ để gửi nhanh vào DLQ.

## 10. Factory giúp tạo diagnostic nhất quán

~~~java
final class MappingFailures {
    static MappingFailure permanent(
            String code,
            MappingStage stage,
            PartnerOrderV2 raw,
            String field) {
        return new MappingFailure(
            new MappingDiagnostic(
                code,
                stage,
                "PARTNER_A",
                raw == null ? null : raw.schemaVersion(),
                raw == null ? null : raw.eventId(),
                field,
                "translator.partner.v2",
                false));
    }
}
~~~

Đây là **factory minh họa**, không phải Spring API. Production có thể dùng một catalog typed `ReasonCode` và `SourceContext` thay vì string rời rạc. `eventId` chỉ được tin cậy sau khi validate format/nguồn; với input độc hại, có thể không đưa ID khai báo vào public response.

Một nguyên tắc hữu ích: **dữ liệu chẩn đoán phải được sinh tại nơi phát hiện lỗi**, vì tầng ngoài đôi khi chỉ thấy `MessagingException`, không biết field `totalAmount` nào sai.

## 11. Kiểm tra field trước conversion, không dùng fallback tùy tiện

Một Mapper sai:

~~~java
BigDecimal amount = new BigDecimal(
    raw.totalAmount() == null
        ? "0" : raw.totalAmount());
~~~

Nó **biến missing amount thành zero**, khiến canonical DTO trông hợp lệ. Với đơn hàng có số tiền thật không biết, đây là silent data corruption.

Một extractor rõ:

~~~java
String requiredText(
        String value,
        String reasonCode,
        MappingStage stage,
        PartnerOrderV2 raw,
        String fieldPath) {
    if (value == null || value.isBlank()) {
        throw MappingFailures.permanent(
            reasonCode, stage, raw, fieldPath);
    }
    return value;
}
~~~

Với JSON:

- **Absent**: property không tồn tại.
- **Explicit null**: property tồn tại nhưng value là null.
- **Blank**: value là chuỗi rỗng/toàn khoảng trắng.
- **Zero**: value số 0, có thể hợp lệ theo business contract.

Nếu cần phân biệt absent và explicit null, record nullable đơn giản thường không đủ: dùng `JsonNode.get()`/schema presence tracking hoặc kiểu tri-state. Đừng dùng `asText("")` và âm thầm nhập ba trạng thái thành một.

## 12. Đổi số tiền và timestamp: lỗi phải chỉ đúng field

Một helper chuyển amount:

~~~java
BigDecimal parseAmount(PartnerOrderV2 raw) {
    String text = requiredText(
        raw.totalAmount(),
        "MISSING_AMOUNT",
        MappingStage.FIELD_EXTRACTION,
        raw,
        "totalAmount");

    if (text.length() > 40) {
        throw MappingFailures.permanent(
            "AMOUNT_OUT_OF_RANGE",
            MappingStage.FIELD_CONVERSION,
            raw,
            "totalAmount");
    }
    try {
        BigDecimal amount = new BigDecimal(text);
        if (amount.signum() < 0) {
            throw MappingFailures.permanent(
                "AMOUNT_OUT_OF_RANGE",
                MappingStage.CANONICAL_VALIDATION,
                raw,
                "totalAmount");
        }
        return amount;
    } catch (NumberFormatException ex) {
        throw new MappingFailure(
            new MappingDiagnostic(
                "INVALID_AMOUNT_FORMAT",
                MappingStage.FIELD_CONVERSION,
                "PARTNER_A",
                raw.schemaVersion(),
                raw.eventId(),
                "totalAmount",
                "translator.partner.v2",
                false),
            ex);
    }
}
~~~

**BigDecimal** tránh vấn đề làm tròn của `double`. Nhưng production phải có **currency scale, max precision/range, rounding policy và business semantics** (gross/net, refund...), không chỉ parse string thành công.

Với timestamp, dùng `Instant.parse(...)` khi hợp đồng đòi ISO-8601 timestamp tương ứng và ánh xạ `DateTimeParseException` thành `INVALID_TIMESTAMP`. Không dùng `Instant.now()` để lấp một `createdAt` thiếu: đó là thời điểm xử lý, không phải thời điểm nghiệp vụ.

## 13. Một Translator hoàn chỉnh phải validate source trước khi tạo canonical

Ví dụ mapper ứng dụng kết hợp các helper ở trên:

~~~java
@Component
class PartnerV2Translator {

    CanonicalOrder translate(
            PartnerOrderV2 raw,
            String verifiedTenantId) {
        if (raw == null) {
            throw MappingFailures.permanent(
                "MISSING_SOURCE_PAYLOAD",
                MappingStage.CONTRACT,
                null,
                "$");
        }
        if (!"2".equals(raw.schemaVersion())) {
            throw MappingFailures.permanent(
                "UNSUPPORTED_SCHEMA_VERSION",
                MappingStage.CONTRACT,
                raw,
                "schemaVersion");
        }

        String eventId = requiredText(
            raw.eventId(),
            "MISSING_EVENT_ID",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "eventId");
        String orderId = requiredText(
            raw.orderId(),
            "MISSING_ORDER_ID",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "orderId");
        String iso = requiredText(
            raw.currency(),
            "MISSING_CURRENCY",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "currency");
        Currency currency;
        try {
            currency = Currency.getInstance(iso);
        } catch (IllegalArgumentException invalid) {
            throw MappingFailures.permanent(
                "INVALID_CURRENCY",
                MappingStage.FIELD_CONVERSION,
                raw,
                "currency");
        }

        BigDecimal total = parseAmount(raw);
        String time = requiredText(
            raw.createdAt(),
            "MISSING_TIMESTAMP",
            MappingStage.FIELD_EXTRACTION,
            raw,
            "createdAt");
        Instant created;
        try {
            created = Instant.parse(time);
        } catch (DateTimeParseException invalid) {
            throw MappingFailures.permanent(
                "INVALID_TIMESTAMP",
                MappingStage.FIELD_CONVERSION,
                raw,
                "createdAt");
        }

        if (verifiedTenantId == null
                || verifiedTenantId.isBlank()) {
            throw MappingFailures.permanent(
                "UNTRUSTED_SOURCE_IDENTITY",
                MappingStage.CONTRACT,
                raw,
                "tenant");
        }

        return new CanonicalOrder(
            verifiedTenantId,
            eventId,
            orderId,
            new CanonicalMoney(currency, total),
            created,
            "PARTNER_A",
            "2");
    }
}
~~~

Ví dụ gom các helper `requiredText()` và `parseAmount()` vào class/service phù hợp khi triển khai; các đoạn được trình bày riêng để giải thích từng ranh giới. `verifiedTenantId` phải được đưa vào từ một adapter đã thực hiện authentication/authorization, **không** lấy nguyên `tenantId` do producer khai báo.

Với production, bổ sung kiểm tra định dạng `eventId/orderId`, allowlist currency, scale/precision, canonical version và amount semantics. Việc tạo được `CanonicalOrder` là **khởi đầu của validation**, không phải chứng nhận mọi business rule đã đúng.

## 14. Dùng `@Transformer` trong Spring Integration

Một endpoint tạo canonical payload:

~~~java
@MessageEndpoint
class PartnerOrderTransformer {
    private final PartnerV2Translator translator;

    PartnerOrderTransformer(PartnerV2Translator translator) {
        this.translator = translator;
    }

    @Transformer(
        inputChannel = "translator.partner.v2",
        outputChannel = "translator.canonical")
    public CanonicalOrder translate(
            Message<PartnerOrderV2> request) {
        String verifiedTenantId =
            (String) request.getHeaders()
                .get("verifiedTenantId");
        return translator.translate(
            request.getPayload(), verifiedTenantId);
    }
}
~~~

`verifiedTenantId` trong ví dụ phải được **adapter nội bộ đáng tin** gắn vào sau xác thực, và downstream không được tin một header cùng tên được nhận nguyên vẹn từ external broker/client. Một thiết kế khác có thể đặt tenant đã xác minh trong request envelope thay vì header.

Nếu mapper ném `MappingFailure`, endpoint không nên trả một `CanonicalOrder` toàn trường null hoặc một “success” payload để che lỗi. Lỗi được xử lý ở ranh giới đồng bộ/error channel và được phân loại có chủ đích.

Spring Integration có thể bảo toàn/copy một số request headers khi Transformer tạo reply payload, nhưng **không mặc định mọi header sẽ sống qua custom MessageBuilder, external adapter hay broker**. Cần test correlation và return-address theo topology thật.

## 15. Java DSL: một cách cấu hình thay thế

Thay vì đăng ký endpoint `@Transformer` ở mục 14, có thể cấu hình Java DSL:

~~~java
@Configuration
@EnableIntegration
class PartnerTranslationFlow {

    @Bean
    IntegrationFlow partnerV2Flow(
            PartnerV2Translator mapper) {
        return IntegrationFlow.from("translator.partner.v2")
            .transform(
                Message.class,
                request -> mapper.translate(
                    (PartnerOrderV2) request.getPayload(),
                    (String) request.getHeaders()
                        .get("verifiedTenantId")))
            .channel("translator.canonical")
            .get();
    }
}
~~~

Hai ví dụ là **các cách thay thế**, không đăng ký cả hai cùng consume từ `translator.partner.v2` khi không có ý định dùng competing consumers. Khi triển khai, xác minh overload/cú pháp Java DSL theo phiên bản Spring Integration được chọn.

Translator có thể được test đơn vị **độc lập** Spring context. IntegrationFlow chỉ làm nhiệm vụ lắp ghép channel, chuyển payload, bảo toàn metadata mong muốn và chuyển lỗi sang đúng boundary.

## 16. Lỗi ánh xạ khác lỗi nghiệp vụ phía sau Transformer

Giả sử `CanonicalOrder` đã có currency/amount đúng nhưng Inventory trả `OUT_OF_STOCK`:

~~~text
PartnerOrderV2
  → Translator: OK
  → CanonicalOrder
  → Inventory: OUT_OF_STOCK
~~~

**OUT_OF_STOCK không phải `INVALID_AMOUNT_FORMAT` hoặc lỗi Translator.** Đây là một business outcome từ hệ thống nhận.

Tương tự:

- `CARD_DECLINED` sau Gateway gọi payment service là business rejection.
- `DB_DEADLOCK` khi ghi đơn là infrastructure failure.
- `UNKNOWN_SKU` có thể là business rejection nếu catalog lookup đã trả kết quả đáng tin.
- `HTTP_503` khi tra cứu SKU là transient dependency failure, **không chứng minh SKU không tồn tại**.

Nếu đẩy mọi exception từ downstream vào cùng `translator.errors` rồi gắn `INVALID_SOURCE_PAYLOAD`, metrics không còn ý nghĩa và producer bị yêu cầu sửa dữ liệu không sai.

**Đặt boundary rõ:** Source decode/validation → Translation → Canonical validation → Business. Mỗi lớp có catalog reason codes và ownership phù hợp.

## 17. Spring exception chain: không chỉ đọc message ngoài cùng

Một lỗi do Transformer ném có thể xuất hiện với wrapper từ Spring Messaging/Integration, ví dụ nhóm `MessagingException` hoặc `MessageTransformationException`, cùng nguyên nhân gốc `MappingFailure`.

Một stack biểu diễn khái niệm:

~~~text
MessageTransformationException: failed to transform message
  caused by MappingFailure: INVALID_AMOUNT_FORMAT
    caused by NumberFormatException
~~~

**Đừng gắn logic nghiệp vụ vào chính xác nguyên văn exception message**, vì text phụ thuộc code, framework và locale. Nên tìm **typed exception** trong cause chain, rồi lấy diagnostic ổn định:

~~~java
MappingFailure findMappingFailure(Throwable problem) {
    Set<Throwable> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Throwable current = problem;

    while (current != null && visited.add(current)) {
        if (current instanceof MappingFailure failure) {
            return failure;
        }
        current = current.getCause();
    }
    return null;
}
~~~

Lưu ý đây là helper để **tìm nguyên nhân**, không làm mất exception gốc. Nếu không có `MappingFailure`, đừng mặc nhiên xem đó là `INVALID_AMOUNT_FORMAT`; có thể là lỗi runtime của code, mất kết nối hoặc thất bại từ endpoint khác.

## 18. `failedMessage` hữu ích nhưng không luôn có

Khi exception là `MessagingException`, có thể có reference tới message bị lỗi:

~~~java
Message<?> findFailedMessage(Throwable problem) {
    Set<Throwable> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Throwable current = problem;

    while (current != null && visited.add(current)) {
        if (current instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            return messaging.getFailedMessage();
        }
        current = current.getCause();
    }
    return null;
}
~~~

`failedMessage` giúp điều tra header như `businessCorrelationId`, source schema hoặc transport reference. Nhưng có những trường hợp **không có failedMessage**:

- JSON parser thất bại trước khi tạo Spring Message.
- Một exception không được framework wrap.
- Adapter chỉ truyền thông tin raw bytes/offset.
- Failure xảy ra trong một external callback không liên kết trực tiếp message gốc.

**Không assume `failedMessage.getPayload()` luôn là DTO đúng kiểu.** Có thể payload là `byte[]`, JSON, một ErrorMessage khác, hoặc message đã biến đổi; phải kiểm tra kiểu và giới hạn việc log payload.

## 19. ErrorMessage và error channel trong flow bất đồng bộ

Khi endpoint chạy trong ngữ cảnh asynchronous hoặc được cấu hình error handling, lỗi có thể được chuyển thành `ErrorMessage`:

~~~mermaid
sequenceDiagram
    participant I as Inbound
    participant Q as Queue/Executor
    participant T as Transformer
    participant EC as Error channel
    participant EH as Error handler
    I->>Q: PartnerOrderV2
    Q->>T: Message
    T--xEC: MappingException/Transformation failure
    EC->>EH: ErrorMessage(Throwable)
    EH->>EH: Classify + quarantine/retry policy
~~~

Trong Java, `ErrorMessage` là message mang `Throwable` làm payload. Spring Integration có cơ chế error channel, nhưng **cách exception được gửi tới channel nào phụ thuộc source/poller/gateway/adapter, header và configuration**.

**DirectChannel đồng bộ:** exception thường lan theo caller thread; không mặc định mọi lỗi đồng bộ được đưa vào global `errorChannel`. **ExecutorChannel/poller/listener:** lỗi có thể xuất hiện sau khi upstream `send()` đã trả về; error handler ở đúng async boundary mới có trách nhiệm.

Đừng xem `send() == true` là chứng cứ Translator thành công nếu đường truyền còn executor/broker phía sau.

## 20. Một error handler chỉ trích xuất diagnostics đã được kiểm soát

Ví dụ một Service Activator:

~~~java
@MessageEndpoint
class TranslationErrorHandler {
    private final QuarantineService quarantine;

    TranslationErrorHandler(QuarantineService quarantine) {
        this.quarantine = quarantine;
    }

    @ServiceActivator(inputChannel = "translator.errors")
    public void handle(ErrorMessage errorMessage) {
        Throwable problem = errorMessage.getPayload();
        MappingFailure known = findMappingFailure(problem);
        Message<?> failed = findFailedMessage(problem);

        if (known != null && !known.diagnostic().retryable()) {
            quarantine.recordPermanentFailure(
                known.diagnostic(),
                safeTransportReference(failed));
            return;
        }

        // Không đánh lỗi chưa phân loại là invalid input.
        throw new IllegalStateException(
            "UNCLASSIFIED_TRANSLATION_FAILURE", problem);
    }
}
~~~

`QuarantineService` và `safeTransportReference()` là **abstraction/helper do ứng dụng viết**. Trong ứng dụng thật, chúng phải có durable persistence, limits và authorization. `findMappingFailure()`/`findFailedMessage()` được giải thích ở các mục trước.

Đây là **mẫu phân loại lỗi**, không phải một recoverer triển khai đầy đủ cho mọi broker. Khi handler ném tiếp exception, cần xác định **error channel error policy** để không tạo vòng lặp vô tận. Tốt nhất là tách recovery cho transient errors ở container/retry boundary và terminal quarantine handler.

**Không ACK/drop trước khi record quarantine hoặc trách nhiệm recovery được lưu bền vững.** Nếu quarantine unavailable, phải để transport giữ trách nhiệm theo chính sách phù hợp.

## 21. Đồng bộ: trả diagnostic cho Gateway/HTTP caller

Một Gateway có thể dùng Translator như request–reply:

~~~java
@MessagingGateway(
    defaultRequestChannel = "translator.partner.v2")
interface TranslationGateway {
    CanonicalOrder translate(PartnerOrderV2 event);
}
~~~

Trong flow đồng bộ, exception có thể lan về caller và được API layer chuyển thành response có cấu trúc:

~~~json
{
  "status": "REJECTED",
  "reasonCode": "INVALID_AMOUNT_FORMAT",
  "fieldPath": "totalAmount",
  "sourceSchemaVersion": "2",
  "retryable": false
}
~~~

Không mặc định `MessageTransformationException` được HTTP framework tự động map thành 400/422; bạn phải có exception mapper/controller advice hoặc typed result phù hợp.

**Gateway contract quan trọng:** nếu Filter/Translator chỉ discard message mà không tạo reply, caller có thể **timeout**, làm người dùng tưởng lỗi hạ tầng thay vì input invalid. Có thể chọn fail-fast exception hoặc một kiểu kết quả như `TranslationAccepted | TranslationRejected`; mỗi lựa chọn phải được triển khai thật, không phải chỉ khai báo kiểu trả về.

Đối với async/broker request–reply, `replyChannel`/correlation của gateway có cơ chế riêng. Không dùng một temporary reply channel làm business ID bền vững; đừng serialize JVM channel object vào event để người nhận khôi phục.

## 22. Error routing theo loại lỗi, không theo catch-all

Một classifier:

~~~mermaid
flowchart TD
    E["Lỗi mapping"] --> K{"Typed MappingFailure?"}
    K -->|"Có"| R{"retryable?"}
    R -->|"false"| Q["Permanent reject / quarantine"]
    R -->|"true"| B["Bounded retry + backoff"]
    K -->|"Không"| U{"Hạ tầng hay mapper defect?"}
    U -->|"Transient đã xác minh"| B
    U -->|"Không rõ"| ALERT["Alert + controlled recovery"]
    B --> DONE{"Thành công?"}
    DONE -->|"Có"| OK["Canonical output"]
    DONE -->|"Không"| EX["Exhausted retries / DLQ or workflow"]
~~~

Không nên chỉ dùng:

~~~java
catch (Exception e) {
    throw new MappingFailure(
        permanentDiagnostic("INVALID_INPUT"), e);
}
~~~

Đoạn anti-pattern này che `NullPointerException` do bug, `SQLException` và HTTP timeouts thành lỗi producer. Thay vào đó, chỉ chuyển các exception **đã biết và có ý nghĩa xác định** thành reason code permanent; lỗi còn lại giữ cause chain để xử lý ở đúng recovery policy.

## 23. Retry policy: lỗi dữ liệu không tự sửa qua retry

| Tình huống | Cùng payload + cùng mapper | Hành động |
|---|---|---|
| `INVALID_AMOUNT_FORMAT` | Luôn sai | Reject/quarantine; producer sửa |
| `MISSING_ORDER_ID` | Luôn thiếu | Reject; không retry nóng |
| `UNSUPPORTED_SCHEMA_VERSION` | Chưa hiểu phiên bản | Quarantine/upgrade/migration |
| `ENRICHMENT_UNAVAILABLE` | Có thể phục hồi | Retry bounded + backoff + deadline |
| Mapper logic bug | Không sửa bằng retry nóng | Alert, fix/deploy, reprocess an toàn |
| Remote timeout sau side effect | Outcome chưa rõ | Reconcile/idempotent remote key |
| Dedupe store inaccessible | Chưa biết duplicate hay không | Fail closed/defer nếu side effect không tự idempotent |

Nếu có `RequestHandlerRetryAdvice`, nhớ rằng advice chỉ bao quanh **handler tương ứng**. Nếu Transformer trả về ngay rồi một consumer async khác ném exception, retry advice trên Transformer **không bắt được** lỗi phía sau.

**Không thiết kế nhiều vòng retry chồng nhau vô hạn**: handler retry + broker container retry + workflow retry có thể tạo bão request. Cần tổng attempt budget, deadline, backoff và nơi ghi trạng thái terminal.

## 24. Một DLQ/quarantine record phải chứa đúng thông tin

Đối với lỗi permanent:

~~~text
quarantineId = Q-5701
sourceSystem = PARTNER_A
sourceSchemaVersion = 2
eventId = EV-702
reasonCode = INVALID_AMOUNT_FORMAT
fieldPath = totalAmount
stage = FIELD_CONVERSION
endpoint = translator.partner.v2
transportReference = topic:orders/partition:3/offset:1209
mappingPolicyVersion = v2-map-4
replayStatus = PENDING_REVIEW
payloadReference = protected-object://...
~~~

Không đưa raw full JSON, secrets, token hoặc PII vào mọi log/metrics. Raw payload chỉ lưu ở **protected storage** khi thực sự cần, có encryption, retention, access control, quota, audit và một reference không truy cập công khai.

**Quarantine record khác business processed marker**. Một input bị reject không có nghĩa business operation đã hoàn tất; khi producer gửi bản sửa cần policy cho event version, fingerprint, replay và idempotency.

**Discard channel ≠ DLQ.** Filter discard là message channel nội bộ Spring Integration; broker DLT/DLQ chỉ hình thành khi có adapter/recoverer/publisher cấu hình rõ.

## 25. ACK và DLQ khi input đến từ broker

Một lỗi mapping permanent ở consumer có thể tạo **poison pill**:

~~~text
Broker → PartnerOrderV2 event EV-702
  → Translator: INVALID_AMOUNT_FORMAT
  → container retry cùng payload
  → Translator: INVALID_AMOUNT_FORMAT
  → ... không bao giờ tự thành công
~~~

Broker/container thường không tự hiểu `MappingFailure.retryable=false` trừ khi **error classifier/recoverer** của adapter được cấu hình tương ứng. Một chính sách thực dụng:

| Kết quả | Xử lý trước khi kết thúc source delivery |
|---|---|
| Mapping thành công, downstream commit đúng | ACK/commit offset theo contract |
| Permanent mapping failure | Lưu DLQ/quarantine an toàn rồi ACK theo transport policy |
| Transient failure | Retry bounded/backoff; không ACK mất việc |
| Quarantine/DLQ unavailable | Giữ trách nhiệm recovery; không drop im lặng |
| Unknown remote side effect | Lưu workflow reconciliation, không giả định chưa commit |

**Một thao tác “publish DLQ rồi ACK source” không mặc nhiên atomic** giữa Kafka, RabbitMQ/AMQP và JMS. Cần xem cơ chế transaction/ack của adapter, kiểm thử crash ở ranh giới và có idempotency cho trường hợp phát trùng.

Không nên requeue vô hạn malformed bytes; cũng không nên đặt mọi lỗi infrastructure vào DLQ permanent chỉ vì chúng xuất hiện trong Transformer.

## 26. Bảo toàn identity khi Translator không tạo được output

Một lỗi mapping có thể xảy ra **trước khi có canonical ID**, ví dụ `orderId` bị thiếu. Phải phân biệt:

| ID | Nguồn | Dùng khi lỗi |
|---|---|---|
| `eventId` | Producer contract | Sử dụng nếu đã validate/trust |
| `orderId` | Business payload | Có thể không tồn tại |
| `businessCorrelationId` | Logical processing group | Chỉ sử dụng nếu được kiểm chứng |
| `traceId` | Observability context | Truy vết request, không làm business group key |
| `MessageHeaders.ID` | Spring message instance | Hữu ích nội bộ, không bền qua broker replay |
| `transportReference` | Topic/partition/offset, broker message ID, file location | Có thể truy nguồn raw message |
| `quarantineId` | Record mới tại error flow | Bền cho review/replay lỗi |

Ví dụ một raw message không có eventId:

~~~text
source=PARTNER_A
transportReference=orders.topic/partition-3/offset-1209
quarantineId=Q-5702
reasonCode=MISSING_EVENT_ID
businessCorrelationId=null
~~~

**Không tạo một business correlation key chung như `UNKNOWN` cho mọi lỗi**: Aggregator hoặc log processing có thể vô tình gom hàng nghìn sự cố khác nhau vào một group. Transport/quarantine identity phải tách khỏi group identity.

Header correlation có thể mất khi message đổi kiểu hoặc đi qua broker. Nếu identity cần cho hoạt động phục hồi, mang các field cần thiết trong **wire contract** hoặc lưu mapping durable từ transport ID tới logical ID, không tin rằng mọi header Spring sẽ tự được serialize.

## 27. Splitter: một child mapping lỗi thì parent group đi đâu?

Giả sử Splitter phát ba line tasks:

~~~text
Order O-701 → Splitter L1, L2, L3
L1 → Translator → LineResult success
L2 → Translator → INVALID_QUANTITY_TYPE
L3 → Translator → LineResult success
                             ↓
                         Aggregator
~~~

Nếu Translator của L2 ném exception mà không có recovery outcome, Aggregator có thể **chờ L2 mãi** vì `sequenceSize=3`. Bản thân `errorChannel` không tự sinh một `LineResult` mang correlation và member identity cho group.

~~~mermaid
flowchart TD
    S["Splitter: L1 L2 L3"] --> T["Per-line Translator"]
    T -->|"L1 L3 OK"| OK["LineResult"]
    T -->|"L2 mapping invalid"| ERR["Mapping error"]
    ERR --> DEC{"Policy?"}
    DEC -->|"Fail whole batch"| BATCH["Abort/mark group FAILED"]
    DEC -->|"Allow item outcomes"| FAIL["LineOutcome L2 = FAILED"]
    OK --> AG["Aggregator"]
    FAIL --> AG
    AG --> SUMMARY["OrderSummary PARTIAL/FAILED"]
~~~

Hai cách xử lý:

1. **Validate toàn bộ input trước Splitter** nếu một member malformed làm invalid cả order; tránh fan-out một phần.
2. Nếu nghiệp vụ cho phép xử lý từng dòng, **chuyển lỗi sang typed `LineOutcome`** mang **parent correlation ID, member ID và reasonCode**, rồi chỉ release khi có đúng expected member outcomes.

Không tự sửa `sequenceSize=3` thành 2 chỉ để Aggregator release, và không đếm duplicate L1 thành đủ ba members. Release strategy nên so với **expected member manifest** và trạng thái final của từng member.

## 28. Resequencer và Router không tự sửa mapping lỗi

Một Router có thể chọn Translator theo:

~~~text
source=PARTNER_A, version=2 → translator.partner.v2
source=LEGACY, version=1    → translator.legacy.v1
else                       → unsupported-schema rejection
~~~

**Router** xử lý lựa chọn nhánh. Nó không tự biến một JSON `totalAmount="one hundred"` thành số hợp lệ. Nếu route dựa trên `schemaVersion` giả mạo, message còn có thể đến nhánh sai và gây lỗi khó hiểu.

**Resequencer** xử lý thứ tự message. Nó không tự khôi phục một child không được Transformer phát do lỗi; thiếu sequence number có thể gây gap kéo dài.

**Filter** có thể reject trước Translator, nhưng nếu Filter chỉ trả Boolean, cần nơi tạo `reasonCode`/typed rejection. Với lỗi chuyển đổi phát hiện khi `new BigDecimal(text)` chạy, đó là lỗi Translator, không phải Filter discard trừ khi đã thiết kế validation trước.

**Aggregator** tạo kết quả gộp; nếu một member không có result, cần timeout/failure outcome/recovery. Không gán trách nhiệm sửa malformed payload cho Aggregator.

## 29. Content Enricher không nên che lỗi mapping bằng dữ liệu đoán

Một Translator thiếu `customerCountry` có thể gọi Customer service để bổ sung:

~~~text
Partner event without country
  → Content Enricher lookup(customerId)
  → country=VN
  → CanonicalOrder
~~~

Nhưng cần phân biệt:

- **Missing vì source schema không hỗ trợ:** có thể enrich nếu contract cho phép.
- **Lookup trả 404 đáng tin:** có thể là `CUSTOMER_NOT_FOUND`, một business/contract error.
- **Lookup HTTP 503:** transient infrastructure failure; không đổi thành `country="VN"` chỉ để bypass.
- **Lookup timeout sau remote mutation:** nếu lookup là read-only thì retry có thể an toàn hơn; nếu có side effect, phải dùng idempotency/reconciliation.

Nếu Content Enricher gửi nhiều request song song, mỗi lookup cần **request ID riêng** và mapping tới parent message; không chỉ dùng customerId để ghép replies nếu nhiều orders cùng customer.

Trong diagnostics, thêm `stage=ENRICHMENT`, dependency alias từ whitelist, attempt/deadline. Không đưa access token/URL chứa secret hoặc nguyên văn remote response vào public error.

## 30. Bẫy trong mapping header và payload

Một Transformer có thể nhận message với:

~~~text
headers.correlationId=G-701
headers.sequenceNumber=2
headers.sequenceSize=3
headers.replyChannel=<temporary channel object>
payload.eventId=EV-701
~~~

Khi tạo `Message<?>` mới, có thể cần giữ correlation/sequence metadata cho endpoint kế tiếp. Nhưng **copy tất cả headers không chọn lọc** qua external transport có thể gây lỗi serialize, sai routing hoặc rò nội bộ.

Nguyên tắc:

- **Trong JVM:** kiểm tra cơ chế header propagation của Transformer/MessageBuilder và headers được phép.
- **Qua broker:** whitelist/map đúng kiểu field, đặt business correlation trong wire schema nếu cần phục hồi.
- **Với Gateway:** `replyChannel` là return address kỹ thuật, không phải business correlation key.
- **Với Splitter:** `sequenceNumber/sequenceSize` chỉ có nghĩa trong đúng correlation group.
- **Khi lỗi:** error handler phải biết parent group nếu muốn gửi failure outcome; nếu không có thì quarantine thay vì bịa group.

**Một message đã được normalize không bảo đảm mọi headers còn như cũ.** Test ở đúng output channel và adapter, không chỉ test hàm mapping trả DTO.

## 31. Phân loại lỗi theo severity, không để monitoring đánh lừa

Ví dụ:

~~~text
INVALID_AMOUNT_FORMAT       → permanent input issue
UNSUPPORTED_SCHEMA_VERSION  → producer/consumer contract mismatch
MAPPING_INTERNAL_ERROR      → code defect, cần alert
ENRICHMENT_UNAVAILABLE      → transient dependency issue
UNKNOWN_REMOTE_OUTCOME      → reconciliation required
~~~

Tất cả đều có thể tạo exception, nhưng **không nên có cùng mức cảnh báo và cùng người chịu trách nhiệm**. Một đối tác vừa đổi format amount có thể làm reject rate tăng; một release mới có NullPointerException là mapper defect; một service 503 có thể là outage tạm.

Các dimension được phép gắn:

- sourceSystem từ enum/allowlist;
- schemaVersion đã normalize theo catalog hữu hạn;
- reasonCode, mappingStage, endpoint, outcome;
- retryable flag;
- mappingPolicyVersion.

Không đưa `eventId`, `orderId`, email hoặc raw exception text vào **metric labels** vì cardinality cao và có thể chứa dữ liệu nhạy cảm. ID cụ thể dùng trong structured logs/traces có retention và phân quyền.

## 32. Metrics và tracing cho Message Translator

Các metric **đề xuất**, không phải mặc định Spring Integration:

| Metric | Ý nghĩa |
|---|---|
| `translator.input.count` | Lưu lượng theo source/schema |
| `translator.success.count` | Số canonical messages |
| `translator.mapping.failure.count` | Mapping errors theo reasonCode/stage |
| `translator.decode.failure.count` | Lỗi raw bytes ở ingress |
| `translator.schema.unsupported.count` | Input version chưa hỗ trợ |
| `translator.retry.attempts.count` | Retry amplification |
| `translator.retry.exhausted.count` | Retry budget bị dùng hết |
| `translator.quarantine.pending.count` | Lỗi permanent chưa review |
| `translator.quarantine.write.failure.count` | Không lưu được error evidence |
| `translator.mapping.duration` | Mapping latency |
| `translator.enrichment.timeout.count` | Phụ thuộc bị timeout |
| `translator.canonical.invalid.count` | Output fail canonical validation |
| `translator.correlation.missing.count` | Không khôi phục được group |
| `translator.failure.outcome.count` | Failure results cho Splitter/Aggregator |

Structured log có kiểm soát:

~~~text
eventId=EV-702
sourceSystem=PARTNER_A
sourceSchemaVersion=2
endpoint=translator.partner.v2
mappingPolicyVersion=v2-map-4
stage=FIELD_CONVERSION
reasonCode=INVALID_AMOUNT_FORMAT
fieldPath=totalAmount
retryable=false
outcome=QUARANTINED
transportReference=topic/orders/p3/o1209
~~~

Không log `totalAmount="one hundred"` nếu dữ liệu thực tế có thể chứa PII hoặc secrets ở field tương ứng. Field path và reason code thường đủ để điều tra ban đầu; raw reference chỉ mở theo quyền khi cần.

## 33. Unit test: converter thành công và lỗi format chính xác

JUnit 5, dùng các model ở mục 7–13:

~~~java
@Test
void partnerV2IsTranslatedWithoutLosingAmount() {
    PartnerV2Translator translator = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-701", "O-701", "USD",
        "129.99", "2026-11-20T09:30:00Z");

    CanonicalOrder result =
        translator.translate(raw, "tenant-a");

    assertEquals("O-701", result.orderId());
    assertEquals("EV-701", result.eventId());
    assertEquals(
        Currency.getInstance("USD"),
        result.total().currency());
    assertEquals(
        0,
        new BigDecimal("129.99")
            .compareTo(result.total().amountMajor()));
    assertEquals(
        Instant.parse("2026-11-20T09:30:00Z"),
        result.orderedAt());
}

@Test
void invalidAmountReportsStableCodeAndField() {
    PartnerV2Translator translator = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "one hundred", "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> translator.translate(raw, "tenant-a"));

    assertEquals(
        "INVALID_AMOUNT_FORMAT",
        failure.diagnostic().reasonCode());
    assertEquals(
        "totalAmount",
        failure.diagnostic().fieldPath());
    assertEquals(
        MappingStage.FIELD_CONVERSION,
        failure.diagnostic().stage());
    assertFalse(failure.diagnostic().retryable());
}
~~~

Không chỉ assert exception được ném; phải assert **reasonCode, stage, fieldPath, retryable và event/source context**. Một test chỉ assert `NumberFormatException` dễ vỡ khi implementation đổi và không chứng minh error contract.

## 34. Unit test: missing field, schema version và timestamp

~~~java
@Test
void missingAmountIsNotDefaultedToZero() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-703", "O-703", "USD",
        null, "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "MISSING_AMOUNT",
        failure.diagnostic().reasonCode());
}

@Test
void unknownSchemaVersionIsNotSilentlyAccepted() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "9", "EV-704", "O-704", "USD",
        "10.00", "2026-11-20T09:30:00Z");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "UNSUPPORTED_SCHEMA_VERSION",
        failure.diagnostic().reasonCode());
}

@Test
void invalidTimestampPointsAtCreatedAt() {
    PartnerV2Translator mapper = new PartnerV2Translator();
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-705", "O-705", "USD",
        "10.00", "yesterday");

    MappingFailure failure = assertThrows(
        MappingFailure.class,
        () -> mapper.translate(raw, "tenant-a"));

    assertEquals(
        "INVALID_TIMESTAMP",
        failure.diagnostic().reasonCode());
    assertEquals(
        "createdAt",
        failure.diagnostic().fieldPath());
}
~~~

Test bổ sung cần bao phủ explicit null, blank IDs, negative amount, currency lỗi, amount quá dài, precision/scale và tenant metadata không đáng tin. Không dùng `@Transactional` test nếu nó che behavior commit/retry của downstream.

## 35. Integration test: exception vẫn giữ diagnostic khi qua Transformer

Một test context dùng Java DSL:

~~~java
@Configuration
@EnableIntegration
class TranslatorTestConfig {
    @Bean
    IntegrationFlow testTranslator(PartnerV2Translator mapper) {
        return IntegrationFlow.from("test.partner.in")
            .transform(
                Message.class,
                request -> mapper.translate(
                    (PartnerOrderV2) request.getPayload(),
                    (String) request.getHeaders()
                        .get("verifiedTenantId")))
            .channel("test.partner.out")
            .get();
    }

    @Bean("test.partner.out")
    PollableChannel outputQueue() {
        return new QueueChannel();
    }
}
~~~

Trong test đồng bộ:

~~~java
@Autowired
ApplicationContext context;

@Test
void mapperErrorCanBeRecoveredFromCauseChain() {
    MessageChannel input = context.getBean(
        "test.partner.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.partner.out", PollableChannel.class);

    PartnerOrderV2 malformed = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "bad amount", "2026-11-20T09:30:00Z");
    Message<PartnerOrderV2> request =
        MessageBuilder.withPayload(malformed)
            .setHeader("verifiedTenantId", "tenant-a")
            .setHeader("businessCorrelationId", "G-701")
            .build();

    RuntimeException thrown = assertThrows(
        RuntimeException.class,
        () -> input.send(request));

    MappingFailure failure = findMappingFailure(thrown);
    assertNotNull(failure);
    assertEquals(
        "INVALID_AMOUNT_FORMAT",
        failure.diagnostic().reasonCode());
    assertNull(output.receive(0));
}
~~~

Các helper `findMappingFailure()` và test bean context đã được giới thiệu trước. Test dùng một sync boundary, nên exception có thể lan về caller. Nếu đổi sang `ExecutorChannel`, test phải kiểm tra error channel/container chứ không giả định `send()` sẽ ném exception.

**Không đăng ký cả `@Transformer` và Java DSL cho cùng input channel** trong cùng test nếu không muốn competing consumers. Chạy các cấu hình như những phương án độc lập.

## 36. Test ErrorMessage và failedMessage: thông tin không bị thất lạc

Một test có thể dựng wrapper lỗi mà error handler sẽ gặp:

~~~java
@Test
void errorMessagePreservesMappingDiagnosticAndFailedMessage() {
    PartnerOrderV2 raw = new PartnerOrderV2(
        "2", "EV-702", "O-702", "USD",
        "wrong", "2026-11-20T09:30:00Z");
    Message<PartnerOrderV2> original =
        MessageBuilder.withPayload(raw)
            .setHeader("businessCorrelationId", "G-701")
            .build();

    MappingFailure mapping = MappingFailures.permanent(
        "INVALID_AMOUNT_FORMAT",
        MappingStage.FIELD_CONVERSION,
        raw,
        "totalAmount");

    MessagingException wrapper = new MessagingException(
        original,
        "Transform failed",
        mapping);
    ErrorMessage error = new ErrorMessage(wrapper);

    MappingFailure detected =
        findMappingFailure(error.getPayload());
    Message<?> failed =
        findFailedMessage(error.getPayload());

    assertNotNull(detected);
    assertEquals("INVALID_AMOUNT_FORMAT",
        detected.diagnostic().reasonCode());
    assertNotNull(failed);
    assertEquals("G-701",
        failed.getHeaders().get("businessCorrelationId"));
}
~~~

Test này chứng minh **helper unwrap** với lỗi đã có `MessagingException.getFailedMessage()`, **không chứng minh container thực sẽ đưa mọi lỗi vào error channel**. Cần một integration test với `ExecutorChannel`/poller/broker adapter thực, error channel của nó và recovery strategy.

Thêm test trường hợp `failedMessage==null`: error handler vẫn phải tạo được một sanitized error record từ transport reference nếu có, hoặc báo `UNKNOWN_SOURCE_CONTEXT` thay vì ném `NullPointerException` làm che lỗi gốc.

## 37. Test raw bytes, schema/version và các kiểu dữ liệu lạ

Một test mapper trực tiếp trên `PartnerOrderV2` chỉ thấy object **đã deserialize**. Cần riêng test adapter/deserializer với bytes:

~~~text
Case A: { "eventId":"EV-702","totalAmount":
        → JSON syntax error, trước Transformer

Case B: { "totalAmount": ["129.99"] }
        → wrong JSON type; không được tự cast thành string

Case C: { "schemaVersion":"9", ... }
        → unsupported schema, đúng reasonCode

Case D: { "currency":null, ... }
        → missing/null policy

Case E: payload cực lớn, nested sâu
        → ingress resource limit trước khi tạo object graph
~~~

Có thể dùng strict schema/deserializer settings để tránh Jackson tự ép `123` thành `"123"`. Những phép coercion được bật/tắt phải được kiểm thử theo API/producer contract, không dựa vào hành vi tình cờ của một bản library.

Test cả **broker header mapping** khi event qua Kafka/AMQP: source/version, business ID, correlation và trace context có thực sự còn, có đúng kiểu, có ai tự ghi đè trước khi Mapper chạy?

**Không log toàn bộ raw bytes thất bại** trong test/production khi có dữ liệu nhạy cảm; lưu hash/reference có kiểm soát để audit và tái hiện khi được phép.

## 38. Test lỗi đồng thời, retry và idempotency

Giả sử consumer xử lý song song hai orders:

~~~text
EV-702 → INVALID_AMOUNT_FORMAT → quarantine
EV-703 → valid → canonical output → business commit

Broker redeliver EV-702 và EV-703:
  EV-702 → permanent reject, không vào business
  EV-703 → idempotent business handling, không double commit
~~~

Điều cần chứng minh:

- Lỗi của EV-702 **không làm đổi correlation/event ID** của EV-703.
- Permanent mapping lỗi không bị retry nóng vô hạn.
- Valid message không bị chặn bởi một poison pill sau khi recoverer xử lý.
- Business downstream không thực thi hai lần do redelivery.
- Quarantine không nhận dữ liệu của tenant khác từ header giả mạo.
- Nếu một Mapper branch bị lỗi, các branch khác vẫn hoạt động theo routing/flow isolation đã thiết kế.

Một test concurrency có thể dùng `CountDownLatch` để điều khiển thứ tự, không dựa vào `Thread.sleep` ngẫu nhiên. Với broker thực, thêm test ACK/nack, DLT publish failure và restart giữa các bước durable.

## 39. Ma trận kiểm thử cho mapping và diagnostics

| Tình huống | Expected error/outcome | Điều phải kiểm tra |
|---|---|---|
| Input v2 hợp lệ | `CanonicalOrder` | Amount, currency, timestamp đúng |
| Missing `orderId` | `MISSING_ORDER_ID` | Stage/extraction, fieldPath |
| `totalAmount=null` | `MISSING_AMOUNT` | Không default thành 0 |
| `totalAmount="abc"` | `INVALID_AMOUNT_FORMAT` | Permanent, không output hợp lệ |
| `totalAmount=[]` | `INVALID_AMOUNT_TYPE` | Xảy ra đúng decode/contract boundary |
| Amount quá lớn | `AMOUNT_OUT_OF_RANGE` | Không overflow/truncate |
| Currency invalid | `INVALID_CURRENCY` | Không fallback USD toàn cục |
| Timestamp không chuẩn | `INVALID_TIMESTAMP` | Chỉ đúng field `createdAt` |
| Schema v9 | `UNSUPPORTED_SCHEMA_VERSION` | Không route nhầm v2 |
| JSON syntax sai | Decode failure | Transformer chưa chạy |
| Tenant/header giả | Security rejection | Không tin raw header |
| Mapper ném NPE | Internal defect | Không gán thành lỗi producer |
| Lookup HTTP 503 | Retryable dependency | Bounded attempts, không permanent DLQ sớm |
| Remote result không rõ | Unknown outcome | Reconcile, không retry side effect mù |
| Filter drop invalid input | Discard/typed error | Gateway không timeout vô nghĩa |
| Async Transformer lỗi | ErrorMessage | Diagnostic/correlation đúng |
| Failed message vắng mặt | Sanitized fallback | Handler không crash lần hai |
| DLQ unavailable | Durable recovery | Không ACK mất nguồn |
| Splitter child lỗi | Failure outcome/batch failure | Aggregator không chờ vô hạn |
| Duplicate event sau commit | Idempotent handler | Không side effect lặp |
| Same eventId/different payload | Idempotency key conflict | Không chấp nhận im lặng |
| Schema upgrade | Mapping policy version khác | Replay/migration có kiểm soát |
| Oversized payload | Resource rejection | Không exhaust memory/parser |

Test **mã lỗi** và **phạm vi ảnh hưởng** song song: không chỉ kiểm tra exception, mà còn kiểm tra không có message đi vào business channel, không phát hai kết quả, không làm mất nhóm và không rò raw payload.

## 40. Runbook khi báo lỗi “Message transformation failed”

Một chuỗi điều tra có thể dùng trong incident:

1. **Tìm endpoint và stage:** lỗi trong deserializer hay Transformer? Hay business handler ở sau Translator?
2. **Truy xuất source/version đáng tin:** event đến từ adapter nào, route theo phiên bản nào?
3. **Đọc reasonCode/fieldPath:** là `MISSING_AMOUNT`, `INVALID_AMOUNT_FORMAT` hay `MAPPING_INTERNAL_ERROR`?
4. **Kiểm tra cause chain:** có `MappingFailure` typed, hay chỉ `MessagingException` bọc lỗi hạ tầng?
5. **Xác định retryability:** cùng input + policy có thể thành công sau retry không?
6. **Đối chiếu raw schema khi được phép:** có thay tên field, type, đơn vị, nullability?
7. **Kiểm tra Router:** source/version có bị đưa vào mapper không tương thích?
8. **Kiểm tra header/correlation:** business ID, parent group, member ID có hợp lệ không?
9. **Xem Gateway/error channel:** lỗi được trả cho caller, vào ErrorMessage hay bị drop thành timeout?
10. **Xem broker ACK/DLQ:** permanent poison pill có được chuyển durable chưa; DLQ có down không?
11. **Xem effects đã commit:** nếu lỗi sau Translator trong business handler, có cần idempotent replay không?
12. **Khắc phục và hồi quy:** sửa producer/mapper/schema policy, test raw bytes và canonical result, rồi replay có audit/retention/quotas.

**Đừng sửa sự cố bằng cách catch mọi exception và return default DTO.** Cách này biến lỗi rõ ràng thành dữ liệu sai âm thầm. Cũng đừng xóa hết idempotency markers rồi replay hàng loạt khi chưa kiểm tra side effects đã commit.

## 41. Checklist thiết kế thông tin chẩn đoán trước khi deploy

Một Message Translator có thể vận hành nên bảo đảm:

- Có contract cho source schema, version và canonical output.
- Có phân biệt decode, extraction, conversion, validation và dependency failures.
- Có catalog `reasonCode` ổn định, fieldPath từ whitelist.
- Không coi missing/null/blank/zero là một.
- Không âm thầm default dữ liệu bắt buộc khi thiếu bằng chứng contract.
- Mapping tiền/ngày/enum kiểm tra units, precision, range và timezone.
- Diagnostic nêu `sourceSystem`, `schemaVersion`, `endpoint`, `stage` và `retryable` khi biết được.
- Business IDs/correlation được kiểm chứng, không gắn mọi lỗi vào group `UNKNOWN`.
- Không đưa raw PII/secrets/payload vào public error hoặc metric labels.
- Error classifier phân biệt permanent, transient và unknown outcome.
- Đường Gateway có typed rejection/exception mapper, không timeout vô nghĩa.
- Async error channel/container handler được cấu hình và test.
- Quarantine/DLQ durable, có quyền, quota, retention và replay policy.
- Splitter/Aggregator có failure outcome và expected members policy.
- Retry có deadline/backoff, idempotency bảo vệ downstream side effects.
- Có unit, integration và transport tests cho error paths.
- Có metrics về reject reason, schema drift, mapper defects và quarantine backlog.

Checklist này **không thay thế** một integration test với adapter, endpoint và error recoverer thực. Nó chỉ làm rõ những cam kết cần chứng minh trước khi đưa Translator vào production.

## 42. Bài thực hành: một Translator có diagnostics và recovery rõ ràng

Xây mini project **PartnerOrderTranslator**:

1. Định nghĩa `PartnerOrderV2` và `CanonicalOrder` như trên.
2. Viết `MappingStage`, `MappingDiagnostic`, `MappingFailure` và catalog reason codes.
3. Viết mapper trả canonical result hoặc lỗi typed, không default amount/currency tùy tiện.
4. Thêm Java DSL Transformer hoặc `@Transformer` (chọn một cấu hình).
5. Viết unit tests với valid input, amount lỗi, field thiếu, timestamp sai, schema không hỗ trợ.
6. Đặt validation parser/JSON schema trước Transformer và test raw malformed bytes.
7. Test `MessagingException` cause chain và `failedMessage`.
8. Tạo một `translator.errors` flow đưa permanent failures vào quarantine có sanitize.
9. Thêm Gateway và HTTP error mapper trả `reasonCode/fieldPath`, không trả stack trace.
10. Gắn broker adapter, test bounded retry, ACK/DLT và DLQ unavailable.
11. Nối Splitter/Aggregator, tạo một child mapping lỗi và xử lý expected members đúng.
12. Đổi source schema từ v2 sang v3, kiểm tra Router chọn mapper đúng và unsupported version bị reject.
13. Thử idempotent replay sau commit; không double business side effect.
14. Tạo dashboard mapping failure theo source/version/reason, không gắn event ID làm metric label.
15. Viết runbook điều tra `MessageTransformationException`, kiểm tra từng error boundary.

**Tiêu chí hoàn thành:** message lỗi được báo **đúng lý do, đúng field, đúng source/version**, không đi vào business flow, không retry vô hạn nếu là lỗi permanent, không mất trách nhiệm khi DLQ down; các message hợp lệ tiếp tục xử lý; correlation và idempotency vẫn đúng sau retry/replay.

## 43. Các hiểu lầm thường gặp

**“Translator chỉ cần ném NumberFormatException là đủ.”** Không. Cần mã lỗi, field, source/version và retryability.

**“Mọi lỗi từ Transformer đều do producer gửi sai.”** Không. Có mapper defects, dependency outages và lỗi downstream.

**“Chỉ cần đọc exception message ngoài cùng.”** Không. Spring có thể wrap thành `MessagingException`; cần cause chain.

**“Lỗi JSON syntax nào cũng vào `@Transformer`.”** Không. Deserialize có thể thất bại trước khi có Spring Message.

**“`failedMessage` luôn tồn tại và có đúng source DTO.”** Không. Có trường hợp null, bytes hoặc payload đã biến đổi.

**“Mọi lỗi đều được gửi vào global errorChannel.”** Không tự động; phụ thuộc sync/async boundary và cấu hình.

**“Filter discard channel là broker DLT.”** Không. Cần publisher/recoverer từ channel tới broker.

**“Một lỗi mapping phải retry ngay nhiều lần.”** Không nếu input permanent malformed; cùng bytes không tự sửa.

**“Nếu mapper không parse được amount thì đặt 0.”** Sai. Đó là silent data corruption.

**“Một unknown currency có thể mặc định USD cho mọi nguồn.”** Không nếu source contract không bảo đảm.

**“Có traceId là đủ để gom kết quả Aggregator.”** Không. Trace và business correlation có ngữ nghĩa khác nhau.

**“MessageHeaders.ID giữ nguyên qua mọi retry và broker.”** Không được giả định; message có thể được xây lại.

**“Khi Translator lỗi thì Gateway tự trả HTTP 400.”** Không. API layer phải map lỗi hoặc trả typed rejection.

**“Gửi nguyên payload và stack trace vào logs/DLQ là an toàn.”** Không khi có PII, secrets, dữ liệu lớn hoặc log injection.

**“Quarantine rồi có thể ACK bất kể storage có lưu thành công hay chưa.”** Không. ACK phải tuân thủ durable recovery contract.

**“Nếu một child Translator lỗi thì Aggregator tự biết kết thúc.”** Không nếu không có failure outcome/release/expiry policy.

**“Có retry advice tức là đã có idempotency.”** Không. Retry và không lặp side effect là hai vấn đề khác nhau.

**“Một mapped message có đúng kiểu là đã đúng semantics.”** Không. Unit, precision, currency, timestamp và business meaning vẫn có thể sai.

## 44. Ghi nhớ

**Lỗi mapping và thông tin chẩn đoán** là một phần của hợp đồng **Message Translator**, không phải chi tiết logging tùy hứng. Một Translator tốt **chuyển message đúng nghĩa hoặc thất bại minh bạch**, nêu rõ **reasonCode, stage, fieldPath, source/version, endpoint, retryability và identity đáng tin** khi có thể.

Trong **Spring Integration**, phân biệt lỗi **trước Transformer** (decode/adapter), lỗi **bên trong Transformer** có thể được wrap thành `MessagingException`/`MessageTransformationException`, và lỗi **sau Translator** ở business handler. Dùng `ErrorMessage`, `failedMessage`, Gateway exception mapping và error channel theo đúng ranh giới đồng bộ–bất đồng bộ; đừng giả định mọi lỗi tự đi vào cùng một kênh.

Phân loại **permanent input**, **transient dependency**, **unknown outcome** và **mapper defect** để quyết định reject/retry/reconcile đúng. Giữ correlation và idempotency khi đi qua Router, Filter, Splitter, Aggregator, Gateway và broker; không ghi raw dữ liệu nhạy cảm vào diagnostics; kiểm thử cả **mã lỗi** lẫn **không tạo side effect khi input sai**. Khi dữ liệu không thể chuyển đổi đúng, **từ chối an toàn tốt hơn tự tạo giá trị sai**.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Message Translator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns, **Normalizer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Gateway**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
