# ScopedProxyMode.INTERFACES and ScopedProxyMode.TARGET_CLASS in Spring Framework

## Learning Objectives

When a short-lived bean (for example `request`, `session`, or `prototype`) is used by a longer-lived bean (usually `singleton`), Spring can insert a **scoped proxy** at the dependency point. The two options `ScopedProxyMode.INTERFACES` and `ScopedProxyMode.TARGET_CLASS` determine **the kind of proxy created, which Java types the proxy can be injected into, and which methods are forwarded**.

After this lesson, you will be able to:

1. Explain the difference between a **stable proxy** and a **target that changes per scope**.
2. Choose `INTERFACES` or `TARGET_CLASS` appropriately based on interface contracts, injection types, and Java class limitations.
3. Distinguish `DEFAULT`, `NO`, `INTERFACES`, and `TARGET_CLASS`; understand how the default on `@Scope` differs from the default on `@RequestScope`/`@SessionScope`.
4. Run a Spring Boot MVC application demonstrating both proxy types, verifying multiple calls within the same request and across multiple requests.
5. Diagnose concrete-class injection failures when a proxy only exposes interfaces, inactive-scope errors, and proxy issues with `final`/`private`.

## 1. The Problem: A Dependency Has a Shorter Scope Than Its Consumer

Spring creates beans in `singleton` scope by default: one instance per bean definition in an IoC container. However, a `request` bean exists for one HTTP request, a `session` bean for one HTTP session, and a `prototype` bean is created anew each time the container is asked to provide an instance.

Consider the following dependency (illustrative snippet explaining the concept; full classes will be written in section 4):

~~~java
@Service
class OrderService {
    private final RequestIdentity requestIdentity;

    OrderService(RequestIdentity requestIdentity) {
        this.requestIdentity = requestIdentity;
    }

    String currentIdentity() {
        return requestIdentity.value();
    }
}
~~~

`OrderService` is a singleton by default, whereas `RequestIdentity` is defined as request-scoped. If the **target** were injected directly when creating the singleton, at startup there is usually no request yet; even if a target happened to be created during some request, holding onto one fixed target would still fail the expectation of "one instance per request."

A **scoped proxy** replaces the direct reference to the target with an intermediary object that can be injected long-term:

~~~text
Singleton OrderService
         |
         | holds stable reference
         v
     Scoped proxy
         |
         | every call needing target
         v
  Active scope (request/session/...)
         |
         +---- Request #1 ---> RequestIdentity target A
         |
         +---- Request #2 ---> RequestIdentity target B
~~~

During request #1, calls through the proxy point to target A; during request #2, the proxy locates target B. The same **proxy object** can be retained by the singleton, while the **target object** is determined by the scope. The proxy **does not create or sustain an HTTP request on its own**; a web-aware context and an actually active request/session must exist when accessing the target.

This is a feature of the **Core Container, IoC, and bean scopes**. It uses a proxy mechanism similar to Spring AOP, but the reason for creating the proxy here is **scope-based bean resolution**, not automatically adding transactions, caching, or business aspects.

## 2. The Four Values of the ScopedProxyMode Enum

Import:

~~~java
import org.springframework.context.annotation.ScopedProxyMode;
~~~

| Value | Meaning | Creates a scoped proxy? | When appropriate? |
| --- | --- | --- | --- |
| `DEFAULT` | Follows the default configuration of the bean registration step, typically equivalent to `NO` unless configured otherwise | Depends on configuration | When inheriting scan configuration defaults; check the effective value |
| `NO` | Do not use a scoped proxy | No | Retrieve the bean within the proper scope via `ObjectProvider`, direct lookup, or when the dependency has a compatible lifecycle |
| `INTERFACES` | Create a JDK dynamic proxy implementing the interfaces publicly exposed by the target | Yes | Consumers depend via an interface; abstract contracts are preferred |
| `TARGET_CLASS` | Create a class-based proxy using CGLIB via a subclass of the target type | Yes | Must inject by concrete class or need to expose methods not on an interface |

**Do not confuse the defaults:**

