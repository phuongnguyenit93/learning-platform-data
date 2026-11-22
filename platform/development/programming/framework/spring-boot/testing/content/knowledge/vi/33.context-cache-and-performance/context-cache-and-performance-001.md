# Context cache tái sử dụng ApplicationContext như thế nào

## 1. Vì sao Spring Boot test thường không khởi động lại context sau mỗi bài?

Một lần chạy `@SpringBootTest` có thể tốn thời gian: Spring quét configuration, phân tích auto-configuration, khởi tạo singleton beans, tạo JPA EntityManagerFactory, DataSource pool, HTTP clients, security chain và các bean khác. Nếu có 80 test methods, khởi động lại toàn bộ context 80 lần thường lãng phí mà không giúp phát hiện thêm lỗi.

Spring Framework TestContext cung cấp **ApplicationContext cache** để tránh chi phí này. Sau khi tải thành công một context, framework ghi nó vào một cache **static trong JVM**. Các tests có **khóa cấu hình tương đương** có thể nhận lại **chính cùng một instance ApplicationContext**. Nhiều test classes khác tên vẫn có thể chia sẻ một context; ngược lại, hai methods gần nhau có thể chạy trên contexts khác nhau nếu cấu hình khác hoặc context bị đánh dấu dirty.

Điều cần nhớ:

> **Tái sử dụng dựa trên configuration key, không đơn thuần dựa trên class name, tên method, package hay loại annotation “@SpringBootTest”.**

Cache là cơ chế của **Spring TestContext Framework**. Spring Boot test support sử dụng cơ chế ấy và bổ sung các context customizers, bootstrap rules, test slices và cấu hình riêng. Không tồn tại “mỗi test method một context” như quy tắc bắt buộc.

### Bạn sẽ học được

- Context được load, lưu, tìm lại và đóng như thế nào.
- Spring tính một **cache key** từ configuration metadata nào.
- Những thay đổi vô tình làm cache miss: profile, inline properties, `@TestPropertySource`, dynamic properties, bean overrides và web mode.
- Ý nghĩa của cache static **trong cùng JVM**, giới hạn mặc định **32**, chính sách **LRU** và cache statistics.
- Cách `@DirtiesContext` loại bỏ context, khác reset data/beans/mock.
- Vì sao cache reuse có thể làm lộ state leakage giữa tests và cách xử lý mà không phá performance.
- Vai trò của `@MockitoBean`/`@MockBean`, `@DynamicPropertySource`, `@ServiceConnection`, context hierarchies và test slices.
- Cách quan sát cache hit/miss và điều chỉnh max cache size/failed-context threshold.
- Ví dụ đầy đủ Java 17+, Spring Boot **3.5.16**, JUnit Jupiter với **9 bài kiểm thử** đối chứng context identity.

**Phạm vi phiên bản:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter. Spring Boot 4.x / Spring Framework 7.x có thể chuyển package, starter hoặc behaviors test. Các lời giải thích về cache key, 32-entry LRU, cache static, `@DirtiesContext` ở đây dựa trên tài liệu Spring Framework 6.2.

## 2. Vòng đời: load, cache, reuse, evict

```text
                  TestClass A needs ApplicationContext
                                  |
                                  v
                  TestContext builds configuration KEY
                                  |
                                  v
                           cache lookup
                           /          \
                         HIT          MISS
                          |             |
                          v             v
              reuse cached context  load new context
                          |             |
                          |        startup succeeds?
                          |           /       \
                          |         yes       no
                          |          |         |
                          |       cache put   fail/threshold
                          |          |
                          +----------+
                                  |
                                  v
                         Test uses beans
                                  |
                    next TestClass with same KEY
                                  |
                                  v
                         same context instance

     Eviction: @DirtiesContext / LRU / JVM shutdown
                    -> context removed/closed
                    -> next request reloads for that key
```

**Các giai đoạn chính:**

1. Spring TestContext xác định cách bootstrap và cấu hình context của test.
2. Nó tạo `MergedContextConfiguration` thể hiện configuration metadata.
3. Framework tìm cache entry theo key đó.
4. **Hit:** trả lại context cũ, không cần refresh bean factory như lần đầu.
5. **Miss:** tạo một context mới, chạy refresh/startup; nếu thành công thì đưa vào cache.
6. Test method dùng context, beans và các dependencies như bình thường.
7. Context thường vẫn còn trong cache sau test method/class để tests tiếp theo có thể dùng lại.
8. Context có thể bị đóng khi `@DirtiesContext`, LRU eviction hoặc JVM shutdown.

### 2.1. “Reuse” nghĩa là cùng object, không phải chỉ cấu hình giống

Nếu cache hit, các kiểm chứng như sau có thể đúng:

```java
assertThat(secondContext).isSameAs(firstContext);
assertThat(secondContext.getBean(MySingleton.class))
        .isSameAs(firstContext.getBean(MySingleton.class));
```

Đây là **snippet**, không tự biên dịch nếu thiếu biến/imports. Cache hit trả **cùng ApplicationContext instance**; do đó singleton bean được giữ nguyên. Nó không đơn thuần tạo lại một context “giống hệt”. Trong phần 9, ta sẽ dùng `TestContextManager` và `isSameAs` để chứng minh điều này trong một JUnit test.

### 2.2. Cache khác singleton scope

Một bean `@Scope("singleton")` chỉ có **một instance trong mỗi ApplicationContext**, không phải một instance duy nhất trong cả JVM. Hai contexts khác nhau có thể chứa hai singleton beans cùng type nhưng instance khác nhau.

Context cache quyết định test nào chia sẻ cả **container**. Singleton scope quyết định trong **một container** có bao nhiêu instance của bean. Đừng nhầm hai cơ chế.

### 2.3. Context startup và method execution

Nếu nhiều tests reuse cùng context, chi phí bean initialization không lặp lại. Nhưng code trong test methods, `@BeforeEach`, transaction, fixture creation, HTTP requests, SQL cleanup và application logic vẫn chạy theo vòng đời JUnit/test listeners. **Context cache không cache kết quả assert, database queries hay HTTP responses**.

## 3. Khóa cache được tính từ những gì?

Tài liệu Spring Framework 6.2 liệt kê các yếu tố chính của context cache key:

| Thành phần key | Nguồn cấu hình | Ví dụ khiến key khác |
|---|---|---|
| `locations` | `@ContextConfiguration` XML/Groovy resource locations | Thay file config |
| `classes` | `@ContextConfiguration` classes | Thay một configuration class |
| `contextInitializerClasses` | Initializers | Thêm `ApplicationContextInitializer` |
| `contextCustomizers` | TestContext ContextCustomizerFactory | `@DynamicPropertySource`, `@MockitoBean`, `@TestBean`, nhiều Boot customizers |
| `contextLoader` | Context loader class | Đổi loader/bootstrap mechanism |
| `parent` | `@ContextHierarchy` | Khác parent hierarchy |
| `activeProfiles` | `@ActiveProfiles` | `test` so với `integration` |
| `propertySourceDescriptors` | `@TestPropertySource` files/resources | Thay resource properties |
| `propertySourceProperties` | `@TestPropertySource` inline values và các inline test properties được đưa vào metadata | Thay một key/value |
| `resourceBasePath` | `@WebAppConfiguration` | Đổi web resource base |

