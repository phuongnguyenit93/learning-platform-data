# Serialization payload

Trong một hệ thống Spring Batch có tích hợp messaging, item thường bắt đầu là một object Java trong bộ nhớ. Khi cần gửi item qua JMS, Kafka, RabbitMQ hoặc Spring Integration channel chạy qua tiến trình khác, object đó phải được chuyển thành dạng dữ liệu mà bên nhận có thể đọc. Quá trình chuyển object thành byte hoặc text được gọi là **serialization**; quá trình khôi phục object từ dữ liệu nhận được là **deserialization**.

Serialization payload là một phần của contract giữa producer và consumer. Producer quyết định dữ liệu nào được đưa vào message, cách mã hóa và schema/version; consumer cần hiểu đúng định dạng đó để tạo lại payload có ý nghĩa. Nếu hai phía không thống nhất, message có thể gửi thành công ở tầng transport nhưng batch worker vẫn không xử lý được item.

Trong Spring Batch, serialization đặc biệt quan trọng khi job trao đổi dữ liệu qua message channel, remote chunking, remote partitioning hoặc khi step đọc/ghi message từ broker. Cần phân biệt payload với message headers, serialization với checkpoint của JobRepository, và lỗi chuyển đổi dữ liệu với lỗi nghiệp vụ. Một thiết kế tốt giữ payload nhỏ, có schema rõ, tương thích version, an toàn khi deserialize và có thể xử lý lại khi message được giao nhiều lần.

## 1. Payload là gì?

Trong Spring Messaging, message thường có hai phần:

- **Payload:** nội dung chính mà producer muốn truyền, ví dụ Order, Payment hoặc một danh sách item.
- **Headers:** metadata mô tả message, ví dụ message ID, correlation ID, timestamp, content type, partition key hoặc thông tin routing.

Một message có thể hình dung như sau:

~~~text
Message
  ├── headers
  │     ├── messageId
  │     ├── correlationId
  │     ├── contentType
  │     └── partitionKey
  └── payload
        └── OrderCreated
~~~

Payload biểu diễn dữ liệu nghiệp vụ. Headers giúp hệ thống vận chuyển, định tuyến, quan sát và tương quan các message. Không nên đưa mọi metadata vào payload nếu transport đã có header phù hợp; cũng không nên đưa business fields quan trọng vào header vì nhiều broker giới hạn kích thước hoặc kiểu header.

Ví dụ payload JSON:

~~~json
{
  "orderId": 1001,
  "customerId": "C001",
  "amount": 250.00,
  "currency": "VND"
}
~~~

Headers có thể chứa correlation ID của job hoặc message, nhưng không thay thế business key orderId trong payload. Consumer cần business key để deduplicate và đối soát ngay cả khi message được gửi lại với message ID khác.

## 2. Serialization và deserialization

Serialization chuyển object thành biểu diễn có thể truyền hoặc lưu:

~~~text
Java object -> serializer -> byte[] / String
~~~

Deserialization thực hiện chiều ngược lại:

~~~text
byte[] / String -> deserializer -> Java object
~~~

Ví dụ object Java:

~~~java
public class OrderPayload {
    private Long orderId;
    private String customerId;
    private BigDecimal amount;
    private String currency;

    public OrderPayload() {
    }

    // getters and setters
}
~~~

JSON representation tương ứng có thể được parse thành một OrderPayload ở consumer. Cần thống nhất tên field, kiểu số, format ngày giờ, enum, null handling và quy tắc unknown field.

Serialization không đồng nghĩa encryption. JSON hoặc Avro có thể được serialize nhưng vẫn đọc được nếu không có mã hóa. Nếu payload chứa dữ liệu nhạy cảm, cần TLS cho transport và có thể cần encryption at rest hoặc field-level encryption theo threat model.

## 3. Serialization nằm ở đâu trong message processing?

Một pipeline message-driven có thể gồm:

~~~mermaid
flowchart LR
    A[Spring Batch item] --> B[Message producer]
    B --> C[Payload converter / serializer]
    C --> D[Broker or channel]
    D --> E[Deserializer / message converter]
    E --> F[Message consumer]
    F --> G[Batch worker or next step]
~~~

Producer tạo payload từ item hoặc chunk. Serializer chuyển payload thành wire representation. Broker vận chuyển bytes cùng headers. Consumer đọc message, giải mã payload thành object và đưa object vào processor/writer hoặc một job/step khác.

Lỗi có thể xuất hiện ở từng boundary:

- Producer tạo object không đúng schema.
- Serializer không hỗ trợ kiểu dữ liệu.
- Broker từ chối message vì kích thước hoặc quyền.
- Consumer dùng schema/version khác.
- Deserializer không thể khôi phục kiểu.
- Payload hợp lệ về cú pháp nhưng sai business rule.

Nên ghi nhận rõ lỗi xảy ra ở tầng nào. Một JSON parse error không giống validation error của Order; một broker timeout cũng không giống lỗi schema.

## 4. Message và payload trong Spring Messaging

Spring Messaging định nghĩa abstraction Message với payload và headers. Producer có thể tạo message bằng MessageBuilder:

~~~java
OrderPayload payload = new OrderPayload();
payload.setOrderId(1001L);
payload.setCustomerId("C001");
payload.setAmount(new BigDecimal("250.00"));
payload.setCurrency("VND");

Message<OrderPayload> message = MessageBuilder
        .withPayload(payload)
        .setHeader("correlationId", "orders-export-2026-11-15")
        .setHeader("contentType", "application/json")
        .build();
~~~

Message object trong bộ nhớ vẫn có payload là Java object. Việc tạo Message không tự động có nghĩa object đã được serialize thành bytes. Converter hoặc adapter của transport thực hiện chuyển đổi khi message đi qua boundary tương ứng.

