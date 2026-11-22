# Triển khai nhiều phiên bản với schema và hợp đồng tương thích

## 1. Vấn đề của vận hành tích hợp khi nâng cấp

Trong hệ thống **Spring Boot Integration**, một lần phát hành thường không thay đổi đồng thời tất cả thành phần. Kubernetes có thể đang chạy cả phiên bản N và N+1 của một service; HTTP client của đối tác còn dùng API cũ; consumer Kafka đang xử lý event nhiều tháng trước; database được dùng chung bởi hai phiên bản ứng dụng; outbox và dead-letter queue còn chứa message theo schema cũ.

Một thay đổi tưởng đơn giản như đổi tên trường `customerId` thành `buyerId` hoặc đổi kiểu `amount` từ số nguyên sang chuỗi có thể khiến một phần luồng tích hợp thất bại ngay khi rollout. Nguy hiểm hơn, code có thể chạy nhưng hiểu **sai ý nghĩa nghiệp vụ** của dữ liệu.

Bài này hướng dẫn thiết kế **tương thích tiến hóa (schema/contract evolution)** và quy trình **triển khai đồng thời nhiều phiên bản** an toàn trong các luồng HTTP, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration. Trọng tâm gồm:

- Xác định phiên bản nào **đọc** và phiên bản nào **ghi** dữ liệu ở từng ranh giới.
- Phân biệt tương thích cấu trúc (*schema*) với tương thích ngữ nghĩa (*contract*).
- Dùng **expand → migrate → contract** với database dùng chung.
- Nâng cấp producer/consumer theo đúng thứ tự với Kafka, RabbitMQ và dữ liệu tồn trong outbox/DLT.
- Rollout từng phần bằng rolling update, canary hoặc blue-green, kèm rollback thực sự khả thi.
- Kiểm thử ma trận phiên bản và quan sát lỗi tương thích khi vận hành.

### Tình huống xuyên suốt

Giả sử hệ thống đặt hàng gồm:

~~~mermaid
flowchart LR
    W[Web / Mobile / đối tác] -->|HTTP JSON| A[Order API: N và N+1]
    A --> D[(orders DB)]
    A --> O[(outbox)]
    O --> K[(Kafka orders.events)]
    K --> P[Payment consumer: N và N+1]
    K --> S[Shipping consumer: N]
    P --> H[HTTP Payment Gateway]
    S --> R[(Shipping DB)]
    K --> L[(DLT / retry topics)]
    L --> X[Replay job sau khi sửa lỗi]
~~~

Phiên bản mới muốn bổ sung `currency` vào sự kiện `OrderPlaced` và tách cột địa chỉ giao hàng trong database. Trong thời gian chuyển tiếp, producer mới có thể phát cho consumer cũ, và consumer mới vẫn phải đọc message cũ hoặc message được replay từ DLT.

**Mục tiêu thành công:** không mất message, không hiểu sai tiền tệ hoặc trạng thái, không tạo giao dịch trùng; có thể quay lại code cũ trong cửa sổ rollback mà không phải khôi phục database bằng bản backup.

## 2. Tương thích được định nghĩa từ người đọc và người ghi

“Hai phiên bản tương thích” không phải thuộc tính chung chung của một file schema. Phải nói rõ **ai là writer** (producer, HTTP server khi trả response, code ghi DB) và **ai là reader** (consumer, HTTP client, code đọc DB).

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Backward compatibility** | **Reader mới** có đọc được **dữ liệu writer cũ** không? | Consumer N+1 vẫn xử lý `OrderPlaced` do producer N tạo |
| **Forward compatibility** | **Reader cũ** có đọc được **dữ liệu writer mới** không? | Consumer N không lỗi khi producer N+1 thêm field tùy chọn |
| **Full compatibility** | Cả hai chiều trên có hoạt động không? | Trong rolling update, reader N và N+1 đọc được dữ liệu tương ứng của hai writer |
| **Transitive compatibility** | Reader/writer có đáp ứng tất cả phiên bản lịch sử trong phạm vi công bố không, không chỉ phiên bản liền kề? | Replay event N-3 sau khi chỉ còn consumer N+1 |
| **Semantic compatibility** | Kết quả nghiệp vụ có giữ đúng ý nghĩa dù cấu trúc vẫn parse được không? | Thêm `currency` nhưng consumer cũ không được tính USD như VND |
| **Operational compatibility** | Các phiên bản có cùng hoạt động với DB, broker, cấu hình, TLS, quota và timeout trong lúc rollout không? | Pod N không crash vì migration N+1 đã xóa cột nó cần |

Ma trận **đọc × ghi** để duyệt một rollout đồng thời:

| Reader ↓ / Writer → | Writer N | Writer N+1 |
| --- | --- | --- |
| **Reader N** | Đường cơ sở phải chạy | **Forward compatibility** cần thiết khi writer N+1 hoạt động trước khi reader N biến mất |
| **Reader N+1** | **Backward compatibility** cần thiết khi còn producer N và dữ liệu cũ | Đường mới phải chạy |

Nếu còn phát lại từ outbox hoặc DLT chứa event N-3, ma trận phải mở rộng thêm các cột writer lịch sử. Chỉ test N và N+1 chưa đủ.

### Cấu trúc giống nhau chưa chắc tương thích nghiệp vụ

Giả sử message N có:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-10",
  "orderId": "ord-42",
  "amountMinor": 150000
}
~~~

Ở N+1, thêm field:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-11",
  "orderId": "ord-43",
  "amountMinor": 2500,
  "currency": "USD"
}
~~~

Về cấu trúc JSON, nhiều consumer cũ có thể bỏ qua `currency`. Nhưng consumer N mặc định `amountMinor` luôn là VND có thể tính sai giá trị 2.500 USD thành 2.500 VND. Đây là **thay đổi ngữ nghĩa phá vỡ hợp đồng**, dù decoder không lỗi.

Kế hoạch an toàn hơn là **hai bước**: đầu tiên nâng cấp tất cả consumer để hiểu `currency` nhưng vẫn xử lý VND cũ; sau đó mới bật feature flag cho phép producer phát đa tiền tệ. Khi còn consumer cũ, producer vẫn chỉ phát dữ liệu có ngữ nghĩa mà consumer cũ hiểu đúng.

## 3. Quy tắc tiến hóa hợp đồng HTTP/JSON

### 3.1. Thay đổi cộng thêm và thay đổi phá vỡ

| Thay đổi | Mức độ rủi ro | Điều kiện tương thích |
| --- | --- | --- |
| Thêm field **optional** ở response JSON | Thường thấp | Client cũ cho phép unknown fields; dữ liệu mới không làm sai quy tắc cũ |
| Thêm field bắt buộc trong **request** | Cao | Client cũ chưa gửi field; server mới phải có default/đường xử lý cũ |
| Thêm enum value mới | Cao dù schema có thể cho phép string | Client cũ có thể dùng exhaustive switch và ném lỗi/nhầm default |
| Đổi tên/xóa field | Cao | Reader cũ cần field đó hoặc đang dùng alias chưa được công bố |
| Đổi kiểu `number → string`, `int → object` | Cao | Các deserializer, validation và tính toán có thể lỗi |
| Đổi ý nghĩa nhưng giữ tên field | Rất cao | Có thể âm thầm tính sai dữ liệu |
| Thêm response header tùy chọn | Thường thấp | Client không lệ thuộc tập header cố định |
| Đổi HTTP status / error code | Trung bình–cao | Client có thể retry, bỏ qua hoặc hiển thị sai |
| Đổi authentication scope, TLS CA/certificate | Có thể phá vỡ vận hành | Cần giai đoạn tin cậy song song và cập nhật client trước |

**Thay đổi cộng thêm chỉ an toàn khi contract nêu rõ optional/default và consumer thực tế chấp nhận.** Không nên áp một “quy tắc bỏ qua mọi unknown field” lên request có rủi ro bảo mật cao: server có thể cần từ chối field không được phép để tránh mass assignment hoặc hiểu nhầm ý định của caller.

### 3.2. Server nhận cả request cũ và mới trong giai đoạn chuyển tiếp

Ví dụ API `POST /v1/orders` ban đầu nhận `shippingAddress` dưới dạng chuỗi. N+1 bổ sung `shippingCity` và `shippingPostalCode`, nhưng client N vẫn gửi định dạng cũ.

