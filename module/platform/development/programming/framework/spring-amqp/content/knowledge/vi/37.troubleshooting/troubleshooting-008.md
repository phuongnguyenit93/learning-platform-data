# MessageConversionException, sai content type hoặc kiểu JSON

Một producer gửi sự kiện `OrderCreated` qua `RabbitTemplate`. Trên RabbitMQ Management UI, message đã nằm trong queue và `@RabbitListener` đã được đăng ký. Nhưng consumer không chạy vào dòng đầu tiên của handler, log liên tục hiển thị `MessageConversionException`, và message bị reject, redeliver hoặc chuyển vào dead-letter queue (DLQ).

Đây thường **không phải lỗi định tuyến exchange–binding–queue**. Message đã tới nơi; thất bại xảy ra khi Spring AMQP **diễn giải bytes thành kiểu Java mà listener mong đợi**. Nguyên nhân có thể là `contentType` không phù hợp, JSON bị serialize hai lần thành một chuỗi, body không phải JSON, type metadata `__TypeId__` trỏ đến class sai, DTO đổi cấu trúc, hoặc cấu hình converter không thống nhất giữa producer và consumer.

Bài thuộc chương **Chẩn đoán sự cố** của module **SPRING_AMQP**. Mục tiêu là có quy trình xác minh từ **raw AMQP message → content type/encoding → message converter → listener argument → nghiệp vụ**, đồng thời bảo vệ độ tin cậy bằng publisher confirms, ACK đúng thời điểm, retry có giới hạn, DLQ và idempotency.

> **Phạm vi phiên bản:** Ví dụ Java dùng phong cách Spring Boot 3.x / Spring AMQP 3.x với `Jackson2JsonMessageConverter`. Tên class và API JSON converter có thể đổi khi nâng lên dòng Spring AMQP/Jackson mới hơn. Luôn đối chiếu dependency thực tế; các nguyên tắc về bytes, metadata, type inference và lỗi trước listener vẫn giữ giá trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi **publish/routing**, **AMQP message conversion**, **method argument conversion**, **validation** và **business handler**.
2. Kiểm tra `contentType`, `contentEncoding`, body bytes, charset, compression và type headers trước khi kết luận lỗi nằm ở DTO.
3. Giải thích sự khác biệt giữa `SimpleMessageConverter`, JSON converter dùng Jackson và cấu hình message converter cho `RabbitTemplate`/listener container.
4. Nhận diện trường hợp JSON hợp lệ nhưng **sai hình dạng**: JSON string thay vì object, array thay vì object, class/field không tương thích.
5. Hiểu `__TypeId__`, inferred listener argument type và quyền ưu tiên type mapping; tránh phụ thuộc tên Java class xuyên dịch vụ.
6. Xử lý `MessageConversionException` ném ra **trước khi phương thức `@RabbitListener` chạy**.
7. Phân loại lỗi không thể phục hồi để reject/DLQ; không retry vô hạn hoặc requeue khiến poison message chiếm queue.
8. Thiết kế bài kiểm thử, metric, log an toàn và runbook chẩn đoán sự cố chuyển đổi payload.

## 2. Đường đi của message và nơi conversion có thể thất bại

Một message RabbitMQ AMQP 0-9-1 về cơ bản gồm:

- **Body**: dãy bytes.
- **Properties**: `contentType`, `contentEncoding`, `messageId`, `correlationId`, delivery mode, headers, timestamp và các thông tin khác.
- **Routing context**: message được publish vào exchange với routing key, sau đó broker chuyển vào queue theo binding.

Broker **không cần hiểu JSON schema của nghiệp vụ** mới đưa message vào queue. Nó định tuyến chủ yếu theo exchange/routing key/binding và các tính năng/policy liên quan.

~~~mermaid
flowchart LR
    P["RabbitTemplate / producer"] -->|"Serialized bytes + properties"| E["Exchange"]
    E -->|"Binding"| Q["Queue"]
    Q --> D["AMQP delivery"]
    D --> MC{"MessageConverter"}
    MC -->|"DTO hợp lệ"| LA["Listener argument"]
    LA --> SV["Business service"]
    MC -->|"Sai bytes/contentType/type"| ER["Conversion exception"]
    ER --> EH["Container error handling"]
    EH --> DLQ["Reject / DLX / DLQ"]
~~~

### 2.1. Tầng chuyển đổi 1: đối tượng Java thành AMQP message

Producer gọi:

~~~java
rabbitTemplate.convertAndSend(
        "orders.exchange", "orders.created", event);
~~~

`RabbitTemplate` sử dụng **message converter đang được cấu hình trên template** để tạo bytes và properties. Converter gửi JSON thường cho body dạng `{"eventId":"..."}` và property `contentType=application/json`. Một converter khác có thể gửi String dưới dạng text, hoặc byte[] dưới dạng `application/octet-stream`.

Nếu producer gọi:

~~~java
rabbitTemplate.send(
        "orders.exchange", "orders.created", rawAmqpMessage);
~~~

thì message đã chứa body/properties sẵn; không nên giả định template sẽ tự chuyển đổi lại nội dung như `convertAndSend()`.

### 2.2. Tầng chuyển đổi 2: AMQP bytes thành Java argument

Consumer:

~~~java
@RabbitListener(queues = "orders.queue")
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

Trước khi `handle()` thực sự được gọi, listener adapter/converter phải diễn giải message thành `OrderCreated`. Có hai mức cần phân biệt:

1. **AMQP message conversion:** từ `org.springframework.amqp.core.Message` (bytes/properties) sang Java payload bằng message converter (ví dụ Jackson).
2. **Method argument conversion:** payload được gắn vào tham số phương thức, có thể đi qua argument resolver/conversion service và validation.

Một lỗi ở giai đoạn bất kỳ **có thể khiến handler chưa được gọi**. Thêm `try/catch` bên trong `handle()` sẽ không bắt được lỗi phát sinh trước khi phương thức được thực thi.

## 3. Bảng triệu chứng để khoanh vùng trong vài phút đầu

| Triệu chứng | Vị trí có khả năng lỗi | Thao tác đầu tiên |
| --- | --- | --- |
| Queue không nhận message | Producer/routing/binding, publish blocked | Kiểm tra exchange, routing key, mandatory returns, publisher confirms |
| Queue có message nhưng listener không được gọi | Conversion/argument mapping hoặc container startup | Kiểm tra stack trace đầy đủ và content type |
| `Cannot convert from [[B] to [OrderCreated]` hoặc tương tự | Body còn `byte[]`, converter không xử lý được JSON | Kiểm tra converter của listener và `contentType` |
| `Unrecognized token` / `Unexpected character` | Body không phải JSON hợp lệ | Xem raw body theo cách an toàn, charset/compression |
| `Cannot deserialize value of type ... from String value` | JSON string thay vì object, hoặc field type sai | Kiểm tra JSON shape và code gửi |
| `Cannot construct instance` / `InvalidDefinitionException` | DTO thiếu creator, thiếu module hoặc type không thể dựng | Kiểm tra record/constructor/Jackson modules |
| `InvalidTypeIdException` / type id không giải quyết được | Header type hoặc polymorphic subtype không tương thích | Kiểm tra `__TypeId__`, allowlist và schema |
| `ListenerExecutionFailedException` bọc conversion exception | Adapter/container lỗi trước handler | Xem *root cause*, không xử lý dựa vào wrapper |
| Payload vào handler được nhưng validation lỗi | Bean Validation hoặc business rules | Phân biệt schema với input invalid và logic handler |
| Cùng message redeliver liên tục | Requeue/retry policy sai đối với poison | Kiểm tra error handler, reject, DLX/DLQ |

**Quy tắc quan trọng:** exception name ở dòng log đầu có thể là wrapper; cần đọc chuỗi `Caused by` tới nguyên nhân gốc. `MessageConversionException` có thể xuất hiện ở nhiều package, đặc biệt `org.springframework.amqp.support.converter` và `org.springframework.messaging.converter`, tùy tầng chuyển đổi.

## 4. Những thông tin phải thu thập trước khi sửa code

Đối với một message lỗi, ghi lại bộ bằng chứng tối thiểu:

| Nhóm | Trường cần kiểm tra | Vì sao |
| --- | --- | --- |
| Nguồn | Producer service, version, deployment, thời điểm | Phân biệt bản deploy mới với dữ liệu cũ |
| Định tuyến | Exchange, routing key, vhost, queue, binding | Xác minh đúng đường gửi |
| Media | `contentType`, `contentEncoding`, body length | Xác minh định dạng trên wire |
| Type metadata | `__TypeId__`, `__ContentTypeId__`, `__KeyTypeId__` khi có | Xác định source của Java type |
| Correlation | `messageId`, `correlationId`, `eventId` ở payload | Theo dõi một event qua retry/DLQ |
| Consumer | Spring AMQP version, converter bean, listener method signature | Kiểm tra cách suy luận kiểu |
| Exception | Exception class, root cause, stack trace, field/path Jackson | Tìm đúng điểm hỏng |
| Retry | Redelivered flag, `x-death`, retry attempts nếu có | Xem có poison loop hay không |
| Business | Có vào handler không, DB đã commit chưa | Đánh giá duplicate/mất side effect |

