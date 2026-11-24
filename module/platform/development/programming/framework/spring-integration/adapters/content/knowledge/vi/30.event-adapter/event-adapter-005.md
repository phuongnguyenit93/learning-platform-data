# Event type và payload mapping trong Spring Integration Event Adapter

## Mục tiêu bài học

Trong chương **Adapter sự kiện** của module **SPRING_INTEGRATION_ADAPTERS**, ta kết nối cơ chế Spring `ApplicationEvent` với `MessageChannel`. Bài này giải quyết hai câu hỏi dễ nhầm khi thiết kế hợp đồng message:

1. **Event type:** adapter nhận/phát loại sự kiện nào, và type đó được xác định tại ranh giới Spring hay trong Spring Integration?
2. **Payload mapping:** dữ liệu nào trở thành `Message.getPayload()`, khi nào cần chuyển đổi thành đối tượng nghiệp vụ và headers được giữ như thế nào?

Sau bài học, bạn có thể cấu hình `eventTypes` cho inbound event adapter, nắm thứ tự ưu tiên khi ánh xạ nguồn sự kiện sang message, sử dụng `publishPayload` ở outbound adapter, viết transformer chuẩn hóa payload và kiểm tra được các trường hợp đặc biệt như `MessagingEvent` và `PayloadApplicationEvent`.

Phạm vi ở đây là trao đổi sự kiện **trong Spring ApplicationContext**. Spring Integration còn có các adapter cho file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; cơ chế event adapter giúp nối các thành phần nội bộ trước hoặc sau những kết nối ấy, nhưng không tự cung cấp hàng đợi bền vững hay giao tiếp xuyên tiến trình.

## 1. Ba lớp kiểu dữ liệu không nên đánh đồng

~~~mermaid
flowchart LR
    A["Spring ApplicationEventPublisher"] -->|"ApplicationEvent hoặc POJO"| B["Inbound event adapter"]
    B -->|"Message&lt;T&gt;"| C["MessageChannel"]
    C --> D["Transformer / Filter / Router"]
    D -->|"Message&lt;DomainEvent&gt;"| E["Outbound event adapter"]
    E -->|"Spring event"| F["@EventListener / ApplicationListener"]
~~~

Trong sơ đồ có ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Spring event type** | Kiểu mà `ApplicationEventPublisher` công bố và Spring listener phân loại | `OrderApprovedApplicationEvent`, `PayloadApplicationEvent<OrderApproved>`, `MessagingEvent` |
| **Spring Integration message type** | Vỏ `Message<?>` chứa payload cùng headers để truyền qua `MessageChannel` | `Message<OrderApprovedApplicationEvent>`, `Message<OrderApproved>` |
| **Domain payload type** | Hợp đồng nghiệp vụ mà các thành phần trong flow cần sử dụng | `OrderApproved(String orderId, BigDecimal total, Instant approvedAt)` |

Ví dụ: `OrderApprovedApplicationEvent` là một loại Spring event, nhưng sau khi đi qua transformer, payload của message có thể trở thành `OrderApproved`. Filter theo event type được thực hiện ở **đầu vào**; filter theo `orderId` hoặc `total` thuộc logic nghiệp vụ **trong flow**. Hai thao tác này giải quyết hai tầng khác nhau.

## 2. Inbound adapter: event type quyết định sự kiện nào được nhận

`ApplicationEventListeningMessageProducer` (package `org.springframework.integration.event.inbound`) là inbound channel adapter, đồng thời đóng vai trò Spring application listener. Adapter nhận sự kiện do `ApplicationEventPublisher` phát và gửi message vào output channel.

Theo mặc định, nó có thể nhận tất cả application events phù hợp trong context. Bạn có thể giới hạn bằng `setEventTypes(Class<?>... eventTypes)`, tương ứng thuộc tính `event-types` trong XML.

~~~java
@Bean
public ApplicationEventListeningMessageProducer approvedEventInbound(
        @Qualifier("rawOrderEvents") MessageChannel outputChannel) {

    var adapter = new ApplicationEventListeningMessageProducer();
    adapter.setEventTypes(OrderApprovedApplicationEvent.class);
    adapter.setOutputChannel(outputChannel);
    return adapter;
}
~~~

Cấu hình trên chỉ đưa những event khớp `OrderApprovedApplicationEvent` vào channel `rawOrderEvents`. Các sự kiện vòng đời Spring như `ContextRefreshedEvent` sẽ không tự đi vào channel này.

