# Xử lý reply không đúng kiểu

Trong mô hình request-reply của Spring Kafka, producer gửi request đến một topic và chờ response trên reply topic. Hai phía phải thống nhất contract của response: kiểu dữ liệu, schema, serializer/deserializer và metadata nhận diện kiểu. Nếu requester mong đợi `OrderReply` nhưng responder gửi `ErrorReply` hoặc một payload không tương thích, lỗi có thể xuất hiện ngay khi deserialize, lúc chuyển đổi message hoặc muộn hơn khi ứng dụng sử dụng kết quả.

Cách xử lý đáng tin cậy là xác định rõ response contract, cấu hình deserializer theo contract đó và kiểm tra các response đa hình bằng một mô hình có chủ đích. Không nên ép mọi reply thành một class bằng cast rồi hy vọng dữ liệu tương thích.

## 1. Request-reply cần một response contract rõ ràng

Ví dụ một luồng tạo đơn hàng:

```text
Requester
  request: OrderRequest
  expected reply: OrderReply

Responder
  receives: OrderRequest
  returns: OrderReply

Kafka
  orders.requests
  orders.replies
```

Request và reply là hai message contract độc lập. Requester có thể gửi đúng request nhưng vẫn nhận sai kiểu reply nếu responder trả nhầm DTO, hai service dùng phiên bản contract khác nhau hoặc cấu hình serializer/deserializer không đồng nhất.

Ví dụ DTO response:

```java
public record OrderReply(
        String orderId,
        String status,
        String message
) {
}
```

Requester nên xác định rõ `OrderReply` là kiểu kết quả của thao tác. Responder cũng nên trả DTO thuộc contract đã công bố, thay vì trả một implementation class nội bộ hoặc entity persistence.

Một contract tốt cần xác định:

- Tên và ý nghĩa các field.
- Kiểu dữ liệu, nullable hay bắt buộc.
- Cách biểu diễn trạng thái thành công và thất bại.
- Phiên bản schema hoặc contract.
- Cách tương thích khi thêm, đổi hoặc bỏ field.
- Cách biểu diễn response lỗi mà requester có thể hiểu.

## 2. Các dạng reply sai kiểu thường gặp

| Dạng lỗi | Ví dụ | Hậu quả |
|---|---|---|
| Responder trả nhầm DTO | Requester chờ `OrderReply`, responder trả `CustomerReply` | Deserialize hoặc cast thất bại |
| Type header chỉ đến class khác | Header ghi `com.server.ErrorReply` | Deserializer cố tạo kiểu không mong đợi |
| Type header chứa tên class không tồn tại ở requester | Producer gửi tên class nội bộ của service khác | `ClassNotFoundException` hoặc lỗi deserialize |
| Không có type header và default type sai | Payload OrderReply bị đọc thành OrderRequest | Lỗi mapping hoặc dữ liệu sai nghĩa |
| Field không tương thích | `amount` đổi từ number sang object | Jackson có thể báo lỗi mapping |
| Response generic bị mất kiểu | Mong đợi `List<OrderItemReply>` nhưng chỉ khai báo raw `List` | Phần tử có thể thành `Map` thay vì DTO |
| Reply lỗi dùng một DTO riêng | Thành công trả `OrderReply`, thất bại trả `ErrorReply` | Một requester chỉ khai báo một kiểu có thể không đọc được cả hai |
| Listener method nhận sai kiểu | Method khai báo `OrderReply` nhưng converter tạo kiểu khác | Message conversion hoặc argument resolution thất bại |

Cần phân biệt lỗi deserialize với lỗi nghiệp vụ. Nếu JSON được parse thành DTO nhưng field bắt buộc bị null, listener vẫn có thể chạy; lỗi chỉ xuất hiện khi validation hoặc business logic sử dụng field đó. Vì vậy, không phải mọi trường hợp reply sai kiểu đều phát sinh `SerializationException`.

## 3. Type header của Spring Kafka ảnh hưởng đến kiểu reply

`JsonSerializer` của Spring Kafka mặc định thêm type information vào Kafka headers; có thể tắt hành vi này bằng cấu hình serializer. Header `__TypeId__` thường cho biết class của value; với cấu trúc phức tạp có thể có thêm thông tin kiểu key, content hoặc container.

