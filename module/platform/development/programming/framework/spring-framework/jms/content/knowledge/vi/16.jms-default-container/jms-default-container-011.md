# Start, stop, shutdown và message đang xử lý trong DefaultMessageListenerContainer

> **Module:** Spring Framework – JMS  
> **Nhóm:** Default container  
> **Trọng tâm:** Vòng đời `DefaultMessageListenerContainer`, khác biệt giữa `start()`, `stop()`, `shutdown()` và trách nhiệm của ứng dụng/broker đối với message **đang được xử lý (in-flight)** khi dừng listener.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả cách `DefaultMessageListenerContainer` (DMLC) tạo và điều phối JMS consumer, `Session` và các tác vụ polling.
2. Phân biệt chính xác **initialized/active**, **running/stopped** và **shut down/destroyed**; biết khi nào được `start()` lại và khi nào không nên.
3. Điều khiển `@JmsListener` theo endpoint ID qua `JmsListenerEndpointRegistry`, đồng thời hiểu registry chỉ quản lý **các container trong application context hiện tại**.
4. Giải thích một message đã giao cho listener trước khi `stop` có thể đang chạy, hoàn thành/commit, lỗi/rollback hoặc được broker redeliver tùy trạng thái và cấu hình.
5. Dùng `stop(Runnable)` để nhận callback khi **listener processing thực sự dừng** trong DMLC, tránh xem yêu cầu stop là dấu mốc mọi in-flight work đã hoàn thành.
6. Hiểu `setAcceptMessagesWhileStopping(false/true)`, receive timeout, số consumer và tác động tới redelivery, latency dừng và việc vẫn nhận message mới trong giai đoạn stopping.
7. Cấu hình `setSessionTransacted(true)` và phân biệt với `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, business idempotency và DB transaction.
8. Lập kế hoạch shutdown graceful trong Spring/Spring Boot và môi trường orchestration: ngừng tiêu thụ, chờ tác vụ đang chạy, ngân sách thời gian, kết nối broker, kill deadline.
9. Phân tích hậu quả với Queue, Topic non-durable, durable/shared subscription khi container stop/restart.
10. Kiểm thử đúng lifecycle, in-flight, broker redelivery và bảo toàn dữ liệu mà không hứa rằng một setter Spring đơn lẻ giải quyết mọi failure.

## 1. “Default container” là gì?

Trong Spring JMS, `DefaultMessageListenerContainer` là implementation thường dùng cho asynchronous JMS consumption. Nó chạy một hoặc nhiều **consumer invoker tasks**; mỗi task gọi `MessageConsumer.receive(...)` theo chu kỳ và chuyển message nhận được đến listener. Nó hỗ trợ tự khôi phục khi broker mất kết nối tạm thời và có thể tăng/giảm số consumers trong giới hạn đã cấu hình.

Khi dùng `@JmsListener`, Spring thường tạo DMLC qua:

```text
org.springframework.jms.config.DefaultJmsListenerContainerFactory
```

Đây là **factory tạo container**, không phải chính listener container đang chạy. Một factory có thể tạo nhiều containers cho nhiều annotated endpoints.

```text
Spring ApplicationContext
  |
  +-- @EnableJms
  |     |
  |     +-- @JmsListener(id="billing.invoice.v1", ...)
  |                |
  |                v
  |         Listener endpoint
  |                |
  |                v
  |   DefaultJmsListenerContainerFactory
  |                |
  |                v
  |      DefaultMessageListenerContainer  <--- Lifecycle start/stop
  |                |
  |          JMS Session(s)
  |          JMS Consumer(s)
  |                |
  +-- JmsListenerEndpointRegistry
       ("billing.invoice.v1" -> container)
                         |
                         v
                  Broker Queue/Topic
```

Điểm cốt lõi là **container chịu trách nhiệm polling + lifecycle**, còn **JMS provider chịu trách nhiệm message delivery, ACK, transaction, persistence, redelivery theo hợp đồng và policy**. Business method quyết định xử lý thành công/không thành công ở mức nghiệp vụ.

### 1.1. DefaultMessageListenerContainer khác SimpleMessageListenerContainer

| Đặc điểm | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Cách nhận | Vòng lặp `MessageConsumer.receive()` trong invoker tasks | JMS asynchronous `MessageConsumer.setMessageListener(...)` |
| Dynamic scaling consumers | Có cấu hình `concurrentConsumers` / `maxConcurrentConsumers` | Không cùng mô hình dynamic polling |
| Recovery khi broker tạm unavailable | Có cơ chế self-recovery/re-establish | Hạn chế hơn, phụ thuộc provider và container |
| Dừng/khởi động lại | Có cơ chế lifecycle và `stop(Runnable)` riêng được tài liệu hóa | Phải kiểm tra subclass semantics |
| Giao dịch | Hỗ trợ local transacted session hoặc external transaction manager | Hỗ trợ local semantics nhưng không giống cơ chế polling/XA của DMLC |
| AUTO_ACKNOWLEDGE mặc định | Có thể ACK **trước listener execution**, không redeliver khi method ném lỗi | Timing khác; không suy đồng nhất |

Bài này tập trung **DMLC**, vì đó là ý nghĩa của đề bài "Default container". Không suy mọi hành vi được mô tả thành quy luật của tất cả JMS listener container implementations.

### 1.2. Ba trạng thái cần tách

- `isActive()` ở `AbstractJmsListeningContainer` cho biết container đã được initialize nhưng **chưa shutdown**. Nó không bảo đảm đang tiêu thụ.
- `isRunning()` cho biết container đang trong trạng thái **started, chưa stopped**. Nó không bảo đảm broker kết nối khỏe hoặc handler đã hoàn tất message.
- `shutdown()`/`destroy()` giải phóng lifecycle resources; đây là **kết thúc vòng đời container** theo normal destruction path, không phải cách pause thông thường.

Một container có thể **active=true, running=false** sau `stop()`. Chính trạng thái này cho phép `start()` lại mà không cần tạo container mới. Ngược lại, sau `shutdown()` không nên dùng cùng object như một pause/resume handle.

## 2. Mô hình vòng đời: initialize → start → stop → restart hoặc shutdown

Sơ đồ khái niệm:

```text
     create / configure
             |
             v
        INITIALIZED
        active = true
             |
       start() / auto-start
             v
          RUNNING
         polls / receives
           |      \
       stop()       \ application context closing
           |         \
           v          v
         STOPPING ---> SHUTDOWN / DESTROY
           |
           | wait for processing / callbacks as applicable
           v
          STOPPED
      active may be true
           |
       start() again
           |
           +-----------------> RUNNING

   STOPPED -- shutdown()/destroy() --> DESTROYED
