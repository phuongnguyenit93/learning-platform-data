# Checking Properties of Input Objects

> **Module:** Spring Security - authorization  
> **Knowledge group:** Pre-method checks  
> **Goal:** Use `@PreAuthorize` to read properties of method parameters (DTO, command, object, collection) and enforce authorization **before the method body executes**; understand `#command`, `@P`, `-parameters`, SpEL, and authorization over client-controlled inputs; design policies grounded in Authentication and trusted server data to prevent IDOR/BOLA/over-posting/TOCTOU; know how to test wrong permissions, missing fields, forged inputs, and side effects.

## 1. Problem: an input property does not equal truth about the object

A service has a method:

```java
public void renameDocument(RenameDocumentCommand command) {
    // Perform document rename...
}
```

A request may contain:

```json
{
  "documentId": 42,
  "claimedOwnerId": "alice",
  "tenantId": "org-a",
  "newTitle": "Next month plan"
}
```

With Spring Method Security, we can write:

```java
@PreAuthorize("hasAuthority('document:rename') and #command != null")
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

Spring evaluates `@PreAuthorize` before running the body and can inspect the `command` object and its properties. However, **you must not** reason that “`command.claimedOwnerId == authentication.name`, therefore the user is definitely the owner of document 42”: `claimedOwnerId` is **client-claimed data**. Alice can submit Bob's `documentId=42` alongside `claimedOwnerId=alice`.

Two distinct questions:

1. **Does the input belong to a request category the actor is allowed to perform?** For example, the “rename” action requires `document:rename`; CSV export format requires `report:export`.
2. **Does real system data allow the actor to perform this on this resource?** You must load the document from a trusted source and check tenant, owner, ACL, status, etc.

This lesson focuses on **pre-invocation checks** and bounded use of input properties without confusing validation with authorization.

## 2. Where does @PreAuthorize operate?

Example:

```java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void renameDocument(RenameDocumentCommand command) {
    // Body only runs when the pre-check permits it.
}
```

Flow in Spring Security Servlet 6.5:

```text
Controller / another Spring bean
            |
            v
Spring AOP proxy (method-security interception)
            |
            v
AuthorizationManagerBeforeMethodInterceptor
            |
            v
PreAuthorizeAuthorizationManager
            |
            v
MethodSecurityExpressionHandler
  - Current Authentication
  - MethodInvocation and parameters
  - SpEL expression inside @PreAuthorize
            |
            +--- DENY -> do not run method body
            |
            +--- ALLOW -> run method body
                              |
                              v
                       Domain policy / DB
```

`@EnableMethodSecurity` must be enabled:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

**Condition:** the bean must be Spring-managed and the invocation must pass through the proxy/advisor. The annotation does not automatically protect `this.method()` calls within the same target object under typical Spring AOP proxy configurations. Nor does it protect objects instantiated with `new` outside the container.

`@PreAuthorize` denies when the interceptor runs **before** the method body; for write commands, this is a more suitable point than `@PostAuthorize`. Still, if the pre-check merely compares two forged client values, it remains a **wrong policy check** despite running at the right time.

## 3. Accessing properties with SpEL

Spring Security supports expressions referencing method parameters:

```java
@PreAuthorize("#command.documentId != null")
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

`#command` is the parameter named `command`; `.documentId` is a SpEL property, typically accessed via the `getDocumentId()` getter or the type's property-access mechanism. For a JavaBean DTO:

```java
public final class RenameDocumentCommand {
    private final Long documentId;
    private final String newTitle;

    public RenameDocumentCommand(Long documentId, String newTitle) {
        this.documentId = documentId;
        this.newTitle = newTitle;
    }

    public Long getDocumentId() {
        return documentId;
    }

    public String getNewTitle() {
        return newTitle;
    }
}
```

How to invoke it in the annotation:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

Things to understand:
- `#command` is distinct from `authentication` and `principal`. It is the call's input.
- The `documentId` property must exist with the matching name and type; a Java field name may not match the property name if a custom getter is used.
- SpEL can invoke methods/property getters. Avoid getters with side effects, I/O, or unstable mutable data inside a security expression.
- If the object is null, an expression accessing properties directly may raise an error. Write explicit null guards and rely on short-circuit `and`.
- A null guard does not mean authorization was verified; it only prevents the expression from dereferencing a nonexistent object.

Multi-level example:

```java
@PreAuthorize(
    "#command != null and #command.options != null and "
    + "#command.options.format == 'CSV'"
)
public void export(ExportCommand command) {
    // ...
}
```

`options` and `format` are still only input properties. You must verify the method body actually executes the checked format; if a controller applies an alias/implicit default or a business command switches modes after the pre-check, the security rule can diverge from real behavior.

## 4. Where does Spring get the name #command from?

A very common error is `#command.documentId` failing to resolve the parameter name at runtime. Spring Security uses `DefaultSecurityParameterNameDiscoverer` to discover parameter names.

Supported mechanisms include:

### A. Compile with -parameters

```bash
javac -parameters RenameDocumentService.java
```

In Maven/Gradle, enable the `-parameters` Java compiler option on the exact module build. Spring Framework 6.1 removed the prior `LocalVariableTable`-based parameter name discovery; therefore, for method-security code referencing `#id` or `#command` by Java name, **having `-parameters` is especially critical**.

Maven Compiler Plugin example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

This is a snippet inside `pom.xml`, which belongs under `build/plugins` per project layout alongside verifying the compiler plugin version; it is a configuration fragment, not a complete Maven file.

With Gradle Groovy DSL you can use:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Many Spring Boot builds configure parameter metadata automatically, yet **inspect the actual build output** instead of guessing from the framework name.

