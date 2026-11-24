# Independence from Execution Order and Other Tests' Data

A good test must state the conditions it verifies and prepare the data it needs on its own. A test's result must not depend on another test having run beforehand, created a database record, mutated a bean, or set a global variable.

In test design, this requirement is called test independence. An independent test can run alone, alongside the entire test suite, repeatedly, and in any order while producing the exact same result when input conditions are unchanged. When tests are configured to run in parallel, independence also requires not contending over shared data or resources.

## Why Must Tests Be Independent?

Consider these two tests:

- Test A creates a customer with code `C-100`.
- Test B looks up customer `C-100` and asserts the name is Lan.

If Test B succeeds only after Test A runs, Test B depends on state produced by another test. When running B alone, running B before A, or re-running B after data changes, the outcome can break.

A test suite with hidden dependencies typically exhibits these symptoms:

- A test passes when run alone yet fails when run with the full suite.
- Changing test execution order alters results.
- Running the same test multiple times triggers duplicate data or unique-key errors.
- Parallel execution causes tests to pass intermittently and fail intermittently.
- One failing test triggers cascading failures across many subsequent tests.
- Failures can be reproduced only by running a fixed command or subset of tests.

These issues erode trust in test signals. When a test fails, the team struggles to tell whether the bug lies in recently changed business code or in leftover state from an earlier run.

## Four Sources of Dependency to Watch For

Independence goes beyond method invocation order. A test can depend on several forms of state:

| Dependency source | Example | How to handle |
|---|---|---|
| Execution order | Test B needs a record created by Test A | Each test prepares its own data |
| Shared data | Multiple tests edit the same customer or table | Use dedicated data, unique identifiers, and scoped cleanup |
| In-memory state | Singleton bean holds a mutated counter, cache, or list | Avoid shared mutable state; reset explicitly when needed |
| External environment | Fixed file path, message broker, live API, current time, or JVM config | Isolate resources and control environment inputs |

A test may never call another test directly yet still depend indirectly on data, caches, configuration, or resources left behind by a preceding test.

## Do Not Design Tests Around Execution Order

JUnit Jupiter manages test lifecycle and method execution. Default test method order is not a business contract for tests to rely on. JUnit does offer ordering via `@TestMethodOrder`, yet that annotation should not be used to turn a chain of state-dependent tests into a test workflow.

For example, the following design is problematic:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class CustomerFlowTest {

    @Test
    @Order(1)
    void createsCustomer() {
        // Create customer C-100 in the database.
    }

    @Test
    @Order(2)
    void findsCreatedCustomer() {
        // Assumes C-100 was created by the test above.
    }
}
~~~

The second test does not create its own input conditions. When run alone, it can fail because no data is found. If the first test changes or is skipped, the second test breaks too.

When testing a multi-step flow, place the steps inside one test case to express a cohesive scenario:

~~~java
@Test
void createsAndFindsCustomer() {
    var customer = customerService.create("C-100", "Lan");

    var found = customerService.findByCode(customer.code());

    assertThat(found).isPresent();
    assertThat(found.get().name()).isEqualTo("Lan");
}
~~~

Here the test actively creates the customer and verifies the result of its own action. Causally linked steps belong to one scenario; other independent behaviors belong in separate tests.

If business logic genuinely requires verifying a state sequence—such as creating an order, paying for it, then cancelling it—keep that sequence within one test or build explicit fixtures for each state. Do not split one scenario across multiple test methods just to mimic independent tests for each step.

## Each Test Prepares Its Own Data

A test should explicitly declare the input data it needs. Do not rely on a pre-existing record in a shared database, a file written by another test, or a static variable updated elsewhere.

Useful principles:

- Create minimal data sufficient to verify the behavior under test.
- Use factories or fixture builders to construct fresh objects per test.
- Prefer unique identifiers when multiple tests share a database or service.
- Avoid mutating a shared record in place without restoring state.
- Name data to reflect the test's intent so failures are easier to read.
- Do not depend on auto-increment ID order unless that ordering itself is under test.

For example, a repository test can generate a unique email per run:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        String email = "row39-" + UUID.randomUUID() + "@example.test";

        jdbcTemplate.update(
            "insert into customer(email, name) values (?, ?)",
            email,
            "Lan"
        );

        var customer = customerRepository.findByEmail(email);

        assertThat(customer).hasValueSatisfying(found ->
            assertThat(found.getName()).isEqualTo("Lan")
        );
    }
}
~~~

