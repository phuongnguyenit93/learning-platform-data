# ContextRefreshedEvent trong vòng đời Spring Framework và Spring Boot

## 1. ContextRefreshedEvent là gì?

`ContextRefreshedEvent` thuộc `org.springframework.context.event` của **Spring Framework**. Đây là sự kiện được phát khi một `ApplicationContext` **hoàn tất việc khởi tạo hoặc refresh**. Trong ứng dụng Spring Boot thông thường, nó xuất hiện trong quá trình `SpringApplication.run(...)`, sau khi Spring Framework dựng xong phần cốt lõi của bean container, nhưng **trước** khi Spring Boot phát `ApplicationStartedEvent`, gọi `ApplicationRunner`/`CommandLineRunner` và phát `ApplicationReadyEvent`.

Nói ngắn gọn:

- **Context created**: một đối tượng `ApplicationContext` đã tồn tại, nhưng chưa chắc có bean.
- **Context initialized** qua `ApplicationContextInitializer`: những tùy chỉnh sớm đã được áp dụng, nhưng `refresh()` còn ở phía sau.
- **Context refreshed**: các bước chính của `refresh()` hoàn tất; `ContextRefreshedEvent` được phát.
- **Application ready**: Spring Boot đã hoàn tất runner và các bước startup bắt buộc của nó; mốc này **muộn hơn** `ContextRefreshedEvent`.

Đó là lý do event này hữu ích để biết **container đã refresh thành công tới mốc phát sự kiện**, nhưng **không đủ** để kết luận dịch vụ đã sẵn sàng nhận traffic, các tác vụ khởi động đã hoàn tất hoặc mọi dependency ngoài đang khỏe.

Bài học theo **Spring Framework 6.1.x, Spring Boot 3.3.x, Java 17+**. Ta sẽ học API, thời điểm phát, quan hệ với vòng đời bean và `SmartLifecycle`, hai cách viết listener, ví dụ chạy được, parent–child contexts, lỗi thường gặp và cách lựa chọn event đúng mục tiêu.

## 2. ContextRefreshedEvent nằm ở đâu trong chuỗi refresh?

Với một `AbstractApplicationContext` thông thường, có thể hình dung:

```text
SpringApplication.run(args)
    |
    +-- Chuẩn bị Environment
    +-- Tạo ConfigurableApplicationContext
    +-- Chạy ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent       [Spring Boot]
    +-- Nạp nguồn cấu hình / bean definitions
    +-- ApplicationPreparedEvent                 [Spring Boot]
    |
    +-- context.refresh()                        [Spring Framework]
    |      |
    |      +-- prepareRefresh()
    |      +-- obtainFreshBeanFactory()
    |      +-- prepareBeanFactory(...)
    |      +-- BeanFactoryPostProcessor / BeanPostProcessor
    |      +-- Khởi tạo MessageSource, event multicaster
    |      +-- onRefresh() / hạ tầng riêng của context
    |      +-- Đăng ký listener
    |      +-- Tạo các singleton không lazy
    |      +-- finishRefresh()
    |             |
    |             +-- LifecycleProcessor.onRefresh()
    |             |       +-- auto-start SmartLifecycle phù hợp
    |             |
    |             +-- publish ContextRefreshedEvent   <-- trọng tâm
    |
    +-- ApplicationStartedEvent                 [Spring Boot]
    +-- LivenessState.CORRECT                   [Boot availability]
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent                   [Spring Boot]
    +-- ReadinessState.ACCEPTING_TRAFFIC        [Boot availability]
```

Thứ tự trên là **các mốc tiêu biểu**, không phải mọi method đều chạy theo một đường duy nhất trong mọi subclass hay test tùy biến. Đặc biệt, `onRefresh()` có thể chuẩn bị web server và một số sự kiện hạ tầng khác.

Điểm được JavaDoc của `AbstractApplicationContext.finishRefresh()` xác nhận: phương thức này hoàn tất refresh bằng cách gọi `LifecycleProcessor.onRefresh()` rồi phát `ContextRefreshedEvent`. Vì thế, các `SmartLifecycle` bean chọn auto-start có thể đã nhận `start()` **trước khi listener của ContextRefreshedEvent được gọi**.

### 2.1. “Refresh xong” không có nghĩa “mọi việc đã xong”

Trong event handler, các singleton **không lazy** bình thường đã được khởi tạo. Tuy vậy:

- Bean `@Lazy` có thể **chưa được tạo**.
- `ApplicationRunner`/`CommandLineRunner` của Spring Boot **chưa được gọi**.
- Một background worker có thể mới khởi động và chưa thực hiện xong tác vụ.
- Một `SmartLifecycle` bean có thể chỉ được cấu hình chạy khi có lệnh start tường minh, không phải auto-start.
- Việc mở HTTP server không chứng minh dependency bên ngoài đang khỏe hay instance đã được phép nhận traffic.
- Một async listener có thể xử lý sau mốc phát sự kiện, không phải phần bảo đảm của listener đồng bộ.

Vì vậy hãy dùng event này như **dấu mốc vòng đời bean container**, không như một probe readiness toàn diện.

## 3. Đây là sự kiện của Spring Framework, không riêng Spring Boot

Tên class đầy đủ:

```java
org.springframework.context.event.ContextRefreshedEvent
```

