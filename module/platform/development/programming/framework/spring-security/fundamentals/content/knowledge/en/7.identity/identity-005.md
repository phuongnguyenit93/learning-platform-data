# GrantedAuthority and SimpleGrantedAuthority in Spring Security

When a user logs in successfully, the application needs to know **who that person is** and **what permissions they are granted**. In Spring Security, identity information is expressed through `Authentication`, while the permissions attached to that identity are represented by **`GrantedAuthority`** objects. The most common implementation for storing a string-based permission is **`SimpleGrantedAuthority`**.

For example, a user may hold the following authorities:

```text
ROLE_USER
report:read
invoice:approve
```

These three strings do not share the same business meaning: `ROLE_USER` is usually a role, `report:read` is a permission to read reports, and `invoice:approve` is a permission to approve invoices. Yet to string-based authority checks, all of them can be placed into `Authentication.getAuthorities()` as `SimpleGrantedAuthority` instances.

**Key takeaway:** `GrantedAuthority` indicates which permissions have been **attached to the subject after a trusted authentication/mapping process**. It does not verify passwords by itself, does not determine the validity of every business policy, and does not replace checking the owner, tenant, or state of a specific record.

This lesson covers the concepts, APIs, how to create/read/check permissions, their relationship to roles and OAuth2 scopes, limitations of string-based authorities, integration in **Spring Boot 3 / Spring Security 6, Java 17+**, and a standalone Java 17 exercise to practice reasoning. Snippets using `HttpSecurity` apply to **Spring MVC / Servlet**; WebFlux uses the corresponding reactive configuration.

## 1. Distinguishing Principal, Credentials, Authorities, and Access Decisions

`Authentication` is the interface representing either an authentication request or the currently authenticated user. Three commonly mentioned properties:

| Property | Question answered | Example |
| --- | --- | --- |
| `principal` | **Who** is being represented? | User ID `u-100`, username `alice`, JWT subject |
| `credentials` | **What evidence** was used to prove identity? | Password, bearer token, or certificate, depending on mechanism |
| `authorities` | What **permissions/permission labels** were granted to the subject? | `ROLE_USER`, `ROLE_ADMIN`, `report:read`, `SCOPE_orders.read` |
| **Authorization policy** | Is that subject **allowed to perform this action on this resource**? | `hasAuthority("report:read")`, policy checking owner/tenant |

For example, Alice is authenticated with `ROLE_USER` and `report:read`. The rule `hasAuthority("report:read")` may allow Alice into the report-viewing endpoint. However, if report ID 500 belongs to another company, the application still must check data scope, ownership relationships, or other business conditions. Holding an authority **does not automatically** open every resource.

Conceptual diagram:

```text
Credentials from client
       |
       v
AuthenticationManager / AuthenticationProvider
       |  verifies password/token and identity source
       v
Authenticated Authentication
       |
       +-- principal    -> who?
       +-- credentials  -> typically erased/minimized after authentication
       +-- authorities  -> Collection<GrantedAuthority>
                                |
                                v
                    AuthorizationManager / @PreAuthorize
                                |
                                v
                    Domain policy: owner/tenant/state
                                |
                                v
                         ALLOW or DENY
```

This is a responsibility model. The actual authentication flow depends on HTTP Basic, form login, OAuth2/OIDC, JWT, and how the application persists `SecurityContext`; not every request re-authenticates with username/password.

## 2. The GrantedAuthority Interface: A Permission Granted to Authentication

### 2.1. Core Definition

In Spring Security, `GrantedAuthority` is an interface in the `org.springframework.security.core` package. Basic shape:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

In modern Javadoc, `getAuthority()` can return **`null`** if the authority is too complex to represent accurately as a single string. The condensed declaration above is for explanation and does not show version-specific nullability annotations.

Responsibilities:

- **`GrantedAuthority`** states "this is a granted permission/permission label".
- **`getAuthority()`** returns the string representation, when a string suffices for an `AuthorizationManager` to evaluate.
- **`Authentication.getAuthorities()`** returns `Collection<? extends GrantedAuthority>` for the current identity.
- **`AuthorizationManager`** or expressions such as `hasAuthority` interpret that authority in the context of protecting a request/method.

A `GrantedAuthority` **does not hold password data**, does not query the database on its own, and does not decide permissions on a specific resource by itself. It is an input to authorization policy.

### 2.2. Example Returning a String

```java
GrantedAuthority authority =
    new SimpleGrantedAuthority("report:read");

String value = authority.getAuthority();
// value equals "report:read"
```

`SimpleGrantedAuthority` is in package:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

When code reads `authentication.getAuthorities()`, each element can be represented by this string.

### 2.3. When Can getAuthority() Return Null?

A complex authority might describe "may approve invoices for customers in set X up to amount threshold Y", which is difficult to express as a single String accurately. If a custom implementation returns `null`, ordinary string-matching rules like `hasAuthority("invoice:approve")` **will not understand that object**. In that case, an `AuthorizationManager` or policy component that **knows the custom type** must evaluate its specific fields.

Illustrative example (fragment, not a standalone Java program):

```java
final class AccountScopedAuthority implements GrantedAuthority {
    private static final long serialVersionUID = 1L;

    private final Set<String> allowedAccountIds;

    AccountScopedAuthority(Set<String> allowedAccountIds) {
        this.allowedAccountIds = Set.copyOf(allowedAccountIds);
    }

    Set<String> allowedAccountIds() {
        return allowedAccountIds;
    }

    @Override
    public String getAuthority() {
        return null; // Requires an AuthorizationManager that understands this custom type.
    }
}
```

