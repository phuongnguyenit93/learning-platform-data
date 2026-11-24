# Request, Session, and Application Scopes in a Web Context

In Spring, **scope** defines the lifecycle and sharing boundary of a bean. The default scope is `singleton`: one instance per bean definition within a Spring container. For web applications running on the Servlet stack, Spring also provides scopes tied to HTTP lifecycles:

- **Request scope**: one instance per HTTP request.
- **Session scope**: one instance per user HTTP session.
- **Application scope**: one instance per web application `ServletContext`.

These scopes help place data where it needs to live. For example, metadata used only within a single request belongs in request scope; a user's temporary shopping cart might belong in session scope; a shared, mostly immutable catalog could belong in application scope.

What matters is understanding **how bean lifetimes differ**, even though all three are still managed by Spring as regular beans. They do not automatically make data durable, do not replace a database, and do not automatically solve concurrent access issues.

## 1. What Is a Scope?

Scope answers three questions:

1. When does the container create an instance of the bean?
2. Which accesses receive the same instance?
3. When does the instance end its lifecycle and get cleaned up?

In Spring Core, the two basic scopes encountered first are:

| Scope | Behavior |
|---|---|
| **singleton** | One instance per bean definition in a container; this is the default. |
| **prototype** | The container creates a new instance each time the bean is requested from the container. |

In Spring's web-aware context, additional scopes exist:

| Web scope | Instance boundary |
|---|---|
| **request** | One active HTTP request. |
| **session** | One active HTTP session. |
| **application** | One `ServletContext` of the web application. |

You can visualize the nested boundaries:

```text
Web application (ServletContext)
│
├── Request A
│   ├── Request-scoped bean A
│   └── Session-scoped bean of Session X
│
├── Request B
│   ├── Request-scoped bean B
│   └── Session-scoped bean of Session X
│
└── Request C
    ├── Request-scoped bean C
    └── Session-scoped bean of Session Y

Application-scoped bean:
  One instance within the ServletContext,
  shared by requests in the web application.
```

The diagram illustrates three requests across two sessions. Every request has its own context; multiple requests in the same session can access the same session-scoped bean; every session in the same `ServletContext` can access the application-scoped bean.

## 2. Web Scopes Only Work When an Appropriate Web Context Exists

Request, session, and application scopes rely on Spring's web infrastructure. They require a **web-aware ApplicationContext** and the corresponding scope must be active.

In a Spring MVC application running on the Servlet stack, Spring integrates request context via `DispatcherServlet` or the corresponding Servlet request-context mechanisms. A Spring Boot web application typically sets up the necessary infrastructure when configured appropriately for web.

If you create a plain Java `AnnotationConfigApplicationContext` without a web environment and request a request-scoped bean, Spring has no active HTTP request to identify an instance. Similarly, session scope cannot operate if there is no session attached to a request.

For example, if a bean is declared as:

```java
@Component
@RequestScope
public class RequestMetadata {
    // ...
}
```

and you try to retrieve this bean in a command-line application without requests, the container may throw an inactive scope error. The annotation does not fabricate a fake HTTP request on its own.

**Distinguish two things:**

- The bean definition can be registered when the application context starts.
- The target instance of request/session scope can only be obtained when the corresponding scope has a valid active context.

## 3. Request Scope: One Instance per HTTP Request

Request scope fits data that only makes sense within a single HTTP exchange, for example:

- Request ID / correlation ID.
- Trace information attached to the request.
- An object collecting temporary data while processing the request.
- Metadata extracted from headers or request attributes.

### 3.1. Declaring with `@RequestScope`

Example of a bean holding a request ID:

```java
package com.example.demo.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {

    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
```

`@RequestScope` is Spring's specialized annotation, equivalent to declaring request scope and defaulting to a class-based scoped proxy.

Each request gets its own target instance. When two different HTTP requests use the bean, they receive two different `RequestMetadata` instances.

### 3.2. Injecting a Request-Scoped Bean into a Singleton Service

Application services are typically singletons. If a singleton's constructor takes a request-scoped object directly, a mechanism is needed so the dependency resolves accurately to the current request.

Example:

```java
package com.example.demo.service;

import com.example.demo.web.RequestMetadata;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public void record(String action) {
        System.out.println(
                metadata.getRequestId() + " - " + action
        );
    }
}
```

Why does this not cause the singleton to hold onto a single request instance?

Because `@RequestScope` creates a **scoped proxy** by default. The `AuditService` singleton retains a reference to the proxy; when a method is invoked, the proxy locates the target instance matching the active request.

```text
ApplicationContext creates AuditService (singleton)
                │
                │ holds reference
                ▼
       RequestMetadata proxy
                │
         method is called
                │
        ┌───────┴────────┐
        ▼                ▼
    Request A        Request B
        │                │
        ▼                ▼
  Target A           Target B
  RequestMetadata    RequestMetadata
```

Proxies allow a longer-lived bean to reference a shorter-lived bean. Without a proxy or on-demand lookup mechanism, the singleton would either retain a target created at startup or fail to switch to subsequent requests.

### 3.3. Using `ObjectProvider` Instead of a Scoped Proxy

Another approach is injecting a provider and retrieving the target when needed:

```java
import com.example.demo.web.RequestMetadata;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final ObjectProvider<RequestMetadata> metadataProvider;

    public AuditService(
            ObjectProvider<RequestMetadata> metadataProvider) {
        this.metadataProvider = metadataProvider;
    }

    public void record(String action) {
        RequestMetadata metadata = metadataProvider.getObject();
        System.out.println(metadata.getRequestId() + " - " + action);
    }
}
```

`ObjectProvider` defers retrieving the bean until `getObject()` is called. This is a clear choice when code wants to emphasize that the dependency is looked up according to the active context.

Whether using a proxy or a provider, the request-scoped target is only meaningful when a request context is active. Calling `record()` from a background thread unrelated to a request will fail when retrieving `RequestMetadata`.

### 3.4. Controller Example Observing Request Scope

```java
package com.example.demo.api;

import com.example.demo.service.AuditService;
import com.example.demo.web.RequestMetadata;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequestController {

    private final RequestMetadata metadata;
    private final AuditService auditService;

    public RequestController(
            RequestMetadata metadata,
            AuditService auditService) {
        this.metadata = metadata;
        this.auditService = auditService;
    }

    @GetMapping("/request-info")
    public String requestInfo() {
        auditService.record("GET /request-info");
        return metadata.getRequestId();
    }
}
```

Send multiple requests to `/request-info`; each request returns the request ID generated for its corresponding target instance. Even if requests arrive within the same session or from the same browser, request scope still creates a new target per request.

## 4. Session Scope: One Instance per HTTP Session

**Session scope** is used when data must persist across multiple HTTP requests belonging to the same session. Examples:

- A user's temporary shopping cart.
- Selections in a multi-step wizard.
- Short-lived UI state tied to a working session.
- A small dataset reused across multiple requests.

Example:

```java
package com.example.demo.web;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class ShoppingCart {

    private final List<String> productIds = new ArrayList<>();

    public void add(String productId) {
        productIds.add(productId);
    }

    public List<String> getProductIds() {
        return List.copyOf(productIds);
    }

    public void clear() {
        productIds.clear();
    }
}
```

`@SessionScope` is Spring's specialized annotation for session scope and uses a scoped proxy by default.

A first request may create a session if the application needs to store state. Subsequent requests carrying the same session ID can access the same `ShoppingCart` target. A different session receives its own `ShoppingCart` target.

```text
Web application
│
├── Session X
│   ├── Request 1 ──┐
│   ├── Request 2 ──┼──> ShoppingCart X
│   └── Request 3 ──┘
│
└── Session Y
    ├── Request 4 ──┐
    └── Request 5 ──┴──> ShoppingCart Y
```

### 4.1. Injecting a Session Bean into a Singleton

```java
@Service
public class CartService {

    private final ShoppingCart cart;

    public CartService(ShoppingCart cart) {
        this.cart = cart;
    }

    public void addProduct(String productId) {
        cart.add(productId);
    }

    public List<String> currentProducts() {
        return cart.getProductIds();
    }
}
```

`CartService` can be a singleton. It holds a scoped proxy for `ShoppingCart`; when a method is invoked during a request, the proxy retrieves the target bound to the active session.

