# Internal Events Are Not a Security Boundary in Spring Framework Application Events

## 1. Core Statement and Learning Objectives

**Spring Application Events are an in-`ApplicationContext` notification mechanism, not an authentication, authorization, or data-isolation boundary.** Any bean can call `ApplicationEventPublisher.publishEvent(...)` to send an object; Spring selects and invokes matching listeners. A listener receiving an event **does not prove** that the user was authenticated, authorized for the target object, that the payload came from a trusted source, or that the data may be handed to that consumer.

This belongs to the **Security and Data** topic in the **Spring Framework Application Events** module. The lesson helps distinguish:

- **Notification of what happened:** `OrderPlaced`, `PaymentConfirmed`, or `CustomerUpdated` published from somewhere in the application.
- **Authorization decisions:** who is permitted to perform an action, on which aggregate, under which tenant, and with which data.
- **Source of truth:** authoritative database state, authorization policies, authenticated principals, and committed business state.
- **Tracking data:** `actorId`, `correlationId`, and `eventId` may serve as audit metadata, **never as authorization credentials**.
- **Execution boundaries:** sync, `@Async`, `@TransactionalEventListener`, and message brokers propagate context and errors differently, none replacing security controls.

An **internal system** can still ingest data from HTTP, webhooks, queues, jobs, plugins, callbacks, or code written by different teams. A seemingly "internal" payload may still originate from caller-controlled inputs. Moreover, code can publish events directly outside the intended workflow, tests can construct synthetic events, and a listener can run at a different time from when the original request was authenticated.

**Early takeaway:** never use "the event was published" as the sole condition for executing a privileged action. Design authorization at business boundaries and protect listeners according to the risk level of their side effects.

## 2. What Do Spring Application Events Actually Guarantee?

A typical publisher:

```java
@Service
public class OrderService {
    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void publishDemo() {
        events.publishEvent(new OrderPlaced("ORD-42"));
    }
}
```

This is an **illustrative integration snippet**, not a standalone compilable Java file. It requires Spring beans, `OrderPlaced`, and imports for `@Service` and `ApplicationEventPublisher`. Nothing in `publishEvent` indicates Spring has:
- Checked the request's JWT/session;
- Verified the caller owns `ORD-42`;
- Checked tenant permissions;
- Verified provenance of each field in the payload;
- Encrypted or filtered data according to consumer privileges;
- Guaranteed the listener runs after a successful commit;
- Persisted the event for recovery across JVM restarts;
- Prevented another bean from publishing a similar object.

`ApplicationEventPublisher` is a **notification publishing** API. `SimpleApplicationEventMulticaster` selects listeners by event type/adapter and dispatches them. `@EventListener` is a callback registration mechanism, **not** a security annotation.

Spring Security has its own mechanisms such as filter chains, method security, authorization checks, `SecurityContextHolder`, and concurrency integrations. They take effect only when **configured and applied at the right boundaries**. Do not assume that merely having a Spring Security dependency means every listener is automatically authorized.

### What Does "Internal" Scope Mean?

Application Events travel inside an application context; they are not a public message bus allowing clients to send directly over a network protocol. That reduces certain attack surfaces, yet **does not create a security sandbox between Spring beans**. If a component in the same JVM is compromised or runs code at equivalent trust, it can invoke services, publish events, read beans, or access other resources with process-level privileges.

Hence, extra checks inside listeners help defend against **programming bugs and invalid/forged data**, yet should not be advertised as isolating **malicious code running in the same process with the same privileges**. Strong isolation requires OS/process boundaries, distinct identities, network policies, scoped credentials, and authorization at receiving services.

## 3. Threat Model: Who Publishes, Who Listens, Who Trusts?

Start from the flow:

```text
Untrusted HTTP request / webhook / message
          |
          v
Authentication + authorization at entry point
          |
          v
Application service checks domain invariants / tenant / ownership
          |
          +--> DB transaction writes business state
          |
          +--> publishEvent(ImmutableDomainEvent)
                         |
              Spring event multicaster
                         |
             +-----------+----------------+
             |                            |
       Audit listener                 Notification listener
             |                            |
       minimal data                 API/email access
             |                            |
       PII control                  privileged side effect
```

Questions to ask before writing a listener:

1. Which code publishes the event? How many paths can publish the **same event type**?
2. Where was the actor authenticated? Is any authorization decision relying on a client-supplied `actorId`?
3. Does the event carry `tenantId`, `ownerId`, or `customerId`? Do those values come from a trusted source or a request body?
4. Which data does the listener read, what access level does it need, and could it touch cross-tenant data?
5. Does the listener only record metrics, or does it send emails, export data, update balances, generate invoices, or trigger payments?
6. If the event is replayed, forged, delivered out of order, or arrives after permissions were revoked, are side effects still safe?
7. Who can view logs/event payloads? Do tracing, dead-letter queues, backups, and support consoles retain copies of the data?

