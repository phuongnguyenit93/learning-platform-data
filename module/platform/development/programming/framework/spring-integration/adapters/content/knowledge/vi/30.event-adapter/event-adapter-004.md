# ApplicationEventPublishingMessageHandler: đưa Message ra hệ thống sự kiện Spring

## Mục tiêu bài học

Trong **Adapter sự kiện** của module **SPRING_INTEGRATION_ADAPTERS**, `ApplicationEventPublishingMessageHandler` là outbound adapter nối một luồng **Spring Integration** với cơ chế **Spring ApplicationEvent**. Sau bài học, bạn có thể:

- Giải thích vị trí của handler trong luồng `MessageChannel → MessageHandler → ApplicationEventPublisher → listener`.
- Cấu hình handler bằng Java, phân biệt chế độ mặc định và `setPublishPayload(true)`.
- Quyết định khi nào cần giữ nguyên `Message<?>` và headers, khi nào nên phát một sự kiện nghiệp vụ thuần.
- Kiểm tra quá trình phát sự kiện, xác định ranh giới lỗi và tránh vòng lặp sự kiện.

Đây là một điểm tích hợp **bên trong Spring ApplicationContext**. Khác với các outbound adapter đi đến HTTP, JMS, Kafka, SFTP hoặc hệ thống ngoài, handler này đưa dữ liệu của Spring Integration đến các thành phần đang lắng nghe sự kiện trong cùng ứng dụng/ngữ cảnh Spring. Nó hữu ích khi luồng tích hợp đã xử lý, định tuyến hoặc chuyển đổi một message và cần thông báo kết quả cho các thành phần nghiệp vụ khác.

## 1. Cơ chế hoạt động

`ApplicationEventPublishingMessageHandler` nằm trong package `org.springframework.integration.event.outbound`, kế thừa `AbstractMessageHandler` và triển khai `ApplicationEventPublisherAware`. Spring tiêm `ApplicationEventPublisher` cho bean; mỗi khi một message đến endpoint được gắn với handler, handler gọi cơ chế phát sự kiện của Spring.

~~~mermaid
flowchart LR
    A["Inbound adapter / gateway / service"] --> B["MessageChannel"]
    B --> C["ApplicationEventPublishingMessageHandler"]
    C --> D["Spring ApplicationEventPublisher"]
    D --> E["@EventListener"]
    D --> F["ApplicationListener"]
~~~

Ví dụ: sau khi một integration flow nhận dữ liệu đơn hàng, kiểm tra hợp lệ và chuẩn hóa payload, handler phát sự kiện `OrderCreated` để thành phần gửi thông báo hoặc ghi nhận audit xử lý. Thành phần gửi message chỉ cần biết `MessageChannel`, không cần gọi trực tiếp từng listener.

**Hướng dữ liệu cần nhớ:**

- **Outbound:** Spring Integration `Message<?>` → `ApplicationEventPublishingMessageHandler` → Spring event.
- **Inbound (chiều ngược lại):** Spring event → `ApplicationEventListeningMessageProducer` → Spring Integration `Message<?>`. Đây là adapter khác; không dùng `ApplicationEventPublishingMessageHandler` để nhận sự kiện.

Handler không có hợp đồng request/reply: nó phát sự kiện và hoàn thành xử lý message theo cách của outbound endpoint. Listener muốn phản hồi một giá trị thì phải thiết kế luồng khác để nhận kết quả; không nên trông chờ handler tự tạo reply message.

## 2. Payload nào thực sự được phát?

Quy tắc quyết định nằm ở thuộc tính `publishPayload`. Giá trị mặc định là `false`.

| Payload đến handler | `publishPayload` | Dữ liệu Spring nhận | Hệ quả với listener |
| --- | --- | --- | --- |
| Một đối tượng nghiệp vụ, ví dụ `OrderCreated` | `false` (mặc định) | `MessagingEvent` bọc **toàn bộ** `Message<?>` | Lắng nghe `MessagingEvent`, lấy `event.getMessage().getPayload()` và headers |
| Một đối tượng nghiệp vụ, ví dụ `OrderCreated` | `true` | Chính đối tượng `OrderCreated` được chuyển cho `publishEvent(Object)` | Có thể dùng `@EventListener` với tham số `OrderCreated`; headers của message gốc không tự đi kèm |
| Payload đã là một `ApplicationEvent` | `false` hoặc `true` | Đối tượng `ApplicationEvent` đó | Listener theo đúng kiểu sự kiện đã phát |

