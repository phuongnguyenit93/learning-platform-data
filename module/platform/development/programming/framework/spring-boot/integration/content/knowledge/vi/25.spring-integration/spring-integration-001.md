# Spring Integration và các mẫu tích hợp doanh nghiệp

## Mục tiêu và bối cảnh

Khi một hệ thống Spring Boot vừa nhận HTTP request, vừa đọc database, gọi dịch vụ ngoài, cập nhật cache và phát thông điệp qua broker, mã xử lý rất dễ trở thành một chuỗi lời gọi phụ thuộc chặt vào nhau. Một thay đổi nhỏ ở định dạng dữ liệu, cơ chế retry hay thứ tự xử lý có thể ảnh hưởng nhiều adapter.

**Spring Integration** cung cấp một mô hình kết nối các thành phần bằng **message**, **channel** và **endpoint**, triển khai nhiều *Enterprise Integration Patterns* (EIP). Thay vì tự viết toàn bộ cơ chế chuyển tiếp, lọc, biến đổi và định tuyến, ứng dụng cấu hình một **integration flow** gồm các bước có trách nhiệm rõ ràng.

Bài học thuộc module **SPRING_BOOT_INTEGRATION** và chương **Spring Integration**. Mục tiêu của module là tổ chức tích hợp qua HTTP client, database, cache, message broker và các adapter, với trọng tâm là cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng thực tế.

Sau bài này, bạn có thể:

- Giải thích `Message`, `MessageChannel`, endpoint và integration flow liên hệ với nhau như thế nào.
- Nhận biết các mẫu EIP cơ bản: Gateway, Transformer, Filter, Router, Splitter, Aggregator, Service Activator và Channel Adapter.
- Tạo một flow bằng Spring Integration Java DSL trong Spring Boot.
- Chọn channel đồng bộ, bất đồng bộ hoặc có hàng đợi theo yêu cầu nghiệp vụ.
- Thiết kế ranh giới lỗi, giao dịch, idempotency, retry, bảo mật và kiểm thử.

> **Phạm vi:** Spring Integration giúp kết nối và điều phối các bước tích hợp. Một channel trong cùng JVM **không tự biến thành message broker bền vững**, và một flow **không tự bảo đảm exactly-once, giao dịch phân tán hay xử lý đúng thứ tự**.

## 1. Bài toán tích hợp doanh nghiệp và tư duy EIP

Xét một hệ thống nhận sự kiện `OrderReceived` từ API nội bộ:

1. Tiếp nhận sự kiện với `eventId`, `orderId` và giá trị đơn hàng.
2. Kiểm tra hợp lệ và chuẩn hóa dữ liệu.
3. Phân luồng đơn hàng theo loại hoặc ngưỡng giá trị.
4. Lưu trạng thái đơn hàng vào database, phát sự kiện cho hệ thống giao hàng.
5. Xử lý lỗi kết nối, retry an toàn và tránh xử lý lại sự kiện đã áp dụng.
6. Theo dõi thời gian xử lý, số lần thất bại và sự kiện tồn đọng.

Nếu ghép tất cả vào một HTTP controller, mã của controller sẽ phải biết cả cấu trúc dữ liệu, broker, chính sách lỗi và giao dịch. EIP mô tả các vai trò riêng trong đường đi của thông điệp.

~~~mermaid
flowchart LR
    A["HTTP / broker / file"] --> B["Inbound adapter / Gateway"]
    B --> C["Message channel"]
    C --> D["Filter & Transformer"]
    D --> E{"Router"}
    E -->|"Đơn thường"| F["Order handler"]
    E -->|"Đơn ưu tiên"| G["Priority handler"]
    F --> H["DB + outbox"]
    G --> H
    H --> I["Broker outbound adapter"]
    D -.-> J["Error handling / observability"]
    E -.-> J
~~~

Hình trên là **kiến trúc tham chiếu**, không có nghĩa các thành phần tự động cung cấp retry, outbox hay transaction. Những chính sách đó phải được cấu hình và kiểm chứng riêng.

Các khái niệm quan trọng:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Message** | Mang payload cùng headers | `OrderReceived` + `eventId`, `correlationId` |
| **Channel** | Kết nối các bước, định nghĩa cách bàn giao message | `DirectChannel`, `QueueChannel` |
| **Endpoint** | Nhận message và gọi logic xử lý, biến đổi, định tuyến hoặc I/O | Service Activator, Transformer |
| **Gateway** | Cho mã nghiệp vụ gọi flow qua interface | `orderGateway.submit(order)` |
| **Channel Adapter** | Kết nối nguồn/đích bên ngoài với luồng message | HTTP, file, JDBC, Kafka |
| **IntegrationFlow** | Khai báo các channel/endpoint và đường đi giữa chúng | Java DSL `IntegrationFlow.from(...)` |

**Phân biệt với broker:** Spring Integration có thể làm việc với RabbitMQ, Kafka, JMS và nhiều transport khác thông qua adapter. Bản thân `DirectChannel` hay `QueueChannel` mặc định chỉ hoạt động bên trong ứng dụng. Không được giả định một message đã `send()` thành công vào channel nội bộ thì đã tồn tại an toàn trên đĩa hoặc tới hệ thống ngoài.

## 2. Message, headers và hợp đồng dữ liệu

Trong Spring Messaging, một thông điệp có hình thức `Message<T>`, gồm:

- **Payload:** nội dung nghiệp vụ có kiểu dữ liệu rõ ràng, chẳng hạn `OrderReceived`.
- **Headers:** metadata phục vụ routing, tương quan request, reply, error, transport hoặc quan sát.