- `@Scope("request")` is equivalent to `@Scope(value = "request", proxyMode = ScopedProxyMode.DEFAULT)` unless specified otherwise; `DEFAULT` is **typically** `NO`.
- `@RequestScope`, `@SessionScope`, and `@ApplicationScope` are specialized web-scope annotations; their `proxyMode` attribute defaults to **`TARGET_CLASS`**.
- `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)` or `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` overrides that default.
- `@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)` explicitly states both the scope and the proxying mechanism.

Therefore, you cannot conclude that "Spring defaults to JDK proxies whenever a class has an interface" for **all scoped proxies**: here the choice is dictated directly by `ScopedProxyMode`. Proxy-selection defaults in other AOP mechanisms are a separate topic.

## 3. Comparing INTERFACES and TARGET_CLASS

### 3.1. INTERFACES — JDK Dynamic Proxy

Declaration:

~~~java
public interface UserView {
    String displayName();
}

@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
public class RequestUserView implements UserView {
    @Override
    public String displayName() {
        return "user-from-current-request";
    }
}
~~~

The snippets in section 3 only illustrate structure; section 4 provides a standalone compilable/runnable project with full files and imports.

A JDK dynamic proxy is a runtime-generated object that **implements the required interfaces** instead of extending `RequestUserView`. Calls through the interface are routed to the proxy handler; the scoped proxy locates the target matching the active scope and invokes the target's method.

Correct way to inject:

~~~java
@Service
class UserService {
    private final UserView userView;

    UserService(UserView userView) {
        this.userView = userView;
    }

    String read() {
        return userView.displayName();
    }
}
~~~

**Mandatory requirement:** the collaborator must depend on `UserView` (or an interface exposed by the proxy), not `RequestUserView`. An ordinary JDK proxy is **not** an instance of the implementation class:

~~~java
// Java type semantics:
UserView view = /* proxy injected by Spring */;
// view instanceof UserView       -> true
// view instanceof RequestUserView -> false
~~~

If the singleton's constructor requires `RequestUserView` while that bean is exposed as a JDK interface proxy, Spring cannot use the proxy to satisfy the concrete class type. The actual error depends on the injection point and configuration, typically wrapped in `UnsatisfiedDependencyException` with a cause indicating "bean not of required type" or "no qualifying bean found."

A JDK proxy requires the target to implement **at least one suitable interface**. It only exposes methods declared on the proxied interfaces; a public method existing only on the implementation cannot be invoked through the `UserView` type if the interface does not declare it.

A `final` implementation class can still be wrapped by a JDK proxy **through an interface**, because a JDK proxy does not need to subclass the implementation. This differs from class-based proxies.

### 3.2. TARGET_CLASS — CGLIB Subclass Proxy

Declaration:

~~~java
@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestIdentity {
    public String value() {
        return "request-data";
    }
}
~~~

Spring generates a subclass proxy compatible with `RequestIdentity` (typically recognizable by a runtime class name containing `$$SpringCGLIB$$`). Because the proxy is a subclass, injecting by concrete class works:

~~~java
@Service
class IdentityService {
    private final RequestIdentity identity;

    IdentityService(RequestIdentity identity) {
        this.identity = identity;
    }

    String read() {
        return identity.value();
    }
}
~~~

This option is appropriate when there is no interface or when caller APIs need a class method not included in an interface. It **does not require** adding a separate CGLIB library yourself: modern Spring Framework versions bundle CGLIB inside `spring-core`.

Limitations of the subclass model:

- **A `final class` cannot be subclassed**, so a CGLIB proxy cannot be created for a final class.
- **A `final method` cannot be overridden/intercepted**. Never call a final method and expect it to forward to the scoped target like an overridable public method.
- **A `private method` cannot be overridden/intercepted**; similarly for some package-private methods inaccessible to subclasses.
- With Java modules, package visibility/access rules can restrict subclass proxy generation; consider appropriate module design and access permissions.
- In Kotlin, classes and methods are final by default, requiring appropriate open modifiers or choosing an interface proxy.

You should not "fix" errors by unconditionally making every class public/non-final. First evaluate whether you can define a stable interface and use `INTERFACES`.

