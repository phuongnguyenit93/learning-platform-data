# TypeExcludeFilter, Component Scanning, and Why Out-of-Scope Beans Appear

One of the major benefits of a **test slice** in Spring Boot is building only the portion of the `ApplicationContext` needed for a given kind of test. For instance, `@WebMvcTest` targets controllers and Spring MVC infrastructure, rather than every service, repository, scheduler, or HTTP client in the application. Yet sometimes a test annotated with `@WebMvcTest` or `@DataJpaTest` still instantiates "out-of-scope" beans: business services, network connection configurations, background jobs, or an unwanted datasource. As a result, the context starts slowly, fails due to missing dependencies, calls external services, breaks because of production configuration, or loses isolation.

A very easy-to-miss cause is **customized component scanning that prevents slice filters from being applied as expected**. Spring Boot uses `TypeExcludeFilter` as the bridge between test slice configuration and component scanning. However, this filter **is not a firewall against every way of registering beans**: `@Import`, `@Bean` methods, auto-configuration, bean overrides, or another scan directive can still bring beans into the context.

This lesson explains the mechanism, symptoms, debugging steps, and deliberate fixes, with runnable examples in **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5**. If you use Boot 4.x, some packages and the list of MVC components have changed; consult the API documentation for your **exact version** rather than copying the example imports verbatim.

**Learning outcomes:** after this lesson you will be able to identify how a bean was registered, understand the role of `TypeExcludeFilter`, distinguish "valid beans in a slice" from "unexpected beans", fix `@ComponentScan` issues, choose `@Import`/`@MockitoBean` purposefully, and verify that a test slice genuinely isolates unrelated parts.

## 1. What Is a "Test Slice," and What Is It Not?

Spring Boot provides specialized test annotations to load **a slice** of the application context along with an appropriate set of auto-configurations. Typically:

| Annotation | Goal | Core components | Things usually not needed |
|---|---|---|---|
| `@WebMvcTest(Controller.class)` | Test HTTP mapping, JSON, validation, MVC/security filters per config | Selected controller, controller advice, allowed MVC parts, `MockMvc` | Business services, repositories, message consumers, scheduled jobs |
| `@DataJpaTest` | Test entity mapping, JPA repositories, queries, DB constraints | JPA/repositories/data source and required persistence infrastructure | REST controllers, unrelated application services |
| `@JsonTest` | Test JSON serialization/deserialization | Related JSON mapper/modules/testers | Full web server, services, and database |
| `@RestClientTest` | Test REST client adapters | HTTP client, serialization, and suitable mock server | Full server/API controllers, unrelated domain workflows |
| `@SpringBootTest` | Test broad/integrated Spring Boot context | Depends on application and `webEnvironment` | **Not a slice**; can load many components |

Slices improve speed and sharpen verification scope, but they do not mean **only a single bean** exists. A valid `@WebMvcTest` can still load `@ControllerAdvice`, `Filter`, `WebMvcConfigurer`, `HandlerMethodArgumentResolver`, or converter/security auto-configuration. These beans **can belong to the MVC slice** and are not "leaks."

Conversely, if `PaymentReconciliationJob` or `InventorySyncService` suddenly gets created even though the test only aims to check a JSON controller, you need to investigate how the bean was registered.

**First debugging question:** is that bean actually allowed in the slice, or does it truly sit outside the boundary the test intends to verify?

## 2. Component Scanning in a Normal Application

Spring Framework discovers many beans from the classpath via component scanning. Commonly inspected stereotypes include `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration`, and custom annotations with matching meta-annotations.

For example:

```java
package com.example.sliceaudit;

import org.springframework.stereotype.Component;

@Component
public class ExternalBillingClient {
    public String preview(long reportId) {
        return "external:" + reportId;
    }
}
```

In a full application context whose component scan covers this package, `ExternalBillingClient` becomes a bean. **There are no network calls** in this example code: the class name only represents an infrastructure adapter so the test does not accidentally call a real service.

`@SpringBootApplication` combines three main capabilities: `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. If you place the application class in a root package such as `com.example.sliceaudit`, Spring Boot scans that package and its subpackages by default.

Common syntax:

```java
@SpringBootApplication
public class SliceAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceAuditApplication.class, args);
    }
}
```

This is an **illustrative header snippet**; the runnable Java file in section 9 has the full package and imports.

Key point: **component scanning** is one **bean registration mechanism**, not the only one. `@Bean` methods in imported configuration classes, auto-configuration, `ImportBeanDefinitionRegistrar`, or Spring TestContext bean overrides can create beans without the implementation class being discovered by component scanning.

## 3. What Is `TypeExcludeFilter`?

`org.springframework.boot.context.TypeExcludeFilter` is the base for **excluding certain candidate types during Boot's component scanning**. In the context of test slices, specialized filters (for example, `WebMvcTypeExcludeFilter`) use information from the test annotation to decide which components qualify.

Think of it as a mechanism that attaches **type-exclusion rules** from the test slice to the component scanning process:

```text
JUnit / @WebMvcTest(ReportController.class)
              |
              v
Spring Boot test bootstrapper
              |
              +--> slice metadata + type-exclude filters
              |
              v
@SpringBootApplication component scanning
              |
              +--> TypeExcludeFilter  ---> evaluate scan candidates
              |                             |
              |                       MVC-allowed type?
              |                         /       \
              |                       yes       no
              |                        |         |
              |                     register   exclude
              |
              v
