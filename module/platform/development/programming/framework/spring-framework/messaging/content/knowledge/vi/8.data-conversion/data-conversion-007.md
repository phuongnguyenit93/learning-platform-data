# GenericMessageConverter và chuyển đổi kiểu bằng ConversionService

Trong Spring Messaging, một message có payload và headers. Payload có thể được tạo từ nhiều nguồn với kiểu dữ liệu khác nhau: String, số, byte array hoặc một object Java. Khi consumer cần một kiểu Java cụ thể, Spring có thể chuyển payload từ kiểu nguồn sang kiểu đích trước khi đưa vào logic nghiệp vụ.

GenericMessageConverter là một MessageConverter dùng ConversionService để thực hiện chuyển đổi kiểu payload. Nó phù hợp với các phép chuyển đổi giữa những kiểu Java mà ConversionService hỗ trợ, ví dụ String sang Integer hoặc String sang một kiểu domain do ứng dụng định nghĩa.

Cần phân biệt chuyển đổi kiểu Java với giải mã một định dạng dữ liệu như JSON. GenericMessageConverter không phải JSON serializer/deserializer. Nó không tự phân tích một chuỗi JSON thành object chỉ vì message có header contentType là application/json.

## 1. Ba thành phần cần hiểu

### 1.1. MessageConverter

org.springframework.messaging.converter.MessageConverter là hợp đồng chuyển đổi payload của Spring Message.

Hợp đồng có hai thao tác chính:

- fromMessage(message, targetClass): lấy payload từ message và chuyển thành kiểu targetClass.
- toMessage(payload, headers): tạo Message từ payload và các headers tùy chọn.

Kết quả của fromMessage là một object đã chuyển đổi, không phải một Message mới. Nếu converter không hỗ trợ kiểu hoặc định dạng được yêu cầu, hợp đồng cho phép trả về null để báo rằng converter không xử lý được message đó.

Header contentType có thể mô tả MIME type của nội dung, ví dụ text/plain hoặc application/json. Converter có thể dùng header này để chọn cách diễn giải payload. Tuy nhiên, việc có contentType không tự thực hiện chuyển đổi; converter đang được gọi phải thật sự hỗ trợ MIME type và định dạng tương ứng.

### 1.2. ConversionService

org.springframework.core.convert.ConversionService là API chuyển đổi giữa các kiểu Java. Nó trả lời hai câu hỏi:

- canConvert(sourceType, targetType): có converter phù hợp cho cặp kiểu này không?
- convert(source, targetType): thực hiện chuyển đổi và trả về object thuộc kiểu đích.

ConversionService là facade cho tập hợp các converter đã đăng ký. Nó tách logic chuyển đổi khỏi code gọi, vì vậy nhiều thành phần có thể dùng chung một quy tắc chuyển kiểu.

Ví dụ, một ConversionService có thể biết cách chuyển:

- String thành Integer hoặc Long.
- String thành Boolean, UUID hoặc enum.
- Một kiểu domain thành String.
- Một kiểu nguồn do ứng dụng định nghĩa thành một kiểu đích khác.
- Collection hoặc array sang kiểu collection/array khác khi có converter phù hợp cho phần tử.

ConversionService không tự hiểu mọi định dạng serialization. Nó làm việc trên các object Java đã có trong bộ nhớ.

### 1.3. GenericMessageConverter

org.springframework.messaging.converter.GenericMessageConverter mở rộng SimpleMessageConverter và dùng ConversionService để chuyển payload sang kiểu đích được yêu cầu.

Nó có hai constructor:

~~~java
new GenericMessageConverter()
~~~

Tạo converter với ConversionService mặc định.

~~~java
new GenericMessageConverter(conversionService)
~~~

Tạo converter với một ConversionService do ứng dụng cung cấp. Cách thứ hai phù hợp khi ứng dụng có custom converter hoặc cần thống nhất quy tắc chuyển đổi giữa nhiều thành phần.

