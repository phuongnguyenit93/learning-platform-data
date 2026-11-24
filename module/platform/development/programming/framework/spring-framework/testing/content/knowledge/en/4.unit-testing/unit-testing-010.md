# Keeping Tests Fast and Independent of the Network

Unit tests deliver the most value when developers can run them frequently, receive results quickly, and trust that outcomes accurately reflect the code being changed. A test that has to call an API over the network, wait on a database, start a broker, or rely on a service running on another machine struggles to preserve those traits.

In Spring Framework Testing, the goal of unit testing is to verify the behavior of a unit of code within a controlled scope. That unit might be a calculation function, domain object, validator, policy, or application service. External dependencies are replaced with small, predictable implementations such as fakes, stubs, or mocks. That lets tests check the unit's decisions without opening network connections.

A fast, network-independent test suite helps you:

- Run tests continuously while writing code, before committing, and in CI.
- Produce consistent results unaffected by external service availability.
- Pinpoint failure causes close to the component just modified.
- Run tests in parallel without contention over shared data.
- Cut waiting time during development and debugging.

Network independence does not mean the application never uses HTTP, databases, or message brokers. It means **unit tests do not need those systems to prove the behavior of the unit under test**. Adapter and integration tests still verify communication with real systems at a separate layer.

## 1. Distinguishing Unit Tests from Tests Requiring Infrastructure

Start from the question the test needs to answer:

- Is a fee-calculation rule correct?
- Does a validator reject invalid data?
- Does an application service coordinate business steps in the right order?
- Does a repository save and read data properly against the database?
- Does an HTTP client send protocol-compliant requests and handle responses properly?

The first three questions can usually be answered with unit tests. The last two need to pass through the corresponding adapter or infrastructure.

~~~mermaid
flowchart TD
    A["What does the test need to verify?"] --> B{"Decision or rule of a single unit?"}
    B -->|"Yes"| C["Unit test"]
    C --> D["Instantiate object directly"]
    D --> E["Fake / Stub / Mock dependencies"]
    E --> F["No network calls, no infrastructure startup"]
    B -->|"No"| G{"Adapter or integration behavior?"}
    G -->|"Yes"| H["Adapter / Integration test"]
    H --> I["Mock HTTP server or real service"]
    I --> J["Verify protocol and interactions"]
~~~

For example, a service computing order totals might take line items and a port to fetch discount policies. Testing the service does not require calling the promotions system over HTTP. It only needs a fake returning a known policy to check how the service calculates totals.

Conversely, if the goal is verifying that an HTTP client constructs the right URL, headers, body, and handles status codes, a business-rule unit test is not enough. You need an adapter test against a mock HTTP server or suitable service. Adapter tests using local sockets also carry different cost and scope from pure unit tests.

## 2. Keeping the Unit Under Test Small and Passing Dependencies Directly

A unit test usually does not need to start a Spring ApplicationContext. If a class has a clear constructor and receives its dependencies as arguments, tests can instantiate the object using plain Java.

Example service applying a discount policy:

~~~java
import java.math.BigDecimal;

public interface DiscountPolicy {
    BigDecimal discountFor(String customerId);
}

public final class OrderTotalService {

    private final DiscountPolicy discountPolicy;

    public OrderTotalService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    public BigDecimal total(
            String customerId,
            BigDecimal subtotal
    ) {
        BigDecimal discount =
                discountPolicy.discountFor(customerId);

        return subtotal.subtract(discount);
    }
}
~~~

A test can pass a simple implementation:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderTotalServiceTest {

    @Test
    void subtractsDiscountFromSubtotal() {
        DiscountPolicy policy =
                customerId -> new BigDecimal("10000");

        OrderTotalService service =
                new OrderTotalService(policy);

        BigDecimal actual = service.total(
                "CUSTOMER-01",
                new BigDecimal("80000")
        );

        assertEquals(new BigDecimal("70000"), actual);
    }
}
~~~

This test creates no Spring context, touches no database, and opens no HTTP connections. It verifies only **OrderTotalService**'s calculation against a deterministic discount response.

