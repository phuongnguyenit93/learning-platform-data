# Phiên bản hợp đồng và tương thích khi thêm hoặc bỏ trường

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp hệ thống qua HTTP client, cơ sở dữ liệu, cache, message broker và các adapter của Spring Integration. Một service có thể nhận HTTP JSON, gọi REST/SOAP của đối tác, lưu PostgreSQL, đẩy event qua Kafka/RabbitMQ và cache kết quả trong Redis. Khi một ứng dụng thay đổi hợp đồng dữ liệu, **các bên không thể nâng cấp cùng một thời điểm**: một pod vẫn chạy bản cũ, một consumer đang đọc event tồn từ tuần trước, một partner chưa cập nhật SDK, một bản ghi outbox chưa phát hoặc một DLQ chờ replay.

Tình huống: phiên bản đầu của sự kiện `OrderConfirmed` chỉ chứa `orderId`, `amount`; phiên bản sau thêm `currency` và bỏ `customerName`. Tác giả producer có thể cho rằng chỉ cần đổi Java record rồi deploy. Nhưng khi consumer cũ từ chối field chưa biết, consumer mới mặc định `currency="USD"` trong khi dữ liệu cũ thực ra là VND, hoặc event cũ trong DLQ bị replay, tích hợp có thể thất bại hoặc **xử lý sai nghiệp vụ** dù JSON vẫn parse được.

Bài thuộc chương **Hợp đồng dữ liệu**, đề mục **Phiên bản hợp đồng và tương thích khi thêm hoặc bỏ trường**. Trọng tâm là đánh giá tương thích từ **góc nhìn reader/writer cụ thể**, định nghĩa semantics cho absent/null/default, phát triển request/response/event và XML/Avro/Protobuf, lập kế hoạch triển khai nhiều phiên bản, kiểm thử hợp đồng và xử lý rủi ro khi thay đổi.

### Sau bài học, bạn có thể

1. Phân biệt schema, semantic contract, version, producer/writer và consumer/reader.
2. Giải thích **backward, forward, full compatibility**, kể cả dạng transitive và quy ước tên có thể khác theo hệ thống.
3. Phân tích tác động khi thêm, bỏ, đổi tên, đổi kiểu, thêm enum value hoặc thay đổi required/null/default.
4. Viết Java DTO/Jackson hợp đồng rõ ràng, không phụ thuộc ngầm vào việc mọi client đều bỏ qua unknown fields.
5. Lập lộ trình **expand → migrate → contract** để xóa trường mà không phá consumer cũ.
6. Chọn policy cho REST/OpenAPI, SOAP/XML/XSD, Kafka/RabbitMQ và Schema Registry.
7. Tách schema version khỏi event identity, business version và API deployment version.
8. Kiểm thử đồng thời producer cũ–mới, consumer cũ–mới, dữ liệu tồn trong broker/DLQ, database và cache.
9. Phát hiện lỗi không tương thích trước deploy, có telemetry cho giai đoạn deprecation và phương án rollback.
10. Áp dụng vào một luồng Spring Boot thực tế có outbox, idempotency và retry.

> **Nguyên tắc:** Một thay đổi chỉ được gọi là *tương thích* khi **bên đọc đang thực sự chạy** có thể đọc **dữ liệu của bên ghi đang thực sự chạy** và vẫn giữ **đúng ý nghĩa nghiệp vụ**. “JSON vẫn hợp lệ” chưa đủ.

## 1. Hợp đồng dữ liệu bao gồm những gì?

Hợp đồng không chỉ là danh sách field và kiểu dữ liệu. Nó gồm nhiều lớp:

| Thành phần | Ví dụ | Rủi ro khi thay đổi |
| --- | --- | --- |
| Tên và cấu trúc field | `orderId`, `customer.id` | Reader không tìm thấy đường dẫn |
| Kiểu dữ liệu | string → number, int32 → int64 | Parse lỗi, tràn số, mất độ chính xác |
| Required/optional/nullability | `currency` bắt buộc | Historical payload không có field |
| Default | Không có `currency` → "VND" | Ngầm định sai cho đơn hàng quốc tế |
| Enum và unknown values | `PENDING`, `CONFIRMED` | Exhaustive switch lỗi |
| Giá trị, đơn vị, định dạng | amount minor units, ISO-4217 | Tính tiền sai |
| Business invariants | `quantity > 0`, status transition | Chấp nhận dữ liệu trái nghiệp vụ |
| Identity và correlation | `eventId`, `operationId` | Retry sinh tác động trùng |
| Thứ tự/nhân quả | `aggregateVersion` | Event cũ ghi đè state mới |
| Error semantics | HTTP 409, field-level error | Client retry sai |
| Transport/envelope | Content-Type, headers, topic/routing key | Message bị route/deserialize sai |
| Retention và replay | 30 ngày topic, DLQ 90 ngày | Reader mới phải đọc dữ liệu rất cũ |
| Security/privacy | PII/secret/classifier | Log hoặc expose field không nên |

Hai payload có cùng schema nhưng một bên đổi đơn vị `amount` từ đồng sang xu có thể **không tương thích về ý nghĩa**, thậm chí nguy hiểm hơn lỗi parse rõ ràng.

### 1.1. Đừng nhầm bốn loại phiên bản

~~~mermaid
flowchart TD
    A["SPRING_BOOT_INTEGRATION deployment"] --> B["Application version: 2.7.0"]
    A --> C["HTTP API contract version: v2"]
    A --> D["Event schemaVersion: 3"]
    A --> E["Aggregate business version: 42"]
    A --> F["Database migration: V18"]
~~~

- **Application version**: phiên bản release/build của code.
- **API contract version**: contract công khai của endpoint/method hoặc media type.
- **Event schema version**: cách diễn giải serialized event.
- **Aggregate version**: thứ tự thay đổi của một đơn hàng, phục vụ optimistic locking/out-of-order protection.
- **Database migration version**: thứ tự DDL/data migration.

Không dùng `aggregateVersion=42` để quyết định parse payload theo schema v42; không đồng nhất tên image tag với API major version.

### 1.2. Writer và reader là ai?

Trong một message:

~~~text
Producer/Writer: Order Service → serialize JSON event
Consumer/Reader: Inventory Service → deserialize JSON event
~~~

Trong một HTTP exchange có **hai hướng**:

~~~text
HTTP request:  Caller writer → Server reader
HTTP response: Server writer → Caller reader
~~~

Một thay đổi server “đọc được request cũ” có thể an toàn cho request nhưng “response mới thêm field” lại phá caller cũ nếu caller strict. Vì vậy phải đánh giá **từng chiều**.

## 2. Backward, forward và full compatibility

### 2.1. Định nghĩa chính xác theo reader/writer

Dùng ký hiệu:

- `W1`: writer sản xuất payload theo schema v1.
- `W2`: writer sản xuất payload theo schema v2.
- `R1`: reader hiểu schema v1.
- `R2`: reader hiểu schema v2.

Một quy ước phổ biến (như Schema Registry trong các hệ sinh thái streaming):

- **Backward compatibility:** `R2` đọc được dữ liệu cũ từ `W1`.
- **Forward compatibility:** `R1` đọc được dữ liệu mới từ `W2`.
- **Full compatibility:** cả hai chiều trên đều đúng.

~~~mermaid
flowchart LR
    W1["Writer v1"] -->|"BACKWARD"| R2["Reader v2"]
    W2["Writer v2"] -->|"FORWARD"| R1["Reader v1"]
    W1 -. "FULL" .-> R2
    W2 -. "FULL" .-> R1
~~~

**Lưu ý về thuật ngữ:** Một số đội/API sử dụng “backward compatible” theo nghĩa tổng quát “client cũ vẫn chạy”, gần với `R1 ← W2` hơn. Để tránh tranh luận tên gọi, luôn ghi rõ **cặp reader/writer** trong tài liệu và test matrix.

### 2.2. Bảng compatibility matrix

| Reader | Writer | Ý nghĩa |
| --- | --- | --- |
| `R1` | `W1` | Hệ thống ban đầu |
| `R2` | `W1` | Reader mới xử lý payload cũ: backward |
| `R1` | `W2` | Reader cũ xử lý payload mới: forward |
| `R2` | `W2` | Hệ thống mới |
| `R3` | `W1` | Hỗ trợ từ hai phiên bản trước: **transitive** nếu trong phạm vi cam kết |
| `R1` | `W3` | Client rất cũ đọc dữ liệu rất mới: cần contract dài hạn nếu muốn |

Nếu chỉ kiểm thử `R2 × W2`, bạn chưa chứng minh nâng cấp không downtime.

### 2.3. Transitive vs non-transitive

Một hệ thống có `v1 → v2 → v3 → v4`:

- Non-transitive backward thường kiểm tra reader mới với **schema ngay trước**.
- Backward transitive yêu cầu reader mới đọc được **mọi schema cũ trong tập được cam kết**, ví dụ v1, v2, v3.
- Tương tự với forward/full transitive.

Không kết luận “v4 backward với v3, vậy v4 đọc được v1”; tính tương thích không tự bắc cầu qua mọi thay đổi thực tế.

### 2.4. Một compatibility check về schema chưa kiểm tra nghiệp vụ

Schema Registry có thể xác nhận Avro reader schema resolve được writer schema, nhưng không biết:

- `amount` đang là VND hay USD.
- `eventId` có ổn định qua retry hay không.
- Khách hàng có đồng ý chia sẻ `phone` không.
- Enum `CANCELLED` có phá một domain state machine hay không.
- Message `shipmentCreated` có còn giữ ordering invariant không.

Vì vậy cần **schema compatibility tests + semantic contract tests**.

