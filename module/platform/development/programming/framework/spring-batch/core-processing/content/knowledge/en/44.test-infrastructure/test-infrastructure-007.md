# Test Profiles in Spring Batch: Isolated Test Infrastructure Configuration

## 1. What Problem Does a Test Profile Solve?

In a Spring Batch application, a job may use a `DataSource`, `JobRepository`, `PlatformTransactionManager`, scheduler, message broker, file storage, external APIs, and settings such as chunk size, file paths, and retry policies. If integration tests accidentally use settings from the live environment, results can become unstable or mutate data outside the test scope.

A **test profile** is a Spring configuration set activated during tests to select appropriate properties and beans for the test environment. Typically, we use a profile named `test`, declared in `application-test.yml` and enabled with `@ActiveProfiles("test")`.

Goals of a Spring Batch test profile:

- Select a dedicated test database containing the `BATCH_*` metadata schema and necessary business schemas.
- **Do not auto-launch jobs when the ApplicationContext starts**; tests explicitly trigger each job or step.
- Replace or simulate external dependencies such as HTTP clients, email gateways, or storage when the test scenario does not require live access.
- Use deterministic input data, temporary paths, and repeatable parameters.
- Control metadata lifecycle in `JobRepository` so one test does not affect another.
- Keep differences between test and production configurations transparent so test failures are easy to analyze.

A test profile **does not run tests by itself** and **does not replace** testing tools such as JUnit, `@SpringBatchTest`, `JobLauncherTestUtils`, `@Sql`, or Testcontainers. The profile selects the environment; those tools drive the test.

```text
JUnit test
   |
   +-- @ActiveProfiles("test")
   |          |
   |          +-- application.yml (shared configuration)
   |          +-- application-test.yml (test-specific configuration)
   |          +-- @Profile("test") beans (if any)
   |
   +-- @SpringBootTest / @SpringBatchTest
              |
              +-- Test ApplicationContext
                     |
                     +-- Test DataSource + JobRepository
                     +-- Job / Step / transaction manager
                     +-- Mock/fake external dependencies
```

## 2. Distinguishing Profiles, Property Sources, and Test Environments

In Spring, a **profile** is a named environment group that can be activated (for example `dev`, `test`, `staging`, `prod`). Spring Boot supports profile-specific properties via `application-{profile}.properties` or `application-{profile}.yml` files. Spring Framework also supports `@Profile` to conditionally register beans.

| Concept | Role | Example |
|---|---|---|
| `@ActiveProfiles("test")` | Activates a profile when running Spring Test | `@SpringBootTest` loads `application-test.yml` |
| `application-test.yml` | Provides dedicated configuration when the `test` profile is active | H2 URL, `spring.batch.job.enabled=false` |
| `@Profile("test")` | Registers a bean only when the `test` profile is active | Fake gateway used in tests |
| `@Profile("!test")` | Registers a bean only when the `test` profile is **not** active | Gateway connecting to the real service |
| `@TestPropertySource` | Attaches a set of properties or property sources to Spring Test | Quick override of a setting in one test class |
| `@SpringBootTest(properties = ...)` | Inline property override in a Boot test | Changing chunk size for one scenario |
| `@DynamicPropertySource` | Supplies dynamic properties before the ApplicationContext is created | JDBC URL, username/password from Testcontainers |

**Shared configuration** is still read from `application.yml` when the `test` profile is active. Properties with the same key in `application-test.yml` override shared values unless a higher-precedence source (such as a test-specific override) specifies something else.

A simple project layout:

```text
src/
  main/
    java/.../BatchApplication.java
    resources/
      application.yml
      application-prod.yml
  test/
    java/.../OrderJobIntegrationTest.java
    resources/
      application-test.yml
      sql/
        schema-test.sql
        orders-seed.sql
        orders-clean.sql
```

Files under `src/test/resources` are only on the **test classpath** in standard build configurations. This keeps test settings out of production artifacts. Separating files alone is not enough for safety; you must activate the right profile and verify the target database is a test database.

## 3. Basic Test Profile Configuration for Spring Batch 5.x

The examples below target **Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter, and Gradle**. Other versions—especially Spring Boot 4.x / Spring Batch 6.x—may change packages, APIs, and configuration rules; check the documentation for your project's version.

