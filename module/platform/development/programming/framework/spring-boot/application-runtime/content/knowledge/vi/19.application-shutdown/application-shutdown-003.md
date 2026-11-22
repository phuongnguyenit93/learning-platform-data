# Trình tự thông báo đóng, dừng Lifecycle và hủy singleton trong Spring Boot

## 1. Vì sao phải phân biệt ba bước shutdown?

Khi một ứng dụng Spring Boot được dừng bình thường, không phải mọi callback “dọn dẹp” đều diễn ra cùng lúc. Spring Framework phân biệt ba cơ chế có mục đích khác nhau:

1. **Thông báo ngữ cảnh đang đóng** qua `ContextClosedEvent`: những listener đã đăng ký biết quá trình đóng context **đã bắt đầu**.
2. **Dừng các thành phần có vòng đời vận hành** qua `LifecycleProcessor.onClose()`: các `Lifecycle` và `SmartLifecycle` đang running được yêu cầu ngừng, có thể phối hợp thứ tự bằng phase và callback bất đồng bộ.
3. **Hủy những singleton được container sở hữu** qua `destroyBeans()`: Spring gọi `@PreDestroy`, `DisposableBean.destroy()` và destroy method đã cấu hình cho các bean thuộc diện hủy.

Đối với **lần đóng bình thường của một `ConfigurableApplicationContext` kiểu Spring Framework 6.1**, thứ tự mức cao là:

```text
Yêu cầu đóng context
    |
    v
ContextClosedEvent
    |
    v
LifecycleProcessor.onClose()
    |-- stop lifecycle beans theo thứ tự phase giảm
    |-- phối hợp SmartLifecycle.stop(Runnable callback)
    v
destroyBeans()
    |-- hủy cached singletons / gọi destruction callbacks
    v
closeBeanFactory()
    |
    v
onClose() của context subclass và cleanup context
    |
    v
close() hoàn tất
```

Đây là **thứ tự các giai đoạn**, không phải khẳng định toàn bộ các callback ở từng giai đoạn luôn chạy trên cùng thread trong mọi cấu hình, hay mọi bean của ứng dụng đều có đầy đủ ba cơ chế. Ví dụ, một bean thông thường có `@PreDestroy` nhưng không triển khai `Lifecycle` sẽ chỉ tham gia giai đoạn destroy; một `SmartLifecycle` có thể vừa nhận `stop(Runnable)`, vừa nhận `@PreDestroy` sau đó.

**Thông điệp chính:** `ContextClosedEvent` là tín hiệu **bắt đầu đóng**, `stop` là thao tác **dừng hoạt động**, còn `destroy` là thao tác **giải phóng bean/tài nguyên**. Không xem ba cơ chế là một callback đồng nghĩa.

Phạm vi bài: **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**, shutdown bình thường và các giới hạn cần nhớ khi chạy trong hệ điều phối/container.

## 2. Điểm xuất phát: điều gì kích hoạt quá trình đóng?

Một context có thể được yêu cầu đóng theo nhiều cách.

### 2.1. Đóng tường minh

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

context.close();
```

Đây là **đoạn minh họa**, cần class `MyApplication` và import Spring tương ứng. `ConfigurableApplicationContext` mở rộng `Closeable`; `close()` kích hoạt trình tự đóng context mà Spring quản lý.

### 2.2. try-with-resources

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    // Thực hiện tác vụ.
}
// Ra khỏi khối: Java gọi context.close().
```

Đây cũng là đoạn minh họa. Với một **CLI/batch hoặc bài thực hành non-web**, cách này giúp đảm bảo close ở luồng hoàn tất bình thường hoặc khi một exception đi qua khối.

Nhưng với **web service chạy lâu dài**, không đặt context vào một try-with-resources kết thúc ngay sau `run()`, vì nó sẽ đóng server trước khi ứng dụng có cơ hội phục vụ request. Web application thường để context sống cho tới khi nhận tín hiệu dừng.

### 2.3. JVM shutdown hook

Spring Boot thông thường đăng ký shutdown hook để context được đóng khi JVM thực hiện shutdown bình thường (ví dụ khi tiến trình nhận tín hiệu dừng cho phép hook chạy). Bởi vậy một yêu cầu **SIGTERM** trong container có thể dẫn tới cùng đường đóng context như `close()`.

Cần phân biệt:

- **`context.close()`**: thao tác trên đối tượng context khi mã ứng dụng còn thực thi.
- **Shutdown hook**: cơ hội JVM gọi code dọn dẹp trong quá trình JVM shutdown.
- **`System.exit(...)`**: chủ động yêu cầu JVM kết thúc, dẫn vào shutdown process nếu runtime cho phép.
- **`SIGKILL`, crash nặng, mất điện**: không cho phép dựa vào hook/`@PreDestroy` như bảo đảm tuyệt đối.

`ContextClosedEvent` **không phải** event báo kết quả SIGTERM của hệ điều hành; nó là Spring `ApplicationContext` event được phát khi context đóng theo cơ chế Spring.

### 2.4. Đóng context không đồng nghĩa khởi động shutdown hook

Nếu bạn chủ động gọi `context.close()` trong một tiến trình đang chạy, Spring xử lý đóng context. JVM **không nhất thiết** phải thoát ngay: có thể vẫn còn non-daemon threads ở nơi khác. Ngược lại, JVM có thể bị dừng đột ngột mà context không kịp hoàn thành toàn bộ cleanup. Không đồng nhất process lifecycle và context lifecycle.

## 3. Vì sao ContextClosedEvent được phát trước stop/destroy?

`ContextClosedEvent` thuộc package `org.springframework.context.event`. Khi `AbstractApplicationContext.doClose()` đi vào đường đóng bình thường, nó phát sự kiện này **trước** khi gọi lifecycle processor và hủy cached singletons.

