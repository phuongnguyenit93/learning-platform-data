# @SpringBootTest and Why main Is Not Executed by Default

## 1. Key conclusion

In Spring Boot, a single class typically holds both the application configuration and the Java entry point:

~~~java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

This is an **illustrative snippet**, not a complete Java file because imports are missing. When running `java -jar` or launching the class with Java, the JVM enters `public static void main(String[] args)`; that method calls `SpringApplication.run(...)` to create the `ApplicationContext`.

However, **`@SpringBootTest` does not invoke this `main` method by default**. According to Spring Boot 3.5.16 documentation, the default value is:

~~~java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.NEVER)
~~~

This is **illustrative syntax placed on a test class**, equivalent to the default behavior of `@SpringBootTest`. Spring Boot Test uses a `SpringApplication` created by the test loader to boot the `ApplicationContext` directly from the configuration class, **bypassing the `main` method body**.

This **does not mean the application is not started in tests**. Spring still:
- Loads configuration and appropriate auto-configuration.
- Registers/instantiates beans in the context.
- Performs dependency injection.
- Calls `@PostConstruct` and bean initialization callbacks.
- Auto-starts applicable `SmartLifecycle` beans during refresh.
- Dispatches the application events of the `SpringApplication` startup sequence.
- Executes registered `ApplicationRunner` and `CommandLineRunner` beans when bootstrap succeeds.
- Lets tests inject `ApplicationContext`, `Environment`, services, and repositories.

**The difference is that logic placed outside `SpringApplication.run(...)` inside the `main` body is not executed automatically.** If `main` configures profiles, banners, listeners, default properties, or performs other side effects before `run(...)`, those settings may be skipped in default tests.

## 2. Distinguishing JVM main, SpringApplication.run, and ApplicationRunner

These three concepts operate at different layers:

| Component | Who calls it? | Purpose | Happens in default @SpringBootTest? |
| --- | --- | --- | --- |
| Java `main(String[] args)` | Java launcher or explicit caller when tests configure using `main` | Process entry point and where the app customizes bootstrap | **No** |
| `SpringApplication.run(...)` | Normally called by `main`; in tests called by `SpringBootContextLoader`/test infrastructure | Creates, configures, refreshes context, and completes Boot startup | **Yes** |
| `ApplicationRunner.run(ApplicationArguments)` | Spring Boot along the `SpringApplication.run(...)` path after refresh | Work after the context has started | **Yes**, if the runner bean is created and startup succeeds |
| `CommandLineRunner.run(String...)` | Spring Boot after refresh | Post-startup work with raw arguments | **Yes**, if the bean exists and startup succeeds |
| `@PostConstruct` | Spring bean initialization mechanism | Bean initialization after injection | **Yes**, for created beans |
| `SmartLifecycle.start()` | Spring lifecycle processor during refresh if auto-start | Starts lifecycle-managed components | **Yes**, per bean contract |
| `@PreDestroy` | Bean destruction mechanism when context closes | Resource cleanup | When the context is destroyed, not necessarily after every test method |

Key point to remember:

~~~text
Running the application normally:
  JVM launcher
      -> MyApplication.main(args)
          -> SpringApplication.run(MyApplication.class, args)
              -> refresh ApplicationContext
              -> @PostConstruct / SmartLifecycle
              -> ApplicationRunner / CommandLineRunner
              -> ApplicationReadyEvent

Default @SpringBootTest:
  JUnit + Spring TestContext
      -> SpringBootContextLoader
          -> SpringApplication used for testing
              -> refresh ApplicationContext
              -> @PostConstruct / SmartLifecycle
              -> ApplicationRunner / CommandLineRunner
              -> ApplicationReadyEvent
          -> test method
  (DOES NOT automatically pass through MyApplication.main)
~~~

This is a general mechanism diagram; ordering among different beans, runners ordered by `@Order`/`Ordered`, and web environment types depend on configuration. It is not an internal method-by-method trace of a specific framework version.

### Why are runners still called while main is not?

`ApplicationRunner` is a **Spring bean**. When `SpringApplication.run(...)` executes, Spring Boot invokes the runner after refreshing the context. The test loader still initializes the context via `SpringApplication`, so the runner still runs.

`main`, by contrast, is **a static Java method**, not a Spring bean lifecycle hook. Annotating a class with `@SpringBootApplication` only helps Spring identify the configuration source; that annotation does not make Spring find and invoke every static method named `main`.

If an application must avoid sending emails, calling remote APIs, or mutating a database during integration tests, **you cannot rely solely on `main` being skipped**: if the side effect lives in `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct`, `SmartLifecycle`, or an event listener, the test can still execute it.

## 3. Three values of useMainMethod

Spring Boot 3.5 provides `org.springframework.boot.test.context.SpringBootTest.UseMainMethod`:

| Value | Rule | If main is not found | When to use |
| --- | --- | --- | --- |
| `NEVER` | Do not call `main`; create test `SpringApplication` | Can still bootstrap from configuration class | Default; testing context independently of entry point |
| `WHEN_AVAILABLE` | Use `main` if present; otherwise use standard test loader | **Fallback**, does not fail merely for lacking `main` | Tests across mixed configurations, leveraging `main` when present |
| `ALWAYS` | Require using `main` to create the context | **Fail** if no matching configuration/`main` exists | Verifying bootstrap config actually used in production |

Equivalent default annotation:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.NEVER)
~~~

To require the test to use `main`:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)
~~~

To use `main` when present without forcing every configuration to define it:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.WHEN_AVAILABLE)
~~~

These three lines are **annotation illustrations**, requiring importing `SpringBootTest` and `UseMainMethod` and placing them on an actual JUnit test class.

### ALWAYS does not mean "fork a new JVM"

When `ALWAYS` is chosen, Spring Boot TestContext invokes the matching `main` method inside the **test runner's JVM** to create the `SpringApplication`/context. That differs from launching a new process with `java -jar`. Therefore:
- Any `System.setProperty` from `main` can affect the entire test JVM, including other tests.
- `System.exit(...)` inside `main` can terminate the entire test process; very dangerous.
- Threads, hooks, or files created by `main` outside the container can leak across tests.
- The Maven/Gradle test runner still manages test ordering, context caching, and shutdown.
- `ALWAYS` does not automatically verify OS process exit codes, command-line packaging, or launch scripts.

