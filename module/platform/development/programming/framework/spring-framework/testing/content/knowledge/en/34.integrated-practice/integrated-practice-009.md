# Running the Full Suite Order-Independently and Aggregating Evidence

A reliable Spring test suite must run from start to finish without developers guessing test ordering, manually rerunning a few classes, or relying on leftover data from an earlier run. Every test must prepare its own preconditions, verify a meaningful behavior, and clean up the resources it owns. When the entire suite runs on CI, the results must be aggregated into sufficient evidence showing which tests ran, which tests failed, which environment was used, and in which step a failure occurred.

Two goals go hand in hand:

- **Order independence:** the outcome of one test does not depend on whether another test ran before it.
- **Evidence aggregation:** a full suite run must preserve results, logs, and environment metadata so the team can evaluate quality and investigate failures.

Running the entire suite once and seeing green is not enough to prove these two goals. You need ways to verify ordering, isolate data, manage shared state, and retain traceable outputs.

## 1. What Does Order Independence Mean?

A test is order-independent when it produces the same right result whether run before, after, or interleaved with other tests in the same suite. The test must establish its own required preconditions and not depend on side effects produced by another test.

For example, a repository test needs to verify finding a customer by email. The test should create the target customer using its own fixture, call the repository, and assert the result. It must not assume another test ran beforehand to insert that customer into the database.

Order-dependent tests typically exhibit these symptoms:

- Passes when run alone, fails when run as part of the full suite.
- Passes when class A runs before class B, fails when the order is reversed.
- Running a second time in the same workspace differs from the first run because stale data remains.
- Test relies on a static field, mutable singleton bean, or system property set by another test.
- Test uses `@Order` or `@TestMethodOrder` merely to mask shared state.
- Outcomes depend on auto-generated IDs, current wall-clock time, record order, or uncontrolled seed data.

JUnit can order tests deterministically, yet that ordering should never become an implicit part of the test contract. A good test suite yields the same outcome even when execution order changes.

### Distinguishing a Workflow from Order Dependency

If business logic genuinely consists of multiple ordered steps, test them within a single test scenario or an explicitly controlled test fixture. For example, creating an order and then paying for it is a workflow; a workflow test can invoke both operations sequentially inside the same test.

Do not write `createOrderTest()` so another test relies on the data it created, followed by `payOrderTest()` assuming the previous test already ran. A test method is an independent verification unit, not a step in a scenario sharing hidden state.

## 2. Designing Each Test to Prepare Its Own Data

The fundamental principle is Arrange–Act–Assert:

1. **Arrange:** create the data and configuration the test needs.
2. **Act:** perform an action on the application.
3. **Assert:** verify the observable outcome.

Repository example:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer customer = repository.saveAndFlush(
                new Customer("customer-a@example.test"));

        Optional<Customer> result =
                repository.findByEmail("customer-a@example.test");

        assertThat(result)
                .isPresent()
                .get()
                .extracting(Customer::getId)
                .isEqualTo(customer.getId());
    }
}
```

The test creates the record it needs. It does not require another test to seed data. `saveAndFlush` also forces SQL to execute before the query when the test needs to check real persistence.

For service or controller tests, create dedicated mocks/fakes per test method or use well-scoped dependency injection. Do not share a mutable mock across concurrent tests if they simultaneously alter expectations or verify state.

### Using Fixture Builders Instead of Hidden Data

When an entity has many properties, a builder or factory keeps data creation clear:

```java
final class CustomerFixtures {

    private CustomerFixtures() {
    }

