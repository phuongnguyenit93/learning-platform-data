# Kiểm thử ApplicationRunner, readiness và vòng đời ứng dụng trong Spring Boot

## 1. Mục tiêu và vấn đề thực tế

Trong Spring Boot, việc khởi tạo xong các bean không đồng nghĩa ứng dụng đã **sẵn sàng nhận lưu lượng**. Một instance có thể đã mở HTTP port nhưng vẫn đang:

- Nạp dữ liệu hoặc làm nóng cache thiết yếu.
- Xác nhận cấu hình, khóa, schema hoặc checkpoint.
- Khởi tạo consumer/background processor bắt buộc.
- Kiểm tra một dependency tối quan trọng trước khi phục vụ.
- Hoàn thành các bước chuẩn bị trong `ApplicationRunner`/`CommandLineRunner`.

Nếu bài test chỉ assert Spring ApplicationContext có thể load, nó bỏ sót thứ tự khởi động, trạng thái readiness, lỗi runner hoặc việc cleanup không đúng khi context đóng.

Mục tiêu bài học là kiểm đầy đủ ba lớp:

1. **Runner:** `ApplicationRunner` chạy với đúng arguments, theo `@Order`, đúng một lần trong mỗi lần SpringApplication startup.
2. **Readiness:** sau refresh, ứng dụng live nhưng **chưa accepting traffic** khi runner đang chạy; sau runners thành công Boot mới báo ready.
3. **Vòng đời/observability:** xác minh `ApplicationStartedEvent`, `ApplicationReadyEvent`, `ApplicationFailedEvent`, `AvailabilityChangeEvent`, Actuator health probe và context shutdown cleanup.

Đặc biệt, phân biệt bốn khái niệm:

~~~text
Spring context refreshed
      != ApplicationStartedEvent itself means ready
      != ApplicationReadyEvent has already changed readiness
      != actual readiness probe is UP
      != external traffic routing by Kubernetes is guaranteed
~~~

### Kết quả học tập

Sau bài này, bạn có thể:

- Đọc và viết `ApplicationRunner`, `CommandLineRunner`, `ApplicationArguments`.
- Biết thứ tự Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING.
- Giải thích `ApplicationAvailability`, `ReadinessState` và `LivenessState`.
- Kiểm `ApplicationRunner` bằng unit test và integration test SpringApplication thật.
- Kiểm HTTP readiness 200/503 với `/actuator/health/readiness`.
- Kiểm startup failure mà không làm cả `@SpringBootTest` thất bại trước khi test method chạy.
- Phân biệt graceful shutdown, lifecycle callbacks và Spring TestContext cache.
- Tránh startup tasks fire-and-forget, bẫy @BeforeEach và tác vụ không idempotent trên nhiều replicas.
- Biết khi nào dùng Actuator startup metrics, startupProbe, readinessProbe và livenessProbe.

## 2. Thứ tự sự kiện Spring Boot 3.5

Theo Spring Boot 3.5 Reference:

~~~text
SpringApplication.run(args)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  +-- Context refresh
  |     +-- ContextRefreshedEvent
  |     +-- WebServerInitializedEvent (nếu có server)
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |     +-- ordered runners run here
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  +-- SpringApplication.run returns ApplicationContext
~~~

Nếu có lỗi trong khởi động, Spring Boot có thể phát `ApplicationFailedEvent` và thực hiện failure handling; không nên mong sự kiện Ready xuất hiện sau startup thất bại.

**Một điểm phải kiểm đúng:** `ApplicationReadyEvent` phát **trước** availability event báo `ReadinessState.ACCEPTING_TRAFFIC`. Trong chính listener của ApplicationReadyEvent, không nên assert readiness đã là ACCEPTING chỉ vì tên event có chữ Ready. Hãy kiểm readiness ở sau `SpringApplication.run`, trong test body sau startup, hoặc nghe chính sự kiện readiness accepting.

### 2.1 Những sự kiện nào có thể nghe qua @Component?

Các events rất sớm như `ApplicationStartingEvent` xảy ra trước khi context/bean listeners được tạo. Một bean `@EventListener` thường **không thể** quan sát tất cả early events.

Muốn ghi lại events trước bean creation, đăng ký listener từ `SpringApplication`:

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>)
                event -> recorder.record("starting"));
~~~

Đây là đoạn minh họa, cần class và imports thực. Trong dự án runnable phía sau, `LifecycleTrace` là bean chỉ nghe các events **sau khi context đã refresh**; failure test riêng đăng ký listeners trực tiếp trên SpringApplication.

### 2.2 ContextRefreshedEvent khác ApplicationStartedEvent

`ContextRefreshedEvent` là sự kiện nền của Spring Framework cho một ApplicationContext được refresh. `ApplicationStartedEvent` là sự kiện Boot phát sau refresh, trước runners. Một project có parent/child contexts có thể có nhiều ContextRefreshedEvent; đừng dùng chúng thay thế cho Ready event một cách vô điều kiện.

## 3. Liveness và readiness: hai ý nghĩa khác nhau

| Trạng thái | Ý nghĩa | Phản ứng hạ tầng |
| --- | --- | --- |
| `LivenessState.CORRECT` | Instance không bị hỏng nội bộ đến mức cần restart | Thường để instance chạy |
| `LivenessState.BROKEN` | Instance không thể tự phục hồi | Có thể restart khi liveness probe fail |
| `ReadinessState.REFUSING_TRAFFIC` | Chưa hoặc không nên nhận traffic mới | Tạm không route requests mới |
| `ReadinessState.ACCEPTING_TRAFFIC` | Sẵn sàng phục vụ | Có thể nhận requests |

Trong startup mặc định:

| Pha | Liveness | Readiness |
| --- | --- | --- |
| Starting | BROKEN | REFUSING_TRAFFIC |
| Started, trước hoặc trong runners | CORRECT | REFUSING_TRAFFIC |
| Ready, sau trạng thái availability final | CORRECT | ACCEPTING_TRAFFIC |

**Không đồng nhất liveness với readiness.** Một instance có thể chạy tốt nhưng đang chờ warmup hoặc quá tải nên từ chối traffic tạm thời.

Tương tự, khi một shared database chết, đánh dấu mọi instance BROKEN có thể kích hoạt Kubernetes restart hàng loạt, làm outage nặng hơn. Readiness có thể phụ thuộc những hệ thống ngoài thực sự thiết yếu, nhưng phải cân nhắc tình huống mọi replicas cùng mất dependency.

### 3.1 ApplicationAvailability

Spring Boot cung cấp injectable `ApplicationAvailability`:

~~~java
ReadinessState readiness =
        availability.getReadinessState();

LivenessState liveness =
        availability.getLivenessState();

AvailabilityChangeEvent<ReadinessState> event =
        availability.getLastChangeEvent(ReadinessState.class);
~~~

Đây là đoạn minh họa cần biến `availability`. Trong một runner được SpringApplication gọi, trạng thái readiness mặc định là REFUSING_TRAFFIC; sau startup thành công và Boot phát state change, nó trở thành ACCEPTING_TRAFFIC.

Một số methods truy vấn generic state có thể trả null trước khi có event; convenience methods có default semantics. Khi muốn kiểm giai đoạn pre-start, phải hiểu đúng version/API, đừng suy từ null rằng ứng dụng đã healthy.

### 3.2 Publish readiness thay đổi

~~~java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);

// Khi instance phục hồi:
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC);
~~~

Đây là cách phát sự kiện cho context cụ thể. Test phải restore trong `finally` nếu context còn được cache/dùng lại.

## 4. ApplicationRunner vs CommandLineRunner

Hai interface được SpringApplication phát hiện và gọi trong giai đoạn sau Started nhưng trước Ready.

~~~java
@Component
@Order(10)
class PrepareIndexRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments arguments) {
        // Xử lý startup tasks.
    }
}
~~~

~~~java
@Component
@Order(20)
class VerifySettingsRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Raw command-line arguments.
    }
}
~~~

Hai snippets này chỉ minh họa, không thuộc mini-project sau. Các điểm chính:

- `ApplicationRunner` nhận `ApplicationArguments`, hỗ trợ options và non-option args.
- `CommandLineRunner` nhận chuỗi arguments gốc.
- `@Order`/`Ordered` định thứ tự thực thi runners; thứ tự khai báo file hay quét component không phải contract.
- Runner chạy **mỗi lần SpringApplication context mới start**; không phải một lần duy nhất toàn JVM/cluster.
- Nếu runner ném exception, Boot startup không hoàn tất bình thường.
- Nên dùng runners cho initialization thực sự cần hoàn tất trước khi nhận traffic.

### 4.1 ApplicationArguments

Với args:

~~~text
--demo.mode=qa
note.txt
--feature.flag=a
--feature.flag=b
~~~

Spring Boot parser có thể cung cấp:

~~~java
args.getOptionValues("demo.mode");   // ["qa"]
args.getOptionValues("feature.flag");// ["a", "b"]
args.getNonOptionArgs();             // ["note.txt"]
~~~

Không có option `getOptionValues` có thể trả null; code nên kiểm null/empty. Với giá trị tùy ý chứa secrets, **đừng log nguyên arguments** vào observability; chỉ trích thông tin vô hại như mode/test input.

### 4.2 @Order không quyết định thứ tự bean creation

Một runner `@Order(10)` có thể được khởi tạo sau một bean khác trong Spring context, nhưng được gọi **trước** runner `@Order(20)` ở bước startup runner invocation. Test không được suy từ @Order ra thứ tự constructor/@PostConstruct chạy.

## 5. Runner và readiness: tránh fire-and-forget

Runners có lợi vì Spring Boot **chỉ phát Ready khi các runners đã return**. Nhưng nếu runner tự tạo background future rồi return ngay:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(() -> preloadCriticalData());
    // Runners return; Boot có thể lập tức đánh dấu ready.
}
~~~

đây là lỗi khi preload là điều kiện phải có trước traffic.

Một phương án có kiểm soát:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    Future<?> future = executor.submit(this::preloadCriticalData);
    try {
        future.get(20, TimeUnit.SECONDS);
    } catch (TimeoutException timeout) {
        future.cancel(true);
        throw new IllegalStateException(
                "Critical startup timeout", timeout);
    }
}
~~~

Hai snippets là minh họa độc lập, cần executor/method/imports. `Future.get(timeout)` giới hạn thời gian đợi, còn `cancel(true)` chỉ gửi interrupt request; worker có thể vẫn chạy nếu I/O không cooperative. Dùng deadline và resource-specific timeouts tương ứng.

**Bẫy khó thấy:** Nếu runner tự publish `REFUSING_TRAFFIC` rồi **return ngay** trong lúc async warmup chưa hoàn thành, Boot sẽ publish `ACCEPTING_TRAFFIC` sau Ready và có thể ghi đè trạng thái trước đó. Không dựa vào một event REFUSING được publish sớm như cờ chặn vĩnh viễn. Hãy xử lý critical init trước khi runner return hoặc thiết kế readiness coordinator rõ.

## 6. Spring Boot Actuator probes

Spring Boot có health groups:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Cần `spring-boot-starter-actuator`. Trên Kubernetes, probes có thể được tự bật; bên ngoài môi trường đó nên cấu hình:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Trong ví dụ dùng status mapping mặc định:

| Availability state | Health group status | HTTP |
| --- | --- | --- |
| Readiness ACCEPTING_TRAFFIC | UP | 200 |
| Readiness REFUSING_TRAFFIC | OUT_OF_SERVICE | 503 |
| Liveness CORRECT | UP | 200 |
| Liveness BROKEN | DOWN | 503 |

Mapping có thể được tùy chỉnh; tests nên dựa trên config thực tế.

**Đừng chỉ gọi `/actuator/health` chung rồi tuyên bố readiness đúng**: global health và readiness group có thể chứa tập indicators khác nhau.

### 6.1 Probe không tự test toàn bộ dependencies

Spring Boot không mặc định đưa mọi DB/Redis/external service vào readiness/liveness groups. Chỉ thêm các health indicators cần thiết, cân nhắc shared dependency down khiến tất cả instances bị rút khỏi routing.

Liveness **không nên** phụ thuộc một remote API hoặc database dùng chung: hạ tầng có thể restart mọi pod mà dependency vẫn hỏng.

### 6.2 Main port và management port

Nếu Actuator chạy trên port riêng, probe có thể UP dù main HTTP connector lỗi. Spring Boot hỗ trợ:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

để có `/livez` và `/readyz` trên **main application port**. Bài runnable dùng Actuator trên cùng port mặc định.

### 6.3 Kubernetes startupProbe

Startup probe giúp những service có startup rất lâu tránh bị liveness policy kill quá sớm. Readiness probe cho biết nên route traffic hay chưa; liveness probe kiểm có nên restart. Không dùng một probe thay cho mọi mục đích.

## 7. Chiến lược test ba tầng

| Tầng | Kiểm chứng | Không chứng minh |
| --- | --- | --- |
| Unit test runner với DefaultApplicationArguments | Parse args, branching, error handling | SpringApplication gọi runner đúng pha |
| `@SpringBootTest(webEnvironment=NONE)` | Runner ordering, lifecycle events, availability state | HTTP/actuator endpoint |
| `@SpringBootTest(RANDOM_PORT)` + Actuator | HTTP readiness/liveness 200/503 | Kubernetes ingress routing đa node |
| SpringApplication isolated test | Runner failure, FailedEvent, context close | Mọi production bean tự nhiên có mặt |
| Kubernetes/staging test | Probe thresholds, routing, rolling update | Thay thế unit/integration test của app |

**Không dùng `ApplicationContextRunner` như bằng chứng full SpringApplication lifecycle.** Nó có thể kiểm auto-configuration/conditions và bean graph rất tốt, nhưng không tự chạy theo trình tự Boot Started → runner → Ready như `SpringApplication.run`.

### 7.1 Spring TestContext cache

`@SpringBootTest` có thể cache context giữa các test methods/classes có cấu hình tương đương. `ApplicationRunner` đã chạy **trước JUnit @BeforeEach**, và không chạy mỗi lần test method mới bắt đầu.

Vì thế, nếu test dùng:

~~~java
@BeforeEach
void resetHistory() {
    lifecycleTrace.clear(); // Xóa mất startup evidence.
}
~~~

rồi mong test body thấy event/runner records, nó sẽ fail giả. Bài giữ trace trong bean xuyên suốt test class, không reset. Khi cần mỗi method có startup mới, dùng `@DirtiesContext` có mục tiêu (tốn thời gian) hoặc tạo isolated SpringApplication per test.

### 7.2 Fixture cho runner phải có trước context startup

Không seed dữ liệu runner cần bằng `@BeforeEach` vì runner chạy trước @BeforeEach. Seed bằng database/container initialization trước context load, auto-configuration/test-specific bean hoặc chỉ tách startup logic thành service và unit test riêng.

## 8. Dự án Java 17+/Spring Boot 3.5.x

Bộ ví dụ gồm **5 production classes** và **5 test classes**, tổng cộng **11 phương thức JUnit Jupiter**, không cần DB/Docker/remote service.

~~~text
lifecycle-readiness-demo/
  settings.gradle
  build.gradle
  src/main/java/example/lifecycle/
    LifecycleDemoApplication.java
    LifecycleTrace.java
    WarmupStatus.java
    StartupArgumentsRunner.java
    CacheWarmupRunner.java
  src/test/java/example/lifecycle/
    RunnerUnitTest.java
    BootLifecycleTest.java
    ReadinessHttpTest.java
  src/test/java/example/isolated/
    RunnerFailureTest.java
    ShutdownLifecycleTest.java
~~~

**Lưu ý package:** isolated tests nằm ở `example.isolated` — không nằm dưới base package `example.lifecycle`. Hai nested `@SpringBootConfiguration` của negative tests không bị component scan của main application tải nhầm và làm hỏng mọi `@SpringBootTest`.

### 8.1 settings.gradle

~~~groovy
rootProject.name = 'lifecycle-readiness-demo'
~~~

### 8.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các version được pin cho bài thực hành, **không tuyên bố mới nhất**. `starter-web` cung cấp embedded server và Jackson; `actuator` cung cấp health groups; `starter-test` có JUnit, SpringBootTest, TestRestTemplate. Gradle wrapper phải được tạo hoặc dùng một Gradle tương thích.

## 9. LifecycleDemoApplication.java

File `src/main/java/example/lifecycle/LifecycleDemoApplication.java`:

~~~java
package example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }
}
~~~

Bài đặt `@SpringBootApplication` ở package `example.lifecycle`, nên các service/runner/listener cùng package này được scan.

## 10. LifecycleTrace.java

File `src/main/java/example/lifecycle/LifecycleTrace.java`:

~~~java
package example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleTrace {

    private final List<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        record("started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        record("ready:event");
    }

    @EventListener
    public void onAvailability(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof LivenessState state) {
            record("liveness:" + state);
        }
        if (event.getState() instanceof ReadinessState state) {
            record("readiness:" + state);
        }
    }
}
~~~