If a class relies on field injection, static singletons, or constructs HTTP clients inside methods, tests struggle to substitute dependencies. You can improve the design with constructor injection or by routing external operations behind an interface. That does not mean creating abstractions for everything; you only need a clear boundary where code genuinely depends on external resources.

### When is Spring still needed?

When the behavior under test depends on Spring's own mechanisms—such as transaction proxies, method security, AOP, conditional beans, or dependency injection—a test must go through the Spring container. Those are container tests or scoped integration tests, not pure unit tests.

Do not use **@SpringBootTest** for every test merely because the production class is annotated with **@Service**. That annotation tells Spring to manage the bean in the application; it does not require every test of the class to boot the application.

Pure Java business rules can still be tested by instantiating objects directly. Reserve the Spring context for questions that genuinely verify Spring-provided behaviors.

## 3. Replacing Network Dependencies with Fakes, Stubs, or Mocks

Network dependencies include HTTP clients, vendor SDKs, repositories calling databases, message publishers, or gateways to other services. In unit tests, control dependency responses so tests stay focused on the unit's decisions.

### Stub: returning predefined data

A stub fits when a test needs a concrete response without verifying interaction details.

~~~java
public interface ExchangeRatePort {
    BigDecimal rate(String from, String to);
}
~~~

~~~java
@Test
void convertsUsingProvidedExchangeRate() {
    ExchangeRatePort rates =
            (from, to) -> new BigDecimal("25000");

    CurrencyConverter converter =
            new CurrencyConverter(rates);

    BigDecimal actual = converter.convert(
            new BigDecimal("2"),
            "USD",
            "VND"
    );

    assertEquals(new BigDecimal("50000"), actual);
}
~~~

Stubs make outcomes predictable. The test does not depend on live exchange rates, external service uptime, or the test runner's network.

### Fake: simulating behavior with a lightweight implementation

A fake holds in-memory state and implements part of a dependency's contract. For example, a fake repository can store entities in a Map to test an application service:

~~~java
public final class InMemoryCustomerRepository
        implements CustomerRepository {

    private final Map<String, Customer> customers =
            new HashMap<>();

    @Override
    public Optional<Customer> findById(String id) {
        return Optional.ofNullable(customers.get(id));
    }

    @Override
    public Customer save(Customer customer) {
        customers.put(customer.id(), customer);
        return customer;
    }
}
~~~

Fakes are helpful when tests involve multiple sequential operations, such as saving a customer and reading it back. However, a fake only simulates the contract it was written for. It does not prove real database SQL, transactions, indexes, or locking work properly.

### Mock: verifying a meaningful interaction

A mock fits when what needs verification is an important call, such as a service emitting a confirmation command when an order is confirmed.

~~~java
@Test
void publishesConfirmationAfterOrderIsConfirmed() {
    OrderEventPublisher publisher =
            mock(OrderEventPublisher.class);

    OrderConfirmationService service =
            new OrderConfirmationService(publisher);

    service.confirm(new OrderId("ORDER-01"));

    verify(publisher).publish(
            argThat(event ->
                    event.orderId().equals("ORDER-01"))
    );
}
~~~

The snippet above illustrates interaction verification with Mockito. Declare the required imports and Mockito setup in the project. Verify only interactions belonging to the contract under protection; if a test asserts every internal call, it turns brittle when implementations are refactored.

| Technique | What It Provides | When to Use |
|---|---|---|
| Stub | Fixed responses | Need to control inputs coming from a dependency |
| Fake | Simple, usually stateful behavior | Need multi-step interactions in memory |
| Mock | Records and verifies calls | An interaction itself is the outcome to verify |

All three approaches keep unit tests network-independent as long as they open no real connections. Do not confuse a mock object with a mock HTTP server: mocking a client interface does not create a server speaking the HTTP protocol.

## 4. Avoiding Sources That Make Tests Slow or Environment-Dependent

The network is one cause of slowness and flakiness, yet not the only one. A unit test can also become hard to repeat when it depends on current time, random numbers, shared state, or external files.

### Do not call real HTTP endpoints or SDKs in unit tests

Never let tests call a public API, staging service, internal API, or an SDK connecting out to the Internet. Failures can happen even when code hasn't changed:

- DNS fails to resolve domain names.
- Corporate network, VPN, or proxy is unavailable.
- External service is under maintenance or rate-limiting.
- Tokens expire or permissions change.
- Responses vary by data, time of day, or account state.
- Requests take long due to timeouts or retries.

Instead of calling real services, hide the operation behind an interface and supply stubs/fakes in unit tests. Dedicated adapter tests verify requests/responses against a mock server when needed.

### Do not use a real database to test pure rules

A test checking calculations or business decisions needs no database connection. If a service reads a value from a repository, pass a fake returning deterministic data.

Database tests remain necessary to verify mappings, queries, and transactions. Place them in an appropriate test group and let unit tests run independently of that group.

### Do not use current system time directly

Code calling **LocalDate.now()**, **Instant.now()**, or **System.currentTimeMillis()** can return different results depending on when it runs. Tests executing near midnight, across time zones, or across day boundaries can fail unpredictably.

Pass **Clock** into components that need the time:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class SubscriptionService {

    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(LocalDate expiryDate) {
        LocalDate today = LocalDate.now(clock);
        return expiryDate.isBefore(today);
    }
}
~~~

Tests can fix time:

~~~java
@Test
void treatsYesterdayAsExpired() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-12T00:00:00Z"),
            ZoneId.of("UTC")
    );

    SubscriptionService service =
            new SubscriptionService(clock);

    assertTrue(service.isExpired(
            LocalDate.of(2026, 11, 11)
    ));
}
~~~

When time is controlled, tests do not rely on the machine's clock or run date. For time-zone-sensitive rules, specify ZoneId explicitly instead of relying on the machine's default time zone.

### Do not depend on uncontrolled random numbers

If code generates UUIDs, random numbers, or reference codes, results can change on every run. When that value affects a decision under test, pass a supplier or generator via constructor so tests supply fixed values.

For instance, instead of calling a random generator directly inside the service, declare a small interface for issuing IDs. Unit tests pass an implementation returning a known ID. The test still verifies the ID is used properly without guessing random values.

### Do not rely on shared state

One test should never depend on data created by another test. Avoid static mutable state, singletons holding test data, shared directories accumulating files, or test execution ordering.

Each test must build its own fixtures and clean up its own state. Under parallel execution, each test needs isolated data so tests never overwrite or accidentally read one another's results.

## 5. Designing Boundaries So Unit Tests Never Accidentally Open the Network

A common cause of network-dependent tests is code constructing clients inside business components. Tests then have nowhere to swap out the dependency.

Hard-to-isolate example:

~~~java
public final class WeatherService {

    public String forecast(String city) {
        var client = HttpClient.newHttpClient();
        // Send a real request to the weather service
        // and parse the response here.
        return "sunny";
    }
}
~~~

Even when result processing is tiny, the method owns both client creation and network communication. Unit tests invoking the method can inadvertently send real requests.

Extract the operation to a port:

~~~java
public interface WeatherGateway {
    WeatherForecast fetch(String city);
}

public final class WeatherService {

    private final WeatherGateway gateway;

    public WeatherService(WeatherGateway gateway) {
        this.gateway = gateway;
    }

    public WeatherForecast forecast(String city) {
        WeatherForecast forecast = gateway.fetch(city);

        if (forecast == null) {
            throw new IllegalStateException(
                    "Weather forecast is unavailable"
            );
        }

        return forecast;
    }
}
~~~

Unit tests pass a fake or stub for **WeatherGateway**:

~~~java
@Test
void returnsForecastFromGateway() {
    WeatherGateway gateway = city ->
            new WeatherForecast(city, "SUNNY");

    WeatherService service = new WeatherService(gateway);

    WeatherForecast actual = service.forecast("Hanoi");

    assertEquals("SUNNY", actual.condition());
}
~~~

The real implementation of **WeatherGateway** uses an HTTP client. That adapter is tested separately to check request construction, status handling, timeouts, and response conversion. This separation creates two independent questions:

- Does **WeatherService** handle forecasts according to business rules?
- Does the HTTP adapter communicate properly with the weather service?

A unit test needs no real URLs, API keys, or provider response payloads. Those details belong to the adapter.

### Constructor injection creates explicit substitution points

