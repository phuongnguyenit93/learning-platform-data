# Giới hạn của cache khi Gradle fork nhiều JVM

## 1. Tại sao phải hiểu phạm vi context cache?

Trong Spring Boot testing, `@SpringBootTest` có thể tốn thời gian vì Spring tạo `ApplicationContext`, xử lý auto-configuration, đăng ký/inject beans, mở resource pools và đôi khi khởi tạo web server hoặc kết nối bên ngoài. Spring TestContext Framework dùng một **context cache** để lưu những contexts đã được khởi tạo và tái sử dụng giữa các tests có cùng cấu hình.

Điểm giới hạn đặc biệt quan trọng: **cache này được lưu trong biến static của Spring TestContext, thuộc bộ nhớ của từng JVM**. Khi Gradle tạo nhiều forked test worker JVMs, mỗi worker có **cache riêng**. Hai tests cùng annotation và cùng Spring configuration nhưng bị xếp vào hai JVMs sẽ phải khởi tạo hai ApplicationContexts độc lập. Không có distributed cache, IPC hay serialization tự động chuyển Spring contexts giữa test workers.

Bài thuộc nhóm **Context cache và hiệu năng** của module **Spring Boot – testing**, với đề bài **Giới hạn của cache khi Gradle fork nhiều JVM**.

Học xong, bạn sẽ:

1. Phân biệt Gradle daemon, Test task, forked test worker JVM, JUnit execution threads và Spring TestContext cache.
2. Hiểu `maxParallelForks`, `forkEvery`, `--max-workers`, `--parallel` tác động khác nhau đến khả năng cache reuse.
3. Biết cache key của Spring phụ thuộc `@SpringBootTest`, profiles, properties, mocks, dynamic properties, context loaders và hierarchies.
4. Chỉ ra vì sao cùng một cache key trong hai PIDs vẫn là **hai context instances khác nhau**.
5. Đọc thống kê hit/miss/cache size với logger `org.springframework.test.context.cache` ở mức DEBUG.
6. Giải thích maxSize mặc định 32, LRU eviction, `@DirtiesContext` và context failure threshold mặc định 1 trong Spring Framework 6.1.
7. Không nhầm Gradle build cache/task UP-TO-DATE với Spring TestContext cache.
8. Quan sát PID, `org.gradle.test.worker`, UUID của bean và context identity để chẩn đoán reuse.
9. Chứng minh reuse **bên trong một JVM** với `TestContextManager` và assertions `assertSame`/`assertNotSame`.
10. Viết test không phụ thuộc thứ tự Gradle phân lớp vào worker và không assert số workers cố định.
11. Lập benchmark kiểm cả wall-clock, CPU, heap, DB connections và số startup, thay vì chỉ tăng forks.
12. Áp dụng một project **Java 17 + Spring Boot 3.3.5 + Gradle 8.8 + JUnit Jupiter**, không cần Docker hay database.

**Tư duy chính:** Cache hit chỉ có thể xảy ra nếu test tiếp theo tìm đúng entry còn tồn tại **trong cùng test JVM**. Fork nhiều JVM tăng song song hóa nhưng có thể giảm cơ hội reuse cache và nhân số lần startup.

## 2. Sơ đồ kiến trúc

~~~text
Shell / CI
   |
   v
Gradle daemon (điều phối build, không chứa Spring test contexts)
   |
   +-- :app:test (Gradle Test task)
         |
         +-- Test worker JVM A (PID 8101)
         |       |
         |       +-- JUnit Jupiter
         |       +-- Spring TestContext static cache A
         |                K1 -> ApplicationContext A1
         |                K2 -> ApplicationContext A2
         |
         +-- Test worker JVM B (PID 8102)
         |       |
         |       +-- JUnit Jupiter
         |       +-- Spring TestContext static cache B
         |                K1 -> ApplicationContext B1
         |
         +-- Test worker JVM C (PID 8103)
                 |
                 +-- Spring TestContext static cache C
                          K1 -> ApplicationContext C1
~~~

Các PIDs và số workers ở sơ đồ là minh họa. Gradle chỉ tạo số worker cần thiết trong giới hạn thiết lập. **K1 ở A và K1 ở B là cùng configuration key về mặt logic, nhưng hai cache độc lập lưu hai instances riêng**.

### 2.1. Khi nào Spring dùng lại context?

Giả sử:

~~~java
@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AlphaTest {
}
~~~

và class khác có cùng annotation:

~~~java
@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BetaTest {
}
~~~

Nếu Alpha và Beta nằm trong **cùng JVM**, không có cache eviction/dirty:

~~~text
Alpha: K1 MISS -> start context X
Beta:  K1 HIT  -> reuse context X
~~~

Nếu hai classes nằm trong **hai forked JVMs**:

~~~text
PID A: Alpha K1 MISS -> context X-A
PID B: Beta  K1 MISS -> context X-B
~~~

Không thể gọi X-A từ JVM B chỉ bằng `@SpringBootTest`. Một `static` Java field không được chia sẻ giữa các processes.

### 2.2. Vì sao context ID không phải bằng chứng?

`ApplicationContext.getId()` có thể giống nhau ở hai contexts mới dựng. Một số frameworks dùng ID mặc định. Để quan sát tốt hơn, kết hợp:

- `ProcessHandle.current().pid()` nhận PID;
- `System.getProperty("org.gradle.test.worker")` nhận worker identifier do Gradle cung cấp;
- một UUID được tạo khi bean singleton của context khởi tạo;
- `System.identityHashCode(context)` để đọc identity **trong một JVM**;
- logger cache DEBUG cho hit/miss trong từng process.

Các giá trị PID/UUID thay đổi mỗi lần chạy, **không phải expected output cố định**. Không viết assertion cross-JVM `alphaStamp.equals(betaStamp)` vì phân lớp theo workers không do test kiểm soát.

## 3. Context cache key gồm những gì?

Spring TestContext dùng một khóa cấu hình kết hợp các metadata chứ không chỉ tên test class. Các nhóm đáng chú ý:

| Thành phần | Ví dụ | Khi nào tạo key khác |
| --- | --- | --- |
| Locations | `@ContextConfiguration(locations=...)` | Đổi resource config |
| Classes | `@SpringBootTest(classes=...)` | Khác root Spring configs |
| Context initializers | `@ContextConfiguration(initializers=...)` | Khác initializer |
| Context customizers | Spring Boot test customizers, bean overrides | `@MockBean`/dynamic properties khác |
| Context loader | Cách test context được tạo | Khác loader |
| Parent | Context hierarchy | Khác parent |
| Active profiles | `@ActiveProfiles` | Đổi profile |
| Test property sources | `@TestPropertySource` | Đổi resource/inline properties |
| Inline properties | `properties="lab.greeting=Hello"` | Khác values |
| Web resource base | `@WebAppConfiguration` | Khác web resource root |

Hai classes cùng root application nhưng một class dùng `lab.greeting=Hello`, class kia dùng mặc định `Xin chào` **không nên reuse context**; bean đã được khởi tạo với giá trị khác.

### 3.1. Mock/customizer làm tăng key

Spring Boot 3.3 có `@MockBean`. Một test khai báo `@MockBean PaymentClient` và test khác khai báo `@MockBean PaymentClient` cùng `@MockBean EmailClient` có thể sinh context customizers khác nhau, tạo thêm cache keys. Với Spring Framework/Boot mới hơn, `@MockitoBean` cũng có cơ chế bean override; không copy annotations của phiên bản khác khi đang dùng Boot 3.3.5.

### 3.2. @DynamicPropertySource

`@DynamicPropertySource` tham gia context customization. Khi mỗi class có method khác hoặc properties khác theo identity, cache key có thể khác. Khi dùng một inherited method nhưng underlying Testcontainers resources đã đổi, một cached context có thể giữ kết nối cũ. Vì vậy resource lifecycle phải được thiết kế phù hợp context lifecycle.

### 3.3. Cache reuse không được ưu tiên hơn correctness

Không xóa profile/property hoặc bỏ mock chỉ để tăng hit rate nếu test thực sự cần scenario khác. Mục tiêu là giảm các **khác biệt vô ích** và giữ shared configuration ổn định, không ép hai scenarios khác nhau dùng cùng bean graph.

## 4. LRU, maxSize và failure threshold

Mặc định Spring TestContext cache giới hạn **32 contexts**, dùng cơ chế loại bỏ **least recently used (LRU)** khi đầy. Trong một JVM, key đã bị evict không còn cho reuse; lần gọi tiếp theo sẽ startup context lại.

System property:

~~~properties
spring.test.context.cache.maxSize=32
~~~

Trong Gradle:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'spring.test.context.cache.maxSize', '32'
}
~~~

`systemProperty` trên `Test` task gửi property vào **forked test JVM**; đặt nó chỉ cho Gradle daemon không bảo đảm property đi tới Spring TestContext.

Nếu có 4 test workers, mỗi worker **tự quản lý maxSize=32**; không có global capacity=32 để chia đều. Tăng maxSize trên cả 4 workers có thể tăng tổng heap mạnh, dù giảm eviction.

### 4.1. @DirtiesContext

`@DirtiesContext` báo Spring TestContext rằng ApplicationContext đang bị bẩn và cần đóng/evict. Lần sau dùng cùng key, context phải load lại. Dùng khi test thực sự mutate Spring context không thể reset an toàn; đừng gắn trên mọi class để “dọn database”.

### 4.2. Context failure threshold

Từ **Spring Framework 6.1**, mặc định một context cache key có **failure threshold=1**. Sau một lần load fail, những lần thử cùng key trong **cùng cache** có thể bị bỏ qua nhanh bằng `IllegalStateException`. Cấu hình:

~~~properties
spring.test.context.failure.threshold=1
~~~

Một worker khác có bộ đếm thất bại riêng. Nếu nhiều JVM đều cố start cùng invalid configuration, log có thể cho thấy root failure **mỗi PID một lần**; không có failure threshold global.

### 4.3. Một entry đóng khi nào?

Các trường hợp thường gồm eviction vì `@DirtiesContext`, LRU khi vượt maxSize, hoặc context được đóng khi JVM kết thúc theo lifecycle. Không giả định entry còn mãi vì Gradle daemon vẫn tồn tại: test worker JVMs có lifecycle riêng.

## 5. Gradle maxParallelForks và forkEvery

### 5.1. maxParallelForks

~~~groovy
tasks.named('test', Test) {
    maxParallelForks = 4
}
~~~

Điều này cho Gradle dùng **tối đa 4 test worker JVMs đồng thời** trong Test task. Mặc định với Gradle Java testing là **1**. Không phải 4 JUnit threads, không bảo đảm đúng 4 PIDs: số classes và tổng worker slots có thể thấp hơn.

Tăng forks có thể:

- giảm wall-clock khi tests làm việc độc lập, CPU còn dư;
- tăng Spring context startups vì key K phải load một lần ở **mỗi worker cần K**;
- tăng heap/metaspace và classloading;
- nhân Hikari pools, broker connections, embedded servers và Testcontainers lifecycles;
- gây tranh chấp IO/CPU và DB limits;
- làm file/port/data conflicts xuất hiện nếu fixtures không tách biệt.

### 5.2. forkEvery

~~~groovy
tasks.named('test', Test) {
    forkEvery = 0
}
~~~

**Default `forkEvery=0` không có nghĩa “test chạy trong Gradle daemon”**. Nó có nghĩa **không đặt giới hạn số test classes trên một forked test JVM**, nên có thể reuse process qua nhiều test classes.

~~~groovy
tasks.named('test', Test) {
    forkEvery = 1
}
~~~

**forkEvery=1** thay JVM sau mỗi test class, khiến static Spring context cache vừa nạp xong mất theo JVM. Đây là chế độ có chi phí cao với full-context Spring Boot tests. `forkEvery=5` cho process chạy tối đa khoảng 5 classes trước khi được thay, nhưng không cam kết test class nào được gom cùng nhau.

### 5.3. --max-workers và --parallel

