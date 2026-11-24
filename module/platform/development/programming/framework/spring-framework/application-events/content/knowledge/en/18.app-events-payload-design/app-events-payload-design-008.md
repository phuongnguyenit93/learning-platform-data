# Actor, Tenant, and Context Information in Spring Application Events Payloads

## 1. Lesson Objectives

A domain event should not only state **what happened**, but often also needs to answer **who performed it**, **which tenant the fact belongs to**, **from which operation or processing flow**, and **when the event occurred**. This information helps consumers process the right data, diagnose incidents, build audit trails, and maintain isolation boundaries in multi-tenant systems.

Example of a business fact:

```text
InvoiceApproved
  invoiceId      = INV-7
  tenantId       = tenant-blue
  actor          = HUMAN:user-42
  correlationId  = REQ-9
  eventId        = <occurrence-specific UUID>
  occurredAt     = <approval timestamp>
```

**Meaning:** invoice `INV-7` of `tenant-blue` was approved by user identity `user-42` inside processing flow `REQ-9`. `tenantId` and `actor` are not substitutes for authorization checks: they are metadata describing the fact **after** the system has authenticated and authorized the operation.

This lesson focuses on designing **domain event payloads**, particularly when Spring Framework dispatches events via `ApplicationEventPublisher` and `@EventListener`. The principles are also useful when a domain event is translated into an integration event, though sending over a broker requires separate reliability and security contracts.

**Key principle:** context data inside an event must be **a minimal, authenticated snapshot appropriate to the domain at the time the fact occurred**. Never place raw HTTP requests, `SecurityContext`, access tokens, sessions, or mutable entities inside events.

## 2. Distinguishing Four Easily Confused Questions

| Attribute | Question | Example | What It Does Not Guarantee |
| --- | --- | --- | --- |
| `actor` | Who/what performed or initiated the action? | `HUMAN:user-42` | Does not by itself prove that identity was authorized |
| `tenantId` | Which tenant scope does this data/fact belong to? | `tenant-blue` | Does not replace tenant filtering when reading/writing the DB |
| `correlationId` | Which steps belong to the same logical flow? | `REQ-9` | Not authentication data or an authorization constraint |
| `eventId` | Which specific occurrence of the event is this? | UUID | Does not by itself provide exactly-once delivery |
| `causationId` | Which command/event directly led to this fact? | `CMD-123` or event ID | Does not automatically enforce guaranteed processing order |
| `occurredAt` | When did the business fact happen? | UTC Instant | Not necessarily equal to when the listener processes it |

Not every event needs **every** field; choose a clear contract per requirements. However, in multi-tenant system events, omitting tenant identity when tenant scoping is required can cause wrong-tenant data processing. Conversely, for genuinely system-wide events, never fabricate `tenantId="default"` just to satisfy a schema.

### Actor Differs from Target Resource Owner

In the operation "support agent locks a customer's account":

- `actor`: the support agent who performed the action.
- `subject` or `targetUserId`: the customer whose account was locked.
- `tenantId`: the tenant owning the account, or the affected tenant per policy.
- `initiator`/`onBehalfOf`: may be needed if the action was delegated or a service acted on a user's behalf.

Never set `actorId = targetUserId` merely because both are user IDs. For sensitive audit events, mixing up actor and subject produces an inaccurate action history.

## 3. Actor: Designing the Identity Performing the Action

The actor is the identity the domain uses to assign accountability or describe the source of an action. An actor does not always have to be a logged-in human user.

Common kinds:

| Actor Kind | Example | Representation |
| --- | --- | --- |
| Authenticated user | Staff member `user-42` approves an invoice | `HUMAN:user-42` |
| Internal service | Billing service runs auto-reconciliation | `SERVICE:billing-service` |
| Scheduled/system process | Subscription expiration job | `SYSTEM:renewal-scheduler` |
| Authenticated partner | Webhook from payment provider | `SERVICE:payment-provider-a` or a domain-specific actor kind |
| Delegated action | Agent acting on behalf of a user | `actor` and `onBehalfOf` clearly separated |

Do not assume every job without an HTTP request is "anonymous". A scheduled job has a system identity; a service-to-service call needs a verified service identity. If the domain genuinely has anonymous actors, model a dedicated kind per policy instead of using blank strings or `null` and leaving consumers to guess.

### 3.1. Use Meaningful Types, Not Ambiguous Strings

A Java 17 pattern:

```java
public enum ActorKind {
    HUMAN, SERVICE, SYSTEM
}

public record ActorRef(ActorKind kind, String id) {
    public ActorRef {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("actor id is blank");
        }
    }
}
```

This is an illustrative declaration snippet; it requires importing `java.util.Objects`. The `kind/id` pair prevents confusing `user-42` with a service that happens to share the same ID string.

If using an identity system with multiple realms, consider adding `issuer` or `identityProviderId`. For example, two tenants sharing the local username `alice` does not mean they are the same person. In integrated systems, the identifier should be a **stable ID**, not a display email or mutable username.

### 3.2. Actor Should Be Resolved at the Trust Boundary

In applications using Spring Security, authenticated user details are typically accessed via `SecurityContextHolder` or a principal supplied to the controller by security integration. However:

- Do not take `actorId` directly from an HTTP body if the action requires authentication.
- Do not treat an arbitrary `X-Actor-Id` header as truth simply because the client sent it.
- Do not copy the entire `Authentication`/`principal` into the event: it may contain credentials, authorities, sessions, and hard-to-serialize structures.
- Do not use `authentication.getName()` as a durable ID when that name is merely a mutable username/email.
- Distinguish **authentication** (who the caller is) from **authorization** (whether they are allowed to act on this resource).

Illustrative example at the web/security layer **with Spring Security**, not part of the standalone project in section 9:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null || !authentication.isAuthenticated()
        || authentication instanceof AnonymousAuthenticationToken) {
    throw new AccessDeniedException("Authentication required");
}