Với Spring Boot, các options như `@SpringBootTest(properties=...)` và test-slice annotations cũng có thể ảnh hưởng tới effective configuration key qua property metadata và/or context customizers. **Không nên suy rằng chỉ cần cùng `@SpringBootTest` là chắc chắn chung context.**

### 3.1. Ví dụ hai classes có thể reuse

```java
@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
class CustomerServiceTest {}

@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
class CustomerRepositoryTest {}
```

Hai classes trên là **snippets minh họa**: nếu các yếu tố khác của key cũng tương đương và chưa bị evict, chúng có thể nhận cùng ApplicationContext. Tên class khác không mặc nhiên phá sharing.

### 3.2. Chỉ một property khác cũng có thể tạo context khác

```java
@SpringBootTest(properties = "feature.mode=fast")
class FastModeTest {}

@SpringBootTest(properties = "feature.mode=safe")
class SafeModeTest {}
```

**Đây là snippets giản lược**, giả định Boot tự phát hiện application config như trong project thực. Hai bộ inline properties khác nhau → hai configurations khác nhau → thông thường hai cache entries. Đừng tạo một unique property value ngẫu nhiên theo từng test class nếu không cần thiết: bạn sẽ vô tình khiến cache luôn miss.

### 3.3. Tên method không phải key

Hai methods khác tên trong một class test dùng cùng application config thường share context, trừ khi có `@DirtiesContext`, dynamic test customizations, lifecycle thay đổi hoặc cache eviction. Một test method chạy sau không tự động được cấp bean mới.

### 3.4. Đặc biệt chú ý dynamic values

`@DynamicPropertySource` là một **context customizer**; định danh/cấu hình method đăng ký dynamic properties ảnh hưởng key. Nhưng **giá trị runtime do supplier trả về không tự được so sánh như một field bất biến trong key**. Hai classes chia cùng method được kế thừa mà supplier trỏ tới những containers/ports khác nhau có thể vô tình reuse một context với values/beans đã được tạo từ nguồn cũ.

Theo Spring docs, trường hợp dynamic properties thay đổi giữa subclasses có thể cần đánh dấu context dirty hoặc tổ chức test configuration tách biệt. Không dùng `@DynamicPropertySource` rồi mặc định mỗi random port làm key mới.

## 4. Phạm vi cache: JVM, test suite, fork và IDE

Context cache của Spring TestContext là **static cache trong process**. Nó không phải Redis, disk, Gradle build cache, Maven repository, JUnit extension store hoặc một singleton global xuyên các JVM.

```text
JVM process #1: static TestContext cache {Key A -> Context A}
                TestClass A ----------------------> HIT
                TestClass B (same key) -----------> HIT

JVM process #2: static TestContext cache {empty initially}
                TestClass C (same key as #1) -----> MISS + fresh load
```

**Hệ quả:**

- Chạy nhiều tests **trong cùng test worker JVM** mới có cơ hội chia sẻ cache.
- Nếu Maven Surefire hoặc Gradle cấu hình fork/restart JVM giữa từng class, static cache không được chuyển sang process khác.
- `maxParallelForks>1` có thể phân lớp test qua nhiều workers; mỗi process có cache riêng, dù classes cùng cấu hình.
- Gradle daemon process và Gradle test worker JVM không mặc nhiên là cùng process.
- IDE có thể dùng một hoặc nhiều test JVM tùy cách khởi chạy và cấu hình.
- Một lệnh build mới hoặc một IDE run mới thường không tái sử dụng in-memory Spring TestContext cache từ lần trước.

**Không nên** dùng `System.identityHashCode(context)` từ hai JVM khác nhau để kết luận reuse; các số có thể trùng ngẫu nhiên và không chứng minh cùng object.

### 4.1. Cấu hình Gradle để tối ưu khả năng sharing

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    // Demo: một test worker JVM, không fork lại sau N classes
    maxParallelForks = 1
    forkEvery = 0

    // JVM system property của TEST worker, không chỉ Gradle daemon:
    systemProperty 'spring.test.context.cache.maxSize', '32'
    systemProperty 'spring.test.context.failure.threshold', '1'
    systemProperty 'logging.level.org.springframework.test.context.cache',
            'DEBUG'
}
```

Đây là snippet Gradle cho Boot 3.5-compatible project. Nó giúp kiểm tra rõ hơn trong một test JVM, nhưng **không có nghĩa** mọi tests sẽ share một context nếu cache keys khác. Bật logging DEBUG cho cache có thể tạo nhiều logs; nên dùng khi chẩn đoán thay vì log liên tục mọi CI job.

### 4.2. Maven Surefire

Với Maven, xem `forkCount`, `reuseForks`, parallel test execution và JVM options. Nếu mỗi test class dùng một fresh fork, Spring cache không có cơ hội reuse xuyên classes. Thực tế có thể cần nhiều forks để cô lập leaks, nhưng phải chấp nhận chi phí startup và không gán tất cả chậm chạp cho Spring.

## 5. Dung lượng: mặc định 32 contexts và LRU

Spring Framework 6.2 cung cấp default cache max size **32 ApplicationContext entries**. Khi số context cấu hình khác nhau vượt mức, implementation cache mặc định dùng chính sách **least recently used (LRU)** để loại bỏ/đóng context ít được dùng gần đây.

Ví dụ ý niệm:

```text
Cache capacity = 3 (minh họa, không phải default)