Đừng nhầm một Spring Message với message representation mà broker lưu. JMS Message, Kafka record và Spring Message có API khác nhau. Spring Integration có thể chuyển đổi giữa chúng thông qua adapter và converter.

## 5. MessageConverter trong Spring Messaging

Spring Messaging cung cấp abstraction MessageConverter để chuyển đổi giữa object và Message:

~~~java
public interface MessageConverter {

    Message<?> toMessage(Object payload, MessageHeaders headers);

    Object fromMessage(Message<?> message, Class<?> targetClass);
}
~~~

Các converter có thể tạo message từ object hoặc lấy object từ message. Spring Integration sử dụng message conversion ở các điểm tích hợp channel/endpoint; converter thực tế phụ thuộc transport và cấu hình.

Không phải mọi hệ thống messaging đều dùng đúng interface này. Ví dụ:

- Spring Messaging MessageConverter có API dựa trên MessageHeaders.
- Spring JMS MessageConverter làm việc với jakarta.jms.Session và jakarta.jms.Message.
- Kafka client dùng Serializer<T> và Deserializer<T> để chuyển value thành bytes và ngược lại.

Tên interface giống nhau không có nghĩa có thể truyền một converter cho mọi transport. Cần chọn đúng API theo adapter/broker đang dùng.

## 6. Chọn định dạng payload

Định dạng serialization ảnh hưởng khả năng tương thích, kích thước, tốc độ, khả năng debug và cách version schema.

| Định dạng | Ưu điểm | Hạn chế | Thường phù hợp |
|---|---|---|---|
| JSON | Dễ đọc, phổ biến, hỗ trợ nhiều ngôn ngữ | Payload thường lớn hơn binary; cần quản lý schema | API, event, integration phổ thông |
| Avro | Binary compact, schema evolution có quy tắc | Cần schema và tooling phù hợp | Event stream, data pipeline |
| Protocol Buffers | Binary nhỏ, typed contract, code generation | Cần quản lý .proto và compatibility | Service-to-service, throughput cao |
| XML | Có schema/XSD và tooling lâu đời | Dài, parsing thường nặng hơn JSON | Hệ thống enterprise dùng XML |
| Java native serialization | Có thể serialize object graph Java nhanh để thử nghiệm | Phụ thuộc class/version, khó tương thích, rủi ro bảo mật | Tránh dùng cho boundary không tin cậy |

Không có format tốt nhất cho mọi trường hợp. Chọn theo contract của consumer, yêu cầu throughput, khả năng version hóa và hệ sinh thái mà các hệ thống liên quan hỗ trợ.

## 7. JSON serialization với Jackson

Jackson thường được dùng để serialize DTO thành JSON. Nên định nghĩa payload DTO riêng thay vì serialize trực tiếp entity persistence hoặc object graph lớn.

Ví dụ:

~~~java
public record OrderEvent(
        String eventId,
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        Instant occurredAt) {
}
~~~

Serialize:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

String json = objectMapper.writeValueAsString(
        new OrderEvent(
                "evt-1001",
                1001L,
                "C001",
                new BigDecimal("250.00"),
                "VND",
                Instant.parse("2026-11-15T10:30:00Z")));
~~~

Deserialize:

~~~java
OrderEvent event = objectMapper.readValue(json, OrderEvent.class);
~~~

Với record hoặc constructor-based DTO, cần cấu hình Jackson module/version phù hợp. Với POJO, cần accessor hoặc annotation theo convention của ứng dụng. Không nên dùng ObjectMapper khác cấu hình production trong test vì behavior null/date/enum/unknown property có thể khác.

## 8. JSON date, time và decimal

Ngày giờ cần format có timezone rõ ràng. Với Instant, ISO-8601 UTC là lựa chọn phổ biến:

~~~json
{
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Không serialize LocalDateTime rồi giả định consumer biết timezone. LocalDateTime không mang offset/timezone; nếu sự kiện biểu diễn thời điểm tuyệt đối, dùng Instant hoặc OffsetDateTime và thống nhất quy tắc.

Với số tiền, dùng BigDecimal trong Java và JSON number theo contract:

~~~json
{
  "amount": 250.00,
  "currency": "VND"
}
~~~

Không chuyển BigDecimal sang double chỉ để serialization đơn giản. Nếu consumer cần scale cố định, hãy quy định rõ serializer/format và test round-trip. JSON number không bảo đảm mọi ngôn ngữ consumer giữ nguyên scale hiển thị, nên business comparison thường cần dựa trên numeric value và currency.

## 9. Enum và giá trị ổn định

Mặc định, enum có thể được serialize bằng tên constant. Nếu đổi tên Java constant, payload wire format có thể thay đổi ngoài ý muốn.

Ví dụ:

~~~java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
~~~

Nếu tên enum là public contract, cần xem việc rename là breaking change. Một lựa chọn khác là dùng code ổn định như CREATED, PAID hoặc mã ngắn được định nghĩa trong schema, với serializer/deserializer tùy chỉnh.

Test nên xác nhận:

- Giá trị enum hợp lệ được parse đúng.
- Giá trị không biết được xử lý theo contract.
- Casing có phân biệt hay được chuẩn hóa.
- Giá trị cũ vẫn đọc được khi producer/consumer được nâng cấp không đồng thời.

Không tự map enum lạ thành một trạng thái hợp lệ như CREATED; điều đó có thể làm sai nghiệp vụ.

## 10. Payload DTO và domain entity

Không nên serialize toàn bộ JPA entity hoặc domain aggregate nếu consumer chỉ cần một phần dữ liệu.

Các rủi ro:

- Lazy-loaded association có thể kích hoạt query bất ngờ.
- Object graph vòng có thể gây lỗi hoặc JSON reference phức tạp.
- Field nội bộ như audit, password hash hoặc token có thể bị lộ.
- Thay đổi schema database vô tình làm thay đổi message contract.
- Payload lớn làm tăng network, broker storage và consumer memory.

Tạo DTO/event riêng:

~~~java
public record OrderExportPayload(
        Long orderId,
        String customerCode,
        BigDecimal total,
        String currency) {
}
~~~

Processor hoặc mapper chuyển domain object sang payload DTO trước khi gửi. DTO nên chứa những field consumer cần và có version/schema contract rõ ràng.

## 11. Envelope và event metadata

Một payload có thể được bọc trong envelope để consumer biết loại event, version và dữ liệu:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-15T10:30:00Z",
  "data": {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00,
    "currency": "VND"
  }
}
~~~

