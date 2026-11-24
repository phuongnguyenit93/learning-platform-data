# @DirtiesContext and Bean Overrides When Multiple Tests Share a Context

## 1. Why Do Errors Appear Only When Running the Full Test Suite?

A Spring Boot test class passes consistently when run on its own. Yet when executed alongside dozens of other test classes, it occasionally picks up a Mockito stub from another class, sees a mutated singleton bean, or fails with `ApplicationContext is no longer active`. Developers add `@DirtiesContext` to every class for "isolation"; flakiness drops, but the suite becomes terribly slow because the `ApplicationContext` restarts constantly.

The issue is not just the cache. There are **three distinct lifecycles**:

1. **Spring TestContext cache**: decides which test classes can reuse the *exact same* `ApplicationContext`.
2. **Bean overrides and mock reset**: decides whether a bean in the context uses the real implementation, a Mockito mock/spy, or a test replacement; and if it is a mock, when its stubbings/interactions are reset.
3. **JUnit/runner parallel execution**: decides which test methods/classes can execute simultaneously on the same context or external resource.

**Core principle:** `@DirtiesContext` closes and evicts the context from the cache. It is **not** equivalent to `Mockito.reset(mock)`, `@AfterEach` cleanup, transaction rollback, or a shield against contention in parallel tests. Similarly, a `@MockitoBean` configured identically in two classes can share the same context; that does **not** make it safe for two tests to stub and verify that mock concurrently.

This lesson focuses on **Isolation and Parallel Execution**, specifically **"@DirtiesContext and Bean Overrides When Multiple Tests Share a Context"**.

### After This Lesson, You Will Be Able To

- Explain why two different test classes share the same context and singleton beans.
- Distinguish cache key, cache hit, dirty/evict, and create-new-context.
- Apply `@DirtiesContext` at method/class level with appropriate `BEFORE`/`AFTER` timing.
- Use Spring Framework 6.2's `@MockitoBean`, `@MockitoSpyBean`, and `@TestBean` aligned with bean override lifecycles.
- Understand `REPLACE_OR_CREATE`, `REPLACE`, `WRAP`, and `enforceOverride=true`.
- Know how field names, bean names, qualifiers, and context hierarchies affect matching and cache keys.
- Distinguish default `MockReset.AFTER` mock resets from context rebuilds.
- Identify race conditions when two tests stub/verify the same mock, or Test A dirties a context currently used by Test B.
- Choose rationally among bean state resets, database rollbacks, mock resets, resource locks, separate contexts, and dirtying.
- Run a Java 17+/Spring Boot 3.5 example with **10 JUnit Jupiter methods** covering same-key reuse, override variants, mock resets, singleton state, and controlled eviction.
- Read cache logs and establish CI rules for parallel integration tests.

**Target versions:** Java 17+, Spring Boot **3.5.16**, Spring Framework **6.2.x**, JUnit Jupiter, Mockito 5, and AssertJ managed by Boot's BOM. Spring Framework 6.2 introduces `@MockitoBean`, `@MockitoSpyBean`, and `@TestBean`. In Spring Boot 4.x/Framework 7.x, modules/starters/import paths may change; always consult documentation for your target version.

## 2. What Does the ApplicationContext Cache Share?

The Spring TestContext Framework holds a static context cache inside the test worker JVM. For each test needing a Spring context:

```text
TestClass A -----------------------------+
                                         |
                                         v
                            MergedContextConfiguration
                                  (cache KEY)
                                         |
                                  cache lookup
                                 /           \
                               HIT          MISS
                                |             |
                                v             v
                           same context   load/refresh new
                                |             |
                                +------+------+
                                       |
                                ApplicationContext
                                       |
                      beans, singletons, proxies, mocks
                                       |
                TestClass B with equivalent effective key
                            -> same context object
```

A cache hit means **the exact same Java `ApplicationContext` object** is returned. Consequently, singleton beans in that container are the exact same instances unless reconfigured/overridden under a different cache key.

This is not a cache of test method results. `@BeforeEach`, test methods, assertions, DB operations, and Mockito calls still re-run. Nor is it the Gradle build cache or JUnit test result cache.

### 2.1. The Cache Key Is More Than Just @SpringBootTest

Primary metadata included in the `MergedContextConfiguration` key in Spring Framework 6.2:

| Component | Examples |
|---|---|
| `locations` / `classes` | `@ContextConfiguration` XML/classes, Boot application class |
| `contextInitializerClasses` | `ApplicationContextInitializer` |
| `contextCustomizers` | `@MockitoBean`, `@TestBean`, `@DynamicPropertySource`, Boot test customizers |
| `contextLoader` | Loader/bootstrapping strategy |
| `parent` | `@ContextHierarchy` parent |
| `activeProfiles` | `@ActiveProfiles("test")` |
| `propertySourceDescriptors` | `@TestPropertySource` resource descriptors |
| `propertySourceProperties` | Inline test properties |
| `resourceBasePath` | `@WebAppConfiguration` |

The test class name itself is **not** a distinct key component merely because the classes have different names. If A and B have the same effective key, both can share the context. With the same application class but differing profiles, properties, or bean overrides, the keys normally differ.

### 2.2. The Context Cache Lives Inside the JVM

```text
JVM test worker #1:
   KEY X -> context X
   KEY Y -> context Y
   Tests in this worker may reuse them.

JVM test worker #2:
   separate empty cache initially
   even KEY X cannot reuse context from worker #1.
```

With Gradle `maxParallelForks`/`forkEvery` or Maven Surefire `forkCount`/`reuseForks`, JVM counts and sharing behavior change. **JUnit `@ResourceLock` does not lock resources across JVM processes**, so if multiple forks access a shared database or file, external resource isolation/coordination is still required.

Spring Framework's default cache max size is **32**, using LRU eviction when capacity is exceeded. Thus a context with the same key can reload after eviction, dirtying, or switching test JVMs. Never assume "same annotations" means a context survives forever in every suite.

## 3. What Does @DirtiesContext Actually Do?

`@DirtiesContext` signals Spring TestContext that a context is **no longer safe for continued sharing**. When triggered, the framework removes the entry from the cache and closes the context. Next time a test requests the same configuration metadata, a fresh context is loaded.

```text
Context K in cache
      |
 Test mutates global bean/context state
      |
 @DirtiesContext trigger
      |
      v
 remove K from TestContext cache
      |
      v
 close old ApplicationContext
      |
      v
 next lookup K -> cache miss -> new context
```

**What it does NOT do:**

- Does not automatically wipe data in PostgreSQL/Kafka/external services.
- Does not guarantee Java static state or OS environment variables are reset.
- Does not automatically roll back transactions for side effects outside the test thread.
- Does not lock JUnit threads or synchronize with Test B while it uses the old context.
- Does not merely reset Mockito stubbings; it closes **the entire container**.
- Does not replace independent test data design.