In Spring applications, constructor injection is a clean way to supply dependencies and make what a class needs explicit:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult pay(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

At runtime, Spring injects the real **PaymentGateway** implementation. In unit tests, the test passes a fake or mock. There is no need to boot Spring to test how **PaymentService** handles gateway outcomes.

If a class accumulates many dependencies simply because it performs database, HTTP, clock, and random generation itself, consider splitting responsibilities and injecting external variation sources appropriately. Do not introduce interfaces for every class; boundaries belong where code needs to control or replace external behavior.

## 6. Categorizing Tests in a Spring Project

A Spring project usually contains several test categories. Grouping them lets developers run the exact suite they need:

| Group | Examples | Needs Network/Infrastructure? | Purpose |
|---|---|---|---|
| Pure unit tests | Domain services, validators, calculators | No | Verify rules and decisions |
| Spring context tests | Bean wiring, conditional configuration | Usually no network | Verify container setup |
| Spring MVC slices | MockMvc with controllers | No external services if dependencies are replaced | Verify HTTP adapters inside the app |
| Repository tests | JPA with test database | May need local/container database | Verify persistence |
| HTTP adapter tests | Clients with MockWebServer/WireMock | May use local sockets | Verify HTTP protocol |
| Integration tests | Multiple components with database/broker | May need infrastructure | Verify real collaboration |
| End-to-end tests | Running application across boundaries | Usually yes | Verify end-to-end flows |

**@WebMvcTest** can start the Spring MVC slice without calling external APIs when service dependencies are replaced with mocks. It still uses a Spring context, yet does not necessarily need the network.

**@DataJpaTest** usually needs a database to verify persistence. With an embedded database it runs locally; with Testcontainers it requires a container environment. This is not a pure unit test.

**@SpringBootTest(webEnvironment = RANDOM_PORT)** starts the application with a real web server in the test process. It suits certain integration tests, yet should not become the default way to test every business rule.

Naming test groups and configuring separate tasks lets CI run unit tests frequently, then run heavier integration groups at appropriate stages. Grouping must reflect actual dependencies rather than folder names alone.

## 7. Keeping Tests Fast While Preserving Valuable Assertions

Fast tests do not mean shallow tests. A single parameterized unit test can cover many input cases without booting extra infrastructure.

For example, testing fee thresholds:

~~~java
@ParameterizedTest
@CsvSource({
    "0, 30000",
    "499999, 30000",
    "500000, 0",
    "700000, 0"
})
void calculatesStandardShippingFee(
        String subtotal,
        String expectedFee
) {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal(subtotal),
            false
    );

    assertEquals(new BigDecimal(expectedFee), actual);
}
~~~

The test constructs the object directly, uses in-memory data, and depends on no external system. Each row represents a meaningful case, including policy boundaries.

A good test should:

- Verify outcomes or interactions belonging to the unit's contract.
- Carry a name expressing conditions and behavior.
- Avoid asserting unrelated implementation details.
- Make no network calls and wait on no external services.
- Never sleep waiting for out-of-scope state.
- Be independent of test execution order.
- Use deterministic inputs and sufficiently strong assertions.

If a unit test takes several seconds just to compute a value, inspect its setup, extensions, static initializers, logging, context loading, or initialized dependencies. Unusually slow test execution usually signals a test has pulled in responsibilities beyond unit scope.

## 8. Managing Execution Time in JUnit and CI

Feedback speed also depends on how the test suite is organized. Several practices keep the unit test group lean:

- Run the test class or method currently under development in the IDE.
- Use dedicated tasks or filters to run the fast unit test group.
- Keep tests requiring Docker, databases, or networks out of the group run as unit tests.
- Avoid repeatedly booting Spring contexts when tests need no context.
- Use small fixtures and avoid generating large datasets or files unnecessarily.
- Keep logging at sensible levels so tests are not slowed down by unnecessary I/O.
- When running tests in parallel, ensure each test owns isolated data and dependencies.

In Gradle, projects can use JUnit Platform tags to separate test groups. Illustrative example:

~~~java
@Tag("unit")
class ShippingFeeCalculatorTest {
    // Unit tests
}

@Tag("integration")
class PaymentGatewayIntegrationTest {
    // Integration tests
}
~~~

