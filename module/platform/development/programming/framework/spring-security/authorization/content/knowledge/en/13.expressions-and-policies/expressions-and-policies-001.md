# SecurityExpressionRoot and the Security Expression Context in Spring Security

## 1. The problem: what does an expression know about the user and the resource?

Suppose an application needs the rule: "The owner may read their own invoice; an administrator may read everyone's invoices." We can attach it to a service method:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
public Invoice readInvoice(@P("owner") String owner) {
    // Load the invoice belonging to owner from the repository.
}
```

This is a **method signature snippet** (not a standalone runnable program). The reason a short expression can use `hasRole`, the `#owner` parameter, and `authentication.name` together is the **security expression evaluation context**. At the center of that context is **`SecurityExpressionRoot`**: the base root class providing the common permission checks and security properties when Spring Security evaluates SpEL.

It is important to distinguish:

- **Authentication** describes the authenticated identity, the `principal`, and the set of `GrantedAuthority` instances.
- **SecurityContext** holds the `Authentication` associated with the current execution thread/context (according to `SecurityContextHolderStrategy`).
- **SecurityExpressionRoot** exposes convenience APIs such as `hasAuthority`, `hasRole`, `isAuthenticated`, `authentication`, and `principal` for SpEL to use.
- SpEL's **EvaluationContext** wraps the root object and supplies parameter variables, bean resolvers, property/method accessors, type converters, and more, depending on Spring Security's configuration.
- The **AuthorizationManager** / interceptor uses the expression result to allow or deny the action.

Therefore, `SecurityExpressionRoot` is neither "the currently logged-in user" nor a permission database itself. It is the **semantic bridge** between security data managed by Spring and authorization expressions declared by the application.

## 2. Where does SecurityExpressionRoot sit in the architecture?

`SecurityExpressionRoot` belongs to the package:

```text
org.springframework.security.access.expression.SecurityExpressionRoot
```

It is an **abstract class** implementing the `SecurityExpressionOperations` contract. In Spring Security 6.x, the key specialized root objects include:

| Context | Root / related component | Context-specific data |
|---|---|---|
| Method Security expressions | `MethodSecurityExpressionRoot` extends `SecurityExpressionRoot`, implements `MethodSecurityExpressionOperations` | Method parameters, `returnObject`, `filterObject`, target object being invoked |
| HTTP/web expressions | `WebSecurityExpressionRoot` extends `SecurityExpressionRoot` | Web request context, when using the web expression evaluator |
| Other cases | Root/evaluation context provided by the corresponding security mechanism | Depends on integration and version |

**Specifically:** the modern `authorizeHttpRequests` API typically uses Java-typed `AuthorizationManager` implementations, such as `.hasAuthority("invoice:read")`. Not every HTTP authorization configuration creates or evaluates a SpEL string. Only when `WebExpressionAuthorizationManager` is explicitly used does a web expression become central.

For **Method Security** enabled via `@EnableMethodSecurity`, the high-level flow is:

```text
A call to a Spring bean through an AOP proxy
    ↓
AuthorizationManagerBeforeMethodInterceptor (e.g., @PreAuthorize)
    ↓
PreAuthorizeAuthorizationManager
    ↓
MethodSecurityExpressionHandler
    ├── Authentication (typically supplied via Supplier<Authentication>)
    ├── MethodInvocation: method, target, arguments
    └── MethodSecurityEvaluationContext
          ├── root = MethodSecurityExpressionRoot
          ├── variables: #owner, #p0, ...
          └── bean reference: @invoicePolicy
    ↓
Evaluate SpEL → true / false
    ├── true: allow the method to execute
    └── false: deny; typically throws AccessDeniedException
```

With `@PostAuthorize`, evaluation happens **after the method executes**, and `returnObject` represents the returned result. Post-checks do not undo side effects that already occurred inside the method.

One technical detail: the modern mechanism defers fetching `Authentication` via `Supplier<Authentication>` to avoid unnecessary work when expressions like `permitAll` can decide without reading the identity. You should not manually instantiate `SecurityExpressionRoot` to replace this mechanism.

## 3. APIs provided by SecurityExpressionRoot

### 3.1. Identity and authentication level

| Expression | Meaning and notes |
|---|---|
| `authentication` | The `Authentication` object currently used for authorization checks |
| `principal` | The `authentication.principal` object; **its concrete type depends on the authentication mechanism** |
| `authentication.name` | Identifier from `Authentication#getName()`; usually safer than assuming the principal's type |
| `isAuthenticated()` | Authenticated according to `AuthenticationTrustResolver`, not anonymous |
| `isAnonymous()` | Currently anonymous according to the trust resolver |
| `isRememberMe()` | Authenticated via remember-me (if the application uses this mechanism) |
| `isFullyAuthenticated()` | Fully authenticated, neither anonymous nor remember-me |
| `permitAll` / `permitAll()` | Always allow |
| `denyAll` / `denyAll()` | Always deny |

