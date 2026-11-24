# Distinguishing Security Context Requiring Dedicated Support From Arbitrary ThreadLocal

In **Spring Framework - concurrency**, an application may receive two HTTP requests from two different users and then dispatch work to the same **ThreadPoolTaskExecutor**. If execution context is handled improperly, a worker may not know who the current user is, or worse, see information from a previous request on a reused thread.

Two types of data are commonly conflated:

1. **Arbitrary application ThreadLocal**: such as a log correlation ID, locale, requestId, or a temporary value stored for convenient access on the same thread.
2. **Security context** managed by **Spring Security**: **SecurityContextHolder**, **SecurityContext**, **Authentication**, principal, and authorities. These are not merely strings for tagging logs; they directly govern **authentication, authorization, and user isolation**.

Even though SecurityContextHolder in standard servlet apps defaults to a **ThreadLocal**-like mechanism, **you should not propagate security context across a thread pool by manually copying an arbitrary ThreadLocal**. Spring Security provides dedicated helpers such as **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextCallable**, **DelegatingSecurityContextExecutor**, **DelegatingSecurityContextExecutorService**, and **DelegatingSecurityContextAsyncTaskExecutor** to set up/tear down context at exact task boundaries.

**Takeaway to remember right away:** ThreadLocal is a **per-thread storage mechanism**; SecurityContext is **part of a security contract**; propagating SecurityContext requires policies for identity, permissions, lifecycle, and cleanup. Simply copying a ThreadLocal reference does not yield safe context propagation.

This lesson belongs to the **Execution Context** group and targets Java 17+, ExecutorService, Spring **@Async**, and Spring Security in server applications handling many concurrent requests.

## 1. Why Does Switching to a Worker Lose Context?

An HTTP servlet request is typically processed on a thread managed by the framework/container:

~~~text
HTTP request A -- Security filters --> request-thread-7
                                    |
                                    +-- SecurityContextHolder
                                    |      Authentication: alice
                                    |
                                    +-- submit(task) ---> worker-2
                                                          |
                                                          +-- Separate ThreadLocal
                                                              usually lacks Alice
~~~

In the default **MODE_THREADLOCAL** configuration, SecurityContextHolder binds information to **the currently running thread**, not to an HTTP request object that automatically travels across every executor.

When a task is dispatched using **ExecutorService.submit**, **CompletableFuture.supplyAsync**, **ThreadPoolTaskExecutor.execute**, or an **@Async** call, the worker may be a different thread. On the worker:

- **SecurityContextHolder.getContext().getAuthentication()** may be null.
- An application-created ThreadLocal also usually lacks the request thread's value.
- An improperly used worker may retain **the old value from a prior execution**.
- Transactions, MDC, RequestContextHolder, and tracing do not necessarily share the same propagation/cleanup behavior as SecurityContext.

**The difference between "no context" and "wrong context" is critical.** Missing Authentication may cause a task to be denied access as expected; wrong Authentication can cause a task to execute under another person's identity or privileges, which is far more severe.

### Spring Security Rules

Per Spring Security documentation, for standard servlet security, **SecurityContextHolder** stores the current thread's authentication info and the filter mechanism manages clearing it after the request. The basic structure is:

~~~text
SecurityContextHolder (holder + strategy)
    |
    +-- SecurityContext (current security state)
             |
             +-- Authentication
                     |
                     +-- principal
                     +-- credentials (depending on mechanism)
                     +-- authorities / roles / scopes
~~~

An **Authentication** is not merely a username. It can hold authorities, authentication method details, a principal object, and permission-related details. Therefore, a custom ThreadLocal<String> storing just a username **is not equivalent** to providing a valid SecurityContext.

## 2. How Does a Normal ThreadLocal Work?

**ThreadLocal<T>** lets each **Thread** hold its own separate T value:

~~~java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();
~~~

This is a **field declaration inside a Java class**, not a standalone program.

If the main/request thread sets REQUEST_ID="A", a pool worker **does not automatically read "A"** simply because the Runnable/lambda submitted by main can reference the static field REQUEST_ID. The ThreadLocal field is an access point; **values are looked up by Thread.currentThread()**, not by the submitting caller.

~~~text
ThreadLocal REQUEST_ID
    |
    +-- request-thread: "A"
    +-- worker-1:      null
    +-- worker-2:      "stale-B"  (if remove() was omitted previously!)
~~~

Note that ThreadLocal **does not automatically synchronize shared data**. It separates slots per thread, yet the T value can still be **a mutable object shared** across threads if you place the same reference into multiple slots.

### Thread Pools Make the Bug Worse

ThreadPoolTaskExecutor and ExecutorService typically **reuse workers**. If a task calls **ThreadLocal.set(value)** and forgets **remove()** in finally:

- The worker can be reused for a subsequent task.
- The subsequent task sees a **stale value** even though it originated from a different request.
- Sensitive data can stay attached to a long-lived thread.
- When a worker sits idle or runs long-term, stale references can keep large objects in memory.

It is not only a memory leak; for identity/authorization data, it is also a **cross-request context leak**.

## 3. Standalone Runnable Java 17: No Automatic Context Propagation and Possible Leaks

The program below is **pure Java 17**, requiring no Spring. It proves three facts on the same worker thread:

1. Caller's ThreadLocal **does not automatically reach the worker**.
2. An Executor wrapper can **capture the value at submit, set it on the worker, and remove in finally** when used properly.
3. If a task sets ThreadLocal itself and **fails to clean up**, the worker can leave a wrong value for the next task.

