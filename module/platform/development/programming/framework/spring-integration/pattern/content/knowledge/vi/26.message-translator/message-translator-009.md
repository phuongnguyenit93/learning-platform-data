# Translator hai chiều và nguy cơ mất thông tin

**Message Translator** là một Enterprise Integration Pattern (EIP) chuyển thông điệp từ **biểu diễn mà một hệ thống hiểu** sang **biểu diễn mà hệ thống khác hiểu**, mà không bắt hai phía phụ thuộc trực tiếp vào kiểu dữ liệu, serialization format hoặc mã quy ước của nhau. Với Spring Integration, Translator thường được triển khai bằng **Transformer**, một chuỗi Transformer, hoặc adapter/codec tại ranh giới tích hợp.

Trong thực tế, nhiều nhóm cần dịch **hai chiều**: đối tác gửi `LegacyOrderV1` vào hệ thống nội bộ, còn hệ thống nội bộ phải trả đơn hàng hoặc phát message ngược lại theo định dạng cũ. Hai hàm `A → B` và `B → A` có thể đều thực thi được nhưng **không bảo đảm phép dịch ngược khôi phục đầy đủ thông tin đầu vào**. Một trường mà A có nhưng B không có sẽ bị mất; decimal bị làm tròn, timestamp mất timezone, enum bị gộp hoặc chuỗi bị chuẩn hóa cũng có thể làm đổi ý nghĩa nghiệp vụ.

Bài **Translator hai chiều và nguy cơ mất thông tin** thuộc chương **Message translator** trong module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, kèm kiểm thử và giám sát các nhánh xử lý.

**Thông điệp chính:** *Có hai Translator không có nghĩa có một cặp hàm nghịch đảo*. Hãy xác định mức độ bảo toàn cần thiết — **tương đương byte**, **tương đương cấu trúc**, **tương đương ý nghĩa nghiệp vụ**, hay chỉ **đủ thông tin cho một thao tác cụ thể**. Khi không đáp ứng được hợp đồng bảo toàn, hãy **báo mất thông tin, từ chối hoặc dùng extension/provenance đã được chấp thuận**, thay vì âm thầm trả một object có vẻ hợp lệ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Message Translator và phân biệt với Normalizer, Header Enricher, Router và serializer.
2. Phân biệt forward mapping, reverse mapping, round-trip và semantic equality.
3. Nhận diện phép dịch **lossless**, **lossy**, **không thể biểu diễn** hoặc **không xác định được phép dịch ngược**.
4. Chỉ ra nguyên nhân mất dữ liệu: thiếu field, đổi type, precision, enum, timezone, null/absent và normalization.
5. Thiết kế DTO v1/v2 minh họa cùng một đơn hàng nhưng khác biểu diễn.
6. Quy định amount major units ↔ minor units dùng `BigDecimal`, kiểm tra scale và overflow.
7. Không để enum/status mới bị ép thành trạng thái cũ gần giống nhưng sai nghiệp vụ.
8. Viết Java Translator hai chiều trả `TranslationOutcome` kèm loss report.
9. Phân biệt **loss report** và **validation error**: có dữ liệu bị loại là khác với không thể map an toàn.
10. Xây dựng Spring Integration Java DSL cho hai hướng dịch, xử lý lossy output trước business handler.
11. Viết JUnit 5 unit test, round-trip/semantic equivalence tests và channel integration tests.
12. Giữ ổn định event identity, tenant/correlation và headers qua ranh giới tích hợp.
13. Thiết kế strict/quarantine policy, retry, error channel, DLQ và Gateway response theo loại lỗi.
14. Quy định schema/version compatibility, provenance và chiến lược khôi phục thông tin bị mất.
15. Quan sát tỷ lệ mất thông tin, lỗi mapping, drift sau deploy và latency.

## 2. Tình huống: một đơn hàng, hai hệ thống

Một đối tác lâu năm gửi message:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": "SPRING-2026"
}
~~~

Hệ thống nội bộ dùng hợp đồng:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderId": "ORDER-101",
  "totalMinorUnits": 2500,
  "currency": "USD",
  "state": "PAID"
}
~~~

Các trường dễ map:

- `orderNo` → `orderId`, khi cả hai đều là business order identity.
- `"25.00" USD` → `2500` minor units, khi đơn vị và precision đã được xác nhận.
- `"P"` → `PAID`, khi đối tác xác định `P` là paid.

Nhưng nội bộ **không có nơi lưu** `legacyPromotionCode="SPRING-2026"`. Nếu dịch trở lại:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

thì bản dịch ngược **không giống đầu vào**. Mã ưu đãi lịch sử đã mất. Nếu một hệ thống khác cần mã đó để audit, khuyến mại hoặc điều chỉnh hóa đơn, việc loại âm thầm có thể làm sai nghiệp vụ dù compile và deserialize đều thành công.

