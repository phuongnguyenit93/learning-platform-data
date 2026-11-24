# Scoped Proxies in Spring Core Container: Scope-Based Target Resolution

## 1. The Problem: A Long-Lived Bean Needs a Short-Lived Dependency

In the Spring IoC container, beans with **different scopes** have different creation times, lifetimes, and reuse rules. For example, a `CheckoutService` is `singleton` by default, while `CurrentCart` needs to live for an HTTP session; or `RequestInfo` only exists for each individual HTTP request.

When a long-lived bean (such as a singleton) receives **an instance directly** of a short-lived bean via constructor, Spring resolves the dependency when constructing the singleton. The injected reference stays fixed. This is not always what you want: the singleton must handle multiple requests/sessions, while the data must match the **currently executing request/session**.

A **scoped proxy** is an intermediary object created and injected by Spring in place of the real target. The dependency holds **the same proxy** across uses; each time a method is called on the proxy, Spring determines the target matching the current scope and delegates the call to that target.

~~~text
Singleton service
    │ stable reference
    ▼
Scoped proxy (P)
    │ on each method call: look up target according to active scope
    ▼
Actual target
    ├── request A → target R-A
    ├── request B → target R-B
    ├── session S1 → target S1
    └── prototype → new target on every method invocation
~~~

It is important to distinguish clearly:

- **Proxy**: the facade object supplied by the container to the injection point; usually exists as a singleton bean in the context.
- **Target**: the real business object that the proxy retrieves from the container and invokes methods on.
- **Scope**: the rule Spring uses to decide whether this lookup should reuse an existing target or create a new target.
- **Scope context**: the context identifying "which request, which session, etc. is currently active." For web scopes, the context must be active on the executing thread.

A scoped proxy **does not pick targets randomly** and does not clone targets. It re-resolves the bean through the container so the scope itself supplies the right instance.

## 2. How It Works When Calling a Method

Declaring a bean with an appropriate scope and `proxyMode` causes Spring to register a proxy representing that bean. At the implementation level, scoped proxies usually rely on `ScopedProxyFactoryBean` and a target source; the internal name of the target bean has the form `scopedTarget.<bean-name>`. This is a useful detail for reading logs/`BeanFactory`, not a business API you should access directly.

Logical flow:

1. Spring initializes the singleton needing the dependency and **injects proxy P**, without requiring the request/session target to exist yet at that moment.
2. Code calls `P.process()` while an appropriate scope context is active.
3. The proxy asks the container for the real target via the target source, equivalent to looking up the target bean by name.
4. `BeanFactory` applies scope rules: create a new instance or return an instance stored in the scope.
5. The proxy forwards the `process()` call to the located target; the method runs against that target's state.
6. On the next call, the proxy **looks up again**. The selected object may be the same or different, depending on the scope context and scope type.

~~~text
service.run()
   │
   ▼
proxy.process()
   │
   ▼
BeanFactory → Scope.get(beanName, objectFactory)
                       │
             ┌─────────┴──────────┐
             │ valid target exists?│
             └─────────┬──────────┘
                  yes  │   no
             ┌─────────┴──────────┐
             ▼                    ▼
     return old target    create new target
             └─────────┬──────────┘
                       ▼
                 target.process()
~~~

The diagram illustrates the semantics of scopes, **not verbatim pseudocode of every internal branch** of Spring. With `prototype`, the rule is to create a new instance every time the container needs a target. With `request` or `session`, the scope normally stores one target per request/session and returns it on subsequent calls within that scope.

One call through the proxy selects a target; **subsequent method calls on the same proxy do not automatically reuse the previous target**. To have multiple methods operate on the exact same prototype instance, you must retrieve and hold the target reference on demand (see section 7).

## 3. How Does Spring Select Targets for Each Scope Type?

