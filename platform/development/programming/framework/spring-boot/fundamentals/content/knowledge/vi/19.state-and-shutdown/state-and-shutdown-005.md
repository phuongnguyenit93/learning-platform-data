# Shutdown hook, đóng context và hủy bean

Một ứng dụng Spring Boot không chỉ có quá trình khởi động. Khi tiến trình cần kết thúc, ứng dụng còn phải ngừng nhận việc mới, cho phép các công việc đang chạy hoàn tất trong giới hạn hợp lý, đóng kết nối và giải phóng tài nguyên. Nếu bỏ qua giai đoạn này, ứng dụng có thể mất log đang chờ ghi, bỏ dở một request, để kết nối chưa được đóng hoặc khiến hệ thống bên ngoài không biết consumer đã dừng.

Spring Boot phối hợp quá trình dừng thông qua **JVM shutdown hook**, **đóng `ApplicationContext`**, **các lifecycle component** và **callback hủy bean**. Các cơ chế liên quan nhưng có nhiệm vụ riêng:

- *Shutdown hook* là điểm JVM gọi khi tiến trình kết thúc theo một đường shutdown bình thường.
- *`ApplicationContext.close()`* yêu cầu Spring container đóng, phát event và xử lý lifecycle của các bean do nó quản lý.
- *`SmartLifecycle`* cho thành phần chạy nền hoặc web server cơ hội dừng có thứ tự trước khi các singleton bị hủy.
- *`@PreDestroy`*, `DisposableBean.destroy()` và `@Bean(destroyMethod = "...")` giải phóng tài nguyên của từng bean.

Điểm quan trọng: **JVM shutdown hook chỉ là một cách kích hoạt quá trình đóng context**. Ứng dụng cũng có thể tự gọi `close()`; ngược lại, một tiến trình bị dừng cưỡng bức có thể không có cơ hội thực hiện cleanup. Bài học đi từ sự kiện dừng tiến trình đến thứ tự hủy bean, rồi thực hành với một ứng dụng Spring Boot 3.3 và Java 21.

## 1. Bức tranh tổng thể khi Spring Boot dừng

Khi ứng dụng chạy bằng `SpringApplication.run(...)`, Boot mặc định đăng ký một shutdown hook với JVM. Trong một lần JVM shutdown bình thường, hook được thực thi và yêu cầu đóng context đã đăng ký.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["JVM bắt đầu shutdown bình thường"] --> B["Shutdown hook của Spring Boot chạy"]
    B --> C["Đóng ApplicationContext"]
    C --> D["Phát ContextClosedEvent"]
    D --> E["LifecycleProcessor dừng Lifecycle / SmartLifecycle"]
    E --> F["Hủy singleton bean theo quan hệ phụ thuộc"]
    F --> G["@PreDestroy / DisposableBean / destroy method"]
    G --> H["Đóng bean factory và hoàn tất context"]
    H --> I["Tiến trình có thể kết thúc"]
    J["Code gọi context.close()"] --> C
~~~

Đây là luồng khái quát cho một context được đóng bình thường. Thứ tự chi tiết giữa những bean độc lập, cách một web server dừng request và thời hạn chờ phụ thuộc vào cấu hình lifecycle.

Có hai kiểu quan hệ thứ tự cần phân biệt:

1. **Thứ tự dừng các thành phần chạy**: do `LifecycleProcessor`, `SmartLifecycle` phase và dependency quyết định.
2. **Thứ tự hủy các bean**: do container và dependency graph quyết định; callback hủy của từng bean nằm trong giai đoạn này.

Một `@PreDestroy` không thay thế cho việc dừng listener đang nhận message. Nếu listener cần ngừng nhận việc rồi mới đóng resource, hãy thiết kế hai bước đó bằng lifecycle API phù hợp.

## 2. Shutdown hook là gì?

JVM cho phép đăng ký các thread đặc biệt bằng `Runtime.getRuntime().addShutdownHook(...)`. Khi JVM bắt đầu một quá trình shutdown thông thường, các hook đã đăng ký có cơ hội chạy để thực hiện công việc dọn dẹp.

Ví dụ Java thuần:

~~~java
public class PlainJavaShutdown {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("JVM is shutting down"))
        );

        System.out.println("Application started");
    }
}
~~~

Trong một ứng dụng Spring Boot thông thường, bạn **không cần tự tạo một hook chỉ để gọi `ApplicationContext.close()`**. `SpringApplication` đã thực hiện việc đăng ký hook cho context theo mặc định.

### 2.1. Khi nào shutdown hook có cơ hội chạy?

Các tình huống thường khiến JVM bắt đầu shutdown có tổ chức:

- Code gọi `System.exit(...)`.
- Tiến trình Java nhận tín hiệu chấm dứt thông thường như `SIGTERM` trong môi trường hỗ trợ.
- Người dùng nhấn Ctrl+C trong console, nếu JVM nhận được tín hiệu ngắt theo đường shutdown thông thường.
- Một công cụ quản lý tiến trình gửi tín hiệu dừng mà JVM có thể xử lý.
- JVM kết thúc theo quá trình shutdown thông thường khi không còn thread không-daemon.

Trên máy Windows, cách IDE hoặc terminal dừng process có thể khác Linux. Không nên giả định mọi nút Stop trong IDE đều tạo ra cùng một chuỗi lifecycle.

### 2.2. Những trường hợp hook có thể không chạy

Shutdown hook là cơ chế **best effort**, không phải cam kết mọi lần tiến trình biến mất đều được cleanup.

| Cách kết thúc | Có thể trông đợi hook? | Ghi chú |
| --- | --- | --- |
| `System.exit(0)` | Thông thường có | JVM bước vào chuỗi shutdown |
| `SIGTERM` thông thường | Thông thường có | Phù hợp với nhiều hệ thống deploy |
| Ctrl+C trong console | Thường có | Phụ thuộc cách console và JVM nhận tín hiệu |
| `SIGKILL` / `kill -9` | Không | Hệ điều hành dừng tiến trình cưỡng bức |
| `Runtime.getRuntime().halt(...)` | Không | Bỏ qua trình tự shutdown hook |
| Mất điện, container bị kill cưỡng bức | Không bảo đảm | Không thể dựa vào callback cuối cùng |
| JVM crash nghiêm trọng | Không bảo đảm | Tiến trình có thể mất khả năng thực thi cleanup |

