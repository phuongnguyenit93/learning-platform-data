# Grant, Deny, ACE Ordering, and Permission Checking Policies in Spring Security ACL

## 1. The Problem: Who Is Allowed to Do What on **Which Exact Object**?

In Spring Security, `hasRole('EDITOR')` or `hasAuthority('document:read')` typically answers whether a user holds a role or authority. Yet two people who both have permission to read documents are not necessarily allowed to read **the exact same document**. For example:

- Alice owns document 42 and can read and edit it.
- Bob has shared **read** permission on document 42, but no permission to edit.
- The `ROLE_AUDITOR` group can view certain reports, without permission to edit.
- Document 57 belongs to another tenant, so Alice cannot read it even if a general role rule allows reading documents.

An **Access Control List (ACL)** adds a list of permission entries per specific domain object. Each entry is an **Access Control Entry (ACE)** specifying a security identity (SID), a permission, and a **grant** or **deny** flag.

This topic is more than "`grant = true`, `deny = false`." In Spring Security ACL, the outcome also depends on:

1. **The order of ACEs** within the ACL.
2. **The order of the requested permissions list**.
3. **The order of SIDs** held by the caller.
4. **The actual `PermissionGrantingStrategy`** configured.
5. **The parent ACL and ACE inheritance flag**.
6. How the application handles **finding no matching ACE**.

The most important takeaway: **never assume deny always beats every grant, and never treat having no ACE as equivalent to an explicit deny ACE**.

## 2. ACL Components to Know

| Component | Meaning | Example |
| --- | --- | --- |
| `ObjectIdentity` | Unique identity of a domain object | `Document.class` + `42L` |
| `Acl` | List of permissions applying to an object identity | ACL of Document 42 |
| `Sid` | Recipient user or authority | `PrincipalSid("alice")`, `GrantedAuthoritySid("ROLE_AUDITOR")` |
| `Permission` | Action/bitmask being checked | `BasePermission.READ` |
| `AccessControlEntry` | Entry combining ACL + SID + permission + granting | Alice, READ, grant |
| `AclService` | Reads ACLs from the data store | `readAclById(...)` |
| `MutableAclService` | Creates, updates, and deletes ACLs | `createAcl`, `updateAcl` |
| `PermissionGrantingStrategy` | Evaluates ACEs and determines allow/deny | `DefaultPermissionGrantingStrategy` |
| `AclPermissionEvaluator` | Bridges ACLs with `hasPermission(...)` expressions | Used in `@PreAuthorize` |

In the common Spring Security ACL JDBC schema:

- `ACL_CLASS` identifies domain classes.
- `ACL_SID` stores principals/authorities as SIDs.
- `ACL_OBJECT_IDENTITY` stores each object, parent ACL, owner, and `entries_inheriting`.
- `ACL_ENTRY` stores each ACE, including `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, and audit flags.

**`ace_order` matters**: ACEs are not an unordered set of permissions. However, `ace_order` is not the sole factor determining evaluation order, because the input permissions and SID lists are ordered as well.

## 3. What Do Grant and Deny Exactly Mean?

Conceptually, an ACE contains:

```text
Object: Document #42
SID:    PrincipalSid("alice")
Mask:   READ (1)
Grant:  true
```

This means an ACE **grants** READ permission to Alice on Document 42.

Another ACE:

```text
Object: Document #42
SID:    PrincipalSid("bob")
Mask:   WRITE (2)
Grant:  false
```

This is an **explicit deny** entry for Bob's WRITE permission on that object.

In Java, an ACE can be inspected via the `AccessControlEntry` interface:

```java
Sid recipient = ace.getSid();
Permission permission = ace.getPermission();
boolean granting = ace.isGranting();
```

This is a **fragment** reading from an existing `AccessControlEntry`; it does not create an ACL or load from a database.

### Do Not Confuse Three States

| State | What Actually Happens | Practical Meaning |
| --- | --- | --- |
| A matching ACE has `granting=true` | A grant decision exists | `isGranted(...)` can return `true` |
| A matching ACE has `granting=false` | An explicit deny decision exists | `isGranted(...)` can return `false` |
| No matching ACE in the search scope | No conclusive decision yet | May check parent ACL, then `NotFoundException` |

In Spring Security ACL, `NotFoundException` from `Acl.isGranted(...)` **does not necessarily mean the business object does not exist**. It can also mean there is insufficient ACL/SID/permission info to reach a decision. The application must decide how to handle it, typically **not granting access** when proof of permission is missing.

For security systems, **fail closed** is the baseline choice: when permission cannot be verified, do not allow reading or modifying data. Still, never swallow all database errors as "no ACE": an outage is an infrastructure failure that needs logging/monitoring and an appropriate error response.

## 4. Permissions and Bitmasks

Spring ACL's `BasePermission` provides standard permissions:

| Permission | Bit | Mask Value |
| --- | ---: | ---: |
| `BasePermission.READ` | 0 | 1 |
| `BasePermission.WRITE` | 1 | 2 |
| `BasePermission.CREATE` | 2 | 4 |
| `BasePermission.DELETE` | 3 | 8 |
| `BasePermission.ADMINISTRATION` | 4 | 16 |

Bitmasks allow combining permissions. For example, mask `3` contains READ (1) and WRITE (2). However, how a combined mask is **matched against an ACE** is the responsibility of `PermissionGrantingStrategy`, so never rely purely on Java bitwise operators to infer the entire policy.

According to the `DefaultPermissionGrantingStrategy` Javadoc, per-ACE evaluation has notable details:

- For a **grant ACE** with a non-zero requested permission mask, the default strategy considers the ACE a match if `(aceMask & requestedMask) != 0`.
- For a **deny ACE**, the default strategy uses **exact mask matching**: `aceMask == requestedMask`.
- With a custom strategy, or custom `Permission` and mask construction, these semantics may differ.

Example under the default strategy:

```text
Grant ACE, mask = 3 (READ | WRITE)
Ask READ, mask = 1  -> (3 & 1) != 0 -> match
Ask WRITE, mask = 2 -> (3 & 2) != 0 -> match

Deny ACE, mask = 3 (READ | WRITE)
Ask READ, mask = 1 -> 3 != 1 -> no match under default deny rule
Ask mask = 3       -> 3 == 3 -> match
```

**Warning:** multi-bit policies can produce surprising results, especially when "must have both permissions" is modeled via OR/bit-overlap. If you need to require both READ and WRITE, design explicit checks for both permissions and test them; never assume mask `3` means "both bits required" in every check API.

## 5. Three Orders That Must Be Distinguished

Saying "the first ACE decides the permission" is **an incomplete description**. For `DefaultPermissionGrantingStrategy`, the Javadoc describes the approximate search order:

```text
for each requested Permission, in list order:
    for each SID, in list order:
        find the first matching ACE for permission + SID
        if ACE grants:
            allow
        if ACE denies:
            record denial, move to next permission

if all tried permissions were denied:
    deny

if no matching ACE was found:
    try parent ACL if inheritance is enabled
    if still none: NotFoundException
