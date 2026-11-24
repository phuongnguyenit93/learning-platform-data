# @OverrideAutoConfiguration and @ImportAutoConfiguration in Spring Boot Test Slices

## 1. Lesson Objectives

A running Spring Boot application needs many auto-configuration mechanisms: MVC, Jackson, datasource, transactions, security, messaging, metrics… Yet a controller test might only need **MVC + MockMvc + controller + mock service**. Loading all auto-configurations and every application bean can make tests slow or cause failures merely because a database or broker is unavailable, even though the goal is checking HTTP request mapping.

Spring Boot solves this with **test slices**. Two annotations sitting behind this design are:

- **`@OverrideAutoConfiguration(enabled = false)`**: overrides the state of `@EnableAutoConfiguration`, typically to **turn off loading the entire default set of auto-configurations**.
- **`@ImportAutoConfiguration(...)`**: **selectively imports** the auto-configuration classes needed by a slice or test, while still applying Spring Boot's ordering and conditional auto-configuration rules.

These two annotations commonly appear **indirectly** through `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@WebFluxTest`… They complement **component-scan filtering** so a slice gets the necessary framework beans without turning into a full application.

By the end of this lesson, you should be able to:

1. Explain why `@WebMvcTest` still provides `MockMvc` and MVC infrastructure while not auto-loading regular services/repositories.
2. Distinguish **disabling broad auto-configuration**, **importing selected auto-configurations**, **component-scan filtering**, and **importing user configuration**.
3. Use `@ImportAutoConfiguration` with `value`/`classes` and `exclude`, plus understand `META-INF/spring/...imports` metadata.
4. Know when to use `@Import`, `@MockitoBean`, `@EnableConfigurationProperties`, or a different test scope instead of misusing `@ImportAutoConfiguration`.
5. Interpret missing-bean errors, dependencies pulled into slices, non-matching conditional auto-configurations, and differences from `@SpringBootTest`.
6. Build a runnable **Java 17+ / Spring Boot 3.5.16 / Maven / JUnit Jupiter** example where tests prove an auto-configuration loads only when permitted.

In this lesson, "auto-configuration" refers to Spring Boot auto-configuration classes or extensions following Spring Boot's standard (typically annotated with `@AutoConfiguration` or used as auto-configuration), **not** every ordinary `@Configuration`.

## 2. Four Distinct Mechanisms You Must Understand

### 2.1. `@EnableAutoConfiguration`: Normal Application Mode

`@SpringBootApplication` includes `@EnableAutoConfiguration`. On startup, Spring Boot discovers auto-configuration candidates on the classpath, evaluates conditions (present classes, existing beans, properties, web application type…), and configures missing beans. Modern Boot candidates are declared via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Such a file can list the fully qualified names of many auto-configuration classes. A **candidate being discovered** does not guarantee its internal `@Bean` methods execute: `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and other conditions can cause a class or bean to back off.

### 2.2. `@OverrideAutoConfiguration(enabled = false)`: Turning Off Broad Auto-Configuration

The annotation lives at:

```java
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
```

Syntax:

```java
@OverrideAutoConfiguration(enabled = false)
```

In Spring Boot 3.5, this annotation overrides whether `@EnableAutoConfiguration` is active. When `enabled=false`, Spring Boot **does not load broad auto-configurations through the default discovery path** of `@EnableAutoConfiguration` in the test context.

However, it does **not** mean:

- "No Spring ApplicationContext exists."
- "No beans defined via `@Component`, `@Bean`, or `@Import` exist."
- "No auto-configuration can ever be imported."
- "No MVC/JSON/JPA infrastructure remains."
- "Beans are forbidden even if imported directly."

Spring-managed classes can still be created through configuration, component scanning, test imports, and other sources. Specifically, `@ImportAutoConfiguration` **can still import a selected set of auto-configurations**.

The `enabled` attribute is **required** in this API, so write `enabled = false` or `enabled = true`; do not assume the annotation has a default value that lets you leave it blank.

### 2.3. `@ImportAutoConfiguration`: Importing Only Specified Auto-Configurations

Import:

```java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
```

Example:

```java
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
```

`@ImportAutoConfiguration` applies auto-configuration ordering rules, while **limiting imports to the specified classes** (or reading from the `.imports` file tied to the annotation). It does not re-enable `@EnableAutoConfiguration` to "load everything" again.

You can also write:

```java
@ImportAutoConfiguration(
        classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
        exclude = ExtraAutoConfiguration.class)
