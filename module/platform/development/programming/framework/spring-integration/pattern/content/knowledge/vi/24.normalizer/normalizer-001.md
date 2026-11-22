# Normalizer chuyển nhiều định dạng về một biểu diễn chung

## 1. Bài toán: ba đối tác gửi cùng một loại thông tin theo ba cách khác nhau

Trong chương **Normalizer** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng. Khi kết nối Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, một câu hỏi quan trọng xuất hiện ngay từ đầu: **nếu các nguồn gửi dữ liệu cùng ý nghĩa nhưng cấu trúc khác nhau, mọi xử lý phía sau có phải hiểu từng cấu trúc đó không?**

Giả sử hệ thống nhận thông tin đơn hàng đã thanh toán từ ba nguồn:

- Hệ thống **ERP** gửi JSON phiên bản cũ, dùng trường `orderNo`, `grossAmountVnd`, `submittedAtIso`, trạng thái `PAID`.
- **Marketplace** gửi JSON phiên bản mới, dùng `purchaseRef`, `amountMinor`, `currencyCode`, thời gian epoch milliseconds và trạng thái `SETTLED`.
- Một đối tác truyền **CSV** với các cột `order_key`, `amount_decimal`, `currency`, `occurred_at`, trạng thái `PAYMENT_COMPLETE`.

Ba payload có cùng thông điệp nghiệp vụ: “đơn hàng X đã thanh toán số tiền Y tại thời điểm Z”. Nhưng nếu Handler, Aggregator và báo cáo cần biết cả ba schema, mỗi lần thêm đối tác phải sửa hàng loạt nơi.

~~~mermaid
flowchart LR
    A["ERP JSON v1"] --> R["Message Router"]
    B["Marketplace JSON v2"] --> R
    C["CSV upload"] --> R
    R --> T1["ERP Translator"]
    R --> T2["Marketplace Translator"]
    R --> T3["CSV Translator"]
    T1 --> N["CanonicalOrder"]
    T2 --> N
    T3 --> N
    N --> V["Validate common contract"]
    V --> F["Router / Aggregator / business flow"]
~~~

**Normalizer** là pattern giúp tất cả nguồn đi qua những phép chuyển đổi riêng, rồi hội tụ về **một cấu trúc nội bộ thống nhất**. Nó không chỉ đổi tên trường: việc diễn giải tiền tệ, múi giờ, trạng thái, định danh và độ tin cậy của dữ liệu phải theo một hợp đồng chung.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Normalizer theo EIP và phân biệt nó với một Transformer đơn lẻ.
2. Phân biệt **parse/decode**, **normalize về schema chung**, **validate** và **enrich**.
3. Xác định **canonical model** có kiểu, đơn vị và ngữ nghĩa rõ ràng.
4. Dùng Router để chọn Transformer theo nguồn hoặc loại payload, thay vì viết một khối `if/else` lan khắp hệ thống.
5. Xây dựng ví dụ Java 17 + Spring Integration Java DSL cho ERP, marketplace và CSV.
6. Bảo vệ tenant/source identity, business correlation, eventId và trace metadata khi đi qua normalizer.
7. Xử lý dữ liệu lỗi, schema lạ, duplicate, retry, DLQ và quarantine mà không làm mất event.
8. Viết unit test và integration test để chứng minh ba định dạng tạo một output contract chung.

## 2. Định nghĩa Normalizer theo Enterprise Integration Patterns

Theo [Enterprise Integration Patterns — Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html), nếu nhiều nguồn gửi những message **tương đương về ngữ nghĩa** nhưng có **định dạng khác nhau**, ta có thể:

1. Dùng **Message Router** nhận biết loại thông điệp.
2. Đưa từng loại vào **Message Translator** phù hợp.
3. Yêu cầu mọi Translator tạo **cùng một định dạng chung**.
4. Đưa các thông điệp đã chuẩn hóa về một luồng xử lý thống nhất.

~~~text
Source A format ──> Translator A ──┐
Source B format ──> Translator B ──┤──> Canonical format
Source C format ──> Translator C ──┘
             ↑
      Message Router chọn nhánh
~~~

Spring Integration có các thành phần **Router**, **Transformer**, **Channel**, **Service Activator**, **Filter** và DSL để hiện thực pattern này. **Không cần giả định có một endpoint riêng mang tên `Normalizer`** mà framework tự chuyển đổi tất cả định dạng. Đây là **một bố cục pattern**, không phải lời hứa framework tự hiểu ngữ nghĩa của dữ liệu đối tác.

### 2.1. Normalizer khác Transformer như thế nào?

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Parser / MessageConverter** | Biến bytes hoặc JSON/XML/CSV thành cấu trúc đọc được | `byte[]` → `ErpOrderV1` |
| **Router** | Chọn nhánh xử lý đúng loại | `VerifiedErpOrder` → `erpOrders` |
| **Transformer** | Chuyển một loại input sang một loại output | `ErpOrderV1` → `CanonicalOrder` |
| **Normalizer** | Phối hợp router và nhiều translator cho một contract chung | ERP, marketplace, CSV → `CanonicalOrder` |
| **Filter** | Chặn/loại message theo tiêu chí | Loại event không đủ quyền hoặc chưa hợp lệ |
| **Aggregator** | Gom nhiều messages liên quan thành một kết quả | Ba `CanonicalOrder` outcomes → một report |
| **Enricher** | Bổ sung thông tin từ nguồn khác | Map external customer ID → trusted internal ID |

Một Transformer có thể đã là toàn bộ giải pháp nếu chỉ có một input format. Khi nhiều format tương đương cần vào **cùng downstream contract**, bố cục Normalizer trở nên hữu ích.

### 2.2. Chuẩn hóa không phải biến mọi nguồn thành cùng giá trị

Ba nguồn có thể tạo cùng **kiểu** `CanonicalOrder` nhưng dữ liệu khác nhau: tenant, sourceEventId, externalOrderId, tiền tệ và thời gian sự kiện vẫn giữ giá trị đúng của mỗi nguồn. **Cùng biểu diễn** nghĩa là các trường, kiểu, đơn vị, semantics và validation thống nhất; không phải ép mọi đơn vào một mã đơn hoặc một currency.

Ví dụ:

| Nguồn | Input tổng tiền | Output chuẩn |
| --- | --- | --- |
| ERP | `"150000"` VND | `Money(150000, VND)` |
| Marketplace | `1235` minor units USD | `Money(12.35, USD)` |
| CSV | `"89.90"` USD | `Money(89.90, USD)` |

Nếu có hai đơn USD và VND, Normalizer không được tự cộng các số tiền thô như thể chúng cùng đơn vị. Việc đổi tiền tệ (FX) là một quy tắc nghiệp vụ độc lập, cần rate/nguồn rate/timestamp/rounding rõ ràng.

## 3. Chuỗi xử lý từ wire bytes tới sự kiện canonical

Các adapter khác nhau có thể mang HTTP JSON, JMS byte payload, AMQP message, file CSV hoặc XML. Một pipeline nên tách các ranh giới:

~~~mermaid
flowchart TD
    W["Wire bytes / payload"] --> P["Parse + schema selection"]
    P --> S["Authenticate & verify source"]
    S --> R["Route by verified source/type"]
    R --> T["Format-specific Transformer"]
    T --> C["CanonicalOrder"]
    C --> V["Common validation"]
    V --> D["Business downstream"]
    P -.-> E["Malformed → quarantine"]
    S -.-> E
    R -.-> E
    T -.-> E
    V -.-> E
~~~

**Các lớp trách nhiệm:**

- **Adapter/Parser:** giải mã protocol, charset, JSON/XML/CSV schema, giới hạn size. Không tự quyết định nghiệp vụ đã thanh toán hay chưa.
- **Trust boundary:** xác minh nguồn/tenant, quyền gửi event và schema mà nguồn được phép phát.
- **Router:** chọn đúng translator; không đoán từ những trường không đáng tin khi có thể dùng identity đã xác minh.
- **Translator:** thực hiện mapping trường, đổi kiểu, chuẩn hóa timezone, money units, enum/status.
- **Canonical validator:** kiểm tra các invariant áp dụng cho **mọi nguồn**, không chỉ riêng ERP.
- **Downstream:** xử lý trên một kiểu CanonicalOrder thống nhất, không chứa `if (source == ERP) ...` trừ khi đó là một quy tắc nghiệp vụ có chủ đích.

### 3.1. Vì sao nên parse trước khi route?

Khi input đã là Java DTO có kiểu, **PayloadTypeRouter** dễ chọn nhánh. Nhưng nếu mọi adapter đưa một `String` JSON vào channel chung, route theo `payload.getClass()` sẽ chỉ thấy `String`, không biết ERP hay marketplace.

Có ba phương án an toàn:

1. **Adapter riêng** decode schema riêng thành DTO có kiểu rồi route theo payload class.
2. **Envelope có `sourceSystem/schemaVersion`** đã kiểm chứng tại ingress, rồi route theo metadata tin cậy.
3. **Content-based routing** sau bước nhận dạng schema an toàn, có versioned contract và validation chặt.

Đừng chỉ tìm một substring như `"orderNo"` trong raw JSON để đoán schema. Field có thể nằm ở nested object, bị escape, hoặc bị producer khác cố ý thêm. Dùng parser/schema registry và nguồn đã xác thực.

### 3.2. Vì sao không parse CSV bằng `split(",")`?

CSV cho phép quoted fields, dấu phẩy bên trong giá trị, dòng xuống trong chuỗi và escaping. `String.split(",")` là phản ví dụ không an toàn cho CSV tổng quát.

Trong hệ thống thật, dùng thư viện parser có hỗ trợ CSV dialect, encoding, BOM và giới hạn kích thước, sau đó map từng dòng thành DTO. Ví dụ của bài dùng **DTO đã được parser tạo**, không giả vờ rằng Java `split` là bộ parser đúng cho mọi CSV.

## 4. Thiết kế canonical model trước khi viết translator

Canonical model là **hợp đồng giữa phía tích hợp và phía nghiệp vụ**. Nó cần rõ ràng đủ để mọi downstream hiểu một lần.

| Thuộc tính | Ý nghĩa | Invariant |
| --- | --- | --- |
| `tenantId` | Tenant đã xác minh | Không rỗng, không đến từ HTTP header tự do |
| `sourceSystem` | Hệ thống phát event đã xác minh | Giá trị allowlisted |
| `sourceEventId` | Logical event ID phục vụ dedup | Ổn định khi redelivery |
| `externalOrderId` | Mã đơn theo hợp đồng nguồn | Có namespace nguồn/tenant nếu cần |
| `status` | Trạng thái có kiểu chung | Chỉ mapping hợp lệ, không tự “thành công” khi unknown |
| `Money` | Số tiền và currency | Không âm, precision đúng currency |
| `occurredAt` | Thời điểm sự kiện | `Instant` UTC đã parse đúng zone |
| `schemaVersion` | Version của canonical contract | Có thể phát triển schema có kiểm soát |

Một số lựa chọn thiết kế:

- Dùng **record bất biến** và `BigDecimal` cho tiền, không dùng `double`.
- Dùng **`Instant`** cho thời điểm tuyệt đối; nếu nguồn gửi local time phải có **ZoneId cụ thể**.
- Giữ **sourceEventId** và **sourceSystem** để trace và dedup.
- Không hủy raw event trước khi đã lưu/quarantine theo retention và yêu cầu riêng tư.
- Không nhét toàn bộ JSON/XML raw vào canonical record chỉ để khỏi viết mapper; raw payload nên nằm ở lưu trữ có kiểm soát nếu thật sự cần.
- Chỉ tạo schemaVersion mới khi contract có thay đổi rõ, tránh đồng nghĩa version với application build.

### 4.1. Schema chung và tính tương thích

Một field mới như `taxIncluded` hoặc `pricingBasis` có thể là **optional** đối với dữ liệu lịch sử nhưng bắt buộc đối với nghiệp vụ mới. Cần quy tắc:

- Field nào bắt buộc, field nào nullable/optional, field nào có default hợp lệ?
- Nếu nguồn không có dữ liệu, trả **UNKNOWN** có chủ đích hay reject?
- Khi đổi đơn vị, có migrate cả stored events và consumers không?
- Khi enum xuất hiện giá trị mới, mapper có fail closed hay tự chọn fallback?

Một “canonical schema” chỉ hữu ích nếu mọi producer/translators và downstream **đồng ý về ngữ nghĩa**, không chỉ tên trường giống nhau.

## 5. Ví dụ đầu vào của ba nguồn

Trong chương này, adapter đã parse JSON/CSV và xác minh source, rồi tạo các **typed input records**. Để bài có thể kiểm thử mà không cần broker ngoài, ta mô phỏng đúng điểm ngay **sau inbound parser và trust validation**.

### 5.1. ERP JSON v1

~~~json
{
  "eventId": "evt-erp-101",
  "orderNo": "ERP-101",
  "grossAmountVnd": "150000",
  "submittedAtIso": "2026-11-01T08:30:00Z",
  "paymentState": "PAID"
}
~~~

### 5.2. Marketplace JSON v2

~~~json
{
  "evt": "evt-market-202",
  "purchaseRef": "MK-202",
  "amountMinor": 1235,
  "currencyCode": "USD",
  "eventTimeEpochMillis": 1793521800000,
  "state": "SETTLED"
}
~~~

`amountMinor=1235` với USD (hai chữ số thập phân) là **12.35 USD**, không phải 1.235 USD hoặc 1235 USD. Với VND, số chữ số thập phân theo `Currency` là 0. Không hard-code mọi currency đều có hai chữ số sau dấu thập phân.

### 5.3. CSV

~~~csv
event_id,order_key,amount_decimal,currency,occurred_at,state
evt-csv-303,CSV-303,89.90,USD,2026-11-01T08:30:00Z,PAYMENT_COMPLETE
~~~

Đây là một CSV dialect có cột `occurred_at` ở định dạng ISO-8601 UTC và `amount_decimal` dùng dấu chấm. Nếu file thực tế dùng `1.234,50` hoặc `dd/MM/yyyy HH:mm`, cần parser/cấu hình locale/timezone **riêng**; không dùng một phép thay dấu phẩy chung cho tất cả đối tác.

## 6. Java 17: ba loại input đã xác minh và một output chung

Thay vì để Translator tin các trường sourceId/tenantId do đối tác tự ghi trong JSON, lớp ingress sẽ tạo một **TrustedSource** từ principal, certificate, broker ACL hoặc cấu hình adapter đã xác minh.

### 6.1. Nguồn tin cậy và raw DTOs

~~~java
enum SourceSystem {
    ERP,
    MARKETPLACE,
    CSV_UPLOAD
}

record TrustedSource(
        String tenantId,
        String partnerId,
        SourceSystem system) {

    TrustedSource {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")
                || partnerId == null
                || !partnerId.matches("[A-Za-z0-9_-]{1,64}")
                || system == null) {
            throw new IllegalArgumentException("INVALID_TRUSTED_SOURCE");
        }
    }
}

record ErpOrderV1(
        String eventId,
        String orderNo,
        String grossAmountVnd,
        String submittedAtIso,
        String paymentState) {
}

record MarketplaceOrderV2(
        String evt,
        String purchaseRef,
        long amountMinor,
        String currencyCode,
        long eventTimeEpochMillis,
        String state) {
}

record CsvOrderRow(
        String eventId,
        String orderKey,
        String amountDecimal,
        String currencyCode,
        String occurredAtIso,
        String state) {
}
~~~

**Tên `TrustedSource` không tự tạo tính đáng tin.** Chỉ code tại trust boundary có quyền tạo record đó sau khi authentication/authorization và partner mapping hoàn tất. Các ví dụ unit test tạo record trực tiếp để cô lập phần normalizer, **không kiểm chứng bảo mật của HTTP/JMS adapter**.

Không dùng một record “universal raw order” chứa 20 nullable fields rồi buộc downstream phải đoán field nào có ý nghĩa. **Mỗi schema nguồn có kiểu riêng** để lỗi version/mapping xuất hiện tại translator tương ứng.

### 6.2. Wrapper đã xác minh để Router nhìn thấy payload type

~~~java
sealed interface VerifiedIncomingOrder
        permits VerifiedErpOrder,
                VerifiedMarketplaceOrder,
                VerifiedCsvOrder {
    TrustedSource source();
}

record VerifiedErpOrder(
        TrustedSource source,
        ErpOrderV1 body) implements VerifiedIncomingOrder {
}

record VerifiedMarketplaceOrder(
        TrustedSource source,
        MarketplaceOrderV2 body) implements VerifiedIncomingOrder {
}

record VerifiedCsvOrder(
        TrustedSource source,
        CsvOrderRow body) implements VerifiedIncomingOrder {
}
~~~

Ví dụ `VerifiedErpOrder` chỉ được tạo sau khi adapter đã xác minh message đến từ hệ thống ERP; input JSON **không thể tự lựa chọn** `source.system()` mà chưa qua ranh giới tin cậy.

### 6.3. Canonical types

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

enum CanonicalOrderStatus {
    PAID,
    CANCELLED,
    PENDING
}

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        int digits = currency.getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_CURRENCY_FRACTION_DIGITS");
        }

        // Không làm tròn dữ liệu sai precision một cách âm thầm.
        amount = amount.setScale(digits, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("NEGATIVE_ORDER_AMOUNT");
        }
    }
}

record CanonicalOrder(
        int canonicalSchemaVersion,
        String tenantId,
        String partnerId,
        SourceSystem sourceSystem,
        String sourceEventId,
        String externalOrderId,
        CanonicalOrderStatus status,
        Money total,
        Instant occurredAt) {

    CanonicalOrder {
        if (canonicalSchemaVersion != 1
                || tenantId == null
                || partnerId == null
                || sourceSystem == null
                || sourceEventId == null
                || sourceEventId.isBlank()
                || externalOrderId == null
                || externalOrderId.isBlank()
                || status == null
                || total == null
                || occurredAt == null) {
            throw new IllegalArgumentException(
                    "INVALID_CANONICAL_ORDER");
        }
    }
}
~~~

**Điều `Money` giải quyết:** chỉ có một kiểu biểu diễn số tiền trong hệ thống; số chữ số thập phân được kiểm soát theo `Currency`. Ví dụ `new Money(new BigDecimal("89.999"), USD)` bị từ chối thay vì tự làm tròn 90.00. Nếu domain cần mức chính xác khác chuẩn tiền tệ (ví dụ tỷ giá hoặc đơn giá theo khối lượng), nên có kiểu **Rate/UnitPrice riêng**, không nới lỏng Money một cách không rõ ràng.

**Điều `CanonicalOrder` giải quyết:** downstream nhìn thấy một trường `status` có enum, một `Money`, một `Instant` và identity rõ. Nó không cần biết ERP lưu tiền thành chuỗi, marketplace gửi minor units hay CSV dùng ISO timestamp.

## 7. Translator theo schema nguồn: một trách nhiệm cho mỗi nhánh

Các hàm sau nhận typed input đã xác minh và trả `CanonicalOrder` **không null**. Trong Spring Integration, Transformer không phải Filter: một phép biến đổi không thể tự trả null để có nghĩa “bỏ qua event”.

### 7.1. Hàm kiểm tra chung cho Translator

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;

final class PurchaseOrderNormalizer {

    private static String requiredId(
            String value,
            String field) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{1,96}")) {
            throw new IllegalArgumentException(
                    "INVALID_" + field);
        }
        return value;
    }

    private static Currency supportedCurrency(String code) {
        if (code == null || !java.util.Set.of(
                "VND", "USD").contains(code)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_CURRENCY");
        }
        return Currency.getInstance(code);
    }

    private static BigDecimal decimal(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("MISSING_AMOUNT");
        }
        try {
            return new BigDecimal(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "INVALID_AMOUNT_FORMAT", ex);
        }
    }

    private static Instant isoInstant(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("MISSING_EVENT_TIME");
        }
        try {
            return Instant.parse(text);
        } catch (java.time.format.DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "INVALID_EVENT_TIME", ex);
        }
    }

    private static void requireSource(
            TrustedSource source,
            SourceSystem expected) {
        if (source == null || source.system() != expected) {
            throw new SecurityException("SOURCE_SCHEMA_MISMATCH");
        }
    }

    private static CanonicalOrder canonical(
            TrustedSource source,
            String eventId,
            String orderId,
            Money total,
            Instant occurredAt,
            CanonicalOrderStatus status) {

        return new CanonicalOrder(
                1,
                source.tenantId(),
                source.partnerId(),
                source.system(),
                requiredId(eventId, "EVENT_ID"),
                requiredId(orderId, "ORDER_ID"),
                status,
                total,
                occurredAt);
    }

    // Ba hàm format-specific được bổ sung bên dưới.
}
~~~

**Lưu ý:** các đoạn code trong bài được chia thành nhiều khối để giải thích. Ba phương thức tiếp theo thuộc **cùng lớp `PurchaseOrderNormalizer`** ở trên; khi đưa vào source file thực tế, hãy đặt chúng bên trong thân lớp, trước dấu `}` cuối, không khai báo lớp trùng.

### 7.2. ERP: parse số tiền VND và ISO timestamp

~~~java
// Phương thức bên trong PurchaseOrderNormalizer.
CanonicalOrder fromErp(VerifiedErpOrder input) {
    requireSource(input.source(), SourceSystem.ERP);
    ErpOrderV1 raw = java.util.Objects.requireNonNull(
            input.body(), "erp body");

    CanonicalOrderStatus status = switch (raw.paymentState()) {
        case "PAID"      -> CanonicalOrderStatus.PAID;
        case "CANCELLED" -> CanonicalOrderStatus.CANCELLED;
        case "PENDING"   -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_ERP_PAYMENT_STATE");
    };

    return canonical(
            input.source(),
            raw.eventId(),
            raw.orderNo(),
            new Money(
                    decimal(raw.grossAmountVnd()),
                    supportedCurrency("VND")),
            isoInstant(raw.submittedAtIso()),
            status);
}
~~~

Những giá trị như `"150000"` có thể parse trực tiếp; `"150,000"` phải bị từ chối nếu **hợp đồng ERP quy định chuỗi decimal không có dấu phân cách**. Đừng tự xóa dấu phẩy khi chưa biết dấu đó là phân tách hàng nghìn hay phần thập phân.

