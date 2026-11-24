# @ServiceActivator làm điểm kết thúc outbound

## 1. Bối cảnh và mục tiêu học tập

Trong Spring Integration, một **service activator** là endpoint nhận message từ một `MessageChannel` và gọi một phương thức hoặc một `MessageHandler` để thực hiện hành động. Khi đặt service activator ở **cuối integration flow**, nó thường thực hiện hành động gửi dữ liệu ra bên ngoài: gọi một service, ghi dữ liệu, phát message sang hệ thống khác hoặc bàn giao cho thành phần tích hợp chuyên dụng.

Annotation `@ServiceActivator` cho phép kết nối một phương thức Java với channel mà không cần tự viết vòng lặp đọc message. Đây là lựa chọn dễ hiểu khi logic kết thúc là một thao tác nghiệp vụ hoặc một lời gọi tới client do ứng dụng quản lý.

Bài học thuộc chương **Tạo integration flow** trong module **SPRING_INTEGRATION_ADAPTERS**. Module hướng tới việc kết nối hệ thống bên ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành với file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu, đồng thời quản lý hợp đồng message, lỗi và vòng đời kết nối.

Sau bài học, người học có thể:

- Giải thích vai trò của `@ServiceActivator`, `inputChannel` và `outputChannel`.
- Gắn một service activator vào cuối flow tạo bằng Java DSL.
- Thiết kế endpoint **one-way** không trả reply và phân biệt với endpoint **request–reply**.
- Xây dựng handler nhận `Message<T>` để dùng cả payload và headers.
- Lựa chọn giữa `@ServiceActivator` tự viết với outbound adapter/gateway tích hợp sẵn.
- Nhận diện lỗi, duplicate, retry, timeout, transaction và giới hạn của việc gửi ra ngoài.
- Viết kiểm thử cho tuyến `channel → flow → @ServiceActivator → client`.

**Phạm vi:** bài tập trung vào cách dùng `@ServiceActivator` làm điểm kết thúc outbound. Một lời gọi ra bên ngoài có thể dùng HTTP, JMS, AMQP, Kafka, SFTP hoặc database; thiết lập kết nối và semantics xác nhận sẽ phụ thuộc từng loại adapter và client.

## 2. Service activator nằm ở đâu trong luồng message?

Một flow đơn hướng thường gồm nguồn message, bước kiểm tra/chuyển đổi, channel đầu ra và endpoint phát sinh tác dụng phụ (*side effect*) tại đích.

~~~mermaid
flowchart LR
    A["Inbound adapter<br/>hoặc ứng dụng gửi"]
    B["orders.input<br/>MessageChannel"]
    C["Filter / Transform"]
    D["orders.outbound<br/>MessageChannel"]
    E["@ServiceActivator<br/>publish(Message<T>)"]
    F["Client bên ngoài"]
    G[("Hệ thống đích")]
    A --> B --> C --> D --> E --> F --> G