Controller:

```java
@RestController
@RequestMapping("/cart")
public class CartController {

    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @PostMapping("/{productId}")
    public List<String> add(@PathVariable String productId) {
        cartService.addProduct(productId);
        return cartService.currentProducts();
    }

    @GetMapping
    public List<String> view() {
        return cartService.currentProducts();
    }
}
```

Requests sharing the same session will observe the same product list. If no active session exists, Spring/the Servlet container may create a session depending on how it is accessed and configured; understand when your application creates sessions to avoid spawning unnecessary ones.

### 4.2. Session Scope Is Not a Database

Session-scoped beans typically store state in the web application's memory via the HTTP session. It does not automatically guarantee data survival across:

- Application restarts if sessions are not persisted/replicated.
- Session timeouts or user logouts.
- Multi-instance deployments if sessions are not shared or sticky routing is not configured properly.
- Lost session cookies or session invalidation.

If shopping carts or user data must survive long-term, proper persistence is required. Session scope is merely a **usage boundary within the session lifecycle**, not a durable storage strategy.

### 4.3. Multiple Requests of One Session Can Run Concurrently

One session can issue multiple nearly simultaneous requests: multiple browser tabs, parallel AJAX calls, or retries. Consequently, two threads can access the exact same session-scoped bean target.

In the `ShoppingCart` example, `ArrayList` is not designed for unsynchronized concurrent updates. The example suits learning scope, yet in real applications you must consider synchronization, appropriate collections, service-layer handling, or storing state in a safe data store.

**Session scope does not automatically make an object thread-safe.** It only determines which instance is shared within the session boundary.

## 5. Application Scope: One Instance per ServletContext

Application scope is scoped to the **ServletContext** within a web application. The bean can be shared across requests and sessions belonging to the same `ServletContext`.

Appropriate examples:

- Rarely changing configuration catalog shared across the web application.
- A read-heavy, mostly immutable set of metadata.
- A component managing application resources whose lifecycle is tied to `ServletContext`.

Example catalog bean:

```java
package com.example.demo.web;

import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class ApplicationCatalog {

    private final List<String> categories =
            List.of("BOOK", "DEVICE", "ACCESSORY");

    public List<String> getCategories() {
        return categories;
    }
}
```

`@ApplicationScope` is Spring's specialized annotation for application scope within `ServletContext`. It uses a scoped proxy by default, similar to request and session scopes.

A controller can inject this bean:

```java
@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final ApplicationCatalog catalog;

    public CatalogController(ApplicationCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/categories")
    public List<String> categories() {
        return catalog.getCategories();
    }
}
```

All requests and sessions within the same `ServletContext` receive the same `ApplicationCatalog` target. In this example, the list is immutable, making it suitable for shared data.

### 5.1. How Does Application Scope Differ from Singleton?

These two scopes are easy to confuse because both appear to be "one shared instance."

| Criterion | Spring singleton | Application scope |
|---|---|---|
| Boundary | One bean definition within one Spring container. | One `ServletContext` of a web application. |
| Depends on web context | No. | Yes. |
| Usable in non-web applications | Yes. | No `ServletContext` exists, so unsuitable. |
| Sharing meaning | Within the container owning the bean definition. | Within the web application/`ServletContext`. |
| When to use | Common stateless services, repositories, components. | State/objects scoped specifically to `ServletContext`. |

If an application has a root `ApplicationContext` and a child web context, singleton beans in the two contexts are instances belonging to two separate containers if each context registers its own definitions. Application scope is bound to `ServletContext`, so its semantics differ from container singleton scope.

**Do not use application scope merely because you want a "global singleton."** For ordinary stateless services, the default singleton is usually more appropriate. Application scope is meant for needs genuinely tied to the web application lifecycle.

### 5.2. Application Scope Is Not Cluster-Wide Scope

If you run three Spring Boot instances on three JVMs/containers, each instance has its own `ServletContext` and its own application-scoped beans. They do not share Java objects over the network.

```text
Load balancer
   │
   ├── Instance A / ServletContext A ── ApplicationCatalog A
   ├── Instance B / ServletContext B ── ApplicationCatalog B
   └── Instance C / ServletContext C ── ApplicationCatalog C
```

