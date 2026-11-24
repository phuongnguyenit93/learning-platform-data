# Event multicaster và thread trong Spring Integration Event Adapter

## Mục tiêu bài học

Trong chương **Adapter sự kiện** của module **SPRING_INTEGRATION_ADAPTERS**, các thành phần Spring có thể trao đổi dữ liệu qua `ApplicationEventPublisher` và kết nối với luồng `MessageChannel` của Spring Integration. Khi đưa sự kiện từ hoặc vào một integration flow, **thread nào chạy listener** quyết định thời điểm xử lý, khả năng truyền exception, ngữ cảnh giao dịch và tốc độ hệ thống.

Sau bài học, bạn có thể:

- Giải thích `ApplicationEventMulticaster` làm gì và vì sao mặc định một Spring event thường được xử lý **đồng bộ**.
- Xác định thread của `ApplicationEventPublishingMessageHandler`, `ApplicationEventListeningMessageProducer`, `DirectChannel` và `ExecutorChannel`.
- Chọn ba cách xử lý bất đồng bộ: executor cho multicaster, `@Async` cho listener, hoặc `ExecutorChannel` cho một phần luồng tích hợp.
- Cấu hình executor có giới hạn, quan sát lỗi, bảo vệ ranh giới giao dịch và kiểm tra hành vi thực tế.

**Phạm vi:** Spring application events là cơ chế phát sự kiện **trong một Spring ApplicationContext**. Chúng có thể làm cầu nối trước hoặc sau adapter file, SFTP, HTTP, JMS, AMQP, Kafka hay cơ sở dữ liệu; riêng event multicaster không tự trở thành một message broker bền vững.

## 1. Event multicaster nằm ở đâu?

`ApplicationEventPublisher` là API mà code gọi để phát một Spring event:

~~~java
publisher.publishEvent(new StockReserved("RSV-001"));
~~~

Spring sử dụng một `ApplicationEventMulticaster` để tìm các `ApplicationListener` phù hợp và chuyển sự kiện tới từng listener. Với ứng dụng Spring Framework thông thường, implementation mặc định là `SimpleApplicationEventMulticaster`.

~~~mermaid
flowchart LR
    S["Integration flow / Service"] --> P["ApplicationEventPublisher"]
    P --> M["ApplicationEventMulticaster"]
    M --> A["@EventListener"]
    M --> I["ApplicationEventListeningMessageProducer"]
    I --> C["MessageChannel"]
    C --> H["Service Activator / Handler"]
~~~

Hai event adapter liên quan trực tiếp:

| Thành phần | Chiều dữ liệu | Vai trò của multicaster |
| --- | --- | --- |
| `ApplicationEventPublishingMessageHandler` | Spring Integration `Message<?>` → Spring event | Gọi `ApplicationEventPublisher`; multicaster phân phối event đến các listener |
| `ApplicationEventListeningMessageProducer` | Spring event → Spring Integration `Message<?>` | Được multicaster gọi như một listener, sau đó gửi message vào output channel |

Ở outbound handler, thuộc tính `publishPayload` ảnh hưởng đến **kiểu sự kiện**, nhưng tự nó không chuyển thread:

- `publishPayload=false` (mặc định): với payload chưa phải `ApplicationEvent`, handler phát `MessagingEvent` giữ message gốc.
- `publishPayload=true`: handler phát payload trực tiếp, ví dụ `StockReserved`; Spring có thể dùng `PayloadApplicationEvent` để biểu diễn POJO.
- Với payload vốn là `ApplicationEvent`, handler phát chính event đó.

Vì vậy khi thay đổi thread, trước tiên cần xác nhận listener nhận đúng **event type**. Sự kiện bị lọc bỏ sẽ không được xử lý, dù cấu hình executor đã đúng.

## 2. Mặc định: đồng bộ trên thread phát sự kiện

