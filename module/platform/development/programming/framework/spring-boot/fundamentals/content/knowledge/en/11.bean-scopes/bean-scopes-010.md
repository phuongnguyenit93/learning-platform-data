# Choosing a Scope by Data Lifetime and Usage Pattern

In Spring, **bean scope** determines the boundary under which the container creates and provides an instance. A bean can be shared across the entire application, created anew on each request to the container, or tied to the lifecycle of an HTTP request, an HTTP session, or a WebSocket session.

Choosing a scope is a decision about **data lifetime and how the object is used**. If a service does not hold per-user state, the default `singleton` scope usually fits. If an object holds data meaningful only within one request, `request` may fit. If data must persist across multiple requests in the same user session, consider `session`. For objects requiring a fresh instance each time they are requested from the container, `prototype` can be used.

Do not pick a scope just because an annotation name sounds appealing. Determine how long the data lives, who shares it, which threads can access it concurrently, and who is responsible for resource cleanup.

## 1. What Problem Does Bean Scope Solve?

A Spring Boot application can have multiple collaborating beans:

~~~text
HTTP request
     |
     v
OrderController
     |
     v
OrderService
     |
     +------> OrderRepository
     |
     +------> PricingService
~~~

With the default `singleton` scope, each bean definition is typically instantiated once by the container and reused throughout the `ApplicationContext` lifecycle. Many requests can pass through the same `OrderService`, `OrderRepository`, and `PricingService`.

This works very well when those beans mainly contain stateless logic or immutable configuration. However, if `OrderService` stores the current request's data in a field, requests can overwrite each other's data.

~~~java
@Service
public class UnsafeOrderService {
    private Long currentCustomerId;

    public void placeOrder(Long customerId) {
        this.currentCustomerId = customerId;
        // Further processing based on currentCustomerId...
    }
}
~~~

If two requests run concurrently on the same singleton, the second request can change `currentCustomerId` while the first request has not finished yet. This is a shared-state bug, not a bug in how Spring injects dependencies.

Bean scopes let you choose an instance lifecycle better suited to the need. Even so, scope does not automatically solve all concurrency or security issues; it only defines the boundary within which an instance is shared.

### Scope Differs from Component Scan Scope

Two concepts are frequently confused:

| Concept | Question |
|---|---|
| Component scan | In which packages does Spring look for candidate classes to register beans? |
| Bean scope | Within what lifecycle boundary are bean instances created and reused? |

A class can be discovered via `@ComponentScan` yet have `singleton`, `prototype`, or web scope. Conversely, placing `@Scope("request")` on a class does not automatically register it without component scanning, `@Bean`, or another registration mechanism.

## 2. Common Spring Scopes

Spring Framework provides the following core scopes. Web scopes require an appropriate web environment; not every scope can be used in every type of `ApplicationContext`.

| Scope | Instance lifecycle | Common use cases |
|---|---|---|
| `singleton` | One instance per bean definition within one Spring container | Stateless services, repositories, configuration, shared clients |
| `prototype` | Container creates a new instance each time the bean is requested via the corresponding lookup | Objects with private state for each usage |
| `request` | One instance for the duration of one HTTP request | Metadata or data belonging strictly to a single request |
| `session` | One instance for the duration of one HTTP session | Shopping cart or workflow state spanning multiple requests |
| `application` | One instance bound to the web application's `ServletContext` | Shared state at the servlet application level |
| `websocket` | One instance per WebSocket session | State dedicated to a WebSocket connection |

`singleton` is the default scope for Spring beans. `request`, `session`, `application`, and `websocket` scopes typically only make sense when the application has a web context and the corresponding scope mechanism is registered.

An important note: singleton does not mean "one unique instance across the entire JVM." It means one instance per **bean definition within one container**. Two separate `ApplicationContext` instances can hold two different singletons; the same class can also be registered as two bean definitions and produce two instances.

## 3. Singleton: Sharing One Instance Within a Container