**Không log nguyên body trên production một cách mặc định.** JSON có thể chứa PII, token hoặc thông tin thanh toán. Trước tiên ghi `eventId`, byte length, content type, schema version, error category và **hash có kiểm soát**; chỉ giữ raw sample trong kho quarantine có mã hóa và quyền truy cập phù hợp nếu thực sự cần.

### 4.1. Một log chẩn đoán hữu ích

~~~text
service=orders-consumer
queue=orders.events.queue
eventId=E42
producerVersion=orders-api-2.4
contentType=text/plain
contentEncoding=UTF-8
bodyBytes=187
typeId=com.example.shared.OrderCreated
stage=AMQP_MESSAGE_CONVERSION
errorClass=UNSUPPORTED_CONTENT_TYPE
redelivered=false
~~~

Đây là **định dạng log minh họa của ứng dụng**, không phải mọi field được Spring AMQP xuất tự động. Đặc biệt, nếu lỗi xảy ra trước khi deserialize, `eventId` có thể chưa đọc được từ payload; có thể sử dụng `messageId` đã đặt bởi producer và correlation ID trong message properties.

## 5. `contentType`: metadata ảnh hưởng converter, không phải lời bảo đảm

Một message chứa bytes trông giống JSON không có nghĩa consumer chắc chắn parse JSON. Converter còn xét **`contentType`** hoặc các điều kiện hỗ trợ khác.

| Content type | Body ví dụ | Kết quả cần dự kiến |
| --- | --- | --- |
| `application/json` | `{"orderId":"O-1"}` | JSON converter phù hợp thường deserialize |
| `application/octet-stream` | Bytes của JSON | Tùy converter và phiên bản; không nên mặc định |
| `text/plain` | `{"orderId":"O-1"}` | Có thể bị coi là text/bytes thay vì JSON |
| `application/x-protobuf` | Protobuf binary | Cần converter Protobuf, không dùng Jackson JSON trực tiếp |
| `application/gzip` hoặc metadata nén riêng | GZIP bytes | Cần giải nén đúng trước khi parse |
| `application/json` | Bytes Java serialization | Media type nói sai; JSON parsing sẽ thất bại |

### 5.1. Trường hợp thiếu content type

Spring AMQP Jackson JSON converters ở một số phiên bản có cơ chế **giả định JSON** khi `contentType` thiếu hoặc là `application/octet-stream`, ví dụ tùy chọn `assumeSupportedContentType`. Tuy nhiên hành vi/giá trị mặc định **phụ thuộc class và phiên bản converter**, và client khác không bắt buộc chia sẻ giả định đó.

Vì vậy **đừng dạy một quy tắc tuyệt đối** rằng “thiếu content type thì Jackson luôn thất bại” hoặc “luôn parse được”. Chuẩn hợp đồng producer/consumer nên yêu cầu **`contentType=application/json` rõ ràng** và có test cho các message legacy thiếu metadata.

### 5.2. Vì sao sửa mỗi content type đôi khi không đủ?

Giả sử body là:

~~~text
"not-json"
~~~

Đây là một JSON **string** hợp lệ, nhưng listener cần một **object `OrderCreated`**. Chỉnh property `contentType` sang `application/json` chỉ bảo converter được phép parse; không thay được hình dạng JSON. Cần sửa producer để gửi object phù hợp, hoặc đổi hợp đồng consumer trong một migration được kiểm soát.

Ngược lại, nếu body thực sự là protobuf nhưng bị gắn `application/json`, sửa DTO hay type headers không thể biến bytes protobuf thành JSON.

## 6. `contentEncoding` và charset: body đúng về cấu trúc nhưng sai bytes

Producer và consumer cần đồng thuận:

- Encoding của text, thường là UTF-8.
- Có nén/mã hóa body hay không, thứ tự giải nén/giải mã.
- Content type và version của schema.
- Cách xử lý non-ASCII: tên người, tiếng Việt, ký tự emoji.
- Có BOM hoặc ký tự không hợp lệ trước dấu mở JSON không.

Ví dụ JSON hợp lệ:

~~~json
{
  "eventId": "81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c",
  "orderId": "ORD-1001",
  "customerNote": "Giao hàng trước 17 giờ"
}
~~~

Nếu producer mã hóa UTF-8 mà consumer diễn giải nhầm thành một charset khác, trường text có thể hỏng hoặc JSON parser gặp lỗi khi byte không hợp lệ. Với JSON business events, **UTF-8 là lựa chọn thông dụng và nên thống nhất**.

### 6.1. Body bị nén nhưng gửi như JSON

Một mẫu lỗi:

~~~text
body: 1F 8B 08 ...        # GZIP bytes
contentType: application/json
contentEncoding: UTF-8   # sai hợp đồng nếu đây vẫn là bytes nén
~~~

Jackson không thể parse body GZIP trực tiếp. Cần thống nhất **cơ chế decompression** trước JSON conversion và khai báo metadata nén nhất quán. Không “thử mọi decoder” vô điều kiện trên payload từ nguồn không đáng tin cậy vì tạo rủi ro bảo mật và tài nguyên.

## 7. `SimpleMessageConverter` khác `Jackson2JsonMessageConverter`

`SimpleMessageConverter` và JSON converter có mục tiêu khác nhau:

| Input gửi | Converter producer | Body/properties thường gặp | Consumer JSON DTO |
| --- | --- | --- | --- |
| `String` | `SimpleMessageConverter` | Bytes text, `text/plain` | Có thể không parse thành DTO |
| `byte[]` | `SimpleMessageConverter` | Raw bytes, binary content type | Không tự hiểu schema |
| Serializable Java object | `SimpleMessageConverter` | Java serialized representation | Không tương thích JSON; có rủi ro an toàn |
| `OrderCreated` | Jackson JSON converter | JSON object + `application/json` | Hoạt động nếu DTO/schema/type đúng |
| JSON text `"{...}"` | Jackson JSON converter | **JSON string có escape** | Sai nếu listener cần object |
| Raw `Message` đã set body/properties | `RabbitTemplate.send()` | Đúng những gì đã set | Phụ thuộc body và metadata |

**Không dùng Java native serialization như giải pháp lâu dài** cho messaging xuyên dịch vụ. Nó phụ thuộc classpath, version và có rủi ro deserialization. Với dữ liệu từ nguồn bên ngoài, phải giới hạn kiểu được phép deserialize và ưu tiên format/schema rõ ràng.

### 7.1. Lỗi điển hình: publisher gửi một chuỗi đã là JSON

Producer tạo JSON text trước:

~~~java
String jsonText = """
        {"eventId":"81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c",
         "orderId":"ORD-1001"}
        """;

rabbitTemplate.convertAndSend(
        "orders.exchange", "orders.created", jsonText);
~~~

Nếu `RabbitTemplate` dùng Jackson converter, nó nhận một **Java String**, nên có thể serialize thành **JSON string**:

~~~json
"{\"eventId\":\"81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c\",\"orderId\":\"ORD-1001\"}"
~~~

Listener đợi `OrderCreated` sẽ gặp lỗi kiểu “cannot deserialize object from String” hoặc lỗi conversion khác. Đây là **double serialization**: JSON object bị bọc trong một JSON string.

**Cách sửa ưu tiên:** gửi **DTO**, không gửi JSON text vào API yêu cầu object:

~~~java
OrderCreated event = new OrderCreated(
        UUID.fromString("81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c"),
        "ORD-1001",
        Instant.parse("2026-11-26T02:00:00Z"));

rabbitTemplate.convertAndSend(
        "orders.exchange", "orders.created", event);
~~~

Nếu thực sự phải gửi raw JSON bytes do một hệ thống khác tạo, hãy xây `Message` có `body`, `contentType`, encoding và headers **được kiểm soát**, rồi dùng `send()` thay vì gọi `convertAndSend()` với String và mong converter không mã hóa lại.

## 8. Kiểu Java/DTO có thể sai dù JSON và content type đều đúng

JSON hợp lệ về cú pháp vẫn có thể không dựng được đối tượng Java:

