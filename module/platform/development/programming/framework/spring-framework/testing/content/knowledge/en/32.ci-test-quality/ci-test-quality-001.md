# Separating Fast Tests from Infrastructure-Dependent Tests

A Spring test suite typically contains many kinds of tests with different costs and environment requirements. Some tests only call a Java method and finish in a few milliseconds; others need to create an `ApplicationContext`, start PostgreSQL, connect to Kafka, or wait for a consumer to process a message. If every test is run the same way on every build, the development team will wait a long time even when changing only a small business rule.

Separating fast tests from infrastructure-dependent tests keeps feedback fast in the development loop while still running valuable integration tests. Separation should be based on the dependency scope and environment a test requires, and then reflected clearly in JUnit tags, Gradle/Maven tasks, and CI stages.

The goal is not to make slow tests disappear from the pipeline. The goal is to know which tests can run immediately, which tests require external services, when each group must run, and who is responsible for ensuring infrastructure readiness.

## 1. Categorize by Scope and Dependencies

A useful way to categorize tests is to look at what a test actually needs to prove its contract.

| Group | Typical scope | Required infrastructure | Execution characteristics |
|---|---|---|---|
| Unit test | A single class or a business rule | No Spring context or external services needed | Very fast, run frequently |
| Spring slice test | An MVC, JPA, JSON, or security slice | Spring test context; may use fakes/mocks or an embedded DB | Fast to moderate |
| Integration test | Multiple beans or an integration boundary | Real database, broker, cache, or service | Takes time for startup and cleanup |
| End-to-end test | Flow across multiple components or a running server | A near-production application and infrastructure stack | Slower, requires a stable environment |

Examples:

- `PriceCalculatorTest` tests pure Java price calculation: unit test.
- `OrderControllerWebTest` uses `@WebMvcTest` to verify binding, validation, and responses: Spring slice test.
- `OrderRepositoryIT` runs queries against PostgreSQL Testcontainers: integration test.
- `OrderFlowIT` starts the application along with a database/broker and sends HTTP requests through a real server: end-to-end or full integration test, depending on scope.

You should not rely solely on annotation names to decide whether a test is fast or slow. `@SpringBootTest` might not use containers and still take time to create a context; a test with a shared container can run fairly quickly after initial startup. Categorize based on dependencies, actual cost, and the risk the test protects against.

## 2. Define the Boundary Between Fast Tests and Infrastructure Tests

Several questions help determine the group:

1. Does the test require Docker or a service running outside the JVM?
2. Does the test require an exact production engine/protocol such as PostgreSQL, Kafka, or RabbitMQ?
3. Does the test need to open an HTTP port or communicate over a real network?
4. Does the test require migrations, transactions, broker acknowledgements, or asynchronous consumers?
5. If run standalone on a developer machine without background services, can the test work?

If the answer to the infrastructure questions is yes, the test usually belongs in the integration or end-to-end group. If the test only needs Java objects, mocks, or a controlled Spring slice, it usually fits the fast group.

| Scenario | Suggested group | Reason |
|---|---|---|
| Testing a function that changes order status | Fast | No database or Spring dependency |
| Testing that a controller returns `400` on an invalid DTO | Fast/slice | Mock MVC context can verify the HTTP contract without a real server |
| Testing a repository using PostgreSQL JSONB | Infrastructure | Requires the exact database engine |
| Testing Flyway migrations on PostgreSQL | Infrastructure | Requires PostgreSQL schema and catalog |
| Testing publish/consume via RabbitMQ | Infrastructure | Requires a real broker and AMQP protocol |
| Testing TLS, ports, or server connectors | Infrastructure/E2E | Requires HTTP transport or a real server |
| Testing a service calling a gateway interface with Mockito | Fast | Only verifies orchestration logic, not transport |

A test can have multiple tags, for example `integration` and `database`. This allows the pipeline to run all integration tests or only the database group when needed. Tags should describe meaningful attributes rather than recording every implementation detail.

## 3. Keep Unit Tests Small and Independent

Unit tests should run directly against the class under test, with dependencies passed through the constructor. Do not start the entire Spring context if the goal is only to test a calculation or business decision.

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void waivesFeeForLargeOrders() {
        assertThat(calculator.calculate(250_000))
                .isZero();
    }
}

