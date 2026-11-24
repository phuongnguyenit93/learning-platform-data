# Meta-Annotations for Readable, Reusable Policy Names

## 1. The Problem: Correct Expressions That Make Business Code Hard to Read and Maintain

In Spring Security, method security allows declaring:

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView getInvoice(long invoiceId) { ... }

@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #invoiceId)")
public void approveInvoice(long invoiceId) { ... }
```

These expressions can be valid, yet when a system has hundreds of service methods, repeating them makes code harder to read and causes policy drift: one place checks tenant, another forgets; one uses `ROLE_MANAGER`, another uses `invoice:approve`; when a rule changes, many locations must be hunted down.

**Security meta-annotations** let you give a business-meaningful Java name to an authorization expression. Instead of reading long SpEL in every service, readers see:

```java
@RequiresInvoiceReadPermission
public InvoiceView listSummary() { ... }

@CanReadInvoice
public InvoiceView getInvoice(long invoiceId) { ... }

@CanApproveInvoice
public void approveInvoice(long invoiceId) { ... }
```

All names above are **project-defined illustrative names**; Spring Security does not ship these business annotations out of the box. Inside the annotation, you must attach a security annotation understood by method security, such as `@PreAuthorize` or `@PostAuthorize`.

Key point to remember: **renaming does not automatically create a safe policy**. If `@CanReadInvoice` internally only checks `invoice:read` without checking tenant/owner, its name **promises too much** compared to its behavior. Good meta-annotations make policies readable, reusable, and testable; bad meta-annotations can hide vulnerabilities behind a reassuring name.

### Before and After

```text
BEFORE:
@PreAuthorize("hasAuthority('invoice:read') and " +
  "@invoicePolicy.canRead(authentication, #invoiceId)")
InvoiceView find(long invoiceId);

AFTER:
@CanReadInvoice
InvoiceView find(long invoiceId);

CENTRALIZED DEFINITION:
@CanReadInvoice
  => @PreAuthorize(
       "hasAuthority('invoice:read') and " +
       "@invoicePolicy.canRead(authentication, #invoiceId)"
     )
```

The desired outcome is **a single clear source of policy definition**, not turning every arbitrary expression into opaque abstract annotation names that are hard to trace.

## 2. How Do Meta-Annotations Work?

Java allows placing an annotation on the definition of another annotation. An annotation used to annotate another annotation is called a **meta-annotation**. Spring Security can discover method security annotations through this structure.

A minimal example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface IsAdmin {
}
```

When you write:

```java
@IsAdmin
public void viewAudit() {
    // Business logic
}
```

Spring Security method security can discover `@PreAuthorize` **through** `@IsAdmin` and evaluate `hasRole('ADMIN')` before running the method.

Model:

```text
Service method
     |
     | @IsAdmin
     v
@IsAdmin definition
     |
     | @PreAuthorize("hasRole('ADMIN')")
     v
Method-security pointcut + interceptor
     |
     | Authentication / authorities
     v
Permit or Deny
     |
     v
Execute method if permitted
```

This is a **security annotation discovery** mechanism, not a replacement of `@PreAuthorize` with a new system. Execution still goes through Spring Security's authorization manager/interceptor and has the same Spring AOP boundaries.

### 2.1. Important Java Elements

| Element | Role | If Missing/Wrong |
| --- | --- | --- |
| `public @interface X` | Declares custom annotation type | No reusable type |
| `@Target(METHOD)` | Allows placement on methods | Cannot be placed on methods |
| `@Target(TYPE)` | Allows placement on classes/interfaces | Cannot be placed on classes |
| `@Retention(RUNTIME)` | Retains annotation for runtime framework discovery | Other retention policies can hide it from interceptors |
| `@PreAuthorize(...)` | Security rule carried inside the meta-annotation | Pretty name with no pre/post check |
| `@Documented` (optional) | Shows annotation in JavaDoc | Does not affect authorization |
| `@Inherited` (case-dependent) | Java class-annotation inheritance rule | Does not replace Spring's annotation lookup algorithm |
| `@EnableMethodSecurity` | Enables method authorization | Meta-annotations do not enable method security by themselves |

In Java, each `public @interface` is normally placed in **a separate `.java` file of the same name**. Code snippets below are fragments of a Spring project; do not concatenate all public types into a single Java file and run `javac` as a standalone program.

### 2.2. Minimum Conditions for the Annotation to Take Effect

- Compatible Spring Security method authorization dependency is present.
- `@EnableMethodSecurity` is present in Spring configuration; Spring Boot Starter Security **does not automatically enable method security**.
- The matching annotation group is enabled: `@PreAuthorize` and `@PostAuthorize` belong to `prePostEnabled=true` by default; `@Secured` needs `securedEnabled=true`; `@RolesAllowed`/`@PermitAll`/`@DenyAll` need `jsr250Enabled=true`.
- The method belongs to a Spring-managed bean and calls actually pass through the appropriate proxy/advice.
- `Authentication` and related policy beans exist with trustworthy data.
- Tests prove unauthorized calls are denied **before executing side effects**.

Creating `@CanReadInvoice` while forgetting `@EnableMethodSecurity` does not mean "deny by default". It may become a plain Java annotation never processed by any method-security interceptor.

## 3. Design Policy Names Before Writing Code

A good annotation name must state accurately **the exact condition it guarantees**.

| Illustrative Name | Appropriate Meaning | Risk of Misnaming |
| --- | --- | --- |
| `@RequiresInvoiceReadPermission` | Caller holds `invoice:read` authority | Does not promise tenant/owner checks |
| `@CanReadInvoice` | Caller may read **specific invoice by ID** with functional permission and object policy | Should not check only a role |
| `@CanApproveInvoice` | Sufficient permission and resource-level approval conditions | May need state re-check at write time |
| `@IsFinanceAdmin` | Holds properly mapped finance-domain admin role | Does not imply admin across all tenants |
| `@MayViewAuditTrail` | Permitted to view audit trail within scope | Do not use bare `authenticated()` |
| `@PublicCatalogRead` | Only truly public catalog read operations | Must not be extended to every API in the service |

Good names usually follow one of these patterns:

- **RequiresXPermission:** functional authority guard, makes no object promise.
- **CanXResource:** guard bound to real parameters/resources and matching policy.
- **RequiresSpecificRole:** role guard; pay attention to `ROLE_` prefix and role scope.
- **MayXUnderCondition:** composite guard with business conditions; requires targeted tests.

Avoid vague names like `@Secure`, `@Trusted`, `@Internal`, or `@Authorized` without clear contracts. They make it hard for reviewers to see **which** policy is enforced and can cause others to over-assume.

### 3.1. Should Every Expression Be Turned Into an Annotation?

