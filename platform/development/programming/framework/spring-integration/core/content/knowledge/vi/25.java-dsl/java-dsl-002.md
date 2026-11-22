# IntegrationFlows và Java DSL

## 1. Mục tiêu và phạm vi

Trong module `SPRING_INTEGRATION_CORE`, Java DSL là cách dùng mã Java để mô tả đường đi của thông điệp qua `MessageChannel` và các endpoint. Bài học thuộc chương **Java DSL**, tập trung vào việc đọc, xây dựng và kiểm thử một `IntegrationFlow` từ đầu vào đến kết quả hoặc lỗi.

Sau bài học, bạn có thể:

- Phân biệt factory `IntegrationFlows` trong tài liệu cũ với interface `IntegrationFlow` trong API mới.
- Giải thích chuỗi `from → transform → filter → route → handle` tạo ra thành phần nào.
- Chọn đầu vào bằng channel, gateway hoặc nguồn được polling.
- Thiết kế hợp đồng payload, header và phản hồi giữa các bước.
- Ghép subflow, nhận biết ranh giới thread và xử lý thông điệp bị từ chối.
- Áp dụng `split`, `aggregate` và viết kiểm thử hành vi cho flow.

Bạn nên biết Java lambda, Spring `@Configuration`, `@Bean` và khái niệm message gồm payload cùng headers. Ví dụ chính dùng Java 17 và API Spring Integration 6.5.x làm mốc minh họa; đây là mốc của bài học, không phải tuyên bố phiên bản mới nhất. Khi đưa vào dự án, dùng bộ phiên bản Spring Boot/Spring Integration tương thích do dự án quản lý.

## 2. IntegrationFlows và IntegrationFlow khác nhau thế nào?

### 2.1. Cách đọc ví dụ cũ

Bạn có thể gặp cấu hình:

~~~java
// Cú pháp lịch sử; phụ thuộc phiên bản còn cung cấp IntegrationFlows.
return IntegrationFlows.from("orders.input")
        .transform(String.class, String::trim)
        .channel("orders.output")
        .get();
~~~

Ở đây `IntegrationFlows` là lớp factory cung cấp các phương thức bắt đầu builder; giá trị cuối cùng có kiểu `IntegrationFlow`.

