# ErrorHandlingDeserializer

## 1. Vì sao cần ErrorHandlingDeserializer?

Kafka lưu key và value dưới dạng byte. Khi consumer đọc record, Kafka client gọi deserializer để chuyển byte thành kiểu dữ liệu ứng dụng. Nếu dữ liệu không hợp lệ, JSON sai cấu trúc, type header trỏ tới class không tồn tại hoặc schema không tương thích, deserializer có thể ném exception ngay trong quá trình `poll()`.

Vấn đề là exception xảy ra trước khi record được chuyển đến phương thức `@KafkaListener`. Nếu consumer dùng trực tiếp `JsonDeserializer` và deserialization thất bại, listener không nhận được record bình thường để xử lý lỗi theo nghiệp vụ. `DefaultErrorHandler` cũng cần một record để thực hiện retry hoặc recovery.

Spring Kafka cung cấp `ErrorHandlingDeserializer` (EHD) như một lớp bao quanh deserializer thật. EHD gọi deserializer delegate; nếu delegate ném exception, EHD bắt lỗi, trả về `null` cho key hoặc value bị lỗi và gắn thông tin lỗi cùng dữ liệu byte gốc vào record header. Listener container có thể dùng thông tin này để đưa lỗi vào cơ chế error handling.

```text
Kafka record (byte[] key/value)
             |
             v
    ErrorHandlingDeserializer
             |
             v
       Delegate deserializer
          /          \
         /            \
   deserialize OK   deserialize lỗi
        |                  |
        v                  v
    object value       trả null
                           |
                           v
                 gắn exception header
                 + giữ raw bytes gốc
                           |
                           v
                 Listener container / error handler
```

EHD không sửa JSON lỗi và cũng không tự quyết định retry. Nó chuyển lỗi deserialization thành metadata gắn với record để Spring Kafka có thể xử lý ở tầng container.

## 2. Delegate deserializer là gì?

`ErrorHandlingDeserializer` không tự giải mã JSON, String hay Avro. Nó bọc một deserializer khác, gọi là **delegate**. Delegate thực hiện chuyển đổi thực tế; EHD chịu trách nhiệm bắt exception nếu quá trình đó thất bại.

Ví dụ:

| Dữ liệu Kafka | Delegate phù hợp | Vai trò của EHD |
|---|---|---|
| Key dạng chuỗi | `StringDeserializer` | Bắt lỗi nếu delegate gặp lỗi bất ngờ và gắn thông tin lỗi cho key |
| Value dạng JSON | `JsonDeserializer` | Bắt lỗi JSON/type mapping và cung cấp exception header cho value |
| Value dạng byte | `ByteArrayDeserializer` | Bao lỗi từ delegate nếu có |

Có thể dùng EHD riêng cho key và value. Trong thực tế, nhiều ứng dụng chỉ bọc value vì key là chuỗi đơn giản; nếu key cũng có thể lỗi khi deserialize, hãy cấu hình EHD cho key tương ứng.

## 3. Cấu hình bằng Spring Boot application.yml

Giả sử topic `orders` chứa JSON của `OrderCreated`:

```java
package com.example.messaging.events;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}
```

Consumer có thể cấu hình EHD làm deserializer bên ngoài và `JsonDeserializer` làm delegate:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging.events
```

Trong cấu hình trên:

- `value-deserializer` là lớp wrapper `ErrorHandlingDeserializer`.
- `spring.deserializer.value.delegate.class` chỉ định delegate là `JsonDeserializer`.
- `spring.json.value.default.type` cấu hình kiểu value mặc định cho JSON delegate.
- `spring.json.use.type.headers: false` yêu cầu JSON delegate dùng kiểu đã cấu hình thay vì type header trong record.
- `spring.json.trusted.packages` giới hạn package DTO được phép dùng.

Nếu key cũng là JSON và cần bảo vệ lỗi deserialize key, có thể cấu hình tương tự:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.key.default.type: com.example.messaging.OrderKey
```

Nếu key là chuỗi, giữ `StringDeserializer` trực tiếp thường đơn giản hơn. Không bọc một deserializer không có khả năng ném lỗi có ý nghĩa nếu điều đó không đem lại lợi ích vận hành.

## 4. Cấu hình bằng Java ConsumerFactory

