# ApplicationStartedEvent trong Spring Boot

## 1. Mục tiêu bài học

`ApplicationStartedEvent` thuộc nhóm **Spring Boot application events** và đại diện cho một mốc xác định trong quá trình `SpringApplication.run(...)`: **ApplicationContext đã refresh xong, nhưng các `ApplicationRunner` và `CommandLineRunner` chưa được gọi**.

Tên đầy đủ của kiểu này là `org.springframework.boot.context.event.ApplicationStartedEvent`. Đây là event về **vòng đời ứng dụng Spring Boot**, không phải domain event như `OrderCreated` hoặc `PaymentCompleted`.

Sau bài này, bạn sẽ hiểu:

- Khi nào Spring Boot phát `ApplicationStartedEvent` và vì sao mốc này khác `ApplicationReadyEvent`.
- Cách nhận sự kiện qua `@EventListener` và `ApplicationListener<ApplicationStartedEvent>`.
- Các thuộc tính event như `getApplicationContext()`, `getArgs()` và `getTimeTaken()`.
- Thứ tự với `ContextRefreshedEvent`, các runner và trạng thái liveness/readiness.
- Những vấn đề liên quan tới startup thất bại, listener đồng bộ/bất đồng bộ, nhiều context và kiểm thử.
- Cách chạy một chương trình Java 17+ kiểm chứng thứ tự một cách xác định.

## 2. Vị trí của `ApplicationStartedEvent` trong chu trình startup

Một lần `SpringApplication.run` thông thường đi qua các mốc chính sau:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  |
  +-- refresh ApplicationContext
  |      |
  |      +-- bean definitions, BeanPostProcessors, singleton, lifecycle
  |      +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  +-- SpringApplication.run(...) trả về ApplicationContext
~~~

Đây là sơ đồ tóm tắt những **mốc liên quan**; các bước nội bộ như chuẩn bị environment, cấu hình web server và callback của context có nhiều chi tiết hơn. Ví dụ một `WebServerInitializedEvent` có thể được phát trong quá trình chuẩn bị web server, trước mốc started.

**Những bất biến quan trọng:**

1. `ApplicationStartedEvent` xuất hiện **sau khi context refresh thành công**.
2. Nó xuất hiện **trước khi Boot gọi các application/command-line runner**.
3. `ApplicationReadyEvent` xuất hiện **sau khi các runner chạy xong**.
4. Boot công bố `LivenessState.CORRECT` ngay sau started, còn `ReadinessState.ACCEPTING_TRAFFIC` sau ready. **Live** và **ready** là hai trạng thái khác nhau.

Theo hợp đồng `SpringApplicationRunListener`, phương thức `started(context, timeTaken)` mô tả đúng thời điểm đã refresh nhưng runner chưa được gọi; `ready(context, timeTaken)` được gọi sau runner. Spring Boot phát `ApplicationStartedEvent` qua cơ chế application events để các listener ứng dụng phản ứng với mốc started đó.

### Started không có nghĩa đã sẵn sàng phục vụ mọi yêu cầu

Một ứng dụng có thể đã phát `ApplicationStartedEvent` nhưng tiếp theo vẫn phải chạy runner tải dữ liệu, xác minh khóa mã hóa, chuẩn bị hệ thống tích hợp hoặc các bước khởi tạo khác. Bởi vậy, **không nên dùng started làm tín hiệu duy nhất cho phép nhận traffic**. Spring Boot có khái niệm readiness và health/availability riêng để phối hợp điều này.

Với ứng dụng web, việc web server đã bind một cổng không tự chứng minh mọi nghiệp vụ đã sẵn sàng. Context refresh, server initialized, started, ready và application availability là các mốc/hợp đồng khác nhau.

## 3. Thuộc tính của event

`ApplicationStartedEvent` là subclass của `SpringApplicationEvent` và cung cấp các API hữu ích:

| API | Giá trị và ý nghĩa |
| --- | --- |
| `getApplicationContext()` | `ConfigurableApplicationContext` vừa khởi động; dùng để xác định context nguồn |
| `getSpringApplication()` | Đối tượng `SpringApplication` liên quan tới lần chạy |
| `getArgs()` | Các đối số dạng `String[]` đã được chuyển vào `SpringApplication` |
| `getTimeTaken()` | `Duration` tính tới mốc started, hoặc `null` nếu không xác định |

