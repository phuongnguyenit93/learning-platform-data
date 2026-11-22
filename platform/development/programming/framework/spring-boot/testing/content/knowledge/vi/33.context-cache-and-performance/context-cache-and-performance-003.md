# Quan sát cache hit, miss và số context thực sự được tạo

## 1. Bài toán: vì sao Spring Boot test suite khởi động chậm?

Trong nhóm **Context cache và hiệu năng** của Spring Boot testing, một khó khăn phổ biến là test suite có hàng trăm JUnit methods, nhưng mỗi lần chạy lại xuất hiện nhiều dòng “Starting ...”, nhiều database pools khởi tạo, container hoặc embedded server bị tạo lại. Người học thường nhầm **số test methods** với **số ApplicationContext** được tạo.

Spring TestContext Framework có **ApplicationContext cache** dùng lại Spring contexts giữa những tests có **cấu hình tương đương**. Khi test A và test B có cùng cấu hình theo cache key, Spring có thể giữ context A đã khởi tạo, sau đó test B dùng chính object context đó thay vì bootstrap lại toàn bộ beans.

Nhưng có những tình huống làm cache miss:

- Test có `@SpringBootTest(properties=...)` khác nhau.
- Profile hoặc `@TestPropertySource` khác.
- Từng class dùng tập `@MockBean`/`@SpyBean` khác nhau ở Spring Boot 3.3.
- Có `@DynamicPropertySource` methods hoặc context customizers khác.
- Một test đánh dấu `@DirtiesContext` làm context bị xóa khỏi cache.
- Suite tạo hơn số lượng contexts mà LRU cache giữ được, dẫn đến eviction rồi reload.
- Gradle/Maven chạy nhiều JVM processes: cache trong JVM này không thể dùng ở JVM khác.

**Mục tiêu của bài:** biết cách quan sát **cache hit**, **cache miss**, **số context hiện đang được cache**, **số lần thực sự tạo mới context** và lý do chúng có thể khác nhau. Học viên phải đọc metrics/logs đúng bản chất, thay vì nói “20 miss nghĩa là 20 cấu hình context khác nhau” hoặc “200 tests nghĩa là 200 contexts”.

Ví dụ sử dụng **Java 17, Spring Boot 3.3.0, Spring Framework 6.1, JUnit Jupiter, Gradle**. Có dự án chạy được, với `TestContextManager` tạo các fixture contexts có cùng/khác cache keys, một bean đánh dấu lần khởi tạo và phép đánh dấu dirty để kiểm chứng context reload. Những số liệu test được mô tả là **kết quả dự kiến**, không phải báo cáo đã thực thi Gradle trên máy của bạn.

## 2. Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt Spring TestContext **ApplicationContext cache** với `@Cacheable` business cache, Hibernate 2nd-level cache và Gradle build cache.
2. Giải thích vì sao Spring có thể chia sẻ một `ApplicationContext` giữa nhiều JUnit methods/classes.
3. Xem DEBUG logs ở `org.springframework.test.context.cache`.
4. Đọc `hitCount`, `missCount`, `size`, `maxSize`, `parentContextCount` và khi có `failureCount`.
5. Hiểu cache key dựa vào **MergedContextConfiguration**, không chỉ tên class.
6. Phân biệt **cache hit request count** với **số context được tạo lần đầu**.
7. Phân biệt `missCount` với **số cache keys duy nhất**, do eviction và reload.
8. Biết default cache max size là **32 contexts**, LRU eviction và cấu hình `spring.test.context.cache.maxSize`.
9. Biết cache được giữ bằng **static state trong cùng JVM process**; fork khác không chia sẻ.
10. Biết `@DirtiesContext` evict/close context và lần sau sẽ phải load lại.
11. Hiểu tại sao dùng `@DirtiesContext` cho mọi test phá lợi ích caching.
12. Biết `@MockBean`/`@SpyBean` ở Spring Boot 3.3 góp phần thay đổi context cache key.
13. Biết `@ActiveProfiles`, inline properties và `@TestPropertySource` thay đổi key.
14. Hiểu `@DynamicPropertySource` thường tham gia key bằng **method định nghĩa dynamic properties**, không phải ngẫu nhiên bằng giá trị mỗi lần gọi supplier.
15. Tạo một `ContextMarker` bean có static sequence counter để quan sát **mỗi lần bean được tạo trong context mới**.
16. Kiểm tra hai fixture classes có cấu hình giống nhau dùng **cùng ApplicationContext instance**.
17. Kiểm tra khác inline property hoặc active profile tạo **context identity khác**.
18. Kiểm tra dirtying context làm context được load lại và marker sequence tăng.
19. Biết giới hạn của marker counter: nó không đếm context không chứa marker hoặc load thất bại trước bean creation.
20. Không sử dụng cache internal/private APIs/reflection để ép hit/miss counters cho một business test thông thường.
21. Biết cách giữ tests độc lập khi chia sẻ singleton beans có mutable state.
22. Hiểu lợi/hại của test slices (`@WebMvcTest`, `@DataJpaTest`) và full `@SpringBootTest`.
23. Biết context cache thống kê từ đâu, khi nào log chỉ là cumulative snapshot.
24. Hiểu Spring 6.1 context failure threshold khác với cache miss/hit.
25. Đề xuất cách đo startup overhead qua test logs, Gradle test results và real profiler, thay vì bịa latency.
26. Xây dựng checklist QA về hiệu năng, tính tái hiện và độ tin cậy của Spring tests.

## 3. Bản chất Spring TestContext context cache

```text
JUnit test runner (same JVM)
        |
        v
Spring TestContext Framework
        |
        +-- MergedContextConfiguration -> cache key
        |
        +-- Lookup static ContextCache
               |
               +-- HIT: key exists
               |       return cached ApplicationContext
               |       reuse bean graph / data sources / services
               |
               +-- MISS: key absent
                       load/refresh ApplicationContext
                       cache it under key
                       return to test
        |
        v
Test method uses injected Spring beans
```

Spring cache giữ object **ApplicationContext** được khởi tạo trước đó, không chỉ lưu một danh sách bean definitions. Vì vậy cache hit có thể tránh nhiều công việc tốn thời gian: component scan, condition evaluation, bean creation, datasource initialization, connection pool, embedded server startup, v.v.

Nhưng dùng lại context cũng có nghĩa singleton beans, `Environment`, datasources, caches, schedulers và resources của context đó có thể tồn tại qua nhiều tests. **Reuse context không phải reset dữ liệu tự động.** Tests vẫn phải làm sạch database, queues, cache và state thuộc nghiệp vụ bằng đúng phạm vi.

### 3.1. Context cache không phải @Cacheable

| Cache | Ai vận hành? | Lưu gì? | Mục tiêu |
| --- | --- | --- | --- |
| Spring TestContext cache | Spring `spring-test` | `ApplicationContext` objects | Tránh startup lặp |
| Spring Cache `@Cacheable` | Application cache abstraction | Business method results | Giảm tải xử lý |
| Hibernate 1st-level cache | Persistence context | Managed entities | ORM unit-of-work |
| Hibernate 2nd-level cache | ORM cache provider | Entity/query data | Giảm DB reads |
| Gradle build cache | Build system | Compilation/task outputs | Tránh build lại |
| Docker image cache | Container runtime | Image layers | Giảm pull/build |

Một log `ContextCache hitCount=...` **không** nói Redis của ứng dụng có cache hit. Ngược lại, `@Cacheable` hoạt động tốt không bảo đảm Spring test context được reuse.

### 3.2. Thời điểm lookup

Spring có thể lookup context nhiều lần cho việc chuẩn bị test instance, dependency injection, test lifecycle callbacks hoặc truy cập `TestContext.getApplicationContext()`. Vì vậy một JUnit method **không tương ứng chính xác một lần lookup**.

Đừng lấy `hitCount` rồi trừ cho tổng `@Test` methods để tính “số tests cached”. Nó là **counter của cache accesses**, không phải metric có một-to-một mapping với tests.

## 4. Cache key gồm những gì?

Spring xác định cache key từ một `MergedContextConfiguration` có thể bao gồm:

- `locations` và `classes` trong `@ContextConfiguration`.
- `contextInitializerClasses`.
- `contextCustomizers`: bao gồm customizers của Spring Boot test support; `@DynamicPropertySource` methods, `@MockBean`/`@SpyBean` trong Boot 3.3 và các test customizers khác.
- `contextLoader`.
- `parent` trong context hierarchy.
- `activeProfiles` từ `@ActiveProfiles`.
- `propertySourceDescriptors`/property source locations trong `@TestPropertySource`.
- `propertySourceProperties`, gồm inline properties từ test configuration.
- `resourceBasePath` với web context configuration.

Chi tiết thuộc Spring Framework version; không tự coi danh sách này là một JSON cache key có thứ tự ổn định. Điều quan trọng là **hai tests “trông gần giống nhau” vẫn có thể tạo hai keys** nếu một cấu hình thành phần khác.

### 4.1. Cùng test configuration -> reuse

Hai fixture classes:

```java
@SpringBootTest(
    classes = CacheStudyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "study.mode=shared")
class A {}

@SpringBootTest(
    classes = CacheStudyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "study.mode=shared")
class B {}
```

Đây là ví dụ khái niệm (tên `CacheStudyApplication` không thuộc project runnable). Nếu các thành phần khác của cache key tương đương và contexts chưa bị evict/dirty, A và B có thể reuse cùng context. **Tên test class khác nhau tự nó không mặc định ép context khác**, nếu merged configuration tương đương.

### 4.2. Khác property -> khác key

```java
@SpringBootTest(properties = "feature.demo=enabled")
class FeatureOnTest {}

@SpringBootTest(properties = "feature.demo=disabled")
class FeatureOffTest {}
```

Hai inline properties khác nên merged configurations khác; chia sẻ cùng Spring main class chưa đủ để hit. Tương tự, `@ActiveProfiles("test")` và `@ActiveProfiles("integration")` thường tạo hai keys.

### 4.3. @MockBean làm context key phân mảnh

Ở Spring Boot **3.3**, `@MockBean`/`@SpyBean` tạo context customizers phù hợp với mock definitions:

```java
@SpringBootTest
class FirstTest {
    @MockBean PaymentClient paymentClient;
}

@SpringBootTest
class SecondTest {
    @MockBean InventoryClient inventoryClient;
}
```

Đây là snippet minh họa, cần mock target classes và imports. Hai tập mock khác nhau thường dẫn đến cache key khác nhau, dù service graph lớn giống nhau. Khi có hàng trăm tests mỗi test mock một tập riêng, context fragmentation rất đáng kể.

**Lưu ý versions:** Spring Boot 3.4 deprecates `@MockBean` để chuyển dần sang Spring Framework `@MockitoBean`; project học này cố định Boot 3.3 nên không mix imports từ phiên bản mới hơn.

### 4.4. @DynamicPropertySource

Một method `@DynamicPropertySource` thường tham gia cache key thông qua `ContextCustomizer` đại diện cho method đó. **Giá trị supplier runtime trả về không tự động biến thành phần tử khác của cache key mỗi lần đọc.** Điều này đặc biệt nguy hiểm với Testcontainers:

```java
@DynamicPropertySource
static void datasource(DynamicPropertyRegistry registry) {
    registry.add("service.url", container::getUrl);
}
```

Đây là snippet, cần `container` được định nghĩa. Nếu hai test classes chia sẻ/inherit cùng dynamic property method nhưng thực ra dùng hai container instances với host/port thay đổi, Spring có thể reuse context giữ connection tới container cũ. Cách sửa là thiết kế container lifecycle khớp context lifecycle, hoặc dùng `@DirtiesContext` có chủ đích khi thực sự khác external resource.

### 4.5. Test slices tạo keys khác

`@WebMvcTest`, `@DataJpaTest`, `@JsonTest` và `@SpringBootTest` nạp các scopes/auto-config khác nhau. Không coi các slices nhất thiết cùng cache key; thậm chí hai `@WebMvcTest` classes khác controllers/imports/mocks có thể tạo keys khác.

## 5. Hit, miss và số contexts: đọc đúng ý nghĩa

| Chỉ số | Cách hiểu | Không nên hiểu thành |
| --- | --- | --- |
| `hitCount` | Số lần cache lookup tìm thấy một context theo key | Số tests được thực thi thành công |
| `missCount` | Số lần lookup không có cached context phù hợp | Số distinct configurations vĩnh viễn |
| `size` | Số contexts hiện đang được giữ trong cache | Tổng contexts đã từng được tạo |
| `maxSize` | Giới hạn số entries của cache | Tổng contexts được phép tạo cả suite |
| `parentContextCount` | Thông tin context hierarchy đang được cache | Số parent test classes |
| `failureCount` | Chỉ số liên quan load failures nếu được hiển thị | Số assertions/JUnit tests failed |

### 5.1. Một key được load, dùng lại nhiều lần

```text
Lookup key "A" -> MISS -> create Context#1
Lookup key "A" -> HIT  -> reuse Context#1
Lookup key "A" -> HIT  -> reuse Context#1
Lookup key "A" -> HIT  -> reuse Context#1

Requests:      4
Misses:        1
Hits:          3
Contexts made: 1
Current size:  1
```

Các số là mô hình đơn giản với đúng bốn lookups; thực tế Spring TestContext có thể perform thêm lookups nội bộ.

### 5.2. LRU eviction và reload

```text
maxSize = 2 (ví dụ để minh họa, không phải default)

Lookup A -> MISS -> create A#1
Lookup B -> MISS -> create B#1
Lookup C -> MISS -> create C#1
           evict least-recently-used A#1

Lookup A -> MISS -> create A#2
           evict another older entry

Distinct cache keys observed: 3 (A,B,C)
Context instances created:   4
Misses in this simple trace:  4
Current cache size:           2
```

**Cốt lõi:** dù chỉ có ba cấu hình khác nhau, key A bị load lại sau eviction. Vì vậy `missCount` không phải là `uniqueDistinctContextCount`; `size` cũng không phải tổng đã khởi tạo.

### 5.3. @DirtiesContext khiến cùng key miss lại

```text
Load A -> create A#1
Mark A dirty -> remove/close A#1
Load A again -> create A#2
```

Cùng một key, nhưng có hai context instances. Count tạo mới tăng, dù không thêm một test profile/property nào.

### 5.4. Load failure không phải successful context creation

Một context load có thể fail vì bean creation, wrong property, missing Kafka/DB hoặc test container chưa start. Cache lookup miss có thể tăng nhưng context chưa refresh thành công. Spring Framework 6.1 có **context failure threshold** (mặc định 1 per key) để fail-fast những lần load tiếp theo. Đừng lấy missCount rồi tuyên bố từng ấy contexts đã chạy thành công.

## 6. Mặc định 32 contexts và LRU policy

Spring TestContext cache dùng một **bounded static cache** trong JVM, với default **maximum size 32**. Khi vượt giới hạn, nó evict và close các contexts ít được dùng gần đây nhất theo **LRU**.

