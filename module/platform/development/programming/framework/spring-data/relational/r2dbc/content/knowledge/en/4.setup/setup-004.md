# Initializing an Application with Spring Boot Auto-Configuration

Spring Boot helps initialize a Spring Data R2DBC application with minimal manual configuration. When the right dependencies are on the classpath and connection details are declared, Spring Boot can automatically create a `ConnectionFactory`, set up reactive data access infrastructure, register repositories, and provide transaction support components.

The key point is that **auto-configuration is driven by dependencies, configuration properties, and existing beans in the ApplicationContext**. Spring Boot cannot guess your database, credentials, or table structure. You still need to add the right driver, supply connection details, and design your schema.

## 1. What Is Spring Boot Auto-Configuration?

Auto-configuration is the mechanism by which Spring Boot automatically configures common components based on what the application declares. It is enabled by `@EnableAutoConfiguration`, which is already included in the composite annotation `@SpringBootApplication`.

Example:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

When the application starts, Spring Boot reads configuration, inspects the classpath and registered beans, and applies matching auto-configurations. These configurations typically evaluate conditions such as:

- A specific class or library is present on the classpath.
- A property is enabled or set to a specific value.
- A required bean already exists or does not yet exist.
- The application is running in a matching environment type.

Auto-configuration is flexible. If the application declares its own bean where auto-configuration only creates one when none exists, the default configuration yields to the application-provided bean. This is known as the *back-off* mechanism.

For example, while Spring Boot can create a `ConnectionFactory` from `spring.r2dbc.*`, you usually do not need to write connection configuration yourself. If you have special requirements and define a custom `ConnectionFactory` bean, the default connection factory configuration backs off to use your bean.

## 2. Preparing Dependencies for Spring Data R2DBC

An R2DBC application needs at least two groups of components:

1. Spring Data R2DBC and Spring Boot's R2DBC integration.
2. The R2DBC driver for the specific database.

The example below uses PostgreSQL and Gradle. Assume the project already applies the Spring Boot Gradle plugin and Spring Boot dependency management:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    // Only needed if the application exposes an HTTP API using Spring WebFlux.
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

If the application has no HTTP API, you can omit `spring-boot-starter-webflux`. If the application already uses Spring MVC, keep the web stack that fits your current architecture; using R2DBC does not force you to migrate the entire application to WebFlux.

With Maven, the corresponding dependencies look like:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

The examples omit explicit versions because Spring Boot dependency management typically manages compatible versions. For projects not using Spring Boot's dependency management, you must manually select compatible versions of Spring Data, the R2DBC SPI, and the driver.

### 2.1. Distinguishing JDBC Drivers and R2DBC Drivers

JDBC drivers and R2DBC drivers are two different types of drivers. For example:

| Purpose | PostgreSQL |
| --- | --- |
| JDBC | `org.postgresql:postgresql` |
| R2DBC | `org.postgresql:r2dbc-postgresql` |

Adding only the PostgreSQL JDBC driver is not enough for Spring Data R2DBC to establish connections. The application needs a driver that implements the R2DBC SPI.

Similarly, connection URLs differ. R2DBC uses a driver-defined scheme such as `r2dbc:postgresql://...`; JDBC uses `jdbc:postgresql://...`.

## 3. Declaring Connection Configuration

Spring Boot reads R2DBC properties from the `spring.r2dbc` prefix. You can declare them in `application.properties`:

```properties
spring.application.name=shop-service

spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=shop_app
spring.r2dbc.password=${DB_PASSWORD:local-secret}
```

Or using YAML in `application.yml`:

```yaml
spring:
  application:
    name: shop-service
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD:local-secret}
```

In this example, the `shop` database must exist and PostgreSQL must be running. `DB_PASSWORD` can be supplied via an environment variable. The default value `local-secret` is only to make the example runnable locally; real environments should retrieve secrets from a secret management system or deployment configuration.

### 3.1. Properties to Know