```

Đây là **mô hình học tập**, không phải enum state công khai của Spring. DMLC không có API `getState()` trả đúng các tên trên. Các sự kiện stop, callback, receive timeout, transaction completion và connection cleanup có thể không hoàn thành đồng thời.

### 2.1. Bảng hành động và ý nghĩa

| Hành động | Ý định | Nhận message mới? | In-flight có bị xóa ngay? | Có thể start lại cùng container? |
| --- | --- | --- | --- | --- |
| `initialize()` | Chuẩn bị tài nguyên & invokers | Tùy auto-start/lifecycle tiếp theo | Chưa có processing bình thường | Có theo lifecycle |
| `start()` | Bắt đầu/tiếp tục tiêu thụ | Có khi broker sẵn sàng | Không liên quan trực tiếp | Đang running |
| `stop()` | Ngừng listener hoạt động để có thể restart | Ngừng nhận theo tiến trình stopping; có race | **Không được giả định** | **Có** khi active |
| `stop(Runnable)` | Yêu cầu dừng và báo khi processing thực sự dừng | Theo stop semantics | Callback đến sau processing stop theo DMLC | Có |
| `shutdown()` | Đóng container và giải phóng JMS resources | Không | Đợi/đóng theo implementation; có deadline/failure ngoài JVM | **Không xem là pause/resume** |
| `destroy()` | Spring bean destruction path, gọi shutdown | Không | Phụ thuộc shutdown path | Không |
| JVM `SIGKILL` / power loss | Hủy process ngoài kiểm soát Spring | Không từ process chết | Có thể bị cắt ngang | Cần process mới |

**Quan trọng:** "Container stopped" và "message đã ACK/commit thành công" là hai sự kiện khác nhau. Một callback chỉ cho biết trạng thái listener processing, không phải toàn bộ DB/JMS/broker/workflow đã đạt exactly-once.

### 2.2. Vì sao cần hai cờ active/running?

Giả sử một listener cần tạm ngưng để bảo trì backend:

1. Container đã initialize: `active=true`.
2. Running: `active=true`, `running=true`.
3. Operator gọi `stop()`: container ngừng vòng nhận theo lifecycle, nhưng chưa hủy toàn bộ cấu hình/resources.
4. Sau bảo trì, `start()`: container lại nhận từ destination, có thể dùng kết nối đã cache hoặc khôi phục theo provider.

Nếu cố gọi `shutdown()` thay `stop()`, bạn đang yêu cầu **đóng** container; muốn quay lại hoạt động thường cần tạo container mới qua Spring context/factory. Đừng nhầm `shutdown()` với một "stop mạnh hơn để resume sau".

## 3. Startup: autoStartup, factory và trạng thái sẵn sàng

Trong Spring Framework, DMLC implements `SmartLifecycle`. Mặc định auto-start được bật. Với annotated endpoints, factory thường quyết định container có tự start khi ApplicationContext refresh hay không.

### 3.1. Cấu hình Spring JMS Java 17+

**File `BillingJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BillingJmsConfiguration {

    @Bean("billingListenerFactory")
    public DefaultJmsListenerContainerFactory billingListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setPubSubDomain(false);    // Queue
        factory.setSessionTransacted(true); // Local JMS transaction
        factory.setConcurrency("2-4");
        factory.setReceiveTimeout(1_000L);

        factory.setAutoStartup(true);
        return factory;
    }
}
```

Điều kiện chạy:

- Spring Framework 6.x/7.x, Jakarta Messaging provider tương thích, Java 17+.
- Dependency `spring-jms`, Spring Context và broker thực.
- ConnectionFactory được cấu hình trước, queue/ACL đúng.
- Các imports và class Spring/JMS nằm trong **project Spring**, không phải ví dụ độc lập chạy bằng JDK.

`setReceiveTimeout(1_000L)` nghĩa một lệnh `receive` chờ tối đa khoảng một giây nếu chưa có message, **không** phải timeout của handler chạy một giây và không phải shutdown grace period toàn hệ thống.

`setConcurrency("2-4")` mô tả từ hai đến bốn concurrent consumers theo DMLC, **không** bảo đảm có đúng bốn thread lúc nào cũng làm việc hoặc mọi message được phân đều 25% mỗi consumer.

### 3.2. Handler với ID rõ ràng

**File `InvoiceWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public final class InvoiceWorker {

    private final InvoiceService service;

    public InvoiceWorker(InvoiceService service) {
        this.service = service;
    }

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs",
            containerFactory = "billingListenerFactory")
    public void handle(String invoiceId) {
        service.process(invoiceId);
    }
}
```

`InvoiceService` là service nghiệp vụ do project cung cấp; cần triển khai thật, có retry/idempotency thích hợp. Method này được Spring gọi ở consumer worker thread khi message đủ điều kiện và conversion thành công. Một endpoint ID duy nhất **không đồng nghĩa** một consumer thread; container có thể có nhiều sessions/concurrent listeners.

### 3.3. Bắt đầu thủ công bằng autoStartup=false

Nếu cần chỉ mở consumer sau khi database migration, external dependency hoặc warm-up xong:

```java
factory.setAutoStartup(false);
```

Spring vẫn **đăng ký container** khi context khởi động, nhưng không tự start consumer theo setting. Có thể start container bằng `JmsListenerEndpointRegistry.getListenerContainer(id).start()` sau điều kiện sẵn sàng.

**Cẩn trọng:** Việc gọi `registry.start()` trên toàn registry là tín hiệu start toàn bộ managed listeners, có thể không phù hợp với chính sách “manual-start” cho một endpoint. Dùng ID và scope rõ nếu chỉ muốn start một container.

### 3.4. isRunning không phải health probe đầy đủ

`isRunning() == true` chỉ xác nhận Spring lifecycle được start, không chứng minh:

- Broker hiện reachable và consumer đã register thành công.
- Queue/topic name và quyền receive đúng.
- Có ít nhất một active consumer.
- Handler đang xử lý thông điệp với latency trong SLO.
- Message không nằm chờ do selector mismatch/DB slow.
- Kết nối không nằm trong recovery loop.

Khi cần trạng thái readiness cho một JMS consumer, kết hợp container state với broker connection/consumer metrics và lịch sử **business processing success**.

## 4. stop(): ngừng nhận thêm, không bấm “hủy” method đang chạy

Một điểm cần nhớ:

> `stop()` là **lifecycle stop**, không phải `Thread.stop()`, không tự interrupt mọi handler hoặc tự rollback mọi transaction ngay lập tức.

Giả sử đang có `M1` được DMLC nhận, code handler gọi database mất 8 giây; lúc giây thứ 3, operator gọi stop:

```text
t=0s    DMLC receives M1, starts handler
t=3s    operator requests stop
t=4s    M1 still inside handler / DB call
t=8s    handler may finish
t≈8s+   JMS session commits (if successful & transacted)
later   stop completion may be signalled
```

Đây là **timeline minh họa**, không hứa mọi handler luôn hoàn thành hoặc callback luôn trễ 5 giây: tùy provider, stop semantics, request timeout, kết nối và thời hạn process.

### 4.1. Ba loại message tại lúc stop

| Trạng thái message | Điều gì xảy ra khi stop? |
| --- | --- |
| **Ready/pending trong broker**, chưa giao consumer | Thường vẫn chờ trong queue theo retention/TTL; provider có thể giao replica khác |
| **Đã receive, đang trong handler** | Có thể tiếp tục thực thi, commit nếu thành công; nếu lỗi/crash/rollback có thể redeliver |
| **Đã receive nhưng chưa được dispatch tới handler lúc stop** | Chịu `acceptMessagesWhileStopping`/transaction/provider; có thể reject/rollback hoặc xử lý |
| **Đã ACK/commit** | JMS transport coi lượt nhận thành công; stop không đảo ngược ACK/commit |
| **Broker-delivered/prefetched nhưng chưa execute** | Cần xem broker/cache/prefetch; đừng suy tất cả đã chạy handler |
| **Mới publish sau stop** | Queue vẫn nhận từ producer, nhưng local stopped listener không chủ động lấy; replicas khác có thể lấy |

**Chỉ xem tổng queue depth** không biết message ở ready, in-flight, đã commit hay đang cached/prefetched. Kết hợp broker counters và ứng dụng.

### 4.2. Stop trên một replica không phải stop toàn cluster

`JmsListenerEndpointRegistry` là bean bên trong **một ApplicationContext**. Hai pods cùng nghe `billing.invoice.jobs`:

```text
Pod A: registry A -> endpoint billing.invoice.worker.v1 -> Consumer A
Pod B: registry B -> endpoint billing.invoice.worker.v1 -> Consumer B
                                         |
                                         v
                                  Same Queue
```

Gọi `stop()` trong Pod A không làm Pod B stop. B có thể xử lý nhiều message hơn vì A đã thôi nhận.

Nếu maintenance yêu cầu **không một replica nào** tiêu thụ, phải điều phối toàn deployment hoặc broker/destination routing; không trông chờ một lời gọi registry local.

### 4.3. Stop không purge queue

Dù container stopped, broker destination vẫn có thể:

- Nhận message từ producer.
- Giữ messages persistent trong queue.
- Đặt thời gian expiration, retention/quota riêng.
- Phân phối cho consumer khác vẫn active.
- Chuyển expired/poison messages theo provider policy.

Không coi `stop()` là clear/delete queue. Không xóa pending messages để “giúp stop nhanh” khi chưa có nghiệp vụ phê duyệt.

## 5. stop(Runnable): biết lúc listener processing thực sự ngừng

DMLC cung cấp overload:

```java
void stop(Runnable callback)
```

Theo Javadoc, callback được gọi **khi tất cả listener processing đã thực sự dừng**. Đây là điểm đồng bộ hữu ích hơn khi cần chờ công việc đang chạy trước bảo trì hoặc shutdown coordinated.

### 5.1. API qua registry cho annotated listener

**File `InvoiceListenerAdmin.java`:**

```java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public final class InvoiceListenerAdmin {

    public static final String INVOICE_ID =
            "billing.invoice.worker.v1";

    private final JmsListenerEndpointRegistry registry;

    public InvoiceListenerAdmin(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer requiredContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer(INVOICE_ID);
        if (container == null) {
            throw new IllegalStateException(
                    "Unknown listener endpoint: " + INVOICE_ID);
        }
        return container;
    }

    public void startInvoiceConsumer() {
        requiredContainer().start();
    }

    public void requestStopInvoiceConsumer(Runnable onStopped) {
        requiredContainer().stop(onStopped);
    }

    public boolean running() {
        return requiredContainer().isRunning();
    }
}
```

`MessageListenerContainer` là `SmartLifecycle`, vì vậy có method `stop(Runnable)`. Với DMLC, overload này có logic callback thực hiện sau processing stop. Đừng tạo public HTTP endpoint không có authentication/authorization cho những method điều khiển production.

**Quan trọng:** `requestStopInvoiceConsumer(callback)` chỉ yêu cầu stop trong **JVM hiện tại**; callback không tự đăng thông báo cho mọi pods hoặc chứng minh broker queue đã hết backlog.

### 5.2. Những race conditions khi stop callback

Javadoc DMLC lưu ý:

- Nếu gọi `stop(callback1)`, rồi **gọi `stop(callback2)` thêm lần nữa trước khi processing dừng**, callback sau có thể **ghi đè callback trước**. Không dựa vào việc mọi callback đều được gọi.
- Nếu gọi `start()` để restart **trước khi stop hoàn tất**, callback của stop có thể **không bao giờ được gọi**.
- Callback biểu thị listener processing dừng; **không** phải hoàn thành external transaction DB khác, replication, checkpoint, broker global drain hay health check đa replica.
- Không chặn callback thread bằng việc chờ lại chính nó hoặc tạo deadlock với lifecycle locks.
- Nếu đang shutdown cả ApplicationContext, nên để Spring `LifecycleProcessor` phối hợp SmartLifecycle thay vì tự gọi stop/start hỗn loạn từ một controller.

Nếu cần orchestration phức tạp, tạo một **stateful control layer**: từ chối stop trùng, không cho restart khi đang stopping, kết hợp timeout và idempotency. Đừng tự giả định callback chạy exactly once trong mọi tổ hợp lệnh racing.

### 5.3. Ví dụ phối hợp timeout có giới hạn

Trong workflow vận hành có thể dùng một `CountDownLatch` để chờ callback, nhưng **không** dùng vô hạn:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch stopped = new CountDownLatch(1);
container.stop(stopped::countDown);

boolean finished = stopped.await(20, TimeUnit.SECONDS);
if (!finished) {
    // Alert, chưa được phép báo "mọi message đã hoàn tất".
}
```

