# Include Filters, Exclude Filters, and Component Scan Scope

## 1. What Problem Does This Lesson Solve?

A **test slice** in Spring Boot is a style of testing that loads only a portion of the application context and a set of auto-configurations suited to the architectural layer under test. For example, `@WebMvcTest` targets Spring MVC; `@DataJpaTest` targets Spring Data JPA, entities, and repositories. Unlike `@SpringBootTest`, a slice intentionally **does not load every bean in the application**.

However, there are times when the default scope is too narrow or too wide for a specific test:

- An MVC slice needs **one** lightweight business converter `@Service` so the controller can run, without wanting to load all services.
- A custom servlet `Filter` falls inside the MVC component set scanned by default, yet the current test focuses solely on JSON serialization and needs to exclude that filter from **what component scanning discovers**.
- A test needs to restrict controllers to just `OrderController` instead of every controller in the module.
- A slice unexpectedly loads a database, scheduler, or external client configuration because the application declares a separate `@ComponentScan` on the `@SpringBootApplication` class.
- A developer adds `includeFilters` and the bean is still missing because it lies outside the scanned base package or is created by a mechanism other than component scanning.

Primary tools:

- `includeFilters` — expands the set of **component candidates** allowed through slice scanning.
- `excludeFilters` — excludes certain candidates from slice scanning.
- `useDefaultFilters` — enables/disables the slice's default component matching rules.
- `controllers` / `value` on `@WebMvcTest` — limits which controllers the test targets.
- `@Import`, `@TestConfiguration`, `@MockitoBean` — ways to add or substitute dependencies **beyond simple component-scan filters**.
- `excludeAutoConfiguration` — acts on auto-configuration classes, **distinct** from excluding beans by type.

**Expected outcome:** know how to pick the right filter, understand scanning mechanics, avoid unintentionally turning a slice into a full context, and verify bean scope with concrete assertions rather than guessing from annotation names.

Lesson scope: Java 17+, Spring Boot 3.x for runnable examples; explains differences in Spring Boot 4.x and risks of using similar syntax in other slice types.

## 2. First, Distinguish Four Bean-Loading Mechanisms

A class appearing in a Spring context does not necessarily come from component scanning. Without distinguishing bean sources, `includeFilters`/`excludeFilters` are easily misused.

| Bean source | Example | Candidate of component scanning? |
|---|---|---|
| Stereotype scanning | `@Component`, `@Service`, `@Repository`, `@Controller` | Yes, when package and filters permit |
| Configuration definition | `@Bean` in a loaded `@Configuration` | The `@Bean` method itself is not directly filtered like a candidate class |
| Config/class import | `@Import(MyConfig.class)`, test configuration | Does not rely on `MyConfig` being auto-discovered by scanning |
| Auto-configuration / registrar | Beans created by Spring Boot auto-config or Spring Data repository registrar | Not fully controlled by scan filters alone |

For instance, an `@Service` in the right package may be excluded from MVC slice candidates even though it is valid in production. You use `includeFilters` to admit that single class into **the scanning process**. Conversely, if a `DataSource` bean is created by auto-configuration, writing `excludeFilters = ...DataSource.class` is **not** the right way to turn off JDBC auto-configuration.

**Rule:** before changing filters, answer *did this bean come from component scanning, @Import/@Bean, or auto-configuration?* and *does the test goal truly need that bean?*

## 3. How Do Test Slices Work?

### 3.1. Full Context and Slices Diverge at Bootstrapping

Given a Spring Boot application with controllers, services, repositories, and web dependencies:

```text
@SpringBootTest
    └─ Primary application configuration
       ├─ Controller
       ├─ Service
       ├─ Repository
       ├─ @Configuration/@Bean
       └─ Auto-configuration per classpath/properties

@WebMvcTest(controllers = OrderController.class)
    └─ MVC slice test
       ├─ OrderController + MVC infrastructure
       ├─ ControllerAdvice/Converter/Filter... within scope
       ├─ MockMvc
       ├─ Deliberately imported/mocked/included dependencies
       └─ Does not scan all @Service/@Repository by default

@DataJpaTest
    └─ JPA slice test
       ├─ Entities and Spring Data repositories via dedicated mechanisms
       ├─ EntityManager/transaction/JDBC-JPA infrastructure
       └─ Does not scan controllers and application services by default
```

This is a **conceptual diagram**, not a complete list of auto-configurations or a guarantee every project loads those exact beans. Details depend on dependencies, configuration, profiles, and Spring Boot version.

Why do slices usually run faster? They load fewer beans and less infrastructure, reducing startup time and failure points outside the layer under test. However, **fewer beans does not mean stronger testing in every situation**: when verifying the entire MVC → service → repository chain, a full-context integration test has its own value.

### 3.2. What Does `@WebMvcTest` Accept by Default?

According to Spring Boot 3.x/4.x Javadoc, the MVC slice picks up controllers and certain MVC-related components. Besides `@Controller`/`@ControllerAdvice`, this includes types such as `@JsonComponent`, `Converter`, `GenericConverter`, `Filter`, `HandlerInterceptor`, `HandlerMethodArgumentResolver`, `HttpMessageConverter`, `SecurityFilterChain`, `WebMvcConfigurer`, and those listed in the documentation for your specific version.

Thus, both of these assumptions are wrong:

- "`@WebMvcTest` contains only a single controller, never filters or advice." False; many MVC support components remain in scope.
- "The controller depends on an `@Service`, so `@WebMvcTest` automatically scans that service." False; ordinary `@Service` beans are excluded from MVC slice component scanning unless deliberately added.

An MVC slice test typically uses `@MockitoBean`/mock services or `@Import` on a small configuration. `includeFilters` is the choice when you **deliberately want to admit a class from scanning into the context**, not something you must apply to every dependency by default.

### 3.3. Does `@DataJpaTest` Have the Same Scanning Mechanism?