Example:

```java
@PreAuthorize("isAuthenticated() and authentication.name == #owner")
public String readOwnData(@P("owner") String owner) {
    return "owner=" + owner;
}
```

The snippet above illustrates an annotation on a Spring-managed service. The `authentication.name` value is taken from the security context supplied to the expression by the framework; the `#owner` parameter comes from the `EvaluationContext` for the current invocation.

**`principal` has no fixed structure.** With login using `UserDetails`, `principal.username` may exist. With a JWT resource server, the principal may be a `Jwt` with claims. With `@WithMockUser` in tests, the default principal is a test `UserDetails`, which does not automatically have `claims`. Only access properties after confirming the application's actual principal type.

### 3.2. Authorities, roles, and permissions

| Expression | Rule |
|---|---|
| `hasAuthority('invoice:read')` | Requires an **exact match** for authority `invoice:read` |
| `hasAnyAuthority('invoice:read', 'invoice:write')` | Requires at least one matching authority |
| `hasRole('ADMIN')` | Under default configuration, checks for authority `ROLE_ADMIN` |
| `hasAnyRole('ADMIN', 'SUPPORT')` | According to the configured role prefix, requires at least one role |
| `hasPermission(#invoice, 'read')` | Delegates to `PermissionEvaluator` to check object permission |
| `hasPermission(#id, 'Invoice', 'read')` | Permission check form using target ID and target type |

A common source of bugs:

```text
Authentication.authorities = ["ROLE_ADMIN", "invoice:read"]

hasRole('ADMIN')               => true   (has ROLE_ prefix by default)
hasAuthority('ROLE_ADMIN')      => true   (exact match)
hasAuthority('ADMIN')           => false  (does not auto-add ROLE_)
hasAuthority('invoice:read')    => true
hasRole('invoice:read')         => false  (looks for ROLE_invoice:read by default)
```

This is an **illustrative outcome table** under default prefix configuration and without a custom role hierarchy. The role prefix can be changed (for example via `GrantedAuthorityDefaults`) and `RoleHierarchy` can alter check results; do not hard-code assumptions if the system has customized them.

`hasPermission(...)` is an **extension point**; it does not mean Spring automatically understands owners, ACLs, tenants, or business permission tables. An appropriate `PermissionEvaluator` (and usually queries/caching) must be configured. Without it, the call does not grant object access by default.

## 4. SpEL EvaluationContext: distinguishing root object, variables, and beans

An expression in `@PreAuthorize` can combine multiple data sources:

```java
@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #amount)")
public String approve(@P("amount") long amount) {
    return "approved=" + amount;
}
```

From the expression above:

1. `hasAuthority(...)` is a **method on the root object**, so you do not need to write `#root.hasAuthority(...)`.
2. `authentication` is a **property of the root object**.
3. `#amount` is a **method parameter variable**, registered in the evaluation context; here `@P("amount")` guarantees a stable name.
4. `@invoicePolicy` is a **Spring bean reference in SpEL**, resolved by the bean resolver.
5. `and` is a SpEL logical operator using short-circuit evaluation: if the left-hand side is false, the right-hand side is generally not invoked.

Easily confused symbols:

| Symbol | Meaning |
|---|---|
| `hasRole('ADMIN')` | Invokes a security check method on the root |
| `authentication.name` | Reads a property through the root |
| `#root` | Special SpEL variable pointing to the current root object |
| `#this` | SpEL's current evaluation object; can change during collection selection/projection |
| `#owner` | Parameter variable discovered or registered in the evaluation context |
| `#p0` / `#a0` | First method parameter (index 0), useful when compiled parameter names are unavailable |
| `@invoicePolicy` | Spring bean named `invoicePolicy` |
| `returnObject` | Overall return value in a `@PostAuthorize` post-check |
| `filterObject` | Current element being evaluated in `@PreFilter` or `@PostFilter` |
| `this` (property on method root) | Reference to the target object of the method invocation; do not confuse with SpEL variable `#this` |

In typical usage, `#root` is a `MethodSecurityExpressionRoot`. An advanced policy bean can accept this object directly via `@policy.decide(#root)` with a `MethodSecurityExpressionOperations` parameter.

