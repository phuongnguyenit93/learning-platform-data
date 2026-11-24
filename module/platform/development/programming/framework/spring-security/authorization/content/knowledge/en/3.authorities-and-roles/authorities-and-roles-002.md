# SimpleGrantedAuthority and the Meaning of Authority Identifier Strings

In Spring Security, **`SimpleGrantedAuthority`** is a way to represent a **permission (authority) as a character string**. For example, `ROLE_ADMIN`, `reports.read`, or `SCOPE_orders.read` can all be stored using the same class:

```java
GrantedAuthority admin = new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority read = new SimpleGrantedAuthority("reports.read");
GrantedAuthority scope = new SimpleGrantedAuthority("SCOPE_orders.read");
```

Key point to grasp: **`SimpleGrantedAuthority` does not grant permissions by itself, authenticate users, or decide whether a request is allowed access**. It only holds an identifier string that authorization components will match against configured rules. Different strings may carry different business meanings, yet the Java objects are still the same `SimpleGrantedAuthority` type.

## 1. How do GrantedAuthority and SimpleGrantedAuthority differ?

### 1.1. `GrantedAuthority` is the general contract

`GrantedAuthority` is a Spring Security interface representing a permission attached to an authenticated principal. Core method:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

`getAuthority()` returns the **string representation** of the authority if the permission can be represented that way. For custom implementations with complex permissions that cannot be fully represented as a string, the method may return `null`, and the corresponding authorization component must understand that authority type. With `SimpleGrantedAuthority`, the string passed to the constructor is the exact return value.

### 1.2. `SimpleGrantedAuthority` is a simple implementation

The class's essential logic can be understood as follows (conceptual code, not a copy of the entire library source):

```java
public final class SimpleGrantedAuthority implements GrantedAuthority {
    private final String authority;

    public SimpleGrantedAuthority(String authority) {
        // Actual Spring Security checks that the string has non-whitespace characters.
        this.authority = authority;
    }

    @Override
    public String getAuthority() {
        return authority;
    }
}
```

The conceptual snippet above **is not a class to compile yourself in a project**; import the real class via `org.springframework.security.core.authority.SimpleGrantedAuthority`. The real implementation also includes `equals`, `hashCode`, `toString`, and input validation.

Properties to remember:

- The constructor accepts a **non-null, non-empty, non-whitespace-only string**; invalid values throw `IllegalArgumentException`.
- The constructor **does not automatically add `ROLE_` or `SCOPE_`**, does not change lowercase/uppercase, and does not normalize content to match policies.
- `getAuthority()` returns the exact string provided, including prefixes and case sensitivity.
- Two `SimpleGrantedAuthority` objects with the **same string** are equal according to `equals` and share the same `hashCode`; they can be used in a `Set` to deduplicate by string.
- The internal field name in the library may be "role", but **the object does not have to hold a role**; it can hold a permission or a scope.

Examples:

| Instantiation | `getAuthority()` | Application-convention meaning |
| --- | --- | --- |
| `new SimpleGrantedAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Administrative role under the default convention |
| `new SimpleGrantedAuthority("ROLE_USER")` | `ROLE_USER` | User role |
| `new SimpleGrantedAuthority("documents.read")` | `documents.read` | Permission to read documents |
| `new SimpleGrantedAuthority("orders:approve")` | `orders:approve` | Permission to approve orders |
| `new SimpleGrantedAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | OAuth2 scope mapped to an authority |
| `new SimpleGrantedAuthority("ADMIN")` | `ADMIN` | A syntactically valid authority, **not** `ROLE_ADMIN` |
| `new SimpleGrantedAuthority("role_admin")` | `role_admin` | A different string from `ROLE_ADMIN` |

The string is an **authority identifier**, not a natural-language description or a full policy object. A name like `orders:approve` only takes effect when the system standardizes the convention and has a rule checking that exact string.

## 2. How are authority identifier strings matched?

In Spring Security's core mechanisms, `Authentication` holds a collection of `GrantedAuthority`; a rule such as `hasAuthority("documents.read")` checks whether a matching authority exists in that collection.

For example, a user has the following authorities:

```text
ROLE_MANAGER
documents.read
SCOPE_orders.read
```

When using default matching rules:

| Rule | Required string | Result with the set above |
| --- | --- | --- |
| `hasAuthority("documents.read")` | `documents.read` | **Allow** |
| `hasAuthority("DOCUMENTS.READ")` | `DOCUMENTS.READ` | **Deny** |
| `hasAuthority("ROLE_MANAGER")` | `ROLE_MANAGER` | **Allow** |
| `hasAuthority("MANAGER")` | `MANAGER` | **Deny** |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | **Allow** |
| `hasAuthority("orders.read")` | `orders.read` | **Deny** |
| `hasRole("MANAGER")` | `ROLE_MANAGER` (default) | **Allow** |
| `hasRole("ADMIN")` | `ROLE_ADMIN` (default) | **Deny** |

**By default, authorities are matched as exact, case-sensitive strings.** There is no automatic rule that assumes "`MANAGER` means `ROLE_MANAGER`", "`read` means `READ`", or "`orders.read` means `SCOPE_orders.read`".

Custom configurations such as **role hierarchy**, custom authorization managers, or authority mappings can extend this behavior. When debugging failures, distinguish between direct single-string matching and the final policy decision, which may include conversion or inheritance steps.

### Why must authority names be standardized?

If the granting side assigns `DOC_READ` while the checking side calls `hasAuthority("documents.read")`, the system will deny access even though the developer thought both meant "read documents". Conversely, if a mapping step accidentally grants `ROLE_ADMIN` to someone who only had scope `admin`, the policy may allow more than intended.

Therefore, a controlled **authority identifier contract** is needed: canonical names, who can be granted them, data sources, validity conditions, matching locations, and update procedures. Do not interpret security semantics merely by looking at keywords like "admin", "read", or "write" in a string.

## 3. Distinguishing authority, role, and permission

`SimpleGrantedAuthority` is a **data container type**; role and permission are **business meanings or conventions** attached to the data.

- **Authority:** a string that Spring Security uses during authorization, such as `ROLE_ADMIN` or `invoices.approve`.
- **Role:** a permission group / user position concept, usually prefixed with `ROLE_` when using default `hasRole`. For example `ROLE_ADMIN`.
- **Permission:** the ability to perform a specific action, e.g. `invoice:read`, `invoice:approve`. This can also be represented with `SimpleGrantedAuthority`.
- **OAuth2 scope:** the scope granted by an OAuth2 Authorization Server to a client/token; with a JWT Resource Server and default converter, it is usually turned into an authority prefixed with `SCOPE_`.

**There is no separate mandatory class for "role"** when checking with `hasRole`. A default role is also stored as a `GrantedAuthority` with a `ROLE_...` string.

Example that **is only data**, not yet an authenticated user:

```java
List<GrantedAuthority> granted = List.of(
    new SimpleGrantedAuthority("ROLE_ACCOUNTANT"),
    new SimpleGrantedAuthority("invoice:read"),
    new SimpleGrantedAuthority("invoice:approve")
);
```

A user with role `ROLE_ACCOUNTANT` **does not automatically** receive `invoice:approve` just because the role name sounds related. The application must map role → permission when creating Authentication, configure an appropriate role hierarchy, or use explicitly declared rules.

### `hasRole` differs from `hasAuthority`

Suppose you already have:

```java
new SimpleGrantedAuthority("ROLE_ADMIN")
```

The following two rules usually express the same requirement **under the default prefix convention**:

```java
.hasRole("ADMIN")
.hasAuthority("ROLE_ADMIN")
```

`hasRole("ADMIN")` is a convenient shorthand using the default `ROLE_` role prefix; `hasAuthority("ROLE_ADMIN")` matches the exact string passed. **Do not prepend `ROLE_` manually when creating `SimpleGrantedAuthority` from a role string whose source already provides that prefix**, and do not by default pass `ROLE_ADMIN` to the `hasRole` API, which normally expects the unprefixed role name.

In applications that reconfigure the prefix or use `RoleHierarchy`, verify against the actual policy instead of assuming every place behaves identically. In this article, all examples use the default prefix.

## 4. Where do authority strings come from?

`SimpleGrantedAuthority` itself **does not fetch permissions** from a database, JWT, or request. Authorities are produced by configured authentication/mapping steps.

### 4.1. Users logging in with username/password

A `UserDetailsService` or `AuthenticationProvider` can retrieve roles/permissions from the database and turn them into `GrantedAuthority` instances. Using Spring Security's `UserDetails` builder:

```java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .roles("ADMIN")
    .build();
```

Under the default convention, `roles("ADMIN")` creates the `ROLE_ADMIN` authority. Conversely, `authorities("ROLE_ADMIN", "invoices.read")` takes **authority names directly**. `encodedPassword` here is a variable from separate configuration logic, not a sample password string to run standalone.