## 3. Thêm trường trong JSON: vì sao “optional” chưa chắc an toàn?

Hợp đồng JSON v1:

~~~json
{
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "amountMinor": 150000
}
~~~

Producer v2 thêm field:

~~~json
{
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

Thay đổi có vẻ additive. Nhưng:

- Reader v1 **strict** có thể reject `currency` là unknown field.
- Reader v2 có thể đòi `currency` non-null và reject payload cũ.
- Reader v2 có thể tự default sang `USD`, khiến đơn hàng lịch sử bị hiểu sai.
- Một consumer sử dụng JSON Schema `additionalProperties: false` có thể reject payload mới.
- API gateway/WAF hoặc generated client có thể enforce closed model.
- Một cache serializer/DB JSON reader có thể khác policy của HTTP mapper.

### 3.1. Ví dụ writer/reader compatibility

| Trường hợp | Kết quả mong muốn | Điều kiện |
| --- | --- | --- |
| Reader v1 đọc JSON v1 | OK | Field cũ đúng |
| Reader v1 đọc JSON v2 | OK nếu support unknown fields | Bỏ qua field `currency` hoặc có version dispatch |
| Reader v2 đọc JSON v1 | OK nếu missing field được hỗ trợ | Có default **đúng nghiệp vụ** hoặc xác định unknown |
| Reader v2 đọc JSON v2 | OK | Cả schema lẫn semantics đúng |

“Optional” là **chấp nhận absent**; nó không đồng nghĩa **optional null** hoặc **optional empty string**. Cần định nghĩa riêng ba trường hợp.

### 3.2. Absent, null và value là ba trạng thái

~~~json
{"orderId":"ORD-100"}
~~~

~~~json
{"orderId":"ORD-100","currency":null}
~~~

~~~json
{"orderId":"ORD-100","currency":"VND"}
~~~

Có thể cần phân biệt:

- **Absent:** writer cũ chưa từng biết field; reader mới cần áp policy legacy.
- **Null:** writer biết field nhưng không có giá trị hoặc yêu cầu xóa giá trị (đặc biệt trong PATCH).
- **Value:** writer cung cấp giá trị hợp lệ.
- **Empty string:** một giá trị chuỗi trống, không tự bằng null.

Đối với `PATCH`, absent thường có nghĩa “giữ nguyên”, null có thể nghĩa “xóa” hoặc “đặt null”; đó là semantics API cần công bố, không giao cho Jackson ngầm quyết định.

## 4. Jackson DTO: nhận field mới mà không phá client cũ

Ví dụ consumer v1 được thiết kế để bỏ qua field mới không hiểu:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderConfirmedV1(
        String eventId,
        String orderId,
        long amountMinor) {
}
~~~

Một JSON v2 có thêm `currency` có thể được deserialize vào `OrderConfirmedV1` vì annotation này hướng dẫn Jackson bỏ qua unknown properties.

**Chỉ dùng khi contract cho phép**: một financial command nên strict về field nguy hiểm hoặc metadata an ninh; bỏ qua mọi field lạ có thể che lỗi chính tả như `amoutMinor` thay vì `amountMinor`.

### 4.1. DTO v2 đọc JSON v1

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderConfirmedV2(
        String eventId,
        String orderId,
        long amountMinor,
        String currency) {

    public String effectiveCurrency() {
        if (currency != null && !currency.isBlank()) {
            return currency;
        }
        // Chỉ đúng nếu v1 contract thực sự quy định tiền VND.
        return "VND";
    }
}
~~~

**Cảnh báo:** Hardcode default `"VND"` chỉ hợp lệ nếu contract v1 khẳng định mọi `amountMinor` là VND. Nếu đơn hàng v1 có thể nhiều loại tiền, reader mới **không thể đoán được** currency từ trường thiếu. Cần lookup theo external metadata, tenant policy hoặc đánh dấu `UNKNOWN` và reconciliation.

### 4.2. Field bắt buộc phải validate riêng

Với Java record:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateOrderRequest(
        @NotBlank String externalId,
        @PositiveOrZero long amountMinor,
        @NotBlank String currency) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping("/v2/orders")
    ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.ok(orders.create(request));
    }
}
~~~

Để Bean Validation chạy, thêm dependency `spring-boot-starter-validation` tương thích. `@Valid` validate DTO sau khi deserialization, không đồng nghĩa đã check quyền người dùng hay transaction idempotency.

Một lỗi hay gặp: field primitive `long amountMinor` bị deserialize thành `0` khi thiếu, khiến không phân biệt absent với zero. Nếu presence quan trọng, dùng `Long` và `@NotNull`, hoặc explicit JSON property presence validation; không dựa primitive default.

### 4.3. Khi cần strict mode

Trong một service, có thể dùng:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Đây là dạng cấu hình phổ biến trên Spring Boot/Jackson 2. Tùy Spring Boot 4/Jackson 3, property/module class có thể thay đổi; xác nhận version trước khi copy. Strict mode giúp bắt typo hoặc field ngoài contract, nhưng khiến mọi additive response field phá client nếu chưa cập nhật.

**Không nhất thiết chọn lenient hay strict toàn ứng dụng**. Có thể chọn policy theo boundary: public command API nghiêm ngặt; event consumer dùng envelope/version và adapter thích ứng; trusted response reader có thể bỏ qua unknown fields nhưng vẫn validate required/semantics.

### 4.4. Unit test đọc payload cũ–mới

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderJsonCompatibilityTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private static final String V1 =
            """
            {"eventId":"evt-100","orderId":"ORD-100",
             "amountMinor":150000}
            """;

    private static final String V2 =
            """
            {"eventId":"evt-100","orderId":"ORD-100",
             "amountMinor":150000,"currency":"VND"}
            """;

    @Test
    void oldReaderAcceptsAddedFieldWhenConfigured() throws Exception {
        OrderConfirmedV1 result =
                mapper.readValue(V2, OrderConfirmedV1.class);

        assertEquals("ORD-100", result.orderId());
    }

    @Test
    void newReaderHandlesLegacyPayloadWhenDefaultIsValid()
            throws Exception {

        OrderConfirmedV2 result =
                mapper.readValue(V1, OrderConfirmedV2.class);

        assertEquals("VND", result.effectiveCurrency());
    }

    @Test
    void newReaderHandlesNewPayload() throws Exception {
        OrderConfirmedV2 result =
                mapper.readValue(V2, OrderConfirmedV2.class);

        assertEquals("VND", result.currency());
    }
}
~~~

Đây là ví dụ dùng Jackson 2-style imports. Test bằng `new ObjectMapper()` không giống Spring Boot configured mapper với custom modules, naming strategy hoặc enum handling. Cần thêm integration test inject **mapper thực tế của application**, đặc biệt với Instant, decimal, enums và polymorphism.

### 4.5. Semantic contract test quan trọng hơn “deserialize không lỗi”

~~~text
Given v1 payload thiếu currency
When reader v2 deserialize
Then currency được đánh dấu LEGACY_VND theo contract v1
And amountMinor vẫn là minor units
And không có foreign exchange conversion ngầm
~~~

Nếu contract v1 không hề bảo đảm currency, assertion trên **không hợp lệ**. Không biến assumption thành “default” chỉ để test xanh.

## 5. Bỏ trường: thường phải thực hiện nhiều giai đoạn

Giả sử event v1:

~~~json
{
  "eventId":"evt-200",
  "orderId":"ORD-200",
  "customerName":"Nguyen A",
  "customerId":"CUST-10"
}
~~~

Muốn bỏ `customerName` vì PII và chuyển sang chỉ dùng `customerId`.

**Thay đổi nguy hiểm:**

~~~json
{
  "eventId":"evt-200",
  "orderId":"ORD-200",
  "customerId":"CUST-10"
}
~~~

Một consumer cũ có thể đang hiển thị `customerName` hoặc validate bắt buộc field này. Xóa ngay ở producer v2 có thể khiến consumer cũ lỗi parse hoặc tệ hơn, ghi dữ liệu rỗng mà không cảnh báo.

### 5.1. Expand → migrate → contract

~~~mermaid
flowchart TD
    A["v1: customerName required"] --> B["EXPAND: thêm customerId, giữ customerName"]
    B --> C["MIGRATE: nâng cấp readers dùng customerId"]
    C --> D["VERIFY: telemetry không còn legacy reader"]
    D --> E["CONTRACT: producer bỏ customerName"]
    E --> F["CLEANUP: deprecate schema, retention/replay policy"]
~~~

Một kế hoạch thực tế:

1. **Expand writer:** thêm field mới, vẫn giữ field cũ nếu an toàn và policy cho phép.
2. **Expand reader:** reader chấp nhận cả hai field, ưu tiên field mới khi present.
3. **Migrate:** cập nhật tất cả consumers, gồm batch jobs, DLQ replay tools, partner SDKs.
4. **Measure:** theo dõi sử dụng field cũ và số reader deployments còn chạy.
5. **Contract:** chỉ bỏ field cũ khi không còn reader cần nó, hoặc tạo major version/topic mới.
6. **Data retention:** vẫn hỗ trợ đọc payload cũ còn trong Kafka topic, database outbox, dead-letter queue và cache.
7. **Cleanup:** xóa code fallback theo cửa sổ cam kết, sau khi có bằng chứng.

### 5.2. Xóa trường khác đổi tên trường

Đổi `customerName` thành `buyerName` là **remove + add** theo góc nhìn schema, không phải một thay đổi rename vô hại. Đội code có thể rename property trong Java nhưng vẫn dùng `@JsonProperty("customerName")` ở wire để giữ hợp đồng cũ.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record BuyerView(
        @JsonProperty("customerName")
        String buyerName) {
}
~~~

