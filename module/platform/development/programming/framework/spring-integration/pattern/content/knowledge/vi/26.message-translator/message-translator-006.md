# Xử lý field không có ánh xạ

## 1. Bài toán: translator gặp một trường không biết chuyển đi đâu

Một hệ thống bán hàng nhận đơn hàng từ đối tác. Đối tác gửi:

~~~json
{
  "eventId": "PARTNER-EVT-901",
  "partnerOrderRef": "EXT-ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "EXP",
  "legacyCampaignHint": "old-q4",
  "newRiskIndicator": "high"
}
~~~

Trong hệ thống nội bộ, nghiệp vụ chỉ cần một cấu trúc chuẩn:

~~~json
{
  "sourceEventId": "PARTNER-EVT-901",
  "orderId": "EXT-ORD-901",
  "amountVnd": 850000,
  "shippingTier": "EXPRESS"
}
~~~

Các trường `eventId`, `partnerOrderRef`, `totalVnd` và `deliveryCode` có quy tắc ánh xạ rõ. Nhưng `legacyCampaignHint` và `newRiskIndicator` **không có trường đích**. Nếu translator bỏ cả hai mà không ghi nhận, nhà cung cấp có thể đã thêm một thuộc tính quan trọng và dữ liệu bị mất âm thầm. Nếu translator ném exception cho mọi trường lạ, một cập nhật mở rộng không quan trọng cũng có thể làm ngừng toàn bộ ingestion.

**Xử lý field không có ánh xạ** là việc thiết kế **chính sách rõ ràng** cho dữ liệu không có quy tắc chuyển đổi từ hệ nguồn sang cấu trúc đích. Chính sách có thể là **từ chối, đưa vào quarantine, bỏ qua có chủ đích, lưu trong vùng mở rộng có kiểm soát hoặc enrich từ nguồn có thẩm quyền**. Lựa chọn phải dựa trên hợp đồng dữ liệu, độ quan trọng nghiệp vụ, quyền truy cập và khả năng replay; không được để thư viện mapper quyết định thay nghiệp vụ một cách vô thức.

~~~mermaid
flowchart LR
    S["Partner order message"] --> T["Message Translator"]
    T --> M["Mapped canonical fields"]
    T --> U["Unmapped-field diagnostics"]
    U --> P{"Policy"}
    P -->|Known safe to ignore| I["Accept + audit warning"]
    P -->|Unknown / critical| Q["Reject or quarantine"]
    P -->|Approved extension| X["Protected extension bag"]
    M --> V["Validate canonical result"]
    I --> V
    X --> V
    V --> B["Business flow if accepted"]
~~~

Bài thuộc chương **Message translator**, trong module `SPRING_INTEGRATION_PATTERN`. Mục tiêu học là triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát các nhánh xử lý.

### Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

1. Phân biệt **field nguồn không có đích**, **field đích không có nguồn**, **field có tên nhưng không chuyển được**, **field null/missing** và **field chưa nhận diện do schema mới**.
2. Quyết định khi nào được **ignore có audit**, khi nào phải **reject/quarantine**, và khi nào cần **extension bag/enrichment**.
3. Triển khai Java translator có `MappingResult`, `MappingIssue`, mức độ lỗi và policy version thay vì map “thành công” bằng cách lặng lẽ loại trường.
4. Xây Spring Integration Java DSL để chuyển payload hợp lệ sang business flow và gửi mapping result không hợp lệ sang quarantine.
5. Kiểm thử số tiền, enum, unknown fields, missing/null, schema evolution, retry và redelivery.
6. Thiết kế quan sát, bảo mật, chống duplicate, replay và xử lý lỗi theo đúng ranh giới.

## 2. Message Translator làm gì, và không làm gì?

**Message Translator** là một Enterprise Integration Pattern dùng để đưa message từ **một định dạng/hợp đồng dữ liệu** sang định dạng/hợp đồng mà consumer hiểu.

Ví dụ:

~~~text
PartnerOrderV1
   partnerOrderRef = EXT-ORD-901
   totalVnd        = "850000"
   deliveryCode    = EXP
      |
      v
Message Translator
      |
      v
NormalizedOrder
   orderId         = EXT-ORD-901
   amountVnd       = 850000
   shippingTier    = EXPRESS
~~~

Trong Spring Integration, một **Transformer endpoint** thường là nơi triển khai Message Translator. Tuy nhiên:

- **Transformer** là cơ chế chuyển payload/message trong framework; **Message Translator** nhấn mạnh ngữ nghĩa và hợp đồng giữa hai hệ thống.
- **Filter** quyết định message nào đi tiếp; **Translator** quyết định dữ liệu được diễn giải/chuyển thành gì.
- **Router** chọn kênh hoặc nhánh; Translator không tự đảm bảo routing đến đích hợp lệ.
- **Content Enricher** bổ sung thông tin từ nguồn khác; không phải một quy tắc bỏ trống hay tự bịa field thiếu.
- **Envelope Wrapper** thêm lớp metadata xung quanh payload; Translator có thể đổi payload mà vẫn phải bảo tồn metadata cần thiết.
- **Normalizer/Canonical Data Model** giúp nhiều nguồn cùng về một cấu trúc nội bộ; translator là điểm đưa dữ liệu nguồn về cấu trúc đó.

### 2.1. Field không ánh xạ không chỉ là tên khác nhau

| Dữ liệu nguồn | Dữ liệu đích | Tình trạng | Hành động |
|---|---|---|---|
| `partnerOrderRef` | `orderId` | Có quy tắc đổi tên. | Chuyển bình thường. |
| `totalVnd` kiểu string | `amountVnd` kiểu số | Có quy tắc parse/validate. | Parse chính xác, reject lỗi. |
| `deliveryCode=EXP` | `shippingTier=EXPRESS` | Có enum mapping. | Mapping có allowlist. |
| `legacyCampaignHint` | Không có field tương ứng. | **Source-only field**, có thể bỏ qua được phê duyệt. | Warning/audit theo policy. |
| `newRiskIndicator` | Không có field tương ứng. | **Unknown source field**, chưa biết có quan trọng không. | Strict reject/quarantine hoặc policy có version. |
| Không có `riskDecision` | Target đòi `riskDecision` | **Target-only required field**. | Enrich từ nguồn có thẩm quyền hoặc reject; không tự gán PASS. |
| `deliveryCode=OVERNIGHT` | Enum không có OVERNIGHT | **Known field, unknown value**. | Mapping error; không tự fallback STANDARD. |
| `totalVnd="abc"` | `amountVnd` | **Conversion error**. | Mapping error và quarantine. |
| `totalVnd=null` | `amountVnd` | **Missing/null required field**. | Validation error; không mặc định 0. |

Điểm then chốt: **Không có mapping** (không tồn tại quy tắc) khác **có mapping nhưng dữ liệu không hợp lệ**. Nếu gộp hai nhóm, error metrics, replay và phân công owner sẽ sai.

### 2.2. Phân biệt phần dữ liệu được phép mất và không được phép mất

Một field như `legacyCampaignHint` có thể được bỏ qua sau khi business owner xác nhận không còn dùng. Nhưng một field mới `exportControlFlag`, `riskIndicator` hoặc `discountAmount` có thể thay đổi quyết định xử lý. Nếu parser âm thầm bỏ, giao dịch có thể bị xử lý sai mà không có cách khôi phục.

Do đó cần một **mapping contract** gồm:

- Những source fields **phải nhận diện**.
- Những source fields **được ánh xạ**.
- Những field **được phép bỏ qua** và lý do.
- Những field **phải từ chối/quarantine nếu xuất hiện** hoặc chưa được review.
- Những target fields **bắt buộc có giá trị**.
- Chuyển kiểu/đơn vị/enum/default rõ ràng.
- Version của hợp đồng và phạm vi áp dụng theo partner/source/tenant.

## 3. Năm trường hợp “không có ánh xạ” dễ bị nhầm

### 3.1. Source-only: nguồn có field, đích không cần

~~~json
{"legacyCampaignHint":"old-q4"}
~~~

Có thể **ignore có chủ đích** nếu đã được phê duyệt và không cần cho downstream. Không nên ghi cả giá trị vào log chỉ để chứng minh đã bỏ qua; thường **tên trường, policy version, số lượng và source** là đủ. Nếu có PII, phải kiểm soát retention và quyền.

### 3.2. Target-only: đích yêu cầu field nhưng nguồn không có

~~~text
Target requires:
  fraudApproved: Boolean

Source provides:
  orderId, amount, deliveryCode
  (no fraudApproved)
~~~

**Không tự gán `fraudApproved=true`**. Có thể:

1. Cho target field là optional nếu nghiệp vụ thật sự cho phép.
2. Áp dụng default **được ghi trong contract**, ví dụ một shipping tier mặc định cho legacy partner.
3. Enrich từ fraud service có thẩm quyền, với timeout/retry và version của quyết định.
4. Từ chối/quarantine nếu không thể thiết lập giá trị bắt buộc an toàn.

Khả năng thiếu source có thể là do **version không tương thích**, không phải do business cố ý để trống.

### 3.3. Known field, unknown value

~~~text
source.deliveryCode = OVERNIGHT
target.shippingTier = STANDARD | EXPRESS
~~~

Về tên trường, mapping tồn tại. Nhưng giá trị `OVERNIGHT` không được định nghĩa trong bảng enum. Nếu tự trả `STANDARD`, hàng cần giao nhanh có thể bị giao chậm và lỗi bị che. Policy thường nên **reject/quarantine UNKNOWN_ENUM_VALUE** để cập nhật contract. Chỉ fallback khi business owner phê duyệt.

### 3.4. Missing, null, empty, blank là các trường hợp khác

| Trạng thái | Ví dụ | Ý nghĩa có thể có |
|---|---|---|
| Missing | JSON không có key `totalVnd`. | Producer không gửi / version cũ. |
| Explicit null | `"totalVnd": null`. | Producer chủ động nói “không có giá trị”, hoặc bug. |
| Empty string | `"totalVnd": ""`. | Dữ liệu trống, không phải số 0. |
| Blank | `"totalVnd": "  "`. | Trống sau normalization. |
| Zero | `"totalVnd": "0"`. | Một giá trị số thật, cần business validation. |
| Malformed | `"totalVnd": "8.5.00"`. | Lỗi conversion. |

Một Java record có field null **có thể đã làm mất khả năng phân biệt missing với explicit null** nếu JSON deserializer map cả hai thành null. Nếu hợp đồng cần phân biệt, phải kiểm tra raw-object structure/JSON node hoặc dùng kiểu biểu diễn presence riêng ở ingress.

### 3.5. Unknown field do schema mới hoặc raw parser

Nếu producer deploy V2 và thêm `newRiskIndicator` trong khi consumer chỉ hỗ trợ V1, nhiều mapper sẽ mặc định ignore unknown properties hoặc có cấu hình reject. Không dựa vào default của mapper để quyết định policy: phải **chốt rõ** consumer muốn forward compatibility hay strict schema.

Với schema nhạy cảm như thanh toán/bảo mật, strict/quarantine giúp phát hiện field mới quan trọng. Với event analytics có hợp đồng extensible, việc ignore extra fields có thể chấp nhận được **nếu có giới hạn và telemetry**.

## 4. Chính sách xử lý khi không tìm thấy mapping

### 4.1. Ma trận lựa chọn

| Chính sách | Khi phù hợp | Rủi ro / điều kiện |
|---|---|---|
| **REJECT** | Mapping thiếu ở field quan trọng; cần trả lỗi ngay cho producer. | Cần error response có cấu trúc, không để mất bản ghi. |
| **QUARANTINE** | Message đã vào broker, cần giữ để phân tích/schema upgrade/replay. | Store/ack, phân quyền, retention và replay phải rõ. |
| **IGNORE_WITH_AUDIT** | Field đã được phê duyệt là không ảnh hưởng. | Ghi warning/metric và policy version; không mặc định ignore mọi trường lạ. |
| **PRESERVE_EXTENSION** | Target có extension model được thiết kế, consumer thực sự cần chuyển tiếp. | Allowlist, type/size bound, security, version, không tự cho phép arbitrary keys. |
| **ENRICH** | Target field cần dữ liệu từ nguồn có thẩm quyền. | Dependency timeout, stale data, authorization, determinism và retry. |
| **DEFAULT_EXPLICIT** | Business contract quy định default rõ, ví dụ missing shipping code -> STANDARD. | Không default unknown enum/amount/security flags. |
| **VERSIONED_MIGRATION** | V1/V2 đổi tên hoặc cấu trúc field có thể map đúng nghĩa. | Upcaster phải test tính tương đương; không tự suy đoán missing value. |

### 4.2. Default là một quyết định nghiệp vụ

**Được phép** (khi có hợp đồng):

~~~text
Partner V1:
  deliveryCode absent means STANDARD

Mapping:
  absent -> ShippingTier.STANDARD
~~~

**Không được tự ý**:

~~~text
Partner:
  totalVnd missing

Mapping:
  missing -> BigDecimal.ZERO
  then send to payment
~~~

Thậm chí default `STANDARD` cũng chỉ hợp lệ khi **field vắng mặt** đúng như contract. Nếu producer gửi `deliveryCode="SAME_DAY"` chưa được hỗ trợ, đó là **unknown value** cần xét riêng, không được coi là missing.

### 4.3. Policy theo partner và version

~~~text
Partner A, contract v1:
  allowedIgnored = [legacyCampaignHint]
  unknownSourceFields = QUARANTINE
  deliveryCode missing = STANDARD

Partner B, contract v2:
  allowedIgnored = [marketingTrace]
  unknownSourceFields = IGNORE_WITH_AUDIT
  deliveryCode missing = ERROR
