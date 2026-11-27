# Providing the Actor with AuditorAware

## 1. Why Does a System Need to Know Who Acted?

In the **Auditing** chapter of **Spring Data MongoDB**, two common fields are **who created** a document and **who last modified** it. When an employee updates an invoice status, a scheduled job synchronizes data, or an API client creates an order, the application often wants to store:

~~~json
{
  "_id": "invoice-101",
  "tenantId": "tenant-a",
  "status": "APPROVED",
  "created_by": "user-101",
  "modified_by": "user-205",
  "created_at": { "$date": "2026-11-20T08:00:00Z" },
  "updated_at": { "$date": "2026-11-20T08:15:00Z" }
}
~~~

The `created_by` and `modified_by` fields must come from a **trusted identity source**, not an arbitrary string sent by the client. Spring Data provides an auditing metadata mechanism where:

- `@CreatedBy` marks the property that receives the creator.
- `@LastModifiedBy` marks the property that receives the last modifier.
- `@CreatedDate` and `@LastModifiedDate` mark the creation/modification timestamps.
- **`AuditorAware<T>`** supplies the current actor for the **imperative** data access flow.
- `@EnableMongoAuditing` enables MongoDB auditing infrastructure and can specify the `AuditorAware` bean.

Without a proper, consistent actor source, `@CreatedBy` and `@LastModifiedBy` cannot automatically know which user a request belongs to.

### Lesson Objectives

1. Understand `AuditorAware<T>`, `Optional<T> getCurrentAuditor()`, and how Spring Data attaches the actor to an entity.
2. Design an entity with `@CreatedBy`/`@LastModifiedBy`, BSON mapping, and optional timestamps.
3. Register `@EnableMongoAuditing(auditorAwareRef = "...")` to select the right auditor provider.
4. Obtain the actor from Spring Security `SecurityContextHolder`, avoiding anonymous principals and client-declared user IDs.
5. Handle tasks without an HTTP principal: jobs, batches, schedulers, migrations, and service accounts.
6. Distinguish repository saves from `updateFirst`, bulk writes, the raw driver, and delete operations.
7. Understand transactions, retries, optimistic locking, and the difference between **audit metadata** and an **audit trail**.
8. Test `createdBy`/`lastModifiedBy` transitions when switching actors against real MongoDB, including raw BSON.
9. Distinguish `AuditorAware` from `ReactiveAuditorAware` in reactive applications.

> Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. Details such as callback ordering, new-entity detection, and the behavior of separate update paths can vary across API/versions; run integration tests on your exact dependency combination. This lesson focuses on **metadata auditing**, not an immutable audit log mechanism meeting every regulatory requirement.

## 2. Auditing Metadata Differs from Business Audit Trails

An invoice document often needs to answer four questions:

| Question | Appropriate Field | Mechanism |
|---|---|---|
| Who created the record? | `createdBy` | `@CreatedBy` + `AuditorAware` |
| Who last modified the record? | `lastModifiedBy` | `@LastModifiedBy` + `AuditorAware` |
| When was it created? | `createdAt` | `@CreatedDate` |
| When was it last modified? | `lastModifiedAt` | `@LastModifiedDate` |

However, these fields **do not answer**:

- Who modified the invoice **every single time** in the past?
- Which values changed, and what were the before/after values?
- Was the action approved by two people?
- Was the document overwritten directly via the driver or a script?
- Did a user forge an identity or was an account compromised?
- Did the transaction containing the operation actually commit?

`lastModifiedBy` is only **snapshot metadata**, not a complete audit history. If the business requires full traceability, use an audit event/ledger/outbox/change streams or a controlled history solution with clear retention and access permissions.

### 2.1. Do Not Confuse Actor with Subject

For example, an admin edits details for a customer:

~~~text
actor = admin staff user-205
subject = customer customer-901
tenant = tenant-a
operation = APPROVE_INVOICE
~~~

`@LastModifiedBy` typically stores the **actor**, not the customer ID being operated on. If you want to store both actor and subject, they are two different fields/concepts. Do not use `tenantId`, `createdBy`, and `customerId` interchangeably.

### 2.2. The Identity Source Must Be Trusted

An HTTP header such as:

~~~http
X-Actor-Id: admin
~~~

is not self-proving evidence that the actor is admin. Only use an identity value **authenticated and authorized** by the security layer, such as a Spring Security principal after a JWT/session is validated.

## 3. Lifecycle Map of Spring Data Auditing

When a repository saves an entity through Spring Data mapping, the auditing infrastructure can participate in the pipeline **before the converter sends BSON to MongoDB**.

~~~mermaid
flowchart TD
    A["Authenticated HTTP/worker"] --> B["Spring Security context / actor provider"]
    B --> C["AuditorAware.getCurrentAuditor()"]
    D["repository.save(entity)"] --> E["Spring Data auditing callback"]
    C --> E
    E --> F["Assign appropriate @CreatedBy/@LastModifiedBy"]
    F --> G["MappingMongoConverter: Java -> BSON"]
    G --> H["MongoDB write"]
    H --> I["Return entity / write result"]
~~~

When saving a new entity, auditing usually populates both creator and modifier per configuration. When saving an existing entity, auditing usually preserves the creator and updates the modifier. However:

1. The framework must identify whether the entity is **new** or **existing** via mapping/version/`Persistable`.
2. Auditing must be **enabled** and a matching `AuditorAware` bean must exist.
3. The write path must go through a Spring Data-supported entity lifecycle.
4. `getCurrentAuditor()` must return an appropriate actor; `Optional.empty()` means no actor is provided, **not a valid empty actor**.
5. Updates executed with the raw driver or update operators will not necessarily run the same entity callback.

**Preparing auditing metadata before a write does not mean the transaction committed.** If the transaction rolls back, the prepared metadata must not be treated as proof that the operation was durably accepted.

### 3.1. Conceptual Execution Order

~~~text
Application service
    └─ repository.save(entity)
         ├─ detect new/existing
         ├─ auditing callback queries AuditorAware
         ├─ update createdBy/modifiedBy/date
         ├─ map entity to BSON
         ├─ MongoDB insert / save
         └─ return result
~~~

Do not read this diagram as an absolute ordering guarantee across all custom callbacks, events, version increments, or store-specific auditing cases. If you write a custom callback that depends on `lastModifiedBy` already being set, test it empirically or apply changes in the service/domain instead of relying on undefined ordering.

## 4. The AuditorAware<T> Contract

Spring Data interface:

~~~java
package org.springframework.data.domain;

import java.util.Optional;

public interface AuditorAware<T> {
    Optional<T> getCurrentAuditor();
}
~~~

This snippet only illustrates the public API contract; **do not recreate `org.springframework.data.domain.AuditorAware` in your project**.

A simple implementation:

~~~java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;

public class FixedActorAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system:demo");
    }
}
~~~

It always returns the same actor, convenient for demos or test fixtures, yet **unsuitable for systems with multiple logged-in users** because every document would carry the same identity.

### 4.1. Generic Type Must Match the Audit Field

| Field Declaration | Matching Provider |
|---|---|
| `@CreatedBy private String createdBy` | `AuditorAware<String>` |
| `@CreatedBy private UUID createdBy` | `AuditorAware<UUID>` or explicit conversion |
| `@CreatedBy private ActorRef createdBy` | `AuditorAware<ActorRef>` with compatible mapping/converter |

If the field is `String` while the provider returns a `User` entity with many relationships, do not assume the converter will persist and query it cleanly. Prefer storing a simple **stable user ID** when the requirement is simply "who acted".

### 4.2. Optional.empty() Is Not Equivalent to Anonymous

~~~java
@Override
public Optional<String> getCurrentAuditor() {
    return Optional.empty();
}
~~~

`Optional.empty()` means **no auditor is supplied** for this invocation. Spring Data does not automatically convert an empty result into `"anonymous"`, `"system"`, or a default account. For new entities, actor metadata may remain unpopulated; for existing entities, changes to auditor fields depend on the state/callback behavior of your version.

If policy dictates that **every write must have an actor**, reject operations lacking identity at the service/security boundary or use an explicitly defined system actor. Do not silently attribute unauthenticated requests to admin.

### 4.3. AuditorAware Is an Identity Source, Not a Permission Checker

