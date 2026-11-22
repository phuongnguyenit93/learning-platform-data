# Bộ chuyển đổi JSON cho JMS theo phiên bản đang sử dụng

> Mục tiêu: cấu hình bộ chuyển đổi JSON để gửi và nhận DTO qua JMS; hiểu sự khác nhau giữa `MappingJackson2MessageConverter` và `JacksonJsonMessageConverter`; chọn đúng API theo Spring Framework/Jackson đang có trong dependency tree; đồng thời quản lý type ID, content metadata, encoding và an toàn khi deserialize.

## 1. Vì sao JMS cần MessageConverter?

JMS làm việc với các kiểu message như `TextMessage`, `BytesMessage`, `MapMessage` và `ObjectMessage`. Trong khi đó, ứng dụng thường làm việc với DTO Java như `OrderCreated`. Một `MessageConverter` chuyển đổi giữa hai mô hình:

- **Chiều gửi:** DTO Java → JSON bytes hoặc text → JMS message.
- **Chiều nhận:** JMS message → đọc JSON → DTO Java có kiểu.

`JmsTemplate.convertAndSend()` và `receiveAndConvert()` dùng `org.springframework.jms.support.converter.MessageConverter`. Converter mặc định `SimpleMessageConverter` phù hợp với các kiểu JMS cơ bản như `String`, `byte[]` và `Map`; muốn gửi DTO dưới dạng JSON, cần cấu hình converter Jackson. <https://docs.spring.io/spring-framework/reference/integration/jms/sending.html>

Không nhầm interface JMS converter với `org.springframework.messaging.converter.MessageConverter`. Hai interface có package và mục đích khác nhau. `JmsTemplate` dùng converter thuộc `org.springframework.jms.support.converter`; `JmsMessagingTemplate` và `JmsClient` làm việc với abstraction Spring Messaging và converter tương ứng của nó.

## 2. Chọn converter theo phiên bản Spring và Jackson

Tên class cần chọn phụ thuộc phiên bản Spring Framework thực tế được resolve, không chỉ phụ thuộc phiên bản Jackson mà bạn muốn dùng:

| Nền tảng | Converter JSON JMS | Ghi chú |
|---|---|---|
| Spring Framework 5.x + Jackson 2 | `MappingJackson2MessageConverter` | Dùng `javax.jms`; các ví dụ cần đổi import JMS từ `jakarta.jms` sang `javax.jms` |
| Spring Framework 6.x + Jackson 2 | `MappingJackson2MessageConverter` | Dùng `jakarta.jms`; phù hợp với ứng dụng Spring 6 và Spring Boot 3 |
| Spring Framework 7.0 + Jackson 3 | `JacksonJsonMessageConverter` | Converter mới dùng Jackson 3 và package `tools.jackson`; đây là hướng được khuyến nghị |
| Spring Framework 7.0 + Jackson 2 | `MappingJackson2MessageConverter` | Vẫn có trong 7.0 nhưng đã deprecated từ 7.0 và được đánh dấu for removal |

Spring Framework 7.0 đưa `JacksonJsonMessageConverter` vào để dùng Jackson 3. `MappingJackson2MessageConverter` bị deprecated từ 7.0 để chuyển sang converter mới. Jackson 3 dùng package `tools.jackson.*`, khác package `com.fasterxml.jackson.*` của Jackson 2. <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html> <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html>

Nếu dự án đang ở Spring Framework 6.2, dùng `MappingJackson2MessageConverter`. Nếu dự án đã nâng lên Spring Framework 7.0 và dùng Jackson 3, chuyển sang `JacksonJsonMessageConverter`. Không import converter Spring 7 vào dự án Spring 6 vì class đó chưa tồn tại ở phiên bản 6.

### Kiểm tra dependency đang thực sự được dùng

Với Maven, xem dependency tree của các module liên quan:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-jms,com.fasterxml.jackson.core:jackson-databind,tools.jackson.core:jackson-databind
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Kiểm tra cả dependency được khai báo trực tiếp lẫn dependency được Spring Boot BOM hoặc dependency management kéo vào. Tránh ép một module `spring-jms` lên version khác với các module Spring Framework còn lại. Khi dùng Spring Boot, ưu tiên để BOM của Boot quản lý phiên bản Spring và Jackson đồng bộ.