`SimpleApplicationEventMulticaster` sử dụng cơ chế đồng bộ mặc định: nó gọi listener trong thread của bên phát event. Nếu bên phát event đang chạy trên HTTP request thread, listener cũng chạy trong thread đó; nếu bên phát chạy trên poller thread hoặc worker thread, listener chạy trên thread tương ứng.

~~~mermaid
sequenceDiagram
    participant T as "Thread gọi publishEvent"
    participant P as ApplicationEventPublisher
    participant M as SimpleApplicationEventMulticaster
    participant L1 as Listener A
    participant L2 as Inbound Event Adapter
    participant C as DirectChannel
    participant H as Service Activator

    T->>P: publishEvent(event)
    P->>M: multicastEvent(event)
    M->>L1: onApplicationEvent(event)
    L1-->>M: return
    M->>L2: onApplicationEvent(event)
    L2->>C: send(message)
    C->>H: handle(message)
    H-->>C: return
    C-->>L2: return
    L2-->>M: return
    M-->>P: return
    P-->>T: return
~~~

Sơ đồ minh họa đường thực thi đồng bộ. Thứ tự listener A và adapter inbound thực tế còn phụ thuộc đăng ký/thứ tự listener, không nên mặc định listener A luôn chạy trước.

Trong trường hợp đồng bộ:

1. `publishEvent(...)` chỉ trả về sau khi các listener đồng bộ đã hoàn tất hoặc có exception làm dừng đường xử lý.
2. Một listener chậm có thể kéo dài thời gian phản hồi của HTTP controller, service hoặc integration flow đang phát event.
3. Exception từ listener có thể truyền ngược về bên phát event, trừ khi được xử lý bởi cấu hình ErrorHandler hoặc lớp bao quanh.
4. Các listener đồng bộ cùng đi qua thread hiện tại, nhưng **thứ tự thực thi không nên là hợp đồng nghiệp vụ**, trừ khi bạn cấu hình thứ tự và hiểu giới hạn của nó.

`@Order` có thể quy định thứ tự gọi các listener; đó không phải cơ chế bảo đảm hoàn tất theo thứ tự nếu về sau có thread bất đồng bộ.

## 3. Ví dụ hoàn chỉnh: lần theo thread qua hai event adapter

Ví dụ sử dụng Spring Boot, Spring Integration và Java 17+.

**Dependency Gradle:**

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

Hãy để Spring Boot quản lý phiên bản dependency tương thích, hoặc sử dụng BOM Spring Integration tương ứng nếu không dùng Spring Boot.

**Bước 1 — Payload nghiệp vụ.**

`StockReserved.java`:

~~~java
package com.example.stock;

public record StockReserved(String reservationId) {
}
~~~

**Bước 2 — Outbound adapter phát POJO làm Spring event, inbound adapter nhận lại event cùng loại.**

`StockEventConfig.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.integration.event.outbound.ApplicationEventPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class StockEventConfig {

    @Bean
    public MessageChannel outgoingStockEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel inboundStockEvents() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "outgoingStockEvents")
    public ApplicationEventPublishingMessageHandler outboundStockEvents() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }

    @Bean
    public ApplicationEventListeningMessageProducer inboundStockListener(
            @Qualifier("inboundStockEvents") MessageChannel outputChannel) {

        var adapter = new ApplicationEventListeningMessageProducer();
        adapter.setEventTypes(StockReserved.class);
        adapter.setOutputChannel(outputChannel);
        return adapter;
    }
}
~~~

**Lưu ý:** flow minh họa có hướng rõ ràng: `outgoingStockEvents → outbound event adapter → Spring event → inbound event adapter → inboundStockEvents`. Nó kết thúc ở consumer bên dưới. Không nối consumer quay lại `outgoingStockEvents`, vì điều đó có thể tạo vòng lặp phát sự kiện vô hạn.

**Bước 3 — Service gửi message vào integration flow.**

`StockCommandService.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class StockCommandService {

    private final MessageChannel outgoingStockEvents;

    public StockCommandService(
            @Qualifier("outgoingStockEvents") MessageChannel channel) {
        this.outgoingStockEvents = channel;
    }

    public void reserve(String reservationId) {
        System.out.println("SENDER: " + Thread.currentThread().getName());

        boolean sent = outgoingStockEvents.send(
                MessageBuilder.withPayload(
                        new StockReserved(reservationId)).build());

        if (!sent) {
            throw new IllegalStateException("Cannot send StockReserved");
        }
    }
}
~~~

