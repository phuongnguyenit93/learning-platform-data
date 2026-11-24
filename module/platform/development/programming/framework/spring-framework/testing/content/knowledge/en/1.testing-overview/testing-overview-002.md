# Risks to Verify in a Spring Application

Spring helps assemble applications from beans, configuration, HTTP converters, data layers, and various background mechanisms. These mechanisms make applications extensible, yet they also introduce risks that are hard to see if you only test individual Java methods in isolation. A service may work correctly when instantiated with `new`, yet behave differently when managed by Spring; a repository may pass tests against a simulated database yet fail on the real database engine; an endpoint may return the right data in the normal case yet miss access control or mishandle invalid input.

Therefore, testing a Spring application needs to answer two parallel questions: **is the business logic correct, and do the Spring-wired components collaborate properly in the actual runtime environment?** This lesson focuses on the risks to identify, how to choose an appropriate testing level, and the evidence to collect to catch bugs before release.

## 1. Configuration and ApplicationContext Initialization

`ApplicationContext` is where Spring discovers, creates, and wires beans. Errors at this stage can prevent the application from starting, or let it start with the wrong configuration.

Common risks include:

- A bean is not scanned because it lies outside the component-scan scope or lacks an import configuration.
- Multiple beans share the same type without an appropriate `@Primary` or `@Qualifier`, leading to injection failure or picking the wrong implementation.
- A bean is only created under a different profile or configuration condition than the deployment environment.
- Property values are missing, have the wrong type or name, or are overridden by a higher-precedence configuration source.
- Initialization configuration introduces a circular dependency, or a bean initializes too early before a dependency is ready.

Do not merely check that a class carries `@Component` or `@Service`. What needs confirmation is that **the context actually creates the required beans and uses the right configuration in the target profile**.

Example of verifying a group of critical beans in the context:

```java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsTheRequiredApplicationBeans() {
        assertNotNull(context.getBean(OrderService.class));
        assertNotNull(context.getBean(OrderRepository.class));
        assertNotNull(context.getBean(PaymentGateway.class));
    }
}
```

This is an example for a Spring Boot application; for a plain Spring Framework application, you can initialize the context from the corresponding Java or XML configuration. There is no need to write a test listing every bean. Focus on beans that govern business flows, security, persistence, and integration.

When configuration involves multiple profiles, verify at least the profile used in testing and key differences in deployment profiles. Pay special attention to required properties such as service URLs, timeouts, connection limits, and credentials. Do not put real secrets into test code; use dummy values or secrets provisioned specifically for the test environment.

## 2. Dependency Injection and Proxy Behavior

Dependency Injection enables Spring to supply dependencies to objects. Risks arise when an application has multiple implementations, uses qualifiers inconsistently, or instantiates objects manually instead of letting the container manage them.

For example, `OrderService` might need `PaymentGateway` for online payments and `TestPaymentGateway` in the test environment. If profiles or qualifiers are misconfigured, the application might invoke the wrong payment gateway. Tests need to confirm that the expected implementation is injected under the right configuration, while also verifying behavior through the Spring-managed bean.

An easily overlooked point is that annotations such as `@Transactional`, `@Async`, `@Cacheable`, and certain AOP annotations operate through proxies. When a method is called from outside the bean, the call can pass through the proxy to apply transactions, run asynchronously, or access the cache. However, if a method inside the same class calls an annotated method directly, that self-invocation usually bypasses the proxy. In that case, the annotation may not produce the effect the developer expects.

Example of self-invocation:

```java
@Service
class OrderService {

    public void placeOrder() {
        saveOrder();
    }

    @Transactional
    public void saveOrder() {
        // Persist order data
    }
}
```

If `placeOrder()` calls `saveOrder()` directly on the same object, the transaction declared on `saveOrder()` may not be activated as intended. The right way to verify this is to invoke the bean through the Spring context and observe the transaction outcome, rather than manually instantiating `new OrderService()` and only checking the method's return value.

When testing proxy-based features, confirm that:

- The object is obtained from the Spring container.
- The call crosses the proxy boundary as designed.
- Proxy configuration suits the bean type and methods in use.
- Observed behavior matches the contract: a transaction is opened, the cache is used, the task is submitted to an executor, or the method is validated.

