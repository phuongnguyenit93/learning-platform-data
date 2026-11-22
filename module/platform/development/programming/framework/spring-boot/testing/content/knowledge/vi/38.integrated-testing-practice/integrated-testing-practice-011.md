# Đo số context, thời gian suite và tối ưu cấu hình dùng chung

## 1. Mục tiêu của bài thực hành

Khi một test JUnit dùng `@SpringBootTest`, Spring có thể phải quét components, tạo beans, bind properties, khởi động connection pools, HTTP filters, JPA hoặc message listeners. Nếu mỗi class dùng cấu hình khác nhau, `ApplicationContext` có thể bị nạp lặp lại dù assertions chỉ tốn vài mili giây.

Bài này thuộc nhóm **Thực hành tích hợp**, chủ đề **Đo số context, thời gian suite và tối ưu cấu hình dùng chung** trong module **Spring Boot - testing**. Mục tiêu là đo đúng **số context thực sự được tạo**, **cache hit/miss**, **thời gian Gradle Test task**, **JUnit testcase durations** và **wall-clock suite**; sau đó giảm chi phí startup mà vẫn giữ test isolation.

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, **JUnit Jupiter** và Gradle 8.x tương thích. Project có một service thuần Java, hai Spring integration classes dùng chung context, một class dùng property khác, và test-only instrumentation. Không cần Docker, DB hoặc broker.

### Bạn sẽ nắm được

- Cách Spring TestContext xây `MergedContextConfiguration` làm cache key.
- Cache static trong test JVM; Gradle forks không chia sẻ cache.
- Context cache mặc định tối đa 32 entries, eviction LRU.
- DEBUG logger `org.springframework.test.context.cache` và cách đọc `hitCount`/`missCount`.
- Vì sao `@TestPropertySource`, `@MockBean`, `@DynamicPropertySource` và `@DirtiesContext` ảnh hưởng reuse.
- Đếm context creations bằng singleton marker thay vì suy từ cache miss.
- Đo build wall time riêng với Gradle TestResult và JUnit XML.
- Thiết kế baseline, thử một biến mỗi lần, benchmark và giữ test coverage/độ ổn định.
- Chọn unit tests/test slices thay cho full `@SpringBootTest` khi phù hợp.
- Cảnh báo về Testcontainers, context lifecycle và parallel tests.

## 2. Phân biệt các thước đo

| Metric | Câu hỏi trả lời | Không được hiểu nhầm |
| --- | --- | --- |
| Context creations | Bao nhiêu instances context được nạp trong một JVM? | Không phải số `@Test` |
| Cache `hitCount` | Bao nhiêu lần Spring tìm thấy context phù hợp? | Không phải số tests PASS |
| Cache `missCount` | Bao nhiêu lookup không có cached entry? | Không nhất thiết bằng số context mới |
| Cache `size` | Có bao nhiêu entries còn trong cache? | Không phải tổng từng được tạo |
| Cache `maxSize` | Giới hạn lưu contexts | Không phải số context luôn cần |
| Gradle Test task elapsed | Test task mất bao lâu? | Không gồm toàn bộ compilation và CI |
| JUnit XML `time` | Testcase duration được runner ghi | Không nhất thiết là context refresh time |
| CLI wall time | Từ lúc chạy Gradle đến lúc kết thúc | Gồm build setup/compile/test/report |
| CI workflow duration | Job/shard kết thúc sau bao lâu? | Có thêm queue/cache/upload |
| Heap/GC/flaky rate | Tối ưu có gây resource/race problem? | Không thể bỏ qua để đổi lấy hit rate cao |

Nếu báo “giảm từ 10 xuống 4 contexts”, cần ghi cách đếm, JVM PID, test set, cache/fork settings và có hay không `@DirtiesContext`. Một lần chạy 4 Gradle workers và lần sau 1 worker không trực tiếp so được số context của một PID.

## 3. Cache Spring TestContext hoạt động ra sao?

```text
SharedOneTest ------> merged context key K1
                       cache MISS -> create Context #1

SharedTwoTest ------> merged context key K1
                       cache HIT  -> reuse Context #1

PropertyVariantTest -> merged context key K2
                       cache MISS -> create Context #2

Static ContextCache **trong một test JVM**
  K1 => Context #1
  K2 => Context #2
```

