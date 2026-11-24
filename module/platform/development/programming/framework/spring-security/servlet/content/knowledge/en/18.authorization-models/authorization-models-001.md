# GrantedAuthority, Roles, and Operation Permissions in Business Models

> **Scope:** Spring Security **Servlet** 6.x, Java 17+, authorization based on `Authentication.getAuthorities()`. This article explains how `GrantedAuthority` represents **roles** and **operation permissions**, how to design a role → permission mapping table, handle the `ROLE_` prefix, configure URL and service authorization with `@PreAuthorize`, and distinguish operation permissions from data ownership. A runnable Spring Boot 3.3.5 application demonstrates both GET and CSRF-protected POST requests.

## 1. The Business Problem: “Who the User Is” Differs from “What the User Can Do”

Suppose an order management system has the following staff groups:

- **Operations staff:** view orders, but cannot automatically approve them.
- **Approvers:** can view and approve orders.
- **Auditors:** view audit reports, without implicitly approving orders.
- **Administrators:** manage sensitive configuration and can be granted necessary operation permissions.
- **Temporarily delegated staff:** although holding the staff role, are granted additional approval permission within a valid scope.

If you only ask “is the user logged in?”, everyone can do the same thing, which violates policy. If you only ask “do they have the ADMIN role?”, routine operations such as viewing orders, approving orders, or viewing audits get lumped into an overly broad role.

Separating the conceptual layers:

```text
Identity / Authentication
  "Who is this verified account?"
             |
             v
Role / Responsibility group
  "Which job group does this person belong to?"
             |
             v
Permission / Operation permission
  "Which actions is this person allowed to perform?"
             |
             v
Resource-level policy / Object-level permission
  "Is this action allowed on THIS SPECIFIC order #42?"
             |
             v
Domain invariant
  "Is order #42 currently in a valid state for approval?"
```

Spring Security places application-layer roles and permissions into `Collection<? extends GrantedAuthority>` on `Authentication`, and authorization rules then compare them. To check ownership, branch, tenant, or order state, the application also needs business logic backed by **trusted server data**.

**Four questions must be answered separately:** who the identity is, what the role is, what permissions are held, and whether access is allowed on this specific resource. Avoid collapsing everything into a single `isAdmin` Boolean.

## 2. What Exactly Is GrantedAuthority?

`GrantedAuthority` is a Spring Security interface representing **a granted authorization privilege/attribute** for an `Authentication`. In the common model, each authority is a string.

```java
package org.springframework.security.core;

import java.io.Serializable;

public interface GrantedAuthority extends Serializable {
    String getAuthority();
}
```

Above is the condensed interface signature for conceptual learning; Spring Security already defines it, **do not recreate this file in your project**.

Common implementation:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority role = new SimpleGrantedAuthority("ROLE_STAFF");
GrantedAuthority permission = new SimpleGrantedAuthority("ORDER_READ");

System.out.println(role.getAuthority());
System.out.println(permission.getAuthority());
```

Output when running the fragment in a Java program with the proper imports and classpath:

```text
ROLE_STAFF
ORDER_READ
```

**`SimpleGrantedAuthority` has no separate flag** saying “this is a role” or “this is a permission”. Both are `GrantedAuthority` instances holding a string. The difference comes from **naming conventions and application rules**. `ROLE_STAFF` is typically treated as a role because of the `ROLE_` prefix; `ORDER_READ` is an operation permission defined by the development team.

Complex `GrantedAuthority` implementations may not be representable by a single string, and `getAuthority()` can return `null`. When using `hasAuthority("...")` with `SimpleGrantedAuthority`, rely on non-null strings and **exact matching**, without assuming all custom authorities share the same semantics.

### Where Do Authorities Live?

After successful authentication, `Authentication` typically contains:

- `getPrincipal()`: the identity, such as `UserDetails` or a token principal.
- `getAuthorities()`: the set of `GrantedAuthority` assigned/mapped from a trusted source.
- `getCredentials()`: authentication credentials (which may have been erased for security).
- `isAuthenticated()`: authentication status.

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    for (GrantedAuthority authority : authentication.getAuthorities()) {
        System.out.println(authority.getAuthority());
    }
}
```

This is a **Java fragment** requiring the corresponding imports. In a real application, do not log the entire `Authentication`, credentials, or personal information. Inspecting the list of authorities can be useful in development, but visibility must be controlled when sensitive data is involved.

**Who grants `GrantedAuthority`?** `UserDetailsService`, authentication providers, JWT/OIDC claims converters, or mapping performed by a trusted system. Clients **must not be able to send `roles=["ROLE_ADMIN"]` and have the server treat it as a valid privilege**.

## 3. How Do Roles, Permissions, and Resource Policies Differ?

| Concept | Example | Meaning | Sufficient to allow the action? |
| --- | --- | --- | --- |
| **Role** | `ROLE_STAFF`, `ROLE_APPROVER` | Job role or responsibility group | Not necessarily; need to know which permissions the role carries |
| **Permission** | `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ` | Capability to perform a type of operation | Not necessarily; resource constraints may still apply |
| **Resource ownership** | User is the assignee for order `42` | Privilege tied to a specific object | Must be verified from a trusted data source |
| **Tenant scope** | User belongs to tenant `acme` | Multi-tenant data boundary | Must be bound to request data and principal |
| **Domain state** | Order is in `PENDING` state | Precondition of the action | Does not replace permission |
| **Authentication** | User is logged in | Identity verification | Does not automatically grant all privileges |