| Target bean scope | Reuse key/context | Two method calls on the same scoped proxy | Consequence |
| --- | --- | --- | --- |
| `singleton` | Same Spring container | Usually the same singleton target | A scoped proxy is usually unhelpful |
| `prototype` | No target cached per scope | **New target for each invocation through proxy** | State modified in the previous call may be gone in the next call |
| `request` | Current HTTP request | Same target within the same request; different requests have different targets | Suitable for data tied to one request |
| `session` | Current HTTP session | Same target within one session; different sessions have different targets | Suitable for shopping cart/per-user session state |
| `application` | `ServletContext` in web app | Same target across the web application | Differs from `singleton` if multiple Spring contexts share a `ServletContext` |
| Custom scope | Key/lifetime defined by `Scope` implementation | Depends on custom scope logic | Must register scope and manage context/lifecycle properly |

The key point is that **the proxy itself does not mean "one target per request" or "one target per method"**: **the target's scope** determines the outcome.

### Comparing Across Calls

~~~text
1) Target scope = prototype
   Proxy P → call #1 → T1
   Proxy P → call #2 → T2
   Proxy P → call #3 → T3       (T1, T2, T3 are different)

2) Target scope = request
   Request A: P → call #1 → RA
              P → call #2 → RA
   Request B: P → call #1 → RB  (RB differs from RA)

3) Target scope = session
   Session S1, request A: P → call #1 → TS1
   Session S1, request B: P → call #2 → TS1
   Session S2, request C: P → call #1 → TS2
~~~

The session example assumes session S1 remains valid and the same application manages the scope. When a session expires or is invalidated, the target belonging to that session ends its lifecycle according to the scope's management mechanism.

### When No Suitable Scope Context Is Active

Injecting a request-scoped proxy into a singleton can succeed at application startup. However, when calling a method through the proxy **outside a bound HTTP request** (for instance from `main`, a background scheduler, or a manually spawned thread), Spring cannot find a valid request target; typically `ScopeNotActiveException` or an underlying scope exception is thrown. A scoped proxy only **defers target lookup**, it does not fabricate a fake HTTP request.

In Spring MVC, `DispatcherServlet` helps set up the request context when handling requests. In other servlet environments, `RequestContextFilter` or `RequestContextListener` can assist with binding the request. Never assume request context automatically propagates to `@Async`, executor threads, or `CompletableFuture`s running on another thread.

## 4. Declaring a Scoped Proxy with Annotations

The `@Scope` annotation has a `proxyMode` attribute with three options to remember:

- `ScopedProxyMode.NO`: do not create a scoped proxy; inject normally at dependency resolution time.
- `ScopedProxyMode.TARGET_CLASS`: create a class-based proxy of the target class (CGLIB/subclass). Injection points can depend on the concrete type if the class/methods allow proxying.
- `ScopedProxyMode.INTERFACES`: create a JDK dynamic proxy based on interfaces. Injection points must use an interface type implemented by the proxy.

Place the scope and proxy mode on the bean definition, for example:

~~~java
@Component
@Scope(value = "prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class ReportPart {
    public void render() {
        // ...
    }
}
~~~

Or in Java configuration:

~~~java
@Bean
@Scope(value = "prototype", proxyMode = ScopedProxyMode.INTERFACES)
public ReportPartApi reportPart() {
    return new ReportPartImpl();
}
~~~

The two snippets above are **standalone configuration templates**, assuming the classes/interfaces exist, appropriate Spring annotations are imported, and component scanning or the config class is registered in the context.

For web scopes, Spring provides convenient composed annotations:

~~~java
@Component
@RequestScope
public class CurrentRequestData {
    public String requestId() {
        return "...";
    }
}

@Component
@SessionScope
public class ShoppingCart {
    // State within one HTTP session
}
~~~

`@RequestScope` and `@SessionScope` default to `ScopedProxyMode.TARGET_CLASS`. You can write `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` if the bean implements an interface and injection points use that interface.

