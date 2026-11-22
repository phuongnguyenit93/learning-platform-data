# Type header khi tiến hóa class

Spring Kafka có thể thêm **type headers** vào Kafka record khi dùng `JsonSerializer`. Những header này cho consumer biết JSON payload cần được deserialize thành kiểu Java nào. Cách làm này thuận tiện khi một topic chứa nhiều loại event, nhưng có thể tạo coupling giữa producer và consumer nếu header mang tên đầy đủ của class Java (fully qualified class name - FQCN).

Khi class được đổi tên, chuyển package hoặc tách sang module contract khác, consumer cũ có thể không tìm thấy class được ghi trong header. Một cách giảm coupling là dùng **type mapping**: producer gửi một token ổn định như `order-created`, còn mỗi consumer ánh xạ token đó tới DTO tương ứng trong codebase của mình. Type header chỉ chọn kiểu đích để deserialize; nó không thay thế schema, versioning hay quy tắc tương thích của payload.

Bài học thuộc chương **Schema và tiến hóa dữ liệu** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách type header hoạt động trong Spring Kafka, cách tiến hóa class an toàn giữa producer/consumer và cách kiểm thử tương thích trong quá trình triển khai nhiều phiên bản.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vai trò của JSON type headers trong Spring Kafka.
- Nhận biết các header như `__TypeId__`, `__ContentTypeId__` và `__KeyTypeId__`.
- Hiểu rủi ro khi type header chứa FQCN hoặc package của producer.
- Cấu hình `spring.json.type.mapping` ở producer và consumer.
- Dùng token ổn định để tách contract event khỏi tên class nội bộ.
- Chọn giữa type header và default target type.
- Xử lý topic có một event type hoặc nhiều event type.
- Phân biệt type header với event version và schema registry.
- Quản lý trusted packages và rủi ro từ type header không đáng tin cậy.
- Kiểm thử class rename, package move và rolling deployment giữa các phiên bản.

## 1. Type header giải quyết vấn đề gì?

Kafka record có key, value và headers. Khi value là JSON, byte payload không tự nói cho Jackson biết nó cần trở thành class Java nào. Spring Kafka có thể đính kèm type metadata vào record để consumer chọn kiểu deserialize.

Ví dụ producer gửi một object:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
~~~

Với `JsonSerializer`, Spring Kafka có thể ghi type header cùng JSON payload:

~~~text
Kafka record
├── key: order-1001
├── value: {"eventId":"evt-1","orderId":"order-1001",...}
└── headers
    └── __TypeId__: com.acme.orders.events.OrderCreated
~~~

Consumer dùng `JsonDeserializer` có thể đọc type header để xác định class đích. Điều này hữu ích khi cùng một topic chứa nhiều event class, nhưng tên class trở thành một phần metadata trao đổi giữa hai ứng dụng.

Nếu producer đổi package từ `com.acme.orders.events.OrderCreated` sang `com.acme.contract.OrderCreated`, consumer đang phụ thuộc FQCN cũ có thể không deserialize được record mới.

## 2. Các type header thường gặp

Spring Kafka JSON serializer có thể ghi các type header sau:

| Header | Vai trò |
|---|---|
| `__TypeId__` | Type ID của payload chính. |
| `__ContentTypeId__` | Type ID của phần tử nội dung, ví dụ kiểu phần tử trong collection. |
| `__KeyTypeId__` | Type ID của key khi key cũng được serialize theo JSON type metadata. |

Với một payload object đơn giản, `__TypeId__` thường là header quan trọng nhất. Khi payload là collection, map hoặc cấu trúc generic, content/key type metadata có thể được sử dụng để khôi phục kiểu phần tử.

Các giá trị header được lưu dưới dạng byte[] trong Kafka. Khi dùng ConsumerRecord, ứng dụng có thể đọc raw header. Khi dùng JsonDeserializer, framework có thể tiêu thụ type metadata trong quá trình deserialize.

Tên header và cách sử dụng phụ thuộc Spring Kafka JSON serializer/deserializer. Đừng tự giả định mọi serializer JSON đều ghi cùng bộ header.

## 3. Rủi ro khi type header chứa FQCN

Nếu không cấu hình type mapping, JSON serializer thường có thể ghi tên class Java làm type ID. Consumer sau đó cần tìm được class tương ứng trên classpath và được phép deserialize class đó.