Vì vậy không nên đặt một thao tác **duy nhất đảm bảo lưu dữ liệu quan trọng** trong `@PreDestroy` hoặc shutdown hook. Trạng thái cần bền vững phải được ghi trong lúc ứng dụng hoạt động, với transaction, acknowledgment, checkpoint hoặc cơ chế tương ứng.

### 2.3. Không dựa vào thứ tự giữa các JVM hook khác nhau

Nhiều thư viện có thể tự đăng ký shutdown hook. JVM không cung cấp một thứ tự tuần tự dễ dự đoán giữa mọi hook: chúng có thể bắt đầu thực thi đồng thời.

Nếu hai tài nguyên phải được dừng theo thứ tự xác định, hãy quản lý chúng qua cùng Spring context và lifecycle/dependency graph. Tránh tạo nhiều shutdown hook độc lập rồi trông chờ hook A luôn hoàn tất trước hook B.

## 3. SpringApplication đăng ký hook như thế nào?

Cách khởi động quen thuộc:

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemoApplication.class, args);
    }
}
~~~

Theo mặc định, Spring Boot đăng ký shutdown hook để đóng `ApplicationContext` khi JVM kết thúc. Các callback lifecycle tiêu chuẩn của Spring được gọi trong quá trình đóng context.

Bạn có thể điều khiển hành vi đăng ký hook khi tự tạo `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(ShutdownDemoApplication.class);

application.setRegisterShutdownHook(false);

ConfigurableApplicationContext context = application.run(args);
~~~

Ví dụ chỉ cho thấy API cấu hình. **Nếu tắt hook**, code sở hữu context phải tự bảo đảm đóng context tại thời điểm thích hợp. Nếu không, bean hạ tầng có thể không nhận destruction callback theo đường bình thường.

Trong phần lớn ứng dụng web Spring Boot, hãy giữ mặc định. Chỉ tắt khi có một lifecycle owner khác đã được thiết kế rõ, chẳng hạn test harness hoặc một tiến trình nhúng Spring context và chủ động gọi `close()`.

### 3.1. Có nên tự thêm Runtime shutdown hook?

Không cần cho ứng dụng Boot thông thường:

~~~java
// Tránh tạo hook thứ hai nếu chỉ muốn đóng cùng context.
Runtime.getRuntime().addShutdownHook(
        new Thread(context::close)
);
~~~

Hook bổ sung có thể gây khó hiểu vì ai sở hữu context, thứ tự cleanup và việc đóng lặp. Nếu muốn thực hiện một hành động khi Spring context đóng, dùng `ContextClosedEvent`, `SmartLifecycle` hoặc callback hủy bean theo mục đích.

### 3.2. Shutdown hook không giữ ứng dụng chạy mãi

Hook chỉ chạy khi JVM **đang dừng**. Nó không phải một non-daemon worker giữ process sống. Một ứng dụng batch không có non-daemon thread nào khác có thể tự kết thúc và JVM sẽ thực thi hook.

Trong các cấu hình Java 21 dùng virtual thread, những thread đó là daemon thread; chỉ dùng virtual threads không tự bảo đảm JVM tiếp tục chạy. Với ứng dụng có nhu cầu giữ tiến trình sống, hãy dùng cơ chế lifecycle phù hợp của Spring Boot thay vì xem shutdown hook là worker thường trực.

## 4. Đóng ApplicationContext bằng code

`ApplicationContext` là abstraction đọc bean và truy cập dịch vụ container. Interface `ConfigurableApplicationContext` bổ sung các thao tác quản lý lifecycle như `refresh()`, `start()`, `stop()` và `close()`.

Một ứng dụng CLI có thể chủ động mở và đóng context:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public class CliLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliConfiguration.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setRegisterShutdownHook(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            ImportService service = context.getBean(ImportService.class);
            service.importData();
        } // Tự gọi context.close(), kể cả khi importData ném exception.
    }
}
~~~

Ví dụ giả định `CliConfiguration` và `ImportService` đã được ứng dụng định nghĩa. `ConfigurableApplicationContext` triển khai `AutoCloseable` nên có thể dùng trong `try-with-resources`.

Đối với ứng dụng web cần phục vụ HTTP lâu dài, **không đặt context trong `try-with-resources` kết thúc ngay sau `run()`**; làm vậy sẽ đóng web server ngay khi khởi động xong. Context phải sống đến khi ứng dụng thực sự được yêu cầu dừng.

### 4.1. close() và stop() có giống nhau không?

Không.

| Thao tác | Ý nghĩa |
| --- | --- |
| `context.start()` | Chuyển tín hiệu start đến các bean tham gia `Lifecycle` |
| `context.stop()` | Chuyển tín hiệu stop đến các bean `Lifecycle`; context chưa bị đóng hẳn |
| `context.close()` | Đóng context, phát event đóng, dừng lifecycle và hủy singleton |
| `context.isActive()` | Cho biết context đang active theo lifecycle của nó |
| `System.exit(code)` | Yêu cầu JVM kết thúc; hook có thể đóng context nếu đã đăng ký |

`context.stop()` không tương đương destruction. Một bean có `@PreDestroy` **không được gọi chỉ vì context.stop()**. Khi context được start lại, một số lifecycle component có thể tiếp tục hoạt động theo hợp đồng của chúng.

`context.close()` là thao tác kết thúc vòng đời context. Sau khi đóng, không nên tiếp tục truy cập bean như một context còn hoạt động hoặc giả định có thể refresh lại context đó tùy ý.

### 4.2. Có thể close() nhiều lần không?

Spring có cơ chế bảo vệ lifecycle khi đóng context. Tuy nhiên, callback cleanup của ứng dụng vẫn nên được viết **an toàn khi tài nguyên đã đóng** và tránh tạo race giữa shutdown hook, test và các worker. Không nên cố ý gọi close nhiều nơi chỉ để phòng ngừa; hãy xác định một lifecycle owner rõ ràng.

## 5. Trình tự bên trong ApplicationContext.close()

Trong một context Spring thông thường, giai đoạn đóng có thứ tự khái quát:

1. Spring xác định context đang active và bắt đầu chu trình đóng.
2. Phát `ContextClosedEvent`.
3. Yêu cầu `LifecycleProcessor` dừng những component tham gia lifecycle.
4. Hủy các singleton bean, tuân theo dependency graph.
5. Đóng bean factory và hoàn tất công việc dọn dẹp của context.
6. Context không còn được dùng như một container active.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant Caller as JVM hook / caller
    participant Context as ApplicationContext
    participant Events as Event listeners
    participant Life as LifecycleProcessor
    participant Beans as Singleton bean registry
    Caller->>Context: close()
    Context->>Events: ContextClosedEvent
    Events-->>Context: Listener callbacks kết thúc
    Context->>Life: onClose()
    Life->>Life: Dừng SmartLifecycle / Lifecycle theo phase
    Life-->>Context: Stop hoàn tất hoặc hết thời hạn chờ
    Context->>Beans: destroySingletons()
    Beans->>Beans: Hủy dependent trước dependency
    Beans-->>Context: Destruction callbacks kết thúc
    Context-->>Caller: Context đóng
~~~

Không nên suy ra rằng mọi background task chắc chắn đã hoàn tất trước bước destroy chỉ vì event đóng được phát. Điều đó phụ thuộc cách `SmartLifecycle.stop(...)`, executor, listener container và timeout được triển khai.

### 5.1. ContextClosedEvent được phát lúc nào?

`ContextClosedEvent` là event của Spring Framework, được phát khi context bắt đầu đóng, **trước khi giai đoạn dừng các lifecycle bean và hủy singleton hoàn tất**.

Ví dụ:

~~~java
package com.example.shutdown;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownEventLogger {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println(
                "Closing context: " + event.getApplicationContext().getId()
        );
    }
}
~~~

Dùng event cho việc quan sát, ghi log, thông báo trong nội bộ process hoặc các phản ứng ngắn, có kiểm soát. Đừng dùng event listener để gọi quá nhiều service, yêu cầu tạo bean mới hoặc thực hiện một tác vụ mạng kéo dài. Context đang trong giai đoạn đóng và một số phụ thuộc có thể sắp bị dừng.

### 5.2. ContextStoppedEvent khác ContextClosedEvent

`ContextStoppedEvent` có thể được phát khi một context được `stop()`. Nó biểu thị tín hiệu dừng lifecycle mà không đồng nghĩa giải phóng toàn bộ bean.

`ContextClosedEvent` biểu thị một lần đóng context. Các destruction callback của singleton thuộc đường `close()`, không thuộc chỉ riêng `stop()`.

Nếu yêu cầu là ngừng một consumer nhưng muốn context tiếp tục tồn tại, có thể dùng API start/stop của component. Nếu yêu cầu là giải phóng toàn bộ tài nguyên ứng dụng, cần đóng context.

## 6. Hủy bean bằng @PreDestroy

`@PreDestroy` đánh dấu method được Spring gọi trong giai đoạn hủy một bean có lifecycle được container quản lý. Với Spring Boot 3.x và Jakarta namespace, import:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Ví dụ một bean sở hữu resource:

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class LocalResourceManager {
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public void useResource() {
        if (closed.get()) {
            throw new IllegalStateException("Resource is closed");
        }
        // Thao tác với resource.
    }

    @PreDestroy
    public void cleanup() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("Releasing LocalResourceManager");
            // Đóng file handle, kết nối hoặc tài nguyên thuộc sở hữu bean.
        }
    }
}
~~~

Method cleanup được gọi khi singleton bean này bị hủy trong quá trình đóng context. `AtomicBoolean` là ví dụ tạo thao tác cleanup idempotent; mã thực tế phải bảo đảm không có luồng khác tiếp tục dùng resource sau khi đóng.

### 6.1. Nên làm gì trong @PreDestroy?

Một số công việc phù hợp:

- Đóng stream hoặc resource do bean trực tiếp sở hữu.
- Đóng một client hoặc adapter khi không có cơ chế lifecycle riêng.
- Flush buffer trong giới hạn thời gian đã định.
- Gỡ listener/registration mà bean đã đăng ký.
- Ghi một log ngắn phục vụ chẩn đoán.

Không nên đặt logic nghiệp vụ quan trọng chỉ chạy lúc JVM dừng vào method này. Callback có thể không chạy khi tiến trình bị kill cưỡng bức.

### 6.2. Method @PreDestroy không nhận tham số

Method annotated `@PreDestroy` thông thường là method không có tham số và có kiểu trả về `void`. Không mong Spring inject service hoặc shutdown event như tham số method này.

Nếu cần dependency trong cleanup, hãy inject nó qua constructor khi tạo bean và quản lý thứ tự hủy theo quan hệ phụ thuộc.

### 6.3. Có phải mọi bean đều được gọi @PreDestroy?

Không. Destruction callback áp dụng cho bean mà container thực sự quản lý ở scope có lifecycle destruction tương ứng. Với singleton được tạo và còn trong context khi đóng, Spring gọi callback hủy theo contract.

Với prototype, Spring quản lý quá trình tạo và initialization nhưng **không tự động gọi destruction callback** sau khi trả instance cho caller. Caller hoặc một owner thích hợp phải tự cleanup.

Với request/session scoped bean, vòng đời target và callback hủy thuộc scope tương ứng; chúng không tương đương với một singleton sống đến khi application context đóng.

## 7. DisposableBean và @Bean(destroyMethod)

Ngoài `@PreDestroy`, Spring còn hỗ trợ các cách khai báo cleanup khác.

### 7.1. DisposableBean

Bean có thể implement interface của Spring:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class RemoteConnection implements DisposableBean {
    private boolean open = true;

    @Override
    public void destroy() {
        if (open) {
            open = false;
            // Giải phóng kết nối bên ngoài.
        }
    }
}
~~~

Khi bean được container hủy, Spring gọi `destroy()`. Cách này rõ về lifecycle, nhưng làm class phụ thuộc trực tiếp vào Spring Framework. Với code nghiệp vụ hoặc thư viện Java thuần, `@PreDestroy` hoặc phương thức đóng thông thường thường dễ tái sử dụng hơn.

### 7.2. @Bean(destroyMethod = "close")

Khi tạo object từ thư viện không kiểm soát được source, có thể chỉ định method hủy trong Java configuration:

~~~java
public class ExternalClient implements AutoCloseable {
    private boolean open = true;

    public String fetch() {
        if (!open) {
            throw new IllegalStateException("Client is closed");
        }
        return "data";
    }

    @Override
    public void close() {
        open = false;
        // Giải phóng tài nguyên.
    }
}
~~~

Đăng ký bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Khi context hủy singleton `externalClient`, Spring gọi `close()` theo metadata. Class `ExternalClient` vẫn là Java thuần.

### 7.3. Suy luận close/shutdown cho bean từ @Bean

Với `@Bean` trong Java configuration, Spring mặc định có thể **suy luận** destruction method như `close` hoặc `shutdown`; implementation `AutoCloseable` hoặc `Closeable` cũng được hỗ trợ.

Ví dụ:

~~~java
@Bean
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

Nếu `ExternalClient` có method đóng được nhận diện, Spring có thể gọi nó khi hủy bean mà không cần khai báo tường minh `destroyMethod = "close"`.

Khi bạn muốn vô hiệu hóa suy luận destruction method cho một bean đặc biệt:

~~~java
@Bean(destroyMethod = "")
ExternalClient externallyManagedClient() {
    return externallyOwnedClient;
}
~~~

Chỉ dùng nếu resource **thực sự được quản lý ở nơi khác**. Bỏ callback mà không có owner thay thế sẽ tạo nguy cơ rò rỉ resource.

### 7.4. Thứ tự callback trong cùng một bean

Nếu một bean đồng thời khai báo nhiều cách hủy, thứ tự thông dụng là:

1. Method `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method được chỉ định.

