# Router theo type

Trong module **SPRING_INTEGRATION_CORE**, router theo type giúp tách một luồng thông điệp thành các nhánh dựa trên **kiểu Java của payload**. Ví dụ, sự kiện tạo đơn đi tới nhánh đơn hàng, sự kiện thanh toán đi tới nhánh thanh toán, còn loại chưa được hỗ trợ đi tới một hàng đợi riêng.

Bài này thuộc chương **Router**, tập trung vào `PayloadTypeRouter`, cách nối router với channel bằng Java DSL, lựa chọn nhánh theo lớp/interface và xử lý tình huống không định tuyến được. Các ví dụ dùng Java 17+ và API Spring Integration 6.5.x; không yêu cầu Spring Boot.

## 1. Mục tiêu và tình huống sử dụng

Sau bài học, bạn có thể:

- Phân biệt kiểu của `Message`, kiểu khai báo của biến và kiểu thực tế của payload.
- Ánh xạ một lớp hoặc interface tới một `MessageChannel`.
- Giải thích sự khác nhau giữa `PayloadTypeRouter` và router dùng lambda `Object::getClass`.
- Chọn chính sách cho payload lạ, channel bị cấu hình sai và lỗi gửi thông điệp.
- Kiểm thử đúng nhánh, không gửi thừa sang nhánh khác và giữ thông tin theo dõi.

Giả sử ứng dụng tiếp nhận các sự kiện đã được chuyển thành đối tượng Java:

| Payload | Ý nghĩa | Channel mong muốn |
| --- | --- | --- |
| `OrderPlaced` | Đơn hàng đã được tạo | `orderEvents` |
| `PaymentCaptured` | Thanh toán đã được ghi nhận | `paymentEvents` |
| `RefundRequested` | Sự kiện nghiệp vụ chưa có nhánh riêng | `otherBusinessEvents` |
| Một `String` ngoài mô hình sự kiện | Đầu vào chưa được hỗ trợ | `unsupportedEvents` |

Ở đây, lớp Java đã thể hiện loại sự kiện. Nếu mọi payload đều là `Order` và quyết định phụ thuộc vào `order.status()`, router theo thuộc tính nghiệp vụ sẽ phù hợp hơn.

## 2. Router nhìn vào kiểu nào?

Thông điệp Spring gồm payload và headers. Với router theo type, dữ liệu để chọn nhánh là kiểu runtime của **payload**, không phải lớp của đối tượng `Message`.

Đoạn mã sau dùng `BusinessEvent` và `OrderPlaced` được khai báo trong cấu hình ở mục 5:

~~~java
BusinessEvent event = new OrderPlaced("ORD-1001");
Message<BusinessEvent> message = new GenericMessage<>(event);

// Kiểu runtime của payload vẫn là OrderPlaced.
Class<?> actualType = message.getPayload().getClass();
~~~

Các lớp thông điệp trong ví dụ thuộc package `org.springframework.messaging` và `org.springframework.messaging.support`.

| Thành phần | Vai trò đối với quyết định định tuyến |
| --- | --- |
| `GenericMessage` | Lớp bao thông điệp |
| `Message<BusinessEvent>` | Kiểu khai báo ở mã nguồn |
| `BusinessEvent` | Interface của payload; có thể được ánh xạ |
| `OrderPlaced` | Lớp thực tế của payload; có thể có nhánh chuyên biệt |
| Header `eventType=PAYMENT` nếu có | Không tự tham gia quyết định của `PayloadTypeRouter` |

Spring định nghĩa `PayloadTypeRouter` là router phân giải channel dựa trên kiểu payload. Vì vậy, hãy xác định dữ liệu đã được giải mã thành kiểu nào trước khi đặt router trong flow. Xem [API PayloadTypeRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/PayloadTypeRouter.html).

Router chọn nơi gửi thông điệp. Transformer đặt trước router có thể thay đổi kiểu mà router quan sát; bản thân router không biến sự kiện đơn hàng thành sự kiện thanh toán.

## 3. Từ kiểu payload tới channel đích

Có thể chia quyết định thành ba bước:

1. Tìm kiểu phù hợp trong các kiểu đã cấu hình.
2. Lấy tên channel gắn với kiểu được chọn.
3. Phân giải tên đó thành bean `MessageChannel`, rồi gửi thông điệp.

