# Validation sau transformer

> **Chương:** Message filter và validation  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **xác thực dữ liệu sau khi chuyển đổi về mô hình chuẩn**, trước khi dữ liệu được phép đi vào các handler có tác dụng nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Transformer thành công không đồng nghĩa message đã hợp lệ** và khi nào cần validation cả trước lẫn sau Transformer.
2. Phân biệt **structural validation**, **canonical/domain validation**, **cross-field validation**, **authorization**, và **business-state validation** theo đúng ranh giới trách nhiệm.
3. Thiết kế thứ tự `Input → Validate transport/schema → Transformer → Validate canonical payload → Filter/Router → Handler` để ngăn lệnh không hợp lệ đến hệ thống đích.
4. Dùng Spring Integration Java DSL với `.transform(...)`, `.filter(...)`, `.route(...)`, `discardChannel` và error channel mà không đánh đồng **rejection nghiệp vụ** với **exception kỹ thuật**.
5. Tạo kết quả validation **có kiểu**, có mã lỗi và vị trí field, tránh làm rơi message âm thầm khi caller cần lời giải thích.
6. Tích hợp Jakarta Bean Validation khi phù hợp, đồng thời xử lý điều kiện liên trường, giới hạn số lượng và policy phụ thuộc dữ liệu có thẩm quyền.
7. Kiểm thử cả nhánh được chấp nhận lẫn nhánh bị từ chối, trường hợp lỗi parsing trong Transformer, metadata/correlation, duplicate, Splitter/Aggregator và tác dụng phụ không được xảy ra.
8. Áp dụng bảo mật, idempotency, observability và error handling để validation không trở thành điểm rò dữ liệu hoặc nguyên nhân gây treo workflow.

## 2. Tình huống: đối tác gửi đơn hàng ở schema riêng

Một hệ thống nhận đơn hàng từ đối tác. Dữ liệu nguồn có các trường dạng chuỗi:

~~~json
{
  "tenantId": "shop-a",
  "partnerOrderId": "PO-901",
  "sku": "book-42",
  "quantityText": "003",
  "unitPriceMinorText": "25000",
  "currency": "vnd"
}
~~~

Ứng dụng cần chuyển sang mô hình nội bộ:

~~~json
{
  "tenantId": "shop-a",
  "orderId": "PO-901",
  "sku": "BOOK-42",
  "quantity": 3,
  "unitPriceMinor": 25000,
  "currency": "VND"
}
~~~

Transformer có thể parse và chuẩn hóa thành công, nhưng vẫn tạo dữ liệu **sai quy tắc**:

~~~json
{
  "tenantId": "shop-a",
  "orderId": "PO-902",
  "sku": "BOOK-42",
  "quantity": -3,
  "unitPriceMinor": 25000,
  "currency": "VND"
}
~~~

`"-3"` là số nguyên **parse được**, nhưng số lượng âm **không thể dùng để đặt hàng**. Tương tự, một `currency` viết đúng cú pháp có thể không thuộc tập tiền tệ được hỗ trợ; giá hợp lệ kiểu `long` có thể gây tràn số khi nhân với quantity.

Vì thế, nên có **một bước validation trên mô hình canonical sau Transformer**:

~~~mermaid
flowchart LR
    IN["Message<ExternalOrder>"] --> PRE["Validate nguồn / schema"]
    PRE --> TR["Transformer: parse + normalize"]
    TR --> VA{"Validate CanonicalOrder"}
    VA -->|"Hợp lệ"| OK["Business handlers / Gateway"]
    VA -->|"Không hợp lệ"| REJ["RejectionResult / audit"]
    TR -->|"Lỗi chuyển đổi"| ERR["Error handling / quarantine"]
~~~

**Bất biến cần giữ:** Không message nào vi phạm policy canonical được đưa tới endpoint thực hiện side effect như giữ kho, tạo hóa đơn hoặc gửi lệnh thanh toán.

## 3. Vì sao validation trước Transformer chưa đủ?

Hai thời điểm kiểm tra giải quyết **những loại sai lệch khác nhau**.

| Thời điểm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Trước Transformer** | Envelope, chữ ký, schema, kiểu biểu diễn, kích thước và nguồn có được tin không? | JSON malformed, tenant chưa xác thực, field quá dài |
| **Trong Transformer** | Có thể diễn giải và chuẩn hóa payload về kiểu canonical không? | `quantityText="abc"` không parse thành `int` |
| **Sau Transformer** | Canonical DTO có thỏa domain invariants không? | Quantity âm, tiền tệ bị cấm, tổng tiền vượt ngưỡng |
| **Trước commit** | Tình trạng hệ thống hiện tại có cho phép thao tác không? | Tồn kho không đủ, tài khoản bị đóng |
| **Sau commit / audit** | Outcome có được ghi/đo đúng không? | Operation ID đã được lưu, event outbox tồn tại |

### 3.1. Ví dụ một trường qua nhiều bước

~~~text
Raw quantityText = " 003 "
    |
    |  Structural validation: field là String, có giới hạn độ dài
    v
Transformer: trim + parse Integer
    |
    v
Canonical quantity = 3
    |
    |  Domain validation: 1 <= quantity <= 500
    v
Business handler: atomically reserve 3 units
~~~

Với input `"0"`, Transformer vẫn hoàn tất; **validation sau Transformer** phát hiện không hợp lệ. Với input `"not-a-number"`, Transformer không thể tạo đối tượng canonical; cần một **transformation error** riêng, không ép nó thành kết quả `quantity=0` cho tiện.

### 3.2. Khi nào cần kiểm cả trong và sau Transformer?

Trước khi chuyển đổi, không nên cho phép payload khổng lồ, quá sâu hoặc có cấu trúc nguy hiểm đi vào parser. Sau khi chuyển đổi, phải kiểm lại những bất biến đã thay đổi vì normalize, defaulting, mapping enum hoặc quy đổi đơn vị.

Ví dụ:

- `currency="usd"` thành `"USD"`: sau đó kiểm tập giá trị được hỗ trợ.
- `"001"` thành `1`: sau đó kiểm giới hạn số lượng.
- Giá nguồn biểu diễn theo đơn vị tiền lẻ: kiểm cả parse, đơn vị tiền và phép tính tổng.
- Mapper điền default cho trường thiếu: validation sau transform quyết định default đó có hợp lệ cho nghiệp vụ này không.
- Router cần một `countryCode` canonical: validation kiểm country trước khi route, tránh rẽ vào nhánh mặc định không phù hợp.

## 4. Validation, Filter, Router và Transformer khác nhau thế nào?

| Thành phần EIP | Trách nhiệm | Không nên mặc định |
| --- | --- | --- |
| **Transformer** | Đổi biểu diễn message/payload | Cứ convert được là dữ liệu hợp lệ |
| **Message Filter** | Quyết định message đi tiếp hay bị chặn bằng điều kiện | Filter luôn tạo giải thích lỗi |
| **Router** | Gửi message đến một nhánh đích theo key/condition | Router là validation đầy đủ |
| **Validator** | Kiểm tra invariants và tạo vi phạm có mã rõ | Validation thay thế authorization |
| **Service Activator** | Thực thi tác vụ nghiệp vụ | Handler tự chịu hết trách nhiệm parsing mọi schema |
| **Aggregator** | Gom những kết quả thuộc cùng nhóm | Filter drop một child không ảnh hưởng release |
| **Error Channel** | Xử lý exception/error message theo topology | Bất kỳ rejection nghiệp vụ nào cũng là exception kỹ thuật |

