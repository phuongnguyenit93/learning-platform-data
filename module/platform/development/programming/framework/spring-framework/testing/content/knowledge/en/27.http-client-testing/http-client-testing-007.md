# Resetting Expectations Between Tests

## Why Do You Need to Reset MockRestServiceServer?

When testing HTTP clients in Spring, `MockRestServiceServer` lets you declare which requests the client is allowed to send and their corresponding mock responses. Each expectation typically describes the request's URL, HTTP method, headers, or body, and then specifies the response to return.

A `RestTemplate` or `RestClient.Builder` may be created once and shared across multiple test methods. If `MockRestServiceServer` is also created once and bound to that client, the mock server's state can persist across tests:

- Expectations from the previous test might remain unfulfilled.
- Recorded requests from the previous test can affect request count or ordering checks.
- A subsequent test may fail due to leftover expectation manager state, even when its own logic is correct.

`MockRestServiceServer.reset()` resets the mock server's state: it clears registered expectations and recorded requests. That allows each test to start with a fresh set of expectations while sharing the same client and mock server.

Resetting is a test-state management operation. It does not automatically verify that the previous test made all required requests. To confirm that the current test's expectations were met, you still need to call `verify()`.

## Expectation Lifecycle

An expectation is usually declared before invoking the client:

~~~java
mockServer.expect(requestTo("https://orders.example.test/api/orders/42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"id": 42, "status": "PAID"}
                """,
                MediaType.APPLICATION_JSON
        ));
~~~

When the client sends a matching request, the mock server matches the request against the expectation and returns the declared response. Once the request is processed, the corresponding expectation is marked as used. `verify()` checks whether all declared expectations were fully satisfied.

You can visualize the lifecycle within a test as follows:

~~~text
reset() before test
      |
      v
Register expectations for the current test
      |
      v
HTTP client sends request
      |
      v
MockRestServiceServer matches and returns mock response
      |
      v
Assert result from client
      |
      v
verify() confirms expectations were met
      |
      v
Test ends
~~~

At the start of the next test, `reset()` clears expectations and request history from the previous run. The new test must register the expectations it needs itself. Do not rely on expectations created by another test.

## Using reset When Client and Mock Server Are Shared

The example below intentionally uses one `RestTemplate`, one `OrderClient`, and one `MockRestServiceServer` across multiple test methods. `TestInstance(PER_CLASS)` keeps fields alive across methods; `BeforeEach` resets the mock server's state before each new test begins.

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderClientTests {

    private final RestTemplate restTemplate = new RestTemplate();

    private MockRestServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeAll
    void createSharedClientAndServer() {
        mockServer = MockRestServiceServer
                .bindTo(restTemplate)
                .build();
        orderClient = new OrderClient(restTemplate);
    }

    @BeforeEach
    void resetExpectationsBeforeEachTest() {
        mockServer.reset();
    }

    @Test
    void findsPaidOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id": 42, "status": "PAID"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse order = orderClient.findById(42);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        mockServer.verify();
    }

    @Test
    void findsNewOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id": 7, "status": "NEW"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse order = orderClient.findById(7);

        assertThat(order.id()).isEqualTo(7L);
        assertThat(order.status()).isEqualTo("NEW");
        mockServer.verify();
    }
}
~~~

In the example, `reset()` runs before each test method, while expectations are registered inside the test that needs them. The two tests do not share each other's expectations even though they share the same `RestTemplate` and mock server.

`OrderClient` and `OrderResponse` are illustrative application types. What matters here is the fixture lifecycle: the client and mock server are created once, and expectation state is reset before each test.

## Why Reset in BeforeEach?

Putting `reset` in `BeforeEach` establishes a clear boundary: the test starts with a mock server free of expectations and request history from the previous test. Then, the test registers the exact mock responses it needs.

This order matters:

~~~java
@BeforeEach
void prepareMockServer() {
    mockServer.reset();
    // Shared expectations for every test can be declared after reset,
    // if those expectations truly belong to every test's fixture.
}
~~~

If a test needs its own expectations, declare them in the test body after `BeforeEach` has run. If shared expectations were created before reset—such as in `BeforeAll`—resetting in `BeforeEach` will wipe them out. Then the test will lack the mock responses it expects.

You could call `reset()` at the end of a test, but that is easy to miss if a test throws an exception or fails an assertion before reaching the reset call. Resetting before the next test is a better defensive mechanism for shared fixtures. Even so, each test should still verify its own expectations with `verify()`.

## Reset Does Not Replace Verify

The two methods serve two distinct purposes:

| Method | Effect |
| --- | --- |
| reset() | Clears expectations and recorded requests to start a fresh run |
| verify() | Checks whether all registered expectations have been fulfilled |

For example, a test registers an expectation but the client sends no request:

~~~java
mockServer.expect(requestTo(
        "https://orders.example.test/api/orders/42"));

// Do not call orderClient.findById(42).

mockServer.verify(); // Fails because the expectation has not been fulfilled.
~~~

If you call `reset()` immediately instead of `verify()`, the unfulfilled expectation is erased. The test loses its chance to catch that the client failed to send the required request. Therefore, `reset` is not a way to "clean up errors" or ignore missing expectations.

In each test, you should:

1. Register all required expectations.
2. Execute the HTTP client behavior.
3. Assert the returned result or expected exception.
4. Call `mockServer.verify()` to confirm requests were sent as declared.

If the project has a shared expectation check in `AfterEach`, ensure it only verifies the current mock server and does not mask the test's original exception. In simple cases, calling `verify()` directly in the test makes the verification point clear.

## Resetting with RestClient.Builder

Since Spring Framework 6.1, `MockRestServiceServer` also supports binding to `RestClient.Builder`. This is useful when the application uses the newer synchronous HTTP client API instead of `RestTemplate`.

~~~java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer mockServer = MockRestServiceServer
        .bindTo(builder)
        .build();

RestClient restClient = builder.build();
~~~

The client is built from the builder bound to the mock server. When this fixture is shared across tests, the mock server can be reset before each test following the same principle:

~~~java
@BeforeEach
void resetServer() {
    mockServer.reset();
}
~~~

Each test registers expectations via `mockServer.expect(...)`, calls `restClient`, asserts the result, and verifies. Using `RestClient` instead of `RestTemplate` does not change the meaning of `reset`: the mock server's expectation state and request history must be isolated between test runs.

## When Using Spring TestContext or Test Slices

In integration tests, `RestTemplate` or `RestClient` may be declared as a singleton bean in the `ApplicationContext`. The Spring TestContext Framework can reuse the context across multiple test classes to save time. If `MockRestServiceServer` is created and bound to that singleton client in the context, the mock server's state may also be shared.

Clarify which fixture is being shared:

- If each test method creates a fresh client and mock server, state does not need resetting between methods because each test has its own instance.
- If tests share a mock server created in a fixture or context, reset it before registering expectations for the current test.
- If another test class also receives that same singleton mock server, it must follow the same lifecycle rules. Do not let one test reset while another test is using the server.

In Spring Boot, HTTP client test slices can auto-configure the client and mock server. Check how the test slice provides the fixture in your specific Spring Boot version before adding a second mock server. Creating two mock servers bound to one client or replacing an already configured customizer can cause the test to send requests through a different fixture than the one being reset.

Resetting mock server state is usually enough to isolate expectations; there is no need to mark `@DirtiesContext` just to clear expectations or request history. `DirtiesContext` instructs Spring to evict the context from the cache and rebuild it, which is more expensive and affects every bean in the context. Only use it when the state of the `ApplicationContext` itself has been mutated so much that it cannot be reused for test goals.

## Ordered vs. Unordered Expectations

`MockRestServiceServer` uses an ordered expectation manager by default. When a test registers multiple requests, the order in which requests are sent must match the order of expectations. You can configure the expectation manager not to require ordering when request order is not part of the contract under test.

Example:

~~~java
MockRestServiceServer mockServer = MockRestServiceServer
        .bindTo(restTemplate)
        .ignoreExpectOrder(true)
        .build();
~~~

Or use a builder with a specific expectation manager when explicit configuration is needed. Regardless of which option you pick, `reset()` is still used to clear the expectation set and recorded requests between tests.

Do not use unordered mode merely to make tests fail less often. If a client must call a token endpoint first and only then call the business API, that order may be part of the behavior to verify. Conversely, if two requests are independent and the system guarantees no order, unordered expectations can avoid coupling to execution scheduling.

## Do Not Share a Mock Server Across Parallel Tests

`reset()` mutates the shared state of the mock server. If two tests use one instance concurrently:

- Test A may register an expectation.
- Test B calls `reset()` and clears A's expectation.
- Test A sends a request and no longer has a matching expectation.
- Test B may record a request or response that alters the result A is checking.

Therefore, do not run tests in parallel if they share a mutable `MockRestServiceServer`. There are three ways to handle this:

1. Create a separate `RestTemplate`/`RestClient` and mock server per test method.
2. Isolate test classes or groups sharing the fixture so they do not execute concurrently.
3. Use a separate fixture per test thread or test instance if the framework and configuration allow it.

Simply using thread-safe collections or a thread-safe expectation manager does not solve this logical issue. `reset()` can still wipe out expectations that another test just registered.

If there is no need to keep a singleton client, the simplest approach is creating the client and mock server in `BeforeEach`. Each test owns its own state, so calling `reset` to clean up state from another test is unnecessary:

~~~java
class IsolatedOrderClientTests {

    private RestTemplate restTemplate;
    private MockRestServiceServer mockServer;
    private OrderClient orderClient;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        mockServer = MockRestServiceServer
                .bindTo(restTemplate)
                .build();
        orderClient = new OrderClient(restTemplate);
    }

    @Test
    void findsAnOrder() {
        mockServer.expect(requestTo(
                        "https://orders.example.test/api/orders/42"))
                .andRespond(withSuccess(
                        """
                        {"id": 42, "status": "PAID"}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        OrderResponse result = orderClient.findById(42);

        assertThat(result.status()).isEqualTo("PAID");
        mockServer.verify();
    }
}
~~~

