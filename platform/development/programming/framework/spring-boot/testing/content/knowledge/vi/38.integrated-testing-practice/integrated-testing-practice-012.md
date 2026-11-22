# Chạy bộ kiểm thử trên CI và điều tra một lỗi chỉ xuất hiện khi chạy song song

## 1. Mục tiêu của bài thực hành tích hợp

Trong module **Spring Boot - testing**, nhóm **Thực hành tích hợp**, bài này mô phỏng một sự cố thực tế: unit tests và Spring Boot integration tests PASS khi chạy tuần tự trên máy lập trình viên; sau khi CI cho chạy JUnit song song, một phép kiểm giỏ hàng bất ngờ đọc giá trị của khách khác. Chạy riêng test vừa FAIL lại thường PASS. Mục tiêu là **thu thập chứng cứ, tái hiện race một cách có kiểm soát, sửa nguyên nhân nghiệp vụ và kiểm tra lại trong CI**, thay vì tăng timeout hoặc tắt hết parallelism.

~~~text
Dev: ./gradlew test                         -> PASS
Dev: ./gradlew integrationTest (serial)     -> thường PASS
CI:  ./gradlew integrationTest (parallel)   -> thỉnh thoảng FAIL
                       |
                       v
   Hai JUnit methods / request workers cùng sử dụng
   Spring @Singleton bean chứa mutable currentCustomer
                       |
                       v
   A ghi "alpha" -> B ghi "beta" -> A đọc "beta"
                       |
                       v
   Root cause: per-request identity bị lưu ở shared field
~~~

**Phân biệt bằng chứng với giả thuyết:** CI-only không mặc định là data race. Lỗi chỉ xuất hiện trên runner còn có thể do Docker, timezone, file path, network quota, order-dependent tests, PostgreSQL transaction, clock, test filter hoặc cấu hình JVM. Phải làm thí nghiệm thay đổi một yếu tố và có logs/artifacts đủ để phân biệt.

Bài có project **Java 17, Spring Boot 3.5.16, Gradle 8.14.x, JUnit Jupiter, Mockito và AssertJ**, chia `test` nhanh với `integrationTest` dùng Spring context thật. Có đúng **5 lớp test, 10 JUnit test methods**: 4 unit và 6 integration. Một test dùng `CountDownLatch` cố ý **chứng minh bug** của singleton sai: nó PASS khi quan sát lỗi, không được diễn giải là dịch vụ lỗi đã an toàn. Các tests còn lại xác nhận bản sửa bằng **stateless singleton + state phân vùng theo ID + atomic per-key operation**.

Kết quả đã được nêu là **dự kiến theo mã**, không phải Gradle/JUnit logs đã quan sát trong lúc biên soạn.

## 2. Phân biệt bốn cấp độ chạy song song

| Cấp độ | Cấu hình | Tài nguyên được chia sẻ |
| --- | --- | --- |
| Gradle task parallelism | `./gradlew --parallel` | Các tasks/subprojects có thể đồng thời |
| Gradle forked test JVMs | `Test.maxParallelForks=2` | Mỗi fork có JVM/static/Spring cache riêng; external DB vẫn có thể chung |
| JUnit Jupiter threads trong JVM | `junit.jupiter.execution.parallel.enabled=true` | Các tests có thể cùng Spring `ApplicationContext`/singleton |
| CI matrix/shards nhiều runner | Nhiều jobs/nodes | JVM khác nhau; DB/topic/bucket/Redis key prefix có thể trùng |
| Worker của ứng dụng | `@Async`, HTTP servlet, Kafka listener | Không chịu lịch điều phối của Jupiter; có thể vẫn concurrent khi JUnit serial |

**`maxParallelForks=1` không tắt JUnit parallel.** Nó chỉ giới hạn số forked JVM cho một Test task. Trong một fork, Jupiter có thể dùng bốn threads theo `junit-platform.properties`. Ngược lại `junit.jupiter.execution.parallel.enabled=false` không ngăn servlet worker hoặc executor được test tạo.

Vì race ở bài này cần **cùng Spring singleton**, cấu hình mẫu giữ `maxParallelForks=1` để JUnit tests gặp cùng `ApplicationContext` cache. Nếu tăng forks, bug có thể bị che vì các test classes bị phân vào JVM khác, nhưng không hề làm business code an toàn hơn.

## 3. Checklist thu thập chứng cứ khi CI đỏ

Ghi lại trước khi rerun:

1. Commit SHA, CI job/run, Gradle Wrapper, Java runtime và hệ điều hành.
2. Task `test` hay `integrationTest`; tên test class/method, assertion failure, stack trace nguyên gốc.
3. JUnit parallel properties/`@Execution`, Gradle forks và CI shard identifier.
4. Spring active profile, context config/cache, bean identity và bean overrides.
5. Owner key của dữ liệu, file path, schema, topic, queue, container IDs nếu có.
6. `@BeforeEach`/`@AfterEach`, timestamps tương đối và background work còn chạy.
7. JUnit XML/HTML của task fail và log thread/owner key.
8. Thay đổi gần đây ở mock reset, `@DirtiesContext`, cleanup, Gradle dependency hoặc CI runner.

Một test PASS khi rerun chỉ là **dấu hiệu lỗi khó tái hiện**, không phải bằng chứng fix. Hãy lưu artifacts của lần fail đầu, sau đó mới lập phép thử controlled.

## 4. Spring TestContext cache và singleton

JUnit mặc định `@TestInstance(PER_METHOD)`: mỗi test method có một test instance riêng. Điều này **không tạo Spring beans riêng**. Khi `@SpringBootTest` của hai classes có context configuration giống nhau, Spring TestContext có thể cache và reuse `ApplicationContext` trong cùng JVM:

~~~text
JUnit test A instance ──┐
                        ├─ cached ApplicationContext
JUnit test B instance ──┘       |
                                +-- CheckoutService @Service singleton
                                +-- CartBalances @Component singleton
                                +-- UnsafeUserSession @Component singleton
                                              |
                                              +-- volatile currentCustomer
~~~

Nếu test A thực hiện `session.enter("alpha")` rồi test B gọi `enter("beta")`, A có thể đọc lại `"beta"`. `volatile` bảo đảm visibility của write nhưng không tạo bản sao field theo request. `AtomicReference` cũng không tự giải quyết vì vẫn là **một vị trí shared**. `@BeforeEach` gọi `clear()` lên singleton còn có thể xóa state test khác đang dùng.

Hai vấn đề riêng:
- **Thread safety:** hai threads thêm vào cùng key không lost update.
- **Isolation:** hai tests có unique keys và chỉ cleanup dữ liệu của mình.

Một `ConcurrentHashMap` có thread-safe operations vẫn bị cross-test leak nếu mọi test dùng cùng key `"test"`. Phải giải quyết cả hai.

## 5. Các dấu hiệu phân biệt root cause

| Dấu hiệu | Nghi vấn | Cách xác minh |
| --- | --- | --- |
| FAIL khi Jupiter concurrent, PASS tuần tự | Bean/static/mock/shared resource race | Log owner + thread; latches dựng interleaving |
| FAIL tuần tự nhưng phụ thuộc test chạy trước | State leak hoặc cleanup thiếu | Chạy cặp tests ở nhiều thứ tự |
| Mockito too-many-invocations | Cùng mock dùng bởi nhiều tests | So context/mock identity và reset lifecycle |
| ApplicationContext no longer active | `@DirtiesContext`, cache eviction | Spring TestContext cache logs |
| Dữ liệu DB còn dù test @Transactional | HTTP/async thread có transaction khác | Xác minh commit và cleanup owner |
| CI shard nào cũng có rows lạ | Shared external schema/topic | Tạo namespace theo run/shard |
| Chỉ CI thiếu Docker | Testcontainers không khởi động | Kiểm engine, container logs, readiness |
| Chỉ fail một timezone | Clock/DST/locale | Inject Clock hoặc cấu hình test clock rõ |
| Local PASS, runner nhỏ timeout | CPU/RAM/network bottleneck | Time budgets, CI resource usage |
| `NO-SOURCE`/0 tests | Sai source set/test task | XML counts, testClassesDirs, runtime classpath |

Đừng "chữa" mọi lỗi bằng `Thread.sleep`: nó thay xác suất scheduling, không xây dựng synchronization contract.

## 6. Kiến trúc lab và số lượng test chính xác

~~~text
Anti-pattern để chẩn đoán:
  UnsafeUserSession @Component
      volatile currentCustomer
      enter(String); currentCustomer()
  RacySessionInvestigationTest
      A enter alpha -> B enter beta -> A read beta
      -> test PASS vì chứng minh lỗi tái hiện

Bản sửa:
  CheckoutService @Service (không có customer field)
      addItem(customerId,sku)
        -> DefaultPriceGateway (stateless)
        -> CartBalances @Component
              ConcurrentHashMap<customerId,total>
              compute() per key atomic
  Test fixtures: customerId UUID riêng mỗi method
  Cleanup: remove(ID của chính test)
~~~

| Task | Class | Số `@Test` methods |
| --- | --- | ---: |
| `test` | `CheckoutServiceUnitTest` | 2 |
| `test` | `CartBalancesConcurrencyTest` | 2 |
| `integrationTest` | `RacySessionInvestigationTest` | 1 |
| `integrationTest` | `SafeCheckoutParallelTest` | 3 |
| `integrationTest` | `SafeCheckoutOtherClassTest` | 2 |
| **Tổng** | **5 test classes** | **10 methods** |

**Không có test cố ý FAIL trong suite mặc định.** Red assertion để chứng minh bug trước fix nằm ở phần giải thích riêng, không phải file runnable, để pipeline mặc định có thể xanh khi bộ test chẩn đoán hoạt động đúng.

## 7. Cấu trúc file

~~~text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties

src/main/java/com/example/parallellab/
  ParallelCiApplication.java
  PriceGateway.java
  DefaultPriceGateway.java
  CartBalances.java
  CheckoutService.java
  UnsafeUserSession.java
src/main/resources/application.properties

src/test/java/com/example/parallellab/
  CheckoutServiceUnitTest.java
  CartBalancesConcurrencyTest.java

src/integrationTest/java/com/example/parallellab/
  RacySessionInvestigationTest.java
  SafeCheckoutParallelTest.java
  SafeCheckoutOtherClassTest.java
src/integrationTest/resources/
  junit-platform.properties
  application-it.properties

.github/workflows/java-test-ci.yml
~~~

Integration tests dùng source set riêng để unit task không khởi động Spring. Hai tasks có JUnit XML/HTML report độc lập. Source code Java và Gradle được viết đủ file/package/imports để có thể tạo project minh họa; wrapper scripts/JAR được Gradle Wrapper sinh, không chép các binary vào README.

## 8. Gradle build: hai task và một công tắc JUnit parallel

**`settings.gradle`:**

~~~groovy
rootProject.name = 'spring-parallel-ci-lab'
~~~

**`build.gradle`:**

~~~groovy
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}

