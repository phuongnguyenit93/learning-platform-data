# Providing Dynamic Connection Properties for Test Environments

When testing a Spring Data R2DBC application, database connection details are often known only at test runtime. For example, Testcontainers starts PostgreSQL in a container and assigns a random host port. The application must receive the right host, port, database, username, and password before Spring creates the ConnectionFactory.

Spring Test provides **@DynamicPropertySource** and **DynamicPropertyRegistry** to register properties computed dynamically during ApplicationContext initialization. Combined with Testcontainers, this lets tests use a real containerized database without hard-coding ports or writing connection details into configuration files.

In a Spring Boot application using R2DBC auto-configuration, the key properties are typically spring.r2dbc.url, spring.r2dbc.username, and spring.r2dbc.password. Pool properties sit under spring.r2dbc.pool.* when the project uses r2dbc-pool and the Spring Boot version supports them.

Keep in mind that an R2DBC URL differs from a JDBC URL. A PostgreSQL container can supply a JDBC URL, but you cannot assign that URL directly to spring.r2dbc.url. You must construct an R2DBC driver URL or build matching ConnectionFactoryOptions.

## 1. Why Are Dynamic Properties Needed in Tests?

A static local configuration might look like:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/app_test
    username: test
    password: test
~~~

This configuration only works if a database is always running at localhost:5432 with the exact database name and credentials. In CI or when running multiple tests in parallel, ports can differ, databases may be created per run, and containers may exist only for the test lifecycle.

With Testcontainers, connection details are typically assigned when the container starts:

- The host may be localhost or an address provided by the container runtime.
- The port inside the container is mapped to an available port on the host.
- The database name, username, and password are configured for the container.
- The container is ready only after startup and health checks finish.

Therefore, properties must be generated from the container's runtime details rather than relying on fixed ports.

### 1.1. Dynamic Configuration Must Exist Before Spring Creates ConnectionFactory

Spring Boot creates ConnectionFactory from configuration when the ApplicationContext initializes. If a test waits until a test method runs to change properties, ConnectionFactory may already have been created with old values.

Register dynamic properties during TestContext preparation so Spring can read those values before initializing beans that depend on database configuration.

Do not do this:

~~~java
@BeforeEach
void setProperties() {
    System.setProperty(
        "spring.r2dbc.url",
        "r2dbc:postgresql://localhost:5432/app_test"
    );
}
~~~

@BeforeEach runs after the test context has typically already been created. Changing properties then does not guarantee ConnectionFactory uses the new value.

## 2. Using Testcontainers and @DynamicPropertySource

The example below uses a PostgreSQL Testcontainer and a Spring Boot integration test.

Typical test dependencies:

~~~gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

If the project manages dependencies with Maven, declare the corresponding artifacts in pom.xml. Use a Testcontainers version compatible with your Spring Boot and Java versions, ideally through a BOM or project dependency management.

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class CustomerRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void r2dbcProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + postgres.getHost()
                + ":"
                + postgres.getMappedPort(
                    PostgreSQLContainer.POSTGRESQL_PORT
                )
                + "/"
                + postgres.getDatabaseName()
        );

        registry.add(
            "spring.r2dbc.username",
            postgres::getUsername
        );

        registry.add(
            "spring.r2dbc.password",
            postgres::getPassword
        );
    }

    @Test
    void repositoryCanReadFromContainerDatabase() {
        // Perform repository/service test assertions.
    }
}
~~~

Key pieces:

- @Testcontainers enables Testcontainers JUnit 5 integration.
- @Container marks the container managed by the test lifecycle.
- static container starts once for the test class.
- @DynamicPropertySource registers dynamic configuration values.
- DynamicPropertyRegistry accepts a property name and a Supplier providing the value when Spring needs to read it.
- The URL uses the r2dbc:postgresql driver scheme along with the container's host and mapped port.

### 2.1. Why Must You Use getMappedPort?

PostgreSQL inside a container normally listens on port 5432. However, Testcontainers may map that port to a random host port such as 49172.

Do not write:

~~~java
"r2dbc:postgresql://localhost:5432/app_test"
~~~

