# Tenant Isolation in Events — Spring Framework Application Events

## 1. The Problem: How Can an Event Leak Data Across Tenants?

In a **multi-tenant** system, one application serves multiple independent organizations/customers on shared infrastructure. Each tenant has its own data, access permissions, and processing boundaries. When a service publishes `OrderCreated`, listeners may update a read model, send an email, record an audit log, compute quotas, or write a notification into an outbox. If a listener queries or writes data **without a tenant condition**, a valid event from tenant A can alter tenant B's data.

Example of a risky design:

```java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Danger: looking up order by orderId only.
    Order order = orderRepository.findByOrderId(event.orderId());
    notificationService.send(order.customerEmail());
}
```

This is a **counterexample**, not standalone code: repository and service classes are omitted. If both tenants use `orderId = "ORDER-7"`, or the repository happens to return the first matching record, the listener may notify the wrong recipient.

Another mistake is calling `TenantContext.getCurrentTenant()` from a `ThreadLocal` inside an `@Async` listener. The asynchronous worker thread usually **does not have the publishing thread's context**. If a thread pool is used without proper context cleanup, the worker might even hold a **stale tenant ID** from an earlier task. Either case can cause cross-tenant bugs.

**Tenant isolation in events** is the set of safeguards ensuring that event data and side effects belong to the right tenant at **every stage**: source authentication, permission checks, payload creation, dispatch, data queries, result writes, retries, logging, and handoff to external systems.

### Learning Objectives

After this lesson, you will be able to:

1. Understand that **a tenant ID is scope-identifying data**, not proof that the sender is authorized.
2. Build event payloads that explicitly carry `tenantId`, `eventId`, and business IDs.
3. Derive the tenant from **authenticated identity and trusted membership**, never blindly trusting request headers or bodies.
4. Use **(tenant_id, entity_id)** keys and queries to avoid ID collisions across tenants.
5. Verify **event provenance** before a listener performs sensitive operations.
6. Distinguish event tenant scope from `SecurityContext`, MDC, and `ThreadLocal` under `@Async`.
7. Choose appropriate protections for databases, caches, outboxes, brokers, object storage, logs, and background jobs.
8. Test isolation when two tenants share the same `orderId`, reject cross-tenant access, and detect forged events.
9. Know the limits of Spring Application Events: an in-process mechanism **is not a security boundary or a durable delivery mechanism**.

## 2. What Does Tenant Isolation Protect?

In an event-driven workflow, consider **confidentiality**, **integrity**, and **availability**:

| Goal | Question | Violation Example |
| --- | --- | --- |
| Confidentiality | Does a listener read or expose another tenant's data? | Tenant B's email is sent in tenant A's flow |
| Integrity | Does tenant A's event modify tenant B's data? | B's projection is updated from A's event |
| Authorization | Does the publishing user or service have rights in the target tenant? | Client tampers with `tenantId` in JSON |
| Provenance | Was the event truly created by a trusted source? | Consumer receives a forged message with an arbitrary tenant ID |
| Resource isolation | Can one tenant starve all event workers? | One tenant emits excessive events, filling the shared queue |
| Auditability | Can operations be traced by tenant and permission? | Logs have only `orderId`, missing `tenantId` |
| Resilience | Do retries/replays preserve the exact tenant and idempotency key? | Replaying A's event under B's active context |

Adding a `tenantId` field to an event should not be mistaken for a complete solution. That field helps **scope data**, but it does not stop a malicious caller from putting another tenant ID into the payload. Trust boundaries must be enforced **before creating the event** and **where side effects occur**.

### Minimal Threat Model

Assume the system has:

- Tenants `tenant-a` and `tenant-b`.
- User `alice`, a member of tenant A.
- User `bob`, a member of tenant B.
- Each tenant may have an order named `ORDER-7`.
- A listener processes `OrderCreated` to update a read model.

Requirements:

```text
alice -> tenant-a / ORDER-7       ALLOW
bob   -> tenant-b / ORDER-7       ALLOW
alice -> tenant-b / ORDER-7       DENY
event A -> A's projection         ALLOW
event A -> B's projection         DENY
```

Having the same `orderId` in two tenants is not duplicate data; records must therefore be distinguished by **tenant_id plus order_id**.

## 3. What Fields Should a Multi-Tenant Event Carry?

An immutable payload using a Java 17 record:

```java
public record OrderCreated(
        String eventId,
        String tenantId,
        String orderId,
        Instant occurredAt
) {}
```

This is a data-type snippet; the complete example in section 8 adds validation.

Field meanings:

| Field | Meaning | Rule |
| --- | --- | --- |
| `tenantId` | Scope of the tenant owning the event | Obtained from verified permissions; never trust client input blindly |
| `eventId` | ID for a single event occurrence | Preserved across retries/replays of the same occurrence |
| `orderId` | Object identifier within the tenant | May collide across different tenants |
| `occurredAt` | Business timestamp when the event was created | Use `Instant` or a controlled clock |
| `correlationId` (if present) | Groups events belonging to a workflow | Does not imply permission or idempotency |
| `causationId` (if present) | Direct parent event | Does not replace tenant ID |
| `schemaVersion` (if needed) | Payload version | Useful when messages are stored durably and evolved |

**Every derived event must retain the tenant of the originating business action**, unless there is an explicitly authorized and fully audited cross-tenant workflow. Do not pull a new tenant from MDC or the current HTTP request if the event has moved to another thread.

### Records Are Shallowly Immutable