tasks.register('integrationTest', Test) {
    description = 'Spring integration and concurrency tests'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()

    maxParallelForks = 1
    shouldRunAfter(tasks.named('test'))

    systemProperty 'junit.jupiter.execution.parallel.enabled',
        (project.findProperty('itParallel') ?: 'true').toString()

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
        showStandardStreams = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

**Giải thích wiring:**
- `integrationTest` source set được Java plugin tạo compile task và resource task riêng.
- `integrationTestImplementation` kế thừa **libraries** của `testImplementation`, không tự trộn source output của `src/test/java`.
- `testClassesDirs` và `classpath` phải trỏ chính xác integration source set, không dựa vào convention của built-in test task.
- `useJUnitPlatform()` bật JUnit Jupiter discovery.
- `maxParallelForks=1` giữ một test JVM; Jupiter threads vẫn có thể concurrent.
- `project.findProperty('itParallel')` nhận `-PitParallel=true|false`, rồi gửi system property **vào forked test JVM**, không chỉ Gradle daemon.
- `shouldRunAfter(test)` chỉ là ordering rule; `check.dependsOn(integrationTest)` mới đưa integration task vào lifecycle.
- `reports` lưu JUnit XML/HTML độc lập cho task.

### Gradle Wrapper và Java

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
~~~

PowerShell:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
~~~

Spring Boot 3.5.16 công bố hỗ trợ Gradle 7.6.4+ trong dòng 7 hoặc 8.4+ trong dòng 8, Java 17+. Chọn Gradle 8.14.3 ở đây và dùng **Wrapper** cho cả local/CI; không tự nâng Boot3.5 sang Gradle9 rồi tuyên bố được hỗ trợ.

## 9. JUnit properties chỉ dành cho integrationTest

**`src/integrationTest/resources/junit-platform.properties`:**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

Với JUnit Jupiter, bật `parallel.enabled` là bước đầu; `mode.default`/`mode.classes.default` quy định classes/methods nào có thể concurrent. Bài chọn fixed parallelism 4 để dễ đo và quan sát.

`Test` task đặt system property `junit.jupiter.execution.parallel.enabled`, nên `-PitParallel=false` có thể **override property trong file** cho forked JVM. Hai phép thử:

~~~bash
./gradlew integrationTest -PitParallel=false --rerun-tasks
./gradlew integrationTest -PitParallel=true --rerun-tasks
~~~

Lưu ý: bài chẩn đoán race còn **tự sinh threads qua ExecutorService** trong một `@Test`; nó vẫn ép interleaving khi Jupiter scheduling tuần tự. Công tắc chỉ điều khiển **lịch JUnit test nodes**, không được hiểu là một công tắc tắt toàn bộ business concurrency.

## 10. Application + profile test

**`src/main/java/com/example/parallellab/ParallelCiApplication.java`:**

~~~java
package com.example.parallellab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelCiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelCiApplication.class, args);
    }
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
spring.main.banner-mode=off
logging.level.com.example.parallellab=INFO
~~~

**`src/integrationTest/resources/application-it.properties`:**

~~~properties
lab.integration-mode=true
~~~

Các Spring integration tests dùng `@ActiveProfiles("it")`. Property `lab.integration-mode` giúp xác minh file resources của `integrationTest` nằm trên runtime classpath; nó không phải một boolean business flag. Không đặt secrets production trong profile test.

## 11. PriceGateway và implementation stateless

**`src/main/java/com/example/parallellab/PriceGateway.java`:**

~~~java
package com.example.parallellab;

public interface PriceGateway {
    long unitPriceCents(String sku);
}
~~~

**`src/main/java/com/example/parallellab/DefaultPriceGateway.java`:**

~~~java
package com.example.parallellab;

import org.springframework.stereotype.Component;

@Component
public class DefaultPriceGateway implements PriceGateway {

    @Override
    public long unitPriceCents(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank"
            );
        }

        return switch (sku) {
            case "pen" -> 100L;
            case "book" -> 400L;
            default -> throw new IllegalArgumentException(
                    "Unknown sku: " + sku
            );
        };
    }
}
~~~

Bean này stateless, không nhớ tên khách hay các calls trước. Integration tests dùng real gateway; unit tests sẽ tạo Mockito mock riêng, không dùng `@MockitoBean` chia sẻ trong cached Spring context.

## 12. CartBalances: state theo customerId và atomic compute

**`src/main/java/com/example/parallellab/CartBalances.java`:**

~~~java
package com.example.parallellab;

import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;

@Component
public class CartBalances {

    private final ConcurrentMap<String, Long> totals =
            new ConcurrentHashMap<>();

    public long add(String customerId, long cents) {
        if (customerId == null || customerId.isBlank()
                || cents <= 0) {
            throw new IllegalArgumentException(
                    "invalid customer or amount"
            );
        }

        return totals.compute(
                customerId,
                (key, oldValue) -> Math.addExact(
                        oldValue == null ? 0L : oldValue,
                        cents
                )
        );
    }

    public long total(String customerId) {
        Objects.requireNonNull(customerId);
        return totals.getOrDefault(customerId, 0L);
    }

    public void remove(String customerId) {
        Objects.requireNonNull(customerId);
        totals.remove(customerId);
    }
}
~~~

`ConcurrentHashMap.compute` hỗ trợ atomic remapping theo key, tránh lost update của hai threads đồng thời cùng thêm vào một cart. Nhưng nó **không phải distributed data store** và không tự ngăn test A xóa nhầm key test B. Mỗi test phải có unique owner key và chỉ cleanup own data.

Ví dụ cùng key: 6 workers × 50 lần add 1 cent phải cho **300 cents**. Ví dụ hai keys A/B: A có thể được remove mà B vẫn giữ nguyên. Các ca này sẽ được kiểm rõ bằng unit tests bên dưới.

