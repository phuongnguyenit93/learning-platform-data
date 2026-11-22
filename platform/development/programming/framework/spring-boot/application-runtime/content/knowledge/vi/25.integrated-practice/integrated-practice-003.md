# Gắn initializer, listener và runner để đối chiếu thứ tự quan sát trong Spring Boot

## 1. Mục tiêu của bài thực hành tổng hợp

Một ứng dụng Spring Boot không chỉ có hai trạng thái “chưa chạy” và “đã chạy”. Giữa lời gọi `SpringApplication.run(...)` và lúc ứng dụng sẵn sàng nhận yêu cầu là một chuỗi giai đoạn: chuẩn bị môi trường, tạo context, áp dụng initializer, nạp bean definitions, refresh, phát các sự kiện, thực thi runners và cuối cùng công bố readiness.

Ba loại extension point thường gây nhầm lẫn nhất là:

- **`ApplicationContextInitializer`**: tùy chỉnh context **trước khi `refresh()`**; thích hợp cho property sources, profiles hoặc bean definitions khi hiểu đúng loại context.
- **`ApplicationListener` / `@EventListener`**: quan sát sự kiện trong vòng đời. Listener được đăng ký trước `SpringApplication.run` có thể nhận cả early events mà bean listener chưa tồn tại.
- **`ApplicationRunner` / `CommandLineRunner`**: thực thi một công việc **sau context refresh, trước `ApplicationReadyEvent`**; có thể đặt thứ tự bằng `Ordered` hoặc `@Order`.

Bài này ghép cả ba vào **một ứng dụng non-web chạy được trên Java 17+ / Spring Boot 3.3.x**. Chúng ta ghi lại các mốc theo đúng thời điểm chúng xảy ra rồi in toàn bộ timeline sau khi đóng context. Cách đó làm thứ tự dễ quan sát, tránh nhầm log của Spring/Gradle với log do bài tạo.

### Sau bài học, bạn sẽ làm được

1. Đăng ký một initializer với `SpringApplication.addInitializers(...)`.
2. Đăng ký listener sớm bằng `SpringApplication.addListeners(...)`.
3. Nhận `ContextRefreshedEvent`/`ContextClosedEvent` qua một bean có `@EventListener`.
4. Khai báo hai runners với thứ tự tường minh bằng `Ordered`.
5. Quan sát `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent`, `ApplicationPreparedEvent`, `ApplicationStartedEvent` và `ApplicationReadyEvent`.
6. Phân biệt `LivenessState.CORRECT` và `ReadinessState.ACCEPTING_TRAFFIC`.
7. Kiểm tra timeline của một lần chạy, thêm unit test / integration test giới hạn phạm vi.
8. Giải thích vì sao một listener không nên thực hiện việc nặng làm chậm startup.

**Giới hạn:** ví dụ cố tình dùng `WebApplicationType.NONE`, không có HTTP server, database hoặc message broker. Vì vậy thứ tự quan sát của **những mốc chung** dễ xác định hơn. Trong ứng dụng web, còn có các sự kiện như `WebServerInitializedEvent` giữa prepared và started; không nên lấy bài non-web để suy ra thứ tự chính xác của mọi event web.

## 2. Trình tự lifecycle chuẩn cần đối chiếu

Spring Boot 3.3 mô tả các sự kiện chính theo trật tự:

```text
SpringApplication.run(args)
    |
    v
ApplicationStartingEvent
    |
    v
ApplicationEnvironmentPreparedEvent
    |
    v
[ Tạo ApplicationContext ]
    |
    v
ApplicationContextInitializer.initialize(context)
    |
    v
ApplicationContextInitializedEvent
    |
    v
[ Nạp bean definitions ]
    |
    v
ApplicationPreparedEvent
    |
    v
[ ApplicationContext.refresh() ]
    |
    +--> ContextRefreshedEvent
    |
    v
ApplicationStartedEvent
    |
    v
AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    v
ApplicationRunner / CommandLineRunner theo order
    |
    v
ApplicationReadyEvent
    |
    v
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    |
    v
SpringApplication.run(...) trả về context
```

Đây là **mốc chuẩn** của đường khởi động thành công. `ApplicationFailedEvent` là nhánh khi startup thất bại, không phải một bước xuất hiện trong mọi lần chạy.

### 2.1. Sự kiện Spring Framework nằm xen giữa Boot events

`ContextRefreshedEvent` thuộc Spring Framework và được phát khi `ApplicationContext.refresh()` hoàn tất. Đối với ứng dụng web, `WebServerInitializedEvent` cũng xuất hiện trong khoảng từ prepared đến started. Danh sách sự kiện `SpringApplicationEvent` không phải danh sách toàn bộ Spring `ApplicationEvent`.

### 2.2. “Started” khác “Ready”

- **Started:** context đã refresh; **runners chưa được gọi**.
- **Ready:** các `ApplicationRunner` và `CommandLineRunner` đã được gọi thành công; Boot có thể công bố readiness accepting.
- Một runner chặn 5 giây sẽ đẩy mốc ready ra sau 5 giây, dù context refresh đã xong.
- Nếu runner ném exception, `ApplicationReadyEvent` và trạng thái readiness thành công **không thuộc đường chạy thành công đó**; Boot xử lý startup failure.

### 2.3. Vì sao cần ghi lại thay vì đọc thứ tự một số log?

Log có thể đến từ nhiều threads và nhiều appenders, có buffer, formatter hoặc được hệ thống quan sát thu gom lại. Hai dòng log hiển thị không phải lúc nào cũng chứng minh quan hệ happens-before của hai callbacks.

Trong ví dụ này, các callback do bài kiểm soát thêm một chuỗi vào `CopyOnWriteArrayList`. Ứng dụng sử dụng event dispatcher đồng bộ mặc định và không tạo async work riêng. Sau khi `run` trả về và context đóng, chương trình in lại snapshot có số thứ tự. **Với các giả định này**, timeline có ý nghĩa để học quan hệ giữa các mốc.

## 3. Mỗi extension point có quyền gì?

| Extension point | Thời điểm | Nên làm | Không nên giả định |
| --- | --- | --- | --- |
| `SpringApplication.addListeners` với early listener | Được đăng ký trước `run` | Ghi nhận early Boot events, quan sát trạng thái | Mọi Spring bean đã tồn tại |
| `ApplicationContextInitializer.initialize` | Context đã được tạo nhưng chưa refresh | Thêm property source, active profile, bean definition hợp lệ | `getBean` luôn trả service đã initialize |
| `ApplicationContextInitializedEvent` | Sau initializers, trước bean definitions | Kiểm tra context đã được chuẩn bị | Bean graph đã tạo |
| `ApplicationPreparedEvent` | Sau load bean definitions, trước refresh | Quan sát cấu hình đã chuẩn bị | Singleton beans đã sẵn sàng |
| `ContextRefreshedEvent` | Khi refresh hoàn tất | Quan sát context lifecycle | Boot runners đã hoàn thành |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Ghi nhận app started | Application ready |
| `ApplicationRunner` | Sau started, trước ready | Warm-up/validation có chủ đích, khởi tạo nghiệp vụ bắt buộc | Được phép chạy vô hạn mà không ảnh hưởng readiness |
| `ApplicationReadyEvent` | Sau runners | Báo mốc Boot ready | Mọi external dependency luôn khỏe mãi |
| `ContextClosedEvent` | Khi context bắt đầu đóng | Nhận biết shutdown, phối hợp ở mức thích hợp | Tất cả bean đã destroy xong |