If you need to test a failure at the **process entry point** layer, use a subprocess with a timeout and inspect the exit code separately; never turn an in-JVM test into a real `System.exit`.

### WHEN_AVAILABLE does not guarantee main ran

If the configuration finds a matching `main` method, `WHEN_AVAILABLE` uses it; otherwise Spring Boot falls back. Therefore, a passing test in `WHEN_AVAILABLE` mode **does not prove `main` is always called** across all modules or after refactoring. If the test's goal is to strictly verify the entry point itself, use `ALWAYS` and assert configuration/behavior originating from `main`.

## 4. Where is the default behavior defined?

`@SpringBootTest` extends how the Spring TestContext Framework is used. In Spring Boot 3.5.16:

- Bootstrapper: `SpringBootTestContextBootstrapper`.
- Default context loader: `SpringBootContextLoader`.
- Configuration source: explicit `classes`, nested `@Configuration`, or `@SpringBootConfiguration` search mechanism.
- `useMainMethod()` defaults to `UseMainMethod.NEVER`.
- `webEnvironment()` defaults to `WebEnvironment.MOCK`.
- `args()` allows passing application arguments into the `SpringApplication` path used in tests.
- `properties()`/`value()` allows adding properties to the test Environment.

**Meaning:** by default, tests use a `@SpringBootApplication`-annotated class as a **configuration source**, rather than calling that class's `main` entry point method.

### Configuration class lookup mechanism

Spring Boot tests typically search upward from the test's package until finding a class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`. In a standard project, the app class sits in the root package and tests sit in the same package or a subpackage, so the right configuration is found.

Example package tree:

~~~text
src/main/java/com/example/lesson/MainMethodLifecycleApplication.java
src/test/java/com/example/lesson/MainDefaultTest.java
src/test/java/com/example/lesson/MainAlwaysTest.java
~~~

Placing a test outside the application's package tree can prevent the framework from finding `@SpringBootConfiguration`, even if `main` exists elsewhere. In that case, use `@SpringBootTest(classes = MainMethodLifecycleApplication.class)` to specify the configuration source explicitly, instead of trying to invoke `main` manually from the test.

### classes specifies the configuration source, it does not force main to run

Writing:

~~~java
@SpringBootTest(classes = MainMethodLifecycleApplication.class)
~~~

**does not mean** `MainMethodLifecycleApplication.main(...)` will be called. It selects the class for loading configuration. Only `useMainMethod` (when supported) changes the `main`-invocation policy.

### When main merely delegates, the difference is barely visible

If `main` only has:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

then default tests and `ALWAYS` tests can produce equivalent contexts in terms of bean graph, even though the entry path differs. The difference becomes apparent when **`main` contains customizations beyond calling `SpringApplication.run`**.

## 5. Customizations in main easily lost when tests skip main

### 5.1. SetAdditionalProfiles

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("from-main");
app.run(args);
~~~

If a test uses `NEVER`, profiles added by `main` **are not auto-activated**. A bean with `@Profile("from-main")` may be missing in default tests even though it exists in production runs. With `ALWAYS`, `main` is used and that profile has a chance to be applied.

This is an illustrative example inside `main`, not standalone. For tests needing an explicit profile, you can also use `@ActiveProfiles("...")`; the choice depends on whether you want to test **real production bootstrapping** or construct an independent test environment.

### 5.2. Default properties

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setDefaultProperties(Map.of("lesson.main.origin", "from-main"));
app.run(args);
~~~

This default property source is only configured when execution passes through `main`. Default `@SpringBootTest` does not know about it unless the same configuration is supplied via another path. Tests can add `@SpringBootTest(properties = "...")` or `@TestPropertySource`, yet that **does not prove `main` was executed**.

This is an illustrative snippet requiring `java.util.Map` and Spring Boot imports. Default properties have **lower precedence** than many other property sources; if tests or the environment override the key, the value may differ.

### 5.3. Banner, logging, and SpringApplication settings

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setBannerMode(Banner.Mode.OFF);
app.setLogStartupInfo(false);
app.run(args);
~~~

If `main` is skipped, settings applied by this method may differ in tests. This may not break assertions directly, yet it can create configuration drift between production and tests.

This is an illustration requiring `org.springframework.boot.Banner` and `SpringApplication` imports.

### 5.4. Listeners and initializers

If `main` creates `SpringApplication` and registers:
- `ApplicationListener` for startup events,
- `ApplicationContextInitializer`,
- additional configuration sources,
- argument or profile processing,
- lazy initialization / web application type settings,

then tests using `NEVER` may not receive the same customizations. When you want those present in tests, use `ALWAYS` or move the customization to a hook/config loaded by Spring Boot TestContext per contract (especially if multiple context types need them).

### 5.5. Side effects outside Spring

A `main` method might:
- Write files, mutate `System.setProperty`.
- Open a socket/connection with manual code.
- Register a JVM shutdown hook.
- Call an external service before the context is created.
- Call `System.exit`.
- Mutate JVM-global state.

Default tests skip the `main` body and thus may **avoid triggering** those side effects. If `ALWAYS` is enabled, they can happen **directly inside the test process**. This is why you should weigh carefully before enabling `ALWAYS` across the whole suite.

## 6. What is NOT skipped: the Spring bean lifecycle still runs

Do not interpret "`main` doesn't run" as "tests don't traverse the lifecycle":

~~~text
Default @SpringBootTest
    |
    +-- TestContext creates SpringApplication
    +-- Environment / auto-configuration
    +-- ApplicationContext.refresh()
    |      +-- BeanDefinition / singleton creation
    |      +-- @PostConstruct / init callbacks
    |      +-- SmartLifecycle auto-start (when applicable)
    |      +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT on standard Boot path
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC on standard Boot path
    |
    +-- JUnit @Test methods
~~~

This is the generalized sequence for a successful `SpringApplication` startup; it may vary by version/customizations. `@SpringBootTest` can also use a `webEnvironment` that does not open a real socket, so `ApplicationReadyEvent` of a **test context** does not equate to a production pod receiving traffic.

### @PostConstruct and @PreDestroy

`@PostConstruct` is tied to bean creation; even though `main` does not run, the test context still creates beans, so the callback can execute. `@PreDestroy` is tied to bean destruction; do not assume it runs **after each `@Test` method** because Spring TestContext uses **context caching**.