`AuditorAware` supplies identity; it **does not decide which invoices a user is allowed to edit**. Authorization must be checked in the service/policy and `tenantId` must be filtered in queries. An authenticated request may still lack permission to edit another tenant's invoice.

## 5. Invoice Entity with @CreatedBy and @LastModifiedBy

This example uses the `audit_invoices` collection and two BSON fields `created_by` and `modified_by`.

**AuditInvoice.java**

~~~java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "audit_invoices")
public class AuditInvoice {

    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String status;

    @CreatedBy
    @Field("created_by")
    private String createdBy;

    @LastModifiedBy
    @Field("modified_by")
    private String lastModifiedBy;

    @CreatedDate
    @Field("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Field("updated_at")
    private Instant updatedAt;

    @Version
    private Long version;

    protected AuditInvoice() {
        // For MongoDB converter.
    }

    public AuditInvoice(String id, String tenantId, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public String getCreatedBy() { return createdBy; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Long getVersion() { return version; }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

In this model:

- Callers do not need public setters for `createdBy`/`lastModifiedBy`; auditing metadata is managed by the lifecycle.
- Java field `createdBy` is stored under BSON `created_by`.
- Java field `lastModifiedBy` is stored under BSON `modified_by`.
- `@CreatedDate`/`@LastModifiedDate` are populated by the auditing date provider.
- `@Version Long` illustrates optimistic locking when the repository saves a loaded entity; it is not mandatory for enabling auditing.
- `tenantId` is never automatically overwritten with the auditor inside a callback. Actor and tenant are distinct concepts.

### 5.1. Repository

**AuditInvoiceRepository.java**

~~~java
package com.example.audit;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditInvoiceRepository
        extends MongoRepository<AuditInvoice, String> {

    Optional<AuditInvoice> findByIdAndTenantId(
            String id, String tenantId);
}
~~~

This is an **imperative** repository. Method naming uses Java property names such as `tenantId`; Spring Data maps them to the physical field accordingly. `findByIdAndTenantId` is convenient for tenant-scoped reads, while updates must continue enforcing tenant and status inside the **write predicate** when invariants require it.

### 5.2. Why Use a Long Version?

For entities with pre-assigned IDs, a `@Version Long` field starting at `null` helps Spring Data detect new entities under supported version strategies. On insert, the framework initializes the version; subsequent saves use the version condition to detect stale writes.

Do not infer from `id != null` that an entity already exists, and do not modify the version manually inside an auditing provider. Entity state detection and optimistic locking must be tested on your specific version.

## 6. Registering Mongo Auditing and Choosing auditorAwareRef

**InvoiceAuditingConfig.java**

~~~java
package com.example.audit;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
        auditorAwareRef = "currentActorAuditorAware",
        modifyOnCreate = true)
public class InvoiceAuditingConfig {
}
~~~

`@EnableMongoAuditing` enables Mongo auditing, where `auditorAwareRef` selects the **bean named** `currentActorAuditorAware`. This is especially useful when the application context contains multiple `AuditorAware<?>` implementations.

`modifyOnCreate = true` is an explicit choice in this lesson: when a new entity is created, the system populates both created metadata and last-modified metadata. If business rules want `lastModifiedBy`/`updatedAt` populated only **after the first update**, consider `modifyOnCreate = false` and write tests verifying the contract on your version.

### 6.1. Enabling Auditing Does Not Guarantee an Actor Exists

If auditing is configured without a matching `currentActorAuditorAware` bean, the application context may fail while building the auditing infrastructure or fail to supply the intended auditor. Always verify bean registration.

If the bean exists yet returns `Optional.empty()` because a request lacks an authenticated principal, the annotations do not invent a substitute user ID. Audit outcomes must be tested for both authenticated and anonymous/system contexts.

### 6.2. @EnableMongoAuditing Does Not Go on Every Entity

`@EnableMongoAuditing` enables infrastructure on a Spring configuration class; `@CreatedBy`/`@LastModifiedBy` go on entity fields/properties per mapping. Do not place `@EnableMongoAuditing` on every repository or service.

If a Spring Boot app has multiple configuration classes, ensure the config is component-scanned or imported, and **do not register conflicting auditing infrastructures**. The Boot MongoDB starter helps create the client/template/repositories, but do not assume the starter automatically picks an actor provider from the security context without configuration.

### 6.3. AuditorAware Does Not Control the Clock

`@CreatedBy` and `@LastModifiedBy` resolve the actor; timestamps come from the auditing time provider. When a controlled clock is needed, Spring Data offers `DateTimeProvider` and the `dateTimeProviderRef` attribute on supported versions.

Do not call `Instant.now()` inside `AuditorAware` to populate time fields manually: mixing two responsibilities makes testing harder and hinders timezone/clock consistency.

## 7. Getting the Actor from Spring Security

In an application using Spring Security, a common approach is reading `SecurityContextHolder` at save time.

Common dependencies when using Spring Security:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

The security starter does not automatically define your project's actor mapping. You must distinguish authenticated principals, anonymous authentication, service accounts, and non-HTTP requests.

**CurrentActorAuditorAware.java**

~~~java
package com.example.audit;

import java.util.Optional;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component("currentActorAuditorAware")
public class CurrentActorAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication auth = SecurityContextHolder
                .getContext()
                .getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        String principalName = auth.getName();
        if (principalName == null || principalName.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(principalName);
    }
}
~~~

Avoid:

~~~java
// Do not use an unverified client-supplied actor:
String actor = request.getHeader("X-Actor-Id");
~~~

In standard Spring Security setups, `Authentication.getName()` returns a representative name for the principal, but **its semantics depend on the authentication provider**:

- Username/password login may return the username.
- A JWT resource server may map from a claim like `sub` depending on the converter.
- OAuth2 login may use a different attribute.
- A service-to-service token may represent a service account.

For durable audit metadata, define your project's **stable actor ID** contract. Do not blindly assume display name, email, or `getName()` is immutable, globally unique, and permissible for long-term storage.

### 7.1. Why Exclude AnonymousAuthenticationToken?

In some Spring Security configurations, an anonymous request still holds an `Authentication` object with `isAuthenticated()` set to `true` per token semantics. Checking `instanceof AnonymousAuthenticationToken` explicitly avoids recording `"anonymousUser"` in a field meant for authenticated users.

If business requirements want to record an actor for public/anonymous operations, define a **dedicated actor type**, such as `"public:anonymous"` or a request ID, instead of treating it as an admin or real user.

### 7.2. Principal ID Does Not Have to Be Email

If you use email as the actor:

- Emails can change;
- One person may have multiple emails;
- Emails can be sensitive PII under privacy policies;
- Service accounts sometimes lack emails.

Storing an immutable `userId`/`serviceAccountId` is generally more reliable. For display names, resolve actor IDs through an identity system with appropriate permissions. Never embed tokens, secrets, or entire principal objects into audit fields.

### 7.3. Resolve Actor Close to the Write, Authorize Before the Write

`AuditorAware` is invoked during the write lifecycle, so it reflects the active security context at that moment. However, authorization **must not wait for the callback**. The service must verify tenant/role/ownership and enforce write predicates at the database. Auditing only records who acted on supported paths; it does not block unauthorized writes.

## 8. A CRUD Service Using Auditing Properly

Once `InvoiceAuditingConfig` and `CurrentActorAuditorAware` are configured, the service does not call `setCreatedBy` or `setLastModifiedBy`.

**InvoiceService.java**

~~~java
package com.example.audit;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private final AuditInvoiceRepository repository;

    public InvoiceService(AuditInvoiceRepository repository) {
        this.repository = repository;
    }

    public AuditInvoice create(
            String authenticatedTenantId,
            String id) {
        requireInput(authenticatedTenantId, id);

        // Domain/policy layer must verify CREATE permission for tenant.
        AuditInvoice invoice =
                new AuditInvoice(id, authenticatedTenantId, "DRAFT");

        return repository.insert(invoice);
    }

    public AuditInvoice approve(
            String authenticatedTenantId,
            String id) {
        requireInput(authenticatedTenantId, id);

        // Domain/policy layer must verify APPROVE permission.
        AuditInvoice invoice = repository
                .findByIdAndTenantId(id, authenticatedTenantId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Authorized invoice not found"));

        if (!"DRAFT".equals(invoice.getStatus())) {
            throw new IllegalStateException(
                    "Only DRAFT invoices can be approved");
        }

        invoice.setStatus("APPROVED");

        // @Version helps detect stale saves on the repository path,
        // not a replacement for all business CAS checks.
        return repository.save(invoice);
    }

    private static void requireInput(String tenantId, String id) {
        if (tenantId == null || tenantId.isBlank()
                || id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid tenant/ID");
        }
    }
}
~~~

**Note on repository API:** when a repository extends `MongoRepository<AuditInvoice, String>`, `insert(entity)` is provided by Spring Data MongoDB. `insert` expresses creation intent more clearly than `save` when duplicate keys must be rejected, provided collections and unique constraints are properly set up.

### 8.1. Who Populates createdBy and lastModifiedBy?

Suppose authenticated user `"user-101"` calls `create`:

~~~text
Before insert:
  id = invoice-101
  status = DRAFT
  createdBy = null
  lastModifiedBy = null

AuditorAware returns "user-101"
MongoDB insert -> metadata populated per auditing config
~~~

Later, authenticated user `"user-205"` calls `approve`:

~~~text
Before save existing:
  status = APPROVED
  auditing receives actor "user-205"

After save:
  createdBy = "user-101"      (preserved)
  lastModifiedBy = "user-205" (latest modifier)
~~~

With `modifyOnCreate = true`, `lastModifiedBy` can be populated on the initial insert. Do not assume this field must be null on new entities across all configurations.

### 8.2. Updating via save Still Risks Races Without Version Control

The service above uses `@Version Long`. If two requests both read the DRAFT entity, and one approves and saves first, the other still holds the old version. The second save is rejected with `OptimisticLockingFailureException` under an acknowledged write concern.

However, if the business requires an atomic state transition without loading the entity first, `MongoTemplate.updateFirst` filtering by `status = DRAFT` and `tenantId` may be a better fit. In that case, **the repository save auditing callback does not run by default**: you must explicitly update the actor and timestamps in the same update or design a dedicated domain repository.

### 8.3. Do Not Check Security Rules Only After Reading

Incorrect:

~~~java
AuditInvoice invoice = repository.findById(id).orElseThrow();
if (invoice.getTenantId().equals(authenticatedTenantId)) {
    return repository.save(invoice);
}
~~~

A save by ID/version alone does not necessarily place the tenant condition into **the write predicate itself**. In multi-tenant domains, define clear security policies and guard invariants against alternative write paths. For sensitive operations, use a conditional update matching `_id + tenantId + status/version` rather than assuming a prior Java check is atomic.

### 8.4. Should CreatedBy Be Immutable?

In an invoicing domain, the **creator** should normally never change after document creation. Never let API request bodies submit `createdBy` and map directly into the entity. Accept only client-editable fields (e.g., validated status/notes) and ensure the write path has no raw JSON copying that overwrites auditing fields.

A raw-driver mutation can still alter `created_by` if the database role allows it; Java auditing annotations **do not enforce field immutability inside MongoDB Server**. Appropriate write permissions, schemas/policies, and audit architecture are required.

## 9. Actors That Do Not Come from HTTP Requests

Not every write is tied to a user in a web session. Examples:

| Change Source | Desired Actor |
|---|---|
| Employee approving invoice | `user:<stable-id>` |
| Scheduled job syncing statuses | `job:invoice-sync` |
| Kafka consumer processing partner messages | `service:partner-ingest` or verified event actor |
| Historical data migration | `migration:2026-11-schema` |
| Reporting system | `service:reporting` |
| API client with machine credentials | `service:<client-id>` |

If `CurrentActorAuditorAware` only reads `SecurityContextHolder`, a job running via a normal scheduler may receive `Optional.empty()`. That **does not mean the actor is an anonymous user**, rather that the current flow lacks a security identity recognized by the provider.

### 9.1. Three Valid Strategies

1. **Service account authentication**: background work runs with a dedicated authenticated principal and scoped permissions, using a stable service/job ID as actor ID.
2. **Trusted actor execution context**: the job orchestrator provides actor metadata from server configuration rather than untrusted payloads; the provider reads that context in the right lifecycle.
3. **Module-specific auditing provider**: a module dedicated to migrations/jobs uses a fixed actor bean selected via `auditorAwareRef`.

Do not automatically return `"SYSTEM"` for **every** missing security context across both HTTP APIs and background jobs. That can mask authentication configuration errors and sign unauthorized actions with a system identity.

### 9.2. Well-Structured Actor Format

A helpful convention:

~~~text
user:3b2d2f
service:catalog-sync
job:nightly-reconcile
migration:2026-11-audit-backfill
~~~

Prefixes are not a built-in requirement of MongoDB or Spring. They are a **domain convention**, helping readers distinguish actor types and avoid ID collisions across sources.

If you later need frequent queries by actor type, consider a value object like `ActorRef(type, id)` or separate metadata; do not stuff unbounded permissions or PII into a single long string.

### 9.3. System Fallback Must Be an Intentional Policy

A small module acting solely as a migration writer might use:

~~~java
@Component("migrationAuditorAware")
public class MigrationAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("migration:2026-11-backfill");
    }
}
~~~