Run A -> miss, cache [A]
Run B -> miss, cache [A,B]
Run C -> miss, cache [A,B,C]
Run A -> hit,  A is most recently used
Run D -> miss, evict B, cache [A,C,D]
Run B -> miss (B was closed), reload B, evict LRU
```

**Không diễn giải LRU bằng cách đo thời gian đơn thuần.** LRU dựa trên lịch sử truy cập cache; Spring docs đã công bố policy. Mở rộng max size có thể làm ít evictions hơn nhưng giữ nhiều bean graphs, thread pools, caches hoặc DataSources trong RAM. Tăng cache lên 100 không tự giúp khi mọi test dùng unique key.

### 5.1. Cách cấu hình dung lượng

JVM system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Hoặc qua SpringProperties mechanism theo Spring Framework docs. **Cần thiết lập đủ sớm trước lúc TestContext cache được sử dụng**, thường bằng Gradle/Maven test worker JVM args. Đặt vào file `application-test.yml` chưa chắc có tác dụng với cache bootstrap vì nó là setting của Spring TestContext cache chứ không phải một bean trong application context.

### 5.2. Đổi 32 thành 64 có phải luôn nhanh hơn?

Không. Nếu suite có 10 unique contexts, 32 đã đủ, tăng 64 vô ích. Nếu suite có 80 unique contexts, trước tiên hãy tìm nguyên nhân: inline properties biến thiên, profile combinations, mocks khác nhau, dynamic customizers, duplicate test slices. Tăng cache size chỉ hợp lý khi memory budget đủ và thống kê chứng minh eviction/thrash là nguyên nhân đáng kể.

## 6. Context cache statistics: quan sát thay vì đoán

Spring Framework hỗ trợ logging ở category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Đặt ở test logging configuration phù hợp để thấy statistics. Có thể dùng JVM/Gradle test-worker logging system properties như snippet trước.

Thông tin debug thường gồm:

- Cache size hiện tại.
- Max size.
- Hit count.
- Miss count.
- Parent context count trong một số cases.
- Failure count liên quan failure threshold ở các phiên bản hỗ trợ.

Các metrics là **tích lũy trong cache của một JVM**; không nên xem một con số hit count từ một toàn suite run như số lần chính xác một controller method được gọi. Context có thể được lookup nhiều lần trong quá trình SpringExtension listeners chuẩn bị từng test, nên hit count có thể lớn hơn “số bài test đã dùng lại”.

### 6.1. Đọc metrics đúng

| Tín hiệu | Ý nghĩa khả dĩ | Việc kiểm tra thêm |
|---|---|---|
| Hit tăng | Framework tìm được context theo key | Các tests nào có metadata tương đương? |
| Miss tăng | Key chưa có context khả dụng | Configuration khác, eviction, fork, dirty? |
| Cache size gần max thường xuyên | Có nhiều unique entries | Có LRU eviction/reload? |
| Đã tăng maxSize nhưng chậm không đổi | Không phải eviction bottleneck | Xem external fixtures, DB setup, migrations |
| Application khởi động lại nhiều lần | Cache miss hoặc dirty/fork | So sánh keys và startup logs |
| Không thấy cache logs | Category chưa ở DEBUG hoặc logger chưa được cấu hình | Test JVM logging config, test runner |

**Tối ưu hiệu năng phải đo trên cùng môi trường CI và cùng workload**. Một lần cold run khác warm run, image pull hoặc database migration có thể lấn át chi phí context.

## 7. @DirtiesContext: chủ động evict, không phải reset data

`@DirtiesContext` thông báo rằng ApplicationContext đã bị test thay đổi theo cách khiến việc reuse không an toàn. Spring TestContext sẽ **loại context khỏi cache và đóng nó**, để lần sau cần cùng key sẽ tạo context mới.

Một số modes tiêu biểu:

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalContextTest {}
```

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void mutatesSingletonConfiguration() {
    // Test sửa state/definition khiến context không còn an toàn.
}
```

Đây là **snippets minh họa**, không phải toàn bộ test classes runnable. Cần xác định context thực sự bị thay đổi trước khi dùng annotation.

### 7.1. BEFORE vs AFTER

- `ClassMode.AFTER_CLASS`: sau class, context bị dirty/closed; class tiếp theo cùng key reload.
- `ClassMode.BEFORE_CLASS`: trước class, loại bỏ cached context cũ và class sẽ load context mới.
- `MethodMode.AFTER_METHOD`: sau test method, dirty; method tiếp theo cùng key phải reload.
- `MethodMode.BEFORE_METHOD`: trước method, dirty; test sử dụng fresh context.
- Nếu annotation ở cả class/method, các modes tương ứng đều được áp dụng theo Spring TestContext listeners.

**Không dùng `@DirtiesContext` mặc định trên mọi test class** để “đảm bảo sạch”. Điều đó loại bỏ phần lớn lợi ích caching và kéo dài suite đáng kể.

### 7.2. Khi nào cần @DirtiesContext?

Thường chỉ khi test:

- Thay bean definitions hoặc context state mà không reset được.
- Gắn hoặc thay environment/singleton configuration theo cách làm context không an toàn.
- Dùng lifecycle-sensitive integration object mà shutdown/restart ảnh hưởng context chia sẻ.
- Có một test thật sự phá vỡ những giả định mà context khác sẽ cần.

**Không tự động cần** sau khi lưu một entity xuống DB (dùng transaction rollback/clean fixtures thường phù hợp hơn) hoặc sau khi mock trả một response khác (mock reset thường đủ). Một bean mutable có thể có `reset()` trong @AfterEach thay vì đóng toàn bộ context.

### 7.3. Context hierarchy

Nếu test dùng `@ContextHierarchy`, dirty context có thêm `hierarchyMode`. Default `EXHAUSTIVE` có thể ảnh hưởng **các subhierarchies cùng chung ancestor**; `CURRENT_LEVEL` nhằm giới hạn hơn khi phù hợp. Không bật CURRENT_LEVEL bừa bãi nếu ancestor cũng bị thay đổi; parent context vẫn có thể chứa state không hợp lệ.

## 8. Thiết kế một demo có thể quan sát object identity

Bộ ví dụ dùng Java 17, Spring Boot 3.5.16, Spring Framework TestContext, JUnit Jupiter và AssertJ.

**Ý tưởng:** một app cực nhỏ tạo ba beans:

- `ContextStamp`: record chứa UUID sinh khi context khởi tạo (phục vụ quan sát).
- `RequestCounter`: singleton mutable dùng để chứng minh state leakage khi context reused.
- `Clock`: bean để `@MockitoBean` mock, qua đó minh họa bean override thay đổi cache key.

Một lớp JUnit thường (không cần annotate chính nó bằng @SpringBootTest) gọi `TestContextManager` với **các fixture test classes** được annotate bằng @SpringBootTest. Điều này chủ động load context **trong cùng test method**, nên ta assert object identity mà không phụ thuộc JUnit chạy class nào trước.

### 8.1. Cây file

```text
src/
├── main/java/com/example/cachelab/
│   └── CacheLabApplication.java
└── test/java/com/example/cachelab/
    └── ContextCacheBehaviorTest.java
build.gradle
settings.gradle
```

Demo không có HTTP server, database, Docker hoặc network dependency. `webEnvironment=NONE` giữ scope tập trung vào TestContext cache.

### 8.2. Build configuration

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Tập trung demo trong một JVM, không tạo fork mỗi class.
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'context-cache-lab'
```

Từ Spring Boot 3.5 BOM, `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Spring Test và Mockito cần cho demo. Không cần thêm spring-security, spring-web hay database starter.

Lưu ý: Gradle Wrapper không được tạo trong nội dung này; dùng Gradle/IDE hoặc init project Gradle có wrapper tương thích. Đừng xem `build.gradle` như một script shell tự chạy.

## 9. Source code production của demo

**File `src/main/java/com/example/cachelab/CacheLabApplication.java`:**

```java
package com.example.cachelab;