Ví dụ tạo message:

~~~java
import java.math.BigDecimal;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderReceived> message =
        MessageBuilder.withPayload(
                new OrderReceived(
                        "evt-1001",
                        "ORD-42",
                        new BigDecimal("129.00")))
                .setHeader("tenantId", "tenant-a")
                .setHeader("correlationId", "corr-42")
                .build();
~~~

Đối tượng `OrderReceived` sẽ được định nghĩa ở phần ví dụ Java DSL. Header `id` và `timestamp` do hạ tầng message tạo ra phục vụ việc định danh message **trong quá trình xử lý**, không thay thế `eventId` do hệ thống nguồn cấp để chống xử lý trùng lặp xuyên các lần gửi lại.

Một số header có ý nghĩa hạ tầng:

| Header | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `id`, `timestamp` | Metadata của message | Không dùng làm khóa idempotency xuyên transport nếu message được tái tạo |
| `replyChannel` | Nơi gửi phản hồi của luồng request-reply | Có thể là tham chiếu channel tạm thời |
| `errorChannel` | Nơi định tuyến lỗi ở các ngữ cảnh hỗ trợ | Phải kiểm tra lỗi đồng bộ và bất đồng bộ khác nhau |
| `correlationId` | Ghép các message có liên quan | Chỉ tin giá trị khi nguồn đã được kiểm soát |
| `sequenceNumber`, `sequenceSize` | Hỗ trợ nhóm message khi split/aggregate | Không thay thế hợp đồng thứ tự của broker |
| Header ứng dụng như `tenantId` | Truyền ngữ cảnh phục vụ xử lý | Xác thực/ủy quyền trước khi tin, tránh rò rỉ sang đích khác |

Spring Messaging cung cấp kiểu `Message` bất biến theo hướng không thay thế payload/headers trực tiếp, nhưng đối tượng nằm trong payload vẫn có thể mutable. Ưu tiên DTO/record bất biến. Khi cần thay payload hoặc header, dùng `MessageBuilder.fromMessage(...)` hoặc bước Transformer/Header Enricher; không sửa trực tiếp dữ liệu đang được nhiều nhánh sử dụng.

Hợp đồng tích hợp tốt cần nói rõ: schema và version, trường bắt buộc, đơn vị tiền tệ, timezone, điều kiện chấp nhận, chiến lược tương thích ngược, cơ chế xác định sự kiện trùng, ý nghĩa của thất bại và khả năng gửi lại.

## 3. Cài đặt và tích hợp với Spring Boot

Trong ứng dụng Spring Boot dùng Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

Starter cung cấp các thành phần cốt lõi cần để tạo integration flow. **Adapter của từng giao thức** có thể cần dependency riêng, ví dụ `spring-integration-http`, `spring-integration-jdbc`, `spring-integration-amqp` hoặc `spring-integration-kafka`, ngoài client/broker và cấu hình kết nối tương ứng. Không cần thêm mọi adapter nếu flow chỉ xử lý message nội bộ.

Spring Boot cung cấp auto-configuration cho Spring Integration và khởi tạo hạ tầng khi dependency phù hợp có trên classpath. Trong một ứng dụng Spring Framework thuần không dùng Boot, cấu hình thường cần `@EnableIntegration` tường minh.

Để Spring tìm những interface mang `@MessagingGateway` trong cùng package hoặc package con, thêm `@IntegrationComponentScan` vào một lớp cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;

@Configuration(proxyBeanMethods = false)
@IntegrationComponentScan
public class IntegrationGatewayScanConfiguration {
}
~~~

`@ComponentScan` thông thường không đăng ký proxy cho interface `@MessagingGateway` chỉ bằng cơ chế quét class. Nếu interface không nằm trong package được scan, cung cấp `basePackageClasses`/`basePackages` thích hợp hoặc import interface theo cơ chế được phiên bản Spring Integration hỗ trợ.

**Lưu ý API:** các ví dụ Java DSL dùng `IntegrationFlow.from(...)` của Spring Integration hiện đại (dòng 6.x/7.x). Tài liệu cũ có thể dùng `IntegrationFlows.from(...)`. Khi sao chép snippet từ bài viết cũ, đối chiếu với phiên bản Spring Integration mà bản Spring Boot đang quản lý; tránh tự ghi đè version thư viện.

## 4. Ví dụ xuyên suốt: tạo flow xử lý sự kiện đơn hàng

Giả sử hệ thống có một cổng nhận `OrderReceived` và một adapter nghiệp vụ `OrderHandler`. Ví dụ này chỉ dùng module Spring Integration core và có thể chạy đồng bộ trong một process. Phần lưu DB/broker là trách nhiệm của adapter thực tế, chưa được đưa vào snippet.

### 4.1. Định nghĩa dữ liệu

~~~java
// OrderReceived.java
import java.math.BigDecimal;

