# Choosing useMainMethod When Verifying Setup Inside main

**Module:** Spring Boot Application Runtime → **Lifecycle Testing**. This lesson explains `@SpringBootTest`'s `useMainMethod` attribute, how to choose `NEVER`, `WHEN_AVAILABLE`, or `ALWAYS`, and how to write integration tests proving that configurations **performed inside `public static void main(String[] args)`** actually participated in creating the `ApplicationContext`. It contrasts this with tests creating contexts **without passing through `main`**, handling apps without `main`, side effects, context caching, and interactions with startup lifecycles.

**Lab environment:** Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, AssertJ, Maven. Standalone project requiring no web server; tests use `@SpringBootTest(webEnvironment = NONE)`. The Java files and `pom.xml` below form a buildable lab, not isolated snippets. Certain extended snippets are clearly marked so they are not accidentally copied into the runnable part.

**Key point:** `@SpringBootTest` **does not call `main()` by default**. If important configuration lives only in `main` — such as `SpringApplication.setAdditionalProfiles(...)`, `addInitializers(...)`, `setApplicationStartup(...)`, or custom listeners — default tests may **fail to verify** the production startup flow. To verify the exact `main` path, choose `useMainMethod = UseMainMethod.ALWAYS` and assert concrete outcomes.

## 1. Learning objectives

After this lesson, you should be able to:

1. Know `useMainMethod` is an attribute of `org.springframework.boot.test.context.SpringBootTest`, of type `SpringBootTest.UseMainMethod`.
2. Accurately interpret `NEVER` (default), `WHEN_AVAILABLE`, and `ALWAYS`.
3. Explain why the same `@SpringBootApplication` can yield two contexts with different settings depending on whether tests call `main`.
4. Choose `ALWAYS` when `main`-only behaviors are mandatory production contracts.
5. Choose `WHEN_AVAILABLE` when you want to leverage `main` **if present**, while accepting fallback when absent.
6. Choose `NEVER` when bootstrapping a test-isolated context without letting `main` side effects interfere.
7. Write tests proving whether custom profiles added by `main()` are active.
8. Write tests proving whether an `ApplicationContextInitializer` registered in `main` creates a marker bean.
9. Verify `ConfigurableApplicationContext.getApplicationStartup()` after `main` sets `BufferingApplicationStartup`.
10. Distinguish running `main` to configure `SpringApplication` from calling `main` directly inside a `@Test` (which risks creating a second context).
11. Know that `ALWAYS` fails when `main` is absent while `WHEN_AVAILABLE` falls back; practice with a `@SpringBootConfiguration` lacking `main`.
12. Understand Spring Test context caching, lifecycle hooks, and why `main` does not run before **every** test method.
13. Recognize risks of `System.exit`, static/global state, browser/service starts, event listeners, JVM shutdown hooks, and ports when letting tests run `main`.
14. Have a QA matrix confirming behavior without relying on log order or Maven test execution order.

## 2. How does @SpringBootTest differ from calling main directly?

Normally an application has an entrypoint:

~~~java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

This is an **architectural snippet**, not a complete file from the lab below. If `main` merely calls `SpringApplication.run(...)`, default test context results are quite similar. In real apps, however, `main` may instantiate `SpringApplication` and configure it:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

application.setAdditionalProfiles("production-bootstrap");
application.addInitializers(context -> {
    // Add beans/configuration sources during prepare phase.
});
application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

This is a **snippet** requiring imports, `MyApplication`, and an appropriate initializer implementation; the runnable lab in section 6 provides complete code.

Because calls like `setAdditionalProfiles`, `addInitializers`, and `setApplicationStartup` **occur before Spring refreshes the context**, they can affect:

- Which profiles are active when evaluating `@Profile`.
- Which beans are available right from context prepare/initialize.
- How startup steps and startup events/metrics are recorded.
- `ApplicationContext` creation mode, banner, lazy initialization, listener registration, and other initializations.
- Logic running in `ApplicationRunner`, `CommandLineRunner`, or lifecycle components depending on environment/bean definitions.

`@SpringBootTest` does not call `main` by default merely because `@SpringBootApplication` points to that class. Spring Boot Test has a mechanism that **initializes a test-dedicated `SpringApplication`** from the configuration class. Thus regular tests can pass while real runtime startup has different profiles/initializers/listeners.

### 2.1. Three bootstrap paths

~~~text
Running production/CLI application
  -> Java main(args)
  -> customizations on SpringApplication
  -> application.run(args)
  -> ApplicationContext refresh / lifecycle / runners / ready

@SpringBootTest (useMainMethod = NEVER) [default]
  -> Spring Boot Test bootstrapper
  -> creates test SpringApplication
  -> loads @SpringBootConfiguration
  -> refresh context / lifecycle / runners / ready
  -> DOES NOT call Java main

@SpringBootTest (useMainMethod = ALWAYS)
  -> Spring Boot Test bootstrapper
  -> locates main on @SpringBootConfiguration
  -> executes main in the TestContext-managed bootstrap flow
  -> main configures SpringApplication, calls run(args)
  -> test uses the context from that exact bootstrap flow
~~~

`WHEN_AVAILABLE` chooses **use `main` if found**, otherwise falling back to **test-specific `SpringApplication`**. Do not treat the description above as an internal implementation diagram guaranteeing all callback/thread timings; it is an API semantic diagram backed by Spring Boot 3.5 documentation.

## 3. Enum SpringBootTest.UseMainMethod

Exact package:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
~~~

Comparison table:

| Value | Calls main? | If main is not found | When to choose |
|---|---|---|---|
| `NEVER` | **No** | Still creates test-specific context if configuration is valid | Test context isolated from `main` setup |
| `WHEN_AVAILABLE` | **Yes if found** | **Fallback** to test-specific path | Projects with modules with/without `main`, needing flexibility |
| `ALWAYS` | **Mandatory** | **Test fails** at bootstrap | Contract requires going through `main` setup |

