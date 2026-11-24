# Tương thích hợp đồng khi triển khai producer và consumer lệch thời điểm

Trong một hệ thống event-driven, producer và consumer thường được triển khai ở những thời điểm khác nhau. Một phiên bản consumer mới có thể đã chạy trong khi producer vẫn phát schema cũ; sau đó producer mới bắt đầu phát schema mới trong lúc một số instance consumer cũ vẫn còn hoạt động. Nếu thay đổi payload không được thiết kế cho giai đoạn chồng lấn này, message có thể không deserialize được, bị đưa vào retry/DLQ hoặc làm hỏng xử lý nghiệp vụ.

Tương thích hợp đồng là khả năng các phiên bản producer và consumer khác nhau vẫn trao đổi message đúng trong suốt vòng đời triển khai, rollback và replay. Điều cần kiểm tra là cặp writer/reader schema thực tế, serializer/deserializer, content type, headers và ý nghĩa nghiệp vụ của từng field. Một schema được registry chấp nhận chưa đủ để chứng minh ứng dụng xử lý đúng.

Bài học này trình bày cách chọn compatibility mode, áp dụng expand-contract, triển khai consumer và producer theo thứ tự phù hợp, dùng Schema Registry trong Spring Cloud Stream, kiểm thử các cặp phiên bản và xử lý thay đổi phá vỡ tương thích bằng topic migration.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao producer và consumer có thể chạy đồng thời nhiều phiên bản.
- Phân biệt wire contract, Java DTO, content type và schema registry.
- Hiểu backward, forward, full và transitive compatibility.
- Chọn thứ tự triển khai consumer/producer theo compatibility mode.
- Áp dụng expand-contract cho việc thêm, đổi và loại bỏ field.
- Thiết kế schema Avro, JSON và Protobuf có khả năng tiến hóa.
- Dùng Spring Cloud Stream Schema Registry và Avro message converter.
- Phân biệt schema registry với native schema của broker.
- Kiểm thử producer/consumer theo ma trận phiên bản và dữ liệu lịch sử.
- Lập kế hoạch rolling deployment, rollback, replay và migration khi thay đổi không tương thích.

## 1. Vì sao producer và consumer lệch phiên bản?

Spring Cloud Stream chuẩn hóa mô hình lập trình bằng Supplier, Function, Consumer và binding. Binder chuyển message giữa ứng dụng và broker. Tuy nhiên, binder không làm cho payload tự động tương thích giữa mọi phiên bản ứng dụng.

Giả sử producer orders phát sự kiện OrderCreated và consumer billing đọc sự kiện đó. Khi nâng cấp, có thể tồn tại đồng thời:

- Producer v1 và producer v2.
- Consumer v1 và consumer v2.
- Message được ghi từ nhiều thời điểm và nhiều schema version.
- Message cũ còn nằm trong retention, backlog hoặc DLQ.
- Consumer mới đọc lại dữ liệu lịch sử sau khi deploy.
- Consumer rollback về bản cũ trong khi producer đã phát dữ liệu mới.

~~~mermaid
flowchart TD
    P1["Producer v1"] -->|Schema v1| B["Broker topic / queue"]
    P2["Producer v2"] -->|Schema v2| B
    B --> G["Consumer group<br/>one message to one member"]
    G --> C1["Instance v1"]
    G --> C2["Instance v2"]
    C1 --> D["Database / downstream"]
    C2 --> D
    B --> R["Replay / DLQ recovery"]
    R --> C1
    R --> C2
~~~

Với cùng một consumer group, các instance v1 và v2 thường cùng chia sẻ message. Broker không tự chọn instance dựa trên schema version. Trong thời gian rolling update, một message có thể đến bất kỳ instance nào đang tham gia group. Vì vậy, mọi instance còn hoạt động phải đọc được các message producer hiện tại đang phát.

Nếu hai consumer group khác nhau, mỗi group có thể nhận một bản sao độc lập của message. Khi đó, cả hai nhóm cần hợp đồng tương thích riêng và có thể tạo side effect trùng nếu cùng ghi vào một hệ thống đích.

## 2. Hợp đồng message gồm những gì?

Không nên xem hợp đồng chỉ là một class Java. Một message contract có nhiều lớp:

| Thành phần | Nội dung | Ví dụ |
|---|---|---|
| Event identity | Tên và ý nghĩa sự kiện | OrderCreated |
| Payload schema | Field, type, optional/default | orderId, totalMinor, currency |
| Serialization | Cách biến object thành bytes | JSON, Avro, Protobuf |
| Content type | Gợi ý MessageConverter cần dùng | application/json |
| Schema reference | Subject, version hoặc schema ID | orders-value v4 |
| Headers | Metadata vận chuyển | eventId, correlationId, traceparent |
| Key | Định tuyến, ordering hoặc partition | orderId |
| Semantics | Ý nghĩa nghiệp vụ của field | totalMinor luôn là số tiền theo đơn vị nhỏ nhất |

Một thay đổi có thể tương thích về cấu trúc nhưng phá vỡ semantics. Ví dụ, total vẫn là long nhưng producer đổi đơn vị từ đồng sang xu. Schema registry có thể coi kiểu dữ liệu không đổi, trong khi consumer tính tiền sai gấp 100 lần.

Hợp đồng nên ghi rõ:
- Tên event và mục đích nghiệp vụ.
- Ý nghĩa, đơn vị, timezone và miền giá trị của field.
- Field bắt buộc, optional, nullable và default.
- Quy tắc enum và giá trị chưa biết.
- Key, ordering và partitioning semantics.
- Cách xử lý field chưa biết hoặc schema version mới.
- Chính sách deprecation và thời gian hỗ trợ phiên bản cũ.

### Java DTO không phải wire contract

Hai service có thể dùng class Java khác package, tên và cấu trúc nội bộ nhưng vẫn trao đổi được nếu bytes và schema tương thích. Ngược lại, hai service cùng khai báo class tên OrderCreated nhưng serialize khác format hoặc khác ý nghĩa field vẫn không tương thích.

Không chia sẻ một thư viện DTO rồi cho rằng điều đó tự giải quyết versioning. Shared library có thể khiến các service buộc phải deploy cùng lúc hoặc vô tình kéo theo dependency version không đồng nhất. Hợp đồng wire cần được quản lý và kiểm thử độc lập với cách mỗi service tổ chức code.

## 3. Content type và schema registry trong Spring Cloud Stream

Spring Cloud Stream biểu diễn dữ liệu dưới dạng Spring Message. Framework dùng MessageConverter để chuyển payload giữa kiểu ứng dụng và wire format. contentType có thể đến từ message header, binding property hoặc giá trị mặc định application/json.

Ví dụ một binding JSON:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          group: billing
          content-type: application/json
~~~

content-type giúp framework chọn converter. Nó không tự kiểm tra mọi message có tuân theo một JSON Schema nghiệp vụ hay không. Nếu consumer DTO dùng cấu hình Jackson strict và nhận field lạ, deserialization có thể thất bại dù JSON hợp lệ.

Cần phân biệt:
- Content type: chọn cách chuyển đổi message.
- Schema: mô tả cấu trúc dữ liệu.
- Schema registry: lưu và tra cứu schema version, có thể thực hiện compatibility check.
- Broker-native schema: cơ chế schema do broker cung cấp, có semantics riêng.

### Native encoding/decoding

Khi bật useNativeEncoding hoặc useNativeDecoding, serialization/deserialization được giao cho client library của binder. Lúc đó, framework không dùng content-type để marshalling payload theo cách thông thường. Producer serializer và consumer deserializer phải được cấu hình tương thích. Với native encoding/decoding, headerMode=embeddedHeaders cũng bị bỏ qua.

Đừng thay đổi giữa framework conversion và native serialization trong một rolling deployment mà không kiểm tra wire bytes và header behavior. Hai ứng dụng có thể dùng cùng Java DTO nhưng tạo ra payload khác nhau.

## 4. Backward, forward và full compatibility

Các compatibility mode mô tả quan hệ giữa schema writer của producer và schema reader của consumer.

| Mode | Quan hệ | Khi nào phù hợp |
|---|---|---|
| BACKWARD | Reader schema mới đọc được dữ liệu ghi bằng schema cũ | Ưu tiên consumer mới đọc được lịch sử |
| FORWARD | Reader schema cũ đọc được dữ liệu ghi bằng schema mới | Cần producer mới chạy cùng consumer cũ |
| FULL | Tương thích cả hai chiều giữa hai schema liền kề | Producer và consumer có thể nâng cấp độc lập |
| BACKWARD_TRANSITIVE | Schema mới đọc được dữ liệu từ tất cả schema cũ | Consumer có thể replay toàn bộ lịch sử |
| FORWARD_TRANSITIVE | Consumer cũ đọc được dữ liệu từ mọi schema mới hơn | Cần giữ reader cũ tương thích với nhiều thế hệ writer |
| FULL_TRANSITIVE | Hai chiều tương thích với toàn bộ lịch sử schema | Hệ thống cần rollback/replay qua nhiều thế hệ |
| NONE | Không kiểm tra compatibility | Chỉ dùng trong quy trình migration có kiểm soát |