In a real application, you must import `GrantedAuthority` and `Set` and build a complete policy handling `AccountScopedAuthority`. Do not create a custom authority merely to hold a plain string; `SimpleGrantedAuthority` already handles that well.

**In practice:** use string-based authorities for roles, scopes, and application-level permissions; use domain policies or a policy engine for decisions based on object, tenant, amount, and state.

## 3. SimpleGrantedAuthority: The Simplest Implementation

### 3.1. Creating and Reading a Permission

`SimpleGrantedAuthority` is a built-in Spring Security class taking an authority string in its constructor.

```java
GrantedAuthority userRole =
    new SimpleGrantedAuthority("ROLE_USER");

GrantedAuthority reportPermission =
    new SimpleGrantedAuthority("report:read");

System.out.println(userRole.getAuthority());
System.out.println(reportPermission.getAuthority());
```

**Output of the snippet, when placed in a Java program with Spring Security dependencies:**

```text
ROLE_USER
report:read
```

The passed string is preserved as the authority. `SimpleGrantedAuthority` does not automatically turn `"ADMIN"` into `"ROLE_ADMIN"`, does not prepend `SCOPE_`, and does not decode JWTs. Consistent naming is decided by the application or converters.

### 3.2. String Authorities Are Exact-Match Values

Two objects representing the same authority:

```java
var a = new SimpleGrantedAuthority("ROLE_USER");
var b = new SimpleGrantedAuthority("ROLE_USER");
var c = new SimpleGrantedAuthority("ROLE_ADMIN");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false
```

`SimpleGrantedAuthority` uses the authority string value for `equals`/`hashCode` comparisons. This is useful when storing them in a `Set` or checking whether a permission is present. There is no built-in understanding that "USER is less than ADMIN" from string names.

Also note:

- `"ROLE_USER"` and `"role_user"` are **two different strings**.
- `"report:read"` and `"report:write"` are **two different permissions**.
- `"ADMIN"` and `"ROLE_ADMIN"` are not automatically equivalent.
- If there is a custom prefix or role hierarchy, evaluation comes from the **authorization** configuration, not from the `SimpleGrantedAuthority` constructor.
- The constructor requires a non-empty authority string. Do not create empty authorities or use `null` to represent "no permissions"; having no permissions should be represented by an appropriate empty authority collection.

### 3.3. One Permission vs. a Set of Permissions

One `SimpleGrantedAuthority` instance describes a single permission label. A user typically holds **multiple authorities**:

```java
List<GrantedAuthority> authorities = List.of(
    new SimpleGrantedAuthority("ROLE_USER"),
    new SimpleGrantedAuthority("report:read"),
    new SimpleGrantedAuthority("invoice:approve")
);
```

If deduplication is needed, you can use a `Set`, though when working with `Authentication.getAuthorities()` you should not assume the returned collection is a `Set`, mutable, or ordered in a particular way. To produce a stable display list:

```java
List<String> names = authentication.getAuthorities()
    .stream()
    .map(GrantedAuthority::getAuthority)
    .filter(java.util.Objects::nonNull)
    .sorted()
    .toList();
```

This handles cases where a custom `GrantedAuthority` returns `null`. Do not expose every user's authority list on a public API indiscriminately; return only data appropriate to the purpose and security policy.

### 3.4. SimpleGrantedAuthority Is Not a User

Do not confuse:

```text
UserDetails / principal
    -> describes a user or subject

Authentication
    -> represents the subject's authentication state
    -> holds the authorities collection

SimpleGrantedAuthority
    -> represents only ONE granted permission string
```

Creating:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
```

does not turn the caller into an admin. Only when a trusted identity source grants that authority and a provider/converter constructs the corresponding `Authentication` can policies use it. Never allow a client to send a `ROLE_ADMIN` string and attach it directly to `SecurityContext`.

## 4. Role, Authority, and Scope: Recognizing Prefixes

### 4.1. hasRole and hasAuthority Are Two Different Checks

| Check in Spring Security | Required authority value (default) | Outcome |
| --- | --- | --- |
| `hasRole("USER")` | `ROLE_USER` | Allowed if holding role USER |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Allowed if holding role ADMIN |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Exact match of the same string |
| `hasAuthority("ADMIN")` | `ADMIN` | Different from `ROLE_ADMIN` |
| `hasAuthority("report:read")` | `report:read` | Checks specific permission |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | Checks authority typically mapped from an OAuth2 scope |
| `hasAnyAuthority("report:read","report:write")` | Either string | Combines independent permissions |

In Spring Security's default setup, `hasRole("ADMIN")` is a convenient shorthand for requiring `ROLE_ADMIN`. The default prefix can be customized; do not write logic assuming it was changed without checking actual configuration.

For example, Alice has:

```text
ROLE_USER
report:read
```

When evaluated against:

```java
.requestMatchers("/api/reports").hasAuthority("report:read")
.requestMatchers("/api/admin").hasRole("ADMIN")
```

Alice passes the report-reading rule, yet lacks the admin role. **Valid authentication and the USER role do not make ROLE_ADMIN appear automatically.**

### 4.2. User.withUsername(...).roles(...) vs. authorities(...)

With Spring Security's built-in builder:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .roles("USER")
    .build();
```

`roles("USER")` adds the prefixed authority `ROLE_USER` to the created user. To include non-role permissions as well, use:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .authorities("ROLE_USER", "report:read")
    .build();