| Mistake | Description | Impact |
| --- | --- | --- |
| **Confused deputy** | Listener holds strong credentials and acts on a payload from an insufficiently trusted source | Performs actions on behalf of an unauthorized caller |
| **BOLA/IDOR** | Listener uses `orderId` or `customerId` without checking ownership | Reads/writes another user's object |
| **Cross-tenant leakage** | Trusts `tenantId` in the payload blindly | Leaks or mutates data from another tenant |
| **Privilege escalation** | Event carries caller-controlled `role=ADMIN` or `approved=true` | Bypasses authorization decisions |
| **Data overexposure** | Event carries full JPA entities or overly broad DTOs | Leaks PII/secrets via listeners, logs, or brokers |
| **Replay/duplicate** | Consumer processes old events multiple times | Sends duplicate notifications or repeats side effects |
| **Context confusion** | Async listener confuses `SecurityContext` or MDC | Attributes wrong actor/tenant; inaccurate audits |
| **TOCTOU** | Permissions were valid at publish time but changed before listener ran | Decisions rely on stale permissions no longer valid |

Not every listener needs to repeat an expensive authorization query. The protection level depends on **side-effect sensitivity**, where permissions were enforced, and whether the event represents a stored fact from a trusted flow. Even so, every design must state its source of truth and trust scope explicitly instead of silently assuming event types are inherently trustworthy.

## 4. Authorization Must Occur at the Command/Application-Service Boundary

Suppose a user submits an order-placement command. The proper flow:

1. The HTTP layer authenticates the token/session via Spring Security or equivalent.
2. Obtain the **authenticated principal from trusted security infrastructure**, never taking username/role directly from request JSON.
3. The application service checks whether the actor may place **that specific order**, verifying tenant, ownership, order state, and business invariants.
4. If denied, do not mutate the aggregate, write to the outbox, or publish the `OrderPlaced` business fact.
5. If permitted, perform the state transition inside a transaction, then publish the domain event or write to the outbox per delivery requirements.
6. Listeners receive a **notification of an accepted business action**, not a blank check to use anywhere.

**Integration** Spring Security pattern:

```java
@Service
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OrderPermissionService permissions;
    private final ApplicationEventPublisher publisher;

    public PlaceOrderService(
            OrderRepository orders,
            OrderPermissionService permissions,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.permissions = permissions;
        this.publisher = publisher;
    }

    @PreAuthorize("hasAuthority('ORDER_PLACE')")
    @Transactional
    public void placeOrder(String orderId, Authentication actor) {
        OrderEntity order = orders.findById(orderId).orElseThrow();

        if (!permissions.mayPlace(actor, order)) {
            throw new AccessDeniedException("No access to order");
        }

        order.place();
        publisher.publishEvent(new OrderPlacedEvent(
            UUID.randomUUID().toString(),
            order.getId(),
            order.getTenantId()
        ));
    }
}
```

**This is not a standalone runnable file.** It requires `@EnableMethodSecurity`, invoking the method through a Spring proxy, Spring Security dependencies/imports, JPA entities/repositories, `OrderPlacedEvent`, and an appropriate transaction manager. Never construct an `Authentication` from unverified request data; in web flows retrieve it from verified Spring Security context/infrastructure. For highly privileged operations, re-query user/permissions from an authoritative source.

**`@PreAuthorize("hasAuthority('ORDER_PLACE')")` alone is insufficient for object-level authorization.** Checking `permissions.mayPlace(actor, order)` verifies domain ownership/tenant. Skipping object-specific checks lets a user with general permission act on someone else's order.

**Beware of self-invocation:** a method annotated with `@PreAuthorize` called internally via `this.placeOrder(...)` in the same bean can bypass the security proxy; an event listener directly calling a private method certainly will not trigger method-security advice. When relying on Spring AOP proxies, test the real call path through the Spring bean/proxy and `@EnableMethodSecurity` configuration.

## 5. Event Type Is Not Proof of Authorization

A codebase can have multiple publishers:

```java
applicationEventPublisher.publishEvent(
    new OrderPlacedEvent("EVT-FAKE", "ORD-42", "tenant-A")
);
```

This is **illustrative code**, not a network-protocol exploit example. It shows any bean holding `ApplicationEventPublisher` can construct an instance and publish it. `@EventListener(OrderPlacedEvent)` does not distinguish an event published by a legitimate application service from one published directly by a poorly designed helper.

A dangerous listener:

```java
@EventListener
public void on(OrderPlacedEvent event) {
    refundOrChargeService.charge(event.orderId());
}
```

