# @SpringBootConfiguration Not Found or Wrong Configuration Selected

## 1. Problem: Spring Boot Tests Cannot Find the Right Bootstrap Entry Point

In the **Spring Boot - testing** module, under **Test Troubleshooting**, two symptoms are often confused:

1. A JUnit test fails **before `ApplicationContext` is created**, with an error along the lines of: **"Unable to find a @SpringBootConfiguration by searching packages upwards from the test"**.
2. The test boots an `ApplicationContext` yet **selects the wrong configuration**, leading to missing beans, wrong component scans, missing repositories, absent controllers, wrong profiles, hitting the wrong database, or loading the entire application when intending to test a single slice.

This is a **bootstrap source and classpath** issue before it is an assertion issue. The right fix is not adding `@SpringBootApplication` to every test, switching everything to `@DirtiesContext`, or adding `@ComponentScan("com")` across the whole project. You need to know **which configuration class** the Spring Boot test bootstrapper actually selects.

### A Typical Stack Trace

~~~text
java.lang.IllegalStateException:
  Unable to find a @SpringBootConfiguration by searching
  packages upwards from the test.
  You can use @ContextConfiguration,
  @SpringBootTest(classes=...) or other Spring Test
  supported mechanisms to explicitly declare the
  configuration classes to load.
  Classes annotated with @TestConfiguration
  are not considered.
~~~

This is a **condensed message pattern**; exact line numbers and packages in the stack trace vary by Spring Boot release. It tells you Spring Boot **could not automatically locate a primary application configuration** in the searched package hierarchy—not that the application lacks any `@Configuration` or that Gradle is missing test dependencies.

**Target outcome:** verify package layout, the main application class, and compile/test runtime classpaths; choose accurately among `@SpringBootTest(classes=...)`, auto-detection, `@SpringJUnitConfig`/`@ContextConfiguration`, `@TestConfiguration`, and slices like `@WebMvcTest`/`@DataJpaTest`; write JUnit tests verifying **bean identity, profiles, properties, classpath, and scan boundaries** rather than merely asserting that the context starts.

This lesson uses **Java 17 + Spring Boot 3.5.16 + Gradle 8.x + JUnit Jupiter + MockMvc + Spring Data JPA/H2**. It includes a complete project with 15 JUnit test methods across eight classes distinguishing full Boot context tests, web/JPA slices, nested and imported test configurations, out-of-package tests, and plain Spring TestContext tests.

## 2. What Is `@SpringBootConfiguration`?

Three annotations that are easy to confuse:

| Annotation | Nature | Role in Test Bootstrap |
| --- | --- | --- |
| `@Configuration` | Declares a source of Spring bean definitions | Can be used with `@ContextConfiguration`/`@SpringJUnitConfig`; **does not automatically act as Boot primary config** |
| `@SpringBootConfiguration` | Specialization of `@Configuration` marking a Boot app's primary source | **Searched by the Spring Boot test bootstrapper** during auto-detection |
| `@SpringBootApplication` | Combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan` | **Most common primary configuration** for full Boot apps |

Counter-example:

~~~java
@Configuration
public class AppConfig {
    @Bean
    SampleService sampleService() {
        return new SampleService();
    }
}
~~~

This is a **snippet**, not runnable source from the main example; `SampleService` is an illustrative type. Although this class can build a valid Spring `ApplicationContext` via `@SpringJUnitConfig(AppConfig.class)`, it is **not** the Boot entry point that `@SpringBootTest` looks for by default via `@SpringBootConfiguration`.

Typical application declaration:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

This is a **snippet**; the full runnable application in later sections is named `BootConfigApplication`. `@SpringBootApplication` is meta-annotated with `@SpringBootConfiguration`, so Spring Boot tests locate it automatically when the package layout aligns.

### Is `@SpringBootConfiguration` Alone Enough?

A class annotated only with `@SpringBootConfiguration` **does not automatically enable** component scanning or auto-configuration like `@SpringBootApplication`. It can serve as an intentionally minimal test source, yet if you expect JPA repositories, MVC controllers, and `@Service` beans to be scanned, you must supply the corresponding imports/configs. Thus, a test that **found a valid Boot configuration class** can still miss beans if that class supplies only partial wiring.

## 3. How Does Spring Boot Locate the Primary Configuration?

According to the Spring Boot 3.5 reference, if a Boot test annotation **does not explicitly declare configuration sources**, the framework searches **upwards from the test's package to parent packages** until it finds a class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`.

Good layout example:

~~~text
src/main/java/
  com/example/store/
    StoreApplication.java          @SpringBootApplication
    domain/OrderService.java
    web/OrderController.java

src/test/java/
  com/example/store/
    StoreApplicationTest.java      @SpringBootTest
    web/OrderControllerTest.java   @SpringBootTest or @WebMvcTest
    domain/OrderServiceTest.java
~~~

For a test in `com.example.store.web`, the ancestor package chain is:

~~~text
com.example.store.web
com.example.store
com.example
com
~~~

When `StoreApplication` resides in `com.example.store` and is on the **test runtime classpath**, Spring Boot locates the primary config. **It does not scan sibling packages, inspect source files on disk, or "remember" the main class from a Gradle `bootRun` command.**

Error-prone layout:

~~~text
src/main/java/com/example/store/StoreApplication.java
src/test/java/com/example/billing/InvoiceTest.java
~~~

Test package `com.example.billing` walks up to `com.example`; `StoreApplication` lives in a **sibling branch** `com.example.store`, outside the ancestor packages visited at each step, so lookup fails.

**Common pitfall:** the folder name under `src/test/java` matters less than the **Java `package` declaration** in the file and on the classpath. Moving a test file without updating its `package com.example...` statement may not change lookup the way you expect.

## 4. Decision Flow: Missing Config or Wrong Config Selected?

~~~text
JUnit test starts
       |
       v
Uses @SpringBootTest / Boot test slice?
       |
       +-- NO --> Uses @SpringJUnitConfig / @ContextConfiguration?
       |            -> Loads Spring context specified by the test;
       |               does not require finding @SpringBootApplication.
       |
       +-- YES --> Explicit primary classes specified?
                    |
                    +-- YES --> Verify classes match right module/app,
                    |           auto-configuration, and scan boundaries.
                    |
                    +-- NO --> Has nested static @Configuration?
                                   |
                                   +-- YES --> May use nested config
                                   |           instead of main Boot config.
                                   |
                                   +-- NO --> Search packages upwards
                                              for @SpringBootConfiguration
                                                   |
                                                   +-- Not found --> error
                                                   |    "Unable to find ..."
                                                   +-- Found --> load config
                                                        |
                                                        +-- Right app, bean fails?
                                                        |   inspect next cause
                                                        +-- Wrong app config?
                                                            specify explicit
                                                            source / fix package
~~~

This is a **diagnostic** flow, not a byte-for-byte internal algorithm of Spring Boot. The key insight: *primary configuration detection* happens before *bean creation*. If you already see JDBC connection errors, missing entities, or port conflicts, the framework almost certainly passed primary config detection.

## 5. Most Common Causes