This snippet assumes the imports `java.util.Optional`, `AuditorAware`, and `@Component` as in section 7. It is meant for a **scoped job/migration context**, not as a default bean replacing user identities across all endpoints.

Do not let `@Component("currentActorAuditorAware")` and `@Component("migrationAuditorAware")` accidentally compete for by-type selection; `auditorAwareRef` specifies which bean to use for a given auditing configuration.

## 10. Thread Switching and SecurityContextHolder Limits

In standard configurations, `SecurityContextHolder` stores security context in a **thread-bound context**. When a service uses:

~~~java
@Async
public void processInvoiceInBackground(...) {
    // Another thread may not share the same SecurityContext.
}
~~~

the actor may no longer be the user from the originating request. Worse, custom `ThreadLocal` variables without cleanup can **leak identities between tasks** on a pooled thread.

### 10.1. Do Not Blindly Copy Security Contexts

Spring Security provides tools such as `DelegatingSecurityContextAsyncTaskExecutor` and context propagation; however, passing a user's privileges to a long-running background job requires an explicit policy:

- Will the user's permissions still be valid hours later when the job runs?
- Is the job authorized for that user's tenant?
- Should the resulting actor be the requesting user or the executing service?
- If a principal is locked or revoked after enqueueing, should it still be used?

Do not dump raw tokens/secrets into job payloads just to "keep the auditor". You can store a verified `requestedByActorId` as **business metadata** while letting the worker run under a service account per a clear contract.

### 10.2. @Async and Transactions

A new thread does not automatically inherit an imperative Spring `@Transactional`/`MongoTransactionManager` context, nor does it automatically inherit the auditor. If a job needs a transaction, open an appropriate transaction boundary **inside the worker** and attach a trusted actor for that worker.

Do not assume an `@Transactional` method in a controller covers writes spawned in a `CompletableFuture`.

### 10.3. Prevent Leaks via Scoped Actor Contexts

If your system truly needs a custom `ActorContext`, use a `try/finally` scope to restore context after execution, or framework-supported task delegation. In reactive pipelines, you must use **Reactor Context** rather than simple thread-local access.

For sensitive audit data, a missing actor is safer than silently attributing the wrong user—and if an actor is mandatory, the request/job should fail and log an explicit error.

## 11. One or Multiple AuditorAware Beans?

In a multi-module monolith, you may have:

~~~text
currentActorAuditorAware : AuditorAware<String>
migrationAuditorAware    : AuditorAware<String>
testActorAuditorAware    : AuditorAware<String> (test scope)
~~~

When the framework needs an `AuditorAware<?>` and multiple candidates exist, injection by type becomes ambiguous. This lesson uses:

~~~java
@EnableMongoAuditing(
    auditorAwareRef = "currentActorAuditorAware")
~~~

to select the exact bean by name.

### 11.1. Do Not Use @Primary to Mask Environment Mistakes

`@Primary` can resolve injection ambiguity, but you should not use it to blindly "win" over other auditors without verification. For auditing, selecting the wrong bean can stamp unintended actors onto every document for a long time.

### 11.2. One Audit Config per Application Context