```

This diagram expresses only the **principle of the default strategy**; it omits internal details such as auditing, bitmasks, unloaded SID errors, and parent traversal. When replacing the strategy, do not assume this diagram applies.

### 5.1. ACE Order: First Matching Entry

Suppose there is only **one** SID, Alice, checking only READ. The ACEs are ordered as:

| `ace_order` | SID | Permission | Granting |
| ---: | --- | --- | --- |
| 0 | Alice | READ | false |
| 1 | Alice | READ | true |

The first matching ACE for `READ + Alice` is ACE 0: **deny**. The ACE at index 1 is not an automatic "patch" overriding index 0.

If we reverse the order:

| `ace_order` | SID | Permission | Granting |
| ---: | --- | --- | --- |
| 0 | Alice | READ | true |
| 1 | Alice | READ | false |

The leading grant ACE is found first and READ is allowed. This is why inserting an ACE at the start vs the end of the list can change the decision.

**Remember:** "first" means first **among ACEs matching the permission/SID being evaluated**, not across all `ACL_ENTRY` rows for all objects.

### 5.2. Requested Permission Order

`Acl.isGranted(List<Permission> permissions, List<Sid> sids, ...)` takes a **list** of permissions. Passing multiple permissions represents **acceptable alternatives**, not by default "must satisfy all of them."

Example with Alice:

| ACE | SID | Permission | Granting |
| --- | --- | --- | --- |
| 0 | Alice | READ | false |
| 1 | Alice | WRITE | true |

Calling:

```java
acl.isGranted(
    List.of(BasePermission.READ, BasePermission.WRITE),
    List.of(new PrincipalSid("alice")),
    false
);
```

Under the default strategy, READ hits a deny; then WRITE is tried and finds a grant → result is **true**. Thus there is no global rule saying "whenever a deny exists, every check fails."

Crucial point: if business logic requires **READ AND WRITE**, never pass both in a single `isGranted` call expecting AND semantics. Express "both" explicitly—for instance, checking each permission separately and combining with AND in a controlled policy while handling exceptions properly.

Permission order also affects **search priority, which ACE is inspected first, and audit trails**. When multiple alternatives exist, choose an order with clear business meaning and test behavior when denies and grants mix.

### 5.3. SID Order

An `Authentication` might map to:

- `PrincipalSid("alice")`: personal SID.
- `GrantedAuthoritySid("ROLE_EDITOR")`: group/authority SID.
- `GrantedAuthoritySid("ROLE_AUDITOR")`: another SID.

Suppose Alice belongs to EDITOR. For a single READ permission:

| ACE | SID | Permission | Granting |
| --- | --- | --- | --- |
| 0 | `ROLE_EDITOR` | READ | true |
| 1 | Alice | READ | false |

If the input SID list checks Alice first, the personal deny can be matched before the group grant branch. If the SID list puts the group before Alice, the group grant can win.

`DefaultPermissionGrantingStrategy` emphasizes that **the order of the SID list is significant**; do not rely on accidental collection ordering, table ordering, or token serialization. `SidRetrievalStrategyImpl` typically builds the user SID and `GrantedAuthoritySid`s from `Authentication`; verify how your system builds the list and its exact order in your version.

In systems with a strict requirement that "user deny must always beat group grant," **formalize that rule** via controlled SID ordering and/or a custom `PermissionGrantingStrategy` with rigorous tests, rather than hoping the database happens to sort rows favorably.

## 6. "Deny Always Takes Priority" Is a False Assumption

"Deny-overrides" may be a valid policy in other systems, but **never assume it is the universal semantics of Spring Security ACL**.

Distinguish:

- **Deny ACE**: a `granting=false` flag attached to a specific permission and SID on an object.
- **Global deny-overrides**: if any deny ACE applies, the final outcome is always deny regardless of other grants. This **cannot** be inferred merely from the presence of a deny flag.
- **First applicable**: processes the first matching ACE/SID/permission according to ordering and traversal rules.
- **Any permission granted**: an alternative permission list can succeed if another listed permission is granted.

For instance, when checking `List.of(READ, WRITE)`, an explicit deny on READ does not prevent an explicit grant on WRITE from satisfying that call. That means something very different from the business requirement "the user is strictly forbidden from READ even if they have WRITE."

To build true deny-overrides, specify clearly: does a personal deny block every group grant? Does a composite-mask deny block individual sub-permissions? Can parent ACLs be overridden? Then implement a custom `PermissionGrantingStrategy` or external domain policy, backed by integration tests.

**Never use "deny beats grant" as a test criterion** without specifying the exact SIDs, permissions, ACEs, ordering, and strategy involved.

## 7. Parent ACL Inheritance: When Is the Parent Consulted?

Each `Acl` can have `getParentAcl()` and an `isEntriesInheriting()` flag. Having a parent link **is not enough** for parent ACEs to apply: inheritance must be enabled.

Under the default strategy, when no matching ACE yields a decision on the current ACL, the system may continue into the parent ACL if:

1. `getParentAcl()` is non-null.
2. `isEntriesInheriting()` is `true`.
3. The SID and permission lists allow continuing lookup per the active strategy.

```text
Document 42 ACL
  Do current ACEs match?
      |
      +-- Effective grant/deny exists -> decide at current ACL
      |
      +-- No matching ACE
             |
             +-- entriesInheriting = false -> do not use parent
             |
             +-- entriesInheriting = true + parent exists
                        |
                        v
                 evaluate parent ACL
