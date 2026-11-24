# Distinguishing Read, Create, Update, Delete, Approve, and Export Data Permissions in Spring Security Authorization

## 1. Objectives

In enterprise data systems, **being able to see a record does not mean a user is allowed to create, update, delete, approve, or export that record**. The six actions have different business impacts, risks, and control targets. If you lump all of them into a single `DATA_ACCESS` permission or rely solely on `ROLE_USER`, the application may unintentionally allow unauthorized data modification, self-approval of transactions, or bulk data extraction.

This lesson belongs to the **Data Permissions** group of Spring Security Authorization. After studying it, you will be able to:

1. Clearly define **READ, CREATE, UPDATE, DELETE, APPROVE, EXPORT** and distinguish them from HTTP verbs.
2. Design permissions by **action + resource type + specific object + tenant + state + data fields**.
3. Use Spring Security Method Security (`@EnableMethodSecurity`, `@PreAuthorize`) combined with a policy bean to control each operation.
4. Apply *least privilege*, *deny by default*, and *separation of duties* (the creator cannot self-approve).
5. Control data export as a separate permission, with scope limits, exportable fields, formatting, auditing, and revocability.
6. Write Java 17+ tests covering both allow and deny paths, specifically proving **the method body does not execute when before-authorization denies**.
7. Identify flaws such as IDOR/BOLA, mass assignment, conflating READ with EXPORT, approving in invalid states, filtering data after pagination, and TOCTOU.

**Illustrative context:** a multi-tenant `Document` system with owners, content, sensitivity labels, and states `DRAFT → SUBMITTED → APPROVED`. Java 17+, Spring Boot BOM 3.5.0, Spring Security 6.5.x, JUnit 5; this is **an example policy**, not six permissions pre-defined by Spring Security.

## 2. Six Non-Equivalent Operations

| Operation | Policy Question | Illustrative Conditions | Impact / Risk |
| --- | --- | --- | --- |
| **READ — Read** | Who can view **which records and which fields**? | Has `DOC_READ`; right tenant; sensitive documents need extra conditions | Exposing others' content/metadata |
| **CREATE — Create** | Who can create records **in which scope**? | Has `DOC_CREATE`; permitted tenant; owner assigned from trusted identity | Creating data in wrong tenant, spoofing owner |
| **UPDATE — Update** | Who can edit **which record, which fields, when**? | Has `DOC_UPDATE`; is owner; record is DRAFT; edit valid content only | Unauthorized changes to permissions, state, sensitive values |
| **DELETE — Delete** | Who can delete, in what mode, with what retention rules? | Has `DOC_DELETE`; is owner; DRAFT only; retention check | Data loss, destroying evidence/audit |
| **APPROVE — Approve** | Who can transition **SUBMITTED → APPROVED**? | Has `DOC_APPROVE`; approver differs from creator; right tenant | Self-approval, bypassing two-person control |
| **EXPORT — Export** | Who can take data **out of normal viewing scope**? | Has `DOC_EXPORT` **and** read permission on exported rows; approved, exportable data only | Bulk PII extraction, file leaks, sensitive data exfiltration |

`DOC_*` names are **application-defined authority conventions**. In Spring Security, `hasAuthority('DOC_READ')` matches the exact authority name `DOC_READ`; it does not implicitly infer `DOC_EXPORT`. Using `hasRole('REVIEWER')` by default looks up authority `ROLE_REVIEWER`, not all the granular permissions above.

### 2.1. Permissions Do Not Automatically Imply "Higher" Ones

The following conclusions are **unsafe unless explicitly declared by policy**:

- Having `READ` does not mean having `EXPORT`; viewing one record in the UI differs from extracting 10,000 records into a file.
- Having `CREATE` does not mean having `UPDATE` on every record of that type, nor does it mean submitting arbitrary owner/tenant values.
- Having `UPDATE` does not mean changing status to `APPROVED`; approval must be an independent action.
- Having `APPROVE` does not mean self-approving documents one submitted.
- Having `DELETE` does not implicitly allow deleting approved documents or permanently purging records subject to retention requirements.
- Having `ROLE_ADMIN` should also not be turned into "every operation allowed" if the system requires separation of duties and auditing.
- Having `EXPORT` without `READ` should not allow exporting contents of records the user is not allowed to view.

You can map **role → set of authorities** with RBAC, yet the final effective permission should still enforce constraints at the object, tenant, state, and field levels.

## 3. Policies Must Answer Six Dimensions, Not Just One Role

A data authorization decision is conceptually expressed as:

```text
ALLOW =
    valid identity
    AND has permission to perform ACTION
    AND within tenant / organization scope
    AND permitted on the specific RESOURCE
    AND workflow state allows ACTION
    AND permitted set of fields / data subset
    AND no violation of other business conditions
```

This is a **conceptual illustration**, not required SpEL syntax. A real policy may have many action-dependent conditions.

| Dimension | Question to Check | Failure When Omitted |
| --- | --- | --- |
| Subject | Who is calling? User, service account, job? | Trusting request-supplied username/owner |
| Action | READ or EXPORT? UPDATE or APPROVE? | Granting the wrong function |
| Resource | Which ID, does the object exist? | Swapping IDs to read/edit another resource |
| Tenant/scope | Does the record belong to a permitted scope? | Cross-customer access |
| Workflow | DRAFT, SUBMITTED, APPROVED, ARCHIVED? | Editing/deleting after approval, invalid state transition |
| Fields/volume/destination | Which fields, how many rows, where does the file go? | PII exposure, mass assignment, out-of-scope export |