| Cause | Symptom | Priority Remedy |
| --- | --- | --- |
| Test sits in a sibling package outside the application root | `@SpringBootConfiguration` not found | Move test under app package or use `@SpringBootTest(classes=MainApplication.class)` |
| Application class is in a source set/module missing from test runtime classpath | Cannot load/find main class | Fix Gradle project dependencies/`testRuntimeClasspath` |
| Main class only annotated with `@Configuration` | Boot test cannot find Boot marker | Use `@SpringBootApplication` for apps, or plain Spring test |
| Main has `@SpringBootConfiguration` without auto-config/component-scan | Context starts but beans are missing | Point to proper Boot app source or add targeted configs |
| Two/multiple Boot configuration candidates in search path | Possible ambiguity/multiple sources error | Specify `classes` explicitly or reorganize app/test config |
| Test has nested `@Configuration` | Test sees test bean but lacks real services | Use nested `@TestConfiguration` to add rather than replace primary |
| Test has nested/top-level `@TestConfiguration` and no Boot app | Still reports primary not found | `@TestConfiguration` **does not replace Boot primary** |
| Test mistakenly uses `@ContextConfiguration(classes=SmallConfig.class)` | Context lacks Boot auto-config | Use `@SpringBootTest(classes=App.class)` if Boot features are needed |
| `@WebMvcTest`/`@DataJpaTest` with wrong root config | Slice lacks expected beans or scans too widely | Fix primary source, scan filters, selective `@Import` |
| Explicit `@ComponentScan` on main application class | Slice filters get disabled | Avoid broad scans on main class; isolate specialized configs |
| Test uses wrong `@ActiveProfiles` | Conditional beans differ | Check properties/profiles after verifying config source |
| `integrationTest` source set task lacks main output | `ClassNotFound`/lookup failure | Fix `testClassesDirs` and `classpath` |
| Picks up config from another app in a monorepo | Context runs, yet unexpected beans appear | Pin explicit source and separate modules/packages |
| Unintended context cache reuse | Unexpected bean/state overrides | Compare context keys, qualifiers, profiles; avoid overusing `@DirtiesContext` |

Before editing code, write down the **test annotation, test `package` declaration, main app FQCN, `Test` task classpath, and first error line**. Any single mismatch in those five items explains most failures.

## 6. Distinguishing Three Test Styles to Choose the Right Mechanism

**Plain JUnit/Mockito test:**

~~~java
class TaxCalculatorTest {
    @Test
    void computesTax() {
        TaxCalculator calculator = new TaxCalculator();
        assertThat(calculator.taxFor(100)).isEqualTo(10);
    }
}
~~~

This is an **illustrative snippet** (`TaxCalculator` is undefined in the project); it needs no Spring `ApplicationContext` or `@SpringBootTest`, so it can never hit a missing `@SpringBootConfiguration` error.

**Plain Spring TestContext:**

~~~java
@SpringJUnitConfig(MiniConfig.class)
class MiniContextTest {
    @Autowired ExampleService service;
}
~~~

This is a snippet; `MiniConfig` and `ExampleService` are illustrative types. `@SpringJUnitConfig` combines `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`; it uses Spring TestContext and **does not ask Spring Boot to search for a main app**.

**Full Boot integration:**

~~~java
@SpringBootTest(classes = MyApplication.class)
class FullAppTest {
    @Autowired ExampleService service;
}
~~~

This snippet requires a real class. `@SpringBootTest` builds a context using `SpringApplication` and Boot features; when `classes` is explicit, it bypasses package auto-detection. For tests under the application root package, plain `@SpringBootTest` usually suffices.

**Slice tests:** `@WebMvcTest` configures the web layer; `@DataJpaTest` configures the JPA test slice. Neither means "automatically skip finding a primary Boot configuration." Naming a controller or entity in a slice **is not equivalent** to declaring the full bootstrap source.

## 7. Runnable Project: File Structure and Scope

Uses Java 17 / Spring Boot 3.5.16 / Gradle Groovy DSL. File tree:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/bootconfig/
  BootConfigApplication.java
src/main/java/com/example/bootconfig/core/
  WelcomeService.java
src/main/java/com/example/bootconfig/web/
  WelcomeController.java
src/main/java/com/example/bootconfig/data/
  NoteEntry.java
  NoteRepository.java
src/main/resources/
  application.properties

src/test/java/com/example/bootconfig/
  BootConfigurationDiscoveryTest.java
  NestedTestConfigurationAddsToApplicationTest.java
  ExtraTestBeans.java
  TopLevelImportedTestConfigurationTest.java
src/test/java/com/example/bootconfig/web/
  WelcomeWebMvcSliceTest.java
src/test/java/com/example/bootconfig/data/
  NoteRepositorySliceTest.java
src/test/java/com/example/outside/
  ExplicitApplicationFromOtherPackageTest.java
  NestedPlainConfigurationReplacesApplicationTest.java
  PlainSpringOnlyTest.java
~~~

*Note:* The runnable tree below contains **eight** JUnit test classes with **15 test methods**: 2 full Boot, 2 web slice, 2 JPA slice, 2 nested additive, 1 top-level imported, 2 explicit outside, 2 nested replacement, and 2 plain Spring (15 total). `ExtraTestBeans` is a `@TestConfiguration` helper, not a test class. Variations like property-override diagnostics in section 16 are illustrative only and excluded from this count.

**Running note:** Examples that *intentionally cause a missing-config failure* are shown only as **counter-example snippets**, **not placed as executable test classes** in the working project so `./gradlew test` does not fail by design. The complete Java classes below are designed to PASS as described; they **were not compiled or run during authoring**.

## 8. Gradle Build and JUnit Test Launcher

**`settings.gradle`:**

~~~groovy
rootProject.name = 'boot-config-diagnostics-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

The Spring Boot 3.5 BOM manages compatible versions for Spring Framework 6.2, JUnit, Mockito, and H2. `spring-boot-starter-web` provides Spring MVC/controller support; `spring-boot-starter-data-jpa` provides Spring Data JPA for a real `@DataJpaTest` slice. H2 is strictly a demo/test embedded DB, not a production database.

**Do not add `@SpringBootTest` to every unit test just to "discover" Spring Boot:** that slows tests down, drags in unrelated JPA/web/DB layers, and blurs dependency boundaries.

## 9. Application Class at the Proper Root Package

**`src/main/java/com/example/bootconfig/BootConfigApplication.java`:**

~~~java
package com.example.bootconfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootConfigApplication.class, args);
    }
}
~~~

This is the **sole primary configuration** in the runnable project. Because its package is `com.example.bootconfig`, default component scanning covers:

~~~text
com.example.bootconfig.core
com.example.bootconfig.web
com.example.bootconfig.data
~~~

And test packages `com.example.bootconfig.web` or `com.example.bootconfig.data` **auto-detect** `BootConfigApplication` via upward package search.

**Placing the main class in a subpackage that is too deep creates a different bug:** e.g., `com.example.bootconfig.app.BootConfigApplication` will not scan sibling packages `com.example.bootconfig.core` and `...web` as expected. Tests then **find the config** yet still miss services. Place the main app at a proper root package or configure `scanBasePackages`/`@EntityScan`/`@EnableJpaRepositories` intentionally when architecture requires it.