`ContextRefreshedEvent` kế thừa `ApplicationContextEvent`, là một `ApplicationEvent` và được framework phát khi `ApplicationContext` được khởi tạo hoặc refresh. Nó xuất hiện trong ứng dụng Spring Framework thuần túy lẫn Spring Boot.

Hai API quan trọng:

```java
ApplicationContext getApplicationContext();
long getTimestamp();
```

Đây là hai chữ ký giải thích API, **không phải chương trình Java độc lập**:

- `getApplicationContext()`: lấy context **đã phát sự kiện**. Dùng nó để xác định instance, phân biệt parent/child và tra cứu bean khi phù hợp.
- `getTimestamp()`: thời điểm đối tượng event được tạo, **không** phải độ dài startup hay bảo đảm thời gian hoàn thành tất cả tác vụ.
- `getSource()` từ superclass cũng liên hệ tới context, nhưng `getApplicationContext()` rõ ý nghĩa và type hơn.

Không nên tự tạo `new ContextRefreshedEvent(context)` rồi publish để giả lập việc đã refresh. Đó chỉ là một object event: Spring không tự chạy toàn bộ chuỗi `refresh()` chỉ vì bạn phát sự kiện bằng tay.

### 3.1. Context active có bằng ready?

Ở thời điểm event, context thông thường báo `isActive() == true`. Tuy nhiên `AbstractApplicationContext` có thể đặt cờ active **sớm trong `refresh()`**. Kết hợp `isActive()` với `ContextRefreshedEvent` cho thấy bạn đã quan sát một mốc cụ thể, nhưng vẫn chưa chứng minh:

- Spring Boot đã chạy các runner.
- `ReadinessState` đang là `ACCEPTING_TRAFFIC`.
- Kubernetes probe trả về 200.
- Database, cache hoặc queue còn đáp ứng.
- Toàn bộ asynchronous startup job đã hoàn thành.

Khi cần quyết định nhận traffic, hãy dùng cơ chế availability/readiness được thiết kế cho vận hành.

## 4. ContextRefreshedEvent khác các sự kiện khởi động như thế nào?

| Sự kiện | Nguồn | Mốc phát | Bean ứng dụng thông thường đã sẵn sàng? |
| --- | --- | --- | --- |
| `ApplicationContextInitializedEvent` | Spring Boot | Sau khi `ApplicationContextInitializer` chạy, trước nạp bean definitions | Chưa. |
| `ApplicationPreparedEvent` | Spring Boot | Sau khi nạp bean definitions, trước `refresh()` | Chưa. |
| **`ContextRefreshedEvent`** | **Spring Framework** | **Cuối `refresh()`, sau khởi tạo singleton thường và lifecycle auto-start** | **Thường đã có các singleton không lazy.** |
| `ApplicationStartedEvent` | Spring Boot | Sau refresh, trước runner | Đã refresh; runner chưa chạy. |
| `ApplicationReadyEvent` | Spring Boot | Sau runner | Mốc Boot hoàn tất startup và sắp thông báo accepting traffic. |
| `ContextStartedEvent` | Spring Framework | Khi gọi `ConfigurableApplicationContext.start()` | Chỉ nói về start của lifecycle processor; không đồng nghĩa refresh. |
| `ContextStoppedEvent` | Spring Framework | Khi gọi `ConfigurableApplicationContext.stop()` | Bean container thường vẫn active. |
| `ContextClosedEvent` | Spring Framework | Trong quá trình đóng context | Đang shutdown, không phải refresh. |

**Hai điểm rất dễ nhầm:**

1. `ApplicationContextInitializedEvent` có chữ “Initialized”, nhưng là **mốc sớm của Boot** trước nạp definitions/refresh. `ContextRefreshedEvent` là **mốc sau khi Spring Framework refresh context**.
2. `ContextStartedEvent` được phát khi gọi `context.start()`; nó **không** được phát chỉ vì Boot đã phát `ApplicationStartedEvent`. Hai loại event có tên gần nhau nhưng được điều khiển bởi những cơ chế khác.

### 4.1. Thứ tự ContextRefreshedEvent và ApplicationStartedEvent

Trong một lần startup chuẩn thành công:

```text
ApplicationPreparedEvent
      |
context.refresh()
      |
ContextRefreshedEvent
      |
ApplicationStartedEvent
      |
ApplicationRunner / CommandLineRunner
      |
ApplicationReadyEvent
```

Khi listener của `ContextRefreshedEvent` chạy đồng bộ, `SpringApplication.run(...)` còn đang trong quá trình refresh, chưa trả về context cho method `main`. Nếu handler ném exception không được xử lý, startup có thể bị hủy trước khi đạt `ApplicationStartedEvent`.

## 5. Cách 1: Bắt event bằng @EventListener trong một bean

Đối với `ContextRefreshedEvent`, cách thông dụng là annotation `@EventListener` trong một bean được Spring quản lý:

```java
package com.example.lifecycle;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshLogger {

    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed: "
                + event.getApplicationContext().getId());
    }
}
```

Đây là **file Java hoàn chỉnh** tại `src/main/java/com/example/lifecycle/RefreshLogger.java` trong một project Spring Boot với component scan bao phủ package này. Khi container dựng xong các singleton không lazy và phát event, bộ xử lý `@EventListener` đã được cấu hình để gọi method tương ứng.

