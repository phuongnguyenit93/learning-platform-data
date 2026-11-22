# Ứng dụng không thoát hoặc không dọn tài nguyên sau khi đóng context

Một ứng dụng Spring Boot có thể đã xử lý xong công việc nhưng tiến trình Java vẫn không kết thúc. Một trường hợp khác là context đã đóng nhưng một số thread, socket, scheduler hoặc client connection vẫn còn hoạt động. Cũng có trường hợp ứng dụng nhận tín hiệu dừng nhưng không hoàn tất việc đóng tài nguyên trước khi hệ điều hành kết thúc process.

Để chẩn đoán đúng, cần tách ba câu hỏi:

1. **Spring ApplicationContext đã đóng chưa?**
2. **Các tài nguyên do ứng dụng quản lý đã được giải phóng chưa?**
3. **JVM process đã kết thúc chưa?**

Ba trạng thái này liên quan nhưng không đồng nhất. `ApplicationContext.close()` đóng lifecycle của Spring context; nó không tự động kết thúc mọi thread hoặc tài nguyên được tạo bên ngoài container. Ngược lại, JVM có thể kết thúc khi không còn non-daemon thread, kể cả khi một ứng dụng command-line chưa chủ động đóng context theo cách mong muốn.

Bài học này giải thích lifecycle khi shutdown, các callback dọn dẹp của Spring, non-daemon threads, executor và background jobs, graceful shutdown, cách xử lý signal từ container, cách đọc thread dump và những mẫu thiết kế giúp ứng dụng đóng sạch sẽ.

> **Nguyên tắc:** mỗi tài nguyên phải có một chủ sở hữu rõ ràng, một thời điểm bắt đầu và một cơ chế đóng tương ứng. Đừng dựa vào việc JVM tự kết thúc để thay thế cleanup có chủ đích.

## 1. Phân biệt đóng context, đóng tài nguyên và kết thúc JVM

Giả sử ứng dụng khởi động:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);
```

Sau đó bạn gọi:

```java
context.close();
```

Spring bắt đầu đóng ApplicationContext. Container phát lifecycle events phù hợp, dừng những bean có lifecycle được quản lý và gọi các destroy callbacks của singleton beans.

Nhưng process có thể vẫn tồn tại:

```text
Spring ApplicationContext
        |
        | close()
        v
Context lifecycle đóng
        |
        +--> Spring-managed beans được destroy
        |
        +--> Một số executor được shutdown
        |
        +--> Embedded server được dừng
        |
        v
JVM vẫn còn hoạt động?
        |
        +--> Có non-daemon thread khác -> JVM tiếp tục chạy
        |
        +--> Không còn non-daemon thread -> JVM có thể kết thúc
```

### 1.1. Ba trạng thái không nên đánh đồng

| Trạng thái | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| Context active | Spring container còn hoạt động | `context.isActive()` |
| Context closed | Container đã thực hiện close lifecycle | `context.isActive()` trả `false`, `ContextClosedEvent` |
| Resource closed | Socket, pool, executor, client... đã được đóng | API/trạng thái riêng của từng resource |
| JVM terminated | Tiến trình Java đã kết thúc | Process manager, PID, container status |

Ví dụ, `context.isActive()` trả `false` không chứng minh một thread tự tạo đã dừng. Tương tự, `executor.isShutdown()` chưa chứng minh mọi task đã hoàn tất; cần phân biệt `isShutdown()` và `isTerminated()`.

### 1.2. Vì sao context đóng nhưng JVM vẫn sống?

Những nguyên nhân phổ biến:

- Một thread được tạo bằng `new Thread(...)` vẫn chạy.
- Một `ExecutorService` không được shutdown.
- Một scheduler hoặc timer không được dừng.
- Một thư viện native/client tạo thread nền riêng.
- Một listener hoặc consumer đang chờ message.
- Một thread bị block vô thời hạn trên I/O, lock hoặc queue.
- Một non-daemon thread được tạo trong static initializer hoặc code không do Spring quản lý.

### 1.3. Vì sao JVM kết thúc nhưng cleanup không đầy đủ?

Nguyên nhân có thể là:

- Tài nguyên được tạo thủ công nhưng không có destroy callback.
- Shutdown callback bị lỗi hoặc timeout.
- Process bị `SIGKILL`, container runtime cưỡng chế dừng hoặc máy bị tắt đột ngột.
- Code gọi `Runtime.halt(...)`, bỏ qua shutdown hooks.
- Một callback cleanup không chờ tác vụ bất đồng bộ hoàn tất.
- Ứng dụng phụ thuộc vào một resource mà lifecycle của nó chưa được quản lý.

Vì vậy, chẩn đoán cần xác định **context đã đóng đến đâu, tài nguyên nào còn sống và process kết thúc theo cơ chế nào**.

## 2. Spring ApplicationContext có thể được đóng như thế nào?

`ApplicationContext` là abstraction đọc bean và quản lý dependency. Để chủ động đóng context, Spring cung cấp `ConfigurableApplicationContext`.

### 2.1. Đóng bằng `close()`

```java
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);

// Khi công việc của ứng dụng đã hoàn tất:
context.close();
```

`close()` yêu cầu Spring đóng context và giải phóng các singleton beans do container quản lý theo lifecycle.

Phương thức này có thể gọi lại sau khi context đã đóng mà không yêu cầu bạn tự destroy từng bean.

### 2.2. `ApplicationContext` và `ConfigurableApplicationContext`

Nếu biến chỉ có kiểu:

```java
ApplicationContext context;
```

thì abstraction này không công bố phương thức `close()`.

Khi cần điều khiển lifecycle, dùng kiểu:

```java
ConfigurableApplicationContext context;
```

Đừng ép kiểu tùy tiện một context bất kỳ nếu bạn không biết implementation có hỗ trợ lifecycle interface tương ứng.

### 2.3. `SpringApplication.run()` trả về context

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(OrdersApplication.class, args);
}
```

Với một web application, method `main` thường kết thúc sau khi Spring Boot khởi động nhưng JVM vẫn chạy vì embedded web server và những thread nền cần thiết.

Với một ứng dụng non-web, khi main kết thúc và không còn non-daemon thread, JVM có thể bắt đầu shutdown. Spring Boot mặc định đăng ký shutdown hook để đóng context trong quá trình JVM shutdown, trừ khi cơ chế đó bị tắt hoặc được thay đổi.

### 2.4. `SpringApplication.exit(...)`

Với một ứng dụng command-line cần kết thúc sau khi hoàn thành công việc:

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(BatchApplication.class, args);

    int exitCode = SpringApplication.exit(context);
    System.exit(exitCode);
}
```

`SpringApplication.exit(context)` thu thập exit code từ các `ExitCodeGenerator` phù hợp và đóng context. `System.exit(exitCode)` yêu cầu JVM kết thúc với exit code đó, sau khi JVM bắt đầu quy trình shutdown.

**Không gọi mẫu này cho một web server cần tiếp tục phục vụ request.** Nó phù hợp với một tiến trình batch/CLI đã hoàn thành nhiệm vụ.

### 2.5. Không dùng `System.exit()` trong service hoặc controller

Không nên:

```java
@Service
public class OrderService {