In this example, every test run gets a fresh mock server, so `reset` is unnecessary. This is usually the easiest approach to understand when client creation is inexpensive and does not depend on a shared context.

## Common Mistakes

### Registering Expectations Before Resetting

If `BeforeEach` calls `reset` after a fixture has already declared expectations, those expectations are wiped out. Reset first, and only then declare expectations for the test.

### Calling reset Instead of verify

`reset` clears unfulfilled expectations, so it can hide the fact that the client never sent a request. Call `verify` to confirm the current test's behavior before the test run ends.

### Assuming reset Recreates RestTemplate or RestClient

`reset` only cleans up `MockRestServiceServer` state. It does not create a new client, nor does it clear interceptors, converters, timeout settings, or other application state attached to the client.

### Sharing a Server but Forgetting to Reset

Unused expectations or request history can persist across test methods. When the client and mock server are shared, resetting at the start of each test establishes a clear boundary.

### Running in Parallel on the Same Mock Server

One test resetting can erase another test's expectations. Create separate fixtures or isolate execution scheduling if tests need to run concurrently.

### Using DirtiesContext Just to Clear Expectations

Rebuilding the entire context is unnecessary if the issue is only mock server state. Using `reset` or creating a new fixture is more appropriate.

## Workflow for Managing Expectations Between Tests

1. Determine whether `RestTemplate`/`RestClient` and `MockRestServiceServer` are shared across multiple tests.
2. If the fixture is shared, call `mockServer.reset()` in `BeforeEach`.
3. Register the test's own expectations after the reset completes.
4. Execute the HTTP client behavior.
5. Assert the response, decoded data, or expected exception.
6. Call `mockServer.verify()` to ensure all expectations were satisfied.
7. Do not run tests in parallel when they share a mutable mock server; if parallelism is needed, create separate fixtures per test.

Resetting expectations cleans up the mock HTTP server's state, while `verify` proves the client actually made the expected requests. When these two steps are placed properly in the test lifecycle, multiple tests can share a fixture without letting expectations or request history from an earlier run corrupt the next one.
