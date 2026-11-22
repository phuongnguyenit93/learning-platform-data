# Xử lý field thiếu giữa các schema

## 1. Bài toán: ba nguồn gửi cùng một đơn hàng nhưng khác cấu trúc

Một hệ thống tiếp nhận đơn hàng từ ứng dụng đời cũ, API đối tác và phiên bản ứng dụng mới. Chúng cùng nói về **đơn hàng**, nhưng không thống nhất tên field, đơn vị tiền, cách biểu diễn thời gian hoặc dữ liệu khách hàng:

~~~json
{
  "source": "legacy-v1",
  "order_no": "O-501",
  "amount_cents": 12500,
  "created_utc": "2026-01-10T07:15:00Z"
}
~~~

~~~json
{
  "schemaVersion": "2",
  "orderId": "O-502",
  "totalAmount": "125.00",
  "currency": "USD",
  "buyer": {"email": null}
}
~~~

~~~json
{
  "schemaVersion": "3",
  "id": "O-503",
  "money": {"value": "125.00", "isoCurrency": "USD"},
  "contactEmail": "buyer@example.org",
  "placedAt": "2026-01-10T07:15:00Z"
}
~~~

**Vấn đề:** schema v1 không có field `currency` hoặc `email`; v2 có `email=null` và không có thời gian; v3 đổi tên các field. Downstream không nên phải có ba nhánh xử lý nghiệp vụ cho cả ba cấu trúc.

**Normalizer** trong Enterprise Integration Patterns là cách **đưa các định dạng đầu vào khác nhau về một định dạng chuẩn chung** bằng cách phối hợp **Message Router** và **Message Translator/Transformer**. Với Spring Integration, pattern này thường được xây dựng bằng Router phân loại nguồn/schema và các Transformer chuyển về **canonical message**; không có nghĩa cứ gọi `.transform()` một lần là tự giải quyết được dữ liệu bị thiếu.

~~~mermaid
flowchart LR
    A["Legacy schema v1"] --> ROUTER["Router: nguồn + schema"]
    B["Partner schema v2"] --> ROUTER
    C["Mobile schema v3"] --> ROUTER
    ROUTER --> T1["Transformer v1"]
    ROUTER --> T2["Transformer v2"]
    ROUTER --> T3["Transformer v3"]
    T1 --> CANON["CanonicalOrder"]
    T2 --> CANON
    T3 --> CANON
    CANON --> VALID["Canonical validation"]
    VALID --> BUS["Business flow"]
~~~

Bài thuộc chương **Normalizer**, module **SPRING_INTEGRATION_PATTERN**, phục vụ học triển khai Enterprise Integration Patterns bằng Spring Integration nhằm xây dựng message flow ít phụ thuộc, dễ mở rộng. Các ví dụ liên hệ **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, cùng phương pháp kiểm thử và giám sát nhánh xử lý.

**Sau bài học**, bạn có thể phân biệt missing/null/blank/zero; quyết định field nào được default, field nào phải reject hoặc enrich; triển khai mapping Java/Jackson và Java DSL; giữ nguyên identity và semantic correctness qua schema evolution; kiểm thử các nguồn lẫn lỗi chuyển đổi.

## 2. Normalizer giải quyết vấn đề gì?

Không có Normalizer, mỗi nghiệp vụ phải hiểu mọi schema:

~~~text
InventoryHandler:
  if legacy → lấy order_no
  else if partner → lấy orderId
  else if mobile → lấy id

PricingHandler: lặp lại cùng logic...
ShippingHandler: lặp lại cùng logic...
~~~

Kết quả là **schema nguồn lan rộng** khắp module. Một lần đổi field ở đối tác có thể buộc sửa nhiều handlers, tăng rủi ro chuyển đổi không nhất quán.

Với Normalizer:

~~~text
Source A/B/C
  → phân loại format
  → map + validate + chính sách field thiếu
  → CanonicalOrder
  → Inventory/Pricing/Shipping dùng một contract
~~~

**Lợi ích:** giảm coupling, quản lý schema evolution tập trung, cùng chính sách validation/defaulting, dễ test một lần tại biên tích hợp.

**Giới hạn:** Normalizer không tự khôi phục thông tin mà producer **không hề cung cấp**. Nếu thiếu dữ liệu quan trọng và không có nguồn dữ liệu đáng tin để suy ra, output phải thể hiện **unknown** hoặc bị reject; không tự phát minh giá trị chỉ để thỏa constructor.

## 3. Bốn tình trạng dễ bị nhầm khi đọc một field

| Tình trạng | JSON minh họa | Ý nghĩa có thể có |
|---|---|---|
| **Missing / absent** | Không có khóa `email` | Producer chưa hỗ trợ, không biết hoặc không gửi |
| **Explicit null** | `"email": null` | Producer chủ động báo không có, chưa biết hoặc yêu cầu xóa — tùy contract |
| **Blank / empty** | `"email": ""` hoặc `"email": "  "` | Giá trị được gửi nhưng rỗng, thường cần kiểm tra |
| **Concrete value** | `"email": "a@b.example"` | Có giá trị, vẫn phải validate định dạng/nguồn |

Với số và boolean còn có:

~~~json
{"quantity": 0, "enabled": false}
~~~

**Zero và false là giá trị thực**, không phải missing. Logic kiểu `if (!value) useDefault()` trong các ngôn ngữ truthy/falsy hoặc code dùng `0` để biểu diễn null có thể biến `quantity=0` thành `quantity=1`, hoặc `enabled=false` thành `true`.

Đặc biệt trong **update/patch semantics**:

- Field absent có thể nghĩa **không thay đổi**.
- Field null có thể nghĩa **xóa giá trị hiện có**.
- Field blank có thể nghĩa **từ chối**.
- Field có value có thể nghĩa **ghi đè**.

Với **create event**, quy tắc có thể khác. Chỉ đọc JSON shape mà không đọc hợp đồng nguồn **không đủ** để xác định ý nghĩa.

## 4. Bảng quyết định field thiếu: reject, preserve unknown, default hay enrich?

| Tình huống | Lựa chọn | Điều kiện an toàn |
|---|---|---|
| Field bắt buộc cho business invariant | **Reject** | Không có dữ liệu đáng tin để khôi phục |
| Field optional không có | **Preserve missing/unknown** | Downstream contract cho phép |
| Default được công bố rõ ở schema nguồn | **Default có điều kiện** | Scope theo source/version; audit được |
| Giá trị có thể tra cứu từ nguồn authoritative | **Enrich** | Có key tin cậy, timeout/retry rõ |
| Field bị đổi tên ở schema mới | **Map/rename** | Semantics và đơn vị tương đương |
| Explicit null mang nghĩa xóa trong patch | **Giữ null-intent** | Không thay bằng default |
| Field chứa chuỗi rỗng không hợp lệ | **Reject/normalize theo contract** | Không âm thầm biến thành dữ liệu đúng giả |
| Lỗi định dạng số, ngày, tiền | **Reject conversion** | Không parse lỏng gây silent truncation |
| Nguồn không được xác thực | **Reject/quarantine** | Không dựa vào một nhãn source tự khai |

Một thứ tự quyết định hợp lý:

~~~mermaid
flowchart TD
    IN["Field đầu vào"] --> REQUIRED{"Required trong canonical contract?"}
    REQUIRED -->|"Không"| PRES{"Schema nguồn phân biệt missing và null?"}
    PRES -->|"Có"| KEEP["Giữ presence semantics"]
    PRES -->|"Không"| UNKNOWN["Giữ unknown hoặc document limitation"]
    REQUIRED -->|"Có"| EXISTS{"Có giá trị hợp lệ?"}
    EXISTS -->|"Có"| MAP["Map/convert + validate"]
    EXISTS -->|"Không"| GUARANTEE{"Có default được bảo đảm?"}
    GUARANTEE -->|"Có"| DEF["Default theo source/version + provenance"]
    GUARANTEE -->|"Không"| ENRICH{"Có authoritative lookup?"}
    ENRICH -->|"Có"| E["Enrich với deadline/retry"]
    ENRICH -->|"Không"| REJ["Reject/quarantine"]
~~~

Không chọn “default tất cả null thành zero hoặc chuỗi rỗng” vì dễ mất thông tin và tạo số liệu tài chính sai.

## 5. Lập bảng hợp đồng nguồn trước khi viết Transformer

Ví dụ **chính sách giả định của hệ thống mẫu**, cần thay bằng contract thật khi triển khai:

| Canonical field | Legacy v1 | Partner v2 | Mobile v3 | Chính sách |
|---|---|---|---|---|
| `orderId` | `order_no` | `orderId` | `id` | Required; không có thì reject |
| `amount` | `amount_cents` | `totalAmount` | `money.value` | Convert có kiểm tra |
| `currency` | Không có | `currency` | `money.isoCurrency` | Legacy v1 được **contract bảo đảm USD**; còn lại required |
| `email` | Không có | `buyer.email` có thể null | `contactEmail` | Optional; giữ presence |
| `orderedAt` | `created_utc` | Không có | `placedAt` | Optional; không tự gán `now()` |
| `sourceVersion` | v1 do adapter định danh | v2 | v3 | Bắt buộc để trace/migrate |
| `tenantId` | Từ trusted transport | Từ auth/partner mapping | Từ principal | Không dùng raw tenant header để tự cấp quyền |