Spring TestContext dùng `MergedContextConfiguration` từ `@ContextConfiguration` classes/locations/initializers, `@ActiveProfiles`, `@TestPropertySource`, resource base path, loader, parent context và `ContextCustomizerFactory` customizers. Spring Boot `@MockBean`/`@SpyBean`, `@DynamicPropertySource` methods và imports có thể góp phần tạo key khác.

**Tên test class không mặc định là cache key.** Hai classes khác tên nhưng effective configuration giống nhau có thể reuse; còn hai classes cùng mục đích nhưng khác một inline property có thể tạo hai contexts.

Cache của Spring Test là một biến **static trong JVM**, không phải Gradle build cache hay cache bên ngoài. Các Gradle test JVM forks, modules/CI jobs khác nhau không chia sẻ static state.

## 4. Default cache size=32 và LRU

Spring Framework 6.1 mặc định `maxSize=32`. Khi nhiều context keys hơn giới hạn, LRU eviction đóng context ít được dùng gần đây; test sau cần lại key đó sẽ phải nạp mới.

JVM property:

```properties
spring.test.context.cache.maxSize=32
```

**Hãy đặt trong test worker JVM** bằng Gradle `Test.systemProperty`, không chỉ trên Gradle daemon. Tăng từ 32 lên 64 chỉ có lý khi logs/measurements cho thấy eviction và còn đủ heap. Giữ nhiều full contexts có Hikari pools, JPA, Kafka threads có thể tăng GC/OOM và làm suite chậm hơn.

`hitCount`/`missCount` là số lookups, không phải số context creation. `size` là số entries còn sống hiện tại, không gồm các contexts đã dirty/evict. Bài dùng test-only bean marker để đếm số lần tạo context, rồi kết hợp với cache statistics để lý giải.

## 5. Bật cache statistics

`src/test/resources/application-test.yml`:

```yaml
spring:
  main:
    web-application-type: none

logging:
  level:
    org.springframework.test.context.cache: DEBUG
```

Ví dụ **định dạng minh họa, không phải stdout thực**:

```text
DefaultContextCache ... size = 2, maxSize = 32,
parentContextCount = 0, hitCount = 40, missCount = 2
```

Logger có thể phát nhiều snapshots của các counters tích lũy, **không cộng nhiều dòng log**. Một số cache lookups rất sớm có thể không xuất hiện nếu logging profile chỉ có hiệu lực sau khi Boot khởi tạo logger. Khi cần theo dõi từ đầu JVM, cấu hình backend logging trước Spring context startup.

Bật DEBUG khi chẩn đoán, tắt/giảm khi chạy CI thường xuyên nếu log quá lớn; không log test secrets/PII.

## 6. Project tự chạy

```text
context-suite-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/cachelab/
│   ├── ContextSuiteApplication.java
│   └── TotalsService.java
├── src/test/java/com/example/cachelab/
│   ├── ContextProbeConfig.java
│   ├── TotalsServiceUnitTest.java
│   ├── ReuseFirstTest.java
│   ├── ReuseSecondTest.java
│   └── VariantPropertiesTest.java
├── src/test/resources/application-test.yml
└── scripts/summarize_junit.py
```

Hai Spring tests `ReuseFirstTest` và `ReuseSecondTest` dùng đúng cùng configuration K1. `VariantPropertiesTest` có thêm `@TestPropertySource` → K2. `TotalsServiceUnitTest` không dùng Spring. Tất cả ứng dụng/minh họa cùng package giúp Spring component scan hoạt động.

## 7. Gradle build

`settings.gradle`:

```groovy
rootProject.name = 'context-suite-lab'
```

