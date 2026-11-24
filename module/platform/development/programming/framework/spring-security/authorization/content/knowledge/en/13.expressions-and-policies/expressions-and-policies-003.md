# Logical Operators, Precedence, and Expression Readability in Spring Security

## 1. Why is logical ordering a security concern?

In Spring Security, policies such as `@PreAuthorize` and `@PostAuthorize` can use Spring Expression Language (SpEL) to combine conditions on roles, operation permissions, user identity, tenant, and resources. Missing just one pair of parentheses can grant access to someone who should have been denied.

Consider a business requirement: **the user must belong to the same tenant as the document AND must be an ADMIN OR hold the read-document permission**. There are three conditions:

- `A`: the user has the ADMIN role.
- `B`: the user holds the `document:read` authority.
- `C`: the user and the document belong to the same tenant.

The intended policy is `(A or B) and C`. However, the expression `A or B and C` is interpreted as `A or (B and C)` because `and` has higher precedence than `or`. Consequently, an ADMIN can bypass the tenant check (`A = true` makes the entire expression true), even though the requirement mandates **everyone** must be in the right tenant.

Lesson goals: recognize SpEL logical operators, read precedence accurately, intentionally group conditions with parentheses, write verifiable policies, and prevent overly permissive authorization bugs.

## 2. Context: SpEL expressions in method-level security

Spring Security uses SpEL to express decisions for annotations such as:

- `@PreAuthorize("...")`: evaluated before invoking the method, commonly used to reject unauthorized calls early.
- `@PostAuthorize("...")`: evaluated after the method returns, able to reference the return value via `returnObject`. Do not rely on this to prevent side effects that have already happened inside the method.
- `@PreFilter` and `@PostFilter`: filter input/output elements; also use expressions, specifically for collection filtering.

For a Spring Boot application using Spring Security, enable method security with the following configuration (this is an application configuration component, not a standalone runnable Java program):

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Merely adding the Spring Security dependency does not enable method security by default. When a Spring bean's method is invoked through the appropriate interceptor/proxy, Spring Security evaluates the expression in a context containing `authentication`, `principal`, functions like `hasAuthority(...)` and `hasRole(...)`, and method parameters formatted as `#parameterName`.

Example:

```java
@PreAuthorize("hasAuthority('document:read') and #documentId != null")
public Document findOne(Long documentId) {
    // Load document via repository; partial snippet only.
}
```

Meaning: both the read authority condition and the non-null ID check must pass. This ID check alone is **not** enough to authorize access to a specific document; a later section uses a trusted policy bean for that.

## 3. The three core logical operators

| Operator | SpEL syntax | Evaluates to true when | Reading hint |
| --- | --- | --- | --- |
| AND | `and` or `&&` | All operands are true | "and" — every condition must be satisfied |
| OR | `or` or `||` | At least one operand is true | "or" — satisfying one of the branches suffices |
| NOT | `not` or `!` | The operand is false | "not" — negates the logical result |

The word forms `and`, `or`, and `not` are case-insensitive in SpEL. Since `@PreAuthorize` accepts a Java string, you can choose word forms for policy readability or symbolic forms familiar to developers. **Keep one consistent style within the same codebase.**

Valid examples:

```java
@PreAuthorize("hasAuthority('document:read') and isAuthenticated()")
@PreAuthorize("hasRole('ADMIN') or hasAuthority('document:read')")
@PreAuthorize("not hasAuthority('account:suspended')")
@PreAuthorize("hasAuthority('document:read') && !hasAuthority('account:suspended')")
```

These four annotations are **four separate examples** for different methods; do not stack four `@PreAuthorize` annotations onto a single method simultaneously.

Key reminder: `hasRole('ADMIN')` typically checks an authority with the `ROLE_` prefix (depending on prefix configuration), whereas `hasAuthority('document:read')` matches the authority string directly. Never mix up roles and authorities without inspecting the actual granted authority data.

## 4. Precedence: NOT → AND → OR

