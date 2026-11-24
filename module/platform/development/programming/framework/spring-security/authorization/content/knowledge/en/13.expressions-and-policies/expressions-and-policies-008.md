# Never Turn Untrusted Input into SpEL Code

## 1. Core issue: separating **policy code** from **data**

In Spring Security, SpEL (Spring Expression Language) often appears in `@PreAuthorize`, `@PostAuthorize`, and custom authorization components. An expression is **code evaluated inside the application**: it can perform comparisons, boolean logic, property access, method invocations, and—depending on `EvaluationContext`—reference other Java/Spring components.

**Safety rule:** untrusted sources may only supply **data values** consumed by a developer-defined policy. Never concatenate those values into a SpEL string and pass the resulting string to `parseExpression(...)` or an equivalent expression engine.

For instance, a user submits a string via URL, form, or JSON. That string may be a document title, search term, or resource ID. The application may compare it against verified data, but **must never let that string dictate operators or authorization branches**.

Lesson objectives:

- Trace paths from external data to an expression parser and identify SpEL injection risks.
- Distinguish **referencing values** via parameters/variables from **interpolating content into expression syntax**.
- Use fixed `@PreAuthorize` expressions, Java policy beans, and trusted resource checks to protect methods.
- Understand the limits of validation, escaping, `SimpleEvaluationContext`, and role-based checks.
- Write tests with inputs containing quotes, logical operators, and code-like expressions to ensure they remain pure data.

## 2. What is SpEL injection, and why is it serious?

**SpEL injection** occurs when an application takes an untrusted string and lets it become **part of the SpEL syntax parsed or evaluated**. When that happens, whoever supplied the string can alter logic, flip true/false branches, or—with a powerful evaluation context—trigger unintended interactions with application objects and methods.

Spring Framework documentation warns that SpEL can invoke methods/constructors, read/write properties, and reference beans depending on configuration; therefore **do not evaluate SpEL expressions originating from untrusted sources**. Actual impact depends on the evaluator, root object, resolvers, variables, and exposed methods. Do not assume every SpEL site leads straight to remote code execution; equally, never assume user-supplied expressions are harmless just because they "look like a condition."

Input sources that must be treated as **untrusted** include:

- Query parameters, path variables, headers, cookies, JSON bodies, uploaded fields, and WebSocket messages.
- Client-submitted `filter`, `sort`, `condition`, or `permissionExpression` fields.
- Database records editable by users, queue payloads, third-party imported config files, partner APIs.
- Strings inside tokens/claims—even when token signatures are verified—if the producer is not authorized to define executable policy.

Even a valid role or permission inside `Authentication` is still **authorization data issued by a trusted system**; never turn those strings into dynamic SpEL code.

**Practical trust boundary:** developers or administrators authorized to author policies may provide **controlled** expressions; regular business users do not have that privilege. If a product intends to let "users build their own rules," design a constrained DSL or structured condition form evaluated by vetted Java code rather than opening a SpEL parser to arbitrary expressions.

## 3. Anti-pattern: concatenating input strings into expressions

Suppose a custom feature takes `filter` from a request and reuses it inside an authorization condition. The code below is an **anti-pattern illustration**, not a recommended implementation:

```java
// DO NOT USE: filter comes directly from the request.
String filter = request.getParameter("filter");
String expressionText =
    "hasAuthority('document:read') and #sameTenant " + filter;

// The application then passes expressionText into a SpEL evaluator.
Expression expression = new SpelExpressionParser()
    .parseExpression(expressionText);
```

This snippet assumes the app sets up a matching `EvaluationContext` with authorization variables and functions. The flaw occurs **before** considering the evaluator: `filter` can alter the parsed statement's structure.

For example, if the input is not constrained to a data value and can contain an `or` operator, the appended branch can make the whole condition evaluate to true. That is a **policy bypass**, not merely a malformed search query.

Risky flow:

```text
User-controlled HTTP/JSON/DB
            |
            v
Concatenate String, String.format, or template into a "formula"
            |
            v
SpelExpressionParser.parseExpression(formula)
            |
            v
Expression.getValue(context) -> unintended decision or behavior
```

Not only `+` concatenation is dangerous: `String.format(...)`, `MessageFormat`, template engines, stitching config fragments, or generating expressions from database columns all create the same broken boundary if any part comes from an untrusted source.

**Another mistake:**

```java
// DO NOT USE: owner value from request placed directly into SpEL string.
String ownerFromRequest = request.getParameter("owner");
String expressionText =
    "authentication.name == '" + ownerFromRequest + "'";
```

Single quotes inside data can break out of how the parser reads a literal. Trying to patch this by replacing a few characters or escaping manually easily misses edge cases and preserves the flawed "data-as-code" design.

## 4. The right way: fixed expressions, data via variables or parameters

### In Spring Security Method Security

Use an expression **fixed in source code**; pass external IDs strictly as method parameters:

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
        "isAuthenticated() and hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

Here:

1. `@PreAuthorize(...)` contains a developer-authored policy, with no request content concatenated into syntax.
2. `#documentId` is the **value** of the Java argument at call time; Spring Security does not re-parse the ID string as a SpEL program.
3. `authentication` is the authentication object provided by Spring Security.
4. `@documentPolicy.canRead(...)` invokes a registered policy bean; the bean matches the caller against the resource in the database.
5. `@P("documentId")` names the parameter explicitly when reflection or builds do not retain parameter names. For method security to run, `@EnableMethodSecurity` must be enabled.

**Boundary note:** do not rewrite this as `hasAuthority(#permissionFromRequest)` when the intent is requiring a fixed `document:read` authority. Using `#permissionFromRequest` causes no syntax injection, yet creates an **authorization logic flaw**: callers get to pick which authority is checked. Preventing SpEL injection and designing sound policies are two separate requirements.

### Policy beans using trusted data sources

The snippet below is a **Spring Boot application component**, assuming `DocumentRepository` and `TenantMembershipService` are implemented beans; entity getters and membership methods represent an illustrative business interface:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantMembershipService membership;

    public DocumentPolicy(
            DocumentRepository documents,
            TenantMembershipService membership) {
        this.documents = documents;
        this.membership = membership;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || documentId == null) {
            return false;
        }

        return documents.findById(documentId)
            .filter(doc -> membership.canAccess(auth, doc.getTenantId()))
            .filter(doc -> auth.getName().equals(doc.getOwnerUsername()))
            .isPresent();
    }
}
```

In a real application, `membership.canAccess` must verify membership/tenant from server-controlled data, not merely match a client-sent `X-Tenant-Id` header. The service above also uses `isAuthenticated()` to block anonymous callers upfront. ACLs or sharing rules can be added in the policy per business requirements; ID-based reads must ensure unauthorized data is never leaked.

This example illustrates **strict ownership**. If owners, groups, admins, tenants, and sharing follow different rules, write Java policies and explicit tests; never assemble formulas from the client.

### When using the SpEL API directly

If a feature genuinely needs SpEL for an **application-defined expression**, parse a fixed syntax and supply dynamic values to `EvaluationContext` as variables:

```java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

ExpressionParser parser = new SpelExpressionParser();

// Trusted because the string is defined by the developer.
Expression fixed = parser.parseExpression("#candidate == #expected");

String rawCandidate = inputFromRequest; // value may contain quotes, parentheses...
String expected = valueFromTrustedSource;

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("candidate", rawCandidate);
context.setVariable("expected", expected);

boolean matches =
    Boolean.TRUE.equals(fixed.getValue(context, Boolean.class));
```

This is a **snippet inside an application with the `spring-expression` dependency**, not a standalone runnable program. `rawCandidate` is placed strictly into `#candidate`, never concatenated into `"#candidate == #expected"` and never parsed a second time. For simple comparisons, plain Java such as `rawCandidate.equals(expected)` is even clearer and needs no SpEL at all.