**Một điểm dễ bỏ sót:** từ Spring Framework 4.2, Spring cho phép `publishEvent(Object)` với POJO thông thường. Spring dùng `PayloadApplicationEvent` để mang POJO, còn Spring Integration inbound adapter có hỗ trợ lọc trực tiếp theo **kiểu payload POJO**. Vì thế có thể viết:

~~~java
adapter.setEventTypes(OrderApproved.class);
~~~

khi phía phát gọi `publisher.publishEvent(new OrderApproved(...))`. Inbound adapter sẽ gửi message mang payload `OrderApproved`. Trong trường hợp này, không nhất thiết phải tự viết `ApplicationListener<PayloadApplicationEvent<OrderApproved>>`.

`setEventTypes(...)` là **lọc theo kiểu**, không phải lọc theo giá trị thuộc tính. Muốn nhận chỉ những đơn hàng có tổng tiền dương hoặc trạng thái cụ thể, hãy dùng `Filter`, `Router` hoặc logic xác thực sau khi event được nhận.

## 3. Inbound payload mapping: thứ tự ưu tiên

Inbound event adapter có ba cách quyết định payload hoặc message đầu ra. Thứ tự xử lý là một phần quan trọng của hợp đồng tích hợp.

| Dữ liệu Spring nhận | Cách inbound adapter tạo message | Điều cần nhớ |
| --- | --- | --- |
| `ApplicationEvent` có `getSource()` là một `Message<?>` | Chuyển **chính message gốc** vào output channel | Headers và payload của message gốc được giữ; không áp dụng nhánh trích payload thông thường |
| `PayloadApplicationEvent<T>` cho POJO | Trích `event.getPayload()` làm message payload | Listener có thể lọc theo `T.class`; headers message gốc không tự xuất hiện |
| `ApplicationEvent` thông thường, source không phải `Message<?>`, có `payloadExpression` | Đánh giá SpEL trên đối tượng event để lấy payload | Dùng khi chỉ cần một phần nội dung event |
| `ApplicationEvent` thông thường, source không phải `Message<?>`, không có `payloadExpression` | Đưa **bản thân event** làm payload | Transformer phía sau nhận đối tượng sự kiện, không phải `event.getSource()` |

Đặc biệt, **không mặc định cho rằng payload bằng `event.getSource()`**. Với event thông thường, không cấu hình biểu thức thì payload là **event**. Với event phát từ `Message<?>`, toàn bộ message có thể được giữ nguyên. Với POJO payload event, Spring Integration trích đối tượng POJO. Ba đường đi này khác nhau.

Ví dụ event tự định nghĩa:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class OrderApprovedApplicationEvent extends ApplicationEvent {

    private final String orderId;
    private final BigDecimal total;
    private final Instant approvedAt;

    public OrderApprovedApplicationEvent(
            Object source, String orderId, BigDecimal total, Instant approvedAt) {
        super(source);
        this.orderId = Objects.requireNonNull(orderId);
        this.total = Objects.requireNonNull(total);
        this.approvedAt = Objects.requireNonNull(approvedAt);
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }
}
~~~

Với event này và `eventTypes(OrderApprovedApplicationEvent.class)`, nếu không đặt `payloadExpression`, payload của message sau inbound adapter là `OrderApprovedApplicationEvent`.

Nếu chỉ cần mã đơn hàng, có thể cấu hình một **phương án thay thế**:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

// Thực hiện trên adapter trước khi đưa vào Spring context:
adapter.setPayloadExpression(
        new SpelExpressionParser().parseExpression("orderId"));
~~~

Biểu thức `orderId` đọc thuộc tính từ `OrderApprovedApplicationEvent`, tương ứng getter `getOrderId()`. Khi đó payload đầu ra là `String`; transformer hoặc service activator phía sau cũng phải khai báo kiểu tương ứng. Không thêm cấu hình này vào ví dụ chuẩn hóa toàn bộ event ở mục tiếp theo vì sẽ làm thay đổi contract của flow.

## 4. Ví dụ hoàn chỉnh: filter theo event type rồi chuẩn hóa payload

Bài toán: khi hệ thống xử lý đơn hàng phát `OrderApprovedApplicationEvent`, ta chỉ tiếp nhận loại event này, chuyển thành hợp đồng nghiệp vụ `OrderApproved` và giao cho một consumer trong Spring Integration.

**Bước 1 — Định nghĩa payload đích.**