Save as **ThreadLocalBoundaryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalBoundaryDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static String current() {
        String value = CONTEXT.get();
        return value == null ? "<empty>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        // Example wrapper for a simple non-security ThreadLocal.
        Executor contextAware = command -> {
            String captured = CONTEXT.get();  // Read at submit time.
            worker.execute(() -> {
                try {
                    if (captured == null) {
                        CONTEXT.remove();
                    } else {
                        CONTEXT.set(captured);
                    }
                    command.run();
                } finally {
                    CONTEXT.remove();
                }
            });
        };

        try {
            CONTEXT.set("alice");

            String rawAlice = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            String wrappedAlice = CompletableFuture.supplyAsync(
                    ThreadLocalBoundaryDemo::current, contextAware)
                    .get(5, TimeUnit.SECONDS);

            CONTEXT.set("bob");

            String wrappedBob = CompletableFuture.supplyAsync(
                    ThreadLocalBoundaryDemo::current, contextAware)
                    .get(5, TimeUnit.SECONDS);

            String rawAfter = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            // Illustrate a buggy task forgetting cleanup on the worker.
            worker.submit(() -> CONTEXT.set("stale-alice"))
                    .get(5, TimeUnit.SECONDS);

            String leaked = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            // Clean up the intentional leak created in the example.
            worker.submit(CONTEXT::remove)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Raw worker thấy: " + rawAlice);
            System.out.println("Wrapped Alice: " + wrappedAlice);
            System.out.println("Wrapped Bob: " + wrappedBob);
            System.out.println("Raw sau wrapper: " + rawAfter);
            System.out.println("Giá trị bị rò: " + leaked);
        } finally {
            CONTEXT.remove();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ThreadLocalBoundaryDemo.java
java ThreadLocalBoundaryDemo
~~~

**Example stdout:**

~~~text
Raw worker thấy: <empty>
Wrapped Alice: alice
Wrapped Bob: bob
Raw sau wrapper: <empty>
Giá trị bị rò: stale-alice
~~~

Explanation:

- The first worker is created by **newSingleThreadExecutor** and lacks main's CONTEXT value, so rawAlice = empty.
- **contextAware** captures alice/bob right when **execute** is called, then sets the exact value on the worker.
- **finally CONTEXT.remove()** guarantees the worker does not retain Alice/Bob info after each wrapped task.
- A task **bypassing the wrapper** deliberately sets stale-alice and omits remove; the subsequent raw task uses the same worker and reads stale-alice.
- The final cleanup line is submitted as a task to the same worker to clear the stale value; the pool shuts down in finally.
- **get(timeout)** waits for each step to finish without relying on Thread.sleep or guessing scheduler timing.

**Important:** this wrapper is solely for teaching **non-security** ThreadLocal, not a SecurityContext propagator to copy into production. In libraries/subsystems with nested callbacks running synchronously on the same thread, you must also consider **saving and restoring the previous context value** rather than only calling remove. For security information, use dedicated Spring Security mechanisms.

## 4. Why Cannot SecurityContextHolder Be Replaced With ThreadLocal<String> userId?

A custom value like REQUEST_USER.set("alice") can be useful for generating **log labels** if the data is non-sensitive and cleaned up. However, it **does not automatically become an Authentication trusted by Spring Security**.

Distinguish clearly:

| Component | Purpose | Who Owns the Contract? |
| --- | --- | --- |
| **ThreadLocal<String> requestId** | Log correlation metadata | Application, logging framework, or context propagation |
| **MDC** | Log diagnostic context | Logging framework; usually needs TaskDecorator/context propagation |
| **SecurityContextHolder** | Access SecurityContext of current thread | Spring Security and SecurityContextHolderStrategy |
| **SecurityContext** | Holds Authentication | Spring Security; tied to authentication/authorization lifecycle |
| **Authentication** | Principal, authenticated flag, authorities, and other details | Spring Security and authentication providers |
| **AuthorizationManager / method security** | Makes resource/operation access decisions | Spring Security per application policy |
| **RequestContextHolder** | Request attributes | Spring Web, not a security store |
| **Reactor Context** | Context traveling along reactive subscriber chain | Reactor; use **ReactiveSecurityContextHolder** for reactive security |

A dangerous mistake is creating a **ThreadLocal<String> CURRENT_USER**, propagating it to a worker, and believing **@PreAuthorize**, **hasRole**, or security authorization will automatically recognize that user. Spring Security normally reads **SecurityContextHolder / Authentication** via real integration, not your custom variable.

Conversely, setting an Authentication in SecurityContextHolder **does not guarantee the user still holds permissions when a background task runs hours later**. Context propagation is a technique for placing context onto the right thread; **valid authorization decisions** are a business and policy concern that must be evaluated at the point of use.

## 5. What Dedicated Mechanisms Does Spring Security Support?

Official wrappers operate on one shared idea:

~~~text
caller thread (SecurityContextHolder)
     |
     | submit Runnable / Callable
     v
DelegatingSecurityContext* wrapper
     |
     | selects SecurityContext per constructor and submit time
     v
underlying executor
     |
     v
worker:
     set SecurityContextHolder -> delegate.run()/call()
                                   |
                                   v
                           finally clearContext()
~~~

Spring Security provides:

| Call / Executor Type | Tool |
| --- | --- |
| A specific Runnable | **DelegatingSecurityContextRunnable** |
| A specific Callable<T> | **DelegatingSecurityContextCallable<T>** |
| Executor with **execute(Runnable)** | **DelegatingSecurityContextExecutor** |
| ExecutorService with **submit/execute** | **DelegatingSecurityContextExecutorService** |
| Spring TaskExecutor | **DelegatingSecurityContextTaskExecutor** |
| Spring AsyncTaskExecutor and **@Async** | **DelegatingSecurityContextAsyncTaskExecutor** |
| Scheduled executor, scheduler | Corresponding **DelegatingSecurityContextScheduledExecutorService / TaskScheduler** variants |

**Dedicated wrappers** transfer context at task boundaries and **clear context in finally**. They do not turn a pool into an unbounded pool, do not guarantee task acceptance, and do not automatically carry every other application ThreadLocal along.

### A Fixed SecurityContext or Per-Submission Context?

Two constructor forms should be distinguished:

**Using a fixed context:**

~~~java
SecurityContext serviceContext = /* validly created context */;
Executor secured = new DelegatingSecurityContextExecutor(
        underlyingExecutor,
        serviceContext);
~~~

This is an **illustrative snippet**. Every task passing through this wrapper receives **the same supplied context**, regardless of the current caller. This mode is only appropriate when **intentionally using a fixed identity**, such as an approved internal job. It is **unsuitable for a shared request executor initialized with the first user's context**.

**Using current context at submit time:**

~~~java
Executor secured = new DelegatingSecurityContextExecutor(
        underlyingExecutor);
~~~

This is also an **illustrative snippet**. The constructor taking no SecurityContext makes the wrapper pick **the context from SecurityContextHolder when the task is submitted to the wrapper**. It is useful for multiple requests from different users: each submission uses the context present at the submission boundary.

**Important warning:** wrappers hold a **SecurityContext** reference; do not treat this as deep-copying the entire Authentication/principal/authorities. If other code continues to **mutate the same SecurityContext object**, the "captured" reference can still observe changes. Avoid mutating a shared SecurityContext across threads; if a truly immutable snapshot is needed, extract the exact required fields and business data. Spring Security also recommends creating a new SecurityContext rather than mutating Authentication in-place on a context object that may be shared.

## 6. Runnable Example With Spring Security: Right User on the Same Worker

This example uses **Spring Security Core** yet **needs no web server, filter chain, or Spring Boot**. It proves a single-worker ThreadPoolExecutor sequentially serves simulated requests from **alice** and **bob**, with the wrapper capturing the right SecurityContext on each submit and then clearing context on the worker.

Structure:

~~~text
security-context-demo/
├── pom.xml
└── src/main/java/example/SecurityContextDelegationDemo.java
~~~

**pom.xml** (Java 17, Spring Security Core 6.5.11):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>security-context-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SecurityContextDelegationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/SecurityContextDelegationDemo.java**:

~~~java
package example;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityContextDelegationDemo {
    private static void signInForDemo(String name) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        name,
                        "not-a-real-password",
                        AuthorityUtils.createAuthorityList("ROLE_USER"));

        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static String currentPrincipal() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();
        return auth == null ? "<none>" : auth.getName();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        DelegatingSecurityContextExecutorService secured =
                new DelegatingSecurityContextExecutorService(raw);

        try {
            signInForDemo("alice");

            String rawAlice = raw.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            String securedAlice = secured.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            signInForDemo("bob");

            String securedBob = secured.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            String rawAfter = raw.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Raw Alice: " + rawAlice);
            System.out.println("Wrapped Alice: " + securedAlice);
            System.out.println("Wrapped Bob: " + securedBob);
            System.out.println("Raw sau wrappers: " + rawAfter);
        } finally {
            SecurityContextHolder.clearContext();
            secured.shutdown();
            if (!secured.awaitTermination(5, TimeUnit.SECONDS)) {
                secured.shutdownNow();
            }
        }
    }
}
~~~