### 3.1. How It Works

If no scope is specified, a bean usually has singleton scope:

~~~java
@Service
public class TaxCalculator {
    public long calculate(long amount) {
        return amount / 10;
    }
}
~~~

You can declare it explicitly:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
public class DefaultPricingPolicy {
    // ...
}
~~~

`ConfigurableBeanFactory.SCOPE_SINGLETON` has the value `singleton`. However, for ordinary beans, there is no need to write the annotation just to restate the default.

Spring creates and retains the singleton instance in the container; when other beans inject it, the container supplies that same instance. Creation normally happens during `ApplicationContext` initialization for eager-init singletons, though it can be deferred if the bean is configured as lazy.

### 3.2. When Does Singleton Fit?

Singleton fits components that:

- Contain business logic without holding per-request mutable state.
- Share configuration, serializers, mappers, or safely reusable clients.
- Are repositories/services coordinating shared resources.
- Can be called concurrently by multiple threads while preserving correctness.

Example of a stateless service receiving data via parameters:

~~~java
@Service
public class DiscountService {
    public long calculate(long unitPrice, int quantity, int percent) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("Invalid input data");
        }
        return unitPrice * quantity * (100 - percent) / 100;
    }
}
~~~

Each invocation keeps its own data in local variables. There is no need to create a new service per request.

### 3.3. Singleton Is Not Automatically Thread-Safe

Singletons are usually shared across multiple requests and threads. If a bean contains mutable fields, concurrent access must be controlled.

Unsafe:

~~~java
@Service
public class SequenceService {
    private long sequence = 0;

    public long next() {
        return ++sequence;
    }
}
~~~

Incrementing a field is not automatically atomic. If multiple threads call it simultaneously, updates can be lost.

If a shared counter within one JVM is genuinely needed, an appropriate concurrency type can be used:

~~~java
@Service
public class SequenceService {
    private final AtomicLong sequence = new AtomicLong();

    public long next() {
        return sequence.incrementAndGet();
    }
}
~~~

`AtomicLong` protects atomic updates within this process/JVM. If the application runs multiple instances, each instance still has its own counter; when a system-wide sequence is needed, use a shared mechanism such as a database sequence or dedicated service.

Do not pick `prototype` merely to avoid thread safety if data actually needs to be shared. Clearly identify who owns the state and the proper synchronization mechanism.

## 4. Prototype: Creating a New Instance When Requested

### 4.1. How to Declare

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private String title;

    public void setTitle(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Each time the prototype bean is requested from the container, Spring creates a new instance and performs dependency injection along with necessary initialization steps.

For example, when retrieved via `ApplicationContext`:

~~~java
ReportDraft first = context.getBean(ReportDraft.class);
ReportDraft second = context.getBean(ReportDraft.class);

System.out.println(first == second); // false
~~~

Two lookups yield two different instances (assuming no other mechanism alters bean provisioning).

### 4.2. Prototype Does Not Mean Every Service Call Gets a New Instance

A commonly misunderstood situation:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    // ...
}

@Service
public class ReportService {
    private final ReportDraft draft;

    public ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
~~~

`ReportService` is a singleton by default. When Spring creates this singleton, it resolves the constructor and supplies one `ReportDraft` instance at that time. The service retains that instance in a field; subsequent calls to `ReportService` keep using the same `draft`.

Diagram:

~~~text
ApplicationContext
       |
       | creates singleton once
       v
ReportService
       |
       +---- ReportDraft instance A
                    |
          service calls
          keep referencing A
~~~

If a fresh `ReportDraft` is needed each time a report is generated, request the instance at the time of use:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> draftProvider;

    public ReportService(ObjectProvider<ReportDraft> draftProvider) {
        this.draftProvider = draftProvider;
    }

    public ReportDraft newDraft() {
        return draftProvider.getObject();
    }
}
~~~

`ObjectProvider<T>` is Spring's abstraction for retrieving beans on demand. Each `getObject()` call for a prototype bean causes the container to provide a new instance.

