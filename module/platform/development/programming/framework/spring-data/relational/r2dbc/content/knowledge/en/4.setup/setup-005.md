# Manual Configuration and the Role of AbstractR2dbcConfiguration

Spring Data R2DBC needs a `ConnectionFactory` to create reactive connections to a database. On top of that foundation, Spring Data builds the components that map data rows to objects, execute SQL statements, provide entity-level APIs, and support repositories. In a Spring application that does not use Spring Boot auto-configuration, or when you need control over how connections and persistence components are created, you can declare manual Java configuration.

`AbstractR2dbcConfiguration` is the base configuration class of Spring Data R2DBC. The application extends this class and provides a `ConnectionFactory`; the base class registers the default infrastructure beans required for Spring Data R2DBC. As a result, you do not have to wire up the mapping context, converters, dialect, `DatabaseClient`, and `R2dbcEntityTemplate` by hand in standard setups.

## 1. Required Components in Manual Configuration

A Spring Data R2DBC configuration typically includes the following components:

| Component | Role |
|---|---|
| `ConnectionFactory` | Creates reactive connections to the database through the R2DBC driver. This is the foundational input for the remaining components. |
| `R2dbcDialect` | Supplies SQL and data type differences for the DBMS, such as how statements are generated and how specific types are handled. |
| `R2dbcMappingContext` | Stores mapping metadata between Java types, entities, tables, and columns. |
| `R2dbcConverter` and custom conversions | Converts values between database data types and the application's Java types. |
| `DatabaseClient` | Executes SQL and processes results through a lower-level reactive API. |
| `R2dbcEntityTemplate` | Provides an entity-level API for reading, writing, and querying data. |
| Repository infrastructure | Generates implementations for repository interfaces declared with Spring Data. |

These components work together. `ConnectionFactory` provides connections; the dialect and mapping metadata help Spring Data generate and interpret data operations; converters transform values; `DatabaseClient` executes SQL; and the template and repositories expose more convenient APIs for the application layer.

## 2. Declaring Configuration with AbstractR2dbcConfiguration

The example below configures an application using the PostgreSQL R2DBC driver. The host, database name, and credentials are illustrative only; in a real application, sensitive values should come from environment variables or a secret management system.

```java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

@Configuration
@EnableR2dbcRepositories(basePackages = "com.example.orders.repository")
public class R2dbcConfig extends AbstractR2dbcConfiguration {

    @Override
    @Bean
    public ConnectionFactory connectionFactory() {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
            .option(DRIVER, "postgresql")
            .option(HOST, "localhost")
            .option(PORT, 5432)
            .option(USER, System.getenv("DB_USER"))
            .option(PASSWORD, System.getenv("DB_PASSWORD"))
            .option(DATABASE, "orders")
            .build();

        return ConnectionFactories.get(options);
    }
}
```

Key points in this configuration are centered around the `connectionFactory()` method:

- `ConnectionFactory` belongs to the R2DBC SPI, not JDBC's `DataSource`.
- `ConnectionFactories.get(options)` locates the driver matching the `DRIVER` option and creates the driver-provided `ConnectionFactory`.
- Options such as host, port, database, and credentials describe how to connect. Specific drivers may support additional driver-specific options.
- `@Bean` registers the `ConnectionFactory` in the Spring application context so persistence beans can use it.

The application needs the corresponding R2DBC driver on the classpath—for example, the PostgreSQL R2DBC driver when using `DRIVER = "postgresql"`. Credentials in the example are read from environment variables; make sure those variables are set before launching the application.

`@EnableR2dbcRepositories` instructs Spring Data to scan repository packages and create implementation beans for matching interfaces. Replace `basePackages` with your project's actual package. If repository scanning is not enabled, the application can still access data via `DatabaseClient` or `R2dbcEntityTemplate`, provided those beans are configured.

## 3. What Does AbstractR2dbcConfiguration Do?

The `AbstractR2dbcConfiguration` class provides default configuration for Spring Data R2DBC infrastructure. Once the application supplies a `ConnectionFactory`, the base class uses it to set up commonly used persistence components.

### 3.1 Creating Data Access Beans

`DatabaseClient` is the abstraction for sending SQL to the database and handling results reactively. It is suited for writing SQL directly or explicitly controlling parameter binding and row-by-row result reading.

`R2dbcEntityTemplate` builds on the data access infrastructure to provide entity-oriented operations. Instead of writing all the mapping logic yourself for common operations, the application can use the template to insert, update, select, and delete objects based on declared metadata.

The repository infrastructure uses these components to back repositories such as `ReactiveCrudRepository`. That allows the business layer to depend on repository interfaces rather than managing connections and row mapping manually.

### 3.2 Setting Up the Mapping Context and Converters

`R2dbcMappingContext` stores metadata describing entities. Spring Data uses this metadata to determine table names, column names, identifier fields, and the structure of objects within an aggregate.

`R2dbcConverter` handles data conversion between the database and Java objects. For example, a numeric column can be converted to `Long`, `BigDecimal`, or an appropriate domain type, depending on the mapping and registered converters.

When the application has custom data types, you can register custom converters to define how those types are read and written. In Spring Data R2DBC versions that provide the `getCustomConverters()` hook, you can add converters in your configuration subclass:

```java
@Override
protected List<Object> getCustomConverters() {
    return List.of(
        new MoneyReadConverter(),
        new MoneyWriteConverter()
    );
}
```

