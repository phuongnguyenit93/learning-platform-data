# Mapping payload và metadata

> **Chương:** Message translator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này đi sâu vào **chuyển đổi payload cùng metadata của một message mà không làm sai hợp đồng, mất correlation hoặc chuyển tiếp thông tin nhạy cảm ngoài ý muốn**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Message Translator** trong Enterprise Integration Patterns (EIP) như một điểm cách ly định dạng message giữa hai hệ thống có hợp đồng khác nhau.
2. Phân biệt **payload**, **message headers**, **transport metadata** và **business metadata**; hiểu lý do cả bốn không thể sao chép tùy tiện.
3. Lập mapping contract cho field, kiểu dữ liệu, đơn vị tiền, thời gian, schema version, header correlation, idempotency và reply/error routing.
4. Viết một Message Translator Java 17 chuyển `Message<PartnerOrder>` thành `Message<WarehouseCommand>` có headers được tạo/kiểm tra rõ.
5. Dùng Spring Integration Java DSL để tích hợp Translator với `Service Activator`, `DirectChannel` và `QueueChannel`, đồng thời hiểu biến thể `.transform(...)`.
6. Phân tích metadata nào phải **preserve**, **rename**, **derive**, **drop** hoặc **recompute** khi đi qua HTTP, Kafka, AMQP, JMS và các kênh nội bộ.
7. Phân biệt lỗi mapping/validation với lỗi kỹ thuật; giữ đúng behavior của Gateway, Router, Splitter/Aggregator, retry, redelivery và idempotent consumer.
8. Viết unit/integration/contract tests xác minh không chỉ payload mà còn headers, quyền, source provenance và các đường lỗi.

## 2. Vấn đề: message nguồn hợp lệ nhưng message đích không dùng được

Một đối tác gửi lệnh đặt hàng theo JSON:

~~~json
{
  "partnerOrderNo": "PO-901",
  "sku": " book-42 ",
  "quantityText": "003",
  "unitPriceMajor": "12.50",
  "currency": "usd",
  "requestedAt": "2026-11-21T15:00:00+07:00",
  "deliveryNote": "Giao giờ hành chính"
}
~~~

Adapter của nguồn đã xác thực người gửi và tạo message nội bộ có metadata như sau:

~~~text
Payload: PartnerOrder(...)
Headers do hệ thống xác minh/cấp:
  trustedTenant        = shop-a
  trustedPartner       = partner-a
  sourceSchemaVersion  = partner-order-v1
  businessCorrelationId= ORD-901
  operationId          = CMD-901
  originalMediaType    = application/vnd.partner.order+json

Headers chỉ thuộc transport/nội bộ:
  id, timestamp, replyChannel, errorChannel, ...
Headers bên ngoài không được tin mặc định:
  authorization, cookie, arbitrary trace IDs, ...
~~~

Warehouse service cần lệnh canonical:

~~~json
{
  "tenantId": "shop-a",
  "partnerId": "partner-a",
  "partnerOrderNo": "PO-901",
  "operationId": "CMD-901",
  "sku": "BOOK-42",
  "quantity": 3,
  "unitPriceMinor": 1250,
  "currency": "USD",
  "requestedAt": "2026-11-21T08:00:00Z",
  "deliveryNote": "Giao giờ hành chính"
}
~~~

Nó còn cần **business correlation** để nối kết quả với đơn gốc và **operation ID ổn định** để chống retry tạo nghiệp vụ trùng. Nhưng warehouse **không được** nhận Authorization header của HTTP client, Java `replyChannel` object hoặc một payload gốc chứa thông tin nhạy cảm trong header.

Nếu một Transformer chỉ đổi `quantityText` thành `quantity`, nhưng quên `operationId` và `businessCorrelationId`, lệnh có thể chạy thành công **mà vẫn không thể gắn đúng reply** hoặc bị xử lý trùng khi redelivery.

**Message Translator đúng nghĩa phải bảo toàn hợp đồng của cả payload và metadata quan trọng.**

~~~mermaid
flowchart LR
    IN["Message<PartnerOrder>"] --> P["Payload mapper"]
    IN --> H["Header/metadata policy"]
    P --> V{"Validate target command"}
    H --> V
    V -->|"Valid"| OUT["Message<WarehouseCommand>"]
    V -->|"Invalid"| REJ["Typed mapping rejection"]
    OUT --> AD["Outbound adapter/header mapper"]
    AD --> W["Warehouse service"]
~~~

## 3. Message Translator trong EIP

**Message Translator** là một loại **Message Transformation**: đổi message từ định dạng mà hệ thống A hiểu sang định dạng hệ thống B hiểu. Nó đóng vai trò lớp chống tương thích/coupling khi mỗi hệ thống định nghĩa field, header, serialization và semantics khác nhau.

Trong Spring Integration, có thể thực hiện với:

- `.transform(...)` / Message Transformer khi mục tiêu là chuyển payload hoặc message representation.
- `.handle(...)` với một service trả về `Message<?>` khi muốn hiển thị rõ việc tạo cả payload lẫn headers.
- Header Enricher / Header Filter cho những chính sách metadata riêng.
- Gateway/Adapter và header mapper để dịch metadata ở ranh giới HTTP, AMQP/JMS/Kafka.
- Router chọn Translator thích hợp khi có nhiều loại source message.

### 3.1. So với các pattern dễ nhầm

| Thành phần | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Message Translator** | Đổi contract message A → B | Đơn đối tác + headers → lệnh kho + headers |
| **Transformer** | Cơ chế/endpoint đổi biểu diễn dữ liệu | `String` JSON → Java record |
| **Normalizer** | Nhiều định dạng nguồn → một định dạng chung | A/B/C translators → `CanonicalOrder` |
| **Header Enricher** | Tạo/bổ sung headers cần thiết | Thêm `businessCorrelationId` |
| **Header Filter** | Xóa metadata không được truyền | Bỏ `authorization` trước broker |
| **Content Enricher** | Bổ sung thông tin từ nguồn bên ngoài | Tra mã khách hàng theo account ID |
| **Content-Based Router** | Chọn nhánh dựa trên metadata/payload | Currency USD → channel quốc tế |
| **Claim Check** | Thay payload lớn bằng reference | File 50 MiB → object key |
| **Idempotent Receiver** | Chặn side effect trùng của cùng operation | Redelivery `CMD-901` không giữ kho thêm |

**Không đồng nhất Message Translator với JSON serializer.** Serializer có thể đổi bytes sang DTO; Translator còn phải hiểu **ý nghĩa field và metadata đích cần nhận**, ví dụ tiền ở đơn vị cent, danh tính nguồn, reply correlation và tenant boundary.

## 4. Bốn lớp thông tin trong một message

~~~text
┌────────────────────────────────────────────┐
│ Message                                   │
│  Payload: business content                │
│     order, item, amount, timestamp         │
│                                            │
│  Business metadata / headers              │
│     correlationId, operationId, tenant     │
│                                            │
│  Integration control headers              │
│     replyChannel, errorChannel, sequence   │
│                                            │
│  Transport-specific metadata              │
│     HTTP headers, JMS delivery headers,    │
│     Kafka topic/partition/offset, AMQP...  │
└────────────────────────────────────────────┘
~~~

### 4.1. Payload

Chứa dữ liệu nghiệp vụ cần cho handler đích: order ID, SKU, quantity, amount, timestamps. Translator có thể đổi tên, kiểu, cấu trúc, đơn vị và enum **theo contract rõ**.

### 4.2. Business metadata

Thông tin quản trị tương tác nghiệp vụ, ví dụ `operationId`, `businessCorrelationId`, source partner/schema version. Có thể nằm trong payload, headers hoặc cả hai theo hợp đồng. **Không tự suy tất cả metadata là đáng tin chỉ vì nó ở header.**