**Three control layers usually go together:**

1. **Function-level:** is the user allowed to invoke `exportReports` or `approveDocument`?
2. **Object-level:** does the user have permission on `Document#123` in the corresponding tenant?
3. **Property-level:** even when READ is allowed, should fields like `salary`, `nationalId`, or `internalNote` be exposed?

OWASP classifies these risks as **API5 Broken Function Level Authorization**, **API1 Broken Object Level Authorization**, and **API3 Broken Object Property Level Authorization**. An API that is valid at the function level can still be broken at the object or property level.

## 4. Reading Data — READ

Reading covers viewing details, viewing lists, viewing metadata, aggregate queries, or loading previews. It is an **information access permission**, not a license to modify or bulk-export.

Examples:

- Alice has `DOC_READ` on tenant A: reads public documents of tenant A.
- Alice lacks read permission on tenant B: changing `GET /documents/123` to an ID in tenant B must be denied (or return 404 under an existence-hiding policy).
- Alice has `DOC_READ` but lacks `DOC_SENSITIVE_READ`: cannot read fields/text of others' `sensitive=true` documents.
- Sensitive fields may require a separate DTO or redaction even when public metadata is readable.

**Enforce authorization before returning content.** `@PreAuthorize` can use the object ID to check via a trusted policy/repository. `@PostAuthorize` can inspect `returnObject`, but the method has already executed before evaluation; do not use it as a guarantee that data was never queried, logged, or caused side effects.

### 4.1. Reading Lists and Pagination

An easily missed spot is `listDocuments(pageable)`:

- Filtering permissions only in the frontend (hiding rows) **does not protect the API**.
- `@PostFilter` after loading a page can produce under-filled pages and wrong total counts.
- For large lists, prefer **WHERE tenant_id = ... AND policy-condition ...** in the repository/query or a well-designed row-level security model, then return only permitted DTOs/fields.
- When querying across multiple resources, verify whether joins, search, counts, aggregates, or autocomplete leak data the user cannot read.

Never allow modifying `sort`, filters, GraphQL selections, or IDs in queries to bypass resource controls.

## 5. Creating Data — CREATE

At CREATE time, **the object does not yet exist**, so you cannot merely check an ACE on the new record itself. Conditions usually rely on the creation scope: tenant, project, folder, quota, document type, and permission to create that type.

```text
POST /tenants/TENANT_A/documents
   |
   +--> current principal has DOC_CREATE?
   +--> principal allowed to create in TENANT_A?
   +--> document type and initial state allowed?
   +--> payload only contains client-declarable fields?
   |
   +--> server sets owner = authentication.name
   +--> server sets status = DRAFT
```

**Never trust `tenantId`, `ownerId`, `approved`, `createdBy`, `role`, or `aclEntries` from JSON** as self-asserted permission fields. Use an allowlist DTO containing only user-editable fields, then assign owner, verified tenant, createdAt, and status on the server.

In an ACL system, CREATE may also need to create the ACL and initial ACEs. Define transactions/lifecycle clearly: creating the domain object without its ACL, or vice versa, can leave inconsistent permissions.

## 6. Updating Data — UPDATE

Updating must check both **UPDATE permission** and **which fields may be modified**. Avoid using `PUT /documents/{id}` and binding the entire entity from the request directly to the database.

For example, an author may edit `text` on a DRAFT document, but must not modify `owner`, `tenant`, `approvedBy`, `status`, or `sensitive` via the same endpoint. If the payload is automatically merged into the entity, an attacker could send `"status": "APPROVED"` to bypass the approval workflow—a form of *mass assignment*.

Illustrative policy:

```text
canUpdate(actor, doc)
  = actor has DOC_UPDATE
    AND doc.tenant == tenant(actor)
    AND doc.owner == actor.username
    AND doc.status == DRAFT
```

In a real product, also check version/optimistic locking to prevent a user from editing a record that someone else approved **after the check but before the write**. Update APIs should explicitly model **operations and field whitelists**, never accepting "edit everything" under one broad permission.

## 7. Deleting Data — DELETE

DELETE usually carries greater risk than UPDATE: it may mean permanent deletion, soft delete, archiving, or queuing for purge. Clarify:

- **Who can delete?** Author, data administrator, or delegated user.
- **When can it be deleted?** Is deleting DRAFT allowed? Does APPROVED require a separate revocation/cancellation workflow?
- **How is it deleted?** Soft delete, tombstone, hard delete, or retention purge.
- **Side effects?** ACLs, attachments, search index, downstream events, audit logs, backups.
- **Does restoration require a separate permission?** RESTORE is not implicitly granted by DELETE.

In the Java example, DELETE allows **only the owner to delete a DRAFT** to demonstrate the principle. The example removes the record from an in-memory map and does not simulate full soft delete/audit/retention. Production needs transactions, auditing, retention policies, and race condition protection.

Do not infer permissions from HTTP `DELETE`: the HTTP method name is an endpoint signal, not a substitute for business authorization. An endpoint like `POST /documents/{id}/remove` must enforce equivalent DELETE checks.