### 3.1. Class-Level Annotation

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class ModifiesGlobalContextTest {
    // ... JUnit tests ...
}
```

This is a snippet, not a full Java file. `AFTER_CLASS` is the default class mode: after the class finishes, the cached context is marked dirty. `BEFORE_CLASS` dirties before the class begins, useful when the class requires starting with a fresh context even if it does not mutate the context itself.

### 3.2. Method-Level Annotation

```java
@Test
@DirtiesContext(
    methodMode = DirtiesContext.MethodMode.AFTER_METHOD
)
void changesMutableSingletonBeyondSafeReset() {
    // A change that makes reuse unsafe.
}
```

`AFTER_METHOD` is the default method mode; `BEFORE_METHOD` dirties before the method when that method requires a fresh context. If modes are set at both class and method levels, each corresponding trigger applies. Using `@DirtiesContext` merely because a Mockito mock was stubbed is usually misuse.

### 3.3. Choosing Modes Based on Actual Requirements

| Mode | When dirtied? | Consequence |
|---|---|---|
| Class `BEFORE_CLASS` | Before class | Evicts an old shared key before the test class uses it |
| Class `AFTER_CLASS` | After class | Subsequent classes needing that key must reload |
| Class `BEFORE_EACH_TEST_METHOD` | Before every method | Context startup may repeat many times |
| Class `AFTER_EACH_TEST_METHOD` | After every method | Evicts after every method; increases startup time |
| Method `BEFORE_METHOD` | Before marked method | Only that method requests a fresh context |
| Method `AFTER_METHOD` | After marked method | Subsequent methods/classes reload |

`BEFORE`/`AFTER` modes are not "run transaction before/after"; they specify **when the context is closed**. Tests can get dependencies re-injected per Spring TestContext lifecycle when the context changes, yet if code stores an old context reference in a static/non-Spring-managed field, that reference becomes **stale/closed**.

### 3.4. Context Hierarchy

With `@ContextHierarchy`, `@DirtiesContext.hierarchyMode` selects invalidation scope. The default `EXHAUSTIVE` clears branches sharing an ancestor; `CURRENT_LEVEL` limits invalidation to the current level when appropriate. If a parent bean was mutated, `CURRENT_LEVEL` may be **insufficient**. With `@MockitoBean`/`@MockitoSpyBean`/`@TestBean` in a context hierarchy, use `contextName` to restrict the override to the proper level if needed; otherwise, it may apply across levels unexpectedly.

## 4. Bean Overrides: Replacing Definitions/Instances at Context Construction Time

In Spring Framework 6.2, bean override support is implemented through TestContext infrastructure (`ContextCustomizerFactory`, `BeanFactoryPostProcessor`, `TestExecutionListener`). It does not automatically mutate an already-cached `ApplicationContext` when a test method starts.

**Every override configuration becomes part of the context customizers/cache key.** If two test classes specify the same mock target, name/qualifier/reset mode, and equivalent other metadata, they can share the **overridden** context. If one overrides and the other does not, or they override different targets, they normally get separate contexts.

### 4.1. Three Strategies

| Strategy | Meaning | Used by |
|---|---|---|
| `REPLACE_OR_CREATE` | Replace existing bean, or create a mock/test bean if absent | Default `@MockitoBean`, default `@TestBean` |
| `REPLACE` | Require an existing bean; otherwise fail fast | `@MockitoBean(enforceOverride=true)`, `@TestBean(enforceOverride=true)` |
| `WRAP` | Capture the real instance and wrap it in a spy | `@MockitoSpyBean` |

**Important limitation:** Spring Framework's bean override facility supports **singleton beans**; do not treat it as an automatic mechanism to override arbitrary prototype/request-scoped beans. With `FactoryBean`, replace/wrap semantics apply to the produced object per Spring's rules rather than replacing an arbitrary prototype `FactoryBean`.

### 4.2. Can "Silently Create" a Nonexistent Bean

```java
@MockitoBean
PaymentGateway gateway;
```

By default, `@MockitoBean` can **create a new mock bean** if no corresponding production bean exists. This lets a slice test start, yet fails to verify that real dependency wiring exists. When intentionally replacing an **existing bean**, use:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
```

Now if the target bean is missing, test setup fails instead of silently adding a mock. Which option is right depends on the test boundary: in an MVC slice, the service might not be scanned so creating a mock is expected; in a full-context bean override test, `enforceOverride` catches wiring regressions.

### 4.3. Bean Identification and Qualifiers

Spring TestContext selects beans by type, `@Qualifier`, explicit name, or fallback field name. Two test classes mocking the same type with different field names can receive **different context keys** because of qualifier metadata. For example:

```java
@MockitoBean
PaymentGateway paymentGateway;

// Another test class:
@MockitoBean
PaymentGateway gateway;
```

Even when only one candidate bean exists, Spring docs note that field names/qualifiers can affect cache sharing. **Prefer consistent names or specify `name="..."` when targeting a specific bean**, rather than renaming fields arbitrarily.

## 5. @MockitoBean: A Context Mock Does Not Belong Exclusively to One Method

`@MockitoBean` replaces/registers a Mockito mock as a Spring bean. When the context is reused, the **same mock instance** can be injected into multiple test instances/classes. It is unlike `@Mock` from `MockitoExtension` in a pure unit test:

- `@Mock` belongs to the Mockito/JUnit lifecycle and does not replace a Spring `ApplicationContext` bean.
- `@MockitoBean` participates in Spring TestContext startup/caching and is injected into other Spring beans.
- Spring beans using that dependency call the mock instead of the real implementation.
- Same config key → potentially the same Java mock object across classes.
- Mocks are reset by Spring Framework 6.2 test listeners according to lifecycle.

### 5.1. Default Mock Reset Is AFTER

Spring Framework 6.2 Javadoc for `@MockitoBean.reset` defaults to **`MockReset.AFTER`**: the framework resets the mock **after each test method** when the Spring TestContext Mockito reset listener runs under default settings.

This usually prevents subsequent test methods from seeing stale stubbings/interactions:

```java
@Test
void firstTest() {
    when(gateway.fetch()).thenReturn("A");
    assertThat(service.read()).isEqualTo("A");
}

// @MockitoBean default AFTER reset runs at end of first test.
// The second test should define its own stubbing.
@Test
void secondTest() {
    when(gateway.fetch()).thenReturn("B");
    assertThat(service.read()).isEqualTo("B");
}
```

This is a snippet for a test class with `@MockitoBean` and an injected service. It does **not** ensure safety when two methods run **concurrently**: if Test A resets while Test B is invoking the same mock, B's stubbing can vanish or verification can be corrupted.

### 5.2. Mock Reset Is Not a Context Reset

| Operation | What does it change? | Cost |
|---|---|---|
| Default `MockReset.AFTER` | Clears Mockito mock stubbings/interactions after method | Lightweight, no context rebuild |
| `Mockito.clearInvocations(mock)` | Clears recorded invocations while keeping stubbings | Lightweight, use intentionally |
| `Mockito.reset(mock)` | Clears both stubbings and invocations | Lightweight, can mask test design if overused |
| Custom stateful bean `reset()` | Resets that specific bean per application API | Keeps context open |
| `@Transactional` rollback | Reverts test-scoped DB transaction | Does not reset mocks/non-transactional singletons |
| `@DirtiesContext` | Evicts and closes the entire `ApplicationContext` | Expensive, can break other tests |