If data must be synchronized across instances, use a database, distributed cache, message broker, or suitable configuration service. Application scope is strictly **local shared state within one web application instance**.

## 6. Comparing Request, Session, and Application Scope

| Question | Request | Session | Application |
|---|---|---|---|
| One instance per... | HTTP request | HTTP session | `ServletContext` |
| Shared across multiple requests? | No, each request gets a separate target | Yes, if in the same session | Yes, within the same web application |
| Shared across sessions? | No | No | Yes |
| Typical termination | When the request completes | When the session expires/is invalidated | When the web application/`ServletContext` shuts down |
| Example | Request metadata | Temporary shopping cart | Shared configuration catalog |
| Main risks | Accessed when no request is active | Concurrent requests in same session, session loss/timeout | App-wide mutable state, not shared across instances |

A quick selection guide:

- Data needed only within **a single HTTP request** → request scope.
- Data needed across multiple requests of **the same session** → session scope.
- Data shared across **an entire web application instance** → application scope.
- Business components holding no per-request/session state → typically singleton.

## 7. Scoped Proxies Resolve Lifecycle Differences

A singleton has a longer lifecycle than a request-scoped bean. If a request bean target were injected directly into a singleton constructor without an intermediary mechanism, the target would be resolved at singleton creation time; this would fail the requirement of "one instance per request."

Specialized annotations:

```java
@RequestScope
@Component
class RequestData { }

@SessionScope
@Component
class UserSessionData { }

@ApplicationScope
@Component
class WebApplicationData { }
```

These annotations default to declaring class-based scoped proxies. The proxy serves as a dependency the long-lived bean can hold; when a method is called, it locates the target for the active scope.

You can also declare scopes manually:

```java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class RequestData {
}
```

Similarly, session and application scopes can be declared using the corresponding constants in `WebApplicationContext`.

### 7.1. Is the Proxy the Target Bean?

No. A scoped proxy is an intermediary object. When injected into a singleton, the reference is the proxy; the real target is retrieved according to the active request/session/application.

This has several consequences:

- `getClass()` on the reference may reveal the proxy class instead of the target class.
- The singleton's constructor can receive the proxy before any actual request exists.
- Method calls on the proxy require the corresponding scope to be active.
- Class-based proxies have constraints with `final` classes/methods and certain structures; if needed, interface proxies or `ObjectProvider` can be used.

### 7.2. Choosing Proxy Mode Explicitly

You can specify proxy mode via the annotation:

```java
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
@Component
public class RequestInfoImpl implements RequestInfo {
    // ...
}
```

This example assumes an `RequestInfo` interface and an implementing class. Interface proxies fit when dependencies are injected via interfaces; class proxies can be convenient when injecting concrete classes, provided the class and methods are proxyable.

Do not change proxy modes blindly just to silence an error you do not understand yet. First identify the injection type, whether the class is `final`, and when the scoped target is being accessed.

## 8. Using `ObjectProvider` to Retrieve Scoped Beans at the Right Time

Instead of letting a proxy forward calls, a singleton can receive `ObjectProvider<T>` and request the bean when needed.

Example:

```java
@Service
public class RequestAuditService {

    private final ObjectProvider<RequestMetadata> provider;

    public RequestAuditService(
            ObjectProvider<RequestMetadata> provider) {
        this.provider = provider;
    }

    public String currentRequestId() {
        return provider.getObject().getRequestId();
    }
}
```

`ObjectProvider` defers retrieving the bean until `getObject()` is called. This approach makes it explicit that the dependency is looked up at the time of use.

Advantages:

- Clearly signals that the dependency requires on-demand lookup.
- Avoids holding a scoped target bean from singleton startup.
- Gives explicit control over where `getObject()` is called.

The drawback is that callers must invoke the provider; if used everywhere, code can accumulate indirection. Scoped proxies generally feel more natural for dependencies used like regular objects.

Do not inject `ApplicationContext` into every service just to call `getBean()` manually. `ObjectProvider` expresses a narrower intent and is usually easier to test.

## 9. Request Scope and Asynchronous Processing