Do not mix client-supplied permissions from an HTTP body with trusted permissions inside `Authentication`. The authentication and mapping step must pull data from an authorized, trusted store.

### 4.2. OAuth2 Resource Server JWT

When the application is an OAuth2 Resource Server, `JwtAuthenticationConverter` can map `scope` or `scp` claims into granted authorities. With the common default configuration:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write"
}
```

The corresponding authorities are typically:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Thus, only an API protected with `hasAuthority("SCOPE_orders.read")` (or a dedicated scope utility) matches. `hasRole("orders.read")` by default looks for `ROLE_orders.read`, **not** `SCOPE_orders.read`.

**Remember:** the JSON above only illustrates a payload. In a real application, Spring Security must **validate the token** and verify issuer, audience, and related constraints before trusting claims. Never read `scope` directly from a self-declared HTTP header or request body and assign authorities.

`JwtGrantedAuthoritiesConverter` can be customized for prefix, claim name, or how scopes are split. When customizing, re-verify authorization rules so names do not drift.

### 4.3. External login systems or identity providers

A role in an IdP might be named `admin`, `ADMIN`, `app-admin`, or placed in a custom claim. This **is not automatically** `ROLE_ADMIN`. An explicit mapping layer can translate verified claims into canonical authority names that **only trusted sources** are permitted to grant.

Conceptual mapping example:

```text
IdP role "application-admin"
     ↓ verify token, issuer, audience, and grant eligibility
Application mapping
     ↓
SimpleGrantedAuthority("ROLE_APP_ADMIN")
     ↓
Authorization rule hasRole("APP_ADMIN")
```

Do not automatically treat every `roles`, `groups`, or `scope` claim from any issuer as equivalent internal permissions. A public scope can mean something completely different from an organization admin permission.

## 5. Runnable Java 17 example: observe the exact strings stored and matched

This example uses **Spring Security's actual `SimpleGrantedAuthority` class**, via the `spring-security-core` Maven dependency. The program creates a simulated trusted authority list, matches strings, and prints results. It **is not an authenticator**, sets up no HTTP security, and grants no permissions to a real login session.

Directory structure:

```text
authority-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AuthorityDemo.java
```

Create **`pom.xml`** inside `authority-demo`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>authority-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.AuthorityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create **`src/main/java/demo/AuthorityDemo.java`**:

```java
package demo;