Run from the directory containing **pom.xml**:

~~~bash
mvn -q compile exec:java
~~~

**Application stdout**, excluding Maven/logging output:

~~~text
Raw Alice: <none>
Wrapped Alice: alice
Wrapped Bob: bob
Raw sau wrappers: <none>
~~~

**Why is the example right?**

1. **signInForDemo** creates a fresh SecurityContext and sets a simulated Authentication on the submitting thread. This is **not a production login flow**; it only creates a test fixture.
2. **raw.submit** sends a task to a worker without SecurityContextHolder set, because main's context does not travel across a thread pool automatically.
3. **secured.submit** uses DelegatingSecurityContextExecutorService to wrap the Callable. The wrapper captures the corresponding SecurityContext at Alice's **submit time**.
4. When the worker runs, the wrapper sets Alice's context and invokes the Callable; the Callable reads Authentication.getName() accurately as alice.
5. The caller replaces its context with a **new SecurityContext object** for Bob. The next submission's wrapper uses Bob, even though the executor reuses the exact same worker.
6. The wrapper clears SecurityContextHolder after each run. The final **raw** task no longer sees Alice or Bob on the worker.
7. **get(timeout)** ensures each step finishes before printing. Output does not depend on worker names or scheduler luck.

**Scope:** this is a program demonstrating library integration; it does not initialize Spring web security, verify real passwords, or grant real permissions. The Maven config uses a confirmed released version of Spring Security; in production projects, pick a maintained patch release and manage dependencies via the appropriate Spring Boot BOM.

### Why Not Write setContext Yourself Without finally?

If a task does:

~~~java
SecurityContextHolder.setContext(requestContext);
doWork();
// Forgot SecurityContextHolder.clearContext().
~~~

This is an **illustrative snippet**. The worker can retain the old Authentication when the next task is assigned to the same thread. Prefer lifecycle-managed Spring Security wrappers over copy-pasting manual setContext/clearContext snippets in every service.

## 7. MODE_INHERITABLETHREADLOCAL Does Not Solve Thread Pools

Spring Security allows configuring SecurityContext storage strategies, including:

- **MODE_THREADLOCAL**: standard default in servlet applications; context belongs to the current thread.
- **MODE_INHERITABLETHREADLOCAL**: newly created child threads can inherit the value when **the thread is created**.
- **MODE_GLOBAL**: one JVM-wide context, suited to certain specialized single-user apps, **unsuitable for multi-user web servers**.

Changing **SecurityContextHolder**'s strategy is a **global** operation and must not be done lightly while requests are in flight. In particular, MODE_INHERITABLETHREADLOCAL **does not propagate the right context per submission into a reusable worker pool**.