Envelope thường chứa:

- eventId: định danh ổn định của sự kiện.
- eventType: loại sự kiện.
- schemaVersion: version contract.
- occurredAt: thời điểm nghiệp vụ.
- correlationId/causationId: liên kết với flow trước đó.
- data: payload nghiệp vụ.

Một số trường phù hợp đặt trong message headers thay vì body. Ví dụ content type, transport partition key và correlation metadata có thể là header; event type/schema version có thể ở envelope nếu message được lưu thành file hoặc chuyển qua nhiều transport. Chọn một quy tắc nhất quán và tránh để cùng metadata có hai giá trị mâu thuẫn ở header và payload.

## 12. Correlation ID, message ID và business key

Ba định danh này có mục đích khác nhau:

| Định danh | Ý nghĩa |
|---|---|
| messageId | Định danh một lần gửi/record transport |
| correlationId | Liên kết nhiều message trong cùng một workflow |
| business key | Định danh thực thể nghiệp vụ, ví dụ orderId |

Khi broker redeliver một message, message ID có thể phụ thuộc transport hoặc cách publish; business key vẫn là căn cứ dedup ở tầng nghiệp vụ. Nếu producer retry publish và tạo message ID mới, eventId ổn định trong payload có thể giúp consumer nhận ra cùng một event.

Với Spring Batch, có thể đưa job execution/step execution reference vào metadata để trace, nhưng không nên dùng các ID đó thay cho business key hoặc event ID.

## 13. JMS serialization

JMS truyền các loại message như TextMessage, BytesMessage, MapMessage và ObjectMessage. Với integration hiện đại, JSON dạng TextMessage hoặc binary dạng BytesMessage thường dễ kiểm soát contract hơn ObjectMessage.

Spring JMS cung cấp MessageConverter riêng để chuyển Java object sang JMS Message và ngược lại. Ví dụ cấu hình Jackson converter có thể serialize DTO thành JSON text hoặc bytes tùy converter và phiên bản Spring:

~~~java
@Bean
public MessageConverter orderMessageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setObjectMapper(objectMapper);
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}
~~~

API converter có thể thay đổi theo phiên bản Spring Framework/Jackson. Kiểm tra class, target type và type mapping trong dependency thực tế. Nếu consumer không phải Java, nên định nghĩa JSON contract độc lập thay vì dựa vào class name trong type header.

## 14. Vì sao nên thận trọng với JMS ObjectMessage?

ObjectMessage thường dựa trên Java native serialization. Consumer cần class tương thích và có thể gặp vấn đề khi:

- Class thay đổi package hoặc field.
- Producer/consumer chạy phiên bản ứng dụng khác nhau.
- Class không có trong classpath consumer.
- Deserialization khởi tạo object graph không mong muốn.
- Payload đến từ nguồn không tin cậy.

Java native deserialization có lịch sử nhiều rủi ro bảo mật. Không deserialize ObjectMessage từ nguồn không tin cậy hoặc broker mà quyền publish không được kiểm soát chặt. Ưu tiên text/binary format có schema rõ ràng như JSON, Avro hoặc Protobuf.

Nếu hệ thống legacy bắt buộc dùng ObjectMessage, giới hạn trusted producer, allowlist class được phép, cập nhật JDK/framework và kiểm soát quyền broker. Không coi việc message nằm trong private network là biện pháp bảo mật đầy đủ.

## 15. Kafka serialization

Kafka record có key và value dạng bytes ở wire boundary. Kafka client dùng Serializer<T> ở producer và Deserializer<T> ở consumer:

~~~text
Producer object
  -> Serializer
  -> Kafka record key/value bytes
  -> topic/partition
  -> Deserializer
  -> Consumer object
~~~

Ví dụ cấu hình JSON serializer/deserializer trong Spring Kafka có thể dùng JsonSerializer và JsonDeserializer:

~~~java
Map<String, Object> producerProps = new HashMap<>();
producerProps.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);

Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class);
consumerProps.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderEvent.class);
~~~

Tên property và package có thể khác theo Spring Kafka version. Cần cấu hình trusted packages/type mapping và tránh phụ thuộc vào class name Java nếu producer/consumer là các ứng dụng khác ngôn ngữ.

Kafka key thường được serialize riêng và có thể quyết định partitioning. Key nên được chọn theo yêu cầu ordering/affinity, ví dụ orderId hoặc customerId. Không nhầm key với payload business identity nếu contract có nhiều loại event.

## 16. Type headers trong JSON message

Một số converter có thể thêm type metadata vào headers để consumer biết class đích. Cơ chế này tiện trong hệ sinh thái Java nhưng có thể làm contract phụ thuộc package/class name.

Ví dụ:

- Producer gửi type header chứa tên Java class.
- Consumer cố load class tương ứng.
- Producer đổi package hoặc class name.
- Consumer cũ không tìm được class dù JSON fields vẫn tương thích.

Với contract cross-service hoặc cross-language, nên dùng eventType/schemaVersion ổn định và mapping rõ từ event type sang DTO được phép. Không cho phép payload tự chỉ định arbitrary Java class để deserializer load.

Nếu sử dụng Spring Kafka type headers, có thể cấu hình type mapping hoặc default target type. Hãy xác nhận behavior của producer và consumer khi header thiếu, header lạ hoặc type không nằm trong allowlist.