**Một Filter đơn giản** phù hợp nếu chỉ cần accept/reject, ví dụ chặn những thông báo không đủ điều kiện gửi sang một kênh. Nếu API/Gateway cần trả **tại sao** bị từ chối, nên tạo một kết quả validation có kiểu và route sang **rejection flow**.

### 4.1. Kiểm tra nghiệp vụ không đồng nghĩa xác thực quyền

`quantity > 0` là domain validation. Nhưng việc tenant A có quyền cập nhật đơn của tenant B là **authorization**. Một DTO qua validation không chứng minh principal có quyền. Đừng dùng header `validated=true` do client gửi thay cho authorization đã được server thực hiện.

## 5. Quy tắc thiết kế pipeline

~~~text
Inbound adapter / Gateway
  |
  +-- Authenticate source, validate tenant, request limits
  |
  v
ExternalOrder (đã parse theo schema nguồn)
  |
  +-- Structural/contract validation
  |
  v
Transformer → CanonicalOrder
  |
  +-- Parse + normalize
  +-- Parse failure → transformation error path
  |
  v
Canonical domain validation
  |
  +-- Valid     → processing branch
  +-- Invalid   → typed rejection + audit + caller response
  |
  v
Idempotent receiver / authorization/state checks
  |
  v
Business handler / external Gateway
  |
  v
Persisted result / outbox / reply
~~~

**Đặt bước validation sau Transformer nhưng trước side effect.** Không chờ tới khi gọi Inventory API bị từ chối mới tìm ra quantity âm; khi đó lỗi domain đã trở thành network traffic và có thể gây retry thừa.

### 5.1. Một chuỗi có thể có nhiều Transformer

~~~text
JSON document → ExternalOrder → CanonicalOrder → ReserveStockCommand
                  |                |                 |
                schema        domain validation   command invariants
~~~

Nếu Transformer thứ hai **đổi ý nghĩa** dữ liệu (ví dụ quy đổi đơn vị, nhân tổng, gom dòng hoặc chuyển currency), hãy kiểm lại **invariants của mô hình đầu ra mới**. Một message từng hợp lệ ở dạng canonical không tự bảo đảm mọi transformation downstream giữ nguyên tính hợp lệ.

### 5.2. Mọi trường cần có nguồn sự thật

| Trường | Nguồn được chấp nhận | Hệ quả nếu tin sai |
| --- | --- | --- |
| `tenantId` | Identity/principal đã xác thực | Cross-tenant routing và IDOR |
| `orderId` | Mapping theo partner namespace đã được duyệt | Trùng ID giữa hai đối tác |
| `quantity` | Chuỗi đã parse, kiểm giới hạn | Số âm/overflow |
| `unitPriceMinor` | Schema/đơn vị tiền đã chuẩn hóa | Nhầm đơn vị/currency, tính tiền sai |
| `sku` | Normalize + lookup theo catalog nếu cần | Router đi nhánh sai |
| `operationId` | Business command identity đã tạo một lần | Retry tạo side effect trùng |

## 6. Thiết kế DTO nguồn và canonical (Java 17)

Ví dụ dùng Java records. Trường số ở nguồn còn là `String` để minh họa rõ **parsing error** khác **domain validation failure**.

~~~java
record ExternalOrder(
    String tenantId,
    String partnerOrderId,
    String sku,
    String quantityText,
    String unitPriceMinorText,
    String currency
) {}

record CanonicalOrder(
    String tenantId,
    String orderId,
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency
) {}
~~~

Tại đây, `CanonicalOrder` **chỉ là record chứa dữ liệu đã chuẩn hóa**, chưa tự áp mọi validation. Cách này cho phép dạy rõ thứ tự: **transformer có thể tạo DTO chưa đạt domain policy; validator quyết định tiếp**.

Nếu dự án có yêu cầu “không thể khởi tạo domain object không hợp lệ”, có thể chuyển bất biến cốt lõi vào constructor của domain value object, và coi exception khi xây dựng model là validation error. Tuy nhiên, muốn thu thập **nhiều lỗi trên một lần gửi**, DTO trung gian + kết quả validation thường thuận tiện hơn.

### 6.1. Tại sao `quantityText` không parse trực tiếp ở gateway?

Nếu tất cả các đối tác dùng cùng canonical schema, mapping có thể nằm sớm ở adapter. Nhưng khi đối tác A dùng `qty` dạng chuỗi còn đối tác B dùng integer, tách **external contract** và **canonical DTO** sẽ làm topology và tests dễ hiểu hơn.

**Không để mapper quyết định authorization.** Tenant trong DTO ví dụ chỉ phục vụ minh họa; production phải gắn tenant đã xác thực từ trusted inbound context và đối chiếu với field nếu có.

## 7. Transformer: parse và normalize, không che lỗi

Mã ví dụ:

~~~java
import java.util.Locale;

final class ExternalOrderMapper {

    CanonicalOrder toCanonical(ExternalOrder source) {
        if (source == null) {
            throw new InvalidRepresentationException("NULL_SOURCE");
        }

        return new CanonicalOrder(
            text(source.tenantId()),
            text(source.partnerOrderId()),
            text(source.sku()).toUpperCase(Locale.ROOT),
            parseInt(source.quantityText(), "QUANTITY"),
            parseLong(source.unitPriceMinorText(), "PRICE_MINOR"),
            text(source.currency()).toUpperCase(Locale.ROOT)
        );
    }

    private static String text(String value) {
        return value == null ? "" : value.strip();
    }

    private static String requiredText(String value, String name) {
        String result = text(value);
        if (result.isEmpty()) {
            throw new InvalidRepresentationException(name + "_MISSING");
        }
        return result;
    }

    private static int parseInt(String raw, String name) {
        try {
            return Integer.parseInt(requiredText(raw, name));
        } catch (NumberFormatException ex) {
            throw new InvalidRepresentationException(
                name + "_NOT_INTEGER", ex);
        }
    }

    private static long parseLong(String raw, String name) {
        try {
            return Long.parseLong(requiredText(raw, name));
        } catch (NumberFormatException ex) {
            throw new InvalidRepresentationException(
                name + "_NOT_INTEGER", ex);
        }
    }
}

final class InvalidRepresentationException extends RuntimeException {
    InvalidRepresentationException(String code) {
        super(code);
    }

    InvalidRepresentationException(String code, Throwable cause) {
        super(code, cause);
    }
}
~~~

**Ví dụ quan trọng:**

| Input | Transformer | Validator sau đó |
| --- | --- | --- |
| `quantityText=" 003 "` | Tạo `quantity=3` | Chấp nhận nếu trong giới hạn |
| `quantityText="-3"` | Tạo `quantity=-3` | Từ chối `QUANTITY_OUT_OF_RANGE` |
| `quantityText="abc"` | Ném `QUANTITY_NOT_INTEGER` | **Không chạy** vì chưa có canonical DTO |
| `currency=" vnd "` | Tạo `currency="VND"` | Kiểm có trong allowed set |
| `currency="xyz"` | Tạo `currency="XYZ"` | Từ chối `UNSUPPORTED_CURRENCY` |
| `price="999999999999999999999"` | Ném `PRICE_MINOR_NOT_INTEGER` | Không chạy |
| `sku=" "` | Tạo `sku=""` | Từ chối `SKU_REQUIRED` |

