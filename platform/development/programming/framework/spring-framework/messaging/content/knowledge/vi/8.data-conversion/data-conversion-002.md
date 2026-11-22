# Phân biệt MessageConverter với ConversionService trong Spring

## 1. Hai abstraction giải quyết hai bài toán khác nhau

Spring có nhiều cơ chế chuyển đổi dữ liệu. Hai abstraction dễ bị nhầm là `MessageConverter` trong Spring Messaging và `ConversionService` trong Spring Core.

Chúng đều có thể chuyển một giá trị từ dạng này sang dạng khác, nhưng phạm vi trách nhiệm khác nhau:

- **MessageConverter** làm việc ở ranh giới messaging. Nó chuyển một object thành `Message<?>` hoặc lấy payload từ message và chuyển thành kiểu Java mà bên nhận yêu cầu. Message có thể mang headers như Content-Type, destination và correlation ID.
- **ConversionService** chuyển đổi giữa các kiểu Java. Nó nhận source object và target type, sau đó tìm converter phù hợp. Nó không tạo message, không quản lý headers và không quyết định cách biểu diễn payload trên giao thức.

Có thể nhớ ngắn gọn: **MessageConverter chuyển đổi qua ranh giới message; ConversionService chuyển đổi giữa các kiểu dữ liệu Java.**

Sau bài học, bạn cần có thể:

- Mô tả đúng trách nhiệm và API của hai abstraction.
- Phân biệt chuyển đổi payload với chuyển đổi object-to-object.
- Chọn converter theo Content-Type, payload và target type.
- Đăng ký converter cho ConversionService mà không nhầm với danh sách MessageConverter.
- Hiểu cách một MessageConverter có thể sử dụng ConversionService bên trong.
- Thiết kế luồng chuyển đổi dễ kiểm thử và không trộn serialization với quy tắc nghiệp vụ.

## 2. MessageConverter: chuyển đổi ở ranh giới messaging

### 2.1 Hợp đồng API

Interface `org.springframework.messaging.converter.MessageConverter` có hai phương thức cốt lõi:

~~~java
Message<?> toMessage(Object payload, MessageHeaders headers);

<T> T fromMessage(Message<?> message, Class<T> targetClass);
~~~

- `toMessage` tạo một message từ payload và headers. Converter có thể bổ sung metadata cần thiết cho biểu diễn message.
- `fromMessage` đọc message và chuyển payload thành target class được yêu cầu.
- Nếu converter không hỗ trợ trường hợp chuyển đổi, nó có thể trả về `null` để báo rằng không thể xử lý message đó.

Điểm quan trọng là MessageConverter làm việc với **toàn bộ ngữ cảnh của message**. Ngoài kiểu payload, converter có thể xem Content-Type để xác định cách serialize hoặc deserialize dữ liệu.

Ví dụ, một ứng dụng gửi DTO qua broker có thể serialize object thành JSON, đặt Content-Type là `application/json` rồi gửi message. Ở phía nhận, converter đọc Content-Type và chuyển payload thành DTO tương ứng.

### 2.2 Những converter thường gặp

| Converter | Phạm vi sử dụng |
|---|---|
| `StringMessageConverter` | Chuyển đổi payload văn bản kiểu String |
| `ByteArrayMessageConverter` | Giữ hoặc tạo payload byte[] |
| `MappingJackson2MessageConverter` | Chuyển đổi object và JSON bằng Jackson trong các phiên bản hỗ trợ |
| `MarshallingMessageConverter` | Chuyển đổi qua Spring OXM marshaller/unmarshaller |
| `GenericMessageConverter` | Dùng ConversionService để chuyển payload giữa các kiểu Java |

Converter cụ thể hỗ trợ MIME type nào phụ thuộc implementation và cấu hình. Ví dụ, StringMessageConverter mặc định phù hợp với text/plain; ByteArrayMessageConverter phù hợp với application/octet-stream. Converter JSON xử lý nội dung JSON theo cấu hình mapper và supported MIME types.