## 17. Avro và schema registry

Avro dùng schema để mô tả cấu trúc record và serialize dữ liệu thành binary. Producer và consumer cần schema tương ứng; schema registry có thể quản lý version và compatibility policy.

Một schema Avro rút gọn:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    {"name": "orderId", "type": "long"},
    {"name": "customerId", "type": "string"},
    {"name": "amount", "type": "bytes"},
    {"name": "currency", "type": "string"}
  ]
}
~~~

Ví dụ chỉ minh họa cấu trúc; biểu diễn decimal thường dùng logicalType decimal với precision/scale và schema bytes/fixed phù hợp. Không tự coi bytes là decimal nếu thiếu logical type metadata.

Ưu điểm của Avro:

- Binary payload gọn.
- Schema có thể được version hóa.
- Consumer có thể đọc writer schema cũ bằng reader schema mới khi compatibility rule cho phép.
- Hỗ trợ nhiều ngôn ngữ.

Schema registry không tự bảo đảm mọi thay đổi đều an toàn. Cần chọn backward/forward/full compatibility theo thứ tự deploy producer/consumer và quy trình replay.

## 18. Protocol Buffers

Protocol Buffers mô tả message trong file .proto và generate class cho ngôn ngữ cần dùng.

Ví dụ:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  int64 order_id = 1;
  string customer_id = 2;
  string amount = 3;
  string currency = 4;
}
~~~

Các field number là một phần của wire contract. Khi thay đổi schema:

- Không tái sử dụng field number đã xóa.
- Dùng reserved cho field number/name cũ nếu cần.
- Thêm field mới theo cách tương thích.
- Kiểm tra semantics của default value và field presence.
- Giữ type ổn định; đổi type có thể làm dữ liệu cũ được diễn giải sai.

Trong ví dụ, amount là string để tránh giả định decimal mapping; một contract thực tế có thể dùng integer minor units hoặc một message Decimal riêng với scale rõ ràng.

## 19. Schema versioning

Producer và consumer thường không được deploy cùng lúc. Vì vậy payload cần có chiến lược tương thích:

- **Backward compatibility:** consumer mới đọc được message cũ.
- **Forward compatibility:** consumer cũ đọc được message mới trong phạm vi quy tắc đã định.
- **Full compatibility:** cả hai chiều đều được hỗ trợ theo policy schema.

Một số thay đổi thường ít rủi ro:

- Thêm field optional có default rõ.
- Thêm enum value nếu consumer có chiến lược unknown value.
- Giữ nguyên field name/type/meaning.

Một số thay đổi thường breaking:

- Xóa field consumer bắt buộc.
- Đổi type number thành string.
- Đổi semantics của field nhưng giữ nguyên tên.
- Đổi timezone/format ngày giờ.
- Đổi enum value hoặc rename wire value.
- Đổi đơn vị tiền hoặc scale mà không đổi contract.

Không chỉ version hóa cấu trúc; semantics cũng cần được quản lý. Field amount đổi từ gross sang net là breaking change dù kiểu vẫn là number.

## 20. Consumer-driven contract và rollout

Trước khi producer phát payload version mới, cần biết consumer nào đang đọc topic/queue đó. Một quy trình rollout có thể:

1. Định nghĩa schema mới và kiểm tra compatibility.
2. Deploy consumer có thể đọc cả version cũ và mới.
3. Xác nhận consumer mới xử lý payload cũ.
4. Deploy producer phát version mới.
5. Theo dõi parse error, unknown field và business validation.
6. Chỉ bỏ hỗ trợ version cũ sau khi hết retention/replay window và các consumer đã nâng cấp.

Nếu producer deploy trước consumer, payload mới có thể bị consumer cũ từ chối. Với batch, một loạt message lỗi có thể làm step fail hoặc tăng skip count. Cần test thứ tự rollout và khả năng replay message cũ.

## 21. Serialization trong remote chunking

Remote chunking chia công việc giữa manager step và worker step. Manager đọc/processor item rồi gửi chunk đến worker qua messaging middleware; worker nhận chunk và thực hiện write.

~~~mermaid
flowchart LR
    A[Manager reader] --> B[Manager processor]
    B --> C[Chunk request]
    C --> D[Serializer]
    D --> E[Broker]
    E --> F[Deserializer]
    F --> G[Worker writer]
    G --> H[Business database]
    H --> I[Chunk response]
    I --> J[Manager]
~~~

Trong mô hình này, payload có thể chứa chunk item và metadata điều phối. Các item phải serialize được theo converter/transport đang dùng. Worker phải deserialize được đúng kiểu hoặc dùng schema contract chung.

Không nên gửi entity chứa lazy proxy, open stream, JDBC connection hoặc object graph lớn không cần thiết. Hãy gửi DTO/command nhỏ và ổn định. Nếu worker cần thêm dữ liệu, có thể gửi business key để worker đọc từ shared store thay vì serialize toàn bộ aggregate.

Remote chunking phù hợp khi manager có thể cung cấp chunk và worker thực hiện cùng một loại processing/write workload. Broker cần đủ throughput và có cơ chế back-pressure, acknowledgement và retry phù hợp.

## 22. Serialization trong remote partitioning

Remote partitioning khác remote chunking. Manager chia workload thành partition và gửi execution request đến worker. Worker thường dùng partition context để đọc dữ liệu của partition từ shared data source.

Payload request có thể chủ yếu chứa thông tin điều phối như job/step execution identity, step name và partition name; business items không nhất thiết được serialize trong request.

Điều này tạo ra khác biệt:

| Remote chunking | Remote partitioning |
|---|---|
| Manager gửi chunk item tới worker | Manager gửi yêu cầu chạy partition |
| Payload có thể lớn vì chứa item | Request thường nhỏ, chứa partition metadata |
| Worker xử lý chunk được gửi | Worker tự đọc phần dữ liệu được phân công |
| Serialization của item là trọng tâm | Serialization của execution request/context là trọng tâm |

