# Dynamic Policy Store and Authoritative Policy Data Sources

> **Topic:** Spring Security – authorization → **Dynamic Policies**. This lesson guides you through designing a permission/policy store that can change while the system is running, identifying the **source of truth** for each piece of authorization data, publishing policies by revision, evaluating permissions with Spring Security, and handling caching, multi-tenancy, auditing, rollback, race conditions, and infrastructure failures. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, JDBC, H2, and JUnit.

## 1. The problem: permissions change without redeploying

An application might start with:

~~~java
@PreAuthorize("hasRole('EDITOR')")
public void renameDocument(Long id, String title) {
    // ...
}
~~~

At that point `ROLE_EDITOR` is checked from `Authentication.getAuthorities()`, yet the hard questions remain:

- EDIT on **which resource type**, in **which tenant**?
- If an admin revokes EDIT at 10:00, will a request at 10:01 still use the old permission?
- If a user holds both a granted role and a denied role, which rule takes precedence?
- Which rules are **currently active** if a new draft exists?
- Which source is right when the token, policy database, and cache on two nodes disagree?
- Who is allowed to edit/publish policies, who approves them, and how do rollback and audit work?
- If the policy store is down or has no matching rule, should access be allowed by default?

**Dynamic policy** means decisions change when the effective permission configuration changes, without necessarily modifying code or restarting. However, this is only safe when permission data is controlled by an authoritative source, versioned, and enforced properly.

Example:

~~~text
Tenant acme, revision 1:
  ROLE_READER  READ -> ALLOW
  ROLE_EDITOR  EDIT -> ALLOW
  ROLE_BLOCKED READ -> DENY
  ROLE_BLOCKED EDIT -> DENY

Tenant beta, revision 1:
  ROLE_READER  READ -> ALLOW
  ROLE_EDITOR  EDIT -> ALLOW
~~~

Alice has READER + EDITOR in acme, so she can READ/EDIT acme documents. Bob has READER in beta and does **not** thereby gain read access to acme. Carol has READER + BLOCKED in acme, so READ is denied under the **explicit DENY overrides ALLOW** rule defined by the application.

## 2. Policy, entitlement, membership, resource: source of truth for each type

A **source of truth** is the authoritative source for a given type of fact, not necessarily a single database for the entire system.

| Data type | Common source of truth | What cannot replace the source of truth |
| --- | --- | --- |
| Identity, account, active status | IAM/IdP, identity directory | Name from request body, unverified headers |
| User–tenant–role membership | Membership DB or group service with a clear contract | Old JWT after a role has been revoked |
| Role and permission catalog | Managed IAM/policy catalog | Arbitrary role names sent by the client |
| Currently active policy | Policy store + active revision pointer | Draft, stale cache, unsynced replica |
| Resource tenant/owner/status | Domain database | `tenantId` in URL used as proof of ownership |
| Business entitlement/license | Billing/entitlement service | Frontend-only feature flag |
| Authorization decision | PDP evaluating against policy and valid inputs | A cached boolean lacking a revision |
| Policy cache | Copy for performance optimization | Place that creates/overrides the original policy |
| Audit | Append-only log/audit system | In-memory logs lost on restart |

Example of a document EDIT request:

~~~text
Authentication verified principal = "alice"
Target tenant selector = "acme"
Resource = Document#101
Resource DB: Document#101.tenant = "acme"
Membership DB: alice has ROLE_EDITOR active in acme
Policy head: acme revision 7 is active
Policy rules rev 7: ROLE_EDITOR EDIT ALLOW
Conditions: document not locked, tenant active
=> decision ALLOW
~~~

No single factor is sufficient on its own: `tenantId=acme` in the URL is only the desired access target, not proof that the actor belongs to that tenant. A role in a JWT does not automatically mean active current membership. An ALLOW policy does not permit operating on a nonexistent resource or one belonging to another tenant.

### 2.1. Authentication is not itself a dynamic policy store

Spring Security stores `GrantedAuthority` instances inside `Authentication`. If a policy only uses `hasAuthority('DOC_EDIT')` and that authority was snapshotted into a JWT at login, an old token can keep holding the permission even though an administrator just revoked the role-permission mapping.

~~~text
T1: Alice's JWT contains ROLE_EDITOR
T2: Admin publishes a policy removing EDIT permission from ROLE_EDITOR
T3: Non-expired JWT still contains ROLE_EDITOR
T4: hasRole("EDITOR") may still evaluate to true
T5: PDP reads new active policy -> EDIT DENY
~~~

When implementing dynamic permissions, distinguish **identity authentication** from **effective policy data**. Updating a policy does not automatically refresh JWTs; changing a role mapping in authentication does not automatically invalidate the policy cache. If membership is managed by IAM, you must design how the PDP receives new membership updates or accept a bounded stale window.

### 2.2. One or multiple sources of truth?