## 3. DTO và hợp đồng JSON

Bắt đầu bằng một DTO đơn giản có schema rõ ràng:

```java
package com.example.messaging;

public record OrderCreated(
        String orderId,
        int itemCount,
        int schemaVersion
) {}
```

Ví dụ JSON tương ứng:

```json
{
  "orderId": "ORD-100",
  "itemCount": 2,
  "schemaVersion": 1
}
```

DTO dùng cho message nên biểu diễn hợp đồng trao đổi giữa producer và consumer. Hạn chế gửi trực tiếp JPA entity, object chứa lazy relationship, service hoặc object phụ thuộc trạng thái nội bộ của một ứng dụng. Dùng kiểu dữ liệu ổn định và xác định rõ field bắt buộc, field tùy chọn, giá trị mặc định và quy tắc tương thích khi thêm field.

JSON chỉ xác định cú pháp dữ liệu. Nó không tự định nghĩa event type hay schema version. Hãy tách riêng:

- `contentType`: representation, ví dụ `application/json`.
- `eventType`: loại sự kiện, ví dụ `order-created-v1`.
- `schemaVersion`: phiên bản cấu trúc payload, ví dụ `1`.

## 4. Cấu hình cho Spring Framework 6.x và Jackson 2

`org.springframework.jms.support.converter.MappingJackson2MessageConverter` dùng Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`). Converter có thể đọc `TextMessage` hoặc `BytesMessage`; khi gửi, mặc định nó tạo `BytesMessage`. Nếu muốn body dạng text dễ quan sát và tương tác với hệ thống khác, đặt target type thành `MessageType.TEXT`. Encoding mặc định là UTF-8. <https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html>

Ví dụ dưới đây dùng API Spring Framework 6.2.19+ để có `setTrustedPackages`:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConverterConfiguration {

    @Bean
    MappingJackson2MessageConverter jmsJsonMessageConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
                "order-created-v1", OrderCreated.class
        ));
        converter.setTrustedPackages("com.example.messaging");
        return converter;
    }
}
```

Ý nghĩa:

- `setTargetType(MessageType.TEXT)` yêu cầu converter gửi JSON trong `TextMessage`. Nếu không đặt, converter mặc định dùng `BytesMessage` (`MessageType.BYTES`).
- `setTypeIdPropertyName("eventType")` chọn JMS property để mang định danh kiểu payload.
- `setTypeIdMappings(...)` ánh xạ ID ổn định `order-created-v1` sang class `OrderCreated`.
- `setTrustedPackages(...)` giới hạn package Java được phép dùng khi deserialize.

`setTrustedPackages` có từ Spring Framework 6.2.19. Nếu dự án ở Spring 6.0, 6.1 hoặc Spring 6.2 cũ hơn 6.2.19, phương thức này chưa có; không copy nguyên ví dụ trên vào dự án đó. Khi chưa có API này, ưu tiên type ID mapping tường minh, không gửi tên class Java thô, không bật polymorphic default typing cho message không tin cậy và cân nhắc nâng lên bản Spring có hỗ trợ trusted packages.

Nếu cần dùng `ObjectMapper` đã cấu hình, Spring Framework 6.1 trở lên có constructor nhận `ObjectMapper`; các phiên bản trước có thể dùng constructor mặc định và setter `setObjectMapper(...)` nếu API của bản đang chạy hỗ trợ.

## 5. Cấu hình cho Spring Framework 7.0 và Jackson 3

Với Spring Framework 7.0 và Jackson 3, dùng `org.springframework.jms.support.converter.JacksonJsonMessageConverter`. Class này dùng `tools.jackson.databind.json.JsonMapper`, đọc `TextMessage` và `BytesMessage`, và mặc định gửi ra `BytesMessage`. Có thể chọn `MessageType.TEXT` nếu hợp đồng cần text body.

Ví dụ cho Spring Framework 7.0.8+:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.support.converter.JacksonJsonMessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Configuration
class JmsJsonConverterConfiguration {

