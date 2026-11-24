# ACL: Granting Permissions per Subject per Object

> **Topic:** Spring Security - authorization  
> **Knowledge group:** Access control models  
> **Objective:** Understand Access Control Lists (ACL), read a permission as a *subject – object – operation* triple, build grant/revoke rules, identify ACL integration points in Spring Security, and prevent cross-resource access vulnerabilities (IDOR/BOLA).

## 1. Why Do We Need ACLs?

Suppose a document storage system has two users, Alice and Bob. Both have the `USER` role; document `doc-42` was created by Alice, while `doc-43` belongs to a different project. Alice may share read-only access to `doc-42` with Bob without allowing Bob to edit it. At the same time, Alice can edit `doc-43` because she was assigned to it. A simple check like `hasRole("USER")` cannot accurately answer **who may perform which operation on which document**.

An **Access Control List (ACL)** is a list of access control entries attached to an object. Each entry describes a **subject** or group of subjects granted/denied **a specific permission** on a **specific object**.

Visual example:

| Object | Recipient Subject | Operation | Decision |
| --- | --- | --- | --- |
| `doc-42` | Alice | READ | Allow |
| `doc-42` | Alice | WRITE | Allow |
| `doc-42` | Bob | READ | Allow |
| `doc-42` | Bob | WRITE | Deny |
| `doc-43` | Alice | WRITE | Allow |
| `doc-43` | Bob | READ | No ACE; handled by default policy |

For Alice and Bob, their roles are identical, yet decisions differ per document. ACLs fit when **fine-grained per-record permissions** are needed: file sharing, ticket permissions, report collaboration, assigning reviewers to a specific proposal, etc.

Mental notation:

```text
canAccess(subject, action, resource, context) -> ALLOW / DENY

subject  = Alice / Bob / GROUP_REVIEWERS
action   = READ / WRITE / DELETE / ADMINISTER
resource = Document:42 / Ticket:19
context  = tenant, state, organization, time, business relationship
```

The ACL provides data for the `(subject, action, resource)` part. If additional conditions exist—such as tenant, expired document, no self-approval, or locked state—the application must still enforce those rules.

## 2. Concepts to Distinguish

| Term | Meaning | Example |
| --- | --- | --- |
| **Principal / subject** | Identity whose permission is being checked | user `alice`, user `bob` |
| **Group / authority** | Group/capability to which the principal belongs | `TEAM_AUDITORS` |
| **Resource / domain object** | Protected object | `Document(id=42)` |
| **Action / permission** | Operation requested on the object | READ, WRITE, DELETE |
| **ACL** | Permission list associated with a resource | ACL of Document:42 |
| **ACE (Access Control Entry)** | A single permission entry in an ACL | Bob is allowed READ on Document:42 |
| **Grant/allow** | ACE confirming permission is granted | Bob: READ = allow |
| **Deny** | ACE denying a permission | Bob: WRITE = deny |
| **Owner** | Owner of the record or of the ACL, depending on the model | Alice created the document |
| **Inheritance** | Child ACL can inherit parent ACL permissions per configuration | File inherits folder permissions |
| **Default deny** | Without grant evidence, the application denies | Carol has no permission to view Document:42 |

Note: the **owner of the business record** and the **owner of the ACL** are not necessarily the same; in Spring Security ACL, owner is an attribute of the ACL, not an assertion that the owner inherently holds every permission. Rules for what an owner can view/edit/delete must be specified explicitly.

**An ACE is not a system-wide role.** Granting Bob `READ` on `doc-42` does not let Bob read all documents. Nor should you store `ROLE_DOCUMENT_42_READER` in each user's token: as documents grow rapidly, authority counts and token update costs become unmanageable.

## 3. ACLs and the Access Control Matrix

You can visualize the entire policy as an **access control matrix**: rows are subjects, columns are objects, and each cell lists permissions. An ACL is the **column-oriented view**: for a given object, list who has which permissions on it.

| Subject \ Object | Document 42 | Document 43 | Document 44 |
| --- | --- | --- | --- |
| Alice | READ, WRITE | READ, WRITE | — |
| Bob | READ | — | READ |
| Carol | — | READ | READ, WRITE |
| Reviewers Group | READ | READ | — |

From this table:

- The ACL of `Document 42` contains entries for Alice, Bob, and the Reviewers group.
- To answer "Which documents can Bob access?", you must **query by subject across multiple ACLs**, not just read one document's ACL.
- A document can have an empty ACL; the default decision must be clearly documented and safe.
- Effective permissions can be affected by group membership, inherited permissions, and the chosen deny/allow rules.

Distinguish three common structures:

1. **ACL (object-centric):** `resource -> subjects + permissions`. Fits a "Who is this document shared with?" screen.
2. **Capability/access grant (subject-centric):** `subject -> resources + permissions`, potentially using unforgeable tokens/handles. Fits capability-based access models.
3. **RBAC (role-based):** `subject -> role -> permissions` on action/feature types. Fits general permissions such as "accountants can create vouchers".

ACL is not the only way to protect an object; in many applications, **ACL + RBAC + attribute conditions** jointly participate in a decision.

## 4. How an ALLOW/DENY Decision Is Formed

A logical flow can be described as follows:

```text
Request: Bob wants to WRITE Document:42
        |
        v
1. Is Bob authenticated and in the right tenant?
        | no -> deny
        v
2. Is the WRITE feature permitted at the application level?
        | no -> deny
        v
3. Look up ACL of Document:42 (and parent ACL if configured)
        |
        v
4. Collect matching SIDs for Bob and current groups
        |
        v
5. Evaluate matching ACEs for the WRITE permission
        | no effective grant / explicit deny -> deny
        v
6. Check additional business policy, state, lock
        | no -> deny
        v
7. Allow write after necessary consistency checks
```

At the design level, **default deny when there is no effective grant** is a safe principle. However, never assume every ACL engine uses the same "deny always wins" rule. How user ACEs, group ACEs, parent ACLs, and multi-permission requests combine is a **specific permission evaluation algorithm**.

Examples of questions to settle before implementation:

- Alice is granted `WRITE` on the child ACL, but denied `DENY WRITE` via a group on the parent ACL: which result does the rule produce?
- If Alice is a member of two groups, one `ALLOW READ` and the other `DENY READ`, which result wins?
- If both `READ` and `WRITE` exist, does requesting `READ + WRITE` mean **both** or **either**?
- If there is no ACE for Bob, do owners or admins pass through automatically?
- When Bob is removed from a group, does the new permission take effect immediately or depend on identity/cache refresh timing?

**In Spring Security ACL:** `DefaultPermissionGrantingStrategy` iterates through permissions and SIDs in input order, finds matching ACEs, and applies its grant/deny algorithm; when no match is found, it may continue to the parent ACL if inheritance is enabled. This is **not** a universal deny-overrides rule regardless of position. Therefore, do not write unit tests based on guessing "deny always has highest priority" without confirming the actual strategy.

## 5. The ACE Model: Granting Within the Exact Scope

For a document sharing system, a minimal ACE might include:

```text
(resource_type, resource_id, recipient_type, recipient_id, permission, granted)
(Document,      42,          USER,           bob,          READ,       true)
(Document,      42,          USER,           bob,          WRITE,      false)
(Document,      42,          GROUP,          reviewers,    READ,       true)
```

Production designs often need `tenant_id`, created/updated timestamps, grantor, grant source, permission expiration, version, or audit events. Not every field exists in Spring Security's built-in ACE table; for those requirements you can use separate domain tables or extend the model.

**Identifiers must be stable:** if usernames or emails can change, do not use those strings as long-lived business keys when a stable subject ID is available. In Spring Security ACL, `PrincipalSid` uses a principal identifier string: ensure this string matches consistently between writing ACEs and evaluating permissions. Permissions granted to `GROUP` are usually represented via authorities in `Authentication`; group membership must be updated and verified from a trusted source.

**An object must be uniquely identified:** `Document:42` must not accidentally collide with `Invoice:42`. In multi-tenant systems, if IDs are only unique per tenant, ACL identifiers must include the tenant or guarantee globally unique IDs while still checking the tenant independently.

**Clear permission semantics:** `READ` means viewing content, `WRITE` means editing, `DELETE` means deleting, `ADMINISTER` means managing the ACL. Never assume `ADMINISTER` implies every business operation or permission to bypass tenants; the delegation scope of each action must be defined.