// Resolve stable actor identity via trusted principal mapping.
// Verify authorization for the target resource before publishing.
// Do not put Authentication or credentials into the event.
```

These types belong to Spring Security and require matching imports/dependencies. Username, principal type, and anonymous checks depend on the authentication mechanism; the snippet above only illustrates the **authentication boundary**, not a copy-paste recipe for every security setup.

### 3.3. Assigning Accountability for Automated Actions

Suppose a user schedules a recurring job, and the next day the job automatically emits `SubscriptionRenewed`. The direct actor of the renewal may be `SYSTEM:renewal-scheduler`, while the user who configured the job is `initiatedByUserId` or `onBehalfOf` per contract. Using only `userId` as the actor can obscure the fact that the system itself executed the run.

When auditing needs to distinguish:

```text
actor: SYSTEM:renewal-scheduler
onBehalfOf: HUMAN:user-42
causedBy: recurring-plan-7
```

These fields should exist only when the domain has clear semantic rules for them. Never imply the user clicked a button at the exact moment the scheduler ran.

## 4. Tenant: Data Ownership and Multi-Customer Isolation

In a multi-tenant architecture, `tenantId` typically represents the **data ownership boundary** or business scope the event belongs to. It is essential for:

- Data partitioning and selecting namespaces/schemas.
- Determining whether a consumer is authorized to process or store the event.
- Per-tenant auditing, metrics, and **incident support**.
- Idempotency, correlation, and routing when multiple tenants share infrastructure.
- Ensuring tenant A's data is never sent to tenant B's sink.

**Do not use `tenantId` inside an event as proof that the consumer is authorized to access that tenant's data.** Producers can have bugs, events can be spoofed at external boundaries, or a shared listener might be processing from the wrong source.

### 4.1. Resource Tenant Differs from "Current Request Tenant"

Suppose a UI allows switching the active tenant, while the operation targets invoice `INV-7`. The true tenant must be **verified against the invoice** and the actor's permissions, not blindly copied from a browser-sent `X-Tenant-Id` header.

Correct flow:

```text
Authenticated principal
    + requested invoice ID
           |
           v
  Resolve invoice -> canonical tenant owner
           |
           v
  Check actor permission inside that tenant
           |
           +-- DENIED --> Do not publish InvoiceApproved
           |
           +-- ALLOWED --> Execute approval
                             |
                             v
                   Publish InvoiceApproved {
                     tenantId = canonical owner,
                     actor = authenticated identity,
                     ...
                   }
```

A system using a tenant claim inside a verified token still needs to verify the target resource and required roles/permissions. "Logged into tenant-blue" does not automatically prove the actor is authorized to approve **every** invoice in tenant-blue.

### 4.2. Tenant ID Must Have a Clear Scope and Format

You can use a UUID or a stable opaque ID, kept consistent system-wide. Clarify:

- Is the tenant ID globally unique or unique only within a region?
- Is there a separate namespace/issuer per tenant provider?
- Can tenants be merged, split, or migrated across clusters?
- Can one entity be owned by multiple tenants?
- Are there system-wide events that do not require a tenant?

For global events, consider a distinct event type/metadata, e.g., `GlobalTaxPolicyPublished` without a tenant. **Do not** insert a fake tenant to pass validation, as consumers may route it into the wrong partition.

### 4.3. Do Not Rely on ThreadLocal as the Primary Tenant Source in Listeners

Some applications use a `ThreadLocal`-based `TenantContextHolder` for datasource routing. When an event listener executes asynchronously, the worker thread **does not automatically inherit** the publisher thread's tenant context.

Worse, thread pools reuse workers. If code sets a tenant into ThreadLocal and forgets to clean up in `finally`, the next task may observe the previous tenant:

```java
// Illustrative pattern in an application with TenantContextHolder.
String previous = TenantContextHolder.getTenantId();
try {
    TenantContextHolder.setTenantId(event.context().tenantId());
    processInTenantScope(event);
} finally {
    if (previous == null) {
        TenantContextHolder.clear();
    } else {
        TenantContextHolder.setTenantId(previous);
    }
}
```

This is **not standalone runnable code**: `TenantContextHolder` and `processInTenantScope` are application-defined. Before setting tenant context from an event, first **verify the event source and tenant authorization** at the trust boundary. Restoring the previous context is merely thread hygiene; it does **not** replace authorization and must not let untrusted events pick arbitrary tenants.

Prefer passing the tenant explicitly in handler methods or queries, for example:

```java
invoiceRepository.findByIdAndTenantId(invoiceId, tenantId);
```

The method above is an **illustrative repository API**, not built into Spring by default. Tenant-scoped queries reduce mix-ups across thread hops. Even with Row Level Security, set the right session/database role and test against cross-tenant data leaks.

## 5. Context: Correlation, Causation, Trace, and Timing

Not all metadata is the same kind of "context". Define each field by a dedicated question rather than making consumers depend on a catch-all `Map<String, Object>`.

### 5.1. Event ID

`eventId` identifies **one specific occurrence** of a fact. Two invoices approved simultaneously must have distinct event IDs; the same event retried/replayed through a broker **should keep its original ID** so consumers can deduplicate, depending on the delivery protocol.

`UUID.randomUUID()` is one option for IDs, though systems may choose ULID, UUIDv7, or another identifier. What matters is consistent uniqueness and ID usage conventions.

Note: sharing the same actor, tenant, and correlation ID **does not mean** it is the same event. One request can produce multiple distinct facts.

### 5.2. Correlation ID

`correlationId` connects steps belonging to one logical journey:

```text
HTTP request (correlationId=REQ-9)
      |
      +--> InvoiceApproved (eventId=E1, correlationId=REQ-9)
      |
      +--> AuditRecorded (eventId=E2, correlationId=REQ-9)
      |
      +--> NotificationRequested (eventId=E3, correlationId=REQ-9)
