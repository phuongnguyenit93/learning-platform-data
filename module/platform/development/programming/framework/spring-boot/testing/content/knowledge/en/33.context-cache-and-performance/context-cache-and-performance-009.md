# Cache Limitations When Gradle Forks Multiple JVMs

## 1. Why must you understand context cache scope?

In Spring Boot testing, `@SpringBootTest` can be expensive because Spring builds an `ApplicationContext`, processes auto-configuration, registers/injects beans, opens resource pools, and sometimes initializes a web server or external connections. The Spring TestContext Framework uses a **context cache** to store initialized contexts and reuse them across tests sharing the same configuration.

An especially critical limitation: **this cache is stored in a static variable of Spring TestContext, living inside the memory of each individual JVM**. When Gradle spawns multiple forked test worker JVMs, each worker has **its own separate cache**. Two tests with identical annotations and identical Spring configuration scheduled onto two JVMs will have to initialize two independent `ApplicationContext`s. There is no distributed cache, IPC, or serialization automatically transferring Spring contexts between test workers.

This lesson belongs to **Context cache and performance** in the **Spring Boot – testing** module, covering **Cache Limitations When Gradle Forks Multiple JVMs**.

After completing it, you will be able to:

1. Distinguish the Gradle daemon, Test task, forked test worker JVM, JUnit execution threads, and the Spring TestContext cache.
2. Understand how `maxParallelForks`, `forkEvery`, `--max-workers`, and `--parallel` affect context cache reuse differently.
3. Know that Spring's cache key depends on `@SpringBootTest`, profiles, properties, mocks, dynamic properties, context loaders, and hierarchies.
4. Show why the same cache key in two PIDs still produces **two different context instances**.
5. Read hit/miss/cache size statistics via the `org.springframework.test.context.cache` logger at DEBUG level.
6. Explain the default `maxSize` of 32, LRU eviction, `@DirtiesContext`, and the default context failure threshold of 1 in Spring Framework 6.1.
7. Never confuse the Gradle build cache / `UP-TO-DATE` tasks with the Spring TestContext cache.
8. Inspect PID, `org.gradle.test.worker`, bean UUIDs, and context identity to diagnose reuse.
9. Prove reuse **within one JVM** using `TestContextManager` and `assertSame`/`assertNotSame` assertions.
10. Write tests that do not depend on how Gradle assigns classes to workers and do not assert a fixed worker count.
11. Design benchmarks tracking wall-clock, CPU, heap, DB connections, and startup counts instead of blindly increasing forks.
12. Apply a **Java 17 + Spring Boot 3.3.5 + Gradle 8.8 + JUnit Jupiter** project requiring neither Docker nor a database.

**Core mindset:** A cache hit can only happen if the next test finds a matching entry still present **in the exact same test JVM**. Forking multiple JVMs increases parallelism while reducing cache reuse opportunities and multiplying startup counts.

## 2. Architecture diagram

~~~text
Shell / CI
   |
   v
Gradle daemon (orchestrates build, does not hold Spring test contexts)
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

PIDs and worker counts in the diagram are illustrative. Gradle spawns only as many workers as needed within configured limits. **K1 in A and K1 in B are logically the same configuration key, yet two independent caches store two distinct instances**.

### 2.1. When does Spring reuse a context?

Suppose:

~~~java
@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AlphaTest {
}
~~~

and another class has the same annotation:

~~~java
@SpringBootTest(
    classes = ForkCacheApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BetaTest {
}
~~~

If Alpha and Beta run in the **same JVM**, with no cache eviction or dirtying:

~~~text
Alpha: K1 MISS -> start context X
Beta:  K1 HIT  -> reuse context X
~~~

If the two classes run in **two forked JVMs**:

~~~text
PID A: Alpha K1 MISS -> context X-A
PID B: Beta  K1 MISS -> context X-B
~~~

JVM B cannot access X-A simply via `@SpringBootTest`. A Java `static` field is not shared across processes.

### 2.2. Why is context ID not proof?

`ApplicationContext.getId()` can be identical across two newly constructed contexts. Some frameworks assign default IDs. For better observation, combine:

- `ProcessHandle.current().pid()` to inspect the PID;
- `System.getProperty("org.gradle.test.worker")` to inspect the Gradle-assigned worker identifier;
- a UUID generated when the context's singleton bean initializes;
- `System.identityHashCode(context)` to observe identity **within one JVM**;
- cache DEBUG logging for hits/misses inside each process.

PID/UUID values change on every run and are **not fixed expected output**. Never write a cross-JVM assertion `alphaStamp.equals(betaStamp)` because worker scheduling is outside the test's control.

## 3. What makes up the context cache key?

Spring TestContext uses a configuration key combining metadata rather than just the test class name. Key groups:

| Component | Example | When it creates a different key |
| --- | --- | --- |
| Locations | `@ContextConfiguration(locations=...)` | Changing resource config |
| Classes | `@SpringBootTest(classes=...)` | Different root Spring configs |
| Context initializers | `@ContextConfiguration(initializers=...)` | Different initializer |
| Context customizers | Spring Boot test customizers, bean overrides | Different `@MockBean`/dynamic properties |
| Context loader | How the test context is loaded | Different loader |
| Parent | Context hierarchy | Different parent |
| Active profiles | `@ActiveProfiles` | Changing profile |
| Test property sources | `@TestPropertySource` | Changing resource/inline properties |
| Inline properties | `properties="lab.greeting=Hello"` | Different values |
| Web resource base | `@WebAppConfiguration` | Different web resource root |

Two classes sharing the root application where one uses `lab.greeting=Hello` and the other uses default `Xin chào` **must not reuse the context**; the bean was initialized with different values.

### 3.1. Mocks/customizers multiply keys

Spring Boot 3.3 includes `@MockBean`. One test declaring `@MockBean PaymentClient` and another declaring `@MockBean PaymentClient` plus `@MockBean EmailClient` generate different context customizers, producing extra cache keys. Newer Spring Framework/Boot versions use `@MockitoBean` for bean overrides; do not copy annotations from a different version while targeting Boot 3.3.5.

### 3.2. `@DynamicPropertySource`

`@DynamicPropertySource` participates in context customization. When each class declares a different method or differing property identities, cache keys can diverge. When sharing an inherited method while underlying Testcontainers resources change, a cached context can retain an old connection. Thus resource lifecycles must be aligned with the context lifecycle.

### 3.3. Cache reuse must never outweigh correctness

Do not delete profiles, properties, or mocks just to boost hit rates if tests genuinely need separate scenarios. The goal is removing **pointless differences** and keeping shared configurations consistent, not forcing two distinct scenarios onto the same bean graph.

## 4. LRU, `maxSize`, and failure threshold

By default the Spring TestContext cache holds up to **32 contexts**, using **least recently used (LRU)** eviction when full. Within one JVM, an evicted key is no longer available for reuse; the next lookup restarts the context.

System property:

~~~properties
spring.test.context.cache.maxSize=32
~~~

In Gradle:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'spring.test.context.cache.maxSize', '32'
}
~~~

`systemProperty` on the `Test` task forwards the property to the **forked test JVM**; setting it solely on the Gradle daemon does not guarantee it reaches Spring TestContext.

With 4 test workers, each worker **independently enforces `maxSize=32`**; there is no global capacity of 32 split evenly. Raising `maxSize` across all 4 workers can spike total heap usage while reducing evictions.

### 4.1. `@DirtiesContext`

`@DirtiesContext` tells Spring TestContext that the `ApplicationContext` is dirty and must be closed/evicted. The next test using the same key must reload the context. Use it when a test truly mutates the Spring context beyond safe reset; never slap it onto every class to "clean the database".

### 4.2. Context failure threshold

Starting in **Spring Framework 6.1**, each context cache key has a default **failure threshold=1**. After one failed load, subsequent attempts with the same key in the **same cache** fail fast with `IllegalStateException`. Configured via:

~~~properties
spring.test.context.failure.threshold=1
~~~

Another worker maintains its own failure counter. If multiple JVMs all try to boot the same invalid configuration, logs may show the root failure **once per PID**; there is no global failure threshold.

### 4.3. When does an entry close?

Common cases include eviction from `@DirtiesContext`, LRU when exceeding `maxSize`, or context closure on JVM exit per lifecycle. Do not assume an entry lives forever just because the Gradle daemon stays alive: test worker JVMs have their own lifecycles.

## 5. Gradle `maxParallelForks` and `forkEvery`

### 5.1. `maxParallelForks`

~~~groovy
tasks.named('test', Test) {
    maxParallelForks = 4
}
~~~

This allows Gradle to run **up to 4 test worker JVMs concurrently** for the Test task. The default in Gradle Java testing is **1**. This is not 4 JUnit threads, and it does not guarantee exactly 4 PIDs: class count and total worker slots can yield fewer.

Increasing forks can:

- reduce wall-clock time when tests are independent and CPU headroom exists;
- increase Spring context startups because key `K` must load once in **each worker needing `K`**;
- increase heap/metaspace and classloading overhead;
- multiply Hikari pools, broker connections, embedded servers, and Testcontainers lifecycles;
- cause CPU/IO contention and hit DB connection limits;
- expose file/port/data collisions if fixtures are not isolated.