## 13. CheckoutService: fix request state đúng kiến trúc

**`src/main/java/com/example/parallellab/CheckoutService.java`:**

~~~java
package com.example.parallellab;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PriceGateway prices;
    private final CartBalances balances;

    public CheckoutService(
            PriceGateway prices,
            CartBalances balances
    ) {
        this.prices = Objects.requireNonNull(prices);
        this.balances = Objects.requireNonNull(balances);
    }

    public long addItem(String customerId, String sku) {
        if (customerId == null || customerId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "invalid customer or sku"
            );
        }

        long cents = prices.unitPriceCents(sku);
        if (cents <= 0) {
            throw new IllegalArgumentException(
                    "price must be positive"
            );
        }
        return balances.add(customerId, cents);
    }

    public long total(String customerId) {
        return balances.total(customerId);
    }
}
~~~

Service này có thể là singleton vì nó chỉ lưu immutable references tới dependencies, không có field `currentCustomer`/`currentCart`. Identity được truyền ở mọi method call. Mutable data nằm trong store có scope key rõ và atomic update.

Nếu là tiền thật, cần database transaction, ledger và idempotency protection khi retry requests; in-memory map chỉ nhằm học concurrency isolation, không thay hệ thống thanh toán.

## 14. UnsafeUserSession: class lỗi để tái hiện và xác minh

**`src/main/java/com/example/parallellab/UnsafeUserSession.java`:**

~~~java
package com.example.parallellab;

import org.springframework.stereotype.Component;

/** PHAN VI DU: KHONG DUNG CHO PRODUCTION REQUESTS. */
@Component
public class UnsafeUserSession {

    private volatile String currentCustomer;

    public void enter(String customerId) {
        currentCustomer = customerId;
    }

    public String currentCustomer() {
        return currentCustomer;
    }

    public void clear() {
        currentCustomer = null;
    }
}
~~~

Với singleton này, hai lời gọi `enter` và `currentCustomer` **không tạo thành một transaction**. `volatile` chỉ làm write của B được thấy bởi A; nó không lưu được identity riêng của A. Dùng `AtomicReference<String>` hoặc synchronized từng method cũng không cứu được luồng `enter(A) → enter(B) → read(A)`.

Tại sao giữ class này trong project học? Để thấy rõ một test chẩn đoán có thể **tái hiện lỗi** bằng điều phối threads thay vì đợi CI thỉnh thoảng FAIL. Bản `CheckoutService` đã sửa **không sử dụng class này**.

## 15. Unit tests bằng MockitoExtension

**`src/test/java/com/example/parallellab/CheckoutServiceUnitTest.java`:**

~~~java
package com.example.parallellab;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceUnitTest {

    @Mock PriceGateway prices;

    private CheckoutService checkout;
    private CartBalances balances;
    private String customerId;

    @BeforeEach
    void setup() {
        balances = new CartBalances();
        checkout = new CheckoutService(prices, balances);
        customerId = "unit-" + UUID.randomUUID();
    }

    @Test
    void mockPriceAndStoreArePrivateToThisMethod() {
        when(prices.unitPriceCents("pen")).thenReturn(125L);

        assertThat(checkout.addItem(customerId, "pen"))
                .isEqualTo(125L);
        assertThat(checkout.total(customerId))
                .isEqualTo(125L);

        verify(prices).unitPriceCents("pen");
    }

    @Test
    void invalidPriceDoesNotMutateCart() {
        when(prices.unitPriceCents("pen")).thenReturn(0L);

        assertThatThrownBy(
                () -> checkout.addItem(customerId, "pen")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("price must be positive");

        assertThat(checkout.total(customerId)).isZero();
        verify(prices).unitPriceCents("pen");
    }
}
~~~

**Hai unit methods**. `MockitoExtension` tạo mock theo test lifecycle, còn `new CartBalances()` tạo store riêng. Vì không khởi động Spring, chúng không phụ thuộc cached ApplicationContext hoặc shared `@MockitoBean`. Nếu một business service chỉ cần kiểm hành vi thuần, ưu tiên dạng test này để giữ CI fast.

## 16. Unit tests cho thread safety và cách ly theo key

**`src/test/java/com/example/parallellab/CartBalancesConcurrencyTest.java`:**

~~~java
package com.example.parallellab;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CartBalancesConcurrencyTest {

    @Test
    void concurrentAddsToOneKeyAreAtomic()
            throws Exception {
        CartBalances balances = new CartBalances();
        ExecutorService pool = Executors.newFixedThreadPool(6);
        CountDownLatch ready = new CountDownLatch(6);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();
        String id = "stress-" + UUID.randomUUID();

        try {
            for (int worker = 0; worker < 6; worker++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "start timed out"
                        );
                    }
                    for (int i = 0; i < 50; i++) {
                        balances.add(id, 1L);
                    }
                    return null;
                }));
            }

            assertThat(ready.await(
                    5, TimeUnit.SECONDS
            )).isTrue();

            start.countDown();
            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertThat(balances.total(id))
                    .isEqualTo(300L);
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS
            )).isTrue();
        }
    }

    @Test
    void removeOneKeyCannotDeleteTheOtherKey() {
        CartBalances balances = new CartBalances();
        String a = "a-" + UUID.randomUUID();
        String b = "b-" + UUID.randomUUID();

        balances.add(a, 100L);
        balances.add(b, 400L);
        balances.add(a, 50L);

        assertThat(balances.total(a)).isEqualTo(150L);
        assertThat(balances.total(b)).isEqualTo(400L);

        balances.remove(a);

        assertThat(balances.total(a)).isZero();
        assertThat(balances.total(b)).isEqualTo(400L);
    }
}
~~~

