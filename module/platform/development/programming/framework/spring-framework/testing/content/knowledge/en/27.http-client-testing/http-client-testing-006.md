# ExpectedCount, Request Ordering, and verify

When testing an HTTP client in Spring, we often need to verify that the client sends the right request, sends it the right number of times, follows the required order, and emits no unexpected calls. For `RestTemplate` or `RestClient`, Spring Test provides `MockRestServiceServer` to simulate the remote server and declare expectations for each request.

Three concepts in this topic are closely linked:

- **ExpectedCount** specifies how many times a request is allowed or required to occur.
- **Request ordering** determines whether expectations must be matched in declaration order or may occur in any order.
- **verify()** confirms that expectations were satisfied after the client completes its work.

Understanding these three parts properly enables HTTP client tests to check both normal behavior and bugs such as excessive API calls, missing requests, out-of-order calls, or forgetting to verify declared requests.

## 1. What Is MockRestServiceServer For?

`MockRestServiceServer` is a Spring Test tool for testing outbound HTTP code without connecting to a real service. It attaches a mock request factory to the HTTP client, receives requests produced by the client, matches them against expectations, and returns test-defined responses.

Processing flow:

~~~text
Test
 |
 | declares request expectations and mock responses
 v
MockRestServiceServer
 ^
 | requests sent by the HTTP client
 |
RestTemplate / RestClient
 |
 v
Application code calling external API
~~~

For example, a service calls a catalog API to fetch product information. A test can:

1. Declare that a GET request must hit a specific URI.
2. Verify the HTTP method and headers.
3. Return mock JSON.
4. Invoke the service under test.
5. Assert the service's result.
6. Call `verify()` to ensure the request was sent as expected.

The mock server only replaces the HTTP communication layer. It does not automatically verify the service's business logic; the test still needs assertions on the value returned by the service.

## 2. Initializing MockRestServiceServer

### With RestTemplate

Create `RestTemplate`, then bind the mock server to that instance:

~~~java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
    MockRestServiceServer.bindTo(restTemplate).build();
~~~

After binding, requests sent by `RestTemplate` are handled by the mock server. There is no need to spin up an HTTP server or open real ports.

