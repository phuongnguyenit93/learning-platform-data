# Boundaries Between Business Components, the Container, and External Infrastructure

When testing a Spring application, the first question should not be "which annotation should I use?" but rather "what do I want to verify?". A business rule can be correct even when Spring has not started. A Spring configuration can create the right beans yet still have a broken database query. A repository can pass against a test database yet fail when run on the database engine used in production.

To choose the right type of test, distinguish three boundaries:

1. **Business components** decide what the application must do.
2. **The Spring container** creates, wires, and manages components within the application.
3. **External infrastructure** provides capabilities outside the application process, such as databases, message brokers, Redis, or HTTP services.

These three boundaries interact when the application runs, yet each boundary poses a different testing question.

In this lesson, the word *container* refers to the **Spring IoC container** — the region where Spring manages beans. Docker containers or OS containers are a different infrastructure deployment concept; they can be used to launch databases and services for testing.

## 1. Viewing the Application Through Three Boundaries

A typical processing flow can be visualized as follows:

~~~mermaid
flowchart LR
    Client["HTTP / Message"] --> Adapter["Controller / Message Adapter"]
    Adapter --> UseCase["Application Service"]
    UseCase --> Domain["Domain Model / Business Rules"]
    UseCase --> Port["Port / Interface"]
    Port --> OutAdapter["Repository / HTTP Client / Broker Adapter"]
    OutAdapter --> Infra["Database / API / Broker"]

    Spring["Spring IoC Container"] -. "creates and wires beans" .-> Adapter
    Spring -. "creates and wires beans" .-> UseCase
    Spring -. "creates and wires beans" .-> OutAdapter
~~~

The diagram shows three kinds of responsibilities:

- The business flow determines the order and meaning of processing steps.
- The Spring container provides objects, injects dependencies, applies configuration, and manages lifecycles.
- Adapters communicate with external systems through the corresponding protocol or driver.

One component can participate in multiple relationships. For example, **OrderService** is a business component from the perspective of responsibility, while also being a Spring bean from the perspective of configuration. Being managed by Spring does not turn the business rules inside it into Spring's responsibility.

Also distinguish **logical boundaries** from **deployment boundaries**. A repository adapter running inside the same JVM is still an adapter targeting data infrastructure. Conversely, a Docker container may simply be a way to launch PostgreSQL for testing; it is not the Spring IoC container.

## 2. Business Components: Verifying the Application Makes Right Decisions

Business components express the rules and decisions of the application. Depending on the architecture, this group may include:

- Domain models, business entities, value objects, and domain services.
- Application services or use cases coordinating a business workflow.
- Policies, validators, calculators, and rules such as pricing, eligibility checks, or business authorization.
- Interfaces/ports describing capabilities the business logic needs from outside.

A well-designed business component usually receives dependencies via constructors or interfaces. Consequently, rules can be invoked directly in the JVM without starting Spring.

For example, a reservation service needs to know whether inventory has enough stock. The reservation rule can depend on a port:

~~~java
public interface StockPort {
    boolean hasEnough(String sku, int quantity);
}

public final class ReservationService {
    private final StockPort stockPort;

    public ReservationService(StockPort stockPort) {
        this.stockPort = stockPort;
    }

    public boolean canReserve(String sku, int quantity) {
        if (quantity <= 0) {
            return false;
        }
        return stockPort.hasEnough(sku, quantity);
    }
}
~~~

You can test the rule with JUnit without creating an **ApplicationContext**:

~~~java
class ReservationServiceTest {

    @Test
    void rejectsNonPositiveQuantity() {
        StockPort stock = (sku, quantity) -> true;
        ReservationService service = new ReservationService(stock);

        assertFalse(service.canReserve("BOOK-01", 0));
    }

    @Test
    void acceptsQuantityWhenStockIsEnough() {
        StockPort stock = (sku, quantity) -> quantity <= 5;
        ReservationService service = new ReservationService(stock);

        assertTrue(service.canReserve("BOOK-01", 3));
    }
}
~~~

Here, the lambda acts as a simple fake: it supplies a controlled response so the test focuses on **ReservationService**'s decision. If you need to verify a specific interaction, you can use a mock; if you need to simulate mutable state, an in-memory fake is often easier to read.