`JsonDeserializer` mặc định sử dụng type headers nếu chúng có mặt để quyết định class cần tạo. Vì vậy, requester khai báo `ReplyingKafkaTemplate<String, OrderRequest, OrderReply>` chưa đủ để bảo đảm payload luôn được deserialize thành `OrderReply`: generic type của Java không tự ghi đè type header mà deserializer đang sử dụng.

Ví dụ responder gửi `OrderReply`, nhưng type header chỉ đến `com.internal.server.OrderReply`. Nếu class này không có trong requester, deserialize có thể thất bại dù JSON fields tương thích với DTO dùng ở requester.

Có ba cách thiết kế phổ biến:

1. **Một reply type cố định:** requester bỏ qua type header và luôn deserialize value thành DTO đã chọn.
2. **Nhiều reply type có kiểm soát:** dùng type mapping hoặc một hierarchy/envelope contract chung.
3. **Payload độc lập với Java class:** dùng `byte[]`, JSON tree hoặc một envelope có `type` và `payload`, sau đó dispatch bằng code của ứng dụng.

Chọn một chiến lược thống nhất cho từng reply topic. Không trộn nhiều quy ước type header mà requester không thể dự đoán.

## 4. Cấu hình requester khi chỉ chấp nhận một kiểu reply

Nếu mọi response của request đều phải là `OrderReply`, cấu hình reply consumer để luôn đọc value thành kiểu này. Với `JsonDeserializer`, có thể đặt default type và tắt việc dùng type headers.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-requester
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.contracts.OrderReply
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.contracts
```

Các thuộc tính có dấu chấm được đặt trong bracket notation để Spring Boot giữ nguyên tên Kafka property khi bind.

Ý nghĩa:

- `spring.json.value.default.type` chỉ định class đích cho value.
- `spring.json.use.type.headers=false` yêu cầu deserializer bỏ qua type header khi chọn class.
- `spring.json.trusted.packages` giới hạn package được phép deserialize.
- Key vẫn được deserialize bằng `StringDeserializer` trong ví dụ.

Nếu tạo `JsonDeserializer` trực tiếp trong Java, cấu hình tương đương có thể được thể hiện như sau:

```java
JsonDeserializer<OrderReply> replyDeserializer =
        new JsonDeserializer<>(OrderReply.class);