**Do not use `@DirtiesContext` just because a mock was stubbed.** If the default reset mode is disabled (`MockReset.NONE`) or custom listeners are altered, understand the lifecycle and cleanup explicitly before assuming test isolation.

### 5.3. Expect the Same Mock Across Two Test Classes

If both classes configure:

```java
@SpringBootTest(classes = ExampleApp.class)
class FirstTest {
    @MockitoBean(name = "paymentGateway", enforceOverride = true)
    PaymentGateway paymentGateway;
}

@SpringBootTest(classes = ExampleApp.class)
class SecondTest {
    @MockitoBean(name = "paymentGateway", enforceOverride = true)
    PaymentGateway paymentGateway;
}
```

they can share **one overridden context** if all other key metadata matches. **Never** assume two separate Spring contexts will always be loaded merely because there are two test classes.

## 6. @MockitoSpyBean: Keeps Real Behavior, Along with Side Effects

`@MockitoSpyBean` uses the `WRAP` strategy: it requires **exactly one candidate bean** to wrap in a spy. Unstubbed methods invoke the real implementation, unlike mocks returning default answers.

```java
@MockitoSpyBean
InvoiceCalculator calculator;

@Test
void recordsRealCall() {
    int amount = calculator.total(2, 100);
    assertThat(amount).isEqualTo(200);
    verify(calculator).total(2, 100);
}
```

This is an illustrative snippet assuming a real `InvoiceCalculator` returning 200; it is **not** part of the runnable demo code below. Spies can invoke DB/network/transactions or mutate real singleton state, so test isolation requires extra care.

### 6.1. Stubbing Spies Properly

With a spy, `when(spy.method())` can **invoke the real method while setting up the stub**. Spring/Mockito docs recommend `doReturn`/`doThrow`/`doNothing` when side effects are undesirable:

```java
doReturn("stubbed")
    .when(spyGateway)
    .fetchRemote();
```

Do not assume `@MockitoSpyBean` creates a new bean if no target exists; it needs an existing bean (single candidate) to wrap. With multiple candidates, specify a qualifier/name; when targeting a level in a context hierarchy, use `contextName`.

## 7. @TestBean: Replacing a Bean via a Static Factory

Not every override needs Mockito. Spring Framework 6.2 provides `@TestBean` to replace a bean with an object returned by a **zero-argument static factory method**.

```java
@TestBean(
    name = "clock",
    methodName = "fixedClock",
    enforceOverride = true
)
Clock clock;

static Clock fixedClock() {
    return Clock.fixed(
        Instant.parse("2040-06-01T00:00:00Z"),
        ZoneOffset.UTC);
}
```

This snippet is used in the runnable demo fixture. It is useful when wanting a deterministic fake/stub without Mockito stubbings. Like `@MockitoBean`, the override participates in context customizers and cache keys; the factory method is typically invoked at context creation time, **not** necessarily per `@Test` method.

**Note:** if the fake holds mutable state, it remains a singleton inside the cached context and can leak across tests. Never assume a "test bean" automatically gets per-method scope.

## 8. Parallel Execution Hazards: Spring Offers Basic Support with Limits

Spring Framework 6.2 documentation on parallel test execution advises **against running tests in parallel** when they:

- use `@DirtiesContext`;
- use `@MockitoBean` or `@MockitoSpyBean`;
- use legacy Spring Boot `@MockBean`/`@SpyBean`;
- mutate shared state across databases, brokers, filesystems, or shared services;
- depend on JUnit test method ordering or ordering mechanisms within the test class.

This is official guidance to avoid flakiness, not a denial of all parallel Spring testing. Many tests without shared mutable state can run concurrently without trouble.

### 8.1. Race from a Shared Mockito Mock

```text
Class A & Class B share Context K and mock M.

Thread A: when(M.read()).thenReturn("A")
Thread B: when(M.read()).thenReturn("B")
Thread A: service.read() -> M.read() might see B
Thread B: verify(M).read() sees A's invocation too
Thread A: @AfterTest Mockito reset(M)
Thread B: service.read() -> M.read() may return default null

Result: timing-dependent assertions, flaky verification.
```

Even though JUnit creates **different test class instances**, the Spring context still holds **the exact same mock bean instance**. Default `AFTER` reset is not concurrent synchronization.

### 8.2. Race from @DirtiesContext While Another Test Uses the Context

```text
Thread A: using ApplicationContext K
Thread B: @DirtiesContext(AFTER_METHOD) closes K
Thread A: continues --> "ApplicationContext is no longer active"
```

Spring docs specifically warn about `ApplicationContext ... no longer active` errors when one thread evicts a cached context while another thread is actively using it (via `@DirtiesContext` or LRU eviction).

**Never "fix" this by bumping timeouts randomly or wrapping a bean in `synchronized`.** Re-evaluate scheduling/isolation: avoid parallelizing tests with dirties/mock overrides, or separate resources/configurations properly.

### 8.3. JUnit @ResourceLock: Helpful, Not Magic

JUnit Jupiter supports:

```java
@ResourceLock(
    value = "shared-payment-test-resource",
    mode = ResourceAccessMode.READ_WRITE
)
class PaymentIntegrationTests {
    // ...
}
```

The JUnit engine locks resource keys within the same execution plan; `READ` locks can run together, while `READ_WRITE` prevents tests declaring **the same key** from overlapping. It covers corresponding lifecycle methods. However:

- All test classes contending on the same resource must **declare compatible keys**.
- Locks do not span JVMs/Gradle workers/Maven forks.
- Locks do not prevent an unregistered class from dirtying the context.
- Tests involving mock resets or complex dirtying should still **prefer serial execution**, per Spring guidance.
- `@Execution(SAME_THREAD)` on one class constrains execution within that class only; it **does not serialize all other classes**.

Another JUnit Jupiter option is `@Isolated` on a class that must run without other concurrent tests in the same engine execution plan (depending on version). When simplicity and reliability matter more, disable parallelism on the **integration test task** while keeping pure unit tests parallel.

### 8.4. Do Not Use Ordering to "Solve" State Leakage

Adding `@TestMethodOrder` so method 2 relies on method 1's stub does not create isolation. It makes tests order-dependent and breaks when classes/methods are run selectively. Every method must set up its own stubs/test data and clean up its side effects.

## 9. Choosing the Lightest Appropriate Reset Mechanism

| Mutated state/resource | Preferred cleanup | When `@DirtiesContext` is needed |
|---|---|---|
| Mockito stubbing/verification | `@MockitoBean` default reset, proper Mockito reset mode | Rarely needed |
| Singleton counter/map/cache | Clear/reset API in `finally` or `@AfterEach` | When context state cannot be restored safely |
| Embedded DB records | Transaction rollback/`@Sql` cleanup/truncate | When schema/embedded context cannot recover safely |
| External DB rows | Unique IDs + cleanup/transactions | When client/context is broken by mutations |
| Kafka topics/messages | Group/topic isolation and cleanup/lifecycle | When infrastructure context is invalidated |
| Java static fields | Clear static state, avoid global mutations | Dirtying context does not reset statics |
| System properties/OS env | Scoped mutation + restore in `finally` | Dirtying does not restore OS/JVM global state |
| `ThreadLocal`/MDC | `remove()` in `finally` | Dirtying does not replace thread-reuse cleanup |
| Mutated bean definitions/context config | Avoid mutating; use distinct test config keys | Usually required |
| Broken server/DataSource pool lifecycle | Controlled dependency/context restart | Can be needed after lifecycle mutation |
| Real HTTP calls via `RANDOM_PORT` | Clean up DB/external side effects separately | Do not rely solely on test `@Transactional` |