## 6. Pure Java 17+ Example: Per-Record ACL

This example runs standalone to clarify the **subject – object – permission** triple. It uses a simple model: scan ACEs in order, take the `granted` value of the first ACE matching all three fields, and return `false` otherwise. **This is a custom illustrative algorithm, not a copy of `DefaultPermissionGrantingStrategy` in Spring Security.**

Save the entire code to `AclExample.java`:

```java
import java.util.List;

public class AclExample {

    enum Permission {
        READ, WRITE, DELETE
    }

    record Ace(
        String resourceId,
        String recipientId,
        Permission permission,
        boolean granted
    ) {}

    static boolean can(
        List<Ace> acl,
        String recipientId,
        String resourceId,
        Permission permission
    ) {
        for (Ace entry : acl) {
            if (entry.resourceId().equals(resourceId)
                    && entry.recipientId().equals(recipientId)
                    && entry.permission() == permission) {
                return entry.granted();
            }
        }
        return false; // Default deny when no matching entry exists.
    }

    public static void main(String[] args) {
        List<Ace> acl = List.of(
            new Ace("doc-42", "alice", Permission.READ, true),
            new Ace("doc-42", "alice", Permission.WRITE, false),
            new Ace("doc-42", "bob", Permission.READ, true),
            new Ace("doc-43", "alice", Permission.WRITE, true)
        );

        System.out.println("Alice READ doc-42: "
            + can(acl, "alice", "doc-42", Permission.READ));
        System.out.println("Alice WRITE doc-42: "
            + can(acl, "alice", "doc-42", Permission.WRITE));
        System.out.println("Alice WRITE doc-43: "
            + can(acl, "alice", "doc-43", Permission.WRITE));
        System.out.println("Bob READ doc-42: "
            + can(acl, "bob", "doc-42", Permission.READ));
        System.out.println("Bob READ doc-43: "
            + can(acl, "bob", "doc-43", Permission.READ));
    }
}
```

Run with JDK 17 or later:

```bash
javac AclExample.java
java AclExample
```

Expected output:

```text
Alice READ doc-42: true
Alice WRITE doc-42: false
Alice WRITE doc-43: true
Bob READ doc-42: true
Bob READ doc-43: false
```

Key lessons:

- Alice can `READ` `doc-42` but cannot `WRITE` the same document.
- Alice can `WRITE` `doc-43`, showing permissions on one document **do not bleed into** another.
- Bob can read `doc-42`, while `doc-43` has no grant and is therefore denied.
- `granted=false` is an **explicit** deny ACE; having no ACE is a **missing grant**. Both may return `false` in this simple model, but they can behave differently when inheritance or multiple SID types apply.

This standalone example intentionally omits Spring Security, databases, groups, parent ACLs, tenants, and transactions. In real implementations, you must add those parts and design clear conflict/precedence rules; do not use this demo loop directly in place of the framework's ACL engine.

## 7. Where Does Spring Security Support ACL?

Spring Security provides an **optional ACL module** (`org.springframework.security:spring-security-acl`) to store/read per-object permissions and integrate evaluation into method security. This module **is not enabled automatically** just because an application uses Spring Security or `@PreAuthorize`.