## 10. Real Service: Verifying Application Beans Load

**`src/main/java/com/example/bootconfig/core/WelcomeService.java`:**

~~~java
package com.example.bootconfig.core;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {

    private final String prefix;

    public WelcomeService(
            @Value("${app.welcome-prefix:Hello}") String prefix
    ) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String welcome(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }

        return prefix + ", " + name.strip() + "!";
    }

    public String prefix() {
        return prefix;
    }
}
~~~

Merely seeing `WelcomeService` in a test is **not always enough** to prove the right package/config was loaded; a mock can also provide that type. Therefore, the full Boot test also verifies `BootConfigApplication` in the context and the bound property value.

**`src/main/resources/application.properties`:**

~~~properties
app.welcome-prefix=Hello
spring.datasource.url=jdbc:h2:mem:boot_config_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.main.banner-mode=off
~~~

`@Value("${app.welcome-prefix:Hello}")` uses a placeholder in a **Spring-managed constructor**. When the service is instantiated via `new WelcomeService("Mini")` in plain Spring TestContext, the test supplies the prefix directly without Boot property loading.

## 11. MVC Controller for Boot and WebMvc Slice Tests

**`src/main/java/com/example/bootconfig/web/WelcomeController.java`:**

~~~java
package com.example.bootconfig.web;

import com.example.bootconfig.core.WelcomeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/welcome")
public class WelcomeController {

    private final WelcomeService service;