If IAM is the source of truth for membership, avoid letting the policy store write membership independently where the two can contradict each other. You can use the policy store as a **read model** of membership, but you must specify event ordering, versioning, retries, and reconciliation. If the domain service owns documents, the policy service must not infer that a document still exists solely from an old ACL entry.

**Rule:** each fact has a clear owner; replicas have a freshness/consistency contract and a recovery procedure from the source of truth.

## 3. PAP, PDP, PEP, PIP architecture

These terms help separate responsibilities:

| Term | Responsibility | Example in Spring |
| --- | --- | --- |
| PAP – Policy Administration Point | Author/approve/publish policies | PolicyPublisher, admin workflow |
| PDP – Policy Decision Point | Compute ALLOW/DENY from request + current policy | PolicyGate or custom AuthorizationManager |
| PEP – Policy Enforcement Point | Block action when PDP denies | Method Security, HTTP AuthorizationFilter |
| PIP – Policy Information Point | Return trusted attributes to PDP | Membership DB, resource DB, IAM |
| Policy store | Store rules, revisions, and active pointer | SQL or policy service |
| Audit | Record who changed policy/decisions under which revision | Audit DB, stream, SIEM |

~~~text
               Admin (PAP)
                   |
       draft -> validate -> approve
                   |
             publish revision
                   |
             Policy Store
                   |
           active revision=N
                   v
request -> Spring PEP -> PolicyGate/PDP
                             |        \
                             |         \-> PIP memberships/resources
                             |
                         ALLOW / DENY
                             |
            DENY --> reject, no mutation
            ALLOW --> application service / DB
~~~

Policy store administration roles are highly sensitive: a single person can grant permissions to thousands of users by changing one rule. Do not automatically allow someone who can update documents to edit policies as well. A tenant admin should only administer policies **within their own tenant**, not grant system-wide permissions.

## 4. Data model of a revisioned policy store

This lesson uses four tables:

| Table | Key attributes | Meaning |
| --- | --- | --- |
| `policy_head` | tenant_id, active_revision | Effective revision pointer |
| `policy_rule` | tenant_id, revision, role, action, effect | Immutable rules in the revision's snapshot |
| `tenant_membership` | principal, tenant_id, role, active | User's role **within the tenant**, currently active |
| `tenant_document` | id, tenant_id, title | Authoritative source identifying which tenant a resource belongs to |

A policy:

~~~json
{
  "tenantId": "acme",
  "revision": 7,
  "role": "ROLE_EDITOR",
  "action": "EDIT",
  "effect": "ALLOW"
}
~~~

### 4.1. Active version and draft version are distinct

~~~text
acme: revision 6 ACTIVE
acme: revision 7 DRAFT, not yet in use

PUBLISH:
  BEGIN TRANSACTION
  insert all policy_rule rows for revision 7
  update policy_head.active_revision=7
  COMMIT

Only requests after publish read revision 7.
~~~

If 8 out of 10 rules are inserted and then an error occurs before commit, the transaction must roll back so `active_revision` still points to revision 6. Do not directly mutate multiple rows of an ACTIVE revision in separate transactions because requests could observe a half-old, half-new policy.

### 4.2. Snapshot vs. patch

- **Full snapshot:** each revision stores *all* effective rules for the scope. A rule absent from a new revision means that rule is revoked.
- **Patch/delta:** stores only changes relative to the previous version. The PDP must reconstruct state and resolve ordering, conflicts, and rollbacks.

This lesson chooses full snapshot: easy to test, debug, and reproduce a historical decision. Production requires adding a `policy_revision` table containing status, author, approver, checksum, reason, effective time, audit, outbox, and retention.

### 4.3. Designing precedence and default-deny

An example custom PDP defines the rule:

~~~text
effects = all matching rules
          for the principal's active membership,
          matching tenant, action, revision

if effects contains DENY: return DENY
if effects contains ALLOW: return ALLOW
return DENY
~~~

Never assume every policy engine uses DENY-overrides by default. Choose one combining algorithm, document it, test it, and apply it consistently. In this lesson, any unknown action or missing rule is **denied**. Never catch a DB exception and return ALLOW to preserve availability.

## 5. Spring Boot + Spring JDBC application (Java 17+)

Runnable example in a Spring Boot 3.x project with compatible Gradle plugins, Spring Security 6.x, and H2. Uses Spring JDBC so you can clearly see the SQL JOIN between active policy, membership, and resource.

Code includes:
- `DynamicPolicyApplication` enabling Method Security.
- `PolicyGate` reading the effective policy on every request.
- `DocumentService` reading documents guarded by `@PreAuthorize`, and updating documents guarded inside a transaction.
- `PolicyPublisher` publishing a full snapshot atomically.
- Integration tests proving policy and membership change **without changing Java code**.

### 5.1. Dependencies

`build.gradle` in the project already configures the Java, Spring Boot, and dependency management plugins:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

No web starter is needed if only testing Spring-managed services. The Spring Security starter **does not automatically enable** `@EnableMethodSecurity`.

