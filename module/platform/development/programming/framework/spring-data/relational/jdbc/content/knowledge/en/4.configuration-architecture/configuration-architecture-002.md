# Enabling Repositories with @EnableJdbcRepositories and Limiting Scan Scope

In Spring Data JDBC, developers typically declare an interface such as `OrderRepository extends CrudRepository<Order, Long>` and inject it directly into a service. Behind that seemingly simple step lies **repository scanning**: Spring Data searches for repository interfaces in permitted packages, determines the aggregate type and primary key type, and registers the corresponding repository beans.

The **`@EnableJdbcRepositories`** annotation lets you explicitly declare **which packages are searched to create JDBC repositories**. This configuration is important when an application has multiple business modules, uses multiple Spring Data technologies simultaneously, or places configuration files in a different package from repositories.

Two foundational rules:

- With Spring Boot and `spring-boot-starter-data-jdbc`, auto-configuration usually already enables Spring Data JDBC repositories located in the default package area. You do not need to add `@EnableJdbcRepositories` just to use CRUD.
- When you need clear control over repository boundaries, use `@EnableJdbcRepositories(basePackages = ...)` or `@EnableJdbcRepositories(basePackageClasses = ...)`. The second form uses a marker type, making package renames easier to manage.

This lesson focuses on **enabling repositories and limiting the scan scope**, while distinguishing repository scanning from component scanning, domain mapping, and database connection configuration.

## 1. What Does Repository Scanning Actually Do?

Consider a repository:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

We do not write a manual implementation class for `findById(...)`, `save(...)`, and `deleteById(...)`. Spring Data JDBC uses a repository factory mechanism to create a bean implementing basic methods and handling validly declared query methods.

General flow:

~~~text
Application startup
       |
       v
Determine root packages for repository scan
       |
       v
Find Spring Data repository interfaces
       |
       v
Read metadata: domain type, ID type, query methods
       |
       v
Register repository factory bean and repository proxy
       |
       v
Application injects PurchaseOrderRepository into service
       |
       v
When repository is called: execute database access via Spring Data JDBC
~~~

**Repository scanning** only decides which interfaces are considered for bean registration. Whether SQL can actually run still depends on `DataSource`, mapping, database tables, connections, and transactions. `@EnableJdbcRepositories` does not create schemas or supply database credentials.

## 2. Spring Boot Usually Enables Repositories Automatically

For a Boot application using the Spring Data JDBC starter and a suitable datasource, Boot typically registers repositories automatically in the *auto-configuration packages*. These packages default to starting from the package containing `@SpringBootApplication`.

Example structure:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── sales/
    │   ├── domain/PurchaseOrder.java
    │   ├── repository/PurchaseOrderRepository.java
    │   └── service/PurchaseOrderService.java
    └── catalog/
        ├── domain/Product.java
        └── repository/ProductRepository.java
~~~

Startup class:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

With the structure above, repositories in `com.example.shop.sales.repository` and `com.example.shop.catalog.repository` lie under the root package `com.example.shop`, so they are typically detected by auto-configuration without needing a separate enable annotation.

Example Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Example connection configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
    password: change-me-in-your-environment
~~~

The values above only illustrate YAML structure and are not credentials ready for direct use. In real projects, passwords should come from secrets or environment configuration.

### When Default Packages Do Not Cover Repositories

Suppose `@SpringBootApplication` is in `com.example.shop.app`, while the repository is in `com.example.shop.sales.repository`:

~~~text
com.example.shop
├── app
│   └── ShopApplication.java
└── sales
    └── repository
        └── PurchaseOrderRepository.java
~~~

`sales.repository` is not a subpackage of `app`, so scanning based on the default package may skip the repository.

You can move `ShopApplication` up to the common parent package `com.example.shop` if the architecture allows, or configure the JDBC repository scope explicitly.

## 3. Enabling Explicitly with @EnableJdbcRepositories

Import the correct annotation:

~~~java
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
~~~

This is **Spring Data JDBC's** `EnableJdbcRepositories`, which differs from JPA's `EnableJpaRepositories`.

### 3.1. Specifying basePackages

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository"
)
public class SalesJdbcRepositoryConfig {
}
~~~

