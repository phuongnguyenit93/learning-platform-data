# Combining Multiple Annotations and Handling Conflicting Declarations in Spring Security Method Security

## Learning Objectives

In a Spring Security project, a service method may need to satisfy several requirements at once: the user must have a business role, hold an appropriate authority, be authorized for that specific record, and not receive out-of-scope resources in the returned result. These requirements can be expressed with `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@RolesAllowed`, `@PreFilter`, `@PostFilter`, or custom annotations.

The question is: **do multiple annotations automatically create OR, AND, overrides, or declaration errors?** The answer depends on whether they are **different annotation types**, the **same annotation type**, or **declarations on methods/classes/interfaces in an inheritance hierarchy**. Misunderstanding this can unintentionally widen permissions or prevent the Spring application from starting.

After this lesson, you will be able to:

1. Explain how method-security interceptors work and why **combining different annotation types means AND**.
2. Explain why `@PreAuthorize` cannot be repeated on the same method, and use a single SpEL expression or policy bean for `and`/`or`.
3. Distinguish annotations on **classes** and **methods**: a method-level annotation of the same type **overrides** the class-level one rather than adding to it.
4. Identify ambiguous inherited declarations from **multiple interfaces**, and resolve them with an explicit policy on the concrete method.
5. Use `@Secured` and `@RolesAllowed` properly when opted in, distinguishing `ROLE_`, roles, and authorities.
6. Combine pre/post invocation checks or collection filtering safely without checking permissions too late relative to side effects.
7. Write Spring tests directly against service beans to verify policies succeed or fail as required.

This lesson uses **Spring Security 6.x/7.x, Java 17+**, primarily on Spring-managed services in Servlet applications. Spring snippets require real dependencies and a Spring context. A standalone Java 17 program in section 12 illustrates composition logic without pretending to be Spring Security's implementation.

## 1. Foundation: Annotations Must Be Executed by Spring

`@PreAuthorize("hasRole('ADMIN')")` in source code **is not automatically** an executable Java statement. Spring Security needs method security enabled to register interceptors into Spring AOP.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

With Spring Security 6.x/7.x:

- `@EnableMethodSecurity` enables `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` by default.
- `@Secured` **is not enabled by default**; it requires `securedEnabled = true`.
- JSR-250 annotations (`@RolesAllowed`, `@PermitAll`, `@DenyAll`) **are not enabled by default**; they require `jsr250Enabled = true`.
- Spring Boot Starter Security does not automatically activate method security merely because you added the dependency.
- Annotations take effect only on calls **intercepted by Spring**. `new Service()`, self-invocation via `this`, methods not passing through the AOP proxy, or tests replacing the real bean with a mock can prevent checks from running.

If the application needs all three groups:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

**Do not enable everything just because it is available.** A codebase should select a minimal, consistent set of annotations to reduce conflicts and simplify reviews.

## 2. Common Annotation Types and Execution Timing

| Annotation | Check Point | Typical Semantics |
| --- | --- | --- |
| `@PreAuthorize` | Before invoking the method body | Evaluates SpEL over principal, authorities, arguments, or policy beans |
| `@PostAuthorize` | After the method returns a result | Evaluates SpEL against `returnObject`; denies returning the result if policy fails |
| `@PreFilter` | Filters input collection/array/map/stream in interceptor | Passes only valid elements to the method body |
| `@PostFilter` | Filters returned collection after invocation | Returns only allowed elements |
| `@Secured` | Before method; requires opt-in | Checks declared authorities/roles, less expressive than SpEL |
| `@RolesAllowed` | Before method; JSR-250, requires opt-in | Declares one or more allowed roles |
| `@PermitAll` | JSR-250, requires opt-in | Permits at the JSR-250 rule layer; does not bypass other interceptors |
| `@DenyAll` | JSR-250, requires opt-in | Denies at the JSR-250 rule layer |

**Note:** `@PostAuthorize` runs after the method body has already executed. It is **not** a safe sole barrier for write/delete/money-transfer/email-sending operations. `@PostFilter` does not replace query scoping and pagination at the database.

### Independent Interceptors

Spring Security uses separate method interceptors for different annotation types, for example:

- `@PreAuthorize`: `AuthorizationManagerBeforeMethodInterceptor#preAuthorize` paired with `PreAuthorizeAuthorizationManager`.
- `@PostAuthorize`: `AuthorizationManagerAfterMethodInterceptor#postAuthorize` paired with `PostAuthorizeAuthorizationManager`.
- `@PreFilter` and `@PostFilter`: dedicated filtering interceptors.
- `@Secured` and JSR-250: corresponding before-method interceptors when enabled.

