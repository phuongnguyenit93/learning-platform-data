# Đo thời gian khởi động context, container và từng nhóm test trong Spring Boot

## 1. Vì sao Spring Boot test suite có thể chậm dù assertions rất nhanh?

Một bộ test có thể chỉ mất vài mili-giây để kiểm business logic nhưng phải chờ hàng chục giây cho JVM, Spring context, database và Docker. Các nguyên nhân thường nằm ở những pha khác nhau:

- Gradle cấu hình project, resolve dependency, compile và mở forked Test JVM.
- JUnit Platform discover classes, đăng ký extensions và tạo test instances.
- Spring TestContext Framework tìm cache, tạo context khi cache miss, khởi tạo bean, chạy auto-configuration.
- `@SpringBootTest` kích hoạt Flyway, Hibernate, HikariCP, embedded server hoặc application runners nếu được cấu hình.
- Testcontainers phải tìm/pull Docker image, create/start container rồi chờ service sẵn sàng.
- Mỗi class có profile, mock bean, dynamic property hoặc `@DirtiesContext` khác nhau có thể khiến Spring phải load context mới.
- Test fixtures, SQL cleanup, HTTP calls và teardown container chạy ngoài test method.
- Gradle mở nhiều worker JVMs nên context cache không thể chia sẻ qua các process.

**Đề bài không phải “in một con số test duration”, mà là đo và phân biệt ba nhóm chi phí: khởi động Spring context, khởi động container, và thực thi từng nhóm/test.** Khi biết nút thắt thực tế, ta mới quyết định nên dùng test slice, tái sử dụng context/container hay tối ưu dữ liệu/migration.

### Sau bài này, bạn có thể

1. Phân biệt Gradle build wall time, Test task wall time, test class, method body, context cache lookup/load, Docker startup, first query và shutdown.
2. Dùng `System.nanoTime()` đo elapsed duration thay cho đồng hồ wall-clock.
3. Hiểu cache key của Spring TestContext, cache hit/miss, giới hạn mặc định 32 và `@DirtiesContext`.
4. Đo từng class/test method qua JUnit Jupiter extension, biết mốc nào bao gồm hoặc loại trừ fixtures.
5. Đo lần lấy `TestContext.getApplicationContext()` bằng `TestExecutionListener` ưu tiên cao.
6. Tạo Gradle Test tasks riêng cho unit/context/container groups, đọc reports HTML và JUnit XML.
7. Tự đo `PostgreSQLContainer.start()`, `SpringApplication.run()`, SQL đầu tiên và `stop()`.
8. Phân biệt `@Container` static/instance với Testcontainers container do Spring context sở hữu.
9. Dùng Spring Boot `BufferingApplicationStartup`, Actuator, startup metrics và JFR để tìm bean/step chậm.
10. Thiết kế so sánh cold/warm và baseline/after có ý nghĩa thống kê, không bịa timing hay tạo flaky assertions.

## 2. Mô hình timeline: không cộng các số đo một cách máy móc

~~~text
./gradlew test
  |
  +-- Gradle initialization/configuration/task graph
  +-- Dependency resolution / compile
  |
  +-- Gradle Test task wall time ------------------------------+
  |     |
  |     +-- Start test worker JVM
  |     +-- JUnit discovery / extensions
  |     |
  |     +-- Test class A
  |     |     +-- Spring context cache LOOKUP
  |     |     |     +-- HIT: reuse context
  |     |     |     +-- MISS: create/refresh context
  |     |     +-- BeforeAll/BeforeEach
  |     |     +-- method execution
  |     |     +-- AfterEach/AfterAll
  |     |
  |     +-- Test class B, possibly reuse context A
  |     +-- Tear down/reports
  |
  +-- Remaining Gradle tasks/reporting
~~~

Nếu test dùng Testcontainers, chi phí có thể được tách thêm:

~~~text
t0 -> container.start() -> t1
t1 -> SpringApplication.run() -> t2
t2 -> first JDBC query -> t3
t3 -> Spring context close -> t4
t4 -> container.stop() -> t5
~~~

Đây là **các mốc**, không phải một công thức cộng đúng cho mọi test. Ví dụ `@SpringBootTest` thường dựng context trong SpringExtension callbacks trước khi test body chạy; đồng hồ nằm trong `@Test` có thể bỏ sót chi phí đó.

### 2.1 Đặt tên metric thật rõ

| Tên | Bắt đầu–kết thúc | Điều có thể nằm trong khoảng |
| --- | --- | --- |
| `build.wall.ms` | Trước/sau command Gradle | Compile, caches, daemon, test/report |
| `gradle.test.task.ms` | Gradle Test task start/end | Test JVM fork, JUnit, setup, reports |
| `junit.class.ms` | JUnit BeforeAllCallback–AfterAllCallback | Class lifecycle, có thể không bao gồm context pre-load |
| `junit.method.ms` | BeforeTestExecution–AfterTestExecution | Test method body, không bao gồm @BeforeEach/AfterEach |
| `spring.lookup_or_load.ms` | Trước/sau `getApplicationContext()` | Cache lookup hoặc context creation nếu MISS |
| `container.start.ms` | Trước/sau `container.start()` | Docker/image/start/wait tùy trạng thái |
| `spring.run.ms` | Trước/sau SpringApplication.run | Boot bootstrap đến ready, gồm runners |
| `jdbc.first_query.ms` | Trước/sau SQL đầu | Có thể bao gồm lazy pool connection |
| `container.stop.ms` | Trước/sau container.stop() | Best-effort Docker teardown |

**Không cộng trực tiếp** `junit.class.ms + spring.run.ms + container.start.ms` nếu các đồng hồ đo những khoảng chồng lấn hoặc thuộc JUnit lifecycle khác nhau. Tách boundary rồi xem timeline thực tế.

## 3. Dùng System.nanoTime() thay currentTimeMillis()

Để đo duration trong cùng JVM:

~~~java
long start = System.nanoTime();

doWork();

double elapsedMs =
        (System.nanoTime() - start) / 1_000_000.0;
~~~

Đây là đoạn minh họa, cần `doWork()`. `System.nanoTime` là monotonic-style elapsed-time source, không phải timestamp lịch sử và không dùng để so trực tiếp giữa các process/machines. `System.currentTimeMillis` là wall clock có thể bị NTP hoặc OS điều chỉnh, không phù hợp để đo một method nhỏ.

### 3.1 Đồng hồ không làm test thành benchmark chuẩn

- Log mỗi lần đo có overhead, đặc biệt khi test body cực ngắn.
- JIT/class loading, GC, CPU scheduling và thermal throttling ảnh hưởng kết quả.
- Một run đẹp không có ý nghĩa thống kê.
- Nếu cần microbenchmark ở nano/microsecond level, dùng **JMH** thay vì một JUnit test.
- Đừng viết `assertTrue(elapsedMs < 100)` trên shared CI chỉ vì laptop local đạt 20ms.