Đừng gửi cả danh sách hàng triệu key trong partition request. Lưu partition range/filter trong execution context hoặc bảng staging và gửi reference/key phù hợp. Cần bảo đảm worker có thể truy cập dữ liệu và metadata cần thiết.

## 23. Payload phải phù hợp với message size limit

Broker thường có giới hạn kích thước message hoặc cấu hình giới hạn ở producer/consumer. Payload lớn có thể:

- Bị producer từ chối.
- Bị broker từ chối hoặc làm tăng storage/replication cost.
- Làm consumer tốn nhiều heap khi deserialize.
- Tăng network latency và thời gian retry.
- Làm một message lỗi khó được replay hoặc điều tra.

Với remote chunking, chunk size vừa là transaction/recovery parameter vừa ảnh hưởng message size. Không chỉ chọn chunk size theo database throughput; cần tính tổng byte sau serialization, headers và protocol overhead.

Nếu payload rất lớn:

- Chỉ gửi business key hoặc reference đến object storage.
- Chia payload thành các message có sequence/part metadata.
- Dùng streaming protocol phù hợp nếu transport hỗ trợ.
- Nén khi chi phí CPU và compatibility cho phép.
- Giữ message envelope nhỏ và có manifest/checksum cho artifact ngoài.

Không chia chunk tùy tiện nếu consumer cần toàn bộ chunk để bảo đảm atomicity. Cần xác định cách tổng hợp và retry từng phần.

## 24. Compression

Compression giảm byte truyền và broker storage nhưng làm tăng CPU, latency và độ phức tạp vận hành. Producer và consumer phải thống nhất thuật toán và cách biểu thị compressed payload.

Cần kiểm tra:

- Payload có thực sự đủ lớn để nén hiệu quả không?
- Broker/client có hỗ trợ compression native không?
- Compression được áp dụng ở record hay ở application payload?
- Consumer có giới hạn decompressed size để tránh decompression bomb không?
- Metric có phân biệt compressed bytes và decompressed bytes không?

Không nén payload nhỏ nếu overhead lớn hơn lợi ích. Với Kafka, compression có thể được cấu hình ở producer/batch record level; với JMS hoặc message channel, có thể cần application-level compression hoặc broker feature. Cách cấu hình phụ thuộc transport.

## 25. Security khi deserialize

Deserialization xử lý dữ liệu đến từ bên ngoài process. Payload phải được coi là input không tin cậy, kể cả khi broker là nội bộ.

Nguyên tắc:

- Không dùng Java native serialization cho payload từ nguồn không tin cậy.
- Không bật Jackson default typing rộng rãi cho dữ liệu bên ngoài.
- Dùng DTO class allowlist hoặc mapping type cố định.
- Validate schema và giới hạn độ sâu/kích thước collection.
- Giới hạn message size, decompressed size và string length.
- Không để payload tự chọn class tùy ý được load.
- Dùng TLS, authentication và authorization cho broker.
- Không log secret hoặc toàn bộ payload nhạy cảm.

Một payload có thể hợp lệ về cú pháp nhưng chứa dữ liệu gây tốn bộ nhớ hoặc kích hoạt logic nguy hiểm. Deserialization nên được giới hạn và theo sau bởi validation.

## 26. Type metadata và polymorphic payload

Nếu payload có nhiều subtype, cần chọn cách biểu diễn type:

- Event envelope có eventType discriminator.
- JSON field type được kiểm soát bằng allowlist.
- Schema registry/Avro record type.
- Protobuf message type theo schema.
- Topic/queue riêng theo event family.

Không cho payload tự khai báo tên Java class tùy ý rồi dùng reflection load class. Type discriminator nên ánh xạ qua registry tĩnh:

~~~java
Map<String, Class<? extends EventPayload>> allowedTypes = Map.of(
        "OrderCreated", OrderCreatedPayload.class,
        "OrderCancelled", OrderCancelledPayload.class);
~~~

Consumer kiểm tra eventType, lấy class từ allowlist rồi deserialize. Nếu type không biết, xử lý theo contract như quarantine hoặc reject; không tự load class theo string nhận từ message.

## 27. Validation sau deserialization

Deserialize thành công chỉ chứng minh bytes/text có thể được chuyển thành object. Nó không chứng minh payload hợp lệ về nghiệp vụ.

Quy trình thường gồm:

1. Kiểm tra content type và schema version.
2. Deserialize vào DTO đã được phép.
3. Validate field bắt buộc, range và format.
4. Kiểm tra business invariants.
5. Kiểm tra business key/idempotency.
6. Đưa item hợp lệ vào processor/writer.

Ví dụ:

~~~java
public void validate(OrderEvent event) {
    if (event.orderId() == null) {
        throw new InvalidPayloadException("orderId is required");
    }
    if (event.amount() == null || event.amount().signum() < 0) {
        throw new InvalidPayloadException("amount must be non-negative");
    }
}
~~~

Không trộn parser error với business validation exception. Việc phân loại rõ giúp quyết định message nào retry, message nào quarantine và message nào cần sửa producer.

## 28. Malformed payload và poison message

Poison message là message luôn thất bại khi consumer xử lý, ví dụ JSON malformed hoặc schema version không được hỗ trợ. Nếu consumer retry vô hạn, một message có thể chặn partition/queue hoặc tiêu tốn tài nguyên liên tục.

Chiến lược thường dùng:

- Retry có giới hạn cho lỗi tạm thời.
- Không retry vô hạn lỗi parse/schema cố định.
- Chuyển message không thể xử lý vào dead-letter queue hoặc quarantine store.
- Ghi event ID, source, error code và payload reference để điều tra.
- Giữ quyền replay sau khi sửa consumer/schema.