Calling `reset()` on a bean to restore invariants costs far less than restarting the entire Spring container. Still, **resets must be safe under parallel execution**; resetting a singleton while another thread reads it remains a race.

## 10. Runnable Example: Java 17+ / Spring Boot 3.5.16

This example focuses on TestContext cache + bean overrides + dirties; no web server, database, or Docker is needed. All tests run in the same JVM **sequentially** to keep identity measurements deterministic.

### 10.1. Scenarios Demonstrated

1. Two Spring Boot test classes with the same inherited `@MockitoBean` field share the context with that mock override configuration.
2. A test class without overrides uses a **different context** than the mock override configuration.
3. A fixture changing `@ActiveProfiles` produces a different cache key.
4. A `@TestBean` explicit replacement produces a separate context and fixed value.
5. A singleton counter inside a shared context retains state unless cleaned up.
6. A `@DirtiesContext(AFTER_CLASS)` fixture evicts the cached context; the next lookup with the same key creates a new context.
7. `@MockitoBean` resets stubbings after each JUnit method when Spring listeners are active.
8. Shared context proofs do not rely on test method order between two classes.

**Expected:** exactly **10 JUnit Jupiter methods**: 2 in mock class A, 2 in mock class B, 6 in the cache evidence class. Nested fixture classes have no `@Test` methods and are not executed as standalone tests.

### 10.2. File Tree

```text
build.gradle
settings.gradle
src/
├── main/java/com/example/sharedctx/
│   └── SharedContextApplication.java
└── test/
    ├── java/com/example/sharedctx/
    │   ├── SharedClockSupport.java
    │   ├── ClockMockAlphaTest.java
    │   ├── ClockMockBetaTest.java
    │   └── CacheBehaviorTest.java
    └── resources/
        └── junit-platform.properties
```

Classes live in the same package to avoid package-private accessibility issues. The app contains only Java singleton beans; `webEnvironment=NONE` avoids opening sockets. Demo startup time is not representative of a full production app.

### 10.3. Gradle Groovy DSL

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
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'shared-context-isolation-lab'
```

**File `src/test/resources/junit-platform.properties`:**

```properties
# Explicitly disable JUnit parallel execution for these integration tests.
junit.jupiter.execution.parallel.enabled=false
```

Boot 3.5 BOM manages Spring Framework 6.2 and Mockito/JUnit/AssertJ versions. Gradle Wrapper files are omitted and can be generated via Gradle/IDE. Never mix Boot 4 dependencies with Boot 3.5 source expecting identical packages.

## 11. Production Source: A Clock, a Service, and a Counter

**File `src/main/java/com/example/sharedctx/SharedContextApplication.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SharedContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedContextApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2025-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }

    @Bean
    Counter counter() {
        return new Counter();
    }

    public static final class GreetingService {
        private final Clock clock;

        public GreetingService(Clock clock) {
            this.clock = clock;
        }

        public String greet(String name) {
            return "Hello " + name + " @ " + clock.instant();
        }
    }

    public static final class Counter {
        private final AtomicInteger value = new AtomicInteger();

        public int get() {
            return value.get();
        }

        public int increment() {
            return value.incrementAndGet();
        }

        public void restore(int original) {
            value.set(original);
        }
    }
}
```

**Explanation:**

- Production `Clock` is deterministic rather than depending on the CI machine's wall clock.
- `GreetingService` receives `Clock` via constructor injection; if tests override the `Clock` bean, the service receives the mock/fake `Clock` as the context is built.
- `Counter` is a singleton holding an `AtomicInteger`. `AtomicInteger` ensures atomic increments, **not** independent mutation/reset across multiple test cases.
- No DB, `@Transactional`, `@Profile`, or `HttpClient`; the demo deliberately isolates caching/override behavior.
- A new `Counter` singleton bean is created only when the context actually reloads; on a cache hit, the existing counter is preserved.

## 12. Base Class: Identical Mock Configuration Across Multiple Classes

**File `src/test/java/com/example/sharedctx/SharedClockSupport.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

abstract class SharedClockSupport {

    @MockitoBean(name = "clock", enforceOverride = true)
    Clock clock;

    @Autowired
    SharedContextApplication.GreetingService service;

    @Autowired
    ApplicationContext context;
}
```

This is a base class containing no JUnit methods. Subclasses share the same inherited field declaration and explicit target name, avoiding differences in fallback field qualifiers. `enforceOverride=true` ensures the test **does not silently create a new `Clock` mock** if the production `clock` bean disappears.

### 12.1. Test Class A

**File `src/test/java/com/example/sharedctx/ClockMockAlphaTest.java`:**

```java
package com.example.sharedctx;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
    classes = SharedContextApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ClockMockAlphaTest extends SharedClockSupport {

    @Test
    void mockClockDrivesServiceWithoutRealClock() {
        Instant fixed =
                Instant.parse("2031-01-02T03:04:05Z");

        when(clock.instant()).thenReturn(fixed);

        assertThat(service.greet("Linh"))
                .isEqualTo("Hello Linh @ 2031-01-02T03:04:05Z");
        verify(clock).instant();
    }

    @Test
    void stubbingStartsCleanInEachMethod() {
        // Spring MockitoBean defaults to MockReset.AFTER.
        assertThat(Mockito.mockingDetails(clock).getStubbings())
                .isEmpty();

        when(clock.instant()).thenReturn(
                Instant.parse("2032-01-01T00:00:00Z"));

        assertThat(service.greet("Minh"))
                .isEqualTo("Hello Minh @ 2032-01-01T00:00:00Z");
    }
}
```

### 12.2. Test Class B

**File `src/test/java/com/example/sharedctx/ClockMockBetaTest.java`:**

```java
package com.example.sharedctx;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
    classes = SharedContextApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ClockMockBetaTest extends SharedClockSupport {

    @Test
    void sameMockOverrideSupportsAnotherTestClass() {
        when(clock.instant()).thenReturn(
                Instant.parse("2041-05-06T07:08:09Z"));

        assertThat(service.greet("An"))
                .isEqualTo("Hello An @ 2041-05-06T07:08:09Z");
        verify(clock).instant();
    }

    @Test
    void mockHasNoLeftoverStubbingsAtMethodStart() {
        assertThat(Mockito.mockingDetails(clock).getStubbings())
                .isEmpty();

        when(clock.instant()).thenReturn(
                Instant.parse("2042-06-07T08:09:10Z"));

        assertThat(service.greet("Bình"))
                .isEqualTo("Hello Bình @ 2042-06-07T08:09:10Z");
    }
}
```

**What these 4 tests demonstrate:**

- The same `Clock` target is mocked in the context built for both classes.
- Each method defines its own stubbing for its behavior.
- Default `MockReset.AFTER` cleans up stubbings between sequential methods.
- Tests do not depend on JUnit running class A before class B.
- No `@DirtiesContext` is needed just to clear mock stubs.

**Limits:** assertions on clean stubbings depend on Spring's Mockito reset listener running and the suite running **sequentially** per `junit-platform.properties`. If custom test listeners or `reset=NONE` disable that reset, explicit setup/cleanup must be designed.

## 13. Test Suite for Cache Identity, @TestBean, and @DirtiesContext

An independent test class uses `TestContextManager` with fixture classes to **explicitly load contexts within one test method**, comparing object references without relying on the execution order of two separate test classes.

This is a technique for **observing Spring TestContext mechanics**, not a mandatory pattern for every application.

**File `src/test/java/com/example/sharedctx/CacheBehaviorTest.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.bean.override.convention.TestBean;