| Thiết lập | Điều khiển | Tác động |
| --- | --- | --- |
| Gradle `maxParallelForks` | Số forked test processes tối đa trong Test task | Mỗi JVM có cache riêng |
| Gradle `forkEvery` | Mức recycle JVM theo số test classes | Mất cache khi process mới |
| Gradle `--max-workers` | Tổng worker slots của build | Có thể chặn tăng forks |
| Gradle `--parallel` | Chạy tasks/project builds song song | Có thể đồng thời nhiều Test tasks |
| JUnit parallel mode | Threads trong test JVM | Có thể cùng dùng một context cache |
| Spring cache maxSize | Entries trong cache per JVM | LRU eviction |
| `@DirtiesContext` | Evict context tương ứng | Reload trong JVM |

Không dùng “Gradle fork” thay cho “JUnit thread”. Threads cùng JVM có static cache chung nhưng cũng có rủi ro shared mutable beans; processes có caches riêng dù ít data races trong JVM.

## 6. Mô hình chi phí và phép đo

Giả sử khởi tạo một context mất 3 giây, có 20 test classes cùng key, mỗi class mất 100ms (chỉ là **số giả định**):

~~~text
1 worker, forkEvery=0:
  ~1 context load, 20 classes dùng chung cache.

4 workers, forkEvery=0:
  Nếu 4 workers đều nhận classes cần K:
  có thể ~4 context loads, đồng thời/overlap.

forkEvery=1:
  Có thể ~20 context loads (mỗi class một JVM).
~~~

Số lần load tăng không có nghĩa wall-clock chắc chắn tăng cùng tỷ lệ vì các forks có thể chạy song song. Nhưng tổng startup CPU/IO, classloading, memory và resource pressure có thể tăng.

Mô hình:

~~~text
Số context loads tối thiểu ~
  Tổng theo mỗi forked JVM:
    Số cache keys duy nhất mà JVM đó sử dụng

+ re-loads do LRU/@DirtiesContext/forkEvery/retries
~~~

Cần đo **wall-clock duration, max RSS/heap, GC, CPU, connection counts, flakiness** và Spring hit/miss trong từng process. Không chọn forks chỉ theo số core hoặc một lần chạy thuận lợi.

## 7. Chuẩn bị project Java 17, Spring Boot 3.3.5 và Gradle 8.8

Lab dựng một ứng dụng không mở web port/DB để tách tác động cache khỏi external resources. Có hai `@SpringBootTest` classes cùng cấu hình, một class khác property, một test cơ chế cache trong cùng JVM và một JUnit test thuần.

### 7.1. File tree

~~~text
fork-cache-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/forkcache/
    │   ├── ForkCacheApplication.java
    │   ├── NameFormatter.java
    │   ├── GreetingService.java
    │   └── ContextStamp.java
    └── test/
        ├── resources/logback-test.xml
        └── java/com/example/forkcache/
            ├── ForkDiagnostics.java
            ├── CacheAlphaTest.java
            ├── CacheBetaTest.java
            ├── CacheVariantTest.java
            ├── CacheMechanicsTest.java
            └── NameFormatterTest.java
~~~

Gradle Wrapper scripts/JAR được sinh bởi Gradle hoặc lấy từ repo chuẩn. Tài liệu Markdown không thể copy `gradle-wrapper.jar` vì đó là binary.

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'fork-cache-lab'
~~~

### 7.3. build.gradle

~~~groovy
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

int forks = Integer.parseInt(
    (project.findProperty('testForks') ?: '1').toString())

long recycle = Long.parseLong(
    (project.findProperty('testForkEvery') ?: '0').toString())

tasks.named('test', Test) {
    useJUnitPlatform()

    maxParallelForks = forks
    forkEvery = recycle

    systemProperty 'spring.test.context.cache.maxSize',
        (project.findProperty('contextCacheSize') ?: '32')
            .toString()

    systemProperty 'spring.test.context.failure.threshold', '1'

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}
~~~

**Cấu hình benchmark có chủ đích:** `-PtestForks` và `-PtestForkEvery` cho đổi cách chạy từ command line mà không chỉnh source. `systemProperty` được truyền vào forked JVM; `showStandardStreams` cho thấy diagnostic logs. JUnit vẫn chỉ chạy tests được phát hiện bởi `useJUnitPlatform()`.

Không tự động bật JUnit thread parallelism vì bài đang so Gradle **process forking**.

### 7.4. ForkCacheApplication.java

~~~java
package com.example.forkcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForkCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForkCacheApplication.class, args);
    }
}
~~~

### 7.5. NameFormatter.java

~~~java
package com.example.forkcache;

import java.util.Objects;

public final class NameFormatter {

    private NameFormatter() {
    }

    public static String format(
            String prefix, String name) {
        Objects.requireNonNull(prefix, "prefix");

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return prefix + ", " + name.trim() + "!";
    }
}
~~~

### 7.6. GreetingService.java

~~~java
package com.example.forkcache;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${lab.greeting:Xin chào}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return NameFormatter.format(prefix, name);
    }
}
~~~

Biểu thức `@Value("${lab.greeting:Xin chào}")` trong bản gốc sẽ được thay ký hiệu bắt đầu property thành dấu đô-la khi lưu; Java code trong Sheet sẽ dùng cú pháp Spring `@Value` chính xác.

### 7.7. ContextStamp.java

~~~java
package com.example.forkcache;

