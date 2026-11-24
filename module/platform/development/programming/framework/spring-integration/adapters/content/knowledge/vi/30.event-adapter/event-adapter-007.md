# Transaction-bound application event trong Spring Integration

## Mục tiêu bài học

Trong chương **Adapter sự kiện** thuộc module **SPRING_INTEGRATION_ADAPTERS**, chúng ta dùng Spring Application Events để kết nối các thành phần trong cùng ứng dụng với các luồng `MessageChannel`. Một vấn đề thường gặp là: **message đã được phát, nhưng transaction của thao tác nghiệp vụ cuối cùng lại rollback**. Nếu listener đã gửi email, cập nhật hệ thống ngoài hoặc phát message đến Kafka/JMS trước khi commit, các hệ thống có thể ghi nhận một thay đổi chưa từng được lưu thành công.

**Transaction-bound application event** giải quyết yêu cầu về **thời điểm chạy listener theo trạng thái transaction** nhờ `@TransactionalEventListener` của Spring Framework. Bài học tập trung vào cách áp dụng nó cùng outbound/inbound event adapter, ảnh hưởng của thread, cách xử lý hậu commit và giới hạn về độ tin cậy khi trao đổi với hệ thống ngoài.

Sau bài này, bạn có thể:

- Phân biệt `@EventListener` và `@TransactionalEventListener`.
- Chọn đúng `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`.
- Phát sự kiện qua `ApplicationEventPublishingMessageHandler` trong một transaction đang hoạt động.
- Chỉ chuyển message vào một integration flow **sau khi commit** bằng transactional listener.
- Nhận biết khi nào `ExecutorChannel`, `@Async` hoặc multicaster executor làm thay đổi ngữ cảnh transaction.
- Kiểm thử commit/rollback và chọn **transactional outbox** khi cần phát message bền vững qua JMS, AMQP, Kafka, HTTP.

## 1. Vấn đề: sự kiện phát trước khi dữ liệu được commit

Giả sử service xử lý đặt hàng theo trình tự:

~~~text
BEGIN TRANSACTION
  INSERT order
  publish OrderPlaced event
  UPDATE inventory             <-- thất bại
ROLLBACK
~~~

Nếu Spring listener gọi hệ thống gửi email ngay lúc `publishEvent(...)`, khách hàng có thể nhận thông báo "đặt hàng thành công" dù cả transaction đã rollback.

Với `@EventListener` thông thường và Spring event multicaster đồng bộ mặc định, listener chạy **ngay khi event được phát**, bên trong transaction của caller nếu có. Annotation này không tự đợi commit.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant DB as Database
    participant P as ApplicationEventPublisher
    participant L as @EventListener
    S->>DB: BEGIN, INSERT order
    S->>P: publish OrderPlaced
    P->>L: Xử lý ngay
    L-->>P: Đã gửi thông báo
    S->>DB: UPDATE inventory lỗi
    S->>DB: ROLLBACK
    Note over L,DB: Thông báo đã ra ngoài nhưng đơn hàng không tồn tại
~~~