Không xóa message lỗi mà không lưu dấu vết nếu dữ liệu có giá trị nghiệp vụ. Với batch, poison message có thể làm step dừng; cần quyết định fail toàn job hay skip/quarantine theo mức độ độc lập của record.

## 29. Acknowledgement và transaction

Message acknowledgement xác nhận consumer đã xử lý hoặc chấp nhận message theo semantics của broker. Nó không tự động đồng nghĩa business database đã commit nếu hai resource không cùng transaction.

Ví dụ rủi ro:

1. Consumer nhận message.
2. Deserialize thành công.
3. Ghi database và commit.
4. Process chết trước khi ack.
5. Broker giao lại message.

Consumer phải idempotent để lần giao lại không tạo kết quả trùng.

Rủi ro ngược lại:

1. Consumer ack message.
2. Database write thất bại hoặc chưa commit.
3. Message không còn được broker giao lại.
4. Business data bị mất.

Thứ tự acknowledgement/commit và transaction integration phụ thuộc JMS/Kafka/RabbitMQ configuration. Cần dùng transaction/ack mode phù hợp và vẫn thiết kế idempotency cho crash window.

## 30. Exactly-once và thực tế xử lý message

Không nên hứa “exactly once” chỉ vì broker hỗ trợ transactional producer hoặc consumer offset transaction. Exactly-once ở một phạm vi transport không tự bảo đảm side effect database, file hoặc API ngoài phạm vi đó cũng chỉ xảy ra một lần.

Một thiết kế thực tế thường dùng:

- At-least-once delivery.
- Stable event ID hoặc idempotency key.
- Unique constraint/deduplication ledger.
- Database transaction cho business update.
- Outbox/inbox pattern khi cần phối hợp message và database.
- Reconciliation và replay có kiểm soát.

Inbox pattern lưu event ID đã xử lý cùng business update trong một transaction. Khi nhận lại event ID, consumer biết message đã được áp dụng và có thể ack mà không thực hiện side effect lần nữa.

## 31. Serialization và Spring Batch retry/skip

Lỗi serialization/deserialization có thể xuất hiện trước khi ItemReader trả được item hoặc trước khi ItemWriter gửi được message. Cần xác định boundary:

- Producer serialize lỗi: chunk có thể fail ở writer.
- Consumer deserialize lỗi: message listener/adapter có thể fail trước khi step nhận item.
- Business validation lỗi: processor có thể ném exception theo item.
- Broker timeout: transport exception có thể retry.

Không cấu hình cùng một retry policy cho mọi exception. Lỗi schema cố định thường không tự hết khi retry; timeout broker có thể tạm thời.

Với chunk writer gửi nhiều message, nếu một số message đã publish rồi message tiếp theo thất bại, retry chunk có thể gửi lại các message trước. Dùng event ID ổn định và consumer dedup, hoặc dùng transactional producer/outbox phù hợp.

## 32. Không serialize toàn bộ ExecutionContext thành payload nghiệp vụ

ExecutionContext của Spring Batch là state vận hành để khôi phục step/job. Nó có thể chứa reader position, page token, resource index và dữ liệu checkpoint nhỏ. Đây không phải message contract chung cho các hệ thống.

Không nên gửi toàn bộ ExecutionContext qua broker như payload business:

- Nó có thể chứa key nội bộ phụ thuộc implementation.
- Một số giá trị không phù hợp cho serialization xuyên version.
- Có thể chứa state nhạy cảm hoặc object không tương thích.
- Consumer không nên phụ thuộc vào metadata nội bộ của JobRepository.

Nếu worker cần thông tin partition/job, gửi DTO request với field rõ ràng như jobExecutionId, stepName, partitionId hoặc business range theo contract tích hợp. Chỉ gửi những trường worker thực sự cần.

## 33. Message payload trong remote chunking: thiết kế DTO

Với remote chunking, payload thường chứa một nhóm item cần worker xử lý. Nên đảm bảo item:

- Có thể serialize bằng format đã chọn.
- Không chứa proxy/resource không thể truyền.
- Có schema ổn định giữa manager và worker.
- Có business key và event/chunk correlation.
- Không vượt giới hạn message size.

Nếu manager và worker dùng cùng Java version/classpath, Java object vẫn cần chuyển qua wire format. Việc cùng codebase không có nghĩa có thể truyền trực tiếp object reference qua broker.

Đối với chunk lớn, cân nhắc gửi reference đến staging dataset hoặc object storage. Worker có thể đọc theo range/key, giảm payload truyền và tránh tạo message khổng lồ.

## 34. Message payload trong remote partitioning: giữ request nhỏ

Trong remote partitioning, manager thường gửi yêu cầu chạy partition. Request nên chứa metadata đủ để worker khởi chạy đúng partition, còn dữ liệu nghiệp vụ được đọc từ nguồn dùng chung.

Một request khái niệm:

~~~json
{
  "jobExecutionId": 501,
  "stepName": "processOrders.worker",
  "partitionName": "partition-03",
  "fromOrderId": 20001,
  "toOrderId": 30000,
  "inputVersion": "snapshot-2026-11-15"
}
~~~

Worker cần xác thực execution/partition và lấy dữ liệu trong range. Không nên gửi cả danh sách object nếu worker có thể đọc cùng nguồn dữ liệu bằng partition key.

Các trường ID nội bộ chỉ nên được dùng trong phạm vi trust boundary và version compatibility đã xác định. Nếu worker khác ứng dụng hoặc khác version, dùng contract DTO rõ thay vì serialize trực tiếp object metadata nội bộ.

## 35. Schema registry và replay

Message broker có thể lưu message lâu hơn vòng đời một deployment. Một consumer mới có thể phải đọc message được serialize bằng schema cũ.

Schema registry hoặc schema repository giúp:

- Lưu version schema.
- Xác định schema ID/version trong message.
- Kiểm tra compatibility trước publish.
- Khôi phục writer schema khi replay.
- Quản lý thời điểm ngừng hỗ trợ schema cũ.

Không xóa schema cũ khi message còn retention hoặc có thể được replay từ archive. Nếu không thể đọc lại message cũ, batch recovery/backfill có thể bị chặn.

## 36. Kiểm thử serialization round-trip

Round-trip test kiểm tra object sau khi serialize rồi deserialize có giữ semantics cần thiết:

~~~java
@Test
void serializesAndDeserializesOrderEvent() throws Exception {
    OrderEvent original = new OrderEvent(
            "evt-1001",
            1001L,
            "C001",
            new BigDecimal("250.00"),
            "VND",
            Instant.parse("2026-11-15T10:30:00Z"));

    String json = objectMapper.writeValueAsString(original);
    OrderEvent restored = objectMapper.readValue(json, OrderEvent.class);

    assertEquals(original, restored);
}
~~~

Round-trip test hữu ích nhưng chưa đủ để chứng minh compatibility giữa hai version. Nếu producer và consumer dùng cùng ObjectMapper và cùng class, test có thể che giấu vấn đề như type header phụ thuộc class name hoặc schema evolution.

## 37. Kiểm thử wire contract độc lập

Nên có test kiểm tra JSON/binary representation mà consumer thực sự nhận:

- Field name đúng contract.
- Field bắt buộc có mặt.
- Không xuất field nội bộ.
- Timestamp có timezone/format đúng.
- Decimal và enum có biểu diễn ổn định.
- Content type/schema version đúng.
- Header correlation/key được đặt đúng.
- Unknown field được xử lý theo policy.

Golden fixture nhỏ có thể giúp kiểm tra wire contract. Parse actual JSON thành tree khi thứ tự key không phải contract; so sánh byte/string nguyên văn chỉ khi format chính xác là yêu cầu.

## 38. Kiểm thử tương thích schema

Với schema versioned, tạo fixture từ các version producer cần hỗ trợ:

- Consumer mới đọc được payload version cũ.
- Consumer xử lý field optional mới.
- Unknown enum value đi vào nhánh đã định.
- Missing required field bị reject rõ ràng.
- Version không hỗ trợ được đưa vào quarantine/DLQ.
- Replay message cũ không phụ thuộc class đã bị xóa.

Với Avro/Protobuf, chạy compatibility check trên schema registry/tooling phù hợp. Với JSON, có thể validate bằng JSON Schema và test mapper version cũ/mới.

## 39. Kiểm thử lỗi deserialization và poison message

Các test cần có:

- JSON malformed.
- Payload rỗng hoặc null.
- Content type không hỗ trợ.
- Schema version không tồn tại.
- Field sai type.
- Payload vượt giới hạn kích thước.
- Polymorphic type không nằm trong allowlist.
- Message bị cắt hoặc bytes không hợp lệ.

Xác nhận consumer không ack một message chưa được xử lý theo semantics đã chọn; hoặc chuyển nó sang DLQ/quarantine đúng cách. Kiểm tra log/error record có event ID và error code mà không lưu secret.

## 40. Integration test với broker

Unit test converter không chứng minh adapter/broker được cấu hình đúng. Integration test có thể dùng broker container hoặc embedded broker phù hợp với transport:

1. Khởi tạo producer và consumer cùng cấu hình converter/serializer.
2. Gửi message với payload và headers đại diện.
3. Nhận message ở consumer.
4. Xác nhận payload, content type, correlation ID và key.
5. Gửi malformed payload và xác nhận error handling/DLQ.
6. Mô phỏng redelivery và xác nhận idempotency.
7. Kiểm tra acknowledgement/transaction behavior khi database write thất bại.

Test broker thật giúp phát hiện khác biệt giữa in-memory Message và wire representation. Tuy nhiên, performance/throughput test nên tách riêng để suite thông thường ổn định.

## 41. Kiểm thử Spring Batch message writer

Nếu step dùng writer gửi message, integration test cần kiểm tra:

- Mỗi item tạo đúng một event hoặc số event theo contract.
- Payload được serialize đúng.
- Message key/partition key được chọn đúng.
- Exception khi publish làm chunk xử lý theo policy.
- Retry không tạo duplicate event ngoài ý muốn.
- Chunk commit/ack phù hợp với transport transaction.
- Job restart tiếp tục từ checkpoint và event ID ổn định.

Nếu writer publish nhiều message trong một chunk, test failure giữa các publish. Xác nhận consumer dedup hoặc outbox bảo đảm các message đã publish trước đó không tạo business effect trùng khi chunk retry.

## 42. Kiểm thử consumer và batch restart

Consumer có thể ghi database rồi ack message. Test nên mô phỏng crash window:

1. Nhận message eventId E1.
2. Ghi business result và inbox record trong cùng transaction.
3. Commit.
4. Giả lập process chết trước ack.
5. Broker giao lại E1.
6. Consumer kiểm tra inbox và không ghi business result lần nữa.
7. Consumer ack redelivery.

Với consumer chạy trong Spring Batch step, cần xác định message acknowledgement được quản lý bởi listener container hay transaction của step. Không giả định JobRepository checkpoint và broker offset/ack tự động atomic với nhau.

## 43. Payload size, chunk size và back-pressure

Chunk size lớn có thể tăng throughput nhưng cũng làm message payload lớn. Khi broker hoặc worker chậm, manager có thể tích lũy nhiều chunk đang chờ, gây áp lực bộ nhớ và queue storage.

Hãy đo:

- Kích thước trung bình và percentile của payload sau serialization.
- Số message in-flight.
- Queue/topic lag.
- Thời gian deserialize.
- Thời gian worker xử lý và commit.
- Số lần retry/redelivery.
- DLQ rate.