You can use a plain Java factory instead of `ObjectProvider` if the object is ordinary data and needs no Spring-managed creation or scoping. Prototype scope is useful when you want the container to perform initialization, inject dependencies, or apply Spring mechanisms to each instance.

### 4.3. The Container Does Not Fully Manage Prototype Destruction

For singletons, the container can call destruction callbacks when the context closes. For prototypes, Spring creates, configures, and initializes the instance and then hands it to the client; it does not track the entire usage lifetime of each instance to automatically call destruction callbacks when the object is no longer referenced.

If a prototype holds resources such as file handles, sockets, or streams, the receiving side must take responsibility for closing resources under an appropriate design. This is one reason not to use prototype for every stateful object.

## 5. Request Scope: One Instance Within One HTTP Request

### 5.1. When to Use Request Scope?

An HTTP request can pass through multiple components:

~~~text
HTTP request A
      |
      v
Controller
      |
      v
Service
      |
      v
Audit component
~~~

Multiple components may need shared information meaningful only for the current request, such as a correlation ID, normalized metadata, or a temporary context object.

A request-scoped bean provides one instance throughout the request. The next request gets a different instance.

### 5.2. Declaring with @RequestScope

~~~java
package com.example.store.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {
    private final String requestId = UUID.randomUUID().toString();

    public String requestId() {
        return requestId;
    }
}
~~~

`@RequestScope` is a convenience annotation for `request` scope. In standard usage, it uses a scoped proxy so the request-scoped bean can be injected into longer-lived beans such as singletons.

A singleton service can receive that dependency via its constructor:

~~~java
@Service
public class AuditService {
    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public void record(String action) {
        System.out.println(
                metadata.requestId() + " - " + action
        );
    }
}
~~~

`AuditService` is a singleton, yet the `metadata` field is provided through a proxy. When `metadata.requestId()` is called during an active HTTP request, the proxy forwards the call to the instance matching the current request.

### 5.3. Request Scope Requires an Active Web Request

Request scope depends on the HTTP request context managed by Spring. If a task runs on a background thread, scheduler, or message listener without a corresponding request context, accessing a request-scoped bean can fail.

Do not retain a request context and use it arbitrarily after the request has finished. If data must be passed to a background task, pass a command/event containing the needed values:

~~~java
public record ProcessOrderCommand(
        Long orderId,
        String requestedBy,
        String correlationId
) {}
~~~

The background task receives explicit data via messages or parameters. This avoids depending on a request scope that no longer exists.

Request scope fits when multiple components within the same request need to share temporary state. If data is used by only one method, local variables or parameters are usually simpler.

## 6. Session Scope: One Instance Across an HTTP Session

### 6.1. How Session Scope Differs from Request Scope

A user can send multiple requests within the same HTTP session:

~~~text
User A's HTTP session
   |
   +-- Request 1: browse products
   |
   +-- Request 2: add product to cart
   |
   +-- Request 3: update quantity
   |
   +-- Request 4: view shopping cart
~~~

Request scope creates a new instance per request. Session scope keeps the instance across the session, so data can persist across multiple requests.

A classic example is a shopping cart not yet saved as an order. However, if the cart must survive user logout, logging in on another device, or syncing across devices, a database or shared store may fit better than session scope.

### 6.2. Declaring @SessionScope

~~~java
package com.example.store.cart;

import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class ShoppingCart {
    private final Map<Long, Integer> quantities = new HashMap<>();

    public synchronized void add(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        quantities.merge(productId, quantity, Integer::sum);
    }

    public synchronized Map<Long, Integer> snapshot() {
        return Map.copyOf(quantities);
    }

    public synchronized void clear() {
        quantities.clear();
    }
}
~~~

`@SessionScope` is a convenience annotation for `session` scope. A singleton service can inject `ShoppingCart` via its constructor:

~~~java
@Service
public class CartService {
    private final ShoppingCart cart;