    @Bean
    JacksonJsonMessageConverter jmsJsonMessageConverter() {
        var converter = new JacksonJsonMessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("eventType");
        converter.setTypeIdMappings(Map.of(
                "order-created-v1", OrderCreated.class
        ));
        converter.setTrustedPackages("com.example.messaging");
        return converter;
    }
}
```

`JacksonJsonMessageConverter` có từ Spring Framework 7.0. `setTrustedPackages` có từ 7.0.8; nếu đang dùng Spring 7.0.0 đến 7.0.7 thì bỏ lời gọi này và dùng type ID mapping tường minh, đồng thời nâng cấp khi có thể. Constructor mặc định tạo `JsonMapper` và tự tìm các Jackson module theo cơ chế của Spring; nếu cần mapper riêng, converter cũng có constructor nhận `JsonMapper` hoặc builder. <https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/JacksonJsonMessageConverter.html>

Không trộn `com.fasterxml.jackson.databind.ObjectMapper` của Jackson 2 với `tools.jackson.databind.json.JsonMapper` của Jackson 3. Đây là hai thế hệ API khác nhau.

## 6. Gắn converter vào JmsTemplate và listener container

Tạo converter bean thôi chưa đủ. Cả producer lẫn consumer phải sử dụng converter tương thích với hợp đồng JSON.

Ví dụ wiring dùng interface converter JMS để có thể thay implementation theo phiên bản:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConverter;

@Configuration
class JmsInfrastructureConfiguration {

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MessageConverter jmsJsonMessageConverter) {
        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(jmsJsonMessageConverter);
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter jmsJsonMessageConverter) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jmsJsonMessageConverter);
        return factory;
    }
}
```

Đây là cấu hình minh họa cho Spring 6.x/7.x dùng `jakarta.jms`. Spring Framework 5.x dùng `javax.jms`, nên import và provider dependency phải cùng namespace. Nếu Spring Boot đã tự cấu hình `JmsTemplate` hoặc listener factory, hãy cấu hình converter trên bean/factory thực sự được dùng thay vì tạo thêm các bean trùng tên.

Gửi DTO:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.incoming", event);
    }
}
```

Nhận DTO:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(OrderCreated event) {
        processOrder(event);
    }
}
```

Phương thức listener khai báo kiểu `OrderCreated`, giúp hợp đồng đầu vào rõ ràng. Converter và listener adapter phải thống nhất cách xác định target type. Nếu nhận nhiều loại event từ cùng destination, hãy kiểm thử type ID mapping và method argument conversion với đúng Spring/provider version.

## 7. Type ID mapping và khả năng tương thích giữa các ứng dụng

Converter có thể ghi một JMS message property mang type ID. Nếu không cấu hình mapping, một số converter có thể dùng tên class Java thô; cách đó làm hợp đồng phụ thuộc package và tên class của producer.

Dùng ID ổn định thay cho class name:

```java
converter.setTypeIdPropertyName("eventType");
converter.setTypeIdMappings(Map.of(
        "order-created-v1", OrderCreated.class,
        "payment-captured-v1", PaymentCaptured.class
));
```

Producer và consumer phải thống nhất các giá trị ID. Khi đổi tên package hoặc refactor class Java, ID bên ngoài vẫn có thể giữ nguyên. Khi thay đổi schema không tương thích, phát một ID/version mới hoặc thiết kế migration rõ ràng.

Không dùng tên class nhận từ message làm cơ sở deserialize tùy ý. Không bật Jackson default typing trên queue có producer không hoàn toàn tin cậy. Chỉ cho phép các loại payload đã biết bằng type ID mapping và giới hạn trusted package theo phiên bản Spring hỗ trợ.

## 8. TextMessage, BytesMessage và encoding

Cả hai converter Jackson JMS nêu trên đều hỗ trợ chuyển đổi JSON qua `TextMessage` hoặc `BytesMessage`: 

| Dạng JMS | Đặc điểm | Khi cân nhắc |
|---|---|---|
| `TextMessage` | Body là chuỗi ký tự; dễ đọc khi quan sát broker và thuận tiện với consumer cần text | Tích hợp với hệ thống xử lý JSON text |
| `BytesMessage` | Body là dãy byte; phù hợp khi muốn biểu diễn payload dưới dạng bytes | Tích hợp có quy ước binary hoặc tối ưu theo transport |

Converter Jackson JMS mặc định tạo `BytesMessage` bằng `MessageType.BYTES`; muốn tạo `TextMessage`, đặt `MessageType.TEXT`. Encoding mặc định cho text là UTF-8. Nếu hai hệ thống dùng cấu hình encoding khác nhau, phải thống nhất encoding và kiểm thử dữ liệu Unicode.