If the same application context contains multiple `@EnableMongoAuditing` configurations with different providers, registrar/bean conflicts or unpredictable behavior can arise. Do not treat placing auditing annotations per module/package as an automatic mechanism where "each repository uses its own `AuditorAware`".

When actor classification varies by business flow, a **unified identity policy** reflecting the authenticated context—or cleanly separated application contexts—is usually better. If collection-specific auditing is required, build tested custom callbacks/writers instead of expecting the annotation to route per repository.

### 11.3. Inspect Actual Beans

In an integration test or diagnostic check:

~~~java
Map<String, AuditorAware> providers =
        applicationContext.getBeansOfType(AuditorAware.class);
~~~

This snippet assumes `ApplicationContext applicationContext` and imports for `Map`/`AuditorAware`, not a standalone Java file. Inspect **bean names and implementation classes**, not just the count of beans.

## 12. Creation and Update Flows with modifyOnCreate

With the configuration from section 6, suppose two authenticated actors act in sequence:

~~~text
T0 — user-101 creates invoice-101:
  created_by  = user-101
  modified_by = user-101
  created_at  = t0
  updated_at  = t0

T1 — user-205 updates invoice-101:
  created_by  = user-101
  modified_by = user-205
  created_at  = t0
  updated_at  = t1
~~~

This is the target behavior in the **standard entity save path** with auditing enabled and `modifyOnCreate = true`.

### 12.1. Comparing modifyOnCreate

| Setting | Insert | Update |
|---|---|---|
| `modifyOnCreate = true` | Usually sets both created and modified metadata | Updates modified metadata |
| `modifyOnCreate = false` | Sets only created metadata | Updates modified metadata |

Do not use `modifiedBy == null` to infer that a document was never updated: in legacy data, a provider might have returned empty, or an update path might have bypassed auditing. Entity state should be tracked by schema/version and domain invariants rather than audit metadata alone.

### 12.2. Who Is Allowed to Modify createdBy?

Normally, `createdBy` is managed by the persistence layer. Status updates must not alter `createdBy`. However, if a controller accepts a raw document payload and issues a raw update, it can alter this field if it holds database write privileges.

The solution is **DTO allowlisting, service ownership, database permissions, and testing bypass write paths**, not merely placing auditing annotations on the entity.

### 12.3. Why Can Timestamps Be Equal?

On insert, created and modified timestamps may be identical (sharing a single auditing timestamp) depending on provider/configuration. In integration tests, do not enforce `updatedAt > createdAt` right after insert. After an update, depending on precision/clock, check `updatedAt >= createdAt` and/or inject a test clock for strict timestamp assertions.

### 12.4. Auditing and Optimistic Locking Are Separate Mechanisms

`@Version` provides stale-write detection on supported persistence paths. `@LastModifiedBy` records the latest modifying actor. Both can coexist on an entity, yet **the auditor is not a version guard**, and the version does not decide who is authorized to edit.

If two requests update an entity concurrently, one save may fail with an optimistic lock error; do not report that audit metadata was committed just because the callback populated the field before the save was rejected.

## 13. Unit Testing Spring Security AuditorAware

Before connecting to MongoDB, we can test in isolation how `CurrentActorAuditorAware` handles authenticated, anonymous, and principal-free contexts.

**CurrentActorAuditorAwareTest.java**

~~~java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

class CurrentActorAuditorAwareTest {

    private final CurrentActorAuditorAware provider =
            new CurrentActorAuditorAware();

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void authenticatedPrincipalIsReturned() {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "user-101",
                        "no-credential",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_OPERATOR"))));
        SecurityContextHolder.setContext(context);

        assertThat(provider.getCurrentAuditor())
                .contains("user-101");
    }

    @Test
    void emptySecurityContextDoesNotBecomeSystem() {
        SecurityContextHolder.clearContext();

        assertThat(provider.getCurrentAuditor()).isEmpty();
    }

    @Test
    void anonymousTokenIsNotAttributedToAuthenticatedUser() {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                new AnonymousAuthenticationToken(
                        "test-key",
                        "anonymousUser",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_ANONYMOUS"))));
        SecurityContextHolder.setContext(context);

        assertThat(provider.getCurrentAuditor()).isEmpty();
    }
}
~~~

This test does not require MongoDB. It proves the **security-context actor resolution policy**, though it does not yet prove Spring Data auditing actually uses the provider during `repository.insert/save`.

### 13.1. Cases to Expand Upon

- A JWT principal uses the `sub` claim while business logic requires a different internal ID.
- User logs in yet `getName()` is mapped incorrectly.
- A service account has restricted scope; do not confuse it with an end user.
- A context is authenticated, yet the user is disabled/locked mid-way through a long background job.
- Calls run through an executor where the security context is not propagated.
- Two consecutive requests on a thread pool must never see the same actor due to context leakage.

Passing a `getCurrentAuditor()` unit test does not prove an access-control policy is enforced; it only proves the provider handles the context input as coded.

## 14. Integration Testing with an Actor-Switching AuditorAware

This is the most important test: **actor A creates a document, actor B updates it, and raw MongoDB BSON reflects both actors**.

To keep tests decoupled from HTTP authentication, we use a controllable `AuditorAware<String>` inside a **test-only context**. In production, `CurrentActorAuditorAware` from section 7 still reads the actor from Spring Security.

### 14.1. Test-Only Provider

**SwitchingAuditorAware.java — placed in test sources**

~~~java
package com.example.audit;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.data.domain.AuditorAware;

public class SwitchingAuditorAware
        implements AuditorAware<String> {

    private final AtomicReference<String> actor =
            new AtomicReference<>();

    public void useActor(String actorId) {
        actor.set(actorId);
    }

    public void clear() {
        actor.set(null);
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(actor.get());
    }
}
~~~

`AtomicReference` simply drives the fixture in a single test context; it is **not a production-ready actor provider**. If parallel tests share the same bean, two tests can overwrite each other's actor. Run serially or isolate contexts/providers per test.

### 14.2. Test Configuration Independent of Production Security

**InvoiceAuditingIntegrationTest.java**

~~~java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import(InvoiceAuditingIntegrationTest.TestAuditingConfig.class)
class InvoiceAuditingIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    @EnableMongoAuditing(
            auditorAwareRef = "testActorAuditorAware",
            modifyOnCreate = true)
    static class TestAuditingConfig {
        @Bean("testActorAuditorAware")
        SwitchingAuditorAware testActorAuditorAware() {
            return new SwitchingAuditorAware();
        }
    }

    @Autowired AuditInvoiceRepository repository;
    @Autowired MongoTemplate mongo;
    @Autowired SwitchingAuditorAware actor;

    @BeforeEach
    void reset() {
        // Run only against an isolated test database.
        actor.useActor("test:initial");
        repository.deleteAll();
    }

