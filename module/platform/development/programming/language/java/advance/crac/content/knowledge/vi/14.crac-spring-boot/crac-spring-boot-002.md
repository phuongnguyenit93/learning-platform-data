# Quan hệ giữa Lifecycle, SmartLifecycle và callback CRaC

Trong ứng dụng Spring Boot, nhiều thành phần cần được khởi động và dừng theo vòng đời của `ApplicationContext`: message listener, scheduler, consumer, connection manager và các worker nền. Spring cung cấp `Lifecycle` và `SmartLifecycle` để điều phối những thành phần này khi context được start, stop, refresh hoặc close. CRaC lại cung cấp một vòng đời khác ở cấp tiến trình: callback `beforeCheckpoint` chuẩn bị tài nguyên trước khi lưu ảnh trạng thái, còn `afterRestore` phục hồi tài nguyên khi tiến trình được khôi phục.

Hai cơ chế có thể phối hợp nhưng không đồng nhất. Spring quản lý trạng thái hoạt động của bean và thứ tự start/stop trong context. CRaC quản lý thời điểm checkpoint/restore của process. Một bean được tạo xong hoặc một `ApplicationContext` đã phát `ApplicationReadyEvent` không có nghĩa ứng dụng đã sẵn sàng cho checkpoint. Tương tự, restore thành công không có nghĩa mọi `SmartLifecycle` đã tự khởi động lại hoặc mọi dependency đã sẵn sàng.

Thiết kế phù hợp thường dùng CRaC `Resource` làm điểm điều phối, rồi giao việc dừng/khởi động các thành phần cho Spring `LifecycleProcessor` hoặc cho các component lifecycle cụ thể. Cần hiểu rõ hành vi của Spring Boot version đang dùng vì một số phiên bản có hỗ trợ CRaC tích hợp sẵn; tránh đăng ký thêm một coordinator trùng với cơ chế tự động của framework.

## 1. Ba vòng đời cần phân biệt

Một ứng dụng Spring Boot có ít nhất ba nhóm sự kiện/vòng đời liên quan:

| Cơ chế | Phạm vi | Sự kiện/callback tiêu biểu | Mục đích |
| --- | --- | --- | --- |
| Spring Bean lifecycle | Một bean trong container | Constructor, dependency injection, `@PostConstruct`, `InitializingBean`, `@PreDestroy`, `DisposableBean` | Khởi tạo và giải phóng object/bean. |
| Spring Context lifecycle | Các bean tham gia hoạt động cùng `ApplicationContext` | `Lifecycle.start()`, `Lifecycle.stop()`, `SmartLifecycle`, `LifecycleProcessor.onRefresh()`, `LifecycleProcessor.onClose()` | Start/stop service, worker và tài nguyên được quản lý bởi context. |
| CRaC process lifecycle | Tiến trình JVM được checkpoint/restore | `Resource.beforeCheckpoint(...)`, `Resource.afterRestore(...)` | Chuẩn bị trạng thái process trước checkpoint và phục hồi sau restore. |

Không nên dùng callback của một vòng đời thay cho vòng đời khác. Ví dụ, `@PreDestroy` phục vụ lúc bean bị hủy; nó không phải callback checkpoint. `ContextClosedEvent` phát khi Spring context đóng; CRaC checkpoint không mặc nhiên đóng `ApplicationContext`. `afterRestore` là callback của CRaC; nó không tự động chạy lại constructor hoặc `@PostConstruct` của các bean đã tồn tại trong heap.

## 2. Spring Bean lifecycle không phải CRaC lifecycle

Khi Spring tạo bean, container thường thực hiện chuỗi bước như sau:

```text
Tạo instance
    |
    v
Inject dependencies
    |
    v
BeanPostProcessor trước initialization
    |
    v
@PostConstruct / afterPropertiesSet / init-method
    |
    v
BeanPostProcessor sau initialization
    |
    v
Bean sẵn sàng trong ApplicationContext
```

Khi context đóng, Spring có thể gọi các callback hủy bean:

```text
ApplicationContext close
        |
        v
LifecycleProcessor dừng Lifecycle beans
        |
        v
ContextClosedEvent
        |
        v
@PreDestroy / DisposableBean.destroy / destroy-method
        |
        v
BeanFactory được đóng
```