import java.time.Clock;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }

    @Bean
    ContextStamp contextStamp() {
        return new ContextStamp(UUID.randomUUID());
    }

    @Bean
    Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    RequestCounter requestCounter() {
        return new RequestCounter();
    }

    public record ContextStamp(UUID id) {}

    public static final class RequestCounter {
        private final AtomicInteger counter = new AtomicInteger();

        public int value() {
            return counter.get();
        }

        public int increment() {
            return counter.incrementAndGet();
        }

        public void restore(int before) {
            counter.set(before);
        }
    }
}
```

**Điểm cần hiểu:**

- Mỗi lần tạo một `CacheLabApplication` context mới, bean method `contextStamp()` tạo một record/UUID mới.
- Nếu context được reuse, `ContextStamp` singleton cũ tiếp tục tồn tại.
- `RequestCounter` không tự được reset giữa test methods chỉ vì JUnit tạo test instance mới.
- `Clock` là một bean hữu hình để Spring Framework 6.2 `@MockitoBean` override.
- UUID/identity chỉ giúp quan sát, không dùng UUID để tạo cache key.
- Không đặt mutable counter static trong app; mục tiêu là chứng minh **state trong singleton container**, không chỉ Java static state.

## 10. Bộ kiểm thử runnable: 9 JUnit methods

**File `src/test/java/com/example/cachelab/ContextCacheBehaviorTest.java`:**

```java
package com.example.cachelab;

import java.time.Clock;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

class ContextCacheBehaviorTest {

    // Fixture classes intentionally have identical configuration metadata
    // except where a test is specifically demonstrating a cache-key change.

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class SharedA {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class SharedB {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @ActiveProfiles("alternate")
    static class DifferentProfile {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "cache.lab.group=shared",
            "cache.lab.variant=inline"
        }
    )
    static class DifferentInlineProperty {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @TestPropertySource(
        properties = "cache.lab.source=separate"
    )
    static class DifferentTestPropertySource {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class DynamicPropertyFixture {
        @DynamicPropertySource
        static void dynamic(DynamicPropertyRegistry registry) {
            registry.add("cache.lab.dynamic", () -> "from-supplier");
        }
    }

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @MockitoBean(types = Clock.class)
    static class MockClockFixture {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
    )
    static class DirtyAfterFixture {}

    private static ApplicationContext load(Class<?> fixtureClass) {
        return new TestContextManager(fixtureClass)
                .getTestContext()
                .getApplicationContext();
    }

    @Test
    void sameConfigInDifferentClassesReusesExactContext() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedB.class);

        assertThat(second).isSameAs(first);
        assertThat(second.getBean(
                CacheLabApplication.ContextStamp.class))
                .isSameAs(first.getBean(
                        CacheLabApplication.ContextStamp.class));
    }

    @Test
    void repeatedLookupOfOneFixtureUsesSameInstance() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedA.class);