No. A simple, readable, one-off expression can stay inline:

```java
@PreAuthorize("hasAuthority('audit:read')")
public List<AuditView> list() { ... }
```

Meta-annotations bring the most value when:

1. A rule is **repeated** across multiple services;
2. The rule represents a **stable business concept**;
3. Multiple developers need to use **the exact same definition**;
4. The policy has multiple conditions that are error-prone when copy-pasted;
5. You want to centralize testing, review, and auditing of the policy.

Do not create hundreds of annotations just to turn a one-line string into a one-line name. The goal is reducing **policy drift** and improving expressiveness.

## 4. Fixed Meta-Annotations with `@PreAuthorize`

### 4.1. Functional Permission: Complete Single-File Annotation Example

File `RequiresInvoiceReadPermission.java`:

```java
package example.security.policy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('invoice:read')")
public @interface RequiresInvoiceReadPermission {
}
```

Used in a Spring-managed service:

```java
@Service
public class InvoiceQueryService {

    @RequiresInvoiceReadPermission
    public List<InvoiceSummary> listOwnInvoices() {
        // Repository must still filter by tenant and owner.
        return repository.findVisibleForCurrentActor();
    }
}
```

With `@EnableMethodSecurity`, this method requires the `invoice:read` authority to be invoked. However, the annotation only verifies **functional permission**. Filtering in `repository.findVisibleForCurrentActor()` must rely on a verified principal/tenant, not an arbitrary client parameter.

If it were named `@CanReadAnyInvoice`, the internal logic would contradict the promise: having permission to read invoices does not mean reading every invoice. Rename or add an object policy to match.

### 4.2. Role Guard: `IsFinanceAdmin` Example

File `IsFinanceAdmin.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('FINANCE_ADMIN')")
public @interface IsFinanceAdmin {
}
```

Under the default role prefix, `hasRole('FINANCE_ADMIN')` checks for `ROLE_FINANCE_ADMIN`. If the application receives groups/roles from an IdP, a trustworthy mapping to application authorities is required; never grant admin roles from raw headers or unverified claims.

If a finance admin only manages one tenant, this annotation does not enforce tenant boundaries yet. Do not slap it onto global read methods treating it as a "superuser pass".

### 4.3. Define Once, Use Multiple Times

Example of one policy serving REST, batch, and admin workflows:

```java
@RequiresInvoiceReadPermission
public InvoiceSummary fetchSummary(long id) { ... }

@RequiresInvoiceReadPermission
public InputStream exportVisibleInvoices() { ... }

@RequiresInvoiceReadPermission
public InvoiceStats calculateStats() { ... }
```

All three share the same functional authority, yet carry **different data risks**. Exporting may need a separate `invoice:export` permission; company-wide statistics may need `invoice:aggregate`. Do not abuse reuse by applying a weaker policy to stronger actions.

Practical rule: **reuse a policy name when operations genuinely share the exact same requirements**, not merely because they live in the same module.

## 5. Object-Level Policy: Combining Permission and Business Bean

Meta-annotations are especially valuable when an expression combines a permission, parameters, and a policy bean. Still, the code pattern must ensure parameters are resolved accurately and the bean performs trustworthy checks.

### 5.1. Defining `@CanReadInvoice`

File `CanReadInvoice.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public @interface CanReadInvoice {
}
```

Why `@Target(METHOD)` instead of `TYPE`? The expression requires the `#invoiceId` parameter. Placing the annotation on an entire class with varied method signatures can break methods lacking that variable and make the policy unreliable. Narrowing the target prevents misapplication.

Used in the service:

```java
@Service
public class InvoiceService {

    @CanReadInvoice
    public InvoiceView readInvoice(long invoiceId) {
        return repository.findVisibleInvoice(invoiceId);
    }
}
```

The code above **is an integration fragment**, requiring repository and domain type declarations in the project. A sound design also queries in the repository with proper tenant and permission conditions rather than relying solely on the policy check beforehand.

### 5.2. Policy Bean with Trustworthy Identity

Illustrative intent of `invoicePolicy`:

```java
@Component("invoicePolicy")
public class InvoicePolicy {

    private final InvoiceRepository repository;

    public InvoicePolicy(InvoiceRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            Authentication authentication, long invoiceId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        // Identity/tenant must come from the verified principal.
        VerifiedActor actor = VerifiedActor.from(authentication);
        if (actor == null || !actor.active()) {
            return false;
        }

        return repository.existsReadableInvoice(
            invoiceId, actor.tenantId(), actor.userId()
        );
    }
}
```

Illustrative code uses application classes such as `InvoiceRepository` and `VerifiedActor`; they must be implemented with safe contracts in the project. `AnonymousAuthenticationToken` must be imported from `org.springframework.security.authentication.AnonymousAuthenticationToken`, and `Authentication` from `org.springframework.security.core.Authentication`.

**Important:** `authentication.isAuthenticated()` alone is not enough to reject anonymous authentication in every configuration; check principal state per policy. Never use `(String) authentication.getPrincipal()` or `request.getHeader("X-Tenant-Id")` to fabricate a verified tenant.

If the repository checks first and the service writes later, a race condition can occur; for state-modifying actions, use **conditional writes/versioning/transactions** at the data layer.

### 5.3. SpEL Parameter Names and `-parameters`

In `#invoiceId`, Spring must know the Java parameter name at runtime. With Spring Framework 6.1+ and common name-discovery paths, compiling with `-parameters` is necessary to preserve parameter names:

```bash
javac -parameters ...
```

In Maven/Gradle, configure the compiler plugin or toolchain to retain parameter names for source compiled with method security. If you prefer not to rely on compiler-supplied Java parameter names, consider Spring Security's `@P("invoiceId")` or a parameter contract supported in your version. Test against the project's actual compiled bytecode, not only IDE mocks.

Renaming `invoiceId` to `id` in a method while forgetting to update the expression can cause runtime errors or unexpected denials. **A meta-annotation depending on parameter names is an internal API contract** that must be versioned and covered by integration tests.

### 5.4. Contextual Naming Is Insufficient When the Same ID Exists Across Tenants

If `invoiceId=42` can collide across two tenants, the policy needs the verified tenant. An expression like:

```java
@PreAuthorize("@invoicePolicy.canRead(#invoiceId)")
```

is not clear enough if `canRead` reads tenant from a client-supplied payload. Better yet, the policy uses the authenticated `Authentication` and queries combining `invoiceId`, tenant, owner/shares/roles; never trust a meta-annotation's name while ignoring server data.

An invoice may be "readable" in several cases: owner, share recipient, assigned reviewer, or tenant admin. Write OR branches inside the policy wrapped by invariant AND tenant/state conditions, e.g.:

```text
canReadInvoice =
  has(invoice:read)
  AND sameTenant
  AND (isOwner OR isValidShareRecipient OR isAssignedReviewer)
```

Do not accidentally write:

```text
(has(invoice:read) AND sameTenant AND isOwner)
OR isAssignedReviewer
```

unless reviewers are intentionally allowed to bypass permissions and tenant boundaries, which warrants special review.

## 6. Parameterized Meta-Annotations: Controlled Use of Templates

Fixed meta-annotations are convenient yet can proliferate into many types like `@IsAdmin`, `@IsManager`, `@IsAuditor`. Spring Security supports **templates for expressions inside meta-annotations**, letting you build one parameterized annotation.

**Version distinction:** `AnnotationTemplateExpressionDefaults` in `org.springframework.security.core.annotation` is documented **starting in Spring Security 6.4**. In Spring Security 6.4/6.5, register the bean to enable template processing per documentation; from Spring Security 7.x onward, check the locked version's default behavior and configuration because template support is more tightly integrated. Do not copy this API into Spring Security 6.3 or older projects assuming the class exists.

### 6.1. Registering the Template Configuration Bean

In a Spring Security 6.4/6.5 project:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

Making the `@Bean` `static` in configuration ensures it is registered early enough for method-security infrastructure. For custom self-published advisors/interceptors, check whether they honor template defaults. Registering the bean does not guarantee every custom application interceptor supports the same mechanism.

### 6.2. Defining `@RequiresRole(String)`

File `RequiresRole.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

Usage:

```java
@RequiresRole("ADMIN")
public void viewAudit() { ... }

@RequiresRole("MANAGER")
public void approveRoutineRequest() { ... }
```

The template resolves `{value}` from the annotation attribute into `hasRole('ADMIN')` or `hasRole('MANAGER')` before Spring Security evaluates it.

Notice:

- Inside the template, `'{value}'` already includes **quotes** because the expected argument is a role string.
- At call sites, write `@RequiresRole("ADMIN")`, without adding extra quotes inside the string value.
- This is a value in **reviewed Java source**, not a value from user requests.
- `hasRole("ADMIN")` under default conventions checks `ROLE_ADMIN`; do not pass `"ROLE_ADMIN"` if the mechanism already prepends the prefix.
- If there are namespaces or tenant roles, verified mappings and object policies are still required.

**Never feel confident a parameterized meta-annotation works just because the class compiles.** If template defaults are missing in an opt-in version, placeholders may not substitute properly; real Spring context tests are mandatory.

### 6.3. `@RequiresAuthority(String)`

A similar form:

```java
@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresAuthority {
    String value();
}
```

Example:

```java
@RequiresAuthority("invoice:read")
public InvoiceSummary getSummary() { ... }

@RequiresAuthority("invoice:export")
public byte[] exportInvoices() { ... }
```

Parameterized annotations reduce creating many nearly identical wrappers, yet are **less expressive of business intent** than a dedicated `@CanApproveInvoice`. For policies involving owner/tenant/SoD, prefer explicit policy names or policy beans rather than stuffing every condition into a string template.

### 6.4. Multi-Role Templates and Quoting

Spring Security 6.5 documentation shows:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

Usage:

```java
@HasAnyRole(roles = { "'USER'", "'ADMIN'" })
public String overview() { ... }
```

In this example, **each element already contains single quotes** so when the template expands, the expression becomes:

```text
hasAnyRole('USER', 'ADMIN')
```

If you write `hasAnyRole('{roles}')` for an array, the whole list can turn into one unintended string. Conversely, if you pass `"USER"` and `"ADMIN"` without quotes in that example, the expanded expression may fail to parse properly.

Do not invent template syntax by guesswork; verify against the **exact version's** JavaDoc/reference and test the real annotation. In many projects, a permission enum or fixed policy annotations are easier to maintain than feeding SpEL strings indirectly everywhere.

### 6.5. SpEL Injection Risk When Templates Accept Untrusted Values

Placeholders are substituted into a SpEL expression, so every value supplied to a template must be treated as **part of policy configuration**, never business data from a user. Java annotation attributes are compile-time constants, yet third-party modules, codegen, or unreviewed dynamic configuration can still produce unintended expressions.

Never build a mechanism reading query/header values like:

```text
client parameter "role" -> value of the @PreAuthorize expression
```

Actual permissions must rely on verified `Authentication` and server policies. With quoted template strings, never accept input containing arbitrary quotes/expressions as a role name; restrict them to developer-controlled roles/authorities. If dynamic business conditions are needed, pass **data** into a policy bean with a typed API and validation instead of generating new SpEL strings per request.

### 6.6. Versions and Migration Configuration

| Version | Key Behavior to Remember |
| --- | --- |
| Spring Security 6.0–6.3 | Fixed meta-annotations like `@IsAdmin` work with method security; do not assume `AnnotationTemplateExpressionDefaults` exists |
| Spring Security 6.4–6.5 | `AnnotationTemplateExpressionDefaults` exists; register opt-in bean for expression templates per docs |
| Spring Security 7.x | Template support is integrated by default per the 7 migration guide; still check exact APIs/config in the locked version |
| Legacy `@EnableGlobalMethodSecurity` | Plan migration to `@EnableMethodSecurity`; do not assume legacy behavior matches modern templates/managers |

When upgrading, re-test every parameterized meta-annotation because the expanded expression is a **security-sensitive part of the policy**.

## 7. Meta-Annotations for `@PostAuthorize`: Using the Right Timing

Spring Security also supports meta-annotations on `@PostAuthorize`, especially useful when authorization depends on the returned object.

### 7.1. Reading Result Policy by Owner

File `ReturnedObjectMustBeOwned.java`:

```java
package example.security.policy;