Chi tiết thứ tự có thể phụ thuộc loại context và phiên bản framework, nhưng điểm cần nhớ là callback hủy bean gắn với việc bean/context thực sự bị đóng.

Trong một CRaC checkpoint bình thường, mục tiêu là giữ lại `ApplicationContext` và các bean để tiếp tục sử dụng sau restore. Vì vậy:

- `@PostConstruct` không tự chạy lại sau restore.
- Constructor và dependency injection không được thực hiện lại chỉ vì process được restore.
- `@PreDestroy` không tự chạy chỉ vì CRaC chuẩn bị checkpoint.
- Không gọi `applicationContext.close()` trong `beforeCheckpoint` nếu mục tiêu là restore chính context đã checkpoint; close sẽ đi vào đường hủy bean và đóng context.
- Tài nguyên cần đóng/mở lại qua checkpoint nên có lifecycle riêng hoặc được điều phối bằng `Lifecycle`/`SmartLifecycle` và CRaC `Resource`.

Nếu một bean chứa socket, scheduler hoặc connection pool, việc bean object vẫn tồn tại sau restore không chứng minh tài nguyên bên trong còn hoạt động. Hãy tách vòng đời object khỏi vòng đời tài nguyên mà object quản lý.

## 3. `Lifecycle`: start và stop theo Spring Context

`org.springframework.context.Lifecycle` là hợp đồng đơn giản cho component có thể được start và stop:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Một bean triển khai `Lifecycle` có thể quản lý worker hoặc listener:

```java
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public final class BackgroundWorker implements Lifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }
        startWorkerThread();
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        requestWorkerStop();
        awaitWorkerWithTimeout();
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    private void startWorkerThread() { /* application-specific */ }
    private void requestWorkerStop() { /* application-specific */ }
    private void awaitWorkerWithTimeout() { /* bounded wait */ }
}
```

`Lifecycle` chỉ mô tả start/stop; nó không định nghĩa thứ tự phụ thuộc phức tạp, tự động start hay callback hoàn tất bất đồng bộ. Những nhu cầu đó được mở rộng bởi `SmartLifecycle`.

Các lời gọi start/stop từ `ApplicationContext` được điều phối thông qua `LifecycleProcessor`. Thông thường, ứng dụng không cần tự tìm từng bean rồi gọi `start()`/`stop()` thủ công nếu Spring đã quản lý chúng trong context.

## 4. `SmartLifecycle`: tự động start, phase và stop bất đồng bộ

`SmartLifecycle` mở rộng `Lifecycle` với các khả năng quan trọng:

- `isAutoStartup()` quyết định bean có tự động start khi context refresh hay không.
- `getPhase()` xác định thứ tự start/stop tương đối giữa các component.
- `stop(Runnable callback)` cho phép component báo cho Spring biết khi thao tác stop bất đồng bộ đã hoàn tất.

Một skeleton minh họa:

```java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class MessageConsumerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (!running) {
            startConsumer();
            running = true;
        }
    }

    @Override
    public void stop() {
        stopConsumerWithTimeout();
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        stopConsumerWithTimeout();
        running = false;
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    private void startConsumer() { /* application-specific */ }
    private void stopConsumerWithTimeout() { /* bounded drain and stop */ }
}
```

Ví dụ trên chỉ minh họa API. Nếu `stopConsumerWithTimeout()` thất bại, callback không được gọi như thể consumer đã dừng thành công. Cần ghi nhận lỗi và để lifecycle coordinator phát hiện việc stop không đạt yêu cầu; tùy implementation, exception có thể được truyền lên hoặc thao tác có thể timeout theo chính sách của Spring. Với implementation bất đồng bộ, chỉ gọi callback sau khi thao tác stop thực sự hoàn tất.

### Phase điều khiển thứ tự

Spring dùng phase để điều phối các `SmartLifecycle`:

- Component có phase thấp hơn được start trước.
- Khi stop, thứ tự đảo ngược: phase cao hơn được stop trước.
- Các component cùng phase có thể được xử lý cùng nhóm; không nên dựa vào thứ tự đăng ký bean như một hợp đồng phụ thuộc.

