# Keeping Per-Request Data Separate from Bean State in Spring

When multiple HTTP requests arrive simultaneously, Spring can let different threads invoke **the same controller or service object**. If that bean stores a username, request parameter, trace ID, or temporary processing data in a **shared field**, one request can overwrite another request's data. The consequence is not merely wrong results: for user-bound data, it can also be **cross-request data leakage**.

Core principle: **data belonging solely to one request should travel with the invocation, a request data object, or a clearly managed request scope; it must never silently become shared state on a singleton bean**. This lesson explains the mechanics, safe design choices, how to handle asynchronous boundaries, and the limits of each approach.

## 1. Why Does Bean State Directly Relate to Concurrency?

In Spring, common stereotypes such as **@Component, @Service, @Repository, @Controller, @RestController** default to **singleton scope**: within a Spring container, a singleton bean definition normally has one instance shared everywhere that bean is used. Singleton is an object lifecycle scope, **not a thread-safety guarantee**.

Picture two requests calling one bean together:

~~~text
Request A (user=An)    Request B (user=Binh)
        |                       |
        +----------+------------+
                   |
             Singleton bean
             field currentUser
                   |
       An writes  | Binh overwrites
                   |
       An reads back -> "Binh" (wrong context)
~~~

Each request has its own data and control flow, yet **a singleton bean's field belongs to the same object on the heap**, so every invocation sees the *exact same state slot*. Spring does not create extra copies of singleton controllers/services per request.

Distinguish clearly:

| Component | Lifecycle and sharing | Suitable for holding per-request data? |
| --- | --- | --- |
| Method parameters and local variables | Each call gets its own variables/references | **Yes**, when not pointing to a shared mutable object |
| DTO/record newly created for the request | A concrete object allocated/delivered for the request | **Yes**, if not improperly reused, published, or mutated |
| Field of a singleton controller/service | One field shared across invocations | **No**, for data belonging only to a single request |
| Field of a request-scoped bean | One target bean bound to an active HTTP request | **Conditionally**, when context must be shared within the same request |
| Field of a session-scoped bean | Bound to an HTTP session, may outlive multiple requests | **Does not replace request scope**; multiple requests in the same session can run concurrently |
| ThreadLocal | Value bound to a thread, not directly to a request | **Only for managed infrastructure with cleanup**, not a default solution |
| Static field | Shared at class/classloader level | **No**, for per-request data |

**Not every singleton field is dangerous.** An immutable dependency injected via constructor, frozen configuration, a stateless service, or a thread-safe cache can be legitimately shared. What must be avoided is placing **per-request mutable state** into a shared location. Even a field with the **final** keyword only locks the *reference*, not making the referenced object automatically immutable or thread-safe.

## 2. Anti-Pattern: Storing Request Data in a Controller Field

The following example is a **Spring MVC snippet to recognize the bug**, not a standalone Java program:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnsafeGreetingController {
    private String currentName; // Shared across all requests!

    @GetMapping("/unsafe/greet")
    public String greet(@RequestParam String name) {
        currentName = name;                 // Request A may have just written "An".
        return "Hello " + currentName;      // Request B may have already written "Bình".
    }
}
~~~

If A and B interleave, A may return "Hello Bình" even though A's parameter was "An". You cannot assume this bug will appear on *every* call, because CPU scheduling is non-deterministic. This is also a **data race**: threads read/write an unsynchronized field concurrently, so value visibility depends on the Java Memory Model and happens-before relationships.

A common flawed fix is adding **synchronized** around the method. That may eliminate some races on the field, yet it turns independent request handling into a queue while retaining a mis-scoped data model. Likewise, switching to **volatile** or **AtomicReference<String>** may change visibility/atomicity, **without turning a shared memory slot into a private slot per request**. Correct synchronization mechanics do not fix wrong data semantics.

## 3. Controlled Bug Reproduction with Java 17+

The standalone Java example below simulates two requests accessing a shared object. **CountDownLatch** actively forces the interleaving order so we do not rely on Thread.sleep or scheduler luck.

