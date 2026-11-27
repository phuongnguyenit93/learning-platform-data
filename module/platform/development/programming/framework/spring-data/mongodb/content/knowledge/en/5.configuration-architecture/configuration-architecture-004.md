# Enabling @EnableMongoRepositories and Scoping Package Scans

> **Chapter:** Configuration and Architecture  
> **Module:** `SPRING_DATA_MONGODB`

When using Spring Data MongoDB, applications commonly declare interfaces such as `MongoRepository<Order, String>`. Spring Data creates beans implementing these interfaces at startup so services can inject repositories to query, save, and update documents. **`@EnableMongoRepositories` defines which packages are scanned to discover and register MongoDB repositories.** Choosing an accurate scan scope helps the application register the right repositories without missing beans or accidentally picking up repositories from other modules.

This lesson focuses on using the annotation in Java configuration, Spring Boot's default behavior, the boundary between repository scanning and other scan mechanisms, and binding repositories to the right `MongoTemplate`. It forms the foundation for the `SPRING_DATA_MONGODB` module, where applications connect to MongoDB, map documents, operate through `MongoTemplate` or repositories, and progress to queries, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the function of `@EnableMongoRepositories` and distinguish it from `@ComponentScan`, `@Document`, and MongoDB connection configuration.
2. Know when Spring Boot auto-configures repositories and when explicit annotation declaration is needed.
3. Limit scanning using `basePackages` or `basePackageClasses` and understand how the location of the configuration class affects scanning.
4. Avoid duplicate registration, scanning unintended interfaces, or binding repositories to the wrong `MongoTemplate` when multiple databases exist.
5. Verify that repository beans are registered properly and troubleshoot common issues in real applications.

## 2. Three Distinct Responsibilities in a MongoDB Application

Distinguish these responsibilities clearly:

| Mechanism | What does it find or configure? | Example | Replaced by `@EnableMongoRepositories`? |
| --- | --- | --- | --- |
| **Component scan** | Configuration classes and Spring components like `@Service`, `@Configuration` | `OrderService`, `MongoRepositoryConfig` | No |
| **Repository scan** | Repository interfaces for Spring Data to create proxy/implementation beans | `OrderRepository extends MongoRepository<...>` | Yes, this is its primary role |
| **Document mapping** | Java types and metadata mapping to BSON/collections | `@Document(collection = "orders")`, `@Id`, `@Field` | No |
| **MongoDB connection/template** | Client, database, converters, and data access tools | `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` | No |

The repository creation flow can be visualized as follows:

```text
Spring application starts
   │
   ├── Initialize MongoClient, MongoTemplate / mapping infrastructure
   │
   ├── Load @Configuration annotated with @EnableMongoRepositories
   │      └── Scan repository interfaces in the selected packages
   │             └── Register proxy beans for OrderRepository, ...
   │
   └── Create OrderService
          └── Inject OrderRepository bean
                 └── Query documents via MongoTemplate/driver
```

A repository is an interface yet can normally be injected because Spring Data generates a dynamic implementation bean. You do not usually write an `OrderRepositoryImpl` class for standard CRUD or derived queries.

**Key point:** `@EnableMongoRepositories` does not open connections, does not create collections, does not pick a database from the package name, and does not scan every class annotated with `@Document`. Repositories are registered by package, while which database they store data in depends on the `MongoTemplate` they use.

## 3. Do You Need @EnableMongoRepositories in Spring Boot?

### 3.1. Typical Spring Boot usage

With Spring Boot having the Spring Data MongoDB dependency and valid connection settings, Boot normally activates repository infrastructure automatically. Without custom repository configuration, Boot derives the default package scope from the application's auto-configuration base package, typically established by `@SpringBootApplication`.

Example:

```text
com.example.shop
├── ShopApplication.java                 (@SpringBootApplication)
├── orders
│   ├── model/Order.java                 (@Document)
│   ├── repository/OrderRepository.java  (MongoRepository)
│   └── service/OrderService.java        (@Service)
└── catalog
    └── repository/ProductRepository.java
```