Chỉ cần thay listener phù hợp thành `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, Spring sẽ đăng ký xử lý với transaction hiện tại và gọi listener **khi transaction đã commit thành công**.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant DB as Database
    participant P as ApplicationEventPublisher
    participant L as @TransactionalEventListener
    S->>DB: BEGIN, INSERT order
    S->>P: publish OrderPlaced
    P-->>S: Đăng ký callback cho transaction
    S->>DB: COMMIT thành công
    DB-->>L: AFTER_COMMIT
    L->>L: Xử lý OrderPlaced
~~~

**Phân biệt hai bảo đảm:** `AFTER_COMMIT` cho biết **thời điểm gọi listener sau commit**. Nó **không** làm sự kiện được lưu bền vững; nếu tiến trình dừng giữa lúc commit xong và lúc listener hoàn thành, tác vụ vẫn có thể bị mất.

## 2. @EventListener khác @TransactionalEventListener ra sao?

| Tiêu chí | `@EventListener` | `@TransactionalEventListener` |
| --- | --- | --- |
| Thời điểm xử lý | Khi Spring multicaster dispatch event | Theo pha của transaction |
| Cần transaction đang hoạt động? | Không | Mặc định **có** |
| Không có transaction | Vẫn xử lý nếu event phù hợp | Mặc định **bỏ qua event**, trừ khi bật `fallbackExecution` |
| Chỉ chạy sau commit | Không | Dùng `phase = AFTER_COMMIT` |
| Khi transaction rollback | Có thể đã xử lý trước rollback | `AFTER_COMMIT` không chạy; `AFTER_ROLLBACK` chạy |
| Giao hàng bền vững khi process chết | Không | Không |
| Dùng cho | Quan sát, xử lý trong ứng dụng, tác vụ không phụ thuộc commit | Hành động phụ thuộc kết quả transaction |

Ví dụ hai listener nhận cùng một payload nghiệp vụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderListeners {

    @EventListener
    public void onPublished(OrderPlaced event) {
        System.out.println("Event observed now: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderPlaced event) {
        System.out.println("Order committed: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRolledBack(OrderPlaced event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

Với một transaction thành công, `onPublished` chạy trong quá trình publish; `onCommitted` chạy sau commit; `onRolledBack` không chạy. Nếu transaction rollback, `onCommitted` không chạy còn `onRolledBack` chạy. Ví dụ này giả định event được phát **khi transaction thực sự đang hoạt động** và Spring đang dùng ngữ cảnh transaction thông thường.

## 3. Bốn transaction phase

`@TransactionalEventListener` có thuộc tính `phase` thuộc enum `org.springframework.transaction.event.TransactionPhase`.

| Phase | Khi chạy | Công việc phù hợp | Điểm cần cẩn trọng |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit hoàn tất | Kiểm tra bổ sung, đồng bộ trạng thái cần đi cùng giao dịch | Sau đó transaction **vẫn có thể rollback**; không gửi side effect không thể thu hồi |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Tạo tác vụ thông báo, đẩy bước xử lý tiếp theo | Side effect có thể thất bại sau khi dữ liệu chính đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận tình huống hủy giao dịch, giải phóng tài nguyên ngoài phù hợp | Không thể coi dữ liệu vừa ghi trong transaction là đã tồn tại |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, commit **hoặc** rollback | Dọn dẹp hoặc telemetry áp dụng cho cả hai kết quả | Không phân biệt kết quả chỉ bằng việc callback được gọi |

Mặc định `phase` là **`AFTER_COMMIT`**. Vì vậy hai annotation dưới đây tương đương về phase:

~~~java
@TransactionalEventListener
public void afterCommitA(OrderPlaced event) {
    // ...
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommitB(OrderPlaced event) {
    // ...
}
~~~

Trong ví dụ trên, nếu đăng ký **cả hai** listener, một event được commit sẽ gọi cả hai. Khi dùng thực tế, chỉ đăng ký các listener thật sự cần thiết.

### BEFORE_COMMIT không phải "chắc chắn sẽ commit"

Một listener `BEFORE_COMMIT` có thể chạy, sau đó commit vẫn thất bại vì ràng buộc DB hoặc một callback khác. Nếu listener gửi email ở phase này, email đã gửi không được rollback cùng database. Ngược lại, exception từ listener chạy trước commit có thể làm transaction không thể hoàn tất; cần quyết định rõ lỗi nào phải chặn nghiệp vụ chính.

### AFTER_COMMIT không có nghĩa bắt đầu một transaction mới

Spring cảnh báo rằng sau commit hoặc rollback, tài nguyên giao dịch như connection/session vẫn có thể còn gắn với thread trong giai đoạn callback. Nếu listener cố ghi database tại thời điểm này, thao tác có thể vẫn "tham gia" ngữ cảnh tài nguyên cũ nhưng **không có commit tiếp theo** để bảo đảm dữ liệu được lưu.

Muốn ghi một bản ghi audit, cập nhật bảng hoặc thực hiện thao tác DB độc lập sau commit, hãy gọi một bean khác có phương thức mở **transaction mới** bằng `Propagation.REQUIRES_NEW`. Ví dụ ở mục 7.

## 4. Ví dụ: outbound event adapter phát event bên trong transaction

Bài toán: service lưu đơn hàng qua JDBC, đồng thời phát `OrderPlaced` cho các listener Spring. Listener gửi thông báo chỉ được chạy sau khi giao dịch ghi DB commit.

### 4.1. Dependency và schema

Với Spring Boot có cơ chế quản lý phiên bản dependency tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("com.h2database:h2")
}
~~~

Ứng dụng cần cấu hình `DataSource` và transaction manager JDBC phù hợp; trong dự án Spring Boot JDBC thông thường, phần cấu hình này được tự động hóa khi có datasource tương ứng.

Schema minh họa (H2):

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

### 4.2. Định nghĩa event nghiệp vụ

`OrderPlaced.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPlaced(
        String orderId,
        BigDecimal amount,
        Instant occurredAt) {
}
~~~

