# Reproducible Datasets and Logged Random Seeds

## 1. Why Must Test Data Be Reproducible?

A reliable test must be able to run again under the same conditions and produce the same result. If each test run generates different data without recording how it was created, a failure appearing in CI can be very hard to reproduce on a developer's machine.

For example, an order-total test randomly generates 20 line items. One run may generate valid values, while another creates quantities or boundary values that expose a bug. If CI only reports that the test failed without logging the generated data, whoever fixes the bug must guess which dataset caused it.

A reproducible dataset helps:

- Re-run the exact scenario that caused the test to fail.
- Distinguish product bugs from failures caused by invalid input data.
- Reduce dependence on test execution order and environment state.
- Share the exact same scenario between a developer machine and CI.
- Turn a random failure case into a fixed regression test.

In Spring Framework Testing, reproducibility applies to unit tests, service tests, repository tests, MVC/WebFlux tests, and integration tests. Test data can come from builders, factories, JSON/CSV files, SQL fixtures, database containers, or randomized data generators.

Important rule: if a test uses randomized data, it must record enough information to regenerate that data.

## 2. Deterministic Datasets vs. Randomized Datasets

There are two common ways to create fixtures.

### Deterministic fixtures

Deterministic fixtures have explicitly declared values:

~~~java
Order order = new Order(
        "ORD-1001",
        "CUST-42",
        List.of(
                new OrderLine("BOOK-1", 2, new BigDecimal("15.00")),
                new OrderLine("PEN-1", 3, new BigDecimal("2.50"))
        )
);
~~~

The advantage is that readers immediately see which data is under test. Deterministic fixtures suit business-rule tests, validation tests, mapping tests, and boundary cases that need to be stated explicitly.

### Randomly generated fixtures

Randomized fixtures produce many different values within a defined domain:

~~~java
Random random = new Random(12345L);

int quantity = 1 + random.nextInt(5);
long cents = random.nextInt(100_000);
BigDecimal price = BigDecimal.valueOf(cents, 2);
~~~

Randomness is useful when you need to exercise many input combinations, verify invariants, or uncover bugs that appear only under certain combinations. Yet without controlling the seed and generation logic, data changes across runs and makes tests hard to reproduce.

Not every test should use randomness. A test checking a discount rule at exactly 10% should have a clear example. A test checking that totals remain non-negative across thousands of combinations can be a good fit for randomly generated data.

An effective approach is to use deterministic fixtures for key business contracts, then supplement them with generated-data tests to broaden combination coverage.

## 3. What Is a Seed?

A **seed** is the initial value supplied to a pseudo-random number generator. Starting from the same seed, a deterministic generator produces the exact same sequence of numbers provided the algorithm and method call order remain identical.

Example:

~~~java
Random first = new Random(20261113L);
Random second = new Random(20261113L);

assertThat(first.nextInt()).isEqualTo(second.nextInt());
assertThat(first.nextInt()).isEqualTo(second.nextInt());
~~~

Both Random objects have the same seed. When calls are made in the same order, they produce the same sequence of results.

A seed is not the entire test dataset. It only reproduces the generator's number sequence. To recreate a fixture, you must also preserve:

- The algorithm/generator used.
- The seed.
- The order and number of generator calls.
- The data-generation library version if the library uses its own algorithm.
- The rules converting random numbers into domain data.
- Other input parameters such as record count, locale, and timezone.

If you add a nextInt() call at the start of the fixture builder, every subsequent generated value can change even when the seed stays the same. Therefore, changing fixture-generation logic can also cause an old seed to produce a different fixture.

## 4. Using `java.util.Random` with a Fixed Seed

java.util.Random is a straightforward choice when you need a reproducible pseudo-random number sequence.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
}

final class OrderLineFactory {