| JSON | DTO đang mong đợi | Kiểu lỗi thường thấy |
| --- | --- | --- |
| `{"eventId":"abc"}` | `UUID eventId` | Invalid format cho UUID |
| `{"createdAt":"yesterday"}` | `Instant createdAt` | Không parse được thời gian |
| `{"quantity":"a lot"}` | `int quantity` | Sai kiểu số |
| `[]` | `OrderCreated` object | JSON array thay vì object |
| `null` | Tham số bắt buộc/validation | Có thể thành null, sau đó validation hoặc business fail |
| `{"payment":{...}}` | DTO cũ yêu cầu `orderId` ở root | Không đúng schema |
| `{"unknown":1,...}` | DTO cấu hình fail on unknown | Unrecognized field |
| `{"amount":0}` | Business yêu cầu amount dương | **Có thể deserialize được**, fail ở validation |

### 8.1. Record và Jackson Java Time

Ví dụ DTO Java 17+:

~~~java
package com.example.orders.contract;

import java.time.Instant;
import java.util.UUID;

public record OrderCreated(
        UUID eventId,
        String orderId,
        Instant occurredAt
) {}
~~~

Jackson cần cấu hình phù hợp để hỗ trợ Java Time (`Instant`), ví dụ module `jackson-datatype-jsr310` qua `ObjectMapper` do Spring Boot cấu hình. Nếu tạo một `new ObjectMapper()` độc lập không đăng ký module cần thiết, `Instant` có thể thất bại, dù Spring MVC JSON ở cùng ứng dụng đang chạy bình thường.

### 8.2. Conversion khác Bean Validation

Jackson có thể tạo `OrderCreated(eventId=null, orderId=null, ...)` nếu DTO không có ràng buộc bắt buộc được áp dụng ở conversion. Nếu sử dụng Bean Validation:

~~~java
public record OrderCreated(
        @jakarta.validation.constraints.NotNull UUID eventId,
        @jakarta.validation.constraints.NotBlank String orderId,
        @jakarta.validation.constraints.NotNull Instant occurredAt
) {}
~~~

cần có cơ chế kích hoạt validation phù hợp ở listener hoặc service. **`@NotNull` không tự bảo đảm Jackson sẽ ném `MessageConversionException`.** Validation exception và conversion exception là hai bước khác nhau, dù đều có thể dẫn tới việc message bị từ chối.

## 9. `__TypeId__` và inferred type của listener

Spring AMQP JSON converter có thể sử dụng những headers mô tả Java type như:

~~~text
__TypeId__ = com.example.orders.contract.OrderCreated
__ContentTypeId__ = java.lang.String
__KeyTypeId__ = java.lang.String
~~~

Đây là **type metadata** cho converter, không phải routing metadata của RabbitMQ. Exchange/binding không đọc `__TypeId__` để quyết định queue.

### 9.1. Producer và consumer không cùng classpath

Producer:

~~~text
Header:
  __TypeId__ = com.orders.events.OrderCreatedV2
Body:
  {"eventId":"...","orderId":"ORD-1001"}
~~~

Consumer:

~~~text
Listener argument:
  com.billing.contract.OrderCreated
~~~

Nếu type mapper cố tìm class từ header nhưng class đó không tồn tại hoặc không thuộc trusted packages, conversion có thể thất bại **dù JSON object đúng schema**. Đây là rủi ro khi để tên Java class của producer thành hợp đồng liên dịch vụ.

### 9.2. Ai quyết định kiểu: method signature hay header?

~~~java
@RabbitListener(queues = "orders.events.queue")
public void onEvent(OrderCreated event) {
    // ...
}
~~~

Trong nhiều phiên bản Spring AMQP, adapter có thể suy luận một **inferred type cụ thể** từ argument `OrderCreated` và JSON converter có thể ưu tiên nó hơn header producer. Nhưng khi method nhận `Object`, interface, abstract type, generic collection hoặc handler nhiều phương thức, header type và cơ chế type mapping có thể được dùng theo cách khác.

Không có một quy tắc tuyệt đối rằng “header luôn thắng” hoặc “listener signature luôn thắng” trong mọi kiểu method. Hãy kiểm tra `TypePrecedence`, inferred argument, converter class, mapper và version Spring AMQP thực tế.

### 9.3. Không bật trustedPackages("*") để chữa lỗi tùy tiện

~~~java
// Cách sửa nhanh nguy hiểm cho dữ liệu không tin cậy:
typeMapper.setTrustedPackages("*");
~~~

Cho header từ nguồn không tin cậy điều khiển kiểu Java được deserialize có thể mở rộng bề mặt tấn công. Giải pháp bền vững hơn:

1. Chỉ trust **các package được phê duyệt**.
2. Đặt listener argument là DTO cụ thể khi phù hợp.
3. Dùng type ID ổn định và ánh xạ ID → class theo allowlist.
4. Không bật polymorphic deserialization mở cho message chưa đáng tin cậy.
5. Giới hạn producer có quyền publish vào exchange theo virtual host/permission.

## 10. Cấu hình JSON converter nhất quán bằng Spring Boot

Một nguyên nhân thường gặp là producer đã dùng JSON converter nhưng listener vẫn dùng `SimpleMessageConverter` mặc định hoặc một `ObjectMapper` không có Java Time module.

Ví dụ **Spring Boot 3.x / Spring AMQP 3.x**:

~~~java
package com.example.orders.messaging;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersRabbitJsonConfiguration {

    @Bean
    Jackson2JsonMessageConverter ordersJsonConverter(
            ObjectMapper objectMapper) {
        return new Jackson2JsonMessageConverter(objectMapper);
    }

    @Bean
    RabbitTemplate ordersRabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter ordersJsonConverter) {
        var template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(ordersJsonConverter);
        template.setMandatory(true);
        return template;
    }

    @Bean("ordersJsonListenerFactory")
    SimpleRabbitListenerContainerFactory ordersJsonListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter ordersJsonConverter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(ordersJsonConverter);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(20);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

Ví dụ dùng `ObjectMapper` do Spring Boot quản lý để thống nhất Java Time và những tính năng Jackson đã định nghĩa. **Khi tạo custom `RabbitTemplate` hay listener factory, không mặc định mọi property Boot dành cho auto-configured beans được áp dụng nguyên vẹn**. Kiểm tra đúng bean đang được inject.

### 10.1. Cấu hình Boot tham khảo

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    virtual-host: /orders
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 20
        default-requeue-rejected: false
~~~

Nếu ứng dụng có nhiều connection factory, listener factory, custom template hoặc nhiều broker, cần xác định bean thực đang publish/consume chứ không nhìn YAML rồi suy đoán.

### 10.2. ObjectMapper và schema contract

Tự tạo `new ObjectMapper()` có thể khác `ObjectMapper` Boot đã cấu hình; `Instant`, naming strategies, enum format và các setting khác có thể xử lý khác. Nhưng việc nới lỏng mọi kiểm tra JSON để “parse được” có thể che đi **breaking change** ở schema.

Ví dụ tắt `FAIL_ON_UNKNOWN_PROPERTIES` có thể hỗ trợ thêm field tương thích trong một số contract, nhưng **không** sửa được field đổi kiểu, DTO đổi ý nghĩa hay event ID không hợp lệ.

## 11. Producer gửi DTO hay raw JSON theo cách khác nhau

### 11.1. Gửi DTO bằng `convertAndSend()`

~~~java
package com.example.orders.messaging;

import com.example.orders.contract.OrderCreated;
import java.time.Instant;
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final RabbitTemplate template;

    public OrderEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(UUID eventId, String orderId) {
        var event = new OrderCreated(
                eventId, orderId, Instant.now());

        template.convertAndSend(
                "orders.events.exchange",
                "order.created",
                event,
                message -> {
                    message.getMessageProperties()
                            .setMessageId(event.eventId().toString());
                    return message;
                });
    }
}
~~~

Với JSON converter phù hợp, kết quả trên wire thường có:

~~~text
exchange: orders.events.exchange
routingKey: order.created
contentType: application/json
messageId: <eventId>
body: {"eventId":"...","orderId":"...","occurredAt":"..."}
~~~

Body/header chính xác phụ thuộc ObjectMapper và converter version. Producer có thể thêm type headers; chúng không thay thế định danh nghiệp vụ `eventId`.

### 11.2. Gửi JSON raw bằng `send()`, không serialize lần thứ hai

Nếu JSON body đã được sản sinh bởi một nguồn tin cậy và đã được validate:

~~~java
package com.example.orders.messaging;

import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public final class RawJsonPublisher {

    private final RabbitTemplate template;

    public RawJsonPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void sendJson(String json, String eventId) {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

        Message message = MessageBuilder.withBody(bytes)
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setMessageId(eventId)
                .build();

        template.send(
                "orders.events.exchange", "order.created", message);
    }
}
~~~