### 3.3. Decision Matrix

| Question | `INTERFACES` | `TARGET_CLASS` |
| --- | --- | --- |
| What Java proxy is it? | JDK dynamic proxy | Subclass proxy via CGLIB |
| Must the target bean implement an interface? | Yes | No |
| Can it be injected into an interface-typed field/constructor? | Yes, when the interface is exposed | Yes, if the class implements that interface |
| Can it be injected into the concrete implementation type? | No | Yes, because the proxy extends the concrete class |
| Call methods present only on the concrete class? | Not through the interface proxy | Yes when the method is eligible for interception |
| Target is a final class? | Possible, if a suitable interface exists | No |
| Target has a public final method needing proxying? | Calls through the interface can be proxied | Cannot intercept final methods |
| Does the proxy make request/session active by itself? | No | No |
| Number of targets per distinct request/session? | Per scope, identical in both modes | Per scope, identical in both modes |
| Is a standalone CGLIB dependency required? | No | No in modern Spring |

**Selection rule:** If the API has a clear interface and all consumers inject by interface, `INTERFACES` is a good choice. If you must inject the implementation class, `TARGET_CLASS` fits better, provided the class/methods can be proxied. Neither changes the lifetime of the target.

## 4. Standalone Runnable Example with Java 17 and Spring Boot MVC

The example deliberately creates **two request-scoped beans** and injects both into a singleton controller: one bean proxied by interface, one by concrete class. It can be run with JDK 17+ and Maven 3.9+.

Directory tree:

~~~text
scoped-proxy-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ScopedProxyApplication.java
    ├── Greeting.java
    ├── RequestGreeting.java
    ├── RequestNumber.java
    └── ProxyController.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>scoped-proxy-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` sets up the Spring MVC/Servlet web context for request scope; `spring-context` and `spring-aop` come from Spring dependencies. There is no need to register `RequestContextFilter` manually because requests to this endpoint are handled by `DispatcherServlet`.

### 4.2. ScopedProxyApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopedProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedProxyApplication.class, args);
    }
}
~~~

### 4.3. Greeting.java — interface seen by clients

~~~java
package demo;

public interface Greeting {
    String identity();
}
~~~

### 4.4. RequestGreeting.java — INTERFACES

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
public class RequestGreeting implements Greeting {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    @Override
    public String identity() {
        return "interface=" + id;
    }
}
~~~

Each request gets its own **`RequestGreeting` target**. Each new target receives an incrementing id so it is clear that two requests use two different instances. The bean is exposed to consumers as a JDK interface proxy; injection points must declare type `Greeting`.

### 4.5. RequestNumber.java — TARGET_CLASS

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestNumber {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public String identity() {
        return "class=" + id;
    }
}
~~~

`RequestNumber` implements no interfaces. The class proxy is injected directly via type `RequestNumber`. The public method `identity()` is non-final, so the proxy can intercept it and access the target belonging to the current request.

### 4.6. ProxyController.java — singleton receiving two proxies

~~~java
package demo;

import java.lang.reflect.Proxy;
import org.springframework.aop.support.AopUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProxyController {
    private final Greeting greeting;
    private final RequestNumber number;

    public ProxyController(Greeting greeting, RequestNumber number) {
        this.greeting = greeting;
        this.number = number;
    }

    @GetMapping(value = "/types", produces = MediaType.TEXT_PLAIN_VALUE)
    public String types() {
        boolean jdk = Proxy.isProxyClass(greeting.getClass());
        boolean cglib = AopUtils.isCglibProxy(number);
        return "jdk=" + jdk + ",cglib=" + cglib + "\n";
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        String i1 = greeting.identity();
        String c1 = number.identity();
        String i2 = greeting.identity();
        String c2 = number.identity();
        return i1 + "\n" + c1 + "\n" + i2 + "\n" + c2 + "\n";
    }
}
~~~

`ProxyController` declares no custom scope so it is a singleton. Its constructor receives two proxies without requiring two request-scoped targets to be pre-created. The `/types` endpoint inspects the **proxy types** without calling the target's business methods. The `/probe` endpoint calls each proxy twice within the same HTTP request.

### 4.7. Run Command and Results

In the `scoped-proxy-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Open another terminal and run sequentially:

~~~bash
curl -s http://localhost:8080/types
curl -s http://localhost:8080/probe
curl -s http://localhost:8080/probe
~~~

Expected output on a freshly started application with no other requests creating targets for those two beans:

~~~text
jdk=true,cglib=true
interface=1
class=1
interface=1
class=1
interface=2
class=2
interface=2
class=2
~~~

`/types` shows that the object behind `Greeting` is a JDK dynamic proxy, while `RequestNumber` is a CGLIB proxy. Each `/probe` response contains two lines for the same interface-proxied target and two lines for the same class-proxied target. On the next request, both targets switch to new instances.

**Scope of output meaning:** The numbers `1` and `2` assume no other requests hit `/probe`; if concurrent requests occur, the counters may differ. The crucial property remains that **two calls to the same bean within one request return the same id; a different request gets a different target**. Output strings are joined with newlines so terminal display does not run lines together.

### 4.8. Experiments to Deepen Understanding

1. In `RequestGreeting`, change `INTERFACES` to `TARGET_CLASS`. The endpoint still works: a CGLIB proxy can be injected via the `Greeting` interface because a subclass of `RequestGreeting` also implements `Greeting`. However, `/types` will output `jdk=false,cglib=true`.
2. In `RequestNumber`, try changing `TARGET_CLASS` to `INTERFACES` **without adding an interface**. This is an invalid configuration: a JDK proxy cannot expose the API of a class without a suitable interface; Spring may fail during proxy creation/startup or fail to satisfy the concrete-class injection point. Exact failure behavior depends on configuration/runtime, so read the root cause.
3. Keep `INTERFACES` on `RequestGreeting`, then change constructor `ProxyController(Greeting greeting, ...)` to require `RequestGreeting greeting`. The JDK proxy is not a `RequestGreeting`; the injection type does not match, even though the underlying target is a `RequestGreeting` instance.
4. Put `final` on `RequestNumber` while keeping `TARGET_CLASS`. CGLIB cannot subclass a final class; the application will fail proxy creation. Switch to an interface-based proxy (after adding an interface) or remove the final class constraint if design permits.
5. Replace `@RequestScope(proxyMode = ...)` with `@Scope(value = "prototype", proxyMode = ...)` in a **separate** experiment: every call through the scoped proxy can resolve **a new prototype target**, so the "one target per request" rule no longer holds. This comes from `prototype` scope, not from the proxy mode.

## 5. Why Do the Two Proxies Have a Different Lifetime from Their Targets?