```

**Do not chain `.roles("USER").authorities("report:read")` assuming both accumulate:** these builder methods set the permission list; depending on the API, the later call can overwrite the earlier list. Specify all desired authorities in a single call or explicitly verify `getAuthorities()` in a test.

`.roles("ROLE_USER")` violates the builder convention because `roles` expects role names **without** the prefix. Use `.roles("USER")` or `.authorities("ROLE_USER")` to make intent clear.

### 4.3. Role Hierarchy Does Not Exist Automatically from Names

An application may want `ADMIN > USER`, meaning admins have every permission granted to USER. Yet creating only:

```java
new SimpleGrantedAuthority("ROLE_ADMIN")
```

does **not automatically include ROLE_USER**. If a `hasRole("USER")` policy must accept admins, you can either:

1. Assign both `ROLE_ADMIN` and `ROLE_USER` to admins; or
2. Configure a compatible `RoleHierarchy` and ensure the authorization components use that hierarchy.

Do not assume `ROLE_SUPER_ADMIN`, `ROLE_ADMIN`, and `ROLE_USER` form a hierarchy from their names alone. Test both cases—with and without inherited permissions—on the exact version and configuration.

### 4.4. Scopes from JWT and the SCOPE_ Prefix

In an OAuth2 Resource Server, the default converter typically maps an `orders.read` scope from the `scope` or `scp` claim of a **verified** token to `SCOPE_orders.read`.

```text
Verified token claim: scope = "orders.read orders.write"
                 |
                 v
JwtGrantedAuthoritiesConverter
                 |
                 v
SimpleGrantedAuthority("SCOPE_orders.read")
SimpleGrantedAuthority("SCOPE_orders.write")
```

However:

- Converters and prefixes can be configured differently; inspect the actual configuration.
- Token signature, issuer, audience, expiration, and other trust checks **must be verified before** using claims as permissions.
- `SCOPE_orders.read` only expresses a coarse-grained read scope; it does not automatically permit reading another tenant's orders.
- Never treat a raw JSON `roles` claim sent by a client in a request body as an authority.

## 5. How Does GrantedAuthority Enter Authentication?

### 5.1. Username/Password

Suppose an application uses `UserDetailsService` and `DaoAuthenticationProvider`:

```text
Client sends username/password
         |
         v
AuthenticationProvider checks credentials
         |
         +-- UserDetailsService.loadUserByUsername(username)
         |       |
         |       +-- UserDetails.getAuthorities()
         |                ROLE_USER, report:read
         |
         +-- PasswordEncoder.matches(raw, storedHash)
         |
         v
Successful Authentication
         |
         +-- principal = verified user
         +-- credentials = may be erased after authentication
         +-- authorities = permissions from trusted source
         |
         v
SecurityContext -> AuthorizationManager
```

`UserDetailsService` supplies user details; `PasswordEncoder` matches passwords appropriately; the provider decides whether authentication succeeds or fails. Authorities from the user store are what authorization consumes.

### 5.2. JWT

With a JWT resource server, `JwtDecoder` verifies the token per configuration and `JwtAuthenticationConverter` maps principal/authorities. The usual default is `JwtAuthenticationToken` with scope authorities. If mapping custom roles from an IdP, perform conversion only after the token passes trust-policy verification; avoid treating any claim named `role` as truth automatically.

### 5.3. Form Login and Session

After form login, the authenticated `Authentication` may be stored in `SecurityContext` attached to the session under the active policy. The authorities in the session represent the state **captured when the context was created** or restored. If a user's permissions change in the database, active sessions/tokens **do not necessarily update immediately**. Applications need refresh, revocation, or runtime permission-checking policies tailored to risk.

### 5.4. Anonymous Does Not Mean Logged-In User

`AnonymousAuthenticationToken` may appear in the context of a public request. It can carry `ROLE_ANONYMOUS` and have `isAuthenticated() == true` at the token level. However, Spring Security's `authenticated()` policy has semantics that exclude anonymous callers.

Therefore, do not use `authentication != null` or manual `isAuthenticated()` checks as a shortcut replacing `authenticated()`, `hasAuthority`, or other policy rules.

## 6. From a List of GrantedAuthority to Authorization Decisions

A common HTTP rule:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public").permitAll()
    .requestMatchers("/api/reports").hasAuthority("report:read")
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

`authorizeHttpRequests` belongs to modern Spring Security Servlet configuration. It binds rules to requests; depending on the rule, `AuthorizationManager` uses the current `Authentication` and its authorities to decide access.

At the service layer, method security can use:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long id) {
    return reportPolicy.readAuthorizedReport(id);
}
```

This is a fragment. The application must enable `@EnableMethodSecurity` and invoke the method across an appropriate proxy boundary. `reportPolicy` must be implemented to verify the principal's access to the specific report ID; `hasAuthority` alone only checks the granted authority.

### 6.1. Role of Authorities in Policy

| Question | Can SimpleGrantedAuthority suffice? | Other layer needed |
| --- | --- | --- |
| Has `report:read` permission been granted? | Yes | Read from `Authentication.getAuthorities()` |
| Has role `ROLE_ADMIN`? | Yes | Proper role matcher/prefix |
| Does verified token have `orders.read` scope? | Yes, after converter mapping | Token verification, issuer/audience/expiration |
| Allowed to view someone else's Order ID 123? | Insufficient | Object/tenant/owner authorization |
| Allowed to approve an invoice in `PENDING` state? | Insufficient | Business-state policy, transaction |
| Allowed to exceed usage quota? | Insufficient | Rate/quota policy |
| Allowed to access an account ID on a dynamic whitelist? | Coarse string usually insufficient | Domain lookup or custom policy |