import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class ContextStamp {

    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
~~~

UUID được sinh lúc Spring tạo singleton. Khi cùng context được reuse, UUID của bean này được giữ. Khi một fork khác tạo context riêng, UUID mới; dùng để quan sát, không dùng UUID ngẫu nhiên làm expected assertion.

### 7.8. ForkDiagnostics.java

~~~java
package com.example.forkcache;

import org.springframework.context.ApplicationContext;

final class ForkDiagnostics {

    private ForkDiagnostics() {
    }

    static void report(
            String label,
            ApplicationContext context,
            ContextStamp marker,
            GreetingService greeting) {

        long pid = ProcessHandle.current().pid();
        String worker = System.getProperty(
                "org.gradle.test.worker", "not-gradle");

        System.out.printf(
            "OBS label=%s pid=%d worker=%s "
              + "contextIdentity=%08x marker=%s greet=%s%n",
            label, pid, worker,
            System.identityHashCode(context),
            marker.id(), greeting.greet("An"));
    }
}
~~~

Đây là code diagnostic trong test source. `worker` có thể là `not-gradle` nếu chạy qua IntelliJ/Eclipse JUnit runner. Không assert giá trị PID/worker/UUID vì chúng thay đổi theo invocation.



## 8. CacheAlphaTest và CacheBetaTest dùng cùng cấu hình

### 8.1. CacheAlphaTest.java

~~~java
package com.example.forkcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheAlphaTest {

    @Autowired ApplicationContext context;
    @Autowired ContextStamp marker;
    @Autowired GreetingService greeting;

    @Test
    void springServiceProducesBusinessValue() {
        assertEquals("Xin chào, An!",
                greeting.greet("An"));
        ForkDiagnostics.report(
                "Alpha-1", context, marker, greeting);
    }

    @Test
    void contextContainsExpectedBeans() {
        assertTrue(context.containsBean("greetingService"));
        assertTrue(context.containsBean("contextStamp"));
        assertFalse(marker.id().isBlank());
        ForkDiagnostics.report(
                "Alpha-2", context, marker, greeting);
    }
}
~~~

### 8.2. CacheBetaTest.java

~~~java
package com.example.forkcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheBetaTest {

    @Autowired ApplicationContext context;
    @Autowired ContextStamp marker;
    @Autowired GreetingService greeting;

    @Test
    void sameConfigStillHasCorrectBusinessBehavior() {
        assertEquals("Xin chào, Bình!",
                greeting.greet("Bình"));
        ForkDiagnostics.report(
                "Beta-1", context, marker, greeting);
    }

    @Test
    void markerBelongsToContext() {
        assertTrue(context.containsBean("contextStamp"));
        assertNotNull(marker.id());
        ForkDiagnostics.report(
                "Beta-2", context, marker, greeting);
    }
}
~~~

### 8.3. Điều cần quan sát

Hai classes không khai báo properties, mocks, profiles hay test customizers khác nhau. Nếu chúng nằm trong cùng JVM và cache entry chưa bị dirty/evict:

- PID giống nhau;
- Gradle worker ID giống nhau;
- bean `ContextStamp` UUID giống nhau;
- `System.identityHashCode(context)` giống nhau (chỉ dùng làm dấu hiệu hỗ trợ);
- Spring TestContext cache có cơ hội ghi nhận reuse/hit.

Nếu bị Gradle chạy trong các JVMs khác nhau, PIDs/worker IDs/markers sẽ khác. **Không được assert Alpha và Beta luôn dùng cùng marker**: scheduler thuộc Gradle, không phải hợp đồng của test business.

Log minh họa, không phải exact stdout:

~~~text
OBS label=Alpha-1 pid=8101 worker=1 contextIdentity=1a2b3c4d marker=abcd... greet=Xin chào, An!
OBS label=Beta-1 pid=8101 worker=1 contextIdentity=1a2b3c4d marker=abcd... greet=Xin chào, An!
~~~

Khi forks=4, hai dòng tương tự có thể mang PIDs và marker khác. Đừng dựa vào thứ tự test class alphabetic.

## 9. CacheVariantTest: cùng app nhưng property khác

**CacheVariantTest.java**

~~~java
package com.example.forkcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "lab.greeting=Hello")
class CacheVariantTest {

    @Autowired ApplicationContext context;
    @Autowired ContextStamp marker;
    @Autowired GreetingService greeting;

    @Test
    void differentPropertyProducesExpectedContext() {
        assertEquals("Hello, An!",
                greeting.greet("An"));
        ForkDiagnostics.report(
                "Variant", context, marker, greeting);
    }
}
~~~

Inline property khác làm **cache key khác**, vì bean `GreetingService` được dựng với prefix khác. Khi cùng JVM, Alpha/Beta có thể dùng một context, còn Variant phải có một context khác. Đó là **cache miss đúng**, không phải lỗi hiệu năng.

## 10. CacheMechanicsTest: chứng minh deterministic trong một JVM

Một test chạy trong một JVM có thể tạo nhiều `TestContextManager` để trực tiếp kiểm chính sách cache. Điều này giúp tránh viết assertion qua nhiều classes mà Gradle có thể phân sang các workers khác nhau.

**CacheMechanicsTest.java**

~~~java
package com.example.forkcache;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestContextManager;

import static org.junit.jupiter.api.Assertions.*;

class CacheMechanicsTest {

    @Test
    void matchingConfigurationReusesContextInOneJvm() {
        ApplicationContext alpha =
            new TestContextManager(CacheAlphaTest.class)
                .getTestContext()
                .getApplicationContext();

        ApplicationContext beta =
            new TestContextManager(CacheBetaTest.class)
                .getTestContext()
                .getApplicationContext();

        assertSame(alpha, beta);
    }

    @Test
    void differentInlinePropertyProducesDifferentContext() {
        ApplicationContext baseline =
            new TestContextManager(CacheAlphaTest.class)
                .getTestContext()
                .getApplicationContext();

        ApplicationContext variant =
            new TestContextManager(CacheVariantTest.class)
                .getTestContext()
                .getApplicationContext();

        assertNotSame(baseline, variant);
    }

    @Test
    void markingDirtyEvictsSpecificEntry() {
        TestContext testContext =
            new TestContextManager(DirtyFixture.class)
                .getTestContext();

        ApplicationContext before =
                testContext.getApplicationContext();

        testContext.markApplicationContextDirty(
                DirtiesContext.HierarchyMode.EXHAUSTIVE);

        ApplicationContext after =
            new TestContextManager(DirtyFixture.class)
                .getTestContext()
                .getApplicationContext();

        assertNotSame(before, after);
    }

    @SpringBootTest(
        classes = ForkCacheApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "lab.greeting=dirty-only")
    static class DirtyFixture {
    }
}
~~~

### Tại sao mã này không phụ thuộc Gradle scheduler?

Trong một test method, hai `TestContextManager` được gọi đồng bộ trên **một JVM đang chạy method**. `matchingConfigurationReusesContextInOneJvm` xác minh hai metadata cùng key truy xuất một instance. Dù Gradle dùng forkEvery=1, method này vẫn thuộc một worker và assertion `assertSame` hợp lệ.