DTO này đổi tên Java accessor sang `buyerName()` nhưng **wire JSON key vẫn là `customerName`**. Nếu muốn wire key mới, cần phased migration hoặc separate versioned DTO/endpoint.

### 5.3. Alias khi chuyển tiếp

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerInput(
        @JsonProperty("customerId")
        @JsonAlias({"legacyCustomerId"})
        String customerId) {
}
~~~

`@JsonAlias` hỗ trợ **đọc** các tên cũ khi deserialize; nó không có nghĩa serializer sẽ phát tất cả aliases. Wire output ở ví dụ vẫn theo `customerId`. Khi cả field mới và alias cùng xuất hiện nhưng giá trị khác nhau, phải định nghĩa conflict policy và test, không đoán Jackson sẽ chọn đúng nghiệp vụ.

### 5.4. Khi không thể giữ field cũ

Trường chứa PII/secret đôi khi **phải** bỏ ngay vì rủi ro pháp lý/bảo mật. Khi đó, ưu tiên cách ly bằng API major version mới, queue/topic mới, adapter chuyển tiếp có redaction, thông báo breaking change và migration plan, thay vì tiếp tục phát dữ liệu nhạy cảm chỉ để giữ backward compatibility.

Compatibility là mục tiêu kỹ thuật, **không vượt quyền yêu cầu bảo mật hay tối thiểu hóa dữ liệu**.

## 6. Thêm trường bắt buộc và thay đổi default

Một trường mới **required** với producer v2 có thể làm reader v2 không đọc được payload v1 nếu không có default.

Ví dụ v1:

~~~json
{"orderId":"ORD-1","amountMinor":5000}
~~~

Schema v2 đòi:

~~~json
{"orderId":"ORD-1","amountMinor":5000,"currency":"VND"}
~~~

Nếu reader v2 reject missing `currency` thì `R2 × W1` **không tương thích**. Có ba lựa chọn:

- Giai đoạn đầu khai báo `currency` optional, chỉ required khi tất cả writers đã nâng cấp và không còn payload cũ.
- Cung cấp default thật sự đúng với **mọi** payload v1 trong phạm vi hỗ trợ.
- Dùng schema v2/topic/endpoint mới và version dispatch, không yêu cầu reader v2 đọc v1 trực tiếp.

### 6.1. Default có ba loại

| Loại default | Ví dụ | Điều kiện an toàn |
| --- | --- | --- |
| Kỹ thuật | `retryCount=0` | Không làm đổi business semantics |
| Theo contract cũ | `currency=VND` | V1 **đã cam kết** mọi amount là VND |
| Theo suy đoán | `country=VN` dựa vào data hiện tại | **Không an toàn** với dữ liệu khác |

Một default giúp deserialize nhưng tạo **business bug âm thầm** nguy hiểm hơn một parse error dễ thấy.

### 6.2. Required, non-null và non-empty không giống nhau

- Required: field phải xuất hiện theo schema.
- Non-null: giá trị không được là JSON null.
- Non-blank: string không được rỗng/toàn whitespace.
- Positive: number phải lớn hơn 0.
- Allowed enum/domain: giá trị phải nằm trong policy và state machine.
- Immutable: có thể xuất hiện nhưng không được đổi giữa updates.

Schema validation và Bean Validation cần thể hiện đúng từng ràng buộc. Nếu thêm validation mới cho field cũ, đó cũng có thể là **breaking change** dù JSON schema shape không đổi.

## 7. Đổi kiểu field và kiểu dữ liệu số

Các thay đổi tưởng nhỏ dễ phá wire:

| Thay đổi | Rủi ro | Cách phát triển |
| --- | --- | --- |
| `int` → `long` | Reader cũ có thể overflow | Giới hạn range cũ hoặc version mới |
| `number` → `string` | Deserialize/validation khác | Field mới hoặc adapter |
| `amount=120.50` → `amountMinor=12050` | Thay units/meaning | Field mới + documented units |
| `timestamp` ISO string → epoch millis | Parser sai | Tên mới hoặc version rõ |
| `status="PAID"` → `status=3` | Enum representation | Stable wire values |
| `orderId` string → object | Structure breaking | Add separate `order` object |
| `nullable` → `non-null` | Historical null values fail | Migration/default có kiểm chứng |
| Numeric/string ID normalization | Leading zeros mất | Treat opaque identifiers as strings |

### 7.1. Tiền tệ và precision

Không dùng `double` để tính giá tiền nếu cần precision cố định. Quy định rõ `amountMinor` là số đơn vị nhỏ nhất và `currency` theo ISO-4217, cùng giới hạn integer range. Với currencies có các minor unit khác nhau, không assume mọi currency có 2 decimals.

### 7.2. Timestamp

~~~json
{"occurredAt":"2026-11-21T06:30:00Z"}
~~~

Cần quy định UTC/offset, fractional seconds và clock semantics. Chuyển sang local time string không offset là thay đổi semantic có thể phá ordering/replay.

### 7.3. DateTime Java

~~~java
import java.time.Instant;

public record EventMetadata(
        String eventId,
        Instant occurredAt) {
}
~~~

Nếu dùng Jackson, cần module hỗ trợ Java Time (Spring Boot thường cấu hình mapper khi dependency thích hợp). Một unit test với bare `new ObjectMapper()` không chắc serialize `Instant` giống Boot mapper. Contract test phải dùng đúng object mapper của adapter.

## 8. Enum và trạng thái nghiệp vụ

Writer v1 phát:

~~~json
{"orderId":"ORD-1","status":"PENDING"}
~~~

Writer v2 thêm `PARTIALLY_SHIPPED`:

~~~json
{"orderId":"ORD-1","status":"PARTIALLY_SHIPPED"}
~~~

Reader v1 có Java enum:

~~~java
public enum OrderStatus {
    PENDING, CONFIRMED, SHIPPED
}
~~~

Nếu reader v1 parse string thành enum Java, giá trị mới có thể gây `InvalidFormatException`/deserialization failure. Một JSON field “string” theo schema vẫn có thể phá semantics của reader.

### 8.1. Thiết kế hướng tương lai

- Nếu domain cho phép, có `UNKNOWN`/`UNRECOGNIZED` path rõ.
- Nếu trạng thái mới không thể xử lý đúng, **park/DLQ** thay vì tự gán `PENDING`.
- Dùng exhaustive status handling test; logging/metrics theo loại.
- Có rollout plan: readers hiểu state mới **trước** khi writers phát nó.
- Nếu thay đổi state machine, phải kiểm thử transitions và idempotency.

Ví dụ:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    PARTIALLY_SHIPPED,
    UNKNOWN
}
~~~

Chỉ thêm `UNKNOWN` vào enum **chưa đủ** để Jackson tự map giá trị lạ; cần configure deserialization hoặc custom mapper tùy version. Và xử lý `UNKNOWN` phải fail-safe, không được tự động hoàn tiền/gửi hàng dựa trên giả định.

## 9. JSON Schema: open vs closed objects

JSON Schema thường dùng để xác minh field types/required và hạn chế fields lạ.

Schema v1 minh họa:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["eventId", "orderId", "amountMinor"],
  "properties": {
    "eventId": {"type": "string"},
    "orderId": {"type": "string"},
    "amountMinor": {"type": "integer"}
  },
  "additionalProperties": false
}
~~~

Với `additionalProperties: false`, object v2 có field `currency` **không hợp lệ** theo v1 schema. Nếu yêu cầu forward compatibility, có thể cần object mở, extension namespace hoặc version dispatch.

### 9.1. Khi nào strict unknown field là đúng?

Một API write nhận payment command có thể reject extra fields để tránh client tưởng đã thực hiện semantics chưa hỗ trợ:

~~~json
{"amountMinor":100000,"currency":"VND","refundImmediately":true}
~~~

Nếu server bỏ qua `refundImmediately`, caller có thể hiểu nhầm lệnh đã được áp dụng. Với commands có side effects, strict validation hoặc explicit capability negotiation có thể an toàn hơn open schema.

**Không có một cấu hình unknown-property đúng cho mọi API**. Cần phân biệt **read-oriented events/responses** với **commands**; lựa chọn theo threat model và hợp đồng triển khai.

## 10. REST API: request và response tiến hóa độc lập

Ví dụ API `POST /v1/orders` nhận:

~~~json
{
  "externalId":"ORD-100",
  "amountMinor":120000
}
~~~

Response v1:

~~~json
{
  "id":"100",
  "status":"ACCEPTED"
}
~~~

Server v2 muốn hỗ trợ `currency` ở request và `operationId` ở response.

### 10.1. Request side

- Server mới phải nhận request cũ chưa có `currency` nếu muốn backward với callers cũ.
- Caller mới gửi `currency` có thể fail nếu còn server cũ phía sau load balancer, nên deploy **reader trước writer**.
- Nếu cần chuyển từ optional sang required, đợi tất cả callers cập nhật hoặc dùng endpoint v2.
- Nếu server cũ strict, ngay cả additive request field cũng có thể phá trong rolling deploy.

### 10.2. Response side

- Server mới phát thêm `operationId` chỉ an toàn với callers cũ nếu chúng bỏ qua unknown response fields.
- Server cũ không biết `operationId`; callers mới phải xử lý missing field trong cửa sổ rollback/rolling upgrade.
- Không biến response `status="ACCEPTED"` thành `"COMPLETED"` chỉ để phù hợp UI; đó là semantic contract change.
- Nếu response được cache qua CDN/Redis, cache key và TTL có thể chứa mixed versions.

### 10.3. HTTP compatibility rollout