`@DataJpaTest` also has `includeFilters`, `excludeFilters`, and `useDefaultFilters`, yet its **default set is completely different**. It focuses on JPA entities, Spring Data repositories, and JPA/transaction/database auto-configuration. Entities/repositories are discovered by specialized mechanisms like entity scanning and Spring Data repository registration.

Therefore, do not assume:

> "If I include an `@Service` in `@DataJpaTest`, the JPA slice turns into `@SpringBootTest`."

It merely admits a candidate via the filter mechanism; it does not auto-load all collaborators, enable all other auto-configurations, or resolve database connections if JPA infrastructure is missing. In many cases, an explicit `@Import` for a pure Java service is easier to read.

## 4. Filter Syntax on Test-Slice Annotations

### 4.1. Structure of `ComponentScan.Filter`

Spring Boot lets you pass `@ComponentScan.Filter` annotation entries in attributes of many test slices:

```java
@WebMvcTest(
    controllers = OrderController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = OrderFormatter.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = RequestAuditFilter.class
    )
)
class OrderControllerWebSliceTest {
}
```

**This is a syntax illustration**, assuming the classes already exist; it is not a standalone runnable test yet. Meaning of the three parts:

1. `controllers = OrderController.class` restricts the selected controller.
2. `includeFilters` explicitly opens the door for `OrderFormatter` (provided it is a scanned component in a valid package).
3. `excludeFilters` removes `RequestAuditFilter` from that component scan, even though it belongs to the default permitted MVC components.

To use the syntax above, typical imports include:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
```

The `WebMvcTest` package shown here is for **Spring Boot 3.x**. Section 11 covers Boot 4.

### 4.2. Common `FilterType` Values

| `FilterType` | Matching criterion | When to use |
|---|---|---|
| `ASSIGNABLE_TYPE` | A specific class/interface or compatible subclass/implementation | Including/excluding a concrete type or implementation hierarchy |
| `ANNOTATION` | An annotation present directly or via meta-annotation per Spring rules | Grouping helper components marked by a custom annotation |
| `REGEX` | Regular expression matching the fully qualified class name | Selecting type groups by name/package; use cautiously |
| `ASPECTJ` | AspectJ type pattern expression | Systems with type-pattern classification rules |
| `CUSTOM` | Class implementing a custom `TypeFilter` | Complex metadata rules not handled by earlier types |

The default for `@ComponentScan.Filter` is typically `FilterType.ANNOTATION`; if you pass `classes = SomeClass.class` and forget `type = ASSIGNABLE_TYPE`, you can hit configuration errors because that class is not an annotation.

**Prefer type safety:** `ASSIGNABLE_TYPE` with `classes = X.class` refactors cleanly and reads better than a regex holding package strings. Regex remains useful for matching multiple classes by name, though it easily matches unintended classes.

### 4.3. Filtering by Annotation

Suppose a project defines `@SliceHelper` on certain web helper classes:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SliceHelper {
}
```

With imports `java.lang.annotation.ElementType`, `Retention`, `RetentionPolicy`, and `Target`; this is only an **illustrative annotation definition**, not a separate source file in the section 7 runnable example.

Tests can include matching classes:

```java
includeFilters = @ComponentScan.Filter(
    type = FilterType.ANNOTATION,
    classes = SliceHelper.class
)
```

This is an **annotation attribute**, not a standalone Java statement. A class carrying `@SliceHelper` must still reside in a valid scan region and be a registrable candidate; a marker annotation alone does not turn an out-of-scope POJO into a Spring bean.

### 4.4. Filtering by Regex

```java
excludeFilters = @ComponentScan.Filter(
    type = FilterType.REGEX,
    pattern = "com\\.example\\.api\\.internal\\..*"
)
```

**Illustrative snippet** for a hypothetical package structure. Regex matching inspects **class names**, not bean names or request paths. If packages change, regex can break; if the pattern is too broad, you may accidentally exclude components under test.

Do not use regex to "exclude every service in a package" when the slice already excludes them; that hurts readability without adding clarity.

### 4.5. How Include, Exclude, and Defaults Interact

Understand the three sets:

- **Slice's default includes**: bean types the slice permits by default.
- **Custom includes**: additional candidates you want to allow.
- **Custom excludes**: candidates to omit from the filtered scan.

A specific exclude rule can remove a candidate even if that candidate belongs to the default or custom includes. Still, this model applies **at the component-scanning level**; beans registered via `@Import`, `@Bean`, or auto-configuration may remain present.

## 5. `controllers` and `useDefaultFilters`: Controlling Default Scope

### 5.1. `controllers` Selects Controllers Without Shrinking the Context to One Class

```java
@WebMvcTest(controllers = ProductController.class)
class ProductControllerWebTest {
}
```

When classes and dependencies are valid, the MVC slice targets only the specified controller instead of scanning all controllers as when `controllers` is omitted. However, the context can still contain `ControllerAdvice`, converters, filters, MVC config, validation, and security infrastructure allowed by the slice.

Accordingly, a test may receive HTTP 403 even with a single controller selected because the Spring Security filter chain remains in scope. Do not conclude a filter was "scanned by mistake" solely from a 403: that may be valid configuration where the test has not supplied an authenticated user or CSRF token.

### 5.2. `useDefaultFilters = true` Is the Default

On many slice annotations, `useDefaultFilters` defaults to `true`, though **"default" means each slice's own permitted set**, not every `@Component` in the application.

- On `@WebMvcTest`, the default permits MVC component types.
- On `@DataJpaTest`, regular component scanning is heavily restricted; entities/repositories follow JPA's specialized mechanisms.
- Two annotations sharing the same attribute name **do not imply the same default bean set**.

### 5.3. `useDefaultFilters = false` Is Only for Tight Control

Illustrative example of intent:

```java
@WebMvcTest(
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductController.class
    )
)
class NarrowWebTest {
}
```

This is a **configuration snippet**, not a standalone runnable test. It deliberately turns off default candidate selection and includes a specific component; the outcome still depends on the bootstrapper, auto-configuration, and controller dependencies. Some MVC configuration you need might stop being scanned, so inspect the resulting context.

**Choose the right tool:** if you only want to test one controller, `controllers = ProductController.class` is usually clearer than disabling all defaults and adding items back manually. Disabling default filters is a special case for controlling an unusual scan set precisely.

### 5.4. A Controller with a Required Dependency

Suppose `OrderController` requires `OrderService` in its constructor. `@WebMvcTest(OrderController.class)` does not scan regular services by default, so the test may fail with `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`.

Three distinct options exist:

1. **Mock the dependency:** `@MockitoBean OrderService service` (on Spring Framework 6.2+/compatible Boot) — appropriate when testing only the HTTP contract/controller.
2. **Import bean/configuration:** `@Import(OrderService.class)` when you want to execute real logic of a class with minimal dependencies.
3. **Include via component scan:** `includeFilters = @Filter(type = ASSIGNABLE_TYPE, classes = OrderService.class)` when that class lies in the scan area and you intentionally want to verify scanning.

Option three is the focus of this lesson. Still, if the goal is verifying real controller → service → repository wiring across many beans, consider `@SpringBootTest + @AutoConfigureMockMvc` instead of expanding a slice close to a full context.

## 6. Experiment Design: One Service Included, One Filter Excluded

We will build a tiny Spring MVC application with these components:

- `EchoController` accepts `GET /api/echo/{word}` and calls `FormatterService`.
- `FormatterService` is marked `@Service`; absent in a normal MVC slice, it **will appear via an include filter**.
- `AuditHeaderFilter` is marked `@Component` and implements servlet `Filter`; by type it is considered by the MVC slice, yet **an exclude filter removes it**.
- `AdminController` is another controller, intentionally **omitted from `controllers`** in the test.
- `BillingService` is another service with no custom include, so it **is not scanned**.

The test's goal goes beyond context startup. We will prove:

1. `FormatterService` is actually in the context and its real logic runs.
2. `AuditHeaderFilter` is not a bean in this slice.
3. `AdminController` and `BillingService` are not dragged into the slice.
4. A request to `EchoController` returns the right JSON without the excluded filter's header.
5. A request to `AdminController`'s endpoint is not mapped in this slice.

**Prerequisites:** the example is designed for **Spring Boot 3.x, Java 17+, and JUnit Jupiter**. All production Java classes reside in a single package to avoid scan-location issues. There is no Spring Security, JPA, database, Testcontainers, or external service in the base example.

## 7. Runnable Java 17+ Example with Spring Boot 3.x

### 7.1. Dependencies

In a Gradle Groovy DSL project already configured with the Spring Boot plugin/BOM, repositories, and Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

If using Maven with Spring Boot parent/BOM and an appropriate test plugin, the corresponding dependencies are:

```xml
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
```

These are **excerpts from build files**, not complete build files. Spring MVC and JSON converters come from the web starter; JUnit Jupiter, AssertJ, and Spring Test/MockMvc come from the test starter. Do not add Security to this sample, because security filters change HTTP statuses unless test users/CSRF are configured.

### 7.2. File Tree

```text
src/
├── main/java/com/example/slicefilters/
│   ├── SliceFiltersApplication.java
│   ├── EchoController.java
│   ├── FormatterService.java
│   ├── AuditHeaderFilter.java
│   ├── AdminController.java
│   └── BillingService.java
└── test/java/com/example/slicefilters/
    └── EchoWebMvcSliceTest.java
```

Place `package com.example.slicefilters;` at the top of every class. The `@SpringBootApplication` class sits in that package so default component scanning covers the remaining classes.

### 7.3. Application Class

**File `src/main/java/com/example/slicefilters/SliceFiltersApplication.java`:**

```java
package com.example.slicefilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceFiltersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceFiltersApplication.class, args);
    }
}
```

**Intentionally do not add a direct `@ComponentScan`** on this class. Spring Boot supplies default scanning with `TypeExcludeFilter` so test slicing continues to work.

### 7.4. Service to Include in the MVC Slice

**File `src/main/java/com/example/slicefilters/FormatterService.java`:**

```java
package com.example.slicefilters;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class FormatterService {
    public String normalize(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
```

Even though it has `@Service` and is scanned in the real application, by default `@WebMvcTest` excludes services from selected MVC components. Thus, the test specifies `includeFilters` with `ASSIGNABLE_TYPE` to admit this class specifically.

### 7.5. Controller Under Test

**File `src/main/java/com/example/slicefilters/EchoController.java`:**

```java
package com.example.slicefilters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {
    private final FormatterService formatter;

    public EchoController(FormatterService formatter) {
        this.formatter = formatter;
    }

    @GetMapping("/api/echo/{word}")
    public Map<String, String> echo(@PathVariable String word) {
        return Map.of("value", formatter.normalize(word));
    }
}
```

The controller requires the service via its constructor. This makes a meaningful test: if the include filter does not work, the context fails to start due to the missing `FormatterService`. When the filter works, a GET request verifies both the real normalization logic and JSON serialization.

### 7.6. Servlet Filter to Exclude from the Slice

**File `src/main/java/com/example/slicefilters/AuditHeaderFilter.java`:**

```java
package com.example.slicefilters;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AuditHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        response.setHeader("X-Audit", "enabled");
        filterChain.doFilter(request, response);
    }
}
```

This class is a `@Component` belonging to the Servlet `Filter` family. Without excluding it, the filter can enter MockMvc and add `X-Audit: enabled`. Because this lesson specifically asks to **exclude a component belonging to the MVC scan set**, the test applies `excludeFilters` to this class.