import static org.assertj.core.api.Assertions.assertThat;

class CacheBehaviorTest {

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class PlainFixtureA {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class PlainFixtureB {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    @ActiveProfiles("other")
    static class OtherProfileFixture {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class FixedClockFixture {

        @TestBean(
            name = "clock",
            methodName = "fixedClock",
            enforceOverride = true
        )
        Clock clock;

        static Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2040-06-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    @DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
    )
    static class DirtyAfterFixture {}

    private static ApplicationContext load(Class<?> fixture) {
        return new TestContextManager(fixture)
                .getTestContext()
                .getApplicationContext();
    }

    @Test
    void equalMockMetadataAcrossClassesUsesSameContext() {
        ApplicationContext a = load(ClockMockAlphaTest.class);
        ApplicationContext b = load(ClockMockBetaTest.class);

        assertThat(b).isSameAs(a);
        assertThat(b.getBean(Clock.class))
                .isSameAs(a.getBean(Clock.class));
        assertThat(Mockito.mockingDetails(
                a.getBean(Clock.class)).isMock()).isTrue();
    }

    @Test
    void nonOverriddenContextDiffersFromMockContext() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext samePlain = load(PlainFixtureB.class);
        ApplicationContext withMock =
                load(ClockMockAlphaTest.class);

        assertThat(samePlain).isSameAs(plain);
        assertThat(withMock).isNotSameAs(plain);
        assertThat(Mockito.mockingDetails(
                plain.getBean(Clock.class)).isMock()).isFalse();
    }

    @Test
    void activeProfileChangesCacheKey() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext other = load(OtherProfileFixture.class);

        assertThat(other).isNotSameAs(plain);
        assertThat(other.getEnvironment().getActiveProfiles())
                .contains("other");
    }

    @Test
    void testBeanFactoryCreatesSeparateReplacementContext() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext replacement =
                load(FixedClockFixture.class);

        assertThat(replacement).isNotSameAs(plain);
        assertThat(replacement.getBean(Clock.class).instant())
                .isEqualTo(Instant.parse("2040-06-01T00:00:00Z"));
        assertThat(replacement.getBean(
                SharedContextApplication.GreetingService.class)
                .greet("Lan"))
                .isEqualTo("Hello Lan @ 2040-06-01T00:00:00Z");
    }

    @Test
    void singletonMutableStateIsVisibleAcrossSharedContexts() {
        ApplicationContext first = load(PlainFixtureA.class);
        ApplicationContext second = load(PlainFixtureB.class);

        SharedContextApplication.Counter counter =
                first.getBean(SharedContextApplication.Counter.class);
        int original = counter.get();

        try {
            int next = counter.increment();
            assertThat(next).isEqualTo(original + 1);
            assertThat(second.getBean(
                    SharedContextApplication.Counter.class).get())
                    .isEqualTo(original + 1);
        }
        finally {
            // Cleanup is cheaper than evicting the whole context.
            counter.restore(original);
        }
    }

    @Test
    void dirtyAfterClassEvictsThenSameKeyReloads()
            throws Exception {
        ApplicationContext old = load(PlainFixtureA.class);
        TestContextManager manager =
                new TestContextManager(DirtyAfterFixture.class);

        manager.beforeTestClass();
        try {
            ApplicationContext dirtyFixtureContext =
                    manager.getTestContext().getApplicationContext();

            // @DirtiesContext itself does not make a new cache key.
            assertThat(dirtyFixtureContext).isSameAs(old);
        }
        finally {
            // Triggers the DirtiesContext AFTER_CLASS test listener.
            manager.afterTestClass();
        }

        ApplicationContext fresh = load(PlainFixtureB.class);
        assertThat(fresh).isNotSameAs(old);
    }
}
```

### 13.1. Distinguishing Identity Tests from Integration Behavior Tests

| Method | What Is Proven |
|---|---|
| `equalMockMetadataAcrossClassesUsesSameContext` | Two classes with identical mocks reuse the context and mock bean |
| `nonOverriddenContextDiffersFromMockContext` | Plain vs overridden have distinct cache keys |
| `activeProfileChangesCacheKey` | Active profiles participate in the cache key |
| `testBeanFactoryCreatesSeparateReplacementContext` | `@TestBean` creates a replacement bean under a different config |
| `singletonMutableStateIsVisibleAcrossSharedContexts` | Shared singletons hold state; cleanup prevents cross-contamination |
| `dirtyAfterClassEvictsThenSameKeyReloads` | `@DirtiesContext` evicts; subsequent lookup reloads |

**Six methods**, plus 4 from the two Mockito classes = **10 methods**. Fixture classes hold only annotations, no `@Test` methods. When comparing "different contexts", a variant context may **already exist** in the cache; the assertion only states it **differs from the baseline key**, not necessarily that it was just created for the first time.

### 13.2. Why Not Assert Startup Counts with a UUID/Global Counter?

Spring Framework cache lookups can happen multiple times per test method, and JUnit execution order can vary. Relying on a global static counter asserting "incremented exactly N times" makes tests fragile when caches or framework listeners invoke additional lookups. Comparing Java object identity directly inside the same method is clearer.

### 13.3. @DirtiesContext on the Fixture Is Triggered via Lifecycle

In the final test, `TestContextManager.beforeTestClass()` and `afterTestClass()` fire test listeners according to `DirtyAfterFixture`'s annotations. This verifies **`AFTER_CLASS`** performs eviction right within the same method. Ordinary production tests never instantiate `TestContextManager` manually; `SpringExtension` invokes lifecycle callbacks automatically.

**Important:** the final test must not run concurrently with other tests sharing the same key, because it intentionally closes the context. The demo disables JUnit parallelism and limits Gradle to one worker to prevent races.

## 14. How to Run

**Linux/macOS**, with a Gradle Wrapper in the project:

```bash
./gradlew test --tests "com.example.sharedctx.ClockMockAlphaTest"
./gradlew test --tests "com.example.sharedctx.ClockMockBetaTest"
./gradlew test --tests "com.example.sharedctx.CacheBehaviorTest"

