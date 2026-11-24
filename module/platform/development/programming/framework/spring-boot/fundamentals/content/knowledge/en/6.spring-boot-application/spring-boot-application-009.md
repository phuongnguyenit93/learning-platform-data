# Splitting Annotations When Explicit Control Over Each Mechanism Is Needed

In Spring Boot, the startup class typically needs only a single `@SpringBootApplication` annotation. This annotation is convenient because it combines three essential mechanisms: identifying the application's configuration class, enabling auto-configuration, and discovering Spring components. However, when an application requires explicit control over scan scope, auto-configuration selection, or organizing configuration into independent pieces, you can **split the three mechanisms into separate annotations**.

What you must understand before splitting is that these annotations **do not do the same thing**. If split improperly, the application may still compile yet fail to create controllers/services, miss repositories, lose web infrastructure, or alter the behavior of Spring Boot tests.

## 1. The Nature of `@SpringBootApplication`

A typical application:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` is a **composed annotation**: it bundles other annotations to reduce repetitive configuration boilerplate.

| Composed annotation | Primary responsibility | Symptom if missing |
|---|---|---|
| `@SpringBootConfiguration` | Identifies the class as a Boot application's configuration source; built on `@Configuration` | Boot tests may fail to auto-detect the app config; the class loses the equivalent Boot config marker |
| `@EnableAutoConfiguration` | Selects auto-configurations based on dependencies, beans, properties, and application type | Web, data, security, or other integrations will no longer be auto-configured by Boot via this mechanism |
| `@ComponentScan` | Searches for stereotype classes like `@Component`, `@Service`, `@Controller`, `@Configuration` in matching packages | Developer-written components may fail to be registered as beans |

You can visualize it as:

~~~text
                   @SpringBootApplication
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
@SpringBootConfiguration  @EnableAutoConfiguration  @ComponentScan
          │                 │                 │
  Configuration source   Selects auto-        Finds app beans
  for Spring Boot        configurations       by Java package
  application            conditionally
          └─────────────────┼─────────────────┘
                            ▼
                      ApplicationContext
                       (beans are created)
~~~

The three annotations above work together, yet **each answers a different question**: where application configuration starts, what infrastructure Boot should supply automatically, and which classes in application source code should be registered.

### Boot Configuration Is Not Synonymous with the Java `main` Method

The `main(String[] args)` method is purely the Java program's entry point. The class passed to `SpringApplication.run(...)`, together with that class's configuration annotations, determines the Spring configuration source. If you place `main` inside a different launcher while still passing `CatalogApplication.class`, the default scan scope remains tied to the configuration class used, not the launcher's name.

## 2. How to Split Nearly Equivalently While Preserving Default Behavior

You can convert the class above to the explicit form below, keeping the same packages and dependencies:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    basePackageClasses = CatalogApplication.class,
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Here:

1. `@SpringBootConfiguration` retains the role of the Boot application's configuration class.
2. `@EnableAutoConfiguration` retains the auto-configuration mechanism.
3. `@ComponentScan(basePackageClasses = CatalogApplication.class)` scans `com.example.catalog` and its subpackages, matching the default scope when `@SpringBootApplication` sits in `com.example.catalog`.
4. The two `excludeFilters` preserve the filters `@SpringBootApplication` applies to component scanning. They matter for Boot's exclusion mechanisms—especially in certain **test slices**—and prevent auto-configuration classes from being picked up as regular components.

In simple applications, many online examples simply write:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class CatalogApplication {
}
~~~

This abbreviated form demonstrates the **three core functions**, yet **does not fully replicate the implicit component scan setup of `@SpringBootApplication`**: it omits the two filters noted above. When substituting in practice while preserving Boot's default behaviors, handle that difference intentionally. Other custom attributes of `@SpringBootApplication`, if used by the application, must also be moved to their corresponding annotations.

This is why splitting annotations should stem from **a specific configuration requirement**, rather than splitting just to write more lines of code.

## 3. Understanding `@SpringBootConfiguration` Alone: Application Configuration Source

`@SpringBootConfiguration` inherits semantics from `@Configuration`: it marks a class capable of declaring beans via `@Bean` and holding Spring configuration metadata. At the same time, it signals to Spring Boot tooling where the **root configuration** is.

Example:

~~~java
package com.example.catalog;

import java.time.Clock;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class CatalogConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

If this class is supplied to `SpringApplication.run(...)`, the `Clock` bean can be registered. However, **having `@SpringBootConfiguration` alone does not automatically enable component scanning or auto-configuration**. It does not automatically create an HTTP server, `DispatcherServlet`, or scan `@Service` classes across packages.

Normally, use `@SpringBootConfiguration` on the application's root configuration class, and `@Configuration` on supplemental configuration classes. Having multiple unnecessary `@SpringBootConfiguration` root classes in packages searched by tests can make test bootstrapping unpredictable.

### Are `@SpringBootConfiguration` and `@Configuration` Identical?

They share the same Spring configuration foundation, yet Boot looks for the `@SpringBootConfiguration` marker during test initialization. Replacing it with plain `@Configuration` will not always preserve **automatic root configuration discovery** for `@SpringBootTest` or test slices.

Therefore, if your goal is simply splitting `@SpringBootApplication` into its three constituent annotations, keeping `@SpringBootConfiguration` on the application class is the clearest choice.

## 4. Understanding `@EnableAutoConfiguration` Alone: Conditional Infrastructure Selection

`@EnableAutoConfiguration` enables Spring Boot to import **auto-configuration candidates** supplied by Boot and integrated libraries. In Spring Boot 3.x, library auto-configuration classes are listed in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Boot evaluates conditions before registering the corresponding configurations or beans. Common condition annotations include:

| Condition | Question checked |
|---|---|
| `@ConditionalOnClass` | Are required classes/libraries on the classpath? |
| `@ConditionalOnMissingClass` | Is a specific class missing? |
| `@ConditionalOnBean` | Does the context already have the required bean? |
| `@ConditionalOnMissingBean` | Is no matching bean present so Boot can create a default? |
| `@ConditionalOnProperty` | Does a property match the required value? |
| `@ConditionalOnWebApplication` | Is the app running an appropriate web stack? |

For example, when matching Spring MVC and Servlet libraries are on the classpath, Boot can configure Spring MVC web infrastructure; when adding Spring Data JPA with database connection conditions satisfied, Boot can create a `DataSource` and JPA infrastructure. If the application already supplies a bean for which an auto-configuration declares `@ConditionalOnMissingBean`, the default configuration usually **backs off**.

The presence of `@EnableAutoConfiguration` does not guarantee all those beans appear. **The classpath opens up possibilities; actual conditions decide the outcome.**

### Excluding a Specific Auto-Configuration

When you want to keep most auto-configurations yet stop Boot from auto-configuring one component, you can use the `exclude` attribute:

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration(
    exclude = DataSourceAutoConfiguration.class
)
@ComponentScan(basePackageClasses = BatchApplication.class)
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

This snippet illustrates the **exclusion intent**: asking Boot not to create a `DataSource` via `DataSourceAutoConfiguration`. When using this in a real application, include the two component scan filters as shown in the complete example in section 2, and ensure other beans no longer depend on the excluded `DataSource`.

Conceptually equivalent, when keeping the composite annotation, you can write:

~~~java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class BatchApplication {
}
~~~

This shows **you do not have to split annotations just to exclude**: `@SpringBootApplication` already exposes `exclude` and `excludeName`. Split only when you need independent control over each mechanism or clearer configuration organization.

### Disabling One Auto-Configuration Differs from Disabling All Auto-Configuration

Omitting `@EnableAutoConfiguration` removes Boot's broad infrastructure selection; excluding one specific configuration affects only the targeted piece, though downstream dependencies may trigger cascading effects. An application might still start yet lack a server, JSON converter, transaction manager, or default beans, depending on remaining configuration.

Do not drop `@EnableAutoConfiguration` altogether simply to avoid a database configuration error. Identify which auto-configuration is being selected and why it failed.

## 5. Understanding `@ComponentScan` Alone: Scope for Discovering App Beans

Suppose an application has the structure:

~~~text
src/main/java/
└── com/example/catalog/
    ├── CatalogApplication.java
    ├── api/
    │   └── ProductController.java
    ├── service/
    │   └── ProductService.java
    ├── config/
    │   └── CatalogConfig.java
    └── persistence/
        ├── ProductEntity.java
        └── ProductRepository.java
~~~

When `CatalogApplication` sits in `com.example.catalog` and `@ComponentScan` specifies no other base packages, Spring typically scans from that package down through its subpackages.

Classes like the following can be discovered:

~~~java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String label(long id) {
        return "product-" + id;
    }
}
~~~

~~~java
package com.example.catalog.api;

import com.example.catalog.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}/label")
    public String getLabel(@PathVariable long id) {
        return service.label(id);
    }
}
~~~

The controller and service must be registered as beans; HTTP routing also requires appropriate web infrastructure. In an application using `spring-boot-starter-web`, **component scan** finds `ProductController` and **auto-configuration** sets up Spring MVC/`DispatcherServlet` so endpoints can be invoked.

### Parent Packages, Sibling Packages, and Scan Scope

~~~text
com.example
├── catalog
│   ├── CatalogApplication   ← default @ComponentScan starts here
│   ├── api                  ← inside scope
│   └── service              ← inside scope
├── shared                  ← outside scope
└── accounting              ← outside scope
~~~

If `ProductService` is moved to `com.example.shared`, it will no longer automatically fall inside `com.example.catalog`'s scan scope. When the controller requests that service, bean creation can fail:

~~~text
Parameter 0 of constructor in ProductController
required a bean of type ProductService that could not be found.
~~~

To fix this, you can widen the scan scope **intentionally**, move the class back under the application's root package, or import a specific configuration.

## 6. Splitting Annotations to Intentionally Scan Multiple Packages

This is a practical scenario where separating the three mechanisms makes intent easy to read.

Suppose:

~~~text
com.example.catalog
├── CatalogApplication
└── api
    └── ProductController

com.example.shared.audit
├── AuditPackageMarker
└── AuditService        ← @Service
~~~

Because `com.example.shared.audit` is not a subpackage of `com.example.catalog`, we want component scanning to cover **two specific packages** without scanning all of `com.example`.

~~~java
// File: com/example/shared/audit/AuditPackageMarker.java
package com.example.shared.audit;

public interface AuditPackageMarker {
}
~~~

~~~java
// File: com/example/catalog/CatalogApplication.java
package com.example.catalog;

import com.example.shared.audit.AuditPackageMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    basePackageClasses = {
        CatalogApplication.class,
        AuditPackageMarker.class
    },
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`basePackageClasses` uses **the package containing each class** as a scan root. The marker interface does not need `@Component`; its role is representing a package, making configuration safer to refactor than handwritten package strings.

You could also specify strings:

~~~java
@ComponentScan(basePackages = {
    "com.example.catalog",
    "com.example.shared.audit"
})
~~~

However, when replacing `@ComponentScan` in full as above, keep Boot's default filters when equivalence with `@SpringBootApplication` is needed. When an application only needs to change scan scope, a **shorter** form is still available:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        CatalogApplication.class,
        AuditPackageMarker.class
    }
)
public class CatalogApplication {
}
~~~

Thus, the benefit of splitting here is making the three independent configuration parts explicit, rather than gaining some scan capability that the composite annotation cannot perform.

### If You Only Need One Configuration Class from Another Package

Instead of scanning an entire large package, you can use `@Import` to register a specific configuration:

~~~java
package com.example.catalog;

import com.example.shared.config.AuditConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(AuditConfiguration.class)
public class CatalogApplication {
}
~~~

`@Import` is another option when integrating a shared module. If `AuditConfiguration` contains `@Bean` methods, those beans can be registered without scanning the entire shared package. Splitting annotations is not always necessary to organize configuration.

## 7. Splitting Annotations to Clearly Separate Component Scanning from Entity/Repository Scanning

A common misconception is assuming widening `@ComponentScan` automatically handles **every** kind of class. In reality:

| Component kind | Typical discovery/registration mechanism |
|---|---|
| `@Service`, `@RestController`, `@Component`, `@Configuration` | Spring component scanning |
| `@Bean` from configuration classes | Processing registered/imported `@Configuration` sources |
| JPA `@Entity` | Entity scanning / JPA persistence unit |
| Interfaces extending `JpaRepository` | Spring Data repository scanning |
| Classes marked with `@ConfigurationProperties` | Configuration properties registration/scanning |
| Library auto-configuration classes | Boot's auto-configuration selection mechanism |

`@EnableAutoConfiguration` typically sets **auto-configuration packages** based on the package of the annotated class. These packages are used by many auto-configurations—including JPA and Spring Data—as their default roots. They **do not automatically update** when changing `@ComponentScan`'s `basePackages`.

Consider the layout:

~~~text
com.example.catalog
└── CatalogApplication

com.example.persistence
├── entity
│   └── ProductEntity             ← @Entity
└── repository
    └── ProductJpaRepository      ← extends JpaRepository
~~~

If you only add `com.example.persistence` to `@ComponentScan`, JPA entities and repository interfaces may still not be discovered as expected. When you need to explicitly specify data scopes, you can write:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(basePackageClasses = CatalogApplication.class)
@EntityScan(basePackages = "com.example.persistence.entity")
@EnableJpaRepositories(
    basePackages = "com.example.persistence.repository"
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

This is a simplified form highlighting the **three different scopes**. If used as the main configuration replacing `@SpringBootApplication` in a real project, add the two component scan `excludeFilters` as in section 2 to retain Boot's behavior.

With the configuration above:

- `@ComponentScan` handles application components in `com.example.catalog`.
- `@EntityScan` handles entities in `com.example.persistence.entity`.
- `@EnableJpaRepositories` handles repository interfaces in `com.example.persistence.repository`.
- `@EnableAutoConfiguration` continues supplying the corresponding auto-configurations **if the classpath and conditions match**.

For Spring Data MongoDB, R2DBC, or other storage modules, use their corresponding repository mechanisms; `@EnableJpaRepositories` is solely for **Spring Data JPA**. The configuration above also assumes the application has the JPA starter, driver, and appropriate database settings.

For `@ConfigurationProperties`, consider `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Widening component scanning **does not automatically replace** configuration properties registration rules.