| Property | Meaning |
| --- | --- |
| `spring.r2dbc.url` | R2DBC URL supported by the driver, specifying database type and connection address |
| `spring.r2dbc.username` | Database connection username |
| `spring.r2dbc.password` | Database connection password |
| `spring.r2dbc.name` | Database name, if supported by the driver and configuration style in use |
| `spring.r2dbc.properties.*` | Additional properties forwarded to connection factory configuration as supported by the driver |

Not every driver supports the exact same options. When configuring SSL, schema, application name, or other specialized properties, check the documentation for the corresponding driver.

### 3.2. Do Not Confuse R2DBC Configuration with JDBC Configuration

These two prefixes serve two different connection mechanisms:

```properties
# R2DBC
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop

# JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
```

Spring Boot does not automatically convert `spring.datasource.*` into `spring.r2dbc.*` or vice versa. If the application uses only Spring Data R2DBC, configure `spring.r2dbc.*` and add an R2DBC driver. If the application uses both JDBC and R2DBC, the two stacks may require separate connection and pool configurations.

## 4. Components Spring Boot Auto-Configures

When dependencies and configuration are valid, auto-configuration can set up the following core components. Exact names and detailed conditions may vary across Spring Boot versions, so consult the documentation for your specific version when deep customization is needed.

### 4.1. `ConnectionFactory`

`ConnectionFactory` is the primary R2DBC entry point for creating database connections. Spring Boot uses the URL and `spring.r2dbc.*` properties, together with the matching driver on the classpath, to build the connection factory.

Example with a URL:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
```

The `r2dbc:postgresql` scheme indicates that the configuration requires the PostgreSQL R2DBC driver. The driver is responsible for implementing the protocol and creating actual connections.

If the corresponding driver is missing, the URL is invalid, or the database is unreachable, the application may fail when creating the connection factory or opening a connection. Auto-configuration cannot compensate for a missing driver or a stopped database.

### 4.2. `DatabaseClient`

`DatabaseClient` is Spring Framework's low-level API for executing SQL reactively. It uses `ConnectionFactory` to interact with the database and supports parameter binding, reading results, and data mapping.

Example illustrating a query:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public class CustomerQueries {

    private final DatabaseClient databaseClient;

    public CustomerQueries(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<String> findNames() {
        return databaseClient.sql("SELECT name FROM customers")
                .map((row, metadata) -> row.get("name", String.class))
                .all();
    }
}
```

In a Spring application, you can inject `DatabaseClient` if auto-configuration created the corresponding bean. This example shows that the application does not have to manually open and close connections for every query.

### 4.3. `R2dbcEntityTemplate` and Mapping Infrastructure

Spring Data R2DBC provides `R2dbcEntityTemplate` to work with entities and aggregates following the Spring Data Relational approach. The mapping infrastructure uses entity metadata, converters, and the mapping context to convert between database rows and Java objects.

The template is helpful when you need flexible operations that the repository abstraction does not express conveniently. For common CRUD operations, repositories are usually the easier starting point.

### 4.4. Reactive Repositories

Spring Data R2DBC supports reactive repositories through interfaces like `ReactiveCrudRepository`. Spring Boot can enable repository configuration based on the classpath and the packages used as scan roots.

In a typical application, place repositories in the same package or subpackages of the `@SpringBootApplication` class so default scanning discovers them. You do not need to add `@EnableR2dbcRepositories` in the default setup.

Only use `@EnableR2dbcRepositories` when you need to customize the scan scope or repository configuration. If you configure it manually, specify packages explicitly and avoid duplicate repository registration.

### 4.5. Reactive Transaction Manager

When a `ConnectionFactory` and required conditions are met, Spring Boot can configure an `R2dbcTransactionManager` to manage reactive transactions. The application can use `@Transactional` on methods returning publishers or use `TransactionalOperator` to define transaction boundaries within a pipeline.

