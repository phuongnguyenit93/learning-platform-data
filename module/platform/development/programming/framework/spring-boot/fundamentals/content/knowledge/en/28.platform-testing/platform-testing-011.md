# Keeping Tests Independent of Execution Order and Unrelated External Services

A reliable Spring Boot test must yield the same outcome whether run **alone**, as part of the full suite, in a different execution order, or re-run on a clean CI machine. Its result must also never depend on whether an external service **unrelated to what is being tested** happens to be up or failing.

These are two closely linked forms of independence:

- **Order independence:** Test A does not need Test B to run beforehand to prepare state, and never leaks state into Test C.
- **Independence from out-of-scope infrastructure:** a unit test for pricing logic does not need a network, real database, SMTP server, payment system, or unrelated microservice started just to construct the object under test.

The goal is not eliminating integration tests altogether. The goal is **picking the right test boundaries**, keeping all inputs and side effects under control, and using real services only in tests genuinely meant to verify those integrations.

## 1. What makes a test independent?

Imagine running these commands:

~~~bash
./gradlew test --tests "*PricingServiceTest"
./gradlew test
~~~

If a test passes in the full suite yet fails when run alone, it may depend on state accidentally left behind by another test. If it passes alone yet occasionally fails in the full suite, tests may be sharing a database, cache, temp file, static field, or other shared resource.

An independent test sets up its own **preconditions**, executes the **behavior under test**, asserts the outcome, and **leaves no uncontrolled side effects** for other tests.

We can picture it as:

~~~text
Test A:
    Arrange A -> Act A -> Assert A -> Cleanup A

Test B:
    Arrange B -> Act B -> Assert B -> Cleanup B

Swapping the order of A and B does not change the result.
~~~

By contrast, an order-dependent design looks like:

~~~text
Test A: create user "alice" in shared database
Test B: look up user "alice" and update
Test C: delete user "alice"
~~~

If B only works after A and C must run after B, that is **a multi-step scenario split into three coupled tests**, not three independent tests.

If you want to verify a create → update → delete flow, execute all three steps inside **one test with its own fixture**, or write an explicit workflow integration test with isolated data and cleanup.

## 2. Common sources of flaky tests

Frequent root causes include:

| Dependency source | Example | Consequence |
|---|---|---|
| Static/global state | Shared `static` list | Later test reads data from earlier test |
| Shared database | Fixed entity with same ID/email | Key collision; tests fail when reordered |
| Shared cache | Test A writes cache, B expects empty cache | Assertions depend on order |
| Mutable singleton bean | Counter or map held inside Spring context | State leaks between test methods |
| Filesystem | Multiple tests writing `/tmp/report.csv` | Tests overwrite each other's files |
| System clock | Comparing directly against `Instant.now()` | Tests fail by timing or timezone |
| Random/UUID | Fixed expectations on random inputs | Results hard to reproduce |
| Async threads | Using `Thread.sleep(...)` to wait | Fails on slow CI runners |
| Network services | Third-party API, SMTP, Redis out of test scope | Fails due to DNS, ports, credentials, downtime |
| Environment config | Relying on one machine's env vars | Fails on other machines |

Some shared data is harmless, such as immutable constants. Problems come from **mutable state and preconditions not owned by the test itself**.

Independent tests do not automatically imply every test must run in parallel right away. However, once tests are genuinely independent, reordering or scaling to parallel execution becomes far safer.

## 3. Designing services with explicit dependencies

To enable unit testing without booting a Spring context or calling external services, expose collaborators as constructor dependencies.

Suppose an application has a booking service with these responsibilities:

1. Validate customer ID and room code.
2. Query a port to check whether the room is available.
3. Build a booking record with the current timestamp.
4. Save via a repository.
5. Return the result.

Some steps touch a database or remote service in production, yet unit tests only need **simulated outputs from those ports**.

~~~java
package com.example.booking;

public interface RoomAvailabilityPort {
    boolean isAvailable(String roomCode);
}
~~~

~~~java
package com.example.booking;

public interface BookingRepository {
    Booking save(Booking booking);
}
~~~

~~~java
package com.example.booking;

import java.time.Instant;

public record Booking(
        String customerId,
        String roomCode,
        Instant createdAt
) {
}
~~~

Service using constructor injection:

~~~java
package com.example.booking;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    private final RoomAvailabilityPort availability;
    private final BookingRepository repository;
    private final Clock clock;

    public BookingService(
            RoomAvailabilityPort availability,
            BookingRepository repository,
            Clock clock) {
        this.availability = Objects.requireNonNull(availability);
        this.repository = Objects.requireNonNull(repository);
        this.clock = Objects.requireNonNull(clock);
    }

    public Booking book(String customerId, String roomCode) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (roomCode == null || roomCode.isBlank()) {
            throw new IllegalArgumentException("roomCode is required");
        }

        if (!availability.isAvailable(roomCode)) {
            throw new IllegalStateException("room is unavailable");
        }

        Booking booking = new Booking(
                customerId,
                roomCode,
                Instant.now(clock)
        );

        return repository.save(booking);
    }
}
~~~

The service does not know whether `RoomAvailabilityPort` uses HTTP or a database. This forms a **test boundary**: booking decision logic is tested independently, while the adapter calling the remote API is tested in a separate integration or contract test.

## 4. Pure unit tests with JUnit Jupiter and Mockito

With Spring Boot, test suites commonly use `spring-boot-starter-test`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

A unit test class can use Mockito Extension without `@SpringBootTest`:

~~~java
package com.example.booking;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class BookingServiceTest {

    @Mock
    RoomAvailabilityPort availability;

    @Mock
    BookingRepository repository;

    BookingService service;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        service = new BookingService(
                availability,
                repository,
                clock
        );
    }

    @Test
    void booksAvailableRoom() {
        when(availability.isAvailable("A101")).thenReturn(true);
        when(repository.save(any(Booking.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Booking result = service.book("customer-1", "A101");

        assertEquals("customer-1", result.customerId());
        assertEquals("A101", result.roomCode());
        assertEquals(
                Instant.parse("2026-01-01T00:00:00Z"),
                result.createdAt()
        );

        verify(availability).isAvailable("A101");
        verify(repository).save(result);
    }

    @Test
    void rejectsUnavailableRoomWithoutSaving() {
        when(availability.isAvailable("A101")).thenReturn(false);

        assertThrows(
                IllegalStateException.class,
                () -> service.book("customer-1", "A101")
        );

        verify(availability).isAvailable("A101");
        verify(repository, never()).save(any(Booking.class));
    }

    @Test
    void rejectsBlankCustomerBeforeCallingDependencies() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.book("  ", "A101")
        );

        verifyNoInteractions(availability, repository);
    }
}
~~~

Characteristics of this suite:

- `BookingService` is a real object instantiated via `new`.
- Collaborators are Mockito mocks fresh per test.
- `Clock.fixed(...)` replaces the system clock.
- No `ApplicationContext` is booted.
- No HTTP or database connections occur.
- Each test configures only the stubbing needed for its branch.

`rejectsUnavailableRoomWithoutSaving` does not require `booksAvailableRoom` to run first; both build their own inputs and dependency behavior.

### Never mock the object under test itself

If you write:

~~~java
BookingService service = mock(BookingService.class);
when(service.book("customer-1", "A101"))
        .thenReturn(expectedBooking);
~~~

the test only verifies outcomes scripted into Mockito, testing nothing inside `BookingService`. Mock collaborators, never the SUT in its own unit tests.

## 5. Fixtures must be owned by each test

JUnit Jupiter provides `@BeforeEach` and `@BeforeAll`, with distinct purposes.

| Mechanism | When it runs | What to prepare |
|---|---|---|
| `@BeforeEach` | Before each test method | Mutable objects, per-test fixtures, mocks, single-test state |
| `@AfterEach` | After each test method | Cleanup of test-specific resources |
| `@BeforeAll` | Once before all tests in the class | Immutable setup or explicitly managed shared infrastructure |
| `@AfterAll` | Once after all tests in the class | Teardown of class-owned shared infrastructure |

Bad example:

~~~java
static final List<String> processed = new ArrayList<>();

@Test
void testA() {
    processed.add("A");
    assertEquals(1, processed.size());
}

@Test
void testB() {
    processed.add("B");
    assertEquals(1, processed.size());
}
~~~

This class fails to isolate state: `processed` is a shared list. Running A then B leaves B seeing two items. Reordering causes A to fail.

A proper approach creates a fresh list for each test:

~~~java
private List<String> processed;

@BeforeEach
void setUp() {
    processed = new ArrayList<>();
}
~~~