### 5.2. `forkEvery`

~~~groovy
tasks.named('test', Test) {
    forkEvery = 0
}
~~~

**Default `forkEvery=0` does not mean "tests run inside the Gradle daemon"**. It means **no limit on how many test classes run in one forked test JVM**, allowing process reuse across test classes.

~~~groovy
tasks.named('test', Test) {
    forkEvery = 1
}
~~~

**`forkEvery=1`** replaces the JVM after every test class, wiping out the freshly loaded static Spring context cache along with the JVM. This mode is very expensive for full-context Spring Boot tests. `forkEvery=5` lets a process run up to roughly 5 classes before replacement, without guaranteeing which classes are grouped together.

### 5.3. `--max-workers` and `--parallel`

| Setting | Controls | Impact |
| --- | --- | --- |
| Gradle `maxParallelForks` | Max forked test processes in a Test task | Each JVM has its own cache |
| Gradle `forkEvery` | JVM recycling rate by test class count | Cache lost when new process spawns |
| Gradle `--max-workers` | Total worker slots across the build | Can cap effective forks |
| Gradle `--parallel` | Run tasks/subprojects concurrently | Multiple Test tasks can run simultaneously |
| JUnit parallel mode | Threads inside a test JVM | Share one context cache |
| Spring cache `maxSize` | Cache entries per JVM | LRU eviction |
| `@DirtiesContext` | Evicts the target context | Reload within that JVM |

Never say "Gradle fork" when you mean "JUnit thread". Threads in the same JVM share a static cache yet risk races on shared mutable beans; separate processes have separate caches with fewer intra-JVM data races.

## 6. Cost model and measurement

Suppose initializing one context takes 3 seconds, there are 20 test classes sharing the key, and each class runs in 100ms (**purely hypothetical numbers**):

~~~text
1 worker, forkEvery=0:
  ~1 context load, 20 classes share the cache.

4 workers, forkEvery=0:
  If all 4 workers receive classes needing K:
  potentially ~4 context loads, concurrent/overlapping.

forkEvery=1:
  Potentially ~20 context loads (one JVM per class).
~~~

More context loads do not always raise wall-clock time proportionally because forks execute in parallel. Yet total startup CPU/IO, classloading, memory, and resource pressure increase.

Model:

~~~text
Minimum context loads ~
  Sum over each forked JVM:
    Unique cache keys used by that JVM

+ reloads from LRU/@DirtiesContext/forkEvery/retries
~~~

Measure **wall-clock duration, max RSS/heap, GC, CPU, connection counts, flakiness**, and Spring hits/misses per process. Never pick fork counts solely from CPU core count or one lucky run.

## 7. Preparing the Java 17, Spring Boot 3.3.5, and Gradle 8.8 project

The lab builds an app with no web port or DB to isolate cache behavior from external resources. It has two `@SpringBootTest` classes with identical config, one class with a differing property, one test verifying cache mechanics within a single JVM, and one plain JUnit test.

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

Gradle Wrapper scripts/JAR are generated by Gradle or taken from a standard repo. Markdown text cannot embed binary `gradle-wrapper.jar`.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'fork-cache-lab'
~~~

### 7.3. `build.gradle`

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

**Intentional benchmark configuration:** `-PtestForks` and `-PtestForkEvery` switch execution modes from the command line without editing source files. `systemProperty` passes values into the forked JVM; `showStandardStreams` prints diagnostic logs. JUnit still executes only tests discovered under `useJUnitPlatform()`.

JUnit thread parallelism is left disabled because this lesson specifically compares Gradle **process forking**.

### 7.4. `ForkCacheApplication.java`

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

### 7.5. `NameFormatter.java`

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

### 7.6. `GreetingService.java`

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

The expression `@Value("${lab.greeting:Xin chào}")` in the original template replaces the property-prefix symbol with a dollar sign when saved; the Java code here uses valid Spring `@Value` syntax.

### 7.7. `ContextStamp.java`

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

The UUID is generated when Spring instantiates the singleton. When the same context is reused, this bean's UUID stays the same. When another fork constructs its own context, a new UUID appears; use it for observation, never asserting a random UUID as a fixed expected value.

### 7.8. `ForkDiagnostics.java`

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

This diagnostic helper lives in test sources. `worker` prints `not-gradle` when run via an IntelliJ/Eclipse JUnit runner. Never assert PID/worker/UUID values because they vary per invocation.



