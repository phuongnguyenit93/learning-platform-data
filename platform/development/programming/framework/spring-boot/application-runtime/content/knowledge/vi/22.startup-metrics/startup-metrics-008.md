# Đối chiếu thời gian tạo bean, runner và listener

Một ứng dụng Spring Boot có thể **tốn thời gian khởi động** ở nhiều lớp khác nhau: phân tích cấu hình và tạo bean trong `ApplicationContext.refresh()`, chạy `ApplicationRunner` / `CommandLineRunner` sau khi context đã refresh, hoặc thực thi các `ApplicationListener` / `@EventListener` trên đường khởi động. Chỉ nhìn dòng log `Started ... in ... seconds` không đủ để biết **đâu là phần gây chậm và khi nào ứng dụng thực sự sẵn sàng nhận traffic**.

Bài học thuộc **Spring Boot Application Runtime**, nhóm **Đo khởi động**, với phạm vi **“Đối chiếu thời gian tạo bean, runner và listener”**. Ví dụ áp dụng cho **Spring Boot 3.3.x, Spring Framework 6.1, Java 17+**, dùng các mốc `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, công cụ `ApplicationStartup` và phép đo đồng hồ đơn điệu `System.nanoTime()`.

**Mục tiêu:** có thể trả lời bằng bằng chứng rằng độ trễ chủ yếu nằm ở **bean creation**, **runner**, **listener** hay phần hạ tầng khác; không cộng các khoảng trùng nhau, không nhầm “started” với “ready”, và có quy trình đo lặp để quyết định tối ưu.

## 1. Bản đồ các giai đoạn cần đối chiếu

~~~text
JVM / main()
  |
  v
SpringApplication.run(args)
  |
  +-- Environment, bootstrap, tạo context
  |
  +-- ApplicationPreparedEvent
  |
  +-- ApplicationContext.refresh()
  |     |
  |     +-- đọc/đăng ký bean definitions
  |     +-- BeanFactoryPostProcessor / BeanPostProcessor
  |     +-- tạo singleton non-lazy, gọi constructor/@Bean
  |     +-- dependency injection, @PostConstruct, init methods
  |     +-- khởi động Lifecycle / SmartLifecycle phù hợp
  |     +-- ContextRefreshedEvent -> listener tương ứng
  |
  +-- ApplicationStartedEvent -> listeners
  |
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent -> listeners
  |
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  v
SpringApplication.run(...) trả về
~~~

Đây là **thứ tự các mốc chính**, không phải toàn bộ các callback hay sự kiện có thể xảy ra. Với ứng dụng web, server có thể được khởi tạo trong quá trình refresh; `WebServerInitializedEvent` có thể nằm trước `ApplicationStartedEvent`.

Ba đoạn thời gian quan trọng nhất:

| Phạm vi | Vị trí trong lifecycle | Cần quan sát |
| --- | --- | --- |
| Tạo và khởi tạo bean | Chủ yếu trong `refresh()` của singleton eager, nhưng bean lazy có thể tạo muộn | Constructor, factory method, injection, `@PostConstruct`, init callbacks, dependencies |
| Runner | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` | Mỗi `ApplicationRunner` / `CommandLineRunner`, thứ tự `Ordered`, blocking I/O |
| Listener | Tại thời điểm event được publish; nhiều listener chạy đồng bộ mặc định | Event nào, listener nào, thời gian xử lý, ảnh hưởng đến mốc kế tiếp |

**Điểm rất quan trọng:** `ApplicationStartedEvent` được phát **sau khi refresh context** nhưng **trước runner**. `ApplicationReadyEvent` được phát **sau khi mọi runner kết thúc thành công**. Listener cho `ApplicationStartedEvent` có thể làm chậm thời điểm runner bắt đầu; listener cho `ApplicationReadyEvent` có thể làm chậm thời điểm `run()` trả về. <escape>Hai loại listener không nằm cùng vị trí trên timeline.</escape>

## 2. “Bean được tạo” bao gồm những bước nào?

Trong Spring, việc tạo bean không phải chỉ là gọi constructor:

~~~text
Lấy bean từ BeanFactory
  |
  +-- Xác định dependency
  |     +-- có thể phải tạo các dependency trước
  |
  +-- Gọi constructor hoặc factory method @Bean
  |
  +-- Populate properties / inject dependencies
  |
  +-- BeanPostProcessor trước khởi tạo
  |
  +-- @PostConstruct / InitializingBean.afterPropertiesSet()
  |   / custom initMethod
  |
  +-- BeanPostProcessor sau khởi tạo / proxy
  |
  v
Bean sẵn sàng cho việc sử dụng phù hợp
~~~

Những khoảng thời gian sau **không tự bằng nhau**:

- **Thời gian constructor:** chỉ thời gian chạy constructor của một object.
- **Thời gian phương thức `@Bean`:** thời gian gọi factory method; có thể bao gồm tạo object bên trong method, nhưng không tự bao trùm mọi post-processing sau method trả về.
- **Thời gian `@PostConstruct`:** callback khởi tạo của một bean, không tính các dependency khác.
- **Thời gian `spring.beans.instantiate` trong startup tracing:** một bước framework instrument có thể bao gồm việc khởi tạo bean và dependency liên quan, **không phải phép đo constructor đơn lẻ**.
- **Thời gian `refresh()`:** còn bao gồm xử lý cấu hình, post-processors, phát event, lifecycle và các việc khác; không thể lấy nó bằng tổng thời gian constructor.

Một bean `@Lazy` có thể không được tạo trong startup. Nếu một runner hoặc listener yêu cầu bean đó lần đầu, **chi phí tạo bean xuất hiện trong thời gian runner/listener**. Do vậy, phải đo theo cả hai chiều: **giai đoạn thực thi** và **công việc bên trong giai đoạn**.

### Ví dụ về chi phí lồng nhau

~~~text
Tạo bean reportService (180 ms)
  -> tạo dependency templateEngine (120 ms)
  -> chạy constructor reportService (30 ms)
  -> @PostConstruct reportService (30 ms)
~~~

Các con số chỉ là minh họa. **Không cộng 180 + 120 + 30 + 30 rồi kết luận 360 ms**, vì `180 ms` có thể đã gồm các khoảng con. Nếu dùng bước trace cha/con từ Spring, chú ý `parentId` và cửa sổ thời gian để tránh tính trùng.

## 3. Runner: đã qua refresh nhưng chưa ready

Spring Boot cho phép đăng ký các bean:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

và:

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Đây là các **chữ ký rút gọn** của API; chúng không phải mã cần định nghĩa lại trong ứng dụng.