import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthorityDemo {

    static boolean containsAuthority(
            List<? extends GrantedAuthority> granted,
            String required
    ) {
        return granted.stream()
                .anyMatch(authority ->
                        required.equals(authority.getAuthority()));
    }

    // Only simulates the default ROLE_ convention.
    // This is NOT Spring Security's full hasRole mechanism.
    static boolean containsDefaultRole(
            List<? extends GrantedAuthority> granted,
            String role
    ) {
        return containsAuthority(granted, "ROLE_" + role);
    }

    public static void main(String[] args) {
        List<GrantedAuthority> granted = List.of(
                new SimpleGrantedAuthority("ROLE_ADMIN"),
                new SimpleGrantedAuthority("invoices.approve"),
                new SimpleGrantedAuthority("SCOPE_invoices.read")
        );

        System.out.println("stored: " + granted.get(0).getAuthority());
        System.out.println("same text equal: "
                + new SimpleGrantedAuthority("ROLE_ADMIN").equals(granted.get(0)));
        System.out.println("authority ROLE_ADMIN: "
                + containsAuthority(granted, "ROLE_ADMIN"));
        System.out.println("authority ADMIN: "
                + containsAuthority(granted, "ADMIN"));
        System.out.println("default role ADMIN: "
                + containsDefaultRole(granted, "ADMIN"));
        System.out.println("permission invoices.approve: "
                + containsAuthority(granted, "invoices.approve"));
        System.out.println("permission INVOICES.APPROVE: "
                + containsAuthority(granted, "INVOICES.APPROVE"));
        System.out.println("scope SCOPE_invoices.read: "
                + containsAuthority(granted, "SCOPE_invoices.read"));
        System.out.println("scope invoices.read: "
                + containsAuthority(granted, "invoices.read"));
    }
}
```

Requires **JDK 17+ and a compatible Maven 3.x/4.x**. Inside the `authority-demo` directory, run:

```bash
mvn -q compile exec:java
```

Program stdout output:

```text
stored: ROLE_ADMIN
same text equal: true
authority ROLE_ADMIN: true
authority ADMIN: false
default role ADMIN: true
permission invoices.approve: true
permission INVOICES.APPROVE: false
scope SCOPE_invoices.read: true
scope invoices.read: false
```

From the output above:

1. The object stores `ROLE_ADMIN` verbatim, without turning into `ADMIN` when calling `getAuthority()`.
2. Two `SimpleGrantedAuthority("ROLE_ADMIN")` instances have equal content via `equals`, even though they are two distinct objects.
3. `ROLE_ADMIN` and `ADMIN` are not equal; only the helper simulating `hasRole("ADMIN")` under the default prefix finds `ROLE_ADMIN`.
4. `invoices.approve` differs from `INVOICES.APPROVE` because matching is case-sensitive.
5. `SCOPE_invoices.read` differs from `invoices.read`. Prefixes must be accounted for when designing rules.

**Scope of the example:** `containsAuthority` only simulates name matching in a list; real Spring Security also checks `Authentication`, anonymous/unauthenticated state, authorization managers, and may consider role hierarchies or custom policies. Do not inject a client-constructed list into an authenticated `Authentication` to protect APIs.

## 6. Using authorities in Spring Security HTTP authorization

Once a Spring Boot Servlet application has configured appropriate **authentication** (session/JWT/other authentication flow), authorities can be used in HTTP rules. Example **integration configuration class** in a Spring Boot 3.x + Spring Security 6.x application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiAccessConfig {

    @Bean
    SecurityFilterChain apiAccess(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("invoices.approve")
                .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

This is **one class inside a Spring application**, not a standalone Java program runnable with `javac`. It only describes HTTP-layer rules. A real application needs authentication configuration, dependencies, filter chain, CSRF/session setup per architecture, and appropriate URL routes.

How to read the rules:

- `/admin/**` requires `ROLE_ADMIN` because `hasRole("ADMIN")` uses the default prefix.
- `GET /api/invoices/**` requires exact `SCOPE_invoices.read`, typically coming from a verified and mapped JWT token.
- `POST /api/invoices/*/approve` requires exact `invoices.approve`, a permission explicitly granted/mapped by the application.
- `anyRequest().denyAll()` blocks requests with no declared rule. Public endpoints, actuator endpoints, or login flows must be intentionally designed in a real deployment.

**Not just any `SimpleGrantedAuthority("ROLE_ADMIN")` created somewhere in code is automatically visible to the rules above.** The object must be inside `Authentication#getAuthorities()` for the request being processed (or equivalent data used by the authorization manager).

### Control at the method layer

When `@EnableMethodSecurity` is enabled, business logic can be protected with `@PreAuthorize`:

```java
@PreAuthorize("hasAuthority('invoices.approve')")
public void approveInvoice(String invoiceId) {
    // Invoice processing logic only after basic permission check.
}
```

This is an **illustrative method** placed inside a Spring-managed bean with method security, not a standalone class. The rule only determines whether the caller has permission `invoices.approve`; if only the owner or matching tenant may approve this invoice, you must **add a check on invoiceId** through a trusted policy/repository. String authorities are generally coarse permissions, not proof of permission on individual records.

## 7. Important properties of authority strings

### 7.1. Case sensitivity, special characters, and whitespace

Suppose a mapper stores:

```text
"ROLE_ADMIN"
"role_admin"
"ROLE_ADMIN "
"ROLE_ADMIN"
```

The first three strings are **three distinct authorities**; the last duplicates the first exactly. `SimpleGrantedAuthority` does not automatically `trim()` or `toUpperCase()`. Strings consisting solely of whitespace are rejected immediately on construction.

If the system stores permissions in a database or receives them from an IdP, **normalize at the data boundary** using consistent rules and controlled mappings, rather than arbitrarily transforming names at match time. Permission name changes must be treated as security contract changes.

### 7.2. `Set` and `List` can represent the same authorities

Create two objects with the same string:

```java
var a = new SimpleGrantedAuthority("invoices.approve");
var b = new SimpleGrantedAuthority("invoices.approve");
```

`a.equals(b)` is `true`. If placed into a `HashSet<GrantedAuthority>`, these two equivalent elements collapse into one. If placed into a `List`, both may remain present. Duplicating an authority must not elevate privilege; authorization does not treat "two copies of an authority" as a stronger permission.

### 7.3. `getAuthority()` is not content you can mutate arbitrarily

