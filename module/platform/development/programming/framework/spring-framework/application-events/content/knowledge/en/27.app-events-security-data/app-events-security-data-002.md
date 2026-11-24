# Access Control When Listeners Process Events in Spring Application Events

## 1. Core Question: Does Receiving an Event Mean Being Authorized to Process It?

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` is a mechanism for publishing events **inside the application**. An `@EventListener` is selected by Spring based on the event type and can execute business logic. However, **the ability to receive an event is not permission to access the data, resources, or operations that the listener is about to perform**.

For example: after placing an order, the system publishes `OrderPlaced`. Listeners may write an audit log, query the buyer's profile, send an email, update a credit limit, or start a refund workflow. These side effects have **different privilege levels**. Spring delivering an event to a listener does not automatically verify that the current user is allowed to call an email-sending API or access another tenant's order.

Four layers must be distinguished:

1. **Producer**: who is permitted to perform the business action that causes the event to appear?
2. **Event**: does the data match the schema, is it trustworthy, and does it carry enough information to verify provenance?
3. **Listener**: under which identity/security context is the processing running?
4. **Service performing the side effect**: is reading/writing that specific resource allowed at **execution time**?

An important rule:

> **An event states what happened; it does not automatically grant recipients permission to perform every related action.**

With synchronous listeners running directly on the request thread, `SecurityContextHolder` may still hold the user's `Authentication`. However, when moving to `@Async`, an executor, a retry job, or after-commit processing, permissions and identity may be absent or may have changed. Therefore, a proper design needs a combination of **Spring Security method authorization**, safe **SecurityContext** management, and appropriate **business authorization**.

## 2. Distinguishing Authentication, Authorization, and Event Filtering

| Concept | Question Answered | Example Mechanism |
| --- | --- | --- |
| **Authentication** | Who is the caller/worker? | `Authentication` in `SecurityContextHolder`, verified JWT, service principal. |
| **Authorization** | Is the actor allowed to perform the specific operation? | `@PreAuthorize`, `AuthorizationManager`, domain/service-layer policy. |
| **Event type matching** | Is the listener subscribed to this event type? | `@EventListener`, `ApplicationListener<E>`, and multicaster. |
| **Event condition** | Does the payload satisfy a business filtering rule? | `@EventListener(condition = "...")`. |
| **Data/tenant isolation** | Is the actor allowed to view/modify the exact record within their scope? | Owner/tenant/object permission checks, queries with tenant constraints. |
| **Message authenticity** | Which source did the event come from, and was it tampered with or forged? | Publisher identity, mTLS/ACL, signature verification across brokers. |

**`@EventListener(condition)` is not an authorization mechanism.** It can filter by event data, such as `status == 'PAID'`, but if the data comes from an untrusted source, the condition only indicates that the data matches the expression. It does not prove that the publisher owns the order or holds `ROLE_ADMIN`.

An error-prone example:

~~~java
// Do NOT use claimedRole in the payload as proof of authorization.
@EventListener(condition = "#p0.claimedRole() == 'ADMIN'")
public void grantRefund(OrderEvent event) {
    // sensitive side effect
}
~~~

*This is an illustrative anti-pattern; `OrderEvent` is a hypothetical type. Do not use the snippet above to protect refund operations.*

An event object can contain `claimedRole="ADMIN"` sent by the caller, no different from any ordinary data string. Privileges are meaningful only when they originate from an **authenticated security context** or a policy/claim verified at the appropriate trust boundary.

## 3. Spring's Default Behavior: Listeners Usually Run on the Same Thread

Under the default behavior of `SimpleApplicationEventMulticaster`, listeners are invoked synchronously on the thread that publishes the event:

~~~text
HTTP request thread
  |
  | SecurityContextHolder -> Authentication("alice", ORDER_NOTIFY)
  v
OrderController -> OrderService.placeOrder()
  |
  | publishEvent(OrderPlaced)
  v
SimpleApplicationEventMulticaster
  |
  v
@EventListener OrderListener.onOrderPlaced()
  |
  | same thread, same request SecurityContextHolder if still valid
  v
@PreAuthorize on protected service
  |
  +-- granted -> execute side effect
  +-- denied  -> throw error, method body does not run
~~~

Characteristics:

- When a listener runs on the **same thread** and the request's authentication scope is still open, `SecurityContextHolder.getContext().getAuthentication()` usually returns the same principal/authorities that the request was authenticated with.
- That **does not mean every event has a logged-in user**. Startup events, schedulers, batch jobs, CLIs, and message consumers may run outside an HTTP security filter chain.
- An event invoked solely from an internal component also **does not automatically guarantee** that all data and business permissions have been authorized.
- When a synchronous listener throws an uncaught exception, the exception can propagate back to the `publishEvent(...)` call, affecting the calling service/transaction.
- If multiple listeners receive the event, one listener may have already performed a side effect before another listener is denied. **An authorization failure in one listener does not turn the entire fan-out into an atomic distributed transaction.**

Spring does not add a generic `LISTEN_EVENT` permission for every `@EventListener`. To protect actions, authorization checks must be placed where the sensitive service, repository, or API is invoked.

## 4. Where Does Spring Security Manage Permissions?

### 4.1. SecurityContextHolder and Authentication

In common servlet/imperative applications, Spring Security manages a `SecurityContext` containing an `Authentication`, typically bound to the current thread:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

*This is an integration Java snippet. You need to import `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`.*

An `Authentication` may include a principal, authorities, authentication status, and provider-specific details. You should not infer permissions solely from `getName()`, an email, or an `actorId` string inside an event.

If there is no authentication or the authenticated actor lacks the required permissions, the security policy must **deny or transition to a controlled service-principal model**, rather than assigning a privileged user to the thread out of convenience.

### 4.2. Enabling Method Security

In modern Spring Security, use:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

*Illustrative configuration snippet: requires importing `org.springframework.context.annotation.Configuration` and `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`.*

`@EnableMethodSecurity` activates method-level infrastructure such as `@PreAuthorize`. **Merely adding `spring-boot-starter-security` does not mean every method automatically gets `@PreAuthorize`.** Methods not protected by an appropriate annotation/policy can still be called.

Example protecting a notification operation:

~~~java
@Service
class NotificationService {
    @PreAuthorize("hasAuthority('ORDER_NOTIFY')")
    public void notifyOrder(OrderPlaced event) {
        // side effect is only executed after checking authority
    }
}
~~~

*Illustrative code snippet: requires `@Service`, `@PreAuthorize`, and the `OrderPlaced` type.*

`hasAuthority('ORDER_NOTIFY')` requires the **exact authority string `ORDER_NOTIFY`**. If you use `hasRole('OPS')`, Spring Security by default interprets it as an authority prefixed with `ROLE_OPS`; do not confuse the two expressions.

### 4.3. Checking via AOP Proxy, Not Just Writing Annotations

Spring method security uses AOP by default. When an external bean calls a protected method through a **Spring proxy**, the interceptor checks permissions before the method body executes.

Conversely, if the same class calls `this.securedMethod()`, self-invocation can **bypass the proxy**. Therefore, separate them:

~~~text
OrderEventListener (bean)
    |
    | calls via Spring-injected dependency
    v
SecuredNotificationService (proxy)
    |
    | @PreAuthorize/AuthorizationManager
    v
Side effect
~~~

Good practice: keep the listener as a lightweight coordinator and call a separate **protected application service**. This also protects the service if tomorrow it is invoked from a REST controller, CLI, scheduler, or another listener.

Placing `@PreAuthorize` directly on a listener method can also work when the invocation truly goes through a Spring-managed proxy, but you must test proxy mode, method visibility, and `@EventListener` registration. Placing authorization on the service performing the side effect makes the rule less dependent on dispatch details.

## 5. Protecting the Exact Data Object, Not Just Global Permissions

Having the `ORDER_NOTIFY` authority does not mean a staff member can send notifications for **every order of every tenant**.

A complete policy may require all of the following:

- The actor is authenticated and holds the minimum authority for the operation.
- The order exists and belongs to a tenant/organization the actor is authorized to serve.
- The actor is permitted to operate on the order's **current state**.
- The destination (email/SMS/payment endpoint) conforms to policy and is not taken from an untrusted payload.
- Every database access operation enforces tenant isolation, rather than checking only at the controller.

Illustrative example of object-level authorization inside a service:

~~~java
@PreAuthorize("hasAuthority('ORDER_NOTIFY')")
public void notifyOrder(OrderPlaced event) {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    // orderAccessPolicy looks up permission for the real orderId from trusted data.
    if (!orderAccessPolicy.canNotify(auth, event.orderId())) {
        throw new AccessDeniedException("Not allowed to notify this order");
    }

    // Execute side effect after both authority and object policy pass.
    notificationGateway.sendForOrder(event.orderId());
}
~~~

*This is an illustrative integration snippet; `orderAccessPolicy` and `notificationGateway` are business dependencies you must define yourself. Requires importing `Authentication` and `AccessDeniedException`.*

Do not implement a "tenant check" by comparing two strings **both taken from an unverified event**; that is not an authorization check. The policy must check against the authenticated identity and data stored/retrieved from a trusted source.

In multi-tenant systems, combine domain checks with tenant-scoped query conditions instead of relying on a single logic layer inside a listener. If using database row-level security, clearly define how the database identity/tenant session and connection lifecycle are set.

## 6. Runnable Java 17+ Example: An Event with a Forged Role Still Fails @PreAuthorize

This example uses **Spring Boot 3.5.16**, Java 17+, and Maven. The application does not start a web server, allowing us to simulate two actors inside `main` without HTTP login:

- `alice` is assigned the trusted authority `ORDER_NOTIFY` → allowed to invoke the protected service.
- `bob` only has the authority `ORDER_VIEW` → denied.
- **Both events declare `claimedRole="ADMIN"`**. This field is just event data and does not participate in authorization decisions.

The key point is that `@EventListener` does not grant permissions itself; it calls a service bean protected by Spring Security with `@PreAuthorize`.

### 6.1. Structure

~~~text
event-access-demo/
├── pom.xml
└── src/main/java/example/EventAuthorizationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>event-access-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

`src/main/java/example/EventAuthorizationDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class EventAuthorizationDemo {

    // claimedRole is received data, NOT a verified authority.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String actorId,
            String claimedRole) {
    }

    // Spring bean: method security creates a proxy for the protected method.
    @Bean
    public SecuredNotificationService securedNotificationService() {
        return new SecuredNotificationService();
    }

    // Listener bean calls service via a Spring-injected dependency.
    @Bean
    public OrderListener orderListener(
            SecuredNotificationService securedNotificationService) {
        return new OrderListener(securedNotificationService);
    }

    public static class SecuredNotificationService {

        @PreAuthorize("hasAuthority('ORDER_NOTIFY')")
        public void sendNotification(OrderPlaced event) {
            System.out.println("SENT " + event.orderId());
        }
    }

    public static class OrderListener {

        private final SecuredNotificationService service;

        public OrderListener(SecuredNotificationService service) {
            this.service = service;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            // Do not trust event.claimedRole() to grant permissions.
            service.sendNotification(event);
        }
    }

    private static void publishAs(
            ApplicationEventPublisher publisher,
            String username,
            String authority,
            OrderPlaced event) {

        // Simulate an authenticated SecurityContext.
        // Production: authentication comes from a verified filter/token.
        Authentication auth =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "not-used",
                        AuthorityUtils.createAuthorityList(authority));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            publisher.publishEvent(event);
            System.out.println("ALLOWED " + username
                    + " " + event.orderId());
        } catch (AccessDeniedException denied) {
            System.out.println("DENIED " + username
                    + " " + event.orderId());
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(EventAuthorizationDemo.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.<String, Object>of(
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            publishAs(
                    context,
                    "alice",
                    "ORDER_NOTIFY",
                    new OrderPlaced(
                            "evt-1", "ORD-7", "alice", "ADMIN"));

            publishAs(
                    context,
                    "bob",
                    "ORDER_VIEW",
                    new OrderPlaced(
                            "evt-2", "ORD-8", "bob", "ADMIN"));
        }
    }
}
~~~