## 3. HTTP Boundary: Routing, Data, and Errors

For Spring MVC or Spring WebFlux applications, controllers form the boundary between HTTP and application logic. Tests that only invoke controller methods directly skip an essential part of request processing.

Risks to verify include:

- URLs, HTTP methods, path variables, query parameters, or headers are mapped incorrectly.
- JSON fails to deserialize properly, or responses have field names, data types, or date/time formats that violate the API contract.
- Validation does not run, constraints are missing, or validation errors are translated into inconsistent responses.
- Exceptions are mishandled, exposing stack traces or turning business errors into unnecessary HTTP 500 responses.
- Content types, encodings, pagination, or sorting are handled incorrectly.
- Requests are accepted despite missing required data, or rejected despite being valid.

Slice testing with `@WebMvcTest` sets up the necessary MVC layer without initializing the whole application. You can replace services with mocks to focus on mapping, validation, and response formatting. The example below uses `@MockitoBean` from Spring Framework 6.2 onward; on older Spring Boot versions, projects may use `@MockBean`.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void rejectsAnInvalidCreateRequest() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"", "items":[]}
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

An endpoint test should verify both the status code and meaningful parts of the body. For validation errors, check the error structure that clients rely on; for business errors, check stable error codes rather than depending on internal messages that might change.

If the application uses WebFlux, test the reactive stack directly. Do not infer that an MVC test proves WebFlux behavior, as pipelines, return types, and backpressure handling differ.

## 4. Authentication and Authorization

A request may carry valid data yet still be dangerous if the caller lacks permission to perform the operation. Security risks often lie in filter chains, role-based permissions, resource-level permissions, or method security not being applied consistently.

Separately verify these scenarios:

- An unauthenticated user accesses a resource requiring authentication.
- An authenticated user lacks the role or permission to invoke an endpoint or method.
- A user authorized for their own resource cannot access another user's resource.
- Tokens are expired, have invalid signatures, have the wrong issuer, or lack required claims.
- CSRF, CORS, and session policies are configured properly for the client type.
- Method-level permissions (`@PreAuthorize`, for example) still apply when the method is called through real execution paths.

With Spring Security Test, you can construct requests carrying mock identities to verify policies without calling a real authentication provider:

```java
mockMvc.perform(get("/admin/reports")
        .with(user("linh").roles("USER")))
    .andExpect(status().isForbidden());
```

Do not test only the allowed case. An authorization test suite needs denied cases as well, especially cross-user or cross-tenant data access. An authorization flaw is usually more severe than a response formatting bug, so prioritize testing at both endpoints and business-layer permission boundaries.

## 5. Persistence, Mapping, and Transactions

A repository may return accurate results for simple data yet fail when facing entity relationships, constraints, data types, or real transactional behavior.

Common risks:

- Entity mappings have incorrect column names, data types, primary keys, or relationships.
- Cascade and orphan removal delete or retain data unexpectedly.
- Lazy loading fails after a session closes, or causes N+1 queries.
- Queries work on H2 yet behave differently on PostgreSQL, MySQL, or the database engine used in production.
- Unique constraints, foreign keys, nullability, or indexes fail to reflect business rules.
- Transactions commit too early, fail to roll back properly, or persist only part of multiple operations.
- Isolation levels fail to satisfy requirements when concurrent requests update the same data.