### 4.3. Integration-control headers

Các headers như `replyChannel`, `errorChannel` và `sequenceNumber` có ý nghĩa trong một luồng Spring Integration cụ thể. Một số là **object chỉ tồn tại trong JVM** hoặc chỉ hữu ích với Aggregator/Resequencer. Khi chuyển sang hệ thống khác, phải chuyển thành **định dạng transport phù hợp**, không serialize một `MessageChannel` tùy tiện.

### 4.4. Transport metadata

Metadata như Kafka offset, AMQP delivery tag, JMS delivery count, HTTP Authorization không phải business identity ổn định. Chúng thường do adapter/broker sở hữu, có thể thay đổi khi retry/redelivery và có hạn chế mapping theo provider.

## 5. Mapping contract: quyết định cho từng field và header

Trước khi viết Translator, lập bảng **nguồn → đích**, chính sách validate và khi thất bại.

### 5.1. Mapping payload

| Nguồn | Đích | Quy tắc | Nếu sai |
| --- | --- | --- | --- |
| `partnerOrderNo` | `partnerOrderNo` | Bảo toàn ID có phân biệt case | Reject nếu trống |
| `sku` | `sku` | Trim + uppercase **nếu SKU contract không phân biệt case** | Reject nếu ký tự sai |
| `quantityText` | `quantity` | Parse exact int, 1..500 | Reject, không default bằng 1 |
| `unitPriceMajor` | `unitPriceMinor` | `BigDecimal` USD × 100 exact | Reject nếu phải round/overflow |
| `currency` | `currency` | Normalize `USD`, kiểm allowlist | Reject unsupported |
| `requestedAt` | `requestedAt` | Offset timestamp → `Instant` | Reject nếu thiếu offset |
| `deliveryNote` | `deliveryNote` | Giữ nội dung theo giới hạn/policy | Reject quá dài hoặc sanitize đúng ngữ cảnh |
| Trusted `tenantId` | `tenantId` | Lấy từ principal/context đã xác thực | Security reject |
| Trusted `partnerId` | `partnerId` | Lấy từ adapter/server registry | Security reject |
| Trusted `operationId` | `operationId` | Giữ qua retry/redelivery | Reject nếu thiếu |

### 5.2. Mapping metadata/headers

| Header/source | Output policy | Giải thích |
| --- | --- | --- |
| `businessCorrelationId` | **Preserve** sau kiểm tra | Reply/audit theo business request |
| `operationId` | **Preserve** và đối chiếu payload đích | Stable idempotency key |
| `trustedTenant` | **Derive** ra `tenantId` của command | Không nhận namespace do client tự khai |
| `trustedPartner` | **Derive** ra `partnerId` | Scope partner có xác thực |
| `sourceSchemaVersion` | **Preserve** để audit | Biết decoder/mapping nào đã dùng |
| `targetSchemaVersion` | **Generate** | Contract output, ví dụ `warehouse-command-v1` |
| `originalMediaType` | **Preserve under new name** khi cần | Tránh content-type cũ mô tả sai payload mới |
| `contentType` | **Recompute** ở outbound serialization | Java record trong JVM không mặc nhiên là JSON bytes |
| `replyChannel` / `errorChannel` | **Preserve có điều kiện** trong cùng JVM trusted flow | Không gửi Java channel object qua broker |
| `sequenceNumber` / `sequenceSize` | **Preserve có điều kiện** nếu downstream cần group semantics | Không áp một group vào execution mới |
| `traceparent` | **Validate/delegate to tracer** | Không copy chuỗi client tự khai như quyền |
| `authorization`, `cookie`, raw JWT | **Drop** tại external boundary | Secret của một trust boundary không thuộc đích |
| `rawPayload`, `debugDump` | **Drop/Claim Check** | Tránh phát tán dữ liệu nhạy cảm hoặc payload lớn |
| `MessageHeaders.ID`, timestamp | **Recreate or framework-managed** | Envelope ID mới không phải operation ID |
| Kafka offset, AMQP deliveryTag | **Do not treat as business identity** | Metadata của từng delivery |

### 5.3. Năm hành động cốt lõi

- **Preserve:** giữ metadata có cùng ý nghĩa trong message mới.
- **Rename:** giữ giá trị nhưng đổi tên theo hợp đồng đích.
- **Derive:** tính giá trị đích từ nguồn đáng tin hoặc business rules.
- **Drop:** bỏ thứ không thuộc quyền, không cần thiết hoặc không nên rời boundary.
- **Recompute:** tạo lại content type, envelope ID, timestamp hoặc header có nghĩa khác sau transform.

**Quy tắc:** Header không có trong contract **không tự động** được phép đi sang consumer khác chỉ vì `MessageBuilder.copyHeaders(...)` làm việc đó thuận tiện.

## 6. Metadata không phải bằng chứng xác thực

Một HTTP client có thể tự gửi:

~~~http
X-Tenant-Id: shop-b
X-Operation-Id: CMD-901
X-Business-Correlation-Id: ORD-901
Authorization: Bearer ...
~~~

Nếu adapter biến nguyên các trường trên thành `trustedTenant` và cho Translator dùng mà **không xác thực**, client có thể gửi lệnh vào namespace của tenant khác.

**Ranh giới hợp lệ:**

~~~text
Untrusted transport headers
    |
    v
HTTP/JMS/Kafka adapter
  -> Authenticate producer/principal
  -> Authorize tenant, partner, schema version
  -> Validate operation/correlation IDs
  -> Strip/disallow untrusted control headers
  -> Create TrustedSourceContext / trusted headers
    |
    v
Message Translator
~~~

Tên header `trustedTenant` trong ví dụ chỉ **biểu thị contract nội bộ**; bản thân tên không khiến một string trở nên đáng tin. Adapter, security filter hoặc gateway ingress phải bảo đảm nguồn gốc và không cho client giả mạo nó.

### 6.1. Correlation và idempotency là hai nhiệm vụ riêng

Ví dụ:

~~~text
businessCorrelationId = ORD-901
operationId           = CMD-901
sourceSchemaVersion   = partner-order-v1
executionId           = RUN-901-A
MessageHeaders.ID     = random message envelope ID
~~~

- **Business correlation** liên kết các message của cùng đơn hoặc request.
- **Operation ID** nhận diện một lệnh có side effect; phải giữ qua mọi retry cùng lệnh.
- **Execution ID** gom một lượt workflow/Scatter-Gather, có thể thay đổi khi reprocess.
- **Message ID** của envelope có thể thay đổi sau khi tái tạo message.
- **Transport delivery metadata** thuộc một attempt, không làm dedup key.

Không dùng `correlationId` quá rộng để chặn mọi command trên cùng một đơn; cũng không dùng `MessageHeaders.ID` làm idempotency key khi broker có thể redeliver bằng envelope mới.

## 7. Payload mapping: đổi biểu diễn nhưng không tự ý đổi nghĩa

Ví dụ giá `"12.50" USD` phải thành `1250` minor units nếu contract đích dùng cent. Những điều kiện cần kiểm tra:

1. Currency phải có trong hợp đồng và có scale được xác định.
2. Giá major units phải được parse chính xác (`BigDecimal`), không đi qua `double`.
3. Chuyển thành minor units phải **exact**, không silently truncate.
4. Range, quantity và tổng tiền phải không overflow.
5. Timestamp phải có offset hoặc chính sách timezone rõ.
6. Enum và SKU phải được normalize **theo contract của field**, không theo thói quen uppercase mọi string.

### 7.1. Sai khác giữa representation và domain validation