Do not treat the filter as "bad" in production. It is simply **out of scope** for this specific test. If the system has real audit/security requirements, add tests where the filter is enabled rather than excluding it from every test.

### 7.7. Two Out-of-Scope Components

**File `src/main/java/com/example/slicefilters/AdminController.java`:**

```java
package com.example.slicefilters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    @GetMapping("/api/admin/ping")
    public Map<String, String> ping() {
        return Map.of("status", "UP");
    }
}
```

**File `src/main/java/com/example/slicefilters/BillingService.java`:**

```java
package com.example.slicefilters;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public int calculateFee() {
        return 100;
    }
}
```

`AdminController` is not listed in `controllers = EchoController.class`. `BillingService` is not in `includeFilters`, and `@Service` is restricted by default in MVC slices. Both serve **scope assertions**, not dependencies needed by `EchoController`.

### 7.8. Test Class with Include and Exclude Filters

**File `src/test/java/com/example/slicefilters/EchoWebMvcSliceTest.java`:**

```java
package com.example.slicefilters;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(
    controllers = EchoController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = FormatterService.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = AuditHeaderFilter.class
    )
)
@AutoConfigureMockMvc(addFilters = true)
class EchoWebMvcSliceTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    FormatterService formatter;

    @Autowired
    MockMvc mvc;

    @Test
    void includesTheSelectedServiceFromComponentScan() {
        assertThat(context.getBeanNamesForType(FormatterService.class))
                .hasSize(1);
        assertThat(context.getBeanNamesForType(EchoController.class))
                .hasSize(1);
        assertThat(formatter.normalize("  book  "))
                .isEqualTo("BOOK");
    }

    @Test
    void excludesServletFilterFromComponentScan() {
        assertThat(context.getBeanNamesForType(AuditHeaderFilter.class))
                .isEmpty();
    }

    @Test
    void doesNotScanUnselectedControllerOrService() {
        assertThat(context.getBeanNamesForType(AdminController.class))
                .isEmpty();
        assertThat(context.getBeanNamesForType(BillingService.class))
                .isEmpty();
    }

    @Test
    void mvcRequestUsesIncludedServiceWithoutExcludedFilter()
            throws Exception {
        mvc.perform(get("/api/echo/hello")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.value").value("HELLO"))
                .andExpect(header().doesNotExist("X-Audit"));
    }

    @Test
    void unselectedAdminEndpointIsNotMapped()
            throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isNotFound());
    }
}
```

**Expectation:** **5 `@Test` methods** pass on a clean Spring Boot 3.x project with the dependencies above, Java 17+, and JUnit Jupiter. The tests do not print stdout themselves; Gradle/Maven/IDE show summaries per their version and configuration. `@AutoConfigureMockMvc(addFilters = true)` here **intentionally keeps default filter registration** — that way, the test is not "hiding" `AuditHeaderFilter` by turning off all filters; instead, we prove the specific filter was genuinely excluded from component scanning.

### 7.9. How to Run

Linux/macOS:

```bash
# If the project uses Gradle Wrapper:
./gradlew test --tests "com.example.slicefilters.EchoWebMvcSliceTest"

# If the project uses Maven Wrapper/Surefire:
./mvnw -Dtest=EchoWebMvcSliceTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.slicefilters.EchoWebMvcSliceTest"

# Or Maven:
.\mvnw.cmd "-Dtest=EchoWebMvcSliceTest" test
```

Pick the command matching your build tool; do not assume a project has both wrappers. In multi-module builds, target the module containing the test. No `java -jar` or HTTP server is needed to run `MockMvc`: tests dispatch requests inside the JVM.

### 7.10. Reading the Experimental Results

| Check | Expected observation | What it proves |
|---|---|---|
| Fetch `FormatterService` from context | Exactly one bean | Custom include filter admitted the bean into the slice |
| `formatter.normalize("  book  ")` | `BOOK` | Real service logic ran, not a Mockito stub |
| Look up `AuditHeaderFilter` | No bean | Custom exclude filter excluded the component |
| Look up `AdminController` | No bean | `controllers = EchoController.class` restricted controllers |
| Look up `BillingService` | No bean | MVC slice does not auto-load every service |
| GET `/api/echo/hello` | 200, JSON `"value":"HELLO"`, no `X-Audit` | Request ran through controller and included service; filter was excluded |
| GET `/api/admin/ping` | 404 | Controller is outside the slice, endpoint is unmapped |

**Reason from assertions, not merely from pass counts.** If you remove `includeFilters`, the test fails right at bootstrapping due to missing `FormatterService`; if you remove `excludeFilters`, `AuditHeaderFilter` appears and adds the header. That verifies the real semantic effect of both filters, not just syntax.

## 8. When to Use Filters vs. Other Approaches?

### 8.1. When Does `includeFilters` Fit?

Use it when:

- The component to add has the right stereotype/interface and sits inside the test's component scan region.
- You want to verify **the scan configuration itself** and the class's real bean.
- The component is small with few collaborators; adding it does not pull a large dependency graph into the slice.
- There is a marker annotation or common interface representing a group of web-supporting components.

Do not use it as a "fix every missing bean mechanism" when the real dependency is a database client, Kafka consumer, scheduler, or complex integration service. In that case, rethink the test structure.

### 8.2. When Is `@Import` More Appropriate?

Suppose the controller needs a pure Java formatter and you do not want to depend on package scanning:

```java
@WebMvcTest(controllers = EchoController.class)
@Import(FormatterService.class)
class EchoWithImportedServiceTest {
}
```

**This is an illustrative test configuration**, not a standalone runnable test. `@Import` registers the named class/configuration explicitly, **without requiring the component to be discovered by an include filter**. This is often the cleanest option when you simply need one real bean in an MVC slice without testing scan mechanics.