Có thể cấu hình JVM system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Đặt từ Gradle test task:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'spring.test.context.cache.maxSize', '64'
}
```

Hoặc từ Maven Surefire/Failsafe JVM config phù hợp; không đặt `spring.test.context.cache.maxSize=64` trong application.properties rồi mặc định nghĩ JVM system property đã được thiết lập sớm như mong muốn. Tài liệu cho phép dùng `SpringProperties` mechanism, nhưng cấu hình JVM test process là con đường rõ ràng.

### 6.1. Đừng tự động tăng maxSize thật cao

Lợi ích: giảm eviction/reload khi nhiều distinct keys.

Đổi lại: giữ nhiều beans, datasources, Hikari pools, executor threads, network clients, embedded servers và native memory cùng lúc. JVM có thể gặp heap pressure, port pressure hoặc memory thrashing. Cần đo **số distinct keys + heap/offheap/process resources** trước khi tăng.

### 6.2. Cache static theo JVM, không chia sẻ giữa forks

TestContext cache lưu trong static variables. Khi build tool tạo **forked JVM processes**, mỗi JVM có cache độc lập. Cùng test class cấu hình giống nhau chạy ở hai processes vẫn bootstrap hai contexts (mỗi process một).

Các tùy chọn cần kiểm tra:

- Gradle `maxParallelForks` > 1 tạo nhiều test workers.
- Gradle `forkEvery` > 0 có thể tạo mới worker sau mỗi N classes.
- Maven Surefire/Failsafe `forkCount` và `reuseForks`.
- IDE có thể chạy mỗi configuration trong process khác.
- CI sharding chia test suite sang máy/containers khác nhau.

Không đổ lỗi cho Spring cache miss khi thực tế build process boundaries đã phá khả năng reuse.

## 7. Đọc DEBUG thống kê cache từ log

Bật log level:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Nếu dùng Spring Boot test và Logback, có thể lưu vào `src/test/resources/application.properties`. Vì cache logging có thể xảy ra sớm trong bootstrap, có thể đặt logger qua logging config được kích hoạt sớm hoặc JVM/test logging configuration tùy dự án. Log level này chỉ nhằm debug test suite; không cần bật cho production.

Một mẫu log mang tính **minh họa**:

```text
Spring test ApplicationContext cache statistics:
[DefaultContextCache@... size = 3, maxSize = 32,
 parentContextCount = 0, hitCount = 18,
 missCount = 3, failureCount = 0]
```

Chính xác format/order/các fields có thể khác theo Spring Framework version. Bạn cần đọc **dữ liệu thực từ test log**, không lấy số 18/3/3 ở ví dụ làm kết quả run.

### 7.1. Snapshot cumulative, không phải per method

Cache stats thường tích lũy trong cùng JVM. Một log sau test class B bao gồm lookup từ test A. Các DEBUG lines lặp lại do nhiều access; đừng cộng `hitCount` của từng dòng như incremental deltas — các số đã là cumulative snapshots.

### 7.2. Cách phân tích khi biết total method count

Ví dụ một suite có 500 methods, cache log cuối báo hits 1.600, misses 12, size 10:

- Điều chắc chắn: nhiều cache lookups reuse contexts; chỉ 10 entries hiện được giữ; 12 lookups miss.
- Không thể suy ra “đúng 488 tests cache hit”.
- Không thể khẳng định có đúng 12 distinct context configs, vì có thể có reload/evictions hoặc failed loads.
- Muốn biết số instances thực được tạo, cần thêm nguồn đo: startup logs có context identity, marker bean, controlled diagnostics hoặc trace load events.

### 7.3. Các context cache entries có thể có parent

Với `@ContextHierarchy`, parent contexts và child contexts có quan hệ đặc biệt khi eviction/dirtying; `parentContextCount` không phải count test classes. Khi phân tích size/miss, hiểu hierarchy mode và không tùy tiện mark dirty EXHAUSTIVE ở một child nếu không cần ảnh hưởng parent/siblings.

## 8. Đếm số context thực được tạo bằng bean marker

Để quan sát một context **thực sự khởi tạo bean graph**, ta dùng một singleton bean `ContextMarker` mà factory method tăng static `AtomicInteger`:

```java
private static final AtomicInteger CREATED =
        new AtomicInteger();

@Bean
ContextMarker contextMarker() {
    return new ContextMarker(
            CREATED.incrementAndGet());
}
```

Trong demo, `ContextMarker` là một singleton eager bean. Mỗi **ApplicationContext refresh thành công** có bean đó sẽ tạo một instance marker; một cached context được reuse thì không tạo marker mới.

**Giới hạn quan trọng:**

- Counter chỉ đếm các contexts **chứa marker** và đã chạy tới bean creation, không đếm toàn bộ context types của cả công ty.
- Nếu bootstrap fail trước marker bean, số counter không tăng dù có một cache miss/load attempt.
- Nếu có parallel contexts, static counter phản ánh tổng của JVM; assertions theo thứ tự phải đồng bộ/isolated.
- Counter static reset khi JVM process mới được tạo; không gộp trực tiếp counters từ nhiều forks.
- Không thêm bean test marker vào production chỉ để đo test suite; dùng `@TestConfiguration`/dedicated fixture khi cần.

### 8.1. Instance identity vs Context.getId()

`ApplicationContext.getId()` thường là một tên ID dùng cho diagnostics, không được bảo đảm là unique vĩnh viễn qua refresh/recreation. `System.identityHashCode(context)` cũng có thể trùng về mặt lý thuyết. Để test reuse, dùng `assertSame(a,b)` và `assertNotSame(a,c)` trên Java object references. Marker sequence cho biết bean factory đã chạy bao nhiêu lần trong process.

### 8.2. Không đếm Context chỉ bằng @BeforeAll

`@BeforeAll` gọi theo JUnit test class, không phải context startup. Một context có thể được dùng bởi 20 test classes (20 BeforeAll callbacks nhưng một context). Vì vậy counter phải gắn vào **bean creation/context refresh**, không gắn với test lifecycle method.

## 9. Dự án Java 17 + Spring Boot 3.3 runnable

### 9.1. Cây thư mục

```text
context-cache-observer/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/contextcache/
    │   └── ContextCacheProbeApplication.java
    └── test/
        ├── java/example/contextcache/
        │   └── ContextCacheBehaviorTest.java
        └── resources/
            └── application.properties
```

Dự án chỉ có một main class chứa singleton marker bean và một test class dùng các nested configuration fixtures. Không có database, Docker hay HTTP server nên dễ quan sát mỗi context startup. `TestContextManager` được dùng có chủ đích như một **diagnostic harness** để tạo nhiều test contexts tuần tự trong một JUnit method; tests ứng dụng thông thường vẫn dùng `@SpringBootTest` trực tiếp.

### 9.2. settings.gradle

```groovy
rootProject.name = 'context-cache-observer'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    // One worker JVM to make cache reuse directly observable.
    maxParallelForks = 1
    forkEvery = 0
}
```

Ở đây chỉ có **một Gradle test worker process**. Khi muốn tìm hiểu forks, thay `maxParallelForks` hoặc `forkEvery` trong branch sandbox rồi so process-level logs; không tự bật nhiều forks trong một test muốn assert sharing cùng JVM.

### 9.4. Test logging: src/test/resources/application.properties

```properties
spring.main.banner-mode=off
logging.level.org.springframework.test.context.cache=DEBUG
```

Đây là test-only logging config. Nếu môi trường/IDE không thấy cache debug, kiểm tra logger configuration của test runtime hoặc file `logback-test.xml`/Gradle logging system; không kết luận Spring cache không hoạt động chỉ vì console lọc DEBUG.

## 10. ContextCacheProbeApplication.java

**src/main/java/example/contextcache/ContextCacheProbeApplication.java**

```java
package example.contextcache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ContextCacheProbeApplication {

    private static final AtomicInteger MARKER_CREATIONS =
            new AtomicInteger();

    public static void main(String[] args) {
        SpringApplication.run(
                ContextCacheProbeApplication.class, args);
    }

    @Bean
    public ContextMarker contextMarker() {
        return new ContextMarker(
                MARKER_CREATIONS.incrementAndGet());
    }

    public static int markerCreations() {
        return MARKER_CREATIONS.get();
    }

    public record ContextMarker(int sequence) {}
}
```

### 10.1. Marker được tạo khi nào?

`@Bean` mặc định tạo singleton không lazy. Trong ứng dụng demo, mỗi lần một ApplicationContext mới refresh và instantiate bean, method `contextMarker()` gọi `incrementAndGet()` một lần.

Khi test B dùng lại chính context của test A, bean đã nằm trong context A, Spring không tạo lại bean và counter không tăng. Khi context bị dirty/evict rồi load lại, sẽ có ContextMarker mới với sequence tiếp theo.

### 10.2. Marker là công cụ chẩn đoán, không phải public business API

`MARKER_CREATIONS` static được dùng có chủ đích để đếm **các instances trong một JVM**. Thực tế nhiều test contexts có thể không chứa marker hoặc load fail. Trong production, không lưu mutable user data trong static fields để tự đánh giá context reuse.

## 11. ContextCacheBehaviorTest.java — 5 JUnit tests

**src/test/java/example/contextcache/ContextCacheBehaviorTest.java**

```java
package example.contextcache;