## 8. Approving Data — APPROVE

APPROVE is a **business state transition** after checking conditions; it is completely different from editing content. Example:

```text
DRAFT ---submit---> SUBMITTED ---approve---> APPROVED
  ^                    |
  |                    +---reject---> REJECTED
  |
  +-------- revise <---+
```

A workflow may involve multiple approval tiers, maker-checker, digital signatures, or amount verification. This lesson's simple example only approves `SUBMITTED → APPROVED`.

Minimal illustrative policy:

```text
canApprove(actor, doc)
  = actor has DOC_APPROVE
    AND same tenant
    AND doc.status == SUBMITTED
    AND doc.owner != actor.username
```

The final condition is **separation of duties (SoD)**: the creator cannot self-approve their own record, even if by authority they hold both DOC_UPDATE and DOC_APPROVE. NIST describes SoD as a mechanism preventing a single person from having enough privileges to execute and validate an entire sensitive operation alone.

Additional checks needed in a real system:

- The approver is not the submitter, nor in a conflicted actor set.
- The record is not already approved or rejected; duplicate approvals must have clear idempotency rules.
- Business validations pass; content version has not changed since submission.
- Record `approvedBy`, `approvedAt`, version, and audit; publish events **after commit** when needed.
- `REJECT`, `REVOKE_APPROVAL`, and `PUBLISH` may be **independent permissions**—never derive all of them from APPROVE.

If you only have `@PreAuthorize("hasAuthority('DOC_APPROVE')")` without checking owner/status, you have not implemented sufficient approval rules.

## 9. Exporting Data — EXPORT

**EXPORT is a separate capability, not an alias for READ.** Being allowed to open a record on screen does not automatically allow downloading CSV/Excel/JSON/PDF files containing hundreds or thousands of records, especially when PII, financial, health, or other customer data is involved.

An export request must check **two layers**:

1. **Functional permission:** does the caller have `DOC_EXPORT`? Does policy require re-authentication, MFA, or export approval?
2. **Per-data permission:** does the caller have READ on every row, every tenant, and every field included in the file?

Sample policy in Java:

```text
canExport(actor, doc)
  = actor has DOC_EXPORT
    AND canRead(actor, doc)
    AND doc.status == APPROVED
    AND doc.sensitive == false
```

This is a **cautious illustrative policy**: even a user with `DOC_SENSITIVE_READ` still cannot export sensitive documents. An organization can add a `DOC_SENSITIVE_EXPORT` permission and a dedicated approval/review step, but must define and test it explicitly rather than letting the system "inherit" from READ.

### 9.1. Boundaries to Check When Exporting

| Boundary | What to Check |
| --- | --- |
| Request | Caller, tenant, reason, export type, dedicated permission, rate/frequency |
| Query | Only rows permitted for READ, tenant scope, never return whole table and filter client-side |
| Field | Explicit column allowlist; never accidentally export `passwordHash`, `internalNote`, PII |
| Volume | Row limits, file size, jobs per hour, timeouts |
| Format | CSV/Excel injection, encoding, escaping, formulas, and metadata |
| Delivery | Download URL with expiry, job ownership, file encryption, bucket access |
| Audit | Who exported, when, which data/scope, policy version, purpose |
| Lifecycle | File retention period, deletion, link revocation, handling running export jobs |

**CSV formula injection:** if user content is placed into CSV columns, spreadsheet apps may interpret cells starting with `=`, `+`, `-`, `@` as formulas. Format/escape according to rules and target reader software; do not assume wrapping CSV cells in quotes handles every case.

The Java example below intentionally exports **three system-controlled fields** (`id,tenant,state`), omitting `text`; it illustrates permissions and *data minimization*, **not** a production CSV library for arbitrary untrusted content.

### 9.2. Asynchronous Exports

If a job is created to export a file minutes later, checking permissions **at job submission time** alone may not suffice: while waiting, the user's permissions might be revoked, or records might change tenant or be marked sensitive. Design a policy to re-check at processing time and/or download time—per security requirements—along with job ownership, expiry, and audit. Never let user B access user A's link just by guessing the job ID.

## 10. Illustrative Permission and State Matrix

Assume tenant A has documents:

- `#1`: owner Alice, `DRAFT`, public.
- `#2`: owner Alice, `SUBMITTED`, public.
- `#4`: owner Bob, `APPROVED`, public.
- `#5`: owner Bob, `APPROVED`, **sensitive**.
- `#6`: owner Outsider, tenant B, `APPROVED`.
- `#7`: owner Bob, `DRAFT`, public.

With the corresponding authorities, results are:

| Request | Result | Why? |
| --- | --- | --- |
| Alice READ #4 with DOC_READ | Allow | Same tenant, non-sensitive |
| Alice READ #6 with DOC_READ | Deny | Cross-tenant |
| Alice READ #5 with DOC_READ only | Deny | Sensitive, not owner / lacks extra permission |
| Alice CREATE tenant A with DOC_CREATE | Allow | Valid scope, server assigns owner Alice |
| Alice CREATE tenant B with DOC_CREATE | Deny | Cannot create outside tenant |
| Alice UPDATE #1 with DOC_UPDATE | Allow | Alice's own draft |
| Alice UPDATE #7 with DOC_UPDATE | Deny | Draft belongs to Bob |
| Alice UPDATE #2 with DOC_UPDATE | Deny | Already SUBMITTED |
| Alice DELETE #1 with DOC_DELETE | Allow | Right owner, DRAFT |
| Bob DELETE #4 with DOC_DELETE | Deny | APPROVED, requires a different workflow |
| Manager APPROVE #2 with DOC_APPROVE | Allow | SUBMITTED, different from creator |
| Alice APPROVE #2 with DOC_APPROVE | Deny | Self-approval |
| Alice EXPORT #4 with READ + EXPORT | Allow | Public, APPROVED, same tenant |
| Alice EXPORT #4 with READ only | Deny | Missing EXPORT |
| Alice EXPORT #5 with READ + SENSITIVE_READ + EXPORT | Deny | Example forbids exporting sensitive data |
| Alice EXPORT #1 with READ + EXPORT | Deny | DRAFT |

This is a **design matrix for learning**, not a Spring default. Keep these rules in a tested policy and use it consistently across controllers, services, jobs, and data access.

## 11. Implementing Spring Security Method Security

Spring Security 6.5 activates method authorization when `@EnableMethodSecurity` is present. For methods on a **Spring-managed bean**, `@PreAuthorize` can call a separate Java bean in SpEL:

```java
@PreAuthorize("@dataPolicy.canUpdate(authentication, #id)")
public Document update(@P("id") long id, String text) {
    // Runs only after the policy allows it.
}
```

`authentication` comes from the method security expression context; `#id` comes from the parameter annotated with `@P("id")`. The `dataPolicy` bean must be registered with the matching name in the Spring ApplicationContext.

**Do not only check `hasAuthority` at the endpoint.** `DataPolicy` must also read the record **server-side** to verify tenant, owner, state, and sensitivity. Never trust client-submitted `owner`, `tenant`, or `approved` fields.

### 11.1. Path Through the Proxy

```text
Controller -> DataService Spring proxy
              |
              v
         @PreAuthorize
              |
              +-- deny -> AccessDeniedException
              |          body has not executed
              |
              +-- allow -> DataService.method(...)
                            -> repository / transaction / event
```

Spring AOP proxies do not automatically intercept `this.update(...)` on internal calls within the same target. Route sensitive actions across a clear Spring bean boundary and test the real call paths. Also do not treat `@PostAuthorize` as a safe substitute for pre-checks on UPDATE/DELETE/APPROVE.

### 11.2. Authorization, Validation, and Transactions Are Three Different Things

1. **Authorization** decides whether the user has permission for the action/object.
2. **Validation** checks whether the payload conforms to schema and business rules (length, required fields, format).
3. **Transactions/concurrency** ensure state updates correctly when multiple requests contend.

`@PreAuthorize` typically runs **before** the method body, but does not replace row locking, version checks, or transactions. If a record transitions from SUBMITTED to APPROVED between pre-check and update, the call must handle conflict/stale state properly instead of silently approving twice. For high-risk data, perform policy/state checks inside a transaction/locked resource and keep the pre-check as an additional defense layer.

## 12. Complete Tested Java 17+ Project

The example uses real Spring Security via `@SpringJUnitConfig`, with an **in-memory** repository to focus on the six-permission policy. It needs no database or web server. In production, replace the repository with JPA/JDBC and add real transactions, locking, and auditing.

### 12.1. Layout

```text
data-actions-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/DataActionsSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'data-actions-demo'
```

`build.gradle`:

```groovy
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
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Requires Gradle with JDK 17+ and access to download dependencies from Maven Central. This project does not need `@SpringBootTest`: `@SpringJUnitConfig` creates the exact context for security method interceptors, so no HTTP `SecurityFilterChain` configuration is required.

### 12.2. Complete Java Test Code

Create `src/test/java/demo/DataActionsSecurityTest.java`:

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(DataActionsSecurityTest.Config.class)
public class DataActionsSecurityTest {

    @Autowired DataService service;
    @Autowired Store store;
    @Autowired Probe probe;

    @BeforeEach
    void resetFixtures() {
        store.reset();
        probe.reset();
    }

    enum State { DRAFT, SUBMITTED, APPROVED }

    public record Doc(
        long id, String tenant, String owner,
        State state, boolean sensitive, String text
    ) {}

    public record ReadView(long id, State state, String text) {}

    public static class Store {
        private final Map<Long, Doc> records =
            new ConcurrentHashMap<>();
        private final AtomicLong nextId = new AtomicLong(1000);

        void reset() {
            records.clear();
            nextId.set(1000);
            put(new Doc(1L, "TENANT_A", "alice",
                State.DRAFT, false, "Alice draft"));
            put(new Doc(2L, "TENANT_A", "alice",
                State.SUBMITTED, false, "Alice submission"));
            put(new Doc(3L, "TENANT_A", "bob",
                State.SUBMITTED, false, "Bob submission"));
            put(new Doc(4L, "TENANT_A", "bob",
                State.APPROVED, false, "Public report"));
            put(new Doc(5L, "TENANT_A", "bob",
                State.APPROVED, true, "Sensitive report"));
            put(new Doc(6L, "TENANT_B", "outsider",
                State.APPROVED, false, "Tenant B report"));
            put(new Doc(7L, "TENANT_A", "bob",
                State.DRAFT, false, "Bob draft"));
        }

        private void put(Doc doc) {
            records.put(doc.id(), doc);
        }

        public Doc get(long id) {
            return records.get(id);
        }

        public int count() {
            return records.size();
        }

        Doc create(String tenant, String owner, String text) {
            long id = nextId.incrementAndGet();
            Doc created = new Doc(
                id, tenant, owner, State.DRAFT, false, text);
            records.put(id, created);
            return created;
        }

        Doc update(long id, String text) {
            return records.compute(id, (key, doc) -> {
                if (doc == null || doc.state() != State.DRAFT) {
                    throw new IllegalStateException("Stale update");
                }
                return new Doc(
                    doc.id(), doc.tenant(), doc.owner(),
                    doc.state(), doc.sensitive(), text);
            });
        }

        boolean delete(long id) {
            Doc existing = records.get(id);
            if (existing == null || existing.state() != State.DRAFT) {
                throw new IllegalStateException("Stale delete");
            }
            return records.remove(id, existing);
        }

        Doc approve(long id) {
            return records.compute(id, (key, doc) -> {
                if (doc == null || doc.state() != State.SUBMITTED) {
                    throw new IllegalStateException("Stale approve");
                }
                return new Doc(
                    doc.id(), doc.tenant(), doc.owner(),
                    State.APPROVED, doc.sensitive(), doc.text());
            });
        }
    }

    public static class Probe {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();

        void mark(String action) {
            calls.computeIfAbsent(
                action, name -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger counter = calls.get(action);
            return counter == null ? 0 : counter.get();
        }

        void reset() {
            calls.clear();
        }
    }

    public static class DataPolicy {
        private final Store store;

        // Only a trusted server-side fixture for the demo.
        // Production uses a tenant verified from identity/DB.
        private static final Map<String, String> USER_TENANTS = Map.of(
            "alice", "TENANT_A",
            "bob", "TENANT_A",
            "manager", "TENANT_A",
            "auditor", "TENANT_A",
            "outsider", "TENANT_B"
        );

        public DataPolicy(Store store) {
            this.store = store;
        }

        private boolean has(Authentication auth, String authority) {
            return auth != null
                && auth.isAuthenticated()
                && auth.getAuthorities().stream().anyMatch(
                    a -> authority.equals(a.getAuthority()));
        }

        private String tenant(Authentication auth) {
            return auth == null ? null
                : USER_TENANTS.get(auth.getName());
        }

        private boolean sameTenant(Authentication auth, Doc doc) {
            String assigned = tenant(auth);
            return doc != null && assigned != null
                && assigned.equals(doc.tenant());
        }

        public boolean canRead(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_READ")
                && sameTenant(auth, doc)
                && (!doc.sensitive()
                    || doc.owner().equals(auth.getName())
                    || has(auth, "DOC_SENSITIVE_READ"));
        }

        public boolean canCreate(
                Authentication auth, String requestedTenant) {
            String assigned = tenant(auth);
            return has(auth, "DOC_CREATE")
                && assigned != null
                && assigned.equals(requestedTenant);
        }

        public boolean canUpdate(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_UPDATE")
                && sameTenant(auth, doc)
                && doc.owner().equals(auth.getName())
                && doc.state() == State.DRAFT;
        }

        public boolean canDelete(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_DELETE")
                && sameTenant(auth, doc)
                && doc.owner().equals(auth.getName())
                && doc.state() == State.DRAFT;
        }

        public boolean canApprove(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_APPROVE")
                && sameTenant(auth, doc)
                && doc.state() == State.SUBMITTED
                && !doc.owner().equals(auth.getName());
        }

        public boolean canExport(Authentication auth, long id) {
            Doc doc = store.get(id);
            return has(auth, "DOC_EXPORT")
                && canRead(auth, id)
                && doc.state() == State.APPROVED
                && !doc.sensitive();
        }
    }

    public static class DataService {
        private final Store store;
        private final Probe probe;

        public DataService(Store store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @PreAuthorize("@dataPolicy.canRead(authentication, #id)")
        public ReadView read(@P("id") long id) {
            probe.mark("READ");
            Doc doc = store.get(id);
            return new ReadView(
                doc.id(), doc.state(), doc.text());
        }

        @PreAuthorize(
            "@dataPolicy.canCreate(authentication, #tenant)"
        )
        public Doc create(
                @P("tenant") String tenant, String text) {
            probe.mark("CREATE");
            String owner = SecurityContextHolder.getContext()
                .getAuthentication().getName();
            return store.create(tenant, owner, text);
        }

        @PreAuthorize("@dataPolicy.canUpdate(authentication, #id)")
        public Doc update(@P("id") long id, String text) {
            probe.mark("UPDATE");
            return store.update(id, text);
        }

        @PreAuthorize("@dataPolicy.canDelete(authentication, #id)")
        public boolean delete(@P("id") long id) {
            probe.mark("DELETE");
            return store.delete(id);
        }

        @PreAuthorize("@dataPolicy.canApprove(authentication, #id)")
        public Doc approve(@P("id") long id) {
            probe.mark("APPROVE");
            return store.approve(id);
        }

        @PreAuthorize("@dataPolicy.canExport(authentication, #id)")
        public String exportCsv(@P("id") long id) {
            probe.mark("EXPORT");
            Doc doc = store.get(id);
            // Export only selected columns, never text/sensitive.
            return "id,tenant,state\n" +
                doc.id() + "," + doc.tenant() + "," +
                doc.state() + "\n";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {
        @Bean
        Store store() {
            return new Store();
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean("dataPolicy")
        DataPolicy dataPolicy(Store store) {
            return new DataPolicy(store);
        }

        @Bean
        DataService dataService(Store store, Probe probe) {
            return new DataService(store, probe);
        }
    }

    @Test
    void serviceIsReallyProtectedBySpringAop() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readPublicDocumentInSameTenantIsAllowed() {
        assertThat(service.read(4L).text())
            .isEqualTo("Public report");
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readAcrossTenantIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.read(6L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readSensitiveOtherOwnerIsDenied() {
        assertThatThrownBy(() -> service.read(5L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_SENSITIVE_READ"}
    )
    void sensitiveReadNeedsExtraAuthority() {
        assertThat(service.read(5L).text())
            .isEqualTo("Sensitive report");
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_CREATE")
    void createAllowedInOwnTenantAssignsTrustedOwner() {
        Doc created = service.create("TENANT_A", "New draft");
        assertThat(created.owner()).isEqualTo("alice");
        assertThat(created.tenant()).isEqualTo("TENANT_A");
        assertThat(created.state()).isEqualTo(State.DRAFT);
        assertThat(probe.count("CREATE")).isEqualTo(1);
        assertThat(store.count()).isEqualTo(8);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_CREATE")
    void createInOtherTenantIsDenied() {
        assertThatThrownBy(
            () -> service.create("TENANT_B", "Malicious"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.count()).isEqualTo(7);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readPermissionDoesNotGrantCreate() {
        assertThatThrownBy(
            () -> service.create("TENANT_A", "No create"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void ownerCanUpdateDraftTextOnly() {
        Doc changed = service.update(1L, "Changed");
        assertThat(changed.text()).isEqualTo("Changed");
        assertThat(changed.owner()).isEqualTo("alice");
        assertThat(changed.state()).isEqualTo(State.DRAFT);
        assertThat(probe.count("UPDATE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void cannotUpdateAnotherOwnersDraft() {
        assertThatThrownBy(() -> service.update(7L, "Attack"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(7L).text()).isEqualTo("Bob draft");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void cannotUpdateSubmittedDocument() {
        assertThatThrownBy(
            () -> service.update(2L, "Late edit"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(2L).text())
            .isEqualTo("Alice submission");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_DELETE")
    void ownerCanDeleteOnlyOwnDraft() {
        assertThat(service.delete(1L)).isTrue();
        assertThat(store.get(1L)).isNull();
        assertThat(probe.count("DELETE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_DELETE")
    void cannotDeleteAnotherOwnersDraft() {
        assertThatThrownBy(() -> service.delete(7L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(7L)).isNotNull();
        assertThat(probe.count("DELETE")).isZero();
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_DELETE")
    void cannotDeleteApprovedDocumentEvenWhenOwner() {
        assertThatThrownBy(() -> service.delete(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(4L)).isNotNull();
    }

    @Test
    @WithMockUser(username = "manager", authorities = "DOC_APPROVE")
    void separateApproverCanApproveSubmittedDocument() {
        Doc result = service.approve(2L);
        assertThat(result.state()).isEqualTo(State.APPROVED);
        assertThat(probe.count("APPROVE")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_APPROVE")
    void creatorCannotApproveOwnDocument() {
        assertThatThrownBy(() -> service.approve(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.get(2L).state())
            .isEqualTo(State.SUBMITTED);
        assertThat(probe.count("APPROVE")).isZero();
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void readAuthorityDoesNotGrantApproval() {
        assertThatThrownBy(() -> service.approve(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("APPROVE")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_EXPORT"}
    )
    void exportApprovedPublicDocumentIsAllowed() {
        assertThat(service.exportCsv(4L)).isEqualTo(
            "id,tenant,state\n4,TENANT_A,APPROVED\n");
        assertThat(probe.count("EXPORT")).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readAuthorityAloneDoesNotGrantExport() {
        assertThatThrownBy(() -> service.exportCsv(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EXPORT")
    void exportAuthorityAloneDoesNotGrantRead() {
        assertThatThrownBy(() -> service.exportCsv(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {
            "DOC_READ", "DOC_SENSITIVE_READ", "DOC_EXPORT"
        }
    )
    void sensitiveDocumentCannotBeExportedByThisPolicy() {
        assertThatThrownBy(() -> service.exportCsv(5L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"DOC_READ", "DOC_EXPORT"}
    )
    void draftDocumentCannotBeExported() {
        assertThatThrownBy(() -> service.exportCsv(1L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("EXPORT")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminRoleDoesNotImplicitlyGrantAllActions() {
        assertThatThrownBy(() -> service.read(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "unknown", authorities = "DOC_READ")
    void unknownTenantCannotReadAnyDocument() {
        assertThatThrownBy(() -> service.read(4L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingObjectIsDeniedWithoutExecutingRead() {
        assertThatThrownBy(() -> service.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }
}
```

