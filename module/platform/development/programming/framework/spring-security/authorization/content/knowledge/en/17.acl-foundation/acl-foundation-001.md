# When You Need an ACL Instead of Roles or a Simple Ownership Flag

## 1. The Practical Problem: Permission on an **Action** Differs from Permission on an **Individual Object**

A Spring Security application typically starts with roles such as `USER`, `EDITOR`, `ADMIN` or authorities such as `document:read`. Later, an `ownerId` field is added to the object so the creator can edit their own data. These two mechanisms solve many business requirements, but they start falling short when **access permissions vary per record and can be shared or revoked independently**.

For example: An creates document 42. An wants to let Binh view the document without editing it; let Chi edit it for one week; allow an audit group to read it; while document 57 remains visible only to An. With only the `EDITOR` role or the condition `document.ownerId == currentUserId`, the system struggles to express those permissions without creating a proliferation of special-purpose roles or cramming lists of shared users into scattered logic.

**ACL – Access Control List** – is a way of storing access rules attached to **each specific resource**. An ACL typically contains **ACEs – Access Control Entries**, where each entry specifies which subject is granted or denied which permission on which object.

The goal of this article is not "use ACL everywhere." The goal is to know **when RBAC or an owner check is enough, when a simple sharing table suffices, and when the complexity of an ACL is genuinely worth it**.

## 2. Four Concepts That Should Not Be Conflated

| Mechanism | Primary Question | Primary Data | Example | Where It Excels |
|---|---|---|---|---|
| **RBAC** (Role-Based Access Control) | Is the user allowed to perform this **type of action**? | Role → authority | `ROLE_EDITOR` has permission to create documents | Permissions relatively stable by job function |
| **Owner check** | Is the user the permitted subject for **this record**? | `resource.owner_id` | Only the owner edits a draft | Simple single-owner rules |
| **ACL** | **Which subject** has **what permission** on **which object**? | Object identity + subject + permission + grant/deny | Binh READs document 42; Chi WRITEs document 42 | Per-object exceptions, flexible sharing/revocation |
| **ABAC / attribute-based policy** | Which conditions of the actor, object, and environment allow the action? | Attributes, relationships, rules | Edit only before the deadline, from the internal network, within the tenant | Dynamic and context-dependent rules |

ACL and RBAC are not mutually exclusive. A common setup is:

1. **RBAC** determines whether the actor is allowed to use the `document:read` or `document:share` capability.
2. **Tenant boundary** restricts which organization the actor can operate within.
3. **Owner/ACL** decides which *exact document* the actor has permissions on.
4. **Business policy** checks document status, validity period, approval lock, or domain-specific conditions.

Conceptual formula, not a mandatory expression for every system:

~~~text
ALLOW = authenticated
    AND action_authority
    AND tenant_scope_matches
    AND object_permission
    AND business_constraints
~~~

A general authority **does not replace** object-level permission. Conversely, an ACE allowing a document to be read **does not necessarily** grant permission to call every API or bypass tenant rules.

## 3. When Are Roles Enough?

Keep RBAC if permissions are primarily tied to a capability or stable scope, **independent of individual records**.

Examples:
- `SUPPORT_AGENT` can use the support screen; `FINANCE_ADMIN` can configure fees.
- A tenant administrator can view the tenant's admin dashboard, according to confirmed organizational rules.
- Only `REPORT_VIEWER` has permission to open the aggregate statistics page; there is no mechanism for individuals to selectively grant permissions on individual reports.
- Permissions are mainly assigned by administrators based on job role and do not change every time an object is created.

Spring Security example:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public ReportSummary getSummary() {
    return reportService.computeSummary();
}
~~~

This is a **Spring integration snippet**: it requires enabling method security and having the appropriate service and beans; it is not a standalone Java file. The rule is suitable if **a global summary within the actor's proper scope** is permitted by that authority.

If `getSummary()` returns tenant-specific data, you still need to filter/restrict by a trusted tenant. A role can act as a **functional gate**, not necessarily complete protection for the data.

**Signs you do not need an ACL:** few permissions, no per-document exceptions, no Share button, no per-object delegation, and permission questions can be answered using role + tenant scope.

## 4. When Is a Simple Owner Flag Enough?

Keep ownership checks when the specification is genuinely "only the author/owner can read or edit," occasionally adding an explicit admin permission. The model usually only needs:

~~~text
DOCUMENT(id, tenant_id, owner_user_id, title, ...)
~~~

Example service reading a single record with an owner check:

~~~java
@Transactional(readOnly = true)
public DocumentView read(long id) {
    Actor actor = actorResolver.requireVerifiedActor();
    Document doc = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

    if (!actor.userId().equals(doc.getOwnerUserId())) {
        throw new AccessDeniedException("Document access denied");
    }
    return mapper.toView(doc);
}
~~~

