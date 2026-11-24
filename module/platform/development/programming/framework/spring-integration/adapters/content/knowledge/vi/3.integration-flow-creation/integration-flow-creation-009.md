# Định tuyến flow qua nhiều endpoint

## 1. Bài toán và mục tiêu học tập

Trong Spring Integration, không phải message nào cũng đi qua cùng một chuỗi xử lý. Đơn hàng giao nhanh cần chuyển đến dịch vụ xử lý ưu tiên; đơn tiêu chuẩn đi đến một handler khác; dữ liệu bị lỗi phải chuyển đến nhánh kiểm duyệt. Một inbound adapter có thể tiếp nhận dữ liệu từ file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu rồi đưa vào **một channel chung**, trong khi bước tiếp theo phải lựa chọn endpoint theo nội dung của message.

**Định tuyến flow qua nhiều endpoint** là cách dùng một *message router* để chọn channel đích. Mỗi channel có thể dẫn đến service activator, transformer, outbound adapter/gateway hoặc một `IntegrationFlow` độc lập. Router có trách nhiệm **quyết định đường đi**, các endpoint ở nhánh đích mới thực hiện xử lý nghiệp vụ.

Bài học thuộc chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**. Module này hướng đến kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; đồng thời thực hành hợp đồng message, xử lý lỗi và vòng đời kết nối. Router là điểm nối quan trọng khi nhiều hệ thống, nhiều giao thức hoặc nhiều luồng nghiệp vụ cùng xuất hiện trong một ứng dụng.

Sau bài, người học có thể:

- Giải thích *Content-Based Router* và phân biệt với filter, transformer, bridge, splitter và publish–subscribe.
- Khai báo router bằng `IntegrationFlow.route(...)`, ánh xạ khóa định tuyến sang tên channel.
- Viết nhiều nhánh `IntegrationFlow` hoặc `@ServiceActivator` tiêu thụ từ các channel khác nhau.
- Cấu hình router dựa trên payload hoặc header, và biết cách xử lý khóa không được hỗ trợ.
- Chọn giữa **một nhánh**, **nhiều nhánh**, **nhánh mặc định**, **nhánh lỗi**.
- Hiểu đường reply khi router nằm trong flow request–reply và ảnh hưởng của Direct/Queue/ExecutorChannel.
- Kiểm thử từng đường định tuyến, trường hợp không khớp, payload sai và metadata quan trọng.

**Phạm vi:** router làm việc với `Message<?>` trong Spring Integration. Nó không tự đọc dữ liệu từ SFTP, ghi vào database, gửi Kafka hay thực hiện retry; những phần đó do adapter, gateway, handler và cấu hình nguồn/đích đảm nhiệm.

## 2. Router đứng ở đâu trong hệ thống?

Ví dụ một ứng dụng nhận message từ nhiều nguồn, chuẩn hóa chúng thành `OrderEvent`, sau đó chọn kênh giao hàng nhanh hoặc tiêu chuẩn.

~~~mermaid
flowchart LR
    A["File / SFTP inbound<br/>hoặc HTTP/JMS/Kafka"]
    B["orders.input<br/>MessageChannel"]
    C["Validate / Normalize"]
    R{"Content-Based Router<br/>priority?"}
    E["orders.express"]
    S["orders.standard"]
    H1["Express Flow<br/>Transformer → Handler"]
    H2["Standard Flow<br/>Transformer → Handler"]
    D1[("Express service")]
    D2[("Standard service")]
    A --> B --> C --> R
    R -->|"EXPRESS"| E --> H1 --> D1
    R -->|"STANDARD"| S --> H2 --> D2
~~~

Router là một **message-handling endpoint**: nó đọc khóa định tuyến từ payload hoặc headers, xác định channel tương ứng và gửi message đến channel đó. Một số kiểu router có thể trả nhiều channel, nhưng trong tình huống *content-based routing* thông thường mỗi message đi vào **một nhánh được lựa chọn**.

| Thành phần | Chức năng | Không nên nhầm với |
| --- | --- | --- |
| Filter | Quyết định message có được đi tiếp hay bị từ chối. | Router, vì filter không phải lúc nào cũng có nhiều đích nghiệp vụ. |
| Transformer | Đổi cấu trúc/kiểu payload. | Router, vì route không có nghĩa là parse hoặc đổi schema. |
| Router | Dựa vào khóa để chọn channel và downstream endpoint. | Outbound adapter, vì router không tự giao tiếp với hệ thống ngoài. |
| Bridge | Chuyển tiếp giữa hai channel đã biết. | Router, vì bridge không chọn đường đi theo nội dung. |
| Publish–subscribe | Phân phát cùng message tới nhiều subscriber. | Router chọn một nhánh thông thường. |
| Splitter | Tách một message thành nhiều message con. | Router chuyển hướng message, không tự tách collection. |
| Gateway | Cung cấp trao đổi request–reply hoặc API Java. | Router, vì gateway liên quan đường request/response. |

**Quy tắc quan trọng:** mọi channel mà router có thể chọn phải có consumer thích hợp. Nếu router gửi vào một `DirectChannel` không có subscriber, thao tác dispatch có thể thất bại. Nếu gửi vào `QueueChannel`, cần endpoint có poller để tiêu thụ. Chỉ khai báo ánh xạ channel là chưa đủ để có luồng xử lý hoàn chỉnh.

## 3. Khóa định tuyến, channel mapping và nhánh mặc định