**The `#` prefix matters.** `#amount` points to a parameter variable; `amount` alone is looked up as a property/method on the root and may fail. Similarly, `@invoicePolicy` references a bean; `#invoicePolicy` means a variable named `invoicePolicy`, not a bean.

### 4.1. How Spring resolves parameter names

Under Method Security, the most reliable approach for an educational example is using the annotation:

```java
import org.springframework.security.access.method.P;

@PreAuthorize("#accountId == authentication.name")
public String inspect(@P("accountId") String accountId) {
    return accountId;
}
```

This is a snippet placed **inside a class/service**, not a standalone program. In real projects, Spring can also infer names via `-parameters` compiler metadata, or supported annotations such as Spring Data's `@Param`. If the source does not provide name metadata, replacing `#accountId` with `#p0` avoids relying on parameter names, though business intent is usually less clear.

### 4.2. Which variables does an expression see at each stage?

| Annotation / location | Key data available |
|---|---|
| `@PreAuthorize` | Security root, `Authentication`, method arguments; checked **before** execution |
| `@PostAuthorize` | Same as above, **plus `returnObject`** after the method returns a result |
| `@PreFilter` | `filterObject` is **each input element** of the collection being filtered |
| `@PostFilter` | `filterObject` is **each result element** filtered after the method runs |
| Web `WebExpressionAuthorizationManager` | Web root with authentication and relevant request data |

`returnObject` is not a security keyword present in every `@PreAuthorize`. Nor does `filterObject` mean "the entire list." If checking each invoice element after querying, for example:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Invoice> findAll() {
    return new ArrayList<>(invoiceRepository.findAll());
}
```

This is an integration snippet requiring `invoiceRepository`, imports, and an `Invoice` class in the application. The return value must be a collection that supports element removal during filtering; `List.of(...)` or an unmodifiable collection can fail when `@PostFilter` needs to remove elements. For pagination or large datasets, filter directly in the query instead of loading everything and post-filtering.

## 5. Runnable Java 17 example: checking root, parameters, beans, and return values

This example uses **Java 17+, Spring Boot 3.5.14 (Spring Security 6.x), Maven, and JUnit 5**. We model three policies:

- `readStatement(owner)`: only the owner or someone with `ROLE_ADMIN` may read.
- `approve(amount)`: requires authority `invoice:approve` **and** approval from the policy bean within the limit.
- `findInvoice(id)`: only the owner or an admin may receive the loaded invoice.

Place the Java files under package `com.example.expression`. No database or HTTP endpoint is needed for this Method Security lesson.

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.14</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-expression-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Application

**`src/main/java/com/example/expression/ExpressionApplication.java`**

```java
package com.example.expression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ExpressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExpressionApplication.class, args);
    }
}
```

`@EnableMethodSecurity` activates interceptors for annotations like `@PreAuthorize` and `@PostAuthorize`. Spring Boot provides auto-configuration for Security, but does not enable annotation-based method security by default unless configured.

### 5.3. Domain object and policy bean

**`src/main/java/com/example/expression/Invoice.java`**

```java
package com.example.expression;