Đoạn này là **mảnh code minh họa** bên trong method đã có biến `container` kiểu DMLC/MessageListenerContainer và chính sách interruption phù hợp; không phải file độc lập. `await` có thể ném `InterruptedException` cần xử lý bằng propagate hoặc restore interrupt.

**Một bẫy thời gian:** timeout của thread chờ callback **không ép** broker, DB hoặc handler hoàn tất trong 20 giây. Nếu timeout xảy ra, đánh dấu chưa drain xong và thực hiện policy shutdown/rollout; không tự xác nhận thành công.

## 6. acceptMessagesWhileStopping: message đến đúng lúc dừng

DMLC kế thừa cấu hình:

```java
container.setAcceptMessagesWhileStopping(boolean accept);
```

Đây là setter của `AbstractMessageListenerContainer` trên **container**, không phải method trực tiếp của `DefaultJmsListenerContainerFactory`. Nếu muốn áp cho các containers được factory tạo, cần tùy biến khi khởi tạo container; không copy code `factory.setAcceptMessagesWhileStopping(...)` nếu phiên bản factory của bạn không có setter đó.

### 6.1. Mặc định false

`setAcceptMessagesWhileStopping(false)` là **default**.

Khi container đang trong quá trình stop mà một receive vừa trả message, container cố **từ chối processing message đó** bằng cách abort receive attempt. Điều này giúp hạn chế mở rộng số message mới được xử lý trong stopping phase.

Tuy nhiên:

- Có thể xảy ra cạnh tranh giữa `receive` đã hoàn tất và tín hiệu stop.
- Broker có thể thấy message được nhận rồi bị rollback/recover; message có thể tăng delivery count.
- Spring Javadoc cảnh báo việc abort những receive attempts như vậy **có thể làm giảm retry count còn lại** của message trên broker. Với concurrency cao, số lần attempted có thể tăng vì nhiều consumers đang dừng đồng thời.
- Không khẳng định message “không bao giờ được delivery” hoặc “chắc chắn giữ nguyên delivery count” khi stop.

### 6.2. Bật true

`setAcceptMessagesWhileStopping(true)` cho phép DMLC **xử lý đầy đủ** những message nó nhận được trong stopping phase.

Lợi ích: tránh việc abort một message đã nhận, có thể giảm một số redelivery do stop race trong workload cụ thể.

Đánh đổi: **có thể xử lý cả message mới gửi trong khi đang dừng**, nếu receive được hoàn tất trước khi các timeout hiện tại hết. Vì vậy thời gian drain có thể kéo dài khi producer tiếp tục gửi liên tục, đặc biệt với receive timeout dài hoặc tải cao.

**Không có một lựa chọn true/false tốt nhất cho mọi hệ thống.** Cần chọn theo SLA stop, broker delivery-attempt policy, receive timeout, số consumers và việc producer có thể ngừng publish tạm thời hay không.

### 6.3. Cách áp trên một DMLC tạo thủ công

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("billing.invoice.jobs");
container.setMessageListener(message -> {
    // Raw listener logic.
});
container.setSessionTransacted(true);
container.setReceiveTimeout(1_000L);
container.setAcceptMessagesWhileStopping(false);
```

Đây là **mảnh code cấu hình** có `connectionFactory` hợp lệ, imports Spring JMS, Jakarta JMS provider/broker; nó chưa gọi `afterPropertiesSet()`/`start()` nên chưa phải chương trình hoàn chỉnh. Chỉ minh họa nơi có setter.

### 6.4. Tùy biến factory cho annotated endpoints

Khi thật sự cần bật `true` cho mọi container của một factory, có thể override hook sau:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean("acceptWhileStoppingFactory")
DefaultJmsListenerContainerFactory acceptWhileStoppingFactory(
        ConnectionFactory cf) {

    var factory = new DefaultJmsListenerContainerFactory() {
        @Override
        protected void initializeContainer(
                DefaultMessageListenerContainer container) {
            super.initializeContainer(container);
            container.setAcceptMessagesWhileStopping(true);
        }
    };

    factory.setConnectionFactory(cf);
    factory.setSessionTransacted(true);
    factory.setReceiveTimeout(1_000L);
    return factory;
}
```

Đây là **method @Bean nằm trong class @Configuration**, không phải file Java độc lập. Cấu hình này cần Spring/Jakarta JMS libraries và provider. Nó chỉ là lựa chọn nếu bạn đã hiểu trade-off stopping-phase; **mặc định false thường là điểm xuất phát an toàn cho giới hạn nhận thêm**. Test behavior thực tế với broker mục tiêu.

## 7. Receive timeout không phải thời hạn thực thi handler

DMLC dựa trên polling `MessageConsumer.receive(timeout)`. `AbstractPollingMessageListenerContainer.setReceiveTimeout(long)` điều chỉnh thời gian chờ **một receive attempt**.

```java
factory.setReceiveTimeout(1_000L);  // 1 giây cho một polling receive.
```

Sự khác nhau:

- `receiveTimeout`: chờ message mới khi broker chưa có message phù hợp.
- **Handler execution duration**: thời gian Java method gọi DB, API, transaction/CPU.
- **stop/drain duration**: thời gian cho mọi hoạt động listener đang active hoàn tất theo lifecycle.
- **Spring lifecycle shutdown phase timeout**: ngân sách mà ApplicationContext dành cho phase dừng.
- **Orchestrator termination grace period**: thời gian từ tín hiệu stop đến kill cứng ở process/pod.

Các timeout này **không hoán đổi cho nhau**. Nếu handler bị kẹt 3 phút vì HTTP client không đặt timeout, việc giảm `receiveTimeout` từ 1 giây còn 100 ms **không làm handler trả trong 100 ms**.

### 7.1. Receive timeout quá dài

Một receive đang chặn có thể làm container phải đợi/điều phối thêm theo provider. Timeout dài giúp giảm polling overhead nhưng có thể trì hoãn đáp ứng tín hiệu stop trong một số implementation/cấu hình. Khi broker đang gửi nhiều message, `receive` có thể trả ngay dù timeout dài; điều đó không bảo đảm quá trình stopping ngắn.

### 7.2. Receive timeout quá ngắn

- Polling thức dậy thường xuyên khi queue rỗng.
- Có thể làm tăng CPU/overhead/network round-trips tùy provider.
- Không tự giải quyết in-flight handler đang block.
- Với một số broker, timeout rất ngắn có thể ảnh hưởng utilization và startup/recovery.

Chọn thông qua benchmark, workload và shutdown requirements. Với ví dụ giáo dục, `1_000L` là cấu hình dễ hiểu; không phải thông số bắt buộc.

### 7.3. Mối liên hệ với maxMessagesPerTask

`DefaultMessageListenerContainer` còn có `maxMessagesPerTask`, `concurrentConsumers`, `maxConcurrentConsumers`, `idleTaskExecutionLimit`. Chúng quyết định cách invoker tasks được phân lịch và scale, **không** phải "xử lý tối đa N message rồi hủy container".

Khi dùng custom `TaskExecutor`, cần biết executor có thích tác vụ ngắn hay không; một consumer invoker có thể chiếm thread dài hạn. Đừng coi thread pool size 10 đồng nghĩa chắc chắn 10 tasks kết thúc đúng lúc stop.

## 8. Dữ liệu quan trọng: ACK, transaction và crash window

`stop` liên quan thời điểm nhận; **mất hoặc lặp message** phụ thuộc acknowledge/commit semantics.

### 8.1. AUTO_ACKNOWLEDGE trên DMLC

Theo Spring Javadoc, với `DefaultMessageListenerContainer` và default `AUTO_ACKNOWLEDGE`, message có thể được **ACK trước listener execution**. Khi business method ném exception, container **không có bảo đảm broker redeliver message đó**.

Ví dụ nguy hiểm:

```text
receive M
   |
   +-- AUTO_ACK applied before handler (DMLC)
   |
   +-- handler writes DB / calls API
          |
          +-- exception / JVM killed
               |
               +-- M may already be acknowledged
```

Một shutdown cứng đúng lúc có thể khiến business chưa xong nhưng message không còn để retry. Đây là lý do Spring docs khuyên dùng local transacted session hoặc transaction manager phù hợp khi yêu cầu reliability.

### 8.2. sessionTransacted=true

`DefaultJmsListenerContainerFactory.setSessionTransacted(true)` giúp mỗi lượt receive + xử lý có **local JMS transaction**:

```text
Broker delivers M
   |
   v
JMS Session transacted
   |
   +-- handler success ----> commit JMS receive
   |
   +-- handler throws -----> rollback JMS receive
                               |
                               +-- provider redelivery policy
```

Khi process chết trước commit, JMS broker có thể giao lại message chưa commit sau recovery theo transaction/delivery semantics. Đặc tả và khả năng persistence của broker vẫn quan trọng; cần cấu hình reliable delivery, không suy ra business transaction đã atomic.