Khi tự tạo `ConsumerFactory`, khai báo EHD ở cấu hình Kafka client và delegate class trong properties:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                ErrorHandlingDeserializer.class);
        props.put(ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
                JsonDeserializer.class);
        props.put(JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.messaging.events");

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

`ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS` là property chỉ định delegate cho value. Với key, dùng `ErrorHandlingDeserializer.KEY_DESERIALIZER_CLASS`. Các property của JSON delegate như default type và trusted packages vẫn được truyền trong cấu hình consumer để delegate sử dụng.

Đảm bảo listener container factory sử dụng đúng `ConsumerFactory` này. Nếu Spring Boot đã auto-configure một factory khác, listener có thể tiếp tục dùng deserializer cũ nếu wiring không rõ ràng.

## 5. EHD xử lý lỗi và exception header như thế nào?

Khi delegate deserialize thành công, EHD trả object bình thường. Khi delegate ném exception, EHD tạo thông tin `DeserializationException`, chứa dữ liệu byte gốc và ngữ cảnh lỗi, rồi lưu thông tin đó trong header của record.

Hai header quan trọng được Spring Kafka định nghĩa trong `SerializationUtils`:

| Header constant | Dùng cho |
|---|---|
| `SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER` | Lỗi khi deserialize key |
| `SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER` | Lỗi khi deserialize value |

Giá trị key/value bị lỗi thường là `null` trong record được chuyển lên tầng listener/container. Header cho phép framework phân biệt `null` do deserialization thất bại với một null value hợp lệ được producer gửi (nếu hệ thống cho phép tombstone/null payload).

Raw bytes được giữ trong thông tin lỗi để phục vụ chẩn đoán hoặc chuyển tiếp record lỗi sang dead-letter topic. Vì header có thể chứa payload gốc và exception details, không nên log toàn bộ header một cách vô điều kiện; payload có thể chứa dữ liệu nhạy cảm hoặc rất lớn.

## 6. Record listener và error handler

Với record listener, listener container có thể kiểm tra exception header trước khi gọi phương thức listener. Khi phát hiện lỗi deserialization, container chuyển record và exception đến `CommonErrorHandler` (thường là `DefaultErrorHandler`) để retry hoặc recovery.

Ví dụ listener:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

Nếu value không deserialize được, phương thức `onOrder()` không nhận một `OrderCreated` hợp lệ để xử lý. Container xử lý exception header qua error handler theo cấu hình. Điều này giúp lỗi deserialize tham gia cùng cơ chế retry/recovery với lỗi xử lý listener, nhưng hai loại lỗi có nguyên nhân khác nhau và có thể cần chính sách retry khác nhau.

Lỗi JSON sai cú pháp thường là lỗi dữ liệu không thể khắc phục bằng retry. Nếu retry nhiều lần không thay đổi dữ liệu, partition có thể bị giữ lại và consumer lag tăng. Có thể phân loại deserialization exception là lỗi không retry hoặc giới hạn retry rất thấp rồi chuyển DLT.

## 7. Cấu hình DefaultErrorHandler và DeadLetterPublishingRecoverer

EHD cung cấp record cùng exception header để error handler có thể phục hồi. Một cấu hình phổ biến là retry có giới hạn rồi publish record lỗi sang dead-letter topic (DLT):

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

Ví dụ cấu hình hai lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau một giây. Khi hết retry, `DeadLetterPublishingRecoverer` publish record sang DLT theo quy tắc mặc định hoặc destination resolver do ứng dụng cấu hình.

Với record lỗi deserialize, recoverer có thể sử dụng raw bytes được lưu trong exception header để chuyển tiếp dữ liệu gốc. Producer dùng để publish DLT vì vậy phải serialize được cả payload bình thường và `byte[]` gốc. Nếu chỉ dùng `JsonSerializer` cho mọi kiểu value, việc gửi raw bytes có thể thất bại hoặc tạo payload không đúng mong muốn.

Trong hệ thống production, nên cấu hình DLT template có serializer phù hợp với nhiều kiểu dữ liệu (ví dụ `DelegatingByTypeSerializer` để xử lý `byte[]` và object đã deserialize) hoặc dùng template chuyên biệt cho raw bytes. Đồng thời tạo DLT topic, đặt retention phù hợp và có quy trình điều tra/phát lại record lỗi.

### Phân loại lỗi deserialize

Không phải mọi lỗi deserialization đều cần cùng số lần retry. Ví dụ:

| Lỗi | Hành vi thường phù hợp |
|---|---|
| JSON sai cú pháp | Không retry hoặc retry rất ít, sau đó DLT |
| Type header trỏ tới class không tồn tại | Sửa hợp đồng/type mapping; thường không có ích khi retry lặp |
| Package không nằm trong trusted packages | Sửa cấu hình consumer sau khi xác minh nguồn dữ liệu |
| Schema/version chưa tương thích | Sửa consumer hoặc triển khai schema tương thích; giữ raw bytes để xử lý lại |
| Lỗi tạm thời ở database sau khi deserialize thành công | Retry theo backoff phù hợp với lỗi nghiệp vụ/hạ tầng |

Có thể cấu hình `DefaultErrorHandler.addNotRetryableExceptions(...)` cho nhóm lỗi không thể khắc phục bằng retry. Cần xác định exception thực tế được bọc trong `DeserializationException` theo phiên bản đang dùng và kiểm thử cách phân loại trước khi đưa vào production.

## 8. Batch listener cần kiểm tra lỗi từng record

Batch listener nhận nhiều record trong một lần gọi. Nếu một record không deserialize được, EHD tạo record có value `null` và exception header tương ứng. Vì listener nhận cả batch, ứng dụng cần xác định record nào chứa lỗi để báo cho error handler.

Ví dụ nhận danh sách `ConsumerRecord` và ném `BatchListenerFailedException` tại record lỗi:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);
        Header errorHeader = record.headers().lastHeader(
                SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);

        if (errorHeader != null) {
            throw new BatchListenerFailedException(
                    "Order value could not be deserialized", index);
        }

        orderService.process(record.value());
    }
}
```

Trong ví dụ, listener kiểm tra exception header trước khi dùng `record.value()`. Khi tìm thấy lỗi, listener báo index của record lỗi cho `DefaultErrorHandler` bằng `BatchListenerFailedException`. Error handler có thể xử lý phần record trước đó và retry/recover từ vị trí lỗi theo cấu hình.

Nếu dùng batch listener nhận `List<OrderCreated>` thay vì `ConsumerRecord`, cần nhận thêm batch converted headers qua `KafkaHeaders.BATCH_CONVERTED_HEADERS` để kiểm tra lỗi theo đúng index. Với batch listener, không được giả định `null` luôn là một JSON null hợp lệ; hãy kiểm tra header lỗi trước khi xử lý.

## 9. Tạo fallback object bằng FailedDeserializationFunction

Trong một số ứng dụng, thay vì trả `null` khi delegate lỗi, có thể cấu hình function tạo một object đại diện cho payload lỗi. EHD hỗ trợ `FailedDeserializationFunction`, nhận `FailedDeserializationInfo` gồm dữ liệu gốc, exception, topic, headers và thông tin lỗi xảy ra ở key hay value.

Ví dụ một DTO có thể biểu diễn sự kiện hợp lệ hoặc sự kiện lỗi:

```java
public record OrderMessage(
        String eventId,
        OrderCreated event,
        boolean deserializationFailed,
        String error) {

    static OrderMessage invalid(FailedDeserializationInfo info) {
        return new OrderMessage(
                null,
                null,
                true,
                info.getException().getMessage());
    }
}
```

Function tạo fallback:

```java
public class OrderFailedDeserializationFunction
        implements Function<FailedDeserializationInfo, OrderMessage> {

    @Override
    public OrderMessage apply(FailedDeserializationInfo info) {
        return OrderMessage.invalid(info);
    }
}
```

Có thể cấu hình function qua property `spring.deserializer.value.function` bằng tên class triển khai phù hợp với kiểu value của consumer. Function cho key dùng property `spring.deserializer.key.function`.

Fallback object giúp listener nhận được một giá trị có kiểu để thực hiện luồng xử lý riêng, ví dụ ghi nhận sự kiện lỗi vào kho quarantine. Tuy nhiên, fallback không làm payload gốc trở nên hợp lệ và không thay thế việc quan sát exception header. Nếu listener chỉ xử lý object fallback như một sự kiện bình thường, lỗi dữ liệu có thể bị che giấu.

Chỉ dùng fallback khi mô hình nghiệp vụ có trạng thái lỗi rõ ràng. Nếu mục tiêu là retry/DLT theo cơ chế container, thường nên để EHD cung cấp `null` cùng exception header và cho error handler xử lý.

## 10. Phân biệt lỗi deserialize và lỗi nghiệp vụ

Hai lỗi xảy ra ở hai giai đoạn khác nhau:

| Tiêu chí | Lỗi deserialization | Lỗi xử lý nghiệp vụ |
|---|---|---|
| Thời điểm | Khi chuyển byte thành key/value, trước khi listener nhận record hợp lệ | Sau khi listener được gọi và bắt đầu xử lý payload |
| Ví dụ | JSON sai, type header sai, class không tồn tại, schema không tương thích | Database timeout, vi phạm quy tắc nghiệp vụ, API downstream lỗi |
| Listener nhận payload hợp lệ? | Không; key/value lỗi thường thành `null` và có exception header | Có thể nhận object đã deserialize |
| Thành phần liên quan | `ErrorHandlingDeserializer` | Listener và service nghiệp vụ |
| Cách khắc phục | Sửa serializer/schema/type/configuration hoặc giữ raw bytes để điều tra | Retry phù hợp, sửa dữ liệu/trạng thái nghiệp vụ hoặc DLT |

Không nên retry vô hạn một record JSON sai cấu trúc như cách retry timeout database. Ngược lại, không nên DLT ngay mọi lỗi tạm thời của dịch vụ phụ thuộc nếu retry có thể phục hồi.

## 11. Bảo toàn raw bytes và bảo mật dữ liệu lỗi

Raw bytes trong exception header rất hữu ích để điều tra record không deserialize được và phát lại sau khi sửa consumer. Tuy nhiên, dữ liệu này có thể chứa thông tin cá nhân, token hoặc dữ liệu nghiệp vụ nhạy cảm.

Khi vận hành:

- Không log toàn bộ raw bytes hoặc exception header ở mức INFO/ERROR nếu không có chính sách che dữ liệu.
- Giới hạn quyền truy cập DLT và thời gian lưu giữ theo yêu cầu dữ liệu.
- Ghi log metadata đủ để truy vết: topic, partition, offset, timestamp, event ID nếu đọc được và loại exception.
- Không ghi đè payload lỗi bằng object fallback nếu cần bảo toàn dữ liệu gốc để điều tra.
- Khi phát lại, xác minh schema và phiên bản consumer đã sửa có thể đọc dữ liệu trước khi gửi lại vào topic chính.

EHD là cơ chế hỗ trợ xử lý lỗi, không phải bộ lọc bảo mật hay schema registry. Hãy validate payload và kiểm soát nguồn producer độc lập với việc bật EHD.

## 12. Kiểm thử ErrorHandlingDeserializer

Kiểm thử nên bao phủ cả đường thành công, đường lỗi và quá trình recovery:

1. **Payload hợp lệ:** gửi JSON hợp lệ, xác nhận delegate deserialize thành DTO và listener xử lý bình thường.
2. **JSON sai cú pháp:** gửi byte JSON không hợp lệ, xác nhận EHD trả null cho value và gắn value deserializer exception header.
3. **Type header không hợp lệ:** gửi record có type header không thể giải quyết, xác nhận exception được ghi nhận theo cấu hình sử dụng type header.
4. **Lỗi key:** cấu hình EHD cho key và gửi key lỗi, xác nhận key exception header được tạo.
5. **Record listener:** xác nhận container chuyển lỗi deserialization đến error handler và listener không xử lý payload không hợp lệ như DTO bình thường.
6. **Batch listener:** xác nhận listener kiểm tra header và ném `BatchListenerFailedException` với đúng index.
7. **Retry và DLT:** xác nhận số lần retry, destination DLT và raw bytes được giữ lại khi publish record deserialize lỗi.
8. **Fallback function:** xác nhận function nhận `FailedDeserializationInfo` và tạo đúng sentinel object nếu ứng dụng sử dụng cơ chế này.
9. **Serializer DLT:** kiểm tra template DLT có thể gửi cả raw `byte[]` và payload đã deserialize.
10. **Dữ liệu nhạy cảm:** xác nhận log không in raw payload hoặc header chứa dữ liệu cần bảo vệ.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với phiên bản Spring Boot. Nên dùng broker/container test để kiểm tra end-to-end việc container phát hiện exception header và recoverer publish DLT; unit test riêng cho delegate không chứng minh toàn bộ luồng container hoạt động đúng.

## 13. Lỗi thường gặp khi cấu hình EHD

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| EHD không gọi được delegate | Thiếu `spring.deserializer.value.delegate.class` hoặc khai báo sai class | Kiểm tra delegate property và dependency của serializer |
| Listener nhận `null` | Deserialization thất bại và EHD trả null | Kiểm tra exception header; không giả định producer gửi null hợp lệ |
| Không thấy retry/DLT | Container không dùng error handler phù hợp hoặc batch listener chưa kiểm tra header | Xác nhận listener container factory và cách xử lý record/batch |
| DLT publish lỗi với `byte[]` | Producer template không có serializer cho raw bytes | Cấu hình serializer hỗ trợ cả byte[] và object bình thường |
| JSON vẫn lỗi dù có default type | Payload/schema không khớp hoặc type header đang được ưu tiên | Kiểm tra JSON, type header, default type và `spring.json.use.type.headers` |
| Consumer bị lag do record lỗi | Retry không cần thiết cho lỗi dữ liệu không thể phục hồi | Phân loại exception, giới hạn retry và chuyển DLT |
| Batch listener bỏ sót record lỗi | Chỉ kiểm tra payload null mà không đọc exception header | Nhận `ConsumerRecord`/converted headers và kiểm tra header theo index |

## 14. Quy trình lựa chọn và triển khai

1. Xác định key/value serializer và deserializer thực tế của producer/consumer.
2. Chọn delegate phù hợp, ví dụ `StringDeserializer` cho key và `JsonDeserializer` cho value.
3. Đặt `ErrorHandlingDeserializer` làm lớp deserializer bên ngoài cho phần dữ liệu có thể lỗi.
4. Cấu hình delegate bằng `spring.deserializer.key.delegate.class` hoặc `spring.deserializer.value.delegate.class`.
5. Với record listener, cấu hình error handler để retry/recover; phân loại lỗi dữ liệu không thể retry.
6. Với batch listener, kiểm tra exception header của từng record và báo record lỗi cho error handler.
7. Nếu dùng DLT, cấu hình template có thể gửi raw bytes và payload bình thường.
8. Chỉ cấu hình fallback function khi ứng dụng có mô hình xử lý object lỗi rõ ràng.
9. Kiểm thử payload hợp lệ, payload lỗi, retry, DLT và khả năng replay trước khi triển khai.

## 15. Tổng kết

- `ErrorHandlingDeserializer` bọc delegate deserializer và bắt exception xảy ra trong quá trình deserialize.
- Khi deserialize thất bại, EHD trả `null` cho key/value lỗi và gắn exception header chứa thông tin lỗi cùng raw bytes.
- Cấu hình delegate qua `spring.deserializer.key.delegate.class` và `spring.deserializer.value.delegate.class`.
- Record listener có thể để listener container chuyển lỗi đến `DefaultErrorHandler`; batch listener cần kiểm tra lỗi theo từng record.
- `DefaultErrorHandler` kết hợp `DeadLetterPublishingRecoverer` hỗ trợ retry có giới hạn và chuyển record lỗi sang DLT.
- DLT producer cần serializer phù hợp với raw `byte[]` và payload bình thường.
- `FailedDeserializationFunction` có thể tạo fallback object, nhưng không thay thế việc quan sát lỗi và bảo toàn dữ liệu gốc.
- Phân biệt lỗi deserialization với lỗi nghiệp vụ để chọn retry, sửa schema hoặc DLT phù hợp.

Khi cấu hình `ErrorHandlingDeserializer` đúng cách, ứng dụng Spring Kafka có thể đưa lỗi xảy ra trước listener vào cùng quy trình quan sát và phục hồi, bảo toàn raw payload để điều tra, đồng thời tránh để một record không hợp lệ âm thầm làm gián đoạn toàn bộ luồng consumer.