    @Test
    void createdByAndLastModifiedByUseDifferentActors() {
        actor.useActor("user-101");

        AuditInvoice created = repository.insert(
                new AuditInvoice(
                        "invoice-101", "tenant-a", "DRAFT"));

        assertThat(created.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(created.getLastModifiedBy())
                .isEqualTo("user-101");
        assertThat(created.getCreatedAt()).isNotNull();
        assertThat(created.getUpdatedAt()).isNotNull();

        Instant firstCreatedAt = created.getCreatedAt();

        actor.useActor("user-205");
        created.setStatus("APPROVED");
        AuditInvoice updated = repository.save(created);

        assertThat(updated.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(updated.getLastModifiedBy())
                .isEqualTo("user-205");
        assertThat(updated.getCreatedAt())
                .isEqualTo(firstCreatedAt);
        assertThat(updated.getUpdatedAt()).isNotNull();

        AuditInvoice reloaded =
                repository.findById("invoice-101").orElseThrow();
        assertThat(reloaded.getCreatedBy())
                .isEqualTo("user-101");
        assertThat(reloaded.getLastModifiedBy())
                .isEqualTo("user-205");
        assertThat(reloaded.getStatus()).isEqualTo("APPROVED");
    }

    @Test
    void bsonUsesMappedFieldNames() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-102", "tenant-a", "DRAFT"));

        Document raw = mongo.getCollection("audit_invoices")
                .find(new Document("_id", "invoice-102"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("created_by"))
                .isEqualTo("user-101");
        assertThat(raw.getString("modified_by"))
                .isEqualTo("user-101");
        assertThat(raw.containsKey("createdBy")).isFalse();
        assertThat(raw.containsKey("lastModifiedBy")).isFalse();
        assertThat(raw.get("created_at")).isNotNull();
        assertThat(raw.get("updated_at")).isNotNull();
    }

    @Test
    void partialUpdateDoesNotApplyEntityAuditorCallback() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-103", "tenant-a", "DRAFT"));

        actor.useActor("user-999");

        UpdateResult result = mongo.updateFirst(
                Query.query(Criteria.where("id").is("invoice-103")
                        .and("tenantId").is("tenant-a")),
                new Update().set("status", "APPROVED"),
                AuditInvoice.class);

        assertThat(result.getMatchedCount()).isEqualTo(1L);

        Document raw = mongo.getCollection("audit_invoices")
                .find(new Document("_id", "invoice-103"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("modified_by"))
                .isEqualTo("user-101");
        assertThat(raw.getString("status"))
                .isEqualTo("APPROVED");
    }

    @Test
    void multipleTenantIdsRemainSeparateFromActor() {
        actor.useActor("user-101");
        repository.insert(
                new AuditInvoice("invoice-a", "tenant-a", "DRAFT"));
        repository.insert(
                new AuditInvoice("invoice-b", "tenant-b", "DRAFT"));

        assertThat(repository
                .findByIdAndTenantId("invoice-a", "tenant-b"))
                .isEmpty();
        assertThat(repository
                .findByIdAndTenantId("invoice-a", "tenant-a"))
                .isPresent();
    }
}
~~~

### 14.3. Why Must Tests Use a Real MongoDB?

`@DataMongoTest` creates a test slice/context for Spring Data MongoDB, but it **does not start a MongoDB server by itself**. You need a running test MongoDB or Testcontainers, and the connection must point to an isolated test database.

A real test verifies:

1. Auditing infrastructure is registered by `@EnableMongoAuditing`.
2. `auditorAwareRef` picks the exact test bean.
3. `repository.insert/save` triggers auditing via the mapping lifecycle.
4. `@CreatedBy` is not overwritten on normal updates.
5. `@LastModifiedBy` updates when the actor changes.
6. `@Field` maps properly to BSON `created_by`/`modified_by`.
7. `updateFirst` does not behave like entity `save` to run audit callbacks.

Mocking the repository verifies `save` was called, but does not prove Spring Data auditing works or BSON is persisted accurately.

### 14.4. Why Does the Test Not Assert Strictly Increasing Timestamps?

Due to clock resolution, timestamp assignment, or execution speed, two writes can receive identical millisecond timestamps. The test checks that timestamps are present and the creation timestamp stayed unchanged; if you need to assert `updatedAt > createdAt` strictly, inject a controllable `DateTimeProvider`/clock and define the policy.

Never use `Thread.sleep` in integration tests just to "wait for the clock to tick", because it makes tests slow/flaky and does not verify auditing logic.

### 14.5. Separating Test Config from Production Config

In the `@DataMongoTest` example, `TestAuditingConfig` provides the `testActorAuditorAware` bean as a test substitute. If the context also imports production `InvoiceAuditingConfig` with `currentActorAuditorAware` and another `@EnableMongoAuditing`, duplicate registrars/beans or wrong provider selection can occur.

Every test must know **which auditing config is active**; never mix two `@EnableMongoAuditing` configs and guess which bean wins. Testing the real production security actor should belong to a separate suite from integration tests using the switching fixture.

## 15. Write Paths That Do Not Automatically Apply AuditorAware

Auditing operates through the Spring Data lifecycle on supported operations. Other operations may **not** materialize and save an entity, so they do not invoke the auditing callback in the same way.

| Write Path | What Usually Happens | Automatically Guarantees Actor Metadata? |
|---|---|---|
| `MongoRepository.insert(entity)` | Inserts entity through mapper | Supported by auditing |
| `MongoRepository.save(entity)` | Saves entity through mapper | Supported by auditing |
| `MongoTemplate.insert/save(entity)` | Entity mapping path | Supported by auditing |
| `MongoTemplate.updateFirst(query, Update, Entity.class)` | Partial server-side update | **Do not** assume full auditing entity callbacks run |
| `MongoTemplate.updateMulti(...)` | Updates multiple documents | Not equivalent to saving each entity |
| `MongoTemplate.findAndModify(...)` | Find + update in one server operation | Not equivalent to entity save auditing by default |
| `BulkOperations.execute()` | Bulk write models | Does not invoke per-item save callbacks by default |
| `MongoCollection.updateOne(...)` | Raw Java Driver | Bypasses Spring Data entity auditing |
| `MongoCollection.insertOne(Document)` | Raw Java Driver | Bypasses converter/auditing |
| `mongo.remove(query, Entity.class)` | Delete by selector | Does not create a `@DeletedBy` field |

**Implication:** if a module requires accurate `lastModifiedBy` regardless of write path, enforce a **shared policy**: restrict raw writes, build partial-update helpers that explicitly add audit fields, apply proper database validation/authorization, and add integration tests for every path.

### 15.1. Counterexample: updateFirst Does Not Change modifiedBy

~~~java
Query query = Query.query(
        Criteria.where("id").is("invoice-101")
                .and("tenantId").is("tenant-a"));

Update update = new Update()
        .set("status", "PAID");

mongo.updateFirst(query, update, AuditInvoice.class);
~~~

This is a partial update. If `modified_by` is not added to `Update`, do not assume Spring Data runs `@LastModifiedBy` across the **entire entity**. Passing the entity class here only assists query/update mapping; it does not create a `repository.save(entity)` cycle.

### 15.2. Explicit Actor Update During Partial Updates

A controlled approach:

~~~java
Query query = Query.query(
        Criteria.where("id").is(invoiceId)
                .and("tenantId").is(authenticatedTenantId)
                .and("status").is("DRAFT"));

Update update = new Update()
        .set("status", "APPROVED")
        .set("lastModifiedBy", authenticatedActorId)
        .currentDate("updatedAt");

UpdateResult result = mongo.updateFirst(
        query, update, AuditInvoice.class);
~~~

This snippet lives inside a service where `mongo`, `invoiceId`, `authenticatedTenantId`, and `authenticatedActorId` are already authenticated/validated. Because the query/update targets `AuditInvoice.class`, Spring Data maps `lastModifiedBy` to `modified_by` and `updatedAt` to `updated_at` per metadata.

`currentDate("updatedAt")` uses **MongoDB server** time for the update, not necessarily the same clock as `@CreatedDate` supplied by the application. If the domain requires a single clock, choose one strategy and test precision/timezones. Never take `authenticatedActorId` from a client-controlled request body.

### 15.3. Conditional Update Guards State Transitions

Putting `status == DRAFT` in the same update alongside the actor prevents illegal state transitions if another request changed the status concurrently. Reading first and updating by ID afterward introduces a time-of-check/time-of-use race.

Note that `matchedCount == 0` can result from a tenant mismatch, missing ID, or status no longer being DRAFT—do not blindly report "not found" without a proper classification policy.

### 15.4. Version Must Also Be Considered

`@Version` does not automatically share the same semantics across all driver/custom update paths. Some Spring Data versions auto-increment version when an update omits it, yet **that must not be mistaken for full optimistic locking** if the query lacks `expectedVersion`. When version-based CAS is required:

~~~javascript
db.audit_invoices.updateOne(
  {
    _id: "invoice-101",
    tenantId: "tenant-a",
    version: 7,
    status: "DRAFT"
  },
  {
    $set: {
      status: "APPROVED",
      modified_by: "user-205"
    },
    $inc: { version: 1 },
    $currentDate: { updated_at: true }
  }
);
~~~

This is an example BSON query. When using Spring Data template on an `@Version` entity, check whether the framework auto-increments version in updates to avoid **double-incrementing**; each write path needs a clear contract.

## 16. Auditing on Delete and Soft Delete

`@CreatedBy`/`@LastModifiedBy` do not provide a built-in **`@DeletedBy` field** across Spring Data MongoDB delete operations.

Example:

~~~java
mongo.remove(
        Query.query(Criteria.where("id").is(invoiceId)
                .and("tenantId").is(authenticatedTenantId)),
        AuditInvoice.class);
~~~

This deletes by query selector. MongoDB can delete the document without loading the entity for auditing. After physical deletion, any audit metadata stored inside that document is **gone from the collection**.

### 16.1. When You Need to Know Who Deleted?

Several strategies exist:

- **Soft delete:** retain the document and set `deletedAt`, `deletedBy`, and `deletedReason` via a conditional update.
- **Audit event/outbox:** store a deletion event with actor/subject/tenant in the same transaction as the delete if all-or-nothing is required.
- **Change streams:** capture MongoDB changes with resume tokens and pre/post-images if configured/supported, though it lacks business actors unless the application persisted them.
- **Service audit journal:** write an event with request ID/actor/tenant before or inside the transaction, managing reliability and retries.

Soft delete example:

~~~javascript
db.audit_invoices.updateOne(
  {
    _id: "invoice-101",
    tenantId: "tenant-a",
    status: { $ne: "DELETED" }
  },
  {
    $set: {
      status: "DELETED",
      deleted_by: "user-205"
    },
    $currentDate: { deleted_at: true }
  }
);
~~~

`deleted_by` and `deleted_at` in this example are **extended schema fields**, absent from the initial `AuditInvoice`. If implemented, declare the entity fields and search rules (filtering out soft-deleted records), retention/TTL, indexes, and access controls.

### 16.2. Delete Events Are Not a Per-Document Audit Log

A `deleteMany(query)` can delete many documents without emitting events containing each individual deleted entity. Do not use `BeforeDeleteEvent`/`AfterDeleteEvent` to infer the exact actor, subject, and prior state for **each document** in a bulk delete.

### 16.3. Tenant-Scoped Deletion Is a Security Condition

An auditor ID can be accurate while a delete query lacking a tenant filter remains dangerous. `tenantId` must be verified from auth/policy and placed inside **the write/delete predicate itself**, not merely logged in an audit event afterward.

## 17. Auditing in Transactions and Uncertain Commit Outcomes

A transactional method can save multiple documents:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void approveAndCreateNotification(...) {
    invoiceRepository.save(invoice);
    notificationRepository.save(notification);
}
~~~

This is an illustrative architectural snippet: it only applies when both repositories and the transaction manager are properly registered. When transactions actually run on a supported MongoDB topology, both writes commit or roll back together.

**`AuditorAware` can run while preparing the entity before the write, not after commit.** It can return the right actor even when the transaction aborts due to another error. Consequently:

- `getCurrentAuditor()` being called does not prove a new document committed.
- `AfterSaveCallback` or listeners running before commit are not proof of final success either.
- Transaction aborts must be verified against **database state**, not callback invocation counts.
- If the client times out during commit, the outcome may be uncertain; never blindly retry a financial write workflow as a fresh request without an idempotency key.

### 17.1. Post-Write Failure Does Not Clear the Actor on the Java Object

Suppose the auditing callback populates `lastModifiedBy = "user-205"` on the Java entity, and MongoDB subsequently aborts the transaction. The in-memory object still holds the computed metadata, while the database **has no matching commit**.

Do not treat in-memory object state after a rollback as proof that data was saved; re-read in an appropriate session or reconcile outside the transaction per contract.

### 17.2. Transactions Do Not Automatically Cover HTTP, Email, or Kafka

If an auditing actor inside a callback triggers an email saying "user-205 approved", the email can go out before the MongoDB transaction rolls back. Use a **transactional outbox**:

~~~mermaid
flowchart LR
    A["Transactional service"] --> B["Save Invoice with actor"]
    A --> C["Insert OutboxEvent with actor/ID"]
    B --> D["Commit MongoDB transaction"]
    C --> D
    D --> E["Outbox worker"]
    E --> F["Publish event; idempotent consumer"]
~~~

The outbox persists the resolved actor/subject alongside the business change. A worker publishes events post-commit and handles retries/duplicate delivery. Unless the message bus supports end-to-end exact-once, consumers still require idempotency.

### 17.3. Do Not Use the Audit Actor as an Idempotency Key

One user can legitimately perform multiple operations. `lastModifiedBy = "user-205"` does not distinguish two separate requests. Use a dedicated **commandId/requestId**, business key/version, and unique constraint aligned with transactions.

## 18. ReactiveAuditorAware Differs from AuditorAware

Applications using **`ReactiveMongoRepository`** or **`ReactiveMongoTemplate`** use Reactor publishers and a different context from imperative flows. When an actor is needed in a reactive pipeline, Spring Data provides the **`ReactiveAuditorAware<T>`** interface:

~~~java
package org.springframework.data.domain;

import reactor.core.publisher.Mono;

public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

This snippet illustrates the contract; **do not recreate this interface in your source code**. With reactive auditing, do not rely on thread-local `SecurityContextHolder` as the default identity source when requests can switch threads; Spring Security provides `ReactiveSecurityContextHolder`.

### 18.1. Implementing with ReactiveSecurityContextHolder

**ReactiveCurrentActorAuditorAware.java**

~~~java
package com.example.audit.reactive;

import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("reactiveCurrentActorAuditorAware")
public class ReactiveCurrentActorAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(auth -> auth != null
                        && auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> name != null && !name.isBlank());
    }
}
~~~