This is **illustrative integration code**: the `Actor`, `Document`, repository, mapper, and exception types belong to the project. The tenant scope is taken from the verified identity; never trust a client-supplied `tenantId`. The owner-only policy is an assumption of this example, **not** a default rule that every owner has all permissions.

Owner checks are well suited for:
- Unshared personal profiles.
- Private drafts that only the creator can edit.
- Certain internal resources where the creator is the only one allowed to make changes.
- Self-service APIs that have no user-to-user delegation requirement.

Advantages: simple schema, easy-to-optimize queries/filters, easy to understand in tests, easy to audit who owns an object. No ACL is needed if requirements do not call for permission exceptions.

**An `isOwner` flag sent by the client is not proof of ownership.** Ownership must be determined from trusted server data; only compare the authenticated actor ID against the owner ID stored in the database.

## 5. Signs That an ACL Starts Adding Value

An ACL is usually worth considering when **several** of the following signs appear together:

1. **Per-document sharing:** An lets Binh view document 42, but not document 43.
2. **Multiple permission levels on the same record:** Binh READs, Chi WRITEs, Dung only COMMENTs, An ADMINISTERs.
3. **Multiple types of granted subjects:** users, groups, sub-organizations, or authorities need separate ACEs.
4. **Independent delegation and revocation:** the document owner grants permissions to others and later revokes them without changing system-wide roles.
5. **Multiple permission sources:** owner, invited users, project groups, reviewers, collaborators; a single place is needed to explain who can do what.
6. **Inherited permissions:** documents inside a folder/project can inherit policies from the parent, with the ability to override or block inheritance by design.
7. **Explainability/audit requirements:** must answer "who granted read permission on this document, when, what permission, and has it been revoked?".
8. **Owner-only rules cause code to grow many exception branches:** `owner OR sharedUser OR teamMember OR reviewer OR delegatedAdmin ...` appears across multiple services/queries.

A classic scenario is a collaborative document management application. The `MEMBER` role only indicates that the user is an application member. An ACL attached to each document/folder determines where that member can READ, WRITE, or MANAGE.

**A single exception does not automatically require deploying an ACL framework.** If you only share one data type with a single read permission, a `document_share(document_id, user_id)` table and relational check queries may be easier to operate. An ACL pays off when the number of permission dimensions, subject types, inheritance, and administrative needs increase noticeably.

## 6. Decision Table: Choose the Simplest Level That Meets Requirements

| Scenario | Usually Suitable Choice | Why? |
|---|---|---|
| Only users with role `ADMIN` can change global configuration | RBAC | No per-record permissions |
| Each user edits only their own profile | Owner check | Clear 1 user ↔ 1 resource relationship |
| Each document has an owner, no sharing | Owner + tenant scope | Few edge cases |
| Read-only sharing for a single user, few actions | Simple share relationship table | An ACL framework may be overkill |
| Document has READ/WRITE/COMMENT/SHARE for many people | ACL | Many permissions × subjects × objects |
| Project/folder inherits permissions down to many resources | ACL with inheritance or suitable relational policy | Parent-child relationships and exceptions matter |
| Resources belong to hundreds of dynamic groups with nested relationships | ACL/relationship-based authorization, depending on design | Needs subject/group modeling and queryability |
| "View only during business hours from compliant devices" | ABAC or policy engine | Depends on environmental attributes, not just lists |
| Users in tenant A never view tenant B data | Mandatory tenant scoping, optionally combined with ACL | ACL does not replace tenant boundaries |
| Millions of records, permissions only by owner and tenant | Scoped query/owner; avoid unnecessary ACL | Lean model, efficient queries |
| Many objects have public share links with expiry | Share token/capability policy with its own lifecycle; can be combined with ACL | Expiring URL/token is not inherently a basic ACE |
| System needs policies based on complex org relationships and cross-resource inference | RBAC + ACL or ReBAC/policy engine | A flat ACL table can struggle to express relationships |

The table above is a **decision guide**, not a rigid rule. Evaluate correctness, simplicity, scale, and audit requirements of the real use case.

## 7. Decision Tree for Choosing Whether to Use an ACL

~~~text
Do permissions depend on individual object IDs?
 ├─ No --> RBAC + organization/tenant scope is usually enough
 └─ Yes
     |
     +-- Is there strictly one owner, with no sharing?
     |     ├─ Yes --> owner check + query scope
     |     └─ No
     |
     +-- Just one simple "can view" relationship?
     |     ├─ Yes --> consider a simple share table
     |     └─ No
     |
     +-- Multiple subjects, multiple permissions, grant/revoke,
          administration/audit, inheritance?
             ├─ Yes --> ACL is worth considering
             └─ No --> keep a simple domain policy
