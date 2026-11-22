# Phối hợp phát hành producer, consumer và schema tương thích

Trong hệ thống serverless hướng sự kiện, producer và consumer thường được triển khai độc lập. Một Java function có thể phát event vào queue hoặc event bus; một function khác nhận event sau vài mili giây hoặc nhiều giờ. Khi producer đổi tên field, thay kiểu dữ liệu hoặc đổi ý nghĩa event, consumer cũ có thể vẫn đang chạy và tiếp tục nhận message đã nằm trong queue từ trước.

Vì vậy, phát hành một service không chỉ là triển khai code mới. Đội phát triển phải phối hợp **event contract**, **schema evolution**, thứ tự rollout, khả năng đọc message cũ và cách rollback. Một schema hợp lệ về cú pháp vẫn có thể phá vỡ nghiệp vụ nếu nó đổi ý nghĩa field, đơn vị tiền, semantics của event hoặc quy tắc ordering.

Bài học này hướng dẫn cách thiết kế contract cho producer/consumer Java, đánh giá backward/forward compatibility, mở rộng schema theo từng bước, kiểm thử tương thích trong CI/CD và phát hành an toàn khi nhiều revision cùng hoạt động.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả event contract gồm envelope, payload, schema và semantics.
- Phân biệt event type/version với schema version và version của ứng dụng.
- Giải thích backward, forward và full compatibility.
- Thay đổi JSON, Avro hoặc Protobuf schema mà không phá consumer đang chạy.
- Áp dụng expand-contract để phát hành producer và consumer theo nhiều giai đoạn.
- Thiết kế consumer chịu được field mới, field thiếu, event cũ và message lặp.
- Viết producer/consumer contract test và kiểm tra schema trong pipeline.
- Lên kế hoạch canary, rollback, replay và xử lý message trong DLQ.
- Nhận diện thay đổi schema tương thích về cấu trúc nhưng phá vỡ semantics nghiệp vụ.

## 1. Producer, consumer và event contract

**Producer** là thành phần tạo và gửi event. **Consumer** là thành phần nhận và xử lý event. Chúng có thể chạy trên các function, service, team hoặc lịch phát hành khác nhau.

Ví dụ trong hệ thống đặt hàng:

- `order-api` tạo đơn và phát `OrderPlaced`.
- `inventory-worker` giữ hàng khi nhận `OrderPlaced`.
- `payment-worker` khởi tạo thanh toán.
- `notification-worker` gửi thông báo sau khi đơn được xác nhận.

~~~mermaid
flowchart LR
    A["order-api<br/>Producer"] --> Q["Queue / Event bus"]
    Q --> B["inventory-worker<br/>Consumer"]
    Q --> C["payment-worker<br/>Consumer"]
    Q --> D["notification-worker<br/>Consumer"]
    B --> DB1["Inventory"]
    C --> DB2["Payment provider"]
    D --> DB3["Notification provider"]
~~~

Một event contract không chỉ là cấu trúc JSON. Nó cần mô tả ít nhất:

1. **Identity:** event ID ổn định để deduplicate và truy vết.
2. **Type:** tên event thể hiện sự kiện nghiệp vụ đã xảy ra, ví dụ `com.example.order.placed`.
3. **Source/producer:** hệ thống tạo event.
4. **Time:** thời điểm nghiệp vụ xảy ra, phân biệt với thời điểm consumer nhận.
5. **Schema:** tên field, kiểu, required/optional, format và quy tắc tiến hóa.
6. **Semantics:** field có ý nghĩa gì, đơn vị nào, trạng thái nào được phép.
7. **Delivery behavior:** ordering, duplicate, retry, retention và dead-letter behavior.
8. **Ownership:** team chịu trách nhiệm thay đổi contract và thông báo cho consumer.

### Envelope và payload

Nên phân biệt metadata vận chuyển với dữ liệu nghiệp vụ. Ví dụ envelope:

~~~json
{
  "eventId": "evt-01J8QX8K6J4P",
  "eventType": "com.example.order.placed",
  "schemaVersion": "2.0",
  "source": "orders-api",
  "occurredAt": "2026-11-17T10:15:30Z",
  "data": {
    "orderId": "ord-1042",
    "customerId": "cus-77",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

- `eventId` là định danh của một sự kiện đã xảy ra; retry phải giữ nguyên ID.
- `eventType` xác định loại sự kiện nghiệp vụ.
- `schemaVersion` chỉ phiên bản cấu trúc payload/envelope theo quy ước.
- `occurredAt` là thời điểm nghiệp vụ xảy ra, không phải thời điểm message được giao.
- `data` chứa payload theo schema.

Nếu hệ thống dùng CloudEvents, hãy tuân theo envelope và thuộc tính chuẩn của CloudEvents thay vì tự tạo một envelope không tương thích. Nếu dùng schema registry, quy định subject/name và version theo cách registry yêu cầu.

Không dùng số version của Lambda/Cloud Run revision làm schema version. Một revision có thể phát cùng schema với revision trước; một schema có thể được nhiều phiên bản ứng dụng dùng.

## 2. Schema compatibility: backward, forward và full

Compatibility mô tả khả năng reader/consumer và writer/producer làm việc với dữ liệu được tạo từ schema ở thời điểm khác nhau.

Giả sử schema v1 có các field `orderId` và `totalAmount`. Schema v2 thêm `currency`.

| Loại compatibility | Ý nghĩa | Ví dụ |
|---|---|---|
| **Backward** | Code/schema mới có thể đọc dữ liệu được ghi theo schema cũ | Consumer mới đọc event v1 thiếu `currency` |
| **Forward** | Code/schema cũ có thể đọc dữ liệu được ghi theo schema mới | Consumer cũ bỏ qua field `currency` mới |
| **Full** | Cả hai hướng đều tương thích | Consumer mới đọc event cũ và consumer cũ đọc event mới |
| **Breaking** | Một hoặc cả hai hướng không còn tương thích | Đổi `totalAmount` từ integer sang object mà consumer cũ không hiểu |

Tên gọi backward/forward đôi khi được mô tả theo góc nhìn writer/reader hoặc schema registry. Trong bài này, backward nghĩa là reader mới đọc được dữ liệu cũ; forward nghĩa là reader cũ đọc được dữ liệu mới. Khi dùng registry, phải kiểm tra định nghĩa mode cụ thể của registry và phạm vi kiểm tra (latest hay transitive).

### Ví dụ thêm field tùy chọn

Schema v1:

~~~json
{
  "type": "object",
  "required": ["orderId", "totalAmount"],
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "integer" }
  }
}
~~~

Schema v2 thêm field `currency` không bắt buộc:

~~~json
{
  "type": "object",
  "required": ["orderId", "totalAmount"],
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "integer" },
    "currency": { "type": "string" }
  }
}
~~~

Consumer v1 có thể tiếp tục đọc event v2 nếu parser/schema policy cho phép bỏ qua property chưa biết. Consumer v2 phải xử lý event v1 không có `currency`. Nếu contract lịch sử quy định mọi `totalAmount` đều là VND, consumer mới có thể dùng fallback VND cho event cũ; nếu currency trước đây không được xác định, không được tự đoán.

Với JSON Schema, keyword `default` chủ yếu là annotation; validator không nhất thiết tự chèn giá trị default vào payload. Consumer phải tự áp dụng fallback hoặc producer phải gửi giá trị. Đồng thời, schema dùng `additionalProperties: false` có thể từ chối field mới; cân nhắc chính sách này khi cần consumer cũ chấp nhận payload mở rộng.

### Thay đổi thường tương thích và không tương thích

| Thay đổi | Rủi ro | Cách xử lý |
|---|---|---|
| Thêm field optional | Thấp nếu consumer bỏ qua field lạ | Thêm field, kiểm tra parser cũ |
| Thêm field required | Consumer mới có thể không đọc event cũ | Có default có ý nghĩa hoặc phát hành major contract |
| Bỏ field | Consumer cũ có thể vẫn cần field | Giai đoạn deprecate, đo usage rồi mới xóa |
| Đổi tên field | Consumer cũ không tìm thấy field | Dual-write/alias trong giai đoạn chuyển đổi |
| Đổi kiểu field | Parser có thể lỗi hoặc mất độ chính xác | Thêm field mới, migrate dần |
| Đổi đơn vị hoặc ý nghĩa | Schema vẫn hợp lệ nhưng nghiệp vụ sai | Field mới hoặc event type mới; tài liệu semantics |
| Thêm enum value | Consumer có switch không có default có thể lỗi | Consumer phải xử lý unknown value |
| Đổi ordering/delivery semantics | Consumer có thể xử lý sai trạng thái | Contract riêng và kiểm thử behavior |

Compatibility về cấu trúc không đảm bảo compatibility về nghiệp vụ. Ví dụ `totalAmount: 1000` vẫn là integer nhưng nếu trước đây là đồng và sau đó chuyển sang xu, consumer có thể tính sai gấp 100 lần mà không có lỗi parse.

## 3. Quy tắc tiến hóa cho JSON event

JSON linh hoạt và dễ đọc, nhưng mỗi consumer phải xử lý thay đổi schema có chủ đích.

Các nguyên tắc nên áp dụng:

- Thêm field mới dưới dạng optional trước khi yêu cầu consumer sử dụng.
- Consumer bỏ qua field không biết nếu contract cho phép.
- Consumer có fallback rõ ràng cho field thiếu; không suy đoán giá trị.
- Không đổi tên hoặc đổi kiểu field đang được dùng rộng rãi.
- Không tái sử dụng một field cho ý nghĩa mới.
- Không đổi đơn vị mà vẫn giữ nguyên tên field.
- Enum consumer phải có nhánh xử lý giá trị chưa biết.
- Chỉ xóa field sau khi hết thời gian tương thích và xác nhận consumer đã ngừng dùng.
- Giữ fixture event của các schema version cũ để test replay.

### Java consumer chịu được field mới

Với Jackson, có thể cấu hình DTO để bỏ qua property không biết:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlacedV1(
        String orderId,
        String customerId,
        Long totalAmount) {
}
~~~