### 3.1. Declaring Dependencies

Groovy `build.gradle` example when the application uses the Spring Boot plugin/BOM for version management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-batch-test` provides utilities such as `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and `StepScopeTestUtils`. H2 provides an in-memory database for simple JDBC tests.

### 3.2. Production / Common Configuration

Suppose `src/main/resources/application.yml` contains non-environment-specific values:

```yaml
spring:
  application:
    name: order-batch

app:
  batch:
    chunk-size: 100
    input-directory: /var/app/orders
```

Keys such as `app.batch.chunk-size` are **application-defined properties**, not built-in Spring Batch properties. They only take effect if application code actually binds and uses them, for example via `@ConfigurationProperties` or `@Value`.

### 3.3. Configuration in `src/test/resources/application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:order_batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-test.sql

app:
  batch:
    chunk-size: 3
    input-directory: build/test-input

logging:
  level:
    org.springframework.batch: INFO
```

Meaning of each section:

| Key | Effect in Tests |
|---|---|
| `spring.datasource.url` | Selects a dedicated H2 database named `order_batch_test`. |
| `DB_CLOSE_DELAY=-1` | Keeps the H2 in-memory database alive after the last connection closes until the JVM exits. |
| `spring.batch.job.enabled=false` | Disables Spring Boot's automatic job execution on application startup. Tests invoke the launcher themselves. |
| `spring.batch.jdbc.initialize-schema=always` | Allows Spring Boot to initialize `JobRepository` tables and ID generators using the platform-matching script. |
| `spring.sql.init.mode=always` | Enables Spring Boot's general SQL initialization. |
| `spring.sql.init.schema-locations` | Points to the script creating **business** tables for tests. |
| `app.batch.chunk-size` | Overrides the business setting to make chunk boundary testing easier, assuming the app uses this property. |
| `app.batch.input-directory` | Directs file I/O into a test-managed data area. |

`spring.batch.jdbc.initialize-schema` is for **Spring Batch metadata**; `spring.sql.init.schema-locations` is for the application's business schema. If the application manages `BATCH_*` via Flyway or Liquibase, set `spring.batch.jdbc.initialize-schema=never` in the test profile and run the corresponding migrations to avoid creating the same tables twice.

**Scope note:** `spring.batch.job.enabled=false` only prevents Spring Boot from auto-launching jobs at startup. It does not prohibit `JobLauncher`, `JobOperator`, schedulers, or application code from explicitly launching jobs. If `@Scheduled` methods trigger batch jobs, control scheduling in tests as well.

## 4. Activating the Test Profile Properly

### 4.1. Using `@ActiveProfiles("test")`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderJobIntegrationTest {

    @Test
    void applicationContextStartsWithTestConfiguration() {
        // Spring context is created with the "test" profile.
    }
}
```

`@ActiveProfiles` belongs to **Spring Test**. It is evaluated when building the `ApplicationContext` for the test class. This annotation does not activate profiles for `java -jar` runs outside tests, nor does it alter the global JVM configuration for other test classes.

To use multiple profiles, declare:

```java
@ActiveProfiles({"test", "integration"})
```

When two profiles define the same key, profile order and property source precedence determine the final value; therefore avoid conflicting values across profiles unnecessarily. A base test class may declare `@ActiveProfiles` for subclasses to inherit. When changing an inherited profile list, be clear about each test class's intent.

### 4.2. Do Not Put `spring.profiles.active` Inside a Profile-Specific File

This is a configuration to avoid:

```yaml
# application-test.yml — DO NOT configure like this:
spring:
  profiles:
    active: test
```

In Spring Boot, `spring.profiles.active` belongs in **non-profile-specific** configuration; placing it inside a document activated by a profile can cause configuration errors. Put `@ActiveProfiles("test")` on the Spring Test class, or select the profile via the launch command or runner mode.

### 4.3. Overrides for Specific Scenarios

If one test needs a non-default chunk size:

```java
@SpringBootTest(properties = "app.batch.chunk-size=1")
@ActiveProfiles("test")
class SingleItemChunkTest {
    // When the context is created, this property takes effect in the test.
}
```