`send()` gửi một `Message` đã có bytes/properties và **không bọc String thành JSON string mới**. Tuy vậy, raw JSON vẫn cần validation/schema; không cho producer không tin cậy tự ý khai báo Java type header.

### 11.3. Listener phải sử dụng đúng factory

~~~java
package com.example.orders.messaging;

import com.example.orders.contract.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final IdempotentOrderService orderService;

    public OrderCreatedListener(IdempotentOrderService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(
            queues = "orders.events.queue",
            containerFactory = "ordersJsonListenerFactory")
    public void onCreated(OrderCreated event) {
        orderService.applyOnce(event);
    }
}
~~~

`IdempotentOrderService` là service nghiệp vụ cần triển khai; phải commit transaction trước khi listener return. Nếu dùng Bean Validation, phải cấu hình kích hoạt validation đúng với listener/service, không coi JSON conversion đồng nghĩa mọi annotation validation đã chạy.

## 12. Type mapper có allowlist và event envelope

### 12.1. Cấu hình mapper cho DTO được phép

Trong Spring AMQP 3.x với các API mapper tương ứng:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.Jackson2JavaTypeMapper;
import org.springframework.amqp.support.converter.DefaultJackson2JavaTypeMapper;

DefaultJackson2JavaTypeMapper typeMapper =
        new DefaultJackson2JavaTypeMapper();

typeMapper.setTrustedPackages("com.example.orders.contract");
typeMapper.setTypePrecedence(
        Jackson2JavaTypeMapper.TypePrecedence.INFERRED);

jsonConverter.setJavaTypeMapper(typeMapper);
~~~

Đoạn code minh họa được đặt trong cấu hình nơi biến `jsonConverter` đã tồn tại. Không copy làm một class độc lập. Sau khi đổi type precedence/allowlist phải kiểm thử generic listeners, subtype, message cũ và producer khác.

### 12.2. Envelope tránh coupling tên class Java

Thay vì bắt consumer biết FQCN của producer, dùng định danh hợp đồng:

~~~json
{
  "eventId": "81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-26T02:00:00Z",
  "payload": {
    "orderId": "ORD-1001"
  }
}
~~~

Consumer chọn schema/DTO từ **`eventType` + `schemaVersion`** theo allowlist, rồi validate. Envelope giúp kiểm soát migration và quarantine event không được hỗ trợ; nó **không tự làm mọi schema change tương thích**. Ngoài ra, `eventId` giữ ổn định qua retry, redelivery và DLQ replay.

## 13. Phân loại exception theo tầng xảy ra

Tìm **root cause** trong stack trace thay vì xử lý theo tên exception bao ngoài.

| Exception hoặc họ lỗi | Tầng thường gặp | Hướng điều tra |
| --- | --- | --- |
| `org.springframework.amqp.support.converter.MessageConversionException` | AMQP converter | Bytes, content type, type headers, Jackson configuration |
| `org.springframework.messaging.converter.MessageConversionException` | Spring Messaging method argument | Payload chưa chuyển được sang tham số listener |
| `ListenerExecutionFailedException` | Adapter/container wrapper | Xem `Caused by` tới lỗi bên trong |
| Jackson `JsonParseException` | Cú pháp/bytes JSON | Body, charset, nén/giải mã |
| Jackson `MismatchedInputException` | JSON shape sai DTO | Object/array/string, nested structure |
| Jackson `InvalidFormatException` | Giá trị không thể đổi kiểu | UUID, số, enum, thời gian |
| Jackson `InvalidDefinitionException` | DTO/module/constructor cấu hình thiếu | Java Time module, records, creators |
| Jackson `InvalidTypeIdException` | Mapping subtype/type metadata | `__TypeId__`, polymorphism, allowlist |
| Validation exception | Validation sau chuyển đổi | `@Valid`/validator và business constraints |
| `AmqpRejectAndDontRequeueException` | Listener error policy | Container được yêu cầu reject không requeue |
| Connection/channel `AmqpException` | Hạ tầng RabbitMQ | Auth, permissions, channel closed, network |

**Lưu ý:** những lớp lỗi có thể được bọc thêm trong `ListenerExecutionFailedException` hoặc một exception do framework sinh. Một log chỉ chứa dòng đầu và không có `Caused by` dễ dẫn tới sửa sai nơi.

### 13.1. Ba stack trace rút gọn

**Sai converter hoặc media type:**

~~~text
ListenerExecutionFailedException
  caused by MessageConversionException:
    Cannot convert from [[B] to [com.example.OrderCreated]
~~~

Kiểm tra converter thực của listener và `contentType`. Không sửa DTO ngay khi body chưa được parse.

**JSON string thay vì object:**

~~~text
MessageConversionException
  caused by MismatchedInputException:
    Cannot construct OrderCreated from String value
~~~

Kiểm tra producer có dùng Jackson converter để gửi String đã chứa JSON hay không.

**Java Time thiếu module:**

~~~text
MessageConversionException
  caused by InvalidDefinitionException:
    Java 8 date/time type java.time.Instant not supported
~~~

Kiểm tra `ObjectMapper` thực đang được converter sử dụng và module Java Time. MVC REST controller hoạt động bình thường **không chứng minh** AMQP converter dùng cùng mapper.

### 13.2. Validation là lỗi khác với conversion

Ví dụ `orderId=""` có thể được Jackson dựng thành String rỗng. Sau đó service hoặc `@Valid` phát hiện điều kiện `@NotBlank`. Nếu ta gom cả hai thành “JSON parse error”, dashboard và retry policy sẽ thiếu chính xác.

Cần đặt phân loại riêng: `malformed_json`, `unsupported_media_type`, `invalid_type_id`, `schema_mismatch`, `validation_failed`, `business_error` và `transient_downstream`.

## 14. Lỗi xảy ra trước `@RabbitListener`: try/catch trong handler không đủ

Đoạn sau **không bắt được lỗi chuyển đổi trước khi gọi method**:

~~~java
@RabbitListener(queues = "orders.events.queue")
public void onCreated(OrderCreated event) {
    try {
        orderService.applyOnce(event);
    } catch (Exception ex) {
        // Chỉ thấy lỗi xảy ra SAU khi event đã được dựng thành DTO.
    }
}
~~~

Khi converter không tạo được `OrderCreated`, framework không thể gọi method với tham số đúng kiểu. Lỗi đi qua **listener adapter/container error handling**.

### 14.1. `ConditionalRejectingErrorHandler` và lỗi fatal

Trong nhiều phiên bản Spring AMQP, `ConditionalRejectingErrorHandler` phân loại một số lỗi là **fatal**, trong đó có những lỗi message conversion/argument mapping; container có thể chuyển chúng thành tín hiệu reject không requeue. Mục đích là tránh poison message được giao lại liên tục mà không bao giờ biến thành DTO hợp lệ.

Nhưng hành vi thực tế còn phụ thuộc:

- Spring AMQP version và error handler class thực đang gắn.
- `FatalExceptionStrategy` do ứng dụng tùy biến hay mặc định.
- Listener container factory và advice chain.
- Có DLX/DLQ hay không, queue type và broker version.
- Header `x-death`/chính sách xử lý message đã dead-letter trước đó.

**Đừng khẳng định mọi conversion error tự động tới DLQ.** Hãy chạy test thực, đo DLQ count và xác minh route. Nếu không có DLX hợp lệ, reject không requeue có thể khiến message không còn trong work queue mà **không có bản để điều tra**.

### 14.2. `defaultRequeueRejected=false` không phải giải pháp cho mọi exception

~~~java
factory.setDefaultRequeueRejected(false);
~~~

Tùy error flow, thiết lập này giúp tránh một số exception dẫn đến requeue vô hạn. Nhưng nó có thể làm **lỗi tạm thời** bị reject ngay nếu chưa áp dụng retry/chính sách phân loại phù hợp.

Nên phân loại:

- **Permanent conversion/schema error:** reject không requeue; đưa vào DLQ/quarantine; sửa hợp đồng hoặc dữ liệu.
- **Transient DB/HTTP error:** retry có backoff hữu hạn, hoặc delay retry queue có ngân sách.
- **Duplicate đã commit:** bỏ qua side effect, xử lý thành công và ACK.
- **Deploy mismatch khiến hàng loạt event hợp lệ đối với phiên bản cũ bị từ chối:** dừng rollout, sửa tương thích, không purge message.
- **Authentication/channel error:** sửa kết nối/quyền, không chỉnh type mapper tùy tiện.

### 14.3. Manual ACK cũng không tự sửa lỗi conversion

Chuyển sang `AcknowledgeMode.MANUAL` không làm DTO đột nhiên parse được. Lỗi vẫn có thể xảy ra trước listener, và cần một error handler có đường xử lý cụ thể. Đừng bật no-ack vô điều kiện chỉ để queue depth giảm: khi message chưa được xử lý mà đã coi là delivered thành công, có thể mất dữ liệu nghiệp vụ.

## 15. Dead-letter topology cho message không thể chuyển đổi

Một giải pháp vận hành là **work queue → DLX → terminal DLQ**:

~~~mermaid
flowchart LR
    P["Publisher / JSON DTO"] --> E["orders.events.exchange"]
    E -->|"order.created"| W["orders.events.queue"]
    W --> L["Converter + @RabbitListener"]
    L -->|"OK: DB commit rồi ACK"| OK["Đã xử lý"]
    L -->|"Fatal: reject không requeue"| X["orders.events.dlx"]
    X -->|"order.invalid"| D["orders.events.dlq"]
    D --> T["Triage / sửa lỗi / replay"]
~~~

### 15.1. Khai báo topology bằng Spring AMQP

~~~java
package com.example.orders.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersTopology {

    static final String EXCHANGE = "orders.events.exchange";
    static final String KEY = "order.created";
    static final String QUEUE = "orders.events.queue";
    static final String DLX = "orders.events.dlx";
    static final String DLQ = "orders.events.dlq";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("order.invalid")
                .build();
    }

    @Bean
    Binding ordersBinding() {
        return BindingBuilder.bind(ordersQueue())
                .to(ordersExchange())
                .with(KEY);
    }

    @Bean
    DirectExchange ordersDlx() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersDlq() {
        // Terminal DLQ không dead-letter vòng về queue nguồn.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersDlqBinding() {
        return BindingBuilder.bind(ordersDlq())
                .to(ordersDlx())
                .with("order.invalid");
    }
}
~~~