~~~mermaid
flowchart LR
    A["eventInput: Message có payload"] --> R["PayloadTypeRouter"]
    R -->|"OrderPlaced"| O["orderEvents"]
    R -->|"PaymentCaptured"| P["paymentEvents"]
    R -->|"BusinessEvent phù hợp"| B["otherBusinessEvents"]
    R -->|"Không có kiểu phù hợp"| U["unsupportedEvents"]
~~~

Một ánh xạ Java có dạng:

~~~java
router.setChannelMapping(
        OrderPlaced.class.getName(),
        "orderEvents");
~~~

Hai đối số mang ý nghĩa khác nhau:

- `OrderPlaced.class.getName()` là khóa kiểu, gồm tên lớp đầy đủ.
- `"orderEvents"` là tên bean channel trong Spring context.

Nên lấy khóa bằng `Class.getName()` thay vì gõ tên lớp bằng tay. Cách này tránh lỗi khi đổi package và xử lý đúng tên lớp lồng nhau có ký tự `$`. Channel đích vẫn cần được khai báo; chuỗi tên trong mapping không tự tạo bean tương ứng.

Cấu hình đối tượng router rồi đưa vào `.route(router)` là cách Spring Integration hỗ trợ trực tiếp. Xem [Router Implementations](https://docs.spring.io/spring-integration/reference/6.5/router/implementations.html).

## 4. Chọn kiểu cụ thể, lớp cha và interface

### 4.1. Ánh xạ chính xác được ưu tiên

Giả sử `OrderPlaced` triển khai `BusinessEvent`, và cả hai kiểu đều có mapping:

~~~text
OrderPlaced   -> orderEvents
BusinessEvent -> otherBusinessEvents
~~~

Thông điệp chứa `OrderPlaced` đi tới `orderEvents`; nó không được gửi thêm tới `otherBusinessEvents`.

Một nhánh chung có thể tiếp nhận các sự kiện mới triển khai `BusinessEvent`, trong khi một số lớp cụ thể có nhánh chuyên biệt. Nhánh chung cần xử lý được các loại sự kiện mà nó có thể nhận.

### 4.2. Có thể ánh xạ lớp cha hoặc interface

| Mapping đã cấu hình | Payload | Kết quả |
| --- | --- | --- |
| Chỉ `Number -> numericEvents` | `Integer.valueOf(10)` | `numericEvents` |
| `Number -> numericEvents` và `Integer -> integerEvents` | `Integer.valueOf(10)` | `integerEvents` |
| Chỉ `BusinessEvent -> otherBusinessEvents` | `RefundRequested` triển khai `BusinessEvent` | `otherBusinessEvents` |

Không nên diễn giải thành “mapping khai báo trước sẽ thắng”. Router đánh giá độ phù hợp của kiểu. Với cây kiểu phức tạp, cũng không thể mặc định mọi lớp cha luôn đứng trước mọi interface: triển khai 6.5.x tính trọng số theo quan hệ kiểu, trong đó interface trực tiếp có thể được ưu tiên hơn một lớp cha. Xem [mã nguồn PayloadTypeRouter 6.5.x](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/router/PayloadTypeRouter.java).

### 4.3. Nhiều kiểu phù hợp ngang nhau có thể gây lỗi

Xét payload triển khai hai interface độc lập:

~~~java
interface Auditable {
}

interface Retriable {
}

record MaintenanceRequested(String requestId)
        implements Auditable, Retriable {
}
~~~

Nếu chỉ có các mapping:

~~~text
Auditable -> auditEvents
Retriable -> retryEvents
~~~

Hai interface trực tiếp có cùng mức phù hợp. Router không coi đây là yêu cầu gửi tới cả hai channel; trường hợp mơ hồ bị từ chối. Trong 6.5.x, thuật toán chọn kiểu phát sinh `IllegalStateException`; khi đi qua cơ chế xử lý message, lỗi có thể được bọc trong ngoại lệ messaging.

Có thể thêm mapping chính xác cho `MaintenanceRequested`, hoặc tổ chức lại các loại payload để quy tắc có một kết quả duy nhất. Nếu nghiệp vụ yêu cầu phát cho nhiều người nhận, hãy chọn mô hình recipient list hoặc publish-subscribe.

Các trường hợp lớp cha, interface và mapping mơ hồ được minh họa trong [kiểm thử của PayloadTypeRouter](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/test/java/org/springframework/integration/router/PayloadTypeRouterTests.java).

## 5. Ví dụ hoàn chỉnh: phân luồng sự kiện

Ví dụ dùng một `DirectChannel` đầu vào và bốn `QueueChannel` đầu ra để dễ quan sát, kiểm thử. Các channel này nằm trong bộ nhớ ứng dụng.

Đặt cấu hình trong `TypeRoutingConfig.java`:

~~~java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.PayloadTypeRouter;

@Configuration
@EnableIntegration
public class TypeRoutingConfig {

    public interface BusinessEvent {
    }

    public record OrderPlaced(String orderId) implements BusinessEvent {
    }

    public record PaymentCaptured(String paymentId, String orderId)
            implements BusinessEvent {
    }

    public record RefundRequested(String orderId) implements BusinessEvent {
    }

    @Bean
    public DirectChannel eventInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel paymentEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel otherBusinessEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel unsupportedEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public PayloadTypeRouter eventTypeRouter() {
        PayloadTypeRouter router = new PayloadTypeRouter();

        router.setChannelMapping(
                OrderPlaced.class.getName(), "orderEvents");
        router.setChannelMapping(
                PaymentCaptured.class.getName(), "paymentEvents");
        router.setChannelMapping(
                BusinessEvent.class.getName(), "otherBusinessEvents");

        router.setChannelKeyFallback(false);
        router.setDefaultOutputChannelName("unsupportedEvents");
        router.setResolutionRequired(true);
        router.setSendTimeout(1_000);

        return router;
    }

    @Bean
    public IntegrationFlow eventRoutingFlow(
            PayloadTypeRouter eventTypeRouter) {

        return IntegrationFlow.from("eventInput")
                .route(eventTypeRouter)
                .get();
    }
}
~~~

Các vai trò cốt lõi trong flow:

- `Message` mang sự kiện và headers.
- `eventInput` là channel tiếp nhận.
- `PayloadTypeRouter` là handler lựa chọn đích.
- Java DSL tạo flow và endpoint kết nối handler với channel đầu vào.
- Các queue giữ thông điệp để bên nhận lấy ra xử lý.

`setChannelKeyFallback(false)` thể hiện chính sách chỉ dùng mapping đã khai báo. `setResolutionRequired(true)` giúp phát hiện tên channel đã ánh xạ nhưng không tồn tại. Nhánh `unsupportedEvents` dành cho payload không có kiểu phù hợp, không thay thế cơ chế báo lỗi cấu hình.

Mỗi queue có sức chứa 100 thông điệp; router chờ tối đa 1.000 ms khi gửi nếu channel cần chờ. Trong ứng dụng thực, cần bố trí bên tiêu thụ và chọn sức chứa phù hợp. `QueueChannel` tạo theo cách trên không lưu bền dữ liệu qua lần khởi động lại ứng dụng.

### 5.1. Gửi thông điệp thử

Đoạn mã sau có thể đặt trong phương thức chạy thử của một lớp cùng package:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                TypeRoutingConfig.class)) {

    var input = context.getBean(
            "eventInput",
            org.springframework.messaging.MessageChannel.class);

    var message = org.springframework.messaging.support.MessageBuilder
            .withPayload(new TypeRoutingConfig.OrderPlaced("ORD-1001"))
            .setHeader("traceId", "trace-01")
            .build();

    boolean sent = input.send(message);
    if (!sent) {
        throw new IllegalStateException("Không gửi được thông điệp");
    }

    var orders = context.getBean(
            "orderEvents",
            org.springframework.integration.channel.QueueChannel.class);

    var routed = orders.receive(1_000);
    if (routed == null) {
        throw new IllegalStateException("Không nhận được sự kiện đơn hàng");
    }

    System.out.println(routed.getPayload());
    System.out.println(routed.getHeaders().get("traceId"));
}
~~~