```

`value` and `classes` are aliases; pick **one of them**. `exclude` specifies auto-configurations not to import. Conditions inside each auto-configuration are still evaluated: listing a class means **it is considered**, not promised to produce every bean inside it.

### 2.4. TypeExcludeFilters: Slices Also Restrict Component Scanning

In Boot 3.5, `@WebMvcTest` carries these typical meta-annotations:

```java
@OverrideAutoConfiguration(enabled = false)
@TypeExcludeFilters(WebMvcTypeExcludeFilter.class)
@AutoConfigureCache
@AutoConfigureWebMvc
@AutoConfigureMockMvc
@ImportAutoConfiguration
```

This is an **excerpt describing `@WebMvcTest`'s meta-annotations**, not a standalone Java class. Each part has a distinct job:

- `@OverrideAutoConfiguration` prevents importing **all** ordinary broad auto-configuration candidates.
- `@TypeExcludeFilters` restricts scanned components according to web MVC slice rules.
- The `@AutoConfigure…` annotations register test configurations for MVC, MockMvc, cache…
- `@ImportAutoConfiguration` and its accompanying metadata file define the **selected list of auto-configurations**.

Therefore, **simply adding `@OverrideAutoConfiguration(false)` to a test does not create a "complete slice"**: it does not automatically provide type-exclude filters or test auto-configurations like `@WebMvcTest`. If you build a custom test slice, you must design both the scan boundary and the required infrastructure beans.

## 3. Comparing Annotations to Avoid Confusion

| Annotation / mechanism | Main function | When to use |
| --- | --- | --- |
| `@SpringBootTest` | Builds test context from application, normally including broad auto-configuration | Testing multi-layer wiring/integration |
| `@WebMvcTest` / `@DataJpaTest` | Test slice integrating bean filtering and matching auto-configs | Testing a meaningful single layer |
| `@OverrideAutoConfiguration(enabled=false)` | Turns off `@EnableAutoConfiguration`'s broad auto-config path | Writing custom slices/test contexts when you explicitly want it disabled |
| `@ImportAutoConfiguration` | Selectively imports auto-configuration classes following ordering/conditions | Adding auto-config to a slice |
| `@Import` | Imports ordinary Spring configurations or test-needed beans/classes | Importing custom `@TestConfiguration`, `@Configuration`, specific components |
| `@MockitoBean` | Replaces/registers a Mockito mock bean in the test Spring context | Supplying a collaborator intentionally excluded by the slice |
| `@EnableConfigurationProperties` | Registers processing for one or more `@ConfigurationProperties` types | Slice needs property binding for an unscanned config class |
| Slice's `excludeAutoConfiguration` | Excludes specific auto-configurations from the slice set | Reducing unrelated infrastructure or blocking a specific auto-config |
| `@SpringBootTest(properties=...)` | Adds/overrides test property sources | Adjusting config conditions/behavior |
| `@DirtiesContext` | Marks cached context dirty, forcing rebuild | Context state was mutated by the test; not a fix for missing beans |

Note: `@ImportAutoConfiguration` is **not** the right way to import an ordinary `@Service` just because slice scanning excluded it. For an MVC controller's service collaborator, normally use `@MockitoBean`. If the goal is testing the real service, switch to `@Import(Service.class)` or a full-context test depending on the risk being verified. Importing a real service can drag in repositories/external dependencies and compromise slice isolation.

## 4. Configuration Flow of a @WebMvcTest

Consider a project with:

```text
CatalogController -> CatalogService -> CatalogRepository -> DataSource
```

A full `@SpringBootTest` can load controller, service, repository, datasource, security, scheduler, messaging, and their auto-configurations. A `@WebMvcTest(CatalogController.class)` focuses on:

```text
Spring TestContext
  |
  +-- MVC infrastructure (DispatcherServlet, handler mappings, codecs)
  +-- MockMvc
  +-- CatalogController (real bean)
  +-- MVC components permitted by the slice filter
  +-- CatalogService? -> NOT scanned as a regular @Service
  +-- CatalogRepository? -> NOT scanned as a regular @Repository
  +-- DataSource auto-config? -> not auto-imported via full-app discovery
```

How to supply the service to the controller:

```java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {
    @MockitoBean
    CatalogService catalogService;

    @Autowired
    MockMvc mvc;
}
```

`@MockitoBean` comes from Spring Framework 6.2+ (Spring Boot 3.4/3.5); the import is `org.springframework.test.context.bean.override.mockito.MockitoBean`. Creating a mock service **does not** load the entire persistence stack. The controller and MVC remain real beans/infrastructure.

**Some slices also auto-import security configuration.** Do not infer "no filters" from "slice." Spring Boot `@WebMvcTest` can auto-configure Spring Security when the dependency is present; HTTP 401/403 when a test expects 200 may come from security, not `@ImportAutoConfiguration`.

## 5. Relationship Between the Two Annotations: Both Are Needed, Each for Its Role

### 5.1. Broad Path of the Full App

```text
@SpringBootApplication
    |
    +-- @EnableAutoConfiguration
            |
            +-- reads AutoConfiguration.imports on classpath
            +-- evaluates conditions and ordering
            +-- creates matching beans
```

### 5.2. Selective Path of a Slice

```text
@WebMvcTest
    |
    +-- @OverrideAutoConfiguration(enabled=false)
    |       |
    |       +-- skips @EnableAutoConfiguration's broad imports list
    |
    +-- @TypeExcludeFilters(WebMvcTypeExcludeFilter)
    |       |
    |       +-- lets only matching MVC components pass component scan
    |
    +-- @AutoConfigureWebMvc/@AutoConfigureMockMvc/...
    |
    +-- @ImportAutoConfiguration
            |
            +-- reads imports list tied to test annotation
            +-- imports slice auto-configurations (and additions)
            +-- evaluates ordering and @Conditional
```

The two annotations **do not conflict**: one shuts off the broad import source while the other keeps the selective import source. If an auto-configuration depends on another bean absent from the slice, importing it may still skip due to failed conditions, or cause context failure due to a missing required dependency. That is why every additional import must correspond to a clear need.

### 5.3. "Imported" Does Not Mean "Bean Guaranteed to Be Created"

Consider an auto-configuration:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.OptionalEngine")
class OptionalEngineAutoConfiguration {
    @Bean
    EngineSupport engineSupport() {
        return new EngineSupport();
    }
}
```

This is a **conceptual illustration**, not a standalone runnable file. When `OptionalEngine` is absent from the classpath, the condition does not match so `EngineSupport` is not created, even if the class was imported via `@ImportAutoConfiguration`.

Other conditions must also pass: web application type, property flags, existing/missing beans, resource availability, and bean definition registration order. Hence, do not treat `NoSuchBeanDefinitionException` by blindly adding imports: inspect the condition evaluation report.

## 6. Runnable Project: Proving Broad Auto-Configuration Is Disabled While Selective Imports Still Work

This section uses **one custom auto-configuration discovered via metadata** and **two custom auto-configurations omitted from broad metadata** to create a clean experiment:

- **`DiscoveryAutoConfiguration`** appears in `AutoConfiguration.imports` on the test classpath: a full test context using `@EnableAutoConfiguration` will see the `discoveryTag` bean.
- **`FeatureAutoConfiguration`** loads only when you write `@ImportAutoConfiguration(FeatureAutoConfiguration.class)`.
- **`ExtraAutoConfiguration`** is used to experiment with `exclude`.
- All extra configuration classes reside in a **package outside the application's component scan**, so they are not picked up as ordinary `@Configuration` classes. This condition is critical so the demo genuinely proves the auto-import path.