Lưu ý: việc hard-code `x-dead-letter-exchange` vào queue arguments có thể khó thay đổi nếu queue đã tồn tại. RabbitMQ policy có thể thích hợp hơn trong vận hành để giảm nhu cầu redeclare; cần kiểm tra precedence của policy/arguments và đặc tính queue type. **Không redeclare queue production với arguments không tương đương chỉ để thử sửa lỗi JSON.**

### 15.2. Phải kiểm chứng DLQ end-to-end

Một reject không requeue **không chứng minh** message đã được bảo vệ:

1. Exchange DLX có tồn tại trên cùng vhost không?
2. Binding và dead-letter routing key có đúng không?
3. Queue DLQ có durable và retention theo chính sách không?
4. Có vòng dead-letter quay về work queue không?
5. Với broker/queue type thực, dead-letter có bảo đảm giao đến đích phù hợp không?
6. Message properties và dữ liệu điều tra có còn đủ không?
7. Có alert khi DLQ nhận message mới và quy trình triage/replay không?

Nếu DLX/queue đích sai, message có thể không nằm trong DLQ như mong đợi. Phải chạy fault injection trong staging, không chỉ review Java code.

## 16. Retry hữu hạn cho business errors, không retry JSON hỏng mãi

Một ví dụ Spring AMQP 3.x dùng `RetryInterceptorBuilder`:

~~~java
package com.example.orders.messaging;

import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryingListenerConfiguration {

    @Bean("retryingOrdersFactory")
    SimpleRabbitListenerContainerFactory retryingOrdersFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setDefaultRequeueRejected(false);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(500L, 2.0, 2000L)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());

        return factory;
    }
}
~~~

`maxAttempts(3)` **bao gồm lần đầu**, nghĩa là tối đa hai lần thử lại in-process trong các đường lỗi có đi qua retry advice. Đây không phải **ba lần broker redelivery**. Với lỗi conversion trước phương thức listener, error handler/fatal exception strategy có thể có vai trò khác và **không nên giả định mọi lỗi JSON sẽ được retry đúng ba lần**.

Nếu một JSON body sai schema vĩnh viễn, retry ba lần liên tiếp vẫn không sửa được dữ liệu. Tốt nhất là **fail fast** tới DLQ/quarantine và báo hợp đồng sai; retry nên dành cho lỗi có khả năng tự hồi phục như transient DB/HTTP.

### 16.1. Retry in-process khác delayed retry

| Cơ chế | Điều kiện | Tác động |
| --- | --- | --- |
| Stateless Spring Retry quanh handler | Lỗi tạm thời ngắn | Giữ consumer thread trong khoảng backoff |
| Requeue ngay vào work queue | Message có thể tới lại ngay | Dễ tạo vòng lặp, cạnh tranh với message hợp lệ |
| TTL + DLX/delayed retry queue | Muốn lùi thời gian retry | Cần topology/limit rõ, có nguy cơ vòng nếu cấu hình sai |
| Terminal DLQ/quarantine | Lỗi permanent hoặc hết retry budget | Để điều tra, không tự phát lại vô hạn |
| Application outbox retry | Publish chưa có xác nhận | Không cùng mục đích với consumer business retry |

Đối với lỗi deserialize, **không thể tạo một DTO hợp lệ chỉ bằng việc tăng số lần retry**. Cần sửa schema, producer, converter hoặc thực hiện có kiểm soát một bước chuyển dữ liệu legacy.

## 17. Đọc raw AMQP message để kiểm tra lỗi mà không làm hỏng queue

Khi lỗi conversion khiến listener không nhận được DTO, có thể chẩn đoán bằng **raw `org.springframework.amqp.core.Message`** ở môi trường test, hoặc tiêu thụ một **bản sao đã được quarantine**.

Không thêm một listener raw “để xem thử” vào **cùng queue production** nếu không có kế hoạch: consumer mới sẽ cạnh tranh với consumer nghiệp vụ và có thể lấy mất message. Dùng staging, một queue debug riêng qua binding phù hợp, hoặc đọc bản sao trong DLQ/quarantine theo runbook.

### 17.1. Ví dụ raw listener không parse JSON ở handler

~~~java
package com.example.orders.diagnostics;

import java.util.Arrays;
import java.util.HexFormat;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RawMessageDiagnostics {

    @RabbitListener(
            queues = "orders.diagnostics.queue",
            containerFactory = "rawDiagnosticsFactory")
    public void inspect(Message message) {
        var props = message.getMessageProperties();
        byte[] body = message.getBody();

        String prefixHex = HexFormat.of().formatHex(
                Arrays.copyOf(body, Math.min(12, body.length)));

        System.out.printf(
                "type=%s encoding=%s bytes=%d prefixHex=%s%n",
                props.getContentType(),
                props.getContentEncoding(),
                body.length,
                prefixHex);

        // Chỉ metadata và prefix giới hạn; không log body JSON chứa PII.
    }
}
~~~

Với Java 17+, `HexFormat` có sẵn. Cần định nghĩa `rawDiagnosticsFactory` với converter/cấu hình raw phù hợp, dùng queue chẩn đoán **không trộn** với queue nghiệp vụ. Không coi handler này là hệ thống logging tự động được bật trên mọi message; đây là công cụ test điều tra có giới hạn truy cập.

### 17.2. Khi có DLQ, hãy giữ bản sao cho phép replay

Để điều tra một message trong DLQ:

1. Xác định message ID/correlation ID và số lượng message lỗi.
2. Sao lưu/quarantine raw body + properties **an toàn** trước khi sửa.
3. Kiểm tra `contentType`, encoding và dấu đầu bytes (magic bytes nếu nén).
4. Đọc `x-death` đúng nghĩa dead-letter history, không coi là số lần mọi exception.
5. Kiểm tra schema/version và producer release.
6. Thử parse trong test bằng converter và DTO kỳ vọng.
7. Chỉ replay sau khi có correction plan và idempotency.

**Không dùng `basic.get` hoặc một consumer phụ trên queue production tùy tiện** vì một thao tác đọc có thể thay đổi delivery/ACK/requeue state và ảnh hưởng thứ tự.

## 18. Kiểm thử converter độc lập để tách lỗi JSON khỏi lỗi broker

Một bài kiểm thử converter không cần RabbitMQ server: tạo một `Message` có bytes/properties rồi gọi converter để biết có dựng được DTO không.

Ví dụ **JUnit 5** (Spring AMQP 3.x):

~~~java
package com.example.orders.messaging;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.nio.charset.StandardCharsets;
import com.example.orders.contract.OrderCreated;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.DefaultJackson2JavaTypeMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

class OrderJsonConversionTest {