Ví dụ minh họa cách đọc:

~~~java
// Phương thức của một Spring-managed bean, chưa phải chương trình độc lập.
@EventListener
public void started(ApplicationStartedEvent event) {
    ConfigurableApplicationContext context = event.getApplicationContext();
    Duration elapsed = event.getTimeTaken();

    System.out.println("Context ID = " + context.getId());
    if (elapsed != null) {
        System.out.println("Started after " + elapsed.toMillis() + " ms");
    }
}
~~~

Thời gian khởi động tùy máy và tải hệ thống, không có stdout milliseconds cố định. `getTimeTaken()` không phải thước đo toàn bộ giai đoạn startup đến ready, vì chưa tính các runner chạy sau started. Nếu cần thời gian đến ready, dùng `ApplicationReadyEvent.getTimeTaken()` cùng công cụ đo chi tiết.

## 4. Đăng ký listener bằng `@EventListener`

Vì `ApplicationStartedEvent` được phát **sau** refresh, một Spring-managed bean có thể nhận event bằng `@EventListener`:

~~~java
@Component
public class StartedObserver {
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Boot context started: "
                + event.getApplicationContext().getId());
    }
}
~~~

Đây là đoạn minh họa class cần có các import `@Component`, `@EventListener` và `ApplicationStartedEvent`, được component scan hoặc khai báo thành bean trong ứng dụng thực.

Listener được Spring chọn theo kiểu event. Với multicaster mặc định đồng bộ, method chạy trên thread phát event, trước giai đoạn runner. Không cần tự publish `ApplicationStartedEvent`; Spring Boot phát nó trong quá trình `SpringApplication.run`.

Nếu listener chỉ ghi metric/log hoặc kiểm tra điều kiện ngắn, cách này khá đơn giản. Nếu listener gọi network hoặc chờ rất lâu, nó có thể kéo dài startup hoặc khiến startup thất bại nếu exception không được xử lý.

## 5. Đăng ký bằng `ApplicationListener`

Bạn cũng có thể triển khai `ApplicationListener<ApplicationStartedEvent>`:

~~~java
public final class StartedListener
        implements ApplicationListener<ApplicationStartedEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartedEvent event) {
        System.out.println("Boot started: "
                + event.getApplicationContext().getId());
    }
}
~~~

Đoạn code minh họa trên cần import `org.springframework.context.ApplicationListener` và kiểu sự kiện Boot. Đăng ký `StartedListener` thành một Spring bean, hoặc tạo instance rồi đăng ký trực tiếp bằng `SpringApplication.addListeners(listener)` **trước** khi gọi `run()`.

Ví dụ với đăng ký trực tiếp:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartedListener());
app.run(args);
~~~

Đây là mã minh họa nằm trong main, `MyApplication` cần được định nghĩa. Không đăng ký cùng listener hai lần vô tình, nếu không nó có thể xử lý một event nhiều lần.

### Lưu ý về các event xảy ra sớm hơn

`ApplicationStartingEvent` được phát rất sớm, **trước khi `ApplicationContext` được tạo**. Một listener chỉ tồn tại dưới dạng bean trong context chưa thể nhận những event đã xảy ra trước đó. Để quan sát early startup events, dùng listener đăng ký với `SpringApplication` trước `run()` hoặc cơ chế đăng ký sớm do Boot hỗ trợ.

`ApplicationStartedEvent` khác ở chỗ context đã sẵn sàng, nên bean với `@EventListener` có thể nhận nó.

## 6. Ví dụ Java 17+ độc lập: kiểm chứng thứ tự năm mốc

Chương trình dưới đây dùng **Spring Boot 3.3.13**, Java 17+ và Maven. Không tạo web server, nên việc quan sát tập trung vào startup events.

Ta dùng một bộ đếm `AtomicInteger` để chứng minh:

1. `ContextRefreshedEvent` chạy trước.
2. `ApplicationStartedEvent` chạy sau refresh.
3. `ApplicationRunner` được gọi sau started.
4. `ApplicationReadyEvent` được gọi sau runner.
5. `SpringApplication.run()` trở về main khi các bước trên đã hoàn tất.