Save as **RequestLeakDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RequestLeakDemo {
    static final class SharedBean {
        private String currentUser;

        String handleAn(CountDownLatch anStored,
                        CountDownLatch binhStored) throws InterruptedException {
            currentUser = "An";
            anStored.countDown();
            binhStored.await(); // Wait for B to overwrite before reading.
            return currentUser;
        }

        String handleBinh(CountDownLatch anStored,
                          CountDownLatch binhStored) throws InterruptedException {
            anStored.await();
            currentUser = "Bình";
            binhStored.countDown();
            return currentUser;
        }
    }

    public static void main(String[] args) throws Exception {
        SharedBean bean = new SharedBean();
        CountDownLatch anStored = new CountDownLatch(1);
        CountDownLatch binhStored = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> an = executor.submit(
                    () -> bean.handleAn(anStored, binhStored));
            Future<String> binh = executor.submit(
                    () -> bean.handleBinh(anStored, binhStored));

            System.out.println("Request An reads: " + an.get());
            System.out.println("Request Bình reads: " + binh.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RequestLeakDemo.java
java RequestLeakDemo
~~~

Result:

~~~text
Request An reads: Bình
Request Bình reads: Bình
~~~

**Why is the result deterministic?** A writes "An", signals B via anStored, and waits. B only writes "Bình" after receiving the signal; B signals binhStored and then A reads back. The countDown/await operations establish the happens-before relationships necessary for A to observe B's write. This example intentionally places state in a shared field to demonstrate the bug; writing production programs this way is strongly discouraged.

**A request is not a fixed thread.** In Servlet MVC, synchronous processing typically occurs on the request thread; however, when using async dispatch, @Async, CompletableFuture, or I/O libraries, parts of the work can move to another thread. Therefore, always identify **who owns the data** rather than relying on assumptions about which thread is running.

## 4. Default Solution: Stateless Singleton, Parameters, and Local Variables

The simplest approach is **passing data into methods**, creating only local variables or new result objects. A bean may hold stable dependencies, but never store the "current request" in a field.

Save as **StatelessRequestDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StatelessRequestDemo {
    static final class GreetingService {
        String greet(String user) {
            String result = "Hello " + user;
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingService();
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> an =
                    executor.submit(() -> service.greet("An"));
            Future<String> binh =
                    executor.submit(() -> service.greet("Bình"));

            System.out.println(an.get());
            System.out.println(binh.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StatelessRequestDemo.java
java StatelessRequestDemo
~~~

Result:

~~~text
Hello An
Hello Bình
~~~

Both tasks use **the same service**, yet each invocation has its own user parameter and result local variable. Regardless of the order in which the executor runs them, one task cannot overwrite the other's local variable.

An important note: **a local variable is a private reference; it does not automatically make the pointed-to object safe**. If two requests hold references to a shared mutable List or Map, mutating that collection can still cause a race. Inspect the entire object graph, not just where the variable is declared.

An easy-to-apply design rule:

~~~text
HTTP request
    -> Controller reads input and request info
    -> Per-call DTO/record
    -> Stateless service receives DTO as a parameter
    -> Repository / external client with thread-safe contract
    -> Response newly created for the caller
~~~

This is a sound default architecture for most Spring MVC REST endpoints.

## 5. Spring MVC Example: Controller and Service Carrying No Request State

The following snippets are **classes/files in a Spring MVC application with Spring Web dependencies**; they cannot be compiled with bare `javac` without Spring on the classpath. Each block represents a separate Java file.

**GreetingResponse.java** — immutable result data as a record:

~~~java
package example.web;

public record GreetingResponse(String requestId, String message) {
}
~~~

**GreetingService.java** — a service that can be a singleton because it has no request fields:

~~~java
package example.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingResponse build(String requestId, String name) {
        String message = "Hello " + name.trim();
        return new GreetingResponse(requestId, message);
    }
}
~~~

**GreetingController.java** — creates per-request info and passes it via parameters:

~~~java
package example.web;

import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greet")
    public GreetingResponse greet(@RequestParam String name) {
        String requestId = UUID.randomUUID().toString();
        return greetingService.build(requestId, name);
    }
}
~~~

When two HTTP requests arrive at **/greet?name=An** and **/greet?name=Bình**, each invocation generates a new requestId and builds its own response object. **There is no currentName/currentRequestId field** in the singleton controller or service. The final greetingService field is an intentionally shared dependency, and this example implementation keeps no request state.

The UUID here only illustrates generating a trace ID; in a real system, a tracing/request ID can come from trusted middleware or standardized observability infrastructure. **A Request ID is not authentication info or proof of authorization**.

Keep this separation even in multi-layered applications: the controller can forward a **request DTO** to the service and then to the repository; the service does not need to store the "current user" in a field. When logic needs the authenticated user, retrieve it from the appropriate security principal at the boundary and pass a well-populated, permission-checked context object.

## 6. Per-Request Objects: DTOs and Immutable Snapshots

When a request has multiple pieces of information that must travel together, rather than repeating many parameters, create a **request context belonging to the invocation**:

~~~java
package example.web;

public record RequestSnapshot(
        String requestId,
        String userId,
        String localeTag
) {
}
~~~

This record can be created in the controller from validated/normalized data and passed through service layers. The record holds final fields, and the Strings in this example are immutable. If a record contains a List, Map, or mutable object, the creator must still copy defensively when needed; the **record** keyword alone does not guarantee the entire substructure is immutable.

With a Spring service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    public String describe(RequestSnapshot snapshot, String invoiceId) {
        return "user=" + snapshot.userId() + ", invoice=" + invoiceId;
    }
}
~~~

This is an **illustrative snippet** assuming InvoiceService and RequestSnapshot are in appropriate packages/imports. Values like userId and invoiceId belong to the invocation and are not stored in fields. A singleton service can execute thousands of independent calls without needing locks merely to hold these variables.

If the data contains secrets (tokens, sensitive identifiers), retain only the minimum required for the task; avoid logging or forwarding excess snapshot data to systems that do not need it.

## 7. When to Use @RequestScope?

Sometimes multiple components within the same request need to share **a context object with a request lifecycle**, such as a correlation ID, computed localization info, or a short-lived scratch cache. Spring Web provides **request scope**: the target bean is created/maintained within the scope of an active HTTP request.

**RequestTrace.java** (a separate bean):

~~~java
package example.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestTrace {
    private final String requestId = UUID.randomUUID().toString();

    public String id() {
        return requestId;
    }
}
~~~

**TraceController.java** (singleton controller depending on a request-scoped bean):

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {
    private final RequestTrace trace;

    public TraceController(RequestTrace trace) {
        this.trace = trace;
    }

    @GetMapping("/trace")
    public String trace() {
        return trace.id();
    }
}
~~~

In Spring, **@RequestScope** defaults to a **class-based scoped proxy**. The singleton controller holds the **proxy**, and when a method is invoked during a valid HTTP request, the proxy resolves the **request-scoped target** for the current request. Two different requests get different RequestTrace targets; multiple accesses within the *same* request use the same target.

Points to understand accurately:

- **@RequestScope does not mean one separate object per thread.** If the same request orchestrates multiple concurrent tasks and those tasks actually access the same target, mutable fields inside the target still require concurrency consideration.
- A scoped bean requires an **active request context**; calling the proxy outside a request, or on an executor thread lacking the corresponding context, can fail with a scope-not-active error.
- Do not pass a request-scoped proxy or target into a background task that runs after the request ends and expect it to still work. Extract the needed data into an immutable snapshot before crossing the asynchronous boundary.
- Request scope is unnecessary when a few local variables and a DTO already solve the requirement. Adding a scope introduces an implicit dependency on the HTTP lifecycle, making tests and async handling harder.

**Request scope differs from prototype scope.** A prototype bean is created when Spring resolves a request for a new bean; if a prototype is injected directly into a singleton's constructor, the injected reference **does not automatically refresh on every HTTP request**. Likewise, do not use **@SessionScope** to emulate request scope: multiple parallel requests in the same session can still share the session object.

## 8. ThreadLocal Is Not Equivalent to Request Scope

ThreadLocal stores a value **per thread**, for example a request ID attached to a thread by middleware while handling a request. It does not establish HTTP-request ownership.

On a server using a thread pool:

1. Worker thread T1 serves request A.
2. If A sets a ThreadLocal and forgets to clear it, T1 can be reused to serve request B.
3. B mistakenly reads A's leftover value: context leakage across requests.

If an infrastructure mechanism genuinely uses ThreadLocal, it must at minimum **clean up in finally** across every error and success branch:

~~~java
public final class TraceHolder {
    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();

    private TraceHolder() {
    }

    public static void runWithTrace(String id, Runnable action) {
        CURRENT.set(id);
        try {
            action.run();
        } finally {
            CURRENT.remove();
        }
    }

    public static String currentId() {
        return CURRENT.get();
    }
}
~~~

This is a **compilable standalone Java class**, yet it only illustrates cleanup for a non-nested context. If nested contexts are allowed, you must deliberately save and restore the previous value. Avoid building a global request-state store with ThreadLocal when parameters/DTOs suffice.

Spring MVC has **RequestContextHolder** and mechanisms using thread-bound request attributes during web processing. This is infrastructure with a bind/unbind lifecycle, **which does not mean spawning an arbitrary @Async task automatically carries request attributes along**. With executors that reuse threads, relying on **InheritableThreadLocal** for request data is especially dangerous because thread creation time and request binding time do not align, and it easily carries stale contexts.

In reactive WebFlux, execution can switch threads across operators; ThreadLocal is even less reliable as a way to identify a logical request. With Reactor, **Context** is the right place for data tied to a reactive subscriber when passing directly via variables/functions is inconvenient.

## 9. Crossing the @Async / CompletableFuture Boundary: Pass a Snapshot, Do Not Borrow a Field

Suppose an HTTP controller has authenticated the user and normalized the request info. Next, long-running work needs to run on an executor:

~~~text
HTTP request on handler thread
    |
    | extracts requestId, userId; checks permissions
    v
RequestSnapshot (dedicated value)
    |
    | passed via parameter
    v
@Async / CompletableFuture / worker
    |
    | uses only the passed snapshot
    v
Result/response or background work with a clear lifecycle
~~~

Example in Spring (requires **@EnableAsync**, an executor bean named **appExecutor**, and calling the method through the Spring proxy):

**RequestSnapshot.java**:

~~~java
package example.async;

public record RequestSnapshot(String requestId, String userId) {
}
~~~

**ReportWorker.java**:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appExecutor")
    public CompletableFuture<String> build(RequestSnapshot snapshot) {
        String result = "request=" + snapshot.requestId()
                + ", user=" + snapshot.userId();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Key point: **snapshot is a parameter built before leaving the request thread**. The Spring proxy dispatches the @Async method to the executor; code inside only reads snapshot. Returning completedFuture in this method makes sense because the method has already been switched to the appropriate execution thread by the @Async interceptor, with no need to wrap another supplyAsync just to switch threads again.

With plain Java, pass the snapshot the same way:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> generateFor(snapshot), executor);
~~~

This is an **illustrative snippet** with snapshot, generateFor, and executor already declared. The lambda captures a *reference*; if snapshot or an internal object is mutated by another thread, a race still exists. Use an immutable DTO or defensive copy when crossing boundaries.

**Warnings to keep in mind:**

- @Async **does not automatically carry all ThreadLocals**, such as logging MDC or SecurityContext under all configurations. If propagation is genuinely needed, use framework-supported mechanisms such as TaskDecorator and corresponding Spring Security wrappers; do not copy security state haphazardly.
- @Async in standard proxy configuration **has no effect on self-invocation** (one method on a bean directly calling another @Async method on itself). This concerns how Spring switches threads, not a way to isolate state.
- If a task runs **after the HTTP request ends**, do not arbitrarily read HttpServletRequest, request-scoped proxies, or RequestContextHolder in the worker. Build a sufficient snapshot beforehand, and define deadlines and resource cleanup responsibilities.
- When using **thenApply/whenComplete** callbacks, a callback may run on the thread completing the future or the registering thread. Do not assume the callback is still on the "request thread."
- Do not push huge request bodies, sessions, mutable principals, or servlet request objects onto queues merely to preserve context; keep data small, safe, and fit for purpose.

## 10. With WebFlux: Isolate per Subscription, Not per Thread

In Spring WebFlux, a request is represented as a reactive pipeline. Multiple subscriptions can share a thread, and one subscription can hop threads. Passing data via parameters and creating dedicated DTOs still works well; for metadata spanning many operators, **Reactor Context** preserves info along the subscriber chain:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> response = Mono.deferContextual(view ->
        Mono.just("requestId=" + view.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "req-42"));
~~~

This is an **illustrative code snippet inside a method with Reactor dependencies**. Upon subscribing, the req-42 data is accessed from the corresponding context; it does not come from a static/field currentRequest. Reactor Context does not automatically give every request an ID like above: the application/filter must supply values along the pipeline appropriately.

If a problem only needs to pass a DTO to a function, pass the DTO directly; there is no need to push every business parameter into Reactor Context. Reactor Context is better suited for cross-cutting context across operators such as tracing and necessary technical metadata. Mind data cleanup/bounding once the pipeline completes and avoid putting secrets into logs.

## 11. Choosing the Right Scope for State

| Need | Preferred choice | What to avoid |
| --- | --- | --- |
| Name, filter, pagination of an HTTP request | Method parameters, request DTO | Mutable currentFilter field in a singleton |
| Intermediate computed values in a service | Local variables, new objects | Shared cache without clear keys and lifecycle |
| Response created specifically for the caller | Immutable DTO/record | Reusing the same mutable response builder |
| Request ID needed across several MVC layers | Pass context explicitly; @RequestScope when truly helpful | Static variables or long-lived manual ThreadLocals |
| @Async / executor work | Immutable snapshot passed as a parameter | Reading request attributes from a worker after the request |
| Cross-task tracing/logging | Infrastructure-managed context propagation | Assuming MDC moves across threads automatically |
| Reactive processing flow | DTOs through operators; Reactor Context for cross-cutting context | Attaching request info to a bare ThreadLocal |
| Genuinely shared counters/caches | Thread-safe primitives, ConcurrentHashMap, proper synchronization | Shared fields like "current user" |
| State persisted across a session | Controlled session mechanism with synchronization as needed | Treating a session bean as one request at a time |

**Legitimate shared state differs from request state.** A system-wide metrics counter can be an AtomicLong; a shared cache can use a concurrent collection; an immutable/thread-safe client can be injected into a singleton. Yet **AtomicReference<UserContext> currentUser** is still a single slot for all callers, so maintaining atomicity does not cure a mistake in request ownership.

**Request scope does not replace authorization either.** Each request having its own context does not guarantee the data inside is authenticated, or that the caller is authorized to access a resource. Permissions must be checked and private data exposure controlled.

## 12. Testing Request Isolation

Do not just run two requests sequentially and declare them safe: bugs only surface under interleaving. A testing strategy:

1. **Controlled concurrent unit tests** using CountDownLatch/CyclicBarrier so two invocations truly overlap during state writes/reads, rather than Thread.sleep and hoping the scheduler creates a race.
2. **Test two requests with distinct data**, such as userId=An, userId=Bình, and different requestIds. Assert that each result contains only its corresponding request's data.
3. **Test errors and cancellations**: if processing fails, are application-managed request contexts/ThreadLocals released? Does the pool reuse a worker carrying stale context?
4. **Test async boundaries**: tasks executing after the request thread finishes must work off snapshots, without querying closed scopes.
5. **Inspect shared dependencies**: a service might be stateless while an injected cache, mapper, builder, or collection holds mutable state. Ensure such objects are truly thread-safe or created per invocation.

For Spring application tests, combine unit tests with MockMvc/WebTestClient or HTTP integration tests appropriate for your stack. If you want to reproduce a race, control interleaving points with latches in a fixture/test seam; an uncontrolled concurrent test can pass many times and then unexpectedly fail.

## 13. Common Misconceptions

**"A Spring singleton has one instance so only one thread uses it at a time."** False. Multiple request threads can call a singleton simultaneously.

**"Every time you enter a method, fields become private copies."** False. Local variables belong to the invocation; fields belong to the object. If the object is a singleton, fields are shared.

**"Adding volatile/synchronized/AtomicReference to currentRequest will isolate requests."** Wrong data model. Synchronization can coordinate access, yet does not create per-request context.

**"Just using prototype gives every request a new instance."** Not necessarily. Prototypes are dispensed when fetching the bean; injecting once into a singleton does not refresh it on every request. Request scope has its own semantics.

**"@RequestScope provides one bean per thread."** False. Scope is based on the active HTTP request, not thread identity.

**"ThreadLocal lives for exactly one HTTP request."** False. Threads are normally reused; async tasks can run on other threads. Managed bind/cleanup and propagation are required.

**"record is always deeply immutable."** False. A record prevents reassigning component references after creation, yet a component pointing to a mutable collection/object can still be mutated.

**"No mutable fields in the service means the app is definitely thread-safe."** Not sufficient. Dependencies, static state, shared mutable inputs, I/O clients, and transaction/session boundaries must all be examined.

**"Using @Async and reading a request-scoped bean is the same as on the request thread."** Not guaranteed. Pass a snapshot or use supported propagation with a valid lifecycle; do not equate request scope with executor task scope.

## 14. Pre-Production Review Process

When reviewing a controller/service handling concurrent requests, ask yourself:

1. **Who owns this data?** One HTTP request, one user session, one workflow, or the whole application?
2. **Where does it live?** Parameter/local, new DTO, bean field, static, ThreadLocal, request scope, or shared cache?
3. **Who can read/write concurrently?** Multiple HTTP requests, multiple tabs in the same session, @Async workers, CompletableFuture callbacks?
4. **Does it need to be shared?** If not, pass via parameters or create new objects; if yes, define the right scope and synchronization mechanism.
5. **Where is the async boundary?** Which snapshot must accompany the task; which info can disappear once the request ends?
6. **How are cleanup and security handled?** Are ThreadLocal values, sensitive data, worker lifecycles, and request-scoped objects handled properly?
7. **Have we tested real interleaving?** Use thread-coordination tools in tests to verify request data does not bleed across requests.

Short anti-pattern fix example:

~~~text
WRONG:
SingletonService.currentUser = request.user
SingletonService.process() reads currentUser

RIGHT:
RequestSnapshot snapshot = extract the request's own data
SingletonService.process(snapshot) reads only the passed data
~~~

If a shared dependency must persist long-lived business data, use a store with explicit identifiers and appropriate concurrency mechanisms (such as DB transactions, optimistic locking, or keyed caches); never use a currentUser field as temporary storage.

## 15. Self-Check

**Question 1.** A `@Service` bean has no scope declared, and two requests call it concurrently. Does each request get its own service?

**Answer:** No. By default, the bean is a singleton in the Spring container. The two invocations have separate parameters/locals, yet see the same instance fields.

**Question 2.** Does replacing `currentUser` with `AtomicReference<String>` guarantee A will not accidentally read B's user?

**Answer:** No. `AtomicReference` manages operations on *one shared reference*, yet A and B still share the `currentUser` slot.

**Question 3.** If a method only takes `String userId` as a parameter, builds `String result` from `userId`, and returns it, why is it usually safe under concurrent calls?

**Answer:** Parameter/local bindings are separated per invocation; provided it does not access or mutate unsafe shared objects underneath.

**Question 4.** How does a request-scoped bean injected into a singleton work?

**Answer:** With default `@RequestScope`, the singleton normally holds a scoped proxy; the proxy resolves the target belonging to the active request when called. You must not assume the proxy works on any arbitrary executor thread later.

**Question 5.** An `@Async` task needs `requestId` after the HTTP response has finished; should it fetch the data using `RequestContextHolder` in the worker?

**Answer:** You should not rely on the HTTP thread's request context. Build an immutable snapshot before the boundary and pass it to the task; tracing/security propagation requires dedicated mechanisms.

**Question 6.** Are all fields in a singleton forbidden?

**Answer:** No. Stateless/thread-safe dependencies, immutable configuration, metrics, and properly synchronized caches remain appropriate. What is wrong is storing state that belongs to a single request in a shared memory slot with no ownership identity.

## Conclusion

**Spring's scope governs object lifecycle; concurrent invocations govern who can access it; the data model governs who owns the state.** For request-specific data, the default choice should be **stateless singleton + parameters + dedicated DTO/record**. Only use **@RequestScope** when an object genuinely needs to exist across components within the same request, and understand its proxy/lifecycle mechanics. Never use singleton fields, ThreadLocal, or prototype as an implicit way to hold the "current request." When moving to **@Async, CompletableFuture, or Reactor**, continue keeping data ownership explicit via snapshots or context propagation tailored to the execution environment.

**Further reading for implementation:** Spring Framework documentation on Bean Scopes, Request Scope, Task Execution and Scheduling/@Async, Spring MVC/WebFlux; JDK documentation on the Java Memory Model, CountDownLatch, and ThreadLocal; Project Reactor documentation on Context.