Record fields are `final`, yet a record holding a `List<Customer>` or a mutable entity is still not deeply immutable. For collections, use `List.copyOf(...)`; for mutable elements, create a dedicated immutable snapshot. Never put a live JPA entity or an active `Authentication`/`SecurityContext` into an event payload. Payloads should hold required IDs and business values, not sensitive resources tied to a thread or request lifecycle.

### Avoid Carrying Unnecessary Sensitive Data

An `OrderCreated` event that only needs `orderId` and `tenantId` for a listener to look up authorized details does not need to bundle full emails, card details, or addresses. Records auto-generate `toString()` containing all components; if a payload carries PII/secrets, `log.info("{}", event)` can inadvertently leak data.

## 4. Establishing Tenant Context from a Trusted Identity

### 4.1. Do Not Trust a tenantId Header on Its Own

A request might send:

```http
POST /tenants/tenant-b/orders
Authorization: Bearer <access-token>
Content-Type: application/json

{"orderId":"ORDER-7"}
```

This is an **illustrative request example**, not real credentials. The path segment `tenant-b` is the **requested tenant**, not proof that the caller has permission. The server must:

1. Authenticate the token/session and identify a trusted principal.
2. Look up the principal's current tenant membership, roles, or entitlements.
3. Verify the principal is allowed to perform the operation **on `tenant-b`**.
4. If allowed, pass the verified tenant to the service and create the event.
5. Otherwise, return an appropriate error without leaking data from other tenants.

Do not trust `tenantId` in a JSON body, query parameter, or arbitrary header just because the field name looks plausible. Those values may be treated as the **requested tenant**, but must be checked against authenticated permissions.

### 4.2. The Role of Spring Security

In an application integrated with Spring Security, identity is represented by `Authentication` inside `SecurityContextHolder` according to the configured strategy. However, **merely reading `authentication.getName()` is not a tenant membership check**.

There should be an authorization service:

```java
public void requireTenantPermission(
        Authentication authentication,
        String requestedTenantId,
        String operation) {
    // Check real authentication, not anonymous.
    // Look up permissions/tenant membership from a trusted source.
    // Verify operation is allowed on requestedTenantId.
    // Otherwise, throw AccessDeniedException.
}
```

This is **architectural API pseudocode**, not a standalone implementation: you must implement policy, anonymous checks, token claims, and the real membership source. A `tenant_id` claim inside a token can be a trusted input **only after the token's signature, issuer, audience, expiry, and system policy have been verified**. If a user belongs to multiple tenants, do not assume a default claim grants access to all tenants.

**Do not derive permissions from logging context.** `MDC.put("tenantId", "...")` is for logging, not proof that the caller can access that tenant.

## 5. Four Protection Layers in the Event Pipeline

```text
HTTP / broker / scheduler
        |
        | 1. AUTHENTICATE + AUTHORIZE source
        v
Application service
        |
        | 2. CREATE trusted immutable event
        |    { tenantId, eventId, orderId }
        v
ApplicationEventPublisher.publishEvent(event)
        |
        | 3. VALIDATE event provenance / invariant
        v
@EventListener(OrderCreated)
        |
        | 4. TENANT-SCOPED REPOSITORY / PROJECTION
        v
(tenant_id, order_id) database/cache/storage
```

**Layer 1 — Authenticate and authorize at the entry point.** If a message comes from a broker/HTTP, authenticate the source identity, check tenant permissions, schema, and publisher. A payload merely containing a tenant name cannot prove validity on its own.

**Layer 2 — Record the verified tenant in the event.** The service does not accept an arbitrary tenant ID from the caller; it uses the authorized tenant. The event has a stable ID and the data needed for delayed work or replay.

**Layer 3 — Listener re-verifies when needed.** Depending on sensitivity, the listener verifies that the event comes from a trusted source/aggregate/state, especially when events may arrive from a broker or public integration. If a consumer receives untrusted messages, you need producer authentication/authorization (e.g., broker ACLs, service identity, signatures, or authoritative data), not merely comparing payload fields against each other.

**Layer 4 — Every storage access is tenant-scoped.** Queries, updates, cache keys, outbox keys, and object paths must use the right tenant. Even if one layer misses a validation check, database policies/tenant partitions act as an extra line of defense.

## 6. Database Isolation: Tenant as Part of Keys and Queries

### 6.1. Shared-Table Model

A minimal schema:

```sql
CREATE TABLE orders (
    tenant_id  VARCHAR(80) NOT NULL,
    order_id   VARCHAR(80) NOT NULL,
    status     VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
```

`ORDER-7` can exist in both `tenant-a` and `tenant-b` without conflict.

Properly **scoped** query:

```sql
SELECT tenant_id, order_id, status
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
```

Properly **scoped** update:

```sql
UPDATE orders
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?;
```

Forbid a sensitive repository from doing:

```sql
SELECT * FROM orders WHERE order_id = ?;
```

if `orderId` is only unique **within a tenant**. A query missing the tenant can return another tenant's row or leak the existence of unauthorized data.

Repository methods should require passing the tenant:

```java
Optional<Order> findByTenantIdAndOrderId(
        String tenantId, String orderId);
```

This is a **repository signature illustration**; define the entity/JPA repository to match your application. Having a tenant-parameterized query method does not mean authorization is finished: the service must verify the caller is allowed to use that `tenantId`.

### 6.2. Schema-per-Tenant or Database-per-Tenant

A system may use three architectures:

| Architecture | Benefits | Risks to Address |
| --- | --- | --- |
| Shared table, `tenant_id` discriminator | Economical infrastructure, scales easily to many small tenants | Missing predicates/constraints cause cross-tenant leaks |
| Schema-per-tenant | Separates database objects per tenant | Selecting wrong schema, connection pool retaining old schema |
| Database-per-tenant | Stronger physical/logical storage isolation | Wrong connection routing, high operational cost |