If the side effect is a financial operation, trusting `event.orderId()` alone is insufficient. A wrong or duplicate event can trigger unwanted charges. The listener must clarify: is this a **committed fact** or merely a **processing request**? If it is a command, it should go through an application service enforcing authorization/invariants; if it is an event, the listener must rely on a recorded fact/intent and idempotency mechanisms.

### Layered Protective Measures

- **Authorize at the command boundary:** never record a fact when the actor lacks permissions.
- **Re-read authoritative state:** listeners performing sensitive side effects should verify the appropriate aggregate/state/outbox record rather than trusting a payload flag like `approved=true`.
- **Valid event IDs and provenance:** critical consumers can cross-check `eventId` against a persisted outbox/approved work item.
- **Idempotency by event ID:** never apply an effect multiple times on replay.
- **Object/tenant scoping in DB queries:** query by verified `tenantId` and object ID, never a bare raw ID in multi-tenant systems.
- **Avoid exposing powerful capabilities:** listeners may need scoped credentials sufficient only for their task; within one process, credentials share the OS boundary so do not treat it as a sandbox.
- **Verifiable audits:** log event ID, verified actor (where appropriate), tenant, decision, and outcome per data policies.

No single annotation turns the Spring event bus into a trust boundary. These controls complement one another and must live where responsibility lies.

## 6. Actor ID, Tenant ID, Correlation ID, Event ID: Metadata Is Not a Credential

| Field | Valid Meaning | Must Not Be Inferred |
| --- | --- | --- |
| `actorId` | Records who initiated the business action | Does not prove the actor still has permission when the consumer runs |
| `tenantId` | Business partition associated with the event | Does not authorize reading every record for a payload-supplied tenant ID |
| `eventId` | Logical event identifier, dedupes retries | Not a digital signature or proof the event was authorized |
| `correlationId` | Links workflow logs/traces | Not a security token |
| `aggregateId` | Identity of the business object | Not proof of ownership |
| `occurredAt` | Timestamp when the fact occurred | Does not prove commit or freshness of state |
| `schemaVersion` | Payload structure version | Does not replace content validation |

Minimal immutable payload example:

```java
public record OrderPlacedEvent(
    String eventId,
    String orderId,
    String tenantId,
    String actorId,
    long totalCents
) {}
```

The payload is useful for auditing and authorized consumers, yet **is not an access-control decision**. Validate format/non-null/ranges at boundaries and establish provenance. For long-lived events, keep schema version, timestamp, and correlation ID in the contract; never send live Spring Security `Authentication`, sessions, JWTs, or mutable permission objects.

### Distinguishing "Event Recording Actor" from "Event Carrying Authority"

A business fact can remain legitimate even after the actor logs out post-commit; thus, **permission requirements when creating the fact** can differ from **current permissions at processing time**. For example:

- Business audit: needs to record who placed the order at that moment.
- Sending customer email: needs current email-consent policy, current address, and data scope.
- Creating a payment: needs an accepted payment intent, idempotency, and order state, not just `actorId`.
- Exporting personal data: may need to check current entitlement and legal basis rather than treating "once authorized" as a permanent license.

Policies must be defined per business flow, neither mechanically "always reauthorize" nor "never reauthorize."

## 7. Data Minimization and the Danger of Overly Broad Payloads

An internal event can easily end up carrying an entity:

```java
public record UnsafeCustomerChanged(CustomerEntity customer) {}
```

This is an **illustrative anti-pattern**. If `CustomerEntity` is a JPA managed entity, the event holds the same mutable reference and can expose the entire graph of lazy relationships, contact details, personal identifiers, hashed credentials, or administrative fields. Wrapping an entity inside a `record` does not make the entity immutable or restrict listeners.

Concrete risks:
- A listener needing only `customerId` receives unnecessary emails/addresses/phones.
- Loggers accidentally print `event.toString()` and leak PII.
- AOP instrumentation or exception handling serializes objects outside policy.
- Async handlers carry the entity to another thread, hitting lazy-loading failures or mutated state.
- If the event is later forwarded to Kafka/queues, the internal schema becomes an external contract exposing sensitive fields.
- Logs, traces, DLQs, backups, and monitoring have different retention/access rules than the source DB.

**Data minimization principle:** every event must carry only the facts needed by approved consumers. Consider sending only IDs and minimal snapshots, letting consumers query needed data via properly scoped and authorized services/repositories.

Note: ID-only **does not guarantee security by itself**. If a listener has unrestricted DB read access and queries by ID without checking tenant/ownership, hiding fields in the payload still does not prevent BOLA/IDOR. Data minimization and authorization are two distinct layers.

### Snapshots May Require the Same Protection as Source Data