    public void submit() {
        // ...
        System.exit(0);
    }
}
```

`System.exit()` kết thúc toàn bộ JVM, không chỉ method hoặc request hiện tại. Một service không nên tự quyết định kết thúc process dùng chung.

Để kết thúc ứng dụng có chủ đích, hãy để lớp điều khiển ở entry point hoặc process supervisor chịu trách nhiệm lifecycle.

## 3. Shutdown hook của JVM và Spring Boot

JVM hỗ trợ **shutdown hooks**: những thread được đăng ký để chạy khi runtime bắt đầu shutdown theo các cơ chế kết thúc bình thường.

Spring Boot thường đăng ký shutdown hook để đóng ApplicationContext khi JVM shutdown.

### 3.1. JVM shutdown hook là gì?

Ví dụ Java thuần:

```java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.out.println("JVM is shutting down");
        })
);
```

Hook trên được gọi khi JVM bắt đầu quá trình shutdown bình thường, ví dụ do `System.exit(...)` hoặc tín hiệu kết thúc mà JVM xử lý như shutdown.

### 3.2. Shutdown hook không chạy trong mọi kiểu kết thúc

Không nên coi hook là cơ chế bảo đảm cleanup tuyệt đối. Hook có thể không chạy khi:

- Process bị kill cưỡng chế như `SIGKILL`.
- Máy hoặc container host bị tắt đột ngột.
- JVM gặp một số lỗi nghiêm trọng không thể thực hiện shutdown bình thường.
- Code gọi `Runtime.getRuntime().halt(...)`.
- Một cơ chế bên ngoài kết thúc process mà không cho JVM thực hiện shutdown sequence.

Trong Kubernetes, container runtime có thể gửi `SIGTERM`, chờ thời gian grace period rồi gửi `SIGKILL` nếu process chưa thoát. Cleanup phải hoàn thành trong khoảng thời gian được cấp.

### 3.3. Không tạo shutdown hook cho từng bean

Spring đã có lifecycle callbacks cho bean. Nếu mọi bean tự đăng ký một JVM shutdown hook, ứng dụng sẽ có nhiều hook độc lập, khó kiểm soát thứ tự và thời gian dừng.

Với resource thuộc một Spring bean, ưu tiên:

- `@PreDestroy`.
- `DisposableBean`.
- `@Bean(destroyMethod = "...")`.
- `Lifecycle` hoặc `SmartLifecycle`.

Dùng JVM shutdown hook cho logic ở cấp process khi thật sự cần; để Spring quản lý lifecycle của bean.

### 3.4. `spring.main.register-shutdown-hook`

Spring Boot cung cấp property:

```properties
spring.main.register-shutdown-hook=true
```

Thiết lập này điều khiển việc đăng ký shutdown hook của SpringApplication. Trong thiết lập thông thường, hook được đăng ký mặc định.

Nếu đặt:

```properties
spring.main.register-shutdown-hook=false
```

ứng dụng phải có một cơ chế khác chủ động đóng context khi process shutdown. Không tắt hook chỉ để tránh một lỗi cleanup chưa được điều tra.

### 3.5. Hook không phải nơi chờ vô hạn

Một shutdown hook nên:

- Hoàn tất trong thời gian hữu hạn.
- Không chờ vô thời hạn một service đang mất kết nối.
- Không gọi `System.exit()` để tạo shutdown lồng nhau.
- Không giả định các hook khác đã chạy theo một thứ tự cụ thể.
- Có timeout và log chẩn đoán phù hợp.

JVM có thể chạy nhiều shutdown hooks đồng thời; không dựa vào thứ tự khởi chạy hook để sắp xếp dependency.

## 4. Các callback destroy của Spring

Spring hỗ trợ nhiều cách chỉ định việc dọn dẹp khi bean bị destroy.

### 4.1. `@PreDestroy`

Đây là cách phổ biến để đánh dấu method cleanup:

```java
package com.example.orders.worker;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class MessageWorker {

    private static final Logger log =
            LoggerFactory.getLogger(MessageWorker.class);

    @PreDestroy
    public void cleanup() {
        log.info("message.worker.cleanup.started");
        // Giải phóng resource do bean sở hữu
        log.info("message.worker.cleanup.completed");
    }
}
```

Với Spring Boot 3, annotation thường được import từ `jakarta.annotation.PreDestroy`. Các ứng dụng Spring Boot 2 cũ hơn có thể dùng `javax.annotation.PreDestroy` tùy dependency/version.

### 4.2. `DisposableBean`

Một bean có thể implement:

```java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class LegacyConnectionManager implements DisposableBean {

    @Override
    public void destroy() {
        // Đóng connection do bean quản lý
    }
}
```

`destroy()` được Spring gọi trong quá trình destroy bean.

Ưu điểm là rõ ràng qua interface; nhược điểm là class phụ thuộc trực tiếp vào Spring API. Nếu muốn giữ class nghiệp vụ ít phụ thuộc framework, `@PreDestroy` hoặc cấu hình `@Bean` có thể phù hợp hơn.

### 4.3. Custom destroy method trên `@Bean`

Khi bean được tạo bởi một `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Khi context đóng, Spring gọi method `close()` được chỉ định trên bean.

Đây là lựa chọn rõ ràng khi class thư viện cung cấp API `close()` hoặc `shutdown()` nhưng không mang annotation Spring.

### 4.4. Inferred destroy method

Spring hỗ trợ suy luận một số destroy method phổ biến cho bean được khai báo bằng `@Bean`, chẳng hạn method `close` hoặc `shutdown` trong những trường hợp phù hợp.

Tuy nhiên, nếu resource quan trọng, khai báo tường minh:

```java
@Bean(destroyMethod = "close")
```

giúp người đọc thấy rõ ai chịu trách nhiệm đóng.

### 4.5. Không gọi cleanup hai lần tùy tiện

Không nên vừa tự gọi `client.close()` trong business code, vừa để Spring gọi `destroyMethod="close"` khi context đóng mà không có thiết kế ownership rõ ràng.

Một resource nên có **một lifecycle owner**. Nếu một method có thể được gọi thủ công trước khi context đóng, cleanup cần idempotent hoặc có trạng thái đóng rõ ràng.

### 4.6. Thứ tự callback và dependency

Spring quản lý quan hệ phụ thuộc giữa bean khi destroy singleton. Những bean phụ thuộc vào một bean khác thường được destroy trước dependency mà chúng cần.

Không nên giả định thứ tự destroy giữa các bean không có quan hệ phụ thuộc. Nếu thứ tự quan trọng, hãy thể hiện quan hệ và lifecycle rõ ràng, hoặc dùng một coordinator quản lý shutdown.

## 5. `Lifecycle` và `SmartLifecycle`

Một số component cần **bắt đầu và dừng có thứ tự**, ví dụ message listener, scheduler hoặc một worker có thể nhận công việc từ bên ngoài.

Spring cung cấp:

```java
org.springframework.context.Lifecycle
org.springframework.context.SmartLifecycle
```

### 5.1. `Lifecycle`

Interface cơ bản:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Một component có thể triển khai để Spring gọi start/stop trong quá trình context lifecycle.

### 5.2. `SmartLifecycle`

`SmartLifecycle` bổ sung khả năng:

- Tự động start theo lifecycle.
- Chỉ định `phase`.
- Dừng bất đồng bộ qua callback `stop(Runnable callback)`.
- Xác định trạng thái đang chạy.

Ví dụ:

```java
package com.example.orders.worker;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class QueueConsumerLifecycle implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(QueueConsumerLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            log.info("queue.consumer.started");
            // Khởi động consumer hoặc bắt đầu nhận message
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                log.info("queue.consumer.stopping");
                // Ngừng nhận message mới và đóng resource phù hợp
            }
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> {
        });
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

Đây là skeleton lifecycle. Trong consumer thực tế, `stop()` phải yêu cầu client ngừng nhận message, chờ xử lý đang chạy theo timeout, commit/ack đúng chính sách và đóng connection.

### 5.3. Callback rất quan trọng

Trong `SmartLifecycle.stop(Runnable callback)`, Spring cần callback được gọi khi component **đã hoàn tất việc dừng**.

Nếu component quên gọi callback, lifecycle processor có thể phải chờ đến timeout. Nếu gọi callback quá sớm trong khi resource vẫn chạy, context có thể tiếp tục destroy dependency mà component còn sử dụng.

### 5.4. Phase và thứ tự start/stop

Spring sắp xếp lifecycle beans theo phase:

- Khi start, phase thấp thường được khởi động trước.
- Khi stop, thứ tự được đảo ngược; phase cao thường dừng trước.

Ví dụ:

```text
Start:
  Phase 0  -> connection infrastructure
  Phase 10 -> message consumer

Stop:
  Phase 10 -> message consumer dừng nhận việc
  Phase 0  -> connection infrastructure đóng sau
```

Đây là một lý do `SmartLifecycle` hữu ích khi thứ tự dừng phụ thuộc tài nguyên khác. Đặt phase theo dependency thực tế của ứng dụng, không chọn số tùy tiện.

### 5.5. Timeout cho lifecycle phase

Spring Boot có property:

```properties
spring.lifecycle.timeout-per-shutdown-phase=30s
```

Property này cấu hình thời gian chờ cho một shutdown phase của lifecycle processor theo phiên bản hỗ trợ.

Đặt timeout quá ngắn có thể khiến resource chưa dừng xong; đặt quá dài có thể làm process vượt thời gian grace period của container.

Không coi timeout là cơ chế tự sửa component bị treo. Component vẫn cần dừng có kiểm soát và gọi callback đúng lúc.

## 6. Tài nguyên nào cần được dọn dẹp?

Một ứng dụng Spring Boot có thể sở hữu nhiều loại resource:

| Resource | Việc cần làm khi shutdown |
| --- | --- |
| `ExecutorService` | Ngừng nhận task mới, chờ task đang chạy, đóng executor |
| `ThreadPoolTaskExecutor` | Dừng executor theo lifecycle đã cấu hình |
| `ThreadPoolTaskScheduler` | Dừng lịch và task đang chạy theo policy |
| `ScheduledExecutorService` | Cancel schedule và shutdown |
| `Timer` | Gọi `cancel()` |
| HTTP client | Đóng connection manager/client nếu API yêu cầu |
| JDBC pool | Đóng datasource/pool do ứng dụng sở hữu |
| Kafka/Rabbit consumer | Ngừng nhận message, xử lý/ack theo chính sách, đóng client |
| File stream | Đóng stream; ưu tiên try-with-resources cho phạm vi ngắn |
| Socket/server socket | Ngừng nhận kết nối và đóng socket |
| Database cursor/result set | Đóng sau khi dùng |
| Subscription/listener | Hủy đăng ký |
| Custom thread | Yêu cầu dừng, interrupt khi phù hợp và join/chờ hữu hạn |
| Native resource | Gọi API release tương ứng |
| Temporary files | Xóa nếu lifecycle và policy yêu cầu |

Không phải mọi object đều cần `@PreDestroy`. File stream dùng trong một method thường nên được đóng bằng try-with-resources ngay tại nơi mở.

## 7. Executor không được shutdown: nguyên nhân thường gặp

Một `ExecutorService` có thể tạo worker threads để thực thi task.

Ví dụ:

```java
ExecutorService executor =
        Executors.newFixedThreadPool(4);