Spring Data JDBC will search for repositories in `com.example.shop.sales.repository` and its subpackages, rather than scanning every package under `com.example.shop` according to this declaration.

**Advantage:** direct, making it easy to see which package is registered.

**Limitation:** the package name is placed inside a string. After renaming a package in an IDE, the string might not be updated automatically.

Multiple scan roots can be specified:

~~~java
@EnableJdbcRepositories(basePackages = {
    "com.example.shop.sales.repository",
    "com.example.shop.reporting.repository"
})
~~~

When using multiple packages, each root should have an intentional scope, avoiding overly broad roots just to fix a "repository not found" error.

### 3.2. Specifying basePackageClasses

A safer approach for refactoring is to create a **marker type** in the repository package to be scanned:

~~~java
package com.example.shop.sales.repository;

/** Used solely as a marker to identify the Sales repository package. */
public interface SalesRepositoryPackage {
}
~~~

Then configure:

~~~java
package com.example.shop.config;

import com.example.shop.sales.repository.SalesRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

Spring uses the **package containing `SalesRepositoryPackage`** as the root package. The marker is not a repository and does not create a bean itself; it does not extend `CrudRepository`.

This approach reduces the risk of package strings becoming stale when directories are renamed or sources are moved. If the marker class/interface is renamed, the compiler also helps catch un-updated references.

Note: `basePackageClasses` **does not mean scanning only the passed-in class**. It scans valid repository interfaces in the package containing that class and its subpackages.

Use multiple markers when multiple areas are needed:

~~~java
@EnableJdbcRepositories(basePackageClasses = {
    SalesRepositoryPackage.class,
    ReportingRepositoryPackage.class
})
~~~

Each marker should reside in its corresponding repository package, rather than placing all of them in an overly broad package like `com.example.shop`.

## 4. Where Does It Scan When basePackages Is Omitted?

If you write directly:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories
public class JdbcRepositoryConfig {
}
~~~

The default scan area of **this declaration** is the package containing the annotated class: `com.example.shop.config`.

~~~text
com.example.shop
├── config/
│   └── JdbcRepositoryConfig.java   <-- default scan starts here
├── sales/
│   └── repository/
│       └── PurchaseOrderRepository.java
└── catalog/
    └── repository/
        └── ProductRepository.java
~~~

Because `sales.repository` is not a subpackage of `config`, the `@EnableJdbcRepositories` declaration above may fail to find business repositories.

This is a key distinction to grasp:

| Activation Method | Where Scan Root Comes From |
|---|---|
| Spring Boot auto-configuration | Boot's auto-configuration packages, usually based on the `@SpringBootApplication` package |
| `@EnableJdbcRepositories` with no scope arguments | Package of the class declaring the annotation |
| `basePackages = "..."` | Package written explicitly as a string |
| `basePackageClasses = X.class` | Package containing type `X` |

Some applications have multiple registration mechanisms active simultaneously. Therefore, the table above describes the **scope of each mechanism**, not necessarily every repository ultimately present in the ApplicationContext.

## 5. Distinguishing Component Scanning from Repository Scanning

A common source of confusion is thinking `@ComponentScan` and `@EnableJdbcRepositories` do the same thing.

| Mechanism | Primarily Finds What? | Configuration |
|---|---|---|
| **Component scanning** | Spring components such as `@Service`, `@Component`, `@Controller` | `@ComponentScan`, `@SpringBootApplication(scanBasePackages = ...)` |
| **Repository scanning** | Valid Spring Data repository interfaces that need a repository factory to create proxies | `@EnableJdbcRepositories` or auto-configuration |
| **Relational mapping** | Metadata mapping Java aggregates to tables/columns | `@Table`, `@Id`, `@MappedCollection` |

Example:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop.sales",
        "com.example.shop.catalog"
    }
)
public class ShopApplication {
}
~~~

The `scanBasePackages` attribute primarily controls **component scanning**. It does not automatically replace repository base package configuration for all Spring Data modules.

A `CrudRepository<PurchaseOrder, Long>` interface does not need `@Component` to become a repository bean. Spring Data handles this interface through repository registration.

### Illustrative Aggregate and Repository

~~~java
package com.example.shop.sales.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderCode;

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public void setOrderCode(String orderCode) {
        this.orderCode = orderCode;
    }
}
~~~