### 3.1. Initializer không phải @PostConstruct

`@PostConstruct` chạy khi một bean đã được tạo và dependency injection/bean lifecycle đang diễn ra. `ApplicationContextInitializer` chạy **trước refresh** trên `ConfigurableApplicationContext`. Không được chuyển code cần BeanFactory đã refresh vào initializer chỉ vì muốn chạy “sớm nhất”.

### 3.2. Early listener không phải Spring bean listener

Một bean `@Component` implement `ApplicationListener<ApplicationStartingEvent>` thường **chưa được tạo** lúc event starting phát ra. Vì vậy phải đăng ký listener cần early events **trước `run`** hoặc qua cơ chế đăng ký sớm của Boot. Sau context refresh, một bean listener hoặc method `@EventListener` có thể xử lý các event tương ứng.

### 3.3. Runner không phải controller hoặc scheduler

`ApplicationRunner` và `CommandLineRunner` chạy một lần theo `SpringApplication.run`; chúng không phải background schedulers tự lặp, cũng không phải HTTP handlers. Chúng nên có điều kiện kết thúc rõ ràng. Nếu công việc khởi tạo không bắt buộc, đừng chặn readiness vì một job dài không cần thiết.

## 4. Thiết kế bài thực hành: một timeline chung

Để quan sát được thứ tự, tất cả các callback sẽ gọi một hàm nhỏ:

```java
static void mark(String value) {
    TIMELINE.add(value);
}
```

`TIMELINE` trong bài là một `CopyOnWriteArrayList<String>` dùng chung, chỉ được tạo cho **demo trong một JVM**. Bài học không cần lưu timeline vào database, gửi HTTP hoặc tạo executor.

### 4.1. Vì sao chọn CopyOnWriteArrayList?

- Có thể ghi các dấu mốc mà không cần tự đồng bộ từng lệnh.
- Thuận tiện lấy snapshot khi đã đóng context.
- Tránh `ConcurrentModificationException` nếu sau này có thay đổi đơn giản ở phần quan sát.

Đây **không** phải công cụ tracing production. `CopyOnWriteArrayList` tốn chi phí copy khi ghi nhiều, không phù hợp ghi hàng triệu events. Trong production, dùng metrics, structured logging, tracing hoặc `ApplicationStartup` tùy mục tiêu.

### 4.2. Vì sao không in trực tiếp trong callback?

Bài muốn so sánh **thứ tự của chính các callback**. Khi chỉ thêm dữ liệu vào một list rồi in ở cuối, không phụ thuộc formatter/log appender, progress messages của Gradle hoặc banner Spring. Tuy nhiên timeline cũng chỉ phản ánh những mốc đã instrument, không phải mọi hoạt động nội bộ của JVM.

### 4.3. Không có background work trong demo

Để giữ thứ tự có thể dự đoán:

- Ứng dụng non-web, không mở port.
- Không bật `@Async` hoặc tự tạo threads.
- Không có `@Scheduled`.
- Không có Spring context hierarchy.
- Không có listener được gọi bất đồng bộ do custom `ApplicationEventMulticaster`.

Với production app thực tế, các giới hạn này không phải luôn đúng, nên thứ tự giữa các callback độc lập có thể cần kiểm tra bằng synchronization/happens-before, không chỉ dựa vào một list.

## 5. Tạo dự án Spring Boot 3.3 / Java 17

### 5.1. Cấu trúc thư mục

```text
lifecycle-observation/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/observe/
    LifecycleOrderApplication.java
  src/test/java/com/example/observe/
    LifecycleOrderApplicationTest.java
```

Ví dụ chính gói mọi thành phần vào một file Java bằng các nested classes để **không thiếu file** và dễ chạy. Bài kiểm thử là một file riêng.

### 5.2. settings.gradle

```groovy
rootProject.name = 'lifecycle-observation'
```

### 5.3. build.gradle

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter` cung cấp core Spring Boot/autoconfiguration và logging.
- `spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ cho phần test.
- Không dùng web starter, nên demo không mở HTTP port.
- Java toolchain khóa ở Java 17 để tránh vô tình dùng API thuộc Java 21+.
- Các lệnh `./gradlew` giả định project đã có Gradle Wrapper; nếu tạo thủ công hãy sinh wrapper qua Gradle tương thích hoặc dùng Spring Initializr.

### 5.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Có thể ghi đè từ CLI khi thử precedence.
demo.mode=observed

