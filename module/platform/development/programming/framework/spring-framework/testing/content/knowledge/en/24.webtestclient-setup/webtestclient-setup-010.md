# Reusing Client Configuration While Isolating Per-Test Data

## 1. Two Kinds of State to Separate

In a Spring WebFlux test suite, the same **WebTestClient** configuration can be reused across many tests: base URL, default headers, codecs, filters, timeouts, and how the client connects to the application. Reusing configuration helps tests send requests consistently and avoids repeating setup code.

By contrast, the data created by each test must remain independent. One test should not accidentally read records created by another test, depend on execution order, or delete another test's data during cleanup.

Distinguish two groups:

- **Client configuration:** shared, stable settings such as root URL, default media types, codecs, and filters that hold no per-test state.
- **Test data and state:** IDs, records, tokens, mock expectations, cache keys, events, or messages created specifically for a single test run.

A built WebTestClient can be used for many requests. Each test creates its own data and sends its own requests. If a test needs to alter client configuration, create a new client from the base client using **mutate()** and then **build()**; do not mutate a shared builder while tests are running.

## 2. WebTestClient and Ways to Connect to the Application

**WebTestClient** provides an API for sending requests and asserting responses similar to WebClient, while integrating test-focused assertions. It can connect to the application in several ways:

| Binding Mode | When to Use | Characteristics |
|---|---|---|
| **bindToController(...)** | Testing one or a few WebFlux controllers | Creates a mock WebFlux stack focused on the controller |
| **bindToRouterFunction(...)** | Testing functional endpoints | Uses the provided RouterFunction |
| **bindToApplicationContext(...)** | Testing WebFlux configuration in an application context | Uses components registered in the context without opening real sockets |
| **bindToServer()** | Testing a running server | Sends HTTP over a connector to a real address |

Example creating a client bound to a WebFlux application context:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient baseClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

This client uses Spring's mock web infrastructure. It is suitable for checking mappings, filters, controllers, codecs, and response contracts inside the application context.

If you need to connect to a running server, you can create a client targeting an HTTP address:

~~~java
WebTestClient serverClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

In Spring Boot integration tests, you usually do not need to manage ports manually. You can let Spring Boot launch the server on a random port and inject a preconfigured WebTestClient.

## 3. Creating a Base Configuration and Reusing the Client

### With a mock application context

If multiple tests share a WebFlux application context, you can create the base client once in a test fixture or test configuration.

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import org.junit.jupiter.api.BeforeEach;

abstract class BaseWebFluxTest {

    @Autowired
    protected ApplicationContext applicationContext;

    protected WebTestClient client;

    @BeforeEach
    void configureClient() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .baseUrl("/api")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE
                )
                .build();
    }
}
~~~

Test classes extending this fixture share the same client setup. If the application context is cached by Spring Test across test classes, creating a client from the context does not require reinitializing the entire application for each method.

If you want to keep a base client and create variants as needed, you can build the base client and use **mutate()**:

~~~java
WebTestClient baseClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .build();

WebTestClient shortTimeoutClient = baseClient.mutate()
        .responseTimeout(java.time.Duration.ofSeconds(3))
        .build();
~~~

**mutate()** creates a builder from the existing client's configuration. Calling **build()** creates a new client with the custom change. The base client remains reusable for other tests.

### With a real Spring Boot server

When you need to send requests through an embedded server, you can use the following setup:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Autowired
    WebTestClient client;
}
~~~

Spring Boot starts the server on a random port and provides a WebTestClient already connected to that server. The same client can be used for multiple requests in the test class.

Do not confuse the two client styles: a client bound to a mock application context does not test sockets or the embedded server; a client configured against a real server tests requests/responses over the HTTP connector.

## 4. A Built WebTestClient Can Be Reused

After calling **build()**, WebTestClient is a configured client ready to perform exchanges. You can reuse the same instance across many requests:

~~~java
client.get()
        .uri("/health")
        .exchange()
        .expectStatus().isOk();