### 7.3. Marketplace: chuyển minor units sang decimal

~~~java
// Phương thức bên trong PurchaseOrderNormalizer.
CanonicalOrder fromMarketplace(VerifiedMarketplaceOrder input) {
    requireSource(input.source(), SourceSystem.MARKETPLACE);
    MarketplaceOrderV2 raw = java.util.Objects.requireNonNull(
            input.body(), "marketplace body");

    Currency currency = supportedCurrency(raw.currencyCode());
    int digits = currency.getDefaultFractionDigits();

    CanonicalOrderStatus status = switch (raw.state()) {
        case "SETTLED"  -> CanonicalOrderStatus.PAID;
        case "CANCELED" -> CanonicalOrderStatus.CANCELLED;
        case "PENDING"  -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_MARKETPLACE_STATE");
    };

    return canonical(
            input.source(),
            raw.evt(),
            raw.purchaseRef(),
            new Money(
                    BigDecimal.valueOf(raw.amountMinor(), digits),
                    currency),
            Instant.ofEpochMilli(raw.eventTimeEpochMillis()),
            status);
}
~~~

Với USD, `BigDecimal.valueOf(1235L, 2)` tạo 12.35. Với VND, `BigDecimal.valueOf(150000L, 0)` tạo 150000. Đây là phép chuyển đơn vị chính xác vì `minorUnits` theo contract là **số nguyên**; nó không phải một tỷ giá và không cần `double`.

### 7.4. CSV: parse decimal theo dialect đã khai báo

~~~java
// Phương thức bên trong PurchaseOrderNormalizer.
CanonicalOrder fromCsv(VerifiedCsvOrder input) {
    requireSource(input.source(), SourceSystem.CSV_UPLOAD);
    CsvOrderRow raw = java.util.Objects.requireNonNull(
            input.body(), "csv row");

    CanonicalOrderStatus status = switch (raw.state()) {
        case "PAYMENT_COMPLETE" -> CanonicalOrderStatus.PAID;
        case "ORDER_CANCELLED"  -> CanonicalOrderStatus.CANCELLED;
        case "AWAITING_PAYMENT" -> CanonicalOrderStatus.PENDING;
        default -> throw new IllegalArgumentException(
                "UNKNOWN_CSV_STATE");
    };

    return canonical(
            input.source(),
            raw.eventId(),
            raw.orderKey(),
            new Money(
                    decimal(raw.amountDecimal()),
                    supportedCurrency(raw.currencyCode())),
            isoInstant(raw.occurredAtIso()),
            status);
}
~~~

Nếu CSV `amount_decimal` chứa chuỗi trống hoặc giá trị `"NaN"`, phép parse phải từ chối. Không convert một số tiền không hợp lệ thành 0, vì điều đó biến **lỗi dữ liệu** thành **giao dịch giá trị 0**.

### 7.5. Hợp nhất không xóa dấu vết của nguồn

Kết quả của ba translator đều có kiểu `CanonicalOrder` nhưng vẫn chứa:

~~~text
tenantId
partnerId
sourceSystem
sourceEventId
externalOrderId
status
total
occurredAt
canonicalSchemaVersion
~~~

Thông tin này cần thiết cho dedup, đối soát và routing nghiệp vụ sau normalizer. **Đừng tự làm mất source identity** chỉ vì “downstream không cần quan tâm định dạng”; không quan tâm **cấu trúc của nguồn** khác với đánh mất **nguồn gốc dữ liệu**.

## 8. Java DSL: Router theo payload type, ba Translator, một canonical channel

Spring Integration cung cấp **PayloadTypeRouter** hoặc Java DSL route theo class của payload. Sau khi adapter đã xác minh và wrap payload bằng `VerifiedErpOrder`, `VerifiedMarketplaceOrder` hoặc `VerifiedCsvOrder`, Router có thể chọn nhánh không cần parse raw JSON lần thứ hai.

~~~mermaid
flowchart TD
    I["verifiedIncomingOrders"] --> R{"Payload type Router"}
    R -->|"VerifiedErpOrder"| E["erpOrders"]
    R -->|"VerifiedMarketplaceOrder"| M["marketplaceOrders"]
    R -->|"VerifiedCsvOrder"| C["csvOrders"]
    R -->|"Unknown type"| Q["unknownFormatOrders"]
    E --> TE["fromErp"]
    M --> TM["fromMarketplace"]
    C --> TC["fromCsv"]
    TE --> N["canonicalOrders"]
    TM --> N
    TC --> N
    N --> V["CommonOrderPolicy"]
    V --> O["canonicalOutput"]
~~~

### 8.1. Common policy sau khi normalize

~~~java
final class CommonOrderPolicy {

    CanonicalOrder requireValid(CanonicalOrder order) {
        if (order == null || order.canonicalSchemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "INVALID_CANONICAL_SCHEMA");
        }

        // Đây là chính sách riêng của ví dụ:
        // PAID cần số tiền dương.
        if (order.status() == CanonicalOrderStatus.PAID
                && order.total().amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "PAID_ORDER_REQUIRES_POSITIVE_AMOUNT");
        }

        return order;
    }
}
~~~

**Lưu ý nghiệp vụ:** có hệ thống cho phép đơn miễn phí có giá 0. Chính sách ở trên chỉ minh họa cách đặt **invariant chung** vào một nơi. Nếu đơn miễn phí hợp lệ, cần model/phân loại riêng, không mặc định coi mọi paid event amount=0 là lỗi.

### 8.2. Cấu hình các channels và Router

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class NormalizerFlowConfig {

    @Bean
    PurchaseOrderNormalizer purchaseOrderNormalizer() {
        return new PurchaseOrderNormalizer();
    }

    @Bean
    CommonOrderPolicy commonOrderPolicy() {
        return new CommonOrderPolicy();
    }

    @Bean
    MessageChannel verifiedIncomingOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel erpOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel marketplaceOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel csvOrders() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel canonicalOrders() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel canonicalOutput() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel unknownFormatOrders() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow verifiedOrdersRouter() {
        return IntegrationFlow.from("verifiedIncomingOrders")
                .<Object, Class<?>>route(Object::getClass, router -> router
                        .channelMapping(
                                VerifiedErpOrder.class, "erpOrders")
                        .channelMapping(
                                VerifiedMarketplaceOrder.class,
                                "marketplaceOrders")
                        .channelMapping(
                                VerifiedCsvOrder.class, "csvOrders")
                        .defaultOutputChannel("unknownFormatOrders"))
                .get();
    }

    @Bean
    IntegrationFlow erpNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("erpOrders")
                .transform(
                        VerifiedErpOrder.class,
                        normalizer::fromErp)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow marketplaceNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("marketplaceOrders")
                .transform(
                        VerifiedMarketplaceOrder.class,
                        normalizer::fromMarketplace)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow csvNormalization(
            PurchaseOrderNormalizer normalizer) {
        return IntegrationFlow.from("csvOrders")
                .transform(
                        VerifiedCsvOrder.class,
                        normalizer::fromCsv)
                .channel("canonicalOrders")
                .get();
    }

    @Bean
    IntegrationFlow commonCanonicalValidation(
            CommonOrderPolicy policy) {
        return IntegrationFlow.from("canonicalOrders")
                .transform(
                        CanonicalOrder.class,
                        policy::requireValid)
                .channel("canonicalOutput")
                .get();
    }
}
~~~

Đây là cấu hình Java DSL hướng tới các bản Spring Integration hiện đại (6.x/7.x). Các DTO/Translator ở phần trước cần được đặt trong cùng module/package import được. **Chưa có Kafka/HTTP adapter thật trong đoạn này**: `verifiedIncomingOrders` được xem là ranh giới **sau** bước xác minh nguồn và parse schema.

### 8.3. Vì sao có nhiều IntegrationFlow thay vì một flow dài?

Router rẽ message vào ba channel riêng. Mỗi sub-flow sở hữu đúng một Translator. Sau khi tạo CanonicalOrder, các nhánh hội tụ về `canonicalOrders` và chạy **cùng một CommonOrderPolicy**.

Nhờ vậy:

- Đổi cấu trúc ERP không cần sửa Marketplace translator.
- Thêm nguồn XML mới chủ yếu thêm **parser + verified DTO + route mapping + translator**.
- Business downstream không cần thêm `switch(sourceSystem)` để diễn giải các trường cơ bản.
- Có thể đo latency/error-rate cho từng translator.
- Có thể cô lập một nguồn lỗi mà không làm những nguồn khác phải đổi schema.

### 8.4. Khi nào chọn một Transformer duy nhất?

Nếu chỉ có hai cấu trúc rất đơn giản, một Transformer có `switch` trên sealed input type có thể đủ. Normalizer pattern nhấn mạnh **phân chia trách nhiệm**, không bắt buộc mỗi input type phải có một JVM class hoặc một channel riêng trong mọi tình huống.

Chọn bố cục nhiều sub-flows khi mỗi nguồn có parsing/validation/rate limit/error policy riêng, hoặc số đối tác lớn khiến một Transformer “vạn năng” khó bảo trì.

## 9. Unsupported type khác malformed known type

Hai loại lỗi nhìn giống nhau nếu chỉ quan sát “không thấy canonical output”, nhưng phải phân biệt:

| Loại | Ví dụ | Vị trí phát hiện | Chính sách |
| --- | --- | --- | --- |
| **Unknown type** | Một `String` hoặc DTO mới chưa có route | Router defaultOutputChannel | Quarantine/unsupported-format metric |
| **Wrong source wrapper** | Payload ERP nhưng TrustedSource=MARKETPLACE | Translator source check | Chặn và báo trust violation |
| **Malformed value** | ERP `grossAmountVnd="abc"` | ERP translator | Reject/quarantine, không tạo số tiền giả |
| **Unknown enum** | State="REFUNDED" chưa có mapping | Translator mapping | Fail closed, cập nhật contract |
| **Invalid canonical invariant** | PAID amount=0 trong policy ví dụ | CommonOrderPolicy | Reject theo chính sách chung |
| **Transient infrastructure failure** | Database lookup lỗi khi enrichment | Adapter/enricher | Retry bounded, không gán lỗi schema |

`unknownFormatOrders` chỉ nhận **message không khớp routing mapping**. Lỗi `NumberFormatException` hoặc `IllegalArgumentException` ném ra từ Transformer **không tự đi tới defaultOutputChannel của Router**. Cần cấu hình error handling ở endpoint/adapter nếu muốn lưu message lỗi sang quarantine.

### 9.1. Không trả null để “lọc”

~~~java
// Không nên dùng trong Transformer:
CanonicalOrder fromErp(VerifiedErpOrder input) {
    if (invalid(input)) {
        return null;
    }
    return convert(input);
}
~~~

Theo tài liệu Spring Integration Transformer, một transformation method **không được trả null** như cách ngầm bỏ message; framework sẽ báo lỗi. Nếu cần Filter, dùng một **Filter có discardChannel**, hoặc tạo một **RejectedEvent outcome** có kiểu để audit.

### 9.2. Không dùng nhánh default để âm thầm chấp nhận dữ liệu