Một listener đơn giản:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
```

Đây là **đoạn method minh họa**, không phải chương trình độc lập. Nó phải nằm trong bean do Spring quản lý, với import `org.springframework.context.event.EventListener` và `org.springframework.context.event.ContextClosedEvent`.

### 3.1. Listener được phép làm gì lúc nhận event?

Ở thời điểm event được phát, quá trình dừng lifecycle và hủy singleton **chưa hoàn tất**. Listener có thể:

- Đánh dấu một trạng thái ứng dụng “đang đóng” để phục vụ việc phối hợp nhanh, có kiểm soát.
- Ghi metric/log shutdown, timestamp, correlation ID không nhạy cảm.
- Gửi tín hiệu ngừng nhận công việc **nếu đó là trách nhiệm được thiết kế riêng**, nhưng tránh trùng với `SmartLifecycle.stop`.
- Thông báo cho những thành phần đã tồn tại rằng close process bắt đầu.

Không nên:

- Giả định worker/consumer đã dừng chỉ vì `ContextClosedEvent` được gửi.
- Khởi tạo thêm thread mới, đăng ký nhiều tác vụ dài hạn hoặc tạo thêm bean phức tạp khi context đang đóng.
- Block vô hạn trong listener, vì với multicaster đồng bộ thông thường, điều này có thể **làm chậm cả lifecycle stop và bean destruction**.
- Gọi `context.close()` đệ quy trong listener.
- Dùng listener này để chứng minh dữ liệu đã được commit hoặc đã flush hoàn toàn.

### 3.2. Có thể dùng @Order để thay đổi thứ tự ba giai đoạn không?

**Không.** `@Order` của các `@EventListener` có thể giúp sắp nhiều **listener cho cùng `ContextClosedEvent`** theo dispatch ordering. Nó không thể thay đổi trật tự nguồn Spring:

```text
ContextClosedEvent -> LifecycleProcessor.onClose() -> destroyBeans()
```

Bạn không thể đặt `@Order(-1000)` trên một method `@PreDestroy` rồi bắt nó chạy trước `ContextClosedEvent`. `@PreDestroy` không phải `ApplicationEvent` listener.

### 3.3. Đồng bộ và bất đồng bộ

`SimpleApplicationEventMulticaster` mặc định thường gọi listener đồng bộ. Khi đó body của listener `ContextClosedEvent` có cơ hội chạy trước khi `doClose()` chuyển sang lifecycle stop.

Nếu ứng dụng có custom event multicaster dùng executor, hoặc listener có async behavior, **không nên dựa vào thời điểm callback bất đồng bộ hoàn tất** để kết luận đã xong trước khi Spring destroy bean. Một job được schedule trong listener có thể vẫn chạy khi bean phụ thuộc bị đóng. Với công việc shutdown bắt buộc, `SmartLifecycle.stop(Runnable)` và timeout/ack có contract rõ hơn.

## 4. LifecycleProcessor.onClose(): dừng hoạt động trước khi hủy bean

Spring định nghĩa `org.springframework.context.Lifecycle`:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Đây là chữ ký rút gọn để giải thích, không phải class cần khai báo lại. `Lifecycle` mô tả **một đối tượng có khả năng chuyển giữa running và stopped**; nó khác việc object tồn tại trong heap.

`SmartLifecycle` còn bổ sung:

- `isAutoStartup()`: cho phép tự start khi context refresh nếu điều kiện phù hợp; mặc định của interface trong Spring 6.1 là `true`.
- `getPhase()`: gán phase để Spring sắp start/stop.
- `stop(Runnable callback)`: hỗ trợ báo hoàn tất shutdown, đặc biệt cho việc dừng bất đồng bộ.

Trong `doClose()` bình thường, Spring gọi `LifecycleProcessor.onClose()` **sau `ContextClosedEvent`**. Implementation thông dụng `DefaultLifecycleProcessor` lấy các bean lifecycle có liên quan rồi điều phối dừng chúng.

**Không phải mọi singleton đều được gọi `stop()`.** Chỉ các bean thuộc hợp đồng `Lifecycle`/`SmartLifecycle` và đang chạy theo cơ chế processor mới tham gia. Bean đơn giản có `@PreDestroy` không có `stop` chỉ nhận destruction callback ở bước sau.

### 4.1. Phase: start tăng, stop giảm

Với các bean `SmartLifecycle` đã đăng ký, nguyên tắc thông thường:

| Phase | Khi start | Khi shutdown |
| --- | --- | --- |
| `-100` | Start rất sớm | Stop tương đối muộn |
| `0` | Sau -100, trước 100 | Sau 100, trước -100 |
| `100` | Sau 0, trước 200 | Trước 0, sau 200 |
| `200` | Sau 100 | Stop trước phase 100 |
| `Integer.MAX_VALUE` | Thuộc các phase cuối khi start | Thuộc các phase đầu khi stop |

Spring Framework 6.1 có `SmartLifecycle.DEFAULT_PHASE == Integer.MAX_VALUE`, còn `Lifecycle` thường không có `Phased` được xem là phase `0` trong processor mặc định.

Ví dụ hai component:

```text
Startup:
    connector phase=100 -> consumer phase=200

Shutdown:
    consumer phase=200 -> connector phase=100
```

Điều đó hợp lý khi consumer cần connector sống trong suốt quá trình stop/drain công việc. Nếu consumer được dừng sau connector, consumer có thể gửi request đến tài nguyên đã bị đóng.

**Không dùng phase để suy ra thứ tự tạo bean**: constructor, `@PostConstruct` và dependency injection diễn ra theo cơ chế bean factory. `getPhase()` điều phối **start/stop**.

### 4.2. @DependsOn có thể ưu tiên hơn phase

Nếu bean B phụ thuộc A, Spring có thể bảo đảm B **stop trước** A dù phase được khai báo ngược. `@DependsOn` diễn tả quan hệ rõ ở mức bean definition, còn phase là mức điều phối lifecycle khi không có dependency tường minh.

Không cố dùng phase để phá một ràng buộc dependency. Nếu một consumer thật sự cần một producer, hãy thể hiện mối quan hệ ấy bằng injection hoặc `@DependsOn` phù hợp.

### 4.3. Các bean cùng phase không có một thứ tự nghiệp vụ được cam kết

Nếu hai listener/worker đều phase `100`, đừng dựa vào thứ tự log tình cờ thấy trong một lần chạy để quyết định chúng phải dừng theo thứ tự nào. Có thể cần tách phase, khai báo dependency hoặc tạo một owner chịu trách nhiệm orchestration rõ ràng.

### 4.4. isRunning() có ý nghĩa gì?

`isRunning()` là trạng thái mà implementation công bố. Khi processor dừng những bean đang chạy, method này có thể được dùng để quyết định có gọi stop hay không. Nếu một component đặt cờ `running=false` trước khi thực sự drain xong, hoặc trả cờ sai, shutdown coordination có thể không đúng.

Không xem việc container gọi `stop()` là bằng chứng **tất cả task async của component đã hoàn tất**. Component phải thiết kế ranh giới dừng của nó.


## 5. SmartLifecycle.stop(Runnable): vì sao callback quan trọng?

Hợp đồng `SmartLifecycle.stop(Runnable callback)` dùng để thông báo khi một component **đã ngừng thật sự**, đặc biệt nếu shutdown thực hiện bất đồng bộ.

Mẫu dừng đồng bộ:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // Dừng thật, không chỉ đổi một flag tùy tiện.
    } finally {
        callback.run();
    }
}
```