Snippets using `request`/`session` only make sense in a **web-aware `ApplicationContext`** managing those scopes. With a plain `AnnotationConfigApplicationContext` that does not register request/session scopes, the configuration will not turn into a web application on its own.

### Interface Proxy vs. Class Proxy

| Type | Mechanism | Points to watch |
| --- | --- | --- |
| `INTERFACES` | JDK proxy implements interfaces | Injection type must be an interface; proxy cannot be cast to concrete implementation |
| `TARGET_CLASS` | CGLIB subclass of target class | Cannot proxy `final` classes; `final` or `private` methods cannot be overridden/intercepted |

If you choose `INTERFACES` while a service declares constructor `CheckoutService(ShoppingCartImpl cart)`, injection by implementation type can fail because the proxy only implements the `ShoppingCart` interface. Change the constructor to `CheckoutService(ShoppingCart cart)` or consider a target-class proxy when the concrete type is genuinely needed.

If the target class is `final` (commonly seen with records), a target-class scoped proxy cannot extend that class. Prefer an interface or adjust the design instead of trying to force a proxy onto an unproxiable class.

Ensure that **business methods invoked through the proxy** are methods the proxy can intercept. Do not rely on `private` or `final` methods to trigger scope-based target lookup.

## 5. Runnable Java 17 Example: Prototype Proxy Held in a Singleton

The following example shows that **the reference to the proxy does not change**, yet the target of each method call on the prototype proxy is a new object. Uses Spring Framework 6.2.19 and Java 17+. No Spring Boot, web server, or HTTP request is required.

File tree:

~~~text
scoped-proxy-demo/
├── pom.xml
└── src/main/java/example/ScopedProxyDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>scoped-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/example/ScopedProxyDemo.java`:

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;

public final class ScopedProxyDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JobService service = context.getBean(JobService.class);
            WorkState proxy = service.state();

            System.out.println("Singleton holds same proxy: "
                    + (proxy == service.state()));
            System.out.println("getBean returns same proxy: "
                    + (proxy == context.getBean(WorkState.class)));

            int firstId = proxy.instanceId();
            int secondId = proxy.instanceId();
            System.out.println("Two calls select different targets: "
                    + (firstId != secondId));

            proxy.increment();
            System.out.println("Next call reads: " + proxy.value());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
               proxyMode = ScopedProxyMode.TARGET_CLASS)
        public WorkState workState() {
            return new WorkState();
        }

        @Bean
        public JobService jobService(WorkState workState) {
            return new JobService(workState);
        }
    }

    // Do not mark final: Spring needs to subclass it as a scoped proxy.
    public static class WorkState {
        private static final AtomicInteger NEXT = new AtomicInteger();
        private final int instanceId = NEXT.incrementAndGet();
        private int value;

        public int instanceId() {
            return instanceId;
        }

        public void increment() {
            value++;
        }

        public int value() {
            return value;
        }
    }

    public static final class JobService {
        private final WorkState state;

        public JobService(WorkState state) {
            this.state = state;
        }

        public WorkState state() {
            return state;
        }
    }
}
~~~

Run in the `scoped-proxy-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ScopedProxyDemo
~~~

Expected program stdout (excluding Maven logs/diagnostics if printed by the environment):

~~~text
Singleton holds same proxy: true
getBean returns same proxy: true
Two calls select different targets: true
Next call reads: 0
~~~

Why is the last line `0`, not `1`? `proxy.increment()` increments `value` on the prototype target of **the first call**. `proxy.value()` is **another call through the proxy**, so Spring selects a fresh prototype target with `value=0`. This behavior matches the configuration, but is usually unsuitable when you want to maintain a job's state across multiple method calls.

`context.getBean(WorkState.class)` in this configuration returns **the proxy for the `workState` bean**, not necessarily a raw new target for the caller. If you obtain the bean from the container and hold the proxy in a local variable, every method call on that variable still re-resolves the target according to scope.