Even better, declare the list locally inside each test if sharing a fixture is unnecessary.

### Does @TestInstance(PER_CLASS) make tests more independent?

No. JUnit Jupiter by default creates a fresh test class instance per test method. Choosing `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` shares instance fields across methods on the same test object.

`PER_CLASS` has specific use cases, yet makes state leaks across test methods easier. If used, take extra care to avoid shared mutable fields or reset them before every test.

## 6. Do not use test ordering to hide state leaks

JUnit lets you order tests using `@TestMethodOrder` and `@Order`:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class OrderedWorkflowTest {

    @Test
    @Order(1)
    void create() {
        // ...
    }

    @Test
    @Order(2)
    void update() {
        // ...
    }
}
~~~

However, **controlling order is not a default fix** for tests that ought to be independent. If `update()` only succeeds after `create()`, adding `@Order` hides a hidden dependency inside what looks like two independent test cases.

A better structure for a workflow:

~~~java
@Test
void createsThenUpdatesBooking() {
    // Arrange: create dedicated data for this test

    // Act: create booking, then update booking

    // Assert: verify final state

    // Cleanup: managed within test scope
}
~~~

When multiple steps genuinely form one scenario, a single test with an explicit internal sequence makes sense. Meanwhile, individual `@Test` methods checking independent rules should never require `@Order`.

Also never assume JUnit always runs methods in source-file order. Running a single test, IDE runners, Gradle, Maven, parallel execution, or test engine settings can all alter execution order.

## 7. Tests must not depend on unrelated external services

Suppose a shipping-fee service has a `@SpringBootTest` that boots the entire application. Inside `ApplicationContext`, there are also:

- An email adapter connecting to SMTP during bean creation.
- A payment client validating a token at startup.
- A message broker consumer requiring Kafka.
- A Redis client or analytics scheduler.
- An external config client calling an internal API.

If the email server goes down temporarily, the shipping-fee test fails **before ever reaching the calculation method**, even though the logic under test never touches email.

That is an **overly broad context scope** bug. Why should a pricing test depend on SMTP?

Prioritized fixes:

1. For pure-logic unit tests, **do not boot Spring**; instantiate the SUT via constructor.
2. For tests needing only a web or data slice, use the right **test slice**.
3. If a Spring context is needed without external adapters, use **fakes/mocks or configurations excluding unrelated integrations**.
4. Use real services only in tests specifically meant to verify those integrations.

Never work around this by raising timeouts, adding endless retries, or making CI "wait for unrelated services to stabilize" when those services have nothing to do with the behavior under test.

## 8. How does @SpringBootTest differ from unit tests?

`@SpringBootTest` builds a Spring `ApplicationContext` with relatively complete application configuration. It is a powerful tool for testing bean wiring, AOP, configuration, and integration.

Example:

~~~java
@SpringBootTest
class ApplicationWiringTest {

    @Autowired
    BookingService service;

    @Test
    void contextProvidesBookingService() {
        assertNotNull(service);
    }
}
~~~

This test verifies Spring can create and inject `BookingService`. That differs from unit tests verifying branches of `book(...)`.

If the app auto-configures dozens of integrations, booting a broad context pulls in out-of-scope dependencies. Distinguish clearly:

- **Unit test:** tests `BookingService` logic using mocks/fakes.
- **Context test:** verifies beans are created and wired properly.
- **Integration test:** verifies adapters connect properly to databases, HTTP services, or brokers.
- **End-to-end test:** verifies flows traversing multiple real components.

Not every test file in a Spring Boot project belongs under `@SpringBootTest`.

## 9. Use test slices instead of loading the entire application

Spring Boot provides test slices to initialize only the relevant portion of infrastructure.

Common examples:

| Goal | Tool | Usually omitted |
|---|---|---|
| Controller HTTP mapping, serialization, validation | `@WebMvcTest` | Full repositories / databases |
| JPA entities and repositories | `@DataJpaTest` | Web server, mail senders |
| JSON serialization | `@JsonTest` | Business integrations |
| JDBC repositories | `@JdbcTest` | Controllers, remote APIs |
| Service unit logic | JUnit + Mockito | Entire Spring context |

With `@WebMvcTest`, controller collaborators are typically replaced with mocks to focus on mapping, request/response handling, and web logic. Spring Security rules or filters can still participate depending on slice setup, so do not assume slices skip every non-web piece automatically.