When an expression combines standard logical operators, the precedence order from highest to lowest is:

1. **Parentheses `(...)`** group conditions to state intent and determine evaluation structure.
2. **Negation `not` / `!`** applies to its operand or grouped subexpression.
3. **Conjunction `and` / `&&`** combines conditions.
4. **Disjunction `or` / `||`** combines branches.

Comparisons such as `==`, `!=`, `>`, `>=`, method calls, and property accesses typically produce the booleans combined by `and`/`or`. When mixing multiple operator types, **place parentheses around checks to make intent explicit**, instead of forcing readers to memorize a longer precedence table.

Examples:

```text
A or B and C        ≡ A or (B and C)
not A and B         ≡ (not A) and B
not (A and B)       ≠ (not A) and B
(A or B) and C      ≠ A or (B and C)
```

The `≡` symbol denotes logical equivalence; `≠` indicates the two expressions can yield different results. With `A = true, B = false, C = false`:

- `A or B and C` → `true or (false and false)` → `true`.
- `(A or B) and C` → `(true or false) and false` → `false`.

This is a severe bug pattern: **the ADMIN role bypasses the mandatory same-tenant check** in the first formulation.

### Truth table for grouping conditions

| A: ADMIN | B: document:read | C: same tenant | `A or B and C` | `(A or B) and C` |
| --- | --- | --- | --- | --- |
| true | false | false | **true** | **false** |
| true | false | true | true | true |
| false | true | true | true | true |
| false | true | false | false | false |
| false | false | true | false | false |
| false | false | false | false | false |

The very first row suffices to prove the unparenthesized expression is **not equivalent** to the business requirement.

## 5. Use parentheses to express policy before optimizing syntax

Suppose the application has a `documentPolicy` bean with a `sameTenant(documentId)` method that verifies the tenant from server-authenticated identity data and the document record in the database.

**Error-prone:**

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('document:read') and " +
    "@documentPolicy.sameTenant(#documentId)"
)
public Document read(Long documentId) {
    // ...
}
```

By precedence, the tenant check binds only to the `document:read` branch. An ADMIN passes via the first branch without any tenant verification.

**Matches the requirement that everyone share the same tenant:**

```java
@PreAuthorize(
    "(hasRole('ADMIN') or hasAuthority('document:read')) and " +
    "@documentPolicy.sameTenant(#documentId)"
)
public Document read(Long documentId) {
    // ...
}
```

Even when precedence could be deduced, parentheses also serve as documentation: the two operation-permission branches are grouped together, and then **the permission group** must satisfy the tenant check.

If the policy genuinely allows ADMINs to cross tenants, that must be an **intentional business decision**, such as a dedicated `hasAuthority('platform:cross-tenant-read')` rule with auditing and full checks. Never treat missing parentheses as an implicit cross-tenant policy.

### Negating a whole group or a single branch?

The following two expressions differ:

```text
not (A or B)   = (not A) and (not B)
(not A) or B   = denies A yet still accepts B
```

If you need to deny access when the user has **any** forbidden authority, write:

```java
@PreAuthorize(
    "not (hasAuthority('account:suspended') or " +
    "hasAuthority('account:blocked'))"
)
```

Do not replace it with:

```java
@PreAuthorize(
    "not hasAuthority('account:suspended') or " +
    "hasAuthority('account:blocked')"
)
```

The wrong expression accepts an account that has `account:blocked` as long as it lacks `account:suspended`. Parentheses after `not` clearly define the **negated scope**.

## 6. Short-circuiting: how short-circuit evaluation affects order

SpEL's `and` and `or` operators use short-circuit evaluation on boolean operands:

- `A and B`: if `A` is already `false`, `B` is not evaluated.
- `A or B`: if `A` is already `true`, `B` is not evaluated.

This helps prevent errors when the right-hand condition requires a non-null object:

```java
@PreAuthorize(
    "#document != null and " +
    "#document.ownerUsername == authentication.name"
)
public void update(Document document) {
    // ...
}
```

If `#document` is `null`, the right-hand side is never accessed, avoiding an error reading `ownerUsername` from a null object. In real applications, **do not trust an owner attribute supplied by the client**: still verify ownership against a trusted data source to prevent data spoofing.