import java.lang.annotation.*;
import org.springframework.security.access.prepost.PostAuthorize;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PostAuthorize("returnObject.owner == authentication.name")
public @interface ReturnedObjectMustBeOwned {
}
```

Usage:

```java
@ReturnedObjectMustBeOwned
public InvoiceView loadOwnedInvoice(long invoiceId) {
    return repository.loadView(invoiceId);
}
```

If `InvoiceView` exposes a matching `owner` property and compares accurately with `authentication.name`, non-owners will not receive the return value when the interceptor evaluates. This is **illustrative integration code**. Handle null returns, missing owners, tenants, resource IDs, and actor encoding without trusting client-sent owner fields.

### 7.2. Do Not Use After-Checks to Guard Write Operations

A defining trait of `@PostAuthorize` is that **the method body has already executed** before the expression is evaluated. With:

```java
@ReturnedObjectMustBeOwned
public InvoiceView approveInvoice(long invoiceId) {
    repository.markApproved(invoiceId);
    return repository.loadView(invoiceId);
}
```

the post-check can withhold the result while **the action has already written to the DB or called external APIs**. Never use it as the sole mechanism protecting approvals, payments, deletions, emails, or exports.

A safer pattern:

- Use `@PreAuthorize` or a `@CanApproveInvoice` meta-annotation before the method.
- Check state/owner/tenant **at write time** with matching transactions/locks/versions.
- Use `@PostAuthorize`, if at all, only as an additional check on suitable read results.
- Test that denied requests **produce no side effects**, not merely checking status 403.

### 7.3. Combining `@PreAuthorize` and `@PostAuthorize`

If a method uses **two different groups**:

```java
@RequiresInvoiceReadPermission
@ReturnedObjectMustBeOwned
public InvoiceView load(long invoiceId) { ... }
```

a pre-guard for functional permission and a post-guard for ownership can both apply: both must pass for the call to succeed. Still, pre-load policies should filter tenant in the query; never load thousands of out-of-scope records just because a post-check exists to filter afterward.

Important point: **do not generalize this into stacking multiple meta-annotations that both carry `@PreAuthorize` to create AND**. Spring Security does not support repeating the same security annotation type on a method arbitrarily. When two pre-conditions are mandatory, write **one pre-expression** using `and`, or consolidate into a policy bean.

## 8. Organizing a Small, Clear Policy Annotation Library

### 8.1. Suggested Structure

A policy library in a Java project might look like:

```text
example/
  security/
    MethodSecurityConfig.java
    policy/
      RequiresInvoiceReadPermission.java
      CanReadInvoice.java
      CanApproveInvoice.java
      RequiresRole.java
      RequiresAuthority.java
    service/
      InvoicePolicy.java
      InvoiceService.java
    test/
      InvoicePolicyTest.java
      InvoiceMethodSecurityTest.java
```

This is an **organizational suggestion**, not a mandate to follow these exact package/file names. Annotations can live in a shared module if multiple services use them, provided policies are versioned and have clear business ownership.

### 8.2. One Policy Definition Across Multiple Entry Points

Suppose a REST controller, scheduled job, and message consumer all call `InvoiceService.approveInvoice(...)`. Putting the meta-annotation on the service:

```text
REST HTTP chain ----+
                    |
Message consumer ---+--> InvoiceService.approveInvoice
                    |         |
Scheduled job ------+         +-- @CanApproveInvoice
                              +-- transaction/data conditions
```

can **reduce** the chance of gaps when a new entry point is added. However, proxy-based method security still needs an `Authentication` or appropriate service identity for non-HTTP calls; a scheduled job does not automatically carry a prior request's principal. Design a least-privilege service account/delegation and test it. If a job calls the repository directly or uses self-invocation, service annotations can be bypassed.

### 8.3. Where Should Annotations Be Placed?

Practical placement choices:

- **Public service entrypoint layer:** protects business actions invoked from multiple channels.
- **Controller:** can add HTTP/method guards for features, yet never treat it as the sole boundary if services are reused.
- **Class-level:** fits policies **shared by every public method** of the class.
- **Method-level:** fits when actions differ; remember method annotations can override same-type class annotations.
- **Interface:** useful when services share public contracts, while avoiding conflicting inherited annotations across multiple interfaces.
- **Repository:** can apply annotations in select cases, yet does not replace query scoping or data constraints.

Putting annotations on `private` methods called only internally **does not create a reliable Spring AOP proxy boundary**.

### 8.4. One Annotation Change Can Open Permissions in Many Places

If `@CanReadInvoice` is used on 50 methods, editing its internal expression:

```text
BEFORE: has(invoice:read) AND sameTenant AND owner
AFTER:  has(invoice:read) AND (sameTenant OR admin)
```

is a **centralized access-control change** affecting all 50 methods. That is both the benefit of reuse and its blast-radius risk. Require code review, regression tests for every deny case, policy change audits, and cross-tenant data-leak checks.

Never treat widening a predicate inside an annotation string as a "naming refactor".

## 9. Ordering, Inheritance, and Annotation Conflicts

### 9.1. Method-Level vs Class-Level

Spring Security documentation notes that `@PreAuthorize` can appear on classes and methods. When a method defines the same annotation type, the method policy **overrides** the same-type class-level policy.

Example:

```java
@RequiresInvoiceReadPermission
@Service
public class InvoiceOperations {

    public List<InvoiceSummary> list() { ... }

    @IsFinanceAdmin
    public void rebuildIndex() { ... }
}
```

Both `@RequiresInvoiceReadPermission` and `@IsFinanceAdmin` are meta-annotations for `@PreAuthorize`. **Do not assume they are ANDed together** on `rebuildIndex()`. During metadata lookup, the method annotation can replace the same-type class-level policy; review and test the exact rules for your version.

If `rebuildIndex()` must require **both invoice read permission and finance admin**, define an explicit separate annotation with a single SpEL expression:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and hasRole('FINANCE_ADMIN')"
)
public @interface FinanceAdminWithInvoiceReadPermission {
}
```

This is a **fragment**; when implementing, add `@Target`, `@Retention(RUNTIME)`, and imports like the complete examples. Even then, ask whether both conditions are genuinely required rather than combining permissions arbitrarily.

### 9.2. Multiple Interfaces with Different Policies

Example:

```java
interface ReadInterface {
    @PreAuthorize("hasAuthority('invoice:read')")
    String fetch();
}

interface AuditInterface {
    @PreAuthorize("hasAuthority('audit:read')")
    String fetch();
}
```

If a class implements both and the same method inherits security metadata from multiple interfaces, Spring Security may be unable to determine which policy applies, causing startup failure. The solution is **defining an explicit policy on the concrete method**, or designing interfaces without conflicts.

The same holds for meta-annotations: a new wrapper name does not erase ambiguity in the underlying `@PreAuthorize`.

### 9.3. Repeating the Same Group vs Different Groups

Spring Security explicitly documents that **repeating the same method-security annotation** on one method (e.g., two `@PreAuthorize` annotations) is not supported. Nor should you stack two differently named wrappers that both contain `@PreAuthorize` expecting the framework to AND them automatically.

If a method has one `@PreAuthorize` and one `@PostAuthorize`, two different interceptors can run sequentially, as in section 7. If `@Secured` or JSR-250 appears alongside `@PreAuthorize`, enable the corresponding group and test the combination. Never use `@PermitAll` to "bypass" other guards.

### 9.4. Should `@Secured` and JSR-250 Be Meta-Annotated?

Spring Security supports discovering enabled method-security annotation groups, yet do not assume every meta-annotation/templating combination shares identical syntax and behavior across all versions. If the project uses `@Secured` or `@RolesAllowed`, enable `securedEnabled=true`/`jsr250Enabled=true` and check the right JavaDoc. For new code, `@PreAuthorize` is usually more flexible and consistent when parameter expressions or policy beans are needed.