Ví dụ một class vừa có `@PreDestroy` vừa implement `DisposableBean` và khai báo custom `close` có thể nhận nhiều callback trong cùng một lần hủy. Nếu cả ba cùng đóng một resource, bạn có thể vô tình giải phóng lặp.

Hãy chọn một cơ chế chính hoặc thiết kế method cleanup gọi chung tới thao tác idempotent. Không nên khai báo nhiều callback chỉ để “chắc chắn được gọi”.

## 8. Thứ tự hủy giữa các bean

Nếu bean A phụ thuộc vào bean B, A thường cần được hủy **trước** B để B còn khả dụng trong quá trình cleanup của A.

Ví dụ:

~~~java
@Component
public class ConnectionManager {
    @PreDestroy
    public void close() {
        System.out.println("ConnectionManager closed");
    }
}

@Component
public class ReportConsumer {
    private final ConnectionManager manager;

    public ReportConsumer(ConnectionManager manager) {
        this.manager = manager;
    }

    @PreDestroy
    public void close() {
        System.out.println("ReportConsumer closed");
    }
}
~~~

Quan hệ qua constructor khiến Spring biết `ReportConsumer` phụ thuộc `ConnectionManager`. Với hai singleton được container quản lý, dependent `ReportConsumer` được hủy trước dependency `ConnectionManager`.