client.get()
        .uri("/version")
        .exchange()
        .expectStatus().isOk();
~~~

Each call to **get()**, **post()**, **put()**, or **delete()** creates a new request specification. Assertions on that exchange apply only to the corresponding request's response.

What to avoid is sharing a mutable **WebTestClient.Builder** and modifying headers, filters, or timeouts while tests run in parallel. Finish configuring and build the client before using it. If a different configuration is needed, derive a new client from the base client with **mutate()**.

Also avoid storing a request specification or response result in a shared field where multiple tests read or modify it. Create request specifications and assert responses directly inside each test method.

## 5. Varying Per Request Without Polluting the Base Client

Values that vary per test are usually request data, not client configuration. For example, correlation ID, tenant ID, user token, or test run ID should be attached to a specific request:

~~~java
String testRunId = java.util.UUID.randomUUID().toString();

client.get()
        .uri("/notes/{id}", noteId)
        .headers(headers -> headers.set("X-Test-Run", testRunId))
        .exchange()
        .expectStatus().isOk();
~~~

The header is attached only to this request. Subsequent requests do not automatically inherit the **X-Test-Run** value.

If a test needs custom client-level configuration, such as a different timeout or an extra filter, create a variant:

~~~java
WebTestClient testClient = client.mutate()
        .responseTimeout(java.time.Duration.ofSeconds(2))
        .build();
~~~

Do not call **defaultHeader()** on a shared builder per test to pass test-specific data. Default headers belong to client configuration and can persist onto subsequent requests. For per-test data, use **headers(...)** on the request builder.

### Shared filters should not hold per-test state

Filters are useful for logging, adding common headers, or timing exchanges. However, a filter configured on a shared client may be invoked concurrently by multiple tests.

A safe filter relies on the current request and avoids storing test data in global mutable variables. If a filter needs a correlation ID, it can read a request header or use Reactor Context along the reactive flow. Avoid recording every request into a shared **ArrayList** and having tests read or clear it, because tests can overwrite or read each other's data.

## 6. Isolating Data with Unique IDs per Test

Reusing a client does not mean tests must share data. A straightforward technique is generating a unique ID for each test, saving fixtures under that ID, sending requests only for that fixture, and deleting that exact fixture in cleanup.

The example below assumes the application has a reactive repository and a GET endpoint for a note by ID:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Autowired
    private NoteRepository noteRepository;

    @Test
    void shouldReturnOnlyTheNoteCreatedForThisTest() {
        String noteId = UUID.randomUUID().toString();
        String title = "note-" + noteId;

        noteRepository.save(new Note(noteId, title)).block();

        try {
            client.get()
                    .uri("/api/notes/{id}", noteId)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            org.springframework.http.MediaType.APPLICATION_JSON)
                    .expectBody()
                    .jsonPath("$.id").isEqualTo(noteId)
                    .jsonPath("$.title").isEqualTo(title);
        } finally {
            noteRepository.deleteById(noteId).block();
        }
    }
}
~~~

Key points in the example:

1. **noteId** is freshly generated for every test run, so it never collides with another test's ID.
2. The test queries only the fixture it created itself.
3. Cleanup deletes only **noteId**, not the entire table.
4. The **finally** block runs cleanup even if assertions fail.

Calling **block()** in a test method is a simple way to finish reactive setup/cleanup operations before the test ends. Never call **block()** inside a WebFlux event loop or in request-handling code. In a larger reactive test suite, setup and cleanup can be written as Reactor chains and driven with **StepVerifier**; the data isolation principle remains the same.

If a test verifies an endpoint that creates new data, extract the ID returned in the response and clean up that exact ID. Do not rely on a hardcoded ID shared across runs or CI workers.

## 7. Isolating via Namespaces Instead of Deleting All Data

Some systems cannot easily assign unique IDs to every kind of data. In such cases, you can attach a test namespace to the data:

~~~java
String testNamespace = "test-" + UUID.randomUUID();