The example assumes the schema has a `customer` table, test configuration provides the datasource and repository, and `findByEmail` returns `Optional<Customer>`. Random emails prevent colliding with records from previous runs or other tests. `@Transactional` lets Spring Test manage the test transaction and roll it back by default when the test finishes.

Unique data does not completely replace cleanup. It reduces collisions and lets tests repeat, but if a test commits data to a shared database, a deletion strategy or database/schema isolation is still needed.

## What Does Transaction Rollback Help With—and What Not?

Spring Test supports test-managed transactions. When a test is annotated with `@Transactional` and a suitable transaction manager is present, Spring Test starts a transaction before the test and rolls it back afterward by default. This mechanism is especially helpful for repository tests and database-backed integration tests.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesOrder() {
        var order = orderRepository.save(new Order("ORD-TEST-1"));

        assertThat(order.getId()).isNotNull();
        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
~~~

Each test running in its own test-managed transaction leaves no rolled-back changes behind for the next test. However, rollback has specific boundaries:

1. It reverts only changes belonging to and participating in the managed transaction.
2. An independent transaction, such as a flow using `REQUIRES_NEW` propagation, can commit separately.
3. Work on another thread or asynchronous tasks do not automatically join the test thread's transaction.
4. Outbound HTTP calls, broker messages, file writes, or emails cannot be undone by database rollback.
5. Changes committed outside the test's transaction remain after the test ends.

Therefore, do not assume adding `@Transactional` isolates every test completely. Identify which data and side effects sit inside the transaction, which commit independently, and which resources need separate cleanup.

When a test must genuinely commit to verify specific behavior, you can use `@Commit` or `@Rollback(false)`. In that case, the test must plan to create dedicated data and delete it afterward, or use a database/schema created specifically for the test run.

## Use Spring Test to Prepare and Clean Data Deliberately

Spring Test provides `@Sql` to execute SQL scripts at specific test method phases. It is useful when a test requires a well-structured database fixture:

~~~java
@Test
@Sql(
    scripts = "/sql/customer-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/customer-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void findsConfiguredCustomer() {
    var customer = customerRepository.findByEmail("fixture@example.test");

    assertThat(customer).isPresent();
}
~~~

Setup and cleanup scripts must stay narrowly scoped, affecting only the test's own data. Avoid wiping whole tables or truncating a shared database when other tests may use the same tables. If tests run in parallel, fixtures with fixed keys can collide; use distinct identifiers or isolated databases/schemas instead.

Depending on transaction configuration, SQL scripts may execute inside the current transaction or in a separate transaction. Choose the execution phase and transaction mode matching the test goal, especially when data needs independent commits.

For larger systems, common isolation strategies include:

- Separate database per test suite or per worker.
- Separate schema per test group.
- Service containers created and destroyed with the test suite lifecycle.
- Datasets namespaced per test run.
- Cleanup keyed by test-generated identifiers or namespaces.

The goal is ensuring one test never deletes, alters, or misreads another test's data.

## Be Careful with Shared `ApplicationContext` and Singleton Beans

Spring Test uses the TestContext Framework to manage `ApplicationContext` instances. Contexts can be cached and reused across tests sharing equivalent configuration. This cuts startup time, but also means multiple tests can see the same bean instances.

By default, Spring beans use singleton scope within an `ApplicationContext`. If a bean holds mutable state, mutations from one test can leak into later tests:

~~~java
@Component
class RequestCounter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
~~~

If a test calls `increment()` assuming `value()` starts at 0, the outcome depends on whether another test already used the bean. In production code as well, stateful mutable singleton beans introduce thread-safety hazards.

Prefer stateless beans or pass state as arguments and return values. If mutable caches or buffers are necessary, provide an explicit reset mechanism in tests, or use a dedicated context when genuinely required by the scenario.

`@DirtiesContext` marks an `ApplicationContext` as no longer fit for reuse, causing Spring to evict it from the cache and recreate it when needed. It is intended for cases where a test mutates context state in ways that cannot be reliably restored. It is not a mechanism for cleaning databases, deleting files, retracting messages, or undoing side effects outside Spring. Overusing this annotation slows suites down through repeated context startups.

## Avoid Global State and Mutable Fixtures

Global state is often hard to spot because it lives outside the test instance lifecycle:

- `static` fields holding shared lists or counters.
- Mutated system properties, default locale, time zone, or JVM settings.
- One-time initialized static caches.
- Singleton beans holding mutable collections.
- Temporary files with hardcoded names.
- Hardcoded network ports or queue names shared across tests.

If a test must alter a global setting, capture the old value and restore it in `finally` or the corresponding lifecycle cleanup. Even then, restoring afterward does not prevent races if another test runs in parallel while the setting is altered. Tests mutating global resources must be serialized or redesigned to stop sharing them.

Fixture builders should also create fresh objects instead of returning a shared instance:

~~~java
class CustomerFixture {

    static Customer newCustomer() {
        return new Customer(
            "customer-" + UUID.randomUUID(),
            "Lan"
        );
    }
}
~~~

Each call to `newCustomer()` creates an independent customer. Reusing a static object and mutating its name or code per test can accidentally share references and corrupt each other's data.

## Independence Under Parallel Execution

Running tests in parallel cuts feedback time, yet exposes shared dependencies. Two tests might concurrently:

- Insert the same fixed email or order code into the same table.
- Delete the same set of records.
- Write to the same file.
- Share a queue, topic, bucket, or resource name.
- Mutate the same system property or singleton bean state.

To run safely in parallel, each test should own its own data and resources. For instance, generate UUID-based filenames in a temp directory, namespace database keys per test run, or assign a dedicated database/schema per worker.

When a resource truly cannot be shared safely, restrict only tests using that resource to run sequentially via an appropriate synchronization mechanism. Locking should make the protected resource explicit; do not serialize the entire test suite just to hide an unresolved dependency.

Also distinguish sharing immutable fixtures from sharing mutable fixtures. Read-only immutable data can usually be shared safely. Mutable data must be copied, freshly constructed, or protected by synchronization.

## Control Time, Randomness, and External Services

A test can depend on its environment even without sharing a database. For example, a test checking invoice expiration by reading current system time directly will yield different outcomes on different dates or right near midnight boundaries.

For time-dependent logic, inject the time source as a dependency so tests can supply a fixed instant:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);