Ví dụ service phụ thuộc database pool:

```text
Startup (phase tăng dần)

DatabasePoolLifecycle       phase 10  -> start trước
MessageConsumerLifecycle    phase 20  -> start sau
RequestSchedulerLifecycle   phase 30  -> start cuối

Shutdown/checkpoint stop (phase giảm dần)

RequestSchedulerLifecycle   phase 30  -> stop trước
MessageConsumerLifecycle    phase 20  -> stop tiếp
DatabasePoolLifecycle       phase 10  -> stop cuối
```

Nhờ đó, scheduler dừng tạo việc mới trước consumer; consumer hoàn tất việc đang xử lý trước khi database pool đóng. Chọn phase theo dependency thật của ứng dụng. Không dùng phase như một cách thay thế cho việc drain request hoặc transaction.

## 5. `LifecycleProcessor` và `ApplicationContext`

`LifecycleProcessor` là thành phần điều phối các bean triển khai `Lifecycle`. `ConfigurableApplicationContext` cung cấp `getLifecycleProcessor()` để truy cập processor của context.

Hai phương thức liên quan:

| Phương thức | Ý nghĩa |
| --- | --- |
| `onRefresh()` | Thông báo context đã refresh để lifecycle processor khởi động các component cần auto-start theo quy tắc Spring. |
| `onClose()` | Thông báo giai đoạn context close để lifecycle processor dừng các component đang chạy theo thứ tự phase. |

Điểm quan trọng: gọi trực tiếp `LifecycleProcessor.onClose()` chỉ nhằm điều phối việc stop các lifecycle component; nó không tương đương với gọi `ApplicationContext.close()` và không phải lệnh hủy toàn bộ bean factory. Tuy nhiên, tên `onClose()` được thiết kế cho close phase của context, nên khi dùng trong CRaC cần có một coordinator sở hữu rõ ràng việc stop/start và phải xác nhận hành vi với phiên bản Spring đang dùng.

Nếu ứng dụng gọi `onClose()` trong `beforeCheckpoint`, sau restore có thể gọi `onRefresh()` để khởi động lại các component được cấu hình auto-start. Các bean `SmartLifecycle` có `isAutoStartup() == false` sẽ không tự động được start chỉ vì `onRefresh()`; chúng cần được điều khiển theo chính sách riêng. Với bean chỉ triển khai `Lifecycle`, hãy kiểm tra cách context/processor đang quản lý trạng thái của nó và không giả định mọi component đều được tự start lại.

Không gọi `applicationContext.close()` rồi kỳ vọng `onRefresh()` mở lại cùng context. Khi close thật, bean factory và singleton có thể đã bị hủy; đây là một vòng đời khác với stop/start phục vụ checkpoint.

## 6. CRaC `Resource`: vòng đời ở cấp tiến trình

CRaC cung cấp `org.crac.Resource` với hai callback chính:

```java
public interface Resource {
    void beforeCheckpoint(Context<? extends Resource> context) throws Exception;
    void afterRestore(Context<? extends Resource> context) throws Exception;
}
```

`beforeCheckpoint` được gọi trong quá trình chuẩn bị checkpoint. Đây là lúc ứng dụng dừng công việc mới, drain worker/transaction, đóng hoặc chuẩn bị lại các tài nguyên không thể tiếp tục qua checkpoint.

`afterRestore` được gọi khi process được khôi phục. Đây là lúc làm mới endpoint/credential, tạo lại connection pool, khởi động component đã dừng và xác nhận readiness.

`Resource` không thay thế `Lifecycle` hoặc `SmartLifecycle`. Nó cung cấp điểm móc vào chu kỳ CRaC để ứng dụng điều phối các lifecycle component phù hợp. Nếu mọi component tự đăng ký một Resource riêng rồi đồng thời được Spring LifecycleProcessor quản lý, cùng một worker có thể bị stop hai lần hoặc start theo thứ tự không mong muốn.

Một mô hình rõ ràng:

```text
CRaC Resource coordinator
        |
        +--> Spring LifecycleProcessor
        |        |
        |        +--> Scheduler SmartLifecycle
        |        +--> Message consumer SmartLifecycle
        |        +--> Database pool Lifecycle
        |
        +--> Refresh credential/configuration
        +--> Validate dependencies
        +--> Publish readiness
```