client.post()
        .uri("/api/jobs")
        .header("X-Test-Namespace", testNamespace)
        .bodyValue(new CreateJobRequest("import"))
        .exchange()
        .expectStatus().isCreated();
~~~

The application must have appropriate test support so that the namespace is incorporated into storage keys, tenants, or fixture metadata. A header only helps if the application actually processes it; adding a header in the test alone does not isolate the database.

Common options:

- Use a unique UUID or sequence per fixture.
- Add a tenant/test-run key to data if the application supports multi-tenancy.
- Use a separate schema or database per test suite or per CI worker.
- Use a dedicated database container per suite when strong isolation is needed.
- Clean up by the set of IDs created by the test, rather than calling **deleteAll()** on shared data.

Avoid calling **deleteAll()** during cleanup of a test running in parallel with other tests against the same database. It can delete fixtures belonging to tests that have not finished yet.

## 8. Why @Transactional Does Not Always Roll Back WebTestClient Requests

A common misconception is that annotating a test method with **@Transactional** automatically rolls back all data created by an endpoint when the test completes.

That is not true for HTTP requests to a real server. The test method and the server-handled request are two independent execution flows. The server request runs its own transactions according to its services/repositories and transaction context; the test method's transaction does not automatically propagate across the HTTP boundary.

In WebFlux, reactive transactions are typically bound to Reactor Context rather than ThreadLocal like traditional imperative transactions. A transaction on a test method is not automatically attached to the Reactor Context of a request sent by WebTestClient.

Even when WebTestClient binds directly to a mock application context without opening a socket, the request is still processed as a separate exchange. Do not assume a test transaction wraps transactions inside the request pipeline.

Therefore, for integration tests using WebTestClient, prefer:

- Setting up fixtures before the request.
- Using unique IDs or namespaces.
- Cleaning up exact data after the request.
- Using a separate database/schema/container when higher isolation is required.

**@Transactional** remains useful for tests calling repositories/services directly within the same transaction managed by the test framework. Simply understand its boundary before applying it to requests sent through WebTestClient.

## 9. Mocks and Service State Must Also Be Independent

For controller slices, services are often mocked to test HTTP mappings and responses:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(NoteController.class)
class NoteControllerTest {

    @Autowired
    private WebTestClient client;

    @MockBean
    private NoteService noteService;

    @Test
    void shouldReturnTheRequestedNote() {
        String noteId = "note-a";
        when(noteService.findById(noteId))
                .thenReturn(Mono.just(new NoteResponse(noteId, "title-a")));

        client.get()
                .uri("/api/notes/{id}", noteId)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(noteId)
                .jsonPath("$.title").isEqualTo("title-a");
    }
}
~~~

In Spring Boot 3.3, **@MockBean** is the familiar way to replace a bean in the application context with a Mockito mock. By default, Spring Boot resets mocks after each test method according to the annotation's reset configuration. Even so, each test should declare its own required stubs explicitly and not depend on test order or data left by a previous test.

If a mock uses an **Answer** holding counters, event lists, or mutable objects, ensure that state belongs only to the current test. Resetting a mock does not automatically stop running async tasks and does not delete data those tasks already wrote to a database.

Do not use a singleton fake service with a shared mutable collection across parallel tests without explicit synchronization and reset. When you need to inspect received events or requests, use a captor or recorder scoped to that single test.

## 10. Running Tests in Parallel Without Data Leakage

When JUnit or CI runs multiple tests concurrently, the base client can be shared, but fixtures must be partitioned.

Practical rules:

- Generate unique IDs inside each test method.
- Do not share a mutable field to store the current test's ID.
- Do not clean up by wiping entire tables, caches, or queues.
- Use request headers or tenant keys only when the application actually supports the corresponding partitioning.
- Shared filters and callbacks must not hold per-test mutable state.
- Do not depend on an earlier test to create data for a subsequent test.
- Close streams, subscriptions, and async resources during cleanup.
- If a test uses an external resource that cannot be partitioned, disable parallelism for that group of tests or provision dedicated resources.