**Bước 4 — Quan sát Spring listener và Spring Integration consumer.**

`StockEventObservers.java`:

~~~java
package com.example.stock;

import org.springframework.context.event.EventListener;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StockEventObservers {

    @EventListener
    public void onSpringEvent(StockReserved event) {
        System.out.printf(
                "SPRING: %s, id=%s%n",
                Thread.currentThread().getName(),
                event.reservationId());
    }

    @ServiceActivator(inputChannel = "inboundStockEvents")
    public void onIntegrationMessage(StockReserved payload) {
        System.out.printf(
                "INTEGRATION: %s, id=%s%n",
                Thread.currentThread().getName(),
                payload.reservationId());
    }
}
~~~

Gọi `stockCommandService.reserve("RSV-001")` từ một service hoặc controller. Với multicaster mặc định và cả hai channel là `DirectChannel`, ba nhãn `SENDER`, `SPRING` và `INTEGRATION` sẽ hiển thị **cùng tên thread**. Ví dụ nếu gọi trên HTTP request thread:

~~~text
SENDER: http-nio-8080-exec-1
SPRING: http-nio-8080-exec-1, id=RSV-001
INTEGRATION: http-nio-8080-exec-1, id=RSV-001
~~~

Đây là kết quả minh họa; tên thread cụ thể và thứ tự hai dòng listener có thể khác. `DirectChannel` chuyển message đến subscriber ngay trong thread gọi `send(...)`, trừ khi đã có một ranh giới bất đồng bộ **trước** channel.

## 4. Ba cách chuyển sang xử lý bất đồng bộ

Không phải mọi nhu cầu bất đồng bộ đều nên cấu hình ở cùng một tầng.

| Cách | Phạm vi ảnh hưởng | Thread đổi tại đâu? | Dùng khi |
| --- | --- | --- | --- |
| Gắn `TaskExecutor` cho `applicationEventMulticaster` | Nhiều Spring application listener trong context | Multicaster lập lịch gọi listener | Muốn các listener đủ điều kiện được dispatch qua executor chung |
| `@Async` trên một phương thức `@EventListener` | Chỉ listener được đánh dấu | Khi Spring chạy phương thức listener | Một consumer độc lập, chậm như gửi email hoặc ghi nhận thống kê |
| `ExecutorChannel` sau inbound event adapter | Một đoạn của integration flow | Khi message được gửi vào channel có executor | Muốn kiểm soát tải và lỗi ở pipeline Spring Integration |

Có thể kết hợp nhiều tầng, nhưng khi đó mỗi tầng có thể tạo thêm một lần chuyển thread. Cần xác định rõ ai sở hữu executor, cách báo lỗi và giới hạn tải.

### Cách A — Dùng executor cho event multicaster

Spring tìm bean có tên **`applicationEventMulticaster`** để sử dụng thay cho multicaster mặc định. Có thể cấu hình `SimpleApplicationEventMulticaster` với một executor có giới hạn.