ApplicationContext built with the slice's auto-configuration
```

The diagram above is a **conceptual** model, not the exact callback sequence or stack trace for every version. Filtering also depends on annotations, include/exclude filters, and bootstrap data.

Mandatory distinctions:

- `TypeExcludeFilter` operates **at the component-scanning candidate level**; it does not automatically remove beans registered from other sources.
- `WebMvcTypeExcludeFilter` is a specific filter for `@WebMvcTest` in Spring Boot 3.5, tied to the set of permitted MVC components.
- `@DataJpaTest` has a filter tailored for the data slice; it does not use an MVC list to determine entities/repositories.
- `@WebMvcTest` also **limits which auto-configurations** are applied; that is a separate axis from component scanning.
- A test slice does not achieve isolation solely through `TypeExcludeFilter`; it requires **the right bootstrapper, the right scanning, and the right auto-configuration**.

In Spring Boot 3.5, the `WebMvcTypeExcludeFilter` Javadoc describes it as the filter for `@WebMvcTest`. Even though it runs during scanning, you should not instantiate the filter manually in a regular business test.

## 4. How Does `@SpringBootApplication` Preserve Slice Filtering?

`@SpringBootApplication` is not merely shorthand for a bare `@ComponentScan`. Spring Boot configures exclude filters for Boot's own mechanisms, including `TypeExcludeFilter`; many release lines also include `AutoConfigurationExcludeFilter` to prevent auto-configuration classes from being picked up accidentally by component scanning.

You can visualize the idea as:

```java
// Illustrates the annotation concept, NOT Boot's actual definition.
@ComponentScan(excludeFilters = {
    @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = TypeExcludeFilter.class),
    @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = AutoConfigurationExcludeFilter.class)
})
```

**Do not copy this annotation snippet** into your application when you just use `@SpringBootApplication` normally. Filter types and source details should be verified against your installed Spring Boot version; the snippet above represents the mechanism in the 3.x line.

Precisely because the default scan includes the proper exclude filters, when `@WebMvcTest` bootstraps a context, the slice filter can restrict `@Service`, `@Repository`, or non-MVC `@Component` beans. Even though the application class is still located to supply the root configuration, the test context does not have to load all production beans.

## 5. Biggest Trap: Declaring `@ComponentScan` Directly on the Application Class

A seemingly harmless change:

```java
// ANTI-PATTERN: do not replace the demo project's root class with this code.
@SpringBootApplication
@ComponentScan("com.example.sliceaudit")
public class SliceAuditApplication {
}
```

The author wanted to be explicit about the base package, but a `@ComponentScan` **declared directly** on the class can take precedence over `@SpringBootApplication`'s meta-annotated scan, causing Boot's default exclude filters **not to be applied to this direct scan directive**. The Spring Boot reference explicitly warns that test slices may begin scanning out-of-scope components or production configurations.

Common consequences:

1. A `@WebMvcTest(ReportController.class)` test picks up `ReportService`, `ExternalBillingClient`, or other non-MVC components.
2. A `@DataJpaTest` test encounters services, schedulers, or configurations unrelated to JPA.
3. Out-of-scope beans have constructors or `@Bean` methods requiring production properties, queues, or network clients, causing the context to fail before any test method runs.
4. The suite suddenly runs slower, accumulates many cache entries, and exhibits hard-to-explain side effects.

**The problem is not the package name itself.** The problem is that the new scan directive **does not carry the exclusion mechanism** Boot places on the default scan. Matching the root package name identically does not make it equivalent to the default configuration.

### 5.1. Preferred Fix: Remove Unnecessary Direct Scans

If the application class is already in the root package above its subpackages, simply use:

```java
@SpringBootApplication
public class SliceAuditApplication {
}
```

This is an illustrative snippet; see section 9 for complete code. This preserves the default scan configuration and is the simplest, easiest approach to review.

### 5.2. If You Only Need to Change the Base Package, Use Boot's Alias

```java
@SpringBootApplication(scanBasePackages = "com.example.sliceaudit")
public class SliceAuditApplication {
}
```

`scanBasePackages` is an alias for the component-scan attribute on `@SpringBootApplication`, so it preserves the filters Boot configured on the composed annotation. For type safety, use `scanBasePackageClasses`. Note: these aliases **do not automatically widen `@EntityScan` or Spring Data repository scanning**; those are separate mechanisms.

### 5.3. If a Direct `@ComponentScan` Is Truly Required

When you genuinely need advanced include/exclude filters, you can re-register Boot's filters on the custom scan:

```java
// Instructional pattern for Spring Boot 3.x: use only with good reason.
@SpringBootApplication
@ComponentScan(
    basePackages = "com.example.sliceaudit",
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class)
    })
