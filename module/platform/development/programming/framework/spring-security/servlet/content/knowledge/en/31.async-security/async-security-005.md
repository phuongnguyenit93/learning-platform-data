# DelegatingSecurityContextExecutor and Executors for @Async in Spring Security Servlet

## 1. Why Does SecurityContext Disappear When Running Asynchronously?

In a **Spring Boot + Spring Security Servlet** application, an HTTP request is normally processed on a servlet container thread. After authentication, Spring Security stores the user's information in **SecurityContextHolder**. With the default **MODE_THREADLOCAL** strategy, each thread has its own SecurityContext.

For example, a controller receives an authenticated request for user **alice** and then invokes a task on a thread pool:

~~~text
HTTP request: Authorization: Basic ...
          |
          v
Servlet thread: http-nio-8080-exec-4
  SecurityContextHolder -> Authentication(name="alice")
          |
          | executor.execute(...) or @Async
          v
Worker thread: secured-async-1
  SecurityContextHolder -> ?  (not transferred from the servlet thread by default)
          |
          v
Write audit / send notification / call authorization-checked service
~~~

If you use a plain **Executor**, **ExecutorService**, **CompletableFuture.supplyAsync(...)**, or an **@Async** method with a standard thread pool, moving to another thread **does not automatically carry over** the request's SecurityContext. The outcome can be:

- **SecurityContextHolder.getContext().getAuthentication() == null** inside the worker.
- A principal-based authorization check no longer sees the user.
- Audit logs miss the requester.
- If you copy ThreadLocal manually yet forget cleanup, the worker can **leak identity** from a prior task to a subsequent task.

Spring Security provides **DelegatingSecurityContext...** wrappers to transfer a selected SecurityContext while a task runs, while restoring/clearing thread state in a **finally** block. Two key components in this lesson:

1. **DelegatingSecurityContextExecutor**: for the **java.util.concurrent.Executor.execute(Runnable)** API.
2. **DelegatingSecurityContextAsyncTaskExecutor**: for Spring's **AsyncTaskExecutor**, suitable for **@Async** as well as supported **submit(...)** calls.

The goal is not to turn every background task into "permitted to do anything", but to **preserve identity and authentication context on the right thread** so subsequent checks have the proper data.

## 2. Three Architectural Layers to Distinguish

### 2.1. SecurityContext, SecurityContextHolder, and Authentication

- **Authentication** is the object holding the principal, authorities, and authentication status; depending on login method it may be UsernamePasswordAuthenticationToken, JwtAuthenticationToken, OAuth2AuthenticationToken, or another implementation.
- **SecurityContext** holds the Authentication. It is an object; passing its reference **does not automatically create an immutable deep copy**.
- **SecurityContextHolder** provides access to the SecurityContext in the current execution context. By default, Spring Security Servlet uses ThreadLocal.
- **SecurityContextHolderFilter / SecurityContextPersistenceFilter** across different configuration generations set up and release the security context within the request lifecycle; never rely on the context remaining on the servlet thread after the request finishes.

Reading the username without assuming a concrete Authentication type:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth == null ? "anonymous" : auth.getName();
~~~

The snippet above is a **fragment placed inside a Java method that has imported** Authentication and SecurityContextHolder, not a standalone runnable program. Never cast to UsernamePasswordAuthenticationToken if the application might use JWT/OIDC.

### 2.2. Why Is InheritableThreadLocal Not the Solution for Thread Pools?

**SecurityContextHolder.MODE_INHERITABLETHREADLOCAL** allows a newly created child thread to receive a context value via Java's InheritableThreadLocal mechanism. However, thread pools **reuse threads**: workers may be created long before a new request arrives and go on to execute many tasks for many users.

This creates problems:

- The context is inherited when **the thread is created**, with no guarantee it reflects the user **currently submitting the task**.
- A thread may execute different tasks for multiple principals.
- Cleanup mistakes can cause one task to observe another task's identity.

Therefore, **never enable MODE_INHERITABLETHREADLOCAL application-wide just to "fix" @Async**. For thread pools, use wrappers that propagate context per task and restore context when the task finishes.

### 2.3. How Does the Wrapper Work?

The idea behind **DelegatingSecurityContextRunnable** (logical description, not verbatim version-specific internal source code):

~~~text
On submit:
  capture the caller's SecurityContext (if no fixed context was passed)
  wrap the original Runnable into DelegatingSecurityContextRunnable

