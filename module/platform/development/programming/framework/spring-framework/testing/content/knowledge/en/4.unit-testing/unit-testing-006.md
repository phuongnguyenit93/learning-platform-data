# Replacing Clocks, ID Generators, and Randomness with Controllable Dependencies

Unit tests must produce predictable results given the same inputs and initial conditions. However, many application operations rely on sources that vary by time or environment: the current timestamp, a newly generated UUID, random numbers, verification codes, retry jitter values, or auto-generated fixture data. When code calls `Instant.now()`, `UUID.randomUUID()`, or `ThreadLocalRandom.current()` directly across many places, tests struggle to control values and often end up waiting, guessing, or asserting overly broad conditions.

The solution is to turn those non-deterministic sources into **injectable dependencies**. Production receives implementations backed by the system clock, ID generator, or appropriate random source. Unit tests replace them with `Clock.fixed`, fixed IDs, fakes, or generators with a known seed. Tests can then assert exact timestamps, identifiers, and logic branches without relying on wall-clock time or chance.

## 1. Identifying Non-Deterministic Sources in Code

The following calls often make tests hard to repeat:

```java
Instant createdAt = Instant.now();
LocalDate today = LocalDate.now();
long now = System.currentTimeMillis();

UUID id = UUID.randomUUID();
int retrySlot = ThreadLocalRandom.current().nextInt(1, 6);
String token = generateRandomToken();
```

On each run, values can differ. A test checking an expiration date might pass today and fail tomorrow. A test comparing an entire entity might fail due to a fresh ID or different timestamp. A retry test might only hit the short-delay branch on some runs, making boundary branches hard to reproduce.

Not every random call needs replacement. When testing an algorithm in isolation where randomness itself is the subject under test, statistical testing or property-based testing may be appropriate. Yet in business unit tests, we usually want to verify how the system reacts to a specific timestamp, ID, or random value. Those sources should be controlled through dependencies.

Three common categories:

| Source | Examples | How to Control in Tests |
|---|---|---|
| Time | `Instant.now()`, `LocalDate.now()`, expiration timestamps | Inject `java.time.Clock`, use `Clock.fixed()` |
| IDs | `UUID.randomUUID()`, ID sequences | Inject `IdGenerator`, return fixed IDs or a predefined sequence |
| Randomness | `Random`, `ThreadLocalRandom`, jitter, random test data | Inject a narrow abstraction or a generator with a fixed seed |

The goal is not to turn every utility function into an interface. Extract only sources whose outputs vary with time, environment, or external state and must be controlled in tests.

## 2. Injecting `Clock` to Control Time

Java provides `java.time.Clock` specifically for this purpose. Instead of calling `Instant.now()` or `LocalDate.now()` directly, code accepts a `Clock` and reads time from it.

```java
import java.time.Clock;
import java.time.Instant;

class ExpirationService {
    private final Clock clock;

    ExpirationService(Clock clock) {
        this.clock = clock;
    }

    Instant currentTime() {
        return Instant.now(clock);
    }
}
```

In the real application, provide a clock backed by the system clock. In a Spring application, you can declare a bean:

```java
@Configuration
class TimeConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Services receive `Clock` via constructor just like any other dependency:

```java
@Service
class SubscriptionService {
    private final Clock clock;

    SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    Subscription renew(Subscription subscription, Duration duration) {
        Instant renewedAt = Instant.now(clock);
        return subscription.renew(renewedAt, duration);
    }
}
```

`Clock.systemUTC()` supplies the current time in UTC. Using `Instant` to store an absolute point in time avoids confusion between instants and display time zones. When business rules require a calendar date in a store's or user's time zone, convert explicitly using `ZoneId` instead of implicitly relying on the test runner's default time zone.

### 2.1. Using `Clock.fixed()` in unit tests

`Clock.fixed(instant, zone)` creates a clock that always returns the same point in time. This is the best option for most tests involving creation dates, update timestamps, expirations, effective dates, and deadline checks.

```java
class ExpirationServiceTest {
    private static final Instant NOW =
            Instant.parse("2026-11-12T08:30:00Z");