Never rewrite a role string inside `@Secured` as a SpEL expression expecting it to parse like `@PreAuthorize`; they are distinct mechanisms.

## 10. Proxies, Self-Invocation, and Execution Scope

### 10.1. The Proxy Is a Critical Boundary

In default `@EnableMethodSecurity` mode, Spring method security relies on Spring AOP proxies. A call from another bean through the proxy runs the interceptor; a `this.method()` call within the same instance usually **bypasses the proxy**.

Dangerous example:

```java
@Service
class InvoiceApprovalService {

    public void runBatch(long invoiceId) {
        approveInvoice(invoiceId);
    }

    @CanApproveInvoice
    public void approveInvoice(long invoiceId) {
        // Update business state.
    }
}
```

If `runBatch` calls `approveInvoice` on the same instance, the annotation may not execute. Move sensitive logic to another Spring bean invoked through a proxy, or enforce policy boundaries directly at the service/data/transaction level. Do not try to fix this merely by slapping annotations onto both methods without analyzing entry points.

### 10.2. Other Scenarios to Test

- Objects created with `new` outside the Spring container do not receive AOP advice automatically.
- `private`/`final` methods or `final` classes have proxy-type limitations; in particular, Kotlin classes/methods are final by default unless configured with open/plugin support.
- Multi-interface beans may use JDK proxies, causing calls via interfaces vs concrete types to behave differently; check real application configuration.
- Async/background threads may lack the HTTP request's `SecurityContextHolder`; use controlled propagation or service identities.
- AspectJ weaving can overcome some proxy limits, yet requires proper dependencies/weaving configuration; merely setting `mode=ASPECTJ` does not enable weaving.
- Placing a meta-annotation on a method does not protect direct repository calls or endpoints that skip that method.

**Annotation policies are one layer of protection, not proof that every path to the data is locked.**

## 11. Safety of Policy Beans and Business Conditions

### 11.1. The Bean Name Is a Contract

In SpEL:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
```

`@invoicePolicy` resolves to a Spring bean with that name. Renaming the bean or method can cause runtime failures in the expression. Best practices:

- Specify bean names explicitly when stability matters, e.g., `@Component("invoicePolicy")`.
- Test policies at both unit level and method-security integration level.
- Avoid expensive uncached/unbounded queries when interceptors run frequently.
- Never call non-idempotent APIs or trigger side effects inside `canApprove(...)`; it must be a **pure check**.
- Fail closed if authorization cannot be verified; never turn dependency exceptions into ALLOW.

### 11.2. `Authentication` and Principal

A meta-annotation:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
```

checks authorities attached to `Authentication`. It **does not re-verify where the role came from**; that belongs to trusted authentication/claim mappers. If a gateway turns an unauthenticated `X-Role: ADMIN` header into `ROLE_ADMIN`, annotations cannot fix that mistake.

Likewise, `@CanApproveInvoice` needs tenant and creator from server-side sources, never relying on `?tenantId=...` or client-sent JSON to decide object scope.

### 11.3. SoD and State Constraints

An invoice approval policy might include:

```text
canApprove(invoice, actor) =
  authenticated
  AND hasAuthority(invoice:approve)
  AND sameTenant
  AND assignedApprover
  AND actor != invoice.creator
  AND invoice.status == PENDING
```

Centralize object logic in `InvoicePolicy.canApprove(...)` for consistency across endpoints. When actually updating, use transactions, optimistic locking, or state/version-conditioned `UPDATE`s; a pre-method `canApprove` check alone does not eliminate all race conditions (TOCTOU).

### 11.4. Policy Definition and Data-Scope Enforcement Must Go Hand in Hand

For list/export APIs, `@RequiresInvoiceReadPermission` can guard the service, yet queries must still filter the dataset:

```sql
SELECT id, total, owner_id, tenant_id
FROM invoices
WHERE tenant_id = :verifiedTenant
  AND (
       owner_id = :verifiedUser
       OR :hasApprovedTeamAccess = true
  );
```

This SQL expresses intent; team-access permission must come from a trusted source, never a boolean taken straight from the client. In multi-tenant systems, evaluate the real authorization model, constrain visible rows explicitly, and prevent other queries/exports from exceeding scope.

## 12. Standalone Java 17: Learning Named and Reusable Policies

The following program has no Spring dependencies. It simulates **stably named policies** called from multiple entry points to highlight the difference between functional and resource permissions. Unknown policy names default to deny rather than allow.

Save `NamedMethodPolicyDemo.java`:

```java
import java.util.Set;

public class NamedMethodPolicyDemo {
    enum Status { DRAFT, PENDING, APPROVED }

    record Actor(
        long id, String tenantId, Set<String> authorities,
        boolean active
    ) {}

    record Invoice(
        long id, String tenantId, long ownerId,
        long creatorId, long assignedApproverId,
        Status status, Set<Long> sharedReaders
    ) {}

    static boolean has(Actor actor, String authority) {
        return actor != null
            && actor.active()
            && actor.authorities() != null
            && actor.authorities().contains(authority);
    }

    static boolean sameTenant(Actor actor, Invoice invoice) {
        return actor != null && invoice != null
            && actor.tenantId() != null
            && actor.tenantId().equals(invoice.tenantId());
    }

    static boolean requiresInvoiceReadPermission(Actor actor) {
        return has(actor, "invoice:read");
    }

    static boolean canReadInvoice(Actor actor, Invoice invoice) {
        return requiresInvoiceReadPermission(actor)
            && sameTenant(actor, invoice)
            && (
                actor.id() == invoice.ownerId()
                || (
                    invoice.sharedReaders() != null
                    && invoice.sharedReaders().contains(actor.id())
                )
            );
    }

    static boolean canApproveInvoice(
            Actor actor, Invoice invoice) {
        return has(actor, "invoice:approve")
            && sameTenant(actor, invoice)
            && invoice.status() == Status.PENDING
            && actor.id() == invoice.assignedApproverId()
            && actor.id() != invoice.creatorId();
    }

    static boolean namedPolicy(
            String name, Actor actor, Invoice invoice) {
        if (name == null) {
            return false;
        }
        return switch (name) {
            case "RequiresInvoiceReadPermission" ->
                requiresInvoiceReadPermission(actor);
            case "CanReadInvoice" ->
                canReadInvoice(actor, invoice);
            case "CanApproveInvoice" ->
                canApproveInvoice(actor, invoice);
            default -> false;
        };
    }

    static void show(String label, boolean result) {
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            10, "A", Set.of("invoice:read"), true
        );
        Actor bob = new Actor(
            20, "A", Set.of("invoice:read"), true
        );
        Actor approver = new Actor(
            30, "A", Set.of("invoice:approve"), true
        );
        Actor outsider = new Actor(
            99, "B", Set.of("invoice:read", "invoice:approve"),
            true
        );
        Actor inactive = new Actor(
            10, "A", Set.of("invoice:read"), false
        );

        Invoice pending = new Invoice(
            101, "A", 10, 10, 30,
            Status.PENDING, Set.of(20L)
        );
        Invoice approved = new Invoice(
            102, "A", 10, 10, 30,
            Status.APPROVED, Set.of()
        );
        Invoice selfApproval = new Invoice(
            103, "A", 10, 30, 30,
            Status.PENDING, Set.of()
        );

        show("alice has read permission",
            namedPolicy(
                "RequiresInvoiceReadPermission", alice, pending
            ));
        show("alice reads own",
            namedPolicy("CanReadInvoice", alice, pending));
        show("bob reads shared",
            namedPolicy("CanReadInvoice", bob, pending));
        show("bob reads unshared",
            namedPolicy("CanReadInvoice", bob, approved));
        show("outsider reads cross tenant",
            namedPolicy("CanReadInvoice", outsider, pending));
        show("inactive reads own",
            namedPolicy("CanReadInvoice", inactive, pending));
        show("approver approves pending",
            namedPolicy("CanApproveInvoice", approver, pending));
        show("approver approves approved",
            namedPolicy("CanApproveInvoice", approver, approved));
        show("approver self approves",
            namedPolicy(
                "CanApproveInvoice", approver, selfApproval
            ));
        show("alice without approve permission",
            namedPolicy("CanApproveInvoice", alice, pending));
        show("unknown policy denied",
            namedPolicy("UnknownPolicy", alice, pending));
        show("null actor denied",
            namedPolicy("CanReadInvoice", null, pending));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac NamedMethodPolicyDemo.java
java NamedMethodPolicyDemo
```

