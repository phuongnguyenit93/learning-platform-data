# Kiểm thử init, runner, sự kiện và giải phóng tài nguyên

Một ứng dụng Spring Boot không chỉ có API hoặc service xử lý nghiệp vụ. Trước khi sẵn sàng phục vụ, ứng dụng phải **tạo bean, thiết lập các thành phần hạ tầng, thực thi tác vụ khởi động và phát các sự kiện vòng đời**. Khi dừng, nó cần ngừng nhận công việc mới rồi **giải phóng kết nối, thread, executor và các tài nguyên được quản lý**.

Các lỗi trong những giai đoạn này có thể không xuất hiện trong một unit test nghiệp vụ thông thường. Ví dụ:

- Một bean chỉ chạy đúng trong IDE vì `@PostConstruct` phụ thuộc vào file cục bộ.
- Một `ApplicationRunner` có tồn tại trong context nhưng không thực sự được gọi bởi một context test nhỏ.
- Một listener không nhận `ApplicationReadyEvent` vì được đăng ký sau khi Boot đã phát sự kiện.
- Một runner khởi chạy task async và trả về ngay, khiến Boot báo ready khi dữ liệu chưa chuẩn bị xong.
- Một singleton không đóng thread pool khi context bị đóng.
- Một phép thử mong `@PreDestroy` chạy sau mỗi `@Test`, nhưng Spring vẫn giữ context trong cache.

Bài học **Spring Boot Fundamentals → Kiểm thử nền tảng → Kiểm thử init, runner, sự kiện và giải phóng tài nguyên** tập trung vào cách tổ chức những phép thử có mục đích rõ ràng: kiểm tra chính xác vòng đời bean, runners, sự kiện khởi động, đường thất bại và shutdown.

## 1. Bản đồ vòng đời cần kiểm thử

Một lần khởi động thành công thường có các mốc khái quát:

~~~text
SpringApplication.run(args)
         |
         v
Chuẩn bị Environment
         |
         v
Tạo và refresh ApplicationContext
         |
         +-- Tạo các singleton eager
         +-- Inject dependencies
         +-- @PostConstruct / InitializingBean
         +-- @Bean(initMethod = ...)
         +-- SmartLifecycle.start()
         |
         v
ApplicationStartedEvent
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent
         |
         v
Công bố readiness chấp nhận traffic
         |
         v
Ứng dụng hoạt động
         |
         v
Đóng ApplicationContext
         |
         +-- ContextClosedEvent
         +-- SmartLifecycle.stop(...)
         +-- @PreDestroy / DisposableBean / destroy method
         |
         v
Tài nguyên được giải phóng
~~~

Sơ đồ chỉ mô tả các mốc chính của đường khởi động và shutdown thông thường. Chi tiết về callback, listener, bean scopes, context hierarchy và luồng chạy phụ thuộc cấu hình thực tế.

Một số điểm rất quan trọng:

1. **Bean đã init không có nghĩa runner đã chạy.**
2. **Context đã refresh không có nghĩa Spring Boot đã phát ApplicationReadyEvent.**
3. **ApplicationReadyEvent không tự bảo đảm các công việc bất đồng bộ đã hoàn tất.**
4. **ContextClosedEvent không phải dấu hiệu tất cả destroy callbacks đã kết thúc.**
5. **Tạo object bằng `new` không làm Spring tự gọi lifecycle callback của object ấy.**

Kiểm thử đúng cần chọn điểm quan sát tương ứng với điều muốn chứng minh.

## 2. Chọn cấp độ kiểm thử phù hợp

| Mục tiêu | Harness phù hợp | Không nên mặc định |
|---|---|---|
| Logic thuần của runner, init hoặc cleanup | JUnit 5 unit test | Phải tạo toàn bộ Spring context |
| Bean init, dependency injection, destroy callback | `AnnotationConfigApplicationContext` hoặc `ApplicationContextRunner` | Context test nhỏ tự chạy các Boot runners |
| Điều kiện đăng ký bean, auto-configuration | `ApplicationContextRunner` | Cần web server thật |
| Runner thực sự chạy trong startup | `SpringApplication` hoặc `@SpringBootTest` | Bean tồn tại đồng nghĩa runner đã chạy |
| Boot startup events | Listener đăng ký sớm trước `SpringApplication.run(...)` | Listener tạo trong `@Test` nhận được event startup đã phát |
| Cleanup tại thời điểm xác định | Test tự tạo và chủ động `context.close()` | Spring TestContext đóng context sau từng method |
| Readiness, graceful shutdown, process exit | Integration/system test | Unit test là đủ để chứng minh hành vi triển khai |

Một test rộng có thể gần sản phẩm thật nhưng chậm và khó kiểm soát. Một test nhỏ có thể rất nhanh nhưng chỉ chứng minh một hợp đồng hẹp. **Nên có nhiều lớp test bổ sung nhau thay vì nhồi mọi điều kiện vào một `@SpringBootTest`.**

## 3. Thư viện kiểm thử Spring Boot

Trong Maven, nếu dự án sử dụng cơ chế quản lý phiên bản Spring Boot phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Starter test thường cung cấp JUnit Jupiter, Spring Test, AssertJ và các thư viện hữu ích khác; thành phần cụ thể phụ thuộc phiên bản Boot và cấu hình dự án.

Trong các ví dụ, ta sử dụng JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
~~~

Đối với Spring Boot 3.x, `@PostConstruct` và `@PreDestroy` dùng namespace `jakarta.annotation`. Những dự án Spring Boot cũ hơn có thể có namespace khác; cần sử dụng đúng hệ thư viện của project.

## 4. Kiểm thử @PostConstruct và @PreDestroy trên bean thực

Ta tạo một bean đơn giản có thể quan sát số lần init và destroy.