**Backward compatibility:** consumer dùng schema mới đọc được message cũ. Nó không đảm bảo consumer cũ đọc được message mới.

**Forward compatibility:** consumer dùng schema cũ đọc được message mới. Nó không đảm bảo consumer mới đọc được message cũ.

**Full compatibility:** cả hai hướng đều được bảo đảm giữa hai schema được kiểm tra. FULL thông thường chỉ so với phiên bản gần nhất; FULL_TRANSITIVE kiểm tra với toàn bộ schema lịch sử.

Confluent Schema Registry mặc định dùng BACKWARD không transitive. Vì vậy, khi hệ thống cần replay từ đầu topic, phải đánh giá BACKWARD_TRANSITIVE thay vì giả định compatibility với schema liền trước đồng nghĩa tương thích toàn bộ lịch sử.

### Thứ tự triển khai theo compatibility mode

| Compatibility | Thứ tự triển khai an toàn | Lý do |
|---|---|---|
| BACKWARD | Consumer mới trước, producer mới sau | Consumer cũ không được đảm bảo đọc schema mới |
| FORWARD | Producer mới trước; chờ dữ liệu cũ được drain/hết retention; consumer mới sau | Consumer mới không được đảm bảo đọc schema cũ |
| FULL | Có thể nâng producer và consumer độc lập theo cặp phiên bản đã kiểm tra | Cả reader cũ và mới đọc được writer cũ và mới ở phạm vi policy |
| NONE | Cần migration/maintenance window được điều phối | Không có bảo đảm từ registry |

Thứ tự trên là quy tắc theo schema compatibility. Khi rolling deployment, vẫn cần tính đến instance cũ còn sống, consumer group membership, backlog và message trong DLQ.

### Non-transitive và transitive

Giả sử có schema v1, v2 và v3:

- BACKWARD chỉ kiểm tra v3 với v2.
- BACKWARD_TRANSITIVE kiểm tra v3 với cả v2 và v1.
- Một chuỗi thay đổi có thể tương thích từng bước nhưng v3 vẫn không đọc được dữ liệu v1.

Transitive rất quan trọng khi topic giữ dữ liệu lâu, consumer có thể reset offset hoặc DLQ có thể được replay sau nhiều tháng.

## 5. Quy tắc expand-contract

Expand-contract là cách thay đổi hợp đồng qua nhiều lần triển khai để giữ tương thích trong giai đoạn các service lệch thời điểm.

Quy trình gồm hai pha:

- **Expand:** mở rộng schema và code để chấp nhận cả dữ liệu cũ lẫn mới.
- **Contract:** chỉ loại bỏ cấu trúc cũ sau khi tất cả producer/consumer đã chuyển và dữ liệu cũ không còn cần xử lý.

Ví dụ cần thêm currency vào sự kiện OrderCreated.

### Giai đoạn 1: Schema v1

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "totalMinor": 125500
}
~~~

Consumer v1 chỉ biết eventId, orderId, totalMinor.

### Giai đoạn 2: Mở rộng consumer

Deploy consumer v2 có thể xử lý message thiếu currency. Trong giai đoạn này, producer vẫn phát schema v1. Consumer v1 và v2 có thể cùng tham gia group; cả hai đều đọc được message cũ.

Ví dụ Java DTO mới:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    long totalMinor,
    String currency
) {
    String resolvedCurrency() {
        return currency == null ? "VND" : currency;
    }
}
~~~

Giá trị mặc định phải phản ánh hợp đồng nghiệp vụ thật. Không dùng một default tùy tiện để che giấu dữ liệu thiếu hoặc sai đơn vị. Không tự giả định mọi currency có cùng số chữ số thập phân; quy tắc quy đổi minor unit phải thuộc contract nghiệp vụ riêng.

### Giai đoạn 3: Nâng producer

Sau khi tất cả consumer cũ đã rời group và consumer v2 đã sẵn sàng, producer v2 bắt đầu phát currency.

~~~json
{
  "eventId": "evt-1002",
  "orderId": "ORD-1002",
  "totalMinor": 125500,
  "currency": "VND"
}
~~~

