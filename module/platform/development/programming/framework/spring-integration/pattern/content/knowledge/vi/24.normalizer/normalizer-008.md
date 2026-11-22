# Tránh làm mất dữ liệu khi chuẩn hóa

> **Chương:** Normalizer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý. Bài này tập trung vào **giữ đúng ý nghĩa, độ chính xác và khả năng đối chiếu dữ liệu khi chuẩn hóa nhiều định dạng về một hợp đồng chung**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả **Normalizer** của EIP như sự phối hợp **Message Router + Message Translator/Transformer** để nhiều loại message trở thành cùng một biểu diễn canonical.
2. Phân biệt **chuyển định dạng** với **thay đổi ngữ nghĩa**, nhận diện chỗ dữ liệu có thể bị mất mà code không ném exception.
3. Xây dựng **mapping contract** xác định field bắt buộc, field không map được, khác biệt giữa `absent`/`null`/giá trị rỗng và các trường extension.
4. Xử lý tiền, đơn vị, số nguyên, thời gian, timezone, enum và định danh mà không tự ý cắt lẻ, làm tròn, default hoặc đổi namespace.
5. Thiết kế canonical DTO kèm **provenance**, version và raw reference có kiểm soát; hiểu giới hạn của việc giữ bản gốc.
6. Viết Java 17 normalizer với kết quả accepted/rejected/warning có kiểu, rồi nối hai nguồn vào Spring Integration Java DSL.
7. Kiểm thử golden mapping, invalid input, dữ liệu tương đương về nghiệp vụ, partial/unknown fields, idempotency và lỗi qua nhiều nhánh.
8. Xử lý bảo mật, retry, DLQ replay, Splitter/Aggregator và observability để không chuyển dữ liệu sai sang nơi có side effect.

## 2. Tình huống: hai đối tác mô tả cùng một đơn theo hai schema

**Partner A** gửi một đơn hàng với số lượng dạng chuỗi, đơn giá theo major units của USD, thời gian ISO-8601:

~~~json
{
  "order_id": "PO-901",
  "qty": "003",
  "unit_price": "12.50",
  "currency": "usd",
  "created_at": "2026-11-21T08:00:00Z",
  "channel": "retail",
  "note": null
}
~~~

**Partner B** dùng minor units (cent), epoch milliseconds và mã kênh:

~~~json
{
  "orderNumber": "PO-901",
  "quantity": 3,
  "priceMinor": 1250,
  "currencyCode": "USD",
  "eventEpochMs": 1795248000000,
  "channelCode": 1,
  "legacyCampaignCode": "CAMPAIGN-7"
}
~~~

Cả hai có thể tạo canonical business fields tương đương:

~~~json
{
  "externalOrderId": "PO-901",
  "quantity": 3,
  "unitPriceMinor": 1250,
  "currency": "USD",
  "occurredAt": "2026-11-21T08:00:00Z",
  "channel": "RETAIL"
}
~~~

Nhưng nếu **chỉ** giữ JSON cuối cùng, bạn đã bỏ lỡ những khác biệt quan trọng:

- A gửi `note: null`, còn B **không có** field note. Hai ý nghĩa có thể khác nhau trong PATCH/merge.
- B gửi `legacyCampaignCode`. Nếu nó điều khiển chiết khấu, bỏ qua có thể gây sai tiền; nếu nó chỉ dùng attribution, có thể chấp nhận warning theo chính sách.
- Cả A và B có thể dùng `PO-901` nhưng là **hai đơn khác nhau** nếu namespace của partner khác nhau.
- Giá major/minor units, timezone và mapping channel cần hợp đồng có version; không thể “đoán” theo kiểu dữ liệu.

**Định nghĩa mục tiêu:** Normalizer phải **bảo toàn thông tin nghiệp vụ cần thiết**, minh bạch về thông tin không biểu diễn được và không phát lệnh sai chỉ vì một Mapper trả thành công.

~~~mermaid
flowchart LR
    A["Partner A"] --> R["Trusted source routing"]
    B["Partner B"] --> R
    R --> TA["Translator A"]
    R --> TB["Translator B"]
    TA --> V{"Mapping + validation"}
    TB --> V
    V -->|"Hợp lệ"| C["CanonicalOrder + provenance"]
    V -->|"Không hợp lệ"| E["Rejection / quarantine"]
    A -.-> RAW[("Protected raw store")]
    B -.-> RAW
    C --> D["Router / Gateway / Business handler"]
~~~

## 3. Normalizer trong Enterprise Integration Patterns

Normalizer giải quyết việc **nhận nhiều loại message và cung cấp một format chung** cho downstream. Về logic, nó bao gồm:

1. **Router:** xác định loại message/schema nguồn bằng metadata đáng tin cậy.
2. **Translator/Transformer tương ứng:** đổi schema nguồn thành canonical model.
3. **Hợp đồng đầu ra thống nhất:** các consumer sau Normalizer không cần hiểu toàn bộ schema A/B/C.
4. **Đường xử lý không map được:** reject, quarantine hoặc warning khi chính sách cho phép.

~~~text
ExternalOrderA --\
ExternalOrderB ----> select translator ---> CanonicalOrder ---> downstream
LegacyOrderC   --/       |                 ^
                          +-- unsupported ---+--> rejection flow
~~~

Trong Spring Integration, có thể xây pattern này bằng `.route(...)` chọn nhánh theo type/schema hoặc bằng các input channels riêng cho từng đối tác rồi `.transform(...)` về cùng shared channel. **Không bắt buộc** có một endpoint Java mang tên `Normalizer`; pattern là sự kết hợp chức năng Router và Transformer.

| Pattern | Trách nhiệm | Không nên nhầm với |
| --- | --- | --- |
| **Normalizer** | Nhiều schema vào → một canonical schema | Cứ thay tên field là an toàn |
| **Transformer** | Chuyển một representation sang representation khác | Tự kiểm mọi quyền, trạng thái DB |
| **Router** | Chọn nhánh theo source/type/content | Tự xác minh schema hợp lệ |
| **Filter** | Chặn message không đạt điều kiện | Tự trả đầy đủ lý do reject |
| **Content Enricher** | Bổ sung dữ liệu từ nguồn khác | Khôi phục raw đã chủ động cất |
| **Claim Check** | Lưu raw/payload lớn ở store, chuyển reference | Tự bảo đảm quyền hoặc retention |
| **Aggregator** | Gom child replies cùng correlation | Nhận duplicate là một child mới |

## 4. Những cách âm thầm làm mất dữ liệu

Mất dữ liệu có thể xảy ra **ngay cả khi deserialize, transform và send đều báo thành công**.

| Loại mất thông tin | Tình huống | Hậu quả |
| --- | --- | --- |
| Drop field | `campaignCode` không có trong output DTO | Mất attribution hoặc quy tắc discount |
| Default sai | Thiếu `qty` → tự gán `1` | Tạo số lượng không được xác nhận |
| Absent/null nhập làm một | Missing field và explicit null cùng thành Java `null` | Xóa nhầm hoặc không xóa field |
| Numeric truncation | `12.345` USD → `1234` cent | Sai tiền |
| Double precision | Parse tiền qua `double` | Lỗi floating point/rounding |
| Overflow | Giá × quantity vượt `long` | Tổng tiền âm/sai |
| Sai đơn vị | `1250` minor units được hiểu là `1250 USD` | Giá gấp 100 |
| Sai epoch unit | Epoch seconds đọc thành milliseconds | Timestamp sai hàng chục năm |
| Timezone mặc định | Local time không offset bị ép UTC | Sai hạn xử lý |
| Unknown enum fallback | `channelCode=3` → RETAIL | Route nhầm quy trình |
| Text normalization mất nghĩa | Uppercase ID phân biệt case | Hai ID khác nhau bị nhập làm một |
| Mất order | `List` → `Set` | Không còn thứ tự nghiệp vụ |
| Mất namespace | Chỉ giữ `orderId`, bỏ tenant/partner | Dedup/authorization sai |
| Metadata bị xóa | Mất execution/correlation/operation ID | Group reply nhầm hoặc side effect trùng |
| Schema drift | Dùng parser v1 cho message v2 | Hiểu sai trường |
| Bắt mọi lỗi rồi trả DTO mặc định | DB/network/bug thành “input không hợp lệ” | Không retry/reconcile đúng |