JUnit timing dùng để **chẩn đoán suite**, không thay performance SLO testing.

## 4. Spring TestContext cache thực sự hoạt động như thế nào?

Spring TestContext lưu những `ApplicationContext` đã tạo theo `MergedContextConfiguration`. Khi test class tiếp theo dùng cùng cache key và chạy trong **cùng JVM**, framework có thể trả lại context cũ.

~~~text
ContextGroupATest -> key K -> CACHE MISS -> tạo context X
ContextGroupBTest -> key K -> CACHE HIT  -> reuse X
ContextGroupCTest -> key L -> CACHE MISS -> tạo context Y
@DirtiesContext  -> evict/close context bị đánh dấu dirty
~~~

Đây là mô hình, không khẳng định Gradle luôn chạy A trước B. Class nào đến đầu tiên với key K sẽ chịu cold context load.

### 4.1 Những yếu tố tạo context cache key

- `@ContextConfiguration` classes, locations, initializers.
- ContextLoader, parent context/hierarchy.
- `@ActiveProfiles`.
- `@TestPropertySource` và `@SpringBootTest(properties=...)`.
- Web resource base path/context customizers.
- Bean override như `@MockitoBean`, Boot test slice annotations.
- `@DynamicPropertySource` customizer methods và các test customizers khác.

Hai test classes có tên khác nhau vẫn **có thể** dùng chung context. Hai test cùng `@SpringBootTest` nhưng khác một mock hoặc một profile thường phải load hai contexts.

### 4.2 Default maxSize là 32

Spring Framework 6.2 định nghĩa `ContextCache.DEFAULT_MAX_CONTEXT_CACHE_SIZE = 32`. Khi đầy, cache dùng LRU-style eviction và đóng context cũ.

Có thể thay bằng JVM system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Đặt property trên **forked test JVM**, không chỉ Gradle daemon. Bài có code Gradle forward nó từ Gradle JVM sang Test task.

**Tăng lên 64 không mặc nhiên nhanh hơn:** giữ thêm Hibernate/Hikari/Redis/executor contexts tăng memory, GC và số resources mở. Đo hit/miss, memory, full suite time trước khi thay.

### 4.3 Context cache chỉ trong cùng process

- `maxParallelForks=4` có thể tạo 4 JVMs với 4 caches độc lập.
- `forkEvery=1` tạo process mới sau mỗi class → giảm mạnh cơ hội reuse.
- Hai lần chạy `./gradlew test` không chia sẻ static Spring TestContext cache dù Gradle daemon vẫn sống.
- Nếu Gradle báo `UP-TO-DATE`, test **có thể không hề chạy**, nên không dùng tổng thời gian đó để so tốc độ context.

### 4.4 @DirtiesContext là công cụ đúng nhưng đắt

`@DirtiesContext` cho Spring biết context bị mutate không thể dùng lại an toàn và cần đóng/evict. Dùng khi test thật sự thay đổi bean definition, state/thiết lập không thể reset, nhưng **không** dùng theo thói quen ở mọi method.

Nếu có thể reset DB fixtures, caches, queues, singleton state và mocks giữa tests, hãy làm đúng cleanup để giữ context. Nếu không thể bảo đảm isolation, chấp nhận context reload; tính đúng quan trọng hơn vài giây.

## 5. Đọc thống kê Spring context cache

Bật:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Những logs của `org.springframework.test.context.cache` cung cấp `size`, `maxSize`, `hitCount`, `missCount` và thông tin khác tùy framework version.

Ví dụ **định dạng minh họa, không phải log đo thực tế**:

~~~text
context cache: size=2 maxSize=32 hitCount=17 missCount=2
~~~

Lưu ý:

- `missCount` liên quan việc truy cập key chưa có cache; thường dẫn tới load.
- `hitCount` có thể tăng nhiều lần **trong cùng một test class** vì SpringExtension/DI/listener truy cập context nhiều lần.
- Không tính số cache hits bằng số test methods.
- `@DirtiesContext` và LRU eviction có thể làm cùng config phải load lại.
- Một context MISS tốn 15s do DB migrations đáng chú ý hơn 100 cache hits nhanh.

Để tìm nguyên nhân chậm, xem **cache misses + time-per-miss + group wall time** cùng nhau.

## 6. Đo context load: dùng TestExecutionListener

Một `TestExecutionListener` có `getOrder()` ưu tiên rất cao có thể kích hoạt `testContext.getApplicationContext()` ngay khi `beforeTestClass` chạy:

~~~text
beforeTestClass:
   t0 = nanoTime
   context = testContext.getApplicationContext()
   elapsed = nanoTime - t0
   log class, context identity, elapsed
~~~

Nếu context chưa được nạp, stopwatch có thể bao gồm bước load/refresh; nếu cached, nó đo lookup.

**Không gọi nó là “toàn bộ Spring Boot startup”**: các bootstrap callbacks có thể đã chạy trước đồng hồ, và listener này chủ động ảnh hưởng thời điểm context được load. Nó là công cụ chẩn đoán đúng phạm vi `lookup_or_load`.

## 7. Đo class và method với JUnit Jupiter extension

Hai cặp callbacks:

| Callback pair | Đo được | Không tự bao gồm |
| --- | --- | --- |
| `BeforeAllCallback` / `AfterAllCallback` | Một phần vòng đời class | Toàn test process nếu extension được gọi sau context setup |
| `BeforeTestExecutionCallback` / `AfterTestExecutionCallback` | Body `@Test` | `@BeforeEach`, `@AfterEach` |
| `BeforeEachCallback` / `AfterEachCallback` | Vòng đời quanh từng method | Toàn context startup nếu xảy ra trước |
| `TestReporter.publishEntry` | Gửi metric key/value vào JUnit execution | Không bảo đảm mọi renderer đều hiển thị |

Việc đăng ký extension trước/sau SpringExtension có thể làm timestamp class khác nhau. Bài dùng JUnit extension cho class/method và listener riêng cho context, không gộp hai số thành một.

## 8. Đo container startup đúng cách

`PostgreSQLContainer.start()` của Testcontainers có thể làm:

1. Kiểm tra Docker daemon/client và environment.
2. Xác định image local hoặc kéo image từ registry khi chưa cached.
3. Tạo network/container/helper resource.
4. Start PostgreSQL process.
5. Chờ container đáp ứng wait strategy/readiness.
6. Trả quyền điều khiển về test.

Thời gian đo này **không phải riêng PostgreSQL binary startup**. Trên clean CI agent, image pull có thể lớn; trên laptop image đã cached, start nhanh hơn.

### 8.1 Cold vs warm

| Trạng thái | Bao gồm |
| --- | --- |
| Cold image & Docker | Image pull + Docker setup + container start |
| Warm image, new container | Không pull image, vẫn create/start/wait |
| Shared static @Container | Một lần mỗi test class, nhiều methods cùng dùng |
| Reusable container | Có thể giữ process qua runs, phải quản lý cleanup |
| Spring-managed container bean | Lifecycle gắn với ApplicationContext |