Regardless of the model, **tenant routing in a listener** must rely on a validated tenant. When using Hibernate multi-tenancy, configure resolvers/connection providers according to your ORM version and system design; never assume every query is automatically safe just because the code mentions `tenantId`.

### 6.3. Row-Level Security as Defense-in-Depth

With PostgreSQL, Row-Level Security (RLS) can restrict rows read/written per tenant at the database layer. However, policies, roles, and connection/session/transaction settings must be configured properly; table owners or privileged roles can bypass RLS depending on configuration. Do not assume toggling a flag without testing roles and connection pooling already guarantees isolation.

Even with RLS, **the service must still authorize the caller**. RLS is an extra defensive layer, not a replacement for authentication or business policy.

## 7. Is Spring ApplicationEventPublisher a Security Boundary?

**No.** `publishEvent(Object)` is a mechanism for publishing and distributing events **inside an ApplicationContext**. Once any bean obtains a reference to `ApplicationEventPublisher`, that bean can publish arbitrary objects per the API. The framework **does not verify message signatures, check tenant membership, or enforce business ACLs per payload**.

For example, a bean could construct:

```java
publisher.publishEvent(
        new OrderCreated(
                "evt-forged",
                "tenant-b",
                "ORDER-7",
                Instant.now()));
```

Just because the payload states `tenant-b` does not mean the event was genuinely created by a service authorized for tenant B. If a listener writes to the database based solely on this field, it is trusting unverified data.

In a **trusted application code** model within a single internal context, publisher services may be governed by code review and entry-point authorization; however, for external message integrations, you must check source identity, tenant scope, integrity, and event schema at the **boundary adapter**. Consumers with sensitive side effects should validate business data against an authoritative source of truth.

### Do Not Confuse `getSource()` with Tenant Identity

A traditional event extending `ApplicationEvent` has `getSource()` passed to its constructor, yet that field **does not prove the producer is permitted to act for a tenant**. For POJO records, Spring may wrap them in `PayloadApplicationEvent`; the wrapper's `source` is not a tenant authentication identity either.

Do not make authorization decisions based solely on the source object's class or listener method name.

## 8. Complete Java 17 + Spring Framework 6.2 Example

The following console example simulates **two tenants using the same `orderId`** and three controls:

1. `alice` creates order `ORDER-7` for `tenant-a`, and `bob` creates `ORDER-7` for `tenant-b`.
2. Reading projections is restricted by tenant permission. `alice` cannot read `tenant-b`.
3. A forged `OrderCreated` is published: assigned `tenant-b` while reusing tenant A's original `eventId`. The listener checks against the **authoritative store by tenant and orderId**, and rejects it.

The example intentionally uses an in-memory `TenantAuthorizer` instead of full Spring Security so tenant logic is easy to verify. The `authenticatedUser` parameter in the demo **represents an identity already authenticated at the entry point**, not advice to trust a `userId` sent by a request. Production must obtain the principal from a verified security layer.

### 8.1. Directory Structure

```text
tenant-isolation-events/
├── pom.xml
└── src/main/java/example/TenantIsolationDemo.java
```

### 8.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>tenant-isolation-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.TenantIsolationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. File src/main/java/example/TenantIsolationDemo.java