The default value of `@SpringBootTest.useMainMethod` is **`UseMainMethod.NEVER`**. This is intentional Spring Boot behavior, not a test framework bug missing `main`.

### 3.1. NEVER: choosing the test-specific context

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.NEVER)
class SomeContextTest {
}
~~~

This is equivalent to the default when considering only `useMainMethod`:

~~~java
@SpringBootTest
class SomeContextTest {
}
~~~

The two snippets above are not complete test files; the runnable part in section 7 includes assertions. With `NEVER`, `SpringBootTest` still refreshes the context, creates beans, and runs appropriate callbacks for bootstrapping tests; it simply **does not execute Java `main`**. It is **wrong** to say "`NEVER` skips the startup lifecycle".

### 3.2. WHEN_AVAILABLE: tolerating missing main

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class MainOptionalTest {
}
~~~

If the class identified as `@SpringBootConfiguration` has `main`, Boot uses it; otherwise, Boot builds a test-specific `SpringApplication`. When the requirement is "the test must definitely run code inside `main`", `WHEN_AVAILABLE` is **not strict enough**: if someone deletes or moves `main`, the test can still boot successfully via fallback and mask the architectural change.

### 3.3. ALWAYS: fail-fast if main is missing

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)
class MainContractTest {
}
~~~

If the configuration class lacks a valid `main`, the test **does not fall back** and fails during bootstrap. When `main` is required to install instrumentation/initializers/listeners, this is typically the right choice.

**Note:** `ALWAYS` does not replace `@SpringBootTest` with a child process. `main` executes inside Spring Boot's test bootstrap mechanism; the test framework still manages the context, dependency injection, cache, and teardown. Do not assume a new PID/JVM or 100% `java -jar` parity.

### 3.4. Scope of the annotation

`UseMainMethod` is a **nested enum of `@SpringBootTest`**, not an `application.properties` key like `spring.test.use-main-method`. Setting a system property or declaring a custom property matching the enum name does not replace declaring the annotation.

Test slices such as `@WebMvcTest`, `@DataJpaTest`, and `@JsonTest` have different bootstraps and component scopes. Do not assume every slice has a `useMainMethod` attribute or needs to run full `main` to test a controller/repository. The purpose of `ALWAYS` is **verifying full-context bootstrapping** when `main` holds configuration worth testing.

## 4. When do you really need tests to go through main?

Settings appearing inside `main` should enter integration test contracts if they affect behavior:

| Setting in main | How can it be verified? | Why default NEVER misses it |
|---|---|---|
| `setAdditionalProfiles("custom")` | `Environment.acceptsProfiles(...)`, `@Profile` beans | Profile is not added via `main` code |
| `addInitializers(...)` | Marker bean, property source, init side effect | Initializer is not registered from `main` |
| `setApplicationStartup(...)` | `getApplicationStartup()`, timeline recorder | Test creates its own `SpringApplication` |
| `addListeners(...)` | Observable marker/log/bean from listener | `main`-only listener is not attached |
| `setDefaultProperties(...)` | `Environment.getProperty(...)` | Default properties from `main` are not loaded |
| `setLazyInitialization(...)` | Appropriate bean creation timing/behavior | Test may eager-init differently |
| `setApplicationContextFactory(...)` | Context class/type and infrastructure | Test may use default context factory |
| `setBannerMode(...)` | Banner/log output | Usually low business value; avoid brittle stdout tests |
| Custom `SpringApplicationBuilder` | Parent/child structure, profiles, context | Default test bootstrap skips builder code |
| Custom early listeners | Measurable side effect or trace marker | `@EventListener` beans in context may be too late |

**Classification:** If `main` setup is only changing banner colors or printing a greeting, a full test calling `main` is not strictly necessary. If that setup determines the bean graph, environment, startup instrumentation, observability, shutdown hooks, or bootstrap behavior, verify it with `ALWAYS`. Furthermore, hard-to-test side effects can be extracted into configuration beans/initializers tested separately for simplicity.

## 5. Choosing test style by goal

| Goal | Recommended configuration | Minimum evidence |
|---|---|---|
| Test isolated business service | Unit test without creating context | Method result and fake dependencies |
| Test general Spring wiring | Default `@SpringBootTest` (`NEVER`) | Beans, config, lifecycle |
| Test runtime exactly as configured by `main` | `@SpringBootTest(useMainMethod=ALWAYS)` | Profile/initializer/applicationStartup |
| `main` may or may not exist per module | `WHEN_AVAILABLE` | Separate branches with and without `main` |
| Test lacking `main` yet still needing boot context | `WHEN_AVAILABLE` or `NEVER` | Context loads and beans suffice |
| Verify **test must fail when `main` is removed** | `ALWAYS` | Bootstrap fails when `main` is not found |
| Test real HTTP | `@SpringBootTest(webEnvironment=RANDOM_PORT,...)` when suitable | HTTP response + lifecycle |
| Test MVC without real server | `@WebMvcTest` / full context `MOCK` | Request mapping/service boundary |
| Test OS exit status, shutdown hooks, and `System.exit` | Fork subprocess/JAR integration test | Process exit status, signals, logs |

You can use `@SpringBootTest(webEnvironment=NONE, useMainMethod=ALWAYS)` for this lesson because we are not testing HTTP. Never open a real port just to check a profile/initializer that the test does not need. Lifecycle beans can still initialize inside a non-web context if their corresponding dependencies exist.

## 6. Runnable Java 17/Spring Boot 3.5 Maven project

### 6.1. Directory structure