To load a specialized test property file:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:overrides/retry-test.properties")
class RetryPolicyIntegrationTest {
}
```

These are **illustrative standalone test classes**. Within one application, typically use `application-test.yml` for default test infrastructure and apply test-level overrides only for genuinely distinct scenarios. Each distinct property set can force Spring Test to build a separate context, slowing suite startup.

## 5. Creating and Isolating Test Data

The profile selects the database; SQL files prepare the structure and fixtures.

### 5.1. Business Schema

Example `src/test/resources/sql/schema-test.sql`:

```sql
CREATE TABLE TEST_ORDER (
    ID BIGINT PRIMARY KEY,
    CUSTOMER_CODE VARCHAR(40) NOT NULL,
    STATUS VARCHAR(16) NOT NULL,
    TOTAL_AMOUNT DECIMAL(12, 2) NOT NULL
);
```

`BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, their context tables, and sequences/ID-generation tables are created by the Spring Batch initializer as shown in Section 3.3. There is no need to copy raw `BATCH_*` DDL into `schema-test.sql` when the initializer already runs cleanly.

### 5.2. Seeding and Cleaning Up per Test Method

`src/test/resources/sql/orders-seed.sql`:

```sql
INSERT INTO TEST_ORDER (ID, CUSTOMER_CODE, STATUS, TOTAL_AMOUNT) VALUES
    (1, 'A001', 'NEW', 125.50),
    (2, 'B002', 'NEW', 80.00),
    (3, 'C003', 'HOLD', 250.00);
```

`src/test/resources/sql/orders-clean.sql`:

```sql
DELETE FROM TEST_ORDER;
```