~~~json
{
  "requestId": "req-501",
  "sku": "SKU-18",
  "quantity": 2,
  "shippingAddress": "1 Main St, HCMC"
}
~~~

Trong cửa sổ chuyển tiếp, server mới có thể nhận đồng thời:

~~~json
{
  "requestId": "req-502",
  "sku": "SKU-18",
  "quantity": 2,
  "shippingAddress": "1 Main St, HCMC",
  "shippingCity": "Ho Chi Minh City",
  "shippingPostalCode": "700000"
}
~~~

Trường địa chỉ cũ vẫn tồn tại cho client/consumer N. Cần xác định khi cả ba trường được gửi: giá trị nào là nguồn chuẩn (*source of truth*) và làm gì khi chúng mâu thuẫn; không chỉ chọn ngẫu nhiên field có mặt.

Ví dụ DTO Java cho **đầu vào trong giai đoạn tương thích**:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderRequest(
        @NotBlank String requestId,
        @NotBlank String sku,
        @Min(1) int quantity,
        String shippingAddress,
        String shippingCity,
        String shippingPostalCode) {
}
~~~

Trong ứng dụng MVC, dùng `@Valid @RequestBody OrderRequest` để kích hoạt Bean Validation và thêm dependency validation phù hợp. Annotation `@JsonIgnoreProperties(ignoreUnknown = true)` chỉ minh họa tính mở rộng; với API nhạy cảm hoặc có write-mapping, cân nhắc validate **allowlist** và từ chối các field chưa có contract. Các field là optional ở wire format không có nghĩa logic nghiệp vụ được phép bỏ qua địa chỉ: validator phải xác nhận **ít nhất một định dạng địa chỉ hoàn chỉnh**, không cho hai định dạng mâu thuẫn và trả lỗi có mã ổn định.

### 3.3. Giữ hợp đồng lỗi và retry

Trong tích hợp HTTP, contract gồm nhiều hơn request body:

- **URI/path** (ví dụ `/v1/orders`), method, query parameter và cách encode;
- **status code**, headers (nhất là `Retry-After` và `Idempotency-Key`);
- **error response** với `code` ổn định, phân biệt validation, conflict, rate limit, unavailable;
- **timeout và retry semantics** của POST/PUT/PATCH;
- **security**: token audience/scope, mTLS identity, certificate trust và chính sách rotation.

Ví dụ một API N trả `409 ORDER_ALREADY_EXISTS` khi lặp `requestId`. N+1 đổi thành `200` kèm bản ghi cũ có thể làm client N hiểu là đã tạo thành công lần mới. Hãy công bố rõ semantics idempotency và kiểm thử client N trước khi thay đổi. Nếu thay đổi phá vỡ thật, có thể mở endpoint/representation version mới (ví dụ `/v2/orders` hoặc media type versioned), duy trì v1 trong thời gian deprecation đã được thỏa thuận.

## 4. Spring Boot: reader chịu được dữ liệu cũ nhưng vẫn kiểm tra ngữ nghĩa

Một consumer có thể nhận cả hai payload `OrderPlaced` minh họa ở mục 2. Decoder mới cần mặc định `currency=VND` **chỉ cho event lịch sử mà hợp đồng cũ xác định tiền tệ là VND**, không tự mặc định VND cho event mới khai báo tiền tệ khác.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.stereotype.Component;

public record OrderPlaced(
        String eventId,
        String orderId,
        long amountMinor,
        String currency) {
}

@Component
public final class OrderPlacedDecoder {
    private static final Set<String> SUPPORTED = Set.of("VND", "USD");
    private final ObjectMapper mapper;

    public OrderPlacedDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public OrderPlaced decode(String rawJson) {
        try {
            JsonNode json = mapper.readTree(rawJson);
            if (json == null || !json.isObject()) {
                throw new IllegalArgumentException("Event phải là JSON object");
            }
            if (!"OrderPlaced".equals(text(json, "eventType"))) {
                throw new IllegalArgumentException("eventType không hỗ trợ");
            }
            JsonNode amount = json.get("amountMinor");
            if (amount == null || !amount.isIntegralNumber()
                    || !amount.canConvertToLong()) {
                throw new IllegalArgumentException("amountMinor phải là long");
            }
            // Chỉ mặc định VND khi field vắng mặt đúng như event lịch sử.
            // Field currency có mặt nhưng null là lỗi hợp đồng.
            String currency = json.has("currency")
                    ? text(json, "currency") : "VND";
            if (!SUPPORTED.contains(currency)) {
                throw new IllegalArgumentException("currency không hỗ trợ");
            }
            return new OrderPlaced(
                    text(json, "eventId"), text(json, "orderId"),
                    amount.longValue(), currency);
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
            throw new IllegalArgumentException("JSON không hợp lệ", ex);
        }
    }

    private static String text(JsonNode json, String field) {
        JsonNode value = json.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Thiếu hoặc sai: " + field);
        }
        return value.textValue();
    }
}
~~~

Mỗi kiểu `public` được đặt trong file Java riêng trong code thực tế; ví dụ gộp để minh họa. Khi triển khai thật, bổ sung giới hạn payload, giới hạn/chuẩn hóa amount và tiêu chuẩn mã tiền tệ theo contract, đồng thời kiểm tra duplicate `eventId`. Đối với dữ liệu liên quan tiền, không dùng `double` để tính giá trị, không tự quy đổi USD/VND theo số nguyên cũ.

Vì decoder cho phép cả VND và USD, **chỉ được phát event USD sau khi các consumer cũ đã được nâng cấp hoặc không còn nhận topic đó**. Nếu cần gửi trước, phải giữ topic v1 chỉ có VND và phát representation v2 ở topic/API riêng hoặc qua adapter chuyển đổi không thay đổi ngữ nghĩa cũ.

### Vấn đề version field

`schemaVersion` hữu ích để định tuyến decoder/upcaster, nhưng không tự bảo đảm compatibility. Nếu consumer N có switch chỉ nhận `schemaVersion=1`, producer N+1 tăng `schemaVersion=2` chỉ vì thêm field optional có thể lập tức gây lỗi, dù JSON vẫn đọc được. Hãy định nghĩa **chính sách phiên bản**: version tăng khi representation đổi, hay chỉ khi breaking change? Cần kiểm tra reader cũ thực tế trước khi bật writer mới.

## 5. Event schema: Kafka, RabbitMQ, Avro, Protobuf và Schema Registry

Event-driven integration phải phục vụ **consumer nhiều phiên bản cùng lúc** và **event lịch sử còn trong log, retry topic hoặc DLT**. HTTP client thường nhận response hiện tại; Kafka consumer có thể đọc record được ghi hàng tháng trước. Vì vậy cần chính sách tương thích cho cả *online rollout* lẫn *replay dài hạn*.

### 5.1. Kiểm soát schema bằng registry

Với Kafka cùng Avro, Protobuf hoặc JSON Schema, có thể dùng một **schema registry** thích hợp. Registry kiểm tra sự tương thích của *schema mới so với những phiên bản đã đăng ký* theo policy; cấu hình cụ thể tùy nhà cung cấp registry và serializer.

Các chế độ thông dụng trong Confluent Schema Registry:

| Chế độ | Đảm bảo theo thuật ngữ registry | Đối tượng cần kiểm thử |
| --- | --- | --- |
| `BACKWARD` | Reader dùng **schema mới** đọc được dữ liệu viết bằng **schema trước liền kề** | Consumer mới nhận record cũ |
| `FORWARD` | Reader dùng **schema cũ** đọc được dữ liệu viết bằng **schema mới** | Consumer cũ nhận record mới |
| `FULL` | Kết hợp `BACKWARD` và `FORWARD` đối với phiên bản liền kề | Các reader/writer N và N+1 |
| `BACKWARD_TRANSITIVE` | Reader mới đọc được dữ liệu từ **mọi schema cũ** trong subject | Replay event lịch sử vào consumer mới |
| `FORWARD_TRANSITIVE` | Mọi reader cũ đọc được dữ liệu viết bằng schema mới | Producer mới phục vụ nhiều consumer lịch sử |
| `FULL_TRANSITIVE` | Tương thích cả hai chiều qua **mọi schema thuộc lịch sử subject** | Mixed-version rộng và replay dài hạn |
| `NONE` | Không có compatibility check tại registry | Chỉ dùng khi đã có cách quản trị khác phù hợp |