public record OrderReceived(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

~~~java
// NormalizedOrder.java
import java.math.BigDecimal;

public record NormalizedOrder(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

Hai DTO này minh họa **hợp đồng đầu vào** và **dữ liệu đã chuẩn hóa**. Một hệ thống thực nên có schema/version, xác định currency và quy tắc validation rõ ràng hơn.

### 4.2. Tạo messaging gateway

~~~java
// OrderEventGateway.java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrderEventGateway {
    void submit(OrderReceived event);
}
~~~

Spring Integration tạo implementation proxy cho interface gateway. Code nghiệp vụ chỉ gọi:

~~~java
orderEventGateway.submit(
        new OrderReceived(
                "evt-1001", " ORD-42 ",
                new java.math.BigDecimal("129.00")));
~~~

Với flow `DirectChannel` đồng bộ như bên dưới, lời gọi thường chỉ trả về sau khi các handler hoàn thành; exception của handler có thể lan về caller. **Phương thức `void` không có nghĩa là message đã được lưu bền vững hoặc xử lý bất đồng bộ.**

### 4.3. Tạo Transformer và handler nghiệp vụ

~~~java
// OrderNormalizer.java
import org.springframework.stereotype.Component;

@Component
public class OrderNormalizer {

    public NormalizedOrder normalize(OrderReceived source) {
        return new NormalizedOrder(
                source.eventId().trim(),
                source.orderId().trim(),
                source.amount());
    }
}
~~~

~~~java
// OrderHandler.java
import org.springframework.stereotype.Component;

@Component
public class OrderHandler {

    public void handle(NormalizedOrder order) {
        // Ví dụ: gọi application service để áp dụng lệnh nghiệp vụ.
        // Bản thực tế cần persistence/idempotency và xử lý lỗi.
        System.out.println("Đã nhận đơn: " + order.orderId());
    }
}
~~~

`System.out.println` chỉ được dùng để nhìn thấy flow hoạt động trong bài học. Hệ thống production cần logic nghiệp vụ thật và logging có cấu trúc, không ghi payload nhạy cảm tùy tiện.

### 4.4. Khai báo flow bằng Java DSL

~~~java
// OrderIntegrationConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow orderIntegrationFlow(
            OrderNormalizer normalizer,
            OrderHandler handler) {

        return IntegrationFlow.from("orders.input")
                .<OrderReceived>filter(
                        order -> order.eventId() != null
                                && !order.eventId().isBlank()
                                && order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amount() != null
                                && order.amount().signum() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                .handle(normalizer, "normalize")
                .handle(handler, "handle")
                .get();
    }
}
~~~

Cơ chế xử lý:

1. Gateway đưa `OrderReceived` vào channel tên `orders.input`.
2. **Filter** kiểm tra các điều kiện cơ bản; vì có `throwExceptionOnRejection(true)`, bản ghi không hợp lệ gây lỗi thay vì bị bỏ qua âm thầm.
3. **Transformer** gọi `OrderNormalizer.normalize(...)`, sinh `NormalizedOrder`.
4. **Service Activator** gọi `OrderHandler.handle(...)` để thực hiện xử lý cuối.
5. `get()` hoàn tất định nghĩa flow. Spring đăng ký các endpoint/channel cần thiết trong application context.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as OrderEventGateway
    participant F as Filter
    participant T as OrderNormalizer
    participant H as OrderHandler
    C->>G: submit(OrderReceived)
    G->>F: Message<OrderReceived>
    alt Hợp lệ
        F->>T: OrderReceived
        T->>H: NormalizedOrder
        H-->>G: Kết thúc xử lý
        G-->>C: return
    else Không hợp lệ
        F-->>G: Exception
        G-->>C: Exception
    end
~~~

Điểm đáng chú ý: flow dùng các channel `DirectChannel` giữa endpoint theo cơ chế mặc định của Java DSL, nên đường đi này **đồng bộ trong thread của caller**. Nó cho thấy EIP mà không che giấu điểm bắt đầu/hoàn thành thực sự của công việc.

### 4.5. Kết nối HTTP vào gateway khi cần

Nếu đã có `spring-boot-starter-web`, một MVC controller có thể nhận HTTP request rồi gọi gateway:

~~~java
// OrderEventController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderEventController {

    private final OrderEventGateway gateway;

    public OrderEventController(OrderEventGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/internal/order-events")
    public ResponseEntity<Void> receive(
            @RequestBody OrderReceived event) {
        gateway.submit(event);
        return ResponseEntity.noContent().build();
    }
}
~~~

Đoạn này có ý nghĩa **HTTP inbound → Gateway → flow**. Nó không sử dụng HTTP inbound channel adapter của Spring Integration và không làm lời gọi trở thành bất đồng bộ. Cần ánh xạ lỗi validation, lỗi nghiệp vụ và lỗi downstream sang HTTP status có chủ đích bằng cơ chế exception handling của ứng dụng. Chỉ trả `202 Accepted` khi có một cơ chế tiếp nhận bất đồng bộ đáng tin cậy tương ứng với hợp đồng API.

## 5. Các mẫu Enterprise Integration Patterns thường dùng