    @Test
    void convertsRawJsonObjectToOrderCreated() {
        var mapper = new ObjectMapper().findAndRegisterModules();
        var converter = new Jackson2JsonMessageConverter(mapper);
        var typeMapper = new DefaultJackson2JavaTypeMapper();
        typeMapper.setTrustedPackages("com.example.orders.contract");
        converter.setJavaTypeMapper(typeMapper);

        String body = """
                {
                  "eventId": "81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c",
                  "orderId": "ORD-1001",
                  "occurredAt": "2026-11-26T02:00:00Z"
                }
                """;

        Message raw = MessageBuilder
                .withBody(body.getBytes(StandardCharsets.UTF_8))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setHeader("__TypeId__", OrderCreated.class.getName())
                .build();

        Object value = converter.fromMessage(raw);

        assertInstanceOf(OrderCreated.class, value);
    }
}
~~~

Đoạn test giả định dependency `jackson-datatype-jsr310` có mặt để `findAndRegisterModules()` hỗ trợ `Instant`. Nếu dự án dùng converter/API khác, điều chỉnh theo phiên bản thực tế.

### 18.1. Bài test nên bao gồm cả trường hợp thất bại

- Raw JSON object đúng type/media → deserialize thành DTO.
- JSON string bọc JSON text → **phải** phát hiện sai shape.
- `text/plain` với JSON body → ghi nhận behavior converter thực.
- Thiếu `contentType` → xác minh behavior `assumeSupportedContentType` phiên bản đang dùng.
- Invalid UTF-8 hoặc GZIP bytes sai media → không được xem là JSON hợp lệ.
- Type header chứa Java class không trust → không được vô tình mở allowlist.
- JSON có UUID/Instant sai → exception có nguyên nhân rõ.
- JSON schema version mới → được đọc theo migration contract hoặc quarantine.

Nếu unit test parse được nhưng listener vẫn lỗi, hãy kiểm tra **bean converter nào thực đang được sử dụng** và bước argument conversion. Không kết luận broker làm hỏng JSON khi một converter được tạo thủ công trong test khác converter trong production.

## 19. Schema evolution: producer nâng phiên bản trước consumer

Một số lỗi `MessageConversionException` chỉ xuất hiện sau deployment vì producer và consumer không còn dùng cùng contract.

| Thay đổi | Có thể tương thích? | Rủi ro |
| --- | --- | --- |
| Thêm một field tùy chọn | Thường có thể | Consumer có thể fail khi bật strict unknown properties |
| Thêm một field bắt buộc | Cần migration | Message cũ thiếu field |
| Đổi `int amount` sang `String amount` | Breaking nếu không có adapter | Jackson coercion không đảm bảo semantic |
| Đổi tên `orderId` thành `id` | Cần hỗ trợ alias/version | Consumer cũ thiếu trường quan trọng |
| Đổi ngày từ ISO-8601 sang epoch integer | Cần agreement/module | Sai cách parse/timezone |
| Đổi từ object sang array | Breaking | Mismatched JSON shape |
| Đổi `eventType` hoặc type header | Có thể breaking | Consumer không tìm class/schema |
| Xóa enum value hoặc thêm enum mới | Cần compatibility plan | Consumer cũ không nhận giá trị mới |

### 19.1. Quy trình rollout tương thích

Một chiến lược thường an toàn:

1. Định nghĩa **schemaVersion** và compatibility policy (backward/forward/both nếu cần).
2. Đưa consumer mới lên trước nếu nó đọc được cả payload phiên bản cũ và mới.
3. Nâng producer sau khi consumer mới được triển khai đầy đủ.
4. Theo dõi conversion failures theo producer version, event type và schema version.
5. Đợi khoảng retention/retry/replay window; consumer mới vẫn có thể nhận message cũ từ DLQ.
6. Chỉ xóa compatibility path khi không còn nguồn phát hoặc replay payload cũ.
7. Giữ migration/replay script có kiểm soát cho message đã quarantine.

**Không lấy “hai service deploy đồng thời” làm đảm bảo**: RabbitMQ có thể giữ lại message từ trước đợt deploy; DLQ có thể chứa dữ liệu từ tháng trước. Consumer phải kiểm thử cả **message lịch sử**, không chỉ message mới do producer cùng version tạo.

### 19.2. Ví dụ alias cho thay đổi tên trường

Với Jackson:

~~~java
package com.example.orders.contract;

import com.fasterxml.jackson.annotation.JsonAlias;
import java.time.Instant;
import java.util.UUID;

public record OrderCreated(
        UUID eventId,
        @JsonAlias({"id"}) String orderId,
        Instant occurredAt
) {}
~~~

`@JsonAlias` cho phép một số tên input thay thế trong quá trình deserialization. Đây có thể là **bước chuyển tiếp**, không bảo đảm hai tên có cùng ý nghĩa nghiệp vụ hay tự xử lý mọi trường hợp hai trường cùng xuất hiện. Cần test cách xử lý precedence và không duy trì alias vô hạn khi có thể gây mơ hồ.

### 19.3. Collection, generic và đa hình

Listener nhận `List<OrderCreated>` hoặc `Map<String,OrderCreated>` cần cơ chế mang type information đầy đủ; một `List.class` đơn thuần có thể chỉ cho ra `List<LinkedHashMap>`. Với polymorphic hierarchy, phải xác định subtype hợp lệ bằng allowlist và hợp đồng schema.

Nếu listener chuyển từ một DTO cụ thể sang `Object` để “né lỗi”, conversion có thể thành generic map nhưng service lỗi ở bước cast hoặc mất validation. **Không coi trả về Map là đã sửa compatibility** trừ khi ứng dụng chủ động phân loại schema và validate từng type.

## 20. Quan sát lỗi trước khi listener được gọi

Để biết message lỗi ở đâu, cần metrics/logging ở **producer, container/error handler, DLQ và business service**.

| Metric (tên minh họa) | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `app_amqp_conversion_failed_total` | Listener container/error handler instrumentation | Số message không chuyển đổi được |
| `app_amqp_handler_failed_total` | Business service | Lỗi sau khi có DTO |
| `app_amqp_handler_completed_total` | Business service | Số event hoàn tất/commit |
| `app_amqp_duplicate_suppressed_total` | Consumer inbox | Message đã xử lý trước đó được chặn trùng |
| `app_amqp_publisher_returned_total` | RabbitTemplate returns | Publish không route được |
| `app_amqp_publish_confirm_timeout_total` | Producer | Publish outcome chưa rõ |
| `app_amqp_dlq_arrivals_total` | DLQ monitor | Message bị cách ly |
| `rabbitmq_detailed_queue_messages_ready` | RabbitMQ Prometheus khi family phù hợp | Độ sâu ready queue |

Các tên `app_` trong bảng là **quy ước của ứng dụng**, không phải metric chắc chắn được Spring Boot/Micrometer xuất tự động. Đừng gắn nhãn `eventId` hay nguyên exception message cho counter vì Prometheus cardinality có thể bùng nổ.

### 20.1. Phân loại log hữu ích

Một log lỗi chuyển đổi nên có:

~~~text
level=ERROR
stage=AMQP_MESSAGE_CONVERSION
queue=orders.events.queue
eventId=E42
producerService=orders-api
producerVersion=2.6.1
schemaVersion=2
contentType=application/json
contentEncoding=UTF-8
bodyBytes=243
typeId=order.created.v2
errorClass=INVALID_FORMAT
jsonPath=$.occurredAt
redelivered=false
action=REJECT_TO_DLQ
~~~

`jsonPath` và `typeId` không phải lúc nào cũng có; chỉ ghi khi lấy được từ exception/metadata một cách an toàn. **Không đưa PII/secret hoặc raw JSON** vào logs trừ khi đã qua redaction và chính sách truy cập.

### 20.2. Lỗi conversion có thể trùng với resource alarm hoặc mất consumer

Nếu message vào DLQ rất nhiều sau deploy, có thể conversion mismatch. Nếu queue `ready` tăng nhưng không có DLQ và consumer count=0, có thể listener không đăng ký do startup/auth/topology chứ chưa từng deserialize. Nếu publisher bị resource alarm chặn, có thể message **chưa vào queue**. Chẩn đoán cần nhìn:

1. Publisher confirm/return và outbox age.
2. Queue ready/unacked, consumer count và broker alarms.
3. Listener container logs và conversion error count.
4. DLQ routing và message IDs.
5. DB commits và business SLO.

**Không suy luận rằng queue trống nghĩa là mọi JSON đều parse tốt.** Message có thể đã bị dead-letter/drop hoặc chưa từng được route tới work queue.

## 21. Cây quyết định chẩn đoán