Request scope is tied to the **HTTP request context**, not simply "one object per thread." One request can be processed across multiple threads or multiple dispatches in the servlet async model. Spring integrates request context within the framework's web processing paths, yet you should not assume every thread spawned by application code automatically inherits the request context.

Example to avoid:

```java
@GetMapping("/report")
public String report() {
    executor.execute(() -> {
        // Do not assume this thread has a request context.
        auditService.record("background");
    });
    return "scheduled";
}
```

If `auditService` needs `RequestMetadata` via a scoped proxy, the call from the background thread can fail because request scope is not active on that thread.

How to handle it:

1. Read the necessary data from the request while the request is still active.
2. Pass immutable values (e.g., request ID) as parameters to the background task.
3. If correlation context is needed, propagate context using an appropriate framework/executor/observability mechanism.
4. Do not retain request/response objects for use after the request has completed.

Example:

```java
@GetMapping("/report")
public String report() {
    String requestId = requestMetadata.getRequestId();

    executor.execute(() -> reportService.generate(requestId));
    return "scheduled";
}
```

Here the background task receives a standalone string instead of trying to access a request-scoped bean later. `requestId` is explicitly copied data, not a proxy tied to a finished request.

With Spring WebFlux, the processing model is built on reactive pipelines and Reactor Context; do not apply ThreadLocal/Servlet request context assumptions directly. Use the corresponding WebFlux APIs instead of bringing `HttpServletRequest`/Servlet scopes into reactive flows.

## 10. Session Scope and Concurrency

Session scope shares a target across requests belonging to the same session. A user can open multiple tabs, submit two forms at once, or the browser can retry a request. Consequently, a mutable session-scoped bean can be accessed concurrently.

Simple example:

```java
@SessionScope
@Component
public class ShoppingCart {
    private final List<String> productIds = new ArrayList<>();

    public void add(String productId) {
        productIds.add(productId);
    }
}
```

Two parallel requests calling `add()` can cause race conditions or inconsistent data. Options depend on requirements:

- Keep the session bean immutable, creating new state on each update.
- Synchronize update operations where appropriate.
- Use data structures with suitable concurrency semantics, while still considering atomicity across multiple operations.
- Move critical state to a database or cache with consistent update mechanisms.

Do not think `@SessionScope` creates a separate object per thread. It creates an object per **session**, and a single session can have multiple active requests.

Sessions can also time out or be invalidated upon logout. If a bean holds resources that require closing, understand the container's destruction callbacks and session configuration; do not arbitrarily store sockets, file handles, or non-serializable resources in a session.

## 11. Application Scope and Shared State

An application-scoped bean can be called concurrently by many requests. Therefore, the same thread-safety principles apply even more strongly: every session and request in the same `ServletContext` can reach the same target.

Example of immutable configuration data:

```java
@ApplicationScope
@Component
public class SupportedLanguages {
    private final Set<String> languages =
            Set.of("vi", "en", "ja");

    public Set<String> all() {
        return languages;
    }
}
```

This is a suitable kind of object: data created once, never modified, and safe to read concurrently.

Example of shared mutable state:

```java
@ApplicationScope
@Component
public class GlobalCounter {
    private long count;

    public long increment() {
        return ++count;
    }
}
```

This code is not thread-safe. If a single-instance local counter is genuinely needed, `AtomicLong` can be used:

```java
@ApplicationScope
@Component
public class GlobalCounter {
    private final AtomicLong count = new AtomicLong();

    public long increment() {
        return count.incrementAndGet();
    }
}
```

However, `AtomicLong` only protects updates within **one JVM/instance**. When deployed across multiple instances, each `ServletContext` still has its own counter. Cluster-wide counting requires a distributed storage/synchronization system.

A Spring Boot application should generally favor stateless singleton services and immutable data over turning global settings into mutable application-scoped beans.

## 12. Distinguishing Session Scope from Spring Security Principal

A session-scoped bean is not synonymous with the authenticated user object.

Spring Security normally stores authentication details in `SecurityContext` via a security context repository suited to the application. Controllers and services can access the current principal through the security context or method security. Do not arbitrarily store passwords, secret tokens, or entire authentication objects inside a custom session-scoped bean.

If you need to keep UI selections or a shopping cart, session scope can fit. If you need to identify the authenticated user, use Spring Security's mechanisms. Both types of state can coexist, yet they have **different responsibilities and lifecycles**.