    @Test
    void considersSubscriptionExpiredAtItsExpirationInstant() {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        ExpirationService service = new ExpirationService(clock);
        Subscription subscription = new Subscription(
                NOW.minus(Duration.ofDays(1)), NOW);

        boolean expired = service.isExpired(subscription);

        assertThat(expired).isTrue();
    }
}
```

Crucially, the test chooses the timestamp itself. There is no need for `Thread.sleep`, no dependence on the CI machine's date, and no risk of crossing midnight between two assertions.

When testing boundaries, clarify the business rule. For example, does a subscription expire when `now` equals `expiresAt` or only when `now` is after `expiresAt`? Tests should cover before, exactly at, and after the boundary:

```java
@Test
void checksExpirationBoundary() {
    Instant expiresAt = Instant.parse("2026-11-12T08:30:00Z");

    assertThat(serviceWithClock(expiresAt.minusMillis(1))
            .isExpired(expiresAt)).isFalse();
    assertThat(serviceWithClock(expiresAt)
            .isExpired(expiresAt)).isTrue();
    assertThat(serviceWithClock(expiresAt.plusMillis(1))
            .isExpired(expiresAt)).isTrue();
}
```

`serviceWithClock` here is a test helper constructing the service with the corresponding `Clock.fixed`. These three cases pinpoint the exact `<`, `<=`, or `>` condition in the expiration rule.

### 2.2. Using `Clock.offset()` when shifting time

`Clock.offset(baseClock, duration)` creates a clock offset by a duration from a base clock. It is useful when deriving another timestamp from the same reference point:

```java
Instant base = Instant.parse("2026-11-12T08:30:00Z");
Clock baseClock = Clock.fixed(base, ZoneOffset.UTC);
Clock fiveMinutesLater = Clock.offset(baseClock, Duration.ofMinutes(5));

assertThat(Instant.now(fiveMinutesLater))
        .isEqualTo(base.plus(Duration.ofMinutes(5)));
```

An offset clock stays fixed if the base clock is fixed. It does not advance with wall-clock time. This is very useful for tests comparing multiple points in time while keeping results repeatable.

### 2.3. When you need a clock that can advance

Some tests exercise multiple operations over time, such as issuing a token and checking that it expires a few minutes later. You can use two separate `Clock.fixed` instances for the two phases, or write a controllable test clock. The following example is a small test-only implementation:

```java
final class AdjustableClock extends Clock {
    private Instant currentInstant;
    private final ZoneId zone;

    AdjustableClock(Instant initialInstant, ZoneId zone) {
        this.currentInstant = initialInstant;
        this.zone = zone;
    }

    void advance(Duration duration) {
        currentInstant = currentInstant.plus(duration);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(currentInstant, zone);
    }

