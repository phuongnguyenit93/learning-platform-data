# Converter cho ReplyingKafkaTemplate

`ReplyingKafkaTemplate` của Spring Kafka hỗ trợ request/reply: ứng dụng gửi một request lên Kafka rồi chờ response tương ứng từ một listener khác. Mỗi request được gắn correlation ID; response phải mang lại correlation ID đó để template tìm đúng future đang chờ. Trong mô hình này, dữ liệu có thể được gửi và nhận dưới dạng `ProducerRecord`/`ConsumerRecord`, hoặc dưới dạng Spring `Message<?>`.

Khi dùng API `Message<?>`, `RecordMessageConverter` là thành phần chuyển đổi giữa Spring Messaging message và Kafka record. Converter giúp ứng dụng gửi một object Java làm payload, ánh xạ header của Spring Message sang Kafka headers, rồi chuyển response Kafka thành Spring Message. Đây là lớp chuyển đổi ở ranh giới messaging; Kafka `Serializer` và `Deserializer` vẫn chịu trách nhiệm chuyển key/value Java thành byte và ngược lại.

Bài học tập trung vào cách cấu hình converter cho `ReplyingKafkaTemplate`, cách dùng converter ở phía listener trả lời, và cách giữ nguyên các header correlation/reply để request có thể ghép đúng response.

## 1. Luồng request/reply trong Spring Kafka

Một request/reply flow thường có ba thành phần:

- **Requester**: ứng dụng dùng `ReplyingKafkaTemplate` gửi request và chờ response.
- **Responder**: listener nhận request, xử lý và gửi response về reply topic.
- **Reply listener container**: consumer container được `ReplyingKafkaTemplate` dùng để nhận response và hoàn tất future tương ứng.

Luồng xử lý:

```text
Requester application
      |
      | Message<OrderRequest>
      v
RecordMessageConverter
      |
      | ProducerRecord + correlation/reply headers
      v
Kafka request topic
      |
      v
Responder @KafkaListener
      |
      | convert request record -> Message/OrderRequest
      v
Business service xử lý
      |
      | OrderReply
      v
Reply converter + reply template
      |
      | response + correlation ID
      v
Kafka reply topic
      |
      v
Reply listener container
      |
      | tìm future theo correlation ID
      v
Requester nhận Message<OrderReply>
```

`ReplyingKafkaTemplate` không tự thực hiện nghiệp vụ request. Nó quản lý việc gửi request, đăng ký future đang chờ, nhận response và ghép response với request bằng correlation ID. Listener phía responder chịu trách nhiệm xử lý request và phát response đúng topic/partition.

## 2. Phân biệt MessageConverter với Serializer/Deserializer

Hai lớp này thường bị nhầm lẫn vì đều tham gia quá trình chuyển dữ liệu:

| Thành phần | Đầu vào/đầu ra | Trách nhiệm |
|---|---|---|
| `RecordMessageConverter` | Spring `Message<?>` ↔ Kafka `ProducerRecord`/`ConsumerRecord` | Chuyển payload và headers ở mức message của Spring |
| `MessagingMessageConverter` | Spring Message ↔ Kafka record | Converter nền, ánh xạ payload và headers; thường dùng cơ chế header mapper |
| `JsonMessageConverter` và các biến thể | Object ↔ JSON representation trong Kafka record | Chuyển object thành JSON và ngược lại |
| Kafka `Serializer` | Java key/value → `byte[]` | Mã hóa key/value để gửi qua Kafka protocol |
| Kafka `Deserializer` | `byte[]` → Java key/value | Giải mã key/value nhận từ broker |

Ví dụ với `StringJsonMessageConverter`, object `OrderRequest` được chuyển thành JSON string. Sau đó `StringSerializer` mã hóa chuỗi JSON thành byte. Ở chiều nhận, `StringDeserializer` tạo lại JSON string và converter chuyển JSON thành object Java dựa trên type metadata hoặc kiểu đích được xác định.

```text
Message<OrderRequest>
       |
       v
StringJsonMessageConverter
       |
       v
String JSON
       |
       v
StringSerializer
       |
       v
byte[] trong Kafka
```

Nếu dùng `ByteArrayJsonMessageConverter`, payload sau conversion là `byte[]`, do đó producer/consumer cần serializer/deserializer byte array tương ứng. Chọn converter và serializer theo cặp; không cấu hình converter tạo `String` nhưng lại dùng serializer chỉ nhận `OrderRequest` hoặc `byte[]`.