`SimpleGrantedAuthority` stores its string in a `final` field; there is no setter to rename the permission on the same object. To update a user's authorities in Authentication/session, you must **rebuild the authority set per policy and update the appropriate authentication mechanism**. Changing permissions in the database does not necessarily take immediate effect on an existing login session or issued JWT.

### 7.4. No hierarchical inference from string names

Having `ROLE_ADMIN` does not automatically imply `ROLE_USER`; `invoices.*` does not automatically match `invoices.approve`. To get role hierarchy or wildcard permissions, you must define a dedicated supporting mechanism and test it. Do not mistake an identifier `"documents.read.*"` for a glob/regex expression automatically understood by Spring Security.

### 7.5. Strings do not carry full decision context

`hasAuthority("documents.read")` only asks about a general permission. Whether a user is actually permitted to read `document-123` may depend on **owner, tenant, status, and sharing** data. Use object-level authorization / method security / a policy service for this step; avoid treating a `SimpleGrantedAuthority` string as sufficient evidence for every record.

## 8. How to design an authority naming convention

There is no single mandatory naming standard for every application; what matters is **consistency** between the granting point, the conversion point, and the checking point.

A commonly used convention:

| Category | Example | Principle |
| --- | --- | --- |
| Internal role | `ROLE_ADMIN`, `ROLE_SUPPORT` | Use the `ROLE_` prefix when rules use default `hasRole` |
| Business permission | `invoice:read`, `invoice:approve` | Use `hasAuthority` and clearly declare who receives it |
| OAuth2 scope | `SCOPE_orders.read` | Only when the converter adds `SCOPE_`; verify against token contract |
| Module-scoped permission | `billing.invoice.export` | Namespaced identifiers to avoid collisions |
| Object-level rule | `canReadInvoice(user, invoiceId)` | Enforced via dynamic policy, never cramming every object ID into authority strings |

Example mapping roles to permissions at Authentication creation time:

```text
ROLE_ACCOUNTANT -> invoice:read
ROLE_APPROVER   -> invoice:read, invoice:approve
ROLE_AUDITOR    -> invoice:read, audit:read
```

This is an **illustrative business contract**, not an automatic feature of `SimpleGrantedAuthority`. Mapping can happen in the authentication service or policy layer, but it must be protected against users self-assigning roles.

With multiple issuers/tenants, define explicit namespaces or check issuer and tenant before mapping; identical permission names from two different systems **do not guarantee** identical semantics or trust levels.

## 9. Common errors and how to diagnose root causes

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| Has `ADMIN` but `hasRole("ADMIN")` denies | Authority is stored as `ADMIN` instead of `ROLE_ADMIN` | Inspect exact `Authentication#getAuthorities()`; align mapping |
| Has `ROLE_ADMIN` but `hasAuthority("ADMIN")` denies | `hasAuthority` does not add prefixes automatically | Use `hasAuthority("ROLE_ADMIN")` or `hasRole("ADMIN")` |
| JWT has `orders.read` but `hasAuthority("orders.read")` denies | Converter produces `SCOPE_orders.read` | Inspect actual mapping and use the exact string |
| DB permission is `report.read` but policy checks `REPORT.READ` | Case sensitivity | Standardize contract at the source |
| Permission with trailing space does not match | String was stored with whitespace | Inspect data/mapping; do not silently strip whitespace in policy |
| Added `new SimpleGrantedAuthority(...)` in code but request permissions didn't change | Object is not inside the active Authentication | Verify authentication pipeline, avoid creating stray objects |
| Added `ROLE_ADMIN` assuming `ROLE_USER` is included | No role hierarchy/mapping configured | Configure role hierarchy or grant appropriate authorities |
| User was downgraded but old token is still accepted | JWT/session holds stale claims/authorities | Design session invalidation, token TTL, and dynamic checks appropriately |
| Checked `documents.read` and then read someone else's document | Checked only coarse permission, omitted ownership/tenant | Add resource-level authorization |
| Read `roles` from HTTP input and granted authorities | Trusted caller-controlled data | Grant only from trusted sources after authentication |
| Logged entire Bearer token to debug permissions | Leaks token and access capability | Log filtered/anonymized authority list; never log tokens/secrets |

**Safe debugging tip:** on the server after authentication, inspect the `Authentication` type, verified principal name, and actual `getAuthority()` list according to allowed log levels. Compare each string against configured rules, paying attention to prefixes, casing, and converter mappings. Avoid logging raw tokens or sensitive data.