    public WelcomeController(WelcomeService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public String greeting(@PathVariable String name) {
        return service.welcome(name);
    }
}
~~~

In a **full `@SpringBootTest`**, both the controller and real `WelcomeService` are present. In **`@WebMvcTest(WelcomeController.class)`**, the controller enters the MVC slice while the service is usually **not** component-scanned as in full context; the test supplies `@MockitoBean WelcomeService`.

If you move the controller outside the application's root package, the full Boot context may fail to scan it; `@WebMvcTest(WelcomeController.class)` explicitly selects the controller, so it would not prove full-app auto-scanning on its own. Different test layers carry different responsibilities.

## 12. JPA Entity/Repository to Verify the DataJpaTest Slice

**`src/main/java/com/example/bootconfig/data/NoteEntry.java`:**

~~~java
package com.example.bootconfig.data;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "note_entries")
public class NoteEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected NoteEntry() {
    }

    public NoteEntry(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

**`src/main/java/com/example/bootconfig/data/NoteRepository.java`:**

~~~java
package com.example.bootconfig.data;

import org.springframework.data.jpa.repository.JpaRepository;

public interface NoteRepository
        extends JpaRepository<NoteEntry, Long> {
}
~~~

`@DataJpaTest` limits scanning by default to JPA entities and Spring Data JPA repositories, auto-configures an embedded database when appropriate, and rolls back test transactions after each method. Those traits make JPA tests faster than full Boot runs. Still, the slice requires a primary Boot application configuration or explicit configuration source to determine component-scan boundaries.

## 13. JUnit: Full Boot Test Auto-Detects the Right Main Application

**`src/test/java/com/example/bootconfig/BootConfigurationDiscoveryTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;
import com.example.bootconfig.web.WelcomeController;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class BootConfigurationDiscoveryTest {

    @Autowired ApplicationContext context;
    @Autowired WelcomeService welcomeService;
    @Autowired MockMvc mvc;

    @Test
    void discoversApplicationAndFullServiceByPackage() {
        assertThat(context.containsBean("bootConfigApplication"))
                .isTrue();

        assertThat(context.getBean(
                com.example.bootconfig.BootConfigApplication.class
        )).isNotNull();

        assertThat(welcomeService.prefix()).isEqualTo("Hello");
        assertThat(welcomeService.welcome(" Ada "))
                .isEqualTo("Hello, Ada!");
    }

    @Test
    void fullBootContextContainsMvcController() throws Exception {
        assertThat(
                context.getBeansOfType(WelcomeController.class)
        ).hasSize(1);

        mvc.perform(get("/api/welcome/Ada"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"));
    }
}
~~~

These are **two test methods**. Without specifying `classes=...` on `@SpringBootTest`, because the test package matches the application package, Spring Boot discovers `BootConfigApplication`. The tests verify **primary config identity**, the service bean, and the real endpoint.

Why is this test valuable? If another test in a similarly named package has its source replaced by a nested `@Configuration`, that test might still boot an `ApplicationContext` while lacking `BootConfigApplication`/`WelcomeService`. These assertions prevent "context starts" from being the only bar.

## 14. JUnit: `@WebMvcTest` Selects a Slice Yet Still Needs a Boot Source

**`src/test/java/com/example/bootconfig/web/WelcomeWebMvcSliceTest.java`:**

~~~java
package com.example.bootconfig.web;

import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(WelcomeController.class)
class WelcomeWebMvcSliceTest {

    @Autowired MockMvc mvc;
    @Autowired ApplicationContext context;

    @MockitoBean
    WelcomeService welcomeService;

    @Test
    void onlyWebLayerIsBootstrappedWithMockService()
            throws Exception {
        given(welcomeService.welcome("Ada"))
                .willReturn("Slice, Ada!");

        mvc.perform(get("/api/welcome/Ada"))
                .andExpect(status().isOk())
                .andExpect(content().string("Slice, Ada!"));

        verify(welcomeService).welcome("Ada");
    }

    @Test
    void mvcSliceDoesNotLoadDataRepository() {
        assertThat(
                context.getBeansOfType(
                    com.example.bootconfig.data.NoteRepository.class
                )
        ).isEmpty();
    }
}
~~~

These are **two tests** in the MVC slice. `@WebMvcTest(WelcomeController.class)` selects **which controller enters the slice**, not a replacement for `@SpringBootConfiguration`. Auto-detection still locates the app config via package `com.example.bootconfig.web` -> `com.example.bootconfig`.

`@MockitoBean` comes from Spring Framework 6.2, registering/replacing a mock bean in the test context. Do not confuse it with plain Mockito `@Mock`: a `@Mock` field on the test class **does not replace the Spring bean** injected into the `@Autowired` controller.

If the test resides outside the application package hierarchy, passing `controllers=WelcomeController.class` alone will not solve a missing root configuration.

## 15. JUnit: `@DataJpaTest` Follows the Same Main Config Lookup

**`src/test/java/com/example/bootconfig/data/NoteRepositorySliceTest.java`:**

~~~java
package com.example.bootconfig.data;

import com.example.bootconfig.web.WelcomeController;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class NoteRepositorySliceTest {

    @Autowired NoteRepository repository;
    @Autowired ApplicationContext context;

    @Test
    void repositoryPersistsEntityWithinJpaSlice() {
        NoteEntry saved =
                repository.saveAndFlush(new NoteEntry("Alpha"));

        assertThat(saved.getId()).isNotNull();

        NoteEntry loaded =
                repository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getTitle()).isEqualTo("Alpha");
    }

    @Test
    void jpaSliceDoesNotLoadMvcController() {
        assertThat(
                context.getBeansOfType(WelcomeController.class)
        ).isEmpty();
    }
}
~~~

These are **two tests**. The test class is in subpackage `com.example.bootconfig.data`, so it discovers `BootConfigApplication`. The tests verify JPA repository/entity behavior, confirm the controller stays out of the slice, and rely on automatic transaction rollback for test isolation.

**Do not place `@DataJpaTest` and `@SpringBootTest` on the same class.** Spring Boot test annotations declare distinct bootstrappers, and combining them improperly triggers bootstrapper conflicts. If you need the full context plus transaction rollback, use `@SpringBootTest` + `@Transactional` per your test contract rather than stacking two slices.

## 16. Nested `@TestConfiguration`: Supplements Rather Than Replaces the App

Spring Boot 3.5 docs distinguish:

- Nested **`@TestConfiguration`**: runs **alongside the primary Boot application** and adds extra beans.
- Nested **`@Configuration`**: is treated by Spring Boot tests as the **replacement primary configuration source** when no explicit classes are given.

**`src/test/java/com/example/bootconfig/NestedTestConfigurationAddsToApplicationTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NestedTestConfigurationAddsToApplicationTest {

    record TestMarker(String name) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ExtraBeans {

        @Bean
        TestMarker testMarker() {
            return new TestMarker("nested-test-config");
        }
    }

    @Autowired WelcomeService welcomeService;
    @Autowired TestMarker marker;
    @Autowired ApplicationContext context;

    @Test
    void nestedTestConfigurationAddsBean() {
        assertThat(marker.name())
                .isEqualTo("nested-test-config");
        assertThat(welcomeService.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }

    @Test
    void nestedTestConfigurationDoesNotHideBootApp() {
        assertThat(
                context.getBean(BootConfigApplication.class)
        ).isNotNull();
    }
}
~~~

**Two test methods** confirm the test-only marker coexists **with** the real application. `@TestConfiguration` is not a "mini `@SpringBootApplication`"; if a test sits outside the app package and cannot locate a primary source, adding a nested `@TestConfiguration` still **will not** fix the missing `@SpringBootConfiguration` error.

When you only need to change properties, `@SpringBootTest(properties="...")` or `@ActiveProfiles("test")` is simpler than writing a brand-new configuration bean. Reserve `@TestConfiguration` for specialized bean definitions.

## 17. Top-Level `@TestConfiguration` Imported Intentionally

Top-level test configs should not leak into every test via scanning. Spring Boot excludes top-level `@TestConfiguration` classes from normal component scanning; bring them into target contexts explicitly with `@Import`.

**`src/test/java/com/example/bootconfig/ExtraTestBeans.java`:**

~~~java
package com.example.bootconfig;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ExtraTestBeans {

    public record NamedMarker(String name) {
    }

    @Bean
    NamedMarker importedMarker() {
        return new NamedMarker("only-when-imported");
    }
}
~~~

**`src/test/java/com/example/bootconfig/TopLevelImportedTestConfigurationTest.java`:**

~~~java
package com.example.bootconfig;

import com.example.bootconfig.core.WelcomeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(ExtraTestBeans.class)
class TopLevelImportedTestConfigurationTest {

    @Autowired WelcomeService welcomeService;
    @Autowired ExtraTestBeans.NamedMarker marker;

    @Test
    void explicitlyImportedTestConfigDoesNotReplaceApp() {
        assertThat(marker.name())
                .isEqualTo("only-when-imported");
        assertThat(welcomeService.welcome("Mai"))
                .isEqualTo("Hello, Mai!");
    }
}
~~~

**One test method.** `@Import(ExtraTestBeans.class)` only adds configuration; it does not replace primary source detection. If no primary Boot app can be found, importing an auxiliary `@TestConfiguration` **does not fix** the root lookup issue. When tests apply multiple customizations, avoid ambiguous bean overrides; in Spring Framework 6.2, use `@MockitoBean(enforceOverride=true)` when you want to assert a real bean existed before overriding.

## 18. Nested `@Configuration` Can Replace the Main App — Tests Still Pass Yet Scope Is Wrong

The next example sits in a package **outside the application root** so other tests do not accidentally component-scan this nested config.

**`src/test/java/com/example/outside/NestedPlainConfigurationReplacesApplicationTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NestedPlainConfigurationReplacesApplicationTest {

    record LocalMarker(String origin) {
    }

    @Configuration(proxyBeanMethods = false)
    static class LocalConfig {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker("plain-nested-config");
        }
    }

    @Autowired ApplicationContext context;
    @Autowired LocalMarker marker;

    @Test
    void nestedPlainConfigurationBecomesPrimarySource() {
        assertThat(marker.origin())
                .isEqualTo("plain-nested-config");
        assertThat(context.getBeansOfType(
                BootConfigApplication.class
        )).isEmpty();
    }

    @Test
    void noMainComponentScanMeansNoWelcomeService() {
        assertThat(
                context.getBeansOfType(WelcomeService.class)
        ).isEmpty();
    }
}
~~~

**Two test methods** intentionally verify the difference. Even though the class uses `@SpringBootTest`, the nested `@Configuration` restricts the test source to `LocalConfig`: **there is no application component scan** and no `WelcomeService`. The test loads a context without throwing "Unable to find @SpringBootConfiguration", yet it **is not testing the real application**.

**Fix when you want the full app + extra beans:** change `@Configuration` to `@TestConfiguration` **and** place the test inside the app package for auto-detection, or use `@SpringBootTest(classes=BootConfigApplication.class)` with `@Import(LocalConfig.class)`. Never treat a nested plain `@Configuration` as an automatic unverified fix.

If your goal was only a tiny Spring context, use `@SpringJUnitConfig(LocalConfig.class)`—it is clearer and does not imply a full Boot app.

## 19. `@SpringBootTest(classes=...)` Fixes Tests Outside the Root Package

**`src/test/java/com/example/outside/ExplicitApplicationFromOtherPackageTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;
import com.example.bootconfig.data.NoteRepository;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = BootConfigApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.welcome-prefix=Explicit"
)
class ExplicitApplicationFromOtherPackageTest {

    @Autowired WelcomeService welcomeService;
    @Autowired ApplicationContext context;

    @Test
    void explicitClassesBypassPackageAutodetection() {
        assertThat(
                context.getBean(BootConfigApplication.class)
        ).isNotNull();

        assertThat(welcomeService.welcome("Hoa"))
                .isEqualTo("Explicit, Hoa!");
    }

    @Test
    void explicitFullAppStillScansItsOwnRepositories() {
        assertThat(
                context.getBeansOfType(NoteRepository.class)
        ).hasSize(1);
    }
}
~~~

**Two test methods** live in `com.example.outside`, a sibling branch of `com.example.bootconfig`. Without `classes=...`, Boot tests **will not walk sideways** into `com.example.bootconfig`. With an explicit source, config selection no longer depends on the test's package; scanning still **follows the primary config class and its metadata**.

Therefore, specify the exact FQCN and verify a sentinel property to prove the intended application booted. If the source pointed to a different app in a monorepo, the context might still start and shallow assertions would give a "false PASS."

## 20. `@SpringJUnitConfig`: When Boot Auto-Configuration Is Not Needed

**`src/test/java/com/example/outside/PlainSpringOnlyTest.java`:**

~~~java
package com.example.outside;

import com.example.bootconfig.BootConfigApplication;
import com.example.bootconfig.core.WelcomeService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(PlainSpringOnlyTest.MiniConfig.class)
class PlainSpringOnlyTest {

    @Configuration(proxyBeanMethods = false)
    static class MiniConfig {

        @Bean
        WelcomeService welcomeService() {
            return new WelcomeService("Plain");
        }
    }

    @Autowired WelcomeService welcomeService;
    @Autowired ApplicationContext context;

    @Test
    void directConfigurationLoadsSmallSpringContext() {
        assertThat(welcomeService.welcome("Binh"))
                .isEqualTo("Plain, Binh!");
    }

    @Test
    void smallContextDoesNotBootstrapBootApplication() {
        assertThat(context.getBeansOfType(
                BootConfigApplication.class
        )).isEmpty();
    }
}
~~~

**Two test methods** demonstrate a **valid Spring context** without `@SpringBootApplication`. `@SpringJUnitConfig` combines `SpringExtension` and `@ContextConfiguration`, creating a context from `MiniConfig`. Do not expect Spring Boot property files, auto-configuration, web servers, or JPA to load because Boot's `SpringApplication` does not run.

A common use case is testing a few `@Bean` definitions, validators, or client adapters that do not rely on Boot features; `@SpringJUnitConfig(MiniConfig.class)` is faster and clearer than `@SpringBootTest`.

### When to Choose `@ContextConfiguration` Directly?

Two equivalent ways to express Spring TestContext intent:

~~~java
@SpringJUnitConfig(MyConfig.class)
class SmallTest {
}
~~~

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyConfig.class)
class SmallTest {
}
~~~