### 4.1. Lossy có chủ đích khác lossy ngoài ý muốn

Không phải mọi trường từ đối tác đều được phép giữ hoặc phát ra. Field nhạy cảm, dữ liệu thừa hoặc secret có thể **phải bỏ** theo data minimization. Nhưng mọi quyết định bỏ dữ liệu cần có:

- Mapping contract nói rõ field nào bị bỏ, vì sao và ai phê duyệt.
- Mức độ ảnh hưởng: **bắt buộc**, optional, không đáng tin, nhạy cảm, extension.
- Chính sách: **ERROR**, **WARNING**, redact, extension hoặc raw retention.
- Bằng chứng đủ cho audit nhưng không log PII/token vô hạn.
- Thời hạn lưu/xóa phù hợp quy định và replay window.

**Tránh mất dữ liệu không đồng nghĩa lưu mọi dữ liệu mãi mãi.** Bảo mật, quyền riêng tư và retention là một phần của tính đúng đắn.

## 5. Mapping contract phải viết trước code

Ví dụ mapping matrix cho hai đối tác:

| Source field | Canonical field | Mapping | Nếu không hiểu được |
| --- | --- | --- | --- |
| A `order_id` | `externalOrderId` | Giữ nguyên ID có namespace | Reject |
| A `qty` | `quantity` | Parse integer exact, range 1..500 | Reject |
| A `unit_price` | `unitPriceMinor` | BigDecimal major→minor theo currency | Reject nếu cần rounding bất ngờ |
| A `created_at` | `occurredAt` | ISO instant có offset | Reject thiếu zone |
| A `channel` | `channel` | retail/wholesale → enum | Reject unknown |
| A `note` | `note` | Giữ absent/null/value | Reject nếu parser mất presence |
| B `priceMinor` | `unitPriceMinor` | Kiểm range, **không nhân 100** | Reject |
| B `eventEpochMs` | `occurredAt` | Instant.ofEpochMilli | Reject ngoài window |
| B `channelCode` | `channel` | 1=RETAIL, 2=WHOLESALE | Reject unknown |
| B `legacyCampaignCode` | Chưa có trong canonical v1 | Warning + raw ref nếu không ảnh hưởng nghiệp vụ | Reject nếu field quyết định discount |
| Trusted `tenantId` | `source.tenantId` | Lấy từ adapter đã xác thực | Security reject |
| Schema version | `source.sourceSchemaVersion` | Chọn decoder/policy đã kiểm | Reject không hỗ trợ |

**Ba quy tắc không nên vi phạm:**

1. Trường required **không** được tự gán default hợp lệ để đi qua Filter.
2. Enum/units không biết **không** được tự map về giá trị nghiệp vụ gần giống.
3. Một field không map được cần **quyết định explicit** chứ không tự động biến mất.

### 5.1. Mỗi field cần nguồn sự thật

Đừng tin `tenantId` hoặc `partnerId` từ body JSON là quyền truy cập. Boundary HTTP/broker phải xác thực principal/source, so khớp tenant, schema version và cấp một **trusted context** cho Normalizer.

Nếu client tự gắn header `partnerId=A` nhằm đi vào Translator A, router chỉ dựa vào header ấy có thể dẫn đến type confusion và cross-tenant data leak.

## 6. Định dạng canonical và provenance

Một canonical DTO tốt không nhất thiết là “siêu tập mọi field từ mọi đối tác”. Mục đích là giữ **các khái niệm chung thật sự cần**.

~~~text
CanonicalOrder
  source:
    tenantId
    partnerId
    sourceSchemaVersion
    rawReference (internal-only)
  externalOrderId
  quantity
  unitPriceMinor
  currency
  occurredAt
  channel
  note: ABSENT | EXPLICIT_NULL | VALUE
  canonicalSchemaVersion
~~~

- **Core fields**: có ý nghĩa và được dùng rộng rãi, có contract/version.
- **SourceContext/provenance**: cho phép truy vết partner, schema và bản gốc theo quyền.
- **Controlled extension**: cân nhắc với field thuộc riêng một nguồn; phải giới hạn kích thước, loại dữ liệu, quyền.
- **Raw reference**: tham chiếu đến raw payload đã lưu an toàn, dùng cho audit/reprocess khi cần.
- **MappingIssue**: mã warning/error khi output không thể giữ toàn bộ ý nghĩa.

Một `rawReference` là dữ liệu **nội bộ**, không phải public URL/bearer token để phát cho mọi consumer. Nếu raw chứa PII, cần encryption, IAM, audit và retention.

### 6.1. Namespace của business identity

Hai đối tác có thể cùng có `orderId=PO-901`. Khóa danh tính nên xét:

~~~text
(tenantId, partnerId, externalOrderId)
~~~

Nếu một order có nhiều lệnh `CREATE`/`CANCEL`/`AMEND`, idempotency cần thêm `commandId` hoặc `operationType` ổn định. **Correlation group** theo execution và **idempotency key** của business side effect là hai mục đích khác nhau.

### 6.2. Absent, explicit null, chuỗi rỗng

| Dữ liệu nguồn | Ý nghĩa khi cập nhật một field | Cần làm gì |
| --- | --- | --- |
| Không có key | Không yêu cầu thay đổi field | Giữ `ABSENT` |
| Key có `null` | Có thể là yêu cầu xóa giá trị | Giữ `EXPLICIT_NULL` |
| Key có `""` | Gửi giá trị rỗng | Giữ `VALUE("")` hoặc reject theo policy |
| Key có chuỗi | Set giá trị cụ thể | `VALUE(text)` sau validation |

Java `Optional<String>` thường không biểu diễn được **sự khác biệt giữa missing và explicit null**; với PATCH/merge, dùng kiểu có trạng thái rõ.

~~~java
enum FieldState {
    ABSENT,
    EXPLICIT_NULL,
    VALUE
}

record FieldText(FieldState state, String value) {
    FieldText {
        if (state == null) {
            throw new IllegalArgumentException("FIELD_STATE_MISSING");
        }
        if ((state == FieldState.VALUE) != (value != null)) {
            throw new IllegalArgumentException("INVALID_FIELD_STATE");
        }
    }

    static FieldText absent() {
        return new FieldText(FieldState.ABSENT, null);
    }

    static FieldText explicitNull() {
        return new FieldText(FieldState.EXPLICIT_NULL, null);
    }

    static FieldText of(String text) {
        return new FieldText(
            FieldState.VALUE,
            java.util.Objects.requireNonNull(text));
    }
}
~~~

**Chú ý tại parser boundary:** Deserializer bind cả missing JSON property và explicit JSON null vào cùng Java `null` có thể làm mất presence *trước cả Transformer*. Nếu contract yêu cầu phân biệt, phải lấy trạng thái tồn tại của field ngay khi parse JSON (hoặc một cấu trúc presence-aware) rồi dựng `FieldText`.

## 7. Bảo toàn tiền và độ chính xác số

Hai nguồn có thể tương đương:

~~~text
Partner A: "12.50" USD (major units)
Partner B: 1250 USD minor units
Canonical: unitPriceMinor=1250, currency=USD
~~~

Nhưng không phải mọi chuỗi decimal đều có thể đổi sang minor units mà **không làm tròn**. Giá `12.345 USD` có phần lẻ cent; nếu chưa có rounding policy, phải reject thay vì cắt bớt.

