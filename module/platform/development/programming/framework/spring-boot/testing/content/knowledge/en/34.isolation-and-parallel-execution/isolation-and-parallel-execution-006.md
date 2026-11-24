# Shared Static Fields, System Properties, Locale, and TimeZone

Under **Isolation and Parallel Execution** in the **Spring Boot - testing** module, a test can pass on its own yet fail when the full suite runs concurrently. A common culprit is **state living outside the test's scope**: a `static` field can survive for the life of the JVM, `System.setProperty` alters configuration for every thread in the process, and `Locale.setDefault` and `TimeZone.setDefault` mutate defaults implicitly read by many libraries. Spring also has its **TestContext cache**, singleton beans, and resource lifecycles; instantiating a new test object does not automatically reset any of those.

For example, one test sets `Locale.setDefault(Locale.FRANCE)` to test number formatting; another expects US decimal points. Running sequentially may pass, while running in parallel turns commas vs periods into a lottery determined by thread scheduling. Likewise, a test changing `System.setProperty("app.feature.enabled", "true")` and forgetting to restore the previous value alters another test's behavior. A `static final AtomicInteger`, though thread-safe to increment, still **shares values across tests** and leaks state.

This lesson presents a prioritized approach:

1. **Avoid JVM global state** via dependency injection: pass `Locale`, `ZoneId`, and `Clock`, scope services/sequences appropriately, and inject configuration instead of calling `System.getProperty` deep inside business logic.
2. When a test **must** alter a JVM default, snapshot the original value, mutate within the shortest possible scope, and restore in `finally` or `AutoCloseable.close()`, even if assertions fail.
3. When JUnit Jupiter runs in parallel, declare `@ResourceLock` with `Resources.SYSTEM_PROPERTIES`, `Resources.LOCALE`, `Resources.TIME_ZONE` and `READ_WRITE` or `READ` mode on tests sharing the resource; use `@Isolated` when an entire test class must run alone.
4. Understand **coordination limits**: JUnit resource locks coordinate only tests declaring the same key inside the same JUnit engine; they do not govern manually spawned threads, other test frameworks, or separate JVM forks.
5. Use `ApplicationContextRunner.withPropertyValues`, `@SpringBootTest(properties=...)`, and `@TestPropertySource` for Spring configuration rather than mutating global System properties to "simulate" each environment.
6. Test formatting/time calculations with `java.time` and explicit test fixtures instead of relying on a laptop's or CI runner's locale/timezone.
7. Distinguish **thread safety**, **test isolation**, **determinism**, and **cleanup**: one mechanism does not automatically provide the other three.

Examples use **Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, and Gradle**. They include standalone Java SE code runnable with `javac`/`java` with **exact stdout**, JUnit unit tests, and Spring Boot context tests. Anti-pattern snippets are labeled and must not be treated as production guidance.

## 1. Matrix of Where State Lives

| State | Actual Scope | Lifetime | Parallel Execution Risk |
| --- | --- | --- | --- |
| Local variable | Single invocation/thread stack | Duration of method | Low unless escaped as a shared object |
| JUnit `PER_METHOD` test instance field | One test instance | Per method instance | Can hold shared injected/external objects |
| Mutable static field | Classloader/JVM | Until class unloaded/process ends | State leak; data race if unsynchronized |
| `System.getProperties()` | JVM-global `Properties` | Entire process | Property write by one test affects others |
| `Locale.getDefault()` | JVM-global default | Until changed/reset/JVM exit | Number/date/case formatting shifts unexpectedly |
| `Locale.Category.FORMAT/DISPLAY` | JVM-global category defaults | Until changed | `FORMAT` differs from `DISPLAY`/general |
| `TimeZone.getDefault()` | Cached JVM default time zone | Until changed/cache cleared | Timestamps and legacy date output change |
| `ZoneId.systemDefault()` | Reads JVM default time zone at call time | Each call may observe a different default | Test depends on host/mutations |
| Spring singleton bean | One `ApplicationContext` | Until context close/eviction | Context cache can share mutable beans |
| Spring TestContext cache | Test JVM process, by cache key | Across compatible test classes/contexts | Other classes can reuse the context |
| Filesystem/DB/broker | External to JVM | Per resource ownership/TTL | `@ResourceLock` does not lock external services |
| Static `ThreadLocal` | One value per thread | Can survive across thread-pool reuse | Leaks principal/trace/MDC into the next task |

**Distinguishing mutable and immutable statics:** `static final String NAME = "catalog"` or an immutable formatter can be shared safely. `static final Map<String, String> CACHE = new HashMap<>()` is still mutable. The `final` keyword only prevents reassigning the field reference; it **does not make the referenced object immutable**.

## 2. Why Resetting in @BeforeEach Can Still Be Insufficient

An anti-pattern:

```java
class FlakyCounterTest {
    private static int counter;

    @BeforeEach
    void reset() {
        counter = 0;
    }

    @Test
    void first() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void second() {
        counter++;
        assertEquals(1, counter);
    }
}
```

This is an **illustrative broken snippet**, requiring JUnit imports. Running sequentially may pass, but if JUnit runs both methods concurrently, one test's `@BeforeEach` can reset `counter` right as the other increments it. Even switching to `AtomicInteger` to eliminate the increment data race still leaves **both tests sharing one counter**, breaking isolation.

Distinguish clearly:

- **Thread safety:** `AtomicInteger.incrementAndGet()` is atomic; two threads will not lose updates.
- **Test isolation:** each test starts with its own counter. A static `AtomicInteger` does **not** provide this.
- **Determinism:** a test does not depend on random method or thread execution ordering.
- **Cleanup:** post-test state is restored properly, including when a test fails.

The preferred solution is **not creating static mutable state** for business logic or test fixtures; use instance-level or explicitly scoped state. When legacy static state is unavoidable, use test isolation/locks and a safe reset API, recognizing it as a transitional workaround rather than an ideal design.

## 3. JUnit Creates New Test Instances by Default, Not a New JVM

JUnit Jupiter defaults to `@TestInstance(Lifecycle.PER_METHOD)`: each test method gets a fresh instance. However, it **does not spawn a new JVM** or reload classes normally:

```text
JUnit test JVM
  |
  +-- SomeTest instance #1 -> @Test method A
  |
  +-- SomeTest instance #2 -> @Test method B
  |
  +-- shared MyClass.staticField
  +-- shared System.properties
  +-- shared Locale.default
  +-- shared TimeZone.default
  +-- potentially cached Spring ApplicationContext
```

Using `@TestInstance(PER_CLASS)` causes instance fields to be shared across methods as well, bringing additional concurrency/lifecycle considerations. JUnit generally avoids running `PER_CLASS` methods in parallel unless configured/annotated to do so; never rely on that as a suite-wide locking mechanism.

**Do not treat `@BeforeEach` as an automatic rollback.** If test code alters a system property or default locale, JUnit does not automatically restore them when the test instance is discarded. `@AfterEach` can restore state, yet if cleanup is skipped on severe failures (process kill) or unmanaged async tasks remain active, state/resources can still diverge. Scoping via `try-with-resources` right around the mutation minimizes risk.