A complete test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class CatalogClientTests {

    @Test
    void loadsProduct() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer mockServer =
            MockRestServiceServer.bindTo(restTemplate).build();

        mockServer.expect(requestTo("https://catalog.example.test/products/42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                """
                {"id":42,"name":"Spring Guide"}
                """,
                MediaType.APPLICATION_JSON
            ));

        String body = restTemplate.getForObject(
            "https://catalog.example.test/products/42",
            String.class
        );

        assertThat(body).contains("Spring Guide");
        mockServer.verify();
    }
}
~~~

In the example, `expect(...)` registers an expectation. `andExpect(...)` adds conditions that must hold for that request. `andRespond(...)` defines the mock response the client receives when the request matches.

### With RestClient

Spring Framework 6.1 added support for binding `MockRestServiceServer` to `RestClient.Builder`. Bind before building `RestClient`:

~~~java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://catalog.example.test");

MockRestServiceServer mockServer =
    MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();
~~~

The test can declare expectations and invoke `RestClient`:

~~~java
mockServer.expect(requestTo("https://catalog.example.test/products/42"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"Spring Guide"}
        """,
        MediaType.APPLICATION_JSON
    ));

String body = restClient.get()
    .uri("/products/42")
    .retrieve()
    .body(String.class);

assertThat(body).contains("Spring Guide");
mockServer.verify();
~~~

For a `RestClient` with a base URL, request matchers can use relative URIs according to how the builder is configured. If you need to verify the absolute URI, use a URI matcher suited to the URI format the actual request produces.

## 3. What Is ExpectedCount?

`ExpectedCount` resides in the package:

~~~java
import org.springframework.test.web.client.ExpectedCount;
~~~

It describes how many times an expectation may be matched. You can pass `ExpectedCount` to an overload of `expect(...)`:

~~~java
mockServer.expect(ExpectedCount.times(2), requestTo("/inventory/42"))
    .andRespond(withSuccess("available", MediaType.TEXT_PLAIN));
~~~

Common factory methods:

| Factory method | Accepted request count | When to use |
|---|---:|---|
| `ExpectedCount.once()` | Exactly 1 time | The request must occur exactly once. |
| `ExpectedCount.times(n)` | Exactly n times | A request must be sent an exact specified number of times. |
| `ExpectedCount.manyTimes()` | At least 1 time, no upper bound | The request may repeat multiple times and must occur at least once. |
| `ExpectedCount.min(n)` | At least n times | Verify the call count meets a minimum threshold. |
| `ExpectedCount.max(n)` | At most n times, possibly 0 | Cap the allowed number of calls. |

Examples:

~~~java
ExpectedCount.once();       // 1 time
ExpectedCount.times(3);     // exactly 3 times
ExpectedCount.manyTimes();  // at least 1 time
ExpectedCount.min(2);       // 2 or more times
ExpectedCount.max(4);       // at most 4 times
~~~

With `times(n)`, the actual count must equal `n`. If the request occurs only once when two were expected, `verify()` fails. If the request occurs more times than permitted, the mock server fails immediately as soon as the request exceeds the expectation.

## 4. Using ExpectedCount to Check Repeated Requests

A service may need to call the same endpoint multiple times, such as reading pages of data or retrying a request per a retry policy.

Example of a client calling an inventory endpoint twice:

~~~java
mockServer.expect(
        ExpectedCount.times(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        """
        {"itemId":42,"available":true}
        """,
        MediaType.APPLICATION_JSON
    ));

inventoryClient.loadItem(42);
inventoryClient.loadItem(42);

mockServer.verify();
~~~

An expectation with an `ExpectedCount` of two accepts two requests matching the declared matchers. There is no need to write two identical expectations just to describe the same request repeating exactly twice.

If the request must occur at least twice:

~~~java
mockServer.expect(
        ExpectedCount.min(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

If you only want to allow at most two calls:

~~~java
mockServer.expect(
        ExpectedCount.max(2),
        requestTo("https://inventory.example.test/items/42")
    )
    .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Note: `max(2)` does not require the request to occur. It only sets an upper bound. If you need to ensure at least one call, use `once()`, `times(n)` with `n` greater than 0, `manyTimes()`, or `min(n)` depending on the contract.

### Verifying an Endpoint Is Not Called

If the test declares no expectation for an endpoint, an unexpected request to the mock server matches no expectation and triggers an error. Therefore, to verify an API is not called, typically you simply omit declaring an expectation for that request and execute the behavior under test.

For example, a cache-hit branch should not call the remote service:

~~~java
mockServer.expect(requestTo("/health"))
    .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

catalogService.getCachedProduct(42);

// If the code unexpectedly calls the catalog API, the mock server reports an unexpected request.
mockServer.verify();
~~~

In this example, the only expectation is the health request if the test intentionally invokes it. If the cache branch needs zero requests, register no expectations; any unexpected call to the mock server fails immediately.

## 5. An Expectation Consists of Matchers and a Response

An expectation typically has three parts:

~~~java
mockServer.expect(ExpectedCount.once(), requestTo("/products/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"Spring Guide"}
        """,
        MediaType.APPLICATION_JSON
    ));
~~~

| Part | Role |
|---|---|
| `expect(count, matcher)` | Declares the count and criteria for identifying the request. |
| `andExpect(matcher)` | Adds conditions on method, headers, query, body, or request attributes. |
| `andRespond(creator)` | Defines the response returned to the client. |

Common request matchers:

~~~java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
~~~

| Matcher | Checks |
|---|---|
| `requestTo(uri)` | Request URI. |
| `method(HttpMethod.GET)` | HTTP method. |
| `header(name, value)` | Header value. |
| `headerDoesNotExist(name)` | Header is not sent. |
| `queryParam(name, values...)` | Query parameters. |
| `content().string(value)` | Text request body. |
| `content().json(json)` | JSON request body. |
| `content().formData(...)` | Form data. |

Common response creators:

~~~java
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
~~~

| Response creator | Mock response |
|---|---|
| `withSuccess(body, mediaType)` | 200 OK with body. |
| `withStatus(status)` | Custom status. |
| `withBadRequest()` | 400 Bad Request. |
| `withSuccess()` | 200 OK with no body. |
| `withNoContent()` | 204 No Content. |
| `withServerError()` | 500 Internal Server Error. |
| `withException(exception)` | I/O error at the request execution layer. |

## 6. Default Request Ordering

By default, `MockRestServiceServer` requires expectations to be satisfied in declaration order. The first request must match the first expectation, the next request must match the next expectation, and so on.

Example of a client that must fetch an access token before calling the orders API:

~~~java
mockServer.expect(requestTo("/oauth/token"))
    .andExpect(method(HttpMethod.POST))
    .andRespond(withSuccess(
        """
        {"access_token":"test-token"}
        """,
        MediaType.APPLICATION_JSON
    ));

mockServer.expect(requestTo("/orders"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("Authorization", "Bearer test-token"))
    .andRespond(withSuccess(
        """
        [{"id":101,"status":"PAID"}]
        """,
        MediaType.APPLICATION_JSON
    ));

orderClient.loadOrders();
mockServer.verify();
~~~

This test verifies ordering at the HTTP level:

1. The client calls the token endpoint.
2. The mock server returns the token.
3. The client uses the token in the Authorization header to call the orders endpoint.
4. The mock server returns the list of orders.

If the code calls `/orders` before `/oauth/token`, the request does not match the pending expectation and the test fails. This is useful for verifying workflows where remote API call order is significant.

### One Expectation Can Be Matched Multiple Times

`ExpectedCount` also participates in ordering. If the first expectation requires two calls, two matching requests must be processed before the next expectation's turn arrives:

~~~java
mockServer.expect(
        ExpectedCount.times(2),
        requestTo("/inventory/42")
    )
    .andRespond(withSuccess("available", MediaType.TEXT_PLAIN));

mockServer.expect(requestTo("/orders/101"))
    .andRespond(withSuccess("created", MediaType.TEXT_PLAIN));

orderClient.checkInventoryTwiceThenCreateOrder();
mockServer.verify();
~~~

The declaration order here describes a sequence: two inventory checks, then creating the order. If ordering is not a business requirement, do not accidentally depend on it.

## 7. Ignoring Order with ignoreExpectOrder(true)

In some cases, requests can be sent in varying order yet all of them must occur. For example, a service calls two independent APIs or makes parallel calls. In that situation, you can tell the mock server to ignore expectation order:

~~~java
MockRestServiceServer mockServer = MockRestServiceServer
    .bindTo(restTemplate)
    .ignoreExpectOrder(true)
    .build();
~~~

Then declare the expectations:

~~~java
mockServer.expect(requestTo("/profile/42"))
    .andRespond(withSuccess(
        """
        {"id":42,"name":"An"}
        """,
        MediaType.APPLICATION_JSON
    ));

mockServer.expect(requestTo("/permissions/42"))
    .andRespond(withSuccess(
        """
        {"canEdit":true}
        """,
        MediaType.APPLICATION_JSON
    ));
~~~

Code can call profile before permissions or vice versa. Each request must still match an expectation, and each expectation must still satisfy its `ExpectedCount` when `verify` is called.

`ignoreExpectOrder(true)` changes the expectation-matching rule; it does not disable request checks. URI, method, headers, body, and call count are still verified as declared.

The builder API to ignore order has been available since Spring Framework 6.1. On older versions, the builder may not provide this method; either keep expectations ordered or upgrade the framework version per your project's dependency management.

### When Should You Not Ignore Order?

Keep the default ordering if:

- The second request needs data from the first request's response, such as an access token.
- The later request is only valid after the earlier request completes.
- Call order is part of the contract under test.
- You want the test to catch bugs when code reverses the sequence.

Only ignore order when requests are truly independent or execution scheduling is not guaranteed. If two expectations have overly similar matchers, ignoring order can make tests confusing; use matchers that clearly distinguish requests by URI, method, query, or header.

## 8. What Does verify() Confirm?

`verify()` checks whether registered expectations were fulfilled the required number of times. Call it after client code finishes the actions under test:

~~~java
catalogService.loadProduct(42);

mockServer.verify();
~~~

If an expectation requires one request and the client never calls it, `verify` fails. If an expectation requires two calls and only one occurs, `verify` also fails.

Important points:

- `expect(...)` only registers an expectation; it does not send a request.
- `andRespond(...)` only configures the mock response; it does not execute the client.
- `verify()` does not invoke the client or create requests itself.
- Unexpected requests typically make the mock server throw an error as soon as the client sends that request.
- `verify()` checks count expectations, catching missing requests.

Do not skip `verify` just because the test received the expected response. A client might return the right data while calling a secondary endpoint too few or too many times. `verify` confirms HTTP communication matched the test contract.

## 9. verify(Duration) for Asynchronous Requests

If code sends requests from another thread or an asynchronous task, calling `verify()` right after starting the task may be too early. The request might not have been sent yet at the moment `verify` runs.

In Spring Framework versions that support it, `verify(Duration timeout)` waits up to the specified duration for expectations to be met:

~~~java
mockServer.verify(Duration.ofSeconds(2));
~~~

Example:

~~~java
import java.time.Duration;

CompletableFuture<Void> operation = orderClient.loadOrderAsync(42);

operation.join();
mockServer.verify(Duration.ofSeconds(2));
~~~

If the `Future` already completes after the HTTP request finishes, regular `verify` is usually sufficient. If a background task is launched independently and the test lacks a direct completion signal, `verify` with a timeout can wait for the request to reach the mock server.

Do not use large timeouts to mask broken synchronization. If the test can await a `Future`, latch, or task completion signal, synchronize on that signal first and then verify. A timeout only sets a wait limit; it does not cause an asynchronous task to finish on its own.

## 10. Example Testing ExpectedCount and verify

Suppose a service reads remote configuration once and then checks health status twice:

~~~java
class RemoteStatusService {

    private final RestTemplate restTemplate;

    RemoteStatusService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    String loadConfiguration() {
        return restTemplate.getForObject(
            "/configuration",
            String.class
        );
    }

    void checkHealthTwice() {
        restTemplate.getForObject("/health", String.class);
        restTemplate.getForObject("/health", String.class);
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.DefaultUriBuilderFactory;

class RemoteStatusServiceTests {

    @Test
    void sendsExpectedRequests() {
        RestTemplate restTemplate = new RestTemplate();
        restTemplate.setUriTemplateHandler(
            new DefaultUriBuilderFactory("https://status.example.test")
        );
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(restTemplate).build();
        RemoteStatusService service = new RemoteStatusService(restTemplate);

        server.expect(once(), requestTo("https://status.example.test/configuration"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("mode=test", MediaType.TEXT_PLAIN));

        server.expect(times(2), requestTo("https://status.example.test/health"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("UP", MediaType.TEXT_PLAIN));

        assertThat(service.loadConfiguration()).isEqualTo("mode=test");
        service.checkHealthTwice();

        server.verify();
    }
}
~~~

The test explicitly declares the count for each endpoint. If health is called only once, `verify` reports one missing request. If health is called three times, the request exceeding `ExpectedCount` fails the test.

## 11. Checking Ordering and Counts in One Scenario

Suppose a client must:

1. Fetch a token once.
2. Read the profile twice.
3. Send one audit request last.

Expectations:

~~~java
server.expect(ExpectedCount.once(), requestTo("/token"))
    .andRespond(withSuccess("{\"token\":\"t1\"}", MediaType.APPLICATION_JSON));

server.expect(ExpectedCount.times(2), requestTo("/profile"))
    .andRespond(withSuccess("{\"name\":\"An\"}", MediaType.APPLICATION_JSON));

server.expect(ExpectedCount.once(), requestTo("/audit"))
    .andRespond(withSuccess());

client.executeWorkflow();
server.verify();
~~~

The scenario above combines both cardinality and order:

| Position | Request | Required count |
|---:|---|---:|
| 1 | `/token` | 1 |
| 2 | `/profile` | 2 |
| 3 | `/audit` | 1 |

If profile is called only once, `verify` catches the unsatisfied expectation. If audit is called before profile finishes, default ordering causes the request not to match the current expectation.

If profile and audit are independent, use `ignoreExpectOrder(true)` rather than relying on incidental thread ordering.

## 12. Resetting the Mock Server Between Phases

`reset()` clears registered expectations and recorded request state so the mock server can be used for a subsequent test phase:

~~~java
server.reset();

server.expect(requestTo("/next-step"))
    .andRespond(withSuccess("done", MediaType.TEXT_PLAIN));
~~~

Usually, you should create a new mock server per test method so tests remain independent and readable. `reset()` is helpful when a single test intentionally exercises multiple distinct phases on the same client, or when a shared fixture needs to clear state between phases.

Do not call `reset` before `verify` if you still need to confirm previous expectations. `reset` wipes the information `verify` checks; finish verifying the current phase before resetting.

## 13. Organizing verify in JUnit

You can call `verify()` directly inside the test:

~~~java
@Test
void loadsProduct() {
    // Declare expectations
    // Call service
    // Assert results
    mockServer.verify();
}
~~~

Or place `verify` in `@AfterEach` so every test in the class is checked:

~~~java
@AfterEach
void verifyMockServer() {
    mockServer.verify();
}
~~~

Using `@AfterEach` requires ensuring every test declares exact expectations and the mock server is reinitialized per test. If a test fails mid-way, a `verify` failure in teardown may appear alongside the original error and make logs harder to read. For tests with multiple branches or phases, calling `verify` explicitly at the end of the test often makes it clearer which phase fell short.

Example using JUnit lifecycle:

~~~java
class CatalogClientTests {

    private RestTemplate restTemplate;
    private MockRestServiceServer server;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        server = MockRestServiceServer.bindTo(restTemplate).build();
    }

    @AfterEach
    void verifyRequests() {
        server.verify();
    }
}
~~~

Do not share the same mutable mock server across tests running in parallel if tests can register or consume each other's expectations. Each test should have its own client and mock server.

## 14. ExpectedCount and Retries

An application may retry when a remote service returns transient errors. `ExpectedCount` helps verify call counts match the retry policy.

Example of a service making up to three attempts:

~~~java
// retryTemplate is configured for at most three attempts.
String body = retryTemplate.execute(context ->
    restTemplate.getForObject(
        "https://inventory.example.test/inventory/42",
        String.class
    )
);
~~~

With a maximum-three-attempts policy, that is one initial call plus up to two retries. If each attempt issues an HTTP request via `RestTemplate` or `RestClient`, the test can use `ExpectedCount.max(3)` to cap the request count. If the scenario specifically requires retrying twice before succeeding, use `times(3)` and configure a mock response for each attempt. The example above illustrates a retry mechanism wrapping `RestTemplate`; `MockRestServiceServer` does not replace `WebClient`'s transport.

Example of `RestTemplate` retry at the service layer:

~~~java
server.expect(ExpectedCount.times(3), requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withServerError());
~~~

If you need to return two errors followed by success, you can declare three expectations with the same matcher in order:

~~~java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withServerError());

server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

server.expect(requestTo("https://inventory.example.test/inventory/42"))
    .andRespond(withSuccess(
        "{\"available\":true}",
        MediaType.APPLICATION_JSON
    ));
~~~

The test must invoke code that actually implements the retry policy and assert the final outcome. Merely declaring three expectations does not make the client retry; retry behavior must exist in the code under test.

## 15. Common Mistakes

### Forgetting to Call verify()

A test can run to completion and its result assertions may still pass even though an expectation was never fulfilled. Call `verify()` to confirm required request counts.

### Confusing ExpectedCount with Response Count

`ExpectedCount` describes how many times a request matches an expectation. It is not the number of elements in a response body or how many times a Java method is called independently of HTTP.

### Using once() for a Retryable Request

If code is designed to retry, a `once()` expectation can cause the test to fail when the second attempt occurs. Declare the count matching the retry policy under test.

### Using manyTimes() When a Count Limit Is Needed

`manyTimes` permits an unlimited number of calls once at least one request has arrived. If you need an upper bound, use `max(n)`; if you need an exact count, use `times(n)`.

### Assuming Ignoring Order Disables All Checks

`ignoreExpectOrder(true)` only drops the ordering constraint. Requests must still match URI, method, headers, body, and `ExpectedCount`.

### Reordering Expectations in a Dependent Workflow

If request B needs a token or ID from request A's response, ordering is part of the behavior. Do not enable `ignoreExpectOrder` just to make a test pass more easily.

### Calling verify Too Early for Asynchronous Requests

If requests are sent on a background thread, calling `verify` immediately after launching the task can run before the request is sent. Await a completion signal or use `verify` with an appropriate timeout.

### Sharing a Mock Server Across Parallel Tests

Expectations and request history are mutable state inside the mock server. Sharing one instance can let tests consume each other's expectations. Initialize separate instances per test.

### Checking Only Requests While Forgetting Business Results

`MockRestServiceServer` verifies HTTP communication. Tests should still verify that the service parsed the response, handled errors, and returned the right result.

## 16. How to Choose ExpectedCount, Ordering, and verify

When writing an HTTP client test:

1. Determine how many times each endpoint must be called.
2. Use `once()`, `times(n)`, `manyTimes()`, `min(n)`, or `max(n)` matching the contract.
3. Keep default ordering if later requests depend on earlier ones or if order is behavior under test.
4. Use `ignoreExpectOrder(true)` when requests are independent and ordering is not part of the contract.
5. Declare matchers specific enough to distinguish requests, especially when ignoring order.
6. Use `andRespond(...)` to simulate success responses, HTTP errors, or I/O errors.
7. Call `verify()` after the client finishes; for async tasks, await the task or use `verify(Duration)` if your Spring version supports it.
8. Separately assert the business result returned by the client code.

`ExpectedCount` answers "how many times is this request called?", expectation ordering answers "which request must happen first?", and `verify()` confirms that declared requirements were actually met. Combining these three mechanisms properly enables HTTP client tests to verify call counts, communication sequence, and completion of the entire workflow.