Reversing the order to:

```java
@PreAuthorize(
    "#document.ownerUsername == authentication.name and " +
    "#document != null"
)
```

is no longer safe when `document` may be null: the program attempts to read the property before checking for null.

Short-circuiting avoids unnecessary work, yet you **should never rely on side effects** of a method called inside SpEL (logging, incrementing counters, mutating state...) to drive decisions. Authorization helper methods should be pure and free of state mutations; a method on the right-hand side might never be invoked.

## 7. Comparisons, null, and client-supplied conditions

In access expressions, data checks are often combined with permission checks:

```java
@PreAuthorize(
    "hasAuthority('order:read') and " +
    "#orderId != null and #orderId > 0"
)
```

This example checks operation authority and basic ID validity. It **does not** prove the user is allowed to read the order with that ID.

Avoid assuming `#ownerUsername == authentication.name` is safe enough if `ownerUsername` is passed from the request: callers can submit any value. Ownership and same-tenant decisions must be verified against server-controlled data.

To prioritize clarity across comparisons and logical checks:

```java
@PreAuthorize(
    "hasAuthority('order:read') and " +
    "(#orderId != null) and " +
    "@orderPolicy.canRead(authentication, #orderId)"
)
```

Here, `orderPolicy.canRead(...)` should return `false` when valid data is missing and validate the order against the trusted identity, tenant, and ACL. In particular, define explicitly whether tenant checks may ever be bypassed; avoid letting an `or` branch accidentally bypass a global constraint.

**Do not use relational operators with `null` as a numeric comparison trick:** SpEL has specific `null` comparison rules that differ from treating "null as 0". Instead, check null and value bounds explicitly.

## 8. Writing readable expressions at varying complexity levels

### Level 1: a single simple permission requirement

```java
@PreAuthorize("hasAuthority('invoice:read')")
public Invoice loadInvoice(Long id) {
    // ...
}
```

When a policy only needs one authority, a short expression is ideal. If two authorities are genuine alternatives, `hasAnyAuthority(...)` is clearer than a long `or` chain:

```java
@PreAuthorize("hasAnyAuthority('invoice:read', 'invoice:admin')")
```

### Level 2: combining an alternative group with a mandatory condition

```java
@PreAuthorize(
    "(hasAuthority('invoice:read') or hasAuthority('invoice:admin')) " +
    "and @invoicePolicy.sameTenant(#invoiceId)"
)
```

Using parentheses is worthwhile even when the author already knows operator precedence: reviewers immediately see which group is `OR` and which condition applies to all branches.

### Level 3: multiple rules—extract into a policy bean

Overly long expressions easily hide loopholes when a branch changes. Extract business logic cleanly:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        // Load the document using the repository injected into the service.
        // Illustrative body, not a standalone implementation.
        throw new UnsupportedOperationException("Illustrative code");
    }
}
```

This snippet illustrates how `#documentId` is explicitly named via `@P` and how the `@documentPolicy` bean is called via SpEL. This is **part of a Spring application**, requiring the `Document` class, the `documentPolicy` bean, and the project's repository; it is not a standalone runnable class.

`DocumentPolicy.canRead(authentication, documentId)` needs to verify the user's granted permissions, current tenant, and ownership/sharing/ACL against real data. When this check grows complex, moving it into plain Java makes naming conditions, writing unit tests, and optimizing queries much easier. **Method names should explain the policy**, such as `canRead`, `canModify`, `sameTenant`; avoid `check1` or `isOk`.

Alternatively, administrative accounts may be granted an authority that already implies read access under a well-designed permission model or role hierarchy, simplifying the expression to `hasAuthority('document:read')`. However, a role hierarchy must never silently bypass per-resource or tenant constraints.

## 9. Standalone runnable Java 17 example: verifying true/false effect of parentheses