- `ApplicationRunner` dùng `ApplicationArguments` đã được phân tích option/non-option.
- `CommandLineRunner` nhận đối số thô kiểu `String...`.
- Cả hai được Spring Boot gọi **sau `ApplicationStartedEvent`** và **trước `ApplicationReadyEvent`**.
- Nếu có nhiều runners và thứ tự quan trọng, dùng `Ordered` hoặc `@Order`.
- Nếu một runner chờ kết nối mạng, đọc file lớn hoặc warm-up cache, thời gian đó có thể làm **time to ready** tăng.
- Nếu runner ném exception làm startup fail, `ApplicationReadyEvent` không xuất hiện trên đường khởi động thành công.

**Không nên chuyển tác vụ khởi động bắt buộc sang thread nền chỉ để log ready nhanh hơn**. Nếu ứng dụng cần dữ liệu ấy trước khi phục vụ, việc báo ready trước khi hoàn tất sẽ là một lỗi vận hành, không phải tối ưu.

### Thời gian khởi tạo bean của runner khác thời gian chạy runner

Một bean triển khai `ApplicationRunner` vẫn là bean Spring. Constructor, injection, `@PostConstruct` của runner có thể xảy ra **trong refresh**, còn method `run(...)` được gọi **sau started**. Vì vậy, khi nói “runner mất 400 ms”, cần làm rõ đang đo:

1. Tạo **bean runner**: constructor/injection/init.
2. **Body của `run()`**: tác vụ chạy sau started.
3. Tổng ảnh hưởng của runner lên mốc ready, có thể gồm việc runner yêu cầu thêm các bean lazy.

Không gộp cả ba rồi gọi một chỉ số duy nhất khi chưa định nghĩa.

## 4. Listener: phải biết event được phát ở mốc nào

| Event | Thời điểm chính | Nếu listener làm việc lâu |
| --- | --- | --- |
| `ApplicationStartingEvent` | Rất sớm, trước context | Có thể làm chậm gần như toàn bộ bootstrap; không thể chỉ đăng ký qua bean |
| `ApplicationEnvironmentPreparedEvent` | Sau khi chuẩn bị Environment, trước context | Có thể làm chậm bootstrap |
| `ApplicationPreparedEvent` | Sau tải bean definitions, trước refresh | Có thể trì hoãn bước refresh |
| `ContextRefreshedEvent` | Cuối quá trình refresh context | Có thể làm tăng đoạn refresh/context setup |
| `ApplicationStartedEvent` | Sau refresh, trước runner | Có thể kéo dài khoảng started → runner |
| `ApplicationReadyEvent` | Sau runners | Có thể kéo dài từ lúc event được phát đến lúc `run()` trả về |
| `AvailabilityChangeEvent` | Khi liveness/readiness được công bố | Listener thường chạy theo cơ chế publish sự kiện trong context |

Theo tài liệu Spring Boot 3.3, **listeners mặc định chạy trong cùng thread xử lý sự kiện**. Vì vậy, một listener đồng bộ gọi API mất 5 giây có thể làm chậm bước tiếp theo 5 giây.

**Không áp dụng mù quáng kết luận “listeners luôn đồng bộ”.** Spring event multicaster có thể được cấu hình executor bất đồng bộ trong một số trường hợp, và có listener không hỗ trợ async execution. Khi đó, thứ tự callback và độ trễ cần đo tại cả nơi publish và nơi xử lý thực tế.

### Hai cách đăng ký listener

**Đăng ký sớm**, trước `run`, phù hợp để đo các mốc rất sớm:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationStartedEvent>) event ->
                System.out.println("started"));
app.run(args);
~~~

Đoạn trên là fragment, cần class cấu hình và import. Listener nằm trong danh sách mà Spring Boot đăng ký từ trước bootstrap.

**Listener là bean** cho các event sau khi context tồn tại:

~~~java
@Component
public class ReadyLogger {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("ready");
    }
}
~~~

Đây là class minh họa, cần import `@Component`, `@EventListener` và event tương ứng.

Đừng dùng một bean `@Component` để bắt `ApplicationStartingEvent` rồi kết luận “không thấy sự kiện nên event không tồn tại”: bean chưa được tạo ở mốc đó.

## 5. Ba loại số đo và cách hiểu đúng

### A. Đồng hồ đo toàn startup

`System.nanoTime()` cung cấp đồng hồ đơn điệu để tính **khoảng thời gian** trong một tiến trình:

~~~java
long t0 = System.nanoTime();
// work
long durationNanos = System.nanoTime() - t0;
double durationMillis = durationNanos / 1_000_000.0;
~~~

Đoạn trên là fragment trong method Java. Dùng `nanoTime` để tính delta; **không diễn giải giá trị tuyệt đối như thời điểm lịch UTC**. Muốn gắn timestamp tuyệt đối cho dashboard, có thể ghi `Instant.now()` bên cạnh, nhưng không dùng `currentTimeMillis` để tính khoảng ngắn khi đồng hồ hệ thống có thể điều chỉnh.

### B. Thời gian Boot công bố tại event

Spring Boot 3.3 cung cấp:

~~~java
Duration started = startedEvent.getTimeTaken();
Duration ready = readyEvent.getTimeTaken();
~~~

Các method `getTimeTaken()` có thể trả **`null` nếu không xác định**. Chúng mô tả thời gian theo mốc vòng đời Spring Boot, không phải “thời gian của chính listener đang chạy”.

**Quan trọng:** giá trị `timeTaken` được chuẩn bị để đưa vào event; một listener chậm thực thi **bên trong việc phát chính event đó** không nhất thiết đã nằm trong `getTimeTaken()` của event đang nhận. Để đo **listener**, phải đặt đồng hồ ở **đầu và cuối callback**.

### C. Thời gian đo trực tiếp từng đoạn

Một mẫu wrapper:

~~~java
long start = System.nanoTime();
try {
    doWork();
} finally {
    double millis = (System.nanoTime() - start) / 1_000_000.0;
    System.out.printf("work took %.3f ms%n", millis);
}
~~~

Đây là fragment, giả định `doWork()` tồn tại. Dùng `finally` để vẫn ghi thời gian khi công việc ném exception, nhưng đừng nuốt exception hoặc đánh dấu tác vụ thành công nếu nó đã fail.

**Không được phép cộng vô điều kiện** các số đo khác nguồn: timestamp relative to JVM start, event `timeTaken`, per-bean duration và per-runner duration có thể dùng **mốc bắt đầu khác nhau**, chứa khoảng lồng nhau, hoặc bị overhead của instrumentation.

## 6. Mô hình “cộng chi phí” đúng: theo timeline không chồng lấn

Giả sử trên cùng đồng hồ đơn điệu có các mốc:

~~~text
t0: trước SpringApplication.run
t1: ContextRefreshedEvent đã được publish
t2: ApplicationStartedEvent được publish
t3: started listeners hoàn tất
t4: ApplicationRunner/CommandLineRunner hoàn tất
t5: ApplicationReadyEvent được publish
t6: ready listeners hoàn tất
t7: SpringApplication.run trả về
~~~