Không phải mọi MessageConverter đều serialize mọi object. Hãy kiểm tra kiểu payload, Content-Type và danh sách converter đã đăng ký ở endpoint hoặc template thực tế.

### 2.3 Ví dụ: chuyển đổi message văn bản

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class MessageConverterDemo {

    public static void main(String[] args) {
        StringMessageConverter converter = new StringMessageConverter();

        Message<String> incoming = MessageBuilder
                .withPayload("order.created")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN)
                .build();

        String payload = converter.fromMessage(incoming, String.class);

        Message<?> outgoing = converter.toMessage(
                payload,
                incoming.getHeaders());

        System.out.println(payload);
        System.out.println(outgoing.getHeaders()
                .get(MessageHeaders.CONTENT_TYPE));
    }
}
~~~

Kết quả:

~~~text
order.created
text/plain
~~~

Ví dụ minh họa cả hai chiều: đọc payload từ message thành String, sau đó tạo message mới từ String và headers. Converter làm việc trong ngữ cảnh messaging và giữ thông tin Content-Type phù hợp.

## 3. ConversionService: chuyển đổi giữa các kiểu Java

### 3.1 Hợp đồng API

`org.springframework.core.convert.ConversionService` cung cấp API tổng quát để kiểm tra và thực hiện chuyển đổi object:

~~~java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);
~~~

Ngoài overload nhận Class, API còn hỗ trợ `TypeDescriptor` để mô tả kiểu chi tiết hơn, hữu ích với generic type, collection và metadata của property.

ConversionService không biết message đến từ channel nào, không đọc destination và không tạo headers. Nó chỉ quan tâm source type và target type.

Các thành phần chính:

- **ConversionService:** interface dùng để kiểm tra và thực hiện chuyển đổi.
- **Converter<S, T>:** converter đơn giản từ kiểu S sang kiểu T.
- **ConverterFactory<S, R>:** tạo converter cho một họ target type có chung kiểu gốc.
- **GenericConverter:** hỗ trợ nhiều cặp source/target type và TypeDescriptor.
- **ConfigurableConversionService:** cho phép đăng ký converter.
- **DefaultConversionService:** implementation có sẵn nhiều converter phổ biến và cho phép bổ sung converter.

ConversionService được dùng trong nhiều phần của Spring như binding, cấu hình, biểu thức và chuyển đổi dữ liệu trong ứng dụng. Phạm vi dùng thực tế phụ thuộc bean hoặc instance được cấu hình cho thành phần đó.

### 3.2 Ví dụ: chuyển String thành kiểu domain

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

public class ConversionServiceDemo {

    record OrderId(String value) {
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                OrderId.class,
                OrderId::new);

        boolean supported = conversionService.canConvert(
                String.class,
                OrderId.class);

        OrderId orderId = conversionService.convert(
                "ORD-42",
                OrderId.class);

        System.out.println(supported);
        System.out.println(orderId.value());
    }
}
~~~

Kết quả:

~~~text
true
ORD-42
~~~

Ở đây không có message, channel hoặc headers. ConversionService chỉ chuyển chuỗi `ORD-42` thành object `OrderId`. Đây là chuyển đổi kiểu Java thuần túy.

### 3.3 Đăng ký converter

Một converter riêng có thể được khai báo bằng interface `Converter<S, T>`:

~~~java
import org.springframework.core.convert.converter.Converter;

public class StringToOrderIdConverter
        implements Converter<String, OrderId> {

    @Override
    public OrderId convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }

        return new OrderId(source.trim());
    }
}
~~~

Sau đó đăng ký converter với ConversionService có thể cấu hình:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToOrderIdConverter());
~~~

Trong ứng dụng Spring, có thể khai báo và inject một ConversionService phù hợp với phạm vi cần dùng. Không nên tạo một instance riêng ở mọi method nếu ứng dụng cần dùng chung một tập quy tắc chuyển đổi đã được quản lý.