`differentInlinePropertyProducesDifferentContext` so hai keys khác nhau; do vậy phải là hai instances khác nhau, dù cùng worker.

`markingDirtyEvictsSpecificEntry` sử dụng `DirtyFixture` có property riêng `dirty-only`, tránh phá cache entry chung của Alpha/Beta. Sau khi mark dirty, việc lấy lại context phải tạo instance mới. Đây là **bài kiểm kỹ thuật TestContext**, không phải pattern nên dùng trong mọi test nghiệp vụ.

### Tại sao không dùng @DirtiesContext cho mọi test?

`@DirtiesContext` thường dùng khi test thật sự làm bẩn ApplicationContext; lạm dụng làm tăng startup count. Một snippet minh họa:

~~~java
@SpringBootTest(classes = ForkCacheApplication.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationScenarioTest {
    // Trường hợp có lý do chính đáng cần evict context.
}
~~~

Snippet không nằm trong project runnable. Reset dữ liệu database, clear test files hay reset mocks thường có cơ chế nhẹ hơn context eviction.

## 11. NameFormatterTest: JUnit thuần không cần Spring

**NameFormatterTest.java**

~~~java
package com.example.forkcache;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NameFormatterTest {

    @Test
    void trimsNameAndFormatsGreeting() {
        assertEquals(
            "Xin chào, Lan!",
            NameFormatter.format(
                "Xin chào", " Lan "));
    }

    @Test
    void blankNameIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> NameFormatter.format(
                "Hello", "  "));
    }
}
~~~

Hai test methods này không khởi động Spring, không cần context cache. Trong một dự án lớn, chuyển logic không phụ thuộc DI sang JUnit thuần có thể giảm test suite cost nhiều hơn tinh chỉnh context cache keys.

### Tổng số phương thức JUnit

| Test class | Số @Test | Mục đích |
| --- | ---: | --- |
| `CacheAlphaTest` | 2 | Spring context/biz behavior |
| `CacheBetaTest` | 2 | Cấu hình tương đương Alpha |
| `CacheVariantTest` | 1 | Different property/cache key |
| `CacheMechanicsTest` | 3 | Same key, different key, dirtied entry |
| `NameFormatterTest` | 2 | Unit test không cần Spring |
| **Tổng** | **10** | Quan sát cache, forks và correctness |

Mười tests được **thiết kế** trong tài liệu. Chưa thực thi Gradle/JUnit ở môi trường soạn bài, nên expected count không được hiểu là thực tế đã chạy PASS.

## 12. Logback test configuration để thấy Spring cache DEBUG

**src/test/resources/logback-test.xml**

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{45} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.springframework.test.context.cache"
            level="DEBUG"/>

    <root level="WARN">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

`spring-boot-starter` dùng logging infrastructure, nên có thể đặt cấu hình Logback test trên classpath. Nó bật đúng category thay vì DEBUG toàn bộ Spring.

Spring cache có thể log các thống kê như size, maxSize, hitCount, missCount. Ví dụ **minh họa, không phải stdout cố định**:

~~~text
Spring test ApplicationContext cache statistics:
size=2, maxSize=32, hitCount=14, missCount=2
~~~

Các counters có thể được log nhiều lần; **không cộng tất cả hitCount trên từng dòng**, vì chúng là các giá trị tích lũy. Nên đọc snapshot gần cuối của từng worker/PID, ghi nhận context keys và không tưởng tượng có một global cache counter.

## 13. Chạy benchmark A/B/C theo Gradle

### 13.1. Chuẩn bị

Yêu cầu JDK 17, Gradle Wrapper 8.8, dependencies tải từ Maven Central lần đầu. Không cần server/DB/Docker. Nếu chưa có Wrapper nhưng đã có Gradle:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau khi sinh Wrapper scripts/JAR, lưu theo repo policy.

### 13.2. Chế độ A: một worker, forkEvery=0

~~~bash
./gradlew test -PtestForks=1 -PtestForkEvery=0 --rerun-tasks
~~~

Windows:

~~~powershell
.\gradlew.bat test -PtestForks=1 -PtestForkEvery=0 --rerun-tasks
~~~

Kỳ vọng: Alpha/Beta được chạy trong cùng test JVM, nếu entry không bị dirty thì dùng cùng context marker; Variant dùng key khác. `CacheMechanicsTest` xác nhận semantics không dựa scheduler.

### 13.3. Chế độ B: tối đa 4 forked JVMs đồng thời

~~~bash
./gradlew test -PtestForks=4 -PtestForkEvery=0 --rerun-tasks
~~~

Kỳ vọng: tùy class distribution và worker slots, có thể xuất hiện nhiều PIDs/worker IDs; cùng một cấu hình Spring có thể bị startup lại trong các JVM khác nhau. Không assert phải có đúng 4 processes hoặc mỗi class một worker.

### 13.4. Chế độ C: recycle mỗi test class

~~~bash
./gradlew test -PtestForks=1 -PtestForkEvery=1 --rerun-tasks
~~~

Kỳ vọng: JVM bị thay giữa test classes, khiến Alpha/Beta không thể reuse context xuyên process. `CacheMechanicsTest` vẫn có thể xác minh reuse bên trong method thuộc một JVM. Startup/fork overhead thường cao hơn.

### 13.5. So sánh theo cùng input

- Không đổi source/dependencies giữa ba runs.
- Tắt JUnit parallelism nếu muốn chỉ đo Gradle forking.
- Dùng `--rerun-tasks` để chắc chắn tests đã chạy.
- Chạy lặp vài lần, dùng median và peak memory, tránh kết luận theo một mẫu.
- Thu duration của **test task**, không gộp cả dependency resolution hoặc compile cold cache vào startup cost.
- Ghi PIDs/worker IDs và context cache counters riêng từng process.
- Kiểm failures/skips: performance không đáng đổi lấy flaky suite.
- Khi dùng CI shared runner, mức CPU/memory có thể thay đổi theo workload khác.