### 6.1. File Tree

```text
slice-autoconfig-lab/
├── pom.xml
├── src/main/java/com/example/slicelab/
│   ├── SliceLabApplication.java
│   ├── CatalogService.java
│   └── CatalogController.java
├── src/test/java/
│   ├── com/example/testsupport/
│   │   ├── DiscoveryTag.java
│   │   ├── FeatureTag.java
│   │   ├── ExtraTag.java
│   │   ├── DiscoveryAutoConfiguration.java
│   │   ├── FeatureAutoConfiguration.java
│   │   └── ExtraAutoConfiguration.java
│   └── com/example/slicelab/
│       ├── FullDiscoveryTest.java
│       ├── WebMvcSliceTest.java
│       ├── WebMvcImportTest.java
│       ├── LeanSelectiveContextTest.java
│       └── ImportExclusionTest.java
└── src/test/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**Important package boundary:** the app lives in `com.example.slicelab`; the test-support auto-configurations live in `com.example.testsupport`, a **sibling** package outside the `com.example.slicelab` subtree. `@SpringBootApplication` scans from root package `com.example.slicelab`, so it does not automatically scan the test-support classes.

### 6.2. Maven POM

`pom.xml`:

```xml
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
  <artifactId>slice-autoconfig-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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
```

Uses `spring-boot-starter-web` to provide MVC and `MockMvc` in tests. Test dependencies include Spring Boot Test Autoconfigure, JUnit Jupiter, Mockito, and AssertJ. Registering `AutoConfiguration.imports` in `src/test/resources` affects only the test classpath and **is not packaged as a main production resource**.

### 6.3. Main Application

`src/main/java/com/example/slicelab/SliceLabApplication.java`:

```java
package com.example.slicelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceLabApplication.class, args);
    }
}
```

### 6.4. Real Service

`src/main/java/com/example/slicelab/CatalogService.java`:

```java
package com.example.slicelab;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    public String label(long id) {
        return "real-" + id;
    }
}
```

### 6.5. Real Controller

`src/main/java/com/example/slicelab/CatalogController.java`:

```java
package com.example.slicelab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {
    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/{id}")
    public ItemResponse item(@PathVariable long id) {
        return new ItemResponse(catalogService.label(id));
    }

    public record ItemResponse(String label) {}
}
```

When running the app without mocks and calling `GET /catalog/7`, the JSON body contains `label="real-7"`. The service here is intentionally simple; its role is to show that the slice excludes the service from component scanning and requires a collaborator.

### 6.6. Three Value Records in Test Support

`src/test/java/com/example/testsupport/DiscoveryTag.java`:

```java
package com.example.testsupport;

public record DiscoveryTag(String value) {}
```

`src/test/java/com/example/testsupport/FeatureTag.java`:

```java
package com.example.testsupport;

public record FeatureTag(String value) {}
```

`src/test/java/com/example/testsupport/ExtraTag.java`:

```java
package com.example.testsupport;

public record ExtraTag(String value) {}
```

The records in the test source set serve solely to tag which auto-configuration produced a bean; they are not production domain types.

### 6.7. Auto-Configuration #1: Discovered Only via Metadata File

`src/test/java/com/example/testsupport/DiscoveryAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DiscoveryAutoConfiguration {
    @Bean
    DiscoveryTag discoveryTag() {
        return new DiscoveryTag("broad-import");
    }
}
```

**Metadata file required** at the exact path:

`src/test/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents: **a single line, without backticks or `#`:**

```text
com.example.testsupport.DiscoveryAutoConfiguration
```

`@EnableAutoConfiguration` sees this class when loading the test classpath. It is **not** explicitly imported by the slice tests.

### 6.8. Auto-Configuration #2: Imported Only When Requested

`src/test/java/com/example/testsupport/FeatureAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {
    @Bean
    FeatureTag featureTag() {
        return new FeatureTag("selective-import");
    }
}
```

Do **not** add `FeatureAutoConfiguration` to the `AutoConfiguration.imports` file above. Because the class is outside component scanning and has no broad metadata registration, it is selected only when a test specifies `@ImportAutoConfiguration(FeatureAutoConfiguration.class)` or an equivalent import mechanism.

### 6.9. Auto-Configuration #3: Used to Test `exclude`

`src/test/java/com/example/testsupport/ExtraAutoConfiguration.java`:

```java
package com.example.testsupport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ExtraAutoConfiguration {
    @Bean
    ExtraTag extraTag() {
        return new ExtraTag("should-be-excluded");
    }
}
```

Likewise, do **not** register this class in the broad metadata file. It serves the selection/exclusion test below.

### 6.10. Test #1 — Full Context Discovers Default Auto-Configuration

`src/test/java/com/example/slicelab/FullDiscoveryTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.DiscoveryTag;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullDiscoveryTest {
    @Autowired ApplicationContext context;

    @Test
    void broadDiscoveryImportsOnlyRegisteredCandidate() {
        assertThat(context.getBean(DiscoveryTag.class).value())
                .isEqualTo("broad-import");
        assertThat(context.getBeansOfType(FeatureTag.class)).isEmpty();
    }
}
```

`@SpringBootTest` uses the app's primary configuration with `@EnableAutoConfiguration` active as usual. `AutoConfiguration.imports` on the test classpath introduces `DiscoveryAutoConfiguration`, so `DiscoveryTag` is present. `FeatureAutoConfiguration` is not broadly registered, so it is not loaded.

`webEnvironment=NONE` only means **do not start a web application context/server**; it does **not** disable all auto-configuration. Thus, this test still proves the broad import path works.

### 6.11. Test #2 — MVC Slice Excludes Broad Auto-Configuration

`src/test/java/com/example/slicelab/WebMvcSliceTest.java`:

```java
package com.example.slicelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = CatalogController.class)
class WebMvcSliceTest {
    @Autowired ApplicationContext context;
    @Autowired MockMvc mvc;

    @MockitoBean CatalogService catalogService;

    @Test
    void sliceHasMvcButNotBroadDiscoveredTag() throws Exception {
        assertThat(context.containsBean("discoveryTag")).isFalse();
        assertThat(context.containsBean("featureTag")).isFalse();

        when(catalogService.label(7L)).thenReturn("mock-7");

        mvc.perform(get("/catalog/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.label").value("mock-7"));
    }
}
```

The test confirms **MVC works** while `DiscoveryAutoConfiguration` (present only in broad metadata) is absent. `MockMvc` exists despite broad auto-configuration being off thanks to the slice's selective test auto-configurations.

`@MockitoBean` provides `CatalogService` so the controller constructor can be satisfied. Without this annotation, the slice does not scan services normally, resulting in `Failed to load ApplicationContext` due to the missing collaborator.

### 6.12. Test #3 — Selectively Adding Auto-Configuration to a Slice

`src/test/java/com/example/slicelab/WebMvcImportTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(controllers = CatalogController.class)
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class WebMvcImportTest {
    @Autowired ApplicationContext context;
    @MockitoBean CatalogService catalogService;

    @Test
    void selectiveImportWorksAlthoughBroadDiscoveryDisabled() {
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");
        assertThat(context.containsBean("discoveryTag")).isFalse();
    }
}
```

The test still carries `@WebMvcTest`, so broad imports from `@EnableAutoConfiguration` do not run, yet `FeatureAutoConfiguration` is **explicitly imported** and creates the `FeatureTag` bean. This is the core experiment showing how both annotations work together without conflict.

### 6.13. Test #4 — Using @OverrideAutoConfiguration Directly with SpringBootTest

`src/test/java/com/example/slicelab/LeanSelectiveContextTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.DiscoveryTag;
import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@OverrideAutoConfiguration(enabled = false)
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class LeanSelectiveContextTest {
    @Autowired ApplicationContext context;

    @Test
    void disableBroadButKeepSelectedImportAndUserBeans() {
        assertThat(context.getBeansOfType(DiscoveryTag.class)).isEmpty();
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");

        // Disabling broad auto-configuration does NOT disable component scan:
        assertThat(context.getBean(CatalogService.class)).isNotNull();
    }
}
```

**Takeaway:** adding `@OverrideAutoConfiguration(enabled=false)` on a full-context test suppresses broad `DiscoveryAutoConfiguration`; `@ImportAutoConfiguration` still imports `FeatureAutoConfiguration`. Meanwhile, `CatalogService` is still created by the app's `@ComponentScan`. Therefore, this test **is not equivalent** to a standard slice filter: it still scans user components in the application package.

Use this manual annotation combination when you have a clear reason, such as exploring the behavior of a restricted set of auto-configurations. In most projects, prefer built-in slices because their meta-annotations are already tested and maintained by Spring Boot.

### 6.14. Test #5 — Importing Two Auto-Configurations While Excluding One

`src/test/java/com/example/slicelab/ImportExclusionTest.java`:

```java
package com.example.slicelab;

import com.example.testsupport.ExtraAutoConfiguration;
import com.example.testsupport.ExtraTag;
import com.example.testsupport.FeatureAutoConfiguration;
import com.example.testsupport.FeatureTag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.OverrideAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@OverrideAutoConfiguration(enabled = false)
@ImportAutoConfiguration(
        classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
        exclude = ExtraAutoConfiguration.class)
class ImportExclusionTest {
    @Autowired ApplicationContext context;

    @Test
    void explicitExcludeWinsForListedAutoConfiguration() {
        assertThat(context.getBean(FeatureTag.class).value())
                .isEqualTo("selective-import");
        assertThat(context.getBeansOfType(ExtraTag.class)).isEmpty();
        assertThat(context.containsBean("discoveryTag")).isFalse();
    }
}
```

`classes` and `value` are simply two names for the import list; **do not pass both with different lists**. In this test, `ExtraAutoConfiguration` is listed yet excluded via `exclude`, so `ExtraTag` is absent. This demonstrates that `exclude` acts on auto-configuration importing rather than deleting an arbitrary bean defined elsewhere.

### 6.15. Running Commands and Comparing Results

Inside the `slice-autoconfig-lab` directory with JDK 17+ and Maven:

```bash
mvn -q clean test

mvn -q -Dtest=FullDiscoveryTest test
mvn -q -Dtest=WebMvcSliceTest test
mvn -q -Dtest=WebMvcImportTest test
mvn -q -Dtest=LeanSelectiveContextTest test
mvn -q -Dtest=ImportExclusionTest test
```

The tests above are designed to PASS with the file structure and dependencies described. When `mvn test` succeeds, Maven exits with code **0**; startup timings, context cache logs, output line counts, and warnings vary across environments. Do not claim fixed console output; the values in the table below are **assertions verified by code**.

| Test | Broad-discovered `DiscoveryTag` | Selected `FeatureTag` | `ExtraTag` | MVC request |
| --- | --- | --- | --- | --- |
| `FullDiscoveryTest` | Yes | No | No | Not tested |
| `WebMvcSliceTest` | No | No | No | Mock HTTP 200, label `mock-7` |
| `WebMvcImportTest` | No | Yes | No | No request invoked |
| `LeanSelectiveContextTest` | No | Yes | No | Web env NONE |
| `ImportExclusionTest` | No | Yes | No | Web env NONE |

You can run the real application with:

```bash
mvn spring-boot:run
```

And in another terminal:

```bash
curl "http://localhost:8080/catalog/7"
```

The body contains `{"label":"real-7"}`. Note that `DiscoveryTag`/`FeatureTag` exist only in the test source set, so **they do not appear** when running the executable application artifact built from main code. The broad discovery demonstration above relies on the test classpath and metadata file in `src/test/resources`.

## 7. Proper Ways to Import When Extending a Slice

### 7.1. Adding Auto-Configuration: @ImportAutoConfiguration

The Spring Boot documentation recommends:

```java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class MyJdbcTests {
    // ...
}
```