# Giảm thông tin log framework để dễ nhìn timeline.
logging.level.root=WARN
```

Trong code, initializer thêm một `PropertySource` mặc định với `demo.mode=observed` ở **cuối** thứ tự ưu tiên. Property ở đây cùng giá trị để demo mặc định không thay đổi theo cách nhập file. Khi thử `--demo.mode=fast`, giá trị CLI ưu tiên hơn default từ initializer.

`spring.main.web-application-type=none` cũng được set tường minh trong `main` để bảo đảm ví dụ non-web dù sau này người học thêm dependency web.

## 6. File Java hoàn chỉnh: initializer, listeners và hai runners

**File:** `src/main/java/com/example/observe/LifecycleOrderApplication.java`

```java
package com.example.observe;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class LifecycleOrderApplication {

    private static final CopyOnWriteArrayList<String> TIMELINE =
            new CopyOnWriteArrayList<>();

    static void mark(String step) {
        TIMELINE.add(step);
    }

    static void resetTimeline() {
        TIMELINE.clear();
    }

    static List<String> snapshot() {
        return List.copyOf(TIMELINE);
    }

    static SpringApplication configuredApplication() {
        SpringApplication app =
                new SpringApplication(LifecycleOrderApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        // Đăng ký TRƯỚC run() để bắt early events.
        app.addListeners(new EarlyEventObserver());

        // Initializer chạy trước context.refresh().
        app.addInitializers(new ModeInitializer());

        return app;
    }

    public static void main(String[] args) {
        resetTimeline();
        mark("MAIN_BEFORE_RUN");

        SpringApplication app = configuredApplication();

        ConfigurableApplicationContext context = app.run(args);
        mark("MAIN_AFTER_RUN");

        // Đóng context có chủ đích để quan sát ContextClosedEvent.
        context.close();
        mark("MAIN_AFTER_CLOSE");

        List<String> result = snapshot();
        for (int i = 0; i < result.size(); i++) {
            System.out.printf(
                    "TRACE|%02d|%s%n", i + 1, result.get(i));
        }
    }

    public static final class ModeInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext context) {
            context.getEnvironment().getPropertySources().addLast(
                    new MapPropertySource(
                            "lesson-defaults",
                            Map.of("demo.mode", "observed")));

            String mode =
                    context.getEnvironment().getProperty("demo.mode");

            mark("INITIALIZER:mode=" + mode);
        }
    }

    public static final class EarlyEventObserver
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationStartingEvent) {
                mark("APPLICATION_STARTING");
            } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
                mark("ENVIRONMENT_PREPARED");
            } else if (event instanceof ApplicationContextInitializedEvent) {
                mark("CONTEXT_INITIALIZED");
            } else if (event instanceof ApplicationPreparedEvent) {
                mark("APPLICATION_PREPARED");
            } else if (event instanceof ApplicationStartedEvent) {
                mark("APPLICATION_STARTED");
            } else if (event instanceof ApplicationReadyEvent) {
                mark("APPLICATION_READY");
            } else if (event instanceof ApplicationFailedEvent) {
                mark("APPLICATION_FAILED");
            } else if (event instanceof AvailabilityChangeEvent<?> change) {
                if (change.getState() == LivenessState.CORRECT) {
                    mark("LIVENESS_CORRECT");
                } else if (change.getState()
                        == ReadinessState.ACCEPTING_TRAFFIC) {
                    mark("READINESS_ACCEPTING_TRAFFIC");
                }
            }
        }
    }

    // Bean listener được đăng ký qua Spring event infrastructure
    // khi context được refresh, không phải early listener.
    @Bean
    ContextEventObserver contextEventObserver() {
        return new ContextEventObserver();
    }

    public static final class ContextEventObserver {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            mark("CONTEXT_REFRESHED");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            mark("CONTEXT_CLOSED");
        }
    }

    @Bean
    ApplicationRunner orderedApplicationRunner(Environment env) {
        return new OrderedApplicationJob(env);
    }

    @Bean
    CommandLineRunner orderedCommandLineRunner(Environment env) {
        return new OrderedCommandJob(env);
    }

    public static final class OrderedApplicationJob
            implements ApplicationRunner, Ordered {

        private final Environment environment;

        public OrderedApplicationJob(Environment environment) {
            this.environment = environment;
        }

        @Override
        public int getOrder() {
            return 10;
        }

        @Override
        public void run(ApplicationArguments arguments) {
            mark("RUNNER_10:mode="
                    + environment.getProperty("demo.mode"));
        }
    }

    public static final class OrderedCommandJob
            implements CommandLineRunner, Ordered {

        private final Environment environment;

        public OrderedCommandJob(Environment environment) {
            this.environment = environment;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... arguments) {
            mark("RUNNER_20:mode="
                    + environment.getProperty("demo.mode"));
        }
    }
}
```

Đây là **file Java hoàn chỉnh**: đúng public class/file name, có imports, không tham chiếu tới helper bên ngoài dự án. Nó tạo **một** `SpringApplication`, đăng ký initializer/early listener trước `run`, tạo bean listener và hai runner trong Spring context, rồi đóng context.

### 6.1. Vì sao dùng implements Ordered cho runners?

Spring Boot sắp xếp các `ApplicationRunner` và `CommandLineRunner` beans theo Spring ordering. Hai loại runner tham gia cùng một chuỗi xử lý; không mặc định “ApplicationRunner luôn chạy trước CommandLineRunner”.

Ở đây:

- `OrderedApplicationJob.getOrder() = 10`.
- `OrderedCommandJob.getOrder() = 20`.
- Giá trị order **thấp hơn** được ưu tiên **trước**.

Vì đã đặt hai giá trị khác nhau, bài có thể kiểm tra thứ tự hai runner một cách xác định. Tránh gán cùng order hoặc chỉ tin thứ tự đăng ký `@Bean` nếu nghiệp vụ yêu cầu rõ ràng.

### 6.2. Vì sao initializer dùng addLast?

`MapPropertySource` đặt ở cuối danh sách làm **giá trị mặc định có độ ưu tiên thấp**. Khi truyền CLI `--demo.mode=fast`, nguồn command-line có ưu tiên cao nên runner đọc `fast`.

Nếu initializer gọi `addFirst` và ghi đè một cấu hình đã cung cấp, nó có thể vô tình thay đổi giá trị mà user/ops đã đặt. Đó là một lựa chọn chính sách phải có chủ đích, không phải mặc định luôn đúng.

### 6.3. Vì sao listener sớm implement ApplicationListener<ApplicationEvent>?

`EarlyEventObserver` nhận các Spring `ApplicationEvent` và lọc những type bài muốn quan sát. Trong thực tế, một listener nhận type cụ thể (ví dụ `ApplicationListener<ApplicationStartingEvent>`) thường dễ bảo trì hơn. Ở đây dùng một listener tổng hợp để lập timeline cho nhiều mốc mà **không cần tạo một class cho mỗi event**.

Không nên log **tất cả** `ApplicationEvent` bằng `event.toString()` ở production: có thể gây nhiễu, leak dữ liệu hoặc tốn thời gian. Phần code chỉ ghi các tên mốc đã chủ động liệt kê.

### 6.4. Vì sao ContextEventObserver là bean?

`ContextRefreshedEvent` và `ContextClosedEvent` xảy ra sau khi bean context có thể xử lý các listener methods. Một `@Bean ContextEventObserver` với `@EventListener` giúp chứng minh method listener được Spring annotation infrastructure đăng ký.

Nếu tạo một object bằng `new ContextEventObserver()` rồi **không đăng ký** vào context, Spring event bus sẽ **không tự gọi** methods được annotate của object đó.

### 6.5. Vì sao main đóng context?

Demo non-web nên không có HTTP server giữ process sống lâu. Việc gọi `context.close()` có chủ đích giúp thấy `ContextClosedEvent`. Sau khi context đóng, `main` chỉ in timeline đã lưu, không gọi `getBean` hoặc yêu cầu resource hoạt động tiếp.

Trong web service thực tế, bạn không nên đóng context ngay sau khi `SpringApplication.run` trả về: như vậy server vừa ready đã bị shutdown, không thể phục vụ traffic.

## 7. Lệnh chạy và cách đọc stdout

Chạy tại thư mục có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trong đường chạy **thành công, không thêm CLI override**, các dòng có prefix `TRACE|` do chương trình tự in được dự kiến theo thứ tự:

```text
TRACE|01|MAIN_BEFORE_RUN
TRACE|02|APPLICATION_STARTING
TRACE|03|ENVIRONMENT_PREPARED
TRACE|04|INITIALIZER:mode=observed
TRACE|05|CONTEXT_INITIALIZED
TRACE|06|APPLICATION_PREPARED
TRACE|07|CONTEXT_REFRESHED
TRACE|08|APPLICATION_STARTED
TRACE|09|LIVENESS_CORRECT
TRACE|10|RUNNER_10:mode=observed
TRACE|11|RUNNER_20:mode=observed
TRACE|12|APPLICATION_READY
TRACE|13|READINESS_ACCEPTING_TRAFFIC
TRACE|14|MAIN_AFTER_RUN
TRACE|15|CONTEXT_CLOSED
TRACE|16|MAIN_AFTER_CLOSE
```

Các dòng framework, Gradle progress hoặc cảnh báo có thể xuất hiện bên ngoài nhóm `TRACE|`. Để so sánh, chỉ lọc các dòng có prefix do code mẫu tạo, không bắt toàn bộ stdout phải đúng 16 dòng.

**Lý do có thể dự đoán:** code không tạo async listeners, chỉ có một context và hai runners có order phân biệt; các sự kiện liệt kê tương ứng với contract Spring Boot 3.3. Nếu người học thay đổi config, thêm custom initializer, context hierarchy, web server hoặc listeners bất đồng bộ, những giả định đó không còn nguyên vẹn. Khi ấy nên assert **quan hệ trước/sau cốt lõi** thay vì đóng đinh một danh sách tuyệt đối.

### 7.1. Đọc từng mốc

| Mốc | Vì sao ở vị trí đó? |
| --- | --- |
| `MAIN_BEFORE_RUN` | Ghi trước khi gọi `SpringApplication.run` |
| `APPLICATION_STARTING` | Listener đã đăng ký sớm nên bắt được event đầu tiên |
| `ENVIRONMENT_PREPARED` | `Environment` đã chuẩn bị, chưa có context |
| `INITIALIZER:mode=observed` | Context có rồi; initializer thêm default property |
| `CONTEXT_INITIALIZED` | Boot phát sau khi initializers hoàn tất |
| `APPLICATION_PREPARED` | Bean definitions đã load; refresh chưa bắt đầu |
| `CONTEXT_REFRESHED` | Context đã refresh, bean event listener hoạt động |
| `APPLICATION_STARTED` | Boot báo started sau refresh và trước runners |
| `LIVENESS_CORRECT` | Boot công bố liveness sau started |
| `RUNNER_10` | Ordered runner priority 10 chạy trước |
| `RUNNER_20` | Ordered runner priority 20 chạy sau |
| `APPLICATION_READY` | Boot báo ready sau khi các runners hoàn thành |
| `READINESS_ACCEPTING_TRAFFIC` | Boot công bố trạng thái readiness |
| `MAIN_AFTER_RUN` | Chỉ chạy sau khi `SpringApplication.run` thành công và trả về |
| `CONTEXT_CLOSED` | Xảy ra trong lời gọi `context.close()` |
| `MAIN_AFTER_CLOSE` | Chỉ chạy sau khi close trả về |

### 7.2. Bản chất MAIN_AFTER_RUN

`SpringApplication.run` thường trả về `ConfigurableApplicationContext` **sau** giai đoạn ready của một đường startup bình thường. Vì vậy dòng main sau run không phải một callback Spring lifecycle; nó là mốc quan sát của caller.

Đừng nhầm `MAIN_AFTER_RUN` là sự kiện do Boot phát. Trong một ứng dụng cần tiếp tục phục vụ HTTP, `main` có thể return còn các threads của web server giữ JVM chạy.

### 7.3. Context closed không có nghĩa JVM phải chết ngay

`ApplicationContext.close()` dừng Spring context và destroy các beans theo lifecycle. Nếu còn executor/thread không-daemon được tạo ngoài container, process có thể vẫn sống. Trong demo không tạo những tài nguyên đó.

`System.exit` không cần cho bài này và không nên được gọi từ listener/runner chỉ để “xem event cuối”; nó có thể kết thúc JVM và cắt ngang quan sát hoặc cleanup.

## 8. Thử property override và kiểm tra thời điểm initializer

Chạy:

```bash
./gradlew bootRun --args="--demo.mode=fast"
```

Những mốc đổi giá trị dự kiến:

```text
TRACE|04|INITIALIZER:mode=fast
TRACE|10|RUNNER_10:mode=fast
TRACE|11|RUNNER_20:mode=fast
```

Những mốc thứ tự còn lại giữ nguyên trong demo đơn giản. Lý do: nguồn command-line được Boot đưa vào `Environment` trước khi initializer chạy, và `MapPropertySource` được thêm ở cuối nên không ghi đè giá trị `fast`.

### 8.1. Thử bỏ property trong application.properties

Nếu xóa dòng `demo.mode=observed` khỏi file, initializer vẫn cung cấp default `observed`. Chương trình vẫn có giá trị cấu hình để runner đọc.

Nếu thay initializer thành:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "lesson-defaults",
                Map.of("demo.mode", "observed")));
```