Đây là định nghĩa theo **schema registry**; không có nghĩa các consumer đều đã deploy đúng version, không chứng minh business semantics đúng và không xác minh HTTP/DB contract. Mức `BACKWARD` (non-transitive) chỉ xét phiên bản ngay trước, nên một chuỗi thay đổi hợp lệ từng bước vẫn có thể làm reader mới không đọc được record rất cũ.

**Mẹo chọn chiến lược triển khai:** theo mô hình schema evolution thông thường, chế độ backward thường hỗ trợ **nâng consumer trước producer**; forward hỗ trợ **nâng producer trước consumer** nếu hợp đồng của reader cũ thật sự đọc được dữ liệu mới. Trong thực tế rolling update nên ưu tiên reader mới đọc được cũ, và chỉ phát dữ liệu mới khi mọi reader còn sống xử lý đúng. Với nhiều producer/consumer độc lập, yêu cầu `FULL` hoặc `FULL_TRANSITIVE` có thể hữu ích nhưng chi phí phát triển cao hơn.

### 5.2. Avro: thêm field có default

Schema Avro v1 (rút gọn):

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.integration.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"}
  ]
}
~~~

Schema v2 thêm field:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.integration.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Với Avro schema resolution, **reader v2** có thể dùng default `"VND"` khi đọc event viết bằng schema v1 thiếu field `currency`. **Reader v1** thường bỏ qua field `currency` có trong bản ghi do writer v2 tạo. Như đã thấy ở mục 2, nếu writer v2 bắt đầu tạo USD, reader v1 bỏ qua currency và **hiểu sai tiền**. Registry có thể kiểm tra compatibility cấu trúc nhưng không ngăn trường hợp đó.

Nếu field là nullable, schema Avro thường dùng union và default tương ứng:

~~~json
{
  "name": "externalReference",
  "type": ["null", "string"],
  "default": null
}
~~~

Đặt `default` cho field mới khi yêu cầu reader mới đọc lịch sử; nếu loại field cũ, cần xem default/alias của field theo cả chiều forward và backward. Thay đổi enum symbols, numeric types, logical types (decimal scale, timestamp units), tên record hoặc ý nghĩa field có thể gây breaking changes tùy định nghĩa schema và serializer. Không dựa vào một checklist “add field = safe” cho mọi định dạng.

### 5.3. Protobuf: số field là định danh

Trong Protobuf, **field number** là phần quan trọng của wire format; thay tên trường mà giữ number không có nghĩa semantics tự giữ nguyên. Ví dụ:

~~~proto
syntax = "proto3";

package example.integration.events;

message OrderPlaced {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  optional string currency = 4;
}
~~~

Khi xóa field, **không tái sử dụng số field** cho ý nghĩa khác. Có thể `reserved` number/name đã bỏ trong schema mới:

~~~proto
message OrderPlacedLegacyMigration {
  reserved 5;
  reserved "old_internal_code";
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  optional string currency = 4;
}
~~~

Protobuf v3 có các quy tắc presence/default và xử lý unknown fields cần hiểu theo ngôn ngữ/runtime. Thêm enum value hoặc đổi wire type có thể khiến code cũ nhận giá trị unknown hoặc hiểu sai. Các thay đổi field number, repeated/singular, oneof hay map cần kiểm tra theo **Protobuf wire safety** lẫn semantics nghiệp vụ. Đừng chỉ thử parse trong một ngôn ngữ Java rồi kết luận mọi consumer .NET, Go hoặc Node.js đều xử lý giống nhau.

### 5.4. Chủ sở hữu schema và version ở đâu?

Đặt schema ở repository/interface do domain sở hữu hoặc một registry được phân quyền, gắn quyền thay đổi với hợp đồng producer–consumer. Các lựa chọn naming/version gồm:

- **Schema ID** trong wire format/headers (theo serializer và registry); consumer tra schema writer tương ứng.
- **Event type + schema version** trong envelope hoặc metadata; giúp routing/upcasting và audit.
- **Topic/queue versioning** khi breaking semantics không thể duy trì một stream chung (ví dụ `orders.events.v2`).
- **HTTP path/media type versioning** cho client không thể nâng cấp đồng thời.

Versioning không phải mục tiêu tự thân: tạo `v2` mà không có deprecation policy, consumer inventory, retention và replay migration sẽ dẫn tới hai đường tích hợp không bao giờ được dọn dẹp.

### 5.5. Schema trong DLT, retry queue, outbox và replay

Message lỗi có thể mang:

1. Raw bytes theo serializer/schema cũ.
2. Schema ID hoặc headers gốc.
3. Exception metadata do Spring Kafka/RabbitMQ thêm.
4. Payload do recoverer chuyển đổi (có thể khác thông điệp gốc).

Một consumer DLT N+1 không nên mặc định mọi record là JSON v2. Cần lưu/truy xuất schema writer, event type và điều kiện chuyển đổi. Nếu gặp event v0 trong Kafka có retention dài, **schema v0 vẫn phải giải mã được** hoặc có bản sao/migration đáng tin cậy. Không xóa schema cũ khỏi registry hoặc xóa code upcaster trước khi chính sách retention/replay cho phép.

**Thận trọng khi phát lại:** replay giữ nguyên `eventId`/idempotency key, nhưng có thể thêm `replayRunId`, `originalTopic`, `originalOffset` vào metadata phục vụ điều tra. Nếu phải thay đổi payload vì migration, cần công bố đó là **representation mới của cùng sự kiện** hay **sự kiện sửa sai mới**, tránh tạo duplicate/vi phạm thứ tự ngoài ý muốn.

## 6. Database dùng chung: expand → migrate → contract

Trong rolling update, hai phiên bản Spring Boot có thể đồng thời truy vấn **cùng cơ sở dữ liệu**. Vì vậy không được deploy một migration phá vỡ mà chỉ code N+1 hiểu. Đặc biệt, DDL của Flyway/Liquibase có thể chạy **trước khi mọi pod N được thay thế**.

### 6.1. Ví dụ tách cột địa chỉ

Schema ban đầu:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL UNIQUE,
    shipping_address VARCHAR(400) NOT NULL,
    status VARCHAR(32) NOT NULL
);
~~~

N+1 muốn có `shipping_city` và `shipping_postal_code`. Thay vì đổi trực tiếp tên `shipping_address` hoặc thêm hai cột `NOT NULL` không có default, thực hiện nhiều release.

~~~mermaid
flowchart LR
    A[Release N: đọc/ghi shipping_address]
    A --> B[EXPAND: thêm cột nullable]
    B --> C[N+1: dual-write, read fallback]
    C --> D[MIGRATE: backfill theo batch]
    D --> E[Verify mọi writer/reader và dữ liệu]
    E --> F[N+2: đổi nguồn dữ liệu chuẩn qua flag]
    F --> G[CONTRACT: chỉ xóa cột cũ khi hết rollback/replay]
~~~

**Giai đoạn 1 – EXPAND**: migration cộng thêm:

~~~sql
-- V20261121_01__expand_shipping_columns.sql (ví dụ PostgreSQL)
ALTER TABLE orders
    ADD COLUMN shipping_city VARCHAR(120),
    ADD COLUMN shipping_postal_code VARCHAR(32);
~~~

Khi schema mới vẫn chứa cột cũ với ý nghĩa cũ, pod N tiếp tục hoạt động. Cách tạo index, khóa bảng và thời gian DDL khác nhau giữa PostgreSQL, MySQL, SQL Server; không sao chép cú pháp hay giả định migration nhanh trên bảng lớn. Đặt DB migration theo công cụ quản lý version như Flyway/Liquibase, chạy một lần có điều phối và quan sát lock/replication lag.

**Giai đoạn 2 – MIXED READ/WRITE**: version N+1 có thể ghi **cả hai representation** nếu thông tin đủ chính xác; khi đọc, sử dụng cột mới nếu đầy đủ, nếu thiếu thì fallback theo hợp đồng cũ. Phải xử lý trường hợp pod N vẫn ghi chỉ `shipping_address` trong giai đoạn hỗn hợp. Nếu không thể suy ra city/postal code chính xác từ free-text, **không tự đoán**: để null, yêu cầu bổ sung dữ liệu hoặc đánh dấu record cần remediation.