Một router dựa vào một **routing key**: giá trị đơn giản mà hệ thống dùng để lựa chọn nhánh. Khóa có thể lấy từ payload hoặc message headers.

Ví dụ contract message:

~~~text
payload = OrderEvent(
    orderId = "ORD-1001",
    priority = "EXPRESS",
    amount = 250000
)

headers = {
    correlationId: "trace-ord-1001",
    sourceSystem: "sftp-import"
}
~~~

Routing key là `priority = "EXPRESS"`. Chính sách định tuyến:

| Routing key | Channel đích | Endpoint phía sau |
| --- | --- | --- |
| `EXPRESS` | `orders.express` | Flow giao nhanh và service riêng. |
| `STANDARD` | `orders.standard` | Flow giao tiêu chuẩn. |
| `null` hoặc giá trị khác | Theo chính sách lỗi hoặc default route. | Không nên im lặng làm mất message. |

Không nên để dữ liệu bên ngoài tự chọn tên bean bất kỳ để router gửi đến. Với khóa từ request HTTP hoặc header của đối tác, hãy **validate và giới hạn tập giá trị được phép**, rồi mapping tường minh sang channel nội bộ. Điều này cũng giúp tránh sự cố do khác chữ hoa/chữ thường, khoảng trắng hoặc một mã mới chưa được triển khai.

Ba chính sách phổ biến khi không tìm được nhánh:

1. **Fail fast:** phát exception để upstream/caller biết dữ liệu chưa được hỗ trợ.
2. **Default route:** đưa message vào channel fallback có consumer thực hiện lưu/quarantine hoặc xử lý chuẩn.
3. **Discard có chủ đích:** chỉ dùng khi nghiệp vụ thực sự cho phép bỏ qua, có metric/audit thích hợp.

Một default channel không nhất thiết là "thành công": nó có thể là **dead-letter/quarantine channel** dành cho message chưa biết cách xử lý.

## 4. Ví dụ hoàn chỉnh: Java DSL định tuyến hai flow độc lập

Ta xây ứng dụng nhận `OrderEvent`, xác minh đơn hợp lệ rồi chọn nhánh **EXPRESS** hoặc **STANDARD**. Sau router, mỗi nhánh có transformer và handler riêng. Một `@MessagingGateway` cho phép Java caller gửi đơn vào flow. Ví dụ ghi nhận kết quả trong bộ nhớ để người học dễ quan sát; nó **chưa giao hàng thật**.

### 4.1. Dependency

Ví dụ dùng Java 17+, Spring Boot cùng phiên bản Spring Integration do BOM của Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Có thể đặt toàn bộ mã minh họa trong tệp `RoutingApplication.java` thuộc package `demo.routing`. Các `record` và interface package-private được khai báo cùng tệp để ví dụ tự chứa.

### 4.2. Định nghĩa channel, router và các nhánh

~~~java
package demo.routing;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
@IntegrationComponentScan
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.express")
    MessageChannel expressOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.standard")
    MessageChannel standardOrders() {
        return new DirectChannel();
    }

    // Flow 1: validate, sau đó chọn channel theo priority.
    @Bean
    IntegrationFlow orderRouterFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(OrderEvent.class,
                        order -> order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amount() != null
                                && order.amount().signum() > 0
                                && order.priority() != null,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .route(OrderEvent.class, OrderEvent::priority,
                        router -> router
                                .channelMapping(
                                        "EXPRESS", "orders.express")
                                .channelMapping(
                                        "STANDARD", "orders.standard")
                                .resolutionRequired(true))
                .get();
    }

    // Flow 2: riêng cho đơn EXPRESS.
    @Bean
    IntegrationFlow expressFlow(RouteRecorder recorder) {
        return IntegrationFlow.from("orders.express")
                .transform(OrderEvent.class,
                        order -> new DispatchCommand(
                                order.orderId(),
                                "EXPRESS",
                                order.amount()))
                .handle(DispatchCommand.class, (command, headers) -> {
                    recorder.record(new RoutedOrder(
                            command.orderId(),
                            command.lane(),
                            (String) headers.get("correlationId")));
                    return null; // nhánh outbound một chiều
                })
                .get();
    }

    // Flow 3: riêng cho đơn STANDARD.
    @Bean
    IntegrationFlow standardFlow(RouteRecorder recorder) {
        return IntegrationFlow.from("orders.standard")
                .transform(OrderEvent.class,
                        order -> new DispatchCommand(
                                order.orderId(),
                                "STANDARD",
                                order.amount()))
                .handle(DispatchCommand.class, (command, headers) -> {
                    recorder.record(new RoutedOrder(
                            command.orderId(),
                            command.lane(),
                            (String) headers.get("correlationId")));
                    return null; // nhánh outbound một chiều
                })
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "orders.input")
interface OrderGateway {
    void submit(
            @Payload OrderEvent event,
            @Header("correlationId") String correlationId);
}

record OrderEvent(String orderId, String priority, BigDecimal amount) {}

record DispatchCommand(String orderId, String lane, BigDecimal amount) {}

record RoutedOrder(String orderId, String lane, String correlationId) {}

@Component
class RouteRecorder {
    private final List<RoutedOrder> received =
            new CopyOnWriteArrayList<>();

    void record(RoutedOrder order) {
        received.add(order);
        System.out.println("Routed: " + order);
    }

    List<RoutedOrder> snapshot() {
        return List.copyOf(received);
    }