## 8. Can Each Configuration Group Be Separated into Its Own Class?

Yes. Instead of stacking every annotation on the application class, you can **import a dedicated configuration class**. Keep in mind that `@ComponentScan`'s default package is the package of the class **carrying `@ComponentScan`**, and does not automatically revert to the package of the class containing `main`.

Example:

~~~java
// File: com/example/catalog/CatalogApplication.java
package com.example.catalog;

import com.example.catalog.bootstrap.CatalogComponents;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootConfiguration
@EnableAutoConfiguration
@Import(CatalogComponents.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

~~~java
// File: com/example/catalog/bootstrap/CatalogComponents.java
package com.example.catalog.bootstrap;

import com.example.catalog.CatalogApplication;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackageClasses = CatalogApplication.class,
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogComponents {
}
~~~

`CatalogComponents` is imported directly via `@Import`, and `@ComponentScan` inside it explicitly sets `basePackageClasses` to cover `com.example.catalog`. If that argument were omitted, default scanning would start at **`com.example.catalog.bootstrap`**, leaving components in `api` or `service` undiscovered.

In this example, `@SpringBootConfiguration` still sits on the root configuration class that Boot uses for startup and tests; `@EnableAutoConfiguration` remains enabled. This split suits cases where a configuration group's scope is complex enough to warrant its own name, or when separating ownership between a bootstrap module and feature modules.

For small applications, a standard `@SpringBootApplication` class remains easier to read and maintain.

## 9. Important Side Effects When Splitting Annotations

### 9.1. Forgetting `@ComponentScan`

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
public class CatalogApplication {
}
~~~

The application may still receive auto-configurations and start up, yet classes like `ProductService` or `ProductController` **are not found via regular component scanning**. Unless they are registered via `@Import`, `@Bean`, or another mechanism, injection can fail or endpoints will not exist.

### 9.2. Forgetting `@EnableAutoConfiguration`

~~~java
@SpringBootConfiguration
@ComponentScan
public class CatalogApplication {
}
~~~

Application components can still be discovered, yet configurations Boot normally provides automatically will not appear from this annotation: such as the embedded HTTP server, MVC infrastructure, or datasource/transaction infrastructure, depending on libraries and remaining configuration. `@ComponentScan` alone does not replace auto-configuration.

### 9.3. Replacing `@SpringBootConfiguration` with `@Configuration` and Forgetting Test Impact

The application can still run if the configuration class is passed directly to `SpringApplication.run(...)`, yet certain Spring Boot tests that search for the root configuration by package may fail to find the expected `@SpringBootConfiguration`. You can specify explicitly:

~~~java
@SpringBootTest(classes = CatalogApplication.class)
class CatalogContextTest {
}
~~~

Still, on a Boot application class, keeping the `@SpringBootConfiguration` marker accurately reflects its bootstrap role and keeps tests convenient.

### 9.4. Dropping the Two `@ComponentScan` Filters

Inside `@SpringBootApplication`, component scanning includes two built-in filters:

~~~java
@ComponentScan.Filter(
    type = FilterType.CUSTOM,
    classes = TypeExcludeFilter.class
)
@ComponentScan.Filter(
    type = FilterType.CUSTOM,
    classes = AutoConfigurationExcludeFilter.class
)
~~~

`TypeExcludeFilter` plays a role in excluding classes outside the scope of certain test slices, while `AutoConfigurationExcludeFilter` prevents auto-configurations from being mistakenly picked up by component scanning. If you write `@ComponentScan` yourself and forget these filters, scan results or test contexts may diverge from expectations—especially with `@WebMvcTest`, `@DataJpaTest`, or slices with custom filters.

### 9.5. Confusing `@ComponentScan` with `@EnableAutoConfiguration`

Adding a package to component scanning does not mean default data, security, or web beans appear automatically. Conversely, adding a starter to the classpath can cause Boot to enable new auto-configurations without needing to widen component scanning. Both mechanisms have **different configuration sources and conditions**.

### 9.6. Using `@EnableWebMvc` as a Substitute for `@EnableAutoConfiguration`

In a Spring Boot MVC application, adding `@EnableWebMvc` typically means **taking manual control of Spring MVC configuration**, causing Boot's MVC auto-configuration to back off in the corresponding areas. That is a completely different decision from splitting `@SpringBootApplication` into its underlying annotations. If you only need to customize formatters, interceptors, or resource handling, consider `WebMvcConfigurer` before taking over all of MVC.

## 10. When to Keep the Composite Annotation vs. When to Split?

| Need | Usually appropriate approach |
|---|---|
| Standard Boot app with components under one root package | Keep `@SpringBootApplication` |
| Only need to add component scan packages | Use `scanBasePackages` or `scanBasePackageClasses` on `@SpringBootApplication` |
| Only need to exclude an auto-configuration | Use `exclude`/`excludeName` on `@SpringBootApplication` or `spring.autoconfigure.exclude` |
| Want explicit separate configuration for config source, auto-configuration, and scanning | Split into `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan` |
| Need multiple scan packages, custom filters, or modular config separation | Split thoughtfully, specify base packages, and retain Boot filters when equivalence is needed |
| Have JPA entities/repositories outside the root package | Use `@EntityScan`/`@EnableJpaRepositories` for their intended purpose |
| Only need to pull in an existing config class from another package | Consider `@Import` |
| Need to tweak a few Spring MVC details | Prefer dedicated MVC customization; avoid disabling unrelated auto-configurations |

Point to keep in mind: **splitting does not guarantee successful customization**. What matters is understanding what each annotation enables or restricts, while preserving the default mechanisms the application still relies on.

## 11. How to Observe Outcomes After Changing Declarations

When splitting annotations in a project, you can rely on practical runtime signals to understand the mechanisms:

| Symptom | Connections to inspect |
|---|---|
| Startup fails due to missing `@Service` or `@Controller` | `@ComponentScan` scan packages, stereotype annotations, `@Import`/`@Bean` |
| Endpoint returns HTTP 404 despite controller existing | Was the controller scanned, is web framework handler mapping configured, is URL mapping right? |
| No embedded web server starts | Is `@EnableAutoConfiguration` still active, is the web starter present, and which web type was chosen? |
| Missing `DataSource` or JPA infrastructure error | JDBC/JPA dependencies, properties, auto-configuration conditions, and exclusions |
| JPA reports `Not a managed type` | `@EntityScan`/persistence unit scope, entity annotations |
| Spring Data repository is not registered | Repository scan scope, matching Spring Data starter |
| `@WebMvcTest` loads unexpected beans or differing context | Check component-scan filters when replacing `@SpringBootApplication` |
| `@SpringBootTest` cannot find root configuration | `@SpringBootConfiguration` marker and test package location |

To inspect **auto-configuration**, Spring Boot provides a Conditions Evaluation Report when run with:

~~~text
--debug
~~~

or:

~~~properties
debug=true
~~~

The report indicates which auto-configurations **matched**, **did not match**, or were **excluded**. It helps explain activation conditions, though it should not be treated as a full list of classes inspected by component scanning.

To see which beans were actually registered, inspect `ApplicationContext` or use the Actuator `beans` endpoint when appropriately enabled and secured. For controllers, inspect endpoint mappings; for repositories/entities, inspect their corresponding data configuration. Looking at the right mechanism saves more time than repeatedly expanding `basePackages`.

## 12. A Combined Example: Organizing an Application by Feature

Suppose an order management system has two feature groups:

~~~text
com.example.orders
├── OrdersApplication
├── sales
│   ├── SalesController
│   └── SalesService
└── shipping
    ├── ShippingController
    └── ShippingService
~~~

If this covers the entire application scope, the best declaration is typically just:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Suppose later the application integrates a company module in package `com.example.shared.events`, while also wanting to import a specialized configuration bean. You can **expand only the relevant parts**:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.orders",
        "com.example.shared.events"
    }
)
@Import(EventPublisherConfiguration.class)
public class OrdersApplication {
}
~~~

If the team needs to manage each mechanism in separate locations, you can switch to the trio `@SpringBootConfiguration`, `@EnableAutoConfiguration`, `@ComponentScan` as shown in the full examples in section 2 or 6, preserving the required Boot behaviors while explicitly declaring scan scope.

**Core principle:** `@SpringBootApplication` provides an intentionally bundled default configuration. Splitting it apart exposes explicit decisions about the **configuration source**, **auto-configuration**, and **component scanning**. When deep control is needed, adjust the specific annotation responsible for the issue at hand, retain necessary filters and conditions, and distinguish components from entities, repositories, or configuration properties. That keeps startup code clear in intent while avoiding unintended side effects in the Spring application context.