`CopyOnWriteArrayList` đủ cho trace mẫu. Nó không cần static global data; mỗi Spring ApplicationContext có một trace bean riêng.

Trong production, custom asynchronous `ApplicationEventMulticaster` có thể thay đổi listener ordering/execution; bài dựa trên Boot default synchronous event delivery và Spring Boot 3.5 timeline.

## 11. WarmupStatus.java

File `src/main/java/example/lifecycle/WarmupStatus.java`:

~~~java
package example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Component;

@Component
public class WarmupStatus {

    private final AtomicBoolean initialized =
            new AtomicBoolean();

    public void markInitialized() {
        initialized.set(true);
    }

    public boolean isInitialized() {
        return initialized.get();
    }
}
~~~

`WarmupStatus` chỉ mô phỏng kết quả của một critical startup task, không có remote API. Trong hệ thống thật, nếu bước warmup có thể fail, hãy propagate exception, đặt deadline và ghi metrics/failure reason.

## 12. StartupArgumentsRunner.java

File `src/main/java/example/lifecycle/StartupArgumentsRunner.java`:

~~~java
package example.lifecycle;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class StartupArgumentsRunner implements ApplicationRunner {

    private final LifecycleTrace trace;

    public StartupArgumentsRunner(LifecycleTrace trace) {
        this.trace = trace;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> modes = args.getOptionValues("demo.mode");

        String mode = modes == null || modes.isEmpty()
                ? "default"
                : modes.get(0);

        String positional =
                String.join(",", args.getNonOptionArgs());

        trace.record("runner:args:" + mode + ":" + positional);
    }
}
~~~

Với args `--demo.mode=qa note.txt`, trace mong đợi:

~~~text
runner:args:qa:note.txt
~~~

Không có option, trace:

~~~text
runner:args:default:
~~~

Các dòng trên là expected trace strings, không phải stdout từ một lần build. `@Order(10)` bảo đảm runner này chạy trước `@Order(20)` trong cùng SpringApplication startup.

## 13. CacheWarmupRunner.java

File `src/main/java/example/lifecycle/CacheWarmupRunner.java`:

~~~java
package example.lifecycle;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class CacheWarmupRunner implements ApplicationRunner {

    private final LifecycleTrace trace;
    private final WarmupStatus status;
    private final ApplicationAvailability availability;

    public CacheWarmupRunner(
            LifecycleTrace trace,
            WarmupStatus status,
            ApplicationAvailability availability) {
        this.trace = trace;
        this.status = status;
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        trace.record("runner:warmup:"
                + availability.getLivenessState()
                + ":" + availability.getReadinessState());

        // Warmup đồng bộ hoàn thành trước khi return.
        status.markInitialized();
    }
}
~~~

Trong vòng đời mặc định, tại lúc runner chạy:

~~~text
runner:warmup:CORRECT:REFUSING_TRAFFIC
~~~

Nghĩa là Spring context đã live nhưng chưa ready. Sau runner, Boot phát `ApplicationReadyEvent` rồi `ReadinessState.ACCEPTING_TRAFFIC`. Trong production, method phải hoàn tất critical task thật sự trước khi set initialized.

## 14. RunnerUnitTest.java: 2 bài unit test

File `src/test/java/example/lifecycle/RunnerUnitTest.java`:

~~~java
package example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RunnerUnitTest {

    @Test
    void parsesOptionsAndPositionalArguments() {
        LifecycleTrace trace = new LifecycleTrace();
        StartupArgumentsRunner runner =
                new StartupArgumentsRunner(trace);

        runner.run(new DefaultApplicationArguments(
                "--demo.mode=unit", "input.csv"));

        assertEquals(
                "runner:args:unit:input.csv",
                trace.snapshot().get(0));
    }

    @Test
    void absentOptionUsesDefault() {
        LifecycleTrace trace = new LifecycleTrace();
        StartupArgumentsRunner runner =
                new StartupArgumentsRunner(trace);

        runner.run(new DefaultApplicationArguments());

        assertEquals(
                "runner:args:default:",
                trace.snapshot().get(0));
    }
}
~~~

Có **2 JUnit methods**. Không khởi động SpringApplication, nên chúng chỉ kiểm logic parsing/defaults của runner. Muốn chứng minh Spring Boot gọi runner đúng thời điểm cần integration tests tiếp theo.

## 15. BootLifecycleTest.java: 4 tests trong Spring Boot context thật

File `src/test/java/example/lifecycle/BootLifecycleTest.java`:

~~~java
package example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = {"--demo.mode=qa", "note.txt"})
class BootLifecycleTest {

    @Autowired LifecycleTrace trace;
    @Autowired WarmupStatus warmup;
    @Autowired ApplicationAvailability availability;

    @Test
    void eventSequenceIncludesRunnerBeforeReady() {
        List<String> events = trace.snapshot();

        List<String> ordered = List.of(
                "started",
                "liveness:CORRECT",
                "runner:args:qa:note.txt",
                "runner:warmup:CORRECT:REFUSING_TRAFFIC",
                "ready:event",
                "readiness:ACCEPTING_TRAFFIC");

        int previous = -1;
        for (String expected : ordered) {
            int current = events.indexOf(expected);
            assertTrue(current > previous,
                    () -> "Wrong startup order for "
                            + expected + " in " + events);
            previous = current;
        }
    }

    @Test
    void finalAvailabilityIsLiveAndReady() {
        assertEquals(LivenessState.CORRECT,
                availability.getLivenessState());
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertNotNull(availability.getLastChangeEvent(
                ReadinessState.class));
        assertTrue(warmup.isInitialized());
    }

    @Test
    void bootForwardsArgumentsToApplicationRunner() {
        assertTrue(trace.snapshot().contains(
                "runner:args:qa:note.txt"));
    }

