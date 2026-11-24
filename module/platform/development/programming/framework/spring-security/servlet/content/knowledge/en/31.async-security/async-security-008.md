# Do Not Share a Mutable SecurityContext Across Multiple Tasks in Spring Security Servlet

## 1. Goal: Protecting Identity During Asynchronous Processing

When a **Spring Security Servlet** application hands off work from the request thread to an **ExecutorService**, **@Async**, **CompletableFuture**, or a scheduler, developers often want the background work to know who initiated the task. A dangerous approach is calling **SecurityContextHolder.getContext()**, keeping that exact **SecurityContext** object, and passing the same instance to multiple tasks.

**SecurityContext is a mutable object**: calling **setAuthentication(...)** swaps the Authentication held by the context. If multiple tasks share one instance, one task changing Authentication can cause another task to read an identity and permissions that do not belong to it. Consequences can include querying the wrong tenant, processing data under another user's privileges, or writing wrong audit logs.

This lesson helps you:
- Understand how **SecurityContextHolder**, **ThreadLocal**, **SecurityContext**, and **Authentication** differ.
- Distinguish **context propagation** from **context isolation**.
- Know why **setContext(...) does not deep-copy SecurityContext**, and `clearContext()` cannot undo a race that already occurred.
- Reproduce the bug with a **Java 17** example using `CountDownLatch` for deterministic results.
- Create an independent SecurityContext per task, manage mutable Authentication, and clean up ThreadLocal.
- Use **DelegatingSecurityContextRunnable/Executor** wrappers properly, understanding their limits when sharing mutable objects.
- Prefer passing an **immutable actor ID + re-authorizing at the business layer** for long-running jobs.
- Design tests for concurrency, thread reuse, session concurrency, logout, and permission revocation.

**Scope:** Spring Security Servlet. Spring WebFlux has a different reactive context mechanism; do not apply Servlet ThreadLocal-based rules verbatim.

## 2. Three Layers of State: ThreadLocal, SecurityContext, Authentication

### 2.1. SecurityContextHolder Holds a Reference for the Current Thread

Typical identity-reading code:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();
~~~

In the Servlet stack, **SecurityContextHolder** typically uses a **ThreadLocal** strategy. ThreadLocal gives thread A and thread B separate storage slots. Yet if both slots point to **the exact same object**, having two ThreadLocal slots **does not create two copies**.

~~~text
Worker thread A -> ThreadLocal A ---+
                                     +---> SecurityContext S
Worker thread B -> ThreadLocal B ---+              |
                                                    v
                                          Authentication = alice
~~~

After B calls **S.setAuthentication(bob)**, both threads can see S holding bob. Much like two Java variables pointing to one mutable List: different variable names do not make the List two independent objects.

### 2.2. SecurityContext Is a Mutable Container

SecurityContext exposes **getAuthentication()** and **setAuthentication(...)**. To create a new context object:

~~~java
SecurityContext independent =
        SecurityContextHolder.createEmptyContext();
independent.setAuthentication(verifiedAuthentication);
~~~

Whereas this merely grabs the current instance:

~~~java
SecurityContext reference = SecurityContextHolder.getContext();
~~~

Storing **reference** in a static field, singleton instance, or multiple Runnables means **sharing a mutable object**. Calling **SecurityContextHolder.setContext(reference)** on another thread only installs that reference into the new thread's SecurityContextHolder; it neither deep-copies nor freezes state.

### 2.3. Authentication and Principal Can Also Be Mutable

Even when two SecurityContexts are distinct:

~~~text
SecurityContext A --+
                    +--> Authentication X --> mutable principal/details
SecurityContext B --+
~~~

they may share the same **Authentication** or a mutable **principal**. Certain Authentication implementations allow mutating **details**, erasing credentials, or holding mutable domain/principal objects. Thus, **calling `createEmptyContext()` and assigning the exact same `original.getAuthentication()` to multiple contexts does not guarantee full isolation**.

There is no universal, safe API to deep-copy every Authentication type. For long-lived async jobs, a better approach is usually passing **immutable identifiers and parameters**, then verifying permissions at execution time rather than passing the whole SecurityContext or sensitive credentials/claims.

## 3. Context Propagation Does Not Equal Context Isolation

**Propagation:** how can a task on another thread receive the appropriate SecurityContext?

**Isolation:** when two tasks run concurrently, can task A have its active principal/authorities altered by task B?