import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext.HierarchyMode;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestContextManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Execution(ExecutionMode.SAME_THREAD)
class ContextCacheBehaviorTest {

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    static class SharedA {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    static class SharedB {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=different"
    )
    static class DifferentProperty {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    @ActiveProfiles("scenario")
    static class DifferentProfile {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=dirty-demo"
    )
    static class DirtyFixture {}

    private static TestContextManager manager(
            Class<?> fixtureClass) {
        return new TestContextManager(fixtureClass);
    }

    private static ApplicationContext contextFor(
            Class<?> fixtureClass) {
        return manager(fixtureClass)
                .getTestContext()
                .getApplicationContext();
    }

    private static int markerOf(ApplicationContext ctx) {
        return ctx.getBean(
                ContextCacheProbeApplication.ContextMarker.class)
                .sequence();
    }

    @Test
    void equivalentFixtureKeysReuseSameContext() {
        ApplicationContext first = contextFor(SharedA.class);
        int markersAfterFirst =
                ContextCacheProbeApplication.markerCreations();

        ApplicationContext second = contextFor(SharedB.class);

        assertSame(first, second);
        assertEquals(markerOf(first), markerOf(second));

        assertEquals(
                markersAfterFirst,
                ContextCacheProbeApplication.markerCreations());
    }

    @Test
    void repeatedLookupDoesNotRecreateBeanGraph() {
        ApplicationContext first = contextFor(SharedA.class);
        int beforeRepeats =
                ContextCacheProbeApplication.markerCreations();

        ApplicationContext second = contextFor(SharedA.class);
        ApplicationContext third = contextFor(SharedA.class);

        assertSame(first, second);
        assertSame(first, third);
        assertEquals(
                beforeRepeats,
                ContextCacheProbeApplication.markerCreations());
    }

    @Test
    void changingInlinePropertyCreatesDifferentContext() {
        ApplicationContext shared = contextFor(SharedA.class);
        ApplicationContext other =
                contextFor(DifferentProperty.class);

        assertNotSame(shared, other);
        assertNotEquals(markerOf(shared), markerOf(other));

        assertEquals(
                "shared",
                shared.getEnvironment()
                        .getProperty("cache.study.variant"));
        assertEquals(
                "different",
                other.getEnvironment()
                        .getProperty("cache.study.variant"));
    }

    @Test
    void activeProfileContributesToCacheKey() {
        ApplicationContext base = contextFor(SharedA.class);
        ApplicationContext profiled =
                contextFor(DifferentProfile.class);

        assertNotSame(base, profiled);
        assertNotEquals(markerOf(base), markerOf(profiled));
        assertTrue(
                Arrays.asList(
                        profiled.getEnvironment()
                                .getActiveProfiles())
                        .contains("scenario"));
    }

    @Test
    void dirtyContextIsRemovedAndNextLookupReloads() {
        TestContextManager firstManager =
                manager(DirtyFixture.class);

        ApplicationContext oldContext =
                firstManager.getTestContext()
                        .getApplicationContext();

        int oldMarker = markerOf(oldContext);
        int createdAfterOld =
                ContextCacheProbeApplication.markerCreations();

        firstManager.getTestContext()
                .markApplicationContextDirty(
                        HierarchyMode.EXHAUSTIVE);

        ApplicationContext newContext =
                contextFor(DirtyFixture.class);

        assertNotSame(oldContext, newContext);
        assertNotEquals(oldMarker, markerOf(newContext));

        assertEquals(
                createdAfterOld + 1,
                ContextCacheProbeApplication.markerCreations());
    }
}
```

**5 JUnit methods** trong một class, với các nested classes làm **fixture cache keys**, không phải năm JUnit test classes độc lập. `TestContextManager` public API được dùng để dựng `TestContext` với bootstrap metadata của `@SpringBootTest` rồi gọi `getApplicationContext()`; đây là một phép thử instrumentation của cache. Ở ứng dụng thật, JUnit Jupiter + SpringExtension thường quản lý TestContextManager tự động.

### 11.1. Cùng key ở hai fixture classes

`SharedA` và `SharedB` có cùng app, web environment, inline property và không có customizers khác. Test assert:

- `assertSame(first,second)`: **cùng Java ApplicationContext object**.
- `markerOf(first)==markerOf(second)`: cùng singleton marker.
- Marker creation total không đổi sau lookup SharedB: **không dựng bean graph mới**.

Tên fixture class khác không làm thay đổi key khi merged configuration tương đương.

### 11.2. Repeated lookups có thể làm hitCount tăng nhưng marker không tăng

Trong `repeatedLookupDoesNotRecreateBeanGraph`, ta truy cập cùng fixture key ba lần. Mỗi lookup sau có thể được ghi vào hit stats, nhưng vẫn là một context instance. Test không assert “hitCount tăng đúng 2” vì Spring có thể làm các accesses bổ sung trong bootstrap; object identity là bằng chứng bền hơn.

### 11.3. Khác property làm identity khác

`DifferentProperty` có `cache.study.variant=different`, nên context key khác SharedA. Nó phải tạo/giữ context riêng và marker sequence khác. Test còn query `Environment` để đảm bảo property thực sự được áp dụng, thay vì chỉ suy đoán từ annotation.

### 11.4. Active profile cũng làm cache key khác

`DifferentProfile` dùng cùng inline property với SharedA nhưng có `@ActiveProfiles("scenario")`. Profile khác góp phần tạo merged key khác. Vì vậy một suite có nhiều lớp bật profiles khác nhau có thể sinh nhiều contexts.

### 11.5. Controlled @DirtiesContext behavior

Trong `dirtyContextIsRemovedAndNextLookupReloads`:

1. Load context key `DirtyFixture`, ghi marker id và counter.
2. Gọi `TestContext.markApplicationContextDirty(HierarchyMode.EXHAUSTIVE)` cho chính context đó.
3. Spring remove/close context khỏi TestContext cache.
4. Load lại cùng key, nhận **context object khác** và **marker id khác**.
5. Trong project chỉ một test class/chạy tuần tự, counter tăng một.

Dùng method public của TestContext là cách viết một **diagnostic test có chủ đích** để minh họa eviction; code ứng dụng thông thường nên dùng `@DirtiesContext` annotation nếu cần mark dirty, không gọi method này trong từng test để “lấy context mới” vô điều kiện.

### 11.6. Test không phụ thuộc thứ tự JUnit methods

Mỗi `@Test` assert identity trực tiếp tại thời điểm gọi fixture, không giả định test trước đã load hay chưa. Riêng dirty fixture dùng một cache key độc lập nên không xóa context của SharedA/DifferentProperty. `@Execution(SAME_THREAD)` cùng Gradle one-worker setup tránh parallel modifications trong lab.

**Giới hạn:** Nếu chạy suite khác trong **cùng JVM và đồng thời** cũng load contexts có marker, global marker counter có thể tăng thêm ngoài riêng dirty test. Bộ lab chỉ có một test class; trong suite thật không assert absolute global totals khi parallel, mà dùng per-key marker identities/isolated suite.

## 12. Chạy project và đọc đúng kết quả

JDK 17, Gradle wrapper tương thích (ví dụ Gradle 8.7), Maven Central/repository cache:

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.contextcache.ContextCacheBehaviorTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.contextcache.ContextCacheBehaviorTest
```

Nếu chưa có wrapper, tạo bằng Gradle phù hợp và lưu wrapper files. Không tự tạo stdout “BUILD SUCCESSFUL” nếu chưa chạy.

| Test | Dự kiến |
| --- | --- |
| `equivalentFixtureKeysReuseSameContext` | Cùng object context và marker |
| `repeatedLookupDoesNotRecreateBeanGraph` | Repeated lookup không tạo marker |
| `changingInlinePropertyCreatesDifferentContext` | Context khác, property khác |
| `activeProfileContributesToCacheKey` | Context khác khi bật profile |
| `dirtyContextIsRemovedAndNextLookupReloads` | Dirty -> context mới, marker tăng |

**Kết quả kỳ vọng:** 5 JUnit methods pass trên Boot 3.3 + Spring 6.1 nếu code được đặt đúng package/file và không có suite khác cạnh tranh cùng marker. Đây không phải phép đo Gradle thực đã chạy. Các con số `hitCount`/`missCount`/`size` thực phải xem DEBUG log của lần chạy, vì framework có thể access cache nhiều hơn một lần cho mỗi method.

### 12.1. Có thể tính “5 contexts” không?

Các fixture keys của demo về mặt cấu hình có thể gồm shared, different-property, different-profile và dirty-demo. Key dirty có thể được load hai lần. Về mặt khái niệm, khi chạy một JVM sạch, không ai khác load chúng, chúng tạo **5 context instances**: shared 1, different-property 1, different-profile 1, dirty-demo 2.

Tuy nhiên đây chỉ là **mô hình expected của chương trình độc lập**, không phải lời hứa rằng DEBUG `missCount` cuối sẽ bằng 5 hoặc JUnit đã thực thi đủ 5. Hơn nữa, test discovery, context loading order và launcher configuration có thể thay đổi khi mở rộng suite.

### 12.2. Nếu bạn thấy cùng config nhưng vẫn miss

Kiểm tra đúng version, equality của full merged context configuration, context eviction, `@DirtiesContext`, TestContext static cache có cùng JVM không, và liệu Spring Boot mock definitions/profile/customizers có khác. Không mặc định đó là bug Spring TestContext.

## 13. TestContextManager là gì và tại sao dùng?

`TestContextManager` là entry point của Spring TestContext Framework, chịu trách nhiệm quản lý `TestContext` và gọi các registered `TestExecutionListener` ở những lifecycle callbacks.

Trong JUnit 5 dùng `@SpringBootTest`, SpringExtension tích hợp sẵn TestContextManager. Trong bài lab, chúng ta tạo thủ công:

```java
TestContextManager manager =
        new TestContextManager(SharedA.class);

ApplicationContext ctx =
        manager.getTestContext()
                .getApplicationContext();
```

Lý do: muốn kiểm tra **nhiều cache keys và identity của các contexts trong cùng một test method**, thay vì dựa vào thứ tự JUnit chạy test classes hoặc shared static maps phải thu thập dữ liệu qua nhiều tests.

**Không dùng pattern này để bypass test lifecycle trong product test suite.** Phép thử này cố ý chỉ yêu cầu context loading/cache semantics, không yêu cầu prepareTestInstance/beforeTestMethod/afterTestMethod của từng fixture. Nếu fixture có transactional test lifecycle, dependency injection vào test instance, TestExecutionListeners đặc biệt hoặc dirty annotations, hãy dùng SpringExtension/JUnit integration thực và đo đúng boundary đó.

## 14. @DirtiesContext: lúc nào cần, lúc nào không?

`@DirtiesContext` cho Spring TestContext biết một context không còn an toàn để reuse, ví dụ test đã sửa bean definition hoặc shared singleton state khó reset, và muốn Spring close/remove entry.

Ví dụ minh họa:

```java
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalConfigurationTest {
    @Test
    void modifiesSingletonConfiguration() {
        // Test changes something that cannot be safely reset.
    }
}
```

Snippet này cần imports và app context phù hợp; nó **không** là class nằm trong runnable lab. Annotation có method/class modes như `BEFORE_METHOD`, `AFTER_METHOD`, `BEFORE_CLASS`, `AFTER_CLASS`.

### 14.1. @DirtiesContext có giá thật

Mark dirty khiến context bị close/removed. Test tiếp theo cùng key phải startup lại, có thể mở lại DB pool/embedded server, rerun bean initialization. Nếu mark dirty sau mọi method trong một suite lớn, caching gần như mất tác dụng.

**Không dùng @DirtiesContext như một cách reset database state mặc định.** Nếu chỉ sửa vài rows, dùng cleanup/truncate/transaction rollback/test fixture. Chỉ dirty context khi bản thân context/bean graph đã bị hỏng và không thể reset an toàn.

### 14.2. Transaction rollback khác context reset

`@Transactional` test với rollback có thể reset database modifications trong test-managed transaction. Nó **không** recreate ApplicationContext, không reset mọi external resources/Redis/queues, và không undo side effects nằm ngoài transaction.

Ngược lại, `@DirtiesContext` recreate bean graph nhưng không tự xóa dữ liệu của external database/Redis đã tồn tại. Chọn đúng công cụ cho đúng state.

### 14.3. @ContextHierarchy

Khi có parent/child contexts, dirty hierarchy modes có thể ảnh hưởng parent/sibling children. `HierarchyMode.EXHAUSTIVE` có phạm vi rộng; `CURRENT_LEVEL` giới hạn level hiện tại theo contract. Bài lab chỉ có một standalone context mỗi key, nên không phải xử lý hierarchy interactions.

## 15. Đếm số context thực sự được tạo trong project lớn

Không có một số duy nhất có thể đo mọi tình huống chỉ bằng việc nhìn số tests. Sử dụng ba nguồn chứng cứ:

### 15.1. Cache DEBUG stats

Để thấy:

- `size`: số entries hiện ở cache.
- `maxSize`: capacity.
- `hitCount`/`missCount`: access counters.
- `failureCount`: context load failures nếu có.

Nguồn chính thức là `org.springframework.test.context.cache` DEBUG. **Không phải per-test metric** và không thể dùng trực tiếp để biết số **successful unique instances created** trong mọi tình huống.

### 15.2. Bean/context marker

Thêm test-only bean marker vào các configurations cần đo và ghi số lần factory được gọi. Khi context reuse, marker ID không đổi. Khi context reload, marker ID đổi.

Trong suite lớn, có thể ghi log test-only:

```text
[context-probe] created marker=1 config=alpha
[context-probe] created marker=2 config=beta
[context-probe] created marker=3 config=dirty
[context-probe] created marker=4 config=dirty(reloaded)
```

Đây là **minh họa** để diễn giải identity; runnable lab không in log có format trên, mà assert markers qua Java.

### 15.3. Startup log và profiler

Mốc “Started Application in X seconds” hoặc Boot startup metrics có thể giúp biết quá trình bootstrap một context, nhưng:

- Bản log có thể không hiển thị nếu config log level khác.
- Có thể có nhiều `SpringApplication.run` ngoài TestContext.
- Không nhất thiết có một dòng duy nhất cho từng context child/hierarchy.
- Startup time phụ thuộc máy/CI, warmup và file/network IO.
- Một app dùng `SpringApplication.run` thủ công **không** hưởng TestContext cache nếu không qua TestContext loader.

Dùng timings để đo **hiệu năng thực**, marker identity để đo **số instances**, cache DEBUG để xem **lookup behavior**.

## 16. Quan sát cache keys mà không phụ thuộc internals

Bạn có thể dùng logging/test annotations để điều tra sự khác biệt, nhưng tránh reflection vào `DefaultContextCache` static fields hay thao tác `clearStatistics()` toàn suite trong product tests.

Một bảng mapping hữu ích:

| Test class | Test annotation | Profiles | Properties | Mocks | Context group |
| --- | --- | --- | --- | --- | --- |
| OrderServiceTest | @SpringBootTest | test | mode=local | PaymentClient | Full-A |
| InvoiceServiceTest | @SpringBootTest | test | mode=local | PaymentClient | Full-A |
| CheckoutWebTest | @WebMvcTest | test | khác | PaymentClient | Web-B |
| JsonSerializationTest | @JsonTest | test | khác | Không | Json-C |
| OrderJpaTest | @DataJpaTest | test | datasource H2 | Không | Data-D |

Đây là bảng phân loại ví dụ. Nhóm “Full-A” là ứng viên reuse khi **mọi thành phần key liên quan** tương đồng; không được quyết định chỉ từ 5 columns tổng quát nếu có customizers/parent/initializers ẩn.

### 16.1. Không dùng contextCache internals làm public test assertion

`DefaultCacheAwareContextLoaderDelegate`/`DefaultContextCache` có các API/implementation details không được khuyến khích làm contract của product code. Test đọc trực tiếp internal counters có thể hỏng khi nâng Framework. Dùng DEBUG stats để đo, `assertSame` để xác minh identity và marker test-only để xác minh khởi tạo.

### 16.2. Cache hit có thật sự cải thiện startup?

Về lý thuyết có: tránh refresh bean graph. Nhưng muốn định lượng tốc độ cần đo actual test run time/startup profile cùng workload/environment. Không suy ra “cache hit=1000 ⇒ nhanh hơn 1000 giây”. Context size và startup cost của từng key rất khác nhau.

## 17. Spring Boot test slices và tốc độ

Các slices giúp giảm bootstrap scope:

- `@WebMvcTest`: MVC controller/web slice, thường cần mock dependencies.
- `@WebFluxTest`: reactive controller slice.
- `@DataJpaTest`: JPA persistence slice, thường rollback transactions.
- `@JdbcTest`: JDBC slice.
- `@JsonTest`: JSON serialization slice.
- `@RestClientTest`: REST client slice.

Một context slice thường rẻ hơn full application vì ít beans/auto-configurations. Tuy nhiên nếu mỗi test class dùng một tập khác nhau của controllers, mocks/imports, nó vẫn có nhiều cache keys.

### 17.1. Đừng trộn nhiều slices tùy tiện

Spring Boot không hỗ trợ combine nhiều `@...Test` slices như thể cộng hai slices tạo một context rõ ràng. Nếu cần full integration, dùng `@SpringBootTest`; nếu cần một slice với extra configuration, dùng `@Import` hoặc auto-config imports có chủ đích.

### 17.2. Không giảm context count bằng cách làm tests sai phạm vi

Gộp tất cả classes vào cùng một @SpringBootTest rồi mock mọi service có thể tăng reuse nhưng mất isolation và tăng startup footprint. Cân bằng giữa tốc độ và fidelity; cache optimization không được phá mục tiêu kiểm chứng security/persistence/serialization.

### 17.3. @MockBean reset per method không đồng nghĩa context mới

Boot 3.3 test mocks thường được reset sau test method bởi test framework; việc gọi `reset()` không tự làm context cache key khác. Nhưng **định nghĩa tập mock beans** khác giữa test classes sẽ thay đổi context customizer, có thể tạo context key khác.

### 17.4. TestConfiguration khác nhau

Một nested `@TestConfiguration` bổ sung bean riêng, `@Import` khác, các `@AutoConfigure...` flags khác có thể khiến context customizers/configurations khác. Khi muốn reuse, chuẩn hóa test configs một cách có chủ đích nhưng vẫn giữ test semantics cần thiết.

## 18. Testcontainers và cache context lifecycle

Một nguồn lỗi khó chịu:

```text
Test class A starts RedisContainer A at mapped port 32768
Spring context A creates Lettuce client to port 32768
Class A ends; Testcontainers JUnit stops container A
Spring context A stays in static TestContext cache

Test class B with same key begins
Spring reuses context A
Redis client still points at 32768, but container A is stopped
Test B fails with connection refused
```

Đây là ví dụ về **external resource lifetime** không khớp context lifetime. Dynamic property method identity/return values có thể làm cache reuse khó nhận ra.

Chiến lược:

1. Dùng container lifecycle gắn với Spring ApplicationContext khi hỗ trợ.
2. Hoặc dùng singleton container sống suốt JVM/suite khi muốn reuse contexts.
3. Hoặc tạo per-class contexts khác có chủ đích và đảm bảo không reuse context trỏ resource đã stop.
4. Không dùng shared container mà teardown class A đóng nó khi context vẫn cached.
5. Không dựa `@DirtiesContext` để xóa database/Redis data ngoài container.
6. Không hardcode container mapped port; dùng Spring Boot `@ServiceConnection` hoặc dynamic properties đúng lifecycle.

**Điểm đánh đổi:** tái sử dụng context giúp nhanh nhưng kéo theo lifecycle của datasource/containers. Đừng chỉ tăng cache.maxSize nếu điều đó giữ những clients tới resources đã chết.

## 19. Process boundaries: Gradle, Maven, IDE và CI

Một suite có 100 classes cùng key vẫn có thể thấy 8 context startups nếu build chia thành 8 JVMs. Đây không phải một cache miss trong một JVM mà là **8 caches độc lập**.

### 19.1. Gradle

`maxParallelForks` quy định số worker processes chạy tests song song. `forkEvery` giới hạn số classes tối đa xử lý bởi một worker trước khi fork mới. Nếu bạn muốn test context reuse across classes, kiểm tra rằng chúng thực sự chạy trong cùng fork.

### 19.2. Maven

Surefire/Failsafe `forkCount`, `reuseForks` và parallel settings có thể ảnh hưởng context reuse. `forkCount=0` có ngữ nghĩa chạy in-process theo plugin/version và tác động isolation, không phải thay đổi nên thực hiện mù quáng chỉ để tối ưu.

### 19.3. IDE

Chạy riêng A và B bằng hai Run Configurations có thể là hai JVMs; bạn sẽ thấy cả hai startup dù chung merged key. Muốn quan sát reuse, chạy cùng suite trong một test process.

### 19.4. CI matrix/shards

Từng shard/CI agent/container có JVM riêng. Cộng tổng metrics startup giữa shards nhưng **không** kỳ vọng chia sẻ context cache cross-shard. Khi tính hiệu năng end-to-end, dùng wall-clock pipeline time và resource cost, không chỉ số unique contexts trong một process.

## 20. LRU eviction, heap usage và context leak

Khi `maxSize`=32 và suite có >32 distinct keys, Spring có thể close LRU context. Nếu test giữ static reference tới một bean/context đã evict, reference đó có thể trở thành stale hoặc giữ tài nguyên khiến GC không thu gom được.

### 20.1. Không giữ injected beans vào static fields

Một JUnit test class có field:

```java
static ApplicationContext retainedContext;
```

đây là anti-pattern nếu không có ownership. Spring có thể evict/close context nhưng static reference vẫn còn; singleton resources có thể không hoạt động đúng và memory không được giải phóng như mong đợi.

### 20.2. Cache eviction không reset external database

Evict/close Spring context thường dừng beans/resources thuộc context, nhưng **không mặc định xóa dữ liệu external PostgreSQL/Redis/Kafka**. Một context mới vẫn có thể đọc state cũ. Lỗi test data isolation và lỗi context reuse là hai vấn đề khác nhau.

### 20.3. Thay đổi max size không chữa root cause

Nếu 300 keys được tạo bởi 300 tập mock beans/phụ thuộc properties khác nhau, tăng cache lên 300 có thể giữ quá nhiều contexts và gây OOM. Tốt hơn là chuẩn hóa configurations, reuse common test slices, bỏ khác biệt không cần thiết và đo cost trước.

## 21. @DirtiesContext và singleton mutable state

Một singleton test fixture có counter trạng thái:

```java
@Component
class CountingStore {
    private int count;

    void add() { count++; }
    int value() { return count; }
}
```

Nếu two tests reuse context, giá trị `count` từ test A có thể còn khi test B bắt đầu. Đó là rò state, **không phải Spring cache bug**. Giải pháp:

- Reset state trong `@BeforeEach`/`@AfterEach` nếu an toàn.
- Dùng test transaction rollback để cô lập DB state khi đúng boundary.
- Dùng fresh test data IDs và cleanup resource thuộc mỗi test.
- Tách state thành per-request/per-test scope nếu phù hợp.
- Chỉ `@DirtiesContext` nếu singleton/bean graph đã bị thay đổi không thể phục hồi.

**Không tắt caching toàn bộ** chỉ vì một test đang không reset state; hãy sửa isolation đúng tầng.

## 22. Chiến lược phân tích một test suite chậm

### Bước 1. Thu thập baseline

Chạy cùng workload, JVM, test worker settings, test ordering và CI machine category. Ghi:

- Tổng số tests/methods thực thi và skipped.
- Test task wall time.
- Số worker JVM processes.
- Tổng số context start events hoặc marker creations.
- Cache DEBUG snapshots: size, hit, miss, max size.
- Các dependencies tốn thời gian: DB migrations, Testcontainers, embedded server, Spring Security/ORM.
- Heap/memory và GC metrics nếu gặp pressure.

### Bước 2. Tìm cache-key fragmentation

Chia groups theo `@SpringBootTest` vs slice, profiles, inline properties, `@TestPropertySource`, mocks/customizers. Tìm classes gần như giống nhau nhưng khác một property/mock không cần thiết.

### Bước 3. Phân biệt misses do configuration và eviction

Nếu số unique keys nhỏ và current size ổn, misses chủ yếu có thể là load ban đầu. Nếu distinct keys vượt maxSize và contexts bị reload, LRU churn có thể tăng overhead. Nếu tests đánh dấu dirty thường xuyên, misses dù keys không đổi.

### Bước 4. Kiểm tra JVM boundaries

Nếu classes giống nhau chạy ở nhiều forks/shards, static cache không chia sẻ được. Thay đổi fork settings có thể giảm startups nhưng cũng làm giảm song song hoặc tăng time-to-completion. So sánh **pipeline wall time** chứ không chỉ context count.

### Bước 5. Thử một tối ưu tại một thời điểm

Ví dụ loại một `@MockBean` khác không cần thiết, chuẩn hóa inline properties, gom common TestConfiguration hoặc bỏ `@DirtiesContext` nơi có thể reset state. Chạy lại cùng workload và đo.

### Bước 6. Kiểm tra correctness không giảm

Sau tối ưu, vẫn phải có negative/positive tests và không để tests phụ thuộc state nhau. Một suite nhanh nhưng bị test pollution là kết quả không thể chấp nhận.

## 23. Cache hit rate có ý nghĩa thế nào?

Nếu chỉ xét lookup counters và không có ảnh hưởng failure/reload phức tạp, có thể định nghĩa:

\[
\text{Lookup hit ratio} =
\frac{\text{hitCount}}
{\text{hitCount}+\text{missCount}}
\]

Ví dụ hypothetical hit=90, miss=10 → hit ratio 90%. Nhưng đây là **tỷ lệ trên cache lookup attempts**, không phải tỷ lệ JUnit methods không phải bootstrap. Hơn nữa, context startup cost có thể dao động rất lớn giữa keys, nên hit ratio 99% không bảo đảm suite nhanh.

Một single miss tạo context 20 giây có thể đắt hơn nhiều hits cho một context mất 100ms. Để tối ưu, đo **miss cost weighted by context startup time** khi có data.

### 23.1. Snapshot khác delta

DEBUG log có thể xuất:

```text
size = 8, hitCount = 300, missCount = 12
size = 8, hitCount = 320, missCount = 12
```

Chênh lệch trong khoảng là +20 hits, +0 misses, không phải “620 hits”. Đừng cộng hai snapshots cumulative.

### 23.2. Failure threshold 6.1

Từ Spring Framework 6.1, default context failure threshold là **1** cho mỗi cache key; sau lần load thất bại đầu, những attempts tiếp theo có thể fail-fast thay vì boot lại vô hạn. Có thể tùy chỉnh JVM property `spring.test.context.failure.threshold` để chẩn đoán khi cần.

Điều này khác `spring.test.context.cache.maxSize` và khác JUnit retry behavior. Đừng khuyến nghị tăng failure threshold trong mọi CI: làm vậy có thể khiến suite lặp boot lỗi và chạy chậm hơn mà không tăng chất lượng chẩn đoán.

## 24. Ví dụ đọc log trong đời thực

Giả sử test suite A có logs giả định:

```text
T0  size=0 maxSize=32 hits=0 misses=0
T1  size=1 maxSize=32 hits=0 misses=1
T2  size=1 maxSize=32 hits=7 misses=1
T3  size=2 maxSize=32 hits=7 misses=2
T4  size=2 maxSize=32 hits=19 misses=2
```

Có thể diễn giải:

- T0→T1: một lookup miss và cache giữ một context.
- T1→T2: bảy cache hits, không tăng size.
- T2→T3: một lookup miss nữa và size thành hai.
- T3→T4: 12 hits, không thêm miss.

**Không thể kết luận** đã có đúng 19 JUnit tests hoặc 19 lần gọi service. Đây là ví dụ **logic thống kê**, không phải log thực của một IDE/Gradle run.

Nếu T5 size về 1, có thể có eviction, dirtying, context close hoặc hierarchy behavior; đọc nhiều thông tin hơn chứ không suy ra một nguyên nhân duy nhất.

## 25. Khi nên thêm context marker ở test configuration riêng?

Nếu không muốn một marker bean nằm trong main app class, tạo `@TestConfiguration` và chỉ import ở các test classes cần đo:

```java
@TestConfiguration(proxyBeanMethods = false)
public class CacheProbeConfig {
    private static final AtomicInteger CREATED =
            new AtomicInteger();

    @Bean
    ContextMarker marker() {
        return new ContextMarker(
                CREATED.incrementAndGet());
    }
}
```

Đây là snippet minh họa, cần record `ContextMarker`, imports và test config; không thuộc runnable project chính. Khi thêm `@Import(CacheProbeConfig.class)` vào tests, chính việc import cũng tham gia cấu hình/cache key. Nếu chỉ một số tests import marker còn số khác không, counter không phản ánh tất cả contexts.

### 25.1. Không đưa marker vào mỗi test với khác class riêng

Nếu mỗi test class tự tạo một nested @TestConfiguration khác, chúng có thể **tự khiến cache key khác** và làm measurement sai. Dùng một shared test configuration class nếu muốn đo reuse mà không làm phân mảnh cấu hình.

### 25.2. Count lần tạo, không count mỗi lần access

Marker không cần giữ singleton mutable business state; bean có sequence fixed. Test chỉ đọc ID. Một static AtomicInteger increment trong bean factory là phép đo số lần bean factory method thực sự chạy, không tự trùng số test method.

## 26. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xác minh |
| --- | --- | --- |
| Every test class prints Starting... | Different cache keys, forks, dirtying | DEBUG cache stats + JVM settings |
| HitCount cao nhưng task vẫn chậm | Một ít miss rất đắt, DB/IO mỗi test | Startup time/profile |
| MissCount cao hơn unique configurations | LRU eviction, dirtying, failed loads | Logs over time, marker IDs |
| Size=32 nhưng đã tạo >32 contexts | Max cache bounded, LRU churn | Marker, maxSize, key grouping |
| Size=1 nhưng bean được tạo nhiều lần | Context dirty/reload hoặc forks | Static per-process marker |
| Same @SpringBootTest nhưng contexts khác | @MockBean/@SpyBean/customizers/profiles | Merged config differences |
| @DynamicPropertySource giống nhưng resource chết | Container lifecycle khác context lifecycle | Container start/stop logs |
| Tests dùng chung context nhưng data rò | Singleton/DB/cache không reset | @BeforeEach cleanup |
| @DirtiesContext làm suite rất chậm | Context startup lặp | Inspect dirty annotations |
| Cache stats không hiện | DEBUG logging chưa áp dụng đúng | logback-test/Boot logging |
| Count marker không tăng khi context fail | Bean chưa tạo trước failure | Failure logs/threshold |
| Count marker tăng dù same key | Key đã evict/dirty hoặc another JVM | Cache logs and process identity |
| Test run by IDE khác Gradle | Different process/fork/logger | Compare launch configuration |
| JVM OOM sau nâng maxSize | Too many pools/beans retained | Heap, threads, process memory |
| @WebMvcTest chậm hơn dự tính | Custom imports/mocks/slice scope | Compare actual context startup |
| Test count=500, miss=10 | Normal: multiple tests share context | Do not equate lookup count to tests |
| Misread hit/miss snapshots | Cumulative counters cộng sai | Compute deltas |
| Context cache clear làm DB vẫn còn | External data not reset | Cleanup provider data separately |
| Run with @DirtiesContext appears correct | Hides shared state pollution | Prefer explicit fixture cleanup |
| Parallel suite unpredictable marker count | Global static counter across concurrent contexts | Run diagnostic suite isolated |
| @ContextHierarchy changes counts | Parent and child contexts share/evict differently | Hierarchy mode, parentCount |

## 27. Bài tập thực hành

1. **Cùng key:** Chạy `equivalentFixtureKeysReuseSameContext`, xác minh SharedA/SharedB cùng context object.
2. **Repeated lookup:** Tăng số lần gọi `contextFor(SharedA.class)` từ 3 lên 10; marker count không tăng sau lần đầu.
3. **Property value:** Đổi `cache.study.variant=different` thành `shared` trong DifferentProperty; trước khi đổi expected, kiểm tra identity/key equality và giải thích điều gì thay đổi.
4. **Profile:** Bỏ `@ActiveProfiles("scenario")` rồi xem cache key có còn khác không.
5. **DirtiesContext:** Dùng fixture Dirty; gọi mark dirty rồi load lại, assert context khác và marker tăng.
6. **Đếm contexts:** Trong một JVM sạch, so marker sequence giữa SharedA, DifferentProperty, DifferentProfile, Dirty before/after; không dùng tổng tests làm proxy.
7. **Đọc stats:** Bật DEBUG và ghi cuối run hit/miss/size; không tự bịa số.
8. **Max size:** Thử `-Dspring.test.context.cache.maxSize=2` trong một branch sandbox, quan sát LRU eviction/reload khi load nhiều keys. Đảm bảo test assertions không dựa số context startup cố định nếu order thay đổi.
9. **Fork:** Đổi Gradle `maxParallelForks=2` khi có nhiều classes, phân biệt static per-JVM context caches.
10. **Mock customization:** Tạo hai test classes khác `@MockBean` definitions (Boot 3.3), quan sát separate contexts.
11. **Common test config:** Dùng cùng một test configuration class thay vì mỗi class một config khác, so startup cost.
12. **Dirties vs cleanup:** Tạo singleton counter fixture, so @BeforeEach reset với @DirtiesContext(AFTER_METHOD); đo startup overhead và correctness.
13. **Testcontainers:** Tạo shared Redis container được giữ lâu bằng context lifecycle, rồi đo cache hits; tránh stale connection do class teardown.
14. **Different slices:** So `@JsonTest` với full `@SpringBootTest` về bootstrap beans/time mà không nhầm scopes.
15. **Debug snapshot:** Từ ba log cumulative, tính delta hits/misses giữa timestamps đúng cách.
16. **Failure threshold:** Chủ động tạo broken bean config trong isolated test, quan sát Spring 6.1 fail-fast; không chỉnh global CI chỉ để bỏ lỗi.
17. **One-key-many-tests:** Tạo 10 JUnit methods cùng @SpringBootTest config; xem có một context reused và nhiều cache lookups.
18. **CI shards:** Chạy same tests ở hai workers/shards, giải thích vì sao mỗi process lại có một initial miss.
19. **Marker limitations:** Một context không import marker sẽ không tăng counter; giải thích vì sao marker count không đại diện mọi contexts.
20. **Memory cost:** Tăng cache.maxSize và theo dõi heap, Hikari pools và process threads; đo trade-off, không tăng mù quáng.

## 28. Checklist QA trước khi tối ưu

- [ ] Phân biệt TestContext cache với business @Cacheable/Redis cache.
- [ ] Đã dùng đúng Spring Boot/Spring Framework versions.
- [ ] Hiểu cache key là merged configuration, không chỉ test class name.
- [ ] Đã xét @ActiveProfiles, @TestPropertySource, inline properties.
- [ ] Đã xét @MockBean/@SpyBean và các context customizers.
- [ ] @DynamicPropertySource method/lifecycle không làm reuse stale clients.
- [ ] Đã bật DEBUG cho org.springframework.test.context.cache khi phân tích.
- [ ] HitCount được hiểu là lookup hits, không là number of test methods.
- [ ] MissCount được hiểu là missing-cache-key accesses, không chắc unique instances.
- [ ] Size là current cache entries, không phải historical total.
- [ ] MaxSize mặc định 32 và LRU eviction được hiểu đúng.
- [ ] Failure threshold 6.1 được phân biệt với misses/evictions.
- [ ] Đã ghi process/fork settings; cache static chỉ chia sẻ trong một JVM.
- [ ] Marker counter chỉ đếm contexts có marker bean và đã instantiate.
- [ ] Tests so ApplicationContext object identity bằng assertSame/assertNotSame.
- [ ] Không assert context.getId() luôn unique khi reload.
- [ ] Đã thử một key đổi property và một key đổi profile.
- [ ] @DirtiesContext chỉ dùng khi state context không thể reset.
- [ ] DB/Redis/queue data được cleanup riêng, không trông cậy context close.
- [ ] Không giữ ApplicationContext/beans static làm rò resource sau eviction.
- [ ] Không khai thác private ContextCache internals/reflection để viết product tests.
- [ ] Không lấy nhiều cumulative snapshots rồi cộng chúng như deltas.
- [ ] Không hardcode startup milliseconds không kiểm soát được.
- [ ] Test slices/full context được lựa chọn theo phạm vi kiểm thử.
- [ ] Không đánh đổi correctness lấy tốc độ vô điều kiện.
- [ ] Khi parallel, marker global và reuse assertions có isolation phù hợp.
- [ ] Khi báo performance, có executed/skipped counts, wall time, process count thật.
- [ ] Nếu chưa chạy Gradle, kết quả chỉ được ghi là expected/not executed.

## 29. Quy tắc chẩn đoán nhanh

```text
Có nhiều "Starting Application" lines?
      |
      +-- Test classes thật sự ở cùng JVM?
      |      -> Xem Gradle/Maven forks, CI sharding.
      |
      +-- MergedContextConfiguration giống nhau?
      |      -> Profiles, properties, mocks, test imports,
      |         dynamic properties, context customizers.
      |
      +-- @DirtiesContext đang evict?
      |      -> Chỉ dùng khi không thể reset state đúng tầng.
      |
      +-- Số unique keys > maxSize?
      |      -> LRU churn, có thể reload same key.
      |
      +-- Context đã load fail?
      |      -> Spring 6.1 failure threshold / bean errors.
      |
      +-- Cần nhìn stats?
      |      -> DEBUG org.springframework.test.context.cache.
      |
      +-- Cần chứng minh same instance?
      |      -> assertSame(ApplicationContext a,b).
      |
      +-- Cần đếm contexts thực tạo?
      |      -> Test-only marker eager bean sequence,
      |         with known scope and no concurrent extra loads.
      |
      +-- Cần biết suite nhanh hơn?
             -> Benchmark repeated runs + startup logs,
                process/heap/GC/CI wall-clock metrics.
```

## 30. Kết luận

**Cache hit** nghĩa là Spring TestContext tìm được một `ApplicationContext` đã được load trước đó theo cache key tương đương. **Cache miss** nghĩa là lần lookup không có entry phù hợp; có thể do key lần đầu xuất hiện, context bị dirty/evict, hoặc cache process mới. **Số context đang được giữ** (`size`) không đồng nghĩa số context từng được tạo. **Số instances thực tạo** nên quan sát bằng marker bean/startup instrumentation phù hợp, và luôn ghi rõ process/scope/failure limitations.

Hiệu năng Spring Boot testing tốt đến từ việc thiết kế **test scope đúng**, cache keys có thể reuse khi an toàn, state cleanup đúng tầng và đo đạc thực tế. Đừng ép mọi tests share một context khi làm vậy khiến chúng phụ thuộc dữ liệu lẫn nhau; cũng đừng dùng `@DirtiesContext` cho mọi method chỉ để che state pollution.

## 31. Tài liệu chính thức

- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.1 — Context Caching (versioned reference): https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/testing.html
- Spring Framework — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework — Spring Testing Annotations: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework — TestContext Framework overview: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework 6.1 — TestContext Javadoc (getApplicationContext/markApplicationContextDirty): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContext.html
- Spring Framework — TestContextManager Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestContextManager.html
- Spring Framework — TestContext cache key, @ContextConfiguration and customizers: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/context-customizers.html
- Spring Framework — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers/service connection integration: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Gradle — Java testing (maxParallelForks/forkEvery): https://docs.gradle.org/current/userguide/java_testing.html
- JUnit Jupiter — Lifecycle, parallel tests, and test suites: https://docs.junit.org/current/user-guide/
