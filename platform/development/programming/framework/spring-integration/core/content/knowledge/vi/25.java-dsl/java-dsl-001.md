# IntegrationFlow

## 1. Mục tiêu và bối cảnh

Trong chương **Java DSL** của module **SPRING_INTEGRATION_CORE**, bài này trình bày cách dùng `IntegrationFlow` để thiết kế và khai báo một luồng thông điệp. Trọng tâm là mối quan hệ giữa `Message`, `MessageChannel`, endpoint và gateway; các phép biến đổi, lọc, định tuyến, gom nhóm là những thành phần có thể ghép vào luồng.

Sau bài học, bạn có thể:

- Đọc một flow và xác định đầu vào, các bước xử lý, đầu ra.
- Khai báo flow thành Spring bean và đưa thông điệp vào đúng channel.
- Phân biệt cấu hình DSL với quá trình xử lý từng thông điệp.
- Thiết kế đường trả lời và đường lỗi cho một yêu cầu qua gateway.
- Kiểm thử hành vi của flow bằng Spring Test và JUnit.

Ví dụ chính là dịch vụ báo giá: nhận số lượng dưới dạng chuỗi, chuẩn hóa, chuyển thành số nguyên, từ chối số lượng không dương và tính thành tiền. Đơn giá cố định chỉ phục vụ minh họa; bài không mô hình hóa thuế, giảm giá hay nghiệp vụ thanh toán.

Các ví dụ dùng cú pháp `IntegrationFlow.from(...)` của Spring Integration 6 trở lên. Dùng JDK và bộ dependency phù hợp với phiên bản Spring của dự án. Những đoạn được ghi là biến thể là lựa chọn độc lập, không phải cấu hình cần đăng ký đồng thời.

## 2. IntegrationFlow mô tả điều gì?