To run from the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

**Lines printed by the program on stdout upon successful startup**, excluding Maven's own logs:

~~~text
SENT ORD-7
ALLOWED alice ORD-7
DENIED bob ORD-8
~~~

### 6.2. Detailed Explanation

1. `@SpringBootApplication` creates the Spring context; `@EnableMethodSecurity` activates method authorization.
2. `SecuredNotificationService` is registered as a Spring bean; Spring Security can create an AOP proxy to intercept calls to `sendNotification(...)`.
3. `OrderListener` is registered as a bean, so `@EventListener` is registered. It **does not check** the `claimedRole` field in the payload itself.
4. `publishAs(...)` simulates the security context of two actors using `UsernamePasswordAuthenticationToken.authenticated(...)`. In real applications, **do not use this technique to turn client-supplied data into a logged-in user**; authentication must be verified at the trust boundary.
5. When `alice` calls `publishEvent(...)`, the listener runs synchronously on the same thread and sees an authentication with the `ORDER_NOTIFY` authority. The service call is permitted, so `SENT ORD-7` appears and the publisher prints `ALLOWED alice ORD-7`.
6. When `bob` does the same, his authority is only `ORDER_VIEW`. The `@PreAuthorize` interceptor denies the call **before the method body runs**, so there is **no** `SENT ORD-8` line. `AccessDeniedException` is caught on the publisher thread in the synchronous setup, printing `DENIED bob ORD-8`.
7. Both events carry `claimedRole="ADMIN"`, yet that field does not alter the `Authentication` or authorities seen by the security policy.
8. `finally` clears `SecurityContextHolder` after each turn so context does not leak into the next publish when the thread is reused.