Khi gửi trực tiếp một `ProducerRecord<K,V>` vào `sendAndReceive(ProducerRecord)`, converter Spring Message không cần chuyển đổi request vì record đã có key/value đúng kiểu Java. Kafka serializer/deserializer vẫn được sử dụng. Converter trở nên hữu ích khi muốn dùng API `Message<?>` và Spring headers.

## 3. RecordMessageConverter và các lựa chọn JSON

Spring Kafka định nghĩa `RecordMessageConverter` để chuyển đổi giữa Spring Message và Kafka record. Các implementation thường gặp:

| Converter | Dạng payload Kafka | Serializer/deserializer phù hợp |
|---|---|---|
| `MessagingMessageConverter` | Payload giữ nguyên kiểu Java trước khi qua Kafka serializer | Phụ thuộc serializer/deserializer được cấu hình |
| `StringJsonMessageConverter` | JSON dạng `String` | `StringSerializer` / `StringDeserializer` |
| `ByteArrayJsonMessageConverter` | JSON dạng `byte[]` | `ByteArraySerializer` / `ByteArrayDeserializer` |
| `BytesJsonMessageConverter` | JSON dạng Kafka `Bytes` | Serializer/deserializer tương ứng với `Bytes` |

Tên class và constructor có thể khác giữa các phiên bản Spring Kafka. Ví dụ dưới đây dùng `StringJsonMessageConverter`, phù hợp khi ứng dụng muốn lưu JSON text và dùng String serializer/deserializer. Nếu dự án đang dùng phiên bản khác, kiểm tra package `org.springframework.kafka.support.converter` và API tương ứng.

Khai báo converter:

```java
@Configuration
public class KafkaMessageConversionConfiguration {

    @Bean
    public RecordMessageConverter requestReplyMessageConverter() {
        return new StringJsonMessageConverter();
    }
}
```

Converter JSON có thể dùng type headers để xác định kiểu object khi đọc lại. Cần thống nhất type mapping giữa requester và responder nếu hai ứng dụng dùng package/class khác nhau. Không nên tin cậy type header đến từ nguồn không kiểm soát; cấu hình trusted packages hoặc mapping theo token phù hợp với phiên bản Spring Kafka.

## 4. Cấu hình producer và reply consumer

Trong ví dụ này, converter biến object request/reply thành JSON string. Vì vậy producer factory và reply consumer factory đều dùng String serializer/deserializer:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: order-reply-client-${INSTANCE_ID}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: latest
```

`auto-offset-reset: latest` là lựa chọn thường dùng cho reply container mới vì requester chỉ cần response phát sinh sau khi bắt đầu gửi request. Tuy nhiên, reply container phải được khởi động và nhận assignment trước khi gửi request; không dựa vào `latest` để sửa lỗi reply container chưa sẵn sàng.

Trong ứng dụng có nhiều requester instance, cần thiết kế reply topic, partition và consumer group sao cho response đến đúng instance đang giữ future. Một group ID dùng chung có thể khiến reply bị phân phối sang instance khác nếu cấu hình topic/partition không được thiết kế phù hợp. Thường mỗi requester instance có group ID riêng hoặc reply topic riêng, và cần kiểm thử với nhiều instance thật.

## 5. Tạo reply listener container

`ReplyingKafkaTemplate` cần một listener container chuyên nhận response. Container này không phải listener nghiệp vụ có `@KafkaListener`; template đăng ký làm message listener cho container và xử lý response dựa trên correlation ID.

Ví dụ tạo container đọc topic `orders.replies`:

```java
@Configuration
public class ReplyContainerConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConsumerFactory<String, String> consumerFactory,
            @Value("${spring.kafka.consumer.group-id}") String replyGroupId) {

        ContainerProperties properties =
                new ContainerProperties("orders.replies");
        properties.setGroupId(replyGroupId);

        return new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties);
    }
}
```

`spring.kafka.consumer.group-id` phải được cấp một giá trị hợp lệ và duy nhất cho requester instance theo chiến lược triển khai. Trong ví dụ, `INSTANCE_ID` được cấp riêng cho từng instance và Spring đưa giá trị này vào group ID. Có thể dùng `ContainerProperties.setGroupId(...)` hoặc cấu hình group ID trên consumer factory, tùy cách tổ chức cấu hình. Không để nhiều reply containers cùng group chia nhau một reply topic nếu mỗi template chỉ có thể hoàn tất future của chính instance gửi request.

Reply container cần được khởi động bởi Spring lifecycle. Nếu ứng dụng tự quản lý start/stop, phải bảo đảm container đã nhận partition assignment trước khi gửi request.

## 6. Tạo ReplyingKafkaTemplate và gắn converter

Sau khi có `ProducerFactory`, reply container và converter, tạo template:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    public ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String> repliesContainer,
            RecordMessageConverter requestReplyMessageConverter) {

        var template = new ReplyingKafkaTemplate<>(
                producerFactory, repliesContainer);
        template.setMessageConverter(requestReplyMessageConverter);
        template.setDefaultReplyTimeout(Duration.ofSeconds(10));
        return template;
    }
}
```