~~~mermaid
flowchart TD
    A["Message có ở queue mong đợi?"] -->|"Không"| B["Kiểm tra exchange/key/binding, confirms, returns, outbox"]
    A -->|"Có"| C["Consumer có đăng ký và nhận delivery?"]
    C -->|"Không"| D["Kiểm tra vhost, auth, listener container, queue declare"]
    C -->|"Có"| E{"Handler đã vào dòng đầu?"}
    E -->|"Có"| F["Business validation, DB/API, transaction"]
    E -->|"Không"| G["Kiểm tra root cause conversion/argument"]
    G --> H{"Body có phải bytes JSON đúng?"}
    H -->|"Không"| I["Fix producer format/charset/compression"]
    H -->|"Có"| J{"contentType và converter phù hợp?"}
    J -->|"Không"| K["Fix media type/bean/factory"]
    J -->|"Có"| L{"DTO/type headers/schema hợp lệ?"}
    L -->|"Không"| M["Fix DTO/type mapper/version; quarantine"]
    L -->|"Có"| N["Kiểm tra method argument và validation"]
~~~

### 21.1. Trình tự thực hiện bằng chứng

**Bước 1 — Xác định phạm vi.** Chỉ một message ID, một queue, một producer version hay tất cả consumer? Lỗi bắt đầu sau khi deploy producer hay consumer?

**Bước 2 — Kiểm tra dữ liệu gốc.** Dùng staging/DLQ hoặc bản sao raw có quyền phù hợp để đọc content type, charset, byte length, JSON shape và type headers. Đừng tự consume khỏi production queue.

**Bước 3 — Xác minh converter thực.** Kiểm tra bean `RabbitTemplate`, `containerFactory` được chọn và cấu hình `ObjectMapper` thực, không chỉ nhìn file YAML.

**Bước 4 — Tái tạo offline.** Dùng bài test converter/DTO với cùng body/properties và dependency versions, sau đó kiểm tra full listener adapter bằng integration test khi cần.

**Bước 5 — Phân loại retry.** Permanent schema/type error không được requeue mãi; transient infrastructure/business error có retry budget riêng.

**Bước 6 — Khôi phục và đối soát.** Sau khi sửa code/config, replay có chọn lọc các message trong DLQ, giữ event ID và dùng idempotency trước khi xác nhận incident đã giải quyết.

## 22. Mười bốn kịch bản kiểm thử thực hành

Các bài thử dưới đây nên chạy trong staging với broker, vhost, exchange, queue và data riêng. Với mỗi kịch bản, ghi **root cause**, conversion error, DLQ count, message ID, ACK/reject và business commit.

### A. JSON đúng, converter đúng

1. Producer gửi `OrderCreated` bằng Jackson converter với `application/json`.
2. Listener nhận DTO cụ thể và converter cùng contract.
3. Xác minh body thành JSON object, listener chạy, DB commit.
4. Kiểm tra ACK và metrics success.

**Kỳ vọng:** đường chuẩn hoạt động; làm baseline cho các lỗi khác.

### B. JSON bytes nhưng `text/plain`

1. Gửi raw JSON body nhưng set `contentType=text/plain`.
2. Listener đợi DTO và dùng Jackson converter.
3. Quan sát behavior conversion/argument mapper theo version.
4. Sửa producer thành `application/json` và thử lại.

**Kỳ vọng:** hiểu ảnh hưởng của media type; không kết luận JSON body hỏng khi chỉ property sai.

### C. Không đặt `contentType`

1. Gửi raw JSON mà không set media type.
2. Thử trên converter/version thực tế.
3. Kiểm tra cơ chế `assumeSupportedContentType` nếu có.
4. So với khi set explicit `application/json`.

**Kỳ vọng:** không dựa vào giả định một version trên mọi hệ thống.

### D. Double serialization của Java String

1. Đưa một String đã chứa JSON vào `convertAndSend()` dùng Jackson converter.
2. Xem raw body dạng JSON quoted string.
3. Listener đợi `OrderCreated`, quan sát conversion error.
4. Sửa producer gửi DTO hoặc dùng `send()` với raw Message.

**Kỳ vọng:** phân biệt JSON object với JSON string chứa JSON text.

### E. Body GZIP nhưng content type JSON

1. Nén JSON body rồi gắn nhầm `application/json`.
2. Cho converter parse trực tiếp.
3. Quan sát lỗi parser/byte signature.
4. Thêm bước giải nén đúng contract trong test.

**Kỳ vọng:** biết khi nào lỗi là content encoding/compression, không phải DTO.

### F. UUID và Instant sai định dạng

1. Gửi `eventId="abc"` hoặc `occurredAt="yesterday"`.
2. Quan sát Jackson `InvalidFormatException`/lỗi liên quan.
3. Sửa payload đúng schema.
4. Bổ sung validation cho các ràng buộc nghiệp vụ sau conversion.

**Kỳ vọng:** không cho một giá trị sai bị retry vô hạn.

### G. Thiếu Java Time module trong ObjectMapper

1. Tạo converter bằng `new ObjectMapper()` không đăng ký module thời gian phù hợp.
2. Deserialize DTO chứa `Instant`.
3. So với `ObjectMapper` đã cấu hình module tương ứng.
4. Kiểm tra converter bean thực trong listener.

**Kỳ vọng:** phát hiện mismatch giữa MVC object mapper và AMQP converter.

### H. Type header trỏ tới class không tồn tại

1. Gửi body JSON hợp lệ và `__TypeId__` của class chỉ tồn tại ở producer.
2. Cấu hình consumer để trường hợp test thực sự dùng header type.
3. Quan sát lỗi class resolution/type mapping hoặc trusted package.
4. Chuyển sang inferred DTO hoặc type mapping allowlist.

**Kỳ vọng:** không mở `trustedPackages("*")` một cách tùy tiện.

### I. DTO ở producer đổi field hoặc enum

1. Producer thêm/đổi một field theo schema mới.
2. Consumer cũ nhận message trong queue.
3. Quan sát lỗi chuyển đổi/validation nếu có.
4. Dùng schema version/alias/migration tương thích, kiểm tra lại.
5. Thử cả message cũ trong DLQ sau khi đã deploy consumer mới.

**Kỳ vọng:** đánh giá compatibility xuyên deployment và retention window.

### J. Handler không được gọi nên try/catch không chạy

1. Gửi JSON không parse được tới listener typed.
2. Đặt metric/log tại dòng đầu method.
3. Xác minh dòng đầu không chạy.
4. Xem error handler/container logs và cách message bị reject.

**Kỳ vọng:** đặt điểm giám sát đúng trước listener.

### K. Poison message và terminal DLQ

1. Gửi một payload permanent-invalid.
2. Kiểm tra error handler/fatal strategy trên phiên bản thực.
3. Xác minh message vào DLQ đúng, không lặp requeue.
4. Ghi lại body/properties qua quarantine có quyền.
5. Sửa lỗi và replay bằng ID gốc.

**Kỳ vọng:** không mất message lỗi và không tạo retry storm.

### L. DLX/binding bị cấu hình sai

1. Cố tình đặt DLX hoặc routing key sai trong queue test.
2. Gửi message conversion lỗi.
3. Kiểm tra work queue, DLQ và broker logs.
4. Sửa topology bằng migration hợp lệ.
5. Thử lại với test event mới.

**Kỳ vọng:** reject không đồng nghĩa message chắc chắn có trong DLQ.

### M. DB commit nhưng consumer ACK bị mất

1. Cho một event hợp lệ xử lý và commit DB.
2. Mô phỏng mất connection trước ACK broker nhận.
3. Cho message redeliver.
4. Kiểm tra inbox/unique constraint ngăn duplicate effect.
5. Phân biệt redelivery hợp lệ với message poison.

**Kỳ vọng:** lỗi connection không bị chẩn đoán nhầm là conversion error.

### N. Lỗi route/publish chứ không phải conversion

1. Gửi event hợp lệ nhưng dùng routing key không có binding.
2. Bật mandatory/returns và correlated publisher confirms.
3. Xác minh event không tới work queue.
4. Khắc phục routing và phát lại từ outbox với event ID gốc.
5. Kiểm tra listener DTO hoạt động sau khi route đúng.

**Kỳ vọng:** xử lý đúng tầng; không sửa converter khi message chưa đến consumer.

## 23. Runbook ứng phó khi conversion errors tăng sau deploy

Tình huống: vài phút sau một bản phát hành, `orders.events.queue` bắt đầu tăng DLQ, một số event không được xử lý và log xuất hiện `MessageConversionException`.

**Mục tiêu:** dừng lan rộng, không mất dữ liệu, xác định đúng producer/consumer/schema mismatch và khôi phục xử lý có kiểm chứng.

### Pha 1 — Giữ an toàn dữ liệu

