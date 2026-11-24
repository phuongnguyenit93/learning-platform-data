# Transaction Binding, Locking, and Re-Checking When Permission Data Changes

## 1. The Scenario: Permission Valid at Check Time, Revoked by Write Time

A Spring Boot application manages multi-tenant documents. `bob` is granted `WRITE` permission on `Document #11` via the `document_grants` table. Managers can **revoke** grants or **transfer ownership/tenant** at any time.

Suppose the system checks permissions only at the start of the request:

```text
Time             Request A: bob edits content         Request B: alice revokes permission
---------        ----------------------------         -----------------------------------
t1               @PreAuthorize: WRITE = true
t2                                                    DELETE bob's grant
t3                                                    COMMIT
t4               UPDATE documents SET body = ...
t5               COMMIT
```

At `t4`, `bob` has lost permission yet can still write because Request A reuses the check result from `t1`. This is **TOCTOU — Time of Check, Time of Use** (check time differs from use time). The flaw occurs even when the API authenticates properly, uses `@PreAuthorize`, uses `@Transactional`, and has zero SQL injection.

This Knowledge unit belongs to **Spring Security – authorization**, **Data Permissions** group. The focus is **binding transactions, locking, and re-checking authorization when owner, tenant, ACL, or grants change**. We analyze what Spring Security, Spring Transactions, and databases actually guarantee; then build a Spring Boot/JDBC example with concurrency tests pitting updates against permission revocation.

After this lesson, you will be able to:

1. Distinguish **functional authority** (on the authentication) from **dynamic data permissions** (owner, tenant, ACL, state, grants in the DB).
2. Pinpoint TOCTOU windows when `@PreAuthorize` runs before or outside the update transaction.
3. Understand why adding `@Transactional` or raising isolation alone **does not guarantee the latest permissions**.
4. Use **consistent row locking** across both data-editing and permission-revoking paths.
5. Place the final permission check **after acquiring the lock**, right inside the write transaction.
6. Know when to use **conditional UPDATE**, `@Version`/optimistic locking, pessimistic locking, and `SERIALIZABLE`.
7. Run a Java 17+ / Spring Boot 3.5.x / H2 JDBC example with `@EnableMethodSecurity`, `@PreAuthorize`, `@Transactional`, and `SELECT ... FOR UPDATE`.
8. Write tests confirming that when **revocation commits before the lock-protected check**, a waiting edit must be denied.
9. Design transactions, caching, retries, and auditing appropriately when permissions span multiple tables, nodes, or services.

**Agreed definition of correctness:** the example ensures **document editing** and **grant revocation** are ordered via a lock on the same document row. If revocation commits before the edit acquires the lock, the edit must re-check the grant and be denied. If the edit acquires the lock first, it may finish before revocation proceeds: that operation was authorized at the time it won lock order—**not** a promise that revoke cancels in-flight work mid-execution.

## 2. Three Layers of Data Determining Permission

A write decision may depend on:

| Data Layer | Example | Change Frequency | Where to Check? |
| --- | --- | --- | --- |
| Authentication | `sub`, principal ID, authority `document:write` | Login, token refresh, account revocation | Security filter/provider and Method Security |
| Domain attributes | `owner_id`, `tenant_id`, `state`, `version` | Owner/tenant transfer, approve, close | Inside transaction, on the real record |
| Grants/ACLs/policy | `document_grants`, `acl_entry`, membership, policy version | Sharing, revoking, group changes | Same transaction or consistency protocol with updates |

Example policy:

```text
canWrite(actor, document, grants) =
    authenticated(actor)
    AND hasAuthority(actor, "document:write")
    AND actor.tenant == document.tenant
    AND document.state == "DRAFT"
    AND (
          actor.id == document.ownerId
          OR grants.contains(document.id, actor.id, "WRITE")
        )
```

Here `actor` and `tenant` must derive from verified identity/server mappings, **never** from `X-User`, `X-Tenant`, or self-declared JSON. `document` and `grants` must be read from **an updatable data source**. A cached `allowed=true` boolean from minutes earlier is insufficient proof at write time.

### 2.1. `@PreAuthorize` Is a Necessary Gate, Not a DB Lock

Example:

```java
@PreAuthorize("hasAuthority('document:write')")
@Transactional
public void edit(long documentId, String newBody) {
    // ...
}
```

`@PreAuthorize` verifies the caller holds the general authority when the proxy intercepts. It does not lock `documents` or `document_grants`, nor force the transaction to contain all policy data.