~~~

Không nên áp cùng policy mềm nhất cho mọi tenant/partner. Một thay đổi policy có thể làm input cũ được accept hoặc bị reject, vì vậy cần **policyVersion**, audit triển khai và migration strategy.

### 4.4. Không loại mất dữ liệu trước khi xác định unknown fields

~~~text
Raw JSON
  -> Generic deserializer silently ignores unknown fields
  -> Typed PartnerOrderInput (newRiskIndicator already dropped)
  -> Translator cannot report unmapped newRiskIndicator
~~~

Muốn biết field nguồn chưa được map, bước **ingress parsing phải giữ hoặc báo được danh sách fields**. Có thể dùng:

- Schema validation với **unknown-properties reporting**.
- Jackson `JsonNode`/tree parsing trước khi bind typed DTO.
- `@JsonAnySetter` hoặc extension map có giới hạn, nếu phù hợp.
- Contract registry hoặc generated schema với strict decode.

**Không** thu toàn bộ raw JSON vô hạn vào map “cho chắc”: phải có giới hạn field count, length, nesting, payload size và chặn dữ liệu nguy hiểm.

## 5. Thiết kế Java: nguồn, đích và ngữ cảnh đáng tin

Các ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x**. Các record/class trong bài được hiểu là đặt trong cùng package và tách thành file Java theo đúng quy tắc nếu đưa vào dự án. Chúng là ví dụ học tập, chưa chạy build và không phải schema production của đơn hàng.

### 5.1. DTO nguồn với các field đã biết và extension fields

~~~java
import java.util.Map;

record PartnerOrderInput(
        String eventId,
        String partnerOrderRef,
        String totalVnd,
        String deliveryCode,
        Map<String, String> extraFields) {

    PartnerOrderInput {
        extraFields = extraFields == null
                ? Map.of()
                : Map.copyOf(extraFields);
    }
}
~~~

`extraFields` dùng để **minh họa field đã decode nhưng chưa có mapping**. Nếu JSON parser đã bỏ qua field lạ trước khi tạo record, translator không thể tự phục hồi tên field đã mất. Map giả định values không null vì `Map.copyOf` không nhận null key/value; nếu wire format phân biệt explicit null, cần một ingress structure mạnh hơn và validation ở parser.

### 5.2. Trusted ingress không được lấy trực tiếp từ JSON tự khai

~~~java
record TrustedPartnerIngress(
        String authenticatedPartner,
        String authenticatedTenant,
        PartnerOrderInput payload) {

    TrustedPartnerIngress {
        if (authenticatedPartner == null
                || authenticatedPartner.isBlank()
                || authenticatedTenant == null
                || authenticatedTenant.isBlank()
                || payload == null) {
            throw new IllegalArgumentException(
                    "INVALID_TRUSTED_INGRESS");
        }
    }
}
~~~

Trong demo, test tự tạo `TrustedPartnerIngress` để tập trung vào mapping. Ở production, partner và tenant phải được **xác thực/ủy quyền ở adapter boundary**, không cho remote caller tự đặt một header tên `authenticatedPartner` rồi mặc nhiên tin.

### 5.3. Canonical DTO đích

~~~java
import java.math.BigDecimal;

enum ShippingTier {
    STANDARD, EXPRESS
}

record NormalizedOrder(
        String sourceEventId,
        String orderId,
        BigDecimal amountVnd,
        ShippingTier shippingTier,
        String sourcePartner,
        String tenantId) {}
~~~

Không có `legacyCampaignHint` hay `newRiskIndicator` trong `NormalizedOrder`: điều đó là **thiết kế canonical contract**. Nếu consumer cần field mới, business/data contract phải thay đổi có kiểm soát; đừng lén nhét vào metadata khác chỉ để tránh mapping error.

### 5.4. Kết quả mapping có severity, reason và version

~~~java
import java.util.List;
import java.util.Objects;

enum MappingSeverity {
    WARNING, ERROR
}

record MappingIssue(
        String code,
        String field,
        MappingSeverity severity) {
    MappingIssue {
        if (code == null || code.isBlank()
                || severity == null) {
            throw new IllegalArgumentException(
                    "INVALID_MAPPING_ISSUE");
        }
    }
}

record MappingResult(
        TrustedPartnerIngress original,
        NormalizedOrder normalized,
        List<MappingIssue> issues,
        String mappingVersion) {

    MappingResult {
        Objects.requireNonNull(original, "original");
        issues = List.copyOf(issues);
        if (mappingVersion == null || mappingVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_MAPPING_VERSION");
        }
    }

    boolean accepted() {
        return normalized != null
                && issues.stream().noneMatch(
                        issue -> issue.severity()
                                == MappingSeverity.ERROR);
    }
}
~~~

**Tại sao có `MappingResult` thay vì chỉ trả `NormalizedOrder`?** Vì:

- Consumer được biết rõ mapping success/warning/failure.
- Field bị bỏ có chủ đích vẫn có thể sinh **warning** mà không làm hỏng output.
- Field lạ chưa được phê duyệt có thể sinh **error** và quarantine.
- Mapping version giúp giải thích vì sao cùng payload được xử lý khác nhau trước/sau deploy.
- Error handler có structured issue, không phải parse text exception.

Không phải mọi error đều đến từ “unknown field”; `MISSING_REQUIRED_FIELD`, `INVALID_DECIMAL` hay `UNSUPPORTED_ENUM_VALUE` vẫn cần reason code riêng.

## 6. Translator với chính sách unmapped field tường minh

### 6.1. Chọn strict hay forward-compatible theo contract

~~~java
enum UnknownFieldMode {
    STRICT_QUARANTINE,
    WARN_AND_IGNORE
}
~~~

`STRICT_QUARANTINE` nghĩa là translator **đánh dấu không accepted** để Spring Filter chuyển sang quarantine; bản thân enum/translator không ghi broker queue. `WARN_AND_IGNORE` chỉ nên dùng cho partner/schema đã được business owner xác nhận chấp nhận các extension keys mới, và cần quan sát rate thay đổi.

### 6.2. Quy tắc mapping cụ thể

| Source | Target | Quy tắc |
|---|---|---|
| `eventId` | `sourceEventId` | Bắt buộc, ổn định qua redelivery. |
| `partnerOrderRef` | `orderId` | Bắt buộc, không trim/sửa ID mù quáng nếu business phân biệt whitespace. |
| `totalVnd` | `amountVnd` | Chuỗi chữ số nguyên dương, giới hạn, parse `BigDecimal` chính xác. |
| `deliveryCode=STD` | `shippingTier=STANDARD` | Enum mapping đã phê duyệt. |
| `deliveryCode=EXP` | `shippingTier=EXPRESS` | Enum mapping đã phê duyệt. |
| `deliveryCode` vắng mặt | `shippingTier=STANDARD` | Default **chỉ** vì ví dụ giả định partner contract cho phép. |
| `deliveryCode` có giá trị khác | Không tạo output hợp lệ | `UNSUPPORTED_DELIVERY_CODE`. |
| `extraFields.legacyCampaignHint` | Không có target | Ignore có warning vì allowlist. |
| Các `extraFields` còn lại | Không có target | Reject/quarantine strict hoặc warning nếu policy lenient. |
| Authenticated partner/tenant | `sourcePartner/tenantId` | Chỉ từ trusted context, không suy từ payload. |

### 6.3. Translator thuần Java, không gọi service ngoài

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class PartnerOrderTranslator {
    static final String MAPPING_VERSION = "partner-order-v1";
    private static final BigDecimal MAX_VND =
            new BigDecimal("1000000000000");
    private static final Set<String> ALLOWED_IGNORED_FIELDS =
            Set.of("legacyCampaignHint");

    private final UnknownFieldMode unknownFieldMode;

    PartnerOrderTranslator(UnknownFieldMode unknownFieldMode) {
        this.unknownFieldMode = unknownFieldMode;
    }

    MappingResult translate(TrustedPartnerIngress ingress) {
        PartnerOrderInput input = ingress.payload();
        List<MappingIssue> issues = new ArrayList<>();

        String eventId = input.eventId();
        if (missing(eventId)) {
            issues.add(error(
                    "MISSING_EVENT_ID", "eventId"));
        }

        String orderId = input.partnerOrderRef();
        if (missing(orderId)) {
            issues.add(error(
                    "MISSING_ORDER_ID", "partnerOrderRef"));
        }

        BigDecimal amount = parseAmount(
                input.totalVnd(), issues);

        ShippingTier tier = mapShipping(
                input.deliveryCode(), issues);

        for (Map.Entry<String, String> extra
                : input.extraFields().entrySet()) {
            if (ALLOWED_IGNORED_FIELDS.contains(extra.getKey())) {
                issues.add(warning(
                        "IGNORED_LEGACY_FIELD", extra.getKey()));
            } else if (unknownFieldMode
                    == UnknownFieldMode.STRICT_QUARANTINE) {
                issues.add(error(
                        "UNMAPPED_SOURCE_FIELD", extra.getKey()));
            } else {
                issues.add(warning(
                        "UNMAPPED_SOURCE_FIELD_IGNORED",
                        extra.getKey()));
            }
        }

        boolean hasErrors = issues.stream().anyMatch(
                issue -> issue.severity()
                        == MappingSeverity.ERROR);

        NormalizedOrder normalized = hasErrors
                ? null
                : new NormalizedOrder(
                        eventId,
                        orderId,
                        amount,
                        tier,
                        ingress.authenticatedPartner(),
                        ingress.authenticatedTenant());

        return new MappingResult(
                ingress, normalized, issues, MAPPING_VERSION);
    }

    private static BigDecimal parseAmount(
            String raw, List<MappingIssue> issues) {
        if (missing(raw)) {
            issues.add(error(
                    "MISSING_AMOUNT", "totalVnd"));
            return null;
        }
        // Minh họa contract: số nguyên VND, không dấu phẩy/dấu chấm.
        // Chặn chuỗi quá dài trước khi tạo BigDecimal.
        if (raw.length() > 20 || !raw.matches("[0-9]+")) {
            issues.add(error(
                    "INVALID_AMOUNT_FORMAT", "totalVnd"));
            return null;
        }
        BigDecimal value = new BigDecimal(raw);
        if (value.signum() <= 0 || value.compareTo(MAX_VND) > 0) {
            issues.add(error(
                    "AMOUNT_OUT_OF_RANGE", "totalVnd"));
            return null;
        }
        return value;
    }

    private static ShippingTier mapShipping(
            String code, List<MappingIssue> issues) {
        if (missing(code)) {
            // Chỉ hợp lệ do contract của partner V1 giả định.
            issues.add(warning(
                    "SHIPPING_DEFAULT_APPLIED", "deliveryCode"));
            return ShippingTier.STANDARD;
        }
        return switch (code) {
            case "STD" -> ShippingTier.STANDARD;
            case "EXP" -> ShippingTier.EXPRESS;
            default -> {
                issues.add(error(
                        "UNSUPPORTED_DELIVERY_CODE", "deliveryCode"));
                yield null;
            }
        };
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }

    private static MappingIssue error(String code, String field) {
        return new MappingIssue(
                code, field, MappingSeverity.ERROR);
    }

    private static MappingIssue warning(String code, String field) {
        return new MappingIssue(
                code, field, MappingSeverity.WARNING);
    }
}
~~~

### 6.4. Ý nghĩa của những quyết định nhỏ trong code

1. **Dùng `BigDecimal`**, không chuyển tiền qua `double` có sai số nhị phân.
2. **Giới hạn độ dài trước parse**, không cho payload số quá lớn làm tốn CPU/memory.
3. **Default missing shipping chỉ theo contract**, không fallback cho giá trị chưa hỗ trợ.
4. **Issue chứa code và field name**, không chứa thẳng email, risk score hay token.
5. **Dùng partner/tenant từ trusted ingress**, không cho field nguồn ghi đè.
6. **Không trả `NormalizedOrder` khi có error**, tránh partial mapping lọt business flow.
7. **Có warning khi bỏ field**, giúp thấy schema drift mà không đánh đồng với failure.
8. **MAPPING_VERSION cố định cho rules**, cần cập nhật khi thay allowlist/default/semantics.

Trong demo `extraFields` được đưa vào `MappingResult.original` và có thể chứa dữ liệu nhạy cảm. Production cần store/reference có mã hóa và retention, không log hoặc publish toàn `MappingResult` ra nơi mọi subscriber đều đọc được.

### 6.5. Không biến `WARN_AND_IGNORE` thành quyền bỏ mọi thứ

Một policy lenient có thể hợp lý cho event tracking ít rủi ro, nhưng nên có:

- Allowed partner/schema versions.
- Maximum extra fields/bytes/nesting tại ingress.
- Cảnh báo `UNMAPPED_SOURCE_FIELD_IGNORED` theo **field name đã sanitize**.
- Rate/threshold để phát hiện producer rollout mới.
- Danh sách **critical fields** không bao giờ được ignore.
- Thời hạn review để chuyển unknown mới thành mapped/allowlisted/blocked.

Không cho người gửi tự đặt `unknownFieldMode=WARN_AND_IGNORE` trong payload. Chế độ phải xuất phát từ policy đáng tin cậy của consumer.

## 7. Nguồn không có đích và đích không có nguồn: giải pháp khác nhau

### 7.1. Source-only không nhất thiết là lỗi

Một partner có field `marketingTrace` chỉ phục vụ dashboard của họ. Nếu canonical `NormalizedOrder` không cần và contract đã xác nhận, **ignore với audit** là hợp lý. Điều kiện quan trọng: không làm thay đổi nghĩa của các field đã map và không có downstream policy phụ thuộc vào nó.