### B. Naming with @P

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "@documentPolicy.mayRequestRename(authentication, #command)"
)
public void renameDocument(
        @P("command") RenameDocumentCommand input) {
    // ...
}
```

`@P("command")` assigns a name usable in SpEL even though the Java variable is named `input`. Useful for separately compiled interface/service contracts or when you do not control compiler flags.

### C. Spring Data @Param

`DefaultSecurityParameterNameDiscoverer` also supports `org.springframework.data.repository.query.Param` in configurations with that dependency. However, do not add Spring Data merely to name a security parameter; `@P` or `-parameters` is usually simpler.

### D. Positional names

Spring `MethodBasedEvaluationContext` typically provides positional aliases like `#p0`, `#a0`, `#p1`. They help illustrate argument access, yet meaningful names like `#command` are easier to read/review and less error-prone when reordering parameters. When multiple overloads/interfaces exist, add tests for the exact method invoked.

**Easily misdiagnosed error:** an expression unable to find `#command` may raise a SpEL error or evaluate to deny, which does not mean the user lacks an authority. Check parameter metadata, property names, and the build before altering policies.

## 5. What variables besides parameters does @PreAuthorize have?

Commonly used expressions:

| Expression | Meaning | What to remember |
| --- | --- | --- |
| `authentication` | Call's `Authentication` | Can contain principal, authorities, details |
| `principal` | `Authentication#getPrincipal()` | Principal type can vary by login/JWT mechanism |
| `authentication.name` | Username per Authentication | Not always equal to DB ID |
| `hasAuthority('x')` | Checks specific authority | Role hierarchy/prefix policy depends on manager config |
| `hasRole('ADMIN')` | Checks role with default `ROLE_` prefix | Do not confuse with resource owner |
| `#command` | Named method argument | Caller-controllable data |
| `#command.documentId` | Property of argument | An ID alone does not prove permission on the object |
| `@documentPolicy` | Spring bean called from SpEL | Complex domain logic should live in Java |
| `hasPermission(...)` | Checks permission via suitable `PermissionEvaluator` | Requires real evaluator/policy config; ACL is not automatic just by enabling Spring Security |

Depending on context/version, additional expression root methods/variables exist. Do not rely on variable names from an example for another version without verifying compilation and tests.

Example:

```java
@PreAuthorize(
    "hasAuthority('report:read') and "
    + "@reportPolicy.canRead(authentication, #query.reportId)"
)
public ReportView getReport(ReportQuery query) {
    // ...
}
```

The bean can extract a trusted actor from Authentication and load the resource from the server. However, **a DB read in the pre-expression** followed by the body reading/updating later must maintain consistency to avoid TOCTOU. Often the pre-expression acts as a general permission gate while full checks run inside the use case transaction.

## 6. Validation and authorization have two distinct jobs

Example receiving a DTO:

```java
public record CreateInvoiceCommand(
    Long projectId,
    java.math.BigDecimal amount,
    String currency,
    String requestedBy
) {}
```

Validation may enforce:
- `projectId` is non-null and positive.
- `amount` is positive with valid precision.
- `currency` is in the supported list.
- `requestedBy` matches character format rules.

Yet validation does not verify the actor:
- Are they permitted to create an invoice for `projectId`?
- Are they a member of the tenant owning the project?
- Do they have sufficient limit to create an invoice with `amount`?
- Are they permitted to choose a `requestedBy` other than themselves?
- Is the resource still in a state that allows creating invoices?

**Never turn client-controllable conditions into proof of permission.** For example, `requestedBy == authentication.name` only proves the caller typed their own name, not that the invoice data belongs to the verified actor. The server should populate `createdBy` from the authenticated principal/actor itself, rather than accepting it directly from JSON if it is security-sensitive.

A method may carry both `@Valid` and `@PreAuthorize`, yet **do not assume the order between validation and the security advisor** is always guaranteed across all Spring/Bean Validation setups. When inputs can be null/malformed, the security expression should handle nulls itself while the service validates at the proper boundary.

## 7. When is using an input property directly reasonable?

Using an input property in a pre-check can be useful when that property is genuinely a **request classification criterion**, not proof that the actor owns a resource.

For example, an export system with two capabilities:
- `report:export:summary` for summary reports.
- `report:export:raw` for sensitive raw data.

```java
@PreAuthorize(
    "#request != null and "
    + "((#request.mode == 'SUMMARY' "
    + "and hasAuthority('report:export:summary')) "
    + "or (#request.mode == 'RAW' "
    + "and hasAuthority('report:export:raw')))"
)
public ExportResult exportReport(ExportRequest request) {
    // ...
}
```

The condition above can be sound if:
1. `mode` is an enum/string parsed and validated consistently;
2. the body actually performs only what `mode` permits;
3. no default/alias/other header causes the body to export RAW when the expression thinks SUMMARY;
4. policies on the real tenant/report are still checked;
5. a user with only summary rights cannot obtain raw data by tweaking other fields.

If mode policy is complex, prefer:

```java
@PreAuthorize("@exportPolicy.mayExport(authentication, #request)")
public ExportResult exportReport(ExportRequest request) {
    // ...
}
```

And the `exportPolicy` bean must check capability against the **effective mode** along with actor/resource. Do not write a multi-branch SpEL string that reviewers can easily misread.

## 8. Dangerous pattern: trusting ownerId inside the DTO

**Unsafe:**

```java
@PreAuthorize(
    "hasAuthority('document:write') and "
    + "#command.claimedOwnerId == authentication.name"
)
public void rename(RenameDocumentCommand command) {
    repository.renameById(command.getDocumentId(),
        command.getNewTitle());
}
```

A client Bob can send:

```json
{
  "documentId": 42,
  "claimedOwnerId": "bob",
  "newTitle": "Changed"
}
```