Reactive transactions propagate context through the Reactor Context. Therefore, keep operations belonging to a transaction within the same reactive pipeline and avoid calling `.block()` mid-flow.

## 5. Creating a Minimal R2DBC Application

This section puts the pieces together into a simple Spring Boot application.

### 5.1. Package Structure

You can organize the source code as follows:

```text
src/main/java/com/example/shop/
    ShopApplication.java
    customer/
        Customer.java
        CustomerRepository.java
        CustomerService.java
        CustomerController.java

src/main/resources/
    application.yml
    schema.sql
```

The `ShopApplication` class resides in the root package `com.example.shop`. The `customer` package is a subpackage, so it is discovered by default component scanning and repository scanning.

### 5.2. Main Application Class

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

In a basic setup, you do not need to call `ConnectionFactories.get(...)` yourself, manually instantiate `DatabaseClient`, or manually register each repository. Spring Boot sets up the infrastructure from the declared dependencies and properties.

### 5.3. Entity

```java
package com.example.shop.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

`@Table` specifies the table name and `@Id` marks the primary key. Remaining properties are mapped according to Spring Data Relational conventions or can be customized with corresponding mapping annotations.

### 5.4. Repository

```java
package com.example.shop.customer;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByNameContaining(String fragment);
}
```

Spring Data generates the repository implementation when the ApplicationContext initializes. You only declare the interface and query methods by convention; you do not have to write implementation classes for basic CRUD.

### 5.5. Service

```java
package com.example.shop.customer;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Flux<Customer> searchByName(String fragment) {
        return repository.findByNameContaining(fragment);
    }

    public Mono<Customer> findByEmail(String email) {
        return repository.findByEmail(email);
    }

    public Mono<Customer> create(String name, String email) {
        Customer customer = new Customer(null, name, email);
        return repository.save(customer);
    }
}
```

The service preserves reactive return types. `save()` returns `Mono<Customer>`; the saved object is emitted when persistence completes. Do not call `.block()` inside the service to obtain a synchronous result.

### 5.6. WebFlux Controller

If the project includes `spring-boot-starter-webflux`, the controller can return publishers directly:

```java
package com.example.shop.customer;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Customer> search(@RequestParam String name) {
        return service.searchByName(name);
    }

    @GetMapping("/email/{email}")
    public Mono<Customer> findByEmail(@PathVariable String email) {
        return service.findByEmail(email);
    }

    @PostMapping
    public Mono<Customer> create(@RequestBody CreateCustomerRequest request) {
        return service.create(request.name(), request.email());
    }

    public record CreateCustomerRequest(String name, String email) {
    }
}
```

The controller demonstrates how Spring WebFlux subscribes to the publisher and writes results to the HTTP response. For a production API, add appropriate validation, error handling, and response design.

## 6. Initializing the Schema Automatically with SQL Scripts

Auto-configuration creates connection and data access infrastructure; it does not automatically know which business tables to create. In development environments or small examples, Spring Boot can execute `schema.sql` and `data.sql` scripts on startup.

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE
);
```

You can add sample data in `src/main/resources/data.sql`:

```sql
INSERT INTO customers (name, email)
VALUES ('An Nguyen', 'an@example.com');
```

To instruct Spring Boot to run scripts on non-embedded databases, configure:

```properties
spring.sql.init.mode=always
```

The default mode and script execution order depend on the Spring Boot version and database type. When using initialization scripts, read the SQL initialization documentation for your exact project version.

Do not rely on simple initialization scripts as a long-term production migration mechanism if the schema will evolve across versions. For real systems, adopt a versioned schema migration strategy with controlled migration ordering and proper rollback procedures. A migration tool may use a separate JDBC connection even while the application accesses business data via R2DBC; configure and manage both connections explicitly.

## 7. Connection Pooling and Advanced Configuration

In environments with real traffic, applications typically use a connection pool to reuse connections. Spring Boot can configure a pooled connection factory when the appropriate R2DBC pooling library is on the classpath and pooling is enabled according to your Boot version's configuration.