public record Invoice(long id, String owner) {
    // JavaBean property for SpEL: returnObject.owner
    public String getOwner() {
        return owner;
    }
}
```

**`src/main/java/com/example/expression/InvoicePolicy.java`**

```java
package com.example.expression;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("invoicePolicy")
public class InvoicePolicy {
    public boolean canApprove(Authentication authentication, long amount) {
        return authentication != null
            && authentication.isAuthenticated()
            && amount >= 0
            && amount <= 1000;
    }
}
```

The `invoicePolicy` bean holds the business logic checking the limit. The 1000 limit is a **simulated rule**, not a Spring Security default. The method accepts `Authentication` so it can be extended to evaluate the user, tenant, authorities, or profile data.

### 5.4. Protected service

**`src/main/java/com/example/expression/InvoiceService.java`**

```java
package com.example.expression;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    @PreAuthorize(
        "isAuthenticated() and (hasRole('ADMIN') or #owner == authentication.name)"
    )
    public String readStatement(@P("owner") String owner) {
        return "statement:" + owner;
    }

    @PreAuthorize(
        "hasAuthority('invoice:approve') and "
        + "@invoicePolicy.canApprove(authentication, #amount)"
    )
    public String approve(@P("amount") long amount) {
        return "approved:" + amount;
    }

    @PostAuthorize(
        "returnObject.owner == authentication.name or hasRole('ADMIN')"
    )
    public Invoice findInvoice(long id) {
        return new Invoice(id, id == 7L ? "alice" : "bob");
    }
}
```

In Java, the `@PreAuthorize` annotation strings above are concatenated **at compile time** from string literals, so they are valid as a constant `String`. If preferred, the entire expression can be written on one line. Never concatenate untrusted input into **SpEL code** at runtime.

### 5.5. Testing with different identities and permissions

**`src/test/java/com/example/expression/InvoiceServiceTest.java`**

```java
package com.example.expression;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class InvoiceServiceTest {
    @Autowired
    private InvoiceService service;

    @Test
    @WithMockUser(username = "alice")
    void ownerMayReadOwnStatement() {
        assertEquals("statement:alice", service.readStatement("alice"));
    }

    @Test
    @WithMockUser(username = "bob")
    void userCannotReadOtherOwnerStatement() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readStatement("alice")
        );
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminMayReadOtherOwnerStatement() {
        assertEquals("statement:alice", service.readStatement("alice"));
    }

    @Test
    @WithMockUser(username = "auditor", authorities = "invoice:approve")
    void authorityAndBeanBothApproveWithinLimit() {
        assertEquals("approved:500", service.approve(500));
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(1500)
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeLetsOwnerReceiveResult() {
        assertEquals("alice", service.findInvoice(7L).getOwner());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeDeniesNonOwnerResult() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.findInvoice(8L)
        );
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected:** Maven/JUnit runs 6 tests and **all 6 tests pass** (`Failures: 0, Errors: 0`). Maven logs may vary by version and environment, so the passing test count is the verification criterion rather than assuming fixed stdout.

Analysis of the key scenarios:
- `alice` reads `"alice"`: `#owner == authentication.name` is true.
- `bob` reads `"alice"`: lacks `ROLE_ADMIN` and owner does not match, so denied **before** the service runs.
- `admin` reads `"alice"`: `hasRole('ADMIN')` is true thanks to `ROLE_ADMIN`.
- `auditor` has authority `invoice:approve`, yet 1500 is still denied because `@invoicePolicy.canApprove(...)` returns `false`.
- `alice` calls `findInvoice(8)`: the method created `Invoice(owner="bob")`, then `returnObject.owner` does not match, so the interceptor denies returning the result.

These checks operate on a **Spring-injected bean**. If you manually instantiate `new InvoiceService()` in a plain test or call `this.approve(...)` from another method inside the same bean (self-invocation), AOP advice may not execute.

## 6. Customizing policies: prefer beans over modifying the root directly

When an expression contains many branches or ACL queries, do not cram all business logic into a hard-to-test string. Spring Security lets you invoke beans inside SpEL:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    return repository.getReferenceById(documentId);
}
```

This is an **integration pattern**, assuming `Document`, `repository`, and the `documentAccess` bean already exist. The bean can encapsulate tenant checks, project membership, and record-level permissions. If checking parameters against the DB, consider query count, caching, race conditions, and pushing permission predicates into SQL to enforce data access boundaries.

When you need to pass the entire root into a bean, you can use `#root`:

```java
@Component("authorizationLogic")
public class AuthorizationLogic {
    public boolean canRead(MethodSecurityExpressionOperations root) {
        return root.hasAuthority("document:read");
    }
}
```

```java
@PreAuthorize("@authorizationLogic.canRead(#root)")
public Document readDocument(long id) {
    return repository.getReferenceById(id);
}
```

These two snippets are an **integration pattern** (the first class needs imports for `org.springframework.stereotype.Component` and `org.springframework.security.access.expression.method.MethodSecurityExpressionOperations`; the service needs `Document` and `repository`). When receiving `#root`, the bean can call `root.getAuthentication()` or methods available on `MethodSecurityExpressionOperations`; however, this couples the policy more tightly to Security APIs. Usually, passing `authentication` and business parameters directly makes the bean clearer.

### When you truly want a custom SecurityExpressionRoot

Some legacy systems extend `DefaultMethodSecurityExpressionHandler` and override:

```java
// Legacy customization API: signature illustration, not the recommended solution
createSecurityExpressionRoot(Authentication authentication, MethodInvocation invocation)
```

With `@EnableMethodSecurity` using `Supplier<Authentication>`, that method **is no longer the appropriate extension point**: the framework calls `createEvaluationContext(Supplier<Authentication>, MethodInvocation)`. If replacing the root is strictly required, you must understand `MethodSecurityExpressionOperations`, root delegation, bean registration, and preserving `getReturnObject()` and `getFilterObject()` behavior. A safer approach for most applications is adding a **policy bean** as shown above or defining a dedicated `AuthorizationManager`.

If you only need to adjust the role prefix or role hierarchy, use the corresponding configuration instead of creating a `SecurityExpressionRoot` subclass just for method-by-method handling.

## 7. Method Security and HTTP security use different contexts