```java
package example;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class TenantIsolationDemo {

    // Composite key: same orderId in another tenant is a different record.
    public record OrderKey(String tenantId, String orderId) {
        public OrderKey {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    // Immutable POJO payload; Spring accepts it via publishEvent(Object).
    public record OrderCreated(
            String eventId,
            String tenantId,
            String orderId,
            Instant occurredAt) {

        public OrderCreated {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank()
                    || tenantId.isBlank()
                    || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "Event identifiers cannot be blank");
            }
        }
    }

    // Demo: static ACL representing a trusted membership source.
    // Production: user comes from a verified Authentication.
    public static final class TenantAuthorizer {
        private final Map<String, Set<String>> membership = Map.of(
                "alice", Set.of("tenant-a"),
                "bob", Set.of("tenant-b"));

        public void requireMembership(
                String authenticatedUser,
                String tenantId) {
            if (!membership.getOrDefault(
                    authenticatedUser, Set.of()).contains(tenantId)) {
                throw new SecurityException(
                        "Not allowed to access requested tenant");
            }
        }
    }

    public static final class OrderStore {
        // Verified eventId bound to (tenantId, orderId).
        private final Map<OrderKey, String> events =
                new ConcurrentHashMap<>();

        public void create(OrderKey key, String eventId) {
            if (events.putIfAbsent(key, eventId) != null) {
                throw new IllegalStateException(
                        "Order already exists in this tenant");
            }
        }

        public boolean matches(OrderKey key, String eventId) {
            return Objects.equals(events.get(key), eventId);
        }
    }

    public static final class ProjectionStore {
        private final Map<OrderKey, String> projections =
                new ConcurrentHashMap<>();

        public void project(OrderKey key, String eventId) {
            // Idempotent for the "OrderCreated" event in the demo.
            projections.putIfAbsent(key, eventId);
        }

        public String get(OrderKey key) {
            return projections.get(key);
        }

        public int rowCount() {
            return projections.size();
        }
    }

    public static class OrderService {
        private final TenantAuthorizer authorizer;
        private final OrderStore orderStore;
        private final ProjectionStore projectionStore;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                TenantAuthorizer authorizer,
                OrderStore orderStore,
                ProjectionStore projectionStore,
                ApplicationEventPublisher publisher) {
            this.authorizer = authorizer;
            this.orderStore = orderStore;
            this.projectionStore = projectionStore;
            this.publisher = publisher;
        }

        public void create(
                String authenticatedUser,
                String tenantId,
                String orderId,
                String eventId,
                Instant occurredAt) {
            // Do not use tenant from the request before checking ACL.
            authorizer.requireMembership(authenticatedUser, tenantId);

            OrderCreated event = new OrderCreated(
                    eventId, tenantId, orderId, occurredAt);
            OrderKey key = new OrderKey(tenantId, orderId);

            // In-memory demo; production uses transaction + outbox.
            orderStore.create(key, event.eventId());
            publisher.publishEvent(event);
        }

        public String readProjection(
                String authenticatedUser,
                String tenantId,
                String orderId) {
            authorizer.requireMembership(authenticatedUser, tenantId);
            return projectionStore.get(new OrderKey(tenantId, orderId));
        }
    }

    public static class OrderProjectionListener {
        private final OrderStore orders;
        private final ProjectionStore projections;
        private final AtomicInteger rejected = new AtomicInteger();

        public OrderProjectionListener(
                OrderStore orders,
                ProjectionStore projections) {
            this.orders = orders;
            this.projections = projections;
        }

        @EventListener
        public void onCreated(OrderCreated event) {
            OrderKey key =
                    new OrderKey(event.tenantId(), event.orderId());

            // Verify eventId against the authoritative source for the exact tenant.
            if (!orders.matches(key, event.eventId())) {
                rejected.incrementAndGet();
                throw new SecurityException(
                        "Event not backed by authoritative order");
            }

            projections.project(key, event.eventId());
        }

        public int rejectedCount() {
            return rejected.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public TenantAuthorizer tenantAuthorizer() {
            return new TenantAuthorizer();
        }

        @Bean
        public OrderStore orderStore() {
            return new OrderStore();
        }

        @Bean
        public ProjectionStore projectionStore() {
            return new ProjectionStore();
        }

        @Bean
        public OrderService orderService(
                TenantAuthorizer authorizer,
                OrderStore orders,
                ProjectionStore projections,
                ApplicationEventPublisher publisher) {
            return new OrderService(
                    authorizer, orders, projections, publisher);
        }

        @Bean
        public OrderProjectionListener projectionListener(
                OrderStore orders,
                ProjectionStore projections) {
            return new OrderProjectionListener(orders, projections);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderService service = context.getBean(OrderService.class);
            ProjectionStore projections =
                    context.getBean(ProjectionStore.class);
            OrderProjectionListener listener =
                    context.getBean(OrderProjectionListener.class);

            Instant time = Instant.parse("2026-11-01T08:00:00Z");

            // Two tenants own two independent ORDER-7 records.
            service.create(
                    "alice", "tenant-a", "ORDER-7", "evt-A", time);
            service.create(
                    "bob", "tenant-b", "ORDER-7", "evt-B", time);

            boolean crossTenantReadDenied = false;
            try {
                service.readProjection(
                        "alice", "tenant-b", "ORDER-7");
            } catch (SecurityException expected) {
                crossTenantReadDenied = true;
            }

            boolean unauthorizedCreateDenied = false;
            try {
                service.create(
                        "alice", "tenant-b", "ORDER-8",
                        "evt-forbidden", time);
            } catch (SecurityException expected) {
                unauthorizedCreateDenied = true;
            }

            boolean forgedEventRejected = false;
            try {
                // Change tenant, keep A's eventId -> invalid for B.
                context.publishEvent(new OrderCreated(
                        "evt-A", "tenant-b", "ORDER-7", time));
            } catch (SecurityException expected) {
                forgedEventRejected = true;
            }

            System.out.println("A event="
                    + service.readProjection(
                            "alice", "tenant-a", "ORDER-7"));
            System.out.println("B event="
                    + service.readProjection(
                            "bob", "tenant-b", "ORDER-7"));
            System.out.println("Cross-tenant read denied="
                    + crossTenantReadDenied);
            System.out.println("Unauthorized create denied="
                    + unauthorizedCreateDenied);
            System.out.println("Forged event rejected="
                    + forgedEventRejected);
            System.out.println("Projection rows="
                    + projections.rowCount());
            System.out.println("Rejected events="
                    + listener.rejectedCount());
        }
    }
}
```

### 8.4. Run Command

Open a terminal in the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Seven lines printed by the program**, excluding Maven or Spring logs:

```text
A event=evt-A
B event=evt-B
Cross-tenant read denied=true
Unauthorized create denied=true
Forged event rejected=true
Projection rows=2
Rejected events=1
```

**Line-by-line explanation:**

1. Tenant A has `OrderKey("tenant-a","ORDER-7")` associated with `evt-A`.
2. Tenant B has `OrderKey("tenant-b","ORDER-7")` associated with `evt-B`. The two keys do not collide even though `orderId` is identical.
3. `alice` lacks membership in `tenant-b`, so the service rejects querying tenant B before inspecting projections.
4. Attempting to create `ORDER-8` for tenant B under `alice`'s identity is rejected before writing to the store or publishing an event.
5. A forged event carrying `tenant-b/ORDER-7` with `eventId="evt-A"` fails because the authoritative record for that key is `evt-B`. The listener rejects it and does not write a projection from the forged event.
6. The projection store has exactly two entries after the valid operations.
7. The listener recorded one rejected event.

**Characteristics of the example:**