# Full demo suite:
./gradlew test
```

**Windows PowerShell**:

```powershell
.\gradlew.bat test --tests "com.example.sharedctx.ClockMockAlphaTest"
.\gradlew.bat test --tests "com.example.sharedctx.ClockMockBetaTest"
.\gradlew.bat test --tests "com.example.sharedctx.CacheBehaviorTest"
.\gradlew.bat test
```

**Code expectation:** 10 JUnit methods are discovered/executed and pass under Spring Boot 3.5.16, Framework 6.2, and the configured test runner. This article was statically reviewed against the APIs, **not reported as an actual Gradle/JUnit compilation or execution**.

### 14.1. Reading the Test Report

When verifying locally:

- Confirm Java 17+ is used by the Gradle test worker.
- Verify the test runner discovers exactly 2+2+6 = **10 `@Test` methods**.
- Confirm none are `@Disabled` or accidentally filtered out.
- When running a single class separately, the Context cache starts fresh in the new test worker JVM; do not expect context reuse from a previous command.
- A build task reporting `UP-TO-DATE` or `FROM-CACHE` is no substitute for verifying tests actually executed during that run.
- Enable cache `DEBUG` logging when inspecting hits/misses, not permanently in every CI run.

### 14.2. Using Maven Instead of Gradle

For Maven, create a corresponding project with Spring Boot 3.5 parent/BOM, `starter`, and `starter-test`. You can select a test class via Maven Wrapper:

```bash
./mvnw -Dtest=CacheBehaviorTest test
```

This is an illustrative command, not a bundled `pom.xml`. Do not run Maven commands in a Gradle-only project.

## 15. What to Watch Out for Regarding @DirtiesContext and Listener Ordering

### 15.1. AFTER_METHOD Is Not a Regular @AfterEach

`@DirtiesContext(methodMode=AFTER_METHOD)` is processed by Spring TestContext in an after-test-method phase per listener ordering. JUnit `@AfterEach` callbacks may execute in a related phase before or outside this callback depending on extensions/test listeners. Do not write cleanup depending on undocumented internal listener ordering.

In `@Transactional` tests, transactions also have their own lifecycle listener. When DB cleanup can be handled by rollback, prefer transactions/fixtures over dirtying the context. When truly dirtying, closing the `DataSource`/`EntityManagerFactory` can break cleanup code still holding old references.

### 15.2. Class AFTER_CLASS Affects Subsequent Tests Sharing the Key

When Class A dirties `AFTER_CLASS`, Class B using the same key afterward must reload. That slows down the suite and changes context identity. Still, **never write tests relying on "A must run before B"**; Test B's assertions must hold even when run alone.

### 15.3. BEFORE_CLASS Fits Pre-Existing State

If a test class must start with a fresh context regardless of what is in the cache, `BEFORE_CLASS` can fit. However, if it mutates the context and leaves dirty state behind, `BEFORE_CLASS` **does not automatically clean up after the class**. When both are needed, consider appropriate class modes supported by the framework or separate test/context setups. Never assume `BEFORE_CLASS` protects subsequent tests.

### 15.4. Parallel Tests Can Make Both BEFORE and AFTER Hazardous

Another thread may already hold the old context and use it right as you dirty it. Cache eviction is valid, yet does not wait for all consumers to finish their work. Therefore **"dirty before method" does not replace mutual exclusion** in a parallel suite.

## 16. How Do Bean Overrides Differ from @TestConfiguration/@Primary?

Spring Boot test code also uses `@TestConfiguration`, `@Import`, and `@Primary` to add or adjust test beans. They are not strictly equivalent to the override API:

- `@MockitoBean`: Spring Framework bean override via Mockito mock, convenient for stubbing/verification, participates in context customizers.
- `@MockitoSpyBean`: wraps an existing real singleton bean with a Mockito spy.
- `@TestBean`: overrides a bean via a static factory method.
- `@TestConfiguration`: adds extra configuration to the test context and can register alternative `@Bean`s, subject to naming/candidate resolution and Boot bean-definition-overriding settings.
- `@Primary`: selects a preferred bean when multiple candidates exist, **without removing the original bean**.
- `@Profile("test")` / `@Conditional...`: swaps bean sets by profile/condition, creating different cache keys when profiles differ.
- `@Import(TestBeans.class)`: imports additional test config classes into the context; differing metadata creates distinct cache keys.

Avoid enabling global `spring.main.allow-bean-definition-overriding=true` just to overwrite beans by name; it can mask accidental duplicate bean definitions. Spring Framework 6.2's test-specific override facility targets specific beans explicitly and is safer in many scenarios.

### 16.1. Cache Reuse with Inherited @MockitoBean

An abstract base test class declaring mock fields inherited by two subclasses with matching `@SpringBootTest` metadata typically shares a context. This reduces startup time, yet **also creates a shared mock instance**. When enabling parallelism, never assume "different subclasses" gives isolation.

### 16.2. @MockitoSpyBean and AOP Proxies

Spying on a bean wrapped by a Spring AOP proxy (transactions, caching, security) may require distinguishing the proxy from the target, and verifying methods can be subtle. Consult docs on target types, proxy/call sites, and `doReturn` stubbing when side effects exist. Never treat a spy `verify` call as proof that real transactions committed or rolled back properly; verify behavior with an integration test.

## 17. Safer Parallelism: Grouping by Risk

Instead of turning parallelism on across the entire suite, categorize tests:

| Group | Recommendation |
|---|---|
| Stateless pure Java/JUnit unit tests | Can run in parallel if no shared globals |
| Read-only Spring tests, no overrides/dirtying | Can run in parallel after verifying lifecycles/resources |
| Tests with `@MockitoBean`/`@MockitoSpyBean` | Prefer serial per Spring 6.2 docs |
| Tests with `@DirtiesContext` | Prefer serial, never overlap on the same context |
| Independent DB transaction tests | Check isolation levels, fixtures, and threads |
| Shared external DB/Kafka/files | Unique resources or serial/coordination |
| Testcontainers static/shared containers | Manage lifecycles, cache keys, shared topics/databases |
| Real HTTP `RANDOM_PORT` | Ports are dynamic, yet DB/bean state may still be shared |
| Context hierarchies + dirtying | Watch parent/child eviction |
| Native/AOT/separate JVM test workers | Handle separately; never rely on cross-process JUnit locks |

### 17.1. One Way to Split Gradle Tasks

Below is a **conceptual snippet**, requiring a project with matching source sets/tags:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'spring-shared-context'
    }
    maxParallelForks = 4
}

tasks.register('sharedContextTest', Test) {
    description = 'Run shared-context Spring tests serially'
    group = 'verification'
    useJUnitPlatform {
        includeTags 'spring-shared-context'
    }
    maxParallelForks = 1
    forkEvery = 0
}
```

**Do not assume this snippet works as-is without configuring `testClassesDirs`/`classpath` or matching your project's Java plugin conventions.** A dedicated `Test` task typically needs `testClassesDirs` and `classpath` from `sourceSets.test`, plus `check.dependsOn(...)` if CI should run both groups. In the runnable sample, we keep a single serial test task to avoid distracting boilerplate.

### 17.2. @ResourceLock Can Narrow Serialization Scope