~~~mermaid
sequenceDiagram
    participant OldClient as Caller v1
    participant NewClient as Caller v2
    participant Server as Server rollout
    Note over Server: Phase A: deploy reader nhận v1 + v2
    OldClient->>Server: v1 request
    Server-->>OldClient: v1-compatible response
    Note over Server: Phase B: client mới bắt đầu gửi v2 field
    NewClient->>Server: v2 request
    Server-->>NewClient: Compatible response
    Note over Server: Phase C: contract/deprecate v1 sau deadline
~~~

Khi nhiều pods cùng version khác nhau, deploy phải bảo đảm cả hai chiều compatibility hoặc routing/canary đúng. Feature flags có thể tắt việc phát field/enum mới dù code mới đã chạy.

## 11. API version: URI, header hay media type?

Không phải mọi thay đổi cần tăng `/v2`. Một thay đổi additive với semantics ổn định có thể giữ version cũ nếu các consumers chấp nhận.

| Chiến lược | Ví dụ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| URI major version | `/api/v2/orders` | Dễ route/document/test | Nhiều endpoints cùng tồn tại |
| Header | `X-API-Version: 2` | URI ổn định | Proxy/cache phải xét header |
| Media type | `Accept: application/vnd.example.order.v2+json` | Phù hợp content negotiation | SDKs/caching phức tạp hơn |
| Event envelope | `schemaVersion: 2` | Dispatch theo event version | Payload vẫn cần durable contract |
| Schema Registry ID | Wire envelope/schema ID | Registry kiểm tra compatibility | Consumer phải phối hợp serialization |
| Separate topic/queue | `orders.confirmed.v2` | Isolation rõ breaking changes | Dual publish/consume và migration |

**Phân biệt major version và minor compatible evolution.** Chọn chiến lược có thể vận hành được và document rõ retirement window. Không dùng timestamp deploy làm schema version.

### 11.1. Cache và HTTP Vary

Nếu response phụ thuộc `Accept` hoặc version header, cache/reverse proxy phải phân biệt các variants (ví dụ `Vary` thích hợp) hoặc cache key phải có version. Nếu không, client v1 có thể nhận v2 payload chưa được hỗ trợ.

### 11.2. HTTP Interfaces của Spring

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/v1")
public interface OrdersHttpApiV1 {

    @GetExchange("/orders/{id}")
    OrderReceiptV1 getOrder(@PathVariable String id);
}
~~~

~~~java
public record OrderReceiptV1(String id, String status) {
}
~~~

Interface chỉ là **client contract trong code**; không tự version/validate server schema. Khi server có v2, có thể tạo `OrdersHttpApiV2` và DTO riêng thay vì thay type v1 rồi làm mọi consumers phụ thuộc thay đổi.

Proxy có thể được tạo bằng `HttpServiceProxyFactory` trên `RestClient` hoặc `WebClient` adapter tùy Spring Framework version; transport vẫn chịu trách nhiệm TLS/auth/timeouts.

## 12. Event-driven contracts: Kafka và RabbitMQ

Một event là **fact đã xảy ra** hoặc thông điệp có semantics đã công bố. Khi producer đổi payload, một consumer đang chậm deploy hoặc đọc từ đầu Kafka topic có thể gặp hàng nghìn sự kiện được tạo bằng schema cũ.

### 12.1. Envelope khuyến nghị

~~~json
{
  "eventId": "b63a4b6f-0a10-4bb7-962b-783e54b3302a",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "aggregateId": "ORD-100",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-21T06:30:00Z",
  "payload": {
    "orderId": "ORD-100",
    "amountMinor": 150000,
    "currency": "VND"
  }
}
~~~

Giải thích:

- `eventId`: identity bất biến của logical event, dùng inbox/idempotency.
- `eventType`: loại event, không phải Java class name trusted.
- `schemaVersion`: chọn parser/adapter, khác aggregate version.
- `aggregateId`: identity của domain aggregate.
- `aggregateVersion`: hỗ trợ ordering/stale-event detection.
- `occurredAt`: thời điểm event phát sinh theo contract; không phải receive timestamp.
- `payload`: domain schema theo version.

**Một eventId phải giữ nguyên khi outbox relay retry**. Nếu chỉ vì thay đổi schema serialization mà tạo eventId mới, consumer có thể áp side effect trùng.

### 12.2. JSON DTO envelope

~~~java
import java.time.Instant;
import com.fasterxml.jackson.databind.JsonNode;

public record EventEnvelope(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        JsonNode payload) {
}
~~~

`JsonNode` cho phép chọn parser theo `eventType`/`schemaVersion`, nhưng phải validate schema, size/depth, trusted event types và authorization. Không lấy arbitrary Java class name từ untrusted header để deserialize tùy ý.

### 12.3. Version dispatch tường minh

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public class OrderEventDecoder {

    private final ObjectMapper mapper;

    public OrderEventDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public CanonicalOrderConfirmed decode(EventEnvelope envelope)
            throws Exception {

        if (!"OrderConfirmed".equals(envelope.eventType())) {
            throw new IllegalArgumentException(
                    "Unsupported event type");
        }

        return switch (envelope.schemaVersion()) {
            case 1 -> {
                OrderConfirmedV1 old =
                        mapper.treeToValue(
                                envelope.payload(),
                                OrderConfirmedV1.class);

                yield mapLegacy(old);
            }
            case 2 -> {
                OrderConfirmedV2 current =
                        mapper.treeToValue(
                                envelope.payload(),
                                OrderConfirmedV2.class);

                yield mapCurrent(current);
            }
            default -> throw new UnsupportedSchemaVersionException(
                    envelope.schemaVersion());
        };
    }

    // mapLegacy/mapCurrent là functions của domain adapter,
    // phải định nghĩa và kiểm thử semantics chuyển đổi.
}
~~~

`CanonicalOrderConfirmed` và `UnsupportedSchemaVersionException` là application-specific types; `mapLegacy`/`mapCurrent` chưa được cung cấp ở snippet này vì khác theo business contract. Lợi ích là parser **không đoán** version từ tình cờ có/mất field.

### 12.4. Upcasting khi cần replay dữ liệu cũ

Một upcaster biến old schema event thành **canonical internal model**:

~~~text
Stored Event v1
   -> validate v1 contract
   -> upcast (v1 amountMinor means VND)
   -> CanonicalOrderConfirmed
   -> business handler
~~~

Upcaster không được tự tạo business fact chưa từng có. Nếu v1 không lưu `customerId`, không nên tự bịa một ID. Có thể tra cứu authoritative source hoặc đánh dấu incomplete và park/reconcile.

### 12.5. Schema version và event type đổi semantics

Nếu `OrderConfirmed` trước kia nghĩa là “order accepted by API” nhưng sau này nghĩa là “payment settled and inventory reserved”, đó là thay đổi **event meaning**. Có thể cần tạo event type mới `OrderFulfilled` hoặc `OrderAccepted`, chứ không đơn giản tăng `schemaVersion` và giữ tên.

## 13. Broker retention, DLQ và consumer downtime

Một event v1 có thể tồn tại:

- Kafka topic retention nhiều ngày.
- RabbitMQ DLQ hoặc delayed retry queues.
- PostgreSQL outbox/inbox/audit tables.
- S3/object archive dùng replay.
- Redis cache chưa hết TTL.
- Customer's exported files.
- Log/CDC pipeline.
- Mobile/partner clients offline.

### 13.1. Thời gian tương thích phải dài hơn deployment

Nếu event nằm trong DLQ 90 ngày, một consumer deploy hôm nay chỉ hiểu v2 nhưng không hiểu v1 có thể **không replay được sự kiện cần xử lý**. Kế hoạch xóa reader v1 phải xét TTL/retention và manual replay policy, không chỉ số pods đang chạy.

### 13.2. Kafka ordering và version

Producer v2 có thể bắt đầu phát event v2 trong khi consumer vẫn đọc `v1` trước đó. Một consumer nâng cấp phải xử lý **mixed versions trên cùng partition**. Schema compatibility không sửa out-of-order business events; dùng `aggregateVersion`/state transition guard.

### 13.3. RabbitMQ queues và schema drift

RabbitMQ chỉ route message theo exchange/queue/binding, không tự biết JSON schema phù hợp. Với nhiều producers vào một queue, một consumer có thể nhận cùng lúc v1/v2. Nếu breaking change, cân nhắc queue mới, routing key mới, dual consumers hoặc adapter, và quan sát DLQ.

## 14. Avro Schema Registry: đọc/ghi theo hai schema

Avro có mô hình **writer schema** và **reader schema**, nên compatibility được định nghĩa khá chính xác. Khi reader mới đọc binary được ghi bằng schema cũ, Avro có rules về field matching và default.

### 14.1. Avro v1

~~~json
{
  "type": "record",
  "name": "OrderConfirmed",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"}
  ]
}
~~~

### 14.2. Avro v2 thêm currency với default