GenericMessageConverter chủ yếu bổ sung chuyển đổi cho thao tác fromMessage. Phương thức toMessage được kế thừa từ SimpleMessageConverter và chỉ bọc payload trong một Message; nó không tự serialize object thành JSON hoặc byte array.

## 2. Luồng chuyển đổi payload

Khi một consumer yêu cầu kiểu Java khác với kiểu payload hiện tại, luồng xử lý khái quát như sau:

~~~text
Message<?>
    |
    | lấy payload
    v
Source object
    |
    | GenericMessageConverter.fromMessage(...)
    v
ConversionService
    |
    | tìm converter cho source type -> target type
    v
Converted object
    |
    v
Consumer xử lý nghiệp vụ
~~~

Ví dụ message có payload là chuỗi "42". Consumer cần Integer. GenericMessageConverter lấy String từ payload, sau đó nhờ ConversionService chuyển String thành Integer.

Nếu payload đã tương thích với targetClass, converter có thể trả lại payload mà không cần chuyển đổi. Nếu ConversionService không tìm thấy converter phù hợp, GenericMessageConverter trả về null. Nếu converter có tồn tại nhưng dữ liệu đầu vào không hợp lệ, thao tác convert có thể ném ConversionException; ứng dụng cần xử lý lỗi này theo chính sách của luồng message.

GenericMessageConverter chỉ chuyển payload. Nó không tự đổi tên header, không sửa MessageHeaders và không tự xác nhận message đã được broker giao thành công.

## 3. SimpleMessageConverter và GenericMessageConverter khác nhau thế nào?

SimpleMessageConverter chỉ unwrap payload nếu payload đã thuộc kiểu đích mong muốn; theo chiều ngược lại, nó bọc payload thành Message. Nó không thực hiện chuyển đổi kiểu thực sự và bỏ qua thông tin content type trong headers.

GenericMessageConverter kế thừa hành vi cơ bản đó, đồng thời dùng ConversionService để chuyển payload sang targetClass khi cần.

| Tiêu chí | SimpleMessageConverter | GenericMessageConverter |
|---|---|---|
| Payload đã đúng kiểu đích | Trả payload | Trả payload |
| String sang Integer | Không tự chuyển đổi | Có nếu ConversionService hỗ trợ |
| Kiểu domain có custom Converter | Không tự xử lý | Có nếu converter được đăng ký |
| toMessage | Bọc payload thành Message | Kế thừa thao tác bọc payload |
| JSON text sang POJO | Không | Không tự động |
| Dựa vào ConversionService | Không | Có cho chuyển đổi payload trong fromMessage |

Chọn SimpleMessageConverter khi producer và consumer đã thống nhất kiểu payload. Chọn GenericMessageConverter khi cần coercion hoặc chuyển đổi kiểu Java thông qua ConversionService. Với JSON, XML, Protobuf hoặc một định dạng serialized cụ thể, hãy dùng converter chuyên biệt cho định dạng đó.

## 4. Dùng chuyển đổi có sẵn

DefaultConversionService là implementation có các converter mặc định thường dùng. GenericMessageConverter có thể nhận một DefaultConversionService để chuyển các kiểu cơ bản.

Ví dụ chuyển String thành Integer:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class BasicConversionDemo {

    public static void main(String[] args) {
        GenericMessageConverter converter =
                new GenericMessageConverter(new DefaultConversionService());

        Message<String> message = MessageBuilder
                .withPayload("42")
                .build();

        Integer quantity = (Integer) converter.fromMessage(
                message,
                Integer.class
        );

        System.out.println(quantity);
    }
}
~~~

Kết quả:

~~~text
42
~~~

Đây là ví dụ chuyển đổi payload trong bộ nhớ. Message có payload kiểu String; consumer yêu cầu Integer; GenericMessageConverter dùng ConversionService để trả về Integer.