If you write:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'WRITE')")
@Transactional
public void edit(Long id, String newBody) {
    repository.update(id, newBody);
}
```

then `hasPermission` may read grants **before the method's transaction starts**, depending on advisor ordering/configuration. Even if run inside a transaction, if a window exists between check and write where grants/owners legitimately change, you still need a consistency mechanism. **Never rely on an annotation as a lock or an immutable permission snapshot.**

Spring Security 6 uses `AuthorizationManagerBeforeMethodInterceptor` for `@PreAuthorize`; Spring Transaction also uses advice in proxy mode. Advice ordering is configurable. Therefore this lesson's main example uses:

- `@PreAuthorize`: checks **functional authority**.
- **Inside `@Transactional`**: acquires the lock, reads the latest permission data under lock ordering, then checks **object-level authorization** before writing.

### 2.2. `@PostAuthorize` Is Unsuitable for Protecting Side Effects

A method:

```java
@PostAuthorize("returnObject.owner == authentication.name")
@Transactional
public Receipt transferMoney(...) {
    // Already performed write operations before @PostAuthorize inspects the result.
}
```

illustrates a **dangerous design**, not runnable code. Post-execution authorization can run after the method body has already caused side effects. If the transaction committed, rejecting the response does not roll back. Spring Security also recommends not relying on `@PostAuthorize` as the sole protection for write methods.

For writes, **check before writing** and enforce permission conditions consistently through commit.

## 3. What Does `@Transactional` Guarantee, and What Not?

Spring `@Transactional` defines a **transaction boundary** when a method is invoked through an appropriate proxy/AspectJ weave. Spring defaults include:

- `Propagation.REQUIRED`: joins an existing transaction or opens a new one.
- `Isolation.DEFAULT`: uses the database/driver default.
- `readOnly=false`.
- Default rollback on `RuntimeException` and `Error`; checked exceptions require `rollbackFor` or matching rollback rules.
- In proxy mode, self-invocation (`this.methodAnnotatedTransactional()`) **does not trigger** transaction advice.

It **does not automatically do** the following:

1. Verify `Authentication` or grant object permissions.
2. Re-read grants/ACLs at write time.
3. Prevent another transaction from modifying grants/owners without matching locks/serialization.
4. Span multiple databases or remote ACL services in one transaction.
5. Turn stale permission caches into fresh results.
6. Guarantee every SQL statement after a check sees the same active policy.

### 3.1. Isolation Does Not Mean "Always Reads the Latest Revocation"

| Isolation | Notable Behavior | Authorization Limitation |
| --- | --- | --- |
| `READ_UNCOMMITTED` | May allow reading uncommitted changes depending on DB | Unsuitable as basis for sensitive permissions |
| `READ_COMMITTED` | Each statement generally sees committed data per DB rules | Grants can change **between two statements** |
| `REPEATABLE_READ` | May hold snapshots/locks preventing certain anomalies | May keep seeing an older snapshot; behavior varies by DB/MVCC |
| `SERIALIZABLE` | DB ensures execution matches some serial order | Can abort on conflict; must retry full **transaction + authorization** |

Do not assume "setting `Isolation.REPEATABLE_READ` guarantees no write after revocation" or "`SERIALIZABLE` automatically blocks all operations started before revocation". Explicitly define the **linearization point** or ordering your product expects, and test on the actual production database.

### 3.2. SQL Locks Have Database-Specific Semantics

In PostgreSQL, `SELECT ... FOR UPDATE` acquires row-level locks, blocking other transactions from updating/deleting/locking those rows until the transaction ends; waiting transactions observe the post-update record once they acquire the lock. H2 supports matching syntax for experimentation, yet lock timeouts, MVCC, and isolation specifics can differ from PostgreSQL/MySQL.

**Never test only on H2 and assume production transaction behavior will be identical.** For concurrency and authorization, run integration tests against the exact target DB engine and version.

## 4. Three Solution Families to Distinguish

### A. Conditional UPDATE — Checking Conditions Inside the Write Statement

Example SQL updating only while the caller remains owner in the tenant:

```sql
UPDATE documents
SET body = :newBody,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedActorId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

`:name` represents illustrative **named parameters**; use `NamedParameterJdbcTemplate` or equivalent parameter binding. Check affected rows: **1** means update succeeded, **0** means a condition no longer matched. Never disclose existence/owner details to unauthorized callers.

When permission is a dynamic grant:

```sql
UPDATE documents
SET body = :newBody,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND state = 'DRAFT'
  AND version = :expectedVersion
  AND EXISTS (
      SELECT 1
      FROM document_grants g
      WHERE g.document_id = documents.id
        AND g.grantee = :trustedActorId
        AND g.action = 'WRITE'
  );
```

This is **illustrative SQL**; adapt `UPDATE` alias/relation syntax to your DB. It shrinks the check–write gap, yet **a single statement does not automatically make concurrent revocation real-time linearizable**: outcomes depend on DB snapshot/locking, how grants update, and competing transactions. If strict ordering between revoke and write is required, add a shared lock or synchronized policy version.

### B. Pessimistic Locking — Locking the Same Coordinating Row

Both transactions always lock the **document row** before reading/writing grants:

```text
Transaction WRITE                      Transaction REVOKE
--------------------------------      --------------------------------
BEGIN                                  BEGIN
SELECT document FOR UPDATE             SELECT document FOR UPDATE
  -> holds lock / waits                  -> waits / holds lock
READ grants and owner after lock       DELETE document_grants
re-check permissions                   COMMIT
UPDATE body + version
COMMIT
```

If WRITE locks first and commits before REVOKE, the update proceeds under the grant valid at that time. If REVOKE locks first and commits, WRITE waits, then re-reads grants, sees the revocation, and is denied.

**Mandatory condition:** all relevant permission-changing paths (grant/revoke, owner transfer, tenant transfer, state changes, and required policy rows) must **obey the same locking protocol**. If a job runs `DELETE document_grants` directly without locking `documents`, the ordering guarantee breaks.

### C. Optimistic Locking / Policy Version

A lighter-locking option attaches `@Version` or `version` to **data being written**, plus an `authorization_version`/`policy_version` for **relevant permissions**.

```text
Document:
  id = 11
  version = 7
  authorization_version = 4

Expected token:
  expectedDocumentVersion = 7
  expectedAuthorizationVersion = 4
```

When changing grants/owner, the transaction increments the resource's `authorization_version`. Writes conditioned on `WHERE version = 7 AND authorization_version = 4` (and policy) will not update if data or permissions changed.

JPA's `@Version` **only tracks the versioned entity itself**. If permissions reside in separate `acl_entry`/`document_grants` tables, altering those tables **does not automatically bump** `Document.version`. Thus, for optimistic authorization consistency, **link a policy version** and bump it on every permission-changing path.

## 5. Practical Example: Shared Locking Protocol for Write and Revoke

We build a Java 17+ application with:

- Spring Boot 3.5.8, Spring Security Method Security.
- Spring JDBC `JdbcTemplate` and an in-memory H2 database.
- `@Transactional` on both the write service and revocation service.
- `SELECT ... FOR UPDATE` on `documents` to coordinate the two flows.
- `document:write` authority from Authentication; per-resource `WRITE` permission from `document_grants`.
- User/tenant mapping from a server directory; never accepting self-declared principal/tenant from requests.
- No HTTP controller; demo runs via `CommandLineRunner`, and tests call Spring-managed beans.
- Transaction/revoke tests use two threads and latches rather than fragile `Thread.sleep()`.

**Demo goal:** when `bob`'s grant is revoked and committed **before the edit acquires the document lock**, `bob` cannot write. While an edit holds a valid lock, revoke waits; a revocation request does not abort work that already won the lock.

### 5.1. Project Structure

```text
transactional-authorization-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TransactionAuthorizationApplication.java
    │   │   ├── DocumentRow.java
    │   │   ├── ActorDirectory.java
    │   │   ├── DocumentRepository.java
    │   │   ├── DocumentEditService.java
    │   │   └── GrantAdministrationService.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── AuthorizationConcurrencyTest.java
```

### 5.2. Gradle and Dependencies

**`settings.gradle`:**

```groovy
rootProject.name = 'transactional-authorization-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Spring Boot auto-configures the H2 `DataSource`, `JdbcTemplate`, and JDBC transaction manager when the required dependencies are present. With default embedded H2, Spring Boot runs `schema.sql` and `data.sql` on startup. Production must use an appropriate database, driver, and migrations.

### 5.3. Creating Schema and Dynamic Permission Data

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_name VARCHAR(64) NOT NULL,
    body VARCHAR(500) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE document_grants (
    document_id BIGINT NOT NULL,
    grantee VARCHAR(64) NOT NULL,
    action VARCHAR(16) NOT NULL,
    PRIMARY KEY (document_id, grantee, action),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_document_grants_lookup
    ON document_grants (grantee, action, document_id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (id, tenant_id, owner_name, body, version) VALUES
    (11, 'T1', 'alice', 'Draft', 1),
    (22, 'T2', 'carol', 'Other tenant', 1);

INSERT INTO document_grants (document_id, grantee, action) VALUES
    (11, 'bob', 'WRITE');
```

In the demo, `alice` owns `Document#11`, `bob` is shared `WRITE` permission, and `carol` belongs to tenant `T2`. Note that this `document_grants` table name and structure **are custom to this demo's policy**, not the four standard ACL tables of the `spring-security-acl` module.

Because IDs here are globally unique across the DB, grants point to documents via a foreign key. If IDs are unique only within each tenant, keys must include tenant or use globally unique identities, and tenant guards must be enforced in both ACLs and queries.

### 5.4. Server-Supplied Domain Row

**`src/main/java/demo/DocumentRow.java`:**

```java
package demo;

public record DocumentRow(
        long id,
        String tenant,
        String owner,
        String body,
        long version) {
}
```

`DocumentRow` must never be bound directly from client JSON. It strictly represents state **read by the repository from the DB**. `owner` and `tenant` must be server-trusted values within an appropriate transaction.

### 5.5. Trusted Identity/Tenant Directory

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

record Actor(String username, String tenant) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("alice", "T1"),
        "bob", new Actor("bob", "T1"),
        "carol", new Actor("carol", "T2")
    );

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    public Actor current() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || resolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted principal");
        }

        Actor actor = actors.get(authentication.getName());

        if (actor == null) {
            throw new AccessDeniedException("No trusted tenant");
        }
        return actor;
    }
}
```

The static directory is a **simulation**. In OIDC/JWT production, map `issuer + subject` or a stable internal user ID to verified tenant memberships and roles. Never trust `X-Tenant` or a body-supplied `tenantId`. Users can belong to multiple tenants; the active tenant choice must undergo **membership verification**.

`AuthenticationTrustResolver` prevents confusing anonymous tokens that report `isAuthenticated() == true` with real users.

### 5.6. Repository: One Lock, Two Operational Paths

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.List;
import java.util.NoSuchElementException;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final RowMapper<DocumentRow> MAPPER =
        (rs, rowNumber) -> new DocumentRow(
            rs.getLong("id"),
            rs.getString("tenant_id"),
            rs.getString("owner_name"),
            rs.getString("body"),
            rs.getLong("version")
        );

    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public DocumentRow lockDocument(long id) {
        List<DocumentRow> rows = jdbc.query(
            """
            SELECT id, tenant_id, owner_name, body, version
            FROM documents
            WHERE id = ?
            FOR UPDATE
            """,
            MAPPER,
            id
        );

        if (rows.isEmpty()) {
            throw new NoSuchElementException("Document not found");
        }
        return rows.get(0);
    }

    public DocumentRow snapshot(long id) {
        List<DocumentRow> rows = jdbc.query(
            """
            SELECT id, tenant_id, owner_name, body, version
            FROM documents
            WHERE id = ?
            """,
            MAPPER,
            id
        );

        if (rows.isEmpty()) {
            throw new NoSuchElementException("Document not found");
        }
        return rows.get(0);
    }

    public boolean hasWriteGrant(long id, String grantee) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM document_grants
            WHERE document_id = ?
              AND grantee = ?
              AND action = 'WRITE'
            """,
            Integer.class,
            id,
            grantee
        );
        return n != null && n > 0;
    }

    public void changeBody(DocumentRow locked, String newBody) {
        int updated = jdbc.update(
            """
            UPDATE documents
            SET body = ?, version = version + 1
            WHERE id = ? AND tenant_id = ? AND version = ?
            """,
            newBody,
            locked.id(),
            locked.tenant(),
            locked.version()
        );

        if (updated != 1) {
            throw new OptimisticLockingFailureException(
                "Document changed concurrently");
        }
    }

    public int revokeWriteGrant(long id, String grantee) {
        return jdbc.update(
            """
            DELETE FROM document_grants
            WHERE document_id = ?
              AND grantee = ?
              AND action = 'WRITE'
            """,
            id,
            grantee
        );
    }
}
```