        assertThat(second).isSameAs(first);
    }

    @Test
    void activeProfileDifferenceCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant = load(DifferentProfile.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getActiveProfiles())
                .contains("alternate");
    }

    @Test
    void inlineTestPropertyDifferenceCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DifferentInlineProperty.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.variant")).isEqualTo("inline");
    }

    @Test
    void testPropertySourceChangeCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DifferentTestPropertySource.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.source")).isEqualTo("separate");
    }

    @Test
    void dynamicPropertySourceCustomizerChangesCacheKey() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DynamicPropertyFixture.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.dynamic")).isEqualTo("from-supplier");
    }

    @Test
    void mockitoBeanOverrideChangesCacheKey() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant = load(MockClockFixture.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(Mockito.mockingDetails(
                variant.getBean(Clock.class)).isMock()).isTrue();
        assertThat(Mockito.mockingDetails(
                base.getBean(Clock.class)).isMock()).isFalse();
    }

    @Test
    void mutableSingletonStateIsSharedUntilReset() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedB.class);

        CacheLabApplication.RequestCounter counter =
                first.getBean(CacheLabApplication.RequestCounter.class);
        int original = counter.value();

        try {
            int incremented = counter.increment();
            assertThat(incremented).isEqualTo(original + 1);
            assertThat(second.getBean(
                    CacheLabApplication.RequestCounter.class).value())
                    .isEqualTo(original + 1);
        }
        finally {
            // Avoid contaminating other tests sharing this context.
            counter.restore(original);
        }
    }

    @Test
    void dirtiesContextEvictsAndReloadsSameConfiguration()
            throws Exception {
        ApplicationContext oldContext = load(SharedA.class);

        // Drive Spring TestContext lifecycle explicitly for this fixture.
        TestContextManager manager =
                new TestContextManager(DirtyAfterFixture.class);
        manager.beforeTestClass();
        try {
            ApplicationContext dirtyFixtureContext =
                    manager.getTestContext().getApplicationContext();
            assertThat(dirtyFixtureContext).isSameAs(oldContext);
        }
        finally {
            // @DirtiesContext(AFTER_CLASS) closes/evicts this cache key.
            manager.afterTestClass();
        }

        ApplicationContext refreshed = load(SharedB.class);
        assertThat(refreshed).isNotSameAs(oldContext);
    }
}
```

### 10.1. Vì sao TestContextManager được gọi thủ công?

Trong một JUnit run bình thường, `SpringExtension` và Spring TestContext listeners tự làm các bước test lifecycle. Ở đây ta cố ý tạo `TestContextManager` cho các fixture classes khác nhau **trong cùng method**, rồi lấy `getTestContext().getApplicationContext()`:

- Cùng configuration metadata → object identity giống nhau.
- Khác active profile / properties / customizer → object identity khác nhau.
- `@DirtiesContext(AFTER_CLASS)` được kiểm chứng bằng cách gọi `beforeTestClass()`, `afterTestClass()` trên manager của fixture rồi load cùng key lại.
- Dùng một method để kiểm tra identity tránh dựa trên thứ tự chạy hai JUnit test classes khác nhau.

**Đây là demo có chủ đích về TestContext internals**, không phải lời khuyên tạo TestContextManager thủ công ở mọi unit/integration test. Trong ứng dụng thật, chỉ cần `@SpringBootTest`, `@Autowired ApplicationContext` và để SpringExtension quản lý lifecycle.

### 10.2. 9 bài kiểm tra chứng minh điều gì?

| Test method | Kết quả mong đợi |
|---|---|
| sameConfigInDifferentClassesReusesExactContext | `SharedA` và `SharedB` cùng instance context |
| repeatedLookupOfOneFixtureUsesSameInstance | Lookup cùng key nhiều lần vẫn cùng object |
| activeProfileDifferenceCreatesSeparateContext | Profile là thành phần key |
| inlineTestPropertyDifferenceCreatesSeparateContext | Inline property thay key |
| testPropertySourceChangeCreatesSeparateContext | Test property source metadata thay key |
| dynamicPropertySourceCustomizerChangesCacheKey | DynamicPropertySource method tham gia customizer/key |
| mockitoBeanOverrideChangesCacheKey | Bean override là một phần context customizer |
| mutableSingletonStateIsSharedUntilReset | Singleton mutable state có thể rò giữa tests reuse |
| dirtiesContextEvictsAndReloadsSameConfiguration | Dirty evicts; lookup sau tạo context mới |

Trong bốn tests so sánh variant, asserts không khẳng định variant được tạo mới **mỗi lần chạy**: nếu một variant key đã có sẵn trong cache từ trước, nó có thể là cache hit của variant ấy nhưng vẫn **khác baseline key**. Đây là phân biệt quan trọng giữa “khác object” và “đang tạo context lần đầu”.

### 10.3. Lệnh chạy

Linux/macOS:

```bash
./gradlew test --tests "com.example.cachelab.ContextCacheBehaviorTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.cachelab.ContextCacheBehaviorTest"
```

**Kỳ vọng của mã:** 9 JUnit methods pass khi dependencies/JDK và Gradle environment phù hợp. Tài liệu này được rà soát theo Spring Framework 6.2 và Spring Boot 3.5 APIs, **không phải báo cáo đã thực thi thực tế trong phiên biên soạn**. Hãy kiểm tra JUnit output executed/passed/skipped thay vì chỉ thấy build task được đánh dấu UP-TO-DATE hoặc FROM-CACHE.

### 10.4. Không cần dựa trên stdout của thứ tự startup

Các context có UUID riêng, startup logs và cache hit counters thay đổi theo test order/run. Vì vậy ví dụ không assert thứ tự UUID hay một giá trị hit count cố định. Assertion mạnh nhất là `isSameAs/isNotSameAs` khi so sánh references trong cùng JVM.

## 11. Context cache và @SpringBootTest trong dự án thực

### 11.1. Khi nào hai @SpringBootTest classes share?

Một số điều kiện phổ biến:

- Cùng `classes`/bootstrapping configuration và application context type.
- Cùng active profiles.
- Cùng inline properties và `@TestPropertySource` declarations.
- Cùng context initializers/loaders.
- Cùng mock/spy/test-bean override declarations trong context customizers.
- Cùng dynamic property method/configuration customizers.
- Cùng parent context/web resource settings nếu có.
- Context chưa bị evict hoặc dirty; cùng test JVM.

**Không cần** mọi test classes phải kế thừa cùng một base class để sharing; base class chỉ giúp chuẩn hóa metadata. Nếu các classes cùng metadata thông qua annotations riêng, cache vẫn có thể hit.

### 11.2. @SpringBootTest và @WebMvcTest không mặc định chung context

`@WebMvcTest` thường nạp MVC slice: controllers, MVC support, các filters/configuration phù hợp; `@DataJpaTest` nạp JPA slice; `@SpringBootTest` tải full context. Các test types này thường có context metadata/customizers khác nhau, nên không nên mong cùng cache entry.

Không cố ép mọi test về `@SpringBootTest` chỉ để giảm unique contexts. Một slice context nhỏ khởi động nhanh và có mục đích cô lập rõ; đôi khi nhiều small contexts tốt hơn một full context nặng và phức tạp.

### 11.3. WebEnvironment tạo khác biệt

`@SpringBootTest(webEnvironment = MOCK)` thường sử dụng mock servlet environment (nếu web stack có trên classpath); `RANDOM_PORT` chạy embedded server. Tính chất context khác nhau và có thể tác động key; không thể mặc định reuse giữa hai chế độ.

Nếu test chỉ cần service/repository auto-config, chọn `webEnvironment=NONE` để tránh startup web infrastructure. Nhưng đừng chọn NONE cho tests cần kiểm tra HTTP filters, container port, real servlet network flow.

## 12. @MockitoBean, @MockBean và mock reset

### 12.1. Bean override là một phần của key

Spring Framework 6.2 hỗ trợ `@MockitoBean` và `@MockitoSpyBean`. Bean override configuration là một context customizer; vì vậy hai tests có một mock target/qualifier khác nhau có thể tạo các cache keys khác nhau.

Spring Boot `@MockBean`/`@SpyBean` được đánh dấu deprecated từ Boot 3.4, với hướng chuyển sang Framework `@MockitoBean`/`@MockitoSpyBean` trong Boot 3.5. Nếu dự án vẫn dùng các annotations cũ, Boot test support cũng có thể ảnh hưởng context customizers.

**Đừng tạo mock field name khác nhau vô cớ** nếu nó là fallback qualifier trong annotation: Spring Framework docs nêu field name/qualifiers có thể làm cache key khác. Thống nhất tên field/target bean cho những mocks có cùng ý nghĩa khi cần sharing.

### 12.2. Reset mock không phải reload context

Trong thông thường, Spring TestContext/Mockito test listeners có thể reset mocks giữa test methods dựa trên reset mode, giúp loại stubbings/interactions cũ. Điều này **không** đồng nghĩa đóng ApplicationContext. Mock bean vẫn được chứa trong context chia sẻ; nó chỉ được reset state.

Kiểm tra đúng API/version và lifecycle khi dự án customizes listeners hoặc reset modes. Nếu test vẫn dùng `@DirtiesContext` sau mỗi mock interaction, hãy xem có thể dùng mock reset/clear invocation hay không để giữ cache.

### 12.3. Overriding không chứng minh original infrastructure

Một test dùng mock bean service đã loại phần behavior thực của service, kể cả transactions/retries/caching advice tùy override strategy. Cấu hình cache khác không chỉ là chuyện tốc độ; nó còn ảnh hưởng phạm vi hành vi được kiểm thử. Nếu muốn xác minh real service/DB transaction, dùng test không override target cần kiểm tra.

## 13. @DynamicPropertySource, Testcontainers và @ServiceConnection

Testcontainers thường cung cấp mapped port/URL chỉ biết khi container start. Spring test có:

```java
@DynamicPropertySource
static void registerDatabase(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            POSTGRES::getJdbcUrl);
}
```

Đây là **snippet**, giả định có static Postgres container `POSTGRES` và dependencies; không nằm trong runnable demo.

### 13.1. Vấn đề hidden reuse khi dynamic supplier thay đổi

Hai test subclasses có thể kế thừa cùng một `@DynamicPropertySource` method nhưng lại dùng static container instance/endpoint khác nhau theo subclass. Cache key có method customizer metadata; **nếu method identity giống**, nó không tự key theo URL do supplier trả trong mỗi lần test.

Hậu quả có thể là reused context có DataSource/clients đã init bằng URL cũ. Giải pháp tùy mục tiêu:

- Dùng container lifecycle ổn định, chia sẻ đúng một endpoint cho các classes muốn share.
- Tách context configurations/dynamic methods khi endpoints cần khác.
- Dùng `@DirtiesContext` ở class base/fixture khi values thật sự thay đổi giữa subclasses, theo Spring docs.
- Hoặc cấu hình một test environment có nguồn ổn định nếu hợp đồng cho phép.

Không thêm random property vào mọi test chỉ để né reuse nếu mục tiêu là cùng database/container; làm vậy tăng contexts và tốn memory.

### 13.2. @ServiceConnection trong Spring Boot

Spring Boot 3.5 có Testcontainers `@ServiceConnection`. Spring Boot test support tạo connection details và context customizers cho annotated containers phù hợp. Cấu hình những containers khác nhau có thể khiến context configuration khác nhau, nhưng **đừng** suy cache key luôn chứa mapped random port như một literal. Cần hiểu lifecycle/container ownership và test context reuse trước khi dùng container static/reusable chia sẻ.

### 13.3. Container dừng nhưng context còn cache

Một nguồn flakiness:

1. Test class A khởi động static Testcontainers DB.
2. Spring context khởi tạo DataSource trỏ tới container A.
3. JUnit extension dừng container A sau class A.
4. Test class B dùng configuration metadata có thể reuse context A, nhưng DataSource vẫn trỏ tới endpoint container đã dừng.

Có thể quản lý bằng container lifecycle gắn với Spring context, một shared singleton container phù hợp, `@DirtiesContext` đúng scope hoặc Boot service connection integration đúng cách. Không mặc định rằng context cache biết Docker container bị stop.

## 14. Shared context mang theo shared state

Cache reuse là tối ưu performance **và** là lời nhắc về test isolation.

### 14.1. Các loại state khác nhau

| State | Context reuse có thể giữ lại? | Cách làm sạch phù hợp |
|---|---|---|
| Singleton bean mutable fields | Có | Reset bean có chủ đích hoặc thiết kế stateless |
| In-memory CacheManager | Có | Evict test cache entries / clear |
| Mockito stubbings/invocations | Có nếu không reset | Framework mock reset/listener |
| ThreadLocal/MDC | Có thể rò qua thread reuse | try/finally remove, test cleanup |
| Static fields | Có cùng JVM, không phụ thuộc context | Clear explicitly; tránh shared global state |
| Embedded DB dữ liệu | Tùy DB lifecycle/transactions | Rollback, @Sql cleanup, truncate fixtures |
| External database/Kafka | Không nằm trong context cache, nhưng clients giữ connections | Unique fixtures, transaction/cleanup, consumer group isolation |
| Bean definitions/scope/proxy | Context giữ tới khi dirty/closed | Tránh mutate; @DirtiesContext nếu thật sự không khôi phục được |
| HTTP port/server sockets | Gắn với context web app lifecycle | Quản lý @SpringBootTest webEnvironment và context lifecycle |

**Không coi `@Transactional` trong test là “reset mọi thứ”.** Rollback thường chỉ áp dụng transaction cùng thread/data source theo test mechanism. Nó không tự reset singleton in-memory state, Kafka messages, remote HTTP actions hoặc mọi async thread side effects.

### 14.2. Vì sao ví dụ dùng try/finally?

Trong bài `mutableSingletonStateIsSharedUntilReset`, test tăng RequestCounter rồi dùng `finally { counter.restore(original); }` để trả lại trạng thái trước khi kết thúc. Nhờ vậy test chứng minh shared state mà không làm methods chạy sau bị bẩn.

Nếu test thay đổi bean definitions hoặc global configuration không thể reset an toàn, dùng `@DirtiesContext`. Nếu chỉ thêm một record vào test DB, dùng rollback/clean fixture thường rẻ hơn nhiều.

### 14.3. @TestInstance và cache là hai vòng đời khác

JUnit Jupiter mặc định tạo test instance theo method, trừ khi `@TestInstance(PER_CLASS)` hoặc cấu hình khác. Spring ApplicationContext cache có vòng đời theo configuration/JVM. **Một Java test object mới không có nghĩa Spring bean mới**.

Tương tự, `@BeforeEach` được chạy mỗi method, nhưng `@PostConstruct` của singleton bean chỉ chạy khi bean/context được tạo mới. Không đưa assertions “PostConstruct phải chạy N lần bằng số @Test” khi caching được bật.

## 15. LRU, context hierarchy và failure threshold

### 15.1. LRU eviction không phải @DirtiesContext

- **LRU:** cache tự đóng entry ít dùng gần đây nếu số context vượt max.
- **@DirtiesContext:** test chủ động nói context không còn an toàn.
- **JVM shutdown:** static cache biến mất cùng process, contexts đang sống được đóng theo cơ chế framework.

Một context bị evict do LRU không chứng minh test đã làm nó dirty; đó có thể chỉ là áp lực cache capacity.

### 15.2. Context hierarchy

Khi `@ContextHierarchy` tạo parent/child contexts, key chứa parent metadata. Một test dirty child context có thể ảnh hưởng nhiều nhánh hierarchy theo default exhaustive strategy; `hierarchyMode=CURRENT_LEVEL` có thể giới hạn phạm vi hơn khi thích hợp.

Không áp dụng `CURRENT_LEVEL` vô điều kiện nếu ancestor state cũng bị sửa. Theo Spring docs, `@MockitoBean` và `@MockitoSpyBean` áp dụng tới các levels mặc định trong một số hierarchy setups; dùng `contextName` nếu phải target một level cụ thể.

### 15.3. Context failure threshold (từ Spring Framework 6.1)

Spring Framework có **failure threshold** mặc định **1** trên mỗi cache key. Nếu một context load thất bại vì cấu hình, các lần thử tiếp theo với cùng key trong cùng suite có thể bị **bỏ qua sớm** với `IllegalStateException` thay vì tốn thời gian khởi động rồi fail lần nữa.

JVM property:

```text
-Dspring.test.context.failure.threshold=1
```

Đây là **chính sách tránh lặp lại context startup failure**, không phải caching một ApplicationContext thành công. Khi gặp thông báo “ApplicationContext failure threshold exceeded”, hãy tìm **lần startup failure đầu tiên** của cùng key, không mặc định test sau có lỗi riêng. Nếu sửa lỗi config, chạy lại suite/process và xác minh.

Không nâng threshold thật cao để che nguyên nhân configuration failure; chỉ điều chỉnh có mục đích khi đang debug transient external dependencies.

## 16. Chẩn đoán tình huống “tại sao context cứ start lại?”

### 16.1. Checklist theo thứ tự

1. Xác định tests có chạy trong cùng JVM/test worker không.
2. Xác định test dùng `@SpringBootTest`, `@WebMvcTest` hay slice khác.
3. So sánh `classes`/locations/loader/initializers.
4. So sánh `@ActiveProfiles`, profiles resolver và inline test properties.
5. So sánh `@TestPropertySource` resource paths và inline properties.
6. So sánh `@MockitoBean`/`@MockBean`/`@TestBean` targets, field names, qualifiers.
7. So sánh `@DynamicPropertySource` method registrations và Testcontainers config.
8. Kiểm tra `@DirtiesContext` (method/class, inheritance và meta-annotations).
9. Kiểm tra LRU cache max size và khả năng cache thrashing.
10. Bật debug `org.springframework.test.context.cache` và đọc hit/miss/size.
11. Xem startup logs/callback và JUnit reports để xác định thời gian nằm ở context hay test fixtures.
12. Tối ưu một yếu tố có căn cứ; không thay security/db wiring chỉ để giảm context count.

### 16.2. Bảng troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mỗi test class đều in Boot banner/startup | Keys khác hoặc fork JVM | So configs/JVM, debug cache |
| Cùng @SpringBootTest nhưng không reuse | Inline properties/profile/mock khác | Chuẩn hóa những gì thật sự tương đương |
| Thay mock field name làm thêm context | Bean override fallback qualifier | Dùng stable field names/explicit qualifier |
| Random port Testcontainers thay đổi, context vẫn dùng URL cũ | Dynamic source method same key nhưng value/lifecycle thay | Stable container owner, dirty/separate key khi cần |
| Context bị đóng sau test class | @DirtiesContext(AFTER_CLASS) | Bỏ khi không thật sự làm context dirty |
| Cache size chạm 32 thường xuyên | Nhiều unique configs, LRU evictions | Giảm unique keys; điều chỉnh maxSize nếu đủ RAM |
| Tăng maxSize nhưng suite vẫn chậm | Bottleneck ở DB migration/setup hoặc memory | Đo từng phase; không tối ưu mù |
| 401/403 khác giữa tests | Profiles/security mock/filters khác | Không ép reuse context trái test contract |
| Singleton counter còn giá trị test trước | Reused context giữ bean state | Reset/clear/rollback phù hợp |
| @Transactional rollback nhưng cache vẫn bẩn | Non-DB singleton/static/async state | Reset đúng resource, không chỉ DB rollback |
| Test 2 nhận context load preemptively skipped | Failure threshold=1 sau lỗi đầu | Tìm root startup error đầu tiên |
| Cache hit count không bằng số test methods | Nhiều lookups cho một test | Chỉ đọc stats như indicators, không như số methods |
| Chạy IDE một class nhanh, chạy CI suite chậm | Fork/parallel/cache thrash/fixtures | So worker processes, suite config |
| Chạy CI nhiều forks nhưng không chung cache | Static cache từng process | Chấp nhận tradeoff isolation/performance |
| TestContextManager demo load context sớm | Chủ động getApplicationContext | Hiểu đây là inspection, không production workflow |
| @WebMvcTest context không giống full Boot | Slice metadata khác | Đừng ép same-key nếu scope khác |
| Context hierarchy dirty gây nhiều reloads | Default exhaustive hierarchy dirtiness | Xem hierarchyMode và ancestor behavior |
| Thêm @TestConfiguration ở mỗi class | Context customizer khác | Reuse shared fixture config nếu semantics giống |
| Flaky do shared singleton state | Tests chưa cleanup | Có reset(), state-independent fixtures |

## 17. Tối ưu thiết kế test suite mà không đổi behavior

### 17.1. Chuẩn hóa những cấu hình trùng ý nghĩa

Nếu 30 classes cần đúng cùng một application profile, có thể tạo một meta-annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
@ActiveProfiles("integration")
public @interface IntegrationTestConfig {}
```