However, do not import an entire subsystem's `@Configuration` when it indirectly pulls in DB, schedulers, network clients, or many auto-configs; doing so can turn a small MVC slice into an unnecessarily complex startup test.

### 8.3. When Is `@TestConfiguration` More Appropriate?

When a dependency needs a **small test-only fake**, you can declare a nested `@TestConfiguration` inside the test:

```java
@TestConfiguration(proxyBeanMethods = false)
static class SliceOnlyConfig {

    @Bean
    ExternalQuoteGateway externalQuoteGateway() {
        return sku -> 123L;
    }
}
```

**Illustrative snippet**: `ExternalQuoteGateway` is a hypothetical interface with one abstract method accepting a SKU and returning `long`/`Long`; to run, define the interface and Spring imports. Test configuration adds a controlled bean without scanning the production external client. It serves behavioral testing, **not proving that `ExternalQuoteGateway` is discovered by `includeFilters`**.

Important detail: nested `@TestConfiguration` typically **supplements** the primary configuration found by test bootstrapping; ordinary nested `@Configuration` can **replace** the primary configuration in certain test bootstrap cases. Choose the annotation deliberately.

### 8.4. Mocking Services: Less Code and Exact Scope

When testing only controller HTTP mapping, JSON, and validation, mocking dependencies is usually appropriate:

```java
@WebMvcTest(EchoController.class)
class EchoContractTest {

    @MockitoBean
    FormatterService formatter;
}
```

**Snippet targets Spring Framework 6.2+ with test bean override support**, such as many Spring Boot 3.4+/4.x projects; requires `import org.springframework.test.context.bean.override.mockito.MockitoBean;`. Boot 3.3 and below typically use Spring Boot's `@MockBean` (deprecated in newer lines). Do not paste `@MockitoBean` into Boot 3.2 and expect the import to exist.

If you want to verify the real `FormatterService.normalize(...)`, do not mock it. The runnable example in section 7 intentionally uses `includeFilters` to exercise component scanning directly.

### 8.5. When Should You Switch to a Full Context?

If a test requires controller + service + repository + transactions + multiple configs, rather than including a dozen classes and chasing `NoSuchBeanDefinitionException` one by one, use:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class FullContextApiTest {
}
```

**Illustrative snippet**, not a complete test class. Unlike an MVC slice, a full application context can load databases or external integrations; prepare proper test profiles/fixtures and isolation. That is an **intentional change of test scope**, not a "filter fix."

## 9. Distinguishing `excludeFilters` from Other Forms of Exclusion

The same word "exclude" in Spring Boot carries several layers of meaning.

| Tool | What gets excluded | What it cannot do on its own |
|---|---|---|
| `excludeFilters` on a slice | Component candidates scanned under filter rules | Not guaranteed to exclude beans registered via `@Import` or auto-config |
| `excludeAutoConfiguration` on a slice | Auto-configuration classes imported/applied by the slice | Not a generic filter for `@Service` |
| `@SpringBootApplication(exclude=...)` | Application auto-configuration classes | Does not exclude arbitrary controllers/services |
| `@ComponentScan(excludeFilters=...)` | Component candidates for that scan | Does not remove beans created by direct `@Bean` registration |
| `@AutoConfigureMockMvc(addFilters=false)` | Skips registering servlet filters from context into MockMvc | **Does not remove** the `Filter` bean from the application context |
| `@MockitoBean` | Creates/overrides a bean with a Mockito mock per test framework rules | Not a package-scanning rule |

This is the most common source of confusion around the word **Filter**:

- **Component-scan `excludeFilters`** decide **whether a class is discovered/registered as a Spring bean via scanning**.
- **Servlet `Filter`** is the runtime object executing before the controller.
- **`@AutoConfigureMockMvc(addFilters=false)`** can leave the `AuditHeaderFilter` bean inside the context while omitting it from the MockMvc filter chain.

Thus, asserting only "no `X-Audit` header" is not enough to prove the filter bean was excluded from scanning. Section 7's example also asserts that `context.getBeanNamesForType(AuditHeaderFilter.class)` is empty to test **the true meaning of the component-scan filter**.

### 9.1. `@ImportAutoConfiguration` Differs from `@Import`

Spring Boot test slices restrict auto-configurations to a tailored set. If you want to add an auto-configuration to a slice, Spring Boot guides you to use `@ImportAutoConfiguration` or slice customization mechanisms, rather than arbitrarily treating `@Import` as equivalent for all auto-configurations.

Conversely, when you just need a regular bean/config, `@Import` can be a clear choice. Automatically applying a dependency-heavy auto-config to an MVC slice just because of a "missing bean" can inadvertently initialize out-of-scope infrastructure.

## 10. Major Trap: Explicit `@ComponentScan` Breaks Slicing

### 10.1. Why Does a Project Have `@WebMvcTest` Yet Still Load Every Service?

By default, Spring Boot places an appropriate component scan inside `@SpringBootApplication` with **`TypeExcludeFilter`** so test slices exclude out-of-scope components.

If you add a separate `@ComponentScan` directly on the main application class:

```java
@SpringBootApplication
@ComponentScan({
    "com.example.application",
    "com.example.shared"
})
public class Application {
}
```

you can **bypass the default exclude mechanism declared via meta-annotation** on `@SpringBootApplication`, causing the scan to pull in components slices try to omit. Typical symptoms:

- `@DataJpaTest` suddenly loads services, web configs, or schedulers.
- `@WebMvcTest` drags in unexpected service/repository graphs.
- Tests fail on datasources, remote clients, or out-of-scope beans.
- Context startup time spikes, losing the lightweight nature of slices.

The Spring Boot docs warn directly against this scenario. This is **not** a bug of `includeFilters` being too broad inside the test itself; the root cause is the **custom scan directive on the main application**.

### 10.2. Preferred Fix

If you only need to widen scanned packages for **components**, consider `@SpringBootApplication`'s attributes:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.application",
        "com.example.shared"
    }
)
public class Application {
}
```