```

**Never conclude** "a local deny ACE will be overridden by a parent grant" — an explicit deny can terminate inheritance lookup for the queried permission. Conversely, **no local ACE** is not a deny: the parent may supply a grant, or the system ultimately throws `NotFoundException` if no basis exists.

Be especially careful with hierarchical ACLs across organizations, folders, or tenants. A grant on a parent ACL can expose large subtrees of child objects. In multi-tenant data, parent references must respect tenant boundaries; ACL inheritance never replaces baseline data isolation guards.

## 8. Finding No ACE Is Not a Deny ACE

`Acl.isGranted(...)` is a decision API, not a getter returning default `false` in every case. Per the Javadoc:

- `true`: grant evidence found per policy.
- `false`: explicit deny decision reached per strategy.
- `NotFoundException`: the strategy found no basis to decide permission.
- `UnloadedSidException`: the ACL was loaded only for a subset of SIDs, and the caller checked an unloaded SID.

Consequence:

```java
boolean allowed;
try {
    allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false
    );
} catch (NotFoundException ex) {
    allowed = false; // fail closed: insufficient ACL info to grant
}
```

This is a **fragment** illustrating no-match handling; `acl` and `sids` must come from trusted sources. Never catch all exceptions and return `true`. If `UnloadedSidException` occurs, investigate/reload the ACL with the complete SID list or ensure safe denial and log the configuration error; never treat it as an explicit ACE deny.

`NotFoundException` when calling `AclService.readAclById(...)` also means **no ACL exists for that `ObjectIdentity`**, distinct from "ACL exists but contains no matching ACE." Both cases should be distinguished in audit/diagnostics, though both normally result in **denying access** under a fail-closed policy.

Never mask database connection drops, schema errors, or cache failures as fake `NotFoundException`s so the app continues as if no ACL existed. Infrastructure errors must be handled separately without leaking data.

## 9. Adding ACEs: Index, Grant Flag, and Persistence Updates

Spring ACL provides `MutableAcl.insertAce(int atIndexLocation, Permission permission, Sid sid, boolean granting)`. The `atIndexLocation` parameter is the **index in the ACE list**, not a database row ID. You can insert at the beginning or append at the end; position choice is a policy decision.

Example **component in a Spring application**, assuming `MutableAclService` is configured, `Document` is a real domain class, and the caller is authorized to administer ACLs:

```java
import java.io.Serializable;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.NotFoundException;

public class DocumentAclAdmin {
    private final MutableAclService aclService;

    public DocumentAclAdmin(MutableAclService aclService) {
        this.aclService = aclService;
    }