## 4. System Properties Are JVM-Wide Configuration

Core pattern:

```java
String old = System.getProperty("lesson.feature.enabled");

try {
    System.setProperty("lesson.feature.enabled", "true");
    // Verify behavior depending on the property.
} finally {
    if (old == null) {
        System.clearProperty("lesson.feature.enabled");
    } else {
        System.setProperty("lesson.feature.enabled", old);
    }
}
```

**Notes:**

- `System.setProperty` is **not thread-scoped**. Any code in the same JVM reading that property key sees the new value, including parallel tests.
- `System.clearProperty` is correct only when the property was **previously absent**. If it originally held `"false"`, cleanup must restore `"false"`, not delete it.
- `System.setProperties(new Properties())` replaces the **entire** JVM property set and can wipe critical Java/Spring/Gradle properties; never do this to reset one key.
- System properties act as a property source in Spring's `Environment`, yet bean conditions and constructor-bound configuration are usually evaluated at context creation time. Changing a property **after** Spring context refresh does not recreate beans or rebind all properties.
- Tests wanting to alter `user.timezone` should not simply set the property and assume all date/time APIs pick up the new zone: `TimeZone` maintains its own cache.

**Safer approach:** supply properties via `ApplicationContextRunner.withPropertyValues(...)` or `@SpringBootTest(properties=...)` instead of mutating the entire JVM.

## 5. Locale: General Default and Two Category Defaults

Java 17 provides:

```java
Locale general = Locale.getDefault();

Locale display =
        Locale.getDefault(Locale.Category.DISPLAY);

Locale format =
        Locale.getDefault(Locale.Category.FORMAT);
```

- **General default**: `Locale.getDefault()`, used by many APIs when none is specified.
- **DISPLAY**: default locale used for displaying language/country names and localization UI strings.
- **FORMAT**: locale used for formatting numbers/dates/times per category.
- `Locale.setDefault(Locale.US)` sets the general default and affects category defaults; if separate overrides existed, snapshot **all three** and restore them in the proper order.
- `Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE)` modifies the `FORMAT` category without automatically changing the general/display default to FR.
- Changing `System.setProperty("user.language", "vi")` **after the JVM has initialized the default Locale** does not refresh the default `Locale` object; understand initialization/caching or call `Locale.setDefault`. Best of all, avoid relying on defaults in business logic.

**Formatting trap:**

```java
NumberFormat.getNumberInstance()
```

uses the default locale; separators can differ across machines. Tests should not assert strings formatted with host defaults. Use:

```java
NumberFormat.getNumberInstance(
        Locale.forLanguageTag("vi-VN"))
```

when formatting specifically for Vietnamese users. CLDR/JDK locale data formatting details can still shift across JDK versions, so for snapshot tests, define explicit contracts and version policies.

**Case conversion:** `someText.toLowerCase()` uses the default locale; for identifiers/protocol keys, use `toLowerCase(Locale.ROOT)` or `equalsIgnoreCase` per contract. Never normalize API keys or slugs using the default locale without specifying a locale.

## 6. TimeZone.default, user.timezone, and ZoneId

Java 17 has two layers that are easily confused:

```java
String property = System.getProperty("user.timezone");
TimeZone zone = TimeZone.getDefault();
ZoneId zoneId = ZoneId.systemDefault();
```

- `user.timezone` is a system property. The JVM uses it when computing the default time zone if none is cached yet or the cache was cleared; it is not a live source-of-truth re-read on every call.
- `TimeZone.getDefault()` returns a clone of the cached default `TimeZone`; the cached default can be changed with `TimeZone.setDefault(...)`.
- `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` changes the JVM default time zone without **automatically updating `user.timezone`**.
- Setting `System.setProperty("user.timezone", "Asia/Tokyo")` **does not guarantee** `TimeZone.getDefault()` changes immediately while a cached default exists.
- `TimeZone.setDefault(null)` clears the cached default so the next lookup recomputes from system properties/environment; this is a **global mutation** and should not be used recklessly in test suites.
- `ZoneId.systemDefault()` reads the JVM default time zone at the moment it is called; a previously stored `ZoneId` does not mutate on its own.
- `TimeZone.getTimeZone("Wrong/Zone")` silently falls back to GMT; `ZoneId.of("Wrong/Zone")` throws an exception, which is helpful for strict config validation.

**Preferred in application code:**

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime local = instant.atZone(zone);
```

When formatting an instant for a user/tenant, the zone should come from configuration or user profile data, never from the CI runner. When needing "now", inject `Clock`; never call `Instant.now()` deep inside logic and expect tests to freeze time.

## 7. DST Rules and Why You Should Never Hard-Code Offsets

`Asia/Ho_Chi_Minh` is UTC+07 in the modern period of these examples, yet **`ZoneId`** represents historical and future time-zone rules, not just a constant offset. Zones like `Europe/Berlin` observe Daylight Saving Time (DST), where clock transitions create ambiguous or nonexistent local times.

- `Instant` represents an absolute point in time; `LocalDateTime` **carries no zone/offset** and cannot map unambiguously to an instant without zone/DST overlap/gap policies.
- `OffsetDateTime` holds a specific UTC offset; `ZonedDateTime` holds full zone rules.
- `Clock.fixed(instant, zone)` works well for testing "now"; `DateTimeFormatter.withZone(zone)` provides deterministic formatting.
- If DST handling is required, test **instants before and after transitions** with an explicit `ZoneId` and the JDK's zone rules. Never assert every local day has exactly 24 hours.
- Never use `TimeZone.getDefault()` to compute financial deadlines or schedules on an arbitrary CI machine.

## 8. Principle: Moving from Global State to Injection

From a failure-prone design:

```java
public String createdAtLabel() {
    return LocalDateTime.now().toString()
            + " " + Locale.getDefault();
}
```

to explicit dependencies:

```java
public final class TimestampLabel {
    private final Clock clock;
    private final ZoneId zone;
    private final Locale locale;

    public TimestampLabel(
            Clock clock, ZoneId zone, Locale locale) {
        this.clock = clock;
        this.zone = zone;
        this.locale = locale;
    }