Các hiệu thời gian:

| Khoảng | Điều được đo | Có thể gồm những gì |
| --- | --- | --- |
| `t2 - t0` | Thời gian tới started | bootstrap, refresh, bean creation, context-refreshed listener |
| `t3 - t2` | Xử lý started listeners | callback, event infrastructure |
| `t4 - t3` | Khối runner và sự kiện/overhead giữa các mốc | body các runners, bean lazy lần đầu dùng |
| `t5 - t4` | Phần còn lại trước ready | overhead sau runners, event publishing |
| `t6 - t5` | Ready listeners | callback, event infrastructure |
| `t7 - t6` | Phần còn lại trước khi run trả về | readiness notification và overhead khác |

Bảng này là **mô hình**, cần đặt instrument đúng các mốc nếu muốn tính chính xác. Các `ApplicationStartedEvent`/`ApplicationReadyEvent` callbacks được gọi **trong** quá trình publish sự kiện, nên một marker “listener enter” không tự là thời điểm event bắt đầu được publish, và “listener exit” không chắc là khi **mọi listener** đã xong.

Để phân tích định lượng:

- Lấy `ApplicationStartedEvent.getTimeTaken()` và `ApplicationReadyEvent.getTimeTaken()` làm **hai mốc Spring Boot có cùng hệ quy chiếu**.
- Đo **riêng** mỗi runner và listener bằng `nanoTime`.
- Xem startup steps với `ApplicationStartup` để tìm beans và các pha refresh.
- Kiểm tra các khoảng chưa được gán, thay vì ép tổng các thành phần bằng đúng `ready time`.

**Ví dụ số giả định:** Boot started `1200 ms`, ready `1850 ms`; hai runners đo `250 ms` và `180 ms`, một started listener đo `100 ms`. Không suy ra khoảng chênh `650 ms` *chỉ* là runner. Những công việc khác giữa hai event, overhead đo và bean lazy phát sinh cũng có thể chiếm phần còn lại.

## 7. Dự án hoàn chỉnh Java 17: nhìn thấy bean, runner và listener trên một timeline

Ta tạo một ứng dụng **console Spring Boot 3.3.13**, không dùng web server, có các mốc dễ quan sát:

1. `@Bean` tạo một `ProbeBean` có constructor chờ nhân tạo.
2. `@PostConstruct` của bean đó thực hiện chờ nhân tạo riêng.
3. `ContextRefreshedEvent` listener có thời gian xử lý giả lập.
4. Listener `ApplicationStartedEvent` đăng ký trước `run` có thời gian xử lý giả lập.
5. `ApplicationRunner` và `CommandLineRunner` có thứ tự xác định qua `Ordered` và thời gian riêng.
6. Listener `ApplicationReadyEvent` có thời gian xử lý giả lập.
7. `main` đo tổng thời gian từ trước tới sau `run()`.
8. `BufferingApplicationStartup` thu thập startup steps để phân tích bổ sung.

**Các lệnh chờ chỉ nhằm minh họa mốc thời gian.** Chúng không đại diện workload production; không dùng `Thread.sleep` để tối ưu ứng dụng thật.

### 7.1. Cấu trúc dự án

~~~text
startup-phases-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startup/
    └── StartupPhasesApplication.java
~~~

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'startup-phases-demo'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Dùng Gradle native BOM để quản lý phiên bản dependency.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

Với Spring Boot Gradle plugin, nên có dependency management tương thích (ở đây là `platform(BOM_COORDINATES)`) khi khai báo starter không có version. Cần Gradle phù hợp với Spring Boot 3.3 và JDK 17+. **Dự án chỉ có starter cơ bản nên không mở HTTP endpoint**.

### 7.4. `StartupPhasesApplication.java`

~~~java
package com.example.startup;

import java.time.Duration;
import java.util.Locale;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class StartupPhasesApplication {

    // Dùng duy nhất một đồng hồ trong JVM để so sánh mốc tương đối.
    private static final long T0 = System.nanoTime();

    public static void main(String[] args) {
        mark("MAIN before SpringApplication.run");

        SpringApplication app =
                new SpringApplication(StartupPhasesApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));

        // Listener được đăng ký trước run. Chỉ log mốc thật
        // khi callback được gọi; không suy ra đây là toàn bộ thời gian event.
        app.addListeners((ApplicationListener<ApplicationStartedEvent>) event -> {
            mark("EVENT ApplicationStartedEvent bootTime="
                    + bootTime(event.getTimeTaken()));
            timed("LISTENER started", 90);
        });

        app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
            mark("EVENT ApplicationReadyEvent bootTime="
                    + bootTime(event.getTimeTaken()));
            timed("LISTENER ready", 60);
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            mark("MAIN after SpringApplication.run");
        }

        mark("MAIN after context.close");
    }

    @Bean
    ProbeBean probeBean() {
        mark("BEAN factory ENTER");
        ProbeBean bean = new ProbeBean();
        mark("BEAN factory EXIT");
        return bean;
    }

    @Bean
    ApplicationRunner applicationRunner(ProbeBean probe) {
        return new FirstRunner(probe);
    }

    @Bean
    CommandLineRunner commandLineRunner() {
        return new SecondRunner();
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        timed("LISTENER ContextRefreshedEvent", 50);
    }

    static final class ProbeBean {
        volatile boolean initialized;

        ProbeBean() {
            timed("BEAN constructor", 120);
        }

        @PostConstruct
        public void init() {
            timed("BEAN @PostConstruct", 70);
            initialized = true;
        }
    }

    static final class FirstRunner implements ApplicationRunner, Ordered {
        private final ProbeBean bean;

        FirstRunner(ProbeBean bean) {
            this.bean = bean;
        }

        @Override
        public int getOrder() {
            return 1;
        }

        @Override
        public void run(ApplicationArguments args) {
            if (!bean.initialized) {
                throw new IllegalStateException("Bean initialization incomplete");
            }
            timed("RUNNER ApplicationRunner", 150);
        }
    }

    static final class SecondRunner implements CommandLineRunner, Ordered {
        @Override
        public int getOrder() {
            return 2;
        }

        @Override
        public void run(String... args) {
            timed("RUNNER CommandLineRunner", 80);
        }
    }

    private static void timed(String label, long sleepMillis) {
        long started = System.nanoTime();
        mark(label + " ENTER");
        try {
            Thread.sleep(sleepMillis);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted in demo timing", ex);
        }
        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
        mark(String.format(Locale.ROOT,
                "%s EXIT duration=%.3fms", label, elapsedMs));
    }

    private static String bootTime(Duration duration) {
        return duration == null ? "unknown"
                : duration.toMillis() + "ms";
    }

    private static void mark(String label) {
        double relativeMs = (System.nanoTime() - T0) / 1_000_000.0;
        System.out.printf(Locale.ROOT, "TRACE +%9.3fms %s%n",
                relativeMs, label);
    }
}
~~~

