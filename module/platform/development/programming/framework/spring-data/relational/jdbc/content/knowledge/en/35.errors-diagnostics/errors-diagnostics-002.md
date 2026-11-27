# Repository Not Found, Wrong Package Scan, or Duplicate Beans

Spring Data JDBC creates repository beans from interfaces extending CrudRepository, ListCrudRepository, or Repository. If the application cannot find a repository, throws NoSuchBeanDefinitionException, or fails on startup with duplicate bean errors, the cause usually lies in package scanning configuration, registering repositories multiple times, or bean name collisions.

Two commonly confused mechanisms must be distinguished:

- **Component scanning** discovers regular beans such as @Component, @Service, @Controller, and @Configuration.
- **Repository scanning** discovers repository interfaces and creates proxy beans through the Spring Data repository infrastructure.

A repository interface does not become a bean merely because its package sits under @SpringBootApplication or because the interface is annotated with @Repository. Spring Data must scan that interface using its repository registrar.

This guide explains how to identify which repository was not registered, configure package scanning properly, handle multiple DataSources, and prevent bean name collisions.

## 1. How does Spring Data JDBC register repositories?

Example repository:

~~~java
package com.example.orders.persistence;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data does not generate a developer-written implementation class. When repository scanning discovers the interface, the infrastructure creates a proxy bean to handle CRUD methods, derived queries, and declared query methods.

With Spring Boot, auto-configuration typically scans for repositories in the root package of the application configuration class and its subpackages. If you need to specify the scope explicitly, use @EnableJdbcRepositories.

High-level initialization flow:

~~~mermaid
flowchart TD
    A[Spring Boot starts up] --> B[Repository auto-configuration]
    B --> C[Determine base package]
    C --> D[Scan repository interfaces]
    D --> E[Register RepositoryFactoryBean]
    E --> F[Create repository proxy]
    F --> G[Inject into service]
~~~

If the interface lies outside the scan scope, no proxy bean is created. Any service injecting the repository will then fail with a missing bean error.

## 2. Component scan and repository scan are two separate mechanisms

Example package structure:

~~~text
com.example
  Application.java
  orders
    application/
      OrderService.java
    domain/
      PurchaseOrder.java
    persistence/
      PurchaseOrderRepository.java
  customers
    application/
      CustomerService.java
    persistence/
      CustomerRepository.java
~~~

If Application.java resides in package com.example, Spring Boot typically scans components and repositories in all subpackages. This is the most predictable layout.

Application configuration:

~~~java
package com.example;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

If the main class is placed too deep:

~~~text
com.example.bootstrap
  Application.java
com.example.orders.persistence
  PurchaseOrderRepository.java
~~~

package com.example.orders.persistence is not a subpackage of com.example.bootstrap. The repository may fall outside the default auto-configuration package scope.

Adding @ComponentScan or scanBasePackages may make @Service and @Configuration beans discoverable, but you should not assume it also configures repository scanning. Repository scanning has its own base package and registrar. Configure @EnableJdbcRepositories or place the application configuration in an appropriate root package.

## 3. Configuring repository scanning explicitly

You can use @EnableJdbcRepositories to explicitly specify packages containing repositories:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.orders.persistence"
)
public class OrdersJdbcRepositoryConfiguration {
}
~~~

Or use basePackageClasses to avoid hardcoding package names as Strings:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = PurchaseOrderRepository.class
)
public class OrdersJdbcRepositoryConfiguration {
}
~~~

basePackageClasses uses the package of the specified class as the scan starting point. This is generally safer during package refactoring because the compiler catches changes to the marker class.

When there are multiple repository packages, declare multiple base packages:

~~~java
@EnableJdbcRepositories(
        basePackages = {
                "com.example.orders.persistence",
                "com.example.customers.persistence"
        }
)
~~~

Only configure repository scanning where needed. If Spring Boot auto-configuration already scans the right package, adding another @EnableJdbcRepositories can register repositories twice or make the scan scope confusing.

## 4. Why doesn't @Repository on an interface fix a scan error?