### 7.1. Java `BigDecimal` và `longValueExact`

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class MoneyNormalization {
    private MoneyNormalization() {}

    static String currency(String raw) {
        if (raw == null) {
            throw new MappingFailure(
                "currency", "CURRENCY_REQUIRED");
        }
        String normalized = raw.strip().toUpperCase(Locale.ROOT);
        if (!normalized.equals("USD")
                && !normalized.equals("VND")) {
            throw new MappingFailure(
                "currency", "UNSUPPORTED_CURRENCY");
        }
        return normalized;
    }

    static int scale(String currency) {
        return switch (currency) {
            case "USD" -> 2;
            case "VND" -> 0;
            default -> throw new MappingFailure(
                "currency", "UNSUPPORTED_CURRENCY");
        };
    }

    static long fromMajor(String raw, String currency) {
        if (raw == null || raw.isBlank()) {
            throw new MappingFailure(
                "unitPrice", "PRICE_REQUIRED");
        }
        try {
            BigDecimal major = new BigDecimal(raw.strip());
            long minor = major.movePointRight(
                scale(currency)).longValueExact();
            return fromMinor(minor);
        } catch (NumberFormatException | ArithmeticException ex) {
            throw new MappingFailure(
                "unitPrice", "PRICE_NOT_EXACT_MINOR_UNITS", ex);
        }
    }

    static long fromMinor(long minor) {
        if (minor < 0 || minor > 1_000_000_000L) {
            throw new MappingFailure(
                "unitPrice", "PRICE_OUT_OF_RANGE");
        }
        return minor;
    }
}
~~~

Giới hạn 1 tỷ minor units, tập tiền `USD/VND` và các scale ở đây **chỉ là policy minh họa**. Production phải kiểm số chữ số thập phân theo currency/contract của từng nguồn, có version và cân nhắc các đồng tiền có quy tắc đặc biệt.

### 7.2. Không tự quy đổi tỷ giá

`12.50 USD` và `12500 VND` **không** tự động là cùng một giá trị. Normalizer chỉ nên thống nhất **cách biểu diễn**, không tự dùng tỷ giá hôm nay để thay nghĩa lịch sử. Nếu cần FX conversion, phải lưu source rate/time/rounding policy và các amount gốc theo yêu cầu audit.

### 7.3. Kiểm overflow của tổng tiền

~~~java
long totalMinor;
try {
    totalMinor = Math.multiplyExact(
        (long) quantity, unitPriceMinor);
} catch (ArithmeticException ex) {
    throw new MappingFailure(
        "totalPriceMinor", "TOTAL_OVERFLOW", ex);
}
~~~

Nếu nghiệp vụ cần số lớn hơn `long`, dùng `BigInteger`/`BigDecimal` với schema và quy tắc serialization rõ. Đừng cast qua `double`.

## 8. Thời gian, timezone và độ phân giải

| Nguồn | Có thể xác định instant? | Hướng xử lý |
| --- | --- | --- |
| `2026-11-21T08:00:00Z` | Có | Parse thành `Instant` |
| `2026-11-21T15:00:00+07:00` | Có | Cùng instant ở UTC |
| `2026-11-21 15:00` không offset | Không chắc | Reject hoặc contract quy định zone |
| Epoch milliseconds | Có khi biết đơn vị | `Instant.ofEpochMilli` |
| Epoch seconds | Có khi biết đơn vị | `Instant.ofEpochSecond` |
| `LocalDate` không giờ | Không phải instant | Giữ date-only, không đoán UTC midnight |

**Không dùng `ZoneId.systemDefault()`** cho dữ liệu đối tác có nghĩa vụ timezone rõ. Khác host timezone có thể cho output khác nhau, thậm chí trước/sau deadline.

Nếu nguồn có nanosecond precision nhưng canonical/broker chỉ giữ milliseconds, đó có thể là **loss có chủ đích**; cần tài liệu hóa. Nếu contract đòi chữ ký trên raw bytes, canonical reserialization không thể thay thế bản gốc.

## 9. Unknown enum, string normalization và schema drift

Giả sử Partner B thêm mã kênh `3=MARKETPLACE` trong bản schema mới. Nếu mapper v2 dùng `default=RETAIL`, toàn bộ đơn marketplace sẽ **đi nhầm Router downstream**.

~~~java
enum OrderChannel {
    RETAIL,
    WHOLESALE
}

static OrderChannel channelByCode(int value) {
    return switch (value) {
        case 1 -> OrderChannel.RETAIL;
        case 2 -> OrderChannel.WHOLESALE;
        default -> throw new MappingFailure(
            "channelCode", "UNKNOWN_CHANNEL_CODE");
    };
}
~~~

Có thể có enum `UNKNOWN` **chỉ khi** downstream hiểu và không thực hiện side effect khi không rõ channel. Unknown không phải “retail gần đúng”.

### 9.1. Không uppercase mọi business ID

`orderId="Ab-12"` và `orderId="AB-12"` có thể là hai IDs khác nhau nếu đối tác phân biệt chữ hoa. Một Transformer áp `toUpperCase` cho mọi string có thể gây **collision** và dedup sai. Việc normalize phải dựa trên contract của **từng field**, không theo thói quen format.

### 9.2. Các version khác nhau

~~~text
source schema A       a-order-v1
source schema B       b-order-v2
canonical schema      canonical-order-v1
normalizer policy     normalizer-policy-v6
~~~

Version của nguồn không đồng nghĩa version của canonical model. Khi policy thay, DLQ replay có thể cho output khác; cần pin version, migration hoặc explicit re-normalization theo quy định.

## 10. Raw reference, provenance và quyết định có giữ field nguồn hay không

Canonical DTO **không bắt buộc** là bản sao lossless của mọi source schema. Ví dụ `legacyCampaignCode` của B chưa có field chung để đặt vào. Có bốn cách có chủ đích:

| Chính sách | Hành động | Điều kiện phù hợp |
| --- | --- | --- |
| **Reject** | Không phát canonical thành công | Field ảnh hưởng giá, quyền, pháp lý hoặc routing |
| **Warn + raw reference** | Accepted với warning có mã | Field không ảnh hưởng xử lý hiện tại, nguồn có thể đối chiếu |
| **Controlled extension** | Lưu vào một extension có schema/allowlist | Một số consumer được phép đọc field đặc thù |
| **Evolve canonical** | Tạo version/field mới, migration | Field đã trở thành khái niệm chung cần thiết |

Một payload canonical có thể giữ provenance:

~~~text
SourceContext
  tenantId              = shop-a
  partnerId             = partner-b
  sourceSchemaVersion   = b-order-v2
  rawReference          = raw/b-901 (internal-only)

CanonicalOrder
  externalOrderId       = PO-901
  quantity              = 3
  unitPriceMinor        = 1250
  currency              = USD
  occurredAt            = 2026-11-21T08:00:00Z
  channel               = RETAIL
  note                  = ABSENT
  canonicalSchemaVersion= canonical-order-v1

MappingWarning
  LEGACY_CAMPAIGN_NOT_MAPPED
~~~

**Không được tuyên bố** canonical DTO riêng lẻ là hoàn toàn lossless khi `legacyCampaignCode` bị bỏ. Warning chỉ là bằng chứng mapping policy đã nhận diện loss; raw reference chỉ hữu ích nếu object tồn tại, đúng tenant, còn retention và consumer có quyền đọc.

Raw storage cần checksum, IAM, encryption, quyền truy xuất và cleanup phù hợp. Một raw reference không được copy thành pre-signed URL công khai. Không giữ raw PII vô hạn để thuận tiện debug; data minimization và quyền xóa dữ liệu vẫn phải được tôn trọng.

## 11. Java 17: model nguồn, canonical và typed mapping result

Bài dùng `record` để biểu diễn dữ liệu bất biến. `SourceContext` là metadata được **adapter đã xác thực** cung cấp, không lấy từ một header do client tự khai.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

record SourceContext(
    String tenantId,
    String partnerId,
    String sourceSchemaVersion,
    String rawReference
) {
    SourceContext {
        if (tenantId == null || tenantId.isBlank()
            || partnerId == null || partnerId.isBlank()
            || sourceSchemaVersion == null
            || sourceSchemaVersion.isBlank()
            || rawReference == null || rawReference.isBlank()) {
            throw new IllegalArgumentException(
                "INVALID_SOURCE_CONTEXT");
        }
    }
}

record PartnerAOrder(
    String orderId,
    String quantityText,
    String unitPriceDecimal,
    String currency,
    String occurredAtIso,
    String channel,
    FieldText note
) {}