### 5.2. Test datasource

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:dynamic_policy;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.continue-on-error=false
~~~

In-memory H2 is not a production policy store. Use Flyway/Liquibase migrations and test dialect/transaction isolation against the target database.

### 5.3. SQL schema

**`src/test/resources/schema.sql`**

~~~sql
create table policy_head (
    tenant_id varchar(40) primary key,
    active_revision bigint not null,
    constraint chk_active_revision check (active_revision > 0)
);

create table policy_rule (
    tenant_id varchar(40) not null,
    revision bigint not null,
    role varchar(50) not null,
    action varchar(24) not null,
    effect varchar(8) not null,
    primary key (tenant_id, revision, role, action),
    foreign key (tenant_id) references policy_head(tenant_id),
    constraint chk_policy_effect check (effect in ('ALLOW','DENY'))
);

create table tenant_membership (
    principal varchar(64) not null,
    tenant_id varchar(40) not null,
    role varchar(50) not null,
    active boolean not null,
    primary key (principal, tenant_id, role),
    foreign key (tenant_id) references policy_head(tenant_id)
);

create table tenant_document (
    id bigint primary key,
    tenant_id varchar(40) not null,
    title varchar(160) not null,
    foreign key (tenant_id) references policy_head(tenant_id)
);

create index idx_policy_rule on policy_rule(tenant_id, revision, action);
create index idx_membership on tenant_membership(principal, tenant_id, active);
~~~

The `policy_rule` table uses its PK to prevent a single role from having two different effects for the same action/revision/tenant. Allowed/denied states are restricted to ALLOW/DENY by the database. `tenant_document` holds the actual tenant, not accepted from the client. For production, you should add constraints, timestamps, policy author/approver, immutable history/audit, and a revision state table.

### 5.4. Seed data

**`src/test/resources/data.sql`**

~~~sql
insert into policy_head(tenant_id, active_revision)
values ('acme', 1), ('beta', 1);

insert into policy_rule(tenant_id, revision, role, action, effect)
values
  ('acme', 1, 'ROLE_READER', 'READ', 'ALLOW'),
  ('acme', 1, 'ROLE_EDITOR', 'EDIT', 'ALLOW'),
  ('acme', 1, 'ROLE_BLOCKED', 'READ', 'DENY'),
  ('acme', 1, 'ROLE_BLOCKED', 'EDIT', 'DENY'),
  ('beta', 1, 'ROLE_READER', 'READ', 'ALLOW'),
  ('beta', 1, 'ROLE_EDITOR', 'EDIT', 'ALLOW');

insert into tenant_membership(principal, tenant_id, role, active)
values
  ('alice', 'acme', 'ROLE_READER', true),
  ('alice', 'acme', 'ROLE_EDITOR', true),
  ('bob', 'beta', 'ROLE_READER', true),
  ('carol', 'acme', 'ROLE_READER', true),
  ('carol', 'acme', 'ROLE_BLOCKED', true);

insert into tenant_document(id, tenant_id, title)
values
  (101, 'acme', 'ACME-original'),
  (202, 'beta', 'BETA-original');
~~~

Alice has READ + EDIT on acme; Bob has READ on beta; Carol has both READ ALLOW and READ DENY but is blocked under DENY-overrides.

### 5.5. Boot application

**`src/main/java/demo/policy/DynamicPolicyApplication.java`**

~~~java
package demo.policy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DynamicPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DynamicPolicyApplication.class, args);
    }
}
~~~

### 5.6. Policy Decision Point: PolicyGate

**`src/main/java/demo/policy/PolicyGate.java`**

~~~java
package demo.policy;

import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("policyGate")
public class PolicyGate {
    private static final Set<String> ACTIONS = Set.of("READ", "EDIT");

    private final JdbcTemplate jdbc;

    public PolicyGate(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean allowed(
            Authentication authentication,
            String tenantId,
            Long documentId,
            String action) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || tenantId == null
                || !tenantId.matches("[a-z][a-z0-9-]{1,39}")
                || documentId == null
                || documentId <= 0
                || action == null
                || !ACTIONS.contains(action)) {
            return false;
        }

        Long count = jdbc.queryForObject(
                """
                select count(*)
                  from tenant_document
                 where id = ? and tenant_id = ?
                """,
                Long.class, documentId, tenantId);

        if (count == null || count != 1L) {
            return false;
        }

        List<String> effects = jdbc.query(
                """
                select r.effect
                  from policy_rule r
                  join policy_head h
                    on h.tenant_id = r.tenant_id
                   and h.active_revision = r.revision
                  join tenant_membership m
                    on m.tenant_id = r.tenant_id
                   and m.role = r.role
                 where r.tenant_id = ?
                   and r.action = ?
                   and m.principal = ?
                   and m.active = true
                """,
                (rs, rowNum) -> rs.getString("effect"),
                tenantId, action, authentication.getName());

        if (effects.contains("DENY")) {
            return false;
        }
        return effects.contains("ALLOW");
    }
}
~~~