By default, JUnit creates one test class instance per test method. If switched to **@TestInstance(PER_CLASS)**, instance fields are shared across methods; be extra careful with fields like current IDs, mutable header maps, mock recorders, or test fixtures.

With parallel tests, a built **WebTestClient** can be reused provided its configuration and filters do not hold shared mutable state. Isolate data and request-specific state inside each test.

## 11. When Do You Need to Create a New Client?

Not every test needs a brand-new client instance. Choose based on what changes:

| Need | Approach |
|---|---|
| Same base URL, codecs, filters, and default headers | Reuse the already-built client |
| Different header or token for a single request | Set the header on the request builder |
| Different timeout for a group of tests | Use **client.mutate().responseTimeout(...).build()** |
| Adding a custom filter for one test | Create a new client via **mutate()** then **build()** |
| Connecting to a mock application context vs. a real server | Create clients with the corresponding bind modes |
| Different database data | Create separate fixture IDs/namespaces; no new client needed |
| Different TLS or connector settings | Create a new client with the matching connector and configuration |

A new client does not clean databases, caches, or mock state by itself. Conversely, using the same client does not cause tests to share data as long as each test creates independent fixtures and requests carry no leftover state.

## 12. Avoiding Error-Prone Isolation Patterns

| Practice | Issue | Alternative |
|---|---|---|
| Creating a static builder and mutating headers per test | Mutable builder can be modified concurrently by multiple tests | Build the base client once; put per-test headers on the request |
| Using a fixed ID across all tests | Tests depend on ordering and stale data | Use UUIDs or isolated namespaces |
| Calling deleteAll() after each test | Can delete data of tests running in parallel | Delete only the test's own ID or namespace |
| Using @Transactional and assuming HTTP requests roll back with the test | Transactions do not automatically cross request boundaries | Explicit cleanup or dedicated database |
| Using a filter that logs state to a singleton collection | Multiple requests can overwrite and read each other's entries | Stateless filters or per-test recorders |
| Using @DirtiesContext to clear data | Reloading the context does not reset databases, Redis, or queues | Clean up external resources properly |
| Sharing response results or request specifications across tests | Responses and requests have per-exchange lifecycles | Create and assert exchanges inside each test method |

**@DirtiesContext** can be useful when a test corrupts the Spring context's state and requires a fresh context. It is not a general-purpose database cleanup mechanism; reloading contexts is also expensive and can slow down test suites significantly.

## 13. A Scalable Test Organization Pattern

You can put the base client configuration into a shared fixture while creating test data inside each method:

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;

abstract class BaseApiIntegrationTest {

    @Autowired
    protected WebTestClient client;

    protected String newTestId() {
        return UUID.randomUUID().toString();
    }
}
~~~

An individual test creates and cleans up its own data:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class NoteApiIntegrationTest extends BaseApiIntegrationTest {

    @Autowired
    private NoteRepository noteRepository;

    @Test
    void shouldReadItsOwnNote() {
        String id = newTestId();
        Note note = new Note(id, "title-" + id);

        noteRepository.save(note).block();

        try {
            client.get()
                    .uri("/api/notes/{id}", id)
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.id").isEqualTo(id);
        } finally {
            noteRepository.deleteById(id).block();
        }
    }
}
~~~

The base class shares only client configuration and an ID-generation helper. Each test method owns its fixture. If a test needs a client with a different timeout or an extra filter, it can create a variant using **client.mutate()** without modifying the base client.

In a project with multiple endpoint styles, you can have one fixture for a mock-bound WebFlux context and another for a real server. Naming and usage should clearly indicate the test level so readers do not mistake a mock context test for an HTTP integration test.

Reusing WebTestClient standardizes how requests are sent and asserted. Per-test independence comes from isolated fixtures, per-request state, scoped cleanup, and avoiding shared mutable state across runs.