```

Nếu worker threads là non-daemon và executor không được shutdown, JVM có thể tiếp tục chạy sau khi main method kết thúc hoặc Spring context đóng.

### 7.1. Ví dụ gây treo process

```java
public static void main(String[] args) {
    ExecutorService executor =
            Executors.newFixedThreadPool(2);

    executor.submit(() -> {
        while (true) {
            try {
                Thread.sleep(1000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    });

    System.out.println("Main completed");
}
```

Sau khi in `Main completed`, thread pool vẫn còn task đang chạy. Nếu executor không được shutdown, JVM có thể tiếp tục tồn tại.

### 7.2. `shutdown()` và `shutdownNow()` khác nhau

```java
executor.shutdown();
```

`shutdown()`:

- Ngừng nhận task mới.
- Cho task đã submit tiếp tục chạy.
- Không chờ mặc định cho tới khi tất cả task hoàn tất.

```java
executor.shutdownNow();
```

`shutdownNow()`:

- Yêu cầu dừng các task đang chạy bằng cách interrupt worker threads.
- Trả về danh sách task đang chờ chưa bắt đầu theo implementation.
- Không bảo đảm task đang chạy dừng ngay; task cần hợp tác với interrupt.

### 7.3. Chờ executor hoàn tất

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Ví dụ cần import `java.util.concurrent.TimeUnit`.

Luồng xử lý:

1. Ngừng nhận task mới.
2. Chờ task đang chạy hoàn tất trong khoảng thời gian hữu hạn.
3. Nếu hết thời gian, gửi interrupt.
4. Nếu thread đang cleanup bị interrupt, khôi phục interrupt status.

### 7.4. Interrupt không phải lệnh kill thread

`Thread.interrupt()` đặt trạng thái interrupt hoặc đánh thức một số blocking operations. Code của task phải hợp tác:

```java
while (!Thread.currentThread().isInterrupted()) {
    doOneUnitOfWork();
}
```

Nếu task nuốt `InterruptedException` rồi tiếp tục loop vô hạn, shutdown sẽ không kết thúc đúng hạn.

Không có API an toàn chung để cưỡng chế kill một Java thread đang chạy tùy ý. Hãy thiết kế task có điểm dừng và timeout.

## 8. Quản lý executor như một Spring bean

Nếu executor thuộc ứng dụng, hãy để Spring quản lý lifecycle thay vì tạo trong service rồi quên đóng.

### 8.1. Khai báo `ExecutorService` với destroy method

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService workerExecutor() {
        return Executors.newFixedThreadPool(4);
    }
}
```

Khi context đóng, Spring gọi `shutdown()` trên executor.

Tuy nhiên, `shutdown()` không tự chờ một thời gian hữu hạn để xác nhận mọi task đã hoàn tất. Nếu cần chờ và escalation, cấu hình một lifecycle component hoặc dùng executor của Spring với các thuộc tính shutdown phù hợp.

### 8.2. Dùng `ThreadPoolTaskExecutor`

```java
@Configuration(proxyBeanMethods = false)
public class TaskConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
```

`ThreadPoolTaskExecutor` được Spring quản lý lifecycle và có các thuộc tính hỗ trợ shutdown. Ví dụ đặt chờ task tối đa 20 giây trước khi hoàn tất shutdown theo hành vi của executor.

### 8.3. Lựa chọn chờ task hay hủy task

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ task đã submit hoàn tất trong quá trình shutdown theo cơ chế được hỗ trợ.

Nếu đặt `false`, executor có thể hủy task đang chờ và interrupt task đang chạy theo shutdown behavior của implementation.

Lựa chọn phụ thuộc:

- Task có idempotent không?
- Có thể retry sau khi process restart không?
- Có ghi nhận tiến độ bền vững không?
- Một task có thể kéo dài bao lâu?
- Có thể bị dừng giữa transaction không?

Đừng chờ vô hạn một task không có timeout hoặc không có khả năng phục hồi.

### 8.4. Spring Boot auto-configured task executor

Spring Boot có các property cho executor/scheduler tự cấu hình trong những phiên bản hỗ trợ, ví dụ:

```properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
```

Tên property và phạm vi áp dụng phụ thuộc Spring Boot version và loại executor auto-configured. Chúng không tự cấu hình mọi executor do bạn tự tạo.

Nếu khai báo một `@Bean` custom, hãy đọc lifecycle API của bean đó và cấu hình shutdown tường minh. Đừng giả định property auto-configuration sẽ tự điều khiển một object được tạo thủ công ở bất kỳ đâu.

## 9. Thread tạo thủ công không thuộc Spring lifecycle

Ví dụ:

```java
@Component
public class PollingWorker {

    public PollingWorker() {
        Thread thread = new Thread(() -> {
            while (true) {
                poll();
            }
        });

        thread.start();
    }

    private void poll() {
        // ...
    }
}
```

Thread được tạo trong constructor không tự động trở thành một Spring bean. Spring không biết cách dừng nó nếu class không cung cấp lifecycle callback.

### 9.1. Quản lý thread có stop flag

```java
@Component
public class PollingWorker {

    private final AtomicBoolean running =
            new AtomicBoolean(false);

    private Thread workerThread;

    @PostConstruct
    public void start() {
        if (!running.compareAndSet(false, true)) {
            return;
        }

        workerThread = new Thread(this::runLoop, "orders-poller");
        workerThread.start();
    }

    private void runLoop() {
        while (running.get() &&
                !Thread.currentThread().isInterrupted()) {
            try {
                pollOnce();
                Thread.sleep(1000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    private void pollOnce() {
        // Xử lý một đơn vị công việc có giới hạn thời gian
    }

    @PreDestroy
    public void stop() {
        running.set(false);

        if (workerThread != null) {
            workerThread.interrupt();
            try {
                workerThread.join(5000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Ví dụ cần import `AtomicBoolean`, `PostConstruct`, `PreDestroy` và các annotation tương ứng. Trong Spring Boot 3, `PostConstruct` và `PreDestroy` thường thuộc `jakarta.annotation`.

### 9.2. Tại sao phải có cả stop flag và interrupt?

- Stop flag biểu thị ý định dừng ở cấp ứng dụng.
- Interrupt giúp đánh thức thread đang sleep hoặc ở một số blocking operations.
- `join(timeout)` chờ thread kết thúc trong thời gian giới hạn.

Nếu `pollOnce()` bị block trong một thư viện không hỗ trợ interrupt hoặc timeout, `join(5000)` có thể trả về trong khi thread vẫn sống. Khi đó cần cấu hình timeout/close cho resource mà `pollOnce()` đang sử dụng.

### 9.3. Đừng dùng daemon thread để che leak

Bạn có thể gọi:

```java
workerThread.setDaemon(true);
```

Daemon thread không giữ JVM sống khi mọi non-daemon threads đã kết thúc. Nhưng khi JVM thoát, daemon thread có thể bị dừng mà không có cơ hội hoàn tất công việc hoặc cleanup.

Đổi thread thành daemon **không thay thế** cơ chế dừng, commit, flush hoặc giải phóng tài nguyên.

## 10. Dùng `@Scheduled` và scheduler có lifecycle

Spring Scheduling thường được quản lý bởi scheduler bean.

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
```

```java
@Component
public class CleanupJob {

    @Scheduled(fixedDelay = 60_000)
    public void run() {
        // Dọn dữ liệu hết hạn theo một batch giới hạn
    }
}
```

Spring Boot/Spring Framework có thể sử dụng task scheduler được cấu hình trong context. Khi context đóng, scheduler do Spring quản lý có lifecycle shutdown phù hợp.

### 10.1. Task đang chạy khi shutdown bắt đầu

Nếu một scheduled method đang chạy, cần xác định:

- Có cho nó hoàn tất không?
- Có thể interrupt không?
- Có thể chạy lại sau restart không?
- Có ghi checkpoint không?
- Có giữ transaction hoặc lock quá lâu không?

Không phải cứ scheduler bean được đóng là mọi business task đang chạy đã hoàn tất an toàn.

### 10.2. Tự tạo `Timer` dễ bị quên

```java
Timer timer = new Timer();
timer.scheduleAtFixedRate(task, 0, 1000);
```

`Timer` tạo thread riêng. Nếu không gọi:

```java
timer.cancel();
```

thread có thể giữ JVM sống.

Nếu dùng scheduler của Spring, hãy để container quản lý lifecycle thay vì tạo timer thủ công trong service.

## 11. Đóng HTTP clients, connection pools và database resources

Không chỉ thread mới gây vấn đề. Client có thể giữ socket, connection pool, selector thread hoặc native resource.

### 11.1. Đóng client bằng `@Bean(destroyMethod=...)`

Ví dụ khái niệm:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    public PartnerClient partnerClient() {
        return PartnerClient.create();
    }
}
```

`PartnerClient` ở đây là class giả định có method `close()`. Khi context đóng, Spring gọi method này.

### 11.2. HTTP client có thể dùng connection pool riêng

Một số HTTP clients có:

- Connection manager.
- Event loop.
- Selector thread.
- Background eviction scheduler.
- Connection pool.

Đóng wrapper mà không đóng resource owner có thể khiến thread hoặc socket còn tồn tại. Hãy đọc API của client cụ thể để biết method nào thực sự đóng connection manager.

### 11.3. DataSource và connection pool

Một `DataSource` do Spring Boot auto-configure thường được quản lý trong context. Nếu tự tạo pool bên ngoài Spring, bạn phải tự đóng pool.

Không giữ connection lấy từ pool mãi trong field của singleton. Connection được mượn cần được trả về:

```java
try (Connection connection = dataSource.getConnection()) {
    // Dùng connection
}
```

Với pooled datasource, `close()` trên connection thường trả connection về pool, còn datasource/pool được đóng ở lifecycle của chính datasource.

### 11.4. Không tự đóng datasource mà bean khác vẫn dùng

Nếu một service tự gọi `dataSource.close()` giữa lúc context còn hoạt động, các bean khác có thể gặp lỗi kết nối.

Lifecycle owner của datasource nên là container hoặc component quản lý pool, không phải một business service ngẫu nhiên.

## 12. Kafka, RabbitMQ và message consumers

Một consumer thường có thread nhận message, network connection và trạng thái ack/offset. Đóng consumer không chỉ là dừng một thread.

### 12.1. Các bước shutdown thường cần có

1. Ngừng nhận message mới.
2. Chờ message đang xử lý hoàn tất trong thời gian cho phép.
3. Commit offset hoặc ack theo semantics của broker.
4. Xử lý task đang chờ theo chính sách retry/dead-letter.
5. Đóng consumer/client và connection.

### 12.2. Tránh mất message hoặc xử lý trùng

Nếu process bị dừng giữa lúc xử lý:

```text
Receive message
      |
      v
Update database
      |
      X process stops
      |
      v
Offset/ack chưa commit?
```

Message có thể được gửi lại. Hệ thống cần idempotency hoặc transaction/ack strategy phù hợp; shutdown cleanup không tự bảo đảm exactly-once business effect.

### 12.3. Spring-managed listener containers

Nếu sử dụng Spring Kafka hoặc Spring AMQP listener container, hãy để framework quản lý lifecycle của container. Cấu hình shutdown timeout, acknowledgement và listener concurrency theo phiên bản và yêu cầu thực tế.

Đừng tạo thread polling broker thủ công trong constructor nếu không có một lifecycle owner rõ ràng.

## 13. Graceful shutdown của web server

Một web server không nên lập tức cắt mọi request khi process nhận tín hiệu dừng bình thường nếu có thể cho request đang xử lý hoàn tất.

**Graceful shutdown** là quá trình:

1. Ngừng nhận request mới.
2. Cho request đang xử lý tiếp tục trong khoảng thời gian giới hạn.
3. Đóng các component và tài nguyên còn lại.
4. Kết thúc process trước deadline của môi trường triển khai.

### 13.1. Bật graceful shutdown trong Spring Boot

Trong những phiên bản Spring Boot hỗ trợ:

```properties
server.shutdown=graceful
```

Spring Boot tích hợp graceful shutdown với embedded web servers được hỗ trợ. Chi tiết hành vi và server support phụ thuộc version và web server implementation.

Nếu không cấu hình chế độ graceful, server có thể dùng cách shutdown mặc định tương ứng phiên bản, thường là dừng ngay hoặc ít chờ request đang xử lý.

### 13.2. Timeout cho shutdown phase

Ví dụ:

```properties
spring.lifecycle.timeout-per-shutdown-phase=30s
```

Property này cho lifecycle processor một khoảng thời gian để chờ từng phase. Nó không nên được đặt lớn hơn một cách tùy tiện so với thời gian mà orchestrator cho phép process kết thúc.

### 13.3. Readiness trong quá trình shutdown

Khi ứng dụng bắt đầu graceful shutdown, Spring Boot có thể chuyển readiness sang trạng thái từ chối traffic mới trong lifecycle tương ứng.

Điều này giúp orchestrator/load balancer ngừng gửi request mới, trong khi server xử lý request đang tồn tại theo cơ chế graceful shutdown.

Tuy nhiên, routing cần có thời gian lan truyền thay đổi. Nếu traffic được gửi trực tiếp vào process, readiness state không tự chặn mọi client.

### 13.4. Graceful không có nghĩa chờ vô hạn

Một request bị treo hoặc một client không trả lời có thể khiến shutdown kéo dài. Cần timeout ở:

- HTTP request.
- Database query/transaction.
- Outbound HTTP call.
- Message processing.
- Executor task.

Shutdown chỉ có thể hoàn tất đúng hạn khi những công việc đang chạy có giới hạn thời gian hoặc cơ chế cancel phù hợp.

## 14. SIGTERM, SIGINT và container lifecycle

Trên Unix-like systems, process thường nhận:

- `SIGTERM`: yêu cầu kết thúc có kiểm soát.
- `SIGINT`: tín hiệu ngắt, thường từ terminal.
- `SIGKILL`: kết thúc cưỡng chế, không thể được ứng dụng xử lý bằng shutdown hook.

### 14.1. Docker

Khi dừng container, Docker thường gửi signal dừng tới process chính (PID 1), chờ khoảng thời gian grace period, rồi mới có thể kill cưỡng chế nếu process chưa thoát.

Ví dụ:

```bash
docker stop --time 40 order-service
```

Container được cho thời gian dừng tối đa theo tham số này trước khi Docker dùng hành động cưỡng chế.

### 14.2. Dùng exec-form ENTRYPOINT

Ưu tiên:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Exec form giúp Java process trở thành process được thực thi trực tiếp trong container theo cách rõ ràng.

Nếu dùng shell form:

```dockerfile
ENTRYPOINT java -jar /app/app.jar
```

shell có thể đứng ở PID 1 và cần chuyển tiếp signal đúng cách. Một shell wrapper không dùng `exec` có thể khiến Java process không nhận signal như dự kiến.

Nếu cần wrapper:

```sh
#!/bin/sh
exec java -jar /app/app.jar "$@"
```

Lệnh `exec` thay process shell bằng Java process.

### 14.3. Kubernetes termination grace period

Trong Kubernetes, Pod termination thường diễn ra theo quy trình:

1. Pod được đánh dấu terminating và ngừng được chọn cho traffic mới theo endpoint/routing propagation.
2. `preStop` hook có thể được chạy nếu khai báo.
3. Container runtime gửi `SIGTERM` tới process.
4. Kubernetes chờ trong `terminationGracePeriodSeconds`.
5. Nếu process chưa dừng khi hết thời gian, container có thể bị `SIGKILL`.

Thứ tự và thời gian thực tế cần xét cùng kubelet, endpoint propagation và preStop hook. `preStop` tiêu thụ thời gian trong termination grace period; nó không tự cộng thêm một khoảng grace mới.

### 14.4. Chọn grace period đủ cho shutdown

Ví dụ:

```yaml
spec:
  terminationGracePeriodSeconds: 60
```

Giá trị này chỉ là ví dụ. Thời gian thực tế phải bao gồm:

- Thời gian ngừng nhận traffic.
- Thời gian request đang xử lý hoàn tất.
- Thời gian dừng consumer/executor.
- Thời gian flush/close tài nguyên.
- Một khoảng dự phòng cho hệ thống.

Không đặt Spring shutdown timeout 90 giây nếu container chỉ cho process 30 giây. Khi đó Kubernetes có thể kill process trước khi Spring hoàn tất.

## 15. Dùng `ContextClosedEvent` để quan sát quá trình đóng

Spring phát `ContextClosedEvent` khi context bắt đầu quá trình đóng.

Ví dụ:

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownEventsLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownEventsLogger.class);

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        log.info("event=application.context.closed");
    }
}
```

Listener này hữu ích để ghi nhận mốc lifecycle. Nhưng event được phát trong quá trình đóng context; **nó không phải callback tốt nhất để tự đóng mọi dependency**.

### 15.1. Đừng giả định mọi bean đã bị destroy khi event được phát

Context close lifecycle còn phải thực hiện các bước dừng lifecycle beans và destroy singleton beans. Một event listener có thể chạy trước khi tất cả resource đã được giải phóng.

Nếu một bean sở hữu executor, hãy dùng `@PreDestroy`, `DisposableBean` hoặc lifecycle interface của bean đó.

### 15.2. Phân biệt event và bằng chứng hoàn tất

Log:

```text
event=application.context.closed
```

cho biết event đã được phát. Để xác nhận executor đã kết thúc, cần kiểm tra trạng thái executor hoặc log/metric cụ thể sau khi await hoàn tất.

Đừng dùng một dòng log “context closed” để kết luận toàn bộ thread nền đã dừng.

## 16. Bean scope và resource ownership

Destroy callback phụ thuộc lifecycle và scope của bean.

### 16.1. Singleton

Singleton bean được container quản lý và thường có destroy callbacks khi context đóng.

```java
@Component
public class SingletonClientManager {

    @PreDestroy
    public void close() {
        // Đóng resource
    }
}
```

### 16.2. Prototype

Prototype bean được tạo mỗi lần yêu cầu, nhưng Spring **không quản lý đầy đủ lifecycle destruction của prototype instance** sau khi trả nó cho client.

Nếu prototype sở hữu resource:

- Client chịu trách nhiệm đóng instance sau khi sử dụng.
- Hoặc thiết kế factory có API acquire/release rõ ràng.
- Tránh tạo prototype chứa thread hoặc socket mà không có owner.

### 16.3. Request/session scope

Scoped bean có lifecycle riêng theo scope. Với request-scoped bean, resource cần được đóng khi request scope kết thúc theo cơ chế phù hợp.

Nếu resource cần sống lâu hơn request, đừng giữ nó trong một request-scoped bean rồi kỳ vọng nó tồn tại sau request.

### 16.4. Resource được tạo ngoài container

Ví dụ:

```java
public class ReportService {

    public void generate() {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        // ...
    }
}
```

Nếu không shutdown executor, Spring không có bean lifecycle callback để gọi.

Tốt hơn:

- Inject executor do Spring quản lý.
- Dùng try-with-resources cho resource phạm vi ngắn.
- Nếu tạo resource động, đóng nó trong `finally` hoặc một scope rõ ràng.

## 17. Sử dụng try-with-resources cho resource ngắn hạn

Không phải resource nào cũng nên giữ tới khi context đóng. Với stream, file, connection hoặc handle dùng trong một method, hãy đóng ngay sau khi hoàn thành.

Ví dụ:

```java
public String readConfig(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Try-with-resources bảo đảm `close()` được gọi khi thoát khỏi block, kể cả khi có exception.

### 17.1. JDBC connection

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select current_timestamp"
             );
     ResultSet resultSet = statement.executeQuery()) {

    if (resultSet.next()) {
        return resultSet.getTimestamp(1).toInstant();
    }
}
```

Với pooled datasource, đóng connection trả nó về pool theo hợp đồng của datasource. Không giữ connection trong singleton field để chờ destroy context.

### 17.2. Resource dùng chung dài hạn

Một HTTP client hoặc connection pool được chia sẻ giữa nhiều request có thể sống suốt thời gian application context. Khi đó `@Bean(destroyMethod=...)` hoặc bean lifecycle là phù hợp.

Phân biệt:

```text
Resource ngắn hạn -> try-with-resources
Resource dùng chung -> Spring bean + destroy lifecycle
Task nền -> executor/worker lifecycle
```

## 18. Shutdown trong ứng dụng command-line và batch

Một ứng dụng Spring Boot không nhất thiết phải có web server. Với batch application, tiến trình có thể thực hiện công việc rồi thoát.

### 18.1. Chạy non-web application

```java
@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context =
                application.run(args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

Đây là một mẫu đơn giản cho batch app đồng bộ, khi runners đã hoàn tất và không cần process sống tiếp.

### 18.2. Không gọi exit ngay khi submit async work

Ví dụ sai:

```java
@Component
public class BatchRunner implements ApplicationRunner {

    private final Executor executor;

    public BatchRunner(Executor executor) {
        this.executor = executor;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(this::processLargeFile);
        // Runner kết thúc ngay
    }
}
```

Nếu main method gọi `SpringApplication.exit(context)` ngay sau `run()`, context có thể bắt đầu shutdown trong khi task đang xử lý.

Thiết kế tốt hơn là:

- Chờ `Future`/`CompletableFuture` hoàn tất trong giới hạn thời gian.
- Dùng batch framework có lifecycle và job status.
- Để executor được quản lý và có shutdown policy rõ ràng.

### 18.3. Trả exit code có ý nghĩa

Spring Boot hỗ trợ `ExitCodeGenerator`:

```java
@Component
public class BatchExitCode implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 0;
    }
}
```

Trong ứng dụng thật, exit code nên phản ánh kết quả batch theo hợp đồng vận hành. Không trả 0 chỉ vì context đã đóng nếu job thất bại.

## 19. Vì sao `@PreDestroy` không chạy như mong đợi?

Một số nguyên nhân thường gặp:

### 19.1. Bean không do Spring quản lý

```java
MyClient client = new MyClient();
```

Nếu object được tạo bằng `new` ngoài container, Spring không tự gọi `@PreDestroy` trên nó.

**Cách xử lý:** đăng ký bean bằng `@Component`, `@Bean` hoặc quản lý resource ở nơi tạo.

### 19.2. Bean prototype

Prototype instance không được Spring tự quản lý đầy đủ destruction lifecycle sau khi được giao cho client.

**Cách xử lý:** client phải đóng resource hoặc dùng factory/lifecycle abstraction phù hợp.

### 19.3. Context không được đóng

Nếu một context được tạo thủ công và không có shutdown hook hoặc code close, destroy callbacks có thể không chạy khi main method kết thúc trong một tình huống còn thread giữ JVM sống.

**Cách xử lý:** dùng `ConfigurableApplicationContext.close()` hoặc đảm bảo process shutdown hook được đăng ký.

### 19.4. JVM bị kill cưỡng chế

`SIGKILL` không cho JVM chạy shutdown hooks. `@PreDestroy` không phải bảo đảm cho một lần kill cưỡng chế.

**Cách xử lý:** thiết kế operation có thể phục hồi, transaction có tính nhất quán và message handling có retry/idempotency.

### 19.5. Cleanup method bị block

Ví dụ:

```java
@PreDestroy
public void cleanup() {
    while (!remoteServiceAvailable()) {
        // Chờ vô hạn
    }
}
```

Context có thể không hoàn tất shutdown đúng hạn.

**Cách xử lý:** đặt timeout, tránh retry vô hạn và cung cấp đường thoát khi dependency không khả dụng.

### 19.6. Cleanup callback ném exception

Nếu callback lỗi, Spring thường ghi nhận lỗi và tiếp tục xử lý các bean destroy khác theo cơ chế container. Nhưng resource mà callback định đóng có thể vẫn còn sống.

**Cách xử lý:** log một failure code phù hợp, giữ thông tin lỗi cần thiết và bảo đảm callback cleanup có xử lý exception theo từng resource.

### 19.7. Annotation import không phù hợp version

Spring Boot 3 dùng Jakarta namespace cho `@PreDestroy`; code cũ dùng `javax.annotation` có thể cần migration/dependency phù hợp.

**Cách xử lý:** dùng annotation namespace đúng với stack version.

## 20. Chẩn đoán process không thoát bằng thread dump

Khi context đã đóng nhưng process vẫn sống, hãy xem **thread nào còn tồn tại**.

### 20.1. Lấy thread dump bằng `jcmd`

Trên máy có JDK và quyền attach phù hợp:

```bash
jcmd <pid> Thread.print
```

Ví dụ:

```bash
jcmd 12345 Thread.print
```

Lệnh này yêu cầu JVM process có PID tương ứng xuất thread dump.

### 20.2. Dùng `jstack`

```bash
jstack 12345
```

Thread dump có thể cho thấy:

- Tên thread.
- Trạng thái (`RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`...).
- Stack trace.
- Lock/monitor liên quan.

Không kết luận mọi thread `WAITING` đều bị leak. Thread pool có thể giữ worker threads chờ task mới; điều quan trọng là **thread còn được sở hữu bởi resource nào và lifecycle của owner đã đóng chưa**.

### 20.3. Thread name giúp tìm chủ sở hữu

Ví dụ:

```text
pool-3-thread-1
orders-worker-2
scheduling-1
http-client-selector
kafka-consumer-0
```

Tên mặc định `pool-3-thread-1` khó truy nguồn hơn tên được đặt có ý nghĩa. Khi tạo executor:

```java
executor.setThreadNamePrefix("orders-worker-");
```

Tên thread có prefix rõ giúp lọc thread dump và tìm bean sở hữu nhanh hơn.

### 20.4. Thread dump trên Linux

Có thể gửi `SIGQUIT` (`kill -3`) tới JVM để yêu cầu thread dump trong những môi trường hỗ trợ; output thường đi vào stdout/stderr của process theo cấu hình runtime.

Không dùng `kill -9` để yêu cầu thread dump. `SIGKILL` kết thúc process cưỡng chế và không cho JVM xử lý tín hiệu.

### 20.5. Windows

Trên Windows, có thể dùng `jcmd` hoặc `jstack` từ JDK tương ứng:

```powershell
jcmd 12345 Thread.print
```

Hãy dùng PID của process Java đúng môi trường và tài khoản có quyền attach.

## 21. Đọc thread dump: những dấu hiệu cần chú ý

### 21.1. Worker thread đang chạy vô hạn

Ví dụ stack:

```text
"orders-worker-1" #42 prio=5 os_prio=0
   java.lang.Thread.State: RUNNABLE
   at com.example.orders.Poller.pollForever(Poller.java:42)
   at com.example.orders.Poller.run(Poller.java:25)