1. Xác định **vhost, queue, producer version, consumer version, thời gian bắt đầu**.
2. Kiểm tra resource alarm, consumer count và publisher confirms/returns để phân biệt sự cố broker với lỗi converter.
3. Đảm bảo DLX và DLQ hoạt động; nếu DLQ đang thiếu/bị cấu hình sai, **dừng luồng gây lỗi theo runbook** trước khi có thêm message bị drop.
4. Không purge work queue hoặc DLQ để “giảm số đỏ”.
5. Giữ outbox tại producer cho các event chưa có publish outcome đáng tin cậy.
6. Thu thập một số message ID/body sample đã được bảo vệ, tránh log payload nhạy cảm.

### Pha 2 — Tìm nguyên nhân

1. Đọc root cause của stack trace; xác định AMQP converter hay method argument/validation.
2. So sánh raw body/properties giữa một message thành công và một message thất bại.
3. Đối chiếu `contentType`, `contentEncoding`, `__TypeId__` và `schemaVersion`.
4. Kiểm tra producer có gửi DTO, raw JSON hay String đã serialize.
5. Xác định `RabbitTemplate` và `containerFactory` thực sử dụng converter nào.
6. Kiểm tra `ObjectMapper`, Java Time module, type mapping và trusted packages.
7. Tái tạo bằng unit test converter; bổ sung integration test với broker khi cần.

### Pha 3 — Khắc phục tương thích

1. Nếu producer mới tạo payload không tương thích, **rollback producer** hoặc phát triển consumer đọc cả hai version.
2. Nếu converter/listener bean sai, sửa cấu hình và triển khai canary.
3. Nếu media type sai, sửa producer trước; với message legacy, dùng adapter/migration được kiểm soát.
4. Nếu schema đổi, sửa DTO, envelope/schema registry policy hoặc versioned deserializer; tránh nới rộng type allowlist không an toàn.
5. Giữ retry riêng cho lỗi transient; permanent conversion lỗi đưa tới DLQ/quarantine với điểm dừng.

### Pha 4 — Replay và nghiệm thu

1. Kiểm tra một message trước đó lỗi giờ có thể deserialize trong staging.
2. Replay một tập nhỏ từ DLQ bằng **eventId gốc**.
3. Theo dõi duplicate suppression, DB commit, ACK, publisher confirm và DLQ.
4. Chỉ tăng tốc replay khi downstream còn capacity; không gây resource alarm.
5. Đối soát nguồn event với đích theo ID, không chỉ so số message.
6. Kiểm tra toàn bộ producer versions và dữ liệu cũ có thể còn trong backlog/DLQ.
7. Ghi lại root cause, các test regression, guardrail và người chịu trách nhiệm.

**Tiêu chí đóng incident:** conversion failures trở về baseline, DLQ đã được triage hoặc có owner xử lý, event hợp lệ được commit trong SLO và không có event nguồn bị thất lạc/side effect trùng chưa đối soát.

## 24. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ đọc exception ngoài cùng | Sửa sai tầng | Xem `Caused by` và exception class gốc |
| Nghĩ broker tự validate JSON | Nhầm routing với conversion | Kiểm tra body/properties phía consumer |
| JSON body có vẻ đúng thì bỏ qua content type | Converter có thể trả byte[] | Xác minh media type và converter version |
| Gửi String đã là JSON qua Jackson `convertAndSend()` | JSON bị bọc trong JSON string | Gửi DTO hoặc raw `Message` bằng `send()` |
| Dùng `SimpleMessageConverter` cho DTO JSON | Không có mapping tự động thành DTO | Cấu hình Jackson converter thống nhất |
| Tạo `ObjectMapper` riêng thiếu modules | `Instant`/enum/format fail | Dùng mapper đã cấu hình và test |
| Đổi `__TypeId__` tùy tiện | Consumer không nhận class hoặc sai type | Có versioned contract và allowlist |
| Bật `trustedPackages("*")` | Mở rộng rủi ro deserialization | Trusted packages tối thiểu |
| Nhận `Object`/`Map` để né hết lỗi schema | Lỗi chuyển sang runtime cast/validation | DTO/version rõ và kiểm tra contract |
| Đặt try/catch trong listener để bắt pre-listener conversion | Catch không bao giờ chạy | Container error handler và DLQ |
| Requeue mọi exception vô hạn | Poison message chiếm queue | Phân loại permanent/transient, retry budget |
| Tắt retry cho mọi lỗi | Lỗi DB tạm thời bị DLQ quá sớm | Retry có backoff theo loại lỗi |
| Coi reject là chắc chắn đã tới DLQ | DLX/binding có thể sai | Test routing và theo dõi DLQ |
| Bật no-ack để queue trống | Message có thể mất trước business commit | ACK sau commit và idempotency |
| Chỉ nhìn queue depth | Message có thể chưa được route hoặc đã DLQ | Publisher confirms/returns, outbox, DLQ |
| Dùng eventId làm Prometheus label | Cardinality lớn | EventId trong log/trace, label theo error class |
| Replay DLQ với ID mới | Duplicate side effects | Giữ ID ổn định và dedup ở storage |
| Quên message cũ sau schema rollout | Dữ liệu tồn/delay queue vẫn không đọc được | Compatibility test với historical messages |

## 25. Checklist production cho contract JSON và lỗi conversion

### Trước khi phát hành producer

- [ ] Producer sử dụng DTO và converter rõ ràng; không vô tình double serialization.
- [ ] Body là định dạng đã công bố, `contentType` và encoding được đặt nhất quán.
- [ ] Event có `eventId` ổn định, `eventType` và `schemaVersion` nếu cần.
- [ ] Không dựa vào Java FQCN producer làm hợp đồng cho mọi consumer.
- [ ] Có contract test với các consumer tương thích hoặc fixture đã được chia sẻ.
- [ ] Có publisher confirms/returns và outbox cho các event không được phép mất.

### Trước khi phát hành consumer

- [ ] Listener dùng đúng `containerFactory` và converter bean đã xác minh.
- [ ] ObjectMapper có Java Time/module/enum/naming settings đúng.
- [ ] DTO có constructor/record và validation phù hợp.
- [ ] Type mapper ưu tiên phù hợp; allowlist không mở toàn bộ package tùy tiện.
- [ ] Unit test raw body/properties đúng/sai, type header, JSON string và schema evolution.
- [ ] Integration test conversion error xảy ra **trước listener method**.
- [ ] Permanent errors reject/quarantine có điểm dừng; transient retries có backoff.
- [ ] DLX/terminal DLQ đã thử với message sai content type và JSON.
- [ ] Consumer commit trước ACK; inbox/idempotency xử lý redelivery/replay.

### Vận hành và quan sát

- [ ] Dashboard có conversion error rate, handler failure, DLQ arrivals và queue age.
- [ ] Có structured log an toàn với content type, byte length, type metadata, error class.
- [ ] Không log payload nhạy cảm và không dùng eventId làm metric label.
- [ ] Có alert khi error rate tăng sau producer/consumer deployment.
- [ ] Có owner cho DLQ, retention và replay policy.
- [ ] Có runbook rollback producer, triển khai converter canary và xử lý message lịch sử.
- [ ] Có kịch bản mất ACK sau commit và unknown publisher confirm để tránh duplicate/missing effects.
- [ ] Có điều kiện nghiệm thu là **business commit và reconciliation**, không chỉ queue trống.

## 26. Tài liệu tham khảo và tổng kết

Những nguồn chính thức nên đối chiếu với **Spring AMQP, Spring Boot, Jackson và RabbitMQ versions đang chạy**:

- [Spring AMQP Reference — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
- [Spring AMQP Reference — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html)
- [Spring AMQP Reference — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Jackson Databind Documentation](https://github.com/FasterXML/jackson-databind)

**`MessageConversionException` không phải một lỗi duy nhất.** Nó có thể đến từ raw bytes không phải JSON, `contentType` không được converter chấp nhận, sai charset/compression, String JSON bị serialize hai lần, type header/trusted package không phù hợp hoặc DTO/Jackson module bị lệch. Đôi khi lỗi đã chuyển qua tầng argument binding hoặc validation, nên cần đọc **root cause và nơi phát sinh**, không chỉ tên exception.

Trong **SPRING_AMQP**, đường chẩn đoán hiệu quả là: **xác minh publish và routing → xem raw body/properties an toàn → xác định converter thực tế → so method signature, type mapper, JSON schema → tái tạo bằng test → xử lý fatal/retry/DLQ phù hợp → replay/idempotent và đối soát nghiệp vụ**.

Bản tin sai định dạng cần có nơi cách ly và sửa chữa, không được requeue vô hạn. Bản tin hợp lệ cũng có thể được giao lại sau mất ACK, nên consumer phải bảo vệ side effect bằng **eventId ổn định, transaction và idempotency**. Đích cuối cùng không phải “hết stack trace”, mà là **event được diễn giải đúng, xử lý bền vững và có thể phục hồi khi một phần đường truyền thất bại**.