Vì sao cách này hoạt động, trong khi `@EventListener(ApplicationContextInitializedEvent.class)` của bean thường lại đến quá muộn? Vì `ContextRefreshedEvent` được phát **trong cuối refresh**, sau khi Spring đã xử lý các singleton và đăng ký listener methods; còn `ApplicationContextInitializedEvent` đến **trước refresh**, khi bean listener chưa được tạo.

### 5.1. Kỹ thuật event listener trong Spring Framework

Method `@EventListener` có thể nhận event làm tham số. Với một tham số `ContextRefreshedEvent`, có thể không cần chỉ rõ class trong annotation:

```java
@EventListener
public void handle(ContextRefreshedEvent event) {
    // Dùng event.getApplicationContext().
}
```

Đoạn này là **method minh họa bên trong một Spring bean**, không phải class độc lập. Các dạng `@EventListener(ContextRefreshedEvent.class)` và `@EventListener` với event parameter đều có thể dùng.

Handler đồng bộ mặc định **nên ngắn, dễ dự đoán**. Nếu cần làm việc nặng hoặc cần bảo đảm chỉ khi toàn bộ Boot startup hoàn tất, hãy cân nhắc `ApplicationRunner` hoặc event muộn hơn.

## 6. Cách 2: Implements ApplicationListener<ContextRefreshedEvent>

Nếu muốn type-safe với class listener riêng:

```java
package com.example.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.stereotype.Component;

@Component
public class RefreshListener
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("Framework context id: "
                + event.getApplicationContext().getId());
    }
}
```

Đây cũng là **file Java hoàn chỉnh** trong project có Spring context. Listener này được đăng ký như bean và được Spring gọi khi event phát ra.

Có thể đăng ký một `ApplicationListener<ContextRefreshedEvent>` thủ công **trước `run`** bằng `SpringApplication.addListeners(...)`, hoặc `ConfigurableApplicationContext.addApplicationListener(...)` trước refresh trong một initializer. Nhưng **không cần** dùng cơ chế đăng ký cực sớm cho event này nếu đã có listener bean đúng phạm vi quét.

**Không đăng ký cả hai ví dụ trong cùng project nếu không muốn hai lần log**: đây là hai cách thay thế hoặc có thể cùng tồn tại nếu chủ đích cần hai handler.

### 6.1. Chọn @EventListener hay ApplicationListener?

| Tiêu chí | `@EventListener` | `ApplicationListener` |
| --- | --- | --- |
| Cú pháp | Method annotation trong bean | Class/interface có generic type |
| Phù hợp | Logic sự kiện ngắn trong ứng dụng | Component listener riêng, tái sử dụng dễ |
| Đăng ký qua component scan | Có | Có |
| Có thể đăng ký sớm ngoài BeanFactory | Không phải mục đích chính | Có, qua `SpringApplication.addListeners` |
| Type-safe | Theo tham số/event class | Theo generic parameter |
| Cần filter parent-child | Có thể cần | Có thể cần |

Không có “cách duy nhất đúng”; chọn theo khả năng kiểm thử, vị trí lifecycle và kiến trúc dự án.

## 7. Ví dụ hoàn chỉnh: quan sát refresh, SmartLifecycle và Boot readiness

Chúng ta tạo một ứng dụng Spring Boot **không mở HTTP server** để minh họa đúng thứ tự mà không bị ảnh hưởng bởi servlet container. Chương trình có:

- Một `SmartLifecycle` auto-start, in log khi bắt đầu và dừng.
- Một bean observer bắt `ContextRefreshedEvent`, `ApplicationStartedEvent` và `ApplicationReadyEvent`.
- Một `ApplicationRunner` in log sau `ApplicationStartedEvent`.
- `try-with-resources` để đóng context có trật tự khi `run(...)` trả về.

