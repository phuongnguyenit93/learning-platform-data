# @DynamicPropertySource When You Need to Supply Connection Configuration Manually for Testcontainers

## 1. Lesson goals

When running integration tests with Testcontainers, a database, Redis, Kafka, or mock HTTP service is typically created **dynamically**. For example, a PostgreSQL container may open port `5432` inside Docker while mapping it to a random port on the host running the tests. Therefore, hardcoding `spring.datasource.url=jdbc:postgresql://localhost:5432/... ` in `application-test.properties` is not a reliable configuration strategy.

Spring TestContext provides **`@DynamicPropertySource`** and **`DynamicPropertyRegistry`** to pass configuration values **known only at test runtime** — such as JDBC URL, username, password, host, and mapped port — into `Environment` before Spring initializes beans that depend on them.

This lesson belongs to the **Spring Boot – testing** module, **Testcontainers** group, with the primary objective: **using `@DynamicPropertySource` when you need to supply connection configuration manually**. This is a Spring TestContext integration technique, not an annotation that starts containers.

After this lesson, you will be able to:

1. Understand the exact role and lifecycle of `@DynamicPropertySource` and `DynamicPropertyRegistry`.
2. Register dynamic JDBC settings with `registry.add("spring.datasource.url", postgres::getJdbcUrl)`.
3. Explain why the registration method must be `static` and accept exactly one `DynamicPropertyRegistry` parameter.
4. Distinguish a lazy `Supplier` from calling a container getter too early.
5. Use `@Testcontainers`/`@Container` to manage a container and pass connection details into Spring Boot.
6. Write `@SpringBootTest` tests using real PostgreSQL, verifying JDBC metadata, services, and repositories.
7. Write `@DataJpaTest` keeping the PostgreSQL container with `@AutoConfigureTestDatabase(replace = NONE)` on Spring Boot 3.3.
8. Verify the **actual** connection path instead of merely asserting properties.
9. Use dynamic properties for multiple services or custom configuration prefixes.
10. Choose among `@DynamicPropertySource`, `@ServiceConnection`, `@TestPropertySource`, and `@ActiveProfiles`.
11. Avoid traps around Spring context caching, shared container lifecycles, parallel tests, stale ports, database replacement, and credential exposure.
12. Run a complete example with **Java 17, Spring Boot 3.3.5, Gradle, PostgreSQL Testcontainers, and JUnit Jupiter**.

**Short takeaway:** `@DynamicPropertySource` injects **dynamic connection values** into Spring `Environment`. It **does not start the database itself** and **does not verify that the app actually uses that connection**; you must manage the container lifecycle and write assertions on the DataSource/runtime.

## 2. The problem with static URL configuration

Suppose Testcontainers starts PostgreSQL:

~~~text
PostgreSQL container
  internal port: 5432
          |
          v
Docker host mapped port: 49157  (illustrative only)
          |
          v
JDBC URL provided by container:
jdbc:postgresql://localhost:49157/customer_test
~~~

On another run, the mapped port might be `49231` or some other number. The number in the diagram **is not a fixed port that tests may assume**. Testcontainers picks dynamic mappings to reduce collisions when multiple jobs run concurrently.

Error-prone configuration pattern:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/customer_test
spring.datasource.username=test_user
spring.datasource.password=test_password
~~~

If a developer's machine happens to run PostgreSQL on port 5432, the test might connect to **the wrong database** and report a "false green." On CI without that local DB, the test fails with `Connection refused`. When parallel jobs demand the same host port, they also collide.

The right approach is reading values from **the running container instance**:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Explanation:

- `postgres` is a `PostgreSQLContainer<?>` declared by the test.
- `getJdbcUrl()` returns the host, mapped port, and database matching the container.
- `getUsername()`/`getPassword()` return credentials for the test database.
- `registry.add(...)` supplies properties for Spring Boot auto-configuration.
- The three method references pass **`Supplier`s**, rather than calling the getters immediately during registration.

## 3. Where does `@DynamicPropertySource` come from?

Exact imports in Spring Framework 6.1 / Spring Boot 3.3:

~~~java
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.DynamicPropertyRegistry;
~~~

Valid method signature:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("feature.endpoint", () -> "http://localhost:18080");
}
~~~

This snippet illustrates the API, not a Testcontainers configuration. Mandatory declaration rules:

- The method is annotated with `@DynamicPropertySource`.
- The method is **`static`**.
- The method returns **`void`**.
- The method has **one `DynamicPropertyRegistry` parameter**.
- The test runs with Spring TestContext supporting dynamic property sources.
- `registry.add(name, supplier)` takes a property name and a `Supplier` providing the value.

This annotation does not go on a container field, `@ConfigurationProperties` bean, or `@Test` method. In Spring Framework 6.1, dynamic property declarations of this style belong to **the test class** and are invoked by Spring TestContext when preparing the `ApplicationContext` for the integration test.

### Role of each component

| Component | Responsible for | Not responsible for |
| --- | --- | --- |
| `@Testcontainers` | Enabling the JUnit 5 Testcontainers extension | Configuring Spring `Environment` automatically |
| `@Container` | Identifying containers for the extension to start/stop | Binding `spring.datasource.url` automatically |
| `PostgreSQLContainer` | Managing the DB container and API to read URL/credentials | Guaranteeing the app uses the right DB |
| `@DynamicPropertySource` | Telling Spring TestContext which method registers properties | Starting containers or creating SQL schemas |
| `DynamicPropertyRegistry` | Registering key/value suppliers into Environment | Creating a DataSource bean if auto-configuration is missing |
| `DataSourceAutoConfiguration` | Building DataSource from config/conditions | Verifying business-correct DB schema |
| `@ServiceConnection` | Providing typed connection details via Boot integration | Required when using pure dynamic properties |

`@DynamicPropertySource` works with PostgreSQL, Redis, Kafka, WireMock, or a host service; **it is not tied exclusively to Testcontainers**. Use it whenever endpoints or ports are generated or known only at runtime.

## 4. Why must we use `Supplier`?

`DynamicPropertyRegistry.add` takes a `Supplier` returning the value, for example:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

This registration does not need to read the JDBC URL at the exact moment Java invokes `registerProperties`. Spring invokes the supplier when the property is resolved.

Conceptually equivalent to:

~~~java
registry.add("spring.datasource.url",
        () -> postgres.getJdbcUrl());