```

Correlation ID is an **observability key**. Do not use it as an auth token, session ID, or tenant boundary. If a client supplies a correlation ID, validate its format/length or issue a trusted ID at ingress; never let arbitrary strings break logs, headers, or metric labels.

### 5.3. Causation ID

`causationId` records the **direct cause**, such as a command ID or preceding event:

```text
ApproveInvoiceCommand CMD-17
         |
         v
InvoiceApproved E-18 (causationId=CMD-17)
         |
         v
AuditRecorded E-19 (causationId=E-18)
```

Not every event needs a causation ID—for example, a simple internal action without a message envelope. If used, standardize ID sources (command, event, job) so you do not produce meaningless chains.

### 5.4. Trace ID / Span ID Differ from Correlation ID

In observability, `traceId` and `spanId` are usually managed by a tracing framework (e.g., OpenTelemetry) with their own formats and propagation rules. `correlationId` may be a business ID outliving a single trace, so the two concepts should not be treated as strictly identical.

- `traceId` can be recorded in event metadata when needed and access policies allow.
- Do not fabricate arbitrary span IDs if you expect distributed tracing compatibility.
- Never store PII, tokens, or tenant secrets in tracing baggage.
- Do not use high-cardinality raw tenant IDs as default metric labels on every event.

### 5.5. Occurred Time, Published Time, and Processed Time

| Timestamp | Meaning | Who Controls It? |
| --- | --- | --- |
| `occurredAt` | Time when the fact was confirmed to occur by the domain | Producer/domain |
| `publishedAt` | Time when the message was sent to transport, if any | Publisher/relay |
| `receivedAt` | Consumer received the event | Consumer |
| `processedAt` | Consumer finished processing | Consumer |

In internal Spring Application Events, an object creation timestamp is not necessarily the transaction commit timestamp, nor does it equal when an async listener runs.

Use UTC `Instant` or a standard format when persisting across systems rather than recording display-timezone times and forcing consumers to guess. If the domain needs a "business date" in the tenant's timezone, model business date/timezone separately—**do not** replace global `occurredAt` with an ambiguous local time.

## 6. Separating Event Metadata from Business Data

An event typically has two groups:

```text
InvoiceApproved {
  business:
    invoiceId
    approvalLevel
  metadata:
    eventId
    occurredAt
    tenantId
    actor
    correlationId
    causationId?      // if defined
}
```

This **does not force** every event to inherit a single base class or envelope. You can use:

1. An event record containing a metadata record, as in the runnable example in section 9.
2. An `EventEnvelope<T>` when shared transport or infrastructure genuinely needs it.
3. Explicit fields directly on each event if there are few events and it reads more clearly.

An overly generic base class can force `tenantId` onto every event—even global ones—or invite piles of optional fields. Choose abstractions based on **genuinely shared invariants**.

### Do Not Store Runtime Objects in Payloads

Fields **to avoid**:

- `HttpServletRequest`, `HttpSession`, Servlet context.
- `Authentication`, `SecurityContext`, access tokens, refresh tokens, cookies.
- `Thread`, `Executor`, `TransactionStatus`, JDBC connections.
- Lazy-loaded JPA entities, Hibernate sessions, or mutable domain aggregates.
- All request headers, entire MDC maps, or unfiltered arbitrary maps.
- Passwords, OTPs, API keys, secrets, raw payment card details.

The issue is not only serialization difficulty: the data can go stale by the time the consumer runs, carry over-privileged details, retain live resources too long, and create data-leak risks.

Instead, carry **stable IDs and minimal snapshots** fitting the contract—for example `ActorRef(HUMAN,"user-42")`, not a full `UserDetails` object packed with authorities and credentials.

## 7. Designing Immutable Java Records for Actor and Metadata

In Java 17, records enable clear payloads with auto-generated accessors. Pattern:

```java
public enum ActorKind { HUMAN, SERVICE, SYSTEM }

public record ActorRef(ActorKind kind, String id) {
    public ActorRef {
        Objects.requireNonNull(kind);
        Objects.requireNonNull(id);
        if (id.isBlank()) throw new IllegalArgumentException("blank actor id");
    }
}

public record EventMetadata(
        UUID eventId,
        Instant occurredAt,
        String tenantId,
        ActorRef actor,
        String correlationId) {
    public EventMetadata {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(actor);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(correlationId);
        if (tenantId.isBlank() || correlationId.isBlank()) {
            throw new IllegalArgumentException("blank context field");
        }
    }
}

public record InvoiceApproved(String invoiceId, EventMetadata metadata) {
    public InvoiceApproved {
        Objects.requireNonNull(invoiceId);
        Objects.requireNonNull(metadata);
        if (invoiceId.isBlank()) throw new IllegalArgumentException("blank id");
    }
}
```

This is an **illustrative declaration** snippet; it requires importing `java.util.Objects`, `java.util.UUID`, and `java.time.Instant`. The full application example in section 9 runs directly.

Place invariants at the proper layer:

- Null/blank checks, ID format, and string length limits belong in metadata constructors/validators.
- Checking whether **the actor has permission** to approve the tenant's invoice belongs in the application/domain service, where resource data and authorization policies live.
- Constructing `EventMetadata` does not prove the payload came from a trusted source. Any code with constructor access can build a record that is **structurally** valid yet forged in terms of **authority**.
- Records are *shallowly immutable*. If metadata contains a `Set`/`List`/`Map`, perform defensive copies (e.g., `Set.copyOf`) and avoid storing mutable objects returned by accessors.

### Do Not Reuse the Same ID for Event and Correlation

One correlation may contain dozens of events, while each event must have its own ID. Never set `eventId=correlationId` out of test convenience. If a producer receives a duplicate command and must not emit another fact, handle idempotency in business logic rather than "rotating UUIDs" every time.

## 8. Where Must Actor/Tenant Data Come From?

A trustworthy pipeline:

1. **Ingress:** verify caller identity, signatures/tokens, or service identity via security infrastructure.
2. **Application service:** identify the action and target resource; look up the resource's owning tenant from an authoritative data source.
3. **Authorization:** verify the actor's permissions **on that specific resource/tenant**, not merely that they are authenticated.
4. **Domain operation:** transition state once business conditions are satisfied.
5. **Event factory:** snapshot actor, tenant, `occurredAt`, correlation, and `eventId`; never copy secrets.
6. **Publish/commit:** publish the event at the appropriate transaction boundary and clarify what is durable.
7. **Consumer:** enforce trust boundaries per transport, process in the right tenant scope, and follow idempotency policies.

Visualized flow:

```text
Untrusted request:
  invoiceId, optional request correlation
           |
           v