    void clear() {
        received.clear();
    }
}
~~~

### 4.3. Phân tích đường đi

Mỗi bean `IntegrationFlow` chỉ giữ một trách nhiệm:

- `orderRouterFlow` nhận `Message<OrderEvent>` từ `orders.input`, kiểm tra hợp đồng rồi lấy `priority` làm routing key.
- Mapping `EXPRESS → orders.express` gửi đơn đến đầu vào của `expressFlow`.
- Mapping `STANDARD → orders.standard` gửi đơn đến đầu vào của `standardFlow`.
- Mỗi nhánh chuyển `OrderEvent` thành `DispatchCommand`; handler ghi một `RoutedOrder` chứa nhánh xử lý và `correlationId`.
- Handler trả `null`: nhánh kết thúc một chiều, không có reply nghiệp vụ cho caller.

Spring Integration đăng ký `OrderGateway` thành proxy nhờ `@IntegrationComponentScan`. Nếu caller gọi:

~~~java
gateway.submit(
        new OrderEvent(
                "ORD-1001", "EXPRESS", new BigDecimal("250000")),
        "trace-ord-1001");
~~~

thì `RouteRecorder` có một bản ghi:

~~~text
RoutedOrder[
    orderId=ORD-1001,
    lane=EXPRESS,
    correlationId=trace-ord-1001
]
~~~

Hai nhánh không được gọi cùng lúc cho một message `EXPRESS`. Trong mã ví dụ, các channel là `DirectChannel` nên router, transformer và handler thường chạy trên thread gửi message. Method gateway `void` vẫn có thể bị chặn đến khi chuỗi xử lý đồng bộ hoàn tất.

### 4.4. Vì sao nên chia thành các flow bean riêng?

Nếu mỗi nhánh có thêm endpoint như HTTP outbound gateway, JMS publisher, SFTP writer hoặc JDBC handler, tách thành các `IntegrationFlow` riêng giúp dễ thay đổi độc lập và kiểm thử hợp đồng. Router chỉ cần biết tên các **channel đích**, không cần biết endpoint downstream dùng giao thức nào.

Khi dùng chung phần xử lý, có thể tạo một **channel hội tụ** mà cả hai nhánh gửi vào sau khi chuẩn hóa payload. Khi đó phải xác định liệu message nào cần giữ thứ tự, có cần aggregation không và consumer ở channel chung có nhận cùng kiểu payload hay không.

## 5. Kiểm thử từng nhánh và khóa không được hỗ trợ

Để chứng minh router và các endpoint thực sự được Spring đăng ký, hãy gọi qua `OrderGateway` trong integration test thay vì gọi trực tiếp method cấu hình bean.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo tệp `RoutingApplicationTest.java` cùng package `demo.routing`:

~~~java
package demo.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessagingException;

@SpringBootTest
class RoutingApplicationTest {

    @Autowired
    OrderGateway gateway;

    @Autowired
    RouteRecorder recorder;

    @BeforeEach
    void reset() {
        recorder.clear();
    }

    @Test
    void expressGoesOnlyToExpressEndpoint() {
        gateway.submit(
                new OrderEvent(
                        "ORD-E1", "EXPRESS", new BigDecimal("100")),
                "trace-express");

        assertEquals(
                List.of(new RoutedOrder(
                        "ORD-E1", "EXPRESS", "trace-express")),
                recorder.snapshot());
    }

    @Test
    void standardGoesOnlyToStandardEndpoint() {
        gateway.submit(
                new OrderEvent(
                        "ORD-S1", "STANDARD", new BigDecimal("200")),
                "trace-standard");

        assertEquals(
                List.of(new RoutedOrder(
                        "ORD-S1", "STANDARD", "trace-standard")),
                recorder.snapshot());
    }

    @Test
    void rejectsUnsupportedPriority() {
        assertThrows(MessagingException.class,
                () -> gateway.submit(
                        new OrderEvent(
                                "ORD-X1", "SAME_DAY",
                                new BigDecimal("300")),
                        "trace-unknown"));

        assertTrue(recorder.snapshot().isEmpty());
    }

    @Test
    void rejectsInvalidAmount() {
        assertThrows(MessagingException.class,
                () -> gateway.submit(
                        new OrderEvent(
                                "ORD-X2", "EXPRESS", BigDecimal.ZERO),
                        "trace-invalid"));

        assertTrue(recorder.snapshot().isEmpty());
    }
}
~~~

Hai test thành công kiểm tra routing key, channel mapping và handler từng nhánh. Hai test lỗi kiểm tra **dữ liệu sai không bị phát tới endpoint nghiệp vụ**. Với cấu hình filter/router trên `DirectChannel`, lỗi thường được lan về caller dưới dạng `MessagingException` hoặc một subtype/exception có nguyên nhân gốc là lỗi định tuyến/loại message.

Nếu trong dự án thực tế có tầng proxy khác bọc exception, hãy kiểm tra cause chain theo hợp đồng thay vì phụ thuộc vô điều kiện vào một lớp exception ngoài cùng. Test ví dụ không chứng minh delivery tới hệ thống ngoài bởi `RouteRecorder` chỉ là bean trong bộ nhớ.

## 6. Định tuyến theo header thay cho payload

Ngoài `priority` trong payload, router có thể dùng metadata như `tenantId`, `sourceSystem`, `eventType` hoặc mã hệ thống đích. Đây là phương án hữu ích khi payload đã chuẩn hóa nhưng tuyến xử lý phụ thuộc nguồn/giao thức.