`OrderApproved.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderApproved(
        String orderId,
        BigDecimal total,
        Instant approvedAt) {
}
~~~

Trong cùng package có `OrderApprovedApplicationEvent` từ mục 3.

**Bước 2 — Khai báo inbound adapter và hai channel.**

`OrderEventAdapterConfig.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderEventAdapterConfig {

    @Bean
    public MessageChannel rawOrderEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel normalizedOrderEvents() {
        return new DirectChannel();
    }

    @Bean
    public ApplicationEventListeningMessageProducer approvedEventInbound(
            @Qualifier("rawOrderEvents") MessageChannel channel) {

        var adapter = new ApplicationEventListeningMessageProducer();
        adapter.setEventTypes(OrderApprovedApplicationEvent.class);
        adapter.setOutputChannel(channel);
        return adapter;
    }
}
~~~

**Bước 3 — Chuyển event thành domain payload và tiêu thụ.**

`OrderEventEndpoints.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class OrderEventEndpoints {

    @Transformer(
            inputChannel = "rawOrderEvents",
            outputChannel = "normalizedOrderEvents")
    public OrderApproved toDomainPayload(OrderApprovedApplicationEvent event) {
        return new OrderApproved(
                event.getOrderId(),
                event.getTotal(),
                event.getApprovedAt());
    }

    @ServiceActivator(inputChannel = "normalizedOrderEvents")
    public void consume(OrderApproved event) {
        System.out.println("Approved order: " + event.orderId());
        // Ví dụ: chuyển tiếp tới một adapter HTTP, JMS hoặc Kafka thích hợp.
    }
}
~~~

`@Transformer` nhận payload `OrderApprovedApplicationEvent` và trả về payload `OrderApproved`. Spring Integration tiếp tục truyền dữ liệu đó trong một message qua `normalizedOrderEvents`. Việc chuẩn hóa này cho phép các bước downstream phụ thuộc vào hợp đồng nghiệp vụ thay vì phụ thuộc trực tiếp vào API Spring `ApplicationEvent`.

**Bước 4 — Phát sự kiện từ service Spring.**

`OrderApprovalService.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderApprovalService {

    private final ApplicationEventPublisher publisher;

    public OrderApprovalService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void approve(String orderId, BigDecimal total) {
        publisher.publishEvent(new OrderApprovedApplicationEvent(
                this, orderId, total, Instant.now()));
    }
}
~~~

Khi gọi `approve("ORD-2048", new BigDecimal("120.50"))`, trình tự là:

~~~mermaid
sequenceDiagram
    participant S as OrderApprovalService
    participant P as ApplicationEventPublisher
    participant I as Event inbound adapter
    participant C as rawOrderEvents
    participant T as Transformer
    participant O as normalizedOrderEvents
    participant H as Consumer

    S->>P: OrderApprovedApplicationEvent
    P->>I: event type khớp
    I->>C: Message<OrderApprovedApplicationEvent>
    C->>T: event làm payload
    T->>O: Message<OrderApproved>
    O->>H: OrderApproved
~~~

Mặc định, `DirectChannel` và Spring event multicaster thông thường hoạt động đồng bộ. Khi kết hợp cơ chế `@Async`, executor channel hoặc custom multicaster, thời điểm gọi consumer và cách báo lỗi có thể thay đổi.

## 5. Trường hợp phát POJO: giảm số lớp wrapper

Nếu chỉ cần truyền sự kiện nghiệp vụ thuần, Spring cho phép phát POJO trực tiếp:

~~~java
publisher.publishEvent(new OrderApproved(
        "ORD-2049",
        new BigDecimal("75.00"),
        Instant.now()));
~~~

Để nhận trực tiếp loại payload này, thay cấu hình inbound tương ứng:

~~~java
adapter.setEventTypes(OrderApproved.class);
~~~

Tại ranh giới Spring, sự kiện POJO được biểu diễn qua `PayloadApplicationEvent<OrderApproved>`. Inbound adapter nhận biết sự kiện kiểu payload và tạo message với payload `OrderApproved`. Do payload đã là dạng chuẩn hóa, có thể gắn consumer thẳng vào output channel mà không cần biến đổi `OrderApprovedApplicationEvent → OrderApproved`.

Đây là **một thiết kế thay thế** cho ví dụ mục 4. Nếu đã đổi `eventTypes` sang `OrderApproved.class` thì `@Transformer` cũ, vốn nhận `OrderApprovedApplicationEvent`, không còn phù hợp. Hãy sửa hoặc bỏ transformer để kiểu đầu ra và đầu vào khớp nhau.