Spring registers a proxy under the bean name requested by clients; the actual target bean is managed separately according to its scope (in Spring's scoped proxy implementation, there is typically an internal target bean prefixed with `scopedTarget.`).

You can visualize it as:

~~~text
Bean injected into client: greeting
  └── scoped proxy (stable)
       └── per-request target lookup (internal: scopedTarget.requestGreeting)
             ├── Request A: target instance #1
             └── Request B: target instance #2
~~~

The internal name is an implementation detail useful for reading logs/diagnostics; business code should not directly look up `scopedTarget.*` beans.

**Two layers of responsibility:**

- **Proxy mode** defines the Java shape of the proxy (`INTERFACES` or `TARGET_CLASS`) and which calls can pass through it.
- **Bean scope** defines how targets are created, reused, and destroyed (`request`/`session`/`prototype`/custom). Changing the proxy mode does **not** change the scope rules.

For example, `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` operates against HTTP sessions instead of requests. The client must preserve the session cookie; requests belonging to the same session resolve the same target until the session ends. If a session bean has mutable state, be aware that multiple concurrent requests can access the target simultaneously; choosing a proxy mode does not automatically guarantee thread-safety.

## 6. @Scope, @RequestScope, @SessionScope, @Bean, and Component Scanning

### 6.1. Declaring with @Scope

~~~java
@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
class ScopedByInterface implements BusinessApi {
    @Override
    public String execute() {
        return "ok";
    }
}
~~~

Here `BusinessApi` is an application interface (to be declared separately). This is an explicit way when using a scope named `request` and wanting a JDK proxy. If you write `@Scope("request")` without specifying `proxyMode`, `DEFAULT` usually does not create a scoped proxy.

### 6.2. Declaring with Specialized Annotations

~~~java
@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
class PerRequestService implements BusinessApi {
    @Override
    public String execute() {
        return "ok";
    }
}

@Component
@SessionScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
class PerSessionState {
    public String current() {
        return "current";
    }
}
~~~

The snippets in section 6 are declaration examples inside an application with proper packages/imports, **not a standalone program**. `@RequestScope` and `@SessionScope` already have `TARGET_CLASS` as the default for `proxyMode`; you only need to specify it explicitly when intentionally changing it or emphasizing intent.

### 6.3. Beans Registered via @Bean

~~~java
@Configuration
class AppConfig {
    @Bean
    @Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
    BusinessApi businessApi() {
        return new BusinessImpl();
    }
}
~~~

Here `BusinessImpl implements BusinessApi`, not a separate component bean of the same name. `@Scope` applies to `@Bean` methods, not only `@Component`. When using an interface proxy, declare the return API type explicitly as the interface. If using a class proxy, ensure the actual class can be subclassed and Spring has sufficient bean type information.

### 6.4. DEFAULT Is Not a "Third Kind of Proxy"

`DEFAULT` expresses inheriting the default in metadata/configuration. In many cases it resolves to `NO`, though a component scan can configure a different default for scoped proxies. Therefore, when reading code, check registration configuration, composed annotations, and the effective `proxyMode` value; do **not** draw conclusions solely from the `DEFAULT` literal.

`NO` is chosen when you genuinely do not want a proxy. If a singleton needs to obtain a request-scoped target at the moment a request is handled, a deferred lookup such as `ObjectProvider` can be used instead of retaining the target during constructor execution.

## 7. When Should You Use ObjectProvider Instead of a Scoped Proxy?

A proxy makes calling code look very natural (`service.operation()`) yet remains an intermediary object with type constraints. `ObjectProvider<T>` is another solution: deferring lookup until the target is actually needed.

Illustrative example where `RequestData` is a `request` bean configured with `proxyMode = ScopedProxyMode.NO`:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
class ReportService {
    private final ObjectProvider<RequestData> provider;

    ReportService(ObjectProvider<RequestData> provider) {
        this.provider = provider;
    }

    String render() {
        RequestData data = provider.getObject();
        return data.value();
    }
}
~~~

Without an active request, `provider.getObject()` also cannot obtain a request-scoped target. `ObjectProvider` does not change target lifetimes; it simply moves resolution to **call time** instead of constructor injection. Its advantage is that you can depend on the concrete type even when the target is unproxied; its drawback is that the application must explicitly call `getObject()`.

In the case of `prototype`, calling `ObjectProvider.getObject()` multiple times creates multiple new targets. If you want to keep one prototype instance throughout a specific task, **fetch it once and pass/hold it within the scope of that task**; do not expect a proxy to hold a single instance steady across an entire task.

## 8. Invocation Mechanics and Cases That Bypass the Proxy

### 8.1. An Active Scope Is Required

When calling `greeting.identity()` in the example's controller, Spring is handling an HTTP request, so the `request` scope knows the current target. If that call is moved to `@Scheduled`, a singleton constructor, a startup callback, or a background thread lacking a request context, the proxy **still exists**, yet obtaining the target may throw an error like:

~~~text
Scope 'request' is not active for the current thread
~~~

You may also see nested messages about `No thread-bound request found`. Inspect the call site, request binding, and thread; switching `INTERFACES` to `TARGET_CLASS` will **not** cure an "inactive scope" cause.

If a bean uses a custom scope that has not been registered, the message instead looks like "No Scope registered for scope name ...". Distinguish "scope not registered" from "registered but not active."

### 8.2. Calls Inside the Target and Self-Invocation

A call from an external object to the proxy is intercepted; however, the target can call `this.otherMethod()` internally without performing another target resolution through the proxy. This matters most when reasoning about AOP-advised calls; with a scoped proxy, the executing object is already the current scope's target.

Conceptual example:

~~~java
public String operation() {
    return this.helper(); // Direct call on the current target.
}
~~~

This call does not automatically create another request-scoped instance. Do not interpret every internal method call in a class as an independent scope lookup.

### 8.3. final/private and Class Proxies

For CGLIB subclass proxies, method calls must be interceptable. `final` methods cannot be overridden; `private` methods cannot be overridden from a subclass. A practical risk is that such methods may execute against the state of the **proxy object itself**, rather than the intended scoped target. Do not rely on that behavior to access per-request state.

With JDK dynamic proxies, only calls through the exposed interfaces are intercepted. A `final` target class can still back an interface proxy, though if a method is absent from the interface, clients cannot invoke it through the interface reference.

### 8.4. Proxies Do Not Solve All Concurrency Issues

`request` isolates data across independent requests; `session` can be accessed concurrently by two requests belonging to the same session. Using `TARGET_CLASS` or `INTERFACES` does not provide synchronization, locking, transaction isolation, or session distribution. For mutable state, apply thread-safety and session persistence practices suited to your system.

## 9. Common Errors and Fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Injecting a request-scoped bean by implementation class reports missing bean/wrong type | Configured with `INTERFACES`, so Spring exposes a JDK proxy, not an implementation subclass | Inject by interface or switch to `TARGET_CLASS` when the class can be subclassed |
| JDK proxy class only shows interface methods | The interface does not declare the method to be called | Add it to the interface contract or consider a class proxy |
| `No Scope registered for scope name 'request'` | Using a context without web scopes registered, e.g. standalone `AnnotationConfigApplicationContext` | Use a web-aware Spring context, or register a suitable test scope |
| `Scope 'request' is not active for the current thread` | Resolving target outside an HTTP request exposed by Spring | Invoke within a request, pass data to background tasks, or change the design |
| Startup failure because CGLIB cannot subclass | Bean class is `final` or has access/module restrictions | Choose `INTERFACES` if an interface exists, or redesign the class |
| Calling a public final method fails to yield the expected scoped target | `TARGET_CLASS` cannot intercept final methods | Use a public overridable method or an interface with `INTERFACES` |
| Singleton initialization fails because request bean is inactive | Used `@Scope("request")` without creating a proxy, so target was resolved too early | Use `@RequestScope` (defaults to TARGET_CLASS), explicit proxy mode, or `ObjectProvider` |
| Same session bean receives overlapping data writes | Two concurrent HTTP requests access the same session target | Design immutable data/synchronized access; proxy mode does not solve this |
| Seeing a single proxy injected leads to assuming there is only one target | Confusing proxy lifetime with scoped bean lifetime | Track target ids across requests as in the example |
| `@EnableTransactionManagement(proxyTargetClass = true)` yet scoped proxy bean still fails injection | Confusing transaction AOP proxy settings with scoped proxy metadata | Check the bean's `@Scope(proxyMode = ...)`/`@RequestScope` and actual injection type |

When diagnosing whether a bean has been proxied, you can use:

~~~java
import org.springframework.aop.support.AopUtils;

boolean jdkProxy = AopUtils.isJdkDynamicProxy(bean);
boolean classProxy = AopUtils.isCglibProxy(bean);
~~~

This snippet is used inside a method that already has a `bean` variable, not a standalone program. `AopUtils` can detect Spring AOP proxies in general, **which does not prove a proxy is necessarily a scoped proxy**. To confirm scoped proxy intent, inspect the annotations/bean definition and the target's scope.

## 10. Design Notes

- **Interface-based design:** Consider `INTERFACES` when clients need a stable contract without depending on the implementation class. It is helpful when the implementation has non-public-API methods or is a `final` class.
- **Concrete-type dependency:** `TARGET_CLASS` preserves concrete class type compatibility, convenient for legacy code, though it depends on subclassing/overriding ability.
- **Do not choose solely for performance:** The cost difference between JDK proxies and CGLIB proxies is rarely the deciding factor in web business logic; scope rules, injection types, correctness, and maintainability matter more.
- **Avoid holding targets outside their scope:** Never place a request target into a static field, global cache, or a reused stateful singleton; keep only the proxy or extracted data values with the proper lifetime.
- **Do not pass a raw request proxy to an async worker** if the worker lacks a request context; pass a DTO carrying the needed information instead.
- **Do not conflate a scoped bean's proxy mode with global AOP proxy settings**: Spring Boot AOP configuration properties and `@EnableAspectJAutoProxy` serve different purposes; always check the scope metadata on the bean in question.
- **Clear bean definitions:** Avoid registering two beans with the same responsibility via both component scanning and `@Bean` unintentionally; choosing a proxy mode does not resolve ambiguity when multiple candidates match a type.

## 11. Selection and Testing Checklist

1. Determine which scope the target bean actually belongs to (`request`, `session`, `prototype`, etc.).
2. Determine whether consumers will inject by **interface** or **concrete class**.
3. If injecting by interface and the target implements a public interface: try `INTERFACES`.
4. If injecting by concrete class and the class/methods can be subclassed/overridden: try `TARGET_CLASS`.
5. Do not guess defaults: `@Scope`'s default `DEFAULT` is usually `NO`, whereas `@RequestScope`/`@SessionScope` default to `TARGET_CLASS`.
6. Verify in tests that an active scope exists when calling the bean; test both the first request and subsequent requests.
7. Test two calls within the same request and across two different requests; results must follow the target scope, not the proxy mode.
8. Check for final classes, final/private methods, type mismatches, and missing requests when running on background threads.
9. Use `Proxy.isProxyClass(...)` or `AopUtils` to confirm proxy type when diagnosing; cross-check with scope metadata to avoid confusing other proxy types.
10. Use `ObjectProvider<T>` if you need explicit lookup control or want to avoid scoped proxy type constraints.

## 12. Knowledge Self-Check

**Question 1.** Why can a singleton receive a `@RequestScope` bean at startup even when there is no HTTP request yet?  
**Answer:** The singleton receives a **proxy**, without needing to create the target yet. When code invokes a method through the proxy during a request, Spring locates the current request's target.

**Question 2.** With `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)`, should a bean `CheckoutImpl implements Checkout` be injected as `Checkout` or `CheckoutImpl`?  
**Answer:** Use `Checkout`, because the JDK proxy implements the interface without extending `CheckoutImpl`.

**Question 3.** Is `@RequestScope` without specifying `proxyMode` equivalent to `@Scope("request")` without specifying `proxyMode`?  
**Answer:** No. `@RequestScope` defaults to `TARGET_CLASS`; `@Scope` defaults to `DEFAULT`, which usually equates to `NO` unless overridden by default configuration.

**Question 4.** Can `TARGET_CLASS` be used for a final class?  
**Answer:** No, because CGLIB must create a subclass. If a suitable interface exists, `INTERFACES` can be used.

**Question 5.** Does switching `INTERFACES` to `TARGET_CLASS` fix the error "request scope is not active"?  
**Answer:** No. The error arises because there is no active request scope when resolving the target; the proxy mode does not create a request.

**Question 6.** With `@Scope(value = "prototype", proxyMode = TARGET_CLASS)`, why can two calls on the same proxy go to two different targets?  
**Answer:** The proxy resolves the target from the scope at call time; prototype scope returns a new instance per lookup. This differs from request scope, where lookups within the same request return the same target.

**Question 7.** Why can a final method on a class-based proxy cause a logic bug even though the program compiles?  
**Answer:** A CGLIB subclass cannot override/intercept a final method. There is no guarantee the call forwards properly to the scoped target; design the API with interceptable methods or through an interface.

## Official References

- Spring Framework Reference — [Bean Scopes; Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- Spring Framework Reference — [Using the @Bean Annotation: @Scope and scoped-proxy](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html).
- Spring Framework Reference — [Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- Spring Framework Reference — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html).
- Spring Framework Javadoc — [ScopedProxyMode (6.2)](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/ScopedProxyMode.html).
- Spring Framework Javadoc — [RequestScope (6.1)](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/context/annotation/RequestScope.html).