    public String value() {
        ZonedDateTime value =
                ZonedDateTime.ofInstant(
                        clock.instant(), zone);
        return value.getYear() + "-"
                + value.getMonthValue() + " ["
                + locale.toLanguageTag() + "]";
    }
}
```

The snippet above is **complete for the class body** but needs imports from `java.time`/`java.util`. The full example below provides complete packaged files with imports and JUnit tests.

**Significance:** tests instantiate `Clock.fixed(...)`, `ZoneId.of(...)`, and `Locale.forLanguageTag(...)` without mutating globals. Two tests can run concurrently because each instance owns its own dependencies, provided collaborators hold no other mutable state.

## 9. Source Structure and build.gradle

Structure of a Java 17 Spring Boot module:

```text
src/
├── main/java/example/isolation/
│   ├── IsolationApplication.java
│   ├── ReportSettings.java
│   ├── ReportConfiguration.java
│   ├── InvoicePrinter.java
│   ├── ReportStamp.java
│   ├── SequenceCounter.java
│   └── DefaultsDemo.java
├── test/java/example/isolation/
│   ├── InvoicePrinterTest.java
│   ├── SequenceCounterTest.java
│   ├── JvmDefaultsScope.java
│   ├── JvmSharedDefaultsTest.java
│   ├── ReportConfigurationRunnerTest.java
│   └── ReportContextTest.java
└── test/resources/
    └── junit-platform.properties
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
}
```

Uses Spring Boot 3.5.x, JUnit Jupiter 5.x from Boot's BOM, and Java 17+. The Gradle plugins are a demo choice; if a project already defines Spring Boot plugins/BOM, align dependency versions consistently. The test suite requires no server, database, Docker, or cloud accounts. `./gradlew` commands assume a compatible Gradle Wrapper already exists (`build.gradle` does not generate the wrapper).

**No global System properties are set in the build file** to secretly "force" all tests onto one timezone. When an app enforces a UTC policy, configure it explicitly and still test places that must support multiple zones.

## 10. InvoicePrinter.java: Explicit Locale and Zone

Create `src/main/java/example/isolation/InvoicePrinter.java`:

```java
package example.isolation;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class InvoicePrinter {
    private final Locale locale;
    private final DateTimeFormatter formatter;

    public InvoicePrinter(Locale locale, ZoneId zone) {
        this.locale = locale;
        this.formatter = DateTimeFormatter
                .ofPattern("yyyy-MM-dd HH:mm XXX", locale)
                .withZone(zone);
    }

    public String render(Instant instant) {
        return formatter.format(instant)
                + " [" + locale.toLanguageTag() + "]";
    }
}
```

`DateTimeFormatter` is immutable and thread-safe; each printer holds a formatter built with an explicit **Locale + ZoneId**. It never queries `Locale.getDefault()` or `ZoneId.systemDefault()` during rendering, so formatting cannot be altered by another test mutating JVM globals.

**Output meaning:**

- For instant `2024-02-29T17:00:00Z`, UTC renders `2024-02-29 17:00 Z`.
- For `Asia/Ho_Chi_Minh`, the exact same instant becomes `2024-03-01 00:00 +07:00`.
- The `[en-US]` or `[vi-VN]` suffix is the instance's locale tag, not the system locale.
- Numeric date patterns keep stdout stable; localized month/day names in CLDR can vary across JDK/locale-provider versions when not pinned by contract.

**Never substitute** `static SimpleDateFormat`: `SimpleDateFormat` is mutable and not thread-safe, making it unsafe to share across threads. `DateTimeFormatter` is the right choice for Java 17.

## 11. Injecting Clock to Test "Now"

Create `src/main/java/example/isolation/ReportStamp.java`:

```java
package example.isolation;

import java.time.Clock;

public final class ReportStamp {
    private final Clock clock;
    private final InvoicePrinter printer;

    public ReportStamp(Clock clock, InvoicePrinter printer) {
        this.clock = clock;
        this.printer = printer;
    }

    public String nowLabel() {
        return printer.render(clock.instant());
    }
}
```

Production can provide `Clock.systemUTC()` in Spring configuration if needed. Tests use `Clock.fixed(Instant.parse(...), ZoneOffset.UTC)` without sleeping or mutating system clocks/timezones. Given the same fixed instant, output stays identical even when JUnit runs on hosts with different default timezones.

## 12. SequenceCounter.java: Replacing Mutable Static State with an Instance

Create `src/main/java/example/isolation/SequenceCounter.java`:

```java
package example.isolation;

import java.util.concurrent.atomic.AtomicInteger;

public final class SequenceCounter {
    private final AtomicInteger next = new AtomicInteger();

    public int next() {
        return next.incrementAndGet();
    }
}
```

This counter is thread-safe **within one instance**, and each instance owns separate state. JUnit creates a fresh counter per test, avoiding static resets. If production needs a **cross-process global sequence**, `AtomicInteger` is insufficient: use a database sequence/ID generator with its own contract.

An anti-pattern to avoid:

```java
public final class LeakySequence {
    private static final AtomicInteger NEXT =
            new AtomicInteger();

    public static int next() {
        return NEXT.incrementAndGet();
    }
}
```

This code has thread-safe increments yet is **not isolated across tests**. Do not add a `reset()` for tests and run in parallel without coordination; prefer replacing the static design with an instance or injecting a `SequenceCounter` with an explicit scope/lifecycle.

## 13. ReportSettings and ReportConfiguration: Binding Without Touching Globals

Create `src/main/java/example/isolation/ReportSettings.java`:

```java
package example.isolation;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.report")
public record ReportSettings(
        @DefaultValue("en-US") String localeTag,
        @DefaultValue("UTC") String zoneId) {
}
```

Create `src/main/java/example/isolation/ReportConfiguration.java`:

```java
package example.isolation;

import java.time.Clock;
import java.time.ZoneId;
import java.util.Locale;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportSettings.class)
public class ReportConfiguration {

    @Bean
    InvoicePrinter invoicePrinter(ReportSettings settings) {
        Locale locale =
                Locale.forLanguageTag(settings.localeTag());
        if (locale.getLanguage().isBlank()) {
            throw new IllegalArgumentException(
                    "invalid report locale");
        }

        ZoneId zone = ZoneId.of(settings.zoneId());
        return new InvoicePrinter(locale, zone);
    }

    @Bean
    Clock reportClock() {
        return Clock.systemUTC();
    }

    @Bean
    ReportStamp reportStamp(
            Clock reportClock, InvoicePrinter invoicePrinter) {
        return new ReportStamp(reportClock, invoicePrinter);
    }