If the reactive security context is absent or anonymous, the pipeline completes **empty**; do not assume `"SYSTEM"`. `ReactiveAuditorAware` returns `Mono<String>`, not `Optional<String>` as in the imperative provider.

### 18.2. Enabling Reactive Mongo Auditing

~~~java
package com.example.audit.reactive;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactiveCurrentActorAuditorAware")
public class ReactiveAuditingConfig {
}
~~~

Pair with matching reactive MongoDB client/template/repositories. `@EnableReactiveMongoAuditing` does not auto-create clients, servers, or a `SecurityWebFilterChain`.

### 18.3. Context Must Follow the Publisher

~~~java
Mono<AuditInvoice> operation = reactiveRepository
        .save(new AuditInvoice(
                "invoice-301", "tenant-a", "DRAFT"));
~~~

In WebFlux, **return/compose the Publisher** so the framework subscribes and propagates the Reactor Context. Do not call `operation.block()` on an event-loop thread assuming reactive security context behaves like a thread-local.

If you manually call `subscribe()` detached from the request, you can lose context, error handling, and transaction boundaries; use an appropriate orchestrator/job identity.

### 18.4. Reactive Transaction Manager Is a Separate Concern

`ReactiveMongoTransactionManager` manages multi-document transactions in the Reactor Context; `ReactiveAuditorAware` only supplies the actor. The two mechanisms are independent yet can participate in the same reactive write flow. Do not mix up imperative `AuditorAware<String>` and `ReactiveAuditorAware<String>` expecting the framework to bridge contexts automatically.

## 19. DateTimeProvider, Timezones, and Auditing Timestamps

Actor and time must be managed **separately**. A policy can define:

- Actor ID per the identity system.
- Timestamps stored as `Instant`/UTC.
- Display timezones applied only in the UI/reports.
- Tests using a mock clock or `DateTimeProvider` for deterministic assertions.
- Never letting clients pass `createdAt`/`updatedAt` unchecked.

### 19.1. Why Is Instant Suitable?

`Instant` represents a point in time independent of display timezone. BSON Date stores timestamps in millisecond units. If a user in Vietnam views `2026-11-20 15:00 +07:00`, the stored value can be `2026-11-20T08:00:00Z`.

Display formatting by timezone or locale should never modify the actor field or trigger a new write.

### 19.2. Data from Different Clocks

Example:

~~~java
new Update()
        .set("lastModifiedBy", actorId)
        .currentDate("updatedAt");
~~~

In this partial update, the timestamp comes from the MongoDB server. On the repository save path, `@LastModifiedDate` typically relies on the application's auditing provider. If multiple services use different server clocks, skew can occur. Define clear consistency expectations and monitor clock skew; do not use timestamps as surrogate versions when strong CAS is needed.

### 19.3. Audit Timestamps Are Not Business Effective Times

`createdAt` tells you **when the document was created in the system**, not necessarily when an invoice was issued or a business event occurred. If a historical file is imported today, `createdAt` reflects the import per auditing policy, whereas `invoiceIssuedAt` is the business time from the source data.

