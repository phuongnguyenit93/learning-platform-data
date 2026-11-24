# Separating Secrets, Environment, and Data for Each Test Suite

A Spring test suite typically requires three distinct groups of information: configuration to choose how the application behaves, credentials to connect to services, and data used as inputs or initial state. Mixing all three into one configuration file or sharing resources with real runtime environments makes tests dependent on the author's machine, risks accidentally accessing production, and makes CI runs unstable.

Separate clearly:

- **Environment configuration** describes how the test connects and behaves: profiles, URLs, ports, timeouts, feature flags, databases, and runtime options.
- **Secrets** are credentials or keys that grant access: passwords, API tokens, private keys, client secrets, signing keys, and service credentials.
- **Test data** consists of records, fixtures, sample requests, CSV/JSON files, or initial state needed by tests to verify behavior.

These three groups have different lifecycles and management practices. Profiles select appropriate beans and configurations; property sources supply configuration values; secret stores or environment variables supply secrets; fixtures and data-creation mechanisms give each test isolated, reproducible state.

## 1. Distinguishing Configuration, Secrets, and Data

For example, an ordering application may need:

| Group | Example | Appropriate Management Place |
|---|---|---|
| Environment configuration | Sandbox API URL, JDBC URL, timeout, profile | Profiles and property sources |
| Secrets | Sandbox API key, database password, signing key | Secret manager or environment variables supplied at runtime |
| Test data | Sample orders, fake customer IDs, product lists, JSON payloads | Fixtures, builders, SQL scripts, or test factories |

A value that varies across local, CI, and integration environments is usually configuration. A value that grants access is a secret, even when used only in test environments. A record created to test business rules is test data.

For example:

- **payment.base-url** is configuration.
- **payment.api-key** is a secret.
- An order with ID **order-test-17** and total amount 250,000 VND is test data.

Do not place an API key inside a JSON fixture merely because a test needs to send a request with an `apiKey` field. If it is a real credential, it must come from a secret source. If the test only verifies request structure, use a dummy value with no access privileges.

## 2. Using Profiles to Separate Test Environments

Spring Profiles allow registering beans or configurations that become active only when the corresponding profile is activated. An application might have profiles such as:

- **default**: default configuration for development or simple cases.
- **test**: configuration dedicated to automated tests.
- **integration**: configuration used when testing multiple collaborating components.
- **local**: configuration for running the application on a developer machine.
- **staging** or **production**: configuration for the corresponding deployment environment.

Profile names are project conventions. There is no need to create a separate profile for every test class; profiles should represent meaningful configuration groups.

### Activating profiles in Spring TestContext

With JUnit Jupiter and the Spring TestContext Framework, you can use **@ActiveProfiles**:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@ActiveProfiles("test")
class OrderServiceTest {
    // Test methods
}
~~~

Spring TestContext activates the **test** profile when creating the `ApplicationContext` for the test. Beans matching the profile condition will be registered.

Example of a fake payment gateway registered only in the `test` profile:

~~~java
@Configuration
@Profile("test")
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Production configuration can register the real adapter under the appropriate profile:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentHttpClient client) {
        return new HttpPaymentGateway(client);
    }
}
~~~

When a test needs `FakePaymentGateway`, it activates the **test** profile and loads the corresponding configuration. In production, the `production` profile supplies the real adapter.

Do not treat profiles as a security boundary. Profiles only decide which configurations and beans are active; they do not protect credentials themselves, do not prevent a test from accidentally calling a production endpoint, and do not replace least-privilege service account permissions.

### Using multiple profiles when truly needed

Multiple profiles can be activated:

~~~java
@ActiveProfiles({"test", "integration"})
@SpringJUnitConfig(IntegrationTestConfig.class)
class OrderIntegrationTest {
}
~~~

Use multiple profiles when they represent independent configuration groups that compose cleanly. Creating too many tiny profiles to toggle individual properties makes profile combinations hard to understand and predict.

An **integration** profile can select integration beans and configurations; URLs, ports, and timeouts should still be supplied through appropriate property sources.

## 3. Separating Profile Configuration with Property Files

Spring Framework provides several ways to add properties to `Environment`. With Spring TestContext, a direct approach is **@TestPropertySource**.

You can create a file in test resources, such as **src/test/resources/test-config/order-test.properties**:

~~~properties
orders.currency=VND
orders.shipping.fee=30000
payment.mode=fake
payment.timeout=2s
~~~

The test loads this file:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(
    locations = "classpath:test-config/order-test.properties"
)
@ActiveProfiles("test")
class OrderPropertiesTest {

    @Autowired
    private Environment environment;

    @Test
    void loadsTestProperties() {
        assertEquals("VND", environment.getProperty("orders.currency"));
        assertEquals("fake", environment.getProperty("payment.mode"));
    }
}
~~~

**@TestPropertySource** can load property files or declare properties inline on the annotation:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(properties = {
    "orders.currency=VND",
    "payment.mode=fake",
    "payment.timeout=2s"
})
class InlineTestProperties {
}
~~~

Use inline properties for a few values very specific to a single test. If multiple tests share configuration, a test properties file or shared configuration class is easier to maintain.

### Property precedence order

When the same key is defined in multiple sources, the final value a bean receives depends on property source precedence. In Spring TestContext, properties declared inline or loaded via **@TestPropertySource** have higher precedence than ordinary property sources such as **@PropertySource**, environment variables, and system properties.

**@DynamicPropertySource** has higher precedence than **@TestPropertySource**, making it suitable for values available only after a test resource starts, such as a database container port.

Avoid defining the same key in too many places. When overriding, keep the intent explicit and verify the effective value through **Environment** or bound beans.

## 4. Profile-Based Configuration in Spring Boot

If the project uses Spring Boot, the Config Data mechanism lets you organize profile-specific configuration files, for example:

~~~text
src/
  main/
    resources/
      application.yml
  test/
    resources/
      application-test.yml
~~~

Example **application-test.yml**:

~~~yaml
orders:
  currency: VND
  shipping:
    fee: 30000

payment:
  mode: fake
  base-url: http://localhost:9090
  timeout: 2s
~~~

When the **test** profile is active, Spring Boot can load the corresponding profile configuration. In tests:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {
}
~~~

Note the distinction: **application-test.yml** is a Spring Boot configuration mechanism. A test using only plain Spring Framework TestContext with **@SpringJUnitConfig** does not automatically get all Spring Boot Config Data rules. In plain Spring Framework, load properties with **@TestPropertySource**, **@PropertySource**, **@PropertySources**, initializers, or appropriate `Environment` configuration.

Do not put real credentials into **application-test.yml** committed to the repository. This file fits non-sensitive values such as timeouts, mock modes, test schema names, or localhost URLs.

## 5. Managing Secrets Separately from Ordinary Properties

Secrets commonly appear in configurations for databases, payment services, email, OAuth clients, or third-party APIs. Even when used only for testing, credentials can grant permission to read data, create transactions, or invoke paid resources.

Important principles:

1. Do not commit passwords, API tokens, private keys, or client secrets to Git.
2. Do not put real secrets into YAML/Properties files, test fixtures, code examples, or annotations.
3. Supply credentials via CI secret managers, environment variables, or security mechanisms provided by the deployment platform.
4. Use test accounts with least privilege that access only test resources.
5. Do not write credentials to logs, exception messages, assertion failures, or CI artifacts.
6. Revoke and rotate credentials when exposure is suspected or when their lifecycle ends.

### Using environment variables to supply secrets

With Spring Boot, properties can reference environment variables:

~~~yaml
payment:
  base-url: ${PAYMENT_SANDBOX_URL:http://localhost:9090}
  api-key: ${PAYMENT_SANDBOX_API_KEY:local-placeholder}
~~~

The default value **local-placeholder** is merely a dummy string for running local tests against a fake adapter or mock server. It is not a credential capable of authenticating against a real service.

In CI, pipelines can supply **PAYMENT_SANDBOX_API_KEY** from the platform's secret store. Do not store secret values in workflow files, logs, or command lines that might be recorded.

In plain Spring Framework, environment variables can be read via **Environment** or placeholder resolvers:

~~~java
@Configuration
class PaymentClientConfiguration {

    @Bean
    PaymentClient paymentClient(Environment environment) {
        String apiKey = environment.getRequiredProperty(
                "payment.api-key"
        );

        return new PaymentClient(apiKey);
    }
}
~~~

If real bean configuration requires credentials, ensure tests use fakes or test-specific configuration when calling real services is unnecessary. Do not require every developer to hold sandbox credentials just to run unit tests.

### Separating secrets by environment

Local, CI, and integration environments may need different credentials:

| Execution Environment | Secret Source | Recommended Credentials |
|---|---|---|
| Local unit tests | No real secret needed | Dummy or mock values |
| Local integration tests | Developer-configured environment variables or secret store | Least-privilege sandbox account |
| CI | CI secret store | Test credentials scoped to jobs that need them |
| Production | Secret manager or secret management platform | Least-privilege production credentials |

Never reuse production credentials for testing. A configuration mistake could cause a test to write or delete real data. Use dedicated sandbox endpoints and accounts, or block outbound network access in test groups that do not require external services.

### Keeping secrets out of logs

Avoid logging entire `Environment` objects, property objects, or HTTP headers. When diagnostics are needed, log only configuration names, whether a value was provided, or non-sensitive identifiers. Never log API keys, passwords, or `Authorization` headers.

If a test fails due to a missing secret, the error message should clearly state which environment variable was not supplied without printing its value.

## 6. Do Not Use Profiles to Hide Production Configuration

A test configuration may replace real beans with fakes, yet that does not mean every production configuration bug will be caught. Divide tests by purpose:

- Unit tests use fakes/stubs/mocks and need no credentials.
- Integration tests use real test databases or brokers to verify adapters and configurations.
- Contract tests can verify request/response interactions against a sandbox.
- Deployment smoke tests check environment configuration after deployment within safe boundaries.

If a test forces the **test** profile, it may miss that the production profile is missing a bean or has a wrong endpoint. Add separate configuration tests or smoke tests to verify those aspects without calling production in the unit suite.

A test profile should not automatically make every external component vanish if the goal is integration testing. Decide explicitly which dependencies must be real, which can be simulated, and what the test needs to prove.

## 7. Separating Test Data from Configuration

Test data describes scenario inputs or state. It can live in code, builders, JSON, CSV, or SQL scripts.

Example JSON fixture:

~~~json
{
  "customerId": "customer-test-18",
  "currency": "VND",
  "items": [
    {
      "sku": "SKU-RED-01",
      "quantity": 2,
      "unitPrice": 125000
    }
  ]
}
~~~

This fixture contains fake business data and no credentials. It can live in **src/test/resources/fixtures/order-valid.json** and be loaded in tests.

Test data should be:

- Synthetic or properly anonymized.
- Limited to fields needed for the scenario.
- Named clearly according to business meaning.
- Reproducible and independent of current production data.
- Free of real tokens, passwords, emails, or personal information unless necessary.

Do not copy an entire production database to use as fixtures. Production data may contain personal data, credentials, sensitive records, or unstable state. Create synthetic data matching business contracts instead.

## 8. Creating Data with Factories, Builders, and Fixtures

There are three common ways to prepare data.

### Factories or builders

Use a factory when tests need many objects with similar structure differing in just a few attributes.

~~~java
final class OrderTestData {

    static Order validOrder() {
        return new Order(
                "order-test-18",
                "customer-test-7",
                List.of(new OrderLine("SKU-RED-01", 2, new BigDecimal("125000")))
        );
    }

    static Order orderForCustomer(String customerId) {
        return new Order(
                "order-test-19",
                customerId,
                List.of(new OrderLine("SKU-BLUE-02", 1, new BigDecimal("80000")))
        );
    }
}
~~~

Factories reduce repetitive Arrange blocks. However, do not let a factory call production services to compute expected values for the very rule the test is verifying. Input data should be declared explicitly.

Builders fit entities with many optional fields:

~~~java
Order order = Order.builder()
        .id("order-test-21")
        .customerId("customer-test-9")
        .status(OrderStatus.PENDING)
        .total(new BigDecimal("250000"))
        .build();
~~~

Builders should only construct data. Business rules under test remain in production objects and require independent expected assertions.

### Fixture files

Fixture files fit large payloads or data shared across multiple tests. You can store JSON, XML, CSV, or YAML in test resources.

Advantages:

- Separates data from test logic.
- Easy to read multi-field payloads.
- Same fixture can be reused across unit and integration tests when structured suitably.
- Data changes can be reviewed in Git.

Avoid creating huge fixtures full of unrelated data. A good fixture clearly expresses its scenario and keeps only needed fields.

### SQL scripts

For persistence tests, Spring TestContext supports **@Sql** to execute scripts before or after test methods:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
@Sql(
    scripts = "/sql/orders-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsThePreparedOrder() {
        Optional<OrderEntity> order = repository.findById("order-test-18");

        assertTrue(order.isPresent());
        assertEquals("customer-test-7", order.get().getCustomerId());
    }
}
~~~