Một rule **chỉ hợp lệ trong ví dụ**: Legacy v1 gửi tiền dưới đơn vị **USD cents** và không gửi currency, vì producer contract đảm bảo toàn bộ feed v1 dùng USD. Vì vậy có thể chuyển `amount_cents=12500` thành `USD 125.00`.

**Nếu feed legacy trộn tiền VND, USD hoặc đã đổi đơn vị mà không versioning**, fallback USD là **sai dữ liệu**, không phải normalization. Khi đó phải reject, bổ sung schema/version hoặc lookup một nguồn authoritative.

## 6. Canonical contract không nên phản ánh ngẫu nhiên một schema nguồn

Canonical model là **định dạng chung có ngữ nghĩa được mô tả**, không đơn giản là “copy DTO của source mới nhất”.

Một contract khả thi:

~~~text
CanonicalOrder
  tenantId: nonblank, trusted
  orderId: nonblank
  money:
    currency: ISO currency code, required
    amountMajor: decimal, required, nonnegative
  email: field-presence + optional string
  orderedAt: field-presence + timestamp in UTC
  provenance:
    sourceSystem: enum
    sourceSchemaVersion: string
    defaultedFields: limited list
  eventId/correlation: stable identifiers
~~~

Người dùng downstream không cần biết `order_no` khác `orderId` hay `money.isoCurrency`, nhưng phải biết **email vắng mặt khác email bị xóa**, hoặc giá trị mặc định được áp dụng từ quy tắc nguồn nào.

Canonical contract nên có **version** độc lập với các producer schema. Khi canonical version đổi breaking semantics, cần migration/routing và compatibility test; đừng cho mọi source version đi vào cùng một DTO rồi hy vọng field mapping không sai.

## 7. Java 17+: biểu diễn presence có chủ đích

Một model đơn giản:

~~~java
enum FieldPresence {
    ABSENT,
    EXPLICIT_NULL,
    PRESENT
}

record FieldValue<T>(FieldPresence presence, T value) {
    FieldValue {
        Objects.requireNonNull(presence, "presence");
        if (presence == FieldPresence.PRESENT && value == null) {
            throw new IllegalArgumentException(
                "PRESENT requires non-null value");
        }
        if (presence != FieldPresence.PRESENT && value != null) {
            throw new IllegalArgumentException(
                "ABSENT/EXPLICIT_NULL require null value");
        }
    }

    static <T> FieldValue<T> absent() {
        return new FieldValue<>(FieldPresence.ABSENT, null);
    }

    static <T> FieldValue<T> explicitNull() {
        return new FieldValue<>(FieldPresence.EXPLICIT_NULL, null);
    }

    static <T> FieldValue<T> present(T value) {
        return new FieldValue<>(FieldPresence.PRESENT, value);
    }
}
~~~

Đây là **application type** do ta tự tạo, không phải một class Spring Integration cung cấp. Nó cho phép consumer hỏi trực tiếp:

~~~java
FieldValue<String> email = FieldValue.absent();
FieldValue<String> unset = FieldValue.explicitNull();
FieldValue<String> actual =
    FieldValue.present("buyer@example.org");
~~~

`Optional<String>` chỉ phân biệt **có value/không có value**, không tự phân biệt missing với explicit null. Với Create-only schema mà cả hai được quy định cùng nghĩa “không biết”, `Optional` có thể đủ; với Patch semantics cần tri-state hoặc kiểu biểu diễn tương đương.

**Không đưa `FieldValue.present("")` vào canonical model khi contract cấm chuỗi rỗng.** Presence hợp lệ vẫn phải vượt validation giá trị.

## 8. Canonical Java model có provenance

~~~java
enum SourceSystem {
    LEGACY,
    PARTNER,
    MOBILE
}

record SourceInfo(
    SourceSystem system,
    String schemaVersion,
    Set<String> defaultedFields
) {}

record CanonicalMoney(
    Currency currency,
    BigDecimal amountMajor
) {}

record CanonicalOrder(
    String tenantId,
    String orderId,
    String eventId,
    CanonicalMoney money,
    FieldValue<String> email,
    FieldValue<Instant> orderedAt,
    SourceInfo provenance
) {}
~~~

Trong ví dụ:

- `Currency` là `java.util.Currency`; ISO code phải được validate.
- `amountMajor` dùng `BigDecimal`, không dùng `double` cho tiền.
- `email` và `orderedAt` giữ presence.
- `SourceInfo` ghi source/version và field nào được default.
- `tenantId` phải lấy từ boundary đã xác thực.
- `eventId` là logical event ID có contract; không dùng `MessageHeaders.ID` để thay thế xuyên broker.

**Provenance cần vừa đủ**: không đưa toàn bộ raw payload và PII vào canonical object nếu consumer không cần. Khi cần audit/replay raw input, lưu safe reference với retention/quyền độc lập.

## 9. Đầu vào v1: schema không có `currency` và `email`

DTO cho legacy feed:

~~~java
record LegacyOrderV1(
    String order_no,
    Long amount_cents,
    String created_utc,
    String event_id
) {}
~~~

Vì v1 không có currency, **chỉ khi** nguồn v1 được hợp đồng bảo đảm là USD cents mới dùng default:

~~~java
CanonicalOrder normalizeLegacyV1(
        LegacyOrderV1 raw,
        String verifiedTenantId) {
    requireNonBlank(raw.order_no(), "MISSING_ORDER_ID");
    requireNonBlank(raw.event_id(), "MISSING_EVENT_ID");
    if (raw.amount_cents() == null) {
        throw new InvalidInputException("MISSING_AMOUNT");
    }
    if (raw.amount_cents() < 0) {
        throw new InvalidInputException("NEGATIVE_AMOUNT");
    }

    CanonicalMoney money = new CanonicalMoney(
        Currency.getInstance("USD"),
        BigDecimal.valueOf(raw.amount_cents(), 2));

    FieldValue<Instant> orderedAt =
        raw.created_utc() == null
            ? FieldValue.absent()
            : FieldValue.present(
                parseUtcOrReject(raw.created_utc()));

    return new CanonicalOrder(
        verifiedTenantId,
        raw.order_no(),
        raw.event_id(),
        money,
        FieldValue.absent(), // v1 hoàn toàn không có email.
        orderedAt,
        new SourceInfo(
            SourceSystem.LEGACY,
            "1",
            Set.of("money.currency")));
}
~~~

`requireNonBlank`, `parseUtcOrReject` và `InvalidInputException` là **helpers/exception do ứng dụng định nghĩa** ở các mục sau. Logic `Set.of("money.currency")` cho phép audit rằng currency **đã được suy ra từ contract nguồn**, không phải field producer gửi.

Không gán email `""` hoặc `"unknown@domain"`, vì đó là dữ liệu bịa có thể lọt tới shipping/notification service.

## 10. V2: phân biệt thiếu `buyer.email` và explicit null bằng Jackson

Một `record PartnerOrderV2(String email)` không đủ để biết key email **không tồn tại** hay tồn tại với `null`, vì nhiều cấu hình Jackson map cả hai thành Java `null`.

Dùng `JsonNode` tại boundary:

~~~java
FieldValue<String> readBuyerEmail(JsonNode root) {
    JsonNode buyer = root.get("buyer");

    if (buyer == null) {
        return FieldValue.absent();
    }
    if (!buyer.isObject()) {
        throw new InvalidInputException("INVALID_BUYER_OBJECT");
    }

    JsonNode email = buyer.get("email");
    if (email == null) {
        return FieldValue.absent();
    }
    if (email.isNull()) {
        return FieldValue.explicitNull();
    }
    if (!email.isTextual()) {
        throw new InvalidInputException("INVALID_EMAIL_TYPE");
    }

    String text = email.textValue();
    if (text.isBlank()) {
        throw new InvalidInputException("BLANK_EMAIL");
    }
    return FieldValue.present(text);
}
~~~

Jackson phân biệt:

- `get("email")==null`: **không có property**.
- `get("email").isNull()`: có property nhưng **giá trị JSON null**.
- `isTextual()`: value kiểu string.
- `textValue()`: lấy string **sau khi kiểm tra type**.

Đừng dùng `path("email").asText("")` rồi cho rằng cả missing/null/blank tương đương nhau: hàm tiện ích có thể làm mất trạng thái presence. Với nested field, cần validate object cha trước.

## 11. Parse số, currency và timestamp phải nghiêm ngặt

Những nguồn khác nhau có thể diễn đạt tiền bằng minor units hoặc decimal string:

~~~text
Legacy: amount_cents=12500  → USD 125.00
Partner: totalAmount="125.00", currency="USD"
Mobile: money.value="125.00", money.isoCurrency="USD"
~~~

Các phép convert phải tránh:

- `Double.parseDouble` rồi `new BigDecimal(double)` gây sai số.
- Ngầm ép `"12.5"` thành integer `12`.
- Lấy `currency=USD` cho tất cả nguồn chỉ vì một nguồn cũ như vậy.
- Chấp nhận `NaN`/`Infinity` hoặc dấu phân cách locale không có contract.
- Dùng `Instant.now()` thay `createdAt` thiếu, làm giả thời điểm nghiệp vụ.