public class SliceAuditApplication {
}
```

This snippet **is not a standalone runnable file**: it requires imports from `org.springframework.boot.autoconfigure`, `org.springframework.boot.context`, and `org.springframework.context.annotation`, plus a `main` method. Verify exact filter names against your version; the **safest, lowest-risk option is avoiding custom scan directives unless necessary**.

Moreover, adding filters to **one `@ComponentScan`** does not automatically fix **other `@ComponentScan` annotations** coming from later imported configurations. When multiple scan sources exist, inspect each one.

## 6. Distinguishing "Scan Leaked a Bean" from "Bean Registered Explicitly"

This is the most important diagnostic step. An out-of-scope bean can appear **without having been picked up by component scanning at all**.

| Entry path into context | Candidate of component scan? | Why might the slice filter not block it? |
|---|---|---|
| `@Service`/`@Component` scanned by default scan | Yes | Slice filter normally has a chance to exclude it if the scan registered the filter properly |
| `@Service` scanned by a separate `@ComponentScan` | Yes, but from a different scan | That scan directive may lack `TypeExcludeFilter` |
| `@Import(SomeService.class)` | Explicit registration | Not a natural result of the component-scan filter |
| `@Import(WholeConfig.class)` | Configuration class imported directly | `@Bean` methods inside may run even if the beans are outside the slice |
| `@Bean` inside a loaded configuration | Bean created by factory method | Component-scan filters do not inspect each `@Bean` product as a component candidate |
| Auto-configuration selected by Boot | Auto-configuration mechanism | Slices restrict auto-configuration separately, not only via `TypeExcludeFilter` |
| `@MockitoBean` in test (Spring 6.2+) | Bean override or mock creation | Mock may exist because the test asked for it, not because of scanning |
| Imported `@TestConfiguration` | Test-specific config | Bean intentionally added; review the import scope |
| `@Enable...` or registrar | Framework registration mechanism | Can register beans outside regular scanning |

Therefore, **"the context has bean X" does not by itself prove `TypeExcludeFilter` is broken**. You must determine **the registration path**.

For example, in `@WebMvcTest`, a field:

```java
@MockitoBean
ReportService reportService;
```

creates a mock `ReportService` in the context because the controller needs that dependency. This is an **intentional** result of the test. It **does not mean the real `@Service` slipped past component scanning**. To check, inspect `Mockito.mockingDetails(reportService).isMock()` and identify beans not created by mocks or imports.

## 7. Which Beans Are Valid in a `@WebMvcTest`?

In Spring Boot 3.5, `@WebMvcTest` auto-configures Spring MVC and limits scanned beans to a set serving MVC, which may include:

- `@Controller`, `@ControllerAdvice`;
- `@JsonComponent` and JSON-related components supported by that version;
- `Converter`, `GenericConverter`;
- Servlet `Filter`;
- `HandlerInterceptor`, `WebMvcConfigurer`, `WebMvcRegistrations`;
- `HandlerMethodArgumentResolver`;
- Additional components brought in by test configuration and appropriate auto-configuration.

If Spring Security is on the classpath, the security filter chain and related security beans may appear depending on the test setup. **Do not remove/disable security just to make the slice have "fewer beans"** if the API needs protection. Use test security setup/`@WithMockUser` or CSRF fixtures matching your version/dependencies and contract.

A subtle point: a bean whose class is named `PaymentAuthFilter` but implements servlet `Filter` can be treated as **MVC infrastructure** and included by rule. The name "Payment" does not automatically make it invalid. If it has expensive dependencies or side effects, that may be a filter/design issue: extract non-MVC logic to a collaborator and mock/provide fixtures at the proper boundary.

### 7.1. `@WebMvcTest(ReportController.class)` Still Needs Controller Dependencies

Even when the controller is selected, its service is **typically not auto-scanned**, so the context may throw `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` if the controller constructor requires the service.

Typical solution:

```java
@WebMvcTest(ReportController.class)
class ReportControllerWebTest {
    @MockitoBean
    ReportService reportService;
}
```

This is a **snippet**; the full test is in section 10. Boot 3.3 and older branches use `@MockBean`; Boot 3.4+/Spring Framework 6.2+ recommend `@MockitoBean`. Do not switch to `@SpringBootTest` just to "fix" a missing dependency when what you actually want is an MVC slice.

## 8. Why Can `@DataJpaTest` See Services and Schedulers?

`@DataJpaTest` targets persistence testing. It typically uses JPA-related auto-configuration, repositories, entity mapping, and an appropriate test database; many tests have transactional rollback by default.

If a production service or job appears, possible reasons include:

1. A direct `@ComponentScan` on the application root disables the slice's default filter.
2. An out-of-scope `@Configuration` is imported, bringing another `@ComponentScan` or `@Bean` definitions with it.
3. `@EnableJpaRepositories`, `@EntityScan`, an added auto-configuration, or a framework registrar brings in extra components through its own mechanism.
4. The test manually imports services/configs or sets an overly broad test configuration.
5. The test actually uses `@SpringBootTest` or a composed annotation that adds full bootstrapping.

**Entities and Spring Data repositories are not just ordinary `@Component` classes.** JPA entities, repository interfaces, entity scanning, and repository registration have their own mechanisms. Do not expect tweaking `TypeExcludeFilter` to fix every entity/repository package issue automatically.

Example of a configuration you should not import just to test a JPA repository:

```java
// ANTI-PATTERN FOR A NARROW SLICE: loads the entire application configuration.
@DataJpaTest
@Import(EntireApplicationInfrastructureConfiguration.class)
class OrderRepositoryTest {
}
```

This is a non-standalone snippet. The imported configuration might create HTTP clients, queue consumers, or schedulers; those beans appear **because they were imported**, not necessarily because default component scanning failed.

## 9. Runnable Example: Spring Boot 3.5.x Project, Java 17+

We will build a very small application to observe three states:

1. **Full context** with regular services and adapters.
2. **Proper MVC slice** with the real controller, the service as a **test-requested Mockito mock**, and **no non-MVC adapter**.
3. **MVC slice importing extra configuration** with a non-MVC bean added **intentionally** — proving `TypeExcludeFilter` does not block every form of registration.

The example uses the class/package name `com.example.sliceaudit`. If copying into another project, rename the package consistently throughout.

### 9.1. Directory Tree

```text
src/main/java/com/example/sliceaudit/
    SliceAuditApplication.java
    ExternalBillingClient.java
    ReportService.java
    ReportController.java