    static List<OrderLine> create(long seed, int count) {
        Random random = new Random(seed);
        List<OrderLine> lines = new ArrayList<>();

        for (int index = 0; index < count; index++) {
            int quantity = 1 + random.nextInt(5);
            long cents = random.nextInt(100_000);
            BigDecimal price = BigDecimal.valueOf(cents, 2);

            lines.add(new OrderLine(
                    "SKU-" + index,
                    quantity,
                    price
            ));
        }

        return List.copyOf(lines);
    }
}
~~~

Each call to OrderLineFactory.create(20261113L, 10) produces the same list under the same implementation and generator call order. SKUs are derived from the index so they do not consume an extra random call and never collide within that fixture.

A test can verify invariants:

~~~java
@Test
void generatedOrderLinesHaveValidValues() {
    List<OrderLine> lines =
            OrderLineFactory.create(20261113L, 50);

    assertThat(lines).hasSize(50);
    assertThat(lines).allSatisfy(line -> {
        assertThat(line.quantity()).isBetween(1, 5);
        assertThat(line.unitPrice()).isGreaterThanOrEqualTo(BigDecimal.ZERO);
        assertThat(line.sku()).isNotBlank();
    });
}
~~~

Do not create a shared static Random for the entire test suite. When multiple tests share a single generator, results depend on which test calls it first and how many times. Create a separate generator for each test or fixture factory.

### Same seed, different call order

The following snippets do not produce the same data because the call order differs:

~~~java
Random random = new Random(seed);

int quantity = random.nextInt(5);
int cents = random.nextInt(100_000);
~~~

~~~java
Random random = new Random(seed);

int cents = random.nextInt(100_000);
int quantity = random.nextInt(5);
~~~

Both use the same seed yet assign the generated numbers to different fields. When modifying fixture-generation code, treat it as a change that can affect replayability.

## 5. Encapsulate the Seed in a TestDataFactory

Avoid repeating generator initialization logic inside every test. You can create a factory that accepts a seed explicitly:

~~~java
public final class TestDataFactory {

    private final Random random;

    public TestDataFactory(long seed) {
        this.random = new Random(seed);
    }

    public Customer customer(int index) {
        return new Customer(
                "customer-" + index,
                "user" + index + "@example.test",
                18 + random.nextInt(63)
        );
    }

    public List<Customer> customers(int count) {
        return IntStream.range(0, count)
                .mapToObj(this::customer)
                .toList();
    }
}
~~~

Test using the factory:

~~~java
@Test
void shouldHandleManyCustomers() {
    long seed = 20261113L;
    TestDataFactory data = new TestDataFactory(seed);

    List<Customer> customers = data.customers(100);

    assertThat(customers).hasSize(100);
    assertThat(customers).allSatisfy(customer ->
            assertThat(customer.age()).isBetween(18, 80)
    );
}
~~~

The factory keeps its own generator, so a test does not depend on another test's generator. Passing the seed via the constructor also makes the data source visible right where the fixture is created.

A single factory can build multiple related data types, provided call order stays clear. If a test creates a customer, order, and payment from the same generator, changing how customers are built can shift the generated order/payment data. For large fixtures, consider separate seeds per data group to narrow the blast radius.

## 6. Log the Seed When Tests Run

A randomized test must report its seed in execution output, especially when failing in CI. Never leave the seed only in source code or in unpersisted debug logs.

JUnit Jupiter provides TestReporter to publish entries into the test report:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;

@Test
void generatedDataShouldPreserveOrderInvariants(TestReporter reporter) {
    long seed = 20261113L;
    reporter.publishEntry("random-seed", Long.toString(seed));

    TestDataFactory data = new TestDataFactory(seed);
    List<Customer> customers = data.customers(100);

    assertThat(customers).allSatisfy(customer ->
            assertThat(customer.age()).isBetween(18, 80)
    );
}
~~~

Additional replay metadata can also be published:

~~~java
reporter.publishEntry("generator", "java.util.Random");
reporter.publishEntry("fixture-version", "customer-factory-v2");
reporter.publishEntry("record-count", "100");
reporter.publishEntry("random-seed", Long.toString(seed));
~~~

If the test uses Faker or a property-based testing framework, log the generator/framework name and relevant version. For complex data, store the test method, fixture factory name, and generation parameters as well.

Record the seed before running the portion of the test that might fail. If you only log after the final assertion, a failure can happen before the seed is captured.

### Default seed and configured seed

You can use a stable default seed while allowing CI or developers to pass another seed via a system property:

~~~java
final class TestSeeds {

    private static final long DEFAULT_SEED = 20261113L;

    static long current() {
        String configured = System.getProperty("test.seed");
        return configured == null
                ? DEFAULT_SEED
                : Long.parseLong(configured);
    }

    private TestSeeds() {
    }
}
~~~

Test reading the seed from configuration:

~~~java
@Test
void shouldProcessGeneratedOrders(TestReporter reporter) {
    long seed = TestSeeds.current();
    reporter.publishEntry("random-seed", Long.toString(seed));

    List<OrderLine> lines =
            OrderLineFactory.create(seed, 100);

    assertThat(lines).hasSize(100);
}
~~~

A default seed keeps local runs stable. When you want to test a different dataset, pass a new seed without editing source code.

## 7. Pass the Seed into the Test Process in CI

With Gradle, ensure the system property from the Gradle process is forwarded to the test worker:

~~~groovy
tasks.test {
    systemProperty(
        "test.seed",
        System.getProperty("test.seed", "20261113")
    )
}
~~~

Then you can run a specific test with a recorded seed:

~~~bash
./gradlew test --tests "com.example.OrderServiceTest" -Dtest.seed=847291
~~~

The command above only takes effect if test.seed is forwarded to the test worker as in the Gradle configuration above. If the project has multiple test tasks, pass the property to the corresponding task.

With Maven Surefire, configure systemPropertyVariables to forward the property into the test JVM. Re-run with the matching property, for example:

~~~bash
mvn -Dtest.seed=847291 -Dtest=OrderServiceTest test
~~~

Inspect the project's plugin configuration to make sure the property is present in the test-running JVM. Passing -D to Maven/Gradle does not automatically guarantee every test worker receives the property unless the build forwards it.

## 8. Give Each Test Its Own Seed and Avoid Order Dependence

A common mistake is using a static generator:

~~~java
static final Random RANDOM = new Random(12345L);
~~~

Each test consumes a different amount of randomness. If test ordering changes, subsequent tests receive different data. Parallel execution can also make generator call ordering non-deterministic.

Instead, create a separate generator for each test:

~~~java
@Test
void shouldCalculateOneOrder() {
    Random random = new Random(1001L);
    // Create fixtures dedicated to this test.
}

@Test
void shouldCalculateAnotherOrder() {
    Random random = new Random(1002L);
    // Create independent fixtures.
}
~~~

If you want a single root seed for the whole suite, you can derive stable child seeds from test names or supply an explicit seed per test case. When deriving child seeds, use a deterministic transformation and log the final seed used to generate the data.

Do not rely on String.hashCode() as a unique identifier if test names could collide on hash. A hash should at most be one input into seed derivation; when certainty matters, store an explicit seed per test case.

### SplittableRandom and independent generators

SplittableRandom supports creating child generators via split(), which fits cases where data generation splits into independent branches:

~~~java
SplittableRandom root = new SplittableRandom(20261113L);

SplittableRandom customerRandom = root.split();
SplittableRandom orderRandom = root.split();
~~~

Each child generator can be assigned to a separate fixture group. This reduces the chance that one data group consuming randomness alters another group. For exact replay, keep the child-generator creation method and order unchanged.

SplittableRandom is not thread-safe. Do not share the same instance across multiple threads. Create or split a separate generator for each task.

## 9. Java Generators and When to Use Them