### 7.2. Target-only required phải được giải quyết trước business handler

Một đích yêu cầu `riskApproval`, nguồn không cung cấp:

~~~mermaid
flowchart LR
    S["Partner order"] --> T["Translator"]
    T --> M{"Target riskApproval required?"}
    M -->|No| B["Create canonical order"]
    M -->|Yes| E["Trusted risk enrichment / validation"]
    E -->|Approved result| B
    E -->|Unavailable or unknown| Q["Retry technical / quarantine by reason"]
~~~

Không mặc định `riskApproval=APPROVED`. Nếu enrichment gọi service ngoài, nó có thể timeout hoặc trả dữ liệu thay đổi giữa retries; cần contract về **snapshot/version/correlation**, retry và authorization. Một translator thuần deterministic thường dễ kiểm thử hơn; để external lookup ở Content Enricher endpoint riêng sẽ làm rõ ranh giới.

### 7.3. Null không phải là một “default” miễn phí

Giả sử `target.discountPercent` không có giá trị:

- Nếu nghiệp vụ cho phép “không áp dụng giảm giá”, có thể dùng optional/zero **theo contract**.
- Nếu thiếu dữ liệu giảm giá làm thay đổi số tiền phải thu, không được tự gán 0 rồi chạy payment khi chưa biết nguồn tính tiền đã hoàn tất chưa.
- Nếu target field có nghĩa “unknown”, dùng representation **UNKNOWN/Optional** có chủ đích, không đồng nhất với “false”.

**Nguyên tắc:** mặc định an toàn phải dựa trên **ngữ nghĩa đã xác nhận**, không dựa trên việc Java constructor/serializer yêu cầu một giá trị.

## 8. Spring Integration: translator + filter + quarantine

### 8.1. Thiết kế flow

Một cách tổ chức dễ kiểm thử:

~~~mermaid
flowchart LR
    INPUT["partner.order.input"] --> TRANSFORM["PartnerOrderTranslator"]
    TRANSFORM --> OUT["MappingResult"]
    OUT --> CHECK{"accepted()"}
    CHECK -->|True| NORM["NormalizedOrder"]
    NORM --> BUS["orders.normalized -> business handler"]
    CHECK -->|False| Q["partner.mapping.quarantine"]
    Q --> STORE["Quarantine writer + audit"]
~~~

Chúng ta **không ném exception** cho một field lạ như một lỗi Java bất ngờ nếu đây là validation outcome dự kiến. Translator trả `MappingResult`; Filter tách accepted và rejected. Nếu translator tự gặp bug hoặc quarantine store lỗi, đó là **technical exception** phải có recovery/error policy khác.

### 8.2. Hai probe chỉ dành cho test

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class AcceptedOrderProbe {
    private final List<NormalizedOrder> values =
            new CopyOnWriteArrayList<>();

    void accept(NormalizedOrder order) {
        values.add(order);
    }

    List<NormalizedOrder> snapshot() {
        return List.copyOf(values);
    }
}

final class MappingQuarantineProbe {
    private final List<MappingResult> rejected =
            new CopyOnWriteArrayList<>();

    void record(MappingResult result) {
        if (result.accepted()) {
            throw new IllegalArgumentException(
                    "CANNOT_QUARANTINE_ACCEPTED_RESULT");
        }
        rejected.add(result);
    }

    List<MappingResult> snapshot() {
        return List.copyOf(rejected);
    }
}
~~~

**Cảnh báo:** Probe chỉ giữ dữ liệu trong memory. Nếu ứng dụng cần **không mất message** khi crash, phải thay bằng durable quarantine DB/queue và thiết kế ack, idempotency, retention, authorization. Không ghi toàn `MappingResult.original` vào structured log vì có thể chứa thông tin riêng tư.

### 8.3. Flow Java DSL minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class MessageTranslatorConfiguration {

    @Bean(name = "partner.order.input")
    MessageChannel partnerInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.normalized")
    MessageChannel normalizedOutput() {
        return new DirectChannel();
    }

    @Bean(name = "partner.mapping.quarantine")
    MessageChannel mappingQuarantine() {
        return new DirectChannel();
    }

    @Bean
    PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator(
                UnknownFieldMode.STRICT_QUARANTINE);
    }

    @Bean
    AcceptedOrderProbe acceptedOrderProbe() {
        return new AcceptedOrderProbe();
    }

    @Bean
    MappingQuarantineProbe mappingQuarantineProbe() {
        return new MappingQuarantineProbe();
    }

    @Bean
    IntegrationFlow translatePartnerOrders(
            PartnerOrderTranslator translator) {
        return IntegrationFlow.from("partner.order.input")
                .transform(
                        TrustedPartnerIngress.class,
                        translator::translate)
                .filter(
                        MappingResult.class,
                        MappingResult::accepted,
                        spec -> spec.discardChannel(
                                "partner.mapping.quarantine"))
                .transform(
                        MappingResult.class,
                        MappingResult::normalized)
                .channel("orders.normalized")
                .get();
    }

    @Bean
    IntegrationFlow businessOrders(AcceptedOrderProbe probe) {
        return IntegrationFlow.from("orders.normalized")
                .handle(
                        NormalizedOrder.class,
                        (order, headers) -> {
                            probe.accept(order);
                            return null; // Terminal demo handler.
                        })
                .get();
    }

    @Bean
    IntegrationFlow quarantineMappingFailures(
            MappingQuarantineProbe probe) {
        return IntegrationFlow.from(
                        "partner.mapping.quarantine")
                .handle(
                        MappingResult.class,
                        (result, headers) -> {
                            probe.record(result);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

### 8.4. Diễn giải các bước

1. Inbound adapter đã tạo một `TrustedPartnerIngress` từ payload và security context.
2. `transform(...)` chạy **translator Java thuần**, trả `MappingResult` có issues.
3. `filter(...)` chỉ chấp nhận khi `accepted()` là true.
4. Nếu accepted, `transform(MappingResult::normalized)` chuyển payload sang `NormalizedOrder`.
5. Message đi qua `orders.normalized` rồi tới business handler.
6. Nếu rejected, Filter gửi **`MappingResult` chưa bị mất issues** sang `partner.mapping.quarantine`.
7. Quarantine handler trong demo ghi probe; ở production thay bằng durable writer.

Đây là ví dụ Java DSL theo Spring Integration 6.x ở mức thiết kế. Các overload và header semantics cần kiểm tra với dependency thực tế ở bước QA/build riêng; STEP 4 này không chạy Gradle/Python hay Content QA chuyên môn.

### 8.5. Tránh cấu hình Filter làm mất quarantine

Đoạn thiếu an toàn:

~~~java
// Chỉ minh họa anti-pattern:
.filter(MappingResult.class, MappingResult::accepted)
~~~

Nếu không có `discardChannel`, rejected message có thể bị loại khỏi đường business mà **không được lưu lại**. Bật `throwExceptionOnRejection(true)` thì semantics chuyển sang lỗi theo cấu hình thay vì mặc nhiên gửi quarantine bình thường. Phải chọn một đường **rõ, quan sát được và được kiểm thử**.

### 8.6. Khi nào dùng Router thay Filter?

Nếu có ba nhóm quyết định:

~~~text
MappingResult.status:
  ACCEPTED_WITH_WARNING
  INVALID_BUSINESS_MAPPING
  UNSUPPORTED_SCHEMA
~~~

Router có thể điều hướng tới ba channel. Với bài tập hai nhánh accepted/rejected, **Filter + discard** thể hiện rõ nhất; còn production có thể dùng một typed outcome và Router để tách technical/schema/business error mà không trộn các lý do.

### 8.7. Đừng để MessageTranslator thay quyền kiểm tra nguồn

`TrustedPartnerIngress.authenticatedTenant` được lấy từ adapter có quyền. Nếu field đích `tenantId` của `NormalizedOrder` được lấy trực tiếp từ một JSON object do caller khai, translator sẽ trở thành **data laundering**: gắn nhãn trusted cho dữ liệu không đáng tin. Security phải được xác thực trước mapping và kiểm tra lại khi replay.

## 9. Unit test: known fields và unknown fields

### 9.1. Fixture đơn giản, không cần Spring context

~~~java
import java.util.Map;

final class PartnerOrderFixtures {
    static TrustedPartnerIngress ingress(
            Map<String, String> extras) {
        return new TrustedPartnerIngress(
                "PARTNER-A",
                "TENANT-A",
                new PartnerOrderInput(
                        "EVT-901",
                        "EXT-ORD-901",
                        "850000",
                        "EXP",
                        extras));
    }
}
~~~

### 9.2. Tất cả field đã biết ánh xạ đúng

~~~java
import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerOrderTranslatorHappyPathTest {
    @Test
    void knownFieldsTranslateToCanonicalValues() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);

        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(Map.of()));

        assertTrue(result.accepted());
        assertEquals("EXT-ORD-901",
                result.normalized().orderId());
        assertEquals(new BigDecimal("850000"),
                result.normalized().amountVnd());
        assertEquals(ShippingTier.EXPRESS,
                result.normalized().shippingTier());
        assertEquals("TENANT-A",
                result.normalized().tenantId());
        assertEquals("partner-order-v1",
                result.mappingVersion());
    }
}
~~~

### 9.3. Field được cho phép ignore sinh warning

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AllowlistedUnmappedFieldTest {
    @Test
    void legacyFieldIsIgnoredWithDiagnostic() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("legacyCampaignHint", "old-q4")));

        assertTrue(result.accepted());
        assertEquals("IGNORED_LEGACY_FIELD",
                result.issues().get(0).code());
        assertEquals(MappingSeverity.WARNING,
                result.issues().get(0).severity());
    }
}
~~~

### 9.4. Unknown field trong strict mode phải chặn business

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StrictUnmappedFieldTest {
    @Test
    void unknownFieldCannotSilentlyReachBusiness() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("newRiskIndicator", "high")));

        assertFalse(result.accepted());
        assertNull(result.normalized());
        assertEquals("UNMAPPED_SOURCE_FIELD",
                result.issues().get(0).code());
        assertEquals(MappingSeverity.ERROR,
                result.issues().get(0).severity());
    }
}
~~~

Ở đây “chặn business” là `MappingResult.accepted()==false`. Việc gửi thật đến quarantine được kiểm chứng bằng **integration test của Spring Flow**, không chỉ unit test translator.

### 9.5. Lenient mode chỉ cho qua khi policy được chọn

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LenientUnmappedFieldTest {
    @Test
    void ignoredUnknownFieldStillProducesWarning() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.WARN_AND_IGNORE);

        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("newRiskIndicator", "high")));

        assertTrue(result.accepted());
        assertEquals("UNMAPPED_SOURCE_FIELD_IGNORED",
                result.issues().get(0).code());
    }
}
~~~

**Không nên lấy test lenient này làm lý do cấu hình lenient ở payment/risk flow.** Nó chỉ chứng minh semantics của một mode mà business contract phải phê duyệt riêng.

### 9.6. Mapping enum mới khác missing

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShippingMappingTest {
    private final PartnerOrderTranslator translator =
            new PartnerOrderTranslator(
                    UnknownFieldMode.STRICT_QUARANTINE);

    @Test
    void unsupportedNewEnumIsErrorNotDefault() {
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-1", "ORD-1", "100000",
                        "OVERNIGHT", Map.of()));

        MappingResult result = translator.translate(input);
        assertFalse(result.accepted());
        assertEquals("UNSUPPORTED_DELIVERY_CODE",
                result.issues().get(0).code());
    }

    @Test
    void absentShippingGetsContractualDefaultAndWarning() {
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-2", "ORD-2", "100000",
                        null, Map.of()));

        MappingResult result = translator.translate(input);
        assertTrue(result.accepted());
        assertEquals(ShippingTier.STANDARD,
                result.normalized().shippingTier());
        assertEquals("SHIPPING_DEFAULT_APPLIED",
                result.issues().get(0).code());
    }
}
~~~

### 9.7. Tiền không được parse kiểu đoán mò

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AmountMappingTest {

    @Test
    void invalidAmountCannotProduceCanonicalOrder() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        TrustedPartnerIngress input = new TrustedPartnerIngress(
                "PARTNER-A", "TENANT-A",
                new PartnerOrderInput(
                        "EVT-3", "ORD-3", "8,500.00",
                        "STD", Map.of()));

        MappingResult result = translator.translate(input);
        assertFalse(result.accepted());
        assertEquals("INVALID_AMOUNT_FORMAT",
                result.issues().get(0).code());
    }
}
~~~

Trong demo, `totalVnd` theo contract là **chuỗi số nguyên không có phân cách hàng nghìn**, nên `"8,500.00"` không tự hiểu là `8500` hay `8.5`. Nếu đối tác hỗ trợ locale/currency khác, viết converter/version riêng có kiểm thử và đơn vị rõ.

## 10. Integration test: rejected message thực sự đi quarantine

### 10.1. Accepted order chỉ đến business handler

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(MessageTranslatorConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorAcceptedIntegrationTest {

    @Autowired
    @Qualifier("partner.order.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe business;

    @Autowired
    MappingQuarantineProbe quarantine;

    @Test
    void knownFieldsBecomeOneNormalizedOrder() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        PartnerOrderFixtures.ingress(Map.of()))
                        .build()));

        assertEquals(1, business.snapshot().size());
        assertEquals(0, quarantine.snapshot().size());
        assertEquals("EXT-ORD-901",
                business.snapshot().get(0).orderId());
    }
}
~~~