These are **two independent properties**. A wrapper may transfer the right object to a worker thread, while that same object can still be shared across other tasks.

~~~text
Request: SecurityContext S (alice)
                 |
         +-------+--------+
         |                |
         v                v
   Async task A      Async task B
   setContext(S)     setContext(S)
   read: alice       S.setAuthentication(bob)
   read: bob         [shared mutation]
~~~

Some consequences:
- **Wrong-user authorization:** task A processes Alice's data yet later reads Authentication as Bob.
- **Wrong audit:** an operation executed by A records B's actor name.
- **Tenant confusion:** A can mistakenly access another tenant's data if services rely on the mutated context.
- **Stale privilege:** a context captured before logout or permission revocation is still used in delayed background work.
- **Thread leak:** a thread pool forgetting to clear context can let a later job see the previous job's identity.

**Do not conclude Spring Security automatically spreads SecurityContext to every thread.** Sharing bugs happen when application code, wrappers, session/repository settings, or a propagation mechanism passes **the same instance** to multiple execution scopes. Conversely, an executor without propagation configured may simply see a null Authentication.

## 4. Common Dangerous Scenarios

### 4.1. Capturing the Same Context for Multiple Runnables

~~~java
SecurityContext shared = SecurityContextHolder.getContext();

executor.execute(() -> {
    SecurityContextHolder.setContext(shared);
    try {
        processOrderA();
    } finally {
        SecurityContextHolder.clearContext();
    }
});

executor.execute(() -> {
    SecurityContextHolder.setContext(shared);
    try {
        processOrderB();
    } finally {
        SecurityContextHolder.clearContext();
    }
});
~~~

This is an **anti-pattern snippet**, not a standalone Java file. Both tasks share one object. **clearContext()** only cleans the thread's context after the task ends; it does not stop task B from mutating the object while task A is running.

### 4.2. Passing a Shared Context to Wrappers

~~~java
SecurityContext shared = SecurityContextHolder.getContext();

Runnable a = new DelegatingSecurityContextRunnable(taskA, shared);
Runnable b = new DelegatingSecurityContextRunnable(taskB, shared);
~~~

**DelegatingSecurityContextRunnable** installs the context on the thread while the delegate runs and handles cleanup/restore per contract, yet **it does not deep-copy `shared`**. If `shared` is mutated while tasks wait or run, wrappers can still observe the mutation.

### 4.3. Two Concurrent Requests Sharing the Same HttpSession

In some session-based designs depending on repository/lifecycle, two requests in the same session may reference a shared context. If custom authentication code calls **SecurityContextHolder.getContext().setAuthentication(newAuth)**, one request can affect the other.

~~~text
Browser session S
    |                |
    v                v
Request A          Request B
    |                |
    +---- context X --+
               |
       setAuthentication(...)
~~~

This is a **scenario to test against your actual configuration**, not a claim that every version/repository shares one instance. Creating a fresh context whenever authentication infrastructure must change Authentication avoids mutating an old context still referenced elsewhere.

### 4.4. MODE_INHERITABLETHREADLOCAL or MODE_GLOBAL

**MODE_INHERITABLETHREADLOCAL** lets child threads inherit a value at thread-creation time; that does not make it safe for thread pools reused across different users. **MODE_GLOBAL** is unsuitable for multi-user servers because it creates global shared state. Never pick these modes merely to "fix" `@Async` missing Authentication.

## 5. Runnable Java 17 Example: Shared Context vs Isolated Context

Uses Spring Security Core to reproduce **object reference sharing** without starting an HTTP server. The sample includes **CountDownLatch** to force read/mutate/re-read steps into deterministic order, avoiding flaky tests caused by `Thread.sleep`.

Expected output:

~~~text
shared: alice -> bob
isolated: alice -> alice, bob -> carol
~~~

The first case is intentionally **broken**; the second uses an **independent context** per job. Authentication in this lesson is a **pre-authenticated test fixture for simulation only**; never construct a similar Authentication from an unverified username in a real API.

Maven structure:

~~~text
context-isolation/
├── pom.xml
└── src/
    ├── main/java/example/context/ContextIsolationDemo.java
    └── test/java/example/context/ContextIsolationDemoTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. src/main/java/example/context/ContextIsolationDemo.java