Trong mô hình này, CRaC điều khiển mốc thời gian; Spring quản lý thứ tự start/stop của các bean; ứng dụng quản lý việc refresh và readiness.

## 7. Điều phối Spring Lifecycle từ một CRaC Resource

Nếu Spring Boot version và dependency hiện tại không cung cấp tích hợp CRaC tự động cho lifecycle của ứng dụng, có thể tạo một singleton bean triển khai `Resource` để điều phối context.

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.crac.Core;
import org.crac.Context;
import org.crac.Resource;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.LifecycleProcessor;
import org.springframework.stereotype.Component;

@Component
public final class SpringLifecycleCracResource implements Resource {
    private final ConfigurableApplicationContext applicationContext;
    private boolean registered;

    public SpringLifecycleCracResource(
            ConfigurableApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
        registered = true;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        LifecycleProcessor processor = applicationContext.getLifecycleProcessor();
        processor.onClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        LifecycleProcessor processor = applicationContext.getLifecycleProcessor();
        processor.onRefresh();
    }

    @PreDestroy
    public void unregister() {
        if (registered) {
            Core.getGlobalContext().unregister(this);
            registered = false;
        }
    }
}
```

Đây là ví dụ điều phối cơ bản, không phải cấu hình dùng được nguyên trạng cho mọi ứng dụng. Cần cân nhắc các điểm sau:

- `SpringLifecycleCracResource` phải là bean singleton còn sống trong suốt vòng đời cần checkpoint; `ApplicationContext` giữ bean và bean giữ context.
- Đăng ký Resource đúng một lần. Nếu Spring Boot version đang dùng đã tự đăng ký lifecycle integration, không thêm coordinator trùng lặp.
- `onClose()` điều phối stop các Lifecycle bean; không gọi `applicationContext.close()`.
- `onRefresh()` khởi động các component theo semantics của Spring; kiểm tra những bean có `isAutoStartup() == false`.
- Cần xử lý readiness riêng. Việc `onRefresh()` trả về không chứng minh database, broker hoặc dependency bên ngoài đã khỏe.
- Các thao tác stop/start phải có timeout. Với `SmartLifecycle.stop(Runnable)`, component phải gọi callback khi thật sự dừng xong.
- Nếu `beforeCheckpoint` thất bại sau khi một số component đã dừng, coordinator phải có logic rollback/restart thích hợp.
- Không dựa vào `afterRestore` như callback rollback cho checkpoint bị abort. Nếu checkpoint không hoàn tất và process ban đầu tiếp tục, ứng dụng cần một đường phục hồi riêng theo semantics của runtime.

`@PreDestroy` trong ví dụ chỉ unregister Resource khi Spring thật sự hủy bean. Nó không được gọi thay cho `beforeCheckpoint`.

## 8. Khi nào nên điều khiển từng SmartLifecycle thay vì cả context?

Gọi `LifecycleProcessor.onClose()` có phạm vi rộng: nó có thể dừng nhiều lifecycle bean trong context. Cách này phù hợp khi toàn bộ các component đó cần dừng trước checkpoint và được phép tự khởi động lại sau restore.

Nếu chỉ một số tài nguyên cần đóng/mở lại, có thể để CRaC Resource gọi một coordinator chuyên biệt thay vì stop toàn bộ context:

```java
public final class MessagingCracResource implements Resource {
    private final MessageConsumerLifecycle consumer;