record PartnerBOrder(
    String orderNumber,
    long quantity,
    long priceMinor,
    String currencyCode,
    long eventEpochMs,
    int channelCode,
    FieldText note,
    String legacyCampaignCode
) {}

record AEnvelope(SourceContext source, PartnerAOrder body) {}
record BEnvelope(SourceContext source, PartnerBOrder body) {}

record CanonicalOrder(
    SourceContext source,
    String externalOrderId,
    int quantity,
    long unitPriceMinor,
    String currency,
    Instant occurredAt,
    OrderChannel channel,
    FieldText note,
    String canonicalSchemaVersion
) {
    CanonicalOrder {
        Objects.requireNonNull(source);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(channel);
        Objects.requireNonNull(note);
    }
}

enum IssueSeverity { WARNING, ERROR }

record MappingIssue(
    String field,
    String code,
    IssueSeverity severity
) {}

record NormalizationResult(
    SourceContext source,
    CanonicalOrder value,
    List<MappingIssue> issues
) {
    NormalizationResult {
        Objects.requireNonNull(source);
        issues = List.copyOf(issues);
    }

    boolean accepted() {
        return value != null && issues.stream().noneMatch(
            i -> i.severity() == IssueSeverity.ERROR);
    }
}

record NormalizationRejection(
    String partnerId,
    String rawReference,
    List<MappingIssue> issues
) {
    NormalizationRejection {
        issues = List.copyOf(issues);
    }
}
~~~

`NormalizationResult` có thể accepted **kèm warning**. Nếu có lỗi bắt buộc, `value=null` và kết quả bị rejected; không tạo DTO giả có default vô nghĩa chỉ để tránh null. `NormalizationRejection` được dùng cho **quarantine nội bộ**; public API cần projection loại raw key và metadata nhạy cảm.

### 11.1. Mapping errors và technical failures là hai loại khác nhau

~~~java
final class MappingFailure extends RuntimeException {
    private final String field;
    private final String code;

    MappingFailure(String field, String code) {
        super(code);
        this.field = field;
        this.code = code;
    }

    MappingFailure(String field, String code, Throwable cause) {
        super(code, cause);
        this.field = field;
        this.code = code;
    }

    String field() { return field; }
    String code() { return code; }
}
~~~

Đây là kiểu lỗi **dữ liệu nguồn không chuyển được theo hợp đồng**, ví dụ unsupported enum, quantity sai, số tiền cần rounding. Không bắt mọi `Exception` rồi biến lỗi DB/object store, bug hoặc unavailable service thành rejection; chúng cần error channel, retry/backoff hoặc alarm riêng.

## 12. NormalizerService: mapping Partner A và B có kiểm soát

Các đoạn mã dưới đây sử dụng `FieldText`, `MoneyNormalization`, `MappingFailure`, `OrderChannel` và các records đã định nghĩa trong bài. Họ `NormalizerService` chỉ tính toán, không gọi side effect.

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

final class NormalizerService {

    public NormalizationResult fromA(AEnvelope env) {
        Objects.requireNonNull(env);
        SourceContext source = Objects.requireNonNull(env.source());
        PartnerAOrder raw = Objects.requireNonNull(env.body());

        try {
            requireSource(source, "partner-a", "a-order-v1");
            String currency = MoneyNormalization.currency(raw.currency());

            CanonicalOrder output = new CanonicalOrder(
                source,
                requiredOrderId(raw.orderId()),
                parseQuantity(raw.quantityText()),
                MoneyNormalization.fromMajor(
                    raw.unitPriceDecimal(), currency),
                currency,
                parseIsoTime(raw.occurredAtIso()),
                fromChannelName(raw.channel()),
                requirePresence(raw.note()),
                "canonical-order-v1");

            validateTotal(output);
            return new NormalizationResult(
                source, output, List.of());
        } catch (MappingFailure failure) {
            return rejection(source, failure);
        }
    }

    public NormalizationResult fromB(BEnvelope env) {
        Objects.requireNonNull(env);
        SourceContext source = Objects.requireNonNull(env.source());
        PartnerBOrder raw = Objects.requireNonNull(env.body());

        try {
            requireSource(source, "partner-b", "b-order-v2");
            String currency = MoneyNormalization.currency(raw.currencyCode());

            CanonicalOrder output = new CanonicalOrder(
                source,
                requiredOrderId(raw.orderNumber()),
                positiveQuantity(raw.quantity()),
                MoneyNormalization.fromMinor(raw.priceMinor()),
                currency,
                parseEpochMillis(raw.eventEpochMs()),
                fromChannelCode(raw.channelCode()),
                requirePresence(raw.note()),
                "canonical-order-v1");

            validateTotal(output);
            List<MappingIssue> issues = new ArrayList<>();

            if (raw.legacyCampaignCode() != null
                && !raw.legacyCampaignCode().isBlank()) {
                // Policy ví dụ: field này chỉ phục vụ attribution.
                issues.add(new MappingIssue(
                    "legacyCampaignCode",
                    "LEGACY_CAMPAIGN_NOT_MAPPED",
                    IssueSeverity.WARNING));
            }
            return new NormalizationResult(
                source, output, issues);
        } catch (MappingFailure failure) {
            return rejection(source, failure);
        }
    }

    private static void requireSource(
            SourceContext source, String partner, String version) {
        if (!partner.equals(source.partnerId())
            || !version.equals(source.sourceSchemaVersion())) {
            throw new MappingFailure(
                "source", "SOURCE_SCHEMA_MISMATCH");
        }
    }

    private static NormalizationResult rejection(
            SourceContext source, MappingFailure failure) {
        return new NormalizationResult(
            source, null,
            List.of(new MappingIssue(
                failure.field(), failure.code(), IssueSeverity.ERROR)));
    }

    private static String requiredOrderId(String id) {
        if (id == null || id.isBlank()) {
            throw new MappingFailure(
                "orderId", "ORDER_ID_REQUIRED");
        }
        // Không uppercase ID nếu đối tác phân biệt hoa/thường.
        return id;
    }

    private static int parseQuantity(String text) {
        if (text == null || text.isBlank()) {
            throw new MappingFailure(
                "quantity", "QUANTITY_REQUIRED");
        }
        try {
            return positiveQuantity(Long.parseLong(text.strip()));
        } catch (NumberFormatException failure) {
            throw new MappingFailure(
                "quantity", "QUANTITY_NOT_INTEGER", failure);
        }
    }

    private static int positiveQuantity(long value) {
        if (value < 1 || value > 500) {
            throw new MappingFailure(
                "quantity", "QUANTITY_OUT_OF_RANGE");
        }
        return (int) value;
    }

    private static Instant parseIsoTime(String value) {
        if (value == null || value.isBlank()) {
            throw new MappingFailure(
                "occurredAt", "TIME_REQUIRED");
        }
        try {
            return validateTime(Instant.parse(value.strip()));
        } catch (DateTimeException failure) {
            throw new MappingFailure(
                "occurredAt", "INVALID_ISO_TIME", failure);
        }
    }

    private static Instant parseEpochMillis(long value) {
        try {
            return validateTime(Instant.ofEpochMilli(value));
        } catch (DateTimeException failure) {
            throw new MappingFailure(
                "eventEpochMs", "INVALID_EPOCH_MILLIS", failure);
        }
    }

    private static Instant validateTime(Instant time) {
        Instant from = Instant.parse("2000-01-01T00:00:00Z");
        Instant until = Instant.parse("2100-01-01T00:00:00Z");
        if (time.isBefore(from) || !time.isBefore(until)) {
            throw new MappingFailure(
                "occurredAt", "TIME_OUT_OF_RANGE");
        }
        return time;
    }

    private static OrderChannel fromChannelName(String value) {
        if (value == null) {
            throw new MappingFailure(
                "channel", "CHANNEL_REQUIRED");
        }
        return switch (value.strip().toUpperCase(Locale.ROOT)) {
            case "RETAIL" -> OrderChannel.RETAIL;
            case "WHOLESALE" -> OrderChannel.WHOLESALE;
            default -> throw new MappingFailure(
                "channel", "UNKNOWN_CHANNEL");
        };
    }