~~~java
package example.context;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextIsolationDemo {
    private ContextIsolationDemo() {
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            System.out.println("shared: " + sharedRace(pool));
            System.out.println("isolated: " + isolatedContexts(pool));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    // Only to simulate a trusted Authentication in the demo.
    // Never accept an arbitrary username from a real request to build this token.
    private static Authentication auth(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static SecurityContext newContext(String name) {
        SecurityContext ctx = SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(auth(name));
        return ctx;
    }

    private static void await(CountDownLatch latch)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Latch timed out");
        }
    }

    // INTENTIONALLY BROKEN: both jobs mutate/read the same instance.
    static String sharedRace(ExecutorService pool) throws Exception {
        SecurityContext shared = newContext("alice");
        CountDownLatch readerReady = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);

        Future<String> reader = pool.submit(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                readerReady.countDown();
                await(changed);
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<?> writer = pool.submit(() -> {
            await(readerReady);
            shared.setAuthentication(auth("bob"));
            changed.countDown();
            return null;
        });

        writer.get(10, TimeUnit.SECONDS);
        return reader.get(10, TimeUnit.SECONDS);
    }

    // PROPER OBJECT ISOLATION: each task owns its own context.
    static String isolatedContexts(ExecutorService pool) throws Exception {
        SecurityContext alice = newContext("alice");
        SecurityContext bob = newContext("bob");
        CountDownLatch readerReady = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);

        Future<String> reader = pool.submit(() -> {
            SecurityContextHolder.setContext(alice);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                readerReady.countDown();
                await(changed);
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> writer = pool.submit(() -> {
            SecurityContextHolder.setContext(bob);
            try {
                String before = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                await(readerReady);
                bob.setAuthentication(auth("carol"));
                changed.countDown();
                String after = SecurityContextHolder.getContext()
                        .getAuthentication().getName();
                return before + " -> " + after;
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        String bobResult = writer.get(10, TimeUnit.SECONDS);
        String aliceResult = reader.get(10, TimeUnit.SECONDS);
        return aliceResult + ", " + bobResult;
    }
}
~~~

**Reading the code:** `sharedRace`'s reader attaches **shared** to ThreadLocal and reads alice. The writer waits until the reader starts, then changes Authentication on **shared** itself to bob. The reader passes the latch and reads again: it sees bob because it is the same object. In `isolatedContexts`, alice and bob are built from **two `createEmptyContext()` calls** with two independent test Authentications; the writer changes bob to carol while alice's reader stays unchanged.

The **clearContext()** step in `finally` prevents ThreadLocal leaks when the pool reuses threads. Yet it **cannot fix the race in `sharedRace`** because the object mutation already happened before cleanup.

### 5.3. Run Command and Expected Stdout

In the Maven project root directory:

~~~bash
mvn test
mvn -q exec:java -Dexec.mainClass=example.context.ContextIsolationDemo
~~~

Two lines of program stdout, excluding Maven/tooling logs:

~~~text
shared: alice -> bob
isolated: alice -> alice, bob -> carol
~~~

CountDownLatch enforces ordering instead of sleep, so the program does not rely on a race happening by chance. Actually running it requires Java 17, Maven, and network access to dependencies on initial download.

## 6. Unit Tests with JUnit

Create **src/test/java/example/context/ContextIsolationDemoTest.java**:

~~~java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class ContextIsolationDemoTest {

    @Test
    void sharedContextChangesAnotherTasksIdentity()
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            assertEquals("alice -> bob",
                    ContextIsolationDemo.sharedRace(pool));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    @Test
    void independentContextsRemainIsolated()
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            assertEquals("alice -> alice, bob -> carol",
                    ContextIsolationDemo.isolatedContexts(pool));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

The two tests confirm:
1. **Negative case:** when sharing a mutable object, one task can observe its principal changed by another task.
2. **Positive case:** two independent contexts do not affect each other's identity when one context has its Authentication replaced.

This is an **object isolation unit test**; it does not yet prove session integration, Servlet filters, or Spring Boot-managed executors. Separate real integration tests are needed.

## 7. Creating a Fresh SecurityContext: Necessary but Not Sufficient

When **authentication infrastructure** has verified the principal and needs to install a new Authentication, the pattern avoiding mutation of the old context is:

~~~java
SecurityContext fresh =
        SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(fresh);
~~~

This is an **illustrative snippet**, not a complete login endpoint. **verifiedAuthentication** must come from a trusted verification source. Never construct a `UsernamePasswordAuthenticationToken` with `isAuthenticated=true` just because a request supplied a username.

By contrast, the following mutates the existing object:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

If that context is still referenced by another request or another Runnable, that mutation can affect them. Understand `SecurityContextRepository`, `HttpSession`, and lifecycles in your running Spring Security version.

### 7.1. Shallow Copy Trap

~~~java
SecurityContext original = SecurityContextHolder.getContext();
SecurityContext first = SecurityContextHolder.createEmptyContext();
SecurityContext second = SecurityContextHolder.createEmptyContext();

first.setAuthentication(original.getAuthentication());
second.setAuthentication(original.getAuthentication());
~~~

**first != second**, yet both may still share **the exact same Authentication instance**. A mutable Authentication or principal altered in the first job can still affect the second job. Thus, **separating only the SecurityContext wrapper does not automatically isolate all mutable data**. There is no universal deep-copy mechanism for every OAuth2/JWT/form-login Authentication type.

### 7.2. Captured Permission Snapshots Can Expire

Even when neither the context nor Authentication is altered by another task, permissions can be **revoked** after scheduling. A job running 1 hour after a user logs out cannot automatically exercise every permission held at enqueue time. Define clear policies for **permissions at request time**, **permissions at execution time**, token expiry, service identities, and user delegation.

**Object isolation** prevents cross-task races; **fresh authorization** addresses whether permissions are still valid; **least privilege** limits each job's blast radius. These three goals do not substitute for one another.

## 8. DelegatingSecurityContextRunnable and Executor

Spring Security provides wrappers such as **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor**, **DelegatingSecurityContextExecutorService**, and **DelegatingSecurityContextAsyncTaskExecutor** to carry SecurityContext into work on other threads.

Example snippet:

~~~java
SecurityContext context =
        SecurityContextHolder.getContext();

Runnable wrapped = new DelegatingSecurityContextRunnable(
        () -> performWork(), context);

executor.execute(wrapped);
~~~

The wrapper sets the delegate's context during execution and cleans/restores per contract. However, **it does not deep-copy `context`**. Passing the same **context** instance to multiple wrappers can still share a mutable object.

Note two cases:
- **Explicit context:** passing an existing SecurityContext object into the wrapper; tasks can observe mutations on that object.
- **Capture context at wrap/submit time:** certain constructors/executor wrappers grab the current context at an API-defined moment; **capture does not mean an immutable snapshot**.

To give each task its own object, actively manage **ownership** and Authentication/principal data. With **@Async**, configuring **DelegatingSecurityContextAsyncTaskExecutor** handles propagation, yet it does not make arbitrary Authentication mutations thread-safe.

Snippet for cases where a job genuinely needs a SecurityContext:

~~~java
SecurityContext taskContext =
        SecurityContextHolder.createEmptyContext();
taskContext.setAuthentication(trustedAuthForThisTask);

Runnable task = new DelegatingSecurityContextRunnable(
        () -> performWork(), taskContext);
executor.execute(task);
~~~

**trustedAuthForThisTask** must be a system-controlled authentication result and must not be shared as a mutable object across multiple tasks. This snippet is not a complete Java file; `performWork`, `trustedAuthForThisTask`, and `executor` must be declared by the application. If only an actor ID is needed, avoid passing the entire context.

## 9. In Spring MVC: Often Only an Immutable Actor ID Is Needed

For background jobs, a more testable pattern is having the authenticated controller **extract a stable identifier**, dispatch an immutable command DTO, and have the worker check permissions per business contract.

Illustrative example in `@RestController`:

~~~java
@PostMapping("/reports")
ResponseEntity<Void> queue(
        @CurrentSecurityContext(
                expression = "authentication") Authentication auth,
        @RequestBody CreateReportRequest request) {

    String actorId = auth.getName();
    jobQueue.enqueue(new ReportJob(actorId, request.reportId()));
    return ResponseEntity.accepted().build();
}

record ReportJob(String actorId, long reportId) {}
~~~

This is a **snippet**, not a standalone file: Spring MVC/Security imports, `CreateReportRequest`, `jobQueue`, and config are required. **actorId** is an immutable `String`, not a mutable SecurityContext; never serialize Authentication or access tokens into a queue.

However, this pattern **does not solve authorization by itself**:
- The controller must run behind proper authentication in a protected endpoint.
- **auth.getName()** must be interpreted under your identity contract; multi-tenant/multi-issuer systems may need **issuer + subject + tenant**, not just an email/display name.
- The client-supplied report ID could belong to someone else. Check ownership/ACL on enqueue and likely **re-check at execution**.
- Workers using service credentials must separate the **requesting actor** from the **executing principal**, avoiding forging an authenticated Authentication from an untrusted actorId.
- Job payloads need integrity/idempotency/expiry and proper auditing.
- When browsers send cookies automatically, POST requests still require proper **CSRF protection**; offloading work asynchronously does not make CSRF disappear.

### When Must SecurityContext Be Propagated?

It may be necessary when legacy APIs or method-security code read `SecurityContextHolder` directly inside the worker. In that case, use a standard wrapper with a separately owned context and clear lifetime, and test permissions; avoid managing static contexts manually. In long-running jobs, never assume a context snapshotted at enqueue time grants indefinite access after logout.

## 10. Servlet Session Concurrency and Identity Changes

When a web app uses HttpSession, two requests in the same session can run concurrently. Depending on the repository and context-storage mechanism, they might reference a shared SecurityContext or race on session updates. If a custom filter or controller swaps Authentication **on the old object**, there is a risk of affecting the other request.

Scenarios to consider:
- Two browser tabs concurrently using the same session.
- One long-running request while another request logs out or switches accounts.
- Re-authentication or step-up authentication while another request is reading authorities.
- APIs having both web sessions and Bearer tokens in separate `SecurityFilterChain`s.
- A background task holding a context reference that outlives the originating request.
- Session invalidation/role revocation while a job is still pending.

To prevent this, **never treat `SecurityContextHolder` as a global state store**, avoid mutating an existing object if it could be shared, and let authentication infrastructure and the repository manage version-appropriate lifecycles. Test concurrency against real session storage rather than inferring safety from a single MockMvc request.

## 11. ThreadLocal Cleanup and Context Restoration

An executor reuses threads. If task A installs alice's context without cleaning up, task B can keep seeing alice even though task B was initiated by bob. Basic rule for dedicated worker threads:

~~~java
SecurityContextHolder.setContext(contextForThisTask);
try {
    doWork();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

**clearContext() is mandatory in manually managed context code** to prevent leaks across thread reuse, yet it **cannot fix two tasks having shared the same object beforehand**.

If work runs nested inside a thread that already holds a valid context, unconditional clearing is not always right: you may need to **restore the previous context**. Use Spring Security's standard wrappers/strategies for nested tasks instead of hand-rolling the whole lifecycle.

Never switch to **MODE_GLOBAL** or **MODE_INHERITABLETHREADLOCAL** as a "general fix" for pooled executors. New threads may inherit context once, while worker threads reused across users have a different lifecycle.

## 12. Practical Testing Strategy

| Test | Objective |
| --- | --- |
| Shared mutable context with CountDownLatch | Prove A can observe B's new Authentication |
| Independent contexts | Prove mutating context B does not affect context A |
| Single-worker thread pool running two jobs sequentially | Catch leftover context from the prior job |
| Two users alice/bob running concurrent work | Ensure actor/tenant data never mixes |
| Two requests sharing HttpSession | Test concurrent Authentication changes/logout |
| Job waiting long after user logs out | Verify policy on still-valid permissions |
| Authorities revoked while job is queued | Verify re-authorization at execution time |
| Task failing with an exception | Verify context cleanup in `finally` |
| Nested wrapper/executor invocation | Verify restoration of caller context |
| Retried long-running task | Verify idempotency, current permissions, and auditing |

### 12.1. Testing Thread Reuse

Test-guidance snippet, not standalone:

~~~java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();
try {
    oneWorker.submit(() -> {
        SecurityContextHolder.setContext(contextForAlice);
        try {
            assertAlice();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }).get();

    oneWorker.submit(() -> {
        assertNoAuthenticationFromPreviousTask();
    }).get();
} finally {
    oneWorker.shutdownNow();
}
~~~

The helpers **assertAlice**, **assertNoAuthenticationFromPreviousTask**, and variable **contextForAlice** must be defined in the real test. Using a single worker guarantees both tasks run on the same thread, confirming **SecurityContextHolder.getContext().getAuthentication()** no longer holds Authentication from the prior task.

### 12.2. Checking Identity at Multiple Checkpoints

A reliable integration test should measure identity at **start**, **before calling services**, **before commit**, and **when writing audit logs**:

~~~text
Task A: alice -> alice -> alice -> alice
Task B: bob   -> bob   -> bob   -> bob
~~~

Assert not only HTTP status, but also **record owner/tenant** and actual actor. When using async Servlet/Callable, custom Executors, or @Async, test against **the exact production execution model and security chain**. MockMvc's `.with(user(...))` does not prove all context propagation or real OIDC/JWT permissions.

## 13. Common Mistakes

1. **"ThreadLocal is thread-safe for all objects."** False: different slots can point to the same mutable object.
2. **"setContext() makes a copy."** False: it installs the context reference.
3. **"DelegatingSecurityContextRunnable deep-copies Authentication."** False: the wrapper mainly handles propagation/lifecycle.
4. **"createEmptyContext() plus setting the same old Authentication is a deep copy."** False: Auth/principal may still be shared.
5. **"clearContext() eliminates races."** False: it cleans the thread after execution, not preventing another task from mutating the object during execution.
6. **"@Async automatically gets the right Authentication."** Not guaranteed; depends on context propagation and executor configuration.
7. **"Having a username lets you build an authenticated token for the job."** False when the username is unverified; that bypasses authentication.
8. **"A job permitted at enqueue time stays permitted forever."** Not by default; permissions can be revoked or changed.
9. **"Sharing context via a static field makes access convenient."** Extremely dangerous: can make multiple users share one identity.
10. **"A unit test returning 200 is enough."** Insufficient; concurrency tests, cleanup tests, and authorization/resource-ownership checks are needed.
11. **"Spring-managed sessions make all custom mutations safe."** False: custom filters can mutate a context referenced by another request.
12. **"No need to distinguish initiator and executor in audit logs."** False: a job may be scheduled by a user yet executed under different service credentials.

## 14. Production Checklist

- [ ] Determine whether a task truly needs SecurityContext or only an actor ID/tenant ID.
- [ ] Never put SecurityContext in a static field/singleton/cache shared across users.
- [ ] Never share one mutable instance across multiple independent tasks.
- [ ] When creating separate contexts, check whether Authentication/principal/details are still shared.
- [ ] Enforce a clear lifecycle: capture, submit, start, finish, cleanup/restore.
- [ ] Avoid mutating Authentication on a context that could be referenced by other requests/tasks.
- [ ] Use proper Spring Security wrapper APIs when propagation is needed, without assuming they create immutable snapshots.
- [ ] Avoid MODE_GLOBAL and misusing MODE_INHERITABLETHREADLOCAL with pooled threads.
- [ ] Never build authenticated tokens from unverified caller-supplied data.
- [ ] Define re-authorization policies when jobs run after logout or permission revocation.
- [ ] Never pass raw credentials/access tokens/refresh tokens through queues unnecessarily.
- [ ] Maintain tests for shared/isolated, reuse, concurrency, sessions, exception cleanup, and role revocation.
- [ ] Log clear actor/tenant/resource audits and alert on cross-user data access.
- [ ] Continue enforcing security rules and CSRF when browsers use sessions/cookies.

## 15. Self-Assessment Questions

1. **SecurityContextHolder uses ThreadLocal, so is SecurityContext automatically immutable?** No; ThreadLocal only stores a per-thread reference.
2. **Can two threads hold the same SecurityContext?** Yes, if code/wrappers/repositories pass the same instance.
3. **What happens if one task calls `setAuthentication(bob)` on a shared context?** Another task can see bob.
4. **What does `clearContext()` solve?** Clears ThreadLocal after work finishes; does not separate a shared object.
5. **Does `DelegatingSecurityContextRunnable` deep-copy objects?** No.
6. **Does `createEmptyContext() + original.getAuthentication()` provide full isolation?** Not necessarily; Authentication may still be the same reference.
7. **Does every background job need SecurityContext?** No; many jobs only need an immutable actor ID with a clear policy.
8. **What if a user loses permissions after enqueueing?** Design re-authorization/revocation according to business requirements.
9. **Why use `CountDownLatch` instead of `Thread.sleep` in unit tests?** To lock event ordering and make tests deterministic.
10. **What is the difference between propagation and isolation?** Propagation delivers context to a task; isolation prevents one task from altering another task's context.

**Conclusion:** In Spring Security Servlet, **SecurityContext is a mutable object**. Passing a shared reference across multiple tasks lets one task alter another task's identity and permissions. **Isolate context and authentication state per task**, manage cleanup/restore according to lifecycle, do not treat propagation wrappers as proof of isolation, and for long-running background work prefer **immutable identity + execution-time authorization**.
