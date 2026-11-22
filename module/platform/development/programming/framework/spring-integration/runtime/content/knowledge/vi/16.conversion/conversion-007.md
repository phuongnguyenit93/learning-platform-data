# Custom converter và registration trong Spring Integration runtime

## 1. Bài toán: khi message đến đúng channel nhưng sai kiểu payload

Trong module **SPRING_INTEGRATION_RUNTIME**, message đi qua channel, endpoint, consumer, poller và executor. Một consumer có thể yêu cầu payload là `OrderId`, trong khi upstream đang gửi `String`, JSON hoặc `byte[]`. Spring Integration cần biết **quy tắc chuyển đổi** và **nơi đăng ký** quy tắc đó trước khi consumer chạy.

Chủ đề **Conversion → Custom converter và registration** trả lời bốn câu hỏi:

1. Khi nào cần viết custom converter thay vì transformer hoặc mapper nghiệp vụ?
2. Đăng ký converter như thế nào để **Spring Integration runtime** thực sự sử dụng?
3. Phân biệt `Converter<S,T>`/`ConversionService` với `MessageConverter` và header `contentType` ra sao?
4. Khi conversion lỗi hoặc mất hiệu năng, tìm đúng vị trí trên message flow thế nào?

Ví dụ: producer gửi message có payload `"  ORD-007  "`, còn consumer nhận `OrderId("ORD-007")`. Ta có thể đặt ràng buộc kiểu trên channel và đăng ký bộ chuyển `String → OrderId`.

~~~mermaid
flowchart LR
    P["Producer: String payload"] --> C["typedOrders: DirectChannel\nsetDatatypes(OrderId.class)"]
    C --> V{"Đúng kiểu OrderId?"}
    V -->|Có| H["@ServiceActivator\nconsume(OrderId)"]
    V -->|Không| CS["integrationConversionService\nString → OrderId"]
    CS -->|Chuyển được| H
    CS -->|Không thể chuyển| E["Conversion / delivery error"]
~~~

Cần nhớ rằng một converter được đăng ký **không tự động biến đổi tất cả message**. Framework chỉ gọi nó khi có mục tiêu kiểu dữ liệu và một thành phần thực thi hỗ trợ conversion (ví dụ datatype channel hoặc cơ chế ánh xạ tham số endpoint).

## 2. Ba lớp cơ chế rất dễ bị nhầm

| Cơ chế | Abstraction chính | Dữ liệu có thể xem | Nơi thường được gọi | Dùng khi |
| --- | --- | --- | --- | --- |
| **Type conversion** | `Converter<S,T>`, `GenericConverter`, `ConverterFactory` qua `ConversionService` | Đối tượng nguồn và kiểu đích; `GenericConverter` còn có `TypeDescriptor` | Datatype channel, chuyển kiểu payload/tham số, một số biểu thức và thành phần khác | Chuyển `String → OrderId`, `String → Enum`, kiểu giá trị này sang kiểu giá trị khác |
| **Message conversion** | `org.springframework.messaging.converter.MessageConverter` | `Message<?>` gồm payload và headers; nhận `targetClass` | Method argument resolver, datatype channel với converter tùy biến, adapter tùy loại | Decode JSON/CSV theo `contentType`, kết hợp headers để chọn format |
| **Message transformer** | `@Transformer`, `IntegrationFlow.transform(...)` và handler transformer | Payload/headers theo method hoặc transformer được chọn | Một endpoint rõ ràng trong flow | Thay đổi cấu trúc nghiệp vụ, làm sạch hoặc enrichment dữ liệu theo từng bước |

`Converter` của Spring Framework xử lý một giá trị Java. `MessageConverter` của Spring Messaging hiểu một **message** và kiểu đích; nó có hai hướng `fromMessage(...)` và `toMessage(...)`. Còn transformer là một **endpoint** trong sơ đồ điều phối message. Có thể phối hợp chúng, nhưng không nên dùng ba khái niệm như từ đồng nghĩa.

**Đường đi của conversion tùy ngữ cảnh:**