~~~

Easy mistake:

~~~java
// DOES NOT COMPILE: the second argument expects Supplier,
// whereas the getter returns String.
registry.add("spring.datasource.url",
        postgres.getJdbcUrl());
~~~

Beyond the type error, reading a port **before the container starts** can also throw an exception like `Mapped port can only be obtained after the container is started`. With `@Testcontainers` and a static `@Container` in the same test class, the JUnit extension manages startup before the test context needs connections, following the Spring/Testcontainers-supported pattern.

### Lazy suppliers do not mean hot-reloading connections

Registering a supplier is a mechanism for **reading properties dynamically**, yet `DataSource` is auto-configured during `ApplicationContext` initialization. Once the Hikari bean is built with URL X, if the container later changes its mapped port to Y, **the Hikari bean does not automatically update its URL and reconnect** just because the supplier can return Y.

Therefore:

- The container must be ready before Spring instantiates beans that depend on the connection.
- Do not restart the container between test methods while reusing the same old `ApplicationContext`.
- If property values truly change across test classes, use a fresh context or a container lifecycle aligned with the context scope.
- Do not write `registry.add(..., () -> randomPort())` to produce a different port every time Spring reads the property; the supplier should reflect **a running, stable endpoint**.

## 5. Execution order with JUnit and Spring

A simplified lifecycle for a static container in a test class:

~~~text
JUnit Jupiter + Testcontainers extension
       |
       v
Start static @Container PostgreSQL
       |
       v
Spring TestContext prepares ApplicationContext
       |
       v
Invoke static @DynamicPropertySource method
       |
       v
Add Suppliers to Environment
       |
       v
Spring Boot creates DataSource/Hikari,
JPA EntityManagerFactory/repositories/services
       |
       v
@BeforeEach -> @Test -> @AfterEach
       |
       v
Close or reuse Spring context per cache policy
       |
       v
Testcontainers stops static container at end of test class
~~~

This diagram is a **high-level relational model**, not an exhaustive trace of every internal JUnit extension callback. The critical point is that the container's URL and credentials are available when the `DataSource` is actually constructed.

`@Container` only acts as a lifecycle annotation when using the proper Testcontainers JUnit Jupiter integration (e.g., a class annotated with `@Testcontainers`), or if you explicitly manage startup another way.

### Static vs instance container

~~~java
@Testcontainers
class ExampleTest {
    @Container
    static PostgreSQLContainer<?> postgres = ...;
}
~~~

A static `@Container` generally runs **once per test class**. If declared as an instance field, the Testcontainers extension manages it per test method; that is usually **incompatible** with static `@DynamicPropertySource` and a cached Spring context expecting a stable URL.

When you want each method to get a fresh DB, design explicit context/resource isolation; merely removing `static` to make an instance field does not automatically resolve Spring context caching.

## 6. Comparison with static test configuration

| Approach | Where connection data comes from | Best suited for |
| --- | --- | --- |
| `application-test.properties` | Test profile file | Fixed URL/port that does not vary at runtime |
| `@TestPropertySource(properties=...)` | Static inline properties/resources | Overriding known test-specific values |
| `@SpringBootTest(properties=...)` | Inline properties on test annotation | Static context configuration |
| `@DynamicPropertySource` | `Supplier` evaluated when property is resolved | Testcontainers mapped ports, mock service URLs |
| `@ServiceConnection` | Typed `ConnectionDetails` from container, Boot integration | DBs/services recognized by Boot |
| `System.setProperty(...)` | JVM-global mutable state | Usually avoid due to leakage across classes/parallel jobs |
| `@ActiveProfiles("test")` | Activates a profile's config sources | Grouping configuration, does not generate dynamic URLs itself |

### Precedence of dynamic properties

In Spring TestContext, properties registered via `@DynamicPropertySource` have **higher precedence** than many common property sources, including `@TestPropertySource`, OS environment variables, Java system properties, and `@PropertySource`.

Illustrative example:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://localhost:1/unused"
})
@SpringBootTest
class ExampleOverrideTest {

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
    }
}
~~~

This snippet **is not a runnable class**: it omits the container declaration, imports, and Boot configuration. It illustrates precedence. **Never point a "fallback" value to a production URL** because a setup bug or behavior change could send tests into the real DB.

### Property precedence vs ConnectionDetails precedence

In Spring Boot, typed `ConnectionDetails` supplied by `@ServiceConnection` can be prioritized by Boot auto-configuration over connection-related properties. If you use **both `@ServiceConnection` and `@DynamicPropertySource` for the same PostgreSQL instance**, reading `Environment` may not reflect the actual connection path chosen by `DataSource`. Safe practices:

1. **Pick one primary configuration method** for a given connection.
2. When using manual dynamic properties, do not also add `@ServiceConnection` on the same container.
3. Assert `DataSource.getConnection().getMetaData()` rather than only reading `Environment`.
4. If combining them is unavoidable (multiple libraries/services), document each property/typed detail and precedence order explicitly.

## 7. Runnable example: Java 17 + Spring Boot 3.3.5 + PostgreSQL

The sample project includes:

- A Spring Boot app using Spring Data JPA.
- `CustomerAccount` entity.
- `CustomerAccountRepository` repository.
- Transactional `AccountRegistrationService`.
- A `@SpringBootTest` using a PostgreSQL container and dynamic properties.
- A separate `@DataJpaTest` using a PostgreSQL container, **`Replace.NONE`**, and rollback test.
- A total of **4 `@Test` methods**, split evenly between the two classes.
- Tests verifying the PostgreSQL DB engine and real data write/read round-trips.

There is no H2 in the lab's dependency tree. The Postgres container runs on the machine's/CI's Docker/compatible container runtime. In an environment without Docker, integration tests **cannot be expected to pass**; never switch to H2 just to keep tests green when PostgreSQL is what is being tested.

### 7.1. Directory tree

~~~text
dynamic-property-postgres/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/dynamicproperties/
    │   ├── DemoApplication.java
    │   ├── CustomerAccount.java
    │   ├── CustomerAccountRepository.java
    │   └── AccountRegistrationService.java
    └── test/java/com/example/dynamicproperties/
        ├── CustomerFullContextTest.java
        └── CustomerJpaSliceTest.java
~~~