class ShippingFeeCalculator {

    int calculate(int orderTotal) {
        return orderTotal >= 200_000 ? 0 : 25_000;
    }
}
```

This test does not need `@SpringBootTest`, a database, or a container. It can run on any machine with a JDK and test dependencies. When a unit test fails, the scope of possible causes is small so developers can locate the bug quickly.

Mocks should be used at boundaries that need isolation, such as an HTTP gateway or a clock. Do not mock every object in a test; otherwise, the test may only verify how the mocks were configured without checking real behavior.

## 4. Spring Slice Tests Usually Belong to the Fast-Feedback Group

Spring Boot provides test slices to create only the part of the context needed for one layer of work:

| Annotation | Typical scope |
|---|---|
| `@WebMvcTest` | MVC controllers, binding, validation, advice, and related web configuration |
| `@DataJpaTest` | JPA entities, repositories, and persistence configuration |
| `@JsonTest` | JSON serialization/deserialization |
| `@RestClientTest` | Spring REST client components and related converters |
| `@WebFluxTest` | WebFlux controllers and selected reactive web components |

Slice tests start Spring so they are usually slower than pure-JVM unit tests, yet still lighter than starting the full application with all external services. If a slice needs to test against an exact production database, it can move to the integration group by connecting Testcontainers.

MVC slice example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", 999))
                .andExpect(status().isNotFound());
    }
}
```

If the controller needs a service, provide a mock for that dependency. There is no need to start PostgreSQL just to verify response mapping if the test does not need to assert database queries.

## 5. Mark Test Groups with JUnit `@Tag`

JUnit Jupiter provides `@Tag` to label a test class or method. Build tools can use tags to select which test groups to run.

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class OrderRepositoryIT {

    @Test
    void storesOrderInPostgres() {
        // Test requiring a real PostgreSQL instance.
    }
}
```

Multiple tags can be attached:

```java
@Tag("integration")
@Tag("database")
class OrderRepositoryIT {
    // ...
}
```

Or create a custom annotation so the convention is reusable:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Tag;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Tag("integration")
public @interface IntegrationTest {
}
```

Then use it:

```java
@IntegrationTest
class OrderRepositoryIT {
    // ...
}
```

Composed annotations help standardize tagging. If a group needs a more specific tag, you can still add `@Tag("database")` or `@Tag("broker")` alongside that annotation.

You should agree on a short vocabulary, for example:

| Tag | Meaning |
|---|---|
| `integration` | Requires one or more real integrated components |
| `database` | Requires a real database or specific database engine |
| `broker` | Requires a message broker |
| `e2e` | Needs to run across multiple components or a real server |
| `slow` | Has a long execution time according to project convention |

There is no need to tag every unit test with `fast` if the default build already selects all tests except integration/e2e. Use tags for groups that need explicit filtering and maintain a consistent convention.

## 6. Separate Gradle Tasks for Fast Tests and Integration Tests

With Gradle, you can keep all tests in the `test` source set while creating two separate `Test` tasks. The default task excludes infrastructure tags; the `integrationTest` task runs only the `integration` tag.

Example `build.gradle` using the Groovy DSL:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration', 'e2e'
    }
}

tasks.register('integrationTest', Test) {
    description = 'Runs tests that require external infrastructure.'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }

    shouldRunAfter tasks.named('test')
}
```

Result:

| Command | Group executed |
|---|---|
| `./gradlew test` | Unit and slice tests; excludes `integration`, `e2e` |
| `./gradlew integrationTest` | Only tests tagged `integration` |
| `./gradlew test integrationTest` | Runs both tasks |

`shouldRunAfter` only specifies ordering if both tasks are requested together; it does not automatically cause `integrationTest` to run when invoking `test`.

If you want `check` to always include integration tests, you can add a dependency:

```groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Decide this clearly according to your build convention. If a fast-feedback pipeline invokes `check`, attaching integration tests to `check` will make that pipeline run infrastructure as well. Another option is to have CI invoke `test` in the fast stage and `integrationTest` in the stage with Docker.

### When Should You Create a Separate Source Set?