~~~mermaid
flowchart LR
    A["Khởi tạo: ConnectionManager"] --> B["Khởi tạo: ReportConsumer"]
    C["Hủy: ReportConsumer"] --> D["Hủy: ConnectionManager"]
~~~

### 8.1. @DependsOn khi quan hệ chỉ là thứ tự

Đôi khi bean không giữ tham chiếu đến một bean khác nhưng cần initializer sẵn sàng trước khi khởi tạo. Có thể khai báo:

~~~java
@Component("providerRegistry")
public class ProviderRegistry {
    @PostConstruct
    void initialize() {
        // Đăng ký provider trong thư viện cũ.
    }

    @PreDestroy
    void shutdown() {
        // Gỡ provider sau khi dependent đã đóng.
    }
}

@Component
@DependsOn("providerRegistry")
public class LegacyClient {
    @PreDestroy
    void close() {
        // Client phải đóng trước khi providerRegistry bị hủy.
    }
}
~~~

`@DependsOn` ép `providerRegistry` được khởi tạo trước `LegacyClient` và giúp Spring ghi nhận thứ tự hủy ngược cho các singleton. Nó không tự inject reference.

Nếu client thực sự cần gọi API của registry, constructor injection thường rõ hơn. Nếu chỉ có quan hệ thứ tự side effect, `@DependsOn` là công cụ phù hợp.

### 8.2. Không dựa vào thứ tự tình cờ của các bean độc lập

Hai singleton không phụ thuộc nhau có thể bị hủy theo một thứ tự quan sát được trong một lần chạy, nhưng không nên xem đó là hợp đồng nghiệp vụ cố định.

Nếu cleanup của A cần B vẫn còn sống, hãy biểu diễn quan hệ dependency. Đừng dùng thứ tự tên class, thứ tự khai báo file hoặc thứ tự log để suy ra bảo đảm của container.

## 9. SmartLifecycle: dừng công việc trước khi hủy resource

Nhiều component không chỉ giữ tài nguyên; chúng **chủ động chạy**: consumer lắng nghe message, scheduler, embedded server, polling thread hoặc một integration endpoint.

Nếu chỉ gọi `@PreDestroy` để đóng kết nối trong khi worker vẫn xử lý message, có thể sinh lỗi. Spring cung cấp `Lifecycle` và `SmartLifecycle` để quản lý các component có khả năng start/stop.

`SmartLifecycle` thuộc package:

~~~java
import org.springframework.context.SmartLifecycle;
~~~

Những method quan trọng:

| Method | Ý nghĩa |
| --- | --- |
| `start()` | Khởi chạy component |
| `stop()` | Dừng component theo contract `Lifecycle` |
| `stop(Runnable callback)` | Dừng và báo cho lifecycle processor khi hoàn tất |
| `isRunning()` | Trạng thái component đang chạy |
| `isAutoStartup()` | Có tự khởi chạy khi context refresh không |
| `getPhase()` | Phase điều khiển thứ tự start/stop |

### 9.1. Ví dụ một worker nhỏ

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class MessagePollingWorker implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        running.set(true);
        System.out.println("Worker started");
    }

    @Override
    public void stop() {
        running.set(false);
        System.out.println("Worker stopped");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
            // Với worker thực, đợi các tác vụ đang chạy hoàn tất
            // trong giới hạn cho phép trước khi gọi callback.
        } finally {
            callback.run();
        }
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
        return 100;
    }

    @PreDestroy
    public void releaseResources() {
        System.out.println("Worker resources released");
    }
}
~~~