The Gradle Wrapper scripts and `gradle-wrapper.jar` must be generated with a compatible Gradle installation or taken from a repo. Markdown snippets do not include binary Wrapper JAR files.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'dynamic-property-postgres'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Explanation:**

- `spring-boot-starter-data-jpa` provides Spring Data JPA, Hibernate, transaction manager, and JDBC/Hikari infrastructure.
- `spring-boot-starter-test` provides JUnit Jupiter, Spring TestContext, assertions, and Spring Boot testing annotations.
- `org.testcontainers:junit-jupiter` provides `@Testcontainers` and `@Container`.
- `org.testcontainers:postgresql` provides `PostgreSQLContainer`.
- `org.postgresql:postgresql` is the PostgreSQL JDBC driver **at test runtime**; production deployments must include runtime driver/DB dependencies per application architecture.
- `junit-platform-launcher` and `useJUnitPlatform()` enable Gradle to run JUnit Jupiter.
- **Adding `spring-boot-testcontainers` is not required** merely to use `@DynamicPropertySource`. That module is for Boot integrations like `@ServiceConnection`; this example uses Testcontainers + Spring TestContext.
- **No H2 is needed**, and no in-memory replacement is used; the goal is proving real PostgreSQL containers.

The Spring Boot BOM manages compatible test library versions. If a project already uses a Gradle platform or custom BOM, inspect the dependency tree rather than arbitrarily pinning Testcontainers major versions.

### 7.4. Application root

**`src/main/java/com/example/dynamicproperties/DemoApplication.java`**

~~~java
package com.example.dynamicproperties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

This file provides root auto-configuration and component scanning. The entity/repository/service classes live in the same package so Boot/JPA discover them. The lab has **no** application properties pointing to a production DB; tests supply connection details dynamically.

### 7.5. Entity

**`src/main/java/com/example/dynamicproperties/CustomerAccount.java`**

~~~java
package com.example.dynamicproperties;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false,
            unique = true, length = 150)
    private String email;

    @Column(name = "display_name", nullable = false,
            length = 100)
    private String displayName;

    protected CustomerAccount() {
        // JPA requirement
    }

    public CustomerAccount(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

`GenerationType.IDENTITY` delegates ID generation to the database, so tests do not hardcode IDs. Column `email` is unique and `nullable=false`; `display_name` has an explicit column name. Hibernate creates the schema in tests via `ddl-auto=create-drop` **solely to keep the lab self-contained**. In production projects with Flyway/Liquibase, use real migrations and `ddl-auto=validate/none` instead of regenerating schemas.

### 7.6. Repository

**`src/main/java/com/example/dynamicproperties/CustomerAccountRepository.java`**

~~~java
package com.example.dynamicproperties;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {

    Optional<CustomerAccount> findByEmail(String email);

    long countByEmail(String email);
}
~~~

This is a Spring Data JPA repository: methods are derived from the Java property `email`. Tests invoke the real repository against PostgreSQL without a mock DB or fake repository.

### 7.7. Transactional service

**`src/main/java/com/example/dynamicproperties/AccountRegistrationService.java`**

~~~java
package com.example.dynamicproperties;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountRegistrationService {

    private final CustomerAccountRepository repository;

    public AccountRegistrationService(
            CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long register(String email, String displayName) {
        CustomerAccount saved = repository.save(
                new CustomerAccount(email, displayName));
        return saved.getId();
    }
}
~~~

This is a real service so the full-context test verifies **application wiring and transactions**. Method `register` uses `@Transactional` and `repository.save`; with `IDENTITY` mapping, Hibernate executes INSERT immediately to obtain the ID. The full-context test has no `@Transactional`, so the service transaction commits before the test reads via the repository.

**Why not mock the service/repository?** Because this lesson aims to verify dynamic connections from Testcontainers; mocking the DataSource or repository would allow a test to pass even with a broken URL. Unit tests suit pure business logic, but cannot replace integration tests with a real DB.

## 8. `@SpringBootTest`: supplying URL, user, and password from PostgreSQLContainer

**`src/test/java/com/example/dynamicproperties/CustomerFullContextTest.java`**

~~~java
package com.example.dynamicproperties;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.sql.init.mode=never"
    })
class CustomerFullContextTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("accounts_full_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Autowired
    private Environment environment;

    @Autowired
    private CustomerAccountRepository repository;

    @Autowired
    private AccountRegistrationService service;

    private String createdEmail;

    @AfterEach
    void cleanupOnlyRowsCreatedByThisTest() {
        if (createdEmail != null) {
            repository.findByEmail(createdEmail)
                    .ifPresent(repository::delete);
        }
    }

    @Test
    void datasourceReallyUsesPostgresContainer()
            throws SQLException {

        assertTrue(postgres.isRunning());

        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData().getURL()
                    .startsWith("jdbc:postgresql:"));

            assertEquals(
                    "accounts_full_test",
                    connection.getCatalog());
        }

        assertEquals(
                postgres.getJdbcUrl(),
                environment.getProperty("spring.datasource.url"));
    }

    @Test
    void fullContextServiceWritesAndReadsFromPostgres() {
        createdEmail = "full-" + UUID.randomUUID()
                + "@example.test";

        Long id = service.register(
                createdEmail, "Full Context");

        assertNotNull(id);

        CustomerAccount found =
                repository.findByEmail(createdEmail)
                        .orElseThrow();

        assertEquals(id, found.getId());
        assertEquals("Full Context", found.getDisplayName());
        assertEquals(1L,
                repository.countByEmail(createdEmail));
    }
}
~~~

### Analyzing the full-context test

**`@Container static PostgreSQLContainer`**

- Testcontainers JUnit Jupiter extension starts the container once for the class lifecycle.
- Mapped port is assigned on container startup; port 5432 is not fixed on the host.
- `getJdbcUrl`/`getUsername`/`getPassword` supply real connection details.
- Database name `accounts_full_test` exists only inside the test container. Username/password here are sample credentials, **not production credentials**.

**`@DynamicPropertySource`**

- Used by Spring TestContext to register configuration into `Environment`.
- Provides the exact three properties for Spring Boot DataSource auto-configuration.
- Passes getters as `Supplier` method references.
- Does not require `@ActiveProfiles("test")` merely to register dynamic ports.

**`@SpringBootTest(webEnvironment = NONE)`**

