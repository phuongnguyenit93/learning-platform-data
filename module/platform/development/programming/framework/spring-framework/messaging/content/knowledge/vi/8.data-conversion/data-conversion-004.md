# CompositeMessageConverter và thứ tự lựa chọn bộ chuyển đổi

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của `MessageConverter`, `SmartMessageConverter` và `CompositeMessageConverter`.
- Mô tả cách composite thử từng converter và dừng ở kết quả khác `null` đầu tiên.
- Phân biệt thứ tự do ứng dụng truyền vào `CompositeMessageConverter` với thứ tự mặc định của Spring Integration `ConfigurableCompositeMessageConverter`.
- Hiểu cách `MessageHeaders.CONTENT_TYPE`, payload type và target type ảnh hưởng đến lựa chọn converter.
- Chọn vị trí phù hợp cho converter tùy chỉnh và tránh converter quá rộng che mất converter chuyên biệt.
- Viết ví dụ Java 17 kiểm tra cả chiều deserialize và serialize.

## 1. MessageConverter giải quyết vấn đề gì?

Một Spring `Message<T>` gồm payload và headers. Khi message đi qua một endpoint hoặc transport, kiểu dữ liệu thực tế của payload có thể khác kiểu mà handler mong đợi.

Ví dụ:

- Producer nhận một JSON document từ hệ thống ngoài dưới dạng `byte[]`.
- Handler nghiệp vụ cần một đối tượng Java `Order`.
- Khi gửi ra ngoài, đối tượng `Order` cần được chuyển thành JSON bytes.
- Một message văn bản có thể cần chuyển từ `String` sang `Integer` cho tham số của handler.

`MessageConverter` là abstraction để chuyển payload giữa dạng đã serialize và kiểu Java đích. Nó làm việc với message và có thể dùng header `MessageHeaders.CONTENT_TYPE` để biết MIME type của dữ liệu.

Hai chiều chuyển đổi:

~~~text
Inbound:
Message<byte[]> + Content-Type: application/json
              |
              v
       MessageConverter
              |
              v
           Order

Outbound:
          Order
              |
              v
       MessageConverter
              |
              v
Message<byte[]> + Content-Type: application/json
~~~

Cần phân biệt `MessageConverter` với `org.springframework.core.convert.converter.Converter`:

- `MessageConverter` chuyển payload trong ngữ cảnh message, thường dựa vào MIME type và kiểu đích.
- `Converter<S, T>` và `ConversionService` chuyển đổi giữa các kiểu Java, ví dụ `String` sang `Integer`.
- `GenericMessageConverter` kết nối hai cơ chế bằng cách dùng `ConversionService` để chuyển payload khi có thể.

## 2. CompositeMessageConverter hoạt động như thế nào?

`org.springframework.messaging.converter.CompositeMessageConverter` là một `MessageConverter` bao bọc một collection các converter khác. Nó thử từng converter theo thứ tự trong collection cho đến khi một converter trả về kết quả khác `null`.

Cơ chế này áp dụng cho cả:

- `fromMessage(message, targetClass)`: chuyển payload của message sang kiểu Java đích.
- `toMessage(payload, headers)`: chuyển object thành payload đã serialize và tạo message mới.

Có thể hình dung thuật toán:

~~~text
Bắt đầu
  |
  v
Converter thứ 1
  |
  +-- trả về kết quả khác null --> Dừng, dùng kết quả
  |
  +-- trả về null
          |
          v
     Converter thứ 2
          |
          +-- trả về kết quả khác null --> Dừng, dùng kết quả
          |
          +-- trả về null
                  |
                  v
             Converter tiếp theo
                  |
                  v
        Hết danh sách mà vẫn null
                  |
                  v
          Composite trả về null
~~~

Điều quan trọng là **first non-null wins**:

1. Composite không chạy tất cả converter rồi chọn kết quả tốt nhất.
2. Composite không tự sắp xếp theo MIME type hoặc mức độ chuyên biệt.
3. Converter nào đứng trước và xử lý được message sẽ kết thúc lượt chọn.
4. Converter không hỗ trợ MIME type, payload hoặc target type nên trả về `null`.
5. Nếu không converter nào xử lý được, composite trả về `null`; endpoint gọi nó có thể chuyển tình huống đó thành lỗi chuyển đổi.
6. Nếu converter đã nhận xử lý nhưng dữ liệu không hợp lệ, converter có thể ném `MessageConversionException`. Không nên dùng exception như tín hiệu để thử converter tiếp theo.

Do đó, thứ tự collection là một phần của cấu hình hành vi, không phải chi tiết trình bày.

### CompositeMessageConverter không tự có danh sách converter mặc định

Constructor của Spring Framework nhận collection do ứng dụng cung cấp:

~~~java
List<MessageConverter> converters = List.of(
        jsonConverter,
        byteArrayConverter,
        stringConverter
);

CompositeMessageConverter composite =
        new CompositeMessageConverter(converters);
~~~

Thứ tự trong list trên là thứ tự composite sẽ thử. Nếu muốn thứ tự xác định, dùng một `List` có thứ tự như `List.of(...)` hoặc `ArrayList`; tránh dựa vào thứ tự không xác định của một collection như `HashSet`.

`CompositeMessageConverter` cũng triển khai `SmartMessageConverter`. Khi caller truyền conversion hint, composite chuyển hint đó tới các delegate cũng triển khai `SmartMessageConverter`. Hint có thể mang ngữ cảnh như `MethodParameter` hoặc metadata của tham số/phương thức.

## 3. Những yếu tố quyết định converter có xử lý được message

Một converter thường xét nhiều yếu tố cùng lúc:

| Yếu tố | Ý nghĩa |
|---|---|
| Payload type | Kiểu object hiện tại, ví dụ `byte[]`, `String` hoặc `Order` |
| Target type | Kiểu Java mà `fromMessage` cần tạo |
| Content type | MIME type trong header `MessageHeaders.CONTENT_TYPE`, ví dụ `application/json` |
| Hướng chuyển đổi | Đọc serialized payload vào object hay serialize object ra message |
| Conversion hint | Ngữ cảnh bổ sung dành cho `SmartMessageConverter` |

Với inbound conversion, header `contentType` cho biết MIME type của payload. Với outbound conversion, đối số `headers` của `toMessage` có thể chứa MIME type mong muốn.

Ví dụ:

~~~java
Message<byte[]> message = MessageBuilder
        .withPayload(jsonBytes)
        .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        )
        .build();

Order order = (Order) converter.fromMessage(message, Order.class);
~~~

Nếu payload là JSON nhưng header lại khai báo `text/plain`, converter JSON có thể từ chối xử lý và trả về `null`. Khi đó một converter văn bản hoặc converter khác ở phía sau có thể được thử. Việc đặt đúng content type là trách nhiệm của producer hoặc adapter tạo message.

Không nên chỉ nhìn payload để đoán định dạng. Một chuỗi có thể là văn bản thuần, JSON, XML hoặc nội dung của một giao thức riêng. Content type giúp consumer diễn giải payload theo contract đã thống nhất.

## 4. Thứ tự mặc định của Spring Integration

Cần phân biệt class trong Spring Framework với extension của Spring Integration:

- `CompositeMessageConverter` thuộc module Spring Messaging của Spring Framework. Nó dùng đúng collection được truyền vào constructor.
- `ConfigurableCompositeMessageConverter` thuộc Spring Integration và mở rộng `CompositeMessageConverter`. Nó cung cấp một danh sách converter mặc định cho content-type conversion của message endpoint.

Khi có Jackson trên classpath, danh sách mặc định của Spring Integration được khai báo theo thứ tự:

| Thứ tự | Converter | Vai trò chính |
|---:|---|---|
| 1 | `MappingJackson2MessageConverter` | Chuyển JSON và object Java; chỉ có khi Jackson processor hiện diện trên classpath |
| 2 | `ByteArrayMessageConverter` | Chuyển payload `byte[]` với MIME type `application/octet-stream` |
| 3 | `ObjectStringMessageConverter` | Chuyển String và có thể chuyển object khác thành String qua `toString()` |
| 4 | `GenericMessageConverter` | Dùng `ConversionService` để chuyển kiểu Java khi có converter phù hợp |