This is a **plain Java program simulating boolean logic**, requiring neither Spring nor SpEL execution. Since the three operators in the example carry the same boolean semantics as Java's `!`, `&&`, and `||`, the program clearly demonstrates the impact of missing parentheses.

Save as `LogicPrecedenceDemo.java`:

```java
public class LogicPrecedenceDemo {

    private static boolean implicit(
            boolean admin, boolean canRead, boolean sameTenant) {
        return admin || canRead && sameTenant;
    }

    private static boolean grouped(
            boolean admin, boolean canRead, boolean sameTenant) {
        return (admin || canRead) && sameTenant;
    }

    private static void check(
            String scenario,
            boolean admin, boolean canRead, boolean sameTenant) {
        System.out.printf(
            "%s: implicit=%s, grouped=%s%n",
            scenario,
            implicit(admin, canRead, sameTenant),
            grouped(admin, canRead, sameTenant)
        );
    }

    public static void main(String[] args) {
        check("Admin outside tenant", true, false, false);
        check("Reader inside tenant", false, true, true);
        check("Reader outside tenant", false, true, false);
        check("No permission", false, false, true);
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac LogicPrecedenceDemo.java
java LogicPrecedenceDemo
```

Standard output (stdout):

```text
Admin outside tenant: implicit=true, grouped=false
Reader inside tenant: implicit=true, grouped=true
Reader outside tenant: implicit=false, grouped=false
No permission: implicit=false, grouped=false
```

The first line shows that with the exact same three booleans, changing grouping alone flips the authorization outcome. In a Spring application, you must also **test the real annotations**, because a plain Java example does not verify interceptors, bean invocation, `Authentication` data, or database permission lookups.

## 10. Testing policies like a truth table

For any expression combining two or three conditions, the fastest way to catch grouping bugs is building a truth table. Let:

- `P` = has read authority;
- `T` = verified same tenant;
- `S` = resource is shared with the user.

Requirement: `P and T and S` for a strict shared-resource read rule. If the rule is `P and T and (S or owner)`, place parentheses correctly around the two valid ways to access the resource. Never leave `owner` inside an `or` branch outside `P` or `T` unless the business genuinely permits it.

With Spring Security Test, integration tests should invoke the service **through the Spring bean/proxy**, using identities with varying permissions and real or controlled mock repositories. Minimum scenarios:

| Scenario | Operation permission | Same tenant | Resource permission | Expected |
| --- | --- | --- | --- | --- |
| Authorized user | Yes | Yes | Yes | Allow |
| Missing authority | No | Yes | Yes | Deny |
| Different tenant | Yes | No | Yes | Deny |
| Not owner / not shared | Yes | Yes | No | Deny |
| ADMIN in different tenant (if tenant mandatory) | ADMIN | No | Depends on policy | Deny |
| Null / non-existent ID parameter | Yes | Unknown | No | Deny |

For instance, `@WithMockUser(authorities = "document:read")` creates a mock identity in tests; `@WithMockUser(roles = "ADMIN")` creates the default role corresponding to `ROLE_ADMIN`. Still, tests must actually exercise the authorization path, not just call a plain Java method bypassing the proxy.

Include **adversarial** tests for parenthesis grouping:
 
- `hasRole('ADMIN') or P and T` versus `(hasRole('ADMIN') or P) and T` when `ADMIN = true` and `T = false`.
- `not (blocked or suspended)` versus `not blocked or suspended` when `blocked = false`, `suspended = true`.
- `P and (#resource != null) and check(resource)` when `resource` is null to catch out-of-order property access.
- Whether method conditions apply when called via another bean; internal `this.method()` calls can bypass the Spring proxy.
- Ensuring no information leaks or unauthorized side effects happen in the method body before `@PostAuthorize` runs.

## 11. Common errors and fixes