```

Đây là dấu hiệu cần xem loop có stop condition hay không. `RUNNABLE` không nhất thiết có nghĩa CPU luôn cao; nó mô tả trạng thái thread theo JVM.

### 21.2. Thread pool đang chờ task

```text
"pool-3-thread-1"
   java.lang.Thread.State: WAITING
   at java.util.concurrent.LinkedBlockingQueue.take(...)
   at java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

Worker đang chờ task mới. Nếu executor vẫn hoạt động sau khi context đóng, hãy kiểm tra executor đã shutdown chưa.

### 21.3. Scheduler thread

```text
"scheduling-1"
   java.lang.Thread.State: TIMED_WAITING
```

Có thể là scheduler đang chờ thời điểm chạy tiếp theo. Hãy xác định scheduler bean có thuộc context đang đóng không và lifecycle callback đã được gọi chưa.

### 21.4. Thread bị block

```text
"orders-worker-2"
   java.lang.Thread.State: BLOCKED
   - waiting to lock <...>
```

Kiểm tra lock owner và khả năng deadlock. Cleanup có thể đang chờ một lock mà task không bao giờ nhả.

### 21.5. Non-daemon hay daemon?

Thread dump có thể cho biết daemon status tùy công cụ/format. Non-daemon thread còn sống có thể giữ JVM tiếp tục chạy.