    @Bean
    SequenceCounter sequenceCounter() {
        return new SequenceCounter();
    }
}
```

**Key points:**

- The Spring Boot binder reads `app.report.locale-tag`/`app.report.zone-id` and constructs `ReportSettings`.
- The factory builds `Locale` and `ZoneId` explicitly without calling `Locale.setDefault` or `TimeZone.setDefault`.
- `ZoneId.of("Wrong/Zone")` fails bean construction fast rather than silently falling back to GMT on misconfiguration.
- `Clock.systemUTC()` is the production clock; unit tests can instantiate `ReportStamp(Clock.fixed(...), ...)`. Changing the system timezone does not alter the `Instant` returned by `Clock.systemUTC()`.
- `SequenceCounter` is a singleton per Spring context under default scope. It is **not static**, yet two test classes sharing the same cached Spring context still share **the same singleton counter**. If you need a per-test counter, instantiate it directly in unit tests or adjust bean scope/context lifecycle contracts instead of assuming every test class gets a fresh Spring singleton.

Create `src/main/java/example/isolation/IsolationApplication.java`:

```java
package example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                IsolationApplication.class, args);
    }
}
```

Spring Boot component scanning detects `ReportConfiguration` in the same package. The demo uses no web dependencies; testing with `@SpringBootTest(webEnvironment=NONE)` still verifies real wiring.

## 14. InvoicePrinterTest.java: Three Deterministic Unit Tests

Create `src/test/java/example/isolation/InvoicePrinterTest.java`:

```java
package example.isolation;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Locale;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InvoicePrinterTest {
    private static final Instant FIXED =
            Instant.parse("2024-02-29T17:00:00Z");

    @Test
    void utcUsesExplicitZone() {
        InvoicePrinter printer = new InvoicePrinter(
                Locale.US, ZoneOffset.UTC);

        assertEquals(
                "2024-02-29 17:00 Z [en-US]",
                printer.render(FIXED));
    }

    @Test
    void vietnamZoneDoesNotDependOnHostTimeZone() {
        InvoicePrinter printer = new InvoicePrinter(
                Locale.forLanguageTag("vi-VN"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                "2024-03-01 00:00 +07:00 [vi-VN]",
                printer.render(FIXED));
    }

    @Test
    void fixedClockMakesNowLabelDeterministic() {
        Clock clock = Clock.fixed(
                FIXED, ZoneOffset.UTC);

        ReportStamp stamp = new ReportStamp(
                clock,
                new InvoicePrinter(
                        Locale.US, ZoneOffset.UTC));

        assertEquals(
                "2024-02-29 17:00 Z [en-US]",
                stamp.nowLabel());
    }
}
```

**Three methods**, free of `System.setProperty`, `Locale.setDefault`, `TimeZone.setDefault`, or `Thread.sleep`. These tests are safe to run concurrently with each other because they use only immutables and separate objects.

The right way to test is not forcing the host to run with `TZ=UTC` and assuming business logic handles every timezone, but injecting each scenario's zone directly and asserting the expected output for a specific instant.

## 15. SequenceCounterTest.java: True Test Isolation

Create `src/test/java/example/isolation/SequenceCounterTest.java`:

```java
package example.isolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SequenceCounterTest {

    @Test
    void firstTestGetsFreshSequence() {
        SequenceCounter counter = new SequenceCounter();

        assertEquals(1, counter.next());
        assertEquals(2, counter.next());
    }

    @Test
    void secondTestAlsoGetsFreshSequence() {
        SequenceCounter counter = new SequenceCounter();

        assertEquals(1, counter.next());
    }

    @Test
    void twoInstancesDoNotShareCounter() {
        SequenceCounter first = new SequenceCounter();
        SequenceCounter second = new SequenceCounter();

        assertEquals(1, first.next());
        assertEquals(1, second.next());
        assertEquals(2, first.next());
        assertEquals(2, second.next());
    }
}
```

**Three methods**, independent of JUnit method ordering. Only a single `AtomicInteger` belongs to each instance, so both concurrency **and** isolation hold within the class scope.

**What this does not prove:** that the counter produces unique IDs across Spring contexts, JVM processes, or cluster nodes. If the business domain requires system-wide unique IDs, rely on DB sequences/UUID/ULID or a distributed generator rather than a static counter.

## 16. When JVM Globals Must Change: Snapshot/Restore Helper

Some legacy APIs only read the default `Locale`/`TimeZone` or System properties, requiring controlled mutation in tests. Create a **test-only** helper to snapshot exact state and restore it on every exit path.

Create `src/test/java/example/isolation/JvmDefaultsScope.java`:

```java
package example.isolation;

import java.util.Locale;
import java.util.TimeZone;

final class JvmDefaultsScope implements AutoCloseable {
    private final String key;
    private final String oldKeyValue;
    private final String oldTimezoneProperty;
    private final Locale oldGeneral;
    private final Locale oldDisplay;
    private final Locale oldFormat;
    private final TimeZone oldZone;

    JvmDefaultsScope(String key) {
        this.key = key;
        this.oldKeyValue = System.getProperty(key);

        // Capture property before getDefault(): the JDK may
        // initialize the default zone and populate user.timezone.
        this.oldTimezoneProperty =
                System.getProperty("user.timezone");

        this.oldGeneral = Locale.getDefault();
        this.oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        this.oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        this.oldZone = TimeZone.getDefault();
    }

    private static void restore(
            String property, String previous) {
        if (previous == null) {
            System.clearProperty(property);
        } else {
            System.setProperty(property, previous);
        }
    }

    @Override
    public void close() {
        try {
            restore(key, oldKeyValue);
        } finally {
            try {
                // setDefault(Locale) can affect both FORMAT and
                // DISPLAY, so restore categories afterward.
                Locale.setDefault(oldGeneral);
                Locale.setDefault(
                        Locale.Category.DISPLAY, oldDisplay);
                Locale.setDefault(
                        Locale.Category.FORMAT, oldFormat);
            } finally {
                try {
                    TimeZone.setDefault(oldZone);
                } finally {
                    restore(
                            "user.timezone", oldTimezoneProperty);
                }
            }
        }
    }
}
```

**Helper breakdown:**

1. Snapshots the value **of the exact property key** modified by the test, distinguishing **missing** (`null`) from `"false"`.
2. Snapshots general `Locale`, `DISPLAY` `Locale`, and `FORMAT` `Locale` intact without assuming they match.
3. Snapshots `user.timezone` before `TimeZone.getDefault()` because initializing the default zone can populate that property.
4. Snapshots `TimeZone.getDefault()` and restores it via `TimeZone.setDefault(oldZone)`.
5. Wraps each cleanup step in `finally` so a failure in an earlier step does not skip later steps.
6. Never calls `System.setProperties(...)` and never replaces the JVM property map with a clone.
7. This helper **does not provide true isolation across threads**. If another test reads the same global while the scope is open without declaring a lock, it still observes temporary state. Coordinate with JUnit locks or process isolation.

**Warning:** if the application itself has background workers reading locale/timezone or an uncooperative test runner, snapshot/restore cannot prevent mid-scope races. Hence the best strategy remains **not mutating globals**.

## 17. JUnit @ResourceLock: Coordinating JVM-Wide Resources

JUnit Jupiter defines `@ResourceLock` and standard constants in `org.junit.jupiter.api.parallel.Resources`:

- `Resources.SYSTEM_PROPERTIES` for Java System properties.
- `Resources.SYSTEM_OUT` and `Resources.SYSTEM_ERR` for reassigned standard output/error streams.
- `Resources.LOCALE` for default locale.
- `Resources.TIME_ZONE` for default time zone.
- `ResourceAccessMode.READ_WRITE`: excludes other tests declaring `READ` or `READ_WRITE` on the same key.
- `ResourceAccessMode.READ`: allows multiple readers concurrently, while excluding writers on the same key.

**This is advisory coordination among JUnit tests declaring the same key.** A test author forgetting a lock or a manually spawned thread accessing globals can still break isolation. When a test reads the default `Locale` and requires a stable value, it must also declare `READ` on the same resource key—not just the writer declaring `READ_WRITE`.

### JvmSharedDefaultsTest.java: Three Mutating Cases with Cleanup

Create `src/test/java/example/isolation/JvmSharedDefaultsTest.java`:

```java
package example.isolation;

import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
@ResourceLock(
        value = Resources.LOCALE,
        mode = ResourceAccessMode.READ_WRITE)
@ResourceLock(
        value = Resources.TIME_ZONE,
        mode = ResourceAccessMode.READ_WRITE)
class JvmSharedDefaultsTest {
    private static final String KEY =
            "lesson.feature.enabled";

    @Test
    void systemPropertyIsRestoredByScope() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            System.setProperty(KEY, "true");

            assertEquals("true",
                    System.getProperty(KEY));
        }
    }

    @Test
    void localeFormatCategoryCanDifferFromGeneral() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.FRANCE);

            assertEquals(Locale.US, Locale.getDefault());
            assertEquals(
                    Locale.FRANCE,
                    Locale.getDefault(
                            Locale.Category.FORMAT));
            assertEquals(
                    Locale.US,
                    Locale.getDefault(
                            Locale.Category.DISPLAY));
        }
    }

    @Test
    void cachedTimezoneNeedNotFollowUserTimezoneProperty() {
        try (JvmDefaultsScope ignored =
                     new JvmDefaultsScope(KEY)) {
            TimeZone.setDefault(
                    TimeZone.getTimeZone("UTC"));

            System.setProperty(
                    "user.timezone", "Asia/Tokyo");

            // TimeZone cache is set explicitly; changing the
            // property alone does not alter the cached default in JDK 17.
            assertEquals("UTC",
                    ZoneId.systemDefault().getId());
            assertEquals(
                    "Asia/Tokyo",
                    System.getProperty("user.timezone"));
        }
    }
}
```

**Three JUnit methods** using class-level resource locks. When JUnit runs concurrently with other tests **also declaring the same locks**, no conflicting writers/readers execute while this class's callbacks/lifecycle hold the locks. `try-with-resources` calls `JvmDefaultsScope.close()` even when assertions fail.

**No post-scope assertion compares against a specific machine's default**; the scope restores according to the snapshot rather than trying to force the JUnit process permanently to English/UTC. If you want to assert restoration, capture snapshots and verify inside the same locked test to avoid interference from uncooperative tests.

**Do not use this test as a template to mutate JVM defaults in every test.** It demonstrates testing legacy behavior, whereas `InvoicePrinterTest` is the design pattern to follow by default.

## 18. @Isolated and @Execution: Reading Protection Scopes Properly

JUnit Jupiter provides:

```java
@Isolated
class LegacyGlobalIntegrationTest {
    // @Test methods impacting many JVM-wide resources.
}
```

This is a **snippet** requiring `import org.junit.jupiter.api.parallel.Isolated`. `@Isolated` fits legacy test classes touching many hard-to-enumerate global resources that must not interleave with other tests in the same JUnit Jupiter execution. However, it **does not stop** already-running background threads, does not lock JVMs in other Gradle forks, and does not protect external databases/files across processes.

`@Execution(ExecutionMode.SAME_THREAD)` keeps methods within the class on the same thread/sequential per JUnit configuration; however, it **does not stop other classes** from running concurrently and mutating `System.properties`, `Locale`, or `TimeZone`. For shared resources, use `@ResourceLock`/`@Isolated` appropriately.

**`@TestInstance(PER_CLASS)`** does not replace `@ResourceLock`. It governs only the test instance lifecycle and creates no lock over JVM-global state.

### ResourceLock on a Single Method

If only one method mutates a system property, scope the lock to that method:

```java
@Test
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
void changesJvmPropertyTemporarily() {
    String old = System.getProperty("app.mode");

    try {
        System.setProperty("app.mode", "safe");
        assertEquals("safe",
                System.getProperty("app.mode"));
    } finally {
        if (old == null) {
            System.clearProperty("app.mode");
        } else {
            System.setProperty("app.mode", old);
        }
    }
}
```

This is a **snippet** requiring JUnit imports and an enclosing test class. JUnit locks also protect corresponding lifecycle methods per Jupiter's contract. When multiple tests **only read** properties, use `mode=READ` so they can run concurrently with each other while avoiding writers. Never use a custom key on a writer and `Resources.SYSTEM_PROPERTIES` on a reader: **mismatched keys do not coordinate**.

## 19. junit-platform.properties: Enabling Parallelism Intentionally

Create `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