| EIP | Câu hỏi thiết kế | Cơ chế Spring Integration | Lưu ý |
| --- | --- | --- | --- |
| **Message Channel** | Chuyển message giữa các bước ra sao? | `MessageChannel`, `DirectChannel`, `QueueChannel` | Đồng bộ, độ bền và buffer phụ thuộc channel |
| **Messaging Gateway** | Logic nghiệp vụ gọi flow như thế nào? | `@MessagingGateway` / `@Gateway` | Có thể request-reply hoặc one-way |
| **Transformer** | Chuẩn hóa DTO/schema thế nào? | `transform(...)`, `@Transformer` | Cần hợp đồng khi chuyển version |
| **Filter** | Có chấp nhận message này không? | `filter(...)`, `@Filter` | Định nghĩa rõ discard hay exception |
| **Content-Based Router** | Message đi nhánh nào? | `route(...)`, `@Router` | Có default route, tránh mất message |
| **Service Activator** | Gọi logic nghiệp vụ ở đâu? | `handle(...)`, `@ServiceActivator` | Side effect cần transaction/idempotency |
| **Splitter** | Tách một payload thành nhiều phần? | `split(...)`, `@Splitter` | Theo dõi correlation/sequence |
| **Aggregator** | Khi nào gom đủ kết quả? | `aggregate(...)`, `@Aggregator` | MessageStore, release/expiry và phần đến muộn |
| **Publish-Subscribe** | Một sự kiện có nhiều consumer? | `PublishSubscribeChannel` | Không phải broker topic bền vững |
| **Wire Tap** | Quan sát/chép message sang nhánh khác? | `wireTap(...)` | Rủi ro dữ liệu nhạy cảm, thêm tải |
| **Channel Adapter** | Kết nối transport bên ngoài? | HTTP, JDBC, Kafka, AMQP, file... | Xác định ack/commit/error ở transport |
| **Idempotent Receiver** | Gửi lại có được áp dụng lần nữa không? | `IdempotentReceiverInterceptor` và store phù hợp | Phải chọn khóa ổn định, atomicity phù hợp |

### Filter khác Router thế nào?

**Filter** đưa ra quyết định *giữ hay loại* message. **Router** chọn một hoặc nhiều đường chuyển tiếp tùy nội dung hoặc header. Ví dụ:

- Filter: chỉ xử lý `amount > 0`.
- Router: `currency == "VND"` đến một nhánh, `currency == "USD"` đến nhánh khác.
- Transformer: chuẩn hóa `orderId` và đổi DTO ngoại vi thành DTO nội bộ.

Nếu filter không khai báo discard channel hay ném lỗi, message bị loại có thể không đi tiếp; Spring Integration có thể ghi cảnh báo tùy phiên bản. Với các sự kiện nghiệp vụ quan trọng, phải quy định rõ thông điệp bị loại đi đâu, có lưu để kiểm tra hay không, và có gửi phản hồi cho caller không.

### Splitter và Aggregator

Giả sử một lô gồm 100 dòng hàng:

~~~text
BatchReceived
     |
  Splitter
     |
Item-1 ... Item-100
     |
Validate / Enrich từng item
     |
 Aggregator
     |
BatchValidated
~~~

Splitter thường thêm các thông tin phục vụ tương quan/thứ tự khi sinh tập message. Aggregator cần xác định:

- **Correlation strategy:** message nào thuộc cùng một nhóm.
- **Release strategy:** khi nào nhóm đủ điều kiện phát kết quả.
- **Message store:** giữ trạng thái nhóm ở đâu; in-memory sẽ mất khi process chết.
- **Timeout và expiry:** làm gì khi một phần tử không bao giờ đến.
- **Duplicate/late messages:** tránh cộng hai lần hoặc tái mở nhóm không mong muốn.

Đặc biệt với xử lý theo cụm hoặc qua broker, không nên giả định mọi phần tử đến đủ, đúng thứ tự hoặc chỉ một lần. Cấu hình aggregator mặc định phải được đánh giá lại theo hợp đồng của luồng thực tế.

### Request-reply, one-way và publish-subscribe

| Kiểu luồng | Ví dụ | Kết quả mong đợi |
| --- | --- | --- |
| **Request-reply** | Tra cứu trạng thái tồn kho | Caller nhận một response hoặc timeout/lỗi |
| **One-way** | Tiếp nhận sự kiện đơn hàng | Caller biết thông điệp được nhận tới ranh giới nào |
| **Publish-subscribe** | Thông báo cập nhật catalog cho nhiều xử lý nội bộ | Mỗi subscriber được chuyển một bản; không mặc định có durable replay |

Khi cần reply, gateway có thể khai báo một phương thức trả kết quả:

~~~java
@MessagingGateway(defaultRequestChannel = "inventory.requests")
public interface InventoryQueryGateway {
    InventoryResult check(InventoryQuery query);
}
~~~

Phía cuối flow cần trả một `InventoryResult` để gateway chuyển phản hồi về caller; một service activator có return value hoặc một bước Transformer có thể thực hiện việc đó. Các ngưỡng `requestTimeout` và `replyTimeout` của gateway không đồng nghĩa timeout kết nối HTTP của một adapter downstream. Nếu flow trả kết quả muộn, cần thiết kế cách xử lý timeout/late reply theo hợp đồng.

## 6. Chọn MessageChannel: đồng bộ, executor và queue

Loại channel quyết định nhiều đặc tính runtime hơn tên gọi của flow.

| Channel | Mô hình thực thi | Ưu điểm | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| `DirectChannel` | Handler thường chạy trong thread gửi, point-to-point | Dễ theo vết; exception đồng bộ; có thể cùng transaction context | Handler chậm giữ thread của caller |
| `ExecutorChannel` | Chuyển việc cho `TaskExecutor` | Tách thời gian thực thi giữa sender/receiver | Ranh giới thread làm gián đoạn transaction context, có thể đổi thứ tự |
| `QueueChannel` | Lưu message trong queue; poller/consumer lấy sau | Buffer và điều tiết nhịp xử lý | Mặc định trong RAM, có nguy cơ mất message; phải giới hạn dung lượng |
| `PublishSubscribeChannel` | Đưa message tới nhiều subscriber | Phát tán sự kiện nội bộ | Không đồng nghĩa broker có lưu trữ/replay |
| `PriorityChannel` | Ưu tiên nhận theo comparator/priority | Phù hợp một số hàng đợi ưu tiên | Cần đánh giá starvation và độ bền |