If `ShopApplication` is in `com.example.shop` and Boot's repository auto-configuration is active, both repositories in subpackages are normally discovered. In this layout, you may **not need** to write `@EnableMongoRepositories`.

Example connection configuration **for local development**:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
```

This is an example URI; real deployment environments need security, access permissions, and secrets configured according to your infrastructure. Having a URI does not guarantee all repositories are scanned properly; those are two independent configurations.

### 3.2. When to declare the annotation explicitly

Consider `@EnableMongoRepositories` when:

- You only want to register repositories for a specific module scope, such as `orders.repository` alone.
- Repositories sit outside the application's default scan package.
- Multiple `MongoTemplate` instances or multiple MongoDB databases exist and each repository group must bind to the right template.
- Building a Spring application that does not rely on Boot's repository auto-configuration.
- You need to customize repository scanning via Spring Data-specific attributes.

If you choose explicit declaration, review other `@EnableMongoRepositories` configurations and related auto-configurations so you do not register the same interface twice. How manual and automatic configurations interact depends on the Spring Boot version, existing beans, and auto-configuration conditions; inspect the **actual `ApplicationContext`** rather than guessing from a package diagram.

## 4. Complete Example: Registering Only Order Repositories

Suppose the project has this structure:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   └── OrdersRepositoryConfig.java
├── orders/
│   ├── model/Order.java
│   ├── repository/
│   │   ├── OrdersRepositoryPackage.java
│   │   └── OrderRepository.java
│   └── service/OrderService.java
└── catalog/
    └── repository/ProductRepository.java
```

The goal is for `OrdersRepositoryConfig` to scan only `com.example.shop.orders.repository`. Classes outside this package fall outside **that configuration's scan scope**.

### 4.1. Document

File `orders/model/Order.java`:

```java
package com.example.shop.orders.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String customerId,
    long totalMinor,
    String status
) {}
```

`@Document` indicates the domain object maps to the `orders` collection. The field `id` maps to `_id` in the BSON document.

### 4.2. Repository interface

File `orders/repository/OrderRepository.java`:

```java
package com.example.shop.orders.repository;

import com.example.shop.orders.model.Order;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByCustomerId(String customerId);
}
```

Once the interface is discovered, Spring Data creates the repository bean and translates `findByCustomerId` into a query against the domain object's `customerId` property. How repositories are organized in packages does not alter collection or field names.

### 4.3. Marker for refactor-safe package selection

File `orders/repository/OrdersRepositoryPackage.java`:

```java
package com.example.shop.orders.repository;

/** Marker used to select the package containing repositories. */
public interface OrdersRepositoryPackage {}
```

This marker is neither a repository nor a bean. Its purpose is to provide a **type-safe package reference**, avoiding raw string package names.

### 4.4. Enabling and limiting scanning

File `config/OrdersRepositoryConfig.java`:

```java
package com.example.shop.config;

import com.example.shop.orders.repository.OrdersRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class
)
public class OrdersRepositoryConfig {}
```

Because the marker resides in `com.example.shop.orders.repository`, the annotation scans that package **and its eligible subpackages**, instead of defaulting to `OrdersRepositoryConfig`'s package. Placing the marker in `com.example.shop` would make the scope broader than intended.

File `ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Since `OrdersRepositoryConfig` is in a subpackage of `com.example.shop`, `@SpringBootApplication`'s default component scan loads this configuration. If the configuration class is moved outside the component scan scope, you must import it or adjust component scanning so Spring actually processes the annotation.

### 4.5. Service using the registered bean

File `orders/service/OrderService.java`:

```java
package com.example.shop.orders.service;