Ví dụ:

~~~java
BigDecimal parseMoneyOrReject(
        JsonNode node, String fieldName) {
    if (node == null || node.isNull()) {
        throw new InvalidInputException(
            "MISSING_" + fieldName);
    }
    if (!node.isTextual() && !node.isNumber()) {
        throw new InvalidInputException(
            "INVALID_" + fieldName + "_TYPE");
    }
    try {
        BigDecimal value = new BigDecimal(
            node.isTextual() ? node.textValue() : node.asText());
        if (value.signum() < 0) {
            throw new InvalidInputException("NEGATIVE_AMOUNT");
        }
        return value;
    } catch (NumberFormatException ex) {
        throw new InvalidInputException("INVALID_AMOUNT");
    }
}
~~~

Trong production, thêm **currency scale policy** (JPY, USD...), maximum precision/range, rounding rule, loại thao tác (refund có âm hay không), và bảo vệ resource với string số cực dài. Khi cần thời gian, dùng ISO-8601 với offset rõ và chuẩn hóa về `Instant`; một local datetime không có timezone **không đủ** để xác định thời điểm.

## 12. Các helper validation giữ mã lỗi ổn định

~~~java
final class InvalidInputException extends RuntimeException {
    private final String reasonCode;

    InvalidInputException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}

void requireNonBlank(String value, String reasonCode) {
    if (value == null || value.isBlank()) {
        throw new InvalidInputException(reasonCode);
    }
}

Instant parseUtcOrReject(String value) {
    try {
        return Instant.parse(value);
    } catch (DateTimeParseException ex) {
        throw new InvalidInputException("INVALID_TIMESTAMP");
    }
}
~~~

Đây là các helper **trong ví dụ**, có thể chuyển thành một validator/service thực. `InvalidInputException` biểu diễn lỗi **không phù hợp contract**, khác `TransientDataAccessException` hoặc HTTP 503.

**Không đưa message exception raw từ parser vào response công khai.** Trả một `reasonCode` đã được chuẩn hóa, cùng field path và source/version nếu phù hợp; raw payload nên được bảo vệ trong quarantine/reference riêng.

## 13. Mapping v2: các field bắt buộc và optional không dùng chung một policy

V2 có `orderId`, `totalAmount` và `currency` bắt buộc, còn `buyer.email` optional:

~~~java
String requiredText(JsonNode root, String field) {
    JsonNode node = root.get(field);
    if (node == null || node.isNull()) {
        throw new InvalidInputException("MISSING_" + field);
    }
    if (!node.isTextual() || node.textValue().isBlank()) {
        throw new InvalidInputException("INVALID_" + field);
    }
    return node.textValue();
}

CanonicalOrder normalizePartnerV2(
        JsonNode root, String verifiedTenantId) {
    String orderId = requiredText(root, "orderId");
    String eventId = requiredText(root, "eventId");
    String code = requiredText(root, "currency");
    Currency currency;
    try {
        currency = Currency.getInstance(code);
    } catch (IllegalArgumentException ex) {
        throw new InvalidInputException("INVALID_CURRENCY");
    }

    BigDecimal amount =
        parseMoneyOrReject(root.get("totalAmount"), "AMOUNT");
    FieldValue<String> email = readBuyerEmail(root);
    return new CanonicalOrder(
        verifiedTenantId,
        orderId,
        eventId,
        new CanonicalMoney(currency, amount),
        email,
        FieldValue.absent(), // v2 không công bố orderedAt.
        new SourceInfo(
            SourceSystem.PARTNER, "2", Set.of()));
}
~~~

Hàm `requiredText()` trong ví dụ từ chối cả missing, explicit null và blank cho **field bắt buộc**. Ngược lại `readBuyerEmail()` ở mục 10 **giữ** sự khác biệt absent/null/present theo hợp đồng email.

**Không bắt buộc mọi field phải có cùng chính sách.** Một schema có thể quy định `orderId` required, `currency` required, `email` nullable, `orderedAt` optional. “Đã chọn canonical schema” không có nghĩa mọi source phải luôn điền một giá trị cho mọi field.

## 14. Mapping v3: đổi tên field không đồng nghĩa đổi semantics

V3 đổi:

~~~text
id                    → orderId
money.value           → money.amountMajor
money.isoCurrency     → money.currency
contactEmail          → email
placedAt              → orderedAt
~~~

Trước khi map, phải xác nhận:

1. `money.value` có **cùng đơn vị và cách làm tròn** với `totalAmount` v2 không?
2. `placedAt` là thời điểm order được tạo, được thanh toán hay được gửi?
3. `contactEmail=null` có mang nghĩa unknown hay yêu cầu xóa email?
4. `id` có uniqueness trong tenant, region, source hay toàn hệ thống?
5. `schemaVersion="3"` đến từ contract đáng tin hay một field client có thể giả?

Một Java helper lấy nested object an toàn:

~~~java
JsonNode requiredObject(JsonNode parent, String field) {
    JsonNode child = parent.get(field);
    if (child == null || !child.isObject()) {
        throw new InvalidInputException("INVALID_" + field);
    }
    return child;
}

CanonicalMoney readMobileMoney(JsonNode root) {
    JsonNode money = requiredObject(root, "money");
    String isoCode = requiredText(money, "isoCurrency");
    Currency currency;
    try {
        currency = Currency.getInstance(isoCode);
    } catch (IllegalArgumentException ex) {
        throw new InvalidInputException("INVALID_CURRENCY");
    }
    BigDecimal value =
        parseMoneyOrReject(money.get("value"), "AMOUNT");
    return new CanonicalMoney(currency, value);
}
~~~

**Không dùng một field cùng tên làm bằng chứng cùng meaning.** Nếu v3 chuyển `amount` từ tiền hàng sang tiền đã gồm phí vận chuyển, mapping phải đổi business contract hoặc tính bổ sung, không âm thầm đặt vào canonical `totalAmount`.

## 15. Normalization phải deterministic khi chỉ dùng dữ liệu đã biết

Với một input và một phiên bản mapping policy xác định, Normalizer nên tạo cùng canonical result:

\[
\operatorname{normalize}(source, version, payload, policy)
= canonical\ result
\]

Vì vậy nên tách:

- **Pure mapping:** đổi tên field, convert đơn vị, validate shape, quyết định absent/null, áp default **đã được contract bảo đảm**.
- **I/O enrichment:** gọi service khác để bổ sung thông tin.
- **Business handler:** cập nhật tồn kho, tính giá, tạo giao dịch.

Không tạo default kiểu `orderedAt=Instant.now()` trong pure mapping: hai lần replay có thể cho hai kết quả khác nhau. Nếu hệ thống thật sự cần `ingestedAt`, đó là **metadata thời điểm nhận** khác `orderedAt`; nên dùng field riêng và không ghi đè semantic timestamp.

Với normalizer chạy lại trong DLQ replay, cần giữ **mappingPolicyVersion** để có thể biết input từng được xử lý bằng quy tắc nào. Nếu quy tắc default/rounding được sửa, kết quả chuẩn hóa có thể thay đổi dù raw payload giống nhau; đây là một thay đổi có tác động nghiệp vụ, cần kiểm soát.

## 16. Một envelope chung để Router chọn Transformer đúng nguồn

Nếu raw bytes đã được adapter parse thành `JsonNode`, có thể chuẩn hóa metadata ở ingress:

~~~java
record NormalizationEnvelope(
    SourceSystem source,
    String schemaVersion,
    String verifiedTenantId,
    JsonNode payload
) {}
~~~

**verifiedTenantId** phải được xác lập bởi authentication/adapter đã tin cậy, không nhận nguyên một field `tenantId` tự khai rồi mặc nhiên tin. `source` và `schemaVersion` cũng cần được xác minh dựa trên transport contract, topic/route hoặc schema registry. Header `sourceSystem` do client tự gửi có thể là dữ liệu untrusted.

Một router Java DSL:

~~~java
@Configuration
@EnableIntegration
class NormalizationRouter {

    @Bean
    IntegrationFlow dispatchSchema() {
        return IntegrationFlow.from("normalizer.input")
            .route(
                NormalizationEnvelope.class,
                envelope -> envelope.source().name(),
                mapping -> mapping
                    .channelMapping("LEGACY", "normalizer.legacy")
                    .channelMapping("PARTNER", "normalizer.partner")
                    .channelMapping("MOBILE", "normalizer.mobile")
                    .defaultOutputChannel("normalizer.unsupported"))
            .get();
    }
}
~~~

Ví dụ minh họa Java DSL; các import, bean/channel và tên overload cần đối chiếu với version Spring Integration đang dùng. Trách nhiệm của Router là **chọn đường chuyển đổi**, không tự bù field thiếu. Đường `normalizer.unsupported` phải có consumer đưa ra error/quarantine hợp lệ, không để message lỗi mất im lặng.

**Source routing và schema version routing là hai bước khác nhau**. Một source có thể gửi v1 và v2 đồng thời; hãy validate/route theo **cặp (source,version)**, hoặc để mỗi adapter source chuyển sang mapper version-aware riêng. Tránh ánh xạ v9 vào handler v2 chỉ vì cùng provider.