Dedicated tasks can be configured to run only the required tag. Exact syntax and task names depend on the project's build script; follow existing conventions rather than inventing duplicate ones.

A typical pipeline runs unit tests early for rapid feedback on every change. Afterward, test groups needing databases, brokers, or deployment environments run in later stages. This layering catches logic errors quickly while still checking integration risks.

Do not delete integration tests just to speed up CI. Put them in the right group, manage resources, and schedule them at the right time.

## 9. Diagnosing When a Unit Test Unexpectedly Depends on the Network

If a test labeled as a unit test runs slowly, hangs, or fails when offline, trace which dependency is opening a connection.

Warning signs include:

- The test runs long and fails with connect timeouts or DNS errors.
- The test requires VPN, proxy, tokens, or external service environment variables.
- The test passes only in an environment with a running database/broker.
- The test depends on live data from an API.
- The test fails intermittently under network load or rate limits.
- The test retries multiple times before finishing.

Trace the call path from the method under test to where the connection opens. Look for **HttpClient**, **RestClient**, **WebClient**, **RestTemplate**, vendor SDKs, JDBC connections, Redis clients, or message producers. Check constructors, static initializers, and bean factories, because connections are sometimes opened before the test even calls the method.

Once the boundary is found, apply fixes:

1. Pass the dependency via constructor or interface.
2. Supply fakes/stubs/mocks in unit tests.
3. Move protocol checks to adapter tests.
4. Move database/broker interaction checks to integration tests.
5. Keep unit tests free of credentials, endpoints, or network settings.

A test never needs to prove the network works to verify a business calculation. If it needs the network, revisit the test question and place it in the right layer.

## 10. Example of Organizing a Test Suite Along Boundaries

Suppose a system has subscription registration. The runtime flow is:

1. Controller receives request.
2. Application service validates data and decides subscription status.
3. Repository saves data.
4. Notification gateway sends email.

Tests can be divided as follows:

| Component | Test Suite | Dependencies in Test |
|---|---|---|
| SubscriptionPolicy | Expiration dates, activation conditions | Fixed clock |
| SubscriptionService | Registration decisions and result handling | Fake repository, mock notification port |
| SubscriptionController | Mapping, validation, responses | @WebMvcTest, mock service |
| SubscriptionRepository | Saving and reading subscriptions | Test database |
| EmailNotificationAdapter | Requests sent to SMTP/provider | Mock SMTP server or adapter test |
| RegistrationFlow | Multi-component collaborative flow | Spring context and required test infrastructure |

Unit tests for **SubscriptionService** can run hundreds of cases without touching email or a database. A fake repository stores objects in memory, while a mock notification port verifies notifications go out only on business success.

Repository tests verify database mappings and queries. Email adapter tests verify message structure or delivery protocol. Integration tests verify beans wire together and the registration flow coordinates properly under application configuration.

Thanks to this separation, when a unit test fails due to wrong subscription state, developers do not have to inspect databases or SMTP. When an adapter test fails due to malformed requests, investigation centers squarely on the adapter and communication contract.

## 11. Practical Criteria for a Fast, Network-Independent Unit Test

Before placing a test into the unit test group, ask:

- Does the test construct the object under test directly or via a small fixture?
- Are external dependencies replaced with stubs, fakes, or mocks?
- Does the test avoid calling HTTP, databases, brokers, and external services?
- Are time, randomness, and shared state controlled?
- Can the test run when the machine has no Internet connection?
- Is the test independent of execution order and other tests?
- Can assertions catch a meaningful behavior bug?
- If the test fails, can the cause be isolated to the unit under test?

If the answer about the network is no, consider extracting an adapter or moving the test to an appropriate group. If the test needs a Spring context because behavior genuinely depends on the container, classify it as a context test and control the dependencies that context initializes.

A good unit test suite delivers fast feedback, repeatability, and requires no external services to run. By keeping dependency boundaries clear, using fakes/stubs/mocks purposefully, and controlling non-deterministic sources like time and randomness, unit tests can run continuously in the IDE and CI. Tests that need to verify HTTP, databases, or brokers stay at the adapter and integration layers, where they provide solid evidence of infrastructure communication.