Example **orders-before-test.sql**:

~~~sql
INSERT INTO customers (id, name)
VALUES ('customer-test-7', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('order-test-18', 'customer-test-7', 'PENDING');
~~~

Scripts must match the database schema and dialect used by the test. When a test uses Spring-managed transactions, scripts may run inside the transaction per default or **@Sql** transaction configuration. Understand transaction modes well to prevent data from committing unexpectedly.

You can declare a cleanup script in the **AFTER_TEST_METHOD** phase when tests do not roll back or need to clean up separately committed side effects:

~~~java
@Sql(
    scripts = "/sql/cleanup-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

If the test already rolls back the entire transaction, a cleanup script may not be needed. Avoid deleting shared data with overly broad conditions; cleanup scripts must target only data owned by the test.

## 9. Isolating Data Between Tests

Tests must be independent so they can run individually, repeatedly, in parallel, or in any order. If one test depends on data created by another test, the suite becomes flaky.

Common strategies:

### Transaction rollback

For persistence tests with Spring-managed transactions, you can annotate the class or method with **@Transactional**. Spring TestContext normally rolls back the transaction after each test method.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderPersistenceTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void createsOrderWithinTestTransaction() {
        repository.save(new OrderEntity("order-tx-1", "customer-tx-1"));

        assertTrue(repository.findById("order-tx-1").isPresent());
    }
}
~~~

This works effectively when database operations participate in the same test-managed transaction. It does not automatically roll back:

- HTTP requests sent to another service.
- Messages already published to a broker.
- Transactions running on another thread.
- Independent transactions already committed.
- Files written to the filesystem or object storage.

An important example is a test running a real server handling HTTP requests. Requests are processed on server threads and do not automatically join the test thread's transaction. Therefore, you cannot assume **@Transactional** on a test method will roll back data written by those requests.

### Using unique identifiers per test

When multiple tests share a database or schema, generate unique identifiers to avoid collisions:

~~~java
String testRunId = UUID.randomUUID().toString();
String customerId = "customer-" + testRunId;
String orderId = "order-" + testRunId;
~~~

Unique IDs reduce conflicts during parallel execution. If data needs cleanup, record the IDs or namespaces the test created so deletion stays properly scoped.

Do not directly assert a pre-known random UUID. Check business attributes or verify results using the exact ID generated during Arrange.

### Scoped cleanup

If data is committed or lives outside a transaction, the test must clean it up after completion:

- Delete only the records created by the test.
- Use dedicated schemas/databases per suite or worker.
- Use dedicated containers when infrastructure isolation is needed.
- Purge messages or reset broker state using test-oriented mechanisms.
- Stop servers, containers, and resources created during the test.

Cleanup should remain safe even if a test fails midway. Use teardown hooks or appropriate lifecycle mechanisms so cleanup runs even when assertions fail.

### Avoiding shared mutable data

Static fixtures can be re-read per test, but do not share a mutable object and mutate it across multiple tests. If one test modifies a list or entity, other tests may observe altered state.

Create fresh objects per test or use factories that return independent copies.

## 10. Isolating Databases and Backing Services

A test requiring a real database should use a database dedicated to testing. You can use an in-memory database for simple queries, or a container of the exact database engine when verifying specific SQL and behavior.

With Testcontainers, you can launch PostgreSQL for integration tests and register dynamic connection properties:

~~~java
@Testcontainers
@SpringBootTest
@ActiveProfiles("integration")
class OrderDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Testcontainers requires appropriate dependencies on the test runtime classpath. This example uses Spring Boot to load application configuration; with plain Spring Framework TestContext, you can combine **@ContextConfiguration** with **@DynamicPropertySource** to register datasource properties into `Environment`.

Do not hardcode container ports because host ports may be mapped dynamically. Use the JDBC URL and credential methods provided by the container.

For brokers or other backing services, apply the same principle: start a dedicated test instance, register dynamic endpoints, and ensure lifecycle management. If a test only needs to verify how a service reacts to dependency outcomes, stubs/fakes may be more suitable than starting full infrastructure.

## 11. Time, Randomness, and Locale Data Also Need Control

Test data is not just database records. Current time, randomness, timezones, locales, and collection ordering can also make results vary.

### Fixing time with Clock

Do not let business logic call **Instant.now()** or **LocalDate.now()** directly if tests require deterministic results. Inject a `Clock`:

~~~java
@Configuration
class TimeTestConfig {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-07-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

In production, you can use **Clock.systemUTC()**. In tests, a fixed clock helps verify expiration dates, order creation timestamps, or term calculation rules without depending on when tests run.

### Controlling randomness

If a test needs random numbers, inject a seedable random source or use an implementation returning predetermined results. Never let a test depend on a lucky random draw.

If the goal is checking ID uniqueness, you can use UUIDs and assert format or distinctness within the same scenario, rather than expecting a fixed value.

### Controlling timezone and locale

Dates and times can differ when local machines and CI use different timezones. Use `Instant` or `LocalDate` with an explicit `Clock`, specify `ZoneId` when converting, and avoid relying on the machine's default timezone.

If tests format numbers, currencies, or dates by locale, pass an explicit locale instead of using the JVM's default locale.

## 12. Organizing Configuration and Test Data Directories

A clean structure can look like this:

~~~text
src/
  main/
    java/
    resources/
      application.yml
  test/
    java/
      .../
        config/
          TestProfileConfig.java
        support/
          OrderTestData.java
        .../
          OrderServiceTest.java
          OrderIntegrationTest.java
    resources/
      application-test.yml
      test-config/
        order-test.properties
      fixtures/
        order-valid.json
        orders.csv
      sql/
        orders-before-test.sql
        cleanup-orders.sql
~~~

In this structure:

- **application-test.yml** holds non-sensitive configuration for Spring Boot tests.
- **test-config** holds property files for tests using Spring TestContext.
- **fixtures** holds reusable JSON/CSV data.
- **sql** holds scripts for creating or cleaning up database data.
- **support** holds factories, builders, and data-creation helpers.
- **config** holds Spring configurations dedicated to tests.

Real secrets must not live inside these directories. If local runs need a separate secret file, place it outside the repository and add its path to **.gitignore** if inside the workspace. Better yet, use environment variables or a secret manager to avoid accidentally committing secret files to Git.

For example, **.gitignore** can include patterns for local files:

~~~gitignore
.env
.env.*
!.env.example
application-local-secrets.yml
test-secrets.properties
~~~

An **.env.example** file should contain only variable names and placeholder values, never real credentials.

## 13. Running the Same Test Suite Locally and in CI

A good test suite should produce consistent results between developer machines and pipelines. To achieve that, standardize how profiles are activated, properties supplied, databases prepared, and fixtures loaded.

Example:

| Component | Local | CI |
|---|---|---|
| Unit profile | `test` | `test` |
| Integration profile | `integration` | `integration` |
| Integration database | Local container | Container on runner |
| Sandbox API key | Environment variable if needed by test | CI secret store |
| Fixtures | In test resources | Same fixtures in repository |
| Database data | Created fresh per test | Created fresh per job or suite |
| Logs | Do not print secrets | Redact credentials and sensitive headers |

A pipeline can be split into two groups:

1. **Unit and slice tests** run fast and need no external credentials.
2. **Integration tests** launch test databases/brokers, receive sandbox credentials only if truly required, and clean up resources afterward.

Avoid making the entire suite depend on a sandbox API that may experience downtime. When contract verification against an external service is needed, isolate that test group and manage timeouts, retries, credentials, and execution conditions explicitly.

## 14. Avoiding Common Security and Stability Mistakes

### Committing credentials to the repository

An API key in a test file is still a secret. Removing it in a new commit does not erase the old credential from Git history. If a real credential was committed, revoke or rotate it per the provider's process and inspect related logs/artifacts.

### Using the production database for tests

A test can delete or update real data if an endpoint or JDBC URL is misconfigured. Use separate databases, users, schemas, and least privilege. When possible, block network connections from standard test suites to the production network.

### Sharing the same mutable data across all tests

One test modifying an entity or collection can affect other tests. Create fresh data for each test and avoid static mutable fixtures.

### Relying on execution order

Test A should not create data for Test B to consume. Each test must prepare its own required state and clean up what it owns.

### Using @DirtiesContext alone to clean up data

**@DirtiesContext** manages the `ApplicationContext` cache. It does not delete committed records, retract messages, remove files, or reset external services.

### Including secrets in error messages

Do not concatenate API keys or passwords into exceptions, assertion messages, or debug logs. When configuration is missing, report only the property name or environment variable that must be supplied.

### Treating the test profile as a security guarantee

A profile can be activated by mistake or a property can be overridden. Use dedicated test endpoints, least-privilege credentials, and network controls. Do not rely on profile names to prevent production access.

### Fixtures containing real personal data

Use synthetic or properly anonymized data. Do not bring production dumps into test resources just to get rich data.

## 15. Workflow for Setting Up a Reproducible Test Suite

When creating tests for a new module, follow this sequence:

1. **Choose the test scope**: unit, slice, or integration.
2. **Select profiles**: identify which bean groups and configurations need activation.
3. **Declare non-sensitive properties**: local URLs, timeouts, schema names, feature flags, and mock modes.
4. **Identify required secrets**: prefer needing no secrets for unit tests; if integration tests need credentials, obtain them from a secret store or environment variables.
5. **Create test data**: use builders, factories, fixtures, or SQL scripts.
6. **Isolate state**: transaction rollback, unique IDs, dedicated databases/schemas/containers, or scoped cleanup.
7. **Control non-deterministic sources**: `Clock`, randomness, locale, timezone, and external endpoints.
8. **Run consistently in CI**: ensure the same profile activation and properties, while keeping credentials out of logs.
9. **Clean up resources**: close contexts when needed, stop containers, delete committed data, and release temporary resources.

An `OrderService` test can use the **test** profile, a fake repository, a fake payment gateway, a fixed `Clock`, and synthetic fixtures. It needs neither real API keys nor a database. A separate integration test can use the **integration** profile, a PostgreSQL container, and separately provisioned sandbox credentials if HTTP adapter verification is needed.

## 16. Combined Example: Isolated Test Configuration

Non-sensitive test configuration:

~~~properties
orders.currency=VND
orders.shipping.fee=30000
payment.mode=fake
payment.timeout=2s
~~~

Test configuration:

~~~java
@Configuration
@Profile("test")
class OrderTestConfiguration {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-07-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    OrderService orderService(
            OrderRepository repository,
            PaymentGateway paymentGateway,
            Clock clock) {
        return new OrderService(repository, paymentGateway, clock);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(
    locations = "classpath:test-config/order-test.properties"
)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderWithTestDependencies() {
        Order order = orderService.create(OrderTestData.validOrderCommand());

        assertEquals("customer-test-7", order.customerId());
        assertEquals(
                Instant.parse("2026-07-01T09:00:00Z"),
                order.createdAt()
        );
    }
}
~~~

In this example, the profile selects test configuration, the property file holds non-sensitive values, the fake repository and fake payment gateway replace external dependencies, and the fixed `Clock` makes time-based outcomes predictable. Input data comes from a factory in test code.

If an integration test needs to connect to a sandbox, use a separate profile and configuration, retrieve API keys from CI-provided environment variables, and grant only the permissions needed for testing. Do not place credentials inside committed fixture files or property files.

## 17. Principles to Maintain When Separating Secrets, Environment, and Data

- Profiles decide which configuration groups or beans are activated; profiles are not secret stores.
- Property sources supply configuration values; avoid defining the same key across multiple sources without a clear reason.
- Secrets must come from secure sources, be least-privileged, never be committed, and never be logged.
- Test data should be synthetic, compact, meaningful, and created per scenario.
- Fixtures contain data only, never real credentials.
- Transaction rollback protects only operations inside that transaction.
- Committed data and external side effects require separate cleanup.
- Tests must be independent of execution order, timezone, system time, and leftover state.
- CI must be able to reproduce the environment without depending on secret files on a developer's machine.

Separating these three groups lets every test suite run in the right environment, with sufficient data, and without excessive access privileges. When a test only needs to verify logic, use the `test` profile with fakes and synthetic fixtures. When integration verification is needed, provision dedicated test resources and least-privilege credentials. As a result, test outcomes are reproducible locally and in CI without mixing configuration, secrets, or data with production environments.