Nếu payload đã là Integer, không cần converter phải phân tích lại. Nếu payload là chuỗi không biểu diễn được một số nguyên hợp lệ, converter mặc định có thể ném lỗi chuyển đổi. Không nên giả định mọi dữ liệu đầu vào đều hợp lệ chỉ vì canConvert trả về true.

## 5. Đăng ký custom Converter

Khi kiểu nguồn hoặc kiểu đích thuộc domain của ứng dụng, có thể đăng ký Converter<S, T> với ConversionService.

Converter<S, T> mô tả một cặp kiểu nguồn và kiểu đích. Ví dụ, ứng dụng có kiểu OrderCode được biểu diễn bên ngoài bằng chuỗi dạng ORD-42.

~~~java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{1,10}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
~~~

Đăng ký converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        OrderCode.class,
        OrderCode::new
);
~~~

Tạo GenericMessageConverter bằng ConversionService đã cấu hình:

~~~java
GenericMessageConverter converter =
        new GenericMessageConverter(conversionService);
~~~

Giờ đây payload String có thể được chuyển thành OrderCode:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-42")
        .build();

OrderCode orderCode = (OrderCode) converter.fromMessage(
        message,
        OrderCode.class
);

System.out.println(orderCode.value());
~~~

Kết quả:

~~~text
ORD-42
~~~

Converter tùy chỉnh cũng là nơi thích hợp để kiểm tra định dạng, chuẩn hóa dữ liệu hoặc từ chối giá trị không hợp lệ. Không nên đặt logic nghiệp vụ phức tạp hoặc truy cập database trong một Converter đơn giản; chuyển đổi nên tập trung vào việc biểu diễn dữ liệu giữa hai kiểu.

## 6. Ví dụ Java 17+ hoàn chỉnh

Ví dụ dưới đây kết hợp chuyển đổi có sẵn String → Integer và custom conversion String → OrderCode trong một chương trình.

~~~java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageConverterDemo {

    public record OrderCode(String value) {
        public OrderCode {
            if (value == null || !value.matches("ORD-[0-9]{1,10}")) {
                throw new IllegalArgumentException("Invalid order code");
            }
        }
    }

    public static void main(String[] args) {
        DefaultConversionService conversionService =
                new DefaultConversionService();

        conversionService.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::new
        );

        GenericMessageConverter converter =
                new GenericMessageConverter(conversionService);

        Message<String> quantityMessage = MessageBuilder
                .withPayload("42")
                .build();

        Integer quantity = (Integer) converter.fromMessage(
                quantityMessage,
                Integer.class
        );

        Message<String> orderMessage = MessageBuilder
                .withPayload("ORD-42")
                .build();

        OrderCode orderCode = (OrderCode) converter.fromMessage(
                orderMessage,
                OrderCode.class
        );

        System.out.println(quantity);
        System.out.println(orderCode.value());
    }
}
~~~

Có thể biên dịch và chạy khi dependency spring-messaging cùng spring-core đã có trên classpath:

~~~bash
javac -cp "spring-messaging.jar;spring-core.jar;spring-jcl.jar" GenericMessageConverterDemo.java
java -cp ".;spring-messaging.jar;spring-core.jar;spring-jcl.jar" GenericMessageConverterDemo
~~~

Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm thay cho dấu chấm phẩy. Trong dự án Gradle hoặc Maven, nên để build tool quản lý transitive dependency thay vì tự ghép các JAR thủ công.

Stdout:

~~~text
42
ORD-42
~~~

Ví dụ minh họa cách cấu hình một ConversionService rồi dùng lại nó cho nhiều message. Converter được đăng ký một lần lúc khởi tạo và có thể được chia sẻ cho các thành phần xử lý message.

## 7. Tự kiểm tra khả năng chuyển đổi

Có thể dùng ConversionService trực tiếp để kiểm tra cặp kiểu trước khi chuyển đổi:

~~~java
boolean supported = conversionService.canConvert(
        String.class,
        Integer.class
);

Integer value = conversionService.convert("42", Integer.class);
~~~

canConvert chỉ cho biết có đường chuyển đổi được đăng ký cho cặp kiểu. Nó không xác nhận nội dung cụ thể chắc chắn hợp lệ. Ví dụ, String có thể chuyển sang Integer, nhưng chuỗi "forty-two" vẫn gây lỗi khi convert.

Đối với collection, array và map, canConvert có thể trả true dựa trên kiểu container dù một phần tử bên trong không chuyển đổi được. Khi chạy thật, convert vẫn có thể ném ConversionException. Hãy kiểm tra dữ liệu và xử lý ngoại lệ tại ranh giới nhận message.

GenericMessageConverter trả null khi ConversionService không có khả năng chuyển payload sang targetClass. Ứng dụng nên phân biệt rõ ba trường hợp:

1. **Đã chuyển đổi thành công:** nhận được object thuộc kiểu đích.
2. **Không có converter phù hợp:** kết quả là null; converter không nhận xử lý message đó.
3. **Có converter nhưng dữ liệu không hợp lệ:** phép chuyển đổi ném exception; cần xử lý lỗi đầu vào.

Không ép null thành object hoặc âm thầm bỏ qua message. Nếu message bắt buộc phải có kiểu đích, hãy chuyển tình huống không hỗ trợ thành lỗi có ý nghĩa để log, retry hoặc đưa vào quy trình xử lý lỗi phù hợp.

## 8. Đăng ký Converter, ConverterFactory và GenericConverter

Spring cung cấp nhiều abstraction để mở rộng ConversionService.

### 8.1. Converter<S, T>

Dùng khi chỉ cần một cặp kiểu nguồn và đích:

~~~java
Converter<String, OrderCode>
~~~

Đây là lựa chọn đơn giản nhất cho các chuyển đổi như String sang OrderCode hoặc Integer sang một kiểu domain khác.

### 8.2. ConverterFactory<S, R>

Dùng khi một kiểu nguồn có thể chuyển sang nhiều kiểu đích cùng một họ. Ví dụ, một factory có thể nhận String và chuyển thành nhiều kiểu enum. ConverterFactory trả về converter cụ thể cho target type được yêu cầu.

### 8.3. GenericConverter

Dùng khi một converter cần hỗ trợ nhiều cặp kiểu hoặc cần đọc metadata kiểu thông qua TypeDescriptor. GenericConverter cung cấp tập ConvertiblePair và phương thức convert nhận sourceType, targetType.

TypeDescriptor có thể mang thông tin về kiểu generic của collection, array, map hoặc annotation trên field/method. Điều này hữu ích khi việc chuyển đổi phụ thuộc vào kiểu phần tử hoặc metadata của vị trí đích.

Đăng ký các loại converter thông qua ConverterRegistry hoặc một implementation như DefaultConversionService. Cần cấu hình xong registry trước khi đưa ConversionService vào sử dụng chung.

## 9. ConversionService và kiểu generic

GenericMessageConverter.fromMessage nhận targetClass kiểu Class<?>. Vì vậy, method này thể hiện được kiểu đích ở mức class, nhưng không thể truyền đầy đủ tham số generic như List<OrderCode> qua một Class thông thường do type erasure của Java.

Nếu cần chuyển đổi collection với kiểu phần tử cụ thể, dùng TypeDescriptor của ConversionService trực tiếp hoặc xây dựng converter chuyên biệt có đủ thông tin kiểu.

Ví dụ khai báo TypeDescriptor cho danh sách Integer:

~~~java
TypeDescriptor sourceType = TypeDescriptor.forObject(
        List.of("10", "20")
);

TypeDescriptor targetType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class)
);

Object converted = conversionService.convert(
        List.of("10", "20"),
        sourceType,
        targetType
);
~~~