- Datatype channel kiểm tra kiểu payload khi `send()`; nếu không khớp, nó có thể nhờ `DefaultDatatypeChannelMessageConverter` và `integrationConversionService` chuyển sang kiểu cho phép.
- Endpoint khai báo method `handle(OrderId id)` có thể cần chuyển payload sang kiểu tham số; cơ chế argument resolver/handler invocation quyết định cách thực hiện.
- Message có `contentType = application/json` không tự bảo đảm JSON được deserialize; phải có bộ chuyển tương thích với payload, target type và vị trí invocation.
- Inbound/outbound adapter như HTTP, JMS, AMQP cũng có converter riêng và quy tắc adapter riêng. Đăng ký `@IntegrationConverter` không có nghĩa mọi adapter sẽ tự dùng cùng một converter.

## 3. Viết custom converter cơ bản

API đơn giản nhất là `org.springframework.core.convert.converter.Converter<S,T>`:

~~~java
import org.springframework.core.convert.converter.Converter;

public record OrderId(String value) { }

public final class StringToOrderIdConverter implements Converter<String, OrderId> {
    @Override
    public OrderId convert(String source) {
        String normalized = source.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }
        return new OrderId(normalized);
    }
}
~~~

Trong đoạn trên, `OrderId` và `StringToOrderIdConverter` được minh họa như **hai tệp Java riêng** vì Java không cho phép đặt hai top-level `public` type trong cùng một tệp. Ví dụ runnable một tệp nằm ở mục 5.

Những nguyên tắc khi thiết kế:

- Viết converter **thuần, xác định**: cùng input cho cùng output, không ghi database hoặc gọi API.
- Chuẩn hóa dữ liệu hợp lệ, nhưng **ném ngoại lệ rõ nghĩa** khi không thể chuyển. Không trả về `null` để “âm thầm bỏ” một message; tùy điểm gọi, kết quả null có thể bị xem là không chuyển được.
- Chú ý nguồn/đích chính xác: `Converter<String, OrderId>` không đồng nghĩa `Converter<byte[], OrderId>`. Nếu đầu vào là byte array, cần decode trước hoặc đăng ký converter phù hợp.
- Giữ converter thread-safe. Một bean converter thường dùng chung giữa nhiều message và nhiều consumer thread.
- Tránh tạo các cặp chuyển quá rộng như `Object → Object`: chúng dễ gây xung đột với converter tích hợp và làm khó đoán kết quả.

### Khi nào dùng `GenericConverter` hoặc `ConverterFactory`?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một cặp nguồn/đích cụ thể, ví dụ `String → OrderId` | `Converter<S,T>` |
| Một converter hỗ trợ nhiều cặp kiểu hoặc cần kiểm tra kiểu generic/lớp cụ thể | `GenericConverter`; kết hợp `ConditionalConverter` nếu cần |
| Một nhóm kiểu đích cùng họ, ví dụ nhiều subclass hoặc enum | `ConverterFactory<S,R>` |
| Quyết định theo `contentType`/tenant/locale từ **message headers** | `MessageConverter` hoặc endpoint có logic được kiểm soát, vì `Converter<S,T>` không nhận headers |

`GenericConverter` nhận `TypeDescriptor` của nguồn và đích, hữu ích khi thông tin generic/annotation liên quan tới lựa chọn chuyển đổi. Đừng tăng độ phức tạp chỉ để chuyển một cặp kiểu đơn giản.

## 4. Registration: làm cho Spring Integration biết tới converter

### 4.1. Đăng ký `@Bean` + `@IntegrationConverter` (thường dùng trong Java configuration)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.IntegrationConverter;

@Configuration
class ConverterRegistration {

    @Bean
    @IntegrationConverter
    StringToOrderIdConverter stringToOrderIdConverter() {
        return new StringToOrderIdConverter();
    }
}
~~~

`@IntegrationConverter` là marker cho các bean triển khai `Converter`, `GenericConverter` hoặc `ConverterFactory`. Hạ tầng Spring Integration thu thập chúng và đăng ký với conversion service cho runtime. Đừng chỉ dựa vào `@Bean` kiểu `Converter` rồi mặc định nó sẽ được đưa vào đúng registry.

Biến thể tương đương khi component scan:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.integration.config.IntegrationConverter;

@Component
@IntegrationConverter
public final class StringToOrderIdConverter
        implements Converter<String, OrderId> {
    @Override
    public OrderId convert(String source) {
        return new OrderId(source.trim());
    }
}
~~~

Hai cách trên là **lựa chọn thay thế**; đừng đồng thời khai báo `@Component` và `@Bean` cho cùng converter khi không cần. Mẫu `@Component` rút gọn logic validation để tập trung vào registration; ví dụ hoàn chỉnh giữ validation ở mục 5.

### 4.2. XML namespace