Khi queue chưa đầy, `send()` hoàn tất sau khi router gửi vào queue. Điều đó chưa có nghĩa nghiệp vụ gửi email hay cập nhật cơ sở dữ liệu đã chạy xong. Ví dụ hiện dừng ở việc phân luồng và nhận thông điệp.

Để xử lý nghiệp vụ từ queue, có thể tạo consumer với poller. Nếu đầu ra dùng `DirectChannel`, handler phía sau chạy đồng bộ trên luồng gửi theo cấu hình thông thường.

### 5.2. Lựa chọn endpoint bằng annotation

Một cách nối khác là thêm annotation sau vào phương thức `@Bean eventTypeRouter()` đã có:

~~~java
@org.springframework.integration.annotation.ServiceActivator(
        inputChannel = "eventInput")
~~~

Khi dùng lựa chọn này, giữ nguyên thân phương thức cấu hình router và bỏ bean `eventRoutingFlow` tương ứng. Chỉ nên có một endpoint router tại điểm nối đang xét; giữ cả hai cách sẽ tạo hai subscriber trên `DirectChannel` và làm thay đổi cách phân phối thông điệp.

## 6. Java DSL với Object::getClass có cùng hành vi không?

Java DSL cho phép một hàm trả về khóa định tuyến. Có thể thay bean flow ở ví dụ chính bằng phương thức sau, đặt trong cùng lớp cấu hình:

~~~java
@Bean
public IntegrationFlow eventRoutingFlow() {
    return IntegrationFlow.from("eventInput")
            .<Object, Class<?>>route(
                    Object::getClass,
                    routes -> routes
                            .channelMapping(
                                    OrderPlaced.class, "orderEvents")
                            .channelMapping(
                                    PaymentCaptured.class, "paymentEvents")
                            .channelKeyFallback(false)
                            .defaultOutputChannel("unsupportedEvents"))
            .get();
}
~~~

Lambda trả về đúng lớp runtime. Router dùng hàm này ánh xạ khóa theo giá trị trả về; nó không tự thực hiện thuật toán tìm lớp cha/interface của `PayloadTypeRouter`.

| Payload | `PayloadTypeRouter` ở mục 5 | Lambda ở mục 6 |
| --- | --- | --- |
| `OrderPlaced` | `orderEvents` | `orderEvents` |
| `PaymentCaptured` | `paymentEvents` | `paymentEvents` |
| `RefundRequested` | `otherBusinessEvents` nhờ interface | `unsupportedEvents` |
| `String` | `unsupportedEvents` | `unsupportedEvents` |

Ngay cả khi thêm `.channelMapping(BusinessEvent.class, "otherBusinessEvents")` vào cấu hình lambda, `Object::getClass` vẫn trả về `RefundRequested.class`, không trả về `BusinessEvent.class`.

Nếu muốn tự nhóm kiểu trong lambda, bạn phải thể hiện quy tắc bằng logic như `instanceof` và trả về khóa nghiệp vụ phù hợp. Để tận dụng quan hệ kế thừa có sẵn, dùng trực tiếp `PayloadTypeRouter` thường thể hiện ý định rõ hơn. Khả năng cấu hình `route()` bằng đối tượng router, biểu thức hoặc lambda được trình bày trong [Message Routers với Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-routers.html).

## 7. Không khớp kiểu và lỗi định tuyến

### 7.1. Bốn tình huống cần phân biệt

Với cấu hình ở mục 5:

| Tình huống | Ví dụ | Hành vi dự kiến |
| --- | --- | --- |
| Không có kiểu phù hợp | Payload `String` | Gửi tới `unsupportedEvents` |
| Có kiểu phù hợp nhưng channel không tồn tại | `OrderPlaced` bị ánh xạ tới `orderEvnts` | Lỗi phân giải channel vì `resolutionRequired=true` |
| Kiểu phù hợp bị mơ hồ | Hai interface trực tiếp cùng được ánh xạ | Lỗi khi chọn kiểu; default không giải quyết sự mơ hồ |
| Channel tồn tại nhưng gửi/xử lý thất bại | Queue đầy quá thời gian chờ hoặc handler đồng bộ ném lỗi | Lỗi gửi/xử lý; không tự chuyển sang default |

`defaultOutputChannel` dành cho trường hợp router không có đích thích hợp. Nó không phải khối `catch` bao mọi lỗi của flow.

