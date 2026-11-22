# Thu thập sự kiện để kiểm chứng thứ tự và trạng thái availability trong Spring Boot

## 1. Mục tiêu: kiểm thử vòng đời bằng dấu vết có thể xác minh

Một test chỉ gọi `SpringApplication.run(args)` rồi kiểm tra không ném lỗi chưa đủ chứng minh ứng dụng đã trải qua các mốc vòng đời đúng thứ tự. Spring Boot có thể refresh `ApplicationContext` thành công nhưng `ApplicationRunner` còn đang chạy; `ApplicationStartedEvent` có thể được phát trong khi readiness vẫn là `REFUSING_TRAFFIC`. Ngược lại, một event `ContextClosedEvent` không chứng minh toàn bộ executor/consumer đã chấm dứt.

Đề bài thuộc chương **Kiểm thử vòng đời**: **thu thập sự kiện để kiểm chứng thứ tự và trạng thái availability**. Chúng ta sẽ ghi lại các mốc quan trọng, dùng assertions theo thứ tự quan hệ, kiểm tra trực tiếp `ApplicationAvailability` tại runner và sau Ready, thử một startup failure có kiểm soát, đổi readiness chủ động và xem giới hạn của phương pháp.

Kết quả cần đạt:

- Đăng ký `ApplicationListener` **trước** `SpringApplication.run` để bắt cả events chưa có context.
- Lưu thông tin tối thiểu: nhãn event, thứ tự quan sát, elapsed time, tên thread.
- Kiểm tra `ApplicationStartedEvent` → `LivenessState.CORRECT` → runner → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- Xác minh trong runner, liveness đã `CORRECT` nhưng readiness còn `REFUSING_TRAFFIC`.
- Xác minh khi runner thất bại, `ApplicationFailedEvent` có mặt; Ready và accepting không có trên đường startup đó.
- Phát `AvailabilityChangeEvent` sau startup để kiểm tra state chuyển refusing → accepting.
- Phân biệt `@RecordApplicationEvents` của Spring TestContext, event recorder đăng ký rất sớm và HTTP health probes của Actuator.
- Không coi event “đã bắt đầu đóng” là bằng chứng tài nguyên đã đóng.

**Phạm vi:** Java 17+, Spring Boot 3.3.5, JUnit Jupiter và Gradle. Project demo chạy non-web, không cần database, broker hoặc Web server. Cách lấy event từ Spring là thật; chuỗi log output có số thứ tự/thời gian thay đổi theo từng máy.

## 2. Các sự kiện liên quan một lần SpringApplication.run

Tài liệu Spring Boot 3.3 mô tả các sự kiện startup chính theo thứ tự:

```text
ApplicationStartingEvent
       |
ApplicationEnvironmentPreparedEvent
       |
ApplicationContextInitializedEvent
       |
ApplicationPreparedEvent
       |
   context.refresh()
     |-- ContextRefreshedEvent
     +-- WebServerInitializedEvent (nếu có Web server)
       |
ApplicationStartedEvent
       |
AvailabilityChangeEvent(LivenessState.CORRECT)
       |
ApplicationRunner / CommandLineRunner
       |
ApplicationReadyEvent
       |
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
       |
SpringApplication.run() trả về thành công
```

Đây là **sơ đồ mốc chính**, không phải danh sách bao trùm mọi event có thể chen vào. Nếu có nhiều contexts, Web stack, parent-child hierarchy, custom publisher hoặc event listener khác, trace có thể khác.

| Sự kiện | Ý nghĩa đúng | Không được suy diễn |
|---|---|---|
| `ApplicationStartingEvent` | Boot bắt đầu run, trước Environment/Context | Bean đã được khởi tạo |
| `ApplicationEnvironmentPreparedEvent` | Environment đã sẵn sàng | Context đã refresh |
| `ApplicationContextInitializedEvent` | Context và initializers đã chuẩn bị, chưa load bean definitions | Có đủ singleton beans |
| `ApplicationPreparedEvent` | Bean definitions đã load, trước refresh | Ứng dụng Ready |
| `ContextRefreshedEvent` | Spring context refresh xong | Runners đã hoàn tất |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Readiness đã accepting |
| `AvailabilityChangeEvent<LivenessState.CORRECT>` | Công bố app đã live | App đã hoàn thành runners |
| `ApplicationReadyEvent` | Sau runners | Mọi listener readiness đã nhận accepting |
| `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>` | Công bố đã ready cho traffic | Tất cả background task đã hoàn tất |
| `ApplicationFailedEvent` | `SpringApplication.run` gặp failure | Mọi event thành công đều đã xảy ra |
| `ContextClosedEvent` | Context đang đi vào giai đoạn close | Mọi tài nguyên đã thật sự dừng |

**Đặc biệt:** `ApplicationReadyEvent` được phát **trước** event `ReadinessState.ACCEPTING_TRAFFIC` ngay sau đó. Vì thế không nên thiết kế test đòi listener `ApplicationReadyEvent` nhìn thấy event accepting đã publish trước nó.

**ApplicationStartedEvent** nằm sau refresh nhưng trước các runner, không phải tên khác của `ApplicationStartingEvent`. Hai sự kiện này rất dễ nhầm vì cùng có từ “Started/Starting”.

**Runner có thể bất đồng bộ:** nếu method `ApplicationRunner.run` chỉ submit `CompletableFuture` rồi return, Boot vẫn có thể đi tới Ready trong khi future còn xử lý. Để Ready phụ thuộc completion của một nhiệm vụ khởi động quan trọng, phải chờ kết quả có deadline phù hợp hoặc có cơ chế giữ readiness từ chối traffic.

## 3. Hiểu LivenessState, ReadinessState và ApplicationAvailability

Spring Boot cung cấp:

```java
org.springframework.boot.availability.ApplicationAvailability
org.springframework.boot.availability.AvailabilityChangeEvent
org.springframework.boot.availability.LivenessState
org.springframework.boot.availability.ReadinessState
```

**Liveness:** tình trạng nội bộ cho biết app có thể hoạt động/khôi phục hay hỏng cần restart. `LivenessState` có `CORRECT` và `BROKEN`. Không nên gán `LivenessState.BROKEN` chỉ vì một database bên ngoài tạm thời mất kết nối; nếu Kubernetes restart toàn bộ replicas, sự cố có thể trầm trọng hơn.

**Readiness:** instance có sẵn sàng **nhận traffic mới** hay không, với `ReadinessState.ACCEPTING_TRAFFIC` và `ReadinessState.REFUSING_TRAFFIC`. Live mà không ready hoàn toàn hợp lệ trong khi runner đang chạy, warm-up hoặc drain trước shutdown.

| Giai đoạn | Liveness chuẩn | Readiness chuẩn |
|---|---|---|
| Ban đầu | Chưa Correct, mặc định như `BROKEN` | `REFUSING_TRAFFIC` |
| Đã Started, đang chạy runner | `CORRECT` | `REFUSING_TRAFFIC` |
| Đã Ready | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Graceful shutdown | Thường vẫn `CORRECT` | `REFUSING_TRAFFIC` |

Bảng mô tả lifecycle thông thường của Boot 3.3. Ứng dụng có thể tự publish các thay đổi, và một HTTP probe có thể chưa được cung cấp ở thời điểm rất sớm hoặc đã dừng trong shutdown.

### 3.1. Kiểm tra state trực tiếp

`ApplicationAvailability` có các API:

```java
LivenessState live = availability.getLivenessState();
ReadinessState ready = availability.getReadinessState();
AvailabilityChangeEvent<ReadinessState> last =
        availability.getLastChangeEvent(ReadinessState.class);
```

Đây là **snippet tích hợp**, cần biến `availability` thuộc `ApplicationAvailability` và các imports thích hợp.

`getReadinessState()` cho biết trạng thái hiện hành, còn `getLastChangeEvent(...)` cho event thay đổi gần nhất **khi có**. Event cuối có thể là null trước khi Boot publish một event thuộc loại đó. Một trạng thái mặc định `REFUSING_TRAFFIC` **không tự chứng minh** đã từng có event `AvailabilityChangeEvent(REFUSING_TRAFFIC)` được publish.

Vì vậy test nên xác minh **state trong runner** thay vì đòi trace ban đầu có event refusing riêng.

### 3.2. Availability được công bố, không phải bằng chứng phục vụ HTTP

`ApplicationAvailability.getReadinessState()==ACCEPTING_TRAFFIC` là dữ liệu nội bộ JVM. Nó không tự chứng minh:

- Web server đang mở đúng port (demo non-web không có Web server).
- Load balancer đã cập nhật routing ngay tức thì.
- Kubernetes probe đã kịp lấy trạng thái mới.
- Toàn bộ HTTP connection/remote dependencies đang khỏe.
- Một task bất đồng bộ ngoài runner đã hoàn thành.

Muốn xác minh đường HTTP thực, cần Web/Actuator integration test riêng.

## 4. Điểm đăng ký listener quyết định những sự kiện có thể bắt

Một bean listener tạo sau khi context được dựng **không thể bắt đáng tin `ApplicationStartingEvent`**:

```java
@Component
class TooLate {
    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        // Event này xảy ra trước khi component bean tồn tại.
    }
}
```

Đây là snippet minh họa lỗi lựa chọn thời điểm, cần imports phù hợp. `@EventListener` rất hữu ích đối với sự kiện sau khi bean đã được đăng ký; nhưng không thay cho early listener trong bài kiểm thử toàn bộ bootstrap.

Cách đúng:

```java
StartupTrace trace = new StartupTrace();

SpringApplication application =
        new SpringApplication(LifecycleTraceApplication.class);

application.addListeners(trace);  // Đăng ký trước run().

ConfigurableApplicationContext context = application.run(args);
```

Đoạn tích hợp trên được triển khai đầy đủ trong phần demo.

Các cách đăng ký sớm khác gồm `SpringApplicationBuilder.listeners(...)` và `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener`. Nếu bạn chỉ cần theo dõi một `AvailabilityChangeEvent` khi app đang chạy, bean `@EventListener` bình thường có thể phù hợp hơn.

## 5. Một recorder nên ghi gì?

Mỗi sự kiện nên có:

- **Sequence:** thứ tự được recorder xử lý.
- **Label:** tên chuẩn hóa, ví dụ `STARTED`, `READY`, `LIVENESS:CORRECT`.
- **Thread:** thread thực thi listener.
- **Elapsed time:** khoảng từ lúc tạo recorder tính bằng `System.nanoTime()`.
- **Context ID / run ID** khi có nhiều contexts hoặc nhiều lần khởi chạy.

Không nhất thiết lưu nguyên object `ApplicationEvent`. Nhiều event có tham chiếu tới context, Environment, exception hoặc object nguồn lớn; giữ chúng trong `static List` có thể làm các test giữ memory lâu hơn mong muốn. Snapshot chuỗi, enum và thời gian thường đủ cho kiểm thử thứ tự.

### 5.1. Thread-safe recording chưa đồng nghĩa toàn cục có thứ tự

Với event multicaster đồng bộ mặc định, một listener thường được gọi trên thread của publisher. Khi thiết kế recorder, `synchronized` giúp tránh hai threads đồng thời tạo cùng sequence hoặc làm hỏng `ArrayList`.