Trong `DirectChannel`, nếu có nhiều subscriber trên cùng một channel dạng point-to-point, thông điệp thông thường được chuyển cho một consumer qua dispatcher, **không broadcast**. Muốn mọi consumer nhận cùng một event, chọn mô hình publish-subscribe phù hợp.

### Ví dụ một queue có giới hạn

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
public class QueueConfiguration {

    @Bean("orders.buffered")
    PollableChannel ordersBuffered() {
        return new QueueChannel(500);
    }
}
~~~

Consumer ở một component được Spring quản lý:

~~~java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class BufferedOrderConsumer {

    @ServiceActivator(
            inputChannel = "orders.buffered",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "20"))
    public void consume(NormalizedOrder order) {
        // Xử lý từ queue; cần thêm logic bảo đảm độ bền.
    }
}
~~~

Để nối luồng ở phần 4 sang queue, có thể thay bước xử lý cuối bằng `.channel("orders.buffered")` sau transformer, và sử dụng consumer ở trên. Khi đó gateway chỉ xác nhận đã chuyển đến queue trong RAM. **Không coi việc này là bảo đảm nhận thành công sau crash hoặc gửi được broker.**

Queue bị đầy có thể chặn sender hoặc làm thao tác send thất bại tùy timeout/chính sách, vì vậy phải theo dõi chiều dài queue, tốc độ tiêu thụ, saturation và giới hạn bộ nhớ. Nếu mất message khi restart là không chấp nhận được, chọn broker bền vững hoặc cấu hình `MessageStore` bền vững cho channel thích hợp (ví dụ dựa trên JDBC) và kiểm tra giao dịch liên quan.

Với poller, có thể khai báo cấu hình mặc định bằng nhóm thuộc tính `spring.integration.poller.*` của Boot; nhưng poller ghi trực tiếp trên endpoint sẽ có cấu hình riêng. Không hiểu nhầm một lần poll tương đương một message: `maxMessagesPerPoll` giới hạn số lần nhận trong mỗi chu kỳ.

## 7. Inbound/Outbound Channel Adapter và các giao thức

Spring Integration có adapter cho nhiều nguồn và đích. Cần phân biệt **inbound adapter**, **outbound adapter** và **outbound gateway**:

- **Inbound adapter:** lấy/nhận dữ liệu ngoài vào flow, ví dụ polling thư mục file hoặc đọc nguồn thông điệp.
- **Outbound adapter:** đưa thông điệp ra ngoài theo mô hình một chiều, ví dụ publish sự kiện.
- **Outbound gateway:** gọi hệ thống bên ngoài và chờ response, ví dụ HTTP request-reply.

| Giao thức/nguồn | Kịch bản minh họa | Chú ý hợp đồng |
| --- | --- | --- |
| HTTP | Gọi API định giá hoặc nhận webhook | Timeout, status code, authentication, schema |
| JDBC | Poll bản ghi công việc hoặc ghi kết quả | Transaction, lock/claim, phân trang |
| Kafka/AMQP/JMS | Tiếp nhận hoặc phát sự kiện | Consumer acknowledgement, offset, redelivery, dead-letter |
| File/SFTP | Nhận file theo lịch và tải kết quả đi | File đang ghi dở, rename, checksum, checkpoint |
| Mail/MQTT/TCP | Tích hợp hệ thống có giao thức riêng | Kết nối lại, session, message framing |

Ví dụ một endpoint JDBC polling đọc được 10 bản ghi chưa có nghĩa là chúng đã được đánh dấu “đã xử lý”. Cần quy định thời điểm claim/commit, số instance cùng đọc, điều kiện retry và lỗi giữa lúc đọc và lúc ghi. Tương tự, outbound HTTP thành công không khiến transaction DB tại chỗ và HTTP request tự trở thành một transaction ACID chung.

**Nguyên tắc adapter:** chuyển đổi và giao tiếp với hạ tầng; giữ quyết định nghiệp vụ, hợp đồng dữ liệu và chính sách retry ở lớp phù hợp để có thể kiểm thử mà không cần kết nối hệ thống thật.

## 8. Xử lý lỗi: đường đồng bộ và bất đồng bộ

Điểm khác biệt căn bản:

**Qua DirectChannel:** handler chạy đồng bộ nên lỗi thường truyền ngược về gateway/caller. Controller hoặc application service phải quyết định trả lỗi, rollback transaction local hay thực hiện retry.

**Qua ExecutorChannel hoặc poller:** caller có thể đã tiếp tục, lỗi xảy ra trong thread khác. Spring Integration có cơ chế tạo `ErrorMessage` (payload là `Throwable`) và gửi tới error channel phù hợp. Header `errorChannel` được xem xét trước; nếu không có, hạ tầng có thể dùng channel toàn cục `errorChannel` theo cơ chế error handler tương ứng.

~~~mermaid
flowchart TD
    A["Message từ source"] --> B{"Ranh giới thực thi"}
    B -->|"DirectChannel / cùng thread"| C["Handler ném exception"]
    C --> D["Caller / Gateway xử lý"]
    B -->|"Poller / Executor"| E["Handler ném exception"]
    E --> F["ErrorMessage"]
    F --> G["errorChannel"]
    G --> H["Alert / DLQ / recovery theo chính sách"]
~~~

Ví dụ đăng ký subscriber quan sát error channel:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationErrorObserver {

    @ServiceActivator(inputChannel = "errorChannel")
    public void record(ErrorMessage message) {
        Throwable cause = message.getPayload();
        // Ghi log đã che thông tin nhạy cảm, tăng metric và cảnh báo.
        // Việc phục hồi/retry cần được thiết kế ở nơi phù hợp.
    }
}
~~~