In a Gradle project using Spring Boot dependency management, you can declare:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-acl'
}
```

You need to configure a `DataSource`, SQL schema, ACL service/lookup/cache/authorization strategy beans, and authentication/method security. Spring Security 6.5 documentation provides illustrative configurations for `JdbcMutableAclService`, `BasicLookupStrategy`, and `AclPermissionEvaluator`. Do not assume the dependency creates tables, generates ACEs for every entity, or grants default owner permissions.

### Key Components

| Spring ACL Component | Role |
| --- | --- |
| `Acl` | Represents an object's ACE set, owner, and inheritance info |
| `AccessControlEntry` | An ACE containing SID, permission, grant/deny, and audit info |
| `Sid` | Security identity: principal or authority |
| `PrincipalSid` | SID of a user/principal |
| `GrantedAuthoritySid` | SID corresponding to an authority/permission group |
| `ObjectIdentity` / `ObjectIdentityImpl` | Identifies an object by type + ID |
| `Permission` / `BasePermission` | Permissions represented as bit masks |
| `AclService` | Reads ACLs for one or more objects |
| `MutableAclService` | Creates, updates, and deletes ACLs |
| `JdbcAclService` / `JdbcMutableAclService` | JDBC-based ACL implementation |
| `LookupStrategy` / `BasicLookupStrategy` | Loads ACLs, supporting batch reads and parent ACLs |
| `AclPermissionEvaluator` | Connects ACL decisions to `hasPermission(...)` expressions |
| `PermissionGrantingStrategy` | Strategy deciding grant/deny when evaluating ACEs |
| `AclCache` | ACL cache; must stay consistent when ACLs change |

`ObjectIdentity` is commonly created with `new ObjectIdentityImpl(Document.class, 42L)`. Two records with the same numeric ID but different classes are distinguished. If a project uses UUIDs or composite keys, verify the ID type and configure compatible JDBC queries rather than assuming the `Long` example works verbatim.

### Five Standard Permissions in BasePermission

| Permission | Bit | Mask Value |
| --- | ---: | ---: |
| `READ` | 0 | 1 |
| `WRITE` | 1 | 2 |
| `CREATE` | 2 | 4 |
| `DELETE` | 3 | 8 |
| `ADMINISTRATION` | 4 | 16 |

Bit masks allow representing permissions as bits of an integer. **This does not mean one bit corresponds to one document**; bits represent *permission types*, while object instances are stored as distinct object identities/ACEs. Custom permissions can be created, but permission codes, expression mappings, and stored data must stay aligned.

Do not assume `WRITE` automatically implies `READ` just from the permission names. If the policy requires that relationship, define and test it explicitly.

## 8. The Four Typical JDBC ACL Tables

The JDBC module uses four relational tables, with actual column types defined by database-appropriate migration scripts:

```text
ACL_SID
  id
  principal                   # principal or authority
  sid                         # subject name/identifier

ACL_CLASS
  id
  class                       # domain object class name

ACL_OBJECT_IDENTITY
  id
  object_id_class             # FK -> ACL_CLASS
  object_id_identity          # ID of each domain object
  parent_object               # FK -> ACL_OBJECT_IDENTITY (if present)
  owner_sid                   # FK -> ACL_SID
  entries_inheriting          # parent ACL inheritance flag

ACL_ENTRY
  id
  acl_object_identity         # FK -> ACL_OBJECT_IDENTITY
  ace_order                   # ACE order/position
  sid                         # FK -> ACL_SID
  mask                        # permission bit mask
  granting                    # grant or deny
  audit_success / audit_failure
```

Flow for evaluating `READ` on `Document:42`:

1. Map `Document` to `ACL_CLASS`, and ID `42` to `ACL_OBJECT_IDENTITY`.
2. Determine the SIDs corresponding to the actor's principal and current authorities.
3. Load `ACL_ENTRY` rows for the object, and parent ACLs when linked/inheriting.
4. Apply `PermissionGrantingStrategy` over the requested permissions and SID list.
5. Combine the ACL result with tenant boundaries and relevant business policies.

`ACL_OBJECT_IDENTITY` essentially describes a managed object, while `ACL_ENTRY` can hold many rows for that same object. When an object is deleted, the application must have a process to clean up the corresponding ACLs. Spring Security does not automatically synchronize JPA entity create/update/delete lifecycles with ACL tables.

**Data cost:** 1 million documents can mean 1 million object identities and many millions of ACEs. Index object identities, SIDs, and lookup keys; design caching, batch lookups, permission revocation, and data cleanup strategies before the system scales.

## 9. Integrating with Spring Method Security

**Partial** configuration example for Spring Security 6.x showing how to wire `hasPermission` to the ACL module. This is an integration snippet, not a standalone Java `main` program: the application must provide the `AclService` bean, schema, and JDBC ACL infrastructure beans mentioned earlier.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class AclMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    PermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }
}
```

Enforcement point on a service:

```java
// Illustrative snippet; Document and DocumentRepository are defined by the application.
@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasPermission(#documentId, 'com.example.domain.Document', 'READ')"
    )
    public Document read(Long documentId) {
        return repository.findById(documentId)
            .orElseThrow(() -> new DocumentNotFoundException(documentId));
    }
}
```

Conditions for this integration snippet to be meaningful:

- `@EnableMethodSecurity` must be enabled and the method must be called through the proper interception/proxy mechanism. Calling a `@PreAuthorize`-annotated method on the same bean (`this.read(...)`) usually bypasses the proxy.
- The string `com.example.domain.Document` is illustrative only: it must match the object identity class actually stored in the ACL, and the ID must be compatible with the persistence model.
- `hasPermission(id, type, permission)` invokes `PermissionEvaluator` to evaluate by object ID and type; the `hasPermission(domainObject, permission)` form applies when the object is already loaded.
- This is **object-level permission**. Tenant checks, workflow state, temporary grants, or other business conditions still need independent handling in the proper transaction/call point.
- Users without `READ` permission should not receive data before permission is verified. Depending on architecture, you can load the record within tenant scope and invoke the policy in the same transaction instead of an ACL query expression before the service.
- If `PermissionEvaluator` is not configured, method security may fall back to a deny-all evaluator; do not assume every `false` comes from accurate ACL data.
- Avoid making `@PostAuthorize` or `@PostFilter` the sole protection for large datasets: by then data may already have been loaded or side effects may have run before evaluation.

For operations that do not go through HTTP (schedulers, message consumers, jobs, commands), design authorization checks inside the use case. URL guards only govern requests passing through the filter chain and do not automatically protect all Java calls.

## 10. Creating, Updating, and Revoking ACEs

There are two layers of responsibility:

- **Who is allowed to modify an ACL?** Usually the owner/authorized administrator, but the application must verify this through a dedicated policy. Never let arbitrary users call a service that grants permissions to themselves.
- **How is ACL data modified?** `MutableAclService` provides `createAcl`, `updateAcl`, and `deleteAcl`; `MutableAcl` allows adding/removing ACEs and adjusting owner/inheritance settings appropriately.

**Illustrative snippet** for initially creating the ACL of document ID 42, run in a service after verifying the caller has share permission and the document exists in the right tenant:

```java
// Variables mutableAclService and Document are application dependencies/domain types.
// Illustrates creating a NEW ACL; createAcl fails if the ACL already exists.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 42L);
MutableAcl acl = mutableAclService.createAcl(oid);

Sid bob = new PrincipalSid("bob");
acl.insertAce(0, BasePermission.READ, bob, true);
mutableAclService.updateAcl(acl);
```

In real code, import types from `org.springframework.security.acls.model` and `org.springframework.security.acls.domain`, manage transactions, and handle exceptions when two requests grant permissions concurrently. Do not call `createAcl` on every share; if an ACL already exists, use `readAclById`, modify `MutableAcl`, and call `updateAcl` according to business rules. `getEntries()` is for administering ACEs; for permission decisions, use `Acl.isGranted(...)` or `PermissionEvaluator` rather than iterating the ACE list manually and misinterpreting ordering.

**Revoking permission is not just changing the UI:**

1. Verify the revoker has administrative rights over that specific resource/ACL.
2. Locate the exact ACE by object identity, SID, and permission.
3. Delete or update the ACE via the `MutableAcl` API; persist with `MutableAclService`.
4. Ensure the ACL cache is refreshed or invalidated; determine propagation delay across multiple nodes.
5. Record an audit event capturing actor, target object, old/new permission, and reason per data security rules.
6. Test that the revoked user can no longer access via API, export, direct file download, or related jobs.

When deleting an object, consider `MutableAclService.deleteAcl(objectIdentity, deleteChildren)`; depending on parent/child ACL design, deleting a parent may be blocked while children exist or cascade-delete the subtree. Never pass `deleteChildren=true` out of habit without evaluating the impact.

## 11. Inherited Permissions: Fewer ACEs, Easy Accidental Exposure

Suppose Project A has an ACL granting `READ` to group `TEAM_A`. Many documents in Project A inherit the parent ACL, avoiding duplicate ACEs per document. A private document needs a mechanism to restrict or break inheritance.

```text
Project A (parent ACL)
  TEAM_A -> READ
    |
    +-- Document 42 (entriesInheriting = true)
    |
    +-- Document 43 (entriesInheriting = true)
    |
    +-- Document 44 (entriesInheriting = false)
            Alice -> READ
```

Separate two questions:

- **Is inheritance enabled?** Controlled by `parent ACL` and `entriesInheriting`.
- **How do local ACEs and parent ACEs interact?** Determined by permission, SID, and the active evaluation strategy.

Do not assume a local `DENY` ACE always overrides every parent/user/group ACE across all strategies. In Spring Security ACL's default implementation, matching ACEs and falling back to the parent follow a specific order.

Scenarios that must be tested: adding a user to a team after document creation; removing a user from a team; moving a document to another project; disabling inheritance on a sensitive document; updating a parent ACL while many children are cached. Moving a resource across tenants is especially sensitive: parent relationships, effective permissions, and tenant boundaries must all update consistently in one controlled workflow.

## 12. ACL vs. RBAC and ABAC: Choose by Problem

| Aspect | RBAC | ACL | ABAC / Attribute-Based Policy |
| --- | --- | --- | --- |
| Typical question | Does the user have the EDITOR role? | Does Bob have WRITE on Document:42? | Is actor in tenant A, document DRAFT, and within office hours? |
| Focus | Role → capability | Object → recipient → permission | Conditions from actor/resource/context attributes |
| Permission changes | Change roles or role-permissions | Add/remove ACEs per object | Change policies and attribute values |
| Strengths | Simple management for general capabilities | Fine-grained per-object sharing | Flexible with dynamic conditions |
| Costs/risks | Role explosion if tied to objects | ACE explosion, caching, inheritance complexity | Complex policies, facts, and decision explainability |

A common combined design:

```text
ALLOW EDIT Document:42 when:
    authenticated
AND belongs to tenant containing Document:42
AND has functional permission document:edit
AND ACL(Document:42) grants actor WRITE
AND Document:42 is DRAFT
```

Here ACL decides **object-level permission**, RBAC/authority decides **functional permission**, and domain policy decides **state-dependent conditions**. Never replace all business truth with a `WRITE` flag if the product requires approval rules, payment limits, separation of duties, or state-transition constraints.

**When the ACL module is unnecessary:** if every document is only visible to its owner, sharing needs are minimal, and team/tenant access is easily expressed via foreign keys and scoped queries, a policy service + repository query can be simpler. Choose Spring Security ACL when the system genuinely needs many per-object ACEs, sharing, revocation, inheritance, and permission-list management.

## 13. Tenant Boundaries and Trusted Data

An ACL returning `ALLOW` for Bob on `Document:42` is insufficient if Bob has been removed from the organization that owns the document.

Constraints to enforce independently:

- Identity in `Authentication` must be verified; never accept client-sent `userId` or `role` in the body as the principal.
- If the API accepts `tenantId` in a URL/header, verify the user has access to that tenant and the document belongs to it. Never treat a client-supplied tenant name as proof.
- For IDs unique only within a tenant, build non-colliding namespaced object identities; if using global IDs, still restrict tenant scope in queries and policies.
- ACEs tied to departed users need deactivation/removal; group ACEs must update when membership changes.
- Stale tokens, ACL caches, and decision caches need explicit expiration/invalidation rules. Revoking in the DB while stale cache still allows is a real-world bug.
- Object-storage file download paths, export links, data copies, and search indexes must enforce permissions consistently, not just metadata routes.
- Never allow users to create `ADMINISTRATION` ACEs to grant permissions to others when application policy does not allow it.

**Preventing IDOR/BOLA:** an attacker can change `/documents/42` to `/documents/43`. If the endpoint only checks `authenticated()` or `ROLE_USER`, the attacker can access someone else's data. ACLs must be looked up by the **exact real resource ID**, combined with tenant scope; checking permission on "some document" is not enough.

## 14. Lists, Pagination, and Performance

A `GET /documents` endpoint may need to return 100 documents the user can view. A naive approach loads 100,000 records, runs `hasPermission` on each object, and drops denied records. This introduces serious risks:

- Sensitive data is loaded too broadly into application memory.
- Separate ACL queries cause N+1 queries and timeouts.
- Applying `LIMIT/OFFSET` before permission filtering produces wrong counts and pagination.
- Using `@PostFilter` on large sets can consume excessive CPU/memory and leak total counts or metadata via counts or debug logs.

Solutions:

1. Build database queries filtered by tenant and visibility/share conditions with proper indexes.
2. With Spring Security ACL, consider `AclService.readAclsById(...)` and `BasicLookupStrategy` to batch-load ACLs instead of querying one ID at a time.
3. If list queries require complex ACE predicates, design a database-level view-permission projection/index instead of calling the evaluator per record.
4. Restrict the result set **before** outputting content; clearly define required permissions for list, detail, download, export, and search.
5. Cache ACLs with proper keys (object identity, SID, version/tenant where relevant), avoid unbounded `ALLOW` caching, and clear/refresh after grant, revoke, move, and delete.
6. Measure latency as ACE counts, group counts, and inheritance depth grow, and run realistic load tests on large datasets.

**Do not store permissions for millions of objects inside `GrantedAuthority` on an `Authentication`.** Keeping general permissions in the identity and looking up ACLs by object scales better; for very large systems, evaluate trade-offs between direct ACLs and precomputed permission indexes.

## 15. Negative Permissions, Errors, and Auditing

A secure policy must specify what happens when there is no grant:

- **Unauthenticated/invalid credentials:** reject at authentication; REST APIs typically return HTTP `401` per contract.
- **Authenticated without an ACL grant:** deny the operation; commonly returns HTTP `403`.
- **Nonexistent or unviewable resource:** may return `404` to avoid disclosing existence per data policy; apply consistently.
- **ACL service/DB/cache error:** never fall back to allow; distinguish system errors from "no grant" in logging/monitoring.
- **Permitted operation in invalid business state:** return the appropriate domain error code (e.g., conflict) if specified by the contract, rather than conflating every invalid state with a missing ACL.

**Two-way auditing:** auditing permission changes (who granted/revoked whom, when, which resource) differs from auditing permission usage (who attempted read/edit/delete, allow or deny). The ACL module has audit attributes on ACEs; the application still needs sufficient business auditing while minimizing sensitive data in logs and ensuring critical events are traceable.

A permission-granting API should enforce:
- The actor has valid `SHARE`/`ADMINISTER` permission on the exact resource.
- The recipient exists and belongs to the allowed sharing scope.
- The granted permission is in the resource type's whitelist and does not exceed delegated authority.
- Transactions prevent succeeding on document updates while failing ACL writes (or vice versa) when both must remain consistent.
- Writes use versioning or concurrency detection to catch simultaneous ACL edits and prevent unintended last-write-wins.
- Caches and secondary systems (search/export/download) update within the defined latency budget.

## 16. ACL Testing Matrix

For `Document:42`, suppose Bob has `READ` without `WRITE`, and Alice has `READ/WRITE`. Test at least:

| Scenario | Expected |
| --- | --- |
| Alice reads Document:42 | ALLOW |
| Alice edits Document:42 | ALLOW if state/tenant rules also hold |
| Bob reads Document:42 | ALLOW |
| Bob edits Document:42 | DENY |
| Carol has no ACE to read Document:42 | DENY per default policy |
| Bob switches ID to Document:43 with no ACE | DENY |
| Bob's READ ACE is deleted; repeat API request | DENY, even when cache exists |
| Bob is removed from a group granted READ | DENY after membership/identity refresh per contract |
| Document:42 moves to another tenant | No cross-tenant permission leak |
| ACL data cannot be retrieved | Never ALLOW on error |
| Conflicting parent ACL, local ACE, and group ACE | Matches chosen `PermissionGrantingStrategy` |
| Same Document with READ/WRITE/DELETE requests | Each permission decided independently |

Test layers:

1. **Policy unit tests:** take actor/resource/permission/context; test allow, deny, missing ACE, explicit deny, group permissions, inheritance, conflicts, and tenant isolation.
2. **ACL database integration tests:** schema/migrations, `createAcl`/`readAclById`/`updateAcl`/`deleteAcl`, principal/authority SIDs, bit masks, ACE ordering, parent/inheritance, cache refresh.
3. **Method security tests:** `@EnableMethodSecurity` and `hasPermission` actually execute via proxy; verify denials are not bypassed via self-invocation or another service call path.
4. **HTTP/end-to-end tests:** valid/anonymous users, tampered object IDs, list/detail/export/download, pagination, and post-revoke behavior; verify responses, side effects, and returned data.
5. **Concurrency/performance tests:** concurrent grants and revocations, resource edits during checks, large numbers of ACEs/groups/parent ACLs, and large datasets.