**File:** `src/main/java/com/example/lifecycle/ContextRefreshDemoApplication.java`

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ContextRefreshDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextRefreshDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("06 RUN_RETURNED active=" + context.isActive());
        }
    }

    @Bean
    SmartLifecycle sampleLifecycle() {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                running = true;
                System.out.println("01 LIFECYCLE_START");
            }

            @Override
            public void stop() {
                running = false;
                System.out.println("07 LIFECYCLE_STOP");
            }

            @Override
            public void stop(Runnable callback) {
                stop();
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
                return 0;
            }
        };
    }

    @Bean
    EventObserver eventObserver(ApplicationContext ownContext) {
        return new EventObserver(ownContext);
    }

    @Bean
    ApplicationRunner reportRunner() {
        return arguments -> System.out.println("04 RUNNER");
    }

    public static final class EventObserver {
        private final ApplicationContext ownContext;

        public EventObserver(ApplicationContext ownContext) {
            this.ownContext = ownContext;
        }

        @EventListener
        public void afterRefresh(ContextRefreshedEvent event) {
            if (event.getApplicationContext() != ownContext) {
                return; // Bỏ event phát từ context con nếu có.
            }
            ConfigurableApplicationContext context =
                    (ConfigurableApplicationContext) ownContext;
            System.out.println("02 CONTEXT_REFRESHED active="
                    + context.isActive());
        }

        @EventListener
        public void afterStarted(ApplicationStartedEvent event) {
            if (event.getApplicationContext() == ownContext) {
                System.out.println("03 APPLICATION_STARTED");
            }
        }

        @EventListener
        public void afterReady(ApplicationReadyEvent event) {
            if (event.getApplicationContext() == ownContext) {
                System.out.println("05 APPLICATION_READY");
            }
        }
    }
}
```

### 7.1. Dependency và môi trường

Tại một project Java 17+ đã thiết lập Spring Boot Gradle plugin 3.3.x cùng dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Nếu muốn build script tối thiểu theo Gradle Groovy DSL, phần chính có thể là:

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

Lưu ý: build script trên giả định bạn có Gradle và plugin phù hợp; ví dụ này minh họa cấu hình Boot 3.3.x, không yêu cầu phải dùng đúng patch version đã ghi nếu dự án khóa một bản 3.3.x tương thích khác. Với `WebApplicationType.NONE`, application không cần web starter, cổng 8080 hay database.

### 7.2. Chạy chương trình

Tại thư mục project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Nếu dự án có nhiều class `main`, hãy cấu hình đúng main class của `bootRun` hoặc để một main class duy nhất trong source set.

### 7.3. Log theo đúng thứ tự vòng đời

Bỏ qua banner, các dòng INFO/DEBUG của Spring và log Gradle; các dòng **do ví dụ tự in** theo thứ tự kỳ vọng:

```text
01 LIFECYCLE_START
02 CONTEXT_REFRESHED active=true
03 APPLICATION_STARTED
04 RUNNER
05 APPLICATION_READY
06 RUN_RETURNED active=true
07 LIFECYCLE_STOP
```

Giải thích từng mốc:

1. `01`: `DefaultLifecycleProcessor.onRefresh()` auto-start `SmartLifecycle` bean.
2. `02`: `ContextRefreshedEvent` được publish sau bước đó; context đã active.
3. `03`: Spring Boot phát `ApplicationStartedEvent` sau `refresh()`.
4. `04`: `ApplicationRunner` được Boot gọi sau `ApplicationStartedEvent`.
5. `05`: Boot phát `ApplicationReadyEvent` khi runner đã chạy xong.
6. `06`: `SpringApplication.run(...)` trả về context cho `main`.
7. `07`: thoát khỏi khối `try-with-resources` làm context đóng, và lifecycle bean nhận `stop()`.

Với một context chuẩn và không có listener/runner khác chen vào, thứ tự **các dòng do chính đoạn mã này in** là ổn định. Spring có thể in nhiều log framework xen kẽ; khi thêm listener bất đồng bộ hoặc nhiều context, thứ tự log toàn cục có thể phức tạp hơn.

**Quan trọng:** `EventObserver` được đăng ký thành `@Bean`, nhưng vẫn bắt được `ContextRefreshedEvent` vì bean listener và bộ xử lý annotation đã sẵn sàng **trước `finishRefresh()`**. Đó là điểm khác với event cực sớm như `ApplicationContextInitializedEvent`.

### 7.4. Có cần @EnableAsync để nhận event?

Không. Ví dụ xử lý sự kiện **đồng bộ**, là cơ chế thông thường. Nếu thêm `@Async` vào listener và cấu hình async phù hợp, thứ tự hoàn thành của handler không còn bảo đảm như log ở trên. Đừng chuyển handler sang async nếu logic của bạn là điều kiện bắt buộc trước khi ứng dụng bắt đầu phục vụ; khi đó phải dùng một cơ chế phối hợp có kết quả hoàn thành rõ ràng, không chỉ fire-and-forget.

## 8. @PostConstruct, singleton và @Lazy tại thời điểm event

Trong `refresh()`, Spring thường:

1. Đăng ký và thực thi `BeanFactoryPostProcessor`, chuẩn bị `BeanPostProcessor`.
2. Khởi tạo các singleton **không lazy** và gọi các callback khởi tạo liên quan.
3. Hoàn tất refresh, khởi động lifecycle components và phát `ContextRefreshedEvent`.

Ví dụ:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class InventoryCache {

    @PostConstruct
    public void initialize() {
        System.out.println("InventoryCache initialized");
    }
}
```

Nếu class `InventoryCache` được component scan, singleton không lazy này thường chạy `@PostConstruct` **trước khi** listener nhận `ContextRefreshedEvent`. Đây là thứ tự trong cùng application context bình thường, không phụ thuộc vào HTTP server.

Nhưng nếu bean là `@Lazy`:

```java
@Lazy
@Component
public class LazyExporter {
    // Constructor chỉ chạy khi bean thực sự được yêu cầu.
}
```

Đây là class minh họa, cần import `@Lazy` và `@Component`; không phải một chương trình có main riêng. `ContextRefreshedEvent` **không buộc mọi bean lazy phải được tạo**. Bean lazy có thể chỉ được khởi tạo khi mã gọi đến nó sau này.

### 8.1. Không nên tự getBean cho tất cả loại bean khi nhận event

Mặc dù BeanFactory đã hoạt động, việc gọi hàng loạt `getBean(...)` trong listener có thể:

- Phá ý nghĩa lazy initialization.
- Kéo dài startup.
- Kích hoạt network I/O hoặc load dữ liệu không kiểm soát.
- Tạo phụ thuộc vòng hoặc lỗi khó truy vết.
- Làm event handler vô tình trở thành công việc nghiệp vụ có tác dụng phụ.