because host port 5432 may not be the container's port. Retrieve the mapped port instead:

~~~java
postgres.getMappedPort(PostgreSQLContainer.POSTGRESQL_PORT)
~~~

Similarly, do not assume the host is always localhost. Use postgres.getHost() to obtain the host reachable from the test execution environment.

### 2.2. Do Not Use the JDBC URL for R2DBC

PostgreSQLContainer.getJdbcUrl() returns a JDBC URL, for example:

~~~text
jdbc:postgresql://localhost:49172/app_test
~~~

That URL is for a JDBC driver. The R2DBC PostgreSQL driver requires a URL with the R2DBC scheme:

~~~text
r2dbc:postgresql://localhost:49172/app_test
~~~

Therefore, when using Testcontainers PostgreSQL with Spring Data R2DBC, build the R2DBC URL from host, mapped port, and database name, or use appropriate ConnectionFactoryOptions.

### 2.3. Using DynamicPropertyRegistry.add Properly

add takes a property name and a Supplier, so pass a method reference or lambda to retrieve the value from the container:

~~~java
registry.add("spring.r2dbc.username", postgres::getUsername);
~~~

Do not invoke getters prematurely before the container has started if the value depends on container state. Passing a Supplier lets TestContext resolve the value when properties are evaluated.

Methods annotated with @DynamicPropertySource must be static. They are usually placed in the test class or in a shared superclass used across multiple test classes.

## 3. R2DBC Properties Commonly Supplied Dynamically

With Spring Boot auto-configuration, the main properties are:

| Property | Purpose | Example |
|---|---|---|
| spring.r2dbc.url | R2DBC connection URL | r2dbc:postgresql://host:port/app_test |
| spring.r2dbc.username | Database username | test |
| spring.r2dbc.password | Database password | test |
| spring.r2dbc.pool.enabled | Enable/disable connection pool when supported | true/false |
| spring.r2dbc.pool.initial-size | Initial connection pool size | 1 |
| spring.r2dbc.pool.max-size | Maximum connection count | 5 |
| spring.r2dbc.pool.max-acquire-time | Max wait time to acquire a connection | 3s |

Exact pool properties and binding capabilities depend on the Spring Boot version and whether the application uses r2dbc-pool. Not all drivers expose the same set of options.

Example registering additional pool properties:

~~~java
@DynamicPropertySource
static void r2dbcProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.r2dbc.url", TestDatabase::r2dbcUrl);
    registry.add("spring.r2dbc.username", TestDatabase::username);
    registry.add("spring.r2dbc.password", TestDatabase::password);
    registry.add("spring.r2dbc.pool.enabled", () -> true);
    registry.add("spring.r2dbc.pool.initial-size", () -> 1);
    registry.add("spring.r2dbc.pool.max-size", () -> 4);
}
~~~

A small pool can work well in tests to reduce resource usage, but it needs enough connections for concurrent test operations and open transactions. If tests do not need to verify pooling, a simpler configuration works.

## 4. Using Helpers to Reuse Dynamic Configuration

If multiple test classes share a container, you can centralize URL construction and property registration in a base class or utility.

Example:

~~~java
abstract class AbstractR2dbcIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void registerR2dbcProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.r2dbc.url",
            AbstractR2dbcIntegrationTest::r2dbcUrl
        );
        registry.add(
            "spring.r2dbc.username",
            postgres::getUsername
        );
        registry.add(
            "spring.r2dbc.password",
            postgres::getPassword
        );
    }

    private static String r2dbcUrl() {
        return "r2dbc:postgresql://"
            + postgres.getHost()
            + ":"
            + postgres.getMappedPort(
                PostgreSQLContainer.POSTGRESQL_PORT
            )
            + "/"
            + postgres.getDatabaseName();
    }
}
~~~

Extending test class:

~~~java
@SpringBootTest
@Testcontainers
class OrderRepositoryIntegrationTest
        extends AbstractR2dbcIntegrationTest {

    @Test
    void savesOrder() {
        // Test logic.
    }
}
~~~