- Record `OrderCreated` is a POJO; Spring publishes it directly via `publishEvent(Object)` and routes it to `@EventListener`.
- The default multicaster runs **synchronously**, so the listener's `SecurityException` can propagate back to `publishEvent(...)` and be caught in `main` in this example.
- `ConcurrentHashMap` protects simple operations inside one JVM, yet it **is not a multi-tenant database**, has no transactions, and offers no durability or isolation across replicas.
- The fixed `eventId` values are only to make output deterministic; production must allocate unique IDs that remain stable on retries.
- Matching `eventId` against `OrderStore` is an **internal consistency check for the demo**, not producer signature verification; for external events, you must verify source identity and message integrity.
- If a synchronous listener fails after `orderStore.create(...)` has already written, the example **does not roll back** the in-memory record. Production uses transactions/outbox and explicit error policies.
- `ProjectionStore.get(...)` is kept at a simple storage layer; **only public service endpoints enforce membership checks**. In a real system, every significant access path must be scoped/authorized so no arbitrary bean or endpoint can bypass the service.

### 8.5. Why Not Use a ThreadLocal Tenant in the Example?

Each event already carries its verified `tenantId`. The listener builds `OrderKey(event.tenantId(), event.orderId())` to select the right data. Consequently, the logic does not depend on whether the listener runs on a request thread or an executor worker.

When using `@Async`, essential business information remains inside the **immutable event payload**. Propagating `SecurityContext` to a worker may be necessary in some designs, yet that is a separate decision and cannot replace checking event provenance/authorization.

## 9. Crossing Threads: @Async, ThreadLocal, and SecurityContext

An asynchronous listener can be declared as:

```java
@Async("tenantEventExecutor")
@EventListener
public void onCreated(OrderCreated event) {
    tenantScopedProjectionService.apply(
            event.tenantId(), event.orderId(), event.eventId());
}
```

This is an **integration snippet**, requiring `@EnableAsync`, a `tenantEventExecutor` bean, and a service that performs trusted validation. It is not part of the synchronous demo in section 8.

### Issues with ThreadLocal

A custom `TenantContext` often uses `ThreadLocal<String>`. When an event is submitted to a thread pool, the worker does not automatically hold the publisher's tenant. A dangerous example:

```java
@Async
@EventListener
public void onOrder(OrderCreated event) {
    String tenant = TenantContext.getTenant();
    repository.updateStatus(tenant, event.orderId());
}
```

This is a **counterexample**. The tenant can be null or wrong when workers are reused. When processing business events, prefer a verified `event.tenantId()` and repositories that require a tenant key.

### When a Scoped Tenant Context Is Mandatory

Some ORMs/schema-routers or libraries require a thread-bound context. In that case, create a scope with `try/finally`:

```java
String previous = TenantContext.getTenant();
try {
    TenantContext.setTenant(validatedEventTenant);
    executeTenantScopedWork();
} finally {
    if (previous == null) {
        TenantContext.clear();
    } else {
        TenantContext.setTenant(previous);
    }
}
```

This is an illustrative snippet; `validatedEventTenant` must already be **verified** from a trusted source, never taken raw from an untrusted payload. Order matters: **validate first, set tenant context second**. Failing to restore in `finally` can leave the worker holding an old tenant and leak data across tasks.

**Do not copy the entire `SecurityContextHolder` or transaction context with an arbitrary MDC `TaskDecorator` and assume permissions come with it.** MDC is only for logging. Spring Security provides `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextAsyncTaskExecutor` to propagate security context per task when needed. Still, **propagation does not equal fresh authorization**; policy must verify actor/producer permissions at the trust boundary.

### Which Contexts Need to Propagate?

| Context | Role | Is It Proof of Tenant Permission? |
| --- | --- | --- |
| `event.tenantId()` | Tenant data routing inside the payload | No; source must be verified |
| Spring `SecurityContext` | Holds `Authentication` per security stack strategy | Only valid when auth/authorization is sound |
| MDC `tenantId` | Enriches logs | No |
| Custom `TenantContext` | Scoped routing for thread/ORM | No, unless validated beforehand |
| Transaction context | Connection/commit/rollback on the thread | No; does not propagate automatically across `@Async` |
| Correlation/trace IDs | Workflow tracing | No |

For background tasks launched much later, the request principal may have expired or tenant permissions may have changed. Consider **service identity + current scoped authorization** rather than keeping a live `Authentication` object from an old request.

## 10. Handling Events from Brokers and Inter-Service Boundaries

A Spring bean receiving a message from Kafka/RabbitMQ can forward the object into `ApplicationEventPublisher.publishEvent(...)`. However, an event from a broker **does not automatically become trusted** simply because it enters the Spring context afterward.

Safe pipeline:

```text
Broker message
    |
    +--> authenticate producer / verify topic ACL or signature
    +--> validate schema + required IDs
    +--> authorize producer for tenantId
    +--> resolve trusted tenant / aggregate metadata
    +--> publish validated internal event
    |
    v
Tenant-aware consumer
    +--> tenant-scoped repository / cache / outbox
```

An adapter should verify:

- Is the **producer** a service permitted to publish this event type?
- Is the producer authorized to publish events for the tenant named in the message?
- Is the message a valid replay or does it show signs of forgery/tampering?
- Is `eventId` stable, and is the schema/version supported?
- Which tenant does the aggregate identifier belong to in an authoritative data source?
- Does it violate any privacy policies regarding PII or retention limits?

Do not treat a broker partition/topic name as the sole proof of permission if ACLs and routing are uncontrolled. Likewise, do not read the tenant from a message header that an untrusted producer can overwrite and blindly open that tenant's schema/database.