~~~json
{
  "type": "record",
  "name": "OrderConfirmed",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Với `reader v2 × writer v1`, field `currency` **không có trong writer v1**, nên Avro reader schema v2 dùng default `"VND"`. Với `reader v1 × writer v2`, reader có thể bỏ qua field mới trong writer. Trên cơ sở **schema resolution**, thay đổi này có thể là full compatible.

**Nhưng:** default "VND" chỉ đúng nếu tất cả v1 events thực sự dùng VND. Schema Registry không xác minh điều đó.

### 14.3. Thêm field nullable với default

~~~json
{
  "name": "promotionCode",
  "type": ["null", "string"],
  "default": null
}
~~~

Việc có union với null và default null giúp reader mới có hành vi rõ khi writer cũ chưa gửi field. Trong Avro, default phải phù hợp type/union branch rules của specification/version; không tự suy rằng mọi nullable union sẽ parse được nếu schema khai báo sai thứ tự/giá trị default.

### 14.4. Bỏ field trong Avro

Giả sử v1 có field `customerName` mà v2 bỏ:

- Reader v2 có thể bỏ qua field trong writer v1 → thường **backward** theo resolution.
- Reader v1 đọc writer v2: nếu reader v1 **yêu cầu field** mà không có default, sẽ không resolve được → **forward incompatible**.
- Nếu v1 reader schema có default hợp lệ cho field bị bỏ, việc đọc mới có thể được hỗ trợ, nhưng semantics vẫn cần kiểm tra.

Không suy “Avro bỏ field luôn an toàn”. Phải xác định compatibility mode và writer/reader direction.

### 14.5. Schema Registry compatibility modes

Các hệ thống như Confluent Schema Registry hỗ trợ các chế độ thường gặp:

| Mode | Ý nghĩa kiểm tra tổng quát |
| --- | --- |
| `BACKWARD` | New schema đọc được dữ liệu theo version trước |
| `BACKWARD_TRANSITIVE` | New schema đọc được dữ liệu theo tất cả version cũ trong subject |
| `FORWARD` | Reader cũ đọc được new writer theo version trước |
| `FORWARD_TRANSITIVE` | Reader cũ đọc được new writer theo tất cả version cũ |
| `FULL` | Backward + forward với version trước |
| `FULL_TRANSITIVE` | Hai chiều với tất cả versions cũ |
| `NONE` | Không enforce compatibility check |

Tên và semantics cụ thể cần xác nhận với **Schema Registry đang dùng**; các hệ thống registry khác có thể dùng thuật ngữ/chính sách riêng. Registry compatibility là một **gate cần thiết nhưng chưa đủ**; nó không thay semantic tests, privacy policy hay deployment coordination.

### 14.6. Subject naming và hỗn hợp event types

Một Kafka topic có thể chứa nhiều event types. Khi chọn subject naming strategy (theo topic hay record), compatibility scope sẽ khác. Không assume registry tự hiểu `eventType` trong envelope của bạn. Thiết kế topic/subject/record namespaces và phân quyền trước khi deploy.

## 15. Protobuf: giữ field numbers và reserved fields

Protobuf wire format dùng **field numbers** làm identity, không chỉ field names. Ví dụ:

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
}
~~~

Thêm field mới:

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  string currency = 4;
}
~~~

Đối với nhiều Protobuf implementations, unknown field numbers có thể bị bỏ qua hoặc được bảo tồn tùy runtime/operation. Nhưng cần test **application behavior**, không chỉ khả năng parse wire.

### 15.1. Bỏ field phải reserve number/name

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;

  reserved 4;
  reserved "currency";
}
~~~

Khi xóa field đã dùng, dùng `reserved` để ngăn tái sử dụng field number/name trong schema tương lai. Không đổi field number của field cũ để đặt tên mới: binary cũ có thể bị hiểu thành giá trị khác.

### 15.2. Protobuf presence và default

Trong proto3, scalar fields truyền thống có default zero/empty và không phải luôn phân biệt absent với explicit default nếu không dùng cơ chế presence. Dùng `optional` hoặc wrapper/message types phù hợp khi phải phân biệt “không gửi” với “đã gửi giá trị mặc định”.

Một service đổi `quantity=0` từ “unset” sang “số lượng 0 hợp lệ” cần schema/semantic plan, vì wire-format compatibility chưa đủ.

### 15.3. Những thay đổi Protobuf rủi ro

- Thay field number hoặc dùng lại number đã xóa.
- Đổi wire type không tương thích.
- Đổi packed/repeated/cardinality/oneof semantics thiếu kiểm thử.
- Đổi meaning/unit mà giữ tag.
- Enum values mới khiến exhaustive application logic fail.
- Đổi message type khiến consumer chưa nâng cấp mất khả năng hiểu.
- Dùng JSON serialization của Protobuf và giả định giống binary compatibility.

**Proto binary compatibility và Proto JSON compatibility không đồng nhất.** Khi Protobuf đi qua JSON gateway/HTTP, tên trường, unknown field policy và parser semantics phải được kiểm thử riêng.

## 16. SOAP/XML/XSD và namespace versioning

XML/SOAP thường có hợp đồng XSD/WSDL. “Thêm optional element” chưa chắc tương thích với client cũ nếu schema sử dụng `xs:sequence` chặt và không cho phép elements ngoài schema.

### 16.1. XSD v1

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:order:v1"
           xmlns="urn:example:order:v1"
           elementFormDefault="qualified">
  <xs:element name="OrderConfirmed">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="amountMinor" type="xs:long"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

### 16.2. Thêm currency optional ở cuối sequence

~~~xml
<xs:element name="currency"
            type="xs:string"
            minOccurs="0"/>
~~~

Đặt element mới ở vị trí đúng trong `xs:sequence` nếu muốn giữ dữ liệu cũ hợp lệ theo schema v2. Nhưng **client cũ** validate XML mới bằng v1 XSD có thể reject unknown element. Các JAXB-generated classes/versioned WSDL bindings cũng có thể có giới hạn.

### 16.3. Cách nâng cấp với SOAP partners

1. Xác định WSDL/XSD thật sự được các clients dùng.
2. Không đổi namespace/service QName bất ngờ.
3. Thêm optional element chỉ khi client cũ chấp nhận hoặc có contract version rõ.
4. Nếu breaking change, tạo WSDL/namespace v2/endpoint version mới.
5. Đảm bảo JAXB/XML parser test cả old/new responses.
6. Với SOAP faults, version/error mapping phải nhất quán.
7. XML Signature/WS-Security không tự đảm bảo schema compatibility.
8. Xem xét XXE/XML parser hardening và payload size khi thêm trường XML.

### 16.4. xsi:nil và missing

Trong XML, không có element, element rỗng và `xsi:nil="true"` có thể mang ý nghĩa khác. `minOccurs="0"` và `nillable="true"` là hai khái niệm độc lập. Mapping Java/JAXB hoặc Spring Web Services cần test rõ cả hai.

## 17. Hợp đồng trong database và cache

Ngay cả khi consumer code dùng cùng DB, schema migration vẫn là một **hợp đồng giữa phiên bản code cũ–mới**.

### 17.1. Thêm cột nullable trước

Giả sử bảng `orders` cũ:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    amount_minor BIGINT NOT NULL
);
~~~

Cần thêm `currency`:

~~~sql
ALTER TABLE orders
    ADD COLUMN currency VARCHAR(3);
~~~

Cột ban đầu nullable giúp code cũ vẫn insert mà không cung cấp field mới. Sau đó:

1. Deploy code mới đọc `currency` với xử lý legacy null đúng.
2. Migrate/backfill dữ liệu cũ theo nguồn đáng tin cậy.
3. Deploy writers mới luôn ghi `currency`.
4. Xác minh không còn null trong phạm vi cần hỗ trợ.
5. Chỉ lúc an toàn mới áp `NOT NULL`/constraint.
6. Cân nhắc rollback: code cũ có còn insert null sau migration không?

Không đặt `NOT NULL` sớm khi còn pod/job cũ insert records; deployment sẽ lỗi dù code mới đã test xanh.

### 17.2. Đổi tên cột bằng expand-contract

Muốn đổi `customer_name` sang `customer_display_name`:

~~~text
Phase 1: Add new nullable column
Phase 2: New reader understands old and new
Phase 3: Backfill / dual-write or DB sync strategy
Phase 4: All readers switch to new column
Phase 5: Stop old writes, verify
Phase 6: Drop old column in later release
~~~

Dual-write có rủi ro inconsistency. Nếu dùng database triggers để đồng bộ, phải kiểm thử recursion, performance, permissions và rollback. Nếu dùng application dual-write, đảm bảo cùng transaction và xử lý version/concurrency.

### 17.3. JSONB/event table cũng có schema contract

PostgreSQL `payload JSONB` không có nghĩa có thể đổi shape tùy ý. Outbox relay cũ/mới, analytics jobs và DLQ replayers cần hiểu historical payload. Schema version có thể nằm trong envelope/header nhưng phải được lưu **cùng durable event intent**.

### 17.4. Redis cache serialization

Một cache value v1:

~~~json
{"id":"ORD-100","status":"CONFIRMED"}
~~~

Cache value v2:

~~~json
{"id":"ORD-100","status":"CONFIRMED","currency":"VND"}
~~~

Nếu key giống nhau nhưng hai versions xử lý khác, reader cũ có thể fail hoặc dùng default sai. Giải pháp:

- Backward-compatible serializer/deserializer.
- Versioned cache key prefix như `order:v2:ORD-100` khi breaking.
- TTL đủ ngắn + controlled invalidation nếu chấp nhận.
- Dual-read with fallback/migrate nếu cần.
- Không invalidate toàn bộ Redis cluster chỉ vì đổi một DTO mà không có capacity plan.

Cache là dữ liệu phái sinh nhưng vẫn cần kiểm soát khi rollout, đặc biệt để tránh cache stampede sau invalidation.

## 18. Outbox, inbox, idempotency và schema evolution

Một outbox event có identity và schema:

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(24) NOT NULL
);
~~~

Relay có thể gửi lại event sau nhiều ngày. Không nên serialize lại event v1 thành v2 với semantics khác rồi vẫn coi như cùng fact, trừ khi có **một transformation/versioning contract** rõ.

### 18.1. EventId giữ ổn định qua retry

~~~text
Outbox E-100 schemaVersion=1
    -> first publish broker ACK lost
    -> retry E-100 (same eventId, payload or documented upcast)
    -> consumer inbox dedup E-100
~~~