**Đây là một file Java hoàn chỉnh** khi đặt ở đúng package/đường dẫn, với Gradle dependency đã nêu. Để dễ đối chiếu, app cố ý dùng một JVM, một context, một bean minh họa, hai runners và hai Spring Boot event listeners được đăng ký sớm.

### 7.5. Phân tích code theo các nguồn độ trễ

| Vị trí trong code | Phần đo được | Mốc liên quan |
| --- | --- | --- |
| `probeBean()` | Khoảng vào/ra factory method `@Bean` | Trong tạo bean, thường trước refresh xong |
| `ProbeBean()` | Constructor với chờ mô phỏng `120 ms` | Nằm trong factory method, **không cộng độc lập** |
| `ProbeBean.init()` | `@PostConstruct` chờ `70 ms` | Sau constructor, trong bean init |
| `onContextRefreshed(...)` | Listener chờ `50 ms` | Cuối refresh; trước `ApplicationStartedEvent` |
| `ApplicationStartedEvent` listener | Chờ `90 ms` | Sau refresh, trước các runners |
| `FirstRunner.run(...)` | Chờ `150 ms` | Sau started |
| `SecondRunner.run(...)` | Chờ `80 ms` | Sau runner trước đó do `Ordered` |
| `ApplicationReadyEvent` listener | Chờ `60 ms` | Sau runners |
| `MAIN after SpringApplication.run` | Mốc sau khi ready event và xử lý còn lại | Không trùng mốc chính xác với việc publish ready |
| `MAIN after context.close` | Đoạn đóng context | **Không tính vào thời gian startup** |

**Không cộng hai lần chi phí constructor:** `BEAN factory ENTER→EXIT` đã bao gồm constructor `120 ms`. Nếu lại cộng `BEAN constructor 120 ms` với `BEAN factory ~120 ms` sẽ đếm cùng một phần công việc hai lần. `@PostConstruct` xảy ra sau factory method, nên là đoạn riêng, nhưng toàn bộ `spring.beans.instantiate` có thể bao gồm cả hai.

### 7.6. Build và chạy

Với Gradle Wrapper tương thích:

~~~bash
./gradlew clean bootJar
java -jar build/libs/startup-phases-demo-1.0.0.jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java -jar .\build\libs\startup-phases-demo-1.0.0.jar
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle clean bootJar
java -jar build/libs/startup-phases-demo-1.0.0.jar
~~~

Tên JAR `startup-phases-demo-1.0.0.jar` là theo tên project và version mẫu; nếu chỉnh classifier hoặc plugin output, dùng file build thực tế.

### 7.7. Kết quả kỳ vọng về thứ tự, không phải con số cố định

Các dòng chính có tiền tố `TRACE` xuất hiện theo thứ tự nhóm tương tự:

~~~text
TRACE +...ms MAIN before SpringApplication.run
TRACE +...ms BEAN factory ENTER
TRACE +...ms BEAN constructor ENTER
TRACE +...ms BEAN constructor EXIT duration=...ms
TRACE +...ms BEAN factory EXIT
TRACE +...ms BEAN @PostConstruct ENTER
TRACE +...ms BEAN @PostConstruct EXIT duration=...ms
TRACE +...ms LISTENER ContextRefreshedEvent ENTER
TRACE +...ms LISTENER ContextRefreshedEvent EXIT duration=...ms
TRACE +...ms EVENT ApplicationStartedEvent bootTime=...ms
TRACE +...ms LISTENER started ENTER
TRACE +...ms LISTENER started EXIT duration=...ms
TRACE +...ms RUNNER ApplicationRunner ENTER
TRACE +...ms RUNNER ApplicationRunner EXIT duration=...ms
TRACE +...ms RUNNER CommandLineRunner ENTER
TRACE +...ms RUNNER CommandLineRunner EXIT duration=...ms
TRACE +...ms EVENT ApplicationReadyEvent bootTime=...ms
TRACE +...ms LISTENER ready ENTER
TRACE +...ms LISTENER ready EXIT duration=...ms
TRACE +...ms MAIN after SpringApplication.run
TRACE +...ms MAIN after context.close
~~~

**`...` trong khối trên là vị trí giữ chỗ mô tả cho số đo thực tế**, không phải stdout literal được cam kết. Mọi số mili-giây phụ thuộc JVM, máy, Gradle/JAR launcher, class loading, GC và scheduling. Chỉ nên kỳ vọng **quan hệ trước–sau của các mốc** và các khối sleep có thời lượng xấp xỉ, không phải chính xác `120.000 ms` hay `90.000 ms`.

Một số log Spring Boot khác có thể xuất hiện. Nếu cấu hình đa context, multicaster tùy biến hoặc runner có cùng order, thứ tự có thể thay đổi; bài demo là một context, hai runners với `Ordered` khác nhau.

### 7.8. Vì sao `ApplicationStartedEvent.getTimeTaken()` và marker tương đối khác nhau?

- `getTimeTaken()` do Spring Boot tính trên mốc bên trong `SpringApplication.run`.
- Marker `TRACE` tính từ `T0` của class ứng dụng, có thể được ghi trước Boot timer và gồm overhead riêng.
- Listener `ApplicationStartedEvent` được gọi sau khi event đã được tạo; thời gian nó đang xử lý **không được tự xem là thời gian sự kiện đã ghi tại điểm bắt đầu listener**.
- Listener `ApplicationReadyEvent` cũng có chi phí xử lý riêng; số `ready` trả về từ event không mặc nhiên bằng số `TRACE` ở `MAIN after run`.

Do đó, chỉ so sánh tương đối và ghi rõ nguồn đồng hồ. **Không lấy `TRACE +...ms` trừ thẳng `event.getTimeTaken()` để công bố thời gian “Framework overhead” chính xác** nếu chưa thống nhất điểm bắt đầu và quy tắc làm tròn.

### 7.9. Nếu muốn kiểm tra bằng unit/integration test

Có thể thêm `spring-boot-starter-test` và viết test xác minh **thứ tự logic** của các mốc. Nhưng `@SpringBootTest` không mặc nhiên thực hiện đúng đoạn `main` tự cài `BufferingApplicationStartup` hay hai `app.addListeners(...)`; test context có bootstrap riêng. Đối với phép đo và sự kiện đã đăng ký trong `main`, **chạy executable JAR** là cách trực tiếp nhất.

Một smoke test shell có thể lọc các marker quan trọng:

~~~bash
java -jar build/libs/startup-phases-demo-1.0.0.jar > run.log 2>&1
grep '^TRACE' run.log
~~~