Consumer v2 đọc được cả message cũ không có currency và message mới có currency. Nếu còn consumer v1, message mới có thể đến consumer đó và gây lỗi nếu nó strict với field lạ. Do đó, không bật producer v2 khi consumer v1 vẫn đang hoạt động trừ khi đã xác minh consumer v1 bỏ qua field lạ.

### Giai đoạn 4: Thu hẹp hợp đồng

Sau khi:
- Tất cả producer đã phát field mới.
- Tất cả consumer đã đọc field mới.
- Backlog và DLQ cũ đã được xử lý hoặc có chiến lược replay.
- Hết cửa sổ retention cần hỗ trợ schema cũ.
- Không còn service nào đọc field cũ.

Khi đó mới xem xét bỏ field cũ hoặc thay đổi schema theo một bước migration riêng. Nếu cần đổi nghĩa hoặc kiểu dữ liệu, hãy thêm field mới, chuyển dần producer/consumer rồi mới loại bỏ field cũ.

~~~mermaid
sequenceDiagram
    participant C1 as Consumer v1
    participant C2 as Consumer v2
    participant P1 as Producer v1
    participant P2 as Producer v2
    participant B as Broker
    P1->>B: Event schema v1
    alt Broker assigns message to old instance
        B->>C1: Consumer v1 reads v1
    else Broker assigns message to new instance
        B->>C2: Consumer v2 reads v1
    end
    Note over C1,C2: Deploy consumer v2; producer stays v1
    P1->>B: Event schema v1
    B->>C2: New consumer reads v1 after rebalance
    Note over C1,C2: Wait until all v1 consumers leave the group
    P2->>B: Event schema v2 with optional field
    B->>C2: Consumer v2 reads v2
    Note over P2,C2: Remove old contract only after backlog and replay window
~~~

## 6. Rolling deployment và consumer group

Trong Kubernetes hoặc nền tảng orchestrator, rolling update thường tạo instance mới trước khi dừng instance cũ. Với consumer group, điều này có nghĩa cả consumer version cũ và mới có thể cùng hoạt động.

Ví dụ group billing có bốn instance:
- Hai instance v1.
- Hai instance v2.

Broker phân phối message cho các instance theo cơ chế group/partition/queue. Broker không biết instance v1 chỉ hỗ trợ schema v1. Nếu producer phát schema v2, instance v1 có thể nhận message đó.

Trước khi bật producer v2:
1. Kiểm tra tất cả replica consumer đã chạy version tương thích.
2. Kiểm tra consumer group đã ổn định sau rebalance.
3. Kiểm tra các worker cũ đã shutdown và rời group.
4. Kiểm tra các consumer khác, không chỉ service do cùng team sở hữu.
5. Kiểm tra DLQ/replay consumer và batch job cũng hiểu schema mới.
6. Sau đó mới chuyển producer sang schema mới.

### Readiness và graceful shutdown

Readiness phải phản ánh khả năng instance nhận và xử lý message. Khi dừng instance:
- Ngừng nhận công việc mới theo cơ chế binder/client phù hợp.
- Hoàn tất hoặc xử lý có kiểm soát message đang in-flight.
- Ack/commit sau khi nghiệp vụ đã hoàn tất.
- Đóng consumer để group rebalance.
- Giữ termination grace period đủ cho shutdown.
- Theo dõi lag và duplicate sau khi rollout.

Không coi HTTP readiness probe là bằng chứng duy nhất cho consumer readiness. Một instance có thể trả HTTP 200 nhưng binder chưa join group hoặc schema registry chưa truy cập được. Kiểm tra health và trạng thái binding/broker theo khả năng của binder.

### Rollback trong lúc rolling update

Rollback consumer v2 về v1 chỉ an toàn nếu producer hiện tại vẫn phát schema mà consumer v1 hiểu. Nếu producer đã phát schema v2, cần:
- Dừng hoặc rollback producer về schema v1 trước.
- Xác minh v1 consumer có thể đọc các message đã ghi.
- Nếu không thể, dùng consumer adapter/bridge hoặc chuyển dữ liệu sang topic mới.
- Không xóa schema v2 khỏi registry để cố làm rollback; message đã phát vẫn có thể tham chiếu schema đó.

## 7. JSON: field mới, field lạ và giá trị null

JSON linh hoạt nhưng không tự động an toàn khi thêm hoặc bỏ field. Tương thích phụ thuộc cả schema policy và cấu hình converter ở từng service.

Ví dụ v1:

~~~json
{
  "orderId": "ORD-1001",
  "totalMinor": 125500
}
~~~

v2 thêm field:

~~~json
{
  "orderId": "ORD-1001",
  "totalMinor": 125500,
  "currency": "VND"
}
~~~

Nếu consumer v1 bỏ qua field không biết, thay đổi có thể tương thích theo hướng forward. Nếu Jackson được cấu hình để fail khi gặp unknown property, consumer v1 sẽ lỗi. Hãy kiểm tra ObjectMapper và MessageConverter thực tế, không dựa vào giả định chung.

Các trường hợp cần phân biệt:

- Field vắng mặt: producer không gửi thuộc tính.
- Field có giá trị null: producer gửi thuộc tính nhưng không có giá trị.
- Field có giá trị mặc định: converter hoặc application tự điền.
- Field có kiểu mới: ví dụ totalMinor từ number thành string.
- Field đổi ý nghĩa: vẫn là number nhưng chuyển đơn vị.

Không gộp các trường hợp này. Validation nghiệp vụ có thể coi missing, null và default là ba tình huống khác nhau.

### JSON Schema và strictness

Nếu dùng JSON Schema registry, cần kiểm tra additionalProperties, required properties và compatibility policy. Với closed schema (additionalProperties: false), thêm field có thể bị từ chối hoặc khiến consumer không tương thích. Với open schema, field lạ có thể được chấp nhận nhưng vẫn phải kiểm tra code consumer.

Schema compatibility không bảo đảm logic nghiệp vụ chấp nhận giá trị. Ví dụ enum status thêm SUSPENDED; consumer cũ có thể parse JSON nhưng không có nhánh xử lý giá trị mới. Nên có fallback rõ ràng hoặc rollout consumer trước.

## 8. Avro: writer schema và reader schema

Avro hỗ trợ schema resolution. Producer ghi dữ liệu theo writer schema; consumer đọc bằng reader schema của phiên bản ứng dụng. Writer và reader có thể khác nhau nếu quy tắc resolution cho phép.

Ví dụ v1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalMinor", "type": "long" }
  ]
}
~~~