With JUnit Jupiter, parallelism can be enabled via configuration. Concurrent default modes increase the odds of exposing unisolated tests. Yet running in parallel guarantees no specific interleaving and **does not prove business code is race-free** from a single pass.

**Things to watch out for:**

- `@ResourceLock` is a Jupiter scheduler mechanism effective only when tests run in an engine honoring lock declarations. It does not lock the whole process.
- Gradle `maxParallelForks > 1` spawns **multiple JVM processes**. Each process has separate System properties/Locale/TimeZone, yet JUnit locks **are not shared across JVMs**. Files, shared databases, or brokers can still contend.
- `forkEvery` or a separate fork isolates JVM-global state leaks across test groups, but incurs startup overhead and **does not replace external resource cleanup**.
- Classes with `@TestInstance(PER_CLASS)`, method ordering, or special semantics can alter execution modes; consult the JUnit user guide instead of assuming all methods run concurrently.
- Filtering with `--tests ...` in Gradle only filters test classes without changing properties/locale/timezone.
- Tests replacing `System.out`/`System.err` need `Resources.SYSTEM_OUT`/`SYSTEM_ERR` specifically.

## 20. Spring Boot: Use Config Properties Instead of System.setProperty

For testing Spring configuration, **avoid** doing:

```java
@BeforeAll
static void turnOn() {
    System.setProperty("app.report.zone-id", "UTC");
}
```

This is an anti-pattern because a JVM-global property can affect other tests and the Spring context may already be cached before the mutation.

**For a full Spring Boot integration test**, declare:

```java
@SpringBootTest(
        properties = {
                "app.report.locale-tag=vi-VN",
                "app.report.zone-id=Asia/Ho_Chi_Minh"
        })
class ReportContextTest {
    // Assert beans are configured from test properties.
}
```

This is a snippet; the runnable file below supplies full imports and class body. Test properties are placed into the context's `Environment` by Spring TestContext for that test's lifecycle, **without changing JVM default locale/timezone**.

**For configuration matrices** (many configurations), `ApplicationContextRunner` is usually faster and cleaner to isolate than multiple `@SpringBootTest` classes. It creates and closes a fresh context per `run()`. When Testcontainers dynamic ports are needed, `@DynamicPropertySource` suits Spring TestContext; never use it to mutate `TimeZone.setDefault` or other JVM globals.

**Property resolution differs from global mutation:** a context's `Environment` can override a system property via a test property source. However, code calling `System.getProperty("app.report.zone-id")` directly deep inside a service will **bypass Spring Environment overrides**. Therefore, business code should inject `ReportSettings` instead of reading System properties directly.

## 21. ReportConfigurationRunnerTest.java: Four Isolated Context Tests

Create `src/test/java/example/isolation/ReportConfigurationRunnerTest.java`:

```java
package example.isolation;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class ReportConfigurationRunnerTest {
    private static final Instant FIXED =
            Instant.parse("2024-02-29T17:00:00Z");

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ReportConfiguration.class);

    @Test
    void defaultsUseUtcAndEnglishWithoutJVMDefaults() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(
                    "2024-02-29 17:00 Z [en-US]",
                    context.getBean(
                            InvoicePrinter.class)
                            .render(FIXED));
        });
    }

    @Test
    void customPropertiesBindLocaleAndZone() {
        runner.withPropertyValues(
                        "app.report.locale-tag=vi-VN",
                        "app.report.zone-id=Asia/Ho_Chi_Minh")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "2024-03-01 00:00 +07:00 [vi-VN]",
                            context.getBean(
                                    InvoicePrinter.class)
                                    .render(FIXED));
                });
    }

    @Test
    void derivedRunnerDoesNotMutateBaseline() {
        runner.withPropertyValues(
                        "app.report.zone-id=Asia/Ho_Chi_Minh")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "2024-03-01 00:00 +07:00 [en-US]",
                            context.getBean(
                                    InvoicePrinter.class)
                                    .render(FIXED));
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(
                    "2024-02-29 17:00 Z [en-US]",
                    context.getBean(
                            InvoicePrinter.class)
                            .render(FIXED));
        });
    }

    @Test
    void invalidZoneFailsFastInsteadOfSilentGmt() {
        runner.withPropertyValues(
                        "app.report.zone-id=Wrong/Zone")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                });
    }
}
```

**Four JUnit methods**. Each `run(context -> ...)` creates and closes a fresh context. The baseline runner is immutable across `withPropertyValues` calls; the "derived runner" test runs both the override and the baseline to prove no property leaks across scenarios.

No `Locale.setDefault`, `System.setProperty`, or `TimeZone.setDefault` is used. This is the cleanest way to test Spring configuration in parallel. It does not claim the full production app booted; it validates only the configuration and bean graph registered with the runner.

## 22. ReportContextTest.java: Full Spring Context with Test Properties

Create `src/test/java/example/isolation/ReportContextTest.java`:

```java
package example.isolation;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = IsolationApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "app.report.locale-tag=vi-VN",
                "app.report.zone-id=Asia/Ho_Chi_Minh"
        })
class ReportContextTest {

    @Autowired
    InvoicePrinter printer;

    @Test
    void springTestPropertiesConfigurePrinter() {
        assertEquals(
                "2024-03-01 00:00 +07:00 [vi-VN]",
                printer.render(
                        Instant.parse("2024-02-29T17:00:00Z")));
    }
}
```

**One JUnit method** boots the Spring Boot test context and injects the real bean without mutating global defaults. If a production project adds MVC/data/security configurations, full context tests catch broader wiring, though this demo includes only formatting beans.

**Context cache caveat:** when another class uses an equivalent Spring test configuration, Spring may reuse the `ApplicationContext` (and its singleton beans). If one test mutates a singleton's state, other methods/classes can see the mutation. `@DirtiesContext` causes Spring to evict/close the dirty context, **yet does not restore System properties or JVM default Locale/TimeZone**. Do not misuse it as a "wipe everything" button when state leaks live outside Spring.

## 23. DefaultsDemo.java: Runnable Java 17 Program with Exact Stdout

Create `src/main/java/example/isolation/DefaultsDemo.java`:

```java
package example.isolation;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Locale;

public class DefaultsDemo {
    public static void main(String[] args) {
        Instant fixed =
                Instant.parse("2024-02-29T17:00:00Z");

        InvoicePrinter vietnam =
                new InvoicePrinter(
                        Locale.forLanguageTag("vi-VN"),
                        ZoneId.of("Asia/Ho_Chi_Minh"));

        InvoicePrinter utc =
                new InvoicePrinter(
                        Locale.US, ZoneOffset.UTC);

        System.out.println(vietnam.render(fixed));
        System.out.println(utc.render(fixed));

        SequenceCounter counter =
                new SequenceCounter();

        System.out.println(
                "seq=" + counter.next() + ","
                        + counter.next());
    }
}
```

Using **JDK 17+** at the project root without Gradle/Spring:

```bash
javac -d out src/main/java/example/isolation/InvoicePrinter.java src/main/java/example/isolation/SequenceCounter.java src/main/java/example/isolation/DefaultsDemo.java
java -cp out example.isolation.DefaultsDemo
```

**Exact** stdout on Java 17 with a timezone database supporting `Asia/Ho_Chi_Minh`:

```text
2024-03-01 00:00 +07:00 [vi-VN]
2024-02-29 17:00 Z [en-US]
seq=1,2
```

**Why is this deterministic?** It reads no global locale/timezone or wall clock, and spawns no worker threads printing in nondeterministic order. The instant is fixed, zone/locale are explicitly passed, and the counter is a local instance. The `javac` command compiles only Java SE files; Spring Boot classes are omitted so no external dependencies are required.

## 24. Summary of the 14 JUnit Tests and How to Run Them

| Test class | Methods | Scope |
| --- | ---: | --- |
| `InvoicePrinterTest` | 3 | Explicit locale/zone/Clock, no globals |
| `SequenceCounterTest` | 3 | Counter isolation, no static state |
| `JvmSharedDefaultsTest` | 3 | System property, locale category, cached timezone, ResourceLocks |
| `ReportConfigurationRunnerTest` | 4 | Spring property binding and context isolation |
| `ReportContextTest` | 1 | Real `SpringBootTest` wiring |
| **Total** | **14** | |

Run each class via Gradle wrapper:

```bash
./gradlew test --tests example.isolation.InvoicePrinterTest
./gradlew test --tests example.isolation.SequenceCounterTest
./gradlew test --tests example.isolation.JvmSharedDefaultsTest
./gradlew test --tests example.isolation.ReportConfigurationRunnerTest
./gradlew test --tests example.isolation.ReportContextTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.isolation.InvoicePrinterTest"
.\gradlew.bat test --tests "example.isolation.SequenceCounterTest"
.\gradlew.bat test --tests "example.isolation.JvmSharedDefaultsTest"
.\gradlew.bat test --tests "example.isolation.ReportConfigurationRunnerTest"
.\gradlew.bat test --tests "example.isolation.ReportContextTest"
```

**14 is the number of methods in the sample source**, not proof that JUnit ran on the learner's machine. Gradle/JUnit console output depends on version/runner. Only the Java SE demo in Section 23 has fixed deterministic stdout. When running the full suite in parallel mode, tests mutating globals require cooperative locks; all remaining tests use injection to avoid contention.

## 25. Spring TestContext Cache and Global State Are Two Separate Problems

A scenario:

```text
TestClass A:
  @SpringBootTest(properties="app.report.zone-id=UTC")
  -> cached context #1

TestClass B:
  same merged configuration
  -> may reuse context #1, same singleton beans

TestClass C:
  @SpringBootTest(properties="app.report.zone-id=Asia/Ho_Chi_Minh")
  -> different context cache key, usually separate context

Unrelated JUnit test:
  TimeZone.setDefault(UTC)
  -> affects JVM default of every live context
     if beans/calls read TimeZone.getDefault() at runtime
```

**Consequences:**