    public void addReadRule(Serializable documentId,
                            String username,
                            boolean granting) {
        ObjectIdentity identity =
            new ObjectIdentityImpl(Document.class, documentId);
        Sid sid = new PrincipalSid(username);

        MutableAcl acl;
        try {
            acl = (MutableAcl) aclService.readAclById(identity);
        } catch (NotFoundException missing) {
            acl = aclService.createAcl(identity);
        }

        // Insert at index 0: ordering can affect decisions.
        acl.insertAce(0, BasePermission.READ, sid, granting);
        aclService.updateAcl(acl);
    }
}
```

**Explanation and boundaries:**

- `addReadRule(..., true)` creates a **READ grant** ACE; `false` creates a **READ deny** ACE.
- `insertAce(0, ...)` precedes existing ACEs. `insertAce(acl.getEntries().size(), ...)` appends at the end.
- `updateAcl(acl)` persists the change. Spring Security **does not automatically create or update ACLs** merely because a repository saves a `Document`.
- You must authorize **who is allowed to edit ACLs**; ACL administration is a sensitive security operation, so never let users choose arbitrary SIDs and granting flags.
- Avoid appending duplicate ACEs indefinitely; manage idempotency, versioning/concurrency, change history, and intentional ordering.
- Transaction/ACL cache settings must ensure permission changes take effect on time. When caching is enabled, verify invalidation and multi-instance behavior.

The example above is not a standalone file: it requires the `Document` model, JDBC ACL infrastructure, schema, datasource, ACL authorization strategy, and application transaction/configuration.

### Should All Denies Be Placed Before All Grants?

That can be a **convention** to reduce conflicts for the same permission/SID, but never treat it as an invariant law of Spring Security ACL. Because the evaluator also iterates requested permissions and SIDs in order, a grant on another permission or SID can still yield an allow depending on the case.

A cleaner convention is resolving conflicts at **write time**: disallow two ACEs with the same `ObjectIdentity + Sid + Permission` and opposite `granting` flags unless an explicit priority rule exists. If business allows overrides, store/maintain ordering explicitly and test update behavior.

## 10. Evaluating via `Acl.isGranted` Instead of Scanning `getEntries`

A common mistake is writing:

```java
// DO NOT USE as a general policy.
boolean canRead = acl.getEntries().stream()
    .anyMatch(ace -> ace.isGranting()
        && ace.getPermission().equals(BasePermission.READ));
```

This code is wrong because it **ignores the caller's SID**, precedence of denies, masks, parent ACLs, unloaded SIDs, and granting strategy. It could grant Alice access merely because an ACE grants READ to Bob.

The proper evaluation API is:

```java
boolean granted = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("alice")),
    false
);
```

In real applications, the SID list should be built from verified `Authentication` via `SidRetrievalStrategy` or a matching policy, never from an arbitrary request username. The `false` third argument is **`administrativeMode`**, which relates to auditing, **not** "skip admin permissions" or "force deny." When `administrativeMode=true`, by contract the check is treated as an administrative inspection and may suppress audit logging.

Never pass `List.of(BasePermission.READ, BasePermission.WRITE)` if business requires **both READ and WRITE**; the list represents alternative permissions that can satisfy a decision. Combine requirements with AND in Java policy or use two separate checks with explicit exception handling.

## 11. Integrating with `PermissionEvaluator` and `@PreAuthorize`

In Spring Security, `AclPermissionEvaluator` bridges ACLs with `hasPermission(...)` expressions. In a Servlet application with method security, you can declare:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AclMethodSecurityConfig {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

This is **component configuration**, requiring properly configured `AclService` and JDBC ACL/caching beans. It does not automatically create ACL tables or ACEs for new documents; provisioning must be managed by the application.

A service can then use:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "hasPermission(#id, 'com.example.documents.Document', 'READ')"
    )
    public Document readDocument(@P("id") Long id) {
        return documents.findById(id).orElseThrow();
    }
}
```

**Important:** the target type string must match the `ObjectIdentity` stored in the real ACL. If the ACL stores class `com.example.documents.Document`, passing `"Document"` when the implementation expects the fully qualified class name can cause ACL lookup misses.

The illustrative code above is only a skeleton:

- It requires your project's `DocumentRepository`, model, and real ACL data.
- Invocation must pass through a **Spring proxy** for `@PreAuthorize` to execute; self-invocation via `this.readDocument(...)` can bypass it.
- `hasPermission` handles ACLs, but **does not replace tenant boundaries**, business ownership constraints, or scoped queries.
- If `AclPermissionEvaluator` returns false, method security denies access; HTTP 403/404 response mapping depends on configuration, **not** on ACEs directly producing HTTP status codes.
- For write permissions, check before side effects and use queries/transactions that guard against TOCTOU. A `@PostAuthorize` denial after a write has committed will not automatically roll back a completed transaction.

### Policies Combining Tenant, State, and ACL