- Loads the full application bean graph without starting an HTTP server.
- Includes the real `AccountRegistrationService` and real Spring Data JPA repository.
- Does not replace the PostgreSQL DataSource with H2 by default as test slices can.
- Runs Hibernate DDL to create tables inside the **test PostgreSQL container**; never a production database.

**Metadata test**

- `postgres.isRunning()` only confirms the container is running.
- `getDatabaseProductName() == "PostgreSQL"` proves the JDBC connection obtained from `DataSource` reaches PostgreSQL.
- `getURL().startsWith("jdbc:postgresql:")` checks driver/URL alignment with the engine.
- `connection.getCatalog()` checks the database name in the lab, catching miswired targets.
- Reading `environment.getProperty(...)` supplements info about registration, yet **never relies on this value alone** as proof of connection.

**Service test**

- Writes an account through the real service, reads via the real repository, and checks ID and display name.
- Uses a UUID email so each run has its own fixture.
- `@AfterEach` deletes **only the row created by the current method**; avoids table-wide `deleteAll()`.
- Because the full-context test has no test-managed transaction by default, the insert committed. Cleanup deletes via repository in an appropriate transaction.
- Even if normal cleanup skips when the JVM is killed before teardown, the test container itself is stopped/destroyed by infrastructure; never reuse this schema setup for production.

## 9. `@DataJpaTest`: keeping PostgreSQL instead of H2

Spring Boot 3.3 includes test database auto-configuration for `@DataJpaTest`. Under Boot 3.3's default policy, a DataSource can be **replaced with an embedded DB** if an embedded driver is available. This is a very common pitfall:

~~~text
@DynamicPropertySource registers correctly:
  spring.datasource.url = jdbc:postgresql://localhost:<port>/...
          |
          v
Default @AutoConfigureTestDatabase in Boot 3.3:
  can REPLACE DataSource with H2
          |
          v
Environment holds Postgres URL
yet repository actually executes against H2
~~~

To ensure **the real PostgreSQL container** is used inside a JPA slice:

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

It **does not generate a URL**; it only instructs test auto-configuration **not to replace the DataSource** configured via dynamic properties. You still need the PostgreSQL driver, container, and Spring Data JPA.

### Complete JPA slice test class

**`src/test/java/com/example/dynamicproperties/CustomerJpaSliceTest.java`**

~~~java
package com.example.dynamicproperties;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataJpaTest(
    showSql = false,
    properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.sql.init.mode=never"
    })
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class CustomerJpaSliceTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("accounts_slice_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void registerDatabase(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerAccountRepository repository;

    @Test
    void sliceHasNotReplacedPostgresWithH2()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData().getURL()
                    .startsWith("jdbc:postgresql:"));

            assertEquals(
                    "accounts_slice_test",
                    connection.getCatalog());
        }
    }

    @Test
    void repositoryRoundTripUsesPostgresSchema() {
        String email = "slice-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount original = new CustomerAccount(
                email, "JPA Slice");

        entityManager.persistAndFlush(original);
        entityManager.clear();

        CustomerAccount fetched =
                repository.findByEmail(email).orElseThrow();

        assertNotNull(fetched.getId());
        assertEquals(email, fetched.getEmail());
        assertEquals("JPA Slice", fetched.getDisplayName());
        assertEquals(1L, repository.countByEmail(email));
    }
}
~~~

### Why is manual cleanup unnecessary in the slice?

`@DataJpaTest` normally opens a **test-managed transaction** and rolls it back at the end of each JUnit method. `entityManager.persistAndFlush` sends the INSERT to the database inside the test transaction, yet **flushing does not commit**. When the test completes, the inserted row is rolled back.

Therefore:

- `@AfterEach repository.deleteAll()` is not needed in the slice example.
- `persistAndFlush` followed by `clear` avoids merely asserting against a still-managed Java object.
- Queries still execute against real PostgreSQL, within the test transaction.
- This **is not evidence** that an HTTP server transaction committed or that another runtime process can see the row after the test.
- If a service uses `REQUIRES_NEW` or executes outside the test transaction, rollback may miss some side effects; handle accordingly.

### Engine verification trap

Do not write only:

~~~java
assertEquals(
    postgres.getJdbcUrl(),
    environment.getProperty("spring.datasource.url"));
~~~

That only verifies `Environment` reflects the dynamic source. If the JPA slice replaced the DataSource with H2, **`Environment` can still report the PostgreSQL URL** and the assertion passes. The test above opens a real connection and checks its metadata. That is the primary safeguard against **false confidence**.

### Differences between Boot 3.3 and Boot 3.4

| Version | Related behavior |
| --- | --- |
| Spring Boot 3.3.x | Default replacement for JPA/JDBC slices is typically `Replace.ANY` |
| Spring Boot 3.4+ | Introduces `Replace.NON_TEST` to detect and keep valid test datasources |
| Both | `Replace.NONE` can be used when you want **not to replace** the configured DataSource |
| Both | Actual connections must still be verified; an annotation alone does not guarantee a safe engine |

On Boot 3.3, **do not write `Replace.NON_TEST`** because that enum constant does not exist in that version. Conversely, `Replace.NONE` does not mean the URL is safe; if a dynamic supplier points to a production DB, the test remains dangerous. Always use a test-specific container and least-privilege credentials.

## 10. Running Gradle and observing results

To run the **4 `@Test` methods** defined above, you need:

- JDK 17 (or toolchain provisioning configured in Gradle).
- A Gradle Wrapper compatible with the project.
- Docker/container runtime usable by Testcontainers.
- Permission to run the PostgreSQL 16 Alpine image and download Maven dependencies.
- No pre-installed PostgreSQL server listening on port 5432.
- No H2 required.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run one group:

~~~bash
./gradlew test --tests 'com.example.dynamicproperties.CustomerFullContextTest'
./gradlew test --tests 'com.example.dynamicproperties.CustomerJpaSliceTest'
~~~

On Windows, replace `./gradlew` with `.\gradlew.bat` in the corresponding commands.

With compatible code and environment, **all 4 tests are expected to pass**:

| Class | Test | Verifies |
| --- | --- | --- |
| `CustomerFullContextTest` | `datasourceReallyUsesPostgresContainer` | DB engine, URL, catalog, registry |
| `CustomerFullContextTest` | `fullContextServiceWritesAndReadsFromPostgres` | Service transaction + real repository |
| `CustomerJpaSliceTest` | `sliceHasNotReplacedPostgresWithH2` | Real DB engine, no embedded replacement |
| `CustomerJpaSliceTest` | `repositoryRoundTripUsesPostgresSchema` | JPA flush/clear/query and test rollback |