Pure Java example illustrating this pitfall, save as **InheritablePoolTrap.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class InheritablePoolTrap {
    private static final InheritableThreadLocal<String> USER =
            new InheritableThreadLocal<>();

    private static String current() {
        String value = USER.get();
        return value == null ? "<empty>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            USER.set("alice");
            String first = pool.submit(
                    InheritablePoolTrap::current)
                    .get(5, TimeUnit.SECONDS);

            // Caller changes, yet the pool reuses the old thread.
            USER.set("bob");
            String second = pool.submit(
                    InheritablePoolTrap::current)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Task đầu: " + first);
            System.out.println("Task sau: " + second);
        } finally {
            USER.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InheritablePoolTrap.java
java InheritablePoolTrap
~~~

Stdout with a single-worker executor created on first submit:

~~~text
Task đầu: alice
Task sau: alice
~~~

**Explanation:** InheritableThreadLocal copies/inherits values when **a new worker thread is created**. Workers are not recreated on every submit. When Bob submits a task, the old worker still holds the value inherited from Alice.

If the pool's worker was created **before** the caller set Alice, the value could be null; if the worker was created by another thread, the value could also differ. Therefore this **is not a mechanism guaranteeing per-request propagation**. The example clarifies one controlled scenario rather than claiming every pool always returns Alice.

**Do not switch SecurityContextHolder to MODE_INHERITABLETHREADLOCAL on a web server as a "quick fix for `@Async`".** It can also leak context to unintended child threads or share mutable SecurityContext references.

## 8. Proper Integration Into Spring @Async With AsyncTaskExecutor

When a method is annotated with **@Async**, Spring AOP normally routes the call through a **TaskExecutor**. If the method body needs to read Authentication, you can wrap a ThreadPoolTaskExecutor with **DelegatingSecurityContextAsyncTaskExecutor**.

The configuration below consists of **two illustrative files in an app already integrating Spring Framework 6.x and Spring Security 6.x**; compiling requires appropriate Spring Context and Security Core dependencies, not plain javac.

**SecureAsyncConfig.java**:

~~~java
package example.async;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class SecureAsyncConfig {
    @Bean("rawAsyncExecutor")
    public ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("secure-work-");
        return executor;
    }

    @Bean("securityAwareExecutor")
    public DelegatingSecurityContextAsyncTaskExecutor
            securityAwareExecutor(
                @Qualifier("rawAsyncExecutor")
                ThreadPoolTaskExecutor delegate) {

        // Do not pass a fixed context when creating the bean.
        return new DelegatingSecurityContextAsyncTaskExecutor(
                delegate);
    }
}
~~~

**SecureReportService.java**:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class SecureReportService {
    @Async("securityAwareExecutor")
    public CompletableFuture<String> currentUserReport() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()) {
            throw new AccessDeniedException("Chưa xác thực");
        }

        return CompletableFuture.completedFuture(
                "report-for:" + auth.getName());
    }
}
~~~

When another bean/controller protected by Spring Security calls **secureReportService.currentUserReport()** through the Spring proxy:

1. The request thread already has SecurityContextHolder managed by the official security mechanism.
2. **@Async("securityAwareExecutor")** selects the Security-aware wrapper instead of rawAsyncExecutor.
3. The wrapper **captures the context of the current submission**, delegates the task to rawAsyncExecutor, and sets the context for the worker before the method body runs.
4. The body can read the corresponding Authentication; when the task finishes, the wrapper clears SecurityContextHolder on the worker.
5. Return type **CompletableFuture<String>** lets the caller observe the outcome, yet **does not replace authorization at the point of data access**.

**Mandatory conditions:** Spring-managed bean, @EnableAsync enabled, async method as the proper entry point, and invocation **going through the Spring proxy**. Self-calling `this.currentUserReport()` inside the same service usually skips interception in proxy mode.

**Note:** this method only illustrates reading Authentication and identity. In a real product, merely reading `auth.getName()` **does not replace checking permission to read that report**. If a task runs late and user permissions changed, an appropriate re-authorization policy is needed.

### Why Not Pass Alice's Context Into the @Bean?

A mistake to avoid:

~~~java
SecurityContext ctx = SecurityContextHolder.getContext();
return new DelegatingSecurityContextAsyncTaskExecutor(
        delegate, ctx);
~~~

This is an **illustrative snippet inside a bean configuration method**. If you accidentally pin a context when initializing a global bean, every subsequent task may run with an empty context or an unrelated person's context. The constructor taking a SecurityContext argument should only be used when **you intentionally want every task on that wrapper to run under the same established identity**. For an executor handling multiple HTTP users, the constructor without a fixed context is usually appropriate.

## 9. @Async and CompletableFuture Do Not Automatically Propagate Context Across Every Stage

Consider a service:

~~~java
@Async("securityAwareExecutor")
public CompletableFuture<String> load() {
    return CompletableFuture.completedFuture("data");
}
~~~

If called through a proxy, **the body of load** can run on a worker where the wrapper propagated SecurityContext.

However:

~~~java
CompletableFuture<String> result = service.load()
        .thenApplyAsync(value -> {
            // Do not assume SecurityContextHolder is present here.
            return enrich(value);
        });
~~~

This is an **illustrative snippet**, not a standalone program. **thenApplyAsync** without an executor usually uses CompletableFuture's default asynchronous execution facility (typically ForkJoinPool.commonPool), so the callback may **lack the request's SecurityContext**.

Even when passing **securityAwareExecutor** to **thenApplyAsync**, understand capture timing:

- A callback scheduled after upstream completes may be submitted from **the thread that completed upstream**, not the original HTTP request thread.
- A wrapper constructed without a fixed SecurityContext grabs the context **at the moment the callback is handed to the Executor**, not necessarily the original HTTP context.
- Consequently, **each async boundary must be designed and tested individually**, especially when a task pipeline spans multiple executors or callbacks run after the request finishes.

If an entire pipeline must use a context **clearly defined for a single job**, you can create a **per-job/per-request wrapper** with a controlled fixed context, rather than using a shared singleton executor pinned to one user:

~~~java
SecurityContext taskContext =
        SecurityContextHolder.getContext();

Executor perJob = new DelegatingSecurityContextExecutor(
        rawExecutor,
        taskContext);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> loadForAuthorizedUser(), perJob)
        .thenApplyAsync(
                value -> transformForAuthorizedUser(value), perJob);
~~~

This is an **illustrative code snippet** assuming `rawExecutor`, `loadForAuthorizedUser`, and `transformForAuthorizedUser` exist. It highlights that the **perJob wrapper** keeps the same specified SecurityContext across both schedule calls. If an immutable snapshot is desired, code must ensure SecurityContext/Authentication is owned and not mutated concurrently; the constructor **does not deep-copy** the context. For long-running jobs, permissions and security status may need re-checking at execution time.

**Never place a perJob wrapper containing user-specific context into a singleton @Bean shared across all other requests.** That is a scope/ownership bug that can cause the entire app to run under the wrong identity.

## 10. SecurityContext Differs From Logging/Tracing Context

In Spring applications, a TaskDecorator is often used to carry **MDC** or observability metadata:

~~~java
import org.springframework.core.task.TaskDecorator;

public final class LoggingTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        String traceId = TraceIdHolder.get();  // At submit time.

        return () -> {
            try {
                TraceIdHolder.set(traceId);
                task.run();
            } finally {
                TraceIdHolder.remove();
            }
        };
    }
}
~~~

This is a **non-standalone illustrative snippet**, as TraceIdHolder is an assumed application abstraction. It should not be copied verbatim into production if TaskDecorator needs to handle nested scopes, rollback prior state, or tracing frameworks with different contracts.

**TaskDecorator** is a standard hook on many Spring TaskExecutors, useful for common context setup/cleanup. However:

- **MDC is not Authentication**; having a traceId in logs does not prove the caller was authenticated.
- **Propagating log context** does not make `@PreAuthorize` or operation permissions run under the right user.
- **Do not write a custom TaskDecorator that arbitrarily copies and sets SecurityContextHolder** if the library already supplies dedicated wrappers. Official security implementations understand holder strategies and their lifecycle designs.
- When combining multiple decorators/wrappers, check **setup and cleanup ordering**, error/rejection cases, and stages re-running on reused workers.

**Micrometer Context Propagation / ContextSnapshot** can help move certain contexts with registered accessors across threads, yet **never assume SecurityContext is automatically propagated across every library or reactive stage**. Choose the right integration, configure accessors, and test security along the actual execution path.

## 11. Authentication and SecurityContext Can Be Mutable: Beware Reference Sharing

An easily missed detail: **SecurityContext is an object**. When a wrapper "captures SecurityContext", in many cases it holds a **reference to that object**, rather than serializing and cloning the whole Authentication.

Dangerous example:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
context.setAuthentication(otherUserAuthentication);
~~~

This is an **illustrative snippet**. If that context object is referenced by a worker waiting to run, mutating the same object can alter the identity seen by the worker. In normal authentication flows, create a **new SecurityContext** and call **SecurityContextHolder.setContext(newContext)** instead of mutating an object that may be shared, matching Spring Security's guidance.

Consider further:

- Principal/UserDetails or Authentication instances may hold mutable state.
- Authorities/scopes may change in the database after a task is enqueued.
- Credentials/tokens are sensitive data; do not copy them wholesale into message queues or logs.
- Context capture is not proof that **the token is still valid** or that the user still holds permissions at processing time.
- A background service must never elevate privileges merely because a caller passed an unverified userId or role string.

When a task only needs to **attach the task creator to an audit record**, capturing an immutable **userId**/requestId verified at the request boundary may suffice. When a task genuinely needs to call APIs relying on Spring method security, use **intentional SecurityContext propagation** or **re-authentication/authorization on the worker**, not arbitrary Strings.

### Distinguishing Identity for Auditing vs. Permissions for Execution

| Purpose | Typically Needed Data | What Must Be Guaranteed |
| --- | --- | --- |
| Audit: who requested the job? | Verified userId, requestId, timestamp, and auth source | Cannot be spoofed by client-supplied userId; persisted per audit contract |
| Authorization: allowed to export this data? | Authentication/authorities and current resource policy | Checked at point of action, including resource-level permissions |
| Calling downstream on user's behalf | Appropriately scoped token, lifetime, and designed delegation | No expired tokens; least-privilege scope |
| Internal job under service account | Least-privilege service identity | Do not share overly broad privileges across all app tasks |
| Correlation logging | traceId or requestId | Never treat log IDs as proof of identity |

**Propagation** answers "which context is visible here"; **authentication/authorization** answers "is that context valid and permitted to perform the current action".

## 12. Spring Security Filter Chain and HTTP Request Boundaries

In Spring MVC with the Security Filter Chain, security filters manage **reading/writing/clearing** SecurityContext according to the request and appropriate session/repository.

Depending on configuration and version, **Spring MVC Callable** and official MVC async mechanisms can integrate specialized Spring Security propagation. However, this **does not mean** a Runnable manually submitted to a custom ExecutorService or an arbitrary **CompletableFuture.supplyAsync** automatically receives SecurityContext.

Distinguish clearly:

~~~text
A. MVC-managed async flow
   Security Filter Chain -> MVC async integration -> Callable path
   Framework may apply appropriate security integration.