Đây là skeleton minh họa thứ tự callback; nó không tạo executor hoặc message consumer thật. Với worker thực tế, `running.set(false)` chỉ đổi một cờ, chưa đủ để chờ tác vụ đang xử lý. Phần dừng thực phải ngừng nhận việc mới và hoàn tất hoặc hủy những việc hiện có theo hợp đồng của hệ thống.

Khi đóng context, phần dừng `SmartLifecycle` xảy ra trước `@PreDestroy`. Nhờ đó, component có cơ hội ngừng hoạt động trước khi resource bị giải phóng.

### 9.2. Phải gọi callback khi stop(Runnable) hoàn tất

`stop(Runnable callback)` có ý nghĩa phối hợp không đồng bộ. Sau khi một component đã dừng xong, nó phải gọi `callback.run()` để thông báo cho `LifecycleProcessor`.

Nếu không gọi callback, container có thể phải chờ đến timeout của phase. Nếu gọi callback quá sớm, Spring có thể chuyển sang dừng các component khác hoặc hủy bean khi worker vẫn đang xử lý.

Một thiết kế asynchronous hợp lý:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewMessages();

    drainExecutor.execute(() -> {
        try {
            waitForInFlightMessages();
        } finally {
            running.set(false);
            callback.run();
        }
    });
}
~~~

Đây là pseudocode ở mức method: `stopAcceptingNewMessages()`, `drainExecutor` và `waitForInFlightMessages()` cần được định nghĩa trong implementation thực. Cần tránh dùng chính executor sắp bị đóng để lên lịch công việc cleanup, nếu nó có thể từ chối task.

### 9.3. SmartLifecycle phase

Các component có phase thấp thường **start trước** phase cao và **stop sau** phase cao. Khi dừng, phase cao được xử lý trước phase thấp.

Ví dụ:

| Component | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Connection manager | 0 | Trước | Sau |
| Message consumer | 100 | Sau | Trước |

Nếu consumer cần connection manager còn hoạt động khi dừng, sơ đồ trên hợp lý. Ngoài phase, Spring cũng xét quan hệ dependency/depends-on giữa các lifecycle bean.

Không nên gán phase tùy tiện cho mọi service. Chỉ dùng khi component có start/stop lifecycle rõ ràng và thứ tự thực sự có ý nghĩa.

## 10. Graceful shutdown cho HTTP server

Với ứng dụng web, shutdown không chỉ là đóng Spring beans. Server có thể đang xử lý request; một response quan trọng có thể chưa hoàn tất khi tiến trình nhận lệnh dừng.

Spring Boot 3.3 hỗ trợ **graceful shutdown** cho các embedded web server phổ biến, bao gồm Servlet và Reactive stack. Với Boot 3.3, bạn bật cơ chế này bằng cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Tương đương trong properties:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong Boot 3.3, `server.shutdown=graceful` là cấu hình cần bật cho graceful shutdown của web server. Ở các phiên bản Boot khác, mặc định có thể thay đổi, vì vậy hãy đối chiếu đúng phiên bản dự án.

### 10.1. Graceful shutdown thực hiện việc gì?

Khi context đóng, Spring Boot dừng web server qua cơ chế lifecycle. Khi graceful shutdown được bật, web server cố gắng:

1. Ngừng chấp nhận request mới hoặc từ chối request mới theo cách server hỗ trợ.
2. Cho phép các request đang xử lý hoàn tất trong khoảng thời gian chờ cấu hình.
3. Tiếp tục chuỗi dừng lifecycle và hủy bean sau khi giai đoạn chờ kết thúc.

~~~mermaid
sequenceDiagram
    participant Platform as Process manager
    participant Boot as Spring Boot
    participant Server as Web server
    participant Request as In-flight request
    Platform->>Boot: SIGTERM / shutdown
    Boot->>Boot: close context
    Boot->>Server: Graceful stop
    Server->>Server: Ngừng nhận request mới
    Request->>Server: Hoàn tất trong grace period
    Server-->>Boot: Stop hoàn tất hoặc timeout
    Boot->>Boot: Hủy singleton bean
    Boot-->>Platform: Tiến trình kết thúc
~~~

Cách từ chối request mới tùy server. Chẳng hạn Tomcat, Jetty và Reactor Netty thường dừng nhận ở tầng mạng; Undertow có thể trả HTTP 503 cho kết nối mới trong giai đoạn shutdown.

### 10.2. Timeout per shutdown phase

Property `spring.lifecycle.timeout-per-shutdown-phase` là thời hạn chờ của các phase `SmartLifecycle`. Trong ví dụ, mỗi phase được phép có thời gian dừng tương ứng theo cơ chế của Spring.

Nó không phải một cam kết rằng toàn bộ process sẽ kết thúc trong đúng 20 giây. Những phần khác như event listener, destruction callback hoặc code cleanup tự viết có thể tiêu tốn thêm thời gian. Process manager hoặc hệ thống orchestration cũng có thể có timeout riêng.

Chọn timeout dựa trên thời gian xử lý request/job thực tế, không dùng giá trị thật lớn chỉ để che một tác vụ không có cơ chế dừng.

### 10.3. Graceful shutdown không phải bảo đảm hoàn tất mọi request

Một request có thể vượt quá grace period, một dependency ngoài có thể bị treo hoặc một client có thể đã ngắt kết nối. Ứng dụng cần thiết kế idempotency, timeout, transaction boundary và retry phù hợp.

Đặc biệt, đừng dựa vào HTTP graceful shutdown để bảo đảm một payment event đã được lưu bền vững. Việc ghi dữ liệu và xác nhận nghiệp vụ phải có bảo đảm độc lập với quá trình process shutdown.

## 11. Shutdown trong container và Kubernetes

Khi chạy trong Docker hoặc Kubernetes, việc shutdown diễn ra qua nhiều tầng:

~~~mermaid
flowchart TD
    A["Orchestrator quyết định dừng instance"] --> B["Ngừng định tuyến / thay đổi readiness"]
    B --> C["Gửi tín hiệu termination tới process"]
    C --> D["JVM shutdown hook đóng Spring context"]
    D --> E["Graceful stop và destruction callbacks"]
    E --> F{"Đã dừng trong grace period?"}
    F -->|Có| G["Process kết thúc sạch"]
    F -->|Không| H["Orchestrator cưỡng bức kết thúc"]
~~~