thì nó có thể áp đặt `observed` dù CLI truyền `fast`, vì source của initializer được đưa lên đầu thứ tự ưu tiên. Đây là **thí nghiệm lý giải precedence**, không phải lời khuyên luôn dùng `addFirst`.

### 8.2. Không ghi secrets trong timeline

Demo chỉ ghi một property công khai `demo.mode`. Với hệ thống thật, không tự đưa `spring.datasource.password`, bearer token, API keys, query parameters nhạy cảm hoặc nguyên mảng args vào timeline. Logs có thể được thu thập tập trung và có người truy cập ngoài dự kiến.

## 9. Runner ordering: thử thay 10 và 20

Giả sử sửa `OrderedApplicationJob.getOrder()` trả `30`, còn `OrderedCommandJob.getOrder()` trả `20`. Trong đường chạy thành công, thứ tự sẽ đảo:

```text
RUNNER_20:mode=observed
RUNNER_10:mode=observed
```

Dòng label `RUNNER_10` khi ấy không còn mô tả đúng **giá trị order thật** của code vì tên label ban đầu được viết cố định. Khi thực hành, hãy đổi luôn label thành `RUNNER_ORDER_30` để tránh đọc nhầm.

**Điều cần rút ra:** `ApplicationRunner` không mặc định chạy trước `CommandLineRunner`. Boot sắp xếp cả hai qua ordering contract; `Ordered`/`@Order` chỉ rõ mức ưu tiên. Khi order bằng nhau, tránh phụ thuộc vào một thứ tự tình cờ do classpath hoặc bean registration.

### 9.1. Khi nào dùng ApplicationRunner?

`ApplicationRunner.run(ApplicationArguments args)` cung cấp `ApplicationArguments` đã phân tích các option và non-option arguments. Dùng khi cần:

- Đọc `--mode=fast` hoặc `--input=path` dưới dạng options.
- Validate các tham số của batch job.
- Thực hiện warm-up bắt buộc và báo lỗi nếu không hoàn thành.
- Chuẩn bị dữ liệu cần thiết trước khi Boot ready.

### 9.2. Khi nào dùng CommandLineRunner?

`CommandLineRunner.run(String... args)` nhận raw args; tiện cho chương trình đơn giản hoặc khi muốn tự parse. Về lifecycle, nó cũng chạy sau started và trước ready.

Không gọi lại runner bằng tay từ `ApplicationReadyEvent`, nếu không công việc có thể chạy hai lần. Nếu cần công việc định kỳ sau startup, dùng một scheduler/worker có owner và lifecycle riêng, không lạm dụng startup runner.

### 9.3. Runner có thể chặn readiness

Thử thêm trong runner:

```java
Thread.sleep(1500);
```

Đây chỉ là snippet, cần xử lý `InterruptedException` hoặc khai báo `throws Exception` ở method. Với code hiện tại `run(...)` không khai báo throws, nên không copy trần vào đó rồi kỳ vọng compiler tự chấp nhận checked exception.

Khi runner block 1,5 giây, khoảng cách giữa `APPLICATION_STARTED` và `APPLICATION_READY` tăng tương ứng. Nếu application dùng health/readiness, việc kéo dài runner làm kéo dài thời gian Boot công bố sẵn sàng. Không dùng `Thread.sleep` như chiến lược production; hãy chờ một điều kiện thực sự với timeout rõ.

## 10. Initializer và sự kiện ContextInitialized

Một thứ tự cốt lõi được Boot bảo đảm là:

```text
ApplicationEnvironmentPreparedEvent
      |
ApplicationContext được tạo
      |
ModeInitializer.initialize(context)
      |
ApplicationContextInitializedEvent
      |
Nạp bean definitions
      |
ApplicationPreparedEvent
```

### 10.1. Initializer có thể đọc gì?

Tại thời điểm initialize:

- `ConfigurableApplicationContext` object đã tồn tại.
- `context.getEnvironment()` có thể chứa các property sources được chuẩn bị trước đó.
- Có thể thêm `MapPropertySource`, chỉnh active profiles hoặc đăng ký definitions theo API context tương ứng.

Nhưng:

- Context chưa hoàn tất refresh.
- Các `@Bean` chưa nhất thiết được instantiate.
- Các beans phụ thuộc network, database hoặc web server chưa chắc sẵn sàng.
- Không nên dùng `getBean(...)` như một cơ chế “khởi động nghiệp vụ sớm”.

### 10.2. Vì sao không dùng @PostConstruct để đặt property default?

`@PostConstruct` chạy trên một bean đã khởi tạo. Khi đó một số beans khác có thể đã bind properties hoặc bắt đầu initialize; thêm default property quá muộn có thể khiến cấu hình không nhất quán.