    private static OrderChannel fromChannelCode(int code) {
        return switch (code) {
            case 1 -> OrderChannel.RETAIL;
            case 2 -> OrderChannel.WHOLESALE;
            default -> throw new MappingFailure(
                "channelCode", "UNKNOWN_CHANNEL_CODE");
        };
    }

    private static FieldText requirePresence(FieldText note) {
        if (note == null) {
            throw new MappingFailure(
                "note", "NOTE_PRESENCE_NOT_CAPTURED");
        }
        return note;
    }

    private static void validateTotal(CanonicalOrder order) {
        try {
            Math.multiplyExact(
                (long) order.quantity(), order.unitPriceMinor());
        } catch (ArithmeticException failure) {
            throw new MappingFailure(
                "totalPriceMinor", "TOTAL_OVERFLOW", failure);
        }
    }
}
~~~

**Điều được bảo vệ:**

- A và B phải đúng **nguồn + schema version** đã xác thực.
- Giá của A được đổi đúng đơn vị và reject khi không thể giữ exact precision; B không bị nhân 100.
- Unknown channel không bao giờ mặc định thành RETAIL.
- Ghi rõ `ABSENT` và `EXPLICIT_NULL` thông qua `FieldText`.
- Không tạo operation ID ngẫu nhiên mỗi lần retry.
- Field campaign chỉ bị bỏ theo chính sách warning đã phê duyệt.

Code tập trung vào mapping. Giới hạn quantity 1..500, price 1 tỷ minor units và thời gian 2000–2100 là **minh họa**, không phải policy chung của mọi ứng dụng.

## 13. Java DSL: hội tụ hai schema về một kênh canonical

Hai input channels thuộc các adapter xác thực khác nhau. Mỗi nhánh dùng một Transformer theo schema, đưa `NormalizationResult` vào shared Router, sau đó tách accepted/quarantine.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class LossAwareNormalizerConfiguration {

    @Bean("normalizer.a.in")
    DirectChannel inputA() { return new DirectChannel(); }

    @Bean("normalizer.b.in")
    DirectChannel inputB() { return new DirectChannel(); }

    @Bean("normalizer.results")
    DirectChannel results() { return new DirectChannel(); }

    @Bean("normalizer.accepted")
    DirectChannel accepted() { return new DirectChannel(); }

    @Bean("normalizer.rejected")
    DirectChannel rejected() { return new DirectChannel(); }

    @Bean("orders.canonical.out")
    QueueChannel canonicalOutput() { return new QueueChannel(); }

    @Bean("orders.quarantine.out")
    QueueChannel quarantineOutput() { return new QueueChannel(); }

    @Bean
    NormalizerService normalizer() { return new NormalizerService(); }

    @Bean
    IntegrationFlow partnerA(NormalizerService normalizer) {
        return IntegrationFlow.from("normalizer.a.in")
            .transform(AEnvelope.class, normalizer::fromA)
            .channel("normalizer.results")
            .get();
    }

    @Bean
    IntegrationFlow partnerB(NormalizerService normalizer) {
        return IntegrationFlow.from("normalizer.b.in")
            .transform(BEnvelope.class, normalizer::fromB)
            .channel("normalizer.results")
            .get();
    }

    @Bean
    IntegrationFlow decision() {
        return IntegrationFlow.from("normalizer.results")
            .route(
                NormalizationResult.class,
                result -> result.accepted() ? "OK" : "REJECT",
                r -> r.channelMapping("OK", "normalizer.accepted")
                      .channelMapping("REJECT", "normalizer.rejected"))
            .get();
    }

    @Bean
    IntegrationFlow deliver() {
        return IntegrationFlow.from("normalizer.accepted")
            .transform(
                NormalizationResult.class,
                NormalizationResult::value)
            .channel("orders.canonical.out")
            .get();
    }

    @Bean
    IntegrationFlow quarantine() {
        return IntegrationFlow.from("normalizer.rejected")
            .transform(
                NormalizationResult.class,
                result -> new NormalizationRejection(
                    result.source().partnerId(),
                    result.source().rawReference(),
                    result.issues()))
            .channel("orders.quarantine.out")
            .get();
    }
}
~~~

### 13.1. Có bắt buộc đặt một Router trước Transformer?

Không. Trong ví dụ, **nguồn đã được xác minh ở input adapter** và hai channels riêng giúp chọn translator đúng. Nếu nhận nhiều schema ở cùng một channel, Router có thể dùng **trusted source/schema/type** để chọn Translator; unknown type/version phải có rejection route, không thử một Mapper mặc định tùy tiện.

Đây là mô hình Java DSL cho họ Spring Integration hiện đại. Chữ ký overload và cấu hình endpoint cần kiểm chứng theo dependency/version thực tế ở vòng Content QA; **STEP 4 NEW chưa chạy build**.

### 13.2. Không gửi lỗi mapping vào business handler

Nhánh `normalizer.accepted` chuyển result thành `CanonicalOrder`; nhánh `normalizer.rejected` chuyển thành `NormalizationRejection` có mã lỗi. Một rejected message không được phát sang Inventory/Payment Gateway chỉ vì Transformer đã trả một object không null.

`QueueChannel` ở demo chỉ cung cấp điểm nhận trong test, không chứng minh consumer cuối commit và cũng không phải durable broker.

## 14. Validation sau Transformer và error handling

Sau Normalize vẫn cần canonical domain validation và business-state validation tại điểm commit.

~~~text
Adapter: authentication + schema + size
    |
    v
Normalizer: source-specific mapping
    |
    +--> ERROR mapping -> reject/quarantine
    |
    v
Canonical business validation
    |
    +--> domain invalid -> typed rejection
    |
    v
Authorization / idempotent receiver
    |
    v
Business transaction (inventory/payment/DB)
    |
    v
Outbox / reply / audit
~~~

| Lỗi | Thuộc bước nào | Có nên retry? |
| --- | --- | --- |
| `qty="three"` | Parse/mapping | Không với cùng bytes |
| `channelCode=99` | Unsupported mapping | Không cho tới khi nâng policy |
| `unit_price="12.345"` USD | Precision mismatch | Cần sửa dữ liệu/rule |
| Source tenant không được phép | AuthN/AuthZ | Không bypass quyền |
| DB/network timeout | Technical | Bounded retry/backoff |
| Hết hàng tại commit | Business-state outcome | Theo hợp đồng nghiệp vụ |

**Không bắt mọi exception thành một `MappingIssue(ERROR)`**. Lỗi hạ tầng phải đi error channel hoặc exception path; một lỗi dữ liệu terminal không nên bị broker retry vô hạn.

### 14.1. Header propagation

Transformer, MessageChannel và adapter có thể tái tạo message/headers. Phải kiểm tra việc bảo toàn `businessCorrelationId`, `executionId`, `commandId` và mapping policy/schema version qua HTTP, JMS, AMQP hay Kafka.

- `MessageHeaders.ID` có thể đổi; không dùng làm business idempotency key.
- `contentType` của raw JSON không nhất thiết đúng cho payload canonical object mới.
- `replyChannel` là object trong JVM, không mặc định serializable qua broker.
- Không copy JWT/secret/raw payload lớn sang header hoặc log không kiểm soát.

### 14.2. Normalization không thay authorization

Một canonical record có field `tenantId` hợp lệ về cú pháp không chứng minh principal có quyền. Tránh lấy namespace từ payload ngoài; validate source và tenant ở ingress và tại business handler nếu cần.

## 15. Unit tests: hai nguồn tương đương về nghiệp vụ, không giống về provenance