    public MessagingCracResource(MessageConsumerLifecycle consumer) {
        this.consumer = consumer;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        consumer.stop();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        consumer.start();
    }
}
```

Ví dụ chỉ phù hợp khi component có API stop/start đồng bộ, idempotent và đã có timeout. Nếu component triển khai `SmartLifecycle` và đang được `LifecycleProcessor` điều khiển, không nên gọi trực tiếp `stop()` ở Resource đồng thời với việc processor cũng stop nó. Hãy chọn một chủ sở hữu điều phối duy nhất.

Có thể tạo một `CheckpointCoordinator` riêng để phối hợp một nhóm bean theo thứ tự nghiệp vụ: dừng scheduler, drain consumer, flush outbox, đóng database pool; sau restore thì refresh credential, tạo pool, khởi động consumer rồi scheduler. Coordinator nên gọi API công khai của component hoặc Spring LifecycleProcessor thay vì gọi trực tiếp callback `beforeCheckpoint`/`afterRestore` của Resource khác.

## 9. Readiness và traffic trong chu kỳ checkpoint–restore

Spring lifecycle state và trạng thái sẵn sàng nhận traffic là hai khái niệm khác nhau. Một bean có `isRunning() == true` chưa chắc database đã kết nối được hoặc message broker đã sẵn sàng. Tương tự, một context đã refresh chưa chắc mọi dependency ngoài đã được kiểm tra.

Trong Spring Boot, có thể dùng Availability API để chuyển readiness state:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;

public final class ReadinessController {
    private final ConfigurableApplicationContext context;

    public ReadinessController(ConfigurableApplicationContext context) {
        this.context = context;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Một thứ tự hợp lý:

**Trước checkpoint**

1. Publish `REFUSING_TRAFFIC` để load balancer/orchestrator ngừng gửi request mới.
2. Dừng scheduler/consumer tạo thêm công việc.
3. Drain request, message và transaction đang chạy.
4. Stop lifecycle component theo phase.
5. Đóng/release connection pool và tài nguyên cần tái tạo.
6. Chỉ cho phép CRaC tiếp tục khi trạng thái ứng dụng đã an toàn.

**Sau restore**

1. Giữ readiness ở `REFUSING_TRAFFIC`.
2. Refresh credential, DNS, config và secret nếu có thể thay đổi.
3. Tạo lại connection pool/client và validate dependency.
4. Start lifecycle component theo thứ tự phase.
5. Xác nhận health check và trạng thái consumer/scheduler.
6. Publish `ACCEPTING_TRAFFIC` sau khi toàn bộ thành phần bắt buộc đã sẵn sàng.

Không publish `ACCEPTING_TRAFFIC` ngay đầu `afterRestore` chỉ để báo process đã sống. Readiness phải phản ánh khả năng phục vụ request thực tế.

## 10. Spring Boot events không thay thế CRaC callbacks

Một số event Spring Boot thường được dùng để quan sát trạng thái ứng dụng:

| Event | Khi nào phát | Có tự phát lại sau CRaC restore không? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Khi ApplicationContext được refresh | Không chỉ vì process restore. |
| `ApplicationReadyEvent` | Khi Spring Boot hoàn tất startup và sẵn sàng phục vụ theo startup flow | Không tự phát lại như một lần khởi động mới. |
| `ContextClosedEvent` | Khi ApplicationContext đóng | Không tự phát chỉ vì CRaC checkpoint. |
| `AvailabilityChangeEvent` | Khi ứng dụng thay đổi trạng thái availability/readiness | Chỉ phát khi ứng dụng hoặc framework publish. |
| CRaC `beforeCheckpoint` | Khi CRaC chuẩn bị checkpoint | Đây là callback CRaC, không phải Spring application event. |
| CRaC `afterRestore` | Khi CRaC khôi phục tiến trình | Đây là callback CRaC, không phải Spring startup event. |

Nếu logic refresh tài nguyên được gắn duy nhất vào `ApplicationReadyEvent`, nó có thể không chạy sau restore. Hãy đặt logic phục hồi vào CRaC Resource hoặc một lifecycle coordinator được gọi rõ ràng trong `afterRestore`.

Tương tự, không dùng `ContextClosedEvent` để giả lập checkpoint nếu không thực sự đóng context. Phát event thủ công cũng không tự thực hiện đầy đủ các bước stop, drain và resource cleanup.

## 11. Thứ tự phase và thứ tự CRaC Resource là hai thứ khác nhau

`SmartLifecycle.getPhase()` điều khiển thứ tự start/stop khi Spring LifecycleProcessor làm việc. Nó không điều khiển thứ tự callback của nhiều `org.crac.Resource` được đăng ký với CRaC `Context`.

Nếu ứng dụng đăng ký riêng từng bean làm CRaC Resource, không nên giả định thứ tự callback sẽ trùng với phase của SmartLifecycle. Điều này có thể tạo race: database pool đóng trước khi consumer drain xong, hoặc consumer khởi động trước khi credential refresh hoàn tất.

Khi cần thứ tự nghiệp vụ, dùng một coordinator duy nhất hoặc một chuỗi điều phối tường minh:

```text
beforeCheckpoint
    |
    v