    @Test
    void eachRunnerRunsOnceForThisContext() {
        long argumentRuns = trace.snapshot().stream()
                .filter("runner:args:qa:note.txt"::equals)
                .count();
        long warmupRuns = trace.snapshot().stream()
                .filter(e -> e.startsWith("runner:warmup:"))
                .count();

        assertEquals(1L, argumentRuns);
        assertEquals(1L, warmupRuns);
    }
}
~~~

Có **4 tests**. Không reset trace trong @BeforeEach vì startup đã xảy ra trước khi JUnit test methods được chạy.

### Vì sao kiểm thứ tự bằng subsequence?

Ứng dụng thật có thể có nhiều listener và lifecycle events ngoài những ones được ghi. Test kiểm thứ tự tương đối các **mốc bắt buộc**, không hardcode toàn bộ events mà frameworks/providers có thể thêm.

### @SpringBootTest(args=...) làm gì?

`args` trên `@SpringBootTest` được chuyển vào SpringApplication khi test context start. `ApplicationRunner` nhận `ApplicationArguments` tương ứng. Điều đó khác với gọi method trực tiếp bằng raw String[] trong unit test.

## 16. ReadinessHttpTest.java: 3 tests HTTP readiness/liveness

File `src/test/java/example/lifecycle/ReadinessHttpTest.java`:

~~~java
package example.lifecycle;

import java.util.Objects;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "management.endpoint.health.probes.enabled=true")
class ReadinessHttpTest {

    @LocalServerPort int port;

    @Autowired TestRestTemplate http;
    @Autowired ObjectMapper mapper;
    @Autowired ApplicationContext context;
    @Autowired ApplicationAvailability availability;

    private ResponseEntity<String> probe(String name) {
        return http.getForEntity(
                "http://localhost:" + port
                + "/actuator/health/" + name,
                String.class);
    }

    private String status(ResponseEntity<String> response)
            throws Exception {
        String json = Objects.requireNonNull(response.getBody());
        return mapper.readTree(json).path("status").asText();
    }

    @Test
    void readinessAndLivenessAreUpAfterStartup()
            throws Exception {
        ResponseEntity<String> ready = probe("readiness");
        ResponseEntity<String> live = probe("liveness");

        assertEquals(200, ready.getStatusCode().value());
        assertEquals("UP", status(ready));
        assertEquals(200, live.getStatusCode().value());
        assertEquals("UP", status(live));

        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertEquals(LivenessState.CORRECT,
                availability.getLivenessState());
    }

    @Test
    void refusingTrafficMapsTo503ThenRestore()
            throws Exception {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        try {
            ResponseEntity<String> ready = probe("readiness");

            assertEquals(ReadinessState.REFUSING_TRAFFIC,
                    availability.getReadinessState());
            assertEquals(503, ready.getStatusCode().value());
            assertEquals("OUT_OF_SERVICE", status(ready));
        } finally {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
        }
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
    }

    @Test
    void readinessRefusalDoesNotBreakLiveness()
            throws Exception {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        try {
            ResponseEntity<String> ready = probe("readiness");
            ResponseEntity<String> live = probe("liveness");

            assertEquals(503, ready.getStatusCode().value());
            assertEquals("OUT_OF_SERVICE", status(ready));
            assertEquals(200, live.getStatusCode().value());
            assertEquals("UP", status(live));
            assertEquals(LivenessState.CORRECT,
                    availability.getLivenessState());
        } finally {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

Có **3 integration tests**. `RANDOM_PORT` không cần hardcode 8080. `TestRestTemplate` gọi localhost thật, `ObjectMapper` parse JSON status. Bài test trạng thái refusing publish event vào chính ApplicationContext rồi restore trong `finally`.

**Không bật parallel execution** của các tests cùng thao tác một availability bean/context, nếu không hai methods có thể ghi trạng thái chồng nhau. Cùng lý do, không quên restore: Spring TestContext có thể reuse context cho test class khác.

## 17. RunnerFailureTest.java: khi startup runner ném exception

Nếu tạo runner luôn ném exception trong chính `@SpringBootTest`, TestContext load fail **trước khi test body chạy**, nên không có chỗ assert gọn. Thay vào đó tạo minimal `SpringApplication` trong một JUnit test riêng.

File `src/test/java/example/isolated/RunnerFailureTest.java`:

~~~java
package example.isolated;

import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RunnerFailureTest {

    @SpringBootConfiguration
    static class BrokenApp {
        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "critical warmup failed");
            };
        }
    }

    @Test
    void startupFailureEmitsFailedButNotReady() {
        AtomicBoolean started = new AtomicBoolean();
        AtomicBoolean ready = new AtomicBoolean();
        AtomicBoolean failed = new AtomicBoolean();

        SpringApplication app =
                new SpringApplication(BrokenApp.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);
        app.addListeners(
            (ApplicationListener<ApplicationStartedEvent>)
                event -> started.set(true),
            (ApplicationListener<ApplicationReadyEvent>)
                event -> ready.set(true),
            (ApplicationListener<ApplicationFailedEvent>)
                event -> failed.set(true));

        RuntimeException exception = assertThrows(
                RuntimeException.class,
                () -> app.run(
                        "--spring.main.banner-mode=off",
                        "--logging.level.root=OFF"));

        assertTrue(started.get());
        assertFalse(ready.get());
        assertTrue(failed.get());
        assertTrue(hasMessage(
                exception, "critical warmup failed"));
    }