Example approval rule:

```text
ALLOW_APPROVE(orderId, user) =
    user is authenticated
    AND user has authority ORDER_APPROVE
    AND order belongs to an allowed tenant/business unit
    AND user is permitted to approve this specific order
    AND order.status == PENDING
```

Here `ORDER_APPROVE` is a **functional permission**; tenant, owner/assignee, and order state are **data-driven business conditions**. Do not simply add `ROLE_ADMIN` and skip tenant verification if the product requires tenant isolation.

### RBAC and Permission-Based Access

- **RBAC (Role-Based Access Control):** authorization based on roles. “Auditors have permission to read audits”. Typically users are assigned roles, and roles hold a set of permissions.
- **Permission-based:** rules check operation permissions, such as `hasAuthority("ORDER_APPROVE")`, without caring which role the user got them from. One permission can be granted by multiple roles or via direct delegation.
- **ABAC / attribute-based policy:** combines roles/permissions with user, resource, organization, time, or state attributes. This is not something `GrantedAuthority` handles automatically; it requires an appropriate authorization manager or domain service.

Practical designs usually **combine them**: use roles to manage user groups, translate roles into clear permissions, then protect endpoints/services by permission and enforce deeper scope/resource checks.

## 4. The ROLE_ Prefix: A Small Convention with Major Impact

Spring Security typically uses the convention of prefixing roles with `ROLE_`. Consider these expressions:

```java
// Three example fragments inside authorizeHttpRequests:
auth.requestMatchers("/admin").hasRole("ADMIN");
auth.requestMatchers("/admin-by-authority").hasAuthority("ROLE_ADMIN");
auth.requestMatchers("/orders").hasAuthority("ORDER_READ");
```

With the **default role prefix**, the first two rules both require the authority string `ROLE_ADMIN`, while the third requires `ORDER_READ`.

| Rule | Expected GrantedAuthority string |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ADMIN")` | `ADMIN` |
| `hasAuthority("ORDER_READ")` | `ORDER_READ` |
| `hasRole("ORDER_READ")` | `ROLE_ORDER_READ`, **not equal to** `ORDER_READ` |

Common mistake: the user store saves `ADMIN`, but the code uses `hasRole("ADMIN")`; the result is 403 because the framework looks for `ROLE_ADMIN`. Or a developer writes `hasAuthority("ADMIN")` while `User.withUsername(...).roles("ADMIN")` creates `ROLE_ADMIN`.

### roles() and authorities() in the User Builder

```java
// Fragment - two different ways of expressing authorities:
UserDetails fromRoles = User.withUsername("mai")
        .password("{noop}local-only")
        .roles("STAFF")
        .build();

UserDetails fromAuthorities = User.withUsername("mai")
        .password("{noop}local-only")
        .authorities("ROLE_STAFF", "ORDER_READ")
        .build();
```

- `.roles("STAFF")` creates the `ROLE_STAFF` authority per builder convention.
- `.authorities("ROLE_STAFF","ORDER_READ")` adds the **exact** two strings passed in.
- `.roles("ROLE_STAFF")` is usually a misuse because `.roles()` does not expect input already prefixed with `ROLE_`.
- The `{noop}local-only` password in this fragment only illustrates builder syntax; the runnable sample application in Section 9 uses BCrypt. **Do not store plaintext/`{noop}` passwords in production.**

**You can customize the role prefix** in certain configuration/authorization infrastructure points, but do not assume every API, method security expression, and third-party integration uses the changed prefix identically. If you change the default prefix, test URL rules, method rules, and token converters consistently. A simple way to reduce confusion is to use `hasAuthority("ROLE_ADMIN")`, or follow the `hasRole("ADMIN")` convention and store `ROLE_ADMIN` consistently.

## 5. Designing a Business-Aligned Permission Catalog

Good permission names should express **resource/action**, remain stable, and stay independent of the UI:

| Permission | Meaning | Typical API/operation |
| --- | --- | --- |
| `ORDER_READ` | Read order details | `GET /api/orders/{id}` |
| `ORDER_CREATE` | Create a new order | `POST /api/orders` |
| `ORDER_UPDATE` | Edit order details | `PUT /api/orders/{id}` |
| `ORDER_APPROVE` | Approve an order | `POST /api/orders/{id}/approve` |
| `ORDER_CANCEL` | Cancel an order | `POST /api/orders/{id}/cancel` |
| `AUDIT_READ` | Read audit trail | `GET /api/audit` |
| `REPORT_EXPORT` | Export reports | `POST /api/reports/export` |
| `USER_MANAGE` | Manage accounts | User administration endpoint |

**Do not confuse HTTP methods with business permissions.** `POST` only indicates the request may create/mutate state, not that “this is an approval”. `ORDER_APPROVE` expresses the permitted action; mapping an HTTP route to a permission is application policy.

Use consistent naming such as `RESOURCE_ACTION` and document each meaning. Avoid:

- `CAN_DO_EVERYTHING` with no clear scope.
- `BUTTON_APPROVE_VISIBLE` tied to UI details.
- An overly broad `ORDER_WRITE` permission covering edits, deletes, refunds, and approvals.
- Attaching money transfers or sensitive data changes to an admin role without required controls.
- Embedding tenant IDs or order IDs into authority names for every resource, which causes an uncontrolled explosion of authorities; for dynamic per-resource permissions, server-side checks are more appropriate.

### Backend Authorization Differs from Hiding/Showing Frontend Buttons