**Hai unit methods.** Latch không đoán thread scheduling bằng sleep; mọi worker đều tới điểm ready rồi cùng được release. `Future.get(timeout)` truyền lại exception của task và giới hạn thời gian chờ. `finally` release latch, shutdown pool do test tạo, await termination trước khi thoát. Test này không chứng minh hình thức mọi interleavings nhưng có giá trị regression.

## 17. Spring integration test: deterministic reproducer của class lỗi

**`src/integrationTest/java/com/example/parallellab/RacySessionInvestigationTest.java`:**

~~~java
package com.example.parallellab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class RacySessionInvestigationTest {

    @Autowired UnsafeUserSession unsafe;
    @Autowired ApplicationContext context;

    @Test
    void forcedOverlapShowsAnotherCustomerInSingletonField()
            throws Exception {
        assertThat(context.getBean(UnsafeUserSession.class))
                .isSameAs(unsafe);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch alphaEntered = new CountDownLatch(1);
        CountDownLatch betaEntered = new CountDownLatch(1);

        try {
            Future<String> alpha = pool.submit(() -> {
                unsafe.enter("alpha");
                alphaEntered.countDown();
                if (!betaEntered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "beta entry timed out"
                    );
                }
                return unsafe.currentCustomer();
            });

            Future<String> beta = pool.submit(() -> {
                if (!alphaEntered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "alpha entry timed out"
                    );
                }
                unsafe.enter("beta");
                betaEntered.countDown();
                return unsafe.currentCustomer();
            });

            String observedByAlpha = alpha.get(
                    5, TimeUnit.SECONDS
            );
            String observedByBeta = beta.get(
                    5, TimeUnit.SECONDS
            );

            // PASS khi phát hiện BUG của class cố tình sai:
            assertThat(observedByAlpha).isEqualTo("beta");
            assertThat(observedByAlpha).isNotEqualTo("alpha");
            assertThat(observedByBeta).isEqualTo("beta");
        } finally {
            alphaEntered.countDown();
            betaEntered.countDown();
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    5, TimeUnit.SECONDS
            )).isTrue();
            unsafe.clear();
        }
    }
}
~~~

**Một integration method.** Latch ép A ghi trước B, rồi A chỉ đọc sau B. Kết quả A thấy `"beta"` là bằng chứng lỗi request-state shared. Bài test **PASS khi tái hiện lỗi**, vì mục tiêu của test này là diagnostic. Đừng hiểu PASS của diagnostic là production code an toàn.

Nếu muốn có **red regression** trước khi sửa, trong một nhánh thử nghiệm tạm đổi đúng assertion của A thành:

~~~java
// SNIPPET, KHÔNG đặt vào suite mặc định của ví dụ:
assertThat(observedByAlpha).isEqualTo("alpha");
~~~

Nó sẽ FAIL khi forced interleaving còn tồn tại, với expected alpha/actual beta. Sau khi refactor service thật không còn mutable request field, viết regression kiểm **service đã sửa** nhận đúng customer ID, thay vì giữ một assertion đỏ trên class anti-pattern.

**Giới hạn của toggle:** `-PitParallel=false` không tắt hai workers do method này tạo. Reproducer cố ý vẫn thấy bug; nó kiểm concurrency của code, không đo riêng scheduler của JUnit.

## 18. Spring integration tests của phiên bản đã sửa

**`src/integrationTest/java/com/example/parallellab/SafeCheckoutParallelTest.java`:**

~~~java
package com.example.parallellab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class SafeCheckoutParallelTest {

    private static final Logger log =
            LoggerFactory.getLogger(SafeCheckoutParallelTest.class);

    @Autowired CheckoutService checkout;
    @Autowired CartBalances balances;
    @Autowired Environment environment;

    private String customerId;

    @BeforeEach
    void setupOwnId(TestInfo info) {
        customerId = "it-" + UUID.randomUUID();
        log.info("START method={} owner={} thread={}",
                info.getDisplayName(), customerId,
                Thread.currentThread().getName());
    }

    @AfterEach
    void cleanupOwnId() {
        balances.remove(customerId);
        log.info("END owner={} thread={}",
                customerId,
                Thread.currentThread().getName());
    }

    @Test
    void penPriceBelongsOnlyToOwnCart() {
        assertThat(environment.getProperty(
                "lab.integration-mode"
        )).isEqualTo("true");

        assertThat(checkout.addItem(customerId, "pen"))
                .isEqualTo(100L);
        assertThat(checkout.total(customerId))
                .isEqualTo(100L);
    }

    @Test
    void bookPriceBelongsOnlyToOwnCart() {
        assertThat(checkout.addItem(customerId, "book"))
                .isEqualTo(400L);
        assertThat(checkout.total(customerId))
                .isEqualTo(400L);
    }

    @Test
    void anotherCustomerDoesNotChangeMyBalance() {
        String other = "it-second-" + UUID.randomUUID();

        try {
            checkout.addItem(customerId, "pen");
            checkout.addItem(other, "book");

            assertThat(checkout.total(customerId))
                    .isEqualTo(100L);
            assertThat(checkout.total(other))
                    .isEqualTo(400L);
        } finally {
            balances.remove(other);
        }
    }
}
~~~

**Ba methods** có `@Execution(CONCURRENT)`, mỗi test dùng UUID và chỉ remove own key. `JUnit PER_METHOD` mặc định khiến `customerId` trong test instance không bị hai methods dùng chung; `CheckoutService` và `CartBalances` là singleton dùng chung nhưng đúng contract.

Log có method, owner và thread để điều tra sau này. Khi parallel, thứ tự các dòng log **không cố định**, không nên assert trình tự log. Đừng log dữ liệu thanh toán hoặc PII thật.