Do not design an authority for **every** object ID in a system with millions of objects unless there is a very specific reason. Oversized authority collections inflate authentication overhead, token/session sizes, and revocation complexity. Domain-object authorization fits per-record permissions much better.

### 6.2. Distinguishing Authority Denial from Authentication Errors

- **401 Unauthorized** (commonly with HTTP Basic): missing or invalid credentials on an endpoint requiring login.
- **403 Forbidden**: authenticated, yet lacking the required authority/role or rejected by another mechanism such as CSRF.
- **200 OK**: request permitted and the controller returns success in the example.
- **404 Not Found**: endpoint or object does not exist; applications may intentionally hide resource existence per policy.

An HTTP 403 **alone does not prove** `SimpleGrantedAuthority` was missing; CSRF, object-level rules, or other filters can also reject the request. When testing authority rules on POST, send a valid CSRF token per configuration so another layer does not block the request first.

## 7. Complete Spring Boot 3 Example: Granting and Checking Authorities

The following example uses **Spring MVC/Servlet, Spring Security 6, Java 17+**. The goal is to clearly see the difference between authority lists and `hasRole`, `hasAuthority`, and `@PreAuthorize` rules.

There are three demo accounts:

| Username | Local password | Authorities |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER`, `report:read` |
| `approver` | `approver-pass` | `ROLE_USER`, `invoice:approve` |
| `admin` | `admin-pass` | `ROLE_USER`, `ROLE_ADMIN`, `report:read`, `invoice:approve` |

Policies:

- `GET /api/public`: accessible to anyone.
- `GET /api/whoami`: authenticated users; returns name and sorted authority list.
- `GET /api/user-zone`: requires role USER.
- `GET /api/admin`: requires role ADMIN.
- `GET /api/reports`: requires authentication at HTTP and `report:read` at service.
- `POST /api/invoice-approvals`: requires `invoice:approve` and a valid CSRF token in the demo setup.

### 7.1. Gradle Dependencies

In a Spring Boot 3 project that already has the appropriate plugins, repositories, and dependency management, the `dependencies` block of `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is not a complete Gradle file; the project needs the Spring Boot plugin and Java toolchain. With Maven, use the corresponding starters and `spring-security-test` in `test` scope. Let the Spring Boot BOM manage Spring Security versions to avoid mixing incompatible module versions.

### 7.2. Main Class

Create `src/main/java/example/authorities/AuthorityDemoApplication.java`:

```java
package example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}
```

### 7.3. SecurityConfig: Granting Permissions from a Trusted Source

Create `src/main/java/example/authorities/SecurityConfig.java`:

```java
package example.authorities;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails approver = User.withUsername("approver")
            .password(encoder.encode("approver-pass"))
            .authorities("ROLE_USER", "invoice:approve")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities(
                "ROLE_USER", "ROLE_ADMIN",
                "report:read", "invoice:approve"
            )
            .build();

        return new InMemoryUserDetailsManager(reader, approver, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/user-zone")
                    .hasRole("USER")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/invoice-approvals")
                    .hasAuthority("invoice:approve")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Here:

1. `UserDetailsService` grants permissions from server-controlled data; demo passwords are hashed with BCrypt. In production, a real identity source and proper credential management are required.
2. `.authorities("ROLE_USER", "report:read")` assigns **two authority strings** to reader, corresponding to `SimpleGrantedAuthority` instances.
3. `.hasRole("USER")` looks for `ROLE_USER`, while `.hasRole("ADMIN")` looks for `ROLE_ADMIN` per the default prefix.
4. `.hasAuthority("invoice:approve")` looks for the **exact string**; the USER role is not sufficient for invoice approval.
5. `.authenticated()` only requires a trusted identity, which is not enough to read reports if the service also enforces `@PreAuthorize`.
6. `.csrf(Customizer.withDefaults())` keeps CSRF protection enabled; POST requests need a matching token. GET requests in the demo do not need a CSRF token.
7. `anyRequest().denyAll()` prevents undeclared routes from accidentally becoming public.

Do not confuse the builder's `.authorities(...)` method with an endpoint letting clients grant themselves permissions: this is a **developer-controlled configuration bean**, not JSON submitted by a client.

### 7.4. Controller and Service

Create `src/main/java/example/authorities/AuthorityController.java`:

```java
package example.authorities;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class AuthorityController {

    private final ReportService reportService;

    AuthorityController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/user-zone")
    Map<String, String> userZone() {
        return Map.of("message", "user-zone");
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }

    @GetMapping("/reports")
    Map<String, String> reports() {
        return Map.of("message", reportService.readReport());
    }

    @PostMapping("/invoice-approvals")
    Map<String, String> approveInvoice() {
        // Demo does not persist real data.
        return Map.of("message", "approved");
    }
}

@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "report";
    }
}
```

When `GET /api/reports` is called, the HTTP layer only requires the user to be logged in. The controller then invokes **a separate Spring bean**, `ReportService`. Method security from `@EnableMethodSecurity` checks `report:read` before running `readReport()`. If approver lacks this authority, Spring Security denies access.

Because `ReportService` is a separate bean invoked via dependency injection, the call crosses the boundary where Spring AOP/method security applies. Calling an `@PreAuthorize` method internally via `this.method()` inside the same bean can bypass the proxy, so do not assume annotations always block self-invocation.

**Example limitations:** the `Map` response returns the username and authority strings only for the demo; production must weigh what information may be exposed to clients. `approveInvoice()` only returns a string without updating an invoice; owner, tenant, invoice-state, and transaction checks are absent. When implementing real business logic, those constraints must be added.

### 7.5. Running Manually

In the Spring Boot project root with the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

With the demo app running on `http://localhost:8080`:

```bash
# Public GET: 200
curl -i http://localhost:8080/api/public

# Missing authentication: HTTP Basic usually returns 401
curl -i http://localhost:8080/api/whoami

# Reader: has ROLE_USER, report:read
curl -i -u reader:reader-pass http://localhost:8080/api/whoami

# Reader has report:read: 200
curl -i -u reader:reader-pass http://localhost:8080/api/reports

# Approver lacks report:read: 403 from method security
curl -i -u approver:approver-pass http://localhost:8080/api/reports

# Reader lacks ROLE_ADMIN: 403
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Admin has ROLE_ADMIN: 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Reader lacks invoice:approve: POST without CSRF may already be blocked by CSRF
curl -i -X POST -u reader:reader-pass \
  http://localhost:8080/api/invoice-approvals
```

The final POST line **does not test missing authority in isolation**, because CSRF is enabled by default. To test POST authority rules, use MockMvc `with(csrf())` in the next section or implement a real CSRF token flow. Avoid disabling CSRF globally merely to make `curl` easier to call.

HTTP Basic only Base64-encodes username/password, so real environments require HTTPS. `curl -u` with the passwords above uses local demo values; never put real secrets in shell history, process lists, or logs.

### 7.6. JSON Output of whoami

When reader logs in validly, an illustrative response:

```json
{
  "username": "reader",
  "authorities": ["ROLE_USER", "report:read"]
}
```

The list is sorted for deterministic results, though the order of **JSON fields** is decided by the serializer. The response contains no password or password hash. A `SimpleGrantedAuthority` carries only a permission string, not a user identifier.

## 8. Testing with Spring Security Test and MockMvc

To prove how `GrantedAuthority` affects authorization, write tests for having permission, lacking permission, no user, and invalid CSRF. The example project already includes `spring-security-test` on the test classpath.

Create `src/test/java/example/authorities/AuthoritySecurityTest.java`:

```java
package example.authorities;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritySecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsNotAuthentication() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerHasExpectedAuthorities() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void reportRequiresMethodAuthority() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRequiresRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void invoiceApprovalRequiresAuthority() throws Exception {
        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("approver", "approver-pass"))
                .with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    void csrfStillProtectsAuthorizedUser() throws Exception {
        mvc.perform(post("/api/invoice-approvals")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void userZoneChecksRoleUser() throws Exception {
        mvc.perform(get("/api/user-zone")
                .with(httpBasic("approver", "approver-pass")))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test --tests example.authorities.AuthoritySecurityTest
```

On Windows:

```powershell
.\gradlew.bat test --tests example.authorities.AuthoritySecurityTest
```

**Expected per sample configuration:** all **9 test methods** succeed. This is the expected outcome from the source code, **not a certification that the tests were executed inside this document**. If your project environment differs, verify Boot/Security dependencies, controllers, method-security proxies, and test setup before concluding.

What the tests prove:

| Test | What is checked | Conclusion |
| --- | --- | --- |
| Anonymous public/private | Authentication and HTTP rules | Public permitted; private requires identity |
| Wrong password | AuthenticationProvider | Does not issue a trusted user from bad credentials |
| Reader whoami | `Authentication.getAuthorities()` | Authority strings match the user store |
| Report reader/approver | `@PreAuthorize` at service | Having/lacking `report:read` yields different outcomes |
| Admin reader/admin | `hasRole("ADMIN")` | Only `ROLE_ADMIN` satisfies the role |
| POST reader/approver with CSRF | `hasAuthority("invoice:approve")` | Permission checked once request passes CSRF |
| POST approver missing CSRF | Exploit protection | Even sufficient authority can be blocked by CSRF |
| User zone | Role prefix | `ROLE_USER` matches `hasRole("USER")` |

### 8.1. Using @WithMockUser and user() When Isolating Authority Checks

In a test checking only authorization, you can simulate:

```java
@WithMockUser(authorities = {"ROLE_USER", "report:read"})
@Test
void reportIsVisibleToReader() {
    // MockMvc request to a protected controller
}
```

or:

```java
mvc.perform(get("/api/reports")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("ROLE_USER"),
            new SimpleGrantedAuthority("report:read")
        )));
```

The examples above **are test fragments only** requiring appropriate context/imports. `@WithMockUser` and `user()` build a simulated `Authentication` in tests, **without checking real passwords**. When you want to prove the user store and `PasswordEncoder` work, tests using `httpBasic(...)` as in section 8 go through the application's authentication provider.

### 8.2. Verifying the Exact Cause of 403

A POST test without a CSRF token may receive 403 **before** authorities are checked. Therefore, the "reader lacks `invoice:approve`" test above uses `with(csrf())` to ensure the request is not blocked by CSRF. Another test intentionally omits CSRF to prove that protection remains active.

In real systems, beyond status codes, verify that no record was modified and no message or payment was dispatched when permission is denied. HTTP 403 alone does not prove absence of side effects if business logic executed prior to the exception.

## 9. Standalone Java 17: Authorities Are Strings and Decisions Need Clear Conditions