## 8. `CacheAlphaTest` and `CacheBetaTest` share the same configuration

### 8.1. `CacheAlphaTest.java`

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

### 8.2. `CacheBetaTest.java`

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

### 8.3. What to observe

Neither class declares differing properties, mocks, profiles, or test customizers. If both run in the same JVM and the cache entry has not been dirtied/evicted:

- PID matches;
- Gradle worker ID matches;
- `ContextStamp` bean UUID matches;
- `System.identityHashCode(context)` matches (useful as supporting evidence);
- Spring TestContext cache can record a reuse/hit.

If Gradle schedules them onto different JVMs, PIDs, worker IDs, and markers differ. **Never assert that Alpha and Beta always share the same marker**: scheduling belongs to Gradle, not to the business test contract.

Illustrative log, not exact stdout:

~~~text
OBS label=Alpha-1 pid=8101 worker=1 contextIdentity=1a2b3c4d marker=abcd... greet=Xin chào, An!
OBS label=Beta-1 pid=8101 worker=1 contextIdentity=1a2b3c4d marker=abcd... greet=Xin chào, An!
~~~

With `forks=4`, two similar lines can show different PIDs and markers. Do not rely on alphabetical test class order.

## 9. `CacheVariantTest`: same app, different property

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

A differing inline property produces a **different cache key**, since `GreetingService` is built with a different prefix. In the same JVM, Alpha/Beta can share one context while Variant must receive a separate context. That is a **valid cache miss**, not a performance bug.

## 10. `CacheMechanicsTest`: deterministic proof within one JVM

A single test running inside one JVM can instantiate multiple `TestContextManager` instances to verify cache semantics directly. This avoids writing cross-class assertions when Gradle could schedule classes onto separate workers.

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

### Why doesn't this code depend on Gradle's scheduler?

Within a single test method, both `TestContextManager` calls execute synchronously inside **the one JVM running that method**. `matchingConfigurationReusesContextInOneJvm` verifies two metadata entries with matching keys retrieve the exact same instance. Even if Gradle uses `forkEvery=1`, this method executes inside one worker so `assertSame` holds.

`differentInlinePropertyProducesDifferentContext` compares two different keys; thus they must be distinct instances even inside the same worker.

`markingDirtyEvictsSpecificEntry` uses `DirtyFixture` with a separate `dirty-only` property, avoiding evicting Alpha/Beta's shared cache entry. After marking dirty, fetching the context again must produce a new instance. This is a **TestContext mechanics check**, not a pattern to imitate in ordinary business tests.

### Why not use `@DirtiesContext` for every test?

`@DirtiesContext` is meant for tests that genuinely taint the `ApplicationContext`; overusing it inflates startup counts. An illustrative snippet:

~~~java
@SpringBootTest(classes = ForkCacheApplication.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationScenarioTest {
    // Case with a legitimate reason to evict the context.
}
~~~

This snippet is not part of the runnable project. Resetting database data, clearing test files, or resetting mocks usually has far lighter mechanisms than context eviction.

## 11. `NameFormatterTest`: plain JUnit without Spring

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

These two test methods do not start Spring and need no context cache. In a large project, moving DI-independent logic into plain JUnit can save more suite time than tweaking context cache keys.

### Total JUnit methods

| Test class | `@Test` count | Purpose |
| --- | ---: | --- |
| `CacheAlphaTest` | 2 | Spring context/business behavior |
| `CacheBetaTest` | 2 | Equivalent config to Alpha |
| `CacheVariantTest` | 1 | Different property/cache key |
| `CacheMechanicsTest` | 3 | Same key, different key, dirtied entry |
| `NameFormatterTest` | 2 | Unit test needing no Spring |
| **Total** | **10** | Observing cache, forks, and correctness |

Ten tests are **designed** in this material. Gradle/JUnit was not executed in the authoring environment, so the expected count must not be read as an observed PASS run.

## 12. Logback test configuration to display Spring cache DEBUG

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

`spring-boot-starter` brings logging infrastructure, allowing a test Logback configuration on the classpath. It enables only the target category instead of turning on DEBUG across all of Spring.

The Spring cache logs statistics such as `size`, `maxSize`, `hitCount`, and `missCount`. **Illustrative example, not fixed stdout**:

~~~text
Spring test ApplicationContext cache statistics:
size=2, maxSize=32, hitCount=14, missCount=2
~~~

Counters can be logged repeatedly; **never sum `hitCount` across lines**, as they are cumulative values. Inspect the final snapshot of each worker/PID, record context keys, and do not imagine a global cache counter exists.

## 13. Running benchmarks A/B/C with Gradle

### 13.1. Setup

Requires JDK 17, Gradle Wrapper 8.8, and dependencies downloaded from Maven Central on the first run. No server, DB, or Docker needed. If you have Gradle installed without a wrapper yet:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

After generating the Wrapper scripts/JAR, store them per repo policy.

### 13.2. Mode A: single worker, `forkEvery=0`

~~~bash
./gradlew test -PtestForks=1 -PtestForkEvery=0 --rerun-tasks
~~~

Windows:

~~~powershell
.\gradlew.bat test -PtestForks=1 -PtestForkEvery=0 --rerun-tasks
~~~

Expectation: Alpha/Beta run in the same test JVM and, unless evicted/dirtied, share the context marker; Variant uses a distinct key. `CacheMechanicsTest` confirms semantics independently of the scheduler.

### 13.3. Mode B: up to 4 concurrent forked JVMs

~~~bash
./gradlew test -PtestForks=4 -PtestForkEvery=0 --rerun-tasks
~~~

Expectation: depending on class distribution and worker slots, multiple PIDs/worker IDs may appear; the same Spring configuration can boot again in different JVMs. Never assert there must be exactly 4 processes or one class per worker.

### 13.4. Mode C: recycle every test class

~~~bash
./gradlew test -PtestForks=1 -PtestForkEvery=1 --rerun-tasks
~~~

Expectation: the JVM is replaced between test classes, preventing Alpha/Beta from reusing the context across processes. `CacheMechanicsTest` still proves reuse inside a single method/JVM. Startup/fork overhead is typically higher.

### 13.5. Comparing with identical inputs

- Keep source and dependencies unchanged across all three runs.
- Keep JUnit parallelism off when isolating Gradle forking.
- Use `--rerun-tasks` to ensure tests actually execute.
- Repeat several runs and compare median and peak memory rather than drawing conclusions from one sample.
- Capture **Test task** duration rather than mixing dependency resolution or cold compile cache into startup cost.
- Record PIDs/worker IDs and per-process context cache counters separately.
- Check failures/skips: speed is never worth a flaky suite.
- On shared CI runners, CPU/memory contention can shift with external workload.

### 13.6. Reports

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.forkcache.CacheAlphaTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheBetaTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheVariantTest.xml
build/test-results/test/TEST-com.example.forkcache.CacheMechanicsTest.xml
build/test-results/test/TEST-com.example.forkcache.NameFormatterTest.xml
~~~

There is no fixed stdout because PIDs, UUIDs, ordering, timestamps, and Gradle scheduling vary at runtime. After actually running, inspect JUnit XML/HTML to verify **10 methods** were discovered and check real results.

## 14. Why is Gradle `UP-TO-DATE` not a Spring cache hit?

Similar-sounding mechanisms with completely different scopes:

| Mechanism | What does it store? | Effect |
| --- | --- | --- |
| **Spring TestContext cache** | Live `ApplicationContext` objects | Reused across matching-key tests in one JVM |
| Gradle task `UP-TO-DATE` | Input/output snapshots/history | Can skip running the test task |
| Gradle build cache | Task outputs | Can reuse outputs without executing tests |
| Gradle configuration cache | Build configuration state | Shortens build config phase; holds no Spring bean graph |
| JVM class/JIT cache | Bytecode/classes/JIT state | JVM-local warmup, not Spring context sharing |
| Gradle daemon reuse | Build execution process | Does not preserve test worker's static Spring cache across builds by default |

`./gradlew test` printing `UP-TO-DATE` means tests **did not run** during that invocation. There are no new Spring cache hits to observe. `--rerun-tasks` forces the task to run, **not** making the Spring cache survive across two Gradle invocations.

## 15. Multiple Test tasks and multi-module builds

A multi-module repository may have:

~~~text
:core:test
:api:test
:integrationTest
~~~

Each Gradle Test task manages its own test worker processes. Spring's static cache is never shared across the JVMs of two separate tasks, even in the same Git repository, classpath, or main application class.

`--parallel` lets tasks across modules run concurrently. That can improve wall-clock time while running more contexts/DB connections/containers simultaneously. Do not merge all tests into one task just to "force context reuse" at the expense of clean unit/integration boundaries and reporting.

### Use each layer for its intended purpose

- **Plain JUnit:** logic needing no Spring DI.
- **Spring slice tests:** `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` when verifying one layer.
- **`@SpringBootTest` non-web:** wiring/auto-configuration/services.
- **`@SpringBootTest(RANDOM_PORT)`**: real HTTP/server boundary.
- **Testcontainers integration tests:** DB/broker semantics needing real infrastructure.
- **End-to-end/proxy/browser tests:** TLS, routing, auth gateway, and client boundaries.

A unit-only suite needs no Spring context cache optimization. A full `@SpringBootTest` suite should inspect unique keys before adding forks.



## 16. JUnit parallel threads vs. Gradle forked processes

JUnit Jupiter supports parallel execution **within the same JVM** when configured:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
~~~

Methods/classes running on multiple threads still share **one static TestContext cache**. However, concurrency can introduce races on:

- Shared mutable singleton beans;
- Static fields and fixtures;
- Shared `@MockBean` stubbing/resets;
- Shared DB rows or tables;
- Testcontainers, ports, or file paths;
- `@DirtiesContext` closing a context while another thread uses it;
- Schedulers/clock overrides;
- Transaction side effects across HTTP server threads.

Never equate "same cache" with "safe to run tests concurrently". Without independent data, use per-test IDs, transaction boundaries, JUnit resource locks, or isolated resources instead of enabling parallel mode blindly.

## 17. Impact on Testcontainers, DB pools, and memory

Starting a context can allocate a Hikari datasource, Kafka/RabbitMQ clients, Redis, HTTP pools, background executors, or Testcontainers resources. With multiple Gradle forks:

- Each JVM builds its own Spring bean graph.
- Each context can open its **own pool/connections**.
- A static Testcontainers field remains **per JVM**, not automatically shared across workers.
- Multiple JVMs can still hit a **shared external database** and collide even though Spring contexts do not share heap.
- `@SpringBootTest(RANDOM_PORT)` avoids HTTP port collisions, yet each worker launches its own embedded server.
- A DB connection limit can be exceeded as workers × contexts × pool size grows.

Hypothetical example: each JVM has a max pool size of 10; four active JVMs can consume more connections than one JVM. Do not treat `4 × 10` as an exact RSS or connection figure, since lazy pools and context counts vary.

### Do not forget test data isolation

If multiple forks share a database or broker, use unique row keys, per-worker schemas/tenants, or controlled cleanup. `org.gradle.test.worker` can help namespace test resources within a single build, though it is not a persistent cross-build identifier. Avoid hardcoded ports/files and never assume JVM isolation provides database isolation.

### Watch HTTP rollback boundaries

With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the client request and server handler can run on different threads/transactions. `@Transactional` on the test method does not automatically roll back the HTTP server request's transaction. Perform real data cleanup instead of raising cache invalidation.

## 18. `@DirtiesContext` in its place, not a cure-all

The `@DirtiesContext` annotation is a tool to **evict a context** when context-level state has been mutated/corrupted. It is not a default for every test writing to a database. Use it when:

- A test alters bean definitions or singleton state that cannot be safely reset;
- A test verifies start/stop/restart lifecycle;
- A context-specific resource cannot be safely reused.

Do not attach it to every test class just because:

- DB rows weren't cleaned up;
- A Mockito mock wasn't reset;
- A file could have been placed in `@TempDir`;
- A test uses a shared mutable static field;
- A test fails only when run alongside another class.

Fix state isolation instead of paying for dozens of Spring startups. Across multiple forks, `@DirtiesContext` only evicts the **cache in the current JVM**—it never broadcasts to other workers.

## 19. Cache size 32 and optimizing key count

The Spring cache defaults to 32 contexts with LRU. In a worker needing 40 distinct keys, eviction and extra startups occur if older keys are revisited. Raising `spring.test.context.cache.maxSize` reduces churn at the cost of heap memory. With 4 JVMs, each JVM retains its own entries, multiplying peak memory.

Better steps before raising `maxSize`:

1. Count unique context configurations.
2. Eliminate unnecessary variations in `@MockBean`, profiles, and inline properties.
3. Share base test annotations/configs when behavior truly matches.
4. Use plain JUnit or slices for tests needing no full context.
5. Avoid widespread `@DirtiesContext`.
6. Verify inherited `@DynamicPropertySource` stays stable alongside resource lifecycles.
7. Keep JUnit parallelism aligned with thread safety.
8. Measure cache misses/hits per process, heap, and wall-clock time.

**Never alter security/bean-wiring tests to use the wrong config just for a cache hit.** Correctness comes first.

## 20. Failure threshold across separate workers

When context `K` fails its first startup, Spring Framework 6.1 marks `K` as exceeding the failure threshold in that cache. Subsequent tests with the same key in that worker fail fast with `ApplicationContext failure threshold exceeded`. However, another worker must still attempt its own startup if it has not hit the error yet.

### Diagnostic steps

1. Group logs by PID and Gradle worker ID.
2. Find the **first root failure** in each worker (e.g., missing bean, connection refused).
3. Do not treat threshold-exceeded as a brand new root cause.
4. Verify configs, credentials, resources, and ports.
5. Never set an enormous threshold just to retry a deterministic failure.
6. If an external dependency needs readiness, use proper startup coordination/checks rather than infinite sleeps.
7. Never mix counters from separate JVMs when reporting.

## 21. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Same config yet multiple startups | Tests run across multiple JVM forks | Check PID, `maxParallelForks`, `forkEvery` |
| `forkEvery=1` suite very slow | Every class gets a fresh JVM/cache | Choose `forkEvery=0` when tests are isolated |
| Test class passes alone, fails in suite | Shared state/external resource | Fix data isolation, not just forks |
| Multiple PIDs even with `forks=1` | Recycling via `forkEvery`, multiple Test tasks | Check task/fork policy |
| `forks=4` yet only 2 PIDs | Max is an upper bound; scheduler/worker slots | Never assert all 4 are created |
| Context IDs match across PIDs | ID is not global object identity | Log PID + marker |
| Cache size=2, high hitCount in one worker | Normal intra-worker reuse | Do not infer global hits from it |
| Raising `maxSize` causes OOM | Many cached contexts × forks | Measure heap, reduce unique keys |
| `@DirtiesContext` slows tests | Repeated evict/restart | Use only when context is truly dirty |
| Different `@MockBean` per test | Creates many cache keys | Consolidate identical configs, use unit/slices |
| Spring cache DEBUG missing | Wrong logger category/initialization | Use `logback-test.xml` |
| Test task `UP-TO-DATE` | Gradle skipped executing tests | Use `--rerun-tasks` for benchmarking |
| `--parallel` on yet test classes stay sequential | Task-level parallelism | Distinguish Gradle vs. JUnit parallelism |
| Testcontainers launches many instances | Static container per JVM | Design lifecycle/resource limits |
| DB connection limit exceeded | Pools multiply across workers | Reduce forks/pool size, isolate DB |
| 401/port conflict only in parallel | Shared external state/static port | Unique endpoints/data per worker |
| Repeated failure threshold exceeded | Each worker has its own failure cache | Find first error per PID |
| JUnit parallel causes mock reset races | Shared context/bean across threads | Serialize/scope mocks properly |
| Single benchmark contradicts later run | Noise, CI contention | Repeat runs, track median/peak |
| Different classloaders in same JVM | Static fields belong per classloader | Understand test classloader boundaries |
| Tests depend on cross-class markers | Gradle scheduler is non-deterministic | Assert within a single method/JVM |

## 22. Benchmark data collection sheet

| Attribute | Record |
| --- | --- |
| Commit/JDK/Gradle/Boot versions | Identical source/runtime |
| `maxParallelForks` | 1, 2, 4… |
| `forkEvery` | 0, N, or 1 |
| JUnit parallel mode | On/off, threads |
| Gradle max workers | Worker slot cap |
| Test method/class counts | Must not change between runs |
| Distinct test JVM PID count | Processes actually used |
| Cache miss/hit snapshot **per PID** | Never sum cumulative log lines |
| Unique config keys | Diversity of contexts |
| Task wall-clock | Primary speed KPI |
| Peak RSS/heap/GC | Memory pressure |
| DB/broker connections | External pressure |
| Flaky/fail/skipped | Test correctness |
| Gradle task state | Actually executed or `UP-TO-DATE` |

Sample report phrasing: "4 forks cut median test task duration from 80s to 65s while raising peak RSS by 1.8GB; CI runners retain sufficient RAM with zero failures." **This is a report format example**, not an actual run result of this project.

## 23. Hands-on exercises

**A.** Run `testForks=1, testForkEvery=0` and compare Alpha/Beta markers when in the same worker. Run `CacheMechanicsTest` to observe `assertSame` independent of the scheduler.

**B.** Run `testForks=4` and record the PIDs/worker IDs that actually appear; explain why fewer than 4 may spawn.

**C.** Enable `forkEvery=1` and compare context startup count and wall-clock time against baseline.

**D.** Reset `CacheVariantTest`'s property back to default and observe cache keys aligning.

**E.** Add `@ActiveProfiles("demo")` to one class; predict the resulting cache key divergence.

**F.** Create two classes with differing `@MockBean` sets and observe context load counts.

**G.** Create a test with its own `@DynamicPropertySource`; check identity/initializer lifecycle.

**H.** Apply `@DirtiesContext(AFTER_CLASS)` to one class; compare cache hits/misses for that key.

**I.** Cap `contextCacheSize=2`, add several config variants, and observe LRU eviction.

**J.** Run Gradle test twice without `--rerun-tasks`; distinguish Gradle `UP-TO-DATE` from a Spring cache hit.

**K.** Enable JUnit parallel threads in a separate branch; verify they share PID/cache while mutable singleton beans can race.

**L.** Run a Testcontainers PostgreSQL test with 1 vs. 4 forks; measure container counts and DB connections.

**M.** Separate `test` and `integrationTest` tasks; prove there is no context sharing across test worker processes.

**N.** Build an invalid context failing startup; observe the failure threshold per PID.

**O.** Enable Spring cache DEBUG and extract the final snapshot per PID without summing `hitCount` lines.

**P.** Run on 2 CPU/8GB and 8 CPU/16GB CI runners; pick fork counts from real metrics.

**Q.** Move pure business formatter tests to plain JUnit and compare Spring startup savings.

**R.** Vary an inline property in every class and watch the key count grow/shrink.

**S.** Add a `@SpringBootTest(RANDOM_PORT)` smoke test and verify no hardcoded ports break under parallel forks.

**T.** Introduce a mutation leaking shared static state, then fix it via isolation instead of jumping to `forkEvery=1`.

## 24. Checklist before merging Gradle test parallelism changes

- [ ] Distinguished Gradle forked JVMs from JUnit threads?
- [ ] Not expecting Spring's static cache to be shared across PIDs?
- [ ] Understood default `maxParallelForks=1`?
- [ ] Understood `forkEvery=0` reuses forked JVMs rather than disabling forking?
- [ ] Not defaulting to `forkEvery=1` for a `@SpringBootTest` suite?
- [ ] Know `org.gradle.test.worker` helps distinguish workers?
- [ ] Have PID/marker/context identity diagnostics available when needed?
- [ ] Not treating `ApplicationContext.getId()` as global object proof?
- [ ] Cache keys aligned across matching classes/profiles/properties/mocks/dynamic config?
- [ ] Not deleting distinct scenarios just to boost reuse?
- [ ] Using `@DirtiesContext` only when genuinely needed?
- [ ] Aware `maxSize=32` and LRU eviction apply per JVM cache?
- [ ] Aware failure threshold=1 since Spring Framework 6.1 is also per key/cache?
- [ ] Not comparing Gradle `UP-TO-DATE` against a real test run?
- [ ] Using `--rerun-tasks` during benchmarks?
- [ ] Not asserting Gradle always spawns exactly `maxParallelForks` JVMs?
- [ ] Test assertions independent of how Gradle distributes classes?
- [ ] Repeated benchmarks covering wall-clock, CPU, RSS, GC, and flaky rate?
- [ ] No fixed ports or file paths shared across forks?
- [ ] Database/broker/Testcontainers resources properly isolated?
- [ ] Not forcing pure unit tests into `@SpringBootTest`?
- [ ] Test contexts with singleton state safely reset?
- [ ] Not spawning extra cache keys via careless mocks/variant properties?
- [ ] Resource pool limits sized appropriately for parallelism?
- [ ] Verified Gradle Test task and CI worker limits?
- [ ] Not enabling JUnit parallelism when beans/test data aren't thread-safe?
- [ ] Report clearly states limitations and measurement methodology?
- [ ] Java 17, Boot 3.3.5, Gradle 8.8 compatibility verified?
- [ ] JUnit report confirms all 10 methods executed, not just cached outputs?

## 25. Official Documentation

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys, static JVM scope, `maxSize=32`, LRU, and logging.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): policy since 6.1, system property, and skipped errors.
- [Spring Framework 6.1 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContextManager.html): `getTestContext`, lifecycle.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): eviction semantics.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `maxParallelForks`, `forkEvery`, and worker property.
- [Gradle — Test task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): test process settings, JVM properties.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): test process forking, trade-offs.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, slices, and context testing.
- [JUnit Jupiter 5.10 — Parallel Execution](https://docs.junit.org/5.10.2/user-guide/#writing-tests-parallel-execution): thread-level parallelism.
- [Java 17 — ProcessHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID diagnostics.

**Remember:** The Spring TestContext cache lives in `static` memory inside **each** Gradle test worker JVM. Increasing `maxParallelForks` adds concurrency without sharing contexts across workers; setting `forkEvery=1` drastically reduces cross-class reuse. To optimize, keep keys stable, avoid unnecessary `@DirtiesContext`, separate unit/slice/full-context tests, track cache hits/misses per PID, and benchmark wall-clock/memory/DB pressure under realistic CI conditions.