The goal of this test is to confirm that inputs and dependency state lead to the right business outcome. It does not prove that Spring registered **ReservationService**, that the repository runs valid SQL, or that the real database contains sufficient data.

### When Is Spring Not Needed?

There is no need to initialize Spring just because a class is named **Service**, or because in the live application that class is annotated with **@Service**. If a test only needs to verify a calculation, condition, or business decision, instantiate the object directly and supply suitable dependencies.

A Spring annotation may serve bean registration or runtime configuration. It is not necessarily part of the business algorithm. If a test must start the entire application to check a simple calculation, the test scope is broader than the question being asked.

Conversely, if the behavior under test depends on a transaction proxy, method security, caching, or another Spring-applied mechanism, instantiating the object with **new** bypasses that mechanism. In that case, you need a test that goes through the Spring container.

## 3. Spring Container: Verifying Configuration and How Components Are Wired

The Spring IoC container manages beans inside the **ApplicationContext**. The container is responsible for behaviors such as:

- Discovering or registering beans from component scanning, **@Configuration**, and other configuration mechanisms.
- Resolving dependencies and injecting beans into constructors, fields, or methods.
- Creating beans conditionally based on conditions, profiles, and properties.
- Managing lifecycles, scopes, and initialization/destruction callbacks.
- Applying **BeanPostProcessor** instances, AOP proxies, and integration mechanisms.
- Wiring components such as transaction managers, security, validation, caching, and web infrastructure.

Therefore, a test at the container boundary needs to answer questions about **runtime configuration**. For example:

- Under this profile or property set, which beans are created?
- Do two dependencies receive the right implementations?
- Does custom configuration apply alongside the expected auto-configuration?
- Does a method actually pass through a transaction proxy or security proxy?
- Is a controller recognized and mapped properly by Spring MVC?

You can use the Spring TestContext Framework to create a small context for the configuration you want to verify:

~~~java
@SpringJUnitConfig(ReservationConfiguration.class)
class ReservationWiringTest {

    @Autowired
    private ReservationService reservationService;

    @Test
    void createsReservationServiceBean() {
        assertNotNull(reservationService);
    }
}
~~~

This example verifies bean creation and injection from the specified configuration. It does not prove the reservation business logic is right in all situations; that belongs to business-component testing. Nor does it prove the adapter can connect to a real database.

If you need to test Spring Boot's conditional auto-configuration, **ApplicationContextRunner** helps spin up lightweight contexts for small sets of configuration/properties and inspect which beans are created. This is useful when confirming conditions that enable or disable a configuration without starting the entire application.

### Choosing an Appropriate Context Scope

Spring Boot offers several ways to create a context. Each has a different scope and purpose:

| Testing Approach | Primary Scope | Fitting Question |
|---|---|---|
| **@SpringJUnitConfig** / **@ContextConfiguration** | Specified Spring context | Do bean configuration and dependencies work? |
| **ApplicationContextRunner** | Small context initialized per run | Does auto-configuration create beans under the right conditions? |
| **@WebMvcTest** | Selected Spring MVC slice | Do mapping, binding, validation, and HTTP handling work? |
| **@DataJpaTest** | Relevant JPA components | Do entity mappings, repositories, and queries work? |
| **@JsonTest** | JSON configuration | Do serialization and deserialization work? |
| **@SpringBootTest** | Broader Spring Boot application context | Do major configurations and components collaborate? |

An annotation name does not automatically determine the strength of the proof. For example, a **@SpringBootTest** that replaces a repository with a mock still does not test queries against a real database. A **@DataJpaTest** running on H2 may confirm some JPA behaviors yet fail to faithfully reproduce PostgreSQL dialects, data types, or locking.

Choose the smallest context capable of verifying the behavior of interest. Smaller contexts typically start faster, are easier to understand, and point failures straight to the misconfigured area. Use a broad context only when collaboration across many configurations is itself what needs verification.

### Behaviors That Only Appear When Going Through the Container

Certain mechanisms cannot be thoroughly verified by calling an object directly:

- **Transaction proxies:** calling a method through a Spring-managed bean can open or join a transaction; calling a manually instantiated object directly skips that proxy.
- **AOP and method security:** the call must pass through the corresponding proxy or interceptor mechanism for the applied behavior to take effect.
- **Dependency injection:** only a context proves that beans are selected and wired properly according to configuration.
- **Conditional configuration:** results depend on the classpath, properties, profiles, or configuration conditions at context creation time.
- **Lifecycle:** initialization, destruction, or post-creation callbacks belong to the container-managed lifecycle.