Nếu handler đã ghi DB thành công nhưng crash **trước JMS commit**, message có thể redeliver và business effect lặp. Vì vậy:

> **Transacted JMS giảm nguy cơ mất message nhưng không tự cung cấp exactly-once business effect nếu DB và JMS commit độc lập.**

### 8.3. Local JMS transaction không bao trùm DB

Timeline:

```text
t0 receive M in JMS tx
t1 update DB & DB commits
t2 JVM crashes before JMS session.commit()
t3 broker redelivers M
t4 handler tries DB update again
```

Cần:

- Một `businessEventId` duy nhất có nghĩa nghiệp vụ.
- Idempotent handler/unique constraint hoặc processed-event table.
- Transaction DB được thiết kế tương thích.
- Outbox/inbox/XA nếu cần phối hợp atomic cross-system, có đánh đổi hiệu năng.
- Retry/DLQ policy cho poison message để không kẹt mãi.

### 8.4. CLIENT_ACKNOWLEDGE, DUPS_OK, transacted

| Chế độ | Ý nghĩa với DMLC khi listener fail/stop/crash |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | ACK trước listener; không dựa vào redelivery sau lỗi |
| `DUPS_OK_ACKNOWLEDGE` | Lazy ack; có thể gặp duplicate khi crash nhưng không bảo đảm retry cho mọi exception |
| `CLIENT_ACKNOWLEDGE` | Container ack sau thành công; best-effort redelivery cho exception/interruptions |
| `sessionTransacted=true` | JMS transaction, rollback khi listener failure; reliable redelivery theo spec/provider |
| External XA/JTA manager | Có thể phối hợp JMS + resource khác nếu XA-aware, tăng complexity và overhead |

Các dòng là mô tả theo **Spring DMLC reference/Javadoc**, không phải sự thật cho mọi dạng consumer API hoặc tất cả broker cùng một implementation. Luôn kiểm tra Spring/JMS version, configured container và thử nghiệm failure thực.

### 8.5. Khi handler tự bắt exception rồi return

```java
@JmsListener(destination = "billing.invoice.jobs")
public void onInvoice(String id) {
    try {
        businessService.process(id);
    } catch (Exception ex) {
        logFailure(ex);
        // return normally
    }
}
```

Đây là **đoạn anti-pattern** giả sử đã có service/log function hợp lệ. Nếu catch rồi return bình thường trong transacted session, container có thể **commit JMS transaction** vì không thấy lỗi. Message đã xử lý lỗi có thể biến mất mà không được quarantine.

Nếu muốn terminal reject có chủ đích, phải bảo đảm message được lưu vào DLQ/quarantine hoặc có kết quả nghiệp vụ phù hợp **trước commit**, kèm tính nhất quán. Nếu không, propagate lỗi để rollback/retry policy phát huy tác dụng.

## 9. “Message đang xử lý” là ranh giới khó nhất khi shutdown

Cần phân biệt bốn mốc thời gian:

```text
receiveTime  handlerStart       handlerReturn    JMSCommit
    |             |                   |              |
    v             v                   v              v
    +-------------+-------------------+--------------+
             |                 |
         stop requested     DB commit may occur here
```

Không có quy tắc rằng stop phải tới đúng một mốc cụ thể:

- Stop trước `receiveTime`: container có thể không nhận message, nhưng consumer khác còn nhận.
- Stop sau receive, trước handler: kết quả phụ thuộc stopping policy, prefetch và transaction.
- Stop giữa handler: handler có thể chạy tiếp đến completion; crash hoặc lỗi có thể dẫn tới rollback.
- Stop sau handler return nhưng trước JMS commit: kết quả vận chuyển chưa được coi hoàn thành chắc chắn.
- Stop sau JMS commit: JMS message đã được acknowledge/commit; không tự phát ngược message chỉ vì stop.

### 9.1. Graceful stop nên nhằm những điều gì?

Một chiến lược thường mong muốn:

1. **Không tiếp nhận workload mới quá lâu.**
2. **Không cắt ngang các business operations đã vào handler** trong giới hạn có thể.
3. **Commit hoặc rollback rõ ràng** mỗi JMS transaction.
4. **Không mất eventId / trace / database side effects**.
5. **Dừng tài nguyên trước khi process bị kill cứng**.
6. **Cho phép message chưa commit redeliver** khi bị cắt bất ngờ.
7. **Không vô tình nhận thêm message khi đã đánh dấu instance terminating**.

Muốn thực hiện, phải cấu hình đúng cả lifecycle, QoS, broker retention, DB idempotency và shutdown deadline; không chỉ gọi `stop()`.

### 9.2. Nếu business call không có timeout

Giả sử handler gọi một external API không có read timeout. Một thread có thể kẹt vô thời hạn, khiến callback stop không thể đến theo kỳ vọng và vượt ngân sách shutdown. Cần:

- HTTP connection/read timeouts cụ thể.
- DB query/transaction timeout phù hợp.
- Cancellation/interrupt handling nếu library hỗ trợ.
- Circuit breaker/backoff cho lỗi tạm thời.
- Idempotent retry khi process buộc bị kill.
- Không giữ khoá DB quá lâu qua stop window.

`receiveTimeout` chỉ xử lý polling, không cứu handler bị block trong external call.

### 9.3. Nếu đã thực thi side effect trước JMS commit

Một message có thể được **redeliver** ngay cả khi nghiệp vụ bên ngoài đã chạy thành công nhưng ack chưa kịp commit. Vì vậy trong shutdown test phải đo cả:

- Số message broker attempted/delivered.
- Số lần handler invoked.
- Số **business event IDs duy nhất** đã commit.
- Số duplicate attempts/idempotency skips.
- Số lần JMS transaction committed/rolled back.

Chỉ xem log "processed" không chứng minh broker đã commit nhận message.

## 10. stop, shutdown, destroy: chọn API đúng mục tiêu

### 10.1. Dùng stop() để pause/resume

Ví dụ vận hành nội bộ sau khi đã có container:

```java
MessageListenerContainer container =
        registry.getListenerContainer("billing.invoice.worker.v1");

if (container == null) {
    throw new IllegalStateException("Listener not found");
}

container.stop();  // Tạm ngừng theo lifecycle.
container.start(); // Có thể bật lại sau khi stop đã hoàn tất.
```

Đây là **mảnh code thuộc Spring project** có `registry` được inject, không dùng ngay liên tiếp trong production khi chưa chờ stop hoàn tất. Không restart trong khi `stop(Runnable)` vẫn chờ mà không hiểu callback race.

### 10.2. Không gọi shutdown() để pause

`shutdown()` ở `AbstractJmsListeningContainer`:

- Stop shared JMS Connection nếu có.
- Gọi `doShutdown()` để đóng registered invokers/resources.
- Đóng lifecycle container.
- Được `destroy()` gọi khi BeanFactory hủy container.

```java
// Chỉ minh họa trên instance được sở hữu/quản lý rõ ràng:
DefaultMessageListenerContainer container = ...;
container.shutdown();
```

Đây là **pseudocode fragment**. Không đi thẳng tới `shutdown()` trên một container do `JmsListenerEndpointRegistry` quản lý chỉ để bảo trì ngắn hạn. Spring context sẽ quản lý destruction; manual shutdown nhầm có thể để registry còn key trỏ tới container đã không còn active.

### 10.3. So sánh vòng đời sau lệnh

| Sau thao tác | DMLC có thể tái dùng không? | Ai chịu trách nhiệm tiếp theo? |
| --- | --- | --- |
| stop completed | Có thể `start()` lại | Registry/ứng dụng |
| shutdown/destroy completed | Không coi là restartable handle | Recreate container/context |
| Spring context closed | Không dùng managed beans đã destroyed | Restart app/context |
| Pod killed | Toàn process mất | Orchestrator restart; broker recovery |
| Topic durable consumer stopped | Subscription có thể vẫn tồn tại broker | Broker + subscription identity |
| Topic non-durable stopped | Subscription có thể không còn active | Producer/consumer lifecycle |

Điều kiện broker và subscription có thể khiến hành vi message khác nhau **dù stop/shutdown cùng được gọi**.

## 11. Spring SmartLifecycle và thứ tự đóng ApplicationContext

DMLC implements `SmartLifecycle`; trong Spring, lifecycle phases quyết định thứ tự start/stop:

- Phase thấp **start trước**.
- Phase cao **start sau**.
- Khi shutdown theo phase thông thường, phase cao **stop trước** (thứ tự đảo ngược).

`AbstractJmsListeningContainer.setPhase(int)` hỗ trợ điều khiển phase. Mặc định là `SmartLifecycle.DEFAULT_PHASE`, tương đương giá trị rất cao; listener thường start muộn và stop sớm trong thứ tự mặc định.

### 11.1. Phase có ích khi nào?

Giả sử handler cần một internal executor/service để xử lý:

```text
Startup:
  dependencies ready first
         |
         v
  JMS consumers start later

Shutdown:
  JMS consumers stop/drain first
         |
         v
  dependencies/executors shut down later
```

Đặt phase và bean dependencies sao cho consumer **không còn chạy handler khi các dịch vụ mà handler cần đã bị destroy**. Nhưng phải kiểm tra cơ chế phase ở registry và từng container, không xem một con số setPhase là bảo đảm tuyệt đối cho mọi phụ thuộc.