Ví dụ logic khái niệm:

~~~text
Message<UnifiedEvent>
    payload = UnifiedEvent(...)
    headers.routeCode = "billing"

routeCode="billing"  -> events.billing
routeCode="shipping" -> events.shipping
routeCode=khác       -> events.unsupported
~~~

Một phương án là khai báo `@Router` trên method của Spring bean:

~~~java
@Component
class OrderDestinationRouter {

    @Router(inputChannel = "orders.ready")
    public String selectDestination(OrderEvent order) {
        return switch (order.priority()) {
            case "EXPRESS" -> "orders.express";
            case "STANDARD" -> "orders.standard";
            default -> "orders.unsupported";
        };
    }
}
~~~

Snippet này giả định có import `org.springframework.integration.annotation.Router`, kiểu `OrderEvent` như mục 4, bean channel cho `orders.ready` và consumer cho ba channel đích. Đây là **một phương án thay thế** cho router Java DSL, không đăng ký đồng thời trên cùng channel với router khác khi không có ý định tạo nhiều consumer.

Method ở trên trả **tên channel đích**. Nếu chỉ muốn trả routing key, có thể dùng cơ chế mapping sang channel của router tương ứng; không nên nhầm chuỗi `"EXPRESS"` với tên bean `"orders.express"`.

### 6.1. Header do bên ngoài cung cấp phải được kiểm tra

Dùng header giúp không phải chạm đến payload, nhưng đồng thời tạo nguy cơ để dữ liệu đầu vào quyết định đường đi nội bộ. Chẳng hạn, không nên viết code cho phép một HTTP header tùy ý trở thành tên bean channel để gửi vào endpoint quản trị.

Nên thực hiện:

1. Parse/normalize header theo một tập giá trị hỗ trợ.
2. Xác thực quyền truy cập hoặc tenant nếu việc routing liên quan dữ liệu nhạy cảm.
3. Mapping key nghiệp vụ sang channel nội bộ theo cấu hình cố định.
4. Ghi log correlation ID và routing decision, nhưng tránh log secrets hoặc toàn bộ payload.
5. Định nghĩa fallback cho header thiếu, null hoặc không hợp lệ.

## 7. Nhánh mặc định và chiến lược xử lý message không khớp

Ví dụ đầu bài dùng `resolutionRequired(true)`: khi router không tìm được channel hợp lệ, nó phải báo lỗi. Trong các hệ thống tích hợp nhiều đối tác, cách khác là gửi message sang **channel chưa được hỗ trợ**.

Một dạng cấu hình Java DSL minh họa:

~~~java
.route(OrderEvent.class, OrderEvent::priority,
        router -> router
                .channelMapping("EXPRESS", "orders.express")
                .channelMapping("STANDARD", "orders.standard")
                .defaultOutputChannel("orders.unsupported"))
~~~

Snippet được dùng **thay thế** phần `.route(...)` của ví dụ mục 4 và yêu cầu có bean channel `orders.unsupported` cùng consumer tương ứng.

Lúc đó:

~~~mermaid
flowchart TD
    R{"priority"}
    E["orders.express"]
    S["orders.standard"]
    U["orders.unsupported<br/>quarantine / audit"]
    R -->|"EXPRESS"| E
    R -->|"STANDARD"| S
    R -->|"Khác / không khớp"| U
~~~

Một handler ở nhánh `orders.unsupported` có thể lưu message vào bảng lỗi, dead-letter queue hoặc file quarantine để kiểm tra. **Không nên trả kết quả thành công** chỉ vì message được nhận vào fallback channel nếu mục đích fallback là lưu lỗi.

Cần phân biệt hai trường hợp:

- **Khóa không có mapping**: router chưa biết đi đâu, nên fail hoặc fallback.
- **Channel có mapping nhưng không gửi được**: ví dụ subscriber dừng, queue đầy, adapter đích lỗi. Đây là **dispatch/delivery failure**, không nhất thiết được xử lý chỉ bằng default channel. Cần chính sách lỗi của endpoint, retry/advice và error channel thích hợp.

Đặc biệt với `QueueChannel`, việc gửi vào queue thành công chỉ cho thấy message đã được lưu trong queue ở thời điểm đó; nó không khẳng định consumer hay hệ thống ngoài xử lý xong.

## 8. Định tuyến qua nhiều endpoint bằng XML namespace

XML namespace là cách diễn đạt tương đương khi dự án đã có cấu hình Spring Integration XML.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orders.input"/>
    <int:channel id="orders.express"/>
    <int:channel id="orders.standard"/>

    <int:router input-channel="orders.input"
                expression="payload.priority">
        <int:mapping value="EXPRESS" channel="orders.express"/>
        <int:mapping value="STANDARD" channel="orders.standard"/>
    </int:router>

    <!-- Service activator hoặc flow consumer của mỗi nhánh
         được cấu hình riêng. -->
</beans>
~~~

Router dùng expression để lấy khóa từ payload. Với `OrderEvent` dạng Java record, cú pháp truy cập property trong SpEL có thể phụ thuộc hỗ trợ introspection và phiên bản; trong dự án thực tế có thể đặt method getter/bean converter rõ ràng nếu parser không truy cập được property như mong đợi. Các mapping cũng yêu cầu channel đích tồn tại và có consumer.