**Dependency note**: `spring-context` in Maven brings in the required Spring modules, including proxying mechanisms in Spring AOP. The demo code is a complete Java program; other short snippets in this article only illustrate API/configuration and may require imports or real application dependencies.

## 6. Scoped Proxies with Request and Session in Web Applications

A design example:

~~~java
public interface CartView {
    int itemCount();
}

// The classes below are illustrative in a web application with component scanning.
@Component
@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)
public class SessionCart implements CartView {
    private int count;

    @Override
    public int itemCount() {
        return count;
    }

    public void addOne() {
        count++;
    }
}

@Service
public class CartSummaryService {
    private final CartView cart;

    public CartSummaryService(CartView cart) {
        this.cart = cart;  // Stable proxy, target selected per session.
    }

    public int currentCount() {
        return cart.itemCount();
    }
}
~~~

This is illustrative code split across appropriate types/files, not a single standalone Java file because it contains multiple `public` types and omits Spring imports. When a user belonging to the same HTTP session makes two consecutive requests, `currentCount()` is forwarded by the proxy to that session's `SessionCart` target. Across two different sessions, there are two different targets. `CartSummaryService` can still remain a singleton.

Note on the interface proxy example: `CartView` only declares `itemCount()`, so consumers receiving the proxy under the `CartView` type cannot call `addOne()` directly. If adding items is needed, include that behavior in the interface or adjust the interface/class proxy accordingly.

For request scope:

~~~java
@Component
@RequestScope
public class RequestAudit {
    private final String marker = java.util.UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@Service
public class AuditService {
    private final RequestAudit audit;

    public AuditService(RequestAudit audit) {
        this.audit = audit;
    }

    public String auditMarker() {
        return audit.marker();
    }
}
~~~

`AuditService` holds a request-scoped proxy. Within the same request, two calls to `auditMarker()` receive the same `marker` because the scope uses the same target. In another request, a different `RequestAudit` target is created with a different marker. Do not use UUIDs to argue mathematical identity guarantees; the exact criterion of a scope is target **reference identity**.

Both examples require a Spring Web MVC application or an appropriate web-aware container; they illustrate dependencies/scoped proxies and do not include `@Controller` or web server startup configuration.

## 7. Choosing Scoped Proxy or `ObjectProvider`?

A **scoped proxy** is suitable when a collaborator wants to invoke a dependency like an ordinary object, and each method call needs to find the right target for the active request/session. Client code holds a stable proxy reference without writing lookup calls itself. This is especially convenient for `request`, `session`, or custom scopes that cache by context.

**`ObjectProvider<T>`** is suitable when business code needs to **actively decide when to obtain the bean**, especially when you want to use **the same prototype target across an entire multi-step workflow**.

Example of a stateful prototype without a proxy:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class Draft {
    private int lines;

    public void addLine() {
        lines++;
    }

    public int lineCount() {
        return lines;
    }
}

@Service
public class DraftService {
    private final ObjectProvider<Draft> drafts;

    public DraftService(ObjectProvider<Draft> drafts) {
        this.drafts = drafts;
    }