Spring Data repository interfaces generally do not need @Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

The @Repository annotation is a stereotype for component scanning and exception translation on conventionally declared repository beans. However, a plain interface without an implementation cannot be turned into a bean by component scanning alone.

The Spring Data repository registrar must detect the interface and create a proxy. Therefore, when a repository is not found, check @EnableJdbcRepositories or the auto-configuration package before adding @Repository.

Also distinguish:

- @Repository on an application-written DAO class registers that class via component scanning.
- A Spring Data interface extending CrudRepository requires Spring Data repository scanning to create an implementation proxy.
- @Repository does not replace @EnableJdbcRepositories and does not fix an incorrect base package.

## 5. Common Errors and Their Meanings

| Error | Common meaning | What to check |
|---|---|---|
| NoSuchBeanDefinitionException for PurchaseOrderRepository | No bean exists with the requested type/name | Repository scan, package, profiles, and test slice |
| No qualifying bean of type PurchaseOrderRepository | No matching bean found for injection | Check whether the repository proxy was registered |
| UnsatisfiedDependencyException in service | Service bean cannot be created due to missing or failing repository dependency | Read the deepest cause in the stack trace |
| BeanDefinitionOverrideException | Two beans share the same name while bean overriding is disabled | Look for duplicate scan configs or same-named repositories |
| ConflictingBeanDefinitionException | Two bean definitions conflict during registration | Check same-named components/repositories |
| Ambiguous dependency / NoUniqueBeanDefinitionException | Multiple beans match one injection point | Use qualifier or separate configurations |
| Failed to configure a DataSource | DataSource/configuration failure happened before repositories | Check JDBC URL, driver, credentials, and profile |

Do not stop at the first UnsatisfiedDependencyException line. Read the caused-by chain down to the root exception; repository scan failures and database connection errors can surface at different layers.

## 6. Checking the application class package

Spring Boot typically uses the package of the @SpringBootApplication class as the root package for auto-configuration. Recommended structure:

~~~text
com.example
  Application.java
  config/
  orders/
    domain/
    application/
    persistence/
  customers/
    domain/
    application/
    persistence/
~~~

Placing Application in a shared parent package gives component scanning and repository auto-configuration a consistent scope.

Avoid placing the main class in a package that is too deep, such as:

~~~text
com.example.orders.application
  Application.java
~~~

if repositories or services reside in sibling packages such as com.example.customers. A sibling package is not a subpackage of the application package.

If you cannot change the main class package, use explicit configuration:

~~~java
@SpringBootApplication
public class Application {
    // ...
}

@Configuration
@EnableJdbcRepositories(
        basePackageClasses = {
                PurchaseOrderRepository.class,
                CustomerRepository.class
        }
)
class JdbcRepositoriesConfiguration {
}
~~~

If components/services also reside outside the component scan scope, configure component scanning separately. Do not conflate the two mechanisms into a single assumption.

## 7. Detecting repository scanning configured twice

A common cause of duplicate bean errors is an application using Spring Boot auto-configuration while also declaring multiple @EnableJdbcRepositories with overlapping scopes.

Example:

~~~java
@SpringBootApplication
public class Application {
}
~~~

and:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example"
)
public class JdbcRepositoryConfiguration {
}
~~~

If auto-configuration already scans com.example, the explicit configuration above can re-scan the same repositories.

How to resolve:

1. Determine whether repository scanning comes from auto-configuration or @EnableJdbcRepositories.
2. Inspect every configuration class annotated with @EnableJdbcRepositories.
3. Determine the basePackages/basePackageClasses scope of each configuration.
4. Keep one clear configuration per repository group and per DataSource.
5. Avoid configuring a broader scan scope than necessary.
6. Do not enable bean overriding merely to mask duplicate registration errors.

If multiple repository configurations are needed for multiple databases, place them in separate packages and bind each configuration to the proper JDBC operations and transaction manager.

## 8. Duplicate repository bean names across different packages

The default bean name of a repository is usually derived from the interface name. Two interfaces with the same simple name in different packages can generate identical bean names.

Example:

~~~text
com.example.billing.persistence.CustomerRepository
com.example.support.persistence.CustomerRepository
~~~

Both may try to register a bean named customerRepository. When loaded into the same application context, their bean names can collide.

The most maintainable solution is to name interfaces after their domain:

~~~java
public interface BillingCustomerRepository
        extends CrudRepository<BillingCustomer, Long> {
}

public interface SupportCustomerRepository
        extends CrudRepository<SupportCustomer, Long> {
}
~~~

Clear naming distinguishes bean names and ensures repository callers reflect the right bounded context.

If two repositories have different domain types but share the same interface name due to legacy history, consider renaming the interfaces. Do not rely on bean overriding so that one repository silently replaces the other.

## 9. Bean collision between a repository and a custom DAO

An application might accidentally declare a DAO class whose bean name collides with a repository:

~~~java
@Repository
public class PurchaseOrderRepository {
    // Application-written DAO implementation.
}
~~~

while also having a Spring Data interface:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Besides the fact that two classes/interfaces cannot share the same fully qualified name in one package, types with the same simple name in different packages can still produce conflicting bean names.

Name DAOs by their specific role:

- PurchaseOrderJdbcDao.
- PurchaseOrderReadDao.
- PurchaseOrderSearchMapper.
- PurchaseOrderLegacyGateway.

Reserve the Repository suffix for repository abstractions with clear aggregate contracts. Avoid naming every database-access class Repository, as it obscures ownership.

## 10. Bean exists, but injection is ambiguous

A repository may be registered, yet injection still fails because multiple beans match the requested type.

For example, a service depending on an overly broad abstraction:

~~~java
public class ExportService {
    private final CrudRepository<?, ?> repository;
}
~~~

If the context has multiple matching repository beans, Spring cannot tell which bean to choose.

Inject the concrete repository interface instead:

~~~java
@Service
public class OrderExportService {
    private final PurchaseOrderRepository orders;

    public OrderExportService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }
}
~~~

If multiple beans of the same type exist due to separate configurations, use @Qualifier:

~~~java
@Service
public class ReportingService {
    private final NamedParameterJdbcOperations reportingJdbc;

    public ReportingService(
            @Qualifier("reportingJdbcOperations")
            NamedParameterJdbcOperations reportingJdbc
    ) {
        this.reportingJdbc = reportingJdbc;
    }
}
~~~

@Primary can mark a default bean when multiple beans share a type, but only use it when a sensible default exists. With multiple repositories/domains or multiple databases, @Qualifier usually expresses intent more clearly.

## 11. Applications with Multiple DataSources

When an application connects to multiple databases, each repository group must be wired to the proper JDBC operations and transaction manager.

Example package layout:

~~~text
com.example
  Application.java
  orders/
    persistence/
      OrderRepository.java
  reporting/
    persistence/
      ReportRepository.java
  config/
    OrdersDatabaseConfiguration.java
    ReportingDatabaseConfiguration.java
~~~

Repository configuration for the orders database:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = OrderRepository.class,
        jdbcOperationsRef = "ordersJdbcOperations",
        transactionManagerRef = "ordersTransactionManager"
)
public class OrdersDatabaseConfiguration {
}
~~~

Configuration for the reporting database:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = ReportRepository.class,
        jdbcOperationsRef = "reportingJdbcOperations",
        transactionManagerRef = "reportingTransactionManager"
)
public class ReportingDatabaseConfiguration {
}
~~~

Referenced beans must exist and be wired consistently:

- DataSource for each database.
- Corresponding NamedParameterJdbcOperations.
- Corresponding TransactionManager.
- Appropriate MappingContext/DataAccessStrategy when configuring multiple JDBC repository contexts.
- Migrations/schemas for each database.

Bean names in the example are illustrative; they must match actual bean names. Never point repositories for database A to the JDBC operations or transaction manager of database B.

When using multiple DataSources, pay special attention to default auto-configuration. Explicitly designate which bean is primary if the application needs a default, and configure repository groups explicitly per data source.

## 12. Test slices do not scan repositories like the full application