| Generator | Replayable by seed? | Notes |
|---|---|---|
| java.util.Random | Yes | Same seed and same call sequence produce the same number sequence |
| SplittableRandom | Yes when preserving split pattern and usage order | Useful for splitting data streams; not thread-safe |
| RandomGenerator | Depends on chosen implementation | Record both algorithm/generator name and seed |
| ThreadLocalRandom | Does not support setting seed normally | Unsuitable for fixtures needing replay |
| SecureRandom | Should not be used for reproducible fixtures | Designed for cryptography; unpredictability rather than replay is the goal |
| Math.random() | No API to pass a seed directly | Avoid in tests requiring reproducibility |

With Java 17 and above, the RandomGenerator API supports multiple algorithms:

~~~java
RandomGenerator generator =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(20261113L);
~~~

When using a named generator, log both the algorithm name and the seed. Do not log only the seed and later swap the implementation while expecting the same data.

Do not use SecureRandom or ThreadLocalRandom for test data that must be reproducible. If a test verifies cryptographic functionality, separate algorithm correctness tests from random fixture generation; use fixed test vectors for cryptographic results under verification.

## 10. Using Faker or Data Generation Libraries

Libraries like Java Faker/DataFaker can generate realistic-looking names, addresses, phone numbers, and data. This is helpful when a large volume of fixtures is needed, but the library must be initialized with a seeded random source.

Example with Java Faker:

~~~java
long seed = 20261113L;
Faker faker = new Faker(new Random(seed));

String name = faker.name().fullName();
String city = faker.address().city();
~~~

If each test uses its own Faker instance, the seed is controlled and calls in the same order can reproduce data under the current library version.

When upgrading Faker/DataFaker, internal algorithms or word lists may change. Thus, an old seed is not guaranteed to produce the exact same strings on a newer library version. Record dependency versions in build reports and pin versions through dependency management.

Do not use Faker to generate every field. For fields governed by business rules, construct data according to domain constraints. For instance, a syntactically valid email is not necessarily a registered account in the system; a random address is not necessarily inside a delivery zone. Faker generates plausible-looking data, not guaranteed domain validity.


## 11. Deterministic Data in Spring Integration Tests

When tests use a Spring ApplicationContext, prepare fixtures in a controlled place such as test data builders, repository fixture factories, or SQL scripts.

For example, a repository test can prepare fixed data:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindCustomerByEmail() {
        Customer customer = new Customer(
                "C-1001",
                "linh@example.test",
                "Linh"
        );
        repository.save(customer);

        assertThat(repository.findByEmail("linh@example.test"))
                .contains(customer);
    }
}
~~~

For repository tests running in a transaction managed by Spring Test, data can be rolled back after the method if the transaction manager and data access share that transaction.

Another option is an SQL fixture:

~~~java
@Test
@Sql("/sql/customer-fixture.sql")
void shouldReturnTheSeededCustomer() {
    assertThat(repository.findByEmail("linh@example.test"))
            .isPresent();
}
~~~

SQL files produce the same data on every run, keeping reproduction simple. If multiple tests share a database or run in parallel, use per-test keys or clean up only that test's fixture. Never run a cleanup script that wipes entire tables while other tests may be using the database.

### Test transactions do not wrap real HTTP requests

If a test sends a request to a server via RANDOM_PORT, the request is handled on a server thread in its own transaction. The test method's transaction does not propagate across an HTTP boundary.

Consequently, data created by an endpoint may remain even after the test method rolls back its own transaction. For HTTP integration tests:

- Create isolated fixtures before the request or through an endpoint.
- Track the fixture's ID/namespace.
- Send the HTTP request.
- Clean up the exact data after the test.
- Use a separate database/schema when tests run in parallel or require strong isolation.

Do not rely on @Transactional on a test to automatically roll back data written by requests to a real server.

## 12. Use Deterministic Namespaces and IDs for Fixtures