Để đo container thật, **bắt đầu stopwatch ngay trước `container.start()`**, không bắt đầu trong `@BeforeAll` nếu `@Testcontainers` extension đã start static @Container trước đó.

### 8.2 Phải tách application ready và database ready

Container có thể sẵn sàng nhận TCP/SQL nhưng Spring vẫn đang khởi tạo Hikari pool, Flyway, Hibernate và runners.

~~~text
container.start() completes
   |
   +-- PostgreSQL accepts connections
   |
SpringApplication.run()
   +-- context refresh
   +-- JDBC auto-configuration
   +-- DB migration if present
   +-- runners/ready
   |
first JdbcTemplate.queryForObject()
   +-- may initialize lazy connection pool
~~~

Đo riêng các mốc; không suy “container.start=DB migrations” hoặc “Boot ready=first SQL done”.

## 9. Bộ ví dụ hoàn chỉnh Java 17+ và Spring Boot 3.5

Bài thực hành gồm ba nhóm:

- **unit:** JUnit thuần, không Spring.
- **context:** hai `@SpringBootTest` classes cùng config, quan sát cache reuse.
- **container:** một test opt-in Docker, tự start PostgreSQL rồi chạy một SpringApplication context **fresh**.

Tất cả timing values được in/publish tại runtime; bài **không bịa số giây** hay coi expected values là log thực.

Cấu trúc:

~~~text
context-timing-demo/
  settings.gradle
  build.gradle
  src/main/java/example/perf/
    BenchmarkApplication.java
    GreetingService.java
  src/test/java/example/perf/
    TimingExtension.java
    ContextLookupTimingListener.java
    PureUnitTimingTest.java
    ContextGroupATest.java
    ContextGroupBTest.java
    PostgresContainerTimingTest.java
  src/test/resources/
    application.properties
~~~

Có **7 JUnit @Test methods**: hai unit, bốn context, một Docker. Docker test bị SKIPPED khi không có environment `RUN_DOCKER_BENCH=true`. Không cần external server cho unit/context groups.

## 10. settings.gradle

~~~groovy
rootProject.name = 'context-timing-demo'
~~~

## 11. build.gradle: cấu hình nhóm test

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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    maxParallelForks = 1
    forkEvery = 0

    // Property phải đến được forked test JVM.
    systemProperty 'spring.test.context.cache.maxSize',
            System.getProperty(
                'spring.test.context.cache.maxSize', '32')

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }

    reports {
        html.required = true
        junitXml.required = true
    }
}

def addBenchGroup = { String taskName, String junitTag ->
    tasks.register(taskName, Test) {
        group = 'verification'
        description = 'Measure JUnit group: ' + junitTag
        dependsOn tasks.named('testClasses')
        testClassesDirs = sourceSets.test.output.classesDirs
        classpath = sourceSets.test.runtimeClasspath

        useJUnitPlatform {
            includeTags junitTag
        }
    }
}

addBenchGroup('unitBench', 'unit')
addBenchGroup('contextBench', 'context')
addBenchGroup('containerBench', 'container')
~~~

File dùng Spring Boot BOM quản lý Testcontainers/JUnit dependency versions. Các bản pin 3.5.0 và 1.1.7 là **mốc ví dụ**, không khẳng định chúng là mới nhất.

`maxParallelForks=1`/`forkEvery=0` giúp cache reuse trong từng Gradle Test task. Ba task `unitBench`, `contextBench`, `containerBench` **vẫn chạy các test JVMs riêng**; không mong Spring cache tồn tại qua ba tasks.

`useJUnitPlatform { includeTags ... }` đảm bảo mỗi task chỉ đo đúng nhóm. Task `test` mặc định có thể chạy tất cả; Docker test disabled nếu env chưa bật.

## 12. src/test/resources/application.properties

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.root=WARN
~~~

Bật cache diagnostics trong Spring Boot test contexts. Với bài benchmark baseline có thể hạ mức DEBUG sau khi đã thu thập cache statistics, vì logging overhead có thể ảnh hưởng timing.

## 13. BenchmarkApplication.java

~~~java
package example.perf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BenchmarkApplication {
    public static void main(String[] args) {
        SpringApplication.run(BenchmarkApplication.class, args);
    }
}
~~~

Vì app có JDBC starter, chạy main mà không có JDBC URL hoặc exclude `DataSourceAutoConfiguration` có thể fail. Trong hai context groups, bài **exclude JDBC auto-configuration** bằng test property; Docker group cung cấp PostgreSQL URL/credentials thật.

## 14. GreetingService.java

~~~java
package example.perf;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + Objects.requireNonNull(name);
    }
}
~~~

Business method cố tình đơn giản và deterministic: mục tiêu đo startup overhead, không phải đánh giá throughput của String concatenation.

## 15. TimingExtension.java: đo từng group/class và method

File `src/test/java/example/perf/TimingExtension.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.junit.jupiter.api.extension.AfterAllCallback;
import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeAllCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtensionContext;

public final class TimingExtension
        implements BeforeAllCallback, AfterAllCallback,
                   BeforeTestExecutionCallback,
                   AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(TimingExtension.class);

    private static final String CLASS_TIME = "class-start";
    private static final String METHOD_TIME = "method-start";

    @Override
    public void beforeAll(ExtensionContext context) {
        context.getStore(NAMESPACE)
                .put(CLASS_TIME, System.nanoTime());
    }

    @Override
    public void afterAll(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove(CLASS_TIME, Long.class);

        if (start != null) {
            print(context, "CLASS_TIME",
                    context.getRequiredTestClass().getSimpleName(),
                    start);
        }
    }

    @Override
    public void beforeTestExecution(ExtensionContext context) {
        context.getStore(NAMESPACE)
                .put(METHOD_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove(METHOD_TIME, Long.class);

        if (start != null) {
            String name = context.getRequiredTestClass()
                    .getSimpleName() + "."
                    + context.getRequiredTestMethod().getName();

            print(context, "METHOD_TIME", name, start);
        }
    }

    private static void print(
            ExtensionContext context,
            String kind,
            String name,
            long start) {

        double ms = (System.nanoTime() - start) / 1_000_000.0;

        String formatted =
                String.format(Locale.ROOT, "%.3f", ms);
        context.publishReportEntry(kind + ".ms", formatted);

        System.out.printf(
                Locale.ROOT,
                "%s name=%s elapsed_ms=%s%n",
                kind, name, formatted);
    }
}
~~~

Extension không dùng một static mutable stopwatch chung; `ExtensionContext.Store` lưu dữ liệu theo class/method scope. `publishReportEntry` phát metadata cho JUnit Platform, còn `System.out.printf` giúp Gradle hiện kết quả khi `showStandardStreams=true`.

**Diễn giải:** `METHOD_TIME` không bao gồm `@BeforeEach` hoặc `@AfterEach`. `CLASS_TIME` phụ thuộc extension ordering và có thể bỏ qua một phần Spring context initialization. Nó là duration trong JUnit class lifecycle, không phải toàn Test task.

## 16. ContextLookupTimingListener.java: đo Spring context cache boundary

File `src/test/java/example/perf/ContextLookupTimingListener.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.springframework.context.ApplicationContext;
import org.springframework.core.Ordered;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public final class ContextLookupTimingListener
        extends AbstractTestExecutionListener {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void beforeTestClass(TestContext testContext) {
        long start = System.nanoTime();

        ApplicationContext context =
                testContext.getApplicationContext();

        double ms = (System.nanoTime() - start) / 1_000_000.0;

        System.out.printf(
                Locale.ROOT,
                "CONTEXT_LOOKUP_OR_LOAD class=%s "
                + "elapsed_ms=%.3f identity=%x%n",
                testContext.getTestClass().getSimpleName(),
                ms,
                System.identityHashCode(context));
    }
}
~~~