### Legitimate Cross-Tenant Workflows

An administrative workflow may **intentionally** touch multiple tenants—for example, aggregating billing for the service operator or performing a controlled data migration. Never use an unrestricted bypass named "admin" without auditing.

The design should explicitly document:

- Acting principal: service identity or staff member with a granted role.
- Source tenant and target tenant scope.
- Permissions/consent required for the operation.
- Purpose and audit record.
- Which fields are allowed to be copied; sensitive data must be minimized.
- Rollback/compensation steps if cross-tenant data transfer fails.

Separate it into a command/workflow with explicit authorization, rather than silently letting tenant A's listener write into tenant B.

## 11. Tenant Isolation in Transactions and Outboxes

A listener using `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is invoked after the publishing transaction commits; however, the annotation **does not check tenant boundaries or guarantee durable processing**.

Integration example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderCreated event) {
    tenantAwareOutboxService.schedule(
            event.tenantId(), event.eventId(), event.orderId());
}
```

This is a snippet; `tenantAwareOutboxService` must verify provenance and write to the outbox in an appropriate **new transaction** during an after-commit callback. Do not reuse an already-committed transaction context expecting additional writes to commit again automatically.

**Event-loss window:** if the process crashes after the business commit but before the `AFTER_COMMIT` callback runs, follow-up work can be lost. If zero event loss is required, write the **event outbox record in the same business transaction** as the order data.

Suggested schema:

```sql
CREATE TABLE event_outbox (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    payload_json    CLOB NOT NULL,
    status          VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
```

This is an illustrative schema; `CLOB` types and specific indexes must be tailored to your database. Uniqueness on `(tenant_id,event_id)` fits when IDs are unique per tenant; if `eventId` is globally unique, an additional constraint may apply.

Outbox workers must keep the tenant in task metadata and fetch only records belonging to the right tenant. If a worker uses a connection with schema-per-tenant, it must select the schema **before querying**, never letting the pool reuse a previous tenant's schema.

### Idempotency in Multi-Tenant Environments

A processed-markers table:

```sql
CREATE TABLE processed_events (
    tenant_id      VARCHAR(80) NOT NULL,
    consumer_name  VARCHAR(80) NOT NULL,
    event_id       VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
```

This key prevents the same consumer from reprocessing an event occurrence within a tenant, **without blocking a valid event that shares the same local ID in another tenant**. Still, if a malicious event swaps `tenantId` while keeping `eventId`, the marker does not automatically detect forgery; provenance and permission checks at the input remain essential.

For payment transfers/invoicing, **business uniqueness** such as `(tenant_id,payment_id,invoice_type)` is also required. Delivery deduplication and business uniqueness are two separate contracts.

## 12. Caches, Object Storage, and Read Models Must Separate Tenants

Tenant isolation does not stop at SQL.

### Cache Keys

Counterexample:

```java
cache.get("ORDER-7");
```

If the same key is used for tenants A and B, the cache can return the wrong tenant's data. A better key:

```text
orders:tenant-a:ORDER-7
orders:tenant-b:ORDER-7
```

Use a stable key format with proper escaping/hashing to avoid collisions if `tenantId` or `orderId` contains delimiters. For Redis or shared caches, establish policies for tenant namespaces, TTLs, cache invalidation, and restricted access.

### Object Storage

If a listener generates a PDF file:

```text
receipts/tenant-a/PAY-42.pdf
receipts/tenant-b/PAY-42.pdf
```

Path prefixes organize data but **do not provide ACLs by themselves**. Bucket/object permissions, presigned URLs, tenant authorization, and URL expiration still need enforcement. Never rely on hard-to-guess path names instead of authentication.

### Search Indexes and Analytics

Events may update Elasticsearch/OpenSearch, read models, or analytics systems. When querying/searching an index, a tenant filter is mandatory if multiple tenants share an index. Never apply the filter only in the UI while the backend API returns data across all tenants.

If events sent to metrics/analytics contain cross-tenant aggregates, establish policies on what may be aggregated, anonymization levels, retention, and dashboard viewing permissions.

## 13. Logging, Tracing, and Sensitive Information

An event-driven pipeline can log:

```text
tenantId
eventId
eventType
aggregateId / orderId
correlationId
causationId
handlerName
processingAttempt
processingStatus
instanceId
```

Safer log example:

```text
tenant=tenant-a event=evt-A type=OrderCreated
handler=projection status=SUCCESS aggregate=ORDER-7
```

Do not log full payloads containing card details, emails, tokens, or secrets. Even when a log shows the right `tenantId`, it does not prove the repository query actually filtered by tenant. Logging must be paired with tests and monitoring at the data layer.

In systems using SLF4J MDC, you can populate MDC from a **verified tenant** within the listener scope:

```java
String previous = MDC.get("tenantId");
try {
    MDC.put("tenantId", trustedTenantId);
    processEvent();
} finally {
    if (previous == null) {
        MDC.remove("tenantId");
    } else {
        MDC.put("tenantId", previous);
    }
}
```

This is an integration snippet; use it only after determining `trustedTenantId` from a trusted source. Never read tenant context from logs and treat it as proof of authorization. For async processing, scope/clean up on the actual worker thread; never let tenant A's MDC persist when the worker moves to event B.

### Tenant IDs Can Also Be Sensitive

In some systems, `tenantId` is the organization's name or an internal code that could reveal customer relationships. Do not assume every tenant identifier can appear in public logs or URLs. You can use pseudonymous identifiers and restrict access logs and retention by policy.