Không âm thầm gán `quantity=0` khi parse sai. Nếu dùng giá trị mặc định, phải có **policy được phê duyệt** và lưu dấu source data/provenance; nếu không lỗi representation sẽ bị che thành lỗi domain khó điều tra.

### 7.1. Không làm I/O hoặc side effect trong mapper

Một Transformer lý tưởng cho bài học này nên **deterministic**: cùng input đã xác minh cho cùng output. Đừng gọi API giữ hàng, gửi email hay ghi database trong hàm `toCanonical`. Điều đó làm retry parsing biến thành retry nghiệp vụ và khiến test khó cô lập.

Nếu cần tra SKU hoặc bảng exchange rate, xem xét tách bước enrichment có caching/versioned policy và **kiểm lại domain invariants** sau enrichment.

### 7.2. Normalize có thể tạo collision

Hai mã nguồn `"book-42"` và `"BOOK-42"` đều thành `"BOOK-42"`. Điều này có thể đúng nếu business coi SKU không phân biệt hoa thường, nhưng có thể sai với đối tác phân biệt case. Quy tắc normalize phải thuộc **contract**; không chỉ “cho đẹp”.

## 8. Validator sau Transformer: mã lỗi có cấu trúc

Để trả về lý do bị từ chối thay vì bỏ message, tạo các DTO:

~~~java
import java.util.List;
import java.util.Objects;

record ValidationIssue(String field, String code) {
    ValidationIssue {
        Objects.requireNonNull(field, "field");
        Objects.requireNonNull(code, "code");
    }
}

record ValidationOutcome(
    CanonicalOrder order,
    List<ValidationIssue> issues
) {
    ValidationOutcome {
        Objects.requireNonNull(order, "order");
        issues = List.copyOf(issues);
    }

    boolean valid() {
        return issues.isEmpty();
    }
}

record RejectionNotice(
    String orderId,
    List<ValidationIssue> issues
) {
    RejectionNotice {
        issues = List.copyOf(issues);
    }
}
~~~

Không trả dữ liệu nhạy cảm thô trong `ValidationIssue`. Phần lớn các lỗi có thể được diễn tả bằng **field name + error code**; một API public có thể ánh xạ sang thông báo thân thiện theo locale.

### 8.1. Business validator thuần Java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

final class OrderPolicyValidator {

    private static final int MAX_QUANTITY = 500;
    private static final long MAX_UNIT_PRICE_MINOR = 1_000_000_000L;

    private static final Set<String> SUPPORTED_CURRENCIES =
        Set.of("VND", "USD");

    ValidationOutcome inspect(CanonicalOrder order) {
        List<ValidationIssue> issues = new ArrayList<>();

        if (order.tenantId().isBlank()) {
            issues.add(new ValidationIssue(
                "tenantId", "TENANT_REQUIRED"));
        }

        if (order.orderId().isBlank()) {
            issues.add(new ValidationIssue(
                "orderId", "ORDER_ID_REQUIRED"));
        }

        if (!order.sku().matches("[A-Z0-9-]{1,64}")) {
            issues.add(new ValidationIssue(
                "sku", "SKU_FORMAT_INVALID"));
        }

        if (order.quantity() < 1
                || order.quantity() > MAX_QUANTITY) {
            issues.add(new ValidationIssue(
                "quantity", "QUANTITY_OUT_OF_RANGE"));
        }

        if (order.unitPriceMinor() < 0
                || order.unitPriceMinor() > MAX_UNIT_PRICE_MINOR) {
            issues.add(new ValidationIssue(
                "unitPriceMinor", "PRICE_OUT_OF_RANGE"));
        }

        if (!SUPPORTED_CURRENCIES.contains(order.currency())) {
            issues.add(new ValidationIssue(
                "currency", "UNSUPPORTED_CURRENCY"));
        }

        // Cross-field guard: tổng tiền phải biểu diễn được bằng long.
        if (order.quantity() > 0 && order.unitPriceMinor() >= 0) {
            try {
                Math.multiplyExact(
                    (long) order.quantity(), order.unitPriceMinor());
            } catch (ArithmeticException ex) {
                issues.add(new ValidationIssue(
                    "totalPriceMinor", "TOTAL_OVERFLOW"));
            }
        }

        return new ValidationOutcome(order, issues);
    }
}
~~~

**Điểm có chủ ý:** validator không ném exception cho các giá trị domain thường gặp như quantity âm hay currency không hỗ trợ. Nó trả **danh sách issues** để một rejection flow có thể trả về phía gửi và ghi audit có kiểm soát.

Tuy nhiên, không phải mọi điều kiện đều phù hợp đưa vào validator thuần. **Giá trị từ trạng thái hệ thống** như tồn kho hiện tại hoặc trạng thái tài khoản có thể thay đổi ngay sau lúc kiểm. Các điều kiện đó phải được xác nhận tại thời điểm **transaction/commit** của business handler.

### 8.2. Những giới hạn bắt buộc phải được quyết định theo nghiệp vụ

Ví dụ giới hạn `MAX_QUANTITY=500` và `MAX_UNIT_PRICE_MINOR=1_000_000_000` chỉ để minh họa. Production phải xác định giới hạn theo tenant, loại hàng, currency/scale và policy version. Không dùng một giới hạn mặc định của bài học để áp cho tất cả hệ thống.

### 8.3. Vì sao cần kiểm tra overflow?

Nếu đơn vị tiền được lưu bằng số nguyên `minor units`, phép nhân `quantity * unitPriceMinor` có thể vượt `Long.MAX_VALUE` dù từng trường parse được. Dùng `Math.multiplyExact` (hoặc `BigInteger/BigDecimal` với rounding và scale rõ ràng) thay vì chấp nhận overflow thành số âm hoặc số nhỏ.

## 9. Spring Integration Java DSL: Transformer → ValidationOutcome → Router

Cấu hình dưới đây là **ví dụ một flow hoàn chỉnh trong cùng JVM**: ingest `ExternalOrder`, normalize thành `CanonicalOrder`, kiểm policy, route tới nhánh chấp nhận hoặc từ chối.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class PostTransformValidationConfiguration {

    @Bean("orders.raw.in")
    DirectChannel input() {
        return new DirectChannel();
    }

    @Bean("orders.validated")
    DirectChannel validated() {
        return new DirectChannel();
    }

    @Bean("orders.rejected")
    DirectChannel rejected() {
        return new DirectChannel();
    }

    @Bean("orders.business")
    QueueChannel business() {
        return new QueueChannel();
    }

    @Bean("orders.rejections.out")
    QueueChannel rejectedNotices() {
        return new QueueChannel();
    }

    @Bean
    ExternalOrderMapper externalOrderMapper() {
        return new ExternalOrderMapper();
    }

    @Bean
    OrderPolicyValidator orderPolicyValidator() {
        return new OrderPolicyValidator();
    }

    @Bean
    IntegrationFlow transformThenValidate(
            ExternalOrderMapper mapper,
            OrderPolicyValidator validator) {

        return IntegrationFlow.from("orders.raw.in")
            .transform(ExternalOrder.class, mapper::toCanonical)
            .transform(CanonicalOrder.class, validator::inspect)
            .route(
                ValidationOutcome.class,
                outcome -> outcome.valid() ? "VALID" : "INVALID",
                r -> r.channelMapping("VALID", "orders.validated")
                      .channelMapping("INVALID", "orders.rejected"))
            .get();
    }

    @Bean
    IntegrationFlow acceptedOrders() {
        return IntegrationFlow.from("orders.validated")
            .transform(ValidationOutcome.class, ValidationOutcome::order)
            .channel("orders.business")
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.rejected")
            .transform(ValidationOutcome.class, outcome ->
                new RejectionNotice(
                    outcome.order().orderId(), outcome.issues()))
            .channel("orders.rejections.out")
            .get();
    }
}
~~~