If document 42 actually belongs to Alice, `#command.claimedOwnerId == authentication.name` still evaluates to true for Bob; the body updates by ID and ignores the real owner. This is **IDOR/BOLA** even though `@PreAuthorize` ran before the body.

A similar anti-pattern:

```java
@PreAuthorize("#command.tenantId == principal.tenantId")
```

If `command.tenantId` is client-supplied, the condition only proves the client selected their active tenant; **it does not prove documentId resides in that tenant**. You must look up the document's tenant in the DB and verify permissions on the actual resource.

**Rule:** any field representing ownership, tenant membership, clearance, approval status, or financial values must be checked against a trusted source. Even if clients are allowed to send them as business inputs, never treat them as verified facts.

## 9. How does mass assignment/over-posting alter inputs?

A DTO accepting too many fields:

```java
public class UpdateUserRequest {
    private String displayName;
    private String email;
    private boolean admin;
    private String tenantId;
    private String ownerId;
    // getters/setters
}
```

If a controller binds JSON into the object above and the service copies it straight into an entity using an unrestricted mapper, a user can set `admin=true` or alter `tenantId`. A `hasRole('USER')` pre-check cannot rescue an over-posting vulnerability.

Better design:
- Profile-edit DTOs contain only allowed fields: `displayName`, `locale`, etc.
- Separate `ChangeRoleCommand` with strong authority and dedicated policies.
- Fields like `createdBy`, `tenantId`, `approvedBy` are server-assigned or membership-checked.
- Mappers copy only an allowlist of fields, never binding an entire entity directly from requests.
- Domain entities do not allow callers to arbitrarily mutate owner/role/status via generic setters.
- Test JSON containing unauthorized fields, verifying DB remains unchanged and the response is appropriate.

A `@PreAuthorize("#request.admin == false")` check inspects the input value at only one point; if another endpoint or binding path permits the admin flag, the system remains at risk. Design proper DTOs and entity invariants.

## 10. Authentication.name is not always the owner ID

`authentication.name` can be:
- internal username;
- email;
- OIDC subject;
- opaque user ID;
- service account name.

Meanwhile, the DB may use a UUID `ownerId` distinct from the username. Comparing:

```java
@PreAuthorize("#command.ownerId == authentication.name")
```

can be both the wrong policy and an identity type mismatch.

Define a server-side actor instead:

```java
public record Actor(
    java.util.UUID userId,
    java.util.UUID activeTenantId,
    java.util.Set<String> authorities
) {}
```

`Actor` must be built from the authenticated Authentication and verified membership/tenant context; never take `userId` or `activeTenantId` from an untrusted body.

A resource-read policy can accept:

```java
boolean canRead(Actor actor, Document document);
```

Avoid calling a policy bean with `authentication.name` and assuming it is always the owner's UUID. When switching OAuth2 providers, principal semantics can change, breaking the rule.

## 11. Putting policies in Java beans instead of long SpEL

A clear interface:

```java
public interface DocumentAccessPolicy {
    boolean canRename(Actor actor, Document document);
}
```

Integration idea:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {

    private final ActorResolver actorResolver;
    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    public DocumentCommandService(ActorResolver actorResolver,
                                  DocumentRepository repository,
                                  DocumentAccessPolicy policy) {
        this.actorResolver = actorResolver;
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize(
        "hasAuthority('document:rename') and #command != null"
    )
    @Transactional
    public void rename(RenameDocumentCommand command) {
        Actor actor = actorResolver.requireAuthenticatedActor();

        Document document = repository.findForUpdateInTenant(
            command.getDocumentId(), actor.activeTenantId()
        ).orElseThrow(DocumentNotFoundException::new);

        if (!policy.canRename(actor, document)) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Rename denied"
            );
        }

        document.rename(command.getNewTitle());
    }
}
```

**This is an integration snippet**, not a standalone JDK file. Types `ActorResolver`, `Document`, `DocumentRepository`, `DocumentAccessPolicy`, `RenameDocumentCommand`, exceptions, and `findForUpdateInTenant` are application contracts. Imports, transaction manager, repository implementation, validation, and authentication must be supplied in a real project.

Flow:
- `@PreAuthorize` checks functional authority before the body.
- Actor comes from server-side Authentication.
- Entity is loaded scoped to the verified tenant, not `command.tenantId`.
- Policy checks owner/ACL/delegation/state.
- Only after ALLOW is the entity modified inside the transaction.

If there is a “tenant admin can edit any document in the same tenant” permission, place it inside `policy.canRename` **scoped to the tenant**, rather than bypassing all checks with `if (isAdmin) return true` at the top.

## 12. Using @documentAccess in @PreAuthorize

Logic can reside in a Spring bean:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccessExpression {

    private final DocumentRepository repository;
    private final ActorResolver actors;

    public DocumentAccessExpression(DocumentRepository repository,
                                    ActorResolver actors) {
        this.repository = repository;
        this.actors = actors;
    }

    public boolean mayRename(Authentication authentication,
                             RenameDocumentCommand command) {
        if (authentication == null || command == null
                || command.getDocumentId() == null) {
            return false;
        }

        Actor actor = actors.requireActor(authentication);
        return repository.findByIdAndTenantId(
                command.getDocumentId(), actor.activeTenantId()
            )
            .filter(doc -> doc.canBeRenamedBy(actor))
            .isPresent();
    }
}
```