Two core points:

1. `lockDocument(id)` uses **`SELECT ... FOR UPDATE`** and must be called **inside a real transaction**. If called outside a transaction (auto-commit), the lock may release immediately after the statement and fail to protect subsequent steps.
2. `changeBody` adds a `version` check to catch unexpected document edits. However, the document's version **does not automatically detect grant revocation**; the lock + grant re-check layer solves that main issue.

**Never expose `snapshot` or `lockDocument` as unauthenticated/unauthorized public read APIs**. They are internal repository methods; services/endpoints must protect read access as well.

### 5.7. Edit Service: Lock -> Read Permissions -> Decide -> Write

**`src/main/java/demo/DocumentEditService.java`:**

```java
package demo;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentEditService {

    private final DocumentRepository documents;
    private final ActorDirectory actors;

    public DocumentEditService(
            DocumentRepository documents,
            ActorDirectory actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public String changeBody(long id, String newBody) {

        Actor actor = actors.current();

        // FIRST: every writer/ACL revoker locks the document row itself.
        DocumentRow locked = documents.lockDocument(id);

        if (!locked.tenant().equals(actor.tenant())) {
            throw new AccessDeniedException("Cross-tenant access");
        }

        boolean isOwner = locked.owner().equals(actor.username());
        boolean isGranted = documents.hasWriteGrant(
            id, actor.username()
        );

        if (!isOwner && !isGranted) {
            throw new AccessDeniedException("Write grant is missing");
        }

        if (newBody == null || newBody.isBlank()
                || newBody.length() > 500) {
            throw new IllegalArgumentException("Invalid body");
        }

        documents.changeBody(locked, newBody);
        return newBody;
    }
}
```

**Why is `hasWriteGrant` called after `lockDocument`?** Assume the revocation transaction also always locks the same document row before deleting the grant. Once the edit holds the lock, grants and owner can only be changed by protocol-compliant writers **after** the edit finishes, or were already changed **before** the edit acquired the lock. There is no longer a window where "revoke commits between check and UPDATE" between these two lock-compliant paths.

`@PreAuthorize` here checks only **static authority**. It may run in an advisor before the transaction; therefore **never treat its outcome as the final verdict for dynamic grants**.

`AccessDeniedException` is a runtime exception; under default Spring `@Transactional`, it triggers rollback. If using checked exceptions for denials, configure rollback rules accordingly.

### 5.8. Revoke Service: Maintaining the Same Lock Order

**`src/main/java/demo/GrantAdministrationService.java`:**

```java
package demo;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GrantAdministrationService {

    private final DocumentRepository documents;
    private final ActorDirectory actors;

    public GrantAdministrationService(
            DocumentRepository documents,
            ActorDirectory actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('grant:revoke')")
    @Transactional
    public int revokeWrite(long id, String grantee) {

        Actor actor = actors.current();

        // ALWAYS lock the same row used by DocumentEditService.
        DocumentRow locked = documents.lockDocument(id);

        if (!locked.tenant().equals(actor.tenant())
                || !locked.owner().equals(actor.username())) {
            throw new AccessDeniedException(
                "Only an authorized same-tenant owner may revoke");
        }

        if (grantee == null || grantee.isBlank()) {
            throw new IllegalArgumentException("Invalid grantee");
        }

        return documents.revokeWriteGrant(id, grantee);
    }
}
```

In the demo, `alice` owns `Document#11` and holds `grant:revoke`. She can revoke `bob`'s permission. Users from other tenants or someone holding only `document:write` cannot call this method.

**System-wide compliance requirement:** every endpoint, job, admin screen, or event consumer that **transfers owner/tenant, changes state, or adds/removes grants affecting write rights** must use **the same coordinating lock** inside a transaction. If code executes a direct `DELETE document_grants` without locking the document, this pattern loses its ordering guarantee.

### 5.9. Spring Boot Application and CLI Output