Consumer có thể đọc event cũ và event mới có thêm field. Tuy nhiên, nếu field bắt buộc bị thiếu hoặc sai kiểu, ứng dụng vẫn cần validate. `ignoreUnknown=true` không giải quyết việc đổi tên field, đổi đơn vị hay field thiếu.

Nếu currency được bổ sung và contract đảm bảo mọi event cũ dùng VND, có thể normalize rõ ràng:

~~~java
public record OrderPlacedPayload(
        String orderId,
        String customerId,
        Long totalAmount,
        String currency) {

    public String effectiveCurrency() {
        return currency == null || currency.isBlank()
                ? "VND"
                : currency;
    }
}
~~~

Fallback này chỉ đúng khi hợp đồng v1 quy định `totalAmount` luôn là VND. Nếu không có bảo đảm đó, consumer nên từ chối event thiếu currency hoặc gửi vào quarantine/DLQ theo chính sách thay vì tự gán.

### Enum và giá trị chưa biết

Một consumer có thể gặp trạng thái mới như `PARTIALLY_REFUNDED` sau khi producer mở rộng enum. Nếu code dùng switch exhaustive hoặc parse enum trực tiếp, message có thể bị lỗi.

Một cách an toàn là giữ giá trị wire dưới dạng String rồi ánh xạ:

~~~java
public enum PaymentStatus {
    PENDING,
    AUTHORIZED,
    CAPTURED,
    REFUNDED,
    UNKNOWN;

    public static PaymentStatus fromWire(String value) {
        if (value == null) {
            return UNKNOWN;
        }
        try {
            return PaymentStatus.valueOf(value);
        } catch (IllegalArgumentException ignored) {
            return UNKNOWN;
        }
    }
}
~~~

Không phải trạng thái lạ nào cũng có thể xử lý như UNKNOWN rồi tiếp tục. Với thao tác thanh toán, consumer có thể cần cách ly event và báo lỗi thay vì mặc định chuyển sang một trạng thái an toàn giả định. Hãy định nghĩa policy cho unknown value theo từng event type.

## 4. Avro và Protobuf: schema có quy tắc tương thích riêng

JSON Schema, Avro và Protobuf không có cùng semantics. Không áp dụng quy tắc của một định dạng cho định dạng khác.

### Avro

Avro dùng writer schema và reader schema để giải quyết dữ liệu khi đọc. Một field mới được thêm vào reader schema thường cần default để reader có thể đọc record được ghi bằng schema cũ không chứa field đó.

Ví dụ thêm currency có default:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
~~~

Default chỉ đúng nếu semantics lịch sử thực sự bảo đảm currency là VND. Avro reader dùng default khi field không có trong writer schema; điều này khác với JSON Schema annotation default.

### Protobuf

Protobuf dùng field number để mã hóa wire format. Quy tắc quan trọng:

- Không thay đổi field number đã phát hành.
- Không tái sử dụng field number đã xóa.
- Dùng `reserved` cho field number/name đã ngừng dùng.
- Tránh thay đổi wire type không tương thích.
- Consumer cần chịu được field chưa biết theo runtime/protobuf version.
- Với enum, giữ giá trị số ổn định và có giá trị UNKNOWN/UNSPECIFIED phù hợp.

Ví dụ:

~~~protobuf
syntax = "proto3";

message OrderPlaced {
  string order_id = 1;
  int64 total_amount = 2;
  string currency = 3;

  reserved 4;
  reserved "legacy_customer_code";
}
~~~

Không tái sử dụng tag 4 cho một field mới, kể cả khi field cũ đã bị xóa khỏi source. Dữ liệu cũ hoặc message replay vẫn có thể chứa tag đó.

### Schema registry

Schema registry có thể lưu nhiều version, kiểm tra compatibility khi đăng ký schema mới và cấp schema ID cho message. Một số hệ sinh thái hỗ trợ Avro, Protobuf và JSON Schema; tính năng và compatibility modes phụ thuộc sản phẩm đang dùng.

Có thể đặt policy như backward, forward, full hoặc transitive variants. Chế độ transitive kiểm tra tương thích với nhiều version trước đó, không chỉ version gần nhất. Chọn mode theo cách consumer nhận và replay message: queue có retention dài hoặc có thể replay dữ liệu lịch sử thường cần kiểm tra nhiều version hơn.

Registry không thay thế test nghiệp vụ. Nó không biết field `totalAmount` đã đổi từ đồng sang xu nếu kiểu vẫn là integer. Contract owner vẫn phải review semantics.

## 5. Version event và schema

Không phải mọi thay đổi đều cần đổi event type. Hãy phân biệt:

- **Event type:** sự kiện nghiệp vụ, ví dụ `order.placed`.
- **Schema version:** cấu trúc payload của event type.
- **Application version:** phiên bản code producer/consumer.
- **Deployment revision:** revision hoặc version được nền tảng chạy.

Một event type có thể tiến hóa từ schema 1 lên schema 2 mà vẫn giữ cùng event type nếu thay đổi tương thích. Khi thay đổi semantics lớn hoặc không thể giữ compatibility, tạo event type mới hoặc major version mới.

Ví dụ:

~~~text
eventType = com.example.order.placed
schemaVersion = 1.0
~~~

Sau khi mở rộng tương thích:

~~~text
eventType = com.example.order.placed
schemaVersion = 1.1
~~~

Nếu ý nghĩa event thay đổi đáng kể, chẳng hạn `OrderPlaced` trước đây phát sau khi đơn được lưu nhưng nay phát trước khi transaction commit, đó là thay đổi semantics. Cần một contract mới hoặc một quy trình migration rõ ràng; chỉ tăng schemaVersion không tự làm thay đổi hành vi an toàn.

Không tạo version cho từng field hoặc từng deployment. Versioning nên giúp consumer biết cách diễn giải event và giữ được khả năng replay.

## 6. Expand-contract: phát hành không làm gián đoạn producer và consumer

Khi producer và consumer được deploy độc lập, cách an toàn thường là **mở rộng trước, thu hẹp sau**.

Giả sử v1 có `customerName`, và muốn chuyển sang `customerDisplayName`.

Không nên đổi producer ngay để chỉ gửi field mới vì consumer cũ vẫn cần `customerName`. Hãy dùng nhiều giai đoạn.

~~~mermaid
flowchart TD
    A["1. Expand consumer"] --> B["2. Deploy tolerant consumers"]
    B --> C["3. Producer dual-writes old + new fields"]
    C --> D["4. Observe usage and migrate consumers"]
    D --> E["5. Producer stops old field"]
    E --> F["6. Contract: remove old field after retention window"]
~~~

### Giai đoạn 1: mở rộng consumer

Consumer mới đọc được cả field cũ lẫn field mới. Nếu field mới thiếu, consumer dùng field cũ theo quy tắc tương thích đã định. Chưa thay producer.

### Giai đoạn 2: triển khai consumer tolerant

Triển khai các consumer có khả năng đọc cả hai dạng. Nếu nhiều team sở hữu consumer, cần xác nhận tất cả consumer đang active, bao gồm consumer chạy theo lịch và consumer có thể replay DLQ.

### Giai đoạn 3: producer dual-write

Producer gửi cả `customerName` và `customerDisplayName`, với giá trị nhất quán. Giữ semantics rõ ràng nếu hai field không hoàn toàn tương đương.

~~~json
{
  "customerName": "Nguyen An",
  "customerDisplayName": "An Nguyen"
}
~~~

Không dual-write hai field nếu chúng có ý nghĩa khác nhau mà consumer cũ có thể hiểu sai. Trong trường hợp đó, tạo event type/version mới hoặc mapping adapter riêng.

### Giai đoạn 4: migrate và quan sát consumer

Cập nhật consumer để dùng field mới. Theo dõi version/schema metrics, parse failures, DLQ và số lượng consumer còn đọc field cũ. Log usage cần tránh chứa dữ liệu cá nhân; metric chỉ nên đếm theo consumer/version, không gắn tên người dùng.

### Giai đoạn 5: ngừng phát field cũ

Chỉ ngừng field cũ khi:

- Tất cả consumer đang chạy đã được nâng cấp.
- Queue/topic không còn message cũ cần xử lý, hoặc consumer mới vẫn đọc được chúng.
- DLQ và replay store đã được xử lý.
- Các consumer theo lịch hoặc ít hoạt động đã được xác nhận.
- Rollback window và retention window đã được thống nhất.

### Giai đoạn 6: contract

Sau thời gian tương thích, producer có thể xóa field cũ và consumer có thể xóa nhánh fallback. Xóa field khỏi schema registry chỉ khi chính sách registry và nhu cầu replay cho phép; không xóa schema version lịch sử đang cần để đọc message cũ.

## 7. Thứ tự deploy producer và consumer

Thứ tự triển khai phụ thuộc hướng tương thích.

| Thay đổi | Thứ tự thường an toàn | Điều kiện |
|---|---|---|
| Thêm optional field, consumer cũ bỏ qua unknown | Producer có thể deploy trước hoặc consumer trước | Parser cũ phải chấp nhận field mới |
| Consumer bắt đầu dùng field mới | Consumer tolerant deploy trước, sau đó producer gửi field | Consumer có fallback khi field chưa xuất hiện |
| Đổi tên field | Consumer hỗ trợ cả tên cũ/mới trước, producer dual-write sau | Có giai đoạn quan sát và rollback |
| Xóa field cũ | Consumer ngừng phụ thuộc trước, producer ngừng gửi sau | Không còn message cũ cần field đó hoặc consumer đọc được |
| Đổi kiểu/ý nghĩa không tương thích | Tạo contract mới, triển khai consumer mới trước producer mới | Có route/topic/version tách biệt và kế hoạch migration |
| Thay đổi semantics ordering | Consumer và hạ tầng được chuẩn bị trước | Có partition key, ordering và replay policy rõ |

Không có thứ tự deploy duy nhất đúng cho mọi thay đổi. Trước rollout phải xác định tổ hợp producer/consumer nào có thể cùng tồn tại: producer cũ với consumer mới, producer mới với consumer cũ, và consumer mới đọc message cũ còn tồn trong queue.

### Ma trận tương thích khi rollout