| Input | Translator | Validator/domain |
| --- | --- | --- |
| `quantityText="003"` | Parse 3 | Hợp lệ nếu 1..500 |
| `quantityText="abc"` | Parse failure | Chưa có DTO canonical |
| `quantityText="-2"` | Parse được | Reject số âm |
| `unitPriceMajor="12.345"` | Cần phần lẻ cent | Reject nếu chưa có rounding policy |
| `currency="usd"` | Normalize thành USD | Hợp lệ |
| `currency="xyz"` | Không biết scale/contract | Reject unsupported |
| Timestamp không offset | Không suy được instant an toàn | Reject hoặc policy có version |

Đừng biến lỗi parser thành giá trị 0 hay enum mặc định cho dễ đi tiếp. Nếu target yêu cầu order quantity hợp lệ, **không để dữ liệu sai lọt tới Inventory Gateway** chỉ vì Translator đã sinh DTO.

## 8. Java 17: DTO nguồn và target command

Các ví dụ sau dùng **Java 17**, Spring Messaging và Spring Integration. Mỗi record/class có thể đặt trong một file tương ứng của cùng package.

~~~java
import java.time.Instant;

record PartnerOrder(
    String partnerOrderNo,
    String sku,
    String quantityText,
    String unitPriceMajor,
    String currency,
    String requestedAt,
    String deliveryNote
) {}

record WarehouseCommand(
    String tenantId,
    String partnerId,
    String partnerOrderNo,
    String operationId,
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency,
    Instant requestedAt,
    String deliveryNote
) {}
~~~

Để đơn giản và tập trung vào mapping, `WarehouseCommand` chứa dữ liệu cần cho kho; `operationId` và namespace nằm trong payload **vì hệ thống đích cần kiểm tra idempotency**. Các headers vẫn cần cho correlation/routing trong integration flow.

### 8.1. Lỗi mapping có mã

~~~java
final class TranslationFailure extends RuntimeException {
    private final String code;

    TranslationFailure(String code) {
        super(code);
        this.code = code;
    }