Trình tự thực tế của readiness, endpoint removal và signal delivery phụ thuộc nền tảng, cấu hình và độ trễ cập nhật. Không giả định ngay sau khi bắt đầu shutdown thì mọi load balancer đã ngừng gửi traffic.

### 11.1. SIGTERM và thời hạn dừng của nền tảng

Kubernetes thường cho container một termination grace period trước khi buộc dừng. Hãy để tổng thời gian drain request, dừng consumer và cleanup nằm trong giới hạn đó.

Nếu Spring Boot được cấu hình chờ 30 giây nhưng orchestrator cưỡng bức kết thúc sau 10 giây, quá trình cleanup có thể bị cắt ngang. Đừng chỉ cấu hình timeout ở một phía.

### 11.2. Process phải nhận tín hiệu

Trong Docker, cách viết entrypoint và wrapper shell ảnh hưởng việc tín hiệu tới tiến trình Java. Một cấu hình phổ biến là dùng exec form để tiến trình Java nhận signal đúng cách:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Nếu dùng script làm entrypoint, script cần quản lý signal và child process cẩn thận. Một shell wrapper không chuyển tiếp tín hiệu có thể khiến JVM không đi qua shutdown hook như mong đợi.

### 11.3. Readiness và graceful shutdown phục vụ hai mục đích

- *Readiness* giúp hệ thống điều phối quyết định có tiếp tục gửi request tới instance hay không.
- *Graceful shutdown* giúp instance xử lý request đang tồn tại và dừng tài nguyên có trật tự.

Cần cả hai khi triển khai service phục vụ lưu lượng thật. Chỉ bật graceful shutdown không đồng nghĩa load balancer sẽ tức thì ngừng định tuyến tới instance.

## 12. SpringApplication.exit và exit code

Với ứng dụng CLI hoặc batch, sau khi công việc kết thúc, bạn có thể muốn đóng context và trả mã thoát có ý nghĩa cho hệ điều hành.

Spring Boot cung cấp:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

Method này tính exit code theo các `ExitCodeGenerator` và đóng context nếu có thể. Muốn biến mã đó thành exit code của JVM, gọi `System.exit(exitCode)`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(BatchApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

Ví dụ giả định công việc batch chạy qua `ApplicationRunner` hoặc `CommandLineRunner` trong quá trình `SpringApplication.run(...)`. Nếu job chạy bất đồng bộ sau đó, bạn phải chờ nó hoàn tất trước khi gọi exit.

### 12.1. ExitCodeGenerator

Một bean có thể cung cấp exit code:

~~~java
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExitConfiguration {

    @Bean
    ExitCodeGenerator exitCodeGenerator() {
        return () -> 0;
    }
}
~~~

Trong ứng dụng thực tế, exit code thường phản ánh kết quả job. Số 0 thường biểu thị thành công, còn các giá trị khác 0 thể hiện lỗi theo contract của hệ thống gọi.

Lưu ý: `System.exit(...)` yêu cầu JVM kết thúc; `SpringApplication.exit(...)` chủ yếu tính exit code và đóng context. Hai method không thay thế nhau hoàn toàn.

### 12.2. Đừng gọi System.exit() từ một @PreDestroy

Gọi `System.exit()` bên trong callback đang chạy trong quá trình shutdown có thể gây hành vi khó kiểm soát. Hãy để lớp launcher hoặc process owner quyết định exit code và yêu cầu process kết thúc; bean tập trung vào cleanup tài nguyên mà nó sở hữu.

## 13. Bean scope và destruction callback

Scope quyết định container quản lý instance đến giai đoạn nào.

| Scope | Ai quản lý thời điểm hủy? | Điều cần nhớ |
| --- | --- | --- |
| `singleton` | Spring context khi bean bị hủy/context đóng | `@PreDestroy` và destroy method được gọi theo contract |
| `prototype` | Chủ yếu do code nhận instance chịu trách nhiệm | Spring không tự thực hiện destruction callback sau khi cấp instance |
| `request` | Web request scope | Target được hủy theo vòng đời request, nếu được scope quản lý |
| `session` | Web session scope | Target theo vòng đời HTTP session tương ứng |
| `application` | Web application scope | Target theo vòng đời ServletContext/application scope |

Một prototype được inject một lần vào singleton constructor sẽ trở thành một reference được giữ bởi singleton, chứ không tự tạo prototype mới mỗi lần singleton gọi method. Nếu prototype sở hữu resource cần đóng, hãy xác định owner của instance đó hoặc dùng factory/provider cùng quản lý cleanup rõ ràng.

Với request-scoped proxy, bean singleton thường giữ **proxy**, còn target request-scoped có vòng đời riêng. Đừng kỳ vọng `@PreDestroy` của target chỉ chạy khi toàn bộ application dừng.

### 13.1. Lazy singleton chưa được tạo

Một singleton `@Lazy` chưa từng được khởi tạo không có instance để chạy `@PreDestroy`. Vì thế không nên đặt một tác vụ bắt buộc phải luôn chạy vào callback của bean có thể chưa được tạo.

Nếu công việc cần chạy dù bean chưa từng được sử dụng, cần một lifecycle owner rõ ràng, không chỉ trông chờ bean destruction.

## 14. Ví dụ kiểm tra thứ tự hủy bean

Có thể dùng một context nhỏ để quan sát init/destroy theo quan hệ `@DependsOn` mà không cần chạy HTTP server.

Định nghĩa collector:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LifecycleLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Resource:

~~~java
public class TransportResource {
    private final LifecycleLog log;

    public TransportResource(LifecycleLog log) {
        this.log = log;
    }

    public void initialize() {
        log.add("transport:init");
    }

    public void close() {
        log.add("transport:close");
    }
}
~~~

Consumer:

~~~java
public class TransportConsumer {
    private final LifecycleLog log;

    public TransportConsumer(LifecycleLog log) {
        this.log = log;
    }

    public void initialize() {
        log.add("consumer:init");
    }

    public void close() {
        log.add("consumer:close");
    }
}
~~~

Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class LifecycleTestConfiguration {

    @Bean
    LifecycleLog lifecycleLog() {
        return new LifecycleLog();
    }

    @Bean(initMethod = "initialize", destroyMethod = "close")
    TransportResource transportResource(LifecycleLog log) {
        return new TransportResource(log);
    }

    @Bean(initMethod = "initialize", destroyMethod = "close")
    @DependsOn("transportResource")
    TransportConsumer transportConsumer(LifecycleLog log) {
        return new TransportConsumer(log);
    }
}
~~~

`TransportConsumer` không inject `TransportResource` trực tiếp; `@DependsOn` chỉ khai báo yêu cầu về thứ tự.

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class BeanDestructionOrderTest {

    @Test
    void dependentIsDestroyedBeforeItsDependency() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleTestConfiguration.class
                );

        LifecycleLog log = context.getBean(LifecycleLog.class);

        try {
            assertEquals(
                    List.of("transport:init", "consumer:init"),
                    log.snapshot()
            );
        } finally {
            context.close();
        }

        assertEquals(
                List.of(
                        "transport:init",
                        "consumer:init",
                        "consumer:close",
                        "transport:close"
                ),
                log.snapshot()
        );
    }
}
~~~