This is the **expected result from the source**, not a record of running Docker/Gradle in the learner's environment. Container ports, startup times, PostgreSQL logs, and Gradle task logs vary; **there is no fixed business stdout** in the test code.

JUnit reports typically appear under:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.dynamicproperties.CustomerFullContextTest.xml
    └── TEST-com.example.dynamicproperties.CustomerJpaSliceTest.xml
~~~

When Gradle reports `UP-TO-DATE` or `FROM-CACHE`, tests were not necessarily freshly executed. When investigating environment issues or dynamic ports:

~~~bash
./gradlew test --rerun-tasks
~~~

If the project lacks a Wrapper yet, a compatible installed Gradle can generate it:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then store the Wrapper scripts/JAR per project policy. Never change Gradle/Boot versions in a real project without verifying dependency tree compatibility.

### Docker in CI

If the Docker daemon is not running, Testcontainers may report no valid Docker environment found. That is an **infrastructure failure**, not a reason to delete assertions or fabricate a "PASS." Check Docker socket/permissions, Testcontainers compatibility, and image pull/network access. Never mount the Docker socket into a production application; only runners dedicated to integration tests need appropriate container permissions.

## 11. When should you use `@ServiceConnection` instead of `@DynamicPropertySource`?

Spring Boot 3.1+ integrates Testcontainers via **`@ServiceConnection`** in the `spring-boot-testcontainers` module. For container/service types Boot recognizes, this annotation automatically supplies **`ConnectionDetails`** without registering the three JDBC properties manually.

**Illustrative** example, not included in the runnable project above:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

~~~java
@Testcontainers
@SpringBootTest
class ServiceConnectionExample {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired repository/dataSource and @Test methods...
}
~~~

This requires imports, app configuration, and actual test methods to run. Spring Boot can automatically generate `JdbcConnectionDetails` from `PostgreSQLContainer`.

**Comparison:**