**Ý nghĩa của thiết kế:**

- `orders.raw.in` chỉ nhận dữ liệu kiểu `ExternalOrder` từ boundary đã được kiểm tra.
- Transformer đầu chuyển sang `CanonicalOrder`; lỗi parse được phân loại là transformation error.
- Transformer kế tạo `ValidationOutcome` có issues.
- Router gửi `VALID` tới handler nhận **payload canonical**; gửi `INVALID` tới nhánh rejection.
- Nhánh rejection trả một `RejectionNotice`, **không chuyển payload lỗi sang business handler**.
- `QueueChannel` là điểm quan sát test, không có nghĩa dữ liệu đã được xử lý nghiệp vụ hoặc đã lưu bền.

### 9.1. Vì sao route thay vì Filter ở ví dụ chính?

Vì bài toán cần **trả lý do từ chối**. Một Filter dựa trên Boolean có thể chặn được message nhưng không bảo đảm mang theo danh sách violations. Dùng `ValidationOutcome` và Router giúp hai luồng có **contract rõ ràng**.

Lưu ý các tên overload Java DSL có thể khác theo phiên bản Spring Integration. Ví dụ theo mô hình API Java DSL hiện đại, cần build/test bằng phiên bản của dự án trong vòng Content QA sau này; STEP 4 NEW này chỉ soạn tài liệu, chưa chạy build.

### 9.2. ValidationOutcome không phải business command

Sau Router, bước `acceptedOrders` lấy lại `CanonicalOrder`. Không nên gửi nguyên `ValidationOutcome` đến inventory vì consumer kho không nhất thiết cần biết chi tiết validate. Ngược lại, không đưa `RejectionNotice` vào cùng channel với lệnh giữ hàng vì có thể gây nhầm contract hoặc lỗi cast runtime.

### 9.3. Headers và correlation qua Transformer

Spring Integration transformers có cơ chế xử lý message và headers theo implementation/cấu hình. Cần kiểm chứng rằng những metadata **được phép chuyển tiếp** như `businessCorrelationId`, `executionId`, `replyChannel`/`errorChannel` còn phù hợp ở từng boundary.

Đặc biệt, đừng giả định:

- Message ID của envelope luôn giống message gốc.
- Một header `validated=true` đủ chứng minh caller có quyền.
- `contentType` của payload nguồn vẫn mô tả đúng payload sau Transformer.
- Header chứa principal/credentials được phép đi ra broker.
- Một Transformer tự giữ mọi header tùy biến qua mọi HTTP/JMS/Kafka adapter.

## 10. Biến thể: dùng Message Filter khi chỉ cần accept/drop

Nếu use case đơn giản, không cần báo nhiều lý do bị từ chối, có thể dùng `.filter(...)` sau `.transform(...)`:

~~~java
@Bean
IntegrationFlow simpleFilterAfterTransform(
        ExternalOrderMapper mapper,
        OrderPolicyValidator validator) {

    return IntegrationFlow.from("orders.simple.in")
        .transform(ExternalOrder.class, mapper::toCanonical)
        .filter(
            CanonicalOrder.class,
            canonical -> validator.inspect(canonical).valid(),
            spec -> spec.discardChannel("orders.invalid.out"))
        .channel("orders.simple.accepted")
        .get();
}
~~~

Đây là **một biến thể code fragment**, cần khai báo các channels và beans tương ứng khi đưa vào ứng dụng. Ý nghĩa:

1. Message chuyển đổi thành `CanonicalOrder`.
2. Predicate trả `true` nếu không có issues.
3. Message hợp lệ đi tiếp.
4. Message không đạt đi vào `discardChannel` theo cấu hình.

**`discardChannel` nhận message bị Filter chặn**, không mặc nhiên nhận `RejectionNotice` với danh sách errors. Nếu muốn errors, phải tạo chúng **trước Filter**, thêm header tin cậy hoặc chuyển sang mẫu typed outcome ở mục 9.

### 10.1. `throwExceptionOnRejection` có tác động gì?

Message Filter có thể cấu hình **ném exception khi từ chối** theo API tương ứng. Điều này hữu ích nếu rejection phải làm fail một request–reply ngay và caller biết cách map exception. Nhưng **không nên** dùng cho mọi lỗi validation trong asynchronous flow, vì một exception có thể dẫn tới retry lặp lại **cùng dữ liệu sai**.

Phân biệt:

| Mục tiêu | Gợi ý |
| --- | --- |
| Bỏ qua message không cần xử lý và chấp nhận không có reply | Filter drop theo contract |
| Chuyển message bị loại sang một kênh | `discardChannel` |
| Trả danh sách lỗi nghiệp vụ cho caller | Typed `ValidationOutcome` → rejection branch |
| Làm fail request đồng bộ có kiểm soát | Exception được mapping thành domain error |
| Xử lý lỗi parse/IO bất thường | Error channel/retry/quarantine theo loại lỗi |

Một Gateway đang đợi phản hồi **có thể timeout** nếu message bị Filter drop mà không có discard/reply flow. Vì vậy **thiết kế sự hiện diện của reply** quan trọng không kém predicate.

## 11. Bean Validation sau Transformer

Thay vì viết tất cả constraints bằng tay, có thể dùng **Jakarta Bean Validation** (ví dụ Hibernate Validator phù hợp phiên bản Spring Boot). Các annotations hỗ trợ các ràng buộc field đơn giản:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

record AnnotatedCanonicalOrder(
    @NotBlank String tenantId,
    @NotBlank String orderId,
    @Pattern(regexp = "[A-Z0-9-]{1,64}") String sku,
    @Min(1) @Max(500) int quantity,
    @Min(0) long unitPriceMinor,
    @Pattern(regexp = "VND|USD") String currency
) {}
~~~

Sau khi Transformer tạo DTO đã annotate, gọi `Validator.validate(...)` một cách tường minh:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

final class BeanValidationInspector {
    private final Validator validator;

    BeanValidationInspector(Validator validator) {
        this.validator = validator;
    }

    Set<ConstraintViolation<AnnotatedCanonicalOrder>> inspect(
            AnnotatedCanonicalOrder order) {
        return validator.validate(order);
    }
}
~~~

**Điểm cần nhớ:** việc khai báo annotations trên một record không có nghĩa **bất kỳ Transformer nào tạo record cũng tự gọi Bean Validation**. Bước kiểm phải được kích hoạt bằng integration endpoint, service method validation hoặc một interceptor được cấu hình phù hợp.

### 11.1. Bean Validation không thay cross-field và state validation

Có thể dùng custom constraint để kiểm `quantity × price`, nhưng quy tắc phụ thuộc inventory/balance thời điểm commit không thích hợp biến thành một lần đọc cache trong validator rồi tin nó mãi mãi.

Một pipeline tốt có thể dùng:

~~~text
Bean Validation (shape + field constraints)
   +
Custom Domain Rules (cross-field and policy)
   +
Transactional Business Preconditions (at commit)
~~~

### 11.2. Nhóm validation theo version/use case