### 10.2. Unknown field trong strict mode chỉ đến quarantine

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(MessageTranslatorConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorQuarantineIntegrationTest {

    @Autowired
    @Qualifier("partner.order.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe business;

    @Autowired
    MappingQuarantineProbe quarantine;

    @Test
    void strictUnknownFieldDoesNotLeakIntoBusiness() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        PartnerOrderFixtures.ingress(
                                Map.of("newRiskIndicator", "high")))
                        .build()));

        assertEquals(0, business.snapshot().size());
        assertEquals(1, quarantine.snapshot().size());
        MappingResult rejected =
                quarantine.snapshot().get(0);
        assertFalse(rejected.accepted());
        assertEquals("UNMAPPED_SOURCE_FIELD",
                rejected.issues().get(0).code());
        assertEquals("partner-order-v1",
                rejected.mappingVersion());
    }
}
~~~

**Ý nghĩa:** Với `DirectChannel` và probe đồng bộ của demo, integration test đi qua `Transformer → Filter → discard channel → quarantine handler`. Nó không chỉ gọi Java method thuần.

**Giới hạn:** Tên channel “quarantine” và một list trong memory không chứng minh durability. Không có broker, DB, retry, ack, security principal hay JSON decoder thật trong bài test này.

### 10.3. Known ignored field vẫn vào business và giữ warning

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MappingWarningOnlyTest {
    @Test
    void allowlistedLegacyFieldDoesNotBlockMapping() {
        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);
        MappingResult result = translator.translate(
                PartnerOrderFixtures.ingress(
                        Map.of("legacyCampaignHint", "retired")));

        assertTrue(result.accepted());
        assertEquals(1, result.issues().size());
        assertEquals(MappingSeverity.WARNING,
                result.issues().get(0).severity());
        assertEquals("EXT-ORD-901",
                result.normalized().orderId());
    }
}
~~~

Nhánh accepted cần xuất **warning metrics/logs đã sanitize**, chứ không đẩy cả source object với các extra values không dùng sang business handler. Ở flow minh họa, business handler nhận `NormalizedOrder` sau bước thứ hai, không nhận `MappingResult.original`.

### 10.4. Kiểm tra Header và Event ID tại ranh giới

Một inbound adapter có thể tạo Spring `Message<TrustedPartnerIngress>` có `MessageHeaders.ID` mới sau mỗi lần redelivery. Logical `sourceEventId` phải đến từ source event/operation identity, không phải `MessageHeaders.ID`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class SourceEventIdentityTest {
    @Test
    void twoSpringMessagesCanCarrySameLogicalEvent() {
        TrustedPartnerIngress same =
                PartnerOrderFixtures.ingress(java.util.Map.of());
        Message<TrustedPartnerIngress> first =
                MessageBuilder.withPayload(same).build();
        Message<TrustedPartnerIngress> retry =
                MessageBuilder.withPayload(same).build();

        assertNotEquals(
                first.getHeaders().getId(),
                retry.getHeaders().getId());

        PartnerOrderTranslator translator =
                new PartnerOrderTranslator(
                        UnknownFieldMode.STRICT_QUARANTINE);

        assertEquals(
                translator.translate(first.getPayload())
                        .normalized().sourceEventId(),
                translator.translate(retry.getPayload())
                        .normalized().sourceEventId());
    }
}
~~~

Điều này chỉ chứng minh Message ID trong JVM có thể khác khi **tạo hai message objects**, không suy ra mọi transport giữ hay đổi ID theo cùng cách. Cần test adapter cụ thể để xác nhận wire metadata mapping.

## 11. Field “không thấy” có thể đã mất trước Translator

### 11.1. Default của JSON binding có thể che schema drift

Giả sử client thêm:

~~~json
{
  "partnerOrderRef": "EXT-ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "EXP",
  "newRiskIndicator": "high"
}
~~~

Nếu Jackson/JSON mapper được cấu hình **ignore unknown properties** mà không ghi nhận, `newRiskIndicator` sẽ biến mất trong quá trình bind DTO. Translator chỉ biết các fields đã nhận, nên sẽ báo **accepted** dù raw source chứa thông tin không được xử lý.

Ngược lại, strict deserializer có thể throw **UnrecognizedPropertyException** trước khi translator chạy; trường hợp này phải đi qua **adapter/parser error handling**, không phải `discardChannel` của typed mapping result.

### 11.2. Parse dưới dạng tree hoặc schema-aware decoder

Pseudo-flow được khuyến nghị:

~~~text
Raw JSON bytes (bounded by size/depth)
  -> Authenticate producer / tenant
  -> Detect schema version, event type
  -> Enumerate declared source property names
  -> Compare against known schema + approved extensions
  -> Decode typed PartnerOrderInput with extraFields
  -> PartnerOrderTranslator
  -> MappingResult
~~~

Với Jackson, `JsonNode`/tree model có thể giúp xác định names trước khi bind. Tuy nhiên **không** có nghĩa phải lưu mọi unknown value trong memory; nhiều hệ thống chỉ cần một **danh sách tên field đã sanitize** và protected raw reference cho investigation.

### 11.3. Lỗi parse khác lỗi mapping

| Tình huống | Lỗi xảy ra tại | Kênh xử lý |
|---|---|---|
| JSON bị cắt | Parser/deserializer | Adapter technical/error/DLQ hoặc raw quarantine. |
| JSON là object nhưng có key mới | Schema-aware parser/translator | Unknown-property policy, reject/warn/quarantine. |
| `totalVnd` là mảng JSON thay string | Deserializer/contract validation | Raw schema violation, trước translator typed. |
| `totalVnd="abc"` là string | Translator | `INVALID_AMOUNT_FORMAT`. |
| Enum `OVERNIGHT` string | Translator | `UNSUPPORTED_DELIVERY_CODE`. |
| Quarantine DB không kết nối được | Quarantine writer | Technical retry/backpressure, không chuyển thành source invalid. |

Không bắt mọi `RuntimeException` ở inbound rồi gắn `UNMAPPED_FIELD`. Cần error classification đúng để chọn retry và owner (producer, mapping team, platform).

### 11.4. Duplicate JSON property keys

~~~json
{
  "totalVnd": "850000",
  "totalVnd": "0"
}
~~~

Một parser có thể chọn một giá trị khi có duplicate keys, làm thay đổi ngữ nghĩa tiền. Với dữ liệu quan trọng, cần **duplicate-key detection/strict parsing** theo policy, không trông đợi một Java `Map` đã bind có thể khôi phục lịch sử cả hai giá trị.

### 11.5. Case-insensitive mapping và aliases cần có giới hạn

Các tên:

~~~text
totalVnd
TotalVnd
total_vnd
total-vnd
~~~

không tự là cùng một field trong mọi schema. Có thể hỗ trợ alias theo version và producer, nhưng nếu cùng message chứa cả `totalVnd` và `total_vnd` với giá trị khác nhau, phải báo **AMBIGUOUS_FIELD_ALIAS** thay vì chọn cái đến sau. Đừng bật case-insensitive property matching để che thay đổi contract mà không có audit.

## 12. Khi nào nên giữ field lạ trong extension bag?

### 12.1. Extension bag là một contract, không phải thùng rác

Một số domain có extensibility được thiết kế rõ:

~~~json
{
  "orderId": "ORD-901",
  "amountVnd": 850000,
  "extensions": {
    "partnerA.campaignHint": "winter"
  }
}
~~~

Khi đó extension **có namespace, allowlist, type, size limit và quyền**. Consumer hiểu extension nào thì dùng; consumer khác có thể bỏ qua. Nhưng không có lý do cho phép một trường tự khai như `"riskApproved": true` trong extensions thay thế kiểm tra rủi ro thật.

### 12.2. Những rủi ro cần tránh

- **Mass assignment:** client gửi field có tên giống internal property để ghi đè status/tenant/permissions.
- **PII leakage:** extension chứa email, token, địa chỉ nhưng bị forward tới nhiều recipients.
- **Schema shadowing:** có cả `amountVnd` chuẩn và `extensions.amountVnd`, hai giá trị mâu thuẫn.
- **Payload inflation:** hàng nghìn keys hoặc values rất lớn gây tốn memory/network.
- **Unknown executable/type hints:** field dùng làm class name, SpEL expression hoặc URL mà hệ thống tự thực thi.
- **Replay ambiguity:** extension bị loại ở attempt đầu nhưng được dùng ở attempt sau khi code nâng cấp, làm thay đổi outcome cùng event.

Nếu application cần metadata thực sự riêng của partner, giữ nó ở **vùng được định danh và versioned**, không đưa tùy ý vào core `NormalizedOrder` hoặc untrusted Spring Message headers.

### 12.3. Field-sensitive policies

Một hợp đồng production nên có thể quy định:

~~~text
partnerA.schemaV1:
  ignored fields:
    legacyCampaignHint -> WARNING

  mapped extensions:
    partnerA.promoReference -> approved string, maxLength=64

  forbidden fields:
    rawPassword
    bearerToken
    privilegedRole

  unknown fields:
    STRICT_QUARANTINE
~~~

Danh sách trên là **mẫu policy**, không phải config Spring Integration mặc định. Quá trình triển khai phải đảm bảo parser phát hiện fields trước khi chúng bị ignore, và không log nguyên giá trị nhạy cảm vào reason codes.

## 13. Mapping contract và schema evolution

### 13.1. Một thay đổi có thể chỉ thêm field, nhưng ý nghĩa lại thay đổi

Producer V1:

~~~json
{
  "partnerOrderRef": "ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "STD"
}
~~~

Producer V2:

~~~json
{
  "partnerOrderRef": "ORD-901",
  "totalVnd": "850000",
  "deliveryCode": "STD",
  "taxIncluded": false
}
~~~

Field mới `taxIncluded=false` có thể **thay đổi ý nghĩa của số tiền**. Nếu V1 giả định mọi giá là đã gồm thuế, việc ignore `taxIncluded` có thể khiến canonical amount sai dù `totalVnd` vẫn parse hoàn hảo.

**Unknown field không phải lúc nào cũng độc lập với các field đã biết.** Khi producer thay đổi schema, cần review business semantics, không chỉ số lượng unmapped fields.

### 13.2. Schema version phải được xác định tại ingress

Một wire envelope nên chỉ ra:

~~~text
eventType=partner.order.submitted
schemaVersion=2
authenticatedPartner=PARTNER-A
payload={...}
~~~

Với phiên bản không được hỗ trợ, chọn:

- **Reject/quarantine** cùng `UNSUPPORTED_SCHEMA_VERSION`.
- **Upcast/downcast** có mapping được thiết kế và kiểm thử cho đúng dữ liệu.
- **Dual-read migration** (consumer hỗ trợ V1 và V2) trong thời gian transition.

Không nên gắn schema V2 vào translator V1 rồi áp dụng unknown-ignore mặc định, nhất là ở lĩnh vực tiền, rủi ro, giao vận hoặc kiểm soát quyền.

### 13.3. Backward/forward compatibility không chỉ là compile

| Thay đổi producer | Consumer V1 | Quyết định |
|---|---|---|
| Thêm field optional không ảnh hưởng business | Có thể chấp nhận. | Allowlisted ignore + warning hoặc extension. |
| Thêm field ảnh hưởng tính giá | Không an toàn khi ignore. | New mapping/version, quarantine cũ. |
| Đổi tên `totalVnd` → `grossVnd` | V1 thiếu required field. | Alias/migration có version. |
| Đổi đơn vị VND → USD | Có thể parse số nhưng ngữ nghĩa sai. | Currency-aware conversion, không đoán. |
| Thêm enum deliveryCode | V1 không biết giá trị. | Explicit mapping hoặc unsupported enum. |
| Xóa field nguồn optional | Có thể chấp nhận theo contract. | Default hoặc optional target. |
| Xóa field nguồn required | V1 không thể tạo canonical hợp lệ. | Reject/enrich có thẩm quyền. |
| Đổi null semantics | Có nguy cơ gán sai default. | Presence-aware migration/test. |
| Thêm nested object | Parser/mapper có thể bỏ cả nhánh. | Schema validation và nested mapping diagnostics. |

### 13.4. Quy tắc mapping cần version hóa cùng code

Một mapping registry/rule set có thể gồm:

~~~text
mappingPolicyId = partnerA-order
mappingVersion  = 2026-11
sourceSchema    = partner.order.v2
targetSchema    = normalized.order.v3
acceptedSources = [PARTNER-A]
unknownFields   = QUARANTINE
approvedIgnored = [legacyCampaignHint]
defaults        = [deliveryCode absent -> STANDARD]
~~~

Các giá trị là minh họa. Với dữ liệu đã quarantine, phải có khả năng xác định **policy nào đã được dùng ở lần nhận đầu**, và policy mới nào được dùng khi replay. Không thay đổi nội dung record cũ rồi xóa mất lý do từ chối ban đầu.

### 13.5. Không lẫn schema version với business version

`sourceSchemaVersion=2` là phiên bản biểu diễn message, không phải `orderVersion=2` của một business order. Một Resequencer cần thứ tự thay đổi đơn hàng phải dùng business sequence/aggregate version được định nghĩa rõ; không lấy số schema version thay.

## 14. Mapper library: tiện lợi nhưng không thay hợp đồng nghiệp vụ

### 14.1. Mapping bằng tay, MapStruct và serializer khác nhau

| Công cụ/cách | Phù hợp với | Điều cần bổ sung |
|---|---|---|
| Java thuần như `PartnerOrderTranslator` | Quy tắc có điều kiện, diagnostics, value validation. | Bảo trì khi field nhiều; cần unit/contract tests. |
| MapStruct | Mapping typed Java bean/record và phát hiện field target/source không map tại compile time. | Business policy, raw unknown JSON, security, recovery. |
| Jackson/ObjectMapper | JSON ↔ Java object, schema binding, unknown-property behavior tùy config. | Semantic mapping, currency/enum/default, audit. |
| JSON Schema/Avro/Protobuf | Kiểm tra/định nghĩa wire schema và compatibility. | Canonical domain translation, authorization, idempotency. |
| Custom dynamic mapping config | Nhiều partner/schema và runtime rules. | Versioning, validation/sandbox, performance, provenance. |