Called from the service:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "@documentAccess.mayRename(authentication, #command)"
)
public void rename(RenameDocumentCommand command) {
    // ...
}
```

**Important technical note:** `doc.canBeRenamedBy(actor)` and `requireActor` here are **app-defined** domain contracts. The pre-expression loads the document before the body, yet the body may query it again afterward. For commands with side effects, still verify the policy on the entity/state used for the write **within the same transaction or conditional update**. Putting DB queries in authorization beans must consider performance bounds, fail-closed exception handling, and never confuse “record not found” with “allowed”.

If the policy only needs a general authority and a clear DTO mode, no DB lookup is needed in SpEL. If owner/tenant is required, consider performing the check inside the service once the object is loaded to avoid duplicate reads and TOCTOU.

## 13. Nested input properties, collections, Maps, and enums

Common forms:

```java
// 1. JavaBean DTO: #request.options.format
@PreAuthorize(
    "#request != null and #request.options != null and "
    + "#request.options.format == 'CSV'"
)
public void export(ExportRequest request) { }

// 2. List of IDs: only checks size, DOES NOT check permission per ID yet.
@PreAuthorize(
    "hasAuthority('document:bulk:read') and "
    + "#ids != null and #ids.size() <= 100"
)
public void readMany(java.util.List<Long> ids) { }

// 3. Property Map: Map access syntax depends on structure.
@PreAuthorize(
    "#attributes != null and #attributes['visibility'] == 'PUBLIC'"
)
public void changeVisibility(java.util.Map<String, String> attributes) { }
```

These are **isolated snippets**, not a standalone compiling class. They show SpEL can inspect properties/collections/maps. However:
- `ids.size() <= 100` is only a batch limit, not proof of permission on **each ID**.
- `attributes['visibility'] == 'PUBLIC'` reads a caller-supplied value; it does not prove the object is allowed to be published.
- Enums/string properties must use the same parser/validation as the body to avoid mismatches.
- Lists/maps may be mutable; external callers could retain a reference and mutate data under async/concurrent execution.
- Avoid invoking arbitrary/side-effecting getter methods inside a security expression.

### With enums

Suppose `ExportMode` is an enum with `SUMMARY` and `RAW`; in SpEL you can reference the class via `T(com.example.ExportMode).RAW`:

```java
@PreAuthorize(
    "hasAuthority('report:export:raw') and "
    + "#request.mode == T(com.example.ExportMode).RAW"
)
public void exportRaw(ExportRequest request) { }
```

Replace package/type with the real class in your project and verify controller parsing. The caller choosing RAW does not bypass the resource policy on the report.

## 14. @PreFilter is not @PreAuthorize

`@PreFilter` is a different interceptor used to **filter an input collection** before the method body runs, rather than simply deciding ALLOW/DENY for the entire method.

Example per Spring Security documentation:

```java
@PreFilter("filterObject.owner == authentication.name")
public void updateAccounts(
        java.util.Collection<Account> accounts) {
    // Passed-in collection has been filtered by the filter expression.
}
```

`filterObject` is the element currently being inspected, not the whole `accounts` collection. For Maps, `filterObject.value` may be used depending on structure.

**Warnings for sensitive commands:**
- If the caller submits Account DTOs with a self-declared `owner`, filtering on that field does not prove DB ownership.
- A bulk operation may require **all-or-nothing** semantics; silently dropping unauthorized elements and updating the rest can violate the contract.
- For large lists, in-memory filtering is costly; verify the ID set against tenant/ACL at the data layer instead.
- Prefiltering mutates/replaces the collection seen in the method; test mutation/return contracts per collection type.
- Do not use `@PreFilter` as the default fix for every BOLA issue.

A safer bulk command queries all entities by ID and tenant, verifies **the full count matches**, checks permissions per entity, and updates within one transaction. If any ID is missing, the whole operation fails with DENY/CONFLICT per contract.

## 15. @PostAuthorize also inspects objects but at a different time

Example:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView readDocument(long id) {
    return repository.getView(id);
}
```

`returnObject` is the result **after** the method. Contrast with:

```java
@PreAuthorize("#command.documentId != null")
public void rename(RenameDocumentCommand command) { }
```

In a pre-check, you have inputs but **no returnObject yet**; in a post-check, the body has already executed. Spring Security docs discourage using `@PostAuthorize` as the primary guard for DB-writing classes because side effects may already have occurred.

Wrong example:

```java
@PostAuthorize("denyAll()")
public void approveTransfer(ApproveTransferCommand command) {
    paymentGateway.sendMoney(command.getTransferId());
}
```

The method may already have sent money before being DENIED. DB transaction rollback does not necessarily undo external side effects. For writes requiring authorization before change, check policies against real state and manage concurrency.

## 16. TOCTOU: a pre-check valid at T1 may no longer hold at T2

Scenario:

```text
T1  @PreAuthorize:
    @documentAccess.mayRename(actor, command.docId) == true
         |
         | Another transaction transfers owner/locks the document.
         v
T2  Method body:
    repository.renameById(command.docId, command.newTitle)
         |
         v
    Permission expired or state became invalid.
```

This is **time-of-check/time-of-use**. `@PreAuthorize` does not automatically guarantee a database snapshot or lock is held until the update.

Mitigations:
1. Place the final check right next to the operation inside the transaction.
2. Load the object scoped to the tenant and lock/read its version when appropriate.
3. Apply optimistic locking `@Version` or conditional updates.
4. Never treat an untrusted input property as proof of ownership.
5. Never trigger external side effects before full authorization and policy checks commit.
6. Handle `affected rows = 0` as conflict/deny/not-found, never success.

Conditional update example for owner-only:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant_id
  AND owner_id = :authenticated_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

The condition must pull `trusted_tenant_id` and `authenticated_actor_id` from server context, **not** from caller-claimed properties. This illustrative SQL does not replace ACL/delegation if business rules permit non-owners to edit.

## 17. Null errors, typing, and overly clever expressions

A fragile expression:

```java
@PreAuthorize(
    "#request.options.format.toUpperCase() == 'CSV'"
)
```

If `request`, `options`, or `format` is null, SpEL/runtime errors can occur. If a getter performs I/O or throws exceptions, the pre-check can also fail before the body.