Separating tasks by tag is usually sufficient if tests share the same test dependencies and conventions. A separate source set such as `integrationTest` is useful when integration tests need different dependencies, dedicated test fixtures, separate classpaths or resources, or a separate build lifecycle.

Do not create a separate source set just because tests are a few seconds slower. Extra Gradle configurations complicate the build and increase maintenance effort. Start with tags and separate tasks; only split source sets when there is a genuine classpath need.

## 7. Separate Maven Surefire and Failsafe

In Maven, Surefire typically runs unit tests in the `test` phase. Failsafe is designed to run integration tests in the `integration-test` and `verify` phases, ensuring teardown and result checks happen in the proper lifecycle.

You can use JUnit `@Tag("integration")` and configure the plugins as follows:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
            <configuration>
                <excludedGroups>integration,e2e</excludedGroups>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.5.2</version>
            <configuration>
                <groups>integration</groups>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Surefire excludes integration/e2e tags. Failsafe selects only the integration tag and runs in the integration lifecycle. Name classes according to Failsafe conventions such as `OrderRepositoryIT` or configure `includes` if the project uses another naming pattern.

| Maven command | Outcome |
|---|---|
| `./mvnw test` | Runs unit/slice tests via Surefire |
| `./mvnw verify` | Runs Surefire and integration tests via Failsafe, then performs lifecycle verification |

Do not invoke the `integration-test` goal alone as the final command in a pipeline because Failsafe is designed to aggregate results in the `verify` goal. Use `verify` to ensure integration test failures fail the build properly.

## 8. Tag Testcontainers Tests

A test that uses real PostgreSQL should declare its infrastructure requirements via tags and container lifecycle:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Tag("integration")
@Tag("database")
@SpringBootTest
@Testcontainers
class OrderRepositoryIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void persistsOrderInPostgres() {
        // Call the repository/service and verify real data.
    }
}
```

`@ServiceConnection` requires Spring Boot 3.1 or higher and the `spring-boot-testcontainers` dependency. If using an older Boot version or an unsupported container, configure `spring.datasource.*` using `@DynamicPropertySource`.

This test should not run in the default fast task if developer machines or fast CI do not guarantee a container runtime. However, it must run in the integration stage that has Docker or an equivalent runtime.

With `@DataJpaTest`, pay attention to database replacement configuration. If you want to use a PostgreSQL container instead of an embedded database, you can declare:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
@Tag("integration")
class OrderRepositoryIT {
    // PostgreSQL container and repository assertions.
}
```

`replace = NONE` prevents the test slice from replacing the configured `DataSource` with an embedded database. If `@ServiceConnection` is used, Spring Boot provides the connection details for the PostgreSQL container.

## 9. Choose the Right Spring Context Level

Not every test that needs a real database has to use `@SpringBootTest`. Choose the smallest context that still verifies the contract:

| Need | Suggested setup |
|---|---|
| Testing a repository with PostgreSQL | `@DataJpaTest` + PostgreSQL Testcontainers |
| Testing a controller and database across multiple beans | `@SpringBootTest` or an appropriate slice with a database container |
| Testing RabbitMQ publish/consume | Spring context with `RabbitTemplate`/listener and RabbitMQ container |
| Testing full HTTP server with DB/broker | `@SpringBootTest(webEnvironment = RANDOM_PORT)` with the required containers |
| Testing a pure service with a mocked repository | Unit test, no context needed |

Larger contexts create more beans, run more auto-configuration, and take longer. Use `@SpringBootTest` when you need to verify full-application wiring; use slices when only part of the context is enough to prove behavior.

Spring TestContext can cache contexts between test classes that share the same configuration. This reduces execution time, but the container lifecycle must stay alive long enough for the cached context to be reused. If a container is stopped while the context remains cached, subsequent tests may try to connect to an endpoint that no longer exists.

## 10. Split Stages in CI

A common pipeline can run groups by cost and dependency level:

```text
Pull request
    |
    v
Compile + static checks
    |
    v
Fast tests (unit + slice)
    |
    +------> Fast feedback for developers
    |
    v
Integration tests (database / broker containers)
    |
    v
End-to-end / deployment checks (if needed)
    |
    v
Merge / release
```