`SpringEventMulticasterConfig.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class SpringEventMulticasterConfig {

    @Bean("springEventExecutor")
    public ThreadPoolTaskExecutor springEventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("spring-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean("applicationEventMulticaster")
    public ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("springEventExecutor") TaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error -> {
            System.err.println(
                    "Application event listener failed: " + error);
        });
        return multicaster;
    }
}
~~~

Spring quản lý lifecycle cho `ThreadPoolTaskExecutor` bean, bao gồm khởi tạo và đóng executor. Trong hệ thống thật, thay `System.err` bằng logger và metric tập trung; chính sách `ErrorHandler` ở trên chỉ ghi nhận lỗi rồi cho phép listener task kết thúc, **không tự retry**.

Sau cấu hình này, Spring listener và inbound event adapter **đủ điều kiện hỗ trợ async** được lập lịch trên các thread như `spring-event-1`, `spring-event-2`. Do inbound adapter sau đó gửi message đến `DirectChannel`, consumer trong flow có thể chạy trên **cùng worker thread với inbound adapter**, không còn là thread gọi `reserve(...)`.

**Hai giới hạn cần nắm:**

- Thay bean `applicationEventMulticaster` tác động đến cơ chế phân phối event của **toàn Spring ApplicationContext**, bao gồm cả listener không liên quan tới flow. Cần kiểm tra tác động lên các listener khác của ứng dụng.
- Từ Spring Framework 6.1, một số listener báo không hỗ trợ thực thi async qua `supportsAsyncExecution()` và phải chạy trong thread phát event; ví dụ điển hình là listener phụ thuộc ngữ cảnh transaction. Do đó không thể khẳng định **mọi** listener sẽ chuyển sang executor chỉ vì đã cấu hình `setTaskExecutor(...)`.

Nếu một worker đang xử lý lâu hoặc queue bị đầy, việc dispatch sẽ bị trễ hoặc executor từ chối tác vụ. Giới hạn pool/queue là một phần của contract vận hành, cần đo đạc theo tải thực tế.

### Cách B — Bất đồng bộ riêng một @EventListener

Nếu chỉ một listener có tác vụ lâu (ví dụ gửi email), dùng `@Async` sẽ giữ nguyên cấu hình multicaster chung.

`SelectiveAsyncConfig.java`:

~~~java
package com.example.stock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class SelectiveAsyncConfig {

    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

`StockNotificationListener.java`:

~~~java
package com.example.stock;

import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class StockNotificationListener {

    @Async("notificationExecutor")
    @EventListener
    public void sendNotification(StockReserved event) {
        System.out.printf(
                "NOTIFY: %s, id=%s%n",
                Thread.currentThread().getName(),
                event.reservationId());

        // Gửi notification bằng một client có timeout và retry hợp lý.
    }
}
~~~

Với multicaster mặc định:

- `sendNotification(...)` chạy trên thread `notification-*`.
- Các listener khác, bao gồm inbound event adapter nếu không có cấu hình khác, vẫn có thể chạy trên thread phát event.
- Exception từ phương thức `void @Async` không tự quay về `publishEvent(...)`. Cần cấu hình `AsyncUncaughtExceptionHandler`, logging/monitoring hoặc tự xử lý lỗi tại listener.

Không dùng giá trị return của một phương thức `@Async @EventListener` làm phương tiện phát event tiếp theo. Nếu cần phát event mới, hãy tiêm `ApplicationEventPublisher` và gọi `publishEvent(...)` một cách tường minh sau khi xử lý.

### Cách C — Bất đồng bộ tại MessageChannel trong Spring Integration

Nếu mục tiêu là tách **phần xử lý integration flow** khỏi thread nhận Spring event, thay `DirectChannel` của inbound adapter bằng `ExecutorChannel`.

~~~java
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean
public MessageChannel inboundStockEvents(
        @Qualifier("integrationWorkerExecutor") Executor executor) {
    return new ExecutorChannel(executor);
}
~~~

Trong ví dụ, cần định nghĩa một bean `integrationWorkerExecutor` (chẳng hạn `ThreadPoolTaskExecutor`) với cấu hình giới hạn tải tương tự ở cách A hoặc B. Đoạn bean này **thay thế** bean `inboundStockEvents()` trả về `DirectChannel` trong mục 3; không để hai bean trùng tên.

Khi Spring multicaster vẫn đồng bộ:

~~~text
SENDER [thread A]
    -> outbound adapter
    -> multicaster (thread A)
    -> inbound adapter (thread A)
    -> ExecutorChannel.send(...), lên lịch cho executor
                                          |
                                          v
                              Service Activator [thread B]
~~~

`send(...)` có thể trả về sau khi lịch xử lý được chấp nhận trong executor; điều đó **không có nghĩa** service activator đã hoàn tất. Nếu executor bão hòa, việc gửi cũng có thể bị từ chối theo chính sách của executor.

Cách C giữ quyền quyết định async ở ranh giới integration flow, thuận tiện khi chỉ một pipeline cần điều chỉnh concurrency, error channel và mức độ xử lý song song.

## 5. Chọn thread đúng cho inbound và outbound

Hãy phân tích **đường đi của thread**, vì cùng một sự kiện có thể trải qua nhiều tầng:

| Điểm bắt đầu | Multicaster | Channel | Thread thường chạy handler cuối |
| --- | --- | --- | --- |
| Service gọi `publishEvent` | Mặc định đồng bộ | `DirectChannel` | Thread service gọi `publishEvent` |
| Service gọi `publishEvent` | Executor async | `DirectChannel` | Worker thread của multicaster, nếu listener hỗ trợ async |
| Service gọi `publishEvent` | Mặc định đồng bộ | `ExecutorChannel` | Worker thread của integration executor |
| Service gọi `publishEvent` | Executor async | `ExecutorChannel` | Worker thread của integration executor, sau khi multicaster dispatch |
| Integration service gửi message đến outbound handler bằng `DirectChannel` | Mặc định đồng bộ | Không có inbound adapter | Spring listener đồng bộ chạy trong thread gửi message |
| Integration service gửi message đến outbound handler bằng `ExecutorChannel` | Mặc định đồng bộ | Không có inbound adapter | Spring listener đồng bộ chạy trong worker thread của `ExecutorChannel` |

Một event có thể có **nhiều Spring listener**. Với multicaster dùng executor, chúng có thể chạy trên các worker khác nhau và hoàn tất ở những thời điểm khác nhau.

**Quy tắc thực hành:** trace thread tại ba điểm: trước khi gọi `publishEvent`, ngay trong Spring listener/inbound adapter, và trong service activator. Chỉ nhìn tên thread ở nơi phát event sẽ không xác định được cách downstream chạy.

## 6. Exception đi đâu khi đổi thread?

Ranh giới bất đồng bộ thường đồng nghĩa với thay đổi nơi exception xuất hiện.

~~~mermaid
flowchart TD
    A["Có exception trong listener / handler?"] --> B{"Listener chạy đồng bộ?"}
    B -->|Có| C["Exception có thể truyền về publishEvent / send"]
    B -->|Không| D["Exception ở worker thread"]
    D --> E["ErrorHandler / async handler / error channel"]
    E --> F["Ghi log, metric, retry hoặc khắc phục theo thiết kế"]
~~~

| Nơi lỗi xảy ra | Có thể quan sát ở đâu | Ghi chú |
| --- | --- | --- |
| Spring `@EventListener` đồng bộ | Caller của `publishEvent` / outbound handler | Trừ khi multicaster có `ErrorHandler` chặn lỗi |
| Listener do multicaster executor chạy | Thread thực thi listener; `ErrorHandler` nếu cấu hình | Caller đã có thể nhận kết quả trước khi listener hoàn tất |
| `@Async @EventListener` với return `void` | `AsyncUncaughtExceptionHandler` hoặc xử lý trong listener | Không tự truyền ngược về caller |
| Service activator trên `DirectChannel` | Luồng gọi `send(...)` | Có thể truyền về inbound adapter/multicaster |
| Service activator trên `ExecutorChannel` | Worker thread và cơ chế lỗi Spring Integration phù hợp | Cần cấu hình/kiểm chứng `errorChannel`, logging hoặc recovery theo topology |

**Đặc biệt chú ý:** câu lệnh `channel.send(message) == true` có thể chỉ xác nhận đã chuyển hoặc chấp nhận message ở ranh giới channel, không xác nhận tác vụ bất đồng bộ downstream đã hoàn tất hay side effect (gửi email/ghi DB) đã thành công.

Khi xử lý lỗi, hãy phân biệt:

- **Lỗi nghiệp vụ có thể thử lại**, ví dụ HTTP 503 hoặc timeout đến service ngoài.
- **Lỗi dữ liệu không hợp lệ**, ví dụ event thiếu `reservationId`, nên được ghi nhận rõ và xử lý theo chính sách poison message.
- **Lỗi executor bão hòa**, có thể xuất hiện ngay ở thời điểm lập lịch, cần kiểm soát queue, từ chối và backpressure.

Spring application events không tự mang cơ chế durable retry, dead-letter queue hay lưu lại event khi tiến trình dừng. Nếu yêu cầu khôi phục xuyên restart hoặc giao hàng giữa nhiều service, hãy cân nhắc broker JMS/AMQP/Kafka cùng outbox hoặc cơ chế lưu trữ thích hợp.

## 7. ThreadLocal, MDC và transaction context

Chuyển thread không chỉ ảnh hưởng hiệu năng; nó còn ảnh hưởng **ngữ cảnh** gắn với thread hiện tại.

### Transaction

Transaction thông thường của Spring gắn với thread. Khi một event được publish bên trong phương thức `@Transactional`:

- Listener **đồng bộ** có thể tham gia cùng transaction của thread đó (tùy thao tác và cấu hình transaction).
- Listener chạy ở **executor thread** không tự thừa hưởng transaction context của thread phát event.
- Nếu consumer cần chạy sau commit, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` trong trường hợp sự kiện được phát khi transaction phù hợp đang hoạt động.