When using a base class, understand container lifecycles and Spring TestContext caching. Do not spin up a separate container and stop it while a cached ApplicationContext still holds a ConnectionFactory pointing to the old port.

A common approach is a shared static container in a base class whose lifecycle aligns with context caching, or a deliberately managed singleton container. If each test class requires an independent database/container, ensure the matching Spring context is not reused with stale properties.

## 5. Context Caching and Container Lifecycle

Spring TestContext can cache the ApplicationContext to speed up tests sharing the same configuration. Dynamic properties are resolved while building the context. This creates a risk if a container stops while the cached context still holds a ConnectionFactory pointing to the old host/port.

Risk scenario:

1. Test class A starts container A on port 49172.
2. Spring creates an ApplicationContext with the URL pointing to port 49172.
3. Test class A finishes and container A is stopped.
4. Test class B has a similar configuration, so Spring reuses the cached ApplicationContext.
5. ConnectionFactory still points to the old port, whereas container B has a different port.

Mitigations:

- Use a shared static container in a base class with a lifecycle aligned to context caching.
- Keep the container alive as long as the context can be reused.
- If a test requires an independent context/container, give it distinct context configuration or use @DirtiesContext when evicting the context from cache is truly required.
- Avoid starting/stopping containers manually in @BeforeEach if the ApplicationContext uses connections built from that container.
- Do not change property values after ConnectionFactory is already initialized and expect the bean to update automatically.

@DirtiesContext closes the cached context, though it should not be the default fix for every lifecycle issue. Using it slows tests down because contexts must be recreated.

### 5.1. Inheriting @DynamicPropertySource

You can place dynamic property methods in a superclass for multiple test classes to share. If subclasses supply different dynamic values under the same property names, remember that context caching may treat the test configurations as equivalent and reuse the context.

When dynamic values vary across subclasses, configure context identity/lifecycle explicitly or separate test groups. Do not rely on the Supplier being re-invoked to mutate an already instantiated ConnectionFactory.

## 6. Combining @ActiveProfiles and application-test.yml

You can keep static shared settings in a test profile and supply only container-dependent values via @DynamicPropertySource.

Example src/test/resources/application-test.yml:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 1
      max-size: 5

logging:
  level:
    org.springframework.r2dbc: DEBUG
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
class CustomerRepositoryIntegrationTest {
    // Container and @DynamicPropertySource.
}
~~~

In this setup:

- application-test.yml holds static test settings.
- @DynamicPropertySource provides the URL, username, and password generated when the container runs.
- @ActiveProfiles("test") activates the corresponding profile.

Dynamic properties have higher precedence than typical test configuration sources such as @TestPropertySource, system properties, environment variables, and application property sources in the TestContext mechanism. Thus dynamic values can override a static URL in application-test.yml.

Avoid declaring the same property in multiple places unnecessarily. If overrides exist, be clear which source wins so tests do not inadvertently connect to a different database.

## 7. When the Application Declares Its Own ConnectionFactory

Dynamic properties such as spring.r2dbc.url are used by Spring Boot auto-configuration only when Boot is responsible for creating ConnectionFactory.

If the application declares its own bean:

~~~java
@Bean
ConnectionFactory connectionFactory() {
    return ConnectionFactories.get(
        "r2dbc:postgresql://localhost:5432/app"
    );
}
~~~

then that bean may cause auto-configuration to back off. Consequently, changing spring.r2dbc.url in @DynamicPropertySource will not automatically alter the URL hard-coded inside the bean.

This is a common reason tests register dynamic properties yet still connect to the old database.

### 7.1. Reading Dynamic Properties in a Custom ConnectionFactory Bean

If a custom bean is required, inject Environment and read the registered properties:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.core.env.Environment;

@Configuration
class TestDatabaseConfiguration {