**Illustrative snippet**, not a complete class. Using the `scanBasePackages` alias avoids replacing the scan with a separate `@ComponentScan` annotation and preserves Boot's meta-annotated filter mechanism.

You can also use `scanBasePackageClasses = {MarkerInApp.class, MarkerInShared.class}` for type-safe package selection that resists package-rename refactoring. The marker classes must exist.

**Important:** `scanBasePackages` only adjusts application component scanning; it **does not automatically expand JPA entity scanning or Spring Data repository scanning**. When those mechanisms need external packages, configure `@EntityScan`/`@EnableJpaRepositories` per application design rather than treating component-scan attributes as a universal fix.

### 10.3. What If a Separate `@ComponentScan` Is Truly Required?

Placing the custom scan on a separate `@Configuration` class loaded in the right place usually avoids breaking default filters on the main class. If you must still place `@ComponentScan` directly and expect slices to work, **re-register `TypeExcludeFilter` properly** according to Boot's docs.

Spring Boot provides the `TypeFilter` named `org.springframework.boot.context.TypeExcludeFilter`, used with `FilterType.CUSTOM` on `@ComponentScan`. Do not blindly copy/omit extra classes from an old version's snippet; check the Javadoc for your Boot branch and re-test slice scope.

To test independently of a complex main application config, you can also specify the test bootstrap source via a dedicated `@SpringBootConfiguration` class for the appropriate test context, rather than letting the framework discover a main class laden with integration annotations.

### 10.4. `@SpringBootApplication` Root Package Also Affects Scope

Spring Boot finds the primary configuration by walking upward from the test's package to the package containing `@SpringBootApplication` or `@SpringBootConfiguration`. If a test sits outside that package hierarchy, configuration discovery can fail.

Furthermore, a component outside the **base package** might **not be considered** even if the type filter matches. For example, `includeFilters = classes=RemoteFormatter.class` will not scan `com.some.other.module` unless that package already sits within the app/test component scan area.

The fix in that situation is usually `@Import(RemoteFormatter.class)`, placing valid scan config in the right spot, or adjusting the root package per design. Do not complicate regex filters to solve a package-scope problem.

## 11. Differences Between Spring Boot 3.x and 4.x

Annotations may retain similar meanings while **packages and starters change across major versions**.

### 11.1. Boot 3.x

Common imports:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
```

Common dependencies: `spring-boot-starter-web`, `spring-boot-starter-test`; add `spring-boot-starter-data-jpa` and a database when testing JPA.

### 11.2. Boot 4.x

Per Boot 4 Javadoc, MVC slice packages were reorganized:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

Test starters are split by specialty in the modular architecture, such as `spring-boot-starter-webmvc-test` and `spring-boot-starter-data-jpa-test` in the Boot 4 ecosystem. Projects must pick dependencies compatible with their BOM/version.

The attributes `controllers`, `includeFilters`, `excludeFilters`, and `useDefaultFilters` still appear in Boot 4 Javadoc, though default included MVC components/auto-configurations can evolve; do not copy one major version's default-includes list and treat it as a permanent contract.

### 11.3. Notes on JUnit, Java, and Security

- Boot 3 uses Java 17 as a suitable baseline for this lesson; Boot 4 requires the JVM baseline specified in its release notes.
- `@WebMvcTest` integrates Spring Test/JUnit Jupiter automatically with the right dependencies; no manual `@ExtendWith(SpringExtension.class)` is needed in examples.
- When Spring Security is on the classpath, the MVC slice can load security filters. An unauthenticated test may hit 401/403 before reaching the controller.
- Do not work around it by disabling all filters if the test aims to verify security. Use test security support, mock users, and CSRF matching endpoint policy.

## 12. Notes on Slices Other Than MVC

### 12.1. `@DataJpaTest`

In a JPA slice, Spring Boot restricts auto-configurations and loads relevant JPA components. You can customize `includeFilters/excludeFilters`, though **entities and repositories are not handled purely by component-scan annotations**.

Illustrative configuration example:

```java
@DataJpaTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = PricingPolicy.class
    )
)
class PricingRepositoryTest {
}
```

This is a **snippet**, assuming `PricingPolicy` is a component inside the scan area and the test already has valid JPA dependencies, entities/repositories/database. It will not compile without those classes. Including `PricingPolicy` does not bring the entire REST application context along.

In JPA tests, focus on query/transaction/constraint/persistence behavior. If you need a business-logic service together with a real repository, `@Import(PricingPolicy.class)` or an appropriate integration test is often clearer than filters.

### 12.2. `@JsonTest`

This slice targets JSON serializers/deserializers and supported JSON components. It does not scan controllers or ordinary services by default. When adding a custom Jackson module or serializer, you can usually `@Import` the specific config or use the version-appropriate mechanism. An include filter affects only scan candidates and does not start an MVC HTTP pipeline.

### 12.3. `@RestClientTest` / Client Slices

HTTP client test slices have their own auto-configuration and scanning scopes, distinct from MVC server slices. Type filtering can help include a small collaborator, but do not turn a client test into a web-server integration test via reckless imports. For `RestClient` or `RestTemplate`, use the mock server/test utilities matching your Boot version.

### 12.4. Do Not Stack Multiple `@...Test` Slices on the Same Class

Spring Boot does not support treating `@WebMvcTest` + `@DataJpaTest` as a way to "merge" two slices. Bootstrappers, context types, auto-configs, and `TypeExcludeFilter`s can conflict.

When two infrastructure layers are needed, pick one primary slice and add the required infrastructure **deliberately** per Spring Boot guidance, or use `@SpringBootTest`. "Adding two annotations" does not construct a valid combined slice.

## 13. How to Verify Scan Scope Instead of Guessing

### 13.1. Assert Bean Names/Types on the Context

In a test with Spring `ApplicationContext context`:

```java
assertThat(context.getBeanNamesForType(FormatterService.class))
        .hasSize(1);