`MoneyReadConverter` and `MoneyWriteConverter` are application-defined converters; they must implement the conversion directions expected by Spring Data. For example, a read converter might convert a `BigDecimal` value from the database into `Money`, while a write converter converts `Money` into `BigDecimal`. When using this hook, declare those converters and add the corresponding imports in your project.

### 3.3 Selecting the Dialect for the Database

SQL varies across database management systems. `R2dbcDialect` captures the differences Spring Data needs to know when generating certain SQL operations and handling data types. The base configuration uses dialect detection matching the `ConnectionFactory` when the driver is supported.

Therefore, `ConnectionFactory` must be created from the right R2DBC driver. If you use a driver or DBMS that Spring Data does not automatically recognize for dialect detection, check dialect support and provide the appropriate integration; do not assume every R2DBC driver automatically has a built-in Spring Data dialect.

## 4. Configuring Reactive Transactions

`ConnectionFactory` is also the basis for reactive transaction management. In a manual configuration, when the application needs Spring-managed transactions, you can register an `R2dbcTransactionManager`:

```java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;

@Bean
ReactiveTransactionManager transactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
```

This transaction manager coordinates transactions with `ConnectionFactory`. When using declarative transactions, Spring's transaction management configuration must also be enabled in the application (or auto-configured by Spring Boot). Database operations must stay inside a proper reactive flow so Spring can propagate the transaction context through the reactive chain.

Do not mix blocking operations or arbitrarily call `block()` inside a reactive transaction. Blocking the thread undermines non-blocking execution and can prevent the transaction context from being used as intended. When multiple operations must succeed or fail together, structure them within the same reactive transaction scope.

If Spring Boot already auto-configures a transaction manager for `ConnectionFactory`, do not register a duplicate bean with the same role without a clear reason. Inspect existing beans before adding manual configuration.

## 5. Spring Boot Auto-Configuration vs. Manual Configuration

In a Spring Boot application, standard cases do not require extending `AbstractR2dbcConfiguration`. With the appropriate starter and connection settings in `application.yml`, Spring Boot can create `ConnectionFactory` and configure Spring Data R2DBC infrastructure automatically.

Example connection configuration in `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Spring Boot reads these properties to build the connection configuration. The PostgreSQL R2DBC driver must still be present in dependencies. Repository scanning can also be auto-configured based on the application structure; if you need to restrict packages or change scanning behavior, you can declare `@EnableR2dbcRepositories`.

| Scenario | Appropriate approach |
|---|---|
| Standard Spring Boot app, single database, standard connection settings | Use `spring.r2dbc.*` and auto-configuration. |
| Spring Framework app without Spring Boot | Extend `AbstractR2dbcConfiguration`, provide `ConnectionFactory`, and enable repository scanning if needed. |
| Need custom converters or Spring Data mapping customization | Use Spring Data R2DBC extension points; extending `AbstractR2dbcConfiguration` is an option. |
| Need a custom `ConnectionFactory`, pooling, or driver-specific setup | Declare the bean manually and ensure Spring Data components use that factory. |
| Multiple databases or multiple `ConnectionFactory` beans | Configure each repository group and its corresponding data access beans explicitly; avoid pointing a repository at the wrong factory. |

Do not declare all beans manually while also leaving another auto-configuration active without checking bean creation conditions. Doing so can cause duplicate bean names, multiple `ConnectionFactory` instances, or repositories using the wrong `R2dbcEntityOperations`. Establish a single clear owner for each component and configure boundaries explicitly when multiple databases are involved.

## 6. What AbstractR2dbcConfiguration Does Not Do Automatically

Extending `AbstractR2dbcConfiguration` initializes Spring Data R2DBC infrastructure, but it does not manage the entire database lifecycle automatically.

- **Does not replace the R2DBC driver.** The application must still add the driver dependency matching the database.
- **Does not create or migrate schemas.** Creating tables, indexes, and schema changes requires a migration tool or dedicated schema management process.
- **Does not generate the domain model.** The application must still define entities, mappings, and aggregate boundaries.
- **Does not turn R2DBC into a full ORM.** The configuration class does not add a JPA-style persistence context, dirty checking, or proxy-based lazy loading.
- **Does not replace transaction design.** The application must still define transaction boundaries and organize operations inside reactive flows.
- **Does not guarantee every database has a compatible dialect.** You must use a driver and dialect supported by Spring Data or supply an appropriate integration.

## 7. Configuration and Verification Sequence at Initialization

When setting up R2DBC manually, you can follow this sequence:

1. Add the R2DBC SPI and driver for the target database management system.
2. Create a `ConnectionFactory` with the appropriate driver, host, port, database, and credentials.
3. Extend `AbstractR2dbcConfiguration` and override `connectionFactory()` so Spring Data has the input needed to build its infrastructure.
4. Enable `@EnableR2dbcRepositories` if the application uses repositories, specifying the packages to scan.
5. Add custom converters or transaction configuration when required by business needs.
6. Start the application and verify bean creation, database connectivity, a simple query, and real repositories.

If the application starts up but queries fail, identify which category the error belongs to: missing driver on the classpath, wrong connection options, unreachable database, unrecognized dialect, mapping mismatch with the schema, or repositories not being scanned. Categorizing errors by layer helps address the responsible component directly.

`AbstractR2dbcConfiguration` therefore serves as the bridge between an R2DBC `ConnectionFactory` and Spring Data R2DBC infrastructure. The application only needs to supply the factory along with any needed customizations; the base class prepares the default mapping and data access components so templates and repositories can work. In Spring Boot, prefer auto-configuration for typical cases and switch to manual configuration only when the application needs specific control or extension points.