Repository:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderCode(String orderCode);
}
~~~

`@Table` describes the table corresponding to the aggregate. `@EnableJdbcRepositories` and auto-configuration are responsible for finding the repository interface. These two layers have different responsibilities.

## 6. Designing Package Boundaries by Module

When a codebase grows, repositories should be placed in packages whose names clearly indicate ownership:

~~~text
com.example.shop
├── config/
│   ├── SalesJdbcRepositoryConfig.java
│   └── CatalogJdbcRepositoryConfig.java
├── sales/
│   ├── domain/
│   │   └── PurchaseOrder.java
│   ├── repository/
│   │   ├── SalesRepositoryPackage.java
│   │   └── PurchaseOrderRepository.java
│   └── service/
│       └── OrderApplicationService.java
└── catalog/
    ├── domain/
    │   └── Product.java
    └── repository/
        ├── CatalogRepositoryPackage.java
        └── ProductRepository.java
~~~

In the configuration limiting Sales:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

Only repositories inside the Sales package are candidates for **this declaration**.

When you need to register Catalog as well, you can:

- Add `CatalogRepositoryPackage.class` to the same `basePackageClasses` if the repositories share the same JDBC infrastructure.
- Create another Catalog configuration with a non-overlapping root package if the architecture requires separate organization.

Example of two non-overlapping configurations:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
class SalesRepositoriesConfiguration {
}

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = CatalogRepositoryPackage.class
)
class CatalogRepositoriesConfiguration {
}
~~~

It is not necessary to have one config class per repository. If the system has only one database and the same configuration style, a single clear root scope may be enough.

### Avoiding Overlapping Scan Scopes

Suppose one configuration scans `com.example.shop` and another scans `com.example.shop.sales.repository`. Both may consider `PurchaseOrderRepository`. If two mechanisms register the same bean, the application may encounter duplicate bean name errors, bean definition overrides, or repository factory conflicts.

The proper solution is to control **all active registrars** and precisely determine which side owns each repository. You should not enable bean overriding by default to mask scope design flaws.

### includeFilters and excludeFilters

`@EnableJdbcRepositories` supports `includeFilters` and `excludeFilters` attributes using Spring type filters when deeper candidate filtering is needed.

Example of ignoring interfaces in a legacy package:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = "com\\.example\\.shop\\.sales\\.repository\\.legacy\\..*"
    )
)
public class SalesJdbcRepositoryConfig {
}
~~~

Here `\\.` in the Java string produces a literal dot in the regular expression, while `.*` matches type names in the legacy package and its sublevels. Whenever possible, prefer **proper package organization from the start** rather than relying on long, error-prone regex filters.

## 7. Which Repositories Qualify for Registration?

Spring Data recognizes a repository interface when it appropriately extends base interfaces, for example:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

You do not need to write a `PurchaseOrderRepositoryImpl` class to implement default CRUD operations; nor do you strictly need to add `@Repository` on the interface.

### Generic Base Interfaces and @NoRepositoryBean

If a project creates a generic repository interface for concrete repositories to extend, it should be marked as not being a standalone repository:

~~~java
package com.example.shop.shared.repository;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseCrudRepository<T, ID>
        extends CrudRepository<T, ID> {
}
~~~

Concrete repository:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import com.example.shop.shared.repository.BaseCrudRepository;

public interface PurchaseOrderRepository
        extends BaseCrudRepository<PurchaseOrder, Long> {
}
~~~

`@NoRepositoryBean` prevents Spring Data from trying to create a repository bean for the generic interface without a concrete domain type. The concrete interface with `PurchaseOrder` and `Long` is still registered when within the scan scope.

### Notes When Using JDBC Alongside JPA/MongoDB

When an application has multiple Spring Data modules on the classpath, Spring Data may use **strict repository configuration** to distinguish which store a repository belongs to.

In the context of Spring Data JDBC:

1. Place JDBC repositories in an appropriately scoped package.
2. Use Spring Data Relational mapping annotations such as `@Table` for JDBC aggregates.
3. Distinguish `@EnableJdbcRepositories` from `@EnableJpaRepositories` or another store's enable annotation.
4. Avoid letting the same repository interface be scanned by multiple stores unintentionally.