Nếu nâng cấp producer khiến retry tạo eventId mới, consumer có thể áp business effect hai lần. Nếu schema conversion tạo new event identity, phải xác định nó là **event mới hợp lệ** hay chỉ một representation của event cũ và giữ idempotency key ở business layer.

### 18.2. Inbox dedupe khác schema version

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Không thêm `schema_version` vào dedupe primary key một cách vô ý: như vậy cùng eventId được replay bằng schema v1 và v2 có thể bị coi là **hai events khác nhau**. Version là metadata diễn giải, không phải identity nghiệp vụ.

### 18.3. Unknown version vào đâu?

Khi consumer gặp `schemaVersion=99` chưa hỗ trợ:

- Không parse nhầm sang v2 hoặc silently drop.
- Có thể park/DLQ với error category `unsupported_schema_version`.
- Giữ eventId, raw bytes đã được xử lý bảo mật, metadata và retention.
- Không ACK như “business applied” nếu chưa có durable handoff hoặc rõ policy.
- Đặt alert tới contract owner, kiểm tra producer rollout.
- Sau khi cập nhật reader, replay có kiểm soát và inbox chống duplicate.

**Poison message** do schema không tương thích là lỗi permanent cho phiên bản consumer hiện tại; retry nóng liên tục không khắc phục.

## 19. Rollout order: cập nhật reader trước writer

### 19.1. Kịch bản thêm trường

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C1 as Consumer old
    participant C2 as Consumer new
    Note over P,C1: Phase 0: cả hai hiểu v1
    Note over C2: Phase 1: deploy reader hiểu v1+v2
    P->>C2: Produce v1 payload
    Note over P: Phase 2: bật phát v2 field sau khi readers sẵn sàng
    P->>C2: Produce v2 payload
    Note over C1: Phase 3: retire/upgrade consumer old
~~~

Với rollout không đồng thời, hai chiến lược:

- **Reader-first:** producer vẫn phát v1 cho tới khi mọi readers đã chấp nhận v2.
- **Compatibility-first:** producer v2 có thể phát field additive trước nếu đã chứng minh mọi readers v1 có policy unknown fields phù hợp.

Không assume tất cả client/partner có thể nâng cấp ngay. Chỉ một mobile app offline hoặc partner batch job chưa cập nhật cũng có thể phá.

### 19.2. Kịch bản bỏ trường

~~~text
T0: Producer P1 emits {A,B}, Consumer C1 requires B.
T1: C2 deployed; accepts {A,B} and {A}.
T2: Migrate all consumers, including DLQ tools and archives.
T3: P2 emits {A} only.
T4: Retire B after agreed compatibility window.
~~~

Nếu `C1` còn chạy lúc `P2` bắt đầu bỏ B, `C1 × P2` lỗi. Đây là lý do xóa field thường là nhiều release, không một commit.

### 19.3. Canary và feature flag

Có thể deploy binary v2 nhưng giữ `emitNewField=false` trong feature flag. Sau khi metric cho thấy readers và errors ổn định, bật cho một phần traffic/topic/tenant rồi mở rộng. Phải đảm bảo cache, message replay, rollback và routing không tạo mixed incompatible payload theo những consumers không được hỗ trợ.

### 19.4. Rollback không đơn giản

Nếu producer mới đã ghi event v2 vào Kafka hoặc JSONB database, rollback consumer về code v1 có thể khiến nó **không parse được historical v2 payload**. Dù binary rollback nhanh, **data rollback** không chắc thực hiện được.

Vì vậy, giữ reader cũ–mới tương thích trong rollback window hoặc bảo đảm feature flag ngăn phát schema mới trước khi rollback không còn cần.

## 20. Contract registry và quản trị thay đổi

Một hệ thống tích hợp nhiều teams nên có một source of truth:

- OpenAPI cho HTTP endpoints.
- AsyncAPI cho event/message APIs, nếu đội sử dụng.
- JSON Schema/Avro/Protobuf schema definitions.
- WSDL/XSD cho SOAP/XML.
- Database migrations cho SQL.
- ADR/contract changelog cho business semantics.
- Consumer ownership/compatibility support window.
- API deprecation/sunset notice và migration guides.

### 20.1. Versioning không tự thay change management

Mỗi breaking change nên có:

1. Lý do thay đổi.
2. Những readers/writers hiện tồn tại.
3. Compatibility matrix.
4. Minimal rollout sequence.
5. Migration/backfill plan.
6. Retention/DLQ/replay impact.
7. Feature flags và rollback conditions.
8. Security/privacy assessment.
9. Test fixtures/contract tests.
10. Owner + deadline deprecation.

### 20.2. Semantic versioning: hữu ích nhưng không thay tests

Một API SDK version `2.3.0` hoặc schema revision 12 là metadata; việc thay field có breaking hay không phụ thuộc readers. SemVer là cách thông báo thay đổi theo contract; **chỉ tăng minor version không biến breaking change thành compatible**.

## 21. Kiểm thử hợp đồng bốn tổ hợp

Với mỗi thay đổi từ v1 sang v2, lập matrix:

| Test | Payload | Reader | Bắt buộc nếu hỗ trợ |
| --- | --- | --- | --- |
| Baseline | Writer v1 | Reader v1 | Hiện trạng |
| Backward | Writer v1 | Reader v2 | Rollout reader-first/replay |
| Forward | Writer v2 | Reader v1 | Mixed deployment/old clients |
| New | Writer v2 | Reader v2 | Hệ thống mới |

Ngoài parse test, assert **business semantics**, kết quả validation, field default, đơn vị tiền, quyền tenant và side effects. Đừng chỉ assert ObjectMapper không throw exception.

### 21.1. Golden fixtures

Lưu representative serialized payloads trong bộ contract tests:

~~~text
fixtures/
  order-confirmed-v1.json
  order-confirmed-v2.json
  order-confirmed-v2-missing-currency.json
  order-confirmed-v2-null-currency.json
  order-confirmed-v2-unknown-enum.json
  order-confirmed-v2-extra-field.json
~~~

Đây là danh mục **minh họa cấu trúc test**, không phải đề nghị tạo file mới ngoài phạm vi bài. Fixtures phải đủ các cases có/không có field, null, unknown, maximum/minimum, unicode, decimals và malformed payload.

### 21.2. Test tách schema compatibility và semantic validation

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NewConsumerContractTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsOldPayloadWithCorrectHistoricalUnit()
            throws Exception {

        String legacy = """
                {"eventId":"E-10",
                 "orderId":"ORD-10",
                 "amountMinor":10000}
                """;

        OrderConfirmedV2 decoded =
                mapper.readValue(legacy, OrderConfirmedV2.class);

        assertEquals("VND", decoded.effectiveCurrency());
        assertEquals(10000L, decoded.amountMinor());
    }

    @Test
    void doesNotMistakeNullForValidCurrency()
            throws Exception {

        String newPayload = """
                {"eventId":"E-11",
                 "orderId":"ORD-11",
                 "amountMinor":10000,
                 "currency":null}
                """;

        OrderConfirmedV2 decoded =
                mapper.readValue(newPayload, OrderConfirmedV2.class);

        // Ví dụ chính sách v2 reject explicit null.
        assertThrows(IllegalArgumentException.class,
                () -> validateV2RequiredCurrency(decoded));
    }

    private void validateV2RequiredCurrency(OrderConfirmedV2 dto) {
        if (dto.currency() == null || dto.currency().isBlank()) {
            throw new IllegalArgumentException(
                    "currency required for v2 payload");
        }
    }
}
~~~

Đây là snippet có chủ đích phân biệt **legacy missing** và **v2 null** ở lớp validation/dispatch. Nếu đọc cả hai vào cùng DTO mà không giữ schemaVersion/JSON presence, bạn có thể **không phân biệt được** missing và explicit null; production cần envelope version hoặc kiểm tra `JsonNode.has(...)`/`isNull()` trước mapping.

### 21.3. Consumer-driven contract testing

Với REST, có thể dùng các công cụ như Pact hoặc Spring Cloud Contract phù hợp project để xác nhận **những fields/methods mà consumers đang dùng**. Provider chạy verification với test cases từ consumers trước khi deploy.

Nhưng consumer-driven tests không nhất thiết biết một consumer chưa đăng ký, mobile app offline hoặc archive replay. Duy trì inventory consumers và retention support window; đừng xem “tất cả tests trên CI xanh” là chứng minh mọi reader ngoài hệ thống đều đã nâng cấp.

### 21.4. Contract diff automation

Trong CI, diff OpenAPI/JSON Schema/Avro/Protobuf definitions, phân loại:

- Optional field added.
- Required field added.
- Field removed.
- Field renamed.
- Type changed.
- Enum value added.
- Requiredness tightened.
- Default/format/unit changed.
- Endpoint status code/error response changed.
- Message routing/version header changed.

Gating cần biết **chính sách của contract**: một field removed có thể safe trong backward Avro direction nhưng phá forward consumer; một field description đổi đơn vị là breaking dù schema diff tool không phát hiện.

## 22. Test tích hợp HTTP và broker trên Spring Boot

### 22.1. REST adapter test với MockRestServiceServer

Giả sử client dùng `RestClient` và DTO `OrderReceiptV1` bỏ qua unknown field:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class OrdersClientCompatibilityTest {

    @Test
    void oldClientCanReadResponseWithNewField() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer mock =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("https://orders.test")
                .build();

        mock.expect(requestTo("https://orders.test/v1/orders/10"))
                .andRespond(withSuccess(
                        """
                        {"id":"10","status":"ACCEPTED",
                         "operationId":"op-100"}
                        """,
                        MediaType.APPLICATION_JSON));

        OrderReceiptV1 result = client.get()
                .uri("/v1/orders/10")
                .retrieve()
                .body(OrderReceiptV1.class);

        assertNotNull(result);
        assertEquals("10", result.id());
        mock.verify();
    }
}
~~~