Dùng JUnit 5 để kiểm `NormalizerService` và các value types. Hai đơn có cùng quantity, price và instant phải cho business fields tương đương, **nhưng** source và trạng thái note không giống nhau.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class NormalizerServiceTest {
    private final NormalizerService service = new NormalizerService();

    private static SourceContext aSource() {
        return new SourceContext(
            "shop-a", "partner-a", "a-order-v1", "raw/a-901");
    }

    private static SourceContext bSource() {
        return new SourceContext(
            "shop-a", "partner-b", "b-order-v2", "raw/b-901");
    }

    private static PartnerAOrder aOrder() {
        return new PartnerAOrder(
            "PO-901", "003", "12.50", "usd",
            "2026-11-21T08:00:00Z",
            "retail", FieldText.explicitNull());
    }

    private static PartnerBOrder bOrder() {
        return new PartnerBOrder(
            "PO-901", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            1, FieldText.absent(), "CAMPAIGN-7");
    }

    @Test
    void sameBusinessMeaningPreservesDifferentSourceMetadata() {
        NormalizationResult a = service.fromA(
            new AEnvelope(aSource(), aOrder()));
        NormalizationResult b = service.fromB(
            new BEnvelope(bSource(), bOrder()));

        assertTrue(a.accepted());
        assertTrue(b.accepted());

        CanonicalOrder first = a.value();
        CanonicalOrder second = b.value();

        assertEquals(first.externalOrderId(),
                     second.externalOrderId());
        assertEquals(first.quantity(), second.quantity());
        assertEquals(first.unitPriceMinor(),
                     second.unitPriceMinor());
        assertEquals(first.currency(), second.currency());
        assertEquals(first.occurredAt(), second.occurredAt());
        assertEquals(first.channel(), second.channel());

        // Không xóa provenance chỉ để cho full DTO bằng nhau.
        assertNotEquals(first.source(), second.source());
        assertEquals(FieldState.EXPLICIT_NULL,
            first.note().state());
        assertEquals(FieldState.ABSENT,
            second.note().state());
    }

    @Test
    void unknownLegacyFieldProducesExplicitWarning() {
        NormalizationResult result = service.fromB(
            new BEnvelope(bSource(), bOrder()));

        assertTrue(result.accepted());
        assertTrue(result.issues().stream()
            .anyMatch(i ->
                i.code().equals("LEGACY_CAMPAIGN_NOT_MAPPED")
                && i.severity() == IssueSeverity.WARNING));
        assertEquals("raw/b-901", result.source().rawReference());
    }

    @Test
    void doesNotSilentlyRoundFractionalCents() {
        PartnerAOrder bad = new PartnerAOrder(
            "PO-902", "1", "12.345", "USD",
            "2026-11-21T08:00:00Z", "retail",
            FieldText.absent());

        NormalizationResult result = service.fromA(
            new AEnvelope(aSource(), bad));

        assertFalse(result.accepted());
        assertNull(result.value());
        assertEquals("PRICE_NOT_EXACT_MINOR_UNITS",
            result.issues().get(0).code());
    }

    @Test
    void rejectsUnknownChannelInsteadOfDefaulting() {
        PartnerBOrder bad = new PartnerBOrder(
            "PO-903", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            99, FieldText.absent(), null);

        NormalizationResult result = service.fromB(
            new BEnvelope(bSource(), bad));

        assertFalse(result.accepted());
        assertEquals("UNKNOWN_CHANNEL_CODE",
            result.issues().get(0).code());
    }

    @Test
    void refusesLostNotePresenceInformation() {
        PartnerAOrder bad = new PartnerAOrder(
            "PO-904", "2", "5.00", "USD",
            "2026-11-21T08:00:00Z", "retail", null);

        NormalizationResult result = service.fromA(
            new AEnvelope(aSource(), bad));

        assertFalse(result.accepted());
        assertEquals("NOTE_PRESENCE_NOT_CAPTURED",
            result.issues().get(0).code());
    }

    @Test
    void rejectsMismatchedSourceSchema() {
        SourceContext wrong = new SourceContext(
            "shop-a", "partner-b", "a-order-v1", "raw/wrong");

        NormalizationResult result = service.fromB(
            new BEnvelope(wrong, bOrder()));

        assertFalse(result.accepted());
        assertEquals("SOURCE_SCHEMA_MISMATCH",
            result.issues().get(0).code());
    }
}
~~~

### 15.1. Điều quan trọng trong test đầu

Nếu dùng `assertEquals(first, second)` rồi sửa code để bỏ `source` và `note` cho test qua, chính test đang **khuyến khích mất dữ liệu**. Câu hỏi đúng là:

> Những field nghiệp vụ nào cần tương đương, và những khác biệt provenance/optional-value nào **phải được giữ nguyên**?

Trong thực tế, một đơn Partner A và đơn Partner B có ID trông giống nhau cũng không nhất thiết là **cùng một đơn**; chỉ so sánh trường hợp ở phạm vi business fields đã thỏa contract.

### 15.2. Các test bổ sung bắt buộc

- `2026-11-21T15:00:00+07:00` và `2026-11-21T08:00:00Z` là cùng instant.
- Timestamp không có timezone/offset bị reject theo policy mẫu.
- Epoch seconds nhầm thành milliseconds không được âm thầm xem là một thời điểm hợp lệ.
- `qty="0"`, `qty="-1"`, `qty="999999999999999999999"` không được thành một quantity thành công.
- Giá âm, quá giới hạn hoặc decimal không thể biểu diễn exact minor units phải bị từ chối.
- Source schema version sai, unknown currency và unknown enum phải có error codes.
- `"note":null` khác missing note; parser có thể phải dùng JSON tree để bảo toàn.
- Hai tenant dùng cùng order ID không bị gộp nhầm trong dedup.
- Bản raw giữ được checksum và chỉ được đọc theo đúng principal.

## 16. Spring Integration integration test: accepted/rejected đi hai đường

Với `LossAwareNormalizerConfiguration`, kiểm thử output là canonical DTO hoặc rejection có mã; đặc biệt assert **rejected message không đến business branch**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(LossAwareNormalizerConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class LossAwareNormalizerFlowTest {

    @Autowired @Qualifier("normalizer.a.in")
    MessageChannel inA;

    @Autowired @Qualifier("normalizer.b.in")
    MessageChannel inB;

    @Autowired @Qualifier("orders.canonical.out")
    PollableChannel accepted;

    @Autowired @Qualifier("orders.quarantine.out")
    PollableChannel rejected;

    @Test
    void validPartnerAEntersCanonicalOutput() {
        SourceContext source = new SourceContext(
            "shop-a", "partner-a", "a-order-v1", "raw/a-901");

        PartnerAOrder order = new PartnerAOrder(
            "PO-901", "003", "12.50", "USD",
            "2026-11-21T08:00:00Z", "retail",
            FieldText.explicitNull());

        assertTrue(inA.send(MessageBuilder.withPayload(
            new AEnvelope(source, order)).build()));

        Message<?> out = accepted.receive(1000);
        assertNotNull(out);
        assertInstanceOf(CanonicalOrder.class, out.getPayload());

        CanonicalOrder canonical = (CanonicalOrder) out.getPayload();
        assertEquals(1250L, canonical.unitPriceMinor());
        assertEquals("partner-a", canonical.source().partnerId());
        assertEquals(FieldState.EXPLICIT_NULL,
            canonical.note().state());

        assertNull(rejected.receive(0));
    }

    @Test
    void badChannelIsRejectedWithNoCanonicalMessage() {
        SourceContext source = new SourceContext(
            "shop-a", "partner-b", "b-order-v2", "raw/b-bad");

        PartnerBOrder bad = new PartnerBOrder(
            "PO-902", 3, 1250, "USD",
            Instant.parse("2026-11-21T08:00:00Z")
                .toEpochMilli(),
            99, FieldText.absent(), null);

        assertTrue(inB.send(MessageBuilder.withPayload(
            new BEnvelope(source, bad)).build()));

        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);
        assertInstanceOf(
            NormalizationRejection.class,
            denied.getPayload());

        NormalizationRejection notice =
            (NormalizationRejection) denied.getPayload();

        assertEquals("raw/b-bad", notice.rawReference());
        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "UNKNOWN_CHANNEL_CODE".equals(issue.code())));

        assertNull(accepted.receive(0),
            "Unmappable source must not reach business output");
    }
}
~~~