When verifying these behaviors, obtain the object from the context and invoke it much like the real application does. Merely testing **new ReservationService(...)** cannot prove that a transaction proxy or Spring configuration is working.

## 4. External Infrastructure: Verifying Communication with Real Systems

External infrastructure refers to systems or resources whose lifecycle, protocol, state, or operation is independent of the application's internal business logic. Common examples:

- Relational databases such as PostgreSQL, MySQL.
- Redis or other storage systems.
- Kafka, RabbitMQ, and message brokers.
- Third-party HTTP services or other internal services.
- File systems, object storage, SMTP servers, and network services.

At this boundary, the question is not only "was the bean created?" but "does the adapter communicate properly with the system it represents?".

For persistence, for instance, behaviors to check may include:

- Do actual queries return the right data?
- Is the mapping between entities and schema accurate?
- Are constraints, indexes, data types, and migrations compatible?
- Do transactions, isolation, locking, and rollback satisfy requirements?
- Does the application handle connection errors or errors from the data system?

For HTTP clients or message adapters, questions may include:

- Do requests have the right method, path, headers, payload, and encoding?
- How are success, error, or malformed responses handled?
- Are timeouts, retries, and network errors handled according to defined policy?
- Do messages use the right schema, keys, headers, and acknowledgement mechanism?

### Real Systems or Simulation?

Not every test needs to connect to a shared service. You can choose from several levels of infrastructure substitution:

| Dependency Provisioning | Characteristics | Best Suited When |
|---|---|---|
| Stub | Returns predefined responses | Testing a specific processing branch |
| Mock | Records and verifies interactions | Verifying an important call or arguments |
| Fake | Simple implementation holding in-memory state | Simulating multi-step stateful behavior |
| In-memory implementation | Runs locally with its own semantics | Differences from the real system are acceptable |
| Protocol-level simulator | Simulates HTTP, SMTP, or brokers at the protocol level | Verifying request/response and error handling |
| Ephemeral real infrastructure | Launches a real database, broker, or service in isolation | Verifying compatibility with real technology |

Stubs, mocks, and fakes are useful for controlling scenarios. They do not prove that drivers, protocols, schemas, or connection settings to real infrastructure work properly.

For databases, H2 or an in-memory database enables fast testing, yet cannot be assumed equivalent to PostgreSQL or MySQL. Differences can arise in SQL dialects, data types, collations, constraints, sequences, locking, and transaction behavior. If the application relies on those characteristics, test against the exact database engine or an ephemerally launched compatible version.

**Testcontainers** is commonly used to run services such as PostgreSQL, Kafka, or Redis in an isolated test environment. Tests can start the service, configure the application to connect to the assigned address, and clean up resources afterward. Consequently, tests can verify adapter behavior against real technology without relying on a long-lived shared server.

For external HTTP services, you can use WireMock or MockWebServer to accept requests and return scripted responses. This verifies the HTTP adapter at the protocol boundary. It confirms the application builds requests and processes responses as expected, though it does not verify the real provider's internal state or logic.

### Isolated and Repeatable

Infrastructure tests require clear state management:

- Every test or test group must have deterministic input data.
- Created data must be cleaned up or placed in an isolated namespace/schema.
- Do not depend on test execution order or leftover data from prior runs.
- Ports, credentials, and endpoints should be supplied by the test environment rather than hardcoded.
- Timeouts and retries must be realistic without causing tests to hang for long periods.
- When tests run in parallel, avoid sharing stateful resources in ways that cause contention.

If a test fails because a shared database is busy or a third-party service drops connections, results become hard to reproduce. Ephemeral environments and isolated data keep failures reproducible and diagnosable.

## 5. One Use Case, Three Testing Questions

Suppose the application has a reservation use case. The use case receives a request, checks stock quantity, saves the reservation, and sends a notification.

You can split testing objectives into three groups:

| Boundary | What to Verify | Example |
|---|---|---|
| Business components | Is the reservation decision correct? | Invalid quantities are rejected; sufficient stock is accepted |
| Spring container | Are components wired properly? | Beans for **ReservationService**, repository, and publisher are injected per configuration |
| External infrastructure | Do adapters communicate properly with real technology? | Repository writes/reads on PostgreSQL; publisher sends messages via broker protocol |

A test suite can implement this as follows:

**At the business level**, instantiate **ReservationService** directly and use a fake **StockPort** to test sufficient stock, insufficient stock, and invalid quantities. These run fast and need no Spring.

**At the container level**, load a context with the application configuration or an appropriate slice. Verify that beans are registered, dependencies are injected, profiles/properties pick the right implementations, and required proxies take effect.

**At the infrastructure level**, run the repository adapter against an appropriate database, or run the publisher adapter against an ephemeral broker. Inspect data and messages on the receiving system to confirm the adapter implements the required protocol and semantics.

The three groups do not replace one another. A strong business test does not prove SQL is right. A test whose context starts successfully does not prove the database accepts the query. A repository test against a real database does not by itself prove every reservation rule is right.

## 6. Mistakes That Frequently Undermine Tests

### Using **@SpringBootTest** for Every Test

When every test starts the whole application, runtime grows and configuration errors can obscure business bugs. A simple calculation does not need a database, web server, or component scanning.

Let business-component tests run independently. Reserve Spring contexts for container-dependent behavior and infrastructure environments for behavior depending on external systems.

### Mocking the Repository and Concluding the Database Works

Mocking a repository only confirms that the caller invoked the repository according to the defined interaction. It does not execute SQL, check mappings, or run transactions on the database.

To verify persistence, you need tests that exercise the adapter and an appropriate database.

### Using an In-Memory Database and Assuming the Production Database Works Too

An in-memory database can be very useful, yet differences in dialect and semantics can let a query pass in tests while failing in deployment. Pick the database engine according to the features the application actually relies on.

### Instantiating Objects Manually Yet Expecting Spring Proxy Behavior

An object created with **new** does not gain transactions, AOP, or method security just because its class carries annotations. Those mechanisms must be applied through the corresponding container/proxy.

If the goal is to test proxies, retrieve the bean from **ApplicationContext** and call the method through that bean.

### Checking a Bean Exists and Concluding the Entire Flow Works

A bean existing only proves part of the configuration. It does not prove business logic, data queries, HTTP requests, or messages are right. Every conclusion must be tied to evidence the test actually observed.

### Using Transaction Rollback to Assume All Side Effects Are Undone

Database rollback does not retract sent emails, published messages, written files, or completed HTTP calls. For tests with side effects outside the transaction, design separate data isolation and cleanup, or use appropriate test-double adapters.

## 7. Choosing Boundaries from the Question to Answer

Before writing a test, frame the goal as a concrete question:

1. **"Does this rule make the right decision?"**  
   Test the business component directly with JUnit; provide dependencies via fakes, stubs, or mocks when needed.

2. **"Does Spring create and wire components properly?"**  
   Use Spring TestContext, **ApplicationContextRunner**, or a suitable Spring Boot test slice. Verify beans, configuration conditions, proxies, and related lifecycles.

3. **"Does the adapter work properly with the system it integrates with?"**  
   Test the adapter against a protocol-level simulator or ephemeral real infrastructure. Pick the exact technology when its semantics affect the outcome.

4. **"Do the major parts collaborate as an application flow?"**  
   Use broader integration tests, possibly **@SpringBootTest**, and decide explicitly which dependencies are real and which are substituted.

When a test fails, clearly defined boundaries help isolate the root cause. Calculation errors typically lie in logic or input data. Missing-bean errors usually belong to container configuration. SQL errors, timeouts, or broker connection failures typically belong to adapters, connection settings, or infrastructure.

## 8. Conclusion on Scope of Proof

Each kind of test proves only what it actually traverses and observes:

- Business-component tests prove rules execute properly under the supplied conditions.
- Spring container tests prove configuration and bean management work inside the constructed context.
- Infrastructure tests prove adapters communicate properly with the system or protocol used in the test.
- Broad integration tests prove selected components collaborate under a specific configuration.

When designing a Spring Framework test suite, keep these three boundaries distinct. An effective test suite does not come from piling on annotations or starting many components; it comes from each test producing the right evidence for the question it asks.