Với bản demo này, các marker phản ánh thứ tự các giai đoạn. Không kiểm tra time tới từng mili-giây bằng assertion cứng vì nhiễu hệ điều hành/JVM sẽ làm test thiếu ổn định.

## 8. Đọc startup steps bằng `ApplicationStartup`

Thay vì tự đặt timer cho từng bean, Spring Framework cung cấp `org.springframework.core.metrics.ApplicationStartup` và `StartupStep` để theo dõi các bước đã được instrument. Spring Boot cung cấp `BufferingApplicationStartup` và có thể expose kết quả qua Actuator.

Ví dụ cấu hình đã có trong `main` của bài tập:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

Đây là đoạn minh họa cho một `MyApplication`, không phải fragment cần thêm lần nữa vào `main` đã chạy.

**Ý nghĩa:** các phần được Spring instrument sẽ tạo bước như:

~~~text
spring.context.refresh
spring.beans.instantiate
spring.context.bean-factory.post-process
spring.context.beans.post-process
~~~

Đây là **tên step tiêu biểu** trong Spring Framework; danh sách và tag có thể thay đổi theo version/chi tiết triển khai. `spring.beans.instantiate` thường có tag `beanName`, có thể có dữ liệu về bean type. **Không coi tên step là API ổn định để hardcode trong production qua nhiều phiên bản Spring.**

### Phân biệt startup step với marker thủ công

| Loại | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `spring.beans.instantiate` | Đo các bước tạo bean qua instrumentation framework | Khoảng có thể lồng dependency; không phải chỉ constructor |
| `spring.context.refresh` | Nhìn tổng giai đoạn refresh | Gồm nhiều việc, không phải tổng constructor |
| `@PostConstruct` timer tự đặt | Biết chính xác callback init của bean mình | Không đo việc inject dependency trước callback |
| Runner timer | Đo đúng body `run(...)` | Không tự tách hết các call bên trong runner |
| Listener timer | Đo callback event thật | Có thể không phản ánh tổng thời gian publish event |
| JFR/CPU profiler | Tìm chỗ allocation, CPU, GC, class loading | Cần công cụ/chi phí đo và phân tích |

**Khi startup step lồng nhau**, hãy xem `parentId` hoặc thời gian bắt đầu/kết thúc. Không nên lấy mọi `duration` rồi cộng lại để “tổng thời gian Spring”, vì cha có thể bao gồm con.

### Tại sao không chỉ dùng `BeanPostProcessor` để đo bean?

`BeanPostProcessor.postProcessBeforeInitialization(...)` và `postProcessAfterInitialization(...)` được gọi **sau giai đoạn tạo instance/điền dependency**, theo chuỗi xử lý init. Nếu đặt timer chỉ giữa hai callback này, bạn **không đo toàn bộ constructor và dependency injection**. Với auto-proxy, vòng đời bean và nhiều post-processors khác, việc quy trách nhiệm càng phức tạp.

Nếu mục tiêu là **tổng chi phí tạo bean**, ưu tiên Spring `ApplicationStartup` và profiling phù hợp, rồi bổ sung timer **bên trong constructor/factory/init** khi cần xác định điểm nóng cụ thể. Không dùng một `BeanPostProcessor` tự viết như phép đo toàn bộ creation mà không chỉ rõ phạm vi.

## 9. Endpoint `/actuator/startup`: cách xem bean creation khi app web chạy

**Lưu ý:** demo `WebApplicationType.NONE` ở phần 7 là ứng dụng CLI, **không có HTTP port**, nên **không thể dùng `curl /actuator/startup` ngay trên demo đó**.

Nếu có **ứng dụng web** Spring Boot 3.3 (ví dụ thêm starter web và dùng servlet web type), thêm Actuator:

~~~groovy
dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là **fragment cấu hình thay thế/điều chỉnh** trong file Gradle thực tế; không thêm một block `dependencies` thứ hai nếu chưa ghép đúng vào build hiện có. Để dùng endpoint HTTP, không đặt `WebApplicationType.NONE` và phải có server được khởi chạy.

Bật endpoint ở môi trường test:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

Sau khi web server khởi động:

~~~bash
curl -sS http://localhost:8080/actuator/startup
~~~

Theo tài liệu Spring Boot 3.3.13, **GET** lấy bản snapshot các startup steps; **POST** dùng để drain buffer. Không dùng POST trong lúc muốn giữ số liệu để điều tra hoặc chụp nhiều lần.

### Dữ liệu tiêu biểu của endpoint

Ví dụ rút gọn, chỉ minh họa cấu trúc JSON:

~~~json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19Z",
        "endTime": "2025-06-19T07:16:20Z",
        "duration": "PT0.1S",
        "startupStep": {
          "id": 3,
          "name": "spring.beans.instantiate",
          "parentId": 2,
          "tags": [{"key": "beanName", "value": "probeBean"}]
        }
      }
    ]
  }
}
~~~

**Đây là JSON minh họa cấu trúc, không phải một response được lấy từ dự án mẫu.** Trong thực tế start/end timestamps, durations, IDs và tags phụ thuộc tiến trình; các mốc ví dụ không nhằm khẳng định duration đúng với hiệu timestamp đã làm tròn.

Mỗi event có thể mang:

- `startTime` và `endTime`: thời điểm tuyệt đối của step.
- `duration`: khoảng thời gian của step theo định dạng ISO-8601 `Duration`.
- `startupStep.name`: tên bước.
- `startupStep.id` và `parentId`: định danh và quan hệ cha/con.
- `startupStep.tags`: key/value bổ sung như `beanName`.

**Không chỉ sort descending theo duration rồi kết luận 10 bean “đắt nhất” có tổng thời gian bằng tổng 10 duration**. Có thể có relationship cha/con và các bước lồng nhau. Khi cần thời gian riêng từng bean, xem stack quan hệ, biểu đồ Gantt hoặc profiler.

### Bảo mật và phạm vi thu thập

Endpoint `startup` hữu ích cho **staging và benchmark**, nhưng không nên expose công khai. Nó có thể tiết lộ tên bean, cấu trúc ứng dụng và metadata; cần bảo vệ bằng network/auth. Buffer có giới hạn; `2048` là kích thước minh họa, không bảo đảm đủ cho mọi dự án lớn. Nếu bị tràn, timeline có thể thiếu bước, vì thế “không thấy bean” **không chứng minh bean chưa được tạo**.

## 10. Khi nào dùng Java Flight Recorder?

`FlightRecorderApplicationStartup` của Spring Framework có thể tích hợp các startup steps vào JFR, giúp đặt thời gian Spring bên cạnh class loading, allocation, garbage collection và CPU events.

Đoạn setup thay thế:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.context.ApplicationStartupAware;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

**Đây là fragment chỉ minh họa cách chọn implementation, không phải một file Java đầy đủ.** Các import của `SpringApplication`, `FlightRecorderApplicationStartup` cần có; `ApplicationStartupAware` không cần dùng trực tiếp trong fragment.

