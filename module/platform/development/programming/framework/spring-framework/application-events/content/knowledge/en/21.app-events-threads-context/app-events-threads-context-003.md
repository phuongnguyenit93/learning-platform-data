# SecurityContext in Async Listeners of Spring Application Events

In Spring Security, the authenticated user's identity is typically accessed via `SecurityContextHolder`. By default, a synchronous Spring Framework `@EventListener` can read the `Authentication` of the thread publishing the event. However, when `@Async` is added, Spring dispatches execution to another executor. With the default strategy `SecurityContextHolder.MODE_THREADLOCAL`, **the SecurityContext does not automatically move to the worker thread**. Therefore, an asynchronous listener may see `null` instead of the user who published the event.

The right solution is not to rely on thread names or enable global `ThreadLocal` inheritance, but to determine the permission requirements of the work and then **propagate `SecurityContext` on a per-task basis** if truly needed—for example, using `DelegatingSecurityContextAsyncTaskExecutor`. This class wraps the task, sets the context on the executing thread, and clears/restores the thread context according to Spring Security's mechanism after the task finishes.

This lesson explains the mechanism, two design options (propagating context vs. passing a business `actorId`), how to configure `@Async`, Java 17+ testing with JUnit 5, and risks around permissions, thread pools, transactions, reactive context, async errors, and long-lived event processing.

## 1. What Scope Does SecurityContext Actually Belong To?

Different objects play different roles:

| Object | Contents | What it does not automatically guarantee |
| --- | --- | --- |
| `Authentication` | Principal, authentication state, and authorities | Current permissions at a future point in time |
| `SecurityContext` | Container holding `Authentication` | A completely independent immutable snapshot |
| `SecurityContextHolder` | Access gateway backed by `SecurityContextHolderStrategy` | That every thread's context is always identical |
| `ApplicationEventPublisher` | Publishes events to Spring listeners | Propagating `SecurityContext` or persisting events durably |
| `@Async` | Schedules method invocation via an executor | Automatically copying `SecurityContext`, transaction, request scope, or MDC |

Servlet/imperative Spring Security normally uses `MODE_THREADLOCAL`. A request thread may hold an `Authentication` for `alice`; a thread in the listener's pool does not automatically carry that `Authentication`.

~~~text
Synchronous (default):
  request-thread: SecurityContext(alice)
       |
       +-- publishEvent(DocumentApproved)
              |
              +-- @EventListener runs on request-thread
                     -> SecurityContextHolder: alice

@Async with a plain executor:
  request-thread: SecurityContext(alice)
       |
       +-- publishEvent(DocumentApproved)
              |
              +-- schedule task
       |
       +-- returns / ends request

  worker-thread: SecurityContext(usually empty)
       |
       +-- @Async @EventListener
              -> getAuthentication() may be null
~~~

Consequently, having `event.actorId()` equal to `alice` does not mean `SecurityContextHolder` on the worker thread holds `alice`'s `Authentication`. **Business payload** and **security execution context** are two independent things.

## 2. Why Can Adding @Async Lose Identity?

A regular listener:

~~~java
@EventListener
public void onApproved(DocumentApproved event) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
    // Under default synchronous dispatch, normally reads the caller's context.
}
~~~

Asynchronous version:

~~~java
@Async("backgroundExecutor")
@EventListener
public void onApproved(DocumentApproved event) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
    // Do not assume the caller's authentication exists on the worker thread.
}
~~~

These are snippets inside a Spring-managed bean; imports and the `backgroundExecutor` bean are required. `@EnableAsync` must be enabled. Spring handles `@Async` via a proxy/interceptor in default mode, so direct self-invocation `this.onApproved(...)` is not a valid test of async execution.

When dispatching events through the default `SimpleApplicationEventMulticaster`, the call to the async proxy normally occurs right on the event-publishing thread; the proxy submits the task to the executor, and a wrapped executor can capture the context on that thread. If the application **also configures the multicaster to run on another executor**, the submitting thread may no longer be the request thread. Therefore, you must identify **which thread actually submits the task**, not just where `publishEvent` is called.