### ApplicationRunner and CommandLineRunner

Both runner types execute when `SpringApplication` completes context bootstrapping. Thus they can:
- Seed data.
- Send messages.
- Call APIs.
- Run jobs.
- Mutate the database.

Those side effects **can happen in default `@SpringBootTest`**, even when `main` is not called. If inappropriate for tests, guard them with profiles/properties or swap dependencies, use test-specific configuration, and design them to be idempotent. Never put dangerous work in a runner and rely merely on `main` not running.

### SmartLifecycle

A `SmartLifecycle` bean with `isAutoStartup()==true` can start during refresh. It must stop/clean up when the test context closes; do not assume all workers have stopped when a test method returns. If a test measures lifecycle, understand context scope/caching and control state within the appropriate test scope.

## 7. Complete demo: Java 17+, Spring Boot 3.5.16, JUnit 5

We build a Maven project demonstrating **four** test cases:

1. `MainDefaultTest`: `@SpringBootTest` without specifying `useMainMethod`; proves the default does not invoke `main`.
2. `MainAlwaysTest`: `useMainMethod=ALWAYS`; proves `main` configuration is applied.
3. `MainWhenAvailableTest`: `useMainMethod=WHEN_AVAILABLE`; `main` is present so it is used.
4. `MainArgumentsTest`: does not invoke `main` yet still passes `args` to `SpringApplication` and observes them in `Environment`.

The application contains:
- `main` method setting `lesson.main.origin=from-main` via `SpringApplication.setDefaultProperties`.
- `main` method adding profile `from-main` via `setAdditionalProfiles`.
- A `StartupState` bean with `@PostConstruct` / `@PreDestroy`.
- An `ApplicationRunner` bean incrementing runner invocation count **per context**.

No network server or external database is used. Test assertions provide stronger evidence than counting logs across classes when context caching may reuse contexts.

### 7.1. Directory structure

~~~text
main-method-test-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/mainmethod/
│   │       └── MainMethodLifecycleApplication.java
│   └── test/
│       └── java/com/example/mainmethod/
│           ├── MainDefaultTest.java
│           ├── MainAlwaysTest.java
│           ├── MainWhenAvailableTest.java
│           └── MainArgumentsTest.java
~~~

The package name across all five Java files is `com.example.mainmethod`. Test files use the `Test` suffix for Maven Surefire discovery. No extra YAML configuration or mocks are needed.

### 7.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>main-method-test-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-test` provides JUnit Jupiter along with Spring Boot TestContext in test scope. `spring-boot-starter` suffices to run the non-web CLI. There is no need to add `spring-boot-starter-web`, avoiding port binding and reducing lifecycle noise.

### 7.3. MainMethodLifecycleApplication.java

File `src/main/java/com/example/mainmethod/MainMethodLifecycleApplication.java`:

~~~java
package com.example.mainmethod;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MainMethodLifecycleApplication {

    public static void main(String[] args) {
        System.out.println("MAIN_METHOD_INVOKED");

        SpringApplication application =
                new SpringApplication(MainMethodLifecycleApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("from-main");
        application.setDefaultProperties(
                Map.of("lesson.main.origin", "from-main"));
        application.run(args);
    }

    @Bean
    StartupState startupState() {
        return new StartupState();
    }

    @Bean
    ApplicationRunner demoRunner(StartupState state) {
        return args -> {
            state.markRunner();
            System.out.println(
                    "APPLICATION_RUNNER_INVOKED count="
                            + state.runnerCalls());
        };
    }

    public static final class StartupState {
        private final AtomicInteger runnerCount = new AtomicInteger();

        @PostConstruct
        public void initialized() {
            System.out.println("BEAN_POST_CONSTRUCT");
        }

        void markRunner() {
            runnerCount.incrementAndGet();
        }

        public int runnerCalls() {
            return runnerCount.get();
        }

        @PreDestroy
        public void destroyed() {
            System.out.println("BEAN_PRE_DESTROY");
        }
    }
}
~~~

This is a **complete** Java file in the project, with no stub/placeholder methods. Meaningful signals:

- `MAIN_METHOD_INVOKED`: printed **only when `main` is called**.
- `lesson.main.origin`: property set only inside the `main` body.
- Profile `from-main`: added only by the `setAdditionalProfiles` call inside `main`.
- `BEAN_POST_CONSTRUCT`: printed when Spring creates the `StartupState` bean, **regardless of whether `main` was called**.
- `APPLICATION_RUNNER_INVOKED count=1`: printed when Boot executes `ApplicationRunner` for a fresh context.
- `BEAN_PRE_DESTROY`: printed when Spring destroys the bean, possibly **after the final test completes**, not necessarily immediately after each method.

`StartupState.runnerCalls()` counts on a **per-context** bean, not a JVM-wide static variable. That keeps assertions stable under Spring TestContext context caching/reuse. If a customization initializes an extra context, each context has its own counter.

### 7.4. Test 1 — MainDefaultTest.java

File `src/test/java/com/example/mainmethod/MainDefaultTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MainDefaultTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void contextStartsWithoutCallingJavaMain() {
        assertNull(environment.getProperty("lesson.main.origin"));
        assertFalse(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

**Assertion explanation:**
- No `useMainMethod`, since the default is `NEVER`.
- `lesson.main.origin` is not set by `main` → `assertNull` in the demo environment.
- `from-main` is not auto-activated.
- Yet `ApplicationRunner` **did run**, so `runnerCalls()==1`.

This is the central distinction between **"not calling `main`"** and **"not starting the Spring application"**. The test still runs a real application context.

Note that this test assumes no external property source/profile intentionally sets `lesson.main.origin` or `from-main`. In a clean learning environment like the project above, the assertion is deterministic. When integrating into an existing project with its own CI profiles, use markers in an isolated test namespace or control configuration sources to avoid collisions.

### 7.5. Test 2 — MainAlwaysTest.java

File `src/test/java/com/example/mainmethod/MainAlwaysTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
class MainAlwaysTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void mainCustomizationsBecomeVisibleToTestContext() {
        assertEquals("from-main",
                environment.getProperty("lesson.main.origin"));
        assertTrue(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

**Explanation:** `ALWAYS` tells TestContext to use `MainMethodLifecycleApplication.main(...)`. `main` creates `SpringApplication`, sets the property/profile, and calls `run`, so customizations become visible inside the test context. The runner still executes as normal.

This tests **the application's launcher configuration**, not just a single service. Only use `ALWAYS` if `main` is written safely for test environments without calling `System.exit` or causing unwanted side effects.

### 7.6. Test 3 — MainWhenAvailableTest.java

File `src/test/java/com/example/mainmethod/MainWhenAvailableTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class MainWhenAvailableTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void usesMainBecauseThisApplicationHasOne() {
        assertEquals("from-main",
                environment.getProperty("lesson.main.origin"));
        assertTrue(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

In this project, the configuration has a `main` method, so `WHEN_AVAILABLE` goes through `main`, matching `ALWAYS` in marker results. If the configuration is later changed to a class without `main`, `WHEN_AVAILABLE` falls back instead of failing.

Do not use `WHEN_AVAILABLE` when the test itself is meant to catch the bug "entry point accidentally deleted"; use `ALWAYS` for that purpose.

### 7.7. Test 4 — MainArgumentsTest.java

File `src/test/java/com/example/mainmethod/MainArgumentsTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        args = "--lesson.cli.marker=passed-by-test-loader")
class MainArgumentsTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void appArgsWorkEvenThoughMainWasNotInvoked() {
        assertNull(environment.getProperty("lesson.main.origin"));
        assertEquals("passed-by-test-loader",
                environment.getProperty("lesson.cli.marker"));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

`@SpringBootTest.args` passes application arguments to the `SpringApplication` used in tests. It **does not mean `main` was called**. This test shows the property from the CLI argument is produced by the test loader, while the property set only in `main` remains absent.

Distinguish clearly:
- `args`: passes application arguments into bootstrap.
- `properties`: adds `key=value` to the test Environment.
- `useMainMethod`: chooses whether to call Java `main` to create `SpringApplication`.

These three capabilities are independent in purpose.

## 8. Running the demo and verifying results

Requirements: JDK 17+, Maven able to download dependencies, and no external properties/profiles deliberately using the `lesson.main.*` namespace.

From the project directory:

~~~bash
mvn test
~~~

Maven Surefire (managed by the Spring Boot parent) executes test classes with the `Test` suffix. Each test has one JUnit 5 method.

**Expected assertion results:**

| Test | useMainMethod | Property `lesson.main.origin` | Profile `from-main` | Runner calls/context |
| --- | --- | --- | --- | --- |
| MainDefaultTest | NEVER (default) | null | false | 1 |
| MainAlwaysTest | ALWAYS | from-main | true | 1 |
| MainWhenAvailableTest | WHEN_AVAILABLE | from-main | true | 1 |
| MainArgumentsTest | NEVER (default) | null | false unless configured elsewhere | 1; CLI marker has value |

A clean project has four test methods and expects **4 tests PASS**, with zero failures/errors. Maven output also includes timestamps, logging framework lines, test class names, and context caching details, so **there is no single fixed full stdout** for `mvn test`.

### Which log markers appear?

When a fresh test context is created:
- With `NEVER`: `BEAN_POST_CONSTRUCT` and `APPLICATION_RUNNER_INVOKED count=1`; **no `MAIN_METHOD_INVOKED` from this context itself**.
- With `ALWAYS`: `MAIN_METHOD_INVOKED`, then `BEAN_POST_CONSTRUCT` and `APPLICATION_RUNNER_INVOKED count=1`.
- With `WHEN_AVAILABLE` and a `main` method present: same as `ALWAYS`.
- `BEAN_PRE_DESTROY`: may appear when the test context cache is cleared, on context eviction, or when the framework exits; **not strictly tied to individual test methods**.

**Do not count `MAIN_METHOD_INVOKED` across the entire suite log to infer test order**, because JUnit may run tests in a different order, Spring TestContext may cache/reuse contexts, and another test may load a similar configuration. Rely on assertions against the **Environment of the context under test**.

### Running a single test class for easier observation

~~~bash
mvn -Dtest=MainDefaultTest test
mvn -Dtest=MainAlwaysTest test
mvn -Dtest=MainWhenAvailableTest test
mvn -Dtest=MainArgumentsTest test
~~~

Each command launches a separate Maven test invocation. Running only the default test in a clean test JVM produces no `MAIN_METHOD_INVOKED` marker from the application, yet still produces the `ApplicationRunner` marker.

### Running the application normally

Compile/package:

~~~bash
mvn package
java -jar target/main-method-test-demo-0.0.1-SNAPSHOT.jar
~~~

When launched via the Java launcher, `main` is indeed the entry point. The markers printed by the application code itself in order during a successful run:

~~~text
MAIN_METHOD_INVOKED
BEAN_POST_CONSTRUCT
APPLICATION_RUNNER_INVOKED count=1
~~~

Spring Boot logs/banners may interleave. Because this is a non-web application, when `main` finishes and no other non-daemon threads remain, the JVM can terminate naturally; the shutdown hook closes the context and `BEAN_PRE_DESTROY` may then appear. **Never use the appearance time of `@PreDestroy` in logs as proof that a specific test method closed the context.**

### If output or assertions look wrong

Check:
1. Are you actually using Spring Boot 3.5.16 or a version supporting `useMainMethod`?
2. Are the test files in `src/test/java` under the right package?
3. Is the test overridden by another `@SpringBootTest(properties=...)`/`@ActiveProfiles` or environment variable?
4. Does `classes` point to the `@SpringBootApplication` class containing `main`?
5. Does `main` call **one** `SpringApplication.run` to create the context?
6. Is another runner in the project throwing an exception and failing startup before the test method?
7. Did Maven accidentally skip tests or run an extra failing test?
8. Are JUnit 4 annotations or an incompatible test runner used in a project migrated to JUnit Jupiter?

## 9. When to use NEVER, ALWAYS, WHEN_AVAILABLE?

### NEVER (default) — testing application configuration and bean graph

Suitable for:
- Service/repository integration tests needing a full Spring context.
- Tests needing to bootstrap the app **without** non-Spring orchestration code in `main`.
- Tests wanting isolated profile/property control via annotations.
- Tests not needing to verify banners, listeners, and settings set manually in `main`.

Pros: reduces coupling to the entrypoint and avoids non-Spring side effects created directly by `main`.

Risk: if production `main` contains critical customizations that tests do not replicate, tests may **PASS in an environment different from production**. That is false confidence, not a TestContext bug.

### ALWAYS — testing the real bootstrap path from main

Suitable when:
- `main` creates `new SpringApplication(...)` and configures additional profiles, banner, initializers, listeners.
- You need to verify that entrypoint startup configuration affects the bean graph.
- You want immediate failure if the configuration class lacks a `main` method.
- You need a dedicated group of integration tests for "launcher parity".

Risk: side effects of `main` execute inside the test process. Do not use when `main` calls `System.exit`, spawns external processes, mutates uncleaned static/global state, or performs destructive data actions.

### WHEN_AVAILABLE — flexible across multiple configurations

Suitable for:
- Test suites running across multiple application configurations, where some modules have `main` and others do not.
- Wanting to use an application's `main` if present without forcing every test source to supply `main`.
- Accepting that a refactor removing `main` will silently fall back.

Risk: a passing test does not prove the `main` path still exists; use `ALWAYS` if that invariant must be guarded.

### Practical recommendation

Most integration tests can use the default. Add a few targeted `ALWAYS` tests if `main` holds important customizations. Better yet, for configuration needed by **both runtime and tests**, move it into beans, `@Configuration`, `ApplicationContextInitializer`, or independently testable Spring Boot configuration mechanisms — rather than putting dozens of side effects in `main`.

## 10. ApplicationRunner still runs: a major risk in lifecycle testing

Some applications place job logic inside a runner:

~~~java
@Bean
ApplicationRunner sendWelcomeEmails(MailSender sender) {
    return args -> sender.sendWelcomeEmails();
}
~~~

This is a **non-standalone illustrative snippet**; `MailSender` and its method are hypothetical types/logic. In default `@SpringBootTest`, `SpringApplication` can still instantiate the runner bean and **execute it**, even though Java `main` is not called.

If the code sends real emails, calls payment APIs, or publishes to Kafka, integration tests can cause unintended side effects.

### Safe design patterns

1. Move business logic into a separate service; the runner only calls the service.
2. Use profiles or properties to control when the runner is registered.
3. In tests, override properties or replace external dependencies with test doubles.
4. Keep job code idempotent: if startup/retries repeat, avoid duplicate sends or corrupting data.
5. Run a dedicated integration test to verify the runner itself in a safe environment.
6. Never use `System.exit` in a runner to "end a test", as it can kill the entire test JVM.

Example guarded by a property:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "jobs",
        name = "send-welcome-emails",
        havingValue = "true")
ApplicationRunner sendWelcomeEmails(MailSender sender) {
    return args -> sender.sendWelcomeEmails();
}
~~~

This is an illustrative snippet. If production needs the job enabled, the property must be configured explicitly; tests omitting it will not run the job. Still, include a dedicated test ensuring the job activates when required. Never arbitrarily flip critical jobs to default `false` without updating production requirements.

## 11. @PostConstruct, SmartLifecycle, and ApplicationReadyEvent in tests

Even when `main` does not run, TestContext starts a real Spring application. Lifecycle extension points can still execute:

### @PostConstruct

A callback invoked when Spring initializes a bean after dependency injection. A singleton bean created in the test context still receives this callback.

If `@PostConstruct` opens connections or creates files, pair it with `@PreDestroy` or an equivalent cleanup path. Do not place unsafe side effects here assuming default tests skip them just because `main` didn't run.

### SmartLifecycle

`SmartLifecycle.isAutoStartup()` is often true. `DefaultLifecycleProcessor` may call `start()` during context refresh. Tests should:
- Know which workers auto-start.
- Use profiles/properties/test config to disable unrelated workers.
- Avoid closing shared beans manually when a test method finishes if the context remains cached.
- Verify `stop(Runnable)` callbacks complete properly when the test context is destroyed.

### Application events

During a successful Boot startup, events like `ApplicationStartedEvent` and `ApplicationReadyEvent` can still fire even if Java `main` did not run, because they are produced by `SpringApplication.run` rather than manual code in the `main` body.

If a test wants to verify event listeners, use Spring TestContext event recording or dedicated listener/test beans. Do not assume `ApplicationReadyEvent` is absent just because `UseMainMethod.NEVER` is active.

### ApplicationContext and WebEnvironment

`@SpringBootTest` defaults to `webEnvironment=MOCK`. With servlet web libraries present, this typically creates a mock web environment **without opening a real server on a TCP port**.

Values:
- `MOCK`: appropriate mock web application context; does not necessarily open an embedded server.
- `RANDOM_PORT`: embedded server using a random port; suited for HTTP integration tests.
- `DEFINED_PORT`: server on a configured or default port; prone to port conflicts across tests.
- `NONE`: no web application context created; suited for CLIs/pure lifecycle tests.

The demo chooses `NONE` to avoid ports and focus on **`main` vs. context lifecycle**. Changing `webEnvironment` **does not** replace `useMainMethod`; they are two separate configuration axes.

## 12. Context caching: main does not run for every @Test

Spring TestContext Framework **caches `ApplicationContext`s** across tests with equivalent configurations. Therefore:
- Context created once → runners and `@PostConstruct` run when the context starts.
- Multiple `@Test`s sharing a cached context → do not restart the context every time.
- The test runner does not invoke `main` for every test method just because you set `ALWAYS`; it uses `main` when **creating a new context** via the loader.
- `@PreDestroy` does not mean running after every test; it may run when the context is evicted/dirtied, the test suite ends, or the cache closes.
- Execution order of test classes is determined by the build/JUnit; do not use suite-wide logs to infer stable callback counts.

### @DirtiesContext

When a test mutates singleton state or context infrastructure and other tests must not reuse that context, you can annotate:

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
~~~

This is an illustrative annotation on a test class, requiring importing `org.springframework.test.annotation.DirtiesContext`. It tells the framework to mark the context dirty after the class to evict it from the cache, triggering a fresh startup later when an equivalent context is needed.

**Do not overuse `@DirtiesContext`** just to "make `main` run again". It slows the suite and can mask tests causing side effects without proper cleanup. If the goal is verifying once-per-startup bean initialization, assertions via per-context markers/counters are usually clearer.

### Parallel execution

If JUnit tests run in parallel or multiple modules share a JVM/process, a static counter in `main` can easily be mutated by another test. That is why the demo uses the `StartupState` bean holding a **per-context** count, combined with Environment properties/profiles to avoid order dependence.

Still, global properties/profiles can be affected if another `main` calls `System.setProperty`; another reason to avoid global mutable state in `main`.

## 13. Even when main runs, @SpringBootTest is still not identical to production

`useMainMethod=ALWAYS` uses `main` to initialize the context, yet **does not guarantee full parity**:

| Difference | Why |
| --- | --- |
| JVM process/flags | Tests usually run inside Maven/Gradle/IDE JVMs, not production `java -jar` |
| Classpath | Tests include `spring-boot-starter-test` and test classes; packaged JARs have a different layout |
| Properties | `@SpringBootTest(properties)`, `@ActiveProfiles`, test resources, and CI env may override |
| Web server | `webEnvironment` may create mocks/ports differing from production |
| Database | Tests may use H2, Testcontainers, or mocks instead of production |
| Context caching | Spring TestContext retains contexts to speed up tests |
| Exit behavior | Must not call `System.exit`; shutdown hooks/test suites differ from production |
| Threads and timing | Parallel tests, instrumentation, coverage agents, and schedulers differ |
| Time/locale/env | JVM system properties, timezone, clock, and external services may differ |

Thus `ALWAYS` is a way to **verify customizations in `main`**, not a replacement for smoke tests running the actual artifact, checking health/readiness, database connectivity, or verifying exit codes in subprocesses.

If a property is only applied when `main` runs, `DEFAULT` tests may not observe it. If `ALWAYS` passes, also verify that property is not overridden in production.

## 14. Case with no main where ALWAYS fails

A `@SpringBootConfiguration` might only declare beans without a `main` method (e.g., a library module or test configuration). With:

~~~java
@SpringBootTest(
        classes = LibraryConfiguration.class,
        useMainMethod = UseMainMethod.ALWAYS)
~~~

the test cannot use `main` if `LibraryConfiguration` lacks that method and **fails during test context creation**.

With `WHEN_AVAILABLE`, the test can use the standard loader to create a context from the configuration class. With `NEVER`, it always uses the loader path and needs no `main`.

This is an **illustrative snippet**, not part of the four passing test files in section 7 because `LibraryConfiguration` is not defined in the demo; to practice, create a concrete `@SpringBootConfiguration`/`@EnableAutoConfiguration` class and write a separate test intentionally expecting failure. Do not put always-failing tests into the default build.

Key takeaway: **lacking `main` does not mean you cannot have a Spring `ApplicationContext`**. Spring configuration is built from class annotations/`BeanDefinition`s, not necessarily a Java launcher method.

## 15. @SpringBootTest(args) vs. calling main(args) directly

Example:

~~~java
@SpringBootTest(
        args = "--app.feature.enabled=true",
        useMainMethod = UseMainMethod.NEVER)
~~~

The test loader passes the argument into the test's `SpringApplication`. If the app defines an `ApplicationRunner` receiving `ApplicationArguments` or reads `Environment`, it can observe this property even though `main` was never invoked.

**Do not assume**: "Only `main(String[] args)` knows about CLI arguments." `SpringApplication.run(args)` also processes arguments, and TestContext can create `SpringApplication` and pass `args` directly.

In the demo, `MainArgumentsTest` verifies `lesson.cli.marker` is present in `Environment` while `lesson.main.origin` is not.

If a test sets:

~~~java
@SpringBootTest(
        properties = "app.feature.enabled=true",
        useMainMethod = UseMainMethod.NEVER)
~~~

that is a **test `Environment` property**, not an argument passed through `main`. The test path can carry the same property name as production while still skipping `main`.

## 16. Distinguishing from @ContextConfiguration and test slices

### @ContextConfiguration

`@ContextConfiguration` is a Spring Test Framework annotation for selecting sources and context loaders. Without passing through an appropriate `SpringApplication`, Boot-specific features such as application arguments/runners/events may behave differently. Do not assume "every Spring test runs `ApplicationRunner`" if a test does not use Boot's `SpringApplication` loader.

`@SpringBootTest` is how Boot integrates TestContext to run a fuller Boot application. Yet by default it **still does not call Java `main`**.

### @WebMvcTest, @DataJpaTest, and test slices

Test slices load a subset of configuration tailored to the layer under test, rather than booting the entire application like `@SpringBootTest`. Do not expect:
- A production runner to always be present in a slice.
- Every `@Component` to be scanned.
- The `main` body to be invoked.
- A real embedded server.

If the goal is merely testing controllers or JPA mappings, use slices to avoid initializing unrelated lifecycles. If the goal is verifying `main`-specific Boot settings, use a well-scoped `@SpringBootTest(useMainMethod=ALWAYS)` integration test.

### @TestConfiguration

When a test needs to swap a bean or add configuration without modifying `main`, use a nested `@TestConfiguration` or import a top-level `@TestConfiguration`. It does not mean "run `main`"; it merely adds configuration sources for the test.

Distinguish `@TestConfiguration` from nested `@Configuration`: per Boot docs, a nested `@Configuration` can become the primary configuration replacing auto-discovered sources, whereas a nested `@TestConfiguration` supplements the primary app configuration.

## 17. Debugging when production config is right yet tests miss a bean

Scenario:

~~~text
Production:
  main():
    new SpringApplication(...)
    setAdditionalProfiles("integration")
    run(...)
  |
  +-- @Profile("integration") BeanA is created

Default @SpringBootTest:
  TestContext:
    creates SpringApplication directly
    does not call main()
  |
  +-- integration profile is not active
  +-- BeanA does not exist
  +-- BeanB requires BeanA -> test startup fails
~~~

**Investigation steps:**

1. Read the missing-bean exception and the bean's annotations/profiles/conditions.
2. Identify where the required setting is applied: inside `main` or in shared files/config?
3. Confirm whether the test uses `UseMainMethod.NEVER`.
4. If the test needs production launcher parity, try `ALWAYS` in a controlled integration test.
5. If the test wants an isolated environment, use `@ActiveProfiles`/`properties` or refactor the config into a shared mechanism.
6. Inspect the condition evaluation report with `--debug`/appropriate logger if a conditional bean is not created.
7. Verify the test isn't manually creating another context or using mocks/slices that alter the bean graph.

Do not patch the test by adding a fake bean before understanding why production has the bean while the test lacks it. Sometimes the real issue is skipped launcher-only configuration.

### What if the test uses ALWAYS and still misses a main property?

Check:
- Does `classes` select the right `@SpringBootApplication` containing `main`?
- Does `main` call `SpringApplication.run(...)` with the right primary source?
- Is the property overridden by higher-precedence test `properties`, system properties, environment variables, or profile config?
- Did a test customize `ContextLoader` away from `SpringBootContextLoader`?
- Is the test context cached from a different configuration? Check merged context configuration and test annotations.
- Is an extension/runner creating a second context outside Spring Test's context?

Do not rely solely on "Started ..." logs to prove `main` ran: default TestContext also logs Spring Boot started upon successful initialization.

## 18. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "`@SpringBootTest` always runs `main`" | Tests miss custom profiles/listeners | Use `useMainMethod` explicitly or refactor bootstrap |
| "`main` doesn't run so `ApplicationRunner` doesn't run" | Tests trigger jobs unintentionally | Manage runners via profiles/properties/test config |
| "`@SpringBootTest(classes=App.class)` means call `App.main`" | Misunderstanding configuration sources | Distinguish `classes` from `useMainMethod` |
| "`ALWAYS` runs `java -jar` in another JVM" | Putting `System.exit` in `main` kills the test runner | Understand it invokes `main` inside the test JVM |
| "`WHEN_AVAILABLE` guarantees `main` exists" | Tests can silently fall back | Use `ALWAYS` when the invariant matters |
| Measuring `main` with one suite-wide static counter | Flaky due to cache/parallelism/global state | Use Environment markers / per-context beans |
| Using `@PreDestroy` to count after every test | Wrong assertions due to context caching | Control cache or test lifecycle separately |
| Putting destructive DB migrations inside a runner | Tests and Devtools may re-run the job | Use migration frameworks and idempotency |
| Switching every test to `ALWAYS` to fix one bug | Side effects, slow tests, hard to control | Enable only for tests needing launcher parity |
| Testing only with `NEVER` | Misses `main`-specific config bugs | Include targeted `ALWAYS` tests |
| Assuming default `MOCK` opens a real HTTP server | Tests sending localhost requests fail | Use `RANDOM_PORT` when real HTTP is needed |
| Misplacing `@TestConfiguration` | Fails to find primary config | Understand nested configuration resolution |
| Calling `System.setProperty` in `main` | Leaks configuration into other tests | Prefer Environment properties/initializers |
| Test method calling `main()` manually | Can create a second context unmanaged by TestContext | Use `useMainMethod=ALWAYS` |
| Runner calling `System.exit` when done | Maven test process is killed | Runner returns outcome; entrypoint decides exit |
| Reading logs instead of assertions | Reordered/cached logs are inconclusive | Assert against Environment and bean state |

## 19. A sound testing model for main-specific logic

A three-layer strategy:

**Layer A — Unit tests:**
- Test services and business logic with JUnit without Spring.
- No dependency on entrypoint or context.
- Use mocks/fakes for network I/O.

**Layer B — Spring integration tests:**
- Use default `@SpringBootTest` or test slices.
- Select profiles/properties suited to the test environment.
- Verify dependency injection, bean lifecycle, runner behavior, and transactions.
- Avoid depending on `main` customizations unless that itself is the test target.

**Layer C — Bootstrap/launcher tests:**
- Use a few well-targeted `@SpringBootTest(useMainMethod=ALWAYS)` tests.
- Assert `main` profiles/default properties/listeners are applied.
- When process args, native env, and OS exit codes must be checked, use a subprocess with the packaged artifact.
- Never allow "launcher" tests to cause uncleaned side effects.

Three layers answer three different questions: is the logic right, is the context right, and is the production entrypoint path right.

### Why keep main thin?

A thin `main`:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

reduces divergence between test and production paths. Configuration beans or Boot config properties are loaded by both paths. Still, not every `main` has to be thin; some projects need entrypoint customizers. In that case, **actively test** those customizations with `useMainMethod` or extract them into independently testable configuration.

## 20. Review questions

**Question 1:** Does `@SpringBootTest` call `MyApplication.main` by default?

**Answer:** No. Default `useMainMethod=NEVER`; TestContext creates a test `SpringApplication` from the configuration class.

**Question 2:** Without calling `main`, are beans still created?

**Answer:** Yes. `SpringApplication` still creates/refreshes the `ApplicationContext`, processing beans, injection, and lifecycle per test configuration.

**Question 3:** Does `ApplicationRunner` execute in default `@SpringBootTest`?

**Answer:** It can and normally does if the runner bean exists and `SpringApplication` startup succeeds. It is a Boot startup hook, not code in the Java `main` body.

**Question 4:** Distinguish `ALWAYS` from `WHEN_AVAILABLE`?

**Answer:** `ALWAYS` requires `main` and fails if missing; `WHEN_AVAILABLE` uses `main` if present, otherwise falls back.

**Question 5:** Which annotation forces tests to invoke `main`?

**Answer:** `@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)`.

**Question 6:** Does `@SpringBootTest(classes = MyApplication.class)` force `main` to run?

**Answer:** No. `classes` selects the configuration source; `useMainMethod` controls invoking `main`.

**Question 7:** Is `@PostConstruct` skipped when `main` does not run?

**Answer:** No, as long as the bean is instantiated. It is a bean lifecycle callback.

**Question 8:** Can `ApplicationReadyEvent` occur in default `@SpringBootTest`?

**Answer:** Yes, on the successful `SpringApplication` startup path; Java `main` does not need to be called.

**Question 9:** When do tests miss a `setAdditionalProfiles` profile from `main`?

**Answer:** When tests use `NEVER`, unless that profile is activated by another source.

**Question 10:** Does `@SpringBootTest(args = "--x=y")` cause `main` to run?

**Answer:** No. Args are passed to the test `SpringApplication`; `useMainMethod` remains independent.

**Question 11:** Is a test whose `main` calls `System.exit` safe with `ALWAYS`?

**Answer:** No. It can terminate the test runner JVM, halting the entire suite.

**Question 12:** Does `@PreDestroy` run after every `@Test`?

**Answer:** Not by default; contexts may be cached across multiple test methods/classes.

**Question 13:** `MAIN_METHOD_INVOKED` is absent, yet `RUNNER_EXECUTED` appears. Is that contradictory?

**Answer:** No. That is the classic behavior of default `@SpringBootTest`: `SpringApplication` runs via the test loader, not via `main`.

**Question 14:** Does `useMainMethod=ALWAYS` guarantee tests are 100% equivalent to production `java -jar`?

**Answer:** No. JVM, classpath, profiles, test properties, web environment, and external services can differ.

**Question 15:** When should `main` logic be refactored into Spring configuration?

**Answer:** When customizations/side effects are needed in both runtime and tests, or require independent verification, avoiding an overly complex entrypoint.

## 21. Practice exercises

### Exercise 1 — comparing default vs. ALWAYS

Run `mvn -Dtest=MainDefaultTest test` then `mvn -Dtest=MainAlwaysTest test`. Note the `main`, bean, and runner markers; compare Environment properties/profiles with assertions.

### Exercise 2 — adding a @Test method

In `MainDefaultTest`, add a second test method that also injects `StartupState`. Observe `runnerCalls()` stays 1 if the context is reused; explain why runners do not re-run per method.

### Exercise 3 — changing configuration in main

Change `setAdditionalProfiles("from-main")` to `setAdditionalProfiles("another-profile")`, update the `ALWAYS` test assertion, and re-run. Default `NEVER` still does not automatically pick up the new profile.

### Exercise 4 — passing args

Change `MainArgumentsTest.args` to `--lesson.cli.marker=another-value` and update the assertion. Confirm the `main` marker still does not appear for the default context.

### Exercise 5 — ALWAYS when main is missing

Create a `@SpringBootConfiguration` class without `main`; write a test with `classes` pointing to it and `useMainMethod=ALWAYS`. Observe the context creation failure, then switch to `WHEN_AVAILABLE` and verify it bootstraps from valid config.

### Exercise 6 — runner side effects

Add a mock runner appending an item to an in-memory list, and verify it executes when default `@SpringBootTest` builds the context. Then use `@ConditionalOnProperty` to disable the runner for a subset of tests. Never use real external email/payments.

### Exercise 7 — verifying cleanup

Add a `SmartLifecycle` or resource bean with `@PreDestroy`. Observe callbacks when the context closes; experiment with `@DirtiesContext` and explain why destruction is not tied strictly to each test method.

### Exercise 8 — testing webEnvironment

Add the web starter in a separate project, try `MOCK` and `RANDOM_PORT`, and observe whether a real embedded server port opens. Never use web-type differences to conclude `main` was called.

### Exercise 9 — test-supplied profile

Use `@ActiveProfiles("from-main")` in a default `NEVER` test. Confirm the profile is active even though `main` did not run; explain why an active profile **is insufficient** to prove `main` ran.

### Exercise 10 — context cache

Run full `mvn test` and observe logs showing when Spring contexts are created. Notice why bean init logs may appear fewer times than the number of test methods, and use per-context state instead of static counters.

### Exercise 11 — testing the packaged launcher

Build `mvn package`, run `java -jar` in a subprocess, and verify the `MAIN_METHOD_INVOKED` marker. Compare against `MainDefaultTest`. Never call `System.exit` inside the test runner JVM.

### Exercise 12 — testing failure paths

Put a `main`-customization controlling a conditional bean. A `NEVER` test fails due to missing bean, while `ALWAYS` succeeds. Inspect the condition report and identify the **root cause** as missing bootstrap profile/property rather than `@SpringBootTest` failing to create beans.

## 22. Official documentation

- [Spring Boot 3.5.16 — Testing Spring Boot Applications, Using the Test Configuration Main Method](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): default skips `main`, `ALWAYS`, and `WHEN_AVAILABLE`.
- [Spring Boot 3.5.16 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment`, and default `useMainMethod=NEVER`.
- [Spring Boot 3.5.16 — SpringBootTest.UseMainMethod Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.UseMainMethod.html): `NEVER`, `ALWAYS`, `WHEN_AVAILABLE`.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): Boot startup sequence, runners, events, and profiles.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html): starter-test, JUnit Jupiter, test slices, and TestContext.
- [Spring Framework 6.2 — TestContext Framework Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cached contexts, `@DirtiesContext`, and cleanup.
- [Spring Framework 6.2 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): `@PostConstruct`, `@PreDestroy`, and Lifecycle/SmartLifecycle.

## 23. Summary and checklist

Before writing or modifying a Spring Boot test:

1. Does the test need the **Spring context**, the **`main` entry point path**, or both?
2. Is `useMainMethod` currently `NEVER`, `ALWAYS`, or `WHEN_AVAILABLE`?
3. Does `main` customize profiles, properties, listeners, or application settings?
4. Are those customizations truly needed in tests, or should they move into shared config?
5. Do `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct`, and `SmartLifecycle` have side effects?
6. Might the test accidentally call `System.exit` or create JVM-global resources?
7. Do `classes`/test packages point to the right primary `@SpringBootConfiguration`?
8. Does `webEnvironment` start a real server or only a mock context?
9. Have `@SpringBootTest(args)` and test `properties` been distinguished from calling `main`?
10. Do context caching, `@DirtiesContext`, or parallel tests affect counters/logs?
11. Does the test have assertions proving `main`-specific customizations were actually applied?
12. Is a subprocess/smoke test needed to verify the runtime process outside the test JVM?

**Final takeaways:**

- **`@SpringBootTest` does not invoke Java `main` by default**: `UseMainMethod.NEVER`.
- **The context still starts**, and bean lifecycle and Boot runners can still execute.
- **`ALWAYS` invokes `main` and fails if `main` does not exist**; **`WHEN_AVAILABLE` invokes it if present and falls back otherwise**.
- `classes` is a configuration source, not a command to call `main`; `args` are application arguments, not an automatic change to `useMainMethod`.
- Logic in `main` such as `setAdditionalProfiles` and `setDefaultProperties` is not automatically present in default tests.
- TestContext uses **context caching**: do not infer callback/startup counts from `@Test` counts.
- When production bootstrap parity is required, write targeted controlled `ALWAYS` tests without calling `System.exit` in the test JVM.
- When only testing services/bean graphs, default `NEVER` is usually better; keep the entrypoint thin, with side effects governed by independently testable configuration/lifecycle.