Nếu ứng dụng dùng cấu hình XML của Spring Integration:

~~~xml
<bean id="stringToOrderId"
      class="demo.integration.StringToOrderIdConverter"/>

<int:converter ref="stringToOrderId"/>
~~~

`<int:converter/>` tương ứng về mục đích với `@IntegrationConverter`. Nó đăng ký bộ chuyển vào `integrationConversionService`. Các ví dụ XML yêu cầu namespace `int` được khai báo theo schema Spring Integration thích hợp.

### 4.3. `integrationConversionService` khác `conversionService`

| Bean / registry | Phạm vi chính | Lưu ý |
| --- | --- | --- |
| `conversionService` | Chuyển kiểu phục vụ Spring Framework, chẳng hạn binding property, cấu hình bean | Có thể được ứng dụng/Boot khai báo với mục đích riêng |
| `integrationConversionService` | Chuyển kiểu **trong lúc xử lý message ở Spring Integration runtime** | Tự được hạ tầng tạo khi đăng ký converter bằng cơ chế Integration, nếu chưa có |
| `integrationArgumentResolverMessageConverter` | `MessageConverter` phục vụ resolution tham số của method endpoint | Độc lập với `@IntegrationConverter`; có thể kiểm tra `contentType` |
| `datatypeChannelMessageConverter` | `MessageConverter` của datatype channel | Mặc định tìm `integrationConversionService` và chuyển payload theo target type |

Cẩn thận với cách đăng ký thủ công: một bean tên `conversionService` không phải mặc nhiên là bean `integrationConversionService`. Muốn dùng chung, có thể khai báo alias trong XML:

~~~xml
<alias name="conversionService" alias="integrationConversionService"/>
~~~

Chỉ nên chọn cách này khi muốn cố ý chia sẻ tất cả quy tắc conversion giữa **cấu hình ứng dụng** và **runtime message**; các converter thiết kế cho cấu hình bean có thể không thích hợp cho dữ liệu message. Trong hệ thống lớn, giữ hai registry độc lập thường làm phạm vi ảnh hưởng dễ kiểm soát hơn.

## 5. Ví dụ chạy được: datatype channel tự đổi String thành OrderId

Ví dụ một tệp `ConversionDemoApplication.java` với Spring Boot, Spring Integration và Java 17+. Spring Boot cần dependency Spring Integration core/starter tương ứng, và package `demo.integration` phải nằm trong component scan.

~~~java
package demo.integration;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.convert.converter.Converter;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.IntegrationConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class ConversionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }

    // Channel chỉ chấp nhận OrderId làm payload.
    @Bean
    MessageChannel typedOrders() {
        DirectChannel channel = new DirectChannel();
        channel.setDatatypes(OrderId.class);
        return channel;
    }

    // Đưa quy tắc String -> OrderId vào registry của Integration.
    @Bean
    @IntegrationConverter
    StringToOrderIdConverter orderIdConverter() {
        return new StringToOrderIdConverter();
    }

    @Bean
    ApplicationRunner produce(@Qualifier("typedOrders") MessageChannel orders) {
        return args -> {
            boolean sent = orders.send(
                MessageBuilder.withPayload("  ORD-007  ")
                    .setHeader("traceId", "trace-007")
                    .build()
            );
            if (!sent) {
                throw new IllegalStateException("Channel did not accept the message");
            }
        };
    }
}

// Không public: cùng file Java với ConversionDemoApplication.
record OrderId(String value) {}

final class StringToOrderIdConverter implements Converter<String, OrderId> {

    @Override
    public OrderId convert(String source) {
        String value = source.trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }
        return new OrderId(value);
    }
}

@MessageEndpoint
class OrderReceiver {

    @ServiceActivator(inputChannel = "typedOrders")
    public void consume(OrderId orderId, @Header("traceId") String traceId) {
        System.out.println(orderId.value() + " | " + traceId);
    }
}
~~~

Kết quả dự kiến:

~~~text
ORD-007 | trace-007
~~~

Diễn giải đúng thứ tự runtime:

1. `ApplicationRunner` gửi một `Message<String>` tới `typedOrders`.
2. `DirectChannel` kiểm tra `String` có tương thích với `OrderId.class` không. Vì không, nó thử chuyển kiểu thông qua `DefaultDatatypeChannelMessageConverter`.
3. Converter đã đăng ký qua `@IntegrationConverter` tạo `OrderId("ORD-007")`.
4. Channel chuyển message có payload đã đổi kiểu cho `OrderReceiver`. Header `traceId` được giữ để consumer đọc.
5. `@ServiceActivator` chạy trên cùng lời gọi `send()` vì đang dùng `DirectChannel` đồng bộ.