### 12.3. Run Command

In the directory containing `build.gradle`:

```bash
gradle test --tests demo.DataActionsSecurityTest
```

If the project has a Gradle Wrapper: use `./gradlew test --tests demo.DataActionsSecurityTest` on Linux/macOS or `gradlew.bat test --tests demo.DataActionsSecurityTest` on Windows.

**Expected result:** all **25 JUnit tests** pass and Gradle finishes with `BUILD SUCCESSFUL`. This is the **expected result based on the code**; it is not a log collected from an actual Java run. Detailed report: `build/reports/tests/test/index.html`.

### 12.4. Which Tests Prove Permission Differences?

| Test Group | Evidence |
| --- | --- |
| READ public/cross-tenant/sensitive | Read permission still depends on scope and sensitivity |
| CREATE own tenant/other tenant/READ-only | CREATE needs authority and scope, owner set from identity |
| UPDATE owner draft/other owner/submitted | UPDATE is not APPROVE and cannot edit all states |
| DELETE own draft/other draft/approved | DELETE is independent of UPDATE, with state constraints |
| APPROVE manager/own document/missing authority | SoD, state, and independent approval permission |
| EXPORT valid/READ only/EXPORT only/sensitive/draft | EXPORT requires both functional and per-data permissions |
| ADMIN role/unknown principal/missing ID | No implicit privilege inference; fail closed on missing data |
| Proxy assertion and Probe | Spring AOP is active and deny happens before the method body |