## 19. Một integration class khác cùng app context

**`src/integrationTest/java/com/example/parallellab/SafeCheckoutOtherClassTest.java`:**

~~~java
package com.example.parallellab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Execution(ExecutionMode.CONCURRENT)
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class SafeCheckoutOtherClassTest {

    @Autowired CheckoutService checkout;
    @Autowired CartBalances balances;

    private final String customerId =
            "other-" + UUID.randomUUID();

    @AfterEach
    void cleanupOwnId() {
        balances.remove(customerId);
    }

    @Test
    void penAndBookAddToMyCart() {
        checkout.addItem(customerId, "pen");
        checkout.addItem(customerId, "book");

        assertThat(checkout.total(customerId))
                .isEqualTo(500L);
    }

    @Test
    void invalidSkuDoesNotMutateMyCart() {
        assertThatThrownBy(
                () -> checkout.addItem(customerId, "unknown")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Unknown sku");

        assertThat(checkout.total(customerId)).isZero();
    }
}
~~~

**Hai methods**. Chúng có thể chạy đồng thời với `SafeCheckoutParallelTest` trong cùng JVM và cùng cached Spring context (khi cấu hình cache key tương đương). Tests không assert context identity như một giá trị cố định; chúng assert invariant nghiệp vụ đúng dù context reuse hoặc reload.

Một failure chỉ lộ khi cả hai classes đồng thời thường là dấu hiệu chúng cùng dùng resource nhưng không có namespace. Hãy kiểm mọi `@AfterEach` có xóa chỉ ID do test tạo hay không.

## 20. Đếm tests và kết quả dự kiến một lần nữa

| Class | Task | Methods | Dự kiến |
| --- | --- | ---: | --- |
| CheckoutServiceUnitTest | test | 2 | Giá mock 125, giá 0 bị từ chối |
| CartBalancesConcurrencyTest | test | 2 | Atomic 6×50=300, remove A giữ B |
| RacySessionInvestigationTest | integrationTest | 1 | Alpha nhìn thấy Beta do anti-pattern |
| SafeCheckoutParallelTest | integrationTest | 3 | Pen100, Book400, owner data riêng |
| SafeCheckoutOtherClassTest | integrationTest | 2 | Pen+Book500, unknown SKU giữ 0 |
| **Tổng** | **2 tasks** | **10** | **4 unit, 6 integration** |

Con số này khớp số `@Test` method trong code. Không có `@ParameterizedTest`, `@Disabled` hoặc test giả intentionally failing trong runnable suite. CI thực tế vẫn có thể FAIL vì môi trường/compile/code issue; không được báo "10 tests PASS" khi chưa thực thi.

## 21. Lệnh chạy ba phép thử có kiểm soát

**Unit nhanh:**

~~~bash
./gradlew clean test
~~~

**Integration Jupiter tuần tự:**

~~~bash
./gradlew integrationTest -PitParallel=false --rerun-tasks
~~~

**Integration Jupiter song song:**

~~~bash
./gradlew integrationTest -PitParallel=true --rerun-tasks
~~~

**Chọn đúng test class:**

~~~bash
./gradlew integrationTest \
  --tests "com.example.parallellab.RacySessionInvestigationTest" \
  -PitParallel=true --rerun-tasks

./gradlew integrationTest \
  --tests "com.example.parallellab.SafeCheckoutParallelTest" \
  -PitParallel=true --rerun-tasks
~~~

**Toàn bộ lifecycle:**

~~~bash
./gradlew clean check -PitParallel=true --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat integrationTest -PitParallel=false --rerun-tasks
.\gradlew.bat integrationTest -PitParallel=true --rerun-tasks
.\gradlew.bat integrationTest --tests "com.example.parallellab.RacySessionInvestigationTest" -PitParallel=true --rerun-tasks
.\gradlew.bat clean check -PitParallel=true --stacktrace
~~~

`--rerun-tasks` yêu cầu Gradle thực thi lại tasks để tránh diễn giải up-to-date/cache output thành một lần test chạy mới. Nếu muốn chạy một test method cụ thể, dùng `--tests "fully.qualified.Class.method"` đúng **Test task**, không tìm class ở source set khác.

## 22. GitHub Actions workflow lưu artifacts kể cả khi FAIL

**`.github/workflows/java-test-ci.yml`:**

~~~yaml
name: java-test-ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Show Java and Gradle version
        run: |
          java -version
          ./gradlew --version

      - name: Run unit tests
        run: ./gradlew --no-daemon test --stacktrace

      - name: Run integration tests with parallel Jupiter
        run: ./gradlew --no-daemon integrationTest -PitParallel=true --rerun-tasks --stacktrace

      - name: Upload test evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-test-reports
          path: |
            build/test-results/test/
            build/test-results/integrationTest/
            build/reports/tests/test/
            build/reports/tests/integrationTest/
          if-no-files-found: warn
~~~

Workflow minh họa, cần thực hiện theo policy GH Actions của tổ chức (review/pin SHA và nâng major action khi phù hợp). Step unit FAIL sẽ khiến integration step sau bị skip mặc định, nhưng `if: always()` vẫn upload reports đã tồn tại. Không dùng `continue-on-error: true` để che lỗi integration.

Nếu tests thực sự dùng Docker/Testcontainers, runner phải có engine/permissions và image readiness; mẫu này không cần Docker. Với CI shards nhiều runner, dùng namespace riêng cho external database/topics/Redis keys thay vì giả định JUnit @ResourceLock có thể khóa xuyên jobs.

## 23. Test reports: cách biết CI đã thực sự chạy bài nào

Gradle Test task có XML và HTML report. Với tên task ở project:

~~~text
build/test-results/test/                    (unit XML)
build/reports/tests/test/                   (unit HTML)
build/test-results/integrationTest/         (IT XML)
build/reports/tests/integrationTest/        (IT HTML)
~~~

Dự kiến `test` có **4** cases và `integrationTest` có **6**. Trên CI, phải kiểm:
- Tasks không `NO-SOURCE`, `SKIPPED` hoặc bị exclude.
- XML `testsuite`/`testcase` phản ánh methods actually executed.
- Failed/error/skipped counts đúng và không bị bỏ qua bởi filtering.
- Reports được upload của **cả hai tasks**, không chỉ HTML unit.
- `--rerun-tasks` dùng khi triage để đảm bảo actual execution.
- Không xóa artifact của lần FAIL đầu bằng rerun trước khi tải.

Skeleton XML mô tả fields, **không phải output Gradle thực tế**:

~~~xml
<testsuite name="com.example.parallellab.SafeCheckoutParallelTest"
           tests="3" failures="0" errors="0" skipped="0">
  ...
</testsuite>
~~~

Các runner/reporters có thể định dạng khác; dùng parser báo cáo phù hợp thay vì assert nguyên văn XML string này.

## 24. Cơ chế gây lỗi chỉ khi các Jupiter methods overlap

Một test thiết kế yếu:

~~~java
@BeforeEach
void setup() {
    globalCart.clear(); // Xóa cả dữ liệu test khác!
}

@Test
void customerA() {
    checkout.addItem("shared", "pen");
    assertThat(checkout.total("shared")).isEqualTo(100);
}
~~~

Đây là **phản ví dụ** chưa đủ class/import, không nằm trong demo runnable. Khi test B cùng dùng `"shared"` hoặc gọi `clear()` ở `@BeforeEach`, A có thể đọc 0/500. Test có thể PASS khi JUnit chạy tuần tự dù mỗi method đều giả định state trống.

Cách sửa:
- Tạo unique ID trước mỗi method.
- Truyền ID vào API thay vì field singleton.
- Dùng atomic update cho cùng key.
- Cleanup **chỉ** key do method sở hữu.
- Chờ background jobs hoàn tất trước cleanup.
- Không dùng global `clearAll()/TRUNCATE` khi parallel.
- Khi cần external DB/queue, cấp schema/topic/consumer group riêng theo test run.
- Với Mockito trong cached context, serialize tests đó theo hướng dẫn Spring.

Một test fix tốt phải assert **business invariant**, không chỉ verify method invocation hoặc kiểm "không throw exception".

## 25. @ResourceLock, @Isolated và Spring annotations có giới hạn

JUnit Jupiter cung cấp `@ResourceLock("key")` để các tests cùng khai báo lock key được scheduler điều phối. Nó có hiệu lực với test lifecycle `@BeforeEach`/`@AfterEach`, nhưng **chỉ trong cùng JUnit execution plan**. Mọi test truy cập cùng global resource phải khai báo đúng lock. Nó **không khóa** hai Gradle JVM forks hoặc CI shards.

Ví dụ snippet cho một system property legacy:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class GlobalPropertyTest {

    @Test
    @ResourceLock(
        value = "app.global.property",
        mode = ResourceAccessMode.READ_WRITE
    )
    void changesPropertyTemporarily() {
        String original =
                System.getProperty("app.global.property");
        try {
            System.setProperty("app.global.property", "test");
            // Assertions thuộc contract cần kiểm.
        } finally {
            if (original == null) {
                System.clearProperty("app.global.property");
            } else {
                System.setProperty("app.global.property", original);
            }
        }
    }
}
~~~

Snippet cần JUnit imports, không thuộc runnable source. Với classes dùng `@MockitoBean`, `@MockitoSpyBean` hoặc `@DirtiesContext`, Spring Framework khuyến nghị **không chạy song song**. Có thể đặt `@Isolated` trên class hoặc tổ chức serial lane; `@Execution(SAME_THREAD)` chỉ điều phối methods theo parent, **không tự cô lập class khỏi mọi class khác**. `@DirtiesContext` đóng cached context và gây chi phí reload, không xóa rows ở external database.

Quan trọng hơn: `@ResourceLock` trên tests không sửa được product code dùng singleton field lưu customer ID khi HTTP requests thật chạy đồng thời. Cần sửa **ownership của state** ở production.

## 26. Test transaction và worker threads

`@Transactional` trên test method Spring thường mở **test-managed transaction** theo test thread. Một HTTP server thread, `@Async` method hoặc Kafka listener có thể dùng transaction khác và commit riêng. Khi test rollback, DB state của worker không tự động rollback.

~~~text
JUnit test thread @Transactional
   BEGIN
   HTTP call -----------------> server thread
                                UPDATE database
                                COMMIT
   test ROLLBACK

Rows do server commit vẫn có thể tồn tại.
~~~

Trong CI parallel, state này có thể va vào test khác. Cần unique business IDs, explicit scoped cleanup sau khi await committed state, và Testcontainers/production-like DB nếu cần kiểm lock/transaction isolation. `@DirtiesContext` hoặc `@MockitoBean` reset không thay external DB cleanup.

Bài ví dụ dùng in-memory map để tập trung vào race của singleton; không tuyên bố đã kiểm PostgreSQL/RabbitMQ/Kafka.

## 27. Quy trình triage lỗi CI-only có thể lặp lại

1. Lưu original CI failure artifacts (XML/HTML/full logs), commit SHA và phiên bản công cụ.
2. Xác định task/source set; chắc chắn tests được discover.
3. So `-PitParallel=false` với `true` trên cùng source/env.
4. Log test method, owner key và thread; đối chiếu setup/teardown.
5. Liệt kê shared mutable objects: singleton, static, mock, database rows, file paths, queues.
6. Nếu nghi race, dựng interleaving tối thiểu bằng `CountDownLatch`, không dùng sleep may rủi.
7. Tạo red invariant trên nhánh sửa, chứng minh FAIL trước fix.
8. Sửa production state ownership hoặc scoped locking đúng cấp.
9. Chạy test regression, cả unit và integration ở serial/parallel, nhiều lần nếu cần.
10. Đối chiếu actual JUnit counts, skipped/error và external DB state.
11. Khôi phục parallel CI cho những tests an toàn; serialize nhóm dùng shared mock/dirty context.
12. Ghi root cause, fix, phiên bản, evidence và giới hạn kiểm chứng vào issue/PR.

Một report có thể viết:

~~~text
Symptom: expected owner alpha but observed beta under CI parallel
Root cause: mutable currentCustomer in singleton Spring bean
Proof: CountDownLatch forces A.enter -> B.enter -> A.read
Fix: request ID passed explicitly, keyed atomic storage
Regression: owner-specific assertions and scoped cleanup
CI: unit 4 + integration 6 expected; verify actual XML
~~~

Đây là **mẫu tóm tắt incident**, không phải report một lần CI đã chạy. Không gán nhãn fixed chỉ vì tắt parallel và hết FAIL.

## 28. Checklist QA trước khi merge

- [ ] Có ghi đúng Java, Spring Boot, Gradle Wrapper và JUnit versions?
- [ ] Đã phân biệt Jupiter threads, Gradle forks, CI shards và app workers?
- [ ] Đã lưu original failure XML/logs trước rerun?
- [ ] Đã xác minh test task/source set đúng và expected counts?
- [ ] Đã so serial/parallel bằng một biến `itParallel`?
- [ ] Có test dùng singleton mutable current user/cart/tenant/session?
- [ ] `volatile`/`AtomicReference` có bị dùng sai như request isolation?
- [ ] Có static cache, default timezone, System property hoặc port dùng chung?
- [ ] Test có unique business ID/namespace và scoped cleanup?
- [ ] Có `@BeforeEach`/`@AfterEach` global clear ảnh hưởng test khác?
- [ ] Có background tasks chưa await trước teardown?
- [ ] Có `@MockitoBean`/`@DirtiesContext` chạy parallel không?
- [ ] Có test cần `@ResourceLock`/`@Isolated` và các giới hạn JVM/shard?
- [ ] Có SQL transaction ở server/async thread ngoài test rollback?
- [ ] Có Testcontainers/Redis/Kafka/DB dùng chung across jobs?
- [ ] Có bounded latches/futures thay cho Thread.sleep?
- [ ] Diagnostic PASS khi thấy bug được phân biệt khỏi regression PASS sau fix?
- [ ] Fixed service không lưu per-request identity ở field?
- [ ] Atomic compute và unique keys đã được test?
- [ ] CI không dùng ignoreFailures hoặc continue-on-error để che tests?
- [ ] Báo cáo JUnit XML/HTML được upload dù job fail?
- [ ] Cả suite serial và parallel đã được chạy trên target CI?
- [ ] Test counts unit 4 và integration 6 được xác nhận từ report thực?
- [ ] Không ghi credentials/PII trong diagnostic logs?
- [ ] Không tuyên bố actual tests PASS nếu chưa chạy?

## 29. Kết quả mong đợi và tài liệu chính thức

Với đúng source files và môi trường đã cấu hình:

| Thao tác | Dự kiến |
| --- | --- |
| `./gradlew test` | 4 unit tests |
| `./gradlew integrationTest -PitParallel=false` | 6 integration tests; Jupiter scheduler tuần tự |
| `./gradlew integrationTest -PitParallel=true` | 6 integration tests; Jupiter parallel enabled |
| `./gradlew check` | 10 methods qua 2 tasks |
| `RacySessionInvestigationTest` | Alpha quan sát Beta: chứng minh class anti-pattern có bug |
| `SafeCheckoutParallelTest` | Pen100, Book400, keys độc lập |
| `CartBalancesConcurrencyTest` | 6×50 increments = 300, remove A không xóa B |

**Những con số này là expected behavior, không phải output Gradle/JUnit thực tế**. Mã mẫu chưa được compile/run tại thời điểm biên soạn; để xác nhận cần dựng project, chạy Gradle Wrapper và kiểm `build/test-results/test` + `build/test-results/integrationTest`. Log order của parallel tests không cố định. Diagnostic test nhìn thấy bug và PASS **không có nghĩa class lỗi đủ an toàn để triển khai**.

### Nguồn chính thức để tra cứu

- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html)
- [JUnit Jupiter 5.12 — Parallel Test Execution](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution)
- [JUnit Jupiter 5.12 — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle)
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Test Task](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Gradle plugin requirements](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)
- [Gradle — GitHub Actions CI](https://docs.gradle.org/current/userguide/github-actions.html)
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Kết luận:** Khi CI-only failure xuất hiện sau khi bật parallel, hãy thu thập evidence và phân biệt các tầng đồng thời. Thử serial/parallel để khoanh vùng, ép race bằng latch để chứng minh root cause, sau đó sửa mutable state ownership: **không lưu customer identity trong singleton field**, truyền ID tường minh và dùng atomic keyed storage với per-test cleanup. Giữ parallel cho tests độc lập, serialize riêng nhóm có mock/context/global resources không thể tách và dùng actual JUnit XML làm bằng chứng.