    TranslationFailure(String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Lỗi này đại diện cho **dữ liệu không thể chuyển theo contract**. Nó không được dùng để che `IOException`, `DataAccessException` hoặc lỗi hạ tầng ngẫu nhiên.

### 8.2. Không bắt mọi exception thành “invalid input”

~~~java
// SAI: timeout của downstream bị coi là payload sai.
try {
    return remoteService.translateAndSave(order);
} catch (Exception ex) {
    throw new TranslationFailure("INVALID_ORDER");
}
~~~

Việc mapping nên càng thuần tính toán càng tốt; side effect được đặt sau Translator, giúp retry parse không vô tình gọi lại API thanh toán/kho.

## 9. Viết một Translator cho cả payload và metadata

Ví dụ `PartnerOrderTranslator` nhận toàn bộ `Message<PartnerOrder>`, không chỉ payload, để áp dụng **hợp đồng header** cùng lúc với mapping nghiệp vụ.

**Giả định tiền đề:** Ingress đã xác thực và đặt `trustedTenant`, `trustedPartner`, `sourceSchemaVersion`, `businessCorrelationId` và `operationId`. Một client bên ngoài không có quyền tự đặt/ghi đè các headers này.

~~~java
import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

final class PartnerOrderTranslator {

    public Message<WarehouseCommand> translate(
            Message<PartnerOrder> inbound) {
        PartnerOrder raw = inbound.getPayload();
        MessageHeaders headers = inbound.getHeaders();

        // Header contract bắt buộc do trusted adapter cung cấp.
        String tenant = required(
            headers.get("trustedTenant", String.class),
            "TENANT_CONTEXT_MISSING");
        String partner = required(
            headers.get("trustedPartner", String.class),
            "PARTNER_CONTEXT_MISSING");
        String sourceVersion = required(
            headers.get("sourceSchemaVersion", String.class),
            "SOURCE_VERSION_MISSING");
        String operationId = required(
            headers.get("operationId", String.class),
            "OPERATION_ID_MISSING");
        String correlationId = required(
            headers.get("businessCorrelationId", String.class),
            "CORRELATION_ID_MISSING");

        if (!"partner-order-v1".equals(sourceVersion)) {
            throw new TranslationFailure(
                "UNSUPPORTED_SOURCE_SCHEMA");
        }
        if (!"partner-a".equals(partner)) {
            throw new TranslationFailure(
                "UNEXPECTED_SOURCE_PARTNER");
        }

        // Payload mapping, không tạo lại commandId mỗi attempt.
        String currency = canonicalCurrency(raw.currency());
        int quantity = parseQuantity(raw.quantityText());
        long unitPriceMinor = parseMinorPrice(
            raw.unitPriceMajor(), currency);

        String note = raw.deliveryNote();
        if (note != null && note.length() > 500) {
            throw new TranslationFailure(
                "DELIVERY_NOTE_TOO_LONG");
        }

        WarehouseCommand command = new WarehouseCommand(
            tenant,
            partner,
            required(raw.partnerOrderNo(), "ORDER_ID_MISSING"),
            operationId,
            canonicalSku(raw.sku()),
            quantity,
            unitPriceMinor,
            currency,
            parseRequestedAt(raw.requestedAt()),
            note
        );

        // Không copyHeaders(...) từ untrusted input.
        MessageBuilder<WarehouseCommand> result =
            MessageBuilder.withPayload(command)
                .setHeader(
                    "businessCorrelationId", correlationId)
                .setHeader("operationId", operationId)
                .setHeader("tenantId", tenant)
                .setHeader("sourceSystem", partner)
                .setHeader(
                    "sourceSchemaVersion", sourceVersion)
                .setHeader(
                    "targetSchemaVersion",
                    "warehouse-command-v1");

        // Khi contract cần truy vết MIME gốc, tách tên.
        String originalMediaType = headers.get(
            "originalMediaType", String.class);
        if (originalMediaType != null) {
            result.setHeader(
                "originalMediaType", originalMediaType);
        }

        // Chỉ hỗ trợ routing nội bộ trong cùng JVM.
        // Không serialize channel objects qua external broker.
        Object reply = headers.getReplyChannel();
        if (reply instanceof MessageChannel localReplyChannel) {
            result.setReplyChannel(localReplyChannel);
        }
        Object error = headers.getErrorChannel();
        if (error instanceof MessageChannel localErrorChannel) {
            result.setErrorChannel(localErrorChannel);
        }

        return result.build();
    }

    private static String required(String value, String code) {
        if (value == null || value.isBlank()) {
            throw new TranslationFailure(code);
        }
        return value;
    }

    private static String canonicalSku(String value) {
        String sku = required(
            value, "SKU_MISSING")
            .strip().toUpperCase(Locale.ROOT);

        if (!sku.matches("[A-Z0-9-]{1,64}")) {
            throw new TranslationFailure("SKU_INVALID");
        }
        return sku;
    }

    private static String canonicalCurrency(String raw) {
        String currency = required(
            raw, "CURRENCY_MISSING")
            .strip().toUpperCase(Locale.ROOT);

        if (!"USD".equals(currency)) {
            // Demo chỉ hỗ trợ USD có 2 minor units.
            throw new TranslationFailure(
                "UNSUPPORTED_CURRENCY");
        }
        return currency;
    }

    private static int parseQuantity(String raw) {
        try {
            int quantity = Integer.parseInt(
                required(raw, "QUANTITY_MISSING").strip());
            if (quantity < 1 || quantity > 500) {
                throw new TranslationFailure(
                    "QUANTITY_OUT_OF_RANGE");
            }
            return quantity;
        } catch (NumberFormatException ex) {
            throw new TranslationFailure(
                "QUANTITY_NOT_INTEGER", ex);
        }
    }

    private static long parseMinorPrice(
            String raw, String currency) {
        if (!"USD".equals(currency)) {
            throw new TranslationFailure(
                "UNSUPPORTED_CURRENCY");
        }
        try {
            long minor = new BigDecimal(
                required(raw, "PRICE_MISSING").strip())
                .movePointRight(2)
                .longValueExact();

            if (minor < 0 || minor > 1_000_000_000L) {
                throw new TranslationFailure(
                    "PRICE_OUT_OF_RANGE");
            }
            return minor;
        } catch (NumberFormatException | ArithmeticException ex) {
            throw new TranslationFailure(
                "NON_EXACT_PRICE", ex);
        }
    }

    private static Instant parseRequestedAt(String raw) {
        try {
            return OffsetDateTime.parse(
                required(raw, "REQUESTED_AT_MISSING").strip())
                .toInstant();
        } catch (DateTimeException ex) {
            throw new TranslationFailure(
                "INVALID_REQUESTED_AT", ex);
        }
    }
}
~~~

### 9.1. Translator đã làm gì?

1. Đọc payload và những headers **được adapter tin cậy cấp**.
2. Từ chối schema/partner không hỗ trợ.
3. Chuyển quantity, money và timestamp bằng kiểu chính xác.
4. Tạo `WarehouseCommand` chứa business operation ID ổn định.
5. Tạo message mới với **allowlist metadata**: correlation, operation, source, versions, tenant.
6. Chỉ giữ `replyChannel`/`errorChannel` nếu chúng là đối tượng `MessageChannel` nội bộ hợp lệ.
7. Không chuyển `authorization`, `cookie`, raw JSON hoặc delivery counters vào message mới.

**Giới hạn của ví dụ:** `required(...)` kiểm string không rỗng, chưa giới hạn độ dài của mọi ID; ingress/schema validator production phải áp length, charset và authorization theo contract. `canonicalSku` uppercase chỉ đúng nếu **SKU nguồn không phân biệt case**. `unitPriceMinor` giới hạn 1 tỷ và USD là lựa chọn minh họa.

### 9.2. Không tạo lại `operationId` trong Translator

Nếu trong `translate(...)` gọi `UUID.randomUUID()` để sinh command ID mới, mỗi broker redelivery có thể tạo **business operation mới** và vượt lớp idempotency downstream.

~~~text
Lần giao #1:
  operationId=CMD-901 -> ReserveStock once

Redelivery:
  operationId=CMD-901 -> return existing outcome

Không được:
  redelivery -> operationId=random-new -> ReserveStock again
~~~

ID cần do producer/nguồn nghiệp vụ phát hành **một lần**, hoặc bởi ingress tin cậy và được lưu bền trước khi retry có thể diễn ra. `MessageHeaders.ID` không phải lựa chọn thay thế ổn định.

### 9.3. Có nên giữ `replyChannel` và `errorChannel` không?

Trong **cùng JVM**, một Gateway chờ reply có thể cần `replyChannel` và error routing còn hiệu lực. Ví dụ code chỉ giữ trường hợp là `MessageChannel` object do ứng dụng nội bộ cấp.

Tại **outbound broker/HTTP boundary**, không được serialize object `MessageChannel`. Cần chuyển sang **reply destination/correlation theo transport contract**, hoặc dùng outbound header mapper bỏ các headers đó. Nếu client có thể tự khai tên channel hoặc routing header, không được giữ mà không kiểm tra allowlist và quyền.

### 9.4. Tại sao không gọi `copyHeaders(...)` cho mọi input?

Nếu làm:

~~~java
// KHÔNG NÊN ở trust boundary:
Message<WarehouseCommand> unsafe = MessageBuilder
    .withPayload(command)
    .copyHeaders(inbound.getHeaders())
    .build();
~~~

Bạn có thể mang theo `Authorization`, `Cookie`, `rawPayload`, MIME gốc không còn đúng, một header tenant giả, hoặc delivery metadata không thuộc consumer đích.

**Lưu ý vận hành:** Ngoài mã Translator, một số endpoint/adapter có thể tự propagate headers theo cơ chế framework. Vì vậy **header policy ở outbound adapter/mapper và contract tests trên message thật** vẫn cần thiết. Việc tạo Message với allowlist **không phải bằng chứng duy nhất** rằng mọi boundary đã loại sạch headers cấm.

## 10. Spring Integration Java DSL cho Translator

Có hai cách dùng Spring Integration thường gặp:

- `.transform(...)` nếu logic chuyển đổi **payload** là chủ yếu.
- `.handle(service, "method")` với method nhận/trả `Message<?>` để mô tả rõ hợp đồng cả payload và headers, như bài này.

### 10.1. Flow minh họa một chiều

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class MessageTranslatorFlowConfiguration {

    @Bean("translator.partner.in")
    DirectChannel inbound() {
        return new DirectChannel();
    }

    @Bean("translator.warehouse.out")
    QueueChannel outbound() {
        // Điểm quan sát cho integration tests,
        // production có thể thay bằng broker adapter.
        return new QueueChannel();
    }

    @Bean
    PartnerOrderTranslator partnerOrderTranslator() {
        return new PartnerOrderTranslator();
    }

    @Bean
    IntegrationFlow mapPartnerOrder(
            PartnerOrderTranslator translator) {
        return IntegrationFlow
            .from("translator.partner.in")
            .handle(translator, "translate")
            // Bổ sung lớp lọc cho một số headers cấm tại
            // flow boundary; external adapter vẫn cần allowlist.
            .headerFilter(
                "authorization", "cookie", "rawPayload")
            .channel("translator.warehouse.out")
            .get();
    }
}
~~~

Trong ví dụ, `DirectChannel` thực hiện dispatch đồng bộ và `QueueChannel` là queue **trong bộ nhớ** để test. Nó không cung cấp durability, ACK hoặc transaction qua broker thực. Khi chuyển sang Kafka/JMS/AMQP, phải kiểm tra adapter serialization, header mapper, offset/ACK và retry policy tương ứng.

### 10.2. Biến thể khi chỉ cần đổi payload

Nếu cả payload và headers của input đều thuộc **cùng trusted domain**, có thể chỉ chuyển payload bằng Transformer:

~~~java
IntegrationFlow payloadOnly(
        java.util.function.Function<PartnerOrder, WarehouseCommand> mapper) {
    return IntegrationFlow.from("partner.payload.in")
        .transform(PartnerOrder.class, mapper::apply)
        .channel("warehouse.commands.out")
        .get();
}
~~~

Đây là đoạn rút gọn, cần cung cấp mapper và channels khi tích hợp. **Đừng mặc định** payload-only Transformer tự áp chính sách drop/rename headers khi message đi qua trust boundary. Nếu đồng thời thay schema/metadata, phải có bước rõ cho headers và tests xác minh.

### 10.3. Lưu ý về content type

Nếu `PartnerOrder` được deserialize từ JSON, input có thể có `contentType=application/json`. Sau Translator, payload trong JVM là Java `WarehouseCommand`, **chưa nhất thiết là JSON bytes**. Outbound serializer sẽ quyết định media type/encoding của message được phát.

Cần tách:

~~~text
originalMediaType = application/vnd.partner.order+json
targetSchemaVersion = warehouse-command-v1

Transport serialization:
  WarehouseCommand -> JSON bytes
  outbound Content-Type = application/json
  encoding = UTF-8 (contract)
~~~

Không giữ mặc định MIME của nội dung gốc nếu output đã đổi biểu diễn. Đừng cố đặt `contentType=application/pdf` cho `Message<ClaimReference>` khi payload đã là DTO metadata.

## 11. Correlation và reply khi có Gateway

Trong request–reply, message qua Gateway thường phải giữ khả năng tìm đúng người nhận reply.

~~~mermaid
sequenceDiagram
    participant P as Partner Gateway
    participant T as Translator
    participant W as Warehouse endpoint
    P->>T: PartnerOrder + trusted correlation + reply route
    T->>W: WarehouseCommand + same business operation
    W-->>T: WarehouseReceipt + operationId
    T-->>P: PartnerOrderReply + correlation
~~~

Một response đi ngược về nguồn thường cần **Translator chiều về**:

| Warehouse response | Partner reply | Quy tắc |
| --- | --- | --- |
| `operationId` | `requestId` | Mapping theo hợp đồng đã xác thực |
| `reservationStatus` | `status` | Enum mapping rõ, không unknown→SUCCESS |
| `warehouseOrderId` | `fulfillmentReference` | Giữ danh tính |
| `businessCorrelationId` | `businessCorrelationId` | Liên kết request/reply |
| `internalErrorDetails` | Không gửi ra ngoài | Redact/mapping public error code |

Chỉ có translator của request **không tự động** chuyển response thành hợp đồng của đối tác. Nếu Gateway dùng external broker, cần reply queue/topic, correlation key ổn định, timeout và xử lý reply trễ.

### 11.1. ReplyChannel nội bộ khác reply address

- Trong cùng JVM, `replyChannel` có thể là `MessageChannel` object hoặc cấu hình Spring tương đương.
- Qua broker, reply address thường là **queue/topic hoặc một định danh transport** có quy tắc kiểm soát riêng.
- Một partner không được gửi tùy ý một reply destination khiến dữ liệu nội bộ bị gửi đến endpoint không có quyền.
- Nếu Translator bỏ `replyChannel` mà Gateway cần reply, caller có thể timeout dù business handler đã xử lý.

### 11.2. Một response success không được suy ra từ việc translate

Translate thành công chỉ nghĩa là **message đích đã được dựng**. Nó không chứng minh warehouse đã nhận, commit hoặc trả kết quả. Với request xử lý bất đồng bộ, có thể cần `ACCEPTED/PROCESSING/COMPLETED` theo contract, không trả “đặt hàng hoàn tất” ngay sau khi tạo `WarehouseCommand`.

## 12. Metadata qua Splitter, Aggregator và Scatter-Gather

Giả sử một đơn có ba dòng:

~~~text
executionId = RUN-901-A
businessCorrelationId = ORD-901

LINE-1 -> warehouse command -> reply
LINE-2 -> warehouse command -> reply
LINE-3 -> warehouse command -> reply
~~~

Translator cho từng child cần giữ đủ thông tin:

- `executionId` để gom theo **đợt xử lý**.
- `lineId` để xác định một **child duy nhất**.
- `operationId` hoặc `(commandId,lineId,operationType)` để bảo vệ side effect.
- `sequenceNumber/sequenceSize` nếu flow sử dụng các header này cho group semantics.
- `businessCorrelationId` để truy vết đơn gốc.

**Không** thay tất cả `correlationId` bằng một `orderId` nếu một order có thể có hai executions đồng thời. Cũng không lấy sequence number của transport làm ID nghiệp vụ.

### 12.1. Không bỏ một child khiến Aggregator treo

Nếu một child `quantity=-3` bị Translator reject và bị Filter drop im lặng, Aggregator đợi đủ ba replies sẽ chỉ nhận hai. Nên tạo **typed child outcome** `REJECTED` đi vào kết quả batch, hoặc thiết kế release/timeout/partial policy rõ.

### 12.2. Duplicate không tính thành child mới

Redelivery có thể tạo hai `WarehouseReceipt` cho LINE-2. Group release phải dựa trên **unique child IDs/expected set**, không phải chỉ `group.size()`. Nếu group đã complete và reply lặp đến sau, cần closed-execution state/tombstone để không tạo group mới rồi phát kết quả cuối thứ hai.

### 12.3. Correlation không thay idempotency

Hai message có cùng correlation chỉ thể hiện liên hệ. Backend vẫn phải dùng operation ID bền vững và transaction/idempotency khi ghi giữ kho, thanh toán hoặc hóa đơn. Một Transformer bảo toàn correlation nhưng tạo lại operation ID ở mỗi retry vẫn có thể gây double charge.

## 13. Unit test: payload đúng và metadata không rơi

Translator phải được kiểm tra hai chiều:

1. Những field/headers **phải tồn tại** ở output.
2. Những field/headers **không được phép tồn tại** ở output.

Chỉ assert `quantity=3` sẽ không phát hiện lỗi mất `operationId` hoặc lộ `authorization` khi phát message.

### 13.1. Fixture chứa cả metadata hợp lệ và dữ liệu cần loại

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TranslationFixture {
    private TranslationFixture() {}

    static Message<PartnerOrder> validMessage() {
        PartnerOrder body = new PartnerOrder(
            "PO-901",
            " book-42 ",
            "003",
            "12.50",
            "usd",
            "2026-11-21T15:00:00+07:00",
            "Giao giờ hành chính");

        return MessageBuilder.withPayload(body)
            .setHeader("trustedTenant", "shop-a")
            .setHeader("trustedPartner", "partner-a")
            .setHeader(
                "sourceSchemaVersion", "partner-order-v1")
            .setHeader("businessCorrelationId", "ORD-901")
            .setHeader("operationId", "CMD-901")
            .setHeader(
                "originalMediaType",
                "application/vnd.partner.order+json")
            // Mô phỏng một header không được truyền ra ngoài.
            .setHeader("authorization", "Bearer demo-secret")
            .setHeader("rawPayload", "private-demo-data")
            .build();
    }
}
~~~

Fixture đặt `trustedTenant` trực tiếp **chỉ cho unit test**; điều này không thay thế authentication ở inbound adapter thực.

### 13.2. JUnit 5: kiểm business payload và headers quan trọng

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PartnerOrderTranslatorTest {

    private final PartnerOrderTranslator translator =
        new PartnerOrderTranslator();

    @Test
    void mapsPayloadAndMandatoryMetadata() {
        Message<WarehouseCommand> out =
            translator.translate(
                TranslationFixture.validMessage());

        WarehouseCommand command = out.getPayload();

        assertEquals("shop-a", command.tenantId());
        assertEquals("partner-a", command.partnerId());
        assertEquals("PO-901", command.partnerOrderNo());
        assertEquals("CMD-901", command.operationId());
        assertEquals("BOOK-42", command.sku());
        assertEquals(3, command.quantity());
        assertEquals(1250L, command.unitPriceMinor());
        assertEquals("USD", command.currency());
        assertEquals(
            Instant.parse("2026-11-21T08:00:00Z"),
            command.requestedAt());

        assertEquals("ORD-901",
            out.getHeaders().get("businessCorrelationId"));
        assertEquals("CMD-901",
            out.getHeaders().get("operationId"));
        assertEquals("warehouse-command-v1",
            out.getHeaders().get("targetSchemaVersion"));
        assertEquals("partner-order-v1",
            out.getHeaders().get("sourceSchemaVersion"));
    }

    @Test
    void doesNotCopySensitiveOrUnmappedHeaders() {
        Message<WarehouseCommand> out =
            translator.translate(
                TranslationFixture.validMessage());

        assertNull(out.getHeaders().get("authorization"));
        assertNull(out.getHeaders().get("cookie"));
        assertNull(out.getHeaders().get("rawPayload"));
        assertNull(out.getHeaders().get("trustedTenant"));
        assertEquals("shop-a", out.getPayload().tenantId());
    }

    @Test
    void refusesMissingOperationIdInsteadOfRegenerating() {
        Message<PartnerOrder> missing = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .removeHeader("operationId")
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(missing));

        assertEquals("OPERATION_ID_MISSING", error.code());
    }

    @Test
    void refusesFractionalCentWithoutRoundingPolicy() {
        PartnerOrder old =
            TranslationFixture.validMessage().getPayload();

        PartnerOrder bad = new PartnerOrder(
            old.partnerOrderNo(), old.sku(),
            old.quantityText(), "12.345",
            old.currency(), old.requestedAt(),
            old.deliveryNote());

        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setPayload(bad)
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("NON_EXACT_PRICE", error.code());
    }

    @Test
    void refusesUnsupportedSchemaVersion() {
        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setHeader(
                "sourceSchemaVersion", "partner-order-v99")
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("UNSUPPORTED_SOURCE_SCHEMA", error.code());
    }

    @Test
    void refusesTimestampWithoutOffset() {
        PartnerOrder old =
            TranslationFixture.validMessage().getPayload();

        PartnerOrder bad = new PartnerOrder(
            old.partnerOrderNo(), old.sku(),
            old.quantityText(), old.unitPriceMajor(),
            old.currency(),
            "2026-11-21T15:00:00",
            old.deliveryNote());

        Message<PartnerOrder> input = MessageBuilder
            .fromMessage(TranslationFixture.validMessage())
            .setPayload(bad)
            .build();

        TranslationFailure error = assertThrows(
            TranslationFailure.class,
            () -> translator.translate(input));

        assertEquals("INVALID_REQUESTED_AT", error.code());
    }
}
~~~

### 13.3. Header và payload không được tự mâu thuẫn

Nếu một source contract chứa operation ID trong **cả** payload và header:

~~~text
payload.operationId = CMD-901
header.operationId  = CMD-902
~~~

Không âm thầm chọn một bên. Quy tắc là xác định **một nguồn sự thật đã xác thực** ở ingress, so các bản sao theo contract và từ chối `OPERATION_ID_CONFLICT` nếu khác nhau. Không tạo ID mới trong retry để “sửa”.

Ví dụ `PartnerOrder` của bài không mang operation ID; adapter tin cậy phát hành hoặc khôi phục `operationId` từ command registry, rồi Translator điền vào `WarehouseCommand`.

## 14. Integration test: cả channel và header policy

Dùng `MessageTranslatorFlowConfiguration` từ phần 10. Test quan sát handler Translator, Header Filter và output channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MessageTranslatorFlowConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class MessageTranslatorFlowTest {

    @Autowired @Qualifier("translator.partner.in")
    MessageChannel input;

    @Autowired @Qualifier("translator.warehouse.out")
    PollableChannel output;

    @Test
    void emitsTargetCommandWithValidAndSafeHeaders() {
        assertTrue(input.send(
            TranslationFixture.validMessage()));

        Message<?> translated = output.receive(1000);
        assertNotNull(translated);
        assertInstanceOf(
            WarehouseCommand.class,
            translated.getPayload());

        WarehouseCommand command =
            (WarehouseCommand) translated.getPayload();

        assertEquals(3, command.quantity());
        assertEquals(1250L, command.unitPriceMinor());
        assertEquals("CMD-901", command.operationId());
        assertEquals("ORD-901",
            translated.getHeaders().get(
                "businessCorrelationId"));

        assertNull(
            translated.getHeaders().get("authorization"));
        assertNull(
            translated.getHeaders().get("rawPayload"));
        assertNull(output.receive(0),
            "One input must yield one target message");
    }
}
~~~

**Giới hạn:** đây là integration test **trong một JVM**, không có HTTP authentication, external warehouse, JMS/Kafka/AMQP provider hay outbox. Với executor/broker bất đồng bộ, `receive(0)` không đủ chứng minh “không bao giờ phát”; cần bounded await và kiểm các business side effects.

### 14.1. Contract tests cần bổ sung

- Gateway request–reply giữ đúng local reply route và timeout semantics.
- HTTP ingress loại header giả mạo tenant/source/correlation trước Translator.
- Broker adapter chỉ phát **allowed headers** sau serialization.
- Kafka/JMS/AMQP round-trip giữ đúng kiểu `operationId` và `businessCorrelationId`.
- Redelivery tạo envelope khác nhưng operation ID và nghiệp vụ không đổi.
- Missing required metadata không sinh `WarehouseCommand` giả.
- Unknown schema hoặc unsupported currency được route error/quarantine rõ.
- Trace không tạo metric labels cardinality cao.
- Hai tenants có cùng `partnerOrderNo` không bị kết hợp thành một operation.
- Nguồn có field bí mật/PII không bị phản chiếu vào outbound headers.

## 15. Mapping metadata qua HTTP, AMQP, JMS và Kafka

Không có một hệ quy chiếu header chung dùng nguyên xi cho tất cả transport. Mỗi adapter có giới hạn kích thước, encoding, các trường provider quản lý và quy tắc tương tác khác nhau.

| Boundary | Rủi ro | Phải xác minh |
| --- | --- | --- |
| HTTP inbound | Client mạo danh tenant/operation bằng custom header | Principal, chữ ký, allowlist |
| HTTP outbound | Vô tình forward token/cookie | Chỉ header hợp đồng được phát |
| AMQP | Reply-to, correlation, retry/DLX headers có semantics riêng | Header mapper và redelivery |
| JMS | `JMSCorrelationID`, `JMSReplyTo`, provider headers | Request–reply, type serialization |
| Kafka | Record key, partition/offset và typed headers | Correlation qua retry topic/rebalance |
| Internal channel | `replyChannel` là Java object/bean name | Không serialize object ra ngoài |
| CloudEvents | `id/source/type/subject` là event envelope | Không nhầm event ID với business command |

### 15.1. Kafka key khác business operation ID

~~~text
Kafka record key:       tenantId + orderId (partitioning)
Business operation ID:  CMD-901 (idempotency)
Business correlation:   ORD-901
Kafka offset:           vị trí record/delivery
~~~

Record có thể được republish sang offset/topic mới; nếu dedup theo offset, cùng business command sẽ bị coi thành một lệnh mới. Kafka transactions có phạm vi của chúng và **không tự rollback external Warehouse HTTP API**.

### 15.2. JMSCorrelationID khác MessageHeaders.ID

JMS `JMSCorrelationID` hỗ trợ tương quan theo giao thức JMS. Spring `MessageHeaders.ID` là ID envelope. Business operation ID có thể được ánh xạ vào JMS correlation theo contract **nếu nghiệp vụ chọn vậy**, nhưng không phải một phép đồng nhất tự nhiên.

### 15.3. Đừng chuyển Java object sang HTTP header

HTTP header thường là text; Spring message header có thể là `MessageChannel`, `UUID` hoặc một object ứng dụng. Outbound mapper phải chọn biểu diễn cố định, đặt giới hạn length, xử lý encoding và không phát object nội bộ/trạng thái bảo mật ngoài ý muốn.

### 15.4. Chính sách allowlist tại outbound adapter

~~~text
Allowed:
  operationId
  businessCorrelationId
  targetSchemaVersion
  sourceSystem (nếu cần)

Denied:
  authorization
  cookie
  rawPayload
  replyChannel (Java object)
  errorChannel (Java object)
  internalPrincipal
  debugException
  arbitrary headers not in contract
~~~

**Kiểm tra dữ liệu trên wire** trong contract tests, không chỉ `PartnerOrderTranslator.translate(...)`. Một số endpoint có thể propagate headers theo cấu hình framework.

## 16. Header propagation không có một quy tắc mặc định cho mọi endpoint

Spring Integration có Transformer, Service Activator, Header Enricher, Header Filter và các outbound adapters với cách tạo message/propagate headers khác nhau.

Không mặc định rằng:

- Mọi Transformer luôn giữ nguyên mọi header.
- Một Service Activator trả `Message<?>` là đủ để loại toàn bộ input headers.
- `MessageHeaders.ID` sẽ không đổi.
- Content type gốc vẫn mô tả payload sau transform.
- `replyChannel`/`errorChannel` có thể được serialize qua Kafka/JMS.
- Header mang tên `trustedTenant` chắc chắn đã được xác thực.

### 16.1. Phòng vệ theo các boundary

~~~mermaid
flowchart LR
    U["Untrusted input"] --> I["Ingress auth + strip/validate"]
    I --> T["Translator: payload + known metadata"]
    T --> A["Outbound adapter allowlist"]
    A --> B["Broker/remote service"]
    B --> R["Receiver: verify source + schema + auth"]
~~~

Đây không phải duplicate effort vô ích: một hệ thống có thể thêm header ở một endpoint trung gian về sau, nên adapter cuối vẫn phải là lớp chặn chắc chắn.

## 17. Retry/redelivery: Translator phải giữ ổn định business identity

Failure window tiêu biểu:

~~~text
PartnerOrder (operationId=CMD-901)
    -> Translator -> WarehouseCommand
    -> Warehouse commits reservation
    -> Network ACK lost
    -> Local retry or broker redelivery
    -> Translator runs again
    -> WarehouseCommand must still have operationId=CMD-901
~~~

Translator không nên sinh `UUID.randomUUID()`, gán lại `Instant.now()` cho event time, đổi giá bằng tỷ giá mới chưa pin version, hoặc tạo correlation group mới trong mỗi attempt.

### 17.1. Correlation không tự là idempotency

`businessCorrelationId=ORD-901` chỉ nối các bước của một đơn. Nếu cùng đơn có lệnh CREATE, CANCEL, AMEND, chúng không thể cùng dedup bằng một correlation ID. `operationId` phải đại diện **một mutation có ý nghĩa**.

Ngay cả khi Translator bảo toàn operation ID, **Warehouse** vẫn phải có idempotent receiver/unique DB key hoặc API idempotency token ở nơi commit, vì broker có thể giao lại.

### 17.2. Phân biệt lỗi terminal và lỗi kỹ thuật

| Lỗi | Có retry cùng input không? | Xử lý |
| --- | --- | --- |
| Quantity không parse | Không | Typed translation rejection |
| Price cần rounding không cho phép | Không | Domain/representation rejection |
| Source schema không hỗ trợ | Không cho đến khi nâng decoder | Quarantine |
| Thiếu trusted tenant/operation ID | Không bypass | Security/contract error |
| Outbound broker timeout | Có điều kiện | Retry giới hạn + stable IDs |
| Warehouse HTTP 503 | Có điều kiện | Backoff/idempotent backend |
| Warehouse commit rồi response mất | Reconcile/retry same operation key | Không phát command mới |
| Authorization denied | Không | Reject theo security policy |

Đừng bắt mọi exception rồi đổi thành `TranslationFailure("INVALID_ORDER")`. Lỗi kỹ thuật cần error channel hoặc retry; input sai terminal không nên được broker retry vô hạn.

## 18. Schema evolution và tái lập mapping khi DLQ replay

Ví dụ:

~~~text
Partner schema v1: unitPriceMajor="12.50"
Partner schema v2: priceMinor=1250
Warehouse v1:      unitPriceMinor=1250
~~~

Nếu message v2 bị đọc như v1, giá có thể tăng 100 lần. Cần `sourceSchemaVersion` xác định decoder/translator và `targetSchemaVersion` xác định output contract.

Một message bị DLQ 15 ngày trước có thể được replay sau khi rule mới thay đổi. Chọn rõ:

1. Pin mapping policy version cũ nếu cần tái lập kết quả.
2. Re-translate theo policy mới nếu được phép, có audit/migration.
3. Reconcile nếu business mutation cũ đã commit.
4. Giữ **cùng operation ID** với cùng business command.
5. Không xem thay đổi metadata transport là thay đổi business intent.

### 18.1. Khi conversion có loss được phép

Không phải lúc nào cũng cần byte-perfect equality. Nhưng việc bỏ field, giảm timestamp precision, làm tròn số hoặc ẩn thông tin phải có **loss policy**. Có thể trả warning, reject, nâng schema hoặc giữ raw/provenance có bảo mật (Claim Check). Nếu chữ ký gốc áp trên bytes, canonical JSON reserialized không thay được raw bytes.

## 19. Observability cho payload và metadata contract

| Signal/metric | Mục tiêu |
| --- | --- |
| `translator_received_total` theo source/schema | Traffic và version skew |
| `translator_success_total` theo target version | Theo dõi mapping |
| `translation_rejected_total` theo code | Schema drift/invalid values |
| `header_contract_missing_total` | Mất operation/correlation metadata |
| `header_contract_conflict_total` | Header và payload mâu thuẫn |
| `outbound_header_filtered_total` | Thấy nỗ lực phát metadata cấm |
| `translation_latency` | Chi phí transform |
| `reply_timeout_total` | Phát hiện lỗi reply route |
| `downstream_retry_total` | Retry kỹ thuật |
| `idempotency_hit_total` | Duplicate business commands |
| `quarantine_oldest_age` | Lỗi cần review |

Không dùng `orderId`, `operationId`, `tenantId`, `businessCorrelationId` làm tag metrics tự do (cardinality cao). Chúng chỉ nên xuất hiện trong log/trace có phân quyền và chính sách masking/retention.

### 19.1. Log metadata nhưng không log secrets

~~~json
{
  "event": "message_translated",
  "source": "partner-a",
  "sourceSchemaVersion": "partner-order-v1",
  "targetSchemaVersion": "warehouse-command-v1",
  "headerContract": "PASS",
  "payloadMapping": "PASS",
  "result": "ACCEPTED"
}
~~~

Đây là **schema log minh họa**, không phải log có sẵn của Spring Integration. Không log raw JSON, access tokens, cookies, pre-signed URL hoặc thông tin cá nhân không cần thiết.

## 20. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ map payload, bỏ qua business headers | Mất correlation và idempotency | Metadata contract đi cùng payload contract |
| Copy toàn bộ headers để “an toàn” | Rò token, PII, Java internal routing | Allowlist/strip ở ingress và outbound |
| Dùng `MessageHeaders.ID` làm operation ID | Retry tạo business effect mới | Stable business operation identity |
| Dùng `businessCorrelationId` cho mọi idempotency | Các thao tác mới cùng đơn bị chặn | Tách correlation/group/operation IDs |
| Sinh `operationId` mới mỗi lần translate | Redelivery thành lệnh mới | Khôi phục ID bền của command |
| Đọc header `trustedTenant` từ HTTP client | Cross-tenant routing/IDOR | Trust boundary xác thực và cấp context |
| Giữ `application/json` từ raw trong khi payload chưa serialize | Consumer hiểu sai representation | Recompute media type ở adapter |
| Serialize `replyChannel` qua Kafka/JMS | Lỗi kiểu hoặc lộ topology nội bộ | Transport reply address + correlation |
| Map `JMSMessageID`/Kafka offset thành business key | Replay tạo key khác | Operation ID từ contract |
| Default unknown currency thành USD | Sai đơn vị và số tiền | Reject unknown/unsupported |
| Dùng `double` để chuyển major→minor | Precision/rounding không kiểm soát | BigDecimal exact + scale policy |
| Đổi `requestedAt` thành `Instant.now()` | Replay làm thay đổi thời gian nghiệp vụ | Parse time nguồn có offset |
| Uppercase mọi ID | Gộp định danh case-sensitive | Normalize từng field theo contract |
| Header và payload xung đột vẫn xử lý | Có thể mạo danh/ghi sai | Validate consistency và reject |
| Parse error bị catch thành technical retry | Retry storm cùng dữ liệu lỗi | Typed terminal rejection |
| HTTP timeout được xem là chưa commit | Có thể tạo side effect lần hai | Idempotency tại đích/reconciliation |
| Không test nhánh không được phép phát | Message lỗi có thể lọt vào handler | Negative test/zero side effects |
| Filter drop child trước Aggregator | Group không đủ replies | Typed rejected child outcome |
| Test trong một JVM rồi coi như broker contract | Header mapper/codec có thể khác | Round-trip tests qua transport thật |
| Log nguyên metadata nguồn | Lộ secret và tăng cardinality | Structured safe logs + masking |
| Replay với mapping policy mới không ghi version | Cùng lệnh cho output khác | Pin/migration/reconciliation |

## 21. Checklist trước khi đưa Message Translator vào production

- [ ] Có bảng mapping cho **payload fields** và một bảng riêng cho **metadata/headers**.
- [ ] Mỗi field có source, target, type, unit, validation và error policy.
- [ ] Phân biệt business metadata, integration-control và transport metadata.
- [ ] Ingress đã xác thực tenant/partner và loại headers giả mạo.
- [ ] Translator không sinh operation ID mới khi retry cùng command.
- [ ] Business correlation ID, operation ID và execution ID có phạm vi rõ.
- [ ] Target command không được dùng `MessageHeaders.ID`/Kafka offset làm key nghiệp vụ.
- [ ] Numeric conversion exact theo currency/scale, không dùng `double` tùy tiện.
- [ ] Timestamps có offset/epoch unit rõ; không thay origin event time bằng giờ xử lý.
- [ ] Unknown enums/source versions có rejection hoặc migration policy minh bạch.
- [ ] Có handling cho required, optional, null và conflicting fields theo contract.
- [ ] Outbound adapter có header allowlist và content-type/serializer đúng.
- [ ] Header nhạy cảm, raw payload và Java channel objects không rò qua external boundary.
- [ ] Gateway reply/error routing hoạt động sau translation và sau transport mapping.
- [ ] Splitter/Aggregator giữ execution/child identity, không đếm duplicate thành phần mới.
- [ ] Mapping errors không bị retry như technical failures; technical errors không bị coi là invalid input.
- [ ] Downstream side effect được bảo vệ bởi idempotent receiver/transaction phù hợp.
- [ ] Có unit tests assert cả required headers **và** forbidden headers.
- [ ] Có integration/contract tests trên broker/HTTP thực cho schema/header round-trip.
- [ ] DLQ replay có source/target schema version và mapping policy rõ.
- [ ] Có observability cho header conflicts, missing metadata, mapping failures và reply timeouts.
- [ ] Logs, metrics và tracing không lộ token/PII hoặc tạo metric labels cardinality cao.

## 22. Bài tập thực hành

Một hệ thống chăm sóc khách hàng nhận yêu cầu vận chuyển qua hai kênh:

**Đối tác A** gửi message:

~~~json
{
  "shipmentNo": "SHP-901",
  "weightKg": "2.500",
  "declaredValue": "120.50",
  "currency": "USD",
  "createdAt": "2026-11-21T15:00:00+07:00",
  "serviceCode": "EXPRESS"
}
~~~

Metadata đã xác thực ở ingress:

~~~text
trustedTenant         = tenant-a
trustedPartner        = carrier-a
businessCorrelationId = CASE-901
operationId           = SHIP-CREATE-901
sourceSchemaVersion   = carrier-shipment-v1
~~~

**Warehouse/shipping system** muốn nhận:

~~~json
{
  "tenantId": "tenant-a",
  "carrierId": "carrier-a",
  "shipmentNo": "SHP-901",
  "weightGrams": 2500,
  "declaredValueMinor": 12050,
  "currency": "USD",
  "createdAt": "2026-11-21T08:00:00Z",
  "serviceTier": "EXPRESS",
  "operationId": "SHIP-CREATE-901"
}
~~~

Hệ thống đồng thời yêu cầu reply `ShipmentCreated` về Gateway theo `CASE-901`. Đối tác A còn gửi thêm các headers `Authorization`, `X-Caller-IP` và `X-Debug-Payload` mà shipping system **không được nhận**.

**Yêu cầu:**

1. Viết mapping matrix cho payload từ kg sang gram, major currency sang minor units và ISO offset sang Instant.
2. Viết metadata mapping contract: field nào preserve, rename, derive, drop, recompute.
3. Giải thích vì sao `businessCorrelationId` và `operationId` không nên dùng thay nhau.
4. Định nghĩa `CarrierShipmentV1`, `ShippingCommandV1` và `TranslationFailure` bằng Java records/classes.
5. Viết Translator nhận `Message<CarrierShipmentV1>` và trả `Message<ShippingCommandV1>`, có explicit header allowlist.
6. Thêm Spring Integration flow gồm inbound, Translator, Header Filter và outbound channel; mô tả cách dùng `.transform(...)` nếu chỉ đổi payload.
7. Thiết kế reply Translator từ `ShipmentCreated` về response đối tác, giữ correlation và không lộ nội bộ.
8. Khi Gateway là request–reply qua JMS, phân biệt `JMSCorrelationID/JMSReplyTo` với `replyChannel` object trong JVM.
9. Kiểm thử `weightKg="2.501"` với yêu cầu gram exact, `declaredValue="120.505"` và unsupported currency; không silently round.
10. Kiểm thử thiếu `operationId`, sai `sourceSchemaVersion`, xung đột tenant giữa payload và identity.
11. Viết JUnit test assert output **không** còn Authorization, raw debug payload hoặc tên Java channel bên ngoài.
12. Viết integration test Kafka/AMQP/JMS (chọn một) để kiểm content-type, schema version, operation ID và correlation qua serialization.
13. Giả lập shipping API commit thành công nhưng ACK mất; redelivery phải giữ operation ID để backend không tạo shipment thứ hai.
14. Với batch nhiều kiện hàng, xử lý một child rejected sao cho Aggregator trả kết quả rõ, không treo.
15. Đề xuất metrics về missing headers, contract conflicts, translation failures, retries và reply timeouts.

**Gợi ý:** Translator không chỉ trả một DTO nhìn đúng. Nó phải trả **message có contract tổng thể đúng**: payload hợp lệ, header cần thiết còn nguyên ý nghĩa, metadata nguy hiểm bị chặn và danh tính thao tác đủ bền để retry an toàn.

## 23. Tổng kết

**Mapping payload và metadata** là trọng tâm của Message Translator khi kết nối các hệ thống có schema và semantics riêng. Đổi field, đơn vị, ngày giờ hoặc enum chỉ là một phần; message còn mang **business identity, correlation, version, reply/error routing, security context và transport metadata**. Giữ thiếu một header quan trọng có thể làm thất lạc reply hoặc retry sai; giữ thừa một header nhạy cảm có thể làm rò dữ liệu và phá trust boundary.

Trong Spring Integration, hãy thiết kế **mapping contract tường minh**, tạo message mới với metadata được chọn/kiểm tra, dùng Transformer hoặc Service Activator phù hợp, rồi áp **header filter/allowlist ở outbound adapter**. Phân biệt việc dịch message thành công với việc business handler đã commit, kiểm thử payload **và** metadata qua các transport, giữ operation ID ổn định qua retry/redelivery và xử lý đúng Splitter/Aggregator, Gateway, error channel, schema evolution và authorization. Mục tiêu là một message đích **đúng nghĩa nghiệp vụ, an toàn, có thể truy vết và không làm sai side effect**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Translator, Message Router, Correlation Identifier, Request-Reply, Idempotent Receiver); Spring Integration Reference về Message Transformation, Header Enricher/Header Filter, Java DSL, Service Activators, Gateways, Routers, Message Channels, Error Handling và Testing; Spring Messaging API về `Message`, `MessageHeaders` và `MessageBuilder`; Java SE về `BigDecimal`, `OffsetDateTime`, `Instant` và `Locale.ROOT`.