Listener này được merge với Spring default listeners trong hai context test classes. Lần đầu cache miss có thể tốn thời gian load/refresh; lần sau với cùng key có thể return nhanh.

**Hạn chế:** `getApplicationContext()` trong listener chủ động khởi tạo context nếu cache miss. `identityHashCode` chỉ giúp nhận biết object trong cùng process, không phải global identifier và có xác suất collision. Đọc thêm cache DEBUG logs, đừng chỉ so identity rồi kết luận số refresh.

## 17. PureUnitTimingTest.java: 2 methods không tải Spring

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
@ExtendWith(TimingExtension.class)
class PureUnitTimingTest {

    @Test
    void returnsGreeting() {
        GreetingService raw = new GreetingService();
        assertEquals("Hello, Ada", raw.greet("Ada"));
    }

    @Test
    void rejectsNullName() {
        GreetingService raw = new GreetingService();
        assertThrows(NullPointerException.class,
                () -> raw.greet(null));
    }
}
~~~

Test dùng object Java thuần. Nếu business logic không cần Spring DI/config, đây là baseline hữu ích; không nên thêm `@SpringBootTest` chỉ để chạy một hàm thuần.

## 18. ContextGroupATest.java: 2 @SpringBootTest methods

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestExecutionListeners;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("context")
@ExtendWith(TimingExtension.class)
@TestExecutionListeners(
    listeners = ContextLookupTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
@SpringBootTest(
    classes = BenchmarkApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc."
        + "DataSourceAutoConfiguration"
    })
class ContextGroupATest {

    @Autowired GreetingService greeting;
    @Autowired ApplicationContext context;

    @Test
    void managedBeanReturnsGreeting() {
        assertEquals("Hello, Ada", greeting.greet("Ada"));
    }

    @Test
    void beanExistsInContext() {
        assertTrue(context.containsBean("greetingService"));
    }
}
~~~

Với `WebEnvironment.NONE`, không mở embedded HTTP server. DataSource auto-config bị exclude trong context test, vì bài không có PostgreSQL ở nhóm này. `MERGE_WITH_DEFAULTS` giữ Spring DependencyInjectionTestExecutionListener và các listeners mặc định khác.

## 19. ContextGroupBTest.java: 2 methods cùng cache key

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestExecutionListeners;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("context")
@ExtendWith(TimingExtension.class)
@TestExecutionListeners(
    listeners = ContextLookupTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
@SpringBootTest(
    classes = BenchmarkApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc."
        + "DataSourceAutoConfiguration"
    })
class ContextGroupBTest {

    @Autowired GreetingService greeting;
    @Autowired ApplicationContext context;

    @Test
    void anotherManagedCallWorks() {
        assertEquals("Hello, Linh", greeting.greet("Linh"));
    }

    @Test
    void serviceBeanAlsoExistsHere() {
        assertTrue(context.containsBean("greetingService"));
    }
}
~~~

Hai `@SpringBootTest` annotations giữ cùng classes, webEnvironment và properties; không có `@DirtiesContext` hoặc mock beans khác nhau. Trong một test JVM, class thứ hai dùng key tương thích có thể **cache HIT**.

**Không assert class B chạy sau class A** hoặc context phải load dưới N milliseconds: test discovery/order, machine speed và GC khác nhau. Đo trên logs, đối chiếu cache hit/miss và identity trong một run.

## 20. PostgresContainerTimingTest.java: 1 opt-in Docker benchmark