They have an ordering in the **Spring AOP advisor chain**, not applied in the line order you typed annotations in the Java file. Spring Security documentation cites `@PreFilter` order 100 and `@PreAuthorize` order 200; advisor groups can be offset with `@EnableMethodSecurity(offset = ...)`. Unless you are designing custom advisors, **do not tweak ordering to try to "make one annotation beat another"**; write explicit policies instead.

## 3. Rule 1: Multiple Annotation Types Are Checked Sequentially (Meaning AND)

When **different** method-security annotation types apply to the same invocation, Spring Security runs the checks **sequentially**. The call is permitted only when **all required checks pass**. In terms of authorization decisions, that is **AND**, not OR.

Example:

```java
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceApprovalService {

    @Secured("ROLE_APPROVER")
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approve(long invoiceId) {
        return "approved:" + invoiceId;
    }
}
```

With `@EnableMethodSecurity(securedEnabled = true)`, this method requires:

```text
Can invoke approve(id) =
    has GrantedAuthority "ROLE_APPROVER"
    AND
    has GrantedAuthority "invoice:approve"
```

| Principal | Authorities | Outcome |
| --- | --- | --- |
| Alice | `ROLE_APPROVER`, `invoice:approve` | ALLOW |
| Bob | `ROLE_APPROVER` | DENY, missing `invoice:approve` |
| Carol | `invoice:approve` | DENY, missing `ROLE_APPROVER` |
| Dave | `ROLE_USER` | DENY |

**Do not think annotation line order makes "top win over bottom".** `@Secured` and `@PreAuthorize` belong to two different interceptor groups. When both are active, either group can deny the invocation.

### When Are Both Needed Together?

Combining them can help when a codebase is migrating from legacy role-based rules to fine-grained authorities. For a new design, however, it is usually clearer to express the same policy with **one** `@PreAuthorize`:

```java
@PreAuthorize(
    "hasRole('APPROVER') and hasAuthority('invoice:approve')"
)
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

`hasRole('APPROVER')` normally checks `ROLE_APPROVER` per the configured role prefix. `hasAuthority('invoice:approve')` checks **the exact string** without adding `ROLE_`.

**Do not manufacture permissions:** code must ensure `Authentication.getAuthorities()` truly contains the expected authorities. Someone holding `ROLE_ADMIN` **does not automatically hold** `invoice:approve` without an explicit mapping/hierarchy/policy granting it.

## 4. Rule 2: Do Not Repeat the Same Annotation Like `@PreAuthorize`

You cannot write two `@PreAuthorize` annotations on the same method expecting the framework to interpret AND or OR:

```java
// WRONG: @PreAuthorize is not a repeatable annotation.
@PreAuthorize("hasAuthority('invoice:read')")
@PreAuthorize("hasRole('AUDITOR')")
public Invoice readInvoice(long id) {
    // ...
}
```

This is an **invalid configuration example**, not compilable code. The Java compiler will report that the annotation is not repeatable; Spring Security also **does not support** repeating the same annotation type on one method.

**If both conditions are required (AND):**

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and hasRole('AUDITOR')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

**If either condition is accepted (OR):**

```java
@PreAuthorize(
    "hasAuthority('invoice:read') or hasRole('AUDITOR')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

Or:

```java
@PreAuthorize(
    "hasAnyAuthority('invoice:read', 'invoice:export')"
)
public Invoice readInvoice(long id) {
    // ...
}
```

`hasAnyAuthority` is OR across authorities. It does not create AND logic; `hasAnyRole('APPROVER', 'ADMIN')` is OR across roles with the matching prefix. Clearly distinguish OR **inside one expression** from AND across **different annotation types**.

### If a Policy Is Long, Extract a Bean Instead of Complex Nested SpEL

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.mayApprove(authentication, #invoiceId)"
)
public void approve(@P("invoiceId") long invoiceId) {
    // update after passing policy
}
```

`@P` is `org.springframework.security.access.method.P`; it explicitly names the parameter for SpEL without relying on compile-time parameter metadata. `invoicePolicy` is an application-implemented Spring bean checking server-side owner/tenant/state data. This is an **integration snippet**, requiring a real policy bean and method body. Never infer security solely from the name `mayApprove`; test the policy.

## 5. Rule 3: Same-Type Annotation on a Method Overrides Class-Level

Spring Security allows placing method-security annotations at the **class level** to apply a shared policy. If a method declares **the same annotation type**, the method-level declaration **overrides** the class-level one; it does not automatically **AND** with the class policy.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasAuthority('ledger:read')")
public class LedgerService {

    // Inherits class-level ledger:read.
    public String list() {
        return "listed";
    }

    // Overrides class-level with ledger:write.
    @PreAuthorize("hasAuthority('ledger:write')")
    public String update() {
        return "updated";
    }
}
```

Result:

| Authorities | `list()` | `update()` |
| --- | --- | --- |
| Only `ledger:read` | ALLOW | DENY |
| Only `ledger:write` | DENY | ALLOW |
| Both | ALLOW | ALLOW |
| Neither | DENY | DENY |

**Critical trap:** someone holding only `ledger:write` **can still call `update()`**, even without `ledger:read`, because method-level `@PreAuthorize` **replaces** class-level `@PreAuthorize`. Do not treat class-level annotations as a "mandatory baseline condition" assuming method-level annotations automatically add to them.

**If `update` must require both read and write:**

```java
@PreAuthorize(
    "hasAuthority('ledger:read') and hasAuthority('ledger:write')"
)
public String update() {
    return "updated";
}
```

Or extract a single policy bean/meta-annotation expressing the entire invariant. During code reviews, always check for this override whenever a class annotation is added to a service that already has method annotations.

### Same Annotation vs Different Annotation Types Are Not the Same Situation

```java
@Secured("ROLE_EMPLOYEE")
public class LedgerService {

    @PreAuthorize("hasAuthority('ledger:write')")
    public String update() {
        return "updated";
    }
}
```

When `securedEnabled = true`, `@Secured` (class-level) and `@PreAuthorize` (method-level) are **two different types**, so both can **apply together**. They do not form an override relationship like two `@PreAuthorize` annotations on class and method. The combined condition is `ROLE_EMPLOYEE AND ledger:write`.

## 6. Rule 4: Interface Inheritance Can Create Ambiguous Declarations

Method-security annotations can also live on **interfaces**. When an implementation inherits the same method from two interfaces and each interface specifies **a different security declaration**, Spring Security cannot automatically know which policy was intended. Spring Security 6.5/7.x docs state that such ambiguous inheritance can cause **startup failure**; resolve it with an explicit annotation on the concrete method.

**Common pitfall example:**

```java
public interface ReviewerApi {

    @PreAuthorize("hasAuthority('review:read')")
    String getReport(long reportId);
}

public interface AuditorApi {

    @PreAuthorize("hasAuthority('audit:read')")
    String getReport(long reportId);
}

// As a Spring-managed bean with method security enabled,
// inheriting two same-type policies from interfaces is ambiguous.
@Service
public class ReportQueryService implements ReviewerApi, AuditorApi {

    @Override
    public String getReport(long reportId) {
        return "report:" + reportId;
    }
}
```

This is an **invalid configuration example** for policy inheritance: imports/beans require a Spring project. Do not assume the annotation on the "leftmost interface" wins; `implements` order is not a security contract.

**Fix: place the desired policy on the concrete method**:

```java
@Service
public class ReportQueryService implements ReviewerApi, AuditorApi {

    @Override
    @PreAuthorize(
        "hasAuthority('review:read') and hasAuthority('audit:read')"
    )
    public String getReport(long reportId) {
        return "report:" + reportId;
    }
}
```

The example chooses **AND** per a hypothetical business policy. If the real product requires only one of the two permissions, change to `or` or `hasAnyAuthority` **per approved requirements**. Never fix a startup error by relaxing to `permitAll` or picking an interface arbitrarily.

**Note:** the before and after code are **two alternatives**; do not put both `ReportQueryService` classes in the same source. Whether using interface-based JDK proxies or class-based proxies, continue testing behavior under the actual AOP configuration.

## 7. Rule 5: Meta-Annotations Are Not a Workaround to Repeat the Same Annotation

A codebase may define business-meaningful annotations to avoid repeating long security expressions. Spring Security supports **meta-annotations** with `@PreAuthorize`/`@PostAuthorize` and compatible annotations.

Example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "hasRole('FINANCE')"
)
public @interface CanApproveInvoice {
}
```

A service can use:

```java
@Service
public class InvoiceService {

    @CanApproveInvoice
    public String approve(long invoiceId) {
        return "approved:" + invoiceId;
    }
}
```

The full condition lives inside the meta-annotation: `invoice:approve AND ROLE_FINANCE`. `@CanApproveInvoice` makes business intent readable at a glance and reuses the policy across multiple methods.

### Still Avoid Two Effective `@PreAuthorize`s at the Same Declaration Point

Do not treat the following as "adding one more condition":

```java
// Avoid: two @PreAuthorize sources on the same method.
@CanApproveInvoice
@PreAuthorize("hasAuthority('invoice:override')")
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

Even though the annotation names differ, `@CanApproveInvoice` **contains `@PreAuthorize`**. Combining them like this can create **two same-type declarations**/policy ambiguities rather than a guaranteed AND. **Merge** conditions into a single policy, or use a method-security annotation of a **different type** with tested semantics.

Avoid putting multiple composed annotations that both carry `@PreAuthorize` on the same method assuming their conditions will automatically AND. When meta-annotations are parameterized with templates, use the **annotation templates** feature of your exact Spring Security version and test the SpEL, rather than assuming string templates substitute automatically in every version.