Combining multiple conditions is usually good practice:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@tenantPolicy.canAccess(authentication, #id) and " +
    "hasPermission(#id, 'com.example.documents.Document', 'READ')"
)
```

`tenantPolicy` must verify the real tenant via server/database state, not merely compare `X-Tenant-Id` against a self-declared claim. If a document is soft-deleted, archived, classified, or the account is suspended, those conditions may need enforcement **outside the ACL**. ACL is an object-level permission layer; it does not define all business rules.

## 12. Standalone Java 17 Demo: Same ACEs, Different Order Changes the Outcome

The following program simulates **part of `DefaultPermissionGrantingStrategy`'s semantics** with single-bit permissions, exact mask matches, and without parent ACLs, caching, auditing, or a database. It does not import Spring Security. Its goal is illustrating three factors: ACE order, SID order, and alternative permission lists.

Create file `AceOrderDemo.java`:

```java
import java.util.List;

public class AceOrderDemo {

    record Ace(String sid, String permission, boolean granting) {}

    enum Outcome {
        GRANT, DENY, NO_MATCH
    }

    static Outcome check(
            List<Ace> entries,
            List<String> requestedPermissions,
            List<String> sids) {

        boolean foundDeny = false;

        for (String permission : requestedPermissions) {
            boolean deniedThisPermission = false;

            for (String sid : sids) {
                for (Ace ace : entries) {
                    if (!ace.sid().equals(sid)
                            || !ace.permission().equals(permission)) {
                        continue;
                    }

                    if (ace.granting()) {
                        return Outcome.GRANT;
                    }

                    foundDeny = true;
                    deniedThisPermission = true;
                    break; // First matching ACE for this SID/permission.
                }

                if (deniedThisPermission) {
                    break; // Try the next requested permission.
                }
            }
        }

        return foundDeny ? Outcome.DENY : Outcome.NO_MATCH;
    }