Refuse traffic
    |
    v
Stop scheduler
    |
    v
Drain consumer and requests
    |
    v
Finish/rollback transactions
    |
    v
Close database and network clients
    |
    v
Checkpoint

afterRestore
    |
    v
Refresh secrets and endpoints
    |
    v
Create database/network clients
    |
    v
Start consumers
    |
    v
Start schedulers
    |
    v
Validate health and accept traffic
```

Trong mỗi bước, xác định rõ timeout, failure behavior và rollback. Không để callback của Resource A gọi trực tiếp callback của Resource B; gọi API lifecycle cấp ứng dụng để tránh callback lặp hoặc phá vỡ ownership.

## 12. Timeout khi Spring dừng SmartLifecycle

Một `SmartLifecycle` có thể stop bất đồng bộ. Khi Spring LifecycleProcessor chờ callback hoàn tất, một consumer bị treo hoặc một worker không drain có thể làm quá trình checkpoint chậm hoặc bị kẹt.

Spring Boot cung cấp cấu hình `spring.lifecycle.timeout-per-shutdown-phase` để giới hạn thời gian chờ mỗi phase khi lifecycle processor dừng component. Cần chọn giá trị phù hợp với thời gian drain và yêu cầu vận hành. Đây là timeout theo phase của Spring; nó không tự giới hạn mọi network call, database query hoặc thao tác CRaC dump.

Các nguyên tắc:

- `stop(Runnable)` phải gọi callback khi component thực sự hoàn tất stop.
- Không chờ vô hạn `Future.get()`, `Thread.join()` hoặc `CountDownLatch.await()` trong stop logic.
- Cấu hình timeout riêng cho HTTP, database, broker và I/O; timeout per phase không thay thế timeout ở client.
- Nếu component không dừng trong hạn, không báo thành công giả. Để coordinator biết checkpoint preparation không an toàn.
- Không giữ application lock trong khi chờ worker hoặc gọi network.
- Log duration, phase, component name và số task còn hoạt động khi stop.

## 13. Xử lý lỗi và checkpoint bị abort

Giả sử `beforeCheckpoint` đã gọi `LifecycleProcessor.onClose()` và dừng tất cả worker. Nếu một bước chuẩn bị tiếp theo thất bại, process ban đầu có thể cần tiếp tục phục vụ traffic. Ứng dụng phải có kế hoạch đưa component về trạng thái hoạt động an toàn hoặc giữ readiness ở `REFUSING_TRAFFIC`.

Không dùng `afterRestore` như callback rollback cho một checkpoint bị abort. `afterRestore` thuộc luồng restore; checkpoint failure không đồng nghĩa một restore mới đã diễn ra. Cần xử lý lỗi ngay trong coordinator khi có thể, và hiểu semantics cụ thể của runtime khi thao tác dump thất bại sau khi callback chuẩn bị đã hoàn tất.

Một state machine có thể dùng:

```text
RUNNING
   |
   v
REFUSING_TRAFFIC
   |
   v
QUIESCING
   |
   v
STOPPING_LIFECYCLE
   |
   +---- preparation error ----> ROLLING_BACK
   |                                  |
   |                                  v
   |                           RUNNING or NOT_READY
   |
   v
READY_FOR_CHECKPOINT
   |
   v
CHECKPOINT
   |
   v
RESTORE
   |
   v
RECONNECTING
   |
   v
STARTING_LIFECYCLE
   |
   v