The following example **runs on plain JDK 17** with no Spring dependencies. It models string-based authorities with Java `record`s so learners can reason clearly before diving into Spring Security. It is **not** a production security implementation; the `authenticated` flag and grant set are simulated data only.

Create **`AuthorityDecisionDemo.java`**:

```java
import java.util.Set;

public class AuthorityDecisionDemo {

    record Grant(String name) {}

    record User(
        String name,
        boolean authenticated,
        Set<Grant> grants
    ) {}

    static boolean hasAuthority(User user, String required) {
        return user != null
            && user.authenticated()
            && user.grants() != null
            && user.grants().contains(new Grant(required));
    }

    static boolean hasRole(User user, String role) {
        return hasAuthority(user, "ROLE_" + role);
    }

    static boolean canReadOrder(User user, String ownerId) {
        return hasAuthority(user, "order:read")
            && user.name().equals(ownerId);
    }

    public static void main(String[] args) {
        User reader = new User(
            "alice", true,
            Set.of(new Grant("ROLE_USER"),
                   new Grant("report:read"),
                   new Grant("order:read"))
        );

        User admin = new User(
            "admin", true,
            Set.of(new Grant("ROLE_ADMIN"))
        );

        User guest = new User("guest", false, Set.of());

        System.out.println("Equal grants: "
            + new Grant("ROLE_USER").equals(new Grant("ROLE_USER")));
        System.out.println("Reader has USER role: "
            + hasRole(reader, "USER"));
        System.out.println("Reader has ADMIN role: "
            + hasRole(reader, "ADMIN"));
        System.out.println("Reader report read: "
            + hasAuthority(reader, "report:read"));
        System.out.println("Reader report READ: "
            + hasAuthority(reader, "report:READ"));
        System.out.println("Admin has USER role: "
            + hasRole(admin, "USER"));
        System.out.println("Guest has USER role: "
            + hasRole(guest, "USER"));
        System.out.println("Alice own order: "
            + canReadOrder(reader, "alice"));
        System.out.println("Alice Bob order: "
            + canReadOrder(reader, "bob"));
    }
}
```

Run:

```bash
javac AuthorityDecisionDemo.java
java AuthorityDecisionDemo
```

**Exact stdout:**

```text
Equal grants: true
Reader has USER role: true
Reader has ADMIN role: false
Reader report read: true
Reader report READ: false
Admin has USER role: false
Guest has USER role: false
Alice own order: true
Alice Bob order: false
```

Explanation:

1. Two `Grant` Java records with the same string value are considered equal by `equals`, mirroring value-based matching in `SimpleGrantedAuthority`.
2. `hasRole(reader, "USER")` prepends `ROLE_`, checking the exact string `ROLE_USER`.
3. Reader lacks `ROLE_ADMIN`, so the admin check fails.
4. `report:read` and `report:READ` differ in case and are not automatically equivalent.
5. Admin has only `ROLE_ADMIN` and does not automatically hold `ROLE_USER`. Inheritance requires assigning it explicitly or configuring a hierarchy.
6. Guest is unauthenticated and is blocked even if they somehow held a permission string.
7. Alice has `order:read`, yet only passes the policy for reading **Alice's** order; Bob's order is still denied.

**Very important limitation:** the program constructs `User(authenticated=true, grants=...)` directly without verifying credentials or the source of authorities. Never trust such records when building real APIs. In Spring Security, `AuthenticationProvider`, `SecurityContext`, and the official authorization mechanisms must be responsible for constructing and consuming verified identities and permissions.

## 10. Granting GrantedAuthority from Database, Token, or External Systems

### 10.1. Using a Database as the Permission Source

Suppose the database stores:

```text
users
  id, username, password_hash, status

roles
  id, code                  # USER, ADMIN, ...

user_roles
  user_id, role_id

permissions
  id, code                  # report:read, invoice:approve

role_permissions
  role_id, permission_id
```

When loading a user, the backend can convert roles into `ROLE_ + code` strings and permissions into strings like `report:read`, then build the appropriate `SimpleGrantedAuthority` instances. The data source must be the application's database/trust boundary, not a `roles` array sent by the client.

Illustrative fragment (requires real `RoleRepository`, entities, and services):

```java
List<GrantedAuthority> authorities = roleCodes.stream()
    .map(code -> new SimpleGrantedAuthority("ROLE_" + code))
    .map(a -> (GrantedAuthority) a)
    .toList();
```

If permissions are also needed, construct a permission set with clear conventions and deduplicate by value. **Validate permission codes** when loading from the DB: do not let regular users edit their own roles/permissions, do not mix tenants, and do not ignore account status.

### 10.2. Using JWT

Tokens can carry scopes or roles; after verifying signature, issuer, audience, expiration, and trust settings, a converter can produce authorities. Example:

```text
Verified JWT:
sub = "user-100"
scope = "report.read invoice.read"

Authorities after converter mapping:
SCOPE_report.read
SCOPE_invoice.read
```

If application policy specifies `hasAuthority("report:read")` while the converter produces `SCOPE_report.read`, the rule will not match. Do not resolve this by "permitting all requests"; align the permission **vocabulary**, configure the converter if needed, and test with real payloads.

### 10.3. When Permissions Change While a Session/Token Is Still Alive

Authorities are usually attached to `Authentication` at authentication time or upon context restoration/token conversion. If an admin revokes a user's permissions, existing tokens or sessions do not necessarily update immediately. Depending on business needs, apply:

- Appropriate token TTLs, with refresh/revocation when needed;
- Session invalidation or an authority reload mechanism;
- Runtime permission checks for sensitive actions;
- Auditing of granted/revoked permissions;
- Tests verifying new permissions actually take effect on time.

Granting permissions is part of identity governance. Do not confuse "updated a permission in the database" with "every active `Authentication` has changed".

### 10.4. When Multiple Tenants Share the Same Role Names

Two people can both hold `ROLE_MANAGER` while belonging to different tenants A and B. A global string authority **does not carry tenant boundaries by default**. Use verified tenant claims/context and explicit tenant-checking policies, or an intentional custom model. Never rely on a `tenantId` submitted by the frontend in a request body as proof of permission.

A policy might look like:

```text
ALLOW viewInvoice if:
  principal is authenticated
  AND has invoice:read
  AND principal and invoice are in a valid tenant
  AND principal is owner or granted view permission within that tenant
  AND invoice state permits it
```

These conditions must be checked in the service/repository or an appropriate policy engine, not by `SimpleGrantedAuthority` alone.

## 11. Common Mistakes When Working with SimpleGrantedAuthority

### 11.1. Assigning ADMIN While Checking ROLE_ADMIN

```java
new SimpleGrantedAuthority("ADMIN"); // Only the "ADMIN" authority
```

If the rule is `hasRole("ADMIN")` with the default prefix, the required string is `ROLE_ADMIN`. Thus the rule does not match. There are two clear choices:

- Grant `new SimpleGrantedAuthority("ROLE_ADMIN")` and use `hasRole("ADMIN")`.
- Grant `new SimpleGrantedAuthority("ADMIN")` and use `hasAuthority("ADMIN")`.

Do not mix conventions without an explicit mapping policy.

### 11.2. Using hasRole("ROLE_ADMIN") Against Convention

`hasRole` normally expects a **role name without the prefix**. In many matchers, passing `ROLE_ADMIN` into `hasRole` causes an error or unexpected behavior because the prefix is applied. Use `hasRole("ADMIN")`, or `hasAuthority("ROLE_ADMIN")` when matching the exact string.

### 11.3. Expecting One Authority to Imply Another

`ROLE_ADMIN` does not automatically include `ROLE_USER`, `invoice:approve`, or `report:read`. If inheritance is desired, configure `RoleHierarchy` properly or explicitly grant the related permissions. Test both inherited permissions and permissions that must not be inherited.

### 11.4. Confusing Authorities with Callable API Lists

`getAuthorities()` is the set of **granted** permissions. It does not automatically map "authority A = endpoint X" unless `authorizeHttpRequests`, `@PreAuthorize`, or another policy defines that rule. A user with `report:read` can still hit an unprotected endpoint if authorization is missing; conversely, an endpoint requiring another permission will remain denied.

### 11.5. Self-Asserting Permissions via Request Body/Header

Anti-pattern:

```java
// Do not do this: request.roles() is client-controlled.
var granted = request.roles().stream()
    .map(SimpleGrantedAuthority::new)
    .toList();
```

Never grant authorities from a client-claimed list. Use a user store, provider, or verified token and check the claim source against trust policy.

### 11.6. Checking Only isAuthenticated()

A successfully logged-in user is not permitted to do everything. For sensitive endpoints, require the right authority plus object/domain policies. `isAuthenticated()` also has a caveat with anonymous tokens; use Spring Security's `authenticated()` policy rather than manual inference.

### 11.7. Using Global Permissions for Every Object

`order:read` may be a feature-level permission, yet it does not prove permission to read `orderId=123`. Add owner, tenant, delegation rules, and query scoping. This is the classic **IDOR/BOLA** vulnerability when authorization only checks roles.

### 11.8. Forgetting CSRF When Testing POST

If `POST /api/invoice-approvals` returns 403, do not immediately conclude `invoice:approve` is missing. A missing CSRF token can block it first. Use `with(csrf())` when isolating authority tests in MockMvc, and keep a separate test confirming CSRF remains active.

### 11.9. Keeping Old Authorities After Role Revocation

While a session or token remains valid, old authorities can persist. Design refresh/revocation for sensitive permissions, limit lifetimes, and check runtime policies when needed. Do not assume updating a permission row in the DB immediately affects every token.

### 11.10. Exposing Too Much Permission Detail

Sometimes a frontend needs to know whether a user has certain capabilities to show buttons. Yet an API returning all internal permissions can leak unnecessary operational detail. Never send passwords, tokens, hashes, or raw `Authentication` objects. Return a minimal DTO for the use case.

### 11.11. Treating String Authorities as Immutable Cross-Environment Permissions

An `ADMIN` string can mean different things between system A and system B. Define the vocabulary, permission ownership, grant/revocation workflows, IdP mappings, and testing policies. With OAuth2, token scopes do not necessarily match internal roles.

### 11.12. "Fixing" 403 with permitAll

If a user lacks an authority, changing `hasAuthority(...)` to `permitAll()` can expose the feature to everyone. Diagnose properly: what are the actual authorities, is the prefix right, did the JWT converter map scopes accurately, is method security enabled, and is CSRF or an object policy blocking the call?

## 12. Debugging a hasRole/hasAuthority Failure

When a request gets 403 or an unexpected permission is granted:

1. **Identify the endpoint and HTTP method**: did the request hit the right `SecurityFilterChain`? Are chain order or matchers misconfigured?
2. **Did authentication succeed?** With HTTP Basic, valid/wrong password; with JWT, was the token verified? Is anonymous handled properly?
3. **Inspect the authority list safely**: what exact strings are in `authentication.getAuthorities()`? Should permission names be redacted/omitted in logs per security policy?
4. **Check prefix/case**: `ROLE_USER` or `USER`? `SCOPE_read` or `read`? `report:read` or `report:READ`?
5. **Check the rule**: `hasRole("ADMIN")`, `hasAuthority("ROLE_ADMIN")`, or `hasAuthority("ADMIN")`?
6. **Check the source**: which user store, database, provider, JWT converter, IdP, or custom mapper granted the authority?
7. **Check method security**: is `@EnableMethodSecurity` enabled, and was the method invoked through a proxy?
8. **Check the object**: which tenant/owner does the user belong to; is the object in an allowed state?
9. **Check other protection layers**: CSRF, request matchers, CORS/browser constraints, session expiry, exception handlers.
10. **Check fresh vs. stale permission state**: is a session or token holding authorities from before a permission update?
11. **Write negative tests**: user with the same role lacking the permission, user in another tenant, anonymous user, request missing CSRF.
12. **Verify no side effects** occurred when access was denied: database, message queue, and external services remain untouched.

You do not need to log passwords or bearer tokens to know what permissions a user holds. If enabling debug logging, restrict environment/duration and scrub sensitive content.

## 13. Checklist for Designing a GrantedAuthority-Based Permission System

**Defining and granting permissions**

- Authority names follow clear conventions: `ROLE_*` for roles, permissions like `resource:action`, or scopes per IdP standards.
- A trusted source grants/revokes roles and permissions; clients cannot self-assert permissions.
- Authentication providers or token converters map authorities consistently.
- User, role, permission, and tenant data are validated at trust boundaries.
- Passwords/tokens are verified, avoiding logging or serializing secrets.
- Role hierarchies, if any, are declared and tested rather than inferred from names.

**Using and enforcing**

- HTTP rules and method rules rely on the permissions actually needed for the action.
- Default-deny or explicit policies protect sensitive endpoints.
- Clear distinction between `hasRole` and `hasAuthority`, prefixes, and case sensitivity.
- Never substitute a coarse authority for owner/tenant/business-state checks.
- A rejected request produces no business side effects.
- For session/cookie APIs, CSRF protection matches the threat model.
- When permissions change, sessions/tokens are refreshed/revoked per validity requirements.

**Testing and operations**

- 401 tests for missing/invalid credentials.
- 403 tests for authenticated users lacking the required authority.
- 200 tests for users holding the appropriate authority.
- Method security tests invoking through real beans.
- Dedicated CSRF tests so 403 causes are never conflated.
- Tests for object permissions, tenants, states, and recently revoked permissions.
- Sufficient audit/metrics for investigation without leaking authentication secrets.

## 14. Self-Check Questions

**Question 1.** How do `GrantedAuthority` and `SimpleGrantedAuthority` differ?

**Question 2.** What does `Authentication.getAuthorities()` return? Does an authority hold the user's password?

**Question 3.** If a user has `SimpleGrantedAuthority("ROLE_USER")`, can `hasRole("USER")` match? What about `hasAuthority("USER")`?

**Question 4.** A user has `ROLE_ADMIN`. Do they automatically carry `ROLE_USER`? What is needed for inheritance?

**Question 5.** Why is `hasAuthority("report:READ")` different from `hasAuthority("report:read")`?

**Question 6.** If a valid JWT has scope `orders.read`, why might `hasAuthority("orders.read")` fail to match?

**Question 7.** Why should you avoid turning every order ID of a user into thousands of `SimpleGrantedAuthority` entries?

**Question 8.** Why must a user with `order:read` still undergo owner/tenant checks?

**Question 9.** When testing a POST requiring invoice-approval permission, why must a valid CSRF token be provided if CSRF is enabled?

**Question 10.** Why must you never call `new SimpleGrantedAuthority(request.role())` directly from client data?

**Question 11.** When a permission is revoked in the DB, do all active `Authentication` instances update automatically?

**Question 12.** When a custom `GrantedAuthority.getAuthority()` returns null, what is needed for policies to use that object?

**Answer hints**

1. `GrantedAuthority` is an interface describing a permission; `SimpleGrantedAuthority` is an implementation holding a single permission string.
2. A collection of permission objects attached to `Authentication`; an authority is not a password store.
3. With the default prefix, `hasRole("USER")` looks for `ROLE_USER` so it matches; `hasAuthority("USER")` looks for exact `USER` and does not match `ROLE_USER`.
4. No. Grant `ROLE_USER` as well or configure a `RoleHierarchy` used by the policies.
5. String matching is case-sensitive.
6. The default converter typically produces `SCOPE_orders.read`. Rules must match the mapped string or customize the converter intentionally.
7. It bloats `Authentication`/tokens/sessions and makes updates and revocation difficult; object-level checks belong in domain policies.
8. A coarse action permission does not prove permission on a specific object.
9. To test the authority once the request passes the CSRF layer; otherwise CSRF may block the request first.
10. Clients could send `ROLE_ADMIN`; authorities must be assigned from a trusted source after authentication.
11. Not necessarily. An appropriate refresh, revocation, or runtime policy mechanism is required.
12. An `AuthorizationManager`/delegate that understands the custom authority and evaluates its specialized data.

## 15. References

- [Spring Security – Authorization Architecture: GrantedAuthority and SimpleGrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security – GrantedAuthority API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html)
- [Spring Security – SimpleGrantedAuthority API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/SimpleGrantedAuthority.html)