Khi `publishPayload=false` và payload chưa phải `ApplicationEvent`, `MessagingEvent` là lớp `org.springframework.integration.event.core.MessagingEvent`, có phương thức `getMessage()` để lấy lại message đầy đủ.

Khi `publishPayload=true` và payload là một POJO/record, Spring Framework hỗ trợ phát object đó qua `ApplicationEventPublisher.publishEvent(Object)`. Framework có thể dùng `PayloadApplicationEvent` ở phía trong; một phương thức `@EventListener` nhận đúng kiểu payload vẫn hoạt động. Cần phân biệt wrapper nội bộ của Spring với `MessagingEvent` do Spring Integration tạo ở chế độ mặc định.

Ví dụ với message sau:

~~~text
payload = OrderCreated(orderId="ORD-1042")
headers = { traceId="abc-123", ... }
~~~

- Chế độ mặc định: listener `MessagingEvent` đọc được cả `OrderCreated` lẫn `traceId` từ message.
- Chế độ `true`: listener `OrderCreated` nhận đối tượng nghiệp vụ; nếu cần `traceId`, hãy đặt nó trong event hoặc thiết kế một contract sự kiện chứa metadata cần thiết.

**Quy tắc chọn chế độ:** phát payload trực tiếp nếu muốn API nghiệp vụ gọn, listener độc lập với Spring Integration. Giữ mặc định nếu người nhận cần metadata hoặc headers của message gốc.

## 3. Cài dependency

Module hỗ trợ event của Spring Integration là `spring-integration-event`. Với ứng dụng Spring Boot quản lý các phiên bản dependency tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

Nếu không sử dụng cơ chế quản lý dependency của Spring Boot, hãy chỉ định phiên bản `spring-integration-event` tương thích với các module Spring Integration khác trong dự án. Các ví dụ bên dưới dùng Java 17+ (record) và cấu hình annotation.

## 4. Ví dụ hoàn chỉnh: từ MessageChannel đến @EventListener

Giả sử việc tạo đơn hàng đã được thực hiện ở tầng nghiệp vụ. Một service cần đưa thông tin `OrderCreated` vào kênh Spring Integration; listener Spring sẽ thực hiện hành động phụ như ghi audit hoặc gửi thông báo.

**Bước 1 — Định nghĩa sự kiện nghiệp vụ.**

`OrderCreated.java`:

~~~java
package com.example.orders;

import java.time.Instant;

public record OrderCreated(String orderId, Instant occurredAt) {
}
~~~

**Bước 2 — Tạo channel và gắn outbound handler.**

`OrderEventIntegrationConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.outbound.ApplicationEventPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderEventIntegrationConfig {

    @Bean
    public MessageChannel orderEventChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEventChannel")
    public ApplicationEventPublishingMessageHandler orderEventPublisher() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }
}
~~~

`@ServiceActivator(inputChannel = "orderEventChannel")` đăng ký handler làm consumer của kênh. Cấu hình `setPublishPayload(true)` ở đây có chủ đích: listener nghiệp vụ sẽ nhận `OrderCreated`, không phải `MessagingEvent`.

**Bước 3 — Gửi message từ service.**

`OrderCommandService.java`:

~~~java
package com.example.orders;

import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderCommandService {

    private final MessageChannel orderEventChannel;

    public OrderCommandService(
            @Qualifier("orderEventChannel") MessageChannel orderEventChannel) {
        this.orderEventChannel = orderEventChannel;
    }

    public void notifyOrderCreated(String orderId, String traceId) {
        var payload = new OrderCreated(orderId, Instant.now());
        var message = MessageBuilder.withPayload(payload)
                .setHeader("traceId", traceId)
                .build();

        if (!orderEventChannel.send(message)) {
            throw new IllegalStateException("Cannot dispatch OrderCreated");
        }
    }
}
~~~

Trong hệ thống thực tế, hãy gọi `notifyOrderCreated` tại vị trí phù hợp với ranh giới giao dịch và yêu cầu nghiệp vụ. Ví dụ này chỉ minh họa cách xuất một message vào adapter; nó không bao gồm thao tác lưu đơn hàng vào database.

**Bước 4 — Tiêu thụ Spring event.**

`OrderCreatedListener.java`:

~~~java
package com.example.orders;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Handle order: " + event.orderId());
    }
}
~~~

Khi `notifyOrderCreated("ORD-1042", "abc-123")` được gọi, chuỗi xử lý ở cấu hình trên là:

1. Service tạo `Message<OrderCreated>` và gửi vào `DirectChannel`.
2. `ServiceActivator` chuyển message đến `ApplicationEventPublishingMessageHandler`.
3. Handler phát payload `OrderCreated` qua `ApplicationEventPublisher`.
4. Spring gọi `onOrderCreated(OrderCreated)` trong ngữ cảnh đồng bộ mặc định; listener nhận `orderId = "ORD-1042"`.

Nếu không có listener phù hợp, Spring vẫn có thể chấp nhận sự kiện mà không tạo một hành động nghiệp vụ nào. Vì vậy, `send(...)` thành công không chứng minh thông báo đã được gửi hoặc audit đã được lưu.

## 5. Trường hợp cần toàn bộ Message và headers

Đổi cấu hình ở bước 2 bằng cách **bỏ** lời gọi `setPublishPayload(true)` (hoặc đặt `false`). Đây là chế độ mặc định của handler:

~~~java
@Bean
@ServiceActivator(inputChannel = "orderEventChannel")
public ApplicationEventPublishingMessageHandler orderEventPublisher() {
    return new ApplicationEventPublishingMessageHandler();
}
~~~

Lúc này, listener đọc `MessagingEvent`:

~~~java
package com.example.orders;

import org.springframework.context.event.EventListener;
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class MessageAuditListener {

    @EventListener
    public void onMessage(MessagingEvent event) {
        Message<?> message = event.getMessage();
        Object payload = message.getPayload();
        Object traceId = message.getHeaders().get("traceId");

        if (payload instanceof OrderCreated order) {
            System.out.println(
                    "Audit " + order.orderId() + " (traceId=" + traceId + ")");
        }
    }
}
~~~

Hai ví dụ ở mục 4 và mục 5 là **hai phương án thay thế**. Khi thực hành, hãy dùng listener tương ứng với giá trị `publishPayload` hiện tại. Không đăng ký đồng thời hai outbound handler trên cùng một `DirectChannel` với kỳ vọng mỗi message tự động đến cả hai: `DirectChannel` mặc định phân phối một message cho một subscriber được chọn.

## 6. Cấu hình bằng Java DSL hoặc XML

Nếu dự án dùng Spring Integration Java DSL, có thể tạo cùng một outbound endpoint mà không khai báo `@ServiceActivator`:

~~~java
@Bean
public IntegrationFlow orderEventFlow() {
    var handler = new ApplicationEventPublishingMessageHandler();
    handler.setPublishPayload(true);

    return IntegrationFlow.from("orderEventChannel")
            .handle(handler)
            .get();
}
~~~

Đoạn DSL giả định bean `orderEventChannel` đã tồn tại như ở mục 4. Chọn **một** cách đăng ký endpoint (DSL hoặc `@ServiceActivator`) cho luồng minh họa; nếu khai báo cả hai trên một `DirectChannel`, bạn đã tạo hai consumer cạnh tranh.

Với cấu hình XML namespace truyền thống:

~~~xml
<int:channel id="orderEventChannel"/>

<int-event:outbound-channel-adapter
    channel="orderEventChannel"
    publish-payload="true"/>
~~~

Đây là phần tử cốt lõi trong tài liệu XML có khai báo namespace `int` và `int-event` cùng schema tương ứng. Nếu chuyển channel thành `QueueChannel` (pollable) thì outbound endpoint phải có poller để lấy message; có thể điều chỉnh tốc độ bằng `fixed-rate`, `max-messages-per-poll` và `task-executor`. Với `DirectChannel` thông thường, việc xử lý bắt đầu ngay khi message được gửi.

## 7. Đồng bộ, giao dịch và xử lý lỗi

Các đặc tính dưới đây quyết định liệu adapter có phù hợp với yêu cầu vận hành hay không.

| Tình huống | Điều xảy ra | Cách thiết kế |
| --- | --- | --- |
| `DirectChannel` và listener Spring đồng bộ mặc định | Handler và listener chạy trong chuỗi lời gọi của bên gửi; lỗi runtime từ listener có thể truyền ngược đến bên gửi | Đặt chính sách lỗi rõ ràng; đừng coi việc phát event là luôn thành công |
| `ExecutorChannel`, poller bất đồng bộ hoặc listener chạy qua `@Async` | Xử lý có thể diễn ra ở thread khác; thời điểm hoàn tất và đường đi của lỗi thay đổi | Cấu hình error handling phù hợp từng ranh giới bất đồng bộ; không giả định exception luôn trở về service gửi |
| Cần thao tác listener chỉ sau khi DB commit | Phát event trước commit có thể khiến listener thấy trạng thái chưa commit; listener đồng bộ cũng có thể ảnh hưởng transaction | Cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` nếu việc publish diễn ra trong transaction phù hợp |
| Ứng dụng dừng hoặc process gặp sự cố | Event của Spring ApplicationContext không phải hàng đợi bền vững | Nếu cần retry xuyên process, lưu trữ durable hoặc giao hàng giữa dịch vụ, dùng outbox/message broker thích hợp |
| Cấu hình cả inbound và outbound event adapter | Nếu inbound thu lại event vừa được outbound phát và đưa về cùng luồng, có thể tạo vòng lặp vô hạn | Giới hạn `eventTypes`, chia tách channel/flow hoặc dùng điều kiện lọc |