If an event carries an address, email, or total at a point in time, that snapshot persists in logs/outboxes/brokers longer than the current entity. Establish policies for:
- Which fields may enter events?
- Who can read the event store, DLQs, traces, and logs?
- How long are they retained, and is encryption-at-rest or redaction applied?
- How are privacy deletion/rectification requests handled across copies?
- Are versioning/compatibility and data revocation supported?

Never call an event DTO "safe" just because it omits entities. An immutable DTO containing a secret is still a secret.

## 8. Runnable Java 17+ Example: Do Not Trust an Event Simply Because It Was Published

The following example uses **Spring Context 6.1.21** and in-memory state to illustrate:
1. An application service checks ownership **against a simulated repository** before changing order state.
2. An unauthorized call is rejected before publishing an event.
3. Any component in the same context can publish a **forged** event via `publishEvent`.
4. A sensitive listener checks whether the event ID matches a fact recorded by the application service.
5. Replaying a valid event is ignored via an idempotency key.

**Critical limitation:** this is a **defensive-programming illustration**, not an authentication system or security sandbox. The `authenticatedActor` parameter is **assumed** to have been obtained upstream by the entry point from a trusted authenticated principal; the demo has no Spring Security, JWT, or DB. If callers can arbitrarily pass `alice`, ownership checks protect nothing. In-memory Maps and Sets do not survive restarts or multi-instance deployments, and any bean in the same process with code execution privileges could manipulate the repository; production requires Spring Security, explicit policies, and DB transactions/unique constraints.

### 8.1. Project Structure

```text
internal-event-security/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/InternalEventSecurityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'internal-event-security'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.InternalEventSecurityDemo'
}
```

### 8.2. Complete Java File

`src/main/java/demo/InternalEventSecurityDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class InternalEventSecurityDemo {

    public record OrderPlaced(
            String eventId, String orderId, String actorId) {}

    // Simulated repository: production must use trusted storage.
    public static final class OrderRepository {
        private final Map<String, String> owners =
            Map.of("ORD-42", "alice");
        private final Set<String> placed = new HashSet<>();
        private final Map<String, String> recordedFacts =
            new HashMap<>();

        public boolean ownedBy(String orderId, String actorId) {
            return actorId != null
                && actorId.equals(owners.get(orderId));
        }

        public void recordPlaced(String orderId, String eventId) {
            if (!placed.add(orderId)) {
                throw new IllegalStateException("Order already placed");
            }
            recordedFacts.put(eventId, orderId);
        }

        public boolean hasRecordedFact(
                String eventId, String orderId) {
            return orderId != null
                && orderId.equals(recordedFacts.get(eventId));
        }
    }

    public static final class PlaceOrderService {
        private final OrderRepository repository;
        private final ApplicationEventPublisher publisher;
        private final AtomicInteger sequence = new AtomicInteger();

        public PlaceOrderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        // authenticatedActor: ASSUMED already authenticated upstream.
        public OrderPlaced place(
                String authenticatedActor, String orderId) {
            if (!repository.ownedBy(orderId, authenticatedActor)) {
                throw new SecurityException("Not allowed to place order");
            }

            String eventId =
                "EVT-" + sequence.incrementAndGet();
            repository.recordPlaced(orderId, eventId);

            OrderPlaced event =
                new OrderPlaced(eventId, orderId, authenticatedActor);
            publisher.publishEvent(event);
            return event;
        }
    }

    public static final class NotificationListener {
        private final OrderRepository repository;
        private final Set<String> processedIds = new HashSet<>();
        private int effects;

        public NotificationListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void on(OrderPlaced event) {
            if (!repository.hasRecordedFact(
                    event.eventId(), event.orderId())) {
                System.out.println(
                    "REJECTED eventId=" + event.eventId()
                );
                return;
            }

            if (!processedIds.add(event.eventId())) {
                System.out.println(
                    "DUPLICATE eventId=" + event.eventId()
                );
                return;
            }

            effects++;
            System.out.println(
                "HANDLED eventId=" + event.eventId()
                    + " orderId=" + event.orderId()
            );
        }

        public int effects() {
            return effects;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public PlaceOrderService placeOrderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new PlaceOrderService(repository, publisher);
        }

        @Bean
        public NotificationListener notificationListener(
                OrderRepository repository) {
            return new NotificationListener(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            PlaceOrderService orders =
                context.getBean(PlaceOrderService.class);
            NotificationListener listener =
                context.getBean(NotificationListener.class);

            try {
                orders.place("mallory", "ORD-42");
            } catch (SecurityException expected) {
                System.out.println("DENIED actor=mallory");
            }

            // Intentionally bypass service: Spring does not authenticate events.
            context.publishEvent(
                new OrderPlaced("EVT-FORGED", "ORD-42", "mallory")
            );

            // Actor assumed authenticated with ownership.
            OrderPlaced accepted =
                orders.place("alice", "ORD-42");

            // Replay of the exact same event.
            context.publishEvent(accepted);

            System.out.println("business_effects=" + listener.effects());
        }
    }
}
```

