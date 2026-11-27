# Repository Scanning and Wiring to R2DBC Infrastructure

## 1. How Are Repositories Discovered and Connected to R2DBC?

In Spring Data R2DBC, a repository is usually just an interface declaring data operations. For example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

This interface neither opens connections itself nor contains SQL implementation code. When the application starts, Spring Data finds repository interfaces in configured packages, creates proxy implementations, and wires those proxies to the R2DBC data access infrastructure.

The component chain can be visualized as follows:

~~~text
Spring Boot application / @EnableR2dbcRepositories
                    |
                    v
        Scan repository interfaces
                    |
                    v
       Repository factory creates proxy
                    |
                    v
          R2dbcEntityOperations
         (usually R2dbcEntityTemplate)
                    |
             +------+------+
             |             |
             v             v
      MappingR2dbcConverter  DatabaseClient
             |             |
             +------+------+
                    |
                    v
             ConnectionFactory
                    |
                    v
               R2DBC Driver
                    |
                    v
            Relational Database
~~~

Each component has a specific responsibility:

- **Repository scanning** finds interfaces and registers repository beans.
- **Repository proxy/factory** generates implementations for CRUD methods, derived queries, and declared queries.
- **R2dbcEntityOperations** provides entity read/write operations; the common implementation is **R2dbcEntityTemplate**.
- **MappingR2dbcConverter** converts between data rows and Java objects according to mapping metadata.
- **DatabaseClient** executes SQL, binds parameters, and reads results from R2DBC.
- **ConnectionFactory** supplies connections via the R2DBC SPI; the specific driver communicates with the database.

Understanding this chain helps troubleshoot common issues: repositories not found, proxies lacking matching infrastructure beans, multiple ConnectionFactory beans causing ambiguity, or repositories pointing to the wrong database.

## 2. What Does Repository Scanning Look For?

Repository scanning searches for **repository interfaces** meeting Spring Data rules within the specified packages. For example:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── Customer.java
│   └── CustomerRepository.java
├── order
│   ├── Order.java
│   └── OrderRepository.java
└── config
    └── R2dbcConfiguration.java
~~~

In a Spring Boot application with a **@SpringBootApplication** class in the root package **com.example.shop**, default auto-configuration can detect repositories located in the root package and its subpackages.

Important distinction:

- Repository scanning finds interfaces such as **CustomerRepository**.
- Entity mapping uses metadata from types such as **Customer**, commonly annotated with **@Table**.
- The database schema contains actual tables such as **customers**.

**Repository scanning does not scan the database for tables**, nor does it automatically create tables. Spring Data does not read the entire schema and generate repositories for each table. Tables are identified through mapping metadata or SQL declared by the application; creating and altering the schema is typically handled by migrations or a database initialization process.

## 3. Minimal Repository and Entity Structure

Entity example:

~~~java
package com.example.shop.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {}
~~~

Repository:

~~~java
package com.example.shop.customer;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

Spring Data can generate implementations for CRUD operations inherited from **ReactiveCrudRepository** and derive queries from method names like **findByEmail**, provided the types and properties are validly mapped.

A repository does not require the **@Repository** annotation in standard cases. Interface discovery and proxy creation are performed by the repository infrastructure. Adding **@Repository** to an interface does not replace repository scanning configuration.

## 4. Spring Boot Auto-Configuration for a Single R2DBC Database

For a single primary database, Spring Boot is usually the most concise way to set everything up.

### 4.1. Declaring Dependencies

Gradle Groovy DSL example for PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

The starter provides Spring Data R2DBC integration. The PostgreSQL driver provides connections via the R2DBC SPI. Use Spring Boot dependency management to select compatible versions.

### 4.2. Connection Configuration

In application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: app
    password: ${DB_PASSWORD}
~~~

Spring Boot can use the URL and credentials to configure **ConnectionFactory**, then create the required R2DBC components if the application does not define custom replacement beans.

Never commit real passwords into source code. Supply values through environment variables or the deployment environment's secret store.

### 4.3. Placing the Application Class in the Root Package

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