Nhưng daemon thread còn sống cũng có thể biểu thị resource chưa cleanup; nó chỉ không giữ JVM sống theo quy tắc daemon thread.

## 22. Viết shutdown callback có timeout và khả năng phục hồi

Một cleanup method tốt cần:

- Dừng nhận công việc mới.
- Cho công việc đang chạy hoàn tất trong giới hạn.
- Đóng resource theo dependency order.
- Khôi phục interrupt status khi bị interrupt.
- Ghi nhận lỗi mà không che lấp nguyên nhân.
- Không chờ vô hạn.

Ví dụ cho một worker:

```java
package com.example.orders.worker;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import jakarta.annotation.PreDestroy;

@Component
public class ExportWorker {

    private static final Logger log =
            LoggerFactory.getLogger(ExportWorker.class);

    private final ExecutorService executor;

    public ExportWorker(ExecutorService exportExecutor) {
        this.executor = exportExecutor;
    }

    @PreDestroy
    public void shutdown() {
        log.info("export.worker.shutdown.started");
        executor.shutdown();

        try {
            if (!executor.awaitTermination(15, TimeUnit.SECONDS)) {
                log.warn("export.worker.shutdown.timeout");
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    log.error("export.worker.did_not_terminate");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        log.info("export.worker.shutdown.finished");
    }
}
```