assertThat(context.getBeanNamesForType(AuditHeaderFilter.class))
        .isEmpty();
```

These assertions are **excerpted from the complete test**; they prove whether a bean type exists in the context.

Using `getBeanNamesForType(Type.class)` is more convenient than comparing raw bean names when Spring applies proxy/bean naming conventions. For factory beans or lazy beans, semantics may differ from ordinary cases; observe according to your goal.

### 13.2. Assert HTTP Behavior, Not Just Bean Existence

Having a `FormatterService` bean present does not prove the controller uses it. A MockMvc request:

```java
mvc.perform(get("/api/echo/hello"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.value").value("HELLO"));
```

provides evidence from request → controller → real service → JSON response. Combining both assertion layers (bean scope and behavior) ensures include filters carry real educational value.

### 13.3. Debug with Component and Auto-Configuration Reports

If context loading fails, do not tweak filters blindly. Verify:

1. Does the class to include have the right stereotype/implement the expected type?
2. Is its package inside the scan roots?
3. What are `useDefaultFilters` and `controllers` set to?
4. Is the class blocked by a higher-precedence custom exclude?
5. Was the bean created via scanning or via `@Import`/`@Bean`/auto-configuration?
6. Does the main class have an explicit `@ComponentScan` breaking slice exclusions?
7. Do profiles/`@ConditionalOnProperty`/`@ConditionalOnClass` suppress the bean?
8. Is a dependency of the included bean missing?
9. Are Spring Security filters blocking the request, making you think the controller is missing?
10. Do JUnit/test starters and the Boot major version match your imports?

Check Spring Boot's condition evaluation report when investigating **auto-configuration**, and inspect context bean definitions when investigating **component scanning**. The two diagnostic tools answer different questions.

## 14. Common Mistakes and Fixes

| Symptom | Why it can happen | How to fix |
|---|---|---|
| `NoSuchBeanDefinitionException` for `@Service` in `@WebMvcTest` | MVC slice intentionally skips regular services | Mock or import the service; use an include filter when testing scanning specifically |
| Include filter names the right class, yet bean is still absent | Package outside scan root, conditional bean, or not a scan candidate | Verify package/annotations/conditions; consider `@Import` |
| Exclude filter fails to omit the bean | Bean created by `@Bean`/`@Import`/auto-config, not scan candidate | Fix the actual bean source; do not misuse `excludeFilters` |
| Servlet filter still in context when using `addFilters=false` | That option only affects MockMvc filter registration | Use `excludeFilters` if the goal is not scanning/registering the bean |
| Other controllers still get loaded | `controllers` omitted or custom scan config broke the slice | Specify `controllers`; check for explicit `@ComponentScan` |
| Security returns 401/403 | Filter chain or CSRF, not necessarily a missing controller | Configure auth/CSRF per policy |
| `useDefaultFilters=false` leaves tests missing advice/converters | Disabled the entire default candidate group | Keep defaults or include/import needed components |
| `excludeAutoConfiguration` does not remove a service | Affects only auto-configuration classes | Use the right mechanism for component-scanned beans |
| `@DataJpaTest` unexpectedly scans web/services | Main app uses explicit `@ComponentScan`, dropping `TypeExcludeFilter` | Move scan to an appropriate config, use `scanBasePackages` alias, or register `TypeExcludeFilter` |
| `WebMvcConfigurer` bean in `@Configuration` is not loaded | Slice excludes configuration classes from scan even if `@Bean` returns `WebMvcConfigurer` | Use `@Import(MyWebConfig.class)` when genuinely needed |
| Boot 3 → 4 upgrade breaks `WebMvcTest` imports | MVC test packages/modules changed | Pick the right Boot 4 imports and starters |
| MVC slice demands a database | Overly broad imports/includes or broken scan | Narrow scope, mock dependencies, split tests appropriately |
| `@Mock` present, yet controller does not receive it | Plain Mockito field does not override Spring beans | Use the framework-supported bean override annotation |
| Tests pass individually, fail as a suite | Context cache/global state/fixtures or unexpected shared configuration | Reset state and isolate contexts as needed; limit `@DirtiesContext` |
| All tests filtered out, none run | Wrong Gradle/Maven test selection, Surefire, or JUnit engine | Check test task/report and class names |

### 14.1. Distinguish Two "No Bean" Situations

- **Bean intentionally unscanned:** e.g., `BillingService` in an MVC slice; this is desired behavior.
- **Missing bean blocking context startup:** e.g., controller requires `FormatterService` and you have not included/imported/mocked it.

The second situation requires resolving the dependency per the test goal, not widening scanning across the whole app to silence errors quickly. A passing test after including all services may no longer be a useful MVC slice.

### 14.2. Do Not Use `useDefaultFilters=false` to Fix a Wrong-Layer Problem

If the issue is an explicit `@ComponentScan` on the main application class, turning off default filters on the test can cause more dependency failures without fixing the scan source. If the issue is auto-configuration, tweaking `excludeFilters` on component scanning will not help either. Identify **which layer is causing the problem**.

### 14.3. If a Test Is No Longer Small, Re-Evaluate

An MVC test forced to include 12 services, 4 repositories, 3 integration clients, and Redis configuration no longer isolates the web layer. Reorganize tests:

- A group of `@WebMvcTest` tests verifying JSON, validation, routes, and error handling with mocked collaborators.
- A group of unit tests verifying business logic.
- A few `@SpringBootTest` integration tests verifying wiring across layers.
- Real HTTP tests where network/server behavior needs verification.

This is not reducing test coverage; this is **distributing contract verification to the proper layer**.

## 15. Practice Exercises

### Exercise A — Include Exactly One Service

Given `ProductController` depending on `ProductFormatter`, declared `@Service` in the application package. You want to run real formatter logic inside the MVC slice. Which configuration fits?

```java
@WebMvcTest(
    controllers = ProductController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductFormatter.class
    )
)
class ProductSliceTest {
}
```

**Answer:** the configuration above works (snippet, assuming existing classes) if the formatter has satisfied dependencies and sits inside scan scope. `@Import(ProductFormatter.class)` can also be a clean option if you do not need to test scanning. If the formatter relies on I/O systems, it usually does not need to run for real in an MVC slice.

### Exercise B — Exclude Filter vs. Disabling the Filter Chain?

You have `@Component AuditHeaderFilter` and want to prove **the bean does not exist in the MVC slice**. Do you choose:

1. `@AutoConfigureMockMvc(addFilters=false)`; or
2. `excludeFilters = @ComponentScan.Filter(type=FilterType.ASSIGNABLE_TYPE, classes=AuditHeaderFilter.class)`?

**Answer:** choose **(2)** and assert bean absence with `getBeanNamesForType(...)`. Option (1) only affects registering filters onto MockMvc and does not prove the class was skipped by scanning.

### Exercise C — "Service Still Appears" Despite MVC Slice

The main class has:

```java
@SpringBootApplication
@ComponentScan({"com.example.api", "com.example.business"})
class Application {
}
```

Why can `@WebMvcTest` load services unexpectedly?

**Answer:** an explicit `@ComponentScan` can disable the default filters `@SpringBootApplication`'s meta-annotation supplies for slicing. Move custom scan configs to an appropriate place, use `scanBasePackages`/`scanBasePackageClasses` aliases if the goal is component base packages, or ensure `TypeExcludeFilter` is registered properly when a custom scan is unavoidable.

### Exercise D — Bean Not Created via Scanning

A `@WebMvcTest` test has `@Import(MyWebConfiguration.class)`, containing `@Bean CacheClient cacheClient()`. You add an exclude filter for `CacheClient.class`, yet the bean remains present. Why?

**Answer:** the bean was created by a `@Bean` method in an **imported** configuration, not discovered as a candidate via component scanning. Fix the imported configuration, split configs, or use an appropriate test bean override; do not expect scan exclude filters to remove beans from another source.

### Exercise E — Pick the Right Test Area

You need to test repository SQL queries with Hibernate and a real database; should you widen `@WebMvcTest` with an include filter for the repository?

**Answer:** no. You need `@DataJpaTest` with appropriate DB data/infrastructure or a JPA integration test. `@WebMvcTest` is not the way to run repository integration logic via an include filter.

### Review Checklist

- [ ] Identified the exact slice annotation and default included component types of the active version.
- [ ] Distinguished `controllers`, `useDefaultFilters`, `includeFilters`, and `excludeFilters`.
- [ ] Every custom filter uses the right `FilterType`, with matching `classes`/`pattern`.
- [ ] Component scanning/packages actually cover the class you want to include.
- [ ] Understood whether a bean originates from scanning, `@Bean`, `@Import`, or auto-configuration.
- [ ] Not using `excludeFilters` to disable arbitrary auto-configurations.
- [ ] Not using `@AutoConfigureMockMvc(addFilters=false)` as a substitute for component-scan exclusions.
- [ ] For MVC tests, service dependencies are mocked/imported/included according to the goal.
- [ ] For JPA tests, understood that entity/repository registration and JPA infrastructure are not ordinary component scanning.
- [ ] Main `@SpringBootApplication` does not carry an explicit scan breaking slice filters, or handles it properly.
- [ ] Each slice test stays small and focused, avoiding out-of-scope DB/remote configs.
- [ ] Verified bean presence/absence in the context alongside appropriate HTTP behavior.
- [ ] Boot 3/4 version, test starters, and imports are aligned.
- [ ] Spring Security/CSRF are handled properly when in scope.
- [ ] Ran exact JUnit classes via Gradle/Maven Wrapper and verified actual executed test counts.
- [ ] Tests do not rely on execution order, global mutable state, or uncontrolled external environments.

## 16. Conclusion

**`includeFilters` and `excludeFilters` are tools for fine-tuning a test slice's component scanning, not universal switches to turn every bean on or off.** `@WebMvcTest` has its own MVC component set; `@DataJpaTest` uses dedicated JPA mechanisms; `@Import`, `@Bean`, and auto-configuration register beans through other paths.

A good MVC slice normally only needs to pick controllers, add a few deliberate dependencies, and verify the HTTP contract. When real service logic must run, a precise `includeFilters` entry can help. When a `Filter` falls outside the test's contract, `excludeFilters` can omit it from component scanning. Still, preserve the distinction between **excluding a bean from the context** and **omitting filters from the MockMvc chain**.

Finally, investigate explicit `@ComponentScan` annotations on the main application class whenever a slice test unexpectedly scans the whole application. Mastering **package scope, default includes, custom filters, and bean registration sources** keeps tests small, clear, stable, and easy to debug.

## Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): slice annotations, MVC/JPA scope, user configuration, `@ComponentScan`, and `TypeExcludeFilter`.
- [Spring Boot 3.5 — WebMvcTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html): `controllers`, `includeFilters`, `excludeFilters`, `useDefaultFilters`.
- [Spring Boot 3.5 — DataJpaTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): JPA slice limits and filter options.
- [Spring Boot 4.0 — WebMvcTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/WebMvcTest.html): new MVC test package and component scope.
- [Spring Boot 4.0 — DataJpaTest Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/jpa/test/autoconfigure/DataJpaTest.html): new JPA test package and filter options.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `ComponentScan`, `FilterType` options, and candidate discovery principles.
- [Spring Boot — TypeExcludeFilter Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/TypeExcludeFilter.html): role in preserving slice scope during component scanning.