Lưu ý: ở bước 3, converter chỉ nhận **chuỗi nguồn**, không nhận `traceId`. Nếu conversion cần header, hãy dùng một `MessageConverter` phù hợp hoặc đặt một endpoint rõ ràng. `send()` trả `true` chỉ cho biết channel chấp nhận message theo contract của nó; không phải xác nhận đã commit mọi hiệu ứng ở các hệ thống bên ngoài.

### Trường hợp nào converter có chạy?

| Payload gửi tới `typedOrders` | Diễn biến | Kết quả |
| --- | --- | --- |
| `"  ORD-007  "` (`String`) | Không khớp `OrderId`; cần conversion | Consumer nhận `OrderId("ORD-007")` |
| `new OrderId("ORD-008")` | Đã đúng kiểu | Consumer nhận trực tiếp, không cần `StringToOrderIdConverter` |
| `"   "` | Converter phát hiện ID rỗng | Lỗi conversion/delivery; không tới consumer |
| `byte[]` | Không khớp kiểu nguồn converter đã đăng ký | Chỉ thành công nếu có conversion path khác thích hợp; nếu không sẽ lỗi |

Với channel cho phép nhiều datatype, runtime có thể cân nhắc các kiểu đích cho phép; để tránh mơ hồ, nên định nghĩa giao ước đầu vào rõ ràng.

## 6. Phân biệt chuyển kiểu tham số endpoint với chuyển tại channel

Có hai thời điểm conversion thường gặp:

~~~mermaid
flowchart TD
    A["Message<String>"] --> B{"Ràng buộc datatype\ntrên channel?"}
    B -->|Có| C["Kiểm tra / convert payload\nkhi gửi vào channel"]
    B -->|Không| D["Channel chuyển message như hiện có"]
    C --> E["Endpoint method invocation"]
    D --> E
    E --> F{"Kiểu payload có phù hợp\nmethod parameter?"}
    F -->|Có| G["Gọi method"]
    F -->|Không| H["Argument resolver thử conversion\nđược cấu hình và hỗ trợ"]
    H -->|Thành công| G
    H -->|Không được| X["Lỗi ở endpoint"]
~~~

**Datatype channel** chủ động xác lập hợp đồng kiểu tại ranh giới channel. Điều này đặc biệt hữu ích khi nhiều consumer/producer liên quan đến cùng contract; nơi gửi có thể phát hiện payload không hợp lệ sớm.

**Method argument conversion** xảy ra tại khâu gọi method, ví dụ `@ServiceActivator` hoặc POJO endpoint. Tùy cách invocation, Spring Integration có thể dùng `integrationConversionService` cho class-to-class conversion hoặc dùng `MessageConverter` trong argument resolver. Không nên suy luận rằng mọi method có tham số `OrderId` sẽ tự đổi mọi `String` trong mọi cấu hình. Hãy dùng kiểm thử cho đúng endpoint và cách khai báo đang sử dụng.

Nếu một bước cần thao tác nghiệp vụ như ghép nhiều field, truy vấn dữ liệu hoặc chuẩn hóa theo tenant, hãy dùng một transformer riêng, với input/output channel rõ ràng. Converter runtime nên tập trung vào biểu diễn dữ liệu.

## 7. Custom MessageConverter: khi target type và contentType cùng quan trọng

Một converter đọc message có giao diện từ Spring Messaging:

~~~java
public interface MessageConverter {
    Object fromMessage(Message<?> message, Class<?> targetClass);
    Message<?> toMessage(Object payload, MessageHeaders headers);
}
~~~

Đây là **dạng chữ ký rút gọn** (bỏ annotation nullability) để giải thích; không phải khai báo lại interface framework.

Ví dụ nghiệp vụ: text payload `"ORD-007;150000"` với header `contentType = text/x-order` cần thành `OrderCommand(String id, BigDecimal amount)`. Khi header khác, converter nên trả `null` để converter khác có cơ hội xử lý. Khi header đúng nhưng dữ liệu hỏng, nên ném exception rõ nghĩa.

~~~java
package demo.integration;

import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.MessageConverter;

record OrderCommand(String id, BigDecimal amount) {}