Create a Maven project named `use-main-method-lab` with Java 17, Spring Boot 3.5.16, package `com.example.mainmethod`. Spring Web/Actuator dependencies are unnecessary; `spring-boot-starter` and `spring-boot-starter-test` suffice.

~~~text
use-main-method-lab/
  pom.xml
  src/main/java/com/example/mainmethod/
    MainMethodLabApplication.java
  src/main/resources/
    application.properties
  src/test/java/com/example/mainmethod/
    DefaultNeverTest.java
    AlwaysMainTest.java
    WhenAvailableMainTest.java
  src/test/java/com/example/nomain/
    NoMainConfiguration.java
    NoMainFallbackTest.java
~~~

**Note on packages:** `com.example.nomain` sits **outside** the default component scan scope of `com.example.mainmethod`, preventing the fallback experiment configuration from being scanned into the full app. Each `public class` is placed in a matching filename. Run everything with Maven `test`.

### 6.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>use-main-method-lab</artifactId>
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

`spring-boot-starter-test` brings in compatible JUnit Jupiter, Spring Test, and AssertJ versions under the parent POM's dependency management. There is no need to add separate versions for individual test libraries. If your organization approved a different Spring Boot 3.5.x release, use that version and re-run QA. Spring Boot 3.5.16 was released in June 2026; it is used here as a concrete version for the lab, without claiming it is always the recommended long-term production version.

### 6.3. Main: three changes that exist only when running main()

File `src/main/java/com/example/mainmethod/MainMethodLabApplication.java`:

~~~java
package com.example.mainmethod;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class MainMethodLabApplication {

    public static void main(String[] args) {
        System.out.println("LAB_MAIN_ENTER");

        SpringApplication app =
                new SpringApplication(MainMethodLabApplication.class);

        // (1) Add profile only when main() is called.
        app.setAdditionalProfiles("main-only");

        // (2) Add initializer only when main() is called.
        app.addInitializers(context -> context.getBeanFactory()
                .registerSingleton(
                        "registeredInMain",
                        new MainMarker("initializer")));

        // (3) Replace recorder before context refresh.
        app.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        app.run(args);
    }

    @Bean
    @Profile("main-only")
    ProfileOnlyService profileOnlyService() {
        return new ProfileOnlyService("profile-bean");
    }

    public record MainMarker(String source) {
    }

    public record ProfileOnlyService(String source) {
    }
}
~~~

**Mechanism explanation:**

1. `LAB_MAIN_ENTER` is a secondary marker for observing the console; **do not use it as the primary assertion** because contexts can be cached or logs interleaved across multiple tests.
2. `setAdditionalProfiles("main-only")` adds an active profile to the `SpringApplication` created by `main`; the `@Bean @Profile("main-only")` method is registered only when that profile is active.
3. `addInitializers(...)` adds an `ApplicationContextInitializer`. Inside `initialize(...)`, the code registers a singleton named `registeredInMain` of type `MainMarker`. This marker bean **has no other `@Component` or `@Bean`**, so it appears only when `main`'s initializer actually ran.
4. `setApplicationStartup(new BufferingApplicationStartup(2048))` installs the recorder before `run`; the context has `getApplicationStartup()` of type `BufferingApplicationStartup` on the `main` path.
5. `app.run(args)` is where Spring builds/refreshes the context, instantiates profile beans, and activates runners/lifecycle like a normal application.
6. There is no `System.exit`, `SpringApplication.exit`, OS command execution, external server startup, or global/static state mutating tests. This makes invoking `main` in tests safer.
7. `MainMarker` and `ProfileOnlyService` are **public** nested Java records; tests can reference them via `MainMethodLabApplication.MainMarker.class` and `ProfileOnlyService.class`.
8. The marker is registered by explicit name, not created by Spring component scanning on the `NEVER` branch.
9. If running `java -jar` directly, without Spring Web the app initializes a CLI context and terminates normally once no non-daemon work remains. This is not a web service keeping a socket open.

**Real setups can also add listeners or a context factory in `main`**, yet the lab picks three settings easily asserted via the context. Never turn `System.out.println` or static counters into the primary evidence of the bootstrap flow.

### 6.4. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=use-main-method-lab
spring.main.banner-mode=off
logging.level.root=WARN
~~~

**Do not set** `spring.profiles.active=main-only`, do not register `registeredInMain` via another configuration, and do not declare a custom `ApplicationStartup` outside `main`. Adding those would let the `NEVER` test observe similar effects without calling `main`, spoiling the experiment design.

## 7. Test 1 — NEVER: main does not run and none of the three signals appear

File `src/test/java/com/example/mainmethod/DefaultNeverTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DefaultNeverTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void defaultNeverSkipsMainCustomization() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isFalse();

        assertThat(context.getBeanNamesForType(
                MainMethodLabApplication.ProfileOnlyService.class))
                .isEmpty();

        assertThat(context.containsBean("registeredInMain"))
                .isFalse();
    }
}
~~~

**Why omit `useMainMethod`?** To prove that `@SpringBootTest`'s default value is `NEVER`. The same annotation can be written explicitly as `useMainMethod = UseMainMethod.NEVER` with identical results. The test still loads the context, injects `ApplicationContext`, and runs JUnit. It does not invoke Java `main`, so the `main-only` profile and initializer marker do not appear.

In a clean test environment, the PASS condition for this test is **all three assertions are false/empty**. If the runner sets a global `main-only` profile via environment, IDE, or JVM args, the test can fail because the external environment enabled the profile. When reproducibility is needed, use a unique sentinel profile name and ensure no external profile property interferes; do not alter the test to accept an accidentally enabled profile.

**Do not confuse:** Lacking `registeredInMain` **does not** mean `@PostConstruct`, bean initialization, or Spring Boot's lifecycle were skipped. `NEVER` only affects the path of **locating and invoking `main`** when booting the test context.

## 8. Test 2 — ALWAYS: requiring main and verifying all three changes

File `src/test/java/com/example/mainmethod/AlwaysMainTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
class AlwaysMainTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void mainCustomizationsArePresent() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isTrue();

        assertThat(context.getBean(
                MainMethodLabApplication.ProfileOnlyService.class)
                .source()).isEqualTo("profile-bean");

        assertThat(context.getBean(
                "registeredInMain",
                MainMethodLabApplication.MainMarker.class)
                .source()).isEqualTo("initializer");

        assertThat(((ConfigurableApplicationContext) context)
                .getApplicationStartup())
                .isInstanceOf(BufferingApplicationStartup.class);
    }
}
~~~