Đây là **snippet minh họa**, cần imports, application class và Java annotation source file riêng. Không bắt buộc dùng meta-annotation; mục tiêu là giữ configuration metadata nhất quán.

Tuy nhiên, đừng hợp nhất hai profiles hoặc properties nếu chúng đại diện business behavior khác. **Correctness trước, cache hit sau.**

### 17.2. Dùng slice/runner khi có lợi

- Unit tests cho pure Java service: không cần Spring ApplicationContext.
- `ApplicationContextRunner` cho custom auto-configuration conditions: nhanh và chủ động tạo context nhỏ; đây là **một loại context test riêng**, không phải bằng chứng Spring TestContext static cache được share với @SpringBootTest.
- `@WebMvcTest` cho controller slice, `@DataJpaTest` cho repository slice.
- `@SpringBootTest` cho full integration behavior.
- `RANDOM_PORT` khi phải kiểm chứng real HTTP/servlet container.

Một full context cache hit có thể rẻ về lần startup sau, nhưng không bù được test đang mock sai tầng hoặc thiếu validations.

### 17.3. Đừng dùng @DirtiesContext như @AfterEach

Nếu một test chỉ biến đổi database data, dùng transaction rollback hoặc `@Sql` cleanup. Nếu một bean giữ in-memory cache, gọi eviction/clear có kiểm soát. Nếu một mock bị stubbing, dùng framework mock reset. `@DirtiesContext` chỉ nên là lựa chọn khi context thật sự không thể reuse an toàn.