Một Router mặc định có thể cấu hình bỏ qua message không có route, nhưng với luồng thanh toán, unknown type cần được quan sát. Dùng `defaultOutputChannel` để đưa vào quarantine là một cách học dễ kiểm thử. Với production, queue có consumer, độ bền, giới hạn và retention; không giữ vô hạn các payload untrusted trong `QueueChannel` in-memory.

## 10. Metadata và correlation qua Normalizer

Nhiều nguồn có thể gửi **cùng một sự kiện nghiệp vụ** qua các transport khác nhau hoặc bị broker redeliver. Normalizer cần giữ metadata đủ để những bước sau đối soát và gom đúng nhóm.

### 10.1. Identity nào phải giữ?

| Identity | Nguồn | Tại sao giữ? |
| --- | --- | --- |
| **trustedTenantId** | Ingress security context | Cô lập tenant |
| **partnerId/sourceSystem** | Authenticated source registry | Truy nguồn, namespace IDs |
| **sourceEventId** | Event contract đã verify | Dedup/redelivery |
| **externalOrderId** | Payload nghiệp vụ hợp lệ | Liên kết đơn theo source |
| **businessCorrelationKey** | Workflow registry/trusted ingress | Gom các messages thuộc một workflow |
| **traceId** | Observability instrumentation | Truy vết các hops |
| **schemaVersion** | Parser/registry contract | Biết diễn giải payload theo version nào |

Một Spring Message được transform thành payload mới sẽ có thể có **MessageHeaders.ID khác** với ID ở ingress. Điều quan trọng là **business identity** vẫn ổn định và được xác minh.

### 10.2. Header propagation của Transformer

Spring Integration thông thường **propagate inbound headers khi Transformer trả về payload**. Nếu Transformer trả về **một `Message` hoàn chỉnh**, code người dùng chịu trách nhiệm về toàn bộ outbound Message và những headers cần giữ.

Ví dụ Transformer chỉ trả payload:

~~~java
.transform(VerifiedErpOrder.class, normalizer::fromErp)
~~~

Trong ví dụ này, các framework headers/headers đã gắn nội bộ có thể được propagate theo các quy tắc framework. Không dựa vào đó như một cam kết **mọi header** qua HTTP/JMS/TCP, vì adapter có cơ chế HeaderMapper khác.

### 10.3. Nếu cần tạo Message mới, chọn header theo allowlist

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class CanonicalMessageFactory {
    private CanonicalMessageFactory() {}

    static Message<CanonicalOrder> fromVerifiedInput(
            CanonicalOrder order,
            String businessGroupKey) {
        if (businessGroupKey == null
                || businessGroupKey.isBlank()) {
            throw new IllegalArgumentException("MISSING_GROUP_KEY");
        }

        return MessageBuilder.withPayload(order)
                .setHeader("trustedTenantId", order.tenantId())
                .setHeader("sourceSystem", order.sourceSystem().name())
                .setHeader("businessEventId", order.sourceEventId())
                .setHeader(
                        "businessCorrelationKey", businessGroupKey)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        businessGroupKey)
                .build();
    }
}
~~~

`businessGroupKey` ở đây **phải do nguồn nội bộ tin cậy tạo hoặc tra cứu**, không được copy nguyên từ client HTTP header. Không tự gắn `replyChannel`, `errorChannel`, `routingSlip` từ payload untrusted khi dựng canonical Message.

### 10.4. Business key khác eventId

Nếu ba events PAYMENT, INVENTORY, SHIPPING của một order cần Aggregator, chúng có **ba eventIds riêng** nhưng một **business correlation key**. Một event PAYMENT được redeliver phải giữ cùng eventId và cùng business key, không được tạo một group mới từ MessageHeaders.ID.

Normalizer chỉ tạo CanonicalOrder cho mỗi input, **không tự Aggregator**. Nếu muốn ghép các CanonicalOrder, phải định nghĩa rõ key, expected member set, release strategy, timeout và xử lý duplicate.

## 11. Unit test cho từng Translator

Trước khi đưa flow vào Spring context, kiểm thử các mapping thuần bằng **JUnit 5**. Các test nên xác nhận **giá trị**, không chỉ việc method trả về một CanonicalOrder.

### 11.1. ERP: decimal VND và trạng thái

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class PurchaseOrderNormalizerTest {

    private final PurchaseOrderNormalizer normalizer =
            new PurchaseOrderNormalizer();

    @Test
    void erpPaidOrderBecomesCanonicalOrder() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-erp-101",
                        "ERP-101",
                        "150000",
                        "2026-11-01T08:30:00Z",
                        "PAID"));

        CanonicalOrder order = normalizer.fromErp(incoming);

        assertEquals(1, order.canonicalSchemaVersion());
        assertEquals("tenant-a", order.tenantId());
        assertEquals("PARTNER-ERP", order.partnerId());
        assertEquals(SourceSystem.ERP, order.sourceSystem());
        assertEquals("evt-erp-101", order.sourceEventId());
        assertEquals("ERP-101", order.externalOrderId());
        assertEquals(CanonicalOrderStatus.PAID, order.status());
        assertEquals(new BigDecimal("150000"), order.total().amount());
        assertEquals(Currency.getInstance("VND"),
                order.total().currency());
        assertEquals(Instant.parse("2026-11-01T08:30:00Z"),
                order.occurredAt());
    }

    @Test
    void unknownErpStatusIsRejected() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-erp-102",
                        "ERP-102",
                        "150000",
                        "2026-11-01T08:30:00Z",
                        "SETTLED_BUT_NOT_CONFIRMED"));

        assertThrows(IllegalArgumentException.class,
                () -> normalizer.fromErp(incoming));
    }

    @Test
    void wrongTrustedSourceCannotUseErpTranslator() {
        var incoming = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-MARKET",
                        SourceSystem.MARKETPLACE),
                new ErpOrderV1(
                        "evt-erp-103", "ERP-103", "100",
                        "2026-11-01T08:30:00Z", "PAID"));

        assertThrows(SecurityException.class,
                () -> normalizer.fromErp(incoming));
    }
}
~~~

Trong ví dụ, thuộc tính `SourceSystem` được bảo vệ bằng `requireSource`, nhưng test này **không thay thế** xác thực ngoài đời thực của kết nối/đối tác. Phải tạo TrustedSource tại ingress từ nguồn đáng tin.

### 11.2. Marketplace: chuyển minor units

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class MarketplaceNormalizationTest {

    @Test
    void convertsUsdMinorUnitsWithoutFloatingPoint() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-1", "MK-202", 1235L, "USD",
                        1793521800000L, "SETTLED"));

        CanonicalOrder result =
                new PurchaseOrderNormalizer().fromMarketplace(input);

        assertEquals(CanonicalOrderStatus.PAID, result.status());
        assertEquals(new BigDecimal("12.35"),
                result.total().amount());
        assertEquals(Currency.getInstance("USD"),
                result.total().currency());
        assertEquals(Instant.ofEpochMilli(1793521800000L),
                result.occurredAt());
    }

    @Test
    void negativeMinorUnitsDoNotBecomeValidMoney() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-2", "MK-203", -10, "USD",
                        1793521800000L, "SETTLED"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer()
                        .fromMarketplace(input));
    }

    @Test
    void unsupportedCurrencyIsRejectedExplicitly() {
        var input = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-3", "MK-204", 1000, "XYZ",
                        1793521800000L, "SETTLED"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer()
                        .fromMarketplace(input));
    }
}
~~~

Chính sách `supportedCurrency` trong ví dụ chỉ chấp nhận VND và USD để tránh vô tình nhận currency mới mà chưa có kiểm thử. Khi mở thêm tiền tệ, phải cập nhật contract, test fractional digits và chính sách tiền/đơn giá.

### 11.3. CSV: decimal scale và format lỗi

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class CsvNormalizationTest {

    private final TrustedSource source = new TrustedSource(
            "tenant-a", "PARTNER-CSV", SourceSystem.CSV_UPLOAD);

    @Test
    void csvDecimalAndStateBecomeCanonical() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-303",
                        "CSV-303",
                        "89.90",
                        "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        CanonicalOrder order =
                new PurchaseOrderNormalizer().fromCsv(input);

        assertEquals(CanonicalOrderStatus.PAID, order.status());
        assertEquals(new BigDecimal("89.90"),
                order.total().amount());
    }

    @Test
    void csvAmountWithWrongPrecisionIsRejected() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-304",
                        "CSV-304",
                        "89.999",
                        "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        assertThrows(ArithmeticException.class,
                () -> new PurchaseOrderNormalizer().fromCsv(input));
    }

    @Test
    void csvDateMustHaveAnUnambiguousInstant() {
        var input = new VerifiedCsvOrder(source,
                new CsvOrderRow(
                        "evt-csv-305",
                        "CSV-305",
                        "89.90",
                        "USD",
                        "01/11/2026 08:30",
                        "PAYMENT_COMPLETE"));

        assertThrows(IllegalArgumentException.class,
                () -> new PurchaseOrderNormalizer().fromCsv(input));
    }
}
~~~

**Giải thích về exception:** `Money` gọi `BigDecimal.setScale(..., RoundingMode.UNNECESSARY)` nên một giá trị có phần lẻ không thể biểu diễn ở scale của currency sẽ ném `ArithmeticException`. Production có thể wrap thành một error code domain như `INVALID_CURRENCY_PRECISION`; test nên khớp với hợp đồng exception cuối cùng mà application công bố.

### 11.4. Property tests và metamorphic tests

Khi các translators ngày càng nhiều, ngoài ví dụ cố định nên kiểm thử tính chất:

- **Deterministic:** cùng input và cùng verified context tạo cùng CanonicalOrder.
- **Không mất nguồn:** tenantId, partnerId, sourceEventId giữ đúng.
- **Không ngầm làm tròn:** số tiền sai precision luôn bị reject.
- **Tương đương ngữ nghĩa:** ví dụ USD `"12.35"` ở CSV và `1235` minor units ở marketplace cho cùng `Money`.
- **Phân biệt tenant:** hai tenant cùng externalOrderId không được coi là một order identity nếu downstream cần isolation.
- **Không biến status lạ thành PAID:** một enum mới chưa được map phải tạo lỗi rõ ràng.
- **Có giới hạn input:** ngày quá xa, số quá lớn, chuỗi quá dài, schemaVersion unsupported phải bị xử lý theo policy.

Chỉ assert `result != null` là chưa đủ để chứng minh Normalizer giữ đúng semantics.

## 12. Integration test: ba formats đi qua chung IntegrationFlow

Test sau dùng **JUnit 5 + spring-test**, không cần Kafka/HTTP broker vì giả định parser và authentication đã chạy trước channel `verifiedIncomingOrders`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NormalizerFlowConfig.class)
class NormalizerFlowTest {

    @Autowired
    @Qualifier("verifiedIncomingOrders")
    MessageChannel input;

    @Autowired
    @Qualifier("canonicalOutput")
    QueueChannel output;

    @Autowired
    @Qualifier("unknownFormatOrders")
    QueueChannel unknown;

    @BeforeEach
    void clearQueues() {
        while (output.receive(0) != null) {
            // Dọn queue của test context.
        }
        while (unknown.receive(0) != null) {
            // Dọn queue của test context.
        }
    }

    private CanonicalOrder nextOrder() {
        Message<?> message = output.receive(0);
        assertNotNull(message);
        assertInstanceOf(CanonicalOrder.class, message.getPayload());
        return (CanonicalOrder) message.getPayload();
    }