Đây là một record nghiệp vụ, không kế thừa `ApplicationEvent`. Spring hỗ trợ phát POJO như application event; listener có thể nhận `OrderPlaced` trực tiếp khi outbound adapter bật chế độ phát payload.

### 4.3. Outbound event adapter với DirectChannel

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
    public MessageChannel orderEvents() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public ApplicationEventPublishingMessageHandler orderEventPublisher() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }
}
~~~

`DirectChannel` mặc định gọi handler trong **thread của bên gửi**. Do đó, khi service gọi `orderEvents.send(...)` trong transaction, `ApplicationEventPublishingMessageHandler` phát `OrderPlaced` **trong cùng thread** đang giữ transaction context. `@TransactionalEventListener` có thể đăng ký callback với transaction đó.

`setPublishPayload(true)` cũng rất quan trọng: với record `OrderPlaced`, nó khiến listener khai báo tham số `OrderPlaced` nhận được đúng kiểu event mong muốn. Nếu để mặc định `false`, outbound handler phát `MessagingEvent` chứa `Message<OrderPlaced>`; khi đó listener `OrderPlaced` trong bài sẽ không được gọi theo cách mong muốn.

### 4.4. Service ghi database và gửi message

`OrderService.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final MessageChannel orderEvents;

    public OrderService(
            JdbcTemplate jdbc,
            @Qualifier("orderEvents") MessageChannel orderEvents) {
        this.jdbc = jdbc;
        this.orderEvents = orderEvents;
    }

    @Transactional
    public void placeOrder(String orderId, BigDecimal amount) {
        insertAndPublish(orderId, amount);
    }

    @Transactional
    public void placeOrderThenFail(String orderId, BigDecimal amount) {
        insertAndPublish(orderId, amount);
        throw new IllegalStateException("Simulated failure after publish");
    }

    private void insertAndPublish(String orderId, BigDecimal amount) {
        jdbc.update(
                "INSERT INTO orders (order_id, amount) VALUES (?, ?)",
                orderId,
                amount);

        var message = MessageBuilder
                .withPayload(new OrderPlaced(
                        orderId, amount, Instant.now()))
                .setHeader("correlationId", orderId)
                .build();

        if (!orderEvents.send(message)) {
            throw new IllegalStateException(
                    "Cannot publish OrderPlaced: " + orderId);
        }
    }
}
~~~

Hãy gọi hai phương thức public `placeOrder(...)` và `placeOrderThenFail(...)` **qua Spring-managed bean** (không tạo bằng `new`, không gọi tự thân từ một phương thức cùng bean với kỳ vọng proxy transaction sẽ được áp dụng). Ví dụ dùng `OrderService` do Spring inject vào controller hoặc test.

Với `placeOrder("ORD-01", new BigDecimal("120.50"))`:

1. `@Transactional` mở transaction JDBC.
2. `INSERT` ghi đơn hàng trong transaction hiện tại.
3. Service gửi `Message<OrderPlaced>` vào `DirectChannel`.
4. Outbound handler phát `OrderPlaced` qua `ApplicationEventPublisher`.
5. `@TransactionalEventListener(AFTER_COMMIT)` đăng ký callback.
6. Service trả về; transaction manager commit, sau đó listener `AFTER_COMMIT` chạy.

Với `placeOrderThenFail("ORD-02", ...)`, exception runtime khiến transaction rollback. Listener `AFTER_COMMIT` **không** chạy cho `ORD-02`; listener `AFTER_ROLLBACK` có thể chạy.

**Lưu ý về headers:** `correlationId` trong message không tự nằm trong `OrderPlaced` khi bật `publishPayload=true`. Nếu consumer Spring cần correlation ID để audit, thêm nó vào event contract, hoặc dùng chế độ `MessagingEvent` và listener nhận đúng kiểu tương ứng. Đây là quyết định về **payload mapping**, độc lập với transaction phase.

### 4.5. Listener sau commit

`OrderPlacedListeners.java`:

~~~java
package com.example.orders;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPlacedListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onSuccess(OrderPlaced event) {
        System.out.println(
                "Committed order: " + event.orderId());
        // Ví dụ triển khai thật: đề nghị gửi notification sau commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlaced event) {
        System.out.println(
                "Rolled back order: " + event.orderId());
    }
}
~~~

Phần ví dụ dùng log để dễ quan sát phase; khi chuyển sang hệ thống gửi email, HTTP hoặc message broker, cần thêm retry, monitoring và cơ chế xử lý thất bại sau commit.

## 5. Luồng inbound: đưa message vào Spring Integration **sau commit**

Có một khác biệt quan trọng giữa "Spring Integration nhận application event" và "Spring Integration chỉ nhận event đã commit".

`ApplicationEventListeningMessageProducer` là **inbound event adapter**. Nó nhận Spring application event từ multicaster và gửi message vào output channel. Tuy nhiên, adapter này **tự nó không chờ transaction commit**. Nếu event được phát trong transaction, inbound adapter mặc định có thể gửi message ngay lúc publish.

~~~mermaid
flowchart TD
    S["Transactional Service"] --> P["ApplicationEventPublisher"]
    P --> D["ApplicationEventListeningMessageProducer"]
    D --> R["rawEvents channel"]
    R --> H["Integration handler chạy trước commit"]
    P --> T["@TransactionalEventListener AFTER_COMMIT"]
    T --> C["committedEvents channel"]
    C --> B["Integration handler chạy sau commit"]
~~~

Nếu downstream chỉ được xử lý khi transaction commit, có thể dùng **transactional event listener làm cầu nối** sang message channel:

`CommittedOrderFlowConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CommittedOrderFlowConfig {

    @Bean
    public MessageChannel committedOrderEvents() {
        return new DirectChannel();
    }
}
~~~