Example using Spring Framework 6.2+ with `@MockitoBean`:

~~~java
@WebMvcTest(BookingController.class)
class BookingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookingService bookingService;

    @Test
    void returnsBookingResponse() throws Exception {
        // Stub service, invoke request via MockMvc, assert response.
    }
}
~~~

Typical imports:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
~~~

In older Spring Boot projects, you will encounter Spring Boot Test's `@MockBean`. Match the annotation to **your project's Spring Framework and Spring Boot version** rather than mixing mechanisms arbitrarily.

A test slice is only worthwhile when testing slice mechanics. If you are only invoking `BookingService.book(...)` and asserting the result, a direct unit test is simpler.

## 10. TestContext caching: faster, yet can hide state leaks

Spring Test Framework normally **caches `ApplicationContext` instances** so tests sharing matching configurations reuse contexts without repeatedly rebooting Spring.

This is a helpful optimization, with important consequences:

- Mutable singleton beans retain state if tests modify them directly.
- Application caches may hold entries from earlier tests.
- Enabled schedulers or background workers keep running.
- Context-level mocks must be reset per lifecycle.
- External storage like databases or files persists even if contexts recreate.

Example of a bean holding a counter in a field:

~~~java
@Component
public class RequestCounter {

    private int value;

    public void increment() {
        value++;
    }

    public int value() {
        return value;
    }
}
~~~

If Test A increments and Test B expects 0 on the same singleton, execution order alters results.

Appropriate solutions by goal:

- If only testing counter logic, instantiate separate objects in unit tests without Spring.
- If a Spring context is required, actively reset fixtures owned by each test.
- If a bean holds real application state, consider backing it with a repository/cache with clear lifecycle rather than an ad-hoc mutable singleton.
- If each test genuinely requires a brand-new context, consider `@DirtiesContext` while accounting for cost.

### @DirtiesContext: last resort, not the default

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class SpecialContextMutationTest {
    // Test modifies configuration or bean state at the context level.
}
~~~

`@DirtiesContext` marks the context unfit for reuse. Spring removes it from cache and rebuilds it when needed by other tests.

This is warranted when a test intentionally alters the environment or context structure. However, scattering `@DirtiesContext` everywhere forces repeated Spring restarts and often **masks underlying state leaks**. It also does not clean databases or files outside `ApplicationContext`.

## 11. Isolating database data between tests

When the goal is genuinely testing persistence, a database or compatible solution is needed. Tests must still create their own isolated data.

Poor example:

~~~java
@Test
void findsAccount() {
    Account account = repository.findByEmail("admin@example.test")
            .orElseThrow();

    assertEquals("ADMIN", account.role());
}
~~~

This test assumes the database already holds `admin@example.test`—perhaps from migrations, environment setup, or another test. When preconditions aren't fixtures owned by the test itself, outcomes become unpredictable.

Better:

~~~java
@Test
void findsAccount() {
    Account saved = repository.save(
            new Account("test-user-42@example.test", "ADMIN")
    );

    Account found = repository.findById(saved.getId())
            .orElseThrow();

    assertEquals("ADMIN", found.getRole());
}
~~~

This is illustrative structure; constructors and entity mappings depend on your project's model. When multiple tests share a database, use unique data/IDs per test, appropriate transaction rollback, or isolated databases/schemas.

### @Transactional test rollback has limits

In integration tests using Spring TestContext, a test method annotated with `@Transactional` typically runs inside a **test-managed transaction** and rolls back by default afterward:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    AccountRepository repository;

    @Test
    void savesAndLoadsAccount() {
        // Test data is managed within the test transaction.
    }
}
~~~

`@DataJpaTest` normally configures transactions for persistence tests in suitable environments. Keep in mind:

- Data written in another transaction may not roll back with the test's transaction.
- Side effects outside the database—files, messages, emails—never roll back.
- With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP requests run on a different thread/transaction than the test thread.
- If application code explicitly commits in an independent transaction, test rollback does not revert it.

Therefore, never assume adding `@Transactional` automatically keeps every integration test clean.

### Avoiding collisions during parallel runs

Do not share a hardcoded email like `test@example.test` across concurrent tests if the DB enforces a unique constraint. Generate distinct IDs per case and clean up purposefully.