## 14. Resource Isolation and Preventing "Noisy Neighbors"

Even when data is never mixed, one tenant can degrade service for others by flooding events:

```text
tenant-a -> 50,000 events -> shared executor queue full
tenant-b -> 10 events     -> waits very long / gets rejected
```

This is an **availability isolation** problem, not just confidentiality. Consider:

- Per-tenant or per-actor incoming event quotas / rate limits.
- Partitioned queues by tenant/service tier when fairness must be guaranteed.
- Bounded queues and backpressure instead of unbounded queues.
- Per-tenant retry/backoff; do not let one failing tenant loop and jam the entire pool.
- Per-tenant metrics for backlog, oldest event, latency, and rejected count.
- Classifying tenant workloads (small/large/special) and fair scheduling.
- Circuit breakers or isolated pools for resource-heavy tasks if needed.

However, **thread-per-tenant** or **executor-per-tenant** also carries overhead and risk of resource exhaustion when tenant count is high. Measure before adopting strict partitioning.

## 15. Event Replay, Retries, and Tenant Identity

When replaying an event from an outbox/event store:

- Preserve the stored `eventId` and `tenantId` of the occurrence.
- Do not take the current tenant from an active request or from a leftover worker `ThreadLocal`.
- Verify the stored record has a trusted source/integrity.
- Use `(tenantId, consumer, eventId)` for idempotency if `eventId` is only unique within a tenant.
- When rebuilding a read model, do not automatically send emails/HTTP calls or trigger external side effects for all historical events.
- If a tenant has been deleted, suspended, or lost processing rights under new policy, define explicit replay/retention policies instead of blindly processing old events.
- For administrative cross-tenant replays, use dedicated audited privileges rather than impersonating each tenant's security context.

### Do Not Treat tenantId in a Payload as an All-Access Pass

A replayed payload might contain `tenantId = tenant-b`. If the message store was tampered with or a producer forged a message, a worker trusting this field and querying database B is a vulnerability. Verify the message source or cross-check aggregate/tenant against authoritative data, especially for sensitive effects.

The section 8 example checks the `OrderKey + eventId` pair against `OrderStore`. That is a useful sanity check, yet it **does not replace true producer authentication** once data crosses application boundaries.

## 16. Systematic Tenant Isolation Testing

A test suite should include both **positive tests** and **negative tests**:

| Scenario | Expected Outcome |
| --- | --- |
| Alice creates order A | Only tenant A gets the record and projection |
| Bob creates order B with same `ORDER-7` | Tenant B gets its own record without overwriting A |
| Alice reads projection B | Rejected before reading |
| Alice tries to create a record for B | Rejected; no new event or record |
| Event changes `tenantId` but keeps A's `eventId` | Listener rejects because it does not match B's authoritative source |
| Event has blank or null ID/tenant | Constructor/validator rejects |
| Replay valid event of A | Does not alter B's data; effect is idempotent per policy |
| Event A processed via `@Async` | Does not depend on stale/null `ThreadLocal` |
| Worker processes A then B on the same thread | No tenant context leaks between tasks |
| Repository query/update | Every path includes a tenant predicate or DB policy |
| Outbox write, processed marker | Keys include tenant; transaction and retry preserve tenant |
| Two tenants have the same payment/order ID | No collision in cache, DB, or object paths |
| Consumer from broker receives forged `tenantId` | Blocked at authentication/authorization boundary |
| Admin permitted for cross-tenant operation | Explicit permission, audit log, and clear scope |
| One tenant floods events | Quota/fairness/backpressure prevents starving B |

### 16.1. Tests Should Not Only Call the Listener Directly

If you only call:

```java
listener.onCreated(
        new OrderCreated("evt-A", "tenant-a", "ORDER-7", time));
```

that test can verify handler logic, yet it **does not prove** Spring routes events correctly. An integration test should boot the context, call `publishEvent(...)` via the real service, and assert projections, like the section 8 example.

You can use Spring TestContext's `@RecordApplicationEvents` to capture events in tests:

```java
@SpringJUnitConfig(Config.class)
@RecordApplicationEvents
class TenantEventTests {
    @Autowired OrderService service;

    @Test
    void publishesOnlyAuthorizedTenant(ApplicationEvents events) {
        events.clear();
        service.create(
                "alice", "tenant-a", "ORDER-7",
                "evt-A", Instant.parse("2026-11-01T08:00:00Z"));

        List<OrderCreated> actual =
                events.stream(OrderCreated.class).toList();

        assertEquals(1, actual.size());
        assertEquals("tenant-a", actual.get(0).tenantId());
    }
}
```

This is an **integration test snippet**, not a complete test file, since it requires test fixtures, imports, and the `Config` bean setup from section 8. In test suites using Spring TestContext, ensure test setup does not accumulate state across tests sharing a context; do not insert the same key into a singleton store when a previous test has already run. Tests should use clean fixtures or isolated contexts.

### 16.2. Negative Tests Must Verify No Side Effects Occurred

When an invalid request is rejected, do not merely assert a `SecurityException`. Assert that:

- No order was created in the target tenant.
- No valid event was published for the target tenant.
- No outbox row or notification job was created.
- No cache entry or projection of another tenant was modified.
- Audits record the denied attempt without leaking confidential record contents.

A forged event might be rejected by one listener **after** another listener has already executed if the multicaster has multiple subscribers. Therefore, for untrusted messages, checking at the adapter **before publishing** remains critical; one defensive listener does not guarantee all other subscribers are safe.

### 16.3. Testing Async with a Single Reused Worker