Modern HTTP authorization declaration example (excerpt inside a `SecurityFilterChain` configuration):

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("report:read")
    .anyRequest().authenticated()
);
```

This is a **Java DSL** that builds authorization managers; there is no SpEL string per matcher. If you genuinely need to reuse web expression strings, Spring Security 6.x provides `WebExpressionAuthorizationManager`, for example as a **configuration snippet**:

```java
.requestMatchers("/reports/**")
.access(new WebExpressionAuthorizationManager("hasAuthority('report:read')"))
```

When applying this, import `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager` and place the snippet in the corresponding configuration chain. The web root has an HTTP context distinct from the method root. Do not assume a service's `#owner` variable automatically appears in web expressions, or that the web `request` variable is automatically available in every `@PreAuthorize`.

Request-level and method-level protection can be combined: HTTP rules decide who can enter the endpoint, while method rules check specific owner/tenant/ID constraints right at the service. To prevent other call paths from bypassing rules, sensitive service methods should enforce appropriate rules independent of URLs.

## 8. Common pitfalls and fixes

**1. Confusing `SecurityExpressionRoot` with `SecurityContext`.** The root provides SpEL APIs; login session identity comes from `Authentication`. Do not modify the root to "change the logged-in user."

**2. Confusing roles and authorities.** `hasRole('ADMIN')` looks for `ROLE_ADMIN` by default, whereas `hasAuthority('ADMIN')` looks for exact `ADMIN`. Verify authority mapping from JWT, LDAP, database, or `UserDetailsService` before using them.

**3. Assuming `principal.claims` exists for every user.** The `principal` type varies across mock users, session login, OAuth2, and JWT. Verify the actual principal type, or use `authentication.name` when you only need the normalized user ID.

**4. Forgetting `#` before parameter names.** `#invoiceId` is an invocation variable; `invoiceId` without `#` is looked up as a property on the root. Use `@P` or the `-parameters` compiler flag to ensure names are discovered reliably.

**5. Forgetting `@EnableMethodSecurity`.** Annotations still compile, but the corresponding interceptors will not activate automatically. A test asserting `AccessDeniedException` is practical proof that advice is active.

**6. Calling internal methods with `this` or creating services via `new`.** Spring AOP proxies do not see self-invocation calls. Invoke from another bean through the Spring-managed proxy and design clear service boundaries. For private/final methods, check class/interface proxy support and specific configuration.

**7. Thinking `@PostAuthorize` protects write operations.** It runs **after** the method; resources have already been modified before permission is checked. Check permissions before dangerous operations via `@PreAuthorize` or corresponding transaction/service policies.

**8. Assuming `hasPermission` automatically knows ACLs.** You must provide a `PermissionEvaluator` and concrete policy. Watch out for permission queries in loops causing N+1 issues.

**9. Concatenating user input into SpEL strings.** Annotation expressions should be trusted code/policy written by developers; user values should pass through `#param` variables, never interpolated directly as expression code.

**10. Using complex expressions that are hard to audit.** Move lengthy business logic into beans, write tests for allow/deny branches, and enforce fail-closed behavior when tenant/owner data is missing. Do not rely on hiding UI buttons as a substitute for server-side authorization.

**11. Failing to test alternate boundaries.** Method rules can be bypassed if another endpoint calls the repository directly; HTTP authorization does not replace per-record permissions. Cover real call flows with integration tests and protect data access appropriately.

## 9. Quick reference table

| Component | Key takeaway |
|---|---|
| `SecurityExpressionRoot` | Base root object for security checks in SpEL |
| `MethodSecurityExpressionRoot` | Root for method security, carrying invocation context and supporting post-checks/filtering |
| `EvaluationContext` | Root + `#arg` variables + `@bean` + property/method access |
| `authentication` / `principal` | Identity details, not variables arbitrarily assigned by developers |
| `hasRole` / `hasAuthority` | Roles use a default prefix; authorities match exactly |
| `#root` / `#this` | Root object / SpEL's current evaluation object |
| `returnObject` / `filterObject` | Full return value / current element in post-check or filtering contexts |
| `@EnableMethodSecurity` | Enables Spring AOP-based expression evaluation for methods |
| `@bean.method(...)` | Extends policy with testable Java code |
| `AuthorizationManager` | Component deciding allow/deny from check results |

**Official references:**
- [Spring Security 6.5 — Method Security: Expressing Authorization with SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)

Understanding the structure **`Authentication → SecurityExpressionRoot → EvaluationContext → SpEL → AuthorizationManager`** helps break a long annotation down into clear parts: checking **who**, **what permission**, **on which resource**, **at what time**, and **within which scope**.