Bật recording khi chạy JAR trên JDK có JFR:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=60s \
     -jar my-app.jar
~~~

Nếu chỉ muốn phân tích vài trăm milliseconds đầu, thiết lập recording đủ dài bao phủ cả startup và những lần warm-up liên quan. JFR có overhead đo đạc; giữ chế độ profiling đồng nhất khi so sánh hai phiên bản.

**JFR không tự tạo thành một “bảng bean/runner/listener” theo ý mình.** Nó cho các events và dữ liệu cần phân tích; kết hợp marker riêng của runner/listener để có câu trả lời chắc chắn.

## 11. Cách đối chiếu mốc started và ready không bị nhầm

Giả sử bạn đo được (số hoàn toàn giả định):

~~~text
ApplicationStartedEvent timeTaken = 1,600 ms
ApplicationReadyEvent   timeTaken = 2,320 ms
Chênh lệch = 720 ms
~~~

Có thể diễn giải rằng khoảng **giữa hai mốc Boot** là `720 ms`, nhưng **không tự động gọi tất cả là “thời gian runner”**. Đo thêm:

~~~text
Started listener A = 100 ms
ApplicationRunner 1 = 280 ms
CommandLineRunner  = 250 ms
Phần còn lại/overhead = 90 ms (ước lượng)
~~~

Đây chỉ là **một phân rã minh họa** với các công việc không chồng lấn. Trong ứng dụng thật, còn listener của liveness event, async work, bean lazy được runner yêu cầu, overhead publish event; cần trace timeline để xác định.

### Quan hệ với `ApplicationReadyEvent` listener

Nếu một `ApplicationReadyEvent` listener chạy 400 ms, event đó được **phát ở mốc ready**. Khi listener đang chạy, `run()` chưa chắc trả về. Do đó:

- `readyEvent.getTimeTaken()` là số đo của Boot tại mốc ready.
- `main-after-run - main-before-run` là thời gian thực thi `run()` nhìn từ caller.
- Khoảng thứ hai có thể lớn hơn khoảng thứ nhất vì chi phí callback ready, readiness event listeners và overhead khác.

**Không nên “tối ưu số liệu” bằng cách bỏ listener chậm mà không hiểu công việc đó có bắt buộc hoàn tất trước khi nhận traffic hay không.** Nếu listener đang làm một việc cần thiết cho readiness, nên chuyển đúng giai đoạn hoặc sửa thiết kế readiness, không đơn giản đẩy công việc chạy nền mà bỏ kiểm chứng.

## 12. Chẩn đoán điểm chậm theo triệu chứng

| Hiện tượng | Phần đáng kiểm tra đầu tiên | Bằng chứng nên lấy |
| --- | --- | --- |
| `T_started` rất lớn, `T_ready - T_started` nhỏ | Refresh/context setup/bean creation/early listeners | Startup steps, JFR, timer factory/constructor/init |
| `T_started` nhỏ, `T_ready - T_started` rất lớn | Started listeners/runners/lazy beans được yêu cầu muộn | Thời gian từng runner và listener, mốc liveness |
| `T_ready` nhỏ nhưng `run()` trả rất muộn | Ready listener/readiness event callbacks hoặc logic sau ready | Timer trong từng callback, marker `main-after-run` |
| Một bean có `@PostConstruct` dài | Bean initialization | Timer trong callback, xem có I/O không |
| Một `@Bean` factory method dài | Factory method/constructor/dependencies | Instrument từng phần, nested startup steps |
| Runner A làm chậm nhiều lần | Blocking remote call, retry, cache warmup, lock | Logs có timeouts, traces và profile |
| Listener `ContextRefreshedEvent` chậm | Listener ở cuối refresh | Timer event callback và bước refresh |
| App web báo ready nhưng request đầu chậm | Lazy bean, connection, class loading, JIT | Cold request latency, constructor logs, trace |
| Tổng các bean durations lớn hơn startup total | Các steps lồng nhau hoặc chạy đồng thời | Quan hệ parent/child, timeline thay vì cộng |
| Test nhanh nhưng JAR chậm | Khác JVM, profile, classpath, environment | Chạy artifact thật với config tương đương |
| `ApplicationReadyEvent` không xuất hiện | Runner/startup exception | `ApplicationFailedEvent`, stack trace, failure analysis |
| Mỗi lần khởi động biến động mạnh | GC/JIT/CPU contention/network/cache | Lặp nhiều run, JFR, OS metrics |

Một kết luận tốt phải chỉ ra **đường chứng cứ**, không chỉ “bean X làm chậm”. Ví dụ: “`@PostConstruct` của bean X chiếm khoảng 300 ms trong 10 lần chạy, nằm trước ContextRefreshedEvent; sau khi bỏ I/O không cần thiết, median T_started giảm tương ứng trong cùng điều kiện benchmark”.

## 13. Trường hợp đặc biệt: listener tạo bean hoặc chạy tác vụ

Listener không nhất thiết chỉ log. Một `ContextRefreshedEvent` listener có thể gọi `applicationContext.getBean(...)`, hoặc một `ApplicationStartedEvent` listener có thể gọi một service lazy. Khi đó, **chi phí tạo bean nằm bên trong listener**.

Ví dụ minh họa:

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    expensiveService.initializeIfNeeded();
}
~~~

Đoạn trên nằm trong Spring-managed bean, giả định `expensiveService` đã được inject. Nếu inject trực tiếp một bean non-lazy, phần tạo bean có thể xảy ra trước event; nếu dùng `ObjectProvider` và gọi `getObject()` trong listener, việc tạo bean có thể xảy ra ngay trong callback.

**Đừng cộng “listener 500 ms” + “bean 300 ms” khi bean là công việc con của listener**. Cần nói rõ:

~~~text
Started listener total = 500 ms
   -> getBean(lazyService) = 300 ms
   -> initialize cache   = 180 ms
   -> overhead          ~= 20 ms
~~~

Ở đây `500 ms` đã bao gồm `300 + 180 + overhead`.

Tương tự, nếu một runner gọi API có listener/event publishing lồng nhau, thời gian listener đó có thể đã nằm trong runner timer. Cộng thêm lần nữa sẽ phóng đại tổng.

## 14. Trường hợp đặc biệt: async listener và task nền

Nếu một listener khởi tạo tác vụ bất đồng bộ rồi **trả về ngay**, thời gian callback có thể nhỏ nhưng **công việc thật chưa hoàn thành**. Có hai chỉ số khác nhau:

1. **Thời gian enqueue/schedule task:** lúc listener trả về.
2. **Thời gian task chạy xong:** gồm chờ queue, thread scheduling và I/O.

Ví dụ:

~~~java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    executor.execute(() -> warmCache());
}
~~~