Test data must be both reproducible and collision-free with other tests. One approach is building a namespace from the test name and seed, then appending an incrementing sequence:

~~~java
final class FixtureIds {

    private final String namespace;
    private int sequence;

    FixtureIds(String testName, long seed) {
        this.namespace = testName + "-" + seed;
    }

    String next(String prefix) {
        return namespace + "-" + prefix + "-" + sequence++;
    }
}
~~~

For instance, a test might generate IDs such as:

~~~text
OrderServiceTest-847291-customer-0
OrderServiceTest-847291-order-1
OrderServiceTest-847291-payment-2
~~~

Deterministic namespaces recreate the exact same IDs when replaying the same test and seed. If multiple workers run the same test/seed against a shared database, add a worker namespace or separate databases/schemas per worker. Worker information must also be logged to rebuild the exact fixture.

Do not use unseeded random IDs like UUID.randomUUID() if the goal is exact reconstruction of the full fixture. When UUIDs are needed, use fixed UUIDs in tests or generate UUIDs from a clearly managed deterministic source.

## 13. Pin Time, Locale, and Timezone

A seed only controls the generator. It will not stabilize a test if outcomes also depend on the CI machine's system clock, timezone, or locale.

### Use Clock instead of system time

If a service calls LocalDate.now() or Instant.now() directly, results can change depending on the date the test runs. Inject Clock instead:

~~~java
@Configuration
class TimeConfig {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

In tests, replace Clock with a fixed instant:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
~~~

You can use @TestBean or @MockitoBean to supply a test clock if the application injects Clock through its constructor. Tests then no longer depend on the calendar date or time of execution in CI.

### Pin timezone and locale

When testing date, number, or currency formatting, specify locale and zone explicitly:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.UK);

String value = formatter
        .withZone(ZoneId.of("UTC"))
        .format(Instant.parse("2026-01-15T10:00:00Z"));
~~~

Do not rely on Locale.getDefault() or ZoneId.systemDefault() in assertions if the API requires a fixed format. The same Instant can render as different dates across timezones; decimal separators and digit grouping also vary by locale.

## 14. Verify Randomized Data Using Invariants

When data is randomly generated, hardcoding the entire expected output is usually impractical if the goal is verifying a general rule. Define invariants that must always hold.

For example, for every order line:

- Quantity must be greater than 0.
- Unit price is non-negative.
- Line total equals unit price multiplied by quantity.
- Order total equals the sum of line totals.
- Total amount does not exceed defined domain limits.