B. User-created background work
   Controller -> customExecutor.submit(task)
   Must explicitly declare SecurityContext propagation or another policy.

C. Reactive flow
   WebFlux/Reactor publisher chain
   Uses ReactiveSecurityContextHolder / Reactor Context,
   do not assume servlet ThreadLocal behavior.
~~~

**Do not use HttpServletRequest or request-scoped objects as valid snapshots for background jobs**; after the request finishes, resource lifecycles may end. If the worker only needs a few verified parameters, capture an immutable DTO before switching threads.

## 13. Why Are ThreadLocal and InheritableThreadLocal Not Authorization Strategies?

Consider three anti-patterns (plus two related pitfalls):

**A. Putting userId into an application ThreadLocal and treating it as trusted identity.**

~~~java
CURRENT_USER.set(request.getParameter("userId"));
executor.execute(() -> readSecret(CURRENT_USER.get()));
~~~

This is an **illustrative buggy snippet**. It both trusts a client-sent userId and assumes ThreadLocal crosses to the executor. Never use this value as an authorization source.

**B. Switching SecurityContextHolder globally to MODE_GLOBAL.**

A single global context shared across all threads is a severe risk in multi-user servers. Never fix context loss by sacrificing per-request identity isolation.

**C. Enabling MODE_INHERITABLETHREADLOCAL and assuming the thread pool always spawns fresh workers.**

Pools can be long-lived, workers may be created on the first task, and inherited values can be stale or belong to another request. Child threads outside app control may also accidentally inherit identity. This does not guarantee right context per submission.

**D. Using a static mutable field for the current Authentication.**

~~~java
static Authentication CURRENT_AUTH;
~~~

In a web server with concurrent requests, all threads read/write one field and overwrite each other's users. This is never a valid replacement for SecurityContextHolder.

**E. Creating a DelegatingSecurityContextExecutor with Alice's context at application startup and sharing it across all users.**

That is **fixed-context mode**, not per-request capture mode. If each task should use the current caller's permissions, use a wrapper without a fixed context at bean creation and define proper submit boundaries.

## 14. Handling Cleanup Properly Even When Tasks Fail

A safe context propagation wrapper must treat **cleanup as mandatory**, not only when business logic succeeds.

~~~text
set context for worker
    |
    +-- task returns normally --------+
    |                                 |
    +-- task throws exception --------+--> finally cleanup
    |                                 |
    +-- task cancellation/interruption+
~~~

For custom ThreadLocal metadata, use try/finally and handle pre-existing values carefully. In nested synchronous execution, **saving previous and restoring previous** may be required; in pure worker pools with independent boundaries, **clearing** must ensure no value from a prior request remains. Never pick one cleanup style blindly regardless of framework contracts.

With Spring Security, **DelegatingSecurityContextRunnable/Callable** and executor wrappers use SecurityContextHolder's setup/clear mechanism. Do not insert a manual `finally` **clearContext()** mid-flow where the framework owns the scope and identity is still needed afterward, if doing so breaks nested scopes. Let dedicated wrappers own the entire boundary.

**If a task is rejected before starting:** the body and `finally` **inside the body never run**. Therefore, never allocate resources or hold sensitive references on the caller expecting the task's `finally` to clean them up. When a wrapper is created yet the task has not executed, review the Runnable/Callable and queue lifecycle per executor.

## 15. Capture Timing: Submit, Execute, and Future Completion

The caller's context is only accurate at **one point in time**. This is crucial if a task is submitted lazily:

~~~text
Request thread Alice:
    t0: SecurityContextHolder = Alice
    t1: create Runnable
    t2: later, thread context changed
    t3: executor.execute(Runnable)
                                |
                                +-- wrapper captures at execute/submit
~~~

With wrappers not fixed to a SecurityContext, **context is captured when wrapping the task for submission**. If code builds a Runnable under Alice yet submits it after the context was cleared, the task may no longer carry Alice.

Similarly, with **CompletableFuture**:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> load(), securedExecutor);
~~~

This is an **illustrative snippet**. With an Executor wrapper capturing at execute time, the supplier gets the context of the thread that called supplyAsync at scheduling time, provided no intermediate layer altered context.

When a **thenApplyAsync** is scheduled after upstream completes, the thread asking the executor to run the callback may be the upstream completion thread. If that thread lacks a valid SecurityContext, a capture-per-submit wrapper cannot recover the old request either.

If a multi-step pipeline must preserve consistent business context, choose explicitly:

1. Use a safely managed **per-job context** and a dedicated wrapper for that scope (never reused as an app-wide singleton).
2. Or **capture immutable user ID/command** and re-authorize at each side-effecting step.
3. Or use a context propagation integration matching your pipeline/framework, and test in practice.
4. Never chain Async callbacks without specifying executors or context contracts.

## 16. Security Boundaries in Long-Running Background Tasks

Context capture may be valid when the request starts, yet minutes or hours later:

- User permissions may be revoked.
- Sessions/tokens may expire.
- Resource permissions may change.
- The user may no longer belong to the organization.
- The job may move to another process/queue that shares no ThreadLocal.

Therefore, match your choice to business needs:

| Task Type | Typically Suitable Model |
| --- | --- |
| Short in-process task needing method security | Spring Security wrapper on executor, verify context per contract |
| Task only auditing who requested it | Capture immutable verified audit identity/requestId |
| Long-running task or sensitive privileges | Persist job identity, re-authenticate/re-authorize at execution time |
| Work across message broker | Pass verified/signed metadata or job ID; consumer builds authz context per policy |
| System task representing no user | Dedicated service account identity with least privilege; never reuse user context |
| Reactive/WebFlux pipeline | ReactiveSecurityContextHolder on Reactor Context, not just servlet ThreadLocal |