When the worker runs:
  remember the existing SecurityContext on the worker (if needed)
  set the selected context into the worker's SecurityContextHolder
  try:
      run the original Runnable
  finally:
      restore / clear the SecurityContext on the worker
~~~

**The finally block is essential**: if the task throws an exception, the context must still be cleaned up. Never write a manual ThreadLocal setter without cleanup.

**Context capture timing:** A wrapper constructor that takes no explicit SecurityContext is used to grab the caller's context **when submitting the task** (for example calling execute), not to "freeze" a user when the Executor bean is created. This lets one Executor bean serve alice and bob across different requests with each task seeing the corresponding context.

**Note on references:** Wrappers typically hold the selected SecurityContext without promising a deep clone of every field inside Authentication. Therefore avoid mutating Authentication/SecurityContext after submission, avoid sharing the same mutable context across concurrent tasks, and never treat the wrapper as proof that credentials/tokens are still valid when a task runs minutes later.

## 3. DelegatingSecurityContextExecutor: Using with execute(Runnable)

Suppose you already have a thread-managing **Executor delegate**. You can wrap it like this:

~~~java
Executor contextAware =
        new DelegatingSecurityContextExecutor(delegate);

contextAware.execute(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    String user = auth == null ? "anonymous" : auth.getName();
    // Write audit or execute appropriately authorized business logic.
});
~~~

This is an **illustrative snippet**: the delegate variable must be defined, the executor must be lifecycle-managed, and Executor, Authentication, SecurityContextHolder, and DelegatingSecurityContextExecutor must be imported properly. When calling **execute(...)**, the caller's current context is attached to the Runnable.

### Two Constructor Styles and Security Impact

**A. Capture per caller on each submission:**

~~~java
Executor wrapped =
        new DelegatingSecurityContextExecutor(delegate);
~~~

Use when the task must run **on behalf of the user who just sent the request**. The same Executor can accept tasks from different requests without mixing contexts, provided the wrapper is used on every entry path.

**B. Using an explicitly passed SecurityContext:**

~~~java
SecurityContext serviceContext =
        SecurityContextHolder.createEmptyContext();
serviceContext.setAuthentication(serviceAuthentication);

Executor wrapped =
        new DelegatingSecurityContextExecutor(delegate, serviceContext);
~~~

This is only a **snippet**; serviceAuthentication is an Authentication created and authorized through a trusted application workflow. This configuration causes tasks to use **the exact specified context**, not the user calling execute.

The explicit-context case suits **background tasks genuinely running under a fixed service principal** with clear permission boundaries. It is **not** suitable for wrapping an Executor that handles arbitrary user requests under an admin principal, as every task could then execute with the wrong privileges.

### Executor vs ExecutorService

**DelegatingSecurityContextExecutor** exposes the **execute(Runnable)** interface. If you need **submit(Callable)** or returning a **Future**, consider the matching wrapper type, such as **DelegatingSecurityContextExecutorService** for ExecutorService. For **@Async**, do not mistakenly use a plain Executor when you have Spring's **AsyncTaskExecutor**: use the AsyncTaskExecutor-specific wrapper in the next section.

## 4. Using DelegatingSecurityContextAsyncTaskExecutor for @Async

### 4.1. Why Does @Async Need an AsyncTaskExecutor Bean?

When a method is annotated:

~~~java
@Async("securityContextExecutor")
public CompletableFuture<String> currentUser() {
    // Runs on a worker provided by the selected executor.
}
~~~

Spring creates a proxy to dispatch work to the executor named **securityContextExecutor**. If that is merely a plain pool, the SecurityContext will not necessarily be present inside the task. To ensure propagation for tasks submitted via @Async, wrap a **ThreadPoolTaskExecutor** with **DelegatingSecurityContextAsyncTaskExecutor**.

**Naming the executor explicitly** in @Async avoids Spring picking another default executor that lacks the security context wrapper.

### 4.2. Complete Application Example: Spring Boot 3.x, Security 6.x, Java 17+

Create a Spring Boot 3.x project using Java 17+ with a Gradle wrapper. **build.gradle** needs the starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