Nếu bật async event multicaster, event A có thể được publisher phát trước B nhưng listener của B chạy trước listener của A do scheduling. Lúc đó recorder chỉ chứng minh **delivery order tới recorder**, không phải publish order hay quan hệ happens-before giữa hai công việc nghiệp vụ. Cần event ID, deadline và `CountDownLatch`/`CompletableFuture` để phối hợp khi thực sự cần.

### 5.2. Không assert toàn bộ chuỗi bằng một list cố định

Không khuyến nghị:

```java
assertEquals(List.of("STARTING", "STARTED", "READY"),
        trace.labels());
```

Đây là ví dụ một test mong manh: còn nhiều event hợp lệ bị bỏ qua; nếu thêm một custom event hoặc Web server, danh sách thay đổi mà invariant vẫn đúng.

Nên assert **partial order**:

```text
STARTING < ENV_PREPARED < CONTEXT_INITIALIZED < PREPARED
PREPARED < CONTEXT_REFRESHED < STARTED
STARTED < LIVENESS:CORRECT < RUNNER
RUNNER < READY < READINESS:ACCEPTING_TRAFFIC
```

Dấu nhỏ hơn ở đây là ký hiệu “xuất hiện trước trong cùng trace”, không phải so sánh enum. Không assert “phải đúng 120 ms” vì tốc độ JVM, CI, CPU/disk và logging thay đổi.

## 6. Cách chứng minh readiness ở chính thời điểm runner

Vấn đề: nếu chỉ hỏi `ApplicationAvailability` sau `run`, bạn chỉ biết app cuối cùng accepting. Muốn xác minh **khi runner đang chạy vẫn refusing**, hãy tạo một custom marker event mang hai state được đọc ngay trong runner:

```java
publisher.publishEvent(
        new RunnerObservedEvent(
                this,
                availability.getLivenessState(),
                availability.getReadinessState()));
```

Recorder sẽ ghi:

```text
RUNNER:CORRECT/REFUSING_TRAFFIC
```

Sau đó mới có `READY` và `READINESS:ACCEPTING_TRAFFIC`. Đó là bằng chứng tốt hơn việc suy luận từ độ trễ hoặc dùng `Thread.sleep`.

Đừng publish accepting thủ công trong runner để ép test pass; như vậy bạn làm thay đổi hành vi mình đang muốn kiểm chứng.

## 7. Project Java 17 + Spring Boot 3.3.5 + JUnit 5 chạy được

Project non-web không dùng DB/broker/HTTP để giảm nhiễu, nhưng dùng thực các event và `ApplicationAvailability` từ Spring Boot.

### 7.1. Cấu trúc

```text
lifecycle-event-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/lifecycletrace/
    │   ├── LifecycleTraceApplication.java
    │   └── StartupTrace.java
    └── test/java/com/example/lifecycletrace/
        └── LifecycleOrderTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'lifecycle-event-order-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` đủ cho non-web app; `spring-boot-starter-test` có JUnit Jupiter. Nếu chạy `./gradlew` hoặc `.\gradlew.bat`, cần có Gradle Wrapper từ Spring Initializr hoặc tạo bằng Gradle tương thích. Việc chỉ thêm `build.gradle` không sinh Wrapper.

### 7.2. StartupTrace.java — recorder nhận early và late events

**`src/main/java/com/example/lifecycletrace/StartupTrace.java`:**

```java
package com.example.lifecycletrace;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

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
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;

public final class StartupTrace
        implements ApplicationListener<ApplicationEvent> {

    public record Entry(
            int sequence,
            long elapsedMicros,
            String threadName,
            String label) {
    }

    private final long beginNanos = System.nanoTime();
    private final List<Entry> entries = new ArrayList<>();

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            record("STARTING");
        } else if (event instanceof
                ApplicationEnvironmentPreparedEvent) {
            record("ENV_PREPARED");
        } else if (event instanceof
                ApplicationContextInitializedEvent) {
            record("CONTEXT_INITIALIZED");
        } else if (event instanceof ApplicationPreparedEvent) {
            record("PREPARED");
        } else if (event instanceof ContextRefreshedEvent) {
            record("CONTEXT_REFRESHED");
        } else if (event instanceof ApplicationStartedEvent) {
            record("STARTED");
        } else if (event instanceof AvailabilityChangeEvent<?> change) {
            if (change.getState() instanceof LivenessState) {
                record("LIVENESS:" + change.getState());
            } else if (change.getState() instanceof ReadinessState) {
                record("READINESS:" + change.getState());
            }
        } else if (event instanceof
                LifecycleTraceApplication.RunnerObservedEvent observed) {
            record("RUNNER:"
                    + observed.liveness() + "/"
                    + observed.readiness());
        } else if (event instanceof ApplicationReadyEvent) {
            record("READY");
        } else if (event instanceof ApplicationFailedEvent) {
            record("FAILED");
        } else if (event instanceof ContextClosedEvent) {
            record("CONTEXT_CLOSED");
        }
    }

    private synchronized void record(String label) {
        long micros = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - beginNanos);

        entries.add(new Entry(
                entries.size() + 1,
                micros,
                Thread.currentThread().getName(),
                label));
    }

    public synchronized List<Entry> snapshot() {
        return List.copyOf(entries);
    }

    public List<String> labels() {
        return snapshot().stream()
                .map(Entry::label)
                .toList();
    }

    public void printAll() {
        for (Entry e : snapshot()) {
            System.out.printf(
                    "%02d +%d us [%s] %s%n",
                    e.sequence(),
                    e.elapsedMicros(),
                    e.threadName(),
                    e.label());
        }
    }
}
```

**Tại sao code trên đúng mục tiêu?**