Ví dụ:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class StockAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onAfterCommit(StockReserved event) {
        System.out.println("Committed reservation: " + event.reservationId());
    }
}
~~~

`@TransactionalEventListener` mặc định **không gọi listener nếu không có transaction**, trừ khi bật `fallbackExecution=true`. Với Spring Framework 6.1+, transactional listener thông thường không hỗ trợ async dispatch qua multicaster executor; nó cần thread phát event để ghi nhận đúng transaction synchronization. Muốn tách công việc sau commit sang worker khác, hãy cân nhắc **phát công việc** từ listener sau commit bằng cơ chế có lifecycle và xử lý lỗi rõ ràng.

`AFTER_COMMIT` bảo đảm thời điểm callback theo transaction trong ứng dụng khi quá trình hoạt động bình thường; nó **không bảo đảm durable delivery** nếu tiến trình dừng ngay sau khi commit. Với nghiệp vụ quan trọng, hãy dùng transactional outbox hoặc chiến lược lưu event phù hợp.

### Trace, security context và locale

`MDC`, `SecurityContext`, locale và nhiều loại context dùng `ThreadLocal`. Executor không mặc định chuyển tất cả giá trị ấy sang worker thread. Vì vậy:

1. Đặt `correlationId`/`traceId` cần thiết vào **payload hoặc message headers** theo contract, thay vì chỉ lưu trong `ThreadLocal`.
2. Nếu cần propagation qua executor, cấu hình `TaskDecorator` hoặc công cụ context propagation tương ứng, kèm thao tác dọn ngữ cảnh sau khi task kết thúc.
3. Không giả định Spring event thông thường chứa toàn bộ headers của Spring Integration. Nếu outbound adapter dùng `publishPayload=true`, các headers không tự đi cùng POJO.