### 14.2. Compile-time unmapped target khác runtime unknown source

Với MapStruct, `unmappedTargetPolicy` có thể giúp phát hiện **field đích** chưa có ánh xạ tại build. `unmappedSourcePolicy` có thể hỗ trợ cảnh báo field nguồn không được dùng ở **typed source model**; cách dùng còn tùy version và cấu hình mapper.

~~~java
// Minh họa policy annotation khi dự án có MapStruct dependency.
// Chưa chạy compile tại STEP 4; không thay thế contract tests.
import org.mapstruct.Mapper;
import org.mapstruct.ReportingPolicy;

@Mapper(
    unmappedTargetPolicy = ReportingPolicy.ERROR,
    unmappedSourcePolicy = ReportingPolicy.WARN
)
interface MappingPolicyExample {
    // Generated mapper methods được khai báo tại đây.
}
~~~

**Quan trọng:**

- Compile-time warning chỉ thấy những fields trong **Java source type**, không biết field JSON lạ đã bị parser bỏ.
- Một `Map<String,Object> extensions` có thể chứa vô số runtime keys mà compiler không enumerate được.
- Một field được MapStruct map tự động theo tên chưa chắc đúng ngữ nghĩa hoặc cùng đơn vị.
- Annotation không thay thế policy quarantine, business validation, source authorization và replay.

Đừng kết luận “không có compiler warning” đồng nghĩa mọi field quan trọng đã map đúng.

### 14.3. Một target field có mapping nhưng output vẫn sai

Ví dụ nguồn `amountCents=850000`, target `amountVnd`, mapper có thể gán số thẳng nếu type tương thích. Nhưng nếu source là **USD cents**, target là **VND**, thì đó là mapping sai về đơn vị, không phải thành công.

Với tiền, xác định:

- Currency và minor/major units của nguồn.
- Rounding mode/scale được phê duyệt.
- Tỷ giá và timestamp nguồn nếu đổi currency.
- Giá trị nào dùng cho idempotency fingerprint.
- Dấu âm, null, 0 và giới hạn giá trị.

Không dùng `double` hoặc `toString()` để xử lý tiền tùy tiện. Nếu conversion cần external FX service, đó là enrichment có failure/recovery semantics riêng.

### 14.4. Unknown enum không nên bị map về một giá trị có ý nghĩa nghiệp vụ khác

Anti-pattern:

~~~java
// Sai nếu default không được business phê duyệt.
ShippingTier map(String code) {
    return switch (code) {
        case "EXP" -> ShippingTier.EXPRESS;
        default -> ShippingTier.STANDARD;
    };
}
~~~

Khi `code="SAME_DAY"` xuất hiện, hệ thống sẽ âm thầm biến nó thành STANDARD. Tốt hơn là **case "STD"** và **case "EXP"** riêng; default phải báo `UNSUPPORTED_DELIVERY_CODE`. Chỉ khi hợp đồng nói mọi unknown value đều STANDARD (rất hiếm với giá trị nghiệp vụ quan trọng) mới có thể làm khác, và phải có monitoring.

### 14.5. Field alias: dễ tạo xung đột dữ liệu

Ví dụ V1 dùng `totalVnd`, V2 dùng `grandTotalVnd`. Trong migration window, nếu payload chứa **cả hai**:

~~~json
{
  "totalVnd": "850000",
  "grandTotalVnd": "900000"
}
~~~

Một mapper không nên chọn đại giá trị cuối hoặc ưu tiên “mới nhất” khi chưa có contract. Có thể:

- Chặn với `CONFLICTING_FIELD_ALIASES`.
- Chỉ hỗ trợ một tên theo declared schema version.
- Nếu contract cho phép cả hai, kiểm tra chúng bằng nhau rồi dùng một giá trị đã được định nghĩa.

**Không được làm sạch mâu thuẫn bằng cách bỏ một field và không ghi dấu.**

## 15. Idempotency và replay khi sửa mapping

### 15.1. Cùng event, khác mapping policy

~~~text
First delivery:
  eventId=EVT-901
  mappingVersion=partner-order-v1
  newRiskIndicator unknown -> QUARANTINED

After policy change:
  eventId=EVT-901
  mappingVersion=partner-order-v2
  newRiskIndicator mapped -> ACCEPTED
~~~

Đây là **revalidation/retranslation của cùng logical event**, không tự động trở thành một order mới. Phải có stable source event/operation identity, replay attempt ID và audit policy version. Đừng cấp một `operationId` mới mỗi lần sửa code rồi để downstream tạo đơn thanh toán trùng.

### 15.2. Quarantine có thể chứa payload cần bảo vệ

Một quarantine case tối thiểu có thể mang:

~~~text
quarantineId: Q-901
trustedPartner: PARTNER-A
tenantScope: TENANT-A
sourceEventId: EVT-901
mappingVersion: partner-order-v1
sourceSchemaVersion: v2
reasonCodes: [UNMAPPED_SOURCE_FIELD]
fieldNames: [newRiskIndicator]
payloadReference: protected-object-ref
state: NEW
~~~

Nếu nguồn không có stable `eventId`, cần một **trusted ingress envelope identity** hoặc transport coordinate + producer contract được định nghĩa cho dedupe. Không tạo UUID mới ở mỗi redelivery rồi tưởng có khả năng chống duplicate.

### 15.3. Quarantine khác business failure

Một translation failure trước khi gọi business handler **thường chưa tạo side effect nghiệp vụ**, nhưng không được mặc định đúng trong mọi flow:

- Có thể translator đã đặt sau một endpoint khác có side effect.
- Một enrich/lookup hoặc audit đã được thực hiện.
- Broker có thể redeliver cùng event ở một pipeline khác.
- Một previous attempt có thể đã đi tới payment, rồi lỗi ở downstream và bị replay.

Vì vậy khi reprocess phải kiểm tra **durable operation ledger/receipt**, không chỉ biết quarantine case trước đó còn mới.

### 15.4. Điều kiện replay an toàn

1. **Authorize:** operator/service được phép replay đúng tenant/partner/case.
2. **Correct source/schema or mapping policy:** biết rõ thay đổi nào giúp xử lý field trước đó không map.
3. **Preserve original:** không ghi đè raw event/policy result ban đầu.
4. **Revalidate:** chạy typed decoder và translator ở policy được chỉ định.
5. **Check idempotency:** event/business operation đã hoàn tất chưa?
6. **Publish/dispatch với lineage:** giữ source event ID, có replayAttemptId/`replayOf`.
7. **Audit result:** ACCEPTED, STILL_INVALID, CONFLICT, PROCESSING_PENDING, COMPLETED.

Nếu field vẫn chưa có mapping, replay ngay 100 lần thường chỉ lặp cùng lỗi deterministic. Cần producer correction hoặc policy change thực sự, và **bounded retry** cho failure kỹ thuật riêng.

### 15.5. Không ghi đè existing receipt sau khi mapping được sửa

Một đơn đã thanh toán với amount VND 850000, sau deploy mapping mới trả amount 900000 từ cùng source event ID. Không được tự xử lý lại thành charge mới hoặc sửa receipt thành 900000. Đây là **semantic conflict** cần business reconciliation/correction event có thẩm quyền, không phải một duplicate có thể bỏ qua.

### 15.6. Source-only warning có thể là tín hiệu rollout

Mỗi field bị ignore trong lenient mode nên được quan sát theo source/schema/policy, không phải vì nó “không quan trọng mãi mãi”. Nếu tỷ lệ `newRiskIndicator` tăng từ 0 lên 100%, đó có thể là bản phát hành mới cần thỏa thuận mapping; để hệ thống ignore vĩnh viễn có thể gây lỗi nghiệp vụ.

## 16. Quarantine writer, acknowledgment và lỗi kỹ thuật

### 16.1. Mapping rejected không có nghĩa case đã lưu bền

Trong demo:

~~~text
Partner input -> Translator -> MappingResult(ERROR)
   -> Filter discardChannel -> MappingQuarantineProbe
~~~

`MappingQuarantineProbe` chỉ lưu trong RAM. Nếu JVM chết, danh sách biến mất. Với production, cần durable quarantine store hoặc queue, policy về:

- Stable case identity và duplicate detection.
- Raw/typed payload reference được mã hóa; tránh lưu thông tin bí mật thừa.
- Reason codes, field names, mappingVersion, sourceSchemaVersion và trusted partner.
- Quota, retention, permission, audit và cleanup.
- Replay/correction/versioned attempts.
- Ack của broker **sau khi durable handoff được xác nhận** theo contract.

### 16.2. Crash windows với broker và quarantine store

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant T as Translator / Filter
    participant Q as Durable Quarantine
    B->>C: Event EVT-901
    C->>T: Translate
    T-->>C: ERROR: UNMAPPED_SOURCE_FIELD
    C->>Q: Persist case key=(tenant,partner,eventId)
    Q-->>C: Commit success
    Note over C,B: Crash trước ack
    B->>C: Redelivery EVT-901
    C->>Q: Same case identity
    Q-->>C: Existing case / idempotent update
    C-->>B: Ack per transport policy
~~~

**Đây là luồng logic**, không phải lời hứa transaction nguyên tử giữa broker và database. Nếu DB commit thành công nhưng broker ack bị mất, message có thể đến lại. Quarantine insert/upsert phải idempotent; nếu dùng MongoDB/JDBC/Kafka/Redis cần kiểm tra tính atomic theo backend thật.

### 16.3. Quarantine store unavailable không làm dữ liệu “valid”

~~~text
MappingResult = ERROR
Quarantine database = TIMEOUT
~~~

Đây là **lỗi lưu kết quả**, không phải lý do để cho message invalid đi vào business flow. Một lựa chọn an toàn:

- Retry bounded với backoff cho store tạm lỗi.
- Backpressure hoặc tạm ngừng ingestion khi không có nơi lưu an toàn.
- Fallback durable queue theo hạ tầng được phê duyệt.
- Alert đội vận hành, ghi `QUARANTINE_WRITE_FAILED`.
- Không ack/commit offset một cách mù quáng trước khi có durable outcome nếu contract yêu cầu loss prevention.

### 16.4. Error channel không thay discard channel

Spring Integration có `errorChannel`/`ErrorMessage` cho lỗi xử lý theo execution model/configuration. Nhưng:

- Translator **trả `MappingResult(ERROR)` bình thường** → Filter có thể chuyển sang discard channel, không có exception.
- JSON parse lỗi **trước translator** → adapter/deserializer handler có thể xử lý riêng.
- Quarantine DB throw → technical exception, có thể được propagate/error-handled tùy direct/async adapter.
- Business payment throw **sau translator accepted** → không được tự gán `UNMAPPED_SOURCE_FIELD`.

Không nên viết một catch-all error flow rồi đưa mọi `Throwable` vào “unknown source field quarantine”. Phân loại đúng để tránh retry sai và giữ ownership của vấn đề.

### 16.5. Chọn retry theo loại lỗi

| Lỗi | Retry cùng payload ngay? | Chính sách |
|---|---|---|
| `UNMAPPED_SOURCE_FIELD` dưới strict v1 | Thường không. | Chờ mapping/schema change hoặc producer correction. |
| `UNSUPPORTED_DELIVERY_CODE` | Không nếu value không đổi. | Update allowed mapping sau review. |
| `MISSING_AMOUNT` | Không nếu raw event bất biến. | Correction từ source/authorized replay. |
| `INVALID_AMOUNT_FORMAT` | Không. | Điều tra source encoding/contract. |
| JSON parser unavailable/config lỗi | Sau khi sửa hạ tầng. | Technical error policy. |
| Quarantine database tạm down | Có giới hạn. | Backoff, dedupe, no silent ack. |
| Business API timeout | Theo operation idempotency. | Reconcile outcome UNKNOWN. |
| Security tenant mismatch | Không. | Deny/audit; không sửa bằng retry. |
| Same eventId, different raw content | Không coi là safe duplicate. | Conflict/quarantine/investigation. |

### 16.6. Đừng bật retry advice quanh toàn flow khi không biết mốc side effect

Ví dụ:

~~~text
Inbound -> Translator -> Filter -> BusinessHandler -> Ack
~~~

Nếu `BusinessHandler` đã commit nhưng reply/ack thất lạc, retry toàn chain sẽ dịch lại cùng event và có thể gọi business lần nữa. Translator thuần deterministic thì dịch lại thường ổn; **business side effect vẫn cần idempotency**. Đừng suy rằng “đã xử lý unmapped fields” đồng nghĩa an toàn trước duplicate delivery.

## 17. Metadata, Envelope Wrapper và MessageHeaders

### 17.1. Translator thay payload nhưng không được làm mất ID cần thiết

Giả sử một `Spring Message<PartnerOrderInput>` mang headers:

~~~text
businessEventId = EVT-901
correlationId   = CHECKOUT-88
traceparent     = ...
trustedTenant   = TENANT-A (from authenticated ingress)
~~~

Translator tạo `NormalizedOrder`. Message payload thay đổi; metadata phục vụ **truy vết/correlation/idempotency** vẫn cần được giữ qua boundary theo contract. Nhưng:

- Spring `MessageHeaders.ID` là ID của message runtime, có thể đổi khi build message mới.
- Một event ID nghiệp vụ phải được giữ riêng, không dùng framework ID để dedupe.
- `replyChannel`/`errorChannel` trong JVM có thể là objects nội bộ, không thể cứ serialize ra Kafka/HTTP.
- `traceparent` không tự là quyền truy cập.