Ví dụ router theo **header**:

~~~xml
<int:header-value-router input-channel="events.input"
                         header-name="routeCode">
    <int:mapping value="billing" channel="events.billing"/>
    <int:mapping value="shipping" channel="events.shipping"/>
</int:header-value-router>
~~~

Đây là ví dụ riêng; `events.input`, `events.billing` và `events.shipping` cần các bean channel và consumer tương ứng.

Với Spring Boot, có thể nạp XML qua `@ImportResource("classpath:integration/routing.xml")`. Tránh vô tình đăng ký **XML router và Java DSL router cùng nhận một DirectChannel** khi mục tiêu là chỉ định một đường xử lý duy nhất.

## 9. Router khác PublishSubscribeChannel và Recipient List Router thế nào?

Yêu cầu **"qua nhiều endpoint"** có thể mang hai nghĩa rất khác nhau:

1. Một message chỉ chọn **một** endpoint trong số nhiều endpoint.
2. Một message cần được phát tới **nhiều** endpoint cùng lúc.

Content-Based Router trong ví dụ chọn một nhánh theo `priority`. Nếu yêu cầu là cùng một event đi tới hệ thống audit **và** hệ thống phân tích, cần cơ chế fan-out như `PublishSubscribeChannel` hoặc **Recipient List Router** có điều kiện nhận riêng.

~~~mermaid
flowchart LR
    A["Message<OrderEvent>"]
    R{"Content-Based Router"}
    E["Express endpoint"]
    S["Standard endpoint"]
    P["PublishSubscribeChannel"]
    AUD["Audit endpoint"]
    MET["Metrics endpoint"]
    A --> R
    R -->|"EXPRESS"| E
    R -->|"STANDARD"| S
    A --> P
    P --> AUD
    P --> MET
~~~

| Nhu cầu | Thành phần thích hợp | Cần quan tâm |
| --- | --- | --- |
| Chọn một nhánh theo `priority` | Payload/router mapping. | Unknown key, lỗi branch, channel đích. |
| Chọn nhánh theo header nguồn | Header value router. | Validation và nguồn gốc header. |
| Phát cùng message tới mọi subscriber | `PublishSubscribeChannel`. | Lỗi một subscriber, thread, thứ tự gửi. |
| Phát tới tập recipient động | Recipient List Router. | Recipient nào bắt buộc, lỗi từng recipient, duplicate. |
| Tách danh sách đơn thành từng message | Splitter. | Correlation/sequence và hoàn tất nhóm. |
| Gom kết quả nhiều nhánh thành một reply | Aggregator hoặc cơ chế join có điều kiện. | Correlation, timeout, release strategy, state bền vững. |

Nếu nhiều branch cùng trả reply cho **một** gateway, cần thiết kế rõ aggregation hoặc chọn một reply cuối. Không nên đăng ký hai handler trả response trên cùng đường reply rồi mong framework tự kết hợp kết quả.

## 10. Routing khi flow cần request–reply

Router không nhất thiết kết thúc một chiều. Với messaging gateway hoặc HTTP inbound gateway, một request có thể đi qua router, được xử lý ở nhánh phù hợp rồi trả reply về caller ban đầu.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as @MessagingGateway
    participant R as Router
    participant S as Branch handler
    C->>G: query(OrderRequest)
    G->>R: Message + replyChannel
    R->>S: route theo loại request
    S-->>G: OrderResponse qua replyChannel
    G-->>C: OrderResponse
~~~

Mẫu handler ở hai nhánh có thể trả cùng kiểu DTO:

~~~java
@ServiceActivator(inputChannel = "quotes.domestic")
public QuoteResult domesticQuote(QuoteRequest request) {
    return new QuoteResult(request.id(), "DOMESTIC", 12000);
}

@ServiceActivator(inputChannel = "quotes.international")
public QuoteResult internationalQuote(QuoteRequest request) {
    return new QuoteResult(request.id(), "INTERNATIONAL", 55000);
}
~~~

Snippet này giả định `QuoteRequest`, `QuoteResult` và các channel được định nghĩa ở nơi khác; mỗi method nằm trong Spring bean. Gateway request–reply phải gửi vào channel dẫn đến router và trả `QuoteResult`.

Để reply trở lại caller, cần có đường trả về phù hợp: những header phục vụ `replyChannel`/correlation không bị mất qua transformer/router, và endpoint cuối thực sự phát response. Nếu một nhánh chỉ gọi outbound adapter một chiều hoặc method trả `void`, gateway đợi DTO có thể chờ đến timeout.

**Output channel và reply channel có vai trò khác nhau:** router gửi request vào channel nhánh được chọn; `replyChannel` thường là thông tin của **request cụ thể**. Với reply chung của nhiều caller, phải xử lý correlation và timeout rõ ràng, tránh trả nhầm kết quả giữa các request.

## 11. Loại channel ảnh hưởng đến hiệu năng và lỗi routing

Router quyết định **channel nào**, còn channel và endpoint quyết định **message được bàn giao như thế nào**.

| Channel nhánh | Cách chạy phổ biến | Khi nào cân nhắc |
| --- | --- | --- |
| `DirectChannel` | Gọi subscriber trong thread gửi. | Handler nhanh, cần đường lỗi đồng bộ. |
| `QueueChannel` | Đưa message vào hàng đợi để poll sau. | Cần buffer có giới hạn và đã thiết kế consumer/poller. |
| `ExecutorChannel` | Giao việc xử lý cho executor thread. | Cần cách ly độ trễ, đã giới hạn executor và xử lý lỗi. |
| `PublishSubscribeChannel` | Gửi message tới nhiều subscriber. | Fan-out có chủ đích; không chỉ là chọn một branch. |