When multiple tests write to a static Java resource/map, `@ResourceLock(value="resource-id", mode=READ_WRITE)` prevents overlap **if every test accessing that resource complies**. For `@DirtiesContext` or Mockito overrides, locks still do not replace Spring TestContext's general serial recommendations.

### 17.3. @Execution(SAME_THREAD) Does Not Serialize Other Test Classes

A common mistake: adding `@Execution(SAME_THREAD)` on Class A and assuming Class B cannot run at the same time. `SAME_THREAD` controls execution of A and its children per JUnit rules; it **creates no suite-wide lock**. Use task-level serialization, `@Isolated`, or full resource coordination by design instead of relying on a local annotation.

## 18. Troubleshooting Confusing Symptoms

| Symptom | Hypothesis to Check | Resolution |
|---|---|---|
| Passes alone, fails in suite | Shared mock/singleton/DB state | Isolate setup, reset/clean up, check parallelism |
| Stub from Class A "leaks" to Class B | Shared context/mock, wrong reset listener/mode | `@MockitoBean` default reset, verify after method |
| Mock suddenly returns `null` | Another test reset the same mock concurrently | Run serially or split contexts appropriately |
| `verify(mock)` sees more calls than expected | Concurrent tests or reset disabled | Serialize, restore reset listeners, per-method stubbing |
| `ApplicationContext no longer active` | Another test dirtied or LRU evicted it | Stop parallelism in that group, inspect cache logs |
| `@DirtiesContext` on every class slows suite | Constant context eviction | Reset beans/mocks/DB instead of context |
| Two classes with same `@SpringBootTest` get different contexts | Different override metadata/qualifier/profile | Compare effective cache keys |
| `@MockitoBean` creates mock despite missing production bean | Default `REPLACE_OR_CREATE` | `enforceOverride=true` when asserting existing bean |
| `@MockitoSpyBean` startup fails | Zero/multiple target candidates | Exact bean name/qualifier, existing singleton |
| `@TestBean` factory not found | Missing static no-arg factory or wrong `methodName` | Fix name/signature/visibility |
| `@TestBean` fake retains state across methods | Cached replacement singleton | Stateless fake or `reset()` |
| Mocks don't reset after method | `reset=NONE` or custom listeners | Restore listener/default mode |
| Resetting mock passes yet real bean is buggy | Mock bypassed behavior needing verification | Add integration tests with real collaborators |
| DB count rolls back yet Kafka messages remain | DB rollback differs from broker state | Clean up topic/consumer-group fixtures |
| Test A's `@DirtiesContext` makes Test B fail randomly | Invalidation race | Move to serial task / avoid dirtying |
| Same test class reloads context in another JVM fork | Process-scoped static cache | Review Gradle/Maven fork settings |
| Cache size hits 32, frequent reloads | LRU eviction from too many unique configs | Reduce key variation, check memory |
| Renaming mock field increases startup time | Fallback qualifier changed | Keep target/field names stable |
| Context hierarchy invalidation too broad | Default `EXHAUSTIVE` | Check `hierarchyMode`/`contextName` |
| `@Transactional` placed on `RANDOM_PORT` test | Server thread uses separate transaction | Explicit DB cleanup |
| `@TestInstance(PER_CLASS)` and singleton bean mixed | JUnit object lifecycle differs from Spring cache | Separate lifecycles / proper cleanup |
| Tests fail when run in a new order | Implicit state dependency | Each test sets up/asserts/resets independently |

## 19. Diagnosing Cache Misses and Closed Contexts

Spring TestContext cache log category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

In some test logging setups, the test worker logger config must apply early enough (Logback test config or JVM property). Useful metrics:

- Current cache size/maxSize.
- Cache hits and misses.
- Number of parent contexts (when using hierarchies).
- Evicted/closed contexts.
- Failure-threshold preemptively skipped startup cases.

Default `spring.test.context.cache.maxSize=32`. A JVM system property can be passed before the TestContext framework initializes:

```text
-Dspring.test.context.cache.maxSize=64
```

Do not immediately bump `maxSize` when seeing a "not active" error; first check for `@DirtiesContext`/parallel races and context key variations. Raising cache size relieves LRU thrashing when memory permits, **without fixing shared mock reset races**.

### 19.1. Failure Threshold vs Context Cache Hit

Spring Framework 6.1+ sets a default context failure threshold of **1** per key: if context startup fails once, subsequent attempts may skip early with `IllegalStateException`. This is **not** caching a healthy context. When logs report threshold exceeded, find the **first root-cause startup failure**. Never crank up the failure threshold just to let CI repeat a broken configuration.

## 20. Cases Where @DirtiesContext Should Be Kept

Some tests genuinely need context rebuilds:

1. Modifying bean definitions or the factory environment in ways that cannot be restored.
2. Intentionally testing `ApplicationContext` lifecycle, stopping/restarting bean infrastructure.
3. Global Spring container reconfiguration that cannot be reversed via bean APIs.
4. Corrupting internal singleton caches lacking safe resets where other behavior depends on a clean context.
5. Closing/restarting embedded infrastructure tied to context lifecycle, invalidating the bean graph.

In those cases:

- Use method-level dirtying if only one method alters the context.
- Use `AFTER_CLASS` if the whole class mutates it.
- Use `BEFORE_CLASS` when needing a fresh context, and clean up after the class if it also dirties state.
- Consider a cache key variant to isolate a test configuration with different needs.
- Run serially with tests sharing the key or shared resources.
- Measure startup impact instead of adding `@DirtiesContext` unconditionally.
- Never trust `@DirtiesContext` to wipe external DB/Kafka data or static state.

**Distinguishing example:** a test flips a feature-flag singleton with a reliable `restore()` API → restoring in `finally` is better. A test mutates `BeanFactory` definitions leaving the graph inconsistent → `@DirtiesContext` may be the right choice.

## 21. Practice Exercises and Answers

### A. Two Classes with Identical @SpringBootTest and @MockitoBean

Are they guaranteed to get two separate mock instances?

**No.** If the effective context key matches and hits the cache, they can share the same `ApplicationContext` and mock bean. Default reset isolates *sequential tests*, but does not turn the mock into a per-method instance.

### B. Adding @DirtiesContext to Every Method to Clear Stubs

Should you do this?

**No.** `@MockitoBean`'s default `MockReset.AFTER` resets stubbings/invocations after each method without rebuilding the context. Only dirty when the context itself is genuinely unsafe.

### C. Test A Dirties AFTER_CLASS While Test B Uses the Same Context

What can happen?

**The context closes while B is using it**, causing intermittent "not active"/bean lifecycle errors. Avoid parallel overlap; never expect `@DirtiesContext` to wait for all in-flight requests/threads.

### D. Two Classes Mock the Same Type with Different Field Names

Can this trigger extra context startups?

**Yes.** The field name can act as a fallback qualifier and change the cache key. Use consistent names or an explicit bean name when targeting the same bean.

### E. @MockitoBean Creates a Mock Even Though the Real Bean Never Existed

Why?

Default `REPLACE_OR_CREATE`. When you must verify a production bean exists, set `enforceOverride=true` to fail fast if absent.