Đây là ví dụ **compatibility skeleton**: để bảo đảm old client bỏ qua `operationId`, cần cấu hình unknown-field policy của Jackson converter trong RestClient hoặc annotate `OrderReceiptV1`:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderReceiptV1(String id, String status) {
}
~~~

Unit test trên chỉ chứng minh JSON response mapping; không chứng minh TLS/HTTP connection pool/timeout. Test integration cần dùng client configuration y hệt production.

### 22.2. Kafka/RabbitMQ Testcontainers

Kiểm thử tiêu chí:

1. Producer v1 gửi event cho consumer v2 và business state đúng.
2. Producer v2 gửi event cho consumer v1 khi forward compatibility được cam kết.
3. Consumer restart với dữ liệu v1 tồn trong topic/DLQ.
4. Unknown schema version được park một cách bền, không ACK như applied.
5. JSON TypeId/header untrusted không làm deserialize arbitrary classes.
6. Schema ID/registry endpoint bị mất kết nối có retry/backoff phù hợp.
7. Producer redelivery cùng `eventId` không nhân đôi side effects.
8. Event v1/v2 đến sai thứ tự vẫn có aggregateVersion guard.
9. Queue/topic bindings/routing unchanged hoặc chuyển đổi theo migration plan.
10. Broker message size limits được kiểm tra khi thêm các trường lớn.

**Không chỉ test gọi trực tiếp `@KafkaListener`/`@RabbitListener` Java methods** rồi nghĩ đã kiểm tra serialization/headers/schema registry/ACK. Dùng broker thật trong integration tests khi delivery contract quan trọng.

### 22.3. SQL migration integration test

Với PostgreSQL Testcontainers:

~~~text
Given schema v1 + legacy rows
When apply additive migration v2
Then old application queries/inserts vẫn chạy trong overlap window
And new application đọc được old rows
When backfill completes
Then currency không còn unknown trong scope hỗ trợ
And new writers fill currency
Then only after reader migration apply NOT NULL and drop legacy column
~~~

Dùng Flyway/Liquibase scripts giống production; H2 không chứng minh tương thích PostgreSQL constraints, locking, JSONB và online migration performance.

## 23. Tương thích khi đổi trường trong lỗi và trạng thái HTTP

Một API contract còn gồm error payload:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Order already exists"
}
~~~

Version v2 thêm:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Order already exists",
  "operationId": "op-123",
  "retryable": false
}
~~~

Nếu SDK cũ chỉ đọc `code` và bỏ extra fields, additive response có thể an toàn. Nhưng đổi mã `ORDER_CONFLICT` thành `DUPLICATE_ORDER` mà không giữ alias có thể làm client mapping lỗi, dù schema vẫn chỉ toàn strings.

### 23.1. Retryable không chỉ là field

Nếu thêm `retryable=true` mà server **có thể đã commit side effect**, client retry cần idempotency key. Schema mới không tự an toàn khi client biến unknown timeout thành retry vô hạn.

### 23.2. HTTP status codes cũng là hợp đồng

Đổi `201 Created` thành `202 Accepted` thay đổi thời điểm được coi là hoàn tất. Đổi `409` thành `400` có thể làm SDK/monitoring phân loại khác. Contract tests phải bao gồm headers, response status, error codes, idempotency semantics, không chỉ JSON body.

## 24. Security và privacy trong schema evolution

Một field mới có thể làm tăng exposure:

~~~json
{
  "orderId":"ORD-100",
  "customerEmail":"person@example.org"
}
~~~

Trước khi thêm dữ liệu nhạy cảm vào events:

- Kiểm tra mục đích xử lý và quyền của mọi consumers.
- Đánh giá topic/queue ACL, DLQ retention, logs/metrics/traces.
- Tránh thêm secrets, raw access token hoặc password.
- Nếu PII không cần thiết, phát identifier/reference thay vì field.
- Khi bỏ một PII field, tính cả archive/DLQ/backup retention.
- Kiểm tra ObjectMapper logging/toString của record có thể lộ dữ liệu.
- Cân nhắc encryption/field-level protection khi contract yêu cầu.

Tính tương thích kỹ thuật không phải lý do hợp lệ để giữ dữ liệu nhạy cảm lâu hơn chính sách cho phép.

### 24.1. Schema alias/type mapping cũng có bề mặt tấn công

Không deserialize arbitrary class name từ Kafka/RabbitMQ headers hoặc Java native serialization theo input chưa tin cậy. Dùng allowed event types và DTO mapping tường minh; limit JSON nesting/size, validate business fields và reject/park untrusted content.

## 25. Observability cho giai đoạn chuyển đổi hợp đồng

Không chỉ đếm HTTP 500 hoặc deserialization errors. Cần biết **consumer đang đọc version nào** và **field cũ còn được sử dụng hay không**.

| Metric | Ý nghĩa |
| --- | --- |
| `integration.contract.received` theo `schema_version` | Payload versions thực tế |
| `integration.contract.decoded_success` | Parse và validate pass |
| `integration.contract.decode_failure` | Type/field/enum/schema error |
| `integration.contract.unknown_version` | Event mới hơn reader hỗ trợ |
| `integration.contract.legacy_fallback` | Reader cần default/alias cũ |
| `integration.contract.field_deprecated_used` | Field cũ vẫn được tiêu thụ |
| `integration.contract.payload_mismatch` | Same operationId, different payload |
| `integration.contract.dlq_age` | Events chưa xử lý vì schema |
| `integration.contract.partner_version` | Version mà partner đang dùng, nếu biết |
| `integration.business_applied` | Side effect thực sự hoàn thành |
| `integration.consumer_duplicate` | Replay dedupe bằng eventId |

Tên metrics là **đề xuất instrument của ứng dụng**, không khẳng định Actuator tự sinh toàn bộ.

### 25.1. Cardinality

Metric labels nên gồm `event_type`, `schema_version`, `outcome`, `downstream` có số giá trị hữu hạn. Không dùng raw `eventId`, `orderId`, email, payload, token hoặc URL có secrets làm tags.

### 25.2. Deprecation readiness

Trước khi bỏ field:

1. Đo bao nhiêu consumer instances đang dùng field cũ (nếu quan sát được).
2. Xác định clients bên ngoài không có telemetry.
3. Quét DLQ/backlog/archived event types theo compatibility window.
4. Kiểm tra contract tests cho rollback.
5. Gửi migration notice và xác minh acknowledgement từ partner.
6. Có kill switch ngừng phát schema mới khi lỗi.
7. Có owner xử lý unknown-schema DLQ.

Nếu không chứng minh được reader cũ đã biến mất, không nên xóa field trong một endpoint không version với yêu cầu backward compatibility.

## 26. Runbook khi thêm/bỏ trường làm tích hợp lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Biện pháp |
| --- | --- | --- |
| Jackson `UnrecognizedPropertyException` | Old strict reader gặp field mới | Tắt emit field, nâng cấp reader hoặc policy compatibility |
| Jackson missing creator property | New required field, old payload không có | Default hợp lệ hoặc version dispatcher |
| NullPointerException sau deploy | Missing/null không được kiểm tra | Validate absent/null, migration |
| Giá trị tiền sai nhưng không có parse error | Default hoặc unit đổi nghĩa | Semantic contract fix, reconciliation |
| Enum parse error | Writer phát enum value mới | Reader-first rollout, UNKNOWN/park policy |
| Kafka DLQ tăng sau producer rollout | Consumer không hiểu schemaVersion | Rollback emission, upcast/upgrade |
| Rabbit listener reject TypeId | Converter/class mapper không tương thích | Allowed type mapping, version dispatch |
| REST 400 khi gửi field mới | Server pod v1 strict | Reader-first deployment/feature flag |
| Generated client lỗi sau OpenAPI update | Client model closed/strict | Compat policy hoặc major API version |
| SOAP validation failed | XSD sequence/namespace mismatch | WSDL/XSD versioning |
| Redis cache deserialize lỗi | Key chứa object schema mới | Versioned keys/adapter/invalidation |
| DB insert lỗi NOT NULL | Old writer không ghi cột mới | Rollback constraint, finish migration |
| SQL column not found | Code/schema rollout order sai | Expand migration before code |
| Consumer replay fail sự kiện tháng trước | Non-transitive compatibility | Upcaster/longer support window |
| Same eventId được xử lý hai lần sau upcast | Dedupe key chứa schemaVersion | Dedupe logical identity |
| New response trả PII ngoài dự kiến | Field exposure thiếu review | Disable field, incident/redaction |
| Rollback code không đọc dữ liệu mới | Data đã được phát theo schema mới | Forward reader fallback hoặc version routing |

### 26.1. Thứ tự điều tra

1. Xác định wire payload và schemaVersion thực tế, không dựa vào Java DTO names.
2. Xác định cụ thể writer version và reader version đang chạy.
3. Kiểm tra failure ở deserialize, validation hay business semantics.
4. Xác định thay đổi field/enum/required/default nào phát sinh lỗi.
5. Đánh giá tác động tới broker backlogs, DLQ, outbox và database.
6. Nếu cần, tắt feature flag phát field/version mới, không xóa message evidence.
7. Deploy reader adapter/compat fix với regression fixtures.
8. Replay an toàn, giữ eventId/idempotency.
9. Kiểm tra business state sau replay.
10. Cập nhật compatibility policy, changelog và CI checks.

## 27. Case study: OrderConfirmed từ v1 sang v2

### 27.1. Bối cảnh