These are **snippets**; `MyConfig` is an illustrative type outside the runnable demo. When you need Boot auto-configuration, ConfigData, web server, Boot test features, and customizers, use `@SpringBootTest(classes=...)`; do not swap annotation names expecting identical runtime behavior.

## 21. Test Method Counts and Per-Class Responsibilities

In the project with all files from sections 7–20:

| Class | Tests | What Is Tested? |
| --- | ---: | --- |
| `BootConfigurationDiscoveryTest` | 2 | Full Boot auto-detect, real controller/beans |
| `WelcomeWebMvcSliceTest` | 2 | MVC slice + `@MockitoBean`; JPA repo excluded |
| `NoteRepositorySliceTest` | 2 | JPA slice + H2; MVC controller excluded |
| `NestedTestConfigurationAddsToApplicationTest` | 2 | Nested `@TestConfiguration` adds bean while keeping app |
| `TopLevelImportedTestConfigurationTest` | 1 | Top-level `@TestConfiguration` via `@Import` |
| `NestedPlainConfigurationReplacesApplicationTest` | 2 | Nested `@Configuration` replaces app config |
| `ExplicitApplicationFromOtherPackageTest` | 2 | Outside package with explicit app source |
| `PlainSpringOnlyTest` | 2 | Plain Spring TestContext without Boot auto-config |
| **Total** | **15** | Key source detection/loading branches |

**No** `@SpringBootTest` class intentionally missing configuration is included in the runnable `test` task. Section 22 provides a **counter-example** to reproduce the error manually, which belongs in an experimental branch or separate classpath rather than committing an intentionally failing test to the default build.

These tests do not claim compatibility across all Spring Boot/JPA major versions; they target Java 17 / Boot 3.5.16. Use the matching dependencies/BOM/runtime and run them directly to obtain CI evidence.

## 22. Counter-Example Causing Missing `@SpringBootConfiguration`

Suppose the application resides in `com.example.bootconfig`, while a test is placed in package **`com.example.diagnostics`**:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BrokenBootLookupTest {

    @Test
    void contextLoads() {
    }
}
~~~

This is an **INTENTIONALLY BROKEN file**, excluded from the runnable demo. Because the test package walks up `com.example.diagnostics` -> `com.example` -> `com`, it never walks down into `com.example.bootconfig` and fails to find `@SpringBootConfiguration`.

Fix using either approach:

**Approach A — place the test under the app package:**

~~~java
package com.example.bootconfig.diagnostics;

@SpringBootTest
class CorrectlyLocatedTest {
    @Test
    void contextLoads() {
    }
}
~~~

**Approach B — explicit primary config when the test lives elsewhere:**

~~~java
package com.example.diagnostics;

@SpringBootTest(classes = BootConfigApplication.class)
class CorrectlyTargetedTest {
    @Test
    void contextLoads() {
    }
}
~~~

Both are **snippets** requiring JUnit, Boot test, and application imports; do not drop them straight into the project without fixing packaging and compilation. Approach A works naturally inside a single app module; Approach B is especially helpful in shared tests, integration source sets, or monorepos.

**Do not "fix" this by dropping an empty `@SpringBootApplication` inside `src/test/java/com/example/diagnostics` without considering component scanning and auto-configuration.** Tests may turn green while actually loading a dummy test app and skipping the real application's domain beans.

## 23. Error: "Configuration Found, Yet Bean Still Missing"

Even after specifying `@SpringBootTest(classes=...)`, a test can still fail with:

~~~text
NoSuchBeanDefinitionException:
  No qualifying bean of type '...WelcomeService'
~~~

This is a **later-stage failure** than "Unable to find @SpringBootConfiguration". Common causes:

1. Main app class sits in a **package nested too deeply**, so component scanning misses sibling packages.
2. `@ComponentScan` has wrong `basePackages` or include/exclude filters.
3. The service lacks `@Component`/`@Service` or `@Bean` registration.
4. `@Profile`/`@ConditionalOnProperty`/`@ConditionalOnClass` prevented bean creation.
5. Controller/service lives in another module whose dependency is missing from the test runtime classpath.
6. `@WebMvcTest` slice contains MVC beans only and omits regular services.
7. Test uses a nested `@Configuration` as primary source, omitting the app's component scan.
8. Repository/entity discovery uses different base packages than component scan.
9. The bean was replaced by a mock or has multiple candidates requiring a qualifier.
10. The app uses parent/child contexts and the test injects from the wrong level.

**Diagnostic order:** first confirm `BootConfigApplication.class` was loaded as the source; next inspect bean definitions, conditions, profiles, scan boundaries, and package paths. **Do not** toggle randomly between `@SpringBootTest` and `@ContextConfiguration` without reading the root exception.

## 24. `@TestConfiguration` vs `@Configuration`: Easy Cause of False Passes

Summary table:

| Placement / Annotation | When Boot Test Resolves Source | Is the Real App Loaded? |
| --- | --- | --- |
| No nested config, test under app root | Searches upwards for `@SpringBootApplication` | **Yes**, if found |
| Nested static `@TestConfiguration` | Added to primary app config | **Yes**, if primary is found |
| Nested static `@Configuration` | Treated as default primary source for the test | **Not necessarily**; usually replaces primary |
| Top-level `@TestConfiguration` not imported | Not scanned normally by Boot | Does not fix missing primary |
| Top-level `@TestConfiguration` + `@Import` | Adds beans to bootstrapped context | Yes, if primary app source is right |
| `@SpringBootTest(classes=App.class)` | Uses `App` explicitly | Yes, per `App` |
| `@SpringJUnitConfig(Mini.class)` | Plain Spring TestContext from `Mini` | No Boot app unless declared |
| `@SpringBootTest(classes=OtherApp.class)` | Loads `OtherApp` | May PASS yet test the **wrong app** |

**Never check only a dummy marker bean** and declare the whole application loaded. Tests must verify contract essentials: controllers, real services, repositories, profile properties, and configuration class identity.

When tests combine `@Import`, nested test configs, `@MockitoBean`, or custom context initializers, cache keys and context customizations change. The same test class can spin up distinct contexts depending on properties/profiles, so do not judge config correctness solely by counting startup logs.

## 25. `@WebMvcTest` and `@DataJpaTest` Also Need the Right Root Config

A common mistake:

~~~java
@WebMvcTest(WelcomeController.class)
class MyMvcTest {
}
~~~

If the test sits outside the application package, the Spring Boot test bootstrapper can still fail to find a primary config. Here `WelcomeController.class` specifies the **target of the MVC slice**, not a replacement for `@SpringBootApplication`.

Likewise:

~~~java
@DataJpaTest
class MyRepositoryTest {
}
~~~

requires a Boot root config or explicit source plus entity/repository scanning and an embedded/test datasource. With `@DataJpaTest`, do not jump to blaming the H2 URL when the error is missing Boot config; locating the Boot source precedes database setup.

**When slice-testing a library module that has no main app class**, you can:

- Place the test in an application module/proper package depending on the domain module under test.
- Provide an **appropriate test-only `@SpringBootConfiguration`** in the test package so the slice has a minimal primary root with deliberate bean/auto-config settings, avoiding scanning the whole monorepo.
- Use `@ContextConfiguration(classes=...)` or explicit Spring Test mechanisms to supply the slice source, while asserting that the slice still restricts beans as intended.
- If only testing plain beans, switch to `@SpringJUnitConfig` instead of forcing a Boot slice.

**Do not** stack two slice annotations like `@DataJpaTest` + `@WebMvcTest`: they declare conflicting test bootstrappers and are not a valid API for "combining parts." If you need the full context, use `@SpringBootTest` or one slice plus the documented `@AutoConfigure...` annotations.

## 26. Explicit `@ComponentScan` on the Main App Can Over-Widen Slices

Spring Boot's `@SpringBootApplication` registers component-scan exclude filters leveraged by Boot test slices. If the main application adds:

~~~java
@SpringBootApplication
@ComponentScan(basePackages = {
    "com.example.bootconfig",
    "com.example.shared"
})
public class BootConfigApplication {
}
~~~

This is a **counter-example**; do not overwrite the runnable application file with it. An explicit `@ComponentScan` can override the filtering required for test slicing; `@DataJpaTest` suddenly pulls in MVC, security, or business beans it was supposed to exclude, causing context failures or bloated tests.

Prefer:

1. Placing the application class in an appropriate root package so default component scanning works.
2. Keeping extra domain configuration in separate `@Configuration` classes and `@Import`ing them where needed.
3. If scanning outside the root is truly required, configuring filters/`TypeExcludeFilter` per Boot testing docs.
4. For slices, checking bean presence/absence via `ApplicationContext#getBeansOfType` to detect scan leaks.
5. Avoiding `@SpringBootTest(classes=...)` as an excuse to normalize overly broad scans.

A "valid" Boot application configuration with broken scan boundaries can still break integration tests. This illustrates why you must separate **discovery**, **component scanning**, **auto-configuration conditions**, and **bean instantiation**.

## 27. Multi-Module Builds, `integrationTest` Source Sets, and Classpath

In a monorepo:

~~~text
settings.gradle
app/
  src/main/java/com/example/bootconfig/BootConfigApplication.java
core/
  src/main/java/com/example/core/DomainService.java
  src/test/java/com/example/core/DomainServiceTest.java
integration-tests/
  src/test/java/com/example/it/WorkflowTest.java
~~~

When `WorkflowTest` lives in `integration-tests`, merely adding:

~~~java
@SpringBootTest(classes = BootConfigApplication.class)
~~~

is **not enough** if `BootConfigApplication.class` **is absent from the test compile/runtime classpath**. Declare the module dependency, e.g., in `integration-tests/build.gradle`:

~~~groovy
dependencies {
    testImplementation project(':app')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

This is a snippet, not a complete build; the Gradle project must include `include ':app', ':integration-tests'` and matching plugins. Do not assume the app JAR enters the test task automatically just because both modules sit in the same repository.

If using a custom `sourceSets.integrationTest`:

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

This snippet requires configuring the source set and dependency configurations for your Gradle version. Missing `testClassesDirs`/`classpath` leads to `NO-SOURCE`, `ClassNotFoundException`, or undiscovered tests even when `@SpringBootConfiguration` is completely valid in source.

**Rule:** The Java package hierarchy decides **which class is eligible for auto-detection**, while the runtime classpath decides **whether the JVM can actually load that class**. Both must be right.

## 28. `@ActiveProfiles` and `@TestPropertySource` Do Not Fix Source Lookup

A test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "app.welcome-prefix=Test"
})
class SomeTest {
}
~~~

This is a snippet needing imports, not a runnable file. `@ActiveProfiles` picks profiles and `@TestPropertySource` adds properties to the context; they **do not relocate the test's package** or point to `@SpringBootApplication`.

Once the bootstrap source is right, profiles and properties affect beans via `@Profile`, `@ConditionalOnProperty`, database URLs, and security. Yet if the root exception is a missing `@SpringBootConfiguration`, tweaking `spring.profiles.active` or `logging.level` will not solve it.

Distinguish:

- **Source selection:** `@SpringBootTest(classes=...)`, package auto-detection, `@ContextConfiguration`.
- **Environment selection:** `@ActiveProfiles`, `@TestPropertySource`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource`.
- **Bean selection:** component scanning, `@Import`, conditional annotations, qualifiers, `@MockitoBean`.
- **Context lifetime:** context cache, `@DirtiesContext`.
- **Test execution:** JUnit/Gradle source sets and test tasks.

Each category acts on a different layer. Do not alter global system properties trying to make Boot see an application class.

## 29. Debug Logs and Gathering Evidence

Start with a targeted test:

~~~bash
./gradlew test \
  --tests "com.example.bootconfig.BootConfigurationDiscoveryTest" \
  --stacktrace --info
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest" --stacktrace --info
~~~

Before running, verify the project JDK/Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests "*BootConfigurationDiscoveryTest" --rerun-tasks
~~~

**Read the first root cause** of `IllegalStateException` in the stack trace, not only the outer exception wrapped by JUnit/Gradle. If the root cause is:

~~~text
Unable to find a @SpringBootConfiguration...
~~~

check packages/sources. If the root cause is already:

~~~text
BeanCreationException
NoSuchBeanDefinitionException
Failed to configure a DataSource
Failed to bind properties
Port already in use
Unable to start web server
~~~

then Boot likely **already located the source**, and the failure moved to a later stage.

You can enable Spring TestContext cache diagnostics in `src/test/resources/application.properties` strictly for debugging:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
~~~

This is an **optional debug file**, excluded from the runnable demo, and does not modify `src/main/resources/application.properties`. `debug=true` prints the condition evaluation report at Boot app startup; that report helps with **auto-configuration conditions** after source selection, **not** proving Boot will locate the right primary config from a wrong package.

Do not leave `DEBUG` on long-term and wade through thousands of log lines instead of checking packages and classpaths directly.

## 30. Analyzing Errors That Look Similar but Differ Fundamentally

### A. `@SpringBootConfiguration` Not Found

~~~text
IllegalStateException: Unable to find a @SpringBootConfiguration
~~~

**Stage:** Primary config detection. **Fix:** proper package, explicit `classes=...`, ensure app class is on classpath.

### B. Wrong Main App Selected While Context Still Loads

~~~text
context.getBean(AppA.class)    -> absent
context.getBean(AppB.class)    -> present
~~~

**Stage:** Wrong source selection. **Fix:** pin `@SpringBootTest(classes=AppA.class)` and assert identity/expected business beans. Never rely solely on `contextLoads`.

### C. `@SpringBootApplication` Found, Yet Bean Is Missing

~~~text
NoSuchBeanDefinitionException: WelcomeService
~~~

**Stage:** Component scan/conditions/bean registration. **Fix:** scan boundaries, annotations, imports, profiles, and mock setup.

### D. Two Beans of the Same Type

~~~text
NoUniqueBeanDefinitionException: expected single matching bean
~~~

**Stage:** Bean candidate selection. **Fix:** `@Qualifier`/`@Primary` matching the contract; do not add arbitrary annotations to mask a wrong context.

### E. JPA Slice Cannot Find Entity

~~~text
Not a managed type: class com.example...NoteEntry
~~~

**Stage:** Entity/repository scanning; root package/config may exclude the entity. **Fix:** proper `@Entity`, `basePackages`, entity scan, and `Test` task classpath. Not every "Not a managed type" error means missing `@SpringBootConfiguration`.

### F. Duplicate Boot Configuration

~~~text
Multiple @SpringBootConfiguration candidates
~~~

**Stage:** Auto-detection ambiguity. **Fix:** one clear primary source per module/package or `classes=...`; keep test-only app configs in their own namespace rather than scattering multiple Boot application classes along the search path.

### G. Missing JUnit Class or Tests Not Running

~~~text
No tests found / ClassNotFoundException / NoClassDefFoundError
~~~

**Stage:** Compile/runtime/test task classpath or discovery. **Fix:** Gradle sources, `testImplementation`/`testRuntimeOnly`, JUnit launcher, and `useJUnitPlatform()`. Fix JVM class loading before touching Spring annotations.

### H. Invalid Combined Bootstrappers

~~~text
Configuration error: multiple declarations of @BootstrapWith
~~~

**Stage:** Incompatible combination of two test slice annotations or bootstrappers. **Fix:** choose one primary test annotation plus required `@AutoConfigure...` annotations; never stack `@WebMvcTest` + `@DataJpaTest` or multiple `@*Test` annotations.

## 31. When Multiple `@SpringBootApplication` Classes Exist

In a multi-module repository, you might have:

~~~text
com.example.orders.OrdersApplication
com.example.payments.PaymentsApplication
com.example.shared.SharedTest
~~~

A test in `com.example.shared` will not guess between two sibling apps from class names `OrdersApplication`/`PaymentsApplication`. Some layouts fail to find a config; others collide with multiple candidates. Never create an extra app class at `com.example` just to stop both tests from failing—it will scan **both orders and payments**, causing duplicate bean and DB configuration conflicts.

How to choose:

- Orders integration test -> `@SpringBootTest(classes=OrdersApplication.class)`.
- Payments integration test -> `@SpringBootTest(classes=PaymentsApplication.class)`.
- Domain-only tests -> `@SpringJUnitConfig(DomainConfig.class)` or unit tests.
- App tests belong best under the real app's root package.
- If using a shared integration module, **test dependencies** must pull in the right app artifact.
- Keep app configs separated by Gradle modules, package roots, profiles, and test reports.

**Do not treat `@SpringBootApplication` names as automatic test selectors**: Boot does not choose a class because its name resembles the test or because `main()` was run previously.

## 32. Test-Only Boot Configurations Can Help, Yet Must State Their Purpose

In a library or starter without an executable main app, `@WebMvcTest` or `@DataJpaTest` sometimes needs a test root:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
class TestOnlyBootConfiguration {
}
~~~

This is a **snippet** needing imports, outside the runnable project. `@SpringBootConfiguration` lets Boot recognize a root configuration; `@EnableAutoConfiguration` activates conditional auto-configurations. However, it **does not scan** all `@Service`/`@Entity` classes like `@SpringBootApplication`. You may need `@Import`, `@EntityScan`, or `@EnableJpaRepositories` matching the test.

This fits standalone library modules **when no real application source exists**. Still:

1. Never place an extra root `@SpringBootConfiguration` inside an application package that already has `@SpringBootApplication`.
2. Never let a test root scan an overly broad package.
3. Ensure real integration tests still target the real app source instead of letting a dummy config take over.
4. Test bean boundaries and source identity.
5. If a test only needs a few beans, plain Spring TestContext is usually simpler.

**A dummy test root can silence a lookup exception while defeating the goal of testing the real app.** Always document an intentional test root during code review.

## 33. Context Cache, Configuration Classes, and Test Speed

Spring TestContext caches `ApplicationContext` instances with equivalent configurations to avoid reloading. `@SpringBootTest(classes=App.class)`, `@ActiveProfiles`, test properties, `@Import`, `@MockitoBean` customizers, and nested configurations all contribute to the cache key.

When tests load different contexts:

~~~text
Test A: BootConfigApplication + property Hello
Test B: BootConfigApplication + property Explicit
Test C: BootConfigApplication + ExtraTestBeans
Test D: LocalConfig only
~~~

the resulting contexts **can differ**; do not expect the same singleton instances everywhere. Yet do not scatter `@DirtiesContext` everywhere to "guarantee freshness": it inflates startup cost and can break parallel tests sharing a context.

Diagnostic goals:

- **Correctness:** each test gets the right config classes, properties, and bean overrides.
- **Isolation:** tests do not mutate global/DB state that breaks other tests.
- **Performance:** reuse contexts when configurations genuinely match.
- **Observability:** if context bootstrap fails, pinpoint the root source before blaming the cache.

`@MockitoBean` in Spring Framework 6.2 resets by default per test lifecycle; this **does not** fix a missing primary source, and when the target bean does not exist, default behavior can create a mock causing a false PASS. Consider `@MockitoBean(enforceOverride=true)` to ensure the real bean existed before overriding.

## 34. Ordered Diagnostic Checklist

- [ ] Identified whether the **root exception** is missing `@SpringBootConfiguration` vs a bean/DB/port failure?
- [ ] Confirmed the test uses the right `@SpringBootTest`/`@WebMvcTest`/`@DataJpaTest` annotation?
- [ ] Confirmed the test's `package` declaration sits beneath the main app's package?
- [ ] Checked the FQCN and annotations on the real main class?
- [ ] Checked whether main uses `@SpringBootApplication` or only `@Configuration`?
- [ ] Verified the primary Boot class is on the task's **test runtime classpath**?
- [ ] For multi-module builds, verified `testImplementation project(':app')`?
- [ ] For custom `integrationTest` source sets, verified `classesDirs`/`classpath`?
- [ ] Checked if a nested static `@Configuration` unintentionally replaced primary?
- [ ] Verified nested `@TestConfiguration` is understood as additive, not replacing the Boot app?
- [ ] Confirmed top-level `@TestConfiguration` is `@Import`ed where needed?
- [ ] Checked for two/multiple Boot configuration classes causing ambiguity?
- [ ] Confirmed `@SpringBootTest(classes=...)` targets the right application when outside its package?
- [ ] Added assertions like `ApplicationContext.getBean(RealApplication.class)`?
- [ ] Asserted real services/controllers/repositories rather than only `contextLoads`?
- [ ] Verified `@WebMvcTest(Controller.class)` explicitly supplies mock/bean dependencies?
- [ ] Verified `@DataJpaTest` has matching entity/repository/H2/test DB setup?
- [ ] Verified test slices do **not** scan every component due to explicit `@ComponentScan`?
- [ ] Avoided stacking multiple slice annotations or bootstrappers?
- [ ] Reserved `@ContextConfiguration`/`@SpringJUnitConfig` for cases needing no Boot extras?
- [ ] Separated `@ActiveProfiles` and test properties from source selection?
- [ ] Verified any `@SpringBootConfiguration`-only test root has needed imports/auto-config?
- [ ] Confirmed test class source sets and resource paths match the Gradle task?
- [ ] Verified `./gradlew test --tests ... --rerun-tasks` discovers the expected test count?
- [ ] Ensured CI does not rely solely on `BUILD SUCCESSFUL` when tests are `SKIPPED`/`NO-SOURCE`?
- [ ] Checked JUnit XML/Gradle reports for the expected count?
- [ ] Enabled `DEBUG` logs/condition reports purposefully without obscuring the root exception?
- [ ] Avoided widening global packages/component scans to hide a misplaced test?
- [ ] Avoided using `@DirtiesContext` as a "fix" for source detection?
- [ ] Avoided claiming code compiled/ran if it was only reviewed?

## 35. Run Commands and Sample Suite Expectations

With JDK 17+, Gradle Wrapper, and all Gradle/Java/resource files matching the sections above:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest"
./gradlew test --tests "com.example.bootconfig.web.WelcomeWebMvcSliceTest"
./gradlew test --tests "com.example.bootconfig.data.NoteRepositorySliceTest"
./gradlew test --tests "com.example.outside.ExplicitApplicationFromOtherPackageTest"
./gradlew test --tests "com.example.outside.PlainSpringOnlyTest"
./gradlew test --rerun-tasks --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.bootconfig.BootConfigurationDiscoveryTest"
.\gradlew.bat test --tests "com.example.bootconfig.web.WelcomeWebMvcSliceTest"
.\gradlew.bat test --tests "com.example.bootconfig.data.NoteRepositorySliceTest"
.\gradlew.bat test --tests "com.example.outside.ExplicitApplicationFromOtherPackageTest"
.\gradlew.bat test --tests "com.example.outside.PlainSpringOnlyTest"
.\gradlew.bat test --rerun-tasks --stacktrace
~~~

**Expected behavior from source:**

| Group | Tests | Expected Outcome |
| --- | ---: | --- |
| Full Boot auto-detect | 2 | Main class bean present; prefix `Hello`; MockMvc `"Hello, Ada!"` |
| Web MVC slice | 2 | Mock service returns `"Slice, Ada!"`; JPA repository absent |
| Data JPA slice | 2 | `NoteEntry` save/find succeeds; MVC controller absent |
| Nested additive `TestConfiguration` | 2 | Local marker present; `WelcomeService` and app main present |
| Top-level imported `TestConfiguration` | 1 | Imported marker present; app service works |
| Nested plain `Configuration` | 2 | `LocalMarker` present; Boot app/service **absent** |
| Explicit full App from outside package | 2 | App bean present; prefix `Explicit`; `NoteRepository` present |
| Plain Spring TestContext | 2 | Prefix `Plain`; Boot app not loaded |
| **Total** | **15** | Cleanly distinguishes source detection/loading paths |

Sample business string outputs:

~~~text
Boot full:    Hello, Ada!
MVC slice:    Slice, Ada!
Explicit app: Explicit, Hoa!
Plain Spring: Plain, Binh!
Jpa slice:    NoteEntry title = Alpha
~~~

These are **expectations derived from source and config**, not observed stdout from Gradle/JUnit/H2. The project **was not compiled or executed while writing this lesson**, and Spring startup logs will contain additional lines. To verify, run `./gradlew clean test` and inspect `build/reports/tests/test/index.html` or `build/test-results/test/TEST-*.xml`; confirm all **15 tests executed** rather than relying on the build exit code alone.

To intentionally reproduce the missing-configuration error, add `BrokenBootLookupTest` **in a separate experimental branch**, run that class alone, and **omit it from the default suite**. Do not leave an intentionally failing test in main CI just for demonstration.

## 36. Conclusion and Official References

**Failing to find `@SpringBootConfiguration` is a problem of choosing the starting point for the test context.** The right diagnostic path:

1. Confirm the test package is under the application package and the app class carries the right Boot annotation.
2. Confirm the app class is actually on the test runtime classpath of the Gradle task/module.
3. When loading the app from another package, use `@SpringBootTest(classes=RealApp.class)`.
4. When you only need minimal Spring beans, use `@SpringJUnitConfig(MiniConfig.class)`.
5. Use nested `@TestConfiguration` to **add** beans, without forgetting nested `@Configuration` **replaces** the app.
6. Do not treat `@WebMvcTest(Controller.class)` as an explicit Boot primary source; slices still need a valid root config.
7. Once the context loads yet a bean is missing, inspect component scans, auto-config conditions, profiles, and imports.
8. Tests should assert real application identity and core beans; `contextLoads()` alone does not guarantee the right application loaded.

### Official Documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications / Detecting Test Configuration](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot 3.5 — @SpringBootConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringBootConfiguration.html)
- [Spring Boot 3.5 — @TestConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/TestConfiguration.html)
- [Spring Boot 3.5 — @WebMvcTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Boot 3.5 — @DataJpaTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Spring Boot 3.5 — How-to: Structure @Configuration Classes for Slice Tests](https://docs.spring.io/spring-boot/3.5/how-to/testing.html)
- [Spring Framework 6.2 — @SpringJUnitConfig](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/junit/jupiter/SpringJUnitConfig.html)
- [Spring Framework 6.2 — @ContextConfiguration](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management.html)
- [Spring Framework 6.2 — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/)