Clearer form:

```java
@PreAuthorize(
    "#request != null and #request.options != null and "
    + "#request.options.format != null and "
    + "#request.options.format.equalsIgnoreCase('CSV')"
)
```

Even so, **input validation** must still decide whether case-insensitive CSV, other values, or blanks are acceptable. Having SpEL check case-insensitively while the controller parses a case-sensitive enum can create two conflicting interpretations.

Common errors:
- `#request` unresolved due to missing `-parameters`.
- `#request.owner` misspelled JavaBean property.
- `#request.amount` is a `String` compared as a number.
- `authentication.name` is an email while `ownerId` is a UUID.
- `#request.tags.contains(...)` invoked on a null list.
- `#request.items.size()` without checking permission per item.
- An overloaded method with different parameter types where a copied annotation is invalid.
- Expression bean `@policy` does not exist or method is non-public/inaccessible per config.
- Exceptions in a policy bean caught and turned into `true` or bypassed; must fail closed.

When branching logic grows complex, move it into a Java `@Component("policy")` to unit-test and handle nulls/exceptions cleanly.

## 18. Role hierarchy and input properties are two separate concerns

A role hierarchy might define:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

An actor with `ROLE_ADMIN`, when the manager is wired with the hierarchy, can pass `hasRole('USER')`. Yet:

```java
@PreAuthorize(
    "hasRole('USER') and #command.ownerId == authentication.name"
)
```

is still unsafe if `ownerId` is client-supplied. Role inheritance only expands reachable authorities; it **does not verify actual object data**.

In multi-tenant systems, never let `ROLE_ADMIN` in tenant A automatically gain access to tenant B objects. Create explicit tenant-wide capabilities if business-approved, while domain policies still verify resource tenant and state.

## 19. HTTP is not the only path calling the service

Placing `@PreAuthorize` on a service is beneficial because the same use case may be invoked from:
- REST controllers;
- GraphQL resolvers;
- message listeners;
- background jobs/schedulers;
- admin consoles;
- other Spring services.

However, every call must go through the Spring proxy/advisor (or appropriate AspectJ configuration). `this.rename(command)` inside the same class can bypass the method-security interceptor under AOP proxies. Objects created via `new` are not protected either.

Across different entry points, the actor context must be trustworthy. A job without an HTTP principal must not bypass policy; use an appropriate service identity/permission scope. If business commands can be invoked outside the method-security boundary, service/domain guards are a mandatory safety layer.

Placing `@PreAuthorize` on a controller is also an option, yet if another controller, job, or message handler calls the service directly, the controller rule will not apply. Pick the main **boundary** at the use case and test every entry point.

## 20. Standalone Java 17+: self-claimed input vs. database object

The following example is a **plain Java simulation** of pre-authorization and resource policy; it does not use Spring Security. The goal is to see why comparing `claimedOwner` from the request is wrong, while loading the real object and checking trusted tenant/owner/permission yields a different decision.

Save `InputPropertyAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class InputPropertyAuthorizationDemo {

    record Actor(String id, String tenant, Set<String> permissions) {}
    record Command(long documentId, String claimedOwner,
                   String claimedTenant, String newTitle) {}
    record Document(long id, String tenant, String owner,
                    boolean locked) {}

    static boolean naivePreCheck(Actor actor, Command command) {
        return actor.permissions().contains("doc:write")
            && actor.id().equals(command.claimedOwner())
            && actor.tenant().equals(command.claimedTenant());
    }

    static String safeDecision(
            Actor actor, Command command, Map<Long, Document> database) {
        if (!actor.permissions().contains("doc:write")) {
            return "DENY permission";
        }
        if (command == null || command.newTitle() == null
                || command.newTitle().isBlank()) {
            return "DENY input";
        }

        Document real = database.get(command.documentId());
        if (real == null) {
            return "DENY not-found";
        }
        if (!actor.tenant().equals(real.tenant())) {
            return "DENY tenant";
        }
        if (real.locked()) {
            return "DENY locked";
        }

        boolean owner = actor.id().equals(real.owner());
        boolean tenantGrant =
            actor.permissions().contains("doc:write:tenant");
        if (!owner && !tenantGrant) {
            return "DENY owner";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Map<Long, Document> db = Map.of(
            42L, new Document(42, "A", "alice", false),
            43L, new Document(43, "A", "alice", true),
            99L, new Document(99, "B", "carol", false)
        );

        Actor alice = new Actor(
            "alice", "A", Set.of("doc:write"));
        Actor bob = new Actor(
            "bob", "A", Set.of("doc:write"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "doc:write", "doc:write:tenant"));
        Actor reader = new Actor(
            "reader", "A", Set.of("doc:read"));

        Command forgedOwner = new Command(
            42, "bob", "A", "Forged title");
        Command wrongClaim = new Command(
            42, "bob", "A", "Valid title");
        Command otherTenant = new Command(
            99, "bob", "A", "Different tenant");
        Command locked = new Command(
            43, "manager", "A", "Cannot edit");
        Command missing = new Command(
            777, "manager", "A", "Does not exist");
        Command blank = new Command(
            42, "manager", "A", "");

        System.out.println("Forged owner naive: "
            + naivePreCheck(bob, forgedOwner));
        System.out.println("Forged owner safe: "
            + safeDecision(bob, forgedOwner, db));
        System.out.println("Owner claim mismatch naive: "
            + naivePreCheck(alice, wrongClaim));
        System.out.println("Owner claim mismatch safe: "
            + safeDecision(alice, wrongClaim, db));
        System.out.println("Cross-tenant safe: "
            + safeDecision(bob, otherTenant, db));
        System.out.println("Tenant grant safe: "
            + safeDecision(manager, forgedOwner, db));
        System.out.println("Locked safe: "
            + safeDecision(manager, locked, db));
        System.out.println("Read-only safe: "
            + safeDecision(reader, forgedOwner, db));
        System.out.println("Missing document safe: "
            + safeDecision(manager, missing, db));
        System.out.println("Blank title safe: "
            + safeDecision(manager, blank, db));
    }
}
```