Ví dụ producer và consumer phụ thuộc cùng FQCN:

~~~text
Producer:
com.acme.orders.events.OrderCreated

Kafka header:
__TypeId__ = com.acme.orders.events.OrderCreated

Consumer:
expects com.acme.orders.events.OrderCreated
~~~

Các thay đổi có thể phá tương thích:

- Đổi tên class.
- Chuyển class sang package khác.
- Chuyển DTO sang một module contract mới.
- Producer và consumer dùng các phiên bản thư viện không đồng bộ.
- Consumer không có dependency chứa class của producer.
- Class cùng tên nhưng khác cấu trúc hoặc ý nghĩa nghiệp vụ.

Một consumer không nên phải import toàn bộ module nội bộ của producer chỉ để deserialize event. Event contract nên độc lập với cấu trúc package của một service cụ thể.

## 4. Type mapping: token ổn định thay cho tên class

Spring Kafka hỗ trợ property `spring.json.type.mapping` để ánh xạ token sang class Java cục bộ.

Ví dụ producer ánh xạ class của mình sang token `order-created`:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.events.OrderCreated
~~~

Consumer ánh xạ cùng token tới DTO của chính nó:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
~~~

Producer và consumer có thể dùng class khác package, nhưng type token trên Kafka vẫn là `order-created`.

~~~text
Producer class
com.acme.orders.events.OrderCreated
          |
          | producer type mapping
          v
Kafka __TypeId__ = order-created
          |
          | consumer type mapping
          v
Consumer class
com.acme.fulfillment.contract.OrderCreated
~~~

Type mapping giúp loại bỏ phụ thuộc vào FQCN của producer. Tuy nhiên, hai class vẫn phải tương thích về cấu trúc JSON và ý nghĩa field. Token ổn định không tự chuyển đổi schema hoặc sửa dữ liệu không tương thích.

## 5. Cấu hình đầy đủ cho producer và consumer

Ví dụ Spring Boot cho hai ứng dụng độc lập:

**Producer application**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.events.OrderCreated
~~~

**Consumer application**

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
        spring.json.use.type.headers: true
~~~

Cần bảo đảm producer và consumer cùng thống nhất token. Tên class sau dấu hai chấm là class cục bộ của từng ứng dụng, không cần giống nhau.

Trong dự án có nhiều ProducerFactory hoặc ConsumerFactory, hãy kiểm tra properties được áp dụng cho đúng factory. Một cấu hình ở `spring.kafka.producer.properties` không tự động áp dụng cho một ProducerFactory tự tạo mà không dùng Boot properties.

## 6. Dùng type mapping cho nhiều event type

Type mapping đặc biệt hữu ích khi một topic chứa nhiều loại event.

Ví dụ producer:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: >-
          order-created:com.acme.orders.OrderCreated,
          order-cancelled:com.acme.orders.OrderCancelled
~~~

Consumer có thể ánh xạ các token tới contract riêng:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract
        spring.json.type.mapping: >-
          order-created:com.acme.fulfillment.contract.OrderCreated,
          order-cancelled:com.acme.fulfillment.contract.OrderCancelled
~~~

Khi nhận token `order-created`, deserializer chọn DTO OrderCreated. Với `order-cancelled`, nó chọn OrderCancelled.

Các token phải duy nhất trong phạm vi mapping của ứng dụng và cần được quản lý như một phần của event contract. Không đổi token chỉ vì class Java được đổi tên hoặc refactor package.

Nếu consumer không cần hỗ trợ một loại event, nên cân nhắc tách topic hoặc định tuyến rõ ràng thay vì tạo một mapping rộng cho mọi class.

## 7. Type header và default target type

Không phải ứng dụng nào cũng cần type header. Nếu một topic chỉ chứa một kiểu payload cố định, consumer có thể cấu hình default target type.

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.acme.fulfillment.contract.OrderCreated
        spring.json.trusted.packages: com.acme.fulfillment.contract
~~~

Khi `spring.json.use.type.headers=false`, consumer không dùng type header để quyết định kiểu đích và dùng default value type đã cấu hình.

Cách này phù hợp khi topic có một event contract cố định. Nếu topic chứa nhiều loại event, một default type duy nhất không đủ để chọn DTO; hãy dùng type mapping/type headers hoặc một envelope có discriminator rõ ràng và deserializer phù hợp.