Run in the project directory with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

**Expected business stdout** (excluding auxiliary Gradle or Spring log lines):

```text
DENIED actor=mallory
REJECTED eventId=EVT-FORGED
HANDLED eventId=EVT-1 orderId=ORD-42
DUPLICATE eventId=EVT-1
business_effects=1
```

### 8.3. Output Analysis

1. `PlaceOrderService.place("mallory", ...)` fails `repository.ownedBy(...)`, so it throws `SecurityException` **before** recording any fact or publishing. `main` prints `DENIED`.
2. A forged event is published directly via the context: Spring does not block constructing `OrderPlaced`. The listener is invoked, yet `recordedFacts` does not contain `EVT-FORGED`, so it prints `REJECTED`.
3. `PlaceOrderService.place("alice", "ORD-42")` assumes `alice` is a valid principal, checks ownership, records the fact under `EVT-1`, and publishes. The listener sees the recorded fact and prints `HANDLED`.
4. When the same `accepted` event is published a second time, `processedIds.add(eventId)` returns `false`, so the listener prints `DUPLICATE` without incrementing `effects`.
5. The total `business_effects=1` shows the demo prevents duplicates within a single JVM and single thread. It **does not** prove proper authorization if callers can pick actor names or stop arbitrary code running in the same process.
6. Across multiple threads/processes or crashes between recording `processedIds` and executing the side effect, a `HashSet` is insufficient. You need transactions/unique constraints or external system idempotency keys.

**Why is this a security-boundary example?** It illustrates the difference between **an event dispatched by Spring** and **an event corresponding to a business fact accepted by the application service**. Still, an in-memory check in a listener is only a guard against mistakes; **it does not create a secure isolation boundary between beans in the same process**. If an untrusted module runs arbitrary code in the JVM, isolate it into a separate service/process with API-level authorization instead of relying on event handlers.

## 9. How Can Forged Data Slip Through Events?

Another example: a controller receives JSON:

```json
{
  "orderId": "ORD-42",
  "tenantId": "tenant-admin",
  "approved": true
}
```

This is **illustrative input data**, not a trusted signal. If the controller maps the request straight into an event:

```java
@PostMapping("/orders/place")
public void place(@RequestBody PlaceOrderRequest request) {
    events.publishEvent(new OrderPlacementApproved(
        request.orderId(),
        request.tenantId(),
        request.approved()
    ));
}
```

so that a privileged listener sees `approved=true` and executes a side effect, the application has turned **client-controlled input** into something treated like an authorization decision. The risk is **confused deputy**: a listener with strong credentials obeys unverified data.

Instead:
- The request body expresses only the request, never an authorization verdict.
- The controller relies on verified authentication and invokes an application service.
- The service loads the object scoped by tenant/owner from an authoritative source, checks policy, and executes the command.
- The event represents only the resulting fact and minimal approved data.
- Sensitive listeners rely on authoritative facts/outbox/records or re-check policy when needed.

Even `@Valid`/Bean Validation on request DTOs checks only **data shape/bounds**, not object-level authorization or business policies.

## 10. Multi-Tenant: tenantId in an Event Is Not a Trusted Filter

In a multi-tenant system, an event may carry `tenantId` for routing work. However, listeners must not blindly use that value to query any object.

Dangerous example:

```java
OrderEntity order = repository.findById(event.orderId())
    .orElseThrow();
externalApi.send(order.getCustomerEmail());
```

This can read an order belonging to another tenant if the ID is valid and policy is not enforced. Safer pattern:

```java
OrderEntity order = repository.findByIdAndTenantId(
        event.orderId(), trustedTenantId
    )
    .orElseThrow();
```

Both snippets are **integration patterns**: the repository/query and `trustedTenantId` must come from an authoritative source, not merely a caller-filled event field. In the database, enforce tenant scope across all queries, updates/deletes, and object relationships; consider row-level security or repository APIs that always require a tenant when cross-tenant risk exists.

A TOCTOU scenario: tenant/object ownership changes after the event is published but before an async listener reads again. The listener must specify whether its requirement relies on the **snapshot authorized when the fact occurred** or **current permissions**. There is no universal answer; state the business policy explicitly.

## 11. Spring SecurityContext: Does Not Automatically Propagate Across Async Listeners

In the servlet stack, `SecurityContextHolder` defaults to a `ThreadLocal`-based strategy. When the multicaster uses a `TaskExecutor` or a listener method has `@Async`, the worker is typically a **different thread** and does not automatically inherit the request's authentication context.