Đây là fragment minh họa cần `executor` và `warmCache()` có sẵn. Mốc `run()` có thể không chờ `warmCache()` hoàn thành. Nếu cache là điều kiện bắt buộc để nhận traffic, đây có thể là **readiness bug**.

Khi một job là điều kiện trước traffic:

- Chạy nó trong runner và chờ hoàn tất có timeout.
- Hoặc thiết kế readiness giữ `REFUSING_TRAFFIC` cho đến khi hoàn tất điều kiện thật, với cơ chế phát `AvailabilityChangeEvent` đúng chỗ.
- Đảm bảo startup failure hoặc timeout được báo rõ thay vì “tự thành công” do task bị bỏ dở.

Không lấy “runner async làm startup nhanh” làm kết luận hiệu năng nếu cold request của người dùng phải chịu công việc còn lại.

## 15. Lazy initialization làm thay đổi vị trí chi phí

Khi bật:

~~~properties
spring.main.lazy-initialization=true
~~~

nhiều bean có thể bị trì hoãn. Vì vậy, bảng phân bổ thời gian có thể thay đổi:

~~~text
EAGER:
  Bean creation nhiều hơn trước StartedEvent
  Runner ít phải tạo bean mới
  Ready có thể đến muộn nhưng request đầu ít cold work

LAZY:
  StartedEvent có thể đến sớm hơn
  Runner nếu getBean(...) vẫn trả chi phí tạo bean
  Listener nếu getBean(...) có thể trả chi phí tạo bean
  Request đầu nếu cần bean chưa tạo sẽ trả chi phí còn lại
~~~

**Không so sánh T_started của eager và lazy rồi kết luận startup end-to-end đã tốt hơn**. Cần đo cả `T_ready`, external readiness và cold first request, kiểm tra lỗi cấu hình bị trì hoãn.

Từ đó ta có thể giải thích vì sao một bean nặng “biến mất” khỏi startup steps: có thể nó thật sự được tối ưu, nhưng cũng có thể chỉ được chuyển sang thời điểm khác.

## 16. Cách đo đối chứng A/B thật

Để đối chiếu một thay đổi làm nhanh startup:

1. Đóng băng **JAR/image**, JDK, JVM flags, profile, tài nguyên và dependencies ngoài.
2. Ghi rõ **mốc bắt đầu/mốc kết thúc** cho từng chỉ số.
3. Chạy nhiều lần với **mỗi lần một JVM mới**, không dùng lần gọi lại `run()` trong một context cũ làm baseline lạnh.
4. Luân phiên thứ tự các biến thể hoặc thay đổi có kiểm soát, tránh xu hướng CPU/cache theo thời gian.
5. Ghi đầy đủ giá trị `ApplicationStartedEvent.getTimeTaken()`, `ApplicationReadyEvent.getTimeTaken()` và marker của bean/runner/listener.
6. Thu timeline `BufferingApplicationStartup`/JFR để phân tích các bước có chi phí lớn.
7. Dùng median và biến thiên; không kết luận từ một lần chạy may mắn.
8. Đo external probe nếu mục tiêu thực tế là **Kubernetes ready**.
9. Nếu thay bean initialization, kiểm tra lỗi bị phát hiện muộn và memory sau warm-up.
10. Nếu thay listener hoặc runner, xác nhận chức năng cần có trước ready vẫn chạy đủ.

Ví dụ bảng thí nghiệm:

| Run | T_started | T_ready | FirstRunner body | SecondRunner body | Started listener | Ready listener |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Đo | Đo | Đo | Đo | Đo | Đo |
| 2 | Đo | Đo | Đo | Đo | Đo | Đo |
| ... | ... | ... | ... | ... | ... | ... |
| N | Median | Median | Median | Median | Median | Median |

Chú ý: **mỗi cột chỉ một phạm vi đo**, không cộng toàn bộ cột lại. Nếu một callback có công việc lồng nhau, phải gắn quan hệ cha–con trong trace để phân bổ đúng.

## 17. Quy trình phân tích một hệ thống thật

### Bước 1 — Xác định vấn đề

Ví dụ: “Pod cần 25 giây mới sẵn sàng” là vấn đề **external ready**, không chắc toàn bộ do tạo bean. Xem thêm image pull, scheduling, container startup, health probe interval và thời gian Spring Boot.

### Bước 2 — Đo hai event chính

Log `ApplicationStartedEvent.getTimeTaken()` và `ApplicationReadyEvent.getTimeTaken()`. Nếu có bất thường, xác định bất thường chủ yếu **trước started** hay **giữa started và ready**.

### Bước 3 — Thu startup steps

Bật `BufferingApplicationStartup` hoặc JFR trong một đợt thử có kiểm soát. Dò các `spring.beans.instantiate` và bước `spring.context.refresh`; xem nested steps/tags.

### Bước 4 — Gắn timer vào runners và listeners

Thêm wrapper `nanoTime` ở đầu/cuối mỗi `run(...)` và event callback. Ghi event class, bean name, thread, elapsed và duration. Không ghi secrets trong log đo.

### Bước 5 — Khoanh vùng bean

Nếu một bean có step dài, tách constructor, factory, dependency resolution và callback init. Với beans của thư viện không sửa được, dùng tracing/JFR để xác định allocation/I/O.

### Bước 6 — Thử tối ưu có kiểm chứng

Ví dụ:

- Bỏ network call không cần thiết khỏi constructor/`@PostConstruct`.
- Chuyển công việc bắt buộc sau refresh vào runner nếu hợp đồng cho phép, nhưng **không gọi việc dời chi phí là tăng tốc đến ready**.
- Giảm timeout/retry vô ích trong runner, tối ưu batch I/O.
- Rút ngắn listener đồng bộ; nếu task không bắt buộc để ready, đưa về giai đoạn thích hợp và thiết kế giám sát.
- Cân nhắc lazy có chọn lọc cho bean hiếm dùng, nhưng kiểm thử cold path và fail fast.

### Bước 7 — Đo lại và kết luận

Chạy cùng bài test A/B, so median/độ phân tán, xác nhận logic nghiệp vụ và readiness. Chỉ tuyên bố cải thiện nếu metric mục tiêu thực sự đổi, không dựa trên việc một thanh timeline biến mất do công việc bị chuyển chỗ.