The frontend can hide the “Approve” button when a user lacks `ORDER_APPROVE`, but hiding a button **is not authorization**. Clients can still send a `POST` request directly. The backend must check the permission at the HTTP or service layer and enforce business conditions against the specific order.

A UI may call `GET /api/me` to display the user's permissions, but that response data is only for user experience, not the place where privileges are granted. The source of truth is server-side authentication/authorization, and policies can change over time.

## 6. Role → Permission: A Maintainable Model

Example mapping of roles to permissions:

| Role | Typically granted permissions |
| --- | --- |
| `ROLE_STAFF` | `ORDER_READ`, possibly `ORDER_UPDATE` within assigned scope |
| `ROLE_APPROVER` | `ORDER_READ`, `ORDER_APPROVE` |
| `ROLE_AUDITOR` | `AUDIT_READ` |
| `ROLE_ADMIN` | `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ`, and only genuinely approved privileges |
| Additional delegation to a user | Specific permission with expiration/scope, without necessarily changing the base role |

This is a **sample design**; Spring Security does not automatically know that `ROLE_APPROVER` implies `ORDER_APPROVE`. If `Authentication` only contains `ROLE_APPROVER`, the rule `hasAuthority("ORDER_APPROVE")` **does not succeed automatically**. The system must:

1. Store a role–permission table in a database or trusted configuration source.
2. When the user is authenticated, aggregate permissions from roles and direct grants.
3. Convert the result into the actual `GrantedAuthority` set on `Authentication`.
4. Enforce `hasAuthority(...)` or `@PreAuthorize(...)` on the server.
5. Have a policy to refresh/revoke authorities when roles/permissions change.

Reference relational data model:

```text
users(id, username, password_hash, active)
roles(id, code)                          -- STAFF, APPROVER, AUDITOR
permissions(id, code)                   -- ORDER_READ, ORDER_APPROVE
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id, expires_at)  -- optional

A user can have multiple roles.
A role can have multiple permissions.
A permission can come from multiple roles.
Direct permissions may require expires_at and auditing.
```

The schema above is a **model illustration**, not a complete SQL migration. Production needs unique constraints, foreign keys, tenant scoping, authorization over role changes, auditing, and revocation handling. In particular, **the privilege to grant privileges** must be tightly protected so it does not become a privilege-escalation path.

### Where Should Roles Be Mapped to Authorities?

Depending on the authentication mechanism:

- **Username/password + UserDetailsService:** after looking up the user and reading roles/permissions from the database, return `UserDetails` with the granted authorities.
- **OIDC/OAuth2 login:** verify identity first, then map claims/groups from a trusted source to application authorities; never trust unverified claims.
- **JWT resource server:** the decoder/validator must verify signature, issuer, audience, and expiry before the converter translates scopes/roles into authorities.
- **External authorization service:** an `AuthorizationManager` can query a policy service on each request; latency, caching, fail-closed behavior, auditing, and trusted inputs must be controlled.

Do not put privileges from an unverified JWT or arbitrary HTTP header into `Authentication`. With JWT scopes, Spring Security Resource Server typically uses the `SCOPE_` prefix for scopes, distinct from the `ROLE_` convention; this requires intentional mapping.

## 7. URL Authorization and Method/Service Authorization

Spring Security Servlet lets you protect HTTP routes using:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
            .hasAuthority("ORDER_READ")
        .requestMatchers(HttpMethod.POST, "/api/orders/{id}/approve")
            .hasAuthority("ORDER_APPROVE")
        .requestMatchers(HttpMethod.GET, "/api/admin/health")
            .hasRole("ADMIN")
        .anyRequest().denyAll());
```

This is a **fragment** inside a `SecurityFilterChain`. When a URL matches a rule, `AuthorizationFilter` evaluates `Authentication.getAuthorities()`. `hasAuthority` performs an exact string match; `hasRole` follows the role prefix convention.

**Why add method security?** In a larger application, a service can be invoked from an HTTP controller, background job, GraphQL handler, or other code. If order approval is only protected at the URL level, another entrypoint calling the service could bypass the policy. When `@EnableMethodSecurity` is enabled, placing `@PreAuthorize` on business methods provides a useful layer of protection:

```java
@PreAuthorize("hasAuthority('ORDER_APPROVE')")
public OrderView approve(long id) {
    // Domain logic needs to check state and ownership inside the service.
}
```

This fragment only illustrates the annotation; the runnable method is in the full service in Section 9. `@PreAuthorize` on a Spring bean is invoked **through a Spring proxy**; calling a method on the same object (`this.approve(...)`) can bypass the proxy and skip method-security advice. Call the service bean from a controller or an appropriate architecture.

### Multi-Layer Rules Should Not Contradict Each Other

If the URL requires `ORDER_APPROVE` and the method also requires `ORDER_APPROVE`, the repetition provides **defense in depth**. However, if the URL allows broader access than the service, the request passes the filter but is still blocked at the method (typically 403 for an authenticated user). Test HTTP and method-level policies together and avoid ambiguous error messages.

If method security is used for a service without an HTTP request, make sure an authentication context is supplied safely during that task. Never let a background job assume unchecked admin privileges just to “avoid 403”.

## 8. Operation Permissions Are Not Enough: Resource and Tenant Checks

Suppose a user has `ORDER_READ` but may only view orders belonging to their own branch:

```text
HTTP GET /api/orders/42
    |
    v
Authentication contains ORDER_READ
    |
    v
HTTP authorization allows through
    |
    v