Example of common pool properties:

```properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-idle-time=30m
```

Verify that these properties exist in your Spring Boot version and ensure the `r2dbc-pool` dependency is provided if the current starter does not bring it in. Do not copy pool settings across versions without checking configuration metadata or documentation.

`max-size` should be chosen based on database capacity, the number of application instances, and connections reserved for other services. Making the pool too large can overload the database; a larger pool does not automatically make queries faster.

When you need to customize how the connection factory is created, Spring Boot provides version-appropriate extension points, or the application can declare its own `ConnectionFactory` bean. Before replacing default configuration, pinpoint exactly which option falls short so you do not end up manually managing unnecessary components.

## 8. Things to Avoid When Using Auto-Configuration

### 8.1. Do Not Recreate Default Beans Unnecessarily

In a basic application, avoid manually declaring `ConnectionFactory`, `DatabaseClient`, templates, and repository factories all at once. Creating duplicate beans can cause auto-configuration to back off or leave the ApplicationContext with multiple conflicting candidates.

Start with standard dependencies and properties. Only add manual configuration when you have special requirements such as multiple databases, custom driver options, or isolated repository scopes.

### 8.2. Do Not Place the Main Class in an Overly Deep or Unrelated Package

By default, `@SpringBootApplication` uses the main class's package as the root for component scanning and derived packages for certain Spring Data configurations. If the main class lives in a narrow subpackage, services or repositories in sibling packages may not be discovered.

Example of a scan-friendly structure:

```text
com.example.shop
    ShopApplication.java
    customer
        CustomerService.java
        CustomerRepository.java
    order
        OrderService.java
```

If you cannot organize packages this way, explicitly configure component scan or repository scan scopes via the appropriate annotations.

### 8.3. Do Not Use the Wrong Driver or URL

The following cases commonly cause initialization failures:

- Adding only a JDBC driver while configuring `spring.r2dbc.url`.
- Using a `jdbc:postgresql://...` URL in the `spring.r2dbc.url` property.
- Using a URL scheme without a matching R2DBC driver on the classpath.
- Using a driver version incompatible with the R2DBC SPI or Spring Boot version in use.

Cross-check driver artifacts and URL schemes against the driver vendor's documentation.

### 8.4. Do Not Call `.block()` Inside Reactive Flows

Reactive repositories return `Mono` or `Flux`. Calling `.block()` on an event-loop thread can block request processing threads and degrade WebFlux throughput.

Compose publishers using `map`, `flatMap`, `zip`, and appropriate Reactor operators. If you must integrate blocking APIs, isolate the blocking work onto a suitable scheduler and bound concurrency.

### 8.5. Do Not Assume R2DBC and JDBC Share Transactions

If an application has both a JDBC `DataSource` and an R2DBC `ConnectionFactory`, Spring Boot may configure separate infrastructure for each. A JDBC transaction manager does not automatically manage R2DBC connections and vice versa.

Identify clearly which stack owns each data operation. If a business flow must update data across both stacks, design explicit consistency and error handling; do not assume a single `@Transactional` creates a distributed transaction.

## 9. Verifying That Auto-Configuration Worked Properly

After adding dependencies and properties, start the application and verify that the components work.

### 9.1. Inspecting Auto-Configuration Conditions

You can run the application with `--debug` to have Spring Boot print an auto-configuration condition evaluation report:

```bash
./gradlew bootRun --args='--debug'
```

The report shows which configurations matched, which did not, and which conditions were not satisfied. On Windows PowerShell, you can pass the same argument through your project's corresponding Gradle command.

To inspect further, you can enable DEBUG logging for Spring Boot's auto-configuration package. Limit such logging to development environments because detailed output can be very verbose.

### 9.2. Verifying Created Beans

During debugging, you can inspect the ApplicationContext to confirm required beans exist, such as:

- `ConnectionFactory` was created.
- `DatabaseClient` can be injected.
- Repository interfaces have proxy implementations.
- The appropriate transaction manager is registered if the application needs transactions.

Do not add debug endpoints to production just to inspect these beans. Use a debugger, test context, or the auto-configuration condition report instead.

### 9.3. Common Errors

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| Missing `ConnectionFactory` bean | Missing R2DBC driver, invalid URL, or auto-configuration not activated | Check dependencies, `spring.r2dbc.url`, and the condition report |
| Cannot connect to database | Database not running, wrong host/port, database name, or credentials | Check database status, network, and credentials |
| Repository bean not found | Repository outside scan scope or repository auto-configuration condition unmet | Check main class package, dependencies, and repository scanning |
| Table not found | Schema not created or initialization script did not run | Check `schema.sql`, `spring.sql.init.mode`, and database schema |
| Data type or mapping error | Incompatible column type or incorrect entity mapping | Compare SQL types, entity properties, and driver support |
| Pool exhausted or slow connection acquisition | Pool too small, connections not released properly, or overloaded database | Monitor pool metrics, query duration, and concurrency limits |

## 10. Testing Applications That Use R2DBC

Spring Boot provides testing utilities for Spring Data R2DBC. `@DataR2dbcTest` is suited for slice tests focused on mapping and repositories; `@SpringBootTest` is suited when testing the full application configuration and integrated components.

Conceptual repository test example:

```java
@DataR2dbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindCustomerByEmail() {
        // Prepare data in the test database,
        // call the repository and verify that the publisher emits the result.
    }
}
```

Real tests require a suitable R2DBC database, schema, and test data. Not every embedded database has an equivalent R2DBC driver. For production databases like PostgreSQL, you can use Testcontainers if the project has Docker and compatible drivers set up.

When testing publishers, use tools like `StepVerifier` to assert values, emission order, completion, and errors without calling `.block()` in application code.

## 11. Workflow for Initializing a New Project

You can follow this sequence:

1. Choose a Spring Boot version compatible with the project's JDK and libraries.
2. Add `spring-boot-starter-data-r2dbc`.
3. Add the R2DBC driver matching your database, such as PostgreSQL R2DBC.
4. If you need a reactive HTTP API, add Spring WebFlux; otherwise only add a web stack when needed.
5. Place the `@SpringBootApplication` class in the application's root package.
6. Declare `spring.r2dbc.url`, username, and password in environment-appropriate configuration.
7. Create entities and repositories in scanned packages.
8. Create the schema via initialization scripts or a migration tool.
9. Start the application and check the condition report if auto-configuration does not behave as expected.
10. Test repositories, transactions, and connectivity against a realistic database.

## 12. Overall Flow

```mermaid
flowchart TD
    A[Add Spring Data R2DBC starter] --> B[Add R2DBC driver]
    B --> C[Declare spring.r2dbc.*]
    C --> D[SpringApplication starts]
    D --> E[@EnableAutoConfiguration checks conditions]
    E --> F[Create ConnectionFactory]
    F --> G[Configure DatabaseClient and mapping infrastructure]
    G --> H[Scan and create repositories]
    H --> I[Application uses Mono / Flux]
    I --> J[Driver executes I/O with database]
```

The diagram shows the general sequence. Specific auto-configurations may be evaluated under different conditions and internal ordering depending on the Spring Boot version.

## 13. Conclusion

To initialize Spring Data R2DBC with Spring Boot auto-configuration, add the R2DBC starter, add the right driver, declare `spring.r2dbc.*`, and place your application class in a sensible root package. Spring Boot will automatically configure the connection factory and required Spring Data infrastructure when the corresponding conditions are satisfied.

You only need manual configuration when you have special requirements such as multiple databases, driver-specific options, or customized repository scopes. When encountering startup failures, inspect dependencies, the URL, package scanning, and the condition report before replacing all of auto-configuration. This keeps the application concise and maintainable while still allowing configuration to expand when real needs arise.