Ở đây `K`, `V` và `R` đều là `String` vì converter dùng JSON string cùng String serializer/deserializer. `setMessageConverter(...)` cho phép API `Message<?>` của template chuyển request Spring Message thành Kafka record và chuyển reply record thành Spring Message. Với API `ProducerRecord`, dữ liệu đã được cung cấp ở dạng Kafka record nên không cần bước chuyển Spring Message ở request.

`setDefaultReplyTimeout(...)` đặt thời gian chờ mặc định cho response. Có thể dùng overload `sendAndReceive` nhận timeout riêng cho từng request nếu phiên bản Spring Kafka đang dùng hỗ trợ. Timeout chỉ giới hạn thời gian chờ future; nó không hủy nghiệp vụ đã chạy ở responder và không bảo đảm request chưa được xử lý.

## 7. Gửi request bằng Spring Message

Khi dùng converter, requester có thể gửi một Spring `Message<OrderRequest>` thay vì tự tạo `ProducerRecord`:

```java
@Service
public class OrderQueryClient {

    private final ReplyingKafkaTemplate<String, String, String> template;

    public OrderQueryClient(
            ReplyingKafkaTemplate<String, String, String> template) {
        this.template = template;
    }

    public OrderReply findOrder(String orderId) throws Exception {
        Message<OrderRequest> request = MessageBuilder
                .withPayload(new OrderRequest(orderId))
                .setHeader(KafkaHeaders.TOPIC, "orders.requests")
                .setHeader(KafkaHeaders.MESSAGE_KEY, orderId)
                .build();

        RequestReplyMessageFuture<String, String, String> future =
                template.sendAndReceive(request);

        Message<?> replyMessage = future.get(10, TimeUnit.SECONDS);
        return (OrderReply) replyMessage.getPayload();
    }
}
```

`KafkaHeaders.TOPIC` xác định request topic và `KafkaHeaders.MESSAGE_KEY` xác định record key. `ReplyingKafkaTemplate` bổ sung correlation ID và thông tin reply topic/partition cần thiết cho request/reply. Converter chuyển payload `OrderRequest` thành JSON string trước khi Kafka producer serializer mã hóa nó.

Ví dụ giả định converter và type metadata được cấu hình để phản hồi được chuyển thành `OrderReply`. Trong code production, nên kiểm tra kiểu payload trả về hoặc dùng một lớp wrapper/service để xác thực kiểu, tránh cast mù nếu nhiều loại response có thể xuất hiện.

Trước khi gửi request đầu tiên, có thể đợi reply container được gán partition:

```java
if (!template.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException("Reply container chưa được assign partition");
}
```

Việc chờ assignment giúp tránh gửi request khi reply container chưa sẵn sàng nhận response. API này có trên các phiên bản Spring Kafka hiện đại; nếu phiên bản đang dùng khác, kiểm tra cơ chế xác nhận container assignment tương ứng.

## 8. Gửi ProducerRecord khi không cần MessageConverter

Nếu ứng dụng đã tự tạo payload ở kiểu `String`, có thể dùng `ProducerRecord` trực tiếp:

```java
ProducerRecord<String, String> request =
        new ProducerRecord<>("orders.requests", "order-42", "lookup:order-42");

RequestReplyFuture<String, String, String> future =
        template.sendAndReceive(request);

ConsumerRecord<String, String> reply =
        future.get(10, TimeUnit.SECONDS);

log.info("reply partition={}, offset={}, value={}",
        reply.partition(), reply.offset(), reply.value());
```