### Object-Level Permissions and Bean Policies

A meta-annotation can wrap a richer policy:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
public @interface CheckInvoiceApproval {
}
```

Use on methods with stably named parameters, e.g., `@P("invoiceId") long id`. `invoicePolicy` must read invoice tenant/owner/status from server data, never trusting a client-asserted `tenantId`. This is an **integration** example without implementing the policy bean itself.

## 8. `@Secured` and `@RolesAllowed`: Opt-In, OR Within the Role Group

### `@Secured`

```java
@Secured({"ROLE_APPROVER", "ROLE_FINANCE"})
public String approve(long invoiceId) {
    return "approved:" + invoiceId;
}
```

A single `@Secured` accepts **multiple authorities**; this configuration accepts **any one of the listed authorities**, rather than requiring both. To require **both**, use `@PreAuthorize("hasAuthority('ROLE_APPROVER') and hasAuthority('ROLE_FINANCE')")`.

You must enable `@EnableMethodSecurity(securedEnabled = true)`. Without enabling it, writing `@Secured` in source does not mean Spring is enforcing it. Test it.

### `@RolesAllowed` (JSR-250)

```java
import jakarta.annotation.security.RolesAllowed;

@RolesAllowed({"OPERATIONS", "SUPPORT"})
public String export(long reportId) {
    return "exported:" + reportId;
}
```

With `@EnableMethodSecurity(jsr250Enabled = true)`, the role list represents **any one of the accepted roles**. In a default environment, `"OPERATIONS"` maps to `ROLE_OPERATIONS` in `GrantedAuthority` via the default role prefix. If the application customizes the role prefix or integrates a custom identity provider, test the exact mapping.

You can place `@RolesAllowed("OPERATIONS")` and `@PreAuthorize("hasAuthority('report:export')")` on the same method. Because they are **two annotation types**, **both the role and the authority** are required when both mechanisms are enabled.

### `@PermitAll` and `@DenyAll` Do Not Arbitrarily "Override" Other Checks

`@PermitAll` is a policy for JSR-250 interception, **not an instruction to turn off all of Spring Security**. If `@PreAuthorize`/`@Secured` also apply to the same invocation, those checks do not disappear just because another annotation permits. `@DenyAll` denies on the JSR-250 side when enabled.

**Never put both `@PermitAll` and `@DenyAll` on one method**, or mix them with opposing meta-annotations to "see which wins". A method needs one unified, reviewable, testable policy. For highly sensitive operations, use `@PreAuthorize("denyAll()")` or disable the entry point by policy and test it, never relying on accidental ordering among conflicting annotations.

## 9. `@PreAuthorize` + `@PostAuthorize`: Two Timings, Two Invariants

Example protecting **data reads** with functional permission beforehand and ownership afterward:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;

public record InvoiceView(
    long id,
    String owner,
    String summary
) {
}

@Service
public class InvoiceQueryService {

    @PreAuthorize("hasAuthority('invoice:read')")
    @PostAuthorize(
        "returnObject.owner().equals(authentication.name)"
    )
    public InvoiceView get(long id) {
        // Assume repository returns InvoiceView from trustworthy data.
        return new InvoiceView(id, "alice", "Invoice summary");
    }
}
```

This is a **Spring snippet**, requiring imports/framework, a service bean, and a real data layer when integrated. Execution conditions:

1. **Before running the method body:** requires `invoice:read`.
2. **After the method body returns a result:** checks `returnObject.owner()` against `authentication.name`.
3. Only when **both** succeed does the caller receive `InvoiceView`. If the post-check fails, the caller is denied **after the body has already run**.

This example expresses read-result leakage protection well, yet does not automatically solve query/tenant scoping; loading out-of-scope data before denial can still waste resources, pollute caches, or write unnecessary logs. In multi-tenant applications, **filter at the repository/query** and apply pre-read policies whenever possible.

### Why Not Use Post-Checks as the Guard for Write Actions?

```java
// WRONG TIMING if you want to prevent side effects.
@PostAuthorize("hasAuthority('payment:execute')")
public void transferMoney(...) {
    // The transfer command may have already been called before post-checking.
}
```

`@PostAuthorize` evaluates after invocation, so an HTTP 403 does not prove the transfer did not happen. Use `@PreAuthorize` or check before side effects, combined with transactions, locking/query conditions, and idempotency where appropriate. `@Transactional` cannot automatically roll back side effects outside the database.

## 10. `@PreFilter` and `@PostFilter` Combined with Authorization

`@PreFilter` and `@PostFilter` are not simply "true/false permission checks" for the whole call. They filter elements of collections/arrays/maps/streams according to policy.

Example of a method receiving a list of tasks:

```java
@PreFilter("filterObject.owner().equals(authentication.name)")
@PreAuthorize("hasAuthority('task:process')")
public List<Task> process(List<Task> tasks) {
    // The method body sees the pre-filtered list.
    return List.copyOf(tasks);
}
```

Meaning:

- `@PreAuthorize` protects **permission to invoke the process operation**.
- `@PreFilter` removes elements not owned by the caller from the incoming collection via the filtering mechanism.
- For an input collection to be filtered by removing elements, pass a suitable **mutable collection** and test the filtering behavior. Never assume passing immutable `List.of(...)` will always succeed.
- If the method has **multiple collection parameters**, specify `filterTarget` when needed to avoid target ambiguity.
- If business rules require **rejecting the entire batch when any item is unauthorized** (all-or-nothing), `@PreFilter` alone is not enough: dropping items can cause unwanted partial processing. Verify every item before writing or reject the batch.

`@PostFilter` runs after the method to filter collection results, but querying all rows and filtering in Java is usually inefficient and breaks pagination/counts. Push permission scoping down into database queries whenever possible.

**Ordering warning:** annotations run in separate interceptors with their own ordering; input filtering may run before another authorization rule depending on advisor ordering. Never design a method relying on filters/checks running in the exact source-line order.

## 11. Multi-Layer Conflicts: Resolution Matrix

| Situation | What Happens / What to Check | Resolution |
| --- | --- | --- |
| Two `@PreAuthorize` on one method | Repetition not supported; may fail to compile | Combine into **one SpEL** with `and`/`or` |
| `@PreAuthorize` on class and same type on method | Method-level **overrides**, does not AND | Write the complete required invariant on the method |
| Two interfaces declare different `@PreAuthorize` on one method | Ambiguous inherited policy; may fail startup | Place one explicit annotation on the concrete method |
| `@Secured` + `@PreAuthorize` | Two types, checked sequentially when both enabled → AND | Keep both with good reason or unify policy |
| `@RolesAllowed` + `@PreAuthorize` | Two types, checks both JSR-250 and SpEL if enabled | Test role prefix and authorities |
| `@PermitAll` alongside `@PreAuthorize` | Cannot assume PermitAll bypasses pre-check | Avoid misleading expressions, test policy |
| `@DenyAll` alongside an allowing annotation | Conflicting intent; do not rely on "who wins" | Pick one explicit business policy |
| Two custom annotations both containing `@PreAuthorize` | Effectively two ambiguous same-type sources | Merge SpEL into **one** meta-annotation |
| `@Secured` present while `securedEnabled=false` | Interceptor disabled, rule may not execute | Enable opt-in or switch to `@PreAuthorize` |
| `@RolesAllowed` present while `jsr250Enabled=false` | JSR-250 rules may not run | Enable opt-in, test service directly |
| `@PostAuthorize` on data-writing method | Check too late for side effects | Move blocking invariant to pre-check |
| Annotated method called via `this.method()` | Self-invocation can bypass proxy | Protect public entry point or extract bean |
| Same service mocked in tests | May skip real bean's interceptor | Test real bean, mock repository dependencies |
| HTTP rule allows yet service lacks role | Service can still deny | Test service exception and HTTP mapping |
| Anonymous or background job lacks context | Missing/unsuitable authentication | Design system identity/propagation, never default to admin |

**Resolution mindset:** first state the **business invariant** in plain prose, pick one primary place to declare the policy, then test both **allow and deny**. Never pick a mechanism simply because an annotation is easy to paste in.

## 12. Standalone Java 17: Simulating AND, OR, Override, and Ambiguous Policies

This example is a **plain Java 17** program that runs without Spring. It simulates combining checks (AND), method-level replacement, OR within one expression, and an explicit choice when two interfaces supply different policies. This is not how Spring AOP resolves annotations; it teaches how to **reason about authorization decisions**.

Save **`AnnotationCompositionDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class AnnotationCompositionDemo {

    record Actor(String name, Set<String> authorities) {
        boolean has(String authority) {
            return authorities.contains(authority);
        }
    }

    static boolean allPass(
        Actor actor, List<Predicate<Actor>> checks
    ) {
        return checks.stream().allMatch(check -> check.test(actor));
    }

    static String decision(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Actor approver = new Actor(
            "alice", Set.of("ROLE_APPROVER", "invoice:approve")
        );
        Actor roleOnly = new Actor(
            "bob", Set.of("ROLE_APPROVER")
        );
        Actor authorityOnly = new Actor(
            "carol", Set.of("invoice:approve")
        );

        List<Predicate<Actor>> combined = List.of(
            a -> a.has("ROLE_APPROVER"),
            a -> a.has("invoice:approve")
        );

        System.out.println(
            "Both checks, approver: " +
            decision(allPass(approver, combined))
        );
        System.out.println(
            "Both checks, role only: " +
            decision(allPass(roleOnly, combined))
        );
        System.out.println(
            "Both checks, authority only: " +
            decision(allPass(authorityOnly, combined))
        );

        Actor writer = new Actor(
            "writer", Set.of("ledger:write")
        );
        // Method-level policy replaces class-level policy:
        Predicate<Actor> classRead =
            a -> a.has("ledger:read");
        Predicate<Actor> methodWrite =
            a -> a.has("ledger:write");

        System.out.println(
            "Class rule, writer: " +
            decision(classRead.test(writer))
        );
        System.out.println(
            "Method override, writer: " +
            decision(methodWrite.test(writer))
        );

        Actor auditor = new Actor(
            "auditor", Set.of("audit:read")
        );
        // Two different interface policies require an explicit choice:
        // below intentionally chooses OR per the hypothetical requirement.
        Predicate<Actor> mergedRule =
            a -> a.has("review:read") || a.has("audit:read");

        System.out.println(
            "Explicit OR, auditor: " +
            decision(mergedRule.test(auditor))
        );
    }
}
```