src/test/java/com/example/sliceaudit/
    ReportControllerWebTest.java
    FullContextControlTest.java
    ExtraSliceConfig.java
    ImportedExtraBeanWebTest.java
```

These files work with Spring Boot 3.5.x + `spring-boot-starter-web` + `spring-boot-starter-test`, requiring no datasource or external network.

### 9.2. Application Root Keeping Default Scan

**`src/main/java/com/example/sliceaudit/SliceAuditApplication.java`**

```java
package com.example.sliceaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceAuditApplication.class, args);
    }
}
```

**Do not declare `@ComponentScan` directly** on the application class. With the root package already right, this is the minimal configuration and stays compatible with test slices.

### 9.3. Non-MVC Adapter: No Network Call in Demo

**`src/main/java/com/example/sliceaudit/ExternalBillingClient.java`**

```java
package com.example.sliceaudit;

import org.springframework.stereotype.Component;

@Component
public class ExternalBillingClient {

    public String preview(long id) {
        return "external:" + id;
    }
}
```

Despite being named a client, the demo implementation just returns a string without opening a connection. In a real app, an adapter might use HTTP/SDKs; slice tests should avoid instantiating unrelated collaborators.

### 9.4. Business Service Depending on the Adapter

**`src/main/java/com/example/sliceaudit/ReportService.java`**

```java
package com.example.sliceaudit;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ExternalBillingClient billingClient;

    public ReportService(ExternalBillingClient billingClient) {
        this.billingClient = billingClient;
    }

    public String describe(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        return billingClient.preview(id).toUpperCase(Locale.ROOT);
    }
}
```

When the service is created in a **full context**, it needs the real `ExternalBillingClient`. In an MVC slice, this service is **not a component that needs scanning**; we only need to mock the collaborator at the controller boundary.

### 9.5. REST Controller and Response Record

**`src/main/java/com/example/sliceaudit/ReportController.java`**

```java
package com.example.sliceaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    public ReportView get(@PathVariable long id) {
        return new ReportView(id, reportService.describe(id));
    }

    public record ReportView(long id, String description) {
    }
}
```

`ReportController` is selected by `@WebMvcTest`; JSON serialization of the `record` is supported by Jackson in Spring Boot 3.5 with starter-web. In a full context, the controller invokes the real service.

## 10. Standard MVC Slice Test: Checking HTTP and Proving the Adapter Was Not Scanned

**`src/test/java/com/example/sliceaudit/ReportControllerWebTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
class ReportControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReportService reportService;

    @Test
    void keepsMvcBoundaryAndExcludesUnrelatedAdapter()
            throws Exception {
        when(reportService.describe(7L)).thenReturn("fixture-7");

        mvc.perform(get("/api/reports/7"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.id").value(7),
                        jsonPath("$.description").value("fixture-7"));

        verify(reportService).describe(7L);

        assertEquals(0, context.getBeanNamesForType(
                ExternalBillingClient.class).length);
        assertTrue(mockingDetails(
                context.getBean(ReportService.class)).isMock());
    }
}
```

**Three things proven separately:**

- The real controller/MVC maps `GET /api/reports/7` and serializes JSON with `id=7`, `description="fixture-7"`.
- `ExternalBillingClient` **is not instantiated as a bean** in this MVC slice; there is no reason to exercise a non-MVC adapter in an HTTP mapping test.
- `ReportService` **has a bean in the context**, but it is a **Mockito mock added by `@MockitoBean`**, not the real `@Service` picked up by component scanning. `mockingDetails(...).isMock()` prevents false conclusions when reviewing the bean list.

`@WebMvcTest` normally auto-configures `MockMvc`; no real HTTP server needs to start. The test does not check `ReportService.describe` logic — that belongs to the service's unit/integration tests.

**If the project enables Spring Security**, requests may need a principal/authorization depending on policy. The runnable example assumes the dependencies in section 16 without adding `spring-boot-starter-security`. Do not disable security in real product tests when access control is part of the contract.

## 11. Control Comparison: Full Context with Real Service and Adapter

**`src/test/java/com/example/sliceaudit/FullContextControlTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = SliceAuditApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullContextControlTest {

    @Autowired
    ReportService service;

    @Autowired
    ExternalBillingClient billingClient;

    @Test
    void createsRegularComponentsInFullContext() {
        assertEquals("external:7", billingClient.preview(7));
        assertEquals("EXTERNAL:7", service.describe(7));
    }
}
```

This test is not an MVC slice. It confirms that the full application context registers the service and adapter via default scanning.

**Key takeaway:** given the exact same production classes, `@WebMvcTest` and `@SpringBootTest` deliberately yield **two different contexts**. The service not appearing as a real implementation in the slice **is not a bug**, and the service appearing in the full context is not "scope leakage."

If tests are failing because the application context is too heavy, pick the test type suited to what needs verification instead of forcing everything to use `@SpringBootTest`.

## 12. Second Comparison: `@Import` Validly Creates an Out-of-Scan Bean

We intentionally register a non-MVC bean using `@Import`. It is not a `@Component`, and by itself it does not belong to MVC component scanning.

**`src/test/java/com/example/sliceaudit/ExtraSliceConfig.java`**

```java
package com.example.sliceaudit;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class ExtraSliceConfig {

    @Bean
    ExtraBackgroundJob extraBackgroundJob() {
        return new ExtraBackgroundJob();
    }
}