Đây là một method minh họa trong class triển khai `SmartLifecycle`; code đầy đủ sẽ xuất hiện ở mục 7.

### 5.1. Nếu dừng bất đồng bộ

Một component có thể:

1. Ngừng nhận task mới.
2. Chờ các task đang chạy hoàn tất hoặc tới deadline.
3. Gửi acknowledgement/hủy subscription tương ứng.
4. Đóng tài nguyên do nó sở hữu.
5. **Sau đó** gọi `callback.run()`.

Mẫu ý tưởng:

```java
@Override
public void stop(Runnable callback) {
    stopExecutor.execute(() -> {
        try {
            stopAcceptingTasks();
            drainWithinDeadline();
            closeOwnedResources();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

Đây là **pseudo-code Java**, chưa biên dịch độc lập: `stopExecutor` và các method phải được định nghĩa thật. Thực tế còn phải xử lý khi `stopExecutor.execute(...)` bị từ chối, bảo đảm callback chỉ gọi **một lần** và không khiến resource dừng dang dở.

**Gọi callback quá sớm** khiến processor có thể chuyển sang stop dependency tiếp theo trong khi worker còn chạy. **Quên gọi callback** khiến processor phải chờ hết timeout của phase. Đây là lý do `stop(Runnable)` không thể được thay bằng một dòng `System.out.println("stopping")`.

### 5.2. Timeout theo shutdown phase

`DefaultLifecycleProcessor` của **Spring Framework 6.1** có timeout mặc định **30 giây cho mỗi phase** khi chờ các `SmartLifecycle.stop(Runnable)` hoàn tất. Spring Boot 3.3 cho phép cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Điều này giới hạn **thời gian chờ của processor cho một phase**, không phải bảo đảm toàn bộ process kết thúc sau 20 giây. Nhiều phase, web server graceful shutdown, JVM hooks và termination grace period của container có thể kéo dài hoặc rút ngắn thời gian thực.

Nếu phase timeout, processor có thể tiếp tục bước sau mà component chưa thật sự hoàn tất. Vì vậy app vẫn cần I/O timeout, cooperative cancellation và bảo đảm không tạo side effect sai sau khi resource bị đóng.

### 5.3. stop(Runnable) không thay @PreDestroy

`stop` dùng để ngừng **hoạt động** có điều phối theo phase. `@PreDestroy` dùng để cleanup **lúc bean được destroy**. Một bean có thể nhận cả hai nếu vừa triển khai `SmartLifecycle` vừa có callback destruction.

Ví dụ một message consumer:

```text
ContextClosedEvent
    |
    +--> SmartLifecycle.stop(callback)
    |       +--> dừng poll / ngừng nhận message
    |       +--> xử lý inflight trong deadline
    |       +--> callback.run()
    |
    +--> @PreDestroy
            +--> cleanup cuối nếu còn resource
```

Nên tránh đóng **cùng một tài nguyên** hai lần một cách không kiểm soát. Có thể thiết kế `close` idempotent hoặc phân chia chính xác trách nhiệm của từng phase. Nếu dùng shutdown callback cuối để phòng thủ khi startup chưa hoàn tất, đừng giả định luôn có `stop` trước đó trong mọi failure path.

## 6. destroyBeans(): hủy singleton theo hợp đồng container

Sau lifecycle stop bình thường, `AbstractApplicationContext` gọi `destroyBeans()`. Implementation mặc định gọi destruction cho **cached singleton beans** do `BeanFactory` đang quản lý. Đây là bước khác với `LifecycleProcessor.onClose()`.

Đối với một bean đủ điều kiện được container destroy, Spring hỗ trợ:

- `@PreDestroy` (trong Spring Boot 3.x dùng `jakarta.annotation.PreDestroy`).
- `org.springframework.beans.factory.DisposableBean.destroy()`.
- Custom destroy method, ví dụ `@Bean(destroyMethod = "close")`.
- Một số bean `@Bean` có thể suy luận method `close()` hoặc `shutdown()` khi destroy theo cấu hình chuẩn.

### 6.1. Thứ tự các cơ chế hủy trên **cùng một bean**

Nếu một bean khai báo **ba callback với ba tên khác nhau**, Spring Framework tài liệu hóa thứ tự:

1. Method mang `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method đã được cấu hình.

Minh họa:

```java
public class ResourceOwner implements DisposableBean {
    @PreDestroy
    public void beforeDestroy() {
        System.out.println("A. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("B. DisposableBean.destroy");
    }

    public void closeResource() {
        System.out.println("C. custom destroy");
    }
}
```

Đây là **class minh họa**, cần import `DisposableBean` và `PreDestroy` cùng một bean definition đăng ký custom method `closeResource`, ví dụ `@Bean(destroyMethod="closeResource")`. Mã chạy đầy đủ ở mục 7.

**Lưu ý:** Đây là thứ tự **nội bộ của một bean**. Không suy ra các bean độc lập sẽ luôn được destroy theo thứ tự tên class, `@Order` hoặc thứ tự xuất hiện trong file Java. Để áp ràng buộc destruction giữa các singleton, cần thể hiện dependency hợp lệ; dependent singleton được destroy trước dependency singleton trong quan hệ `depends-on`.

### 6.2. Các bean nào không tự được hủy như singleton?

| Đối tượng/scope | Khi context đóng bình thường | Ai chịu trách nhiệm cleanup? |
| --- | --- | --- |
| Singleton được Spring quản lý và có destruction callback | Spring gọi callback theo cơ chế bean destruction | Spring điều phối; callback chịu trách nhiệm release resource |
| Singleton không giữ tài nguyên và không có destroy callback | Không có việc cleanup đặc biệt cần gọi | Không cần tự tạo `close()` vô nghĩa |
| `prototype` bean | Spring tạo/initialize nhưng **không tự thực thi destruction callback từng instance lúc context đóng** | Caller/owner của từng instance |
| Object tạo bằng `new` ngoài container | Không có Spring bean lifecycle tự động | Code sở hữu object |
| Object được tạo bằng `new` **trong `@Bean` và trả về như bean singleton** | Có thể có Spring destruction callbacks vì object đã là bean được quản lý | Xem scope và destroy method, không chỉ cách gọi constructor |
| Resource nằm trong field của singleton nhưng không đăng ký thành bean | Container destroy owner bean, không mặc nhiên biết resource con | Owner bean đóng resource trong callback phù hợp |