An interface merely extending `CrudRepository` sometimes lacks enough information to pick the right store in an application containing multiple Spring Data modules. Domain mapping and repository configuration must be consistent.

## 8. When Does JDBC Infrastructure Need Explicit Configuration?

`@EnableJdbcRepositories` **does not create a DataSource**. With a single database, Spring Boot typically prepares the datasource and related JDBC beans when dependencies and connection properties are complete.

Service example:

~~~java
package com.example.shop.sales.service;

import com.example.shop.sales.repository.PurchaseOrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository repository;

    public OrderApplicationService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public boolean exists(Long orderId) {
        return repository.existsById(orderId);
    }
}
~~~

Successful service injection means the repository bean has been registered. When calling `existsById(...)`, whether the SQL succeeds still requires valid connectivity, schema, and mapping.

### 8.1. Multiple DataSources Are Not Just Multiple basePackages

Consider two groups of repositories:

~~~text
sales.repository       -> Sales database
analytics.repository   -> Analytics database
~~~

Configuring separate scan roots only determines which repository belongs to each group. To actually use two databases, the application must also configure the corresponding JDBC operations beans, transaction managers, and mapping/data access infrastructure.

Depending on the Spring Data JDBC version, `@EnableJdbcRepositories` provides configuration references such as `jdbcOperationsRef` and `transactionManagerRef`. Their role is to link repositories to specific beans, but specifying those two parameters alone does not guarantee that every part of a multi-datasource design is correct. You must evaluate dialects, converters, data access strategies, transaction boundaries, and bean configuration in the version being used.

The example above only explains the **separation of responsibilities**: choosing packages configures repository registration; choosing databases configures deeper infrastructure.

## 9. Common Errors and Pinpointing the Failing Layer

### 9.1. "No qualifying bean of type PurchaseOrderRepository"

Example:

~~~text
No qualifying bean of type
'com.example.shop.sales.repository.PurchaseOrderRepository'
available
~~~

Causes usually belong to the bean registration layer:

- The repository is outside the base packages being scanned.
- `@EnableJdbcRepositories` has no arguments, while the configuration class is in another package.
- The class containing `@Configuration` is not loaded by Spring.
- The repository is filtered out by `excludeFilters`.
- The repository is not considered a valid candidate.
- The corresponding auto-configuration did not activate under the application's conditions.

In case the configuration class is outside component scan, you can import it via a configuration class that Spring already loads:

~~~java
package com.example.shop;

import com.example.shop.config.SalesJdbcRepositoryConfig;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SalesJdbcRepositoryConfig.class)
public class ShopApplication {
}
~~~

`@Import` is an explicit way to load config, not a mandatory step if the config is already found by component scanning.

### 9.2. "Relation/table does not exist" When Querying

Example:

~~~text
BadSqlGrammarException:
relation "purchase_order" does not exist
~~~

If the repository has already been injected and SQL is being issued, scanning is usually no longer the primary cause. Check the schema, table name in `@Table`, migrations, database permissions, datasource, and dialect.

### 9.3. Repository Bean Registered Twice

If multiple `@EnableJdbcRepositories` or auto-configuration combined with explicit configuration are present, check whether scan regions overlap. Separate packages, narrow scan roots, and ensure each repository is managed by a single appropriate mechanism.

### 9.4. Changing Packages While Forgetting to Update Strings

~~~java
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository"
)
~~~

If classes were moved to `com.example.shop.orders.repository`, the string above becomes stale. A marker class makes the package link clearer during refactoring.

### 9.5. Marker Placed Too High

If a marker is placed in `com.example.shop` and used with `basePackageClasses`, Spring may unintentionally scan multiple modules such as Sales, Catalog, Billing, etc. Markers should normally reside in a dedicated repository package, such as `com.example.shop.sales.repository`.

## 10. Observing the Actual Repository Set in ApplicationContext

An integration test can be used to confirm that the expected repository was registered:

~~~java
package com.example.shop;

import com.example.shop.sales.repository.PurchaseOrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void purchaseOrderRepositoryIsRegistered() {
        assertThat(context.getBeansOfType(
                PurchaseOrderRepository.class
        )).hasSize(1);
    }
}
~~~

This is an illustrative integration test, requiring the application to have a valid test datasource and related beans. The result confirms the bean count in the **entire ApplicationContext**; it does not test a single enable annotation in isolation.