Compile and run on JDK 17+:

```bash
javac InputPropertyAuthorizationDemo.java
java InputPropertyAuthorizationDemo
```

**Exact** stdout:

```text
Forged owner naive: true
Forged owner safe: DENY owner
Owner claim mismatch naive: false
Owner claim mismatch safe: ALLOW
Cross-tenant safe: DENY tenant
Tenant grant safe: ALLOW
Locked safe: DENY locked
Read-only safe: DENY permission
Missing document safe: DENY not-found
Blank title safe: DENY input
```

Interpretation:
1. Bob has `doc:write` and claims `claimedOwner=bob` and tenant A, so **naive is true** even though real document 42 belongs to Alice. This is a dangerous false positive.
2. The safe policy looks up document 42 and denies Bob because he is neither the owner nor holds a tenant grant.
3. Alice is the real owner even when the client mistakenly claims Bob; naive returns false while safe returns ALLOW. This shows client claims are **not the source of truth**.
4. Bob cannot modify a tenant B document even if claiming tenant A.
5. Manager has an **explicitly granted** tenant-wide permission so they can edit a document in the same tenant, yet cannot bypass state checks.
6. Locked documents are still DENIED.
7. Reader with only read permission cannot write.
8. Nonexistent IDs are denied.
9. Blank titles are rejected before operations run.

**Demo limitations:** `Map` is a mock database, `Actor` is a test fixture, and `safeDecision` uses no real Authentication/JPA/transactions/locking and mutates no state. Never copy `naivePreCheck` into production. In a real system, the actor must come from a trusted security context and data queries must use tenant scoping with appropriate transactions/conditional updates.

## 21. Unit testing multi-property policies

When separating policy logic from annotations, write direct unit tests:

```java
@Test
void editorCannotRenameDocumentOwnedByOtherUser() {
    Actor actor = actor("bob", "tenant-A", "document:rename");
    Document doc = document(42L, "tenant-A", "alice", "DRAFT");

    assertThat(policy.canRename(actor, doc)).isFalse();
}

@Test
void editorCannotRenameCrossTenantDocument() {
    Actor actor = actor("alice", "tenant-A", "document:rename");
    Document doc = document(99L, "tenant-B", "alice", "DRAFT");

    assertThat(policy.canRename(actor, doc)).isFalse();
}

@Test
void ownerCannotRenameLockedDocument() {
    Actor actor = actor("alice", "tenant-A", "document:rename");
    Document doc = document(43L, "tenant-A", "alice", "LOCKED");

    assertThat(policy.canRename(actor, doc)).isFalse();
}
```

`actor`, `document`, and `policy` are **custom test fixtures/domain APIs**, not built-in Spring classes. These are JUnit 5/AssertJ snippets in a project that already has the dependencies.

Test coverage should at minimum include:
- Null inputs and null properties.
- Negative/empty/nonexistent IDs.
- Wrong tenant with right owner, and vice versa.
- Right authority without ownership.
- Owner without authority.
- High role without scoped grant.
- LOCKED/ARCHIVED states.
- Duplicate IDs, batch requests, and unauthorized elements.
- Forged command fields `claimedOwnerId`/`tenantId`/`approvedBy`.
- Concurrent/version changes prior to update.

## 22. Integration test: does @PreAuthorize run before the body?

With Spring Test, call the service bean through the proxy using `@WithMockUser` or request post-processors:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DocumentCommandSecurityTest {

    private DocumentCommandService service; // Injected from Spring context

    @Test
    @WithMockUser(authorities = {"document:read"})
    void readOnlyUserDeniedBeforeRename() {
        RenameDocumentCommand cmd =
            new RenameDocumentCommand(42L, "New title");

        assertThatThrownBy(() -> service.rename(cmd))
            .isInstanceOf(
                org.springframework.security.access.AccessDeniedException.class
            );
    }
}
```

This is an **illustrative test snippet**: in a real project use `@SpringBootTest`/`@ContextConfiguration`, `@Autowired` for the service bean, fixtures, and entity/transaction repositories. Never use `new DocumentCommandService(...)` when testing interception.

Also verify `repository.save/rename` **is not invoked** when pre-authorize DENIES. When the role suffices yet owner differs, verify the in-service policy denies and the DB remains unchanged.

**False positive:** An HTTP POST test receiving 403 due to a missing CSRF token does not prove `@PreAuthorize` or ownership policy ran. With MockMvc and CSRF enabled, supply a valid token on write requests and verify the exact checkpoint.

## 23. Testing parameter names: do not test only single-parameter methods

Example:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void rename(String auditReason, RenameDocumentCommand command) {
    // ...
}
```

If compiled without `-parameters`, `#command` may fail to resolve; if positional `#p0` is used, it points to `auditReason` instead. The impact can be unexpected denial or misconfiguration.

Tests should:
- Call through the Spring proxy using the real production build toolchain.
- Enable `-parameters` or use explicit `@P("command")`.
- Test overloads with multiple parameters.
- Test interface methods whose `@P` differs from the implementation.
- Test null data.
- If the app uses Kotlin, verify metadata/compiler and final-class proxying per version.
- Never fix parameter-binding bugs by switching SpEL to parse raw request bodies.

## 24. MockMvc: combining HTTP and method security properly

Example request:

```http
PATCH /api/documents/42
Content-Type: application/json

{"newTitle":"Title", "claimedOwnerId":"alice"}
```