In stateless REST applications using bearer tokens, HTTP sessions might not be used for authentication at all. That does not forbid using session scope for another feature, though you must decide explicitly whether endpoints should ever create unintended sessions.

## 13. Scopes and Multiple Web Application Contexts

In large web applications, Spring may have multiple `ApplicationContext` instances, such as a root context and a servlet-bound context. This makes two concepts easy to confuse:

- **Singleton scope**: one instance per bean definition within each container.
- **Application scope**: tied to `ServletContext`, which is the web application boundary.

Therefore, avoid using the word "global" without specifying the boundary. A singleton in a child context is not automatically the same object as a singleton of the same class in the root context. Application scope binds to `ServletContext`, giving it different semantics even though instances are accessed through Spring bean infrastructure.

In a simple Spring Boot app, developers usually interact with only one main application context, so this difference rarely surfaces. It becomes important when integrating complex servlet contexts or legacy applications.

## 14. Which Scope Fits Which Scenario?

| Scenario | Scope/mechanism to consider | Why |
|---|---|---|
| Stateless calculation service holding no request state | Default singleton | One reused instance, clear dependencies. |
| Request ID, metadata specific to one invocation | Request | Avoids leaking data to other requests. |
| Temporary shopping cart within a user session | Session | Retains state across multiple requests of the same session. |
| Immutable configuration catalog shared in one web app | Application or singleton depending on required boundary | Application binds to `ServletContext`; singleton binds to container. |
| Data that must survive restarts/deployments | Database/durable cache | Web scopes only live for the runtime lifecycle. |
| State shared across multiple JVMs | Distributed store/service | Local scopes do not synchronize across the network. |
| User authentication information | Spring Security context | Security framework manages identity/authentication. |
| Background task running after request finishes | Pass required data or context propagation | Does not depend on a request scope that is no longer active. |

## 15. How to Test the Behavior of Each Scope

A visual way to learn is to log bean identities across multiple requests.

You can create an illustrative endpoint:

```java
@RestController
public class ScopeDemoController {

    private final RequestMetadata requestMetadata;
    private final ShoppingCart shoppingCart;
    private final ApplicationCatalog applicationCatalog;

    public ScopeDemoController(
            RequestMetadata requestMetadata,
            ShoppingCart shoppingCart,
            ApplicationCatalog applicationCatalog) {
        this.requestMetadata = requestMetadata;
        this.shoppingCart = shoppingCart;
        this.applicationCatalog = applicationCatalog;
    }

    @GetMapping("/scope-demo")
    public Map<String, Object> scopeDemo() {
        return Map.of(
            "requestId", requestMetadata.getRequestId(),
            "cartSize", shoppingCart.getProductIds().size(),
            "categories", applicationCatalog.getCategories()
        );
    }
}
```

Experiment:

1. Call `/scope-demo` the first time in browser A.
2. Call it again from browser A with the same session cookie: new request ID, same session cart.
3. Call from browser B without that session cookie: new request ID, separate session/cart.
4. Compare the catalog: within the same application instance, catalog contents match.
5. Restart the application: request/session/application targets are recreated under the new lifecycle, unless sessions are persisted/restored by external infrastructure.

Do not rely on identical catalog content to conclude object identity is identical; to verify identity, add a unique initialization ID to the bean in a test environment and observe it in a controlled way.

### Testing Request Scope with MockMvc