### 17.2. Source-only field không nên được “giấu” trong headers tùy tiện

Anti-pattern:

~~~text
newRiskIndicator unmapped in payload
  -> .setHeader("newRiskIndicator", rawValue)
  -> every downstream consumer receives it
~~~

Đây không giải quyết thiếu mapping mà chỉ **chuyển vị trí dữ liệu**. Nếu field chứa risk/PII, có thể làm lộ thông tin. Chỉ đưa metadata vào selected headers khi nó có **mục đích rõ, schema, type, quyền và lifetime**.

### 17.3. Correlation không thay event identity

~~~text
Checkout CHECKOUT-88
  -> Event EVT-901: OrderSubmitted
  -> Event EVT-902: PaymentAuthorized
  -> Event EVT-903: InventoryReserved
~~~

Ba events có thể cùng correlation ID nhưng ba logical identities. Nếu dùng correlation làm idempotency key toàn cục, event thứ hai bị loại nhầm. Với Translator, giữ ID theo trách nhiệm của từng lớp và không sinh ID mới khi chỉ đổi schema representation của **cùng event**.

### 17.4. Mapping version khác schemaVersion

~~~text
sourceSchemaVersion = partner.order.v2
mappingVersion      = partner-to-canonical.2026-11
targetSchemaVersion = normalized.order.v3
~~~

Source schema có thể giữ nguyên trong khi mapping policy đổi (ví dụ default shipping được phê duyệt lại). Ngược lại một schema mới có thể vẫn dùng cùng mapping semantic. Vì vậy tracking các version **riêng biệt** sẽ giúp replay và điều tra chính xác.

### 17.5. Không tái dùng envelope security context khi replay trái quyền

Một quarantine case lưu `tenant=TENANT-A` từ lượt nhận cũ không tự chứng minh người đang replay hôm nay có quyền xử lý tenant đó. Replay phải kiểm tra principal/actor, trạng thái revoke/retention và quyền hiện hành. Không nhận lại header `trustedTenant` tự khai từ bên ngoài mà bỏ qua authorization.

## 18. Message Translator phối hợp với các Enterprise Integration Patterns

### 18.1. Filter: tính outcome trước, lọc sau

~~~text
PartnerOrderInput
   -> Translator computes MappingResult
   -> Filter:
        accepted -> normalized business flow
        rejected -> quarantine
~~~

Cách này giữ **reason codes** của field không map được. Nếu Filter chỉ trả Boolean bằng cách gọi mapper một lần trong predicate, rồi gọi lại mapper ở quarantine handler, policy hoặc dữ liệu tham chiếu có thể thay đổi giữa hai lần. Tốt hơn là **tính outcome một lần** rồi route chính outcome đó.

### 18.2. Router: chọn translator theo schema có thẩm quyền

~~~mermaid
flowchart LR
    INPUT["Incoming envelope"] --> VERIFY["Authenticate + validate source/type/version"]
    VERIFY --> R{"Schema Router"}
    R -->|Partner A V1| TA["Translator A V1"]
    R -->|Partner A V2| TB["Translator A V2"]
    R -->|Partner B V1| TC["Translator B V1"]
    R -->|Unsupported| Q["Schema quarantine"]
    TA --> N["Canonical model"]
    TB --> N
    TC --> N
~~~

Không route chỉ theo một `source=trusted-service` trong payload tự khai. Nếu Router không có mapping version phù hợp, **không** định tuyến mặc định tới translator cũ rồi ignore fields mới để “chạy được”.

### 18.3. Content Enricher: tách lookup khỏi mapping

Giả sử target `taxRegion` cần địa chỉ khách hàng từ CRM:

~~~text
Partner source fields -> Pure Translator -> Partial validated model
   -> Content Enricher (trusted CRM lookup)
   -> Canonical model validation
   -> Business handler
~~~

Một lookup có thể thất bại do network timeout, khác với “field nguồn không có ánh xạ”. Cần policy về stale lookup, consistency, deadline, authorization và retry riêng. Nếu enrichment trước translator, vẫn phải biết default nào dựa trên source, default nào do lookup, và giá trị nào thuộc version nào.

### 18.4. Splitter: một batch có những child không map được

~~~text
Batch B-9
  -> Item 1: mapped OK
  -> Item 2: unsupported deliveryCode
  -> Item 3: mapped OK
~~~

Nếu Splitter sinh ba child messages và Filter đẩy item 2 sang quarantine, Aggregator downstream có thể thiếu một phần. Cần:

- Stable `batchId + itemId` và correlation/sequence.
- Outcome cho rejected child nếu batch contract chờ một kết quả mỗi child.
- Timeout/release strategy cho partial failures.
- Dedupe duplicate child replies, không lấy một item lặp làm thay item thiếu.

**Không tự coi translator rejected child là success** để lấp sequence cho đủ.

### 18.5. Aggregator: không ghép dữ liệu canonical với raw mập mờ

Một Aggregator nhận kết quả từ ba đối tác, một đối tác không map được `currency`. Không nên cộng `amount` nếu chưa biết đơn vị. Chỉ aggregate các **typed canonical values đã validate**, hoặc phát một `AggregationOutcome(PARTIAL_FAILURE)` với reason, không silently bỏ nhánh có số tiền không rõ.

### 18.6. Scatter–Gather: branch replies có schema riêng

Một request fan-out tới Inventory, Pricing và Fraud. Các nhánh có thể trả:

~~~text
InventoryReplyV2 -> InventoryTranslator -> InventoryOutcome
PricingReplyV1   -> PricingTranslator   -> PricingOutcome
FraudReplyV3     -> FraudTranslator     -> FraudOutcome
~~~

Gatherer phải phân biệt **missing branch**, **invalid mapping**, **timeout** và **success**. Nếu Fraud reply chứa field chưa map được quyết định rủi ro, không được làm `APPROVED` chỉ vì hai nhánh khác thành công.

### 18.7. Resequencer: schema mapping không được làm sai thứ tự

`schemaVersion` là số phiên bản biểu diễn, không phải `sequenceNumber` của các business events. Translator có thể chuyển V1/V2 về canonical DTO nhưng vẫn phải giữ **business sequence** và `correlationId` nếu Resequencer cần.

Nếu một message `seq=2` không map được và bị quarantine, Resequencer chờ chuỗi 1,2,3 có thể bị kẹt. Thiết kế một **failure placeholder/gap policy**, hoặc quarantine cả group theo contract, không tự đánh lại `seq=3` thành `2`.

### 18.8. Idempotent Receiver: mapping sửa rồi không được tạo effect trùng

~~~text
Original event EVT-901 -> translator V1 rejects
Replay EVT-901 -> translator V2 accepts
~~~

Khi replay, downstream dedupe theo **stable business event/operation ID**, không phải mappingVersion hay Spring MessageHeaders.ID mới. Nếu đã có side effect/receipt trước đó ở một nhánh khác, cần trả previous result hoặc báo conflict, không tự khởi động operation mới.

### 18.9. Claim Check: token còn nhưng raw data có thể hết hạn

Một quarantine case có thể chỉ giữ claim token dẫn tới raw partner payload. Nếu TTL của Claim Check store ngắn hơn review/replay horizon, khi mapper được sửa lại **không còn original để dịch**. Cần protected replay source/retention phù hợp, hoặc ghi rõ không thể phục hồi. Không tự chế lại missing field dựa trên warning trước đó.

### 18.10. Gateway: cần response cho rejected mapping

Một `MessagingGateway` đang chờ reply từ sync flow có thể timeout nếu Filter discard message vào one-way quarantine. Nếu API contract cần phản hồi, nên trả:

~~~json
{
  "status": "REJECTED_MAPPING",
  "eventId": "EVT-901",
  "mappingVersion": "partner-order-v1",
  "issueCodes": ["UNMAPPED_SOURCE_FIELD"],
  "quarantineRef": "Q-901"
}
~~~

Response chỉ nên gồm **mã lỗi/field được phép lộ cho caller**, không trả nguyên dữ liệu nhạy cảm. Một event asynchronous có thể chỉ cần ack sau durable quarantine; đồng bộ Gateway cần reply path được kiểm chứng.

### 18.11. Error channel: phân loại theo điểm lỗi

~~~text
Decoder error -> raw/schema error handling
MappingResult(ERROR) -> quarantine/rejection routing
Translator implementation exception -> technical error handling
Quarantine write exception -> persistence retry/backpressure
Business handler exception -> downstream retry/reconciliation
~~~

Không dùng cùng một `RetryAdvice` cho tất cả mà không biết **side effect** và **exception scope**. Mapping failure deterministic không được sửa bằng cách retry liên tục; infrastructure failure có thể retry có giới hạn.

## 19. Vận hành: metric và audit để phát hiện field bị bỏ âm thầm

### 19.1. Những mốc có ý nghĩa

~~~text
event=SOURCE_MESSAGE_RECEIVED
  partner=PARTNER-A
  sourceSchemaVersion=v2
  eventRef=EVT-901

event=MAPPING_STARTED
  mappingVersion=partner-order-v1
  sourceType=PartnerOrderInput

event=MAPPING_COMPLETED
  status=REJECTED
  issueCodes=[UNMAPPED_SOURCE_FIELD]
  issueFields=[newRiskIndicator]

event=QUARANTINE_PERSISTED
  caseRef=Q-901
  mappingVersion=partner-order-v1

event=REPLAY_AUTHORIZED
  caseRef=Q-901
  targetMappingVersion=partner-order-v2

event=RETRANSLATION_COMPLETED
  caseRef=Q-901
  status=ACCEPTED
~~~

Đây là **schema structured logs do ứng dụng đề xuất**, không phải logs mặc định của Spring Integration. Nếu source/field name có thể chứa dữ liệu nhạy cảm, cần sanitize, truncation, whitelist và phân quyền. Đặc biệt **không ghi giá trị raw của extraFields vào logs thông thường**.

### 19.2. Metrics gợi ý

| Metric | Đo điều gì? |
|---|---|
| `translator_messages_received_total` | Số deliveries vào translator. |
| `translator_accepted_total{source,policy}` | Số outcomes accepted. |
| `translator_rejected_total{reason}` | Số outcomes rejected. |
| `translator_unmapped_fields_total{fieldClass}` | Field lạ theo nhóm phân loại hữu hạn. |
| `translator_ignored_fields_total{policy}` | Field được bỏ qua hợp lệ. |
| `translator_default_applied_total{field}` | Số lần dùng contractual defaults. |
| `translator_invalid_format_total{field}` | Giá trị không parse được. |
| `translator_unsupported_enum_total{field}` | Giá trị enum mới/chưa hỗ trợ. |
| `translator_schema_mismatch_total{sourceType}` | Schema không tương thích. |
| `mapping_quarantine_persisted_total` | Case mapping được lưu bền. |
| `mapping_quarantine_write_failed_total` | Ghi quarantine lỗi. |
| `mapping_replay_total{outcome}` | Kết quả replay/retranslation. |
| `translator_latency_seconds` | Độ trễ mapping. |
| `mapping_policy_version_active` | Phiên bản policy đang chạy theo cấu hình hữu hạn. |

Metric names chỉ là ví dụ. Không dùng `eventId`, `orderId`, `customerId`, `quarantineId` hay free-form unknown field values làm labels vì có thể tạo cardinality khổng lồ hoặc rò rỉ dữ liệu. Với unknown field names có nhiều biến thể, gộp theo `known_ignored/critical_unknown/other_unknown`; muốn điều tra cụ thể thì dùng log có kiểm soát.

### 19.3. “Translated successfully” có thể vẫn chưa có business result

| Mốc | Có thể khẳng định | Không thể khẳng định |
|---|---|---|
| Raw received | Adapter nhận bytes/record. | Typed decode đã thành công. |
| JSON decoded | Cú pháp/kiểu đã parse theo decoder. | Mapping đúng business semantics. |
| Mapping accepted | Translator tạo canonical outcome theo rule. | Business handler đã commit. |
| Warning ignored field | Field bị bỏ theo policy đang áp dụng. | Field chắc chắn không quan trọng ở phiên bản tương lai. |
| Filter discarded | Không đi tiếp trên đường accepted của Filter. | Quarantine record đã lưu bền. |
| Quarantine persisted | Case đã được ghi theo store contract. | Replay đã hoàn tất business operation. |
| Business receipt COMPLETED | Operation có outcome có thẩm quyền. | Remote side effect được rollback atomically khi dùng hệ thống ngoài. |
| Broker ack | Transport ghi nhận theo semantics của nó. | Không có duplicate republish trong tương lai. |

### 19.4. Message History không cho biết field nào bị bỏ

Spring Integration Message History (khi bật tracking) có thể cho thấy message đã qua Transformer/Filter nào. Nhưng nó không tự biết:

- `newRiskIndicator` bị parser bỏ trước khi vào flow.
- Mapping policy đã chấp nhận ignore theo business approval nào.
- `totalVnd` bị đổi đơn vị sai nhưng không throw.
- Target required field được bịa default ngoài contract.
- Quarantine case đã commit/được replay theo phiên bản nào.

Vì vậy cần **mapping diagnostics, contract tests, audit policy/version và business idempotency receipt** bổ sung.

### 19.5. Runbook khi số unmapped fields tăng đột biến