    public CartService(ShoppingCart cart) {
        this.cart = cart;
    }

    public void add(Long productId, int quantity) {
        cart.add(productId, quantity);
    }

    public Map<Long, Integer> view() {
        return cart.snapshot();
    }
}
~~~

A scoped proxy ensures the service uses the instance bound to the current session when methods are called inside a request with a valid session.

The example above uses `synchronized` to illustrate protecting operations on mutable state. One HTTP session can still receive multiple concurrent requests—for example, a user opening multiple tabs. For complex read-modify-write operations, define atomicity and synchronization strategies explicitly; session scope alone does not protect data from race conditions.

### 6.3. Session Scope Requires Data and Infrastructure Considerations

Sessions typically outlive requests, so pay attention to:

- **Size:** do not store bulky objects or unnecessary data in the session.
- **Security:** do not use session beans as arbitrary stores for secrets or sensitive credentials.
- **Expiration:** sessions can expire; data inside them is not durable storage.
- **Multiple application instances:** if a load balancer distributes requests across multiple servers, sessions need sticky sessions or an appropriate shared session store.
- **Serialization:** some session stores require serializable data or impose specific storage rules.
- **Concurrency:** multiple requests in the same session can access the same state.

If data has long-term business value—such as orders, payments, or asset ownership—store it in a durable data system and use sessions only for appropriate interactive state.

## 7. Application Scope: Tied to ServletContext

`application` scope provides one instance within the `ServletContext` of a web application. It can be used to share an object across requests within the same servlet application.

~~~java
@Component
@ApplicationScope
public class ApplicationBanner {
    private final String message = "Store is running";

    public String message() {
        return message;
    }
}
~~~

`@ApplicationScope` is Spring's convenience annotation for web application scope.

Distinguish application scope from singleton:

- `singleton` binds to a bean definition in a Spring container.
- `application` binds to the `ServletContext` of a web application.

In a simple application with one `ApplicationContext` bound to one `ServletContext`, the two scopes can behave similarly. However, in applications with multiple contexts or complex servlet structures, their boundaries can differ.

Application scope is not a distributed data store across multiple JVMs or servers. If an application is deployed across three instances, each `ServletContext` has its own application-scoped object. Cluster-wide shared data requires a shared system such as a database, distributed cache, or appropriate service.

Normally, shared services and configuration in a Spring Boot application should use singleton. Only choose application scope when you genuinely need semantics bound to `ServletContext`.

## 8. WebSocket Scope: One Instance per WebSocket Session

WebSocket creates a long-lived, bidirectional connection between client and server. One connection can receive many messages during the session's lifetime. When per-connection state is needed, WebSocket scope can fit.

Conceptual example:

~~~java
@Component
@Scope(
        scopeName = "websocket",
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class WebSocketConversation {
    private String lastTopic;

    public void selectTopic(String topic) {
        this.lastTopic = topic;
    }

    public String lastTopic() {
        return lastTopic;
    }
}
~~~

This bean is intended for Spring WebSocket environments where the corresponding scope is registered, typically within an appropriate messaging/WebSocket configuration. If the application does not enable the required WebSocket infrastructure, the `websocket` scope may not be registered and bean creation will fail.

WebSocket scope differs from HTTP session scope: one user can have multiple WebSocket sessions, and each connection may need isolated state. If the application needs to share data across connections or multiple servers, a separate storage/sharing mechanism is required.

## 9. Choosing Scope by Data Lifecycle

Instead of starting from annotations, start with the question: **how long must the data held by the bean live, and who is it shared with?**

~~~text
Data only serves one calculation?
       |
       +-- Yes --> Local variable / plain Java object
       |
       +-- No
            |
            v
Data safely shared across the app?
       |
       +-- Yes --> Singleton
       |
       +-- No
            |
            v
Need a new instance each time container provides it?
       |
       +-- Yes --> Prototype or Factory
       |
       +-- No
            |
            v
Data tied to a web context?
       |
       +-- One HTTP request --> Request
       |
       +-- One HTTP session --> Session
       |
       +-- ServletContext --> Application
       |
       +-- One WebSocket session --> WebSocket
~~~

This is a guiding flowchart. In many cases, per-request data should be passed via parameters rather than creating request-scoped beans. Likewise, prototype is not the default answer for every object needing fresh instances; a plain Java factory can be simpler.

### Practical Decision Table

| Requirement | Usually suitable choice | Reason |
|---|---|---|
| Calculation service holding no request state | Singleton | Can be shared safely |
| Repository or client configured once and safe concurrently | Singleton | Resource reuse |
| Object with dedicated state for each report generation | Prototype or factory | Fresh instance per request to create |
| Correlation metadata used within one HTTP request | Request | Data ends when request ends |
| Temporary cart persisting across multiple requests in same session | Session | Lifetime matches user session |
| Configuration or object tied to `ServletContext` | Application | Shared within the web application |
| State specific to one WebSocket connection | WebSocket | Connection-bound lifecycle |
| Order data that must survive after session expiration | Database | Needs durability, not bean scope |

## 10. Do Not Use Bean Scope Instead of Passing Data via Parameters

A common design mistake is creating request-scoped beans for all request data, even when data is needed in just one method.

For example, instead of:

~~~java
@Service
public class GreetingService {
    public String greet(String customerName) {
        return "Hello " + customerName;
    }
}
~~~

there is no need to create a request-scoped bean just to hold `customerName`. Method parameters express the relationship much more clearly.

Distinguish:

- **Dependency:** stable collaborator a class needs, such as repository, gateway, policy.
- **Input data:** data varying per call, such as ID, quantity, command.
- **Stateful context:** state that must be shared across multiple components within a specific boundary, when genuinely justified.

Bean scopes should be used for the **lifecycle of collaborating objects**, not to turn every piece of data into a bean.

## 11. Scoped Proxy: How Does a Singleton Use Request/Session Beans?

A singleton service is created when the `ApplicationContext` starts, whereas request/session beans only have instances when a corresponding request/session is active. Injecting the target instance directly into a singleton causes a lifecycle mismatch.

Spring solves this with a **scoped proxy**. The proxy has a longer lifetime and is injected into the singleton; when a method is invoked, the proxy locates the target bean belonging to the active scope.

~~~text
ApplicationContext
      |
      v
Singleton AuditService
      |
      v
RequestMetadata proxy
      |
      +-- Request A --> RequestMetadata instance A
      |
      +-- Request B --> RequestMetadata instance B
~~~

`@RequestScope` and `@SessionScope` typically configure scoped proxies by default. You can also write it explicitly with `@Scope`:

~~~java
@Component
@Scope(
        value = WebApplicationContext.SCOPE_REQUEST,
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class RequestData {
    // ...
}
~~~

Import the corresponding types from `org.springframework.web.context` and `org.springframework.context.annotation`.

Two common proxy modes:

| Proxy mode | Meaning |
|---|---|
| `ScopedProxyMode.TARGET_CLASS` | Creates a class-based proxy (typically using CGLIB) |
| `ScopedProxyMode.INTERFACES` | Creates an interface-based proxy |

When using class proxies, `final` classes/methods or proxy mechanism limits can affect proxy creation. When using interface proxies, consumers must interact through the matching interface.

A scoped proxy does not mean the request-scoped bean becomes a singleton. The proxy is the shared object; **the actual target still changes per scope**.

### Using ObjectProvider Instead of a Proxy

You can inject `ObjectProvider<RequestData>` into a singleton and call `getObject()` inside an active request. This makes the bean retrieval point explicit, yet still requires the scope to be active. Pick proxy or provider depending on the API you want to express; do not use both just to add complexity.

## 12. Bean Lifecycle and Destruction Callbacks by Scope

Scope affects when beans are created and destroyed. Key differences:

| Scope | Instance creation | End of lifecycle | Cleanup notes |
|---|---|---|---|
| Singleton | Usually at context startup, or first use if lazy | When context closes | Container calls managed destruction callbacks |
| Prototype | Each time container is asked for the bean | After handoff to client, client manages it | Spring does not fully track and call destruction callbacks |
| Request | First time request needs the bean | When request completes | Web scope can invoke destruction callbacks |
| Session | First time session needs the bean | When session expires or is invalidated | Watch session storage and cleanup |
| Application | When `ServletContext` needs the bean | When web application shuts down | Depends on `ServletContext` lifecycle |
| WebSocket | When WebSocket session needs the bean | When WebSocket session closes | Depends on WebSocket scope infrastructure |

A singleton holding resources should close them safely on context shutdown. A prototype holding resources needs closing logic on the consumer side, since the container does not manage its full ending. Request/session scopes have cleanup tied to web lifecycles, though you should not assume callbacks always run if a process is abruptly killed.

## 13. Common Mistakes When Choosing Scope

### Mistake 1: Changing a Service to Prototype to Avoid Shared State

If a service holds per-request state, switching it to prototype might reduce instance sharing in a few setups, yet it does not fix the root cause if the service is still injected into a singleton. The singleton consumer only receives one prototype when created.

A better solution is usually removing request state from fields, passing data via parameters, or placing state in an appropriately scoped abstraction.

### Mistake 2: Thinking Request Scope Protects Data from All Concurrent Access

A request is typically handled on one thread at a time in standard servlet models, yet async processing and passing objects to other tasks can complicate contexts. Request scope is not a synchronization lock and should not be used as a concurrency control mechanism.

### Mistake 3: Using Session Scope as a Database

Sessions can expire, be evicted, or be lost when deployments lack suitable session persistence. Orders, payments, ownership, and auditable data must have durable storage.

### Mistake 4: Injecting a Prototype Directly into a Singleton and Expecting a New Instance Each Time

Prototypes are created when the singleton is wired, not swapped on every method call. Use `ObjectProvider` or a factory when fresh instances are truly needed.

### Mistake 5: Using Application Scope to Share Across Multiple Servers

Application scope binds only to one web application's `ServletContext`, not the entire cluster. Use a database, distributed cache, or shared service if multiple instances must see the same data.

### Mistake 6: Accessing Request/Session Beans Outside Web Contexts

A scheduler or message listener without a matching HTTP request/session cannot access web-scoped beans. Pass needed data into the task instead of relying on an ended web context.

### Mistake 7: Choosing Scope Without Considering Thread Safety

Scope defines instance boundaries, not safety of operations on mutable state. Singleton, session, and application beans can all be accessed concurrently by multiple threads.

## 14. Testing Beans by Scope

Scope also affects how tests are written. For singleton services, unit tests can instantiate the service directly or use a Spring context. For request/session scopes, tests need to establish the corresponding web context.

For instance, a Spring MVC test with `MockMvc` can dispatch two requests and assert that request-scoped data is not shared between them. For session scope, send multiple requests with the same session and verify state persists; then use a different session to verify isolated state.

Desired test diagram:

~~~text
Request A (session S1)
    -> Request bean A
    -> Session bean S1

Request B (session S1)
    -> Request bean B
    -> Session bean S1

Request C (session S2)
    -> Request bean C
    -> Session bean S2
~~~

Results:

- Request beans A and B differ because they belong to two requests.
- Session beans of A and B are identical because they share session S1.
- Session bean of C differs because it belongs to session S2.

This is the right way to verify scope semantics, rather than merely checking whether a class carries `@RequestScope` or `@SessionScope`.

For prototypes, tests can retrieve the bean multiple times via a provider and verify distinct instances. Remember prototype destruction is not fully managed by the container; if tests allocate resources, clean them up explicitly to avoid leaks.

## 15. Choosing Scope in Real-World Scenarios

### Scenario A: PricingService Doing Pure Calculations

`PricingService` takes price and quantity, returns total cost, and keeps no data across calls. Singleton is the right choice. Creating a new instance for every HTTP request brings no clear benefit.

### Scenario B: RequestMetadata Holding a Correlation ID

The correlation ID is determined per HTTP request and multiple components within that request need to read it. Request scope can fit. If only one service needs the ID, passing it via a command or context object may be simpler.

### Scenario C: ShoppingCart Holding Selected Items

The cart must persist across multiple requests of a user session. Session scope may fit simple apps, though you must evaluate concurrency, timeouts, memory size, and multi-device syncing. If the cart is critical data or needs durability, store it in an appropriate database/cache.

### Scenario D: ReportDraft Needing Dedicated State per Export

If each report generation needs an independent builder and that builder has dependencies Spring must inject, prototype or a factory can fit. If it is just a simple data object, instantiating with a Java constructor is usually easier.

### Scenario E: ApplicationBanner Shared in a Servlet App

If the banner is an immutable value, singleton is usually sufficient. Application scope should only be chosen when you explicitly want lifecycle bound to `ServletContext` or have web context structure reasons.

### Scenario F: ConversationState Tied to a WebSocket

If each connection needs private state and the app has WebSocket scope registered, `websocket` scope is an option. If clients can reconnect and must recover state, store data in an appropriate durable or shared store.

## 16. Mental Checklist Before Choosing a Scope

Before adding `@Scope`, answer these questions:

1. **Is the data truly bean state?** If it is just input parameters, use method arguments or commands.
2. **Who needs to share the state?** One method, one request, one session, one servlet application, or one WebSocket session?
3. **How long does the state live?** Within one call, one request, multiple requests, or the entire application lifecycle?
4. **Will multiple threads access it concurrently?** If so, design concurrency explicitly.
5. **Must the data survive process restarts or session expiration?** If so, bean scope is not persistence.
6. **Who closes resources?** Especially for prototypes or off-container resources.
7. **Which consumer scope injects this bean?** Singletons receiving prototypes directly can retain instances longer than intended; web scopes need proxies/providers.
8. **Does the application have the right context to use that scope?** Request/session/websocket scopes require corresponding infrastructure.

## 17. Self-Application Exercise

Suppose you are building a Spring Boot application for an online learning platform:

- `CourseCatalogService` reads the course list.
- `LearningProgressService` updates progress.
- `CurrentRequestInfo` holds the HTTP request correlation ID.
- `LearningSession` holds the currently selected lesson during an interactive session.
- `ReportBuilder` creates an independent report per export.

Choose a scope or object creation mechanism for each component and explain:

| Component | Question to think through |
|---|---|
| CourseCatalogService | Does it hold per-user state, or only execute logic and access data? |
| LearningProgressService | Should learning progress be stored in a bean or a database? |
| CurrentRequestInfo | Does the data exist only within one HTTP request? |
| LearningSession | Is "Session" here an HTTP session, a business learning session, or a WebSocket connection? |
| ReportBuilder | Does Spring need to manage a new instance per export, or is a Java factory enough? |

The name `LearningSession` does not decide the scope by itself. A business "learning session" might last for days and require database persistence, whereas an HTTP session expires after inactivity. Choose based on **actual lifecycle semantics**, not just class names.

## Conclusion

Choosing a bean scope is choosing the **sharing boundary and instance lifecycle**. Singleton fits most stateless services and safely shared components; prototype fits cases needing fresh instances when the container provisions them; request/session/application/websocket bind objects to the corresponding web boundaries.

Before changing a scope, determine how long data lives, who accesses it, whether concurrent access can occur, and who owns cleanup. Never use scope as a substitute for method parameters, databases, or synchronization mechanisms. When scopes accurately reflect data lifecycles, the Spring Boot object graph becomes easier to reason about, avoids cross-user state leakage, and behaves consistently in production environments.