| Producer | Consumer cũ | Consumer mới |
|---|---|---|
| Producer cũ | Tổ hợp hiện tại | Consumer mới phải đọc schema cũ |
| Producer mới | Consumer cũ phải đọc schema mới hoặc producer giữ field cũ | Tổ hợp mục tiêu |
| Replay message cũ | Consumer cũ có thể đọc | Consumer mới phải hỗ trợ lịch sử trong retention/replay window |

Nếu producer mới phát message không tương thích với consumer cũ và không thể deploy consumer trước, hãy dùng topic/queue/event type version mới để cô lập luồng. Không đưa event không tương thích vào cùng queue mà không có consumer có thể xử lý.

## 8. Java producer: phát event từ contract đã định nghĩa

Producer nên tạo event DTO rõ ràng và serialize qua adapter. Không gửi trực tiếp entity JPA hoặc object nội bộ vì thay đổi database model có thể vô tình làm đổi event contract.

Ví dụ DTO:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
        String eventId,
        String eventType,
        String schemaVersion,
        String source,
        Instant occurredAt,
        T data) {
}

public record OrderPlacedV2(
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {
}
~~~

Tạo event ở application boundary:

~~~java
import java.time.Clock;

public final class OrderEventFactory {
    private final Clock clock;
    private final EventIdGenerator eventIds;

    public OrderEventFactory(Clock clock, EventIdGenerator eventIds) {
        this.clock = clock;
        this.eventIds = eventIds;
    }

    public EventEnvelope<OrderPlacedV2> placed(
            String orderId,
            String customerId,
            long totalAmount) {

        return new EventEnvelope<>(
                eventIds.nextId(),
                "com.example.order.placed",
                "2.0",
                "orders-api",
                clock.instant(),
                new OrderPlacedV2(
                        orderId,
                        customerId,
                        totalAmount,
                        "VND"));
    }
}

public interface EventIdGenerator {
    String nextId();
}
~~~

Trong production, inject một ID generator phù hợp (ví dụ UUID) và tạo ID đúng một lần khi ghi event vào outbox cùng business transaction. Worker retry publish phải đọc lại và gửi cùng event đã lưu, không gọi generator để tạo ID mới. Consumer vẫn phải idempotent vì broker có thể giao lặp. Currency ở ví dụ được cố định là VND chỉ vì contract minh họa quy định như vậy; hệ thống đa tiền tệ phải lấy currency từ dữ liệu nghiệp vụ.

### Outbox giữ event nhất quán với database

Nếu producer ghi order vào database rồi publish event trực tiếp, có thể xảy ra hai tình huống: database commit nhưng publish thất bại, hoặc publish thành công nhưng transaction database rollback. Transactional outbox ghi business record và event vào cùng transaction; worker publish outbox sau đó.

Khi worker retry publish, nó gửi lại cùng event ID. Consumer vẫn phải idempotent vì broker có thể giao lặp. Outbox không tự tạo exactly-once end-to-end.

## 9. Java consumer: đọc nhiều schema version an toàn

Consumer nên có một lớp adapter deserialize event và normalize về command nội bộ. Business logic không cần biết field cũ hay mới được truyền qua wire.

Ví dụ payload có thể nhận cả `customerName` và `customerDisplayName` trong giai đoạn migration:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerData(
        String customerName,
        @JsonProperty("customerDisplayName")
        String customerDisplayName) {

    public String effectiveDisplayName() {
        if (customerDisplayName != null
                && !customerDisplayName.isBlank()) {
            return customerDisplayName;
        }
        if (customerName != null && !customerName.isBlank()) {
            return customerName;
        }
        throw new IllegalArgumentException(
                "event has no customer display name");
    }
}
~~~

Nếu cần hỗ trợ cả hai JSON property mapping vào cùng một logical property, có thể dùng `@JsonAlias` hoặc custom deserializer; hãy chọn cách không làm hai field xung đột. Ví dụ trên giữ hai property riêng để ưu tiên field mới một cách tường minh.

Sau khi consumer mới đã được triển khai và producer dual-write, consumer có thể dùng `effectiveDisplayName()`. Chỉ xóa fallback sau khi không còn message cũ trong queue, DLQ hoặc archive có thể replay.

### Normalize wire event sang command

~~~java
public record NotifyCustomerCommand(
        String orderId,
        String customerDisplayName) {
}

public final class OrderEventMapper {
    public NotifyCustomerCommand toCommand(
            OrderPlacedPayload payload,
            CustomerData customer) {
        if (payload.orderId() == null || payload.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return new NotifyCustomerCommand(
                payload.orderId(),
                customer.effectiveDisplayName());
    }
}
~~~

Mapper chịu trách nhiệm validate field bắt buộc và chuyển schema cũ/mới thành một mô hình nội bộ ổn định. Nếu không thể normalize một event cũ vì thiếu dữ liệu thiết yếu, hãy cách ly message và báo lỗi có thể điều tra; đừng tự điền giá trị nghiệp vụ không có căn cứ.

## 10. Contract test giữa producer và consumer

Unit test producer chứng minh code tạo object đúng. Unit test consumer chứng minh consumer xử lý object đúng. Nhưng hai test riêng có thể cùng pass trong khi JSON thực tế không khớp, ví dụ producer đổi tên field mà consumer không nhận ra.

Contract test kiểm tra sự tương thích tại ranh giới serialization.

### Producer contract test

- Serialize event từ producer.
- Kiểm tra event type, schema version và field bắt buộc.
- Validate payload bằng schema đã đăng ký.
- Kiểm tra event ID ổn định qua retry/outbox.
- So sánh với golden fixture hoặc schema compatibility rule.

Ví dụ JUnit với Jackson:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderEventSerializationTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .findAndRegisterModules();

    @Test
    void writesThePublishedContract() throws Exception {
        var event = new EventEnvelope<>(
                "evt-100",
                "com.example.order.placed",
                "2.0",
                "orders-api",
                java.time.Instant.parse("2026-11-17T10:00:00Z"),
                new OrderPlacedV2(
                        "ord-1", "cus-1", 1250000L, "VND"));

        String json = mapper.writeValueAsString(event);

        assertTrue(json.contains("\"eventType\":\"com.example.order.placed\""));
        assertTrue(json.contains("\"schemaVersion\":\"2.0\""));
        assertTrue(json.contains("\"currency\":\"VND\""));
    }
}
~~~

Trong project thật, nên parse JSON thành tree hoặc validate bằng JSON Schema thay vì chỉ dùng `contains` cho mọi assertion. Cần kiểm tra field type, required properties và schema ID/version.

### Consumer compatibility test với fixture lịch sử

Giữ payload mẫu của các schema version đang còn trong retention/replay window:

~~~text
src/test/resources/events/
  order-placed-v1.json
  order-placed-v2.json
  order-placed-unknown-enum.json
  order-placed-missing-required-field.json
~~~

Consumer test nên xác minh:

- Event v1 được đọc và normalize đúng.
- Event v2 có field mới được đọc đúng.
- Field không biết không làm parser lỗi nếu contract cho phép.
- Field bắt buộc bị thiếu được phân loại là invalid.
- Enum mới được xử lý theo policy.
- Event type/schema version không hỗ trợ được quarantine hoặc reject theo chính sách.

Golden fixture phải được quản lý cùng contract. Khi producer thay đổi, không sửa fixture cũ để khiến test pass; thêm fixture mới và giữ dữ liệu lịch sử cần thiết.

### Consumer-driven contract

Với nhiều consumer độc lập, mỗi consumer có thể công bố các field và semantics mà nó phụ thuộc. Producer kiểm tra thay đổi mới không phá các contract đó trước khi release.

Cách này hữu ích khi producer không biết hết tất cả consumer. Tuy nhiên, consumer-driven contract không thay thế schema registry và không tự kiểm tra delivery, ordering hoặc business side effects.

## 11. Schema compatibility trong CI/CD

Pipeline nên kiểm tra schema trước khi build/publish artifact hoặc deploy producer.

~~~mermaid
flowchart TD
    A["Pull request: code + schema"] --> B["Lint / validate schema"]
    B --> C["Compatibility check against registry/history"]
    C --> D["Compile and unit tests"]
    D --> E["Producer serialization tests"]
    E --> F["Consumer tests with old/new fixtures"]
    F --> G["Contract / integration tests"]
    G --> H["Deploy tolerant consumers"]
    H --> I["Deploy producer canary"]
    I --> J["Observe errors, DLQ and business metrics"]
    J --> K{"Stable?"}
    K -->|Yes| L["Promote rollout"]
    K -->|No| M["Rollback producer or route to old contract"]
~~~

Các bước kiểm tra:

1. **Schema lint:** kiểm tra syntax, naming, required/optional, description và reserved fields.
2. **Compatibility check:** so schema mới với schema hiện tại và các version lịch sử theo policy.
3. **Compile/code generation:** sinh Java classes từ Avro/Protobuf nếu dự án dùng schema-first.
4. **Producer tests:** kiểm tra serialized event đúng contract.
5. **Consumer fixture tests:** đọc tất cả schema versions còn cần hỗ trợ.
6. **Contract tests:** xác minh producer output tương thích consumer expectations.
7. **Integration tests:** xác minh broker, auth, serialization, retry và DLQ.
8. **Deployment gate:** chỉ promote khi consumer tolerant đã sẵn sàng.
9. **Post-deploy verification:** theo dõi parse error, unknown event, retry, DLQ và business outcome.

Không cho phép CI chỉ validate schema mới với chính nó. Cần so với version đã publish và những version còn được dùng/replay.

### Schema registry trong pipeline

Nếu dùng schema registry, pipeline có thể gọi compatibility endpoint hoặc lệnh tương ứng để đăng ký schema mới. Registry cần được cấu hình policy phù hợp cho từng subject/event type. Không giả định mọi registry có cùng command, authentication hoặc compatibility semantics; dùng công cụ chính thức của nền tảng đang vận hành.

Schema registry nên là nguồn lịch sử contract, nhưng schema file vẫn cần version control trong repository để review và tái tạo build. Ghi schema ID/version vào metadata event hoặc message header theo quy ước của serializer/registry.

## 12. Canary, rollout và rollback

Sau khi contract đã tương thích, vẫn cần phát hành theo từng bước vì code mới có thể có bug nghiệp vụ.

Một rollout có thể:

1. Deploy consumer mới nhưng vẫn hỗ trợ event cũ.
2. Xác minh consumer mới đọc được message đang có trong queue.
3. Deploy producer mới với dual-write hoặc optional field.
4. Chuyển một phần producer traffic sang revision mới nếu nền tảng hỗ trợ.
5. Theo dõi deserialization error, consumer failure, DLQ, latency và kết quả nghiệp vụ.
6. Tăng dần tỷ lệ producer mới.
7. Chỉ contract field cũ sau thời gian tương thích và khi rollback window đóng.

### Rollback không chỉ là quay code

Nếu producer mới đã phát event v2 vào queue, rollback producer về code v1 không xóa những message v2 đã được publish. Consumer v1 có thể tiếp tục nhận chúng và thất bại.

Kế hoạch rollback phải trả lời:

- Consumer cũ có đọc được event mới không?
- Nếu không, có thể rollback consumer hay phải giữ consumer mới?
- Có cần route event v2 sang queue riêng?
- Message đã vào DLQ có thể replay bằng consumer version nào?
- Schema version cũ có còn được registry giữ lại không?
- Side effect đã xảy ra có cần compensation không?

Với thay đổi không tương thích, triển khai consumer hỗ trợ cả v1/v2 trước khi producer phát v2. Nếu không thể, dùng event type/topic version mới và chạy consumer v2 song song.

### Dual-read và dual-write

- **Dual-read:** consumer đọc cả field cũ và mới trong thời gian chuyển đổi.
- **Dual-write:** producer phát cả field cũ và mới.
- **Backfill/replay:** chuyển đổi dữ liệu/event lịch sử khi cần.
- **Contract:** xóa field hoặc route cũ sau khi mọi consumer đã chuyển.

Không duy trì dual-read/dual-write mãi mãi. Đặt thời hạn, owner và metric chứng minh khi nào có thể kết thúc migration.

## 13. Queue retention, retry, DLQ và replay

Schema compatibility phải tính đến message đã được lưu trước khi deployment. Một consumer mới có thể nhận event cũ sau nhiều ngày; một message trong DLQ có thể được replay sau khi đã triển khai nhiều revision mới.

Cần xác định:

- Queue/topic retention tối đa.
- Retry window và số lần giao lại.
- DLQ retention và quyền replay.
- Event archive hoặc object storage chứa payload lịch sử.
- Schema versions còn được hỗ trợ.
- Consumer version được dùng khi replay.
- Cách xử lý event không thể parse hoặc không còn semantics phù hợp.

Không xóa schema v1 ngay sau khi producer chuyển v2 nếu queue hoặc archive vẫn có event v1. Nếu replay event cũ vào consumer mới, consumer phải có compatibility test cho payload đó.

### Poison message

Một poison message là message luôn thất bại do payload sai, schema không hỗ trợ hoặc dữ liệu nghiệp vụ bất thường. Retry vô hạn có thể làm tắc queue hoặc tạo chi phí.

- Phân loại lỗi parse/schema và lỗi tạm thời.
- Giới hạn retry theo cấu hình trigger.
- Đưa message không thể xử lý vào DLQ/quarantine.
- Ghi event ID, schema version, error category và correlation ID; không log secret hoặc payload nhạy cảm.
- Sửa consumer hoặc mapping, rồi replay có kiểm soát.
- Giữ nguyên event ID khi replay để idempotency tiếp tục hoạt động.

Replay không có nghĩa là bỏ qua idempotency. Nếu side effect đã thành công trước khi consumer timeout, replay phải không tạo side effect lần thứ hai.

## 14. Ordering và semantics của event

Một schema có thể hoàn toàn tương thích nhưng consumer vẫn xử lý sai nếu thứ tự event thay đổi.

Ví dụ:

~~~text
OrderCreated -> PaymentAuthorized -> OrderCancelled
~~~

Nếu consumer nhận `OrderCancelled` trước `PaymentAuthorized`, nó cần quy tắc xử lý trạng thái rõ ràng. Không được giả định mọi queue/event bus đều bảo đảm ordering toàn cục.

Các câu hỏi cần ghi trong contract:

- Ordering được bảo đảm theo toàn queue, partition key hay không được bảo đảm?
- Event có thể duplicate không?
- Consumer có thể nhận event trễ không?
- Có sequence/version theo aggregate không?
- Event nào có thể được xử lý song song?
- Consumer xử lý event cũ hơn trạng thái hiện tại ra sao?
- Có cần partition theo orderId hoặc aggregateId không?

Có thể đưa aggregate version/sequence vào payload để consumer phát hiện event cũ hoặc bỏ sót event:

~~~json
{
  "orderId": "ord-1042",
  "aggregateVersion": 7,
  "status": "CONFIRMED"
}
~~~

Consumer có thể so sánh version với trạng thái đã lưu và quyết định bỏ qua, retry hoặc điều tra gap. Cần định nghĩa rõ semantics của version: tăng cho mọi thay đổi aggregate hay chỉ cho event phát ra.

## 15. Idempotency và event identity

Hệ thống event thường có delivery at-least-once hoặc có retry ở nhiều tầng. Consumer nên coi duplicate là khả năng bình thường.

Mẫu xử lý:

1. Nhận event và lấy event ID ổn định.
2. Thử claim event ID trong kho idempotency bằng unique constraint/conditional write.
3. Nếu event đã xử lý thành công, trả acknowledgement theo contract.
4. Nếu claim thành công, thực hiện nghiệp vụ và lưu kết quả trong transaction phù hợp.
5. Nếu xử lý thất bại, giữ trạng thái cho retry/lease recovery theo thiết kế.
6. Không đánh dấu hoàn tất trước khi side effect được commit.

Không dùng request ID do broker tạo mới cho mỗi lần delivery làm idempotency key nếu nó thay đổi giữa các lần retry. Dùng event ID do producer tạo và lưu bền vững.

Với consumer phát event tiếp theo, có thể dùng transactional outbox để commit business state và event mới cùng transaction. Đây là cách giảm khoảng trống giữa cập nhật database và publish message.

## 16. Quan sát compatibility trong production

Không chỉ theo dõi HTTP 5xx. Với consumer, các chỉ số quan trọng gồm:

| Metric/log | Điều cần biết |
|---|---|
| Messages received theo event type/schema version | Consumer đang nhận những contract nào |
| Deserialization/schema validation failures | Payload nào không đọc được |
| Unknown enum/value count | Producer đã phát giá trị mới chưa |
| Retry count và delivery attempt | Consumer có lỗi lặp không |
| DLQ depth/age | Message lỗi có đang tích tụ không |
| Processing latency | Consumer có chậm sau thay đổi không |
| Duplicate/idempotency hit | Delivery lặp hoặc producer retry ra sao |
| Business completion/failure | Event có tạo kết quả nghiệp vụ đúng không |

Dùng metric label có cardinality thấp như event type, schema major, consumer name và outcome. Không đưa event ID, order ID hoặc customer ID vào metric label; những giá trị đó phù hợp hơn trong log có kiểm soát hoặc trace.

Khi rollout, so sánh consumer v1/v2 và producer revision theo cùng time window. Có thể giữ một metric `schema_compatibility_failure_total` hoặc log event có cấu trúc để phát hiện sớm vấn đề.

## 17. Checklist phát hành producer/consumer

- [ ] Mỗi event type có owner, purpose, schema và semantics rõ ràng.
- [ ] Envelope có event ID ổn định, event type, schema version, source và occurred time.
- [ ] Schema version không bị nhầm với application/revision version.
- [ ] Backward/forward/full compatibility được xác định theo đúng registry/tool.
- [ ] Field mới được thêm optional trước khi consumer yêu cầu.
- [ ] Consumer bỏ qua field mới hoặc có policy xử lý unknown field.
- [ ] Field thiếu có fallback chỉ khi semantics lịch sử bảo đảm giá trị đó.
- [ ] Không đổi tên, kiểu, đơn vị hoặc ý nghĩa field mà không có migration.
- [ ] Enum consumer xử lý unknown value theo policy.
- [ ] Avro default và Protobuf field number/reserved rules được tuân thủ.
- [ ] Schema mới được kiểm tra với version hiện tại và các version còn replay.
- [ ] Consumer tolerant được deploy trước producer breaking/expanded output.
- [ ] Producer dual-write chỉ trong thời gian migration có owner và deadline.
- [ ] Queue retention, DLQ, archive và replay window đã được tính đến.
- [ ] Consumer có idempotency và xử lý duplicate/out-of-order theo contract.
- [ ] CI chạy producer serialization, consumer fixture và contract tests.
- [ ] Canary có metric cho parse error, retry, DLQ và business outcome.
- [ ] Rollback plan xét message mới đã nằm trong queue, không chỉ code revision.
- [ ] Schema cũ chỉ bị retire sau khi hết nhu cầu đọc/replay và rollback window.

## Tự kiểm tra

1. Event contract gồm những thành phần nào ngoài JSON payload?
2. Backward compatibility và forward compatibility khác nhau thế nào theo góc nhìn reader?
3. Vì sao thêm field optional thường an toàn hơn thêm field required?
4. JSON Schema `default` có tự động chèn giá trị vào payload không?
5. Avro reader default khác JSON Schema default như thế nào?
6. Vì sao Protobuf không được tái sử dụng field number đã xóa?
7. Expand-contract yêu cầu thứ tự thay đổi consumer và producer ra sao?
8. Vì sao rollback producer không loại bỏ event v2 đã nằm trong queue?
9. Schema tương thích có đảm bảo ordering và semantics nghiệp vụ không?
10. Event ID phải được giữ như thế nào qua retry/replay để consumer idempotent?

Producer và consumer được phát hành an toàn khi contract có owner, schema được version hóa và mỗi thay đổi được kiểm tra theo khả năng đọc dữ liệu cũ/mới. Expand-contract cho phép consumer trở nên tolerant trước khi producer thay đổi payload; contract test và schema registry phát hiện lỗi cấu trúc trong CI; còn retry, DLQ, replay và idempotency bảo vệ quá trình vận hành sau deployment. Luôn kiểm tra semantics, ordering và side effect cùng schema vì một event parse thành công vẫn có thể làm sai nghiệp vụ.