class ExtraBackgroundJob {
    String mode() {
        return "intentionally-imported";
    }
}
```

`ExtraBackgroundJob` is a package-private class purely for learning; its `mode()` method has no side effects. `@TestConfiguration` lives in test sources and **does not need scanning** to be used when `@Import`ed.

**`src/test/java/com/example/sliceaudit/ImportedExtraBeanWebTest.java`**

```java
package com.example.sliceaudit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;

@WebMvcTest(ReportController.class)
@Import(ExtraSliceConfig.class)
class ImportedExtraBeanWebTest {

    @MockitoBean
    ReportService reportService;

    @Autowired
    ApplicationContext context;

    @Test
    void explicitImportRegistersBeanOutsideMvcComponentScan() {
        assertEquals("intentionally-imported",
                context.getBean(ExtraBackgroundJob.class).mode());
    }
}
```

**Expected outcome:** the test passes, even though `ExtraBackgroundJob` does not belong to MVC component scanning. This is the **expected behavior of `@Import`**, not proof that the filter failed.

What is concerning in real projects is that `@Import(EntireInfrastructureConfig.class)` can pull in many `@Bean` definitions: datasources, background executors, network clients, schedulers. Therefore, **import only the needed beans/configs**, and avoid "importing a whole package" or importing the entire application configuration just to fix a single missing slice dependency.

## 13. When `@Import` or `@Bean` Causes Many Beans to Appear

A common example: a configuration is imported into a test slice to get one `WebMvcConfigurer`, yet that class also provides a datasource and an HTTP client:

```java
// ILLUSTRATIVE ANTI-PATTERN, not a runnable file.
@Configuration
class MixedInfrastructureConfig {
    @Bean WebMvcConfigurer mvcConfigurer() { /* ... */ }
    @Bean DataSource dataSource() { /* ... */ }
    @Bean RemoteGateway remoteGateway() { /* ... */ }
}

@WebMvcTest(MyController.class)
@Import(MixedInfrastructureConfig.class)
class MyControllerTest {
}
```

This **is not standalone code**: `MyController`, `RemoteGateway`, `DataSource`, method bodies, and imports are undefined. It illustrates the risk of configuration classes holding too many responsibilities.

**Proper fix:** split into `MvcOnlyConfiguration` with `@Bean WebMvcConfigurer` and `DatabaseConfiguration` with the datasource/DB. `@Import(MvcOnlyConfiguration.class)` in the MVC slice will then be clear and will not pull in the DB.

Distinguish among:

- `@WebMvcTest`'s `includeFilters`: allows adding selected scan candidates when deliberately expanding the scan.
- `@Import`: directly adds configuration/bean classes and may pull in their dependencies.
- `@ImportAutoConfiguration`: used when adding Boot auto-configuration through Boot's mechanism; **do not substitute plain `@Import` arbitrarily** for auto-configuration classes.
- `@MockitoBean`: adds/replaces a mock bean to supply a collaborator the controller needs; it does not test the real bean's logic.

Common rule: **every slice expansion must have a clear reason tied to the contract under test**.

## 14. `includeFilters`, `excludeFilters`, and `useDefaultFilters`

`@WebMvcTest` (Boot 3.5) provides attributes to control which scanned components are selected, including `controllers`, `includeFilters`, `excludeFilters`, and `useDefaultFilters`.

Syntax example:

```java
// Illustrates intentionally adding a component to the slice.
@WebMvcTest(
    controllers = ReportController.class,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = SpecialMvcAdapter.class))