File **src/main/java/com/example/asyncsecurity/AsyncSecurityApplication.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableAsync
public class AsyncSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncSecurityApplication.class, args);
    }

    @Bean("rawAsyncPool")
    ThreadPoolTaskExecutor rawAsyncPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("secured-async-");
        // As a Spring bean, the framework manages initialize/shutdown.
        return pool;
    }

    @Bean("securityContextExecutor")
    AsyncTaskExecutor securityContextExecutor(
            @Qualifier("rawAsyncPool") ThreadPoolTaskExecutor pool) {
        // Captures caller context when each task is submitted.
        return new DelegatingSecurityContextAsyncTaskExecutor(pool);
    }

    @Bean("jobExecutor")
    Executor jobExecutor(
            @Qualifier("rawAsyncPool") ThreadPoolTaskExecutor pool) {
        // For manual executor.execute(Runnable) calls.
        return new DelegatingSecurityContextExecutor(pool);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Demo user only. Never hardcode credentials in production.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/async-identity")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Key configuration points:**

- **@EnableAsync** activates `@Async` method processing.
- **rawAsyncPool** is a real **ThreadPoolTaskExecutor** bean, so Spring manages its lifecycle. The example uses **a single worker** to test against context leakage across reused threads; production must tune pool size, queue capacity, timeouts, and saturation/rejection policies for real load.
- **securityContextExecutor** is an AsyncTaskExecutor wrapped by **DelegatingSecurityContextAsyncTaskExecutor**, invoked explicitly by name in @Async.
- **jobExecutor** is a **DelegatingSecurityContextExecutor** wrapper for manual execute(Runnable); both wrappers share the pool while capturing context independently per task submitted through them.
- **HTTP Basic** simply provides a demo user without needing a login page. Real systems can use form login/OIDC/JWT; the example service relies only on the generic Authentication interface.
- **anyRequest().denyAll()** keeps the demo exposing only endpoints with explicit authentication policies; do not copy this policy into a real app without designing its routes.
- ThreadPoolTaskExecutor is declared separately so the container initializes and shuts it down; never create an ExecutorService per request that is never closed.

File **src/main/java/com/example/asyncsecurity/CurrentUserAsyncService.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserAsyncService {

    @Async("securityContextExecutor")
    public CompletableFuture<String> identity() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
                ? "anonymous"
                : authentication.getName();

        String result = username + "@" + Thread.currentThread().getName();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Code inside **identity()** runs on **secured-async-...** when invoked through the Spring proxy and the executor bean configured above. From within this method, do not use **CompletableFuture.supplyAsync(...)** without passing another executor to create a new hop, because that hop could run on **ForkJoinPool.commonPool()** and lose the security context. Returning **completedFuture** is the contract-compatible way for @Async once the method body is already running on the worker.

File **src/main/java/com/example/asyncsecurity/IdentityController.java**:

~~~java
package com.example.asyncsecurity;

import java.util.concurrent.CompletableFuture;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final CurrentUserAsyncService service;

    public IdentityController(CurrentUserAsyncService service) {
        this.service = service;
    }

    @GetMapping("/api/async-identity")
    public CompletableFuture<String> identity() {
        // Call through the Spring-proxied @Service bean, not internal 'this'.
        return service.identity();
    }
}
~~~

Run the application in a project with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Try a request:

~~~bash
curl -i -u alice:demo-password \
  'http://localhost:8080/api/async-identity'
~~~

When configured properly, the **HTTP 200** response has a body starting with **alice@secured-async-**, for example:

~~~text
alice@secured-async-1
~~~

The trailing thread number is not a fixed contract. Requests lacking valid credentials will not enter the controller and will typically receive **HTTP 401** from the HTTP Basic entry point. Never use these demo credentials outside a local environment.

**Security note on the example:** Context passed to the worker only lets code read the caller's identity. If an identity service accesses sensitive data, the API still needs fine-grained authorization by role/scope and per resource. Never treat "having Authentication" as having permission for every object.

## 5. Testing Propagation and Anti-Leakage in the Same Thread Pool

Test at least both directions:

1. When the caller has Authentication **alice**, the worker reads **alice**.
2. After the caller clears context, the next task on the **same thread pool** must not see **alice** again.

In the example, the pool has exactly one worker to focus on testing thread **reuse**. The test does not rely on the full thread name beyond the configured prefix. Because the app has **@EnableAsync**, the service injected into the test is a Spring proxy, not an object created via **new CurrentUserAsyncService()**.

File **src/test/java/com/example/asyncsecurity/AsyncSecurityContextTest.java**:

~~~java
package com.example.asyncsecurity;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AsyncSecurityContextTest {

    @Autowired
    CurrentUserAsyncService service;

    @Autowired
    @Qualifier("jobExecutor")
    Executor jobExecutor;

    private static SecurityContext aliceContext() {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        "N/A",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        return context;
    }

    @Test
    void asyncMethodCarriesIdentityAndNextTaskHasNoLeak()
            throws Exception {

        try {
            SecurityContextHolder.setContext(aliceContext());

            String first = service.identity().get(5, TimeUnit.SECONDS);
            assertThat(first).startsWith("alice@secured-async-");
        } finally {
            SecurityContextHolder.clearContext();
        }

        // The same single-worker pool will be reused.
        String second = service.identity().get(5, TimeUnit.SECONDS);
        assertThat(second).startsWith("anonymous@secured-async-");
    }

    @Test
    void manualExecutorPropagatesCallerContext() throws Exception {
        CompletableFuture<String> result = new CompletableFuture<>();

        try {
            SecurityContextHolder.setContext(aliceContext());
            jobExecutor.execute(() -> {
                Authentication a =
                        SecurityContextHolder.getContext().getAuthentication();
                result.complete(a == null ? "anonymous" : a.getName());
            });

            assertThat(result.get(5, TimeUnit.SECONDS)).isEqualTo("alice");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.asyncsecurity.AsyncSecurityContextTest
~~~

Windows (in PowerShell/cmd inside the directory containing Gradle wrapper):

~~~powershell
.\gradlew.bat test --tests com.example.asyncsecurity.AsyncSecurityContextTest
~~~

**Expected** both tests pass without assertion errors on a compatible Boot 3.x, Java 17+, Spring Security 6.x project. This is the logically expected result, not a confirmed live run log. The first test verifies **alice** is carried to the worker and not retained for the next task; the second verifies **DelegatingSecurityContextExecutor** with execute(Runnable).

### Important Additional Pre-Production Tests

| Scenario | What to Verify |
| --- | --- |
| Caller **alice**, caller **bob** submitting interleaved | Whichever worker runs whose task sees the right identity when the task starts |
| Task throws an exception | SecurityContext on the thread pool is still cleaned up; next task does not inherit the previous user |
| Caller has no Authentication | Task must never suddenly see a stale or admin principal |
| Executor queue full | Rejection is handled properly (no silent data loss, no bypassed permission checks) |
| Caller logs out / locked after submission | Queued task must not bypass authorization policies at processing time |
| @Async from a method in the same bean | Never treat self-invocation as a proxied async task |
| Nested CompletableFuture or a second executor | Every thread hop needs its own context policy, not just the first hop |
| Multi-node application | Context is bound to the in-process task; it does not cross message brokers or other JVMs automatically |
| HTTP Basic, form login, JWT, OIDC | Concrete principal may vary; tests must not depend on a specific Authentication class |
| Security method annotations | Verify advisor/proxy order, authorization evaluation point, and expected Principal |

## 6. Common @Async Pitfalls

### 6.1. Forgetting @EnableAsync or Self-Invocation

When a method in the same object calls **this.identity()**, the call does not go through the Spring proxy, so **@Async has no effect** under default proxy mechanics. It may execute directly on the servlet thread and accidentally return the right principal, tricking developers into believing propagation succeeded.

Wrong:

~~~java
@Service
class ExampleService {
    public void handle() {
        identity(); // self-invocation: @Async may be bypassed
    }

    @Async("securityContextExecutor")
    public CompletableFuture<String> identity() {
        // ...
        return CompletableFuture.completedFuture("...");
    }
}
~~~

This is an **abbreviated snippet** showing an anti-pattern, not a standalone file. The right approach is calling a **public method of another bean through the Spring proxy**, such as IdentityController → CurrentUserAsyncService, or structuring proxied beans cleanly instead of calling `this`.

**Never place @Async only on a private method** expecting a Spring proxy to intercept it. When debugging, verify the thread name is actually **secured-async-...** rather than checking only the principal output.

### 6.2. Accidentally Using the Wrong Default Executor

If you write **@Async** without specifying a bean, Spring may locate a default executor configured via AsyncConfigurer, a TaskExecutor bean, or create a fallback depending on context. If the chosen executor is unwrapped, the worker loses the security context.

For this lesson, take the explicit approach:

~~~java
@Async("securityContextExecutor")
public CompletableFuture<String> identity() {
    // ...
}
~~~

Alternatively, in larger systems, define **AsyncConfigurer** pointing to the default wrapper so @Async methods need not repeat the name, while verifying the right bean is actually used without circular dependencies. Do not randomly create multiple wrappers across unrelated pools.

### 6.3. Nested Async and CompletableFuture

A task receiving context does not mean all work **inside it** keeps the context if it switches threads again:

~~~text
Servlet thread (alice)
  → @Async("securityContextExecutor")  [alice present]
      → CompletableFuture.supplyAsync(... commonPool) [alice not guaranteed]
          → call another service [context may be lost]
~~~

If an extra hop is needed, pass a **context-wrapped Executor** for that hop. When submitting the nested task, the worker already holds the right context so the wrapper can capture it. If using a shared fixed service context, design dedicated authorization for that service.

### 6.4. @Async Does Not Automatically Carry All ThreadLocals

SecurityContext propagation does not mean the following state travels along automatically:

- **RequestContextHolder**, HttpServletRequest, HttpSession;
- **MDC** for logging/correlation IDs;
- **LocaleContextHolder**, request timezone;
- **TransactionSynchronizationManager** and Spring transactions;
- tracing contexts or other thread-locals.

Do not try to read **HttpServletRequest** or entities tied to a closed transaction from a post-request worker. If correlation IDs/MDC are needed, configure a **TaskDecorator** or appropriate context-propagation mechanism and guarantee cleanup in finally. **Never use TaskDecorator to replace permission checks**; SecurityContext wrappers handle propagating security context specifically.

### 6.5. Handling Exceptions, Futures, and Cancellation

For @Async returning **CompletableFuture**, task errors are normally represented as exceptional completion; callers need proper **handle/whenComplete/exceptionally** rather than assuming "fire and forget" success. For @Async methods returning **void**, errors may route to **AsyncUncaughtExceptionHandler**, requiring proper monitoring/logging setup.

- The propagation wrapper must still clean up context even when the task fails.
- Never write raw tokens, passwords, or sensitive Authentication info into exception logs.
- If a task is cancelled or the queue is full, ensure business side effects and audits remain consistent; never equate successful submission with completed business work.
- Never conflate checking "the task was placed in the queue" with "the business logic executed successfully".

## 7. Security Boundaries: Propagation Is Not Authorization

Distinguish four concerns:

1. **Context capture** answers: under which authentication context was this task submitted?
2. **Authorization** answers: is that principal **permitted** to execute this business operation?
3. **Freshness/identity** answers: are the permissions, account status, or session still valid **when the task executes**?
4. **Audit** answers: who requested the task, under what authority was it executed, when, and on which resource?

For instance, user alice is permitted to view orders at submission time yet has permissions revoked before the task runs 30 minutes later. A SecurityContext snapshot can still hold old authorities, so it cannot be treated as the freshest source of permissions. For long-running work or work with significant side effects:

- Pass **requesterId/tenantId/jobId/operationId** as controlled business data rather than persisting the full SecurityContext.
- At execution time, reload **user state/permissions/target object** from a trusted source and check authorization per policy.
- When tasks live in a queue/message broker or run on another JVM, design a dedicated service identity and explicit scoped delegation (on-behalf-of); in-memory SecurityContext does not automatically serialize across brokers.
- Prove identity/authorization at both the calling layer and worker layer for high-risk business logic; never trust just a client-sent username string.
- Never store long-lived user credentials/access tokens inside a Runnable or message to "reuse" when the task runs.

### @PreAuthorize and Async Threads

A method protected by **@PreAuthorize** may be called inside or outside a worker depending on bean/proxy structure and advisor ordering. Never assume an annotation placed alongside @Async will always evaluate on the thread you expect. When method security is needed:

- Explicitly enable **@EnableMethodSecurity** when appropriate.
- Place clear permission-check boundaries at methods/services and verify behavior with integration tests through real proxies.
- Enforce ownership/tenant rules; an old authority in SecurityContext is insufficient to grant access to arbitrary resources.
- If permissions must be re-validated at task execution time, call a policy service backed by fresh data rather than reading only an authority snapshot.

## 8. Comparing Implementation Approaches

| Approach | Context on Worker | When to Use |
| --- | --- | --- |
| Plain **Executor** | Does not automatically propagate SecurityContext | User-independent tasks, or when managing other context via trusted mechanisms |
| **DelegatingSecurityContextExecutor(delegate)** | Captures per caller on execute | Manually submitted Runnables on behalf of a user |
| **DelegatingSecurityContextExecutor(delegate, fixedContext)** | Uses one explicit context | Service principal with fixed permission scope; never use to "elevate" arbitrary users |
| **DelegatingSecurityContextAsyncTaskExecutor(delegate)** | Captures per caller on @Async/submit | Spring @Async, AsyncTaskExecutor |
| **MODE_INHERITABLETHREADLOCAL** | May inherit when spawning new threads | Unsuitable as primary mechanism on reused thread pools |
| Custom **TaskDecorator** | Implementation-dependent | Propagation of MDC/tracing/other contexts; requires safe cleanup |
| **Pass only requesterId/jobId** | Does not auto-create Authentication | Long-lived jobs, cross-JVM queues, requiring re-authorization at execution |

## 9. Quick Troubleshooting

| Symptom | Cause Worth Checking | Fix |
| --- | --- | --- |
| Inside @Async, **getAuthentication() == null** | @Async runs on unwrapped pool; thread boundary drops ThreadLocal | Use **DelegatingSecurityContextAsyncTaskExecutor** and specify bean in @Async |
| Still seeing alice even after caller switched to bob | ThreadLocal manually set without clearing; fixed context misused | Use standard wrapper, check constructor, test thread reuse |
| Principal exists yet thread name is still http-nio... | Self-invocation or @EnableAsync missing; task not truly async | Call through another bean's proxy and verify thread |
| @Async works sometimes, fails sometimes | Multiple executor beans, different fallbacks, wrong qualifier annotation | Name and inject the exact AsyncTaskExecutor; inspect actual config |
| Permission check in worker sees wrong role | Context captured too early, permissions changed, proxy/method security order | Design runtime reauthorization; test with changed permissions |
| Nested CompletableFuture loses context | New hop uses commonPool / unwrapped Executor | Use wrapper on **every thread hop** |
| Async task throws exception yet HTTP still succeeds | Controller only submits without awaiting/observing Future | Define response contract, manage Future and job state |
| Fails after logout even though task was submitted | Context snapshot still exists while session/token may no longer be valid | Separate identity snapshot from current authorization state |
| Missing MDC/correlation ID | Security wrapper handles SecurityContext only | Add separate context propagation for MDC/tracing |
| Thread pool full / unbounded pending tasks | Wrong queue/pool config and missing backpressure | Bound queue, timeouts, rejection policy, monitor executor |
| @Async runs on requests using JWT/OIDC | Code assumes UsernamePasswordAuthenticationToken | Use generic Authentication interface, inspect principal type per reality |

## 10. Production Readiness Checklist

- Classify which tasks run on behalf of the current user, which need a service principal, and which should not receive a SecurityContext.
- For @Async, have **@EnableAsync**, call methods **through a proxy**, and explicitly name a **wrapped AsyncTaskExecutor** bean.
- For manual execute(Runnable), use **DelegatingSecurityContextExecutor**; for submit(Callable)/Future, use the wrapper matching that Executor type.
- Never enable **MODE_INHERITABLETHREADLOCAL** to patch thread pools and never set SecurityContextHolder manually on a worker without `finally`.
- Choose a fixed SecurityContext only with clear justification; never accidentally run user tasks with admin privileges.
- Test both context propagation and **no leak** when the pool reuses threads, including anonymous callers, failing tasks, and interleaved users.
- Never assume SecurityContext propagation carries HTTP requests, transactions, MDC, or arbitrary ThreadLocals.
- Never rely on a captured context to execute sensitive operations hours later; re-verify state, permissions, tenant, and target object at execution.
- Never log or persist long-lived tokens/credentials. Manage executor lifecycle, queue capacity, shutdown, and exceptions.
- If tasks cross JVMs, use job identity and dedicated delegation mechanisms; ThreadLocal SecurityContext does not automatically cross message brokers.
- Audit separately **requestedBy** and **executedAs** when tasks use a service principal, along with operation ID/tenant/resource ID.
- Verify the real HTTP path, method-security proxy, and Future result before concluding propagation works.

**Conclusion:** Spring Security isolates SecurityContext per thread; async processing must explicitly define each task's context. **DelegatingSecurityContextExecutor** is the tool for Runnable/Executor, while **DelegatingSecurityContextAsyncTaskExecutor** fits @Async. Wrappers provide safer propagation and cleanup than manual ThreadLocal copying, yet they do **not** replace authorization, fresh permission checks, or governance of long-running jobs.