var service = new ExpirationService(fixedClock);
~~~

In a Spring application, `Clock` can be declared as a bean and overridden with a fixed clock in test configuration. Tests can then verify exact expiration boundaries without relying on the host machine's clock.

For random data, use a fixed seed when reproducing an exact sequence of values; use UUIDs or random keys when avoiding collisions across tests. These two goals differ: fixed seeds aid reproducibility, whereas unique identifiers aid isolation.

Do not let business tests call real external APIs whose responses and state lie outside the test's control. Replace remote dependencies with stubs, fakes, or mocks appropriate for the layer under test. When real communication must be verified, keep a separate integration test group with controlled environment and data.

Avoid `Thread.sleep()` to wait on uncertain conditions. Sleeping only delays tests; it does not guarantee the desired state has arrived. For async tasks, wait on an explicit condition via synchronization primitives or bounded polling, and clean up tasks and resources once done.

## Detecting and Fixing a Dependent Test

When a test fails only in full-suite runs, isolate it by running the test alone, running it repeatedly, running the whole class, shuffling order, or enabling parallel execution if supported. The aim is finding which state the test is inadvertently inheriting externally.

Common symptoms and diagnostic questions:

| Symptom | Question to investigate |
|---|---|
| Passes alone, fails in suite | Which earlier test modified data, a bean, or configuration? |
| Passes first run, fails second run | Which committed records or files/resources remained behind? |
| Fails only under parallel execution | Which resource or identifier is being shared? |
| Result depends on when it runs | Does the test read a clock, time zone, locale, or external service? |
| Adding `@DirtiesContext` hides the error | Is a mutable bean or context state leaking? |
| Data remains even after rollback | Is there an independent transaction, another thread, or an out-of-DB side effect? |

Once you find the root cause, fix it at the dependency source: build dedicated fixtures, use unique identifiers, restore state, isolate resources, or eliminate unnecessary mutable state. Simply forcing execution order or resetting the entire context may mask symptoms in one configuration while leaving the underlying bug intact.

## Immediately Applicable Design Principles

When writing a new test, ask yourself:

1. Can the test run alone without another test creating data first?
2. Does the test construct the records and objects it needs itself?
3. Can data created by this test collide with other tests or earlier runs?
4. Does the test mutate singleton beans, static variables, system properties, files, or shared resources?
5. If a transaction is used, do all write operations actually participate in that transaction?
6. If tests run in parallel, does each test own dedicated data and resources?
7. Are time, random numbers, and external service responses controlled?
8. After the test finishes, are the data and resources owned by the test rolled back or cleaned up?

An independent test does not need to know which test ran before it. It sets up its own inputs, exercises one clearly scoped behavior, asserts the outcome, and manages the changes it produces. Maintaining this discipline keeps the test suite reliable whether run individually, repeatedly, reordered, or scaled to parallel execution.