    static Customer customer(String email) {
        return new Customer(email, "Lan", true);
    }
}
```

Test:

```java
@Test
void filtersActiveCustomers() {
    repository.saveAndFlush(
            CustomerFixtures.customer("active@example.test"));

    List<Customer> result = repository.findByActiveTrue();

    assertThat(result)
            .extracting(Customer::getEmail)
            .contains("active@example.test");
}
```

Fixtures should construct objects with valid, intuitive defaults. Properties directly tied to the behavior under test should be passed explicitly so readers know which condition is being verified.

### Avoiding Shared Fixed Data Across Multiple Tests

A hardcoded email or order code can collide when two tests run in parallel or when data remains from a previous run. You can generate a unique key per test:

```java
String email = "customer-" + UUID.randomUUID() + "@example.test";
```

When reproducing a failure, record the value or seed used. Randomized data is only helpful when the test can reproduce the exact same inputs from the failure evidence.

## 3. Managing Cleanup and Test-Owned Resources

Tests should clean up only the resources they created. Wiping an entire database or deleting shared files can break other tests running concurrently.

Cleanup examples:

- Database: delete records by ID or the test's unique business key.
- Files: create an isolated temporary directory and remove it after the test.
- Mock HTTP server: reset stubs and request journal after each test if the server is shared.
- Executor: stop executors created by the test and wait for workers to finish.
- Containers: let Testcontainers' lifecycle manage the appropriate suite or test scope.
- System properties/locale/timezone: save old values, restore in `finally`, and lock the resource when needed.

Example using JUnit's temporary directory:

```java
class FileExportServiceTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void writesExportFile() throws IOException {
        Path output = temporaryDirectory.resolve("orders.csv");

        new FileExportService().export(output);

        assertThat(output).exists();
        assertThat(Files.readString(output)).contains("orderId");
    }
}
```

`@TempDir` provisions an isolated directory for the test and manages cleanup. The test does not need a shared fixed path in the workspace.

For databases, test-managed transaction rollback is useful, yet it does not cover independent transactions, other threads, or requests hitting an embedded server. If a test commits data or produces out-of-transaction side effects, clean up explicitly after the operation completes.

## 4. Avoiding Shared State and Order Dependencies

Common sources of shared state often cause hard-to-reproduce bugs:

| State Source | Risk | How to Isolate |
|---|---|---|
| `static` mutable field | Earlier test mutates value seen by later test | Avoid mutable static; reset under control |
| Singleton Spring bean with mutable fields | Multiple tests/requests mutate the same object | Design statelessly or use appropriate scope/context |
| System properties | Affects the entire JVM | Save and restore; use `@ResourceLock` |
| Default locale/timezone | Parsing/formatting differs across environments | Configure explicitly or lock when mutating global defaults |
| Shared database records | Tests read/delete/update another test's data | Isolated data, unique IDs, ownership-based cleanup |
| Fixed files or ports | Collisions during parallel runs | Temp directories and dynamic ports |
| Mock server or broker | Stubs/requests/events leak between tests | Reset or use dedicated instances |
| Spring context cache | Singleton or context gets mutated | Do not mutate shared state; use `@DirtiesContext` only when truly needed |

### JUnit Method Ordering Is Not a Fix for Dependent Tests

JUnit Jupiter supports `@TestMethodOrder` and `@Order` for sorting methods when there is a clear need. For example, a test group might need an order for demonstration purposes or a specialized extension. However, using ordering so one test method creates data for another makes tests hard to run individually, hard to parallelize, and brittle when the suite changes.

If a scenario requires multiple steps, put those steps inside the same test:

```java
@Test
void createsAndPaysOrder() {
    Order order = orderService.createOrder(command);
    Payment payment = paymentService.pay(order.getId());

    assertThat(payment.getOrderId()).isEqualTo(order.getId());
    assertThat(payment.getStatus()).isEqualTo(PaymentStatus.APPROVED);
}
```

The test can still call multiple components, yet the data and sequence belong to a single scenario rather than depending on another method.

## 5. Verifying Independence with Random Ordering

Running the suite in random order is a proactive way to uncover order dependencies. If tests only pass when run in a familiar order, changing the order can expose leaked state.

JUnit Jupiter supports random orderers for test methods and test classes. You can configure this in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testmethod.order.default = org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default = org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed = 20261113
```

These properties require JUnit Jupiter's random orderer support. A fixed seed makes the exact ordering reproducible across subsequent runs. When trying a different order, change the seed and record the seed used.

You can also place the orderer directly on a class:

```java
@TestMethodOrder(MethodOrderer.Random.class)
class CustomerServiceTest {

    @Test
    void createsCustomer() {
        // Independent test.
    }

    @Test
    void rejectsInvalidEmail() {
        // Independent test.
    }
}
```

Random ordering is not the same as parallel execution. JUnit can run tests in a random order yet still sequentially. This separates two investigation variables:

- Random ordering checks order dependencies.
- Parallel execution checks contention when multiple tests run simultaneously.

Test each mode separately first, then combine them if needed.

### Saving the Seed and Order on Failure

When random ordering causes a test failure, save the seed, test class/method, and execution logs. Rerun with the same seed to reproduce; then run a smaller subset of tests to locate the interfering test.

Do not keep changing the seed until the suite passes and conclude the bug is gone. What you need to find is which state was created or modified by an earlier test, and why the later test depended on it.

## 6. Running Sequentially and in Parallel as Two Separate Checks

Order independence and parallel-execution safety are two related yet distinct properties.

| Execution Mode | Best at Detecting |
|---|---|
| Random order, sequential | Tests depending on state left behind by an earlier test |
| Fixed order, parallel | Race conditions and resource contention |
| Random order, parallel | Combined order dependencies and concurrent contention |
| Running each test individually | Bugs inside the test itself or its direct dependencies |

JUnit Jupiter can enable parallel execution with:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
```

This configuration allows test classes to run concurrently while keeping methods within each class sequential under the default mode. This can be a cautious starting point for Spring integration tests. Ensure the database, connection pool, containers, and shared resources can handle the load.

If a test mutates a system property or global resource, use `@ResourceLock` with the same resource key across all conflicting tests. If a test is not parallel-safe, mark it `@Execution(SAME_THREAD)` or isolate it into a sequential group while fixing the root cause.

## 7. Isolating the Spring ApplicationContext

The Spring TestContext Framework caches `ApplicationContext` across tests with matching configurations to reduce startup time. A cached context may hold singleton beans, datasources, executors, caches, or mock servers. Therefore, a test must not mutate shared bean state and expect a fresh context to be built for the next test.

Some key principles:

- Keep services and controllers stateless whenever possible.
- Never store test-specific data in singleton fields.
- Reset stateful caches or collaborators if doing so is the test's responsibility.
- Use explicit profiles/configuration to avoid depending on developer environments.
- Use `@DirtiesContext` only when a test genuinely renders the context unusable, not as a blanket cleanup for every data bug.
- Do not close context-owned resources inside one test if other tests still use that context.

`@DirtiesContext` marks the context to be evicted from the cache and closed according to its scope. It does not delete committed database rows, reset external services, or fix race conditions in static state.

### Test Slices and Full Context

Test slices such as `@WebMvcTest` or `@DataJpaTest` reduce the number of beans and resources initialized. `@SpringBootTest` tests broader configuration but is usually heavier. Regardless of type, tests must remain independent with respect to data and side effects.

Do not use a full context merely to share a common dataset across multiple tests. Have each test create the data it needs or use fixtures with explicitly managed lifecycles.

## 8. Organizing Database Data so the Full Suite Is Repeatable

A database integration test suite should be able to run repeatedly on a fresh database or a cleaned-up database without depending on IDs or test order.

Helpful practices:

- Create data inside tests using repositories, `TestEntityManager`, SQL scripts, or intentional fixtures.
- Use a unique business key per test when the database is shared.
- Do not assume auto-generated IDs start at a specific value or stay contiguous after rollbacks.
- Do not rely on query result ordering unless the query includes `ORDER BY`.
- Flush when SQL and constraints need to be verified.
- Clearly distinguish test transactions, independent transactions, and operations running on other threads.
- Clean up by test-owned keys rather than deleting whole shared tables.
- If a test requires special database state, use a separate schema/database or a dedicated container per suite.

Example using `@Sql` to prepare data for a test:

```java
@Test
@Sql(scripts = "/sql/customer-test-data.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/cleanup-customer-test-data.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void findsSeededCustomer() {
    assertThat(repository.findByEmail("seeded@example.test")).isPresent();
}
```

Scripts should scope data with test-specific keys and be safe to rerun if the suite is re-executed. If multiple tests share a script with identical data and run in parallel, they can still collide; in that case, use isolated data or separate schemas.

## 9. Controlling Time, Randomness, and OS Resources

To keep tests consistent across developer machines and CI:

- Inject `Clock` rather than calling `Instant.now()` or `LocalDate.now()` directly inside logic under test.
- Use explicit timezones and locales.
- Fix random seeds or log the seed when failures occur.
- Use `@TempDir` instead of fixed file paths.
- Use dynamic ports for embedded servers and mock servers.
- Use readiness checks or completion conditions instead of `Thread.sleep`.
- Set timeouts wide enough for CI yet finite so tests never hang indefinitely.
- Clean up executors, sockets, file handles, and containers created by the test.

Example with `Clock`:

```java
@Test
void expiresAtExpectedInstant() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);
    ExpirationService service = new ExpirationService(clock);

    assertThat(service.isExpired(
            Instant.parse("2025-12-31T23:59:59Z"))).isTrue();
}
```

The test does not depend on when it actually runs. This keeps results consistent when CI runs on a different day or in a different timezone.

## 10. Running the Entire Test Suite with the Build Tool

Once tests are independent, run the entire suite in the exact lifecycle used by the project.

### Gradle

Run the test task:

```bash
./gradlew test
```

Run standard verification tasks:

```bash
./gradlew check
```

`check` normally depends on `test` and other verification tasks attached to the lifecycle by the project. If the project defines a separate integration test task, verify that it is wired into `check` or invoke it explicitly.

Example of a separate integration test task:

```groovy
tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'
    useJUnitPlatform()
    shouldRunAfter(tasks.test)
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    filter {
        includeTestsMatching '*IntegrationTest'
    }
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