This is an **illustration for Spring Boot 3.5**, not part of the MVC project in section 6. When a test slice needs extra auto-configurations, use `@ImportAutoConfiguration` instead of `@Import` for the auto-configuration class itself. Spring Boot applies proper ordering/condition policies when processing auto-config classes.

**Do not pull an entire set of unrelated auto-configurations** into a slice. For instance, if a test only verifies controller JSON, importing messaging brokers, batch, JDBC, JPA, schedulers, and HTTP clients defeats isolation.

### 7.2. Adding Regular Spring Configuration: @Import

If a controller test needs a custom `WebMvcConfigurer`, Jackson module, argument resolver, or project-authored `@TestConfiguration`, use:

```java
@WebMvcTest(CatalogController.class)
@Import(CustomMvcTestConfiguration.class)
class CatalogMvcTest {
    // ...
}
```

`CustomMvcTestConfiguration` is an **illustrative name**, not a class in the section 6 project. This is how you import **user configuration**, not an auto-config candidate needing ordering processing.

Do not use `@ImportAutoConfiguration` on an `@Service` class—it does not become an "auto-configuration" just from how it is imported. Use `@Import`/`@MockitoBean` or change the test scope.

### 7.3. Adding a Collaborator: @MockitoBean

`@WebMvcTest` does not scan all app services. When a controller depends on `CatalogService`, the cleanest way to verify the MVC contract is:

```java
@MockitoBean
CatalogService catalogService;
```

This field creates a mock bean directly in the test `ApplicationContext`. Do not use plain Java Mockito `@Mock` and expect Spring to inject it into the controller. If you want to test the real service together with the controller, consider `@Import(CatalogService.class)` or `@SpringBootTest + @AutoConfigureMockMvc`, paying attention to the service's dependencies.

### 7.4. Adding @ConfigurationProperties

For a slice needing an app-defined properties holder:

```java
@WebMvcTest(CatalogController.class)
@EnableConfigurationProperties(CatalogProperties.class)
class CatalogPropertiesTest {
    // ...
}
```

This is a syntax example; `CatalogProperties` must be defined by the project with valid binding annotations. Test slices normally do not auto-scan all `@ConfigurationProperties` beans in the application. Register it explicitly so binding actually takes place.

### 7.5. Adjusting Conditions Instead of Blindly Importing

If an auto-configuration has `@ConditionalOnProperty(name="feature.enabled", havingValue="true")`, merely specifying the class without the property can still fail to create the bean. To satisfy the condition:

```java
@WebMvcTest(
    controllers = CatalogController.class,
    properties = "feature.enabled=true")
@ImportAutoConfiguration(FeatureAutoConfiguration.class)
class FeatureEnabledMvcTest {
    // ...
}
```

This pattern illustrates the principle (`FeatureAutoConfiguration` in section 6 has no property condition). With a real auto-configuration, the outcome still depends on all conditions, not just one property.

## 8. .imports Metadata Files and Custom Composed Annotations

Several `@AutoConfigure…` annotations in Spring Boot use:

```java
@ImportAutoConfiguration
```

without listing classes in the annotation. When `classes` is empty, Spring Boot reads class names from the corresponding file:

```text
META-INF/spring/<fully-qualified-name-of-annotated-class>.imports
```

For example, an annotation `com.example.testtools.AutoConfigureDemoFeature` can carry:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ImportAutoConfiguration
public @interface AutoConfigureDemoFeature {}
```

This is a **syntax pattern**, not a standalone runnable file: it requires Java imports for `ElementType`, `RetentionPolicy`, related annotations, and placing the resource file below to take effect.

Metadata filename:

```text
src/test/resources/META-INF/spring/com.example.testtools.AutoConfigureDemoFeature.imports
```

Its contents can be:

```text
com.example.testtools.FeatureAutoConfiguration
# Comments are supported
```

If you need to declare a class that **might not be on the classpath**, Spring Boot supports the `optional:` prefix in `@ImportAutoConfiguration` metadata imports files. Check the Javadoc for your version and do not abuse `optional:` to hide missing required dependencies.

Distinguish **the two filenames**:

| Filename | Who uses it? | Meaning |
| --- | --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | `@EnableAutoConfiguration` | Broad candidate list of the app |
| `META-INF/spring/com.example.testtools.AutoConfigureDemoFeature.imports` | `@ImportAutoConfiguration` placed on that annotation | Selected list for the test/feature annotation |

Mixing up the two files can cause the specified auto-configuration to load everywhere, or **never load in any test**.

## 9. exclude: Excluding Auto-Configurations at the Right Layer

Common approaches:

### 9.1. Exclude at @ImportAutoConfiguration

```java
@ImportAutoConfiguration(
    classes = {FeatureAutoConfiguration.class, ExtraAutoConfiguration.class},
    exclude = ExtraAutoConfiguration.class)
```

This directly excludes from a selective import without modifying the production app.

### 9.2. Exclude via Slice Attribute

Many test slices support `excludeAutoConfiguration`. For example:

```java
@WebMvcTest(
    controllers = CatalogController.class,
    excludeAutoConfiguration = SomeAutoConfiguration.class)