Đây là **mẫu quan sát lỗi**, không phải triển khai đầy đủ cơ chế dead-letter hoặc xử lý bù. Không kỳ vọng handler error channel ở trên sẽ bắt mọi exception chạy đồng bộ trong `DirectChannel`. Nếu code xử lý lỗi lại ném exception, còn phải xem hành vi phát tán và logging của chính đường lỗi.

Phân loại lỗi để quyết định xử lý:

| Nhóm lỗi | Ví dụ | Gợi ý |
| --- | --- | --- |
| Hợp đồng không hợp lệ | Thiếu orderId, sai schema, currency không hỗ trợ | Từ chối có lý do; lưu audit nếu cần |
| Lỗi tạm thời | Mất kết nối, broker không sẵn sàng, HTTP 503 | Retry có giới hạn + backoff/jitter, bảo vệ downstream |
| Lỗi quyền truy cập/cấu hình | Token sai, endpoint không được phép | Cảnh báo và sửa cấu hình; tránh retry liên tục |
| Lỗi nghiệp vụ vĩnh viễn | Đơn đã bị khóa, trạng thái chuyển không hợp lệ | Trả lỗi/đưa vào xử lý thủ công theo hợp đồng |
| Lỗi không xác định kết quả | Timeout sau khi gửi request ghi | Truy vấn trạng thái, sử dụng idempotency key trước khi gửi lại |

Một lỗi timeout **không chứng minh** downstream chưa áp dụng thao tác. Vì vậy retry một lần ghi phải được kết hợp với idempotency và cơ chế đối soát.

## 9. Giao dịch, xử lý trùng lặp và bảo đảm giao nhận

### 9.1. Ranh giới giao dịch

Khi toàn bộ flow chạy trên một `DirectChannel` cùng thread, transaction do caller thiết lập **có thể** bao phủ những thao tác database được thực hiện trong cùng context và cùng resource manager, với điều kiện phương thức chịu quản lý transaction phù hợp. Chuyển sang `ExecutorChannel` hoặc `QueueChannel` sẽ chuyển sang bối cảnh xử lý khác; không thể giả định transaction của thread gửi được mang qua.

Các kiểu bảo đảm cần nói rõ:

- **At-most-once:** có thể mất một thông điệp, không cố giao lại.
- **At-least-once:** có thể giao lại; consumer phải chịu được duplicate.
- **Exactly-once theo hiệu ứng nghiệp vụ:** cần thiết kế hợp đồng, state và ranh giới atomic phù hợp; không suy ra chỉ từ một annotation hay channel.

### 9.2. Idempotent Receiver

Ví dụ broker giao lại cùng một sự kiện có `eventId = evt-1001` sau khi consumer đã cập nhật DB nhưng chưa kịp acknowledge. Nếu xử lý lại toàn bộ, có thể tăng số lượng tồn kho/ghi thanh toán hai lần.

Spring Integration có `IdempotentReceiverInterceptor` hỗ trợ phát hiện message trùng dựa trên selector và metadata store, nhưng **chính ứng dụng** phải chọn khóa nhận diện ổn định và quy tắc xử lý. Với state chỉ giữ trong RAM, restart hoặc mở nhiều instance có thể làm mất khả năng phát hiện trùng. Khi dùng store tập trung, vẫn phải xem tính nguyên tử của thao tác kiểm tra/đánh dấu và side effect nghiệp vụ.

Một cách bảo vệ ở tầng database là **inbox table** có unique constraint trên eventId:

~~~java
// Mã minh họa ý tưởng; inboxRepository phải cung cấp
// thao tác INSERT ... ON CONFLICT/IGNORE tương đương, atomic.
// Cả hai thao tác DB cùng tham gia một transaction.
@Transactional
public void apply(NormalizedOrder event) {
    boolean firstTime =
            inboxRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return; // Event đã được áp dụng
    }

    orderRepository.applyBusinessChange(event);
}
~~~

Trong ví dụ này, `insertIfAbsent` phải dùng unique constraint thực tế và transaction nhất quán với `applyBusinessChange`. Nếu thao tác nghiệp vụ thất bại, transaction phải rollback cả dấu nhận sự kiện; nếu không, event sẽ bị đánh dấu “đã xong” dù thay đổi chưa xảy ra. Không thay thế unique constraint bằng một chuỗi `existsById()` rồi `save()` không nguyên tử khi có nhiều consumer đồng thời.

### 9.3. Outbox cho DB và broker

Khi cần “ghi đơn hàng rồi phát OrderCreated”, một transaction database local không đồng thời commit được broker một cách mặc định. Mẫu **Transactional Outbox** giải quyết bằng cách ghi thay đổi nghiệp vụ và bản ghi outbox **trong cùng một transaction DB**, rồi một publisher độc lập gửi outbox tới broker.

~~~mermaid
flowchart LR
    A["Order handler"] --> B["DB transaction"]
    B --> C["Order row"]
    B --> D["Outbox row"]
    D --> E["Publisher / CDC"]
    E --> F["Message broker"]
    F --> G["Consumer + inbox/idempotency"]
~~~

Publisher có thể gửi lặp lại khi crash đúng lúc broker đã nhận nhưng chưa đánh dấu outbox hoàn tất; consumer vẫn cần idempotency. Tương tự, quy tắc thay đổi trạng thái và đối soát phải được định nghĩa nếu hệ thống ngoài không hỗ trợ giao dịch chung.