Một dấu hiệu của lỗi propagation là log ở thread phát có `traceId`, nhưng log ở listener async lại không có. Đây là lỗi ngữ cảnh thực thi; nó khác với việc event bị lọc sai type hoặc mất payload.

## 8. Thứ tự, concurrency và giới hạn tải

**Đồng bộ không tự đồng nghĩa luôn tuần tự trên toàn ứng dụng.** Một publisher đang gọi đồng bộ có thể xử lý các listener trong một thread, nhưng nhiều publisher từ các request thread khác nhau vẫn có thể chạy đồng thời.

Khi bật executor:

- **Thứ tự:** `@Order` có thể quyết định thứ tự **dispatch** listener, nhưng không bảo đảm thứ tự **hoàn tất** khi các task được chạy song song.
- **Concurrency:** một listener có thể được gọi đồng thời cho nhiều event. Các biến mutable dùng chung phải an toàn thread; tránh dùng `ArrayList`/`HashMap` không đồng bộ làm bộ nhớ trạng thái chung.
- **Queue:** cấu hình queue quá lớn có thể che giấu nghẽn và tăng độ trễ/bộ nhớ. Queue quá nhỏ có thể dẫn đến `TaskRejectedException` nếu producer nhanh hơn consumer.
- **Idempotency:** sự kiện bị gửi lại từ tầng khác hoặc retry thủ công có thể khiến side effect thực hiện nhiều lần. Thiết kế business handler có khóa idempotency khi cần.
- **Shutdown:** khi ứng dụng dừng, cần chính sách chờ tác vụ, timeout và xử lý công việc chưa hoàn thành. Cấu hình `waitForTasksToCompleteOnShutdown` chỉ hỗ trợ graceful shutdown trong phạm vi process; nó không thay thế cơ chế lưu message bền vững.