import com.example.shop.orders.model.Order;
import com.example.shop.orders.repository.OrderRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public List<Order> ordersOf(String customerId) {
        return orders.findByCustomerId(customerId);
    }
}
```

If the application starts successfully and the `OrderRepository` bean exists, Spring can inject it into the service via constructor injection. An active MongoDB connection is required to **execute queries**; successful bean creation does not prove the database is running or queries match real data.

## 5. How Do `basePackages` and `basePackageClasses` Differ?

`@EnableMongoRepositories` provides two common ways to specify scanned packages:

### 5.1. `basePackages`: string-based declaration

```java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackages = "com.example.shop.orders.repository"
)
public class OrdersRepositoryConfig {}
```

This configuration is concise and readable, but when renaming packages with refactoring tools, string literals may not update automatically. A typo in the path can leave the application finding no repositories in that scope.

### 5.2. `basePackageClasses`: class-based declaration

```java
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class
)
```

Spring takes the **package containing the specified class/interface**, not just that class/interface alone. A marker makes intent clear; you can also pass `OrderRepository.class` if you want to scan the entire package containing that repository.

| Criterion | `basePackages` | `basePackageClasses` |
| --- | --- | --- |
| How scope is selected | Package name as string | Package of the Java type |
| Refactoring support | Prone to breaking if strings are missed | Java tooling typically updates imports/types |
| Multiple scopes supported | Yes, pass multiple package names | Yes, pass multiple classes/markers |
| Precision | That package and subpackages | Also that package and subpackages |
| Recommended choice | When explicit configuration strings are preferred | When the codebase can use dedicated module markers |

Both attributes accept **multiple** values:

```java
// Standalone example: use when intentionally scanning both packages.
@EnableMongoRepositories(
    basePackages = {
        "com.example.shop.orders.repository",
        "com.example.shop.billing.repository"
    }
)
```

Or:

```java
@EnableMongoRepositories(
    basePackageClasses = {
        OrdersRepositoryPackage.class,
        BillingRepositoryPackage.class
    }
)
```

In the second example, `BillingRepositoryPackage` is a marker placed in the billing repository package. These short annotation snippets illustrate **alternative options**; do not apply overlapping scan configurations just to mix both syntaxes.

### 5.3. What if neither `basePackages` nor `basePackageClasses` is specified?

`@EnableMongoRepositories` defaults to using the package of the **annotated configuration class** as the root package to scan.

Suppose:

```text
com.example.shop
├── config/OrdersRepositoryConfig.java  <-- @EnableMongoRepositories without basePackages
└── orders/repository/OrderRepository.java
```

Here, the configuration only searches within `com.example.shop.config` and its subpackages, **not** the sibling package `com.example.shop.orders.repository`. This is a frequent cause of services failing to inject repositories after moving the annotation from the root application class into a `config` class.

**Rule:** if you place a configuration class inside a dedicated package like `config`, specify `basePackageClasses` or `basePackages` explicitly.

## 6. Repository Scanning Is Not Component Scanning

Spring must **load the configuration class** first before the annotation on that class takes effect. The two scan scopes can differ:

```text
@SpringBootApplication / @ComponentScan
    └── finds @Configuration OrdersRepositoryConfig
           └── @EnableMongoRepositories
                 └── finds MongoRepository interfaces in orders.repository
```

For example, if `OrdersRepositoryConfig` sits in `com.example.infrastructure.mongo` outside the `com.example.shop` application package: even if the annotation has the correct `basePackageClasses`, if Spring does not load the configuration, **that repository scan never runs**.

You can import the configuration from the application class:

```java
package com.example.shop;

import com.example.infrastructure.mongo.OrdersRepositoryConfig;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(OrdersRepositoryConfig.class)
public class ShopApplication {}
```

This is an optional example; `OrdersRepositoryConfig` must actually exist in the relevant dependency/module. `@Import` is unnecessary if the class already lies inside component scan scope and is properly loaded by Spring.

**Repository scanning also does not scan document entities the way JPA does.** Spring Data MongoDB obtains mapping metadata for domain classes when working with them and through the mapping infrastructure. Placing `Order` in a different package from `OrderRepository` will not cause the repository to be skipped, provided the domain class is on the classpath and its mapping is valid.

## 7. Limiting Scans to Avoid Accidental Registration

A large project structure might look like:

```text
com.example.platform
├── sales
│   └── repository/OrderRepository.java
├── audit
│   └── repository/AuditRepository.java
├── experiments
│   └── repository/DraftRepository.java
└── bootstrap
    └── MongoConfig.java