## 4. So sánh trực tiếp

| Tiêu chí | MessageConverter | ConversionService |
|---|---|---|
| Package | `org.springframework.messaging.converter` | `org.springframework.core.convert` |
| Đầu vào | Payload và/hoặc Message | Object Java |
| Đầu ra | Message hoặc payload theo target type | Object thuộc target type |
| Headers | Có thể đọc hoặc tạo headers | Không quản lý headers |
| Content-Type / MIME | Có ý nghĩa trong lựa chọn và biểu diễn message | Không phải khái niệm cốt lõi |
| Serialization | Có thể serialize/deserialize payload | Không tự định nghĩa wire format |
| Ví dụ | DTO ↔ JSON Message | String → OrderId |
| Bối cảnh | Messaging, channel, adapter, template | Binding, type conversion, ứng dụng Spring |

Ví dụ cùng một chuỗi `"42"`:

- ConversionService có thể chuyển String thành Integer nếu converter phù hợp được đăng ký.
- MessageConverter có thể đọc payload từ một Message có Content-Type phù hợp và trả về String hoặc object theo khả năng của converter.
- MessageConverter JSON có thể deserialize JSON thành DTO; ConversionService mặc định không phải JSON parser.

Không nên dùng hai abstraction thay thế nhau chỉ vì cả hai đều có chữ “converter”.

## 5. Chúng có thể kết hợp với nhau như thế nào?

Một số MessageConverter sử dụng ConversionService để thực hiện bước chuyển đổi payload. `GenericMessageConverter` là ví dụ rõ ràng: nó dựa vào ConversionService để chuyển payload từ kiểu hiện tại sang target class.

Luồng kết hợp:

~~~text
Message<?> từ channel
        |
        v
MessageConverter.fromMessage(...)
        |
        | đọc payload + headers
        v
GenericMessageConverter
        |
        v
ConversionService.convert(source, targetType)
        |
        v
Object Java theo target type
~~~

Trong trường hợp này:

1. MessageConverter nhận message và xác định payload cần chuyển đổi.
2. GenericMessageConverter gọi ConversionService với source object và target type.
3. ConversionService tìm Converter phù hợp.
4. Object đã chuyển đổi được trả về như kết quả của fromMessage.

Điều này không có nghĩa mọi MessageConverter đều dùng ConversionService. Converter JSON thường dựa vào ObjectMapper hoặc serializer riêng. Converter văn bản có logic charset riêng. Mỗi implementation có cơ chế nội bộ khác nhau.

### 5.1 Ví dụ: GenericMessageConverter dùng ConversionService

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageConversionDemo {

    record OrderId(String value) {
    }

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(String.class, OrderId.class, OrderId::new);

        GenericMessageConverter converter =
                new GenericMessageConverter(service);

        Message<String> message = MessageBuilder
                .withPayload("ORD-99")
                .build();

        OrderId orderId = converter.fromMessage(
                message,
                OrderId.class);

        System.out.println(orderId.value());
    }
}
~~~

Kết quả:

~~~text
ORD-99
~~~

Ví dụ cho thấy hai lớp phối hợp: GenericMessageConverter xử lý ngữ cảnh Message, còn ConversionService thực hiện chuyển đổi String thành OrderId.

## 6. Khi nào chọn abstraction nào?

### 6.1 Dùng MessageConverter khi

- Đọc message từ channel hoặc adapter thành payload Java.
- Gửi object thành message qua template hoặc adapter.
- Cần serialize DTO thành JSON, XML hoặc biểu diễn khác.
- Cần xét Content-Type, MIME type hoặc charset.
- Cần giữ hoặc thiết lập metadata phù hợp với giao thức.

### 6.2 Dùng ConversionService khi