**Giai đoạn 3 – MIGRATE**: backfill dữ liệu lịch sử theo batch có thể chạy lại. Ghi watermark/progress, tránh lock lâu; đọc những bản ghi thiếu cột mới, dùng nguồn dữ liệu tin cậy, cập nhật có điều kiện. Ví dụ minh họa cho dữ liệu đã được chuẩn hóa bên ngoài:

~~~sql
-- Chỉ update khi chưa có dữ liệu mới; giá trị đã được xác minh trước.
UPDATE orders
SET shipping_city = :verified_city,
    shipping_postal_code = :verified_postal_code
WHERE id = :order_id
  AND shipping_city IS NULL
  AND shipping_postal_code IS NULL;
~~~

Nếu vẫn có pod N ghi `shipping_address` mà N+1 đã dùng hai cột mới làm nguồn chuẩn, backfill một lần **không đủ**: cần dual-write/compatibility logic, change capture hoặc chạy backfill lặp lại cho đến khi mọi writer cũ được thay thế và đối soát hoàn tất.

**Giai đoạn 4 – CONTRACT**: chỉ sau khi có bằng chứng không còn code, report, ETL, consumer hoặc replay job phụ thuộc `shipping_address`, mới tạo migration xóa cột cũ ở một release riêng:

~~~sql
-- Chỉ được thực hiện sau khi hết cửa sổ rollback của code cũ.
ALTER TABLE orders DROP COLUMN shipping_address;
~~~

Việc xóa cột không có rollback an toàn chỉ bằng deploy lại JAR cũ. Khi đã chạy contract migration, rollback phải được xem là thay đổi tương thích đã thiết kế hoặc khôi phục dữ liệu theo quy trình riêng; **đừng hứa rollback code cũ luôn khả thi**.

### 6.2. Ma trận tương thích code–database

| Phiên bản code | Schema cũ | Schema đã expand | Schema đã contract |
| --- | --- | --- | --- |
| **N** chỉ dùng `shipping_address` | OK | OK | **Hỏng**: cột bị xóa |
| **N+1** dual-read/dual-write | Có thể không chạy nếu code yêu cầu cột mới | OK | Có thể hỏng nếu vẫn ghi cột cũ |
| **N+2** dùng cột mới, có fallback | Không được deploy trước expand | OK | OK nếu đã loại bỏ mọi truy cập cột cũ |

Không nên diễn giải bảng này như quy tắc cứng của mọi implementation; hãy **kiểm thử bằng binary thực và schema thực**. Thậm chí một migration “thêm cột” có thể làm pod N lỗi nếu code dùng `SELECT *` ánh xạ theo vị trí cột, mapping không chịu unknown field, hoặc ETL phụ thuộc thứ tự cột.

### 6.3. Tương thích khi thay enum/constraint

Một thay đổi như thêm `PAUSED` vào trạng thái đơn hàng có thể khiến phiên bản N:

- Lỗi khi map DB value vào Java enum không chứa `PAUSED`.
- Chạy nhánh `default` không an toàn (ví dụ xem mọi trạng thái lạ là `CANCELLED`).
- Viết ngược `status=RECEIVED` lên record mới vì bản thân nó không hiểu chuyển trạng thái.

Chiến lược: deploy reader nhận/định tuyến unknown status có kiểm soát, **chưa phát trạng thái mới**; sau khi old readers hết hoặc được bảo vệ, mới bật writer trạng thái mới qua feature flag. Nếu DB thêm `CHECK` constraint hoặc `NOT NULL`, kiểm tra mọi writer cũ có còn ghi giá trị vi phạm không trước khi kích hoạt.

### 6.4. Migration không thay thế rollback dữ liệu

Một migration đã thay đổi dữ liệu có thể không đảo ngược được: ví dụ gộp nhiều cột thành một, chuẩn hóa giá trị hoặc xóa trường. Cần phân biệt:

- **Rollback ứng dụng**: chuyển traffic về binary N.
- **Rollback cấu hình/feature flag**: dừng phát định dạng mới nhưng giữ binary N+1.
- **Rollback schema**: chỉ thực hiện nếu migration đảo ngược được, có bản sao an toàn và quy trình xác minh.
- **Data compensation**: tạo thao tác nghiệp vụ mới để sửa dữ liệu, không phải chạy `DROP COLUMN` ngược lại.

Một kế hoạch rollout không có cửa sổ rollback và điểm dừng rõ ràng chưa hoàn chỉnh, kể cả khi migration tool báo thành công.

## 7. Thứ tự triển khai producer và consumer khi nhiều phiên bản cùng tồn tại

Thay đổi trên event stream thường cần nhiều release hơn thay đổi trong một service đơn lẻ, vì producer và consumer có vòng đời độc lập. Một Kafka topic có thể có nhiều consumer group; trong **cùng một consumer group**, các partition còn có thể được chia giữa pod N và N+1. Producer không điều khiển chắc chắn record sẽ đến pod nào trong giai đoạn rolling.

### 7.1. Chiến lược reader-first, writer-later

Với việc bổ sung `currency`:

1. **Đo inventory:** xác định mọi consumer của `orders.events`, kể cả analytics, ETL, audit, replay worker và ứng dụng đối tác. Kiểm tra version/schema mà chúng nhận được.
2. **Đăng ký schema mới và kiểm tra contract:** nếu dùng registry, chạy schema compatibility check; bổ sung contract test semantic.
3. **Deploy reader N+1 trước:** consumer đọc được event N thiếu currency (hiểu là VND theo contract cũ) và event N+1 có currency. Tuy nhiên producer vẫn chỉ phát VND.
4. **Quan sát mixed deployment:** xác nhận mọi instance N+1 xử lý event lịch sử thành công; tìm instance N còn chạy hay consumer group bên ngoài chưa cập nhật.
5. **Kích hoạt writer N+1 sau:** bật feature flag phát currency khác VND chỉ khi không còn reader cũ có thể hiểu sai; trong một số hệ thống phải dùng event type/topic mới thay vì chỉ bật flag.
6. **Giữ khả năng replay:** lưu decoder cho event N trong phiên bản mới đến khi hết thời hạn hỗ trợ lịch sử.
7. **Thu dọn định dạng cũ:** chỉ khi không còn dependency vào message cũ, và đã hoàn tất data migration/retention theo hợp đồng.

~~~mermaid
sequenceDiagram
    participant Ops as Release pipeline
    participant P as Producer
    participant CN as Consumer N
    participant CNew as Consumer N+1
    participant B as Broker
    Ops->>CNew: Deploy reader nhận schema cũ + mới
    Note over CN,CNew: Có thể cùng tồn tại trong nhiều group/rolling
    P->>B: V1 / VND (feature mới OFF)
    B-->>CN: V1
    B-->>CNew: V1
    Ops->>Ops: Kiểm tra inventory, DLT và consumer lag
    Ops->>CN: Thay thế/retire reader cũ
    Ops->>P: Bật writer mới khi an toàn
    P->>B: V2 / USD (feature mới ON)
    B-->>CNew: V2
~~~

**Vì sao không bật writer mới ngay khi thấy một pod consumer N+1 khỏe?** Trong một group, pod N còn giữ partition khác; ở group khác có thể còn consumer N chưa được cập nhật. Nếu writer phát USD, một reader cũ có thể không crash nhưng hạch toán sai.

### 7.2. Khi nào producer-first có thể chấp nhận?

Nếu hợp đồng mới **được chứng minh forward-compatible** với mọi reader cũ đang tồn tại, ví dụ thêm một field mô tả hoàn toàn optional không ảnh hưởng logic cũ, có thể deploy writer trước. Nhưng phải kiểm tra:

- Decoder cũ không bật `FAIL_ON_UNKNOWN_PROPERTIES` hoặc strict schema làm nó reject.
- Field mới không đổi ý nghĩa field cũ, không thêm enum value mà code cũ không hiểu.
- Payload còn đáp ứng giới hạn kích thước broker, registry, HTTP gateway và compression.
- Security policy, log masking, storage/index không phụ thuộc vào tập field cố định.

**Không có một thứ tự chung cho mọi schema.** Quy tắc thực tế là giải quyết dependency: phía nào có thể hiểu cả hai dạng thì triển khai trước, phía tạo dữ liệu chưa được bên kia hiểu thì kích hoạt sau.

### 7.3. Versioned topic hoặc dual-publish khi breaking change