Đừng giả định việc chọn `MessageType.TEXT` sẽ tự đặt HTTP-style `Content-Type` header. JMS có `JMSType`, nhưng trường đó không đồng nghĩa MIME `Content-Type`. Nếu consumer ngoài Java cần biết representation, hãy thống nhất một JMS property riêng, ví dụ `contentType=application/json`.

Có thể gắn property sau khi converter đã tạo message bằng `MessagePostProcessor`: 

```java
jmsTemplate.convertAndSend("orders.incoming", event, message -> {
    message.setStringProperty("contentType", "application/json");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
```

Các property JMS phải dùng kiểu dữ liệu được JMS hỗ trợ. Producer và consumer cần thống nhất tên property, kiểu dữ liệu và ý nghĩa của chúng.

## 9. Schema evolution và validation

Converter chịu trách nhiệm chuyển JSON thành object Java. Nó không tự xác nhận mọi quy tắc nghiệp vụ hoặc bảo đảm producer/consumer đang dùng cùng schema.

Khi thiết kế schema:

- Thêm field mới theo hướng tương thích, có quy tắc default hoặc optional rõ ràng.
- Không đổi kiểu field đang được consumer sử dụng nếu chưa có migration.
- Dùng `schemaVersion` hoặc event type version khi thay đổi cấu trúc không tương thích.
- Giữ tên field và enum ổn định; thống nhất quy tắc xử lý giá trị enum mới.
- Kiểm tra field bắt buộc, range và invariant sau khi deserialize.
- Không serialize trực tiếp entity có quan hệ vòng hoặc field nội bộ không thuộc hợp đồng.

Jackson 2 `MappingJackson2MessageConverter` tùy chỉnh một số mặc định, trong đó `FAIL_ON_UNKNOWN_PROPERTIES` bị tắt. Điều đó có thể giúp consumer cũ bỏ qua field mới, nhưng không thay thế schema validation. Nếu cần strict contract, cấu hình `ObjectMapper` phù hợp và viết test cho payload không hợp lệ. Hành vi của mapper Jackson 3 cần được xác nhận theo mapper/module và cấu hình của phiên bản đang dùng.

## 10. Lỗi chuyển đổi và cách xử lý

Các lỗi thường gặp gồm:

- **Không có converter phù hợp:** ứng dụng dùng `SimpleMessageConverter` nên DTO không được chuyển thành JSON như mong đợi.
- **Sai JMS message type:** consumer nhận `ObjectMessage` hoặc message type khác trong khi converter chỉ hỗ trợ text/bytes.
- **Sai type ID:** property không tồn tại, ID không có trong mapping hoặc hai phía dùng tên ID khác nhau.
- **Sai encoding:** ký tự Unicode bị lỗi khi bytes được đọc bằng encoding khác.
- **JSON không hợp lệ:** payload bị cắt, sai cú pháp hoặc có kiểu dữ liệu không thể deserialize.
- **Schema không tương thích:** JSON hợp lệ nhưng field/enum/structure không phù hợp DTO consumer.
- **Thiếu dependency hoặc lệch version:** converter không có trên classpath, Jackson module không tương thích hoặc `javax.jms` bị trộn với `jakarta.jms`.

Spring biểu diễn lỗi chuyển đổi bằng `MessageConversionException` trong JMS converter. Lỗi có thể xuất hiện trước khi method `@JmsListener` được gọi. Hãy cấu hình error handler, transaction, redelivery và dead-letter policy để poison message không bị retry vô hạn.

## 11. Kiểm thử converter và hợp đồng hai chiều

Một bộ kiểm thử tốt cần xác nhận cả representation trên broker lẫn object sau khi nhận:

1. Gửi DTO và kiểm tra JMS message tạo ra là `TextMessage` hay `BytesMessage` theo cấu hình.
2. Đọc body và xác nhận JSON có field, encoding và schema version đúng.
3. Kiểm tra JMS property chứa type ID và content metadata nếu hợp đồng yêu cầu.
4. Nhận message bằng converter phía consumer và xác nhận DTO có giá trị đúng.
5. Kiểm thử unknown type ID, type ID thiếu, JSON hỏng, field sai kiểu và schema version không hỗ trợ.
6. Kiểm thử tương thích producer/consumer ở các phiên bản ứng dụng khác nhau.
7. Chạy integration test với JMS provider thực tế hoặc test broker tương ứng để kiểm tra mapping property và behavior của listener container.