`ApplicationContextInitializer` phù hợp hơn khi bạn cần điều chỉnh environment/context **trước refresh**. Với các cấu hình sớm hơn giai đoạn tạo context, có thể cần `EnvironmentPostProcessor` hoặc `BootstrapRegistryInitializer` tùy mục đích; không gộp tất cả vào initializer.

### 10.3. Không phải mọi initializer đều cần SpringApplication

Muốn test `ModeInitializer` đơn lẻ, tạo `GenericApplicationContext`, gọi `initialize(context)` và assert property. Không cần gọi `SpringApplication.run` cho logic thêm default property. Nhưng test đó **chưa chứng minh Boot đã đăng ký initializer đúng chỗ**; bài full run phía trên dùng để chứng minh wiring.

## 11. Listeners đăng ký sớm và bean @EventListener

Trong ví dụ có hai con đường đăng ký:

**Early listener**

```java
app.addListeners(new EarlyEventObserver());
```

Được thêm **trước `run`**, có thể nhận `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`. Đây là các mốc thường xảy ra trước khi bean container tạo beans.

**Bean listener**

```java
@Bean
ContextEventObserver contextEventObserver() {
    return new ContextEventObserver();
}
```

Class này có method:

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    mark("CONTEXT_REFRESHED");
}
```

Spring phải đọc bean definition, tạo bean và xử lý annotation method để đăng ký listener. Do đó cách này phù hợp cho các events trong/ sau context refresh, không phải mọi sự kiện cực sớm.

### 11.1. Điều gì xảy ra nếu chỉ thêm @Component cho early listener?

Một `@Component` listener có thể không nhận `ApplicationStartingEvent` vì bean của nó chưa tồn tại. Việc class compile và được component scan sau refresh không làm Spring phát lại sự kiện đã qua.

Để tự động đăng ký cho nhiều cách khởi tạo ứng dụng, Spring Boot hỗ trợ khai báo listener trong `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener`. Nhưng file đó cần đúng đường dẫn, class loadable/constructor thích hợp và không đăng ký trùng qua nhiều cách.

### 11.2. @EventListener xử lý ContextClosedEvent có đồng nghĩa đã destroy mọi resource?

Không. `ContextClosedEvent` được phát khi context đóng, **trước hoặc trong quy trình shutdown/destruction**; các beans có thể còn sống tại thời điểm listener nhận event. Không dùng event này như chứng cứ rằng mọi connection pool hoặc executor đã terminated.

Nếu muốn đảm bảo cleanup của một resource, dùng `@PreDestroy`, `DisposableBean`, lifecycle của managed executor hoặc test tình trạng resource **sau** khi `context.close()` trả về.

### 11.3. @Order trên listeners khác @Order trên runners

`@Order` hoặc `Ordered` có thể điều khiển thứ tự listener **cho cùng một event** khi dispatch đồng bộ. Nhưng thứ tự giữa hai **loại event khác nhau** đến từ lifecycle của Spring Boot, không do một annotation order trên listener quyết định.

Đừng dùng `@Order(1)` trên một `ApplicationReadyEvent` listener với hy vọng nó chạy trước `ApplicationStartedEvent`; chúng được phát ở hai mốc khác nhau.

## 12. AvailabilityChangeEvent: trạng thái sống và sẵn sàng

`EarlyEventObserver` trong demo kiểm tra:

```java
if (change.getState() == LivenessState.CORRECT) {
    mark("LIVENESS_CORRECT");
} else if (change.getState()
        == ReadinessState.ACCEPTING_TRAFFIC) {
    mark("READINESS_ACCEPTING_TRAFFIC");
}
```

Đây là hai trạng thái thuộc **hai enum khác nhau**:

- `LivenessState.CORRECT`: Spring Boot coi trạng thái nội bộ của application sau refresh là live.
- `ReadinessState.ACCEPTING_TRAFFIC`: Boot cho biết ứng dụng có thể nhận traffic theo lifecycle mặc định sau runners.

Ứng dụng non-web demo vẫn có các trạng thái availability dù không mở HTTP port. Đây là **tín hiệu lifecycle** để đối chiếu, không phải một kết quả HTTP health check.

### 12.1. Ready event và accepting traffic không có cùng timestamp tuyệt đối

Theo trình tự Boot:

```text
ApplicationReadyEvent
      |
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
```

Hai events ở sát nhau nhưng là hai lần publish tách biệt. Nếu một listener ready chạy lâu hoặc ném exception, nó có thể trì hoãn hoặc phá hỏng đường ready, tùy contract. Vì vậy tránh làm việc nặng trong listener.

### 12.2. Readiness không có nghĩa tất cả dependency ngoài luôn hoạt động

Trạng thái readiness là một phần của hợp đồng ứng dụng và hạ tầng. Nếu database hoặc API ngoài mất kết nối sau startup, các trạng thái health/availability cần xử lý bằng policy riêng. Không suy luận rằng `ApplicationReadyEvent` là chứng chỉ vĩnh viễn cho mọi remote dependency.

### 12.3. Liveness và dependency lỗi tạm thời

Không đánh dấu liveness broken chỉ vì một external dependency gián đoạn ngắn nếu application có thể phục hồi; trong Kubernetes, điều đó có thể gây restart storm. Readiness phù hợp hơn khi app tạm thời không nên nhận traffic.

## 13. Viết test cho timeline với JUnit 5

Ví dụ chính đã chạy qua toàn bộ SpringApplication nhưng **không cần web server**. Ta có thể kiểm tra quan hệ mốc thực tế trong một JUnit test riêng, đồng thời unit test initializer với context nhỏ.

**File:** `src/test/java/com/example/observe/LifecycleOrderApplicationTest.java`

```java
package com.example.observe;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleOrderApplicationTest {

    @Test
    void initializerAddsDefaultBeforeRefresh() {
        LifecycleOrderApplication.resetTimeline();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new LifecycleOrderApplication.ModeInitializer()
                    .initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("observed");
            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void explicitPropertyBeatsInitializerDefault() {
        LifecycleOrderApplication.resetTimeline();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-override",
                            Map.of("demo.mode", "fast")));

            new LifecycleOrderApplication.ModeInitializer()
                    .initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        }
    }

    @Test
    void applicationContextRunnerAppliesInitializer() {
        LifecycleOrderApplication.resetTimeline();

        new ApplicationContextRunner()
                .withInitializer(
                        new LifecycleOrderApplication.ModeInitializer())
                .withPropertyValues("demo.mode=fast")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("demo.mode")).isEqualTo("fast");
                });
    }

    @Test
    void springApplicationPublishesStagesAroundOrderedRunners() {
        LifecycleOrderApplication.resetTimeline();

        SpringApplication app =
                LifecycleOrderApplication.configuredApplication();

        try (ConfigurableApplicationContext context = app.run()) {
            List<String> events =
                    LifecycleOrderApplication.snapshot();

            assertThat(events).containsSubsequence(
                    "APPLICATION_STARTING",
                    "ENVIRONMENT_PREPARED",
                    "INITIALIZER:mode=observed",
                    "CONTEXT_INITIALIZED",
                    "APPLICATION_PREPARED",
                    "CONTEXT_REFRESHED",
                    "APPLICATION_STARTED",
                    "LIVENESS_CORRECT",
                    "RUNNER_10:mode=observed",
                    "RUNNER_20:mode=observed",
                    "APPLICATION_READY",
                    "READINESS_ACCEPTING_TRAFFIC"
            );

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("observed");
        }

        assertThat(LifecycleOrderApplication.snapshot())
                .contains("CONTEXT_CLOSED");
    }
}
```

Đây là **file test hoàn chỉnh**, có bốn test methods, dùng JUnit 5/AssertJ từ `spring-boot-starter-test`. Test thứ tư **thật sự gọi `SpringApplication.run`** (nhưng non-web) để xác minh event wiring/order; ba test còn lại không boot toàn ứng dụng.

### 13.1. Vì sao containsSubsequence thay vì containsExactly?

`containsSubsequence` kiểm tra một **chuỗi quan hệ có thứ tự**, cho phép những mốc khác xuất hiện xen vào sau khi ứng dụng được mở rộng. Điều này phù hợp với contract lifecycle hơn là khóa mọi mốc nội bộ. Nếu demo được thêm custom listener hay web starter, test vẫn phát hiện mối quan hệ quan trọng thay vì fail vì một log/event phụ.

### 13.2. Vì sao test không gọi main()?

`main` chủ động đóng context và in timeline. Gọi trực tiếp `main()` trong JUnit có thể khó kiểm soát stdout hoặc tác dụng phụ nếu người học mở rộng code.

Test sử dụng factory `configuredApplication()`, gọi `run` trong `try-with-resources` để context luôn đóng và kiểm tra timeline trực tiếp. Nó không cần `System.exit`.

### 13.3. Vì sao test đầu dùng GenericApplicationContext?

Initializer chỉ thao tác environment. Tạo `GenericApplicationContext` rồi gọi `initialize` là đủ; không phải chờ component scanning, autoconfiguration, DataSource hoặc web server. Đây là ví dụ áp dụng nguyên tắc **test nhỏ nhất đủ chứng minh hành vi**.

### 13.4. Lệnh chạy test

```bash
./gradlew test
```

Nếu cấu hình Gradle/JDK phù hợp và các dependencies tải được, bốn test được kỳ vọng pass. Gradle in `BUILD SUCCESSFUL` với thời gian phụ thuộc môi trường. Không dự đoán toàn bộ log, vì Spring Boot và test runner có thể in cảnh báo hoặc debug info khác.

Lưu ý: test sử dụng một list static để học timeline, nên **không chạy song song các test truy cập cùng recorder** khi chưa cô lập state. JUnit 5 thông thường không bật parallel test execution mặc định; nếu project của bạn đã bật parallel, cần thiết kế recorder theo từng context/test thay vì static global.

## 14. Điều gì xảy ra nếu runner thất bại?

Giả sử `OrderedCommandJob.run(...)` ném:

```java
throw new IllegalStateException(
        "SIMULATED_RUNNER_FAILURE");