class SpecializedMvcTest {
}
```

This **is not a standalone compilable file**; `SpecialMvcAdapter` is undeclared, and annotation/enum imports are needed. This approach can bring extra beans into the slice (within the scan scope). So whenever an unexpected bean appears, check **the `includeFilters` declared directly on the test annotation**.

Conversely, `excludeFilters` can remove unwanted components. However, **do not start debugging by adding random `excludeFilters` to hide beans**. If the root cause is a separate `@ComponentScan` that broke the default filters, fix the scan source; if the bean was introduced via `@Bean`/`@Import`, a component-scan exclude is not an adequate fix.

`useDefaultFilters=false` alters how default candidates are matched in the test slice. It does not turn the context into "zero beans," because infrastructure, auto-configuration, and imports can still create beans. Use it only when you understand the exact set of types to retain.

**Version note:** the default includes list and supported bean types can change across Boot releases. When a test has different beans after an upgrade, check the `@WebMvcTest` API for your exact version before calling it a regression.

## 15. Locating Root Configuration and Nested Configurations

If a test simply writes:

```java
@WebMvcTest(ReportController.class)
class ReportControllerWebTest {
}
```

Spring Boot normally locates the application configuration by walking up from the test's package to parent packages looking for `@SpringBootApplication` or `@SpringBootConfiguration`. **The located application class may carry other configuration annotations** such as `@Import`, `@EnableScheduling`, or a custom `@ComponentScan`. That affects the slice context even though you did not write those annotations on the test class.

Sources to check while debugging:

1. The root application class located by Boot.
2. Direct `@ComponentScan` and meta-annotations on the root.
3. `@Import`, `@ImportAutoConfiguration`, `@Enable...` on the root.
4. Nested `@Configuration` or imported configuration classes.
5. Test-specific annotations (`@WebMvcTest` include/exclude), `@TestConfiguration`, and bean overrides.

**A subtle case:** a nested `@Configuration` inside a Spring Boot test can be treated as the test's primary configuration per bootstrap rules, whereas a nested `@TestConfiguration` typically supplements the primary configuration. Do not use nested configuration annotations by guesswork and assume Boot still finds and uses the same root as before.

When you want to specify the root explicitly, use `classes` on annotations that support it or explicit test configuration, **without turning a slice test into a full context** by pointing at an overly broad configuration source.

## 16. Gradle and Commands to Run the Examples

The example project in sections 9–12 uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Mockito**. In a Gradle project already configured with the Spring Boot plugin/BOM and repositories, the required dependency section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive snippet**, not a complete `build.gradle` (plugins/versions/repositories depend on the project). If these starters are already present, do not duplicate them.

Run from a project with the Gradle wrapper:

```bash
./gradlew test --tests com.example.sliceaudit.ReportControllerWebTest --tests com.example.sliceaudit.FullContextControlTest --tests com.example.sliceaudit.ImportedExtraBeanWebTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.sliceaudit.ReportControllerWebTest --tests com.example.sliceaudit.FullContextControlTest --tests com.example.sliceaudit.ImportedExtraBeanWebTest
```

In a multi-project Gradle build, replace `test` with the actual module's test task. With the code and configuration as described, **all three test methods are expected to pass**, and Gradle reports `BUILD SUCCESSFUL`. This is an **expected result from reading the code**, not a claim that they were executed against a provided repository. Snippets labeled ANTI-PATTERN or non-standalone illustrations **must not be created as files in the runnable project**.

Specific expectations:

- `ReportControllerWebTest`: HTTP 200, JSON `id=7` and `description=fixture-7`; no `ExternalBillingClient` bean; `ReportService` in the context is a Mockito mock.
- `FullContextControlTest`: full context has `ExternalBillingClient`, service returns `EXTERNAL:7`.
- `ImportedExtraBeanWebTest`: `ExtraBackgroundJob` is in the MVC slice **due to `@Import`** and returns `intentionally-imported`.

JUnit tests do not print fixed business stdout. Gradle messages and context logs vary by configuration. Reports are typically at `build/reports/tests/test/index.html`, and XML data at `build/test-results/test/` of the module.

## 17. Simulating the `@ComponentScan` Bug to See Loss of Isolation

You can learn by **reading** the following two configurations; do not arbitrarily modify the main application in a production project to experiment.

**Normal configuration:**

```java
@SpringBootApplication
class DemoApplication { }
```

**Suspect configuration:**

```java
@SpringBootApplication
@ComponentScan("com.example.sliceaudit")
class DemoApplication { }
```

If the app root uses the suspect configuration, `@WebMvcTest` or `@DataJpaTest` tests may scan additional out-of-scope components because the direct scan directive does not preserve the default exclude filters.

**Symptoms that can occur when switching configurations:**

- A controller test that previously only needed `@MockitoBean ReportService` now instantiates the real `ExternalBillingClient`.
- Tests hit dependencies/properties of non-MVC components.
- Startup time increases; tests need extra mocks just to build the context.
- Unexpected test-specific components or configurations get scanned.

Not every setup manifests identically. When both a real bean and a mock of the same type exist, the framework may apply bean overriding or throw an ambiguity error depending on test configuration. **Do not jump to conclusions from a single final exception; inspect the bean definitions and registration mechanism.**

**Fix:** remove the redundant scan directive; to change the base package, use `@SpringBootApplication(scanBasePackages = ...)`; for mandatory additional scans, configure filters deliberately and write a test proving isolation.

## 18. Diagnosis: Where Did a Bean Enter the Context?

There are three levels of observation:

### 18.1. Safe Level: Inspect Bean Type and Behavior

In a test, you can inject `ApplicationContext` and query:

```java
// Snippet placed inside a @Test; context is ApplicationContext.
String[] names = context.getBeanNamesForType(
        ExternalBillingClient.class);
assertEquals(0, names.length);
```

This proves the bean **was not registered under that type** in the context under inspection. It does not prove which filter excluded the bean or the original reason.

To distinguish mocks:

```java
boolean isMockitoMock =
        Mockito.mockingDetails(context.getBean(ReportService.class))
                .isMock();
assertTrue(isMockitoMock);
```

Requires importing `org.mockito.Mockito`, `assertTrue`, and running in a test class with `context` injected. This is an **illustrative snippet**, not a standalone Java class.

### 18.2. Detailed Level: Bean Definition and Registration Source

With an appropriate `ConfigurableApplicationContext`/`BeanFactory`, you can look up the `BeanDefinition` by bean name and inspect metadata such as `getResourceDescription()`, `getFactoryBeanName()`, `getFactoryMethodName()`, or source if available:

```java
// Illustrative debugging snippet, not a standalone file.
ConfigurableListableBeanFactory factory =
        configurableContext.getBeanFactory();

BeanDefinition definition =
        factory.getBeanDefinition("externalBillingClient");