- Order Service (producer) phát Kafka `OrderConfirmed`.
- Inventory (consumer) dùng `orderId` và `amountMinor`.
- Billing (consumer) dùng `customerName` cho hóa đơn.
- Analytics reader xử lý event lịch sử.
- Redis lưu `OrderSummary`.
- Một DLQ có event v1 chờ replay.
- V2 muốn thêm `currency` và bỏ `customerName` vì PII.

### 27.2. Kế hoạch sai

~~~text
Release 2:
  Producer xóa customerName, thêm required currency.
  Deploy producer trước.
  Consumer Inventory và Billing chưa cập nhật.
~~~

Hậu quả:

- Billing thiếu `customerName` và có thể fail.
- Inventory strict mapper từ chối `currency`.
- Analytics mới nếu required currency sẽ không parse historical v1.
- DLQ replay v1 vào consumer mới có thể lỗi.
- Rollback producer không xóa được v2 events đã ghi vào topic.

### 27.3. Kế hoạch nhiều giai đoạn

**Giai đoạn A — chuẩn bị compatibility**

- Audit consumers, event retention, DLQ và partner data usage.
- Xác minh v1 `amountMinor` có luôn VND hay không.
- Tạo v2 schema cho currency (initially optional/default đúng).
- Thêm upcaster v1 → canonical event nếu cần.
- Chuẩn bị Billing lookup theo `customerId` thay vì `customerName`.
- CI schema diff và golden fixtures.

**Giai đoạn B — reader-first**

- Deploy Inventory/Billing/Analytics readers hiểu v1 và v2.
- Billing bỏ phụ thuộc bắt buộc vào `customerName`.
- Validate metrics `legacy_fallback`, `unknown_version` và DLQ.
- Nếu producer v1 chưa có `customerId`, có giai đoạn thêm nó trước.

**Giai đoạn C — producer rollout**

- Producer phát `currency`, giữ `customerName` trong giai đoạn overlap khi policy cho phép.
- Bật canary/feature flag; quan sát errors.
- Chạy mixed producer/consumer compatibility matrix.

**Giai đoạn D — contract/deprecation**

- Sau khi không còn reader cần `customerName` và compliance cho phép, producer bỏ field cũ.
- Nếu không thể an toàn trên cùng topic, dùng event major version/topic mới hoặc adapter.
- Giữ reader xử lý historical v1 trong retention/replay window.
- Nếu muốn currency required, xác minh dữ liệu lịch sử/backfill/default chính xác rồi tightening.

### 27.4. Acceptance criteria

~~~text
Given v1 OrderConfirmed event thiếu currency
When v2 Inventory reader xử lý
Then event được interpret bằng historical currency đúng
And không tạo reservation trùng.

Given v2 OrderConfirmed chứa currency mới
When old reader trong hỗ trợ forwards đọc
Then reader không crash hoặc event được route tới compatible adapter.

Given v2 không còn customerName
When Billing reader xử lý
Then Billing dùng customerId từ authoritative source
And không lộ PII cũ trong logs/DLQ mới.

Given event v1 trong DLQ được replay 60 ngày sau
When current reader nhận event
Then version dispatcher hiểu v1
And giữ nguyên eventId để inbox dedupe.
~~~

## 28. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai? | Thay thế |
| --- | --- | --- |
| “Thêm field thì luôn backward compatible” | Strict reader/required/default có thể fail | Reader/writer matrix |
| Chỉ test new reader với new writer | Không kiểm tra rollout overlap | Test cả 4 cặp |
| Đổi tên JSON key khi rename Java property | Wire breaking change | `@JsonProperty`/alias/migration |
| Bỏ field ngay trong producer | Old reader có thể vẫn cần | Expand-migrate-contract |
| Default currency theo cảm tính | Sai tiền không báo lỗi | Business-valid historical default |
| Dùng primitive khi cần detect missing | Missing thành zero/false | Wrapper/presence validation |
| Cho unknown enum biến thành status hợp lệ | Sai state machine | UNKNOWN/park/fail-safe |
| Đổi unit nhưng giữ field name | Semantic breaking change | Field mới/version rõ |
| Đọc mọi schemaVersion bằng DTO hiện tại | Historical payload sai | Version dispatcher/upcaster |
| Schema Registry check xanh là đủ | Chỉ kiểm tra structural resolution | Semantic tests |
| Đổi Protobuf field number | Wire data bị diễn giải sai | Keep/reserve tags |
| Đổi XSD sequence không test old client | XML old reader reject | WSDL/XSD compatibility |
| Chọn strict JSON global cho mọi consumer | Additive events fail | Per-boundary policy |
| Chọn lenient global cho mọi command | Typos silently ignored | Strict command validation |
| Đổi API 201 thành 202 không thông báo | Business completion semantics đổi | Version/contract notice |
| Xóa field khỏi DB trước deploy code | Old code vẫn truy vấn | Expand-contract migration |
| Cache v1/v2 dùng chung key khi schema breaking | Deserialize error | Key versioning/adapter |
| Dedupe key gồm eventId + schemaVersion | Replay cùng event được áp hai lần | Stable eventId |
| Xóa reader cũ ngay sau rollout | DLQ/archives có old events | Retention-aware support |
| Rollback code mà không xét data mới | Old binary có thể không parse | Forward-compatible rollback plan |
| Đưa PII vào schema để “tiện cho consumer” | Privacy/ACL/retention risk | Reference/least data |

## 29. Checklist trước khi phát hành hợp đồng mới

- [ ] Đã chỉ định contract owner và inventory readers/writers.
- [ ] Đã xác định rõ request writer/reader và response writer/reader riêng.
- [ ] Mỗi thay đổi có compatibility matrix `R1/W1`, `R2/W1`, `R1/W2`, `R2/W2`.
- [ ] Có policy backward/forward/full và transitive support window.
- [ ] Đã phân biệt missing/null/empty/default và validate đúng.
- [ ] Không đổi nghĩa/đơn vị/requiredness mà không kiểm tra semantic compatibility.
- [ ] Field mới có default **được chứng minh đúng** cho dữ liệu lịch sử hoặc migration plan.
- [ ] Field bỏ có deprecation/migrate/retention/rollback plan.
- [ ] Không dùng unversioned enum mới khi readers cũ không handle.
- [ ] DTO, Jackson config và Bean Validation nhất quán theo boundary.
- [ ] OpenAPI/AsyncAPI/JSON Schema/Avro/Protobuf/WSDL/XSD được version và kiểm thử.
- [ ] Avro writer/reader compatibility và Schema Registry policy phù hợp.
- [ ] Protobuf field tags được giữ ổn định, tags xóa được reserved.
- [ ] SOAP XML namespace/sequence/minOccurs/nillable được thử với clients cũ.
- [ ] Database migrations theo expand-migrate-contract, test rolling deployments.
- [ ] Redis cache schemas/keys/TTL không phá callers cũ.
- [ ] Event envelope có schemaVersion, eventId, aggregateVersion tách biệt.
- [ ] Outbox/inbox giữ eventId qua retry/replay, không gắn version vào dedupe identity.
- [ ] Consumers đọc được historical events trong Kafka/DLQ/archives theo cam kết.
- [ ] Unknown version được park/DLQ có kiểm soát, không tự áp business effect.
- [ ] Contract tests trên golden fixtures, broker thật và SQL migrations khi cần.
- [ ] Có CI schema diff + semantic tests + canary/feature flag.
- [ ] Đã xác định rollout order, rollback và support deadline cho partners.
- [ ] Metrics đo version distribution, old-field usage, decode errors và business applied.
- [ ] Security/privacy review khi thêm/bỏ PII, secret hoặc authorization-sensitive fields.

**Ghi nhớ:** Hợp đồng dữ liệu sống lâu hơn một lần deploy. “Thêm trường” có thể phá reader cũ strict hoặc reader mới đòi default sai; “bỏ trường” có thể phá client/broker consumer chưa nâng cấp và dữ liệu chờ replay. Cách phát triển an toàn là **định nghĩa tương thích theo reader/writer cụ thể, phân biệt structural và semantic contracts, triển khai reader trước writer, expand–migrate–contract, version dispatch khi cần và kiểm thử toàn bộ ma trận cũ–mới**. Trong Spring Boot Integration, thêm điều kiện **outbox/inbox, idempotency, SQL migrations, cache và observability** để tránh lỗi dữ liệu trở thành lỗi nghiệp vụ âm thầm.

## Tài liệu tham khảo

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, HTTP Interfaces và contract mapping.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): auto-configuration và JSON mapping theo version.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation và boundary validation.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): request/response schema và API documentation.
- [JSON Schema Specification](https://json-schema.org/specification): required, nullable alternatives, additionalProperties.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): writer/reader resolution, defaults, aliases.
- [Confluent Schema Registry — Schema Evolution](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): backward/forward/full/transitive.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): safe field numbering, reserved, presence.
- [Protocol Buffers — Field Presence](https://protobuf.dev/programming-guides/field_presence/): absent, default and optional.
- [W3C XML Schema Definition](https://www.w3.org/TR/xmlschema11-1/): XML/XSD particles, minOccurs, nillable.
- [Spring for Apache Kafka — Reference](https://docs.spring.io/spring-kafka/reference/): producer/consumer and message converters.
- [Spring AMQP — Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ converters, listeners and retry.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): cache and Redis serialization.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned DB schema migrations.
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer/provider contract verification.
- [Pact — Consumer Driven Contract Testing](https://docs.pact.io/): provider compatibility checks.
- [Enterprise Integration Patterns — Versioning](https://www.enterpriseintegrationpatterns.com/ramblings/09_versioning.html): versioned message contracts.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable event intent và retry.