class MvcWithoutOneAutoConfigTest {
    // ...
}
```

`SomeAutoConfiguration` is an illustrative class that must exist in a real project; this is not a standalone runnable file. In Spring Boot 3.5, `WebMvcTest.excludeAutoConfiguration` is an alias for the slice's `@ImportAutoConfiguration.exclude`.

### 9.3. Exclude Broad Auto-Configuration

`@SpringBootApplication(exclude=...)` and the `spring.autoconfigure.exclude` property affect the application's normal auto-configuration path; `@EnableAutoConfiguration` supports exclusions. **Do not treat these forms as full replacements for `@ImportAutoConfiguration.exclude` when customizing a test slice**. They operate on different entry points and scopes.

### 9.4. Exclude Does Not Mean "Delete Bean"

If another user configuration already creates a `FeatureTag` bean (for instance, `@Bean` in `@TestConfiguration`), excluding `FeatureAutoConfiguration` does not automatically remove that bean. The same applies to component scanning: excluding an auto-configuration class does not stop an accidentally scanned `@Component`. To debug, identify **the bean definition source** before choosing an exclusion.

## 10. Conditional Auto-Configuration and Ordering

### 10.1. `@AutoConfiguration` Is Still Configuration with Conditions

An auto-configuration typically declares:

```java
@AutoConfiguration(after = {DependencyAutoConfiguration.class})
@ConditionalOnClass(FeatureEngine.class)
class FeatureAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    FeatureFacade featureFacade() {
        return new FeatureFacade();
    }
}
```

This is an **illustrative pattern**, not a complete program: `DependencyAutoConfiguration`, `FeatureEngine`, and `FeatureFacade` are project-supplied types.

Key points:
- `@AutoConfiguration(after=...)` defines ordering **among auto-configuration classes**, not a guaranteed order when business methods execute.
- `@ConditionalOnClass` matches only when the required class is present.
- `@ConditionalOnMissingBean` can back off if a matching bean is already registered.
- Even when `@ImportAutoConfiguration` selects a class, its conditions are still processed normally.
- If you import a class whose required dependency/condition is absent, some beans will not appear; that is not necessarily a framework bug.

### 10.2. Why Not Use @Import for Auto-Configurations?

The Spring Boot test reference states clearly: to add **auto-configurations** to a slice, use `@ImportAutoConfiguration`, **do not use regular `@Import`** for auto-configuration classes. Reason: ordering, exclusions, candidate selection, and conditional auto-configuration need to follow Boot's import pipeline.

Conversely, `@Import` fits user configs and specific Spring beans. Pick the right tool so you do not inadvertently alter bean registration order or bypass desired exclusions.

### 10.3. Why Can Beans Still Be Missing Even After Importing?

For instance, `@ConditionalOnMissingBean` may back off due to an existing bean, or `@ConditionalOnClass` may fail to match because a dependency is absent. Check with the Spring Boot condition evaluation report:

```text
Condition evaluation report
  Positive matches: ...
  Negative matches: ...
  Unconditional classes: ...
```

The block above is a **description of the report format**, not exact stdout. Enable `debug=true` in test configuration or appropriate logging, then search for the **auto-configuration name** and its match/no-match reason. Do not just call `context.getBean(...)` and assume the framework ignored the annotation.

## 11. Choosing the Right Slice in Real Applications

| Risk to test | Test annotation | Usually needed auto-configurations | Should you manually add @ImportAutoConfiguration? |
| --- | --- | --- | --- |
| HTTP routing, JSON, MVC validation | `@WebMvcTest` | MVC, MockMvc, matching JSON/security | Only when a very specific extra auto-config is needed |
| WebFlux controllers/filters | `@WebFluxTest` | Reactive web pipeline, matching WebTestClient | Possible, if the slice lacks an auto-config under test |
| JPA mapping/repositories | `@DataJpaTest` | JPA, transactions, embedded/test DB per conditions | Possible, when a valid integration auto-config is needed |
| JDBC/repository helpers | `@JdbcTest` | JDBC, datasource, transactions | Possible, per Spring Boot's `IntegrationAutoConfiguration` example |
| JSON serialization | `@JsonTest` | JSON mapper/testers | Usually unnecessary when testing mapping only |
| Full context with external services | `@SpringBootTest` | App auto-configs | Do not add arbitrarily; only for custom specific needs |
| Custom framework test slice | Composed test annotation + filter + selective auto-config | Exact designed infrastructure set | Core building block of custom slices |

Never place two test slice annotations such as `@WebMvcTest` and `@DataJpaTest` on the same class to "add two slices together." Spring Boot does not support this direct combination. Pick one slice and add the other layer's specific `@AutoConfigure…`/imports, or use `@SpringBootTest` when real integration across two layers is required.

### 11.1. Web MVC Slice

`@WebMvcTest` cares only about controllers/MVC; if a controller directly requires a repository (a suboptimal design), you can mock the repository collaborator, though that proves nothing about database behavior. Fix the controller/service boundary architecture when possible; test services with unit tests and repositories with separate JPA slice tests.

### 11.2. JPA Slice

`@DataJpaTest` loads repositories, entities, `EntityManager`, and transactional test support per configuration; accidentally importing web/HTTP/broker auto-configs into a JPA slice both adds overhead and masks architectural issues. When a production-like DB is needed, use Testcontainers or a real test database appropriately rather than "importing all auto-configs."

### 11.3. JSON Slice

`@JsonTest` uses JSON mappers and appropriate testers to verify serialization. Do not assume that because a DTO serializes properly in the JSON slice, controller statuses, security, or full HTTP contracts are also valid. Use `@WebMvcTest`/integration tests for the HTTP boundary.

## 12. Common Failures and Diagnostics

### 12.1. `NoSuchBeanDefinitionException` After Using @OverrideAutoConfiguration(false)

**Symptom:** previously a datasource/codec/client existed, and after disabling broad auto-configuration the bean vanished.

**Cause:** you turned off the broad `@EnableAutoConfiguration` path without re-importing the needed auto-configurations; or you used a custom context lacking full type-exclude filters/infrastructure.

**Resolution:** identify which beans genuinely belong in the test scope. For built-in slices, use the right annotation; for custom tests, import the exact needed auto-configurations along with dependencies/conditions. Do not set `@OverrideAutoConfiguration(enabled=true)` just to make everything appear automatically when the goal is slice isolation.

### 12.2. @ImportAutoConfiguration Declared, Yet the Bean Does Not Appear

**Possible causes:**
- `@ConditionalOnClass` does not match because a dependency is absent.
- `@ConditionalOnProperty` is false or the key is missing.
- `@ConditionalOnMissingBean` backed off because another bean exists.
- `@ImportAutoConfiguration.exclude`/slice `excludeAutoConfiguration` excluded the class.
- Wrong imported class name, or the source set containing the class was not compiled.
- The `.imports` metadata file uses the wrong fully qualified annotation name.
- User-defined config already created a competing bean/candidate.

**Fix:** read the condition report; check classpath, property sources, exclusions, and package boundaries. If context loading fails, inspect the root `Caused by`, not just the outer `Failed to load ApplicationContext` wrapper.

### 12.3. @WebMvcTest Is Missing a Service

`@WebMvcTest` does not scan ordinary `@Service` beans. Constructor dependencies on the controller fail context startup. Fix with `@MockitoBean Service` to test MVC independently, or `@Import(Service.class)` when you want the real service. `@ImportAutoConfiguration(Service.class)` is not the right tool for importing a business service.

### 12.4. Test Slice Still Loads Unwanted Beans

**Cause:** The app root class uses an explicit `@ComponentScan` without preserving the default type-exclude filters; or user `@Configuration`/`@Import` forces extra beans in; or a component is an MVC-related type allowed in the slice.

**Fix:** inspect app root scan configuration, test `@Import`, `@TestConfiguration`, packages, and filters. Per the Spring Boot reference, using an explicit `@ComponentScan` on the application class can bypass default slice filters; re-register the appropriate `TypeExcludeFilter`.

### 12.5. Test Slice Has Security When You Expected HTTP 200

`@WebMvcTest` supports auto-configuring Spring Security when the dependency is present. Receiving 401/403 signals the request needs authentication/CSRF setup per policy; do not claim "slices disable security." Use Spring Security Test `@WithMockUser` or appropriate request post processors. Disable security/filters only if the test's requirements explicitly exclude them, and add separate tests covering security policy.

### 12.6. "I Used @Import Instead of @ImportAutoConfiguration and It Still Worked"

`@Import` can import a configuration class, yet doing so for auto-configurations is not Boot's recommended path for slices. The test might PASS by coincidence in a specific version and context while losing auto-configuration ordering/exclusion guarantees. Switch to `@ImportAutoConfiguration` if it is genuinely an auto-config class. For regular user configs, keep using `@Import`.

### 12.7. "Auto-Configuration Is Disabled" Yet CatalogService Still Exists

`@OverrideAutoConfiguration(enabled=false)` **does not turn off component scanning**. `CatalogService` is created by `@Service` and app scanning, so it remains in `LeanSelectiveContextTest`. To exclude user components, you need type-exclude filters or a test annotation with scoped scanning, such as `@WebMvcTest`. That is separate from auto-configuration candidate importing.

### 12.8. Importing One Auto-Config Pulls In a Chain of Dependencies

Depending on the auto-configuration, conditions may require dependent beans; importing a selected class can create multiple beans inside it, triggering DB/broker connections or missing-secret errors. The answer is not always importing the next dependency. Clarify the test goal; if you only need a fake collaborator, `@MockitoBean`/`@TestConfiguration` is usually narrower.

### 12.9. Context Cache Slows Down When Each Test Has Different Imports

Spring TestContext cache keys consider configuration, profiles, properties, context customizers, imports, and bean overrides. Two tests using different `@ImportAutoConfiguration` sets get separate contexts; that is expected because their bean graphs differ. Keep slices with the same purpose consistently configured, prefer unit tests for non-Spring logic, and avoid overusing `@DirtiesContext`.

### 12.10. Tests Pass Locally on Dev Machine, Fail on CI

Common differences:
- Different classpath due to dependencies/profiles/plugins.
- Test resource `META-INF/spring/...imports` not copied.
- Missing environment variables causing conditions not to match.
- Spring Boot version changed slice auto-configuration lists or package imports.
- JDK/DB/network and test execution order.
- A full-context test leaving mutated state that pollutes other tests.

**Diagnostic steps:** run a clean Maven/Gradle build, compare `target/test-classes`, `dependency:tree`, the condition report, and the first failing context load. Do not fix it by enabling all auto-configurations if the original test had a clear narrow scope.

## 13. Repeatable Debugging Workflow

### 13.1. Observe Actual Beans in the Context

In a test:

```java
@Autowired ApplicationContext context;