- `@SpringBootTest(properties=...)` is a property source/context setting. It does not change JVM-wide `user.timezone` or `Locale.getDefault()` unless application code itself does so.
- Context cache keys combine many components (classes/configs/profiles/properties/context customizers...), not just properties; you do not need to memorize the exact hashing algorithm to design tests cleanly.
- A singleton bean holding a mutable cache/list/shared state can leak across test classes sharing that context.
- `@DirtiesContext` merely marks a TestContext framework context dirty for recreation when needed; it does not "reset" static fields/System properties/locale/timezone.
- In a test-managed `@Transactional`, DB rollback binds a transaction to the test thread; it does not revert statics/Locale/TimeZone and does not automatically roll back an off-thread `@Async` worker transaction.
- `@ActiveProfiles` and `@TestPropertySource` build contexts with different profiles/properties; they do not replace resource locks for JVM globals.
- `@DynamicPropertySource` injects dynamic values into the Spring context (e.g., Testcontainers URLs) without locking external resources; when dynamic values vary across subclasses and context caching applies, align lifecycles/context isolation accordingly.

**Dangerous bug:** booting a context first, then calling `System.setProperty(...)` and expecting `@ConditionalOnProperty` to register a different bean. Conditions are normally evaluated when the context is built, not on every `getBean` call.

## 26. Static Caches, ThreadLocal, mockStatic, and System.out

Beyond the three main globals, other frequent state leaks include:

**Static cache:**

```java
private static final Map<String, String> CACHE =
        new HashMap<>();
```

This is a snippet. The Map has mutable contents despite a `final` reference; both thread safety and test isolation are at risk. If caching is part of the production contract, test with a scoped cache instance having clear/evict APIs and defined ownership. Never depend on test order for an empty map.

**Static ThreadLocal:**

```java
private static final ThreadLocal<String> TENANT =
        new ThreadLocal<>();
```

`ThreadLocal` does not share the same value across two threads, yet if an executor thread is reused and code forgets `remove()` in `finally`, the next request/test on **the same thread** sees the previous tenant. Tracing MDC, security contexts, and transaction state also require cleanup per framework policy.

**Mockito static mocking:** when using `Mockito.mockStatic(...)`, close `MockedStatic` in `try-with-resources`. Static mocks typically apply to the controlling thread and cannot be assumed to cover other async workers. Avoid arbitrarily mocking `System.getProperty`/core JDK methods, which easily breaks frameworks.

**System.out/System.err:** a test calling `System.setOut(...)` or `System.setErr(...)` modifies output streams **across the whole JVM**. Use snapshot/restore plus `Resources.SYSTEM_OUT`/`Resources.SYSTEM_ERR` when verifying legacy printing. Injecting a logger/output abstraction is usually far better than swapping standard streams.

**Default charset:** `Charset.defaultCharset()` can also depend on JVM startup/config/runtime caching; do not assume it is always UTF-8 across deployments. Pass `StandardCharsets.UTF_8` explicitly when checking payloads/CSV/HTTP text bytes.

## 27. Running in Parallel Does Not Make Every Resource Automatically Safe

JUnit `ResourceLock` locks only tasks within the engine sharing the same key. Exceptions to distinguish:

- **Background threads** spawned by a test can outlive the test method after JUnit releases the lock. If they keep reading/writing globals, other reader tests can be affected. Use `Future.get(timeout)`/thread joins/cancellation/`awaitTermination` and finish cleanup before the test returns.
- **Gradle forks** or Maven Surefire forks are separate JVMs, so static state/System properties/Locale/TimeZone are separate; however, files/databases/brokers/ports may remain shared. `ResourceLock` does not lock cross-process.
- **Other test engines** do not necessarily honor JUnit Jupiter's locks.
- **Production code** in the same JVM does not wait on JUnit resource locks; if a Spring background scheduler/consumer is active, mutating default `Locale`/`TimeZone` can affect it.
- **Parallel Streams/`ForkJoinPool`** or Servlet async work can execute on other threads; test-thread snapshot/restore does not pause those tasks.
- **Static mutable singletons** and Spring singletons do not become per-test merely because the test class uses `@TestInstance(PER_METHOD)`.
- **JVM startup flags** like `-Duser.timezone=UTC` help stabilize CI environments, but do not replace testing app support across multiple zones/locales.

When forced to test global side effects without control over external threads/engines, running tests in a **dedicated JVM fork** (process isolation) is stronger than an in-engine resource lock; still clean up external resources and account for startup overhead.

## 28. When to Use @Isolated, @ResourceLock, or Process Fork?

| Situation | Preferred Option |
| --- | --- |
| Business formatter handling user locales | Inject `Locale`/`ZoneId`/`Clock`, no lock needed |
| Legacy test mutating one specific property key | Snapshot/restore + `@ResourceLock(Resources.SYSTEM_PROPERTIES, READ_WRITE)` |
| Multiple tests only reading system properties | `@ResourceLock(..., READ)` if writers on that key cooperate |
| Test changing `Locale.Category.FORMAT` | Snapshot general/display/format + `Resources.LOCALE` |
| Test changing `TimeZone.default` | Snapshot `TimeZone` and `user.timezone` + `Resources.TIME_ZONE` and `SYSTEM_PROPERTIES` |
| Legacy test class mutating multiple global states | `@Isolated` with cleanup; consider separate fork |
| Static cache shared inside a Spring singleton | Separate cache scope, controlled reset, `@DirtiesContext` if needed |
| 2 JVMs writing the same DB/file | External resource isolation/namespace/lock, not `@ResourceLock` |
| API using static `ThreadLocal` across a thread pool | `finally` remove/propagation and task reuse test |
| Testing localized output broadly | Explicit inputs and snapshot version policy, do not trust defaults |

**Do not slap `@Isolated` on every test by default**: it reduces concurrency and masks designs relying on global state. Fix seams/injection first; locking is a stopgap for code that cannot be refactored immediately.

## 29. Debugging Flaky Failures by Symptom

**A. Passes alone, fails in full suite:** check for mutable `static` maps/counters, `System.setProperty`, `Locale.setDefault`, `TimeZone.setDefault`, Spring singletons/caches, and lingering async tasks.

**B. Fails only on a laptop with a different language:** formatter uses `Locale.getDefault()` or casing lacks `Locale.ROOT` for identifiers; inject the scenario's locale.

**C. Fails only under a different timezone/DST:** `ZoneId.systemDefault()`, `LocalDateTime.now()`, `Date.toString()`, or host-dependent date parsing; inject zone/`Clock` and assert `Instant`/ISO contracts.

**D. Set `user.timezone` yet output didn't change:** default `TimeZone` is cached or formatter was already constructed. Do not expect properties to be re-read; pass `ZoneId.of` explicitly.

**E. `static final AtomicInteger` still leaks across tests:** atomic != isolated. Create a separate counter per test or reset with locks and ownership.

**F. `@BeforeEach` resets static yet fails in parallel:** one test's reset clobbers another; avoid static state or use properly scoped locking.

**G. `@DirtiesContext` didn't solve it:** System properties/Locale/TimeZone leaked outside the Spring context; recycling beans does not reset global JVM state.

**H. `@ResourceLock` didn't stop failures:** another test used a different key/no lock, a background thread, another test engine, or another Gradle fork.

**I. `@TestInstance(PER_METHOD)` yet bean retains state:** the Spring singleton context is reused, not the test instance.