**Why is `Probe` important?** A test checking only the exception could miss side effects that happened beforehand. Here, when `@PreAuthorize` denies, the action counter does not increment; that proves **the method body was never invoked** along the Spring proxy path.

**What the demo does not guarantee:** the repository is a `ConcurrentHashMap`, without JPA transactions, audit loggers, row locks, pagination, export queues, content-aware CSV escaping, HTTP response mappers, or real organizational authorization. Thus the code should only be used as a **mechanism test suite and sample policy**, not a production-ready service.

## 13. Extension: From In-Memory Policy to Real Data

### 13.1. Queries Must Be Bound by Tenant

Conceptual JPA repository example:

```java
// Illustrative fragment, not a standalone repository interface.
@Query("""
    select d
    from DocumentEntity d
    where d.id = :id
      and d.tenantId = :tenantId
""")
Optional<DocumentEntity> findAllowedScope(
    @Param("id") Long id,
    @Param("tenantId") String tenantId
);
```

`tenantId` must come from identity or trusted server data, **not** from an unverified request. For list/search, apply the same scope directly in SQL, then handle authorized columns/DTOs. If using database row-level security, still set the tenant/session context safely and test every connection in the pool.

### 13.2. Using `PermissionEvaluator` or `AuthorizationManager` for Complex Policies

When a system uses per-document ACLs, it can express:

```java
@PreAuthorize(
    "hasAuthority('DOC_UPDATE') and " +
    "hasPermission(#id, 'demo.Document', 'WRITE')"
)
public void update(@P("id") long id, String text) {
    // Still must check status / field whitelist / transaction.
}
```

This is an illustrative fragment requiring a `PermissionEvaluator` wired into `MethodSecurityExpressionHandler` and a working `AclService`. **Do not treat `BasePermission.WRITE` as automatically equivalent to APPROVE or EXPORT**: if separate workflow permissions exist, define separate masks/authorities/policies.

You can create a custom `AuthorizationManager<MethodInvocation>` for actions, yet the core value remains the rule across **action + resource + actor + context**, not where the annotation is placed.

### 13.3. Controlling Time-of-Check vs Time-of-Use (TOCTOU)

`@PreAuthorize` checks state at one point in time. Afterward, another transaction can alter state/owner/tenant before the SQL update runs. For approve, delete, and critical transactions:

1. Apply `@Transactional` at the proper Spring proxy boundary.
2. Lock/version the object or use conditional SQL updates with the expected state.
3. Re-check permission-affecting conditions inside the transaction and respond with conflict if data changed.
4. Never emit events/side effects outside the transaction before commit.
5. Test two concurrent requests racing to approve/delete the same object.

Example conditional SQL update:

```sql
UPDATE documents
SET status = 'APPROVED',
    approved_by = :actor
WHERE id = :id
  AND tenant_id = :tenant
  AND status = 'SUBMITTED'
  AND created_by <> :actor;
```

This is **implementation-guiding SQL**, not standalone runnable. Check that the affected row count equals 1 before treating the operation as successful, and verify `DOC_APPROVE` and related policies before this statement; do not assume the SQL statement replaces authentication.

## 14. Bulk Operations and Asynchronous Exports

If a user selects 100 records to update or export:

- **Bulk READ/EXPORT:** never grant access to the rest just because one element is permitted.
- **Bulk DELETE:** decide whether the entire batch must be authorized or partial success is allowed; if partial, the API must return per-ID results without leaking details of unauthorized records.
- **Bulk APPROVE:** check SoD and state **on every individual record**, not just the approver's role once.
- **Bulk UPDATE:** restrict updatable fields, version, and batch size; handle transactions/locking.
- **Export job:** re-check ownership, tenant, sensitivity, and revocation policies at file generation and download time per your risk model.

For example, bulk action responses must avoid leaking content/names of unauthorized records. If using `@PreFilter` or `@PostFilter`, understand they execute inside the method-security interceptor and do not rewrite database queries; for large datasets, handle scoping at the data layer.

## 15. Essential Test Suite Before Production

Minimum test cases for the six operations:

| Group | Cases to Test |
| --- | --- |
| READ | Permitted/unpermitted, owner/other, same/cross-tenant, public/sensitive, row/field redaction |
| CREATE | Same/cross-tenant, request self-declaring owner/role/status, non-existent object, quota and data type |
| UPDATE | Right owner, other owner, DRAFT/SUBMITTED/APPROVED, field allowlist, version conflict |
| DELETE | DRAFT/APPROVED, soft/hard delete, legal hold, related data, audit and rollback |
| APPROVE | Approver differs from creator, self-approval, wrong state, duplicate approval, two concurrent approvers |
| EXPORT | READ-only/EXPORT-only/both, sensitive, tenant, multiple rows, multiple columns, job link, revoked permission |
| Cross-cutting | Anonymous/admin role, self-invocation, batch/scheduler, stale cache, BOLA, log and error leakage |

An important acceptance rule is that **negative-path tests must prove zero side effects**: database unchanged, no events emitted, no file created, denial properly audited. For EXPORT, verify the file contains **only** authorized records and columns rather than checking HTTP 200/403 status alone.

## 16. Common Mistakes

**Mistake 1 — "Having READ means being allowed to EXPORT."** False unless intentionally defined by policy. Export has external impact and can aggregate massive data; it requires a separate authority plus scope controls.

**Mistake 2 — "The creator can always edit or approve forever."** CREATE/UPDATE/APPROVE are distinct. Once a document is SUBMITTED or APPROVED, edit rights must change per workflow, and the creator cannot self-approve under SoD.

**Mistake 3 — "Checking `ROLE_ADMIN` is enough."** Broad roles can bypass ownership, tenant, sensitivity, and two-person controls. A role is only part of the policy, not a substitute for object-level authorization.

**Mistake 4 — "Hard-to-guess IDs are already safe."** Random UUIDs reduce ID guessing but do not replace checking permissions on every object when accepting IDs from clients.

**Mistake 5 — "Hiding the button is enough."** Frontend is only UX. APIs, GraphQL, batch workers, and service methods still need server-side permission checks.

**Mistake 6 — "`@PostAuthorize` blocks bad transactions."** It runs after the method body. For UPDATE/DELETE/APPROVE, enforce authorization before side effects and control state/transactions at write time.

**Mistake 7 — "Blocking GET protects POST/DELETE automatically."** Every function/HTTP method/action must have its own policy, including custom endpoints like `/approve` or `/export`.

**Mistake 8 — "Export only needs per-row checks."** You must also check fields/columns, volume, format, job ownership, URL expiry, auditing, and retention.

**Mistake 9 — "Updating a raw entity directly from JSON is faster."** Mass assignment can overwrite `approved`, `owner`, `tenant`, or permissions. Use an allowlist DTO and update permitted fields explicitly.

**Mistake 10 — "Checking permissions once is enough."** Permissions can change between check and commit or before an export runs. Use transactions/locks/re-checks based on risk, especially for revoked permissions.

## 17. Exercises

1. **Add REJECTED state:** define `DOC_REJECT` separate from `DOC_APPROVE`, and test that creators cannot self-reject if the product requires it.
2. **Protect fields:** extend `Doc` with `salary` and `internalNote`; allow reading metadata while checking `DOC_SENSITIVE_READ` before returning sensitive fields.
3. **Add ACL:** allow Alice to WRITE on Doc#7 only when Bob has granted an ACE; verify UPDATE authority + WRITE permission + DRAFT state.
4. **Test mass assignment:** have the client send `owner="manager", state="APPROVED"` on UPDATE. Design a DTO and test that these two fields can never be changed by the client.
5. **Bulk export:** add `exportTenantCsv` with a scoped query predicate and column allowlist; test that every row has READ, tenant B is excluded, and row count is capped.
6. **Maker-checker:** create a user holding both `DOC_UPDATE` and `DOC_APPROVE`; test that the user still cannot self-approve a document they created.
7. **Race condition:** two users concurrently approve one SUBMITTED document; combine optimistic versioning or conditional update so only one succeeds.
8. **Revoke export job:** create an export job with valid permissions, then have an admin revoke `DOC_EXPORT`; design the download-time policy and test the outcome.

## 18. Summary

Remember by **action + data + context**:

- **READ:** view valid **records and fields**.
- **CREATE:** create within a valid **scope**; the server sets owner/tenant/state.
- **UPDATE:** modify valid **fields** of a valid **record** in a valid **state**.
- **DELETE:** delete under a dedicated policy, mindful of retention and recoverability.
- **APPROVE:** **transition state** per workflow, with separation-of-duties controls.
- **EXPORT:** take a **selected dataset** externally, requiring a dedicated permission, scope/field/volume limits, and file protection.

Spring Security provides **enforcement mechanisms** such as `@PreAuthorize`, `AuthorizationManager`, and `PermissionEvaluator`; the **application** itself must define these rules, implement policies reading trusted data, and test allow, deny, and side-effect paths. One broad permission never substitutes for six distinct business decisions.

## References

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, `@PreAuthorize`, custom beans in SpEL: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests; difference between HTTP authorization and service authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- OWASP API1:2023 — Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP API5:2023 — Broken Function Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/
- NIST CSRC Glossary — Separation of Duty: https://csrc.nist.gov/glossary/term/separation_of_duty