Hãy chỉ lấy dependency mà handler thật sự cần. Khi cần load dữ liệu ban đầu như một bước startup bắt buộc, `ApplicationRunner` thường có vị trí rõ ràng hơn trong chuỗi Spring Boot.

## 9. SmartLifecycle và ContextRefreshedEvent

`Lifecycle` và `SmartLifecycle` cung cấp contract `start()`/`stop()` cho một số bean có trạng thái chạy. Spring dùng `LifecycleProcessor` (thông thường là `DefaultLifecycleProcessor`) để điều phối chúng.

`SmartLifecycle` bổ sung:

- `isAutoStartup()`: bean có tự khởi động khi context refresh không.
- `getPhase()`: pha để sắp thứ tự start/stop.
- `stop(Runnable callback)`: báo kết thúc stop bất đồng bộ; phải gọi callback khi dừng xong.

Trong `AbstractApplicationContext.finishRefresh()`, processor nhận `onRefresh()` **trước** khi phát `ContextRefreshedEvent`. Những `SmartLifecycle` bean có auto-start phù hợp vì vậy có thể được start trước listener của event.

### 9.1. Nhưng không phải mọi bean Lifecycle đều đã running

Một bean chỉ implements `Lifecycle` thường không được auto-start theo cách `SmartLifecycle.isAutoStartup()`. Cũng có thể có `SmartLifecycle` trả `false` cho `isAutoStartup()`. Vì thế:

```text
ContextRefreshedEvent đã phát
      !=
mọi Lifecycle bean đều running
      !=
mọi background job đã hoàn thành
```

Nếu bạn cần biết một worker cụ thể đã tiếp nhận nhiệm vụ, hãy kiểm tra trạng thái thực tế của worker đó hoặc thiết kế sự kiện/health indicator chuyên biệt; không suy luận từ context refresh.

### 9.2. ContextRefreshedEvent có bị phát lại khi gọi start()?

**Không phải theo contract thông thường.** `context.start()` yêu cầu `LifecycleProcessor` khởi động các bean lifecycle phù hợp và phát `ContextStartedEvent`. Nó **không gọi lại `refresh()`**, nên không tạo thêm một `ContextRefreshedEvent` chỉ vì start sau stop.

Tương tự, `context.stop()` phát `ContextStoppedEvent` và dừng lifecycle beans; còn `context.close()` đi vào shutdown và phát `ContextClosedEvent`. Ba thao tác không nên bị nhầm thành “refresh”.

## 10. ContextRefreshedEvent có thể được phát nhiều lần không?

Không có bảo đảm “chỉ một lần cho cả JVM”. Những tình huống phải xét:

- **Nhiều context:** ứng dụng có parent/child contexts, nhiều `SpringApplication` hoặc nhiều bài test chạy các context khác nhau.
- **Một số implementation hỗ trợ refresh lặp:** gọi lại `refresh()` hợp lệ có thể phát event mới.
- **Event propagation:** một event phát trong child context có thể được gửi đến listener ở parent context.
- **Đăng ký listener hai lần:** cùng logic có thể nhận hai callback dù chỉ có một context refresh thật.

Ngược lại, nhiều implementation dựa trên `GenericApplicationContext` chỉ cho phép refresh một lần. `Spring Boot` thường không thiết kế luồng runtime dựa trên việc tự gọi `refresh()` liên tục; đừng lấy sự kiện này làm nút restart ứng dụng.

### 10.1. Tại sao listener ở parent nhận event của child?

Spring Framework cho phép event từ context con lan lên context cha. Nếu bạn có:

```text
Parent ApplicationContext
    |
    +-- Child ApplicationContext
            |
            +-- refresh() -> ContextRefreshedEvent(child)
                                   |
                              Child listeners
                                   |
                              Parent listeners
```

Listener ở parent có thể nhận event của **child**, chứ không phải chỉ event do parent phát. Nếu logic nạp cache hoặc đăng ký resource chạy mỗi lần nhận event mà không lọc, nó có thể được thực hiện hai lần hoặc với context không mong muốn.

### 10.2. Cách lọc event về đúng context

Ví dụ một Spring bean được inject context hiện tại:

```java
@Component
public class OwnContextRefreshHandler {

    private final ApplicationContext ownContext;

    public OwnContextRefreshHandler(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("My own context refreshed");
    }
}
```

Đây là **class Java minh họa** trong package dự án; cần import `org.springframework.stereotype.Component`, `ApplicationContext`, `ContextRefreshedEvent` và `EventListener`. So sánh identity bằng `!=` nhằm trả lời “chính context đã phát event có phải context của bean này không?”, không so sánh tên displayName có thể trùng.

Nếu muốn thực hiện side effect **một lần cho mỗi lần deploy**, việc lọc context mới giải quyết một phần. Vẫn cần idempotence và strategy phù hợp nếu test hoặc runtime tạo context nhiều lần.

## 11. Có nên dùng ContextRefreshedEvent để chạy business initialization?

Phụ thuộc vào thứ bạn cần.

**Tác vụ chỉ cần container đã refresh:** một listener có thể phù hợp để ghi log cấu hình, đăng ký một hook nhẹ hoặc quan sát thông tin các bean đã dựng.

**Tác vụ startup bắt buộc, cần bean/repository:** thường dùng `ApplicationRunner`/`CommandLineRunner` vì chuỗi của Spring Boot được thiết kế chạy runner **sau context refresh và trước ready**.