| Khi dùng | Nên chọn |
| --- | --- |
| Spring event có thêm thông tin nguồn, thời điểm, ngữ cảnh và API riêng | Event class kế thừa `ApplicationEvent` |
| Sự kiện nghiệp vụ là hợp đồng độc lập, các bên đều biết kiểu POJO | Phát và nhận POJO qua `publishEvent(Object)` |
| Cần giữ `Message<?>` và headers như `correlationId`, `traceId` | Bọc message bằng `MessagingEvent` hoặc thiết kế một event contract có metadata rõ ràng |

Không có lựa chọn duy nhất cho mọi hệ thống; contract phải phù hợp nhu cầu downstream.

## 6. Outbound mapping: từ message trở lại Spring event

`ApplicationEventPublishingMessageHandler` là outbound adapter cùng module `spring-integration-event`. Nó chuyển message trong Spring Integration thành event cho `ApplicationEventPublisher`.

Quy tắc phát event là:

| Payload trong message đầu vào | `publishPayload` | Event Spring nhận |
| --- | --- | --- |
| `OrderApprovedApplicationEvent` (đã kế thừa `ApplicationEvent`) | `false` hoặc `true` | Chính `OrderApprovedApplicationEvent` |
| `OrderApproved` (POJO) | `false` (mặc định) | `MessagingEvent` chứa toàn bộ `Message<OrderApproved>` |
| `OrderApproved` (POJO) | `true` | `OrderApproved` được phát trực tiếp; Spring có thể biểu diễn dưới dạng `PayloadApplicationEvent<OrderApproved>` |

Ví dụ outbound endpoint phát POJO:

~~~java
@Bean
@ServiceActivator(inputChannel = "outboundOrderEvents")
public ApplicationEventPublishingMessageHandler outboundOrderEventPublisher() {
    var handler = new ApplicationEventPublishingMessageHandler();
    handler.setPublishPayload(true);
    return handler;
}
~~~

Ví dụ giả định đã có bean `MessageChannel` tên `outboundOrderEvents` và một producer gửi `Message<OrderApproved>` vào channel đó. Một listener có thể xử lý:

~~~java
@EventListener
public void onApproved(OrderApproved event) {
    System.out.println("Observed: " + event.orderId());
}
~~~

Nếu không gọi `setPublishPayload(true)`, listener trên sẽ không nhận trực tiếp một `OrderApproved` từ message có payload POJO; khi ấy hãy lắng nghe `MessagingEvent`, ví dụ:

~~~java
@EventListener
public void onMessagingEvent(MessagingEvent event) {
    var message = event.getMessage();
    Object correlationId = message.getHeaders().get("correlationId");

    if (message.getPayload() instanceof OrderApproved approved) {
        System.out.println(approved.orderId() + ", corr=" + correlationId);
    }
}
~~~

Đoạn listener thứ hai cần import `org.springframework.integration.event.core.MessagingEvent`. Hai phương án tùy thuộc lựa chọn `publishPayload`; đừng áp dụng cả hai rồi suy ra một event tự động được nhân đôi.

## 7. Header mapping và metadata

**Payload mapping không đồng nghĩa header mapping.** `Message<?>` và `ApplicationEvent` có hai mô hình metadata khác nhau.

- Khi inbound adapter nhận event có `getSource()` là `Message<?>`, nó chuyển message gốc, nên những header như `correlationId`, `traceId` có thể giữ nguyên qua ranh giới này.
- Khi nhận Spring event thông thường hoặc POJO, inbound adapter tạo message mới. Nó không thể tự tạo lại headers của một message vốn không tồn tại tại nguồn; đưa dữ liệu quan trọng vào cấu trúc event hoặc thêm header sau khi nhận.
- Khi outbound handler phát `MessagingEvent`, Spring listener lấy được message gốc bằng `getMessage()`. Khi phát trực tiếp POJO, message headers không tự trở thành fields của POJO.

Ví dụ cố ý giữ header bằng `MessagingEvent`:

~~~java
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderApproved> original = MessageBuilder
        .withPayload(new OrderApproved(
                "ORD-2050", new BigDecimal("88.00"), Instant.now()))
        .setHeader("correlationId", "trace-2050")
        .build();

publisher.publishEvent(new MessagingEvent(original));
~~~