**`src/main/java/demo/TransactionAuthorizationApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class TransactionAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            TransactionAuthorizationApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demo(
            DocumentEditService editor,
            GrantAdministrationService grants,
            DocumentRepository documents) {

        return args -> {
            try {
                as("bob", "document:write");
                System.out.println("BOB_BEFORE_REVOKE: "
                    + editor.changeBody(11L, "Bob revision"));

                as("alice", "grant:revoke");
                System.out.println("GRANTS_REVOKED: "
                    + grants.revokeWrite(11L, "bob"));

                as("bob", "document:write");
                denied("BOB_AFTER_REVOKE",
                    () -> editor.changeBody(11L, "Stale revision"));

                as("alice", "document:write");
                System.out.println("ALICE_OWNER_EDIT: "
                    + editor.changeBody(11L, "Alice revision"));

                as("carol", "document:write");
                denied("CROSS_TENANT",
                    () -> editor.changeBody(11L, "Forbidden tenant"));

                DocumentRow finalRow = documents.snapshot(11L);
                System.out.println("FINAL_BODY: " + finalRow.body());
                System.out.println("FINAL_VERSION: "
                    + finalRow.version());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void as(String user, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            user,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`UsernamePasswordAuthenticationToken` is constructed directly with authorities here to **simulate tests/CLI**, not how authentication is built for real users. Production must verify tokens/sessions via a provider; never build trusted tokens from HTTP request-declared usernames/roles. `SecurityContextHolder` is cleared at the end of the demo so identity does not leak into other tasks.

Run in the project directory if Gradle Wrapper is present:

```bash
./gradlew bootRun
```

On PowerShell:

```bash
.\gradlew.bat bootRun
```

If there is no wrapper yet, generate one with a compatible Gradle version or run `gradle bootRun` when Gradle is installed. **Lines printed by the program itself**, excluding Spring/Gradle logs, are expected to be:

```text
BOB_BEFORE_REVOKE: Bob revision
GRANTS_REVOKED: 1
BOB_AFTER_REVOKE: DENIED
ALICE_OWNER_EDIT: Alice revision
CROSS_TENANT: DENIED
FINAL_BODY: Alice revision
FINAL_VERSION: 3
```

Analysis:

- Before revocation, `bob` holds `document:write` **and** a WRITE grant on document 11, updating `Draft` to `Bob revision`; version increments 1 -> 2.
- `alice` holds `grant:revoke` and is the same-tenant owner. Revoking deletes Bob's single grant and commits.
- When `bob` tries to write again, the new transaction locks the document, re-reads the **deleted** grant, and throws `AccessDeniedException`. No UPDATE occurs.
- `alice` is the same-tenant owner with `document:write`, so she updates to `Alice revision`; version 2 -> 3.
- `carol` belongs to T2 and is denied despite holding `document:write`.
- Final body is `Alice revision`, final version is `3`.

**This output is inferred from the source code, not a claim that it was executed in the current environment.** Output order comes from sequential `CommandLineRunner` calls; dedicated concurrency tests are in section 6.

## 6. Integration Tests: Verifying Both Business Logic and Concurrency

Uses `@SpringBootTest`, `@WithMockUser`, and `@DirtiesContext` so each test gets a fresh H2 database. The concurrency test specifically uses two threads and `TransactionTemplate` to **hold the row lock in an explicit transaction**, then pits `bob`'s edit against revocation.

**`src/test/java/demo/AuthorizationConcurrencyTest.java`:**

```java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AuthorizationConcurrencyTest {

    @Autowired DocumentEditService editor;
    @Autowired GrantAdministrationService grants;
    @Autowired DocumentRepository documents;
    @Autowired PlatformTransactionManager txManager;

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "document:write"
    )
    void validGrantAllowsEditing() {
        assertEquals(
            "Edited",
            editor.changeBody(11L, "Edited")
        );
        assertEquals("Edited", documents.snapshot(11L).body());
        assertEquals(2L, documents.snapshot(11L).version());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "grant:revoke"
    )
    void ownerMayRevokeWriteGrant() {
        assertEquals(1, grants.revokeWrite(11L, "bob"));
        assertEquals(0, grants.revokeWrite(11L, "bob"));
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    @WithMockUser(
        username = "carol",
        authorities = "document:write"
    )
    void crossTenantUserCannotEditDocument() {
        assertThrows(
            AccessDeniedException.class,
            () -> editor.changeBody(11L, "Forbidden")
        );
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "document:read"
    )
    void missingFunctionalAuthorityIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> editor.changeBody(11L, "Forbidden")
        );
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    void revocationCommittedBeforeWriteLockCausesDenial()
            throws Exception {

        ExecutorService pool = Executors.newFixedThreadPool(2);

        CountDownLatch revokerLocked = new CountDownLatch(1);
        CountDownLatch releaseRevoker = new CountDownLatch(1);
        CountDownLatch writerStarted = new CountDownLatch(1);

        TransactionTemplate tx = new TransactionTemplate(txManager);

        try {
            Future<?> revoker = pool.submit(() ->
                asUser("alice", "grant:revoke", () -> {

                    // An admin transaction already locked the document.
                    // Follows the same lock order as GrantAdministrationService.
                    tx.executeWithoutResult(status -> {
                        documents.lockDocument(11L);
                        revokerLocked.countDown();
                        await(releaseRevoker);
                        documents.revokeWriteGrant(11L, "bob");
                    });
                    return null;
                })
            );

            assertTrue(
                revokerLocked.await(10, TimeUnit.SECONDS),
                "Revoker did not obtain document lock"
            );

            Future<String> writer = pool.submit(() ->
                asUser("bob", "document:write", () -> {
                    writerStarted.countDown();
                    return editor.changeBody(11L, "Stale update");
                })
            );

            assertTrue(
                writerStarted.await(10, TimeUnit.SECONDS),
                "Writer thread did not start"
            );

            // Revoke commits when releasing the lock-holding transaction.
            // Writer waits on lock or starts after commit: both must deny.
            releaseRevoker.countDown();
            revoker.get(10, TimeUnit.SECONDS);

            ExecutionException denied = assertThrows(
                ExecutionException.class,
                () -> writer.get(10, TimeUnit.SECONDS)
            );

            assertInstanceOf(
                AccessDeniedException.class,
                denied.getCause()
            );

            assertEquals("Draft", documents.snapshot(11L).body());
            assertEquals(1L, documents.snapshot(11L).version());

        } finally {
            releaseRevoker.countDown();
            pool.shutdownNow();
        }
    }

    private static <T> T asUser(
            String username,
            String authority,
            Supplier<T> operation) {

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                username,
                "demo-only",
                List.of(new SimpleGrantedAuthority(authority))
            )
        );

        SecurityContextHolder.setContext(context);

        try {
            return operation.get();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for test latch");
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted while waiting", interrupted);
        }
    }
}
```

Run:

```bash
./gradlew test
```

### 6.1. What Does the Concurrency Test Prove?

1. The **revoker** thread opens a transaction, locks `documents.id=11`, and holds the lock.
2. The **writer** thread invokes `DocumentEditService.changeBody` through the Spring proxy.
3. Upon releasing the latch, the revoker deletes Bob's grant **inside the lock-holding transaction**, then commits.
4. If the writer waited on the row, it acquires the lock post-commit; if it had not yet reached the lock, it still reads grants post-commit. In both valid schedules, `hasWriteGrant(11,"bob")` is `false` and no UPDATE runs.
5. The test catches `AccessDeniedException` from the Future while reading back body and version to guarantee **zero unauthorized side effects**.

`CountDownLatch` creates intentional synchronization points; never use `Thread.sleep()` as proof of transaction ordering. This test demonstrates **revoker winning lock order**; to prove symmetry, add a scenario where the writer locks first while the revoker waits, confirming the writer commits before revocation completes.

**Limitation:** tests use H2 and do not directly prove lock behavior across all databases. For PostgreSQL/MySQL production, add integration tests on the target DB or Testcontainers and verify execution plans/lock timeouts.

### 6.2. Why Not Put `@Transactional` on the Test Method?

If the main test method opens its own transaction and calls the repository before spawning two threads, the test can hold unexpected locks/connections. In the example, transactions are managed **inside the two worker threads** via Spring transactional services and `TransactionTemplate`, testing real lock/commit ordering more faithfully. `@DirtiesContext` resets the in-memory DB between tests, avoiding order dependence.

### 6.3. Do Not Treat `403`/Exceptions Alone as Sufficient

After a denied write, **always read back the DB**:

```text
body        = Draft
version     = 1
grant bob   = absent
```

An API can return `403` yet have written data before throwing. If writes happen outside a transaction or rollback rules are wrong, HTTP status alone proves nothing. In this test we assert body/version unchanged, and can add `documents.hasWriteGrant(11,"bob") == false` to verify revocation.

## 7. Other Competing Designs

### 7.1. Storing Permissions on the Resource Row Itself

If policy consists solely of `ownerId`, `tenantId`, and state, you can lock **the `documents` row itself**, check, and write—needing no separate grant table.

However, when policies live in another table (`acl_entry`, `document_grants`), note there is no built-in guarantee that a transaction updating a grant will conflict with a transaction updating a document. Locking the document row is an **application protocol**, not an automatically enforced foreign key.

### 7.2. `@Lock(PESSIMISTIC_WRITE)` with Spring Data JPA

Equivalent pattern in JPA:

```java
public interface DocumentJpaRepository
        extends JpaRepository<DocumentEntity, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from DocumentEntity d where d.id = :id")
    Optional<DocumentEntity> lockById(@Param("id") Long id);
}
```

This is an **illustrative** snippet requiring `jakarta.persistence.LockModeType`, Spring Data JPA imports, entity, and repository bean. JPA/Hibernate generates the matching locking SQL per DB dialect.

In `@Transactional` services, both `editDocument` and `revokeGrant` must call `lockById(id)` **before** checking/updating owners/ACLs. If revoke merely calls `grantRepository.deleteBy...` without locking the document, `@Lock` on the writer **cannot protect permissions**.

### 7.3. `@Version` Does Not Automatically Track ACLs

```java
@Entity
class DocumentEntity {
    @Id Long id;