    @Bean
    ConnectionFactory connectionFactory(Environment environment) {
        String host =
            environment.getRequiredProperty("test.r2dbc.host");
        Integer port =
            environment.getRequiredProperty("test.r2dbc.port", Integer.class);
        String database =
            environment.getRequiredProperty("test.r2dbc.database");
        String username =
            environment.getRequiredProperty("test.r2dbc.username");
        String password =
            environment.getRequiredProperty("test.r2dbc.password");

        ConnectionFactoryOptions options =
            ConnectionFactoryOptions.builder()
                .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                .option(ConnectionFactoryOptions.HOST, host)
                .option(ConnectionFactoryOptions.PORT, port)
                .option(ConnectionFactoryOptions.DATABASE, database)
                .option(ConnectionFactoryOptions.USER, username)
                .option(ConnectionFactoryOptions.PASSWORD, password)
                .build();

        return ConnectionFactories.get(options);
    }
}
~~~

Test registering custom properties:

~~~java
@DynamicPropertySource
static void registerDatabase(DynamicPropertyRegistry registry) {
    registry.add("test.r2dbc.host", postgres::getHost);
    registry.add(
        "test.r2dbc.port",
        () -> postgres.getMappedPort(
            PostgreSQLContainer.POSTGRESQL_PORT
        )
    );
    registry.add("test.r2dbc.database", postgres::getDatabaseName);
    registry.add("test.r2dbc.username", postgres::getUsername);
    registry.add("test.r2dbc.password", postgres::getPassword);
}
~~~

This approach works well when the application has custom ConnectionFactory creation logic. However, declare a custom factory in tests only when truly necessary; if Boot auto-configuration meets your needs, using spring.r2dbc.* is simpler and requires less configuration.

### 7.2. Avoid Reading Values Too Early in Custom Beans

Do not construct a static ConnectionFactory at class-loading time before dynamic properties are registered. Let Spring build the bean after TestContext registers properties, via dependency injection or @Configuration.

If the custom factory needs SSL, driver-specific options, or pooling, attach those options from bound properties. Option names and types depend on the driver; do not copy PostgreSQL options blindly to another driver.

## 8. Using @ServiceConnection When Supported by Spring Boot

Some Spring Boot versions support Testcontainers service connections via @ServiceConnection. When the container type and corresponding service connection factory are supported, Spring Boot can produce ConnectionDetails and configure connections without manually registering each property.

Conceptual example:

~~~java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

}
~~~

This is shorter, though it depends on the Spring Boot version, Testcontainers module, and supported service connection types. For R2DBC, check your project version's documentation to verify that service connection provides the corresponding R2DBC ConnectionDetails.

If your version does not support R2DBC service connections, or the application needs custom properties, @DynamicPropertySource remains an explicit and flexible approach.

Do not combine @ServiceConnection and @DynamicPropertySource for the same URL just to "be safe." Having two configuration sources supply the same value makes it harder to tell which one is active.

## 9. Dynamic Configuration for Databases Other Than PostgreSQL

The general pattern does not depend on PostgreSQL: obtain host, port, database, and credentials from the container, then build a URL using the matching R2DBC driver scheme.

| Database | Common driver scheme | Notes |
|---|---|---|
| PostgreSQL | r2dbc:postgresql:// | Driver artifact r2dbc-postgresql |
| MySQL | r2dbc:mysql:// | Driver artifact r2dbc-mysql |
| MariaDB | r2dbc:mariadb:// | Depends on chosen driver |
| Microsoft SQL Server | r2dbc:mssql:// | Driver-specific options |
| H2 R2DBC | r2dbc:h2:mem:///... | Often used for lightweight tests; not a full replacement for production databases |

Exact URLs and options depend on the driver and version. Consult the driver documentation instead of assuming every driver shares identical username/password, SSL, or query option syntax.

### 9.1. Using Testcontainers with the Target Database

If production runs PostgreSQL, integration tests should prefer a PostgreSQL container matching the major version or project-supported version. H2 can be faster, but differs in SQL dialect, data types, sequences/identity, locking, constraints, JSON, collation, and transaction semantics.

Testcontainers lets tests run against a real database in an isolated environment, increasing confidence in mapping, query, and migration tests.

### 9.2. Test Databases Should Never Point to Production

Dynamic properties must point to a container or dedicated test database. Never pull a production URL from a secret store as a fallback for tests. Tests may run migrations, truncate tables, or delete rows; accidentally connecting to production can cause severe damage.