    @Test
    void threeFormatsConvergeIntoTheSameCanonicalType() {
        var erp = new VerifiedErpOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
                new ErpOrderV1(
                        "evt-e-1", "ERP-101", "150000",
                        "2026-11-01T08:30:00Z", "PAID"));

        var market = new VerifiedMarketplaceOrder(
                new TrustedSource(
                        "tenant-a", "MARKET-01",
                        SourceSystem.MARKETPLACE),
                new MarketplaceOrderV2(
                        "evt-m-1", "MK-202", 1235,
                        "USD", 1793521800000L, "SETTLED"));

        var csv = new VerifiedCsvOrder(
                new TrustedSource(
                        "tenant-a", "PARTNER-CSV",
                        SourceSystem.CSV_UPLOAD),
                new CsvOrderRow(
                        "evt-c-1", "CSV-303", "89.90", "USD",
                        "2026-11-01T08:30:00Z",
                        "PAYMENT_COMPLETE"));

        assertTrue(input.send(
                MessageBuilder.withPayload(erp).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(market).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(csv).build()));

        List<CanonicalOrder> results = List.of(
                nextOrder(), nextOrder(), nextOrder());

        assertEquals(3, results.size());
        assertEquals(Set.of(
                        SourceSystem.ERP,
                        SourceSystem.MARKETPLACE,
                        SourceSystem.CSV_UPLOAD),
                results.stream()
                        .map(CanonicalOrder::sourceSystem)
                        .collect(Collectors.toSet()));

        assertTrue(results.stream().allMatch(
                order -> order.canonicalSchemaVersion() == 1));
        assertTrue(results.stream().allMatch(
                order -> order.status()
                        == CanonicalOrderStatus.PAID));
        assertEquals(new BigDecimal("150000"),
                results.get(0).total().amount());
        assertEquals(new BigDecimal("12.35"),
                results.get(1).total().amount());
        assertEquals(new BigDecimal("89.90"),
                results.get(2).total().amount());
        assertNull(output.receive(0));
    }

    @Test
    void unknownPayloadTypeGoesToQuarantineChannel() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        "unrecognized-data").build()));

        Message<?> quarantine = unknown.receive(0);
        assertNotNull(quarantine);
        assertEquals("unrecognized-data",
                quarantine.getPayload());
        assertNull(output.receive(0));
    }
}
~~~

**Ý nghĩa:** dù ba payload có field names và kiểu nguyên thủy khác nhau, kênh `canonicalOutput` chỉ phát `CanonicalOrder`. Test `unknownPayloadType` chỉ chứng minh nhánh Router mặc định; nó **không** chứng minh lỗi parse ở translator đi vào cùng queue.

### 12.1. Lưu ý về thứ tự assertions

Flow demo dùng **DirectChannel**, mỗi lần `send` chạy đồng bộ qua router/transformer/policy rồi output QueueChannel, nên ví dụ kiểm tra thứ tự ba lần send như trên là hợp lý. Nếu đổi sang **ExecutorChannel**, kết quả có thể về theo thứ tự bất kỳ; test phải ghép theo sourceEventId rồi assert nội dung, không dựa vào `results.get(0)` là ERP.

### 12.2. Test lỗi format đã biết