### 17.4. Tối ưu bằng đo lường

Một kế hoạch:

1. Chạy một baseline suite trên cùng CI worker với timing logs.
2. Bật TestContext cache DEBUG, thu size/hits/misses.
3. Ghi số application start thực, số test JVM forks và số @DirtiesContext.
4. Tìm các nhóm tests khác nhau chỉ vì property/fixture không cần thiết.
5. Gộp đúng những metadata tương đương (không thay behavior).
6. Kiểm tra singleton/shared state có cleanup.
7. Chạy lại đúng suite, so elapsed time, pass/fail/skipped và RAM.
8. Chỉ tăng maxSize nếu eviction là nguyên nhân và memory cho phép.

Một cache hit rate cao không phải mục tiêu duy nhất: nếu isolation sai làm test flaky hoặc che bug, tốc độ cao không đáng tin.

## 18. Câu hỏi thực hành có đáp án

### A. Hai classes khác tên, cùng @SpringBootTest

Có thể chia sẻ ApplicationContext không?

**Có**, nếu effective configuration key tương đương và cùng test JVM, context chưa dirty/evicted. Test class name tự nó không phải thành phần key độc lập.

### B. Cùng class, hai @Test

Context có phải được tạo hai lần không?

**Thông thường không.** Spring TestContext reuse context; test instance JUnit có thể mới từng method nhưng Spring singleton beans vẫn cũ.

### C. Đổi @ActiveProfiles("test") sang "ci"

Tại sao context khác?

**Vì activeProfiles tham gia key.** Hai profiles có thể tạo bean/configuration khác, nên không ép sharing.

### D. Mỗi class thêm một random inline property

Hệ quả?

**Có thể tạo rất nhiều unique keys**, giảm hit rate và gây LRU eviction. Chỉ tạo random names/ports trong configuration khi test thực cần isolation đó.

### E. @DynamicPropertySource supplier trả port khác

Có tự tạo key khác mỗi lần không?

**Không có bảo đảm như vậy.** Method/customizer metadata tham gia key; giá trị runtime không được tự động dùng làm unique key. Cần quản lý container lifecycle và context dirtiness.

### F. Thêm @MockitoBean vào một class