Không dùng `Thread.sleep` để đoán thứ tự; mỗi callback kiểm tra chính xác trạng thái trước đó.

Cấu trúc:

~~~text
boot-started-event/
├── pom.xml
└── src/main/java/demo/ApplicationStartedDemo.java
~~~

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>boot-started-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. `src/main/java/demo/ApplicationStartedDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class ApplicationStartedDemo {

    public static final class Progress {
        private final AtomicInteger step = new AtomicInteger();

        public void advance(int expected, int next, String label) {
            if (!step.compareAndSet(expected, next)) {
                throw new IllegalStateException(
                    "Expected " + expected + " but actual " + step.get());
            }
            System.out.println(label);
        }

        public int value() {
            return step.get();
        }
    }

    public static final class StartupEvents {
        private final Progress progress;

        public StartupEvents(Progress progress) {
            this.progress = progress;
        }

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            progress.advance(0, 1, "1 ContextRefreshedEvent");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            progress.advance(1, 2, "2 ApplicationStartedEvent");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            progress.advance(3, 4, "4 ApplicationReadyEvent");
        }
    }

    @Bean
    public Progress progress() {
        return new Progress();
    }

    @Bean
    public StartupEvents startupEvents(Progress progress) {
        return new StartupEvents(progress);
    }

    @Bean
    public ApplicationRunner runner(Progress progress) {
        return new ApplicationRunner() {
            @Override
            public void run(ApplicationArguments args) {
                progress.advance(2, 3, "3 ApplicationRunner");
            }
        };
    }

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ApplicationStartedDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            Progress progress = context.getBean(Progress.class);
            if (progress.value() != 4) {
                throw new AssertionError("Unexpected startup lifecycle");
            }
            System.out.println("5 SpringApplication.run returned");
        }
    }
}
~~~

Tại thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q spring-boot:run
~~~

Năm dòng do chương trình tự in ra (theo đúng thứ tự):

~~~text
1 ContextRefreshedEvent
2 ApplicationStartedEvent
3 ApplicationRunner
4 ApplicationReadyEvent
5 SpringApplication.run returned
~~~

Console cũng có thể có log bổ sung từ Maven/Spring, nhưng thứ tự của **năm dòng do mã ví dụ in** được kiểm tra bằng `Progress.advance`.

### 6.3. Vì sao output đáng tin?

- Phần refresh của `SpringApplication.run` phát `ContextRefreshedEvent`. Bean listener đã được đăng ký trong quá trình khởi tạo context; bộ đếm từ 0 sang 1.
- Spring Boot phát `ApplicationStartedEvent` sau refresh; bộ đếm chuyển từ 1 sang 2.
- `ApplicationRunner` được Boot gọi tiếp theo và chuyển bộ đếm từ 2 sang 3.
- `ApplicationReadyEvent` được phát sau runner và chuyển bộ đếm từ 3 sang 4.
- `SpringApplication.run` trả `ConfigurableApplicationContext`, rồi main đọc bộ đếm 4 và in dòng cuối.

Ở đây `WebApplicationType.NONE` loại bỏ web server. Ví dụ chỉ có một context không có hierarchy, một runner, listener đồng bộ và không bật `@Async`, nên các mốc tương đối rõ ràng. Trong dự án có nhiều runner, context hierarchy hoặc các callback async, cần kiểm tra thêm phạm vi và loại bảo đảm mình muốn.

## 7. So sánh các event dễ nhầm

| Event | Khi nào phát | Gợi ý dùng |
| --- | --- | --- |
| `ApplicationStartingEvent` | Rất sớm, trước khi environment/context sẵn sàng | Đăng ký listener từ trước `run()` |
| `ApplicationEnvironmentPreparedEvent` | Environment đã chuẩn bị, chưa tạo context | Hook chuẩn bị cấu hình môi trường |
| `ApplicationPreparedEvent` | Context đã được chuẩn bị và definitions được load, chưa refresh | Quan sát bước trước refresh |
| `ContextRefreshedEvent` | Một Spring `ApplicationContext` refresh xong | Lắng nghe vòng đời context |
| `ApplicationStartedEvent` | **Sau refresh, trước runner** | Hook/metrics ở mốc started |
| `ApplicationReadyEvent` | Sau runner | Công việc yêu cầu Boot đã hoàn tất startup |
| `ApplicationFailedEvent` | Startup có exception | Xử lý/ghi nhận nhánh lỗi |

**`ContextStartedEvent` không phải `ApplicationStartedEvent`.** `ContextStartedEvent` là sự kiện Spring Framework phát liên quan đến `ConfigurableApplicationContext.start()`; `ApplicationStartedEvent` là event startup được Spring Boot phát trong `SpringApplication.run()`. Không suy ra hai tên này đồng nghĩa.

## 8. Startup thất bại: started có thể đã xảy ra nhưng ready chưa

Có hai thời điểm lỗi quan trọng:

**Lỗi trước khi refresh thành công:** Boot chưa đạt mốc started nên `ApplicationStartedEvent` không xuất hiện. `ApplicationFailedEvent` có thể được phát để báo nguyên nhân failure.

**Lỗi ở `ApplicationRunner`/`CommandLineRunner`:** Boot đã phát `ApplicationStartedEvent` trước đó; runner ném exception khiến startup thất bại. `ApplicationReadyEvent` không xuất hiện theo luồng startup bình thường.

Ví dụ:

~~~java
// Đoạn minh họa về runner thất bại; chưa phải class độc lập.
@Bean
ApplicationRunner failingRunner() {
    return args -> {
        throw new IllegalStateException("Required configuration unavailable");
    };
}
~~~

Nếu cấu hình thêm runner lỗi này, cần xác định thứ tự gọi runner nếu có nhiều runner. Không nên dùng sự kiện started làm bằng chứng “ứng dụng khởi động đã thành công” khi vẫn còn các bước hậu refresh có thể thất bại.

Với monitoring, thường nên phân biệt trạng thái **context created**, **started**, **ready** và **failed** thay vì chỉ lưu một cờ boolean `started=true`.

## 9. Đồng bộ, `@Async` và thời điểm hoàn tất

### Listener mặc định đồng bộ

Với `SimpleApplicationEventMulticaster` mặc định, callback listener được gọi đồng bộ trong quá trình phát event. Một listener `ApplicationStartedEvent` chạy lâu có thể làm chậm runner và readiness. Exception không xử lý trong callback đồng bộ có thể làm `SpringApplication.run` thất bại tùy cấu hình error handler.

Đừng đặt request mạng không timeout, công việc migration lớn hoặc tác vụ có thể treo vào listener startup đồng bộ mà không quản lý lỗi.

### Listener bất đồng bộ

Nếu bean có `@Async`, ứng dụng bật `@EnableAsync` và cấu hình executor phù hợp, phần thân listener có thể chạy trên thread nền:

~~~java
// Minh họa: cần @EnableAsync và bean executor có tên startupExecutor.
@Async("startupExecutor")
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    warmupCache();
}
~~~

Event vẫn mang ý nghĩa mốc started, nhưng **Boot không mặc nhiên chờ tác vụ async này kết thúc trước khi gọi runner**. Nếu runner cần cache đã warmup, sẽ có race condition. Khi có phụ thuộc, hãy dùng một bước điều phối có chờ kết quả tường minh, hoặc để runner trực tiếp thực hiện/chờ công việc cần thiết.

Thread async không tự mang theo transaction, `ThreadLocal`, security context hay MDC của thread phát. Cần quyết định cách truyền context, log lỗi, retry và xử lý khi executor bão hòa.

### `getTimeTaken()` và hiệu năng

`getTimeTaken()` đo đến **mốc started**. Nó không thể hiện chính xác thời gian runner vì runner còn chưa chạy. Để tìm chỗ chậm, kết hợp thời gian đến ready và quan sát các bước khởi động bằng công cụ thích hợp (ví dụ `ApplicationStartup`, metrics/tracing).

## 10. Parent/child contexts và khả năng nhận nhiều event

Spring cho phép có context cha và context con. Event được publish trong child có thể lan truyền lên parent, khiến listener trong parent nhận thêm sự kiện. Nếu xử lý chỉ dành cho context đang sở hữu bean, nên kiểm tra identity:

~~~java
// Minh họa trong bean đã inject ApplicationContext ownContext.
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    initializeForOwnContext();
}
~~~

Đoạn minh họa này cần khai báo `ownContext` và `initializeForOwnContext`. Với nhiều `SpringApplication`, integration tests hoặc context hierarchy, không dùng một biến static toàn JVM để khẳng định event chỉ có một lần trong đời process.

Khi một startup action có side effect, nên thiết kế nó có thể chạy lặp mà không gây trùng bản ghi, gửi trùng thông báo hoặc chiếm tài nguyên nhiều lần. Điều này đặc biệt có giá trị khi test chạy với nhiều context.

## 11. Chọn công cụ phù hợp với yêu cầu

| Nhu cầu thực tế | Công cụ phù hợp |
| --- | --- |
| Ghi nhận mốc context refresh xong nhưng chưa chạy runner | `ApplicationStartedEvent` |
| Cần chạy một bước khởi tạo có kiểm soát, sau refresh | `ApplicationRunner` hoặc `CommandLineRunner` |
| Cần phản ứng sau mọi runner và quá trình startup Boot | `ApplicationReadyEvent` |
| Cần theo dõi live/ready để nhận traffic | `ApplicationAvailability`, health/readiness probe |
| Cần quản lý start/stop của một tài nguyên theo context | `SmartLifecycle` hoặc lifecycle phù hợp |
| Cần bắt event trước khi context tồn tại | `ApplicationListener` đăng ký sớm với `SpringApplication` |
| Cần xử lý thất bại trong startup | `ApplicationFailedEvent`, log và error handling |

### Các lỗi thường gặp

- **Nhầm started với ready:** `ApplicationStartedEvent` xảy ra **trước** runner. Không xây dựng điều kiện sẵn sàng phục vụ request chỉ dựa trên event này.
- **Nhầm starting với started:** `ApplicationStartingEvent` xảy ra khi còn rất sớm; bean listener thông thường có thể chưa tồn tại.
- **Nhầm Boot với Framework:** `ContextStartedEvent` không đồng nhất với `ApplicationStartedEvent`.
- **Chặn startup vô hạn:** listener đồng bộ gọi mạng chậm hoặc chờ Future không timeout.
- **Tin rằng async listener hoàn tất trước runner:** khi dùng `@Async`, Boot chỉ biết listener đã được schedule; công việc có thể chưa chạy xong.
- **Không xét lỗi runner:** started đã phát nhưng ready có thể không xuất hiện nếu runner thất bại.
- **Không lọc context:** callback trong parent nhận event từ child và vô tình chạy nhiều lần.
- **Đo thời gian sai:** `getTimeTaken()` tại started chưa bao gồm runner; giá trị có thể `null`.
- **Dùng `@TransactionalEventListener` không có transaction:** event vòng đời Boot thường không gắn với transaction hiện tại, và listener transaction-bound mặc định có thể bỏ qua event.

## 12. Bài tập tự kiểm tra

1. Chạy ví dụ Java; giải thích tại sao `ContextRefreshedEvent` xuất hiện trước `ApplicationStartedEvent`.
2. Thêm một `CommandLineRunner`. Nếu cần thứ tự cụ thể giữa nhiều runner, dùng `@Order`/`Ordered` và kiểm thử. Không tự giả định chúng có thứ tự nhất định khi không cấu hình.
3. Tạo runner ném exception; dự đoán những event nào đã phát và event nào không xuất hiện.
4. In `getTimeTaken()` tại started và ready. Tại sao số đo giữa các lần chạy và giữa hai event có thể khác?
5. Chuyển một listener started thành `@Async`, thêm xử lý chậm; kiểm tra liệu runner có chờ listener hoàn tất hay không.
6. Trong ứng dụng có parent/child context, sử dụng `getApplicationContext()` để bảo đảm listener xử lý đúng nguồn.

**Ghi nhớ:** `ApplicationStartedEvent` đánh dấu Spring Boot đã refresh xong context và sắp bắt đầu gọi các runner. Để xác nhận những công việc startup sau refresh đã hoàn tất, dùng mốc ready và các điều kiện readiness phù hợp.

## Tài liệu chính thức

- Spring Boot — SpringApplication events và thứ tự startup: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationStartedEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3 — `SpringApplicationRunListener` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot 3.3 — `ApplicationReadyEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Framework — ApplicationContext events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