    @Version
    long version;
}
```

This is a partial snippet without full entity mappings. Optimistic locking detects when another writer changed the document version, yet **does not automatically notice** a `DELETE` in a separate grant/ACL table. If business requires permission changes to invalidate in-flight updates, maintain a linked `authzVersion`; every policy-changing path must increment that version **in the same transaction**. Writers must check it at write time.

### 7.4. `SERIALIZABLE` and Retries

`SERIALIZABLE` provides serial-order semantics within the DB's transaction scope; it can trigger serialization failures/deadlocks. When retrying:

1. Catch only retryable concurrency errors.
2. Start a **new transaction**.
3. Read **fresh identity/policy/ACL state**.
4. Re-check permissions completely.
5. Write only after a valid decision.
6. Cap retry counts/backoff; avoid blind automatic retries on non-idempotent side effects.

**Never retry by reusing `wasAllowed = true` or ACL objects loaded in the failed transaction.** If permission was revoked, the retry must return deny.

### 7.5. Permissions Stored in Another DB or External Service

If grants live in a permission service outside the document's database, `@Transactional` on the document DB **cannot atomically lock and commit** with the permission service. Pick an explicit consistency model:

- Ultra-sensitive permissions: keep write-decision policies close to the resource DB or use one authoritative transaction/lock.
- Remote PDP decisions: consider short-lived decision tokens/versions, revalidation at commit, or an API performing **atomic authorize-and-write** at the same authority.
- Cross-service revocation: use events/outbox/sagas with bounded propagation latency and a clear definition of when revocation takes effect.
- When permissions depend on long-lived JWTs, local token validation can still verify signatures while being stale; add version/revocation semantics for permissions requiring immediate revocation.

Never claim "system-wide instant revocation" solely because an event was published to a queue; verify actual latency and consistency.

## 8. Deadlocks, Lock Ordering, and Performance

### 8.1. Choose One System-Wide Lock Ordering

When updating multiple documents, if transaction A locks `Document#11` then `Document#22` while transaction B locks `#22` then `#11`, deadlocks readily occur.

Convention:

```text
1. Normalize and sort document IDs ascending.
2. Lock each document in sorted order.
3. Then lock/update grant/ACL rows in a defined order.
4. Check permissions on every object to be written.
5. Perform changes or roll back the entire batch.
```

Never use JVM-local locks like `synchronized` or `ReentrantLock` to substitute for DB locks in multi-instance systems: other nodes do not share those locks. Row locks/transactions must belong to the authoritative data store.

### 8.2. Keep Transactions Short

While holding row locks, avoid:

- Slow HTTP service calls without timeouts.
- Waiting for user input.
- Running ML jobs or heavy file processing.
- Sending emails directly before commit.
- Triggering N+1 ACL lookups per item.

A common pattern is preparing/validating data outside the transaction, then opening a short transaction to **lock -> recheck -> mutate -> commit**. For events/emails, write an outbox record in the same transaction and publish after commit.

### 8.3. Lock Timeouts and Deadlocks Must Be Handled Properly

Depending on the DB, you may encounter:

- Lock wait timeouts.
- Deadlock detection errors.
- Optimistic locking failures.
- Serialization failures.
- Transaction rollbacks due to network/connection drops.

Never catch all exceptions and `return true` or silently write unchecked. Distinguish permission denials, concurrency conflicts, and infrastructure errors—typically 403/404 policy, 409 conflict, or 5xx per API contract. **Never leak info about documents/tenants the caller cannot view** through error messages.

### 8.4. Which Metrics to Benchmark?

| Metric | Why Needed |
| --- | --- |
| Write p50/p95/p99 latency | Lock waits can inflate p99 |
| Lock waits / deadlocks / timeouts | Detects poor locking protocols |
| Rows scanned / SQL query count | Spots N+1 ACL lookups |
| Post-lock permission checks | Ensures re-checks actually run |
| Granted vs denied ratio | Tracks policy behavior shifts |
| Stale cache hits / revocation lag | Evaluates revoked-permission exposure |
| Transaction duration | Prevents holding locks too long |
| Retry count / serialization failures | Detects contention |

Measure both **correctness** and performance. An optimization that skips permission re-checks is not an improvement.

## 9. ACLs, `PermissionEvaluator`, and Dynamic Permissions in Transactions

If the system uses real Spring Security ACLs:

```text
@PreAuthorize hasPermission(#id, 'Document', 'WRITE')
        |
        v
AclPermissionEvaluator
        |
        v
AclService / ACL cache -> Acl.isGranted(...)
```

The result may be computed **before** the write transaction or against an application snapshot/cache. Thus, for sensitive writes:

- Use `@PreAuthorize` to fail early and shed load, yet **never treat it as the final check**.
- Lock the authoritative resource/policy under a protocol that grant/revoke code also obeys.
- **Re-check** ACL/owner/tenant/status after locking; if the ACL cache can be stale, use an authoritative read API or proper invalidation/versioning.
- After `MutableAclService.updateAcl`, ensure transaction commit and cache invalidation order properly; propagate across clusters.
- If parent/group ACLs or role privileges change, locking only the document may not suffice. Define locks/versions for **every policy source affecting** the decision, or explicitly accept and document weaker consistency.

**Never use `@PostAuthorize` to "roll back" an already-committed write**. To span authorization and mutation in one transaction, ensure authorization logic genuinely runs inside the right transaction/lock boundary rather than just stacking annotations and guessing advice order.

### `PermissionEvaluator` Is Not a Transaction Manager

`PermissionEvaluator.hasPermission(authentication, object, permission)` can read ACLs but has no contract to "lock all data sources" or "re-check before commit". A custom evaluator may call services/DAOs, though it should avoid per-object N+1 DB calls, cross-user permission caches, and relying on transactions from a different datasource.

## 10. Ownership Transfer and Tenant Migration Must Obey the Same Protocol

Revocation is not the only permission change. Example:

1. Alice owns document 11.
2. Admin transfers `owner_id` to Bob.
3. Alice has an in-flight edit request that already passed the owner check.
4. Alice continues writing under old ownership.

If transfer updates the owner **without locking the same row** or edit skips re-checking owner after locking, TOCTOU occurs.

An ownership-transfer service should:

```text
BEGIN
  lock document #11
  authenticate + authorize actor permitted to transfer
  verify current owner/tenant/state
  verify new owner and tenant membership
  update owner_id, related grants/ACLs, and policy version
  write audit/outbox
COMMIT
```

Transferring `tenant_id` is even more sensitive because it is a data boundary. It may require migrating file storage, caches, ACL SIDs, encryption keys, and related resources—not just updating one column. Each workflow needs matching consistency controls; never use a generic `updateEntity` accepting `ownerId`/`tenantId` from clients.

## 11. Decision Table for Choosing a Solution

| Requirement | Primary Mechanism | Conditions and Notes |
| --- | --- | --- |
| Owner-only edits, policy on same row | Conditional UPDATE on owner/tenant/version | Bind server identity, check affected rows |
| Grants in separate table, strict revoke ordering | Shared lock on resource row in edit/revoke | Every grant-changing path obeys the lock |
| Low contention, multiple writers on same entity | `@Version` / optimistic locking | ACL changes must bump authz version if detection needed |
| Multiple resources in one transaction | Sort IDs and lock in canonical order | Prevent deadlocks, all-or-nothing policy |
| Complex policy requiring SERIALIZABLE | Serializable transaction + retry | Retry transaction and authorization from scratch |
| Multi-node ACL cache | Cache invalidation / versioning | Do not claim instant revocation if propagation lags |
| Permissions in external service outside DB | Consistency contract and authoritative check | No atomicity from local `@Transactional` alone |
| Must cancel writers started before revoke | Stronger protocol (epoch/barrier/cancel) | Plain row locks let writers that won the lock finish before revoke |

### What Does "Immediately Revoked" Mean?

There are three distinct requirements:

1. **Reject operations started after revocation commits.**
2. **Disallow commits of operations authorized before revocation that try to commit after revocation.**
3. **Abort all in-flight work the moment an admin clicks revoke, even if holding a lock or calling external services.**

The demo's locking protocol satisfies **sequential ordering by lock acquisition**: when a writer locks before revoker, the writer can commit first; when revoker locks first, the writer is denied after revoke commits. It does **not** fulfill the third requirement automatically.