Khi dùng TypeDescriptor, ConversionService có thể áp dụng chuyển đổi cho từng phần tử của collection nếu các converter cần thiết đã đăng ký. Đây là API chuyển đổi kiểu Java trực tiếp; GenericMessageConverter không tự suy ra mọi generic type của một method parameter từ targetClass.

## 10. Phân biệt chuyển đổi kiểu với giải mã JSON

Đây là điểm dễ gây nhầm lẫn nhất khi sử dụng GenericMessageConverter.

Giả sử message có payload là chuỗi:

~~~json
{"orderId":"ORD-42","quantity":2}
~~~

Consumer yêu cầu OrderEvent.class. GenericMessageConverter không tự phân tích chuỗi JSON thành OrderEvent. ConversionService mặc định không phải JSON parser.

Các trường hợp nên phân biệt:

| Payload đầu vào | Kiểu đích | Công cụ phù hợp |
|---|---|---|
| String "42" | Integer | GenericMessageConverter + ConversionService |
| String "true" | Boolean | GenericMessageConverter + ConversionService |
| String "ORD-42" | OrderCode | GenericMessageConverter + custom Converter |
| JSON text | OrderEvent | JSON converter, ví dụ MappingJackson2MessageConverter khi cấu hình Jackson phù hợp |
| byte[] chứa JSON | OrderEvent | JSON converter có hỗ trợ byte/string và content type tương ứng |
| XML | Domain object | XML/marshalling converter phù hợp |

MessageHeaders.CONTENT_TYPE có thể giúp converter chuyên biệt xác định MIME type. Nhưng GenericMessageConverter chỉ thực hiện type conversion qua ConversionService; nó không biến JSON text thành object chỉ nhờ header application/json.

Nếu cần serialize object thành JSON khi gửi message, hãy chọn converter có khả năng serialize JSON. Nếu cần deserialize JSON khi nhận, hãy chọn converter hỗ trợ JSON và target type. Không dùng GenericMessageConverter thay cho Jackson, JAXB hoặc một serializer chuyên biệt.

## 11. Phân biệt MessageConverter của Spring Messaging và JMS

Có hai interface cùng tên MessageConverter trong các package khác nhau:

- org.springframework.messaging.converter.MessageConverter: chuyển payload giữa Spring Message và object Java.
- org.springframework.jms.support.converter.MessageConverter: chuyển giữa object Java và jakarta.jms.Message.

Chúng không phải cùng một interface và không thể thay thế trực tiếp cho nhau.

GenericMessageConverter thuộc Spring Messaging. Nó sử dụng org.springframework.core.convert.ConversionService để chuyển payload trong Spring Message.

JMS converter làm việc với các loại JMS message như TextMessage, BytesMessage hoặc MapMessage. JmsTemplate sử dụng converter của spring-jms; ứng dụng có thể cấu hình converter JMS phù hợp cho payload cần gửi/nhận qua broker.

JmsMessagingTemplate là cầu nối giữa Spring Messaging abstraction và JMS. Sự tồn tại của nó không có nghĩa GenericMessageConverter tự động trở thành JMS MessageConverter. Khi một luồng đi qua JMS, hãy xác định converter ở từng tầng và kiểm thử mapping thực tế.

## 12. Đăng ký và quản lý ConversionService trong ứng dụng Spring

Trong ứng dụng Spring, ConversionService thường được tạo lúc khởi động, cấu hình các converter cần thiết rồi chia sẻ cho nhiều bean. Các implementation chuẩn như DefaultConversionService được thiết kế để dùng chung sau khi cấu hình.

Ví dụ khai báo bean:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public DefaultConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::new
        );

        return service;
    }

    @Bean
    public GenericMessageConverter genericMessageConverter(
            ConversionService conversionService) {

        return new GenericMessageConverter(conversionService);
    }
}
~~~