This is an example **illustrating the mechanism**, not a login workflow. Programmatically constructing an authenticated token like this is only appropriate in demos or controlled tests. Production must authenticate requests/messages using filters, an identity provider, a service account, or an approved system mechanism.

**Scope note:** the demo checks a global authority. In a real system, you must add object-level authorization with `orderId`, tenant, state, and data rules as described in section 5. It also provides no durability or transactional delivery guarantees.

## 7. Why Not Just Put @PreAuthorize Directly on @EventListener?

You may encounter this style:

~~~java
@EventListener
@PreAuthorize("hasAuthority('ORDER_NOTIFY')")
public void onOrderPlaced(OrderPlaced event) {
    // Receives event and performs side effect directly in the method.
}
~~~

*This is an illustrative code snippet, not a standalone program.*

This approach **can** be intercepted by the method-security interceptor when the listener bean/proxy is registered and the method is invoked properly through the proxy. However, there are risks to check:

- Both event listener infrastructure and method security rely on proxy/adapter mechanisms; classes, interfaces, method visibility, `final`/`private` methods, and bean post-processing order can cause the configuration not to work as intended.
- If other business code calls an internal helper via `this.someSecuredMethod()`, self-invocation can bypass the security proxy.
- Permissions live solely on the listener, while the same side effect might be performed from a REST endpoint or another job that does not go through the listener.
- Tests that merely call `listener.onOrderPlaced(...)` directly do not accurately reproduce event dispatch/proxy behavior.