System.out.println(definition.getResourceDescription());
System.out.println(definition.getFactoryMethodName());
```

Requires imports for `ConfigurableApplicationContext`, `ConfigurableListableBeanFactory`, and `BeanDefinition`; the `configurableContext` variable must have the proper type. Metadata **may be null or insufficient to pinpoint every registration path**, so combine it with logs and configuration code.

Do not leave this debugging code in production or automatically dump all beans/properties to CI logs: it can create noise or expose sensitive configuration data.

### 18.3. Framework Level: Selective Logging

You can increase logging for Spring configuration/classpath scanning when debugging:

```properties
logging.level.org.springframework.context.annotation=DEBUG
logging.level.org.springframework.boot.test.autoconfigure=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
```

This is a **temporary configuration hint**; exact log output varies by version and logger. A logger is not guaranteed to print the reason for every candidate. What matters most is identifying **which scan**, **which root configuration**, **which import**, and **which bean definition** brought the bean into the context.

When a test fails with `Failed to load ApplicationContext`, look for the **root cause** in the `Caused by` chain related to bean creation, rather than stopping at the outermost wrapper exception.

## 19. Troubleshooting Workflow Without Compromising Test Value

If a slice test unexpectedly contains an out-of-scope service:

1. **Confirm the actual annotation in use.** `@WebMvcTest` or `@SpringBootTest`? Is a composed annotation adding the full context?
2. **Inspect the bean type.** Is it a valid `@ControllerAdvice`/`Filter` or an `@Service`/job/non-MVC infrastructure bean?
3. **Locate the Spring root config.** Which `@SpringBootApplication` is Boot finding? Does it carry special scans/imports?
4. **Audit every `@ComponentScan`.** Directly on the root, inside imported configs, or in custom meta-annotations? Is `TypeExcludeFilter` in `excludeFilters` where needed?
5. **Audit other paths.** `@Import`, `@Bean`, `@ImportAutoConfiguration`, `@Enable...`, test `@MockitoBean`, or bean-registering factories.
6. **Check scan scope.** Are `basePackages`/`basePackageClasses` scanning multiple modules or test sources?
7. **Fix at the smallest source.** Remove redundant scans, split mixed configs, import exact beans, or use Boot's aliases.
8. **Add an isolation assertion if valuable.** For instance, verify that network adapters are absent in critical MVC slices.
9. **Run slice tests and a few integration tests.** Ensure scan fixes did not accidentally leave production missing a bean.
10. **Observe runtime/context cache.** Faster tests are just one signal; you must still assert functional contracts.

A short code-review checklist:

- [ ] Does the root `@SpringBootApplication` have an unnecessary direct `@ComponentScan`?
- [ ] Is an overly broad configuration class `@Import`ed in a test slice?
- [ ] Does a test-only mock/bean cause an unfamiliar bean to appear **intentionally**?
- [ ] Is a `Filter`/`ControllerAdvice` allowed by design, or is it genuinely an unwanted dependency?
- [ ] Is each missing dependency resolved with a test double/import at the right boundary rather than full app scanning?
- [ ] Should an adapter have its own HTTP/DB test instead of being forced into the MVC slice?
- [ ] Do the final assertions still guard HTTP/persistence behavior rather than only `contextLoads`?

## 20. Common Misconceptions

**"`@WebMvcTest` only contains controllers."** False. It needs MVC infrastructure and certain related bean types, plus whatever beans the test appropriately imports, mocks, or auto-configures.

**"Having an `@Service` bean in `@WebMvcTest` means the filter is broken."** Not necessarily. The bean may be a Mockito mock from `@MockitoBean` or explicitly imported.

**"`TypeExcludeFilter` excludes every bean outside the slice."** False. It mainly participates in **component scanning**. `@Bean`, `@Import`, auto-configuration, and registrars do not necessarily pass through the same candidate-scanning step.

**"Just add `@ComponentScan` on the root to be explicit about packages."** This easily breaks Boot's default mechanism if the filters are omitted. Usually you just place the application class in the right root package or use `scanBasePackages`.

**"Adding `excludeFilters` to the test will definitely fix it."** Not necessarily. If the bean is imported or created via `@Bean`, a scan filter is the wrong tool.

**"To make the test pass, switch `@WebMvcTest` to `@SpringBootTest`."** That can make the context load many more beans, take longer, and obscure design boundaries. Switch only when the goal truly requires full integration.

**"Faking/mocking a service with `@MockitoBean` is always wrong."** No. In an MVC slice test, mocking the service to test the controller contract is appropriate; just do not use that result to conclude the service's business logic is correct.

**"Slice tests prove the whole application works properly."** No. You must pair them with appropriate unit, adapter, integration, and contract tests to protect what lies outside the slice.

**"A test profile guarantees no outbound connections."** No. An out-of-scope bean pulled in via scanning/imports can still initialize or make network calls. Design safe adapters and test environments.

## 21. Practice Exercises

### Exercise A — Identify the Root Cause

A project has:

```java
@SpringBootApplication
@ComponentScan({"com.example.app", "com.example.shared"})
class App {
}
```

A `@DataJpaTest` suddenly instantiates `NotificationScheduler` and demands an API key. Answer:

1. Which scan directive is most suspect?
2. Why might the test slice lose its ability to exclude beans?
3. What two fixes avoid bringing the scheduler into the test?

**Guided answer:** The direct `@ComponentScan` on the app root is suspect because it can override the default scan containing exclude filters. Prefer removing the direct scan or using `@SpringBootApplication(scanBasePackages=...)`; if advanced custom scanning is required, ensure the proper filters are present and inspect any other scans.

### Exercise B — A Mock Service Does Not Mean the Real Service Was Scanned

In `@WebMvcTest`:

```java
@MockitoBean
ReportService service;
```

Meanwhile `ApplicationContext.getBean(ReportService.class)` returns an object. Can we conclude the real `@Service` slipped past scanning? What should be checked?

**Answer:** No. `@MockitoBean` can create/replace a mock. Check `Mockito.mockingDetails(bean).isMock()` and the bean definition/scan source if you truly need to tell them apart.

### Exercise C — `@Import` Causes an Unexpected Bean to Appear

Why is `ExtraBackgroundJob` from section 12 present in the MVC slice even though it is not a `@Controller`, `@Filter`, or `WebMvcConfigurer`?

**Answer:** Because `@Import(ExtraSliceConfig.class)` registers a configuration with a `@Bean` method. This bean does not need to be selected by MVC component scanning.

### Exercise D — Fixing a Mixed-Responsibility Configuration

An `AllInfrastructureConfig` contains `@Bean` methods for `WebMvcConfigurer`, datasource, email sender, and Kafka client. The team imports the entire class into `@WebMvcTest` just to get a converter. Split the configuration into smaller classes and identify which class should be imported. Explain why `excludeFilters` on scanning does not fully address beans created by `@Bean`.

### Exercise E — Which Beans Are Valid?

An MVC slice contains `GlobalExceptionAdvice`, `RequestIdFilter`, `WebMvcConfigurer`, and `OrderReconciliationJob`. The first three may be valid depending on configuration and test goals; the job bean usually warrants investigation. Explain how to verify whether each bean was registered via scanning, import, or auto-configuration.

### Exercise F — Write a Regression Test for Isolation

Based on `ReportControllerWebTest`, add a non-MVC `@Component PaymentWebhookPoller` class and assert `context.getBeanNamesForType(PaymentWebhookPoller.class).length == 0`. Then analyze what would happen if someone added a direct `@ComponentScan` to the root app.

## 22. Design Choices for Multi-Module Spring Boot Projects

In a monolith or modular monolith, "scanning every package" with a broad `@ComponentScan` can drag unrelated modules into a slice. The more modules you have, the harder the consequences are to spot.

Architectural suggestions:

- Place `@SpringBootApplication` in a sensible root package for the application scope.
- When expanding scanning, prefer `@SpringBootApplication`'s `scanBasePackageClasses` alias to preserve Boot defaults and avoid fragile package strings.
- Do not put MVC, database, messaging, scheduling, and security beans all inside one configuration class.
- For modules with a single adapter, define a dedicated configuration so it can be imported deliberately when needed.
- Split unit tests for services/domain, slice tests for controllers/repositories, and integration tests for real wiring/transactions.
- Maintain tests ensuring **external adapters** are not instantiated in slice tests where isolation matters.
- Avoid arbitrary variations of test overrides/imports that fragment the context cache and slow CI.
- When upgrading Spring Boot, review annotation types/packages and allowed MVC types rather than only bumping dependency versions.

Slice isolation is a **design and performance tool**, not a contest to minimize bean counts. The goal is to load **the right components to verify**, along with minimal appropriate infrastructure, keeping tests fast and trustworthy.

## 23. Summary and Final Checklist

Remember the three-question model:

**1. Should this bean be in the slice?** In `@WebMvcTest`, controllers/advice/filters/converters can be valid; business services and scheduled jobs are usually outside the target.

**2. How was this bean registered?** Default component scan, custom component scan, `@Import`, `@Bean`, auto-configuration, bean override, or registrar? `TypeExcludeFilter` does not govern all of those paths.

**3. Which fix preserves the right boundary?** Remove redundant `@ComponentScan`, use `@SpringBootApplication` aliases, split configurations, import only the needed parts, or use `@MockitoBean` for MVC collaborators. Move to a full integration test only when the goal requires it.

Verification checklist:

- [ ] The test has an appropriate slice annotation and is not accidentally using full `@SpringBootTest`.
- [ ] Root application configuration is discovered in the proper package.
- [ ] Component scanning does not inadvertently replace Boot's default filters.
- [ ] If multiple `@ComponentScan` directives exist, I inspected **each scan source**.
- [ ] I distinguish component-scan candidate filtering from auto-configuration, imports, and bean factories.
- [ ] I do not call a valid MVC bean "out-of-scope" merely because of its class name.
- [ ] I distinguish test-created mock beans from scanned real implementations.
- [ ] I do not import a broad infrastructure configuration just to get one small bean.
- [ ] I do not use scan excludes to suppress a bean created directly by `@Bean`.
- [ ] The test also checks mapping/JSON/data contracts, not just `contextLoads`.
- [ ] Initializing the slice opens no real connections or out-of-scope side effects.
- [ ] Separate unit/integration/adapter tests cover the logic the slice intentionally skips.
- [ ] When failures occur, I trace the root cause, bean definition source, and configuration annotations instead of mocking everything to make tests green.

**Core message:** `TypeExcludeFilter` helps Spring Boot **enforce component-scanning boundaries** for test slices; a direct `@ComponentScan` or another bean registration source can bring unexpected components into the context. Identify **how a bean entered** before applying a fix. A good slice is not just fast: it clearly states what it tests and what it intentionally leaves out.

### Official References

- Spring Boot 3.5 — Testing Spring Boot Applications, *Auto-configured Tests* and *User Configuration and Slicing*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 API — `SpringBootApplication`, `scanBasePackages`, and `scanBasePackageClasses`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.5 API — `WebMvcTypeExcludeFilter`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTypeExcludeFilter.html
- Spring Boot 3.5 — How-to Testing, deliberately importing configuration: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Framework 6.2 — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html