`build.gradle`:

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Một worker JVM, cho phép reuse static context cache.
    maxParallelForks = 1
    forkEvery = 0

    // Chuyển project property vào JVM chạy JUnit.
    systemProperty(
        'spring.test.context.cache.maxSize',
        providers.gradleProperty('contextCacheSize')
                 .orElse('32')
                 .get())

    reports {
        junitXml.required = true
        html.required = true
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
        exceptionFormat =
          org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }

    afterSuite { descriptor, result ->
        if (descriptor.parent == null) {
            long millis = result.endTime - result.startTime
            println(
                'TEST_SUMMARY ' +
                'cases=' + result.testCount +
                ' passed=' + result.successfulTestCount +
                ' failed=' + result.failedTestCount +
                ' skipped=' + result.skippedTestCount +
                ' elapsedMs=' + millis)
        }
    }
}
```

Giải thích:

- `spring-boot-starter` đủ để tạo một Boot context không có web/JPA infrastructure.
- `spring-boot-starter-test` cung cấp Spring Test/JUnit Jupiter/Mockito/AssertJ.
- `maxParallelForks=1` giới hạn Gradle test workers; mặc định mỗi `Test` task chạy trong forked JVM.
- `forkEvery=0` không recycle worker sau mỗi test class; `forkEvery=1` rất tốn startup và làm mất cơ hội cache reuse.
- `spring.test.context.cache.maxSize` được truyền đúng test JVM qua `Test.systemProperty`.
- `showStandardStreams=true` để quan sát `CTX_CREATED`; production CI chỉ bật nhiều stdout khi thực sự cần.
- `afterSuite` root in task-level counts/duration; **không đo riêng context startup**.
- JUnit parallel không được bật trong lab để giảm yếu tố race.
- Không thêm `ignoreFailures=true` hoặc `|| true` làm xanh giả.

Nếu project chưa có Gradle Wrapper, `./gradlew`/`.\gradlew.bat` chưa tồn tại; tạo Wrapper tương thích hoặc dùng Gradle 8.x đã cài.

## 8. Java application và service thật

`src/main/java/com/example/cachelab/ContextSuiteApplication.java`:

```java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextSuiteApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextSuiteApplication.class, args);
    }
}
```

`src/main/java/com/example/cachelab/TotalsService.java`:

```java
package com.example.cachelab;

import org.springframework.stereotype.Service;

@Service
public class TotalsService {
    public long totalCents(long price, int quantity) {
        if (price < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }
        return Math.multiplyExact(price, quantity);
    }
}
```

`TotalsService` có thể kiểm tra thuần Java; các Spring tests chỉ nhằm minh họa bean wiring/cache, không phải vì phép nhân yêu cầu `@SpringBootTest`.

## 9. Test-only probe đếm context creations

`src/test/java/com/example/cachelab/ContextProbeConfig.java`:

```java
package com.example.cachelab;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ContextProbeConfig {

    private static final AtomicInteger CREATED =
            new AtomicInteger();

    @Bean
    ContextMarker contextMarker() {
        int ordinal = CREATED.incrementAndGet();
        System.out.println(
                "CTX_CREATED pid=" +
                ProcessHandle.current().pid() +
                " ordinal=" + ordinal);
        return new ContextMarker(ordinal);
    }
}

record ContextMarker(int ordinal) {
}
```

Spring tạo singleton `ContextMarker` **một lần khi context có import config được khởi tạo**. Khi hai classes dùng lại cùng cached context, bean cũ được inject; counter không tăng.

Điểm giới hạn:
- Static counter chỉ sống trong **một test JVM**, cần xem PID.
- Reload sau `@DirtiesContext` hoặc eviction làm ordinal tăng.
- Context không import probe không được đếm.
- Context startup fail trước khi bean được tạo không in marker.
- Test class order không cố định; **không assert ordinal phải bằng 1 hay 2**.
- `@TestConfiguration` top-level không bị Boot scan như production config; tests phải `@Import`.
- Marker đếm context instances, không đo thời gian refresh. Muốn timing chi tiết dùng Spring `ApplicationStartup`/JFR hoặc profiler phù hợp.

## 10. Unit tests không cần ApplicationContext

`src/test/java/com/example/cachelab/TotalsServiceUnitTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TotalsServiceUnitTest {

    private final TotalsService service = new TotalsService();

    @Test
    void computesWithoutSpringContext() {
        assertEquals(600L, service.totalCents(200, 3));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalCents(-1, 2));
    }
}
```

Hai tests không nạp context và có thể chạy nhanh. Nếu service chỉ có pure logic, đây thường là test level thích hợp. Giữ Spring integration tests cho behavior như bean wiring, profile, transaction, filters và external integrations.

## 11. Shared Spring configuration K1: class thứ nhất

`src/test/java/com/example/cachelab/ReuseFirstTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
class ReuseFirstTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;

    @Test
    void calculatesWithSpringBean() {
        assertEquals(240L, service.totalCents(120, 2));
    }

    @Test
    void receivesContextMarker() {
        assertTrue(marker.ordinal() > 0);
    }
}
```

Đây là 2 phương thức `@Test`. Key K1 chứa app class, environment NONE, test profile và imported config.

## 12. Shared Spring configuration K1: class thứ hai

`src/test/java/com/example/cachelab/ReuseSecondTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
class ReuseSecondTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;

    @Test
    void handlesZeroQuantity() {
        assertEquals(0L, service.totalCents(120, 0));
    }

    @Test
    void usesValidMarkerInstance() {
        assertTrue(marker.ordinal() > 0);
    }
}
```

Đây là 2 phương thức `@Test`. Effective config giống class thứ nhất, nên có thể reuse K1 trong cùng test JVM nếu context vẫn ở cache. Không dùng static fields trao đổi marker giữa classes vì sẽ làm tests phụ thuộc execution order.

## 13. PropertyVariantTest: thêm property tạo K2

`src/test/java/com/example/cachelab/PropertyVariantTest.java`:

```java
package com.example.cachelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ContextSuiteApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(ContextProbeConfig.class)
@TestPropertySource(properties = "lab.variant=extra")
class PropertyVariantTest {