final class OrderTextMessageConverter implements MessageConverter {

    @Override
    public Object fromMessage(Message<?> message, Class<?> targetClass) {
        if (targetClass != OrderCommand.class ||
                !(message.getPayload() instanceof String text)) {
            return null;
        }

        Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
        if (contentType == null ||
                !contentType.toString().startsWith("text/x-order")) {
            return null;
        }

        String[] fields = text.split(";", -1);
        if (fields.length != 2 || fields[0].isBlank()) {
            throw new MessageConversionException(message, "Invalid order text");
        }
        try {
            return new OrderCommand(
                fields[0].trim(),
                new BigDecimal(fields[1].trim())
            );
        } catch (NumberFormatException ex) {
            throw new MessageConversionException(
                message, "Invalid order amount", ex);
        }
    }

    @Override
    public Message<?> toMessage(Object payload, MessageHeaders headers) {
        // Ví dụ này hỗ trợ inbound conversion; trả null nếu không xử lý outbound.
        return null;
    }
}
~~~

Trong một class `@Configuration`, đăng ký converter cho **method argument resolution** bằng bean name đúng:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.context.IntegrationContextUtils;
import org.springframework.integration.support.converter.ConfigurableCompositeMessageConverter;

@Configuration
class ArgumentConversionConfiguration {

    @Bean(name = IntegrationContextUtils.ARGUMENT_RESOLVER_MESSAGE_CONVERTER_BEAN_NAME)
    ConfigurableCompositeMessageConverter argumentMessageConverter() {
        return new ConfigurableCompositeMessageConverter(
            List.of(new OrderTextMessageConverter()),
            true   // Giữ các default converters sau custom converter.
        );
    }
}
~~~

`ConfigurableCompositeMessageConverter` thử các delegate theo thứ tự và dừng khi một converter trả kết quả khác `null`. Đối số `true` ở constructor hai tham số yêu cầu thêm các converter mặc định **sau** converter tùy biến. Constructor một tham số nhận list sẽ **không** tự thêm defaults; rất dễ gây lỗi cho format trước đó vẫn được hỗ trợ.

Có thể dùng `@ServiceActivator(inputChannel = "textOrders")` với method `consume(OrderCommand command)` và gửi `Message<String>` có `contentType = text/x-order` để kiểm chứng converter tham số hoạt động. Đối với method invocation dựa trên SpEL, cơ chế `MessageConverter` theo `contentType` không được áp dụng giống argument resolver; cần kiểm tra cách endpoint đó cấu hình.

**Đừng nhầm registration:** `@IntegrationConverter` chỉ đánh dấu Spring `Converter`/`GenericConverter`/`ConverterFactory`. Nó không tự đăng ký một `MessageConverter` vào `integrationArgumentResolverMessageConverter`. Ngược lại, đăng ký bean argument resolver không tự đổi luật datatype cho mọi channel.

### Custom converter dành riêng cho datatype channel

Datatype channel có converter mặc định `DefaultDatatypeChannelMessageConverter`, tra cứu `integrationConversionService` theo bean name. Khi muốn chuyển dữ liệu có xét headers ở **chính ranh giới channel**, có thể gắn một `MessageConverter` riêng cho channel hoặc cung cấp bean `datatypeChannelMessageConverter` cho các datatype channel.

Đối với custom `MessageConverter` đó, datatype channel chỉ sử dụng hướng `fromMessage(message, targetClass)`; method có thể trả payload đã chuyển hoặc một `Message<?>` đầy đủ. Khi tự trả một `Message<?>`, phải bảo toàn các headers cần thiết như `correlationId`, `replyChannel`, `errorChannel`, trace và thông tin bảo mật theo contract; không coi copy toàn bộ headers là mặc nhiên an toàn cho mọi hệ thống.

## 8. Chuyển đổi ở runtime: thread, transaction, retry, message store

Conversion là một phần của **đường chạy thực tế**; nó chịu ảnh hưởng bởi nơi đặt channel và cách consumer nhận message.