`CommittedOrderForwarder.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommittedOrderForwarder {

    private final MessageChannel committedOrderEvents;

    public CommittedOrderForwarder(
            @Qualifier("committedOrderEvents") MessageChannel channel) {
        this.committedOrderEvents = channel;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void forward(OrderPlaced event) {
        if (!committedOrderEvents.send(
                MessageBuilder.withPayload(event).build())) {
            throw new IllegalStateException(
                    "Failed to forward committed order");
        }
    }
}
~~~

`CommittedOrderConsumer.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class CommittedOrderConsumer {

    @ServiceActivator(inputChannel = "committedOrderEvents")
    public void handle(OrderPlaced event) {
        System.out.println(
                "Integration flow after commit: " + event.orderId());
    }
}
~~~

Kết quả:

- Service phát event trước commit để đăng ký callback.
- Chỉ sau khi commit thành công, `CommittedOrderForwarder` gửi một `Message<OrderPlaced>` vào channel.
- `CommittedOrderConsumer` thực thi dưới mô hình xử lý của Spring Integration; tại điểm này, transaction ban đầu đã commit.

Đây là cách tổ chức rõ ràng khi muốn xử lý business event bằng `ServiceActivator`, `Transformer`, `Router` hoặc outbound adapter HTTP/JMS/Kafka **sau commit**.

**Không nên đồng thời cấu hình inbound `ApplicationEventListeningMessageProducer` nhận cùng `OrderPlaced` rồi cho nó đẩy thẳng vào `committedOrderEvents`**, vì nhánh inbound đó sẽ bỏ qua quy tắc hậu commit và chạy ngay khi event được phát.

## 6. Vì sao thread là điều kiện quyết định?

Với **transaction imperative** thông thường (JDBC/JPA), Spring giữ transaction context trong `ThreadLocal`. `@TransactionalEventListener` được đăng ký khi event được phát trên thread có transaction hoạt động.

Ví dụ đúng:

~~~text
Thread A:
  @Transactional
    INSERT order
    DirectChannel.send(...)
      -> ApplicationEventPublishingMessageHandler
      -> publishEvent(OrderPlaced)
      -> register AFTER_COMMIT callback
    COMMIT
    callback chạy AFTER_COMMIT
~~~

Ví dụ có nguy cơ sai:

~~~text
Thread A (có transaction):
  @Transactional
    INSERT order
    ExecutorChannel.send(message)
    COMMIT

Thread B (không kế thừa transaction ThreadLocal):
  ApplicationEventPublishingMessageHandler
    -> publishEvent(OrderPlaced)
    -> @TransactionalEventListener không thấy transaction
    -> mặc định bỏ qua event