    @Autowired TotalsService service;
    @Autowired ContextMarker marker;
    @Autowired Environment environment;

    @Test
    void seesAdditionalProperty() {
        assertEquals(
                "extra",
                environment.getProperty("lab.variant"));
    }

    @Test
    void stillUsesRealService() {
        assertEquals(1000L, service.totalCents(250, 4));
        assertTrue(marker.ordinal() > 0);
    }
}
```

Đây là 2 phương thức `@Test`. Class vẫn dùng profile `test` nhưng **`@TestPropertySource` khác** nên key K2. Một project chạy 3 Spring test classes trong cùng JVM, cache đủ chứa K1/K2 và không có DirtyContext có kỳ vọng **hai context creations**, không phải số đã đo.

## 14. Kiểm kê methods và cách hiểu

| Class | `@Test` methods | Context |
| --- | ---: | --- |
| TotalsServiceUnitTest | 2 | Không |
| ReuseFirstTest | 2 | K1 |
| ReuseSecondTest | 2 | K1 |
| PropertyVariantTest | 2 | K2 |
| **Tổng** | **8** | 3 classes Spring |

**8 phương thức `@Test`** tính từ mã, không phải “8 tests PASSED”. Không có parameterized tests. Nếu JUnit task fail ở compilation/dependency resolution thì không nhất thiết sinh XML. Chỉ sau khi chạy và đọc report mới có kết quả.

## 15. Chạy suite với cache mặc định

Linux/macOS:

```bash
./gradlew --no-daemon clean test \
  -PcontextCacheSize=32 --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --no-daemon clean test -PcontextCacheSize=32 --console=plain
```

Sau khi chạy:
1. Tìm `CTX_CREATED pid=... ordinal=...` trong output.
2. Tìm DEBUG stats của `org.springframework.test.context.cache`.
3. Đọc `TEST_SUMMARY cases=... passed=... failed=... skipped=... elapsedMs=...`.
4. Xem Gradle HTML tại `build/reports/tests/test/index.html`.
5. Xem JUnit XML tại `build/test-results/test/TEST-*.xml`.

Mỗi loại bằng chứng có scope khác nhau. Không cộng các cache lookup snapshots để lấy số context, và không gọi elapsed của Gradle Test task là toàn bộ build time.

## 16. Đo wall clock mà vẫn giữ exit code lỗi

Bash:

```bash
set -o pipefail
/usr/bin/time -p ./gradlew --no-daemon clean test \
  -PcontextCacheSize=32 --console=plain 2>&1 |
  tee suite-context.log