**Never serialize a raw SecurityContext** (especially credentials, tokens, or large principal objects) into a durable queue just for convenience. Store only minimal data that can be re-verified and complies with system security policies.

## 17. How to Pick the Right DelegatingSecurityContext Wrapper

| What You Have | Consider Using | Note |
| --- | --- | --- |
| A Runnable needing current context | DelegatingSecurityContextRunnable | Captures in constructor; cleanup supported |
| A Callable returning data | DelegatingSecurityContextCallable | Use when result/exception via Callable is needed |
| JDK Executor with execute only | DelegatingSecurityContextExecutor | No direct submit/get on Executor interface |
| JDK ExecutorService with submit/Future | DelegatingSecurityContextExecutorService | Wraps both Runnable and Callable, delegates lifecycle via wrapper |
| Spring TaskExecutor | DelegatingSecurityContextTaskExecutor | Supports fixed context or per-submit capture |
| Spring @Async with AsyncTaskExecutor | DelegatingSecurityContextAsyncTaskExecutor | Register named executor bean and use `@Async("...")` |
| Periodic/scheduled execution | Corresponding ScheduledExecutorService/TaskScheduler wrappers | Distinguish service-identity jobs vs. caller-bound jobs |

**Do not confuse:** context wrappers do not raise **corePoolSize**, **maxPoolSize**, or the underlying executor's queue capacity. If the pool is overloaded, tasks can still be rejected; if the executor does not accept a task, no worker carries context. You still must handle TaskRejectedException/RejectedExecutionException and retry policies.

## 18. Safe Testing: Two Users, One Worker, Zero Context Leaks

A solid integration test should cover these cases:

1. Set **Alice**'s context on the caller.
2. Submit to the **raw executor** and verify the worker does not automatically have Alice.
3. Submit through the **security wrapper** and verify the worker sees Alice.
4. Set a **new SecurityContext object** for **Bob**, submit via the same wrapper/pool, and verify Bob is seen.
5. Submit a raw task immediately afterward on **the exact same worker** and verify **neither Alice nor Bob remains**.
6. Make a protected task throw an exception; verify the wrapper still cleans up after exceptional completion.
7. If using CompletableFuture and multiple executors, test every **thenApplyAsync**/thenComposeAsync when upstream completes on another thread.
8. Test an **executor rejection** branch and a shutdown branch; never report a job as accepted if the task did not run.
9. If testing with `@Async`, always invoke **the Spring-managed bean through its proxy**, never `new` the bean directly and never self-invoke.
10. When deterministic ordering is needed, use **CountDownLatch** and **Future.get(timeout)** rather than `Thread.sleep` hoping the worker hits the right timing.

**Do not assert only the right business result.** Code running under the wrong Authentication can still return expected data for public records. Tests must inspect **principal/authorities inside the worker** and post-task cleanup.

### Testing Errors in Security Work

A realistic integration test should include:

~~~java
Future<?> failed = secured.submit(() -> {
    if (SecurityContextHolder.getContext()
            .getAuthentication() == null) {
        throw new IllegalStateException("Thiếu context");
    }
    throw new IllegalStateException("Giả lập lỗi nghiệp vụ");
});
~~~

This is an **illustrative snippet** in a scope with an ExecutorService `secured` and SecurityContext set on the caller. After `failed.get()` reports the error (`ExecutionException`), submit a **raw** task to the same worker to verify context was cleared. Do not use `Future.isDone()` as proof cleanup finished without proper observation.

## 19. Very Common Misconceptions

**"SecurityContextHolder uses ThreadLocal, so I can propagate it with any ThreadLocal wrapper."** False. You must preserve the security strategy, identity, and lifecycle; use Spring Security wrappers or integrations with equivalent contracts.

**"Just create ThreadLocal<String> USER and set username so Spring method security recognizes it."** False. Spring Security reads SecurityContext/Authentication through its own mechanisms, not your arbitrary variable.

**"Switching to InheritableThreadLocal is enough for ThreadPoolTaskExecutor."** False. Inheritance primarily occurs when a new thread is created; pooled workers can reuse old values.

**"MODE_GLOBAL lets all workers see the current user, so it is great for web apps."** False. It can make multiple requests share an identity, unsuitable for multi-user servers.

**"Using DelegatingSecurityContextAsyncTaskExecutor gives every CompletableFuture stage security context automatically."** False. Each scheduling/Executor handoff is a boundary to examine.

**"The constructor with SecurityContext and the constructor without SecurityContext behave the same."** False. One uses a fixed context; the other captures current context at submit time.

**"Spring Security wrappers deep-copy the entire Authentication."** Do not assume that. They may hold a SecurityContext reference; avoid mutating shared contexts and re-check authorization on delayed jobs.

**"Once SecurityContext is propagated, the job is authorized to read every resource."** False. Propagation does not replace authorization/resource-level checks.

**"`@Async` always runs on a worker with the right identity."** False. It requires a Spring proxy, registered executor, proper wrapper, and valid context at submit.

**"Using TaskDecorator to propagate MDC already propagates SecurityContext."** False. MDC and SecurityContext are two distinct domains; never use log metadata to decide permissions.

**"Persisting the raw SecurityContext into a queue to process tomorrow is safe."** Not by default. Context can contain sensitive data and stale permissions; long-lived jobs need clear identity/authorization policies.

**"When a task finishes, it automatically removes the ThreadLocal I set."** False. ThreadLocals do not self-remove when a Runnable finishes; pools keep threads alive, requiring boundary cleanup.

**"A client-sent userId in the request proves that user is authenticated."** False. User identity for auth/auditing must come from trusted authentication mechanisms and policy checks.

**"Reactor uses thread pools, so I can just use servlet SecurityContextHolder."** Wrong general model. Reactive security uses **Reactor Context/ReactiveSecurityContextHolder**; thread switches in reactive pipelines are not equivalent to servlet ThreadLocal flows.