**J. `Locale` `FORMAT` changed yet display names didn't:** `FORMAT` and `DISPLAY` are distinct categories; configure/assert the right category.

**K. `DateTimeFormatter` output shifted despite injected `ZoneId`:** pattern may use localized month/day names without an explicit `Locale`, or database/JDK time zone rules version differs; check `Locale`, `ZoneId`, and `Instant`.

**L. Test JVM fails to exit:** unmanaged executor/scheduled threads or unstopped listeners, not just static fields.

**M. Unit test uses `Clock.fixed` yet integration code still calls `Instant.now()`:** injection didn't reach the whole call path; locate hidden calls.

**N. `MockStatic` passes on test thread, fails inside `@Async`:** thread-scoped; replace static dependency with an injected collaborator.

## 30. Mistakes to Avoid

1. Using `static final AtomicInteger` or a mutable map as a per-test fixture without reset/isolation.
2. Assuming `@TestInstance(PER_METHOD)` resets static fields and JVM defaults.
3. Resetting statics in `@BeforeEach` and running methods concurrently without locks.
4. Using `System.setProperty` to configure Spring tests when `@SpringBootTest(properties)`/context runner suffices.
5. Cleaning up with `System.clearProperty` even when the key held a value before the test.
6. Calling `System.setProperties(new Properties())` to remove one property.
7. Changing `user.language` at runtime expecting `Locale.getDefault()` to refresh.
8. Snapshotting only the general `Locale` while ignoring `FORMAT`/`DISPLAY` category overrides.
9. Changing `user.timezone` and assuming `TimeZone.getDefault()` re-reads immediately.
10. Calling `TimeZone.getTimeZone(invalid)` without realizing GMT fallback can hide misconfiguration.
11. Asserting dates against CI's `ZoneId.systemDefault()` instead of the zone contract.
12. Using `LocalDateTime.now()` for deterministic time tests instead of `Clock`.
13. Sharing a static `SimpleDateFormat` across worker threads.
14. Using `@Execution(SAME_THREAD)` thinking it locks other test classes.
15. Using mismatched `@ResourceLock` keys between reader and writer thinking they coordinate.
16. Trusting `@ResourceLock` to block background threads or external processes.
17. Forgetting to restore in `finally`, especially when assertions fail.
18. Believing `@DirtiesContext` restores JVM globals outside Spring.
19. Forgetting that a Spring singleton can be shared via a cached context.
20. Mocking a static API without closing `MockedStatic`, or assuming it applies to async threads.
21. Putting a static `ThreadLocal` on a reused executor without calling `remove()`.
22. Reassigning JVM-wide `System.out` to test logs without `Resources.SYSTEM_OUT` and cleanup.
23. Writing assertions that depend on thread/test method execution order to read a counter.
24. Using JVM forks to mask races in a shared DB/file without isolating external namespaces.
25. Treating one green run in concurrent mode as proof of thread safety.
26. Skipping tests for domain-specific locales/timezones by forcing UTC across all CI.
27. Logging property credentials/secrets in test logs or committed configs.
28. Assuming `ResourceLock` "detects" races; it merely serializes cooperating tests.

## 31. Final QA Checklist

**Architecture:**

- Is static mutable data truly necessary, or can it become an instance/config-injected collaborator?
- Does formatting use explicit `Locale`/`ZoneId` and immutable `DateTimeFormatter`?
- Is "now" obtained via an injected `Clock` instead of implicit `Instant.now()`?
- Do sequences/caches have clear per-test/scoped lifecycles?
- Are `ThreadLocal`/MDC/security contexts cleared in `finally`?

**Global mutation:**

- If a System property is altered, are **both previous values and `null`** snapshotted accurately?
- Does restoration use `setProperty` vs `clearProperty` matching the snapshot?
- Is `System.setProperties` avoided so the global map is not wiped?
- Are general/`DISPLAY`/`FORMAT` `Locale`s all snapshotted before mutation?
- Are both `TimeZone` and `user.timezone` snapshotted?
- Is everything restored in `finally`/`try-with-resources` even when tests fail?
- Is the mutation scope as short as possible with no background workers still reading afterward?

**JUnit parallel:**

- Do both readers and writers declare matching resource keys and `READ`/`READ_WRITE`?
- Is `@ResourceLock` applied for the corresponding locale/timezone/properties?
- Is `@Isolated` reserved for cases genuinely needing class-wide isolation?
- Is it clear `ResourceLock` does not lock background threads, other engines, or JVM forks?
- Are Gradle `maxParallelForks` and JUnit modes configured intentionally?
- Are tests independent of method ordering and exact thread scheduling?

**Spring Boot:**

- Do config tests use `withPropertyValues`/`@SpringBootTest(properties)` instead of JVM `System.setProperty`?
- Are config records bound and bean factories free of implicit default `Locale`/`TimeZone` reads?
- Are both baseline and overridden contexts checked with the runner?
- If singleton mutable state lives in the context cache, are teardown/resets and context ownership clear?
- Is `@DirtiesContext` never treated as a static/system-property reset?
- Have `@Async`/`@Scheduled` tasks completed/stopped before tests finish?

**Runnability and claims:**

- Are Java package/class/file names and Gradle dependencies consistent?
- Does the Java SE demo compile/run with exact stdout via `javac`/`java` on JDK 17?
- Is the actual JUnit method count 14 across five test classes?
- Are anti-pattern snippets marked so they aren't copied into production code?
- Is test runner behavior distinguished from application business correctness?

**Conclusion:** JVM-wide shared state **knows no test boundaries**. Mutable `static` state, `System.properties`, and default `Locale` and `TimeZone` can make tests flaky even when each method passes alone. The best prevention is **passing configuration and time/locale/zone explicitly**, scoping state appropriately, and avoiding JVM global mutations. For legacy code that must touch globals, use **snapshot/restore + JUnit `@ResourceLock` or `@Isolated`**, remembering these only coordinate cooperating tests and never replace process isolation or out-of-JVM resource cleanup.

## 32. References

- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.10.0/user-guide/#writing-tests-parallel-execution): `@Execution`, `@ResourceLock`, `@Isolated`, and parallel config.
- [JUnit Jupiter ResourceLock API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html): lock keys and `READ`/`READ_WRITE` semantics.
- [JUnit Jupiter Resources API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Resources.html): `SYSTEM_PROPERTIES`, `SYSTEM_OUT`, `SYSTEM_ERR`, `LOCALE`, `TIME_ZONE`.
- [Java SE 17 Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `getDefault`/`setDefault`, `DISPLAY`/`FORMAT` categories.
- [Java SE 17 TimeZone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TimeZone.html): `getDefault`/`setDefault`, cached default, and `user.timezone`.
- [Java SE 17 ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): timezone rules and `systemDefault`.
- [Java SE 17 Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed`/`systemUTC` and deterministic time.
- [Java SE 17 DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): immutable formatter, `withZone`, and locale.
- [Spring Boot 3.5 Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `SpringBootTest` properties, TestContext cache, and context runner.
- [Spring Framework TestContext caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): caching/eviction and context isolation.
- [Spring Boot 3.5 Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): `@ConfigurationProperties`, `@DefaultValue`, and property precedence.