Với `@TransactionalEventListener`, listener phụ thuộc vào transaction đang hoạt động (trừ khi bật cơ chế fallback thích hợp). Khi tách thread, cần xem xét việc truyền transaction context và yêu cầu sau commit; không nên xem annotation này là cơ chế đảm bảo giao hàng.

**Phân biệt event nội bộ và message broker:** `ApplicationEventPublishingMessageHandler` không tự ghi event xuống Kafka/JMS/AMQP, không thêm đảm bảo durable delivery, retry, dead-letter queue hay exactly-once. Nó chỉ dùng cơ chế phát sự kiện của Spring ApplicationContext. Khi cần giao tiếp ngoài process, hãy chọn outbound adapter hoặc gateway tương ứng của Spring Integration.

## 8. Kiểm tra và chẩn đoán

Để kiểm tra kịch bản ở mục 4 trong ứng dụng mẫu:

1. Khởi động Spring context có `OrderEventIntegrationConfig` và `OrderCreatedListener`.
2. Gọi `orderCommandService.notifyOrderCreated("ORD-1042", "trace-01")`.
3. Xác minh listener được gọi một lần với `OrderCreated.orderId() == "ORD-1042"`.
4. Chuyển handler về mặc định và thay listener bằng `MessageAuditListener` của mục 5; xác minh đọc được `traceId == "trace-01"` từ headers.
5. Thử một listener ném exception khi dùng `DirectChannel` và listener đồng bộ để quan sát exception lan về caller; lặp lại với kênh bất đồng bộ để thấy ranh giới lỗi khác nhau.

Trong automated test, nên dùng listener kiểm thử ghi event vào một bộ nhớ tạm như `AtomicReference<OrderCreated>` hoặc danh sách đồng bộ, rồi assert số lần nhận và nội dung sự kiện. Nếu chỉ thấy log `Message sent` mà không thấy listener chạy, hãy kiểm tra lần lượt:

- Handler đã được đăng ký vào đúng `inputChannel` chưa, và bean có nằm trong Spring context đang chạy không?
- Listener mong chờ `OrderCreated` hay `MessagingEvent`? Chế độ `publishPayload` hiện tại là gì?
- Có consumer khác cùng nhận trên `DirectChannel` không? Nếu muốn gửi đến nhiều handler Spring Integration, cân nhắc `PublishSubscribeChannel`; nếu muốn nhiều listener Spring nhận cùng một event, đăng ký nhiều Spring listener phù hợp.
- Có lọc event theo kiểu, dùng `@Async`, poller, hoặc transaction listener làm thay đổi thời điểm nhận không?
- Có vô tình nối inbound event adapter về channel dẫn tới outbound handler, tạo vòng lặp không?

## 9. Bài tập áp dụng

**Bài tập 1 — Event nghiệp vụ:** xây dựng flow nhận `PaymentConfirmed(paymentId, orderId)`, phát payload trực tiếp, dùng hai listener độc lập: cập nhật báo cáo và gửi thông báo. Quan sát cả hai Spring listeners được gọi từ một lần phát event.

**Bài tập 2 — Theo dõi trace:** đổi về `publishPayload=false`, đưa `correlationId` vào message header và tạo listener `MessagingEvent` để log `correlationId`. Giải thích vì sao listener `PaymentConfirmed` ở bài tập 1 cần chỉnh lại nếu không dùng chế độ phát payload.

**Bài tập 3 — Phân tích lỗi:** đặt một listener ném `IllegalStateException`, so sánh đường đi của exception khi dùng `DirectChannel` với một cấu hình xử lý bất đồng bộ. Xác định nơi cần đặt cơ chế khắc phục, đồng thời mô tả lý do không nên dùng event nội bộ như hàng đợi tin cậy giữa các service.

## Tài liệu tham khảo

- [Spring Integration Reference — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html)
- [ApplicationEventPublishingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/outbound/ApplicationEventPublishingMessageHandler.html)
- [MessagingEvent API](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/event/core/MessagingEvent.html)