- Chuyển String thành enum, số, ngày tháng hoặc kiểu domain.
- Chuyển đổi giá trị property trong binding.
- Chuyển kiểu argument hoặc dữ liệu giữa các lớp Java.
- Tái sử dụng quy tắc chuyển đổi kiểu trong nhiều thành phần Spring.
- Muốn đăng ký Converter, ConverterFactory hoặc GenericConverter.

### 6.3 Khi cần cả hai

Một ứng dụng có thể cần cả hai trong cùng một luồng:

1. Adapter nhận message JSON.
2. MessageConverter deserialize JSON thành DTO.
3. Service kiểm tra hợp đồng và quy tắc nghiệp vụ.
4. ConversionService chuyển một field String thành kiểu domain chuyên biệt nếu cần.
5. Service thực hiện nghiệp vụ.
6. MessageConverter serialize kết quả thành message outbound.

Không nên đưa logic nghiệp vụ vào converter. Converter nên tập trung vào biểu diễn và chuyển đổi dữ liệu. Việc một mã đơn hàng có hợp lệ trong hệ thống hay người dùng có quyền thao tác với đơn hàng là trách nhiệm của validation và service nghiệp vụ.

## 7. Cấu hình trong Spring và Spring Boot

### 7.1 Đăng ký ConversionService

Trong ứng dụng Spring, có thể khai báo một bean ConversionService hoặc sử dụng implementation được framework cung cấp. Cấu hình thực tế phụ thuộc thành phần tiêu thụ: Spring MVC, data binding, configuration properties hoặc messaging adapter có thể có registry và lifecycle riêng.

Ví dụ khai báo bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration
public class ConversionConfiguration {

    @Bean
    public DefaultConversionService applicationConversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                OrderId.class,
                OrderId::new);

        return service;
    }
}
~~~

Bean trên chỉ được các thành phần sử dụng bean đó hoặc được cấu hình để nhận nó dùng. Không giả định mọi converter registry trong ứng dụng tự động dùng chung một instance.

### 7.2 Đăng ký MessageConverter

Danh sách MessageConverter được cấu hình theo thành phần messaging đang dùng. Ví dụ, Spring WebSocket/STOMP có cơ chế cấu hình message converters riêng; các template hoặc adapter khác cũng có thể nhận danh sách converter riêng.

Khi cấu hình, cần xác định:

- Converter nào hỗ trợ payload và MIME type của luồng.
- Converter nào được thử trước nếu có nhiều converter tương thích.
- ObjectMapper hoặc serializer nào được dùng cho JSON.
- Content-Type được tạo và truyền qua adapter như thế nào.
- Converter có được cấu hình cho inbound, outbound hay cả hai.

Đăng ký ConversionService không tự động có nghĩa là đã đăng ký MessageConverter cho STOMP, JMS, AMQP hoặc Kafka. Tương tự, thêm MessageConverter vào một adapter không làm thay đổi ConversionService được dùng trong binding của ứng dụng.

## 8. Xử lý lỗi và kiểm tra khả năng chuyển đổi

### 8.1 Với MessageConverter

Nếu converter không hỗ trợ payload, Content-Type hoặc target class, kết quả có thể là `null`. Tùy thành phần gọi, việc không tìm được converter có thể dẫn tới lỗi chuyển đổi hoặc lỗi xử lý message.

Cần kiểm tra:

- Payload thực tế có đúng kiểu dự kiến không?
- Content-Type có tương thích với converter không?
- Target class có đúng với hợp đồng message không?
- Converter có được đăng ký tại đúng adapter/template không?
- Serializer có xử lý schema/version hiện tại không?

### 8.2 Với ConversionService

Dùng `canConvert` trước nếu ứng dụng cần kiểm tra khả năng chuyển đổi:

~~~java
if (!conversionService.canConvert(String.class, OrderId.class)) {
    throw new IllegalStateException("No converter for OrderId");
}
~~~

Nếu không có converter phù hợp, `convert` có thể ném `ConversionFailedException` hoặc exception thuộc nhóm ConversionException. Nếu converter tự kiểm tra dữ liệu và ném exception, hãy phân biệt lỗi dữ liệu đầu vào với lỗi thiếu converter.