`@DataJpaTest` is well suited for checking mappings and repositories. When testing saving and reloading an entity, call `flush()` and then `clear()` before querying again. This forces the persistence context to push changes to the database and avoids reading back the same in-memory instance.

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @PersistenceContext
    EntityManager entityManager;

    @Test
    void persistsAndReloadsAnOrder() {
        Order saved = orderRepository.save(new Order("customer-42"));

        entityManager.flush();
        entityManager.clear();

        Order reloaded = orderRepository.findById(saved.getId())
            .orElseThrow();

        assertEquals("customer-42", reloaded.getCustomerId());
    }
}
```

The snippet illustrates the idea; constructors and getters must match your project's entity. If production uses a specific database engine, add integration tests against the same database type, typically launched via Testcontainers. Substitute databases in fast test suites remain useful, yet cannot prove every difference in dialect, locking, JSON columns, sequences, collation, or constraints.

Transactions should be tested at the service level when a business operation involves multiple steps. For example, placing an order might create the order, deduct inventory, and write history. If the final step fails, prior state must roll back as required. Both the success path and mid-flow failure paths need verification.

Note that many slice tests run inside a transaction and roll back when finished. This is convenient for data isolation, yet can mask actual commit behavior, `afterCommit` events, or transactions opened on another thread. For such cases, design integration tests with explicit transaction boundaries and verify state from a new transaction or connection.

## 6. Integration with External Services

Spring applications frequently call payment APIs, identity services, email systems, file storage, message brokers, or other internal services. Risks include not only success or failure responses, but also timeouts, malformed responses, transient errors, rate limits, and uncertain state after a dropped connection.

For each integration, identify and test:

- Connection and read timeouts have reasonable bounds.
- 4xx, 5xx, timeout, and network errors are classified accurately.
- Retries apply only to retryable errors; non-idempotent operations are not retried blindly.
- Clients handle responses with missing fields, null fields, or invalid formats.
- Secrets, tokens, and authorization headers are sent properly without appearing in logs.
- When an external service goes down, the application returns a controlled state and does not hold resources indefinitely.

For HTTP clients, you can use a mock server to control responses and verify outgoing requests. With Spring Boot, `@RestClientTest` supports testing certain client configurations; `MockRestServiceServer`, WireMock, or MockWebServer are options depending on the client type. For real message brokers or databases, Testcontainers helps test protocols and configuration closer to the runtime environment.

Mocks make it fast to simulate rare situations like timeouts or error responses. Still, at least one integration test layer should verify that endpoints, serialization, authentication, and connection settings actually align with the target system or a reliable simulation.

## 7. Asynchronous Tasks, Schedulers, and Events

Annotations like `@Async`, `@Scheduled`, and the application event mechanism change execution timing. A call returning successfully may only mean the task was queued, not that the work has completed.

Risks to verify:

- Tasks are never dispatched to the executor, or the executor becomes saturated.
- Exceptions in background threads go unobserved and unhandled.
- Tests finish before the task completes, creating flaky results.
- Schedulers run duplicates, use the wrong timezone, or fire repeatedly across multiple application instances.
- Events are published before the transaction commits, causing listeners to read uncommitted data.
- A message or event is delivered multiple times while the handler is not idempotent.

Avoid using `Thread.sleep()` with arbitrary durations to wait for tasks. Wait via `Future`/`CompletableFuture`, latches, or a condition-waiting library like Awaitility with an explicit timeout. For schedulers, extract business logic into a service that can be called directly in unit tests; then verify trigger configuration and scheduler registration at the integration level.

If a listener needs to run after transaction commit, test that exact timing by reading data from an independent transaction. For message consumers, verify ack/nack, retries, dead-letter handling, and duplicate-processing safety according to system policy.

## 8. Caching and Shared State

Caching can reduce load, yet easily causes stale data bugs or cross-user data leaks if keys omit essential context. Tests should confirm:

- Cache keys properly distinguish tenants, users, or parameters that affect the outcome.
- Data is evicted or updated after write operations.
- TTL and expiration policies are appropriate.
- Cache misses, cache errors, or cache unavailability do not break business flows unexpectedly.
- Concurrent requests do not produce corrupted state due to race updates.

For `@Cacheable` and `@CacheEvict`, invoke the bean through the Spring context so the proxy is applied. Verify both the returned result and the number of times the underlying service or repository is actually called. If using a distributed cache in production, a test with an in-memory cache is not enough to prove serialization, key structure, or eviction behavior across a distributed system.

## 9. Performance and Fault Tolerance

A functional test may run quickly with a few records yet slow down severely as data grows. Common culprits are N+1 queries, missing indexes, unbounded queries, holding transactions too long, connection pool exhaustion, or synchronized retry storms increasing load when an external service struggles.

Define meaningful thresholds for the product up front: response time, throughput, connection counts, batch sizes, message processing latency, and error rates. Use data approximating real distributions to test high-risk flows. For databases, inspect SQL and query plans; for HTTP clients, observe timeouts and retry counts; for executors, check queue depth and thread counts.

Load testing and resilience testing suit these goals. They complement unit and integration tests rather than replacing logic checks. When retries, circuit breakers, or concurrency limits are present, test both normal conditions and scenarios where dependencies are slow or unresponsive.

## 10. Error Observability and Information Protection

When errors occur in production, logs, metrics, and traces help identify root causes. Yet excessive logging or writing sensitive data into logs introduces risks of its own.

Verify that:

- Important errors are recorded with an appropriate correlation ID or trace ID.
- Logs provide sufficient diagnostic context without containing passwords, tokens, secrets, or unnecessary personal data.
- Metrics distinguish business errors from infrastructure errors while avoiding high-cardinality labels.
- Exceptions are translated into contract-compliant responses without leaking internal details.
- Health checks accurately reflect the state of essential dependencies; never mark the application healthy when a required component has lost connectivity.

You do not necessarily need to assert exact log wording. Check operationally meaningful properties, such as the presence of a correlation ID, the error category, the absence of tokens, and no stack traces leaked in public responses.

## 11. Runtime Environment, Migrations, and Application Lifecycle

An application may run fine in an IDE yet fail when packaged or deployed. Differences often stem from environment variables, timezones, locales, file permissions, database migrations, startup ordering, or shutdown behavior.

Scenarios to consider:

- Required properties are not supplied in the deployment environment.
- Migrations fail when run against schemas containing legacy data or when multiple instances start concurrently.
- The application interprets time in a timezone different from business expectations.
- Graceful shutdown fails to wait for in-flight requests or messages per policy.
- Health/readiness checks allow traffic before the application is ready.
- Differences in JDK versions, libraries, or logging configuration alter behavior.

These risks must be tested in packaging pipelines, staging environments, or deployment environments close to production. Testing in a single isolated context cannot prove complete behavior during rollouts, restarts, or schema upgrades.

## 12. Choosing the Right Test Layer

Not every risk requires `@SpringBootTest`. Choose the test layer based on the failure mechanism and the evidence you need to collect.

| Test Layer | Best Suited to Verify | Example Tools / Approaches |
| --- | --- | --- |
| Unit test | Pure business rules, conditional branches, calculations, and error handling | JUnit 5, Mockito; instantiate objects directly when Spring is unnecessary |
| Spring context test | Bean wiring, profiles, properties, and application configuration | `@SpringBootTest`, contexts from Java/XML config |
| Slice test | A specific Spring boundary | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest` in Spring Boot |
| Integration test | Multiple components collaborating with a database, broker, or mock service | Testcontainers, WireMock, mock servers |
| Contract test | Agreement between two systems on requests, responses, and schemas | Consumer/provider contracts or schema validation |
| End-to-end test | User flows crossing major boundaries | Staging environment or integrated test environment |
| Load/resilience test | Latency, throughput, and behavior under degraded dependencies | Load generators, metrics, traces, and fault injection |