**Giới hạn của integration test:** Đây là test trong một Spring context, chưa thử broker/Kafka/JMS, raw object store, authentication thực hay business transaction. `QueueChannel` và `DirectChannel` demo đồng bộ giúp assert không có message ở nhánh không chọn. Với ExecutorChannel/broker async, cần bounded await và đồng bộ hóa để kiểm chứng **không có side effect**, không chỉ dựa vào `receive(0)`.

### 16.1. Không chỉ assert rejection đã được gửi

Một Flow có bug có thể vừa phát rejection vừa gửi canonical sai sang handler. Test phải kiểm **negative path** và tốt hơn là dùng mock business handler hoặc kiểm database để chứng minh **zero mutations** khi normalization fail.

## 17. Golden mapping vectors và property-based tests

Một vài fixtures thành công không đủ phát hiện schema drift. Giữ một bộ **golden vectors** theo source/schema/mapping policy:

~~~text
A v1:
  qty="003", price="12.50", USD
  -> quantity=3, minor=1250, USD, ACCEPTED

A v1:
  qty="2", price="12.345", USD
  -> REJECT PRICE_NOT_EXACT_MINOR_UNITS

B v2:
  channelCode=99
  -> REJECT UNKNOWN_CHANNEL_CODE

B v2:
  legacyCampaignCode="CAMPAIGN-7"
  -> ACCEPTED + WARNING LEGACY_CAMPAIGN_NOT_MAPPED

A v1:
  note present=null
  -> note EXPLICIT_NULL

B v2:
  note missing
  -> note ABSENT
~~~

Có thể dùng property-based testing (ví dụ một công cụ generator phù hợp với JUnit) để kiểm những bất biến:

- Mọi quantity 1..500 trong source A parse sang đúng int.
- Giá major units có scale được phép → minor units không mất giá trị.
- Giá có phần lẻ minor units → không silently round.
- Timestamp ISO với các offset khác nhau nhưng cùng instant → output bằng nhau.
- Một ID nguồn không bị thay đổi case khi contract không cho phép.
- Unknown enums và schema version → không bao giờ accepted.
- Normalization không sinh commandId/operationId mới khi retry.
- Raw source hash/round-trip được kiểm theo phạm vi đúng.

### 17.1. Round-trip chỉ bảo đảm theo ngữ nghĩa được định nghĩa

Ví dụ:

~~~text
A source price "012.500" USD
   -> canonical unitPriceMinor=1250
   -> serialized source price "12.50"
~~~

Có thể đúng **giá trị nghiệp vụ**, nhưng không khôi phục **chuỗi byte ban đầu**. Nếu chữ ký, pháp lý, forensic hoặc replay yêu cầu chính xác raw bytes, phải lưu raw theo quyền và retention. Không lấy canonical JSON reserialized làm bằng chứng thay raw JSON ban đầu.

## 18. DLQ replay, mapping policy version và idempotency

Một message có thể được gửi lại sau nhiều ngày. Khi đó code/policy có thể đổi:

~~~text
Lần đầu:
  source schema = a-order-v1
  normalizer-policy-v1
  canonical-order-v1

DLQ replay:
  source schema = a-order-v1
  code currently deployed = normalizer-policy-v3
  canonical-order-v2
~~~

Cùng raw có thể cho ra giá trị khác nếu v3 đổi rounding, enum mapping, timezone hoặc defaulting. Chọn một trong các chiến lược rõ ràng:

1. **Pin policy version** cho execution khi cần tái lập quyết định.
2. **Re-normalize bằng rule mới** khi nghiệp vụ cho phép sửa mapping bug, với audit/migration.
3. **Migrate canonical v1 → v2** có kiểm soát, không trộn ngầm.
4. **Reconcile/manual review** nếu downstream đã commit side effect theo kết quả cũ.

### 18.1. Giữ business operation identity

Một retry/redelivery của cùng command không được sinh `commandId` mới trong normalizer. Nếu làm vậy, Idempotent Receiver tại downstream có thể coi lần thử mới là thao tác mới và trừ kho/charge lần hai.

- **Business operation key**: dùng để ngăn side effect trùng.
- **Execution ID/correlation**: dùng để gom đúng một lượt workflow.
- **Message ID/attempt**: thuộc transport/diagnostic, có thể đổi.
- **Raw reference**: dùng để đối chiếu source, không tự là idempotency key.

### 18.2. Retention phải phù hợp cửa sổ replay

Nếu broker/DLQ có thể replay sau 15 ngày nhưng raw store chỉ giữ 2 ngày, không được cam kết có thể re-normalize đầy đủ sau 15 ngày. Tương tự, nếu xóa ledger idempotency trước khi DLQ replay, nghiệp vụ có thể bị xử lý lặp. Cần phối hợp retention của **raw, metadata, idempotency state và broker**.

## 19. Normalizer trong flow Splitter–Aggregator

Một batch chứa nhiều đơn/dòng hàng có thể đi qua:

~~~mermaid
flowchart TD
    B["Batch from mixed sources"] --> S["Splitter"]
    S --> N["Normalizer A/B"]
    N --> D{"Mapping acceptable?"}
    D -->|"Có"| A["ItemOutcome NORMALIZED"]
    D -->|"Không"| R["ItemOutcome REJECTED + issue codes"]
    A --> G["Aggregator by executionId"]
    R --> G
    G --> O["BatchOutcome: accepted/rejected counts"]
~~~

**Không Filter-drop âm thầm một child không normalize được** nếu Aggregator đang đợi đủ `sequenceSize` hoặc tập child IDs. Nếu LINE-2 bị mất, Aggregator có thể giữ nhóm vô thời hạn hoặc timeout khó giải thích.

### 19.1. Phân biệt “đủ replies” và “toàn bộ được chấp nhận”

~~~text
Expected children: [LINE-1, LINE-2, LINE-3]
LINE-1 -> NORMALIZED
LINE-2 -> REJECTED (UNKNOWN_CHANNEL_CODE)
LINE-3 -> NORMALIZED

Aggregator received 3/3 child outcomes
Business result: 2 accepted, 1 rejected
~~~

Một group đủ ba outcomes **không** đồng nghĩa ba phần hợp lệ về business. Nếu contract là all-or-nothing, batch cần báo `FAILED` dù đã đầy đủ.

### 19.2. Duplicate và correlation

Một child có thể bị broker redeliver hai lần. Đừng coi hai message của `LINE-1` là hai child khác nhau. Dedupe theo `(executionId, childId)` hoặc một business key phù hợp. Idempotency của downstream side effects vẫn là lớp riêng, không được đánh đồng với group correlation.

## 20. Observability: phát hiện thông tin bị bỏ hoặc biến đổi

Một log `normalized=true` không thể giải thích dữ liệu đã mất.

| Metric/signal | Cần trả lời |
| --- | --- |
| Inbound count by partner/version | Ai gửi schema gì? |
| Unknown source/schema count | Có đối tác đổi format không báo? |
| Mapping accepted/rejected rate | Tỷ lệ chấp nhận thế nào? |
| Issue codes (warnings/errors) | Field nào đang bị bỏ/mất nghĩa? |
| Precision-loss rejected count | Có input cần rounding không cho phép? |
| Unknown enum/currency count | Có schema drift không? |
| Raw-store available/missing | Còn khả năng đối chiếu/reprocess không? |
| Quarantine oldest age/backlog | Có lỗi bị quên không xử lý? |
| DLQ re-normalization version changes | Replay có thể đổi kết quả không? |
| Business commit vs normalized count | Chấp nhận mapping có thực sự thành công nghiệp vụ? |

**Metric labels** nên dùng `partnerType`, `sourceSchemaVersion`, `issueCode` và endpoint với số giá trị hữu hạn. Không dùng `orderId`, `rawReference`, `tenantId` hoặc `executionId` làm time-series tags cardinality cao; thông tin cần thiết để debug nên ở log/trace được phân quyền.

### 20.1. Log có kiểm soát

~~~json
{
  "event": "normalization_rejected",
  "partner": "partner-b",
  "sourceSchemaVersion": "b-order-v2",
  "canonicalSchemaVersion": "canonical-order-v1",
  "issueCodes": ["UNKNOWN_CHANNEL_CODE"],
  "decision": "QUARANTINE"
}
~~~