Trong cấu hình thực tế, tránh đăng ký nhiều bean cùng tên conversionService hoặc tạo nhiều bộ converter có quy tắc mâu thuẫn. Hãy xác định rõ ConversionService nào được dùng bởi messaging converter và thành phần framework khác.

Các custom Converter nên stateless và thread-safe. Không lưu trạng thái request, principal hoặc dữ liệu mutable của message trong converter dùng chung. Nếu cần thông tin theo request, truyền thông tin đó qua service xử lý hoặc context thích hợp, không nhét vào một singleton converter.

## 13. Lỗi thường gặp và cách xử lý

### 13.1. fromMessage trả về null

Nguyên nhân thường là ConversionService không có converter cho source type và targetClass. Kiểm tra cặp kiểu bằng canConvert và đăng ký converter phù hợp nếu đó là kiểu domain riêng.

### 13.2. ConversionException hoặc ConversionFailedException

Có thể converter đã được tìm thấy nhưng dữ liệu không hợp lệ, ví dụ chuỗi không phải số nguyên hoặc mã đơn hàng sai định dạng. Xác thực đầu vào, bổ sung thông báo lỗi rõ ràng và quyết định message có được retry hay cần chuyển sang error flow.

### 13.3. Mong đợi JSON tự chuyển thành object

GenericMessageConverter không phải JSON mapper. Dùng converter chuyên biệt và kiểm tra content type, Jackson dependency cùng cấu hình converter.

### 13.4. Chuyển đổi thành công trong unit test nhưng lỗi ở môi trường tích hợp

Có thể ConversionService dùng trong test khác với bean được ứng dụng thực tế inject. Kiểm tra constructor của GenericMessageConverter và bean ConversionService được cấu hình ở ApplicationContext.

### 13.5. Custom converter không được sử dụng

Kiểm tra converter đã được đăng ký trước khi chuyển đổi, source/target type có đúng như mong đợi và có một ConversionService khác được inject vào GenericMessageConverter hay không.

### 13.6. Nhầm converter của JMS với converter của Spring Messaging

Kiểm tra package import và nơi converter được cấu hình. JmsTemplate nhận converter thuộc spring-jms; GenericMessageConverter thuộc spring-messaging.

### 13.7. Collection có phần tử sai kiểu

canConvert ở mức collection có thể trả true nhưng convert vẫn thất bại ở một phần tử. Dùng TypeDescriptor khi cần thông tin kiểu generic và kiểm tra dữ liệu thực tế.

## 14. Checklist khi triển khai GenericMessageConverter

1. Xác định kiểu payload thực tế của message.
2. Xác định targetClass mà consumer cần.
3. Kiểm tra cặp kiểu bằng ConversionService.canConvert.
4. Dùng converter mặc định nếu phép chuyển đổi đã được hỗ trợ.
5. Đăng ký custom Converter nếu kiểu domain chưa có quy tắc chuyển đổi.
6. Dùng TypeDescriptor khi cần xử lý collection/map với generic element type.
7. Kiểm tra trường hợp trả null và exception.
8. Dùng JSON/XML converter riêng cho serialized format.
9. Xác nhận đúng ConversionService được inject vào GenericMessageConverter.
10. Phân biệt interface MessageConverter của Spring Messaging và spring-jms.
11. Cấu hình converter trước khi chia sẻ ConversionService cho nhiều thread.
12. Viết test cho cả dữ liệu hợp lệ, dữ liệu sai và kiểu không được hỗ trợ.

## 15. Tài liệu tham khảo

- [GenericMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html)
- [SimpleMessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/SimpleMessageConverter.html)
- [MessageConverter — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [ConversionService — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [DefaultConversionService — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring JMS — Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms.html)

GenericMessageConverter giải quyết việc chuyển payload giữa các kiểu Java thông qua ConversionService. Khi cần xử lý JSON, XML hoặc một protocol serialization cụ thể, hãy chọn converter đúng với định dạng đó và giữ ranh giới rõ ràng giữa type conversion, serialization và transport.