1. Xác nhận **source/tenant/schema version** bị ảnh hưởng.
2. Kiểm tra **tên field đã sanitize**, mức độ severity và mappingVersion đang active.
3. Xác định producer vừa deploy hay có thay đổi schema/feature flag không.
4. Đánh giá **ngữ nghĩa field mới** với business/domain owner, đặc biệt tiền/thuế/quyền/rủi ro.
5. Kiểm tra mode `STRICT_QUARANTINE` hay `WARN_AND_IGNORE` và những message đã accepted khi field bị ignore.
6. Nếu nghi sai dữ liệu nghiệp vụ, hạn chế ingestion/processing theo risk policy thay vì tăng ignore list vô điều kiện.
7. Tạo/update contract version hoặc translator mapping và regression tests.
8. Kiểm tra **replay eligibility**, original reference, tenant permission, stable eventId và operation receipts.
9. Revalidate/retranslate dưới policy mới với audit và bounded attempts.
10. Đối chiếu số accepted/rejected/quarantined/persisted, không gộp các mốc.

## 20. Ma trận kiểm thử field không có ánh xạ

| ID | Tình huống | Kết quả mong đợi | Điều không được xảy ra |
|---|---|---|---|
| MT-01 | Tất cả source fields đã biết, dữ liệu hợp lệ | Tạo `NormalizedOrder` đúng giá trị. | Thay đổi orderId/amount. |
| MT-02 | `partnerOrderRef` khác tên `orderId` | Rename theo mapping. | Đặt target orderId rỗng. |
| MT-03 | `totalVnd="850000"` | `BigDecimal("850000")`. | Dùng double gây sai số. |
| MT-04 | `totalVnd="0"` | `AMOUNT_OUT_OF_RANGE`. | Thực hiện payment 0 theo default sai. |
| MT-05 | `totalVnd="-1"` | `INVALID_AMOUNT_FORMAT` theo demo. | Cho amount âm vào business. |
| MT-06 | `totalVnd="8,500"` | `INVALID_AMOUNT_FORMAT`. | Đoán locale/đơn vị. |
| MT-07 | `totalVnd="8500.50"` | `INVALID_AMOUNT_FORMAT` của hợp đồng số nguyên. | Silent rounding. |
| MT-08 | `totalVnd=null` | `MISSING_AMOUNT`. | Default 0. |
| MT-09 | `totalVnd=""` hoặc blank | `MISSING_AMOUNT`. | Parse như số 0. |
| MT-10 | Giá trị số quá dài | `INVALID_AMOUNT_FORMAT`, bound resource. | Tốn memory/CPU không giới hạn. |
| MT-11 | Giá trị lớn hơn max demo | `AMOUNT_OUT_OF_RANGE`. | Vượt giới hạn không báo. |
| MT-12 | `deliveryCode=STD` | `ShippingTier.STANDARD`. | Value ngược. |
| MT-13 | `deliveryCode=EXP` | `ShippingTier.EXPRESS`. | Value ngược. |
| MT-14 | `deliveryCode` thiếu | Default STANDARD + warning theo contract V1. | Dùng default mà không audit. |
| MT-15 | `deliveryCode=OVERNIGHT` | `UNSUPPORTED_DELIVERY_CODE`. | Auto fallback STANDARD. |
| MT-16 | `eventId` thiếu | `MISSING_EVENT_ID`, không accepted. | Tạo UUID ở consumer attempt. |
| MT-17 | `partnerOrderRef` thiếu | `MISSING_ORDER_ID`. | Tạo blank order. |
| MT-18 | `legacyCampaignHint` trong extraFields | Ignore + `IGNORED_LEGACY_FIELD` warning. | Tự thêm raw value vào canonical DTO. |
| MT-19 | `newRiskIndicator` trong strict mode | `UNMAPPED_SOURCE_FIELD` ERROR. | Bỏ qua im lặng. |
| MT-20 | `newRiskIndicator` trong lenient mode | Warning, accepted theo policy đã phê duyệt. | Không có telemetry. |
| MT-21 | Hai unknown fields cùng message | Lưu đủ tên field/reasons (không raw secret). | Chỉ ghi thành công giả. |
| MT-22 | Cùng source field nhưng schema V2 đổi semantics | Version-specific mapping/quarantine. | Dùng rule V1 làm sai tiền/thuế. |
| MT-23 | JSON chứa key mới, parser ignore unknown mặc định | Test phát hiện/ghi nhận ở ingress. | Translator tưởng không có field lạ. |
| MT-24 | Malformed JSON trước typed input | Adapter raw error route. | Claim Filter xử lý được typed outcome. |
| MT-25 | JSON duplicate keys | Parser/schema validation phát hiện. | Chọn giá trị mơ hồ. |
| MT-26 | Cả `totalVnd` và alias `grandTotalVnd` khác nhau | `CONFLICTING_FIELD_ALIASES` hoặc reject theo schema. | Ưu tiên ngẫu nhiên. |
| MT-27 | Source-only field đã phê duyệt ignore | Warning/audit theo mappingVersion. | Đẩy vào mọi headers downstream. |
| MT-28 | Required target `riskApproval` không có nguồn | Enrich có thẩm quyền hoặc reject. | Default APPROVED. |
| MT-29 | Optional target thiếu, default có contract | Default + diagnostic/contract version. | Gán default cho unknown value. |
| MT-30 | Source money dùng đơn vị khác | Currency-aware mapping hoặc reject. | Cộng hai đơn vị tiền khác nhau. |
| MT-31 | Source enum thêm giá trị hợp lệ ở V2 | Translator V2 mapping và tests. | V1 silently accept không xem xét. |
| MT-32 | Field lạ chứa bearer token | Không log/forward raw; deny theo policy. | Rò rỉ token vào quarantine log/metrics. |
| MT-33 | Untrusted tenant trong payload | Bind bằng authenticated tenant. | Chuyển sang tenant khác. |
| MT-34 | Same event, Spring Message ID mới | Stable `sourceEventId`. | Business effect lặp do runtime UUID. |
| MT-35 | Same source eventId nhưng raw payload mâu thuẫn | Identity conflict/review. | Dedupe mù quáng. |
| MT-36 | Accepted branch | Business probe nhận một `NormalizedOrder`. | Quarantine nhận nhầm. |
| MT-37 | Strict rejected branch | Quarantine probe nhận `MappingResult` có issues. | Business handler được gọi. |
| MT-38 | Filter thiếu discard channel | Test phát hiện record không được giữ. | Silent drop được coi thành công. |
| MT-39 | `throwExceptionOnRejection` bật | Error semantics đúng cấu hình được test. | Tự khẳng định discard vẫn hoạt động. |
| MT-40 | Quarantine store down | Bounded technical retry/backpressure. | Ack rồi mất original. |
| MT-41 | Broker ack mất sau quarantine commit | Dedupe case idempotent. | Tạo case trùng vô hạn. |
| MT-42 | Quarantine raw payload hết retention trước replay | Báo không thể replay hoặc nguồn hợp lệ khác. | Tự tạo lại thiếu dữ liệu. |
| MT-43 | Policy V1 rejected, policy V2 accepted | Versioned retranslation + audit. | Xóa original/reason cũ. |
| MT-44 | Replay same event đã có business receipt | Idempotent previous outcome. | Tạo payment/operation mới. |
| MT-45 | Splitter có một child mapping error | Failure outcome/correlation/gap policy. | Aggregator chờ mãi. |
| MT-46 | Aggregator nhận amount chưa rõ currency | Reject/partial failure theo contract. | Cộng sai đơn vị. |
| MT-47 | Scatter–Gather Fraud reply unmapped critical field | Không APPROVED toàn request. | Bỏ qua Fraud. |
| MT-48 | Resequencer có gap do mapping rejected | Gap/placeholder/timeout policy. | Đảo thứ tự hoặc giả success. |
| MT-49 | Gateway mapping rejected | Có rejected response/error contract. | Caller treo không giới hạn. |
| MT-50 | Producer thêm field lạ hàng loạt | Cảnh báo source/policy, review schema drift. | Ignore vô thời hạn không theo dõi. |
| MT-51 | MapStruct compile không warning nhưng raw key mới | Runtime decoder/schema test bắt được. | Đồng nhất compiler check với wire safety. |
| MT-52 | Extension bag quá lớn | Size/count/type bounds, backpressure. | OOM hoặc log injection. |
| MT-53 | Unknown field tên chứa ký tự điều khiển | Sanitize field path/log output. | Log forging/injection. |
| MT-54 | Retry sau khi source bị revoke | Reauthorization theo principal hiện tại. | Dùng metadata cũ để vượt quyền. |
| MT-55 | Success count khác durable persisted count | Dashboard phân biệt các mốc. | Báo mọi rejected đều đã quarantine bền. |

### 20.1. Bậc kiểm thử nên dùng

| Tầng | Kiểm tra | Chưa chứng minh |
|---|---|---|
| **Unit translator** | Field mapping, null/enum/amount, severity/policy. | Spring flow routing hoặc broker. |
| **JSON/schema contract** | Raw unknown keys, duplicate keys, aliases, size/type/version. | Durable quarantine commit. |
| **Spring Integration flow** | Transformer → Filter → discard/business handlers. | Multi-node persistence nếu dùng fake. |
| **Adapter test** | Deserialize, header mapping, error channel/DLQ, ack. | Business external payment idempotency. |
| **Database test** | Quarantine unique key, transaction, concurrent writes, retention. | Ack của broker nếu không dùng broker. |
| **System/recovery** | Crash windows, replay, source version migration, multi-node. | Mọi lỗi thực tế chưa được mô phỏng. |
| **Security test** | AuthN/AuthZ, tenant, PII masking, protected replay. | Trust boundaries chưa review. |

### 20.2. Golden mapping fixtures

Để phát hiện thay đổi sai sau deploy, nên giữ ít nhất các fixtures có version:

~~~text
Fixture A / partnerA-v1-accepted:
  eventId=EVT-A1, orderRef=ORD-A1
  totalVnd=850000, deliveryCode=EXP
  expected.amountVnd=850000, shippingTier=EXPRESS

Fixture B / partnerA-v1-ignored:
  legacyCampaignHint=retired
  expected.accepted=true
  expected.warning=IGNORED_LEGACY_FIELD

Fixture C / partnerA-v2-new-field:
  newRiskIndicator=high
  expected.strictV1.error=UNMAPPED_SOURCE_FIELD
  expected.v2.mapping=explicitly approved outcome

Fixture D / partnerA-v1-unknown-enum:
  deliveryCode=OVERNIGHT
  expected.error=UNSUPPORTED_DELIVERY_CODE
~~~

Những fixtures nên test cả **raw serialization → typed input → mapping result → flow routing**; nếu chỉ tạo Java object đã typed sẵn, có thể bỏ sót unknown JSON field từ parser.

## 21. Những anti-pattern cần tránh

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| “Field nào không map thì mặc định bỏ.” | Mất dữ liệu có ý nghĩa. | Strict policy hoặc allowlist ignore có audit. |
| “Field lạ luôn là lỗi nghiêm trọng.” | Bản mở rộng optional cũng làm dừng ingestion. | Phân loại critical/approved ignored/extension. |
| “MapStruct không warning nghĩa là raw JSON không có unknown field.” | Runtime field có thể bị decoder bỏ trước. | Schema-aware ingress diagnostics. |
| “Target required thiếu thì default cho đủ constructor.” | Tạo giá trị nghiệp vụ sai, có thể nguy hiểm. | Enrich/optional/reject theo contract. |
| “Enum mới cứ map STANDARD.” | Tự đổi điều kiện giao hàng. | Explicit enum mapping và unsupported error. |
| “Amount parse được là đúng tiền.” | Sai currency/scale/đơn vị. | Semantic conversion với version/validation. |
| “Ignore field nhưng không cần warning.” | Không phát hiện schema drift. | Warning metrics và mappingVersion. |
| “Bỏ raw field bằng cách đưa vào Spring header.” | Rò rỉ dữ liệu và route injection. | Metadata allowlist, protected extension bag. |
| “Default cho missing và unknown là một.” | Giá trị mới bị che. | Missing-only default có contract. |
| “Bất cứ null nào cũng là zero/false.” | Có thể đồng nhất UNKNOWN với phủ định. | Presence-aware validation và optional semantics. |
| “Một retry mapping tạo eventId mới.” | Idempotency vô hiệu. | Stable event/operation identity. |
| “Quarantine ghi vào list là đủ durable.” | Crash làm mất case. | Durable DB/queue và ack sequencing. |
| “Dùng throw exception cho mọi mapping issue.” | Khó phân loại business-invalid và technical failure. | Typed MappingResult + error path riêng. |
| “Filter false tự lưu message.” | Silent discard. | Discard channel/quarantine handler. |
| “Gateway duplicate/rejected tự trả reply.” | Caller timeout. | Reply/error contract. |
| “Nếu target thiếu field, coi translator đã chạy xong.” | Partial object có thể lọt business. | Validate canonical invariants trước handler. |
| “Cùng raw event được dịch lại sẽ có cùng business outcome bất kể policy.” | Mapping mới có thể thay nghĩa và side effects. | Versioned replay + reconcile/receipt conflict handling. |
| “Đổi schema V2 là có thể bỏ V1 ngay.” | Historical events/DLQ không thể replay. | Backward compatibility theo retention. |
| “Chỉ unit test map đúng thì production an toàn.” | Header/decoder/store/ack có thể lỗi. | Contract/adapter/system tests. |

## 22. Bài tập thực hành