Không nên tắt type headers ở consumer mà vẫn kỳ vọng nó tự phân biệt nhiều class bằng mapping. Mapping cần type ID đầu vào để chọn class.

## 8. Khi nào nên tắt việc ghi type header?

Producer có thể không ghi type metadata nếu consumer đã biết trước target type và contract của topic chỉ có một loại payload.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
~~~

Consumer tương ứng dùng default type:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.acme.contract.OrderCreated
        spring.json.trusted.packages: com.acme.contract
~~~

Tắt type header làm record ít phụ thuộc vào metadata class, nhưng producer và consumer phải thống nhất topic chỉ mang một kiểu payload hoặc có cơ chế phân biệt kiểu khác.

Nếu một topic chứa nhiều event class, không tắt type header trước khi có giải pháp discriminator/deserializer thay thế.

## 9. Header removal sau deserialize

Sau khi JsonDeserializer dùng type header để tạo object, Spring Kafka có thể loại bỏ type headers khỏi record theo cấu hình mặc định của phiên bản. Điều này giúp metadata nội bộ phục vụ deserialize không tiếp tục xuất hiện như application header ở listener.

Có thể cấu hình giữ lại type headers nếu ứng dụng cần kiểm tra metadata sau deserialize:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.remove.type.headers: false
~~~

Nếu cần audit chính xác raw header, hãy kiểm thử hành vi với phiên bản Spring Kafka thực tế. Khi deserializer loại header, listener có thể không còn nhìn thấy chúng trong ConsumerRecord headers.

Không nên dựa vào type header sau deserialize để xác thực nguồn gửi. Header chỉ là metadata do producer cung cấp, không phải chữ ký số hay bằng chứng danh tính.

## 10. Type header không phải event version

Type ID và event version trả lời hai câu hỏi khác nhau:

- Type ID: payload thuộc loại event/class nào?
- Event version: contract của loại event đó đang ở phiên bản nào?

Ví dụ:

~~~text
__TypeId__ = order-created
event_version = 2
~~~

Type mapping có thể vẫn giữ token `order-created` trong khi schema được mở rộng tương thích. Khi thay đổi không tương thích, có thể dùng token versioned như `order-created-v2` hoặc giữ token loại event và version riêng theo quy ước contract.

Không dùng tên class như `OrderCreatedV2` làm cơ chế versioning duy nhất. Class name là chi tiết triển khai; event version cần có ý nghĩa rõ ràng với mọi producer và consumer.

## 11. Type mapping không tự bảo đảm schema compatibility

Giả sử consumer ánh xạ token `order-created` tới class:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        String currency
) {}
~~~

Producer có thể thêm field mới:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        String currency,
        String salesChannel
) {}
~~~

Việc consumer có deserialize được hay không còn phụ thuộc cấu hình Jackson, kiểu field, constructor, nullability và quy tắc xử lý unknown properties. Type mapping chỉ giúp chọn class đích.

Khi tiến hóa schema, cần đánh giá:

- Thêm field optional có default hoặc cách xử lý null rõ ràng.
- Xóa field consumer cũ còn cần hay không.
- Đổi kiểu dữ liệu có làm JSON không deserialize được không.
- Đổi enum có khiến consumer cũ không nhận giá trị mới không.
- Đổi format timestamp, decimal hoặc identifier.
- Producer mới có thể chạy cùng consumer cũ trong rolling deployment không.
- Consumer mới có thể đọc record cũ còn trong retention không.

Type header và schema compatibility là hai lớp cần quản lý riêng.

## 12. Package move và class rename an toàn

Giả sử producer đổi package:

~~~text
Before:
com.acme.orders.events.OrderCreated

After:
com.acme.contracts.orders.OrderCreated
~~~

Nếu Kafka header mang FQCN, consumer phụ thuộc tên cũ có thể lỗi. Với type mapping, producer chỉ cần giữ token ổn định:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: order-created:com.acme.contracts.orders.OrderCreated
~~~

Consumer vẫn giữ mapping:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
~~~

Việc refactor class phía producer không làm thay đổi token trên wire. Cần triển khai consumer tương thích payload trước hoặc đồng thời theo chiến lược rollout, sau đó mới phát payload có thay đổi schema.