```

`set -o pipefail` ngăn `tee` che exit status của Gradle. Log đặt ngoài `build` để không bị `clean` xóa.

PowerShell:

```powershell
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& .\gradlew.bat --no-daemon clean test -PcontextCacheSize=32 --console=plain
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("SUITE_WALL_MS=" + $sw.ElapsedMilliseconds)
exit $code
```

Đồng hồ shell gồm build setup/compile/test/report, không phải riêng context cold start. Nếu tests chỉ được chạy từ task UP-TO-DATE, phép đo không tương đương full run.

## 17. Đọc JUnit XML để tìm slow cases

Tạo `scripts/summarize_junit.py`:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

files = sorted(
    Path("build/test-results/test").glob("TEST-*.xml")
)
if not files:
    print("No JUnit XML found; check test task execution.")
    sys.exit(2)

cases = []
fail_count = 0
skip_count = 0

for file in files:
    try:
        root = ET.parse(file).getroot()
    except ET.ParseError as error:
        print(f"Invalid report {file}: {error}")
        sys.exit(2)

    for case in root.iter("testcase"):
        seconds = float(case.get("time", "0") or "0")
        clazz = case.get("classname", file.stem)
        name = case.get("name", "unknown")
        failure = (
            case.find("failure") is not None
            or case.find("error") is not None
        )
        skipped = case.find("skipped") is not None
        cases.append((seconds, clazz, name))
        fail_count += int(failure)
        skip_count += int(skipped)

print("XML_FILES=", len(files))
print("TESTCASES=", len(cases))
print("FAILED_OR_ERROR=", fail_count)
print("SKIPPED=", skip_count)
print(
    "REPORTED_CASE_SECONDS_SUM=",
    round(sum(row[0] for row in cases), 3),
)
print("SLOWEST_CASES:")
for seconds, clazz, name in sorted(cases, reverse=True)[:10]:
    print(f"{seconds:.3f}s {clazz}#{name}")
```

Chạy:

```bash
python3 scripts/summarize_junit.py
```

**Script không đo context count hoặc toàn bộ wall time**; tổng testcase durations do XML ghi không nhất thiết bao gồm startup và có thể lớn hơn wall clock khi tests chạy parallel. Không có XML vì `compileTestJava` fail thì script báo thiếu report, không thể kết luận zero test failures.

## 18. Thí nghiệm có kiểm soát

### A: cache size 32

```bash
./gradlew --no-daemon clean test -PcontextCacheSize=32 --console=plain
```

Kỳ vọng 2 context keys K1/K2 trong lab, không cần eviction vì maxSize32, nếu không có config khác phát sinh. Đọc marker và DEBUG để xác minh.

### B: cache size 1

```bash
./gradlew --no-daemon clean test -PcontextCacheSize=1 --console=plain
```

K1/K2 xen kẽ có thể gây eviction/reload. Nhưng nếu run order là K1 → K1 → K2, có thể vẫn chỉ hai creations; nếu K1 → K2 → K1 thì có thể ba. **Không hardcode số context creations từ maxSize khi chưa biết class order.**

### C: làm các configs khác nhau

Trong sandbox, thêm `@TestPropertySource(properties="lab.variant=other")` vào ReuseSecondTest rồi chạy lại; nó không còn cùng key K1. Sau đó khôi phục và so kết quả.

### D: thử @DirtiesContext

Chỉ trong sandbox, đánh dấu `@DirtiesContext(classMode=AFTER_CLASS)` ở một class. Nếu class sau cần lại key bị invalidated, Spring nạp lại. Kết quả phụ thuộc thứ tự; không coi DirtiesContext là một property thay cache maxSize.

**Mỗi thí nghiệm chỉ đổi một biến.** Ghi cùng test set, JDK/Gradle versions, forks, CPU/RAM và số tests executed.

## 19. Nguồn làm phân mảnh cache key

| Khác biệt | Ảnh hưởng |
| --- | --- |
| `@ActiveProfiles` khác | Có thể tạo cache key khác |
| `@TestPropertySource` khác | Inline property locations/values tham gia key |
| `@SpringBootTest(properties=...)` khác | Boot config metadata khác |
| `@MockBean` hoặc `@SpyBean` khác | TestContext customizers khác |
| `@DynamicPropertySource` methods khác | Context customizers có thể khác |
| Nested `@TestConfiguration` riêng mỗi class | Config class identities khác |
| `@Import` khác | Bean/config scope khác |
| `@WebMvcTest` và `@SpringBootTest` | Slice/full context khác |
| `RANDOM_PORT` vs `NONE` | Web environment khác |
| `@DirtiesContext` | Không chỉ đổi key; invalidates context |
| Test class name khác | Không tự là key mới |
| Gradle fork khác | Static cache hoàn toàn khác JVM |