Đây là schema log minh họa, **không** phải log Spring Integration có sẵn. Không log raw JSON, secrets, pre-signed URLs hoặc dữ liệu cá nhân chỉ để biết input lỗi.

## 21. Anti-pattern và cách tránh

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Map những field quen và âm thầm bỏ field lạ | Schema mới bị mất dữ liệu | Mapping contract + warning/error |
| `qty="abc"` thành 0 | Che lỗi nguồn | Reject typed code |
| Parse tiền bằng `double` | Mất độ chính xác | BigDecimal + exact minor |
| Sai major/minor units | Giá chênh 100 lần | Unit contract rõ theo source |
| Timestamp không offset bị ép UTC | Sai deadline/thời gian | Reject hoặc versioned zone policy |
| Epoch seconds đọc là milliseconds | Sai năm | Validate unit/range |
| Missing và null cùng Java null | Mất PATCH semantics | Preserve field presence trước mapper |
| Unknown enum → RETAIL | Route sai | Reject hoặc UNKNOWN có kiểm soát |
| Uppercase mọi order ID | Collision | Chỉ normalize theo field contract |
| Raw reference phát công khai | Rò dữ liệu | Authorization/projection |
| Lưu raw trong message header | Tăng payload và nguy cơ leak | Claim Check/storage bảo vệ |
| Lưu raw vô hạn | Vi phạm retention | Data minimization và expiry |
| Source/tenant header tự khai | Source spoofing | Trusted adapter context |
| Mọi exception thành mapping error | Technical failure không retry | Error channel riêng |
| Mapper tạo UUID operation mới mỗi attempt | Side effect trùng qua redelivery | Stable business key |
| Child invalid bị Filter drop | Aggregator chờ thiếu phần | Typed child rejection outcome |
| Test chỉ happy path | Miss loss/overflow/schema drift | Golden/property-based/negative tests |
| Canonical JSON được coi là raw ban đầu | Sai bằng chứng byte/signature | Lưu original bytes khi cần |

## 22. Checklist đưa Normalizer vào production

- [ ] Có mapping matrix cho từng source schema version, gồm field unknown.
- [ ] Phân biệt field required, optional, bảo mật, extension và field buộc reject.
- [ ] Chuẩn hóa số/tiền có đơn vị, precision, rounding và overflow policy rõ.
- [ ] Timestamp có timezone, epoch unit và precision theo contract.
- [ ] Missing, explicit null và empty string không bị gộp ngoài ý muốn.
- [ ] Enum unknown không bị gán một giá trị nghiệp vụ giả.
- [ ] Business IDs không bị đổi case/namespace tùy tiện.
- [ ] Trusted source context đến từ authentication/adapter, không phải body client.
- [ ] Có canonicalSchemaVersion, sourceSchemaVersion và normalizer policy version.
- [ ] Raw/provenance có retention và quyền đọc phù hợp nếu cần tái lập.
- [ ] Bất kỳ field quan trọng nào chưa map được đều dẫn đến rejection.
- [ ] Warning không trở thành “lỗ hổng” khiến downstream hiểu result là lossless.
- [ ] Mapping errors tách technical errors và domain/business-state errors.
- [ ] Rejected messages không tới handler thực hiện side effect.
- [ ] Giữ correlation/idempotency key qua Transformer và transport mapping.
- [ ] Splitter/Aggregator nhận cả typed child rejection outcomes.
- [ ] Có unit tests, integration tests, schema contract và negative tests.
- [ ] Quan sát unknown field, price precision errors và schema drift mới.
- [ ] Không log raw PII/tokens hoặc dùng IDs tự do làm metric tags.
- [ ] Có runbook để xử lý quarantine, mapping migration, DLQ replay.

## 23. Bài tập vận dụng

Một hệ thống giao nhận nhận thông tin kiện hàng từ ba carrier.

**Carrier A:** cân nặng kilogram dưới dạng decimal; kích thước centimet; thời gian ISO có offset; `fragile:null`:

~~~json
{
  "shipment_id": "SHP-18",
  "weight_kg": "1.250",
  "length_cm": "30.0",
  "width_cm": "20.0",
  "height_cm": "10.0",
  "event_at": "2026-11-21T15:00:00+07:00",
  "fragile": null
}
~~~

**Carrier B:** cân nặng gram, kích thước millimetres, epoch milliseconds; không có `fragile`:

~~~json
{
  "shipmentId": "SHP-18",
  "weightGrams": 1250,
  "lengthMm": 300,
  "widthMm": 200,
  "heightMm": 100,
  "eventEpochMs": 1795248000000
}
~~~

**Carrier C:** có thêm `temperatureControlClass` mà canonical schema hiện chưa biểu diễn. Một số sản phẩm bắt buộc phân loại này để chọn kho lạnh.

**Yêu cầu:**

1. Lập mapping matrix cho A/B/C, chỉ rõ field cần giữ và field không map được.
2. Thiết kế canonical `Shipment` với đơn vị khối lượng, chiều dài và thời gian chuẩn.
3. Chuyển `kg → grams`, `cm → millimetres` bằng BigDecimal/exact conversion; khi nào phải reject thay vì round?
4. Phân biệt explicit null của A và absent của B cho `fragile`.
5. Chọn chính sách cho `temperatureControlClass`: warning, reject, extension hay nâng schema? Vì sao nếu ảnh hưởng điều kiện bảo quản thì phải reject trước route?
6. Tách `tenantId`, `carrierId`, `sourceSchemaVersion` và raw reference thành trusted context.
7. Viết `NormalizerService` và `NormalizationResult` có error/warning codes.
8. Xây Java DSL gồm Router, Transformers cho A/B/C, typed accepted/rejected channels.
9. Tạo golden tests chứng minh hai carriers tương đương về mass/dimensions/instant nhưng khác provenance.
10. Kiểm tra overflow, epoch-unit mistake, unknown enum và null/absent.
11. Nếu một child không normalize được trong batch 100 kiện, phát `ShipmentRejected` để Aggregator không chờ mãi.
12. Thiết kế retention, ACL và checksum cho raw store nếu cần replay.
13. Giải thích vì sao không được tạo commandId mới mỗi lần normalize lại message từ DLQ.
14. Đề xuất metrics/alert cho schema drift, precision loss, quarantine backlog và raw-reference failures.

**Gợi ý:** Mục tiêu không chỉ là làm JSON giống nhau mà là giữ **cùng một ý nghĩa**; điều gì chưa thể biểu diễn thì phải có quyết định nghiệp vụ, bằng chứng và đường xử lý rõ ràng.

## 24. Tổng kết

**Tránh làm mất dữ liệu khi chuẩn hóa** là nhiệm vụ cốt lõi khi xây Normalizer cho nhiều nguồn. Router chọn Translator theo nguồn/schema đáng tin, còn Transformer đổi biểu diễn về canonical model. Nhưng code chuyển đổi thành công **không chứng minh kết quả bảo toàn ý nghĩa**: missing và null, rounding tiền, timezone, enum, ID namespace, raw field và metadata có thể mất hoặc bị bóp méo âm thầm.

Một thiết kế bền vững cần **mapping contract, schema/policy version, typed warnings/errors, numeric/time conversion chính xác, trusted source context và tuyến accepted/rejected rõ ràng**. Khi có nhu cầu audit/replay, raw reference hoặc Claim Check giúp đối chiếu trong phạm vi quyền và retention hợp lệ; nó không thay thế authorization hay quyết định bảo mật. Kết hợp Spring Integration Java DSL, Router, Transformer, Filter, Gateway, Splitter/Aggregator, retry/error channel, correlation và idempotency với kiểm thử unit/integration/contract để bảo đảm message được chuẩn hóa **đúng nghĩa, có khả năng giải thích và không tạo side effect sai**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Normalizer, Message Translator, Content-Based Router, Claim Check, Correlation Identifier); Spring Integration Reference về Transformers, Routers, Java DSL, Message Channels, Claim Check, Error Handling, Testing; Java SE về `BigDecimal`, `Instant`, `Locale.ROOT`, `Math.multiplyExact` và records; tài liệu về data contracts/schema evolution.