**Meaning of the four assertions:**

1. `main-only` is in profiles because `main` called `setAdditionalProfiles`.
2. Bean `ProfileOnlyService` is created because `@Profile("main-only")` matches the environment.
3. Bean `registeredInMain` proves the initializer registered exclusively in `main` was applied.
4. `BufferingApplicationStartup` proves the startup instrumentation configured before `run` entered the context.

These assertions are **stronger** than merely looking for `LAB_MAIN_ENTER` in stdout; no other path in the lab produces those effects. If someone accidentally deletes `addInitializers(...)` or `setApplicationStartup(...)` in `main`, the test fails on the exact contract under check.

**One point to remember:** `ALWAYS` **does not** mean `main` runs before every `@Test`. TestContext may cache the application context; `main` executes when the context needs to be created. Assert effects **present** in the context, rather than asserting how many times `main` was called via a static counter.

## 9. Test 3 — WHEN_AVAILABLE: uses main when present

File `src/test/java/com/example/mainmethod/WhenAvailableMainTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class WhenAvailableMainTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void usesMainBecauseItExists() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isTrue();

        assertThat(context.containsBean("registeredInMain"))
                .isTrue();
    }
}
~~~

In this project `MainMethodLabApplication` has `public static void main(String[] args)`, so `WHEN_AVAILABLE` passes through `main` and both assertions are true. Yet if `main` is moved/deleted during a refactor and the configuration class loses `main`, `WHEN_AVAILABLE` **does not fail fast**; it falls back to creating a test-specific context instead. Therefore, if you require "`main` has mandatory setup", use **`ALWAYS`**, not `WHEN_AVAILABLE` merely because the test currently passes.

The difference between `ALWAYS` and `WHEN_AVAILABLE` is not about "when `main` exists, either works", but about the **contract when `main` does not exist**.

## 10. Test 4 — WHEN_AVAILABLE without main: fallback

To demonstrate real fallback, create a configuration **without `main`** outside the main app's package.

File `src/test/java/com/example/nomain/NoMainConfiguration.java`:

~~~java
package com.example.nomain;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
public class NoMainConfiguration {

    @Bean
    String fallbackBean() {
        return "created-without-main";
    }
}
~~~

File `src/test/java/com/example/nomain/NoMainFallbackTest.java`:

~~~java
package com.example.nomain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = NoMainConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class NoMainFallbackTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void loadsContextWithoutAnyMainMethod() {
        assertThat(context.getBean("fallbackBean", String.class))
                .isEqualTo("created-without-main");
    }
}
~~~

Here a valid `@SpringBootConfiguration + @EnableAutoConfiguration` lacks `main()`, yet `WHEN_AVAILABLE` still lets the context be created. That is **intentional fallback**. The test does not depend on the main app's `main-only` profile.

### 10.1. What happens with ALWAYS on NoMainConfiguration?

If you change the annotation in `NoMainFallbackTest` to:

~~~java
@SpringBootTest(
        classes = NoMainConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
~~~

then TestContext fails to find a valid `main` and **fails during bootstrap**. This is a **negative-experiment snippet**, not meant to replace the four green tests in the default suite. Try it on a copy or separate test command, then restore `WHEN_AVAILABLE`.

**Do not hardcode a single exception message:** Stack trace details can change across patch versions, yet the core invariant is that **the test cannot complete bootstrap via fallback** when `ALWAYS` is set on a configuration lacking `main`.

### 10.2. Why separate the packages?

If `NoMainConfiguration` were placed under `com.example.mainmethod` and `@ComponentScan` were accidentally added, it could get scanned into the main app, altering the bean graph/context search. Separating into `com.example.nomain` and specifying `classes` explicitly in tests keeps the illustration clean, avoiding "two competing `@SpringBootConfiguration`s" in the same auto-scan package.

## 11. Running all tests and reading results

### 11.1. Building/testing with Maven

On Linux/macOS if the project has a Maven Wrapper:

~~~bash
java -version
./mvnw -version
./mvnw clean test
~~~

If using pre-installed Maven:

~~~bash
java -version
mvn -version
mvn clean test
~~~

Windows PowerShell with Maven Wrapper:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean test
~~~

Windows PowerShell with pre-installed Maven:

~~~powershell
java -version
mvn -version
mvn clean test
~~~

The project sets `java.version=17`. Confirm `java -version` and Maven use JDK 17+; if `JAVA_HOME` points to an older JDK, the build can fail despite valid code. Each test file has a class name ending in `Test` so Maven Surefire discovers it by default parent POM rules.

### 11.2. Expected results

Four tests across the classes:

| Test | useMainMethod | Main exists? | Expected |
|---|---|---|---|
| `DefaultNeverTest` | NEVER (implicit) | Yes | `main-only` profile false, marker absent |
| `AlwaysMainTest` | ALWAYS | Yes | Profile/bean/initializer/startup recorder present |
| `WhenAvailableMainTest` | WHEN_AVAILABLE | Yes | Profile and marker present |
| `NoMainFallbackTest` | WHEN_AVAILABLE | No | Fallback context loads, bean present |

With the proper config files and dependencies, all four test methods are expected to **PASS**. Maven Surefire may print a summary like "Tests run: 4, Failures: 0, Errors: 0", though formatting and class order can vary across Maven/JDK versions and need not match a fixed stdout line.

In the console, `LAB_MAIN_ENTER` may appear when bootstrapping the `ALWAYS`/`WHEN_AVAILABLE` contexts. Do not assert the total printed marker count equals 2 in every environment, because context caching, test execution order, test parallelism, and test builds can change it. Assertions on the context are the primary evidence.

### 11.3. Running each class individually

Linux/macOS:

~~~bash
mvn -Dtest=DefaultNeverTest test
mvn -Dtest=AlwaysMainTest test
mvn -Dtest=WhenAvailableMainTest test
mvn -Dtest=NoMainFallbackTest test
~~~

Windows PowerShell with Maven:

~~~powershell
mvn "-Dtest=DefaultNeverTest" test
mvn "-Dtest=AlwaysMainTest" test
mvn "-Dtest=WhenAvailableMainTest" test
mvn "-Dtest=NoMainFallbackTest" test
~~~

Running individually helps isolate which class fails without depending on test suite order. `mvn -Dtest=... test` may create a fresh context per test JVM invocation; do not compare console counts across processes as an invariant.

### 11.4. Running the real JAR

~~~bash
mvn clean package
java -jar target/use-main-method-lab-0.0.1-SNAPSHOT.jar
~~~

When run this way, the JVM calls `main` per the JAR entrypoint, so `LAB_MAIN_ENTER`, the `main-only` profile, and the initializer all appear. Because the app is a CLI with no server, it can exit after startup once no non-daemon work remains. To verify profiles/beans in a production entrypoint, add controlled markers or integration probes; do not merely print logs while ignoring context state.

**Never call `MainMethodLabApplication.main(args)` directly inside a `@Test`** when intending to use the `@SpringBootTest`-managed context; doing so can create an extra independent context, run callbacks twice, and cause leaks/conflicts. Use `useMainMethod` so the Spring Boot Test bootstrapper controls the lifecycle.

## 12. Distinguishing effects on main vs. effects on ApplicationContext

### 12.1. Main before refresh, bean callbacks after

With the lab code:

~~~text
TestContext starts creating context
    |
    +-- If NEVER:
    |      TestContext creates its own SpringApplication
    |      Does not run LAB_MAIN_ENTER / setAdditionalProfiles
    |
    +-- If ALWAYS or WHEN_AVAILABLE with main:
    |      calls main
    |      setAdditionalProfiles("main-only")
    |      addInitializers(...)
    |      setApplicationStartup(...)
    |      app.run(args)
    |
    +-- create/prepare ApplicationContext
    +-- run ApplicationContextInitializer
    +-- refresh bean factory
    +-- evaluate @Profile("main-only")
    +-- instantiate beans, @PostConstruct, callbacks
    +-- lifecycle start, events, runners
    +-- test method executes with context
~~~

A bean's `@PostConstruct` is not "skipped" just because `main` didn't run. The difference lies in the **state/configuration established before the bean lifecycle begins**.

### 12.2. Semantics of initializers

`app.addInitializers(...)` registers an initializer for Spring to invoke **during context preparation before refresh**. It is not a listener invoked after the server is ready. If an initializer adds a property source or singleton bean, the app's bean graph can differ from a `NEVER` test. Section 6 uses a marker to verify that.

When a real app needs to configure initializers by profile or test mode, separate business rules from `main` so conditions aren't hardcoded and hard to test. Yet if production genuinely relies on an initializer registered in `main`, at least one integration test must traverse `main` and assert the outcome.

### 12.3. ApplicationStartup recorder

`BufferingApplicationStartup` must be attached before `SpringApplication.run` to record steps from early bootstrap stages. The `ALWAYS` test confirms the context uses the right recorder. The `NEVER` test does not receive the `main`-only recorder; to test startup timelines, either use `ALWAYS` or configure the recorder in TestContext via a supported mechanism.

Do not see Actuator `/actuator/startup` lacking events in a `NEVER` test and infer production isn't recording them. The two bootstrap paths can differ.

### 12.4. Events and listeners

An `@EventListener` bean in the context is typically registered during context refresh; **very early** events (before context/bean creation) may have already passed. If `main` uses `app.addListeners(...)` to register an early listener, `NEVER` skips that listener. With `ALWAYS`, tests can observe listener side effects if designed with safe markers. Avoid using a single global static counter across all tests to assert exact event counts due to context caching/parallel tests.

## 13. @SpringBootTest.args, properties, and active profiles

`@SpringBootTest` can pass arguments/properties to customize the context, yet **does not turn `NEVER` into `ALWAYS`**.

### 13.1. Passing args to SpringApplication

Example **annotation snippet**:

~~~java
@SpringBootTest(
        classes = MainMethodLabApplication.class,
        useMainMethod = UseMainMethod.ALWAYS,
        args = "--lab.mode=integration",
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
~~~

When the test goes through `main` and `main` calls `app.run(args)`, arguments supplied by test bootstrap can be used in `Environment`/runners. `main` code must not hardcode `new String[0]` instead of forwarding the received `args` if command-line behavior must be preserved. This snippet is not a complete test class; the main lab does not need `lab.mode`.

### 13.2. Properties do not prove main ran

If a test writes:

~~~java
@SpringBootTest(
        properties = "spring.profiles.active=main-only")
~~~

then a `NEVER` test can still enable the `main-only` profile via **the annotation itself**. In that case, an assertion checking a `@Profile` bean passes **without proving `main` called `setAdditionalProfiles`**. That is why the lab uses three independent signals and does not put this profile in `application.properties` or test properties.

Similarly, `@ActiveProfiles("main-only")` can mimic the `main` profile. In tests meant to verify `main`, choose a signal that **cannot be accidentally configured identically**, such as a singleton marker registered solely by an initializer inside `main`.

### 13.3. Property precedence order

Command-line args, test property sources, environment variables, and application properties have different precedence levels in Spring Boot. Do not claim "`main` always beats test properties": `setAdditionalProfiles` adds profiles, while `setDefaultProperties` acts as a fallback and can be overridden by higher-precedence sources. When testing a property from `main`, check both the final `Environment` value and its expected config source rather than merely asserting `SpringApplication`'s constructor was called.

## 14. Context caching and @DirtiesContext

Spring TestContext caches application contexts with equivalent configurations to reduce suite runtime. Consequences:

- `main()` (when `useMainMethod` invokes `main`) executes when the context **is created**, not before every method.
- If multiple test methods share a cached context, `main` setup is not necessarily re-executed.
- If a test mutates singleton state in the context, subsequent tests can observe the leftover state; avoid mutable shared state and clean up in `@AfterEach` if needed.
- `@DirtiesContext` forces the context to be evicted from the cache at the chosen scope; use it when a fresh startup/teardown is truly needed, not as a crutch to "fix" test flakiness.
- With varying configurations/test properties/active profiles, the test framework can create separate contexts. Do not design assertions around context counts unless you are explicitly measuring them.
- When parallel tests open ports or touch a global resource, `main` side effects can contend, especially with `webEnvironment=DEFINED_PORT`.

**Example of what not to do:**

~~~java
@Test
void assumesMainRunsBeforeEveryTestMethod() {
    // Should not assert static mainInvocationCount == 1
    // per test method when ContextCache may reuse the context.
}
~~~

This snippet illustrates an anti-pattern and is not in the runnable project. What is worth asserting is that **the context has the expected profile/initializer/recorder**, not how many times `main` was invoked.

## 15. Dangerous side effects when tests invoke main

If `main` exhibits any of the following behaviors, address them before enabling `ALWAYS` in CI:

| Behavior in main | Risk when running under JUnit | Mitigation |
|---|---|---|
| `System.exit(...)` | Terminates the entire test runner JVM | Refactor exit path; use subprocess for exit-code tests |
| `Runtime.halt(...)` | Skips shutdown hooks, kills JVM | Do not run inside TestContext |
| Spawning unclosed threads/executors | Keeps JVM alive, hangs tests | Assign owner bean, `@PreDestroy`/`SmartLifecycle` |
| Starting HTTP server on fixed port | Port collisions in parallel tests | Use `webEnvironment=NONE` or `RANDOM_PORT` |
| Writing files or deleting data | Corrupts dev/CI environment | Test-specific config, temp dirs, fake storage |
| Touching real external DB/broker | Mutates data, flakiness | Testcontainers, fakes, test environments |
| Sending real emails/HTTP webhooks | Unintended side effects | Stub/disable external integrations |
| Mutating global `System.setProperty` | Leaks state into other tests | Avoid globals, clean up in `finally` |
| `System.setOut(...)` | Corrupts logging and test harness | Avoid mutating global streams |
| Registering custom shutdown hooks | Hooks run outside expected test lifecycle | Separate owner, verify shutdown policy |
| Static mutable singletons | State leaks across contexts/tests | Refactor into beans or controlled resets |
| Heavy I/O in early `ApplicationListener` | Slows/hangs bootstrap | Lightweight handlers, instrumentation, deadlines |

**Rule:** `useMainMethod=ALWAYS` provides no automatic OS sandbox. It lets `main` execute inside the test environment. If `main` runs destructive or irreversible code, refactor it into a `SpringApplication` configuration method safe to call, or run the real app in a **separate process** with isolated resources.

### 15.1. Refactoring main to reduce risk

A testable design might look like:

~~~java
public static SpringApplication configuredApplication() {
    SpringApplication app =
            new SpringApplication(MyApplication.class);
    app.setAdditionalProfiles("custom");
    return app;
}

public static void main(String[] args) {
    configuredApplication().run(args);
}
~~~

This is a **snippet** requiring `MyApplication`, imports, and remaining configuration; do not overwrite the main lab with it. Refactoring enables unit testing `configuredApplication()` (via observable API/state) alongside a `useMainMethod=ALWAYS` integration test to confirm full bootstrapping. Never use unit tests of a factory method as a complete substitute for runtime tests if the app relies on effects during `run(args)`.

### 15.2. Startup failures in main

If `main` throws an exception before calling `run(args)`, `ALWAYS` causes test bootstrap to fail. That may be the right behavior for a real error. A `NEVER` test might load the context cleanly and mask that bug. Therefore, keep a test traversing `main` for core configuration.

If `main` catches an exception and calls `System.exit(0)`, an `ALWAYS` test is even more dangerous: the JVM terminates with 0 and CI can report misleading results. Fix the error handling rather than "fixing" it by switching `useMainMethod` to `NEVER` and ignoring the production bug.

## 16. Distinguishing useMainMethod from other lifecycle test styles

### 16.1. @SpringBootTest does not necessarily open an HTTP server

Common `@SpringBootTest.webEnvironment` modes:

| Mode | Meaning | Suitable for main demo? |
|---|---|---|
| `MOCK` (default) | Mock web context if web framework is on classpath; does not necessarily open a real port | Works, though web is unneeded |
| `RANDOM_PORT` | Opens embedded server on random port | Only needed when testing real HTTP |
| `DEFINED_PORT` | Opens server on `server.port` or default; risks port collisions | Avoid if only checking profiles/initializers |
| `NONE` | No web environment | **Chosen in the lab** |

`webEnvironment` and `useMainMethod` answer **two separate questions**: does the context open a web server, and does the boot path invoke `main`? Never set `RANDOM_PORT` and assume `main` was called.

### 16.2. Testing lifecycle callbacks

A test with `@SpringBootTest(useMainMethod=NEVER)` can still trigger:

- Bean construction/dependency injection.
- `@PostConstruct` / init callbacks.
- `SmartInitializingSingleton` for eligible singletons.
- `SmartLifecycle.start()` on context refresh when `autoStartup` conditions apply.
- Context events, runner callbacks, and `SpringApplication` lifecycle in the test startup path.

The difference is that **customizations in `main` are skipped**. If the question is "does `SmartLifecycle` run on refresh?", a `NEVER` test can work. If the question is "does `SmartLifecycle` run after the profile/initializer added by `main`?", choose `ALWAYS` to guarantee the right conditions.

### 16.3. ApplicationContextRunner differs from @SpringBootTest

`ApplicationContextRunner` builds controlled contexts very useful for unit/auto-configuration tests. It **does not automatically run the application's `public static void main`**. Use it to test conditions/properties/bean logic, then add at least one `@SpringBootTest(useMainMethod=ALWAYS)` if production relies on `main`-only effects.

### 16.4. Do not call main manually in @BeforeAll

The approach below is **not** equivalent to `SpringBootTest` `useMainMethod`:

~~~java
@BeforeAll
static void launch() {
    MainMethodLabApplication.main(new String[0]);
}
~~~

This is an **anti-pattern snippet**; the test context may already be bootstrapped separately by Spring Test. Calling `main` in `@BeforeAll` can spin up a **second context**, execute application runners twice, and leak executors/threads/ports. Choose `useMainMethod=ALWAYS` instead of manually launching a parallel app lifecycle outside TestContext's ownership.

## 17. QA matrix for this topic

| Scenario | Mode | Expected result | Design bug exposed |
|---|---|---|---|
| `main` has 3 customizations | NEVER | No `main`-only profile/marker | Default tests skip `main` |
| `main` has 3 customizations | ALWAYS | Profile, initializer marker, and recorder present | `main` setup deleted/altered |
| `main` has 3 customizations | WHEN_AVAILABLE | Present because `main` is found | May not fail later if `main` disappears |
| Config without `main` | WHEN_AVAILABLE | Test context boots via fallback | Entrypoint not required |
| Config without `main` | ALWAYS (negative test) | Bootstrap fails | Contract requiring `main` violated |
| `main` calls `System.exit` | ALWAYS | Must not run in same JUnit JVM | Subprocess needed |
| Test has `@ActiveProfiles("main-only")` | NEVER | Profile activates despite skipping `main` | Single assertion creates false positive |
| `main` adds initializer, test uses NEVER | NEVER | Marker bean absent | Test config drifts from production |
| `main` adds `BufferingApplicationStartup` | ALWAYS | Context recorder has matching type | Instrumentation needs pre-run setup |
| Multiple methods share context | ALWAYS | Effects remain; `main` need not re-run | Assertions on invocation count fail |
| App opens real server | ALWAYS + RANDOM_PORT | Server managed by test framework | Avoid fixed ports unnecessarily |

**Pass/fail principle:** Assert outcomes of the **created context** rather than log line counts, `main` invocation counts, or specific timings of a parallel test suite. For proving missing `main` fails, do not keep an intentionally failing `ALWAYS` class in the main test suite.

## 18. Common failure diagnostics

| Symptom | Hypothesis | How to verify |
|---|---|---|
| Profile in `main` inactive in `@SpringBootTest` | Default `NEVER` | Add `useMainMethod=ALWAYS`, assert Environment |
| `@Profile` bean differs between dev and test | `main` adds profile/PropertySource | Compare `main` setup, `@ActiveProfiles`, test properties |
| `@SpringBootTest` PASSES even though `main` was deleted | `NEVER` or `WHEN_AVAILABLE` fallback | Use `ALWAYS` for `main` contracts |
| `ALWAYS` fails "main method not found" | Config class lacks a valid `main` | Check `@SpringBootConfiguration` class used by test |
| `WHEN_AVAILABLE` still loads without `main` | Intended fallback behavior | See `NoMainFallbackTest` |
| Test runner exits abruptly | `main` calls `System.exit`/`halt` | Refactor, use subprocess |
| Two apps appear in logs | Test calls `main` manually while framework also bootstraps | Remove manual invocation |
| Actuator startup differs from runtime | Recorder attached only in `main` while test uses `NEVER` | Use `ALWAYS` or test-specific instrumentation |
| Initializer marker missing under `ALWAYS` | `main` code changed, initializer unregistered, or wrong config class | Check `classes` and marker registration |
| `ALWAYS` has profile yet lacks marker | Profile enabled elsewhere | Assert both initializer marker and recorder |
| Test sees marker despite `NEVER` | Marker registered in another `@Configuration` or global shared state | Ensure marker comes solely from `main` |
| Tests unusually slow | `main` opens external services or runners | Test resources, fakes, deadlines |
| Port 8080 busy | `main`/startup starts fixed-port server | `NONE`/`RANDOM_PORT` |
| Not every test method prints `LAB_MAIN_ENTER` | Context caching | Do not assert `main` invocation count |
| `@DirtiesContext` slows test suite | Forces context reloads | Use only when isolating mutable state |
| Test slice rejects `useMainMethod` | Annotation is not `@SpringBootTest` | Check scope and use full integration test if needed |
| JDK below 17 | Spring Boot 3.5 requires Java 17+ | Check `java`/Maven JDK |
| Maven test fails missing dependencies | `pom` missing `spring-boot-starter-test` or plugins | Check Maven effective deps/build |
| Test results differ in CI | External env/profile/global properties | Log active profiles, isolate config |
| `main` uses persistent `System.setProperty` | Global state leaks across tests | Refactor into Environment/property sources |

## 19. Practice exercises with verification criteria

### Exercise A — Default is NEVER

Run `DefaultNeverTest` and explain why `main-only` is inactive and `registeredInMain` does not exist, yet the context still loads and JUnit runs. Note that `NEVER` is a **bootstrap path choice**, not disabling the Spring lifecycle.

### Exercise B — Requiring main

Run `AlwaysMainTest`. Observe `LAB_MAIN_ENTER` if the console prints output; use assertions to confirm the profile, profile bean, initializer marker, and recorder. Temporarily remove `app.setAdditionalProfiles(...)` in a copy and re-run: the profile assertion fails. Restore the code afterward.

### Exercise C — Counter-proof via initializer

In a copy, remove `app.addInitializers(...)`. `AlwaysMainTest` must fail when looking up `registeredInMain`, while `DefaultNeverTest` still passes. This proves the `ALWAYS` test actually verifies `main`-only setup rather than an accidentally enabled property.

### Exercise D — WHEN_AVAILABLE with main

Run `WhenAvailableMainTest`. Confirm the profile/marker are present. Explain the difference in guarantees between `WHEN_AVAILABLE` and `ALWAYS` even though both currently yield true.

### Exercise E — WHEN_AVAILABLE without main

Run `NoMainFallbackTest`. Then in a copy change `WHEN_AVAILABLE` to `ALWAYS`; observe test bootstrap fail. Restore so the whole suite stays green. Do not rely on an exact exception message.

### Exercise F — Context cache

Add a second test method to `AlwaysMainTest` asserting the marker/recorder again. Explain why `main` does not have to be invoked twice. Avoid static counters if the test suite uses parallelism or caching.

### Exercise G — Main containing System.exit

Inspect a real entrypoint calling `System.exit(SpringApplication.exit(...))`. Explain why `ALWAYS` should not be enabled in the same JUnit JVM before refactoring. Design a `java -jar` subprocess test asserting exit status, logs, and cleanup.

### Exercise H — Web server or broker

Suppose `main` sets a profile enabling a listener container and adds an initializer changing a resource URI. Choose `ALWAYS` to test proper wiring; use fakes/Testcontainers for dependencies, `webEnvironment=NONE` when HTTP is unneeded, and `RANDOM_PORT` when HTTP verification is needed. Measure `SmartLifecycle` running/teardown and never call `main` manually again.

### Exercise I — Optimizing test policy

Classify the test suite into unit, slice, full-context `NEVER`, full-context `ALWAYS`, and subprocess smoke tests. Enable `ALWAYS` only for the group genuinely verifying `main` setup, avoiding unnecessary side effects across every test context.

## 20. Acceptance checklist

- [ ] Know `@SpringBootTest.useMainMethod` and import `SpringBootTest.UseMainMethod`.
- [ ] Correctly state default `NEVER`.
- [ ] Explain `WHEN_AVAILABLE` fallback when `main` is absent.
- [ ] Explain `ALWAYS` fail-fast when `main` is not found.
- [ ] Know profiles/initializers/recorders may be set up only in `main`.
- [ ] Run Maven Java 17 + Spring Boot 3.5 + JUnit Jupiter cleanly.
- [ ] `DefaultNeverTest` confirms profile inactive and marker bean absent.
- [ ] `AlwaysMainTest` confirms profile, profile bean, initializer marker, and Buffering recorder.
- [ ] `WhenAvailableMainTest` confirms `main` is used when available.
- [ ] `NoMainFallbackTest` confirms the context still loads when `main` is missing.
- [ ] Do not declare `spring.profiles.active=main-only` outside `main` in the lab.
- [ ] Do not call `System.exit` directly in the test runner.
- [ ] Do not call `main` manually from `@Test` or `@BeforeAll` to spin up extra contexts.
- [ ] Distinguish `WebEnvironment.NONE` from whether `main` is called.
- [ ] Do not infer `main` execution counts from log line counts due to context caching.
- [ ] Understand `@Profile` alters the bean graph before the bean lifecycle.
- [ ] Verify via context state rather than console-only checks.
- [ ] Know when to use default `NEVER` for unit/context wiring instead of `ALWAYS`.
- [ ] Have subprocess tests for exit status/signals if the entrypoint needs OS-level verification.
- [ ] Check test resources/ports/globals before running `main` in CI.

## 21. Official documentation

1. Spring Boot 3.5 — **Testing Spring Boot Applications, Using the Test Configuration Main Method**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
2. Spring Boot 3.5 — **SpringBootTest.UseMainMethod API** (NEVER/WHEN_AVAILABLE/ALWAYS): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.UseMainMethod.html
3. Spring Boot 3.5 — **SpringBootTest API** (`useMainMethod`, `args`, `properties`, `webEnvironment`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html
4. Spring Boot 3.5 — **SpringApplication API** (`setAdditionalProfiles`, `addInitializers`, `setApplicationStartup`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
5. Spring Boot 3.5 — **Application Startup** and `BufferingApplicationStartup`: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
6. Spring Framework 6.2 — **Testing, Context Caching**: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
7. Spring Framework 6.2 — **ApplicationContextInitializer**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
8. Spring Boot 3.5.16 official release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now

**Summary:** When a Spring Boot application has important logic in `main`, default `@SpringBootTest` (`NEVER`) tests can build a context **lacking** those settings. `WHEN_AVAILABLE` fits only when fallback is acceptable; `ALWAYS` is the right choice for tests that **require** running `main` and catching when `main` disappears. Assert **real profiles, initializers, bean graphs, and startup recorders** instead of merely inspecting logs. For entrypoints with side effects, `System.exit`, or OS calls, never let JUnit run `main` directly; extract safe configuration or verify via a subprocess with isolated resources.