1. `ApplicationListener<ApplicationEvent>` nhận sự kiện từ nhiều subtype; ta lọc bằng `instanceof`.
2. `record` và `snapshot` dùng `synchronized` cho consistency nội bộ. `Entry` là immutable Java record.
3. Không giữ raw event object, không tạo static list; mỗi test tạo recorder riêng.
4. `ApplicationContextInitializedEvent`, `ApplicationEnvironmentPreparedEvent` được nhận nhờ đăng ký sớm, không phải do class recorder là bean.
5. `elapsedMicros` là khoảng thời gian từ khi recorder được tạo; không dùng làm con số startup latency cố định.
6. `printAll` thực hiện sau khi app đã chạy/đóng trong main, tránh dùng I/O logging nhiều lần bên trong listener.
7. Với đa context/async listeners, cần nâng cấp recorder thêm run/context IDs và chọn đúng ordering semantics.

### 7.3. LifecycleTraceApplication.java — bootstrap và runner marker

**`src/main/java/com/example/lifecycletrace/LifecycleTraceApplication.java`:**

```java
package com.example.lifecycletrace;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LifecycleTraceApplication {

    public static ConfigurableApplicationContext start(
            StartupTrace trace, String... args) {

        SpringApplication app =
                new SpringApplication(LifecycleTraceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.addListeners(trace); // Đăng ký trước run(args).
        return app.run(args);
    }

    public static void main(String[] args) {
        StartupTrace trace = new StartupTrace();
        ConfigurableApplicationContext context = null;

        try {
            context = start(trace, args);

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println(
                    "AFTER_RUN liveness="
                    + availability.getLivenessState()
                    + " readiness="
                    + availability.getReadinessState());
        } finally {
            try {
                if (context != null) {
                    context.close();
                }
            } finally {
                trace.printAll();
            }
        }
    }

    @Bean
    ApplicationRunner reportRunner(
            ApplicationEventPublisher publisher,
            ApplicationAvailability availability,
            Environment environment) {

        return args -> {
            publisher.publishEvent(new RunnerObservedEvent(
                    this,
                    availability.getLivenessState(),
                    availability.getReadinessState()));

            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "Controlled failure in ApplicationRunner");
            }
        };
    }

    public static final class RunnerObservedEvent
            extends ApplicationEvent {

        private final LivenessState liveness;
        private final ReadinessState readiness;

        public RunnerObservedEvent(
                Object source,
                LivenessState liveness,
                ReadinessState readiness) {

            super(source);
            this.liveness = liveness;
            this.readiness = readiness;
        }

        public LivenessState liveness() {
            return liveness;
        }

        public ReadinessState readiness() {
            return readiness;
        }
    }
}
```

**Giải thích:**

- `start(trace,args)` tạo một `SpringApplication` thật, thêm listener trước startup, rồi trả context nếu thành công.
- `WebApplicationType.NONE` khiến ví dụ không mở Web server nhưng Boot vẫn có availability.
- `reportRunner` là `ApplicationRunner`: nó phát một event chứa chính liveness/readiness tại mốc thực thi.
- Flag `demo.fail-runner` là property tự định nghĩa của demo, không phải cấu hình built-in. Khi true, runner cố ý throw sau khi publish marker.
- `main` in state **sau khi `run` trả về**, rồi đóng context để demo non-web có thể kết thúc. Không áp dụng đóng ngay cho Web service production.
- Nếu `run` throw, biến `context` có thể null; `finally` vẫn in trace, exception tiếp tục lan lên Java launcher. App không nuốt lỗi khởi động.
- `RunnerObservedEvent` kế thừa `ApplicationEvent` để Spring publisher chuyển event qua cùng hệ thống listener và recorder bắt nó.
- Code không giả lập trạng thái availability; nó đọc `ApplicationAvailability` thật từ Boot.

### 7.4. Chạy thành công

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kết quả quan trọng:

```text
AFTER_RUN liveness=CORRECT readiness=ACCEPTING_TRAFFIC
```

Các label chính trong trace của một lần startup bình thường theo thứ tự:

```text
STARTING
ENV_PREPARED
CONTEXT_INITIALIZED
PREPARED
CONTEXT_REFRESHED
STARTED
LIVENESS:CORRECT
RUNNER:CORRECT/REFUSING_TRAFFIC
READY
READINESS:ACCEPTING_TRAFFIC
CONTEXT_CLOSED
```

**Đây là subsequence nhãn để giải thích**, không phải toàn bộ stdout chính xác: chương trình còn in sequence, elapsed micros, thread name và log Boot/Gradle. Có thể có các availability/shutdown events khác trong trace khi đóng context; do đó test không nên assert một danh sách tuyệt đối chỉ có đúng từng dòng trên.

### 7.5. Chạy startup failure có kiểm soát

Linux/macOS:

```bash
./gradlew bootRun --args='--demo.fail-runner=true'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail-runner=true"
```

Runner sẽ publish marker `RUNNER:CORRECT/REFUSING_TRAFFIC`, sau đó throw `IllegalStateException`. Boot phát `ApplicationFailedEvent` khi xử lý failure. Không có `ApplicationReadyEvent` và không có event readiness accepting từ **đường startup thành công**.

Gradle có thể báo `bootRun` thất bại / process exit khác 0; đó là điều muốn quan sát ở kịch bản test lỗi, không có nghĩa recorder hỏng.

## 8. Test JUnit Jupiter: xác nhận thứ tự, failure và state

**`src/test/java/com/example/lifecycletrace/LifecycleOrderTest.java`:**