Spring Framework có những scope khác như request/session có thể có destruction callback theo lifecycle scope của chúng. Không gom mọi non-singleton vào quy tắc prototype mặc định.

### 6.3. Tại sao @PreDestroy không phải thứ cần gọi thủ công để stop worker?

`@PreDestroy` chỉ là metadata cho destruction phase, **không phải API public “hãy dừng component bây giờ”**. Nếu cần tạm dừng một worker trong khi context vẫn sống, dùng contract `Lifecycle.stop()`, `SmartLifecycle` hoặc một service operation riêng. `context.stop()` cũng không destroy toàn bộ bean, nên không gọi lại mọi `@PreDestroy`.

Nếu cần giải phóng resource đúng lúc kết thúc một request/job ngắn, dùng `try-with-resources` hoặc ownership theo scope thay vì đợi JVM shutdown.

## 7. Ví dụ chạy được: quan sát đủ 8 mốc với Spring Boot 3.3.13

Ta tạo một Spring Boot **non-web** nhỏ để tránh web server và startup task của các starter khác ảnh hưởng stdout. Chương trình có:

- Một listener `ContextClosedEvent`.
- Hai bean `SmartLifecycle` với phase `200` và `100`.
- Một bean singleton có cả `@PreDestroy`, `DisposableBean.destroy()` và custom `destroyMethod`.
- Một `try-with-resources` đóng context rõ ràng khi ứng dụng đã startup thành công.

**Dự đoán:** event đóng trước; `SmartLifecycle` phase 200 dừng trước phase 100; sau đó ba callback hủy của singleton chạy theo đúng thứ tự.

### 7.1. build.gradle

Tạo project Gradle Groovy với Gradle Wrapper và **Java 17**. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'shutdown-stages-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Đây là dự án non-web: không có embedded Tomcat/Netty, nên output của lifecycle demonstration không bị xen log web server.

### 7.2. File Java hoàn chỉnh

Tạo đúng đường dẫn **`src/main/java/com/example/shutdown/ShutdownStagesApplication.java`**:

```java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ShutdownStagesApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ShutdownStagesApplication.class, args)) {
            System.out.println("01 main: request context close");
        }
        System.out.println("08 main: close finished");
    }

    @EventListener
    public void contextClosing(ContextClosedEvent event) {
        System.out.println("02 ContextClosedEvent");
    }

    @Bean
    PhaseWorker lowPhaseWorker() {
        return new PhaseWorker("LOW", 100);
    }

    @Bean
    PhaseWorker highPhaseWorker() {
        return new PhaseWorker("HIGH", 200);
    }

    @Bean(destroyMethod = "closeResource")
    CleanupSentinel cleanupSentinel() {
        return new CleanupSentinel();
    }

    public static final class PhaseWorker implements SmartLifecycle {
        private final String label;
        private final int phase;
        private volatile boolean running;

        public PhaseWorker(String label, int phase) {
            this.label = label;
            this.phase = phase;
        }

        @Override
        public void start() {
            running = true;
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                if (phase == 200) {
                    System.out.println("03 stop HIGH phase=200");
                } else {
                    System.out.println("04 stop LOW phase=100");
                }
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
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
            return phase;
        }
    }

    public static final class CleanupSentinel implements DisposableBean {

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("05 singleton @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("06 singleton DisposableBean.destroy");
        }

        public void closeResource() {
            System.out.println("07 singleton custom closeResource");
        }
    }
}
```

### 7.3. Giải thích các quyết định trong code

- `@SpringBootApplication` khởi tạo ứng dụng non-web và quét các bean cần thiết.
- `@EventListener` trên class application nghe `ContextClosedEvent` trong context đó; với multicaster đồng bộ mặc định, nó in **02** trước stop.
- `lowPhaseWorker()` và `highPhaseWorker()` là hai singleton `SmartLifecycle`. `isAutoStartup() == true` nên được start trong refresh; `isRunning()` trả true trước khi đóng context.
- Hai worker dùng `getPhase()` là 100 và 200. Khi `LifecycleProcessor.onClose()` chạy, phase cao **200 stop trước 100**.
- `stop(Runnable)` gọi `stop()` thật rồi luôn gọi callback trong `finally`. Vì method dừng đồng bộ và không có task nền, callback được báo ngay sau dừng.
- `CleanupSentinel` là một singleton được `@Bean(destroyMethod="closeResource")` đăng ký. Nó có ba callback **khác tên**, phù hợp để kiểm chứng thứ tự Spring: `@PreDestroy` → `DisposableBean.destroy` → custom method.
- `try-with-resources` đóng context ở cuối block. Sau khi toàn bộ `close()` return, main in **08**.
- Không có phần mềm ngoài, message broker hoặc network I/O; các dòng đánh số không có tranh chấp scheduling.

### 7.4. Chạy chương trình

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Những dòng **được chính mã Java này in ra**, theo đúng thứ tự với cấu hình mặc định đã mô tả:

```text
01 main: request context close
02 ContextClosedEvent
03 stop HIGH phase=200
04 stop LOW phase=100
05 singleton @PreDestroy
06 singleton DisposableBean.destroy
07 singleton custom closeResource
08 main: close finished
```

Có thể có thêm output của Gradle/task hoặc log lỗi hệ thống khi môi trường chạy có vấn đề; chúng không nằm trong danh sách dòng đánh số.

**Đối chiếu:**

- Dòng **02 trước 03**: thông báo đóng không phải xác nhận worker đã dừng.
- Dòng **03 trước 04**: lifecycle shutdown phase được xử lý theo thứ tự **cao xuống thấp**.
- Dòng **05 sau 04**: singleton destruction bắt đầu sau giai đoạn lifecycle stop thông thường.
- Dòng **05, 06, 07**: thứ tự destruction mechanisms **trên cùng một bean**.
- Dòng **08 sau 07**: lời gọi `context.close()` đã hoàn tất.

Nếu thử đặt exception trong một callback, output sẽ **không còn là bảng mốc thành công ở trên**; khi ấy phải điều tra nhánh lỗi shutdown, không ghi test cứng rằng mọi mốc luôn xuất hiện trong mọi tình huống.

### 7.5. Thay đổi thí nghiệm để hiểu sâu