READY
```

Rollback phải biết component nào đã dừng và component nào chưa. `SmartLifecycle.start()` cần idempotent hoặc coordinator cần theo dõi state để không start hai lần. Nếu không thể phục hồi đầy đủ, giữ readiness ở trạng thái từ chối traffic và báo lỗi cho orchestration.

## 14. Spring Boot có tích hợp CRaC sẵn hay không?

Khả năng tích hợp phụ thuộc phiên bản Spring Boot, Spring Framework, CRaC JDK và dependency trên classpath. Một số phiên bản Spring Boot có hỗ trợ CRaC tích hợp để điều phối lifecycle của ứng dụng. Trước khi tự viết `Resource`, cần kiểm tra tài liệu đúng phiên bản và xác nhận framework đang tự động làm những bước nào.

Quy trình quyết định:

1. Xác nhận version Spring Boot và Spring Framework thực tế.
2. Xác nhận dependency CRaC (`org.crac`) và runtime JDK được hỗ trợ.
3. Đọc tài liệu CRaC của đúng phiên bản Boot để biết lifecycle component nào được stop/start tự động.
4. Kiểm tra có auto-configuration hoặc Resource do framework đăng ký hay không.
5. Chỉ bổ sung custom Resource cho phần ứng dụng chưa được framework quản lý.
6. Tránh gọi `LifecycleProcessor.onClose()` lần nữa nếu framework đã thực hiện tương đương.
7. Kiểm thử log callback để xác nhận mỗi component chỉ stop/start đúng số lần.

Không suy luận rằng chỉ cần thêm `org.crac:crac` là mọi resource tùy chỉnh tự được xử lý. Framework có thể hỗ trợ lifecycle bean nhưng không hiểu cách đóng một client tự viết, refresh secret hoặc xác minh nghiệp vụ của ứng dụng.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `@PreDestroy` không chạy lúc checkpoint | Checkpoint không đóng ApplicationContext và không hủy bean | Dùng `Resource.beforeCheckpoint` hoặc Lifecycle stop cho resource cần chuẩn bị. |
| `@PostConstruct` không chạy sau restore | Bean đã tồn tại trong ảnh; restore không tạo lại bean | Đưa việc phục hồi tài nguyên vào `afterRestore` hoặc lifecycle coordinator. |
| Consumer bị stop hai lần | Vừa có Boot CRaC integration vừa có custom Resource gọi processor | Xác định một chủ sở hữu lifecycle, bỏ điều phối trùng. |
| Consumer không start lại | `isAutoStartup()` false hoặc coordinator chỉ gọi `onRefresh()` | Start component theo chính sách riêng hoặc cấu hình autoStartup phù hợp. |
| Database pool start trước consumer drain xong | Dựa vào thứ tự Resource callback thay vì Spring phase/coordinator | Dùng phase hoặc trình tự điều phối tường minh. |
| Checkpoint treo khi stop | `stop(Runnable)` không gọi callback hoặc task không có timeout | Bổ sung bounded wait, cancellation và log thời gian stop. |
| Ứng dụng nhận traffic quá sớm sau restore | Readiness được bật ngay khi process sống hoặc ngay khi gọi start | Chỉ publish `ACCEPTING_TRAFFIC` sau khi dependency và health check đạt. |
| Context không hoạt động sau restore | Đã gọi `ApplicationContext.close()` trước checkpoint | Không đóng context; chỉ stop lifecycle/resource cần thiết. |
| Checkpoint bị abort nhưng worker vẫn dừng | Không có rollback cho preparation đã hoàn tất | Coordinator theo dõi component state và restart/resume an toàn. |
| Spring event handler không chạy sau restore | Logic chỉ gắn vào `ApplicationReadyEvent` hoặc `ContextRefreshedEvent` | Gọi logic phục hồi rõ ràng từ CRaC callback. |

## 16. Kiểm thử quan hệ giữa Spring Lifecycle và CRaC

Kiểm thử cần xác nhận cả thứ tự callback lẫn trạng thái hoạt động của ứng dụng.

### Kiểm thử Spring Lifecycle độc lập

1. Khởi tạo `ApplicationContext`.
2. Xác nhận `SmartLifecycle` auto-start bean được start theo phase.
3. Gửi stop qua lifecycle processor và xác nhận thứ tự stop đảo ngược.
4. Xác nhận `stop(Runnable)` chỉ báo hoàn tất sau khi component thực sự dừng.
5. Kiểm tra `isAutoStartup() == false` không tự start ngoài ý muốn.

### Kiểm thử CRaC tích hợp

1. Khởi động ứng dụng trên JDK/CRaC tương thích.
2. Xác nhận readiness đang `ACCEPTING_TRAFFIC` và các lifecycle component hoạt động.
3. Yêu cầu checkpoint.
4. Xác nhận readiness chuyển sang `REFUSING_TRAFFIC`, scheduler dừng, consumer drain và pool đóng theo đúng trình tự.
5. Restore từ checkpoint.
6. Xác nhận resource được refresh, pool được tạo lại và lifecycle component được start đúng một lần.
7. Xác nhận readiness chỉ chuyển sang `ACCEPTING_TRAFFIC` sau health check.
8. Gửi request và message thử để xác nhận ứng dụng thực sự hoạt động.

### Kiểm thử lỗi

- Consumer không drain trước timeout.
- `SmartLifecycle.stop(Runnable)` không gọi callback.
- Một component stop thành công nhưng component tiếp theo thất bại.
- Credential hoặc database chưa sẵn sàng sau restore.
- Checkpoint bị abort sau khi lifecycle component đã dừng.
- Restore lặp lại hoặc một component nhận yêu cầu start khi đã running.
- Boot integration và custom Resource cùng hiện diện để phát hiện stop/start trùng.

Kiểm thử unit cho phase và state machine hữu ích, nhưng cần kiểm thử checkpoint/restore thực tế trên JDK và môi trường CRaC triển khai. Chỉ gọi trực tiếp `beforeCheckpoint()`/`afterRestore()` không chứng minh runtime đã tạo hoặc khôi phục được process image.

## 17. Checklist thiết kế

- [ ] Phân biệt bean initialization/destruction, Spring context lifecycle và CRaC process lifecycle.
- [ ] Không dùng `@PreDestroy` như callback checkpoint.
- [ ] Không dùng `@PostConstruct` như callback restore.
- [ ] Không gọi `ApplicationContext.close()` nếu cần tiếp tục dùng cùng context sau restore.
- [ ] Mỗi lifecycle component có một chủ sở hữu start/stop rõ ràng.
- [ ] Dùng `SmartLifecycle` phase để thể hiện dependency start/stop.
- [ ] `stop(Runnable)` chỉ báo hoàn tất sau khi component dừng thực sự.
- [ ] Có timeout cho mỗi phase và cho từng I/O/database/broker operation.
- [ ] Xác nhận Boot version có CRaC integration sẵn trước khi đăng ký Resource tùy chỉnh.
- [ ] Tránh đăng ký hai coordinator cùng stop/start một component.
- [ ] Dùng CRaC Resource để điều phối các bước trước checkpoint và sau restore.
- [ ] Refresh credential, endpoint và cấu hình có thể thay đổi trong thời gian checkpoint.
- [ ] Có rollback khi preparation thất bại hoặc checkpoint bị abort theo semantics runtime.
- [ ] Readiness từ chối traffic trong quá trình quiesce/reconnect.
- [ ] Chỉ chấp nhận traffic sau khi lifecycle component và dependency đã sẵn sàng.
- [ ] Kiểm thử thứ tự, timeout, lỗi stop/start và checkpoint/restore thực tế.

## 18. Kết luận

Spring Bean lifecycle quản lý việc tạo và hủy bean; `Lifecycle`/`SmartLifecycle` quản lý việc start và stop các component trong `ApplicationContext`; CRaC `Resource` quản lý thời điểm chuẩn bị checkpoint và phục hồi sau restore. Các cơ chế này bổ trợ cho nhau nhưng không tự thay thế nhau.

Hãy để Spring LifecycleProcessor điều phối các bean theo phase, dùng CRaC Resource làm điểm tích hợp cấp tiến trình, và quản lý readiness riêng để không nhận traffic khi resource chưa sẵn sàng. Xác nhận hỗ trợ CRaC tích hợp của đúng phiên bản Spring Boot trước khi tự đăng ký coordinator. Với cách phân chia trách nhiệm rõ ràng, ứng dụng có thể dừng worker, drain transaction, đóng tài nguyên trước checkpoint và khởi động lại đúng thứ tự sau restore mà không đóng/hủy ApplicationContext.