**Practical recommendation:** the listener should pass event information to a **protected application service**, where permissions are attached to the sensitive operation itself. Test through `ApplicationContext` and observe actual data state to verify that denial blocks the side effect.

Do not assume putting it directly on the listener "never works"; the point to evaluate is **whether the actual call passes through the proxy applying the advisor**.

## 8. @Async and Executors: Does SecurityContext Propagate Automatically?

Under the default strategy, `SecurityContextHolder` uses a thread-bound context. If you offload a listener to a thread pool, the value present on the publisher thread **does not automatically travel to the worker**:

~~~text
Publisher request thread                    Executor worker
------------------------                    ---------------------------
Authentication=alice
    |
    | publishEvent(OrderPlaced)
    |       |
    |       +-- submit task ----------------> @EventListener(...)
    |                                        SecurityContextHolder:
    |                                        - may have no Authentication
    |                                        - or receive a stale context if cleanup failed
    |
    +-- request ends
~~~

Two common ways to switch to async:

1. Configure `SimpleApplicationEventMulticaster` to use a `TaskExecutor`.
2. Annotate a listener method with `@Async` and enable `@EnableAsync`.

**The two executors may be different.** If a listener uses `@Async("emailExecutor")` while propagation is configured on the multicaster's executor named `eventExecutor`, the context can be lost at the `emailExecutor` hop.

Spring Security provides wrappers such as:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextAsyncTaskExecutor`.
- `DelegatingSecurityContextExecutorService` and related variants.

These wrappers set up the `SecurityContext` when the task runs and clean up or restore the appropriate state after the task finishes. You must choose between **capturing the context at submission time** or using a **fixed service identity** according to business requirements.

### 8.1. Illustrative Executor Configuration with SecurityContext Propagation

~~~java
@Bean(name = "securedEventExecutor")
AsyncTaskExecutor securedEventExecutor() {
    ThreadPoolTaskExecutor delegate =
            new ThreadPoolTaskExecutor();
    delegate.setCorePoolSize(2);
    delegate.setMaxPoolSize(4);
    delegate.setQueueCapacity(100);
    delegate.setThreadNamePrefix("secure-events-");
    delegate.initialize();

    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}

@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("securedEventExecutor") AsyncTaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

*This is an **illustrative integration configuration**, not standalone code: it requires importing `@Bean`, `@Qualifier`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, `DelegatingSecurityContextAsyncTaskExecutor`, `SimpleApplicationEventMulticaster`, and an appropriate configuration bean. In production, manage executor lifecycle/shutdown explicitly; when using Spring Boot, consider a container-managed executor bean rather than initializing one manually without a shutdown hook.*

With the constructor that does not pass a fixed `SecurityContext`, the wrapper uses the security context present when the task is submitted. With the constructor that passes a fixed context, tasks can run under the same identity on every submission — suitable for some background-service use cases, but **very dangerous if the service account is over-privileged**.

**Propagation passes a context snapshot/reference for execution; it does not re-authenticate the user.** If the account is locked or permissions change after the task is submitted, the captured context may become stale. Sensitive operations with long delays should have a policy to re-check permissions at processing time, not only at publish time.

### 8.2. Why Not Use InheritableThreadLocal for Pools?

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` is not a general solution for thread pools: it can inherit when creating a new thread, but executors typically reuse existing workers from previous requests. This creates risks of identity leakage, confused permissions, and hard-to-control cleanup. Prefer wrappers supported by Spring Security or explicit service-to-service authorization design.

### 8.3. Not All Errors Propagate Back to the Publisher

A denied synchronous listener can throw an exception back through `publishEvent(...)` as shown in the demo. With `@Async` listeners or a multicaster executor, authorization errors may appear only on the worker; the caller has already finished and does not receive the exception directly.

Use `AsyncUncaughtExceptionHandler` where appropriate for `@Async void`, and the multicaster's `ErrorHandler` for callbacks dispatched through the multicaster. If retry/durable processing is required, you need storage infrastructure, a queue/outbox/inbox, and idempotency; **never swallow `AccessDeniedException` and mark the event as successfully processed**.