| Vị trí trong flow | Conversion thường xảy ra khi nào? | Hệ quả |
| --- | --- | --- |
| `DirectChannel` có `setDatatypes(...)` | Trong lời gọi `send()`, trước khi dispatch đến handler | Producer có thể thấy lỗi ngay trên thread hiện tại |
| `ExecutorChannel` có datatype | Kiểm tra/chuyển kiểu ở ranh giới channel; handler được dispatch bằng executor | Không được suy rằng lỗi converter và lỗi handler xảy ra trên cùng thread |
| `QueueChannel` có datatype | Kiểm tra/chuyển payload khi enqueue vào channel; poller lấy message đã nhận sau đó | Tách thời điểm conversion lúc gửi và xử lý lúc poll |
| Endpoint POJO có type conversion tham số | Khi adapter gọi method trên thread consumer | Lỗi có thể xuất hiện sau dequeue hoặc trong worker thread |
| Adapter inbound/outbound có message conversion | Theo vòng đời adapter, thường gần điểm đi vào/ra hệ thống bên ngoài | Phải kiểm tra converter cụ thể của adapter, content type và acknowledgement |

Đừng mặc định converter có retry hoặc transaction riêng. Retry advice thường gắn với handler/poller; conversion ở lúc `send()` vào datatype channel có thể nằm **ngoài** vùng retry advice của endpoint downstream. Nếu muốn retry khi nguồn dữ liệu tạm thời không đọc được, cần thiết kế vị trí retry phù hợp. Tuy vậy lỗi cú pháp cố định (ví dụ ID rỗng) thường **không nên retry**.

Transaction của Spring thường gắn với thread. Trên flow đồng bộ, conversion có thể xảy ra bên trong transaction của lời gọi. Khi flow qua executor hoặc poller, transaction context không tự truyền sang thread mới. Converter không nên phụ thuộc vào side effect chưa commit ở thread khác; cũng không nên thực hiện I/O/ghi database bên trong `convert()`.

Message store và persistence có thêm điểm cần nghĩ tới:

- Nếu lưu message **trước** bước conversion, phải lưu được kiểu payload nguồn và metadata cần decode khi đọc lại.
- Nếu lưu message **sau** bước conversion, kiểu đích phải serializable/được mapping phù hợp với `MessageStore` cụ thể.
- Không giả định format Java record/object có thể được persistence provider tự lưu và khôi phục trong mọi backend. Xác nhận cấu hình serializer, version schema và tính tương thích khi triển khai.
- Header `correlationId` có thể giữ qua conversion kiểu payload đơn giản, nhưng **correlation vẫn cần chiến lược rõ** trong splitter/aggregator và các flow đa nhánh.

Về hiệu năng, chỉ số đáng theo dõi là số lần conversion theo cặp kiểu, p95/p99 latency ở endpoint/channel, lỗi conversion, độ sâu queue và mức sử dụng executor. Conversion JSON nặng hoặc format parse lặp lại có thể tăng allocation và GC. Converter nên stateless và tránh giữ buffer mutable dùng chung giữa các worker.

## 9. Chẩn đoán lỗi registration và conversion

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| `No converter found capable of converting...` hoặc lỗi datatype channel | Không có converter phù hợp với **source type** và **target type** | Kiểm tra bean có `@IntegrationConverter`, kiểu generic chính xác, target `setDatatypes(...)` |
| Bean converter tồn tại nhưng method `convert()` không chạy | Không có điểm yêu cầu đổi kiểu, payload đã đúng kiểu, bean không được đăng ký vào Integration registry | Xem flow và runtime `canConvert(...)` |
| `ConversionFailedException` / lỗi wrapper khi `send()` | Nguồn không hợp lệ, parse ném exception, kiểu trả về không tương thích | Tìm root cause và payload type tại điểm gửi |
| JSON/CSV không decode theo `contentType` | Đăng ký `Converter` thay vì `MessageConverter`, thiếu header hoặc resolver khác đang được dùng | Kiểm tra `MessageHeaders.CONTENT_TYPE`, bean `integrationArgumentResolverMessageConverter` và invocation mode |
| Một luồng xử lý cũ bị hỏng sau khi thêm converter | Converter mới có phạm vi quá rộng, hoặc composite đã thay defaults | Giới hạn cặp kiểu; kiểm tra constructor composite và thứ tự delegate |
| Test synchronous PASS nhưng production async fail | Sai khác thread và thời điểm xử lý; lỗi nằm trong poller/worker | Log thread, `errorChannel`, retry advice, trạng thái endpoint/poller |
| Header trace/correlation biến mất | Custom `MessageConverter` tự trả message mới nhưng không chuyển headers cần thiết | Kiểm tra `MessageBuilder` và contract xử lý headers của adapter |

Kiểm tra nhanh khi đã bật context:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.core.convert.ConversionService;