## 10. Retry, backpressure và kiểm soát tải

Mẫu retry hợp lý cho tích hợp cần đủ bốn yếu tố: **phân loại lỗi**, **giới hạn số lần**, **khoảng chờ backoff/jitter**, và **đích xử lý khi hết lượt**.

Spring Integration có thể phối hợp với Spring Retry thông qua advice ở endpoint, hoặc sử dụng cơ chế retry của adapter/transport. Tránh thêm retry ở nhiều tầng mà không kiểm soát tổng số lần: nếu HTTP client retry 3 lần, handler retry 3 lần và broker cũng redeliver 3 lần, hệ thống có thể tạo rất nhiều lời gọi cho một sự kiện.

Các biện pháp chống quá tải:

1. **Bounded queue:** `QueueChannel` hoặc executor queue có dung lượng hữu hạn.
2. **Giới hạn concurrency:** số handler/consumer không vượt khả năng xử lý DB và downstream.
3. **Timeout:** riêng thời gian chờ gửi vào channel, chờ response và timeout tại transport.
4. **Rate limit/circuit breaker:** bảo vệ dịch vụ bên ngoài khi có lỗi lan rộng.
5. **Dead-letter/recovery:** message đã hết retry được giữ đủ thông tin để kiểm tra và gửi lại có kiểm soát.
6. **Giám sát backlog:** độ sâu queue, tuổi message cũ nhất, tốc độ vào/ra, số lần lỗi.

Không xem `ExecutorChannel` là “bất đồng bộ vô hạn”: thread pool hoặc queue có giới hạn sẽ dẫn đến backpressure, từ chối task hoặc chặn sender theo cấu hình executor. Không bật buffer không giới hạn để che một downstream liên tục quá tải.

## 11. Quản lý cấu hình và an toàn dữ liệu

Một flow cần cấu hình tách theo môi trường:

~~~yaml
# application.yml - ví dụ thuộc tính của ứng dụng
integrations:
  orders:
    destination: ${ORDER_DESTINATION:orders.received}
    max-attempts: 3
    enabled: true
~~~

Những khóa `integrations.orders.*` là **thuộc tính tự định nghĩa**, không phải thuộc tính Spring Integration tự hiểu. Chúng cần được bind bằng `@ConfigurationProperties` hoặc được tiêm theo cách khác vào adapter/cấu hình flow.

Không ghi credentials, API key, password hoặc token cố định vào source. Dùng secret manager/biến môi trường theo cơ chế đã chuẩn hóa. Với message có thông tin khách hàng hoặc tenant, cần kiểm tra:

- Không phát tán toàn bộ headers sang adapter ngoài khi không cần.
- Tenant identity phải xuất phát từ thông tin đã xác thực, không tin header HTTP bất kỳ.
- Schema và deserializer phải giới hạn kích thước, loại dữ liệu và phiên bản.
- Nội dung log, trace, metric và error message tránh mang token hoặc PII.
- Quản lý quyền truy cập broker topic, queue, database và endpoint quản trị.

Khi có nhiều adapter, tách **properties theo downstream** và kiểm tra cấu hình lúc khởi động (URL/topic bắt buộc, timeout dương, retry giới hạn). Không để tên kênh hoặc destination chính thức rải rác thành nhiều string khó kiểm soát.

## 12. Kiểm thử một flow theo hành vi

Cần kiểm thử từ hợp đồng đầu vào đến hiệu ứng đầu ra, không chỉ kiểm tra bean `IntegrationFlow` tồn tại.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Message hợp lệ | Gateway đi qua filter/transform và gọi đúng handler |
| Message bị từ chối | Bị ném lỗi hoặc chuyển discard channel đúng thiết kế |
| DTO/schema sai | Không phát hành side effect ngoài ý muốn |
| Trùng `eventId` | Business state chỉ thay đổi một lần theo hợp đồng |
| Downstream không sẵn sàng | Timeout/retry có giới hạn, lỗi cuối được ghi nhận |
| Queue đầy | Có backpressure hoặc timeout, không tăng RAM vô hạn |
| Crash/restart | Thông điệp đã hứa nhận được khôi phục theo bảo đảm thiết kế |
| Split/aggregate thiếu phần tử | Release/expiry xử lý nhóm tồn đọng |
| Giao dịch rollback | Không đánh dấu event đã xử lý khi business change chưa commit |
| Nhiều tenant | Không rò rỉ dữ liệu, header hoặc route giữa tenant |

Một ví dụ integration test cho đường đồng bộ:

~~~java
// Minh họa phần assertion trong @SpringBootTest;
// OrderHandler trong fixture được thay bằng fake/spy có lưu kết quả.
@Test
void acceptsAndNormalizesValidOrder() {
    gateway.submit(new OrderReceived(
            "evt-1",
            "  ORD-1  ",
            new BigDecimal("15.50")));

    assertEquals("ORD-1", fakeHandler.lastOrder().orderId());
}
~~~

Test này phải chạy với **Spring context có đăng ký gateway và flow**, đồng thời chuẩn bị fake handler trước khi gọi gateway; chỉ dùng `new OrderNormalizer()`/`new OrderHandler()` sẽ không xác minh integration wiring. Ngoài ra, cần test riêng thời điểm lỗi đi về gateway ở `DirectChannel` và đi vào error handling ở poller/executor.

Spring Integration có module test `spring-integration-test`, annotation `@SpringIntegrationTest` và hỗ trợ thay handler/source bằng thành phần giả trong một số ngữ cảnh. Nên dùng chúng khi cần cô lập I/O; với Kafka, Redis, JDBC hoặc HTTP thật, dùng broker/database/container hay stub phù hợp để kiểm tra hợp đồng giao nhận thay vì chỉ mock toàn bộ.