Avoid using randomness solely to hide bugs without keeping reproducibility info. When generating dynamic data, log the ID on failure or use a seeded repeatable generator.

## 12. Using Testcontainers when integration needs real infrastructure

When verifying repositories against the exact database engine used in production, an ephemeral database inside a container fits far better than a shared static database.

Testcontainers lets tests own the lifecycle of test dependencies, such as a PostgreSQL container:

```text
Integration test
       |
       +--> Test-dedicated PostgreSQL container
       |
       +--> Spring application / repository
       |
       v
   Assertions
       |
       v
   Lifecycle-managed cleanup
```

Advantages:

- Reduces reliance on databases pre-installed on developer machines.
- Pins exact service versions reliably in CI.
- Eliminates risk of touching real data.
- Reproducible environment configuration.

Still, Testcontainers does not turn a test into a unit test. It remains an integration test requiring container runtime, startup time, and data management.

If a test checks only calculation logic and needs no SQL, **never start a PostgreSQL container** for it. Less infrastructure means clearer failure boundaries.

## 13. HTTP services: mocks/fakes in unit tests, mock servers in adapter tests

In `BookingService` unit tests, `RoomAvailabilityPort` is mocked. No real HTTP request occurs.

When writing the real adapter:

~~~java
@Component
public class HttpRoomAvailabilityAdapter
        implements RoomAvailabilityPort {

    // Use configured RestClient/WebClient.
    // Convert HTTP response to boolean.
}
~~~

we introduce new test goals: URL, HTTP method, JSON mapping, status codes, timeouts, and error handling.

Appropriate tools then include:

- A local mock HTTP server on a dynamic port.
- `MockRestServiceServer` with supported Spring clients.
- WireMock or MockWebServer in an appropriately configured integration test.
- Contract tests verifying adapter requests and responses.

The principle is that adapter tests **create and control a simulation of the service they call**, never hitting production APIs or shared mutable staging endpoints.

For instance, a service unit test should never require:

~~~yaml
room:
  service:
    url: https://real-availability.example.test
~~~

Calling live endpoints makes tests fail due to DNS, TLS certificates, rate limits, or maintenance with zero business bugs in the service.

### Mocking the endpoint does not verify the HTTP contract

Mocking `RoomAvailabilityPort` tests only coordination logic. It does not prove the adapter sends the right headers, parses JSON properly, or stays compatible with the remote API.

Dedicate separate tests to adapters and contracts; do not force unit tests to make external calls just to feel "more realistic."

## 14. Preventing unrelated infrastructure from connecting at startup

Even in integration tests, Spring initializing an unneeded bean can couple tests to external services.

Consider a component with:

~~~java
@PostConstruct
public void initialize() {
    remoteClient.connect();
}
~~~

If that bean is built inside `@SpringBootTest`, the test fails at startup even when never invoking that component's features.

Better design options:

1. **Narrow context scope:** if the test does not need the bean, use a test slice or focused context configuration.
2. **Decouple adapters from business services:** inject interfaces and swap adapters for fakes/mocks when the integration is out of scope.
3. **Defer connection until actual use:** avoid unnecessary network calls inside constructors or `@PostConstruct`.
4. **Conditional registration:** where business rules allow, gate integration beans by property/profile and disable them cleanly in tests.
5. **Configure test dependencies:** if the test needs the context and bean without live networking, supply a deterministic test implementation.

Example conditional adapter registration:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "external.notifications",
            name = "enabled",
            havingValue = "true"
    )
    NotificationClient notificationClient() {
        return new NotificationClient();
    }
}
~~~

This illustrates the pattern: if disabling a bean, dependent components must also be configured not to require it unconditionally. Do not simply add a flag that causes missing-dependency crashes at context startup.

Also remember a test might not use integration X in business logic while application auto-configuration still tries to boot X. Pinpoint the exact bean or auto-configuration initiating the connection rather than provisioning every external service just to let tests boot.

## 15. Using dedicated test profiles and properties explicitly

For tests requiring a Spring context, you can declare:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationIntegrationTest {
    // ...
}
~~~

And provide `src/test/resources/application-test.yml`:

~~~yaml
external:
  notifications:
    enabled: false
  analytics:
    enabled: false

spring:
  task:
    scheduling:
      enabled: false
~~~

The properties in this example only take effect when the application or auto-configuration **actually honors those keys**. Never assume every custom scheduler turns off just because you set an arbitrary key; check the component's own configuration logic.