```

Đây là snippet minh họa đặt trong runner, không phải đường mặc định của demo.

Trình tự thường đi đến:

```text
APPLICATION_STARTED
LIVENESS_CORRECT
RUNNER_10:mode=observed
[ Runner order 20 ném exception ]
APPLICATION_FAILED
[ Spring Boot xử lý failure / cleanup context ]
```

**Không có đường ready thành công** vì `SpringApplication.run` không hoàn tất bình thường. Cũng không được giả định tất cả destroy events của mọi bean đều có thứ tự giống một đường đóng bình thường; việc cleanup phụ thuộc pha xảy ra lỗi.

### 14.1. Vì sao main trong demo không in timeline khi run() ném?

Đường mặc định:

```java
ConfigurableApplicationContext context = app.run(args);
mark("MAIN_AFTER_RUN");
```

Khi `run` ném exception, dòng sau nó không được chạy. Vì vậy nếu bạn muốn thử failure mode và vẫn in kết quả, có thể dùng một `catch` ngoài `run` để dump recorder rồi **ném lại** exception, giữ nguyên fail status/stack trace. Không nên nuốt exception rồi báo “startup success”.

Mẫu bổ sung:

```java
try {
    ConfigurableApplicationContext context = app.run(args);
    // Đường thành công tiếp tục như ví dụ chính.
} catch (RuntimeException ex) {
    snapshot().forEach(System.err::println);
    throw ex;
}
```

Đây là snippet cần biến `app` và method `snapshot` trong cùng class. Không copy nó bên cạnh code hiện tại mà quên thống nhất cách quản lý `context`; hãy refactor thành một đường xử lý duy nhất nếu thực sự thêm failure mode.

### 14.2. ApplicationFailedEvent không phải mọi runtime exception

`ApplicationFailedEvent` xuất hiện trong đường **SpringApplication startup thất bại**. Một exception tại controller sau khi server ready không tự sinh event này. Tương tự một background job `@Async` fail sau vài phút cần handler/metrics riêng.

### 14.3. Failure listener không nên dựa vào bean còn sống

`ApplicationFailedEvent` có thể phát khi context chưa tạo hoặc refresh thất bại. Trong demo listener sớm chỉ ghi tên event, không dùng `context.getBean`. Đó là lựa chọn an toàn nếu muốn cùng listener hoạt động ở nhiều pha lỗi.

## 15. Đối chiếu thứ tự bằng một bảng trạng thái

| Mốc | Environment? | Context? | Beans sẵn sàng? | Runner đã chạy? | Ready? |
| --- | --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Chưa chuẩn bị | Chưa | Chưa | Chưa | Chưa |
| `ApplicationEnvironmentPreparedEvent` | Có | Chưa | Chưa | Chưa | Chưa |
| `ModeInitializer.initialize` | Có | Mới tạo, chưa refresh | Không đảm bảo | Chưa | Chưa |
| `ApplicationContextInitializedEvent` | Có | Có, chưa load definitions | Không | Chưa | Chưa |
| `ApplicationPreparedEvent` | Có | Có, chưa refresh | Không đảm bảo | Chưa | Chưa |
| `ContextRefreshedEvent` | Có | Đã refresh | Singleton không lazy thường tạo | Chưa | Chưa |
| `ApplicationStartedEvent` | Có | Đã refresh | Có theo context thành công | Chưa | Chưa |
| `ApplicationRunner / CommandLineRunner` | Có | Đã refresh | Có | Đang chạy | Chưa theo Boot ready |
| `ApplicationReadyEvent` | Có | Đã refresh | Có | Đã chạy xong theo đường thành công | Đang được công bố |
| `ReadinessState.ACCEPTING_TRAFFIC` | Có | Đã refresh | Có | Đã xong | Có |
| `ContextClosedEvent` | Có thể còn tham chiếu | Đang đóng | Có thể đang destroy | Đã kết thúc hoặc bị dừng | Không còn nhận traffic |

**Không xem bảng này là một API cho phép truy cập mọi bean tại mọi mốc.** Bean lazy có thể chưa tạo ngay cả sau refresh; các clients bên ngoài có thể chưa khỏe; và trạng thái readiness có thể thay đổi sau startup.

## 16. Khi một listener bị chậm, thứ tự vẫn đúng nhưng thời gian tăng

Trong Spring event publishing mặc định, phần lớn listeners được gọi đồng bộ trong thread phát event. Nếu một listener `ApplicationStartedEvent` thực hiện request mạng 10 giây, các bước phía sau **có thể bị trì hoãn**.

Một anti-pattern:

```java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    remoteApi.callAndWaitWithoutTimeout();
}
```

Đây là snippet phản ví dụ, `remoteApi` là service tự định nghĩa; không phải mã chạy độc lập.

**Hướng phù hợp:**

- Nếu công việc **bắt buộc trước ready**, đặt trong một runner có timeout, failure policy và logs rõ ràng.
- Nếu công việc **không bắt buộc**, có thể chạy bằng managed executor sau khi app ready theo thiết kế và không làm chậm event dispatcher.
- Nếu cần durable processing, dùng queue/job framework, không chỉ fire-and-forget trong listener.
- Nếu cần đo thời gian chi tiết, thêm `ApplicationStartup` steps, metrics hoặc trace; đừng chỉ suy từ một vài mốc.

### 16.1. @Async thay đổi khả năng suy luận order

Khi `@Async` hoặc custom asynchronous `ApplicationEventMulticaster` được bật, callback có thể chạy ở thread khác. Thời điểm một callback bắt đầu/kết thúc không còn mặc nhiên theo thứ tự dòng code ở publisher. Test cần latch, futures hoặc synchronization cụ thể, không chỉ so sánh console output.

### 16.2. Không dùng sleep để tạo ra “thứ tự”

Thêm `Thread.sleep(100)` vào listener để “ép dòng A in trước B” không sửa nguyên nhân race. Hãy thiết kế thông điệp và lifecycle đúng, dùng `Ordered` cho listener cùng event hoặc đồng bộ hóa rõ nếu có multiple threads.

## 17. Tình huống có nhiều contexts và event truyền lên parent

Spring cho phép parent/child `ApplicationContext`. Một event phát ở child có thể được truyền lên listeners của parent. Do đó:

- Parent listener có thể nhận nhiều `ContextRefreshedEvent`.
- Cùng một event type không có nghĩa đến từ cùng context.
- Khi cần chỉ xử lý event của context sở hữu, kiểm tra `event.getApplicationContext() == owningContext`.
- Listener sớm được đăng ký trên nhiều `SpringApplication` có thể báo trùng nếu không phân biệt ứng dụng/context nguồn.

Demo có **một context duy nhất**, nên timeline dự kiến không có duplicate từ hierarchy. Nếu chuyển bài sang một service có parent-child contexts, cần thêm context identity vào marker, hoặc filter theo origin.

### 17.1. Không gọi close trên parent chỉ vì child closed

Một listener nhận `ContextClosedEvent` từ child không được tự đóng `DataSource` của parent. Resource thuộc context nào thì context/owner đó quản lý lifecycle. Dùng event để quan sát và điều phối đúng phạm vi, không biến listener thành một owner thứ hai không kiểm soát.

## 18. Đo thời gian mà không nhầm với thứ tự

Ví dụ chính chỉ ghi **thứ tự tương đối**. Nó không đo duration từng phase.

Nếu muốn thời gian thực thi:

- Ghi `System.nanoTime()` ở đầu/cuối operation muốn đo, không dùng `currentTimeMillis` cho monotonic duration.
- Dùng `ApplicationStartup` và `StartupStep` của Spring Framework để đo những phases có instrumentation.
- Dùng `BufferingApplicationStartup` và Actuator startup endpoint nếu đã cấu hình trước `run`.
- Đối chiếu `application.started.time` với `application.ready.time` để thấy tổng thời gian đến các mốc.
- Dùng JFR/profiler khi cần biết CPU, I/O, locks, allocations và GC.

### 18.1. Không cộng thời gian startup steps bừa bãi

Các `StartupStep` có thể lồng nhau; nếu cộng duration của parent và child sẽ đếm lặp thời gian. Timeline theo mốc trong bài giúp kiểm tra **order**, còn một trace đầy đủ có id/parentId/timing mới giúp định vị bottleneck.

### 18.2. Có phải mọi lần Boot có đúng 16 sự kiện?

Không. **16 marker** là số điểm chúng ta chủ động ghi trong đường demo cụ thể, bao gồm hai marker tự thêm ở main và một marker initializer. Framework có thể phát nhiều events khác mà bài không ghi; khi thêm web server, listeners, failure modes hoặc context hierarchy, số marker thay đổi.

Tập trung vào **ràng buộc thứ tự** hơn là con số cố định khi đưa nguyên lý vào dự án thực.

## 19. Một thí nghiệm trước–sau khi thay đổi cấu hình

### Bản A: đúng đường mặc định

- Initializer thêm property default `observed`.
- Early listener ghi các Spring Boot events.
- Context listener ghi refresh/closed.
- Runner order 10 rồi 20.
- Ready phát sau runners.

Kết quả: timeline của phần 7.

### Bản B: đổi property qua CLI

- Không sửa code.
- Chạy `--demo.mode=fast`.
- Initializer đọc `fast` thay vì `observed` do precedence.
- Hai runner cũng đọc `fast`.

Kết quả: thứ tự không đổi; **giá trị marker** thay đổi.

### Bản C: đảo runner order

- Đổi `getOrder()` thành giá trị phân biệt ngược lại.
- Kiểm tra runner 20 có chạy trước runner có priority thấp hơn.
- Giữ các marker ApplicationStarted và ApplicationReady làm hai cột mốc.

Kết quả: **các runner đảo vị trí trong khoảng started → ready**.

### Bản D: runner ném exception

- Cho runner ném exception có chủ đích.
- Quan sát `ApplicationFailedEvent`.
- Không suy luận `ApplicationReadyEvent` đã được phát.
- Xử lý/report failure thay vì nuốt lỗi.

Kết quả: **đường startup thành công bị cắt ngắn**; nếu cần log timeline của failure phải xử lý recorder độc lập với return thành công của `run`.

### Bản E: chuyển một handler sang @Async

- Một callback có thể chạy đồng thời với các mốc khác.
- Console output có thể xen kẽ.
- Test containsSubsequence đồng bộ có thể không còn đủ.

Kết quả: phải phân biệt **thứ tự publish event** với **thời điểm handler hoàn thành**.

## 20. Lỗi phổ biến trong bài thực hành

| Hiểu nhầm hoặc lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Initializer chạy sau bean @PostConstruct | Initializer chạy trước refresh | Đặt logic tùy chỉnh environment ở initializer |
| @Component listener luôn bắt ApplicationStartingEvent | Bean chưa có khi event phát | Đăng ký bằng `addListeners` trước `run` |
| ApplicationStartedEvent đồng nghĩa app ready | Runners chưa chạy | Chờ `ApplicationReadyEvent`/readiness |
| ApplicationRunner luôn chạy trước CommandLineRunner | Cả hai dùng ordering | Dùng `Ordered`/@Order |
| Gán order bằng nhau rồi đòi một thứ tự cố định | Không có hợp đồng rõ | Đặt order phân biệt |
| @EventListener trên new object tự hoạt động | Object chưa vào Spring context | Đăng ký bean hoặc listener tường minh |
| ContextRefreshedEvent do Boot phát sau runners | Refresh xảy ra trước started | Đặt mốc đúng sơ đồ |
| Readiness accepting xảy ra trước runner | Boot công bố sau ready event | Thực hiện công việc bắt buộc trong runner |
| Gọi System.exit trong listener | Cắt ngang lifecycle/JUnit | Để entrypoint quản lý JVM |
| Dùng context.getBean trong initializer tùy ý | Context chưa refresh | Chỉ cấu hình context hoặc bean definitions hợp lệ |
| In logs đa luồng rồi suy chắc thứ tự | Interleaving/async làm sai diễn giải | Recorder hoặc test synchronization |
| Quên close context trong non-web demo | Resource có thể chưa cleanup | `context.close()`/try-with-resources |
| Dùng println trong mọi event của production | Nhiễu, tốn tài nguyên, có thể lộ dữ liệu | Structured logs/metrics có kiểm soát |
| Mở DB connection trong early listener | Infrastructure chưa sẵn sàng | Chuyển việc sang đúng lifecycle phase |
| Runner sleep vô hạn | App không ready | Timeout/cancel/failure policy |
| Nuốt exception trong runner | App có thể ready dù chưa an toàn | Fail-fast cho công việc bắt buộc |
| Nhầm ContextClosedEvent với mọi resource đã destroy | Event là giai đoạn đóng | Test resource sau close |
| Coi default MapPropertySource như source ưu tiên cao | `addLast` là ưu tiên thấp | Hiểu property precedence |
| Thêm web starter rồi mong timeline y hệt | Có thêm web events/beans | So sánh mốc cốt lõi, không đóng cứng mọi dòng |
| Unit test listener trực tiếp = production wiring đúng | Không kiểm tra registration | Một integration test `SpringApplication` |
| Nhiều contexts nhưng không filter source | Có thể nhận trùng từ child | Dùng context identity |
| Static timeline dùng cho parallel tests | State chia sẻ và bị race | Tạo recorder theo context/test |
| Event listener báo READY bằng cách bắt ContextRefreshed | Runner còn chưa hoàn thành | Dùng đúng ApplicationReady/availability |
| Thay đổi phase bằng @Order trên listener | @Order chỉ quyết định cùng một event | Dựa lifecycle của event source |

## 21. Checklist trước khi dùng extension point trong dự án thật

1. Xác định việc cần làm **trước refresh**, **sau refresh**, **trước ready** hay **sau ready**.
2. Chọn đúng API: initializer, listener, runner hoặc managed lifecycle component.
3. Early event listener được đăng ký trước `SpringApplication.run`.
4. Không autowire bean nghiệp vụ trong listener chạy trước context.
5. Initializer thao tác context/environment phù hợp giai đoạn trước refresh.
6. Property source được thêm với precedence có chủ đích.
7. Tránh mở tài nguyên có side effects trong initializer nếu không có owner cleanup.
8. Dùng bean `@EventListener` cho events sau khi annotation infrastructure đã sẵn sàng.
9. Nếu hai runners phụ thuộc thứ tự, dùng `Ordered`/@Order với giá trị phân biệt.
10. Không cho runner block vô hạn nếu readiness phụ thuộc nó.
11. Runner quan trọng gặp lỗi phải có failure policy rõ ràng.
12. Không gọi `System.exit` trong listener/runner chỉ để ép thứ tự.
13. Phân biệt `ApplicationStartedEvent` và `ApplicationReadyEvent`.
14. Đo liveness và readiness bằng đúng trạng thái/endpoint, không tự suy từ print log.
15. Không giữ BeanFactory hoặc context sau khi đã close.
16. Khi dùng async dispatch, test bằng synchronization, không tin thứ tự console.
17. Khi context hierarchy tồn tại, filter events theo owning context.
18. Resource có managed shutdown/destroy callback.
19. Tránh lộ secret trong event tags/log.
20. Test logic initializer riêng với `GenericApplicationContext` khi có thể.
21. Test bean listener wiring bằng context nhỏ hoặc `@EventListener` test phù hợp.
22. Giữ một integration test non-web kiểm tra thứ tự lifecycle quan trọng.
23. Khi chuyển sang web app, kiểm tra bổ sung `WebServerInitializedEvent`/readiness.
24. Không coi một lần chạy trên laptop là bằng chứng hiệu năng startup production.
25. Document thứ tự các mốc và vai trò của chúng cho người bảo trì.

## 22. Câu hỏi tự kiểm tra

**1. Initializer chạy trước hay sau ApplicationContextInitializedEvent?**

Trước. Boot phát `ApplicationContextInitializedEvent` sau khi đã áp dụng các `ApplicationContextInitializer` lên context.

**2. ApplicationStartingEvent có thể bắt bằng @Bean listener thông thường không?**

Không nên trông chờ vì event phát trước khi context/bean definitions sẵn sàng. Đăng ký sớm bằng `SpringApplication.addListeners` hoặc cơ chế đăng ký tương ứng của Boot.

**3. ContextRefreshedEvent có nghĩa runners đã chạy xong không?**

Không. Context refresh trước `ApplicationStartedEvent` và trước runners.

**4. ApplicationStartedEvent và ApplicationReadyEvent khác nhau thế nào?**

Started đến sau refresh nhưng trước runners; Ready đến sau các runners chạy thành công.

**5. Hai runner triển khai hai interface khác nhau có xếp thứ tự được không?**

Có. Boot sắp xếp `ApplicationRunner` và `CommandLineRunner` bằng Spring ordering; `Ordered`/@Order cho độ ưu tiên.

**6. @EventListener bean sẽ nhận được ApplicationStartingEvent nếu chỉ tạo sau refresh chứ?**

Không. Event sớm không được phát lại chỉ vì sau đó bean được tạo.

**7. Vì sao demo không có WebServerInitializedEvent?**

Vì dùng `WebApplicationType.NONE` và không mở embedded web server.

**8. Thấy LivenessState.CORRECT thì đã ready chưa?**

Chưa. Boot còn có thể đang chạy runners và chưa phát readiness accepting.

**9. Nếu runner ném exception thì ApplicationReadyEvent có chắc được phát không?**

Không theo đường startup thành công. Boot chuyển sang xử lý lỗi khởi động.

**10. Khi muốn test property default của initializer, có phải boot cả ứng dụng không?**

Không. Dùng `GenericApplicationContext` chưa refresh và gọi `initialize(context)` trực tiếp.

**11. Vì sao println sau context.close còn chạy trong demo?**

Vì `context.close()` đóng Spring context chứ không tự gọi `System.exit`, còn `main` vẫn tiếp tục thực thi.

**12. Với custom ApplicationEventMulticaster bất đồng bộ, timeline có còn là thứ tự hoàn tất listener tuyệt đối không?**

Không. Phải dùng synchronization/await để kiểm tra callback completion và phân biệt publish order với finish order.

## 23. Kết luận và sơ đồ nhớ nhanh

```text
           SpringApplication.run
                    |
     +--------------+--------------+
     |                             |
  EARLY LISTENER                ENVIRONMENT
  starting / env                   |
  prepared                         |
                                   v
                              INITIALIZER
                            (trước refresh)
                                   |
                                   v
                          CONTEXT INITIALIZED
                                   |
                                   v
                             PREPARED
                                   |
                                   v
                             REFRESH
                                   |
                        ContextRefreshedEvent
                                   |
                                   v
                       ApplicationStartedEvent
                                   |
                        LivenessState.CORRECT
                                   |
                                   v
                      Ordered runners 10 -> 20
                                   |
                                   v
                        ApplicationReadyEvent
                                   |
                      ReadinessState.ACCEPTING
                                   |
                                   v
                             run() return
                                   |
                              context.close
                                   |
                        ContextClosedEvent
```

**Ghi nhớ:** initializer để cấu hình context **trước refresh**; listener để **quan sát** lifecycle events (đăng ký sớm nếu cần early events); runner để chạy công việc **sau refresh nhưng trước ready**. Đặt thứ tự runner rõ bằng `Ordered`, ghi các mốc trong cùng recorder, và quan sát `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → readiness accepting. Một bài thực hành non-web có thể chứng minh những quan hệ này mà không cần mở database hoặc HTTP server, nhưng khi triển khai thực tế vẫn phải kiểm tra những tác động của async listeners, context hierarchy và resource ownership.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API: addInitializers, addListeners và run](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationContextInitializedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot 3.3 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.3 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — Application Events: @EventListener](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Boot 3.3 — Testing and ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html)