Do not use auditing dates for every domain timestamp. Similarly, `createdBy` may be the person who ran the import, not the original issuer in the source system.

## 20. Legacy Data and Backfilling Audit Metadata

Many collections have older documents lacking `created_by`/`modified_by`:

~~~json
{
  "_id": "invoice-old",
  "tenantId": "tenant-a",
  "status": "PAID"
}
~~~

Enabling auditing **does not scan the collection to backfill actors on old data**. It only affects lifecycle writes going forward.

### 20.1. Do Not Fabricate Historical User Actors

If you cannot determine who created a historical document, do not make up a specific user just to make fields look complete. Options include:

- `unknown:legacy` when business policy approves and reports understand its meaning;
- `migration:<id>` when the field represents the actor performing the **current backfill**, not the original creator;
- Separate metadata `auditBackfilledBy`/`auditBackfilledAt` to mark the supplementary operation;
- Keeping null and explicitly reporting that history prior to enabling auditing lacks a trusted identity source.

### 20.2. Avoid Overwriting createdBy with an Uncontrolled Save Sweep

Running `repository.save(...)` across every legacy document can:

- Increment versions;
- Overwrite modified metadata with the migration actor;
- Overwrite fields if the entity mapper does not understand parts of an old schema;
- Generate heavy write load;
- Trigger unintended callbacks or domain logic.

Instead, build a **dedicated migration** with clear query filters, batching, and checkpoints, setting only verifiable fields and avoiding altering original creation metadata without evidence. Measure index/build impact and prepare a rollback/backup plan.

### 20.3. Example Backfill with Clear Provenance

~~~javascript
db.audit_invoices.updateMany(
  {
    created_by: { $exists: false },
    tenantId: "tenant-a"
  },
  {
    $set: {
      created_by: "unknown:legacy",
      audit_backfill_id: "migration:2026-11"
    }
  }
);
~~~

This example runs **only when policy explicitly treats historical creators as unknown**. It does not claim the original actor was a real user named `unknown:legacy`; it is an explicit sentinel for missing data. Before production migration, conduct business/legal/retention reviews, backups, and a dry run.

## 21. Security, Privacy, and Integrity of Audit Metadata

Audit fields can be sensitive because they link actions to individuals. A complete policy requires:

1. **Authenticated identity source**: never trust client-supplied actors.
2. **Stable identity**: use immutable IDs; avoid overusing email/displayName.
3. **Read authorization**: not every client should see `createdBy`/`lastModifiedBy`.
4. **Write authorization**: DTOs must not allow arbitrary editing of audit fields.
5. **Tenant isolation**: all queries/writes/deletes take tenant from the server auth context.
6. **Retention**: retain or purge audit metadata per legal and data-governance requirements.
7. **Secrets**: never store passwords, access tokens, session IDs, raw JWTs, or auth payloads in auditing fields.
8. **Logging**: never log entire `Authentication` objects, raw BSON, or unnecessary principal claims.
9. **Migration policy**: never fabricate historical actors.
10. **Integrity evidence**: when immutability/tamper-resistance is required, add an audit ledger/outbox/append-only storage and strict administrative controls.

### 21.1. @CreatedBy Is Not Database Access Control

Someone with direct database privileges can still execute:

~~~javascript
db.audit_invoices.updateOne(
  { _id: "invoice-101" },
  { $set: { created_by: "fake-user" } }
);
~~~

Spring Data auditing annotations do not block this raw MongoDB command. When audit metadata carries legal/compliance significance, enforce database write permissions, journaling, monitoring, change streams/ledgers, and operational controls.

### 21.2. Do Not "Authorize" Solely by Reading createdBy

A rule like "only the creator can edit" is unsafe if the service simply checks `createdBy` after reading and then writes by ID. Under concurrent changes or role policies, a complete write predicate/authorization contract is needed. `createdBy` is one piece of data when evaluating permissions, not an entire security model.

### 21.3. What Actors Should Clients See?

For public APIs, DTOs might return status, timestamps, and pseudonymized IDs instead of internal user IDs/emails. Admin APIs may require dedicated permissions to view audit metadata. Enforce serialization allowlists per endpoint/role; never expose raw MongoDB entities to all users.

## 22. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `@CreatedBy` always null after insert | Auditing not enabled, provider missing, or `Optional.empty()` | Check `@EnableMongoAuditing`, bean name, actor context |
| `@LastModifiedBy` unchanged after `updateFirst` | Partial update bypasses entity auditing | Explicitly add actor/timestamp to `Update` |
| `createdBy` changed on save | Mapper/custom logic overwrote metadata | Check DTOs, lifecycle, and update policy |
| `modifiedBy` populated immediately on insert | `modifyOnCreate = true` | Accept per contract or change config |
| `modifiedBy` null on insert | `modifyOnCreate = false` or actor absent | Verify intended config and provider |
| Every document created by `system` | Global fallback masking real identities | Separate request/user actors from job actors |
| Anonymous requests save `anonymousUser` | Filtering only on `isAuthenticated()` | Exclude `AnonymousAuthenticationToken` or define a public actor |
| Principal changes yet audit keeps old actor | Security context leak or fixed bean | Inspect context lifecycle, provider bean, cleanup |
| JWT user ID mismatches business ID | `getName()` reads a different claim | Configure converter and stable actor ID |
| `@Async` has no auditor | Thread-bound context not propagated | Use intentional actor propagation/job identity |
| Reactive auditing returns empty | Using `SecurityContextHolder` instead of Reactor Context | Use `ReactiveAuditorAware`/`ReactiveSecurityContextHolder` |
| Multiple `AuditorAware` beans cause ambiguity | No specific auditor chosen | Point `auditorAwareRef` to the right bean |
| `@EnableMongoAuditing` has no effect | Config outside component scan or duplicate registrar | Import/scan properly and inspect context |
| Unit test mocks save but runtime audit is null | Mocks do not run mapping callbacks | Write real MongoDB integration tests |
| `@Field("modified_by")` differs from raw BSON | Inconsistent mapping/schema/write path | Inspect raw BSON and field names |
| `@Version` raises stale save | Entity changed since read | Handle optimistic conflict; do not force version |
| Right actor yet wrong tenant | Auditor does not enforce authorization | Add tenant filter/policy to write query |
| Raw driver update alters `createdBy` | Auditing is only Spring infrastructure | Restrict DB privileges, allowlist writes |
| Migration sets all docs to migration actor | Using `save`/audit callback during backfill | Distinguish original actor from backfill/modifier |
| `AfterSave` ran yet DB rolled back | Hook fires before commit | Use outbox/transaction commit verification |
| Timestamp does not visibly increase between saves | Clock/precision or date provider | Test with controlled clock; avoid `sleep` |
| `lastModifiedBy` updated despite unchanged fields | Save triggers audit metadata update | Save only when needed; define "modification" semantics |
| Delete leaves no `deletedBy` | Physical delete removes metadata | Use soft delete, outbox, or audit ledger |
| Secondary replica reads stale actor after write | Replication lag / read preference | Define read consistency contract |

### 22.1. Checklist When createdBy Is Missing

Before adding controller workarounds, verify in order:

1. Entity has `@CreatedBy` on the right field with a compatible type.
2. `@EnableMongoAuditing` infrastructure is present in the application context.
3. `auditorAwareRef` matches the bean name, not just the type.
4. `getCurrentAuditor()` returns `Optional.of(actorId)` at write time.
5. Principal is not anonymous or carrying the wrong user ID.
6. The actual operation is `repository.insert/save` rather than a raw/partial update.
7. MongoDB converter maps the field to BSON properly via `@Field`.
8. Entity is classified new/existing under the intended ID/version strategy.
9. No custom callback or other auditing config overwrites the field.
10. A test against real MongoDB inspects the final raw document.

Do not work around it by setting `createdBy = "admin"` before saving. That can hide a serious authentication or attribution bug.

### 22.2. Distinguishing Context Bugs from Data Bugs

If the provider returns the right actor yet BSON lacks it, the issue lies in auditing registration, mapping, or the write path. If the provider returns empty, the issue lies in the security context, job identity, or bean selection. If BSON is right yet the API omits it, the issue lies in projection, DTO, serialization, or read consistency.

Separating these three layers when debugging avoids misguided fixes: **identity provider → persistence auditing → API representation**.