Back-pressure có thể được kiểm soát bằng concurrency, prefetch, bounded queue, broker quota và chunk size. Không tăng worker concurrency vô hạn nếu database hoặc downstream là bottleneck.

## 44. Observability cho serialization

Metric và log hữu ích:

- Serialization success/failure count.
- Deserialization failure count theo error type/schema version.
- Payload byte size.
- Serialization/deserialization latency.
- Unknown schema/type count.
- DLQ/quarantine count.
- Retry/redelivery count.
- Event type và schema version.
- Correlation ID và business key phù hợp.

Không log toàn bộ payload ở mức INFO. Với lỗi, log event ID, content type, schema version, payload size và error code; chỉ lưu payload mẫu đã làm sạch khi chính sách dữ liệu cho phép.

## 45. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Producer gửi được nhưng consumer parse lỗi | Hai phía dùng schema/target type khác nhau | Chốt contract và test producer-consumer |
| ClassNotFoundException khi nhận message | Dựa vào Java class name hoặc native serialization | Dùng DTO/wire schema độc lập và type mapping allowlist |
| Ngày giờ lệch | Thiếu timezone hoặc format không thống nhất | Dùng Instant/OffsetDateTime và ISO-8601 |
| Decimal sai scale/value | Coerce sang double hoặc contract không rõ | Dùng BigDecimal và test numeric semantics |
| Unknown enum làm consumer fail | Producer thêm enum value | Có policy unknown value hoặc version schema |
| Message quá lớn | Gửi entity/chunk không giới hạn | DTO nhỏ, chunk sizing, reference đến object storage |
| Retry tạo duplicate | Publish/DB commit/ack không atomic | Stable event ID, inbox/outbox và idempotency |
| Poison message retry mãi | Parse/schema error bị coi là transient | Retry có giới hạn và DLQ/quarantine |
| Type header load class tùy ý | Dùng polymorphic deserialization không giới hạn | Allowlist event type và DTO đích |
| Replay message cũ thất bại | Schema/class cũ đã bị xóa | Giữ schema compatibility trong retention window |
| Header và payload mâu thuẫn | Metadata được lặp ở nhiều nơi | Quy định nguồn chuẩn cho từng field |
| Batch restart gửi lại chunk | Một phần message đã publish trước failure | Event ID ổn định và consumer dedup |
| Consumer ack trước khi DB commit | Acknowledgement không phối hợp transaction | Transaction/ack mode phù hợp và inbox pattern |
| Log làm lộ dữ liệu | Ghi nguyên payload khi lỗi | Log metadata, business key và payload reference |

## 46. Quy trình thiết kế serialization payload

1. **Xác định boundary:** message đi qua Spring Integration, JMS, Kafka hay transport nào?
2. **Định nghĩa payload DTO:** chỉ chứa field consumer cần, có business key ổn định.
3. **Định nghĩa envelope/headers:** event type, schema version, correlation ID, content type và key.
4. **Chọn wire format:** JSON, Avro, Protobuf hoặc định dạng được consumer hỗ trợ.
5. **Cấu hình serializer/deserializer:** dùng đúng abstraction của transport, không trộn converter API.
6. **Quản lý schema/version:** quy định compatibility và thời gian hỗ trợ payload cũ.
7. **Giới hạn payload:** đo byte size, chunk size, nesting, collection và decompressed size.
8. **Bảo vệ deserialization:** allowlist type, validate schema, không native deserialize dữ liệu không tin cậy.
9. **Xác định delivery semantics:** ack, retry, redelivery, DLQ và idempotency.
10. **Tích hợp với Batch:** hiểu chunk transaction, checkpoint và side effect ngoài transaction.
11. **Viết contract test:** round-trip, wire fixture, schema compatibility và malformed payload.
12. **Viết integration test:** gửi/nhận qua broker, mô phỏng duplicate, failure và restart.
13. **Theo dõi production:** serialization errors, payload size, lag, retry và DLQ.

## 47. Những nguyên tắc cần nhớ

- Payload là dữ liệu chính của message; headers mang metadata vận chuyển, routing và correlation.
- Serialization chuyển object thành bytes/text; deserialization khôi phục object ở consumer.
- Tạo Spring Message không tự đồng nghĩa payload đã được serialize trên wire.
- Spring Messaging, Spring JMS và Kafka client có converter/serializer API khác nhau.
- JSON dễ debug; Avro/Protobuf phù hợp khi cần binary schema contract; tránh Java native serialization ở trust boundary.
- Dùng DTO/event payload riêng thay vì serialize toàn bộ entity hoặc object graph.
- Chuẩn hóa date/time, decimal, enum, null và unknown field behavior.
- Dùng event ID/business key ổn định để deduplicate; message ID và correlation ID có mục đích khác nhau.
- Version hóa schema và kiểm tra compatibility vì producer/consumer thường deploy lệch thời điểm.
- Remote chunking truyền chunk item; remote partitioning thường truyền execution/partition request nhỏ hơn.
- Giới hạn payload size, chunk size, nesting và decompressed size.
- Không cho payload tự chọn arbitrary Java class khi deserialize; dùng type allowlist.
- Lỗi parse/schema cố định thường không nên retry vô hạn; dùng DLQ/quarantine có thể replay.
- Broker acknowledgement không tự động atomic với business database commit hoặc JobRepository checkpoint.
- Dùng inbox/outbox, unique key và idempotency để xử lý redelivery/crash window.
- Kiểm thử wire contract, schema compatibility, malformed payload, broker integration và batch restart.

Serialization payload là contract dữ liệu giữa các thành phần của hệ thống batch và messaging. Khi payload DTO nhỏ, schema được version hóa, serializer/deserializer được cấu hình theo đúng transport và consumer có idempotency, các message có thể được truyền, replay và xử lý qua nhiều worker mà vẫn giữ được ý nghĩa nghiệp vụ.