Use dedicated test credentials, minimum privileges, and disposable databases.

## 10. Dynamic Properties for Migrations and Schema Setup

R2DBC applications may use Flyway or Liquibase to create schemas before tests run. Because many migration tools use JDBC rather than R2DBC, configure a separate JDBC URL pointing to the same container/database.

Example with Flyway:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.r2dbc.url", TestDatabase::r2dbcUrl);
    registry.add("spring.r2dbc.username", postgres::getUsername);
    registry.add("spring.r2dbc.password", postgres::getPassword);

    registry.add("spring.flyway.url", postgres::getJdbcUrl);
    registry.add("spring.flyway.user", postgres::getUsername);
    registry.add("spring.flyway.password", postgres::getPassword);
}
~~~

Here the two URLs have different schemes yet point to the same container database:

- spring.r2dbc.url uses the R2DBC driver.
- spring.flyway.url uses the JDBC driver for migrations.

Do not assign the JDBC URL to spring.r2dbc.url or the R2DBC URL to spring.flyway.url.

If the project uses Liquibase, schema.sql, or another migration mechanism, provide properties under the proper namespace and ensure migrations run before tests access repositories.

### 10.1. Avoiding Races Between Migrations and Tests

The container must be ready and the schema created before repositories query it. Spring Boot normally runs migrations during context startup when enabled. If tests initialize schemas manually, ensure setup finishes before test cases execute.

Avoid having multiple test classes concurrently run destructive migrations on the same shared database/schema. Use separate databases/schemas or serialize test groups that require independent migrations.

## 11. Verifying the Actual Connection Configuration

When a test reports connection errors, inspect each layer:

1. Has the container started and is the database ready?
2. Are host and mapped port retrieved from the container?
3. Does the URL have the R2DBC scheme matching the driver?
4. Do username/password/database name match container settings?
5. Is the R2DBC driver on the test runtime classpath?
6. Is Spring Boot auto-configuring ConnectionFactory, or did the application declare a custom bean?
7. Are repositories/templates using the expected ConnectionFactory?
8. Did migrations run on the same database?
9. Is TestContext reusing a cached ConnectionFactory pointing to a stopped container?
10. Is the connection pool holding stale connections after a container restart?

You can log host, port, and database name in tests for diagnostics, while avoiding logging passwords or URLs containing credentials.

### 11.1. Do Not Verify Only Property Strings

Seeing the expected spring.r2dbc.url value does not guarantee repositories use a factory built from that property. A custom ConnectionFactory bean, another profile, or multi-database configuration could make repositories use a different source.

Verify both bean wiring and execute a small query against the database container in integration tests.

## 12. Using Test Profiles and Dynamic Properties Together

A common layout:

~~~text
src/main/resources/
    application.yml

src/test/resources/
    application-test.yml

src/test/java/
    AbstractR2dbcIntegrationTest.java
    CustomerRepositoryIntegrationTest.java
    OrderRepositoryIntegrationTest.java
~~~

application.yml holds default application settings. application-test.yml holds static test values such as pool size, logging, and feature flags. Testcontainers supplies the URL and credentials via @DynamicPropertySource.

Example:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      max-size: 4

  flyway:
    enabled: true

logging:
  level:
    org.springframework.r2dbc: DEBUG
~~~

There is no need to store a container URL with a fixed port in files. That value is registered dynamically from the container at test runtime.

If tests use multiple databases, register separate property namespaces:

~~~java
registry.add("app.orders.r2dbc.url", TestDatabases::ordersUrl);
registry.add("app.billing.r2dbc.url", TestDatabases::billingUrl);
~~~

Custom configuration binds these namespaces and builds the corresponding factories. Under default Spring Boot auto-configuration, only one spring.r2dbc.* namespace is picked as the default ConnectionFactory; multiple databases typically require explicit bean configuration.

## 13. Common Mistakes

**Assigning a JDBC URL to spring.r2dbc.url.** Testcontainers getJdbcUrl() returns a JDBC URL. R2DBC requires its own driver scheme. Build r2dbc:postgresql://... from host, mapped port, and database name.