A test using @DataJdbcTest may load only part of the ApplicationContext. If the test class sits in a package unrelated to the application's root package, or repository configuration lies outside the discovered scope, repository beans may be missing.

Example:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {
    @Autowired
    PurchaseOrderRepository repository;
}
~~~

If the repository is not found, check:

- Is the test class in a package aligned with the application configuration?
- Is there a custom @EnableJdbcRepositories configuration that needs to be imported?
- Are DataSource and mapping configurations included in the test slice?
- Are custom configuration beans/converters imported via @Import?
- Was repository auto-configuration accidentally excluded?

You can import required configurations:

~~~java
@DataJdbcTest
@Import(JdbcRepositoriesConfiguration.class)
class PurchaseOrderRepositoryTest {
}
~~~

Only import configurations that are genuinely needed. Do not turn a slice test into a full application context by adding broad @ComponentScan annotations if the goal is testing repository isolation.

## 13. Distinguishing scan errors from repository initialization errors

A repository may be discovered yet fail to initialize due to other errors:

- Domain entity cannot be mapped.
- Derived query method property path cannot be parsed.
- Query annotation has invalid syntax or mismatched parameters.
- MappingContext is missing a converter.
- DataSource cannot connect.
- Mismatched JDBC operations or transaction manager.
- Two repository configurations share the same bean name.

Thus, a message saying "repository bean could not be created" does not always mean package scanning is wrong. Identify the root exception:

| Root exception | Investigation direction |
|---|---|
| NoSuchBeanDefinitionException | Scan scope or bean reference |
| BeanDefinitionOverrideException | Duplicate bean name |
| NoUniqueBeanDefinitionException | Multiple beans of the same type |
| PropertyReferenceException | Derived query references nonexistent property |
| QueryCreationException | Invalid repository query |
| DataAccessResourceFailureException | Database/connection |
| MappingException or ConversionFailedException | Entity metadata/converter |

Read the full stack trace and check which bean was being created at the time of failure.

## 14. Inspecting repository beans at runtime

In development environments, you can inspect ApplicationContext bean definitions:

~~~java
@Component
public class RepositoryBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    public RepositoryBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names = context.getBeanNamesForType(
                PurchaseOrderRepository.class
        );

        System.out.println(
                "PurchaseOrderRepository beans: "
                        + Arrays.toString(names)
        );
    }
}
~~~

This is a temporary diagnostic helper; there is no need to keep this class in production unless operationally required.

You can use the Actuator beans endpoint in secured environments to inspect bean names and dependencies. Because this endpoint can expose internal configuration details, do not expose it publicly.

Enabling DEBUG logging for Spring Data repository configuration packages can reveal which packages the repository scanner searches and which interfaces it registers. Exact logger names may vary by version; start with org.springframework.data.repository.config and org.springframework.data.jdbc.repository.config.

## 15. Step-by-Step Diagnostic Workflow

When a service cannot inject a repository, follow this sequence:

1. Read the root exception at the bottom of the stack trace.
2. Confirm the repository interface extends Repository/CrudRepository with the right types.
3. Locate the package of the Application class and the package of the repository.
4. Identify the auto-configuration package used by Spring Boot.
5. Find all @EnableJdbcRepositories annotations in the project.
6. Verify basePackages and basePackageClasses.
7. Check whether multiple DataSources are configured.
8. Inspect repository scanner logs to confirm whether the interface is detected.
9. If the interface was detected, check query parsing, mapping, DataSource, and converter errors.
10. If the bean exists but injection is ambiguous, check bean types/names and use @Qualifier or rename the repository.
11. Run a minimal context test to reproduce the failure.
12. Remove duplicate scan configurations or overly broad package scans once the root cause is found.

Do not add a broad @ComponentScan across the entire root package before verifying where the repository registrar scans. Overly broad configurations can introduce duplicate beans and obscure the original failure.

## 16. Common Configuration Mistakes