### 13.6. Reports

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.forkcache.CacheAlphaTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheBetaTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheVariantTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheMechanicsTest.xml
build/test-results/test/TEST-com.example.forkcache.NameFormatterTest.xml
~~~

Không có exact stdout cố định vì PID, UUID, order, timestamps và Gradle scheduler phụ thuộc runtime. Nếu đã chạy thật, mở JUnit XML/HTML để xác minh **10 methods** được phát hiện và kết quả thực.

## 14. Vì sao Gradle UP-TO-DATE không phải Spring cache hit?

Các cơ chế có tên gần giống nhưng phạm vi khác:

| Cơ chế | Nó lưu gì? | Tác động |
| --- | --- | --- |
| **Spring TestContext cache** | ApplicationContext objects đang sống | Reuse giữa tests cùng key trong một JVM |
| Gradle task UP-TO-DATE | Input/output snapshot/history | Có thể bỏ qua test task |
| Gradle build cache | Task outputs | Có thể reuse results mà không chạy tests |
| Gradle configuration cache | Build configuration state | Rút ngắn giai đoạn cấu hình build, không chứa Spring bean graph |
| JVM class/JIT cache | Bytecode/classes/JIT state | JVM-local warmup, không phải Spring context sharing |
| Gradle daemon reuse | Build execution process | Không bảo toàn test worker's static Spring cache qua build mặc định |

`./gradlew test` trả `UP-TO-DATE` nghĩa là tests **không được thực thi lại** trong invocation đó. Không có Spring cache hits mới để quan sát. `--rerun-tasks` ép task chạy, **không** làm Spring cache tồn tại xuyên hai Gradle invocations.

## 15. Nhiều Test tasks và multi-module

Trong multi-module repository có thể có:

~~~text
:core:test
:api:test
:integrationTest
~~~

Mỗi Gradle Test task quản lý các test worker processes của nó. Không tự chia sẻ Spring static cache giữa các JVMs của hai tasks, kể cả cùng Git repository, cùng classpath hay cùng main application class.

`--parallel` có thể làm các tasks của nhiều modules chạy đồng thời. Điều này có thể giúp wall-clock, nhưng thêm nhiều contexts/DB connections/containers ở cùng thời điểm. Không gộp tất cả tests vào một task chỉ nhằm “ép reuse context” mà làm mất ranh giới unit/integration và reporting hợp lý.

### Sử dụng các layers đúng mục đích

- **JUnit thuần:** logic không cần Spring DI.
- **Spring slice tests:** `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` khi muốn kiểm một layer.
- **`@SpringBootTest` non-web:** wiring/auto-configuration/services.
- **`@SpringBootTest(RANDOM_PORT)`**: HTTP/server boundary thật.
- **Testcontainers integration tests:** DB/broker semantics cần môi trường thật.
- **End-to-end/proxy/browser tests:** boundary TLS, routing, auth gateway và clients.

Một suite chỉ có unit tests không cần optimize Spring context cache. Một suite full `@SpringBootTest` cần xem số unique keys trước khi tăng forks.



## 16. JUnit parallel threads khác Gradle forked processes

JUnit Jupiter hỗ trợ parallel execution **trong cùng JVM** khi bật configuration:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
~~~

Các methods/classes chạy trên nhiều threads vẫn có thể sử dụng **một static TestContext cache**. Nhưng đồng thời có thể dẫn đến race ở:

- Shared mutable singleton beans;
- Static fields và fixtures;
- Shared `@MockBean` stubbing/reset;
- Cùng DB rows hoặc tables;
- Testcontainers, ports hoặc file names;
- `@DirtiesContext` đóng context khi thread khác đang dùng;
- Schedulers/clock overrides;
- Transaction side effects qua HTTP server threads.

Không đồng nhất “cùng cache” với “test an toàn chạy đồng thời”. Với data không độc lập, dùng per-test IDs, transaction boundaries, JUnit resource locks hoặc tách resources; không bật parallel mode vô điều kiện.

## 17. Hệ quả tới Testcontainers, DB pool và memory

Một context khởi động có thể tạo Hikari datasource, Kafka/RabbitMQ clients, Redis, HTTP pools, background executors hoặc Testcontainers resources. Khi nhiều Gradle forks chạy:

- Mỗi JVM dựng Spring bean graph của mình.
- Mỗi context có thể tạo **pool/connections riêng**.
- Một static Testcontainers field vẫn là **per JVM**, không tự dùng chung giữa workers.
- Các JVMs có thể cùng truy cập **external shared database** và gây collision, dù Spring context không chia sẻ heap.
- `@SpringBootTest(RANDOM_PORT)` tránh nhiều collision của HTTP listening port, nhưng mỗi worker vẫn có embedded server riêng.
- Một DB connection limit có thể bị vượt nếu số workers × contexts × pool size tăng.

Ví dụ giả định: mỗi JVM có một pool size tối đa 10; bốn JVM cùng hoạt động có thể cần nhiều connections hơn một JVM. Không dùng `4 × 10` như con số RSS hay connections chắc chắn, vì lazy pools và số contexts thay đổi.

### Không quên test data isolation

Nếu nhiều forks dùng chung database/broker, hãy dùng unique row keys, schemas/tenants theo worker hoặc cleanup có kiểm soát. `org.gradle.test.worker` có thể giúp đặt tên test resources trong một build, nhưng không là định danh bền vững across builds. Tránh port/file hardcode và không giả định JVM isolation cũng là database isolation.

### Chú ý rollback qua HTTP

Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, client request và server handler có thể chạy khác threads/transactions. `@Transactional` trên test method không tự rollback transaction của HTTP server request. Tách cleanup dữ liệu thật thay vì tăng cache invalidation.

## 18. @DirtiesContext đúng chỗ, không phải liệu pháp chung

Annotation `@DirtiesContext` là công cụ **evict context** khi đã thay đổi/corrupt state ở cấp context. Nó không phải mặc định cho mọi test ghi database. Dùng khi:

- Test thay bean definitions hoặc singleton state khó reset;
- Test cần kiểm lifecycle start/stop/restart;
- Một context-specific resource không thể reuse an toàn.

Không nên gắn mọi test classes chỉ vì:

- Dữ liệu DB chưa được cleanup;
- Một Mockito mock chưa được reset;
- Một file có thể đặt trong `@TempDir`;
- Một test có shared mutable static field;
- Một task fail khi chạy cùng lớp khác.

Hãy sửa state isolation thay vì đánh đổi hàng chục lần Spring startup. Với nhiều forks, @DirtiesContext chỉ evict **cache trong JVM hiện tại**, không hề broadcast tới workers khác.

## 19. Cache size 32 và tối ưu theo số keys

Spring cache mặc định 32 contexts với LRU. Trong một worker cần 40 distinct keys, có thể xảy ra eviction/thêm startup nếu các keys cũ được dùng lại. Tăng `spring.test.context.cache.maxSize` có thể giảm churn nhưng tăng heap memory. Với 4 JVMs, mỗi JVM giữ riêng entries nên peak memory còn tăng.

Cách tốt hơn trước khi nâng maxSize:

1. Đếm unique context configurations.
2. Giảm variations không cần thiết của `@MockBean`, profiles, inline properties.
3. Dùng base test annotations/config chung khi thực sự cùng behavior.
4. Dùng JUnit thuần/slices cho tests không cần full context.
5. Tránh `@DirtiesContext` tràn lan.
6. Kiểm inherited `@DynamicPropertySource` có ổn định cùng resource lifecycle.
7. Giữ JUnit parallelism phù hợp thread-safety.
8. Đo cache miss/hit ở từng process, heap và wall-clock.

**Không chỉnh security/bean wiring test để dùng sai config chỉ nhằm tăng cache hit.** Tính đúng vẫn là ưu tiên.

## 20. Failure threshold trong các worker riêng

Khi một context K bị lỗi khởi động lần đầu, Spring Framework 6.1 có thể đánh dấu K đã vượt failure threshold trong cache đó. Các test sau cùng key trong worker ấy gặp một lỗi nhanh `ApplicationContext failure threshold exceeded`. Nhưng worker khác vẫn phải thực hiện attempt riêng nếu nó chưa thấy lỗi.

### Quy trình chẩn đoán

1. Tách logs theo PID và Gradle worker ID.
2. Tìm **failure gốc đầu tiên** trong mỗi worker (ví dụ missing bean, connection refused).
3. Không hiểu threshold-exceeded là root cause mới.
4. Kiểm config/credentials/resources và ports đã đúng chưa.
5. Không đặt threshold cực lớn để retry cùng một lỗi deterministic.
6. Nếu dependency ngoài cần readiness, dùng startup coordination/checks phù hợp, không sleep vô hạn.
7. Không trộn counters của các JVMs khi làm báo cáo.

## 21. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| Cùng cấu hình nhưng nhiều startups | Tests chạy nhiều JVM forks | Kiểm PID, maxParallelForks, forkEvery |
| `forkEvery=1` suite rất chậm | Mỗi class có JVM/cache mới | Chọn forkEvery=0 nếu tests cô lập |
| Một test class riêng pass, suite fail | Shared state/external resource | Sửa data isolation, không chỉ fork |
| Nhiều PID dù forks=1 | Recycle theo forkEvery, nhiều Test tasks | Kiểm task/fork policy |
| forks=4 nhưng chỉ 2 PIDs | Max là giới hạn, scheduler/worker slots | Không assert đủ 4 |
| Context IDs trùng giữa PIDs | ID không phải object identity toàn cục | Ghi PID + marker |
| Cache size=2, hitCount cao trong một worker | Đúng trong-worker reuse | Không suy global hits từ nó |
| Tăng maxSize nhưng OOM | Nhiều cached contexts × forks | Đo heap, giảm unique keys |
| @DirtiesContext làm test chậm | Evict/restart lặp lại | Chỉ dùng khi context thật sự dirty |
| @MockBean mỗi test khác nhau | Tạo nhiều context keys | Gom config tương đồng, dùng unit/slice |
| Spring cache DEBUG không xuất hiện | Logger category/initialization sai | Dùng logback-test.xml |
| Test task UP-TO-DATE | Gradle không chạy tests | Dùng --rerun-tasks để benchmark |
| --parallel bật mà test classes chưa chạy đồng thời | Tác động task-level | Phân biệt Gradle vs JUnit |
| Testcontainers chạy nhiều bản | Static container per JVM | Thiết kế lifecycle/resource limits |
| DB connection limit exceeded | Pools nhân theo workers | Giảm forks/pool size, cô lập DB |
| 401/port conflict chỉ xảy ra song song | Shared external state/static port | Unique endpoints/data per worker |
| failure threshold exceeded lặp lại | Mỗi worker có failure cache riêng | Tìm error đầu tiên từng PID |
| JUnit parallel làm mock reset race | Shared context/bean giữa threads | Serialize/scope mocks đúng |
| Bench một lần mâu thuẫn | Noise, CI contention | Lặp runs, đo median/peak |
| Classloader khác trong cùng JVM | Static fields theo classloader | Hiểu test classloader boundaries |
| Tests phụ thuộc marker giữa classes | Gradle scheduler không ổn định | Assert bên trong một method/JVM |

## 22. Bảng thu thập số liệu benchmark

| Thuộc tính | Ghi nhận |
| --- | --- |
| Commit/JDK/Gradle/Boot versions | Cùng source/runtime |
| maxParallelForks | 1, 2, 4… |
| forkEvery | 0, N hoặc 1 |
| JUnit parallel mode | Bật/tắt, threads |
| Gradle max workers | Giới hạn worker slots |
| Số test methods/classes | Không được thay giữa runs |
| Distinct test JVM PID count | Process thực dùng |
| Cache miss/hit snapshot **per PID** | Không cộng cumulative log lines |
| Unique config keys | Mức độ đa dạng contexts |
| Task wall-clock | KPI chính về tốc độ |
| Peak RSS/heap/GC | Memory pressure |
| DB/broker connections | External pressure |
| Flaky/fail/skipped | Test correctness |
| Gradle task state | Có thực thi hay chỉ UP-TO-DATE |

Một kết luận mẫu: “4 forks giảm median test task từ 80s xuống 65s nhưng tăng peak RSS thêm 1,8GB; CI runner còn đủ RAM và không có failures.” **Đây là ví dụ định dạng báo cáo**, không phải kết quả chạy của project này.