Nếu Jackson không có trên classpath, converter JSON đầu tiên không được đăng ký; các converter mặc định còn lại giữ thứ tự tương ứng.

`ObjectStringMessageConverter` là converter của Spring Integration, không phải converter mặc định của Spring Framework thuần. Đây là fallback chuyển object thành String. Tài liệu khuyến nghị dùng chiều `fromMessage` của nó với target type là `String.class`; không dùng `toString()` như một cách serialize JSON hay một contract truyền dữ liệu.

### Các constructor của ConfigurableCompositeMessageConverter

Spring Integration cung cấp ba cách tạo:

~~~java
// Danh sách converter mặc định.
new ConfigurableCompositeMessageConverter();

// Chỉ dùng converter tùy chỉnh; không thêm converter mặc định.
new ConfigurableCompositeMessageConverter(customConverters);

// Converter tùy chỉnh đứng trước, converter mặc định được thêm ở cuối.
new ConfigurableCompositeMessageConverter(customConverters, true);
~~~

Cách thứ ba hữu ích khi ứng dụng cần ưu tiên định dạng riêng nhưng vẫn muốn giữ các fallback chuẩn. Converter tùy chỉnh phải trả về `null` khi nó không hỗ trợ message để composite tiếp tục thử converter kế tiếp.

## 5. Vì sao thứ tự lại quan trọng?

Giả sử ứng dụng có:

- Một converter chuyên xử lý JSON.
- Một converter chuyên xử lý bytes.
- Một converter có thể chuyển nhiều kiểu thành String.
- Một converter tổng quát dùng `ConversionService`.

Converter chuyên biệt thường nên đứng trước converter fallback rộng. Nếu một converter rộng đứng quá sớm và trả về kết quả cho một payload mà converter chuyên biệt xử lý tốt hơn, composite sẽ dừng ngay tại kết quả đó.

Một số tình huống:

**JSON bytes sang Order**

- `MappingJackson2MessageConverter` kiểm tra content type `application/json` và target type `Order`.
- Nếu hỗ trợ, nó trả về `Order`.
- Composite dừng; byte-array, string và generic converter không được gọi.

**Binary bytes sang byte[]**

- Converter JSON không hỗ trợ `application/octet-stream` nên trả về `null`.
- `ByteArrayMessageConverter` xử lý payload.
- Composite dừng ở converter thứ hai.

**Text sang String**

- Converter JSON và byte-array không hỗ trợ cặp MIME/payload/target tương ứng.
- `StringMessageConverter` hoặc `ObjectStringMessageConverter` có thể xử lý tùy danh sách đang dùng.

**String sang Integer**

- Converter văn bản có thể không hỗ trợ target type `Integer`.
- `GenericMessageConverter` thử `ConversionService`.
- Nếu `ConversionService` có khả năng chuyển `String` sang `Integer`, kết quả được trả về.

Đừng thêm một converter có thể xử lý mọi payload vào đầu danh sách chỉ vì nó “linh hoạt”. Một fallback quá rộng có thể che mất converter đúng định dạng và làm thay đổi kết quả khi thêm dependency hoặc thay đổi content type.

## 6. Ví dụ Java 17: thử converter theo thứ tự

Ví dụ dùng Spring Framework 6.2.18, Java 17 và Jackson 2.18.3. Nó tạo một `CompositeMessageConverter` với bốn delegate theo thứ tự rõ ràng, sau đó kiểm tra JSON, bytes, text và chuyển đổi kiểu Java.

Cấu trúc thư mục:

~~~text
composite-message-converter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CompositeConverterDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composite-message-converter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/CompositeConverterDemo.java`:

~~~java
package demo;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.ByteArrayMessageConverter;
import org.springframework.messaging.converter.CompositeMessageConverter;
import org.springframework.messaging.converter.GenericMessageConverter;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class CompositeConverterDemo {

    public static void main(String[] args) {
        List<MessageConverter> delegates = List.of(
                new MappingJackson2MessageConverter(),
                new ByteArrayMessageConverter(),
                new StringMessageConverter(),
                new GenericMessageConverter()
        );

        CompositeMessageConverter composite =
                new CompositeMessageConverter(delegates);

        String order = delegates.stream()
                .map(converter -> converter.getClass().getSimpleName())
                .collect(Collectors.joining(" -> "));

        System.out.println("converterOrder=" + order);

        String json = """
                {"orderId":"ORD-1001","total":125.00}
                """.trim();

        Message<byte[]> jsonMessage = MessageBuilder
                .withPayload(json.getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON
                )
                .build();

        Order convertedOrder = (Order) composite.fromMessage(
                jsonMessage,
                Order.class
        );

        System.out.println(
                "jsonOrder=" + convertedOrder.orderId()
                        + ":" + convertedOrder.total().toPlainString()
        );

        Message<?> outbound = composite.toMessage(convertedOrder, null);

        System.out.println(
                "outboundPayloadType="
                        + outbound.getPayload().getClass().getSimpleName()
        );
        System.out.println(
                "outboundContentTypePresent="
                        + (outbound.getHeaders().get(
                                MessageHeaders.CONTENT_TYPE) != null)
        );

        Message<byte[]> binaryMessage = MessageBuilder
                .withPayload("raw".getBytes(StandardCharsets.UTF_8))
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_OCTET_STREAM
                )
                .build();

        byte[] binary = (byte[]) composite.fromMessage(
                binaryMessage,
                byte[].class
        );

        System.out.println("rawByteCount=" + binary.length);

        Message<String> textMessage = MessageBuilder
                .withPayload("hello")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN
                )
                .build();

        String text = (String) composite.fromMessage(
                textMessage,
                String.class
        );

        System.out.println("plainText=" + text);

        Message<String> numberMessage = MessageBuilder
                .withPayload("42")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.TEXT_PLAIN
                )
                .build();

        Integer number = (Integer) composite.fromMessage(
                numberMessage,
                Integer.class
        );

        System.out.println("genericInteger=" + number);
    }
}

record Order(String orderId, BigDecimal total) {}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.CompositeConverterDemo
~~~

Kết quả stdout:

~~~text
converterOrder=MappingJackson2MessageConverter -> ByteArrayMessageConverter -> StringMessageConverter -> GenericMessageConverter
jsonOrder=ORD-1001:125.00
outboundPayloadType=byte[]
outboundContentTypePresent=true
rawByteCount=3
plainText=hello
genericInteger=42
~~~

Giải thích:

- JSON bytes có content type `application/json`, nên Jackson converter tạo `Order`.
- Khi serialize `Order`, Jackson converter tạo message có payload bytes và content type JSON mặc định.
- Binary message dùng `application/octet-stream`, nên byte-array converter xử lý.
- Text message dùng `text/plain`, nên string converter xử lý.
- Với target `Integer`, string converter không đáp ứng target type; generic converter dùng `ConversionService` để chuyển `"42"` thành `42`.
- Danh sách được truyền vào constructor chính là thứ tự ưu tiên. Composite dừng ngay khi một converter trả về kết quả khác `null`.

## 7. Đăng ký converter tùy chỉnh trong Spring Integration

Spring Integration dùng `ConfigurableCompositeMessageConverter` trong cơ chế phân giải tham số của message endpoint. Việc chuyển đổi có thể dựa vào header `contentType` khi endpoint cần chuyển payload sang kiểu tham số của handler.

Có thể thay đổi converter chain mặc định bằng bean có tên dành riêng cho argument resolver:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessageConversionConfiguration {

    @Bean(
        name = IntegrationContextUtils
                .ARGUMENT_RESOLVER_MESSAGE_CONVERTER_BEAN_NAME
    )
    public ConfigurableCompositeMessageConverter argumentResolverConverter(
            MessageConverter xmlConverter,
            MessageConverter protobufConverter) {

        return new ConfigurableCompositeMessageConverter(
                List.of(xmlConverter, protobufConverter),
                true
        );
    }
}
~~~

Trong cấu hình trên:

1. `xmlConverter` được thử trước.
2. `protobufConverter` được thử tiếp theo.
3. Các converter mặc định của Spring Integration được thêm ở cuối vì tham số `registerDefaults` là `true`.
4. Converter tùy chỉnh phải trả về `null` khi không hỗ trợ message để các converter sau có cơ hội xử lý.

Nếu muốn chỉ dùng converter tùy chỉnh và bỏ toàn bộ defaults, dùng constructor nhận collection mà không truyền `registerDefaults = true`:

~~~java
new ConfigurableCompositeMessageConverter(
        List.of(xmlConverter, protobufConverter)
);
~~~

Constructor không tham số tạo danh sách mặc định. Constructor chỉ nhận collection tạo danh sách riêng. Constructor nhận collection và `true` đặt converter tùy chỉnh trước defaults. Hãy chọn rõ ràng theo mục đích để tránh vô tình bỏ converter chuẩn.

Nếu ứng dụng cần thay thế toàn bộ cơ chế argument resolution, Spring Integration cũng cho phép đăng ký một `MessageConverter` riêng dưới bean name `integrationArgumentResolverMessageConverter`. Khi đó ứng dụng chịu trách nhiệm về toàn bộ chính sách chuyển đổi.

## 8. MessageConverter và ConversionService trong Spring Integration

Hai cơ chế thường bị nhầm vì cùng thực hiện chuyển đổi dữ liệu:

| Cơ chế | Đầu vào và đầu ra | Dùng khi |
|---|---|---|
| `MessageConverter` | Message payload đã serialize ↔ object Java | Chuyển JSON bytes thành DTO, hoặc DTO thành bytes |
| `ConversionService` | Một kiểu Java ↔ kiểu Java khác | Chuyển String thành Integer, enum, number hoặc kiểu ứng dụng |
| `GenericMessageConverter` | Message payload ↔ kiểu đích thông qua ConversionService | Dùng trong composite khi các converter chuyên biệt không xử lý |

Spring Integration còn có `integrationConversionService` cho các phép chuyển đổi kiểu trong runtime của Integration, ví dụ payload type conversion và data type channel. Nó khác với `ConfigurableCompositeMessageConverter` được dùng cho content-type conversion khi gọi method endpoint.

Không nên đăng ký converter cho constructor/property binding của Spring rồi mặc định rằng chúng sẽ được dùng cho runtime message conversion. Chỉ dùng chung `ConversionService` khi đã cấu hình alias hoặc wiring có chủ đích.

## 9. Lỗi thường gặp

1. **Cho rằng CompositeMessageConverter tự có converter mặc định.** Spring Framework composite chỉ dùng collection được truyền vào constructor. Danh sách mặc định thuộc Spring Integration `ConfigurableCompositeMessageConverter`.
2. **Nhầm thứ tự list với thứ tự tốt nhất theo MIME type.** Composite thử theo thứ tự collection; nó không tự xếp hạng theo độ chuyên biệt.
3. **Dùng collection không có thứ tự ổn định.** Dùng `List` để kết quả chọn converter có thể dự đoán.
4. **Đặt fallback rộng trước converter chuyên biệt.** Một converter trả về kết quả sớm sẽ chặn các converter phía sau.
5. **Dùng ObjectStringMessageConverter để serialize JSON.** Nó có thể gọi `toString()`; kết quả đó không phải JSON contract.
6. **Thiếu hoặc khai báo sai content type.** Converter có thể trả về `null` dù payload trông có vẻ đúng định dạng.
7. **Nhầm null với exception.** `null` có nghĩa converter không xử lý được và composite thử tiếp. Exception thường báo lỗi khi converter đã nhận xử lý nhưng dữ liệu hoặc cấu hình không hợp lệ.
8. **Bỏ converter mặc định ngoài ý muốn.** Constructor nhận collection của `ConfigurableCompositeMessageConverter` không tự thêm defaults; muốn giữ defaults sau custom converters, dùng constructor có `registerDefaults = true`.
9. **Chỉ kiểm thử inbound.** Cần kiểm thử cả `fromMessage` và `toMessage`, vì converter có thể hỗ trợ một chiều nhưng không hỗ trợ chiều còn lại.
10. **Nhầm MessageConverter với HTTP MessageConverter.** `org.springframework.messaging.converter.MessageConverter` là abstraction cho Spring Messaging; `org.springframework.http.converter.HttpMessageConverter` thuộc Spring Web và có contract khác.
11. **Cho rằng GenericMessageConverter có thể chuyển mọi kiểu.** Nó chỉ chuyển khi `ConversionService` tìm được converter phù hợp.
12. **Deserialize dữ liệu ngoài mà không kiểm soát kiểu đích.** Xác định kiểu đích rõ ràng, quản lý cấu hình Jackson và không tin metadata kiểu do nguồn không đáng tin cậy cung cấp.

## 10. Checklist thiết kế converter chain

- [ ] Xác định chiều chuyển đổi: serialized payload sang object hay object sang serialized payload.
- [ ] Xác định payload type, target type và content type cho từng loại message.
- [ ] Dùng `CompositeMessageConverter` với một `List` có thứ tự rõ ràng.
- [ ] Đặt converter chuyên biệt trước converter fallback rộng.
- [ ] Bảo đảm converter trả về `null` khi không hỗ trợ message.
- [ ] Để lỗi dữ liệu không hợp lệ được thể hiện bằng exception phù hợp.
- [ ] Phân biệt Spring Framework composite với Spring Integration configurable composite.
- [ ] Xác định có giữ converter defaults hay thay thế toàn bộ danh sách.
- [ ] Kiểm tra Jackson dependency nếu cần JSON converter mặc định.
- [ ] Đặt `MessageHeaders.CONTENT_TYPE` đúng với định dạng payload.
- [ ] Kiểm thử thứ tự delegate, cả inbound và outbound, cùng trường hợp không có converter phù hợp.
- [ ] Theo dõi lỗi conversion và ghi log đủ metadata để xác định content type, target type và converter đã chọn.

## 11. Kết luận

`CompositeMessageConverter` là chuỗi các `MessageConverter` được thử theo đúng thứ tự đã đăng ký; converter đầu tiên trả về kết quả khác `null` sẽ được chọn. Spring Framework cung cấp composite tổng quát, còn Spring Integration cung cấp `ConfigurableCompositeMessageConverter` với danh sách mặc định gồm Jackson, byte array, object-to-string và generic conversion theo thứ tự đã công bố. Muốn chọn converter đúng, hãy kiểm soát list order, content type, payload type và target type; đặt converter chuyên biệt trước fallback và kiểm thử cả hai chiều chuyển đổi.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2.18 Javadoc: CompositeMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/CompositeMessageConverter.html) — first-non-null delegation, constructor, fromMessage, toMessage và conversion hints.
- [Spring Framework 6.2.18 Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — contract chuyển đổi payload và sử dụng content type.
- [Spring Framework 6.2.18 Javadoc: MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/MappingJackson2MessageConverter.html) — chuyển đổi JSON với Jackson.
- [Spring Framework 6.2.18 Javadoc: ByteArrayMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/ByteArrayMessageConverter.html) — hỗ trợ application/octet-stream và byte[].
- [Spring Framework 6.2.18 Javadoc: GenericMessageConverter](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/converter/GenericMessageConverter.html) — sử dụng ConversionService cho chuyển đổi kiểu Java.
- [Spring Integration 6.5 Reference: Message Endpoints — Content Type Conversion](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html) — thứ tự mặc định của ConfigurableCompositeMessageConverter và cách đăng ký converter tùy chỉnh.
- [Spring Integration 6.1 Javadoc: ConfigurableCompositeMessageConverter](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/converter/ConfigurableCompositeMessageConverter.html) — constructors và thứ tự defaults/custom converters.
- [Spring Integration 6.1 Javadoc: ObjectStringMessageConverter](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/converter/ObjectStringMessageConverter.html) — hành vi chuyển object thành String và phạm vi khuyến nghị.
- [Spring Framework 6.2 Reference: Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html) — ConversionService và cơ chế chuyển đổi giữa các kiểu Java.