| Criterion | `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- | --- |
| What it supplies | Spring `Environment` properties | Spring Boot typed `ConnectionDetails` |
| How it is declared | Static registry method, `Supplier` | Annotation on supported container field/bean |
| Flexibility with custom prefixes | Very high | Depends on supported connection details types |
| Needs `spring-boot-testcontainers` | Not required | Yes |
| Works outside Spring Boot | Yes, via Spring TestContext | Spring Boot-specific feature |
| Multiple services defining custom props | Well suited | May require combining with manual registration |
| Conflict risk if both are used | Yes, two config paths | Yes, connection details can override properties |
| Checking actual DB | Still needs metadata/SQL tests | Still needs metadata/SQL tests |

### Selection recommendations

- If tests only connect to PostgreSQL/Redis/MongoDB that Boot already recognizes cleanly, **`@ServiceConnection`** is usually shorter with less boilerplate.
- If tests must pass **custom keys** — such as `external.inventory.base-url`, a token/host/port produced by a local process, or an engine/library without matching typed details — **`@DynamicPropertySource`** is more flexible.
- If a project does not use `spring-boot-testcontainers` or prefers keeping the Spring TestContext model standalone, dynamic properties remain common.
- Avoid placing both `@ServiceConnection` and `@DynamicPropertySource` on the same datasource without an explained and verified reason.

**This lesson intentionally focuses on `@DynamicPropertySource`** so learners understand exactly how to supply connection properties manually, even on Spring Boot versions that support service connections.

## 12. Extending to Redis, Kafka, and HTTP mock servers

`@DynamicPropertySource` is not limited to `spring.datasource.*`. Any Spring property accepting a dynamic host/port/URL can be registered.

### Redis via GenericContainer

~~~java
@Testcontainers
class RedisIntegrationTest {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }
}
~~~

**Illustrative snippet**, needing Spring context, imports, and test methods. Do not confuse `redis.getMappedPort(6379)` with port `6379` on the host: the mapped port must be obtained **after the container starts**. For an app using Spring Data Redis on Boot 3.3, the standard config prefix is `spring.data.redis.*`. When a library uses another prefix, register the exact key that library binds.

### HTTP mock server

Suppose a mock server exposes `getBaseUrl()`, for instance:

~~~java
@DynamicPropertySource
static void serviceEndpoint(DynamicPropertyRegistry registry) {
    registry.add("external.payment.base-url",
            paymentMockServer::getBaseUrl);
}
~~~

**Illustrative snippet**: `paymentMockServer` must be declared/started properly, and the app must read `external.payment.base-url`. Registering a key that no bean reads **has no effect**. To prove the system hits the mock server, send a request via the real client in the test and assert that the mock server received the expected request.

### Kafka bootstrap servers

With a matching `KafkaContainer kafka` in the test:

~~~java
registry.add("spring.kafka.bootstrap-servers",
        kafka::getBootstrapServers);
~~~

This snippet belongs inside a `@DynamicPropertySource` method with `registry`/`kafka` available. Spring Kafka reads the bootstrap server list from that property. When using multiple Kafka brokers or security protocols, supply full configuration, not just one URI string.

### Multiple services in the same registry

~~~java
@DynamicPropertySource
static void dynamicServices(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
    registry.add("spring.data.redis.host",
            redis::getHost);
    registry.add("spring.data.redis.port",
            () -> redis.getMappedPort(6379));
}
~~~

This snippet requires both containers to have proper lifecycles. Suppliers can reference distinct container instances. There is no need to write a separate `@DynamicPropertySource` method per property when they belong to the same config group and test scope.

**Warning:** The app may initialize beans needing both PostgreSQL and Redis; a container not yet started when its supplier resolves will fail context startup. Ensure all required services are managed consistently by JUnit/Boot/Testcontainers.

## 13. Context caching: the trap of a stopped container with a living context

Spring TestContext caches `ApplicationContext` based on multiple test configuration factors. Caching speeds up suites, yet introduces an important pitfall:

1. Test class A uses a static Postgres container.
2. Spring creates the `ApplicationContext` and a Hikari DataSource pointing to container A.
3. Class A finishes; the Testcontainers extension stops container A.
4. Class B has an equivalent Spring configuration and reuses the context from cache.
5. The DataSource still holds the endpoint of **stopped** container A.
6. Class B hits `Connection refused`, `connection is closed`, or intermittent timeouts.

**Having a `@DynamicPropertySource` method does not make the Hikari pool swap endpoints while the context cache retains the old bean.** That is why **container lifetime** and **`ApplicationContext` lifetime** must align.

### Ways to reduce the risk

- In the runnable example, the two classes use **different Spring test configurations** (`@SpringBootTest` and `@DataJpaTest`), separate containers, and separate databases. Do not attempt to reuse a stopped DB container across contexts.
- When sharing a base test class with a static container, consider a singleton container living across the entire period the cached context is used.
- If subclasses receive **different dynamic property values**, Spring docs suggest `@DirtiesContext` on the base class when a fresh context is required.
- `@DirtiesContext` **evicts the context**, it does not erase committed DB data; never substitute it for cleanup.
- When scaling integration tests, group tests around stable context/container configurations to reduce startup cost without leaking state.

### Suggested structural example

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
abstract class IsolatedPostgresTestBase {
    // Static container/dynamic properties per subclass.
    // Each subclass gets a fresh context if endpoints differ.
}
~~~

This is a structural snippet, not a standalone runnable class. Depending on inheritance and how JUnit/Testcontainers manage static fields, verify whether containers are unintentionally shared. Do not add `@DirtiesContext` to every test when the same container/context can be reused safely; it slows down the suite and opens more connections.

### Do not blindly pair an instance container with a cached context

~~~java
@Container
PostgreSQLContainer<?> postgres = ...;
~~~

If the container is an instance field, the JUnit extension may start/stop it per method. However, `@DynamicPropertySource` is static, and the Spring context can retain the DataSource longer than a single method; the new container's mapped port/endpoint does not automatically enter the already-created Hikari pool. When the goal is **each test method getting a real fresh database**, choose intentional DB schema/transaction/container lifecycle isolation rather than changing one keyword.

## 14. Parallel testing and data isolation

When running multiple JUnit methods/classes in parallel, avoid these patterns:

- All methods sharing one fixed email/ID and concurrently writing/`DELETE`ing it.
- An `@AfterEach repository.deleteAll()` wiping another method's rows.
- Static mutable properties/state overwritten by multiple classes.
- Restarting a shared container while another context still uses the pool.
- Assuming a test transaction covers HTTP/server threads.
- Using a fixed database name on a shared DB server outside Testcontainers.

Solutions:

1. Use **test-specific keys** such as UUIDs and clean up strictly by those keys.
2. Use `@DataJpaTest` rollback when tests only invoke repositories within the test-managed transaction.
3. Use separate schemas/databases or separate containers when operations cannot roll back.
4. If sharing one container across the suite, define clear ownership and avoid table-wide cleanup.
5. With parallel writes, guarantee isolation and lock behavior; when verifying PostgreSQL transaction semantics, test on the real engine.
6. When testing a real HTTP server, clean up committed data via transactions that actually commit.

**The demo's full-context test** uses UUID emails and targeted deletion. **The JPA slice test** uses UUIDs and default rollback. The two differ because their transaction boundaries differ, not because using `@DynamicPropertySource` makes transaction behavior identical.

## 15. Why not pass dynamic URLs using `System.setProperty`?

An older pattern:

~~~java
@BeforeAll
static void configure() {
    System.setProperty(
            "spring.datasource.url",
            postgres.getJdbcUrl());
}
~~~

Besides having to guarantee container startup ordering, `System.setProperty` mutates **JVM-global state**; it can affect other tests running in the same JVM, especially under parallel execution or Spring context caching.

`@DynamicPropertySource` binds property sources directly to the **Spring test `ApplicationContext` configuration** without mutating global JVM properties. That is a major win for test isolation.

When an external library does not read Spring `Environment` and only reads Java system properties, `@DynamicPropertySource` may **not suffice**; use that library's configuration mechanism while carefully scoping and cleaning it up. Do not assume every external library reads `spring.datasource.url` or any Spring key.

## 16. `@DynamicPropertySource` does not replace `@ActiveProfiles`

A system can use both together:

~~~java
@ActiveProfiles("test")
@SpringBootTest
@Testcontainers
class PostgresWithProfileTest {

    @Container
    static PostgreSQLContainer<?> postgres = ...;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

This snippet is not standalone. `@ActiveProfiles("test")` selects a profile, while the dynamic registry provides runtime URL/credentials.

For example, `application-test.yml` can define:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

This is an **extended configuration**, not a file included in the runnable project; when using `ddl-auto: validate`, the schema must be created first by Flyway/migrations. Do not run this snippet standalone without migrations. Separation of concerns:

- Profile: selects logging levels, schema strategies, feature flags, and test defaults.
- `DynamicPropertySource`: unknown runtime URL/host/port values.
- Migration tool: prepares a compatible schema.
- Assertions: prove the DataSource and business behavior use the right resource.

Never place real passwords into `application-test.yml` just because it belongs to the `test` profile. Use container test credentials or CI secrets per policy.

## 17. Custom configuration prefixes or multiple DataSources

Some applications do not use default `spring.datasource.*` properties for every connection. For example:

~~~properties
app.datasource.orders.url=...
app.datasource.audit.url=...
~~~

If the app builds two DataSources from these prefixes, the registry can register:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("app.datasource.orders.url",
            ordersPostgres::getJdbcUrl);
    registry.add("app.datasource.orders.username",
            ordersPostgres::getUsername);
    registry.add("app.datasource.orders.password",
            ordersPostgres::getPassword);

    registry.add("app.datasource.audit.url",
            auditPostgres::getJdbcUrl);
    registry.add("app.datasource.audit.username",
            auditPostgres::getUsername);
    registry.add("app.datasource.audit.password",
            auditPostgres::getPassword);
}
~~~

This illustrative snippet requires **two container instances** and app `@ConfigurationProperties`/`@Bean` definitions binding those exact keys. Registering new keys does not automatically create or alter DataSource beans.

### Verifying each DataSource/qualifier matters more than a single URL

When an app has a `@Primary DataSource` for orders and `@Qualifier("auditDataSource")` for audit, a test opening only the primary connection cannot prove the audit source is configured right. You should:

- Inject each DataSource using its qualifier.
- Open connections and inspect `DatabaseProductName` and catalog/schema on each resource.
- Verify repositories/transaction managers use the intended DataSource.
- When using `AbstractRoutingDataSource`, set the right tenant/route context before checking.
- Avoid reusing one container's connection details to accidentally configure both sources.

In Boot 3.3 test slices, `@AutoConfigureTestDatabase` replacement generally considers only the **primary DataSource**, rather than replacing every source in a multi-DB app. Using `Replace.NONE` asks to keep the DataSources, **without verifying by itself that each source is test-only**.

## 18. When is Testcontainers JDBC URL `jdbc:tc:` an alternative?

Testcontainers supports a special JDBC URL mode, for example:

~~~properties
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///sampledb
~~~

When matching Testcontainers JDBC driver support is present, connecting through a `jdbc:tc:...` URL can start a database container without declaring `@Container` in the usual way.

This is an **alternative approach**, not used in the runnable lab. Key differences:

| Approach | Container management | Configuration |
| --- | --- | --- |
| Static `@Container` + `@DynamicPropertySource` | JUnit/Testcontainers extension | Registry binds URL/user/password from container |
| Static `@Container` + `@ServiceConnection` | JUnit/Testcontainers + Boot typed details | Less boilerplate when supported |
| JDBC URL `jdbc:tc:...` | Testcontainers JDBC driver | Special URL; lifecycle tied to JDBC |
| Fixed external test DB | Infrastructure outside Testcontainers | Files/profiles/CI secrets; manually managed |

Do not mix `jdbc:tc:` with `postgres::getJdbcUrl` on the same DataSource without understanding their semantics. In Boot 3.3 test slices, still account for embedded database replacement; `Replace.NONE` is the explicit policy when keeping the configured connection source.

## 19. Test auto-config vs preparing the schema

`@DynamicPropertySource` only provides connectivity. It **does not create tables, indexes, or insert fixtures**. In the runnable lab, we use:

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

because this lesson covers dynamic connections, not Flyway/Liquibase. This comes with limitations:

- Hibernate generates the schema from current entities inside the test container.
- It does not prove production migrations deploy cleanly.
- It does not simulate legacy data in a DB running an earlier version.
- `create-drop` is unsuitable for production or shared databases.
- If production deployments use Flyway/Liquibase, dedicated migration integration tests are required.

In projects using Flyway or Liquibase:

1. Create a dedicated test database.
2. Run real migrations before repository queries.
3. Set `ddl-auto=validate` or `none` per contract.
4. Verify DB engine/schema/migration history.
5. Seed isolated fixtures and test behavior.

When using `@DataJpaTest` on PostgreSQL Testcontainers, ensure migration test auto-config is active if needed; never assume a schema exists just because the DataSource connected successfully.

### "Connection successful" is not "Integration successful"

A test running only:

~~~java
try (Connection c = dataSource.getConnection()) {
    assertTrue(c.isValid(2));
}
~~~

proves the connection is usable, not that the schema, JPA mapping, migrations, or business service work. That is why the runnable lab pairs **both assertion types**: JDBC metadata **and** a repository/service round-trip.

## 20. Common errors and diagnostics

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Mapped port can only be obtained after the container is started` | Calling `getMappedPort`/`getJdbcUrl` before container starts | Use `Supplier` and manage static `@Container` lifecycle properly |
| `@DynamicPropertySource method must be static` | Instance method or wrong signature | `static void method(DynamicPropertyRegistry registry)` |
| `DynamicPropertyRegistry` not found | Missing `spring-test`/Spring TestContext dependency | `spring-boot-starter-test` in `testImplementation` |
| No Docker environment found | Missing Docker daemon/socket/permissions | Fix runner/container runtime; never fake passes |
| `Connection refused` to `localhost:5432` | URL hardcodes internal port; mapped port differs | Use `postgres::getJdbcUrl` |
| Hikari connects to old port | Cached context reused after container restart/stop | Align container lifecycle and context cache |
| Environment shows Postgres URL yet queries run on H2 | Boot 3.3 `@DataJpaTest` replaced DataSource | `Replace.NONE`; assert JDBC metadata |
| `Failed to replace DataSource with embedded database` | Slice expects H2/HSQLDB without driver | `Replace.NONE` to keep container if intended |
| `No suitable driver` | Missing PostgreSQL JDBC driver on test runtime | Add `testRuntimeOnly org.postgresql:postgresql` |
| DataSource defaults to `localhost:5432` | Dynamic registry not picked up or wrong key | Check Spring test context and configuration prefix |
| Container `isRunning=true` yet app hits wrong DB | Custom bean/`ConnectionDetails` has different precedence | Inspect metadata of the actual injected DataSource |
| `@ServiceConnection` does not work | Missing `spring-boot-testcontainers` or unsupported container | Add module/config or use `DynamicPropertySource` |
| App cannot find business service in `@DataJpaTest` | Slice intentionally limits component scan | Switch to full context or `@Import` intentionally |
| Passes as single class, fails in full suite | Spring context cache reuses stale container | Isolate context/lifecycle or use `@DirtiesContext` when needed |
| Test rolls back yet row remains in DB | HTTP/server transaction or `REQUIRES_NEW`/auto-commit | Use properly scoped cleanup/transactions |
| `relation customer_accounts does not exist` | DDL/migrations did not run | Configure schema strategy for the test DB |
| Unique key insert collision | Shared hardcoded fixture email | Use test-specific UUIDs and cleanup/rollback |
| Hikari pool exhaustion | Unclosed JDBC connections or long-held transactions | Try-with-resources, reduce contention |
| CI Docker pull timeout | Network/registry restrictions | Use cached images/approved registry mirror |
| Passwords leaked in logs | Logging full Environment/URL/secrets | Sanitize; never log passwords/tokens |
| Passes on laptop, fails in CI | Docker differences, OS, architecture, resources | Standardize CI runner/image versions and test settings |