### 11.2. Ví dụ config phase

```java
@Bean("invoiceListenerFactory")
DefaultJmsListenerContainerFactory invoiceListenerFactory(
        ConnectionFactory cf) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setSessionTransacted(true);
    factory.setAutoStartup(true);
    factory.setPhase(100);
    return factory;
}
```

Đây là **một @Bean method** ở trong class @Configuration có imports phù hợp; không standalone. `100` là giá trị minh họa, **không phải khuyến nghị mặc định**. Khi dùng `@JmsListener`, `JmsListenerEndpointRegistry` cũng tham gia lifecycle của annotated containers; phải xác minh thứ tự shutdown thực qua logs/test của Spring version đang chạy.

### 11.3. Cẩn thận với shutdown phase timeout

Spring LifecycleProcessor hỗ trợ timeout chờ stop callbacks theo phase. Nếu budget chờ chỉ 10 giây nhưng handler có thể chạy 45 giây, callback của listener có thể đến sau khi phase đã hết hạn, và các dependency có thể tiếp tục đóng theo policy. Đừng chỉ tune receiveTimeout để “giải quyết 45 giây” — phải xét handler worst-case và deadline của toàn deployment.

## 12. Spring Boot graceful shutdown không tự bảo đảm JMS drain

Một điểm rất dễ nhầm: cấu hình **HTTP server graceful shutdown** trong Spring Boot và lifecycle dừng JMS listeners là các phần khác nhau của Spring application.

Trong Spring Boot 3.x, thường có:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 40s
```

Spring Boot 4.x có những default khác đối với embedded web server, nên phải đọc tài liệu **đúng version**. `spring.lifecycle.timeout-per-shutdown-phase` cấu hình khoảng thời gian Spring chờ mỗi phase lifecycle stop — **không phải** lời hứa JMS transaction nào cũng hoàn thành trong 40 giây hoặc setting tự động gắn trên riêng DMLC.

### 12.1. Có ba ngân sách thời gian khác nhau

| Thời gian | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| JMS receive timeout | `factory.setReceiveTimeout(...)` | Thời gian chờ một receive |
| Spring lifecycle phase timeout | `spring.lifecycle.timeout-per-shutdown-phase` | Budget Spring LifecycleProcessor chờ callback trong phase |
| Orchestrator stop grace period | Kubernetes `terminationGracePeriodSeconds` hoặc tương đương | Từ SIGTERM đến khả năng kill cứng |
| Handler timeout | HTTP/DB/client/business logic | Giới hạn external calls/CPU/transaction riêng |
| Broker redelivery delay | Provider policy | Khoảng thời gian trước một redelivery/retry |

Nếu Pod termination grace = 15s mà Spring lifecycle timeout = 40s, **orchestrator có thể kill process trước** khi Spring chờ xong. Không thể bảo đảm shutdown graceful chỉ bằng YAML của Spring.

### 12.2. Ví dụ timeline rolling deployment

```text
t=00s  Orchestrator marks pod terminating, sends SIGTERM
t=01s  ApplicationContext begins graceful shutdown
t=02s  JMS container gets stop signal
t=03s  Handler M1 still working
t=08s  Handler M1 completes, JMS commit occurs
t=09s  DMLC stop callback may run
t=10s  Remaining Spring beans shut down
t=12s  Process exits