A proper test needs:
- An actor authenticated with authority `document:rename`.
- A CSRF token if session-based security is enabled.
- An entity in the DB with a specific owner/tenant.
- Sending a `claimedOwnerId` **different from** the entity owner to test over-posting.
- Asserting 403/404 status per contract.
- Asserting the document in the DB is unchanged.
- Asserting the service policy checks the real resource owner, not only the DTO.

Example snippet:

```java
// Requires MockMvc, spring-security-test, document 42 fixture,
// real PATCH controller, and appropriate CSRF configuration.
mvc.perform(patch("/api/documents/42")
        .with(user("bob").authorities(
            new SimpleGrantedAuthority("document:rename")
        ))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"newTitle":"Forged","claimedOwnerId":"bob"}
            """))
   .andExpect(status().isForbidden());
```

In a real project imports include `patch`, `user`, `csrf`, `status`, `MediaType`, and `SimpleGrantedAuthority`. If the API uses stateless JWT with CSRF disabled by design, test setup differs; never use a fake CSRF token to “fix” authorization.

Include a control ALLOW test for the authorized owner so you have proof the DENY response is not caused by a missing route or failed authentication.

## 25. Property-based testing for DTO authorization

A fixed test suite easily misses variants:
- Variations in query casing/whitespace before DTO binding.
- Missing or null `ownerId`/`tenantId` fields.
- Empty maps/lists or collections containing cross-tenant IDs.
- Nested objects null at different depths.
- Negative/huge amounts or precision exceeding limits.
- Nonexistent enum modes or changed defaults.
- Payloads with extra fields (mass assignment).
- Immutable vs. mutable DTOs with setters mutated after pre-check.
- Controller and service parsing the same format differently.
- Resource ownership changing between T1 pre-check and T2 write.

Property tests you can write:
1. For any actor lacking functional permission, the command must be DENIED.
2. For any document outside the verified tenant, the command must be DENIED regardless of client claims.
3. For any locked document, write commands must be DENIED.
4. For any command missing required fields, no side effects may occur.
5. For a RAW capability, a user holding only SUMMARY cannot trigger RAW via any mode alias.
6. Changing client `claimedOwner`/`claimedTenant` **must not alter the decision** when server-side actor/resource remain unchanged.

**Strongest proof against IDOR:** swap the ID to a resource owned by another user/tenant on the same endpoint, set arbitrary remaining fields under attacker control, and verify **no data is leaked or modified**.

## 26. Security expression errors and diagnostics

Reasons a method may not run:
- Missing `@EnableMethodSecurity` so annotations have no effect.
- Bean invoked without passing through the proxy.
- `#command` not found due to parameter metadata.
- Misspelled or null getter/property.
- `@documentPolicy` bean misnamed or missing.
- Custom policy throws an exception on DB errors.
- Authentication lacks the required authority.
- Role hierarchy not wired to the expression handler.
- Real owner/tenant policy legitimately denied access.
- Method-level annotation overrides class-level rule unexpectedly.
- Another `@PostAuthorize`/advisor denies after the body.
- An exception handler translates the authorization exception to a different response.

Do not deduce an error in `#command` from a single HTTP 403. When testing:
1. Record direct authorities and actor identity (without logging tokens).
2. Check compiler `-parameters` or `@P`.
3. Verify the method runs through the Spring proxy.
4. Unit-test SpEL/policy beans with fixtures.
5. Verify the right resource owner/tenant was loaded.
6. For writes, assert DB and external side effects remain unchanged on DENY.

Do not place raw JWTs, passwords, payment details, or sensitive content into logs; safely audit actor ID, action, resource ID, and reason codes.

## 27. When should input properties NOT be checked inside annotations?

Some cases belong largely or wholly in a domain service:
- Permissions depend on recently mutated DB data.
- Multiple resources must be checked inside one transaction.
- Ownership, ACLs, tenant inheritance, delegation, and complex workflows exist.
- Commands require locking/versioning and consistent invariants.
- Logic involves amounts and limits that can change between requests.
- “Cannot self-approve” policies require comparing against the true creator.
- Detailed decision reasons/audits must be returned.
- The exact same logic must run across HTTP, GraphQL, schedulers, and message consumers.
- The SpEL expression has become long and hard to test.

Simple example:

```java
@PreAuthorize("hasAuthority('payment:approve')")
@Transactional
public void approve(ApprovePaymentCommand command) {
    Actor actor = actors.requireAuthenticatedActor();
    Payment payment = payments.findForUpdateInTenant(
        command.getPaymentId(), actor.activeTenantId()
    ).orElseThrow(PaymentNotFoundException::new);

    policy.requireCanApprove(actor, payment);
    payment.approveBy(actor.id());
}
```

This snippet requires domain contracts, not standalone Java. Even if the client sends `approvedBy` or `creatorId`, those fields must not drive final decisions; the policy uses stored values and the trusted principal.

## 28. Anti-patterns and fixes table