**Tác vụ phải hoàn thành trước khi instance nhận traffic:** nên được phối hợp với readiness thật; không chỉ tạo một `@Async @EventListener(ContextRefreshedEvent.class)` rồi mặc định app sẽ chờ tác vụ xong.

### 11.1. Tình huống: khởi tạo cache từ database

Giả sử ứng dụng cần nạp một cache dữ liệu. Việc đặt query database nặng trong listener `ContextRefreshedEvent` có thể làm startup bị chặn, tăng thời gian chờ và khiến refresh thất bại khi database gián đoạn. Một phương án rõ ràng hơn:

```java
@Bean
ApplicationRunner warmCache(CacheService service) {
    return args -> service.warmUp();
}
```

Đây là snippet trong `@Configuration`/`@SpringBootApplication`; giả định `CacheService` là bean có method `warmUp()`, có import `ApplicationRunner` và `@Bean`. Khi runner được Boot gọi, singleton đã sẵn sàng. Đặt timeout, xử lý lỗi và health/readiness theo yêu cầu nghiệp vụ. **Đừng coi snippet này là Java độc lập** nếu chưa có `CacheService`.

### 11.2. Tình huống: đăng ký một listener hoặc metric sau refresh

Nếu chỉ cần log “context X đã refresh” và đọc số lượng bean definitions, một listener ngắn là phù hợp. Nhưng đừng dùng event như một “hook cuối cùng để thêm mọi bean”: tại thời điểm đó quá trình tạo singleton đã hoàn tất; những thay đổi bean definitions trễ có thể không được đưa vào trạng thái sẵn sàng như dự định.

Khi muốn sửa cấu hình BeanFactory, hãy cân nhắc `BeanDefinitionRegistryPostProcessor` hoặc `BeanFactoryPostProcessor`, chạy **trước** tạo singleton.

## 12. Lỗi trong listener sẽ ảnh hưởng startup thế nào?

Theo cấu hình sự kiện đồng bộ thông thường, listener được gọi ngay trên đường phát `ContextRefreshedEvent`. Nếu listener ném exception không được xử lý, exception có thể lan qua `publishEvent` và khiến `refresh()` thất bại. Spring sẽ thực hiện cleanup phù hợp và Boot có thể phát `ApplicationFailedEvent`.

Đó là lý do một handler chỉ để audit/diagnostic không nên làm thay đổi kết quả startup vì lỗi I/O phụ trợ. Ngược lại, nếu nó xác minh một điều kiện **bắt buộc** để khởi động an toàn, fail fast có chủ đích có thể hợp lý.

### 12.1. Phân biệt phản ứng của listener đồng bộ và bất đồng bộ

- **Đồng bộ (thường mặc định):** code handler chạy trên đường publish; timeout/lỗi có thể ảnh hưởng startup.
- **Bất đồng bộ có cấu hình:** handler có thể chạy sau khi `publishEvent` đã trả về, lỗi xử lý theo cơ chế executor/async; startup có thể tiếp tục mà chưa có kết quả nghiệp vụ.
- **Transaction-bound listener:** `@TransactionalEventListener` có contract phụ thuộc transaction. `ContextRefreshedEvent` bình thường không được phát trong một transaction nghiệp vụ, nên không dùng nó như thay thế trực tiếp `@EventListener`.

Đừng gọi `Thread.sleep(...)` trong event listener để “đợi server ready”. Hãy dùng đúng event hoặc readiness API của Spring Boot.

### 12.2. Lỗi startup sau refresh vẫn có thể xảy ra

Một ứng dụng có thể đã phát `ContextRefreshedEvent` thành công nhưng sau đó `ApplicationRunner` ném exception. Khi đó `ApplicationStartedEvent` có thể đã xảy ra, còn `ApplicationReadyEvent` thì không. Vì thế câu “đã thấy ContextRefreshedEvent trong log” **không phải bằng chứng toàn bộ startup PASS**.

## 13. Sự kiện có liên quan đến trạng thái active, running, closed không?

`ConfigurableApplicationContext` cung cấp `isActive()` và các thao tác `Lifecycle` như `start()`, `stop()` và `isRunning()`. Cần phân biệt:

- **`isActive()`:** context đang active theo lifecycle refresh/close. Trong `ContextRefreshedEvent`, thông thường là `true`.
- **`isRunning()`:** trạng thái hoạt động theo `LifecycleProcessor`; thường là `true` sau `finishRefresh()` nếu dùng processor mặc định, nhưng không có nghĩa mọi ứng dụng/bean đều khỏe.
- **`close()`:** đóng context, dừng lifecycle beans và hủy singleton; `ContextClosedEvent` thuộc đường shutdown.
- **`start()/stop()`:** điều phối managed lifecycle beans; không làm lại toàn bộ `refresh()`.
- **“Closed”** không có một `ConfigurableApplicationContext.isClosed()` tổng quát trong contract sử dụng phổ biến; `isActive() == false` có thể do chưa refresh hoặc đã close.

Ví dụ trạng thái đơn giản:

```text
Trước refresh:
    active=false, running=false

Sau refresh thành công:
    active=true, running=true (thông thường)

Sau context.stop():
    active=true, running=false

Sau context.start():
    active=true, running=true

Sau context.close():
    active=false, running=false
```