Test minh họa rằng hủy singleton diễn ra theo chiều ngược lại quan hệ dependency. Nó không kiểm tra JVM shutdown hook; test chủ động gọi `context.close()` nên có kết quả ổn định mà không cần kết thúc JVM.

### 14.1. Kiểm tra ContextClosedEvent và @PreDestroy

Một bài test khác có thể đăng ký listener cho `ContextClosedEvent` và một bean `@PreDestroy` để ghi vào collector. Sau khi gọi `close()`, kiểm tra event đóng được nhận trước callback hủy của singleton.

Để test gọn, dùng `AnnotationConfigApplicationContext`. Không nên tạo `System.exit(...)` trong unit test vì nó có thể kết thúc cả JVM chạy bộ test.

## 15. Quan sát shutdown trong ứng dụng web

Thử một ứng dụng Boot 3.3 có Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Cấu hình:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Thêm một endpoint giả lập công việc có thời gian xử lý:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(5000);
        return "completed";
    }
}
~~~

`Thread.sleep` chỉ dùng để minh họa request đang xử lý; trong ứng dụng thật, không nên cố ý block server thread khi không cần thiết, đặc biệt với reactive stack.

Quy trình quan sát bằng tay:

1. Chạy ứng dụng từ terminal để có thể gửi tín hiệu dừng bình thường.
2. Gửi request tới `/slow`.
3. Khi request còn đang xử lý, gửi tín hiệu dừng thích hợp cho process.
4. Quan sát request hiện tại có thể hoàn tất trong grace period.
5. Quan sát log của context shutdown và destruction callback của một bean `@PreDestroy`.
6. Thử rút timeout hoặc kéo dài request để thấy giới hạn của graceful shutdown.

Không nên dùng `kill -9` để kiểm tra graceful shutdown; nó bỏ qua đường shutdown thông thường và có thể làm kết luận sai.

### 15.1. Log thứ tự cleanup

Ví dụ:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CleanupLogger {

    @PreDestroy
    public void onShutdown() {
        System.out.println("CleanupLogger: @PreDestroy called");
    }
}
~~~

Khi context đóng bình thường, log trên giúp xác nhận callback hủy của bean được gọi. Nhưng log này chỉ xác nhận một callback đã chạy, không chứng minh mọi request hay mọi giao dịch ngoài đã hoàn tất.

### 15.2. Có cần tự gọi close() khi nhấn Ctrl+C?

Không, với một ứng dụng `SpringApplication` thông thường giữ cấu hình mặc định. JVM shutdown hook của Boot có nhiệm vụ đóng context khi process đi qua đường shutdown có tổ chức.

Nếu bạn tạo nhiều context độc lập thủ công, hãy xác định context nào được hook quản lý và context nào cần được owner khác đóng.

## 16. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@PreDestroy` không chạy | Process bị kill cưỡng bức hoặc bean không được Spring quản lý | Kiểm tra cách dừng process và ownership |
| `@PreDestroy` không chạy với prototype | Spring không tự hủy prototype sau khi cấp instance | Caller quản lý cleanup |
| Context đóng ngay sau startup | `try-with-resources` kết thúc ngay sau `run()` trong ứng dụng web | Giữ context sống đến thời điểm shutdown |
| Listener vẫn nhận việc sau tín hiệu dừng | Chưa có cơ chế stop/quiesce thích hợp | Dùng `SmartLifecycle` hoặc cơ chế listener container |
| Connection pool đóng trước consumer | Thiếu hoặc sai quan hệ dependency/phase | Biểu diễn dependency và lifecycle order |
| Shutdown treo lâu | `stop(Runnable)` không gọi callback hoặc chờ I/O vô hạn | Hoàn tất callback, đặt timeout và kiểm soát stop |
| Container bị kill trước khi cleanup xong | Orchestrator grace period ngắn hơn tổng thời gian dừng | Điều chỉnh timeout và giảm thời gian xử lý |
| Request mới vẫn tới instance đang dừng | Readiness/load balancer chưa ngừng route ngay | Phối hợp readiness, draining và graceful shutdown |
| Đóng resource hai lần | Nhiều destruction callback cùng giải phóng tài nguyên | Dùng một callback chính hoặc cleanup idempotent |
| Không thấy ContextClosedEvent | Context chưa đóng, listener chưa được đăng ký hoặc JVM bị dừng cưỡng bức | Kiểm tra lifecycle và signal |
| `context.stop()` không gọi `@PreDestroy` | Stop không phải destroy | Gọi `close()` khi thật sự cần kết thúc context |
| Bean không còn khả dụng trong listener đóng | Tạo/sử dụng bean quá muộn trong chu kỳ shutdown | Chỉ làm việc quan sát ngắn trong event listener |
| Hook hoạt động trên terminal nhưng không trong IDE | IDE có thể dừng process theo cách khác | Kiểm tra cách Stop của IDE và signal thực tế |

### 16.1. Không lạm dụng shutdown hook

Nếu một bean chỉ cần đóng tài nguyên, dùng `@PreDestroy` hoặc `@Bean(destroyMethod = "close")`. Nếu nó cần dừng nhận việc trước khi đóng, dùng `SmartLifecycle`.

Hook tùy biến phù hợp khi bạn kiểm soát một tiến trình Java không dùng Spring hoặc có một yêu cầu process-level đặc biệt. Không nên thêm hook riêng cho từng bean rồi tự quản lý dependency order.

### 16.2. Không cho rằng @PreDestroy là nơi commit cuối cùng