Ở cách này, ứng dụng chịu trách nhiệm tạo chuỗi payload. Kafka serializer/deserializer chuyển chuỗi thành byte và ngược lại. `RecordMessageConverter` không tự chuyển một object tùy ý thành JSON trong overload nhận `ProducerRecord`; nếu muốn gửi object, hoặc dùng `Message<?>` cùng converter, hoặc serialize object trước khi tạo record.

Sử dụng `ProducerRecord` phù hợp khi cần kiểm soát trực tiếp topic, partition, timestamp, key và Kafka headers. Sử dụng `Message<?>` phù hợp khi muốn tích hợp với Spring Messaging, `MessageBuilder`, header mapping và chuyển đổi payload tự động.

## 9. Cấu hình converter ở phía responder

Responder nhận request record và gửi response. Nếu muốn method `@KafkaListener` nhận `OrderRequest` thay vì JSON string, listener container factory cần dùng cùng loại converter:

```java
@Configuration
public class RequestListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            requestListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTemplate<String, String> replyTemplate,
                    RecordMessageConverter requestReplyMessageConverter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(requestReplyMessageConverter);
        factory.setReplyTemplate(replyTemplate);
        return factory;
    }
}
```

`setRecordMessageConverter(...)` chuyển Kafka record request thành Spring Message để argument resolver có thể cung cấp payload theo kiểu tham số listener. `setReplyTemplate(...)` cung cấp template dùng để gửi giá trị trả về từ listener. `KafkaTemplate` phía responder cần serializer tương thích với kết quả converter tạo ra và cũng cần được gắn cùng message converter để object trả về được chuyển thành JSON string:

```java
@Bean
public KafkaTemplate<String, String> replyTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter requestReplyMessageConverter) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(requestReplyMessageConverter);
    return template;
}
```

Listener có thể trả về một object và dùng `@SendTo` không ghi destination để Spring lấy reply topic từ header request:

```java
@Component
public class OrderRequestListener {

    @KafkaListener(
            topics = "orders.requests",
            groupId = "orders-service",
            containerFactory = "requestListenerContainerFactory")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderService.find(request.orderId());
    }
}
```

Trong request/reply flow này, request có reply topic header do `ReplyingKafkaTemplate` thêm vào. Listener container dùng reply template gửi giá trị trả về tới topic/partition được chỉ định và giữ correlation ID để requester ghép response. Nếu dùng `@SendTo("orders.replies")` cố định, phải bảo đảm topic đó đúng với reply container và chiến lược định tuyến response của requester.

## 10. Correlation ID và reply headers

Request/reply cần phân biệt nhiều request đang chờ đồng thời. `ReplyingKafkaTemplate` tạo correlation ID cho mỗi request và lưu mapping từ ID đó tới future tương ứng. Khi response quay lại, template đọc correlation ID để hoàn tất đúng future.

Các header Spring Kafka thường gặp:

| Header | Mục đích |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Liên kết response với request ban đầu |
| `KafkaHeaders.REPLY_TOPIC` | Cho responder biết reply topic cần gửi tới |
| `KafkaHeaders.REPLY_PARTITION` | Chỉ định partition nhận response khi dùng định tuyến theo partition |
| `KafkaHeaders.TOPIC` | Topic đích của request khi tạo record từ Spring Message |
| `KafkaHeaders.MESSAGE_KEY` | Key của Kafka record |

Không tự xóa correlation/reply headers khi chuyển đổi message. Nếu custom `KafkaHeaderMapper`, hãy bảo đảm các header request/reply và type metadata cần thiết được map qua Kafka record. Một converter có thể chuyển payload đúng nhưng request/reply vẫn timeout nếu correlation ID hoặc reply destination bị mất.

Nếu cần thay đổi tên correlation header hoặc cách sinh ID, `ReplyingKafkaTemplate` có các tùy chọn cấu hình tương ứng tùy phiên bản. Chỉ thay đổi khi cả requester và responder thống nhất cách truyền lại header. Correlation ID là metadata kỹ thuật của một lần request; không nên dùng nó thay cho business ID của đơn hàng hoặc giao dịch.

## 11. Chuyển đổi type metadata giữa các ứng dụng

Converter JSON thường dùng type headers để xác định lớp Java khi deserialize. Nếu requester gửi `com.example.client.OrderRequest` nhưng responder chỉ có `com.example.server.OrderRequest`, việc phụ thuộc trực tiếp vào tên class có thể làm hai ứng dụng gắn chặt package với nhau.