`IntegrationFlow` mô tả cách các channel và endpoint được ghép thành một luồng. Builder thu thập cấu hình; `IntegrationFlowBeanPostProcessor` xử lý cấu hình đó để đăng ký các thành phần vào Spring container. Khi chạy, thông điệp đi qua các channel và handler đã được tạo. Phương thức `@Bean` không chạy lại mỗi lần có yêu cầu. Cơ chế này được mô tả trong [tài liệu Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

| Thành phần | Vai trò trong ví dụ báo giá |
| --- | --- |
| `Message` | Mang số lượng hoặc kết quả cùng metadata |
| `MessageChannel` | Nối bên gửi với bước nhận tiếp theo |
| Handler | Thực hiện công việc như chuyển chuỗi thành số |
| Endpoint | Gắn handler vào cơ chế nhận message và quản lý hoạt động của nó |
| Gateway | Cung cấp phương thức Java để gọi vào hệ thống messaging |
| `IntegrationFlow` | Khai báo cấu trúc kết nối các thành phần trên |

Một flow có thể biểu diễn nhiều mẫu Enterprise Integration Patterns, không bắt buộc chỉ là chuỗi tuyến tính. Trong DSL, các động từ thường dùng tương ứng với các thành phần sau. Xem [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

| Phương thức | Thành phần/mục đích |
| --- | --- |
| `transform(...)` | Transformer: thay đổi biểu diễn dữ liệu |
| `filter(...)` | Filter: cho đi tiếp hoặc từ chối |
| `handle(...)` | Service activator: gọi xử lý |
| `route(...)` | Router: chọn đường đi |
| `split(...)` | Splitter: tách thông điệp |
| `aggregate(...)` | Aggregator: gom nhóm thông điệp |
| `bridge(...)` | Bridge: chuyển tiếp giữa các channel |

Để học cấu trúc flow, ta bắt đầu bằng đường đi tuyến tính. Khi bổ sung router hoặc aggregator, cần xác định thêm hợp đồng của từng nhánh và điều kiện hoàn tất nhóm.

## 3. Đọc cấu trúc khai báo

Một khai báo builder có dạng:

~~~java
@Bean
IntegrationFlow sampleFlow() {
    return IntegrationFlow.from("sample.input")
            .<String, String>transform(String::trim)
            .<String>filter(value -> !value.isEmpty())
            .<String>handle((payload, headers) -> "Received: " + payload)
            .get();
}
~~~

Đây là đoạn minh họa cấu trúc, chưa phải cấu hình báo giá hoàn chỉnh.

- `from(...)` xác định điểm vào.
- Các lệnh ở giữa khai báo endpoint hoặc channel.
- `get()` kết thúc builder và trả về đối tượng mô tả flow.

`get()` ở đây không nhận message, không chờ kết quả và không kích hoạt một yêu cầu nghiệp vụ. Tên bean `sampleFlow` cũng không phải tên channel `sample.input`.

Với `from("sample.input")`, DSL tìm channel mang tên đó; nếu chưa có, DSL có thể tạo `DirectChannel`. Các endpoint liền nhau mặc định được nối bằng direct channel. Cách phân giải này được trình bày trong [Message Channels của Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

Có thể khai báo channel tường minh và truyền đối tượng vào `from(...)` để làm rõ hợp đồng đầu vào:

~~~java
@Bean(name = "sample.input")
DirectChannel sampleInput() {
    return new DirectChannel();
}

@Bean
IntegrationFlow sampleFlow(
        @Qualifier("sample.input") DirectChannel input) {

    return IntegrationFlow.from(input)
            .<String, String>transform(String::trim)
            .get();
}
~~~

Hai đoạn ở mục này là hai lựa chọn thay thế. Không đăng ký cả hai bean `sampleFlow` trong cùng context.

## 4. Ví dụ hoàn chỉnh: luồng báo giá

### 4.1. Dependency và cấu trúc

Nếu dự án đã dùng Spring Boot với parent hoặc BOM tương ứng, có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Giữ dependency management thống nhất với dự án. Với ứng dụng Spring thuần, cần `spring-integration-core`; phần kiểm thử bên dưới cần Spring Test và JUnit Jupiter.

Ví dụ gồm `QuoteGateway.java`, `QuoteFlowConfiguration.java` và một lớp chạy thử, cùng nằm trong package `example.integration`.

~~~mermaid
flowchart LR
    A["Caller: quote(rawQuantity)"] --> G["QuoteGateway"]
    G --> C["quote.input"]
    C --> T1["trim: String → String"]
    T1 --> T2["parse: String → Integer"]
    T2 --> F{"quantity > 0?"}
    F -- Có --> H["Tính tiền: Integer → BigDecimal"]
    H --> R["replyChannel"]
    R --> G
    G --> O["Trả BigDecimal cho caller"]
    F -- Không --> E["MessageRejectedException"]
~~~

Sơ đồ chỉ thể hiện channel đầu vào và channel trả lời. Các bước liên tiếp ở giữa còn được nối bằng channel do DSL tạo.

### 4.2. Gateway là cửa vào của ứng dụng

File `QuoteGateway.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "quote.input",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "1000")
public interface QuoteGateway {

    BigDecimal quote(String rawQuantity);
}
~~~

Ứng dụng gọi `quote(" 3 ")` như một phương thức Java. Proxy gateway tạo request message và chuyển kết quả trả lời thành `BigDecimal`.

Ví dụ dùng `@Import(QuoteGateway.class)` ở cấu hình bên dưới để đăng ký proxy, cách được hỗ trợ từ Spring Integration 6. Một lựa chọn khác là `@IntegrationComponentScan` cho các interface có `@MessagingGateway`. Xem [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-configuration-annotations).

### 4.3. Khai báo channel và các bước xử lý

File `QuoteFlowConfiguration.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
@Import(QuoteGateway.class)
public class QuoteFlowConfiguration {

    private static final BigDecimal UNIT_PRICE =
            new BigDecimal("120000");

    @Bean(name = "quote.input")
    public DirectChannel quoteInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteFlow() {
        return IntegrationFlow.from("quote.input")
                .<String, String>transform(
                        String::trim,
                        endpoint -> endpoint.id("quote.trim"))
                .<String, Integer>transform(
                        Integer::valueOf,
                        endpoint -> endpoint.id("quote.parse"))
                .<Integer>filter(
                        quantity -> quantity > 0,
                        endpoint -> endpoint
                                .id("quote.positiveQuantity")
                                .throwExceptionOnRejection(true))
                .handle(
                        Integer.class,
                        (quantity, headers) ->
                                UNIT_PRICE.multiply(
                                        BigDecimal.valueOf(quantity)),
                        endpoint -> endpoint
                                .id("quote.calculateTotal")
                                .requiresReply(true))
                .get();
    }
}
~~~

`@EnableIntegration` cung cấp hạ tầng Spring Integration trong context cấu hình Java này. Mỗi `id(...)` đặt tên cho endpoint tương ứng, giúp xác định vị trí xử lý khi quan sát hoặc kiểm thử. Lambda cấu hình endpoint cũng là nơi đặt poller, lifecycle và advice khi cần. Xem [DSL and Endpoint Configuration](https://docs.spring.io/spring-integration/reference/dsl/java-endpoints.html).

Ở bước cuối, `handle(Integer.class, ...)` nhận payload và headers; `Integer.class` chỉ rõ kiểu đầu vào cho lambda. Giá trị trả về là kết quả xử lý được chuyển tiếp dưới dạng reply message. Các dạng handler và lưu ý về kiểu của lambda được mô tả trong [Service Activators and the handle() method](https://docs.spring.io/spring-integration/reference/dsl/java-handle.html).

### 4.4. Gọi thử qua Spring context

File `QuoteDemo.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class QuoteDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                QuoteFlowConfiguration.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);
            BigDecimal total = gateway.quote(" 3 ");

            System.out.println(total); // Kỳ vọng: 360000
        }
    }
}
~~~

Diễn tiến của yêu cầu:

| Vị trí | Payload | Kiểu |
| --- | --- | --- |
| Request message | `" 3 "` | `String` |
| Sau `quote.trim` | `"3"` | `String` |
| Sau `quote.parse` | `3` | `Integer` |
| Sau filter | `3` | `Integer` |
| Sau `quote.calculateTotal` | `360000` | `BigDecimal` |
| Giá trị gateway trả về | `360000` | `BigDecimal` |

Filter giữ nguyên message được chấp nhận. Với đầu vào `"0"` hoặc `"-2"`, cấu hình `throwExceptionOnRejection(true)` khiến yêu cầu bị từ chối bằng lỗi thay vì đi tiếp. Nếu filter chỉ loại bỏ message, caller đang cần phản hồi sẽ không có kết quả thành công từ nhánh đó. Xem [Filter](https://docs.spring.io/spring-integration/reference/filter.html).

## 5. Hợp đồng dữ liệu trên từng đoạn flow

Generic của các lambda giúp viết code đúng kiểu, nhưng toàn bộ `IntegrationFlow` không phải một pipeline generic được compiler chứng minh xuyên suốt. Channel có thể nhận message từ nhiều nguồn. Vì vậy, mỗi ranh giới vẫn cần hợp đồng về kiểu payload, headers bắt buộc và hành vi với dữ liệu sai.

Trong ví dụ:

- Gateway nhận chuỗi số nguyên, có thể có khoảng trắng ở hai đầu.
- Transformer chuẩn hóa trước khi parse.
- `"abc"`, `"1.5"` hoặc số vượt phạm vi `Integer` không qua được bước parse.
- Số lượng không dương bị filter từ chối.
- Mọi số lượng hợp lệ đi tới handler tạo `BigDecimal`.

Nếu nghiệp vụ yêu cầu số lượng tối đa, đó phải là điều kiện được bổ sung rõ ràng; ví dụ hiện tại chỉ kiểm tra lớn hơn 0.

Một `Message` gồm payload và headers. Cấu trúc headers không cho phép sửa trực tiếp qua `put(...)`; tính bất biến của vỏ message cũng không làm cho một đối tượng payload tùy ý trở thành bất biến. Khi tự tạo message thay thế, cần giữ metadata cần thiết cho đường trả lời và theo dõi. Xem [Message](https://docs.spring.io/spring-integration/reference/message.html).

Đừng dùng `message.getHeaders().getId()` làm mã nghiệp vụ cố định xuyên suốt phép biến đổi. Ví dụ báo giá có thể dùng header riêng `quoteRequestId` để theo dõi yêu cầu, còn `replyChannel` biểu thị nơi gửi phản hồi.

## 6. Những cách chọn điểm vào

### 6.1. Nhận message trên channel có sẵn

Ví dụ chính dùng:

~~~java
IntegrationFlow.from("quote.input")
~~~

Cách này phù hợp khi một gateway, flow khác hoặc producer nội bộ đã biết channel cần gửi. Đặt tên channel theo hợp đồng nghiệp vụ giúp kết nối các phần mà không phụ thuộc tên bean flow.

### 6.2. Để DSL tạo gateway từ interface

Một biến thể độc lập có thể bắt đầu từ interface:

~~~java
@Bean
IntegrationFlow inlineQuoteFlow() {
    return IntegrationFlow.from(
                    QuoteGateway.class,
                    gateway -> gateway.beanName("inlineQuoteGateway"))
            .<String, String>transform(String::trim)
            .<String, Integer>transform(Integer::valueOf)
            .<Integer>filter(
                    quantity -> quantity > 0,
                    endpoint -> endpoint.throwExceptionOnRejection(true))
            .handle(
                    Integer.class,
                    (quantity, headers) ->
                            new BigDecimal("120000")
                                    .multiply(BigDecimal.valueOf(quantity)))
            .get();
}
~~~

Các kiểu ở đây là `IntegrationFlow`, `BigDecimal` và `QuoteGateway` đã dùng ở ví dụ chính. Bean này đặt trong một cấu hình thay thế có `@EnableIntegration` và không import gateway thêm lần nữa.

Với dạng `from(QuoteGateway.class, ...)`, DSL tạo gateway và channel nội bộ nối vào bước đầu tiên. Request channel trên annotation của interface được thay bằng channel nội bộ đó. Không dùng biến thể này đồng thời với cách đăng ký gateway ở mục 4. Xem [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/dsl/integration-flow-as-gateway.html).

### 6.3. Tạo message từ nguồn polling

Một flow có thể chủ động lấy dữ liệu từ `Supplier`:

~~~java
@Bean
IntegrationFlow heartbeatFlow() {
    return IntegrationFlow.fromSupplier(
                    () -> "heartbeat",
                    source -> source.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))
                                    .maxMessagesPerPoll(1)))
            .handle(message -> {
                System.out.println(message.getPayload());
            })
            .get();
}
~~~

Đoạn này cần thêm import `java.time.Duration` và `org.springframework.integration.dsl.Pollers`, đặt trong cấu hình có `@EnableIntegration`.

Nguồn được poll theo lịch; kết quả supplier được bọc thành message nếu chưa phải message. Handler cuối chỉ tiêu thụ, nên flow này dùng giao tiếp một chiều. Xem [Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html).

Đây là nguồn phát theo lịch, khác với việc một caller gọi gateway và chờ báo giá.

## 7. Channel quyết định cách thực thi

Java DSL không tự biến mọi bước thành bất đồng bộ. Việc đổi loại channel có thể thay đổi thread xử lý, thời điểm producer được trả quyền điều khiển và cách tiếp nhận lỗi.

| Loại channel | Đặc điểm cần cân nhắc |
| --- | --- |
| `DirectChannel` | Gọi một subscriber trên thread gửi message |
| `QueueChannel` | Lưu message để consumer lấy ra; cần cơ chế nhận |
| `ExecutorChannel` | Chuyển việc dispatch cho executor; hành vi còn phụ thuộc executor |
| `PublishSubscribeChannel` | Phát đến các subscriber; có thể cấu hình executor |

Một `QueueChannel` thông thường dùng bộ nhớ không phải kho lưu bền vững. Việc xếp hàng và việc xử lý thành công là hai thời điểm khác nhau. Bounded queue còn đặt ra khả năng gửi bị chặn khi đầy. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 7.1. Poller thuộc consumer của queue

Ví dụ độc lập dưới đây nhận số nguyên qua queue rồi nhân đôi:

~~~java
package example.integration;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class QueuedNumberConfiguration {

    @Bean(name = "numbers.input")
    public QueueChannel numbersInput() {
        return new QueueChannel(100);
    }

    @Bean(name = "numbers.output")
    public QueueChannel numbersOutput() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow numberFlow(
            @Qualifier("numbers.input") QueueChannel input,
            @Qualifier("numbers.output") QueueChannel output) {

        return IntegrationFlow.from(input)
                .handle(
                        Integer.class,
                        (number, headers) -> number * 2,
                        endpoint -> endpoint
                                .id("numbers.double")
                                .poller(Pollers
                                        .fixedDelay(Duration.ofMillis(100))
                                        .maxMessagesPerPoll(5)))
                .channel(output)
                .get();
    }
}
~~~

Poller được cấu hình trên endpoint `numbers.double` vì endpoint này phải lấy message từ `numbers.input`. Queue đầu ra dành cho bên nhận chủ động gọi `receive(...)`; không cần một endpoint polling nữa nếu chính caller lấy kết quả.

`fixedDelay` cấu hình lịch polling, còn `maxMessagesPerPoll` giới hạn số lần lấy/xử lý message trong một lượt poll, không phải số thread. Hạ tầng DSL cung cấp `Pollers` để cấu hình metadata cho polling endpoint. Xem [Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html).

Ở một đoạn thử nghiệm có `context` được tạo từ `QueuedNumberConfiguration`:

~~~java
QueueChannel input = context.getBean(
        "numbers.input", QueueChannel.class);
QueueChannel output = context.getBean(
        "numbers.output", QueueChannel.class);

boolean accepted = input.send(
        new org.springframework.messaging.support.GenericMessage<>(21),
        1000);

org.springframework.messaging.Message<?> result = output.receive(2000);
// Kỳ vọng: accepted == true; result khác null; payload == 42.
~~~

Không diễn giải `accepted == true` thành bảo đảm đã có kết quả `42`. Khi nhận kết quả, cần kiểm tra `null` và có timeout phù hợp.

## 8. Kết thúc flow, phản hồi và lỗi

### 8.1. Điểm cuối phải phù hợp với hợp đồng gọi

Flow báo giá kết thúc bằng handler trả giá trị và không chỉ định output channel, nên phản hồi có thể quay về `replyChannel` của request. Gateway thiết lập đường trả lời để lấy kết quả.

Nếu thay handler cuối bằng một consumer chỉ ghi log, sẽ không còn kết quả `BigDecimal` cho `quote(...)`. Tương tự, việc thêm output channel tường minh có nghĩa kết quả đi tới channel đó; cần thiết kế đường quay về gateway nếu vẫn giữ hợp đồng request–reply.

Một handler trả `null` cũng có thể làm mất phản hồi. `requiresReply(true)` ở ví dụ chính giúp phát hiện trường hợp handler báo giá không tạo reply. Nó không buộc filter đã loại message phải tạo kết quả.

### 8.2. Timeout không ngắt handler đồng bộ

`requestTimeout` áp dụng khi gửi vào channel có khả năng chặn; `replyTimeout` giới hạn giai đoạn chờ reply. Nếu toàn bộ xử lý đang chạy trên thread caller qua direct channel, timeout chờ reply không ngắt handler chậm. Việc gọi HTTP hoặc cơ sở dữ liệu vẫn cần timeout tại client tương ứng. Xem [Gateway Behavior When No Response Arrives](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

Với báo giá, hãy chọn rõ kết quả nghiệp vụ cho từng tình huống: trả tổng tiền, trả phản hồi từ chối theo mô hình dữ liệu, hoặc báo lỗi. Đừng dùng việc hết thời gian chờ để biểu diễn một quy tắc như “số lượng phải lớn hơn 0”.

### 8.3. Đường lỗi phụ thuộc ranh giới thực thi

Trong cấu hình báo giá đồng bộ, lỗi có thể truyền ngược qua lời gọi gateway. Khi chuyển xử lý sang task bất đồng bộ hoặc scheduled poller, không thể dựa vào cùng call stack của sender.

Hạ tầng xử lý lỗi của Spring Integration có thể gửi `ErrorMessage` tới channel được chỉ định bởi header `errorChannel` hoặc channel lỗi toàn cục. Chỉ khai báo một flow nghe `errorChannel` không có nghĩa mọi exception đồng bộ sẽ tự đi vào đó. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Đối với ví dụ này, nên phân biệt:

| Tình huống | Điểm phát sinh | Cách diễn giải |
| --- | --- | --- |
| `"abc"` | `quote.parse` | Sai định dạng đầu vào |
| `"0"` | `quote.positiveQuantity` | Vi phạm điều kiện số lượng |
| Handler không trả kết quả | `quote.calculateTotal` | Vi phạm hợp đồng phản hồi |
| Lỗi trong flow dùng queue | Task nhận message | Cần quan sát đường lỗi của task |

Tên endpoint giúp liên hệ lỗi với bước xử lý. Khi bổ sung retry, chỉ áp dụng cho lỗi có khả năng hồi phục và cân nhắc tác dụng phụ; parse lại cùng chuỗi `"abc"` không làm dữ liệu hợp lệ hơn.

## 9. Kiểm thử hợp đồng của flow

Các kiểm thử sau dùng Spring context thật với cấu hình báo giá và không kết nối dịch vụ bên ngoài. Chúng kiểm tra kết quả, từ chối dữ liệu và bảo toàn header nghiệp vụ.

Spring Integration hỗ trợ kiểm thử trên nền Spring Test; `spring-integration-test` cung cấp thêm công cụ khi cần thay thế hoặc điều khiển các thành phần trong flow. Ví dụ nhỏ này chỉ cần Spring Test và JUnit Jupiter. Xem [Testing Support](https://docs.spring.io/spring-integration/reference/testing.html).

File `QuoteFlowTest.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuoteFlowConfiguration.class)
class QuoteFlowTest {

    @Autowired
    private QuoteGateway gateway;

    @Autowired
    @Qualifier("quote.input")
    private MessageChannel input;

    @Test
    void calculatesTotalAfterTrimming() {
        assertEquals(
                new BigDecimal("360000"),
                gateway.quote(" 3 "));
    }

    @Test
    void rejectsNonPositiveQuantity() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> gateway.quote("0"));

        assertTrue(hasCause(error, MessageRejectedException.class));
    }

    @Test
    void rejectsInvalidNumber() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> gateway.quote("abc"));

        assertTrue(hasCause(error, NumberFormatException.class));
    }

    @Test
    void repliesToSuppliedChannelAndPreservesBusinessHeader() {
        QueueChannel replies = new QueueChannel(1);

        Message<String> request = MessageBuilder
                .withPayload(" 2 ")
                .setHeader("quoteRequestId", "Q-1001")
                .setReplyChannel(replies)
                .build();

        assertTrue(input.send(request, 1000));

        Message<?> reply = replies.receive(1000);
        assertNotNull(reply);
        assertEquals(new BigDecimal("240000"), reply.getPayload());
        assertEquals("Q-1001", reply.getHeaders().get("quoteRequestId"));
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Hai test lỗi kiểm tra chuỗi nguyên nhân vì lớp bọc exception có thể khác giữa điểm gọi và handler. Chúng vẫn yêu cầu đúng loại nguyên nhân, thay vì chỉ chấp nhận bất kỳ lỗi nào.

Test cuối gửi message trực tiếp vào channel, nhờ đó kiểm tra được cả metadata. `QueueChannel` dùng làm nơi hứng reply trong test không cần poller: test tự gọi `receive(1000)`. Timeout hữu hạn giúp test kết thúc rõ ràng nếu đường trả lời bị hỏng.

Đây là mã kiểm thử để người học thực hành; bài viết không kèm kết quả biên dịch hay thực thi trong một dự án mẫu.

## 10. Tổ chức và quản lý flow

### 10.1. Tách cấu hình kết nối và xử lý nghiệp vụ

Khi phép tính phát triển thành nghiệp vụ lớn, chuyển nó vào service riêng và inject service vào phương thức `@Bean`. Ví dụ, với một bean `pricingService` có phương thức `calculate(Integer quantity)` trả `BigDecimal`:

~~~java
.handle(
        pricingService,
        "calculate",
        endpoint -> endpoint
                .id("quote.calculateTotal")
                .requiresReply(true))
~~~

Đây là đoạn thay cho bước tính tiền của flow chính. Flow diễn tả thứ tự chuẩn hóa, kiểm tra và gọi service; service chứa quy tắc tính giá. Cách tách này cho phép kiểm thử nghiệp vụ độc lập và thay cách kết nối mà không dồn mọi xử lý vào một lambda dài.

Đặt channel được chia sẻ thành bean riêng và inject vào các flow cần dùng. Tránh tạo nhiều đối tượng channel khác nhau cùng được hiểu là một điểm nối chung.

### 10.2. Phân biệt nối tiếp và gọi flow con có phản hồi

`channel("another.input")` chuyển message tới một channel. Khi cần gọi một flow con, chờ kết quả rồi tiếp tục bước kế tiếp, có thể dùng `gateway("another.input")`. Đây là operator bên trong DSL, khác với interface gateway mà ứng dụng gọi vào. Xem [Operator gateway()](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html).

Trước khi tái sử dụng flow con, xác định nó có luôn trả lời hay không. Một nhánh chỉ ghi log không đáp ứng hợp đồng chờ kết quả của caller.

### 10.3. Lifecycle và đăng ký động

Flow khai báo bằng `@Bean` được Spring quản lý. Các thành phần liên quan hỗ trợ lifecycle; việc start/stop flow được ủy quyền tới các thành phần đó. Không gọi lại phương thức tạo flow để “gửi thêm một message”. Xem [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

Nếu ứng dụng thực sự phải tạo hoặc gỡ flow khi đang chạy, `IntegrationFlowContext` cung cấp cơ chế đăng ký và quản lý. Đăng ký động cần tên rõ ràng và giải phóng registration khi không còn dùng. Ví dụ báo giá cố định chưa cần cơ chế này. Xem [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html).

## 11. Những lỗi cần nhận ra khi đọc IntegrationFlow

| Biểu hiện | Điều cần xem lại |
| --- | --- |
| Có builder nhưng không nhận được message | Flow đã được đăng ký vào context và hạ tầng integration đã bật chưa |
| Gửi tới tên bean `quoteFlow` | Producer cần gửi tới channel `quote.input` |
| Gateway chờ rồi không có kết quả | Có filter loại message, handler trả `null` hoặc nhánh không tạo reply không |
| Thay direct channel bằng queue rồi flow không chạy | Consumer đầu tiên sau queue đã có poller hoặc cơ chế nhận phù hợp chưa |
| Gửi vào queue thành công nhưng nghiệp vụ thất bại | Đã quan sát kết quả và đường lỗi của consumer chưa |
| Thêm flow bắt lỗi toàn cục nhưng caller vẫn nhận exception | Lỗi có đang phát sinh đồng bộ trên thread caller không |
| Payload sai kiểu ở giữa flow | Hợp đồng tại đầu vào và mỗi phép biến đổi đã được xác định rõ chưa |

Khi mở rộng ví dụ sang đơn hàng thực, có thể thêm router để chọn đường xử lý hoặc splitter–aggregator để tính theo từng dòng hàng. Mỗi bổ sung cần mô tả được đầu vào, đầu ra, nhánh bị từ chối và điều kiện phản hồi. Đó là cơ sở để dùng Java DSL thiết kế các mẫu tích hợp trong module Spring Integration Core mà vẫn giữ luồng dễ đọc và kiểm thử.