### Typical Failures

- `getAuthentication()` returns `null`, and calling `getName()` directly throws a `NullPointerException`.
- The listener invokes a secured method and is denied because the worker's `SecurityContext` lacks a user/authorities.
- The next task inherits the previous task's principal if code manually sets context without cleaning it up.
- Unit tests calling the listener method directly pass, whereas integration tests that publish a real event and run the executor fail.
- The event publisher has already logged out or their permissions changed, yet the task holds information from submission time; a separate authorization policy must be considered.

## 3. DelegatingSecurityContextAsyncTaskExecutor Propagates Context Per Task

Spring Security provides `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`. It implements `AsyncTaskExecutor` and wraps `Runnable` or `Callable` to set up `SecurityContext` for the execution duration on the worker.

~~~text
submitter thread:
  SecurityContextHolder = alice
            |
            v
  DelegatingSecurityContextAsyncTaskExecutor.submit(task)
            |
            +-- capture the submitting thread's context
            +-- wrap task with security context
            v
pool worker:
  install captured context -> listener sees alice
  try { process event; }
  finally { clear/restore previous context; }
~~~

In the single-argument constructor, the context is captured **when the task is submitted**, not snapshotted once for the bean's lifetime. The two-argument constructor takes a fixed `SecurityContext`: every task can run under that fixed identity. Use the fixed-context case only when the business logic genuinely requires an intentionally privileged service identity; never capture an admin context at startup and accidentally apply it to all users.

Configuration for a Spring MVC/imperative application:

~~~java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean("notificationsPool")
    ThreadPoolTaskExecutor notificationsPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("notifications-");
        return pool;
    }

    @Bean("secureNotifications")
    AsyncTaskExecutor secureNotifications(
            @Qualifier("notificationsPool")
            ThreadPoolTaskExecutor delegate) {
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
~~~

This is a configuration **snippet**; it requires importing `@Configuration`, `@EnableAsync`, `@Bean`, `@Qualifier`, `ThreadPoolTaskExecutor`, `AsyncTaskExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`.

The decisive step in the listener is choosing **the right executor**:

~~~java
@Component
class NotificationListener {

    @Async("secureNotifications")
    @EventListener
    public void onApproved(DocumentApproved event) {
        Authentication auth = SecurityContextHolder.getContext()
            .getAuthentication();

        if (auth == null) {
            // Handle missing principal according to the business contract.
            return;
        }

        notificationService.sendFor(event.documentId(), auth.getName());
    }
}
~~~

This is a snippet requiring `DocumentApproved`, `notificationService`, and the corresponding imports. **Do not merely check `auth.isAuthenticated()` and assume it is always a real user**: depending on configuration, `AnonymousAuthenticationToken` may still be marked authenticated. When permissions matter, use the system's formal authorization policy and distinguish anonymous authentication.

**Note:** declaring the `secureNotifications` bean does not automatically make all `@Async` methods use it. You need `@Async("secureNotifications")` or an intentionally configured default async executor. A wrong bean name can cause the task to run on a different executor or fail at runtime.

## 4. Practical Test: Plain Executor vs. Security-Delegating Executor

The example below is a Spring Context test suite running on Java 17+, Spring Framework 6.2, and Spring Security 6.4. It deliberately uses **two separate thread pools** to contrast no-propagation with context propagation. No HTTP server or database access is needed, as the focus is event dispatch, the async proxy, and thread-local security context.

Verified scenarios:

1. The event-publishing thread has user `alice`; the plain executor does not automatically have that user.
2. The wrapped executor receives `alice`'s `SecurityContext` at submission time.
3. After switching to user `bob`, the wrapped executor receives `bob`.
4. When the publishing thread clears its context, the next task does not reuse principal `bob`.

### 4.1. Gradle Dependencies

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.security:spring-security-core:6.4.3'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If the project uses Spring Boot, prefer the Framework and Security versions managed by Boot. Do not mix incompatible BOMs. The test uses `spring-security-core` to work with `SecurityContextHolder` and the executor wrapper without needing to build a security filter chain.

### 4.2. src/test/java/example/events/SecurityContextAsyncEventTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SecurityContextAsyncEventTest.Config.class)
class SecurityContextAsyncEventTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Listener observer;

    @BeforeEach
    void reset() {
        SecurityContextHolder.clearContext();
        observer.clear();
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void ordinaryPoolLosesCallerButSecuredPoolPropagates()
            throws Exception {
        login("alice");
        publisher.publishEvent(new PlainEvent("P-1"));
        publisher.publishEvent(new SecureEvent("S-1"));

        Seen plain = observer.takePlain();
        Seen secured = observer.takeSecured();

        assertEquals("P-1", plain.eventId());
        assertEquals("<none>", plain.user());
        assertTrue(plain.thread().startsWith("plain-"));

        assertEquals("S-1", secured.eventId());
        assertEquals("alice", secured.user());
        assertTrue(secured.thread().startsWith("secure-"));
    }

    @Test
    void contextDoesNotLeakToTheNextTask() throws Exception {
        login("bob");
        publisher.publishEvent(new SecureEvent("S-2"));
        assertEquals("bob", observer.takeSecured().user());

        SecurityContextHolder.clearContext();
        publisher.publishEvent(new SecureEvent("S-3"));
        Seen second = observer.takeSecured();

        assertEquals("S-3", second.eventId());
        assertEquals("<none>", second.user());
    }

    private static void login(String name) {
        Authentication auth = new UsernamePasswordAuthenticationToken(
            name, "not-a-password",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    record PlainEvent(String id) {}
    record SecureEvent(String id) {}
    record Seen(String eventId, String user, String thread) {}

    static class Listener {
        private final BlockingQueue<Seen> plain =
            new LinkedBlockingQueue<>();
        private final BlockingQueue<Seen> secured =
            new LinkedBlockingQueue<>();

        @Async("plainExecutor")
        @EventListener
        public void onPlain(PlainEvent event) {
            plain.offer(observe(event.id()));
        }

        @Async("secureExecutor")
        @EventListener
        public void onSecure(SecureEvent event) {
            secured.offer(observe(event.id()));
        }

        private Seen observe(String id) {
            Authentication auth = SecurityContextHolder.getContext()
                .getAuthentication();
            return new Seen(
                id,
                auth == null ? "<none>" : auth.getName(),
                Thread.currentThread().getName()
            );
        }

        Seen takePlain() throws InterruptedException {
            Seen result = plain.poll(5, TimeUnit.SECONDS);
            assertNotNull(result, "plain listener did not finish");
            return result;
        }

        Seen takeSecured() throws InterruptedException {
            Seen result = secured.poll(5, TimeUnit.SECONDS);
            assertNotNull(result, "secure listener did not finish");
            return result;
        }

        void clear() {
            plain.clear();
            secured.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config {

        @Bean("plainExecutor")
        ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("plain-");
            return pool;
        }

        @Bean("securePool")
        ThreadPoolTaskExecutor securePool() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("secure-");
            return pool;
        }

        @Bean("secureExecutor")
        AsyncTaskExecutor secureExecutor(
                @Qualifier("securePool") ThreadPoolTaskExecutor pool) {
            return new DelegatingSecurityContextAsyncTaskExecutor(pool);
        }

        @Bean
        Listener listener() {
            return new Listener();
        }
    }
}
~~~

### 4.3. Running the Test and Reading Results

In a project with the Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.SecurityContextAsyncEventTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.SecurityContextAsyncEventTest"
~~~

The verification lies in the assertions, not in lines printed by Gradle to stdout:

| Scenario | Executor | Expected principal in listener |
| --- | --- | --- |
| `PlainEvent("P-1")` after logging in alice | Plain pool | `<none>` |
| `SecureEvent("S-1")` after logging in alice | Delegating wrapper | `alice` |
| `SecureEvent("S-2")` after logging in bob | Delegating wrapper | `bob` |
| `SecureEvent("S-3")` after `clearContext` | Delegating wrapper | `<none>` |

**Why does the test use `BlockingQueue` and a timeout?** `@Async` means work may finish after the publisher has already returned. `poll(5, TimeUnit.SECONDS)` lets the test wait with a bounded timeout instead of calling `Thread.sleep(...)` and hoping the scheduler finishes. If a task fails or the executor is inactive, the assertion fails rather than hanging forever.

**Why separate the two pools?** To prevent one executor from accidentally applying context propagation to both branches. Each pool has one worker in this example, allowing us to observe `SecurityContext` cleanup/restoration behavior across tasks.

**Do not apply this mechanically to Spring WebFlux:** this test assumes the thread-local `SecurityContextHolder` of imperative Spring Security. In reactive applications, identity is normally stored in the Reactor Context, which requires a different mechanism.

## 5. Choosing Between Propagating Context or Passing Actor Data in the Event

Depending on business requirements, the handling differs.

### Tasks That Need to Run Under the User's Identity

For example, a listener calls a service with method security and needs to evaluate permissions based on the caller at submission time. Choose a wrapped executor, propagate the context, and test the authorization policy. Note that **permissions may change** after the task is scheduled. For sensitive or long-running operations, consider re-checking permissions at execution time.

### Tasks That Only Need to Know Who Performed the Action

For simple email/audit notifications, it is usually sufficient to store a verified actor identifier in the payload:

~~~java
public record DocumentApproved(
    String documentId,
    String actorId,
    String correlationId
) {}
~~~

This is a standalone Java record. The application service takes `actorId` from a trusted `Authentication` source when accepting the command; do not trust an arbitrary client-supplied `actorId` as proof of authentication. The consumer uses the actor ID for audit or notification mapping, while operations requiring authorization still apply security policies.

### Long-Running Tasks or Tasks Delivered via a Broker

Never serialize `SecurityContext` or credentials into Kafka/RabbitMQ/outbox/HTTP. Use a minimal event payload, schema version, correlation ID, and a service identity with appropriate permissions. Because `SecurityContext` is in-JVM runtime state, it does not survive restarts and is not a safe capability to pass across process boundaries.

| Requirement | Preferred design | What must be verified |
| --- | --- | --- |
| Short caller-scoped async task | `DelegatingSecurityContextAsyncTaskExecutor` | Captured from the right submit thread; cleanup |
| Actor audit | Immutable `actorId` in the event | `actorId` must come from a trusted `Authentication` |
| Scheduled/long-running retry job | Service identity, authenticate/authorize at execution time | Least privilege, revoked permissions, idempotency |
| Cross-service messaging | Independent integration event | Never embed raw `SecurityContext`/tokens |
| Async listener not needing security | Do not propagate context | Avoid propagating unnecessary privileges |

## 6. Why Is MODE_INHERITABLETHREADLOCAL Usually Unsuitable?

Spring Security supports `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` so newly created threads can inherit the creating thread's context. However, thread pools **reuse worker threads across multiple requests**; a context inherited at thread creation time does not accurately reflect the user submitting subsequent tasks. Switching the global strategy to inheritable can cause missing-context bugs or identity leaks.

Therefore, do not turn on `MODE_INHERITABLETHREADLOCAL` globally just to "fix `@Async`". Propagating context **per task** and ensuring cleanup is the proper approach.

Code that sets context manually without cleaning up:

~~~java
// WRONG if running in a thread pool:
SecurityContextHolder.setContext(captured);
process(event);
// Missing finally; the worker may retain the previous task's context.
~~~

When manual manipulation really is necessary, use `try/finally` to restore the previous context or clear it per policy. Spring Security already provides `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, and executor wrappers so you do not have to write this logic yourself.

### SecurityContext Can Be Mutable

A wrapper capturing `SecurityContext` does not necessarily create an immutable deep copy. If the application continues mutating the captured `Authentication` or context object, race conditions or unpredictable behavior can occur. Do not mutate shared context after submission; for auditing purposes, use an immutable actor ID and correlation ID. For especially sensitive tasks, re-verify permissions at execution time rather than trusting that submission-time permissions still hold.

## 7. SecurityContext Is Not a Transaction, MDC, or Reactor Context

The three context types have distinct meanings:

1. **SecurityContext**: `Authentication`/authorities for authentication and authorization.
2. **Transaction context**: DB transaction resources, commit/rollback, typically thread-bound in JDBC.
3. **Logging/tracing context**: correlation ID, MDC, observation context, which can be propagated via Micrometer context propagation.

An async task may receive a propagated `SecurityContext` yet **not participate in the original JDBC transaction**. If an event is published inside `@Transactional`, the listener might run before commit and read stale DB state. If business logic requires processing only after commit, consider `@TransactionalEventListener(phase = AFTER_COMMIT)` and then design the appropriate executor/propagation; if events must never be lost on crash, an outbox or durable registry is required.

~~~text
publisher thread:
  [SecurityContext = alice] [DB TX-1]
     -> UPDATE data
     -> publish event
     -> COMMIT or ROLLBACK

async listener worker:
  [SecurityContext = alice, if propagated by wrapper]
  [DB TX-1 is not automatically propagated]
     -> open a new transaction if separate DB operations are needed
~~~

With an `AFTER_COMMIT` listener, task submission may occur during the transaction completion callback rather than precisely when the application calls `publishEvent`. If `SecurityContext` has already been cleared by then, a wrapper cannot recreate the old `Authentication`. You should test the flow end-to-end, especially when the multicaster also uses an executor.

### Spring Framework ContextPropagatingTaskDecorator

Spring Framework provides `ContextPropagatingTaskDecorator`, which works with Micrometer to propagate context for tracing/MDC. **Do not conclude that `SecurityContext` is propagated as well** unless the application actually integrates appropriate context accessors and has been tested. When propagation is needed for servlet/imperative Spring Security, `DelegatingSecurityContext*` wrappers are the direct and transparent choice.

### Reactor/WebFlux SecurityContext

In Spring WebFlux, reactive security normally uses `ReactiveSecurityContextHolder` backed by **Reactor subscriber Context**, rather than relying solely on the thread-local `SecurityContextHolder`.

~~~java
// Reactive snippet, requires a Reactor subscription carrying a security context:
Mono<String> principalName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

This snippet requires the corresponding imports. If no context is present, the `Mono` may emit no value. Wrapping an imperative executor with `DelegatingSecurityContextAsyncTaskExecutor` **does not automatically ensure** Reactor subscriber Context transfer. When working with WebFlux/Reactive, keep the flow within the Reactor chain, use `ReactiveSecurityContextHolder`, and design explicit handling when crossing to external threads/tasks/messages.

## 8. Common Mistakes and How to Test

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `@Async @EventListener` immediately calls `getAuthentication().getName()` | Possible NPE | Check auth for null; use the right executor when actually needed |
| A wrapped executor bean exists, but `@Async` does not select it | Task still runs on a non-propagating executor | Use `@Async("secureExecutor")` or configure the async default |
| Pinning a privileged `SecurityContext` on every task | Runs under the wrong privileges | Use per-task capture or an intentional service identity |
| Enabling `MODE_INHERITABLETHREADLOCAL` for a pool | Wrong or stale context on reused threads | Wrap per task and clean up in `finally` |
| Calling `setContext` manually without clearing | Identity leaks to other jobs | `try/finally` or `DelegatingSecurityContext` wrapper |
| Treating `actorId` in an event as proof of authentication | Spoofed privileges | Authorize based on verified identity |
| Assuming `SecurityContext` pulls the transaction along | Reads wrong DB point; outside original TX | Transaction phase / new transaction; test commit behavior |
| Async listener throws an error and publisher expects to catch it | Exception does not propagate like a sync listener | `AsyncUncaughtExceptionHandler`, logs, metrics, retries |
| Publishing before commit and using email/API as a side effect | May fire even when DB rolls back | Post-commit or transactional outbox |
| Asserting in tests immediately after publish | Race condition | `BlockingQueue`/latch with timeout |

Additional production tests: users A and B submitting closely together; listener throwing exceptions; executor rejecting tasks due to a full queue; context without `Authentication`; caller logging out; permissions revoked; custom multicaster using an executor; service with `@PreAuthorize`; after-commit listeners; and WebFlux if applicable. In particular, measure `task submitted`, `task completed`, `task failed`, and queue saturation to detect tasks not running.

With `@Async` methods returning `void`, errors can be handled by `AsyncUncaughtExceptionHandler` or default logging. Do not infer that `publishEvent()` waits for all async listeners or that events are guaranteed to be delivered. If durable delivery is required, design appropriate retry/idempotency and outbox mechanisms instead of treating `SecurityContext` propagation as a form of message delivery.

## 9. Adoption Checklist

- Confirmed the listener is `@Async`, actually invoked via a Spring proxy, and `@EnableAsync` is active.
- Selected a dedicated executor for the listener; the name in `@Async("...")` matches the bean using propagation.
- Verified whether the thread **submitting the task** actually holds a `SecurityContext`, especially with a custom multicaster.
- No unintended fixed privileged context is retained; least privilege is applied.
- Workers handle absent `Authentication` and anonymous authentication.
- `MODE_INHERITABLETHREADLOCAL` is not used as the default pool solution.
- Tokens, credentials, or `SecurityContext` are not serialized into domain/integration events.
- `SecurityContext` is not confused with transactions or Reactor Context.
- Real async tests exist with timeouts, cross-task context cleanup, and error paths.
- Clear policies exist for post-commit events, long-running tasks, retries, and permission changes.

## 10. Self-Check Questions

**Question 1:** Why does a synchronous `@EventListener` see the user, whereas `@Async @EventListener` might see `null`?

Because the asynchronous invocation runs on a different thread, where `SecurityContextHolder` under the default `MODE_THREADLOCAL` does not hold the caller's context.

**Question 2:** How does the single-argument constructor of `DelegatingSecurityContextAsyncTaskExecutor` differ from the fixed-context constructor?

The single-argument constructor captures `SecurityContext` from the submitting thread per task; the fixed-context constructor uses a specified context for tasks. Choose based on purpose and privilege boundaries.

**Question 3:** If only `actorId` is placed in the event payload, does the listener have a `SecurityContext`?

No. Actor ID serves as business/audit data; it does not automatically install a trusted `Authentication` into `SecurityContextHolder`.

**Question 4:** Should you switch to `MODE_INHERITABLETHREADLOCAL` when using a thread pool?

Not by default. Worker threads are reused and can retain context for the wrong user; use a per-task wrapper and cleanup instead.

**Question 5:** Does `SecurityContext` propagation put the async task in the same JDBC transaction as the publisher?

No. Transactions and `SecurityContext` are separate boundaries. A new transaction or after-commit/outbox handling is needed depending on business logic.

**Question 6:** Should Spring WebFlux read the thread-local `SecurityContextHolder` like a servlet application?

Not by default. Reactive security normally resides in the Reactor Context; use `ReactiveSecurityContextHolder` and preserve the subscriber context in the pipeline.

**Remember:** in async application events, identity does not automatically follow into the thread pool. If a listener genuinely needs the caller's privileges, propagate context at the right time with `DelegatingSecurityContextAsyncTaskExecutor`, restrict privileges, clean up context after every task, and test with a real executor. For auditing or long-running tasks, passing minimal actor data and authorizing independently is usually safer and more resilient.

## References

- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security – DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.3/api/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html)
- [Spring Framework – Task Execution and @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework – Asynchronous Application Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework – Observability and Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