Ví dụ một listener gửi email mất 2 giây; nếu mỗi giây nhận 20 event mà chỉ có hai worker, số lượng tác vụ chờ có thể tăng nhanh. Tăng số thread mà không giới hạn queue, timeout và tốc độ nguồn phát chỉ chuyển điểm nghẽn từ caller sang executor.

## 9. Kiểm thử hành vi thread một cách đáng tin cậy

Không nên dùng mỗi `Thread.sleep(...)` để “chứng minh” đã chạy async; thời gian scheduler thay đổi giữa các môi trường. Dùng đồng bộ hóa như `CountDownLatch` hoặc `CompletableFuture` để chờ sự kiện cần quan sát.

Ví dụ một listener kiểm thử lưu tên thread:

~~~java
package com.example.stock;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StockEventProbe {

    private final CountDownLatch observed = new CountDownLatch(1);
    private final AtomicReference<String> listenerThread =
            new AtomicReference<>();

    @EventListener
    public void onEvent(StockReserved event) {
        if ("RSV-TEST".equals(event.reservationId())) {
            listenerThread.set(Thread.currentThread().getName());
            observed.countDown();
        }
    }

    public CountDownLatch observed() {
        return observed;
    }

    public String listenerThread() {
        return listenerThread.get();
    }
}
~~~

Trong test sử dụng một Spring context mới cho mỗi kịch bản:

~~~java
String publisherThread = Thread.currentThread().getName();
publisher.publishEvent(new StockReserved("RSV-TEST"));

assertTrue(probe.observed().await(5, TimeUnit.SECONDS));
assertNotNull(probe.listenerThread());

// Chỉ ở kịch bản có cấu hình multicaster executor:
assertTrue(probe.listenerThread().startsWith("spring-event-"));
~~~

Các dòng này là **phần thân** một phương thức test, với `publisher` và `probe` đã được inject; import `TimeUnit` và các assert của JUnit theo dự án. `CountDownLatch` chỉ sử dụng một lần nên mỗi test nên tạo context/probe mới hoặc thiết kế probe có thể reset an toàn.

Khi kiểm thử, nên tách:

1. **Case đồng bộ mặc định:** xác minh listener được gọi trong thread caller, không cần chờ `sleep`.
2. **Case async multicaster:** xác minh listener được gọi trên `spring-event-*`; dùng latch chờ kết quả.
3. **Case `@Async`:** xác minh chỉ listener được đánh dấu dùng `notification-*`.
4. **Case `ExecutorChannel`:** xác minh Spring event inbound có thể ở thread phát, trong khi service activator nằm trên integration worker.
5. **Case lỗi:** cố tình ném exception ở một listener; kiểm tra caller nhận exception trong sync nhưng việc ghi nhận lỗi đi qua async handler ở cấu hình tương ứng.
6. **Case transaction:** phát trong transaction, kiểm tra thời điểm listener `AFTER_COMMIT` và hành vi rollback.