## 23. Designing Auditing for Production

A safe architecture does not offload every responsibility onto `AuditorAware`. Divide responsibilities clearly:

~~~mermaid
flowchart TD
    A["Authenticated request / verified job"] --> B["Identity + authorization policy"]
    B --> C["Trusted Actor ID and tenant"]
    C --> D["AuditorAware / application context"]
    C --> E["Domain service"]
    D --> F["Spring Data entity auditing"]
    E --> F
    E --> G["Conditional update / transaction / outbox"]
    F --> H["MongoDB document metadata"]
    G --> I["Audit event / business history"]
    H --> J["Monitoring + access policy"]
    I --> J
~~~

### 23.1. Design Decisions to Document

| Decision | Example Contract |
|---|---|
| What is the Actor ID? | Stable user ID or service account ID |
| Who can supply the actor? | Only Spring Security / verified server context |
| Are anonymous writes allowed? | Public creation gets `public:anonymous` or is rejected |
| Who is the job actor? | `job:invoice-sync` |
| Can `createdBy` ever change? | No, except approved migrations with separate audit |
| `modifiedBy` on insert? | Yes if `modifyOnCreate=true` |
| Which clock does `LastModifiedAt` use? | `DateTimeProvider`/UTC for entity saves; explicit policy for raw updates |
| Are there multiple MongoDB writers? | Yes: all writers must follow the audit contract, not rely only on Spring callbacks |
| Does physical deletion need history? | Yes: outbox/ledger/soft delete |
| How long is audit metadata retained? | Per approved legal and retention policies |
| Does actor contain PII? | Prefer stable opaque IDs; restrict exposure |
| What level of evidence is needed? | Metadata vs. append-only event journal |

### 23.2. An Actor Provider Does Not Replace Domain Policy

In an invoice approval service, you must:

1. Verify the principal.
2. Verify the tenant and approval permission.
3. Apply a valid CAS/state transition.
4. Record the audit actor in the same command/lifecycle path.
5. Ensure a transaction if multiple documents are involved.
6. Record a business event with request/command ID if traceability is needed.
7. Handle retries, network errors, unknown commits, and reconciliation.

`AuditorAware` handles **only the actor-supply step**. Separating responsibilities lets the application switch from security sessions to JWT or service identities without rewriting every repository.

### 23.3. When Should You Avoid Automatic Auditing?

If a service performs bulk writes via aggregation pipelines or bulk ops and every write needs an actor, an **explicit update builder/domain repository adding audit fields** can be clearer. If a data model intentionally has no identity (e.g., public aggregate counters), do not attach a fake actor merely so every document has `createdBy`.

Automatic auditing fits the **entity lifecycle**; it does not have to be the metadata mechanism for every MongoDB operation.

## 24. Hands-On Exercises

**Exercise 1 — AuditorAware contract.** Write an `AuditorAware<String>` returning `Optional.of("test-actor")`, then switch to `Optional.empty()`. Explain why null/empty must not default to user `SYSTEM`.

**Exercise 2 — Entity metadata.** Create `AuditInvoice` with `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, `@LastModifiedDate`, `@Version`; use `@Field` to map to snake_case BSON. Inspect the raw document.

**Exercise 3 — Enabling auditing.** Create `@EnableMongoAuditing(auditorAwareRef = "currentActorAuditorAware")`. Intentionally misspell the bean name in a test context to observe the configuration failure, then fix it.

**Exercise 4 — Spring Security identity.** Create a security context with an authenticated `UsernamePasswordAuthenticationToken`; assert the auditor returns the right ID. Then test a null context and an anonymous token.

**Exercise 5 — Stable identity.** Compare storing username/email vs. a stable user ID. Design actor IDs for a system with human users, service accounts, and migration jobs.

**Exercise 6 — Two actors on one document.** Actor A inserts, actor B updates via repository `save`. Verify `createdBy=A`, `lastModifiedBy=B`, and `createdAt` unchanged.

**Exercise 7 — modifyOnCreate.** Run separate tests with `modifyOnCreate=true` and `false` (two independent test contexts), comparing `lastModifiedBy` and `updatedAt` after insert.

**Exercise 8 — Partial update bypass.** Actor B uses `MongoTemplate.updateFirst` updating only status. Verify `modified_by` does not change automatically, then add `set("lastModifiedBy", actorId)` and `currentDate("updatedAt")` in the same write.

**Exercise 9 — Version/optimistic lock.** Two actors read the same DRAFT invoice and save sequentially. Distinguish version conflict from auditing; do not let a callback overwrite version to force a save.

**Exercise 10 — Tenant security.** A user authorized for `tenant-a` attempts to read/edit a `tenant-b` invoice. Test both query and write filters, not just auditor ID.

**Exercise 11 — Job without a principal.** Run a scheduled job in a test with no `SecurityContext`. Pick a dedicated service/job actor or explicitly reject when an actor is mandatory; do not fall back to admin.

**Exercise 12 — @Async actor propagation.** Invoke an operation on another executor. Measure the returned actor and implement lifecycle-safe job identity/propagation, verifying cleanup between two tasks.

**Exercise 13 — ReactiveAuditorAware.** Write a provider using `ReactiveSecurityContextHolder`, enable `@EnableReactiveMongoAuditing`, and test with `StepVerifier`. Do not rely on `ThreadLocal` assuming the actor exists on every scheduler.

**Exercise 14 — Transaction rollback.** On a test MongoDB replica set, save an entity with an actor and throw an exception before commit. Verify data does not appear after rollback and that a pre-commit callback is not a durable audit event.

**Exercise 15 — Outbox.** Add `AuditActionEvent` with command ID, actor, subject ID, tenant, and timestamp. Write the event alongside the invoice change inside a transaction; design an idempotent publisher/consumer.

**Exercise 16 — Soft delete.** Design `deletedBy`/`deletedAt` for a document requiring deletion history. Compare with physical delete (which loses metadata) and outbox storage.

**Exercise 17 — Legacy migration.** A collection has 10,000 documents missing `created_by`. Design a migration with checkpoints, backups, and an actor sentinel, without fabricating original creators or accidentally overwriting modified metadata across all records.

**Exercise 18 — Multi-writer policy.** The same collection is updated by a Spring repository, bulk import, and raw driver. Identify which paths run entity auditing automatically and standardize a process ensuring consistent metadata.

**Exercise 19 — Quality metrics.** Measure the percentage of documents missing `created_by` over time, classify causes (legacy, empty context, raw writes), and define alerts without leaking user IDs into logs.

**Exercise 20 — Audit privacy.** Design API DTOs that expose actor metadata only to authorized roles. Prove regular users cannot overwrite `created_by` via request JSON.

## 25. Key Takeaways

**`AuditorAware<T>` supplies the actor identity for Spring Data MongoDB auditing on the imperative path.** Combine `@CreatedBy`/`@LastModifiedBy` on the entity with `@EnableMongoAuditing(auditorAwareRef = "...")` so the framework populates creator/modifier on supported entity save paths. `getCurrentAuditor()` returns `Optional<T>`; it does not authenticate, authorize, or invent a system user when no principal is present.

In applications using **Spring Security**, you can read `Authentication` from `SecurityContextHolder`, but you must exclude anonymous tokens, map to a **stable actor ID**, and distinguish users, service accounts, jobs, and migrations. Never trust unverified actor IDs from request bodies or headers. For WebFlux/reactive MongoDB, use **`ReactiveAuditorAware<T>` and `ReactiveSecurityContextHolder`** with Reactor Context instead of forcing an imperative provider into a reactive pipeline.

**Entity auditing does not replace database constraints or audit history.** `repository.save` and `MongoTemplate.updateFirst` do not share the same lifecycle; partial updates, bulk writes, and the raw driver can bypass auditing callbacks. When using conditional updates, include actor/timestamp in the **same write** from a verified identity. Actor metadata does not replace `@Version`, tenant authorization, unique indexes, transactions, or idempotency.

Finally, **`createdBy`/`lastModifiedBy` are current-document metadata, not immutable proof of full history**. For critical operations, design audit events/outbox/ledgers and govern commits, retention, and privacy. Verify by testing two-actor transitions, reading raw BSON, checking partial-update bypasses, and testing rollbacks against a real test MongoDB before deploying to production.