Unit tests should make up the majority because they are fast and make failures easy to pinpoint. However, Spring-introduced risks such as proxies, filter chains, mappings, transactions, and context configuration need tests that exercise the corresponding Spring mechanisms.

`@SpringBootTest` is useful when nearly the entire application needs to start, but using it for everything slows the suite down and makes small configuration failures hard to isolate. Slice tests narrow the scope; integration tests with real infrastructure uncover differences mocks cannot simulate.

## 13. Risk and Required Evidence Matrix

The following table suggests how to turn a risk into an observable verification. Final priority depends on business impact, likelihood, and post-deployment detectability.

| Risk | Potential Consequence | Test Evidence to Collect |
| --- | --- | --- |
| Misconfigured bean or profile | Application fails to start or uses the wrong implementation | Context starts; key beans and properties match the target profile |
| Proxy not applied | Transactions, caching, or async fail to activate | Invoke bean through context and observe real side effects |
| Wrong API mapping/validation | Clients get wrong responses or invalid data slips through | Real HTTP requests via MockMvc/WebTestClient; verify status and body |
| Missing authorization | Unauthorized users read or modify data | Unauthenticated, forbidden, and cross-resource access scenarios |
| Wrong database mapping/query | Data loss, query errors, or poor performance | Flush/clear/readback; constraints and queries on a production-compatible database |
| Non-atomic transaction | Business operation persists only partially | Induce failure mid-flow and verify proper rollback/commit |
| Slow or failing external service | Hung requests, excessive retries, or uncertain state | Timeouts, network errors, 4xx/5xx, and controlled retries in a mock server |
| Background task/event timing bug | Lost, duplicated, or uncommitted data processing | Wait for completion with timeout; verify idempotency and event timing |
| Wrong cache key or missing eviction | Stale data returned or user data mixed | Verify keys, invocation counts, and post-update behavior |
| Overload or resource exhaustion | Rising latency, cascading failures | Load tests, pool/executor metrics, and degraded dependency tests |
| Sensitive data in logs/responses | Secret or personal data leakage | Verify responses and logs omit sensitive fields |
| Deployment migration/startup failure | Unable to roll out or restart safely | Run migrations on populated schemas; check readiness and shutdown |