## 20. Reasoning Exercises

**Question 1.** Caller has Alice's SecurityContext yet submits a Runnable via `Executors.newFixedThreadPool` without a wrapper. Is the worker guaranteed to see Alice?

**Answer:** No. Under default MODE_THREADLOCAL, the worker normally does not automatically receive the caller's context.

**Question 2.** A reused worker previously ran Bob's task. Alice's new task only uses an arbitrary ThreadLocal and forgets to remove it after running. What is the risk?

**Answer:** Subsequent tasks can see stale values from Alice or Bob if the thread is not cleaned; cross-request data leak risk.

**Question 3.** `DelegatingSecurityContextExecutor` is created with the constructor taking only Executor. When Alice and Bob submit tasks, which context does it use?

**Answer:** Per the current wrapper mechanism, it captures SecurityContextHolder **each time a task is submitted to the wrapper**, not pinned to one user at wrapper initialization.

**Question 4.** If the constructor receives a service account's SecurityContext and the wrapper is used by many different callers, which context do tasks receive?

**Answer:** The same fixed context provided, per that constructor's design; only sensible when using a shared identity is intentional and properly authorized.

**Question 5.** Why can MODE_INHERITABLETHREADLOCAL cause a worker to keep seeing Alice when Bob submits a task?

**Answer:** It transfers values when the worker is created; pools can reuse existing workers rather than spawning a new thread on every submit.

**Question 6.** An `@Async("securityAwareExecutor")` method rightly sees Alice. Then the caller uses `thenApplyAsync(fn)` without passing an executor. Is `fn` guaranteed to see Alice?

**Answer:** No. CompletableFuture has its own default async executor, usually commonPool. Context at that stage must be handled explicitly.

**Question 7.** A task runs on a worker with Alice's Authentication, yet permission on a resource was just revoked. Does checking `auth.getName()` alone authorize resource access?

**Answer:** No. Apply proper authorization policies at the point of operation; context capture does not guarantee permissions remain valid.

**Question 8.** A custom wrapper sets SecurityContextHolder yet omits clearing in `finally` because the task already completed. Is there a problem?

**Answer:** Yes. Worker thread pools can reuse threads and retain the old Authentication, leaking data or risking execution under the wrong user.

**Question 9.** A task needs to record who created the job, without executing on the user's behalf. Must you keep the entire SecurityContext in the queue for hours?

**Answer:** No. Capture the verified userId and minimal audit data, persisted per business contract, without retaining redundant credentials/Authentication.

**Question 10.** Should Reactor/WebFlux rely on the exact same ThreadLocal assumptions as servlet security?

**Answer:** No. Reactive security uses Reactor Context and dedicated integrations; identify the application type and actual propagation mechanism.

## 21. Implementation Checklist

- [ ] Identify the context type needed: **SecurityContext** vs. logging/tracing metadata.
- [ ] Do not replace Spring Security Authentication with a custom **ThreadLocal<String> userId**.
- [ ] With Spring Security servlet, understand the **SecurityContextHolderStrategy / MODE_THREADLOCAL** in use.
- [ ] Do not use **MODE_GLOBAL** in multi-user web apps to fix context loss.
- [ ] Do not use **MODE_INHERITABLETHREADLOCAL** as the default solution for thread pools.
- [ ] For Runnable/Callable, choose **DelegatingSecurityContextRunnable/Callable** when appropriate.
- [ ] For Executor/ExecutorService, use **DelegatingSecurityContextExecutor/ExecutorService**.
- [ ] For Spring @Async, identify **DelegatingSecurityContextAsyncTaskExecutor** and the right bean name.
- [ ] Never pin one user's SecurityContext inside a singleton executor handling multiple requests.
- [ ] Avoid sharing/mutating the same SecurityContext instance across multiple threads.
- [ ] Verify **`@Async` goes through the proxy**, with no self-invocation.
- [ ] If a pipeline has multiple CompletableFuture stages, verify context at **every scheduling boundary**.
- [ ] Use **TaskDecorator or tracing integrations** for MDC/request correlation; never conflate with security.
- [ ] Clean up context in `finally` or let dedicated Spring Security wrappers own it.
- [ ] Pass business input via **immutable snapshots**, never holding HttpServletRequest/transactions in the background.
- [ ] When jobs run delayed or long-term, re-check permissions/tokens/resources per policy.
- [ ] Test **Alice → Bob on the same worker**, followed by a raw task to confirm zero context leakage.
- [ ] Test error/rejection/shutdown, timeouts, and cleanup on abnormal task termination.
- [ ] Never arbitrarily serialize credentials or sensitive SecurityContext into queues/logs.

## Conclusion

**ThreadLocal merely provides per-thread storage; SecurityContextHolder is the gateway to a security context governing authentication and authorization.** When work traverses ExecutorService, CompletableFuture, or Spring `@Async`, request context does not automatically follow every thread. Manually propagating an arbitrary ThreadLocal can cause lost context, cross-request leaks, and identity mix-ups.

With Spring Security, prefer **DelegatingSecurityContextRunnable/Callable** or the matching **DelegatingSecurityContextExecutor / ExecutorService / AsyncTaskExecutor** wrappers. Explicitly choose **fixed context vs. submit-time context**, ensure **cleanup on the worker**, never treat InheritableThreadLocal as the default for pools, and test multiple users on **the exact same reused worker**. Finally, **context propagation does not replace authorization**: data, tokens, and permissions must be verified at execution time according to business requirements.

**Official reference documentation:**

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): DelegatingSecurityContext* wrappers and set/clear mechanisms.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContextHolder, Authentication, and holder strategies.
- [DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, TaskDecorator, and `@Async`.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html), [InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html), and [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