Hard kill deadline might be at t=30s.
```

Chỉ là một **timeline mong muốn**, không phải cơ chế bảo đảm. Nếu handler không xong trước deadline, OS/orchestrator có thể buộc dừng và broker phải xử lý message chưa commit theo cấu hình. Bảo vệ nghiệp vụ bằng idempotency và transactional correctness.

### 12.3. Readiness và traffic drain

Khi rolling deploy có nhiều replicas:

1. Đánh dấu instance không nhận **HTTP traffic mới** (nếu app có web entry point).
2. Ngừng/giảm receive JMS đúng policy. **HTTP readiness=false không tự stop JMS listener**.
3. Đợi in-flight processing hoàn tất trong ngân sách.
4. Cho broker redistribute queue messages sang replicas còn active.
5. Đóng context và cho process exit.

Nếu cần "không nhận JMS mới", phải **stop JMS containers** hoặc quản lý receive/broker routing; readiness probe HTTP chỉ ảnh hưởng load balancer HTTP.

## 13. Queue vs Topic khi dừng Default container

### 13.1. Queue

- Message **chưa giao** thường vẫn nằm trong Queue theo TTL/retention/quota.
- Nếu có consumer khác của cùng Queue đang chạy, broker có thể giao cho consumer đó.
- Message **đã receive nhưng chưa commit** có thể redeliver khi rollback hoặc connection mất.
- Một message có thể đã có DB side effect nhưng chưa JMS commit → duplicate khi redeliver.
- `stop()` không xóa Queue, không bảo đảm backlog về 0.

### 13.2. Topic non-durable subscription

Khi consumer/subscription non-durable không active, publisher có thể tiếp tục gửi event nhưng **subscription mới không nhận hồi tố** những event trước thời điểm nó tồn tại. Vì vậy pause một non-durable listener có thể khiến ứng dụng bỏ lỡ event, dù producer dùng persistent delivery.

Đừng triển khai "stop rồi start lại sẽ tự đọc toàn bộ event đã publish" với non-durable Topic. Nếu nghiệp vụ yêu cầu offline replay, thiết kế durable subscription **trước** khi publish.

### 13.3. Topic durable subscription

Một durable subscription được định danh và duy trì theo Jakarta Messaging/provider rules:

- Khi consumer ngừng, matched messages có thể tiếp tục pending cho subscription.
- DeliveryMode, TTL, broker retention, quota và subscription identity vẫn ảnh hưởng.
- Đổi `clientId`/`subscription` khi restart có thể khiến consumer đọc một subscription **khác**, bỏ lỡ backlog cũ.
- Durable không đồng nghĩa exactly-once business processing.
- Với shared durable subscription, những consumers chung subscription chia tải; với nhiều subscriptions độc lập, mỗi subscription có backlog riêng.

**Không dùng @JmsListener.id thay cho broker-side durable subscription name**. Container endpoint ID là key trong Spring registry, còn subscription/client ID thuộc JMS transport lifecycle.

### 13.4. So sánh

| Ý định | Queue | Topic non-durable | Topic durable |
| --- | --- | --- | --- |
| Tạm dừng local listener | Backlog queue có thể tồn, hoặc consumer khác nhận | Có thể mất event trong lúc unsubscribed | Matched event có thể tích backlog subscription |
| Restart | Có thể nhận pending queue | Chỉ những event sau khi subscription active trở lại | Có thể đọc matched backlog theo policy |
| Nhiều replica | Competing consumers | Có thể mỗi subscription riêng nhận copy | Shared/unshared identity phải thiết kế rõ |
| Hệ quả in-flight rollback | Có thể redeliver | Phụ thuộc provider/subscription lifecycle | Có thể redeliver theo transaction/subscription state |

## 14. Connection recovery không phải stop/restart do operator

DMLC có cơ chế self-recovery khi broker unavailable tạm thời. Khi đang running mà broker mất kết nối, container có thể:

- Ghi lỗi kết nối.
- Đợi theo `recoveryInterval`/`BackOff`.
- Re-establish Connection/Session/Consumer.
- Tiếp tục nhận khi hạ tầng trở lại.

`setRecoveryInterval(...)` mặc định Spring DMLC là **5.000 ms** trên các version được trích dẫn. Giá trị này là khoảng thử phục hồi kết nối, **không phải delay redelivery của message bị rollback**.

```java
factory.setRecoveryInterval(5_000L);
```

Nếu broker đang down, `container.isRunning()` có thể vẫn true dù chưa có active consumer kết nối thật. Khác với operator `stop()`, recovery loop là container muốn tiếp tục chạy nhưng đang xử lý lỗi hạ tầng.

### 14.1. Đừng chỉ nhìn isRunning

Các chỉ số DMLC hữu ích:

- `getActiveConsumerCount()`: số consumer invokers đang active theo container.
- `getScheduledConsumerCount()`: số consumers được schedule.
- `isRegisteredWithDestination()`: có consumer đã tạo fixed registration với destination trong cache mode phù hợp.
- Broker consumer count, connection status, enqueue/deliver/ack rate.
- Listener success/failure, timeout/latency, DLQ và oldest message age.

Các count/flag DMLC **không tự thay thế broker metrics**, đặc biệt nếu có cache, provider prefetch, transacted receive hoặc connection recovery.

### 14.2. CachingConnectionFactory và stop/restart

Spring DMLC Javadoc khuyến nghị thận trọng khi dùng `CachingConnectionFactory` bên ngoài listener container: DMLC thường có cơ chế cache session/consumer riêng. Stop/restart có thể cần **Connection cache độc lập cục bộ**, không phải externally shared cache khiến semantics khác mong muốn.

Nếu gặp hiện tượng stop rồi broker vẫn hiển thị consumers cached, đừng tự suy container đang nhận message; kiểm tra provider, cache level, external connection factory và counters, rồi test trên broker đúng phiên bản.

## 15. Chẩn đoán khi stop “không dừng” hoặc message bị lặp

### Tình huống A — Stop rồi vẫn có business log

Khả năng:

1. Handler đã bắt đầu **trước** stop.
2. `acceptMessagesWhileStopping=true` cho phép message nhận trong stopping phase được xử lý.
3. Operator chỉ stop một replica, replica khác vẫn consume.
4. Stop callback chưa đến, pending processing vẫn chạy.
5. Logger xuất log trễ/asynchronous, không phản ánh thời điểm handler start.
6. Có một listener container khác cùng destination không được stop.

Cách làm: ghi eventId, endpointId, instance, receive/start/end/commit timestamps, và chờ callback trước khi kết luận. Đừng tăng mức kill/force shutdown ngay mà chưa phân loại in-flight.

### Tình huống B — Stop xong queue depth tăng

Đây thường **không phải bug**: producer vẫn publish, consumer tạm dừng thì backlog tăng. Quan sát arrival rate, TTL, disk quota, broker producer flow control và khả năng consumer khác nhận.

Nếu không muốn queue tăng, cần phối hợp upstream throttling/backpressure hoặc một nơi lưu bền phù hợp. Không purge queue để làm dashboard đẹp.

### Tình huống C — Restart lại thấy xử lý cùng eventId hai lần

Có thể:

- JMS receive trước đó chưa commit khi process stop/crash.
- Handler đã commit DB trước JMS commit, message redeliver.
- Producer retry phát lại cùng event nghiệp vụ.
- Cùng event xuất hiện nhiều lần upstream.
- Topic có nhiều subscription độc lập và bạn đang tổng hợp logs của các replicas.

Giải pháp: business idempotency, xem `JMSRedelivered`, processed-event table, transaction logs và broker delivery policy. Không sửa bằng cách tắt persistent mode hoặc ACK sớm.

### Tình huống D — Graceful shutdown quá lâu

Tìm:

- Handler chạy lâu và chưa return.
- Receive timeout lớn/provider stop chậm.
- `acceptMessagesWhileStopping=true` khiến vẫn xử lý message vừa nhận.
- External HTTP/DB calls không có timeout.
- Nhiều consumers, pending inflight count cao.
- LifeCycle phase timeout và orchestrator grace period không phù hợp.
- Cross-bean shutdown order khiến dependency bị đóng trước khi handler xong.

Thay đổi một parameter rồi đo, không đồng thời giảm mọi timeout xuống gần 0.

### Tình huống E — Stop làm message tăng redelivery count

Với `acceptMessagesWhileStopping=false`, DMLC có thể abort receive attempts xảy ra lúc stopping; Spring Javadoc cảnh báo việc này có thể tiêu hao retry count ở provider. Broker có delivery limit thấp và concurrency cao có thể đẩy message sang DLQ dù business method chưa xử lý.

Cách giảm rủi ro: kiểm tra broker retry policy, concurrency, stop timing và cân nhắc `acceptMessagesWhileStopping` theo kết quả test. **Không** đặt retry vô hạn mà không có DLQ/quarantine và observability.

### Tình huống F — SIGKILL trước JMS commit

Spring không được gọi cleanup bình thường; có thể mất network connection giữa transaction. Với transacted receive và broker reliable, uncommitted message có thể redeliver. Nếu code có side effects, idempotency là bắt buộc.

Không khẳng định graceful shutdown có thể hoạt động khi kill cứng vì `SIGKILL` không cho Spring thực thi shutdown hooks.

## 16. Thiết kế quy trình vận hành pause/resume an toàn

Một runbook tối thiểu cho **một local endpoint**:

1. **Định danh chính xác:** service, env, pod, endpoint ID, Queue/Topic/durable subscription và broker namespace.
2. **Quyền thao tác:** chỉ operator được ủy quyền, audit lý do và thời điểm.
3. **Điều kiện trước stop:** xem số in-flight tasks, handler max duration, queue backlog và có consumer khác không.
4. **Yêu cầu stop:** dùng `registry.getListenerContainer(id).stop(callback)` khi cần biết drain completion.
5. **Chờ có giới hạn:** callback đến hoặc hết timeout; không được coi timeout là thành công.
6. **Xác minh:** broker consumer/in-flight counts, handler in-progress gauge, JMS commits/rollbacks, DB side effects.
7. **Đánh giá backlog:** nếu Queue pending tăng, xác định đó là kỳ vọng hay quá quota.
8. **Bảo trì:** thay đổi dependency/config khi không còn handler đang dùng chúng.
9. **Khôi phục:** `start()` đúng local endpoint hoặc cho context mới khởi động.
10. **Sau start:** xác minh broker registration, successful processing, oldest age/throughput và error rate.
11. **Phân tán:** thực hiện có điều phối trên toàn replicas nếu mục tiêu là global pause.
12. **Rollback plan:** nếu stop chưa hoàn tất, không xóa message; cho provider/JMS transaction phục hồi theo chính sách, theo dõi duplicate.

### 16.1. Runbook khi deploy nhiều replicas

Cho Queue có 3 replicas A/B/C:

- Đưa A vào chế độ terminating và dừng listener của A, nhưng để B/C tiếp tục xử lý.
- Chờ in-flight A (trong grace budget).
- Thay A bằng A' và xác minh A' kết nối/consume thành công.
- Lặp lại B, rồi C.

**Không** stop tất cả A/B/C đồng thời nếu queue không đủ disk/backlog hoặc upstream vẫn publish mạnh. Ngược lại, nếu cần broker schema migration đòi dừng toàn bộ, phải có kế hoạch xử lý messages/quota và producer coordination.

### 16.2. Production không nên expose stop/start vô điều kiện

Một HTTP API `POST /jms/stop?id=...` chưa xác thực là bề mặt rủi ro vận hành và bảo mật. Nếu phải có control plane:

- Xác thực/ủy quyền mạnh, giới hạn allowlist endpoint IDs.
- Audit mọi lệnh và người yêu cầu.
- Chặn thao tác trùng/racing.
- Trả trạng thái **requested / draining / stopped**, không chỉ “200 OK”.
- Không coi remote RPC 200 như callback completion trên toàn cluster.
- Có timeout, idempotency, rollback và người chịu trách nhiệm.

## 17. Kiểm thử integration lifecycle với broker thật

### Test A — autoStartup=false rồi start

1. Cấu hình một factory `setAutoStartup(false)`.
2. Khởi động Spring context, xác minh registry có endpoint ID nhưng container không running.
3. Gửi một message vào Queue.
4. Xác minh message pending khi không có consumer khác/không expiry.
5. Gọi `start()`, xác minh listener nhận và xử lý.
6. Dừng và start lại để xác minh normal pause/resume.

### Test B — stop giữa handler

1. Dùng test handler báo `started` bằng latch.
2. Giữ handler chưa complete bằng latch thứ hai.
3. Producer gửi `M1`.
4. Sau khi started latch được đánh dấu, gọi `container.stop(callback)`.
5. Xác minh callback **chưa đến khi handler đang xử lý** (với DMLC và test configuration).
6. Cho handler hoàn thành, xác minh callback được gọi sau processing stop.
7. Đọc broker commit/ack và business result; đừng chỉ assert callback.
8. Dùng timeout cho mọi latch và cleanup test broker resource.

### Test C — transacted và failure

1. `setSessionTransacted(true)`, handler lưu `eventId` rồi cố tình throw ở tình huống kiểm soát.
2. Xác minh rollback/redelivery theo broker policy.
3. Tạo business idempotency, chứng minh duplicate attempts không tạo duplicate side effects.
4. Kiểm tra DLQ/quarantine khi vượt attempts.
5. Lặp lại với `AUTO_ACKNOWLEDGE` trong queue test riêng và ghi nhận có thể không redeliver.

### Test D — acceptMessagesWhileStopping

1. Chạy DMLC với `false` và concurrency cao hơn một.
2. Producer bắn message đồng thời stop; đo callback duration, delivery counts và DLQ.
3. Lặp lại với `true`, cùng tải và receive timeout.
4. So sánh số message được xử lý trong stopping phase và retry consumption.
5. Chọn policy theo kết quả thực, không theo phỏng đoán.

### Test E — stop 1/3 replicas

1. Dùng ba ứng dụng kết nối cùng Queue test.
2. Dừng registry/container ở một instance.
3. Xác minh hai replicas còn lại tiếp tục nhận.
4. Kiểm tra A không còn xử lý message mới sau khi callback completion, có log những in-flight trước đó.
5. Khởi động lại A và xác minh consumer count phục hồi.
6. Không dùng chung JMS unshared durable topic clientId trong test Queue/Topic khác.

### Test F — non-durable vs durable topic

1. Tạo non-durable Topic listener, publish E1, stop listener.
2. Publish E2 khi subscription không còn active; restart, xác minh không có bảo đảm replay E2.
3. Tạo durable subscription với identity cố định đúng provider, làm tương tự.
4. Quan sát matched E2 có thể vào durable backlog theo TTL/delivery mode/broker policy.
5. Đảm bảo không đổi subscription name/clientId giữa các lần.

### Test G — kill giữa DB commit và JMS commit

1. Handler nhận eventId, commit business effect vào DB.
2. Tại test barrier ngay trước JMS receive transaction commit, kill process thô trong môi trường test.
3. Restart consumer; kiểm tra redelivery.
4. Xác minh idempotency làm business effect không bị lặp.
5. Quan sát broker delivery count và DLQ policy; tránh thử trên production.

### Test H — shutdown deadline

1. Cho handler mô phỏng công việc 5s và 20s, cấu hình grace period khác nhau.
2. Trigger Spring ApplicationContext close bằng path chuẩn trong test.
3. Quan sát order Spring SmartLifecycle stop, callback, bean destroy và process exit.
4. Giả lập orchestrator kill deadline ngắn; kiểm tra incomplete transactions được redeliver.
5. Test cả broker unavailable trong lúc shutdown để thấy khả năng recovery/quá hạn.
6. Không kết luận thành công chỉ vì process exit code = 0.

## 18. Java 17 chạy độc lập: mô phỏng in-flight khi stop

Chương trình sau **chỉ dùng JDK 17**, không JMS broker, không Spring dependencies. Nó mô phỏng trạng thái Queue sẵn sàng, message đang xử lý, yêu cầu stop, completion và shutdown. **Đây là state-machine demo**: không tái hiện chính xác mọi race, commit timing hay provider behavior.

Tạo file **`ListenerLifecycleDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