## 14. Building a Business-Flow-Driven Test Strategy

Start from a high-value flow, such as creating an order. List the boundaries the flow crosses: controller, authentication, service, transaction, repository, payment gateway, and events published after a successful save. For each boundary, identify what can go wrong and choose the matching verification.

Example for an order creation flow:

1. **Service unit tests:** verify total calculation rules, order status transitions, and invalid-order rejection conditions.
2. **MVC/security slice:** send valid and invalid HTTP requests; check validation, authentication, and data ownership.
3. **Repository integration:** save and reload orders; verify relationships, constraints, and queries on a compatible database.
4. **Transaction integration:** make the payment or persistence step fail; verify state rolls back or transitions to the compensating state as designed.
5. **External client test:** simulate payment timeouts, rejections, and successes; verify timeouts, retries, and idempotency.
6. **Event test:** verify events are emitted only at the right moment and consumers handle duplicates safely.
7. **End-to-end test:** run a happy-path flow through an integrated environment to verify overall configuration and wiring.

You do not need to put every combination into end-to-end tests. Business branches belong in unit or slice tests; end-to-end tests should keep only representative, high-value flows that confirm components are wired together properly.

## 15. Testing Practices That Create a False Sense of Security

A test suite with many tests can still miss risks if every test checks the same layer of behavior. Watch out for these situations:

- **Mocking every dependency:** tests prove the class's internal logic but do not prove Spring injects the right bean, proxies work, or queries execute.
- **Testing only the happy path:** timeouts, denied permissions, rollbacks, and boundary data are usually where risks concentrate.
- **Using only a substitute database:** fast tests help, yet dialect and constraint differences may appear only on the production database.
- **Instantiating with `new` in every test:** appropriate for pure unit tests, but skips container- and proxy-based behavior.
- **Using `@SpringBootTest` for every test:** slows down the suite and makes minor configuration issues harder to isolate.
- **Waiting for tasks with fixed `Thread.sleep()`:** easily creates flaky tests sensitive to machine load and execution timing.
- **Using shared data or relying on execution order:** causes outcomes to vary with test order, parallel runs, or environment state.
- **Checking only the status code:** a response may return 200 with wrong data, or an error may have the right status but the wrong error code expected by clients.

A good test must have clear input conditions, a specific action, and observable outcomes. For critical risks, test both normal conditions and at least one likely failure scenario.

## 16. Guiding Questions When Designing Tests

Before writing tests for a Spring feature, ask yourself:

- Which components does Spring create or configure, and what happens if they are misconfigured?
- Which behaviors depend on proxies, transactions, security filters, serializers, or lifecycle?
- Which boundaries call external systems, and what happens when those systems are slow or unresponsive?
- Which data could be partially written, misread, served stale from cache, or accessed without authorization?
- Does the current test actually pass through the mechanism that needs verification?
- Which results prove the risk is controlled, and which merely prove a mock was called?
- Do we need a real database, broker, or production-like environment to catch configuration differences?

Answering these questions helps the team choose a balanced test suite: unit tests protect business rules, slice tests verify Spring boundaries, integration tests confirm infrastructure and configuration, and end-to-end along with load/resilience tests validate high-impact flows. The goal is to produce evidence matched to the application's actual risks, so bugs are caught where they are easiest to understand and fix.