**Không ép mọi config giống nhau nếu business contract cần khác.** Một integration test có test profile đặc biệt để disable real scheduler hoặc dùng DB isolation riêng không nên bỏ profile chỉ vì mục tiêu “tăng cache hit”.

## 20. @MockBean và shared configuration

Spring Boot 3.3 `@MockBean` tạo/thay bean trong ApplicationContext; tập mocked beans là context customizer. Hai classes mock những collaborators khác nhau có thể cần hai contexts. Không nên tạo mega configuration với hàng chục mocks để ép dùng chung một context.

`@MockBean` được Boot reset theo test lifecycle, thường mặc định sau mỗi method, nhưng **reset mock không xóa SQL rows, Kafka messages, Redis keys, hay singleton state khác**. Khi share context, test data phải được cleanup đúng tầng.

Với logic service thuần, dùng JUnit + MockitoExtension không Spring. Với MVC, dùng `@WebMvcTest` và mocked controller collaborator. Với full integration, dùng `@SpringBootTest` khi thực sự cần wiring rộng.

## 21. @DirtiesContext và chuyện cleanup

`@DirtiesContext` đóng và remove context khỏi cache. Dùng nó khi test thay bean definitions hoặc corrupt singleton state không thể reset an toàn. Nếu chỉ có DB fixture, thường nên dùng rollback/cleanup theo namespace thay vì rebuild toàn bộ app.

Không tự xóa tất cả DirtiesContext để tối ưu: nó có thể đang bảo vệ một state leak thật. Tìm nguồn rò và thiết kế reset/ownership tương đương trước.

Trong parallel execution, một thread invalidating context có thể ảnh hưởng thread khác đang dùng nó. Không bật JUnit parallel cho classes dùng `@DirtiesContext` hoặc shared mocks/DB state chưa cô lập.

## 22. @DynamicPropertySource và Testcontainers

Một test dùng PostgreSQLContainer có thể đăng ký JDBC URL:

```java
@DynamicPropertySource
static void database(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

**Đây là snippet mở rộng**, cần khai báo `PostgreSQLContainer<?> postgres` cùng imports, Testcontainers dependency và lifecycle đúng; không nằm trong project lab.

Rủi ro:
- `@DynamicPropertySource` methods là context customizers, có thể phân mảnh cache.
- Static JUnit `@Container` per class có thể bị dừng sau class, trong khi Spring context vẫn cached và giữ DataSource tới cổng cũ.
- `@ServiceConnection` của Boot 3.3 giảm cấu hình kết nối thủ công nhưng không tự giải quyết vòng đời container/context.
- Shared DB cần schema/row namespace và cleanup; context caching không tạo data isolation.
- Testcontainers JUnit Jupiter extension chính thức không hỗ trợ chạy parallel extension; không dùng `@Execution(CONCURRENT)` trên `@Testcontainers` class như một cách benchmark supported.

Cần align container lifetime với context lifetime, hoặc dùng per-class context invalidation khi thật sự cần, rồi đo lại.

## 23. Gradle forks, parallel threads và multi-module

`maxParallelForks=1` có thể giúp các class dùng cùng Spring context share cache. `maxParallelForks=4` tạo nhiều test JVMs, mỗi JVM load contexts độc lập; đôi khi tổng wall time giảm nhờ parallel throughput nhưng memory/context starts tăng. `forkEvery=1` thường làm mất reuse giữa classes và tốn JVM startup. JUnit `parallel.enabled=true` là **thread-level concurrency trong một JVM**, khác với Gradle process forks.

Nhiều Gradle Test tasks, modules hoặc CI shards cũng không chia static Spring cache. Khi tổng hợp, nhóm logs theo worker PID, task/module và JUnit report. Không lấy cache stats của một worker rồi gán cho cả pipeline.

## 24. Tối ưu đúng thứ tự

1. **Xác định scope**: task(s), test classes, JDK/Gradle/Boot version, CI resources.
2. **Đo baseline**: marker creations/PID, cache stats, wall time, task elapsed, JUnit counts.
3. **Tìm bottleneck**: context startup, SQL, network, fixture, compilation hay GC?
4. **Chuyển unit-style tests khỏi @SpringBootTest** khi không cần Spring.
5. **Dùng slices** như `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest` đúng contract.
6. **Chuẩn hóa config** cho nhóm tests thực sự cùng intent: profiles, imported TestConfiguration, mock policy.
7. **Giảm @DirtiesContext** chỉ sau khi có cleanup state an toàn.
8. **Align Testcontainers lifecycle** với context reuse.
9. **Tuning maxSize/forks/parallel** khi measurements chứng minh có lợi và memory đủ.
10. **Chạy full suite** với test coverage, pass/failed/skipped counts và flaky rate không xấu đi.

Một full context được cache một lần nhưng startup nặng có thể chậm hơn ba nhỏ slices. Mục tiêu là **total cost đúng đắn**, không phải ít context bất chấp.

## 25. Failure threshold của Spring Framework 6.1

Spring TestContext 6.1 có context failure threshold mặc định **1**. Nếu một lần load context cho key K thất bại, các classes sau cần K có thể fail-fast mà không thử startup đầy đủ thêm lần nữa.

Tên property:

```properties
spring.test.context.failure.threshold=1
```

Khi điều tra, phân biệt lỗi gốc `Failed to load ApplicationContext` với các `ApplicationContext failure threshold exceeded` sau đó. Đừng gọi suite fail-fast là “context optimization”, và đừng tăng threshold để che bean/config/DB startup error.

## 26. Checklist trước và sau tối ưu

- [ ] Cùng code revision, JDK, Gradle, Spring Boot và test task selection?
- [ ] Cùng số testcase executed, passed, failed, skipped?
- [ ] Có marker count theo PID và cache stats?
- [ ] Cache maxSize được truyền vào test worker JVM?
- [ ] Đã phân biệt Gradle test task time và total wall clock?
- [ ] Không dùng JUnit XML time làm exact startup timer?
- [ ] Đã điều tra @TestPropertySource/@MockBean/@DynamicPropertySource differences?
- [ ] Chỉ dùng @DirtiesContext khi context thật sự dirty?
- [ ] Unit tests có thể chạy không Spring khi phù hợp?
- [ ] Slices vẫn bảo vệ MVC/JPA/JSON/security contract?
- [ ] Không tắt filters/auth hoặc bỏ integration coverage để tăng tốc?
- [ ] Database/topics/Redis/filesystem có test-specific namespaces?
- [ ] Testcontainers context/container lifecycle được kiểm soát?
- [ ] Không bật unsupported extension parallel hoặc shared mock race?
- [ ] Memory/GC được kiểm tra trước khi tăng cache size/forks?
- [ ] Có chạy nhiều samples, so median và biến thiên?
- [ ] Có regression QA và rollback plan?
- [ ] Không tuyên bố tests PASS nếu chưa chạy thực tế?

## 27. Tài liệu chính thức

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): key, static cache, size32, LRU và DEBUG.
- [Spring Framework 6.1 — ContextCache Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/context/cache/ContextCache.html): hits/misses/size.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): failure threshold mặc định 1.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): invalidation.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): safety với shared state.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest, @TestConfiguration, slices.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): @ServiceConnection.
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): @Container lifecycle, parallel extension limitation.
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test worker forks, reports, logging.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): task profiling/parallel tuning.
- [JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/): lifecycle/parallel execution.
- [Python ElementTree](https://docs.python.org/3/library/xml.etree.elementtree.html): parse XML.

## 28. Kết luận

**Tối ưu Spring Boot test suite phải dựa trên hai nhóm bằng chứng: context lifecycle và thời gian thực thi.** Spring TestContext cache là static trong từng JVM, keyed theo merged configuration, default tối đa 32 contexts với LRU. Profiles, inline properties, mocks, dynamic properties, DirtiesContext và Gradle forks đều có thể ảnh hưởng reuse.

Project Java 17+/Boot 3.3.5 minh họa **8 phương thức @Test**: hai unit tests không cần Spring, hai classes có cùng K1 và một class có K2 do inline property. Bean `ContextMarker` giúp quan sát số context creations per JVM, còn Gradle summary, JUnit reports và shell stopwatch đo các phạm vi thời gian khác nhau. Đây là mã hướng dẫn, **không phải tuyên bố Gradle/JUnit đã PASS khi chưa chạy**.

Một tối ưu chỉ thành công khi wall time/resource cost giảm qua phép đo công bằng **và** mọi business/integration assertions, test isolation, pass/fail/skip counts vẫn được bảo vệ.