Use `@Sql` to manage fixtures per test method:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@Sql(scripts = "/sql/orders-seed.sql",
     executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/orders-clean.sql",
     executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
```

These annotations can be placed on the test class or test method. The schema is created once during context startup; seed data is inserted before each test. Do not put all test-method-specific fixture data into `schema-test.sql`, because it will not automatically regenerate on every method run.

**Be careful with shared H2 URLs:** `jdbc:h2:mem:order_batch_test;DB_CLOSE_DELAY=-1` can stay alive in the same JVM after a context closes. If multiple independent contexts use the same DB name and each tries to initialize the schema, "table already exists" errors can occur. Assign a distinct DB name per test context or use an appropriate schema creation/cleanup strategy. When running in parallel, ensure each test group has an independent database/repository.

## 6. Running Jobs Under Control in a Test Profile

`@SpringBatchTest` integrates Spring Batch test utilities. With Spring Batch 5.x, it can be combined with `@SpringBootTest` and `@ActiveProfiles("test")`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
@Sql(scripts = "/sql/orders-seed.sql",
     executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/orders-clean.sql",
     executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
class OrderBatchProfileIT {

    @Autowired
    private JobLauncherTestUtils launcherTestUtils;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("orderJob")
    private Job orderJob;

    @BeforeEach
    void prepare() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(orderJob);
    }

    @AfterEach
    void removeBatchMetadata() {
        repositoryTestUtils.removeJobExecutions();
    }

    @Test
    void processesOnlyNewOrders() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addLong("run.id", 582L)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer processed = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'DONE'",
                Integer.class);
        assertEquals(2, processed);

        Integer untouched = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'HOLD'",
                Integer.class);
        assertEquals(1, untouched);
    }
}
```

This example **assumes the application already registers a `Job` bean named `orderJob`** that transitions `NEW` orders to `DONE`, configures a transaction manager, and uses `TEST_ORDER`. `@SpringBootTest` starts the application context and `@SpringBatchTest` supplies the test beans. If the project defines multiple jobs, designate the exact job to launch as shown so you do not rely on automatic bean resolution.

Key takeaways:

1. `spring.batch.job.enabled=false` prevents `orderJob` from **auto-running** on test context startup; `launcherTestUtils.launchJob(parameters)` executes the job explicitly.
2. `@ActiveProfiles("test")` ensures the test uses H2/test profile, **provided application configuration and dependency wiring do not manually override the DataSource with another bean**.
3. `JobParameters` establish job instance identity. Rerunning a `COMPLETED` job with the same identifying parameters while retaining metadata can fail with `JobInstanceAlreadyCompleteException`.
4. `JobRepositoryTestUtils.removeJobExecutions()` deletes all executions in **the repository the utility points to**. Use it only against a dedicated test repository, never when other tests share that repository concurrently.
5. `@Sql` cleans business data, while `JobRepositoryTestUtils` cleans metadata. These are two distinct datasets.
6. Generally do not put `@Transactional` on the whole test method calling `launchJob()`; job/step transactions may commit independently, invalidating the assumption that "test rollback cleans everything".

### 6.1. Running a Single Step

To test a single step using Batch infrastructure loaded from the `test` profile, you can call:

```java
JobExecution execution = launcherTestUtils.launchStep("processOrdersStep");
assertEquals(BatchStatus.COMPLETED, execution.getStatus());
```

`launchStep` is available on `JobLauncherTestUtils` in Spring Batch 5.x. The step runs inside a wrapper test job built by the utility, so job-level listeners or transitions of the original job do not necessarily fire as they would in a full job launch. When the goal is testing the complete flow, launch the actual job.

## 7. Using `@Profile` to Swap Beans per Environment

Profiles also control which beans are registered in the Spring container. Suppose a job sends a notification upon completion and production calls an external API, whereas in integration tests we want to capture notifications in memory.

```java
public interface NotificationGateway {
    void send(String orderId);
}
```

Production bean:

```java
@Configuration
@Profile("!test")
class ProductionGatewayConfiguration {

    @Bean
    NotificationGateway notificationGateway(ExternalNotificationClient client) {
        return orderId -> client.sendOrderNotification(orderId);
    }
}
```

Test bean:

```java
@TestConfiguration
class NotificationTestConfiguration {

    @Bean
    @Primary
    NotificationGateway notificationGateway() {
        return orderId -> {
            // Test fake: can record orderId into a list for assertions.
        };
    }
}
```

With `@TestConfiguration`, tests can import it explicitly:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(NotificationTestConfiguration.class)
class NotificationBatchIT {
}
```

`ExternalNotificationClient` and the concrete implementation above are **hypothetical application components**, not Spring Batch APIs. `@Primary` selects the fake when multiple beans of the same type exist, but it will not prevent a production bean from initializing and calling an external service at startup if that bean was still created. When real integration must be disabled completely in tests, guard production configuration with profiles/properties or explicit dependency injection.

If you want to use `@Profile("test")` to pick up a fake via component scanning, replace `@TestConfiguration` with a standard `@Configuration` and ensure it falls within the scan/import scope. Placing `@Profile` on an unregistered class has no effect.

### 7.1. Distinguishing Fakes, Mocks, and Real Integration

| Dependency Type | When to Use | Limitations |
|---|---|---|
| Interface fake implementation | Tests need to track data without network dependencies | Must build fake behavior representative enough for the case. |
| Mockito mock | Tests only need to verify calls/arguments or return canned data | Does not verify real connection protocols. |
| Testcontainers / real test service | Integration tests for SQL, message brokers, transactions, or protocols | Slower and requires managing infrastructure lifecycle. |

When testing batch processing logic without caring about the gateway, mocks/fakes are usually appropriate. When verifying contracts with Kafka, databases, or storage, the `test` profile should point to a real test service (often containerized) while preserving key interfaces and configuration.

## 8. Controlling Schedulers and Automatic Job Launches

Two mechanisms are frequently confused:

- `spring.batch.job.enabled=false`: disables Boot's automatic `Job` execution at application startup.
- `@Scheduled`: an application method triggered on a timer by a scheduler, which may call `JobLauncher` itself.

If a scheduled method remains active during tests, the job may run concurrently with assertions. Make scheduling conditional:

```java
@Configuration
@EnableScheduling
@Profile("!test")
class BatchSchedulingConfiguration {
    // Register production @Scheduled tasks here.
}
```

In an application where `@Scheduled` methods are scattered across already-created beans, simply putting `@Profile` on one configuration with `@EnableScheduling` might conflict with scheduling enabled by another configuration. A cleaner design is grouping scheduling registration into a configuration toggleable by profile or property, and launching jobs directly via test utilities.

An option using a dedicated property:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app.batch.scheduler",
    name = "enabled",
    havingValue = "true")
@EnableScheduling
class BatchSchedulerConfiguration {
}
```

In `application-test.yml`:

```yaml
app:
  batch:
    scheduler:
      enabled: false
```

`app.batch.scheduler.enabled` is an application-defined key; this pattern only works if scheduling is managed through that configuration. If multiple beans directly carry `@Scheduled`, apply the same control strategy there as well.

## 9. Testcontainers: Keeping the Test Profile While Using a Production-Like Database

H2 works well for many tests, but with PostgreSQL, MySQL, or Oracle, vendor-specific SQL, transaction isolation, and locking can differ significantly. You can keep using a test profile while pulling connections from a PostgreSQL container to test infrastructure closer to production.

Example dependencies for Spring Boot 3.1+:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

### 9.1. Providing the DataSource via `@ServiceConnection`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgresBatchIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void appStartsUsingPostgres() {
        // Add query/job assertions according to the test goal.
    }
}
```

Create `src/test/resources/application-test-postgres.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-postgres-test.sql
```

Do not declare a static H2 URL in this profile. `@ServiceConnection` supplies connection details directly from the PostgreSQL container; the framework wires a `DataSource` to the ephemeral database. The `BATCH_*` metadata script is selected by platform once the database is detected. If Flyway or Liquibase owns the schema, run migrations and set `initialize-schema` to `never`.

### 9.2. Providing Properties via `@DynamicPropertySource`

When a project does not use `@ServiceConnection`, connection details can be supplied dynamically:

```java
@Testcontainers
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgresBatchWithDynamicPropertiesIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Additional imports: `org.springframework.test.context.DynamicPropertyRegistry` and `org.springframework.test.context.DynamicPropertySource`. This is an **alternative** to the `@ServiceConnection` example; do not use both to configure the same datasource. Testcontainers requires Docker or a compatible container runtime locally and in CI.