Run with **JDK 17+**:

```bash
javac AnnotationCompositionDemo.java
java AnnotationCompositionDemo
```

**Exact stdout:**

```text
Both checks, approver: ALLOW
Both checks, role only: DENY
Both checks, authority only: DENY
Class rule, writer: DENY
Method override, writer: ALLOW
Explicit OR, auditor: ALLOW
```

Explanation:

- Both predicates are required simultaneously → **AND**; missing either authority yields DENY.
- In the method override simulation, `writer` lacks `ledger:read` yet holds `ledger:write`: the class rule alone DENIES, while the new method rule ALLOWS. It is **replacement**, not addition.
- Two sources requiring review/audit cannot be merged arbitrarily: the example **intentionally chooses OR** to show a business decision must be made. In a Spring implementation, write **one explicit policy** on the concrete method.
- The program does not read real annotations, create a `SecurityContext`, or test Spring proxies. To verify real framework behavior, use the tests in section 13.

## 13. Spring JUnit Test: Proving Real Annotation Composition

A proper test must obtain **real services from the Spring `ApplicationContext`**, enable the matching method security, use `@WithMockUser` to set up `Authentication`, and invoke methods **through the Spring bean proxy**. Never rely solely on HTTP statuses or plain Java tests on services instantiated via `new`.

Below is **a JUnit 5 class for a Spring test project** with compatible `spring-context`, `spring-security-config`, `spring-security-test`, `spring-test`, `jakarta.annotation-api`, and JUnit 5 dependencies. It cannot compile with plain JDK; Maven/Gradle with aligned versions/BOM is required.

```java
import jakarta.annotation.security.RolesAllowed;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(AnnotationCompositionTest.Config.class)
class AnnotationCompositionTest {

    @Autowired ApprovalService approvals;
    @Autowired LedgerService ledgers;
    @Autowired ExportService exports;

    @Test
    @WithMockUser(authorities = {"ROLE_APPROVER", "invoice:approve"})
    void bothAnnotationsMustPass() {
        assertEquals("approved:42", approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "ROLE_APPROVER")
    void roleWithoutFineGrainedAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "invoice:approve")
    void authorityWithoutRoleIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.approve(42L));
    }

    @Test
    @WithMockUser(authorities = "ledger:write")
    void methodLevelPreAuthorizeOverridesClassLevel() {
        assertEquals("updated", ledgers.update());
        assertThrows(AccessDeniedException.class, ledgers::list);
    }

    @Test
    @WithMockUser(authorities = {"ROLE_OPERATIONS", "report:export"})
    void jsr250AndPreAuthorizeBothPass() {
        assertEquals("exported", exports.export());
    }

    @Test
    @WithMockUser(authorities = "report:export")
    void jsr250RoleIsStillRequired() {
        assertThrows(AccessDeniedException.class, exports::export);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "invoice:read")
    void postCheckRejectsWrongOwnerAfterMethodRuns() {
        assertThrows(AccessDeniedException.class,
            () -> approvals.view(42L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:read")
    void postCheckAllowsOwner() {
        assertEquals("alice", approvals.view(42L).owner());
    }

    @Configuration
    @EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
    static class Config {
        @Bean ApprovalService approvals() {
            return new ApprovalService();
        }
        @Bean LedgerService ledgers() {
            return new LedgerService();
        }
        @Bean ExportService exports() {
            return new ExportService();
        }
    }

    public static class ApprovalService {
        @Secured("ROLE_APPROVER")
        @PreAuthorize("hasAuthority('invoice:approve')")
        public String approve(long id) {
            return "approved:" + id;
        }

        @PreAuthorize("hasAuthority('invoice:read')")
        @PostAuthorize("returnObject.owner() == authentication.name")
        public InvoiceView view(long id) {
            return new InvoiceView(id, "alice");
        }
    }

    public record InvoiceView(long id, String owner) {}

    @PreAuthorize("hasAuthority('ledger:read')")
    public static class LedgerService {
        public String list() {
            return "listed";
        }

        @PreAuthorize("hasAuthority('ledger:write')")
        public String update() {
            return "updated";
        }
    }

    public static class ExportService {
        @RolesAllowed("OPERATIONS")
        @PreAuthorize("hasAuthority('report:export')")
        public String export() {
            return "exported";
        }
    }
}
```