Stdout results in order:

```text
alice has read permission: true
alice reads own: true
bob reads shared: true
bob reads unshared: false
outsider reads cross tenant: false
inactive reads own: false
approver approves pending: true
approver approves approved: false
approver self approves: false
alice without approve permission: false
unknown policy denied: false
null actor denied: false
```

**Explanation of results:**

1. Alice has functional permission `invoice:read` and is the owner, so she can read invoice 101.
2. Bob has read permission and is in invoice 101's valid share list, so he can read it; for unshared invoice 102, the result is false even though he still has the permission.
3. Outsider in tenant B cannot read tenant A's invoice, even with both `invoice:read` and `invoice:approve`.
4. Inactive account cannot read even though permissions remain in the `Set`.
5. Approver can approve `PENDING` invoice when assigned as approver and not the creator; `APPROVED` invoice and self-approval are both denied.
6. Unknown policy and null actor default to deny. There is no "allow if policy is unknown".
7. `namedPolicy` uses string names purely to illustrate the mindset; in a Spring app, annotations are processed by method-security advisors, **not** by running this `switch`.

**Program limitations:** no `Authentication`, Spring AOP, proxies, tokens, Hibernate, or transactions. Real share-list/tenant logic must be verified server-side, never trusting a client-supplied `Set`. Stdout proves policy semantics, not meta-annotation integration tests.

## 13. Testing Meta-Annotations on Real Spring Beans

### 13.1. Minimal Test with Fixed Annotations

Example simple bean:

```java
import org.springframework.stereotype.Service;

@Service
public class ReportGateService {

    @RequiresInvoiceReadPermission
    public String read() {
        return "allowed";
    }

    @IsFinanceAdmin
    public String admin() {
        return "admin-allowed";
    }
}
```