**How PolicyGate decides:**

1. Unauthenticated or anonymous user → false.
2. Invalid tenant/action/ID → false.
3. No document exists belonging to the specified tenant → false.
4. Queries rules **only from the active revision** and **only matching active roles** of the user in the target tenant.
5. If DENY is present → false, even if ALLOW is also present.
6. ALLOW present and no DENY → true.
7. No matching rules → false.

The SQL uses prepared placeholders rather than concatenating request values directly. **There is no cache in the example**, so every decision reads the source of truth on each call. If the DB fails, the exception propagates; it is never caught to return true.

The method does not rely on authorities self-assigned by `@WithMockUser` in the example; it uses the authenticated principal name to look up membership in the DB. In production, the principal name should be an immutable subject ID, not an email that could be reused or collide across tenants.

### 5.7. Enforcement: DocumentService

**`src/main/java/demo/policy/DocumentService.java`**

~~~java
package demo.policy;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final JdbcTemplate jdbc;
    private final PolicyGate gate;

    public DocumentService(JdbcTemplate jdbc, PolicyGate gate) {
        this.jdbc = jdbc;
        this.gate = gate;
    }

    @PreAuthorize(
            "@policyGate.allowed(authentication, #tenantId, #id, 'READ')")
    @Transactional(readOnly = true)
    public String readTitle(
            @P("tenantId") String tenantId,
            @P("id") Long id) {

        return jdbc.query(
                """
                select title from tenant_document
                 where id = ? and tenant_id = ?
                """,
                rs -> {
                    if (!rs.next()) {
                        throw new AccessDeniedException("Not available");
                    }
                    return rs.getString(1);
                },
                id, tenantId);
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional
    public void rename(
            @P("tenantId") String tenantId,
            @P("id") Long id,
            String newTitle) {

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        Boolean exists = jdbc.query(
                """
                select id from tenant_document
                 where id = ? and tenant_id = ?
                 for update
                """,
                rs -> rs.next(),
                id, tenantId);

        if (!Boolean.TRUE.equals(exists)) {
            throw new AccessDeniedException("Not available");
        }

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (!gate.allowed(auth, tenantId, id, "EDIT")) {
            throw new AccessDeniedException("Not permitted");
        }

        int affected = jdbc.update(
                """
                update tenant_document
                   set title = ?
                 where id = ? and tenant_id = ?
                """,
                newTitle, id, tenantId);

        if (affected != 1) {
            throw new IllegalStateException("Concurrent change");
        }
    }
}
~~~

Why do read and write differ?

- `@PreAuthorize("@policyGate...")` checks READ right at the method boundary; the body still queries by tenant as a second guard.
- For WRITE, `isAuthenticated()` guards the entry before the body, while the EDIT check is placed **inside the transaction** after locking the document to narrow the time-of-check/time-of-use window.
- `@P("tenantId")` and `@P("id")` help Spring Security resolve the right SpEL variables, even when not compiled with `-parameters`.
- `@Transactional` and Method Security operate via Spring-managed proxies. Do not test with `new DocumentService(...)` or self-invocation and assume annotations are enforced.
- `SELECT ... FOR UPDATE` only locks the document row; it does not automatically lock membership or `policy_head`. Write paths requiring immediate revocation must add synchronization/revision guards across all related policy sources.

### 5.8. Publish snapshot: PolicyPublisher

**`src/main/java/demo/policy/PolicyPublisher.java`**

~~~java
package demo.policy;