**Why this test matters:**

- Verifies both `@Secured` + `@PreAuthorize` annotation types actually work (not just sitting in source).
- Verifies class/method override is **not AND** for the same `@PreAuthorize` type.
- Verifies `@RolesAllowed` is an independent JSR-250 interceptor with its own role check when enabled.
- Verifies `@PostAuthorize` can deny **after the method has produced a result**.
- Contains no controllers or URLs: these are pure **method-security tests** at the service boundary.
- `@WithMockUser(authorities = {...})` declares the full authority set; **do not** combine `roles` and `authorities` on the same annotation if your test support version forbids it.
- The test context uses nested `public static` classes so Spring AOP can create proxies; real service beans are injected. Depending on your project and custom configuration, verify classpath/proxy strategies in the target environment.

**Do not place the "two conflicting interfaces" example into this same test context**, because it is designed to demonstrate a configuration that **can prevent the context from starting**. Write a **separate context initialization test** for the conflicting class and a working context test after adding the explicit annotation, isolated from integration suites expected to stay green.

## 14. Testing Conflict Resolution, Inheritance, and Meta-Annotations

A useful QA matrix:

| Test Case | Input | Expected |
| --- | --- | --- |
| Two annotation types with AND | Has role only, lacks authority | DENY |
| Two annotation types with AND | Has both role + authority | ALLOW |
| One `@PreAuthorize` with OR | Has only one of two authorities | ALLOW per policy |
| Same-type class-level and method-level | Has method permission only | ALLOW method, does not require class permission |
| Interface conflict | Two interfaces have different `@PreAuthorize` | Detect ambiguity, resolve with concrete method policy |
| Single meta-annotation | User satisfies policy inside meta | ALLOW |
| Meta-annotation policy | User misses one condition | DENY |
| `@Secured` not enabled | Annotation present while interceptor off | Do not assume protection; test detects and fix config |
| JSR-250 enabled | User has role + permission | ALLOW |
| JSR-250 enabled | User has permission only | DENY due to missing role |
| Pre + Post | Sufficient permission but wrong owner | DENY after invocation |
| Pre + Post | Sufficient permission and matching owner | ALLOW |
| Anonymous | Lacks required permissions | DENY |
| Self-invocation | `this.annotatedMethod()` | Test for proxy bypass and fix design |
| Production object policy | Has role yet document belongs to another tenant | DENY at service/query |
| Side-effecting operation | User denied before writing | Repository/external calls never invoked |

### How to Test Startup Ambiguity in a Project

1. Define two interfaces with **different same-type policies** on the same method signature.
2. Create a concrete bean implementing both without declaring an explicit policy.
3. Boot an application context with `@EnableMethodSecurity` to observe the ambiguity error in your exact version; keep this test isolated from suites expecting startup success.
4. Add **one** annotation on the concrete method expressing the reviewed policy.
5. Re-run the context test, then use `@WithMockUser` to test both ALLOW and DENY. Never treat "it booted" as proof the permissions are right.

### Observing Side Effects

For operations that write to the DB or emit events, DENY tests must assert:

- the method body did not run when a pre-check denies;
- repository update/delete was not called;
- no events were published, emails sent, or external APIs called;
- transactions persisted no unintended mutations.

Never assert only an HTTP 403 and conclude every internal operation was blocked: 403 could come from HTTP authorization, CSRF, or `@PostAuthorize` after side effects already ran.

## 15. Common Design Mistakes