Không phải mọi context/lifecycle processor tùy biến đều có kết quả giống hệt bảng. Điều chắc chắn là **`ContextRefreshedEvent` và `ContextClosedEvent` thuộc hai thời điểm đối lập của vòng đời context**.

## 14. Spring Boot readiness, liveness và ContextRefreshedEvent

Trong Spring Boot 3.3, `ApplicationAvailability` tách hai khái niệm vận hành:

- `LivenessState`: `CORRECT` hoặc `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC`.

Lộ trình startup thường là:

```text
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
```

Vì vậy, tại `ContextRefreshedEvent`, readiness chưa chắc đã cho phép nhận traffic. Nếu ứng dụng có Spring Boot Actuator, health probes `/actuator/health/liveness` và `/actuator/health/readiness` có thể hữu ích khi được bật/cấu hình phù hợp. Trong Kubernetes, Boot có cơ chế tự bật availability probes phù hợp, nhưng endpoint thực tế còn phụ thuộc actuator configuration, management port và network path.

**Không thay thế readiness bằng listener đặt boolean “READY=true” tại `ContextRefreshedEvent`.** Điều đó có thể mở traffic trong khi runner chưa hoàn tất hoặc một dependency bắt buộc chưa sẵn sàng.

## 15. Phân biệt ContextRefreshedEvent với lifecycle test

Trong test Spring Boot hoặc Spring Framework:

- `@SpringBootTest` thường sử dụng Spring TestContext, có thể **cache** `ApplicationContext` giữa nhiều test.
- `ContextRefreshedEvent` phát khi context thực sự refresh, **không nhất thiết trước mọi test method**.
- Nếu chỉ có một cached context cho cả test suite, listener có thể được gọi ít lần hơn số lượng bài test.
- Dùng `@DirtiesContext` có thể khiến test framework hủy cache và tạo/refresh context mới, từ đó có event mới; không dùng bừa bãi vì tốn startup time.
- Nếu listener có side effect ra database, queue hay tài nguyên thật, test có thể vô tình chạy side effect mỗi lần refresh hoặc khi context được khởi tạo lại.

Để kiểm thử riêng một listener, nhiều khi tốt hơn là unit-test method xử lý sự kiện với context giả/đã tạo phù hợp, và integration-test mốc thật ở số lượng tối thiểu.

### 15.1. Sự kiện theo parent-child trong test

Một test có context hierarchy có thể tạo event từ parent và child; listener ở parent có thể nhận cả event của child. Khi đếm số lần listener chạy, hãy ghi rõ context id/identity và lọc đúng context thay vì mặc định một callback = một application startup.

## 16. Chẩn đoán các hiểu lầm phổ biến

| Triệu chứng hoặc phát biểu | Nguyên nhân/điều đúng | Cách giải quyết |
| --- | --- | --- |
| “ContextRefreshedEvent nghĩa ứng dụng hoàn toàn ready.” | Runner/readiness của Boot còn đến sau. | Dùng `ApplicationReadyEvent` và readiness probe. |
| “Không bắt được ContextRefreshedEvent bằng @EventListener.” | Có thể bean listener không được scan, annotation sai import hoặc context khác. | Kiểm tra component scan, bean đăng ký và context identity. |
| “Phải addListeners từ main mới bắt được event.” | Đó là yêu cầu chính cho một số **early Boot events**. | Với ContextRefreshedEvent, listener bean hoặc `@EventListener` thường đủ. |
| “ContextRefreshedEvent chạy trước @PostConstruct.” | Eager singleton init và callback thường ở trước finishRefresh. | Kiểm tra lazy/non-lazy và bean lifecycle. |
| “Thấy event tức mọi @Lazy bean đã tạo xong.” | Lazy bean có thể chưa được tạo. | Không giả định; chỉ cần thì yêu cầu bean cụ thể. |
| “SmartLifecycle luôn start sau ContextRefreshedEvent.” | `LifecycleProcessor.onRefresh()` thông thường ở trước publish event. | Quan sát phase và `isAutoStartup()`. |
| “context.start() phát lại ContextRefreshedEvent.” | `start()` liên quan `ContextStartedEvent`. | Phân biệt refresh với start. |
| “Một event chỉ xuất hiện một lần cho cả JVM.” | Nhiều context/refresh hoặc propagation có thể tạo nhiều callback. | Lọc context và thiết kế idempotent. |
| “Listener trong parent chỉ nghe parent.” | Event từ child có thể truyền lên parent. | So sánh `event.getApplicationContext() == ownContext`. |
| “Có ContextRefreshedEvent thì startup chắc chắn sẽ thành công.” | Runner hoặc callback muộn vẫn có thể fail. | Quan sát `ApplicationReadyEvent`/exception sau event. |
| “ContextRefreshedEvent dùng để tái khởi động context.” | Event là thông báo, không phải lệnh refresh. | Để framework sở hữu lifecycle. |
| “Bắt event rồi chạy I/O vô hạn không ảnh hưởng khởi động.” | Listener đồng bộ có thể chặn/hỏng refresh. | Giới hạn công việc, timeout, runner hoặc kiến trúc khác. |
| “@TransactionalEventListener là tương đương @EventListener.” | Transactional listener có điều kiện transaction riêng. | Dùng `@EventListener` cho event context thông thường. |
| “Thấy HTTP 404 nghĩa ContextRefreshedEvent chưa xảy ra.” | Server có thể đã chạy nhưng không có route. | Kiểm tra logs, handler mappings, URL và probes. |