Ví dụ này giả định `exportExecutor` là bean được inject và **ExportWorker là owner duy nhất** chịu trách nhiệm shutdown executor. Nếu executor cũng có destroy callback riêng, cần tránh shutdown hai nơi hoặc điều chỉnh ownership.

### 22.1. Không để hai bean cùng sở hữu một executor

Một lỗi thiết kế thường gặp:

```text
ExportWorker @PreDestroy -> executor.shutdown()
Executor bean destroy    -> executor.shutdown()
```

Shutdown lặp đôi có thể idempotent với `ExecutorService`, nhưng hai nơi cùng chờ hoặc cùng interrupt có thể tạo hành vi khó dự đoán.

Tốt hơn là một bean cấu hình sở hữu executor lifecycle; worker chỉ submit task và dừng nhận task mới theo lifecycle của chính nó.

### 22.2. Đóng theo thứ tự dependency

Nếu consumer dùng executor để hoàn tất các callback cuối cùng, đừng shutdown executor trước khi consumer dừng.

Thứ tự hợp lý có thể là:

```text
Stop accepting new messages
          |
          v
Wait for in-flight message handling
          |
          v
Shutdown task executor
          |
          v
Close database / HTTP clients
```

Thứ tự cụ thể phụ thuộc resource và transaction semantics. `SmartLifecycle` phase hoặc một shutdown coordinator có thể giúp biểu diễn trình tự.

## 23. Tránh deadlock trong quá trình shutdown

Một số cleanup callback có thể chờ lẫn nhau:

```text
Bean A @PreDestroy
   waits for task in Executor
             |
             v
        Task needs Bean B
             |
             v
        Bean B already closing
```

Nếu Bean B đã đóng connection/client mà task còn cần, task không thể hoàn tất. Bean A chờ task, context chờ A và shutdown kéo dài.

### 23.1. Ngừng tạo việc trước khi đóng dependency

Một trình tự tốt thường là:

1. Ngừng nhận traffic/message mới.
2. Ngừng schedule task mới.
3. Chờ in-flight operations.
4. Dừng worker/executor.
5. Đóng client/connection pool.
6. Hoàn tất context close.

### 23.2. Không giữ lock khi chờ thread khác

Không nên:

```java
synchronized void shutdown() {
    worker.interrupt();
    worker.join();
}
```

nếu worker cần chính monitor này để kết thúc. Đây có thể tạo deadlock.

Tách bước cập nhật trạng thái trong lock khỏi bước chờ thread:

```java
public void shutdown() {
    synchronized (this) {
        running = false;
    }

    worker.interrupt();
    // Chờ sau khi đã nhả monitor
}
```

## 24. Logging trong shutdown

Log giúp biết lifecycle đi tới đâu:

```text
event=shutdown.started
event=consumer.stop.started
event=consumer.stop.completed
event=executor.shutdown.started
event=executor.shutdown.completed
event=application.context.closed
```

### 24.1. Ghi log có ý nghĩa

Nên ghi:

- Tên component.
- Hành động shutdown.
- Thời gian chờ.
- Số task đang chạy/chờ nếu có thể lấy an toàn.
- Failure code khi đóng không thành công.

Không ghi:

- Password/secret.
- Toàn bộ cấu hình.
- Message payload nhạy cảm.
- Nội dung request/response.

### 24.2. Đừng chỉ log “shutdown complete” từ một callback

Một component có thể đóng xong trong khi resource khác vẫn sống. Mỗi owner nên log kết quả cleanup của resource mình sở hữu.

Một dòng `application.shutdown.completed` nên được phát ở vị trí có đủ thông tin để xác định các bước quan trọng đã hoàn tất, không chỉ vì một listener nhận được `ContextClosedEvent`.

### 24.3. Logging system cũng cần lifecycle

Spring Boot quản lý logging system. Không nên tự đóng logging backend quá sớm rồi kỳ vọng các bean destroy callback sau đó vẫn ghi log bình thường.

Để framework quản lý logging shutdown và giữ callback cleanup ngắn gọn.

## 25. Test lifecycle đóng context

Không cần chờ một JVM thật kết thúc để kiểm tra một destroy callback cơ bản. Có thể dùng Spring test context và quan sát side effect.

### 25.1. Bean ghi nhận destroy

```java
public class CleanupProbe {

    private final AtomicBoolean destroyed =
            new AtomicBoolean(false);

    public boolean isDestroyed() {
        return destroyed.get();
    }

    @PreDestroy
    public void destroy() {
        destroyed.set(true);
    }
}
```

### 25.2. Kiểm tra bằng `AnnotationConfigApplicationContext`

```java
class ContextCloseTest {

    @Test
    void invokesPreDestroyWhenContextCloses() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.registerBean(CleanupProbe.class);
        context.refresh();

        CleanupProbe probe =
                context.getBean(CleanupProbe.class);

        assertThat(probe.isDestroyed()).isFalse();

        context.close();

        assertThat(probe.isDestroyed()).isTrue();
    }
}
```

Ví dụ giả định test dùng JUnit 5 và AssertJ, cùng imports cho `AtomicBoolean` và Spring context.

### 25.3. Kiểm tra executor đã terminate

```java
context.close();

assertThat(executor.isShutdown()).isTrue();
assertThat(executor.isTerminated()).isTrue();
```

Đừng chỉ assert `isShutdown()`. Một executor có thể đã ngừng nhận task nhưng task đang chạy chưa hoàn tất.

### 25.4. Kiểm tra `@SpringBootTest`

Spring Test thường cache ApplicationContext giữa các test để tăng tốc. Context không nhất thiết bị đóng ngay sau mỗi method test.

Nếu cần kiểm tra việc context bị đóng và tạo lại, có thể dùng:

```java
@DirtiesContext
```

ở scope phù hợp để Spring Test loại context khỏi cache và đóng nó theo lifecycle của test framework.

Không nên thêm `@DirtiesContext` cho mọi test nếu không cần; nó có thể làm test suite chậm và thay đổi trạng thái chia sẻ.

### 25.5. `ApplicationContextRunner`

Đối với kiểm thử auto-configuration hoặc bean lifecycle nhỏ, `ApplicationContextRunner` cung cấp callback chạy trong context mà runner quản lý:

```java
new ApplicationContextRunner()
        .withBean(CleanupProbe.class)
        .run(context -> {
            CleanupProbe probe =
                    context.getBean(CleanupProbe.class);
            assertThat(probe.isDestroyed()).isFalse();
        });
```

Runner đóng context sau callback. Nếu cần assert state sau close, hãy giữ reference tới probe và kiểm tra sau khi `run(...)` kết thúc.

## 26. Kiểm tra shutdown trong integration test với process riêng