    private static boolean hasMessage(
            Throwable error, String expected) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            String message = current.getMessage();
            if (message != null && message.contains(expected)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Có **1 test**. Runner thất bại sau Started event; không có Ready event; Boot publish Failed event. Code test không gọi `System.exit` và không làm các full-context tests khác fail. Nested config nằm trong package `example.isolated`, nằm ngoài scan base package của main demo.

**Không assert HTTP 503 sau startup fail**: embedded server có thể chưa tồn tại hoặc đã bị đóng. Assertion sự kiện/exception là contract lifecycle chính xác hơn.

## 18. ShutdownLifecycleTest.java: đóng context dọn resource

Test riêng cho cleanup:

File `src/test/java/example/isolated/ShutdownLifecycleTest.java`:

~~~java
package example.isolated;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ShutdownLifecycleTest {

    static final class CloseProbe implements AutoCloseable {
        final AtomicInteger closes = new AtomicInteger();

        @Override
        public void close() {
            closes.incrementAndGet();
        }
    }

    @SpringBootConfiguration
    static class CloseOnlyApp {
        @Bean
        CloseProbe closeProbe() {
            return new CloseProbe();
        }
    }

    @Test
    void contextCloseInvokesBeanDestroyMethod() {
        SpringApplication app =
                new SpringApplication(CloseOnlyApp.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context =
                app.run(
                    "--spring.main.banner-mode=off",
                    "--logging.level.root=OFF");

        CloseProbe probe = context.getBean(CloseProbe.class);
        try {
            assertEquals(0, probe.closes.get());
        } finally {
            context.close();
        }
        assertEquals(1, probe.closes.get());
    }
}
~~~

Có **1 test**. Spring `@Bean` có destroy-method inference cho `close()` của `AutoCloseable`; test chủ động tạo context và có quyền đóng nó trong finally.

Không gọi `context.close()` trên shared context của `@SpringBootTest` rồi mong tests sau vẫn hoạt động; TestContext có thể đang cache object đó. Muốn kiểm context shutdown lifecycle, sở hữu context riêng hoặc dùng `@DirtiesContext` có mục tiêu.

## 19. Tổng cộng 11 bài kiểm thử và cách chạy

| Test class | @Test | Mục tiêu |
| --- | ---: | --- |
| `RunnerUnitTest` | 2 | ApplicationArguments/defaults |
| `BootLifecycleTest` | 4 | Event ordering, runner @Order, final availability |
| `ReadinessHttpTest` | 3 | HTTP readiness 200/503, liveness independence |
| `RunnerFailureTest` | 1 | ApplicationFailedEvent và không Ready |
| `ShutdownLifecycleTest` | 1 | Bean cleanup trên context.close |
| **Tổng** | **11** | Unit + Spring startup + HTTP + isolated failures |

Linux/macOS:

~~~bash
./gradlew test --tests example.lifecycle.RunnerUnitTest --tests example.lifecycle.BootLifecycleTest --tests example.lifecycle.ReadinessHttpTest --tests example.isolated.RunnerFailureTest --tests example.isolated.ShutdownLifecycleTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.lifecycle.RunnerUnitTest --tests example.lifecycle.BootLifecycleTest --tests example.lifecycle.ReadinessHttpTest --tests example.isolated.RunnerFailureTest --tests example.isolated.ShutdownLifecycleTest
~~~

Toàn bộ suite:

~~~bash
./gradlew clean test
~~~

**Kết quả dự kiến** theo cấu trúc: 11 JUnit Jupiter methods PASS trên Java 17+/Spring Boot 3.5.x với đúng các files/dependencies nêu trên. Đây là dự kiến từ static code/API review, **chưa phải output của Gradle được chạy thực tế**. Random port và startup logs phụ thuộc môi trường; không hardcode stdout.

### 19.1 Debug khi test fail

1. Có dùng đúng main `@SpringBootApplication` và package scan không?
2. Có một nested `@SpringBootConfiguration` khác bị scan nhầm vào context không?
3. `@SpringBootTest(args=...)` đã khai báo đúng option/non-option args chưa?
4. `@Order` được đặt trên các runner beans được Spring nhận diện chưa?
5. Bean listener có được tạo trước ApplicationStartedEvent không?
6. Có async custom ApplicationEventMulticaster làm thứ tự callback thay đổi không?
7. `@BeforeEach` có xóa startup trace đã ghi từ trước không?
8. `ApplicationAvailability` có ở đúng context và state nào?
9. Actuator có trong dependencies và `probes.enabled=true` ở môi trường test không?
10. Có custom status/http mappings hoặc security filter trên health endpoint không?
11. HTTP test đã restore readiness state sau case 503 chưa?
12. Context failure test có dùng isolated SpringApplication thay vì làm full test context fail không?
13. Context cleanup có đúng ownership và không phá TestContext cache không?

## 20. Điều cần tránh trong production startup

### 20.1 Runner quá lâu không deadline

Một runner gọi remote API với timeout vô hạn có thể làm startup đứng mãi. Readiness REFUSING nhưng hạ tầng có thể có startup/liveness timeouts. Đặt deadline, retries có giới hạn/backoff và chính sách fail startup/degraded rõ. Không dùng `Thread.sleep` làm test startup.

### 20.2 Runner khởi tạo dữ liệu không idempotent

Một SpringApplication khởi động lại sẽ gọi runner lại. Kubernetes scale lên nhiều replicas có thể chạy nhiều runners **đồng thời**. Không dùng runner để gửi email/thanh toán/migrate DB mà không idempotency, lock hoặc migration tool phù hợp.

### 20.3 Ready event kích hoạt critical warmup bất đồng bộ

~~~java
@EventListener(ApplicationReadyEvent.class)
public void afterReady() {
    executor.execute(this::loadCriticalData);
}
~~~

Nếu `loadCriticalData` là điều kiện nhận traffic, đây là anti-pattern: Boot sắp publish ACCEPTING sau listener return. Chuyển phần critical sang runner, hoặc thiết kế coordinator quản lý readiness sau startup có kiểm thử thứ tự.

### 20.4 Đặt mọi dependency check vào liveness

Một shared DB outage có thể làm mọi pods restart và gây cascading failure. Liveness kiểm lỗi nội bộ không thể tự hồi phục; readiness kiểm khả năng phục vụ và có thể bao gồm một số dependency thiết yếu.

## 21. Graceful shutdown, readiness và vòng đời resource

Ở shutdown:

~~~text
Running:
    liveness CORRECT
    readiness ACCEPTING_TRAFFIC

Graceful shutdown:
    readiness REFUSING_TRAFFIC
    server stops accepting new requests
    in-flight requests may complete within grace period

Shutdown complete:
    ApplicationContext closed
    resources destroyed
~~~

Có thể cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Tùy embedded server và Boot version, chi tiết reject/drain khác nhau. Bài `ShutdownLifecycleTest` chỉ chứng minh `AutoCloseable.close()` được Spring gọi khi context close; **nó không chứng minh HTTP draining**.

Muốn test HTTP graceful shutdown đúng, cần context/embedded server riêng, request có `CountDownLatch` giữ in-flight, đóng context từ thread khác có deadline, xác minh readiness và response đang chạy, release latch, chờ terminated. Không đoán bằng Thread.sleep hoặc dùng fixed port.

### 21.1 Resource ownership trong tests

| Resource | Owner | Cách cleanup |
| --- | --- | --- |
| @SpringBootTest ApplicationContext | Spring TestContext | Không close tùy tiện trong test |
| Isolated SpringApplication context | Chính test | close trong finally |
| Runner tạo executor riêng | Application lifecycle | shutdown/await khi context đóng |
| DB rows runner tạo | Database/fixture | Committed cleanup, không chỉ @Rollback |
| Message subscriptions | Listener/container | Stop/dispose đúng lifecycle |
| HTTP warmup request | HTTP client | Timeout, close response |
| Readiness state test tự publish | Test đang sở hữu mutation | Restore event trong finally |
| Actuator random-port server | Spring TestContext | Context close/destroy |

### 21.2 Thread-local transaction và runner

Test-managed `@Transactional` trên JUnit thread bắt đầu **sau khi startup runners đã chạy**. Rollback của test không tự xóa DB writes mà runner tạo và commit trước đó. Nếu runner seed data vào shared DB, dùng dedicated test schema/containers và cleanup rõ.

## 22. Startup metrics và observability

Lưu ý ba nhóm tín hiệu khác nhau:

1. **Spring Boot events:** Starting/Started/Ready/Failed và availability changes.
2. **Startup timing/steps:** `ApplicationStartup`, `BufferingApplicationStartup`, startup metrics và Actuator startup endpoint nếu cấu hình.
3. **Health probes:** `/actuator/health/liveness` và `/actuator/health/readiness`.

`ApplicationStartup` có thể đo bean initialization/configuration steps, nhưng không tự chứng minh một business warmup đã hoàn thành. Probe status cho biết state được publish, không xác minh mọi downstream healthy nếu chúng không được khai báo vào readiness group.

Trong production nên quan sát:

| Tín hiệu | Mục đích |
| --- | --- |
| startup duration | Thời gian từ khởi chạy tới ready |
| runner duration/failure | Xác định bước critical chậm/lỗi |
| availability transitions | Bao nhiêu lần refusing/accepting/broken |
| Actuator probe 200/503 | Quan sát trạng thái ứng dụng qua HTTP |
| failed startup root cause | Chẩn đoán cấu hình/dependency |
| restart count | Nhận biết crash loop |
| shutdown duration | Kiểm drain/cleanup |
| side-effect count | Phát hiện runner chạy nhiều lần khi restart/scale |
| application instance ID | Phân biệt các pods/contexts |

Không log secrets được truyền qua args/environment hoặc health details. Dùng các labels/tags có cardinality hợp lý.

### 22.1 Vì sao không assert startup < 100ms?

Máy CI, local laptop, JDK warmup, filesystem, network và classpath khác nhau. Test semantic lifecycle nên assert **thứ tự và giá trị**; startup performance cần benchmarks/metrics với SLO và môi trường tương ứng.

## 23. Các lỗi kiểm thử thường gặp

**1. Chỉ dùng unit test gọi runner.run rồi tuyên bố Spring tự gọi.**  
Unit test không chứng minh lifecycle wiring; thêm @SpringBootTest hoặc SpringApplication.

**2. Nhầm ApplicationStartedEvent với ApplicationReadyEvent.**  
Started trước runner, Ready sau runner.

**3. Assert readiness ACCEPTING trong listener ApplicationReadyEvent.**  
Boot publish readiness accepting ngay **sau** Ready event. Đợi state change/return.

**4. Liveness CORRECT bị hiểu là ready.**  
Khi runner chạy liveness correct nhưng readiness refusing.

**5. Runner tạo background job rồi return.**  
Boot đánh dấu ready dù initialization chưa xong; chờ critical task hoặc quản lý readiness rõ.

**6. Runner publish REFUSING rồi return.**  
Boot có thể publish ACCEPTING sau đó, override state; không xem refusal là sticky flag.

**7. Đặt heavy startup trong @PostConstruct mà không hiểu phase.**  
Khó xác định StartupRunner order và readiness; tách vào runner hợp lý.

**8. Không test runner failure.**  
Có thể nuốt exception và báo Ready sai; kiểm FailedEvent/absence of Ready.

**9. Test runner fail trực tiếp trong @SpringBootTest.**  
Context fail trước @Test; dùng isolated SpringApplication negative test.

**10. Quên probes.enabled ngoài Kubernetes.**  
Health probe endpoint có thể 404, không phải readiness DOWN.

**11. Dùng global /actuator/health thay readiness group.**  
Các health contributors có thể khác; query đúng path.

**12. Từ 503 readiness suy rằng TCP port bị đóng.**  
Readiness là routing signal; localhost vẫn có thể trả HTTP.

**13. Test readiness không restore sau REFUSING_TRAFFIC.**  
Cached context rò state; dùng finally.

**14. Spring TestContext cache bị xem như tạo mới mỗi method.**  
Runner chỉ chạy khi context load, không chạy mỗi @Test.

**15. @BeforeEach reset lifecycle trace.**  
Làm mất startup events đã được ghi trước khi test chạy.

**16. Dùng @DirtiesContext mỗi test không cần thiết.**  
Tăng startup cost và làm runners chạy lại.

**17. Seed fixture trong @BeforeEach nhưng runner cần nó lúc startup.**  
Fixture quá muộn; seed trước context load hoặc unit test logic.

**18. Không phân biệt CommandLineRunner raw args với ApplicationArguments structured args.**  
Test parser đúng interface.

**19. Dựa vào thứ tự component scan thay @Order.**  
Không có contract; dùng explicit ordering.

**20. Suy từ một SpringApplication startup ra an toàn multi-replica.**  
Mỗi instance có runners; cần idempotency/locks.

**21. Đặt shared DB outage vào liveness check.**  
Có thể gây restart storm; liveness không phải dependency monitor.

**22. Mock mọi startup dependency đến mức test không còn đường đi thật.**  
Giữ một integration test thật cho Boot lifecycle/runner invocation.

**23. Coi ApplicationContextRunner như full Boot startup.**  
Không tự cung cấp đầy đủ Started/Ready/runner semantics.

**24. Hardcode port 8080 trong HTTP test.**  
CI parallel dễ xung đột; dùng RANDOM_PORT.

**25. Không close isolated SpringApplication context.**  
Rò threads/resources; test tự sở hữu context phải đóng.

**26. Close shared SpringBootTest context giữa tests.**  
Làm TestContext cache không nhất quán.

**27. Không kiểm deadline và cancellation của runner.**  
Startup có thể treo mãi; cần bounded operations.

**28. Dùng exact startup time assertions trong CI.**  
Flaky; kiểm order/state và monitor performance riêng.

## 24. Checklist thiết kế test đúng

1. Xác định mọi ApplicationRunner/CommandLineRunner và startup tasks quan trọng.
2. Nêu dependencies/ordering giữa runners; dùng @Order/Ordered.
3. Viết unit tests cho arguments, branching và business initialization logic.
4. Giữ ít nhất một @SpringBootTest full startup để kiểm SpringApplication invocation.
5. Ghi events vào bean được tạo trong context, không xóa trace ở @BeforeEach.
6. Assert Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING.
7. Kiểm trạng thái liveness/readiness **ngay trong runner** và sau startup.
8. Test failure bằng isolated SpringApplication và ApplicationFailedEvent.
9. Bật Actuator probes rõ ràng ngoài Kubernetes.
10. Kiểm HTTP readiness UP/200, REFUSING OUT_OF_SERVICE/503.
11. Kiểm readiness refusing không đồng nghĩa liveness broken.
12. Restore readiness state trong finally và không chạy parallel state-mutating tests.
13. Không đợi Thread.sleep để suy đoán lifecycle phase.
14. Không coi port đang mở là bằng chứng ready.
15. Có cleanup/timeout cho critical startup I/O và side effects.
16. Mỗi SpringApplication instance được khởi động có thể gọi runner; thiết kế idempotent.
17. Test shutdown callbacks/context close trên context riêng.
18. Xem xét Kubernetes startupProbe, readinessProbe, livenessProbe đúng chức năng.
19. Phân biệt startup metrics và availability event semantics.
20. Không bịa stdout/logs; ghi rõ expected values và version của framework.

### Checklist cuối

- [ ] Runner unit tests có ApplicationArguments phù hợp.
- [ ] Runner integration test gọi qua SpringApplication thật.
- [ ] @Order được kiểm đúng.
- [ ] Ready event xuất hiện sau runners, trước accepting event.
- [ ] Startup failure không phát Ready.
- [ ] Readiness accepting sau startup và refusing khi cần.
- [ ] Actuator 200/503 mapping được kiểm qua HTTP thật.
- [ ] Liveness độc lập với readiness.
- [ ] Test restore readiness sau khi mutate.
- [ ] Spring TestContext cache không làm rò state.
- [ ] Không dùng async fire-and-forget cho critical initialization.
- [ ] Startup operations có deadline/error policy/idempotency.
- [ ] Context close có cleanup được kiểm.
- [ ] Không gắn external systems vào liveness vô điều kiện.

## 25. Kết luận

**Started nghĩa context đã refresh; Ready nghĩa Spring Boot đã chạy xong runners và sắp chuyển readiness sang accepting.** Trình tự nền tảng cần nhớ:

~~~text
ApplicationStartedEvent
  -> LivenessState.CORRECT
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
~~~

Một bộ kiểm thử tốt không chỉ thấy ApplicationContext load. Nó phải chứng minh runner chạy đúng, sự kiện có thứ tự đúng, readiness health group phản ánh 200/503, runner thất bại không tạo Ready và các resources được dọn khi context đóng. Khi ứng dụng có async warmup/cluster scale/độ trễ dependency, readiness policy và idempotency cần được kiểm sâu hơn để không báo sẵn sàng giả.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ApplicationRunner, ApplicationArguments, lifecycle events và availability.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness probes, health statuses, Kubernetes lifecycle.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest(args), RANDOM_PORT và TestRestTemplate.
- [Spring Boot 3.5 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): getReadinessState, getLivenessState, last event.
- [Spring Boot 3.5 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): publish and state.
- [Spring Boot 3.5 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html): startup runner contract.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): @EventListener/ApplicationListener.
- [Spring Framework — Bean Destroy Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks, AutoCloseable inference.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): graceful shutdown and lifecycle phase timeout.