**Thí nghiệm A — đổi phase:** Đổi phase HIGH từ 200 thành 50. Khi shutdown, bean LOW phase 100 được dừng trước HIGH phase 50. Nhớ sửa các nhãn log để không đánh lừa người đọc. `ContextClosedEvent` vẫn đứng trước phần stop.

**Thí nghiệm B — bỏ @PreDestroy:** Bỏ annotation và method `beforeDestroy()` khỏi `CleanupSentinel`. Hai callback còn lại `DisposableBean.destroy()` và custom `closeResource()` vẫn chạy theo cơ chế được cấu hình.

**Thí nghiệm C — bỏ DisposableBean:** Bỏ `implements DisposableBean` và method `destroy()` khỏi sentinel; method `@PreDestroy` và custom `closeResource` vẫn là hai đường cleanup hợp lệ khi singleton được destroy.

**Thí nghiệm D — đổi stop(Runnable):** Không gọi `callback.run()` là phản ví dụ. Processor có thể chờ tới hết shutdown phase timeout trước khi đi tiếp; không áp dụng ở production.

**Thí nghiệm E — context.stop():** Thay thử `close()` bằng `context.stop()` trong một ứng dụng còn giữ context. Lúc đó là lệnh **tạm dừng lifecycle**, không phải destroy toàn bộ singleton và không phải `ContextClosedEvent`. Cần có kế hoạch gọi `context.start()` hoặc `context.close()` sau đó để tránh resource leak.

**Thí nghiệm F — thêm @DependsOn:** Nếu một worker được khai báo phụ thuộc worker khác, thứ tự stop có thể được điều phối bởi quan hệ dependency ngay cả khi phase khác. Đây là behavior có chủ đích của Spring, không phải lỗi phase comparator.


## 8. context.stop() khác context.close() như thế nào?

Hai method thường bị nhầm vì đều có chữ “stop/dừng”, nhưng contract khác:

| Thao tác | Event | Lifecycle processor | Destruction singleton | Context có thể dùng lại? |
| --- | --- | --- | --- | --- |
| `context.stop()` | Thông thường có `ContextStoppedEvent` sau khi gọi processor stop | Dừng các `Lifecycle` đang running | **Không** destroy toàn bộ bean | Có thể `context.start()` lại nếu context còn hợp lệ |
| `context.close()` | Phát `ContextClosedEvent` trong đường đóng bình thường | Sau đó dừng lifecycle components | **Có**, hủy singleton đủ điều kiện | Không: context đã đóng |
| `context.start()` | Thông thường có `ContextStartedEvent` | Gọi start các lifecycle components | Không tạo lại mọi bean | Chỉ dùng khi context còn hoạt động |

**Không đồng nhất `ContextStoppedEvent` và `ContextClosedEvent`**. `close()` không phải đơn giản “gọi `stop()` rồi phát `ContextStoppedEvent`”; ở đường `doClose()` thông thường, Spring **phát `ContextClosedEvent` rồi gọi `LifecycleProcessor.onClose()`**, không tự biến thành một `ContextStoppedEvent`.

Thêm một ví dụ:

```java
context.stop();  // Dừng Lifecycle beans; context chưa destroyed.
context.start(); // Có thể khởi động lại Lifecycle beans còn hợp lệ.
context.close(); // Đóng context, dừng rồi destroy singleton.
```

Đây là đoạn minh họa **trong nơi đã có biến `context` là ConfigurableApplicationContext**, không phải chương trình độc lập. Không gọi `start()` sau khi context đã close. Với worker mở resource không thể tái sử dụng, `stop()/start()` vẫn cần implementation đủ an toàn, không tự được Spring bảo đảm.

## 9. Lifecycle stop thành công không đồng nghĩa mọi tác vụ nền đã hoàn thành

Một `SmartLifecycle` có thể start một executor hoặc message consumer. Nếu `stop(Runnable)` chỉ đổi `running=false` rồi gọi callback, trong khi những task nền đang thực thi vẫn cần database/connection, lifecycle processor có thể chuyển sang stop phase thấp hơn và **đóng dependency trước khi task hoàn tất**.

Hãy tách các trạng thái:

```text
stop requested
    |
    +--> refusing new work
    +--> draining in-flight tasks
    +--> releasing owned resource
    +--> stop callback acknowledged
    +--> bean destroy callback(s)
```

Điểm nguy hiểm là việc **báo stop complete quá sớm**. Cần một contract thực sự trả lời:

- Worker có còn nhận thêm job mới không?
- Những job đã nhận có được hoàn tất hoặc checkpoint bền vững không?
- Có transaction nào đang commit hoặc message nào cần acknowledgement không?
- Đã đợi Future/consumer acknowledgements đúng deadline chưa?
- Có resource dùng chung nào chỉ được đóng sau khi các dependent components đã dừng không?

### 9.1. Khuyến nghị với executor

Với executor do bean sở hữu, dừng thường gồm:

1. Ngừng submit task mới.
2. `shutdown()` executor để bắt đầu dừng theo contract của pool.
3. Đợi `awaitTermination(timeout, unit)` hoặc futures/ack có timeout.
4. Nếu hết deadline, kích hoạt chính sách hủy/checkpoint phù hợp và báo lỗi vận hành.
5. Không mặc định cho rằng `shutdown()` return thì mọi tác vụ đã xong.

`shutdownNow()` là cố gắng dừng, không bảo đảm I/O đang chạy đã dừng hoặc side effect đã rollback. Với task quan trọng phải sống qua crash, cần durable queue/checkpoint/idempotency; không chỉ dựa vào JVM hook.

### 9.2. Khuyến nghị với message consumer

Consumer nên ngừng nhận message mới, drain in-flight, ack/nack theo giao thức broker, rồi mới release connection. Nếu consumer phase cao hơn một connector, stop consumer trước connector thường thuận lợi.

Nhưng việc sắp phase **không tự làm drain**; `SmartLifecycle.stop(Runnable)` của từng component phải thực hiện đầy đủ. `@PreDestroy` có thể làm cleanup phòng thủ cho resource còn tồn tại, song không nên là nơi duy nhất điều phối một quy trình dừng có dependency phức tạp.

## 10. Graceful shutdown của web server trong Spring Boot 3.3

Spring Boot 3.3 hỗ trợ graceful shutdown cho các embedded web servers trong servlet/reactive applications. Cần **bật rõ** property đối với cấu hình Boot 3.3:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Theo tài liệu Boot 3.3, graceful shutdown diễn ra **trong quá trình đóng application context**, ở **giai đoạn sớm nhất khi dừng các `SmartLifecycle` beans**. Nó cho request đang xử lý một khoảng thời gian hoàn tất và không tiếp nhận request mới theo cơ chế của web server.