Với một canonical model dùng nhiều ngữ cảnh, có thể định nghĩa **validation groups** hoặc các DTO riêng cho `CreateOrder` và `AmendOrder`. Nếu tạo đơn bắt buộc có `currency`, nhưng cập nhật partial cho phép thiếu `currency`, không nên dùng một rule chung không phân biệt command type.

Rule cần có **policy/schema version** nếu message có thể retry/DLQ replay sau khi code đã nâng cấp. Một message cùng bytes có thể bị đánh giá khác nếu rules đã thay đổi; hợp đồng cần quy định revalidation/reprocessing có được phép hay không.

## 12. Lỗi parsing, lỗi validation và lỗi nghiệp vụ phải đi đường khác nhau

| Loại lỗi | Ví dụ | Cách phân loại | Hướng xử lý |
| --- | --- | --- | --- |
| **Representation** | `quantityText="xyz"` | Transformer không thể parse | Invalid input/parse error |
| **Canonical validation** | `quantity=-3` | DTO tồn tại nhưng vi phạm policy | `RejectionNotice` với code |
| **Authorization** | Đơn của tenant khác | Principal không có quyền | Security error, không retry mù |
| **Transient technical** | DB timeout, HTTP 503 | Downstream có thể phục hồi | Bounded retry/backoff |
| **Business-state conflict** | Hết hàng, đơn đã chốt | Điều kiện commit không đạt | Outcome nghiệp vụ terminal hoặc retry có điều kiện |
| **Integrity/schema drift** | Event phiên bản mới chưa hỗ trợ | Contract không tương thích | Quarantine + schema handling |

### 12.1. Không biến mọi lỗi thành `false`

Một anti-pattern:

~~~java
// KHÔNG NÊN: lỗi DB cũng bị hiểu là "validation failed".
try {
    return remoteService.validate(order);
} catch (Exception ex) {
    return false;
}
~~~

Nếu remote call timeout, không thể kết luận order không hợp lệ. Hãy tạo trạng thái `UNKNOWN`/`VALIDATION_UNAVAILABLE` hoặc đẩy vào error/retry path. Một Filter Boolean phù hợp cho điều kiện xác định được một cách đáng tin; nó không đủ biểu diễn **lỗi kỹ thuật không chắc chắn**.

### 12.2. Lỗi đồng bộ và bất đồng bộ

Trong flow dùng `DirectChannel`, exception của Transformer/handler có thể **lan về thread gửi**. Trong flow có `ExecutorChannel`, poller, broker adapter, lỗi có thể được đóng gói thành `ErrorMessage` theo cơ chế endpoint/container và đưa tới error channel nếu được cấu hình.

Không nên viết tài liệu giả định cứ gọi `.filter(...)` bị từ chối thì Spring Integration tự tạo một `ErrorMessage`. **Rejection** và **exception** là hai cơ chế khác nhau.

### 12.3. Retry cùng dữ liệu sai chỉ làm tăng tải

Nếu `quantity=-3` là lỗi terminal, retry qua RabbitMQ/Kafka hoặc RequestHandlerRetryAdvice không làm nó hợp lệ. Đưa rejected message tới kênh riêng để caller sửa, quarantine có TTL/retention và audit mã lỗi. Đừng để nó lặp vô hạn trong DLQ/retry topic.

## 13. Message Filter sau Transformer và Aggregator

Một tình huống dễ sai: **Splitter → Transformer → Filter → Aggregator**.

~~~text
Batch ORD-901: expected 3 order lines
   |
   v
Splitter: LINE-1, LINE-2, LINE-3
   |
   +--> LINE-1 → valid   → success result
   +--> LINE-2 → invalid → Filter drops silently
   +--> LINE-3 → valid   → success result
   |
   v
Aggregator: has 2/3, may wait forever
~~~

Nếu Aggregator đợi `sequenceSize=3` hoặc ba unique item IDs, việc drop im lặng LINE-2 làm **không bao giờ đủ phần**.

### 13.1. Giải pháp: chuyển validation failure thành một kết quả có kiểu

~~~text
LINE-1 → ItemOutcome(lineId=1, status=ACCEPTED)
LINE-2 → ItemOutcome(lineId=2, status=REJECTED,
                     codes=[QUANTITY_OUT_OF_RANGE])
LINE-3 → ItemOutcome(lineId=3, status=ACCEPTED)
          |
          v
Aggregator releases 3/3 → BatchOutcome(PARTIAL/REJECTED)
~~~

Trong flow này, **một kết quả từ chối vẫn là kết quả của một item**, không phải message bị mất. Aggregator có thể release khi nhận đủ **unique line IDs** rồi tạo outcome hợp đồng.

### 13.2. Không dùng `group.size()` thay unique business IDs

Nếu LINE-1 bị redeliver hai lần và LINE-2 bị Filter bỏ, Aggregator có thể nhận:

~~~text
LINE-1: ACCEPTED
LINE-1: ACCEPTED (duplicate)
LINE-3: ACCEPTED
~~~

Ba raw messages không chứng minh ba phần nghiệp vụ đã có kết quả. Dedupe theo `(executionId, lineId)`; group correlation theo execution, idempotency của side effect theo command/line/operation key riêng.

### 13.3. Lỗi validation có thể là terminal item outcome

Nếu LINE-2 đã được xác định là **không hợp lệ**, caller không nhất thiết muốn retry nó. Tạo `ItemRejected` có code và line ID, đưa qua reply path được Aggregator chấp nhận; nếu business contract yêu cầu **all-or-nothing**, Aggregator vẫn có thể trả `FAILED` cho toàn batch dù đủ ba kết quả.

**Đủ phản hồi** và **thành công nghiệp vụ** là hai chiều độc lập.

## 14. Validation trước Router và Gateway

Nếu Router quyết định đích theo nội dung canonical như `currency` hoặc `countryCode`, phải xác minh key trước khi route. Một default channel không phù hợp có thể khiến dữ liệu sai lạc tới endpoint có quyền rộng hơn.

~~~mermaid
flowchart LR
    IN["Raw order"] --> T["Transformer"]
    T --> V{"Validate canonical"}
    V -->|"Valid"| R{"Router theo currency"}
    R -->|"VND"| VN["Domestic payment"]
    R -->|"USD"| US["International payment"]
    V -->|"Invalid"| E["Rejection"]
~~~

Một số quy tắc:

- Không đưa `currency="XYZ"` sang default payment channel rồi mới phát hiện chưa hỗ trợ.
- Không lấy `destinationTenant` từ payload chưa xác thực để chọn channel có quyền tenant đó.
- Giới hạn những header có thể được client ảnh hưởng trước khi Router dùng chúng.
- Nếu Gateway gửi command có side effect, giữ idempotency key qua Validator và Transformer.
- Validation nên xảy ra **trước** điểm phát side effect, nhưng điều kiện phụ thuộc state vẫn cần kiểm tại transaction của handler.

## 15. Unit test: Mapper và Validator

Hai phần này là **Java thuần**, có thể kiểm tra nhanh bằng JUnit 5 mà không dựng Spring context.