OrderService checks orderId=42
    |
    +-- Load actual order from database
    +-- Determine order's tenant/branch/owner
    +-- Compare against user's trusted permission scope
    |
    +-- Match: return data
    +-- Mismatch: deny (403) or 404 depending on resource disclosure policy
```

This is a critical boundary to prevent **IDOR/BOLA (Broken Object Level Authorization)**. `hasAuthority("ORDER_READ")` only knows the user has a type of permission; it **does not know** which tenant order 42 belongs to, which customer owns it, or whether the record is locked.

One way to express the policy:

```text
CAN_READ_ORDER(authentication, orderId) =
    hasAuthority(authentication, "ORDER_READ")
    AND orderRepository.findById(orderId).tenantId
        IN trustedAllowedTenants(authentication)
```

This is pseudo-code, not full Spring Expression Language syntax. In real code, only use `tenantId` obtained from the principal, permission store, or server-side memberships; never rely solely on a client-supplied `X-Tenant-Id` header to make authorization decisions.

### Custom Bean in @PreAuthorize

One pattern you can use:

```java
// Fragment illustrating the idea, requiring a real orderPolicy bean:
@PreAuthorize("hasAuthority('ORDER_READ') and @orderPolicy.canRead(authentication, #id)")
public OrderDetails loadOrder(long id) {
    return repository.findDetails(id);
}
```

`orderPolicy.canRead`, `OrderDetails`, and `repository` are application components you need to implement. Ensure Spring Security can resolve the method parameter name `id` (or use `@P("id")` / metadata configuration when needed), verify ownership using server data, and avoid N+1 query issues.

**For write operations**, also consider domain invariants: the order must be in `PENDING` state, the user cannot self-approve an order they created if a separation-of-duties policy applies, and two-person approval may be required. A check in an HTTP filter cannot guarantee that resource state remains valid up to transaction commit.

### TOCTOU: Permissions and State Can Change

In a concurrent environment, an order's status or assignee can change after the authorization filter has already checked. Use transactions, optimistic locking, conditional updates (for example, updating only while status is still PENDING), and domain-level checks inside the service to prevent **time-of-check/time-of-use** races. `GrantedAuthority` does not lock database records.

## 9. Runnable Example: Java 17 + Spring Security 6 + Spring Boot 3.3.5

The Servlet application below uses HTTP Basic to make inspecting identities/authorities easy and includes a POST endpoint to approve orders. **To avoid teaching bad practices about CSRF**, the demo keeps CSRF protection enabled even with Basic auth, and provides a GET endpoint that issues a token so an HTTP client can make POST calls with a valid cookie + CSRF header.

### Endpoints and Policy

| Method + URL | HTTP authorization | Service authorization | Result |
| --- | --- | --- | --- |
| `GET /api/hello` | `permitAll()` | Not required | Public message |
| `GET /api/csrf` | `permitAll()` | Not required | CSRF token for POST |
| `GET /api/me` | `authenticated()` | Not required | User + list of authorities |
| `GET /api/orders/{id}` | `ORDER_READ` | `ORDER_READ` | Order data |
| `POST /api/orders/{id}/approve` | `ORDER_APPROVE` | `ORDER_APPROVE` | Transitions demo order state |
| `GET /api/audit` | `AUDIT_READ` | Not required | Audit demo message |
| `GET /api/admin/health` | `ROLE_ADMIN` via `hasRole("ADMIN")` | Not required | Admin-only message |

### Users and Authorities in the Demo

| Username | Demo password | GrantedAuthority |
| --- | --- | --- |
| `mai` | `demo123` | `ROLE_STAFF`, `ORDER_READ` |
| `an` | `demo123` | `ROLE_APPROVER`, `ORDER_READ`, `ORDER_APPROVE` |
| `linh` | `demo123` | `ROLE_STAFF`, `ORDER_READ`, `ORDER_APPROVE` |
| `binh` | `demo123` | `ROLE_AUDITOR`, `AUDIT_READ` |
| `root` | `demo123` | `ROLE_ADMIN`, `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ` |
| `guest` | `demo123` | `ROLE_GUEST` |

User `linh` illustrates **a user holding the STAFF role who is granted an additional ORDER_APPROVE permission**. Because rules check permissions, this user can approve orders even without holding `ROLE_APPROVER`. Real applications must enforce governance, logging, and time limits on such delegations.

### 9.1. Project Structure

```text
authorities-demo/
├── pom.xml
├── src/main/java/example/authorities/
│   ├── AuthoritiesApplication.java
│   ├── SecurityConfig.java
│   ├── OrderService.java
│   └── ApiController.java
└── src/test/java/example/authorities/
    └── AuthorizationRulesTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authorities-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

### 9.3. AuthoritiesApplication.java