Cần phân biệt:

- `ContextClosedEvent` đến khi context bắt đầu đóng; không bảo đảm các in-flight HTTP requests đã hoàn tất.
- Trong `LifecycleProcessor.onClose()`, web server graceful shutdown tham gia stop lifecycle với phase phù hợp.
- Sau lifecycle stop, destruction callback của singleton mới được xử lý theo đường đóng bình thường.
- Quá trình ngừng nhận request mới thay đổi theo server và network, không mặc định mọi request mới đều nhận một HTTP status giống nhau.
- Graceful timeout của Boot là **thời gian chờ per shutdown phase**, không bảo đảm toàn bộ JVM shutdown hoàn tất trong thời hạn đó.

Ở Boot 3.3, Jetty, Reactor Netty, Tomcat và Undertow có cơ chế riêng. Jetty/Reactor Netty/Tomcat có thể không nhận request mới ở network layer; Undertow có thể trả `503` cho kết nối mới. Đây là mô tả behavior tài liệu Boot 3.3, không phải hợp đồng cố định cho tất cả versions hoặc cấu hình proxy.

### 10.1. Graceful shutdown và readiness

Trong một môi trường có load balancer/Kubernetes, thông thường cần **rút Pod/instance khỏi traffic** trước hoặc trong quá trình dừng, đồng thời dành thời gian cho những request đang xử lý hoàn tất.

Readiness và shutdown phối hợp nhưng là những cơ chế khác nhau:

- `ReadinessState.REFUSING_TRAFFIC` mô tả ứng dụng không muốn nhận request mới.
- Kubernetes readiness probe ảnh hưởng danh sách endpoint route, nhưng có chu kỳ/độ trễ lan truyền.
- `ContextClosedEvent` là event trong Spring context, không trực tiếp thao tác Kubernetes Endpoints.
- Web server graceful shutdown dừng nhận request theo khả năng của embedded server.
- JVM shutdown hook cung cấp cơ hội chạy cleanup, nhưng không bảo đảm với kill cưỡng bức.

Không dùng một method `@PreDestroy` ngủ nhiều giây để “đợi load balancer rút route” thay cho một kế hoạch drain rõ ràng. Cần điều chỉnh readiness, preStop/terminationGracePeriodSeconds, graceful timeout và ingress/server theo môi trường thực.

### 10.2. Boot 3.3 khác default của các version mới

Không lấy tài liệu một Spring Boot major version mới hơn rồi suy rằng Boot 3.3 luôn bật graceful shutdown mặc định. Trong phạm vi Boot 3.3 của bài, hãy **cấu hình `server.shutdown=graceful`** khi mong muốn behavior ấy, và kiểm thử bằng đúng embedded server.

## 11. Rủi ro khi bắt đầu tác vụ mới trong ContextClosedEvent