### 15.1. Test mapping và normalization

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExternalOrderMapperTest {

    private final ExternalOrderMapper mapper = new ExternalOrderMapper();

    @Test
    void normalizesValidPartnerOrder() {
        ExternalOrder raw = new ExternalOrder(
            "shop-a", "PO-901", " book-42 ",
            " 003 ", "25000", " vnd ");

        CanonicalOrder result = mapper.toCanonical(raw);

        assertEquals("BOOK-42", result.sku());
        assertEquals(3, result.quantity());
        assertEquals(25_000L, result.unitPriceMinor());
        assertEquals("VND", result.currency());
    }

    @Test
    void validIntegerRepresentationCanStillBeBadDomainData() {
        CanonicalOrder result = mapper.toCanonical(
            new ExternalOrder(
                "shop-a", "PO-902", "BOOK-42",
                "-3", "25000", "VND"));

        assertEquals(-3, result.quantity());
        assertFalse(new OrderPolicyValidator()
            .inspect(result).valid());
    }

    @Test
    void malformedQuantityFailsAtTransformerBoundary() {
        InvalidRepresentationException ex = assertThrows(
            InvalidRepresentationException.class,
            () -> mapper.toCanonical(new ExternalOrder(
                "shop-a", "PO-903", "BOOK-42",
                "three", "25000", "VND")));

        assertEquals("QUANTITY_NOT_INTEGER", ex.getMessage());
    }

    @Test
    void hugePriceCannotSilentlyOverflowDuringParsing() {
        assertThrows(InvalidRepresentationException.class,
            () -> mapper.toCanonical(new ExternalOrder(
                "shop-a", "PO-904", "BOOK-42",
                "1", "999999999999999999999", "VND")));
    }
}
~~~

### 15.2. Test validation và error codes

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class OrderPolicyValidatorTest {

    private final OrderPolicyValidator validator =
        new OrderPolicyValidator();

    @Test
    void acceptsCanonicalOrder() {
        CanonicalOrder order = new CanonicalOrder(
            "shop-a", "PO-901", "BOOK-42",
            3, 25_000L, "VND");

        ValidationOutcome result = validator.inspect(order);

        assertTrue(result.valid());
        assertTrue(result.issues().isEmpty());
    }

    @Test
    void collectsMoreThanOneDomainIssue() {
        CanonicalOrder order = new CanonicalOrder(
            "shop-a", "PO-902", "***",
            -3, -100, "XYZ");

        ValidationOutcome result = validator.inspect(order);
        Set<String> codes = result.issues().stream()
            .map(ValidationIssue::code)
            .collect(Collectors.toSet());

        assertFalse(result.valid());
        assertTrue(codes.contains("SKU_FORMAT_INVALID"));
        assertTrue(codes.contains("QUANTITY_OUT_OF_RANGE"));
        assertTrue(codes.contains("PRICE_OUT_OF_RANGE"));
        assertTrue(codes.contains("UNSUPPORTED_CURRENCY"));
    }

    @Test
    void rejectsQuantityAboveBusinessLimit() {
        ValidationOutcome result = validator.inspect(
            new CanonicalOrder(
                "shop-a", "PO-903", "BOOK-42",
                501, 25_000L, "VND"));

        assertTrue(result.issues().stream()
            .anyMatch(issue ->
                issue.code().equals("QUANTITY_OUT_OF_RANGE")));
    }
}
~~~

Các tests trên chỉ kiểm mapping và validation **trong JVM**. Chúng chưa chứng minh wiring Spring Integration đúng hoặc lỗi đã được route sang kênh mong muốn.

## 16. Integration test: accepted/rejected phải đi đúng kênh

Dùng cấu hình `PostTransformValidationConfiguration` ở mục 9. Với QueueChannel, test có thể quan sát **một output được chấp nhận** và **một rejection notice**, đồng thời xác nhận nhánh còn lại không nhận message.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PostTransformValidationConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class PostTransformValidationFlowTest {

    @Autowired @Qualifier("orders.raw.in")
    MessageChannel input;

    @Autowired @Qualifier("orders.business")
    PollableChannel accepted;

    @Autowired @Qualifier("orders.rejections.out")
    PollableChannel rejected;

    private boolean send(
            String orderId, String quantityText, String currency) {
        ExternalOrder raw = new ExternalOrder(
            "shop-a", orderId, "book-42",
            quantityText, "25000", currency);

        return input.send(MessageBuilder.withPayload(raw)
            .setHeader("businessCorrelationId", orderId)
            .build());
    }

    @Test
    void validCanonicalOrderReachesBusinessBranchOnly() {
        assertTrue(send("PO-901", " 003 ", "vnd"));

        Message<?> approved = accepted.receive(1000);
        assertNotNull(approved);
        assertInstanceOf(CanonicalOrder.class, approved.getPayload());

        CanonicalOrder order = (CanonicalOrder) approved.getPayload();
        assertEquals("BOOK-42", order.sku());
        assertEquals(3, order.quantity());
        assertEquals("VND", order.currency());

        assertNull(rejected.receive(0),
            "Valid input must not reach rejection branch");
        assertNull(accepted.receive(0),
            "Exactly one canonical output expected");
    }

    @Test
    void invalidCanonicalOrderReachesRejectionOnly() {
        assertTrue(send("PO-902", "-3", "vnd"));

        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);
        assertInstanceOf(RejectionNotice.class, denied.getPayload());

        RejectionNotice notice =
            (RejectionNotice) denied.getPayload();

        assertEquals("PO-902", notice.orderId());
        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "QUANTITY_OUT_OF_RANGE".equals(issue.code())));

        assertNull(accepted.receive(0),
            "Invalid order must not reach business branch");
        assertNull(rejected.receive(0),
            "Exactly one rejection notice expected");
    }

    @Test
    void normalizedButUnsupportedCurrencyIsRejected() {
        assertTrue(send("PO-903", "3", "xyz"));
        Message<?> denied = rejected.receive(1000);
        assertNotNull(denied);

        RejectionNotice notice =
            (RejectionNotice) denied.getPayload();

        assertTrue(notice.issues().stream()
            .anyMatch(issue ->
                "UNSUPPORTED_CURRENCY".equals(issue.code())));
        assertNull(accepted.receive(0));
    }
}
~~~

**Phạm vi:** Đây là integration test của các channels và Transformers/Router **trong một Spring context**, không kiểm tra DB thật, broker, JWT, external API hoặc transaction của tồn kho.

### 16.1. Test lỗi parsing phải khác test rejection

Nếu gửi `quantityText="abc"`, Transformer ném `InvalidRepresentationException` trước khi tạo `ValidationOutcome`. Với `DirectChannel`, exception có thể lan qua một `MessagingException`. Tùy exception wrapping và cấu hình, test nên assert **mã lỗi nguyên nhân** và **không có output ở business/rejection queue** nếu parser error được xử lý ở đường error riêng.

Không nên mong mặc định nó biến thành `RejectionNotice`; nếu API yêu cầu một phản hồi lỗi đồng nhất, hãy thiết kế **error-to-response mapping** ở boundary.

### 16.2. Assert cả nhánh không được chọn

Một test chỉ assert có `RejectionNotice` không phát hiện trường hợp dữ liệu lỗi **đồng thời vẫn đi vào business branch**. Với validation trước side effect, negative assertion `accepted.receive(0) == null` là một phần quan trọng.

Nếu downstream chạy bất đồng bộ, cần test bằng bounded await, không dùng `receive(0)` để “chứng minh vĩnh viễn không có message”; các kiểm tra âm cần đồng bộ hóa và deadline phù hợp.

## 17. Ma trận kiểm thử toàn diện