import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PolicyPublisher {

    public record RuleSpec(String role, String action, String effect) {
    }

    private static final Set<String> ACTIONS =
            Set.of("READ", "EDIT");
    private static final Set<String> EFFECTS =
            Set.of("ALLOW", "DENY");

    private final JdbcTemplate jdbc;

    public PolicyPublisher(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("hasAuthority('POLICY_PUBLISH')")
    @Transactional
    public long publish(String tenantId, List<RuleSpec> snapshot) {

        if (tenantId == null
                || !tenantId.matches("[a-z][a-z0-9-]{1,39}")
                || snapshot == null || snapshot.isEmpty()) {
            throw new IllegalArgumentException("Invalid snapshot");
        }

        // Lock the ACTIVE pointer to serialize publishers for the same tenant.
        Long active = jdbc.query(
                """
                select active_revision from policy_head
                 where tenant_id = ?
                 for update
                """,
                rs -> rs.next() ? rs.getLong(1) : null,
                tenantId);

        if (active == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        long nextRevision = active + 1;

        for (RuleSpec rule : snapshot) {
            if (rule == null
                    || rule.role() == null
                    || !rule.role().matches("ROLE_[A-Z0-9_]+")
                    || rule.action() == null
                    || !ACTIONS.contains(rule.action())
                    || rule.effect() == null
                    || !EFFECTS.contains(rule.effect())) {
                throw new IllegalArgumentException("Invalid policy rule");
            }

            jdbc.update(
                    """
                    insert into policy_rule
                        (tenant_id, revision, role, action, effect)
                    values (?, ?, ?, ?, ?)
                    """,
                    tenantId, nextRevision,
                    rule.role(), rule.action(), rule.effect());
        }

        int updated = jdbc.update(
                """
                update policy_head
                   set active_revision = ?
                 where tenant_id = ? and active_revision = ?
                """,
                nextRevision, tenantId, active);

        if (updated != 1) {
            throw new IllegalStateException("Revision conflict");
        }

        return nextRevision;
    }
}
~~~

**Significance:**

- `POLICY_PUBLISH` is a control-plane authority **reserved** for the example; regular users must not be allowed to call publish. Production must add tenant restrictions, approvals, step-up MFA, and auditing.
- `@Transactional` wraps both the INSERT of rules and the active pointer update in **a single database transaction**.
- Locking the `policy_head ... FOR UPDATE` row serializes two concurrent publishers for the same tenant on databases that support it. You must test isolation/locking on the real DB.
- `snapshot` is the **full policy** for the tenant at the new revision; rules not carried over will no longer be in effect.
- An invalid rule after inserting an earlier rule throws a runtime exception → the transaction rolls back all INSERTs and keeps the active revision unchanged.
- The unique PK protects against duplicate keys; `effect` has a CHECK constraint.
- The sample code does not include policy audit/outbox and does not by itself satisfy all production governance requirements.

If you want to reduce the risk of accidentally dropping permissions when an admin publishes based on an old version, you can add `expectedActiveRevision` from the UI and reject mismatches instead of always computing `active+1`.

## 6. Testing runtime policy and membership changes

The integration tests below boot H2, Spring JDBC, and Spring Method Security proxies. `@WithMockUser` creates a test `Authentication` rather than proving a real JWT login flow.

**`src/test/java/demo/policy/DynamicPolicyIntegrationTest.java`**

~~~java
package demo.policy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = DynamicPolicyApplication.class)
class DynamicPolicyIntegrationTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired PolicyGate gate;
    @Autowired DocumentService documents;
    @Autowired PolicyPublisher publisher;

    @BeforeEach
    void reset() {
        // No @Transactional on tests; services must perform real commits/rollbacks.
        jdbc.update("update policy_head set active_revision = 1");
        jdbc.update("delete from policy_rule where revision > 1");
        jdbc.update("update tenant_membership set active = true");
        jdbc.update(
                "update tenant_document set title = 'ACME-original' where id = 101");
        jdbc.update(
                "update tenant_document set title = 'BETA-original' where id = 202");
    }

    private Authentication alice() {
        return new UsernamePasswordAuthenticationToken(
                "alice", "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    @WithMockUser(username = "alice")
    void aliceCanReadAndEditAcme() {
        assertEquals("ACME-original",
                documents.readTitle("acme", 101L));

        documents.rename("acme", 101L, "Reviewed");

        assertEquals("Reviewed",
                documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "bob")
    void betaReaderCannotEditOrReadAcme() {
        assertEquals("BETA-original",
                documents.readTitle("beta", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.rename("beta", 202L, "Changed"));

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void foreignTenantAndIdAreDenied() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("beta", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.rename("acme", 202L, "Hacked"));
    }

    @Test
    @WithMockUser(username = "carol")
    void blockedRoleOverridesReaderGrant() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingMembershipChangesDecisionWithoutDeployment() {
        assertEquals("ACME-original",
                documents.readTitle("acme", 101L));

        jdbc.update(
                """
                update tenant_membership set active = false
                 where principal = ? and tenant_id = ? and role = ?
                """,
                "alice", "acme", "ROLE_READER");

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));

        // Alice still has ROLE_EDITOR.
        documents.rename("acme", 101L, "Edited");
        assertEquals("Edited", jdbc.queryForObject(
                "select title from tenant_document where id = 101",
                String.class));
    }

    @Test
    @WithMockUser(username = "operator", authorities = "POLICY_PUBLISH")
    void newRevisionIsUsedImmediately() {
        long revision = publisher.publish("acme", List.of(
                new PolicyPublisher.RuleSpec(
                        "ROLE_READER", "READ", "DENY"),
                new PolicyPublisher.RuleSpec(
                        "ROLE_EDITOR", "EDIT", "ALLOW")));

        assertEquals(2L, revision);
        assertEquals(2L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));

        assertFalse(gate.allowed(alice(), "acme", 101L, "READ"));
        assertTrue(gate.allowed(alice(), "acme", 101L, "EDIT"));

        // Test switches Authentication to Alice for Spring Method Security.
        SecurityContextHolder.getContext().setAuthentication(alice());

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));

        documents.rename("acme", 101L, "Policy updated");
        assertEquals("Policy updated", jdbc.queryForObject(
                "select title from tenant_document where id = 101",
                String.class));
    }

    @Test
    @WithMockUser(username = "operator", authorities = "POLICY_PUBLISH")
    void invalidSecondRuleRollsBackTheFirstInsert() {
        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("acme", List.of(
                        new PolicyPublisher.RuleSpec(
                                "ROLE_READER", "READ", "ALLOW"),
                        new PolicyPublisher.RuleSpec(
                                "ROLE_EDITOR", "EDIT", "INVALID"))));

        assertEquals(1L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));
        assertEquals(0L, jdbc.queryForObject(
                """
                select count(*) from policy_rule
                 where tenant_id = 'acme' and revision = 2
                """,
                Long.class));

        assertTrue(gate.allowed(alice(), "acme", 101L, "READ"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ordinaryUserCannotPublishPolicy() {
        assertThrows(AccessDeniedException.class,
                () -> publisher.publish("acme", List.of(
                        new PolicyPublisher.RuleSpec(
                                "ROLE_READER", "READ", "DENY"))));

        assertEquals(1L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingPolicyOrResourceDefaultsToDeny() {
        assertFalse(gate.allowed(alice(), "acme", 101L, "DELETE"));
        assertFalse(gate.allowed(alice(), "acme", 999L, "READ"));
        assertFalse(gate.allowed(alice(), "beta", 202L, "EDIT"));
    }
}
~~~

### Expected results

| Test | Behavior |
| --- | --- |
| Alice READ + EDIT acme | Allowed |
| Bob READ beta but not EDIT | READ allow, EDIT deny |
| Alice uses beta's resource ID | Deny |
| Carol has both READER and BLOCKED | DENY overrides |
| Revoke Alice's READER membership | READ denied immediately on next check; EDIT not automatically lost |
| Publish revision 2 changing READ to DENY | PDP uses revision 2, no Java code change |
| Second rule invalid in transaction | First rule rolled back; revision 1 remains active |
| Ordinary user calls publish | Method Security denies |
| Unknown action, missing resource, tenant without membership | Deny by default |

Run on macOS/Linux:

~~~text
./gradlew test --tests demo.policy.DynamicPolicyIntegrationTest
~~~

Windows:

~~~text
gradlew.bat test --tests demo.policy.DynamicPolicyIntegrationTest
~~~

There is no `System.out.println`, so there is no fixed business stdout. You should verify that all assertions pass and Gradle completes the `test` task. The code above has been statically reviewed; before real-world use, it must be run against your specific Spring Boot/Security versions and target database.

## 7. Why "re-read DB on every request" alone does not solve everything

In the demo, `PolicyGate` reads the SQL source of truth every time. However, a real request has multiple steps:

~~~text
T1: PDP reads membership Alice=EDITOR, policy revision 7 -> ALLOW.
T2: Admin revokes membership or publishes revision 8.
T3: Application service is processing UPDATE.
~~~

This is **time-of-check/time-of-use (TOCTOU)**. A transaction when updating the resource and locking the document row narrows one class of races, but does not automatically lock membership or `policy_head`. For highly sensitive writes, you need a policy revision guard, isolation/locking on related data, or an agreement between the PDP and service on a time-bounded/conditional decision snapshot.

Also do not confuse policy commit with business data commit on another service. `@Transactional` only protects operations participating in **the same transaction manager**, and does not automatically provide atomicity across a different database and a message broker/network.

## 8. Policy caching, multiple instances, and revocation lag

Production may add caching to reduce SQL load:

~~~text
DB active policy acme = revision 18
        |
        +--- Node A caches revision 18
        +--- Node B caches revision 17 (STALE)
        +--- Node C caches revision 18
~~~

If revision 18 revokes EDIT, Node B can still erroneously allow it. **Cache is not the source of truth**.

| Caching approach | Strengths | Limitations |
| --- | --- | --- |
| No cache | Always reads current DB | Higher load/latency |
| Local TTL | Simple, fast | Revocation can lag up to full TTL |
| Local + pub/sub invalidation | Propagates notifications when policy changes | Lost/delayed events, reordering, network partitions |
| Shared backend | Can share policy snapshot | Key aliases, serializers, refill race |
| Cache by immutable revision | Snapshot has clear ID, no rule mixing | Still need to determine active revision |
| Revision check at decision time | Detects stale cache | Increases queries to version service |
| Direct DB on sensitive paths | Avoids stale permissions from cache | More SQL; still has concurrent commit races |

**Policy publish must be propagated after commit**, avoiding the case where a node receives invalidation before commit, re-reads the old policy, and caches stale data.

~~~text
Transaction:
  insert revision 18 rules
  update policy_head.active_revision=18
  insert outbox PolicyActivated(acme,18)
COMMIT
  publisher sends event
  every node evicts/reloads acme policy scope
~~~

`@TransactionalEventListener(phase = AFTER_COMMIT)` only guarantees the callback inside that JVM after commit, not delivery to other nodes. If the node crashes right after commit but before publishing, the event can be lost. **Transactional outbox** combined with a durable event bus, retries/acks, and idempotent consumers closes part of that gap.

### 8.1. Revision is the safety key when receiving events

An event:

~~~json
{
  "type": "POLICY_ACTIVATED",
  "tenantId": "acme",
  "revision": 18,
  "changeId": "change-982"
}
~~~

The consumer needs to:
1. Validate the tenant and event origin.
2. Never downgrade the cache from revision 19 to 18 due to a late-arriving event.
3. Handle duplicate events idempotently.
4. If a missing revision is detected, query the active pointer again.
5. Evict all keys/aliases belonging to the tenant/scope.
6. Measure the latency from commit to enforcement on every node.

### 8.2. The "refill after invalidate" race

~~~text
T1 Node B cache miss, currently running SELECT for revision 17.
T2 Node A commits revision 18 and sends invalidate.
T3 Node B evicts cache.
T4 B's stale query finishes, puts revision 17 into cache.
T5 New request reads cached revision 17 -> erroneous ALLOW.
~~~

You need a version-aware conditional put or an active revision check at decision time, rather than just firing an event and assuming it is done. TTL can bound the stale window, **not eliminate** the race. For operations requiring immediate revocation, stronger mechanisms than asynchronous invalidation are required.

## 9. Policy administration is a security change

Full workflow:

1. **Draft:** authorized user creates an inactive version.
2. **Validate:** schema, role/action whitelist, target tenant, DENY precedence, resource scope, duplicate rules, conditions.
3. **Review:** display diff against active, calculate blast radius, detect grants affecting an overly broad group.
4. **Test:** run positive/negative tests, cross-tenant, deny-overrides, missing rules.
5. **Approve:** 2-person rule/step-up MFA for sensitive privilege-expanding changes.
6. **Publish:** transaction writes full snapshot + active pointer + outbox; records author/reason/ticket.
7. **Observe:** monitor revision distribution, decision anomalies, cache invalidation lag.
8. **Rollback:** publish a new revision containing a known-safe snapshot; do not edit history in-place.
9. **Reconcile:** compare active revision against caches/agents across all nodes.

### 9.1. A tenant admin must not escalate to a system policy admin

Example required policy:

~~~text
canPublish(actor, tenant, proposedRules):
  actor authenticated
  AND actor has policy administration permission in target tenant
  AND all roles/actions are in tenant-grantable allowlist
  AND does not grant ROLE_SYSTEM_ADMIN/POLICY_PUBLISH_GLOBAL
  AND does not modify another tenant's policy
  AND has sufficient approvals for sensitive changes
~~~

The demo's `POLICY_PUBLISH` is a **global permission granted solely for tests**, not something a `ROLE_TENANT_ADMIN` holder owns by default. Production must separate `POLICY_DRAFT`, `POLICY_REVIEW`, `POLICY_PUBLISH` and enforce tenant scoping. Never expose policy modification to a public API lacking actor enforcement and auditing.

### 9.2. Policy rollback does not undo actions that already occurred

If revision 18 allowed an update, a user wrote data, and then revision 19 revoked the permission, reverting to an old policy **does not restore the data**. Separate:
- Policy rollback: changes rules for future requests.
- Business compensation: reverts side effects via a separate workflow.
- Audit: retains records of actor, action, resource, policy revision, and decision.

## 10. Auditing with the right source and right revision

A decision log may include:

~~~text
decisionId=authz-874
subject=user-17
tenant=acme
resourceType=DOCUMENT
resourceId=101
action=EDIT
policyRevision=18
decision=DENY
reason=EXPLICIT_DENY
~~~

Log minimal metadata; do not put tokens, passwords, or sensitive document contents into logs. When policies span multiple nodes, the revision is essential data to answer "Why was this request allowed while that request was blocked?".

Policy change audits must record the requester, approver, diff/checksum, publish timestamp, old/new revisions, tenant, reason/ticket, and commit outcome. If the audit write sits inside a rolled-back transaction, the log can disappear; for critical forensic requirements, design a dedicated audit store/outbox.

## 11. Common pitfalls and safe handling

| Symptom | Cause | Solution |
| --- | --- | --- |
| Policy edited but permissions do not change | App only uses `hasRole` against an old JWT | Connect PDP to read active policy + membership |
| Node A denies, Node B allows | Stale policy cache | Version/invalidation after commit, monitoring |
| Publish fails after 3 rules yet new policy is active | Published across multiple transactions or updated pointer early | Full snapshot + single transaction |
| User has READER and BLOCKED yet can still READ | Checked only for ALLOW presence | Define/test DENY overrides |
| No rule exists yet user is permitted | Default allow or permissive exception fallback | Default DENY, fail closed |
| Tenant acme reads beta document | Trusted tenant selector or missing resource check | Query by id + tenant + membership |
| Tenant admin publishes system policy | Control-plane lacks scope/allowlist | Tenant-scoped PAP, 2-person approval |
| Revoked role still has permissions | Stale JWT/session/membership cache | Revocation/version/TTL/source-of-truth |
| Policy changed but code only reads draft | Query does not join `active_revision` | Evaluate ACTIVE revision only |
| Permissions change mid-request | TOCTOU, mismatched sources/transactions | Appropriate revision guard/isolation/locking |
| Policy DB fails and user is still permitted | Caught exception → true | DENY/503, never fail open |
| Cache refills stale policy after invalidation | SELECT takes longer than event | Version-aware cache conditional put |
| Policy rollback loses history | Edited/deleted old revision | Immutable revisions, publish new rollback revision |
| Typo in effect causes unexpected allow | Missing catalog/schema validation | CHECK constraint, whitelist, tests |
| `@PreAuthorize` does not run | `@EnableMethodSecurity` not enabled or self-invocation | Enable proxy, test Spring-managed bean |
| Rule uses role "EDITOR" while membership uses "ROLE_EDITOR" | Inconsistent authority naming | Canonical role IDs and migration |
| Data store update succeeds but event is lost | Crash after commit before publish | Transactional outbox, idempotent consumer |
| Service uses SQL grant but ignores domain state | PDP does not check owner/lock/tenant | Domain PIP + clear policy combining |

## 12. Pre-deployment safety test suite

| Scenario | Result |
| --- | --- |
| User has membership role and ALLOW rule | ALLOW for matching object/action/tenant |
| User holds both deny and allow roles simultaneously | DENY |
| User belongs to another tenant | DENY |
| Resource ID belongs to another tenant | DENY |
| Role is revoked in DB | DENY within the time bound specified by policy contract |
| No rule / unknown action | DENY |
| Policy store unreachable | Must not return ALLOW |
| Full snapshot publish succeeds | Active revision switches atomically |
| Publish fails mid-transaction | Active pointer unchanged, no half snapshot |
| Two concurrent publishers | No lost updates, ordered revisions |
| Late or duplicate event | Cache never downgraded to older revision |
| Node disconnected from broker | Reconciliation or appropriate fail closed |
| Admin policy privilege for wrong tenant | DENY |
| Stale cache hit after revocation | Detected by revision/lag tests |
| HTTP/method/job use different PDP paths | Consistent decisions under the same rules |

Asserting HTTP 403 alone is insufficient: tests must also verify **no data mutation**, active revision, SQL rows, cache version, and audit logs when a publisher fails.

## 13. Practice exercises

**Exercise 1 — New policy without deploy.** Publish acme revision 2 changing READER's READ from ALLOW to DENY while keeping EDITOR's EDIT. Verify Alice is denied READ but can still EDIT. Explain why `@PreAuthorize` does not need to change.

**Exercise 2 — Membership revocation.** Toggle Alice's `tenant_membership.active` in acme. Keep the old Authentication; prove the updated policy DB governs READ instead of trusting a role snapshot.

**Exercise 3 — DENY overrides.** Give Carol both READER and BLOCKED. Add another role that also grants READ ALLOW; verify it is still DENY. Write a test with no matching rules → DENY.

**Exercise 4 — Atomic publish.** Insert one valid rule followed by one invalid rule in a publish transaction. Test that both the first INSERT is rolled back and `active_revision` stays unchanged.

**Exercise 5 — Concurrent publishers.** Run two concurrent publish transactions for the same tenant. Use `FOR UPDATE`, expected revision, or optimistic versioning, and verify two snapshots are never simultaneously active and neither publisher's changes are silently lost.

**Exercise 6 — ABAC.** Add `owner_id` and LOCKED state to the resource. Allow EDIT only when tenant matches, role matches, owner matches, and document is unlocked. Test state changes within a transaction.

**Exercise 7 — Multi-instance policy cache.** Warm revision 1 on two nodes. Publish revision 2, intentionally drop the event to node B. Demonstrate stale ALLOW; add a revision gate/TTL or DB fallback.

**Exercise 8 — PAP workflow.** Add DRAFT/APPROVED/ACTIVE; require an approver different from the author for a sensitive ALLOW rule, and verify a tenant user cannot publish a system policy.

**Exercise 9 — Audit/replay.** Record policy revision and decision ID during authorization checks, allowing explanation of why a past request was allowed. Roll back via a new revision instead of mutating history.

**Exercise 10 — External PDP.** Use a custom `AuthorizationManager` or external policy agent. Test that timeout, 5xx, null decision, and unknown revision never turn into ALLOW.

**Completion criteria:** correctly identify the source of truth for identity/membership/policy/resource; separate PAP/PDP/PEP/PIP; design active revision + immutable snapshots; default DENY and combining rules; atomic publish with rollback; connect Spring Security to a dynamic policy DB; test revocation/cross-tenant/cache/version/fail closed.

## Official references

- Spring Security 6.5 – **Method Security** (custom bean with `@PreAuthorize`): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 – **Authorize HTTP Requests** and external `AuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework – **Using @Transactional**, proxy and transaction semantics: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework – **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **Transaction-bound Events**: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework – **Spring JDBC JdbcTemplate**: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