## 18. Checklist các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Xem log `Started` là ready | Started trước runners | Log cả Started và Ready |
| Cộng `spring.beans.instantiate` cha và con | Đếm trùng thời gian | Xem `parentId`/timeline |
| Chỉ đo constructor và gọi đó là bean creation | Bỏ qua injection/init/proxy/dependency | Dùng `ApplicationStartup` và timer chi tiết |
| Dùng BeanPostProcessor sau init để đo toàn bean | Constructor đã xảy ra trước callback | Làm rõ phạm vi hoặc dùng startup steps |
| Cho rằng runner bean được tạo lúc `run()` | Constructor bean thường có thể ở refresh | Đo riêng bean init và body runner |
| Listener `ContextRefreshedEvent` bị quên | Có thể làm chậm cuối refresh | Timer callback event |
| `@EventListener` bắt sự kiện rất sớm | Bean chưa tồn tại | Đăng ký sớm qua `addListeners`/`spring.factories` |
| Đo toàn `ApplicationReadyEvent` bằng getTimeTaken | Không phải duration của chính listener | Đặt timer vào listener |
| Thấy runner nhanh nên không có việc sau started | Còn started listener, lazy bean, overhead | Đo timeline đầy đủ |
| Chạy 1 lần rồi so A/B | JIT/cache/CPU/network nhiễu | Nhiều JVM mới, thống kê |
| Đo trên `@SpringBootTest` rồi suy ra production | Test context/launcher khác JAR | Chạy artifact thật |
| Bật lazy làm bean step biến mất | Chi phí bị dời sang lần dùng đầu | Đo cold request và lỗi muộn |
| Đẩy task bắt buộc sang background | Ready báo trước khi hoàn thành | Chờ hoàn tất hoặc readiness gating |
| Dùng `currentTimeMillis()` cho đoạn rất ngắn | Đồng hồ wall-clock có thể điều chỉnh | Dùng `nanoTime()` để đo delta |
| Cộng các timer có concurrency | Sum có thể vượt wall time | Dùng critical path và parent-child trace |
| Bật Actuator startup công khai | Lộ metadata cấu trúc ứng dụng | Giới hạn exposure/auth/network |
| Quên giới hạn buffer | Timeline có thể thiếu bước | Chọn capacity phù hợp, theo dõi số step |
| Listener tự tạo thread và không dọn | Vòng đời ngoài container có thể bị giữ | Quản lý executor và shutdown |
| Runner retry vô hạn | Ready không bao giờ đạt | Đặt timeout và failure policy |
| Không kiểm tra failure path | Ready event có thể không xuất hiện | Theo dõi `ApplicationFailedEvent`, log và exit status |

## 19. Tự kiểm tra kiến thức

1. **`ApplicationStartedEvent` xảy ra trước hay sau runner?** Trước.
2. **`ApplicationReadyEvent` xảy ra trước hay sau runner?** Sau tất cả runners trên đường thành công.
3. **`ContextRefreshedEvent` thường nằm ở đâu?** Cuối refresh, trước `ApplicationStartedEvent`.
4. **Bean runner có thể được tạo trước body `run(...)` không?** Có; bean creation và runner execution là hai mốc khác nhau.
5. **Constructor time có bằng tổng bean creation time không?** Không.
6. **`@PostConstruct` chạy trước hay sau constructor?** Sau constructor và injection phù hợp.
7. **`ApplicationStartedEvent.getTimeTaken()` đo gì?** Thời gian Boot tới mốc started, không phải thời gian listener callback.
8. **`ApplicationReadyEvent.getTimeTaken()` đo gì?** Thời gian Boot tới mốc ready; có thể `null`.
9. **Muốn đo riêng listener thì làm gì?** `System.nanoTime()` ở đầu/cuối callback.
10. **Một listener started chậm có ảnh hưởng runner không?** Có thể, vì callback đồng bộ mặc định chạy trước runners.
11. **Một listener ready chậm có làm `run()` trả về muộn không?** Có thể.
12. **Có nên lấy `T_ready - T_started` gọi luôn là thời gian runner?** Không; còn listener và các công việc khác.
13. **`spring.beans.instantiate` đo riêng constructor hay cả dependency?** Đây là startup step framework có thể gồm dependency/khởi tạo; không coi là constructor riêng.
14. **Vì sao không được cộng các step durations tùy tiện?** Có các khoảng cha/con lồng nhau.
15. **`BeanPostProcessor` có mặc định đo toàn constructor không?** Không, callback sau instantiation không bao trùm toàn constructor.
16. **Demo CLI có gọi được `/actuator/startup` qua HTTP không?** Không khi `WebApplicationType.NONE` và không có web server.
17. **Cách bật startup tracing trong `main`?** `setApplicationStartup(new BufferingApplicationStartup(...))`.
18. **`GET /actuator/startup` khác `POST`?** GET xem snapshot, POST drain buffer.
19. **Dữ liệu startup step có hợp đồng tên ổn định tuyệt đối không?** Không; tên/tag có thể thay theo triển khai/version.
20. **Nếu một listener yêu cầu bean lazy, nên quy thời gian vào đâu?** Vừa mô tả listener bao gồm bean creation, vừa chỉ ra bean step con; không cộng hai lần.
21. **Nếu task nền đang warm cache sau khi app báo ready, có phải startup đã hoàn thành mọi điều kiện nghiệp vụ?** Không nhất thiết.
22. **Để kiểm chứng tối ưu, cần bao nhiêu lần đo?** Nhiều lần trong điều kiện kiểm soát, không có một số cố định cho mọi hệ thống.
23. **Mốc `ApplicationReadyEvent` có giống readiness HTTP của Kubernetes không?** Không hoàn toàn; external probe có độ trễ và hạ tầng riêng.
24. **Nên dùng gì để phân tích allocation/GC bên cạnh startup steps?** JFR/profiler với cùng điều kiện.
25. **Vì sao nên dùng `Ordered` cho runners có phụ thuộc thứ tự?** Tránh dựa vào thứ tự phát hiện bean ngẫu nhiên.

**Kết luận:** Muốn đối chiếu thời gian tạo bean, runner và listener, hãy dùng **hai mốc Boot started/ready** làm bản đồ chung, dùng **`ApplicationStartup`/startup steps** cho bean creation, và **timer `nanoTime` bên trong từng runner/listener** cho body thực thi. **Không nhầm mốc event với thời gian callback, không cộng các khoảng cha–con, không bỏ qua bean lazy và không đo một lần duy nhất.** Một kết luận đáng tin phải chỉ ra **phần nào chậm, chi phí phát sinh ở giai đoạn nào và việc tối ưu có cải thiện thời điểm sẵn sàng thật sự hay chỉ chuyển chi phí sang nơi khác**.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — SpringApplication: **Application Events and Listeners**, **Application Startup tracking**, **ApplicationRunner/CommandLineRunner**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationStartedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3.13 — `ApplicationReadyEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3.13 — Actuator **Application Startup (startup)** REST API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Framework 6.1 — `ApplicationStartup` API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework — Application Startup Steps (bước `spring.beans.instantiate`, tag, tính nội bộ): https://docs.spring.io/spring-framework/reference/core/appendix/application-startup-steps.html
- Spring Framework 6.1 — Core bean lifecycle và `BeanPostProcessor`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Boot 3.3 — Gradle dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