## 13. Quan sát và vận hành luồng tích hợp

Một flow chạy được trên máy cá nhân chưa đủ cho production. Cần có log, metric và trace với khả năng trả lời:

- Sự kiện đang ở bước nào; đã được xử lý hay đang chờ?
- Bước nào có latency cao, tỉ lệ lỗi tăng hoặc backlog?
- Số lần retry/duplicate là bao nhiêu; DLQ có tăng không?
- Message lỗi thuộc version schema nào; đã qua những endpoint nào?
- Có mất hoặc xử lý chậm dữ liệu sau khi rollout/restart không?

Spring Integration có cơ chế quản lý/quan sát endpoint, message history, metrics và khả năng tích hợp Micrometer/Actuator tùy dependency, version và cấu hình. Khi bật observation/message history, cân nhắc chi phí và cardinality; tránh đưa toàn bộ payload, orderId, eventId, tenantId vào tag của metric. Giữ `correlationId`/trace context qua ranh giới transport theo quy ước có kiểm soát.

Các số liệu thiết thực:

| Chỉ số | Phục vụ quyết định nào? |
| --- | --- |
| Message received/handled/failed | Có bước nào đang từ chối hoặc thất bại liên tục? |
| Endpoint processing duration p95/p99 | Bước nào làm tăng độ trễ cuối luồng? |
| Queue depth và oldest-message age | Consumer có theo kịp producer không? |
| Retry count, DLQ count | Có lỗi tạm thời hay lỗi hợp đồng kéo dài? |
| Duplicate rate theo event type | Redelivery nhiều hay upstream tạo sự kiện trùng? |
| Downstream error/timeout rate | Cần circuit breaker hoặc tăng capacity? |
| Outbox backlog và publish lag | DB→broker có đang chậm hoặc bị kẹt? |

Đảm bảo metric, alert và log khớp với **ranh giới đã nhận trách nhiệm xử lý**. Một HTTP gateway trả thành công sau khi ghi vào RAM queue không thể được đo như sự kiện đã lưu bền vững ở broker.

## 14. Khi nào nên dùng Spring Integration?

**Phù hợp** khi ứng dụng Spring cần kết nối nhiều transport, điều phối chuỗi chuyển đổi/định tuyến, polling nguồn dữ liệu, request-reply qua message, hoặc tách adapter khỏi logic nghiệp vụ với những EIP có sẵn.

**Không cần thiết** nếu một API chỉ có vài lời gọi trực tiếp và tích hợp đơn giản hơn bằng `RestClient`/`WebClient`, repository hoặc client broker là đủ. Spring Integration cũng không tự thay thế:

- **Broker:** dùng để giao nhận bền vững giữa các process, phân phối theo topic/queue hoặc replay theo khả năng của broker.
- **Spring Batch:** dùng cho job xử lý dữ liệu hữu hạn theo bước, checkpoint/restart và chunk processing.
- **Workflow/saga orchestration:** dùng cho quy trình dài hạn, nhiều bước có trạng thái, bù trừ và timeout nghiệp vụ.
- **Giao dịch và idempotency nghiệp vụ:** cần thiết kế lưu trữ, unique constraint, outbox/inbox và hợp đồng tác động bên ngoài.

Một ứng dụng thực tế có thể kết hợp Spring Integration với tất cả các thành phần đó. Điều quan trọng là mỗi công cụ giữ đúng trách nhiệm của mình.

## 15. Checklist thiết kế một integration flow

- [ ] Có sơ đồ source → channel → endpoint → sink, nêu rõ chỗ đồng bộ và bất đồng bộ.
- [ ] Có hợp đồng message gồm schema/version, khóa nghiệp vụ, correlation và quy định header.
- [ ] Đã chọn channel theo yêu cầu độ trễ, lưu bền, throughput và transaction.
- [ ] Filter/Router định nghĩa rõ đường đi cho message bị từ chối hoặc không có route.
- [ ] Adapter I/O có timeout, retry và fallback/đích lỗi phù hợp.
- [ ] Side effect được bảo vệ bằng idempotency key, giao dịch local, outbox/inbox khi cần.
- [ ] Queue/poller/executor có giới hạn tải và cơ chế quan sát backlog.
- [ ] Có kiểm thử thành công, dữ liệu sai, duplicate, timeout, crash/restart và ranh giới commit.
- [ ] Có metric, trace/log có kiểm soát dữ liệu nhạy cảm và quy trình replay lỗi.

**Ghi nhớ:** Spring Integration biến luồng tích hợp thành các thành phần có ranh giới rõ ràng: message diễn tả dữ liệu, channel diễn tả cách bàn giao, endpoint diễn tả thao tác, adapter giao tiếp với hệ thống khác. Độ tin cậy thực tế đến từ **hợp đồng dữ liệu, giao dịch, idempotency, retry, khả năng phục hồi và quan sát** được thiết kế xuyên suốt luồng.

## Tài liệu tham khảo

- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): starter, auto-configuration, scheduler và poller.
- [Spring Integration — Overview](https://docs.spring.io/spring-integration/reference/overview.html): messaging model, channel và endpoint.
- [Spring Integration — Java DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow` và các toán tử EIP.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway` và cách đăng ký proxy.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel` và cấu hình bền vững.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel` và lỗi bất đồng bộ.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): advice và metadata store phục vụ phát hiện trùng.