    public int createTwoLineDraft() {
        Draft draft = drafts.getObject(); // One actual prototype target.
        draft.addLine();
        draft.addLine();
        return draft.lineCount();         // Result: 2.
    }
}
~~~

These are illustrative classes for an application with component scanning, not a standalone program. With a prototype **not configured with a scoped proxy** like this example, each `drafts.getObject()` fetches an independent target and you hold onto the `draft` reference across calls.

**Combination trap:** if `Draft` is configured with a **scoped proxy**, then `ObjectProvider<Draft>.getObject()` will typically also resolve the registered **proxy bean** by name/type. Calling the provider once does not guarantee "keeping the same prototype target" when multiple methods are subsequently called on the proxy! To keep one prototype target for an entire operation, organize an **unproxied** prototype bean for the provider to fetch directly, or use a factory API designed specifically for creating drafts.

Selection table:

| Need | Typically suitable choice | Why |
| --- | --- | --- |
| Singleton reads info from the **current request** | `@RequestScope` + scoped proxy | Automatically selects the current request's target on each method call |
| Singleton uses **current session** state | `@SessionScope` + scoped proxy | Same target is reused across requests in the same session |
| Each job needs a mutable object; multiple calls share that object | Unproxied prototype + `ObjectProvider.getObject()` once/job | Keeps a consistent target reference throughout the job |
| Exactly one dependency at collaborator construction; no context-based change needed | Direct injection | Simple, sufficient when lifetimes are compatible |
| Code must control lookup, optional dependencies | `ObjectProvider` or `ObjectFactory` | Explicit about when the container creates/returns the bean |

Other options include `jakarta.inject.Provider<T>` or `@Lookup` (lookup-method injection); they still rely on scope when actually resolving the bean. Not every state problem needs a scoped proxy: if an object is pure Java data and does not need DI/lifecycle, creating a plain object can be simpler.

## 8. Subtle Situations Easy to Misunderstand

### 8.1. Self-Invocation Inside the Target

Suppose the target has `outer()` and `inner()`:

~~~java
public void outer() {
    inner(); // this.inner(): same target currently running outer().
}
~~~

After calling `proxy.outer()`, the container has already selected the target for this invocation. The call `this.inner()` happens **inside the target**, without going back through the proxy to pick another target. Conversely, calling `proxy.outer()` then `proxy.inner()` from the outside means **two trips through the proxy**; with prototype scope, they normally get two different targets.

This shares the same "self-invocation bypasses the proxy" principle as Spring AOP, except here we are looking at its consequence for **scope-based target selection**.

### 8.2. Injecting a Proxy and Storing a Target Are Two Different Things

If a singleton stores a proxy in a field, each method call through that field can select the target matching the current context. If the singleton instead extracts the **real target** and stores it long-term in a field, that target may be used beyond its intended lifetime; request/session state risks being retained or mixed up between users.

Do not infer target identity from `proxy == proxy`, `System.identityHashCode(proxy)`, or `proxy.getClass()`. Those expressions inspect the **proxy**, not whether the underlying targets are identical.

### 8.3. Target Constructor, Init, and Destroy

Creating a proxy at context startup does not mean the request/session target has already been created. Targets are usually created when the scope is queried and no matching instance exists yet. Once a target is created, Spring still performs wiring, bean post-processing, and initialization callbacks just like other Spring beans.

- `request`/`session`: target lifecycle and destruction callbacks are tied to when the scope ends via the container/web framework, provided the scope has registered destruction properly.
- `prototype`: Spring initializes and hands off the instance, **but does not automatically call destroy callbacks for each prototype target** after use. If it holds resources requiring closing, design explicit ownership/cleanup.
- A proxy cannot turn every target into a singleton or extend the lifetime of a request/session.

### 8.4. Threads, Async, and Request Context

Do not assume "same user" means an active request context exists on every thread. With `@Async`, `ExecutorService`, scheduled tasks, or message listeners, there is usually no HTTP request bound to the thread; a request-scoped proxy may fail to resolve a target. If business logic needs request data in an async task, **extract the required data** into independent values and pass them into the task, or use a properly configured and verified context propagation mechanism. Avoid indiscriminately passing entire request/session proxies into long-running tasks outside web requests.

### 8.5. Performance and Correctness Consequences

Every method call through a scoped proxy incurs a target selection step; with prototypes, this can trigger frequent instance creation. The "increment in method A, read in method B" pattern breaks when the two methods run on two different prototype targets. With request/session scope, calls within the same context typically reuse the target, making stateful models more appropriate.

Choose scopes according to **the unit of state that must stay consistent**: request, session, job, or entire context; do not pick one just to make constructor injection code shorter.

## 9. Common Errors and How to Handle Them

| Symptom | Typical cause | Resolution |
| --- | --- | --- |
| Singleton always sees the first request's state | Short-lived target injected directly, or target cached manually | Inject a request-scoped proxy, avoid storing targets outside scope |
| Calling method outside HTTP request reports inactive scope | No request-bound context | Call within request lifecycle or pass needed data to background processing |
| Prototype proxy "loses state" between two methods | Each invocation selects a new prototype target | Use an unproxied prototype + provider once per job |
| Interface-based bean reports missing implementation when injecting concrete type | `INTERFACES` (JDK proxy) chosen while injection asks for class | Inject by interface or choose `TARGET_CLASS` if feasible |
| `final` class/`final` method not proxied properly | CGLIB needs subclassing/overriding | Use interface proxy, remove `final` when appropriate, or change design |
| Calling `new MyBean()` shows no scope/proxy/AOP | Object created outside the Spring container | Obtain bean from Spring or DI via proper bean definition |
| Test calling request proxy on plain context fails | Web scope/context not registered | Use web test context/MockMvc or set up a valid mock scope |
| Logs show same proxy but different user data | Comparing proxy instead of target | Inspect identity/state inside target methods per context |
| Prototype holds resources that are never cleaned up | Prototypes are not automatically destroyed by Spring by default | Close resources according to ownership; do not wait for context close |

## 10. Design Checklist and Self-Check

Before configuring a scoped proxy, determine: **which bean needs scoped state**, **which bean holds the reference longer**, **whether each method call needs the same target as the previous one**, **where the web/custom scope context is active**, and **whether you are injecting the proxy via an interface or a class**.

A short practical checklist:

1. The target bean is declared with the right scope (`prototype`/`request`/`session`/custom scope) and is actually registered by Spring.
2. Proxying is enabled via `@Scope(proxyMode = ...)` or an appropriate web annotation.
3. The injection type matches either a JDK interface proxy or a CGLIB target-class proxy.
4. Invoked methods pass through the proxy, without relying on `private`/`final` methods or self-invocation to select a new target.
5. You have verified that **the same request/session uses the same target**, and **different scopes use different targets**.
6. If using a stateful prototype, you have chosen a mechanism to retain one target for **the entire operation** when needed.
7. You have a strategy for missing active scopes, request context across async boundaries, and resource cleanup.

### Self-Check Questions

**Question 1.** A singleton holds a request-scoped proxy `P`. During request A, it calls `P.read()` twice, then request B calls it once. What is the minimum number of request targets created?

**Answer:** Two targets (one for A, one for B), assuming both requests access that bean for the first time and the context is functioning validly. The two method calls in request A reuse target A.

**Question 2.** A singleton holds a prototype-scoped proxy `P`. It calls `P.addItem()` and then `P.total()`. Will `total()` necessarily see the newly added item?

**Answer:** No. Two calls through the proxy usually select two different prototype targets. One target must be retained throughout the operation if business logic requires continuous state.

**Question 3.** Within the same session, there are two different HTTP requests. Does a session-scoped proxy select two different targets or the same one?

**Answer:** The same target while the session remains active, assuming the same web application/scope and that it has not been invalidated or had its scope state altered.

**Question 4.** Can a request-scoped proxy be injected into a singleton at web app startup before the first request arrives?

**Answer:** Yes. The proxy can be constructed and injected beforehand; the actual request target only needs to be resolved when a request context exists. Calling methods outside a request will have no valid target and can throw a scope error.

**Question 5.** If `@Scope(proxyMode = INTERFACES)` creates a JDK proxy, can it be injected as the concrete implementation class?

**Answer:** You should not. A JDK proxy implements interfaces, not an instance of the implementation class. The constructor/field needs to use an interface supported by the proxy.

## 11. References

- [Spring Framework Reference — Bean Scopes and Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework Javadoc — Scope](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Scope.html)
- [Spring Framework Javadoc — ScopedProxyMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ScopedProxyMode.html)