```java
package example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.authorities;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");

        return new InMemoryUserDetailsManager(
                User.withUsername("mai").password(hash)
                        .authorities("ROLE_STAFF", "ORDER_READ").build(),
                User.withUsername("an").password(hash)
                        .authorities("ROLE_APPROVER",
                                "ORDER_READ", "ORDER_APPROVE").build(),
                User.withUsername("linh").password(hash)
                        .authorities("ROLE_STAFF",
                                "ORDER_READ", "ORDER_APPROVE").build(),
                User.withUsername("binh").password(hash)
                        .authorities("ROLE_AUDITOR", "AUDIT_READ").build(),
                User.withUsername("root").password(hash)
                        .authorities("ROLE_ADMIN", "ORDER_READ",
                                "ORDER_APPROVE", "AUDIT_READ").build(),
                User.withUsername("guest").password(hash)
                        .authorities("ROLE_GUEST").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/hello").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                        .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders/{id}/approve")
                        .hasAuthority("ORDER_APPROVE")
                .requestMatchers(HttpMethod.GET, "/api/audit")
                        .hasAuthority("AUDIT_READ")
                .requestMatchers(HttpMethod.GET, "/api/admin/health")
                        .hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());

        // Identity comes from request credentials, not from a web session.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // Do not disable CSRF for HTTP Basic: browsers can cache credentials.
        // Cookie stores the CSRF token; clients fetch the token from GET /api/csrf,
        // then send the cookie + X-XSRF-TOKEN header on POST.
        http.csrf(csrf -> csrf.csrfTokenRepository(
                new CookieCsrfTokenRepository()));

        return http.build();
    }
}
```

**Reading the code:**

1. `@EnableMethodSecurity` allows Spring to enforce `@PreAuthorize` on service beans.
2. `UserDetailsService` returns both role authorities (`ROLE_...`) and operation permissions. Sharing one BCrypt hash across demo accounts is valid for password matching, but real accounts must have distinct passwords, persistently stored hashes, and comply with password policies.
3. `hasAuthority("ORDER_APPROVE")` checks the permission **exactly** and does not infer it from `ROLE_APPROVER`.
4. `hasRole("ADMIN")` uses the default `ROLE_` prefix and allows only the `root` account on the demo admin route.
5. `STATELESS` does not load `SecurityContext` from an HTTP session; HTTP Basic uses credentials on every request. It **does not mean other controllers cannot create an `HttpSession`**.
6. `CookieCsrfTokenRepository` is a **CSRF token storage mechanism**, independent of `SecurityContext` storage. Because the demo app has state-changing POST requests and Basic credentials can be sent automatically by browsers, CSRF protection is retained.
7. `NullRequestCache` fits APIs that do not redirect back after form login. `anyRequest().denyAll()` fails closed for undefined URLs.
8. The demo has no automatic role hierarchy and no real database: each user's authorities are explicitly declared to make the policy clear.

### 9.5. OrderService.java

```java
package example.authorities;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final Map<Long, OrderView> orders = new ConcurrentHashMap<>();

    public OrderService() {
        orders.put(42L, new OrderView(42L, "PENDING"));
        orders.put(43L, new OrderView(43L, "PENDING"));
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderView get(long id) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }
        return order;
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public OrderView approve(long id) {
        OrderView updated = orders.computeIfPresent(
                id, (key, oldValue) -> new OrderView(key, "APPROVED"));
        if (updated == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }
        return updated;
    }

    public record OrderView(long id, String status) {
    }
}
```

**Explanation:** This is an **in-memory order store solely for hands-on practice**. `ConcurrentHashMap` keeps demo requests updating objects reasonably safely within a single process; the code **does not check tenant, assignee, separation of duties, or complex state transitions**. Production needs a database, transactions, and resource-level policies as discussed in Section 8. `@PreAuthorize` on the service acts as an extra safeguard: if another entrypoint calls the service via a Spring bean, the permission rule is still enforced.

In this demo, `approve` also transitions an already APPROVED order to APPROVED (idempotent at the status level); production may reject re-approvals, record audits, and require business confirmation.

### 9.6. ApiController.java

```java
package example.authorities;

import java.util.List;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final OrderService orderService;

    public ApiController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/hello")
    public String hello() {
        return "hello:public";
    }

    @GetMapping("/api/csrf")
    public String csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }
        return token.getToken();
    }

    @GetMapping("/api/me")
    public MeView me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new MeView(auth.getName(), authorities);
    }

    @GetMapping("/api/orders/{id}")
    public OrderService.OrderView order(@PathVariable long id) {
        return orderService.get(id);
    }

    @PostMapping("/api/orders/{id}/approve")
    public OrderService.OrderView approve(@PathVariable long id) {
        return orderService.approve(id);
    }

    @GetMapping("/api/audit")
    public String audit() {
        return "audit:ok";
    }

    @GetMapping("/api/admin/health")
    public String adminHealth() {
        return "admin:ok";
    }

    public record MeView(String user, List<String> authorities) {
    }
}
```

`GET /api/me` outputs a sorted list of authorities to make inspecting permissions easy in the lab. In production, do not expose detailed sensitive permission lists unless required by the product; this endpoint requires `authenticated()` and must follow API policy.

`GET /api/csrf` reads `CsrfToken` from the request attribute provided by Spring Security. Reading `getToken()` causes the token to be materialized in the flow, allowing the cookie repository to send the corresponding CSRF cookie. If you change the request handler or token repository in Spring Security, re-test how the token is retrieved and submitted.

### 9.7. Running the Project

Use JDK 17+ and Maven 3.9+ in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

With the default configuration, the application listens on `http://localhost:8080`. The curl commands below are for **localhost**; real deployments must use **HTTPS**, because HTTP Basic sends credentials recoverable from Base64 and the CSRF cookie is not a network encryption mechanism.

## 10. Practicing READ, APPROVE, AUDIT, and ROLE_ADMIN Permissions

### 10.1. Public Endpoint

```bash
curl -s http://localhost:8080/api/hello
```

Expected body:

```text
hello:public
```

Without a Basic header, this still returns 200 due to the `permitAll()` rule. However, if a client **actively sends** invalid Basic credentials even to a public URL, the authentication filter may still attempt authentication and cause a 401 before the authorization rule runs.