### Ordered debugging steps

1. Check **Spring Boot version**: sample code targets 3.3.5.
2. Check JDK/Gradle/Testcontainers dependencies and Docker daemon.
3. Did the container start? If not, read the Testcontainers root cause.
4. Does `@DynamicPropertySource` have the right static method/registry signature?
5. Are you passing a **supplier** instead of calling the getter too early?
6. Are the property keys actually read by Spring Boot or custom configuration?
7. Are you using `@SpringBootTest` or a `@DataJpaTest`/`@JdbcTest` slice?
8. On a Boot 3.3 slice, is `@AutoConfigureTestDatabase(replace = NONE)` present?
9. Is `@ServiceConnection` or a custom bean overriding connection details?
10. Open a real DataSource connection and inspect DB product/catalog/URL.
11. Query the real repository, not merely `Environment` or `container.isRunning`.
12. When failing only in the full suite, check context cache and container lifecycle.
13. For fixture/state issues, check transactions and cleanup.
14. Never log credentials/PII while debugging.

## 21. Hands-on exercises

**Exercise A — drop dynamic URL:** In the full-context class, temporarily remove `registry.add("spring.datasource.url", postgres::getJdbcUrl)` and run against an isolated test database. Explain why auto-configuration loses the endpoint or might pick up another URL from the environment. Restore the registration.