With a single-worker pool, submit event A, event B, and then an event with a missing/invalid tenant. Use latches/futures with timeouts to wait rather than `Thread.sleep(100)` before asserting. If using a scoped `TenantContext`, every task must clean up via `finally`; task B must never observe tenant A.

For tenant routing, tests must verify that **database/queries** use the right tenant, not merely that MDC logs print the right tenant.

### 16.4. Testing Real Database Isolation

If using shared tables, integration tests must verify the same `orderId` in two tenants and queries scoped to the right tenant; add tests for tenant-filtered updates/deletes. If using schema-per-tenant, intentionally reuse connections to confirm the schema resets/routes properly. If using RLS, test under the **actual database role** used by the application; superuser/owner accounts can yield misleading results.

## 17. Common Mistakes

1. **Adding `tenantId` to an event and considering it safe.** A field is not proof that the producer is allowed to pick that tenant.
2. **Trusting `X-Tenant-Id` or JSON body unconditionally.** Clients can tamper with the tenant field.
3. **Reading tenant from MDC for DB queries.** MDC is for logging, not authorization.
4. **Reading `TenantContext` `ThreadLocal` inside an async listener.** The worker does not automatically carry the publisher's context.
5. **Failing to clear/restore `TenantContext` after a task.** Tenant B's worker can reuse leftover tenant A.
6. **Querying entities by `orderId` alone when IDs are tenant-unique.** Easy to read or modify the wrong tenant's record.
7. **Cache keys without tenant.** Two tenants can share `ORDER-7`.
8. **Object storage keys include tenant, but bucket ACLs are unrestricted.** Prefixes do not replace authorization.
9. **Using `SecurityContextHolder.getContext()` without verifying principal/membership.** Merely having a context object does not prove rights.
10. **Putting whole `Authentication` or `HttpServletRequest` objects into events.** Risks carrying expired/mutable state or sensitive info.
11. **Trusting a broker `tenantId` header without verifying the producer.** Forged messages can route to another tenant.
12. **Using Spring event `getSource()` as tenant identity.** Source carries no authorization contract.
13. **Creating derived events that drop `tenantId` or replace it with the current thread's tenant.** Breaks workflow provenance.
14. **Writing outboxes without tenant and with overly broad dedupe keys.** `eventId` can collide per tenant or effects can mix.
15. **Putting sensitive data in payloads and logging `toString()`.** Can expose PII/secrets.
16. **Using a DB account that bypasses all RLS while believing RLS protects you.** Test with the real role/configuration.
17. **Validating in only one listener while letting untrusted messages reach all subscribers.** Other listeners can still be exploited.
18. **Assuming `@Async` or `@TransactionalEventListener` adds security.** Annotations control timing/threads, not tenant checks.
19. **Believing the original transaction follows across workers.** It does not by default; a properly scoped new transaction is needed.
20. **Ignoring event replay when a tenant is suspended or deleted.** Operational and legal policies can change.
21. **Using global admin privileges for all background tasks.** A wrong-tenant event could gain write access everywhere.
22. **Not testing two tenants with the same ID.** Tests using globally unique IDs miss missing tenant predicates.
23. **Not limiting load per tenant.** One tenant can saturate shared queues/workers.
24. **Confusing logging context with tenant authorization.** Having the right `tenantId` in logs does not prove the event was processed for the right tenant.

## 18. Production Readiness Checklist

- [ ] Every sensitive event explicitly includes `tenantId`, `eventId`, and aggregate ID.
- [ ] Tenant is determined from an authenticated principal/claims and active membership/roles.
- [ ] Request headers/bodies naming a tenant are never trusted before checking permissions.
- [ ] Events from brokers/external APIs have producer authentication and validation before internal publishing.
- [ ] Listeners verify data/tenant provenance on sensitive actions rather than trusting only the payload's tenant name.
- [ ] DB queries and updates enforce tenant predicates or tested ORM/RLS policies.
- [ ] Unique/foreign keys match tenant scope; avoid assuming `orderId` is globally unique.
- [ ] Caches, object storage, search indexes, and read models enforce tenant namespaces/filters.
- [ ] Events are immutable and carry no mutable entities, requests, tokens, or unnecessary secrets.
- [ ] Async listeners do not depend on missing or stale `ThreadLocal`; scoped contexts always restore in `finally`.
- [ ] MDC/traceId are used for observability, never for granting permissions.
- [ ] Transactions, outboxes, and idempotency preserve the tenant across retries/replays.
- [ ] Consumer side effects guarantee no cross-tenant writes, even when events are replayed.
- [ ] Cross-tenant admin workflows have explicit permissions and auditing.
- [ ] Tests cover read/write/rollback and two tenants sharing the same ID.
- [ ] Tests cover forged events, missing tenant, tenant mismatch, and worker reuse.
- [ ] Metrics/alerts track rejected events, tenant mismatches, backlogs, and per-tenant quotas.
- [ ] Logging and event storage comply with data minimization and retention requirements.

**Remember:** tenant isolation in Spring Application Events does not reside in a single annotation. You must **authenticate and authorize the tenant at entry**, carry the verified tenant in an **immutable event payload**, **verify provenance** before side effects, use **tenant-scoped** keys/queries across every store, and properly manage transactions, thread contexts, retries, and outboxes. A `tenantId` inside an event is vital routing information—**it is not by itself proof of access rights**.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Hibernate ORM — Multi-tenancy and tenant identifier resolution](https://docs.hibernate.org/orm/6.4/userguide/html_single/Hibernate_User_Guide.html#multitenacy)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