| Kịch bản | Input | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | `quantityText="003"`, `currency="vnd"` | Canonical quantity=3, currency=VND, đi business |
| Số âm | `quantityText="-3"` | Mapper thành công, validator reject |
| Số bằng 0 | `quantityText="0"` | Rejected theo policy |
| Số vượt ngưỡng | `quantityText="501"` | `QUANTITY_OUT_OF_RANGE` |
| Chữ thay số | `quantityText="three"` | Transformation error, không tạo canonical |
| Số quá lớn | Chuỗi giá vượt long | Parse error, không overflow âm |
| SKU khoảng trắng | `sku=" "` | `SKU_FORMAT_INVALID` |
| SKU lowercase | `sku="book-42"` | Normalize đúng nếu contract cho phép |
| Currency lowercase | `currency="vnd"` | Normalize và accept |
| Currency không hỗ trợ | `currency="ABC"` | `UNSUPPORTED_CURRENCY` |
| Nhiều lỗi một DTO | Quantity âm, price âm, currency sai | Nhiều issues có code |
| Header tenant giả mạo | Principal tenant A, payload tenant B | Deny trước side effect |
| Message lớn quá ngưỡng | Input vượt size limit | Reject trước parse/transform |
| Null field | `tenantId=null` | Domain/structural rejection theo contract |
| Lỗi DB trong business step | DB timeout | Technical retry/error, không coi là invalid input |
| Filter drop im lặng | Gateway chờ reply | Test bắt được thiếu rejection/timeout |
| Splitter 3 child, 1 invalid | Một dòng bị chặn | Aggregator nhận ItemRejected hoặc xử lý group expiry |
| Duplicate child | Cùng lineId giao lại | Không tính hai kết quả nghiệp vụ |
| Reorder message | Hai execution xen kẽ | Correlation không trộn nhóm |
| Retry sau commit | ACK lost/redelivery | Idempotent handler không tạo effect thêm |
| Adapter qua broker | JMS/Kafka header mapper | Metadata tin cậy tồn tại đúng contract |
| Policy version thay đổi | DLQ replay dữ liệu cũ | Được xử lý theo chiến lược version rõ |
| Rejection chứa PII | Input dữ liệu nhạy cảm | Response/log không lộ raw value |
| Caller quyền hạn khác | Hai tenant dùng cùng ID | Authorization và scope ngăn chặn |

## 18. Validation có phiên bản và dữ liệu cũ trên DLQ

Giả sử policy tại thời điểm T1 cho phép `quantity<=500`; sau một tháng, policy đổi thành `quantity<=100`. Một message đã bị DLQ và được replay ở T2 có `quantity=300`.

Các lựa chọn:

1. **Revalidate theo policy mới:** phù hợp khi command chưa từng được chấp nhận và luật hiện tại phải áp dụng; cần thông báo lý do.
2. **Pin policy version của execution:** phù hợp khi workflow đã được tạo theo hợp đồng/giá tại thời điểm cũ và phải giữ tính tái lập.
3. **Migration có kiểm soát:** chuyển schema/policy, ghi rõ việc dữ liệu đổi nghĩa và xác thực lại quyền.

Không nên âm thầm đưa một message cũ qua Transformer mới tạo dữ liệu khác mà không audit. `schemaVersion`, `policyVersion`, `receivedAt` và nguồn đáng tin có thể cần thiết để giải thích vì sao cùng input cho kết quả khác giữa các thời điểm.

### 18.1. Idempotency và validation có thứ tự nào?

Một duplicate của operation đã commit có thể gặp **policy validation mới** không chấp nhận input cũ. Không được retry cùng command rồi âm thầm tạo một business effect mới vì idempotency lookup đến sau quá muộn.

Với các command có side effect, xác thực nguồn/tenant/operation identity trước; sau đó cân nhắc **truy vấn trạng thái operation đã commit** và trả persisted outcome theo contract, đồng thời xử lý schema/validation của request một cách nhất quán. Không có một thứ tự chung phù hợp mọi API, nhưng **không được dùng thay đổi policy để bỏ qua idempotency**.

### 18.2. Header `validated` có thể bị stale

Nếu một message đã được validate ở bước A, rồi Transformer B đổi currency, quantity hoặc chủ thể sở hữu, header `validated=true` của bước A **không còn là bằng chứng** dữ liệu sau B hợp lệ. Với pipeline nhạy cảm, gắn validation result theo **model/schema/policy version**, hoặc chạy validation lại ở boundary cần đảm bảo invariant.

## 19. Observability: đo rejection mà không lộ dữ liệu

Các metrics có ích:

| Điểm đo | Metric / signal | Ý nghĩa |
| --- | --- | --- |
| Inbound | `inbound_invalid_schema_total` | Lỗi representation ban đầu |
| Transformer | `transform_failed_total` theo error category | Parse/mapping failures |
| Validator | `validation_passed_total` | Message canonical hợp lệ |
| Validator | `validation_rejected_total` theo error code | Domain violations |
| Router | `accepted_routed_total` | Message hợp lệ đi đúng nhánh |
| Router | `rejection_routed_total` | Có rejection path, không silent drop |
| Business handler | `side_effect_committed_total` | Kết quả nghiệp vụ thật |
| Error channel | `technical_error_total` | Lỗi hạ tầng khác rejection |
| Aggregator | `missing_child_outcome_total` | Có child bị drop/lỗi khiến group thiếu |
| Retry | `retry_attempts_total` | Phát hiện retry storm do phân loại lỗi sai |

Các nhãn `validationCode`, `sourceType`, `schemaVersion`, `endpoint` thường có tập giá trị kiểm soát được. Không gắn `orderId`, `tenantId`, `email`, `correlationId` tùy ý làm metric tags có cardinality cao.

### 19.1. Log rejection có kiểm soát

~~~json
{
  "event": "post_transform_validation_rejected",
  "businessCorrelationId": "PO-902",
  "schemaVersion": "external-order-v1",
  "policyVersion": "canonical-order-v1",
  "errorCodes": ["QUANTITY_OUT_OF_RANGE"],
  "branch": "orders.rejections.out"
}
~~~

Đây là **schema log minh họa của ứng dụng**, không phải log tự có của Spring Integration. Cần giới hạn độ dài, masking IDs/PII theo quy định, và tránh log raw payload, access tokens, chi tiết stack trace ra client.

### 19.2. Validation latency

Một validator thuần tính toán ở JVM thường rẻ. Nếu nó gọi nhiều API bên ngoài, độ trễ và số lượng retries có thể tăng. Tách validation deterministic khỏi enrichment/state checks và đo latency riêng. Đặt giới hạn tài nguyên cho các thao tác regex, parse, mảng lớn hoặc dữ liệu có cấu trúc sâu để tránh DoS.