v2 thêm currency với union nullable và default null:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalMinor", "type": "long" },
    {
      "name": "currency",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Default cho field mới cho phép reader schema mới đọc record được ghi bằng schema cũ mà không có field currency. Avro yêu cầu default phù hợp với nhánh đầu tiên của union; vì vậy mẫu trên đặt null trước.

Đổi tên field có thể cần alias để reader schema nhận diện tên cũ. Xóa field cũng cần kiểm tra reader/writer resolution và default. Không đổi tên chỉ vì muốn Java property đẹp hơn; wire name là một phần hợp đồng.

### Spring Cloud Stream Schema Registry

Spring Cloud Stream cung cấp:
- Standalone Schema Registry Server.
- SchemaRegistryClient để ứng dụng đăng ký và lấy schema.
- Avro message converter tích hợp với registry.
- Client tương tác với Spring Cloud Stream Schema Registry hoặc Confluent Schema Registry.

Với Avro converter, binding output dùng content type dạng application/*+avro. Converter suy ra schema từ payload type, đăng ký schema theo subject và version, rồi gửi content type có thông tin subject/version. Consumer đọc reference trong header, lấy writer schema và reconcile với reader schema của ứng dụng.

Ví dụ cấu hình endpoint:

~~~yaml
spring:
  cloud:
    stream:
      schemaRegistryClient:
        endpoint: https://schema-registry.example.net
~~~

Đăng ký client trong ứng dụng:

~~~java
import org.springframework.cloud.stream.schema.registry.EnableSchemaRegistryClient;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableSchemaRegistryClient
public class BillingApplication {
}
~~~

Với output binding, đặt content type Avro theo binding property mà phiên bản Spring Cloud Stream của dự án hỗ trợ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/*+avro
~~~

Kiểm tra artifact spring-cloud-stream-schema-registry-client, phiên bản BOM và cấu hình SchemaRegistryClient của dự án. Spring Cloud Stream hỗ trợ Avro schema registry converter out of the box; nếu dùng JSON Schema hoặc Protobuf, cần serializer/converter và registry integration phù hợp, không giả định Avro converter tự xử lý chúng.

Registry kiểm tra schema theo subject. Subject naming strategy phải ổn định giữa các phiên bản; nếu đổi subject ngoài ý muốn, schema mới có thể đi vào một chuỗi compatibility khác và bỏ qua lịch sử của subject cũ.

## 9. Protobuf: field number và reserved identifiers

Protobuf dùng field number trong wire format. Không thay field number của một field đang tồn tại. Khi xóa field:
- Không tái sử dụng field number cũ.
- Đưa số đó vào reserved.
- Nên reserve cả field name để tránh xung đột với JSON/TextFormat.
- Thêm field mới với field number chưa từng dùng.

v1:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 total_minor = 2;
}
~~~

v2 thêm currency:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
}
~~~

Sau khi bỏ total_minor trong một thay đổi tương lai:

~~~protobuf
message OrderCreated {
  string order_id = 1;
  string currency = 3;

  reserved 2;
  reserved "total_minor";
}
~~~

Không đổi total_minor từ int64 sang string bằng cách giữ nguyên field number. Thay đổi đó có thể phá wire compatibility. Hãy tạo field mới với số mới, migrate consumer/producer, rồi reserve field cũ.

Enum cũng cần được tiến hóa cẩn thận. Consumer cũ phải có cách xử lý giá trị enum chưa biết; tránh giả định producer chỉ gửi các giá trị mà phiên bản code hiện tại đã biết.

## 10. Schema registry và broker-native schema

Không phải broker nào cũng quản lý schema theo cùng cách:

| Hệ thống | Cơ chế thường gặp | Điểm cần kiểm tra |
|---|---|---|
| Kafka | Schema Registry bên ngoài hoặc serializer/deserializer theo convention | Subject, compatibility mode, schema ID/version, key/value subject |
| RabbitMQ | Payload và headers do producer/consumer thỏa thuận; broker không tự áp một schema chung cho mọi queue | Contract repository, converter, validation ở ứng dụng |
| Pulsar | Native schema và schema version gắn với topic; có thể dùng JSON, Avro, Protobuf hoặc schema type phù hợp | Schema compatibility policy, producer/consumer schema và topic |
| Spring Cloud Stream | MessageConverter, content type và SchemaRegistryClient | Converter nào thực sự có mặt và binder có giữ headers/native metadata không |

Schema Registry của Spring Cloud Stream và native schema của Pulsar là hai cơ chế khác nhau. Một ứng dụng có thể dùng schema registry ở tầng framework hoặc giao schema cho client/broker, nhưng phải thống nhất một wire contract cho mỗi topic.

Nếu dùng RabbitMQ, việc queue tồn tại không chứng minh payload hợp lệ. Cần contract tests, validation và versioned schema ở tầng ứng dụng hoặc registry riêng. Nếu dùng Kafka, registry compatibility không tự bảo đảm consumer đang chạy có serializer/deserializer đúng. Nếu dùng Pulsar, broker-native schema enforcement phải được bật/cấu hình phù hợp; consumer vẫn cần logic nghiệp vụ tương thích.

## 11. Kiểm thử contract trước khi deploy

Một test chỉ serialize và deserialize cùng một phiên bản không kiểm tra được tình huống lệch thời điểm. Cần test các cặp producer/consumer khác version.

### Ma trận kiểm thử

| Producer | Consumer | Câu hỏi |
|---|---|---|
| P1 | C1 | Baseline hiện tại còn chạy không? |
| P1 | C2 | Consumer mới đọc được dữ liệu cũ không? |
| P2 | C1 | Consumer cũ đọc được dữ liệu mới không? |
| P2 | C2 | Hai phiên bản mới hoạt động đúng không? |
| P1/P2 | Replay C2 | Consumer mới đọc được toàn bộ lịch sử cần hỗ trợ không? |
| P2 | DLQ/recovery C1 | Công cụ phục hồi có hiểu schema mới không? |

Với BACKWARD, P1/C2 là cặp quan trọng; P2/C1 không được đảm bảo. Với FORWARD, P2/C1 là cặp quan trọng; P1/C2 không được đảm bảo. Với FULL, cả hai cặp cần pass trong phạm vi các phiên bản mà policy bảo vệ.

### Kiểm thử trong CI

Pipeline có thể thực hiện:

1. Lấy schema đang đăng ký của subject.
2. So sánh schema candidate với compatibility policy.
3. Sinh serializer/deserializer hoặc message fixtures.
4. Chạy test P1 → C2 và P2 → C1 theo mode đã chọn.
5. Kiểm tra missing/null/default/unknown fields.
6. Kiểm tra enum mới và field type changes.
7. Replay message từ fixture lịch sử.
8. Kiểm tra header, content type, schema reference và key.
9. Chạy integration test bằng đúng binder/broker đang dùng.
10. Chặn merge hoặc release nếu cặp version được yêu cầu không tương thích.

Không chỉ test schema registry endpoint. Registry có thể chấp nhận schema, trong khi business validation hoặc downstream database vẫn từ chối giá trị mới.

### Test với Spring Cloud Stream

Dùng Spring Integration Test Binder để kiểm thử logic binding/function nhanh, nhưng bổ sung integration test với broker thật hoặc môi trường tương đương để kiểm tra:
- Serializer/deserializer thực tế.
- Header và content type.
- Schema registry authentication/availability.
- Consumer group rollout.
- Retry, DLQ và replay.
- Native schema behavior của binder.
- Broker compatibility enforcement.

Test binder không thay thế test wire format trên broker.

## 12. Xử lý thay đổi không tương thích

Một thay đổi được coi là breaking nếu producer mới phát dữ liệu mà consumer đang hoạt động không thể đọc hoặc diễn giải đúng.

Ví dụ:
- Đổi totalMinor từ integer sang decimal/string.
- Đổi đơn vị tiền hoặc timezone mà không đổi contract.
- Đổi key làm thay đổi ordering/partitioning.
- Bỏ field consumer vẫn cần.
- Đổi enum và consumer không xử lý giá trị mới.
- Đổi content type hoặc serialization format.
- Đổi schema subject khiến registry policy không áp vào lịch sử cũ.

Khi không thể giữ tương thích:
1. Tạo topic hoặc event type mới cho contract mới, ví dụ orders.v2.
2. Triển khai consumer v2 và kiểm thử với producer v2.
3. Nếu cần, dùng bridge/adapter đọc v1 rồi chuyển sang v2.
4. Dual-publish hoặc mirror trong một giai đoạn có kiểm soát.
5. So sánh số lượng, event ID và business outcome giữa hai luồng.
6. Chuyển consumer/downstream sang v2.
7. Ngừng v1 sau khi backlog, retention và DLQ v1 đã được xử lý.
8. Giữ runbook replay và rollback trong suốt thời gian migration.

Không thay schema phá vỡ rồi đặt compatibility mode thành NONE để vượt qua CI. Điều đó chỉ tắt hàng rào kiểm tra; consumer vẫn có thể lỗi khi nhận dữ liệu.

## 13. Rollback và dữ liệu lịch sử

Rollback ứng dụng không xóa message đã được publish. Nếu producer v2 đã ghi schema v2, rollback producer về v1 không làm topic chỉ còn schema v1. Consumer rollback cần đọc được tất cả schema vẫn có thể xuất hiện trong backlog/replay.

Trước rollback:
- Xác định version schema mới nhất đã được publish.
- Xác định consumer rollback có đọc được writer schema đó không.
- Kiểm tra message đã xử lý một phần và idempotency.
- Kiểm tra DLQ, retry queue và scheduled replay.
- Giữ schema registry và schema history nguyên vẹn.
- Nếu không tương thích, deploy adapter/consumer bridge trước khi rollback service.

Đối với Kafka, reset offset hoặc replay từ đầu có thể đưa message rất cũ trở lại. Đối với RabbitMQ, message tồn tại trong queue hoặc DLQ theo retention/TTL. Đối với Pulsar, backlog và retained message có thể tham chiếu schema cũ. Chính sách compatibility nên tính đến thời gian dữ liệu có thể được đọc lại, không chỉ thời gian rolling update.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Consumer cũ lỗi ngay sau khi producer rollout | Producer phát field/type mới khi instance cũ còn trong group | Deploy consumer tương thích trước hoặc dùng FULL |
| Consumer mới không đọc message lịch sử | Schema mới chỉ backward với phiên bản liền trước hoặc thiếu default | Kiểm tra transitive compatibility và reader schema |
| Registry chấp nhận nhưng function vẫn lỗi | Schema hợp lệ nhưng business validation/DTO strict | Test converter, validation và semantics |
| Thêm JSON field làm consumer cũ lỗi | Jackson strict với unknown property | Kiểm thử ObjectMapper và triển khai consumer trước |
| Avro báo thiếu field | Field mới không có default phù hợp | Thêm union/null và default theo Avro resolution |
| Protobuf parse sai sau khi đổi field | Tái sử dụng field number hoặc đổi wire type | Dùng field number mới, reserve số cũ |
| Consumer mới hiểu sai enum | Giá trị enum mới chưa có fallback | Thêm UNKNOWN/default path và deploy consumer trước |
| Rollback consumer thất bại | Producer đã phát schema mà consumer cũ không đọc được | Rollback producer, adapter hoặc topic migration |
| Schema check không phát hiện breaking change lịch sử | Dùng compatibility non-transitive | Chọn mode transitive khi cần replay lịch sử |
| Hai service dùng subject khác nhau | Subject naming strategy không thống nhất | Chuẩn hóa subject và ownership |
| Header/schema ID bị mất | Binder hoặc native encoding thay đổi header behavior | Test header mapping và wire format |
| Dual-publish tạo side effect trùng | Consumer nhận cùng event từ hai topic | Dùng eventId ổn định và deduplication |
| Đổi partition key làm thứ tự thay đổi | Key semantics thay đổi trong khi consumer còn xử lý luồng cũ | Lập kế hoạch migration key/partition riêng |

## 15. Bài thực hành: nâng cấp OrderCreated v1 lên v2

Tình huống: producer hiện phát OrderCreated v1 với orderId và totalMinor. Cần thêm currency, trong khi consumer billing và reporting được deploy riêng.

1. Lưu schema v1 làm fixture.
2. Tạo schema v2 thêm currency optional với default hợp lệ.
3. Đăng ký schema v2 và kiểm tra BACKWARD hoặc FULL theo rollout dự kiến.
4. Viết consumer v2 đọc được message v1 thiếu currency.
5. Chạy test P1/C2 và kiểm tra kết quả nghiệp vụ.
6. Deploy consumer v2 trong khi producer vẫn v1.
7. Xác minh toàn bộ consumer v1 đã rời group và group ổn định.
8. Deploy producer v2 bắt đầu gửi currency.
9. Chạy test P2/C2 và kiểm tra dashboard lỗi deserialize/DLQ.
10. Replay message v1 từ fixture hoặc môi trường test qua consumer v2.
11. Mô phỏng rollback producer và consumer để xác nhận compatibility.
12. Sau thời gian hỗ trợ cũ, ngừng field cũ nếu có và kiểm tra schema transitive.
13. Viết runbook cho replay, rollback và DLQ.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Contract | Có event name, field semantics, type, null/default và key |
| Compatibility mode | Được chọn theo thứ tự deploy và replay window |
| Schema registry | Subject/version được quản lý ổn định |
| Consumer v2 | Đọc được message v1 |
| Producer v2 | Chỉ phát schema mới khi consumer cũ đã rời group hoặc mode cho phép |
| Rolling update | Không có instance không tương thích cùng nhận message |
| Replay | Dữ liệu lịch sử và DLQ đọc được |
| Serializer | Content type, schema reference và wire bytes đúng |
| Broker | Kafka/RabbitMQ/Pulsar binder được test thực tế |
| Rollback | Có đường quay về an toàn |
| Semantic compatibility | Đơn vị, timezone, enum và key không đổi ngoài kế hoạch |
| Migration | Breaking change dùng topic/adapter và cutover có kiểm soát |

## Kết luận

Tương thích hợp đồng phải được thiết kế cho toàn bộ thời gian producer và consumer có thể lệch phiên bản, gồm rolling update, rollback, backlog và replay. Backward compatibility yêu cầu consumer mới đọc được dữ liệu cũ; forward compatibility yêu cầu consumer cũ đọc được dữ liệu mới; full compatibility hỗ trợ cả hai chiều trong phạm vi schema được kiểm tra. Transitive cần thiết khi dữ liệu lịch sử có thể được đọc lại qua nhiều phiên bản.

Với Spring Cloud Stream, content type, MessageConverter, native encoding/decoding và schema registry là các phần cần cấu hình riêng. Áp dụng expand-contract, triển khai consumer tương thích trước khi producer phát schema mới, kiểm thử cặp producer/consumer chéo phiên bản và giữ schema history. Khi thay đổi thực sự phá vỡ hợp đồng, tạo topic/version mới và migration có kiểm soát thay vì dựa vào một lần deploy đồng thời.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.5 – Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/5.0/schema-registry/spring-cloud-stream-schema-registry.html)
- [Spring Cloud Stream – Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Confluent – Schema Compatibility API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html)
- [Apache Avro – Specification](https://avro.apache.org/docs/1.12.0/specification/)
- [Protocol Buffers – Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Protocol Buffers – Reserved Field Numbers and Names](https://protobuf.dev/programming-guides/editions/#reserved-field-numbers)
- [Spring Boot – Application Availability and Graceful Shutdown](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