Unit test converter có thể kiểm tra logic serialize/deserialize; integration test mới chứng minh được provider, message type, property mapping, transaction và listener container phối hợp đúng.

## 12. Lỗi cấu hình thường gặp

- **Dùng `MappingJackson2MessageConverter` trên Spring 7 như lựa chọn mới:** class đã deprecated từ 7.0; ưu tiên `JacksonJsonMessageConverter` khi dùng Jackson 3.
- **Dùng `JacksonJsonMessageConverter` trên Spring 6:** class chưa có ở Spring 6; dùng converter Jackson 2.
- **Nhầm Jackson 2 và Jackson 3 package:** `com.fasterxml.jackson.*` và `tools.jackson.*` không thể thay thế import cho nhau.
- **Quên gắn converter vào cả sender và listener container:** producer gửi JSON nhưng consumer vẫn dùng converter mặc định.
- **Cho rằng converter mặc định tạo TextMessage:** cả converter Jackson JMS nói trên mặc định tạo `BytesMessage`; cần đặt `MessageType.TEXT` nếu muốn text.
- **Không cấu hình type ID cho luồng đa hình:** converter không xác định được class đích khi cần suy ra từ message.
- **Gửi Java class name thay cho type ID ổn định:** producer và consumer bị ghép chặt vào package/class name.
- **Mở rộng trusted packages quá rộng hoặc dùng wildcard:** tăng bề mặt deserialize không cần thiết.
- **Nhầm `JMSType` với `Content-Type`:** nếu cần MIME type, định nghĩa JMS property riêng và tài liệu hóa.
- **Không kiểm tra version thực tế:** dependency management có thể kéo một version khác với version được ghi trực tiếp trong build file.
- **Coi deserialize thành công là validation thành công:** DTO vẫn cần kiểm tra dữ liệu và quy tắc nghiệp vụ.

## 13. Quy trình chọn và triển khai

1. Xác định Spring Framework và Jackson version thực tế từ dependency tree.
2. Chọn `MappingJackson2MessageConverter` cho Spring 5/6 với Jackson 2; chọn `JacksonJsonMessageConverter` cho Spring 7 với Jackson 3.
3. Kiểm tra namespace JMS: `javax.jms` ở Spring 5 và `jakarta.jms` ở Spring 6/7.
4. Định nghĩa DTO và schema JSON độc lập với entity nội bộ.
5. Chọn `TextMessage` hoặc `BytesMessage` theo hợp đồng tích hợp; thống nhất UTF-8.
6. Cấu hình converter, type ID property và mapping ID ổn định; giới hạn trusted packages nếu phiên bản hỗ trợ.
7. Gắn converter vào `JmsTemplate` và listener container đang được ứng dụng sử dụng.
8. Định nghĩa property `contentType`, event type và schema version nếu consumer ngoài Java cần metadata.
9. Kiểm thử round-trip, type ID, schema compatibility, encoding, poison message và dead-letter behavior.
10. Nâng cấp Spring/Jackson theo BOM đồng bộ và kiểm tra deprecation trước mỗi lần nâng phiên bản.

## 14. Kết luận

JSON converter của JMS chuyển DTO Java thành `TextMessage` hoặc `BytesMessage`, rồi chuyển ngược JMS message thành object. Với Spring Framework 5/6 và Jackson 2, dùng `MappingJackson2MessageConverter`; với Spring Framework 7 và Jackson 3, ưu tiên `JacksonJsonMessageConverter`. Cần chọn theo dependency thực tế và namespace JMS của dự án.

Để producer và consumer tương thích lâu dài, hãy dùng DTO/schema ổn định, type ID mapping tường minh, encoding thống nhất, metadata có quy ước và validation sau deserialize. Cấu hình cùng converter cho `JmsTemplate` và listener container, kiểm thử cả hai chiều với broker thực tế, đồng thời xử lý lỗi chuyển đổi qua retry có giới hạn và dead-letter policy.