### 10.2. Missing Credentials to an Endpoint Requiring Login

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me
```

Expected result:

```text
401
```

This is **missing authentication**, not an authenticated user lacking permission.

### 10.3. User mai Has ORDER_READ

```bash
curl -s -u mai:demo123 http://localhost:8080/api/orders/42
```

Expected JSON body before order approval:

```json
{"id":42,"status":"PENDING"}
```

`mai` has `ORDER_READ`, so both the HTTP rule and `OrderService.get` allow access. `mai` lacks `ORDER_APPROVE` and cannot successfully invoke the approve endpoint.

### 10.4. Inspecting a User's Authorities

```bash
curl -s -u linh:demo123 http://localhost:8080/api/me
```

Expected JSON body:

```json
{"user":"linh","authorities":["ORDER_APPROVE","ORDER_READ","ROLE_STAFF"]}
```

The list is sorted alphabetically. This case illustrates the direct `ORDER_APPROVE` permission granted to user `linh`'s STAFF role in the demo; Spring Security does not infer this permission from `ROLE_STAFF`.

### 10.5. POST Requires a Valid CSRF Token

With CSRF protection enabled in the project, the following command is **not** enough:

```bash
curl -i -u an:demo123 -X POST \
  http://localhost:8080/api/orders/42/approve
```

Without a CSRF token, the response is typically **403** before HTTP/method authorization allows the operation.

Fetch the token **and** save the cookie in a same-origin request:

```bash
csrf_token="$(curl -fsS -c csrf-cookies.txt \
  http://localhost:8080/api/csrf)"
```

Send both the cookie and the token via header:

```bash
curl -i -u an:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/42/approve
```

Expected response has status **200** and JSON body:

```json
{"id":42,"status":"APPROVED"}
```

**Why must the token returned by `/api/csrf` be used?** Spring Security 6 protects CSRF tokens against BREACH via masking by default. The token obtained from `CsrfToken.getToken()` in the request can differ from the raw value stored in the cookie. Do not simply assume you can read the `XSRF-TOKEN` cookie and send that exact value in the header across every request handler/config; follow the token-issuing contract and test it. The example is designed so curl saves the cookie from the same origin and sends back the returned token.

### 10.6. User mai Cannot Approve Even with Valid CSRF

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u mai:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/43/approve
```

Expected:

```text
403
```

This time CSRF is valid, but `Authentication` lacks `ORDER_APPROVE`. **Do not fix this by disabling CSRF**: the issue is permission policy, not request validation.

### 10.7. User linh Has ROLE_STAFF but Was Granted a Separate Approve Permission

```bash
curl -s -u linh:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/43/approve
```

Expected:

```json
{"id":43,"status":"APPROVED"}
```

Although `linh` does not have `ROLE_APPROVER`, this user holds `ORDER_APPROVE` in their authorities list, so both URL and service-level checks allow it. The example shows the benefit of **protecting operations with specific permissions**, rather than forcing everyone who needs to approve orders to switch their primary job role.

### 10.8. Auditor Can Read Audits, Not Orders Under the Demo's Default Privileges

```bash
curl -s -u binh:demo123 http://localhost:8080/api/audit

curl -s -o /dev/null -w '%{http_code}\n' \
  -u binh:demo123 http://localhost:8080/api/orders/42
```

Expected two outputs:

```text
audit:ok
403
```

`binh` has `ROLE_AUDITOR` and `AUDIT_READ`, but **does not** have `ORDER_READ`. An auditor role does not automatically equate to permission to read all data.

### 10.9. hasRole("ADMIN") Checks the ROLE_ Prefix

```bash
curl -s -u root:demo123 http://localhost:8080/api/admin/health

curl -s -o /dev/null -w '%{http_code}\n' \
  -u an:demo123 http://localhost:8080/api/admin/health
```

Expected:

```text
admin:ok
403
```

`root` has `ROLE_ADMIN`, whereas `an`, despite having `ORDER_APPROVE`, still does not have the ADMIN role. When administrative authorization is needed, use both specific permissions and scope controls to avoid an overly broad super-role.

### 10.10. Summary Authorization Matrix

| User | GET order | POST approve (valid CSRF) | GET audit | GET admin |
| --- | --- | --- | --- | --- |
| Anonymous | 401 | 401 or 403 if missing CSRF | 401 | 401 |
| `mai` | 200 | **403** | 403 | 403 |
| `an` | 200 | **200** | 403 | 403 |
| `linh` | 200 | **200** | 403 | 403 |
| `binh` | **403** | **403** | 200 | 403 |
| `root` | 200 | 200 | 200 | 200 |
| `guest` | 403 | 403 | 403 | 403 |

The table assumes the URL exists and POST includes a valid CSRF token. When CSRF is missing, a POST request may receive 403 **before** authorization runs. The body of a 200 response can differ if the demo order state was already modified by a prior request; restart the app to reset in-memory state.

## 11. Automated Testing with Spring Security Test

The `pom.xml` already includes `spring-boot-starter-test` and `spring-security-test`. Create the file:

```text
src/test/java/example/authorities/AuthorizationRulesTest.java
```

Contents:

```java
package example.authorities;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staffCanReadButCannotApprove() throws Exception {
        mvc.perform(get("/api/orders/42").with(user("mai")
                .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isOk());

        mvc.perform(post("/api/orders/42/approve")
                .with(csrf())
                .with(user("mai").authorities(
                        new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void approverCanApproveWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/orders/42/approve")
                .with(csrf())
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isOk());
    }

    @Test
    void adminRoleIsSeparateFromOperationPermission() throws Exception {
        mvc.perform(get("/api/admin/health")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk());

        mvc.perform(get("/api/admin/health")
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsDeniedEvenWithPermission() throws Exception {
        mvc.perform(post("/api/orders/42/approve")
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
mvn test
```

**What the test verifies:** Requests carrying a mocked `Authentication` with predefined authorities are passed through the security filters and service method interceptor. `with(user(...))` **does not** test passwords in `UserDetailsService`; to test authentication end-to-end, add tests using real HTTP Basic headers. This tests the **authorization policy** decoupled from password verification.

One detail to note: if test methods run in parallel and both mutate order 42, status changes could affect data assertions. The test suite above only asserts HTTP status, independent of whether the order is still PENDING or already APPROVED. When testing domain transitions, reset database/in-memory state or use independent fixtures.

### Cases to Catch in Regression Tests

- `ROLE_STAFF` cannot approve if `ORDER_APPROVE` is missing.
- `ROLE_APPROVER` without the permission is **not** enough, unless the mapper granted the permission.
- `ROLE_ADMIN` does not automatically carry every permission unless mapped.
- `AUDIT_READ` does not imply `ORDER_READ`.
- Reading requires `ORDER_READ`; POST approve requires `ORDER_APPROVE` and valid CSRF.
- Method-level `@PreAuthorize` applies even if the controller is renamed or a new entrypoint is added.

## 12. Role Hierarchy, Inheritance, and Delegation

Some systems want admins to “inherit” staff permissions. Spring Security supports the **role hierarchy** concept in appropriate configurations, but **does not automatically infer** that `ROLE_ADMIN` contains every role. If inheritance is desired, it must be **explicitly defined**, and you must verify how the role hierarchy is wired into both URL and method authorization.

```text
Illustration of inheritance policy (not mandatory DSL):
ROLE_ADMIN > ROLE_APPROVER > ROLE_STAFF
```

Caution: role hierarchies can introduce unintended privileges. For example, an auditor under a separation-of-duties policy **should not** implicitly inherit approval rights. In large systems, an explicit **role → permissions** mapping is easier to audit than a hierarchy graph with hidden edges.

### Direct and Temporary Permission Grants

An employee delegated to approve orders for one week should have a complete record capturing:

- Who granted and who approved the grant?
- Which permission and which scope (branch, tenant, maximum order value)?
- Effective start and expiration timestamps?
- Is two-person approval required for sensitive transactions?
- Upon revocation, how quickly does the privilege disappear from sessions, JWTs, or caches?

Do not simply add `ORDER_APPROVE` to a 30-day JWT and assume revoking it in the DB immediately strips the privilege from already-issued JWTs. With self-contained tokens, authorities are a snapshot at issuance time unless the application implements dynamic permission checks or revocation.

## 13. Sessions, JWTs, and When Permission Updates Take Effect

Changing permissions in the database **does not guarantee** every request using an existing session/token will immediately see the change.

| Authentication mode | Where authorities typically come from | Stale permissions risk |
| --- | --- | --- |
| Username/password with HTTP Basic per request | UserDetailsService/provider checks credentials | Can be stale if user cache/mapping has not updated |
| Form login + session | Authentication stored in the session's SecurityContext | Role changes after login, but old context keeps old authorities |
| JWT access token | Claims signed at issuance/mapping time | Unexpired token still carries the old claim snapshot |
| OIDC login | IdP claims/authorities mapped at login/refresh | Permissions in the session/login can be stale |
| Dynamic policy service | Looked up each time or via cache | Permission changes can lag by TTL/cache invalidation |

To reduce risk: choose appropriately short-lived tokens, revoke/expire sessions when sensitive permissions change, support token introspection or dynamic service checks for critical actions, and maintain a cache invalidation policy.

**Important:** `hasAuthority("ORDER_APPROVE")` does not automatically run a database query to ask whether a permission was just revoked; it typically evaluates the **currently held** `Authentication.getAuthorities()`. Ensure your authentication/claims refresh strategy reflects the system's revocation requirements.

## 14. Common Mistakes and Vulnerabilities

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Has `ADMIN` but `hasRole("ADMIN")` still returns 403 | Missing `ROLE_` prefix | Store `ROLE_ADMIN` or map the prefix consistently |
| Has role STAFF but `hasAuthority("ORDER_READ")` returns 403 | Framework does not automatically map roles to permissions | Add a role–permission mapping in a trusted source |
| Regular user can reach the approval endpoint | Only checks `authenticated()` or `permitAll()` | Protect with specific permissions and method security |
| Auditor can read every tenant | Only checks `AUDIT_READ`, omits scope check | Add server-side tenant/resource policy |
| Authorization looks fine in UI, yet HTTP still allows it | Only hid frontend buttons | Enforce URL/service authorization on the backend |
| Token keeps privilege after DB revocation | Authorities in session/JWT are stale | Apply appropriate revocation/refresh/cache invalidation |
| 401 when not logged in | Missing authentication | This is not a permission grant bug |
| 403 when user is logged in | Missing permission, CSRF failure, or resource policy denial | Inspect filter order and decision |
| POST has permission but returns 403 | Missing/invalid CSRF token | Send the valid token or design CSRF per threat model |
| Write privilege bypassed when calling service directly | Only controller/URL is protected | Use `@PreAuthorize` on the service bean |
| `@PreAuthorize` does not run on self-invocation | Calling method on the same object bypasses the proxy | Split services and call through a Spring-managed proxy |
| Admin accidentally gets all permissions | Uncontrolled mapping of `ROLE_ADMIN` to `*` | Use explicit permissions and separation of duties |
| Data-dependent permission only checks role | Missing resource-level authorization | Look up ownership/tenant/status server-side |