If you want to restrict to Sales and exclude Catalog, you can assert that `CatalogRepository` is absent from the context, but only after ensuring no other registrar intentionally registers Catalog.

Spring Data's startup logs usually show the repository bootstrap process and the number of interfaces found. If you need a closer look, you can enable appropriate logging for `org.springframework.data.repository.config` to inspect repository scanning for the version in use.

## 11. Step-by-Step Practice: Specifying the Sales Module Scan Scope

Starting from this structure:

~~~text
com.example.shop
├── ShopApplication.java
├── config/
│   └── SalesJdbcRepositoryConfig.java
└── sales/
    ├── domain/
    │   └── PurchaseOrder.java
    └── repository/
        ├── SalesRepositoryPackage.java
        └── PurchaseOrderRepository.java
~~~

**Step 1 — Create the marker:**

~~~java
package com.example.shop.sales.repository;

public interface SalesRepositoryPackage {
}
~~~

**Step 2 — Register JDBC repositories via the marker:**

~~~java
package com.example.shop.config;

import com.example.shop.sales.repository.SalesRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

**Step 3 — Load the config:** if the `config` package is within Boot's component scan, the `@Configuration` class is detected. Otherwise, use `@Import(SalesJdbcRepositoryConfig.class)` on an already-loaded configuration class.

**Step 4 — Inspect the context:** confirm that `PurchaseOrderRepository` appears as exactly one bean. If the goal is to restrict to Sales, remember to account for other active repository scan configurations, including Boot auto-configuration if present.

**Step 5 — Verify query capability:** once the repository is successfully injected, invoke an appropriate read operation and distinguish connection/schema errors from bean-lookup errors.

This is a minimal example for designing scan boundaries. There is no need to write a manual repository implementation or place `@Repository` on the marker.

## 12. Questions to Understand the Fundamentals

**If an `@EnableJdbcRepositories` class is in `com.example.shop.config` without basePackages, will it automatically scan `sales.repository`?**

Not under that configuration. By default, the annotation scans the package of the class bearing the annotation. Repositories located elsewhere must be brought into an explicit scan scope or registered by another registrar.

**Does `basePackageClasses = PurchaseOrderRepository.class` scan only that exact repository?**

No. It uses the package containing `PurchaseOrderRepository` as the scan root, so other valid repositories in the same package and subpackages can also be registered.

**Is `@EnableJdbcRepositories` needed for every Boot application using JDBC?**

No. Spring Boot usually auto-configures repositories when the starter and conditions are met. Add the explicit annotation only when you have a reason to control scan scope or infrastructure.

**Can repository errors be fixed with `@SpringBootApplication(scanBasePackages = "...")`?**

That configures component scanning. Repository scanning has its own rules; do not treat it as a general replacement for `@EnableJdbcRepositories`.

**The repo can be injected, but `findById(...)` throws an SQL error—does that mean scanning is wrong?**

Not necessarily. The bean has been created; at that point, inspect the database, schema, mapping, and query.

**If two datasources and two `basePackages` are declared, is each guaranteed to map to its intended database?**

Not yet. Package scanning only determines which repositories are registered; JDBC infrastructure and transaction configuration must be designed accordingly.

## 13. Mental Model to Remember

~~~text
@SpringBootApplication + Spring Boot auto-configuration
    └── Usually enables JDBC repositories in the default package

@EnableJdbcRepositories
    ├── basePackages       -> specify packages as Strings
    ├── basePackageClasses -> derive package from marker type
    ├── include/exclude    -> refine repository candidates
    └── no arguments       -> package of the annotated class

Repository scanning
    -> find interfaces -> create repository factory/proxy

Component scanning
    -> find @Service / @Component / @Controller ...

Relational mapping
    -> uses @Table / @Id / @MappedCollection ...

DataSource + JDBC infrastructure
    -> executes actual connections, mapping, and SQL
~~~

When using Spring Data JDBC, treat `@EnableJdbcRepositories` as a tool to **declare repository registration boundaries**. Choose sufficiently narrow root packages, prefer markers when refactoring safety matters, avoid overlapping scans, and review all active configurations as a whole. That makes it easy to explain which repository belongs to which module and why a repository bean was created.