~~~

Before investing in an ACL, also answer:
- "Who has permission to **grant/revoke** a permission? Can the recipient re-delegate it?"
- "Are group permissions evaluated at grant time or at access time? What happens upon leaving the group?"
- "When a parent folder is deleted or moved between tenants, how do child ACLs change?"
- "If an ACL is not found or the ACL database fails, what does the system do?"
- "Do we need to filter thousands of documents in list/pagination without N+1 queries?"
- "Are latency, cache invalidation, and audit overhead acceptable?"

Without reliable answers to these questions, adopting an ACL prematurely can increase the security bug surface rather than reduce it.

## 8. Evolution Example from Owner-Only to ACL

### Phase A: Exclusive Creator

~~~text
document #42: owner=an, tenant=north
an READ, WRITE
binh DENY
chi DENY
~~~

A single `owner_user_id` column and a scoped query are enough.

### Phase B: Sharing with One Viewer

~~~text
document #42: owner=an
share: (document=42, recipient=binh, permission=READ)
~~~

If only READ is needed, a `document_share` table with a unique key and fixed conditional logic works. This is not yet necessarily the point where switching to Spring Security ACL is mandatory.

### Phase C: Multiple Permissions, Multiple People, Revocation

~~~text
document #42:
  owner an       READ + WRITE + MANAGE
  binh           READ
  chi            READ + WRITE
  team-review    READ + COMMENT

document #43:
  owner an       READ + WRITE + MANAGE
  binh           DENY
~~~

Binh's `MEMBER` role cannot express the difference between document 42 and 43. An owner check also cannot describe Chi having WRITE without being the owner. At this stage, an ACL or equivalent permission relation model becomes worthwhile.

### Phase D: Folders and Exceptions

~~~text
folder /projects/north: team-review READ
  ├── #42: inherits team-review READ
  └── #43: does not inherit because it contains sensitive data
~~~

At this point you must clearly define inheritance, grant/deny precedence, which objects can override, and how to re-evaluate when folders or memberships change. Never implicitly assume "deny always wins" or "last grant wins": the outcome depends on the engine and policy the application chooses.

## 9. What Structure Does an ACL Have?

General model:

~~~text
Subject (user/group/authority)
          |
          | ACE: permission + grant/deny
          v
Object Identity (type, object ID, tenant scope)
          |
          +-- ACL entries
          +-- optional parent ACL / inheritance
~~~

Key components:

- **Object identity:** identifies a record, typically consisting of resource type and ID. With multi-tenancy, ensure identities, queries, and policies always include a trusted tenant scope.
- **SID – Security Identity:** a user or authority/group granted permission. In Spring ACL there are `PrincipalSid` and `GrantedAuthoritySid`.
- **Permission:** rights such as READ, WRITE, CREATE, DELETE, ADMINISTRATION. Custom permissions can be defined if business requires; their meaning and implications must be specified.
- **ACE – Access Control Entry:** an entry recording that a SID is granted or denied a permission on an object.
- **ACL:** the set of ACEs attached to an object; it may have a parent and rules for inheritance.
- **Grant/revoke:** operations to add, modify, or remove ACEs, along with auditing and conditions on who is allowed to share.

Policies **should default to denying access** when no ACE/owner/policy proves permission. However, exact handling of "no ACL," "deny ACE," and "abstain" differs across engines; you must choose a clear fail-closed behavior and test it.

**Do not confuse ACL owner with domain owner:** in Spring ACL, `Acl.getOwner()` represents the SID that owns the ACL in the framework sense. It does not automatically prove that the person is the business `document.ownerUserId` or inherently has full permission to edit content. Owner policies and administrative rights must be explicitly defined and tested.

## 10. What Does Spring Security ACL Provide?

Spring Security has a dedicated **`spring-security-acl`** module for domain-object authorization. The official documentation describes this mechanism for cases that must evaluate "who, where, and which object," rather than merely blocking a URL or method by role.

Four core tables in the default JDBC implementation:

| Table | Role |
|---|---|
| `ACL_SID` | Permission subject: principal or granted authority |
| `ACL_CLASS` | Type of domain object to protect |
| `ACL_OBJECT_IDENTITY` | Specific object, ACL owner, parent, and inheritance flag |
| `ACL_ENTRY` | ACE for an object and SID, permission bit mask, grant/deny, audit flags |

Related interfaces/classes:

- `Acl`, `AccessControlEntry`, `Permission`, `Sid`, `ObjectIdentity`.
- `AclService` for reading ACLs; `MutableAclService` for updating them.
- `JdbcMutableAclService` and `BasicLookupStrategy` to support efficient JDBC storage/lookup.
- `AclPermissionEvaluator` to integrate with `hasPermission(...)` expressions in method security.
- `BasePermission` provides common bitmask permissions. For example, READ is bit 0, WRITE is bit 1, CREATE is bit 2, DELETE is bit 3, and ADMINISTRATION is bit 4.

**A bit mask is not the number of objects.** The bits represent **permission types**, not individual documents. A system can still have millions of object identities and ACEs, even though permissions are represented as bits in an integer.

The ACL module does not automatically create/delete ACEs whenever the application calls `save()` or `delete()` on an entity. The application must actively manage the ACL lifecycle, keeping it synchronized with resource creation/deletion, grant/revoke, ownership transfer, and project moves; never assume `@EnableMethodSecurity` does this automatically.

Spring Security 7.x still documents ACLs, but when upgrading versions you must follow the migration guide. For legacy systems using `AclEntryVoter`/after-invocation providers, the migration 7 documentation recommends shifting focus to `AclPermissionEvaluator` rather than keeping plugins based on legacy voter APIs.

Official sources:
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security 6.5 → 7 – ACL migration](https://docs.spring.io/spring-security/reference/6.5/migration-7/acl.html)

## 11. Permission Modeling: Do Not Invent Unverified Relationships

Depending on the application, permissions may be:
- **READ**: read allowed content and metadata.
- **WRITE**: modify content, though not necessarily allowed to share.
- **COMMENT**: add comments, though not necessarily allowed to edit content.
- **SHARE/MANAGE**: invite users, revoke permissions.
- **DELETE**: delete the resource; usually requires strong guards.
- **ADMINISTRATION**: manage ACLs or policies; meaning varies by domain.

If a product calls a permission "Editor," you must **explicitly specify** whether editor includes WRITE+READ or also COMMENT/SHARE/DELETE. Do not assume `WRITE` implicitly includes `DELETE` or `MANAGE`: in an ACL they can be granted separately.

Example business policy table (not a built-in Spring ACL policy):

| Access Level | READ | COMMENT | WRITE | SHARE | DELETE |
|---|---|---|---|---|---|
| Viewer | Yes | No | No | No | No |
| Commenter | Yes | Yes | No | No | No |
| Editor | Yes | Yes | Yes | No | No |
| Manager | Yes | Yes | Yes | Yes | Yes |

This table is one way of mapping **from business levels to permission sets**, not fixed roles created by Spring Security. For high-risk documents, DELETE and SHARE may additionally require secondary approval or fresh MFA.

### Allow and Deny ACEs

Some ACLs allow both *grant* and *deny* entries. You should not hand-roll logic like:

~~~java
// Design flaw if the engine supports deny/inheritance:
return aclEntries.stream().anyMatch(AccessEntry::isGranting);
~~~

That condition ignores permission type, subject, target, ACE order, and deny entries. When using Spring ACL, let `Acl.isGranted(...)` or `AclPermissionEvaluator` handle actual semantics; the Javadoc advises against iterating directly over `getEntries()` to make decisions. If building your own engine, you must have an explicit specification for precedence and inheritance.

## 12. Combining Roles, Owner, Tenant, and ACL: Safe Ordering

A typical policy for a private document:

~~~text
1. Verify authentication and actor.
2. Check that the actor has permission to use the corresponding capability.
3. Verify tenant scope; do not trust tenant from client.
4. Query the object by ID and verified tenant.
5. Determine object permission:
      owner or valid ACE or approved administrative rule.
6. Check business constraints: locked, archived, legal hold, ...
7. Only then read sensitive information / return data / perform write side effects.
~~~

**These conditions must be combined with AND.** If the policy is `tenantMatch AND (isOwner OR hasAce) AND actionAllowed`, do not mistakenly write `tenantMatch OR isOwner OR hasAce`. A user with an ACE on a matching ID in a different tenant must never cross the tenant boundary.

For an admin, you also need to define which scope they administer: `TENANT_ADMIN` is not automatically an admin of all other tenants; a global superuser, if one exists, must be a separately governed, audited, and tested capability.

ACL **does not replace authentication**, capability-level RBAC, tenant data isolation, or business state logic. It is one part of the authorization decision, not the sole layer of defense.

## 13. Spring Method Security: Using PermissionEvaluator

Once `AclService` and `AclPermissionEvaluator` are configured, you can use the `hasPermission(...)` expression to check permissions against an object or object ID/type.

Illustrative example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    @PreAuthorize(
        "isAuthenticated() and hasAuthority('document:read') " +
        "and hasPermission(#documentId, 'com.example.domain.Document', 'READ')"
    )
    @Transactional(readOnly = true)
    public DocumentView readDocument(Long documentId) {
        // The query must also include tenant scope and business conditions.
        return loadScopedDocument(documentId);
    }

    private DocumentView loadScopedDocument(Long documentId) {
        throw new UnsupportedOperationException("Domain implementation");
    }
}
~~~