## 23. Bài tập thực hành

**A.** Chạy `testForks=1, testForkEvery=0` và so marker của Alpha/Beta khi cùng worker. Chạy `CacheMechanicsTest` để thấy `assertSame` độc lập scheduler.

**B.** Chạy `testForks=4` và ghi những PIDs/worker IDs thực xuất hiện; giải thích vì sao có thể ít hơn 4.

**C.** Bật `forkEvery=1` rồi so số lần khởi động context và wall-clock với baseline.

**D.** Thay `CacheVariantTest` property về default và xem cache key tương đồng hơn.

**E.** Thêm `@ActiveProfiles("demo")` vào một class; dự đoán context key khác.

**F.** Tạo hai classes có bộ `@MockBean` khác nhau và quan sát số context loads.

**G.** Tạo test có `@DynamicPropertySource` riêng; kiểm identity/initializer lifecycle.

**H.** Dùng `@DirtiesContext(AFTER_CLASS)` đúng một class; so cache hit/miss của key liên quan.

**I.** Giới hạn `contextCacheSize=2`, tạo vài config variants và quan sát LRU eviction.

**J.** Chạy Gradle test hai lần không `--rerun-tasks`; phân biệt Gradle UP-TO-DATE với Spring cache hit.

**K.** Bật JUnit parallel threads trong một branch riêng; xác minh cùng PID/cache nhưng shared mutable bean có thể race.

**L.** Chạy một Testcontainers PostgreSQL test với 1/4 forks; đo container count và DB connections.

**M.** Tách `test` và `integrationTest` tasks; chứng minh không có context sharing qua test worker processes.

**N.** Tạo một invalid context có lỗi startup; quan sát failure threshold trong mỗi PID.

**O.** Dùng Spring cache DEBUG và trích snapshot cuối per PID, không cộng hitCount từng log line.

**P.** Chạy trên CI runners 2 CPU/8GB và 8 CPU/16GB; chọn forks bằng số liệu thực.

**Q.** Chuyển business formatter tests sang JUnit thuần và so chi phí khởi động Spring giảm.

**R.** Đổi một inline property trong mỗi class rồi quan sát số keys tăng/giảm.

**S.** Thêm một `@SpringBootTest(RANDOM_PORT)` smoke test và kiểm không hardcode port khi chạy parallel forks.

**T.** Thực hiện mutation gây shared static state leak, sửa bằng isolation chứ không vội `forkEvery=1`.

## 24. Checklist trước khi merge thay đổi Gradle test parallelism

- [ ] Đã phân biệt Gradle forked JVM với JUnit threads?
- [ ] Không kỳ vọng Spring static cache dùng chung giữa PIDs?
- [ ] Đã hiểu mặc định `maxParallelForks=1`?
- [ ] Đã hiểu `forkEvery=0` là reuse forked JVM, không phải không fork?
- [ ] Không mặc định `forkEvery=1` cho SpringBootTest suite?
- [ ] Biết `org.gradle.test.worker` hữu ích để phân biệt workers?
- [ ] Có PID/marker/context identity diagnostics khi cần?
- [ ] Không lấy `ApplicationContext.getId()` làm unique object proof?
- [ ] Cache keys đúng với classes/profiles/properties/mocks/dynamic config?
- [ ] Không loại bỏ scenario riêng chỉ để tăng reuse?
- [ ] Chỉ dùng @DirtiesContext khi thật sự cần?
- [ ] Biết maxSize=32 và LRU eviction áp dụng cho từng cache JVM?
- [ ] Biết failure threshold=1 từ Spring Framework 6.1 cũng per key/cache?
- [ ] Không so Gradle UP-TO-DATE với real test run?
- [ ] Có `--rerun-tasks` trong benchmark?
- [ ] Không assert Gradle luôn tạo đúng maxParallelForks JVMs?
- [ ] Assertions trong test độc lập cách Gradle phân lớp?
- [ ] Có benchmark nhiều lần về wall-clock, CPU, RSS, GC và flaky rate?
- [ ] Không mở port/file cố định giữa forks?
- [ ] Database/broker/Testcontainers resources được cô lập?
- [ ] Không gộp tất cả unit tests vào @SpringBootTest?
- [ ] Test contexts chứa singleton state được reset an toàn?
- [ ] Không lạm dụng mocks/variant properties tạo keys thừa?
- [ ] Có giới hạn resource pools phù hợp parallelism?
- [ ] Gradle Test task và CI worker limits đã được kiểm?
- [ ] Không dùng JUnit parallelism khi beans/test data chưa thread-safe?
- [ ] Báo cáo nói rõ limitations và measurement methodology?
- [ ] Java 17, Boot 3.3.5, Gradle 8.8 đúng compatibility?
- [ ] JUnit report chứng minh 10 methods chạy thật, không chỉ cached result?

## 25. Tài liệu tham khảo chính thức

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache key, static JVM scope, maxSize=32, LRU và logging.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): policy từ 6.1, system property và lỗi skipped.
- [Spring Framework 6.1 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContextManager.html): `getTestContext`, lifecycle.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): eviction semantics.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): maxParallelForks, forkEvery và worker property.
- [Gradle — Test task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): test process settings, JVM properties.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): test process forking, tradeoffs.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest, slices và context testing.
- [JUnit Jupiter 5.10 — Parallel Execution](https://docs.junit.org/5.10.2/user-guide/#writing-tests-parallel-execution): thread-level parallelism.
- [Java 17 — ProcessHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID diagnostics.

**Ghi nhớ:** Spring TestContext cache được lưu trong `static` memory của **mỗi** Gradle test worker JVM. Tăng `maxParallelForks` tạo thêm cơ hội chạy đồng thời nhưng không chia sẻ context giữa workers; đặt `forkEvery=1` thường làm giảm mạnh reuse giữa classes. Để tối ưu, giữ keys ổn định, hạn chế @DirtiesContext không cần thiết, tách unit/slice/full-context tests, đo cache hit/miss theo PID và benchmark wall-clock/memory/DB pressure trong điều kiện CI thật.