~~~java
@Test
void generatedOrderTotalMustEqualSumOfLines() {
    long seed = 847291L;
    List<OrderLine> lines = OrderLineFactory.create(seed, 100);

    BigDecimal expected = lines.stream()
            .map(line -> line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

    BigDecimal actual = orderCalculator.total(lines);

    assertThat(actual).isEqualByComparingTo(expected);
}
~~~

Here, data is generated from a seed while expected is computed via an independent summation over the generated lines. Avoid calling the same production method to compute both actual and expected; if both sides share buggy logic, the test can still pass.

For algorithms with known reference results, keep fixed example tests as well. Random tests broaden input coverage; they do not replace examples illustrating business rules.

## 15. Property-Based Testing and Logged Seeds

Property-based testing generates many inputs to verify a general property instead of running only a few hand-picked examples.

For example, one property might be: for any non-negative monetary amount within the supported range, applying a 0% discount must preserve the original price.

With jqwik:

~~~java
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.LongRange;

class DiscountProperties {

    @Property(tries = 200)
    void zeroDiscountKeepsTheOriginalPrice(
            @ForAll @LongRange(min = 0, max = 1_000_000_00L) long cents
    ) {
        BigDecimal price = BigDecimal.valueOf(cents, 2);

        assertThat(discountService.apply(price, 0))
                .isEqualByComparingTo(price);
    }
}
~~~

Property-based frameworks can generate many values and often include shrinking: when a failing input is found, the framework tries to minimize it to a smaller, easier-to-understand case.

With randomized tests of this kind, seeds play a vital role. Frameworks like jqwik report the seed in results so developers can re-run the same generation pass. When capturing a CI failure, preserve:

- The property/test method name.
- The seed reported by the framework.
- The try count and generator configuration.
- The jqwik and JDK versions.
- The specific value that failed the property if provided in the report.

You can pin the seed in property configuration when replaying a bug. Exact replay syntax depends on the jqwik version; use the seed reported and the API/configuration of your installed version.

### When should you use property-based testing?

It is suitable when:

- A general invariant applies across many inputs.
- The combination space is large and hard to enumerate manually.
- You need to uncover edge cases or multi-field interaction bugs.
- You want the framework to shrink failing inputs into easy-to-diagnose examples.

Do not use property tests to replace all business tests. Scenarios such as orders rejected for insufficient stock, unauthorized users, or already-completed payments still need explicit fixed examples stating clear expectations.

## 16. Valid Random Data Must Respect Domain Constraints

Generating numbers in a range does not automatically yield valid data. For example:

- Ages between 18–80 may be valid, yet the birth date must correspond to that age.
- A positive quantity can still exceed inventory limits.
- A well-formed email might collide with an existing account.
- End date must come after start date.
- Totals must obey currency scale and rounding rules.

Put domain rules directly inside fixture factories:

~~~java
static Subscription subscription(Random random) {
    LocalDate start = LocalDate.of(2026, 1, 1)
            .plusDays(random.nextInt(365));
    LocalDate end = start.plusDays(1 + random.nextInt(30));

    return new Subscription(start, end);
}
~~~

Generators should produce valid data by default. Negative-case tests can intentionally construct invalid data to test validation. Never let most random tests fail simply because the generator accidentally creates invalid data outside the test's target.


## 17. Seed Strategy for Local, Pull Request, and Nightly CI

A good CI workflow balances reproducibility with broad data exploration.

Three modes can be used:

| Mode | Seed | Goal |
|---|---|---|
| Local default | Stable seed in configuration | Everyone re-runs the same dataset unless a seed is specified |
| Pull request | Stable seed or recorded per-build seed | Review results are reproducible |
| Nightly/stress | Seed varies per run and is always saved | Broaden input combinations to discover rare bugs |

If nightly CI uses varying seeds, write the seed into the test report and build summary logs. When a test fails, trigger a replay run using that exact seed rather than continuing with a new seed.

One way to derive a per-build seed is from the build number or a CI-supplied value. However, never rely solely on the build number without logging the actual value passed to the test worker. Reports should indicate the final seed the generator received.

Never rotate seeds on every run without saving them. Otherwise tests can detect bugs without supplying enough data to fix them.

## 18. Logging Seeds and Fixture Info in CI

Besides JUnit TestReporter, you can log seeds with a logger so the information appears in CI logs:

~~~java
long seed = TestSeeds.current();

logger.info(
        "Running randomized order test with seed={}, fixtureVersion={}",
        seed,
        "order-lines-v3"
);
~~~

A useful replay record should include:

| Field | Example | Reason |
|---|---|---|
| Test class/method | OrderCalculatorTest.generatedOrderTotal | Identifies the test to re-run |
| Seed | 847291 | Recreates the number sequence |
| Generator | java.util.Random | Identifies the algorithm |
| Fixture version | order-lines-v3 | Identifies the rules turning numbers into domain data |
| Record count | 100 | Identifies dataset size |
| JDK | 21.x | Records execution runtime |
| Dependency version | DataFaker 2.x | Needed when using data-generation libraries |
| CI build/run ID | pipeline-1842 | Locates original logs and artifacts |

If a test fails on a specific record, also log the generated value or save the fixture as a build artifact. A seed alone may be insufficient if the generator depends on external libraries, locale data, or algorithms that change across versions.

Never write real sensitive data into test reports. Test data should use dummy addresses and identifiers like example.test, not personal details or production data.

## 19. Workflow for Reproducing a Random CI Failure

When CI reports a randomized test failure, follow a repeatable workflow:

1. Open the report and locate the test name, seed, generator, and fixture version.
2. Identify the exact JDK and dependency versions of the failing build.
3. Run that specific test with the recorded seed.
4. Confirm the test reproduces the same failure.
5. Capture the smallest possible input if a property-based framework shrank the data.
6. Fix the bug and add a regression test for the concrete case.
7. Keep the random test to continue exploring other combinations if it provides value.

Example re-run with Gradle:

~~~bash
./gradlew test --tests "com.example.OrderCalculatorTest" -Dtest.seed=847291
~~~

If the test uses a framework-managed seed, pass the seed via that framework's mechanism rather than only passing a generic system property. A jqwik seed is not necessarily the same as a seed for a factory using java.util.Random.

### When it cannot be reproduced

If the same seed does not reproduce the issue, inspect factors outside the seed:

- Does the test use a static or shared generator across tests?
- Did execution order or the number of random calls differ?
- Did another test write to the same database/cache/queue?
- Did system time, timezone, or locale affect the outcome?
- Were asynchronous tasks still unfinished when the test ended?
- Did the JDK or data-generation library version differ?
- Did external test data or an external service change?

A seed only reproduces the randomness it controls. It does not by itself make the execution environment deterministic.

## 20. Data Isolation Under Parallel Execution

CI often runs test classes or methods in parallel to reduce duration. If tests write to the same database, file, queue, or mock state, data can collide even when every test has a fixed seed.

Isolation strategies:

- Generate distinct IDs per test class, test method, seed, and worker.
- Use a dedicated database/schema/container per test suite or worker.
- Clean up only the records created by the test rather than wiping entire tables.
- Use a dedicated temporary directory per test.
- Use namespaced topics/queues.
- Do not share a mutable Random or SplittableRandom across threads.
- Do not share a stateful fixture factory across concurrent tests.

If two workers run the same test with the same seed, they can generate identical IDs. Thus, a seed is not a globally unique identifier for external resources. Adding a worker namespace or isolating databases is necessary when concurrent runs share a resource.

### Avoid order-dependent tests

A test must not require another test to run beforehand to build fixtures or reset state. Let each test create the data it needs and clean up within its own scope.

Spring's context caching saves time loading ApplicationContext, yet it does not automatically clean databases, Redis, files, or message brokers. Resources outside the context must still be managed independently.

## 21. Sources of Nondeterminism Beyond Randomness

A logged seed is still insufficient if a test depends on unfixed environmental factors.

| Source of variance | Example | How to control |
|---|---|---|
| System clock | Orders expire based on the current date | Inject Clock and use Clock.fixed |
| Timezone | Dates render differently between local and CI | Use an explicit ZoneId |
| Locale | Decimal separators or month names differ | Specify Locale explicitly |
| Collection order | Iterating a HashMap and assuming order | Sort by key before asserting |
| Database state | Leftover records from earlier runs | Dedicated fixtures, proper transactions, and cleanup |
| Sequence/identity | Auto-increment IDs differ across runs | Do not assert fixed generated IDs unless part of the contract |
| Concurrency | Race conditions alter event order | Use latches/barriers and contract-based assertions |
| Network ports | Server picks a different port | Obtain the injected port or URL from the server fixture |
| External services | Responses vary over time | Stub with a local server or deterministic fixtures |
| File system | Stale paths or file contents | Use temporary directories and clean up after tests |

When tests verify asynchronous processing order, do not use Thread.sleep() hoping tasks complete on time. Use latches, barriers, controlled publishers, or Awaitility with clear deadlines.

## 22. Turn a Random Failure into a Regression Test

When a random test uncovers a bug, preserve a fixed example so that bug cannot vanish if seeds or generators later change.

For example, a random test discovers that totals are calculated incorrectly for very large quantities. After identifying the concrete input, add an explicit test:

~~~java
@Test
void shouldCalculateTotalForLargeQuantities() {
    List<OrderLine> lines = List.of(
            new OrderLine(
                    "SKU-LARGE",
                    100_000,
                    new BigDecimal("999.99")
            )
    );

    assertThat(orderCalculator.total(lines))
            .isEqualByComparingTo("99999000.00");
}
~~~

Afterward, you can still keep the random/property test to find additional combinations. The fixed regression test guards the known case and clarifies the rule; the random test continues exploring a broader input space.

If a bug only reproduces after a sequence of multiple operations, store the seed alongside the test method and fixture version. If that sequence depends on external state, also store the input data or event sequence needed for full reproduction.

## 23. Checklist for Using Reproducible Random Data

Before adding a randomized test to CI, verify:

- Which generator is used and whether it supports seeding.
- Where the seed comes from: constant, system property, or CI build.
- Where the seed is logged in reports/logs.
- Whether factories hold isolated state per test.
- Whether generated values satisfy domain constraints.
- Whether fixtures have IDs/namespaces avoiding collisions in parallel runs.
- Whether the failing test can be re-run individually with the logged seed.
- Whether generator version and fixture version are recorded if needed.
- Whether other sources like clock, locale, timezone, and database state are controlled.
- Whether known failure cases have deterministic regression tests.

There is no need to generate millions of records for every test. Choose a data size appropriate to the invariant under test and use separate stress/load tests when evaluating performance limits.

## 24. A Complete Replayable Test Pattern

The following example combines a seed from a system property, TestReporter, and a fixture factory:

~~~java
@SpringBootTest
class OrderCalculatorRandomizedTest {

    private static final long DEFAULT_SEED = 20261113L;

    @Autowired
    private OrderCalculator orderCalculator;

    @Test
    void totalMustMatchTheSumOfGeneratedLines(TestReporter reporter) {
        long seed = Long.parseLong(
                System.getProperty(
                        "test.seed",
                        Long.toString(DEFAULT_SEED)
                )
        );

        reporter.publishEntry("random-seed", Long.toString(seed));
        reporter.publishEntry("generator", "java.util.Random");
        reporter.publishEntry("fixture-version", "order-lines-v1");

        List<OrderLine> lines = OrderLineFactory.create(seed, 100);

        BigDecimal expected = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal actual = orderCalculator.total(lines);

        assertThat(actual).isEqualByComparingTo(expected);
    }
}
~~~

When the test fails in CI, grab the random-seed value from the report and re-run that exact test with the corresponding system property. Make sure Gradle/Maven forwards the property to the test process.

This example checks the sum of generated data. In real projects, you can add assertions for domain limits, rounding, quantities, order statuses, and empty-data handling. Keep the expected calculation independent from the implementation under test.

## 25. Principles for Maintaining Reproducible Datasets

- Prefer fixed fixtures for concrete business scenarios.
- Use randomness for exploring combinations and verifying invariants.
- Create an isolated generator per test or fixture branch.
- Record the seed before assertions that may fail.
- Record algorithm names, fixture versions, and data-generation libraries when needed.
- Forward seeds explicitly from CI to test workers.
- Isolate databases, queues, files, and IDs during parallel execution.
- Pin Clock, timezone, locale, and data ordering whenever they affect outcomes.
- Replay CI failures using the logged seed, then add deterministic regression tests.
- Keep test data synthetic and never use sensitive production data.

A good test dataset enables tests to explore many situations while still allowing exact reproduction of any failing case. The logged seed is the starting point; the generator, fixture creation rules, and runtime environment must also be controlled so CI delivers failures that can be investigated and fixed.