## 17. Checklist triển khai trong dự án thật

1. Xác định cần mốc **context refresh**, **Boot started**, **runner complete** hay **readiness** trước khi chọn event.
2. Với `ContextRefreshedEvent`, ưu tiên một listener bean nhỏ, rõ ràng, idempotent.
3. Nếu dùng parent/child contexts, luôn kiểm tra `event.getApplicationContext()`.
4. Không giả định mọi bean lazy đã được tạo; tránh lấy tất cả bean chỉ để kiểm tra.
5. Nếu dùng `SmartLifecycle`, đối chiếu `isAutoStartup()` và `getPhase()`.
6. Không gọi `context.refresh()` hoặc `context.close()` từ listener chỉ để “điều khiển tiến độ”.
7. Không làm network I/O blocking hoặc retry vô hạn trong handler đồng bộ.
8. Với tác vụ bắt buộc trước ready, dùng runner + timeout + failure policy; xác minh readiness.
9. Không coi event này là sự kiện shutdown; `ContextClosedEvent` mới thuộc quá trình đóng context.
10. Nếu app có test context caching, đừng viết logic “mỗi test phải có một ContextRefreshedEvent”.
11. Khi startup fail, phân biệt lỗi trong refresh listener và lỗi ở runner sau refresh.
12. Kiểm tra tiếng log của chính ứng dụng và log framework riêng biệt; không dựa vào thứ tự một số logger bất đồng bộ.
13. Với service production, kết hợp traces/metrics, Spring Boot Actuator và dependency health thay vì một boolean tự đặt.
14. Khi cần tách thao tác theo giai đoạn, dùng `BeanFactoryPostProcessor`, `@PostConstruct`, `SmartLifecycle`, `ApplicationRunner` hoặc `ApplicationReadyEvent` đúng contract.

## 18. Câu hỏi tự kiểm tra

**1. ContextRefreshedEvent có xảy ra trước khi singleton không lazy được tạo không?**

Không, trong `AbstractApplicationContext` thông thường nó được phát ở cuối `refresh()`, sau khi container hoàn tất bước khởi tạo singleton không lazy.

**2. @EventListener trong một bean bình thường có bắt được ContextRefreshedEvent không?**

Có. Khác với các sự kiện Boot rất sớm, event này đến lúc Spring đã có hệ thống xử lý bean listeners.

**3. Tại ContextRefreshedEvent, ApplicationRunner đã chạy chưa?**

Chưa trong trình tự `SpringApplication.run` chuẩn. Runner chạy sau `ApplicationStartedEvent`, còn event refresh diễn ra trước đó.

**4. Khi gọi context.stop() rồi context.start(), event nào phản ánh lệnh start?**

`ContextStartedEvent`, không phải `ContextRefreshedEvent`. Start không tự refresh context.

**5. Một listener ở parent context có thể nhận event của child không?**

Có. Cần so sánh `event.getApplicationContext()` với context thật của listener nếu muốn chỉ xử lý event của chính mình.

**6. ContextRefreshedEvent có chứng minh HTTP server đã ready và backend database luôn khỏe không?**

Không. Nó là mốc vòng đời container; readiness/health cần kiểm tra riêng.

**7. SmartLifecycle được auto-start trước hay sau event refresh?**

Trong `AbstractApplicationContext.finishRefresh()` và processor mặc định, `onRefresh()` start các `SmartLifecycle` phù hợp **trước khi** publish `ContextRefreshedEvent`.

**8. Nếu listener ContextRefreshedEvent đồng bộ ném exception thì sao?**

Nó có thể làm `refresh()`/startup thất bại, kéo theo cleanup và `ApplicationFailedEvent`. Vì vậy cần chọn chiến lược xử lý lỗi có chủ đích.

## 19. Tóm tắt

```text
ApplicationContextInitializedEvent  [Boot: trước nạp bean definitions]
               |
ApplicationPreparedEvent            [Boot: trước refresh]
               |
           refresh()
               |
       tạo singleton không lazy
               |
     LifecycleProcessor.onRefresh()
               |
      ContextRefreshedEvent          [Framework: context refresh]
               |
      ApplicationStartedEvent        [Boot: sau refresh]
               |
        ApplicationRunner
               |
       ApplicationReadyEvent         [Boot: sau runners]
               |
      Readiness ACCEPTING_TRAFFIC
```

**Quy tắc nhớ nhanh:** `ContextRefreshedEvent` nói **Spring bean container đã refresh**, không nói **toàn bộ quy trình startup của Spring Boot đã xong**. Nó khác `ApplicationContextInitializedEvent`, `ContextStartedEvent` và `ContextClosedEvent`. Khi muốn thực hiện công việc cần bean, chọn đúng pha; khi muốn mở traffic, dựa vào readiness; và khi có nhiều contexts, lọc event theo context thật.

## Tài liệu chính thức

- [Spring Framework 6.1 — ContextRefreshedEvent API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html)
- [Spring Framework 6.1 — AbstractApplicationContext API, finishRefresh()](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — Application events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Bean lifecycle, Lifecycle và SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication events and listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Application Availability, readiness/liveness](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)