Một inbound adapter lọc `MessagingEvent.class` có thể chuyển chính `original` vào output channel; phần downstream vẫn đọc được `correlationId`. Điều này khác với cách phát POJO trực tiếp. Cũng cần phân biệt header nghiệp vụ cần được bảo tồn với header nội bộ của Spring Integration (ví dụ `id` hoặc `timestamp`), vốn có các quy tắc tạo/cập nhật riêng khi tạo message mới.

Ở các hệ thống có yêu cầu kiểm toán, nên xây dựng hợp đồng sự kiện ghi rõ `eventId`, `eventType`, `occurredAt`, `aggregateId`, `correlationId`, `schemaVersion` nếu thực sự cần. Đừng để consumer phải phụ thuộc vào việc một header tình cờ được chuyển qua ranh giới Spring event.

## 8. Lọc type, lọc nội dung và định tuyến

Lỗi thường gặp là dùng một cấu hình lọc kiểu để thay cho quy tắc nghiệp vụ. Hãy chia ba bước:

1. **Lọc event class tại inbound adapter:** `setEventTypes(OrderApprovedApplicationEvent.class)` hoặc `setEventTypes(OrderApproved.class)` để tránh đưa sự kiện không liên quan vào flow.
2. **Chuẩn hóa payload:** dùng `@Transformer` để thống nhất về DTO hoặc record. Kiểm tra dữ liệu bắt buộc như `orderId`, `total` và `approvedAt`.
3. **Lọc/định tuyến nghiệp vụ:** dùng `Filter`, `Router` hoặc service activator để quyết định đơn hàng nào cần xử lý, event nào đi đến HTTP/JMS/Kafka hay nơi lưu trữ.

Ví dụ quy tắc nghiệp vụ cho đối tượng `OrderApproved`: chỉ những sự kiện có `total.signum() > 0` mới được đưa đến tiến trình thanh toán. Quy tắc này không thuộc `eventTypes` vì cả sự kiện hợp lệ và không hợp lệ đều cùng có class `OrderApproved`.

Một hạn chế khác: tên class Java là contract nội bộ trong cùng JVM; khi đẩy thông điệp sang broker hoặc dịch vụ khác, hãy xác định schema, content type, versioning và cơ chế serialize/deserialize riêng. Không gửi trực tiếp đối tượng Spring `ApplicationEvent` như một schema công khai của dịch vụ nếu bên nhận chỉ cần nghiệp vụ.

## 9. Mapping sai thường gây lỗi gì?

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra / khắc phục |
| --- | --- | --- |
| Inbound adapter không đẩy message vào channel | `eventTypes` lọc sai class; event là POJO nhưng đang lọc lớp `ApplicationEvent` không phù hợp | Xem đối tượng được truyền cho `publishEvent`; thử đúng `OrderApproved.class` hoặc event class cụ thể |
| Transformer báo không thể gọi method trên `String` | Đã thêm `payloadExpression="orderId"` nhưng transformer vẫn chờ một event object | Đồng bộ lại kiểu tham số transformer với payload mới |
| Listener `@EventListener(OrderApproved)` không chạy ở outbound | Payload là POJO nhưng `publishPayload=false` nên Spring nhận `MessagingEvent` | Bật `setPublishPayload(true)` hoặc đổi listener sang `MessagingEvent` |
| Mất `correlationId` sau khi sang Spring event | Phát POJO hoặc event mới không chứa message headers | Đưa correlation ID vào event contract hoặc dùng `MessagingEvent` để bảo toàn message |
| Đọc nhầm payload từ `getSource()` | Với `ApplicationEvent` thông thường, mặc định inbound payload là event, không phải source | Dùng transformer để trích dữ liệu hoặc cấu hình `payloadExpression` |
| Một event chạy qua nhiều lần hoặc lặp vô hạn | Inbound adapter thu lại sự kiện do outbound adapter của chính flow phát | Giới hạn type, tách hướng xử lý và tránh nối quay lại cùng chu kỳ publish |

Đặc biệt với `MessagingEvent`: event type thật sự là `MessagingEvent`, nhưng sau inbound adapter, payload được giữ theo message gốc. Vì vậy, khi kiểm tra lỗi, cần quan sát **cả runtime event class trước adapter lẫn runtime message payload class sau adapter**.

## 10. Lỗi, vòng đời và giới hạn vận hành