Từ Spring Integration 6.0, `IntegrationFlows` được đánh dấu deprecated để chuyển các factory method sang chính interface `IntegrationFlow`. Với mã mới theo API được dùng trong bài, viết `IntegrationFlow.from(...)`. Chỉ thay tên factory chưa đảm bảo một ứng dụng cũ đã được migrate đầy đủ; cần kiểm tra các thay đổi khác của phiên bản đích. Xem [thay đổi giữa 5.5 và 6.0](https://docs.spring.io/spring-integration/reference/changes-5.5-6.0.html) và [Javadoc IntegrationFlows 6.0.3](https://docs.spring.io/spring-integration/docs/6.0.3/api/org/springframework/integration/dsl/IntegrationFlows.html).

~~~java
// Cú pháp dùng trong bài.
return IntegrationFlow.from("orders.input")
        .transform(String.class, String::trim)
        .channel("orders.output")
        .get();
~~~

Hai đoạn trên minh họa cách khai báo, chưa có consumer cho `orders.output`. Muốn gửi và nhận kết quả thực tế, cần nối channel đó tới endpoint khác hoặc khai báo nó là `QueueChannel` để đọc bằng `receive(...)`.

| Tên | Vai trò |
| --- | --- |
| `IntegrationFlows` | Factory trong API cũ; cần đối chiếu phiên bản trước khi dùng |
| `IntegrationFlow` | Hợp đồng mô tả flow; đồng thời có các static factory method trong API mới |
| `IntegrationFlowBuilder` | Builder thu thập các channel, handler, endpoint và cấu hình liên quan |
| Java DSL | Cách diễn đạt topology bằng Java, fluent API và lambda |

### 2.2. DSL mô tả topology khi khởi tạo

Phương thức `@Bean` xây dựng một mô tả flow khi Spring tạo application context. Spring Integration xử lý mô tả này và đăng ký các thành phần thực vào context. Khi có message, channel và endpoint thực thi công việc; framework không gọi lại toàn bộ chuỗi builder cho mỗi message. Cơ chế này được mô tả trong [Java DSL reference](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

~~~mermaid
flowchart LR
    A["@Bean tạo IntegrationFlow"] --> B["Spring đăng ký channel và endpoint"]
    B --> C["Context khởi động"]
    C --> D["Message đến channel"]
    D --> E["Endpoint xử lý message"]
~~~

Ví dụ:

~~~java
@Bean
IntegrationFlow textFlow() {
    System.out.println("Đang khai báo flow");

    return IntegrationFlow.from("text.input")
            .transform(String.class, text -> {
                System.out.println("Đang xử lý một payload");
                return text.trim();
            })
            .channel("text.output")
            .get();
}
~~~

Dòng đầu chạy khi bean được tạo. Lambda bên trong `transform` chạy khi endpoint nhận message. Trong ví dụ này, `get()` hoàn tất builder để trả về đối tượng flow; nó không gửi message, không chờ phản hồi và không lấy một phần tử từ nguồn.

## 3. Đọc chuỗi DSL theo hợp đồng thông điệp

### 3.1. Các động từ chính

| DSL | Ý nghĩa trong flow | Câu hỏi cần trả lời khi thiết kế |
| --- | --- | --- |
| `from(...)` | Xác định nơi flow bắt đầu | Ai tạo message và gửi vào đâu? |
| `channel(...)` | Nối tới một channel | Có đổi thread hoặc lưu đệm không? |
| `transform(...)` | Biến đổi dữ liệu | Payload sau bước này có kiểu gì? |
| `filter(...)` | Chấp nhận hoặc từ chối message | Message bị từ chối đi đâu? |
| `handle(...)` | Gọi handler hoặc dịch vụ nghiệp vụ | Có tạo phản hồi không? |
| `route(...)` | Chọn đường đi | Các khóa định tuyến đã được xử lý đủ chưa? |
| `split(...)` | Chia một đầu vào thành nhiều message | Mỗi phần có thông tin correlation/sequence nào? |
| `aggregate(...)` | Gom nhóm message thành kết quả | Nhóm nào được gom và khi nào được nhả? |
| `bridge(...)` | Chuyển tiếp giữa các channel | Hai đoạn flow được nối theo cách nào? |
| `get()` | Kết thúc quá trình xây dựng bằng builder | Đã đăng ký kết quả làm bean chưa? |

Các động từ được ánh xạ tới endpoint của Spring Integration, chẳng hạn transformer, filter và service activator. Xem [DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

Một flow nên có hợp đồng rõ ràng cho từng cạnh:

~~~text
RawOrder
  -> Order đã chuẩn hóa
  -> Order có amount > 0
  -> Receipt theo nhánh ưu tiên/thông thường
  -> String phản hồi
~~~

Tên flow không thể thay thế hợp đồng này. Nếu một bước đổi payload từ `Order` sang `Receipt` thì bước kế tiếp phải nhận `Receipt`, dù tên channel vẫn chứa từ “orders”.

### 3.2. Lambda nhận payload hay Message?

Trong nhiều overload, đối số của lambda là **payload**:

~~~java
.transform(String.class, text -> text.trim())
.handle(String.class, (payload, headers) -> payload.toUpperCase(Locale.ROOT))
~~~

Ở dạng `handle` hai đối số, tham số thứ hai cung cấp headers. Muốn dùng đoạn trên cần import `java.util.Locale`.

Không nên giả định rằng viết generic `Message<?>` là đủ để yêu cầu framework truyền toàn bộ message:

~~~java
// Tránh: framework có thể vẫn truyền payload vào lambda.
.<Message<?>, String>transform(message ->
        message.getPayload().toString())
~~~

Nếu cần message đầy đủ, chọn overload có token lớp phù hợp, ví dụ `transform(Message.class, message -> ...)`, hoặc dùng handler có chữ ký thể hiện rõ hợp đồng nhận message. Lưu ý khác biệt overload và type erasure được giải thích trong [DSL Basics, mục lambda và Message](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

Khi tự dựng một `Message` mới, cần chủ động bảo toàn các header phục vụ flow. Đặc biệt, làm mất `replyChannel` có thể khiến gateway không nhận được kết quả; làm mất correlation/sequence có thể khiến aggregator không gom đúng nhóm.

## 4. Chuẩn bị dependency và cách đăng ký bean

Trong ứng dụng Spring Boot đã quản lý phiên bản, dependency tối thiểu thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Nếu không dùng Spring Boot, cần `org.springframework.integration:spring-integration-core` và cấu hình Spring phù hợp. Java DSL nằm trong Spring Integration core ở mốc phiên bản của bài; không cần thêm artifact Java DSL cũ chỉ vì thấy nó trong một hướng dẫn lịch sử.

Ví dụ kiểm thử bên dưới dùng JUnit Jupiter, `spring-test` và các assertion của JUnit. Trong dự án Boot, có thể dùng `spring-boot-starter-test` ở scope `test`. `spring-integration-test` là dependency bổ sung khi cần các tiện ích như mock integration endpoint, không bắt buộc cho ví dụ kiểm thử gateway đơn giản này.

Phương thức khai báo flow phải được Spring quản lý:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class ExampleConfiguration {

    @Bean
    IntegrationFlow exampleFlow() {
        return IntegrationFlow.from("example.input")
                .transform(String.class, String::trim)
                .channel("example.output")
                .get();
    }
}
~~~

`@EnableIntegration` thể hiện cấu hình hạ tầng rõ ràng khi học với Spring thuần. Trong ứng dụng Boot, cần hiểu phần hạ tầng nào đã được auto-configuration cung cấp.

Tạo builder trong một biến Java thông thường rồi không đưa nó vào cơ chế đăng ký flow sẽ không tạo ra pipeline được Spring quản lý. Tương tự, đừng gọi `getObject()` thủ công trên các `IntegrationComponentSpec` trong phương thức `@Bean`; để container quản lý các spec đó theo vòng đời `FactoryBean`. Khi chia sẻ channel giữa nhiều flow, cách dễ theo dõi là khai báo channel thành bean riêng và inject nó.

## 5. Ví dụ hoàn chỉnh: tiếp nhận và phân loại đơn hàng

### 5.1. Yêu cầu nghiệp vụ

Ứng dụng nhận một yêu cầu gồm mã đơn, cờ ưu tiên và số tiền ở dạng chuỗi. Luồng cần:

1. Bỏ khoảng trắng thừa, chuyển tiền sang `BigDecimal`.
2. Từ chối số tiền không dương.
3. Gửi đơn vào nhánh `PRIORITY` hoặc `STANDARD`.
4. Tạo biên nhận, định dạng và trả về cho bên gọi.

Ví dụ này chỉ phân loại và tạo biên nhận trong bộ nhớ. Nó chưa tạo đơn ở cơ sở dữ liệu, chưa gọi nhà vận chuyển và chưa đảm bảo chống xử lý trùng.

~~~mermaid
flowchart LR
    A["OrderGateway.submit"] --> B["RawOrder -> Order"]
    B --> C{"amount > 0?"}
    C -->|Không| X["MessageRejectedException"]
    C -->|Có| D{"priority?"}
    D -->|true| E["Receipt PRIORITY"]
    D -->|false| F["Receipt STANDARD"]
    E --> G["Định dạng String"]
    F --> G
    G --> H["Phản hồi gateway"]
~~~

### 5.2. Cấu hình và kiểu dữ liệu

Đặt đoạn mã sau trong `OrderFlowConfiguration.java`, package `example.integration`:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.handler.annotation.Header;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderFlowConfiguration {

    public record RawOrder(
            String id,
            boolean priority,
            String amount) {
    }

    public record Order(
            String id,
            boolean priority,
            BigDecimal amount) {
    }

    public record Receipt(
            String orderId,
            String lane,
            BigDecimal amount) {
    }

    public interface OrderGateway {
        String submit(
                RawOrder command,
                @Header("correlationKey") String correlationKey);
    }

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow
                .from(OrderGateway.class, gateway -> gateway
                        .beanName("orderGateway")
                        .replyTimeout(2_000L))
                .transform(
                        RawOrder.class,
                        OrderFlowConfiguration::normalize,
                        endpoint -> endpoint.id("orders.normalize"))
                .channel("orders.normalized")
                .filter(
                        Order.class,
                        order -> order.amount().signum() > 0,
                        filter -> filter
                                .id("orders.positiveAmount")
                                .throwExceptionOnRejection(true))
                .<Order, Boolean>route(
                        Order::priority,
                        router -> router
                                .subFlowMapping(true, branch -> branch
                                        .handle(Order.class, (order, headers) ->
                                                new Receipt(
                                                        order.id(),
                                                        "PRIORITY",
                                                        order.amount())))
                                .subFlowMapping(false, branch -> branch
                                        .handle(Order.class, (order, headers) ->
                                                new Receipt(
                                                        order.id(),
                                                        "STANDARD",
                                                        order.amount()))))
                .transform(
                        Receipt.class,
                        receipt -> receipt.orderId()
                                + "|" + receipt.lane()
                                + "|" + receipt.amount().toPlainString(),
                        endpoint -> endpoint.id("orders.formatReceipt"))
                .get();
    }

    static Order normalize(RawOrder raw) {
        Objects.requireNonNull(raw, "command is required");

        String id = Objects.requireNonNull(
                raw.id(), "id is required").trim();

        if (id.isEmpty()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        BigDecimal amount = new BigDecimal(
                Objects.requireNonNull(
                        raw.amount(), "amount is required").trim());

        return new Order(id, raw.priority(), amount);
    }
}
~~~

Gateway proxy được tạo bởi `IntegrationFlow.from(OrderGateway.class, ...)`. Vì vậy, ví dụ này không cần triển khai interface thủ công và không cần scan thêm cùng interface bằng `@IntegrationComponentScan`. Khả năng bắt đầu flow bằng interface và đặt tên proxy được mô tả trong [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

`replyTimeout(2_000L)` cấu hình thời gian chờ reply của gateway. Nó không phải giới hạn tổng thời gian chạy của mọi thao tác trong flow: nếu một handler đồng bộ giữ thread của caller quá lâu thì timeout này không tự ngắt handler. Các tùy chọn builder nằm trong [Javadoc GatewayProxySpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/GatewayProxySpec.html).

### 5.3. Gọi flow bằng Java thuần

Có thể chạy cấu hình trên bằng một lớp riêng:

~~~java
package example.integration;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class OrderFlowDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            var gateway = context.getBean(
                    "orderGateway",
                    OrderFlowConfiguration.OrderGateway.class);

            String result = gateway.submit(
                    new OrderFlowConfiguration.RawOrder(
                            " O-100 ", true, " 125.50 "),
                    "request-100");

            System.out.println(result);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
O-100|PRIORITY|125.50
~~~

Đóng context bằng `try-with-resources` giúp kết thúc vòng đời các thành phần khi demo xong.

### 5.4. Theo dõi message qua từng bước

| Vị trí | Payload | Header nghiệp vụ cần giữ |
| --- | --- | --- |
| Gateway tiếp nhận | `RawOrder(" O-100 ", true, " 125.50 ")` | `correlationKey=request-100` |
| Sau normalize | `Order("O-100", true, 125.50)` | `correlationKey` |
| Sau filter | Vẫn là `Order` | `correlationKey` |
| Sau nhánh priority | `Receipt("O-100", "PRIORITY", 125.50)` | `correlationKey` |
| Sau formatter | `"O-100\|PRIORITY\|125.50"` | Header phục vụ trả lời gateway |

`correlationKey` trong ví dụ là header ứng dụng để lần theo một yêu cầu. Nó không tự thay thế `correlationId` mà splitter/aggregator sử dụng.

Gateway che giấu API messaging khỏi code gọi và thiết lập thông tin trả lời để nhận kết quả. Khi endpoint cuối có kết quả nhưng không có output channel khai báo riêng, nó có thể dùng `replyChannel` từ message. Xem [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html) và [Service Activator](https://docs.spring.io/spring-integration/reference/6.5/service-activator.html).

## 6. Filter, router và hợp đồng phản hồi

### 6.1. Filter từ chối không đồng nghĩa trả về false

Trong ví dụ, predicate trả `true` thì message đi tiếp. Nếu nó trả `false`, cấu hình `throwExceptionOnRejection(true)` khiến flow phát sinh `MessageRejectedException`.

Nếu bỏ tùy chọn này và không cấu hình discard, message bị loại khỏi đường xử lý chính; gateway có thể chờ đến hết timeout vì không có phản hồi. Nếu nghiệp vụ muốn trả kết quả “đơn không hợp lệ”, hãy thiết kế một nhánh tạo phản hồi có kiểu rõ ràng, chẳng hạn router chuyển tới handler tạo `RejectedOrder`. `discardChannel`/`discardFlow` cần được thiết kế theo đích xử lý bị loại, không nên mặc nhiên xem chúng là cơ chế trả lỗi cho caller. Xem [Filter](https://docs.spring.io/spring-integration/reference/6.5/filter.html).

Với ví dụ hiện tại:

| Đầu vào | Bước quyết định | Kết quả |
| --- | --- | --- |
| `amount="100"` | Filter chấp nhận | Có biên nhận |
| `amount="0"` | Filter từ chối | Exception |
| `amount="-10"` | Filter từ chối | Exception |
| `amount="abc"` | Normalize thất bại | Lỗi biến đổi trước khi đến filter |

Phân biệt lỗi parse và điều kiện không thỏa giúp đặt đúng thông báo, metric và quy tắc retry. Gửi lại nguyên chuỗi `"abc"` thường không làm parse thành công.

### 6.2. Subflow inline quay lại bước chung

Hai `subFlowMapping` trong ví dụ tạo hai nhánh trả `Receipt`, sau đó đều chạy formatter đứng sau `route`.

Không nên thay một nhánh thành:

~~~java
.handle(message -> System.out.println(message.getPayload()))
~~~

rồi vẫn kỳ vọng có `Receipt` để formatter xử lý. Handler một chiều như vậy chỉ tiêu thụ message.

`channelMapping` hướng message tới channel đích; nó không tự tạo cùng hợp đồng quay về như subflow inline. Khi gọi một flow riêng và cần kết quả để tiếp tục flow hiện tại, có thể dùng `gateway(...)` để biểu đạt request-reply. Nếu đã quyết định gửi một chiều thì phải thiết kế đường kết thúc tương ứng. Những khác biệt này được mô tả trong [Sub-flows support](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-subflows.html).

### 6.3. handle có trả kết quả hay chỉ thực hiện tác vụ?

~~~java
// Có kết quả để bước sau tiếp tục.
.handle(Order.class, (order, headers) ->
        new Receipt(order.id(), "STANDARD", order.amount()))

// Một chiều: phù hợp khi kết thúc một nhánh ghi nhận sự kiện.
.handle(message -> System.out.println(message.getPayload()))
~~~

Trong ứng dụng thực, nên đưa việc lưu đơn hoặc gọi dịch vụ vào bean nghiệp vụ, rồi để DSL làm nhiệm vụ nối các bước. Khi handler trả `null` hoặc có kiểu trả về `void`, không có reply để truyền tiếp; nếu endpoint bắt buộc phải trả lời thì cần cấu hình yêu cầu reply thích hợp. Xem [Service Activator](https://docs.spring.io/spring-integration/reference/6.5/service-activator.html).

## 7. Chọn cách bắt đầu flow

### 7.1. Bắt đầu từ một channel

~~~java
@Bean("text.results")
QueueChannel textResults() {
    return new QueueChannel(20);
}

@Bean
IntegrationFlow textFlow(
        @Qualifier("text.results") QueueChannel results) {

    return IntegrationFlow.from("text.input")
            .transform(String.class, String::trim)
            .channel(results)
            .get();
}
~~~

Đây là đoạn cấu hình bổ sung độc lập, cần các import `Bean`, `Qualifier`, `QueueChannel` và `IntegrationFlow` tương ứng. `from("text.input")` dùng channel đã có theo tên đó, hoặc để DSL tạo channel nếu chưa có.

Bên gửi dùng `MessageChannel`, bên đọc kết quả dùng `QueueChannel`:

~~~java
MessageChannel input = context.getBean("text.input", MessageChannel.class);
QueueChannel results = context.getBean("text.results", QueueChannel.class);

boolean sent = input.send(new GenericMessage<>("  spring integration  "), 1_000);
if (!sent) {
    throw new IllegalStateException("Không gửi được message");
}

Message<?> reply = results.receive(1_000);
if (reply == null) {
    throw new IllegalStateException("Không nhận được kết quả");
}

System.out.println(reply.getPayload());
~~~

Đoạn gọi cần thêm các import `org.springframework.messaging.Message`, `MessageChannel` và `org.springframework.messaging.support.GenericMessage`. Biến `context` là application context đã nạp cấu hình.

Một lợi ích của channel có tên là nhiều flow có thể nối vào cùng một hợp đồng. Tuy nhiên, đừng khai báo hai đối tượng channel inline khác nhau rồi đặt cùng một tên với kỳ vọng chúng là một channel. Với thành phần được chia sẻ, khai báo bean một lần rồi inject hoặc tham chiếu bằng tên. Xem [Message Channels trong Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-channels.html).

### 7.2. Bắt đầu từ gateway

Dùng gateway khi code nghiệp vụ cần một phương thức có tên, tham số và kiểu trả về rõ ràng, như `OrderGateway.submit(...)`.

Hai cách cấu hình thường gặp:

| Cách | Phù hợp khi |
| --- | --- |
| `IntegrationFlow.from(MyGateway.class, ...)` | Muốn khai báo gateway cùng flow bằng DSL |
| `@MessagingGateway` + cơ chế đăng ký gateway + flow từ request channel | Muốn tách interface gateway khỏi flow theo channel đã thống nhất |

Chọn một cách đăng ký cho cùng gateway. Với `from(MyGateway.class)`, request channel được tạo để nối vào flow đó; không nên kỳ vọng một `requestChannel` ghi trên annotation sẽ điều hướng sang flow khác. Xem [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

### 7.3. Bắt đầu từ supplier được polling

Một nguồn chủ động phát tick có thể khai báo như sau:

~~~java
@Bean
IntegrationFlow heartbeatFlow() {
    return IntegrationFlow
            .fromSupplier(
                    () -> java.time.Instant.now().toString(),
                    source -> source.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)))
            .handle(message ->
                    System.out.println("heartbeat=" + message.getPayload()))
            .get();
}
~~~

Đoạn trên cần `org.springframework.integration.dsl.Pollers` và hạ tầng integration đã bật. Nó chạy lặp lại theo poller khi context hoạt động.

Poller ở đây thuộc endpoint lấy dữ liệu từ nguồn. `maxMessagesPerPoll(1)` giới hạn số lần lấy/phát trong một lượt polling; nó không giới hạn tổng số message suốt vòng đời ứng dụng.

Không phải mọi `from` đều cần poller: flow từ `DirectChannel` nhận message theo cơ chế subscription; nguồn polling và consumer đọc `PollableChannel` mới có nhu cầu polling tương ứng. Xem [Pollers](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-pollers.html).

## 8. Channel quyết định cách thực thi

Đặt các lời gọi DSL trên nhiều dòng không làm chúng chạy song song. Loại channel, executor và endpoint quyết định việc thực thi.

| Channel | Cách chuyển message | Hệ quả cần tính |
| --- | --- | --- |
| `DirectChannel` | Gọi subscriber trên thread gửi | Caller chịu thời gian xử lý downstream đồng bộ |
| `QueueChannel` | Lưu message để consumer lấy ra | Cần consumer/poller; có sức chứa và chờ đợi |
| `ExecutorChannel` | Dispatch qua executor | Có ranh giới thread theo cấu hình executor |
| `PublishSubscribeChannel` | Phát tới nhiều subscriber | Là broadcast; cần xem có executor hay không |

`DirectChannel` có ngữ nghĩa point-to-point. Nhiều consumer trên nó không có nghĩa mọi consumer đều nhận mỗi message. `PublishSubscribeChannel` phù hợp với mục tiêu broadcast. Queue mặc định lưu trong bộ nhớ nếu không gắn cơ chế lưu bền khác. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 8.1. Ví dụ consumer đọc queue

Đoạn cấu hình dưới đây là ví dụ độc lập; đặt các phương thức trong một class `@Configuration` đã bật `@EnableIntegration`:

~~~java
@Bean("tasks.input")
QueueChannel tasksInput() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow queuedTasksFlow(
        @Qualifier("tasks.input") QueueChannel input) {

    return IntegrationFlow.from(input)
            .handle(
                    String.class,
                    (payload, headers) -> {
                        if (payload.isBlank()) {
                            throw new IllegalArgumentException(
                                    "task must not be blank");
                        }

                        System.out.println("processed=" + payload);
                        return null; // Hợp đồng một chiều.
                    },
                    endpoint -> endpoint
                            .id("tasks.worker")
                            .poller(Pollers.fixedDelay(200)
                                    .maxMessagesPerPoll(10)
                                    .errorChannel("tasks.errors")))
            .get();
}

@Bean
IntegrationFlow taskErrorsFlow() {
    return IntegrationFlow.from("tasks.errors")
            .handle(message ->
                    System.err.println("task failed: " + message.getPayload()))
            .get();
}
~~~

Các import ngoài cấu hình cơ bản:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.Pollers;
~~~

Consumer `tasks.worker` có poller vì đầu vào là `QueueChannel`. `tasks.errors` được flow xử lý lỗi dùng làm input channel. Endpoint cuối của mỗi flow là một chiều nên không yêu cầu caller cung cấp reply channel.

Nếu bên gửi chỉ gọi `send(...)` vào `tasks.input` và nhận `true`, điều đó xác nhận gửi vào channel thành công. Việc worker hoàn thành hay thất bại xảy ra sau đó, không được chứng minh bằng giá trị `true` này.

### 8.2. Các quyết định khi thêm queue

Trước khi thay một channel trực tiếp bằng queue, hãy xác định:

1. Sức chứa phù hợp với tốc độ đến và tốc độ xử lý.
2. Thời gian chờ gửi khi queue đầy và hành vi khi hết thời gian.
3. Ai đọc queue, poller nào quản lý nhịp đọc.
4. Cách quan sát lỗi và backlog.
5. Yêu cầu lưu bền nếu process dừng.

Queue không tự tạo consumer. Poller cũng không tự tạo khả năng lưu bền. Nếu dữ liệu phải sống qua restart, cần chọn message store hoặc hạ tầng messaging tương ứng với yêu cầu.

Ranh giới executor/queue cũng đòi hỏi xem lại transaction và context gắn với thread. Không suy luận rằng transaction của caller sẽ tự bao phủ công việc chạy trên thread khác.

## 9. Kết hợp splitter và aggregator bằng DSL

### 9.1. Ví dụ xử lý một danh sách

Giả sử message chứa `List.of(1, 2, 3)`. Mỗi số cần nhân mười, rồi kết quả được gom lại.

~~~java
@Bean("batch.results")
QueueChannel batchResults() {
    return new QueueChannel(20);
}

@Bean
IntegrationFlow batchFlow(
        @Qualifier("batch.results") QueueChannel results) {

    return IntegrationFlow.from("batch.input")
            .split()
            .transform(Integer.class, value -> value * 10)
            .aggregate()
            .channel(results)
            .get();
}
~~~

Với đầu vào là một `List<Integer>` không rỗng, splitter mặc định tạo message cho từng phần tử và điền thông tin sequence/correlation. Aggregator có thể dùng các thông tin đó để xác định nhóm và thời điểm nhả nhóm. Xem [Splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

~~~mermaid
flowchart LR
    A["List: 1, 2, 3"] --> B["split"]
    B --> C["1 -> 10"]
    B --> D["2 -> 20"]
    B --> E["3 -> 30"]
    C --> F["aggregate cùng correlationId"]
    D --> F
    E --> F
    F --> G["Kết quả gồm 10, 20, 30"]
~~~

Đường xử lý mặc định ở ví dụ là đồng bộ; sơ đồ nhiều nhánh thể hiện các message con, không cam kết chúng chạy trên nhiều thread.

### 9.2. Aggregator có trạng thái và điều kiện hoàn thành

Ba câu hỏi phải trả lời:

| Câu hỏi | Thành phần liên quan | Trong ví dụ danh sách |
| --- | --- | --- |
| Message nào thuộc cùng nhóm? | Correlation strategy | Header correlation do splitter tạo |
| Khi nào đủ dữ liệu? | Release strategy | Số phần tử đã biết từ sequence |
| Ghép thành đầu ra gì? | Group processor | Gom payload của nhóm |

Aggregator giữ nhóm trong message store; đây là endpoint có trạng thái. Mặc định dựa vào `correlationId` để gom và thông tin `sequenceSize` để quyết định hoàn thành. Khi nhóm không thể đủ dữ liệu, cần chính sách timeout/expiry và xử lý phần thiếu; chỉ cấu hình timeout chờ của gateway không giải phóng trạng thái nhóm. Xem [Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Ví dụ lỗi thiết kế thường gặp:

~~~text
split danh sách 3 phần tử
  -> filter loại 1 phần tử
  -> aggregator vẫn chờ đủ 3
~~~

Nếu cần loại phần tử, hãy cân nhắc lọc danh sách trước khi split, hoặc thiết kế lại release strategy và hợp đồng kết quả từng phần. Một phương án khác là giữ đủ số phản hồi nhưng biểu diễn phần không hợp lệ thành một kết quả từ chối có kiểu rõ ràng.

Với danh sách rỗng, không có message con được phát để kích hoạt gom như trường hợp không rỗng. Cần quy định riêng kết quả đầu vào rỗng. Với nguồn iterator/stream không biết trước kích thước, cũng không được mặc nhiên áp dụng điều kiện “đã nhận đủ N phần tử”.

Nếu thêm xử lý song song, thứ tự hoàn thành có thể khác thứ tự đầu vào. Nếu thứ tự kết quả quan trọng với nghiệp vụ, phải thiết kế và kiểm thử nó thay vì chỉ nhìn vị trí các dòng trong DSL.

## 10. Xử lý lỗi theo ranh giới thực thi

### 10.1. Flow đồng bộ trả lỗi cho caller

Trong `orderFlow`, các channel trực tiếp giữ đường xử lý đồng bộ. Nếu chuẩn hóa hoặc filter phát sinh lỗi, gateway trong cấu hình hiện tại truyền lỗi cho caller vì chưa cấu hình error channel riêng cho gateway.

Lỗi nghiệp vụ gốc có thể được bọc trong exception của messaging, vì vậy kiểm thử nên xem cả exception ngoài và nguyên nhân. Không nên chỉ bắt `NumberFormatException` ở code gọi rồi cho rằng mọi lỗi parse đều đến trực tiếp dưới đúng kiểu này.

### 10.2. Flow bất đồng bộ cần đường nhận lỗi riêng

Khi task của framework chạy qua executor hoặc poller, exception không thể chỉ ném ngược theo call stack của thread đã gửi xong. Cơ chế xử lý lỗi có thể tạo `ErrorMessage` với payload là `Throwable`, rồi gửi tới error channel thích hợp.

Cấu hình error channel của poller, header `errorChannel` trên message và error channel của gateway có phạm vi tác dụng riêng. Không nên suy luận rằng chỉ tạo bean `errorChannel` sẽ tự bắt mọi exception của mọi handler đồng bộ. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Trong ví dụ queue, `.errorChannel("tasks.errors")` đặt ngay trên poller giúp thấy rõ đích lỗi của công việc polling đó. Với hệ thống thực, thay `System.err.println` bằng xử lý có thể quan sát và vận hành được, như ghi log có mã yêu cầu, metric và nơi lưu các lỗi cần xử lý lại.

### 10.3. Phân biệt timeout, retry và kết quả thất bại

| Tình huống | Quyết định thiết kế gợi ý |
| --- | --- |
| Tiền sai định dạng | Trả lỗi đầu vào; sửa dữ liệu trước khi thử lại |
| Filter loại message trong request-reply | Chọn ném lỗi hoặc một nhánh tạo phản hồi từ chối |
| HTTP downstream lỗi tạm thời | Cân nhắc timeout và retry có giới hạn |
| Gateway hết thời gian chờ | Kiểm tra downstream; chưa kết luận công việc đã dừng |
| Thiếu một message con | Kiểm tra nhóm aggregator và chính sách expiry |
| Retry thao tác tạo đơn | Cần quy tắc chống tạo trùng theo khóa nghiệp vụ |

Các lựa chọn ở bảng là hướng thiết kế cho ứng dụng, không phải hành vi tự động mà DSL cấp sẵn.

Nếu caller timeout nhưng tác vụ tiếp tục tạo đơn, lần gọi lại có thể tạo thêm đơn. Vì vậy, timeout cần đi cùng hợp đồng xử lý trùng và cách tra cứu kết quả cuối cùng; chỉ rút ngắn số mili giây chờ không giải quyết tình huống này.

## 11. Kiểm thử flow ở biên công khai

### 11.1. Kiểm thử gateway của ví dụ chính

Đặt class sau trong `OrderFlowConfigurationTest.java` cùng package `example.integration`. Đây là mã kiểm thử để người học chạy trong dự án có dependency test phù hợp.

~~~java
package example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderFlowConfiguration.class)
class OrderFlowConfigurationTest {

    @Autowired
    @Qualifier("orderGateway")
    private OrderFlowConfiguration.OrderGateway gateway;

    @Test
    void normalizesAndRoutesPriorityOrder() {
        String result = gateway.submit(
                new OrderFlowConfiguration.RawOrder(
                        " O-100 ", true, " 125.50 "),
                "req-priority");

        assertEquals("O-100|PRIORITY|125.50", result);
    }

    @Test
    void routesStandardOrder() {
        String result = gateway.submit(
                new OrderFlowConfiguration.RawOrder(
                        "O-101", false, "20.00"),
                "req-standard");

        assertEquals("O-101|STANDARD|20.00", result);
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(
                MessageRejectedException.class,
                () -> gateway.submit(
                        new OrderFlowConfiguration.RawOrder(
                                "O-102", false, "0"),
                        "req-rejected"));
    }

    @Test
    void exposesMalformedAmountAsTransformationFailure() {
        MessagingException error = assertThrows(
                MessagingException.class,
                () -> gateway.submit(
                        new OrderFlowConfiguration.RawOrder(
                                "O-103", false, "not-a-number"),
                        "req-malformed"));

        assertInstanceOf(NumberFormatException.class, rootCause(error));
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

Các kiểm thử kiểm tra hành vi mà code gọi quan sát được: chuẩn hóa, hai nhánh định tuyến và lỗi. Chúng không cần biết tên channel tự sinh hay cấu trúc nội bộ của builder.

Khi thay handler bằng dịch vụ ngoài, có thể mock bean nghiệp vụ hoặc dùng hỗ trợ của `spring-integration-test`. Các tiện ích kiểm thử integration được giới thiệu trong [Testing support](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

### 11.2. Kiểm thử flow có queue

Với flow kết thúc bằng `QueueChannel`, hãy:

1. Gửi một message mang dữ liệu xác định.
2. Nhận kết quả bằng `receive(timeout)` có giới hạn.
3. Kiểm tra cả việc có message và nội dung mong đợi.
4. Với ca lỗi, kiểm tra error channel hoặc cơ chế ghi nhận lỗi.
5. Đảm bảo trạng thái queue và nhóm aggregator không lẫn giữa các ca.

Không dùng `Thread.sleep(...)` làm bằng chứng công việc đã hoàn tất. Cũng không dùng `receive()` vô hạn trong kiểm thử vì cấu hình sai có thể làm test treo.

Với batch ba phần tử, điều cần chứng minh là có một kết quả gom chứa đúng ba giá trị sau biến đổi và không lẫn dữ liệu của batch khác. Nếu chỉ kiểm tra `send(...) == true` thì chưa kiểm tra splitter hay aggregator.

### 11.3. Chọn mức kiểm thử phù hợp

| Mức | Cần chứng minh | Ví dụ |
| --- | --- | --- |
| Hàm nghiệp vụ | Quy tắc dữ liệu độc lập với messaging | Normalize mã đơn và số tiền |
| Flow trong context | Các endpoint nối đúng, đúng nhánh, đúng reply | Gọi gateway và kiểm tra kết quả/lỗi |
| Tích hợp hạ tầng | Giao thức và phụ thuộc ngoài làm việc đúng | Adapter HTTP/JMS/JDBC với môi trường kiểm thử |

Một flow chỉ nối các hàm đúng riêng lẻ vẫn có thể sai ở channel, header hoặc đường phản hồi. Ngược lại, không cần đưa toàn bộ hạ tầng ngoài vào test chỉ để kiểm tra một quy tắc parse thuần Java.

## 12. Đặt tên và chia flow để dễ bảo trì

Trong ví dụ:

- `orderFlow` là tên bean chứa cấu hình flow.
- `orderGateway` là tên proxy cho code nghiệp vụ gọi.
- `orders.normalized` là channel mang `Order` đã chuẩn hóa.
- `orders.normalize` và `orders.formatReceipt` là các endpoint ID chủ động đặt tên.

Đặt tên tại những ranh giới cần quan sát hoặc điều khiển. Không nên gắn test vào tên channel tự sinh theo chỉ số vì việc thêm một endpoint có thể làm chỉ số thay đổi.

Khi một lambda lớn chứa nhiều nhánh nghiệp vụ, chuyển phần tính toán vào một bean có phương thức rõ ràng. Khi một nhánh được tái sử dụng hoặc có vòng đời độc lập, cân nhắc flow riêng nối qua channel/gateway với hợp đồng đầu vào và phản hồi cụ thể.

Ví dụ, nếu “tạo biên nhận ưu tiên” sau này gồm gọi ba dịch vụ, bù trừ lỗi và ghi dữ liệu, nhét tất cả vào lambda của `subFlowMapping` sẽ khiến topology khó đọc. Flow chính nên diễn đạt các bước ở mức nghiệp vụ; implementation của từng bước có thể được kiểm thử riêng.

## 13. Lỗi thường gặp khi viết Java DSL

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng sửa |
| --- | --- | --- |
| Không import được `IntegrationFlows` | Đang áp dụng ví dụ lịch sử vào phiên bản khác | Dùng factory tương ứng với phiên bản; với mốc bài dùng `IntegrationFlow` |
| Message vào nhưng gateway không có reply | Filter loại, handler một chiều hoặc làm mất header trả lời | Theo dấu từng nhánh và quy định kết quả cho mọi đường |
| Flow từ queue không đọc được | Thiếu consumer/poller hoặc consumer chưa hoạt động | Kiểm tra endpoint polling và vòng đời |
| Gửi vào direct channel báo không có subscriber | Không có endpoint nhận hoặc flow chưa khởi động | Kiểm tra đăng ký bean và channel đích |
| Chỉ một trong nhiều handler nhận message | Đang dùng channel point-to-point | Chọn broadcast khi cần mọi subscriber nhận |
| Lỗi ép kiểu khi lambda nhận `Message` | Overload vẫn đang truyền payload | Chọn overload có token lớp hoặc handler nhận message rõ ràng |
| Hai flow có xung đột tên channel | Tạo nhiều đối tượng inline cùng ID | Khai báo channel dùng chung thành bean một lần |
| Aggregator chờ mãi | Thiếu phần tử, sai correlation hoặc điều kiện release | Kiểm tra sequence, filter và chính sách nhóm |
| Chỉ có dòng log rồi flow dừng | Handler cuối không trả kết quả | Chọn rõ hợp đồng một chiều hoặc request-reply |
| Retry làm phát sinh dữ liệu trùng | Side effect chưa có quy tắc xử lý trùng | Áp dụng khóa nghiệp vụ và hợp đồng idempotency |
| Caller timeout nhưng downstream vẫn chạy | Timeout chờ reply không hủy công việc | Thiết kế deadline/cancel và truy vấn kết quả khi cần |

Dùng bảng để hình thành giả thuyết, sau đó xác minh bằng message thực, cấu hình endpoint và log. Một timeout đơn lẻ chưa đủ xác định message đã bị loại, mất header hay còn nằm trong queue.

## 14. Bài thực hành tự triển khai

### Bài 1: Thêm một nhánh nghiệp vụ

Đổi điều kiện định tuyến để chia thành `PRIORITY`, `STANDARD` và `MANUAL_REVIEW` cho đơn vượt một ngưỡng tiền.

Yêu cầu hoàn thành:

- Tất cả khóa định tuyến hợp lệ đều có đích.
- Mỗi nhánh có cùng kiểu phản hồi trước formatter.
- Có kiểm thử cho giá trị đúng ngưỡng và vượt ngưỡng.
- Mã phân loại nằm trong một hàm/bean có thể kiểm thử độc lập.

### Bài 2: Đổi hợp đồng từ chối

Thay việc ném exception khi số tiền không dương bằng một kết quả nghiệp vụ có trạng thái `REJECTED`.

Trước khi sửa DSL, định nghĩa kiểu trả về của gateway cho cả đơn được chấp nhận và đơn bị từ chối. Sau đó dùng router hoặc nhánh phản hồi thích hợp, rồi kiểm thử rằng mọi đầu vào đều có kết quả theo hợp đồng.

### Bài 3: Thêm queue và quan sát lỗi

Tách công việc xử lý sang một queue có sức chứa hữu hạn.

Yêu cầu hoàn thành:

- Consumer có poller tường minh.
- Một task hợp lệ đi đến đích quan sát được.
- Một task lỗi đi đến đường ghi nhận lỗi.
- Test có timeout hữu hạn và không dựa vào sleep.
- Phân biệt được gửi thành công với xử lý thành công.

### Bài 4: Kiểm tra batch không đầy đủ

Với flow `split → transform → aggregate`, thử thêm một filter sau split và loại một phần tử. Giải thích vì sao nhóm chưa hoàn thành, sau đó chọn cách sửa phù hợp với nghiệp vụ.

Không chỉ tăng timeout. Cần đưa ra hợp đồng rõ cho nhóm thiếu dữ liệu, đầu vào rỗng và kết quả từng phần.

## 15. Các điểm cần ghi nhớ

`IntegrationFlow` mô tả cách các channel và endpoint nối với nhau; Java DSL giúp diễn đạt topology ngay trong cấu hình Java. Khi đọc tài liệu cũ có `IntegrationFlows`, trước hết đối chiếu API với phiên bản đang dùng.

Thiết kế một flow bắt đầu bằng hợp đồng: ai gửi message, mỗi bước nhận/trả payload nào, header nào phải giữ, mỗi nhánh tạo kết quả gì và lỗi đến đâu. Sau đó chọn channel để xác định đồng bộ, polling hay dispatch qua executor.

Một flow hoàn chỉnh phải giải thích được cả đường thành công, đường từ chối và đường không hoàn tất. Gateway, filter, router và aggregator chỉ phối hợp đúng khi các hợp đồng đó được định nghĩa và kiểm thử.