Example policy:

| Stage | Test group | Goal |
|---|---|---|
| Every commit or pull request | Unit and slice tests | Catch failures quickly at low cost |
| Pull request before merge | Essential integration tests | Verify database/broker and critical boundaries |
| Post-merge or scheduled | Full integration suite, E2E, long tests | Cover broad flows and complex environments |
| Before release | Release test suite | Confirm the version is deployable |

This is a reference organization. If a change directly affects migrations or broker contracts, the relevant integration tests need to run before merge rather than waiting for nightly runs. Path filters or build matrices can be used to run the appropriate test groups, but every important test must still have a pipeline responsible for executing it.

## 11. Pipeline Example with Gradle

With the tasks declared earlier, the pipeline can invoke two separate steps:

```yaml
jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew test

  integration-tests:
    runs-on: ubuntu-latest
    needs: fast-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew integrationTest
```

The example uses runners with a pre-installed container runtime. Testcontainers creates databases/brokers inside the job. If your runner or organization policy requires custom Docker configuration, declare that configuration according to your CI platform.

Both jobs can run in parallel if they are independent and runners have sufficient capacity. If you only want integration tests to run after fast tests pass, use the `needs` dependency as shown. Choose ordering based on feedback goals and runner cost.

## 12. Pipeline Example with Maven

With Surefire/Failsafe configured:

```yaml
jobs:
  fast-tests:
    steps:
      - run: ./mvnw test

  integration-tests:
    needs: fast-tests
    steps:
      - run: ./mvnw verify
```

`verify` runs the preceding phases, including `test`, followed by Failsafe's integration-test and verify. Therefore, the integration job will also run unit/slice tests unless Surefire is skipped. If you want to avoid re-running fast tests, you can design a dedicated Maven profile/lifecycle, while ensuring Failsafe is still invoked via `verify` and results are aggregated.

Do not use `-DskipTests` broadly to make the integration job run only Failsafe if that flag also causes Failsafe to skip tests. If you need to skip Surefire, use a configuration or property specific to the Surefire plugin, and verify that Failsafe still executes in the lifecycle.

## 13. Avoid Turning Infrastructure Tests into Skipped Tests

One risk of separating tests is that the `integration` tag gets dropped from every pipeline because the Docker-enabled job is unconfigured or too slow. This creates the illusion of a green build while no longer verifying critical boundaries.

Define clearly:

- Which job runs each tag.
- Which job requires Docker or service containers.
- When the runtime is unavailable, the build must fail with a clear configuration error.
- Which tests are allowed to run nightly and which are mandatory before merge.
- Who is responsible for monitoring integration test failures and flakiness.

Do not use assumptions or `disabledWithoutDocker` to silently skip integration tests in mandatory CI. If local developers lack the runtime, provide a separate fast task so they still get quick feedback; the CI integration job requires the runtime and must execute the tests.

## 14. Isolate Data and Avoid Inter-Test Dependencies

Splitting tasks does not automatically make data clean. Multiple integration tests may share a single PostgreSQL container or Kafka broker. If tests rely on data from a previous test, results will depend on execution order or parallelism.

Common isolation approaches:

| Approach | Benefit | Caveat |
|---|---|---|
| Dedicated container per class or method | Clean infrastructure per lifecycle | Startup can be slow |
| Separate schema/database | Data isolation on the same server | Needs schema creation and cleanup management |
| Transaction rollback | Cleans up rows after a test | Does not cover async work or separate transactions |
| Dedicated queue/topic | Prevents reading messages from other tests | Needs topology cleanup or unique names |
| Data with unique keys | Reduces collisions during parallel execution | Still needs cleanup if state persists long-term |

Tests must prepare their own fixtures and must not depend on execution order. With a broker, a producer sending successfully does not mean the listener has finished processing; wait for an observable condition using Awaitility, a latch, or a synchronization mechanism with a timeout.

## 15. Control Wait Times and Flakiness

Infrastructure-dependent tests have more sources of variance than unit tests: image pulls, database startup, readiness, network scheduling, consumer polling, and transaction commits.

To reduce flakiness:

- Use wait strategies instead of `Thread.sleep(...)` to wait for container readiness.
- Set finite timeouts for connections, queries, requests, and message consumption.
- Do not share fixed ports across test processes.
- Do not assume request/message ordering when tests run in parallel.
- Pin image versions.
- Keep fixtures small and avoid unindexed data queries in tests.
- Collect container logs and test reports when a job fails.
- Only retry tests at the pipeline level under a clear policy; retries must not hide product defects.

If a test fails intermittently, record the timestamp, logs, requests/messages, and container state. Do not add `@Disabled` or remove tags just to turn the pipeline green.

## 16. Use Execution Time to Decide Group Placement

Group names should not be a fixed guess. Measure execution time in CI and examine infrastructure startup cost.

Some useful metrics:

| Metric | What it indicates |
|---|---|
| Total duration of the fast task | Feedback latency in the developer loop |
| Spring context startup time | Auto-configuration cost and context cache efficiency |
| Container pull/start time | Infrastructure overhead in CI |
| Duration per integration test | Which tests or services consume most of the time |
| Flaky/environment failure rate | Pipeline reliability |
| Percentage of tests run in PRs | Protection coverage before merge |

If a test is tagged `integration` but does not actually need external services, review its scope. Conversely, if a test is tagged `fast` but requires Docker or a real server, fix the tag and pipeline instead of merely increasing timeouts.

## 17. When to Split into a Separate Source Set or Module?

Tags and separate tasks are usually enough. Split into a separate test source set or module when one of these needs applies:

- Integration tests need dependencies that fast tests do not.
- Tests require different resources, fixtures, or compiler configurations.
- You want independent lifecycle, reporting, or parallelism management.
- An application module has its own infrastructure and should not pull those dependencies into other modules.
- The build needs to run the integration suite as an independent artifact or job.

If you only need to select tests by tag, adding another source set increases classpath, test fixture, and dependency management configuration without adding much value. Start with tags; only expand when the build structure genuinely requires it.

## 18. Checklist for Organizing Test Groups and CI

Before putting conventions into the build, the team should be able to answer:

- Which tests run in the default task?
- Which tests require Docker, a database, a broker, or a server?
- Which JUnit tags are used and what does each tag mean?
- Which Gradle/Maven task runs each group?
- Which integration tests are mandatory before merge?
- Which CI runners have a container runtime and image pull permissions?
- Are tests data-independent and safe to run in parallel?
- Is the container lifecycle compatible with Spring context caching?
- How are timeouts, readiness, and failure logs managed?
- Where are fast-feedback duration and flaky rates tracked?

## 19. Implementation Workflow

1. Inventory existing tests and record the real dependencies of each group.
2. Mark unit/slice tests and integration/e2e tests using JUnit `@Tag`.
3. Choose a short tag vocabulary and a clear convention.
4. Create Gradle tasks or Maven Surefire/Failsafe configuration to filter by tag.
5. Ensure the default fast command requires no external infrastructure.
6. Create a CI job with a container runtime to run mandatory integration tests.
7. Place tests using real databases/brokers in the smallest feasible context.
8. Isolate data, queues/topics, and lifecycle between tests.
9. Collect reports, container logs, and execution timings.
10. Monitor flaky tests and adjust groups based on actual cost and risk.

## 20. References

- [JUnit 5 User Guide — Tagging and Filtering](https://junit.org/junit5/docs/current/user-guide/#writing-tests-tagging-and-filtering): tagging and selecting test groups.
- [Gradle User Manual — Test Filtering](https://docs.gradle.org/current/userguide/java_testing.html#test_filtering): configuring test tasks and test selection.
- [Gradle User Manual — JVM Test Suite](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): organizing test suites in Gradle.
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): running JUnit Jupiter and filtering tags.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): lifecycle for integration tests.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test slices and test support.
- [Testcontainers for Java](https://java.testcontainers.org/): managing databases, brokers, and services in containers for integration tests.

Separating fast tests from infrastructure-dependent tests gives developers early feedback while preserving integration evidence against real databases, brokers, and servers. Categorize by real dependencies, apply consistent tags, create separate tasks, and ensure CI has a stage responsible for running every critical infrastructure test before changes are accepted.