Mặc định, `ignoreSendFailures=false`. Với `DirectChannel`, lỗi sâu hơn trong nhánh đồng bộ có thể quay ngược về thao tác gửi của router. Xem [Common Router Parameters](https://docs.spring.io/spring-integration/reference/6.5/router/common-parameters.html).

### 7.2. resolutionRequired không thay thế nhánh mặc định

`resolutionRequired` kiểm soát lỗi **phân giải tên channel**:

- `true`: tên đích không phân giải được sẽ gây lỗi.
- `false`: cho phép bỏ qua đích không phân giải được; khi không còn đích, router có thể dùng default đã cấu hình.

Nếu không có channel đích và cũng không có default, router vẫn có thể ném `MessageDeliveryException`. Chỉ đặt `resolutionRequired=false` không có nghĩa thông điệp tự đi vào `errorChannel` hoặc bị loại bỏ có chủ đích.

Từ Spring Integration 6.0, đặt default output channel cũng đặt `channelKeyFallback=false` nếu chưa có lựa chọn tường minh khác. Ví dụ chính khai báo rõ để người đọc thấy chính sách. Nếu tự bật lại fallback theo khóa, cần xem xét tương tác với `resolutionRequired`: tổ hợp default channel, `channelKeyFallback=true` và `resolutionRequired=true` bị từ chối khi khởi tạo. Xem [quy tắc trong AbstractMappingMessageRouter](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/router/AbstractMappingMessageRouter.java).

### 7.3. Chính sách cho payload lạ và lỗi thực thi

Có thể giữ payload lạ tại `unsupportedEvents` cùng `traceId` để kiểm tra phía gửi hoặc bước giải mã. Nhánh này cần quy trình tiêu thụ; để thông điệp dồn mãi sẽ làm đầy bộ đệm.

Nếu hợp đồng đầu vào chỉ cho phép một tập kiểu cố định và cần phát hiện vi phạm ngay, có thể bỏ default để báo lỗi khi không có đích. Nếu chủ động muốn loại bỏ thông điệp, Spring Integration có `nullChannel`; lựa chọn phải phù hợp với nghiệp vụ.

Lỗi thực thi cần chính sách riêng tại ranh giới flow. Với lời gọi trực tiếp vào `DirectChannel`, ngoại lệ thường truyền về bên gọi `send()`; chỉ thêm header `errorChannel` không tự biến lời gọi này thành cơ chế phát lỗi bất đồng bộ. Khi có poller, executor hoặc gateway xử lý lỗi, cần cấu hình theo cơ chế của thành phần đó.

Không nên retry vô hạn lỗi thiếu mapping hoặc sai tên bean channel. Chạy lại cùng thông điệp khi chưa thay đổi cấu hình không tạo ra đích hợp lệ.

## 8. Kiểm thử quyết định định tuyến

Mã sau dùng JUnit Jupiter, Spring context và cấu hình ở mục 5. Cần có `spring-integration-core` cùng các dependency Spring tương thích; dự án có thể quản lý phiên bản bằng BOM hiện có.

Mỗi phép thử tạo context mới. Hàm kiểm tra xác nhận đúng một queue nhận cùng payload và header theo dõi; các queue còn lại phải rỗng. Không dùng `Thread.sleep()`.

Đặt mã trong `TypeRoutingConfigTest.java`, cùng package với cấu hình:

~~~java
package example.integration;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class TypeRoutingConfigTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                TypeRoutingConfig.class);
        input = context.getBean("eventInput", MessageChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void concreteOrderTypeWinsOverBusinessEventInterface() {
        assertOnlyRoute(
                new TypeRoutingConfig.OrderPlaced("ORD-1001"),
                "orderEvents");
    }

    @Test
    void paymentTypeUsesItsDedicatedQueue() {
        assertOnlyRoute(
                new TypeRoutingConfig.PaymentCaptured("PAY-1", "ORD-1001"),
                "paymentEvents");
    }

    @Test
    void eventWithoutDedicatedMappingUsesBusinessEventInterface() {
        assertOnlyRoute(
                new TypeRoutingConfig.RefundRequested("ORD-1001"),
                "otherBusinessEvents");
    }

    @Test
    void unrelatedPayloadUsesDefaultQueue() {
        assertOnlyRoute("unrecognized payload", "unsupportedEvents");
    }

    private void assertOnlyRoute(Object payload, String expectedChannel) {
        Message<?> source = MessageBuilder.withPayload(payload)
                .setHeader("traceId", "trace-test")
                .build();

        assertTrue(input.send(source));

        for (String name : List.of(
                "orderEvents",
                "paymentEvents",
                "otherBusinessEvents",
                "unsupportedEvents")) {

            QueueChannel queue = context.getBean(name, QueueChannel.class);

            if (name.equals(expectedChannel)) {
                Message<?> result = queue.receive(1_000);
                assertNotNull(result, "Thiếu thông điệp ở " + name);
                assertSame(payload, result.getPayload());
                assertEquals(
                        "trace-test",
                        result.getHeaders().get("traceId"));
                assertNull(queue.receive(0), "Có thông điệp thừa ở " + name);
            }
            else {
                assertNull(queue.receive(0), "Gửi sai nhánh tới " + name);
            }
        }
    }
}
~~~

`assertSame(payload, result.getPayload())` kiểm tra ví dụ định tuyến trong bộ nhớ không thay thế payload. Đây không phải cam kết giữ nguyên object qua broker, serialization hoặc transformer.

Khi sửa cấu hình, nên bổ sung các tình huống sau vào bộ kiểm thử của ứng dụng:

| Biến thể | Điều cần xác nhận |
| --- | --- |
| Xóa default, gửi kiểu không ánh xạ | Bên gửi nhận lỗi thay vì im lặng mất thông điệp |
| Gõ sai tên channel trong mapping | Lỗi đích không bị coi là sự kiện lạ |
| Ánh xạ hai interface trực tiếp của cùng payload | Lỗi mơ hồ; kiểm tra cả nguyên nhân gốc nếu ngoại lệ bị bọc |
| Thay router bằng lambda `Object::getClass` | Sự kiện chỉ khớp interface đi theo chính sách mới |
| Queue đạt sức chứa tối đa | Hành vi gửi quá thời gian chờ và cách bên gọi xử lý |

## 9. Những giới hạn dễ gây định tuyến sai

### 9.1. JSON chưa trở thành kiểu nghiệp vụ

Dữ liệu sau vẫn chỉ là `String` nếu bước nhận chưa deserialize:

~~~json
{
  "eventType": "ORDER_PLACED",
  "orderId": "ORD-1001"
}
~~~

Trường `eventType` không làm payload trở thành `OrderPlaced`. Deserialize chung vào `Map` cũng có thể khiến nhiều loại sự kiện có cùng lớp runtime.

Có thể thiết kế theo một trong hai hướng:

~~~text
Dữ liệu ngoài -> deserialize thành kiểu nghiệp vụ
               -> PayloadTypeRouter -> nhánh theo kiểu Java
~~~

~~~text
Dữ liệu ngoài -> đọc trường phân loại hoặc header chuẩn hóa
               -> router theo giá trị -> nhánh nghiệp vụ
~~~

Hướng thứ nhất phù hợp khi mô hình kiểu là hợp đồng trong ứng dụng. Hướng thứ hai phù hợp khi các thông điệp dùng cùng một envelope và loại sự kiện nằm trong dữ liệu.

### 9.2. Generic collection không mang đủ thông tin định tuyến

`List<OrderPlaced>` và `List<PaymentCaptured>` có thể cùng là `ArrayList` tại runtime. `PayloadTypeRouter` không dựa vào tham số generic trong mã nguồn để phân biệt từng danh sách.

Nếu cần xử lý từng sự kiện, có thể đặt splitter trước router. Nếu danh sách phải đi nguyên lô, nên dùng kiểu bao riêng như `OrderBatch`, `PaymentBatch`, hoặc định tuyến theo thông tin loại lô rõ ràng.

### 9.3. Mapping quá rộng che khuất dữ liệu chưa hỗ trợ

Mapping `BusinessEvent` là quyết định có chủ đích: sự kiện mới triển khai interface này được chấp nhận vào nhánh chung.

Nếu thêm mapping quá rộng như `Object` cho các payload đối tượng thông thường, nhiều dữ liệu ngoài dự kiến cũng có thể được coi là đã có nhánh. Default channel khi đó không còn là chỉ báo hữu ích cho những dữ liệu ấy.

Hãy xác định ranh giới giữa “sự kiện hợp lệ chưa có nhánh riêng” và “đầu vào không được hỗ trợ”. Hai trường hợp có thể cần cách theo dõi và xử lý khác nhau.

### 9.4. Đổi tên lớp ảnh hưởng tới mapping

Trong cùng ứng dụng, dùng `SomeEvent.class.getName()` giúp mapping đi cùng việc refactor. Nếu tên lớp đầy đủ được lưu ở cấu hình ngoài, cần cập nhật cấu hình khi đổi package hoặc lớp.

Với hợp đồng liên hệ thống, mã sự kiện ổn định như `ORDER_PLACED` độc lập với cấu trúc package Java hơn. Có thể chuyển mã đó thành đối tượng nghiệp vụ tại ranh giới nhận, rồi dùng type routing bên trong ứng dụng.

## 10. Áp dụng vào thiết kế flow

Dùng `PayloadTypeRouter` khi kiểu payload phản ánh nhánh xử lý và bạn muốn khai thác quan hệ lớp/interface. Dùng mapping chính xác cho nhánh chuyên biệt; chỉ thêm mapping kiểu cha khi nhánh chung xử lý được mọi payload mà nó nhận.

Khi đọc hoặc sửa flow, lần lượt xác định kiểu runtime tại đầu vào router, mapping được chọn, channel đích và chính sách khi không có đích. Kiểm thử cần chứng minh cả nhánh nhận đúng lẫn các nhánh không được nhận. Các thông tin này giúp kiểm soát tác động khi thêm một loại sự kiện mới.