```

Setting `basePackages = "com.example.platform"` causes all matching MongoDB repository interfaces across subpackages to be scanned. When all repositories point to a single template, unintended modules can easily get registered into the same `ApplicationContext`.

Ways to control this:

1. **Organize repositories along module boundaries:** e.g. `sales.repository`, `audit.repository`.
2. **Point markers to the narrowest package needed:** e.g. `SalesRepositoryPackage.class`.
3. **Separate configurations by repository group and template** when multiple MongoDB sources exist.
4. **Avoid overlapping `@EnableMongoRepositories` scan scopes** if both would register the same repositories.
5. If you have a shared base repository interface that should **not become a bean directly**, annotate it with `@NoRepositoryBean`.

Example base interface:

```java
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
```

`@NoRepositoryBean` instructs Spring Data not to create a repository bean for the base interface that lacks a concrete domain type. Subinterfaces with concrete domain types will still be registered. This is useful when defining shared methods across repositories without letting the generic interface be treated as a standalone repository.

`@EnableMongoRepositories` also supports `includeFilters` and `excludeFilters`. They can help in special situations, but clearly separated packages are generally easier to maintain and less surprising than name- or annotation-based filters.

## 8. Multiple `MongoTemplate`s: Selecting the Right Database for Each Repository Group

In a multi-module system, operational repositories might target the `shop` database while aggregated data targets `analytics`. **Scoping scanned packages alone does not determine the target database.** You must bind each repository group to its corresponding `MongoTemplate` bean via `mongoTemplateRef`.

Conceptual example:

```text
orders.repository  -- @EnableMongoRepositories -->
                       mongoTemplateRef="ordersMongoTemplate"
                       MongoTemplate(database="shop")

analytics.repository -- @EnableMongoRepositories -->
                       mongoTemplateRef="analyticsMongoTemplate"
                       MongoTemplate(database="analytics")
```

### 8.1. Configuring repositories for orders

The example below uses a `MongoClient` already provided by the application (such as from Spring Boot auto-configuration):

```java
package com.example.shop.config;

import com.example.shop.orders.repository.OrdersRepositoryPackage;
import com.mongodb.client.MongoClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class,
    mongoTemplateRef = "ordersMongoTemplate"
)
public class OrdersMongoConfig {

    @Bean("ordersMongoTemplate")
    public MongoTemplate ordersMongoTemplate(MongoClient client) {
        return new MongoTemplate(client, "shop");
    }
}
```

- `basePackageClasses` identifies the **group of repository interfaces**.
- `mongoTemplateRef` identifies the **MongoTemplate bean name** used by that group.
- `new MongoTemplate(client, "shop")` selects the `shop` database on the supplied client.

This configuration **replaces** `OrdersRepositoryConfig` from Section 4. When using `OrdersMongoConfig`, remove the old overlapping scan configuration in a real application to prevent registering the same repository twice. When multiple templates exist, injecting `MongoTemplate` directly into a service requires specifying the target bean (e.g. with `@Qualifier`).

### 8.2. Configuring the analytics group

Another configuration class can declare:

```java
@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = AnalyticsRepositoryPackage.class,
    mongoTemplateRef = "analyticsMongoTemplate"
)
public class AnalyticsMongoConfig {
    @Bean("analyticsMongoTemplate")
    MongoTemplate analyticsMongoTemplate(MongoClient client) {
        return new MongoTemplate(client, "analytics");
    }
}
```

This snippet assumes `AnalyticsRepositoryPackage` exists in the analytics repository package and the application shares one `MongoClient` for two databases on one deployment. If the databases reside on two separate clusters or use different credentials, declare **two corresponding clients/factories** instead of sharing a single client.

`mongoTemplateRef` must match the **actual bean name**. A typo will cause Spring to fail when creating the repositories because the template cannot be found. If two repository groups scan overlapping packages, pointing to different templates does not make duplicate beans valid.

### 8.3. Difference between package grouping and authorization

Grouping repositories by package organizes **application** beans. It does not replace MongoDB authentication and authorization. If multiple repositories share a client that has permissions on multiple databases, package scanning does not restrict server-side privileges. Configuring principals, roles, TLS, and credentials must be handled independently.

## 9. Imperative and Reactive Must Configure the Right Repository Type

Spring Data MongoDB supports two access styles:

| | Imperative (synchronous/blocking) | Reactive |
| --- | --- | --- |
| Typical repository | `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| Explicit scan annotation | `@EnableMongoRepositories` | `@EnableReactiveMongoRepositories` |
| Template | `MongoTemplate` | `ReactiveMongoTemplate` |
| Method return types | `Optional`, `List`, `Page`, ... | `Mono`, `Flux`, ... |