### 9.3. Isolation Between Container-Backed Tests

A container may be reused across a test class or via Spring context caching. If Test A and Test B both wipe a `JobRepository` currently in use by another test, parallel runs will fail unpredictably. Clearly define database ownership and fixture/metadata cleanup timing; for restart tests, preserve the database and identifying parameters between the failed run and the rerun.

## 10. When Should You Split Multiple Test Profiles?

A single `test` profile suffices for most modules, though larger applications may split by infrastructure type:

| Profile | Infrastructure | Example Scenarios |
|---|---|---|
| `test` | H2, fake gateways, job startup disabled | Fast integration tests with H2-compatible SQL. |
| `test-postgres` | PostgreSQL Testcontainers, real schema/migrations | Testing JDBC readers/writers and locking on PostgreSQL. |
| `test-s3` | Fake/emulated object storage or dedicated test endpoint | Testing jobs that read/write files via storage APIs. |
| `test-restart` | Database with controlled lifecycle preserving metadata across launches | Testing checkpoints and restarts. |

The names above are **suggested conventions**, not built-in Spring Batch defaults. Avoid creating many profiles differing by only a single key; use test-level overrides or helper configurations where appropriate. Split profiles only when infrastructure and test lifecycles genuinely differ.

## 11. Test Profiles and Testing `@StepScope`, `@JobScope`

`@StepScope`/`@JobScope` beans read parameters or execution context while the scope is active. The test profile supplies beans and properties, while **scope test utilities** supply the simulated execution context.

Example step-scoped bean:

```java
@Bean
@StepScope
public OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderFileReader(inputFile);
}
```

To invoke this bean in a unit/integration test with a Spring context:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "build/test-input/orders.csv")
        .toJobParameters();

StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution(params);

String fileName = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> orderFileReader.getFileName());

assertEquals("build/test-input/orders.csv", fileName);
```

`OrderFileReader` is an application-defined class, and `getFileName()` is merely an illustrative method. For this code to work, the test must obtain the injected scoped proxy from a Spring context with the corresponding scope configured. `MetaDataInstanceFactory` only creates in-memory metadata; `StepScopeTestUtils` opens the `StepContext` for the callback. `@ActiveProfiles("test")` **does not automatically activate step scope**.

In Spring Batch 5.x, `@SpringBatchTest` configures test listeners for step/job scope; you can declare a factory method returning `StepExecution` in the test so the listener picks up custom metadata.

## 12. Property Precedence and Subtle Configuration Bugs

Suppose `application-test.yml` declares:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:safe_test
```