// Inside a @Test method:
assertThat(context.containsBean("featureTag")).isTrue();
assertThat(context.containsBean("discoveryTag")).isFalse();
```

This is an **illustrative** snippet; import AssertJ and `ApplicationContext` as in the runnable files in section 6. When bean names come from `@Bean` methods, you can also check `context.getBean(FeatureTag.class)`. With multiple beans of the same type, use `context.getBeansOfType(...)` or select by name.

### 13.2. Inspect Output Resources and Dependencies

```bash
mvn -q clean test
mvn dependency:tree
```

In the example, `AutoConfiguration.imports` must be copied into:

```text
target/test-classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Its contents must be the exact FQCN `com.example.testsupport.DiscoveryAutoConfiguration`. The file must not sit under `target/classes` because it is a **test resource**, intentionally kept away from production.

### 13.3. Enable the Condition Evaluation Report When Needed

You can add `debug=true` to a Spring Boot test or use appropriate logging to see positive/negative matches of auto-configurations. A bean being absent can happen because **it was not imported** or **it was imported yet a condition was false**; these are two different causes.

Filter logs by the auto-configuration class name and condition rather than reading unstructured startup logs top to bottom.

### 13.4. Maven Surefire Output

`mvn test` reports TEST FAILURE for assertion mismatches and ERROR when the test context fails; that is just the test runner's classification. Context failure can happen before any test body runs. Subsequent failures with the same context cache key may be blocked by Spring TestContext's failure threshold; read **the first failure for that context**. Do not treat raising the threshold as a fix for missing beans.

### 13.5. How to Write Boundary-Protecting Checks

Have at least two kinds of assertions:
- **Feature under test**: e.g., an MVC request to `/catalog/7` returns 200 and the expected JSON label.
- **Slice boundary**: unrelated auto-config beans do not appear, while required beans are present.

A test asserting only that `MockMvc` was autowired can miss accidentally importing the whole DB stack. A test asserting only that an imported bean exists without calling the SUT can miss bugs in the controller. Combine behavioral checks and boundary checks in critical slices.

## 14. When NOT to Use These Two Annotations