Nếu sự kiện mới có semantics không thể dịch về cũ, ví dụ thay `OrderPlaced` thành `OrderSettled` với trạng thái kế toán khác, hãy cân nhắc:

~~~text
orders.events.v1  <--- producer compatibility adapter  <--- domain state
orders.events.v2  <--- producer v2                    <--- domain state
                         |
                     consumer v2
~~~

Dual-publish có chi phí: hai stream có thể khác nhau về thời gian, ordering và thành công/thất bại. Nên sinh từ cùng một **outbox/source-of-truth**, giữ idempotency key rõ và đối soát hai tuyến. Không gọi hai `KafkaTemplate.send()` rồi kết luận chúng nguyên tử với DB; cần transactional outbox, producer transaction trong đúng phạm vi broker hoặc quy trình retry/reconciliation phù hợp.

Khi chuyển consumer từ v1 sang v2, phải công bố offset cutover, nguồn dữ liệu snapshot/rehydration và cách xử lý giai đoạn overlap để tránh mất event hoặc tiêu thụ trùng. Nếu hai loại event diễn đạt cùng business action, consumer cần biết ngăn duplicate giữa **hai topic** chứ không chỉ trong một topic.

## 8. Các ranh giới tích hợp khác cũng phải tương thích

### 8.1. Outbox, inbox và idempotency trong giai đoạn chuyển tiếp

Một hệ thống đáng tin cậy thường ghi transaction nghiệp vụ và outbox event trong cùng database transaction, rồi publisher bất đồng bộ phát event sang Kafka/RabbitMQ. Trong rolling deployment:

- Pod N có thể ghi outbox payload theo v1.
- Pod N+1 có thể ghi payload theo v2.
- Publisher N hoặc N+1 có thể quét cùng bảng.
- Retry scheduler hoặc DLT replay có thể xuất bản lại event v1 **sau khi producer chính đã lên v2**.

Do đó publisher và consumer mới phải giải mã/định tuyến đúng cả dữ liệu tồn. Mỗi outbox row nên có `eventId`, `eventType`, `schemaVersion` hoặc schema ID, `aggregateId`, trạng thái publish và created time. Publisher không được tự chuyển đổi im lặng v1→v2 nếu phép chuyển đổi làm đổi nghĩa; nếu cần upcast phải là một bước có kiểm thử, idempotency và audit.

Ví dụ cấu trúc inbox để chặn duplicate:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Với PostgreSQL, một handler có thể thử `INSERT ... ON CONFLICT DO NOTHING` trong cùng transaction với thay đổi nghiệp vụ rồi kiểm tra số dòng được insert. Nếu event đã xử lý, không thực hiện side effect lần hai. **Không** đánh dấu `consumed` trước khi transaction nghiệp vụ thành công rồi kết thúc với trạng thái sai; các bước ghi inbox và nghiệp vụ cần cùng phạm vi transaction hoặc một state machine phục hồi được.

Với HTTP gọi đối tác, DB transaction không bao trùm request remote. Nếu N+1 đã gọi đối tác rồi crash trước commit DB, N hoặc N+1 có thể xử lý lại; dùng idempotency key ở đối tác và reconciliation. Deployment đa phiên bản không thay đổi nguyên tắc này.

### 8.2. Spring Integration: message header, channel và transformer

Một `IntegrationFlow` có thể gồm HTTP inbound, adapter file, transformer, router, filter, handler JDBC và outbound broker. Các message header như `contentType`, `correlationId`, `replyChannel`, `errorChannel` có hợp đồng riêng; thay đổi tên, kiểu hoặc cách serialize header có thể phá vỡ flow dùng qua broker hoặc qua ứng dụng khác.

Khi transformer mới xử lý dữ liệu đa phiên bản:

~~~mermaid
flowchart LR
    A[Inbound payload V1/V2] --> B{Nhận diện schema}
    B --> C[Deserializer v1]
    B --> D[Deserializer v2]
    C --> E[Upcast sang CanonicalOrder]
    D --> E
    E --> F[Validate business invariants]
    F --> G[Router/Handler chung]
    G --> H[DB, HTTP hoặc broker]
    F -. Không hợp lệ .-> I[DLT / quarantine]
~~~

Điểm thiết kế hữu ích là **canonical internal model** ổn định trong khoảng nâng cấp. Reader/adapter biên chịu trách nhiệm parse và upcast; tầng nghiệp vụ xử lý model nội bộ. Khi đổi schema nguồn, có thể thay adapter mà không viết lại toàn bộ service.

Tuy nhiên, một message v2 không phải lúc nào cũng chuyển xuống model v1 mà không mất thông tin. Nếu v2 có yêu cầu mới không thể biểu diễn trong v1, phải chặn/định tuyến sang flow mới; không “bỏ qua field” và giả vờ thành công.

### 8.3. Cache schema và cache key

Redis hoặc cache dùng chung giữa pod N và N+1 có thể chứa serialized DTO hoặc object theo version cũ. Một lần deploy có thể lỗi ngay cả khi HTTP, DB và Kafka tương thích:

| Cách lưu cache | Rủi ro | Cách bảo vệ |
| --- | --- | --- |
| Java native serialization | `serialVersionUID`, đổi class/package và binary compatibility | Tránh chia sẻ object binary không kiểm soát version |
| JSON cũ/mới cùng key | Reader cũ reject unknown field hoặc thiếu default | Đọc hỗn hợp, TTL, validation và compatibility tests |
| Đổi semantics nhưng giữ key | Đọc nhầm cache cũ mà không có exception | Namespace key versioned hoặc chủ động invalidate có lộ trình |
| Cache chứa quyền/credential | Dùng dữ liệu phân quyền stale sau deploy | TTL và invalidation hợp đồng; không dùng cache stale khi có yêu cầu security-critical |

Ví dụ `order:summary:v1:{id}` và `order:summary:v2:{id}` cho thay đổi phá vỡ cấu trúc/semantics, với TTL và kế hoạch warm-up/invalidate. Thêm suffix v2 không giải quyết đồng bộ dữ liệu nếu writer cũ còn ghi v1; hai không gian cache phải có policy nhất quán trong thời gian chuyển tiếp.

### 8.4. TLS, secrets và cấu hình chung

Nâng cấp contract đôi khi bao gồm rotation mTLS certificate, CA hoặc OAuth scope của HTTP client. Trong giai đoạn chuyển tiếp:

- Server/gateway cần chấp nhận danh tính/certificate **cũ và mới** trong khoảng được phê duyệt nếu thiết kế PKI cho phép.
- Client mới phải tin cậy CA mới **trước** khi server đổi certificate; thu hồi CA cũ sau khi không còn client lệ thuộc.
- Đổi secret chỉ ở pod mới trong khi pod cũ vẫn chạy có thể tạo lỗi phân bố ngẫu nhiên.
- Không đưa secret vào log/canary tags; phân biệt lỗi TLS/authentication với lỗi schema/HTTP status.

Các biến cấu hình Spring Boot cũng là hợp đồng vận hành. Đổi `app.partner.base-url` hoặc tên feature flag chỉ trong code N+1 có thể khiến pod N bị lỗi khi cả hai cùng đọc một Config Server/Secret chung. Thêm key mới trước, duy trì key cũ trong cửa sổ chuyển tiếp; thay đổi phá vỡ phải có kế hoạch giống DB schema.

## 9. Rolling, canary và blue-green: lựa chọn chiến lược phát hành

### 9.1. Rolling deployment

Rolling update thay dần pod N bằng pod N+1, thường giữ dịch vụ phục vụ liên tục. Đây là cách triển khai phổ biến với Kubernetes Deployment, nhưng nó **bắt buộc N và N+1 cùng hoạt động an toàn** trước database, cache, API và broker.

Ví dụ cấu hình khái niệm cho một Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.internal/order-api:1.9.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
~~~

Giả sử Spring Boot Actuator có cấu hình Kubernetes probes phù hợp và các endpoint trên được phép truy cập từ kubelet. Các trường về replicas, image registry và thời gian là minh họa, cần điều chỉnh theo tài nguyên thực tế. `maxUnavailable: 0` giúp giữ số replica sẵn sàng trong điều kiện đủ capacity, nhưng **không** bảo đảm không có lỗi request trong quá trình chuyển traffic, không thay được connection draining hoặc readiness đúng.

Để graceful shutdown, cần:

- Không tiếp nhận công việc mới khi pod đang dừng.
- Để HTTP request đang xử lý có thời gian hoàn thành trong termination grace.
- Để Kafka/RabbitMQ listener dừng polling/nhận message và xử lý/ack theo chính sách; nếu chưa xác nhận thì broker được phép giao lại.
- Để DB/outbox writer xử lý idempotent khi cùng tác vụ có thể đến pod khác.
- Giữ trace và event correlation trong trường hợp request chuyển từ phiên bản N sang N+1.

Trong Spring Boot có thể cấu hình `server.shutdown=graceful` cùng `spring.lifecycle.timeout-per-shutdown-phase` theo phiên bản và loại web server. Thời gian này phải phối hợp với termination grace của orchestrator. Các scheduler, custom thread pool và message listener cần kiểm tra khả năng dừng riêng; đừng mặc định một flag shutdown sẽ drain mọi adapter.

### 9.2. Canary: chỉ gửi một phần traffic đến N+1

Canary đưa lượng nhỏ traffic hoặc **một nhóm message/tenant** qua phiên bản mới để đo hiệu quả trước khi tăng tỷ lệ. Với HTTP có thể dùng ingress/service mesh để điều hướng phần trăm request. Với Kafka, **không thể đơn giản điều hướng 5% record tới pod N+1** chỉ bằng tăng replica N+1 trong cùng consumer group: partition assignment và key distribution quyết định record đi đâu, không phải request-level load balancer.

Cách canary event consumer có thể gồm:

- **Shadow consumer group** riêng đọc cùng topic để kiểm tra parse/transform, nhưng **không gọi side effect**; cân nhắc chi phí đọc và chính sách PII.
- **Consumer group canary** dành cho một topic/test tenant riêng hoặc phân vùng dữ liệu được thiết kế sẵn.
- **Feature flag** bật logic mới cho một tập business key ổn định, sau khi kiểm tra rằng pod cũ cũng có đường xử lý an toàn.
- **Dual-run comparison**: cùng input vào engine cũ/mới trên dữ liệu đã làm sạch; so kết quả mà không phát hai lần thanh toán/giao hàng.

Canary chỉ có ý nghĩa nếu metric có nhãn `application.version`/`deployment.track` hoặc tín hiệu tách biệt N và N+1. Nếu metrics tổng cộng che mất tỷ lệ lỗi của một replica mới, có thể tưởng rollout thành công.

### 9.3. Blue-green deployment

Blue-green giữ hai nhóm instance độc lập (blue=N, green=N+1), sau đó chuyển traffic. Nó có lợi khi cần rollback **routing** nhanh, nhưng không tách database/broker nếu cả hai cùng dùng chúng.

**Giới hạn quan trọng:** chuyển traffic về blue chỉ an toàn nếu blue còn đọc được trạng thái database, event, cache, config mà green đã ghi. Nếu green đã phát enum mới hoặc migration đã DROP cột cũ, đảo ingress về blue có thể khiến lỗi lan rộng. Vì vậy blue-green cũng cần **expand/compatibility** và feature gating, không được dùng như lý do bỏ qua schema evolution.

### 9.4. Lựa chọn theo điều kiện hệ thống

| Chiến lược | Ưu điểm | Điểm rủi ro về hợp đồng |
| --- | --- | --- |
| Rolling | Ít tài nguyên dự phòng, tự động qua orchestrator | Bắt buộc hỗ trợ mixed version ở thời điểm rollout |
| Canary | Phát hiện lỗi với blast radius nhỏ | Cần routing/traffic split có chủ đích; khó với broker partition |
| Blue-green | Chuyển routing/rollback code nhanh | Shared DB/event schema vẫn có thể phá vỡ blue |
| Shadow read / dual run | So sánh logic cũ–mới trước khi bật writer | Không được tạo double side effect, chú ý dữ liệu nhạy cảm |
| Feature flag | Tách **deploy binary** khỏi **activate behavior** | Phải đồng bộ quy tắc flag, default an toàn và có rollback flag |

### 9.5. Feature flag nên có trạng thái mặc định an toàn

Ví dụ cấu hình:

~~~yaml
# application.yml
integration:
  orders:
    enable-multi-currency-events: false
    read-v1-events: true
    write-legacy-shipping-address: true
~~~

Ý nghĩa:

| Cờ | Khi `false` / `true` | Thời điểm đổi |
| --- | --- | --- |
| `enable-multi-currency-events` | false: chỉ phát VND tương thích; true: có thể phát USD | Chỉ bật sau khi mọi consumer liên quan hiểu currency |
| `read-v1-events` | true: giữ decoder lịch sử | Chỉ cân nhắc tắt sau khi hết replay/retention theo hợp đồng |
| `write-legacy-shipping-address` | true: tiếp tục dual-write | Chỉ tắt khi không còn reader N hoặc đường rollback cần cột cũ |

Đây là **property tùy chỉnh của ứng dụng**, không phải cờ built-in của Spring Boot. Cần bind bằng `@ConfigurationProperties` và xác định cờ được đọc một lần lúc startup hay refresh động. Không nên bật flag tại thời điểm hệ thống chỉ kiểm tra “một pod N+1 đã sẵn sàng”.

## 10. Kiểm thử compatibility trước khi phát hành

### 10.1. Test theo ma trận phiên bản, không chỉ unit test của N+1

Một pipeline nên có kiểm thử ở ba lớp:

1. **Schema/static:** parse/validate Avro/Protobuf/JSON Schema, rule của Schema Registry, contract/OpenAPI diff và DB migration lint.
2. **Behavioral contract:** chạy thực binary/DTO reader N và N+1 với payload của writer N và N+1; kiểm tra không chỉ deserialize mà cả business outcome.
3. **Deployment/integration:** chạy hai phiên bản song song với DB expand, broker/HTTP test doubles, restart/rollback/replay và failure injection.

Ví dụ ma trận cho event `OrderPlaced`:

| Test case | Producer | Consumer | Dữ liệu | Điều kiện đạt |
| --- | --- | --- | --- | --- |
| Baseline | N | N | VND, không currency | Kết quả cũ đúng |
| Backward | N | N+1 | Không currency | N+1 suy ra VND theo hợp đồng, không lỗi |
| Forward structural | N+1 | N | Có currency=VND | N không lỗi và kết quả vẫn đúng |
| Breaking semantic | N+1 | N | currency=USD | **Không được phép phát thực tế** khi N còn sống; test chứng minh rủi ro |
| New normal | N+1 | N+1 | currency=USD | Tính toán đúng đơn vị tiền |
| Historical replay | N-2 | N+1 | Schema cũ hơn, thiếu field khác | Upcaster xử lý hoặc route quarantine rõ ràng |
| Poison event | N/N+1 | N+1 | Sai kiểu, thiếu eventId | Reject/DLT có lý do, không chạy side effect |

**Đặc biệt:** một consumer có thể deserialize được JSON USD nhưng tạo sai giá trị. Vì vậy assert phải bao gồm **đơn vị tiền tệ, amount, idempotency, trạng thái DB và HTTP request được phát**, chứ không chỉ `assertDoesNotThrow`.

### 10.2. Contract tests HTTP

Với HTTP, có thể dùng Spring Cloud Contract, Pact, WireMock/MockWebServer hoặc test theo OpenAPI. Hãy lưu **consumer expectations** của client N khi chạy provider N+1, đồng thời test client N+1 với provider N nếu trong rolling có thể gặp tình huống đó.

Ví dụ tập kịch bản cần xác minh:

- Client N gửi request thiếu `shippingCity`; server N+1 vẫn chấp nhận và xử lý theo contract cũ.
- Client N nhận response có field optional mới; không phát sinh lỗi decoder.
- Server N+1 trả `409` khi trùng `requestId` theo cùng semantics mà client N hiểu.
- Client N+1 không gửi request yêu cầu API v2 tới server N đang nhận traffic (hoặc có route/feature gate rõ).
- Token/mTLS của cả hai client còn được server tin cậy trong cửa sổ overlap.

Consumer-driven contract testing không thay thế test runtime network/TLS hay database migration. Với bên thứ ba không có contract test pipeline, dùng sandbox của đối tác, replay mẫu response đã được công bố và giai đoạn canary có giám sát.

### 10.3. Database migration integration tests

Dùng Testcontainers database engine phù hợp (PostgreSQL/MySQL/MongoDB tùy ứng dụng) để chạy:

~~~text
DB V0 + binary N
  -> chạy EXPAND migration
  -> chạy binary N và N+1 đồng thời
  -> N ghi record cũ, N+1 đọc/ghi record mới
  -> chạy backfill batch nhiều lần
  -> restart và rollback code về N khi vẫn ở schema expanded
  -> assert không mất dữ liệu, không lỗi SQL
  -> chỉ sau khi hết cửa sổ rollback, test CONTRACT migration riêng
~~~

Khẳng định invariant như số dòng, unique request ID, số tiền, trạng thái và tương quan giữa cột cũ/mới. Chạy lại backfill để xác minh idempotency. Với bảng lớn, dùng dữ liệu thử quy mô phù hợp để đo lock duration, index build và replication lag. Không chỉ tin migration “applied” là đã tương thích.

### 10.4. Broker tests và replay

- Kafka: producer N và N+1 xuất bản vào topic test; consumer N/N+1 trong các group riêng đọc cả hai, kiểm tra schema ID, headers và offset. Kiểm tra trong một group đang rolling cũng có thể có pod hỗn hợp.
- RabbitMQ: kiểm tra queue, exchange, routing keys, message properties/headers, serializer và DLQ khi decoder cũ gặp message mới.
- Spring Integration: assert payload và headers trên channel sau transformer/router; với `errorChannel`, không nuốt message khi không parse được schema.
- Outbox/inbox: một event được phát lại có thể consumer đọc nhiều lần, nhưng DB/HTTP side effect vẫn chỉ một lần logic.
- DLT replay: dùng event lịch sử đã lưu, kiểm tra converter tương thích, audit và khả năng dừng khi lỗi vượt ngưỡng.

### 10.5. Cổng kiểm soát CI/CD

Một pipeline phát hành đáng tin nên từ chối rollout nếu:

- Schema mới không đạt policy registry đã đặt, hoặc có thay đổi semantic cần phê duyệt nhưng không có kế hoạch.
- Consumer-driven contract của client còn được hỗ trợ bị hỏng.
- DB migration phá vỡ binary N đang chạy, hoặc không có kế hoạch backfill/rollback.
- Message lịch sử trong tập golden fixtures không giải mã được bởi consumer N+1.
- Không có metric/alert đủ để tách N và N+1 trong canary.
- Không có plan bật/tắt feature mới và xác nhận downstream đã sẵn sàng.

Khi có breaking change đã được phê duyệt, cổng kiểm soát nên yêu cầu **versioned endpoint/topic và deprecation contract** thay vì chỉ bỏ qua mọi lỗi kiểm thử.

## 11. Quan sát hỗn hợp phiên bản và quyết định rollback

Một rollout có thể vượt qua health check nhưng vẫn sai dữ liệu. Readiness chỉ cho biết instance có thể phục vụ theo tiêu chí kiểm tra; nó không khẳng định consumer cũ hiểu schema mới hay HTTP API còn đúng semantics. Vì vậy cần giám sát các **chỉ số hiệu ứng nghiệp vụ**.

### 11.1. Metric và log nên có

| Chỉ số / tín hiệu | Ý nghĩa | Phân tách quan trọng |
| --- | --- | --- |
| `integration_messages_total{service,version,result}` | Tỷ lệ xử lý message thành công/thất bại | Phân tách reader N và N+1 |
| `integration_schema_decode_failures_total{event_type,writer_schema}` | Lỗi decode theo schema writer | Phát hiện message cũ/mới không tương thích |
| `integration_contract_rejections_total{code}` | Lỗi validation/semantics | Phân biệt sai dữ liệu với lỗi hạ tầng |
| `http_server_requests_seconds{version,status}` | Error rate/latency API trong canary | So sánh N và N+1 với baseline |
| `http_client_requests_seconds{remote_service,status}` | Lỗi outbound do contract/timeout/auth | Không đồng nhất 409 với 503 |
| `broker_consumer_lag{group}` | Backlog Kafka khi đổi listener | Group cũ/mới, partition và schema lỗi |
| `dead_letter_backlog{type}` | Số message bị cách ly | Schema incompatible, mapping hay downstream lỗi |
| `outbox_oldest_unpublished_seconds` | Event tồn chưa được phát | Publisher N+1 có đọc được payload N không |
| `database_migration_progress{phase}` | Tiến trình backfill/verify | Có cột null và dual-write lệch không |
| `idempotency_duplicate_suppressed_total` | Bản sao đã bị chặn | Tăng bất thường sau rollout/rollback |
| `business_reconciliation_mismatch_total` | Tác dụng phụ hoặc số tiền không khớp | Phát hiện sai ngữ nghĩa dù parse thành công |

Tên metric trên là **đề xuất triển khai**, không phải tất cả được Spring Boot/Micrometer tự xuất. Tag như `service`, `application.version`, `eventType` và mã lỗi chuẩn có thể hữu ích, nhưng tránh đưa `requestId`, `eventId`, email, customer ID, raw payload hoặc exception message vào metric label vì cardinality/PII. Correlation ID cần được lưu ở log/tracing có quyền truy cập và retention phù hợp.

### 11.2. Canary gates đo kết quả nghiệp vụ

Ví dụ điều kiện trước khi tăng canary từ 5% lên 25%:

- Không có **schema decode error** mới so với baseline sau một chu kỳ nhận đủ sự kiện đại diện.
- HTTP 5xx, timeout và P95/P99 latency không vượt SLO/error budget đã thống nhất.
- Tỷ lệ Kafka DLT/RabbitMQ DLQ không tăng do message v1/v2.
- Không có chênh lệch số tiền/tiền tệ, trạng thái đơn hàng hoặc event count trong đối soát.
- Không có schema migration lỗi, lock kéo dài hoặc outbox backlog tăng liên tục.
- Các consumer group độc lập và đối tác bên ngoài đã xác nhận trạng thái tương thích.
- Có khả năng tắt feature writer mới và dừng rollout trong cùng ca vận hành.

Ngưỡng chính xác phải dựa trên baseline traffic và business SLO; không nên đưa một con số cố định cho mọi hệ thống. Với event hiếm nhưng rủi ro cao (hoàn tiền, hủy đơn), tỷ lệ sample 5% có thể chưa xuất hiện ca tương ứng; phải test bằng fixture riêng và tăng thời gian quan sát khi cần.

### 11.3. Khi nào rollback code là không đủ?

Giả sử N+1 đã:

1. Thêm state `PAUSED` vào database.
2. Phát event `OrderPlaced(currency=USD)` cho topic chung.
3. Xóa cột `shipping_address`.

Nếu đổi toàn bộ pod về N, code N có thể fail khi map `PAUSED`, tính sai USD và lỗi SQL. Lúc này rollback routing/code **không** phải lựa chọn an toàn.

Khả năng rollback phải được xây **trước khi phát hành**:

- Giữ DB ở schema expanded ít nhất qua cửa sổ rollback.
- Chưa phát semantics mới cho đến khi không còn reader không tương thích.
- Tắt writer mới bằng feature flag mà không buộc dừng toàn bộ hệ thống.
- Lưu dữ liệu/metadata cần khôi phục nếu có bước chuyển đổi không đảo ngược.
- Có quy trình bù trừ và reconciliation nếu tác dụng phụ bên ngoài đã xảy ra.

Nếu đã đi qua điểm không thể quay lại (irreversible change), kế hoạch khôi phục phải là **roll-forward fix**, hotfix tương thích, hoặc restore/bù trừ có kiểm soát, không tuyên bố “rollback bằng một lệnh Kubernetes”.

## 12. Runbook phát hành mẫu: từ N lên N+1

### 12.1. Trước cửa sổ triển khai

1. **Chốt hợp đồng:** xác định writer/reader N và N+1 theo HTTP, event, database, cache, SSL và config.
2. **Định danh mọi consumer:** bao gồm các consumer group không do cùng team quản lý, batch job, CDC, BI/report, outbox publisher, replay worker.
3. **Đặt compatibility policy:** chọn schema registry mode (thường cân nhắc transitive cho lịch sử dài), OpenAPI/contract test và deprecation timeline.
4. **Xác định điểm không thể đảo ngược:** DROP cột, ghi giá trị enum mới, phát multi-currency event, thay đổi state machine.
5. **Chuẩn bị metric, alert, dashboard:** tách theo phiên bản, có backlog, error, DLT, business reconciliation.
6. **Kiểm tra phương án hồi phục:** tắt cờ, đảo traffic, rollback code ở expanded DB, dừng producer mới; xác định ai có quyền quyết định.