If **CustomerRepository** is in **com.example.shop.customer**, that package is a subpackage of **com.example.shop**, so the repository can be discovered by Spring Boot's default configuration.

With a standard single-database structure, you do not need to add **@EnableR2dbcRepositories** just to scan default subpackages. Only configure it explicitly when you need to change scan scope, control packages, or bind repositories to a specific R2DBC infrastructure set.

## 5. Explicit Repository Scanning Configuration with @EnableR2dbcRepositories

Spring Data R2DBC provides the **@EnableR2dbcRepositories** annotation in the package:

~~~java
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;
~~~

This annotation enables the repository infrastructure and lets you specify packages containing repository interfaces.

### 5.1. Using basePackages

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackages = {
                "com.example.shop.customer",
                "com.example.shop.order"
        }
)
class RepositoryConfiguration {
}
~~~

**basePackages** accepts package names as strings. This makes it easy to configure multiple packages, though because package names are strings, renaming a package might not be updated everywhere by an IDE.

### 5.2. Using basePackageClasses

A safer option is to use marker classes:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = {
                CustomerRepository.class,
                OrderRepository.class
        }
)
class RepositoryConfiguration {
}
~~~

Spring Data uses the packages containing the specified classes as scan starting points. This provides compile-time type checking and is convenient when refactoring packages.

You can create a dedicated marker class if you want to avoid coupling configuration to a specific repository:

~~~java
package com.example.shop.customer;

public interface CustomerRepositoryPackage {
}
~~~

Then use:

~~~java
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepositoryPackage.class
)
~~~

The marker only needs to sit inside the package you want to scan; it is not a repository and does not need to extend any Spring Data interface.

### 5.3. When Is the Explicit Annotation Needed?

You may use **@EnableR2dbcRepositories** when:

- Repositories reside outside the root package of the **@SpringBootApplication** class.
- The application has multiple repository groups and needs package separation.
- The application has multiple databases or multiple **R2dbcEntityOperations** beans.
- You want to specify which entity operations bean a group of repositories uses.
- The application does not rely on Spring Boot's default auto-configuration.

Avoid accidentally placing the annotation on multiple configurations that scan the same package. Duplicate repository registration can cause bean conflicts or make it unclear which configuration owns a repository.

## 6. Which Infrastructure Is the Repository Proxy Wired To?

When a repository interface is discovered, Spring Data creates a proxy implementing that interface. The proxy handles repository methods using the repository factory and corresponding persistence components.

For example, the call:

~~~java
customerRepository.findById(10L);
~~~

is handled conceptually as follows:

1. The proxy receives the repository method call.
2. The repository infrastructure determines the operation to execute.
3. The repository uses the configured entity operations.
4. Mapping metadata of **Customer** determines the table and columns.
5. DatabaseClient builds and executes SQL via ConnectionFactory.
6. MappingR2dbcConverter converts result rows into Customer instances.
7. The repository emits the result via **Mono<Customer>**.

For derived queries, Spring Data parses the method name and property metadata to build the query. With **@Query**, the SQL statement is declared explicitly. Both still use the R2DBC infrastructure wired to the repository.

A repository proxy does not hold a JDBC-style EntityManager or persistence context like JPA. Spring Data R2DBC's model is based on reactive database operations and per-operation entity mapping.

## 7. Binding Repositories to R2dbcEntityTemplate

### 7.1. R2dbcEntityOperations Is the Entity Operations Abstraction

**R2dbcEntityTemplate** implements the **R2dbcEntityOperations** abstraction. The repository infrastructure uses entity operations to execute CRUD and entity-mapped queries.

In a typical configuration, the default template bean is named:

~~~text
r2dbcEntityTemplate
~~~

The **entityOperationsRef** attribute on **@EnableR2dbcRepositories** lets you specify the entity operations bean that a repository group should use. By default, repository scanning typically binds to the bean named **r2dbcEntityTemplate**.

For example:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class,
        entityOperationsRef = "r2dbcEntityTemplate"
)
class CustomerRepositoryConfiguration {
}
~~~