Authentication -> TrustedIdentity(userId, memberships)
           |
           v
Load Invoice(id) -> canonical tenantId
           |
           v
Authorize actor for invoice + tenant
           |
           +--> Reject: no InvoiceApproved event
           |
           v
Apply approved state
           |
           v
InvoiceApproved {
  invoiceId,
  metadata(tenantId, ActorRef, correlationId, eventId, occurredAt)
}
           |
           v
@EventListener -> tenant-scoped consumer/audit
```

This prevents bugs where an actor from tenant A sends a request with `tenantId=B` and the system emits an event stamped with tenant B without checking the resource. When events arrive over a broker outside the trust perimeter, consumers must also verify transport/provenance per policy before using the payload's tenant for routing.

## 9. Runnable Example: Actor/Tenant Resolved Before Publishing the Event

This example uses **Java 17+**, **Spring Framework 6.2.12**, and Maven. It intentionally omits Spring Security, HTTP, and databases to focus on payload contracts and demonstrate **authorization before publication**:

- `TrustedIdentity` represents an **authenticated** identity from an upstream boundary (simulated only, not a complete authentication system).
- `InvoiceStore` holds the authoritative invoice → tenant mapping in application data.
- `InvoiceService` checks that the actor belongs to the tenant owning the invoice before approving and publishing `InvoiceApproved`.
- The listener receives immutable metadata without needing `ThreadLocal` or `SecurityContext`.
- Attempting to approve the same invoice from a user in another tenant is rejected before publishing any event.

### Structure

```text
event-context-demo/
├── pom.xml
└── src/main/java/demo/EventContextDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-context-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.EventContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/EventContextDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventContextDemo {

    public enum ActorKind { HUMAN, SERVICE, SYSTEM }

    public record ActorRef(ActorKind kind, String id) {
        public ActorRef {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) throw new IllegalArgumentException("blank actor id");
        }
    }

    public record TrustedIdentity(String userId, Set<String> tenantIds) {
        public TrustedIdentity {
            Objects.requireNonNull(userId, "userId");
            Objects.requireNonNull(tenantIds, "tenantIds");
            if (userId.isBlank()) throw new IllegalArgumentException("blank user");
            tenantIds = Set.copyOf(tenantIds);
        }
    }

    public record EventMetadata(
            UUID eventId,
            Instant occurredAt,
            String tenantId,
            ActorRef actor,
            String correlationId) {
        public EventMetadata {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(actor, "actor");
            Objects.requireNonNull(correlationId, "correlationId");
            if (tenantId.isBlank() || correlationId.isBlank()) {
                throw new IllegalArgumentException("blank event metadata");
            }
        }
    }

    public record InvoiceApproved(String invoiceId, EventMetadata metadata) {
        public InvoiceApproved {
            Objects.requireNonNull(invoiceId, "invoiceId");
            Objects.requireNonNull(metadata, "metadata");
            if (invoiceId.isBlank()) {
                throw new IllegalArgumentException("blank invoice id");
            }
        }
    }

    public static final class InvoiceStore {
        private static final class Invoice {
            final String tenantId;
            boolean approved;

            Invoice(String tenantId) {
                this.tenantId = tenantId;
            }
        }

        private final Map<String, Invoice> invoices = new HashMap<>();

        public InvoiceStore() {
            invoices.put("INV-7", new Invoice("tenant-blue"));
        }

        public synchronized String approve(
                String invoiceId, TrustedIdentity identity) {
            Invoice invoice = invoices.get(invoiceId);

            // Use a generic error message so resources of other tenants are not leaked.
            if (invoice == null
                    || !identity.tenantIds().contains(invoice.tenantId)) {
                throw new SecurityException("access denied");
            }
            if (invoice.approved) {
                throw new IllegalStateException("already approved");
            }

            invoice.approved = true;
            return invoice.tenantId;
        }
    }

    public static final class InvoiceService {
        private final InvoiceStore store;
        private final ApplicationEventPublisher publisher;

        public InvoiceService(
                InvoiceStore store, ApplicationEventPublisher publisher) {
            this.store = store;
            this.publisher = publisher;
        }

        public void approve(
                String invoiceId,
                TrustedIdentity identity,
                String correlationId) {

            // Tenant retrieved from the looked-up invoice and authorized.
            String tenantId = store.approve(invoiceId, identity);

            EventMetadata metadata = new EventMetadata(
                    UUID.randomUUID(),
                    Instant.now(),
                    tenantId,
                    new ActorRef(ActorKind.HUMAN, identity.userId()),
                    correlationId);

            publisher.publishEvent(new InvoiceApproved(invoiceId, metadata));
        }
    }

    public static final class AuditListener {
        @EventListener
        public void onInvoiceApproved(InvoiceApproved event) {
            EventMetadata m = event.metadata();
            System.out.println(
                    "APPROVED invoice=" + event.invoiceId()
                    + " tenant=" + m.tenantId()
                    + " actor=" + m.actor().id()
                    + " kind=" + m.actor().kind()
                    + " correlation=" + m.correlationId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InvoiceStore invoiceStore() {
            return new InvoiceStore();
        }

        @Bean
        InvoiceService invoiceService(
                InvoiceStore store, ApplicationEventPublisher publisher) {
            return new InvoiceService(store, publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            InvoiceService service = context.getBean(InvoiceService.class);

            service.approve(
                    "INV-7",
                    new TrustedIdentity("user-42", Set.of("tenant-blue")),
                    "REQ-9");

            try {
                service.approve(
                        "INV-7",
                        new TrustedIdentity("user-99", Set.of("tenant-red")),
                        "REQ-10");
            } catch (SecurityException denied) {
                System.out.println("DENIED " + denied.getMessage());
            }
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines explicitly printed by the program (excluding environment-dependent logs):

```text
APPROVED invoice=INV-7 tenant=tenant-blue actor=user-42 kind=HUMAN correlation=REQ-9
DENIED access denied
```

**Exact interpretation:**

1. Spring creates `AnnotationConfigApplicationContext` and registers `AuditListener.onInvoiceApproved` via `@EventListener`.
2. Simulated user `user-42` has membership in `tenant-blue`. `InvoiceStore` finds `INV-7` belongs to `tenant-blue`, permits the state transition, and returns the canonical tenant to the service.
3. The service captures metadata containing event UUID, timestamp, actor reference, and correlation; the listener receives the event and prints IDs and kind. Since the code does not print `eventId` and `occurredAt`, stdout stays deterministic even though both are generated at runtime.
4. Simulated user `user-99` only has membership in `tenant-red`. The store throws a generic `access denied` error **before publishing any event**, so there is no second `APPROVED` line.
5. `TrustedIdentity` is instantiated in `main` solely to illustrate pre-authenticated data. In real applications, it must come from a **trusted** authentication boundary, never from a client-supplied object.
6. The example uses an in-memory `HashMap` with no transactions or durable storage. If a listener throws an exception after the state changed, the example **does not automatically roll back**. In production, design transactions + outbox or matching publishing policies.

**Authorization note:** because the example uses membership alone for simplicity, it does not model roles or an `APPROVE_INVOICE` permission. Real systems must verify membership, resource-level roles/permissions, invoice status, and approval policies (e.g., preventing self-approval of one's own invoice) before emitting the fact.

## 10. With `@Async` or `TaskExecutor`: Which Context Still Exists?

Under `ApplicationEventPublisher`, Spring events are normally dispatched synchronously via the default multicaster. When a listener executes asynchronously via `@Async` or an executor configured on the multicaster, the handling thread may differ from the publishing thread.

In Spring Framework, **ThreadLocal and logging context are not automatically propagated into async listeners**. Spring Security also keeps `SecurityContextHolder` in a ThreadLocal by default. Hence:

```java
@Async
@EventListener
public void onInvoiceApproved(InvoiceApproved event) {
    // Do NOT rely on SecurityContextHolder from the old request thread.
    // Use the actor + tenant snapshot inside the event after verifying provenance.
    var actorId = event.metadata().actor().id();
    var tenantId = event.metadata().tenantId();
    processApprovedInvoice(tenantId, event.invoiceId(), actorId);
}
```

This is an **illustrative snippet**: it requires a listener bean with `@EnableAsync`/appropriate executor and an application-defined `processApprovedInvoice`. It is not part of the standalone program in section 9.

### 10.1. Capturing Context Does Not Mean Transferring Full Authority

Storing actor/tenant in an event tells the consumer **what context the fact had**, yet does not grant the consumer authority to perform arbitrary actions as that actor. If a consumer action requires current permissions, apply trust and authorization checks against current authority; a user's permissions may have been revoked after the fact occurred.

An audit consumer may need to record the historical actor **exactly as at event publication time**. A consumer sending data externally must check current policies and tenant permissions. Those two needs differ.

### 10.2. `TaskDecorator` and Context Propagation

Some systems propagate MDC/tracing/security context across executors using a `TaskDecorator` or equivalent. That is a convenience for runtime observability, not a reason to shove mutable security objects into events.

When using propagation:

- Propagate only genuinely required context.
- Follow Spring Security's mechanisms (e.g., executor wrapping/delegation) if propagating authentication.
- Restore/clear context in `finally` so it does not leak to the next task.
- Avoid grabbing the actor at **listener execution time** to overwrite the actor at **fact occurrence time**.
- Define retention/sensitivity: trace baggage and MDC can end up written to logs.

### 10.3. Thread-Local Tenants Easily Cause Cross-Tenant Contamination

If a worker thread previously handled tenant A and fails to clear tenant context, the next event for tenant B may run under tenant A. The key test is not merely "did the listener receive the right `tenantId` in the payload?", but "which tenant scope are the repository, datasource, and logs actually operating under?".

Prefer immutable tenant information in the event, executed within explicit boundaries with cleanup. If tenant selection needs async/scheduling, use a context snapshot or explicit parameter rather than inferring from an ambient ThreadLocal that may be absent.

## 11. Transactions: When Actor/Tenant Are Captured and What "Occurred" Means

If the service is `@Transactional`:

```java
@Transactional
public void approveInvoice(...) {
    // 1. Authenticate + authorize actor for invoice tenant.
    // 2. Change invoice state in the transaction.
    // 3. Construct and publish InvoiceApproved.
}
```

This is pseudocode. Calling `publishEvent` while the transaction is **uncommitted** causes synchronous `@EventListener` methods to run immediately on the transaction thread. Events may reach consumers while the DB transaction can still roll back afterward.

For side effects valid **only after commit**, use:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onInvoiceApproved(InvoiceApproved event) {
    // Callback after successful commit.
}
```

This is an illustrative snippet inside a Spring bean with a transaction manager, requiring `TransactionalEventListener`/`TransactionPhase` imports. By default, without an active transaction, transactional event listeners do not process events unless `fallbackExecution = true` is enabled.

**Limits to keep in mind:**

- `AFTER_COMMIT` constrains **callback timing**, not durable event persistence.
- A process crash after DB commit and before delivery can still lose processing if using only in-memory events.
- To guarantee events can be redelivered after a crash, consider a transactional outbox written in the same transaction as business data.
- `occurredAt` must be precisely defined by the domain: approval decision time or commit time? Never equate object creation timestamp with commit timestamp.
- Actor/tenant must be resolved where the business decision happens; never wait until `AFTER_COMMIT` to re-read a request ThreadLocal.

### When a Consumer Writes to the DB After Commit

An `AFTER_COMMIT` listener may briefly still see old transaction resources bound to the thread per Spring's lifecycle. If it needs to write to the DB in a new transaction, design an explicit separate transaction (e.g., `REQUIRES_NEW` on a properly proxied service). Never assume an after-commit listener annotation automatically creates a new transaction.

## 12. Distinguishing Domain Events and Integration Events Across System Boundaries

For internal Spring Application Events:

```text
InvoiceService
     |
     v
ApplicationEventPublisher
     |
     v
@EventListener in the same context/JVM
```

Event objects can be ordinary Java records; Spring does not require extending `ApplicationEvent`. When moving out to a broker:

```text
Domain event (in-process)
    |
    v
Outbox / secure publisher
    |
    v
Integration message (schema version, tenant, actor, IDs)
    |
    v
Authenticated consumer
    |
    v
Tenant-aware processing
```

In integration events, clarify:

1. **Provenance:** which producer is authorized to emit this event type? Which broker ACLs/signatures/identities protect the transport?
2. **Schema:** which fields are required, what is the version, and what is the compatibility policy?
3. **Tenant routing:** which partition keys, namespaces, or queues belong to which tenant? Tenant metadata alone does not prove broker isolation.
4. **Privacy:** can actor IDs cross systems or tenants? Are pseudonyms or mappings required?
5. **Replay:** will actor identities at publication time still be interpretable years later? What is the retention policy?
6. **Duplicates/out-of-order:** does the consumer enforce `eventId` idempotency and business ordering?
7. **Destination authorization:** is the consumer allowed to process that tenant's data, rather than blindly trusting a JSON field?

When an integration event is generated from a domain event, **do not accidentally change the actor's meaning**: a relay service does not become the actor of the business fact. You can record `publisherService` or `emittedBy` separately while keeping the historical `actor` as the person/service that executed the business action.

## 13. Security, Privacy, and Auditing

Good metadata records help investigate who did what. Yet trustworthy auditing requires more than having an `actorId` field in a record.

### 13.1. Do Not Treat Events as Proof of Authentication

Event payloads can be constructed by buggy code or forged over unprotected transport. An event containing `actorId=user-42` **does not prove** `user-42` was actually authenticated when the event was created.

A reliable pipeline requires:

- Authentication at ingress.
- Tenant/resource authorization where business decisions are made.
- Restricting sensitive event publication to authorized producers.
- Appropriate audit or integrity controls (append-only storage, access control, retention).
- Consumers verifying message provenance before trusting metadata for actions.

### 13.2. Actor ID Is Not a Token

An opaque user ID is identification data, not a credential. Never put access tokens into `actorId` or `correlationId`. Avoid using an email directly as a permanent actor ID when an internal ID is available; emails change and are PII.

### 13.3. Data Classification and Minimization

| Field | Should Contain | Avoid |
| --- | --- | --- |
| `actor.id` | Minimal stable principal identifier | Raw JWTs, passwords, emails when unnecessary |
| `actor.kind` | `HUMAN`/`SERVICE`/`SYSTEM` or clear domain kind | Giant role lists, entire authorities snapshots |
| `tenantId` | Consistent opaque ID | Company names/addresses and secrets instead of IDs |
| `correlationId` | Controlled ID useful for tracing | Tokens, unvalidated raw headers |
| `eventId` | Occurrence ID | Secrets used as access keys |
| `occurredAt` | Instant/UTC per contract | Local time without timezone |
| `business fields` | Facts needed to understand the occurrence | Whole entities containing out-of-scope PII |

Event and audit retention may be subject to legal, contractual, and organizational policies. Never claim every event must be kept forever; establish retention limits, access permissions, and redaction or deletion/anonymization mechanisms per applicable regulations.

### 13.4. Logging Can Create Secondary Leaks

Even without tokens in the payload, `log.info("event={}", event)` can print all metadata and business fields via record `toString()`. For events with PII, log an allowlist of necessary IDs and avoid full object dumps.

If tenant/user IDs are logged, configure log access permissions accordingly because logs duplicate data and may persist for long periods.

## 14. Metadata Schema Evolution

When adding `causationId` to an event used across multiple services, consider compatibility:

- Can old consumers unaware of the new field ignore it?
- Can new consumers read old messages lacking causation?
- Can the field be optional or does it require a new contract version?
- When renaming `userId` to `actor.id`, how is historical data migrated?
- Do old consumers understand `SYSTEM`/`SERVICE` `ActorKind` values?
- Does `tenantId` change format or namespace?

**Never silently change a field's meaning.** For instance, previously `actorId` was always the human clicking a button; now the same field holds a relay service. When downstream consumers rely on it for auditing or policy enforcement, that shift is dangerous even if the schema remains a string.

Illustrative envelope:

```json
{
  "schemaVersion": 2,
  "eventType": "InvoiceApproved",
  "eventId": "d15e2182-89e7-4f29-8033-760312e91578",
  "tenantId": "tenant-blue",
  "actor": {
    "kind": "HUMAN",
    "id": "user-42"
  },
  "correlationId": "REQ-9",
  "occurredAt": "2026-01-01T10:00:00Z",
  "data": {
    "invoiceId": "INV-7"
  }
}
```

This JSON **illustrates an integration event**, not automatic serialized output from Spring Framework. Spring Application Events mandate no `eventType`, `schemaVersion`, or fixed envelope. When using brokers/APIs, teams must define serializers, versioning, schema registries, and field validation policies.

## 15. Idempotency and Tenant Isolation Under Duplicate Processing

An event may be redelivered by a broker or republished on retry. Metadata helps identify it, yet **does not automatically prevent duplicates**.

A durable consumer design can key by:

```text
PRIMARY KEY (tenant_id, event_id)
```

with a `processed_events` table and business updates **in the same transaction**. If `event_id` is already guaranteed globally unique, `event_id` alone may suffice, though keeping `tenant_id` still aids partitioning and auditing. Deduplication policies must reflect actual contracts and boundaries—never assume a UUID string makes everything automatically exactly-once.

Important:

- Verify the **target resource's** tenant before writing, not only the message's tenant.
- If tenant scope is part of database keys, queries must include the right scope or use tested Row Level Security.
- Never use `correlationId` as a deduplication key: one correlation can produce many events.
- When replaying events, the historical actor stays preserved, yet authority to re-execute side effects may need separate verification.
- For untrusted events, verify provenance **before** using `tenantId` to select a datasource or partition.

## 16. Special Design Scenarios

### 16.1. System-Wide Operations

For example, `PricingPolicyPublished` applies to all tenants. If the contract is genuinely global, use an explicit global event type/context rather than a fake tenant like `all` or `default` that consumers might mistake for a real tenant.

An application can define two contracts:

```text
TenantScopedEvent { tenantId, ... }
GlobalEvent       { scope = GLOBAL, ... }
```

Do not allow `null` in every tenant-scoped event and force consumers to guess whether it means global or a missing-data bug.

### 16.2. One Actor Affecting Multiple Tenants

An operations admin may perform a bulk action across multiple tenants. If each tenant undergoes its own business change, emit tenant-scoped events for each fact. A single event with an arbitrary `tenantId` makes auditing, idempotency, and authorization hard to determine.

You can keep one shared `correlationId` to tie the whole batch together and use `actor=HUMAN:admin-7` for the performer; each fact still gets its own `eventId` and `tenantId`.

### 16.3. Handling Impersonation / Delegation

If support staff are allowed to "act on behalf of a customer", the audit contract should distinguish:
- Who actually performed the action: `actor`.
- Whose identity was represented: `onBehalfOf`.
- Reason/authorization record for delegation: `delegationId` when needed.

Never record the customer as `actor` simply because the UI had the customer's profile open; events must reflect the true origin of the action.

### 16.4. Events Originating from Webhooks

A payment webhook may carry a provider's event ID and its own merchant/tenant mapping. The consumer must verify signatures/provider identity and look up the trusted internal tenant. Never take a tenant ID from webhook JSON as authoritative if the provider does not guarantee that field's semantics or the message is unauthenticated.

### 16.5. Service Events Without a Current User

Scheduled jobs, retries, or queue consumers may have no `SecurityContextHolder`. Default to a clearly identified `SYSTEM`/`SERVICE` actor instead of failing for "missing userId", provided that matches the operation's true semantics. If the work continues a prior user request, keep `originalInitiator` separately for traceability.

### 16.6. Tenant Migration or Renaming

A tenant display name can change while its stable ID stays fixed. If the system merges or splits tenants, historical events reflect the owner at the time the fact occurred. Never rewrite `tenantId` retroactively across all historical events without a migration/audit policy; maintain a mapping history if querying across the current structure.

## 17. Decision-Table Testing for Actor, Tenant, and Context

| Test Case | What to Verify |
| --- | --- |
| Actor belongs to invoice-owning tenant | Event gets tenant from source data, trusted actor ID, and right correlation |
| Actor belongs to a different tenant | Rejected; **do not publish** event |
| Invoice does not exist | Error leaks no info about other tenants; no publish |
| Unauthenticated actor | No valid `TrustedIdentity` created from spoofed requests |
| Has membership but lacks approval permission | Rejected per real policy, not membership alone |
| Actor is a scheduled service | Correct `kind=SYSTEM/SERVICE` and stable ID, not impersonating a user |
| Delegated operation | `actor` and `onBehalfOf` are distinguished |
| One request emits two facts | Two distinct `eventId`s, may share `correlationId` |
| Async listener uses thread pool | Still reads actor/tenant metadata from payload without request ThreadLocal |
| Multiple tenants share a pool | No leaked tenant context from prior tasks; cleanup always runs |
| Transaction rollback | Contract never claims a committed fact when transaction rolls back |
| Event arrives after user permissions change | Audit keeps historical actor; new actions check current authorization |
| Replayed/duplicate event | Consumer deduplicates by event ID and proper tenant scope |
| New schema version | Old/new consumers are compatible per contract |
| Payload with sensitive data | No tokens, credentials, or out-of-policy PII logged/serialized |
| Message from untrusted producer | Provenance verified before using tenant to select resources |

### Testing Beyond Reading Logs

You can build a recorder listener to capture events in tests rather than only matching stdout:

```java
public final class InvoiceEventRecorder {
    private final List<InvoiceApproved> events = new ArrayList<>();

    @EventListener
    public void record(InvoiceApproved event) {
        events.add(event);
    }

    public List<InvoiceApproved> snapshot() {
        return List.copyOf(events);
    }
}
```

This is an illustrative **synchronous test helper**, requiring imports for `List`, `ArrayList`, `EventListener`, and the `InvoiceApproved` type. Register the recorder as a Spring bean before publishing. When testing with an async multicaster, use a thread-safe recorder and a bounded wait mechanism; `ArrayList` is not safe when multiple listeners/tasks write concurrently.

Illustrative assertions (inside a JUnit test, not part of the standalone Maven example):

```java
assertEquals("tenant-blue", event.metadata().tenantId());
assertEquals("user-42", event.metadata().actor().id());
assertEquals(ActorKind.HUMAN, event.metadata().actor().kind());
assertEquals("REQ-9", event.metadata().correlationId());
assertNotNull(event.metadata().eventId());
```

Beyond checking metadata, verify **no event is emitted when unauthorized**, and that actual data access inside listeners is restricted to the right tenant. Asserting `event.tenantId()` alone will not catch a non-tenant-scoped database query.

## 18. Common Pitfalls

1. **Taking `actorId` from the request body and copying it straight into the event.** Untrusted input unless verified; derive from a verified principal/identity.
2. **Copying tenant from an HTTP header without checking the resource.** Users can specify another tenant; resolve the canonical owner from the repository and check permissions.
3. **Confusing actor with affected subject.** Audit history attributes actions to the wrong person.
4. **Reading `SecurityContext` in an async listener expecting the old user.** ThreadLocal does not propagate by default.
5. **Setting tenant into ThreadLocal and forgetting to clear it.** The next worker task may run under the wrong tenant.
6. **Saving whole `Authentication` or JWTs into events.** Leaks credentials, complicates serialization, and carries unnecessary data.
7. **Using email as a permanent actor key.** Emails change and are PII; prefer stable IDs.
8. **Using correlation ID instead of event ID.** One request can create multiple facts, causing wrong deduplication.
9. **Treating tenant ID in an event as proof of authorization.** Provenance and policies are needed on producers and consumers.
10. **Assuming writing actor into an event is enough for reliable audit logs.** Transactions/durability, producer controls, retention, and integrity are also required.
11. **Forcing every event into one metadata type with mandatory tenant, including global events.** Leads to fake tenants or confusing nulls.
12. **Treating `@TransactionalEventListener(AFTER_COMMIT)` as an outbox.** Post-commit callbacks have no redelivery guarantee if the JVM crashes.
13. **Assuming records make all nested objects immutable.** Defensive copies are required for mutable references.
14. **Dumping all MDC/headers into payloads.** Can leak secrets and increase coupling and PII risk.
15. **Logging events via `toString()` unchecked.** Logs can replicate sensitive data.
16. **Using historical actor to auto-authorize later consumer actions.** Permissions change; verify per current needs.
17. **Failing to enforce tenant checks at the database boundary.** Correct payloads with unscoped queries still leak data.
18. **Changing `actorId` semantics between users and services without versioning.** Audit consumers may misinterpret it.
19. **Relying on local time without timezones.** Hard to trace events across multi-region systems.
20. **Publishing events before the fact is confirmed.** Complete metadata cannot fix an event lying about the domain.

## 19. Step-by-Step Process for Choosing Metadata per Event

**Step 1 — Define the fact.** For example, "invoice has been approved per tenant policy".

**Step 2 — Identify the subject/resource.** Which tenant owns the invoice? Can there be multiple valid owners? Where does the canonical owner live?

**Step 3 — Identify the actor.** User, service, system job, or delegated action? Which trust boundary provides the stable ID?

**Step 4 — Determine the needed context level.** Do `eventId`, timestamp, correlation, causation, trace, and request ID serve a real purpose? Which fields can be omitted?

**Step 5 — Enforce authorization.** Check permissions where the business decision happens before publishing; metadata never replaces policy.

**Step 6 — Package an immutable snapshot.** Keep mutable requests/principals/entities out of payloads; use meaningful types and validation.

**Step 7 — Choose transaction/delivery.** If the fact must be durable or cross services, specify commits, outbox, retries, idempotency, and producer provenance.

**Step 8 — Design tenant-scoped consumers.** Query the right tenant, prevent thread-context leaks, and bound permissions and logging.

**Step 9 — Test attack and failure scenarios.** Wrong tenant, spoofed actor, retries, async, tenant switching, startup/shutdown, and replay.

### Review Checklist

- [ ] Does `actor` answer "who/what performed it" and stay distinct from `subject` when needed?
- [ ] Is the actor ID stable, not a token, password, or entire principal?
- [ ] Is the tenant ID retrieved from an authoritative resource-ownership source after permission checks?
- [ ] Does the event carry only metadata needed to understand the fact, without copying whole requests/MDC?
- [ ] Does `eventId` identify the occurrence, `correlationId` link the workflow, and `causationId` (if any) have a clear definition?
- [ ] Does `occurredAt` use a consistent time format, never confused with commit/publish/receive time?
- [ ] Is the event payload immutable for required data, free of mutable aggregates/sessions/connections?
- [ ] Are async listeners independent of the publisher's `SecurityContext`/tenant `ThreadLocal`?
- [ ] Do consumers verify provenance and permissions at boundaries, enforcing tenant scope on data access?
- [ ] Are events containing PII governed by logging, retention, and access-control policies?
- [ ] Do transactions/outbox and idempotency match reliability requirements?
- [ ] Do tests verify **no** fact is emitted when the actor lacks permission on that tenant/resource?

**Conclusion:** in domain events, `actor` describes the performing identity, `tenant` describes the ownership boundary, and correlation/causation/event IDs plus timestamps describe relationships and timing. All must originate from **authenticated sources after authorization checks**, be stored as minimal snapshots, and be consumed within controlled boundaries. Good metadata aids diagnostics, auditing, and tenant isolation, yet **never replaces authentication, authorization, transactions, or reliable delivery mechanisms**.

## References

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security Reference — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