Giả sử `orders.express` dùng `DirectChannel` và handler gọi API giao hàng mất 8 giây. Khi caller gửi `EXPRESS` qua gateway `void`, lời gọi Java vẫn có thể mất 8 giây do xử lý đồng bộ. Router **không tự biến endpoint thành bất đồng bộ**.

Nếu `orders.express` là `QueueChannel`, message có thể chờ trong queue. Khi đó cần poller ở endpoint nhận, quản lý capacity, backlog và retry. `QueueChannel` mặc định lưu bộ đệm trong bộ nhớ; nếu yêu cầu bền vững sau restart, phải bổ sung message store hoặc dùng broker có delivery semantics phù hợp.

### 11.1. Thứ tự và transaction qua router

Một route dùng cùng `DirectChannel` có thể giữ đường xử lý trên cùng thread, nhưng thứ tự giữa **hai nhánh khác nhau** không tự được bảo đảm nếu chúng có worker/poller độc lập. Đặc biệt, chuyển qua queue, executor hoặc broker có thể thay đổi thứ tự quan sát và ranh giới transaction.

Với thanh toán hoặc cập nhật tồn kho, không dùng giả định "message trước sẽ luôn hoàn tất trước" khi các branch xử lý song song. Nếu thứ tự quan trọng, cần key/partition, serialization, locking hoặc transactional processing theo yêu cầu.

Router không mở transaction bao phủ cả JMS, HTTP và database. Nếu cần consistency giữa ghi DB và phát event broker, cân nhắc transactional outbox, saga/compensation hoặc đối soát.

## 12. Lỗi, retry và idempotency trong flow phân nhánh

Một flow có router có nhiều điểm lỗi:

~~~mermaid
flowchart TD
    S["Inbound adapter"]
    V{"Validate"}
    R{"Router chọn key"}
    E["Express branch"]
    N["Standard branch"]
    U["Unsupported / quarantine"]
    O["External endpoint"]
    ERR["Retry / Error flow / DLQ"]
    S --> V
    V -->|"Hợp lệ"| R
    V -->|"Sai"| ERR
    R -->|"EXPRESS"| E --> O
    R -->|"STANDARD"| N --> O
    R -->|"Không khớp"| U
    E -. "timeout" .-> ERR
    N -. "timeout" .-> ERR
~~~

| Loại lỗi | Vị trí | Hướng xử lý |
| --- | --- | --- |
| Payload sai schema | Trước router. | Validation rồi reject/quarantine; không thử lại vô hạn cùng payload sai. |
| Routing key không hỗ trợ | Tại router. | Fail fast hoặc default channel, ghi metric và thông tin nguồn. |
| Channel đích không có consumer | Dispatch sang branch. | Kiểm tra topology/startup, cảnh báo và điều kiện retry. |
| HTTP/JMS/Kafka/SFTP/DB endpoint lỗi | Tại branch. | Client retry/backoff, dead-letter và xác nhận giao thức. |
| Kết quả không rõ sau timeout | Tại side effect bên ngoài. | Đối soát bằng business key, idempotency tại đích. |
| Một nhánh xử lý trễ | Queue/executor của branch. | Giới hạn backlog, quản lý thread và timeout. |

### 12.1. Vì sao retry có thể làm sai đường đi?

Giả sử đơn `ORD-1001` đã đi nhánh `EXPRESS` và hệ thống đối tác tạo shipment. Response bị mất, upstream retry cùng message. Nếu logic router sử dụng dữ liệu mutable (chẳng hạn thuộc tính priority bị cập nhật) thì retry có thể đi **nhánh khác**, tạo hai side effect.

Cần quyết định:

- Routing key có cố định theo event/command không?
- Có cần lưu **routing decision** trong metadata bền vững để replay đúng nhánh?
- Mỗi branch kiểm tra idempotency theo `eventId`/`orderId` như thế nào?
- Trạng thái nào được xem là "đã nhận", "đã gửi" và "đã hoàn tất nghiệp vụ"?

Đối với những sự kiện phải replay, có thể lưu route key đã được chuẩn hóa, correlation ID và phiên bản quy tắc định tuyến cùng record cần xử lý. Điều đó giúp tái hiện quyết định khi điều tra lỗi sau thay đổi cấu hình.

### 12.2. Error channel trong xử lý bất đồng bộ

Khi router và handler dùng `DirectChannel`, exception từ handler có thể lan trở lại sender/gateway theo call stack. Khi một branch đổi sang `QueueChannel`, `ExecutorChannel` hoặc listener broker, exception xuất hiện ở thread khác và có thể được chuyển thành `ErrorMessage` tới `errorChannel` theo cấu hình endpoint.

Không có một error channel tự động giải quyết mọi lỗi ở mọi tầng. Cần phân biệt lỗi source, lỗi phân tuyến, lỗi dispatch và lỗi adapter ngoài hệ thống; mỗi nhóm có chính sách retry và alert khác nhau.

## 13. Routing nhiều nguồn và nhiều giao thức

Trong module **SPRING_INTEGRATION_ADAPTERS**, router có thể nằm sau bước chuẩn hóa chung cho các adapter:

| Nguồn | Payload ban đầu | Bước chuẩn hóa | Khóa định tuyến / đích |
| --- | --- | --- | --- |
| File CSV hoặc SFTP | `File` hoặc byte[] | Parse CSV thành `OrderEvent`. | `priority` → express/standard. |
| HTTP inbound gateway | JSON/DTO request | Validate, map DTO và metadata. | `tenantId` hoặc `requestType` → service. |
| JMS/AMQP listener | Message broker payload | Convert/validate event. | `eventType` → xử lý đặt hàng/thanh toán. |
| Kafka inbound | Record có topic, partition, key | Deserialize, kiểm tra schema. | Business key → flow phù hợp. |
| JDBC polling | `Map`/record dữ liệu | Chuyển thành DTO miền. | `status` hoặc loại nghiệp vụ → handler. |

Ví dụ nhiều nguồn đưa về một contract:

~~~mermaid
flowchart LR
    F["File/SFTP"]
    J["JMS/AMQP"]
    K["Kafka"]
    H["HTTP"]
    N["Normalize → OrderEvent"]
    C["orders.input"]
    R{"Router"}
    EX["Express flow"]
    ST["Standard flow"]
    F --> N
    J --> N
    K --> N
    H --> N
    N --> C --> R
    R --> EX
    R --> ST
~~~

Mỗi adapter vẫn chịu trách nhiệm về kết nối, acknowledgement, offset/polling, retry nguồn và đóng tài nguyên. Router chỉ nhận message đã có contract đúng. **Không dùng router để che giấu sự khác biệt schema giữa các nguồn:** nên parse và normalize trước khi routing.

### 13.1. Header kỹ thuật và header nghiệp vụ

Các header của framework như `replyChannel`, `errorChannel` hoặc header đặc thù Kafka/JMS không luôn truyền nguyên vẹn qua boundary HTTP/broker. Khi route dựa vào một header như `tenantId`, phải chắc rằng bước converter/mapper thật sự tạo và duy trì header đó.

Nên dùng routing key ổn định mang ý nghĩa nghiệp vụ và kiểm thử mapping. Không phụ thuộc tùy tiện vào tên header do connector đời cũ sử dụng, vì các module/giao thức có thể thay đổi cách map headers theo phiên bản.

## 14. Khuyến nghị thiết kế khi số nhánh tăng

Một router gồm hai mapping rất dễ hiểu. Khi lên tới hàng chục đối tác và nhiều luồng nghiệp vụ, cần giữ topology rõ ràng.

1. **Chuẩn hóa khóa trước:** tránh một nhánh dùng `"Express"`, nhánh khác dùng `"EXPRESS"`, còn source khác gửi `" express "`.
2. **Đặt tên channel theo mục đích:** `orders.express`, `orders.standard` hoặc `payments.review` dễ quan sát hơn những tên kiểu `channel1`.
3. **Giữ logic routing thuần túy:** nếu rule phức tạp, đưa vào service có thể unit test, rồi để router chỉ thực hiện map kết quả sang channel.
4. **Không để downstream thiếu consumer:** mỗi mapping cần có endpoint hợp lệ khi context khởi động.
5. **Có chiến lược unknown key:** fail, fallback hoặc quarantine với mã lỗi và metric.
6. **Đo riêng từng branch:** số lượng, độ trễ, failure rate, queue depth, retry và xác nhận đích.
7. **Lập phiên bản hợp đồng:** khi thêm route key mới, phải tính đến các instance đang chạy phiên bản cũ.
8. **Giới hạn chi phí fan-out:** nếu cần gửi nhiều recipient, cần đo và xử lý lỗi từng nhánh, không nhầm với router chọn một nhánh.

Trong hệ thống lớn, rule định tuyến có thể đến từ cấu hình hoặc database; điều đó đòi hỏi cơ chế quản lý thay đổi, kiểm tra trước khi áp dụng và xử lý cache/version. Không để mỗi message truy cập database cấu hình từ xa mà không có timeout hoặc fallback, vì router sẽ trở thành điểm nghẽn mới.

## 15. Lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| Message đi vào router nhưng không thấy handler nào chạy. | Routing key không có mapping, channel đích không có subscriber, endpoint dừng. | Log key đã normalize, kiểm tra mapping, bean channel và consumer. |
| Mọi đơn đều đi nhánh STANDARD. | Expression/mapper lấy sai trường; default route được dùng quá rộng. | Test từng key; đo số message vào fallback và cảnh báo bất thường. |
| Một message chỉ đến một trong hai handler dù muốn cả hai. | Dùng content router hoặc DirectChannel thay cho multicast. | Dùng PublishSubscribeChannel/RecipientListRouter với semantics rõ ràng. |
| Một message vào cả hai nhánh ngoài ý muốn. | Vô tình cấu hình fan-out hoặc hai inbound source phát cùng event. | Kiểm tra topology, dedup và routing rules. |
| Caller bị timeout sau khi gửi vào branch. | Branch kết thúc one-way nhưng gateway chờ reply hoặc replyChannel mất. | Quy định one-way/request–reply, bảo toàn headers và tạo reply đúng. |
| Queue có message nhưng handler không nhận. | Nhánh dùng QueueChannel nhưng thiếu poller. | Tạo polling consumer và giám sát queue depth. |
| Source xử lý chậm bất ngờ. | Nhánh DirectChannel chứa HTTP/DB call blocking. | Timeout client, backpressure hoặc async có giới hạn. |
| Retry tạo bản ghi trùng ở đối tác. | Side effect đã thành công nhưng response bị mất. | Idempotency key, unique constraint và đối soát. |
| Message đi nhánh khác sau restart/replay. | Routing key hoặc rule thay đổi. | Lưu rule version/route decision và cố định key cần thiết. |
| XML và Java DSL router cùng nhận một input channel. | Đăng ký hai endpoint cạnh tranh mà không chủ đích. | Chọn một router hoặc thiết kế dispatch/fan-out rõ ràng. |
| Lỗi không trở lại caller. | Nhánh chạy trên thread executor/broker khác. | Error flow, DLQ, retry và contract phản hồi bất đồng bộ. |