File `src/test/java/example/perf/PostgresContainerTimingTest.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("container")
@ExtendWith(TimingExtension.class)
class PostgresContainerTimingTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_DOCKER_BENCH", matches = "true")
    void measuresContainerBootQueryAndStop(
            TestReporter reporter) {

        PostgreSQLContainer<?> postgres =
                new PostgreSQLContainer<>("postgres:16-alpine");

        try {
            long containerStart = System.nanoTime();
            postgres.start();
            publish(reporter,
                    "container.start.ms", containerStart);

            long bootStart = System.nanoTime();
            try (ConfigurableApplicationContext context =
                    new SpringApplicationBuilder(
                            BenchmarkApplication.class)
                        .web(WebApplicationType.NONE)
                        .properties(
                            "spring.main.banner-mode=off",
                            "spring.datasource.url="
                                    + postgres.getJdbcUrl(),
                            "spring.datasource.username="
                                    + postgres.getUsername(),
                            "spring.datasource.password="
                                    + postgres.getPassword())
                        .run()) {

                publish(reporter,
                        "spring.run.ms", bootStart);

                JdbcTemplate jdbc =
                        context.getBean(JdbcTemplate.class);

                long queryStart = System.nanoTime();
                Integer result = jdbc.queryForObject(
                        "SELECT 1", Integer.class);

                publish(reporter,
                        "jdbc.first_query.ms", queryStart);

                assertEquals(1, result);
            }
        } finally {
            long stopStart = System.nanoTime();
            postgres.stop();
            publish(reporter,
                    "container.stop.ms", stopStart);
        }
    }

    private static void publish(
            TestReporter reporter, String metric, long start) {

        double ms = (System.nanoTime() - start) / 1_000_000.0;
        String value =
                String.format(Locale.ROOT, "%.3f", ms);

        reporter.publishEntry(metric, value);
        System.out.printf(
                Locale.ROOT,
                "BENCH metric=%s elapsed_ms=%s%n",
                metric, value);
    }
}
~~~

Test **không có @SpringBootTest**, vì SpringExtension có thể tạo context trước khi test method bắt đầu. Nó chủ động start PostgreSQL, sau đó gọi `SpringApplicationBuilder.run()` để đo riêng Boot startup với database đã ready.

Context được đóng bằng try-with-resources **trước khi** container stop. Đó là ownership phù hợp: bean/DataSource có cơ hội cleanup trong khi DB còn sống.

### 20.1 Khi không có Docker

`@EnabledIfEnvironmentVariable` khiến Docker test được **SKIPPED** nếu không đặt `RUN_DOCKER_BENCH=true`; 6 test còn lại chạy không cần Docker. Không tuyên bố benchmark Docker PASS khi case bị skipped. Với env=true nhưng Docker không khả dụng, test sẽ fail và báo lỗi thật.

### 20.2 Những số đo có nghĩa gì?

- `container.start.ms`: có thể gồm image pull, Docker startup, wait strategy.
- `spring.run.ms`: từ trước SpringApplicationBuilder.run cho tới lúc context Boot ready, không chỉ riêng `refresh()`.
- `jdbc.first_query.ms`: có thể có lazy connection setup của pool, không phải thuần SQL execution.
- `container.stop.ms`: cleanup từ Testcontainers, không bao gồm mọi cleanup ngoài process.
- `CLASS_TIME` đo lớp JUnit, có thể có thêm setup/teardown overhead.
- `METHOD_TIME` đo body bao gồm cả start/run/query/stop vì tất cả nằm trong `@Test`. **Không cộng METHOD_TIME với các thành phần trên**.

### 20.3 Yêu cầu để chạy

Cần Docker daemon hoạt động, image `postgres:16-alpine` tải được, JDK 17+, PostgreSQL JDBC driver. Spring Boot auto-configures DataSource/JdbcTemplate vì có JDBC starter và URL/credentials thật. SQL `SELECT 1` kiểm kết nối cơ bản, **không** đại diện chi phí Flyway/Hibernate hoặc workload nặng.

## 21. Chạy ba nhóm đo

Linux/macOS:

~~~bash
./gradlew unitBench
./gradlew contextBench
RUN_DOCKER_BENCH=true ./gradlew containerBench
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat unitBench
.\gradlew.bat contextBench

$env:RUN_DOCKER_BENCH="true"
.\gradlew.bat containerBench
Remove-Item Env:RUN_DOCKER_BENCH
~~~

Chạy toàn bộ:

~~~bash
./gradlew test
~~~

Nếu project chưa có wrapper, tạo Gradle wrapper hoặc dùng Gradle compatible. `RUN_DOCKER_BENCH` là **environment variable**, không phải Gradle `-P` property.

Nếu Gradle task UP-TO-DATE, sẽ không có measurements mới. Để buộc task chạy lại:

~~~bash
./gradlew contextBench --rerun-tasks --max-workers=1
~~~

**Lưu ý:** `--rerun-tasks` có thể ép các dependency tasks compile lại; đừng lấy toàn command wall time so với một run chỉ thực hiện Test task. Dùng context/listener logs để xem con số riêng.

### 21.1 Kết quả được kỳ vọng, không phải stdout đã chạy

| Group | Tests | Expected |
| --- | ---: | --- |
| unitBench | 2 | 2 PASS |
| contextBench | 4 | 4 PASS, có cache lookup/load logs |
| containerBench, env không bật | 1 | 1 SKIPPED |
| containerBench, Docker có sẵn và env=true | 1 | 1 PASS nếu database/config đúng |

Giá trị `elapsed_ms` được tính **tại runtime** và phụ thuộc machine. Bài không đưa ra con số đo thực hay khẳng định đã chạy Gradle.

## 22. Đọc HTML, JUnit XML và Gradle profile

Gradle tạo HTML/JUnit XML report theo Test task:

~~~text
build/reports/tests/unitBench/index.html
build/reports/tests/contextBench/index.html
build/reports/tests/containerBench/index.html

build/test-results/unitBench/TEST-*.xml
build/test-results/contextBench/TEST-*.xml
build/test-results/containerBench/TEST-*.xml
~~~

JUnit XML testcase `time` phản ánh reporting semantics của Gradle/JUnit, không tự là `container.start.ms` hoặc `context.refresh.ms`. Với parallelism, **tổng testcase.time có thể lớn hơn task wall** vì các tests chạy cùng lúc.

Ví dụ **số liệu giả định chỉ để minh họa báo cáo**:

| Group | Sum case time | Gradle task wall | Context misses | Container starts |
| --- | ---: | ---: | ---: | ---: |
| Unit | 0,4s | 3,1s | 0 | 0 |
| Context | 2,0s | 9,5s | 1 | 0 |
| Container | 6,2s | 12,0s | 0 trong Spring Test cache | 1 |

Không suy từ bảng giả định rằng ứng dụng thật có những con số này. Số cache miss của Docker test bằng 0 theo **Spring TestContext framework** vì nó dùng SpringApplicationBuilder trực tiếp, dù vẫn tạo **một context mới**.

### 22.1 Gradle --profile

~~~bash
./gradlew contextBench --profile
~~~

Gradle profile cho biết **Gradle task durations**, hữu ích phân biệt compile và Test task. Nó không tự tách context load, container startup hoặc JDBC migration. Build scans/Develocity nếu tổ chức dùng có thể cho timeline sâu hơn, nhưng kiểm privacy/authorization trước khi upload logs/secrets.

## 23. Spring Boot ApplicationStartup và StartupStep

Spring Framework có `ApplicationStartup` để ghi các `StartupStep` trong quá trình startup/bean init. Spring Boot 3.5 cung cấp `BufferingApplicationStartup`.

Mẫu instrumentation:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app =
        new SpringApplication(BenchmarkApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
~~~

Đây là **fragment riêng**, cần `BenchmarkApplication` và `args`. Khi chạy ngoài Docker test, app có JDBC starter nên vẫn cần URL/credentials hoặc auto-config exclude.

`BufferingApplicationStartup` giữ các events để phân tích sau; có thể dùng Actuator startup endpoint khi thêm Actuator/web dependency và expose đúng. Nếu app có hàng nghìn beans, buffer 2048 steps có thể không chứa toàn bộ events. Tăng capacity tùy mục tiêu.

### 23.1 Không cộng các startup step durations

Một `spring.beans.instantiate` có thể nằm bên trong một step refresh lớn hơn. Các spans/steps có parentId và có thể overlap. Cộng tổng mọi durations sẽ **double-count**.

`ApplicationStartup` mô tả **Spring startup steps**, không bao gồm việc pull Docker image trước SpringApplication.run. Nếu muốn tìm bean nào init chậm, kết hợp StartupSteps với JFR/logs; nếu muốn biết Docker start, vẫn cần stopwatch riêng.

## 24. Actuator startup endpoint và metrics

Với `spring-boot-starter-actuator` và `BufferingApplicationStartup` được cấu hình, Actuator có thể expose:

~~~text
GET /actuator/startup
POST /actuator/startup
~~~

GET lấy snapshot, POST có thể drain recorded steps, tùy Boot version. Cần enable HTTP exposure theo policy:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

**Mini-project hiện tại không có Actuator/Web starter**, nên endpoint trên **không chạy tự nhiên**; đây là hướng dẫn mở rộng. Trong production, startup endpoint có thể lộ bean names/configuration details, phải bảo vệ bằng network/security.

Spring Boot Actuator/Micrometer cũng có metrics:

- `application.started.time`: thời gian tới mốc ApplicationStartedEvent, sau refresh context.
- `application.ready.time`: thời gian tới mốc ApplicationReadyEvent, sau ApplicationRunner/CommandLineRunner.

Nếu một runner warm cache trong 10s, ready time có thể lớn hơn started time. Nếu Docker được start trước SpringApplication, metrics Boot startup **không** tính image pull. Không nhầm các giá trị này với TestContext cache lookup timer.

## 25. Java Flight Recorder để tìm bottleneck

JDK 17 có **Java Flight Recorder (JFR)**; Spring hỗ trợ `FlightRecorderApplicationStartup`:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app =
        new SpringApplication(BenchmarkApplication.class);

app.setApplicationStartup(
        new FlightRecorderApplicationStartup());

app.run(args);
~~~

Chạy executable JVM với recording:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=30s -jar app.jar
~~~

Đây là **ví dụ phương pháp**, không phải kết quả chạy. Nếu muốn capture JFR trong Gradle test, cần đưa JVM args **vào forked Test worker** và dùng filename riêng per fork để tránh overwrite. JFR có thể giúp xem class loading, allocations, CPU/GC, blocking và startup steps. Nhưng profiler cũng có overhead; đo baseline không profiler để so.

## 26. Testcontainers lifecycle và context cache cần thống nhất

### 26.1 Static @Container và instance @Container

Ví dụ snippet:

~~~java
@Testcontainers
class RepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Static `@Container` thông thường start trước tests của **class**, stop sau tests class. Instance `@Container` start/stop cho mỗi method. Cả hai rất khác “một DB duy nhất cho toàn suite”. Testcontainers JUnit 5 extension khuyến nghị dùng sequential execution; parallel lifecycle có rủi ro.

### 26.2 Cached context trỏ vào container đã dừng

Một failure mode quan trọng:

~~~text
Class A: static DB container A starts
   +-- @SpringBootTest context X uses JDBC URL of A
Class A ends -> JUnit stops container A
Class B gets cached context X
   +-- DataSource still points at stopped container A
   +-- JDBC query fails
~~~

Nếu context cần sống qua nhiều classes, nên đảm bảo container ít nhất sống bằng vòng đời context. Spring Boot 3.5 hỗ trợ container beans được quản lý bởi Spring và `@ImportTestcontainers`, `@ServiceConnection`.

### 26.3 @ServiceConnection

Snippet:

~~~java
@Testcontainers
@SpringBootTest
class JdbcIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Cần thêm:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

`@ServiceConnection` giúp Boot tạo JDBC connection details, giảm code dynamic URL. Nhưng **static @Container lifecycle vẫn do Testcontainers/JUnit nắm**, và cached context ở class khác vẫn cần design phù hợp.

### 26.4 Container làm Spring bean

Một mẫu để gắn lifetime với context:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class SharedDbTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> db() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

Khi import config vào `@SpringBootTest` và có Boot Testcontainers support, container bean có thể được start/stop cùng context thay vì đóng ngay cuối test class. Đây là **mẫu mở rộng**, không thuộc 7 tests code hoàn chỉnh.

### 26.5 Dynamic properties

Khi dùng `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", db::getJdbcUrl);
    registry.add("spring.datasource.username", db::getUsername);
    registry.add("spring.datasource.password", db::getPassword);
}
~~~