```java
package com.example.lifecycletrace;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LifecycleOrderTest {

    @Test
    void startupOrderAndAvailabilityAreCorrect() {
        StartupTrace trace = new StartupTrace();

        try (ConfigurableApplicationContext context =
                LifecycleTraceApplication.start(trace)) {

            List<String> labels = trace.labels();

            before(labels, "STARTING", "ENV_PREPARED");
            before(labels, "ENV_PREPARED", "CONTEXT_INITIALIZED");
            before(labels, "CONTEXT_INITIALIZED", "PREPARED");
            before(labels, "PREPARED", "CONTEXT_REFRESHED");
            before(labels, "CONTEXT_REFRESHED", "STARTED");
            before(labels, "STARTED", "LIVENESS:CORRECT");
            before(labels, "LIVENESS:CORRECT",
                    "RUNNER:CORRECT/REFUSING_TRAFFIC");
            before(labels, "RUNNER:CORRECT/REFUSING_TRAFFIC",
                    "READY");
            before(labels, "READY",
                    "READINESS:ACCEPTING_TRAFFIC");

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            assertEquals(
                    LivenessState.CORRECT,
                    availability.getLivenessState());
            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());
        }

        assertTrue(trace.labels().contains("CONTEXT_CLOSED"));
    }

    @Test
    void failingRunnerDoesNotBecomeReady() {
        StartupTrace trace = new StartupTrace();

        assertThrows(RuntimeException.class, () ->
                LifecycleTraceApplication.start(
                        trace, "--demo.fail-runner=true"));

        List<String> labels = trace.labels();

        assertTrue(labels.contains("STARTED"));
        assertTrue(labels.contains("LIVENESS:CORRECT"));
        assertTrue(labels.contains(
                "RUNNER:CORRECT/REFUSING_TRAFFIC"));
        assertTrue(labels.contains("FAILED"));
        assertFalse(labels.contains("READY"));
        assertFalse(labels.contains(
                "READINESS:ACCEPTING_TRAFFIC"));
    }

    @Test
    void explicitReadinessTransitionsAreRecorded() {
        StartupTrace trace = new StartupTrace();

        try (ConfigurableApplicationContext context =
                LifecycleTraceApplication.start(trace)) {

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);

            assertEquals(
                    ReadinessState.REFUSING_TRAFFIC,
                    availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);

            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());

            List<String> labels = trace.labels();
            int firstAccept =
                    labels.indexOf("READINESS:ACCEPTING_TRAFFIC");
            int refuse =
                    labels.indexOf("READINESS:REFUSING_TRAFFIC");
            int lastAccept =
                    labels.lastIndexOf("READINESS:ACCEPTING_TRAFFIC");

            assertTrue(firstAccept >= 0);
            assertTrue(refuse > firstAccept);
            assertTrue(lastAccept > refuse);
        }
    }

    private static void before(
            List<String> labels, String earlier, String later) {

        int a = labels.indexOf(earlier);
        int b = labels.indexOf(later);

        assertTrue(
                a >= 0 && b > a,
                () -> "Expected " + earlier
                        + " before " + later
                        + " in " + labels);
    }
}
```

### 8.1. Điều các test chứng minh

**Test 1** gọi `SpringApplication.run` thật với recorder đã đăng ký trước đó. Nó assert các quan hệ trước–sau, kiểm tra `ApplicationAvailability` sau Ready, rồi close context và xác nhận `ContextClosedEvent` đã được recorder nhìn thấy.

**Test 2** cho runner thất bại có kiểm soát, `assertThrows` bảo đảm startup không thành công; event `FAILED` có, các event Ready/accepting không có. Không cố lấy bean `ApplicationAvailability` từ context mà `run` không trả về.

**Test 3** publish refusing rồi accepting sau startup, so cả `ApplicationAvailability` và trace. Sử dụng `firstAccept` và `lastAccept` giúp phân biệt **accepting lúc Boot Ready** với **accepting mới do test khôi phục**.

### 8.2. Cách chạy test

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Code test tạo recorder/context mới cho từng method và chủ động close, không dựa vào một static global event list. Những asserts quan trọng đều dựa vào logic event/availability chứ không dựa vào số milliseconds cố định.

### 8.3. Vì sao không Thread.sleep?

Ở cấu hình dispatcher đồng bộ thông thường, khi `SpringApplication.run` trả về và khi `AvailabilityChangeEvent.publish` trả về, listener tương ứng đã xử lý trên luồng publish. `Thread.sleep(100)` không tăng độ đúng đắn, chỉ làm test chậm và flaky. Nếu dùng async multicaster, chuyển sang `CountDownLatch` hoặc future có deadline, không dùng sleep để đoán event đã đến.

## 9. @RecordApplicationEvents thuộc Spring TestContext, khác early capture

Spring Framework TestContext có:

- `@RecordApplicationEvents`: kích hoạt event recording trong test context.
- `ApplicationEvents`: duyệt events đã ghi bằng `stream()`.
- `ApplicationEventsTestExecutionListener`: hỗ trợ đăng ký recording theo vòng đời test method.

Khung tích hợp:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class BusinessEventsTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Test
    void observesEventFromTestMethod(ApplicationEvents events) {
        publisher.publishEvent(new DomainEvent(this));

        assertEquals(
                1L,
                events.stream(DomainEvent.class).count());
    }
}
```

**Không phải file runnable độc lập:** phải import annotations/types và định nghĩa `DomainEvent`. Nó minh họa việc test **một event phát từ test method**, không bảo đảm bắt toàn bộ `ApplicationStartingEvent` trước khi context được khởi tạo.

Một test method bắt đầu sau Spring TestContext bootstrap; vì vậy không kỳ vọng `@RecordApplicationEvents` sẽ tự cấp dữ liệu của mọi early event mà `SpringApplication` phát trước đó.

| Việc cần làm | Công cụ phù hợp |
|---|---|
| Bắt `ApplicationStartingEvent` | `SpringApplication.addListeners` trước `run` |
| Test Started → runner → Ready | Early listener + runner marker |
| Test state sau startup | `ApplicationAvailability` |
| Test custom event publish trong JUnit method | `@RecordApplicationEvents` |
| Test readiness change | `AvailabilityChangeEvent.publish` + state/assertions |
| Test shutdown của resource | `SmartLifecycle` callback/termination markers |
| Test HTTP routing/probe | Actuator Web integration test |

## 10. Kiểm thử readiness động trong ứng dụng

Khi queue quá tải hoặc một điều kiện quan trọng khiến instance chưa thể nhận thêm traffic, ứng dụng có thể publish:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
```