**Note:** `StandardEvaluationContext` enables powerful capabilities; the snippet above is safe against injection only because **the expression string is fixed and trusted**. Never assume setting variables makes every object or data operation inherently safe. Authorization must still rely on trusted data sources and conditions.

## 5. Do not confuse three different security situations

| Situation | What can go wrong? | Prevention |
| --- | --- | --- |
| Input becomes part of the string passed to `parseExpression` | **SpEL injection**: user alters expression structure/behavior | Never parse user-created expressions; use fixed policies and data variables |
| Input is just `#requestedRole` inside a fixed expression | No SpEL syntax injected, yet user can choose which permission is checked | Developers fix required permissions; never let clients pick the policy |
| Input is `#ownerId` compared against a client-supplied ID | Not necessarily injection, yet can cause **IDOR / broken ownership check** | Fetch real owner/tenant/ACL from the database and verify server-side |

An especially dangerous **logic** flaw even with zero SpEL syntax injection:

```java
// Wrong policy if the caller gets to choose the required role:
@PreAuthorize("hasRole(#requestedRole)")
public void execute(String requestedRole) {
    // ...
}
```

Users can submit a low-privilege role they already hold instead of the high-privilege role the business requires. Right approach when an action is admin-only:

```java
@PreAuthorize("hasRole('ADMIN')")
public void executeAdminAction() {
    // ...
}
```

Conversely, if checks depend on a specific resource, fix the expression using a policy bean: `@PreAuthorize("@policy.canRead(authentication, #id)")`. Never assume "using `#arg`" automatically means safe: examine **what `#arg` is trusted to decide**.

## 6. Choosing a policy from a fixed set, not accepting arbitrary code

Suppose an API lets users request `view` or `download` actions. The `action` field is a **selection label**, not a Spring expression string:

```java
public boolean mayPerform(
        String action,
        Authentication authentication,
        Long documentId) {
    if (action == null) {
        return false;
    }

    return switch (action) {
        case "view" -> policy.canRead(authentication, documentId);
        case "download" -> policy.canDownload(authentication, documentId);
        default -> false;
    };
}
```

This snippet belongs to a service with a `policy` bean, not a standalone program. With `default -> false`, unknown actions are denied. Each Java method still performs real permission checks rather than relying solely on the action name being allowlisted. Use an `enum` to eliminate free-form strings and validate inputs before reaching the service.

If a product wants users to filter lists, design structured data input such as `{field: "status", operator: "eq", value: "OPEN"}`. The server accepts only allowlisted `field` and `operator` values and translates them via code into query criteria/query APIs. **Never convert client-supplied expressions wholesale into SpEL**. Separately enforce access permissions on fields and returned records.

## 7. Do `SimpleEvaluationContext`, escaping, and validation replace proper design?

### `StandardEvaluationContext` vs. `SimpleEvaluationContext`

- `StandardEvaluationContext` exposes full SpEL language and reflection capabilities; **never use it to run expressions from untrusted sources**.
- `SimpleEvaluationContext` restricts features and targets data-binding use cases, e.g., omitting type references, constructors, and beans; however, Spring Framework notes these restrictions are not an **absolute security guarantee** for untrusted expressions. Exposed objects, properties, methods, and functions in the context still require strict review.

Therefore, **never switch from `StandardEvaluationContext` to `SimpleEvaluationContext` and conclude it is safe to let users enter arbitrary SpEL**. The primary defense is not parsing input as an expression language at all. If an exceptional requirement mandates externally supplied expressions, you need a dedicated threat model, restricted evaluator, purpose-built target objects, allowlisted features, and security review—while recognizing residual risk.

### Why quote-escaping alone is insufficient

A common quick patch looks like:

```java
// Do not treat this as a complete SpEL injection prevention mechanism.
String sanitized = userInput.replace("'", "''");
String expression = "someProperty == '" + sanitized + "'";
```

Even if quoting yields a valid string literal in one narrow case, this design breaks easily wherever inputs are interpolated (parentheses, property names, method names, operator order, nested templates...) and fails to stop authorization logic flaws where users pick policies. **Using variables or typed Java APIs instead of string-built expressions** is the default choice.

Validation is not an execution-safety switch either: length limits, format rules, and action allowlists are useful data checks, yet **never authorize turning a free-form string into SpEL code**. When malformed rule config is detected, deny and log safely—never return `true` or relax conditions to keep running.

## 8. Static annotations and Spring Security templates

A common point of confusion: standard Java annotations use compile-time constant values:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and " +
    "@invoicePolicy.canRead(authentication, #invoiceId)"
)
public Invoice readInvoice(Long invoiceId) {
    // ...
}
```

This string **does not splice HTTP parameter values into annotation code**. `#invoiceId` is a method context variable. You cannot dynamically turn an arbitrary request value into a Java annotation value at runtime given how standard Java annotations work.

Spring Security also supports **meta-annotation templating** when `AnnotationTemplateExpressionDefaults` is configured. Official documentation illustrates this pattern:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface HasRole {
    String value();
}
```

With `@HasRole("ADMIN")` in source code, the `{value}` placeholder comes from developer-controlled annotation metadata. When using templates:

- Confirm every substitution source is **controlled metadata**; never let clients or user-editable records supply content directly into SpEL.
- Quote literals carefully per template syntax and value types (single string, list, variable name); test the expanded result.
- If external config holds business rules, parse them into enums/data structures handled by Java policies or controlled authorization managers.

Do not treat template `{value}` syntax as proof that Spring automatically "parameterizes" everything: **template replacement generates expression code**, unlike passing runtime values into `#value` variables.

## 9. Standalone runnable Java 17 example: malicious data is never executed

This example models a Java policy with server-side resource data. It **runs no SpEL** and requires no Spring, proving that operator-shaped strings remain inert data when the program never parses them.

Save verbatim as `TrustBoundaryDemo.java`:

```java
import java.util.Set;

public class TrustBoundaryDemo {
    record Actor(String username, String tenantId, Set<String> authorities) {}
    record Document(long id, String tenantId, String ownerUsername) {}

    static boolean canRead(Actor actor, Document document) {
        return actor.authorities().contains("document:read")
            && actor.tenantId().equals(document.tenantId())
            && actor.username().equals(document.ownerUsername());
    }

    public static void main(String[] args) {
        String untrustedText = "or true";
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of("document:read"));
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of("document:read"));

        Document aliceDoc = new Document(1, "tenant-a", "alice");
        Document otherTenantDoc = new Document(2, "tenant-b", "alice");

        System.out.println("Untrusted input: " + untrustedText);
        System.out.println("Bob reads Alice doc: "
            + canRead(bob, aliceDoc));
        System.out.println("Alice reads own doc: "
            + canRead(alice, aliceDoc));
        System.out.println("Alice reads other tenant doc: "
            + canRead(alice, otherTenantDoc));
    }
}
```

Run with JDK 17 or higher:

```bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
```

Stdout:

```text
Untrusted input: or true
Bob reads Alice doc: false
Alice reads own doc: true
Alice reads other tenant doc: false
```

Nowhere is `untrustedText` concatenated into code for parsing. It is printed yet never used for authorization, and policy outcomes remain governed by trusted authority, tenant, and owner values. This also shows that **injection-free input handling** and **resource authorization** must both be achieved together.

## 10. Key testing practices for real applications

### Testing parse paths and edge-case values

For features accepting client strings, submit empty strings, `null`, single/double quotes, parentheses, `and`/`or`/`not` strings, property names, method-call-like strings, long whitespace, and Unicode strings. Expect:

1. Those strings are handled strictly as **values**, never altering authorization rules.
2. `parseExpression` **never receives** content originating from requests or user-editable data.
3. Invalid input is rejected per data validation rules; no "allow on parse error" fallback exists.
4. No stack traces, context data, bean names, or sensitive resource info leak to clients.
5. For the same identity and resource, changing input strings never escalates privileges.

For fixed SpEL `#candidate == #expected`, tests passing code-like strings in `candidate` must behave like plain string comparison, with zero re-parsing of variable contents.

### Testing actual permissions

Create test fixtures spanning multiple tenants, owners, roles, and authorities; verify allow/deny per table:

| Caller | Authority | Resource | Expected outcome |
| --- | --- | --- | --- |
| Alice | `document:read` | Alice's document, same tenant | Allow |
| Bob | `document:read` | Alice's document, same tenant | Deny by owner policy |
| Alice | `document:read` | Document in another tenant | Deny |
| Alice | Missing `document:read` | Alice's document | Deny |
| Anonymous | No permissions | Any document | Deny |

For method security, run tests through **Spring-managed beans/proxies**, since internal `this.method()` calls bypass advice. When using `@WithMockUser` or security test contexts, verify authorities and method outcomes rather than calling policy methods directly in unit tests alone.

### Auditing the codebase

Search for places building and evaluating SpEL—especially data paths from controllers, requests, databases, queues, or external config into:

- `SpelExpressionParser` / `ExpressionParser.parseExpression(...)`.
- `Expression.getValue(...)`, `EvaluationContext`, `StandardEvaluationContext`, custom bean or method resolvers.
- `String.format(...)`, `+` concatenation, `StringBuilder`, or templates generating policy strings.
- Custom authorization managers, DB-stored expressions, rule builders, and meta-annotation templates.

Seeing `parseExpression` alone is **not enough** to conclude a vulnerability exists; trace the origin of the expression text and who controls it. Similarly, a static `@PreAuthorize` using `#arg` is not automatically vulnerable to injection. Nonetheless, any path feeding untrusted **expression syntax** into authorization must be remediated before use.

## 11. Remediation steps when code parses user input

1. **Stop treating input as a formula:** identify what the user actually needs to supply—an ID, keyword, filter operator, action type, or permission code.
2. **Redefine the API contract:** accept primitives, enums, or schema-validated JSON; remove "arbitrary SpEL" input fields.
3. **Move policies into trusted code:** use fixed `@PreAuthorize` expressions, Java policy beans, or reviewed `AuthorizationManager`s.
4. **Bind permissions to resources:** read owner, tenant, membership/ACL from server/database; push permission predicates into queries for large lists.
5. **Avoid powerful evaluators for free-form input:** especially never feed user strings into `StandardEvaluationContext` as expressions. Restricting context is defense-in-depth, not a substitute for removing input parsing.
6. **Fail closed on errors:** unknown rules, unknown actions, missing permission data, or verification errors must deny safely per API contract.
7. **Add regression tests:** include strings with quotes/operators, cross-tenant cases, insufficient roles, and run static analysis or code reviews along paths reaching parsers.
8. **Track dependency versions:** keep Spring Framework, Spring Security, and related libraries updated per official advisories; upgrading patches framework flaws, yet does not fix an application's broken input→expression design.

### Quick rule of thumb

**The application controls authorization syntax; request data is strictly arguments.** Use `#argument` or context variables to pass values into fixed expressions—or better yet, write resource checks in Java querying trusted data. Never let clients, editable records, or partner payloads dictate **which SpEL code gets parsed and executed**.

## Official Documentation

- [Spring Framework — SpEL Evaluation, Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html): distinguishing `StandardEvaluationContext` and `SimpleEvaluationContext`, warnings on untrusted expressions.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): SpEL syntax, variables, and expression elements.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `#argument`, policy beans, and template meta-annotations.