Yet a test class has:

```java
@SpringBootTest(properties =
    "spring.datasource.url=jdbc:postgresql://example-host:5432/orders")
```

The property supplied by the test annotation can override the H2 URL. Therefore, **having the `test` profile active does not guarantee you are connected to H2**. Understand property source precedence, especially when CI or an IDE passes environment variables, system properties, `@TestPropertySource`, `@DynamicPropertySource`, or command-line flags.

A test can assert key environment attributes explicitly:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;

class ActiveProfileCheck {

    @Autowired
    private Environment environment;

    @Test
    void testProfileIsActive() {
        assertTrue(environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("test")));
    }
}
```

This snippet must live inside a Spring Test class whose context is enabled via `@ActiveProfiles("test")` and a context-loading annotation such as `@SpringBootTest`. Checking active profiles helps debugging, while proving the datasource actually points to the test environment requires inspecting connection metadata/URLs per project policy rather than relying solely on profile names.

### 12.1. Property Application Order

General rule: **higher-precedence configuration sources win on duplicate keys**. In Spring Boot tests, `@DynamicPropertySource` and test-inline properties generally override settings from `application-test.yml`. The exact hierarchy across all sources depends on the Boot version and startup mode; consult the *Externalized Configuration* section of the Spring Boot documentation when multiple sources define the same key.

To minimize conflicts, define any given key in as few places as possible; put default test infrastructure in `application-test.yml` and override only in test classes with a clear, deliberate need.

## 13. Common Test Profile Configuration Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `@ActiveProfiles("test")` is set but test hits an external DB | Custom `DataSource` bean or higher-precedence property overrides it | Inspect datasource beans, property sources, and the actual connection URL. |
| Job auto-runs on context startup | Missing `spring.batch.job.enabled=false`, active scheduler, or startup hook | Disable auto-run in the profile; control application schedulers/launchers separately. |
| `Table BATCH_JOB_INSTANCE not found` | JDBC metadata not initialized, wrong datasource/schema, or initializer disabled | Enable the proper Batch schema initializer or run metadata migrations. |
| `Table TEST_ORDER not found` | Missing business DDL | Check `schema-locations`, `mode`, and resource paths. |
| `Table ... already exists` | Schema re-created on an unreset DB or multiple initializers active | Isolate databases, enforce a single DDL owner, manage lifecycle. |
| `No qualifying bean of type Job` or `NoSuchBeanDefinitionException` | Job not scanned/imported or excluded by profile conditions | Verify component scan, `@Import`, `@Profile`, and config properties. |
| `JobInstanceAlreadyCompleteException` | Same identifying parameters as an already completed instance | Clean test metadata or use a fresh instance; do not do this mid-restart test. |
| Tests fail when run in parallel | Shared H2 database, shared repository, or global cleanup | Isolate databases/test contexts; avoid wiping another test's data. |
| `@StepScope` bean fails in test | Step scope is not active | Use `StepScopeTestUtils`, scope-supporting listeners, or run a real step. |
| Passes locally, fails in CI | Different profiles, env vars, filesystem, timezone, database, or container runtime | Explicitly declare active profiles and CI resources; eliminate workstation assumptions. |
| Test gets real gateway instead of fake | Both beans created or fake not imported | Check `@Profile`, `@Primary`, and scan/import configuration. |
| Data leaks between tests | Asymmetric seed and cleanup, job transactions committing independently | Use `@Sql` before/after, scope-bound metadata resets, and per-test databases. |

## 14. Reliability and Maintainability Notes

### 14.1. Avoid Workstation Clock and Filesystem Dependencies

Many batch jobs depend on the current date or timestamped filenames. The test profile should allow the application to receive a `Clock`, business date, or input path via dependency injection or properties. For example, supply `Clock.fixed(...)` in a test bean if production code is designed to inject `Clock`. Merely shrinking chunk size in YAML will not make time-dependent values deterministic.

Paths like `build/test-input` are relative to the working directory. For file I/O tests, use JUnit's `@TempDir` to create a dedicated area per test and pass paths into the job via `JobParameters` instead of hardcoding a shared directory.

### 14.2. Keep Configurations Close to Production for Integration Tests

If a test aims to verify transactions, SQL paging, partitioning, restartability, or locking, retain the influential settings and swap only external infrastructure for an equivalent test environment. A test using an in-memory repository when production uses a JDBC `JobRepository` cannot verify real database constraints and transactions.

### 14.3. Do Not Share Metadata While Testing Restart

In a restart test, the first run must genuinely fail, persisting `FAILED` metadata and `ExecutionContext`; the second run must pass the exact same identifying parameters so Spring Batch resolves the same job instance. Cleaning `JobRepository` between the two runs turns it into something other than a restart test. Use a dedicated repository or an isolated fixture for each restart test.

### 14.4. Do Not Treat Profiles as a Security Mechanism

Profiles are strictly a configuration and bean-selection mechanism. Test profiles should be designed without production credentials and should not allow an accidental override to connect to live environments. Even test credentials should come from environment variables or a secret manager if needed; never commit secrets into the repository.

### 14.5. Control Context Caching

Spring Test can cache `ApplicationContext` instances across test classes with matching configurations, improving speed. Classes with differing profiles or properties create new contexts. A reused context may continue holding an in-memory H2 database and singleton state. Therefore, when sharing contexts, business data, bean state, and Batch metadata must be reset or scoped cleanly. Reserve `@DirtiesContext` for cases where recreating the context is genuinely required, as it increases suite startup time.

## 15. Workflow for Adopting Test Profiles in a Spring Batch Project

You can build your test infrastructure in this sequence:

1. **Classify the test type:** unit test, reader/writer test, single-step run, full-job run, or restart. Do not spin up a Spring context or database for pure unit tests if unnecessary.
2. **Select the profile:** use `test` for baseline infrastructure; create `test-postgres` or specialized profiles only when requirements truly diverge.
3. **Create property files:** configure the test datasource, disable job auto-run, define schema initialization, and set test business properties.
4. **Activate the profile in Spring Test:** apply `@ActiveProfiles("test")`, combined with `@SpringBootTest` and `@SpringBatchTest` when running jobs or steps.
5. **Assign schema ownership:** Batch initializer for metadata, SQL initializer or migrations for business tables—avoid duplicate DDL execution.
6. **Load predictable fixtures:** use `@Sql`, builders, or test-data factories; keep DDL separate from seed data.
7. **Control job lifecycle:** invoke `JobLauncherTestUtils` with explicit `JobParameters` rather than letting startup or schedulers launch jobs.
8. **Verify outcomes:** check job/step status, business data, and metadata when repository persistence is part of the test goal.
9. **Clean data at the right scope:** reset both business data and batch metadata without deleting data belonging to concurrent tests.
10. **Switch to a real engine when needed:** for vendor-specific SQL or transaction/concurrency behavior, use Testcontainers and migrations to stay faithful to production.

### Hands-On Exercises

Build two tests for an order state-transition job:

**Exercise 1 — H2 Test Profile:**

- Create `application-test.yml` with in-memory H2 and `spring.batch.job.enabled=false`.
- Populate `TEST_ORDER` with `NEW` and `HOLD` records using `@Sql`.
- Use `@SpringBatchTest` + `JobLauncherTestUtils.launchJob(...)` to run the job.
- Verify processed order counts and untouched records; clean up data and metadata.

**Exercise 2 — PostgreSQL Integration Profile:**

- Create a `test-postgres` profile using Testcontainers and PostgreSQL-compatible schema migrations.
- Run the same business test case from Exercise 1.
- Introduce a unique or foreign-key constraint into the schema to observe how the test catches data errors.
- Ensure both test groups use separate repositories and can run independently in CI.

Through these two exercises, you see that **the test profile governs the infrastructure the test relies on**, while assertions and fixtures govern what batch behaviors are verified.

## 16. References

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): activating profiles, profile-specific files, and environment-based configuration.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence order, and overrides.
- [Spring Boot Reference — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): Batch metadata schema, SQL initialization, and migrations.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, and testing scoped beans.
- [Spring Framework Reference — Context Configuration with `@ActiveProfiles`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html): how Spring Test resolves active profiles.
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): container databases and `@ServiceConnection` in integration tests.