~~~

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Message<?>` | Mang payload và headers giữa các bước tích hợp. | `PartnerOrder`, header `correlationId`. |
| `MessageChannel` | Bàn giao message cho consumer; ảnh hưởng đồng bộ hoặc bất đồng bộ. | `DirectChannel`, `QueueChannel`. |
| `IntegrationFlow` | Khai báo tuyến transform/filter/route/channel bằng DSL. | `IntegrationFlow.from("orders.input")`. |
| `@ServiceActivator` | Đăng ký một method hoặc handler làm endpoint nhận message. | `@ServiceActivator(inputChannel = "orders.outbound")`. |
| Client / service | Thực thi hành động cuối hoặc gọi hệ thống ngoài. | HTTP client, `JmsTemplate`, JDBC repository. |
| Hệ thống đích | Nhận kết quả gửi ra ngoài và có quy tắc xác nhận riêng. | ERP, broker, file server, database. |

`@ServiceActivator` không chỉ dùng ở cuối flow: nếu phương thức trả giá trị, message có thể tiếp tục đi qua một channel khác hoặc được gửi về caller. Nó trở thành **điểm kết thúc outbound** khi được bố trí cuối tuyến và handler hoàn tất công việc mà không cần phát message tiếp.

Một endpoint ở cuối flow không đồng nghĩa hệ thống ngoài **đã xử lý thành công**. Có thể handler mới chỉ gửi vào hàng đợi cục bộ hoặc client đã gửi request nhưng chưa nhận xác nhận. Vì thế phải tách rõ ý nghĩa *đã gửi*, *đã nhận* và *đã hoàn thành nghiệp vụ*.

## 3. Cú pháp cơ bản của @ServiceActivator

### 3.1. Gắn annotation lên phương thức của Spring bean

~~~java
@Component
class AuditWriter {

    @ServiceActivator(inputChannel = "audit.outbound")
    public void writeAudit(Message<String> message) {
        String event = message.getPayload();
        System.out.println("Audit: " + event);
    }
}
~~~

Điểm cần nhớ:

- Class chứa method phải được Spring quản lý, ví dụ nhờ `@Component` và component scan.
- `inputChannel` chỉ rõ channel mà endpoint đăng ký nhận message.
- Parameter có thể là `Message<T>` để dùng cả payload và headers; với handler đơn giản có thể khai báo trực tiếp kiểu payload.
- Giá trị trả về `void` biểu thị endpoint không cung cấp reply. Handler có side effect nhưng không sinh message mới cho phần tiếp theo.
- Spring Integration đăng ký consumer/endpoint theo annotation trong application context. Code gửi message vào channel sẽ kích hoạt xử lý theo kiểu channel tương ứng.

Nếu class được tạo bằng `new AuditWriter()` nằm ngoài Spring context, annotation không tự biến method đó thành endpoint. Tương tự, đặt tên channel sai khiến luồng không đến được handler.

### 3.2. Khi method trả về một đối tượng

Một service activator cũng có thể biến message đầu vào thành reply:

~~~java
@ServiceActivator(inputChannel = "validation.requests")
public ValidationResult validate(OrderCommand command) {
    return new ValidationResult(command.id(), true);
}
~~~

Trong snippet này, `OrderCommand` và `ValidationResult` là hai kiểu dữ liệu do ứng dụng định nghĩa. Kết quả method sẽ được framework đóng gói thành message phản hồi và gửi theo cấu hình `outputChannel` hoặc `replyChannel` thích hợp.

Nếu caller dùng messaging gateway để gọi đồng bộ, phải đảm bảo flow phát reply mà gateway đang chờ. Nếu method `void` hoặc trả `null`, một gateway mong đợi response có thể phải đợi đến timeout. Vì vậy, **endpoint outbound one-way** và **endpoint request–reply** cần hợp đồng riêng.

### 3.3. Những thuộc tính annotation thường gặp

| Thuộc tính | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `inputChannel` | Tên channel nhận message. | `"orders.outbound"`. |
| `outputChannel` | Channel nhận kết quả khi method có reply. | Nối handler với chặng xử lý tiếp theo. |
| `requiresReply` | Yêu cầu handler tạo reply; hữu ích khi reply là bắt buộc. | Request–reply hoặc bước biến đổi phải có kết quả. |
| `poller` | Cấu hình consumer lấy message định kỳ từ `PollableChannel`. | `QueueChannel` đầu vào. |
| `autoStartup` | Cho biết endpoint có tự khởi động theo lifecycle không. | Cần kiểm soát thời điểm mở luồng gửi. |

Với `DirectChannel`, handler thường được kích hoạt ngay khi có message gửi tới channel và **không cần `poller`**. Với `QueueChannel`, phải có consumer polling phù hợp để lấy message từ queue.

## 4. Ví dụ hoàn chỉnh: kết thúc flow bằng @ServiceActivator

Giả sử một ứng dụng nhận đơn hàng nội bộ, kiểm tra số tiền, chuyển thành DTO đối tác, sau đó gửi đến một client đại diện cho hệ thống ERP. Để tập trung vào cách nối endpoint, client trong ví dụ chỉ lưu dữ liệu vào bộ nhớ. Có thể thay client này bằng kết nối HTTP, JMS hoặc một adapter thực tế khi triển khai.

Ví dụ sử dụng Java 17+, Spring Boot và Spring Integration.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

### 4.1. Code ứng dụng

Đặt toàn bộ đoạn dưới vào `OutboundFlowApplication.java` trong package `demo.outbound`. Chỉ có một class `public`; các record và component còn lại được khai báo package-private.

~~~java
package demo.outbound;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
public class OutboundFlowApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(OutboundFlowApplication.class, args);

        var input = context.getBean("orders.input", MessageChannel.class);
        input.send(MessageBuilder.withPayload(
                        new Order("ORD-1001", new BigDecimal("250000")))
                .setHeader("correlationId", "trace-ord-1001")
                .build());
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.outbound")
    MessageChannel ordersOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderToPartnerFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(Order.class,
                        order -> order.total() != null
                                && order.total().signum() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(Order.class,
                        order -> new PartnerOrder(
                                order.id(), order.total()))
                .channel("orders.outbound")
                .get();
    }
}

record Order(String id, BigDecimal total) {}

record PartnerOrder(String id, BigDecimal total) {}

@Component
class PartnerClient {

    private final List<PartnerOrder> received =
            new CopyOnWriteArrayList<>();

    public void send(PartnerOrder order, String correlationId) {
        // Demo: giả lập tác vụ gửi sang hệ thống ngoài.
        received.add(order);
        System.out.println("Sent " + order.id()
                + " with correlationId=" + correlationId);
    }

    public List<PartnerOrder> received() {
        return List.copyOf(received);
    }

    public void clear() {
        received.clear();
    }
}

@Component
class OutboundOrderPublisher {

    private final PartnerClient client;

    OutboundOrderPublisher(PartnerClient client) {
        this.client = client;
    }

    @ServiceActivator(inputChannel = "orders.outbound")
    public void publish(Message<PartnerOrder> message) {
        PartnerOrder order = message.getPayload();
        String correlationId =
                (String) message.getHeaders().get("correlationId");

        client.send(order, correlationId);
    }
}
~~~

Chạy Spring Boot application sẽ khởi tạo context, tạo hai channel, đăng ký `IntegrationFlow` và tạo endpoint từ `@ServiceActivator`. Method `main()` gửi một message có payload `Order` vào `orders.input`. Khi xử lý thành công, console dự kiến hiển thị thông tin `Sent ORD-1001...`.

Ví dụ này **không tạo request mạng và không xác nhận ERP đã nhận đơn hàng**. `PartnerClient` chỉ mô phỏng ranh giới outbound. Trong production, nó cần dùng client thực với cấu hình xác thực, timeout, retry, giám sát và hợp đồng response/ack của đích.

### 4.2. Đường đi của một message

~~~mermaid
sequenceDiagram
    participant A as Application
    participant I as orders.input
    participant F as IntegrationFlow
    participant O as orders.outbound
    participant S as OutboundOrderPublisher
    participant P as PartnerClient
    A->>I: Message<Order> + correlationId
    I->>F: filter(Order)
    F->>F: transform(Order -> PartnerOrder)
    F->>O: Message<PartnerOrder>
    O->>S: publish(message)
    S->>P: send(partnerOrder, correlationId)
    P-->>S: method returns
    S-->>A: no reply (one-way)
~~~

Với hai `DirectChannel` của ví dụ, phần xử lý chạy đồng bộ theo đường gửi message. `send(...)` trả về khi subscriber đã xử lý xong hoặc có exception được lan truyền; giá trị boolean của `MessageChannel.send(...)` không phải xác nhận nghiệp vụ từ hệ thống ngoài.

Các điểm quan trọng:

1. `orderToPartnerFlow()` không gọi thẳng `OutboundOrderPublisher`. Nó chuyển message qua `orders.outbound`.
2. `@ServiceActivator(inputChannel = "orders.outbound")` tạo consumer cho channel cuối cùng.
3. Method `publish(Message<PartnerOrder>)` nhận đúng kiểu payload mà transformer tạo ra, đồng thời đọc `correlationId` từ header.
4. `PartnerClient.send(...)` phát sinh hành động cuối. Vì `publish` trả `void` nên không có reply cho message.
5. `filter` phát exception khi số tiền không hợp lệ, thay vì im lặng loại message và khiến phía gửi không nhận được tín hiệu lỗi.

**Hợp đồng message:** đầu vào là `Order(id, total)`, yêu cầu `total > 0`; đầu ra tại channel `orders.outbound` là `Message<PartnerOrder>` và header `correlationId`. Đối với mã sản xuất, phải bổ sung validate `id`, kiểu dữ liệu, hạn mức tiền, thông tin hệ thống nguồn và ID dùng chống xử lý trùng.

## 5. Vì sao @ServiceActivator phù hợp làm outbound terminal?

Một integration flow có thể kết thúc bằng nhiều loại endpoint:

| Cách kết thúc | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- |
| `@ServiceActivator` trên service tùy chỉnh | Phải gọi logic riêng, client đã có hoặc quy trình nghiệp vụ đặc thù. | Tự chịu trách nhiệm mapping, lỗi, timeout và retry của lời gọi bên ngoài. |
| Java DSL `.handle(...)` | Muốn cấu hình handler ngay trong flow hoặc dùng bean service có sẵn. | Nên tách logic dài ra service riêng; hiểu kiểu reply. |
| Outbound adapter có sẵn | Giao thức được Spring Integration hỗ trợ và cần thao tác gửi một chiều. | Cấu hình kết nối, ack, retry, serializer theo protocol. |
| Outbound gateway có sẵn | Phải nhận phản hồi từ hệ thống ngoài và dùng response ở flow. | Timeout, mapping phản hồi và lỗi phía đích. |

Về cơ chế, một outbound adapter tích hợp sẵn cũng thường sử dụng loại **message-handling endpoint** để chuyển dữ liệu ra đích. Khác biệt nằm ở phạm vi chức năng: `@ServiceActivator` là cách **gắn phương thức hoặc handler bất kỳ vào luồng**, trong khi adapter/gateway chuyên dụng đã cung cấp bộ xử lý cho một giao thức.

Không nên tự viết lại toàn bộ logic SFTP, JMS, AMQP hoặc HTTP khi một adapter tương ứng đã đáp ứng yêu cầu. Tuy nhiên, service activator vẫn hữu ích cho nghiệp vụ cần phối hợp nhiều service hoặc các bước lưu dấu riêng.

### 5.1. So sánh với Java DSL .handle(...)

Dạng annotation của ví dụ:

~~~java
@ServiceActivator(inputChannel = "orders.outbound")
public void publish(Message<PartnerOrder> message) {
    client.send(message.getPayload(),
            (String) message.getHeaders().get("correlationId"));
}
~~~

Có thể thực hiện một endpoint tương tự trong Java DSL bằng handler:

~~~java
@Bean
IntegrationFlow partnerDeliveryFlow(PartnerClient client) {
    return IntegrationFlow.from("orders.outbound")
            .handle(PartnerOrder.class, (order, headers) -> {
                client.send(order, (String) headers.get("correlationId"));
                return null; // kết thúc một chiều
            })
            .get();
}
~~~

**Hai đoạn là hai cách cấu hình thay thế nhau.** Nếu khai báo đồng thời trên cùng `DirectChannel` với hai consumer độc lập, một message có thể đi đến một trong các subscriber theo cách channel phân phối, chứ không mặc nhiên phát cho cả hai. Muốn multicast tới nhiều nhánh, cần channel và thiết kế publish–subscribe phù hợp.

### 5.2. Gắn @ServiceActivator vào @Bean trả về MessageHandler

Khi cần quản lý handler như một bean độc lập, có thể dùng `@Bean` và `@ServiceActivator` trên method trả về `MessageHandler`:

~~~java
@Bean
@ServiceActivator(inputChannel = "orders.outbound")
MessageHandler outboundHandler(PartnerClient client) {
    return message -> {
        PartnerOrder order = (PartnerOrder) message.getPayload();
        String trace =
                (String) message.getHeaders().get("correlationId");
        client.send(order, trace);
    };
}
~~~

Snippet minh họa cấu hình **thay thế** cho `OutboundOrderPublisher` ở mục 4, không thêm song song vào ví dụ chạy được. Cả hai cách đều chỉ rõ input channel và handler mà Spring quản lý. Để giữ cách viết dễ kiểm thử và ít casting, annotation trên method có kiểu `Message<PartnerOrder>` thường dễ đọc hơn.

## 6. One-way và request–reply: chọn đúng hợp đồng

### 6.1. Endpoint một chiều

Trong một flow **one-way**, handler chủ yếu thực hiện side effect:

~~~java
@ServiceActivator(inputChannel = "notifications.outbound")
public void sendNotification(Notification notification) {
    notificationService.send(notification);
}
~~~

`Notification` và `notificationService` là các kiểu/dịch vụ ứng dụng cung cấp. Nếu không có reply, đừng thiết kế một messaging gateway đồng bộ bắt buộc trả về `NotificationResult` mà không có bước tạo kết quả.

**Lưu ý:** method không trả giá trị không có nghĩa tất cả xử lý đều bất đồng bộ. Ví dụ `DirectChannel` vẫn có thể gọi `notificationService.send(...)` ngay trên thread gửi message, đợi lời gọi kết thúc rồi mới trả quyền điều khiển.

### 6.2. Endpoint có phản hồi

Nếu phía gọi cần biết kết quả gửi hoặc muốn đi tiếp tới chặng xử lý khác, service activator có thể trả đối tượng:

~~~java
@ServiceActivator(inputChannel = "partner.requests")
public DeliveryResult deliver(PartnerOrder order) {
    return partnerDeliveryService.submit(order);
}
~~~

Lúc này phải bố trí reply channel hợp lệ hoặc dùng gateway request–reply. Có thể chỉ định `outputChannel` cho bước sau, hoặc để framework sử dụng `replyChannel` trong message khi thích hợp. Giá trị trả về có thể là payload cho một message mới. Đối với API HTTP có response, mô hình outbound gateway thường diễn đạt nhu cầu này rõ ràng hơn.

### 6.3. Gửi thành công đến đâu?

Có ba mức kết quả khác nhau:

1. **Đã gọi handler:** message đến `@ServiceActivator`.
2. **Đã bàn giao hoặc đã nhận ở protocol:** HTTP request có response, broker nhận bản tin, file được ghi hoặc thao tác database đã trả kết quả.
3. **Đã hoàn tất nghiệp vụ tại đích:** đối tác đã thực sự xử lý yêu cầu; có thể cần callback, ACK nghiệp vụ hoặc quy trình đối soát.

Không suy diễn mức 3 từ việc method `void` chạy xong, từ `send() == true` của `MessageChannel` hoặc từ một phản hồi nhận request ở tầng mạng. Hợp đồng tích hợp phải quy định rõ loại xác nhận nào đủ để đánh dấu hoàn tất.

## 7. Payload, header và ranh giới hệ thống

Handler outbound thường là điểm cuối cùng có thể bổ sung metadata trước khi dữ liệu rời ứng dụng. Một hợp đồng message điển hình:

~~~text
Message<PartnerOrder>
  payload:
    id: "ORD-1001"
    total: 250000
  headers:
    correlationId: "trace-ord-1001"
    sourceSystem: "order-service"
    idempotencyKey: "partner-a:ORD-1001"
~~~

| Trường | Tác dụng | Lưu ý |
| --- | --- | --- |
| `id` | Mã nghiệp vụ ở payload. | Đối tác có thể yêu cầu format và tính duy nhất khác hệ thống nội bộ. |
| `total` | Giá trị cần gửi. | Quy định đơn vị, currency, scale và rounding. |
| `correlationId` | Ghép log và luồng điều tra lỗi xuyên hệ thống. | Thường bảo toàn qua các bước transform/route. |
| `sourceSystem` | Chỉ ra hệ thống nguồn hoặc đối tác phát dữ liệu. | Hữu ích khi nhiều inbound adapter chung một flow. |
| `idempotencyKey` | Nhận diện thao tác logic đã xử lý để chống duplicate. | Đích phải biết và thực thi semantics tương ứng. |

Các header Spring Integration như `replyChannel` và `errorChannel` có thể là đối tượng channel nội bộ; **không tự động gửi toàn bộ chúng qua HTTP/JMS/Kafka**. Khi rời hệ thống, hãy dùng header mapper hoặc DTO rõ ràng. Đừng gửi thông tin nội bộ/nhạy cảm ra ngoài chỉ vì nó xuất hiện trong `MessageHeaders`.

Transformer thường bảo toàn các header cần thiết khi framework xây dựng message mới từ payload. Nếu tự tạo `Message<?>` mới, cần kiểm tra kỹ header correlation, tracing, error/reply, routing và các header dành riêng cho protocol. Khi một outbound handler chuyển đổi payload sang JSON hoặc format đối tác, mapping phải kiểm thử cả thiếu field, null, format thời gian, charset và dữ liệu vượt giới hạn.

## 8. Kết hợp service activator với inbound adapter, gateway và poller

Vì là consumer của một channel, `@ServiceActivator` không phụ thuộc message đến từ đâu:

~~~mermaid
flowchart TB
    FILE["File/SFTP inbound<br/>+ poller"]
    API["HTTP inbound gateway"]
    BROKER["JMS/AMQP/Kafka<br/>inbound listener"]
    DB["JDBC inbound<br/>+ poller"]
    FLOW["Validate / Transform / Route"]
    CH["outbound channel"]
    ACT["@ServiceActivator"]
    CLIENT["HTTP / JMS / Kafka / File<br/>hoặc database client"]
    FILE --> FLOW
    API --> FLOW
    BROKER --> FLOW
    DB --> FLOW
    FLOW --> CH --> ACT --> CLIENT
~~~

Nhiệm vụ ở hai đầu khác nhau:

- Inbound adapter nhận message từ file/SFTP, event broker hoặc DB và quyết định khi nào xác nhận đã đọc.
- `IntegrationFlow` chuẩn hóa payload và channel.
- Service activator gọi client/đích; phải quyết định khi nào coi outbound là thành công, lỗi nào retry và cách theo dõi tác động bên ngoài.

Khi thiết kế luồng nhận file rồi gửi HTTP, không nên đánh dấu file đã xử lý vĩnh viễn chỉ vì inbound adapter phát được `Message<File>`; nếu HTTP thất bại sau đó, cần cơ chế giữ lại/retry hoặc trạng thái xử lý để không bỏ mất record.

### 8.1. Khi input channel là QueueChannel

`DirectChannel` chuyển message ngay cho subscriber, còn `QueueChannel` giữ message để consumer lấy sau. Một service activator nhận từ queue cần poller phù hợp:

~~~java
@Bean(name = "outbound.queue")
QueueChannel outboundQueue() {
    return new QueueChannel(100);
}

@ServiceActivator(
        inputChannel = "outbound.queue",
        poller = @Poller(
                fixedDelay = "1000",
                maxMessagesPerPoll = "10"))
public void sendQueued(Message<PartnerOrder> message) {
    partnerClient.send(message.getPayload(),
            (String) message.getHeaders().get("correlationId"));
}
~~~

Snippet này giả định có import `QueueChannel`, `@Poller` và bean `partnerClient` trong class chứa method. Đây là ví dụ **cấu hình thay thế**, không được cắm đồng thời vào flow mẫu nếu chưa thay đổi thiết kế.

Queue có giới hạn dung lượng giúp tránh tăng bộ nhớ vô hạn, nhưng `QueueChannel` mặc định lưu message trong bộ nhớ và **không bảo đảm bền vững qua restart**. Nếu cần delivery chắc chắn, xem xét persistent message store, broker hoặc outbox cùng semantics xác nhận phù hợp.

## 9. Đường lỗi của outbound terminal

Thao tác outbound có thể lỗi ở nhiều giai đoạn:

~~~mermaid
flowchart TD
    M["Message đã vào @ServiceActivator"]
    V{"Dữ liệu hợp lệ?"}
    SEND["Client gửi tới đích"]
    R{"Đích xác nhận theo hợp đồng?"}
    OK["Ghi nhận thành công"]
    BAD["Business validation error"]
    RETRY["Chính sách lỗi, retry / DLQ / quarantine"]
    M --> V
    V -->|"Không"| BAD
    V -->|"Có"| SEND --> R
    R -->|"Có"| OK
    R -->|"Không / chưa rõ"| RETRY
    BAD --> RETRY
~~~

### 9.1. Lỗi đồng bộ

Với `DirectChannel`, exception trong method `@ServiceActivator` thông thường lan ngược qua lời gọi gửi message và có thể đến caller phía đầu vào. Ví dụ lỗi parse dữ liệu hoặc client ném exception trong cùng thread. Ứng dụng phải quyết định phía gửi sẽ thấy exception đó ra sao (HTTP status, trả lỗi gateway, log tại poller, v.v.).

### 9.2. Lỗi khi đổi thread

Nếu flow dùng `ExecutorChannel`, `QueueChannel`, broker hoặc task executor, handler có thể chạy ở thread khác. Khi đó, exception không nhất thiết quay lại caller gốc; xử lý lỗi có thể cần `errorChannel`, `ErrorMessage`, retry advice, dead-letter queue hoặc nơi lưu message thất bại.

Một poller lặp lại sau lỗi **không đồng nghĩa** message lỗi tự động được retry đúng cách. Điều này còn phụ thuộc trạng thái queue/source, transaction, acknowledgement và cách xử lý exception. Phải kiểm chứng bằng test với adapter cụ thể.

### 9.3. Trường hợp khó: side effect đã xảy ra nhưng mất response

Giả sử service activator gửi đơn qua HTTP. Đối tác đã tạo đơn nhưng kết nối ngắt trước khi ứng dụng nhận response. Nếu retry cùng request mà không có idempotency, đích có thể tạo hai đơn.

Biện pháp thường dùng:

- Sinh `idempotencyKey` ổn định theo **một thao tác nghiệp vụ**, truyền đến đích nếu được hỗ trợ.
- Ghi lại trạng thái yêu cầu/outbound ở kho bền vững và có cơ chế đối soát khi kết quả không rõ.
- Giới hạn retry, dùng backoff và xử lý khác nhau theo loại lỗi: input sai, timeout, rate limit, lỗi máy chủ.
- Đưa trường hợp không thể tự phục hồi vào dead-letter/quarantine với metadata đủ để kiểm tra và chạy lại có kiểm soát.

**Không có bảo đảm exactly-once chỉ nhờ `@ServiceActivator`.** Hành vi giao hàng phải xét đồng thời phía nguồn, channel, handler và hệ thống đích.

## 10. Ranh giới transaction và tài nguyên

Ví dụ một flow đồng bộ nhận đơn qua `DirectChannel` rồi gọi JDBC service trong cùng thread: transaction Spring có thể bao phủ các thao tác nội bộ nếu được cấu hình đúng. Nhưng **transaction trong một database không tự bao phủ lời gọi HTTP hoặc broker bên ngoài**.

Nếu lưu DB thành công rồi outbound thất bại, trạng thái hệ thống có thể không đồng nhất. Các giải pháp tùy bài toán gồm transactional outbox, trạng thái gửi riêng, retry có idempotency, saga hoặc compensating action.

Ở handler outbound, chú ý:

| Tình huống | Rủi ro | Quyết định thiết kế |
| --- | --- | --- |
| Client HTTP timeout | Thread bị chiếm, kết quả ngoài hệ thống không rõ. | Timeout, connection pool, idempotency và đối soát. |
| Publish Kafka/JMS | Publish có thể async hoặc broker ack theo cấu hình. | Chọn mức delivery/ack, serializer, error callback và DLQ. |
| Ghi SFTP/file | File đích có thể bị đọc khi đang ghi. | Ghi tạm rồi rename, kiểm soát permission và cleanup. |
| Ghi DB | Duplicate, transaction rollback hoặc lock contention. | Unique constraint, transaction và retry theo mã lỗi. |
| Ứng dụng dừng | Message in-flight chưa xong; queue mất dữ liệu. | Graceful shutdown, drain queue và persistent state. |

Không dùng method outbound chạy blocking trên scheduler hoặc thread nhận sự kiện khi độ trễ của đích không có giới hạn. Nếu tách thread, cần giới hạn queue/concurrency, kiểm soát lifecycle và thiết kế lại đường lỗi tương ứng.

## 11. Kiểm thử điểm kết thúc outbound

Kiểm thử tốt cần xác nhận ba điều: dữ liệu được biến đổi chính xác, method `@ServiceActivator` được gọi qua channel thực, và client nhận đúng dữ liệu/metadata.

Với `PartnerClient` mô phỏng lưu bộ nhớ ở mục 4, có thể tạo test dùng Spring context. Đặt vào `OutboundFlowApplicationTest.java` trong package `demo.outbound`:

~~~java
package demo.outbound;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class OutboundFlowApplicationTest {

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    PartnerClient client;

    @BeforeEach
    void resetClient() {
        client.clear();
    }

    @Test
    void validOrderReachesOutboundServiceActivator() {
        var message = MessageBuilder.withPayload(
                        new Order("ORD-2001", new BigDecimal("999.00")))
                .setHeader("correlationId", "test-2001")
                .build();

        assertTrue(input.send(message));

        assertEquals(
                new PartnerOrder("ORD-2001", new BigDecimal("999.00")),
                client.received().get(0));
        assertEquals(1, client.received().size());
    }

    @Test
    void invalidOrderDoesNotReachPartnerClient() {
        var invalid = MessageBuilder.withPayload(
                new Order("ORD-2002", BigDecimal.ZERO)).build();

        assertThrows(MessageRejectedException.class,
                () -> input.send(invalid));

        assertTrue(client.received().isEmpty());
    }
}
~~~

Dự án cần `spring-boot-starter-test` ở scope `test`. Mẫu kiểm thử dùng hai `DirectChannel` nên thao tác gửi message hoàn tất đồng bộ trước khi assert. Nếu thay `orders.outbound` bằng queue hoặc executor, test phải đợi kết quả theo một điều kiện có giới hạn thời gian (ví dụ latch hoặc công cụ await), không nên assert tức thì.

Với outbound thực tế, mở rộng kiểm thử thêm các trường hợp: timeout, HTTP 429/5xx, broker mất kết nối, lỗi serializer, duplicate và khởi động lại ứng dụng. Dùng mock server, test broker hoặc database test tương ứng; đo side effect ở đích, không chỉ kiểm tra handler đã được gọi.

### 11.1. Kiểm tra lỗi do handler ném ra

Thêm một test thay `PartnerClient` bằng fake ném exception theo điều kiện. Kỳ vọng của bài kiểm thử phải trả lời:

1. Caller của `MessageChannel.send(...)` có nhận exception không?
2. Message đã bị loại khỏi nguồn/queue chưa?
3. Có thể xử lý lại cùng một request theo cách không tạo side effect trùng không?
4. Khi handler đã chạy một phần, trạng thái nào cho phép đối soát?

Các câu trả lời phụ thuộc loại channel và nguồn; không nên kết luận toàn flow tin cậy chỉ dựa vào một unit test gọi trực tiếp method `publish()`.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Handler `@ServiceActivator` không được gọi. | Class chưa là Spring bean, sai `inputChannel`, endpoint chưa start hoặc không có message. | Kiểm tra component scan, tên channel và endpoint lifecycle. |
| Gửi vào `DirectChannel` báo không có subscriber. | Chưa đăng ký consumer cho channel hoặc endpoint đang dừng. | Tạo đúng service activator/flow consumer và kiểm tra tên bean. |
| Hai handler cùng đăng ký nhận nhưng chỉ một handler chạy. | `DirectChannel` phân phát cho subscriber, không multicast. | Dùng `PublishSubscribeChannel` nếu cần fan-out và quyết định xử lý lỗi từng nhánh. |
| Gateway timeout dù outbound đã hoàn thành. | Handler `void` không tạo reply, nhưng gateway chờ kết quả. | Phân biệt one-way với request–reply; thiết kế đường reply có chủ đích. |
| Thông tin correlation mất sau transform. | Tự tạo message mới nhưng không giữ header cần thiết. | Chỉ rõ hợp đồng headers, bổ sung kiểm thử message end-to-end. |
| Đích nhận lặp cùng yêu cầu. | Retry hoặc redelivery sau lỗi không rõ kết quả. | Idempotency key, checkpoint, outbox hoặc đối soát. |
| Hệ thống chậm khi API đối tác chậm. | Handler đồng bộ giữ thread của poller hoặc listener. | Timeout, giới hạn tải và cân nhắc tách luồng có kiểm soát. |
| Unit test pass nhưng production mất dữ liệu. | Test chỉ gọi method, chưa kiểm tra source/ack/queue/restart. | Integration test qua channel và nguồn thật/mô phỏng sát hành vi. |
| Retry làm side effect lặp. | Không phân biệt lỗi trước và sau khi gửi thành công. | Thiết kế state machine gửi và retry có idempotency. |

## 13. Bài thực hành mở rộng

**Bài toán:** ứng dụng nhận message đơn hàng từ nguồn file CSV hoặc Kafka, chuyển đổi sang `PartnerOrder` rồi gửi outbound tới một ERP thông qua client. Thiết kế luồng với yêu cầu:

1. Inbound chuẩn hóa thành `Order(id, total, currency)`; record thiếu ID hoặc số tiền không dương đi vào luồng lỗi.
2. `IntegrationFlow` chuyển message hợp lệ thành DTO phù hợp ERP, giữ header `correlationId`.
3. `@ServiceActivator(inputChannel = "erp.outbound")` gọi client ERP, không tạo reply cho nguồn one-way.
4. Client giả lập thành công cho một số đơn, timeout cho một số đơn và trả lỗi dữ liệu cho số còn lại.
5. Thiết kế mã idempotency để timeout/retry không gây duplicate.
6. Ghi nhận message lỗi vào kho có thể điều tra; phân biệt lỗi cần sửa dữ liệu với lỗi có thể retry.
7. Khi thay `DirectChannel` bằng `QueueChannel`, bổ sung poller và giải thích thay đổi về thread, timing, error propagation và độ bền queue.

**Tiêu chí hoàn thành:** viết test cho đường thành công, lỗi validation, lỗi client và retry sau timeout; chứng minh message đưa vào đúng `erp.outbound` và mô tả điểm nào được tính là đã xử lý nghiệp vụ. Giải thích vì sao method `void` không đủ để chứng minh ERP đã hoàn tất đơn.

## 14. Câu hỏi tự kiểm tra

1. `@ServiceActivator` được dùng để định nghĩa loại endpoint nào? Nó có bắt buộc là outbound adapter không?
2. Vì sao annotation chỉ có tác dụng khi method thuộc một Spring bean?
3. `inputChannel` được nối với `IntegrationFlow.channel(...)` như thế nào?
4. Method `void` làm endpoint cuối có nghĩa tất cả bước trước đó chạy bất đồng bộ không?
5. Trong một flow có `DirectChannel`, exception từ client outbound có thể xuất hiện ở đâu?
6. Nếu method trả `PartnerResult`, Spring Integration sẽ gửi reply theo cơ chế nào?
7. Vì sao hai subscriber trên cùng `DirectChannel` không phải cơ chế broadcast?
8. Một request đã được đối tác xử lý nhưng client timeout: xử lý retry sao cho không ghi lặp?
9. Khi dùng `QueueChannel`, điều gì xảy ra nếu không có poller/consumer?
10. Đâu là ranh giới đảm bảo dữ liệu khi chuyển từ database nội bộ sang HTTP/SFTP/JMS?

**Gợi ý:** service activator gắn method/handler vào message channel; endpoint có thể nằm giữa flow hoặc cuối flow; muốn reply thì phải khai báo đường reply phù hợp; kết quả của side effect không suy ra từ message delivery nội bộ. Tính đúng đắn khi outbound phụ thuộc xác nhận của giao thức, trạng thái bền vững và quy tắc chống xử lý trùng.

## 15. Kết luận

`@ServiceActivator` là công cụ gọn để biến một phương thức Java thành **consumer của MessageChannel**. Ở cuối integration flow, nó có thể làm điểm kết thúc outbound bằng cách gọi service hoặc client gửi dữ liệu tới hệ thống khác. Sử dụng `void` cho thao tác một chiều, hoặc trả kết quả khi kiến trúc thực sự có đường reply.

Khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, hãy giữ hợp đồng payload/headers rõ ràng, chọn channel và thread phù hợp, quản lý timeout/retry, phân biệt trạng thái gửi với trạng thái xử lý nghiệp vụ và kiểm thử lỗi/duplicate. Đó là điều kiện để endpoint đơn giản trên giấy hoạt động tin cậy khi kết nối nhiều hệ thống.