Có thể phá cache reuse?

**Có.** Bean override context customizer tham gia key, bao gồm target/qualifier metadata. Dùng consistent mock declarations khi các classes thật sự cần cùng cấu hình.

### G. Một @DirtiesContext trên method

Điều gì xảy ra sau khi test kết thúc?

Theo `AFTER_METHOD`, cached context được evict/closed; method/test tiếp theo cần cùng configuration sẽ load context mới.

### H. Test thay mutable singleton counter

Context được reuse có làm counter tự reset không?

**Không.** Cần manual reset/fixture hoặc dirty context nếu không thể khôi phục an toàn.

### I. Cùng key nhưng chạy ở hai forked JVMs

Có chia sẻ cùng ApplicationContext instance không?

**Không.** Static cache riêng theo process.

### J. Cache đạt 33 entries ở default maxSize 32

Hệ quả?

Cache mặc định dùng LRU eviction và đóng entry ít được dùng gần đây để giữ kích thước giới hạn. Một test cần entry đã evicted sẽ load lại.

### K. Tăng maxSize từ 32 lên 64

Có luôn cải thiện performance không?

**Không.** Nếu unique keys ít hơn 32 hoặc bottleneck nằm ở DB fixtures/test operations, tăng không giúp. Nếu RAM hạn chế, còn có thể gây memory pressure.

### L. Context load error lặp lại ở nhiều classes

Tại sao các failures sau thông báo threshold exceeded?

Spring Framework 6.1+ có failure threshold mặc định 1 theo key. Nó tránh retry một context lỗi nhiều lần; tìm lỗi startup **đầu tiên**.

### M. @TestInstance(PER_CLASS) có nghĩa cache per-class?

**Không.** Đó là lifecycle của JUnit test object; Spring context cache độc lập và có thể được share giữa nhiều test classes.

### N. Context cache reuse có làm database records rollback không?

**Không.** Database transaction test listener/rollback và cleanup fixtures là cơ chế khác. Context cache chỉ giữ container/beans.

### O. Context không share giữa @WebMvcTest và @SpringBootTest

Có lỗi không?

**Không.** Hai test scopes/configuration metadata thường khác nhau. Chọn đúng layer thay vì ép hit.

## 19. Checklist QA cho context cache và performance

- [ ] Đã phân biệt context loading và test method execution.
- [ ] Hiểu key là MergedContextConfiguration, không đơn thuần tên class.
- [ ] Đã xem profiles, inline properties, TestPropertySource và customizers.
- [ ] MockitoBean/MockBean qualifiers và field names được đặt nhất quán.
- [ ] DynamicPropertySource methods/values/container lifecycles được quản lý rõ.
- [ ] Không giả định ServiceConnection random port tự tạo unique context key.
- [ ] Cùng JVM/test worker nếu kỳ vọng share static cache.
- [ ] Đã rà soát Maven/Gradle forks/parallel workers.
- [ ] Không áp @DirtiesContext mặc định cho mọi method.
- [ ] Sử dụng @DirtiesContext khi shared context thật sự không an toàn.
- [ ] Singleton bean mutable state được reset hoặc thiết kế stateless.
- [ ] Test DB rollback/cleanup không bị nhầm thành context refresh.
- [ ] ThreadLocal/static/mock state có cleanup thích hợp.
- [ ] Không assert số UUID/startup logs/hit count tuyệt đối phụ thuộc thứ tự tests.
- [ ] Đã xem TestContext cache DEBUG statistics trước khi tăng maxSize.
- [ ] Biết maxSize mặc định 32 và chính sách LRU.
- [ ] Property maxSize được đặt ở test JVM đủ sớm.
- [ ] Có đủ RAM nếu tăng maxSize.
- [ ] Biết context failure threshold khác successful context cache.
- [ ] Không coi preemptively skipped context load là root cause.
- [ ] @ContextHierarchy và hierarchyMode được cân nhắc khi dirty parent/child.
- [ ] Không ép reuse contexts với actual configuration requirements khác.
- [ ] Không chuyển hết slice tests thành full Boot tests chỉ để share một key.
- [ ] Đã đo suite time, memory, context miss/hit và test correctness cùng nhau.
- [ ] Test methods chạy độc lập, không dựa vào thứ tự shared state.
- [ ] CI report có executed/passed/failed/skipped counts, không chỉ build green.
- [ ] Java 17+/Boot 3.5/Spring 6.2 imports đúng bản mục tiêu.
- [ ] Không dùng demo TestContextManager thủ công trong production test code khi SpringExtension đủ.
- [ ] Có chiến lược lifecycle nếu contexts giữ thread pools/connections/container services.
- [ ] Không tiết lộ credentials, production endpoints hoặc PII trong cache/debug logs.

## 20. Kết luận

**Spring TestContext cache tái sử dụng chính ApplicationContext instance theo một khóa cấu hình**, trong một static cache thuộc JVM đang chạy tests. Hai test classes khác tên nhưng cùng metadata có thể dùng chung context và singleton beans; các thay đổi về profile, properties, context customizers, bean overrides hoặc environment scope có thể tạo key khác.

- Cache mặc định có **maxSize 32** và evict theo **LRU**.
- `@DirtiesContext` chủ động close/remove context; đừng dùng thay cho DB/mock/state cleanup thông thường.
- `@MockitoBean`, `@DynamicPropertySource`, test slices và Testcontainers config cần được xem xét khi debug cache misses.
- Forked JVMs không chia sẻ static cache.
- Context reuse cải thiện startup performance nhưng **giữ lại singleton state**, nên test isolation là điều kiện đi kèm.
- Hãy xem debug cache statistics và đo execution time thực, không suy từ một test run nhỏ.

Bộ ví dụ Java 17+ và 9 JUnit tests cung cấp bằng chứng trực tiếp bằng object identity về cùng key được reuse, metadata khác tạo context khác và `@DirtiesContext` khiến context được load lại. Với hệ thống phức tạp, kết hợp thông tin ấy với profiling DB, Testcontainers và web/server startup để tối ưu đúng nút thắt.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): configuration cache key, static JVM cache, default 32/LRU, stats/debug, shutdown.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): class/method modes, eviction, hierarchy mode.
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html): threshold mặc định 1 từ Framework 6.1.
- [Spring Framework 6.2 — Bean Override with @MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, qualifiers, field names và context cache.
- [Spring Framework 6.2 — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): @DynamicPropertySource và dynamic values.
- [Spring Framework 6.2 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/TestContextManager.html): getTestContext, beforeTestClass, afterTestClass.
- [Spring Framework 6.2 — Context Hierarchies](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/hierarchies.html): parent/child metadata and hierarchy eviction.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, webEnvironment, slices và test configuration.
- [Spring Boot 3.5 — MockitoBean/MockBean migration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): deprecated legacy Boot mock annotation.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection và container-related test configuration.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html): Gradle plugin 3.5.16 và build setup.