This is an illustrative configuration; projects should use a separate source set for integration tests when dependencies, resources, and reports need separation. Avoid accidentally running the same test twice in both `test` and `integrationTest` due to unclear filters or source sets.

Gradle normally stores XML results in `build/test-results/test` and HTML reports in `build/reports/tests/test`. For custom tasks, report directories typically match the task name. You can configure test logging to print failures and summaries to the console, while keeping XML reports as machine-readable artifacts.

### Maven

Run the test phase:

```bash
./mvnw test
```

Run through the verify phase:

```bash
./mvnw verify
```

Surefire normally runs unit tests in the `test` phase. Failsafe normally runs integration tests across the `integration-test` and `verify` phases when configured. The `verify` phase lets the plugin check integration test outcomes after tests finish running.

Surefire results typically reside in `target/surefire-reports`; Failsafe results typically reside in `target/failsafe-reports`. Keep both XML reports and console logs so CI can aggregate test counts, failures, errors, and skipped tests.

### Rerunning a Single Test to Investigate Does Not Replace the Full Suite

Targeted commands are useful for isolating issues:

```bash
./gradlew test --tests "com.example.orders.OrderIntegrationTest"
```

```bash
./mvnw -Dtest=OrderIntegrationTest test
```

After fixing an issue, you still need to rerun the full suite and CI lifecycle. A single test passing in isolation does not prove it is independent of other tests.

## 11. Aggregating Evidence from JUnit and the Build Tool

A full suite run should produce at least two types of output:

1. **Machine-readable reports:** JUnit XML or equivalent reports so CI can aggregate test counts, pass/fail/error/skipped totals, and link to failing tests.
2. **Human-readable reports:** HTML reports, console logs, stack traces, and diagnostic artifacts so developers understand the failure context.

Information to aggregate:

| Evidence Group | Contents |
|---|---|
| Build identification | Commit SHA, branch, build number, execution timestamp |
| Environment | JDK, OS, CPU/RAM, timezone, locale |
| Versions | Spring Boot, Spring Framework, JUnit, Gradle/Maven, database/container images |
| Test configuration | Active profiles, key properties, parallel mode, random seed |
| Results | Total tests, passed, failures, errors, skipped, duration |
| Failures | Test class/method, assertion, stack trace, suppressed exceptions |
| External dependencies | Database/container/service versions, readiness, and relevant logs |
| Retry/flaky | Passed or failed on first attempt, retry count, final status |