Có thể dùng type mapping theo token ổn định, ví dụ `order-request` và `order-reply`, để mỗi ứng dụng ánh xạ token sang class cục bộ tương ứng. Cấu hình chính xác phụ thuộc converter và phiên bản Spring Kafka; với JSON serializer/deserializer, các property `spring.json.type.mapping`, default type và trusted packages thường được dùng. Đảm bảo mapping request và reply thống nhất ở cả hai phía.

Không nhầm type metadata với schema version. Type ID trả lời câu hỏi payload thuộc kiểu nào; schema version mô tả cấu trúc payload đang dùng. Nếu contract tiến hóa theo thời gian, nên có trường version hoặc schema registry và quy tắc tương thích riêng.

Khi dùng converter tùy chỉnh, có thể chủ động đặt type header hoặc chuyển đổi sang envelope có trường `eventType` và `schemaVersion`. Tuy nhiên, đừng ghi đè các header `KafkaHeaders.CORRELATION_ID`, `REPLY_TOPIC` hoặc `REPLY_PARTITION` khi tạo response.

## 12. Timeout, send failure và reply failure

`ReplyingKafkaTemplate` trả về future để theo dõi cả kết quả gửi request và response. Có thể kiểm tra hai giai đoạn riêng:

```java
RequestReplyFuture<String, String, String> future =
        template.sendAndReceive(requestRecord);

SendResult<String, String> sendResult =
        future.getSendFuture().get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> replyRecord =
        future.get(10, TimeUnit.SECONDS);
```

`getSendFuture()` cho biết request có được producer gửi thành công hay không. Future chính hoàn tất khi nhận response phù hợp hoặc thất bại do timeout/lỗi. Nếu send thất bại, responder không nhận được request. Nếu send thành công nhưng future timeout, có thể responder chưa xử lý xong, không gửi reply, gửi sai topic/partition hoặc response bị mất correlation ID.

Timeout không chứng minh nghiệp vụ chưa được thực hiện. Request có thể đã được xử lý thành công nhưng response đến muộn. Nếu requester gửi lại sau timeout, responder có thể thực hiện nghiệp vụ hai lần. Dùng request ID/idempotency key ở tầng nghiệp vụ để chống lặp; correlation ID chỉ ghép response với lần gọi đang chờ.

Với lỗi nghiệp vụ, responder có thể trả về một response biểu diễn lỗi thay vì để request timeout. Một số phiên bản Spring Kafka hỗ trợ `setReplyErrorChecker(...)` trên template để nhận diện error response theo header/payload và hoàn tất future bằng exception. Hãy kiểm tra API theo phiên bản trước khi dùng; cách đơn giản và portable là định nghĩa `OrderReply` có `status`, `errorCode` và `message` rồi requester tự xử lý kết quả.

## 13. Nhiều requester instance và reply partition

Trong môi trường nhiều instance, mỗi requester có một tập future đang chờ trong bộ nhớ của chính nó. Response phải được route tới reply container của instance đã gửi request. Nếu các reply containers chia sẻ group và topic không đúng cách, response có thể được một instance khác nhận; instance đó không có correlation mapping tương ứng nên future ở requester ban đầu sẽ timeout.

Một số chiến lược thường dùng:

1. Dùng reply topic riêng cho từng requester instance.
2. Dùng một reply topic nhiều partition và một consumer group chung; mỗi requester chỉ chọn partition đang được assign cho reply container của chính nó, còn responder gửi vào partition được chỉ định trong reply partition header.
3. Dùng group ID riêng cho reply container của mỗi instance trên reply topic dùng chung. Khi đó mỗi group có thể nhận mọi response trên topic; template chỉ hoàn tất future có correlation ID khớp và bỏ qua response không thuộc instance đó. Cần tính tới lượng traffic nhân lên theo số requester instance.

Không chọn chiến lược chỉ dựa trên số partition. Hãy kiểm tra `waitForAssignment()`, partition được gán cho mỗi reply container và giá trị reply topic/partition header trong request. Kiểm thử ít nhất hai requester instance gửi request đồng thời để xác nhận response không bị giao chéo.