Đôi khi cần xác nhận process thực sự thoát sau khi nhận signal. Đây là bài kiểm tra cấp process, khác với kiểm tra Spring bean callback.

Một test có thể:

1. Khởi chạy executable JAR bằng `ProcessBuilder`.
2. Chờ một dòng startup/ready signal có giới hạn.
3. Gửi tín hiệu dừng phù hợp với hệ điều hành.
4. Chờ process kết thúc trong timeout.
5. Kiểm tra exit code và shutdown logs.

Ví dụ Java khái niệm:

```java
Process process = new ProcessBuilder(
        "java",
        "-jar",
        "build/libs/demo.jar"
).start();

boolean exited = process.waitFor(
        30,
        TimeUnit.SECONDS
);
```

Ví dụ này chỉ minh họa chờ process; một integration test hoàn chỉnh còn phải gửi tín hiệu shutdown và thu stdout/stderr để tránh pipe bị đầy. Trên Windows và Unix, cách gửi signal khác nhau.

### 26.1. Không dùng `destroyForcibly()` làm phép kiểm tra graceful

```java
process.destroyForcibly();
```

kết thúc process cưỡng chế. Nó không kiểm chứng Spring shutdown hooks hoặc `@PreDestroy`.

Hãy dùng tín hiệu shutdown bình thường được môi trường hỗ trợ, chờ trong timeout, rồi chỉ dùng force termination để cleanup test nếu process bị treo.

### 26.2. Test phải có timeout

Một test shutdown bị treo có thể làm CI job đứng vô thời hạn. Đặt timeout cho:

- Startup.
- Gửi request test.
- Shutdown signal.
- Process exit.
- Thu thập output.

## 27. Các nguyên nhân thường gặp khiến process không thoát

| Nguyên nhân | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| `ExecutorService` chưa shutdown | `pool-N-thread-M` còn sống | Tìm nơi tạo executor và lifecycle owner |
| Thread tự tạo loop vô hạn | Thread custom còn RUNNABLE | Xem stop flag, interrupt và timeout |
| Scheduled executor còn chạy | Scheduler thread còn sống | Kiểm tra scheduler bean hoặc `Timer.cancel()` |
| HTTP client giữ event loop | Selector/connection thread còn sống | Kiểm tra API close của client/manager |
| Message consumer chưa dừng | Consumer thread còn hoạt động | Kiểm tra listener container và in-flight work |
| Cleanup chờ vô hạn | Context close kéo dài | Thêm timeout, đọc stack thread đang chờ |
| Async task không hợp tác interrupt | `shutdownNow()` nhưng task vẫn sống | Sửa task để kiểm tra interrupt/cancel |
| Thread bị block I/O | Stack đang ở socket read/connect | Đặt network timeout và đóng socket/client |
| Non-daemon thread từ thư viện | Tên thread thuộc library | Xác định owner bean và shutdown API |
| Context không được close | Destroy callbacks không chạy | Kiểm tra `close()` và shutdown hook |
| Process bị giữ bởi nhiều context | Một context đóng nhưng context khác còn active | Tìm mọi `SpringApplication`/context được tạo |
| Shell không forward signal | Java không nhận SIGTERM như dự kiến | Kiểm tra PID 1 và exec-form ENTRYPOINT |

## 28. Các lỗi thường gặp trong callback cleanup

### 28.1. Dùng `Thread.sleep()` để chờ shutdown

Không nên:

```java
@PreDestroy
public void cleanup() throws InterruptedException {
    Thread.sleep(30_000);
}
```

Sleep không chứng minh resource đã đóng hoặc task đã hoàn tất.

Hãy chờ trạng thái cụ thể:

```java
executor.awaitTermination(10, TimeUnit.SECONDS);
```

### 28.2. Nuốt `InterruptedException`

Không nên:

```java
try {
    executor.awaitTermination(10, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    // Ignore
}
```

Thông thường, nếu không thể propagate exception, hãy khôi phục interrupt:

```java
catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

### 28.3. Chờ một remote dependency không có timeout

Nếu cleanup gọi API từ xa mà không timeout, context có thể treo khi network lỗi.

Đặt connect/read/request timeout phù hợp. Shutdown không nên phụ thuộc vô hạn vào một hệ thống bên ngoài đang mất khả năng phản hồi.

### 28.4. Gửi task cleanup vào executor đang đóng

Không nên:

```java
@PreDestroy
public void cleanup() {
    executor.submit(this::closeRemoteSession);
}
```

nếu sau đó không chờ task. Executor có thể bị shutdown ngay sau callback, task có thể không chạy hoặc không hoàn tất.

Nếu cleanup cần async, phải có một cơ chế chờ hoàn tất rõ ràng trong timeout.

### 28.5. Đóng dependency trước consumer

Nếu consumer còn dùng database client, đóng database client trước khi consumer dừng có thể khiến cleanup consumer thất bại.

Hãy thể hiện lifecycle order theo quan hệ sử dụng.

### 28.6. `@PreDestroy` gọi một method `@Async`

Không giả định:

```java
@PreDestroy
public void cleanup() {
    asyncService.flush();
}
```

sẽ hoàn tất trước khi context tiếp tục destroy bean. Nếu `flush()` là async, callback có thể chỉ submit task.

Trong cleanup, ưu tiên thao tác đồng bộ có timeout hoặc chờ `Future` cụ thể.

## 29. Một ví dụ tổng hợp: ứng dụng có web server và worker

Giả sử Orders API có:

- Embedded Tomcat.
- Một worker nhận message.
- Một executor xử lý export.
- Một HTTP client gọi pricing service.

Lifecycle shutdown mong muốn:

```text
SIGTERM
   |
   v
Readiness -> REFUSING_TRAFFIC
   |
   v
Web server ngừng nhận request mới
   |
   v
Message consumer ngừng nhận message mới
   |
   v
Chờ request/message đang xử lý
   |
   v
Executor ngừng nhận task và chờ hoàn tất
   |
   v
Đóng HTTP client / connection pool
   |
   v
Destroy singleton beans
   |
   v
JVM kết thúc
```

Thứ tự thực tế cần được cấu hình theo lifecycle mechanisms và dependencies của ứng dụng; sơ đồ là mục tiêu thiết kế.

### 29.1. Web graceful shutdown

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
```

### 29.2. Consumer lifecycle

Consumer cần có `SmartLifecycle` hoặc listener container do framework quản lý để:

- Dừng nhận message mới.
- Chờ in-flight message.
- Commit/ack đúng policy.
- Đóng connection.

### 29.3. Executor lifecycle

Khai báo executor bean với thread prefix và shutdown wait:

```java
@Bean
public ThreadPoolTaskExecutor exportExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("export-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);

    return executor;
}
```

### 29.4. HTTP client ownership

Đăng ký client thành bean và khai báo destroy method:

```java
@Bean(destroyMethod = "close")
public PricingClient pricingClient() {
    return PricingClient.create();
}
```

`PricingClient` là class minh họa có method `close()`. Trong dự án thực tế, thay bằng API đóng resource đúng của HTTP client được chọn.

### 29.5. Tổng ngân sách thời gian

Giả sử:

| Giai đoạn | Ngân sách minh họa |
| --- | ---: |
| Ngừng nhận traffic/message mới | 5 giây |
| Chờ request và message đang xử lý | 15 giây |
| Chờ export executor | 15 giây |
| Đóng clients và pool | 5 giây |
| Dự phòng | 10 giây |
| Tổng | 50 giây |

Nếu Kubernetes `terminationGracePeriodSeconds` chỉ là 40 giây, thiết kế trên không phù hợp. Cần rút ngắn, điều chỉnh hoặc thay đổi grace period theo giới hạn deployment.

Không cộng timeout một cách máy móc: lifecycle phases có thể chạy tuần tự hoặc có cơ chế phối hợp khác. Hãy đo shutdown time thực tế và xác nhận bằng integration test.

## 30. Quan sát shutdown bằng metrics và events

Ngoài log, có thể theo dõi:

- Số task đang chạy khi shutdown bắt đầu.
- Số task đang chờ.
- Thời gian từ signal tới process exit.
- Số consumer còn active.
- Số request đang xử lý.
- Số resource close thành công/thất bại.
- Container termination reason và restart count.

Ví dụ event:

```text
event=shutdown.started
activeRequests=4
activeMessages=2
queuedExports=3
```

```text
event=shutdown.component.completed
component=message-consumer
durationMs=1200
```

```text
event=shutdown.completed
durationMs=18300
```

Đây là log minh họa. Tránh đưa payload, token hoặc thông tin người dùng vào các event shutdown.

### 30.1. Shutdown metrics không thay thế thread dump

Metric `activeTasks=0` hữu ích, nhưng có thể bỏ sót thread do thư viện tạo ngoài executor. Khi process vẫn sống, thread dump vẫn là bằng chứng quan trọng.

### 30.2. Correlate theo instance và deployment

Khi nhiều replicas shutdown đồng thời, log nên có instance/pod identity và version. Điều này giúp phân biệt shutdown bình thường do rollout với shutdown bất thường do crash.

## 31. Checklist điều tra khi context đã đóng nhưng process vẫn sống

Đi theo thứ tự:

1. Xác nhận `ConfigurableApplicationContext.isActive()` và có `ContextClosedEvent` chưa.
2. Xác nhận Spring destroy callbacks quan trọng đã được gọi.
3. Lấy thread dump bằng `jcmd <pid> Thread.print` hoặc `jstack`.
4. Tìm non-daemon threads còn sống và ghi nhận thread name.
5. Truy ngược thread tới executor, scheduler, client hoặc library sở hữu.
6. Kiểm tra resource owner có destroy callback/lifecycle hay không.
7. Kiểm tra task có bị block I/O, lock hoặc queue không.
8. Kiểm tra shutdown timeout và container grace period.
9. Xác nhận process có nhận signal dừng bình thường không.
10. Chạy lại một test đóng context hoặc process riêng để tái hiện.

Đừng chỉ thêm `System.exit(0)` để ép process thoát trước khi hiểu thread nào còn sống; làm vậy có thể che leak và cắt ngang công việc cần hoàn tất.

## 32. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`context.close()` luôn kết thúc JVM.” | Nó đóng Spring context; non-daemon thread khác vẫn có thể giữ process sống |
| “Main method kết thúc là JVM kết thúc.” | JVM tiếp tục khi còn non-daemon threads |
| “`@PreDestroy` chạy cho mọi object.” | Chỉ áp dụng cho bean/lifecycle do Spring quản lý phù hợp |
| “Prototype bean được Spring destroy tự động.” | Prototype instance không được container quản lý đầy đủ destruction lifecycle |
| “`shutdown()` chờ mọi task xong.” | Nó ngừng nhận task mới; cần `awaitTermination()` nếu muốn chờ |
| “`shutdownNow()` kill thread ngay.” | Nó yêu cầu interrupt; task phải hợp tác |
| “Daemon thread giải quyết resource leak.” | Daemon chỉ không giữ JVM sống; cleanup vẫn có thể bị bỏ qua |
| “ContextClosedEvent nghĩa mọi resource đã đóng.” | Event là một mốc trong quá trình close |
| “Startup hook và `@PreDestroy` là một.” | JVM hook khởi động quá trình đóng; Spring callback xử lý bean lifecycle |
| “Shutdown hook chạy cả khi `kill -9`.” | SIGKILL không thể được xử lý bằng shutdown hook |
| “Graceful shutdown chờ vô hạn request.” | Nó có timeout và bị giới hạn bởi orchestrator |
| “Readiness DOWN tự ngăn mọi client.” | Chỉ có tác dụng với routing/orchestrator tôn trọng readiness |
| “`@Async` trong `@PreDestroy` chắc chắn xong.” | Async call có thể chỉ submit task rồi callback trả về |
| “Một dòng shutdown complete chứng minh process exit.” | Cần quan sát process và thread thực tế |
| “Executor do `new` tạo tự được Spring đóng.” | Resource ngoài container cần owner và cleanup riêng |
| “Database connection chỉ cần đóng lúc context shutdown.” | Connection mượn theo request phải được trả về ngay sau khi dùng |

## 33. Bài tập thực hành

### Bài 1 — Đóng context và quan sát JVM

Tạo một ứng dụng non-web:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

context.close();
```

Quan sát log destroy callbacks và process exit. Giải thích sự khác nhau giữa context state và JVM process state.

### Bài 2 — Tạo thread giữ JVM sống

Tạo một non-daemon thread loop có stop condition. Cho main method kết thúc nhưng chưa dừng thread.

Quan sát process vẫn sống, lấy thread dump và xác định tên thread.

Sau đó thêm `@PreDestroy` để stop, interrupt và join trong timeout.

### Bài 3 — So sánh `shutdown()` và `shutdownNow()`

Tạo executor với một task đang sleep và một task đang chờ queue.

Thử shutdown theo hai cách, đo thời gian hoàn tất và xem task nào được chạy, task nào bị interrupt.

Giải thích vì sao interrupt cần được code task xử lý.

### Bài 4 — Quản lý executor bằng Spring

Đăng ký `ThreadPoolTaskExecutor` bean với thread name prefix, wait-on-shutdown và await timeout.

Submit vài task có thời lượng hữu hạn. Đóng context và kiểm tra executor đã terminated chưa.

### Bài 5 — So sánh `@PreDestroy` và `DisposableBean`

Tạo hai bean:

- Một bean có `@PreDestroy`.
- Một bean implement `DisposableBean`.

Đóng `AnnotationConfigApplicationContext` và ghi nhận callback nào được gọi.

### Bài 6 — Dùng `@Bean(destroyMethod)`

Tạo một resource giả định có method `close()`. Đăng ký bằng:

```java
@Bean(destroyMethod = "close")
```

Đóng context và xác nhận method được gọi đúng một lần theo thiết kế ownership.

### Bài 7 — `SmartLifecycle` phase

Tạo hai `SmartLifecycle` beans có phase khác nhau. Ghi log start/stop order và giải thích vì sao shutdown order được đảo ngược.

Thử quên gọi callback trong `stop(Runnable)` và quan sát timeout.

### Bài 8 — Graceful shutdown web server

Bật:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Tạo một endpoint có xử lý mất vài giây. Gửi request rồi dừng ứng dụng, quan sát request đang chạy và request mới.

### Bài 9 — Tái hiện SIGTERM trong container

Đóng gói ứng dụng bằng exec-form ENTRYPOINT, chạy container và gửi lệnh stop với grace period có giới hạn.

Quan sát shutdown hooks, Spring destroy callbacks và process exit. Sau đó thử shell wrapper không `exec` để hiểu signal forwarding.

### Bài 10 — Đọc thread dump

Khởi chạy ứng dụng có:

- Một executor chưa shutdown.
- Một scheduler.
- Một custom non-daemon thread.

Đóng context và lấy `jcmd Thread.print`. Phân loại từng thread theo owner và đề xuất callback dừng.

### Bài 11 — Kiểm tra lỗi block trong cleanup

Tạo `@PreDestroy` chờ một latch không được release. Quan sát context shutdown kéo dài.

Sau đó thêm timeout, log failure code và xác nhận process có thể thoát trong ngân sách thời gian.

### Bài 12 — Shutdown khi dependency không khả dụng

Tạo một client giả định có `close()` cần gọi remote endpoint. Làm remote endpoint không phản hồi.

Thêm timeout cho cleanup và giải thích vì sao shutdown không nên chờ remote dependency vô hạn.

### Bài 13 — Prototype resource

Tạo prototype bean mở một resource và được lấy nhiều lần từ factory.

Kiểm tra destroy callback có tự chạy không. Sau đó bổ sung API acquire/release hoặc cơ chế client chịu trách nhiệm đóng.

### Bài 14 — Test context lifecycle

Viết test với `AnnotationConfigApplicationContext` để xác nhận:

- `@PreDestroy` được gọi.
- Executor đã shutdown.
- Executor đã terminated sau khi task kết thúc.

Không chỉ assert `isShutdown()`.

### Bài 15 — Batch app và exit code

Tạo ứng dụng non-web dùng `ApplicationRunner`, xử lý một input và gọi `SpringApplication.exit(context)`.

Kiểm tra exit code cho thành công/thất bại. Xác nhận runner chờ công việc thực sự hoàn tất trước khi đóng context.

### Bài 16 — Thiết kế ngân sách graceful shutdown

Với một service có HTTP requests, message consumer, executor và HTTP client, lập bảng thời gian cho từng giai đoạn.

Đối chiếu tổng thời gian với Kubernetes `terminationGracePeriodSeconds`, xác định thứ tự đóng và những task nào có thể retry sau restart.

## 34. Ghi nhớ

**Đóng Spring ApplicationContext không đồng nghĩa JVM đã kết thúc.** Context chỉ quản lý lifecycle của những bean và resource thuộc phạm vi container. Thread tự tạo, executor ngoài Spring, timer hoặc client do code thủ công tạo vẫn cần owner và cơ chế cleanup riêng.

Spring cung cấp `@PreDestroy`, `DisposableBean`, `@Bean(destroyMethod=...)`, `Lifecycle` và `SmartLifecycle` để dừng component theo lifecycle. Với executor, hãy ngừng nhận task mới, chờ task đang chạy trong timeout, rồi interrupt khi cần; task phải hợp tác với interrupt và có timeout cho I/O.

Với web application, graceful shutdown giúp ngừng nhận traffic mới và cho request đang xử lý hoàn tất trong thời gian giới hạn. Khi chạy container, thời gian này phải phù hợp với SIGTERM handling và `terminationGracePeriodSeconds`. `SIGKILL` không chạy shutdown hooks, vì vậy ứng dụng vẫn cần khả năng phục hồi sau khi bị dừng cưỡng chế.

Khi process không thoát, hãy lấy thread dump và truy thread còn sống về resource owner. Khi cleanup không hoàn tất, kiểm tra callback, dependency order, timeout và việc task có bị block hay không. **Mỗi resource cần một owner, một đường đóng rõ ràng và một giới hạn thời gian có thể quan sát**; đó là nền tảng để ứng dụng Spring Boot dừng sạch sẽ và không để lại tài nguyên ngoài ý muốn.