1. **Mapping cơ bản:** dùng `PartnerOrderTranslator` để đổi `partnerOrderRef`, `totalVnd`, `deliveryCode` thành `NormalizedOrder` và kiểm tra từng field.
2. **Source-only allowlist:** gửi `legacyCampaignHint`, giữ mapping accepted nhưng sinh warning; chứng minh raw value không đi tới `NormalizedOrder`.
3. **Unknown strict:** thêm `newRiskIndicator` vào `extraFields`; assert `UNMAPPED_SOURCE_FIELD` và `normalized==null`.
4. **Unknown lenient:** bật `WARN_AND_IGNORE` trong unit test, so sánh accepted/status với strict mode và giải thích rủi ro nếu không có approval.
5. **Multiple fields:** gửi hai unknown fields, kiểm tra đủ reasons và không log raw values.
6. **Missing required:** bỏ `eventId`, `partnerOrderRef` hoặc `totalVnd`; xác minh mỗi lỗi có reason code riêng.
7. **Missing vs null:** dùng raw JSON parser để phân biệt key vắng mặt và explicit null trước khi bind DTO; xác nhận policy lựa chọn.
8. **Default đúng hợp đồng:** bỏ `deliveryCode`, nhận STANDARD + `SHIPPING_DEFAULT_APPLIED`.
9. **Unknown enum:** gửi `deliveryCode=OVERNIGHT`, assert error thay vì fallback.
10. **Amount locale:** thử `850000`, `850000.0`, `850,000`, `1E6`; xác nhận chỉ format đã khai được chấp nhận.
11. **Giới hạn input:** tạo `totalVnd` quá dài; assert reject có kiểm soát mà không parse toàn số khổng lồ.
12. **Target-only risk field:** thêm required `riskApproval` vào canonical model, thiết kế reject/enrich có thẩm quyền, tuyệt đối không default APPROVED.
13. **Extension bag:** định nghĩa namespace/allowlist/type/length cho một metadata field của partner; test shadowing với core field.
14. **Jackson unknown property:** thử một JSON key mới bị mapper mặc định ignore; sửa ingress parser để phát hiện trước khi translator chạy.
15. **Duplicate JSON keys:** tạo raw JSON có hai `totalVnd`; cấu hình parser/validation báo conflict.
16. **Field aliases:** cho V1 `totalVnd` và V2 `grandTotalVnd`; kiểm tra khi cả hai có giá trị khác nhau.
17. **Schema V2:** đổi `newRiskIndicator` thành field chính thức sau review, tăng mappingVersion và tạo golden fixtures.
18. **Partner scope:** cùng source key từ Partner A và Partner B, chọn hai policy độc lập; không dùng allowlist của A cho B.
19. **Tenant authorization:** tạo input có tenant tự khai khác authenticatedTenant; xác minh không bị map thành tenant quyền cao hơn.
20. **Spring DSL accepted:** gửi message qua `partner.order.input`; assert business probe có đúng một `NormalizedOrder` và quarantine rỗng.
21. **Spring DSL rejected:** gửi unknown field qua strict mode; assert quarantine có `MappingResult` và business probe rỗng.
22. **Filter error semantics:** thử bỏ `discardChannel` hoặc bật `throwExceptionOnRejection`; giải thích từng kết quả và cách tránh silent drop.
23. **Header preservation:** đưa `businessEventId` và `correlationId` qua Transformer/adapter, kiểm tra không bị mất và không nhầm `MessageHeaders.ID`.
24. **Broker redelivery:** cùng event ở hai Spring Messages với runtime IDs khác; downstream Idempotent Receiver vẫn chỉ áp dụng một business operation.
25. **Durable quarantine:** thay probe bằng JDBC repository có unique `(tenant,partner,eventId,caseType)` phù hợp; kiểm tra hai workers ghi cùng lúc.
26. **Crash/ack:** mô phỏng commit quarantine xong nhưng ack broker bị mất; redelivery tạo một case idempotent, không tạo hai.
27. **Store failure:** làm quarantine DB unavailable; kiểm tra không cho message rejected chảy vào business và có bounded retry/backpressure.
28. **Replay có quyền:** thay mappingVersion V1 bằng V2, retranslate một quarantined event theo authorization và audit; không mất raw original.
29. **Replay conflict:** same eventId nhưng amount thay đổi; kiểm tra completion ledger và từ chối tự ý charge lại.
30. **Splitter/Aggregator:** một child có unknown enum, sinh failure outcome có correlation/sequence để Aggregator không đợi vô hạn.
31. **Scatter–Gather:** Pricing/Inventory thành công nhưng Fraud mapping fail; Gatherer không trả overall APPROVED.
32. **Resequencer:** message seq=2 bị quarantine; tạo gap policy hoặc failure placeholder, giữ business sequence không đổi.
33. **Gateway response:** caller gửi malformed/unsupported mapping, nhận `REJECTED_MAPPING` có issue codes và reference, không timeout vô cớ.
34. **Metrics:** xây dashboard accepted/rejected/quarantine persisted/unknown warnings; không dùng event IDs hoặc raw unknown values làm metric labels.
35. **Runbook:** viết checklist xử lý tăng `UNMAPPED_SOURCE_FIELD` theo source/schema, từ producer deploy đến mapping policy upgrade và controlled replay.

### 22.1. Tiêu chí hoàn thành thực hành

Một implementation được đánh giá tốt khi:

- Mỗi field nguồn quan trọng có **mapping rule hoặc quyết định rõ**.
- Source-only ignored fields có approval, warning và policy version.
- Target-only required fields không được bịa default trái nghĩa.
- Missing/null/blank/unknown enum/unknown field được phân loại tách biệt.
- Giá trị tiền/đơn vị được chuyển đúng contract, không dùng double.
- Translator trả kết quả có reason code và không phát canonical object khi còn ERROR.
- Spring flow chuyển accepted và rejected vào **đúng handler**, không silent drop.
- Lỗi parser trước translator và lỗi store sau translator có error path riêng.
- Stable eventId, tenant/source trust boundary và quyền replay được bảo vệ.
- Có test dữ liệu raw → typed → mapping → channel → business/quarantine, không chỉ test một hàm map.

## 23. Câu hỏi tự kiểm tra

**Câu 1: Message Translator gặp source field không có target tương ứng, có phải luôn xóa nó không?**

Không. Cần policy: reject/quarantine, ignore có approval, preserve extension có giới hạn hoặc mở rộng canonical model. Quyết định dựa trên ngữ nghĩa nghiệp vụ và hợp đồng dữ liệu.

**Câu 2: Source-only và target-only khác nhau gì?**

Source-only là trường nguồn có nhưng đích không yêu cầu; target-only là trường đích cần nhưng nguồn không cấp. Trường target-only bắt buộc có thể cần enrichment hoặc reject, không thể giải quyết chỉ bằng ignore.

**Câu 3: Nếu `legacyCampaignHint` đã được phê duyệt bỏ qua, có cần ghi warning không?**

Nên có diagnostics/telemetry theo policy để xác nhận field bị ignore có chủ đích và phát hiện drift, nhưng không nhất thiết log giá trị raw.

**Câu 4: `deliveryCode=null` và `deliveryCode=OVERNIGHT` có nên đều map STANDARD?**

Không. Trong demo, missing/null có default STANDARD **theo hợp đồng V1**; OVERNIGHT là một enum value mới chưa hỗ trợ nên phải báo lỗi.

**Câu 5: Vì sao `totalVnd="850000"` parse được mà vẫn chưa đủ để khẳng định mapping đúng?**

Còn phải biết đơn vị, currency, scale, tổng trước/sau thuế, giới hạn và business semantics. Một mapping đúng kiểu dữ liệu vẫn có thể sai nghĩa.

**Câu 6: Tại sao cần `MappingResult` thay vì trả thẳng `NormalizedOrder`?**

Vì cần lưu issues, severity, mappingVersion, nguồn và quyết định accepted/rejected để điều tra hoặc replay một cách có kiểm soát.

**Câu 7: Nếu Jackson đã bỏ unknown JSON field trước khi tạo DTO, translator có thể phát hiện lại không?**

Không từ DTO đã bị lược bỏ. Cần schema-aware parser, tree model, strict error hoặc extension collector ở ingress.

**Câu 8: MapStruct báo không có unmapped target ở compile-time, có chứng minh raw JSON không có field lạ không?**

Không. Compiler không thấy những runtime keys đã bị decoder bỏ hoặc nằm trong map. Vẫn cần contract/runtime tests.

**Câu 9: Vì sao không chuyển mọi unmapped fields vào Spring headers?**

Vì sẽ lộ dữ liệu, phá ranh giới domain/transport, tăng payload, có thể bị header injection và làm consumer nhận fields không được phép.

**Câu 10: Một field mới `taxIncluded` có thể bỏ qua vì đã biết `totalVnd` chưa?**

Không được mặc định. `taxIncluded` có thể thay đổi nghĩa của total; phải review schema semantics và mapping.

**Câu 11: Filter rejected có nghĩa message đã được lưu durable quarantine chưa?**

Chưa. `discardChannel` chỉ định đường đi; cần durable writer/ack, persistence và test recovery.

**Câu 12: Đặt `throwExceptionOnRejection(true)` có giống discard bình thường không?**

Không. Nó thay đổi semantics khi Filter từ chối; phải kiểm tra config và error route đúng execution model.

**Câu 13: Business handler lỗi timeout sau khi mapping accepted có nên gắn `UNMAPPED_SOURCE_FIELD` không?**

Không. Đây là downstream/technical failure hoặc outcome chưa rõ, cần retry/reconciliation theo business operation.

**Câu 14: Tại sao cần mappingVersion và sourceSchemaVersion riêng?**

Vì cùng schema có thể đổi quy tắc/default qua deploy; hoặc schema mới vẫn dùng cùng mapping semantics. Hai version hỗ trợ audit/replay chính xác.

**Câu 15: Replay một event rejected trước đó bằng mapper V2 có phải business event mới không?**

Không mặc định. Nếu chỉ dịch lại cùng logical event, giữ eventId và kiểm tra downstream idempotency, thêm replay attempt lineage.

**Câu 16: Một message raw thiếu eventId được quarantine thì dedupe theo gì?**

Có thể dùng trusted ingress envelope identity hoặc transport record identity được định nghĩa đúng semantics; không tạo UUID mới mỗi lần nhận rồi gọi đó là stable key.

**Câu 17: Nếu translator được triển khai sau Splitter và một child fail mapping, Aggregator sẽ thế nào?**

Có thể bị thiếu một child. Cần error outcome/placeholder, correlation, timeout hoặc partial release theo contract, không tự coi child lỗi là SUCCESS.

**Câu 18: Một field chứa thông tin bảo mật có được đưa vào log `UNMAPPED_SOURCE_FIELD` không?**

Không ghi raw value. Chỉ dùng reason code, field name đã sanitize/masked và protected payload reference nếu cần, có quyền/retention.

**Câu 19: Vì sao `MessageHeaders.ID` không nên dùng làm dedupe identity khi retranslation?**

Spring message runtime có thể được tạo lại với ID khác; logical eventId/business operationId cần ổn định qua retry/replay.

**Câu 20: Nếu caller là Gateway sync và mapping rejected bị discard vào one-way quarantine, caller nhận gì?**

Có thể timeout. Cần response/error contract minh bạch, ví dụ `REJECTED_MAPPING` + mã issue + quarantine ref, không mặc định discard channel trả reply.

**Câu 21: Khi nào có thể dùng `WARN_AND_IGNORE`?**

Khi business/data owner phê duyệt cho partner/schema/field scope cụ thể, có giới hạn an toàn, cảnh báo/metrics và không làm sai các invariant quan trọng.

**Câu 22: Có được tự gán `riskApproval=true` để thỏa required target không?**

Không. Giá trị này phải từ nguồn có thẩm quyền; nếu chưa có thì enrich/retry có kiểm soát hoặc reject.

**Câu 23: Mapping error deterministic có nên retry tự động liên tục không?**

Không. Dữ liệu và policy chưa đổi sẽ cho cùng lỗi; cần correction hoặc mapping upgrade. Chỉ lỗi hạ tầng có thể retry có giới hạn.

**Câu 24: Vì sao một unit test mapper pass chưa đủ để đưa production?**

Vì parser có thể bỏ unknown fields, header mapping có thể làm mất event ID, quarantine store/ack có thể lỗi, và side effect có thể bị nhân đôi do broker redelivery. Cần contract, Spring Integration, adapter, persistence và recovery tests.

## 24. Kết luận

**Xử lý field không có ánh xạ** trong Message Translator là một **quyết định về hợp đồng dữ liệu và an toàn nghiệp vụ**, không chỉ là cài một tùy chọn của mapper. Trường nguồn không có đích, trường đích thiếu nguồn, enum mới, giá trị không parse được và missing/null **không phải một loại lỗi duy nhất**. Mỗi nhóm cần policy và reason code rõ: **reject/quarantine, ignore có audit, default được phê duyệt, enrichment có thẩm quyền hoặc extension schema có giới hạn**.

Với Spring Integration, một thiết kế dễ kiểm thử là **Translator tạo `MappingResult` → Filter kiểm tra accepted → business flow hoặc discardChannel tới quarantine**. Bảo toàn source event identity, correlation, trusted tenant và mapping version; phân biệt parse error trước translator với downstream error sau mapping; đừng ack/deduplicate/replay mà không biết durable outcome và business side effects.

Trong `SPRING_INTEGRATION_PATTERN`, khi phối hợp Message Translator với Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Gateway, Claim Check, Idempotent Receiver, retry và error channel, hãy luôn trả lời được: **“Field nào đã chuyển đúng nghĩa?”, “Field nào bị bỏ hoặc thiếu và theo chính sách nào?”, “Một message bị từ chối được giữ ở đâu, ai có quyền sửa rồi replay?”, và “Làm sao bảo đảm retry không nhân đôi tác động nghiệp vụ?”**. Những câu trả lời đó giúp hệ thống ít phụ thuộc vào producer, có thể nâng cấp schema an toàn, quan sát được và phục hồi được sau lỗi.