    @Override
    public Instant instant() {
        return currentInstant;
    }
}
```

Tests can advance time without waiting:

```java
@Test
void expiresTokenAfterConfiguredDuration() {
    AdjustableClock clock = new AdjustableClock(
            Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    TokenService service = new TokenService(clock, Duration.ofMinutes(10));

    Token token = service.issue();
    assertThat(service.isValid(token)).isTrue();

    clock.advance(Duration.ofMinutes(10));

    assertThat(service.isValid(token)).isFalse();
}
```

This implementation is not thread-safe across threads. Use it only in sequential tests; if tests access it from multiple threads, guard the instant with `AtomicReference` or use a thread-safe test clock. In most unit tests, two fixed clocks are simpler.

### 2.4. Distinguishing `Instant`, `LocalDate`, and time zones

A common mistake is calling `LocalDateTime.now()` directly in business code. `LocalDateTime` carries no time zone or offset, so a value like `2026-11-12T08:00` does not identify an absolute instant without a zone.

For record creation times, token expirations, or event timestamps, prefer `Instant`:

```java
Instant createdAt = clock.instant();
```

For business dates in a specific region, pass an explicit `ZoneId`:

```java
LocalDate businessDate = LocalDate.now(clock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")));
```

Tests checking day rollovers or daylight saving time transitions should fix both the instant and the zone. Do not rely on the default time zone of a developer's machine or CI.

## 3. Injecting ID Generators

A service often needs IDs to create entities, events, or requests. If the service calls `UUID.randomUUID()` itself, tests cannot easily assert the exact ID attached to the object and passed through processing steps.

Create a small abstraction expressing the application's exact need:

```java
@FunctionalInterface
interface IdGenerator {
    UUID nextId();
}
```

Production implementation using random UUIDs:

```java
@Component
class UuidIdGenerator implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
```

Service depending on `IdGenerator`:

```java
@Service
class InvoiceService {
    private final IdGenerator idGenerator;
    private final Clock clock;
    private final InvoiceRepository invoices;

    InvoiceService(IdGenerator idGenerator,
                   Clock clock,
                   InvoiceRepository invoices) {
        this.idGenerator = idGenerator;
        this.clock = clock;
        this.invoices = invoices;
    }

    Invoice createInvoice(CustomerId customerId) {
        Invoice invoice = new Invoice(
                idGenerator.nextId(), customerId, clock.instant());
        return invoices.save(invoice);
    }
}
```

In unit tests, use a lambda because `IdGenerator` is a functional interface:

```java
@Test
void createsInvoiceWithGeneratedIdAndControlledTimestamp() {
    UUID expectedId = UUID.fromString(
            "123e4567-e89b-12d3-a456-426614174000");
    Instant expectedTime = Instant.parse("2026-11-12T08:30:00Z");
    IdGenerator ids = () -> expectedId;
    Clock clock = Clock.fixed(expectedTime, ZoneOffset.UTC);
    InvoiceRepository repository = new InMemoryInvoiceRepository();
    InvoiceService service = new InvoiceService(ids, clock, repository);

    Invoice invoice = service.createInvoice(new CustomerId("customer-7"));

    assertThat(invoice.id()).isEqualTo(expectedId);
    assertThat(invoice.createdAt()).isEqualTo(expectedTime);
    assertThat(repository.findById(expectedId)).contains(invoice);
}
```

The example uses an in-memory repository to illustrate controlling dependencies; in real tests, you can use a fake matching the repository contract or a mock if the goal is verifying calls. The key point is that the test chooses the ID and timestamp, so assertions do not depend on random UUID generation.

### 3.1. Using Mockito or a sequential ID generator

If a service calls the ID generator multiple times, Mockito can return IDs in sequence:

```java
UUID firstId = UUID.fromString("123e4567-e89b-12d3-a456-426614174001");
UUID secondId = UUID.fromString("123e4567-e89b-12d3-a456-426614174002");

when(idGenerator.nextId()).thenReturn(firstId, secondId);
```

Or write a small queue-backed fake so each call clearly receives its expected value:

```java
final class SequenceIdGenerator implements IdGenerator {
    private final Queue<UUID> ids;

    SequenceIdGenerator(UUID... ids) {
        this.ids = new ArrayDeque<>(List.of(ids));
    }

    @Override
    public UUID nextId() {
        UUID next = ids.poll();
        if (next == null) {
            throw new IllegalStateException("No test ID configured");
        }
        return next;
    }
}
```

The fake fails loudly if code calls it more times than expected. Avoid silently generating real UUIDs when the queue runs dry, as that returns the test to non-determinism and masks an unexpected interaction.

### 3.2. Database-generated IDs

Not all IDs are created by the service. When the database or persistence provider generates IDs, let repository integration tests verify mappings and ID persistence/retrieval. Service unit tests do not need to simulate database sequences if the service does not own ID generation.

Keep the distinction clear:

- Business IDs created by the service: inject `IdGenerator` and assert the ID passed into entities or events.
- Database-generated IDs: verify via persistence tests against an appropriate database.
- IDs issued by external systems: model the corresponding client/port and simulate responses in unit tests.

Do not claim a specific UUID is unique simply because a test used a fixed value. The test verifies ID propagation and storage, whereas uniqueness of the real generator must be verified against the contract and generation mechanism in the target environment.

## 4. Controlling Randomness Sources

Random values can influence algorithm selection, retry delays, sampling, verification codes, or fixture data. If a service draws random numbers directly from a global API, tests struggle to force a particular branch.

One approach is injecting a narrow abstraction exposing only what the business rule needs:

```java
@FunctionalInterface
interface RandomIntSource {
    int nextInt(int origin, int bound);
}
```

The implementation for ordinary randomness can use `ThreadLocalRandom`:

```java
@Component
class ThreadLocalRandomIntSource implements RandomIntSource {
    @Override
    public int nextInt(int origin, int bound) {
        return ThreadLocalRandom.current().nextInt(origin, bound);
    }
}
```

The service knows only `RandomIntSource`, independent of how the implementation produces numbers:

```java
class RetryDelayPolicy {
    private final RandomIntSource random;

    RetryDelayPolicy(RandomIntSource random) {
        this.random = random;
    }

    Duration nextDelay() {
        int millis = random.nextInt(100, 501);
        return Duration.ofMillis(millis);
    }
}
```

In Java, `nextInt(origin, bound)` is inclusive of the lower bound and exclusive of the upper bound. Thus the example produces delays from 100 to 500 milliseconds. Unit tests can force the random source to return boundary values:

```java
@Test
void usesTheConfiguredMinimumDelay() {
    RetryDelayPolicy policy = new RetryDelayPolicy((origin, bound) -> origin);

    assertThat(policy.nextDelay()).isEqualTo(Duration.ofMillis(100));
}

@Test
void usesTheLargestAllowedDelay() {
    RetryDelayPolicy policy = new RetryDelayPolicy((origin, bound) -> bound - 1);

    assertThat(policy.nextDelay()).isEqualTo(Duration.ofMillis(500));
}
```

The fake returns the exact chosen value, keeping the test focused on how the service handles it. If you want to verify the random source was called with the right bounds, use Mockito `verify` or a fake that records `origin` and `bound`.

### 4.1. Using a fixed seed for algorithms needing random sequences

When a reproducible sequence of pseudo-random values is needed, use a pseudo-random generator with a fixed seed. `java.util.Random` works well for simple cases and implements `java.util.random.RandomGenerator` on Java 17 and later:

```java
Random random = new Random(20261112L);

int first = random.nextInt(100);
int second = random.nextInt(100);
```

With the same implementation and seed, the `Random` sequence is reproducible. This is helpful when testing algorithms over many values or generating repeatable fixtures. Record the seed explicitly in the test so readers can reproduce the scenario.

Do not use a single fixed seed to claim an algorithm achieves proper random distribution. Seeded tests check one concrete input sequence. Checking statistical properties requires large sample sizes, appropriate statistical criteria, and flakiness control; that belongs to a separate kind of test.

If the application uses `RandomGenerator` from Java 17, you can inject that interface and pass a deterministic generator in unit tests:

```java
RandomGenerator random = new Random(20261112L);
```

Do not assume every `RandomGenerator` implementation is thread-safe. If a generator is a shared singleton in Spring invoked concurrently, pick a concurrency-safe implementation or isolate the source per thread. In tests, giving each test its own generator prevents one test from consuming numbers meant for another.

### 4.2. Distinguishing pseudo-randomness from cryptographic randomness

`Random`, `ThreadLocalRandom`, and many other generators serve general simulation or ordinary selection purposes. They do not replace a cryptographic entropy source when creating password reset tokens, session secrets, API keys, or anti-guessing nonces.

For sensitive data that must be unpredictable, use `SecureRandom` or the security API recommended by your platform. Never swap `SecureRandom` for `new Random(seed)` in production just to make tests easier. Instead, route token creation through a dedicated interface and supply fixed token values in unit tests. Tests verify the token is used and propagated properly; the security properties of the implementation are verified separately.

Example:

```java
@FunctionalInterface
interface ResetTokenGenerator {
    String nextToken();
}

@Component
class SecureResetTokenGenerator implements ResetTokenGenerator {
    private final SecureRandom secureRandom = new SecureRandom();

    @Override
    public String nextToken() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
}
```

In unit tests, replace `ResetTokenGenerator` with `() -> "test-token-001"`. You do not need to call `SecureRandom` to check that the service stores the token, sets its expiration, or sends the reset link to the right address.

## 5. Organizing Dependencies in a Spring Application

These dependencies can be supplied via constructor injection like any other component. For example, `Clock` is declared as a configuration bean, while `IdGenerator` and `RandomIntSource` have `@Component` implementations:

```java
@Configuration
class RuntimeDependencyConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}

@Component
class UuidIdGenerator implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
```

A service receives the needed dependencies via constructor:

```java
@Service
class VerificationService {
    private final Clock clock;
    private final IdGenerator ids;
    private final ResetTokenGenerator tokens;

    VerificationService(Clock clock,
                        IdGenerator ids,
                        ResetTokenGenerator tokens) {
        this.clock = clock;
        this.ids = ids;
        this.tokens = tokens;
    }

    VerificationRequest createRequest() {
        return new VerificationRequest(ids.nextId(), tokens.nextToken(),
                clock.instant());
    }
}
```

Unit tests can instantiate the service directly with fixed dependencies without booting Spring:

```java
@Test
void createsRequestWithControlledValues() {
    Instant now = Instant.parse("2026-11-12T08:30:00Z");
    UUID id = UUID.fromString("123e4567-e89b-12d3-a456-426614174010");

    VerificationService service = new VerificationService(
            Clock.fixed(now, ZoneOffset.UTC),
            () -> id,
            () -> "test-token-001");

    VerificationRequest request = service.createRequest();

    assertThat(request.id()).isEqualTo(id);
    assertThat(request.token()).isEqualTo("test-token-001");
    assertThat(request.createdAt()).isEqualTo(now);
}
```

Constructor injection makes the varying sources a service depends on explicit. It also saves unit tests from mocking the entire Spring container. Use `@SpringBootTest` or test slices only when the goal is verifying bean wiring, configuration, or cross-component integration.

### 5.1. Replacing dependencies in Spring integration tests

When you need to verify Spring wiring with a fixed clock, provide an override bean in the test context using `@TestConfiguration` and `@Primary`:

```java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class SubscriptionIntegrationTest {
    @Autowired
    private SubscriptionService subscriptions;

    @Test
    void recordsTheConfiguredInstant() {
        // Verify integration behavior at the fixed instant.
    }
}

@TestConfiguration
class FixedTimeTestConfiguration {
    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
    }
}
```

This is how beans are overridden in a test context. If the application already defines multiple `Clock` beans, clarify qualifiers or primary policies to avoid ambiguous injection. Do not load the entire context just to test a simple time calculation; unit tests with `Clock.fixed` are much leaner.

Similarly, for ID or token generators, you can supply a `@Primary` test bean. Make sure test configurations never accidentally leak fixed fakes into production profiles. Keep test configurations under test sources and import them explicitly.

## 6. Testing Expirations, Retries, and Generated Data

Once input sources are controlled, tests can express boundary cases directly.

### 6.1. Timestamps and expirations

Suppose a service issues tokens with a 15-minute lifetime. The test must verify `expiresAt` is computed from the clock-supplied time:

```java
@Test
void setsTokenExpirationFromInjectedClock() {
    Instant now = Instant.parse("2026-11-12T08:30:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    TokenService service = new TokenService(clock, Duration.ofMinutes(15));

    Token token = service.issue();

    assertThat(token.createdAt()).isEqualTo(now);
    assertThat(token.expiresAt()).isEqualTo(now.plus(Duration.ofMinutes(15)));
}
```

The test never checks the machine's current clock. If logic truncates to start-of-day or converts time zones, add tests for time zones and timestamps near day boundaries.

### 6.2. Retry delays and jitter

Jitter spreads out retries so many clients do not hammer a service simultaneously. Unit tests should verify delay formulas and bounds using a controlled random source:

```java
@Test
void capsRetryJitterAtConfiguredMaximum() {
    RandomIntSource maximumValue = (origin, bound) -> bound - 1;
    RetryDelayPolicy policy = new RetryDelayPolicy(maximumValue);

    Duration delay = policy.nextDelay();

    assertThat(delay).isEqualTo(Duration.ofMillis(500));
}
```

Beyond the maximum, test the minimum, invalid-bound handling, and how jitter combines with base backoff. Do not call `Thread.sleep(delay)` in unit tests to wait out real retries; verify the computed delay or use a controllable scheduler/clock if testing scheduling itself.

### 6.3. IDs and events

If a service generates an ID and publishes an event, supply a fixed ID and verify the event carries that exact ID:

```java
UUID expectedId = UUID.fromString(
        "123e4567-e89b-12d3-a456-426614174020");
when(idGenerator.nextId()).thenReturn(expectedId);

service.createOrder(command);

ArgumentCaptor<OrderCreated> captor =
        ArgumentCaptor.forClass(OrderCreated.class);
verify(eventPublisher).publishEvent(captor.capture());
assertThat(captor.getValue().orderId()).isEqualTo(expectedId);
```

This verifies the ID crosses the boundary intact. The service unit test does not need to verify which algorithm generated the UUID.

## 7. Controlling Random Data in Test Fixtures

Some tests generate bulk data randomly to avoid manually typing many records. If each run produces different data, failures become hard to reproduce and read. Prefer explicit fixtures when the number of cases is small:

```java
Customer customer = new Customer(
        "customer-42", "Lan", "lan@example.test", LocalDate.of(1995, 4, 12));
```

Explicit fixtures immediately tell readers which values matter. For many cases, use a builder or factory that accepts a seed:

```java
final class CustomerFixtureFactory {
    private final Random random;

    CustomerFixtureFactory(long seed) {
        this.random = new Random(seed);
    }

    Customer nextCustomer(int index) {
        int age = 18 + random.nextInt(60);
        return new Customer(
                "customer-" + index,
                "Customer " + index,
                "customer" + index + "@example.test",
                LocalDate.of(2000, 1, 1).minusYears(age));
    }
}
```

When a test fails, the seed and index recreate the same fixture sequence. Still, random data must never obscure test conditions. When testing blank emails, negative amounts, or boundary dates, write those exact values explicitly rather than hoping a generator happens to produce them.

Do not use random data to check a property requiring exact values unless the test records the seed and failing input. A flaky test is harder to diagnose than one with a slightly longer, explicit fixture.

### 7.1. Property-based testing and failure replay seeds

Property-based testing generates many inputs to verify a general property, such as allocated parts always summing to the original total or a parser rejecting malformed strings. This is where randomized data shines.

To keep results inspectable:

- Pick a framework that logs the seed on failure.
- Preserve the seed and failing input case in CI reports.
- Use shrinking if supported by the framework to reduce complex inputs to a minimal reproducible example.
- Separate property-based tests from explicit example-based unit tests so their purpose and runtime remain clear.

A fixed seed reproduces a generation sequence; it does not replace saving the failing input. When a framework supports seed-based replay, use the replay mechanism the framework provides.

## 8. Anti-Patterns to Avoid

### Do not read system time directly across multiple layers

If a service, entity factory, and helper each call `Instant.now()` independently, tests only control part of the flow. Pass the same `Clock` wherever time is needed so all operations share one reference point.

### Do not use `Thread.sleep` to make time pass

Sleeping slows tests down and depends on the OS scheduler. Use `Clock.fixed`, controllable clocks, or simulated schedulers to advance time without real waiting.

### Do not compare random IDs against uncontrollable literals

If the service creates the ID, inject a generator. If the database generates the ID, verify it at the persistence layer. Do not assume real UUIDs will match across runs.

### Do not share a stateful generator across multiple tests

If one test consumes several random numbers, the next test receives a different sequence. Give each test its own generator or reset with a known seed. Under parallel execution, avoid sharing mutable generators unless the implementation guarantees thread safety.

### Do not replace cryptographic randomness with pseudo-randomness

Authentication tokens, secrets, and unguessable values require a secure source like `SecureRandom`. Control the service in tests by replacing the token-generation abstraction rather than weakening the production implementation.

### Do not deep-mock JDK implementations

Instead of mocking `Instant.now()` or the static `UUID.randomUUID()` method, design dependencies at application boundaries: `Clock`, `IdGenerator`, `ResetTokenGenerator`, or `RandomIntSource`. Explicit dependencies are easier to read, rely less on static-mocking tools, and work cleanly in production too.

## 9. Workflow for Applying This to a Service

When encountering a service involving time, IDs, or randomness, follow this sequence:

1. Find direct calls such as `now()`, `randomUUID()`, `new Random()`, or `ThreadLocalRandom.current()`.
2. Determine whether the source affects business rules or assertions.
3. Choose the smallest abstraction: `Clock` for time, `IdGenerator` for IDs, a focused interface for tokens or random numbers.
4. Inject the dependency via constructor; supply an appropriate default implementation for production.
5. In unit tests, use fixed values, sequential fakes, or explicit seeds.
6. Test boundary cases: before/at/after deadlines, IDs propagated properly, random min/max bounds, and matching branches.
7. In Spring integration tests, override beans in the test context only when verifying wiring or integration behavior.

After refactoring, each test should create its own time, ID, and random sources. This avoids test-order dependencies and makes parallel test execution safer.

## 10. Tool Selection Table

| Need | Production | Unit Test |
|---|---|---|
| Current point in time | `Clock.systemUTC()` | `Clock.fixed()` |
| Advancing time in tests | Not needed in production | `Clock.offset()` or a controllable test clock |
| Application-generated UUIDs | `UUID.randomUUID()` inside `IdGenerator` | Lambda returning a fixed UUID or sequential fake |
| Database-generated IDs | Database/persistence ID mechanism | Repository integration test |
| Ordinary randomness | `ThreadLocalRandom` or load-appropriate generator | Fake returning deterministic values or seeded `Random` |
| Security tokens/secrets | `SecureRandom` behind token-generation abstraction | Fake generator returning fixed test tokens |
| Large fixture sets | Factory with clear data rules | Fixed seed, logging seed/failing input |

## 11. Key Principles to Remember

- Time, IDs, and random data are input sources that can make unit tests hard to repeat.
- Inject `Clock` instead of calling the system clock directly; `Clock.fixed()` enables exact time-boundary checks.
- Inject `IdGenerator` when the service owns ID creation; let database tests verify database-generated IDs.
- Use fakes or fixed seeds to control randomness; prefer explicit fixtures when a few concrete values suffice.
- Keep secure random sources like `SecureRandom` for tokens and secrets; never compromise security requirements just for test convenience.
- Each test should own its stateful dependency sources rather than relying on another test to consume or reset them.

When non-deterministic sources are turned into dependencies, tests can pick exact timestamps, IDs, and random values. This lets you verify business logic at boundaries, reproduce failures easily, and keep unit tests fast and reliable across every execution environment.