Cần static `db`, imports và context phù hợp. Cache key có thể xét dynamic-property context customizer **mà không đồng nghĩa xét mọi giá trị supplier đang trả ở thời điểm sau**. Nếu subclass thay container/port giữa tests mà Spring context được reuse, có thể trỏ stale URL. Thiết kế isolation rõ hoặc `@DirtiesContext` khi thật sự cần.

## 27. Chọn test slices để giảm Spring context startup

| Đang kiểm | Layer phù hợp | Có cần full context? |
| --- | --- | --- |
| Pure parser/domain service | JUnit + fake/Mockito | Không |
| JSON serialize/deserialize | `@JsonTest` | Không |
| MVC mapping/validation | `@WebMvcTest` | MVC slice |
| JPA repository/query | `@DataJpaTest` | JPA slice + DB |
| REST client mapping | `@RestClientTest` | Client slice |
| Full security/transactions/events/bean wiring | `@SpringBootTest` | Thường có |
| Real PostgreSQL migration/SQL | Testcontainers + integration | Có DB thật |
| End-to-end request path | Staging-like test | Nhiều services |

Một slice test có thể nhanh hơn một full-context test, nhưng nếu mỗi class tạo **một slice context riêng** do mock/import/profile khác, tổng suite vẫn chậm. Đo số cache misses và startup duration của **cả nhóm**, không chỉ một test class.

Không biến full integration/security tests thành pure unit tests để khoe nhanh nếu mất phần quan trọng cần kiểm.

## 28. Isolation và cleanup quyết định reuse có an toàn không

Tách hai loại state:

- **Context topology:** giữ ổn định để Spring cache reuse.
- **Mutable data/resources:** reset trong `@BeforeEach`/`@AfterEach` hoặc test transaction đúng boundary.

Những điều cần dọn:

- DB rows/fixtures và cache entries.
- Message subscriptions, queues/offsets.
- SecurityContext/MDC/ThreadLocal tenant.
- HTTP server/client resources.
- Task scheduler/executor tasks do test tạo.
- Testcontainers resources thuộc test.
- Mock state/invocation histories.

**Không shutdown Spring-managed shared DataSource/executor bean trong @AfterEach**, vì cached context có thể dùng lại bean đó. Dọn tasks/data mà test sở hữu; để Spring đóng bean khi context close. `@DirtiesContext` được dùng khi state không thể khôi phục an toàn.

## 29. Cold và warm benchmarks: quy tắc so sánh công bằng

Một benchmark có thể tái lập nên ghi:

| Metadata | Lý do |
| --- | --- |
| Git SHA | Cùng code/test version |
| JDK vendor/version | JIT/GC/classloader khác |
| Spring Boot/Framework | Auto-config/cache behavior khác |
| Gradle and test JVM settings | Fork/parallel/reporting khác |
| Docker/Testcontainers versions | Lifecycle/image policy khác |
| PostgreSQL image/tag/digest | Image layers/startup khác |
| CPU/RAM/OS/architecture | Nền hiệu năng khác |
| Container image pre-pulled? | Phân biệt cold/warm |
| Gradle daemon/caches | Đánh giá compile/build overhead |
| Context maxSize/hit/miss | Đo mức reuse |
| Number of tests/contexts | Không tối ưu bằng cách bỏ tests |
| Runner count and retries | Có thêm startup work |
| Profiling/logging enabled? | Overhead instrumentation |
| Sample count, median, p95 | Không cherry-pick |