~~~java
// Mảnh phương thức bổ sung vào NormalizerFlowTest.
@Test
void malformedKnownFormatDoesNotProduceCanonicalOrder() {
    var invalid = new VerifiedErpOrder(
            new TrustedSource(
                    "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
            new ErpOrderV1(
                    "evt-e-invalid", "ERP-999", "not-a-number",
                    "2026-11-01T08:30:00Z", "PAID"));

    // Exception có thể được Spring Integration wrap thành
    // MessagingException/MessageTransformationException.
    assertThrows(RuntimeException.class,
            () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

    assertNull(output.receive(0));
    // Unknown-format channel không phải errorChannel của Transformer.
    assertNull(unknown.receive(0));
}
~~~

Nếu muốn lỗi này vào quarantine, hãy thêm **error handling đúng tại ingress/transformer** theo semantics sync/async, hoặc xử lý trong adapter có ack/retry/DLQ phù hợp. Không đổi assertion để giả vờ Router đã chuyển lỗi parse sang defaultOutputChannel.

### 12.3. Test giữ business correlation header

~~~java
// Mảnh phương thức bổ sung vào NormalizerFlowTest.
@Test
void propagatesTrustedBusinessCorrelation() {
    var erp = new VerifiedErpOrder(
            new TrustedSource(
                    "tenant-a", "PARTNER-ERP", SourceSystem.ERP),
            new ErpOrderV1(
                    "evt-e-correlation", "ERP-777", "500",
                    "2026-11-01T08:30:00Z", "PAID"));

    String businessKey = "ord:v1:tenant-a:ERP-777:2";
    assertTrue(input.send(
            MessageBuilder.withPayload(erp)
                    .setHeader("businessCorrelationKey", businessKey)
                    .build()));

    Message<?> transformed = output.receive(0);
    assertNotNull(transformed);
    assertEquals(businessKey,
            transformed.getHeaders().get(
                    "businessCorrelationKey"));
}
~~~

Trong test, header được gắn bằng code nội bộ và xem như đã verified. Production cần có lớp xác thực/lookup để tạo key; đừng để một client tự gửi `businessCorrelationKey` rồi đi thẳng vào `verifiedIncomingOrders`.

## 13. Chuẩn hóa ngữ nghĩa quan trọng hơn đổi tên field

Đổi `orderNo` thành `externalOrderId` là một phép mapping cơ học. Nhưng hai trường có tên giống nhau **chưa chắc cùng ý nghĩa**.

### 13.1. Gross, net và thuế

Giả sử:

~~~text
ERP:
  grossAmountVnd = 150000
  includesTax = true

Marketplace:
  amountMinor = 150000
  currencyCode = VND
  excludesFees = true
~~~

Nếu ERP là tổng đã gồm thuế, Marketplace là tổng chưa gồm phí vận chuyển, hai trường này không thể mặc định cùng nghĩa `total`. Nếu canonical contract thực sự cần **gross payable amount**, translator Marketplace phải có đủ dữ liệu và quy tắc để tính được; nếu không, **reject hoặc bổ sung field `amountBasis`/khả năng thiếu dữ liệu**.

Không biến dữ liệu không đủ thông tin thành giá trị nhìn hợp lệ chỉ để hoàn tất Normalizer.

### 13.2. “PAID” có thật sự bằng “SETTLED” không?

Ở một đối tác, `SETTLED` có thể nghĩa là tiền đã về tài khoản, còn `PAID` chỉ là payment được ủy quyền. Ở một đối tác khác, cả hai đều tương ứng với việc khách hàng đã thanh toán xong.

Mọi bảng mapping trạng thái phải được **nghiệp vụ phê duyệt**. Bảng của ví dụ:

| ERP | Marketplace | CSV | Canonical |
| --- | --- | --- | --- |
| PAID | SETTLED | PAYMENT_COMPLETE | PAID |
| CANCELLED | CANCELED | ORDER_CANCELLED | CANCELLED |
| PENDING | PENDING | AWAITING_PAYMENT | PENDING |

Chỉ đúng nếu các tên nguồn **có cùng nghĩa theo hợp đồng tích hợp cụ thể**. Một giá trị mới như `PARTIALLY_REFUNDED` không được tự map thành PAID hoặc CANCELLED khi chưa định nghĩa semantics.

### 13.3. Thời gian tuyệt đối, local time và daylight saving

`Instant.parse("2026-11-01T08:30:00Z")` là một thời điểm tuyệt đối. Nhưng `"2026-11-01 08:30"` **không cho biết timezone**.

Nếu ERP gửi local time và hợp đồng quy định `Asia/Ho_Chi_Minh`, có thể parse bằng `LocalDateTime` rồi áp dụng `ZoneId` đã thống nhất. Nếu dữ liệu đến từ một vùng có daylight saving, thời điểm local có thể **không tồn tại hoặc lặp**. Phải có quy tắc resolve rõ ràng hoặc reject; không mặc định timezone của máy chạy container.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

static Instant parsePartnerLocalTime(String text) {
    LocalDateTime local = LocalDateTime.parse(
            text,
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
    return local.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
}
~~~

**Đây là ví dụ theo hợp đồng timezone cụ thể**, không phải generic converter cho mọi nguồn. Với zone có DST và yêu cầu chính xác cao, cần xử lý gap/overlap chủ động thay vì mặc định Java `atZone()` tự quyết định đúng theo nghiệp vụ.

### 13.4. Đơn vị đo lường cũng cần canonical

Normalizer không chỉ dùng cho tiền. Một hệ thống logistics có thể nhận:

~~~text
Source A: weight=2.5 kg
Source B: weight=2500 g
Source C: weight=5.511556 lb
~~~

Nếu canonical `weightGrams` là decimal hoặc số nguyên theo precision đã chọn, mọi translator phải quy đổi có rule làm tròn, giới hạn và đơn vị rõ ràng. Một phép nhân với `double` rồi cast `int` có thể mất độ chính xác; nên dùng `BigDecimal` với precision được quyết định.

### 13.5. Mã đối tác và mã nội bộ

Hai source có thể cùng gửi `externalOrderId="1001"` nhưng là hai đơn khác nhau. **Normalizer không được coi đó là một internal order ID chung** nếu chưa tra registry theo tenant + partner + externalId.

Nếu downstream cần `internalOrderId`, thêm một **Enricher** có quyền tra mapping, hoặc tách thành một bước `ResolveIdentity` sau normalization. Không đánh đồng canonical schema với việc mọi external business ID đã đồng nhất.

## 14. Định dạng XML và schema version: thêm nguồn mới như thế nào?

Normalizer cần mở rộng được khi có nguồn thứ tư gửi XML:

~~~xml
<purchaseEvent schemaVersion="3">
    <eventId>evt-xml-404</eventId>
    <externalOrder>XML-404</externalOrder>
    <money currency="USD">19.99</money>
    <occurredAt>2026-11-01T08:30:00Z</occurredAt>
    <state>PAYMENT_CAPTURED</state>
</purchaseEvent>
~~~

Quy trình tích hợp đúng:

1. Inbound adapter nhận raw XML qua kênh đã xác thực và giới hạn kích thước.
2. XML parser được cấu hình **chống XXE/external entity resolution**, có schema/namespace validation.
3. Giải mã thành `XmlPurchaseV3` có kiểu, chỉ sau đó tạo `VerifiedXmlOrder`.
4. Thêm route cho kiểu mới hoặc source+version đã xác minh.
5. Viết một `fromXmlV3` translator trả **CanonicalOrder version 1**.
6. Thêm contract tests, test invalid fields, unknown status, currency precision và tenant isolation.
7. Giữ downstream trên CanonicalOrder version 1 nếu ngữ nghĩa không thay đổi.

**Không bắt buộc canonical version tăng từ 1 lên 3 chỉ vì XML source dùng schema v3.** Có hai lifecycle độc lập:

- **Source schema version**: thay đổi ở đầu vào của một partner.
- **Canonical schema version**: thay đổi ở hợp đồng nội bộ dùng chung.

### 14.1. Khi một source có nhiều versions

Giả sử Marketplace phát cả `MarketplaceOrderV1` và `MarketplaceOrderV2` trong giai đoạn migration. Nên có hai typed DTOs hoặc một versioned parser với validation rõ:

~~~text
JSON version 1 -> VerifiedMarketplaceV1 -> Translator V1 --+
                                                          +-> CanonicalOrder v1
JSON version 2 -> VerifiedMarketplaceV2 -> Translator V2 --+
~~~

Không dùng `if (fieldX != null)` để đoán version nếu hai schemas có trường trùng. Dựa vào schemaVersion đáng tin hoặc contract/endpoint-specific parser, với cơ chế reject khi version không hỗ trợ.

### 14.2. Thay đổi canonical contract cũng có chi phí

Nếu downstream cần thêm `taxIncluded` hoặc `lineItems`, một thay đổi từ CanonicalOrder v1 lên v2 có thể cần:

- Chính sách backward/forward compatibility.
- Mapping v1 → v2 hoặc support đồng thời.
- Schema registry và producer/consumer contracts.
- Migration persisted events/replay/DLQ.
- Test compatibility giữa nhiều service.
- Lộ trình rollout, tránh nâng mọi translator trong một lần triển khai không thể rollback.

**Normalizer giảm phụ thuộc vào source schemas**, không loại bỏ chi phí versioning của **canonical schema**.

## 15. Một file CSV chứa nhiều dòng không phải một message chuẩn hóa

Trong ví dụ chính, mỗi `VerifiedCsvOrder` đại diện cho **một dòng đã parse**. Với file có 10.000 dòng, cần một flow khác ở phía trước:

~~~mermaid
flowchart LR
    F["CSV file"] --> P["CSV parser"]
    P --> S["Splitter: từng row"]
    S --> N["Normalizer: row -> CanonicalOrder"]
    N --> V["Validate common contract"]
    V --> H["Idempotent business handler"]
    N -.->|"Row validation failed"| Q["Row quarantine"]
~~~

Nơi tách dòng có thể là parser/poller/Splitter tùy kích thước và cơ chế streaming. Không load file nhiều GB vào `List` chỉ để gọi Splitter nếu một iterator/stream bounded phù hợp.

### 15.1. Chính sách lỗi từng dòng

| Loại lỗi | Ví dụ | Quyết định có thể |
| --- | --- | --- |
| **File-level** | Signature sai, tenant không có quyền | Reject cả file |
| **Schema-level** | Header thiếu cột bắt buộc, charset không đúng | Reject file hoặc quarantine |
| **Row-level** | Dòng 305 có amount="abc" | Reject đúng row, cho row khác tiếp tục nếu policy cho phép |
| **Infrastructure** | DB down trong lúc ghi row 400 | Retry/park, không coi là invalid row |
| **Duplicate row** | Cùng eventId trong file hoặc redelivery | Dedup theo logical event |
| **Unknown outcome** | Lệnh ngoài đã gửi nhưng không nhận reply | Reconcile trước khi retry có side effect |

Nếu nghiệp vụ yêu cầu **all-or-nothing** (mọi dòng hợp lệ hoặc reject toàn file), không để Normalizer xử lý partial success không chủ đích. Ngược lại, nếu chấp nhận import từng dòng, phải có **ImportReport** gồm số expected, accepted, rejected, pending và error code mỗi row.

### 15.2. Đừng để Filter mất một item trước Aggregator

Nếu Splitter gắn `sequenceSize=100` và một row bị Filter loại mà không tạo terminal outcome, Aggregator đợi đủ 100 outcomes có thể không bao giờ release. Với bài toán import có report đầy đủ:

- Mỗi row cần **một terminal result** (SUCCESS hoặc REJECTED) nếu đó là policy.
- Exception infrastructure cần retry, state/timeout, không ngầm đổi thành REJECTED.
- Aggregator dựa trên correlationId/sequence hoặc manifest **chỉ release khi đủ các logical rows**, không đếm attempts.

Đây là cách Normalizer phối hợp với **Splitter, Filter, Aggregator và retry** mà không làm mất dữ liệu hợp lệ.

### 15.3. CSV row identity

Khi file được phát lại sau crash, dòng số 300 có thể xuất hiện lần nữa. Một khóa có thể là:

~~~text
logicalEventKey =
    trustedTenantId
    + ":" + partnerId
    + ":" + fileImportId
    + ":" + rowIdentity
~~~

`rowIdentity` cần được định nghĩa ổn định qua replay (lineNumber trong manifest bất biến hoặc eventId nguồn đáng tin). Nếu parser bỏ các dòng rỗng rồi đánh lại số, line number có thể không còn ổn định. Có thể dùng eventId có sẵn hoặc content digest với chính sách conflict; không chọn bừa theo lần chạy.

## 16. Retry, replay và idempotency sau Normalizer

Một Transformer có thể deterministic, nhưng nếu broker giao lại cùng raw event, Normalizer có thể tạo **hai CanonicalOrder giống nhau**. Về mặt biến đổi, điều đó không sai; về mặt ghi database hoặc gọi dịch vụ ngoài, nó có thể gây **hai side effects**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant N as Normalizer
    participant H as Business Handler
    participant D as Database
    B->>N: Raw event E, attempt 1
    N->>H: CanonicalOrder E
    H->>D: Apply business effect
    D-->>H: Commit
    Note over B: Ack/connection lost
    B->>N: Raw event E, attempt 2
    N->>H: CanonicalOrder E
    H->>D: Detect E already processed
    D-->>H: Skip duplicate effect
~~~

**Normalizer không cung cấp exactly-once processing** chỉ vì nó đưa mọi định dạng về cùng một kiểu. Idempotency phải bảo vệ **logical business event hoặc operation** ở điểm phát sinh tác động.

### 16.1. Định danh event đúng phạm vi

Nếu `sourceEventId` chỉ duy nhất trong một partner, một dedup key phù hợp có thể là:

~~~text
dedupKey = trustedTenantId + ":" + partnerId + ":" + sourceEventId
~~~

Đừng dùng chỉ `externalOrderId`: một đơn có thể có nhiều events hợp lệ (PAYMENT, REFUND, CANCEL). Đừng dùng `MessageHeaders.ID`: đó là identity kỹ thuật có thể thay đổi qua các lần build/replay. Đừng dùng `occurredAt` làm idempotency key vì nhiều sự kiện có thể cùng timestamp.

### 16.2. Một inbox/ledger bền

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE canonical_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    partner_id VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    raw_digest VARCHAR(128) NOT NULL,
    source_schema_version INTEGER NOT NULL,
    canonical_schema_version INTEGER NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, partner_id, source_event_id)
);

CREATE INDEX canonical_event_inbox_status_idx
    ON canonical_event_inbox (processing_status);
~~~

Khi nhận một event:

1. Lấy `tenantId`/`partnerId` từ trust boundary, `sourceEventId` từ payload đã validate.
2. Tính digest trên **wire payload canonicalized theo cùng schema/format version**, hoặc lưu raw digest có cách tính đã quy định.
3. Tra/claim event bằng unique constraint.
4. Nếu đã xử lý và digest bằng nhau, đó có thể là một redelivery, không tạo effect mới.
5. Nếu cùng identity nhưng digest khác, tạo **ID_CONFLICT** và quarantine; không âm thầm overwrite.
6. Nếu trạng thái còn RECEIVED/DISPATCH_PENDING, khôi phục xử lý thay vì bỏ qua.
7. Chỉ đánh dấu COMPLETED khi tác động nghiệp vụ đạt điều kiện commit theo contract.

### 16.3. Cửa sổ crash giữa inbox và downstream

Phản ví dụ:

~~~text
1. INSERT inbox E, status=SEEN
2. COMMIT
3. Crash trước khi gửi E tới business handler
4. Broker redeliver E
5. Code thấy E đã SEEN rồi drop
=> Business effect không bao giờ xảy ra
~~~

Các lựa chọn sửa:

- **Transactional outbox:** ghi inbox và event cần dispatch trong cùng transaction; worker sẽ publish/consume tiếp sau crash.
- **Inbox state machine:** RECEIVED → DISPATCH_PENDING → PROCESSED, có recovery scanner và ownership.
- **Transactional consumer:** commit offset/ack phù hợp với database transaction theo khả năng adapter; vẫn kiểm thử khoảng hở giữa resource boundaries.

Không cần cả ba trong mọi ứng dụng, nhưng phải có **một mô hình cụ thể** bảo vệ điểm cắt crash.

### 16.4. Replay khi mapping version thay đổi

Giả sử `MarketplaceOrderV2` từng được map `SETTLED → PAID`, nhưng sau thay đổi hợp đồng phải phân biệt `SETTLED` với trạng thái mới `RECONCILED`.

Khi replay raw events để tái tạo projections, phải biết:

- Source schema version ban đầu.
- Version của phép dịch ngữ nghĩa/mapping.
- Canonical schema version.
- Có cần rebuild **read model** hay thực hiện lại **side effect** không.
- Quy tắc migration và backward compatibility.

Replay để rebuild reporting **không được tự động gửi lại charge/email/booking**. Tách **projection rebuilding** khỏi những handler có effect và dùng idempotency/operation ledger.

### 16.5. Vì sao không phát random eventId trong Transformer?

~~~java
// Phản ví dụ cho redelivery:
String newId = java.util.UUID.randomUUID().toString();
~~~

Nếu mỗi lần Transformer chạy tạo eventId mới, một raw event bị redeliver sẽ trông như event mới, vượt qua dedup. `sourceEventId` phải ổn định theo hợp đồng; nếu nguồn không cung cấp, ingress cần định nghĩa một identity **deterministic từ manifest/operation** hoặc persist mapping. Đừng dùng `UUID.randomUUID()` ở mỗi attempt mà không lưu.

## 17. Xử lý lỗi: không được biến dữ liệu hỏng thành dữ liệu có vẻ hợp lệ

### 17.1. Phân loại lỗi

| Lớp lỗi | Ví dụ | Nên xử lý |
| --- | --- | --- |
| **Parsing/schema** | JSON invalid, CSV missing required column | Reject/quarantine tại adapter |
| **Authorization** | Producer không được phát ERP event của tenant khác | Reject, audit/security alert |
| **Semantic mapping** | Source status mới chưa hỗ trợ | Quarantine, update mapping contract |
| **Canonical validation** | PAID total=0 theo policy minh họa | Reject domain validation |
| **Transient infrastructure** | Lookup registry timeout, DB unavailable | Retry bounded, giữ eventId |
| **Unexpected application bug** | NullPointerException/IllegalStateException do lỗi code | Alert, quarantine/retry sau sửa |
| **External side effect unknown** | HTTP timeout sau khi đã gửi lệnh charge | Reconcile, không coi như lỗi dữ liệu |

Không catch `Exception` rồi trả một `CanonicalOrder` `status=PENDING` với amount=0, vì nó khiến hệ thống downstream coi một event lỗi thành một event hợp lệ.

### 17.2. DirectChannel và async channel khác nhau

Ví dụ DSL của bài dùng **DirectChannel**. Khi Translator ném exception:

- Exception thường lan ngược về sender (có thể được Spring Integration wrap thành MessagingException).
- Việc `input.send()` thất bại không tự đưa message vào QueueChannel `unknownFormatOrders`.
- Inbound adapter (HTTP/JMS/Kafka) phải quyết định ack/retry/response theo contract thực tế.

Nếu thay bằng **ExecutorChannel**, poller hoặc các endpoint async, error handling có thể tạo **ErrorMessage** vào `errorChannel`. Nhưng một ErrorMessage chứa Throwable, không phải CanonicalOrder hợp lệ, và `errorChannel` **không tự là một durable DLQ**.

### 17.3. Quarantine record

Một bản ghi quarantine hữu ích:

~~~json
{
  "sourceSystem": "CSV_UPLOAD",
  "schemaVersion": 1,
  "eventRef": "evt-csv-304",
  "errorStage": "NORMALIZATION",
  "errorCode": "INVALID_CURRENCY_PRECISION",
  "retryable": false,
  "status": "REQUIRES_SOURCE_CORRECTION"
}
~~~

Đây là **mô hình ví dụ**, không phải `ErrorMessage` do Spring Integration tự sinh. Quarantine có thể lưu raw payload vào object storage được bảo vệ, đồng thời trong metadata chỉ lưu reference/digest; hạn chế PII và thực hiện retention/authorization rõ ràng.

### 17.4. Đường sửa và replay

Với lỗi data:

1. Ghi nguồn, schema version, event ID, error code và đủ thông tin đối soát.
2. Yêu cầu đối tác sửa payload hoặc cung cấp event correction hợp lệ.
3. Không tự thay payload rồi phát lại với cùng eventId nếu chính sách versioning không cho phép.
4. Sau sửa, dùng `eventId`/revision identity theo hợp đồng, kiểm tra existing ledger và side effects.
5. Chạy lại qua **đúng translator/version** được áp dụng, không bypass validation.

Với lỗi hạ tầng, retry có giới hạn và backoff; nếu vẫn không giải quyết được, đặt trạng thái pending/unknown và một recovery job, không lặng lẽ coi message đã normal.

## 18. Độ lớn dữ liệu, backpressure và thứ tự

Chuyển đổi payload có thể là CPU-bound (JSON/XML parse) hoặc I/O-bound (lookup catalog/rate). Một pipeline hoạt động tốt ở 10 events/giây chưa chắc ổn khi nhận 10.000 events/giây.

### 18.1. Bounded resources

- Giới hạn số bytes mỗi HTTP/JMS/AMQP message và kích thước CSV row.
- Giới hạn số digits của `amountDecimal` trước khi tạo BigDecimal; chuỗi số khổng lồ có thể tiêu tốn CPU/memory.
- Giới hạn số XML nodes/độ sâu, tắt external entity resolution để tránh XXE.
- Không tạo unbounded `QueueChannel` trong production chỉ vì test demo dùng kiểu đó.
- Sử dụng bounded executor, queue capacity, timeout và rate limit theo nguồn.
- Nếu một partner thường xuyên gửi schema lỗi, cơ chế quarantine cần quota để không làm đầy storage của mọi đối tác khác.

### 18.2. Không có parallelism chỉ vì có ba nhánh Router

Router chọn nhánh theo type. Với DirectChannel, code thường chạy trên thread sender; gửi ba messages liên tiếp trong test không chứng minh chúng xử lý song song.

Để đạt parallelism, có thể đặt ExecutorChannel/adapter async ở vị trí phù hợp và đặt bulkhead theo source. Tuy nhiên:

- Thread pool lớn không thay thế connection pool/DB capacity.
- Async transformations có thể **đảo thứ tự hoàn thành**.
- Nếu downstream yêu cầu xử lý theo thứ tự logical event, cần sequence/version và Resequencer hoặc một coordinator riêng.
- Không sắp xếp theo `occurredAt` một cách mù quáng khi clocks của các producers có skew.

### 18.3. Sự độc lập giữa các nguồn

Một partner gửi nhiều event lỗi hoặc chậm không nên làm tất cả tenants/ngành hàng không thể xử lý. Có thể dùng:

- Rate limit/quota theo source.
- Bounded queues và error isolation.
- Circuit breaker cho enrichment/lookup bên ngoài, không phải cho một phép chuyển đổi thuần.
- Metrics latency/error theo adapter/translator.
- Pause/resume ingestion hoặc DLQ replay riêng mỗi source.

**Đừng tách theo nguồn rồi quên thống nhất validation ở đầu ra**: ba translators phải cùng tuân một canonical contract để downstream có thể tin cậy.

## 19. Observability cho Normalizer

Một báo cáo lỗi tổng quát `TRANSFORM_FAILED` không đủ để tìm vì sao một đối tác đang gửi trạng thái mới hoặc amount scale sai.

| Metric | Ý nghĩa |
| --- | --- |
| **normalizer_input_total{source,schema}** | Số messages được nhận theo nguồn/schema |
| **normalizer_output_total{source,status}** | Số CanonicalOrder được phát |
| **normalizer_unsupported_type_total{source}** | Router không tìm được translator |
| **normalizer_parse_failed_total{source,code}** | Dữ liệu không parse được |
| **normalizer_semantic_reject_total{source,code}** | Mapping/validation bị từ chối |
| **normalizer_processing_duration_seconds{source}** | Latency parse/translate/validate |
| **normalizer_quarantine_total{reason}** | Số event đã lưu xử lý sau |
| **normalizer_retry_total{source,reason}** | Attempts do lỗi tạm thời |
| **normalizer_duplicate_skipped_total{source}** | Event được nhận ra là redelivery |
| **normalizer_inbox_pending** | Inbox chưa dispatch hoặc chưa hoàn tất |
| **normalizer_backpressure_total{source}** | Queue full/task rejected |
| **normalizer_canonical_version_total{version}** | Distribution của canonical schema versions |

Giữ `source`, `schema`, `status`, `reason` trong một **tập giá trị hữu hạn**. Không đặt eventId, orderId, tenantId hoặc payload text tùy ý làm metric label; đó là cardinality rất lớn và có nguy cơ lộ dữ liệu.

### 19.1. Log mẫu khi thành công

~~~json
{
  "stage": "NORMALIZE",
  "sourceSystem": "MARKETPLACE",
  "sourceSchemaVersion": 2,
  "canonicalSchemaVersion": 1,
  "eventRef": "evt-market-202",
  "outcome": "SUCCESS",
  "normalizedStatus": "PAID"
}
~~~

### 19.2. Log mẫu khi dữ liệu lỗi

~~~json
{
  "stage": "NORMALIZE",
  "sourceSystem": "CSV_UPLOAD",
  "sourceSchemaVersion": 1,
  "eventRef": "evt-csv-304",
  "outcome": "REJECTED",
  "errorCode": "INVALID_CURRENCY_PRECISION",
  "retryable": false
}
~~~

**Không log** raw payment details, token, thông tin khách hàng, file path nhạy cảm hoặc payload chưa lọc. Nếu cần đọc lại raw event, lưu ở vị trí có access control và retention phù hợp, trong log chỉ để reference.

### 19.3. Alert hữu ích

1. Một source đột ngột tăng lỗi UNKNOWN_STATUS sau khi đối tác nâng API.
2. Số unsupported-type messages tăng nhưng không có kế hoạch bổ sung translator.
3. Một adapter nhận thành công nhưng normalizer output giảm mạnh.
4. Currency precision errors tăng ở marketplace sau rollout.
5. Quarantine đầy hoặc không có consumer/operator phụ trách.
6. Inbox có nhiều RECEIVED/DISPATCH_PENDING quá SLA.
7. Canonical schema version mới xuất hiện trước khi consumers hỗ trợ.
8. Một source phát nhiều tenant IDs khác quyền đã xác minh.
9. Downstream báo false joins do externalOrderId thiếu partner namespace.
10. Replayed messages tạo business effect lần nữa.

## 20. Runbook: đối tác gửi dữ liệu nhưng CanonicalOrder không xuất hiện

**Tình huống:** hệ thống ghi nhận inbound event thành công, nhưng downstream không thấy CanonicalOrder tương ứng.

### Bước 1 — Xác minh event thực sự vào đúng adapter

Thu thập trusted source/partner, schema version, event ID, thời gian nhận và trace. Kiểm tra adapter nhận bytes thành công chưa, có bị rate limit/quota hoặc parse failure không. Không dùng HTTP 200 hoặc broker ACK như bằng chứng business handler đã commit.

### Bước 2 — Kiểm tra authentication và wrapper type

Raw event có đi qua bước xác thực/authorization chưa? Có tạo đúng VerifiedErpOrder/VerifiedMarketplaceOrder/VerifiedCsvOrder không? Nếu event ERP bị wrap thành marketplace, Router có thể chọn nhánh sai.

### Bước 3 — Kiểm tra route selection

Một DTO mới sau rollout có thể không có channelMapping. Kiểm tra unknownFormatOrders/quarantine và metrics unsupported-type. Không âm thầm chuyển mọi unknown DTO sang ERP translator chỉ vì đó là default route.

### Bước 4 — Kiểm tra converter và status mapping

Ví dụ:

~~~text
Input source=MARKETPLACE, schemaVersion=2
currencyCode=USD
amountMinor=1235
state=PARTIALLY_REFUNDED

Normalizer:
  source recognized
  amount valid
  state not mapped
  outcome: UNKNOWN_MARKETPLACE_STATE
~~~

Không sửa mapping thành PAID nếu chưa biết PARTIALLY_REFUNDED có ý nghĩa gì. Cần đối chiếu contract của partner và domain owner.

### Bước 5 — Kiểm tra common validation

Một message có thể qua Translator thành công rồi thất bại ở CommonOrderPolicy, chẳng hạn PAID amount=0 theo chính sách ví dụ. Phải phân biệt **format-specific error** với **canonical invariant violation**.

### Bước 6 — Tìm ErrorMessage/quarantine

Nếu dùng DirectChannel, exception có thể truyền về adapter caller. Nếu dùng async, xem errorChannel/error handler, DLQ hoặc recovery job. Quarantine record phải có source, schema, event identity và error code đủ để xử lý lại.

### Bước 7 — Kiểm tra inbox/dedup state

Nếu eventId đã tồn tại:

- **COMPLETED + digest giống:** có thể đã xử lý, redelivery bị skip là đúng.
- **RECEIVED/DISPATCH_PENDING:** tìm worker/recovery bị kẹt.
- **Cùng ID nhưng digest khác:** cần điều tra ID_CONFLICT.
- **Không tồn tại:** tìm lỗi ingestion/routing trước inbox.

### Bước 8 — Khôi phục có kiểm soát

Chỉ replay khi đã biết đó là lỗi dữ liệu được sửa, lỗi hạ tầng có thể retry hoặc một correction hợp lệ. Giữ identity/version phù hợp; tránh phát lại side effects không idempotent.

### Bước 9 — Xác nhận sau khắc phục

Kiểm tra canonical output đúng Money/Instant/status/source identity, business handler hoàn tất đúng một lần và metrics/error-rate trở lại mức bình thường. Với dữ liệu từ nhiều nguồn, so sánh schema contract thay vì chỉ đếm số lượng event đã xử lý.

## 21. Bài thực hành: Normalizer cho ba nguồn thanh toán

Hãy triển khai một module Spring Integration tiếp nhận ba loại payment notification:

~~~text
ERP             -> JSON v1 -> ErpPaidEvent
Marketplace     -> JSON v2 -> MarketplacePaidEvent
Batch Partner   -> CSV     -> CsvPaidRow

Mọi loại:
   -> validated trusted context
   -> Normalizer (route + translator)
   -> PaymentCanonicalEvent
   -> common validation
   -> idempotent persistence
~~~

### 21.1. Canonical contract tối thiểu

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;

record PaymentCanonicalEvent(
        int schemaVersion,
        String tenantId,
        String sourceSystem,
        String sourceEventId,
        String externalPaymentId,
        String internalOrderId,
        BigDecimal amount,
        Currency currency,
        Instant paidAt,
        String paymentStatus) {
}
~~~

**Yêu cầu:** internalOrderId phải đến từ **mapping đáng tin** theo tenant/source/externalPaymentId hoặc externalOrderId; không giả định mã thanh toán của các đối tác nằm chung một namespace.

### 21.2. Bộ dữ liệu cho test

| Dòng | Nguồn | Giá trị nguồn | Output mong đợi |
| --- | --- | --- | --- |
| 1 | ERP | `"150000"` VND, `PAID` | 150000 VND, PAID |
| 2 | Marketplace | `1235` minor USD, `SETTLED` | 12.35 USD, PAID |
| 3 | CSV | `"89.90"` USD, `PAYMENT_COMPLETE` | 89.90 USD, PAID |
| 4 | ERP | `"abc"` VND | Reject INVALID_AMOUNT_FORMAT |
| 5 | Marketplace | `-1` minor USD | Reject negative amount |
| 6 | CSV | `"89.999"` USD | Reject invalid precision |
| 7 | Marketplace | `PARTIALLY_REFUNDED` | Reject unknown status trước khi được định nghĩa |
| 8 | Unknown schema | JSON version 9 | Unsupported version/quarantine |
| 9 | Duplicate | Event ID của dòng 2 gửi lại | Không ghi effect lần hai |
| 10 | Multi-tenant | Cùng externalPaymentId ở tenant khác | Không ghép nhầm identity |

### 21.3. Các bước thực hiện

1. Xác định nguồn/tenant từ identity của adapter, không dựa vào payload tự khai.
2. Định nghĩa canonical schema có kiểu, đơn vị và validation rõ ràng.
3. Định nghĩa DTO riêng cho ERP, Marketplace và CSV.
4. Viết parser/MessageConverter từng schema; kiểm thử invalid JSON, CSV quoting, charset và input size.
5. Viết Router chọn typed payload hoặc trusted source+version.
6. Viết ba Translator thuần; không I/O ngoài nếu không bắt buộc.
7. Chuyển các nhánh vào một canonical channel.
8. Thêm CommonCanonicalValidation bảo vệ invariants dùng chung.
9. Thêm một default route cho unknown type và error path cho invalid known type.
10. Viết unit tests cho trường, status, tiền tệ, timestamp, source identity.
11. Viết integration test chứng minh cả ba formats đều tạo PaymentCanonicalEvent.
12. Giữ sourceEventId, partnerId và businessCorrelationKey qua Normalizer.
13. Dùng inbox/ledger hoặc idempotent receiver phù hợp để tránh effect trùng qua redelivery.
14. Nếu xử lý CSV batch, thiết kế row-level outcome và final import report.
15. Viết một contract test cho nguồn XML mới mà không sửa business handler.
16. Mô phỏng mapping version thay đổi và replay historical input có kiểm soát.
17. Đo parse/translate latency, quarantine rate, pending inbox và backpressure.
18. Viết runbook hướng dẫn replay một event lỗi mà không gửi lại side effect đã commit.

### 21.4. Các tiêu chí đạt

| Tiêu chí | Cách xác minh |
| --- | --- |
| Một output contract | Downstream chỉ nhận PaymentCanonicalEvent |
| Mapping theo nguồn | Mỗi input schema có translator riêng và test |
| Currency chính xác | USD minor units và VND không sai scale |
| Timestamp chính xác | Instant có timezone/UTC rõ ràng |
| Status đúng semantics | Unknown không tự thành PAID |
| Tenant/source isolation | Sai verified context bị chặn |
| Router fallback | Unknown input có quarantine thay vì biến mất |
| Error handling | Known format lỗi không âm thầm thành canonical |
| Header propagation | Business correlation và event ID không bị đổi tùy tiện |
| Replay | Cùng eventId không tạo effect trùng |
| CSV batch | Một row lỗi không gây mất row khác ngoài ý muốn |
| Observability | Có metrics và log đủ điều tra lý do reject |

### 21.5. Thử thay một nguồn mà không chạm downstream

Một tiêu chí kiến trúc hữu ích:

> Khi đối tác đổi từ CSV v1 sang XML v3 nhưng ý nghĩa dữ liệu vẫn giống nhau, nhóm tích hợp phải có thể thay parser, typed DTO và Translator mà **không cần sửa logic tính báo cáo/ghi đơn** đang chỉ tiêu thụ canonical schema.

Nếu mọi source-specific field names vẫn lộ vào downstream dưới dạng `if (source == CSV)`, Normalizer chưa thực sự tạo một boundary ít phụ thuộc.

## 22. Câu hỏi tự kiểm tra

1. Normalizer có phải một Transformer đơn lẻ hay là một pattern phối hợp Router với nhiều Translators?
2. Vì sao ba JSON/CSV payload có cùng ý nghĩa nhưng khác trường/đơn vị lại là bài toán Normalizer?
3. Vì sao một `MessageConverter` tự đổi bytes thành Java record chưa đủ là normalization?
4. Canonical schema có bắt buộc các giá trị của mọi source đều giống nhau không?
5. `grossAmountVnd` và `amountMinor` có thể map thẳng về cùng `total` trong mọi trường hợp không?
6. Tại sao không dùng `double` cho số tiền?
7. `SETTLED` có luôn đồng nghĩa `PAID` không?
8. Nếu Marketplace có state mới chưa hỗ trợ, nên tự default thành PENDING hay fail closed?
9. Khi nào route theo payload type hợp lý, và khi nào cần route theo trusted schemaVersion?
10. Vì sao không route mọi raw `String` JSON chỉ dựa trên `payload.getClass()`?
11. `Transformer` trả null có phải cách Filter hợp lệ không?
12. `defaultOutputChannel` của Router có tự nhận lỗi từ Translator không?
13. Sự khác biệt giữa source schema version và canonical schema version là gì?
14. Vì sao tính `sourceEventId` lại cần ổn định qua retry?
15. Business correlationId khác source eventId ở đâu?
16. Nếu Translator tạo Message hoàn chỉnh mới, điều gì cần làm với trusted headers?
17. Vì sao `Instant` quan trọng khi hai nguồn dùng timezone khác nhau?
18. Nếu CSV một dòng lỗi, có nên reject toàn file không?
19. Vì sao unique index ở inbox vẫn có thể gây mất event nếu crash trước dispatch?
20. Normalizer có bảo đảm exactly-once side effect không?
21. Khi một partner thay schema, nên kiểm tra gì trước khi bật production route mới?
22. Dùng những metric nào để phân biệt unknown input type và invalid known value?
23. Khi nào cần Enricher sau Normalizer để map externalOrderId thành internalOrderId?
24. Tại sao không nên giữ một unbounded QueueChannel để gom mọi message lỗi?

## 23. Checklist thiết kế và vận hành

- Đã liệt kê các input schema, version, charset, currency/timezone và chủ sở hữu từng nguồn.
- Mọi nguồn đi qua authentication/authorization và schema validation trước trusted routing.
- Canonical contract định nghĩa rõ field types, units, nullable semantics và enum values.
- Source-specific parsing tách khỏi semantic translation; không dùng generic CSV split hoặc XML parser không an toàn.
- Router chọn đúng translator theo typed payload hoặc trusted source+version.
- Không có default route silently đổi unknown payload thành data có vẻ hợp lệ.
- Mỗi Translator trả một CanonicalOrder không null hoặc phát lỗi được phân loại.
- Mapping trạng thái đã được domain owner xác nhận là tương đương ngữ nghĩa.
- Money dùng BigDecimal/Currency và rounding/precision policy rõ.
- Timestamp có timezone/UTC rõ, không dựa vào system default zone.
- Source eventId, tenant, partner, schema version và business correlation được giữ đúng scope.
- Nếu Transformer tạo Message mới, chỉ copy/gắn những headers nội bộ được phép.
- Common validator được dùng sau mọi Translator; không có nguồn nào bypass policy.
- Source schema migration có contract tests và rollback plan.
- Canonical schema versioning có backward/forward compatibility rõ.
- Unknown format và malformed known format có error/quarantine paths riêng.
- Error channel, DLQ và quarantine có consumer, độ bền, retention và audit.
- Retry phân biệt data errors với transient infrastructure failures.
- Inbox/outbox/recovery xử lý cửa sổ crash và event ID conflict.
- Side effects có idempotency độc lập với việc Transformer deterministic.
- CSV/file batch có policy all-or-nothing hoặc partial success rõ ràng.
- Splitter/Aggregator không mất item khi một row bị Filter/reject.
- DirectChannel/ExecutorChannel được chọn theo latency, ordering và backpressure.
- Hạn chế input size, queue, pool, parser resources và event rate theo source.
- Logs không chứa sensitive raw payload; metrics không có high-cardinality IDs.
- Test bao phủ happy path, sai amount, wrong status, wrong source, unknown schema, duplicate, replay, tenant isolation và schema upgrade.
- Có runbook điều tra từ adapter tới canonical output và downstream effect.

**Kết luận:** Normalizer giúp nhiều nguồn **cùng ngữ nghĩa nhưng khác định dạng** đi về một biểu diễn chung. Trong Spring Integration, pattern được hiện thực rõ ràng bằng **Router → Translator riêng theo nguồn → canonical channel → common validation**. Giá trị lớn nhất không nằm ở việc đổi tên trường, mà ở việc **chuẩn hóa ngữ nghĩa của tiền tệ, thời gian, trạng thái và danh tính**, rồi bảo vệ hợp đồng ấy bằng schema versioning, kiểm thử, error handling, idempotency và monitoring. Khi được thiết kế đúng, thêm một format mới không buộc mọi downstream consumer phải hiểu thêm một ngôn ngữ dữ liệu mới.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html): Router + Message Translators tạo một định dạng thống nhất cho các thông điệp tương đương ngữ nghĩa.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): chuyển cấu trúc và ngữ nghĩa của một message sang cấu trúc khác.
- [Enterprise Integration Patterns — Content-Based Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html): chọn route dựa vào đặc tính message.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): các router, Java DSL và default output channel.
- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): PayloadTypeRouter và routing theo Java class.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): POJO/DSL transformer, hạn chế null return, header propagation và header filtering.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): immutable Message, MessageHeaders và MessageBuilder.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): tạo các IntegrationFlow và kết nối Router/Transformer/Channel.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): các message con, correlation và sequence metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): group correlation, release, timeout và partial results.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi đồng bộ/bất đồng bộ, errorChannel và ErrorMessage.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): hỗ trợ dedup và giới hạn cần lưu ý trước side effects.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel và QueueChannel.