~~~

Ngay cả khi worker xử lý trước thời điểm thread A commit, thread B vẫn không tự có transaction context của thread A. Bởi vậy **chỉ thay `DirectChannel` bằng `ExecutorChannel` trước event publisher** có thể làm listener hậu commit không được gọi.

| Cấu hình | Context khi publish event | Khả năng đăng ký AFTER_COMMIT |
| --- | --- | --- |
| `@Transactional` → `DirectChannel` → outbound handler | Cùng thread, cùng imperative transaction | Có, nếu transaction đang hoạt động |
| `@Transactional` → `ExecutorChannel` → outbound handler | Executor thread khác | Thường không thấy transaction gốc |
| `@Transactional` → gọi `ApplicationEventPublisher` trực tiếp | Cùng thread | Có |
| Event được publish sau khi phương thức transactional đã kết thúc | Không còn transaction gốc | Mặc định không đăng ký được listener |
| Multicaster dùng executor | Phụ thuộc loại listener | Transactional listener phải được xem xét riêng; không nên giả định mọi listener async |

Từ **Spring Framework 6.1**, `TransactionalApplicationListener` là ví dụ listener báo không hỗ trợ async execution do multicaster lập lịch; việc **đăng ký transaction callback** vẫn cần gắn với thread phát event. Một `@Async` gắn trên phương thức listener lại là câu chuyện khác: phần thân có thể được chuyển sang executor **sau khi phase đã xảy ra**, và khi ấy không còn transaction context cũ.

**Nguyên tắc thiết kế:** phát event cần ràng buộc transaction trên đường đồng bộ, rồi mới tách phần xử lý hậu commit sang executor hoặc message broker nếu cần.

## 7. Lưu database sau AFTER_COMMIT: cần REQUIRES_NEW

Giả sử sau khi đặt hàng thành công, bạn muốn ghi thêm một bản ghi vào bảng `notification_audit`. Hãy tách phần ghi DB thành một Spring bean khác, mở một transaction mới:

~~~java
package com.example.orders;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NotificationAuditService {

    private final JdbcTemplate jdbc;

    public NotificationAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        jdbc.update(
                "INSERT INTO notification_audit(order_id) VALUES (?)",
                orderId);
    }
}
~~~

Với schema ví dụ:

~~~sql
CREATE TABLE notification_audit (
    order_id VARCHAR(80) PRIMARY KEY
);
~~~

Listener gọi bean trên:

~~~java
@Component
public class NotificationAuditListener {

    private final NotificationAuditService audit;

    public NotificationAuditListener(NotificationAuditService audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        audit.record(event.orderId());
    }
}
~~~

`NotificationAuditService` và `NotificationAuditListener` nằm trong hai bean để lời gọi `record(...)` đi qua proxy quản lý transaction của Spring. `REQUIRES_NEW` tạo transaction riêng, có commit/rollback riêng; lỗi ghi audit sau đó **không thể rollback đơn hàng vốn đã commit**.

Đoạn trên giả định đã import `Component`, `TransactionalEventListener` và `TransactionPhase` như các ví dụ trước. Trong production, phải quyết định việc ghi audit thất bại sẽ được ghi nhận và retry thế nào; `REQUIRES_NEW` không tự đem lại retry hay durable delivery.

## 8. fallbackExecution: khi event không nằm trong transaction

Theo mặc định, `@TransactionalEventListener` **không xử lý** event phát ngoài một transaction phù hợp.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Không chạy nếu không có transaction để đăng ký callback.
}
~~~

Nếu muốn listener xử lý cả trường hợp không có transaction:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCommittedOrFallback(OrderPlaced event) {
    // Khi có transaction: theo AFTER_COMMIT.
    // Khi không có transaction: xử lý ngay theo nhánh fallback.
}
~~~

**Cảnh báo về ngữ nghĩa:** với `fallbackExecution=true`, chữ "AFTER_COMMIT" không còn đồng nghĩa **mọi lần chạy đều sau một database commit**. Trong trường hợp không có transaction, không có commit nào để chờ. Vì vậy không nên bật fallback nếu hợp đồng nghiệp vụ bắt buộc phải có commit thực sự trước khi xử lý.

Trong test, script chạy độc lập hoặc call từ một thành phần không có `@Transactional`, việc listener "không nhận event" có thể chính là hành vi đúng của mặc định. Trước khi bật fallback, hãy kiểm tra vì sao event không được phát trong transaction như dự kiến.