| Anti-pattern | Why it is dangerous | Proper approach |
| --- | --- | --- |
| `#dto.ownerId == authentication.name` | `ownerId` can be forged by the client | Load real owner from DB |
| `#dto.tenantId == principal.tenantId` | Document ID may belong to another tenant | Query entity scoped to verified tenant |
| Only `#ids.size() <= 100` for bulk delete | Does not check permission per ID | Load/scope and authorize every object |
| Only `hasRole('ADMIN')` then update by ID | Skips tenant/owner/ACL/state | Scoped domain policy |
| `@PostAuthorize` on writes as primary guard | Method may already have written data | Pre-check + transactional guard |
| DTO getters with side effects | Impure security expression | Immutable/pure-data DTOs |
| Assuming `authentication.name` is a UUID | Identity format can differ | Actor resolver and normalized ID |
| Not enabling `-parameters` | `#command` fails to resolve | Compiler flag/`@P` and tests |
| SpEL dereferencing nested properties without null checks | Unexpected evaluation exceptions | Null guards, validation, policy beans |
| Catching policy errors and returning true | Fail-open | Fail-closed + proper exception handling |
| Over-posting role/admin/owner fields | Client alters its own privileges | DTO allowlists + domain invariants |
| Policy only on controllers | Jobs/GraphQL can bypass | Use-case policies |
| Service calling `this.securedMethod()` | Proxy advice may not run | Protect boundaries and domain guards |
| Testing 403 without CSRF | False positive | Valid request and verify exact DENY point |
| Large multi-branch expressions | Hard to review, diverges from body | Testable Java `@Component` policy |
| DB check in pre-expression followed by delayed write | TOCTOU | Check close to point of use, versions/locks |
| Testing only low roles missing authority | Misses IDOR/BOLA | Test actors with valid role yet wrong owner/tenant |

## 29. Pre-merge checklist for @PreAuthorize on input objects

1. Is the service method Spring-managed and invoked through a proxy?
2. Is `@EnableMethodSecurity` enabled in the actual context?
3. Is the annotation on a method, class/interface, or meta-annotation, and are there overrides?
4. Does `#command` resolve via `-parameters`/`@P`?
5. Do DTO JavaBean property names match accurately?
6. Are null/nested properties handled safely?
7. Is the input condition a **functional requirement** or mistakenly acting as proof of authorization?
8. Are Authentication/principal verified and normalized into a stable Actor?
9. Are payload owner/tenant/role fields ever mistakenly trusted as DB truth?
10. Does the method body use the exact checked value rather than an alias/default?
11. Are there complex collections/maps/enums that warrant a policy bean?
12. Is authorization applied to **every object** in bulk requests?
13. Is tenant membership verified against real membership records?
14. Are resource scope queries and ACL/owner checks in place?
15. Do data-mutating commands verify conditions right before side effects?
16. Have TOCTOU risks, locking/versioning, or conditional updates been addressed?
17. Do HTTP and non-HTTP calls to the method enforce the same policy?
18. Have you tested an attacker forging `ownerId`/`tenantId`/`approvedBy` in the DTO?
19. Have you tested null, malformed, nested-null inputs, and method overloads?
20. Have you tested a user with the right role in a different tenant/owner?
21. Have you tested the right owner missing the required authority?
22. Have you verified state remains unchanged after DENY?
23. Do HTTP tests rule out CSRF/404/405 as false causes?
24. Do errors and logs keep resource data confidential?
25. Can the policy be explained and reviewed using concrete permission names?

### Self-check questions

**Q1.** Is `@PreAuthorize("#command.ownerId == authentication.name")` enough to protect document ownership?  
→ **No**, if `ownerId` is client-supplied. Compare against the real document owner and tenant scope.

**Q2.** The Java parameter is named `command`, yet SpEL `#command` is null in Spring Framework 6.1+; what should you check?  
→ Compiler `-parameters`, `@P("command")`, interface/method signatures, and runtime argument binding.

**Q3.** Can `#command.options.format` be used to gate RAW export permissions?  
→ **Yes**, if the input is parsed/validated consistently, the body strictly honors that mode, and the actual report still passes domain policies.

**Q4.** Is `@PreFilter("filterObject.owner == authentication.name")` equivalent to DENYING the entire bulk operation when one account is unauthorized?  
→ **No**. It filters elements; for all-or-nothing, validate the entire set.

**Q5.** Does `hasRole('ADMIN')` or a role hierarchy prove an object belongs to the admin's tenant?  
→ **No**. Tenant/resource scope must be checked separately.

**Q6.** A pre-check queried the DB and saw owner Alice, then ownership changed before the update. Is authorization guaranteed to remain valid?  
→ **No**. Use appropriate transactions, locks/versions, or conditional updates.

**Q7.** Does `authentication.name` always equal a UUID `ownerId` in the DB?  
→ **No**. Normalize identity from the trusted principal.

**Q8.** If a method has `@PreAuthorize` yet is called via `this.method()` in the same bean, is advice guaranteed to run?  
→ **No** under standard proxy AOP. Verify boundaries and enforce mandatory domain guards.

**Q9.** Does a POST test returning 403 without a CSRF token prove `@PreAuthorize` DENIED it?  
→ **No**. Distinguish `CsrfFilter` from method security.

**Q10.** What is the best test to catch IDOR with DTOs?  
→ An actor with valid authority submits another user's/tenant's resource ID, forges arbitrary owner/tenant fields, and verifies zero data leaks or side effects.

## Conclusion

`@PreAuthorize` can use SpEL to inspect input object properties via `#command.property`, classify requests, and call policy beans **before the method body executes**. However, client-submitted DTOs, path IDs, ownerId, tenantId, status, or roles **are not authorization evidence**. Safe design combines **functional authorities from a trusted Authentication**, **semantically validated input properties**, **server-sourced entity/tenant/owner/ACL checks**, **policies enforced at the point of data use**, and **negative tests even when the caller holds the required role**. When logic is complex or mutates state, move decisions into transactional service/domain policies rather than relying solely on a short SpEL expression.

## Official References

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PreAuthorize`, `MethodSecurityExpressionHandler`, method parameters, bean authorization, `@PreFilter`, and `@PostAuthorize`.
2. [Spring Security 6.5 — Authorization Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html) — `-parameters` compiler requirement after Spring Framework 6.1 removed LocalVariableTableParameterNameDiscoverer.
3. [Spring Security 6.5 — Method Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` and testing method interception.
4. [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — authorities, roles, and policies.
5. [Spring Security 6.5 — Domain Object Security (ACL)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — object permissions and `PermissionEvaluator`.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP security and its distinct scope from method security.