| Configuration / issue | Consequence | Fix |
|---|---|---|
| Main class placed too deep in packages | Repositories in sibling packages are not scanned | Place main class in root package or configure basePackageClasses |
| Only adding @Repository to the interface | Repository proxy is still not created | Configure Spring Data repository scanning |
| Component scan is right but repository scan is wrong | Services exist but repositories are missing | Check @EnableJdbcRepositories/auto-configuration package |
| @EnableJdbcRepositories overlaps auto-config scope | Repositories may be registered twice | Choose one clear scanning mechanism |
| Two interfaces share the same simple name | Bean names may collide | Rename interfaces by domain |
| Repositories for two databases share config | Repositories use wrong DataSource or transaction manager | Separate packages and configure repository groups |
| Injecting an overly broad abstraction | Multiple repositories match | Inject concrete interface or use qualifier |
| Test slice does not import config | Custom repositories/converters missing from context | Import minimal required configuration |
| Using bean overriding to handle duplicates | One bean silently shadows the other | Fix registration source and bean naming |
| Query method references invalid property | Repository is scanned but initialization fails | Fix derived query or @Query |

## 17. Package and Bean Configuration Checklist

Before finalizing configuration, verify:

- The Application class sits in a shared parent package or has explicit scan configuration.
- Repository interfaces extend the proper Spring Data Repository abstraction.
- Repository packages lie within scanned base packages.
- Component scanning and repository scanning are treated as separate mechanisms.
- Multiple @EnableJdbcRepositories configurations do not unintentionally overlap.
- Repository interface simple names do not collide across different domain packages.
- No @Repository DAO class shares a bean name with a repository proxy.
- Injections use concrete types, not overly broad CrudRepository when multiple repositories exist.
- Each repository group uses the correct DataSource, JDBC operations, and transaction manager.
- Test slices import necessary configurations without scanning the entire application unnecessarily.
- Logs and Actuator diagnostics are used in a controlled manner.

## 18. Complete Configuration Example for a Single Database

A simple layout can rely on default auto-configuration:

~~~text
com.example
  Application.java
  orders/
    domain/
      PurchaseOrder.java
    application/
      PurchaseOrderService.java
    persistence/
      PurchaseOrderRepository.java
  customers/
    domain/
      Customer.java
    application/
      CustomerService.java
    persistence/
      CustomerRepository.java
~~~

Application:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Repository:

~~~java
package com.example.orders.persistence;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Service:

~~~java
package com.example.orders.application;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.persistence.PurchaseOrderRepository;
import org.springframework.stereotype.Service;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }
}
~~~

With root package com.example, Spring Boot automatically configures component and repository scanning for subpackages. There is no need to add @EnableJdbcRepositories if auto-configuration already covers the desired scope.

If repositories live outside com.example, add explicit repository scan configuration rather than assuming Spring will scan the entire classpath automatically.

## 19. Key Takeaways

- Spring Data JDBC creates proxy beans from repository interfaces via repository scanning.
- Component scanning and repository scanning are two distinct mechanisms.
- @Repository on an interface does not replace @EnableJdbcRepositories.
- The package of @SpringBootApplication affects the default package Spring Boot uses for auto-configuration.
- Use @EnableJdbcRepositories with basePackageClasses or basePackages when you need to specify scope explicitly.
- Avoid overlapping repository scan configurations with auto-configuration without reason.
- Two repository interfaces with the same simple name can cause bean name collisions; name them by domain.
- Use @Qualifier when multiple matching beans exist, and @Primary only when a sensible default applies.
- With multiple DataSources, wire each repository group to the correct jdbcOperationsRef and transactionManagerRef.
- Test slices may need to import custom repository or converter configurations.
- Read the root exception to distinguish scan errors, duplicate beans, query parsing, mapping, and database connection errors.
- Do not enable bean overriding to hide conflicts; fix the registration source and bean ownership.

When a repository cannot be found or beans collide, identify which mechanism is responsible for registering it. Place the application class in a sensible root package, configure repository scanning explicitly when needed, and clearly separate repository groups when multiple databases are used. Bean names and injection points should express specific domains so Spring creates the right proxies and the application avoids relying on bean overriding or overly broad scans.