public final class ListenerLifecycleDemo {

    enum State { STOPPED, RUNNING, STOPPING, DESTROYED }

    static final class Listener {
        private State state = State.STOPPED;
        private final Queue<String> ready = new ArrayDeque<>();
        private final List<String> committed = new ArrayList<>();
        private String inFlight;

        Listener(String... messages) {
            for (String message : messages) {
                ready.add(message);
            }
        }

        void start() {
            if (state == State.DESTROYED || state == State.STOPPING) {
                throw new IllegalStateException(
                        "Cannot start from " + state);
            }
            state = State.RUNNING;
        }

        String receive() {
            if (state != State.RUNNING || inFlight != null) {
                return null;
            }
            inFlight = ready.poll();
            return inFlight;
        }

        void stop() {
            if (state == State.RUNNING) {
                state = inFlight == null
                        ? State.STOPPED : State.STOPPING;
            }
        }

        String finish() {
            if (inFlight == null) {
                throw new IllegalStateException("No message in flight");
            }
            String id = inFlight;
            committed.add(id);
            inFlight = null;
            if (state == State.STOPPING) {
                state = State.STOPPED;
            }
            return id;
        }

        void shutdown() {
            if (inFlight != null) {
                throw new IllegalStateException("Not drained");
            }
            state = State.DESTROYED;
        }

        State state() { return state; }
        String inFlight() { return inFlight; }
        List<String> ready() { return List.copyOf(ready); }
        List<String> committed() { return List.copyOf(committed); }
    }