public void inspectConversionService(ApplicationContext context) {
    ConversionService cs = context.getBean(
        "integrationConversionService", ConversionService.class);

    System.out.println(cs.canConvert(String.class, OrderId.class));
    System.out.println(cs.convert("  ORD-007  ", OrderId.class));
}
~~~

Đây là **đoạn kiểm tra độc lập** dựa trên `OrderId` và converter ở mục 5; gọi sau khi context khởi tạo. Kết quả mong đợi là `true` và `OrderId[value=ORD-007]`. Nếu thiếu bean, điều đó gợi ý chưa khởi tạo registry qua đúng cấu hình hoặc không tồn tại conversion service trong context đang kiểm tra. `canConvert(...) == true` chỉ xác nhận có conversion path, chưa chứng minh mọi input đều hợp lệ hay logic chuyển đổi đã được endpoint thực sự sử dụng.

### Tổ chức lỗi theo nghiệp vụ

- **Input bị lỗi vĩnh viễn:** ghi nhận theo định dạng đầu vào, đưa sang error/dead-letter flow nếu hệ thống yêu cầu; không retry vô hạn.
- **Hạ tầng tạm thời lỗi:** đặt retry có giới hạn, backoff và idempotency ở endpoint/adapter phù hợp; tránh làm converter phụ thuộc trực tiếp hạ tầng.
- **Sai cấu hình converter:** xem như lỗi triển khai, sửa registration và version; retry cùng message không giải quyết được.
- **Async flow:** định nghĩa `errorChannel`/`ErrorMessage` đúng nơi; `try/catch` bọc `send()` thường không bắt lỗi handler diễn ra sau trên worker thread.

## 10. Bài thực hành từng bước

1. Chạy chương trình mục 5; xác nhận `OrderReceiver` nhận `OrderId("ORD-007")` và `traceId`.
2. Thử gửi trực tiếp `new OrderId("ORD-008")`; đặt breakpoint trong converter và xác nhận không nhất thiết chạy khi payload đã đúng kiểu.
3. Bỏ `@IntegrationConverter` tại bean registration rồi khởi động lại. Gửi payload String vào `typedOrders`, ghi nhận hành vi lỗi hoặc converter khác nếu ứng dụng có; khôi phục annotation.
4. Đổi input thành chuỗi trắng; quan sát exception gốc và xem ứng dụng có xử lý/retry sai loại lỗi không.
5. Thêm `@ServiceActivator` nhận `OrderCommand` trên channel `textOrders` rồi dùng MessageConverter ở mục 7. Thử cả `contentType = text/x-order`, header không tồn tại, và chuỗi amount lỗi.
6. Đổi datatype channel thành `QueueChannel` và thêm polling consumer đúng cách; so sánh thời điểm conversion với thời điểm method nhận message, log tên thread và queue depth.
7. Nếu có message store, lưu và đọc lại message trước/sau conversion để kiểm tra tính tương thích serializer, headers và correlation.

### Những điều cần ghi nhớ

- Viết `Converter<S,T>` cho **type-to-type**, đăng ký bằng `@IntegrationConverter` hoặc `<int:converter/>` để Spring Integration runtime biết tới.
- `integrationConversionService` chuyên phục vụ conversion khi chạy message; khác với `conversionService` của cấu hình Spring.
- Datatype channel có thể chuyển payload ngay khi gửi message; endpoint method argument converter có thời điểm gọi và cơ chế registration khác.
- Dùng `MessageConverter` nếu cần xem đầy đủ message và `contentType`; chú ý bean name và giữ default converters nếu muốn.
- Registration thành công không bảo đảm converter được gọi trên mọi message. Phải xác nhận target type, channel/endpoint và thread tại điểm xử lý.
- Converter nên đơn giản, thread-safe, có lỗi rõ ràng; transaction, retry, message store và correlation thuộc thiết kế runtime của flow.

## 11. Tài liệu chính thức

- [Spring Integration — Message Endpoints: Payload Type Conversion và Content Type Conversion](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Configuring Message Channels: Datatype Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration API — `@IntegrationConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/config/IntegrationConverter.html)
- [Spring Integration API — `ConfigurableCompositeMessageConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/converter/ConfigurableCompositeMessageConverter.html)
- [Spring Integration API — `DefaultDatatypeChannelMessageConverter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/converter/DefaultDatatypeChannelMessageConverter.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