    public static void main(String[] args) {
        List<Ace> denyFirst = List.of(
            new Ace("alice", "READ", false),
            new Ace("alice", "READ", true)
        );
        List<Ace> grantFirst = List.of(
            new Ace("alice", "READ", true),
            new Ace("alice", "READ", false)
        );

        List<Ace> alternatives = List.of(
            new Ace("alice", "READ", false),
            new Ace("alice", "WRITE", true)
        );

        List<Ace> principalAndGroup = List.of(
            new Ace("team", "READ", true),
            new Ace("alice", "READ", false)
        );

        System.out.println("Deny ACE first: " + check(
            denyFirst, List.of("READ"), List.of("alice")));

        System.out.println("Grant ACE first: " + check(
            grantFirst, List.of("READ"), List.of("alice")));

        System.out.println("READ or WRITE: " + check(
            alternatives, List.of("READ", "WRITE"), List.of("alice")));

        System.out.println("Principal SID first: " + check(
            principalAndGroup, List.of("READ"),
            List.of("alice", "team")));

        System.out.println("Group SID first: " + check(
            principalAndGroup, List.of("READ"),
            List.of("team", "alice")));

        System.out.println("No matching ACE: " + check(
            denyFirst, List.of("DELETE"), List.of("alice")));
    }
}
```

Run with JDK 17 or newer:

```bash
javac AceOrderDemo.java
java AceOrderDemo
```

Exact stdout:

```text
Deny ACE first: DENY
Grant ACE first: GRANT
READ or WRITE: GRANT
Principal SID first: DENY
Group SID first: GRANT
No matching ACE: NO_MATCH
```

Explanation:

- **Lines 1–2:** two ACEs with the same SID/permission; swapping their order flips the outcome.
- **Line 3:** READ is denied, yet WRITE is an alternative permission with a grant → outcome is grant.
- **Lines 4–5:** the exact same ACE list, but changing the order of evaluated SIDs flips the outcome.
- **Line 6:** no ACE matches DELETE → insufficient information state, **not synonymous with explicit deny**.

**Simulation limits:** the code uses string permission names and does not simulate asymmetric grant/deny bitmask matching, auditing, `UnloadedSidException`, parent ACLs, or all production details. To verify real policies, write tests using `DefaultPermissionGrantingStrategy`/`AclImpl` and Spring Security's ACL persistence in your target version.

## 13. When Do You Need a Custom `PermissionGrantingStrategy`?

`DefaultPermissionGrantingStrategy` is a solid default with clear traversal rules. However, some organizations require different policies:

- A principal deny **always** beats any group grant.
- A deny on a child ACL is **never** overridden by a parent in any scenario.
- The ADMINISTRATION permission implies a custom set of actions per convention.
- Every request must satisfy both permissions (AND), not OR.
- Priority among principal, role, and department must remain invariant regardless of the order in which SIDs are passed.

If you choose policies like these, specify them completely and implement them in a centralized component such as a custom `PermissionGrantingStrategy` or dedicated domain policy, rather than scattering `if` conditions across services.

Questions to answer before writing a custom strategy:

1. **Can a grant ever override an explicit deny?** If so, when?
2. **Does a group deny block a personal grant?**
3. **Is SID order part of the contract?**
4. **Does a composite-mask deny block individual sub-permissions?**
5. **How does parent inheritance handle deny vs missing entries?**
6. **Are auditing semantics and `NotFoundException`/`UnloadedSidException` behavior preserved?**
7. **Could current rules break when upgrading Spring Security versions?**

Only swap strategies after building a **decision-table test suite** covering disputed grant/deny cases. For simple policies such as owner and tenant checks, filtered database queries or a Java authorization bean can be cleaner than a heavily customized ACL framework.

## 14. ACL Grant/Deny/Order Testing Checklist

| Scenario | What to Verify |
| --- | --- |
| Only a READ grant ACE for Alice | Alice can read; others are not automatically granted |
| Only a READ deny ACE for Alice | Alice is denied; no default grant |
| Deny then grant for same SID/permission | Order decides per strategy; test reversed order too |
| Grant then deny for same SID/permission | Outcome can flip when ACE order reverses |
| Group grant, personal deny | Outcome depends on SID order/strategy; do not assume global deny |
| `List.of(READ, WRITE)` with READ denied, WRITE granted | Understand these are alternative permissions, not AND |
| Child ACL has no matching ACE, inheritance on | Parent can be evaluated |
| Child ACL has explicit deny, parent grants | Local deny and inheritance follow strategy; test |
| Inheritance off | Parent is not consulted for grants |
| No matching ACE in either child or parent | `NotFoundException`/fail-closed handling |
| Unloaded SID | `UnloadedSidException` or safe SID loading validation |
| Multi-bit grant mask, multi-bit deny mask | Verify asymmetric matching rules |
| ACL update changes order | Decision updates accurately, cache is refreshed |
| Object belongs to another tenant | ACL never crosses tenant boundaries |
| DB failure while loading ACL | Never grants access; infrastructure error logged properly |
| Call via Spring proxy | `hasPermission` annotation actually executes |
| Internal call `this.method()` | Identify proxy-bypass risk |
| User edits ACEs via API | Only authorized actors can modify ACLs |

### Types of Tests to Include

**Unit tests:** construct ACLs with controlled ordering of ACEs/SIDs/permissions and call `isGranted(...)`; assert grant/deny/missing and custom strategy branches.

**Integration tests:** use the JDBC ACL schema, repositories, transactions, caches, and `@EnableMethodSecurity`. Ensure `ace_order` rows are persisted and loaded in order, ACL updates leave no stale cache entries, and revocations take effect.

**Security/negative tests:** test cross-tenant users, non-group members, missing SIDs, denied permissions, wrong tokens/roles, and documents without ACLs; verify zero unauthorized data exposure or side effects.

**Audit tests:** verify reasons are logged internally at the necessary level without logging tokens/secrets or leaking detailed ACL internals to unauthorized callers. `administrativeMode` must be used as intended, never confused with `ADMINISTRATION` rights.

## 15. Real-World Bugs and How to Fix Them

| Bug | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "Deny always beats every grant" | Strategy traverses permissions, SIDs, and ACEs in order; a grant on another branch can win | Define the real policy, read the Javadoc, and test multiple branches |
| Treating `ACL_ENTRY` as an unordered set | `ace_order` and `insertAce` index exist | Manage order explicitly and test after reload |
| Using `isGranted(List.of(READ, WRITE), ...)` to require both | Permission list succeeds if one alternative matches | Write an explicit AND check |
| Treating missing ACE as a stored explicit deny | No match can throw `NotFoundException` | Fail closed, but distinguish them in logs/tests |
| Assuming `NotFoundException` means the business entity definitely does not exist | ACL or matching ACE may simply be missing | Verify domain records and ACLs separately |
| Ignoring `UnloadedSidException` | ACL was loaded without all SIDs needed for the check | Load all needed SIDs or fail safely |
| Iterating `getEntries()` and ignoring SIDs | Can pick up another user's grant | Use `Acl.isGranted(...)` |
| Assuming grant/deny bitmask matching is symmetric | Default strategy treats grant and deny masks differently | Test masks; never guess from bitwise math alone |
| Forgetting `entriesInheriting` with a parent ACL | Parent may or may not apply | Verify the inheritance flag and test child/parent |
| Giving ACL owner all domain rights | ACL ownership and domain object rights are not identical by default | Separate ACL administration from domain read/write |
| Letting clients choose granting/index/SID | Users could grant themselves permissions | Strictly protect ACL update endpoints and audit changes |
| Checking ACL then querying/writing unscoped | Race conditions or cross-tenant access | Scope queries by tenant/owner and transaction |
| ACL updated but cache not refreshed | Revocations do not take effect immediately | Invalidate cache and test multi-instance setups |
| Writing only simulated unit tests | Does not prove the framework matches the simulation | Write integration tests with real APIs and DB ACLs |

## 16. Review Workflow for a Conflicting ACL

When encountering a bug like "a user can still view despite a deny," do not tweak ACEs blindly. Investigate in order:

1. Identify the exact **object identity**: class + ID, and verify the domain object belongs to the right tenant.
2. Identify the **requested permissions**: READ, WRITE, a composite mask, or alternative list; record the exact order.
3. Identify the **SID list** derived from `Authentication`: principal and `GrantedAuthority` SIDs; record the exact order.
4. Read **the current ACL's ACEs in `ace_order`**, checking grant/deny and masks.
5. Identify the actual **`PermissionGrantingStrategy`** in use (default or custom).
6. Inspect the **parent ACL**, `entriesInheriting` flag, and any inherited ACEs that may be evaluated.
7. Distinguish **grant**, **explicit deny**, **no match**, and **unloaded SID**, without conflating infrastructure errors.
8. Check **cache**, version, and transactions after the latest ACL modification.
9. Run a reproduction test with the exact same permission/SID/ACE order and a test with reversed order.
10. Fix the policy centrally, protect ACL management APIs, and add regression tests.

**Summary:** In Spring Security ACL, an ACE's `granting=true/false` flag is only one piece of the decision. To determine the final permission, evaluate **permission order → SID order → ACE order**, mask semantics, parent inheritance, and `PermissionGrantingStrategy`. `Acl.isGranted(...)` is the supported decision point; never replace it by manually searching for any granting ACE in the database.

## Official Docs

- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL/ACE model, permission bitmasks, storage tables, and `insertAce`.
- [Spring Security API — DefaultPermissionGrantingStrategy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): permission/SID order, first matching ACE, grant/deny, `NotFoundException`, and mask matching.
- [Spring Security API — Acl and isGranted](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): permission-checking contract, inheritance, and loaded SIDs.
- [Spring Security API — AclImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AclImpl.html): `getEntries`, `insertAce`, `isEntriesInheriting`, `getParentAcl`.
- [Spring Security API — AclPermissionEvaluator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): integrating ACLs with `hasPermission`.
- [Spring Security — ACL database schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): structure of `acl_entry`, `ace_order`, and ACL tables.