    public static void main(String[] args) {
        Listener listener = new Listener("JOB-1", "JOB-2");

        listener.start();
        System.out.println("Received: " + listener.receive());

        listener.stop();
        System.out.println("Stop requested: " + listener.state());
        System.out.println("In-flight: " + listener.inFlight());
        System.out.println("Receive while stopping: "
                + (listener.receive() == null ? "none" : "unexpected"));

        System.out.println("Completed: " + listener.finish());
        System.out.println("State after drain: " + listener.state());
        System.out.println("Pending: " + listener.ready());

        listener.start();
        System.out.println("Restart received: " + listener.receive());
        System.out.println("Completed: " + listener.finish());
        System.out.println("Committed: " + listener.committed());

        listener.shutdown();
        System.out.println("Shutdown state: " + listener.state());

        try {
            listener.start();
        } catch (IllegalStateException ex) {
            System.out.println("Restart after shutdown: REJECTED");
        }
    }
}
```

Lệnh chạy:

```bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
```

**Stdout chính xác:**

```text
Received: JOB-1
Stop requested: STOPPING
In-flight: JOB-1
Receive while stopping: none
Completed: JOB-1
State after drain: STOPPED
Pending: [JOB-2]
Restart received: JOB-2
Completed: JOB-2
Committed: [JOB-1, JOB-2]
Shutdown state: DESTROYED
Restart after shutdown: REJECTED
```

Giải thích:

- `JOB-1` được receive trước stop.
- Stop chuyển sang `STOPPING` khi đang có in-flight work.
- `receive()` từ chối thêm message khi stop đang diễn ra.
- `finish()` mô phỏng handler completion và JMS commit, chuyển sang `STOPPED`.
- `JOB-2` vẫn trong `ready` cho đến khi start lại.
- `shutdown()` chuyển sang state kết thúc vòng đời; lần start sau bị từ chối.

Đây là **mô phỏng tuần tự**, không chạy Spring `DefaultMessageListenerContainer`. Trong JVM/JMS thật, message commit/rollback do JMS Session/container, receive timeout/connection/provider race khác nhau; `stop()`/`shutdown()` không trả enum `State` như demo. Nó nhằm giúp hiểu **in-flight không biến mất chỉ vì đã yêu cầu stop**.

### 18.1. Bài tập mở rộng demo

1. Thêm `rollback()`: đưa `inFlight` về đầu `ready` và tăng attempt counter thay vì thêm vào `committed`.
2. Thêm `deadline`: nếu stop quá lâu, mô phỏng process kill và JMS redelivery sau restart.
3. Thêm một listener thứ hai chung Queue: chỉ một consumer được receive `JOB-2` ở mỗi lần delivery.
4. Thêm idempotency `Set<String> processedIds` để bỏ qua side effect khi `JOB-1` được redeliver.
5. So sánh trạng thái `STOPPING` ở demo với callback `stop(Runnable)` của DMLC, nhưng **không coi đây là implementation của callback thật**.

## 19. Các lỗi tư duy thường gặp

**Lỗi 1 — “stop() xóa mọi message đang chạy.”**  
Không. Stop điều khiển listener lifecycle; in-flight có thể chạy tiếp, commit, rollback hoặc bị cắt bởi process failure.

**Lỗi 2 — “stop() giống shutdown().”**  
Không. `stop()` dùng cho pause/resume; `shutdown()` đóng lifecycle/resources và không nên dùng cho restart cùng object.

**Lỗi 3 — “isRunning=false nghĩa là không còn method nào đang chạy.”**  
Không đủ. Dùng stop callback/drain monitoring để xác minh processing dừng.

**Lỗi 4 — “isRunning=true nghĩa là broker kết nối khỏe.”**  
Không đủ. DMLC có thể đang retry recovery mà lifecycle vẫn running.

**Lỗi 5 — “stop một Pod làm cả cluster ngừng consume.”**  
Sai. Registry local; replicas khác vẫn có thể nhận.

**Lỗi 6 — “stop() sẽ purge Queue.”**  
Sai. Broker queue/pending là state riêng.

**Lỗi 7 — “Mọi message vừa đến trong stopping phase chắc chắn được xử lý.”**  
Không. Default `acceptMessagesWhileStopping=false` có thể reject receive attempts.

**Lỗi 8 — “acceptMessagesWhileStopping=true luôn an toàn hơn.”**  
Không. Có thể tiếp tục xử lý cả message mới trong lúc stopping, kéo dài drain.

**Lỗi 9 — “acceptMessagesWhileStopping=false không ảnh hưởng retry.”**  
Không hẳn. Spring Javadoc cảnh báo abort receive có thể tiêu hao delivery attempts của provider.

**Lỗi 10 — “receiveTimeout=1s làm handler timeout sau 1s.”**  
Sai. Nó chỉ là thời gian chờ mỗi JMS receive.

**Lỗi 11 — “stop(callback) callback luôn chạy dù stop hai lần hoặc restart sớm.”**  
Không. DMLC có các race callback override/cancellation được tài liệu hóa.

**Lỗi 12 — “Bật sessionTransacted=true là DB + JMS commit nguyên tử.”**  
Không. Local JMS transaction không tự bao trùm database.

**Lỗi 13 — “AUTO_ACKNOWLEDGE sẽ retry nếu handler throw.”**  
Không thể dựa vào điều này với DMLC; nó có thể ACK trước listener.

**Lỗi 14 — “JMS transaction đảm bảo business effect đúng một lần.”**  
Không. Crash giữa business commit và JMS commit có thể tạo duplicate processing.

**Lỗi 15 — “server.shutdown=graceful đủ để dừng JMS an toàn.”**  
Không. Đó là web server shutdown; còn listener lifecycle, phase timeout, broker state và orchestrator grace phải được xét.

**Lỗi 16 — “spring.lifecycle.timeout-per-shutdown-phase=40s buộc Pod sống đủ 40s.”**  
Không. Orchestrator có thể kill sớm hơn theo riêng deadline.

**Lỗi 17 — “Pod readiness=false tự stop @JmsListener.”**  
Không. Readiness thường ảnh hưởng routing HTTP, không phải JMS polling.

**Lỗi 18 — “Dừng Topic subscriber không thể mất event nếu producer PERSISTENT.”**  
Không đúng với non-durable subscription khi không active.

**Lỗi 19 — “shutdown() có thể dùng để toggle listener như stop().”**  
Không. Shutdown dành cho cleanup cuối vòng đời, không phải pause ngắn.

**Lỗi 20 — “Có stop callback là mọi business side effects đã atomic commit.”**  
Không. Phải quan sát transaction boundaries và data stores thực tế.

## 20. Checklist trước khi đưa lifecycle policy lên production

- [ ] Biết chính xác listener container class đang dùng: `DefaultMessageListenerContainer` hay loại khác?
- [ ] Đã phân biệt factory, registry, endpoint ID và container instance?
- [ ] Có stable `@JmsListener.id` để tra cứu đúng container không?
- [ ] Biết `isActive` và `isRunning` biểu thị điều gì, không coi chúng là broker health?
- [ ] Nếu cần manual-start, đã cấu hình `setAutoStartup(false)` và workflow start phù hợp?
- [ ] Stop có cần `stop(Runnable)` callback để xác minh drain không?
- [ ] Có bảo vệ race stop trùng, start sớm, callback bị ghi đè?
- [ ] Có theo dõi in-flight handler count và JMS commit/rollback?
- [ ] Đã xem default `acceptMessagesWhileStopping=false` có hợp broker retry policy?
- [ ] Nếu bật true, đã test khả năng nhận message mới và kéo dài stopping phase?
- [ ] Receive timeout chỉ dành polling; business I/O cũng có timeout độc lập?
- [ ] Có giới hạn worst-case handler execution và DB transaction duration?
- [ ] Listener session có `sessionTransacted=true` hoặc transaction strategy phù hợp?
- [ ] Đã xác minh AUTO_ACK behavior trên DMLC, không dựa vào retry giả?
- [ ] Có business idempotency để xử lý redelivery sau crash?
- [ ] Broker destination persistence, TTL, redelivery, DLQ/quarantine đã được kiểm thử?
- [ ] Đã xác định queue/topic/durable/shared subscription và mất event khi offline?
- [ ] Spring lifecycle phases và callback timeout có phù hợp các dependencies?
- [ ] Spring Boot version và server shutdown behavior đã được đọc đúng?
- [ ] Orchestrator termination grace đủ lớn so với lifecycle/handler worst-case?
- [ ] Readiness/HTTP drain và JMS consumer stop được phối hợp riêng?
- [ ] Rolling deploy có đảm bảo chỉ dừng một phần replicas khi còn message backlog?
- [ ] Có runbook authorized start/stop, audit log và timeout/rollback?
- [ ] Có metrics broker queue depth, oldest age, consumer counts, retries, DLQ?
- [ ] Có test stop khi handler đang chạy, stop khi message vừa nhận, broker outage, SIGKILL?
- [ ] Đã kiểm thử bối cảnh nhiều replicas, không nhầm local registry với cluster control?
- [ ] Không gọi `shutdown()` để pause/resume container do registry quản lý?
- [ ] Không suy callback completion đồng nghĩa mọi business result đã commit atomically?

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `DefaultMessageListenerContainer` nhận message bằng cơ chế gì?

**Đáp án:** DMLC dùng các invoker tasks gọi `MessageConsumer.receive()` để polling, chạy listener và quản lý JMS sessions/consumers; khác SimpleMessageListenerContainer dùng `setMessageListener`.

**Câu 2.** Stop và shutdown khác gì?

**Đáp án:** Stop cho phép pause/resume container đang active; shutdown là cleanup/close cuối vòng đời, không nên xem là thao tác pause có thể restart bình thường.

**Câu 3.** Một message đã vào handler trước `stop()`. Nó có chắc bị hủy ngay không?

**Đáp án:** Không. Handler có thể tiếp tục hoàn tất hoặc lỗi/rollback tùy trạng thái, container, provider và deadline process.

**Câu 4.** Làm sao nhận tín hiệu khi listener processing đã thực sự dừng trong DMLC?

**Đáp án:** Dùng `stop(Runnable callback)`; callback được gọi sau processing stop. Phải xét timeout và race khi stop trùng/restart sớm.

**Câu 5.** Default của `acceptMessagesWhileStopping` là gì?

**Đáp án:** `false`, tức container cố reject message vừa receive trong stopping phase. Điều đó có thể ảnh hưởng provider retry count.

**Câu 6.** Vì sao bật `acceptMessagesWhileStopping(true)` có thể kéo dài dừng?

**Đáp án:** Nó cho xử lý những message nhận lúc stopping, kể cả message mới được producer gửi trước khi receive timeout kết thúc.

**Câu 7.** `receiveTimeout=1000` có giết method business chạy hơn 1 giây không?

**Đáp án:** Không. Đây chỉ là polling receive timeout; business method cần timeout riêng.

**Câu 8.** `setSessionTransacted(true)` giúp gì?

**Đáp án:** JMS receive được commit sau listener thành công; lỗi/crash có thể rollback/redeliver theo JMS transaction/broker policy. Không gộp DB thành cùng local JMS transaction.

**Câu 9.** `AUTO_ACKNOWLEDGE` trên DMLC có bảo đảm retry khi handler throw không?

**Đáp án:** Không. DMLC có thể ACK trước listener execution, nên không dựa vào redelivery khi exception.

**Câu 10.** Đã ghi DB xong nhưng crash trước JMS commit. Message có thể lặp không?

**Đáp án:** Có. Broker có thể redeliver message chưa commit. Cần idempotent business effect.

**Câu 11.** `registry.getListenerContainer(id)` trả gì khi ID không tồn tại?

**Đáp án:** `null`; phải kiểm tra trước khi gọi start/stop.

**Câu 12.** Stop listener ở Pod A có stop Pod B không?

**Đáp án:** Không. Registry và container lifecycle nằm trong từng ApplicationContext/JVM.

**Câu 13.** Dừng một Topic non-durable consumer có tự lưu events phát trong thời gian offline không?

**Đáp án:** Không. Non-durable subscription không bảo đảm replay message đã publish khi không active.

**Câu 14.** Vì sao durable topic có thể giữ backlog khi container stopped?

**Đáp án:** Broker duy trì durable subscription identity và matched messages theo retention/delivery policy, miễn subscription đã được tạo/cấu hình đúng.

**Câu 15.** `isRunning()==true` có chứng minh broker đang giao message tốt không?

**Đáp án:** Không. Cần broker metrics, connection/recovery state và business processing counters.

**Câu 16.** `spring.lifecycle.timeout-per-shutdown-phase=40s` bảo đảm gì?

**Đáp án:** Nó là ngân sách chờ lifecycle stop theo phase ở Spring; không buộc orchestrator kéo dài grace period và không bảo đảm handler finish trong 40s.

**Câu 17.** Có thể gọi `shutdown()` trên container registry-managed để pause rồi `start()` không?

**Đáp án:** Không nên. Shutdown đóng resources/vòng đời; để pause/resume dùng stop/start.

**Câu 18.** Hai lần `stop(callback)` gọi liên tiếp có cả hai callback không?

**Đáp án:** Không được bảo đảm. DMLC có thể ghi đè callback cũ trước processing stop; start sớm cũng có thể hủy callback.

**Câu 19.** Khi stop, queue depth tăng. Đây có chắc là lỗi container không?

**Đáp án:** Không. Producer vẫn gửi, consumer dừng thì queue backlog tăng theo cơ chế broker thông thường.

**Câu 20.** Chỉ số nào quan trọng hơn một cờ isRunning duy nhất?

**Đáp án:** Handler in-flight, commits/rollbacks, broker active consumers, queue depth/oldest age, redelivery, DLQ, throughput và business event IDs.

**Câu 21.** Tại sao phải xét `terminationGracePeriodSeconds` ở môi trường Kubernetes?

**Đáp án:** Nếu deadline kill cứng ngắn hơn thời gian drain và Spring lifecycle timeout, process có thể bị kill trước callback/JMS commit.

**Câu 22.** Khi producer tiếp tục publish mạnh, bật `acceptMessagesWhileStopping(true)` có luôn tốt không?

**Đáp án:** Không. Nó có thể tiếp tục nhận/processing trong stopping phase, làm khó dự đoán drain deadline.

## Kết luận

Vòng đời `DefaultMessageListenerContainer` phải được hiểu qua **ba lớp độc lập nhưng tương tác**:

1. **Spring lifecycle:** `initialize/start/stop/shutdown`, `SmartLifecycle` phases, registry endpoint ID, stop callbacks.
2. **JMS delivery:** received/ready/in-flight, ACK/transaction, commit/rollback, redelivery, queue/topic subscription behavior.
3. **Business execution:** handler I/O duration, DB transaction, side effects, idempotency, retry và timeouts.

**`stop()` không phải kill in-flight tasks; `shutdown()` không phải pause; `stop(Runnable)` giúp biết lúc processing dừng nhưng không phải chứng cứ exactly-once business completion.** Thiết kế dừng an toàn cần bounded drain, local JMS transaction hoặc phối hợp XA hợp lý, broker retry/DLQ, timeout cho business I/O, orchestrator grace period và idempotency.

### Tài liệu chính thức để đối chiếu

1. [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): polling consumers, scaling, auto recovery, stop callback, cache và receive timeout.
2. [Spring Framework – AbstractJmsListeningContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractJmsListeningContainer.html): `initialize/start/stop/shutdown/destroy`, `isActive/isRunning`, `autoStartup/phase`.
3. [Spring Framework – AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html): `acceptMessagesWhileStopping`, AUTO_ACK/CLIENT_ACK/transacted semantics và exception handling.
4. [Spring Framework – AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html): `receiveTimeout` và JMS polling lifecycle.
5. [Spring Framework – DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): factory settings cho DMLC.
6. [Spring Framework – JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): quản lý annotated listener containers, `getListenerContainer` và lifecycle.
7. [Spring Framework – Annotation-driven JMS Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, `@JmsListener`, factory/registry.
8. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): MessageListenerContainers, JMS acknowledgment, transactions và recovery.
9. [Spring Boot – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): web server lifecycle, `spring.lifecycle.timeout-per-shutdown-phase` và phiên bản Boot.
10. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS Session transactions, acknowledgments, queue/topic semantics, durable/shared subscriptions.