This is an **integration snippet**, not a standalone runnable example. It illustrates the necessary conditions rather than a complete implementation: `com.example.domain.Document` is an example class name, and the ID/type must match the actual ObjectIdentity; you need to configure the expression handler so `hasPermission` uses the ACL evaluator, a scoped repository, a trusted principal, and proper exception handling. The `loadScopedDocument` stub is purely illustrative and must be replaced with domain logic.

One way to configure the expression handler in Spring Security supporting modern method security:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator permissionEvaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }
}
~~~

This is also **integration code**, requiring Spring Security/Spring Context imports and an `AclService` configured with a datasource. Registration/configuration details vary by version and stack, so check your project's version and documentation. `@EnableMethodSecurity` does not automatically generate ACL tables or services.

Several essential caveats:
- Method security relies on Spring AOP proxies: internal calls like `this.readDocument(...)` can bypass the interceptor depending on the AOP mode; always test through actual Spring beans.
- `hasPermission` checks the **object/ID and permission**, not replacing tenant filtering in repositories.
- For multi-field data, separate permissions may be required for metadata, body content, and attachments; a document ACL does not automatically allow every field.
- For writes, place permission checks **before mutation**. Avoid relying solely on `@PostAuthorize` after data has already been written or events published.

## 14. Listing and Pagination: ACL Has Significant Cost

Checking an ACL for **one** document is relatively straightforward. Harder is "list a page of 20 documents the user can view" from a repository of millions of documents.

Result-breaking anti-pattern:

~~~text
SELECT any 20 documents
--> filter each document by ACL after querying
--> only 3 allowed documents remain
--> return page size 3, wrong total count / hints at sensitive data
~~~

This pattern can lead to:
- **N+1 ACL lookups**: each document triggers an extra query to check permission.
- Underfilled result pages, inaccurate page counts and `totalElements`.
- Loading unauthorized documents into memory/cache/logs before filtering.
- Information leakage via counts, sort order, search facets, exports, or response timing.
- Sharp increases in CPU/DB pressure as ACL entries and group memberships grow.

Better strategies when ACLs reside in the DB can include:
- **Query-first**: push owner/tenant/permission conditions into the query; ensure `countQuery` and sorting stay consistent.
- **Batch ACL reads** by list of object identities/SIDs when not all predicates can be pushed to the DB; fetch additional items to fill the page while recalculating pagination semantics and privacy guarantees.
- **Materialized authorized-view/permission index** or cache with controlled invalidation for large-scale workloads.
- Separate detail and list APIs: list returns scoped metadata; detail still **re-checks authorization** on the object.
- Test with large datasets, changing permissions, group permissions, and multiple tenants.

Spring ACL has `LookupStrategy` for batch/caching optimization, but it **does not automatically generate permission-filtered pagination SQL** for every repository and use case. Avoid assuming that enabling ACLs automatically solves listing and counting.

## 15. Grant, Revoke, Share, and Audit Have Lifecycle Costs

If permissions are managed by an ACL, you need a dedicated management API/flow, not just document CRUD.

Required operations:
- **Grant**: a subject with sharing permission creates the appropriate ACE for recipient, action, and exact resource.
- **Revoke**: delete/update the ACE and ensure access is lost once the change takes effect.
- **List grants**: display who has what permission; do not let users without MANAGE permission read sensitive grant lists.
- **Transfer ownership**: update domain-owner rights and ACL owner if the contract requires it; do not confuse the two concepts.
- **Delete resource**: clean up the object's ACL, ACEs, and corresponding caches per lifecycle, avoiding orphaned ACLs.
- **Remove user/group**: handle ACEs, memberships, SIDs, tokens/sessions, and caches with accurate semantics.
- **Inherit/uninherit**: control impact when a folder/project changes parent or opts out of inheritance.
- **Audit**: who granted/revoked, when, which permission, which object, and what the outcome was.

**Who is allowed to share?** Do not default to letting a user with `WRITE` grant `ADMINISTRATION` to others. Read/write permissions, ACL management permissions, and re-delegation permissions must be defined separately.

Permission management data must guard against races/TOCTOU. For example, a user had SHARE permission at T1 but was revoked before granting at T2. Place checks close to mutations and choose transactions/locking matching consistency requirements. If ACLs live in another service, define how to handle eventual consistency and fail-closed behavior when synchronization lags.

### Expiring Permissions