~~~mermaid
flowchart LR
    A["LegacyOrderV1
    có promotionCode"] -->|"Translate A→B"| B["CanonicalOrderV2
    không có promotionCode"]
    B -->|"Translate B→A"| A2["LegacyOrderV1'
    promotionCode=null"]
    A2 -->|"So sánh"| LOSS["Khác A: mất field"]
~~~

Cũng có trường hợp B có **trạng thái mới `REFUNDED`** nhưng A chỉ hỗ trợ `N` (new), `P` (paid) và `C` (cancelled). Không nên tự gán `REFUNDED → C`: hủy trước thanh toán và hoàn tiền sau thanh toán có semantics khác nhau.

## 3. Thế nào là Translator hai chiều?

Ký hiệu:

- \(T_{AB}: A \rightarrow B\): dịch biểu diễn A sang B.
- \(T_{BA}: B \rightarrow A\): dịch biểu diễn B sang A.
- \(a \in A\), \(b \in B\): các message thuộc hai hợp đồng.

**Round-trip lý tưởng theo cấu trúc:**

\[
T_{BA}(T_{AB}(a)) = a
\]

và:

\[
T_{AB}(T_{BA}(b)) = b
\]

Nhưng trong tích hợp thực tế, nhiều phép dịch chỉ bảo đảm:

\[
T_{BA}(T_{AB}(a)) \approx_{\text{business}} a
\]

trong đó \(\approx_{\text{business}}\) là **tương đương theo những field và quy tắc nghiệp vụ đã công bố**, không phải giống từng byte.

### 3.1. Bốn mức độ bảo toàn

| Mức | Yêu cầu | Ví dụ |
|---|---|---|
| **Byte-for-byte** | Serialized bytes sau round-trip giống hệt | JSON giữ cả whitespace, field order, lexical number |
| **Structural** | Cùng fields/types/giá trị cấu trúc | Jackson DTO deep equality, có thể khác JSON field order |
| **Semantic** | Kết quả nghiệp vụ tương đương | `"025.000" USD` và `"25.00" USD` cùng giá trị tiền |
| **Task-sufficient** | Đủ thông tin cho việc cụ thể, không hứa khôi phục source | Tạo shipment chỉ cần orderId/address, không cần legacy promo |

Không được dùng chữ **lossless** mà không nêu rõ đang nói **mức nào**.

### 3.2. Hàm nghịch đảo có thể không tồn tại

Nếu A có 7 fields còn B chỉ có 6 fields và trường thứ bảy không được lưu ở đâu khác, nhiều giá trị A sẽ cho cùng một B:

~~~text
A1: promotionCode=SPRING-2026
A2: promotionCode=VIP-2026

T_AB(A1) = B
T_AB(A2) = B
~~~

Khi chỉ có B, không thể suy ra nó xuất phát từ A1 hay A2. Đây là vấn đề **mất khả năng phân biệt đầu vào**, không thể sửa bằng cách viết reverse Transformer phức tạp hơn.

### 3.3. Hai hướng có miền hợp lệ khác nhau

Một hàm A→B có thể xử lý mọi trạng thái v1, nhưng B→A chỉ xử lý tập con trạng thái v2 mà legacy hiểu:

~~~text
A.statusCode: N | P | C
B.state:      NEW | PAID | CANCELLED | REFUNDED

A→B: N/P/C đều có mapping
B→A: REFUNDED không có mapping hợp lệ
~~~

Không bảo đảm rằng hai Translator là **total functions** trên mọi giá trị. Có thể định nghĩa chúng là **partial mappings**, trả lỗi rõ khi gặp trường hợp ngoài miền biểu diễn.

## 4. Message Translator khác các pattern liên quan

| Thành phần | Nhiệm vụ | Quan hệ với dịch hai chiều |
|---|---|---|
| **Message Translator EIP** | Chuyển biểu diễn giữa hai hệ thống | Pattern tổng thể A↔B |
| **Spring Integration Transformer** | Thực thi phép đổi payload/message | Cài đặt một hoặc nhiều Translator |
| **Normalizer EIP** | Nhiều input formats hội tụ canonical form | Thường sử dụng nhiều Translators một chiều |
| **Envelope Wrapper** | Bọc payload với metadata xuyên boundary | Có thể wrap trước/unwrap sau dịch |
| **Header Enricher** | Thêm metadata ở headers | Không tự khôi phục field payload đã mất |
| **Content-based Router** | Chọn nhánh theo loại/phiên bản | Route A→B hoặc tới version adapter |
| **Filter** | Chấp nhận/bỏ thông điệp theo điều kiện | Chặn translation outcome không đáp ứng policy |
| **Idempotent Receiver** | Ngăn side effect trùng | Dùng event ID ổn định sau khi dịch |
| **Aggregator** | Gom các part theo group/release rule | Cần correlation/business ID không đổi |
| **Gateway** | Request-reply bridge | Cần reply path kể cả khi dịch thất bại |

Một Transformer có thể đổi kiểu Java `LegacyOrderV1` thành `CanonicalOrderV2`, nhưng **nó không tự kiểm chứng** rằng dữ liệu không bị mất hoặc rằng hai hàm biến đổi ngược nhau. Đó là trách nhiệm của **contract, implementation và tests**.

### 4.1. Translator khác serialize/deserialize thuần

Serialize:

~~~text
CanonicalOrderV2 Java object -> JSON bytes
~~~

Translate:

~~~text
LegacyOrderV1 semantics -> CanonicalOrderV2 semantics
~~~

Khi wire format A/B khác nhau, một adapter có thể vừa decode vừa translate; vẫn nên tách hai bước để xác định lỗi ở **parse/encoding** hay ở **semantic mapping**.

## 5. Bảy nhóm mất thông tin điển hình

### 5.1. Bỏ trường

A có `legacyPromotionCode`, B không có: mất field khi đi A→B. Không phải lỗi deserialize; schema B hợp lệ nhưng **không còn dữ liệu để tái tạo A**.

### 5.2. Trộn nhiều giá trị thành một

~~~text
A.status: PAID_BY_CARD | PAID_BY_BANK
B.status: PAID
~~~

Cả hai source statuses → cùng một target status. Dịch ngược từ PAID không thể biết phương thức thanh toán ban đầu.

### 5.3. Cắt ngắn, làm tròn hoặc overflow

~~~text
A.amount = 19.999 USD
B.amountMinorUnits = 2000
~~~

Nếu làm tròn thì **một phần độ chính xác đã bị loại**; có thể còn sai số theo quy tắc tài chính. Trong bài, Translator sẽ **reject** số không biểu diễn chính xác ở minor units, không tự làm tròn.

### 5.4. Chuẩn hóa chuỗi và mất lexical form

~~~text
A = "00025.00"
B = 2500 (cents)
A' = "25.00"
~~~

Cùng amount nghiệp vụ nhưng **không giữ bản biểu diễn chuỗi nguyên gốc**. Nếu chữ ký số hoặc audit đòi raw original bytes, cần giữ bản gốc riêng.

### 5.5. Mất timezone và độ chính xác thời gian

~~~text
A = "2026-11-21T09:00:00+07:00"
B = 2026-11-21T02:00:00Z
~~~

Hai giá trị là cùng `Instant` nhưng **không cùng offset text**. Nếu chỉ lưu ngày giờ địa phương không có timezone, đôi khi không thể khôi phục instant gốc.

### 5.6. Null, absent, empty và default

~~~text
A: field absent
B: field=null
A': field=""

A: discountPercent=0
B: discountPercent=null
~~~

Các trạng thái **không được cung cấp**, **cố ý để null**, **chuỗi rỗng** và **giá trị 0** có thể mang nghĩa khác nhau. Một codec bỏ qua null fields hoặc tự fill default có thể làm mất trạng thái ban đầu.

### 5.7. Collection/encoding/metadata

- Thứ tự list bị biến thành set → mất ordering và duplicate entries.
- Map key normalization làm hai keys khác nhau bị gộp.
- Unicode normalization có thể đổi byte sequence dù hiển thị giống nhau.
- Trường nhị phân chuyển qua String với charset sai → data corruption.
- JSON unknown fields bị bỏ → mất khả năng round-trip tới schema mới.
- Spring headers như `correlationId` hoặc `replyChannel` bị loại → mất routing context.
- Serialized signature không còn hợp lệ sau re-encode dù business data tương đương.

## 6. Hợp đồng ví dụ A↔B

Ta giới hạn bài vào **hai currencies USD/VND**, để đơn vị tiền và scale được giải thích rõ. Đây là **support matrix của ví dụ ứng dụng**, không phải tuyên bố mọi Currency ISO có cùng số decimal digits.

| Thuộc tính | Legacy A | Canonical B | Kết quả |
|---|---|---|---|
| Event ID | `eventId` | `eventId` | Giữ nguyên |
| Tenant | `tenantId` | `tenantId` | Giữ nguyên, phải auth tại ingress |
| Order ID | `orderNo` | `orderId` | Đổi tên, giữ business identity |
| Amount | `amountMajorText` | `totalMinorUnits` | Parse/convert chính xác |
| Currency | `currency` | `currency` | Bảo toàn |
| Trạng thái | `statusCode=N/P/C` | `state=NEW/PAID/CANCELLED/REFUNDED` | B→A không map được REFUNDED |
| Legacy promotion | `legacyPromotionCode` | **Không tồn tại** | Có nguy cơ mất dữ liệu |

### 6.1. Điều kiện để chấp nhận translation

- `eventId`, `tenantId`, `orderNo/orderId` là chuỗi nonblank, phù hợp grammar ID.
- `currency` là `USD` hoặc `VND` trong ví dụ.
- `amountMajorText` có decimal syntax hợp lệ, số dương, chuyển sang `long` minor units **chính xác**.
- `state` và `statusCode` thuộc tập đã công bố; unknown không được map thành PAID hay CANCELLED.
- Khi `legacyPromotionCode` có dữ liệu, A→B phải trả **loss report** hoặc reject theo chính sách.
- B→A không được hứa khôi phục promotion code lịch sử vì B không chứa nó.
- Business event ID không đổi khi forward cùng logical event.
- Bản dịch được phép **khác lexical amount text** khi giá trị tiền nghiệp vụ tương đương.

### 6.2. Một source event không nhất thiết tạo một event mới

Translator ở boundary thường **đổi representation**, không phát sinh business event mới. Đừng gọi `UUID.randomUUID()` làm eventId trong mỗi lần dịch. Khi service thật sự tạo một *derived event* (ví dụ ShipmentRequested từ OrderCreated), mới cấp event ID mới và liên kết causation phù hợp.

## 7. Money: major units → minor units không dùng double

Ví dụ `USD` có hai chữ số minor units và `VND` dùng số nguyên không có chữ số thập phân trong contract demo.

~~~text
USD:
  "25.00" major -> 2500 minor
  "25.001" major -> không biểu diễn chính xác (reject)

VND:
  "25000" major -> 25000 minor
  "25000.50" major -> không biểu diễn chính xác (reject)
~~~

Không làm:

~~~java
// Anti-pattern: floating-point có thể gây rounding sai.
double major = Double.parseDouble("19.99");
long cents = (long) (major * 100);
~~~

Cách phù hợp hơn là `BigDecimal` và kiểm tra chính xác:

~~~java
import java.math.BigDecimal;

public final class MoneyConversions {

    private MoneyConversions() {}

    public static long toMinorExact(
            String majorText,
            String currency) {

        if (majorText == null || majorText.isBlank()) {
            throw new TranslationContractException(
                    "AMOUNT_REQUIRED");
        }

        int scale = fractionDigits(currency);

        final BigDecimal major;
        try {
            major = new BigDecimal(majorText);
        }
        catch (NumberFormatException ex) {
            throw new TranslationContractException(
                    "AMOUNT_FORMAT_INVALID", ex);
        }

        if (major.signum() <= 0) {
            throw new TranslationContractException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        try {
            return major.movePointRight(scale)
                    .longValueExact();
        }
        catch (ArithmeticException ex) {
            throw new TranslationContractException(
                    "AMOUNT_NOT_EXACT_OR_OVERFLOW", ex);
        }
    }

    public static String toMajorCanonical(
            long minor,
            String currency) {

        if (minor <= 0) {
            throw new TranslationContractException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        int scale = fractionDigits(currency);
        return BigDecimal.valueOf(minor, scale)
                .toPlainString();
    }

    private static int fractionDigits(String currency) {
        return switch (currency) {
            case "USD" -> 2;
            case "VND" -> 0;
            default -> throw new TranslationContractException(
                    "CURRENCY_UNSUPPORTED");
        };
    }
}
~~~

Đây là **bộ chuyển đổi chính xác cho demo USD/VND**, không phải engine ngoại hối hay ISO 4217 tổng quát. Mở rộng currencies cần định nghĩa rounding/scale theo currency và hợp đồng nghiệp vụ, kiểm thử thay đổi đơn vị, overflow và currency-specific edge cases.

### 7.1. Exact minor units không đồng nghĩa giữ nguyên lexical string

~~~text
Input A: amountMajorText="0025.000"
B:       totalMinorUnits=2500
Output A': amountMajorText="25.00"
~~~

Theo monetary semantics, hai amount có thể tương đương; theo **byte/lexical equality** thì khác. Nếu audit cần raw `amountMajorText`, phải giữ bản gốc qua sidecar/extension hoặc lưu raw input, không thể tự tái tạo từ `long`.

### 7.2. Những tình huống bị reject

| Input | Currency | Kết quả |
|---|---|---|
| `"25.00"` | USD | 2500 |
| `"25.001"` | USD | `AMOUNT_NOT_EXACT_OR_OVERFLOW` |
| `"25000"` | VND | 25000 |
| `"25000.50"` | VND | `AMOUNT_NOT_EXACT_OR_OVERFLOW` |
| `"-1"` | USD | `AMOUNT_MUST_BE_POSITIVE` |
| `"abc"` | USD | `AMOUNT_FORMAT_INVALID` |
| `"1E1000"` | USD | Reject overflow/range |
| `"10"` | XXX | `CURRENCY_UNSUPPORTED` |

Phần lớn lỗi ở đây là **vi phạm contract mang tính xác định**; retry cùng payload nguyên trạng không tự chữa được.

## 8. Enum và trạng thái không thể dịch ngược

Hợp đồng Legacy:

~~~text
N = NEW
P = PAID
C = CANCELLED
~~~

Canonical có thêm `REFUNDED`:

~~~java
public enum OrderState {
    NEW,
    PAID,
    CANCELLED,
    REFUNDED
}
~~~

### 8.1. Forward mapping fail-fast

~~~java
public static OrderState toCanonicalState(
        String legacyCode) {

    return switch (legacyCode) {
        case "N" -> OrderState.NEW;
        case "P" -> OrderState.PAID;
        case "C" -> OrderState.CANCELLED;
        default -> throw new TranslationContractException(
                "LEGACY_STATE_UNSUPPORTED");
    };
}
~~~

### 8.2. Reverse mapping là một partial function

~~~java
public static String toLegacyState(
        OrderState state) {

    return switch (state) {
        case NEW -> "N";
        case PAID -> "P";
        case CANCELLED -> "C";
        case REFUNDED -> throw new TranslationContractException(
                "TARGET_STATE_NOT_REPRESENTABLE");
    };
}
~~~

Không map `REFUNDED` thành `CANCELLED` vì hai hành vi nghiệp vụ khác nhau. Nếu partner thật sự muốn một "generic terminal" state, phải có **approval và contract riêng**, kèm loss report. Không tự dùng `default -> "C"` để né việc cập nhật mapping.

### 8.3. Unknown code không đồng nghĩa `UNKNOWN`

Có những hệ thống hỗ trợ state `UNKNOWN` một cách hợp lệ; số khác coi unknown là dữ liệu hỏng. Nếu bạn thêm enum `UNKNOWN` vào canonical, cần định nghĩa rõ downstream được phép xử lý nó thế nào. Mặc định map mọi code chưa biết thành UNKNOWN rồi cho phép fulfilment chạy có thể gây side effects không đúng.

## 9. Null, absent, default và thứ tự dữ liệu

### 9.1. Optional source field

`legacyPromotionCode=null` có thể mang nghĩa "không có promotion" hoặc "không được cung cấp" tùy contract. Dữ liệu `legacyPromotionCode="SPRING-2026"` mất khi sang B vì B không có field tương ứng. Trong bản dịch ngược, bạn không thể biết code gốc và cũng không nên tự sinh promotion mới.

### 9.2. Absent khác explicit null

Ví dụ JSON:

~~~json
{"orderNo": "ORDER-101"}
~~~

và:

~~~json
{"orderNo": "ORDER-101", "legacyPromotionCode": null}
~~~

có thể map vào **cùng Java record với `legacyPromotionCode=null`** nếu Jackson deserializer không theo dõi field presence. Nếu cần exact round-trip distinction, phải dùng `JsonNode`/presence marker, schema union hoặc original raw representation.

### 9.3. Collections

Nếu A có một `List<LineItem>` bảo toàn thứ tự nhưng B chuyển thành `Set<LineItem>`, bạn có thể mất thứ tự và những phần tử lặp hợp lệ. Dù Reverse Transformer chuyển Set trở lại List, nó không có đủ thông tin để khôi phục sequence gốc.

### 9.4. Timestamps

Một hệ thống có `OffsetDateTime`, hệ thống kia chỉ giữ `Instant` hoặc `LocalDateTime`. Chuyển về UTC có thể đúng về **thời điểm xảy ra**, nhưng offset gốc không thể tự khôi phục. Mất timezone có thể tệ hơn khi local datetime rơi vào giờ DST bị lặp hoặc không tồn tại. Hợp đồng phải xác định chính xác cần bảo toàn *instant* hay *local wall-clock/timezone identity*.

## 10. Tiêu chuẩn kỹ thuật trước khi viết Translator

Nên tạo một **mapping ledger** làm cơ sở review:

| Field / invariant | A→B | B→A | Loss policy |
|---|---|---|---|
| `eventId` | Giữ nguyên | Giữ nguyên | Không chấp nhận mất |
| `tenantId` | Giữ nguyên, auth | Giữ nguyên | Không chấp nhận đổi |
| `orderNo/orderId` | Rename | Rename ngược | So value |
| `amountMajorText/minor` | Exact scale conversion | Canonical decimal text | Mất lexical form được công bố |
| `statusCode/state` | N/P/C → enum | REFUNDED không biểu diễn | Reject |
| `legacyPromotionCode` | Không có đích | Không tự khôi phục | Loss report/quarantine |
| `schemaVersion` | Input contract | Output contract | Ghi provenance |
| `MessageHeaders.ID` | Runtime-generated | Runtime-generated | Không dùng làm business event ID |
| `correlationId` | Preserve theo contract | Preserve theo contract | Không tạo ngẫu nhiên |
| `traceparent` | Propagate theo trust policy | Propagate theo trust policy | Không trộn business identity |

**Policy phải được quyết định trước khi dịch:** outbound target có cho phép mất promotion code không? Nếu không, A→B cần **reject/quarantine**, hoặc thiết kế một canonical extension/sidecar lưu dữ liệu đó. Nếu có, cần telemetry để biết trường nào bị loại và vì sao.
## 11. Java 17: DTO, loss report và exception

Ta dùng records để payload không bị đổi field sau khi tạo. Mỗi khai báo `public` top-level trong các code block sau cần đặt trong **file Java riêng cùng tên**, với Java 17+.

### 11.1. DTO nguồn A (legacy)

~~~java
public record LegacyOrderV1(
        String eventId,
        String tenantId,
        String orderNo,
        String amountMajorText,
        String currency,
        String statusCode,
        String legacyPromotionCode
) {}
~~~

### 11.2. DTO đích B (canonical)

~~~java
public record CanonicalOrderV2(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        OrderState state
) {}
~~~

Enum `OrderState` từ mục 8 hỗ trợ `NEW`, `PAID`, `CANCELLED` và `REFUNDED`. Việc B hỗ trợ trạng thái mới không đồng nghĩa A hiểu được trạng thái ấy.

### 11.3. Loss report không mang dữ liệu nhạy cảm

~~~java
public record TranslationLoss(
        String fieldName,
        String reasonCode
) {}
~~~

`fieldName` và `reasonCode` là vocabulary hữu hạn; không nhét raw promotion code, tên khách, token hay payload vào reason. Khi vận hành cần biết sự kiện cụ thể, dùng event identity ở audit store với quyền phù hợp.

### 11.4. Outcome có cả nguồn để xử lý quarantine

~~~java
import java.util.List;
import java.util.Objects;

public record TranslationOutcome<S, T>(
        S original,
        T translated,
        List<TranslationLoss> losses
) {
    public TranslationOutcome {
        Objects.requireNonNull(original, "original");
        Objects.requireNonNull(translated, "translated");
        losses = List.copyOf(losses);
    }

    public boolean lossless() {
        return losses.isEmpty();
    }
}
~~~

Ở ví dụ này, `TranslationOutcome` giữ `original` trong phạm vi nội bộ để quarantine/reconciliation có thể truy cập thông điệp gốc khi thực sự cần. **Không serialize cả outcome** sang partner hoặc business topic nếu họ chỉ mong DTO `translated`: vô tình gửi `original` sẽ làm lộ nội dung legacy.

Bản thân `lossless()` chỉ nghĩa **không có mất field nào mà Translator này đã đánh dấu theo contract**, chứ không bảo đảm byte-for-byte equality; ví dụ lexical amount vẫn có thể bị canonicalize dù list loss rỗng.

### 11.5. Contract exception

~~~java
public final class TranslationContractException
        extends RuntimeException {

    private final String reasonCode;

    public TranslationContractException(
            String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public TranslationContractException(
            String reasonCode,
            Throwable cause) {
        super(reasonCode, cause);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

Bảng phân biệt outcome:

| Kết quả | Ví dụ | Hành động |
|---|---|---|
| Translated + no flagged loss | A không có promo code | Có thể đưa tới business handler sau validation |
| Translated + flagged loss | Có `legacyPromotionCode` nhưng B không hỗ trợ | Quarantine/explicit approval |
| Contract exception | Legacy status `"H"` không biết | Reject, không tạo business output |
| Contract exception | B state `REFUNDED` không map A | Unsupported reverse mapping |
| Infrastructure failure | Mapping registry/service tạm hỏng | Bounded retry, không coi là loss field |

Một loss report **không phải exception**: có thể tạo giá trị B hợp lệ nhưng **không được phép đưa vào business flow** nếu chính sách cấm mất field.

## 12. Translator hai chiều với quyết định mất dữ liệu rõ ràng

### 12.1. Enum mapper

~~~java
public final class OrderStateMappings {

    private OrderStateMappings() {}

    public static OrderState toCanonicalState(
            String legacyCode) {

        if (legacyCode == null) {
            throw new TranslationContractException(
                    "LEGACY_STATE_REQUIRED");
        }

        return switch (legacyCode) {
            case "N" -> OrderState.NEW;
            case "P" -> OrderState.PAID;
            case "C" -> OrderState.CANCELLED;
            default -> throw new TranslationContractException(
                    "LEGACY_STATE_UNSUPPORTED");
        };
    }

    public static String toLegacyState(
            OrderState state) {

        if (state == null) {
            throw new TranslationContractException(
                    "CANONICAL_STATE_REQUIRED");
        }

        return switch (state) {
            case NEW -> "N";
            case PAID -> "P";
            case CANCELLED -> "C";
            case REFUNDED -> throw new TranslationContractException(
                    "TARGET_STATE_NOT_REPRESENTABLE");
        };
    }
}
~~~

Enum mapping không dựa trên `name()`/`valueOf()` khi các hệ thống dùng các vocabularies khác nhau. Trạng thái mới `REFUNDED` được từ chối có chủ đích thay vì giả vờ là `CANCELLED`.

### 12.2. PartnerOrderTranslator

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public final class PartnerOrderTranslator {

    private static final Pattern IDENTIFIER =
            Pattern.compile("[A-Za-z0-9._-]+");

    public TranslationOutcome<LegacyOrderV1, CanonicalOrderV2>
    toCanonical(LegacyOrderV1 source) {

        if (source == null) {
            throw new TranslationContractException(
                    "LEGACY_PAYLOAD_REQUIRED");
        }

        requireId(source.eventId(), "EVENT_ID_INVALID");
        requireId(source.tenantId(), "TENANT_ID_INVALID");
        requireId(source.orderNo(), "ORDER_ID_INVALID");

        // Kiểm tra decimal exact, currency scale và overflow.
        long minor = MoneyConversions.toMinorExact(
                source.amountMajorText(),
                source.currency());

        OrderState state =
                OrderStateMappings.toCanonicalState(
                        source.statusCode());

        CanonicalOrderV2 translated = new CanonicalOrderV2(
                source.eventId(),
                source.tenantId(),
                source.orderNo(),
                minor,
                source.currency(),
                state);

        List<TranslationLoss> losses = new ArrayList<>();

        if (source.legacyPromotionCode() != null
                && !source.legacyPromotionCode().isBlank()) {
            losses.add(new TranslationLoss(
                    "legacyPromotionCode",
                    "FIELD_NOT_REPRESENTABLE_IN_CANONICAL"));
        }

        return new TranslationOutcome<>(
                source, translated, losses);
    }

    public TranslationOutcome<CanonicalOrderV2, LegacyOrderV1>
    toLegacy(CanonicalOrderV2 source) {

        if (source == null) {
            throw new TranslationContractException(
                    "CANONICAL_PAYLOAD_REQUIRED");
        }

        requireId(source.eventId(), "EVENT_ID_INVALID");
        requireId(source.tenantId(), "TENANT_ID_INVALID");
        requireId(source.orderId(), "ORDER_ID_INVALID");

        String amountText =
                MoneyConversions.toMajorCanonical(
                        source.totalMinorUnits(),
                        source.currency());

        String legacyStatus =
                OrderStateMappings.toLegacyState(
                        source.state());

        LegacyOrderV1 translated = new LegacyOrderV1(
                source.eventId(),
                source.tenantId(),
                source.orderId(),
                amountText,
                source.currency(),
                legacyStatus,
                null);

        // Không có legacy promotion field ở source B để mất.
        // Nhưng hàm này KHÔNG cam kết tái tạo A lịch sử.
        return new TranslationOutcome<>(
                source, translated, List.of());
    }

    private static void requireId(
            String id, String error) {

        if (id == null
                || !IDENTIFIER.matcher(id).matches()) {
            throw new TranslationContractException(error);
        }
    }
}
~~~

**Đọc code đúng ngữ nghĩa:**

- `toCanonical` giữ event ID, tenant ID và business order ID.
- `MoneyConversions.toMinorExact` từ mục 7 dùng `BigDecimal`, không âm thầm làm tròn.
- `OrderStateMappings` từ chối trạng thái không biết.
- Legacy promotion code **không thể đại diện trong B**: bản dịch trả B kèm `TranslationLoss`, cho policy quyết định.
- `toLegacy` tạo message legacy hợp lệ từ B cho **một outbound operation mới**, nhưng không có thông tin để khôi phục promotion code của một A từng xuất hiện trong quá khứ. Trường `legacyPromotionCode=null` không phải bằng chứng original legacy không có promo.
- `toLegacy` từ chối `REFUNDED`: không phát một `CANCELLED` giả.

**Lưu ý về `lossless()`:** Nếu `toLegacy` nhận một B đã trải qua việc mất promo khi đi A→B, nó sẽ không thấy dấu vết đó trong B. Do vậy **chỉ nhìn outcome của lượt B→A là không đủ để kết luận round-trip A→B→A lossless**. Phải giữ loss report/provenance của lượt đầu qua boundary nếu cần xác minh round-trip.

### 12.3. Quarantine không phải "đã xử lý thành công"

Vì `TranslationOutcome` giữ cả input gốc, một loss report có thể được route tới quarantine để operator soát dữ liệu, tạo mapping bổ sung hoặc yêu cầu partner làm rõ. Nhưng **chưa được ACK như business success** nếu hợp đồng bảo đảm không làm mất order. Chính sách ACK/NACK là của transport adapter và transaction, không phải của Java record hay việc gửi vào QueueChannel.

### 12.4. Không thêm default từ ngữ cảnh bất định

Nếu Legacy A không có currency và B yêu cầu currency, không nên đoán từ timezone, quốc gia của IP hoặc người dùng. Một currency mặc định chỉ hợp lệ khi **contract của một input endpoint đáng tin** bảo đảm mọi amount là một currency cố định, kèm version/schema rule. Dùng default tùy tiện có thể gây lỗi tài chính nghiêm trọng.

## 13. Unit test: phép dịch và loss report

Các test này chỉ dùng JUnit 5 và các Java classes ở trên; chưa cần Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class PartnerOrderTranslatorTest {

    private final PartnerOrderTranslator translator =
            new PartnerOrderTranslator();

    private LegacyOrderV1 sample(String promotion) {
        return new LegacyOrderV1(
                "evt-order-1001",
                "tenant-a",
                "ORDER-101",
                "25.00",
                "USD",
                "P",
                promotion);
    }

    @Test
    void nonEmptyLegacyPromotionIsReportedAsLoss() {
        LegacyOrderV1 input = sample("SPRING-2026");

        var outcome = translator.toCanonical(input);

        assertFalse(outcome.lossless());
        assertEquals(
                "FIELD_NOT_REPRESENTABLE_IN_CANONICAL",
                outcome.losses().get(0).reasonCode());
        assertEquals(
                "legacyPromotionCode",
                outcome.losses().get(0).fieldName());

        assertEquals(
                2500L,
                outcome.translated().totalMinorUnits());
        assertEquals(
                OrderState.PAID,
                outcome.translated().state());

        // Original được giữ trong outcome nội bộ để quarantine.
        assertEquals(
                "SPRING-2026",
                outcome.original().legacyPromotionCode());
    }

    @Test
    void noLegacyPromotionCanPassLossPolicy() {
        var outcome = translator.toCanonical(sample(null));

        assertTrue(outcome.lossless());
        assertEquals(
                "evt-order-1001",
                outcome.translated().eventId());
        assertEquals(
                "ORDER-101",
                outcome.translated().orderId());
    }

    @Test
    void amountWithExtraFractionalCentIsRejected() {
        LegacyOrderV1 input = new LegacyOrderV1(
                "evt-order-1002", "tenant-a",
                "ORDER-102", "25.001", "USD",
                "P", null);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toCanonical(input));

        assertEquals(
                "AMOUNT_NOT_EXACT_OR_OVERFLOW",
                exception.reasonCode());
    }

    @Test
    void unsupportedLegacyStatusCannotBecomePaid() {
        LegacyOrderV1 input = new LegacyOrderV1(
                "evt-order-1003", "tenant-a",
                "ORDER-103", "10.00", "USD",
                "H", null);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toCanonical(input));

        assertEquals(
                "LEGACY_STATE_UNSUPPORTED",
                exception.reasonCode());
    }

    @Test
    void refundedIsNotMappedToCancelled() {
        CanonicalOrderV2 source = new CanonicalOrderV2(
                "evt-refund-1001",
                "tenant-a",
                "ORDER-101",
                2500,
                "USD",
                OrderState.REFUNDED);

        TranslationContractException exception =
                assertThrows(
                        TranslationContractException.class,
                        () -> translator.toLegacy(source));

        assertEquals(
                "TARGET_STATE_NOT_REPRESENTABLE",
                exception.reasonCode());
    }

    @Test
    void exactDomainRoundTripPreservesBusinessFields() {
        LegacyOrderV1 source = sample(null);

        var canonical = translator.toCanonical(source);
        var back = translator.toLegacy(
                canonical.translated());

        assertEquals(
                source.eventId(), back.translated().eventId());
        assertEquals(
                source.tenantId(), back.translated().tenantId());
        assertEquals(
                source.orderNo(), back.translated().orderNo());
        assertEquals(
                source.currency(), back.translated().currency());
        assertEquals(
                source.statusCode(), back.translated().statusCode());
        assertEquals(
                source.amountMajorText(),
                back.translated().amountMajorText());

        assertEquals(
                source, back.translated());
    }

    @Test
    void lexicalAmountCanChangeDespiteSemanticEquality() {
        LegacyOrderV1 source = new LegacyOrderV1(
                "evt-order-1004", "tenant-a",
                "ORDER-104", "0025.000", "USD",
                "P", null);

        var canonical = translator.toCanonical(source);
        var back = translator.toLegacy(
                canonical.translated());

        assertEquals(
                2500L, canonical.translated().totalMinorUnits());

        assertEquals(
                "25.00", back.translated().amountMajorText());

        // Khác lexical bytes, dù giá trị tiền cùng 25.00 USD.
        assertNotEquals(
                source.amountMajorText(),
                back.translated().amountMajorText());
    }
}
~~~

### 13.1. Vì sao test đầu không gọi `assertEquals(A, A')`?

Vì có `legacyPromotionCode` mà canonical không lưu, `A'` sẽ không giống `A`. Cố viết một test khẳng định equality cho mọi source và sau đó "sửa" Translator bằng cách gán một promotion mặc định sẽ che lỗi thực sự. Test cần phản ánh **miền dữ liệu có thể bảo toàn**, và nêu rõ khi nào output khác input theo policy.

### 13.2. Test canonical reverse riêng

Một B được tạo từ nguồn nội bộ có thể chứa `REFUNDED` mà legacy không diễn đạt được. Cần test không chỉ A→B→A, mà còn B→A→B:

~~~java
@Test
void canonicalReverseRoundTripWorksForSharedStates() {
    CanonicalOrderV2 initial = new CanonicalOrderV2(
            "evt-order-2001", "tenant-a",
            "ORDER-201", 7500L, "USD",
            OrderState.NEW);

    CanonicalOrderV2 result =
            translator.toCanonical(
                    translator.toLegacy(initial).translated())
                    .translated();

    assertEquals(initial, result);
}
~~~

Thêm method này vào test class ở trên. Với `REFUNDED`, round-trip B→A→B không tồn tại bởi reverse mapping đã reject. Đó là hành vi đúng theo support matrix.

## 14. Java DSL: hai flows với policy trước khi vào nghiệp vụ

Dùng Spring Integration Java DSL triển khai hai đường:

~~~text
partner.orders.in
    -> Translator A→B
    -> TranslationOutcome
    -> lossless?
         yes -> extract translated CanonicalOrderV2 -> orders.canonical.accepted
         no  -> orders.translation.quarantine

orders.canonical.out
    -> Translator B→A
    -> TranslationOutcome
    -> extract translated LegacyOrderV1
    -> partner.orders.out
~~~

**Quan trọng:** chỉ có `translated` được đưa ra business/outbound channels; `TranslationOutcome` có original payload và loss details chỉ tồn tại trong internal validation/quarantine path.

### 14.1. Spring configuration

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
public class BidirectionalTranslatorConfiguration {

    @Bean
    public PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator();
    }

    @Bean(name = "partner.orders.in")
    public MessageChannel legacyInbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.canonical.accepted")
    public PollableChannel canonicalAccepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.translation.quarantine")
    public PollableChannel quarantinedTranslations() {
        return new QueueChannel();
    }

    @Bean(name = "orders.canonical.out")
    public MessageChannel canonicalOutbound() {
        return new DirectChannel();
    }

    @Bean(name = "partner.orders.out")
    public PollableChannel partnerOutbound() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow legacyToCanonicalFlow(
            PartnerOrderTranslator translator) {

        return IntegrationFlow
                .from("partner.orders.in")
                .transform(
                        LegacyOrderV1.class,
                        translator::toCanonical)
                .filter(
                        TranslationOutcome.class,
                        TranslationOutcome::lossless,
                        filter -> filter.discardChannel(
                                "orders.translation.quarantine"))
                .transform(
                        TranslationOutcome.class,
                        TranslationOutcome::translated)
                .channel("orders.canonical.accepted")
                .get();
    }

    @Bean
    public IntegrationFlow canonicalToPartnerFlow(
            PartnerOrderTranslator translator) {

        return IntegrationFlow
                .from("orders.canonical.out")
                .transform(
                        CanonicalOrderV2.class,
                        translator::toLegacy)
                .transform(
                        TranslationOutcome.class,
                        TranslationOutcome::translated)
                .channel("partner.orders.out")
                .get();
    }
}
~~~

**Phạm vi demo:** `DirectChannel` + `QueueChannel` trong một JVM để kiểm thử translation. Không phải broker consumer/HTTP adapter hoàn chỉnh; không có transaction, persistent quarantine, ACK hoặc remote authentication. Đầu ra `orders.translation.quarantine` đang chứa `TranslationOutcome`, **không phải ErrorMessage**. Nếu error xảy ra khi gọi `toCanonical` hoặc `toLegacy`, exception đi theo error handling khác chứ không được tự đưa vào discard channel.

### 14.2. Vì sao Filter `lossless` đứng sau Translator?

Một Source A có thể map thành B có cấu trúc hợp lệ nhưng đã mất `legacyPromotionCode`. Nếu flow đưa ngay B tới business handler, không còn biết thông tin nào đã bị loại. Bước Filter nhận **outcome có thông tin loss** trước khi chỉ lấy `translated`.

Trong production, policy có thể tinh vi hơn: cho phép mất một trường đã được chủ business phê duyệt nhưng cấm mất trường dùng cho thanh toán/audit. Hãy dùng **typed loss severity/allowlist** và approval, không thay `lossless` bằng một điều kiện khó giải thích.

### 14.3. Quarantine phải có xử lý và retention

`QueueChannel` là fixture trong test, không bảo đảm sống qua restart. Nếu xử lý dữ liệu thật, quarantine cần store bền vững, reason code, event ID, source/version, quyền truy cập, mã hóa và replay policy. Nếu business không cho phép bỏ một message, chỉ chuyển tới in-memory quarantine rồi ACK broker có thể vẫn làm mất việc khi process chết.

### 14.4. Reverse flow không chứng minh round-trip của A gốc

Luồng B→A cho output LegacyOrderV1 có `legacyPromotionCode=null` do B không có field đó. Điều này đúng cho trường hợp **xuất một canonical order mới sang partner**. Nếu bạn dùng B này để cập nhật một legacy A đã có promotion code, phải lấy record gốc qua trusted store hoặc extension; nếu không có, không được giả rằng PartnerOrderTranslator có thể khôi phục nó.

## 15. Integration test qua Spring Integration channels

Test dưới đây kiểm tra actual routing/transformer wiring và việc lossy output không lọt vào canonical business channel.

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

@SpringJUnitConfig(
        classes = BidirectionalTranslatorConfiguration.class)
class BidirectionalTranslatorFlowTest {

    @Autowired
    @Qualifier("partner.orders.in")
    MessageChannel partnerInbound;

    @Autowired
    @Qualifier("orders.canonical.accepted")
    PollableChannel canonicalAccepted;

    @Autowired
    @Qualifier("orders.translation.quarantine")
    PollableChannel quarantine;

    @Autowired
    @Qualifier("orders.canonical.out")
    MessageChannel canonicalOutbound;

    @Autowired
    @Qualifier("partner.orders.out")
    PollableChannel partnerOutbound;

    private LegacyOrderV1 legacy(String promo) {
        return new LegacyOrderV1(
                "evt-order-3001", "tenant-a",
                "ORDER-301", "19.99", "USD",
                "P", promo);
    }

    @Test
    void reversibleInputReachesCanonicalChannel() {
        assertTrue(partnerInbound.send(
                MessageBuilder.withPayload(legacy(null))
                        .build()));

        Message<?> accepted = canonicalAccepted.receive(1000);
        assertNotNull(accepted);
        assertInstanceOf(
                CanonicalOrderV2.class, accepted.getPayload());

        CanonicalOrderV2 order =
                (CanonicalOrderV2) accepted.getPayload();

        assertEquals(1999L, order.totalMinorUnits());
        assertEquals(OrderState.PAID, order.state());
        assertEquals("evt-order-3001", order.eventId());
        assertNull(quarantine.receive(0));
    }

    @Test
    void lossyInputIsQuarantinedBeforeBusinessOutput() {
        assertTrue(partnerInbound.send(
                MessageBuilder.withPayload(
                        legacy("SPRING-2026"))
                        .build()));

        Message<?> rejected = quarantine.receive(1000);
        assertNotNull(rejected);
        assertInstanceOf(
                TranslationOutcome.class,
                rejected.getPayload());

        TranslationOutcome<?, ?> outcome =
                (TranslationOutcome<?, ?>) rejected.getPayload();

        assertFalse(outcome.lossless());
        assertEquals(
                "legacyPromotionCode",
                outcome.losses().get(0).fieldName());

        assertNull(canonicalAccepted.receive(0));
    }

    @Test
    void canonicalOrderCanBeTranslatedForPartner() {
        CanonicalOrderV2 canonical =
                new CanonicalOrderV2(
                        "evt-order-3002", "tenant-a",
                        "ORDER-302", 2500L, "USD",
                        OrderState.NEW);

        assertTrue(canonicalOutbound.send(
                MessageBuilder.withPayload(canonical)
                        .build()));

        Message<?> translated = partnerOutbound.receive(1000);
        assertNotNull(translated);
        assertInstanceOf(
                LegacyOrderV1.class,
                translated.getPayload());

        LegacyOrderV1 legacy =
                (LegacyOrderV1) translated.getPayload();

        assertEquals("25.00", legacy.amountMajorText());
        assertEquals("N", legacy.statusCode());
        assertEquals(
                "evt-order-3002", legacy.eventId());
        assertNull(legacy.legacyPromotionCode());
    }

    @Test
    void reverseUnsupportedStateDoesNotEmitFakeCancellation() {
        CanonicalOrderV2 refunded =
                new CanonicalOrderV2(
                        "evt-refund-3003", "tenant-a",
                        "ORDER-303", 5000L, "USD",
                        OrderState.REFUNDED);

        assertThrows(RuntimeException.class,
                () -> canonicalOutbound.send(
                        MessageBuilder.withPayload(refunded)
                                .build()));

        assertNull(partnerOutbound.receive(0));
    }
}
~~~

Test trên không yêu cầu broker thật. Khi có `SpringJUnitConfig` và các channel beans, nó kiểm chứng các nhánh theo DTO runtime types. Nếu test suite dùng cached ApplicationContext và shared QueueChannel, cần drain/cleanup hoặc đặt unique events để tránh leftover messages giữa tests, nhất là khi chạy song song.

### 15.1. Integration test không thay contract/wire tests

Ngay cả khi Java method chạy đúng, serializer có thể đổi `amountMajorText="25.00"` thành JSON number `25.0`, bỏ null hoặc đổi field name. Cần test **serialized JSON/Avro/Protobuf** với sample thực của hai phía, không chỉ compare Java records trong JVM.

### 15.2. Invalid input không tự vào quarantine của Filter

Nếu `toCanonical` ném `TranslationContractException` vì số tiền không chính xác, Filter `lossless` chưa được gọi. Đây là **translation failure**; nó đi theo Spring Integration exception/error channel tùy topology, không tự đến `orders.translation.quarantine`. Muốn mọi invalid event có bản ghi điều tra, cấu hình một error flow/quarantine adapter riêng hoặc classify **trước** Transformer.

## 16. Header, metadata và correlation qua hai hướng

Spring Integration truyền các thông tin điều phối bằng `MessageHeaders`, nhưng không nên giả chúng là dữ liệu nghiệp vụ hoặc được bảo toàn qua mọi serializer/hop.

| Metadata | A→B | B→A | Lưu ý |
|---|---|---|---|
| `eventId` trong payload | Preserve | Preserve | Business event identity; không sinh mới |
| `tenantId` | Preserve + authenticate | Preserve | Không tin untrusted payload một cách mù |
| `orderId` | Map từ `orderNo` | Map thành `orderNo` | Stable group key cho Aggregator |
| `businessCorrelationId` | Preserve theo contract | Preserve | Phân biệt với schema version/trace |
| `traceparent` | Chuyển qua tracing adapter khi được phép | Tương tự | Không dùng làm idempotency key |
| Spring `MessageHeaders.ID` | Có thể đổi khi transform | Có thể đổi | Không phải logical event ID |
| `replyChannel`/`errorChannel` | Runtime-local | Runtime-local | Chỉ copy khi topology/namespace phù hợp |
| `contentType` | Cập nhật sau serialization | Cập nhật | Tránh stale content type |
| `schemaVersion` | Input version A → output version B | B → A | Không giữ version cũ cho payload mới |
| `Authorization`/secrets | Không copy tùy tiện | Không copy tùy tiện | Authentication từng hop |

### 16.1. Spring Transformer và header propagation

Khi `.transform(PartnerOrderV1.class, ...)` trả về **payload mới**, Spring Integration có thể giữ các input headers trên output message theo cơ chế của Transformer endpoint, nhưng việc header nào tiếp tục tồn tại còn phụ thuộc implementation, việc trả `Message<?>` hay chỉ payload, serialization và adapter mapping.

**Không xem header propagation mặc định là một chính sách bảo mật**. Trước khi gửi ra transport khác, dùng explicit allowlist/mapper cho business correlation và tracing context được phép. Không copy raw `replyChannel`/`errorChannel` objects hoặc bearer tokens ra broker tùy ý.

### 16.2. Schema version phải mô tả payload hiện tại

Nếu A là schema v1 và B là schema v2:

~~~text
Inbound:
  payload=LegacyOrderV1
  schemaVersion=1

Outbound:
  payload=CanonicalOrderV2
  schemaVersion=2
  sourceSchemaVersion=1
~~~

Nếu chỉ đổi Java type mà không đổi header `schemaVersion`, downstream có thể chọn sai decoder. `sourceSchemaVersion` hữu ích cho audit/provenance, nhưng không thay thế current schema version.

### 16.3. Correlation không được phụ thuộc lexical amount

Một business key nên dựa trên trusted tenant/order ID, không dùng số tiền hoặc trạng thái làm correlation key: amount có thể đổi biểu diễn qua Translator và trạng thái có thể tiến triển. Nếu các event Payment/Inventory có IDs riêng, cần canonical business identity mapping trước Aggregator.

### 16.4. Cần preserve source provenance nhưng không copy source secrets

Có thể thêm `sourceSystem`, `sourceSchemaVersion` và `translationVersion` trong metadata nội bộ, theo namespace/trust policy. Tuy nhiên nếu dữ liệu này có rủi ro cardinality hoặc chứa identifiers nhạy cảm, giới hạn logs/headers và retention.

## 17. Strict mode, tolerant mode và loss budget

**Không có một policy loss duy nhất hợp lệ cho mọi use case.**

### 17.1. Strict translation

Yêu cầu:

- Mọi required field phải có mapping chính xác.
- Unknown enum/state bị reject.
- Money conversion không rounding.
- Legacy promotion code có dữ liệu nhưng canonical thiếu field → reject hoặc quarantine.
- Chỉ sau khi được phê duyệt business output mới tới downstream.

Phù hợp cho payment, fulfillment, legal/audit data hoặc event không được phép giảm nghĩa.

### 17.2. Tolerant translation có kiểm soát

Có thể cho phép:

- Canonicalize lexical amount `"0025.000" → "25.00"`.
- Bỏ một field *chỉ dùng cho giao diện cũ* nếu business owner phê duyệt.
- Map một enum alias đã có contract.
- Giữ unknown optional fields trong extension bag khi schema mới cho phép.

Nhưng tolerant không đồng nghĩa **bỏ qua bất kỳ lỗi nào**. Phải có:

1. Loss type/reason rõ.
2. Owner chấp thuận loại mất thông tin.
3. Version scope và thời hạn chính sách.
4. Tests và observability.
5. Cơ chế giữ original khi cần replay/audit.

### 17.3. Loss budget

Một tổ chức có thể chấp nhận 0 lost monetary events nhưng cho phép một số optional display fields bị bỏ trong một batch migration. Tuy nhiên "0.1% được mất trường" không nhất thiết phù hợp dữ liệu quan trọng: policy nên xét **từng field và mức độ ảnh hưởng nghiệp vụ**, không chỉ tỷ lệ tổng message.

### 17.4. Đừng tự lặng lẽ "fix" dữ liệu sai

Nếu `amountMajorText="25.005"` không thể chuyển thành integer cents một cách chính xác, đừng làm tròn sang 2501 rồi coi là successful translation trừ khi hợp đồng tài chính đã quy định rounding mode và business effect. Nếu một mã trạng thái không hiểu, đừng map nó thành NEW chỉ để handler nhận được event.

## 18. Khi nào round-trip test có giá trị?

Một round-trip test nên được viết có **miền dữ liệu và equality relation** cụ thể:

### 18.1. A→B→A cho miền A tương thích

~~~text
Source A có promotionCode=null,
statusCode thuộc N/P/C,
amount có lexical canonical form,
currency được hỗ trợ

-> A' có thể bằng A theo record equality
~~~

Với source promotion code không-null hoặc amount có leading zeros, không được kỳ vọng exact equality.

### 18.2. B→A→B cho miền B legacy biểu diễn được

~~~text
Source B state thuộc NEW/PAID/CANCELLED
-> B' có thể bằng B

Source B state=REFUNDED
-> Reverse Translator reject; round trip không tồn tại
~~~

### 18.3. Property-based testing thay vài example tests

Với nhiều sample amount và status, có thể kiểm tra:

- `toMinorExact(toMajorCanonical(minor,currency),currency)==minor` cho mọi minor hợp lệ.
- A→B giữ eventId/tenantId/orderId.
- Không map unexpected enum thành một giá trị khác.
- Loss list có reason code khi promotion không thể đại diện.
- Việc retry cùng input sinh cùng output/loss list (deterministic).
- Không có side effect trong Translator.
- Input có dấu/giới hạn numeric không làm overflow âm thầm.

Có thể dùng jqwik hoặc QuickTheories cho property tests nếu project có dependency, nhưng **JUnit 5 parameterized tests** với boundary samples cũng rất có ích.
## 19. Round-trip JSON/Avro khác round-trip Java object

Một `LegacyOrderV1` object có thể khớp sau A→B→A, nhưng JSON bytes của message ban đầu vẫn khác vì serializer:

- Đổi field order.
- Bỏ fields null.
- Đổi `"25.00"` thành `"25"` nếu amount bị parse thành numeric.
- Chuyển snake_case/camelCase theo naming policy.
- Đổi charset hoặc Unicode normalization.
- Bỏ unknown fields.
- Không giữ comments/whitespace của source JSON.
- Chuyển integer lớn sang floating-point trong một JavaScript client.

### 19.1. Test contract trên wire representation

Giả sử một legacy producer gửi:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "0025.000",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

Nếu bạn parse → translate → translate back → serialize bằng Jackson, output có thể là:

~~~json
{
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMajorText": "25.00",
  "currency": "USD",
  "statusCode": "P",
  "legacyPromotionCode": null
}
~~~

Business amount bằng nhau nhưng raw bytes khác. Nếu hệ thống dùng **chữ ký trên body gốc**, phép dịch đã phá byte equality. Nếu audit yêu cầu bằng chứng chính xác về request nhận, lưu **original signed bytes** theo chính sách bảo mật/retention, không trông chờ serialize ngược từ DTO.

### 19.2. Deserialize có thể mất thông tin trước cả Translator

Một `ObjectMapper` với unknown-properties policy bỏ qua field chưa biết có thể làm mất `futureAttribute` ngay lúc đọc JSON into LegacyOrderV1, **trước** khi `PartnerOrderTranslator` chạy. Khi đó loss report của Translator không có cơ hội biết field đã mất.

Nếu cần detect unknown fields, cấu hình decoder strict/validate schema, hoặc parse vào `JsonNode`/extension fields và ghi nhận chúng trước khi tạo typed DTO. Không thể cam kết lossless end-to-end chỉ bằng việc kiểm tra code Translator nếu **codec đầu vào** đã vứt dữ liệu.

### 19.3. Binary formats và registry

Avro/Protobuf có schema evolution rules, defaults, unknown fields behavior và encoding khác JSON. Version/schema ID ở registry chỉ giúp chọn đúng codec và kiểm tra compatibilities; nó **không tự chứng minh** rằng mapping nghiệp vụ từ v1 sang canonical v2 là hoàn toàn đảo ngược.

Test nên có fixtures được xuất **từ producer thật** cho các versions còn được hỗ trợ, cùng cases field renamed/deprecated và các enum values mới.

## 20. Làm gì khi bắt buộc khôi phục thông tin nguồn?

Khi A có dữ liệu mà B không biểu diễn, có một số chiến lược. Không có chiến lược nào miễn phí về độ phức tạp, bảo mật hay retention.

### 20.1. Mở rộng canonical schema

Nếu `legacyPromotionCode` thực sự có ý nghĩa lâu dài, bổ sung một field có contract rõ vào B:

~~~text
CanonicalOrderV3
  ...
  legacyPromotionCode: optional
  provenance.sourceSchemaVersion: 1
~~~

Ưu điểm: thông tin di chuyển cùng business record. Nhược điểm: mọi downstream consumers có thể chịu tác động schema evolution. Không nhét mọi legacy field vào canonical DTO mà không xét domain ownership và privacy.

### 20.2. Extension bag có namespace

~~~json
{
  "orderId": "ORDER-101",
  "totalMinorUnits": 2500,
  "extensions": {
    "partner-a/v1/legacyPromotionCode": "SPRING-2026"
  }
}
~~~

Ưu điểm: giữ dữ liệu dành riêng một hệ thống ở ranh giới. Nhược điểm:

- Key/value schema có thể khó govern.
- Dễ bị lạm dụng chứa PII/secrets.
- Downstream có thể vô tình phụ thuộc vào extension không ổn định.
- Cần owner/version/collision policy.
- Không nên serialize extension cho mọi người nhận nếu không được phép.

### 20.3. Sidecar/provenance store

Lưu thông tin không có chỗ trong B vào storage riêng:

~~~text
Business key:
  (tenantId, sourceId, eventId)

Canonical record:
  CanonicalOrderV2

Provenance/sidecar:
  originalLegacyPromotionCode
  originalAmountMajorText
  sourceSchemaVersion
  rawPayloadHash
  sourceReceivedAt
~~~

Khi cần tái tạo A, truy vấn sidecar theo **trusted immutable key**. Đây không phải một phép dịch chỉ dựa trên B nữa: cần một **nguồn dữ liệu bổ sung**, có retention, consistency, authorization, backup và recovery.

Nếu sidecar được ghi trước business transaction nhưng business action fail, có thể tồn tại provenance mồ côi; nếu ghi sau mà crash, business record có thể thiếu provenance. Nếu chúng ở **cùng DB**, dùng transaction chung khi cần nguyên tử. Nếu ở hai hệ thống, cần outbox/reconciliation/compensation policy.

### 20.4. Lưu raw original có kiểm soát

Nếu phải chứng minh chính xác bytes/chữ ký của A, một bản original raw message có thể phù hợp hơn tự dựng lại. Nhưng đây là dữ liệu có rủi ro bảo mật:

- Encryption at rest/in transit.
- Phân quyền truy cập theo tenant/source.
- TTL/legal retention.
- Integrity checksum/signature.
- Tránh log hoặc forward raw credential.
- Audit việc xem/tải/khôi phục bản gốc.
- Data deletion theo quy định.

### 20.5. Từ chối phép dịch

Khi không có cách bảo toàn field bắt buộc, **từ chối với reason code** có thể an toàn hơn nhận một record sai. Ví dụ B→A với `REFUNDED` không thể map đúng: phải reject hoặc dùng một version mới của partner contract hỗ trợ refund.

Không tự gán `REFUNDED→CANCELLED` rồi hứa "round-trip tương đương" nếu chưa có văn bản business contract chấp thuận việc gộp semantics.

## 21. Nhiều schema versions: Translator hay Normalizer?

Một hệ thống có thể có:

~~~text
LegacyOrder v1 ──┐
LegacyOrder v2 ──┼──> CanonicalOrder v3
PartnerOrder v4 ─┘
~~~

Đây là một **Normalizer EIP** dùng nhiều version-specific Translators hội tụ về canonical representation. Nếu cần phản hồi mỗi partner theo format riêng, có thể có hướng ngược:

~~~text
CanonicalOrder v3
   ├─> Partner A v1
   ├─> Partner B v4
   └─> Internal API v3
~~~

**Không** tự hiểu rằng có converter A→B nghĩa là B→A có thể thực hiện được mọi B states. Một schema version mới có thể thêm trường/trạng thái không thể biểu diễn ở target cũ. Mỗi **cặp source-target-version** cần support matrix và test riêng.

### 21.1. Version và business revision là hai khái niệm khác nhau

- `sourceSchemaVersion`: chọn parser/translator.
- `canonicalSchemaVersion`: output contract.
- `orderRevision`: thứ tự trạng thái đơn hàng.
- `eventId`: nhận dạng logical event để chống duplicate.
- `correlationId`: nhóm business messages.
- `traceId`: theo dõi flow.

Không dùng source schema version làm correlation key hoặc thứ tự business event.

### 21.2. Expand → migrate → contract

Một quy trình nâng cấp:

1. Deploy consumers có thể đọc cả v1/v2.
2. Test mappings trong cả hai hướng.
3. Producer bắt đầu phát v2 canary.
4. Theo dõi lossy/unsupported/error rates.
5. Ngừng phát v1 sau khi dữ liệu mới ổn.
6. Giữ converter v1 cho broker backlog, DLQ và historical replay.
7. Retire v1 khi retention window và rollback plan cho phép.

Xóa reverse translator v1 quá sớm có thể làm hỏng một tích hợp partner chưa kịp nâng cấp dù nội bộ đã chạy canonical v3.

### 21.3. Tránh loop khi ghép hai hướng

Nếu vô tình nối output của A→B vào input B→A và output B→A lại quay về A, bạn có thể tạo **infinite message loop**:

~~~mermaid
flowchart LR
    A["System A"] --> TAB["Translator A→B"]
    TAB --> B["System B"]
    B --> TBA["Translator B→A"]
    TBA --> A
~~~

Cần phân biệt **direction/operation** và xử lý response theo request contract. Một message đã được translate ngược để trả reply **không phải** một command mới cần phát lại vào cùng input topic. Idempotency cũng không thay việc cắt loop đúng topology.

## 22. Exception, discard, quarantine và DLQ

Một hệ thống dịch hai chiều cần phân biệt lỗi **không thể biểu diễn** và một **loss được phép theo business policy**.

| Tình huống | Kết quả | Policy gợi ý |
|---|---|---|
| A map hoàn toàn sang B | Outcome không có flagged loss | Cho đi business channel |
| A có promotion code mà B không chứa | Outcome có loss | Quarantine hoặc approved lossy path |
| Legacy status `"H"` không biết | Exception deterministic | Reject và báo producer |
| B state `REFUNDED` không có mã legacy | Exception deterministic | Không gửi fake CANCELLED |
| Amount có fractional minor units | Exception deterministic | Từ chối hoặc có rounding contract riêng |
| Schema registry tạm unavailable | Exception transient | Bounded retry/backoff |
| Partner API timeout sau gửi | Outcome remote không rõ | Reconcile/idempotency; không retry mù |
| Input JSON quá lớn | Ingress security validation | Reject trước parse |
| Same event ID, khác business payload | Integrity/idempotency conflict | Audit/quarantine, không skip im lặng |

### 22.1. Discard channel không phải error channel

Trong `BidirectionalTranslatorConfiguration`:

- `orders.translation.quarantine` nhận **TranslationOutcome** từ Filter khi `lossless()==false`.
- Nếu `PartnerOrderTranslator` ném exception, `MessageFilter` chưa được gọi; exception đi theo caller hoặc error infrastructure.
- `errorChannel` của Spring Integration thường nhận `ErrorMessage` chứa Throwable khi lỗi được publish bởi error handler/adapter.
- Broker DLQ là cơ chế transport riêng, không tự tạo chỉ vì có một bean đặt tên "quarantine".

Vì vậy consumer của quarantine **không được ép cast** mọi payload thành `ErrorMessage`. Với yêu cầu "mọi translation failure phải lưu hồ sơ", cần một **error classification flow riêng** chuyển typed exceptions thành `RejectedTranslationRecord`.

### 22.2. DirectChannel và async error propagation

Với `DirectChannel` đồng bộ, exception trong Transformer có thể lan về `send()` (và có thể được framework bọc trong `MessagingException`). Khi chuyển sang `ExecutorChannel`, poller hoặc broker listener, error có thể xảy ra trên worker thread; adapter/error handler có thể publish `ErrorMessage` tới error channel đã cấu hình.

Không mặc định một exception sync luôn tự động đến global `errorChannel`. Hãy test theo topology và inbound adapter thật.

### 22.3. Poison message không được retry vô hạn

Nếu một event có `statusCode="H"` và consumer không hỗ trợ, retry 1000 lần cùng payload không tạo mapping mới. Phân loại là non-retryable contract error, quarantine/DLQ với reason code, thông báo owner và chỉ reprocess khi đã có version adapter/mapping được phê duyệt.

### 22.4. Loss không phải một Throwable

Có thể **báo loss** mà không throw khi muốn cho policy filter quyết định. Ngược lại, dùng exception cho trường hợp không thể tạo target hợp lệ. Không catch mọi `RuntimeException` rồi trả `TranslationLoss("UNKNOWN")` để biến DB timeout hoặc bug code thành "mất optional field".

## 23. Retry, broker ACK và idempotency hai chiều

Một Transformer thuần không thực hiện side effects và cùng input luôn cho cùng output có lợi cho retry. Nhưng broker/gateway vẫn có thể đưa **cùng business event** tới downstream nhiều lần.

~~~text
Partner sends eventId=evt-order-1001
  -> Translate A→B
  -> Business DB commit
  -> Broker ACK lost
  -> Partner/Broker redelivers evt-order-1001
  -> Translate A→B again
  -> Idempotent Receiver must skip duplicate business effect
~~~

### 23.1. Dùng stable business event ID

Idempotency key có thể là `(tenantId, sourceSystem, eventId, operationType)` tùy namespace. Không dùng `MessageHeaders.ID` của Spring Message, broker delivery tag hoặc timestamp retry: chúng có thể đổi qua các hop và mỗi lần dịch.

### 23.2. Translation có thể đổi payload fingerprint

Nếu fingerprint dedup được tính trên **raw JSON bytes**, một event v1 và cùng event republished dưới v2 có thể khác hash mặc dù business meaning giống. Cần định nghĩa fingerprint theo **canonical business fields** và rules/versions. Nếu cùng event ID nhưng amount khác về bản chất, phải coi là **conflict**, không skip mù.

### 23.3. ACK sau khi outcome đã bền vững

Một discard/quarantine QueueChannel in-memory không bảo đảm nội dung được giữ qua restart. Nếu business contract yêu cầu không làm mất event, ACK chỉ nên được thực hiện khi event đã được xử lý/ghi bền hoặc được reject/quarantine theo một chính sách nguồn đáng tin. Adapter-specific ACK/NACK và transactions cần test thật.

### 23.4. Remote side effect sau Translator

Nếu outbound B→A gọi partner API có tác dụng tạo đơn, timeout **không chứng minh** bên partner chưa tạo đơn. Retry cùng stable idempotency key nếu API hỗ trợ, hoặc query/reconcile. TranslationOutcome không thay thế remote idempotency protocol.

## 24. Gateway request-reply và translation hai chiều

Một request có thể vào dưới hợp đồng A và reply về hợp đồng A sau khi business xử lý bằng B:

~~~mermaid
flowchart LR
    REQ["Partner Request A"] --> AB["Translate A→B"]
    AB --> HANDLER["Canonical business handler"]
    HANDLER --> BA["Translate B→A response"]
    BA --> RESP["Partner Reply A"]
~~~

**Lưu ý:** nhiều lúc request/response là **hai loại message khác nhau**; không lấy cùng `LegacyOrderV1` cho mọi response. Cần `LegacyOrderResponseV1` và `CanonicalOrderResultV2` với mapping và round-trip invariants riêng.

### 24.1. Không đồng nhất reverse translation với response

B→A có thể là phép dịch payload của một **event** hoặc **response**. Nó không tự biết `replyChannel` nào cần gửi. Với Spring Integration Gateway, reply destination, timeout và error mapping phải được cấu hình theo endpoint; khi đi qua broker khác JVM, không serialize `replyChannel` Java object và kỳ vọng đối tác dùng được.

### 24.2. Khi mất thông tin, trả kết quả nào?

Tùy API contract, có thể trả:

- `422 Unprocessable Content` (hoặc status phù hợp) nếu request không thể dịch đúng.
- Một response có danh sách field loss được chấp nhận, nếu API hỗ trợ partial acceptance.
- Một async `202 Accepted` + tracking ID khi cần manual reconciliation.
- Một error outcome với stable reason code để partner sửa message.

Đây là các **lựa chọn thiết kế API**, không phải quy định của Spring Message Translator. Không silent-drop request rồi để Gateway timeout nếu caller cần biết vì sao không được nhận.

### 24.3. Cần lưu reply khi idempotent request được gửi lại

Nếu partner retry một request đã xử lý, có thể phải trả **business receipt/result cũ**, không chạy lại handler. Idempotency record có thể lưu response reference/receipt theo transaction để B→A response mapping nhất quán.

## 25. Security, nguồn tin cậy và dữ liệu nhạy cảm

### 25.1. Map tenant không đồng nghĩa authorize tenant

`PartnerOrderTranslator` chỉ validate grammar `tenantId`; nó **không xác thực** người gửi có quyền trên tenant đó. HTTP/JMS/Kafka ingress phải đối chiếu tenant với principal/peer identity đã xác thực và ACL, trước khi business handler thực hiện side effects.

### 25.2. Loss report có thể lộ dữ liệu

`TranslationOutcome.original` lưu toàn source record trong memory/quarantine. Nếu record có promotion code, customer info, token hoặc địa chỉ, việc serialize nguyên outcome ra log/broker có thể làm lộ PII. Chỉ ghi reason codes vào metrics; chỉ lưu full source trong **restricted encrypted quarantine store** khi thực sự cần.

### 25.3. Chuỗi đầu vào không nên điều khiển channel tên tùy ý

Không route trực tiếp theo `source.legacyPromotionCode` hoặc trường từ payload không tin cậy để chọn `MessageChannel`/tenant queue. Version/type route cần allowlist và mapping rõ. Kiểm soát payload size, Unicode/numeric parser limits, schema validation và retries ở ingress.

### 25.4. Chữ ký trên payload bị phá sau khi dịch

Một chữ ký trên JSON bytes của A không còn chứng minh tính toàn vẹn của B sau khi reserialize. Nếu cần cryptographic integrity end-to-end:

1. Verify original A bytes/signature ở boundary.
2. Translate theo contract và lưu provenance/audit.
3. Ký B theo key/identity được ủy quyền nếu đích yêu cầu.
4. Không copy chữ ký cũ như thể nó xác thực B bytes mới.

TLS chỉ bảo vệ từng hop; nó không tự cấp quyền cho nội dung JSON/tenant do client khai.

## 26. Observability: biết mất gì, ở đâu, với version nào

Một hệ thống dịch hai chiều cần thấy **tổng input, output, loss, invalid, quarantine và retry** chứ không chỉ số exceptions.

| Metric | Mục đích | Labels được khuyến nghị |
|---|---|---|
| `translator_input_total` | Số message nhận | direction, sourceVersion |
| `translator_success_total` | Dịch thành công theo policy | direction, targetVersion |
| `translator_loss_detected_total` | Có trường bị mất | fieldName, reasonCode |
| `translator_quarantined_total` | Bị chặn bởi loss policy | direction, reason |
| `translator_contract_error_total` | Lỗi mapping deterministic | reasonCode |
| `translator_infrastructure_error_total` | Lỗi registry/service | dependency |
| `translator_reverse_unsupported_total` | Target A không biểu diễn B | stateType |
| `translator_round_trip_mismatch_total` | Sai semantic invariant | contractVersion |
| `translator_latency_seconds` | Độ trễ dịch | direction, version |
| `translator_replay_total` | Được phát lại | source, eventType |
| `translator_downstream_duplicate_total` | Effect trùng bị chặn | flow |
| `translator_source_version_share` | Tỷ lệ source format | source, version |

### 26.1. Log có cấu trúc

~~~text
service=partner-bridge
flow=legacy-orders
direction=A_TO_B
sourceVersion=1
targetVersion=2
eventType=order.created
eventId=evt-order-1001
outcome=QUARANTINED_LOSSY
lossFields=[legacyPromotionCode]
reasonCode=FIELD_NOT_REPRESENTABLE_IN_CANONICAL
traceId=trace-1001
~~~

Chỉ log identifiers theo policy bảo mật, có thể hash/redact; không log raw promotion code hoặc toàn payload. Không dùng `eventId`/`orderId`/`traceId` làm metric labels cardinality cao. Mục `lossFields` trong log có thể chứa **tên field ổn định**, không chứa giá trị business.

### 26.2. Dấu hiệu mapping drift

- `AMOUNT_NOT_EXACT_OR_OVERFLOW` tăng sau khi partner đổi đơn vị.
- Nhiều `REFUNDED` bị reverse reject sau khi canonical service triển khai trạng thái mới.
- `legacyPromotionCode` loss tăng sau một campaign.
- Cùng event ID nhưng canonical fingerprint khác giữa version v1/v2.
- Contract tests trên JSON fixtures bắt đầu thất bại sau serializer upgrade.
- Tỷ lệ quarantine tăng dù broker delivery ổn định.
- ACK thành công nhưng business output không có vì nhánh loss bị drop.
- Một reply Gateway bắt đầu timeout vì no-op/discard branch không trả response.

### 26.3. Alert dựa trên mức rủi ro

Một trường display-only bị mất trong migration có thể là warning. Nhưng mất business amount, tenant identity hoặc eventId phải **fail closed** và alert. Không tạo cùng severity cho mọi translation loss.

## 27. Performance và độ tin cậy của Translator

### 27.1. Pure mapping là mặc định tốt

`PartnerOrderTranslator` là một class thuần: không gọi DB, broker hoặc remote API. Nó dễ unit test, retry và có thể chạy trên nhiều instances. Nếu cần resolve external ID hoặc currency rules theo version, hãy đưa dependency resolution vào một boundary có caching/timeout rõ, tách khỏi mapping thuần khi có thể.

### 27.2. Không nhân đôi payload lớn trong outcome vô hạn

`TranslationOutcome<S,T>` giữ cả source và target. Với message lớn, điều đó tăng memory/GC, nhất là khi source có binary attachment. Production có thể dùng **source reference/Claim Check** thay vì giữ hai bản payload lớn, với checksum, ACL và retention. Đây cũng là một đánh đổi: khi source reference hết hạn thì không thể reconstruct source để replay.

### 27.3. Bounded queues và backpressure

Nếu 20% traffic bị loss policy chặn nhưng không có consumer cho quarantine queue, queue có thể tăng vô hạn. Đặt bounded capacity, persistence, retry/backpressure, metric và retention. Không ACK rồi để message bị loss mất trong một in-memory QueueChannel.

### 27.4. Ordering và correlation qua hai hướng

Nếu một order có các event CREATED→PAID→REFUNDED và Translator khác nhau chạy trên nhiều executor instances, output có thể không giữ thứ tự gửi. `schemaVersion` không phải sequence number; khi cần ordering, dùng business revision/sequence và key partition theo tenant/order, cộng Resequencer/Aggregator nếu contract đòi hỏi.

### 27.5. Two-way flow không phải hai service gọi nhau vô hạn

Khi tích hợp hai hệ thống cùng phát thay đổi, cần định nghĩa **source-of-truth**, direction ownership và loop prevention. Một message đi A→B không nên được B coi như thay đổi mới rồi echo trở lại A nếu không có policy nguồn gốc/version/idempotency phù hợp.

## 28. Anti-patterns dễ gây mất dữ liệu

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ có A→B và B→A nghĩa round-trip lossless | Không phục hồi source fields | Ghi miền hợp lệ, loss report |
| Bỏ legacy field vì "đích không dùng" | Mất audit/promotion | Approval, extension/sidecar |
| Tạo promotion code mặc định để đủ schema | Thông tin bịa | Null/optional/reject |
| Gộp REFUNDED thành CANCELLED | Sai trạng thái nghiệp vụ | Unsupported mapping |
| Dùng double cho money | Sai precision | BigDecimal, exact minor units |
| Làm tròn không theo contract | Tăng/giảm giá trị tài chính | Reject hoặc approved rounding |
| Tin "25.00" và "0025.000" giống byte | Sai chữ ký/audit | Phân biệt lexical và semantic |
| Bỏ unknown JSON fields trước Translator | Loss report không biết | Strict decode/extension bag |
| Dùng null = absent = empty = zero | Sai nghĩa | Presence-aware schema |
| Convert List thành Set | Mất order/duplicates | Chọn collection giữ contract |
| Dùng enum default như PAID/CANCELLED | Nuốt trạng thái mới | Fail-fast và version route |
| Dịch nhưng đổi eventId | Replay bị double processing | Preserve logical event ID |
| Dùng amount/status làm correlation key | Drift nhóm | Stable business key |
| Đưa TranslationOutcome cả original vào broker | Leak dữ liệu, đổi contract | Chỉ gửi approved translated DTO |
| Cho lossy B thẳng vào business handler | Business xử lý khi dữ liệu thiếu | Explicit loss gate |
| Chỉ bắt exception, bỏ qua loss result | Mất dữ liệu không báo lỗi | Audit loss outcome |
| Coi discard = DLQ | Không có persistent recovery | Quarantine/broker policy |
| ACK khi chỉ đưa vào in-memory quarantine | Crash làm mất event | Durable storage + ACK policy |
| Copy mọi Spring headers sang partner | Lộ token/stale contentType | Allowlist + transport mapper |
| Chỉ test Java object equality | Không phát hiện wire serializer drift | JSON/Avro fixture tests |
| Hai flows nối nhau thành loop | Lặp message và side effects | Direction ownership/loop guard |
| Tưởng Transformer là exactly-once | Retry vẫn chạy handler | Idempotent Receiver + transaction |

## 29. Bài tập thực hành, test matrix và câu hỏi

### 29.1. Bài tập

**Bài 1 — Xác định mức bảo toàn.** Với `"0025.000" USD` → 2500 minor units → `"25.00"`, giải thích byte, structural và semantic equality.

**Bài 2 — Chứng minh không đảo ngược.** Tạo A1/A2 chỉ khác promotion code nhưng cùng canonical B; giải thích vì sao không thể khôi phục code từ B.

**Bài 3 — Money exactness.** Test USD `"25.00"`, `"25.001"`, VND `"25000"`/`"25000.50"` và overflow long.

**Bài 4 — Enum evolution.** Thêm trạng thái `REFUNDED` ở B và xác nhận B→A fail với reason rõ.

**Bài 5 — Forward translator.** Viết `toCanonical` và xác nhận giữ eventId, tenantId, orderId và tiền.

**Bài 6 — Loss report.** Dùng A có `legacyPromotionCode`, expect `TranslationOutcome.losses` không rỗng và original được giữ trong scope nội bộ.

**Bài 7 — Reverse translator.** Tạo B có state PAID và xác nhận amount/status map về A; thảo luận lý do không thể phục hồi promotion code lịch sử.

**Bài 8 — Round-trip domain.** Kiểm tra A→B→A cho A không có promotion, amount lexical chuẩn, status thuộc N/P/C.

**Bài 9 — Semantic round-trip.** Dùng source `"0025.000"` và xác minh exact string khác nhưng monetary value tương đương.

**Bài 10 — Spring Integration DSL.** Dựng `BidirectionalTranslatorConfiguration`, gửi hợp lệ vào accepted channel, có loss vào quarantine.

**Bài 11 — Exception route.** Gửi `statusCode="H"` và amount `"25.001"`; test exception được phân loại thay vì nằm trong loss list.

**Bài 12 — Gateway response.** Thiết kế reply khi request bị loss policy chặn, tránh silent drop làm caller timeout.

**Bài 13 — Preserve original.** Thiết kế sidecar store cho promotion code và raw amount lexical, xác định transaction/TTL/ACL.

**Bài 14 — JSON fixtures.** Serialize A→B→A bằng Jackson; so sánh wire JSON và business fields, test unknown property behavior.

**Bài 15 — Idempotency.** Gửi cùng eventId qua hai Spring Message instances sau redelivery; downstream chỉ thực hiện business write một lần.

**Bài 16 — Adapter headers.** Xác nhận Authorization không bị chuyển tiếp, nhưng trusted correlation/tracing metadata được giữ qua transport.

**Bài 17 — Schema migration.** Giữ converter v1 cho archived events khi producer phát v2; lập test regression.

**Bài 18 — Collections.** Thử List→Set→List có duplicates/order; thiết kế loss report hoặc preserve sequence metadata.

**Bài 19 — Timezones.** Dịch OffsetDateTime→Instant→OffsetDateTime; phân biệt same instant và original offset.

**Bài 20 — Monitoring.** Thêm metrics về field loss, impossible reverse mapping, invalid money, quarantine và version drift.

### 29.2. Ma trận kiểm thử tối thiểu

| Input/hoàn cảnh | Expected |
|---|---|
| A không promotion, USD amount chuẩn | B hợp lệ, loss list rỗng |
| A có promotion | Loss report, không vào strict business channel |
| A amount không exact minor | Contract error |
| A currency ngoài support matrix | Contract error |
| A status unknown | Contract error |
| B REFUNDED | Reverse not representable |
| A lexical amount có leading zeros | Semantic round-trip, byte không bằng |
| A eventId rỗng | Reject |
| A tenantId sai principal | Reject ở auth boundary |
| B→A→B với state shared | Canonical semantic equality |
| A→B→A với promo không-null | Không được tuyên bố lossless |
| Input JSON unknown fields | Theo schema/decoder policy, không bỏ âm thầm |
| Original payload có secret | Không serialize whole outcome ra broker |
| Broker redelivery | Stable event ID, idempotent side effect |
| Consumer lag/DLQ v1 | Converter v1 vẫn có replay plan |
| Quarantine store unavailable | Retry/ACK theo durability policy |
| Error trong async translator | ErrorMessage/error flow có policy |
| Lossy result từ Filter | Discard payload là TranslationOutcome, không phải ErrorMessage |
| Two-way loop | Có direction/echo guard |
| Schema mới đổi status/amount | Contract regression test trước deploy |

### 29.3. Câu hỏi tự kiểm tra

1. Một Message Translator khác Serializer ở điểm nào?
2. Có hai hàm A→B, B→A có chứng minh inverse không?
3. Ba mức byte, structural, semantic equality khác nhau thế nào?
4. Khi nào A→B là many-to-one?
5. Vì sao mất promotion code không thể sửa bằng cách viết reverse mapper?
6. Vì sao REFUNDED không nên map thành CANCELLED?
7. Vì sao không dùng double khi đổi major/minor units?
8. Numeric equality có đồng nghĩa lexical string equality không?
9. Null, absent và empty khác nhau thế nào?
10. Unknown JSON fields có thể bị mất ở bước nào?
11. Vì sao `TranslationOutcome.lossless()` chưa chứng minh byte-level round trip?
12. Vì sao reverse outcome không biết loss đã xảy ra ở forward outcome?
13. Vì sao nên giữ original payload khi quarantine?
14. Khi nào nên dùng extension bag thay canonical field?
15. Sidecar store làm phép reverse phụ thuộc điều gì?
16. Vì sao business event ID phải giữ nguyên qua translator?
17. SchemaVersion khác business revision/traceId thế nào?
18. Tại sao Spring discard channel không mặc nhiên là errorChannel?
19. Khi nào exception là non-retryable và khi nào transient?
20. Gateway sẽ gặp gì nếu loss policy silent drop request?
21. Vì sao duplicate broker delivery vẫn xảy ra khi Translator deterministic?
22. Khi nào có thể xóa legacy translator?
23. Làm sao chống infinite loop A↔B khi cả hai sides phát event?
24. Metric nào phát hiện dữ liệu mất sau partner upgrade?
25. Khi nào cần test wire serialized bytes thay vì chỉ so Java records?

## 30. Checklist thiết kế Translator hai chiều

- [ ] Đã định nghĩa rõ domain A/B, source/target schema versions.
- [ ] Có mapping ledger cho từng field và business invariant.
- [ ] Xác định mức bảo toàn: byte, structural, semantic hoặc task-sufficient.
- [ ] Đã định nghĩa tập giá trị nào được phép round-trip.
- [ ] Đã chứng minh fields không thể phục hồi được nhận diện.
- [ ] Mọi loss được báo bằng reason code hoặc bị reject theo contract.
- [ ] Không tự điền default cho trường business không biết.
- [ ] Enum mới/unknown bị reject hoặc map theo policy được phê duyệt.
- [ ] Money conversion dùng BigDecimal/exact unit mapping và overflow checks.
- [ ] Null/absent/empty/zero có semantics rõ.
- [ ] Collection ordering/duplicates có contract bảo toàn.
- [ ] Timestamp giữ đúng instant/offset/timezone cần thiết.
- [ ] Không đổi eventId/tenant/business identity khi chỉ đổi representation.
- [ ] Authenticated tenant/source được xác minh trước business side effects.
- [ ] TranslationOutcome original không được xuất public/broker tùy tiện.
- [ ] Quarantine có persistence, ACL, encryption, TTL và replay policy.
- [ ] Filter loss không bị nhầm với errorChannel Throwable.
- [ ] Deterministic invalid input không được retry vô hạn.
- [ ] Transient dependency failures có bounded retry và backoff.
- [ ] ACK broker chỉ sau outcome bền vững theo contract.
- [ ] Downstream có Idempotent Receiver/transaction phù hợp.
- [ ] Gateway trả explicit response/error cho loss policy.
- [ ] Header mapping có allowlist, không copy token hoặc runtime channel objects.
- [ ] Current schemaVersion và source provenance được gắn đúng.
- [ ] A→B và B→A có separate tests; không giả inverse tự động.
- [ ] Property/parameterized tests bao phủ numeric boundaries/enum values.
- [ ] Có tests round-trip theo **semantic equality** rõ ràng.
- [ ] Có serialized JSON/Avro fixtures test từng version.
- [ ] Schema evolution/legacy retirement xét DLQ, backlog và replay.
- [ ] Có owner duyệt field loss, semantic changes và migration strategy.
- [ ] Metrics phân biệt success, loss, impossible mapping, invalid, replay.
- [ ] Không dùng event ID/order ID/trace ID làm metric labels cardinality cao.
- [ ] Two-way flows có direction ownership và loop prevention.
- [ ] Không gọi công việc dịch payload là xử lý nghiệp vụ hoàn tất.

## 31. Tổng kết

**Translator hai chiều và nguy cơ mất thông tin** nhắc rằng việc chuyển đổi **A→B và B→A** chỉ mang lại *khả năng kết nối* giữa hai hợp đồng, **không tự tạo một cặp hàm nghịch đảo**. Khi một trường của A không tồn tại ở B, hoặc nhiều trạng thái A bị gộp thành một B, thông tin nguồn có thể mất không thể khôi phục. Khi amount đổi từ chuỗi decimal sang minor units, numeric value có thể bảo toàn nhưng lexical representation không còn nguyên; khi enum mới vượt khả năng biểu diễn của legacy, reverse translation phải có **unsupported outcome** thay vì map sai.

Trong Spring Integration, dùng **Transformer** để thực thi mapping, **Filter** để chặn `TranslationOutcome` có loss không được phép, Router/Normalizer để chọn schema/version adapters, Gateway để duy trì request-reply contract và error channel/quarantine cho failures. Một Translator an toàn cần **typed reasons, explicit loss policy, exact money/enum conversion, stable event identity, bảo mật headers và kiểm thử hai hướng**. Khi cần exact round-trip, giữ dữ liệu nguồn ở canonical extension/sidecar hoặc original record với quyền truy cập và retention phù hợp; không tự bịa dữ liệu đã mất.

Đối với **SPRING_INTEGRATION_PATTERN**, mục tiêu là tích hợp nhiều hệ thống **ít phụ thuộc và dễ mở rộng** mà vẫn trung thực về ý nghĩa message: có thể từ chối thay vì nhận dữ liệu sai, có thể báo rõ loss thay vì âm thầm drop, có thể replay mà không tạo duplicate side effects, và có thể nâng cấp schema với test, audit và observability đáng tin cậy.

### Tài liệu tham khảo

- Enterprise Integration Patterns — Message Translator: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns — Normalizer: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Enterprise Integration Patterns — Envelope Wrapper: https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html
- Enterprise Integration Patterns — Idempotent Receiver: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Message Routing: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Gateway: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Java SE 17 API — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17 API — Currency: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/