- **Ranh giới đồng bộ:** với cấu hình mặc định của `DirectChannel` và Spring `ApplicationEventMulticaster`, listener và flow có thể chạy trên thread đang phát event; exception downstream có thể ảnh hưởng caller. Inbound adapter hỗ trợ `errorChannel` để nhận `MessagingException` trong cấu hình phù hợp; không nên giả định mọi lỗi đều nổi lên cùng một đường khi có executor hoặc `@Async`.
- **Vòng đời context:** inbound adapter là thành phần trong Spring context; nếu tự tạo object nhưng không đăng ký bean hoặc không chạy lifecycle thích hợp, không thể kỳ vọng nó tự nhận sự kiện.
- **Không bền vững:** Spring application events không mặc định persist, retry xuyên lần khởi động, đảm bảo thứ tự giữa các thread hoặc exactly-once. Nếu cần trao đổi tin cậy giữa service, kết hợp adapter JMS/AMQP/Kafka với thiết kế giao hàng phù hợp.
- **Giao dịch:** event có thể được phát trước khi transaction ghi database commit; nếu downstream phải chạy sau commit, cân nhắc transaction-aware listener hoặc outbox, đồng thời kiểm tra ngữ cảnh transaction thực sự.
- **Chống vòng lặp:** không nối một event inbound flow vào outbound publisher phát lại đúng loại event mà inbound adapter đang nghe, trừ khi có điều kiện dừng rõ ràng.

## 11. Bài kiểm tra thực hành

Tự tạo một Spring Boot project có dependency `spring-boot-starter-integration` và `spring-integration-event` (được quản lý version đồng bộ theo Spring Boot). Dùng `OrderApprovedApplicationEvent` và `OrderApproved` trong ví dụ trên, rồi thực hiện:

| Ca thử | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| T1 — Đúng type | Phát `OrderApprovedApplicationEvent("ORD-01", ...)` | Consumer nhận `OrderApproved("ORD-01", ...)` |
| T2 — Sai type | Phát `ContextRefreshedEvent` hoặc một event class khác | Không tạo message đến flow đã lọc `OrderApprovedApplicationEvent.class` |
| T3 — POJO | Thay `eventTypes` bằng `OrderApproved.class`, bỏ bước transformer không cần thiết, phát `OrderApproved` | Consumer nhận payload đúng kiểu `OrderApproved` |
| T4 — Mapping expression | Cấu hình `payloadExpression` trích `orderId` và sửa consumer nhận `String` | Consumer nhận chỉ mã đơn hàng |
| T5 — Header | Phát `MessagingEvent` bọc `Message<OrderApproved>` có `correlationId`, cấu hình lọc `MessagingEvent.class` | Message qua inbound có cùng payload và header |
| T6 — Outbound mode | Gửi `Message<OrderApproved>` vào outbound adapter, lần lượt bật/tắt `publishPayload` | Listener theo `OrderApproved` nhận ở chế độ true; listener theo `MessagingEvent` nhận ở chế độ mặc định |
| T7 — Vòng lặp | Kiểm tra một flow có inbound và outbound cùng kiểu event | Luồng có điều kiện ngăn tự phát lại vô hạn |

Khi tự động hóa bằng JUnit, hãy assert **kiểu thực tế** của payload, giá trị các trường quan trọng, headers cần bảo toàn và số lần consumer nhận. Log hiển thị một đối tượng có tên giống event chưa đủ để khẳng định mapping đúng.

## 12. Câu hỏi tự đánh giá

1. Vì sao event type `OrderApprovedApplicationEvent` không nhất thiết là payload type mà consumer cuối cùng nhận?
2. Inbound adapter xử lý thế nào khi `ApplicationEvent.getSource()` là `Message<?>`?
3. Vì sao `payloadExpression` có thể khiến chữ ký `@Transformer` hiện tại không còn tương thích?
4. Khi `publishEvent(new OrderApproved(...))` được gọi, vì sao `setEventTypes(OrderApproved.class)` vẫn có thể dùng?
5. Nếu cần giữ `traceId` đi từ integration flow sang Spring listener, bạn chọn `MessagingEvent` hay phát POJO trực tiếp, và vì sao?
6. Khi chuyển event ra Kafka/JMS, những thông tin nào của hợp đồng cần đưa vào payload hoặc headers một cách có chủ đích?

## Tài liệu tham khảo

- [Spring Integration Reference — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html): quy tắc `eventTypes`, `payloadExpression`, `PayloadApplicationEvent`, `MessagingEvent` và `publishPayload`.
- [ApplicationEventListeningMessageProducer API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/inbound/ApplicationEventListeningMessageProducer.html).
- [ApplicationEventPublishingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/outbound/ApplicationEventPublishingMessageHandler.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