**Exercise B — switch to direct getter:** Try `registry.add("spring.datasource.url", postgres.getJdbcUrl())`. The code must **fail to compile** because the argument requires a `Supplier`. Restore the method reference.

**Exercise C — hardcode port:** Replace the container URL with `jdbc:postgresql://localhost:5432/accounts_full_test` on a study branch. Observe the risk of hitting the wrong DB or failing when the mapped port differs. Revert.

**Exercise D — H2 replacement:** In the JPA slice, remove `@AutoConfigureTestDatabase(replace=NONE)` and add the H2 test driver. On Boot 3.3, the slice may swap Postgres for H2; the metadata assertion must catch the wrong engine.

**Exercise E — metadata vs Environment:** Write an assertion checking only `environment.getProperty("spring.datasource.url")`; explain why it is insufficient if the DataSource was replaced. Rewrite it using Connection metadata.

**Exercise F — add a custom property:** Spin up an HTTP server on a dynamic mapped port and register `external.payment.base-url`. Use a real client in the app to call the mock server and assert request and response.

**Exercise G — same container, multiple test classes:** Use a base class declaring dynamic properties and a static container. Run a suite where the container stops between classes; observe context caching and choose an appropriate singleton lifetime or `@DirtiesContext`.

**Exercise H — service connection:** Add `spring-boot-testcontainers` and switch a separate class to `@ServiceConnection`. Remove the PostgreSQL dynamic registry in that class and assert JDBC metadata; compare boilerplate and behavior.

**Exercise I — profile:** Add `@ActiveProfiles("test")` and configure static logging/schema settings. Keep URL/credentials in `@DynamicPropertySource`. Explain each tool's responsibility.

**Exercise J — cleanup:** In the full-context test, use a UUID email and verify `@AfterEach` deletes only that email's row. Never use `deleteAll()` when tests run in parallel.

**Exercise K — Flyway migration:** Replace `ddl-auto=create-drop` with a Flyway migration creating `customer_accounts`. Run against the Postgres container and assert migration history plus repository round-trip.

**Exercise L — different database:** Use `MySQLContainer` matching your organization's MySQL version, swap the JDBC driver and registry entries, and verify `DatabaseProductName = MySQL`. Never assume PostgreSQL-specific SQL is portable.

**Exercise M — multiple services:** Register PostgreSQL and Redis mapped ports in the same registry; verify both the JPA repository and Redis client. Avoid expanding into an unstable stress test.

## 22. Pre-merge checklist

- [ ] Does the test genuinely require a **dynamic** endpoint/configuration?
- [ ] Is `@DynamicPropertySource` a static void method taking one `DynamicPropertyRegistry`?
- [ ] Does every `registry.add` pass a `Supplier`/method reference?
- [ ] Is the container started before Spring resolves connection settings?
- [ ] Are container host ports never hardcoded?
- [ ] Are containers managed by test lifecycles rather than unmanaged background Docker containers?
- [ ] Do dynamic properties match the exact keys read by DataSource/custom clients?
- [ ] Are `@ServiceConnection` and registry registrations avoided on the same datasource unless precedence is understood?
- [ ] Are only test-only containers/credentials used, without leaking secrets?
- [ ] On Boot 3.3 `@DataJpaTest`/`@JdbcTest`, is `Replace.NONE` used when keeping Testcontainers?
- [ ] Did I inspect `DataSource.getConnection().getMetaData()` for real?
- [ ] Is there at least one real query/operation proving integration?
- [ ] Is the schema initialized via test DDL/migrations rather than implicitly relying on production?
- [ ] Are transactions/cleanup aligned with full context vs test slice boundaries?
- [ ] Do fixtures use unique test IDs without deleting out-of-scope data?
- [ ] Does static container lifetime match `ApplicationContext` caching?
- [ ] Do parallel tests avoid restarting shared containers or mutating global `System` properties?
- [ ] Does CI have the right Docker runtime, image access, permissions, and networking?
- [ ] Do tests avoid silently falling back to H2/mocks when the production DB engine is required?
- [ ] Are logs free of passwords, tokens, and PII?
- [ ] Do Gradle/JUnit reports show tests actually executed rather than only cached tasks?

## 23. Official references

The sources below align with Spring Boot 3.3.x / Spring Framework 6.1.x; check exact dependencies/versions when upgrading to Boot 3.4+ or Boot 4.

- [Spring Framework — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): static methods, registry `Supplier`, precedence, inheritance, and context caching.
- [Spring Framework 6.1 — DynamicPropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/DynamicPropertySource.html): annotation API and test lifecycle.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` and `@DynamicPropertySource`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@DataJpaTest`, `@JdbcTest`, test datasource replacement.
- [Spring Boot 3.3 — AutoConfigureTestDatabase.Replace](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.4 — AutoConfigureTestDatabase.Replace](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `NON_TEST` recognizing test-scoped databases.
- [Testcontainers Java — JUnit 5 Quickstart](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` lifecycle.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`, `getJdbcUrl`, database/user/password.
- [Spring Data JPA — Testing and Transactions](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): default test slice rollback and context setup.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/): method lifecycle and Gradle/JUnit Platform.

**Takeaway:** `@DynamicPropertySource` is the bridge between **dynamically allocated endpoints in Testcontainers** and **Spring `Environment`**. Proper usage includes a static method, `DynamicPropertyRegistry.add(..., Supplier)`, a stable container lifecycle, accurate property names, and assertions against real JDBC/HTTP integration. For Spring Boot 3.3 JPA/JDBC slices, keep the container datasource using `@AutoConfigureTestDatabase(replace=NONE)`. Never treat a valid URL in properties as final proof: verify **where the `DataSource` actually opens connections**.