### Sensible Debugging Workflow

1. Did the request enter the **right SecurityFilterChain**? If multiple chains exist, check `securityMatcher` and `@Order`.
2. Verify the authentication provider/decoder validated credentials and does not trust client-sent user/role fields.
3. Observe the **actual** `Authentication` authorities in development (never log secrets).
4. Compare `hasRole` with `hasAuthority` and the `ROLE_` prefix.
5. Identify which permission is required for the method/action and whether URL and method rules align.
6. Distinguish 401 (missing authentication) from 403 (authenticated, but missing permission or CSRF).
7. If the policy is resource-scoped, verify tenant/owner/order state from the database, not from the client.
8. If permissions just changed, check whether the session/JWT/cache was refreshed.
9. Add negative tests: unprivileged user, different tenant, invalid resource state, missing CSRF, wrong role prefix.

You can enable Spring Security logs during development:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log raw `Authorization` headers, Basic credentials, JWTs, session cookies, CSRF tokens, or sensitive data in production. Only log allowed audit metadata: actor ID, permission/action, safely formatted resource ID, decision, and correlation ID.

## 15. Self-Check Questions

1. **Does `GrantedAuthority` only represent roles?** No, it can be a role, a permission, or another application-defined authority string.
2. **Does `SimpleGrantedAuthority("ROLE_STAFF")` differ from `SimpleGrantedAuthority("ORDER_READ")` in Java type?** No, both are the same class; semantics differ by convention.
3. **Which string does `hasRole("ADMIN")` usually check?** `ROLE_ADMIN`.
4. **Do `.roles("ADMIN")` and `.authorities("ADMIN")` create the same authority?** No; the `.roles()` builder prepends the `ROLE_` prefix.
5. **Does the APPROVER role automatically imply ORDER_APPROVE?** No; a role–permission mapping or direct rule is needed.
6. **Does `hasAuthority("ORDER_APPROVE")` know whether the user may approve order 42 belonging to another tenant?** No; resource/tenant checks are required.
7. **Can ORDER_APPROVE be granted directly to a ROLE_STAFF user?** Yes, in a permission-based model, if business rules allow it and auditing/scoping are in place.
8. **Does hiding the approve button on the frontend replace backend authorization?** No.
9. **If a user has ORDER_READ, can they POST to approve?** No, if the rule requires ORDER_APPROVE.
10. **Why can a POST return 403 even with ORDER_APPROVE?** CSRF may be missing or another domain policy may deny it.
11. **Does `@PreAuthorize` automatically run on self-invocation?** In standard proxy-based method security, no; the call must go through the proxy.
12. **Do authorities inside an already-issued JWT change immediately when a DB role is updated?** Not automatically; proper lifecycle/revocation/refresh handling is needed.
13. **Does a role hierarchy appear automatically when naming something ROLE_ADMIN?** No; it must be configured.
14. **Why should direct grants have an expiration time?** It reduces long-lived privileges and supports revocation and auditing.
15. **Is domain status PENDING a GrantedAuthority?** No; it is an object state that must be checked in the service/database.

## 16. Business Authorization Design Checklist

- [ ] Define roles as responsibility groups and permissions as specific operation privileges.
- [ ] Use `GrantedAuthority` from trusted sources; never accept client-declared roles.
- [ ] Standardize the `ROLE_` prefix and distinguish `roles()`, `authorities()`, `hasRole()`, and `hasAuthority()`.
- [ ] Define clear, auditable role–permission mappings; do not grant default privileges beyond what is needed.
- [ ] Protect endpoints by action (`READ`/`CREATE`/`UPDATE`/`APPROVE`/`EXPORT`...), not just `authenticated()`.
- [ ] Use method security / the service layer as a protection layer for critical business actions.
- [ ] Authorize by resource, tenant, and owner using server-side data, not authority strings alone.
- [ ] Enforce domain invariants/TOCTOU checks inside transactions, especially for approvals and refunds.
- [ ] Never use frontend button visibility as security.
- [ ] Choose a lifecycle/cache invalidation strategy to revoke privileges when roles/permissions change.
- [ ] Design direct permissions/temporary delegations with expiration and scope, enforcing separation of duties.
- [ ] Evaluate HTTPS/CSRF/cookies and the authentication scheme; do not disable protections just to make demo POSTs easier.
- [ ] Test anonymous access, invalid credentials, present/missing permissions, wrong role prefix, missing CSRF, and cross-tenant operations.
- [ ] Separate `ROLE_ADMIN` administrative policy from specific business permissions; avoid sprawling wildcard privileges.

**Conclusion:** `GrantedAuthority` is how Spring Security represents **the privileges granted to an Authentication**. Roles (`ROLE_STAFF`, `ROLE_ADMIN`) describe responsibility groups, while permissions (`ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ`) describe **permitted actions**. `hasRole`/`hasAuthority` evaluate the current authority strings; for a secure system, also add **trusted role–permission mapping**, **service/method authorization**, **resource/tenant checks**, CSRF matching the client model, and **a privilege update/revocation process**.