### Do not conflate authentication with authorization

- **Authentication** verifies the user/token and creates `Authentication`.
- **Authority mapping** attaches trusted `GrantedAuthority` instances onto `Authentication`.
- **Authorization** evaluates rules against identity, authorities, and other policy factors.

If authentication fails, the issue may lie in JWT signature/issuer/audience, password/session, or authentication provider. If authentication succeeds but returns 403, then inspect authority strings, `hasRole`/`hasAuthority` logic, and resource rules. Actual HTTP responses also depend on entry points/exception handlers and security configuration.

## 10. Testing checklist for permission names and policies

A sufficient test suite to catch normalization and mapping bugs:

1. **Role default:** user with `ROLE_ADMIN` is allowed by `hasRole("ADMIN")`; user with only `ADMIN` is not treated as role `ADMIN` by default.
2. **Exact string:** `hasAuthority("invoice:approve")` does not match `invoice:read` or `INVOICE:APPROVE`.
3. **Scope mapping:** valid token with `scope=orders.read` → expected authority per converter; rule checks `SCOPE_orders.read` if using default prefix.
4. **Empty input:** attempting `SimpleGrantedAuthority(null)`, `""`, `"   "` must be rejected; never store meaningless values.
5. **Equality:** two objects with identical strings are equal; `Set` deduplicates by identifier.
6. **Hierarchy:** inherited permissions only work when corresponding role hierarchy/mapping is configured; never assumed from names.
7. **Authentication source:** tokens/claims issued by third parties or unverified must not become internal permissions.
8. **Resource boundary:** user with `documents.read` who does not own / is not shared the document is still denied at the policy layer if business rules require it.
9. **Revocation:** modifying roles in the DB must have a strategy to update sessions/tokens and caches; test after revocation.
10. **Multiple APIs/tenants:** authority names from multiple issuers/tenants are not mixed unintentionally.

## 11. Self-check questions

**Q1:** Is `new SimpleGrantedAuthority("ADMIN")` syntactically invalid?  
**Answer:** No. It is a valid authority, but `hasRole("ADMIN")` by default requires `ROLE_ADMIN`, so it does not match `ADMIN` automatically.

**Q2:** Does `SimpleGrantedAuthority("ROLE_ADMIN")` play a different role from `SimpleGrantedAuthority("invoices.approve")` at the Java class level?  
**Answer:** No. Both are the same class; meaning is defined by the string and application rules.

**Q3:** A JWT has claim `scope=orders.read`; why does `hasAuthority("orders.read")` fail to match by default?  
**Answer:** With the default JWT scope converter, the authority is usually `SCOPE_orders.read`. Inspect the actual mapping and check the exact identifier.

**Q4:** Can two `SimpleGrantedAuthority("ROLE_USER")` objects be equal even if created at different times?  
**Answer:** Yes; `equals` and `hashCode` are based on the same string.

**Q5:** If you have `documents.read`, can you view every document?  
**Answer:** Not automatically; object-level permissions may also require owner, tenant, status, sharing, or a separate policy.

**Q6:** Does creating a `SimpleGrantedAuthority("ROLE_ADMIN")` inside a controller turn the request into an administrator?  
**Answer:** No. Permission assignment must happen through a trusted authentication/authority mapping flow and rules applied to the proper `Authentication`.

## Summary

- **`GrantedAuthority`** is the interface describing a permission; **`SimpleGrantedAuthority`** is the implementation holding **a single identifier string**.
- `SimpleGrantedAuthority` **does not add prefixes**, does not distinguish role/permission/scope by Java type, and does not perform permission checks itself.
- **`hasAuthority("X")`** checks authority `X` by exact name; **`hasRole("ADMIN")`** checks `ROLE_ADMIN` by default; **JWT scopes** typically become `SCOPE_...` by default.
- Permissions are only valid when created from a trusted source, attached to the proper `Authentication`, and checked by the right policy. General permissions do not replace per-resource permissions.
- Aligning identifiers across **permission source → mapper → Authentication → authorization rule** is essential to avoid confusing 403s or accidental privilege grants.

## References

- [SimpleGrantedAuthority – Spring Security Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/core/authority/SimpleGrantedAuthority.html)
- [GrantedAuthority – Spring Security Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/core/GrantedAuthority.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Maven Central – spring-security-core](https://central.sonatype.com/artifact/org.springframework.security/spring-security-core/6.5.11)