replyDeserializer.addTrustedPackages("com.example.contracts");
replyDeserializer.ignoreTypeHeaders();
```

API fluent và constructor có thể thay đổi theo phiên bản Spring Kafka. Tránh vừa cấu hình cùng một thuộc tính qua constructor, setter và map properties nếu không nắm rõ thứ tự ưu tiên.

Với chiến lược fixed type, một payload `ErrorReply` không tự biến thành `OrderReply` chỉ vì deserializer đã bỏ qua type header. Nếu hai DTO có cấu trúc khác nhau, việc mapping có thể thất bại hoặc tạo object thiếu dữ liệu. Hãy dùng một contract response chung nếu requester cần nhận cả thành công và thất bại.

## 5. Cấu hình ReplyingKafkaTemplate với response type cụ thể

`ReplyingKafkaTemplate<K, V, R>` mô tả key, request value và reply value ở tầng API. Reply container cũng phải được cấu hình đúng kiểu `R` để deserialize response.

Ví dụ cấu hình reply consumer cho `OrderReply`:

```java
@Bean
ConsumerFactory<String, OrderReply> orderReplyConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-requester"
    );
    properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
    );
    properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class
    );
    properties.put(
            JsonDeserializer.VALUE_DEFAULT_TYPE,
            OrderReply.class.getName()
    );
    properties.put(
            JsonDeserializer.USE_TYPE_INFO_HEADERS,
            false
    );
    properties.put(
            JsonDeserializer.TRUSTED_PACKAGES,
            "com.example.contracts"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
```

Tạo reply listener container và template:

```java
@Bean
ConcurrentMessageListenerContainer<String, OrderReply> orderReplyContainer(
        ConsumerFactory<String, OrderReply> orderReplyConsumerFactory) {

    ContainerProperties containerProperties =
            new ContainerProperties("orders.replies");

    containerProperties.setGroupId("orders-requester");

    return new ConcurrentMessageListenerContainer<>(
            orderReplyConsumerFactory,
            containerProperties
    );
}

@Bean
ReplyingKafkaTemplate<String, OrderRequest, OrderReply> orderRequestTemplate(
        ProducerFactory<String, OrderRequest> requestProducerFactory,
        ConcurrentMessageListenerContainer<String, OrderReply> orderReplyContainer) {

    return new ReplyingKafkaTemplate<>(
            requestProducerFactory,
            orderReplyContainer
    );
}
```

Ví dụ này giả định một requester instance dùng reply topic cố định và mọi reply của topic đều tuân theo `OrderReply`. Nếu triển khai nhiều requester instance cùng reply topic, hãy tạo group ID riêng cho từng instance như mục correlation/routing bên dưới. Trong ứng dụng Spring Boot, cần bảo đảm các bean `KafkaProperties`, producer factory, imports và listener container được cấu hình phù hợp với phiên bản đang sử dụng.

Gửi request và đọc reply:

```java
ProducerRecord<String, OrderRequest> requestRecord =
        new ProducerRecord<>(
                "orders.requests",
                request.orderId(),
                request
        );

RequestReplyFuture<String, OrderRequest, OrderReply> future =
        orderRequestTemplate.sendAndReceive(requestRecord);

ConsumerRecord<String, OrderReply> replyRecord =
        future.get(10, TimeUnit.SECONDS);

OrderReply reply = replyRecord.value();
```

Kiểu `OrderReply` ở đây được bảo đảm bởi cấu hình reply consumer, không chỉ bởi generic của template. Nếu responder gửi một kiểu không tương thích, lỗi cần được phát hiện ở ranh giới deserialize/contract và đưa vào đường xử lý lỗi có quan sát được.

## 6. Responder phải trả đúng contract

Listener xử lý request nên trả đúng DTO response đã thống nhất. Ví dụ:

```java
@KafkaListener(
        topics = "orders.requests",
        groupId = "orders-service"
)
public OrderReply handle(OrderRequest request) {
    OrderResult result = orderService.create(request);

    return new OrderReply(
            result.orderId(),
            result.status(),
            result.message()
    );
}
```

Để listener tự gửi response, cấu hình listener container factory phía responder với một `KafkaTemplate` dùng để publish reply:

```java
factory.setReplyTemplate(responderReplyTemplate);
```

`ReplyingKafkaTemplate` ở requester gắn reply topic và correlation ID vào request. Listener container phía responder sử dụng `responderReplyTemplate` để gửi kết quả về địa chỉ reply được yêu cầu; cần bảo đảm reply template và listener adapter giữ đúng headers routing/correlation theo cấu hình của ứng dụng. Đây là `KafkaTemplate` thông thường ở responder, không phải `ReplyingKafkaTemplate` của requester.

Không trả trực tiếp JPA entity, Hibernate proxy, exception object hoặc class implementation riêng của responder. Chuyển chúng thành DTO contract trước khi gửi qua Kafka. Như vậy requester không phải phụ thuộc package nội bộ hay thư viện persistence của responder.

Nếu responder cần trả lỗi nghiệp vụ, hãy biểu diễn lỗi trong response contract, chẳng hạn `OrderReply` có `status=REJECTED` và `message` phù hợp. Không dùng một exception Java tùy ý làm response payload.

## 7. Khi requester cần nhận nhiều loại reply

Một số API có nhiều kết quả hợp lệ. Ví dụ request có thể trả về `OrderAccepted` hoặc `OrderRejected`. Có hai cách thiết kế thường dùng.

**Cách A: một envelope chung**

```java
public record OrderResponse(
        String responseType,
        String orderId,
        String status,
        String message
) {
}
```

Cả thành công và thất bại đều dùng `OrderResponse`. Requester chỉ cần một deserializer và kiểm tra `responseType` hoặc `status` để chọn nhánh xử lý.

```java
switch (response.responseType()) {
    case "ORDER_ACCEPTED" -> handleAccepted(response);
    case "ORDER_REJECTED" -> handleRejected(response);
    default -> throw new IllegalArgumentException(
            "Unsupported response type: " + response.responseType()
    );
}
```

Cách này phù hợp khi các reply có chung các metadata và lifecycle. Nếu payload của từng loại khác nhau đáng kể, envelope có thể chứa thêm trường `payload` và version, nhưng cần xác định rõ cách deserialize payload theo type.

**Cách B: dùng type mapping cho nhiều DTO**

Spring Kafka hỗ trợ type mapping giữa token ổn định và class Java. Producer có thể ánh xạ class response thành token; requester ánh xạ token về class DTO tương ứng.

Ví dụ cấu hình mapping:

```properties
spring.json.type.mapping=accepted:com.example.contracts.OrderAccepted,rejected:com.example.contracts.OrderRejected
```

Hai phía phải thống nhất token, nhưng có thể ánh xạ token tới class nằm trong package khác nhau ở từng service. Điều này giảm phụ thuộc vào tên class đầy đủ của service phát message.

Với nhiều kiểu reply, nên khai báo template/deserializer theo một kiểu cha hoặc `Object`, rồi kiểm tra kiểu cụ thể trước khi sử dụng. Generic `R` không tự kiểm tra toàn bộ các kiểu con tại runtime.

Không dùng type mapping như cơ chế cho phép deserialize mọi class. Chỉ khai báo các response type nằm trong contract được phép.

## 8. Generic response và kiểu collection

Một nguyên nhân khác là Java type erasure. Nếu requester khai báo `List` raw type, Jackson không biết phần tử phải là `OrderItemReply`; các phần tử có thể được tạo thành `LinkedHashMap`.

Ví dụ không nên dùng:

```java
RequestReplyFuture<String, OrderRequest, List> rawListFuture =
        rawListReplyTemplate.sendAndReceive(requestRecord);
ConsumerRecord<String, List> replyRecord =
        rawListFuture.get(10, TimeUnit.SECONDS);

List items = replyRecord.value();
OrderItemReply item = (OrderItemReply) items.get(0);
```

Ở đây reply container dùng `JsonDeserializer` với default type là `List.class` và không có metadata kiểu phần tử. Jackson có thể tạo từng phần tử thành `LinkedHashMap`; phép cast sang `OrderItemReply` sẽ thất bại.

Hãy dùng một DTO có kiểu phần tử cụ thể:

```java
public record OrderItemsReply(
        String orderId,
        List<OrderItemReply> items
) {
}

public record OrderItemReply(
        String sku,
        int quantity
) {
}
```

Khi contract cần collection ở cấp cao nhất, hãy cấu hình Jackson với `TypeReference`/`JavaType` phù hợp và xác nhận `JsonDeserializer` của phiên bản Spring Kafka hỗ trợ cách khởi tạo đó. Một envelope DTO thường đơn giản hơn vì giữ được thông tin kiểu phần tử, metadata và schema version trong một contract rõ ràng.

Không dựa vào generic declaration của `ReplyingKafkaTemplate` để phục hồi generic element type đã mất sau type erasure.

## 9. Phân biệt deserialize, message conversion và cast

Reply sai kiểu có thể lỗi ở các tầng khác nhau:

| Tầng | Ví dụ lỗi | Nơi kiểm tra |
|---|---|---|
| Kafka deserializer | JSON không parse được, class trong type header không tồn tại | `JsonDeserializer`, type headers, `ErrorHandlingDeserializer` |
| Message converter | Message được deserialize nhưng không chuyển được sang tham số listener | Record/message converter và method signature |
| Runtime cast | Giá trị thực là `ErrorReply` nhưng code ép thành `OrderReply` | Contract, generic boundary và validation |
| Business validation | DTO đúng class nhưng field bắt buộc thiếu hoặc trạng thái không hợp lệ | Bean Validation và business rules |
| Correlation/routing | Reply không khớp request đang chờ | Correlation ID, reply topic, reply partition |

Khi debug, hãy xác định tầng phát sinh lỗi trước. Đổi `trusted.packages` không sửa được JSON sai schema; đổi DTO không sửa được correlation ID bị mất; tăng timeout cũng không sửa được response deserializer đang thất bại.

## 10. Xử lý deserialize lỗi trên reply consumer

Nếu reply payload có thể lỗi định dạng, có thể bọc deserializer bằng `ErrorHandlingDeserializer` để giữ exception và raw bytes trong header. Điều này giúp container có dữ liệu chẩn đoán và hỗ trợ đường recovery.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.contracts.OrderReply
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.contracts
```

Tuy nhiên, reply consumer của `ReplyingKafkaTemplate` có một yêu cầu bổ sung: lỗi deserialize phải được quan sát và liên kết với request đang chờ. Nếu error handler chỉ log rồi bỏ record, requester có thể không nhận được response hợp lệ và cuối cùng timeout. Không được xem một giá trị null do deserialize failure là response thành công.

Với hệ thống quan trọng, hãy định nghĩa cách xử lý rõ ràng: phát hiện lỗi deserialize, ghi log/metric có correlation ID, lưu raw payload hoặc chuyển sang error topic theo chính sách, rồi hoàn tất request bằng lỗi có thể quan sát được nếu kiến trúc cho phép. Nếu không thể chuyển lỗi thành future failure trực tiếp, phải có timeout và cảnh báo để không che giấu reply hỏng.

## 11. Correlation ID và reply routing

Ngay cả khi response đúng kiểu, requester vẫn có thể nhận nhầm reply nếu correlation ID hoặc reply destination bị sai.

`ReplyingKafkaTemplate` dùng correlation ID để ghép response với request đang chờ. Một reply hợp lệ cần:

- Có correlation ID tương ứng với request đang chờ.
- Được gửi đến reply topic mà reply container đang consume.
- Có partition routing phù hợp nếu reply container chỉ subscribe một số partition.
- Được serialize theo response contract mà requester đã cấu hình.

Không tự tạo hoặc ghi đè correlation ID nếu không có lý do. Khi dùng custom responder, hãy giữ correlation header từ request sang response theo quy ước Spring Kafka. Khi nhiều requester instance dùng chung reply topic, mỗi instance cần reply consumer group riêng để mọi instance đều nhận được bản sao reply và tự đối chiếu correlation ID. Bật chế độ shared reply topic trên template:

```java
orderRequestTemplate.setSharedReplyTopic(true);
```

Nếu các instance dùng chung một consumer group, Kafka phân phối mỗi record cho một instance; instance không sở hữu correlation ID tương ứng sẽ bỏ qua reply và request đang chờ ở instance khác có thể timeout. Chỉ dùng shared reply topic khi các requester cùng tuân theo cơ chế correlation của `ReplyingKafkaTemplate`.

Nếu dùng reply topic động, requester và responder phải thống nhất cách truyền/đọc `KafkaHeaders.REPLY_TOPIC` và `KafkaHeaders.REPLY_PARTITION`. Nếu dùng reply topic cố định, bảo đảm reply container subscribe đúng topic và không để nhiều client cạnh tranh đọc cùng một reply mà client khác đang chờ.

## 12. Timeout không đồng nghĩa reply sai kiểu

`ReplyingKafkaTemplate` có thể timeout khi không nhận được reply tương ứng trong thời gian chờ. Nguyên nhân có thể là responder chưa xử lý, reply gửi sai topic/partition, correlation ID không khớp hoặc reply consumer không deserialize được response.

Ví dụ xử lý future:

```java
try {
    ConsumerRecord<String, OrderReply> replyRecord =
            future.get(10, TimeUnit.SECONDS);

    OrderReply reply = replyRecord.value();
    validateReply(reply);
}
catch (TimeoutException exception) {
    throw new OrderReplyTimeoutException(
            "No valid reply received in time",
            exception
    );
}
catch (ExecutionException exception) {
    throw new OrderReplyFailedException(
            "Request-reply failed",
            exception.getCause()
    );
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new OrderReplyFailedException(
            "Waiting for the reply was interrupted",
            exception
    );
}
```

Cần phân biệt timeout, lỗi gửi request, lỗi deserialize reply và response nghiệp vụ từ chối. Đừng tự động gửi lại request khi timeout nếu thao tác không idempotent: responder có thể đã xử lý request và chỉ reply bị thất lạc. Dùng request ID/idempotency key để chống tạo đơn hàng hoặc side effect trùng.

## 13. Kiểm thử reply sai kiểu

Kiểm thử phải xác nhận cả response đúng contract lẫn các trường hợp responder trả sai kiểu hoặc sai schema.

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Responder trả đúng `OrderReply` | Requester nhận đúng DTO và correlation ID |
| Type header trỏ đến class nội bộ không có ở requester | Deserialization failure được quan sát |
| Tắt type headers và đặt default type | Payload được đọc theo response DTO cố định |
| Responder trả `ErrorReply` trong flow chỉ nhận `OrderReply` | Contract violation bị phát hiện, không bị xem là thành công |
| JSON sai định dạng | Error handler ghi nhận lỗi; raw bytes có thể được lưu |
| Thiếu field bắt buộc | Validation phát hiện trước khi dùng response |
| Reply sai topic | Request timeout và có metric chẩn đoán |
| Correlation ID không khớp | Reply không hoàn tất nhầm future |
| Hai loại reply qua type mapping | Mỗi token được deserialize thành đúng DTO |
| Generic list | Phần tử được tạo thành đúng DTO, không phải `Map` |

Với Embedded Kafka hoặc Testcontainers:

1. Tạo request topic và reply topic.
2. Khởi chạy requester với reply container và response deserializer thật.
3. Khởi chạy responder test có thể trả DTO đúng, DTO sai và payload JSON lỗi.
4. Gửi request với correlation ID.
5. Xác nhận reply đúng type hoàn tất future.
6. Gửi reply sai type và xác nhận error/timeout path đúng thiết kế.
7. Kiểm tra log/metric có request ID hoặc correlation ID, không log toàn bộ payload nhạy cảm.
8. Kiểm thử timeout và retry để bảo đảm không tạo side effect trùng.

## 14. Những lỗi thường gặp và checklist

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ClassNotFoundException` khi đọc reply | Type header chứa tên class chỉ có ở responder | Dùng DTO contract dùng chung, type mapping hoặc bỏ qua type header |
| `ClassCastException` sau khi nhận reply | Runtime value khác kiểu code mong đợi | Kiểm tra type thực tế và tránh cast mù |
| `MessageConversionException` | Converter không chuyển được payload sang tham số listener | Đồng bộ DTO, converter và method signature |
| JSON parse thất bại | Schema hoặc JSON shape không tương thích | Version contract và kiểm thử tương thích |
| Reply thành `Map`/`LinkedHashMap` | Deserializer không biết kiểu đích hoặc generic type bị xóa | Dùng DTO/envelope hoặc cấu hình `JavaType` |
| Request timeout dù responder đã xử lý | Reply gửi sai topic/partition, correlation ID mất hoặc deserialize lỗi | Kiểm tra reply headers, container và error handler |
| Reply lỗi biến thành null | Error handler đã nuốt deserialize failure | Không coi null là thành công; phát metric và hoàn tất request bằng lỗi |
| Deserialize bị từ chối vì package | Package chưa nằm trong trusted packages | Chỉ thêm package contract tin cậy |
| Thêm field mới làm client cũ lỗi | Quy tắc schema compatibility không được xác định | Thiết kế field optional/default và kiểm thử version |

Checklist trước khi triển khai:

1. Chốt một response contract cho mỗi request operation.
2. Dùng DTO contract ổn định, không gửi entity hoặc class nội bộ.
3. Chọn rõ deserializer dùng type headers hay một default reply type cố định.
4. Nếu có nhiều reply type, dùng envelope hoặc type mapping có whitelist.
5. Cấu hình trusted packages tối thiểu cần thiết.
6. Không dùng raw collection hoặc cast response mù.
7. Giữ correlation ID và reply routing headers.
8. Phân biệt deserialize failure, conversion failure, business rejection và timeout.
9. Thiết kế idempotency trước khi retry request.
10. Kiểm thử reply sai class, sai schema, JSON lỗi, timeout và correlation mismatch.

Reply không đúng kiểu là lỗi contract hoặc cấu hình serialization/deserialization. Khi requester và responder thống nhất DTO, type metadata và reply routing, `ReplyingKafkaTemplate` có thể trao đổi response ổn định. Với nhiều loại kết quả, hãy biểu diễn sự đa hình một cách rõ ràng để requester biết chính xác loại response mà nó đang xử lý.