- **Pure Java logic:** use JUnit + Mockito, instantiate the SUT via constructor, without loading a Spring context.
- **One service needing small config:** use `@TestConfiguration` and `@Import`; no need to write a custom auto-configuration unless there is clear value.
- **Integration needing all real beans:** `@SpringBootTest` with appropriate profiles/test infrastructure; manually disabling broad auto-config can make the test unrepresentative of the app.
- **Test needing only one fake collaborator:** use `@MockitoBean`; do not build an auto-config just to register one mock.
- **Testing database mapping:** use built-in `@DataJpaTest` with an appropriate test DB; do not rewrite `@OverrideAutoConfiguration` from scratch unless developing a custom test slice framework.
- **Disabling one specific auto-config in a slice:** use `excludeAutoConfiguration` or `@ImportAutoConfiguration(exclude=...)`, rather than disabling everything and rebuilding many classes manually.
- **Blindly optimizing performance via "fewer beans":** first verify the test boundary, infrastructure setup, context reuse, and actual bean graph.

## 15. Review Questions with Answers

1. **Why does `@WebMvcTest` have MockMvc even though broad auto-configuration is turned off?** Because the annotation composes `@AutoConfigure…` and `@ImportAutoConfiguration` for MVC/test infra alongside type-exclude filters.
2. **Does `@OverrideAutoConfiguration(enabled=false)` remove `@Service` from component scanning?** No. It controls the `@EnableAutoConfiguration` path and does not alter component scanning by itself.
3. **Why can `@ImportAutoConfiguration(FeatureAutoConfiguration.class)` still create beans when broad auto-config is off?** Because it is an **independent selective import path**; the class is processed under auto-configuration rules and conditions.
4. **Is an imported auto-configuration guaranteed to produce its beans?** No. Unmet conditions or an existing bean can cause it to back off.
5. **Should you use `@Import` or `@ImportAutoConfiguration` to add `IntegrationAutoConfiguration` to `@JdbcTest`?** Use `@ImportAutoConfiguration`, per Spring Boot documentation.
6. **What do you use to bring a custom `WebMvcConfigurer` configuration into an MVC slice?** Typically `@Import` an appropriate `@Configuration`/`@TestConfiguration` class, not treating it as an auto-config candidate.
7. **What do you use to supply `CatalogService` to `CatalogController` in `@WebMvcTest`?** Typically `@MockitoBean`; use `@Import` if you genuinely need the real service.
8. **Why does `FullDiscoveryTest` see `DiscoveryTag` while `WebMvcSliceTest` does not?** The full test uses broad `@EnableAutoConfiguration` and `AutoConfiguration.imports`; the MVC slice disables the broad path.
9. **Why does `WebMvcImportTest` still see `FeatureTag`?** Because `FeatureAutoConfiguration` is imported explicitly via `@ImportAutoConfiguration`.
10. **Does `@ImportAutoConfiguration`'s `exclude` remove a user-created bean of the same type?** No; it excludes an auto-configuration from importing and does not delete other bean definitions.
11. **Can you place `@WebMvcTest` and `@DataJpaTest` on the same class to combine two slices?** Not supported by Spring Boot; pick one slice and add appropriate configuration, or use full-context.
12. **When a custom metadata imports file does not load, what should you check?** Path, FQCN, `target/test-classes` output, annotation placed on the class, classpath, and conditions.
13. **Why can a direct `@ComponentScan` on the app root cause a slice to load too much?** Because it can override the exclude filters `@SpringBootApplication` provides for slicing.
14. **When should you use `@OverrideAutoConfiguration` directly?** When designing a very specific test context/slice and you know what to re-import/re-configure; normally built-in slices handle this.
15. **What must you verify after adding a custom auto-config to a slice?** The target bean is present, unrelated beans remain absent, and SUT behavior works properly.

## 16. Pre-Merge Checklist for a Test Slice

- [ ] Chose the right slice type (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`…) instead of writing configuration from scratch?
- [ ] Clearly distinguished broad auto-config from selective imports and user bean scanning?
- [ ] Aware that `@OverrideAutoConfiguration(enabled=false)` does **not** turn off component scanning?
- [ ] Aware that `@ImportAutoConfiguration` still evaluates conditions and ordering?
- [ ] Imported only truly needed auto-configurations without dragging the whole system into the test?
- [ ] When mocking service/controller collaborators, used `@MockitoBean` on the exact bean?
- [ ] When importing user `@Configuration`, used `@Import` for its proper purpose?
- [ ] If properties are needed, configured `@EnableConfigurationProperties`/property sources appropriately?
- [ ] If using exclusions, targeted the right auto-config class rather than trying to delete a bean from a different source?
- [ ] If `.imports` metadata is used, verified the path/FQCN and presence in output resources?
- [ ] Verified bean presence/absence in the slice via `ApplicationContext` or condition report?
- [ ] Included real behavioral tests (HTTP/JSON/queries) instead of asserting only "context loads"?
- [ ] Tested security, transactions, and external infrastructure at the right boundary?
- [ ] Verified tests run cleanly in Maven/Gradle, not just the IDE?
- [ ] Avoided placing two slice annotations on the same class?
- [ ] After adjusting configuration, checked speed/context caching and re-ran the relevant suite?

**Conclusion:** `@OverrideAutoConfiguration(enabled=false)` closes the door on **broad auto-configuration discovery**, while `@ImportAutoConfiguration` opens it for **selected auto-configurations**. A good test slice also needs a **component-scan boundary** and **appropriate test infrastructure**, ensuring the test checks exactly one part of the application without accidentally pulling in out-of-scope subsystems.

## 17. Official Documentation

- Spring Boot 3.5 — Testing Spring Boot Applications, sections Auto-configured Tests / Additional Auto-configuration and Slicing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 Javadoc — `@OverrideAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/OverrideAutoConfiguration.html
- Spring Boot 3.5 Javadoc — `@ImportAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Spring Boot 3.5 Javadoc — `@WebMvcTest` (including meta-annotations and `excludeAutoConfiguration`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Javadoc — `@EnableAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Framework — TestContext Framework context caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter User Guide: https://docs.junit.org/5.11.4/user-guide/