## 17. Một Transformer cho mỗi định dạng, cùng output type

Các Transformer nhận `NormalizationEnvelope`, validate version rồi trả `CanonicalOrder`:

~~~java
@Configuration
@EnableIntegration
class NormalizationTransformers {

    @Bean
    IntegrationFlow legacyFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.legacy")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromLegacy)
            .channel("normalizer.canonical")
            .get();
    }

    @Bean
    IntegrationFlow partnerFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.partner")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromPartner)
            .channel("normalizer.canonical")
            .get();
    }

    @Bean
    IntegrationFlow mobileFlow(OrderNormalizers normalizers) {
        return IntegrationFlow.from("normalizer.mobile")
            .transform(
                NormalizationEnvelope.class,
                normalizers::fromMobile)
            .channel("normalizer.canonical")
            .get();
    }
}
~~~

`OrderNormalizers` là service **do ứng dụng viết**, trong đó `fromLegacy()` đọc v1 và gọi `normalizeLegacyV1()`, `fromPartner()` dùng `normalizePartnerV2()`, và `fromMobile()` dùng helpers v3. Mỗi method phải:

1. Kiểm tra `source` và `schemaVersion` của envelope.
2. Validate required fields **trước** phép convert dễ thất bại.
3. Chuẩn hóa field thiếu theo contract từng version.
4. Gắn source provenance và defaultApplied flags.
5. Tạo `CanonicalOrder` hoàn chỉnh hoặc **ném lỗi phân loại được**, không trả object nửa vời.

Nếu ba flow đều gửi vào cùng `normalizer.canonical`, cấu hình **một consumer business downstream** (hoặc fan-out có chủ đích). Không đăng ký nhiều subscriber vào một DirectChannel rồi kỳ vọng mọi subscriber đều thấy message; DirectChannel với nhiều subscribers có dispatch semantics riêng.

## 18. Canonical validation sau Transformer là một hàng rào nữa

Source-specific validation bảo vệ input contract. Sau khi tất cả mapping cùng tạo `CanonicalOrder`, cần kiểm tra **bất biến canonical**:

~~~java
@Service
class CanonicalOrderValidator {
    boolean isValid(CanonicalOrder order) {
        return order != null
            && order.tenantId() != null
            && !order.tenantId().isBlank()
            && order.orderId() != null
            && !order.orderId().isBlank()
            && order.eventId() != null
            && !order.eventId().isBlank()
            && order.money() != null
            && order.money().currency() != null
            && order.money().amountMajor() != null
            && order.money().amountMajor().signum() >= 0
            && order.email() != null
            && order.orderedAt() != null
            && order.provenance() != null;
    }
}
~~~

Ví dụ này kiểm tra các field cơ bản; production thêm max precision/range, tenant authorization, format/orderId uniqueness, email validation, ngày hợp lệ, schema version và domain-specific policy.

Một integration flow canonical:

~~~java
@Bean
IntegrationFlow canonicalValidation(
        CanonicalOrderValidator validator) {
    return IntegrationFlow.from("normalizer.canonical")
        .filter(
            CanonicalOrder.class,
            validator::isValid,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("orders.business")
        .get();
}
~~~

**Không đồng nhất hai loại lỗi:** malformed source input nên báo mã như `MISSING_ORDER_ID`; một bug trong mapper tạo `CanonicalOrder` invalid dù source hợp lệ là **normalization defect** cần alert, không nên quay lại đổ lỗi cho producer.

## 19. Filter chỉ quyết định accept/reject, không tự sinh field bị thiếu

~~~text
Raw parsed source
  → Filter(check required source fields)
  → Transformer(normalize)
  → Filter(check canonical invariants)
  → Business handler
~~~

Một Filter trả `false` có thể drop, đưa message tới `discardChannel` hoặc ném exception tùy cấu hình. Việc ***normalization*** xảy ra ở Transformer hoặc service mapping, không phải do Filter tự bù field.

Đặt Filter **trước Transformer** cho các điều kiện rẻ, thuần dữ liệu và nguy hiểm khi thiếu (JSON shape, mandatory IDs, số phần tử, schema version). Sau Transformer kiểm tra canonical invariants.

Nếu Transformer ném `InvalidInputException` trước khi Filter thứ hai được gọi, đó là **mapping rejection path**, không phải một Filter discard event. Cần xử lý loại lỗi này ở Gateway/broker error boundary tương ứng.

## 20. Content Enricher khi field bắt buộc không có trong source

Giả sử nghiệp vụ vận chuyển yêu cầu `deliveryAddress`, nhưng feed legacy chỉ có `customerId`. Có thể:

~~~mermaid
flowchart LR
    LEG["Legacy order, no address"] --> MAP["Normalize known fields"]
    MAP --> LOOK{"Content Enricher: customer lookup"}
    LOOK -->|"Found + authorized"| ADD["Canonical order + address"]
    LOOK -->|"Definitive not found"| REJ["Permanent rejection / business outcome"]
    LOOK -->|"Timeout/503"| RET["Retryable failure"]
    ADD --> SHIP["Shipping handler"]
~~~

**Enrich** chỉ hợp lệ nếu có **nguồn authoritative** và một key được xác thực. Không có địa chỉ không có nghĩa nên đặt `address="N/A"` rồi để Shipping chạy.

Spring Integration **Content Enricher** có thể phối hợp request/reply để bổ sung thông tin, nhưng:

- Phải giữ correlation của original qua lookup và reply.
- Có timeout/retry budget cho lookup.
- Phân biệt **“không tìm được địa chỉ”** với **“dịch vụ lookup không khả dụng”**.
- Không gắn value từ customer khác chỉ vì cùng tên hoặc request đến gần nhau.
- Cân nhắc cache TTL, stale data và authorization trước khi dùng kết quả.

**Đừng biến lỗi HTTP 503 thành một `FieldValue.absent()` rồi cho business chạy** nếu địa chỉ là required. Đó là lỗi hạ tầng chưa phục hồi, không phải thông tin nguồn cố tình bỏ trống.

## 21. Giữ correlation, trace và identity khi schema thay đổi

Một message có thể mang:

~~~text
sourceSystem=PARTNER
sourceSchemaVersion=2
eventId=EV-501
tenantId=tenant-a
businessCorrelationId=tenant-a|O-501|revision-2
springMessageId=<framework message ID>
traceId=<distributed tracing ID>
~~~

Những ID này **không thay thế nhau**:

- `springMessageId` nhận diện một Spring message object, có thể đổi khi Transformer tạo reply.
- `eventId` nhận diện sự kiện theo contract producer.
- `businessCorrelationId` nhóm những kết quả cùng logical work.
- `traceId` phục vụ observability, không mặc nhiên là business group ID.
- `sequenceNumber/sequenceSize` phục vụ Splitter/Resequencer, không phải source schema version.

Normalizer cần **giữ các business identifiers cần thiết** trong canonical payload/header. Không dùng `order_no` từ source A nhưng `MessageHeaders.ID` từ source B làm cùng một trường `orderId`; đây là lỗi semantics, không phải chỉ khác kiểu dữ liệu.

Khi tạo message mới bằng `MessageBuilder`, xác định rõ headers nào cần chuyển và headers nào không an toàn qua trust boundary (ví dụ replyChannel, authentication, raw internal routing). Với broker, test header mapper và nên có business identifiers cần thiết trong **wire contract**.

## 22. Normalizer đặt trước Splitter và Aggregator

Một nguyên tắc hữu ích: **normalize đơn hàng trước khi split thành các line tasks** nếu field còn thiếu có thể ảnh hưởng toàn batch.

~~~text
Legacy v1 / Partner v2 / Mobile v3
  → Normalizer → CanonicalOrder
  → Validate common invariants
  → Splitter: CanonicalLineWork #1..#N
  → Worker branches
  → Aggregator: CanonicalOrderResult
~~~

Nếu một source không có `currency` và normalize sai thành default khác, **tất cả child Pricing** có thể tính sai, dù Aggregator vẫn nhận đủ N results. Vì vậy chính sách field thiếu cần được quyết định **trước** fan-out.

**Correlation:** Splitter thường gắn `correlationId/sequenceNumber/sequenceSize` theo group con. Normalizer không nên vô cớ ghi đè các headers này hoặc gộp result của hai source có order ID trùng nhưng khác tenant/operation/revision.

Nếu một line có data malformed sau Splitter:

- **Reject whole batch** khi business không cho partial.
- Hoặc tạo **failure outcome có cùng member ID/group key** cho line đó, để Aggregator kết luận PARTIAL/FAILED có chủ đích.

Không tự giảm expected group size khi một member bị Filter drop; làm vậy che lỗi nguồn và có thể tạo success giả.

## 23. Gateway có thể trả canonical output hoặc rejection

Một Gateway:

~~~java
@MessagingGateway(defaultRequestChannel = "normalizer.input")
interface OrderNormalizationGateway {
    CanonicalOrder normalize(NormalizationEnvelope input);
}
~~~

Điều kiện để Gateway trả đúng:

1. Tất cả source flows cuối cùng phải tạo **một canonical reply** phù hợp.
2. Header `replyChannel` cần được giữ qua endpoints hoặc reply routing được cấu hình rõ.
3. Invalid source phải tạo **typed error response** hoặc exception được map, không bị drop âm thầm.
4. Async broker call hoặc Content Enricher có thể timeout; không gán hết timeout thành `INVALID_SCHEMA`.
5. Cần phân biệt `schemaVersion` của source với `canonicalVersion` của kết quả.

Nếu Filter nhận invalid message rồi **discard không reply**, Gateway có thể chỉ báo timeout thay vì thông báo `MISSING_ORDER_ID`. Với request–reply, thường nên dùng **fail-fast validation exception có reasonCode** hoặc một kết quả có kiểu `NormalizationRejected` nằm trong return contract.

**Normalizing một object không nhất thiết cần Gateway** nếu receiver đã nằm trong IntegrationFlow. Gateway chỉ có ích khi boundary muốn request–reply hoặc API typed.

## 24. Error channel: malformed input khác lỗi dependency

| Tình huống | Lớp lỗi | Kết quả mong muốn |
|---|---|---|
| JSON parse lỗi | Decode/adapter boundary | Reject/quarantine; không retry vô hạn |
| Source version không hỗ trợ | Contract | `UNSUPPORTED_SCHEMA_VERSION` |
| Thiếu `orderId` bắt buộc | Contract | `MISSING_ORDER_ID` |
| Số tiền không parse được | Mapping/contract | `INVALID_AMOUNT` |
| Không có currency và không có fallback hợp lệ | Contract | `MISSING_CURRENCY` |
| Content Enricher HTTP 503 | Transient dependency | Bounded retry/backoff |
| Lookup customer trả 404 chính xác | Business/contract tùy case | Reject hoặc terminal outcome |
| Mapper ném NPE do bug | Application defect | Alert + error path; không đổ lỗi nguồn |
| Broker/MessageGroupStore lỗi | Infrastructure | Retry/recovery theo transaction semantics |

Một `InvalidInputException` có thể được map sang HTTP 400/422 hoặc DLQ/quarantine vĩnh viễn; exception infrastructure có thể được retry. Với `DirectChannel` đồng bộ, lỗi có thể lan về caller; với `ExecutorChannel`/poller/broker, lỗi xảy ra ở một **async error boundary** khác.

**Không mặc định mọi exception sẽ vào `errorChannel`**: một lỗi xảy ra trong deserializer trước khi Spring Integration tạo Message có thể chỉ được adapter/container error handler xử lý. Và `discardChannel` của Filter không tự là DLQ của broker.

## 25. Retry và idempotency của quá trình normalize

Một message bị redeliver sau khi normalize thành công:

~~~text
Raw eventId=EV-501, schemaVersion=1
  → normalize → CanonicalOrder
  → downstream commit
  → crash trước broker ACK
  → redelivery EV-501
~~~

Nếu Normalizer deterministic và không có side effects, việc normalize lại cùng dữ liệu thường an toàn. **Nhưng business handler phía sau** vẫn cần idempotency để không double charge/double publish.

Những điều cần giữ qua retry:

- `eventId`/logical work ID ổn định; không sinh UUID mới mỗi lần normalize.
- `source/version/mappingPolicyVersion` xác định.
- Defaulting policy nhất quán; không tùy ý áp default mới cho replay cũ.
- Canonical output có business group/member identity phục vụ Splitter/Aggregator.
- Fingerprint/canonicalization rõ khi cùng key nhưng input khác.

Nếu mapping dựa trên external lookup và lookup data thay đổi giữa attempts, Normalizer không còn hoàn toàn deterministic. Có thể cần **snapshot/lookup version**, lưu normalized output hoặc idempotent workflow state, tùy nghiệp vụ.

**Không retry mãi một malformed input**: cùng raw bytes sai schema không tự sửa được. Nếu producer sửa schema, đó là một **reprocess/migration workflow có kiểm soát**, không phải retry nóng đơn thuần.

## 26. Schema evolution và điều kiện tương thích

Một field mới hoặc optional field trong producer có vẻ là backward-compatible, nhưng vẫn cần kiểm tra consumer:

| Thay đổi | Có thể tương thích? | Cần xem xét |
|---|---|---|
| Thêm optional `email` | Thường có | Unknown fields có bị reject không? |
| Thêm field required không có default | Thường breaking với input cũ | Có cần version mới/migration? |
| Đổi `order_no` thành `orderId` | Breaking nếu parser cũ yêu cầu tên cũ | Mapper theo source version |
| Đổi `amount_cents` sang decimal major units | Breaking semantics | Convert scale/currency chính xác |
| Cho phép `null` ở field trước đây non-null | Có thể breaking | Downstream có nhận unknown không? |
| Thay zero thành “missing” | Breaking semantics | Không merge falsey values |
| Đổi meaning của `createdAt` | Breaking dù type giữ nguyên | Contract và data lineage |
| Đổi `orderId` scope từ global sang per-tenant | Breaking correlation/key | Idempotency/correlation migration |

Khi dùng Avro/Protobuf/JSON Schema, schema registry và compatibility mode giúp phát hiện **một số thay đổi cấu trúc**, nhưng **không tự kiểm chứng meaning**, ví dụ tiền là gross hay net, currency scale hoặc timezone.

Trong giai đoạn chuyển tiếp, có thể chạy **v1 và v2 Transform** song song cho những messages được định tuyến theo version. Đừng cố làm một function với hàng chục `if (fieldExists)` mà không có policy, vì dễ đổi hành vi khi input tình cờ có cả tên cũ lẫn tên mới.

## 27. Contract-first: thống nhất ý nghĩa field trước khi deploy

Mỗi source schema nên có một bảng field contract được version hóa. Ví dụ:

| Field | Type wire | Presence rule | Null rule | Canonical mapping | Owner |
|---|---|---|---|---|---|
| v1 `order_no` | string | Required | Reject | `orderId` | Legacy team |
| v1 `amount_cents` | integer | Required | Reject | USD cents → decimal | Legacy team |
| v1 `email` | Không có | Absence expected | N/A | `ABSENT` | Legacy team |
| v2 `buyer.email` | string/null | Optional | `EXPLICIT_NULL` | `email` | Partner team |
| v2 `currency` | ISO string | Required | Reject | Currency | Partner team |
| v3 `placedAt` | ISO timestamp | Optional/required theo contract | Reject hoặc unknown | `orderedAt` | Mobile team |

**Đừng viết mapping policy từ suy đoán của consumer.** Source owner phải xác nhận:

- Field absent có ý nghĩa gì?
- Có cho explicit null không?
- Giá trị mặc định được bảo đảm **ở phiên bản nào**, đến thời điểm nào?
- Đơn vị tiền, độ chính xác, timezone, case sensitivity là gì?
- Một ID có uniqueness trong phạm vi nào?
- Producer thay đổi trường bằng migration hay event version?
- Ai chịu trách nhiệm khi unknown/null đi tới downstream?

Một thay đổi contract không có nghĩa cứ sửa Transformer là xong. Cần **contract tests, release sequencing và observability** để phát hiện traffic từ producer phiên bản không mong đợi.

## 28. Chính sách mặc định theo nguồn phải có phạm vi và nguồn gốc

Một tập chính sách ví dụ:

~~~text
Policy legacy-v1:
  if currency ABSENT:
     currency = USD
     reason = LEGACY_V1_USD_CENTS_CONTRACT
  if email ABSENT:
     preserve ABSENT

Policy partner-v2:
  if currency ABSENT:
     REJECT MISSING_CURRENCY
  if buyer.email ABSENT:
     preserve ABSENT
  if buyer.email EXPLICIT_NULL:
     preserve EXPLICIT_NULL

Policy mobile-v3:
  if money.isoCurrency ABSENT:
     REJECT MISSING_CURRENCY
  if placedAt ABSENT:
     preserve ABSENT only if optional
~~~

Không nên dùng rule global:

~~~java
String currency = payload.get("currency") == null
    ? "USD"
    : payload.get("currency").asText();
~~~

Rule đó sẽ gán USD cho mọi payload không có field `currency`, kể cả v3 có currency ở nested `money.isoCurrency`, hoặc đối tác thực sự gửi một loại tiền khác.

**Ghi provenance:** lưu field nào đã default, rule/policy version và source/version. Không nhất thiết xuất provenance ra mọi public API, nhưng internal pipeline và audit cần cách truy lại nguồn của giá trị.

## 29. Khi missing xuất hiện trong patch/update event

Tập trung vào một ví dụ `UpdateCustomerContact`:

~~~json
{
  "customerId": "C-501",
  "email": null
}
~~~

Nếu contract patch quy định:

- Không có key `email` → giữ email cũ.
- `email=null` → xóa email cũ.
- `email="new@example.org"` → cập nhật email.
- `email=""` → invalid.

Thì transform sang `Optional<String>` làm mất phân biệt absent và null, có thể gây **xóa dữ liệu ngoài ý định** hoặc không thực hiện xóa khi caller yêu cầu.

Một canonical change instruction có thể là:

~~~java
record EmailPatch(
    FieldValue<String> email
) {}

void applyEmailPatch(EmailPatch change) {
    switch (change.email().presence()) {
        case ABSENT -> {
            // Giữ nguyên.
        }
        case EXPLICIT_NULL -> {
            // Xóa email theo contract và authorization.
        }
        case PRESENT -> {
            // Validate rồi ghi giá trị email mới.
        }
    }
}
~~~

Đây là ví dụ về **ý nghĩa field thiếu**, không phải một REST PATCH framework hoàn chỉnh. Trước khi áp dụng xóa/update phải có authorization, optimistic locking và idempotency/operation version.

**Không áp dụng chính sách patch này mặc định cho create event** nếu schema nguồn quy định explicit null cũng là “không biết”. Semantics do **contract của message type** quyết định.

## 30. Unknown và nullable phải được downstream hiểu thống nhất

Một canonical field có thể optional nhưng consumer phải quyết định làm gì:

| Consumer | `email ABSENT` | `email EXPLICIT_NULL` | `email PRESENT` |
|---|---|---|---|
| Email notification | Không gửi; ghi thiếu dữ liệu | Không gửi; tôn trọng trạng thái xóa/null | Validate và gửi nếu được phép |
| Customer CRM sync | Không thay đổi nếu patch semantics | Xóa nếu contract cho phép | Update |
| Analytics | Đếm nhóm “missing” | Đếm nhóm “explicit null” | Dùng giá trị được phép |
| Shipping | Không cần nếu shipment không dùng email | Không cần nếu không bắt buộc | Có thể dùng cho thông báo |

**Không tự biến missing thành một địa chỉ email giả** rồi để service gửi nhầm. Nếu downstream không thể xử lý `FieldValue`, adapter riêng có thể chuyển về contract của consumer nhưng phải có quy tắc rõ cho unknown/null.

Canonical model **không bắt buộc** dùng tri-state cho mọi field. Chỉ dùng khi nghiệp vụ thực sự cần phân biệt; nếu không thì schema nên đơn giản và quy định rõ missing/null hợp nhất như thế nào.

## 31. Test: legacy v1 thiếu currency nhưng default có chứng cứ

JUnit 5 cho mapper:

~~~java
@Test
void legacyV1UsesContractualCurrencyDefault() {
    LegacyOrderV1 source = new LegacyOrderV1(
        "O-501", 12500L,
        "2026-01-10T07:15:00Z",
        "EV-501");

    CanonicalOrder result =
        normalizeLegacyV1(source, "tenant-a");

    assertEquals("O-501", result.orderId());
    assertEquals(
        Currency.getInstance("USD"),
        result.money().currency());
    assertEquals(
        0,
        result.money().amountMajor()
            .compareTo(new BigDecimal("125.00")));
    assertEquals(
        FieldPresence.ABSENT,
        result.email().presence());
    assertTrue(result.provenance().defaultedFields()
        .contains("money.currency"));
    assertEquals(
        Instant.parse("2026-01-10T07:15:00Z"),
        result.orderedAt().value());
}
~~~

Test khẳng định **default USD chỉ xuất hiện với legacy v1 theo contract ví dụ**. Cần một test đối nghịch cho v2/v3 thiếu currency: **phải reject**, không lén chạy chung global fallback.

Các method snippet ở các mục trước được hiểu là nằm trong class/service/test fixture tương ứng; import và wiring được lược bỏ để tập trung vào Normalizer.

## 32. Test: missing, explicit null, blank và present

Jackson `ObjectMapper` cho raw JSON:

~~~java
@Test
void distinguishesEmailPresenceStates() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    JsonNode missing = mapper.readTree(
        "{\"buyer\":{}}");
    JsonNode explicitNull = mapper.readTree(
        "{\"buyer\":{\"email\":null}}");
    JsonNode present = mapper.readTree(
        "{\"buyer\":{\"email\":\"buyer@example.org\"}}");
    JsonNode blank = mapper.readTree(
        "{\"buyer\":{\"email\":\"   \"}}");

    assertEquals(FieldPresence.ABSENT,
        readBuyerEmail(missing).presence());
    assertEquals(FieldPresence.EXPLICIT_NULL,
        readBuyerEmail(explicitNull).presence());
    assertEquals(FieldPresence.PRESENT,
        readBuyerEmail(present).presence());
    assertEquals(
        "buyer@example.org",
        readBuyerEmail(present).value());
    assertThrows(InvalidInputException.class,
        () -> readBuyerEmail(blank));
}
~~~