In Spring MVC tests, each HTTP request executed via `MockMvc` has its own request context. Example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RequestScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void eachRequestGetsItsOwnRequestId() throws Exception {
        MvcResult first = mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk())
                .andReturn();

        MvcResult second = mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk())
                .andReturn();

        assertNotEquals(
                first.getResponse().getContentAsString(),
                second.getResponse().getContentAsString()
        );
    }
}
```

This example assumes the `/request-info` endpoint returns a unique request ID and has the required MockMvc/JUnit imports. Two independent requests should have distinct request-scoped targets. When testing session scope, reuse the same `MockHttpSession` for requests simulating the same session; use another session to verify isolated targets.

## 16. Common Errors When Using Web Scopes

| Symptom | Possible cause | What to check |
|---|---|---|
| `Scope 'request' is not active` | Called a request-scoped bean outside an active HTTP request or on a thread without request context. | Inspect call path, async tasks, web context, and proxy invocation timing. |
| `Scope 'session' is not active` | No active HTTP session/request at access time. | Check request/session lifecycle, initialization path, and test environment. |
| Request bean persists across multiple requests | Target was injected directly without a proper proxy/provider or scope configuration is wrong. | Check `@RequestScope`, scoped proxy, and bean definition. |
| Session state disappears | Session expired, invalidated, cookie was not sent, or deployment does not store/replicate sessions. | Check cookies/session ID, timeout, logout, and session store. |
| Cart data corrupts under parallel requests | Multiple requests in the same session mutate a non-thread-safe object. | Check concurrency and state update design. |
| Application bean differs across servers | Each JVM has its own `ServletContext` and application target. | Use a shared store/config service if synchronization is needed. |
| Request scope fails in background executor | Background threads do not automatically inherit request context. | Pass required data or propagate context using a supported mechanism. |
| Scope tests fail even though app runs normally | Test uses a non-web `ApplicationContext` or lacks mock request/session. | Use a web test environment, `MockMvc`, and appropriate mock sessions. |
| Proxy cannot be created | Bean/class type incompatible with proxy mode, e.g., `final` class with class-based proxy. | Check interfaces/classes, `final` methods, and proxy mode. |

### A Note on Exceptions and Cleanup

Do not catch every scope exception and return a default like `null`. If request/session is not active, that signals code is accessing the wrong lifecycle. Fix the boundary between requests and background tasks or choose the right scope instead of hiding the error.

## 17. Practice Exercises

### Exercise A — Request Scope

Create `RequestMetadata` with a random ID generated when the bean is created. Inject it into a controller and return the ID on each request. Call the endpoint multiple times; observe each request receives a new ID.

### Exercise B — Session Scope

Create `ShoppingCart` using `@SessionScope`. Add endpoints to add/view products. Send two requests with the same session cookie, then compare with a different browser/session. Explain why new requests retain the cart data.

### Exercise C — Application Scope

Create `ApplicationCatalog` using `@ApplicationScope`, holding an immutable list. Access it from multiple requests and sessions. Observe that it is shared within the same web application instance.

### Exercise D — Singleton Service Injecting Request Bean

Create a singleton `AuditService` receiving `RequestMetadata`. Verify two requests log different IDs. Then call the audit service from an executor thread with no request context and explain the failure. Fix it by passing the request ID as a parameter.

### Exercise E — Thread Safety of Session/Application

Create an endpoint incrementing a counter in session scope and send multiple concurrent requests from the same session. Observe race conditions when using unsynchronized `int`/`ArrayList`. Try an appropriate synchronization mechanism and distinguish single-JVM protection from multi-instance synchronization.

### Exercise F — Distinguishing Singleton and Application

Create two web-aware application contexts in a controlled test, registering beans of the same type in each context. Compare container-level singleton with `ServletContext`-level application scope. Document the actual sharing boundary of each object.

## 18. Key Principles to Remember

1. **Request scope** lives for one HTTP request; a new request gets a new target.
2. **Session scope** lives for an HTTP session; requests in the same session can share the target.
3. **Application scope** lives for a `ServletContext`; requests/sessions in the same web application instance can share the target.
4. **Singleton** lives per bean definition in a Spring container; it does not equate to application scope or a cluster-wide instance.
5. Scoped proxies or `ObjectProvider` allow singletons to use shorter-lived beans; targets can only be accessed when the scope is active.
6. Mutable session/application-scoped beans must be designed for concurrent access.
7. Web scopes are not databases, do not guarantee persistence, and do not automatically share across multiple JVMs.
8. Servlet scopes and WebFlux reactive context follow different models; do not mechanically apply `HttpSession`/`ServletContext` to reactive pipelines.

When selecting a scope, start with the question: **"Which requests need to share this data, and until what point must it exist?"** If the answer is one request, one user session, or an entire web application instance, consider request, session, or application scope respectively. If it must outlive the runtime or be shared across multiple instances, move storage responsibility to a more suitable mechanism.