Test-specific overrides can also be inline:

~~~java
@SpringBootTest(properties = {
        "external.notifications.enabled=false",
        "external.analytics.enabled=false"
})
class ShippingApplicationTest {
}
~~~

Another option is `@TestPropertySource` when needing dedicated test property sources.

**Do not treat the `test` profile as an unconditional kill switch.** If production fails to boot due to broken bean wiring, a test profile disabling too many components masks the defect. Use profiles/properties to control out-of-scope integrations while keeping dedicated wiring/integration tests for critical integrations.

## 16. Making time, timezones, and randomness controllable

Tests relying on the system clock often flake around midnight, across timezones, or across CI speeds.

Flaky example:

~~~java
LocalDate today = LocalDate.now();
assertEquals(today, service.expiryDate());
~~~

Midnight can pass between the two calls, or the service may use a different timezone.

Inject `Clock` instead:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-03-01T12:00:00Z"),
        ZoneOffset.UTC
);
~~~

Service uses:

~~~java
Instant createdAt = Instant.now(clock);
~~~

Tests assert exact values on `createdAt` regardless of when they run.

Similarly for random IDs:

~~~java
public interface BookingIdGenerator {
    String nextId();
}
~~~

In tests, the generator returns `"booking-123"`. In production, the implementation can use UUIDs.

Not every computation needs an abstract interface. Introduce seams only where nondeterminism or infrastructure dependencies would otherwise make tests non-repeatable.

## 17. File resources must have isolated scopes

If two tests write to the same filename:

~~~text
/tmp/booking-report.csv
~~~

one test can overwrite or delete the other's data. Under parallel runs, this becomes even harder to control.

JUnit Jupiter provides `@TempDir` to create a dedicated temporary directory per test:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportWriterTest {

    @TempDir
    Path tempDir;

    @Test
    void writesReport() throws Exception {
        Path output = tempDir.resolve("report.txt");

        Files.writeString(output, "completed");

        assertEquals("completed", Files.readString(output));
    }
}
~~~

Each test owns its own path. JUnit handles cleanup per lifecycle, avoiding cross-test interference.

If production code hardcodes a file path inside its implementation, swapping paths in tests is difficult—a sign to inject a path or storage abstraction via constructor rather than hardcoding it.

## 18. Testing async code: await conditions, never guess durations

An anti-pattern:

~~~java
service.startAsyncWork();
Thread.sleep(500);
assertEquals("DONE", repository.getStatus());
~~~

`Thread.sleep(500)` does not guarantee the work finished: slow CI runners may take longer than 500 ms, while fast machines waste time sleeping. It also hides exceptions thrown on background threads.

Make async work observable instead:

- Return a `CompletableFuture` and wait with a bounded timeout.
- Inject a controllable executor in unit tests.
- Poll an observable condition or use explicit synchronization in integration tests.
- Surface exceptions from futures instead of inspecting logs.

Example with a future:

~~~java
CompletableFuture<String> future = service.processAsync();

String result = future.get(2, TimeUnit.SECONDS);

assertEquals("DONE", result);
~~~

The timeout here is an **upper bound preventing tests from hanging forever**, not an assumption that the task always takes two seconds.

If code uses `@Async` and you want to verify the proxy or real executor, write an integration test of Spring's async infrastructure; unit tests for internal logic can execute synchronously using a controllable dependency or executor.

## 19. Parallel tests require explicit resource isolation

When enabling JUnit parallel execution or running multiple Gradle test workers, tests that only passed sequentially by luck reveal race conditions.

Common hazards:

- Updating shared static fields.
- Sharing a database/schema and fixed keys.
- Binding the same fixed TCP port.
- Writing to the same file.
- Mutating global system properties.
- Test A restarting or stopping a service Test B uses.
- Sharing a cache or message queue without isolated namespaces.

Do not solve every issue by permanently disabling parallel execution. Find unnecessary shared state and isolate it first.

When a resource **genuinely cannot be shared concurrently**, use synchronization mechanisms such as JUnit Jupiter's `@ResourceLock`. Yet locks do not solve Test B needing data prepared by Test A; they only serialize concurrent access.

If multiple tests require locks to mutate a single global state, consider refactoring test fixtures or redesigning the dependency.

## 20. Avoid uncontrolled changes to system properties and global environment