Giả sử listener:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    backgroundExecutor.submit(() -> sendFinalReport());
}
```

Đây là **phản ví dụ**, với `backgroundExecutor` và `sendFinalReport` chỉ là những symbol minh họa. Lệnh `submit(...)` không đợi công việc hoàn tất; ngay sau listener return, Spring tiếp tục dừng lifecycle và destroy singleton. Executor, HTTP client hoặc connection pool có thể bị shutdown trước khi task thực hiện xong.

Nếu báo cáo cuối là **bắt buộc**, cần một cơ chế dừng có deadline, Future/ack và ownership rõ ràng. Thường phù hợp hơn là:

- Worker `SmartLifecycle` ngừng nhận việc rồi drain, gọi callback sau khi đã hoàn tất.
- Một orchestrator quản lý shutdown trong ứng dụng với thứ tự dependency rõ.
- Durable outbox/job state để thông điệp vẫn có thể được gửi lại sau restart.
- Không lệ thuộc một network call không timeout trong JVM shutdown hook.

Nếu thông báo chỉ là telemetry best-effort, có thể ghi metric/log ngắn trong `ContextClosedEvent`. Đừng đặt tính đúng đắn dữ liệu vào việc event listener có kịp gửi request ra ngoài hay không.

## 12. Ngoại lệ và đường shutdown không hoàn hảo

Thứ tự ở mục 1 là **đường đóng bình thường** khi Spring có thể thực hiện đầy đủ các giai đoạn. Một số tình huống làm thứ tự quan sát khác:

### 12.1. Context refresh thất bại

Nếu bean initialization hoặc `SmartLifecycle.start()` ném lỗi trong refresh, Spring có thể tiến hành cleanup các singleton đã tạo nhưng chưa đi qua một đường `ContextClosedEvent → LifecycleProcessor.onClose()` bình thường. Tài liệu Spring Framework cảnh báo **stop notification không được bảo đảm xảy ra trước destruction** khi refresh bị hủy hoặc trong những trường hợp refresh đặc biệt.

Vì vậy destruction callback nên chịu được trường hợp component **chưa được start**, hoặc start một nửa. Đừng viết `@PreDestroy` giả định `stop()` đã chạy trong mọi failure path.

### 12.2. Listener đóng context ném lỗi

Spring xử lý exception khi phát `ContextClosedEvent` trong `doClose()` và có đường ghi log, nhằm tiếp tục cleanup. Nhưng điều đó không có nghĩa mọi callback ném exception được nuốt theo cùng cách hoặc shutdown vẫn chắc chắn sạch trong mọi lỗi nghiêm trọng.

Listener nên ít side effect và timeout rõ ràng. Nếu muốn báo lỗi, ghi log/metric có đủ context, không làm hỏng khả năng dọn dẹp của những bean khác.

### 12.3. stop callback không chạy hoặc phase timeout

Nếu implementation `SmartLifecycle.stop(Runnable)` quên `callback.run()`, processor có thể chờ tới timeout rồi chuyển bước. Trạng thái bean có thể chưa stopped thật; resource bị destroy trong khi worker còn dùng chúng.

Đây là lỗi thiết kế lifecycle, không phải do `@PreDestroy` “chạy quá sớm”. Cần sửa callback và logic drain theo deadline.

### 12.4. Destruction callback ném exception

Một `DisposableBean.destroy()` hoặc destroy method lỗi không nên được dùng làm cơ chế kiểm soát flow chính của shutdown. Spring cố log các lỗi dọn dẹp và tiếp tục hủy các bean khác khi khả thi.

Cần thiết kế cleanup idempotent, không block vô hạn, cho phép retry/recovery ở hệ thống ngoài nếu side effect chưa thành công. Không bảo đảm giao dịch tiền tệ hoặc thông báo durable chỉ nhờ một callback chạy trong vài giây trước JVM exit.

### 12.5. SIGKILL, OOM, crash hoặc mất điện

Không có cơ chế Java/Spring nào bảo đảm `ContextClosedEvent`, `SmartLifecycle.stop()` và `@PreDestroy` đều thực thi nếu process bị kill cưỡng bức. Hãy thiết kế idempotency, lease timeout, transaction timeout, broker redelivery và cơ chế reconciliation cho các trường hợp không chạy callback.

### 12.6. Object/scope không được quản lý đầy đủ

Nếu một worker tự được tạo bằng `new` ngoài container, Spring không tự biết để gọi stop/destroy. Với prototype, mặc dù Spring có thể khởi tạo instance, container mặc định không theo dõi destruction callback của mọi prototype đến khi đóng context. Owner phải chủ động đóng tài nguyên.

## 13. Những ngộ nhận dễ gặp

| Phát biểu hoặc triệu chứng | Vì sao sai/thiếu? | Cách xử lý |
| --- | --- | --- |
| “ContextClosedEvent nghĩa mọi worker đã dừng” | Event được phát **trước** lifecycle stop | Chờ stop callback/ack nếu cần |
| “@PreDestroy của singleton chạy trước SmartLifecycle.stop” | Trái trình tự đóng bình thường | Kiểm tra lifecycle phase và đường failure |
| “context.stop() và context.close() giống nhau” | stop không destroy cached singletons | Chọn API theo nhu cầu tạm dừng hay đóng hẳn |
| “ContextClosedEvent và ContextStoppedEvent là một” | Hai event cho hai thao tác khác nhau | Dùng đúng event type |
| “@Order(-100) làm @PreDestroy chạy trước ContextClosedEvent” | @Order không đổi thứ tự các giai đoạn | Dùng lifecycle extension đúng |
| “getPhase() thấp sẽ stop trước” | Khi shutdown phase **cao dừng trước** | Thiết kế dependent consumer phase cao hơn |
| “Mọi singleton đều gọi stop()” | Chỉ những bean triển khai Lifecycle tham gia stop | Dùng destruction callback cho bean không có start/stop |
| “Phase điều khiển cả thứ tự tạo bean” | Phase không thay dependency/initialization order | Injection/depends-on cho bean creation |
| “stop(Runnable) không cần callback” | Processor có thể chờ timeout | Gọi callback đúng một lần khi thật sự stopped |
| “Callback chạy nghĩa mọi Future đều hoàn tất” | Implementation có thể báo dừng quá sớm | Drain và await với deadline |
| “@PreDestroy là cách tạm dừng một worker” | Callback destruction không dùng cho runtime pause | Dùng Lifecycle.stop / API nghiệp vụ |
| “Mọi singleton được destroy theo tên” | Bean destruction có dependency/lifecycle ordering riêng | Không dựa vào tên bean hoặc thứ tự file |
| “Mọi prototype được auto-destroy khi context close” | Prototype destruction không tự được Spring theo dõi | Caller/owner chịu trách nhiệm |
| “ContextClosedEvent chắc chạy sau SIGKILL” | Process không có cơ hội dọn dẹp | Thiết kế crash recovery |
| “server.shutdown=graceful là mặc định ở Boot 3.3” | Cần cấu hình rõ trong phạm vi Boot 3.3 | Kiểm tra property và server |
| “Graceful timeout là SLA cho cả JVM” | Thời gian chờ per phase, cộng thêm các bước khác | Điều chỉnh budgets của app/container |
| “Listener onClosing gửi một async job nghĩa đã gửi thành công” | submit chưa chắc task completed/durable | Chờ ack, dùng outbox khi quan trọng |
| “Started rồi chắc không thể có shutdown failure” | Shutdown callbacks có thể lỗi/timeout | Quan sát thời gian và error metrics |

## 14. Checklist kiểm tra shutdown khi vận hành

1. **Ai khởi phát shutdown?** `context.close()`, JVM shutdown hook, SIGTERM, deployment rollout, IDE stop hay SIGKILL?
2. **Có `ContextClosedEvent` không?** Nếu không, xem có lỗi trong refresh, process crash hoặc hook chưa chạy.
3. **Listener có block hoặc throw không?** Bản thân shutdown notification không nên làm tắc quy trình dừng.
4. **Bean nào triển khai Lifecycle/SmartLifecycle?** Liệt kê phase, `isRunning()` và ownership.
5. **Thứ tự phase có phù hợp?** Worker phụ thuộc resource nào, resource nào phải stop sau?
6. **Có @DependsOn/injected dependency không?** Quan hệ dependency có thể ảnh hưởng thứ tự stop và destruction.
7. **stop(Runnable) có gọi callback?** Nó báo sau khi drain thực sự hay ngay sau khi submit một task dừng?
8. **Có timeout per phase?** Cấu hình `spring.lifecycle.timeout-per-shutdown-phase`, thời gian thực tế có đủ?
9. **@PreDestroy của singleton có release đúng tài nguyên?** Có double-close, deadlock hoặc blocking I/O không timeout?
10. **Các prototype và object tự new được dọn thế nào?** Không mặc định Spring theo dõi chúng.
11. **Có web server không?** `server.shutdown=graceful` có bật, request mới có được rút route đúng cách?
12. **Kubernetes/LoadBalancer dùng readiness và termination budget nào?** Tránh đóng resource khi vẫn còn request đang xử lý.
13. **Có job durable hay transaction chưa commit không?** Shutdown hook không thay transaction/ack/recovery.
14. **Có nhiều ApplicationContext hay context hierarchy không?** Một event có thể đi qua các context khác nhau; log context ID cho chính xác.
15. **Có test đường lỗi?** Thử stop timeout, destroy throw, startup fail, SIGTERM và forced kill phù hợp môi trường.
16. **Log có đủ và an toàn không?** Ghi mốc, bean name, phase, duration, request count, root cause; tránh secret/token/dữ liệu nhạy cảm.

### 14.1. Nên đo ba khoảng thời gian khác nhau

```text
T0: context.close requested
T1: ContextClosedEvent listeners completed
T2: LifecycleProcessor stop phase(s) completed / timed out
T3: singleton destruction completed
T4: context.close returned
```

- `T0→T1`: thời gian thông báo đóng và listener xử lý.
- `T1→T2`: thời gian dừng lifecycle components và draining in-flight.
- `T2→T3`: thời gian destruction callbacks.
- `T3→T4`: cleanup context cuối cùng.

Không dùng một metric “shutdown took X seconds” để suy nguyên nhân nếu các pha này có hành vi rất khác nhau. Các timestamp là mô hình quan sát; không phải API mà Spring tự sinh đủ bốn mốc cho mọi application.

## 15. Tự kiểm tra

**Câu 1.** Khi gọi `context.close()` bình thường, `ContextClosedEvent` đến trước hay sau `SmartLifecycle.stop()`?

**Đáp:** Trước. Event báo bắt đầu đóng; lifecycle stop được gọi sau khi event được phát theo đường chuẩn.

**Câu 2.** Vì sao một bean có `@PreDestroy` nhưng không có `SmartLifecycle` vẫn được cleanup?

**Đáp:** Vì nó tham gia giai đoạn singleton destruction, không cần triển khai Lifecycle để có destruction callback.

**Câu 3.** Hai SmartLifecycle phase 20 và 100 được stop theo thứ tự nào?

**Đáp:** Theo phase giảm: 100 trước 20, trừ quan hệ dependency tường minh phải ưu tiên.

**Câu 4.** Khi nào nên gọi `callback.run()` trong `stop(Runnable)`?

**Đáp:** Sau khi thao tác dừng thực sự hoàn tất. Nếu dừng bất đồng bộ, báo callback khi task dừng xong, không chỉ khi được schedule.

**Câu 5.** `ContextStoppedEvent` có tự thay cho `ContextClosedEvent` khi close không?

**Đáp:** Không. `context.stop()` và `context.close()` là hai lifecycle operations khác nhau.

**Câu 6.** Thứ tự `@PreDestroy`, `DisposableBean.destroy()` và custom destroy method của **cùng bean**?

**Đáp:** `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, khi cả ba callback được cấu hình hợp lệ và khác tên.