If an absolute cutoff for all background tasks is needed, design a **revocation epoch**, cancellation protocol, barrier protocol, or authoritative executor/queue enforcing ordering. Document and test that guarantee as part of your business security contract.

## 12. Common Mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Checking grants only in `@PreAuthorize` | Permission can be revoked before UPDATE | Re-check grants inside transaction after locking |
| Assuming `@Transactional` freezes grants | Another DB tx can alter ACLs/grants | Choose appropriate locks/versions/serialization |
| Writer locks document, revoker only deletes grant | Locking protocol bypassed | Both must lock the same resource |
| `SELECT FOR UPDATE` outside a transaction | Lock may release immediately | Place lock inside a real `@Transactional` |
| `@Version` only on document | Misses separate grant changes | Tie policy version to revocation |
| Assuming `REPEATABLE_READ` sees latest data | Snapshot can be stale | Understand DB semantics + locks/versions |
| Retrying after conflict while keeping `allowed=true` | Authorizes using stale snapshot | Re-run checks from scratch in a new transaction |
| Calling `this.edit(...)` from the same bean | Bypasses Spring proxy advice | Separate secured bean, test proxy behavior |
| Using `@PostAuthorize` for money transfers | Side effects may already commit | Pre-write authorization and DB guards |
| Trusting `tenantId` from JSON/header | Bypasses tenant isolation | Derive tenant from verified identity/directory |
| Caching decisions solely by `documentId` | Cross-user/tenant permission leaks | Key by principal/tenant/action/version |
| Revoking on one node while another node's cache stays warm | Old permissions remain active | Distributed invalidation, policy versions |
| Locking multiple documents in arbitrary order | Deadlocks | Sort IDs and standardize lock order |
| Holding locks across external API calls | Prolonged lock waits | Short transactions, outboxes |
| Catching exceptions and returning `true` | Fail-open | Fail closed, monitor infrastructure errors |
| Tests asserting only `403` | UPDATE may have occurred before exception | Read back body/version and grants |
| Using H2 tests in place of production DB | Lock/isolation semantics differ | Testcontainers/integration tests on target DB |
| User has right role but does not own document | Broken object-level authorization | Authority AND owner/tenant/grant |
| Denying after write via filter/audit | Cannot undo side effects | Block at the transaction boundary |

## 13. Self-Check Exercises

1. **What does TOCTOU mean in authorization?**  
   Permission is checked at T1, yet permission data changes before the operation executes at T2.

2. **Does `@PreAuthorize` automatically lock ACL tables?**  
   No; it decides whether to allow invoking the method, not act as a DB lock.

3. **Which isolation level does `@Transactional` use by default?**  
   `Isolation.DEFAULT` of the transaction manager/DB—not `SERIALIZABLE` by default.

4. **Why can `READ_COMMITTED` still cause TOCTOU?**  
   Grants can change between two statements in the same transaction without appropriate locks/protocols.

5. **If revoker commits before writer acquires the document lock, what must writer do?**  
   Re-read grants/owner/tenant and deny if permission is gone.

6. **If writer acquires the document lock first while revoker waits, can writer commit?**  
   Yes, if the grant is still valid and policy permits writer-before-revoke ordering. Revoker commits after writer releases the lock.

7. **Why doesn't Document's `@Version` detect a deleted grant?**  
   Because grants live in a separate table/entity; `Document.version` does not automatically change.

8. **Does `UPDATE ... WHERE EXISTS grant` guarantee all real-time revocation semantics?**  
   Not automatically; DB isolation/snapshots/locking and competing transactions must be analyzed.

9. **When retrying a serialization failure, can you reuse `wasAllowed=true` from the previous attempt?**  
   No. Fetch fresh permission data and re-verify inside the new transaction.

10. **Must owner transfer use the same locking protocol?**  
    Yes, whenever ownership affects writer permissions under the application's contract.

11. **Is a `document:write` role enough for a T1 user to edit a T2 document?**  
    No. Tenant and object-level permissions must also be verified from server data.

12. **How do you test concurrency more reliably than `Thread.sleep()`?**  
    Use latches/barriers, real transactions/row locks, and assert DB state post-commit.

13. **When locking multiple objects, how do you reduce deadlocks?**  
    Standardize lock ordering (e.g., ascending IDs) and keep transactions short.

14. **Can `@PostAuthorize` guarantee a write rolls back if the user lacks permission?**  
    Do not rely on it. Post-checks can run after side effects/commit depending on advisor order.

15. **If ACLs live in a service outside the DB, can local `@Transactional` lock the ACLs?**  
    No. Explicit consistency protocols or authoritative services are required.

## 14. Official References and Takeaways

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, advisor/proxy behavior, and `@PostAuthorize` caveats for writes.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, isolation, rollback, and proxy/self-invocation.
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, and transaction scope differences.
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` for tests/workflows.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): `@Lock(PESSIMISTIC_WRITE)` and queries.
- [Spring Boot — SQL databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `JdbcTemplate`, datasources, script initialization, and transaction managers.
- [PostgreSQL — Explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, `FOR UPDATE`, writer contention, and lock release on transaction end.
- [PostgreSQL — Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation characteristics and serialization failures.
- [Spring Security — ACL authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACEs, permission evaluators, owners, caching, and ACL services.

**Summary:** data permissions are **dynamic** data. `@PreAuthorize` helps fail early, yet writes must re-verify **owner, tenant, grants, ACLs, and state** under a protocol consistent with permission changes. One clear option is **having both writer and revoker lock the same document row, read/check permissions after locking, and write before committing**. Other architectures require conditional SQL, authz versions, isolation/retries, or cross-service protocols. Always test both commit orders, rollbacks, cache invalidation, and DB state after denials.