A test might do:

~~~java
System.setProperty("app.mode", "test");
~~~

`System.setProperty` mutates JVM-wide state. If not restored, subsequent tests read `app.mode=test` regardless of their own setup.

If mutating a system property is unavoidable, save the old value and restore it in `finally` or via a cleanup extension. In Spring Boot, however, passing properties through the test context is much cleaner:

~~~java
@SpringBootTest(properties = "app.mode=test")
class ModeIntegrationTest {
}
~~~

In unit tests, inject a configuration object or constructor argument instead of reading global system properties.

Process environment variables cannot be safely mutated per test within the same JVM either. Never design unit tests that require mutating OS environment variables while tests run.

## 21. CI and reproducing order-dependent failures

A well-isolated test suite runs reliably from the IDE, Gradle/Maven, and CI without requiring an "initializer test" first.

Diagnostic clues when failures appear:

- **Fails alone, passes in full suite:** missing fixture, relying on another test's setup.
- **Passes alone, fails in full suite:** leaking mutable state or resource collision.
- **Passes on developer machine, fails on CI:** relying on pre-installed services, local configs, timezone, paths, or timing.
- **Fails only in parallel:** race condition, fixed port, shared database keys, or concurrent global state mutations.
- **Fails when Service A stops even though Test B does not test A:** overly broad context or unrelated eager connection.

When diagnosing, capture test names, inputs, exceptions, property sources, and dependency states to find the root cause; never treat "rerun until green" as a long-term solution.

Gradle/Maven commands for running a subset of tests are helpful during development, such as:

~~~bash
./gradlew test --tests "*BookingServiceTest"
mvn -Dtest=BookingServiceTest test
~~~

These commands are merely study examples and do not change test design principles. An independent test must never need "run the whole suite first" to succeed.

## 22. Clearly distinguish three types of dependencies

When designing a test, separate:

| Category | Example | Typical handling |
|---|---|---|
| Direct business dependency | Service needs room availability | Mock/fake port in unit test; dedicated integration test for adapter |
| In-scope infrastructure | Repository test needs PostgreSQL | Provision isolated test DB with dedicated lifecycle and data |
| Unrelated external service | Pricing unit test triggering SMTP | Do not start or call SMTP; narrow context or swap bean |

The goal of unit testing is not pretending external services don't exist. It is verifying **the contract of a single unit of code** without dragging in factors outside that contract.

When a service integrates with many systems, constructor injection and port interfaces let tests control exactly what is simulated. In integration tests, scope may be broader, yet every active piece of infrastructure must belong to the test goal and have controlled state.

## 23. Workflow for designing an independent test

Follow this mental checklist whenever adding a Spring Boot test:

1. **Identify the unit under verification.** Is it service logic, an HTTP controller, a JPA repository, or an end-to-end flow?
2. **Choose the narrowest scope sufficient for the goal.** Unit tests need no Spring context; controllers and repositories can use slices.
3. **List all inputs.** Include data, clocks, randomness, configuration, and collaborator outputs.
4. **Build private fixtures.** Never rely on objects, rows, or side effects prepared by another test.
5. **Replace out-of-scope dependencies with mocks/fakes.** Never force unit tests to call real APIs, SMTP, brokers, or databases.
6. **Own required resources.** If an integration test needs a DB, container, or file, keep its lifecycle and data isolated.
7. **Assert observable outcomes.** Check return values, exceptions, and meaningful side effects without locking onto trivial internal details.
8. **Clean up or avoid global state.** Watch out for separate transactions, caches, static state, temp files, and background threads.
9. **Never use test order as a precondition.** Express multi-step workflows inside one scenario rather than chaining dependent tests.
10. **Control infrastructure at context startup.** If an unrelated adapter tries to connect over the network, narrow the context, swap the adapter, or remove eager connections.

The core principle is that **each test is responsible for its own preconditions and resources**. Constructor injection enables replacing collaborators with mocks or fakes; isolated fixtures eliminate order dependence; test slices and narrowed contexts keep unrelated external services from skewing outcomes. Integration tests requiring real infrastructure still play a vital role, cleanly separated by purpose with explicit data and lifecycle management.

When these principles hold, your Spring Boot test suite becomes readable, repeatable, and able to pinpoint defects in the exact behavior under test rather than reflecting leftover state from unrelated tests or services.