Đây là test **sự khác biệt về presence**; test `@Valid` trên Java DTO sau deserialize không thay thế được vì nếu đã map missing/null cùng thành Java `null`, mất thông tin ban đầu.

Thêm test cho `buyer=null`, `buyer=[]`, `buyer.email=123` và nested field quá dài. Với một API patch, test riêng “missing giữ nguyên” và “explicit null xóa” để ngăn silent data loss.

## 33. Test: missing amount không được mặc định thành zero

Sau khi chuyển legacy DTO `amount_cents` sang `Long` nullable, test:

~~~java
@Test
void legacyMissingAmountIsNotAssumedZero() {
    LegacyOrderV1 source = new LegacyOrderV1(
        "O-501", null, null, "EV-501");

    InvalidInputException error =
        assertThrows(
            InvalidInputException.class,
            () -> normalizeLegacyV1(source, "tenant-a"));

    assertEquals("MISSING_AMOUNT", error.reasonCode());
}
~~~

**Vì sao dùng `Long` thay vì `long`?** Khi JSON bỏ field, một số cấu hình deserializer có thể đặt primitive `long` thành `0`, khiến không phân biệt **amount thiếu** với **amount thực sự bằng zero**. Nếu API cần phân biệt, dùng boxed type hoặc `JsonNode`/schema validation trước khi dựng DTO.

**Zero có thể hợp lệ** cho một đơn hàng giảm giá 100%, tùy contract. Không tùy tiện reject amount 0 chỉ để tránh missing; validator phải dựa trên nghiệp vụ.

## 34. Test: currency thiếu ở v2 phải reject, không mượn default v1

~~~java
@Test
void partnerV2MissingCurrencyIsRejected() throws Exception {
    JsonNode source = new ObjectMapper().readTree(
        "{"
        + "\"orderId\":\"O-502\","
        + "\"eventId\":\"EV-502\","
        + "\"totalAmount\":\"125.00\""
        + "}");

    InvalidInputException error =
        assertThrows(
            InvalidInputException.class,
            () -> normalizePartnerV2(source, "tenant-a"));

    assertEquals(
        "MISSING_currency",
        error.reasonCode());
}
~~~

Trong ví dụ helper ở mục 13, `requiredText(root,"currency")` đang ghép mã lỗi dựa theo tên field, nên chuỗi là `MISSING_currency`. Với production nên chuẩn hóa mã thành **uppercase enum/catalog**, ví dụ `MISSING_CURRENCY`, thay vì để case của tên JSON quyết định error code.

Quan trọng hơn việc viết hoa: **partner v2 không được hưởng default USD của legacy v1**. Một test kết quả `currency=USD` khi v2 thiếu field sẽ là **bug**, dù dữ liệu cuối nhìn có vẻ hợp lệ.

## 35. Integration test Router → Transformer → canonical validation

Thiết lập test Spring context có dispatcher và ba transformers ở mục 16–18. Đưa message vào:

~~~java
Message<NormalizationEnvelope> request =
    MessageBuilder.withPayload(
        new NormalizationEnvelope(
            SourceSystem.LEGACY,
            "1",
            "tenant-a",
            legacyJsonNode))
    .setHeader("businessCorrelationId",
        "tenant-a|O-501|revision-1")
    .build();
~~~

Một test có thể dùng `QueueChannel` đặt tại `orders.business` để assert:

~~~java
@Test
void legacyMessageBecomesCanonicalWithoutLosingIdentity() {
    MessageChannel input =
        context.getBean("normalizer.input", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.business", PollableChannel.class);

    assertTrue(input.send(request));
    Message<?> received = output.receive(1_000);
    assertNotNull(received);
    assertInstanceOf(
        CanonicalOrder.class,
        received.getPayload());

    CanonicalOrder canonical =
        (CanonicalOrder) received.getPayload();
    assertEquals("O-501", canonical.orderId());
    assertEquals("EV-501", canonical.eventId());
    assertEquals(
        SourceSystem.LEGACY,
        canonical.provenance().system());
}
~~~

`context`, `legacyJsonNode` và `request` là **test fixtures**, không phải Spring Integration global variables. Chạy test với **consumer production đã tắt** để tránh competing subscriber lấy mất output. Để kiểm tra header propagation, thêm assertion về `businessCorrelationId` và `replyChannel` tại đúng điểm chúng được yêu cầu; không giả định mọi header sống qua mọi external adapter.

Test riêng mỗi source/version và kiểm tra **cùng canonical semantic** khi input tương đương. Không chỉ assert instance type; phải assert money, email presence, timestamp và provenance.

## 36. Ma trận kiểm thử schema và failure paths

| Test case | Input | Kỳ vọng |
|---|---|---|
| v1 đúng contract | Không có currency/email | USD default có provenance, email ABSENT |
| v2 đúng contract | Currency + email null | Không default currency; email EXPLICIT_NULL |
| v3 đúng contract | Nested money + contactEmail | Map đúng names/units |
| v1 thiếu amount | `amount_cents` absent | `MISSING_AMOUNT` |
| v2 thiếu currency | `currency` absent | Permanent reject |
| v3 thiếu `money` | Nested object absent | `INVALID_money` hoặc catalog equivalent |
| Missing order ID | `orderId` rỗng/null | Reject trước business |
| Wrong amount type | Array/object | Reject `INVALID_AMOUNT_TYPE` |
| Zero amount | `0` | Xử lý theo contract, không coi missing |
| Email absent | Không có email key | ABSENT |
| Email explicit null | `"email":null` | EXPLICIT_NULL |
| Email blank | `"email":"  "` | `BLANK_EMAIL` |
| Timestamp invalid | Offset không hợp lệ | `INVALID_TIMESTAMP` |
| Unsupported version | Producer gửi v9 | Reject/quarantine |
| Source mismatch | Header LEGACY, transport PARTNER | Reject/trust boundary validation |
| Tenant mismatch | Payload tenant-b, principal tenant-a | Security reject |
| Lookup 503 | Required field cần enrich | Retryable, không `UNKNOWN` giả |
| Duplicate raw event | Redelivery cùng eventId | No duplicate business side effect |
| Two groups | Cùng orderId, tenant/revision khác | Correlation tách biệt |
| Splitter child failure | Một line invalid sau split | Failure outcome hoặc whole batch reject |
| Mapper bug | Null pointer từ mapping code | Application defect alert, không đổ lỗi source |
| Broker retry | Spring Message ID thay đổi | Business identity vẫn ổn định |
| DLQ replay | Schema đã được hỗ trợ sau migration | Reprocess có policy/version/audit |

**Lưu ý:** exception mã lỗi trong ví dụ có thể còn phụ thuộc field name/case; production nên dùng một `enum ReasonCode` hoặc catalog độc lập với ngôn ngữ/naming của payload để tránh biến `MISSING_currency` thành API contract lâu dài.

## 37. Property-based và metamorphic tests giúp bắt lỗi normalization

Ngoài từng ví dụ cố định, có thể kiểm tra các bất biến:

1. **Same source+version+payload+policy → same canonical result.**
2. **Không có giá trị bịa**: email absent ở v1 không bao giờ trở thành chuỗi giả.
3. **Không mất số 0**: amount 0, boolean false phải giữ đúng theo contract.
4. **Không trộn tenant**: hai payload có cùng orderId nhưng tenant khác phải khác identity.
5. **Money conversion exact**: 12500 USD cents phải bằng `BigDecimal("125.00")`.
6. **Reject invalid types**: array/object ở field scalar không được cast âm thầm.
7. **Version routing**: v2 không dùng v1 default.
8. **Field presence**: absent/null/present luôn giữ semantics.
9. **Mapping provenance**: chỉ ghi field thực sự được default.
10. **Không side effect trước validation**: malformed input không chạy handler.

Property-based testing (ví dụ jqwik) có thể sinh nhiều chuỗi trống, Unicode, số cực lớn, decimal scale và nested objects để tìm silent truncation hoặc exception không được phân loại.

**Không cần cài cả property-based framework để bắt đầu**; một bảng test data-driven JUnit cho các schema versions và presence states đã có giá trị lớn.

## 38. Serialization của canonical field presence

Một kiểu Java `FieldValue<String>` **không tự bảo đảm** wire format thể hiện absent/null/present theo ý nghĩa mong đợi. Nếu hệ thống publish canonical message qua Kafka hoặc HTTP, phải có schema rõ cho tri-state.

Một biểu diễn JSON tường minh:

~~~json
{
  "canonicalVersion": "1",
  "orderId": "O-502",
  "email": {
    "presence": "EXPLICIT_NULL",
    "value": null
  }
}
~~~

Với value có thật:

~~~json
{
  "email": {
    "presence": "PRESENT",
    "value": "buyer@example.org"
  }
}
~~~

Nếu `presence=ABSENT`, contract có thể chọn:

- Có field wrapper `{"presence":"ABSENT","value":null}` để **giữ tri-state tường minh**; hoặc
- Bỏ hẳn property `email` khi serialize và dùng parser có thể nhận biết missing.

Chọn **một cách** và test end-to-end; đừng để một serializer bật `NON_NULL` tự xóa `value` rồi consumer ngộ nhận value absent, hoặc một deserializer làm mất phân biệt null/missing.

Khi dùng Avro/Protobuf, optional/union/presence semantics khác JSON; phải lập schema theo công nghệ cụ thể. **Không suy diễn rằng `null` của Java đồng nghĩa JSON null hoặc field absent trên mọi transport.**

## 39. Khả năng mở rộng: mỗi source có mapper riêng nhưng phải giới hạn tài nguyên

Một Normalizer thường nằm **trước mọi business branch**, nên có thể trở thành bottleneck:

~~~text
N inbound producers
  → Router/Normalizer CPU
  → Canonical validation
  → Downstream workers
~~~

Thiết kế giới hạn:

| Tài nguyên | Nguy cơ | Biện pháp |
|---|---|---|
| JSON parse | Payload rất lớn/nested sâu | Max bytes, nesting depth, token count |
| String numeric parse | Decimal hàng triệu chữ số | Max length/precision |
| Regex/validation | Catastrophic backtracking | Regex an toàn, timeout/size limit |
| Transformer CPU | Nhiều input schemas phức tạp | Profiling, bounded concurrency |
| Content Enricher I/O | Fan-out lookup gây quá tải | Bounded executor, quota, caching phù hợp |
| Error/quarantine store | Producer lỗi gửi hàng triệu messages | Rate limit, retention, storage quota |
| Output message volume | Normalized order bị split thành N lines | Limit N trước Splitter |

**Normalize càng sớm càng tốt nhưng không cần ôm mọi business logic.** Một Transformer nên làm việc xác định theo input contract, không tự gọi ba external services để “cố lấp đủ field” khi source thiếu hầu hết dữ liệu.

Nếu flow chạy async, cần biết chính xác lỗi mapping xảy ra trên thread nào, gửi vào error channel/container handler nào; `send()` thành công ở upstream không chứng minh mapping và business đã hoàn tất.

## 40. Bảo mật dữ liệu: source, tenant và optional PII

Nguồn có thể gửi:

~~~text
headers.sourceSystem=LEGACY
headers.tenantId=tenant-b
payload.order_no=O-501
payload.buyer.email=somebody@example.org
~~~

Nếu nguồn không đáng tin, nó có thể **tự khai là LEGACY** để hưởng defaulting rule v1 hoặc tự thay tenant để đưa message vào group khác.

Những biện pháp cần có:

1. Xác định source từ **authenticated adapter, topic/queue được phân quyền hoặc partner credentials**.
2. Xác định tenant từ context đáng tin và kiểm tra payload tenant nếu có.
3. Validate source/version combo được phép; một producer v2 không được khai v1 để bỏ field required.
4. Giới hạn raw headers/properties được copy vào message mới.
5. Kiểm tra email/address và PII theo consent/business purpose, không đưa vào logs không cần thiết.
6. Dùng quarantine encryption, access control, retention và audit cho raw payloads.
7. Không dùng correlation ID như authorization token.

**Một value mặc định đúng với contract kỹ thuật không tự cho phép dùng value ấy cho mọi mục đích nghiệp vụ.** Ví dụ email có thật vẫn có thể không được phép dùng để gửi marketing; presence và consent là hai dữ liệu khác nhau.

## 41. Observability: theo dõi default, missing và lỗi mapping

Các metric **gợi ý**, không khẳng định có sẵn trong Spring Integration:

| Metric | Phát hiện |
|---|---|
| `normalizer.received.count` | Lưu lượng theo source/version |
| `normalizer.completed.count` | Tổng canonical outputs |
| `normalizer.rejected.count` | Input bị reject permanent |
| `normalizer.failed.count` | Lỗi mapper/infra |
| `normalizer.default.applied.count` | Field được default theo policy |
| `normalizer.missing.field.count` | Field absent |
| `normalizer.explicit.null.count` | Explicit null |
| `normalizer.unsupported.schema.count` | Source/version ngoài danh sách |
| `normalizer.currency.invalid.count` | Money mapping lỗi |
| `normalizer.conversion.duration` | Latency theo mapper/source |
| `normalizer.enrichment.retry.count` | Retry của lookup |
| `normalizer.enrichment.timeout.count` | Timeout phụ thuộc |
| `normalizer.quarantine.pending.count` | Backlog lỗi input |
| `normalizer.canonical.validation.failed.count` | Mapper sinh output sai contract |

Tags nên có cardinality thấp: `sourceSystem`, `schemaVersion` theo tập đã giới hạn, `reasonCode`, `fieldName` từ whitelist, `policyVersion`. **Không dùng `orderId`, `eventId`, `customerEmail` hoặc raw payload làm metric tag**.

Structured logs/tracing được bảo vệ có thể cho thấy:

~~~text
eventId=EV-501
sourceSystem=LEGACY
sourceSchemaVersion=1
mappingPolicyVersion=legacy-map-1
canonicalVersion=1
defaultedFields=["money.currency"]
missingFields=["email"]
normalizationOutcome=ACCEPTED
orderId=O-501
~~~

Không log untrusted raw email/address, secrets hoặc payload lớn chỉ vì muốn debug. Khi cần raw data, dùng protected quarantine reference và kiểm soát truy cập.

## 42. Runbook khi downstream báo thiếu hoặc sai field

1. **Xác định output sai:** field thật sự absent, explicit null, blank hay đã bị default?
2. **Xem canonical schema version:** downstream có hiểu đúng presence contract không?
3. **Đối chiếu source/version:** message đã đi đúng Transformer chưa?
4. **Xem trust boundary:** sourceSystem/tenant lấy từ credential hay raw header?
5. **Xem raw schema (theo quyền):** source có field gốc không, type có đúng không?
6. **Xem mapping rule:** field đổi tên, unit hoặc default được áp đúng source/version chưa?
7. **Xem provenance:** field nào được default, theo policyVersion nào?
8. **Xem Serializer:** wrapper presence hoặc JSON null có bị biến mất?
9. **Xem Content Enricher:** lookup missing definitive hay timeout/503?
10. **Xem Router/Filter:** unsupported schema bị reject hay lạc vào nhánh cũ?
11. **Xem correlation/idempotency:** retry có tạo event/group ID mới hoặc làm trộn nhóm?
12. **Xem Splitter/Aggregator:** dữ liệu lỗi có lan vào child, gây partial result sai không?
13. **Khôi phục có kiểm soát:** sửa mapping/schema, test contract, sau đó reprocess có audit/idempotency, không replay bừa dữ liệu đã có side effect.

Một dấu hiệu đặc trưng: tỷ lệ `default.applied` tăng đột ngột sau khi source nâng version. Đây có thể là dấu hiệu source **bỏ một field quan trọng** hoặc Router định tuyến sai, không phải “một cải thiện vì normalizer ít reject hơn”.

## 43. Các hiểu lầm thường gặp

**“Normalizer là đổi tên field.”** Chỉ đúng một phần. Nó còn cần type, unit, presence, validation, defaulting policy và schema/version routing.

**“Spring Integration có `@Normalizer` tự xử lý mọi schema.”** Không nên giả định có endpoint magic; EIP Normalizer thường là tổ hợp Router và Transformer.

**“Field không có và field null giống nhau.”** Không trong nhiều patch/update contract và một số event schemas.

**“`Optional<T>` luôn đủ để biểu diễn missing.”** Không khi cần phân biệt missing với explicit null.

**“Zero, false và empty đều là missing.”** Sai. Zero/false có thể là giá trị hợp lệ; empty tùy contract.

**“Nếu field required bị thiếu thì đặt default bất kỳ cho code chạy.”** Sai. Default chỉ hợp lệ khi nguồn/phiên bản **bảo đảm semantics**.

**“Legacy v1 dùng USD, vì vậy mọi source thiếu currency đều là USD.”** Sai. Fallback theo source/version, không global.

**“`Instant.now()` là cách sửa timestamp thiếu.”** Sai nếu field được định nghĩa là thời điểm nghiệp vụ gốc; `ingestedAt` là field khác.

**“Jackson map thành DTO không lỗi là đủ validation.”** Không. Required semantics, blank, money scale, schemaVersion và authorization vẫn cần kiểm tra.

**“JSON number và Java double phù hợp cho mọi phép tính tiền.”** Không. Dùng `BigDecimal`/minor units và currency policy.

**“Content Enricher timeout thì coi field unknown và chạy tiếp.”** Không nếu field là required; timeout là dependency failure.

**“Sau khi normalize, không cần lưu provenance.”** Với nhiều source/version có default rules, bỏ provenance làm khó audit và schema migration.

**“Version mới parse được bằng mapper cũ thì chắc chắn tương thích.”** Không nếu semantics/units/requiredness đổi.

**“Một canonical schema khiến mọi consumer tự hiểu null.”** Không; phải có contract/documentation và tests riêng.

**“Metadata correlation được giữ nguyên qua mọi broker adapter.”** Không tự bảo đảm; cần wire contract và header mapping test.

**“Một field invalid sau Splitter có thể drop mà Aggregator vẫn kết luận đủ.”** Không nếu group còn thiếu member; phải có failure outcome hoặc policy rõ.

## 44. Checklist thiết kế một Normalizer có thể vận hành

Trước khi publish source mới, kiểm tra:

- Có inventory tất cả **source+schema versions** và owner của chúng.
- Có **canonical contract version** độc lập với từng nguồn.
- Các field required, optional, nullable và patch semantics được mô tả.
- Policy cho **absent/null/blank/zero/false** có test tương ứng.
- Default chỉ có khi source contract bảo đảm; có **source/version scope**.
- Money/timezone/precision được convert có kiểm tra.
- Identity và tenant scope được lấy từ nguồn đáng tin.
- Mapping/validation không làm side effect trước khi đủ dữ liệu.
- Unknown/unsupported schema có rejection path, không fallback ngầm.
- Error mapping phân biệt input permanent với transient dependency.
- Có **provenance** cho default/mapping policy quan trọng.
- Correlation và idempotency không đổi qua Router/Transformer/broker.
- Gateway có rejection reply, không bị drop dẫn tới timeout vô nghĩa.
- Splitter/Aggregator có manifest/member outcome policy.
- Có contract tests, unit tests, transport integration tests, metrics và runbook.

**Một checklist đã tick đủ nhưng không test end-to-end vẫn chưa chứng minh hệ thống đúng.** Ít nhất cần xác minh cả raw input decode, Router source/version, Mapper và canonical consumer.

## 45. Bài thực hành: thêm schema thứ tư mà không sửa business handlers

Xây một mini project **OrderMessageNormalizer** với ba nguồn đã giới thiệu, sau đó thêm **Partner v3**:

1. Định nghĩa `CanonicalOrder`, `CanonicalMoney`, `FieldValue<T>` và `SourceInfo`.
2. Viết schema contract table cho Legacy v1, Partner v2 và Mobile v3.
3. Viết `normalizeLegacyV1` với fallback USD chỉ từ contract legacy.
4. Viết `normalizePartnerV2` dùng Jackson `JsonNode` cho `buyer.email` absent/null/present.
5. Viết `normalizeMobileV3` từ `money.value`, `money.isoCurrency`, `contactEmail`, `placedAt`.
6. Dùng Router Java DSL để chọn transformer theo trusted source/version.
7. Tạo canonical validator và rejection flow có reasonCode.
8. Gắn Gateway nhận input và trả canonical result hoặc typed rejection.
9. Nối một broker adapter mô phỏng mất custom headers; kiểm tra business IDs còn trong canonical contract.
10. Thêm Content Enricher cho một field required, mô phỏng 404 và HTTP 503 khác nhau.
11. Splitter một normalized order thành nhiều line jobs; kiểm tra Aggregator không trộn group hoặc báo success giả khi child invalid.
12. Chạy tests cho money conversion, missing/null/zero, unsupported version, tenant mismatch, mapping replay, DLQ.
13. Tạo dashboard tỷ lệ reject, default áp dụng, latency và enrichment timeout.
14. **Thêm Partner v3 có field đổi tên**; thay adapter/mapper/router, **không sửa Inventory/Pricing business handlers** nếu canonical contract không thay đổi.
15. Viết migration plan khi canonical contract cần thay đổi breaking semantics.

**Tiêu chí hoàn thành:** ba source khác nhau cho cùng semantic input tạo canonical result tương đương; field vắng mặt không bị điền bừa; v1 có default được audit, v2/v3 thiếu currency bị reject; email absent/null vẫn phân biệt được; không đổi logical correlation khi retry; thêm source mới không làm business handlers phụ thuộc schema nguồn.

## 46. Ghi nhớ

**Xử lý field thiếu giữa các schema** là trọng tâm của một **Message Normalizer** đáng tin cậy. Normalizer đưa nhiều dạng dữ liệu về một **canonical contract**, thường kết hợp **Router + Transformer**, nhưng **không được tự bịa những giá trị mà nguồn không cung cấp hoặc hợp đồng không bảo đảm**.

Hãy phân biệt **absent, explicit null, blank, zero và concrete value**; phân loại field **required, optional, nullable hoặc có default theo source/version**; chỉ enrich khi có nguồn authoritative; chuyển lỗi parse/schema sang đường reject đúng, còn dependency outages sang retry có kiểm soát. Với tiền và thời gian, giữ **unit, currency, scale và timezone** chính xác. Với các event đi qua Gateway, Filter, Splitter, Aggregator và broker, giữ ổn định **business identity, correlation và idempotency**.

Một Normalizer tốt giúp business handlers chỉ hiểu một contract chung, trong khi dữ liệu thiếu/không hợp lệ được **giữ đúng ý nghĩa hoặc từ chối minh bạch**. Đo lường tỷ lệ default/rejection, lưu provenance khi cần, kiểm thử cả raw bytes lẫn canonical output, và version hóa các quy tắc mapping để ngăn schema evolution làm thay đổi âm thầm kết quả nghiệp vụ.

### Tài liệu tham khảo

- Enterprise Integration Patterns, **Normalizer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Enterprise Integration Patterns, **Message Translator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns, **Content-Based Router**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference, **Content Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