```text
HTTP request thread
  SecurityContext(actor=alice)
          |
          +--> publishEvent(OrderPlaced)
                        |
                        +--> executor worker thread
                               SecurityContext may be empty
```

This has two consequences:
1. If a listener **needs** to know the originating actor for auditing, record a verified `actorId` in the event fact; do not read `SecurityContextHolder` on a later thread and guess.
2. If a listener truly must act under the current identity, use Spring Security-supported propagation mechanisms while carefully evaluating **scope, privileges, lifetime, and cleanup**.

Spring Security provides wrappers such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor` to attach/transfer `SecurityContext` per contract. **Integration** configuration example:

```java
@Bean("securedTaskExecutor")
AsyncTaskExecutor securedTaskExecutor(
        ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
```

This requires Spring Security concurrency integration and corresponding imports; use it only when this executor is genuinely the executor to which listeners/tasks are submitted.

**Do not treat propagation as authorization.** Copying a high-privilege context into a task can make background work run with broader rights than needed. Contexts can go stale if a user is locked or roles are revoked, and tasks may finish after the request has ended. For long-running jobs, it is often better to use a **minimal-privilege service identity** and enforce policy where work executes rather than keeping user permissions alive on a thread pool.

### MDC/Correlation ID Is Not a SecurityContext Either

`MDC.put("userId", ...)` is purely logging data. `correlationId`, `traceId`, or thread names do not prove authentication; never use them inside `@PreAuthorize` as a security principal. If auditing requires it, include the verified actor as metadata and govern log access/PII.

## 12. Transaction Timing Does Not Elevate Trust

With synchronous Spring events, `@EventListener` may run **before the DB commit** inside the publisher's transaction. A listener performing external non-DB side effects when the transaction later rolls back can cause inconsistency.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` defers the callback until after a successful commit, yet it does not:
- Authenticate who created the event;
- Verify tenant/ownership;
- Prevent other beans from publishing the same event type;
- Guarantee the callback is not lost on JVM crash;
- Mint a new security principal for workers;
- Automatically guarantee idempotency or authorization for side effects.

Integration example:

```java
@Component
public class OrderEmailListener {
    private final OrderReadService orders;
    private final MailGateway mail;

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlacedEvent event) {
        OrderEmailView view = orders.loadAllowedNotificationView(
            event.orderId(), event.tenantId()
        );
        mail.sendConfirmation(view);
    }
}
```

This is an **integration snippet**, requiring beans/repositories, view types, tenant policies, and imports. `orders.loadAllowedNotificationView` must be implemented properly against authoritative data; merely naming a method "Allowed" does not make it safe.

If an after-commit callback reads/writes the database, use an appropriate new transaction when needed (such as a bean method with `@Transactional(propagation = REQUIRES_NEW)`), rather than assuming the original transaction will still commit later changes. In Spring Tests, an `@Transactional` test that auto-rolls back at the end will not trigger `AFTER_COMMIT`; you must actually commit when testing that phase.

**Security boundaries and durability are two orthogonal axes**: an event can be authorized yet still lost on a crash, or delivered reliably via a broker while carrying wrong-tenant data. Designs must address both.

## 13. Outboxes and Brokers Do Not Automatically Guarantee Data Safety

To avoid losing events after commit, an application may use a transactional outbox:

```text
Application service
  |-- Authentication + object-level authorization
  |-- Domain transition
  |-- INSERT outbox(eventId, aggregateId, type, safePayload)
  |-- COMMIT both domain state + outbox
                         |
                         v
               Outbox dispatcher / broker
                         |
                         v
               Consumer validate, authorize
                         |
                         v
               Idempotent business effect
```

An outbox provides **reliability**, not authentication. If a producer writes sensitive data or a wrong-tenant payload into the outbox, the broker will very durably replay a security bug. Therefore:
- Design integration event schemas separately from JPA entities.
- Define required fields, consumer permissions, and data classification.
- Apply ACL/IAM/broker topic permissions, TLS, and encryption as required.
- Deduplicate by `eventId` and consumer identity on retries.
- Consumers must validate message schemas, sources, and their own policies.
- Protect DLQs, tracing, replay consoles, and outbox admin tooling since they can contain payloads.
- Monitor retries and access permissions; avoid logging raw events in exceptions.

When events leave the process, **trust boundaries become sharper**: never trust a message merely because it came from an "internal topic." Require service identities, message transport security, and consumer-side authorization. Signatures or envelope metadata help only when keys/verification are managed under an appropriate threat model, and they never replace business authorization.

## 14. Replay, Idempotency, and Permissions Changing Over Time

Suppose `CustomerExportRequested(EVT-42)` was created while the user held export permission. Before the background worker runs, the permission is revoked. At least two valid policies exist depending on the application:

| Policy | Meaning | When Appropriate? |
| --- | --- | --- |
| **Authorize at request time** | Intent was accepted as a binding job; worker executes the committed authorized intent | Approved work intended to run later under a contract |
| **Reauthorize at execution time** | Worker checks current permissions before exporting data | Sensitive data/rights that may be revoked and must take effect immediately |
| **Hybrid** | Stores approved intent, yet still checks consent/legal basis/tenant policy before side effects | Long-running workflows with state changes and compliance rules |

Do not assume every event must re-check user roles at processing time; that can break valid workflows after a user logs out. Conversely, never assume "once valid, always valid" for data exports or high-privilege operations. Document the policy explicitly per use case.

**Idempotency differs from authorization.** A unique constraint on `(consumer_name, event_id)` prevents reprocessing the same event, yet an accepted first event can still be unauthorized without proper authorization. An event ID is not a "pre-cleared pass."

For external APIs, prefer upstream-accepted idempotency keys; on uncertain timeouts, reconciliation against external references may be needed. Never rely solely on an in-memory `Set` and assume multi-instance safety.

## 15. Protecting Listeners That Perform Privileged Side Effects

A listener might merely do best-effort cache invalidation, or it might:
- Send emails containing PII;
- Export customer data;
- Create ledger entries, payments, or refunds;
- Send messages to partner systems;
- Modify user, tenant, or access-permission states.

For sensitive side effects, design a clear handler contract:

1. **Source of intent:** a valid business fact/command accepted by a service, ideally persisted in a DB/outbox with a stable ID.
2. **Data scope:** aggregate/tenant resolved from authoritative records; every query has proper tenant/ownership guards.
3. **Permissions:** enforced at the command boundary and/or reauthorized per execution policy.
4. **Minimal data:** read only fields the listener needs; avoid full entities and raw request bodies.
5. **Idempotency:** explicit keys backed by transactions/unique constraints or external API mechanisms.
6. **Audit:** record who requested, what was decided, when, and under which policy/version if needed.
7. **Failure policy:** if permissions are missing or a forged event is detected, fail closed without silently executing; emit safe logs/metrics and provide an investigation path.
8. **Recovery:** retries must never bypass auth/validation; for DLQs/replays, restrict who can trigger replays.

A listener can call a service guarded by method security rather than duplicating policy. However, verify the call goes through **Spring proxy/authorization infrastructure**, and that method security protects the specific resource rather than only a broad role.

### Do Not Grant Default "Root Privileges" to Background Tasks

A worker being trusted infrastructure does not mean every event may command that worker to do anything. Design task-specific service methods and credentials under least privilege, restricting callable endpoints, DB/table rights, topic scopes, and exported data. A "god listener" reading every event and performing every side effect is hard to audit and expands blast radius.

## 16. Testing Event Security Properly

### 16.1. Authorization at the Entry/Service Boundary

- User lacks general permission → service rejects before touching the DB or publishing business facts.
- User has `ORDER_PLACE` permission but does not own the order → service rejects.
- User in tenant A tries to act on tenant B's order → service rejects.
- Authorized user → aggregate transitions properly and a fitting fact is recorded.
- Invoke methods through beans/proxies, not just calling un-advised methods directly.

When tests use `@WithMockUser`, distinguish **mocking a principal for tests** from proving real JWT/OAuth authentication works. Separate filter-chain integration tests may be needed to verify the authentication boundary.

### 16.2. Listener Receiving a Forged Payload

In a test context, call `publishEvent(new OrderPlacedEvent(...))` directly with an unverified event. For sensitive side-effect listeners, assert they do **not** send emails/charges/exports when the contract requires an approved fact. The section 8 demo illustrates this check.

This tests against **accidental publication**; it does not prove malicious code in the same JVM is sandboxed. If the security model includes untrusted plugins, test true separation across services/processes/credentials.

### 16.3. Deduplication and Concurrency

- Re-sending the same `eventId` → side effect is not duplicated.
- Two different event IDs for the same aggregate → consumer handles them per semantics/version rather than wrongly dropping based on aggregate ID alone.
- Two workers concurrently claiming the same event → unique constraints or atomic mechanisms protect the effect.
- Failure after side effect before ACK → retrying the same ID does not repeat the unintended business effect.

### 16.4. Async SecurityContext and MDC

Write a test listener running on `ThreadPoolTaskExecutor` with `@Async` or a multicaster executor. Assert:
- Context is not assumed to propagate automatically.
- If using `DelegatingSecurityContextAsyncTaskExecutor`, context is set/cleared per policy and never leaks to another actor's task.
- Authorization is never inferred from thread names or MDC.
- Delayed tasks use approved intents or reauthorization per policy.
- Without a principal, privileged operations fail closed rather than falling back to default admin rights.

Await tasks using `CountDownLatch`/`CompletableFuture`/Awaitility with bounded timeouts; never use `Thread.sleep` and guess the outcome.

### 16.5. Transactions and Crash Windows

- Publish before rollback: no unauthorized side effects occur when the command rolls back.
- `@TransactionalEventListener(AFTER_COMMIT)` executes only on real commits; do not expect callbacks in an auto-rolling-back test transaction.
- Crash after DB commit before callback → an outbox is required if events cannot be lost.
- Outbox replay/broker retries → consumers still validate source, scope, and idempotency.

### 16.6. Data Leaks

Verify event DTOs/serialization:
- No access tokens, passwords, secrets, full entity graphs, or out-of-scope PII.
- Loggers never call `toString()` on sensitive full payloads.
- Exception handlers/metrics/tracing never expose event bodies.
- DLQ/outbox/log retention and read permissions match data classification.
- Cross-tenant queries are explicitly tested with valid IDs belonging to other tenants.

## 17. Anti-Patterns and Fixes

| Anti-Pattern | Why It Is Wrong | Replacement |
| --- | --- | --- |
| "It has `@EventListener`, so the event is trusted" | Listener registration is only dispatch | Validate source and use approved domain facts |
| Using `event.actorId` as a principal | Actor ID is data; can be spoofed or stale | Principal from Spring Security boundary, explicit policy |
| Putting `role=ADMIN` in the event | Caller-sent flag is not authorization | Check permissions in the service/consumer |
| Letting clients send `tenantId` and querying the whole DB | Easy cross-tenant leak | Derive tenant from trusted context/record and scope queries |
| Sending managed JPA entities to every listener | Mutable, lazy, overexposed | Minimal immutable DTO/snapshot/IDs |
| Putting JWTs in events to "preserve rights" | Exposes credentials, tokens expire, leaks in logs/brokers | Actor metadata + policy, service identity where needed |
| Copying `SecurityContext` to every thread | Uncontrolled privilege propagation | Propagate only when needed; scope/cleanup and least privilege |
| Believing `AFTER_COMMIT` means secure/durable | Phase differs from authorization/delivery guarantees | Authorization + outbox if required |
| Deduplicating `eventId` is enough security | Idempotency does not prove authorization | Independent authorization |
| Listener calls external APIs from a raw ID | Confused deputy / IDOR | Read authoritative record and policy before side effects |
| A `tenantId` string in an event equals "tenant isolation" | Just a metadata string | Tenant-scoped repositories/RLS/service policies |
| Logging whole events "for debugging" | Leaks PII, tokens, long-lived data | Structured logs with safe IDs only |
| Treating internal broker topics as unconditionally trusted | Misconfigurations or other producers can publish | Broker ACLs, identities, consumer authorization |

## 18. Pre-Merge Design Checklist

- [ ] Clearly distinguished event notification from authentication/authorization boundaries?
- [ ] Command/application service obtains principal from an **authenticated source**, never from client-controlled body fields?
- [ ] Object-level authorization, tenant isolation, and domain invariants enforced before recording business facts?
- [ ] Code does not assume `publishEvent` or `@EventListener` validates event provenance automatically?
- [ ] Privileged listeners rely on authoritative approved records/policies rather than trusting flags in payloads?
- [ ] Event payloads contain only essential IDs/facts, with no tokens, credentials, managed entities, or excess data?
- [ ] `actorId`, `tenantId`, `correlationId`, and `eventId` are used strictly in their proper roles, never as authorization passes?
- [ ] Async tasks do not assume `SecurityContextHolder` follows the thread automatically?
- [ ] Where security context is propagated, scope and cleanup are tested without granting excessive privileges?
- [ ] Authorize-at-request vs reauthorize-at-execution policy is explicitly defined for delayed work?
- [ ] `@TransactionalEventListener` is used for the right phase without confusing it with security or durability?
- [ ] Non-droppable work uses an outbox/queue and idempotent consumers that still enforce security validation?
- [ ] Schemas/serialization/logging/traces/DLQs comply with data classification and retention policies?
- [ ] Tests cover forged events, object permissions, cross-tenant isolation, replays, concurrency, and failure windows?
- [ ] If untrusted extension code must run, is there **real process/service isolation** instead of treating `ApplicationContext` as a sandbox?

**Remember:** internal events are **in-application signals**, not **proof of authorization**. Spring handles publishing and listener selection, while the application itself must authenticate inputs, check authorization/ownership/tenant boundaries, minimize data, and constrain side effects. To isolate untrusted code, build real security boundaries at processes/services/APIs and identities rather than relying on two modules communicating via `publishEvent`.

## References

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Concurrent Execution / SecurityContext](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