## 9. @Async và ApplicationEventMulticaster: nên tách ở điểm nào?

Có ba vị trí liên quan tới việc chuyển thread, nhưng ý nghĩa giao dịch khác nhau.

### Trước khi phát event

~~~text
@Transactional service
    -> ExecutorChannel
        -> outbound publisher
            -> @TransactionalEventListener
~~~

Trường hợp này có nguy cơ làm mất transaction context. Tránh áp dụng nếu mục tiêu là đăng ký callback với transaction của service.

### Trong Spring multicaster

`SimpleApplicationEventMulticaster` có thể nhận `TaskExecutor`. Điều này cho phép các listener đủ điều kiện chạy bất đồng bộ. Tuy nhiên transactional listeners có ràng buộc đăng ký transaction; không nên dựa vào một executor toàn cục để "tự đưa `@TransactionalEventListener` chạy sau commit".

Ngoài ra, cấu hình `applicationEventMulticaster` thay đổi hành vi nhiều listener trong context. Với ứng dụng có listener xử lý Spring lifecycle events, kiểm tra tác động rộng trước khi bật async trên toàn multicaster.

### Sau commit

Nếu một listener hậu commit cần gọi HTTP hoặc gửi email chậm, có thể chuyển **phần tác vụ** sang `@Async`:

~~~java
@Configuration
@EnableAsync
public class AsyncNotificationConfig {

    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

~~~java
@Component
public class AsyncOrderNotificationListener {