Example reactive interface:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<Order, String> {

    Flux<Order> findByCustomerId(String customerId);
}
```

If reactive repositories need explicit activation, use the matching annotation:

```java
@Configuration(proxyBeanMethods = false)
@EnableReactiveMongoRepositories(
    basePackageClasses = ReactiveOrderRepository.class,
    reactiveMongoTemplateRef = "reactiveMongoTemplate"
)
public class ReactiveOrderRepositoryConfig {}
```

The example assumes the application already has a `reactiveMongoTemplate` bean of type `ReactiveMongoTemplate` and imports `@EnableReactiveMongoRepositories`/`@Configuration`. In a project using both styles, keep synchronous and reactive repository packages separate to avoid overly broad scanning or Spring Data inferring the wrong repository type.

Reactive repositories require the reactive MongoDB driver and matching connection configuration; merely changing `@EnableMongoRepositories` to another annotation does not turn blocking services into non-blocking ones. Likewise, atomicity, transactions, and index choices still follow MongoDB's capabilities and how operations are executed.

## 10. Verifying Configuration at Application Startup

### 10.1. Verifying repository beans in ApplicationContext

Integration test example using JUnit 5 and Spring Boot Test:

```java
package com.example.shop;

import com.example.shop.orders.repository.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MongoRepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void orderRepositoryIsRegistered() {
        assertThat(context.getBeansOfType(OrderRepository.class))
            .hasSize(1);
    }
}
```

This test proves that one `OrderRepository` bean was registered. If the goal is **ensuring out-of-scope repositories are absent**, add an assertion for that repository type, ensuring no other configuration is intentionally registering it.

The test context may still initialize MongoDB infrastructure; to test actual query execution, use an isolated MongoDB test instance (such as Testcontainers) and intentional test data. Keep two conclusions distinct:

- **Bean exists:** repository scanning and basic wiring are correct.
- **Queries work:** connectivity, mapping, collection names, permissions, and actual data are correct.

In Spring Boot applications, `@DataMongoTest` can test the data slice. If repositories reside outside the package searched by the slice test, import the needed configuration or adjust the test scope; do not assume all runtime configurations are automatically loaded into the slice.

### 10.2. Checking logs and auto-configuration conditions

At startup, Spring Data normally logs repository discovery and the count of detected interfaces. If the count is unexpected, first check which configuration classes are being loaded, then check packages and repository types. You can enable debug logging for repository configuration:

```yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
```

Spring Boot also supports viewing the auto-configuration conditions report in debug mode to see which auto-configurations were activated or skipped. Only enable verbose logging while diagnosing issues; avoid excessive debug-level logging in normal operation.

## 11. Common Errors and Troubleshooting

| Symptom | Possible cause | How to inspect and fix |
| --- | --- | --- |
| `No qualifying bean of type 'OrderRepository'` | Repository package is outside scan scope; config class not loaded | Check `@Configuration` location, `basePackageClasses`, and component scan/`@Import` |
| Repository scan reports 0 interfaces found | Placed `@EnableMongoRepositories` in `config` package without setting base package | Specify the repository package explicitly via marker or string |
| Repository created twice, duplicate bean error | Two configurations scan overlapping interfaces | Split packages cleanly; remove redundant annotations/configs |
| Repository writes to unexpected database | All repositories use the default template or bind to the wrong bean | Check `mongoTemplateRef`, `MongoTemplate` beans, and each template's database |
| Missing `mongoTemplate` or custom template bean | Missing bean or typo in `mongoTemplateRef` | Declare the template/connection and verify the exact bean name |
| Multiple `MongoTemplate`s cause ambiguous injection | Multiple beans of the same type with no primary or qualifier | Mark `@Primary` appropriately or inject using `@Qualifier` |
| Generic interface treated as concrete repository | Base interface missing `@NoRepositoryBean` | Add `@NoRepositoryBean` to the generic base repository |
| Reactive repository fails to register properly | Used imperative annotation/template or mixed packages | Use `@EnableReactiveMongoRepositories` and reactive infrastructure; separate scan scopes |
| Repository exists but queries fail | Wrong field names, converters, connection, permissions, or mapping | Run a real query and verify `@Document`/`@Field` metadata and target database |

### Step-by-step diagnostic example

Suppose `OrderService` reports it cannot inject `OrderRepository`:

1. Confirm `OrderRepository` is actually an interface recognized by Spring Data (e.g., extends `MongoRepository<Order, String>`).
2. Confirm `OrdersRepositoryConfig` has been loaded into the `ApplicationContext`.
3. Check the package of marker `OrdersRepositoryPackage` and compare it against the repository's location.
4. Check for other repository-enabling annotations or active auto-configurations.
5. Inspect repository bootstrap logs and test `getBeansOfType(OrderRepository.class)`.
6. Only after the bean is confirmed present should you verify MongoDB connectivity and actual queries.

Do not "fix" this by adding a broad `@ComponentScan("com.example")`: widening component scanning does not replace setting the right repository base package and can pull in unwanted configurations.

## 12. Design Checklist Before Production

Before finalizing your configuration, answer:

- **What is the activation source?** Spring Boot auto-configuration, `@EnableMongoRepositories`, or an intentional combination?
- **Where are the repositories?** Are their packages within the scan scope?
- **Is the configuration class loaded by Spring?** Via component scan or `@Import`?
- **Are any unintended packages scanned?** Subpackages, experimental repositories, generic interfaces, or other modules' packages?
- **Which template is used?** Default `mongoTemplateRef` or an explicit bean name; which database does the template target?
- **Is the access style consistent?** `MongoRepository`/`MongoTemplate` or `ReactiveMongoRepository`/`ReactiveMongoTemplate`?
- **Are results verified?** Are there bean registration tests and query tests against an appropriate MongoDB instance?

### Case study exercise

An application has two modules:

```text
com.example.app
├── App.java
├── config
│   └── MongoConfig.java
├── customer.repository
│   └── CustomerRepository.java
└── report.repository
    └── DailyReportRepository.java
```

Requirement: register only `CustomerRepository` with `customerMongoTemplate` pointing to the `crm` database, and `DailyReportRepository` with `reportMongoTemplate` pointing to the `reporting` database.

**Solution hints:**

1. Create a separate marker in each of the two repository packages.
2. Create two configuration classes annotated with `@EnableMongoRepositories`, each with distinct `basePackageClasses` and `mongoTemplateRef`.
3. Register two `MongoTemplate` beans targeting the appropriate databases, with required clients/factories and connection privileges.
4. Ensure both configuration classes are loaded by Spring and their scan scopes do not overlap.
5. Verify each repository creates exactly one bean; execute sample queries and confirm data lands in the intended databases.

## Key Takeaways

`@EnableMongoRepositories` is the tool for **selecting and registering repository interfaces**. In typical Spring Boot apps, auto-configuration handles activation; when you need to restrict scope or use multiple data sources, declare it explicitly using `basePackageClasses` or `basePackages`. The location of the `@Configuration` class determines the default scope if none is specified, while `mongoTemplateRef` determines which `MongoTemplate` bean the repositories use. Separating repository scanning, component scanning, document mapping, and connection configuration surfaces errors early and keeps Spring Data MongoDB architectures maintainable.