### F. @MockitoSpyBean on a Prototype Bean

Is this supported in Framework 6.2's test override facility?

**Not as a general mechanism**; overrides target singleton beans. Spies also require exactly one existing candidate.

### G. Non-Static @TestBean Factory Method

Is this valid?

**No.** The factory must be `static`, zero-arg, with a compatible return type. Provide an explicit `methodName` to avoid convention ambiguity.

### H. Does Transaction Rollback Reset a Singleton Map?

**No.** DB rollback does not clear in-memory singleton fields. Use a dedicated reset/clear, or dirty the context if recovery is impossible.

### I. Does JUnit @ResourceLock Lock Across Gradle Forks?

**No.** It coordinates scheduling inside a single Jupiter execution plan, not across JVM processes. Shared external resources need separate isolation.

### J. maxSize 32 Filled Up and an Old Context Reloaded

Did a test necessarily mark it dirty?

**Not necessarily.** LRU eviction can close entries due to capacity. Inspect cache `DEBUG` stats.

### K. Switching Test Profile from "unit" to "integration"

Is the context still shared?

Normally **no**; active profiles are part of the cache key. Separate contexts alone do not mean parallel tests are safe if both still hit the same external DB/broker.

### L. Method @DirtiesContext(BEFORE_METHOD)

Does it clean up database records from a Testcontainers Postgres instance shared across classes?

**No.** It only invalidates the Spring context. External DB state needs dedicated transactions/SQL/schema cleanup.

### M. MockitoBean(reset=NONE) and Parallel Execution

Does this solve races?

**No.** Disabling reset does not prevent stubbing/verifying from clobbering each other. It also creates greater leakage across sequential methods sharing the mock. Proper isolation or serial execution is what matters.

### N. Can a @TestBean Fake Be Shared Across Two Classes?

**Yes.** If override metadata and context keys match, the fake singleton lives inside the reused context; keep fakes stateless or reset them reliably.

### O. Does @Isolated Replace @DirtiesContext?

**No.** `@Isolated` (JUnit Jupiter) controls scheduling isolation for a class within an execution plan; `@DirtiesContext` controls Spring context invalidation. A test may need one, both, or neither depending on state/lifecycle.

## 22. QA Checklist Before Enabling Parallelism or Adding Bean Overrides

- [ ] Understand that Spring TestContext cache shares the actual `ApplicationContext` instance.
- [ ] Do not confuse JUnit's per-method test instance with Spring singleton lifecycles.
- [ ] Determine whether context keys match or differ based on classes/profiles/properties/customizers.
- [ ] Keep mock override targets/names/qualifiers consistent when sharing is intended.
- [ ] Verify `@MockitoBean` default `AFTER` reset has the proper test listeners active.
- [ ] Do not use `@DirtiesContext` merely to clear stubbings/invocations.
- [ ] Use `@MockitoBean(enforceOverride=true)` when proving an existing bean is replaced.
- [ ] Ensure `@MockitoSpyBean` targets exactly one existing singleton and avoid side-effect stubbing.
- [ ] Verify `@TestBean` static factory/bean names are accurate and fakes do not leak mutable state.
- [ ] Follow Spring's guidance not to run tests with Dirties/Mockito overrides in parallel without strong isolation.
- [ ] Never assume `@ResourceLock` locks all tests or spans JVM forks.
- [ ] Never mistake `@Execution(SAME_THREAD)` for suite-wide serialization.
- [ ] Ensure shared mutable beans have reliable cleanup in `finally`/`@AfterEach`.
- [ ] Isolate/clean DB/Kafka/File state independently rather than relying on context dirtying.
- [ ] Restore `ThreadLocal`/MDC/global system properties.
- [ ] Explore reset/clear mechanisms before deciding to rebuild `ApplicationContext`.
- [ ] When using `@ContextHierarchy`, review `hierarchyMode` and `contextName`.
- [ ] Ensure test classes using `@DirtiesContext` never overlap with tests using the same context.
- [ ] Account for cache capacity/LRU/forks causing reloads outside `@DirtiesContext`.
- [ ] Trace context failure-threshold errors back to the first startup failure.
- [ ] Avoid asserting absolute cache hit counts that depend on test ordering.
- [ ] Measure test duration, startup counts, flakiness, and memory on the real CI environment.
- [ ] Verify CI reports show accurate executed/failed/skipped method counts.
- [ ] Ensure test fixtures contain no real credentials or production data.
- [ ] Cross-check Java 17+/Boot 3.5/Framework 6.2 imports.
- [ ] When upgrading to Boot 4/Framework 7, re-verify tests against updated APIs.
- [ ] Complement mocked tests with integration tests protecting real collaborator behavior.
- [ ] Never force all tests to share a context when they have conflicting semantic needs.
- [ ] Never scatter `@DirtiesContext` everywhere as a blanket "isolation optimization".
- [ ] Identify tests hitting shared services across multiple JVMs/parallel tasks.

## 23. Summary

**`@DirtiesContext` and bean overrides solve different problems.**

- Spring TestContext's cache stores **the exact `ApplicationContext` instance** by key; different test classes can share the same singleton beans.
- `@MockitoBean`, `@MockitoSpyBean`, and `@TestBean` contribute **bean override metadata to the cache key**; identical overrides can share the overridden context.
- `@MockitoBean` resets after each test method by default (`MockReset.AFTER`), yet resetting a mock **does not close the context** and **is not concurrency-safe**.
- `@DirtiesContext` evicts/closes the context so the next lookup reloads; it is far costlier than resetting bean/mock/DB state.
- Spring Framework 6.2 advises against running `@DirtiesContext`, `@MockitoBean`, and `@MockitoSpyBean` tests in parallel due to the risk of resetting/closing while another test shares the context.
- JUnit scheduling controls help, provided you respect their boundaries—especially forked JVMs and external resources.
- Dirty only when state/context is genuinely unsafe to keep; otherwise favor isolated fixtures and boundary-aligned cleanup.

The accompanying 10-method JUnit example using Java 17+, Boot 3.5.16, and Framework 6.2 demonstrates effective-key reuse, mock overrides differing from plain contexts, profile variation, `@TestBean` replacement, shared counter state, and controlled `@DirtiesContext` eviction. This is a **test design grounded in API documentation**, without claiming compilation or JUnit execution during authoring.

## Official References

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache, keys, maxSize 32/LRU, and DEBUG statistics.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): test groups to avoid parallelizing, context no longer active.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): method/class modes, hierarchy clearing.
- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): overrides, qualifiers, resets, and cache keys.
- [Spring Framework 6.2 — @TestBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testbean.html): static factory replacement.
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): `REPLACE`/`REPLACE_OR_CREATE`/`WRAP`, lifecycle.
- [Spring Framework 6.2 — TestContextManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/TestContextManager.html): lifecycle methods and context access.
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html): failure threshold.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, context setup, and slices.
- [JUnit 5 — Parallel Execution](https://docs.junit.org/5.13.0/user-guide/#writing-tests-parallel-execution): `@ResourceLock`, `@Isolated`, execution modes, and resource scheduling.