    @Async("notificationExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderPlaced event) {
        System.out.println(
                "Sending notification for " + event.orderId()
                + " on " + Thread.currentThread().getName());
    }
}
~~~

Trong ví dụ này, cần import `Configuration`, `Bean`, `EnableAsync`, `ThreadPoolTaskExecutor`, `Component`, `Async`, `TransactionalEventListener` và `TransactionPhase` tương ứng. Listener được đăng ký với transaction khi publish, nhưng phần thân xử lý `@Async` chạy trên executor sau thời điểm callback hậu commit được kích hoạt.

Hệ quả:

- Caller không chờ nội dung listener async hoàn tất.
- Ngữ cảnh transaction của thread publish không tự được chuyển sang worker.
- Lỗi của phương thức `void @Async` cần được xử lý/quan sát bằng logging, `AsyncUncaughtExceptionHandler` hoặc cơ chế nghiệp vụ khác.
- Nếu queue bão hòa, tác vụ có thể bị từ chối ngay khi dispatch sau commit; đơn hàng vẫn đã commit.

Với thông báo cực kỳ quan trọng, nên ghi một bản ghi **outbox** trong cùng transaction với đơn hàng rồi dùng worker độc lập gửi sau commit.

## 10. Sau commit không có nghĩa message được giao thành công

Một số tình huống cần phân biệt:

| Tình huống | Trạng thái DB chính | Trạng thái event/tác vụ phụ |
| --- | --- | --- |
| Transaction rollback trước commit | Đã rollback | `AFTER_COMMIT` không chạy |
| Commit thành công, listener gửi HTTP thành công | Đã commit | Tác vụ phụ hoàn tất |
| Commit thành công, listener gửi HTTP timeout | Đã commit | Tác vụ phụ thất bại; không thể tự rollback transaction chính |
| Commit thành công, process crash trước listener | Đã commit | Event in-memory có thể bị mất |
| Commit thành công, listener async được lập lịch nhưng process chết | Đã commit | Task chưa chạy hoặc đang chạy có thể bị mất |
| Commit thành công, listener gửi Kafka nhưng chưa có ack | Đã commit | Cần chính sách xác nhận, retry, idempotency theo transport |

Đặc biệt, exception trong listener hậu commit **không thể quay ngược và hủy một commit đã thành công**. Tùy callback/lifecycle và loại lỗi, exception vẫn có thể xuất hiện ở thread xử lý commit hoặc bị ghi nhận ở nơi khác. Không nên diễn giải exception từ phương thức `placeOrder(...)` là bằng chứng database đã rollback nếu lỗi phát sinh sau khi commit.

### Transactional outbox cho kết nối ngoài ứng dụng

Khi cần gửi sự kiện tin cậy tới Kafka, JMS, AMQP, HTTP hay service ngoài, mô hình **transactional outbox** thường thích hợp hơn chỉ dùng `@TransactionalEventListener`:

~~~mermaid
flowchart LR
    S["@Transactional OrderService"] --> D["Database: orders"]
    S --> O["Database: outbox_events"]
    D ---|"Cùng một DB transaction"| O
    O --> P["Poller / CDC / Relay"]
    P --> B["Kafka / JMS / AMQP / HTTP"]
    B --> C["Consumer"]
~~~

Các bước:

1. Trong **cùng một database transaction**, ghi bản ghi nghiệp vụ vào `orders` và sự kiện cần gửi vào `outbox_events`.
2. Chỉ sau khi transaction commit, một poller, CDC hoặc relay độc lập mới đọc outbox đã commit.
3. Relay gửi event qua adapter phù hợp, theo dõi xác nhận của hệ thống đích và cập nhật trạng thái gửi.
4. Nếu relay hoặc process chết, bản ghi outbox vẫn còn để thử lại.
5. Consumer có thể nhận trùng do retry, nên cần idempotency theo `eventId` hoặc khóa nghiệp vụ.

`@TransactionalEventListener(AFTER_COMMIT)` có thể dùng như **tín hiệu đánh thức relay để giảm độ trễ**, nhưng không được là nguồn dữ liệu duy nhất; relay vẫn cần quét outbox để phục hồi sự kiện bị mất.

## 11. Transaction-bound listener với reactive transaction

Các ví dụ trước dùng Spring JDBC/JPA và **imperative transaction** dựa trên `ThreadLocal`.

Từ **Spring Framework 6.1**, `@TransactionalEventListener` cũng hỗ trợ **reactive transactions**. Tuy nhiên, reactive transaction được mang trong **Reactor Context** thay vì `ThreadLocal`; việc gọi `ApplicationEventPublisher.publishEvent(...)` thông thường không có nghĩa listener đã biết reactive transaction hiện tại.

Với reactive flow:

- Dùng cơ chế được Spring hỗ trợ để gắn **transaction context vào event source**.
- Spring cung cấp `org.springframework.transaction.reactive.TransactionalEventPublisher` để hỗ trợ phát event trong reactive transaction.
- Bảo đảm thao tác publish thuộc cùng chuỗi `Mono`/`Flux` có transaction; không gọi `subscribe()` tùy tiện để tách một chuỗi xử lý rồi mong giữ transaction.
- Kiểm tra phiên bản Spring Framework, transaction manager và API đang dùng; ví dụ imperative dựa trên `DirectChannel` ở mục 4 không thể chuyển nguyên xi sang giao dịch reactive.

Sơ đồ khái niệm:

~~~text
Reactive transaction (Reactor Context)
  -> ghi dữ liệu reactive
  -> TransactionalEventPublisher (gắn context vào event)
  -> transaction-bound listener
  -> xử lý theo phase
~~~

Dù dùng reactive hay imperative, transaction phase vẫn không cung cấp durable delivery tới hệ thống ngoài.

## 12. Kiểm thử commit và rollback

Kiểm thử nên assert **hành vi theo transaction thực tế**, không chỉ assert rằng `publishEvent(...)` trả về thành công.

Với ví dụ `OrderService` ở mục 4:

| Ca thử | Thao tác | Điều cần kiểm tra |
| --- | --- | --- |
| T1 — Commit | `placeOrder("ORD-01", ...)` | DB có đơn; listener `AFTER_COMMIT` nhận một lần; `AFTER_ROLLBACK` không nhận |
| T2 — Rollback | `placeOrderThenFail("ORD-02", ...)` | DB không có đơn; `AFTER_COMMIT` không nhận; `AFTER_ROLLBACK` nhận một lần |
| T3 — Không transaction | Gọi `publishEvent(new OrderPlaced(...))` từ nơi không có transaction | Listener transaction-bound mặc định không nhận |
| T4 — Fallback | Bật `fallbackExecution=true` rồi phát ngoài transaction | Listener nhận ngay theo nhánh fallback |
| T5 — Thread boundary | Đổi `orderEvents` thành `ExecutorChannel` trước publisher | Kiểm tra transaction callback không còn được đăng ký với transaction gốc như kỳ vọng |
| T6 — Sau commit | Forward event vào `committedOrderEvents` | Service activator chỉ chạy sau commit và không chạy nếu rollback |
| T7 — Lỗi hậu commit | Làm tác vụ phụ thất bại | Đơn hàng vẫn đã commit; lỗi phải được xử lý ở cơ chế hậu commit |

Trong Spring tests, **test-level `@Transactional` thường rollback theo mặc định**. Vì vậy test gọi `placeOrder(...)` bên trong một test transaction chưa commit có thể khiến `AFTER_COMMIT` không chạy, dù code đúng. Để kiểm thử:

- Dùng `TransactionTemplate` và kết thúc transaction tường minh.
- Hoặc với Spring TestContext, dùng `TestTransaction.flagForCommit()` / `TestTransaction.end()` tại thời điểm phù hợp.
- Dùng listener probe đếm event và ghi event ID vào bộ nhớ kiểm thử; assert sau khi transaction đã hoàn tất.
- Với asynchronous listener, dùng `CountDownLatch`/cơ chế chờ điều kiện có timeout, tránh chỉ dựa vào `Thread.sleep`.

Ví dụ ý tưởng kiểm tra bằng `TransactionTemplate`:

~~~java
import java.math.BigDecimal;
import org.springframework.transaction.support.TransactionTemplate;

// Trong method test, đã inject transactionTemplate, publisher và probe.
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderPlaced(
            "ORD-T1", new BigDecimal("12.00"), java.time.Instant.now()));
    // Probe AFTER_COMMIT chưa nhận ORD-T1 trong block này.
});