With a single database, the default name is usually sufficient and **entityOperationsRef** does not need to be redeclared. This attribute becomes important when an application has multiple templates.

### 7.2. Distinguishing DatabaseClient and R2dbcEntityTemplate

| Component | Role |
|---|---|
| **ConnectionFactory** | Provides R2DBC connections from the driver |
| **DatabaseClient** | Executes SQL, binds values, and reads rows |
| **R2dbcMappingContext** | Stores entity and property mapping metadata |
| **MappingR2dbcConverter** | Converts between rows/values and Java objects |
| **R2dbcEntityTemplate** | Combines client and mapping to provide entity operations |
| **ReactiveCrudRepository proxy** | Provides repository API built on top of entity operations |

If you need to write SQL directly, use DatabaseClient. If you want to work with entities, Criteria, and mapping metadata, use R2dbcEntityTemplate. Repositories are a higher-level abstraction for operations tied to aggregates/entities.

## 8. Manual Configuration with AbstractR2dbcConfiguration

Not every application uses Spring Boot auto-configuration. In plain Spring Framework applications or when full control over R2DBC configuration is needed, you can extend **AbstractR2dbcConfiguration**.

Configuration skeleton example:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;

@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class
)
class R2dbcConfiguration extends AbstractR2dbcConfiguration {

    @Override
    public ConnectionFactory connectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:local-password@localhost:5432/shop"
        );
    }
}
~~~

The example uses an illustrative URL for local usage. In real applications, credentials should be loaded from external configuration rather than hardcoded in source code.

**AbstractR2dbcConfiguration** provides the core Spring Data R2DBC configuration components based on ConnectionFactory. You can override configuration hooks when you need to register custom conversions or customize mapping.

If your application already uses Spring Boot auto-configuration, avoid creating a full manual configuration alongside it without understanding which beans are being registered. Two configuration sources may conflict or cause auto-configuration to back off. Choose one consistent configuration approach per R2DBC infrastructure set.

## 9. Wiring Multiple Repository Groups to Multiple Databases

An application may use multiple relational databases, for example:

- Customer database holding customer profiles.
- Order database holding orders.
- Reporting database serving reporting queries.

In this situation, do not let all repositories share one default template if they need to connect to different databases. Create separate infrastructure sets and wire each repository group to the right **R2dbcEntityOperations**.

### 9.1. Separating Packages by Database

~~~text
com.example.app
├── customer
│   └── CustomerRepository.java
├── order
│   └── OrderRepository.java
└── config
    ├── CustomerDatabaseConfiguration.java
    └── OrderDatabaseConfiguration.java
~~~

Customer repository scanning configuration:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class,
        entityOperationsRef = "customerR2dbcEntityTemplate"
)
class CustomerDatabaseConfiguration {
}
~~~

Order repository scanning configuration:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = OrderRepository.class,
        entityOperationsRef = "orderR2dbcEntityTemplate"
)
class OrderDatabaseConfiguration {
}
~~~

Here, each repository group is bound to a differently named template bean. The application must provide those beans along with the ConnectionFactory, DatabaseClient, and mapping converter matching the respective database.

### 9.2. Creating Separate DatabaseClient Beans for Each ConnectionFactory

Client declaration example:

~~~java
@Bean("customerDatabaseClient")
DatabaseClient customerDatabaseClient(
        @Qualifier("customerConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Similarly, the order database has its own client:

~~~java
@Bean("orderDatabaseClient")
DatabaseClient orderDatabaseClient(
        @Qualifier("orderConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Each DatabaseClient must use its corresponding ConnectionFactory. Never use a client for one database and accidentally wire it into the template of another database.

### 9.3. Creating Separate Templates and Wiring via entityOperationsRef

You can build a template from a DatabaseClient and an appropriate converter:

~~~java
@Bean("customerR2dbcEntityTemplate")
R2dbcEntityTemplate customerR2dbcEntityTemplate(
        @Qualifier("customerDatabaseClient")
        DatabaseClient databaseClient,
        @Qualifier("customerR2dbcConverter")
        R2dbcConverter converter) {

    return new R2dbcEntityTemplate(databaseClient, converter);
}
~~~

Similarly for the order database:

~~~java
@Bean("orderR2dbcEntityTemplate")
R2dbcEntityTemplate orderR2dbcEntityTemplate(
        @Qualifier("orderDatabaseClient")
        DatabaseClient databaseClient,
        @Qualifier("orderR2dbcConverter")
        R2dbcConverter converter) {

    return new R2dbcEntityTemplate(databaseClient, converter);
}
~~~

The snippet above focuses on showing the wiring between client, converter, and template. In a real configuration, you must provide the corresponding converter/mapping context beans and ensure they use the dialect, custom conversions, and metadata appropriate for each database. You can use dedicated configurations extending Spring Data R2DBC configuration to manage these components.

When multiple beans of the same type exist, use **@Qualifier** or **@Primary** deliberately. Do not rely on bean initialization order to determine which database a repository connects to.

### 9.4. Why entityOperationsRef Matters

Suppose both templates have type **R2dbcEntityTemplate**. If repositories are not explicitly bound, Spring may fail to determine which template to use, or repositories may end up using an unintended default bean.

**entityOperationsRef** states explicitly:

- CustomerRepository uses **customerR2dbcEntityTemplate**.
- OrderRepository uses **orderR2dbcEntityTemplate**.

The name in the annotation must match the bean name exactly. If the bean does not exist or the name is misspelled, the application will fail when initializing the repository infrastructure.

### 9.5. Transaction Managers Also Need to Be Separated per Database

If each database has its own ConnectionFactory and needs independent transactions, a matching R2DBC transaction manager is required for each ConnectionFactory. When multiple transaction managers exist, transaction boundaries must specify the right manager—for example via a qualifier or transaction manager name in **@Transactional** according to application configuration.

A transaction manager tied to the customer database does not automatically manage operations on the order database. Nor does a single **@Transactional** annotation create a distributed transaction across multiple databases. If business logic requires consistency across multiple databases, design an appropriate mechanism such as an outbox or saga instead of assuming a single local transaction covers everything.

## 10. Custom Repository Fragments and R2DBC Infrastructure

When derived queries or **@Query** are not flexible enough, you can add a custom repository fragment. A fragment consists of a separate interface declaring custom behavior and an implementation using a template or DatabaseClient.

Fragment interface example:

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> searchByName(String keyword);
}
~~~

Main repository combining the fragment:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Implementation following the default **Impl** suffix convention:

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final R2dbcEntityTemplate template;

    public CustomerSearchRepositoryImpl(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Override
    public Flux<Customer> searchByName(String keyword) {
        return template.select(
                Query.query(Criteria.where("name").like("%" + keyword + "%")),
                Customer.class
        );
    }
}
~~~

This example illustrates how a fragment uses the injected template. For inputs containing wildcard characters or complex search requirements, clearly define LIKE semantics and escaping. Do not concatenate user values into a SQL string; in the Criteria API, values are passed as data conditions.

Repository scanning discovers the main repository; Spring Data composes fragment implementations according to configuration conventions. A fragment does not create a new ConnectionFactory. It uses the injected infrastructure, so whichever database group a repository belongs to, the template received by its fragment must also belong to that group.

## 11. Query Methods and @Query Share the Same Repository Infrastructure

### 11.1. Derived Queries

~~~java
Flux<Customer> findByStatus(String status);
Mono<Customer> findByEmail(String email);
Mono<Boolean> existsByEmail(String email);
Mono<Long> countByStatus(String status);
~~~

Spring Data parses method names and entity properties to construct queries. The repository proxy executes them through the wired entity operations.

Property names in methods are Java property names, not SQL column names when the two differ. For instance, if an entity has property **email** mapped to **email_address**, a derived query method should be based on the **email** property.

### 11.2. Explicit Queries

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    """)
Flux<Customer> findActiveCustomers(String status);
~~~

With **@Query**, SQL is declared directly. The repository is still created by the scanning infrastructure and still uses the wired R2DBC configuration. However, table/column names in raw SQL must match the schema and dialect; entity mapping does not automatically rewrite arbitrary custom SQL.

When you need to control parameter names, you can use **@Param**:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :customerStatus
    """)
Flux<Customer> findByStatus(
        @Param("customerStatus") String status
);
~~~

Do not embed inputs directly into the SQL string. Use bind parameters for data values.

## 12. Repository Scanning Does Not Automatically Create Tables

A common misconception is that adding a repository interface and **@Table** will make Spring automatically create tables on startup. Repository scanning only creates repository beans; mapping metadata only describes how an entity relates to tables/columns.

Schema creation requires a separate mechanism:

- Migrations using Flyway or Liquibase.
- Database initialization scripts in development environments.
- A separately managed DDL workflow.
- A schema creation mechanism actively configured by the project.

An entity example:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {}
~~~

does not guarantee that the customers table already exists. If a repository executes a query on a table that has not been created yet, the database will return a relation/table not found error.

In an R2DBC application, migrations may use JDBC depending on the tool and configuration. That does not mean the application's runtime data access path has to switch to JDBC. Migrations and runtime persistence are two separate responsibilities.

## 13. Common Errors in Repository Scanning and Infrastructure Wiring

| Symptom | Common cause | Resolution |
|---|---|---|
| Repository cannot be injected | Package lies outside scanning scope | Place package under root package or configure **@EnableR2dbcRepositories** |
| No repository bean on startup | Repository auto-configuration disabled or missing infrastructure prerequisites | Check dependencies, repositories configuration, and ConnectionFactory |
| Cannot create repository proxy | Missing entity operations/template or incorrect repository configuration | Check **R2dbcEntityTemplate**, **entityOperationsRef**, and factory configuration |
| No ConnectionFactory | Missing R2DBC driver or invalid URL | Check runtime dependencies and **spring.r2dbc.url** |
| Multiple ConnectionFactory beans causing ambiguity | Spring does not know which bean to pick | Use **@Primary**, **@Qualifier**, and separate repository configurations |
| Repository runs but hits wrong database | **entityOperationsRef** points to wrong template or template uses wrong client | Trace template → DatabaseClient → ConnectionFactory chain |
| Template bean not found | Bean name does not match **entityOperationsRef** | Align bean name with annotation value |
| Table/column not found | Mapping metadata does not match schema or migrations have not run | Check **@Table**, **@Column**, naming strategy, and schema |
| Query method not created | Property name in method does not exist or query derivation unsupported | Verify Java property names and use **@Query** when needed |
| Duplicate repository registration | Multiple configurations scanning the same package | Separate packages clearly and remove overlapping scan configs |
| Custom fragment not attached to repository | Wrong implementation name or package not discovered | Check fragment name, Impl suffix, and package |
| Transaction uses wrong database | Transaction manager bound to a different ConnectionFactory | Specify the right transaction manager for the operation group |

### 13.1. Repository Outside the Root Package

For example, the application class is in **com.example.shop**, while the repository is in **org.company.shared.customer**. The repository package is not a subpackage, so default auto-scan may not discover it.

You can specify:

~~~java
@EnableR2dbcRepositories(
        basePackages = "org.company.shared.customer"
)
~~~

Or use **basePackageClasses** with a marker inside that package.

### 13.2. Missing R2DBC Driver

An application might have repository interfaces and the starter, yet lack a database driver. In that case Spring cannot create a suitable ConnectionFactory. Check the runtime classpath, not just the compile classpath.

### 13.3. Multiple Templates Without Specifying the Bean

When an application has multiple databases, each repository package must be bound to its corresponding template. Check **entityOperationsRef** and bean names before investigating SQL. A repository created successfully but bound to the wrong template can cause very subtle data issues.

### 13.4. Confusing JPA Annotations with R2DBC

Spring Data R2DBC uses relational mapping such as **@Table**, **@Id**, **@Column**, and **ReactiveCrudRepository**. Do not use **@EnableJpaRepositories**, **EntityManager**, or assume JPA's **@Entity** configures R2DBC repositories.

If an application uses both JPA and R2DBC concurrently, cleanly separate repository packages, entity mappings, and transaction managers for each technology.

## 14. Testing Repository Scanning and Wiring

An integration test should verify not only that the application context starts, but also that repositories are created and can access the database.

Example checking the repository bean:

~~~java
@SpringBootTest
class CustomerRepositoryWiringTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void repositoryShouldBeInjected() {
        assertThat(customerRepository).isNotNull();
    }
}
~~~

This test only verifies that the bean is registered. It does not prove that ConnectionFactory or SQL works.

You can add data access tests against a real database or Testcontainers:

~~~java
@Test
void shouldReadCustomerFromDatabase() {
    StepVerifier.create(customerRepository.findById(1L))
            .expectNextMatches(customer -> customer.id().equals(1L))
            .verifyComplete();
}
~~~

To test wiring more thoroughly, verify that:

- Repositories are injected from the expected packages.
- Entity mappings point to the correct tables and columns.
- Repositories use the intended template/database.
- ConnectionFactory can connect to the database.
- Actual queries execute and return the expected data types.
- The proper transaction manager is used if tests involve transactions.
- With multiple databases, repositories in each package access their corresponding database.

Tests using mocks can check service logic, but do not catch package scan, bean qualifier, dialect, SQL, or driver issues the way integration tests do.

## 15. Configuration Checklist from Repository to Database

When setting up a new repository, you can go in this order:

1. Identify the package containing the repository interface.
2. Confirm that package is within Spring Boot's default scan scope or configure **@EnableR2dbcRepositories**.
3. Declare the repository extending **ReactiveCrudRepository** or an appropriate Spring Data interface.
4. Ensure the entity has mapping metadata such as **@Table** and **@Id**.
5. Provide the R2DBC driver and configure the database URL/credentials properly.
6. Verify **ConnectionFactory** is created.
7. Verify **DatabaseClient**, mapping converter, and **R2dbcEntityTemplate** are configured.
8. If there are multiple templates, set **entityOperationsRef** accurately for each repository package.
9. If there are multiple ConnectionFactory beans, use qualifiers/primary and separate transaction managers intentionally.
10. Run migrations to ensure tables and columns exist.
11. Test repository beans and actual queries using a compatible database.

You can check against the following diagram:

~~~text
Repository interface scanned?
              |
         +----+----+
         |         |
         No       Yes
         |         |
         v         v
 Fix package /   Repository proxy
 Enable annot.     created?
                      |
                 +----+----+
                 |         |
                 No       Yes
                 |         |
                 v         v
          Check factory,  Entity operations
          template, ref     wired?
                               |
                          +----+----+
                          |         |
                          No       Yes
                          |         |
                          v         v
                  Check bean name, ConnectionFactory
                  qualifier           and driver
                                           |
                                           v
                                     Actual query
                                           |
                                           v
                                   Maps entity right?
~~~

## 16. Conclusion

Repository scanning is the step where Spring Data discovers repository interfaces and generates proxies for the application to use. With Spring Boot, packages beneath the **@SpringBootApplication** class are typically scanned by default configuration. When you need package control or separation across multiple databases, use **@EnableR2dbcRepositories** with **basePackages**, **basePackageClasses**, and **entityOperationsRef**.

The repository proxy is wired to **R2dbcEntityOperations**, usually **R2dbcEntityTemplate**. The template uses the mapping converter and DatabaseClient; DatabaseClient relies on ConnectionFactory and the R2DBC driver to execute SQL. This wiring chain determines which tables and database a repository interacts with.

Remember that repository scanning does not create tables nor discover the entire schema automatically. Entity mapping, connection infrastructure, and schema migrations are separate parts that must be configured together consistently. When an application has multiple databases, separating repository packages and wiring each group to its corresponding template, ConnectionFactory, and transaction manager helps prevent accessing the wrong data and keeps configuration manageable.