Không bắt mọi exception rồi trả về null vì điều đó có thể che giấu lỗi cấu hình hoặc dữ liệu sai.

## 9. Kiểm thử hai abstraction riêng biệt

### 9.1 Test ConversionService

Kiểm tra source type, target type, giá trị chuyển đổi và dữ liệu không hợp lệ. Ví dụ, String rỗng không nên trở thành OrderId hợp lệ nếu domain không cho phép.

### 9.2 Test MessageConverter

Kiểm tra:

- Payload và Content-Type sau toMessage.
- Target type sau fromMessage.
- Charset với dữ liệu Unicode.
- MIME type không được hỗ trợ.
- JSON schema không tương thích.
- Converter trả null hoặc phát sinh lỗi theo hợp đồng.

### 9.3 Test tích hợp

Khi MessageConverter dùng ConversionService, test cả hai tầng:

1. ConversionService có converter cho source/target type cần thiết.
2. MessageConverter thực sự gọi được cơ chế chuyển đổi đó trong luồng message.
3. Adapter hoặc template đã đăng ký đúng converter.
4. Headers và Content-Type được giữ hoặc ánh xạ đúng.

Unit test cho ConversionService không chứng minh broker adapter đã cấu hình MessageConverter. Integration test với endpoint thực tế mới xác minh được wiring của messaging.

## 10. Các lỗi thường gặp

- **Coi MessageConverter và ConversionService là một:** một bên xử lý Message và payload, bên kia xử lý chuyển đổi kiểu Java.
- **Nghĩ ConversionService tự parse JSON:** cần serializer/deserializer JSON riêng.
- **Nghĩ MessageConverter chỉ chuyển object Java:** nó còn làm việc với headers, Content-Type và message envelope.
- **Đăng ký ConversionService nhưng quên MessageConverter:** adapter có thể vẫn không biết cách serialize payload.
- **Đăng ký MessageConverter ở sai adapter:** mỗi endpoint hoặc template có thể có converter registry riêng.
- **Bỏ qua Content-Type:** converter không được chọn hoặc giải mã sai định dạng.
- **Đưa quy tắc nghiệp vụ vào converter:** khiến chuyển đổi dữ liệu phụ thuộc trạng thái domain và khó tái sử dụng.
- **Không kiểm tra null hoặc exception:** lỗi chuyển đổi bị che giấu và khó truy vết.
- **Cho rằng một bean ConversionService tự động dùng ở mọi nơi:** từng framework component có thể dùng registry riêng.
- **Không test converter ordering:** converter tổng quát có thể nhận dữ liệu trước converter chuyên biệt.

## 11. Checklist lựa chọn

Trước khi triển khai chuyển đổi, hãy trả lời:

- Đầu vào là một Message hay một object Java thuần?
- Có cần đọc hoặc tạo headers và Content-Type không?
- Có cần serialize/deserialize JSON, XML hoặc binary không?
- Chỉ cần chuyển đổi source type sang target type hay cần xử lý message envelope?
- Converter đã được đăng ký tại đúng adapter/template chưa?
- ConversionService có hỗ trợ source/target type chưa?
- Có nhiều converter phù hợp và thứ tự lựa chọn đã rõ chưa?
- Dữ liệu lỗi, MIME mismatch và target type không hỗ trợ được xử lý thế nào?
- Có test riêng cho từng abstraction và integration test cho luồng kết hợp không?

Khi tách đúng hai trách nhiệm, MessageConverter đảm nhiệm cách dữ liệu đi qua ranh giới messaging, còn ConversionService cung cấp quy tắc chuyển đổi giữa các kiểu Java. Hai abstraction có thể phối hợp trong cùng luồng nhưng vẫn giữ được phạm vi rõ ràng, giúp hệ thống dễ mở rộng, kiểm thử và bảo trì.