| Error | Consequence | Fix |
| --- | --- | --- |
| Writing `A or B and C` when intending `(A or B) and C` | Branch `A` skips `C` | Parenthesize according to the business rule first |
| Flipping `not (A or B)` into `not A or B` | Wrong negation scope; may permit blocked subjects | Wrap the entire negated group in parentheses |
| Cramming all conditions into one giant string | Hard to review; easy to miss overly broad branches | Use `hasAnyAuthority` or a clearly named `@policy` bean |
| Using `hasRole('ADMIN')` when data only has `ADMIN`, or `hasAuthority('ADMIN')` when data only has `ROLE_ADMIN` | Permissions evaluate differently than expected | Inspect actual authorities and role prefix configuration |
| Placing null check after property access | Can throw an exception before reaching the null check | Place checks first and rely on short-circuit `and` |
| Trusting request data to decide owner/tenant | Easy to spoof for cross-tenant/user access | Read identity/tenant from trusted context and query DB/ACL |
| Writing checks only in a post-annotation after method execution | Side effects or intermediate data already occurred | Check beforehand; guard queries and transactions |
| Skipping tests where one `OR` branch is true while a mandatory condition is false | Grouping bugs from missing parentheses go undetected | Use a truth table and negative test cases |
| Using `A`/`B` names in real policies | Readers cannot tell business intent | Extract methods like `canRead`, `sameTenant`, `isOwner` |

**A note on annotations:** you cannot repeat multiple `@PreAuthorize` annotations on the same method to express distinct conditions. If a method carries multiple security annotations **of different kinds**, Spring Security evaluates each interceptor; all applicable checks must pass, effectively behaving like `AND`. Never guess execution order to fabricate an implicit `OR` relationship; when alternatives are needed, write an explicit `or` in a single policy or use an appropriate authorization component.

## 12. Checklist when reviewing authorization expressions

Before merging a SpEL rule, verify:

1. **Write the requirement in plain words:** which conditions are mandatory for everyone, and which are alternatives?
2. **Group with parentheses:** form `(A or B) and C` matching the written statement; never rely on left-to-right reading habits.
3. **Check negation:** does `not` apply to one condition or an entire group of conditions?
4. **Distinguish roles/authorities:** is there a `ROLE_` or custom prefix?
5. **Check data sources:** do identity, tenant, owner, and ACL come from a trusted server/database?
6. **Trace evaluation order:** check null and cheap conditions before deep property access; avoid side-effecting calls and repeated expensive checks.
7. **Name things clearly:** if an expression grows long, move logic to a Java bean and write independent tests.
8. **Test negative cases:** one `OR` branch true with a mandatory requirement false; ADMIN in another tenant; missing authority; null ID.
9. **Test via Spring proxy:** verify the annotation actually runs at the service call site.
10. **Keep policies auditable:** document business intent if needed; a short, clear, tested expression almost always beats a "clever" hard-to-read one.

### Self-practice

Consider the requirement: "*Only active accounts may export reports; the account must be an administrator **or** hold export permission; in all cases it must belong to the right tenant.*"

Let `A = active`, `R = admin`, `E = export permission`, `T = same tenant`.

- Correct expression: `A and (R or E) and T`.
- Error-prone expression: `A and R or E and T` (because it is equivalent to `(A and R) or (E and T)`).
- Counterexample: `A = false, R = false, E = true, T = true`. The buggy version returns `true` for a deactivated account, while the correct one returns `false`.

Illustrative SpEL mapping:

```java
@PreAuthorize(
    "@accountPolicy.isActive(authentication) and " +
    "(hasRole('ADMIN') or hasAuthority('report:export')) and " +
    "@tenantPolicy.canAccess(authentication, #tenantId)"
)
```

Both `accountPolicy` and `tenantPolicy` must use server-verified account status, tenant membership, and permissions. `tenantId` may be a request input, but it is **not** proof that the caller has access to that tenant.

## Official Documentation

- [Spring Framework — SpEL: Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html): `and`, `or`, `not` syntax, comparison operators, and equivalent forms.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): expression syntax, whitespace rules, and language structure.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, authority/role expressions, policy beans, and testing method authorization.