Không so **laptop warm Docker image** với **CI cold agent chưa pull image** rồi quy nguyên chênh lệch cho Spring cache config.

### 29.1 Quy trình đo nhiều lần

1. Fix machine/config/JDK/Git SHA.
2. Chạy một warm-up run nếu mục tiêu warmed performance.
3. Thu thập nhiều runs (ví dụ 10) cho từng group; gắn label cold/warm.
4. Ghi raw durations, context miss count và container start count.
5. Tính median, p95 (nêu phương pháp percentile), min/max.
6. Chỉ đổi **một** biến tối ưu mỗi lượt.
7. Đo lại trong điều kiện tương đương.
8. Kiểm functional tests vẫn đủ và không phát sinh skipped không mong muốn.
9. Nếu tăng parallelism, báo wall time, CPU/memory contention và số contexts duplicated.
10. Không biến benchmark thành flaky assertion trên shared CI.

### 29.2 Minh họa tiết kiệm, không phải số thực

Giả định:

~~~text
Before: 180 seconds, 20 context misses, 10 container starts.
After:   65 seconds,  3 context misses,  2 container starts.

Saving = 115 seconds, or about 63.9%.
~~~

Đây là **số giả định để minh họa công thức**; không áp vào dự án thật nếu không có measurements tương ứng.

## 30. Gradle forks, parallelism và task time

Gradle có `maxParallelForks` và `forkEvery`. Tăng maxParallelForks có thể giảm wall time nếu CPU còn dư, nhưng mỗi fork có JVM/TestContext cache riêng; một Spring context có thể được load nhiều lần. Giảm `forkEvery` có thể giúp reuse, nhưng nếu test classes leak static state, một JVM quá lâu có thể gây memory pressure.

Nếu class A và B có cùng context key nhưng Gradle phân cho **hai forks khác nhau**, cache HIT giữa classes **không xảy ra**. Vì thế khi so before/after:

- Ghi maxParallelForks và forkEvery.
- Ghi số Spring context misses thực.
- Ghi number of worker JVMs.
- Ghi Docker/DB contention.
- Không dựa vào tổng sum XML testcase.time để suy wall time khi parallel.

### 30.1 Build daemon không giữ Spring TestContext across runs

Gradle daemon tăng tốc phần build/config/cache ở Gradle level; Spring TestContext nằm trong Test worker JVM. Khi Gradle task mới tạo JVM khác, context được tạo lại. Một lần chạy nhanh bất thường có thể chỉ vì Gradle báo UP-TO-DATE, không phải Boot context tự khởi động nhanh.

## 31. Database initialization và migrations

Thời gian Boot context có JDBC starter có thể bao gồm:

~~~text
SpringApplication.run()
   +-- bean definition / bean creation
   +-- DataSource/Hikari connection pool
   +-- Flyway/Liquibase migration (nếu enabled)
   +-- JPA/Hibernate metadata validation
   +-- repository/service bean initialization
   +-- ApplicationRunner
   +-- ApplicationReadyEvent
~~~

Một số kết nối được tạo **lazy** nên first SQL query có thể lớn hơn các queries sau. Nếu muốn đo Flyway riêng, dùng Spring StartupStep/metrics/logs tại migration bean, hoặc instrument migration phase, không tự trừ hai stopwatch có boundaries khác nhau.

**Không tắt migration trong benchmark chỉ để nhanh hơn nếu integration test đang yêu cầu schema production-like.** Tối ưu bằng nhóm tests hợp lý: pure unit không cần DB, integration suite có migration/schema chính xác.

## 32. Container reuse, image caching và lifecycle

- Image caching giảm network download nhưng không loại bỏ create/start/wait.
- Static containers có thể share trong class, không mặc nhiên across every class.
- `withReuse(true)`/Testcontainers reusable feature có trade-offs về isolation/data leak, cần Docker/test policy phù hợp.
- Spring-managed container bean giúp lifecycle khớp cached context khi triển khai đúng.
- Container nhiều forks đồng thời có thể tranh CPU/RAM và làm benchmark tệ hơn.
- Chạy test trên Docker host có quota thấp có thể khiến wait strategy timeout dù code đúng.
- Không dùng `Thread.sleep(5000)` để “đợi DB ready”; dùng đúng wait strategy/connection checks.
- Không reuse database chứa dữ liệu khách thật hoặc secrets trong pipeline không cô lập.

## 33. JFR, profiler và metrics khi cần tìm chi phí sâu

Khi thấy `spring.run.ms` cao nhưng chưa biết tại sao:

- **BufferingApplicationStartup**: startup step names/durations và tags.
- **FlightRecorderApplicationStartup/JFR**: class loading, allocations, GC, CPU, blocking.
- **Micrometer timers**: ApplicationStarted/Ready, runner/migration custom timings.
- **Gradle --profile**: configuration/compile/Test tasks.
- **Spring ContextCache DEBUG**: hit/miss/size statistics.
- **Testcontainers logs/Docker events**: image start/wait/cleanup.
- **JUnit XML parser**: slow methods/classes trong tập lớn.

JFR/profiling có overhead. Giữ một baseline không profiler, một diagnostic run có profiler; đừng lấy số JFR instrumented so với baseline uninstrumented rồi tuyên bố cải thiện.

## 34. Khi tổng suite chậm dù method time nhanh

Kiểm theo thứ tự:

1. Số context misses bao nhiêu và mỗi miss mất bao lâu?
2. Class nào tạo context mới vì profile/mock/property khác?
3. Có `@DirtiesContext` bị lạm dụng không?
4. TestContainers đang start bao nhiêu containers, image warm hay cold?
5. JDBC pool có mở connection trong refresh hay first query?
6. Có Flyway/Liquibase/hibernate schema validation lặp lại không?
7. `@BeforeEach` seed DB quá nhiều rows hay call HTTP không?
8. `@AfterEach` cleanup/truncate chậm không?
9. Gradle Test task mở nhiều process hay forkEvery thấp không?
10. CPU/memory/DB Docker contention có tăng khi parallel không?
11. Có scheduled/async threads/consumers còn sống và giữ JVM không?
12. Có quá nhiều logging/reporting/profiling overhead không?

Đừng sửa blind “giảm @SpringBootTest thành unit” mà không biết test coverage mất gì.

## 35. Lỗi phổ biến

**1. Đo method body rồi gọi là context startup.**  
`BeforeTestExecution` không bao gồm mọi Spring setup.

**2. Dùng currentTimeMillis đo elapsed.**  
Wall clock có thể nhảy; dùng nanoTime.

**3. Assert context startup phải dưới 100ms trên shared CI.**  
Flaky; cần SLO benchmark kiểm soát.