## 14. Lỗi thường gặp khi dùng converter với ReplyingKafkaTemplate

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassCastException` khi gửi | Converter tạo `String` nhưng producer serializer mong đợi object/byte array khác | Đồng bộ output type của converter với Kafka serializer |
| Listener không chuyển được JSON thành object | Converter không được gắn vào listener container factory hoặc type metadata không phù hợp | Cấu hình `setRecordMessageConverter()` và kiểm tra type mapping |
| Reply future timeout dù responder đã xử lý | Reply gửi sai topic/partition hoặc correlation header bị mất | Kiểm tra `KafkaHeaders.REPLY_TOPIC`, `REPLY_PARTITION`, `CORRELATION_ID` |
| Future hoàn tất nhưng payload sai kiểu | Reply converter không suy ra được type hoặc responder gửi sai payload | Kiểm tra JSON type headers, default type và contract reply |
| Reply container chưa sẵn sàng | Container chưa start hoặc chưa nhận partition assignment | Chờ `waitForAssignment()` trước khi gửi request |
| Request gửi thành công nhưng không có reply | Listener lỗi, thiếu `@SendTo`, thiếu reply template hoặc lỗi gửi response | Kiểm tra log responder, `setReplyTemplate()` và reply topic |
| Nhiều instance bị timeout ngẫu nhiên | Reply consumer group/partition routing khiến response tới nhầm instance | Thiết kế reply topic/partition và group ID theo từng requester |
| Timeout rồi retry tạo side effect trùng | Request trước có thể đã được xử lý nhưng response đến muộn | Dùng business request ID và idempotent handler |

## 15. Kiểm thử converter và request/reply flow

Nên kiểm thử riêng hai lớp: conversion và request/reply integration.

### Unit test converter

Kiểm tra object request được chuyển thành record payload có dạng mong đợi và có thể chuyển ngược thành object. Với JSON converter, kiểm tra các trường quan trọng, type metadata và null handling. Nếu dùng custom header mapper, kiểm tra các header kỹ thuật được giữ nguyên.

### Integration test với Kafka thử nghiệm

Một integration test nên xác minh toàn bộ luồng:

1. Khởi động broker thử nghiệm và tạo request/reply topics.
2. Khởi động reply listener container và đợi assignment.
3. Khởi động responder listener với converter và reply template.
4. Gửi `Message<OrderRequest>` qua `ReplyingKafkaTemplate`.
5. Xác minh responder nhận đúng `OrderRequest`.
6. Xác minh response mang correlation ID phù hợp và requester nhận đúng `OrderReply`.
7. Kiểm tra timeout, send failure, response lỗi và nhiều request đồng thời.

Các trường hợp nên có:

| Trường hợp | Kỳ vọng |
|---|---|
| Request/reply bình thường | Future hoàn tất với đúng response và payload type |
| Request payload Unicode | JSON/string giữ nguyên ký tự tiếng Việt |
| Thiếu responder | Future timeout theo cấu hình |
| Reply mất correlation ID | Không ghép nhầm future; request timeout và log có thể truy vết |
| Sai reply topic/partition | Phát hiện qua timeout và kiểm tra header/assignment |
| Nhiều request đồng thời | Mỗi future nhận đúng response theo correlation ID |
| Nhiều requester instance | Response tới đúng reply container của instance gửi request |
| Response nghiệp vụ lỗi | Requester nhận error result hoặc exception theo contract |

## Checklist trước khi đưa request/reply vào production

- Đã chọn rõ dùng `Message<?>` + converter hay `ProducerRecord` trực tiếp.
- Output type của converter tương thích với Kafka serializer/deserializer.
- Converter được cấu hình ở requester template và responder listener container factory khi cần.
- Reply container đã start và được assign partition trước khi gửi request.
- Reply topic/partition và consumer group được thiết kế để response về đúng requester instance.
- Correlation ID, reply topic và reply partition headers được giữ nguyên qua converter/header mapper.
- Type mapping/trusted packages phù hợp với contract giữa requester và responder.
- Có timeout hữu hạn và xử lý riêng send failure với reply timeout.
- Request có business ID/idempotency key để chống side effect trùng khi retry sau timeout.
- Có integration test cho nhiều request đồng thời, nhiều instance và response lỗi.

`RecordMessageConverter` giúp `ReplyingKafkaTemplate` làm việc tự nhiên với Spring `Message<?>`, payload object và headers. Để request/reply hoạt động đúng, converter, serializer/deserializer, type metadata và correlation/reply headers phải thống nhất ở cả hai phía. Khi thiết kế thêm timeout, routing và idempotency rõ ràng, ứng dụng có thể dùng request/reply trên Kafka một cách đáng tin cậy.