Trong kiểm thử async, đừng assert một **thứ tự log cố định** giữa các listener độc lập. Assert event ID, payload, headers cần thiết, số lần xử lý và điều kiện hoàn thành tương ứng với yêu cầu nghiệp vụ.

## 10. Checklist chẩn đoán khi event xử lý chậm hoặc sai thread

| Dấu hiệu | Kiểm tra trước tiên | Hướng xử lý |
| --- | --- | --- |
| HTTP request chậm sau khi phát event | Listener đồng bộ có đang thực hiện I/O lâu? | Tách consumer phù hợp sang `@Async` hoặc `ExecutorChannel` |
| Đã cấu hình multicaster executor nhưng một listener vẫn chạy trên caller thread | Listener có hỗ trợ async dispatch không, nhất là transactional listener? | Kiểm tra `supportsAsyncExecution()` và contract của listener |
| Event được phát nhưng inbound adapter không chạy | `eventTypes` có khớp lớp Spring event/POJO không? | Kiểm tra runtime type, `publishPayload`, bean registration |
| Listener async lỗi nhưng caller không thấy exception | Có `ErrorHandler` / `AsyncUncaughtExceptionHandler` hoặc integration error flow? | Bổ sung logging, metric và recovery |
| Log của worker thiếu `traceId` | Ngữ cảnh chỉ lưu `ThreadLocal`? | Mang metadata trong event/message và cấu hình context propagation |
| Event mất thứ tự | Executor có nhiều worker hoặc nhiều publisher song song? | Thiết kế ordering theo khóa, serialization hoặc cơ chế có bảo đảm thứ tự phù hợp |
| Executor dùng nhiều bộ nhớ | Queue không giới hạn hoặc consumer chậm? | Giới hạn queue, concurrency; bổ sung backpressure và metric |
| Event được xử lý nhiều lần liên tiếp | Flow inbound có phát lại event ra outbound cùng loại? | Kiểm tra vòng lặp và tách chiều luồng |

Để quan sát thực tế, ghi nhận `eventId`, `eventType`, `threadName`, thời điểm publish, thời điểm listener bắt đầu/kết thúc, thời gian chờ queue, số tác vụ bị từ chối và kết quả xử lý. Không nên chỉ dựa vào log “publish thành công”.

## 11. Bài tập áp dụng

**Bài tập 1 — Đo thread:** dùng ví dụ `StockReserved` ở mục 3. Phát 10 event và ghi thread ở service, `@EventListener` và service activator. Giải thích vì sao cả ba cùng tên thread khi dùng multicaster mặc định và `DirectChannel`.

**Bài tập 2 — Chuyển một điểm:** thay `inboundStockEvents` bằng `ExecutorChannel`. Dùng latch chờ các event hoàn thành; so sánh số worker và thứ tự hoàn tất. Không giả định 10 event sẽ kết thúc theo đúng thứ tự phát.

**Bài tập 3 — So sánh chiến lược:** thử một lần chỉ bật `@Async` trên listener gửi thông báo, một lần chỉ bật executor cho multicaster. Dự đoán và đối chiếu thread của inbound adapter; mô tả hệ quả nếu ứng dụng còn nhiều Spring listeners khác.

**Bài tập 4 — Lỗi và giao dịch:** để một listener ném `IllegalStateException`. Quan sát đường đi exception ở sync và async. Sau đó phát event trong phương thức `@Transactional` và thử listener `AFTER_COMMIT` khi commit/rollback; giải thích vì sao cần outbox nếu sự kiện ảnh hưởng đến service ngoài.

**Bài tập 5 — Quá tải:** giới hạn executor còn một worker và queue nhỏ, làm consumer tốn thời gian xử lý; tăng tốc phát event. Ghi nhận các tác vụ bị từ chối và xác định chính sách backpressure/retry có thể chấp nhận được.

## Tài liệu tham khảo

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
- [Spring Framework — Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-async).
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html).
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html).