Assuming the project has the annotations from section 4 and `@EnableMethodSecurity` configuration. JUnit 5 test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MetaAnnotationMethodSecurityTest {

    @Autowired
    ReportGateService service;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanRead() {
        assertEquals("allowed", service.read());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotRead() {
        assertThrows(
            AccessDeniedException.class, service::read
        );
    }

    @Test
    @WithMockUser(roles = "FINANCE_ADMIN")
    void financeAdminCanRunAdminMethod() {
        assertEquals("admin-allowed", service.admin());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotRunAdminMethod() {
        assertThrows(
            AccessDeniedException.class, service::admin
        );
    }
}
```

This is **integration test code**, requiring a real Spring Boot test context, `spring-security-test` dependency, and compiled annotation definitions. Calls must pass through the **proxied Spring bean**, never `new ReportGateService()`; manually instantiating the object skips interceptors and yields misleading results.

### 13.2. Testing Template Annotations in 6.4/6.5

Test bean:

```java
@Service
public class TemplateGate {

    @RequiresRole("MANAGER")
    public String managersOnly() {
        return "manager-zone";
    }

    @RequiresAuthority("invoice:export")
    public String export() {
        return "exported";
    }
}
```

Tests should verify:

- `@WithMockUser(roles="MANAGER")` passes `managersOnly()`.
- `@WithMockUser(roles="USER")` is denied `managersOnly()`.
- `@WithMockUser(authorities="invoice:export")` passes `export()`.
- A user with only `invoice:read` is denied `export()`.
- Context startup succeeds without placeholder parse errors.
- Tests without `AnnotationTemplateExpressionDefaults` live only in an **isolated context** to demonstrate the difference, never mixing conflicting configs into one context.

Testing the real application is far more valuable than inspecting annotations with reflection: reflection only proves `@RequiresRole` carries `@PreAuthorize`, not that Spring's interceptor activated and the parser expanded `{value}`.

### 13.3. Testing `@CanReadInvoice` with Parameters

For meta-annotations relying on `#invoiceId`:

- Mock/fixture repository has invoice 101 in tenant A owned by Alice.
- Alice with `invoice:read` and tenant A: allowed to read.
- Bob with `invoice:read` but neither owner nor share recipient: denied.
- Carol in a different tenant even with a high role: denied.
- Owner lacking `invoice:read`: denied.
- Anonymous user or inactive account: denied.
- Non-existent ID: cannot read.
- Denied requests: return no data and trigger no side effects.
- Actual release compilation uses `-parameters`, so `#invoiceId` binds properly.

Each test must know **which layer blocked**. A `MockMvc` test returning 403 due to CSRF does not prove `@CanReadInvoice` was invoked by the interceptor. Test the service directly through the bean and maintain separate HTTP tests.

### 13.4. Testing Missing/Stacked Annotation Configurations

Negative tests that catch security bugs:

| Case | What Must Be Proven |
| --- | --- |
| `@EnableMethodSecurity` not enabled | Annotation does not protect by itself; test catches missing config |
| `prePostEnabled=false` | Meta-annotation wrapping `@PreAuthorize` does not run automatically |
| Self-invocation | Annotation can be bypassed when skipping the proxy |
| Annotation on `private`/`final` method | Do not rely on unapplied proxy guards |
| Class-level and method-level sharing underlying `@PreAuthorize` | Method policy can override class; does not AND automatically |
| Two conflicting interfaces | Policy must be declared explicitly on the concrete method |
| Two wrappers both carrying underlying `@PreAuthorize` | Do not expect automatic combining; use one unified expression |
| Missing template bean on opt-in version | Do not assume placeholders were substituted |
| Template with quotes or unusual roles | Validated and does not widen permissions |
| Policy bean error / DB timeout | Sensitive actions fail closed |
| User's tenant/role changed in session | Object policy and permission revocation take effect per design |

For custom meta-annotations on `@PostAuthorize`, test that **read** methods returning an owned object succeed while non-owners are denied. Never use a passing post-check test to claim a write operation had no side effects.

### 13.5. MockMvc and HTTP Authorization

You might have:

```text
HTTP: GET /api/invoices/101 -> authenticated
Service: @CanReadInvoice
DB: query scoped by verified tenant
```

In this setup, HTTP allows a logged-in user through to the service, while the method blocks if authority/tenant is missing. That is **proper multi-layer coordination**, not a contradiction. If another controller, export job, or event consumer invokes the service, the method still requires a valid context and proper object policy.

Never use meta-annotations as an excuse to open `anyRequest().permitAll()` on HTTP. Keep fallback deny, route-level checks, and CSRF protection for cookie/session models.

## 14. Operating and Governing a Policy Annotation Library

### 14.1. Naming and Documentation Conventions

Each annotation should have minimal JavaDoc answering:

1. Which **action** does it protect?
2. Which permission/role is required?
3. Does it depend on any method parameter (e.g., `invoiceId`)?
4. Does it check tenant/owner/sharing/status?
5. Does it guarantee no side effects occur before denial?
6. Is it intended for methods or classes, and on which interfaces?
7. What minimum Spring Security version is required?
8. Are there tests proving both allow and deny cases?

Example clear contract:

```java
/**
 * Invoke this method only when the actor has invoice:read and is
 * permitted to read invoiceId in the verified tenant.
 *
 * Requires a method parameter named invoiceId (compile with -parameters).
 * Does not replace query scope and transaction invariants.
 */
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public @interface CanReadInvoice {}
```

This is just a JavaDoc/annotation fragment; add `@Retention`, `@Target`, and imports as in section 5 when creating the real file.

### 14.2. Renaming vs Changing Semantics

- **Renaming** `@CanReadInvoice` to `@MayReadInvoice` while keeping the expression: code API refactor; still update call sites/tests.
- **Changing the expression** from owner-only to owner-or-team: access policy change; requires security review and scope testing.
- **Adding export permission** to the manager role: can widen access even without editing the annotation.
- **Changing the policy bean** from a scoped query to `findById`: introduces IDOR risk even though the annotation did not change.
- **Disabling method security** or changing AOP config: can disable the entire annotation library at once.

Treat annotation policies as a **security API**: changes require migration notes, versioning, approvers, and regression tests.

### 14.3. Auditing and Observability

When a call is denied, appropriate logs can record:

- Correlation ID;
- Policy name (e.g., `CanApproveInvoice`);
- Action and object type;
- **Verified** principal/tenant, minimized;
- ALLOW/DENY outcome and reason code;
- Timestamp of role/policy version changes.

Never log raw JWTs, passwords, session cookies, customer profiles, or sensitive resource details. Never expose full SpEL expressions to end users since that leaks internal structure; return appropriate status codes and messages to clients (401, 403, 404, 409 per design).

A complex expression firing multiple DB queries inside a policy bean can cause overhead; optimize with caching keyed precisely by tenant/actor/object, appropriate TTLs, revocation hooks, and never reuse cached results across different users.

## 15. Common Mistakes

| Mistake | Why Wrong/Dangerous? | How to Prevent |
| --- | --- | --- |
| Naming `@CanReadInvoice` while checking only `ROLE_USER` | Name promises object check, yet policy lacks it | Separate functional permission and object policy |
| Forgetting `@EnableMethodSecurity` | Annotation has no interceptor | Enable and integration-test Spring beans |
| Missing `@Retention(RUNTIME)` | Runtime cannot see the annotation | Set proper retention |
| `@Target(TYPE)` on a policy depending on `#invoiceId` | Class has methods lacking that parameter | Use `METHOD` or clear contracts |
| Reading `#invoiceId` without preserving parameter names | SpEL cannot find the right argument | Compile with `-parameters`/proper config |
| Creating objects with `new` | Bypasses AOP proxy | Invoke Spring beans |
| Self-invocation | Bypasses method-security proxy | Refactor bean boundaries |
| Using two `@PreAuthorize` wrappers as AND | Can conflict / repetition unsupported | Single expression or policy bean |
| Confusing class-level + method-level for AND | Method overrides same-type policy | Write combined conditions explicitly |
| Using `@PostAuthorize` for writes | Denies after side effects | Pre-checks and transaction/data invariants |
| Using 6.4 templates on 6.3 | API does not exist | Lock version and check JavaDoc |
| Forgetting template bean in 6.4/6.5 | Placeholders do not expand as expected | Static bean + context test |
| Wrong array template quoting | Broken SpEL parse or semantics | Test expansion explicitly |
| Letting users control SpEL template values | Injection and privilege escalation risk | Reviewed compile-time values only |
| Inconsistent `ROLE_` role naming | False denials or dangerous workarounds | Standardize authority/prefix catalog |
| Checking permission while ignoring tenant/owner | IDOR/BOLA | Policy bean and query scoping |
| Check-then-write without state constraints | TOCTOU | Conditional updates/versioning/transactions |
| Turning off pre/post group due to config errors | Custom annotations lose guards | Debug instead of disabling |
| Testing only reflection annotations | Fails to prove interceptor runs | Test through Spring-managed beans |
| Editing a centralized policy without testing all call sites | Broad privilege escalation | Code review, CI regression, auditing |
| Forgetting non-HTTP entry points | Job/consumer bypasses | Service method guards + task identity |

## 16. Hands-On Exercises

### Exercise 1 — Policy Name vs Contents

Create `@RequiresInvoiceReadPermission` checking only `invoice:read` and `@CanReadInvoice` checking tenant and owner/share as well. Find a scenario where a user has functional read permission yet is not allowed to view a specific object; explain why the two names are not synonymous.

### Exercise 2 — Running a Static Meta-Annotation in Spring

Create `@IsFinanceAdmin` with `@PreAuthorize("hasRole('FINANCE_ADMIN')")`; place it on a Spring service public method; enable `@EnableMethodSecurity`. Test with `@WithMockUser(roles="FINANCE_ADMIN")` and `roles="USER"`. Ensure tests call through the injected bean.

### Exercise 3 — 6.4+ Template Meta-Annotations

Register `AnnotationTemplateExpressionDefaults`. Create `@RequiresAuthority("{value}")` with exact syntax as in section 6.3; test `invoice:read` and `invoice:export`. Create a misquoted case in an isolated test context to observe the error. Never deploy that broken code to production.

### Exercise 4 — Parameter Binding

Use `@CanReadInvoice` depending on `#invoiceId`. Compile with and without `-parameters` in a controlled test setup; verify how binding behaves in your version. Try renaming the parameter from `invoiceId` to `id` and verify regression tests catch the break.

### Exercise 5 — Class vs Method Precedence

Put `@RequiresInvoiceReadPermission` on a class and `@IsFinanceAdmin` on one method. Test how the method rule applies. If business logic requires both, write an AND expression in a new annotation instead of guessing the framework merges them.

### Exercise 6 — Denying at the Right Time

Create `@ReturnedObjectMustBeOwned` with `@PostAuthorize` and use it for read-only queries. Then try putting it on a write method and explain why denial is too late. Design `@CanApproveInvoice` with a pre-check and version/condition-guarded update.

### Exercise 7 — Running Java 17

Run `NamedMethodPolicyDemo.java` and verify all 12 stdout lines. Add an `auditor` actor, an invoice in another tenant, and a `CanExportInvoice` policy; keep default-deny for unknown policy names and allow exporting only within scope.

### Exercise 8 — Testing a Centralized Policy Change

Suppose `@CanReadInvoice` is used on 20 service methods. The business adds team-read access. List the allow/deny test cases to add, cross-tenant risks, export data limits, message consumer call paths, and rollback steps if the new policy proves overly permissive.

## 17. Pre-Production Checklist

- [ ] Name reflects **the exact conditions** the annotation actually checks.
- [ ] `@Retention(RUNTIME)` and `@Target` match intended usage sites.
- [ ] `@EnableMethodSecurity` is present and the pre/post group is active.
- [ ] Static meta-annotations have one clear expression without overly broad privileges.
- [ ] For templates, verified Spring Security 6.4+/7.x and the version's bean/default behavior.
- [ ] Template values are reviewed compile-time configuration, never client-supplied.
- [ ] Quoting, array expansion, and role prefixes are integration-tested.
- [ ] Expressions using `#param` have parameter names preserved properly by the compiler.
- [ ] No stacking of annotations sharing underlying `@PreAuthorize` as an implicit AND.
- [ ] Class/interface/method inheritance creates no conflicting policies.
- [ ] Services are called through Spring proxies or configured weaving.
- [ ] Policy beans have trustworthy check logic with no side effects.
- [ ] Queries/transactions continue enforcing tenant, owner, status, and version.
- [ ] `@PostAuthorize` is used only when post-checking is safe and leaves no missed side effects.
- [ ] Allow/deny tests run on real Spring beans, plus HTTP integration tests when applicable.
- [ ] Regression tests run whenever expressions, mappers, prefixes, or Spring Security versions change.
- [ ] Policies have clear owners/reviewers and security change tracking.

## 18. Self-Check

1. **What is a meta-annotation?** An annotation used to annotate another annotation; Spring Security can discover method-security annotations nested inside it.
2. **Does creating `@IsAdmin` automatically enable method security?** No; `@EnableMethodSecurity` and proper interception are required.
3. **Why is `@Retention(RUNTIME)` required?** So the framework's runtime scanner can see the annotation.
4. **When should you use `@Target(METHOD)` instead of including `TYPE`?** When the policy depends on parameters present only on methods, or is unsuitable across an entire class.
5. **Is naming an annotation `@CanReadInvoice` while checking only `invoice:read` enough?** No, if the name promises per-invoice authorization; tenant/owner/share checks are also required.
6. **How does `@RequiresRole("ADMIN")` differ from `@RequiresAuthority("ROLE_ADMIN")`?** The role matcher prepends a prefix by default, whereas the authority matcher compares exact names; keep mappers consistent.
7. **In 6.4/6.5, what is needed for templated annotations?** An `AnnotationTemplateExpressionDefaults` bean registered per the documentation.
8. **Can template values come from user query parameters?** Never; they are part of the authorization expression and must be controlled and reviewed.
9. **Why must `hasAnyRole({roles})` watch quoting carefully?** The template expands an array into SpEL arguments; each element needs valid string syntax.
10. **What must be done if a Java method renames `invoiceId` to `id`?** Update the policy/annotation or keep explicit binding and run tests.
11. **Is placing two meta-annotations carrying `@PreAuthorize` guaranteed to AND them?** No; do not rely on stacking the same underlying annotation; write one unified expression.
12. **Can `@PostAuthorize` replace pre-checks for money transfers?** No; denying after the method runs can be too late.
13. **Is an internal call `this.approve()` guaranteed to run the interceptor?** Not with standard Spring AOP proxies.
14. **Does adding meta-annotations to services replace HTTP security?** No; check routes/filter chains, methods, and resources together.
15. **If one annotation is used in 50 places, what does editing its expression affect?** It simultaneously changes permissions across all 50 call sites; require regression testing and review.
16. **Does enabling a role hierarchy solve tenant authorization?** No; hierarchies model authority relationships, not data scoping.
17. **If a request returns 403, does that prove the annotation ran?** No; it could be blocked by HTTP matchers, CSRF, or another layer.
18. **Why prefer policy beans for complex conditions?** Easier to unit-test with real types, avoids huge SpEL strings, and avoids duplicating logic across annotations.
19. **When upgrading Spring Security, what should be reviewed?** Template APIs, annotation scanners/interceptors, expressions, role prefixes, AOP configuration, and permission tests.
20. **What should happen if a principal has the permission yet the invoice belongs to another tenant?** Denied by the object policy; meta-annotations must never open a bypass.

**Remember:** meta-annotations in Spring Security are a way to give **meaningful business names** to method authorization policies, making code readable and consistent. Choose names that accurately reflect permission scope, use static wrappers for stable policies, use controlled templates only when parameters are genuinely needed, and keep tenant/owner/state checks where trustworthy data lives. Final security comes not from the annotation's name, but from **enabled interceptors, applied expressions, sound business policies, and tests proving denial cases**.

### Official Documentation

- [Spring Security 6.5 – Method Security / Using Meta Annotations](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 – AnnotationTemplateExpressionDefaults JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html)
- [Spring Security – Migration to 7 / Authorization Changes](https://docs.spring.io/spring-security/reference/6.5/migration-7/authorization.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – HTTP authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)