"Share the document with Chi **for 7 days**" is a very common requirement, but a basic Spring ACL bitmask ACE **does not natively handle full expiration, invitations, and revocation tokens**. You must add an expiry model or dedicated policy, such as a share table with `expires_at` checked at access time; if extending ACL, design appropriate migrations, schema, and logic.

Never issue a permanent grant and merely hide the Share button in the UI after 7 days: the API could still allow access.

## 16. Group Membership and Inheritance: Points to Verify

If permission is granted to "team-review":
- The ACL engine needs to know which teams the actor belongs to **at evaluation time**.
- With Spring ACL, a SID can represent a principal or a granted authority. If using group authorities, authentication or the resolver must reflect trusted, current membership.
- When a user leaves a group, permissions inherited via that group must end per contract. A token carrying stale membership or a stale cache can prolong access.
- If groups can nest, you must specify how relationships expand, cycle detection, and query cost; do not assume the default ACL module automatically resolves arbitrary organizational trees.
- With ACL parent inheritance, distinguish between inheriting **parent permissions** and inheriting **domain owner**; do not conflate them.

For large organizations with multi-level group/folder relationships, a ReBAC model or policy engine may fit better than manually creating ACEs for every object/user. What matters is the **actual authorization problem**, not the framework name.

## 17. Standalone Java 17 Demo: When ACL Makes a Difference

The following program simulates owner + tenant admin role + per-document READ/WRITE ACL on **individual documents**. It is plain Java, with no Spring and no DB connection. It illustrates why Binh's permission on document 42 does not imply permission on every document.

Create file `AclChoiceDemo.java`:

~~~java
import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class AclChoiceDemo {

    enum Action { READ, WRITE }
    enum Role { USER, TENANT_ADMIN }

    record Actor(String userId, String tenantId, Set<Role> roles) { }
    record Document(long id, String tenantId, String ownerId) { }
    record ObjectKey(String tenantId, long id) { }

    static final class Policy {
        private final Map<ObjectKey, Map<String, EnumSet<Action>>> acl =
                new HashMap<>();

        void grant(Document document, String userId, Action action) {
            ObjectKey key = new ObjectKey(document.tenantId(), document.id());
            acl.computeIfAbsent(key, ignored -> new HashMap<>())
                    .computeIfAbsent(
                            userId, ignored -> EnumSet.noneOf(Action.class))
                    .add(action);
        }

        void revoke(Document document, String userId, Action action) {
            Map<String, EnumSet<Action>> entries =
                    acl.get(new ObjectKey(document.tenantId(), document.id()));
            if (entries == null) {
                return;
            }
            EnumSet<Action> rights = entries.get(userId);
            if (rights != null) {
                rights.remove(action);
                if (rights.isEmpty()) {
                    entries.remove(userId);
                }
            }
        }

        boolean allowed(Actor actor, Document document, Action action) {
            if (actor == null || document == null || action == null
                    || actor.userId() == null || actor.userId().isBlank()
                    || actor.tenantId() == null || actor.roles() == null
                    || document.id() <= 0
                    || !actor.tenantId().equals(document.tenantId())) {
                return false;
            }

            // An admin only has permissions within the verified tenant.
            if (actor.roles().contains(Role.TENANT_ADMIN)) {
                return true;
            }

            // This example intentionally grants the owner both READ and WRITE.
            if (actor.userId().equals(document.ownerId())) {
                return true;
            }

            Map<String, EnumSet<Action>> entries =
                    acl.get(new ObjectKey(document.tenantId(), document.id()));
            if (entries == null) {
                return false;
            }
            EnumSet<Action> rights = entries.get(actor.userId());
            return rights != null && rights.contains(action);
        }
    }

    public static void main(String[] args) {
        Document document = new Document(42, "north", "an");
        Actor an = new Actor("an", "north", Set.of(Role.USER));
        Actor binh = new Actor("binh", "north", Set.of(Role.USER));
        Actor chi = new Actor("chi", "north", Set.of(Role.USER));
        Actor southAdmin = new Actor(
                "admin", "south", Set.of(Role.TENANT_ADMIN));

        Policy policy = new Policy();
        policy.grant(document, "binh", Action.READ);

        System.out.println("owner-write="
                + policy.allowed(an, document, Action.WRITE));
        System.out.println("shared-read="
                + policy.allowed(binh, document, Action.READ));
        System.out.println("shared-write="
                + policy.allowed(binh, document, Action.WRITE));
        System.out.println("not-shared-read="
                + policy.allowed(chi, document, Action.READ));
        System.out.println("cross-tenant-admin="
                + policy.allowed(southAdmin, document, Action.WRITE));

        policy.revoke(document, "binh", Action.READ);
        System.out.println("after-revoke-read="
                + policy.allowed(binh, document, Action.READ));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac AclChoiceDemo.java
java AclChoiceDemo
~~~

Stdout:

~~~text
owner-write=true
shared-read=true
shared-write=false
not-shared-read=false
cross-tenant-admin=false
after-revoke-read=false
~~~

Explanation:
1. An is the owner and thus gets WRITE according to the **example's policy**, not because of the USER role.
2. Binh has a READ ACE so Binh can view document 42, but cannot WRITE.
3. Chi also has USER, with no owner status or ACE, so Chi cannot READ.
4. A TENANT_ADMIN of tenant south cannot bypass the north tenant guard.
5. After revocation, Binh immediately loses READ in the demo's map.

**Demo limitations:** actors are instantiated directly in code; in a real application, actor/tenant/roles must come from authenticated sources. An in-memory map lacks persistence, concurrency, auditing, deny ACEs, group membership, inheritance, expiry, or cache revocation. This code only illustrates the **difference in expressive power** of an ACL compared to roles/owners, not a production ACL engine.

## 18. Security Testing When Deciding to Use an ACL

### 18.1. Mandatory Matrix

| Scenario | Expected Outcome |
|---|---|
| Owner gets READ/WRITE per published policy | ALLOW within valid scope |
| Non-owner with no ACE | DENY |
| User with READ ACE requesting WRITE | DENY |
| User with WRITE ACE but no SHARE | Cannot modify ACL |
| Revoked user | DENY immediately after revocation takes effect per contract |
| User with USER role on unshared document | DENY |
| User with TENANT_ADMIN role from another tenant | DENY |
| User in a group with READ ACE | ALLOW if membership is verified |
| User leaves group | DENY unless another independent grant exists |
| Document does not exist in tenant | Do not grant, do not leak data |
| Missing ACL / missing ACE | Do not grant per designed default |
| ACL service timeout | Do not perform operation; report technical error |
| Conflicting deny ACE and grant ACE | Outcome follows tested precedence/inheritance |
| Parent ACL has READ, child disables inheritance | Does not automatically inherit |
| Resource changes tenant/owner | Does not retain stale rights violating policy |
| Listing 1000 objects with a subset permitted | Return only valid objects, accurate count/pagination |
| User guesses ID from another tenant | No reading, writing, logging, or caching of unauthorized data |
| Batch export or background job | Permissions checked on every resource with correct identity |

### 18.2. API and Data Leakage Tests

Do not only assert HTTP 403. Also verify:
- Denied documents are **not updated or deleted**.
- Counts, search suggestions, sort order, thumbnails, file downloads, and attachment endpoints do not leak documents.
- No sensitive metadata appears in error messages or client logs.
- Multiple `SecurityFilterChain`/method security configurations do not bypass the ACL.
- Non-HTTP entry points (messaging, schedulers, direct service calls) still enforce the corresponding resource policy.
- Permission caches are invalidated when revocations, memberships, or parent ACLs change.
- List queries and `countQuery` do not accidentally include unauthorized records.

**Performance testing:** measure SQL queries per page, p95/p99 latency, number of ACEs loaded, cache hit rate, grant/revoke speed, and behavior when the ACL database is unavailable. A correct policy that triggers 200 queries for every 20-document page may not be operationally sustainable.

## 19. Step-by-Step Decision and Implementation Process

**Step 1 — Write a business permission matrix.** List subjects (users/groups/admins), resources (documents/folders/projects), actions, tenant conditions, and owners. Specify who grants/revokes permissions.

**Step 2 — Check if role + owner is enough.** If rules remain simple, keep them that way. Avoid designing an ACL purely for "future extensibility" without real requirements.

**Step 3 — Try a small share table model.** If only a single READ permission is needed, a share table with a unique key and scoped queries can drastically reduce complexity.

**Step 4 — Choose ACL when dimensions grow.** Define rules for READ/WRITE/COMMENT/SHARE permissions, multiple SIDs, inheritance, grant/deny, auditing, and revocation mechanisms.

**Step 5 — Design default deny and lifecycle.** Having no ACE does not automatically mean public. Specify object creation/deletion, grant/revoke, parent/membership changes, outages, caching, and TTLs.

**Step 6 — Choose the right library/engine.** With Spring Security ACL, verify version/ID type/schema compatibility, `AclService`, `AclPermissionEvaluator`, and policy extensions needed. For highly complex dynamic relationships, consider another engine rather than forcing everything into ACE bitmasks.

**Step 7 — Enforce at service and query boundaries.** Method security blocks actions; tenant-scoped repositories and object policies protect individual records. Ensure Spring proxies cannot be bypassed via self-invocation.

**Step 8 — Optimize listing/pagination and auditing.** Prefer query-first or batch permission checks to avoid N+1. Define how totals/counts and cache invalidation work.

**Step 9 — Test revocation and system failures.** This is where real bugs surface: users still viewing after revocation, admins from another tenant reading data, permission service timeouts passing requests through, or file downloads forgetting ACL checks.

**Step 10 — Roll out per resource type.** You do not need to migrate every table in the system to ACLs at once. Target object types with clear sharing needs, keeping RBAC/owner where still appropriate.

## 20. Common Mistakes

**Mistake 1: "Having the EDITOR role means editing any document."** Roles grant capability permissions, not proof of object permissions. **Fix:** check tenant and object-level permissions.

**Mistake 2: "Having an ownerId means you never need an ACL."** OwnerId cannot express multiple people with multiple permission levels. **Fix:** add a relational/ACL model when genuine sharing exists.

**Mistake 3: "Even a single share table requires full Spring ACL."** False: a single READ relationship can be simpler. **Fix:** choose the minimum necessary complexity.

**Mistake 4: "ACLs automatically protect all lists and counts."** Object-level ACLs do not automatically solve pagination and search. **Fix:** build permission-filtered queries, batching, and proper invalidation.

**Mistake 5: "If no ACL is found, allow by role."** This can unintentionally open up access. **Fix:** fallback policies must be explicitly designed, defaulting to deny for private resources.

**Mistake 6: "The ACL owner is always the business owner."** These are two different concepts. **Fix:** map explicitly and test ownership transfers.

**Mistake 7: "WRITE implies SHARE/DELETE."** Not a universal truth. **Fix:** separate permissions according to business behavior.

**Mistake 8: "Group permissions can be stored once in a token forever."** Membership can change. **Fix:** define token/cache lifetimes and revocation mechanisms.

**Mistake 9: "If the ACL service fails, skip it so the app keeps working."** That is fail-open. **Fix:** do not perform operations when permissions cannot be verified.

**Mistake 10: "Checking ACL after writing is fine."** Risks side effects that cannot be rolled back. **Fix:** guard before mutation.

**Mistake 11: "Just adding @PreAuthorize protects every call."** Self-invocation or services bypassing proxies can skip method security. **Fix:** structure service boundaries and test via real Spring beans.

**Mistake 12: "Enabling spring-security-acl automatically creates ACEs when saving entities."** The framework does not automatically synchronize the entire ACL lifecycle with repositories. **Fix:** implement transactional grant/revoke/create/delete logic and auditing.

## 21. Final Decision Checklist

- [ ] Do permissions genuinely vary by object ID, or only by capability?
- [ ] Are user-to-user/group sharing, multiple permissions, and grant/revoke needed?
- [ ] Would an owner check or a single-permission share table suffice?
- [ ] Are trusted tenant scope, actor identity, and resource identity clearly defined?
- [ ] Are READ/WRITE/COMMENT/SHARE/DELETE permissions defined independently?
- [ ] Is it specified who can grant, re-delegate, revoke, and transfer ownership?
- [ ] Are there requirements for inheritance, explicit deny, expiry, or dynamic groups?
- [ ] Is there a default DENY when ACL/permission does not exist or cannot be verified?
- [ ] Is there a strategy to protect list/search/count/export/download, not just detail APIs?
- [ ] Are database/indexes/batch reads designed to avoid N+1 ACL lookups?
- [ ] Are auditing, cache invalidation, transactions, and revocation workflows in place?
- [ ] Are there integration tests for Spring proxies, permission evaluators, and non-HTTP entry points?
- [ ] Are multi-tenancy, stale permissions, outages, and side effects tested?
- [ ] Does the operational cost of ACL justify the object-level sharing benefits?

**Conclusion:** Use **roles** when permissions follow capabilities; use **owner checks** when each record has a single permitted subject under simple rules; use a **small share table** when only a few easily expressed relationships exist. Choose **ACL** when a resource requires multiple subjects, multiple permission levels, flexible grant/revoke, potential inheritance, and per-object permission administration/auditing. In all cases, **tenant isolation, authentication, scoped queries, and fail-closed behavior** remain mandatory safeguards.

## References

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): SID/ACL/ACE structure, permissions, JDBC schema, `AclService`, and `AclPermissionEvaluator`.
- [Spring Security 6.5 – ACLs](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): behavior comparison for version 6.5.
- [Spring Security – Acl interface API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `isGranted`, `getEntries`, and parent/inheritance semantics.
- [Spring Security – AclPermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): permission checks by object/ID.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, annotations, and proxy interception.
- [Spring Security 6.5 → 7 ACL migration](https://docs.spring.io/spring-security/reference/6.5/migration-7/acl.html): preferring `AclPermissionEvaluator` when migrating away from legacy voter APIs.