Sau khi phục hồi:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.ACCEPTING_TRAFFIC);
```

Đây là snippet tích hợp. Method overload nhận `ApplicationContext` được Spring Boot cung cấp; ngoài context, cũng có overload nhận `ApplicationEventPublisher`, source và state.

**Lưu ý chính sách:** nếu nhiều subsystem tự publish accepting/refusing, một event accepting mới có thể ghi đè trạng thái refusing từ subsystem khác. Hãy thiết kế một coordinator tổng hợp các điều kiện, chỉ publish accepting khi tất cả điều kiện thiết yếu đều đã đúng.

Không dùng liveness BROKEN để xử lý mọi trường hợp tạm thiếu traffic capacity. Và publish readiness không làm load balancer lập tức ngắt mọi connection đang tồn tại; còn độ trễ probe/routing và công việc drain ở tầng HTTP/worker.

### Ví dụ service publish event

```java
@Service
class ReadinessCoordinator {

    private final ApplicationEventPublisher publisher;

    ReadinessCoordinator(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pauseTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Đây là snippet tích hợp cần import. Trong production cần thêm chính sách khi có nhiều nguồn tình trạng và concurrency, không để mọi service được tùy tiện resume cùng một trạng thái chung.

## 11. Actuator HTTP probes so với state trong JVM

Nếu thêm `spring-boot-starter-actuator` vào một ứng dụng **Web** và cấu hình phù hợp, có thể kiểm tra:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Trong Kubernetes, các probe health groups có thể được bật tự động. Ở môi trường khác có thể cấu hình:

```properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
```

Cấu hình này **không tạo HTTP endpoint cho demo non-web** ở phần 7. Cần Web stack và Actuator thật.

Phân biệt:

1. **State nội bộ:** `ApplicationAvailability` trả về liveness/readiness.
2. **Health indicator:** Boot/Actuator chuyển state thành health response.
3. **HTTP endpoint:** server và management exposure quyết định URL có được phục vụ không.
4. **Orchestrator:** Kubernetes nhận kết quả probe, quyết định instance có nhận traffic; cập nhật không tức thì.

`REFUSING_TRAFFIC` thường tương ứng trạng thái health không sẵn sàng (ví dụ `OUT_OF_SERVICE`) và HTTP 503 trong mapping mặc định; cấu hình status mapping có thể đổi, nên test HTTP phải dựa vào chính project.

Nếu management server chạy trên **port riêng**, probe có thể báo khỏe dù port ứng dụng chính bị lỗi. Với use case này, cần kiểm tra hướng dẫn exposure probes trên main server port và an ninh endpoint; không mở toàn bộ Actuator công khai.

## 12. Kiểm thử ContextClosedEvent và shutdown đúng cách

Trong một lần `context.close()` bình thường:

```text
ContextClosedEvent
      |
LifecycleProcessor.onClose()
      |
SmartLifecycle.stop(Runnable) theo phase
      |
chờ callback hoặc hết timeout mỗi phase
      |
destroy singleton beans
  @PreDestroy / DisposableBean / destroy-method
      |
close() trả về
```

**`ContextClosedEvent` xuất hiện ở đầu đường đóng context**, không phải event “tất cả tài nguyên đã dừng thành công”.

Nếu một consumer cần writer, có thể dùng `getPhase()=200` cho consumer và `100` cho writer. Khi stop, consumer phase cao được yêu cầu dừng trước, và `SmartLifecycle.stop(Runnable)` chỉ nên gọi callback sau khi consumer đã hoàn tất drain; Spring mới có cơ sở tiến tới writer phase thấp. Nếu quên callback, lifecycle processor có thể chờ tới timeout phase. Nếu callback sớm, writer có thể đóng khi consumer vẫn dùng nó.

Muốn test shutdown, hãy thu thập thêm markers từ resource thật:

```text
CONTEXT_CLOSED
CONSUMER_STOP_BEGIN
CONSUMER_DRAINED
CONSUMER_STOP_CALLBACK
WRITER_STOP_BEGIN
WRITER_STOP_CALLBACK
CONSUMER_DESTROY
WRITER_DESTROY
```

Đây là **timeline minh họa**, không phải event list tự động Boot phát. Thứ tự destroy còn phụ thuộc cấu hình dependency/bean destruction; test cần dựa trên contract thật, không áp đặt tùy tiện.

Ngoài ra, `context.close()` có thể đã return nhưng một worker non-daemon do ứng dụng tự tạo vẫn sống nếu bạn không stop nó. Java process có thể tiếp tục chạy theo đường close trực tiếp; không lấy `ContextClosedEvent` làm bằng chứng process đã thoát.

## 13. Event hierarchy, async dispatcher và thứ tự quan sát

### 13.1. Parent-child contexts

Spring event propagation cho phép event từ child context truyền tới parent. Một listener có thể thấy nhiều event cùng loại từ nhiều context. Khi test, ghi `contextId` hoặc so sánh `ApplicationContext` trong event với context cần kiểm tra, không assert count=1 theo toàn ứng dụng phức tạp.

### 13.2. Listener bất đồng bộ

Nếu event multicaster dùng executor, thứ tự xử lý listener có thể bị đảo so với thứ tự publish. Test cần:

- Phân biệt publish order và observed delivery order.
- Dùng `CountDownLatch`/future với deadline để chờ các event cần thiết.
- Có correlation ID nếu cần ghép event với một thao tác.
- Không suy happens-before từ thứ tự timestamp ở các thread không có synchronization.
- Không cố sửa bằng `Thread.sleep` cố định.

### 13.3. @Order và phase không thay cho completion

`@Order` có thể ảnh hưởng thứ tự runner/listener trong phạm vi thích hợp, nhưng không bảo đảm toàn bộ JVM bean init, async tasks hay shutdown tuần tự theo nó. `SmartLifecycle.getPhase()` phục vụ thứ tự lifecycle start/stop; completion của task vẫn cần future/latch/callback riêng.

### 13.4. Nhiều lần publish cùng state

Có thể có hai `AvailabilityChangeEvent(REFUSING_TRAFFIC)` liên tiếp. Trừ khi ứng dụng có hợp đồng publish đúng một lần, test nên kiểm tra state cuối hoặc **thứ tự transitions cần thiết**, không mặc định mỗi enum state chỉ xuất hiện một lần trong toàn bộ run.

### 13.5. Test fail ở các giai đoạn khác nhau

| Nơi lỗi xảy ra | Có thể đã có | Không được mặc định có |
|---|---|---|
| Environment preparation | `STARTING` và `FAILED` | `ContextRefreshedEvent` |
| Bean definition loading | Một số event trước refresh, `FAILED` | `STARTED` |
| Singleton construction trong refresh | `PREPARED`, `FAILED` | `READY` |
| Runner | `STARTED`, liveness correct, runner marker, `FAILED` | Ready/accepting |
| Ready listener ném lỗi | Có thể `ApplicationReadyEvent` đã được publish | Readiness accepting đã công bố |
| Async background job sau Ready | App đã có thể Ready | `ApplicationFailedEvent` của startup |

Một startup failure trong runner khác với startup failure trước context. Test cần chọn invariants phù hợp. Nếu lỗi xảy ra **sau Ready** trong `@Async`/scheduler, `ApplicationFailedEvent` không tự được phát giống lỗi `SpringApplication.run`.

## 14. Chẩn đoán các test thất bại

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| Không thấy `STARTING` | Listener đăng ký sau run hoặc chỉ là bean | `addListeners` trước run |
| Có `STARTED`, thiếu runner marker | Runner không chạy hoặc sai event type | Kiểm tra `@Bean ApplicationRunner` |
| Runner readiness đã accepting | Custom code publish accepting quá sớm | Tìm mọi `AvailabilityChangeEvent.publish` |
| Normal run thiếu `READY` | Runner/listener khác ném exception | Xem `ApplicationFailedEvent`/stack |
| Thiếu accepting event | Recorder filter sai state/event, startup fail | Kiểm tra `AvailabilityChangeEvent<?>` |
| State và trace mâu thuẫn | Khác context, publish đồng thời hoặc async listener | Gắn context/run ID, xác định mốc |
| Count=1 fail trong child context | Event propagated hoặc refresh lặp | Filter context identity |
| Event order flaky trên CI | Async event processing không chờ | Dùng completion/latch |
| `CONTEXT_CLOSED` có nhưng process sống | Executor/thread chưa shutdown | Kiểm tra resource termination |
| Timeout assert fail | Dựa vào milliseconds cố định | Assert order/semantic state thay thời gian |
| Test sau ảnh hưởng test trước | Static recorder hoặc context cache | Recorder mới cho từng lần chạy |
| HTTP probe không tồn tại | Non-web, Actuator chưa bật/expose | Chạy Web integration test phù hợp |
| Liveness BROKEN khi DB ngoài mất | Nhầm readiness/liveness | Sửa phân loại trạng thái |

Không khắc phục bằng cách bỏ bừa các assertions cần thiết. Đọc timeline và thread names, xác định sai ở **điểm ghi event**, **điểm publish**, **state source** hay **expectation**.

## 15. Bảo mật và chi phí event tracing

Listener xử lý đồng bộ theo mặc định có thể làm startup chậm nếu mỗi event ghi I/O nặng. Trong demo, recorder chỉ append một Entry nhỏ, in sau khi đã quan sát. Trong production, cần bounded/ring buffer hoặc logging có kiểm soát để không giữ event vô hạn trong heap.

Trace có thể chứa tên class, context IDs, thread names, cấu hình và thông tin lỗi. Tránh lưu secrets hoặc payload PII. Nếu lưu exception, sanitize thay vì giữ trọn graph `Throwable`/`ApplicationContext` trong static collection.

Khi nhiều replicas, dùng correlation ID/process ID và timestamp thích hợp; không so hai `System.nanoTime` từ hai JVM như cùng một clock. Actuator health endpoints phải có access control, không bật tất cả endpoint công khai chỉ để quan sát lifecycle.

## 16. Bài thực hành

**Bài 1 — baseline:** chạy test và ứng dụng, ghi thứ tự `STARTING → ENV_PREPARED → CONTEXT_INITIALIZED → PREPARED → CONTEXT_REFRESHED → STARTED → LIVENESS:CORRECT → RUNNER → READY → READINESS:ACCEPTING_TRAFFIC`.

**Bài 2 — listener quá muộn:** bỏ `app.addListeners(trace)`, thay bằng `@Component @EventListener` rồi so những early events không còn thấy. Giải thích theo mốc tạo context.

**Bài 3 — kiểm tra state ở runner:** so `LivenessState.CORRECT` và `ReadinessState.REFUSING_TRAFFIC` được đọc ngay trong runner; không tự publish accepting để làm bài test dễ pass.

**Bài 4 — runner failure:** chạy `--demo.fail-runner=true`, assert `FAILED`, không có Ready hoặc accepting. Sau đó tạo một failure trước refresh và điều chỉnh expectations.

**Bài 5 — readiness transitions:** publish refusing rồi accepting sau Ready; so `ApplicationAvailability.getReadinessState()` và event trace; đọc `getLastChangeEvent`.

**Bài 6 — recorder race:** tạo hai publisher threads, ghi sequence bằng recorder. Vì sao thứ tự recorder khác event semantic ordering trong một hệ thống async?

**Bài 7 — @RecordApplicationEvents:** viết test có `@SpringBootTest` và publish custom domain event trong method; chứng minh nó không thay early listener cho `ApplicationStartingEvent`.

**Bài 8 — Web/Actuator:** tạo Web app có Actuator, bật probes rồi kiểm tra response `/actuator/health/readiness` và state in-memory. Phân biệt HTTP probe khỏi state nội bộ.

**Bài 9 — graceful shutdown:** thêm `SmartLifecycle` consumer và writer với phase khác nhau, ghi marker `STOP_BEGIN` và `STOP_CALLBACK`, chỉ assert completion sau callback.

**Bài 10 — callback bị quên:** trong test cô lập, cố tình bỏ callback để thấy phase timeout; khôi phục ngay sau khi quan sát, không áp dụng vào production.

**Bài 11 — multiple contexts:** dùng parent/child context và thêm context ID vào Entry; sửa assertion chỉ xét events thuộc context mục tiêu.

**Bài 12 — async work:** runner submit `CompletableFuture` mà không đợi; xác nhận Ready có thể đến trước completion. Sau đó thiết kế một cách đợi hợp lệ trước Ready.

**Bài 13 — phối hợp nhiều health sources:** mô phỏng hai điều kiện readiness. Đảm bảo một nguồn chưa phục hồi thì nguồn khác không thể publish accepting qua coordinator.

**Bài 14 — test không sleep:** với event async, dùng `CountDownLatch` hoặc Future để chờ thay vì `Thread.sleep(100)`; giải thích happens-before.

**Bài 15 — viết báo cáo:** ghi Boot/JDK version, event list đã lọc, thứ tự assertions, state runner/after Ready, kết quả failure test, shutdown completion và giới hạn của observation.

### Câu hỏi tự đánh giá

1. `ApplicationStartedEvent` có trước hay sau runner?
2. Boot công bố `LivenessState.CORRECT` trước hay sau `ApplicationStartedEvent`?
3. Trong runner, readiness mặc định là gì?
4. `ApplicationReadyEvent` và event `ReadinessState.ACCEPTING_TRAFFIC` xuất hiện theo thứ tự nào?
5. Vì sao `@EventListener` bean không bắt đáng tin `ApplicationStartingEvent`?
6. `ApplicationAvailability.getReadinessState()` có giống “đã quan sát một event refusing” không?
7. `@RecordApplicationEvents` có phù hợp để ghi toàn bộ bootstrap events hay chủ yếu events trong test method?
8. Vì sao kiểm thử partial order tốt hơn assert nguyên danh sách tuyệt đối?
9. Khi runner throw, các mốc Ready/accepting có được phát bình thường không?
10. `ContextClosedEvent` có chứng minh worker đã dừng hoàn toàn không?
11. Nếu event multicaster chạy async, vì sao observed order có thể khác publish order?
12. Vì sao readiness accepting không bảo đảm HTTP load balancer đã lập tức route traffic?

## 17. Checklist hoàn thành

- [ ] Dùng listener đăng ký trước `run` để bắt early events.
- [ ] Dùng recorder riêng cho từng test/lần run.
- [ ] Ghi label, sequence, elapsed time và thread, không giữ context object lâu dài.
- [ ] Assert Started trước runner, runner trước Ready.
- [ ] Assert Correct sau Started, accepting sau Ready.
- [ ] Kiểm tra readiness Refusing trong runner bằng state thật.
- [ ] Không bắt buộc có một event refusing ở đầu startup khi state mới là mặc định.
- [ ] Test runner failure bằng `assertThrows` và sự vắng mặt của Ready/accepting.
- [ ] Test publish readiness và đọc lại `ApplicationAvailability`.
- [ ] Test context close và resource completion riêng biệt.
- [ ] Không assert toàn bộ event list cho ứng dụng có nhiều contexts/optional events.
- [ ] Async listener phải có completion signal thay vì ngủ cố định.
- [ ] Tách Actuator Web probe tests khỏi in-memory availability tests.
- [ ] Không leak secrets, có giới hạn lưu trace.

## 18. Kết luận

Để kiểm thử Spring Boot Application Runtime, cần kết hợp **trace events** và **availability state**. Một lần startup thành công của Boot 3.3 có chuỗi cốt lõi `ApplicationStartedEvent` → `LivenessState.CORRECT` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`. Trong runner, readiness vẫn có thể và thường là `REFUSING_TRAFFIC`.

`SpringApplication.addListeners` trước `run` là cách đơn giản để bắt các early events. `@RecordApplicationEvents` hữu ích cho events trong test method, không thay được listener bootstrap. `AvailabilityChangeEvent.publish` cho phép chủ động thay đổi state để kiểm thử, nhưng các probe HTTP/routing ngoài JVM cần integration test riêng. `ContextClosedEvent` cho biết close đã bắt đầu, không có nghĩa toàn bộ resource đã dừng.

Test nên xác nhận **thứ tự các mốc có ý nghĩa và trạng thái tại thời điểm liên quan**, không dùng log trọn vẹn hay thời gian tuyệt đối làm hợp đồng mong manh.

### Tài liệu chính thức

- Spring Boot 3.3 — Application Events, Listeners và Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator Probes và Application Lifecycle States: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationAvailability API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3 — AvailabilityChangeEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Framework — Testing Application Events (@RecordApplicationEvents): https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework 6.1 — SmartLifecycle API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — ContextClosedEvent API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/ContextClosedEvent.html