## 9. Events Processed After Commit: When Are Permissions Evaluated?

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` allows a listener to react only after the corresponding transaction commits:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void whenOrderCommitted(OrderPlaced event) {
    securedNotificationService.sendNotification(event);
}
~~~

*This is an illustrative integration snippet with Spring transaction infrastructure; requires importing `@TransactionalEventListener` and `TransactionPhase`. Not a standalone runnable example.*

There are three distinct timelines:

1. **Authorization at request reception**: is the user allowed to place an order?
2. **Commit of business data**: were the order changes actually persisted successfully?
3. **Authorization at side-effect execution**: is the actor or service processing the event allowed to send notifications/access data?

With synchronous callbacks on the same thread, the security context may still be present at after-commit time. However, if execution is moved to an executor, delayed, or replayed after a process restart, you cannot assume the old request's `Authentication` still exists or remains valid.

Choose a clear policy:

- **User-delegated action**: authenticate the actor and check permissions on the resource; for delayed tasks, re-authentication or querying current permissions may be required.
- **System-owned business reaction**: operations the system itself must perform once a fact has occurred, such as sending a mandatory business receipt; run under a **least-privilege service principal**, rather than pretending it is the customer's session.
- **Audit attribution**: store the `actorId` verified at business creation to record who initiated the action, without using it as an authorization token for later tasks.

Do not infer that using `AFTER_COMMIT` guarantees event delivery after a crash. If the business cannot afford to lose events after commit, consider a **transactional outbox** and clear authorization policies on the consumer.

## 10. ActorId in Payloads and Trusted Data

Including `actorId`, `tenantId`, and `correlationId` in events helps with auditing/routing. However, their security meanings differ:

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        String actorId,
        String tenantId,
        String correlationId) {
}
~~~

*Illustrative record snippet; the record itself does not validate or verify any field.*

| Field | Proper Use | Must Not Be Inferred |
| --- | --- | --- |
| `eventId` | Identifies the occurrence, supports dedup and audit. | Having an event ID means having permission to perform side effects. |
| `actorId` | Attributes responsibility for who initiated the fact **if verified at the producer**. | An `actorId` string proves the current caller is that actor. |
| `tenantId` | Partitions data/routing after verifying the source. | A `tenantId` in the payload is enough to allow access to all tenant data. |
| `correlationId` | Links logs/events in the same workflow. | A correlation ID is an authentication/authorization token. |
| `claimedRole` | Merely a claim if present; provenance must be verified. | An `ADMIN` string in the payload is equivalent to a trusted authority. |

If an event arrives from an **external broker, partner, or another boundary**, you must authenticate the source (mTLS/ACL/authenticated producer), verify integrity where required by the design, validate the schema, and enforce permissions on operations against internal data. Do not use `@EventListener(condition)` as a tool to prove a trusted source.

If an event inside the same JVM originates from a service lacking input authorization checks, being "internal" does not make it safe automatically. **Protect the application where all call paths converge**, usually the application service modifying the resource.

## 11. User Permissions Differ from Background Service Permissions

A long-running workflow might start from a customer request and finish in a consumer running at midnight. There are three common architectural choices:

### 11.1. Continue Processing Under the User's Identity

Use when policy genuinely requires acting-on-behalf-of, with valid tokens/delegation and clear revocation behavior. Do not simply serialize the entire `Authentication` object into a database/JSON and reuse it indefinitely.

If delegation is needed for a long-running task, use a scoped, time-limited delegation/credential mechanism, store it securely, and re-check at execution time. The user's identity may be locked or permissions revoked between publish and consume.

### 11.2. Run with a Service Identity

Use when the event reflects a committed fact and the system must perform an internal task—for example, sending a confirmation email, updating a projection, or forwarding a message to another service. The service identity needs **least privilege**: only the permissions for that specific kind of operation, never `ROLE_ADMIN` by default.

Do not share one omnipotent service principal across all event listeners; if one listener has a bug or is compromised, the blast radius will be huge. Separate service identities by task type or trust boundary.

### 11.3. Deny Explicitly When Unauthorized

This is the default choice for actions lacking an appropriate policy. For retryable events, distinguish:

- **No valid authentication**: fail closed, record the error according to policy.
- **Authenticated but lacking authority**: access denied, do not execute side effect.
- **Permissions temporarily unknown due to policy service failure**: handle under a fail-safe policy, never turn a policy lookup error into an allow.
- **Actor permissions revoked**: business decision on whether to stop, route for approval, or let a system-owned workflow continue under a different principal, never silently bypassing permissions.

## 12. Immutability, Data Minimization, and Preventing Leaks

Payloads should contain only the data needed by listeners. Do not send entire `UserEntity`, `Authentication`, JWT, or sensitive details in events just so downstream "has enough context." Risks include:

- Mutable objects or JPA lazy proxies may change between publish and async processing.
- An event fanning out to many listeners multiplies the places where personal data appears.
- Logs/traces may record payloads and accidentally leak emails, phone numbers, access tokens, addresses, or payment information.
- Long-lived data in outboxes/brokers can violate retention rules or original processing purposes.
- Sensitive data can be accessed by under-privileged consumers if authorization exists only at the producer.

Recommendations:

1. Use **IDs, verified tenant keys, and minimal snapshots** instead of entity graphs.
2. Fetch additional data from repositories/services via protected APIs only when genuinely needed.
3. Encrypt/mask sensitive fields, and design retention and read permissions for event stores/brokers.
4. Never write tokens, passwords, or private keys into events, MDC, or tracing baggage.
5. Avoid treating "access to a message topic" as permission to read all payload data; topic ACLs and data-level authorization are two separate layers.

When sending emails from an event, only one authorized service should have access to recipient addresses and templates; metrics listeners may only need event type, event ID, and aggregate status.

## 13. Handling Authorization Errors, Transactions, and Side Effects

In synchronous listeners, `@PreAuthorize` rejects the service call before the side effect executes **inside the protected method**. However, note an important caveat: if another listener already ran earlier and modified data, an authorization failure in a later listener does not automatically undo all prior work.

Example:

~~~text
OrderPlaced
  |
  +--> AuditListener writes audit row     [may have already occurred]
  |
  +--> SecuredNotificationService
           |
           +--> @PreAuthorize fails       [does not send email]
  |
  +--> OtherListener                     [may not have run yet]
~~~

If an event is published inside an active `@Transactional` and synchronous listeners participate in the transaction, an unhandled exception can cause the transaction to roll back according to the transaction manager's rules. However, HTTP calls, emails, or messages sent outside the DB **do not automatically roll back** just because the database transaction rolled back.

If you want "once the order commits, send the notification without losing events," consider:

- Writing to a **transactional outbox** in the same transaction as the order change.
- A worker sending notifications from the outbox under a queue/retry policy.
- The consumer checking permissions under an appropriate service identity and protecting objects/tenants.
- Using `eventId`/idempotency keys to avoid duplicate side effects on retries.
- Classifying **authorization denied** errors as policy/tenant issues or configuration bugs to investigate, rather than retrying endlessly like transient network errors.

**Do not treat a `@TransactionalEventListener(AFTER_COMMIT)` listener as an absolute durability guarantee**: an in-memory callback does not provide durable delivery if the process crashes after commit.

## 14. @EventListener(condition), @PreAuthorize, and @TransactionalEventListener

These three annotations answer three different questions:

| Mechanism | Purpose | When Evaluated? | Cannot Replace |
| --- | --- | --- | --- |
| `@EventListener(condition=...)` | Filter matching event types/values | When event infrastructure prepares to invoke the handler | Authentication, object authorization. |
| `@PreAuthorize(...)` | Block method when actor is not allowed | Before method body via method-security proxy | Input validation or guaranteeing the event has committed. |
| `@TransactionalEventListener(phase=...)` | Bind listener to a transaction phase | According to transaction synchronization state | Access control, durable delivery, async security context. |

Example:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.status() == 'CONFIRMED'")
public void onConfirmed(OrderConfirmed event) {
    securedService.handleConfirmed(event);
}
~~~

*Illustrative integration snippet; `OrderConfirmed`/`securedService` are application-defined. Appropriate transaction synchronization must exist; Spring does not automatically grant permissions based on status `CONFIRMED`.*

Here `condition` selects matching events, `phase` chooses timing, and `securedService` must protect the operation itself. If an event has no transaction and `fallbackExecution=false` (the default), the listener may not run **even if the SpEL condition is true and the actor has permissions**.

## 15. Testing Real Permissions: Do Not Only Assert That the Listener Was Called

A security test suite for event listeners must cover **actors, events, method interceptors, data, and execution paths**.

### 15.1. Basic Tests

- Actor with `ORDER_NOTIFY` → protected service executes.
- Actor with only `ORDER_VIEW` → side effect is not performed.
- Event carrying `claimedRole="ADMIN"` while actor lacks permission → still denied.
- Missing `SecurityContext` → handled according to the system's fail-closed policy.
- Actor has global authority but wrong tenant/order owner → blocked by object policy.
- Permitted on one order but not another → cannot "piggyback" on an ID in the event.
- Service invoked from REST/scheduler/CLI → permission checks still hold.

### 15.2. Proxy and Configuration Tests

- `@EnableMethodSecurity` is enabled and beans are managed by Spring.
- The protected service is a dependency **injected from the context**, not an instance created manually with `new` outside Spring.
- Actual calls pass through the proxy: no self-invocation.
- For event dispatch, test via `context.publishEvent(...)` to verify listener registration.
- Include assertions verifying **no side effect occurred**, not just checking for an exception.
- If using `@PreAuthorize` with method parameter names, ensure compiler metadata is intact or use supported explicit binding.

### 15.3. Async, Retry, and Cleanup Tests

- Without propagation configured: workers must not automatically inherit user identity from the publisher.
- With valid propagation: workers receive the exact required context, never one from a previous request.
- Cleanup in `finally` ensures thread pools do not leak principals/tenants.
- Permissions revoked before job execution: policy re-check yields the right decision.
- Listener throws `AccessDeniedException` on a worker: the error is observed and never marked as a false success.
- If an event is redelivered, idempotency prevents duplicate notifications.
- If tenant access changes, the consumer does not send data to the old tenant from an unverified event.

Use `CountDownLatch`, bounded awaits, or suitable test utilities when testing async; do not rely on `Thread.sleep(100)` expecting a task to finish. With Spring Security testing, `@WithMockUser` is helpful for creating an `Authentication` in some integration tests, but verify that the context is established on the **thread actually running the code**.

### 15.4. Distinguishing "No Auth" vs "Insufficient Permissions" Errors

A system may throw `AuthenticationCredentialsNotFoundException` when authentication is missing, or `AccessDeniedException` when an actor has an `Authentication` but lacks permissions. Exception paths depend on security/method-interceptor configuration; do not assume all errors share the same class.

With async listeners, these errors may appear only on the executor. Tests must verify error handling and side-effect state, not just call `publisher.publishEvent(...)` and assert no exception was thrown.

## 16. Operations: Logs, Audits, Metrics, and Data Access Control

When processing events with sensitive data, security error observability needs useful fields without leaking secrets:

| Field | Usage |
| --- | --- |
| `eventType`, `eventId` | Trace events and handle duplicates. |
| `correlationId` | Correlate steps in the same workflow. |
| `principalId` or redacted subject | Who is authenticated at processing time, when policy permits logging. |
| Event's `actorId` | Who initiated the fact, **only when provenance has been verified**. |
| `resourceType` | Resource category (`ORDER`, `PAYMENT`, `PROFILE`). |
| `tenantId` | Useful for auditing, though privacy must be considered. |
| `authorizationOutcome` | `GRANTED` / `DENIED` / `ERROR`. |
| `policyName` / `action` | Which rule was applied. |

Do not log access tokens, passwords, raw JWTs, or full authority lists without justification and access controls. For metrics, unique values such as `eventId`, `userId`, and `correlationId` should not be used as low-cardinality tags; use action, event type, listener, and outcome.

A denial should be recorded sufficiently for investigation, but **must not disclose resource existence details or sensitive data** to unauthorized callers. Public error messages can be more generic than protected internal logs.

For brokers/outboxes, managing topic/queue access, consumer identities, credential secrets, and retention periods is part of event-driven security, not solely the listener's responsibility.

## 17. Common Mistakes

1. **Treating `@EventListener` as a security boundary.** Being invoked by Spring does not mean being authorized to read data, write to a DB, or send emails.
2. **Using `claimedRole` or `actorId` from the payload to grant permissions.** These fields can be forged and are valid only when provenance is verified.
3. **Thinking `@EventListener(condition)` is authorization.** It is only an event filter, not a principal and object-permission check.
4. **Protecting only REST controllers.** Listeners/schedulers/message consumers can invoke services outside HTTP paths; protect at the service boundary.
5. **Adding `@PreAuthorize` while forgetting `@EnableMethodSecurity`.** The annotation may not produce an interceptor.
6. **Self-invocation or creating beans with `new`.** Can bypass the proxy and skip method protection.
7. **Enabling `@Async` and assuming authentication follows the thread automatically.** `SecurityContextHolder` is typically thread-bound; propagation or a service identity is required.
8. **Using `MODE_INHERITABLETHREADLOCAL` for thread pools.** Not a reliable propagation mechanism in worker-reuse environments.
9. **Forgetting SecurityContext cleanup on workers.** Risks leaking identity/tenant across requests and tasks.
10. **Capturing user context and reusing it forever in long-lived jobs.** Permissions can change; expiration/revalidation or another principal is needed.
11. **Using an omnipotent service account to fix denied errors.** Violates least privilege and expands blast radius when a handler fails.
12. **Checking only global authority while ignoring object/tenant access.** An actor allowed to send emails may not be allowed to access another tenant's orders.
13. **Assuming `AFTER_COMMIT` automatically guarantees retries after a crash.** In-memory callbacks are not durable messaging.
14. **Catching `AccessDeniedException` and treating the event as successfully processed.** Side effects did not happen, yet the system may falsely mark success.
15. **Assuming exceptions in async listeners return to the publisher.** Dedicated error handlers/monitoring are required.
16. **Passing raw JWTs or `Authentication` objects via events.** Risks secret leaks, tight coupling, and stale permissions on replay.
17. **Using correlation IDs or event IDs as authorization keys.** They help trace/deduplicate, not prove identity.
18. **Checking permissions after side effects have already occurred.** Authorization must happen before sensitive operations.
19. **Forgetting to check alternative call paths to the same service.** Policy should sit where all callers converge.
20. **Ignoring side effects already completed in other listeners when one listener is denied.** Event fan-out does not automatically roll back sent emails/HTTP calls.

## 18. Production Design Checklist

Before shipping a listener with side effects to production, verify for yourself:

1. **Event contract**: what fact does the event describe, which fields are trusted, and who is the producer?
2. **Trust boundary**: is the event source in the same JVM or via broker/HTTP/partner? Is the source authenticated?
3. **Authorization boundary**: which service executes the side effect; do all call paths go through policy?
4. **Method security**: are `@EnableMethodSecurity`, proxies, and method accessibility tested?
5. **Object scope**: are tenant, owner, data sensitivity, and current state checked?
6. **Execution identity**: does processing run under a user or service principal? When is authentication/authorization re-evaluated?
7. **Thread hop**: which executor does the multicaster or `@Async` use, and are propagation/cleanup configured properly?
8. **Transaction**: publish before commit, after commit, or from an outbox? How far can exceptions roll back?
9. **Error semantics**: how are denials logged/metered/retried or reported as failures?
10. **Idempotency**: can retrying an event cause a side effect twice?
11. **Data minimization**: do payloads/logs contain tokens, PII, or mutable entities?
12. **Test matrix**: are allow, deny, no-auth, wrong tenant, async, replay, and startup/shutdown covered?

If an important item lacks an answer, that listener may work in a demo while still posing security risks in production.

## 19. Self-Check Exercises

**Question 1.** A listener receives `OrderPlaced` with `claimedRole="ADMIN"`. Can that field be used to skip permission checks?

**Answer:** No. It is event data, not a verified `Authentication`. Permissions must come from a trusted, verified security/policy mechanism.

**Question 2.** In the section 6 example, why didn't `bob` produce the line `SENT ORD-8`?

**Answer:** Even though Bob's event carried `claimedRole="ADMIN"`, his current authentication only had `ORDER_VIEW`. The service proxy applied `@PreAuthorize("hasAuthority('ORDER_NOTIFY')")` and blocked execution before the method body.

**Question 3.** Why is protecting controllers with HTTP authorization alone not enough for event listeners?

**Answer:** The same protected service can be called from events, schedulers, CLIs, or message consumers without going through the HTTP path. Protecting at the method/domain service boundary ensures all call paths obey policy.

**Question 4.** An `@Async` listener cannot read the request's `SecurityContextHolder`. Does this prove the user was not logged in?

**Answer:** No. Context is typically thread-bound; the worker might simply not have had authentication propagated. Valid propagation or a service-identity design is needed.

**Question 5.** Should a user's `Authentication` be copied into an event and stored in a broker for processing 3 days later?

**Answer:** Not as a safe default. Credentials/authorities can expire, change, or leak. Store minimal audit attribution and choose an appropriate delegation/revalidation policy or service principal.

**Question 6.** Does `@TransactionalEventListener(AFTER_COMMIT)` automatically grant permissions to the handler method?

**Answer:** No. It defines a transaction timing milestone; authorization must be checked independently.

**Question 7.** An actor has the notification-sending authority, but the order belongs to another tenant. Should it pass simply because `hasAuthority('ORDER_NOTIFY')` is true?

**Answer:** No. Object/tenant-level access control verified against trusted data is required.

**Question 8.** A synchronous listener throws `AccessDeniedException` after another listener already called a payment API. Does the exception automatically revert the HTTP side effect?

**Answer:** No. External non-DB side effects generally do not roll back automatically. Appropriate transaction boundaries and compensation/idempotency must be designed.

**Question 9.** Why is `SecurityContextHolder.clearContext()` in `finally` important?

**Answer:** Threads can be reused; without cleanup, the previous request's principal/authorities can leak into subsequent processing.

**Question 10.** Why should method security be tested through the Spring context/proxy instead of only calling the Java method directly?

**Answer:** The `@PreAuthorize` interceptor operates via an AOP proxy. Direct calls on an object created with `new` or self-invocation can bypass this check layer.

## References

- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager`, proxies, and parameter-based access control.
- [Spring Security Reference — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): thread-bound `SecurityContextHolder`, `DelegatingSecurityContextRunnable`, executor wrappers, and cleanup.
- [Spring Security Reference — SecurityContextHolder](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): how authentication is stored and retrieved.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, and async processing caveats.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT`, and `fallbackExecution`.
- [Spring Boot 3.5 Reference — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): application lifecycle used in the example; the demo app runs with `WebApplicationType.NONE`.