File `LifecycleProbe.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class LifecycleProbe {

    private final String requiredValue;
    private final AtomicInteger initCalls = new AtomicInteger();
    private final AtomicInteger destroyCalls = new AtomicInteger();

    public LifecycleProbe(String requiredValue) {
        this.requiredValue = requiredValue;
    }

    @PostConstruct
    public void initialize() {
        if (requiredValue == null || requiredValue.isBlank()) {
            throw new IllegalArgumentException(
                    "requiredValue must be configured");
        }
        initCalls.incrementAndGet();
    }

    @PreDestroy
    public void destroy() {
        destroyCalls.incrementAndGet();
    }

    public int initCount() {
        return initCalls.get();
    }

    public int destroyCount() {
        return destroyCalls.get();
    }
}
~~~

File `LifecycleConfiguration.java`:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean
    LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe("configured");
    }
}
~~~

Ta chủ động tạo và đóng context trong test:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleProbeTest {

    @Test
    void callsInitOnRefreshAndDestroyOnClose() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        LifecycleProbe probe = null;

        try {
            context.register(LifecycleConfiguration.class);
            context.refresh();

            probe = context.getBean(LifecycleProbe.class);

            assertEquals(1, probe.initCount());
            assertEquals(0, probe.destroyCount());
        } finally {
            context.close();
        }

        assertEquals(1, probe.destroyCount());
    }
}
~~~

Đây là **context-level test**. Spring thực sự tạo bean, xử lý annotation init và đóng bean lúc hủy context.

### Test này chứng minh điều gì?

- Một singleton bean đã được container khởi tạo.
- `@PostConstruct` đã chạy trước khi bean được dùng.
- `@PreDestroy` chưa chạy khi context còn mở.
- Sau khi `context.close()` hoàn tất, callback hủy đã chạy.

### Test này chưa chứng minh điều gì?

- `ApplicationRunner` đã chạy.
- `ApplicationReadyEvent` đã được phát.
- Web server đang phục vụ request.
- Tác vụ async do bean tự submit đã hoàn tất.
- Tài nguyên bên ngoài thật sự đã ngừng hoạt động nếu callback chỉ đặt một cờ.

Để chứng minh các điều đó cần thêm những test khác.

## 5. @PostConstruct khác với một lần gọi method Java thường

Nếu test viết:

~~~java
LifecycleProbe probe = new LifecycleProbe("configured");
probe.initialize();

assertEquals(1, probe.initCount());
~~~

nó chỉ xác nhận method `initialize()` làm điều đã lập trình. Spring không tham gia. Vì thế, test không phát hiện lỗi quên đăng ký bean, cấu hình annotation processing hoặc bean bị tạo ngoài container.

Hai kiểu test có vai trò khác nhau:

- Unit test direct method giúp kiểm tra logic init thuần.
- Context-level test giúp kiểm tra **framework wiring và lifecycle**.

Một hàm init phức tạp nên được tách thành method có thể kiểm thử thuần, còn annotation chỉ đóng vai trò gọi logic đó:

~~~java
@PostConstruct
void initialize() {
    validateConfiguration();
}

void validateConfiguration() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException(
                "Missing endpoint");
    }
}
~~~

Tránh đẩy các thao tác mạng lớn, migration hay tải dữ liệu kéo dài vào `@PostConstruct` nếu bài toán có thể dùng runner, task chuyên biệt hoặc một trạng thái readiness rõ ràng hơn.

## 6. Kiểm thử init thất bại bằng ApplicationContextRunner

`ApplicationContextRunner` là tiện ích hữu ích khi cần khởi tạo một context nhỏ, xem bean và quan sát lỗi. Nó tạo context phục vụ mỗi callback và quản lý việc đóng context sau khi callback kết thúc.

Một bean cố tình thất bại:

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;

public class BrokenBean {

    @PostConstruct
    void init() {
        throw new IllegalStateException(
                "simulated initialization failure");
    }
}
~~~

Test:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class BrokenBeanTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BrokenConfig.class);

    @Test
    void reportsFailureWhenInitThrows() {
        runner.run(context -> {
            assertNotNull(context.getStartupFailure());
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfig {

        @Bean
        BrokenBean brokenBean() {
            return new BrokenBean();
        }
    }
}
~~~

`context.getStartupFailure()` cho phép quan sát exception trong quá trình dựng context. Có thể kiểm tra cause chain khi muốn khẳng định nguyên nhân là một lỗi cụ thể.

**Giới hạn quan trọng:** `ApplicationContextRunner` không tự gọi các `ApplicationRunner` và `CommandLineRunner` như một lần chạy `SpringApplication.run(...)`. Vì vậy, startup failure của context runner không tự đồng nghĩa đã có `ApplicationFailedEvent` do Spring Boot phát.

## 7. Kiểm thử các cơ chế init khác

Ngoài `@PostConstruct`, Spring còn có các callback:

| Cơ chế | Ý nghĩa | Hướng test |
|---|---|---|
| Constructor | Khởi tạo object Java | Unit test |
| `@PostConstruct` | Callback sau injection | Context-level test |
| `InitializingBean.afterPropertiesSet()` | Callback của Spring sau khi điền thuộc tính | Context-level test |
| `@Bean(initMethod="...")` | Method init khai báo ở bean definition | Context-level test |
| `SmartLifecycle.start()` | Bắt đầu vận hành khi lifecycle processor start bean | Context-level test |
| `ApplicationRunner.run(...)` | Tác vụ sau context refresh trong Boot startup | Unit test hoặc full Boot startup test |

Ví dụ `InitializingBean`:

~~~java
public class EndpointValidator
        implements InitializingBean {

    private final String endpoint;

    public EndpointValidator(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public void afterPropertiesSet() {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException(
                    "endpoint is required");
        }
    }
}
~~~

Ví dụ `@Bean(initMethod)`:

~~~java
@Bean(initMethod = "warmUp")
SearchIndex searchIndex() {
    return new SearchIndex();
}
~~~

`SearchIndex` là type giả định có method `warmUp()`. Muốn kiểm tra Spring đã gọi callback, hãy dùng context-level test với bean definition trên.

Không nên tùy tiện chồng nhiều cơ chế init lên cùng một bean. Việc có **một owner và một hợp đồng init rõ ràng** giúp code dễ đọc, test dễ hiểu hơn.

## 8. Unit test ApplicationRunner

`ApplicationRunner` nhận `ApplicationArguments` và thường dùng cho các tác vụ sau khi context đã refresh.

Ví dụ một runner chỉ chuyển mode tới service:

~~~java
package com.example.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;

public class StartupModeRunner implements ApplicationRunner {

    public interface ModeTask {
        void execute(String mode);
    }

    private final ModeTask task;

    public StartupModeRunner(ModeTask task) {
        this.task = task;
    }

    @Override
    public void run(ApplicationArguments args) {
        String mode = resolveMode(args);
        task.execute(mode);
    }

    static String resolveMode(ApplicationArguments args) {
        if (!args.containsOption("mode")) {
            return "normal";
        }

        List<String> values = args.getOptionValues("mode");

        if (values == null || values.isEmpty() ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "--mode requires a value");
        }

        return values.get(0);
    }
}
~~~

`ModeTask` được giữ thành interface để dễ thay bằng fake trong unit test.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StartupModeRunnerTest {

    @Test
    void passesModeToTask() throws Exception {
        AtomicReference<String> actual =
                new AtomicReference<>();

        StartupModeRunner runner =
                new StartupModeRunner(actual::set);

        runner.run(new DefaultApplicationArguments(
                "--mode=safe"));

        assertEquals("safe", actual.get());
    }

    @Test
    void defaultsWhenModeIsAbsent() throws Exception {
        AtomicReference<String> actual =
                new AtomicReference<>();

        StartupModeRunner runner =
                new StartupModeRunner(actual::set);

        runner.run(new DefaultApplicationArguments());

        assertEquals("normal", actual.get());
    }

    @Test
    void rejectsMissingModeValue() {
        StartupModeRunner runner =
                new StartupModeRunner(mode -> { });

        assertThrows(
                IllegalArgumentException.class,
                () -> runner.run(
                        new DefaultApplicationArguments("--mode"))
        );
    }
}
~~~

Các test này chứng minh runner xử lý input và gọi dependency đúng. Chúng **không chứng minh Spring Boot thực sự phát hiện và gọi runner khi startup**; test tích hợp tiếp theo giải quyết điều đó.

### Khi nào nên unit test trực tiếp?

- Parse `ApplicationArguments`.
- Validation của startup option.
- Gọi service đúng thứ tự trong code runner.
- Xử lý exception hoặc fallback.
- Thử logic với fake thay vì database/network thật.

Tách logic khỏi framework giúp những phép thử này chạy nhanh và xác định.

## 9. Unit test CommandLineRunner

`CommandLineRunner` nhận trực tiếp mảng `String... args`:

~~~java
package com.example.startup;

import org.springframework.boot.CommandLineRunner;

public class ArgumentCountRunner
        implements CommandLineRunner {

    private final java.util.function.IntConsumer sink;

    public ArgumentCountRunner(
            java.util.function.IntConsumer sink
    ) {
        this.sink = sink;
    }

    @Override
    public void run(String... args) {
        sink.accept(args.length);
    }
}
~~~

Test:

~~~java
@Test
void countsRawArguments() throws Exception {
    AtomicInteger actual = new AtomicInteger(-1);

    ArgumentCountRunner runner =
            new ArgumentCountRunner(actual::set);

    runner.run("--verbose", "source.csv");

    assertEquals(2, actual.get());
}
~~~

Hai loại runner đều có thể tham gia startup Spring Boot, nhưng **`ApplicationRunner` nhận đối tượng `ApplicationArguments`**, còn **`CommandLineRunner` nhận chuỗi đối số thô**.

Với chương trình CLI có nhiều option, `ApplicationRunner` thường tiện hơn. Với cú pháp dòng lệnh đơn giản, `CommandLineRunner` cũng phù hợp.

## 10. Tích hợp: xác nhận Boot thực sự gọi runner

Một test `@SpringBootTest` có thể khởi động một cấu hình nhỏ và xác nhận runner đã thực thi.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = RunnerBootTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RunnerBootTest {

    @Autowired
    Counter counter;

    @Test
    void runnerIsCalledAtStartup() {
        assertEquals(1, counter.calls.get());
    }

    static class Counter {
        final AtomicInteger calls = new AtomicInteger();
    }

    @SpringBootConfiguration
    static class TestApplication {

        @Bean
        Counter counter() {
            return new Counter();
        }

        @Bean
        ApplicationRunner runner(Counter counter) {
            return args -> counter.calls.incrementAndGet();
        }
    }
}
~~~

Trên một context mới khởi động theo cơ chế của Spring Boot test, runner được gọi khi SpringApplication hoàn tất bước refresh và xử lý runners.

### Cẩn trọng với context caching

Spring TestContext có thể cache context giữa các test có cấu hình giống nhau:

- Không nên mặc định runner chạy một lần trước **mỗi method `@Test`**.
- Không nên mặc định `@PostConstruct` chạy lại với từng method.
- Một singleton mutable có thể giữ state từ phép thử trước.
- Context được cache cũng có thể khiến việc quan sát shutdown không xảy ra ở thời điểm `@AfterEach`.

Nếu test cần điều khiển chính xác **một lần start và một lần close**, dùng `SpringApplication` tự tạo trong test sẽ rõ ràng hơn.

## 11. Kiểm thử thứ tự các runners

Spring Boot có thể sắp runner dựa trên `@Order` hoặc `Ordered`.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class RunnerOrderingConfiguration {

    @Bean
    @Order(10)
    ApplicationRunner validateSchema(StepRecorder recorder) {
        return args -> recorder.record("schema");
    }

    @Bean
    @Order(20)
    CommandLineRunner loadCache(StepRecorder recorder) {
        return args -> recorder.record("cache");
    }
}
~~~

`StepRecorder` là bean minh họa:

~~~java
public final class StepRecorder {

    private final List<String> steps =
            new CopyOnWriteArrayList<>();

    public void record(String step) {
        steps.add(step);
    }

    public List<String> snapshot() {
        return List.copyOf(steps);
    }
}
~~~

Sau khi một lần Boot startup chạy thành công với cả hai runner, test có thể assert:

~~~java
assertEquals(
        List.of("schema", "cache"),
        recorder.snapshot()
);
~~~

Lưu ý:

- `@Order` phản ánh **thứ tự gọi runner**, không phải thứ tự tạo bean.
- Với hai runner cùng một thứ tự, không nên dựa vào một trình tự ngầm.
- Nếu runner đầu khởi động một thread nền rồi trả về, không bảo đảm thread đó xong trước khi runner thứ hai chạy.
- Nếu hai tác vụ thật sự có dependency, cấu trúc phối hợp tường minh thường tốt hơn nhiều runner có thứ tự phụ thuộc vào side effect.

## 12. Kiểm thử runner thất bại

Nếu runner xác nhận một tài nguyên bắt buộc bị thiếu, startup có thể cần thất bại thay vì tiếp tục phục vụ ở trạng thái sai:

~~~java
@Bean
ApplicationRunner verifyCatalog() {
    return args -> {
        throw new IllegalStateException(
                "Catalog is required before startup completes");
    };
}
~~~

Ở cấp unit test:

~~~java
@Test
void runnerPropagatesFailure() {
    ApplicationRunner runner = args -> {
        throw new IllegalStateException("missing catalog");
    };

    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> runner.run(
                    new DefaultApplicationArguments())
    );

    assertEquals("missing catalog", error.getMessage());
}
~~~

Bài test này chỉ chứng minh lời gọi runner ném lỗi. Để kiểm tra **`ApplicationFailedEvent`**, phải đi qua `SpringApplication.run(...)`.

Một integration test về failure cần kiểm tra:

1. Lỗi thoát khỏi runner.
2. `SpringApplication.run(...)` không hoàn thành thành công.
3. Listener được đăng ký từ trước nhận sự kiện failure.
4. Lỗi gốc không bị che bởi lỗi khác.
5. Các resource đã được container quản lý được cleanup theo hợp đồng tương ứng.

## 13. Sự kiện Spring Framework và Spring Boot

Các sự kiện thường gặp:

| Sự kiện | Thuộc | Khi nào dùng để quan sát |
|---|---|---|
| `ContextRefreshedEvent` | Spring Framework | Context vừa hoàn tất refresh |
| `ContextClosedEvent` | Spring Framework | Context bắt đầu đi vào quá trình đóng |
| `ApplicationStartedEvent` | Spring Boot | Context refresh xong, chuẩn bị chạy runners |
| `ApplicationReadyEvent` | Spring Boot | Runners đã kết thúc, Boot đi tới mốc ready |
| `ApplicationFailedEvent` | Spring Boot | Có lỗi làm startup do SpringApplication quản lý thất bại |
| `AvailabilityChangeEvent` | Spring Boot | Trạng thái availability thay đổi |

Điểm quan trọng đối với test:

- `AnnotationConfigApplicationContext.refresh()` có thể phát `ContextRefreshedEvent`.
- Lời gọi đó **không tự phát `ApplicationStartedEvent` hoặc `ApplicationReadyEvent`**.
- `context.close()` phát `ContextClosedEvent` và điều phối shutdown.
- `ApplicationFailedEvent` cần được kiểm tra bằng startup thất bại qua `SpringApplication`.

Một test dùng sai loại context có thể kết luận listener bị hỏng trong khi thực ra sự kiện đang cần chưa bao giờ được phát.

## 14. Test một event listener bằng cách publish event

Đối với một event nghiệp vụ không gắn với startup, có thể dùng context nhỏ.

Event:

~~~java
package com.example.events;

public record CatalogUpdatedEvent(int version) {
}
~~~

Listener:

~~~java
package com.example.events;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class CatalogListener {

    private final AtomicInteger lastVersion =
            new AtomicInteger(-1);

    @EventListener
    public void onCatalogUpdated(CatalogUpdatedEvent event) {
        lastVersion.set(event.version());
    }

    public int lastVersion() {
        return lastVersion.get();
    }
}
~~~

Test:

~~~java
@Test
void dispatchesBusinessEvent() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    try {
        context.registerBean(CatalogListener.class);
        context.refresh();

        context.publishEvent(new CatalogUpdatedEvent(7));

        assertEquals(
                7,
                context.getBean(CatalogListener.class)
                        .lastVersion()
        );
    } finally {
        context.close();
    }
}
~~~

Với multicaster đồng bộ mặc định, listener được gọi trong quá trình publish. Nếu ứng dụng cấu hình event multicaster async, test cần chờ theo một completion signal rõ ràng thay vì assert ngay.

Test này xác nhận **wiring và handler**, không chứng minh `ApplicationReadyEvent` được Boot phát vào đúng thời điểm.

## 15. @RecordApplicationEvents: nên dùng đúng mục đích

Spring Test cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để quan sát sự kiện được publish trong phạm vi thực thi test.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@RecordApplicationEvents
class CatalogEventRecordingTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    ApplicationEvents events;

    @Test
    void recordsEventPublishedInTest() {
        publisher.publishEvent(new CatalogUpdatedEvent(9));

        long count = events.stream(
                CatalogUpdatedEvent.class
        ).count();

        assertEquals(1, count);
    }
}
~~~

Ví dụ giả định class event và Spring Boot application phù hợp đã tồn tại.

**Giới hạn:** các sự kiện startup như `ApplicationStartedEvent` và `ApplicationReadyEvent` có thể đã được phát **trước khi method test bắt đầu**. Vì vậy, không nên mặc định `@RecordApplicationEvents` sẽ ghi lại đầy đủ những mốc startup của một cached `@SpringBootTest` context.

Muốn kiểm tra chúng, gắn listener trực tiếp **trước** khi `SpringApplication.run(...)` được gọi.

## 16. Test ApplicationStartedEvent, runner và ApplicationReadyEvent

Ví dụ một test tạo SpringApplication có cấu hình tối thiểu. Để test đơn giản, một recorder `static` được dùng trong **một test tuần tự**; khi bật test parallel, cần thay bằng recorder không chia sẻ state ngoài ý muốn.

~~~java
package com.example.startup;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StartupOrderIntegrationTest {

    private static final List<String> STEPS = new ArrayList<>();

    @Test
    void startedThenRunnerThenReady() {
        STEPS.clear();

        SpringApplication application =
                new SpringApplication(TestApp.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
            (ApplicationListener<ApplicationStartedEvent>)
                event -> STEPS.add("started"),
            (ApplicationListener<ApplicationReadyEvent>)
                event -> STEPS.add("ready")
        );

        try (ConfigurableApplicationContext context =
                application.run("--spring.main.banner-mode=off")) {

            assertEquals(
                List.of("started", "runner", "ready"),
                List.copyOf(STEPS)
            );
        }
    }

    @SpringBootConfiguration
    static class TestApp {

        @Bean
        ApplicationRunner recordRunner() {
            return args -> STEPS.add("runner");
        }
    }
}
~~~

Điểm bài test chứng minh:

- Listener được đăng ký trước startup.
- Boot đã phát started khi context refresh xong.
- Boot thực thi runner sau started.
- Boot phát ready sau runner khi startup thành công.

### Không nên dùng recorder static trong suite song song

Trong một suite lớn, có thể nhiều test cùng thao tác biến `static` làm kết quả không xác định. Cách chắc chắn hơn là dùng một recorder instance được inject vào configuration/runner và được test giữ reference, hoặc tách test process/class để loại shared state.

Quan trọng là **thứ tự quan hệ** được kiểm tra, không phải việc recorder dùng static hay bean.

## 17. Test ApplicationFailedEvent khi runner ném exception

Để thu được failure event, đăng ký listener sớm với `SpringApplication`.

~~~java
package com.example.startup;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.*;

class StartupFailureIntegrationTest {

    @Test
    void publishesFailedEventForRunnerException() {
        AtomicReference<Throwable> failure =
                new AtomicReference<>();

        SpringApplication application =
                new SpringApplication(FailingApp.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationFailedEvent>)
                    event -> failure.set(event.getException())
        );

        assertThrows(
                Exception.class,
                () -> application.run(
                        "--spring.main.banner-mode=off")
        );

        assertNotNull(failure.get());
    }

    @SpringBootConfiguration
    static class FailingApp {

        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "simulated startup failure");
            };
        }
    }
}
~~~

Test xác nhận `SpringApplication` xử lý lỗi và phát `ApplicationFailedEvent`. Exception bề ngoài có thể được wrapper; khi muốn kiểm tra lỗi gốc, nên xem chuỗi `getCause()` thay vì phụ thuộc quá chặt vào một lớp wrapper.

### Vì sao không dùng ApplicationContextRunner cho test này?

Vì `ApplicationContextRunner` không chạy toàn bộ đường startup của Boot và không gọi runners theo cùng cơ chế. Nó phù hợp để kiểm tra lỗi khởi tạo bean, **không tự chứng minh Boot startup failure event**.

### Vì sao không chỉ tạo một listener @Component?

Listener tạo từ bean có thể chưa tồn tại khi startup thất bại sớm. Với sự kiện lỗi khởi động, đăng ký trực tiếp vào SpringApplication từ trước là cách minh họa đáng tin cậy hơn.

## 18. Test ContextClosedEvent

`ContextClosedEvent` được publish khi context bắt đầu xử lý đóng.

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextClosedEvent;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextClosedEventTest {

    @Test
    void publishesCloseEvent() {
        AtomicInteger received = new AtomicInteger();

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.addApplicationListener(
            (ApplicationListener<ContextClosedEvent>)
                event -> received.incrementAndGet()
        );

        context.refresh();

        assertEquals(0, received.get());

        context.close();

        assertEquals(1, received.get());
    }
}
~~~

Phép thử này kiểm tra event. Nhưng **event được publish không đồng nghĩa tất cả bean đã chạy xong destroy callbacks**.

Một sơ đồ khái quát:

~~~text
context.close()
      |
      v
Publish ContextClosedEvent
      |
      v
Dừng lifecycle components
      |
      v
Destroy managed singleton beans
      |
      v
close() hoàn tất
~~~

Nếu cần kiểm tra resource đã đóng, hãy assert trạng thái đó **sau `context.close()`**, không phải ngay trong listener của `ContextClosedEvent`.

## 19. Những callback giải phóng tài nguyên phổ biến

| Cơ chế | Cách sử dụng | Điều cần quan sát |
|---|---|---|
| `@PreDestroy` | Method cleanup của bean | Method có được gọi trước khi bean bị hủy không? |
| `DisposableBean.destroy()` | Bean implement interface Spring | Destroy callback có thực hiện không? |
| `@Bean(destroyMethod="close")` | Factory method khai báo cleanup | Resource có được close khi context đóng không? |
| `AutoCloseable` / `Closeable` | Hợp đồng Java cho resource | Owner có đóng resource không? |
| `SmartLifecycle.stop(...)` | Dừng component đang chạy | Việc dừng và callback hoàn tất có đúng không? |
| `try-with-resources` | Resource scope ngắn | Stream/file/socket có đóng cả khi lỗi không? |

Một bean có thể dùng nhiều callback, nhưng nếu chúng cùng đóng một resource thì cần tránh double-close hoặc có thiết kế idempotency rõ ràng.

## 20. Test @Bean(destroyMethod) bằng fake resource

Ta tạo fake connection có cờ đóng:

~~~java
package com.example.resources;

import java.util.concurrent.atomic.AtomicBoolean;

public class FakeConnection implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    public boolean isClosed() {
        return closed.get();
    }

    public void send(String message) {
        if (closed.get()) {
            throw new IllegalStateException(
                    "Connection already closed");
        }
    }

    @Override
    public void close() {
        closed.set(true);
    }
}
~~~

Đăng ký bean với destroy method tường minh:

~~~java
package com.example.resources;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FakeConnectionConfiguration {

    @Bean(destroyMethod = "close")
    FakeConnection fakeConnection() {
        return new FakeConnection();
    }
}
~~~

Test:

~~~java
package com.example.resources;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ConnectionCleanupTest {

    @Test
    void closesResourceWhenContextCloses() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        FakeConnection resource;

        try {
            context.register(FakeConnectionConfiguration.class);
            context.refresh();

            resource = context.getBean(FakeConnection.class);

            assertFalse(resource.isClosed());
        } finally {
            context.close();
        }

        assertTrue(resource.isClosed());
    }
}
~~~

Phép thử có ý nghĩa hơn việc chỉ assert `@PreDestroy` tăng một counter: nó xác nhận resource giả đã chuyển sang trạng thái đóng.

### Chú ý về ownership

Nếu resource được tạo bởi Spring bean và do Spring sở hữu, không nhất thiết caller phải tự gọi `close()`. Ngược lại, nếu một method mượn hoặc tạo resource ngắn hạn, nó có thể phải tự đóng trong `try-with-resources`.

Không nên vừa để Spring đóng một resource vừa tự đóng cùng resource ở nhiều nơi mà không kiểm soát. Fake resource có thể ghi số lần close nếu muốn kiểm tra hợp đồng ownership.

## 21. DisposableBean và callback destroy

Spring có interface `DisposableBean`:

~~~java
public class DisposableWorker
        implements DisposableBean {

    private final AtomicBoolean destroyed =
            new AtomicBoolean();

    @Override
    public void destroy() {
        destroyed.set(true);
    }

    public boolean isDestroyed() {
        return destroyed.get();
    }
}
~~~

Nếu bean được container quản lý như singleton thông thường, Spring gọi `destroy()` khi bean được hủy trong quá trình đóng context.

Test tương tự:

~~~text
Tạo context
  -> đăng ký bean
  -> refresh
  -> assert isDestroyed() == false
  -> close
  -> assert isDestroyed() == true
~~~

Trong code thực tế, import `org.springframework.beans.factory.DisposableBean` và `java.util.concurrent.atomic.AtomicBoolean`.

`@PreDestroy`, `DisposableBean` và destroy method đều giải quyết nhóm bài toán cleanup nhưng khác cách khai báo. Chọn một cơ chế phù hợp với phong cách dự án và tính chất của resource.

## 22. SmartLifecycle: start và stop khác destroy

Một component có thể là consumer hoặc worker cần được **start** khi context sẵn sàng và **stop** khi shutdown.

`SmartLifecycle` cho phép Spring phối hợp start/stop theo phase.

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public class ControlledWorker implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public void stop(Runnable callback) {
        stop();
        callback.run();
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
~~~

Test:

~~~java
@Test
void workerStartsAndStopsWithContext() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(ControlledWorker.class);
    context.refresh();

    ControlledWorker worker =
            context.getBean(ControlledWorker.class);

    assertTrue(worker.isRunning());

    context.close();

    assertFalse(worker.isRunning());
}
~~~

### Tại sao stop(Runnable) cần gọi callback?

Với shutdown có phase, Spring dùng callback để biết một component đã dừng xong. Nếu logic dừng đồng bộ thì có thể gọi callback ngay sau stop. Nếu logic dừng bất đồng bộ, callback cần được gọi **khi việc dừng thật sự hoàn tất**, không phải lúc vừa submit yêu cầu dừng.

### Ý nghĩa phase

Thông thường:

- Startup: phase thấp được start trước phase cao.
- Shutdown: phase cao được stop trước phase thấp.

Khi một consumer phụ thuộc vào connection pool, cần xác định thứ tự để consumer dừng nhận việc trước khi resource nó cần bị đóng. Test có thể dùng recorder để xác nhận quan hệ thứ tự.

## 23. Test thứ tự cleanup với recorder

Một cách đơn giản là tạo recorder:

~~~java
public final class LifecycleRecorder {

    private final List<String> events =
            new CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Các bean ghi lại mốc:

~~~text
consumer-start
connection-open
consumer-stop
connection-close
~~~

Sau khi `context.close()` trả về, test có thể kiểm tra:

~~~java
List<String> timeline = recorder.snapshot();

assertTrue(timeline.contains("consumer-stop"));
assertTrue(timeline.contains("connection-close"));

assertTrue(
        timeline.indexOf("consumer-stop") <
        timeline.indexOf("connection-close")
);
~~~

Chỉ assert thứ tự nếu đó là **yêu cầu kiến trúc**. Không nên assert toàn bộ trình tự sự kiện nội bộ của Spring hoặc một thứ tự không được framework bảo đảm, vì test dễ gãy khi nâng version.

Quan trọng: `ContextClosedEvent` đến trước nhiều thao tác stop/destroy, nên không nên ghi `context-closed` và suy luận đó là marker cuối cùng trong timeline.

## 24. Bất đồng bộ và nguy cơ “runner xong nhưng việc chưa xong”

Xét runner:

~~~java
@Bean
ApplicationRunner prepareCatalog(
        Executor executor,
        CatalogService catalogService
) {
    return args -> {
        executor.execute(catalogService::prepare);
    };
}
~~~

`CatalogService` là service minh họa. Khi `executor.execute(...)` chấp nhận task, runner thường trả về ngay.

Hệ quả:

~~~text
ApplicationStartedEvent
        |
        v
Runner submit prepare()
        |
        v
Runner trả về
        |
        v
ApplicationReadyEvent
        |
        v
Task nền có thể vẫn đang chạy
~~~

Test chỉ kiểm tra `ApplicationReadyEvent` **không chứng minh task hoàn tất**.

Cần test riêng:

- Task có được submit không?
- Task hoàn tất thành công hay lỗi?
- Readiness có ở trạng thái không đạt khi task chưa xong không?
- Khi task thất bại, hệ thống retry hay fail-fast?
- Khi shutdown, task có được hủy hoặc chờ theo chính sách không?

### Dùng future hoặc latch thay Thread.sleep

Một interface có thể mô tả trạng thái hoàn thành:

~~~java
public interface CatalogPreparation {
    CompletableFuture<Void> prepareAsync();
}
~~~

Trong test dùng fake:

~~~java
CompletableFuture<Void> completion =
        new CompletableFuture<>();

// Fake prepareAsync() trả về completion.
CompletableFuture<Void> actual = fake.prepareAsync();

assertFalse(actual.isDone());

completion.complete(null);

assertTrue(actual.isDone());
~~~

`fake` chỉ là placeholder cho một test double cụ thể. Ý nghĩa là test **chủ động điều khiển completion** thay vì đợi một khoảng thời gian tùy ý.

Khi dùng `@Async`, nhớ rằng self-invocation trong cùng bean có thể bỏ qua Spring proxy và không chuyển sang thread khác. Một integration test nên xác nhận đường gọi qua proxy nếu tính bất đồng bộ là yêu cầu.

## 25. Test event listener bất đồng bộ

Nếu một listener dùng `@Async` hoặc ứng dụng cấu hình event multicaster async, `publishEvent(...)` có thể trả về trước khi listener xử lý xong.

Ví dụ:

~~~java
@Component
public class CatalogNotificationListener {

    private final CountDownLatch processed =
            new CountDownLatch(1);

    @Async
    @EventListener
    public void onCatalogUpdated(CatalogUpdatedEvent event) {
        try {
            // Xử lý event.
        } finally {
            processed.countDown();
        }
    }

    public boolean awaitProcessed(Duration timeout)
            throws InterruptedException {
        return processed.await(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS
        );
    }
}
~~~

Đoạn code giả định đã bật `@EnableAsync`, cấu hình executor và import những type liên quan. Nó minh họa cách ghi nhận event completion.

Test:

~~~java
publisher.publishEvent(new CatalogUpdatedEvent(11));

assertTrue(
        listener.awaitProcessed(Duration.ofSeconds(2))
);
~~~

Nếu listener có thể nhận nhiều event, latch một lần không đủ để phân biệt từng lần xử lý; có thể dùng counter, queue hoặc future gắn với event ID.

**Không nên sử dụng `Thread.sleep(500)` rồi assert**, vì kết quả sẽ phụ thuộc tốc độ CI hoặc tình trạng CPU, dẫn tới test không ổn định.

## 26. Test Context cache và @DirtiesContext

Spring TestContext cache context giữa các phép thử có cấu hình tương thích để tiết kiệm chi phí startup.

Hệ quả:

| Giả định sai | Hành vi có thể xảy ra |
|---|---|
| Mỗi `@Test` đều chạy `@PostConstruct` | Bean được tạo từ context cache trước đó |
| Mỗi test method đều gọi runner | Runner chỉ chạy khi Boot startup thực sự |
| `@AfterEach` đồng nghĩa context đã đóng | Context có thể tiếp tục nằm trong cache |
| Listener trong method thấy ready event | Event đã được phát trước khi method chạy |
| Singleton mutable tự reset giữa methods | Trạng thái có thể giữ lại |

`@DirtiesContext` có thể yêu cầu Spring loại context khỏi cache:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
@SpringBootTest
class SpecialIntegrationTest {
    // ...
}
~~~

Nhưng không nên lạm dụng:

- Làm suite chậm hơn vì context phải tạo lại.
- Không phải công cụ tốt nhất để xác nhận close trong **chính một method**.
- Có thể che một thiết kế test phụ thuộc shared mutable state.

Khi cần bảo đảm **create → refresh → assert → close → assert**, nên dùng context tự quản lý trong test.

## 27. Lưu ý về prototype, lazy bean và số lần init

Số lần lifecycle callback phụ thuộc bean scope và thời điểm tạo:

- Singleton eager thường được tạo một lần cho mỗi context.
- Lazy singleton có thể chưa init trước lần thực sự được dùng.
- Prototype có thể tạo instance mới mỗi lần yêu cầu.
- Parent/child contexts có thể phát event theo cấu trúc phân cấp.
- Context tạo mới sau khi đóng sẽ có instance bean mới.

Đặc biệt, **Spring không tự quản lý destroy lifecycle cho từng prototype instance như singleton thông thường**. Caller đã yêu cầu prototype resource cần xác định ownership và thực hiện cleanup phù hợp.

Vì vậy, khi assert `initCount() == 1` hoặc `destroyCount() == 1`, hãy nói rõ phạm vi: **một singleton trong một context mới do test tạo và đóng đúng một lần**.

Đừng biến điều kiện đúng trong test đó thành một quy tắc áp dụng cho mọi bean scope.

## 28. Nếu shutdown xảy ra khi khởi tạo dở dang?

Một lỗi khó là context tạo được một số bean rồi thất bại khi tạo bean tiếp theo:

~~~text
Create connection pool  -> success
Create catalog bean     -> success
Create payment client   -> failure
SpringApplication.run   -> failed
~~~

Trong tình huống đó, cần phân biệt:

1. Resource đã đăng ký thành bean được Spring quản lý.
2. Object mới được tạo cục bộ bên trong một factory method nhưng chưa được trả về thành bean.
3. Task async đã khởi chạy và nằm ngoài lifecycle của Spring.

Spring có cơ chế dọn các singleton đã tạo trong một lần context refresh thất bại. Nhưng nếu constructor hoặc factory method tự mở resource rồi ném exception trước khi resource trở thành bean được quản lý, **ứng dụng có thể phải tự đóng resource trong `try/finally`**.

Một test kiểm soát tốt có thể:

- Tạo fake resource có cờ closed.
- Đăng ký resource làm bean.
- Đăng ký bean tiếp theo ném exception khi init.
- Chạy context và xác nhận failure.
- Kiểm tra resource được cleanup theo hợp đồng.

Không nên khẳng định Spring có thể tự phát hiện và đóng mọi object được tạo bằng `new`, nhất là khi object chưa từng được đưa vào container.

## 29. Test cleanup thất bại và tính idempotent

Cleanup có thể thất bại do network, timeout hoặc resource đã được đóng trước đó.

Thiết kế cleanup cần xác định:

- Nếu gọi hai lần, thao tác có an toàn không?
- Nếu resource chưa init hoàn chỉnh, cleanup xử lý được không?
- Exception cleanup có cần log hay báo cáo không?
- Có cần timeout để không kẹt shutdown?
- Có cần flush/commit dữ liệu trước khi close không?
- Có cần stop task trước khi đóng dependency không?

Ví dụ:

~~~java
@PreDestroy
public void shutdown() {
    if (!closing.compareAndSet(false, true)) {
        return;
    }

    try {
        client.close();
    } catch (Exception error) {
        log.warn("Client shutdown was not clean", error);
    }
}
~~~

Các field `closing`, `client` và `log` thuộc implementation minh họa, không phải API Spring.

Không nên mặc định `context.close()` sẽ ném lại mọi exception trong `@PreDestroy`. Spring có thể ghi nhận và tiếp tục giải phóng các bean khác. Test nên kiểm tra hợp đồng thực sự của resource và cách lỗi được báo cáo, thay vì một wrapper exception nội bộ.

## 30. Giải phóng executor và thread

Một rủi ro phổ biến:

~~~java
public void process() {
    ExecutorService executor =
            Executors.newSingleThreadExecutor();

    executor.submit(this::doWork);

    // Không shutdown executor.
}
~~~

Mỗi lần gọi có thể tạo thread mới mà không có owner chịu trách nhiệm dừng.

Trong ứng dụng Spring Boot, có thể:

- Dùng executor bean được Spring quản lý.
- Khai báo destroy lifecycle phù hợp.
- Dừng tiếp nhận task mới khi shutdown.
- Chờ hoặc hủy các task đang chạy theo chính sách.
- Giới hạn thời gian chờ.
- Test bằng fake executor hoặc CompletionStage thay vì chỉ đoán thread đã ngừng.

Nếu dùng `SmartLifecycle` để dừng một consumer, cần gọi `stop(Runnable callback)` khi phần dừng thực sự hoàn tất. Nếu dùng executor có shutdown riêng, kiểm thử chính executor đã shutdown và những task quan trọng đã kết thúc/hủy.

**`context.close()` trả về không tự chứng minh mọi thread do ứng dụng tự tạo đã ngừng.**

## 31. Test bằng CountDownLatch thay vì sleep

Một công cụ Java hữu ích là `CountDownLatch`:

~~~java
public final class CloseSignal {

    private final CountDownLatch closed =
            new CountDownLatch(1);

    public void markClosed() {
        closed.countDown();
    }

    public boolean awaitClosed(Duration timeout)
            throws InterruptedException {

        return closed.await(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS
        );
    }
}
~~~

Sau khi yêu cầu shutdown:

~~~java
context.close();

assertTrue(
        closeSignal.awaitClosed(Duration.ofSeconds(2))
);
~~~

Lợi ích:

- Chờ đúng tín hiệu cần quan sát.
- Không lãng phí thời gian cố định nếu sự kiện xảy ra sớm.
- Có timeout hữu hạn nếu phần dừng bị treo.
- Test diễn đạt rõ hơn nghĩa của “đã đóng”.

Nếu cleanup đồng bộ, không cần latch; một assertion ngay sau close thường đơn giản và ổn định hơn.

## 32. @Timeout: tránh làm cả test suite bị treo

JUnit 5 có annotation `@Timeout`:

~~~java
@Test
@Timeout(5)
void startupCompletesWithinReasonableLimit() {
    // Khởi động context nhỏ với fake dependencies.
}
~~~

`@Timeout` không thay thế timeout của các HTTP client, database query hoặc shutdown callback. Nó chỉ bảo vệ phép thử khỏi việc chạy quá giới hạn đã chọn.

Một test có network hoặc thread nền cần đồng thời:

- Timeout ở operation thực.
- Cleanup trong `finally`.
- Fake/sandbox dependency phù hợp.
- Cơ chế hủy task khi timeout.
- Giới hạn đủ rộng để tránh flaky trên CI.

Không nên dùng phép thử dựa vào lỗi mạng ngẫu nhiên để “kiểm tra retry”; hãy cho fake dependency trả lỗi theo kịch bản xác định.

## 33. Test resource do chính test tạo

Nếu test mở stream hoặc file, test phải đóng nó kể cả khi assertion thất bại.

~~~java
@Test
void readsTestFixture() throws Exception {
    InputStream input = getClass()
            .getResourceAsStream("/fixtures/message.txt");

    assertNotNull(input);

    try (InputStream stream = input) {
        String content = new String(
                stream.readAllBytes(),
                StandardCharsets.UTF_8
        );

        assertFalse(content.isBlank());
    }
}
~~~

`getResourceAsStream(...)` có thể trả `null` nếu fixture không tồn tại, nên test kiểm tra trước khi đọc.

Đối với file tạm:

~~~java
@TempDir
Path temporaryDirectory;
~~~

JUnit có hỗ trợ `@TempDir` giúp quản lý một thư mục tạm cho test. Khi dùng những resource khác như socket, consumer hoặc executor, test vẫn cần cơ chế cleanup tường minh phù hợp.

## 34. Không kiểm thử shutdown bằng System.exit trong JUnit

Một test như sau là không phù hợp:

~~~java
@Test
void shutdownHookRuns() {
    System.exit(0);
}
~~~

Nó có thể kết thúc JVM đang chạy toàn bộ suite.

Để kiểm tra lifecycle Spring, hãy dùng:

~~~java
SpringApplication app =
        new SpringApplication(TestApplication.class);

app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context =
        app.run("--spring.main.banner-mode=off")) {

    // Assertions khi app đang chạy.
}
// Context đã được đóng bởi try-with-resources.
~~~

Nếu cần test ứng dụng nhận SIGTERM và graceful shutdown thực tế, hãy chạy executable artifact trong **process con** ở một system test riêng, gửi signal có kiểm soát, xem exit code và cleanup. Không giả định shutdown hook chạy được khi process bị `SIGKILL` hoặc máy chủ mất nguồn.

## 35. Graceful shutdown: test cả in-flight work

Đối với Spring Boot web app, có thể cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Một system test có thể:

1. Khởi động server.
2. Bắt đầu một request có thời gian thực hiện đủ dài.
3. Ra lệnh shutdown.
4. Xác nhận server không tiếp tục nhận request mới theo hành vi server hỗ trợ.
5. Kiểm tra request đang xử lý hoàn tất hoặc bị xử lý đúng timeout.
6. Kiểm tra consumer và worker nền ngừng theo chính sách.
7. Xác nhận process thoát và resource đã đóng.

**Graceful shutdown của web server không tự quản lý mọi task nền tự tạo.** Nên thử riêng các worker/executor nếu chúng là bộ phận quan trọng của ứng dụng.

## 36. Các lỗi thường gặp khi test init, runner và cleanup

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `@PostConstruct` không chạy | Tạo object bằng `new`, không qua Spring | Context-level test hoặc gọi logic init thuần |
| Runner bean tồn tại nhưng không chạy | Dùng context runner đơn giản | Test qua `SpringApplication` |
| `ApplicationReadyEvent` không đến listener trong test | Đăng ký sau startup | Gắn listener trước `run(...)` |
| `@RecordApplicationEvents` không thấy startup event | Event xảy ra trước method test | Dùng listener sớm trong Boot startup integration test |
| `@PreDestroy` chưa chạy sau `@Test` | Cached context chưa đóng | Tạo context riêng và close |
| ContextClose event đến trước destroy | Event đánh dấu bắt đầu close | Assert resource sau khi close hoàn tất |
| Test chập chờn | Sleep hoặc async race | Latch, future, fake executor |
| Test treo trong shutdown | Thread/network không có timeout | Thiết kế stop và giới hạn thời gian |
| Lỗi startup không được test đúng | Chỉ gọi runner trực tiếp | Test `SpringApplication.run(...)` |
| Test độc lập chạy được nhưng cả suite lỗi | Shared singleton/static state | Cô lập context, reset state, tránh parallel conflict |
| Cleanup báo thành công nhưng resource vẫn mở | Chỉ tăng counter, chưa đóng resource | Kiểm tra trạng thái fake resource |
| Prototype không được hủy khi đóng context | Prototype destroy không do container quản lý đầy đủ | Caller chịu trách nhiệm cleanup |

Mỗi triệu chứng có thể có nhiều nguyên nhân; test nên ghi thông báo cụ thể về hợp đồng bị vi phạm thay vì chỉ đưa thông báo chung “context failed”.

## 37. Kịch bản kiểm thử thực tế cho một startup pipeline

Giả sử dịch vụ cần:

~~~text
Validate config
      |
      v
Initialize connection pool
      |
      v
Load required catalog
      |
      v
Ready for traffic
      |
      v
Process messages
      |
      v
Shutdown and release resources
~~~

Có thể chia thành các nhóm:

### A. Config/unit tests

- Thiếu cấu hình bắt buộc thì validation ném lỗi rõ ràng.
- Một giá trị không hợp lệ được phát hiện trước khi dùng.
- Các tham số runner được giải mã chính xác.

### B. Bean lifecycle tests

- Connection fake được tạo và init đúng.
- Nếu bean tiếp theo thất bại, các resource đã đăng ký được cleanup.
- `@PreDestroy` hoặc destroy method làm resource đóng khi context close.

### C. Runner tests

- Runner gọi catalog loader.
- Thành công làm state chuyển `READY`.
- Thất bại không bị nuốt.
- Nếu có nhiều runner, thứ tự phụ thuộc được đảm bảo.

### D. Event tests

- Started xuất hiện trước runner.
- Ready xuất hiện sau runner thành công.
- Failed xuất hiện khi runner ném lỗi.
- Close event đến khi context bước vào shutdown.

### E. Async/shutdown tests

- Readiness không đạt trong lúc catalog load chưa xong.
- Khi shutdown, consumer ngừng nhận thêm task.
- Task đang chạy được xử lý theo chính sách.
- Connection và executor được đóng.

Không phải mọi kịch bản cần dùng một `@SpringBootTest` lớn. Phân tầng hợp lý giúp xác định nguyên nhân test thất bại nhanh hơn.

## 38. Bài thực hành tự xây dựng

Hãy thử tạo một ứng dụng Boot nhỏ với ba bean:

1. `LifecycleProbe` có `@PostConstruct` và `@PreDestroy`.
2. `StartupModeRunner` nhận `ApplicationArguments` và gọi fake task.
3. `ControlledWorker` implement `SmartLifecycle`.

Sau đó viết các test:

- **Test 1:** xác nhận init chạy đúng khi context refresh, destroy chạy sau close.
- **Test 2:** xác nhận runner nhận `--mode=safe` đúng và có fallback.
- **Test 3:** Boot startup thực sự gọi runner.
- **Test 4:** listener sớm ghi được started và ready, với runner ở giữa.
- **Test 5:** runner lỗi khiến Boot phát failed event.
- **Test 6:** SmartLifecycle start và stop khi context thay đổi.
- **Test 7:** fake resource có `isClosed()` chuyển sang true sau close.
- **Test 8:** task async chưa hoàn thành thì readiness chưa đạt.
- **Test 9:** cố tình để test dùng cached context, quan sát vì sao runner không chạy lại từng method.
- **Test 10:** thay sleep bằng latch/future để kiểm tra completion.

Bài thực hành quan trọng nhất không phải viết càng nhiều assertion càng tốt, mà là **mỗi assertion tương ứng với một hợp đồng vòng đời xác định**.

## 39. Checklist trước khi hoàn thành bộ test

1. Test đang chứng minh hành vi của method hay của Spring container?
2. Test có dùng đúng `SpringApplication` khi cần Boot startup events/runners không?
3. Listener được đăng ký trước khi event phát chưa?
4. Context là mới hay lấy từ cache?
5. Assertion nằm trước hay sau refresh/runner/ready/close?
6. Có task async nào đang chạy không?
7. Nếu có, test chờ bằng tín hiệu hoàn tất nào?
8. Resource được quản lý bởi ai?
9. Khi assertion lỗi, resource/context có chắc chắn được đóng không?
10. Có timeout hữu hạn cho thao tác chờ và network không?
11. Có side effects thật lên database, broker hoặc email service không?
12. Test có thể chạy song song an toàn không?
13. Có giả định về thứ tự không được Spring cam kết không?
14. Nếu startup thất bại, test có kiểm tra nguyên nhân và cleanup phù hợp không?
15. Một test thất bại có thể cho người đọc biết rõ hợp đồng nào đã bị vi phạm không?

## Kết luận

Kiểm thử nền tảng Spring Boot không chỉ là kiểm tra service hoặc controller. **Init callbacks, runner, startup events và resource cleanup** là những hợp đồng khác nhau của vòng đời ứng dụng.

- Dùng **unit tests** để kiểm tra logic của runner, handler và cleanup.
- Dùng **`ApplicationContextRunner` hoặc context tự tạo** để kiểm tra bean init, lỗi khi refresh và destroy callbacks.
- Dùng **`SpringApplication` hoặc `@SpringBootTest`** khi cần chứng minh runner thực sự chạy.
- Gắn listener trước `run(...)` để quan sát **`ApplicationStartedEvent`, `ApplicationReadyEvent` và `ApplicationFailedEvent`**.
- Chủ động gọi `context.close()` để kiểm tra `ContextClosedEvent`, `@PreDestroy`, destroy method và `SmartLifecycle.stop(...)`.
- Không nhầm **context refresh**, **runner hoàn thành**, **ready**, **async completion** và **shutdown completion**.
- Quản lý resource ownership, dùng fake và completion signals thay vì phụ thuộc vào `Thread.sleep(...)` hoặc thời điểm ngẫu nhiên.

Một bộ kiểm thử tốt chứng minh không chỉ rằng **ứng dụng bắt đầu được**, mà còn rằng **nó bắt đầu đúng, báo lỗi đúng và dừng mà không để lại tài nguyên không được quản lý**.