Không đổi token trong cùng một đợt refactor nếu không có kế hoạch migration cho mọi consumer đang đọc topic.

## 13. Rolling deployment giữa producer và consumer

Trong rolling deployment, producer và consumer có thể chạy nhiều phiên bản cùng lúc. Type header cần được thiết kế để các phiên bản giao tiếp được trong giai đoạn overlap.

Một trình tự an toàn:

1. Xác định token type hiện tại và contract JSON đang được phát.
2. Triển khai consumer mới có mapping cho token hiện tại và hỗ trợ payload mới nếu cần.
3. Xác minh consumer mới đọc được cả record cũ còn trong topic.
4. Triển khai producer mới nhưng tiếp tục phát token ổn định.
5. Nếu schema thay đổi, chỉ phát field/giá trị mới sau khi consumer tương thích đã sẵn sàng.
6. Theo dõi lỗi deserialize và DLT trong suốt rollout.
7. Chỉ bỏ hỗ trợ contract cũ sau khi hết thời gian retention và không còn consumer cũ.

Nếu cần token mới, consumer phải được triển khai hỗ trợ token đó trước khi producer phát record sử dụng token mới. Nếu producer phát trước, consumer cũ có thể không biết token và deserialize thất bại.

## 14. Trusted packages và type header không đáng tin cậy

JsonDeserializer có cơ chế trusted packages để giới hạn package class được phép deserialize khi type header chứa class name.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.acme.fulfillment.contract,com.acme.shared.events
~~~

Không nên đặt `*` trong production nếu không có lý do đặc biệt và đánh giá bảo mật. Chỉ tin cậy package cần thiết cho contract.

Trusted packages là allowlist cho quá trình type resolution, không phải cơ chế authentication. Producer vẫn có thể gửi payload và header giả mạo; consumer cần xác thực dữ liệu, kiểm tra quyền truy cập topic và không dùng type header làm căn cứ phân quyền.

Type mapping token tới class cục bộ giúp giảm việc phải load class theo FQCN bên ngoài, nhưng vẫn cần kiểm soát mapping và input. Không map token không giới hạn tới class tùy ý từ payload.

## 15. Polymorphic payload và class hierarchy

Một số ứng dụng dùng interface hoặc abstract class làm kiểu chung:

~~~java
public sealed interface OrderEvent
        permits OrderCreated, OrderCancelled {}

public record OrderCreated(String orderId) implements OrderEvent {}

public record OrderCancelled(String orderId, String reason)
        implements OrderEvent {}
~~~

Producer có thể serialize implementation cụ thể và ghi type mapping tương ứng. Consumer cần mapping cho từng subtype được phép.

Nếu consumer chỉ nhận `OrderEvent` nhưng không có mapping cho subtype, deserialize có thể thất bại hoặc không tạo được kiểu mong muốn. Hãy xác định rõ danh sách subtype hợp lệ và kiểm thử từng loại.

Đừng mở rộng trusted packages quá rộng chỉ để hỗ trợ polymorphism. Danh sách subtype nên là một phần contract được quản lý, review và version hóa.

## 16. Đọc type header để điều tra

Có thể đọc trực tiếp header từ ConsumerRecord:

~~~java
Header typeHeader = record.headers().lastHeader("__TypeId__");

String typeId = typeHeader == null || typeHeader.value() == null
        ? null
        : new String(typeHeader.value(), StandardCharsets.UTF_8);
~~~

Đoạn code chỉ đọc raw header nếu nó còn tồn tại sau deserialize. Nếu JsonDeserializer đã loại type headers theo cấu hình, giá trị có thể không còn trong record listener.

Để điều tra raw type metadata, có thể dùng consumer test với ByteArrayDeserializer hoặc cấu hình `spring.json.remove.type.headers=false`. Không ghi toàn bộ payload hoặc header nhạy cảm vào log production.

Khi thấy type ID là FQCN, kiểm tra class đó có tồn tại trên consumer classpath và có nằm trong trusted packages hay không. Khi thấy token, kiểm tra mapping token ở consumer.