1. **Treating multiple annotations as OR:** co-applied method security check types generally **must all pass**.
2. **Repeating `@PreAuthorize` twice on a method:** annotation is not repeatable and unsupported. Use one expression.
3. **Believing class-level `@PreAuthorize` always adds to method-level `@PreAuthorize`:** method-level **overrides** class-level policy.
4. **Inheriting different annotations from two interfaces expecting Spring to pick one:** requires an explicit policy on the implementation.
5. **Stacking multiple meta-annotations containing `@PreAuthorize` on one method:** creates ambiguity with no guaranteed AND.
6. **Treating `hasRole('ADMIN')` and `hasAuthority('ADMIN')` as equivalent:** roles usually carry the `ROLE_` prefix.
7. **Mistaking `@Secured({"ROLE_A","ROLE_B"})` for AND:** the list accepts **any one of the authorities**.
8. **Adding `@Secured` without `securedEnabled=true`:** the annotation may stay inactive.
9. **Adding `@RolesAllowed` without `jsr250Enabled=true`:** JSR-250 policies may be ignored.
10. **Using `@PermitAll` to try bypassing another `@PreAuthorize`:** permission from one group does not disable other interceptors.
11. **Putting `@PostAuthorize` on write/delete commands:** post-checking is too late to guarantee no side effects.
12. **Using `@PostFilter` as a replacement for query scoping:** wastes memory, breaks pagination, or leaks internal data prior to filtering.
13. **Using `@PreFilter` for all-or-nothing batches:** filtering silently drops items instead of DENYING the whole request.
14. **Assuming annotation line order equals execution order:** AOP advisors have their own ordering.
15. **Forgetting proxies/self-invocation:** annotations on methods called via `this` may not be intercepted.
16. **Testing with `new Service()` or mocking the service itself:** does not verify Spring method security.
17. **Relying on HTTP 403 to conclude all annotations ran:** requests may be blocked before the method by CSRF/HTTP policies.
18. **Omitting object/tenant permission checks:** roles and authorities are only one layer and do not authorize every ID.
19. **Mixing Spring Security 5.x/6.x/7.x conventions untested:** older frameworks have different semantics/annotations; run migration tests.
20. **Picking a policy just to make context startup succeed:** ambiguity must be resolved according to business invariants, not interface order.

## 16. Implementation and Code Review Checklist

- [ ] Application enables `@EnableMethodSecurity` in the context containing protected services.
- [ ] `securedEnabled`/`jsr250Enabled` are enabled only if the application actually uses those annotations.
- [ ] For multiple annotations of **different types**, AND semantics and check timing of each type are verified.
- [ ] For multiple conditions inside **one annotation**, `and`, `or`, or `hasAnyAuthority` matches policy.
- [ ] No repeated `@PreAuthorize` or multiple composed annotations sourcing `@PreAuthorize` on one method.
- [ ] Same-type method-level annotations are reviewed as **overrides** of class-level, not additions.
- [ ] No method inherits ambiguous policies from two interfaces; concrete methods carry clear policies.
- [ ] Role prefixes are properly mapped to `ROLE_`/custom hierarchies/real authorities.
- [ ] Policy beans use trustworthy identity/owner/tenant data, never client-declared values.
- [ ] For write operations, authorization blocks **before** side effects; never rely solely on `@PostAuthorize`.
- [ ] For filtering, partial filtering vs all-or-nothing is chosen intentionally per business rules.
- [ ] Services are called through **Spring-managed proxies**; avoid self-invocation or manual instantiation bypasses.
- [ ] Direct-service JUnit tests cover ALLOW, DENY, overrides, `@Secured`/JSR-250 combinations, and post-checks.
- [ ] If HTTP controllers exist, test HTTP rules, CSRF, and exception mapping separately; URL tests do not replace method tests.
- [ ] Include context-startup and security regression tests in CI before upgrading Spring Security.

### Self-Check Questions

**Question 1.** A method has `@Secured("ROLE_APPROVER")` and `@PreAuthorize("hasAuthority('invoice:approve')")`. Is a principal holding only `ROLE_APPROVER` allowed?

**Answer:** **No**, if both interceptors are enabled. These are two co-applied annotation types, so both the role and the authority are required.

**Question 2.** Class has `@PreAuthorize("hasAuthority('ledger:read')")`, while `update` has `@PreAuthorize("hasAuthority('ledger:write')")`. Can a user with only write permission call `update`?

**Answer:** **Yes**, if the call is intercepted and no other independent check exists: a method-level annotation **overrides** the same type at the class level. If both read and write are required, express both conditions explicitly on the method.

**Question 3.** Can you put `@PreAuthorize("hasRole('ADMIN')")` and `@PreAuthorize("hasAuthority('invoice:delete')")` on the same method to get OR?

**Answer:** **No**. Use **one** `@PreAuthorize` with `or`, or `and` if both are mandatory.

**Question 4.** A class implements two interfaces, each with a different `@PreAuthorize` on the same method. Which interface should Spring pick?

**Answer:** **Do not pick arbitrarily**; this is ambiguous inheritance that can prevent the application context from starting. Put an approved policy on the concrete method and test it.

**Question 5.** A money transfer method has `@PostAuthorize("hasAuthority('payment:send')")` and denies access; does that prove no money was transferred?

**Answer:** **No**. The body runs before post-checking; put the condition in a pre-check and ensure transaction/side-effect safety.

## Official References

- Spring Security 6.5, *Method Security*: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0, *Method Security*: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security, *Testing Method Security*: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security, *Spring MVC Authorization / HTTP Rules*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework, *Proxying Mechanisms and Self Invocation*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