**Testing trap:** asserting only HTTP 403 does not prove the ACL works. A `PATCH` endpoint can return 403 due to CSRF or missing authentication. Tests must supply valid credentials/CSRF per configuration, then vary **only the ACL or object ID** to confirm the reason for denial, while verifying data was not mutated.

## 17. Common Pitfalls and Fixes

| Mistake | Why Dangerous | Fix |
| --- | --- | --- |
| Checking only `hasRole("USER")` | Other users with the same role can read unauthorized records | Check ACL by real object ID |
| Sharing by document name instead of stable ID | Duplicate names or renames corrupt permissions | Use unique identity by type + ID + tenant |
| Accepting `ownerId` or `recipient` from client without verification | Privilege escalation, unauthorized sharing | Authenticate actor and enforce share policy |
| Treating `owner` as unconditionally all-powerful | Bypasses approval workflows or tenant boundaries | Define owner rights explicitly and check separately |
| Assuming "deny always wins" without checking strategy | Conflicting permissions yield unexpected results | Test ACE order, groups, parent, and SID order |
| Deleting grants from tables while leaving stale cache | Revoked permissions remain usable | Invalidate caches and test real revocation |
| Protecting only controllers | Jobs, consumers, or internal methods bypass checks | Place guards at appropriate use cases/methods |
| Checking one object then exporting everything | Bulk data leak | Filter permissions consistently per operation/list/export |
| Creating ACLs on document creation without cleanup on deletion | Orphaned ACLs and stale permission data | Manage ACL lifecycle alongside domain objects |
| Writing N+1 queries per document | Severe latency spikes on large datasets | Batch ACL lookups / permission indexing |
| Confusing `ADMINISTRATION` bit with global super-admin | Exceeds business scope | Separate ACL administration from domain/tenant bypass |
| Mixing role permissions and per-object permissions in one oversized expression | Hard to audit, maintain, and easy to drop conditions | Use clearly named policies tested independently |

## 18. Selecting the Model and Shipping to Production

Before enabling Spring Security ACL, be ready to answer:

1. Do we genuinely need different shared permissions **per instance**, or only owner/tenant/role?
2. Which principals/groups can receive ACEs, and which stable IDs will be used?
3. What are the permissions, do any imply others, and which permission allows **modifying the ACL**?
4. When grants/denies conflict across user–group–parent, which algorithm decides?
5. Under what conditions can tenant, state, or business rules veto the ACL?
6. What is the ACL lifecycle when objects are created, transferred, moved, or deleted?
7. How quickly must permission revocation take effect; how are caches/tokens/replicas refreshed?
8. How do list, search, export, and download queries ensure only authorized data is returned?
9. Who can explain denial decisions to users and auditors?
10. Are there automated tests for 401/403/404, IDOR, group membership, inheritance, revocation, races, and high ACE counts?

**Self-check exercise:**

- `Document:42` shares READ with Bob, while `Document:43` has no ACE. Bob changes the ID in the URL from 42 to 43; what should the system do? → **Deny** per 43's ACL and the designed non-disclosure rules.
- Carol is a member of `TEAM_A`, which has READ on a parent ACL. When Carol leaves the team while an old JWT still retains the `TEAM_A` authority, what can happen? → Access may persist until the identity/token expires or a revocation/membership re-check takes effect. The design must specify the revocation latency.
- A `WRITE` ACE is granted, but the document is in `APPROVED` state, which forbids editing. Should it be allowed? → **No**, because ACL permissions do not override business invariants/policies.
- A document has no ACE for Alice, yet Alice is the record owner. Can she READ it? → **Cannot conclude** without knowing the owner rule. The system must define the owner case explicitly.

**Conclusion:** An ACL expresses "**which subject has which permission on which specific object**". Spring Security provides an ACL library to store/retrieve ACEs and bind them to `hasPermission`, while the application still owns tenant, state, and permission-lifecycle rules. A sound ACL design requires durable identifiers, safe default deny, clear grant/revoke governance, checks across all access paths, and tests for conflicts, revocation, and cross-resource access.

## References

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [API: AclPermissionEvaluator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html)
- [API: Acl / MutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html)
- [API: DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html)