Not every value needs to be logged by every test. You can write a build-level metadata file and link it alongside XML/HTML reports to avoid repeating information.

### JUnit XML and HTML Reports

JUnit XML lets CI identify test cases, durations, and failure messages. HTML reports are convenient for browsing test classes and stack traces. Console logs are useful for seeing execution order, Spring startup logs, container readiness, and details omitted from XML.

Do not save only a summary like "1 test failed". Retain detailed reports from failed runs and full associated logs. When a CI job fails, artifacts must still be uploaded for developers to download.

## 12. Recording Run Metadata

You can generate a metadata file before running tests to attach environment details to the report:

```json
{
  "commit": "<git-sha>",
  "javaVersion": "<java-version>",
  "os": "<operating-system>",
  "timezone": "UTC",
  "springProfile": "test",
  "parallelExecution": false,
  "randomOrderSeed": 20261113,
  "databaseImage": "postgres:<pinned-version>"
}
```

The values in the example are placeholders or illustrative settings. CI should record actual build values rather than copying placeholder strings. If random ordering or database containers are not used, record the corresponding configuration explicitly rather than omitting them ambiguously.

Environment details can be collected from the build script or pipeline and stored next to test reports. Avoid writing passwords, tokens, connection strings with secrets, or personal data into artifacts. Only store information needed to reproduce failures.

### Attaching Identifiers to Logs

When multiple tests run concurrently, request logs can interleave. Including a correlation ID or test-specific identifier in request data and logs helps tie a test to server operations. Do not rely on log line ordering to infer test ordering when parallel execution is enabled.

With Spring Boot, you can configure the logging pattern to print the thread name and correlation ID if the application already uses MDC. Clear MDC after each request/test so values do not leak into reused threads.

## 13. Automatically Collecting Evidence When Tests Fail

JUnit Jupiter provides extension callbacks such as `TestWatcher` to record test outcomes. Simple example:

```java
class FailureRecordingExtension implements TestWatcher {

    @Override
    public void testFailed(ExtensionContext context, Throwable cause) {
        String testName = context.getDisplayName();
        System.err.println("FAILED TEST: " + testName);
        cause.printStackTrace(System.err);
    }
}
```

Registering the extension:

```java
@ExtendWith(FailureRecordingExtension.class)
class CustomerServiceTest {
    // Tests.
}
```

This is only a minimal logging example. In CI systems, it is usually best to let JUnit XML and the test runner manage official results, while extensions only supplement metadata or capture specialized state. If an extension writes files, generate safe, unique filenames per test under parallel execution; never let multiple threads overwrite the same file.

`TestWatcher` does not replace JUnit reports and must not swallow test exceptions. A failing test must still be reported as failed by the test engine.

### Collecting Logs and Service State

For integration tests using Testcontainers or mock servers, you can save container logs and readiness status when the suite fails. Tag artifacts with the container/service name and related test class. Collect logs before the container is stopped or removed; if the lifecycle shuts the container down too early, logs may be lost.

For the Spring application context, startup logs can point out which bean failed to initialize. For databases, server logs and SQL can reveal deadlocks, timeouts, constraint violations, or connection exhaustion. Collecting the right sources reduces guesswork.

## 14. Configuring CI So Reports Are Not Lost on Test Failure

CI should run the full suite and always upload reports, even when the test step exits with a non-zero code. General pipeline example:

```text
Checkout source
      |
      v
Record commit and environment metadata
      |
      v
Compile and run unit tests
      |
      v
Run integration tests
      |
      v
Collect JUnit XML, HTML and service logs
      |
      v
Publish test report artifacts (also when tests fail)
      |
      v
Fail build if required tests failed
```

Report upload should be configured with `always` or `if: always()` depending on your CI provider. Never restrict uploads to successful jobs, because the most valuable artifacts usually come from failed runs.

Illustrative YAML example:

```yaml
- name: Run tests
  run: ./gradlew check

- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: spring-test-reports
    path: |
      **/build/test-results/**
      **/build/reports/tests/**
```

Paths and syntax must be adjusted to your actual Gradle project layout and CI provider. For Maven, add `target/surefire-reports/**` and `target/failsafe-reports/**`. In multi-module projects, collect reports from every module.

### Do Not Turn Retries into False Green Results

If CI uses retries, retain the first-attempt result and mark tests that pass only after retry as flaky. Aggregated reports should distinguish:

- Passed on first attempt.
- Failed initially, passed after retry.
- Failed after exhausting retries.
- Skipped or quarantined.

A suite is only trustworthy when flaky rates are tracked and owned for resolution. Do not erase initial stack traces or report only the final status as passed.

## 15. Creating an Evidence Matrix for the Entire Suite

A format helpful for quick reviews is a matrix grouped by test category:

| Group | Scope | Required Reports | Additional Evidence |
|---|---|---|---|
| Unit | Pure Java logic | JUnit XML, duration | Seed if randomized, failure logs |
| MVC slice | Controllers and Spring MVC | JUnit XML, HTML | Request/response, active profile |
| JPA slice | Repositories and persistence | JUnit XML, SQL/failure logs when needed | Database version, transaction/cleanup |
| Integration | Multiple application layers | JUnit XML, HTML | Spring context logs, dependency versions |
| HTTP server | Embedded server and network path | JUnit XML | Port, server logs, request correlation ID |
| Native/AOT | Generated context or native executable | Build/test reports | GraalVM version, AOT artifacts, runtime hints |

The matrix tells the team what evidence is needed for each test type. You do not need SQL tracing or debug logs enabled for every test; collect deeper diagnostics only when a test category or failure calls for it.

## 16. Process for Running the Full Suite Independently and Traceably

A practical workflow for a Spring project:

1. **Prepare environment:** check out a clean commit, use pinned JDK and dependency versions, and explicitly configure test profiles, database/containers, and timezone.
2. **Run individual tests when investigating:** confirm a test has no deterministic failures within its immediate scope.
3. **Run the whole class and related groups:** detect state leaking across methods or classes.
4. **Test with random ordering:** record the seed to uncover order dependencies and reproduce failures.
5. **Test in parallel:** separate from random ordering to detect race conditions and resource contention.
6. **Run the full lifecycle:** use `./gradlew check` or `./mvnw verify` according to your project build, including configured integration tests.
7. **Collect reports:** save JUnit XML, HTML, console logs, environment metadata, and relevant service logs.
8. **Aggregate results:** distinguish passes, failures, errors, skipped tests, flaky-after-retry tests, and quarantined tests.
9. **Preserve evidence on failure:** CI still uploads reports even if the test task fails.
10. **Fix root causes:** isolate data, synchronize async work, eliminate shared state, or fix environment configuration; then rerun the full suite under the same conditions.

## 17. Suite Completion Criteria

A test suite can be considered CI-ready when:

- It runs from a clean checkout using the documented project build command.
- No test requires another test to run beforehand to create data or configuration.
- Individual tests or classes can be run alone for investigation.
- Random ordering does not change functional outcomes.
- Parallel execution is enabled within a defined scope without uncontrolled race conditions.
- Data and resources are created, managed, and cleaned up by ownership.
- Tests do not depend on wall-clock time, timezone, locale, or non-contractual collection ordering.
- Transactions, async tasks, and server requests have clear boundaries.
- CI retains machine-readable reports and logs sufficient to trace failures.
- Retries or quarantines, if any, are documented and have an owner.

## 18. Conclusion

Running the full suite order-independently starts with each test preparing its own data, sharing no mutable state, and cleaning up the resources it created. Use random ordering to find order dependencies, use parallel execution to find concurrent contention, and verify the full lifecycle after fixes.

Aggregating evidence means preserving JUnit XML/HTML, stack traces, service logs, and environment metadata even when CI fails. Combining test independence with traceable reporting turns a Spring test suite into a reliable signal for software changes: failures are reproducible, blast radius can be localized, and full-suite results can be reviewed from a single run.