**Câu 7.** Tất cả bean trong context đều được gọi `stop()` trước destroy không?

**Đáp:** Không. Chỉ bean tham gia `Lifecycle`/`SmartLifecycle` mới thuộc lifecycle stop protocol; các singleton khác có thể chỉ có destruction callbacks.

**Câu 8.** Nếu một ContextClosedEvent listener submit task async rồi return, Spring có chờ task xong trước destroy không?

**Đáp:** Không tự chờ. Cần await/ack có deadline hoặc đưa trách nhiệm shutdown vào lifecycle contract phù hợp.

**Câu 9.** `context.stop()` có tự gọi toàn bộ `@PreDestroy` không?

**Đáp:** Không. Nó không có ý nghĩa destroy bean.

**Câu 10.** Nếu refresh failed khi một SmartLifecycle.start() throw, có bảo đảm vẫn đi đúng event→stop→destroy không?

**Đáp:** Không. Shutdown/cleanup trong canceled refresh có đường khác; stop notification có thể không xảy ra trước destruction.

**Câu 11.** Spring Boot 3.3 muốn graceful HTTP shutdown thì dùng property nào?

**Đáp:** `server.shutdown=graceful`, có thể thêm `spring.lifecycle.timeout-per-shutdown-phase` để điều chỉnh thời gian chờ phase.

**Câu 12.** Nếu bị SIGKILL, `@PreDestroy` có bảo đảm chạy không?

**Đáp:** Không. Cần thiết kế dữ liệu và work queue chịu được crash.

**Câu 13.** Prototype bean có `@PreDestroy` có được Spring tự destroy mỗi instance khi context.close() không?

**Đáp:** Không, theo quy tắc prototype mặc định. Caller/owner chịu trách nhiệm cleanup.

**Câu 14.** Nếu một resource singleton bị dependent consumer dùng, ai nên stop trước?

**Đáp:** Consumer nên ngừng nhận/drain trước, rồi mới dừng resource/connector. Dùng phase và dependency để thể hiện ràng buộc.

## 16. Tóm tắt và tài liệu chính thức

Các ý quan trọng:

- **ContextClosedEvent**: phát khi context bắt đầu đóng, **trước** Lifecycle stop và singleton destruction ở đường đóng bình thường.
- **LifecycleProcessor.onClose()**: dừng các `Lifecycle`/`SmartLifecycle` đang running; `SmartLifecycle` phase **cao stop trước**.
- **SmartLifecycle.stop(Runnable)**: callback phải được gọi sau khi dừng thật sự, processor có timeout **theo phase**.
- **destroyBeans()**: sau lifecycle stop, container hủy cached singleton beans. Với **cùng một bean**: `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, khi cấu hình cả ba.
- **context.stop() không phải context.close()**: không đồng nhất `ContextStoppedEvent` với `ContextClosedEvent`.
- **Các ngoại lệ**: startup refresh failure, prototype, object ngoài container, async callbacks, SIGKILL và timeout có thể không theo đủ ba bước chuẩn.
- **Spring Boot 3.3 web graceful shutdown**: bật `server.shutdown=graceful`; stop web server có phase/lifetime riêng, không nên coi ContextClosedEvent là bằng chứng đã drain xong.
- **Shutdown đúng nghĩa** là ngừng nhận việc, hoàn tất hoặc checkpoint in-flight, release resource theo ownership và có chiến lược phục hồi khi JVM bị dừng bất thường.

Tài liệu tham khảo:

1. [Spring Framework 6.1 — AbstractApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose()`, `destroyBeans()` và `close()`.
2. [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): `onClose()`, lifecycle stop phase và timeout mặc định.
3. [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): `stop(Runnable)`, `getPhase()`, `isAutoStartup()`.
4. [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization/destruction order và stop không được bảo đảm trong mọi failed refresh.
5. [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): dependent bean destroy trước dependency bean.
6. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): graceful web shutdown trong early SmartLifecycle phase và cấu hình timeout.
7. [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): event lifecycle, ready/readiness và shutdown hook.

**Kết luận:** Một thông báo “đang đóng” không đồng nghĩa “đã dừng”. Một lời gọi `stop` không đồng nghĩa “đã hủy bean”. Để shutdown an toàn, cần dùng đúng **ContextClosedEvent**, **LifecycleProcessor** và **singleton destruction** cho từng nhiệm vụ, đồng thời xác định ai sở hữu tài nguyên và điều gì phải hoàn tất trước khi dependency bị đóng.