**4. @SpringBootTest cho pure domain mapper.**  
Không cần context; chuyển unit test nếu semantics cho phép.

**5. @DirtiesContext after mỗi method.**  
Phá cache reuse mà không cần thiết.

**6. Mỗi class khác một @MockitoBean hoặc @ActiveProfiles.**  
Tăng cache key diversity và số misses.

**7. Cho rằng context cache chia sẻ qua Gradle forks.**  
Không: static cache trong từng test JVM.

**8. Đổi forkEvery=1 rồi không xem context startup tăng.**  
Vừa tăng process overhead vừa giảm reuse.

**9. Đặt maxSize 128 rồi tin luôn nhanh.**  
Memory/GC/resources có thể tệ hơn.

**10. Không phân biệt task UP-TO-DATE với test thực thi.**  
Không có số đo mới nếu JUnit không chạy.

**11. Static @Container là singleton cho toàn build.**  
Thông thường scoped theo class/JUnit extension.

**12. Bắt đầu timer @BeforeAll sau khi @Container đã được start.**  
Bỏ lỡ container startup.

**13. Cached context trỏ vào container đã stop.**  
Phải thống nhất lifecycle hoặc isolate.

**14. @ServiceConnection bị coi là tự xử lý mọi lifecycle.**  
Nó cung cấp connection details; owner container vẫn quan trọng.

**15. Đo container.start mà gọi là DB migrations time.**  
Different stages, cần đồng hồ riêng.

**16. Đo first query như SQL throughput benchmark.**  
Có thể gồm lazy pool connection.

**17. Cộng tất cả StartupStep durations.**  
Nested/overlap gây double counting.

**18. Gán false FAIL khi container test SKIPPED mặc định.**  
Đó là opt-in benchmark; báo skipped minh bạch.

**19. Dùng TestReporter nhưng không xuất log/report reader hỗ trợ.**  
Có thể không thấy số; in logs hoặc CI listener phù hợp.

**20. Bật parallel benchmarks nhưng không tách worker/environment.**  
Kết quả bị tranh CPU/DB.

**21. Hardcode Postgres port hoặc localhost:5432.**  
Testcontainers map random ports; dùng `getJdbcUrl()`.

**22. Không close context/container trong finally.**  
Resource leak và suite chậm ở test sau.

**23. So JUnit testcase.time sum với Gradle task wall như cùng metric.**  
Chúng khác lifecycle/forks/parallel.

**24. Chỉ đo một lần rồi báo nhanh hơn 70%.**  
Phải có repeated samples và environment metadata.

**25. Test slice nhanh nhưng bỏ mất security/DB integration requirements.**  
Tính đúng quan trọng hơn tốc độ đẹp.

**26. Chạy image cold và warm mà không gắn label.**  
Không thể kết luận thay đổi code làm startup nhanh.

**27. Tắt mọi cache/migration/health check chỉ để giảm startup.**  
Có thể làm suite không đại diện production.

**28. Không đo teardown.**  
Non-daemon threads và Docker cleanup có thể giữ JVM lâu sau tests.

## 36. Quy trình tối ưu theo bằng chứng

1. Chụp baseline: Gradle task wall, method times, cache hit/miss, container count.
2. Nhóm tests thành unit, MVC/JPA slices, full context, Testcontainers và E2E.
3. Bật TestContext DEBUG và tìm class/config tạo MISS.
4. Dùng listener đo context lookup/load và extension đo method/class.
5. Với Docker, tách `container.start()`, `SpringApplication.run()` và first SQL.
6. Ghi Git SHA, JDK/Boot/Gradle/Docker/image versions và CI machine.
7. Đo cold và warm trong điều kiện giống nhau.
8. Phân tích top slow classes/methods và startup steps nếu cần JFR.
9. Chỉ thay một biến: giảm context key variants, test slice, fixture strategy, container lifecycle hay forks.
10. Đo lại nhiều runs; dùng median/p95, không chỉ fastest run.
11. Xác nhận functional assertions/test count không giảm ngoài chủ ý.
12. Nếu số đo cải thiện nhưng test bắt đầu order-dependent, rollback optimization.

### Checklist cuối

- [ ] Có phân tách build, JUnit, context cache, container và DB query time.
- [ ] Biết default Spring cache maxSize 32 và key factors.
- [ ] Đã đo cache HIT/MISS thay vì suy từ số class names.
- [ ] Context lookup/load instrumentation không bị gán nhầm là full Boot run.
- [ ] Test class/method callbacks được hiểu đúng setup/teardown boundaries.
- [ ] Testcontainers image pull/start/wait được ghi rõ cold/warm.
- [ ] Context và container có lifecycle không để cached DataSource trỏ container stopped.
- [ ] Docker benchmark chỉ tính khi RUN_DOCKER_BENCH=true và có Docker thật.
- [ ] Có JUnit XML/Gradle task reports cho mỗi group.
- [ ] JVM forks và parallelism được kiểm soát/ghi nhận.
- [ ] Không đặt ngưỡng timing cứng thiếu SLO thống kê.
- [ ] Không bỏ/disable integration tests quan trọng chỉ để suite nhanh.
- [ ] Kết quả so sánh có phiên bản code, machine metadata và sample count.

## 37. Kết luận

**Muốn giảm thời gian suite Spring Boot, trước tiên phải chỉ rõ thời gian nằm ở đâu.** Spring TestContext cache giúp tiết kiệm refresh khi các tests dùng cùng config/trong cùng JVM; Testcontainers có chi phí Docker riêng; JUnit extension đo test class/method; Gradle reports đo Test task; Spring Boot ApplicationStartup/JFR cung cấp bức tranh sâu về bean startup.

Trong demo, unit group không dùng context, hai context groups thể hiện cache reuse, còn Docker group đo riêng container/startup/SQL/stop mà không bịa một số ms cố định. Khi làm thật, hãy đo nhiều lần, gắn cold/warm labels, giữ test isolation và chỉ tối ưu thành phần đã được đo là nút thắt.

### Tài liệu tham khảo

- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cache key, default maxSize, LRU, logging.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): cache invalidation.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, test slices.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): ServiceConnection, dynamic properties, context lifetimes.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): BufferingApplicationStartup, FlightRecorderApplicationStartup.
- [Spring Boot 3.5 — Startup Endpoint](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): startup steps JSON.
- [Spring Boot — Application Startup Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): application.started.time, application.ready.time.
- [Testcontainers — JUnit 5 Lifecycle](https://testcontainers.com/guides/testcontainers-container-lifecycle/): static vs instance @Container.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers extension behavior.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks, maxParallelForks, forkEvery, HTML/XML.
- [Gradle — Build Performance](https://docs.gradle.org/current/userguide/performance.html): profiler/task performance.
- [JUnit 5 — Extensions](https://docs.junit.org/current/user-guide/#extensions): lifecycle callbacks and TestReporter.