## 17. Những lỗi thường gặp khi tiến hóa class

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException` | Header chứa FQCN không còn tồn tại ở consumer | Dùng type mapping ổn định hoặc giữ compatibility class trong giai đoạn migration. |
| Type ID không được mapping | Token mới chưa có trong consumer | Triển khai mapping consumer trước khi producer phát token mới. |
| Untrusted type | Package không nằm trong trusted packages | Thêm đúng package contract đã review; không mở wildcard tùy tiện. |
| JSON mapping error | Payload field/type không tương thích với DTO | Kiểm tra schema, field, enum và Jackson config. |
| Consumer chọn sai class | Header/type mapping bị cấu hình sai hoặc token trùng | Chuẩn hóa token và test mapping hai phía. |
| Type header không xuất hiện | Producer tắt add type headers hoặc dùng serializer khác | Kiểm tra serializer và cấu hình hiệu lực. |
| Listener không thấy type header | Deserializer đã remove type headers | Cấu hình giữ header nếu có nhu cầu audit. |
| Một topic có nhiều event nhưng default type cố định | Consumer không thể chọn subtype đúng | Dùng type mapping/type header hoặc discriminator strategy. |

Khi deserialize thất bại, record có thể đi vào error handler/DLT. Cần giữ raw bytes và headers để điều tra, vì deserialize chưa thành công đồng nghĩa listener có thể chưa nhận được object.

## 18. Kiểm thử type header và class evolution

Một bộ integration test nên xác minh metadata thực sự nằm trên Kafka record và consumer ánh xạ đúng class cục bộ.

| Kịch bản | Điều cần xác minh |
|---|---|
| Producer mapping | Header chứa token `order-created`, không chứa FQCN nội bộ. |
| Consumer mapping | Token được deserialize thành DTO đúng package consumer. |
| Package move | Producer đổi package nhưng token không đổi; consumer vẫn đọc được. |
| Class rename | Refactor class không làm thay đổi wire token. |
| Multiple event types | Mỗi token chọn đúng subtype. |
| Unknown token | Consumer thất bại có kiểm soát và record đi qua error path. |
| Default type | Topic một loại payload deserialize đúng khi không dùng type header. |
| Type headers disabled | Producer/consumer vẫn tương thích theo cấu hình default type/discriminator. |
| Trusted package | Class không được tin cậy bị từ chối. |
| Rolling compatibility | Consumer cũ/mới đọc được tập payload được cam kết hỗ trợ. |
| Header retention | Type header còn hoặc bị remove đúng cấu hình. |
| Raw DLT | Payload và type header được bảo toàn để điều tra lỗi deserialize. |

Ví dụ kiểm tra type header bằng ConsumerRecord:

~~~java
Header header = received.headers().lastHeader("__TypeId__");

assertThat(header).isNotNull();
assertThat(new String(header.value(), StandardCharsets.UTF_8))
        .isEqualTo("order-created");
~~~

Để xác minh class đích, gửi record bằng producer thật và nhận bằng consumer có JsonDeserializer cùng type mapping của ứng dụng. Unit test riêng cho map string không đủ để chứng minh serializer/deserializer đang dùng đúng properties.

Dùng EmbeddedKafka hoặc Testcontainers và chờ record bằng Awaitility/latch có timeout. Không dùng Thread.sleep cố định.

## 19. Quy ước quản lý type token

Type token là một phần giao thức giữa producer và consumer. Nên có quy ước:

- Dùng tên ổn định, dễ hiểu và không chứa package Java.
- Không tái sử dụng token cho một ý nghĩa event khác.
- Giữ token khi chỉ refactor class hoặc package.
- Dùng token versioned khi cần phân biệt contract không tương thích.
- Công bố mapping trong tài liệu contract của event.
- Triển khai consumer hỗ trợ token trước producer phát token mới.
- Có test cho mọi token đang được phát.
- Không dùng tên class nội bộ hoặc tên module làm contract công khai.
- Quản lý deprecation token cùng thời gian retention và lịch rollout.

Ví dụ token:

| Token | Ý nghĩa |
|---|---|
| `order-created` | Sự kiện tạo đơn hàng. |
| `order-cancelled` | Sự kiện hủy đơn hàng. |
| `order-created-v2` | Contract phiên bản 2 khi thay đổi không tương thích cần tách token. |

Token không nhất thiết phải có hậu tố version nếu contract thay đổi tương thích. Quyết định version hóa phải theo chính sách schema của hệ thống, không chỉ theo việc Java class có đổi tên hay không.

## 20. Khi nào nên dùng Schema Registry?

Type mapping giải quyết việc chọn class Java ở consumer. Nó không cung cấp registry lưu schema, compatibility rules, schema ID hoặc hỗ trợ đa ngôn ngữ đầy đủ.

Nếu hệ thống có nhiều service, nhiều ngôn ngữ hoặc cần kiểm soát schema evolution chặt chẽ, cân nhắc Avro, Protobuf hoặc JSON Schema cùng Schema Registry phù hợp với nền tảng.

| Nhu cầu | Type mapping của Spring Kafka | Schema Registry |
|---|---|---|
| Chọn class Java từ type token | Có | Không phải mục đích chính |
| Tách FQCN producer/consumer | Có | Có thể tách qua schema contract/serializer |
| Lưu trữ và quản lý schema version | Không | Có |
| Kiểm tra compatibility theo policy | Không tự có | Có, tùy registry và cấu hình |
| Đa ngôn ngữ | Hạn chế nếu phụ thuộc Jackson/Java | Phù hợp hơn với schema format đa ngôn ngữ |
| Schema ID và lookup schema | Không | Có |

Có thể dùng type mapping cho ứng dụng JSON đơn giản với contract được quản lý thủ công. Khi yêu cầu governance tăng, schema registry giúp kiểm soát thay đổi trước khi producer phát dữ liệu mới.

## 21. Bài tập tổng hợp: refactor OrderCreated mà không đổi wire contract

Hãy có hai ứng dụng:

- Producer trước đây dùng `com.acme.orders.events.OrderCreated`.
- Consumer dùng `com.acme.fulfillment.contract.OrderCreated`.

Yêu cầu:

1. Cấu hình producer JsonSerializer với token `order-created`.
2. Cấu hình consumer JsonDeserializer ánh xạ token về DTO của consumer.
3. Gửi record và xác minh Kafka header `__TypeId__` là token, không phải FQCN.
4. Đổi package class producer nhưng giữ token.
5. Xác minh consumer không cần thay package mapping.
6. Thêm event type `order-cancelled` và mapping subtype tương ứng.
7. Thử consumer thiếu mapping cho token mới và quan sát error handling/DLT.
8. Tắt type headers cho topic một loại event và cấu hình default target type.
9. Thử trusted package không hợp lệ.
10. Kiểm tra header removal sau deserialize.
11. Thêm field optional vào payload và xác minh consumer cũ xử lý được theo contract.
12. Mô phỏng rolling deployment với producer/consumer hai phiên bản.
13. Viết integration test cho class rename, package move và multiple event types.
14. Ghi quy ước type token và quy trình deprecate token cũ.

Bài tập hoàn thành khi producer có thể refactor class nội bộ mà wire type token không đổi, consumer ánh xạ được token tới DTO riêng và payload vẫn tuân thủ schema compatibility.

## 22. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Type metadata | `__TypeId__` và related headers | Đọc và giải thích được type header. |
| 2. FQCN coupling | Package/class rename | Mô tả được vì sao consumer cũ có thể lỗi. |
| 3. Type mapping | Token-to-class mapping | Producer/consumer dùng class khác package nhưng cùng token. |
| 4. Multiple types | Polymorphic events | Ánh xạ đúng từng event subtype. |
| 5. Default target | Một topic, một payload type | Deserialize được khi không dùng type headers. |
| 6. Header policy | Add/use/remove type headers | Kiểm soát được vòng đời metadata. |
| 7. Schema evolution | Field và event version | Phân biệt type token với schema version. |
| 8. Security | Trusted packages và untrusted headers | Giới hạn type resolution an toàn. |
| 9. Deployment | Rolling upgrade và backward compatibility | Consumer mới hỗ trợ record cũ và producer mới. |
| 10. Testing | Round-trip và compatibility matrix | Kiểm tra được wire header cùng class đích. |

Bài học hoàn thành khi bạn có thể giải thích rủi ro của FQCN trong type header, cấu hình type mapping hai phía, chọn default target type cho topic đơn loại và kiểm thử class/package evolution mà không làm thay đổi wire contract ngoài dự kiến.

Type header giúp Spring Kafka chọn class Java khi deserialize JSON, nhưng class Java là chi tiết triển khai có thể thay đổi. Dùng token ổn định để giảm coupling, quản lý event version và schema compatibility riêng, giới hạn trusted packages và kiểm thử producer/consumer trong giai đoạn rolling deployment.