Ví dụ, một consumer đọc message từ broker cần xác nhận/acknowledge message theo hợp đồng trong lúc xử lý. Nếu chỉ lưu trạng thái xử lý trong `@PreDestroy`, một lần process crash có thể làm mất trạng thái đó.

Hãy dùng transaction hoặc cơ chế delivery/acknowledgment của broker. Cleanup chỉ giải phóng tài nguyên; nó không thay thế durability của nghiệp vụ.

### 16.3. Không chặn shutdown bằng sleep vô thời hạn

Một callback `@PreDestroy` chạy vô hạn có thể giữ process trong giai đoạn dừng cho đến khi orchestrator cưỡng bức kill. Khi cần chờ in-flight task, phải có deadline rõ ràng, log đủ để chẩn đoán và phương án khi quá thời hạn.

## 17. Chọn cơ chế theo mục tiêu

| Bạn muốn làm gì? | Cơ chế phù hợp |
| --- | --- |
| Đảm bảo Spring context được đóng khi JVM shutdown thông thường | Shutdown hook mặc định của Spring Boot |
| Chủ động đóng một context do code tạo ra | `ConfigurableApplicationContext.close()` |
| Dừng tạm lifecycle component nhưng giữ context | `ConfigurableApplicationContext.stop()` hoặc API component |
| Quan sát thời điểm bắt đầu đóng context | `ContextClosedEvent` |
| Dừng message consumer/polling trước khi destroy | `SmartLifecycle` |
| Điều khiển thứ tự start/stop của component | `SmartLifecycle.getPhase()` và dependency graph |
| Dọn resource của component bean | `@PreDestroy` |
| Đóng object do `@Bean` tạo | `destroyMethod` hoặc suy luận `close/shutdown` |
| Cung cấp exit code cho CLI | `ExitCodeGenerator` và `SpringApplication.exit(...)` |
| Cho HTTP request đang xử lý hoàn tất | `server.shutdown=graceful` và lifecycle timeout |
| Phối hợp shutdown giữa nhiều node | Readiness, process manager và orchestration |
| Đảm bảo dữ liệu nghiệp vụ bền vững | Transaction, durable storage, acknowledgment/checkpoint |

Một cách phân biệt dễ nhớ là: **hook đưa tiến trình vào đường đóng context; lifecycle component dừng hoạt động; destruction callback đóng tài nguyên; hệ thống triển khai quyết định thời gian được phép chờ.** Mỗi tầng giải quyết một phần của shutdown.

## 18. Bài tập thực hành

### Bài tập 1 — Kiểm tra @PreDestroy

Tạo singleton bean `FileBuffer` với `@PostConstruct` và `@PreDestroy`. Chạy ứng dụng Spring Boot từ terminal, dừng theo đường bình thường và quan sát thứ tự log. Thử tạo một instance bằng `new FileBuffer()` ngoài Spring rồi giải thích vì sao callback không tự chạy.

### Bài tập 2 — Context.close() và context.stop()

Tạo một bean `SmartLifecycle` có method log trong `start`, `stop` và `@PreDestroy`. Gọi `context.stop()` rồi `context.start()`, sau đó `context.close()`. Ghi lại callback nào chạy và phân biệt stop với destroy.

### Bài tập 3 — Thứ tự hủy theo @DependsOn

Tạo `ProviderBootstrap` và `LegacyClient`, dùng `@DependsOn` để client được khởi tạo sau provider. Ghi log các init/destroy method và xác nhận client bị hủy trước provider. So sánh với trường hợp client inject provider qua constructor.

### Bài tập 4 — SmartLifecycle và phase

Tạo một connection manager phase 0 và consumer phase 100. Quan sát thứ tự start/stop khi context refresh và close. Giải thích vì sao consumer nên stop trước khi connection manager đóng.

### Bài tập 5 — Graceful shutdown HTTP

Tạo endpoint có thời gian xử lý cố định. Bật `server.shutdown=graceful` và đặt `spring.lifecycle.timeout-per-shutdown-phase=20s`. Gửi request rồi dừng ứng dụng theo cách cho JVM nhận shutdown signal. Quan sát request in-flight và callback hủy.

### Bài tập 6 — Giới hạn của shutdown hook

So sánh dừng JVM bình thường với một lần kill cưỡng bức trong môi trường thử nghiệm. Xác định callback nào có hoặc không có cơ hội chạy. Giải thích vì sao không được lưu dữ liệu nghiệp vụ quan trọng duy nhất trong `@PreDestroy`.

### Bài tập 7 — CLI có exit code

Tạo `ApplicationRunner` xử lý batch và một `ExitCodeGenerator`. Sau khi runner kết thúc, gọi `SpringApplication.exit(context)` rồi trả mã bằng `System.exit(code)`. Xác nhận context đóng và exit code phản ánh kết quả job.

## 19. Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [SpringApplication API 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)

## 20. Ghi nhớ

Spring Boot mặc định đăng ký JVM shutdown hook để đóng `ApplicationContext` khi JVM kết thúc bình thường. Tuy nhiên, cùng chuỗi đóng context cũng có thể được kích hoạt tường minh qua `ConfigurableApplicationContext.close()` hoặc `SpringApplication.exit(context)`. Hook không được bảo đảm chạy trong mọi tình huống, đặc biệt khi tiến trình bị kill cưỡng bức.

Khi context đóng, Spring phát `ContextClosedEvent`, dừng các component `Lifecycle`/`SmartLifecycle`, rồi hủy các singleton theo dependency graph. Bên trong từng bean, Spring hỗ trợ `@PreDestroy`, `DisposableBean.destroy()` và custom destroy method. Với bean dependency A → B, A được hủy trước B; với lifecycle phase, những component cần dừng sớm có thể được cấu hình phase phù hợp. `context.stop()` chỉ dừng lifecycle; `context.close()` mới kết thúc vòng đời container.

Trong ứng dụng web Spring Boot 3.3, `server.shutdown=graceful` cho phép web server ngừng nhận việc mới và chờ request đang xử lý trong giới hạn cấu hình. Đối với worker, dùng `SmartLifecycle` để dừng nhận việc và chờ công việc đang xử lý trước khi `@PreDestroy` đóng resource. Dữ liệu quan trọng phải được lưu bền vững ngay trong luồng nghiệp vụ vì không callback shutdown nào có thể thay thế transaction, acknowledgment hoặc cơ chế phục hồi sau crash.