## 16. Bài thực hành: định tuyến đơn hàng đến ba endpoint

**Bối cảnh:** một ứng dụng nhận đơn hàng từ SFTP CSV và API HTTP. Sau khi chuẩn hóa thành `OrderEvent`, cần route theo `priority` và `currency`:

- `EXPRESS` + `VND`: gửi tới dịch vụ giao nhanh trong nước.
- `EXPRESS` + currency khác: gửi tới dịch vụ giao quốc tế.
- `STANDARD`: gửi tới xử lý hàng tiêu chuẩn.
- Giá trị thiếu/không hỗ trợ: đưa vào channel kiểm duyệt.

**Nhiệm vụ thực hiện:**

1. Thiết kế DTO `OrderEvent(id, priority, currency, amount)` và các header `sourceSystem`, `correlationId`, `idempotencyKey`.
2. Tạo inbound channel `orders.input`, một bước validation và router chọn channel theo rule.
3. Đăng ký ba nhánh endpoint bằng các `IntegrationFlow` riêng; mỗi nhánh có transformer và handler mô phỏng outbound.
4. Thêm fallback channel `orders.review` có consumer lưu reason và payload metadata để kiểm tra.
5. Viết test cho cả ba nhánh thành công, cho dữ liệu sai, cho unknown key và kiểm tra message không bị gửi tới nhánh khác.
6. Chuyển nhánh quốc tế thành `QueueChannel` với polling consumer; đo thay đổi thời điểm gateway trả về và thời gian xử lý.
7. Mô phỏng timeout ở outbound sau khi đối tác đã nhận đơn, rồi thiết kế idempotency để replay không tạo shipment thứ hai.
8. Thử dùng một `PublishSubscribeChannel` riêng để gửi bản sao event thành công tới audit, trong khi vẫn chỉ có một nhánh fulfillment thực hiện side effect.

**Tiêu chí hoàn thành:** mapping rõ ràng, channel đích có consumer, lỗi không bị bỏ qua, header correlation không mất, test quan sát được đúng nhánh và giải thích được tính tin cậy khi request đi qua queue hoặc adapter ngoài.

## 17. Câu hỏi tự kiểm tra

1. Content-Based Router chọn channel đích dựa vào thông tin nào?
2. `.route(...)` khác `.transform(...)` và `.filter(...)` thế nào?
3. Vì sao channel mà router chọn cần có consumer tương ứng?
4. Khi khóa định tuyến không khớp, có những chính sách nào?
5. Router dựa trên header khác router dựa trên payload ở điểm nào?
6. Hai endpoint cần cùng nhận một message thì dùng loại channel hoặc pattern nào?
7. Nếu một nhánh có `QueueChannel`, cần cấu hình gì để message không nằm chờ mãi?
8. Khi routing trong flow request–reply, vì sao cần giữ `replyChannel`?
9. Vì sao gateway method `void` không bảo đảm xử lý bất đồng bộ?
10. Router có tự bảo đảm transaction giữa database và HTTP không?
11. Lỗi dispatch vào channel khác gì lỗi HTTP client của branch?
12. Khi replay event sau thay đổi rule, làm sao giữ tính nhất quán?
13. Làm thế nào kiểm tra mỗi key chỉ đi đến endpoint được định nghĩa?
14. Một channel chung nhận từ SFTP và Kafka cần quy ước payload/header ra sao?

**Gợi ý:** Router làm nhiệm vụ quyết định đường đi, còn channel/consumer và adapter quyết định thời điểm xử lý, error path, acknowledgement và side effect. Trước khi route, cần chuẩn hóa dữ liệu; sau khi route, phải kiểm thử từng nhánh và khả năng phục hồi.

## 18. Ghi nhớ

**Định tuyến flow qua nhiều endpoint** là cách Spring Integration phân phối message tới nhánh phù hợp dựa trên payload hoặc headers. Với Java DSL, một `IntegrationFlow.route(...)` có thể mapping khóa nghiệp vụ sang các channel; mỗi channel bắt đầu một flow hoặc endpoint riêng. Annotation `@Router` và XML namespace cung cấp cách cấu hình tương đương.

Trong module **SPRING_INTEGRATION_ADAPTERS**, router có thể đứng sau adapter file/SFTP, HTTP, JMS, AMQP, Kafka hoặc JDBC, nhưng chất lượng luồng phụ thuộc vào **hợp đồng message, channel mapping, nhánh mặc định, reply/error handling, thread/transaction và idempotency**. Một sơ đồ routing đúng phải chỉ ra được mỗi message đi đâu, ai tiếp nhận, khi lỗi thì phục hồi thế nào và khi nào mới thật sự coi thao tác outbound là thành công.