**Hard-coding port 5432.** Testcontainers usually maps container ports to random host ports. Use getMappedPort() rather than hard-coding 5432 on the host.

**Registering properties in @BeforeEach.** @BeforeEach runs too late if ApplicationContext and ConnectionFactory have already been created. Use @DynamicPropertySource or a property source mechanism running before context initialization.

**Dynamic properties have no effect on a custom ConnectionFactory.** If the application declares a factory bean with a hard-coded URL, Boot auto-configuration may have backed off. Make the custom bean read dynamic properties or remove the custom bean if unnecessary.

**Container stops while Spring context remains cached.** ConnectionFactory may still point to the old port. Align container lifecycles with context caching, use a shared container, or isolate contexts when needed.

**Missing R2DBC driver dependency.** Even with a valid URL, ConnectionFactory cannot be created if the driver is absent from the classpath. Ensure test/runtime dependencies include the matching R2DBC driver.

**Providing URL without credentials.** Some URLs can embed credentials, though separating username and password into distinct properties is usually clearer. Ensure the container and Spring use matching values.

**Migrations running against a different database.** Flyway normally uses a JDBC URL. If you configure spring.r2dbc.url without configuring Flyway's datasource, migrations may not run against the container database queried by the application.

**Running tests in parallel on a shared schema.** Tests can wipe each other's data or collide during migrations. Use separate schemas/databases or proper isolation per test group.

**Putting sensitive credentials in source files.** Never commit real passwords or production URLs in test files. Use throwaway credentials for containers and proper secrets if tests connect to managed services.

## 14. Practical Setup Workflow

A basic workflow for Spring Boot + Spring Data R2DBC + Testcontainers:

1. Add compatible R2DBC driver and Testcontainers dependencies.
2. Declare the database container using static @Container.
3. Wait for container readiness via Testcontainers health checks.
4. Register spring.r2dbc.url using the R2DBC scheme, host, and mapped port.
5. Register username/password from the container.
6. Activate the test profile if static test settings are needed.
7. Ensure Spring Boot auto-configuration uses the dynamic properties, or custom ConnectionFactory beans read those properties.
8. Run migrations on the target database container.
9. Execute integration tests via repositories/services.
10. Ensure containers are not stopped before the ApplicationContext using them finishes.

Across many test classes, consider a base class or singleton container to avoid repeated database startups and prevent cached contexts from pointing to stopped containers.

## 15. Design Principles

- Use @DynamicPropertySource to supply properties before Spring builds the ApplicationContext.
- Use DynamicPropertyRegistry.add with Suppliers to read host, mapped port, and credentials from the container.
- Use spring.r2dbc.url, spring.r2dbc.username, and spring.r2dbc.password for Boot R2DBC auto-configuration.
- Build R2DBC URLs using the driver scheme; never pass a JDBC URL directly.
- Use getHost() and getMappedPort() rather than hard-coding localhost and default ports.
- If declaring a custom ConnectionFactory, inject dynamic properties into that bean.
- Align Testcontainers lifecycles with Spring TestContext caching.
- Separate static properties in application-test.yml from dynamic container values.
- Configure JDBC migration settings separately when the migration tool uses JDBC.
- Use isolated databases/credentials dedicated solely to testing.
- Verify that repositories actually use the ConnectionFactory built from dynamic properties.
- Test against the target database engine and driver closest to production.

## 16. Summary

Dynamic connection properties let tests obtain URLs, hosts, ports, databases, and credentials from the running environment instead of hard-coding them in configuration files. With Spring Boot R2DBC, @DynamicPropertySource can register spring.r2dbc.url, spring.r2dbc.username, and spring.r2dbc.password from Testcontainers before ApplicationContext creates ConnectionFactory.

Use the driver-specific R2DBC URL and the container's mapped port; JDBC URLs from Testcontainers are only for JDBC-based tools like Flyway. If the application creates its own ConnectionFactory, Boot's dynamic properties will not alter that bean automatically, so custom factories must read the corresponding properties. Finally, manage container lifecycles cleanly alongside Spring context caching and always use isolated test databases so integration tests can run repeatedly and safely.