### 12.2. Giai đoạn mở rộng

| Bước | Việc thực hiện | Điều kiện tiếp tục |
| --- | --- | --- |
| A | Chạy migration **additive** (thêm nullable column, index theo chiến lược online) | Code N vẫn đọc/ghi bình thường |
| B | Đăng ký schema mới và kiểm tra compatibility | Schema/semantics tests đạt |
| C | Deploy consumer/HTTP server N+1 có đường đọc cả v1/v2 | Không tăng lỗi decode/contract |
| D | Giữ writer mới **OFF**; old producer tiếp tục phát dữ liệu cũ | Toàn bộ reader nằm trong tập tương thích |
| E | Triển khai dual-read/dual-write cho DB qua feature gate | Cột cũ/mới nhất quán, old pod không lỗi |
| F | Chạy backfill theo batch, đối soát | Không còn dữ liệu thiếu chưa được đánh dấu/remediate |

Trước khi bật producer, phải có **bằng chứng** chứ không chỉ thông báo “đã deploy N+1”: bảng version của tất cả pod, trạng thái consumer group, danh sách đối tác và smoke test v1/v2. Nếu N vẫn chạy, event mới phải giữ semantics N hiểu được.

### 12.3. Giai đoạn kích hoạt

1. Bật một phần hành vi mới qua flag/canary trên tập traffic được định nghĩa rõ.
2. Đo lỗi schema, DLT, consumer lag, API latency, outbox backlog và business invariants.
3. Tăng tỷ lệ canary theo bậc; ở mỗi bậc kiểm tra cả dữ liệu mới và event lịch sử.
4. Khi tất cả reader liên quan hỗ trợ và đã xác minh, mới cho producer phát dữ liệu mang semantics mới.
5. Theo dõi một khoảng đủ dài cho việc replay, scheduler, batch/ETL và dữ liệu có thời gian sống dài; không chỉ kiểm tra vài phút sau deployment.

### 12.4. Giai đoạn thu gọn

Sau khi hết cửa sổ rollback và đã xác nhận không còn consumer cũ:

- Gỡ feature flag không còn cần thiết theo quy trình kiểm thử.
- Thực hiện migration contract ở release khác (ví dụ `DROP COLUMN`) với kế hoạch backup/restore riêng.
- Dừng dual-publish/dual-write sau khi xác nhận không còn reader cần đường cũ.
- Cập nhật API deprecation notice, schema registry lifecycle, tài liệu producer/consumer và playbook replay.
- Giữ upcaster/decoder lịch sử đến khi không còn dữ liệu hợp lệ có thể được phát lại.
- Xóa metric/check chỉ phục vụ giai đoạn chuyển tiếp **sau khi** đã có bằng chứng hệ thống ổn định.

Không nên gộp **expand, bật semantics mới và contract destructive** vào cùng một phát hành vì rất khó khôi phục khi có lỗi.

### 12.5. Bảng go/no-go và hành động dừng

| Tín hiệu | Hành động trước tiên | Có nên rollback binary N? |
| --- | --- | --- |
| Tăng decode error khi writer mới vừa bật | **Tắt writer flag**, dừng rollout, kiểm tra consumer cũ | Chỉ nếu N vẫn đọc được dữ liệu đã phát |
| Đã chạy migration expand, code N+1 lỗi | Dừng rollout, kiểm tra lỗi schema; giữ schema expanded | Thường có thể rollback binary N nếu đã test |
| Đã DROP cột mà N còn dùng | Dừng thay đổi; roll-forward fix/khôi phục có kiểm soát | **Không** đơn giản rollback N |
| DLT tăng vì message lịch sử | Giữ message, bật upcaster/decoder hoặc xử lý schema | Không tự replay trước khi sửa |
| Business mismatch nhưng không có exception | Dừng phát dữ liệu mới, cô lập nguồn sai và đối soát | Không rollback mù vì dữ liệu mới có thể đã được ghi |
| HTTP đối tác từ chối TLS/permission mới | Dừng rollout cert/auth, khôi phục trust overlap an toàn | Tùy tính tương thích cert/secret với version N |
| Consumer lag tăng sau nâng cấp | Kiểm tra tốc độ xử lý, deserializer, partition distribution | Chỉ rollback nếu dữ liệu đã nhận vẫn tương thích |

Runbook phải có người phụ trách cụ thể cho DB migration, schema registry, producer flag, consumer fleet, đối tác bên ngoài và decision rollback. Với những hệ thống có quy trình phê duyệt thay đổi, cần lưu bằng chứng test và thời điểm đạt các gate trước khi chuyển giai đoạn.

## 13. Những sai lầm phổ biến và câu hỏi tự kiểm tra

### Sai lầm nên tránh

1. **“Schema registry báo PASS nên nghiệp vụ an toàn.”** Registry kiểm tra wire/schema, không biết consumer cũ sẽ hiểu USD như VND.
2. **“Chỉ có một service nên deploy đồng thời dễ.”** Database, cache, outbox, cron job và message lịch sử cũng là reader/writer có version.
3. **“Thêm field luôn backward/forward compatible.”** Điều đó phụ thuộc decoder, default, required/optional, enum, semantics và hướng đọc–ghi.
4. **“Flyway migrate thành công tức là rollback được.”** Migration destructive hoặc data transformation không đảo ngược bằng thay JAR.
5. **“Blue-green không có mixed version.”** Có thể không có mixed HTTP traffic, nhưng shared DB/broker vẫn chịu dữ liệu ghi bởi green.
6. **“Consumer Kafka mới chạy khỏe là mọi consumer đã sẵn sàng.”** Còn group ngoài, analytics, batch job hoặc replay worker chưa cập nhật.
7. **“Replay chỉ là gửi message lại.”** Cần giữ eventId, có audit, giới hạn tốc độ, xử lý ordering và idempotency.
8. **“Canary pass thì được xóa cột cũ ngay.”** Batch, report, ETL và rollback window có thể chưa được kiểm tra.

### Câu hỏi tự kiểm tra

- Nếu reader N+1 đọc được payload N nhưng reader N lỗi với payload N+1, hợp đồng có backward, forward hay full compatibility?
- Vì sao schema `OrderPlaced` thêm `currency` với default VND vẫn có thể là breaking change khi producer bắt đầu phát USD?
- Vì sao `BACKWARD` không đồng nghĩa `BACKWARD_TRANSITIVE` trong Schema Registry?
- Nếu pod N và N+1 cùng chạy sau khi `ALTER TABLE ADD COLUMN`, điều kiện nào khiến migration vẫn có thể gây lỗi?
- Sau khi bật producer mới, việc chuyển traffic blue-green về pod cũ có luôn an toàn không?
- Kafka consumer group N+1 đã được nâng cấp 95% có đủ để phát event mới chưa? Những reader còn lại là ai?
- Khi một outbox row N được publish sau khi tất cả producer đã chạy N+1, consumer cần khả năng nào?
- Tại sao feature flag, idempotency, compatibility test và monitoring phải được thiết kế cùng nhau?

**Kết luận:** triển khai nhiều phiên bản an toàn là một bài toán **reader/writer compatibility và điều phối thời điểm thay đổi**, không chỉ là chạy nhiều pod. Trong Spring Boot Integration, một quy trình đáng tin cậy phải đảm bảo hợp đồng HTTP, schema sự kiện, database, cache, cấu hình và dữ liệu replay **đều** được xét trong cùng ma trận phiên bản. Cách làm hiệu quả là **mở rộng trước, nâng reader trước, kích hoạt writer sau, quan sát và đối soát, rồi mới loại bỏ dạng cũ**.

## Tài liệu tham khảo

- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Apache Avro — Schema Resolution and Defaults](https://avro.apache.org/docs/current/specification/#schema-resolution)
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Protocol Buffers — Proto Best Practices](https://protobuf.dev/best-practices/dos-donts/)
- [Spring Boot Reference — Database Initialization and Migration](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)
- [Flyway Documentation — Migrations](https://documentation.red-gate.com/fd/migrations-184127470.html)
- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Integration Reference — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html)
- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Container Lifecycle / Termination](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)