## 20. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng cải thiện |
| --- | --- | --- |
| “Transformer parse được nên đã hợp lệ” | Quantity âm/price sai lọt tới handler | Validate canonical DTO |
| Chỉ validate raw JSON rồi bỏ qua canonical | Normalize/defaulting làm đổi invariants | Validate sau transform |
| Mapper trả `0` khi parse thất bại | Che lỗi representation | Throw typed parse error |
| Filter drop và không có reply cho Gateway | Caller timeout khó giải thích | Rejection branch/typed response |
| Ném exception cho mọi domain violation | Retry cùng dữ liệu sai qua broker | Phân loại terminal rejection |
| Filter bắt mọi exception và trả false | DB outage bị coi là dữ liệu sai | Technical error path riêng |
| Header `validated=true` tin từ client | Bypass kiểm tra | Trusted validator và policy version |
| Validation thay thế authorization | Cross-tenant side effect | AuthN/AuthZ tại boundary đáng tin |
| SKU normalize không theo hợp đồng | Collide các mã khác nhau | Versioned canonicalization |
| Xem `contentType` cũ vẫn đúng sau transform | Serialization/consumer hiểu sai | Mô tả content type mới |
| Dùng Filter sau Splitter rồi drop child | Aggregator chờ thiếu nhóm mãi | ItemRejected hoặc group expiry |
| Đếm raw messages thay unique item IDs | Duplicate làm release sớm | Idempotent child correlation |
| Chỉ test positive branch | Message lỗi có thể vẫn tới handler | Assert negative branch và no side effects |
| Dùng test một JVM rồi suy ra end-to-end | Bỏ sót adapter/DB/retry | Integration/contract tests theo boundary |
| Không giới hạn length/range | Overflow, DoS, quá tải | Input limits + numeric checks |
| Trả raw payload trong rejection | Lộ dữ liệu nhạy cảm | Error codes, projection, masking |
| Revalidate DLQ không xem policy version | Replay dữ liệu cũ bị đổi nghĩa | Versioned migration/policy snapshot |
| Chỉ kiểm state tồn kho trước API | Race đến thời điểm commit | Atomic business precondition |

## 21. Checklist triển khai

- [ ] Có validation cho input schema, size, authentication và tenant **trước** Transformer.
- [ ] Transformer chỉ parse/normalize theo contract; lỗi representation không bị che thành default tùy tiện.
- [ ] DTO canonical có bộ invariants rõ ràng, test cho field và cross-field.
- [ ] Validation sau Transformer nằm **trước Router/Gateway/handler có side effect**.
- [ ] Có tiêu chí phân biệt domain rejection, transient technical errors và business-state failure.
- [ ] Caller cần thông báo thì có typed rejection với field/code, không silent drop.
- [ ] Nếu dùng Filter, discard channel/reply semantics được test rõ.
- [ ] Nếu dùng Bean Validation, `Validator.validate(...)` thực sự được kích hoạt, không chỉ annotate DTO.
- [ ] Quy tắc normalize và policy có version; replay sau nâng cấp có contract.
- [ ] Validation không thay thế AuthN/AuthZ hoặc transaction-state checks.
- [ ] Source/tenant/correlation/operation IDs được xác thực và truyền qua các boundary cần thiết.
- [ ] Không gửi lại dữ liệu lỗi terminal vô hạn qua retry topics/DLQ.
- [ ] Splitter/Aggregator có ItemRejected hoặc release/expiry policy thay vì mất message âm thầm.
- [ ] Có unit tests Mapper/Validator và integration tests hai nhánh, bao gồm **nhánh không được đi**.
- [ ] Có test parsing overflow, numeric bounds, invalid currency, wrong tenant và policy migration.
- [ ] Có metrics error category, accepted/rejected count, nhưng không log PII/raw token.
- [ ] Có idempotency ở nơi business effect thực thi; Filter pass không đảm bảo exactly-once.

## 22. Bài tập thực hành

Một hệ thống nhập lô hóa đơn từ ba đối tác. Mỗi đối tác gửi:

~~~json
{
  "partnerId": "partner-a",
  "invoiceNo": "INV-2026-51",
  "amountText": " 125000 ",
  "currencyText": " vnd ",
  "dueDateText": "2026-12-01",
  "customerRef": "CUST-51"
}
~~~

Sau Transformer, hệ thống cần `CanonicalInvoice(partnerId, invoiceNo, amountMinor, currency, dueDate, customerRef)`. Theo policy:

- `amountMinor` phải lớn hơn 0 và không vượt hạn mức theo loại hóa đơn.
- `currency` nằm trong tập cho phép, đã normalize.
- `dueDate` không được trước ngày phát hành được xác minh.
- `invoiceNo` phải phù hợp format và unique theo partner namespace (kiểm tra uniqueness **tại commit** nếu nhiều instance).
- Tenant/partner identity phải đến từ nguồn xác thực, không chỉ từ payload.
- Batch có thể gồm 100 hóa đơn; caller cần biết hóa đơn nào bị từ chối.

**Yêu cầu:**

1. Vẽ flow `Inbound → Parse schema → Transformer → Bean Validation → Domain rules → Router accepted/rejected → Handler`.
2. Viết Java records cho external invoice, canonical invoice và `ValidationOutcome` chứa error codes.
3. Phân loại dữ liệu `amountText="abc"`, `amountText="-1"`, `currencyText="xyz"` và `dueDateText="not-a-date"`: lỗi nào ở Transformer, lỗi nào sau Transformer?
4. Thiết kế validation cho `amount × taxRate` mà không bị overflow và có quy tắc rounding.
5. Chỉ ra vị trí bắt buộc AuthN/AuthZ cho partner identity và idempotency key cho `invoiceNo`.
6. Dùng Spring Integration Java DSL để chuyển dữ liệu, đánh giá policy và route đúng nhánh.
7. Tạo rejection DTO không chứa `customerRef` hay nội dung nhạy cảm nếu caller không có quyền.
8. Viết JUnit tests cho input hợp lệ, parsing error, negative amount, unsupported currency, missing field và cross-field rule.
9. Viết integration test chứng minh rejected invoice **không thể đi vào** handler ghi sổ.
10. Nếu flow dùng Splitter/Aggregator, đưa `InvoiceRejected(invoiceNo, codes)` về nhóm để một batch 99/100 hợp lệ không bị treo chờ.
11. Với DLQ replay sau 30 ngày, giải thích cách versioning validator và không phát hóa đơn hai lần.
12. Thiết kế metrics cho parse errors, domain rejections, duplicate/conflict và business commit, không dùng customer ID làm tag.

**Gợi ý:** Trả cho caller một `BatchImportOutcome(total, imported, rejected, errorsByInvoice)`. **Rejection của một hóa đơn vẫn là một item outcome**, nhưng nếu hợp đồng yêu cầu all-or-nothing, batch outcome cần phản ánh điều đó; không tùy tiện thay đổi `expectedCount`.

## 23. Tổng kết

**Validation sau transformer** là lớp bảo vệ giữa **“dữ liệu đã đổi biểu diễn”** và **“dữ liệu được phép thực hiện nghiệp vụ”**. Transformer giúp chuẩn hóa schema nguồn, kiểu số, chữ hoa/thường và cấu trúc; validator sau đó kiểm quantity, amount, currency, cross-field invariants và chính sách canonical. Việc parse thành công **không chứng minh domain correctness**, và validation ở một điểm **không thay thế authorization hay kiểm tra trạng thái nguyên tử tại commit**.

Trong Spring Integration, có thể kết hợp `.transform(...)` với `.filter(...)` cho điều kiện đơn giản hoặc với **ValidationOutcome + Router** để tạo accepted/rejected branches có typed error codes. Xử lý lỗi representation, domain rejection và technical failure theo các đường khác nhau; không drop child im lặng trước Aggregator, không retry mãi dữ liệu sai, và kiểm thử cả positive/negative paths. Kết hợp Router, Splitter/Aggregator, Gateway, retry/error channel, correlation và idempotency để chỉ **message canonical hợp lệ, có quyền và đúng business operation** mới đến được điểm tạo side effect.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Filter, Message Translator, Content-Based Router, Splitter, Aggregator); Spring Integration Reference về Message Filter, Transformers, Router, Java DSL, Message Channels, Error Handling và Testing; Jakarta Bean Validation specification; Spring Framework validation/transaction management; Java SE về records, `Math.multiplyExact` và `Locale.ROOT`.