// Khi executeWithoutResult trả về sau commit thành công:
// Probe AFTER_COMMIT đã được gọi trong trường hợp listener đồng bộ.
~~~

Đoạn trên minh họa **thời điểm callback**; việc kiểm tra DB của ví dụ service nên nằm trong integration test riêng với `DataSource`. Không dùng cùng một bộ đếm listener cho nhiều test song song nếu không bảo đảm an toàn thread hoặc reset đúng cách.

### Các log nên có khi chẩn đoán

Ghi các trường: `orderId`/`eventId`, `phase`, `threadName`, thời điểm publish, kết quả commit/rollback, thời điểm listener chạy và kết quả gửi ra adapter ngoài. Nếu listener không chạy, lần lượt kiểm tra:

1. Spring đã đăng ký bean listener chưa và event type có khớp không?
2. Event có được phát **khi transaction đang hoạt động** không?
3. `@Transactional` có thực sự được áp dụng qua Spring proxy không?
4. Event có bị chuyển sang thread khác **trước khi publish** không?
5. `fallbackExecution` đang bật hay tắt?
6. Listener đang chờ `OrderPlaced` hay `MessagingEvent` do cấu hình `publishPayload`?
7. Có tình huống rollback, lỗi commit hoặc test transaction chưa hoàn tất không?

## 13. Bài tập áp dụng

**Bài tập 1 — So sánh pha:** xây dựng bốn listener tương ứng `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Dùng `placeOrder(...)` và `placeOrderThenFail(...)` để ghi nhận callback nào chạy trong từng trường hợp. Giải thích vì sao `BEFORE_COMMIT` không phải thời điểm hợp lệ để gửi email chắc chắn thành công.

**Bài tập 2 — Cầu nối sau commit:** sửa ví dụ sao cho `CommittedOrderForwarder` gửi `Message<OrderPlaced>` vào một integration flow có transformer, router và outbound adapter HTTP. Đảm bảo flow không chạy khi transaction rollback.

**Bài tập 3 — Thread:** thay `DirectChannel` trước outbound publisher bằng `ExecutorChannel`. Theo dõi `TransactionSynchronizationManager.isActualTransactionActive()` tại thời điểm publisher phát event và giải thích kết quả. Sau đó phục hồi `DirectChannel` và chỉ chuyển async tại **kênh sau commit**.

**Bài tập 4 — Lưu audit:** ghi bản ghi `notification_audit` bằng `REQUIRES_NEW` sau commit; gây lỗi ở thao tác audit và quan sát vì sao bản ghi đơn hàng chính không bị rollback.

**Bài tập 5 — Outbox:** tạo bảng `outbox_events(event_id, aggregate_id, event_type, payload, created_at, published_at)`. Ghi event vào outbox cùng transaction ghi đơn hàng, dùng Spring Integration poller và adapter Kafka/JMS/AMQP để xuất bản. Mô tả chiến lược retry và xử lý trùng lặp theo `event_id`.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html).
- [Spring Framework API — TransactionPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html).
- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html).
