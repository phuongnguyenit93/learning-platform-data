# PermissionEvaluator for Object-Level Action Authorization in Spring Security Servlet

## 1. Why Checking Only Roles Is Insufficient

A document management application typically has an endpoint:

~~~http
GET /api/documents/123 HTTP/1.1
Authorization: Basic ...
~~~

Suppose alice and bob both have `ROLE_USER`. The HTTP rule:

~~~java
.requestMatchers("/api/documents/**").hasRole("USER")
~~~

tells you the caller is a USER, **not who document 123 belongs to, which tenant it is in, whether it is locked, or whether the user has permission to read/edit that specific document**.

This is the distinction between:

- **Role-based access control (RBAC)**: checking general roles like `ROLE_USER` or `ROLE_ADMIN`.
- **Per-resource permissions (object-level authorization)**: checking actions such as `read`, `write`, `delete`, `approve`... on **a specific object**.
- **Ownership/tenant policy**: verifying the resource actually belongs to the permitted principal, group, organization, project, or tenant.
- **Contextual policy**: considering document state, time, approvals, MFA, separation of duties, or other business rules.

Spring Security provides the **`PermissionEvaluator`** interface to back `hasPermission(...)` expressions in method-security expressions. It enables decisions based on **Authentication + resource (or ID/type) + permission**, rather than looking solely at the user's role.

Lesson objectives:

1. Understand both overloads of `PermissionEvaluator` precisely and when each is invoked.
2. Build policies grounded in **trusted server-side resource data**, never trusting client-submitted owner/tenant fields.
3. Wire a custom evaluator into `@PreAuthorize`/`@PostAuthorize` via `MethodSecurityExpressionHandler`, avoiding the assumption that declaring a bean alone suffices in all configurations.
4. Write tests for ownership, same-tenant, cross-tenant, locked state, allowed actions, and denied actions.
5. Understand limits around performance, N+1 queries, race conditions/TOCTOU, CSRF, and differences between 401, 403, and 404.
6. Apply a complete Java 17+ / Spring Boot 3.3.13 / Spring Security 6 example for the **Servlet stack**.

**Core message:** `PermissionEvaluator` is an **authorization decision extension point**, not a permissions database, not an authentication provider, and does not automatically protect all data-access paths.

## 2. PermissionEvaluator in the Spring Security Flow

Conceptual flow:

~~~text
Browser / API client
        |
        v
Servlet filters: Basic / Session / Bearer authentication
        |
        v
Verified Authentication
        |
        v
HTTP authorization, e.g., /api/**.authenticated()
        |
        v
Spring MVC Controller
        |
        v
Spring-managed Service Proxy
        |
        v
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
        |
        +--> MethodSecurityExpressionHandler
        |         |
        |         v
        |     PermissionEvaluator.hasPermission(
        |       Authentication, targetId, targetType, permission)
        |         |
        |         +--> Server-side tenant membership
        |         +--> Document metadata: owner, tenant, locked
        |         +--> Decision: true / false
        |
        +-- true  -> Service method executes
        |
        +-- false -> AccessDeniedException -> typically HTTP 403
~~~

`@PreAuthorize` runs via the Spring method-security interceptor before the method body. `PermissionEvaluator` returns a `boolean` for the given condition. If the expression denies access, the method does not proceed normally. The HTTP response depends on `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and the authentication type.

**Alternative:** `@PostAuthorize("hasPermission(returnObject, 'read')")` checks permissions against the object **after the method produces a result**. While convenient for some use cases, it has a drawback: the service may have already loaded out-of-scope data, called external APIs, logged data, or performed side effects before the policy denies access.

For sensitive data, **prefer scoping queries by user/tenant and checking before acting**. Use `PermissionEvaluator` as an additional policy layer, not as magic that prevents unauthorized data from ever being loaded into memory.

## 3. The PermissionEvaluator Interface: Two Key Overloads

In Spring Security, the interface defines two primary methods:

~~~java
package org.springframework.security.access;

import java.io.Serializable;
import org.springframework.security.core.Authentication;

public interface PermissionEvaluator {
    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission
    );
}
~~~

The snippet reproduces **the core method signatures for explanation**, not a complete copy of the framework source. Both overloads return `boolean`. Which overload the framework calls depends on the SpEL expression used.

### 3.1. Overload Accepting the Actual Object

~~~java
hasPermission(Authentication authentication,
              Object targetDomainObject,
              Object permission)
~~~

Expression example:

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document preview(Document document) {
    // ...
}
~~~

- `authentication`: verified identity from the security context.
- `targetDomainObject`: the object passed to the method, such as `Document`.
- `permission`: requested action, such as the string `"read"`.
- The evaluator can inspect the object's metadata, query a policy service, or look up permissions by resource ID.

**Trustworthiness caution:** If a REST controller receives JSON containing `owner="alice"` and constructs a client-declared `Document`, the evaluator **must not trust** that owner field as the real database owner. Use an entity loaded from a trusted source or **use only the object's ID as a key to fetch the canonical server-side record**.

A target object can be `null` or the wrong type: the policy should **fail closed** (return false), never falling back to `permitAll`. Loading a target before checking permissions still incurs cost and can introduce data-exposure risks in the service.

### 3.2. Overload Accepting ID and Target Type

~~~java
hasPermission(Authentication authentication,
              Serializable targetId,
              String targetType,
              Object permission)
~~~

Example:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long documentId) {
    // ...
}
~~~

Here:

- `#p0` refers to the first parameter, `long documentId` in Java; through SpEL it is boxed to `Long`, which implements `Serializable`.
- `'Document'` is an **application-defined resource type name**, not automatically a SQL table/entity name, Java class, or URL segment.
- `'read'` is the requested permission. You must define exactly what it means.
- The evaluator uses ID/type and Authentication to resolve metadata/rights from server sources.

**Advantage:** the service can check permissions **before the method body reads the resource**. However, the evaluator may still need to read metadata, and if the method queries again afterward while owner/status changed mid-flight, you must prevent **time-of-check-to-time-of-use (TOCTOU)**; Section 11 covers this.

### 3.3. Two Expressions Invoke Two Different Overloads

| Expression | Overload | Scenario |
| --- | --- | --- |
| `hasPermission(#document, 'read')` | Takes object | Trusted object already loaded |
| `hasPermission(returnObject, 'read')` | Takes object | Check after method returns object |
| `hasPermission(#id, 'Document', 'read')` | Takes ID + type | Only ID is available before method |
| `hasPermission(#p0, 'Document', 'write')` | Takes ID + type | Check edit permission by ID |
| `hasPermission(#id, 'Document', 'delete')` | Takes ID + type | Check delete permission if supported by policy |

Note that casing of `targetType` and `permission` is **application-defined**. If you only support `"Document"`, `"read"`, and `"write"`, requests for `"DOCUMENT"` or `"READ"` should be denied unless you have explicit normalization rules. Never automatically infer permission strings from controller names.

## 4. How PermissionEvaluator Differs from hasRole, hasAuthority, and AuthorizationManager

| Mechanism | Primary Information | Best Suited For |
| --- | --- | --- |
| `hasRole("ADMIN")` | Default `ROLE_ADMIN` authority | Functional roles / admin routes |
| `hasAuthority("document:read")` | Exact authority string | Coarse action permissions |
| `hasPermission(#id, 'Document', 'read')` | Authentication + type + ID + data policy | Permissions on a **specific object** |
| Custom `AuthorizationManager` | Authentication + manager-selected context | Complex HTTP/method policies |
| Database row-level security | Identity/tenant context at DB | Protecting datasets and queries at the source |
| Service/domain policy | Membership, owner, workflow, tenant, state | Detailed business invariants |

A user with `document:read` **does not automatically have permission to read every document** if the system requires per-object owner/tenant checks. Conversely, being a document's owner does not mean they can perform `delete`/`approve` when the workflow disallows it.

`PermissionEvaluator` is typically used **inside expression-based method authorization**. It does not automatically turn `.requestMatchers(...).hasRole(...)` into object-level checks, nor does it run if callers bypass the method-security proxy.

In multi-entry-point systems (MVC, batch, scheduler, message consumer), service methods are a logical place for policies; however, if someone accesses a repository directly from another endpoint, annotations on the original service **will not protect the new path**.

## 5. Designing Policies Around Real Resources and Trusted Tenants

Suppose we have these documents:

| ID | Tenant | Owner | State |
| --- | --- | --- | --- |
| 1 | tenant-a | alice | draft, unlocked |
| 2 | tenant-a | bob | draft, unlocked |
| 3 | tenant-b | charlie | draft, unlocked |
| 4 | tenant-a | bob | locked |

And authenticated users:

| User | Server-Side Tenant Membership | Role |
| --- | --- | --- |
| alice | tenant-a | ROLE_USER |
| bob | tenant-a | ROLE_USER |
| manager | tenant-a | ROLE_MANAGER |
| charlie | tenant-b | ROLE_USER |

Demo policy:

1. **`read`**: users may only read documents in **their own tenant**, and must be the **owner** or hold `ROLE_MANAGER` in that tenant.
2. **`write`**: only the **same-tenant owner** may change the title when the document is **unlocked**; MANAGER does not automatically get edit rights on all documents.
3. **Other permissions** such as `delete`, `approve`, `share`: **deny** because the demo does not define them.
4. Unauthenticated users, users with no tenant, non-existent IDs, invalid target types, null targets, or unsupported permission expressions: **deny**.
5. Trusted `owner`/`tenant` fields must come from the server's **store or database**, never from JSON, HTTP headers, query strings, or client-controlled cookies.

Under this policy:

~~~text
alice, read doc 1 -> ALLOW (tenant-a, owner)
alice, read doc 2 -> DENY  (not owner, not manager)
manager, read doc 2 -> ALLOW (tenant-a, ROLE_MANAGER)
manager, read doc 3 -> DENY  (tenant-b, different tenant)
charlie, read doc 3 -> ALLOW (tenant-b, owner)
alice, write doc 1 -> ALLOW (owner, unlocked)
bob, write doc 4 -> DENY  (locked)
manager, write doc 1 -> DENY (not owner)
alice, delete doc 1 -> DENY (unsupported permission)
~~~

Policy diagram:

~~~text
Verified Authentication
             |
             v
Resolve tenant from server-side membership
             |
             v
Load resource metadata from trusted store
             |
             +-- Resource missing? -> DENY
             +-- No membership? -> DENY
             +-- Different tenant? -> DENY
             |
             v
Action "read"?
             +-- owner or manager in tenant -> ALLOW
             +-- otherwise -> DENY
             |
Action "write"?
             +-- owner and unlocked -> ALLOW
             +-- otherwise -> DENY
             |
Unknown action? -> DENY
~~~

This is the example's policy, **not a universal Spring Security rule**. A real application may need approvers, project memberships, per-tenant roles, separation of duties, MFA, legal holds, ACLs, or time-bounded delegated permissions.

## 6. Normalizing Authentication, ID, Type, and Permission

### 6.1. Authentication Must Come from a Trusted Mechanism

Spring Security can produce `Authentication` from form login, HTTP Basic, sessions, a JWT resource server, or another provider. The evaluator should rely on the **framework-verified principal**.

Do not write:

~~~java
// Security flaw: X-User is set by the caller.
String user = request.getHeader("X-User");
boolean allow = document.owner().equals(user);
~~~

Request headers are not proof of authentication unless infrastructure rigorously verifies and enforces a dedicated trust boundary and identity assertion. Likewise, never use `?isOwner=true`, `?tenantId=tenant-a`, or `X-Role: ADMIN` to self-grant permissions.

### 6.2. An ID Is Not Permission

An ID `123` specifies **the resource to check**, not that the user has rights on it. Checking `existsById(id)` and allowing any authenticated user is wrong whenever data has owners/tenants.

Avoid concatenating raw input IDs into SQL; use Spring Data, prepared statements/parameters, query builders, or scoped repository methods. Compare `targetType` against an allowlist, avoiding Reflection to load arbitrary classes just because a client sent a type name.

### 6.3. Unknown Permissions Fail Closed

If the evaluator only supports `read`/`write`, a `delete` request must return false. Never use:

~~~java
default -> true; // Wrong: unknown action becomes permit!
~~~

If permissions become dynamic codes (enums, action metadata), normalize once and test every action, including empty strings, nulls, and case mismatches. Allow **only permissions explicitly recognized by the policy**.

### 6.4. Anonymous Authentication

In the servlet chain, an anonymous request may be represented by `AnonymousAuthenticationToken` whose authenticated flag depends on framework behavior, so do not rely solely on `authentication.isAuthenticated()` to conclude the caller is a real user. Use `AuthenticationTrustResolver` or explicitly exclude anonymous tokens per policy.

If a method is strictly for logged-in users, add `@PreAuthorize("isAuthenticated() and hasPermission(...)")` to make intent explicit, alongside an HTTP authentication entry point. The complete example rejects anonymous requests on `/api/**` and the evaluator also fails closed for anonymous tokens.

## 7. Wiring PermissionEvaluator into Method Security Properly

### 7.1. Enable Method Security

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // ...
}
~~~

This snippet is configuration-only; real Java imports and beans are required. `@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize` processing by default.

Do not confuse `@EnableWebSecurity` or `SecurityFilterChain` with enabling full method security. HTTP URL authorization and method authorization are two separate layers.

### 7.2. Register the Evaluator on the Expression Handler

Explicit configuration example:

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator permissionEvaluator) {

    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(permissionEvaluator);
    return handler;
}
~~~

This snippet belongs inside a `@Configuration` class and requires imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
~~~

A `static @Bean` method is a Spring Security pattern used to supply the expression handler early while initializing method-security infrastructure. If the application already defines a custom `MethodSecurityExpressionHandler` bean, **configure the evaluator on that bean** instead of creating two competing handlers.

**Never assume a `@Component PermissionEvaluator` alone causes every expression handler to pick up your custom implementation.** Test which overload is invoked and verify the result on a method proxy. Auto-configuration/APIs can vary across versions, so the example configures the handler **explicitly**.

### 7.3. Using @PreAuthorize with an ID

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

This snippet is not standalone: it needs a service bean, repository, Document, and imports. `#p0` is the first method parameter, avoiding reliance on parameter-name metadata. The expression invokes the **ID + type + permission** overload and evaluates **before the method body**.

If the evaluator returns false, the service never enters the method body. However, the evaluator may have already queried metadata; to prevent leaks and TOCTOU, the service's own query design should still be properly scoped.

### 7.4. Using @PreAuthorize with an Object

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document viewLoaded(Document document) {
    return document;
}
~~~

This form invokes the **target object** overload. Use it only when document is a **trusted server-loaded object**, or the evaluator **re-reads canonical server data by ID**. If the input is a client-submitted DTO, never check `document.owner == authentication.name` and release sensitive data.

### 7.5. Using @PostAuthorize with returnObject

~~~java
@PostAuthorize("hasPermission(returnObject, 'read')")
public Document readThenCheck(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

This snippet checks permissions **after** the method has read the result. It can be useful when the resource is unknown before execution, but the data has already entered memory; prior logs/events/side effects **are not undone**. Whenever pre-checking by ID/type is possible, prefer preauthorization and scoped queries.

**Never use `@PostAuthorize` on operations with critical side effects** hoping an exception will roll everything back; transactions/events/outboxes/remote calls may have already executed. Check permissions before writing and maintain consistent checks inside the transaction.

## 8. Enforcing Object-Level Authorization on a REST API

A typical API has:

~~~text
GET    /api/documents/{id}        -> read
PUT    /api/documents/{id}/title  -> write
DELETE /api/documents/{id}        -> delete
POST   /api/documents/{id}/share  -> share
~~~

HTTP security can require authentication across `/api/**`, while method security decides **per resource**. User A having `ROLE_USER` does not imply they can delete document B.

Given a request:

~~~http
PUT /api/documents/1/title HTTP/1.1
Content-Type: application/json
Authorization: Basic ...

{"title":"Updated version"}
~~~

A safe flow:

1. Authentication provider verifies the user.
2. CSRF filter validates the token when using CSRF-protected mechanisms (the demo keeps CSRF enabled).
3. Method-security proxy calls `hasPermission(1L, "Document", "write")`.
4. The evaluator resolves tenant/owner/locked from the **server-side store**.
5. The service updates with **permissions re-checked inside the write operation**, preventing TOCTOU.
6. Return only an appropriate DTO, avoiding exposure of sensitive metadata.

**Distinguishing 401 and 403:** unauthenticated callers typically receive 401 with HTTP Basic, whereas authenticated users lacking permission receive 403. With form login, anonymous requests may receive a 302 redirect. If a PUT lacks a CSRF token, it may receive 403 **before PermissionEvaluator ever runs**. Never treat every 403 as a `hasPermission` failure.

### 8.1. Returning 403 or 404?

When a user lacks access to a document or the ID does not exist, products can choose:
- **403 Forbidden**: clearly reflects missing permission per the API contract.
- **404 Not Found**: avoids revealing whether the resource exists to unauthorized callers.

Both carry trade-offs. This demo intentionally returns **403** for non-existent IDs during ID checks because the evaluator returns false; that is an **illustrative choice**, not a Spring Security requirement to use 403 everywhere. Even when choosing 404, avoid leaking data via timing, error bodies, counts, logs, or side channels commensurate with the threat model.

### 8.2. Never Let a Global Role Bypass Tenant Checks

A rule like "if ADMIN then always true" can let a tenant A administrator read tenant B's documents. In multi-tenant systems, check **tenant membership first**, then evaluate owner, manager, or special permissions **within the tenant**. A "cross-tenant super admin", if genuinely needed, must be a separate, strictly protected and audited policy.

## 9. Complete Java 17+ Project: Spring Boot 3.3.13, Security 6, HTTP Basic

This project builds a **real PermissionEvaluator** for documents and configures the expression handler **explicitly**. It implements both overloads, demonstrates `@PreAuthorize` by ID and by object, and includes a `@PostAuthorize` example for timing comparison.

### 9.1. Example Scope

- **Server-side data:** 4 small documents in `DocumentStore`, with tenant, owner, title, and locked flag.
- **TenantDirectory:** maps username → tenant on the server; never accepts tenant from headers.
- **Evaluator:** supports `Document/read` and `Document/write`; unknown permissions or types return false.
- **HTTP:** `GET /health` is public, `/api/**` requires authentication, all other paths are denied.
- **Service methods:** read by ID, read by trusted object, read-then-post-check, rename via PUT.
- **Tests:** anonymous 401, owner read allowed, same-tenant manager read allowed, cross-tenant blocked, non-owner write blocked, locked write blocked, missing CSRF 403, unknown action fails closed.
- **Defense in depth:** rename re-checks owner/tenant/locked inside a synchronized store. Real databases require atomic conditional UPDATEs.
- **Limitations:** no database, session replication, ACL persistence, audit trail, distributed locking, or UI; demo passwords are local only. **Do not deploy as-is to production.**

### 9.2. File Tree

~~~text
permission-evaluator-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/permissiondemo/
    │       ├── PermissionDemoApplication.java
    │       ├── SecurityConfig.java
    │       ├── TenantDirectory.java
    │       ├── DocumentStore.java
    │       ├── DocumentPermissionEvaluator.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/
        └── java/com/example/permissiondemo/
            └── PermissionEvaluatorTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>permission-evaluator-demo</artifactId>
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
~~~

**`src/main/java/com/example/permissiondemo/PermissionDemoApplication.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig: HTTP and Method Expression Handler

**`src/main/java/com/example/permissiondemo/SecurityConfig.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // Do not disable CSRF: PUT /api/** requires a token in the demo.
            .build();
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(hash)
                .roles("MANAGER")
                .build(),
            User.withUsername("charlie")
                .password(hash)
                .roles("USER")
                .build()
        );
    }
}
~~~

**Explanation:**

1. `@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize` on Spring-managed beans via method-security infrastructure.
2. The static `@Bean MethodSecurityExpressionHandler` configures **the exact evaluator instance** used in expressions, rather than just registering a Component and hoping auto-wiring picks it up.
3. The HTTP filter chain only ensures `/api/**` is authenticated. **Per-document permissions** are checked in the service.
4. HTTP Basic is used in tests to clearly distinguish 401/403; the password `demo-pass` must never be used in real environments.
5. Default Servlet CSRF remains enabled. GET tests need no token, while PUT uses `.with(csrf())`.

### 9.4. TenantDirectory: Trusted Server-Side Membership

**`src/main/java/com/example/permissiondemo/TenantDirectory.java`**

~~~java
package com.example.permissiondemo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> tenantByUsername = Map.of(
        "alice", "tenant-a",
        "bob", "tenant-a",
        "manager", "tenant-a",
        "charlie", "tenant-b"
    );

    public String tenantFor(String username) {
        return tenantByUsername.get(username);
    }
}
~~~

In production, membership usually comes from a database, identity service, or claims **verified by a token verifier**, and can include multiple tenants, groups, and per-tenant permissions. The demo uses a single tenant per user. Never replace this method with `request.getHeader("X-Tenant")` and trust the client.

### 9.5. DocumentStore: Canonical Metadata and Guarded Update

**`src/main/java/com/example/permissiondemo/DocumentStore.java`**

~~~java
package com.example.permissiondemo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Doc(
        long id,
        String tenantId,
        String owner,
        String title,
        boolean locked
    ) {
    }

    private final Map<Long, Doc> docs = new HashMap<>(Map.of(
        1L, new Doc(1L, "tenant-a", "alice", "Design", false),
        2L, new Doc(2L, "tenant-a", "bob", "Finance", false),
        3L, new Doc(3L, "tenant-b", "charlie", "Legal", false),
        4L, new Doc(4L, "tenant-a", "bob", "Frozen", true)
    ));

    public synchronized Optional<Doc> find(long id) {
        return Optional.ofNullable(docs.get(id));
    }

    public synchronized Doc renameIfOwnedAndUnlocked(
            long id,
            String authenticatedUser,
            String trustedTenant,
            String newTitle) {

        Doc current = docs.get(id);

        if (current == null
                || !Objects.equals(current.tenantId(), trustedTenant)
                || !Objects.equals(current.owner(), authenticatedUser)
                || current.locked()) {
            throw new AccessDeniedException("Document operation not allowed");
        }

        Doc updated = new Doc(
            current.id(),
            current.tenantId(),
            current.owner(),
            newTitle,
            current.locked()
        );
        docs.put(id, updated);
        return updated;
    }
}
~~~

Synchronization in the demo provides consistent reads/writes within **a single JVM**; it does not replace database transaction isolation/locking. The owner/tenant/locked conditions are checked **inside the update operation itself**, rather than relying solely on a prior preauthorization check.

The store exposes no API to modify owner/tenant/locked from requests, keeping policy data server-controlled. In production, concurrent owner/membership updates across multiple instances can occur; use DB transactions or atomic conditional UPDATEs and evaluate permissions against data at write time.

### 9.6. DocumentPermissionEvaluator: Two Overloads and Deny-by-Default

**`src/main/java/com/example/permissiondemo/DocumentPermissionEvaluator.java`**

~~~java
package com.example.permissiondemo;

import java.io.Serializable;
import java.util.Objects;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

import com.example.permissiondemo.DocumentStore.Doc;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentPermissionEvaluator(
            DocumentStore store,
            TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Doc doc)) {
            return false;
        }

        // Do not trust owner/tenant from the input object: take only the ID,
        // then re-read the canonical copy from the server-side store.
        return permitted(authentication, doc.id(), permission);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return permitted(authentication, id, permission);
    }

    private boolean permitted(
            Authentication authentication,
            long documentId,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String trustedTenant = tenants.tenantFor(authentication.getName());
        if (trustedTenant == null) {
            return false;
        }

        Doc doc = store.find(documentId).orElse(null);
        if (doc == null
                || !Objects.equals(doc.tenantId(), trustedTenant)) {
            return false;
        }

        boolean owner = authentication.getName().equals(doc.owner());
        boolean manager = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));

        if ("read".equals(permission)) {
            return owner || manager;
        }

        if ("write".equals(permission)) {
            return owner && !doc.locked();
        }

        return false; // Unknown action -> deny.
    }
}
~~~

**Detailed explanation:**

- `hasPermission(auth, Object, permission)` accepts only `Doc`; other/null objects → false.
- Even if a client constructs a fake Doc, the code **does not trust owner/tenant on the passed object**; it looks up the canonical copy by ID in DocumentStore.
- `hasPermission(auth, Serializable, targetType, permission)` accepts only `targetType = "Document"` and a Java `Long` ID; anything else → false.
- `authentication.isAuthenticated()` is not enough to identify anonymous callers; the code also excludes `AnonymousAuthenticationToken`. Production policies can use `AuthenticationTrustResolver` for special states.
- The tenant comes from `TenantDirectory`, not from client headers/queries. Cross-tenant access is denied **before** checking manager role.
- Manager is read from a trusted authority in `Authentication`, never from `X-Role` or a JSON field.
- `"read"` and `"write"` are the only supported actions. `"delete"`, `"approve"`, `null`, and any undeclared variants return false.
- To avoid granting access on store errors, a real system needs a clear error-handling strategy. **Never catch all database exceptions and return true**; on infrastructure failure, fail closed and emit safe alerts.
- This evaluator **does not globally cache decisions by ID while omitting user/tenant/permission**, as doing so can create cross-permission vulnerabilities.

**Note on targetId:** In the demo, `#p0` has type `long` and is boxed to `Long`. If a project uses `UUID` or String IDs, adjust the type checks and repository lookups accordingly; never coerce arbitrary values to Long by rounding.

### 9.7. DocumentService: Pre-Read Checks, Object Overload, and Post-Check

**`src/main/java/com/example/permissiondemo/DocumentService.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import com.example.permissiondemo.DocumentStore.Doc;

@Service
public class DocumentService {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentService(DocumentStore store, TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Doc read(long id) {
        return store.find(id).orElseThrow();
    }

    @PreAuthorize("hasPermission(#p0, 'read')")
    public Doc readServerLoaded(Doc document) {
        // Fetch the canonical copy, never return a forged client object.
        return store.find(document.id()).orElseThrow();
    }

    @PostAuthorize("hasPermission(returnObject, 'read')")
    public Doc readPostChecked(long id) {
        // Demo only: method ALREADY read before PostAuthorize evaluates.
        return store.find(id).orElseThrow();
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'write')")
    public Doc rename(long id, String newTitle) {
        if (newTitle == null
                || newTitle.isBlank()
                || newTitle.length() > 80) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String actor = authentication.getName();
        String tenant = tenants.tenantFor(actor);

        // Re-verify owner/tenant/locked inside the mutation.
        return store.renameIfOwnedAndUnlocked(
            id, actor, tenant, newTitle);
    }
}
~~~

Key points:

1. `read(id)`: ID overload checks permission **before** the method body reads the document.
2. `readServerLoaded(Doc)`: object overload checks permission. Canonical data is loaded from the store; the method does not trust fields of a client-supplied object.
3. `readPostChecked(id)`: object overload via `returnObject`, running **after** loading. Used for learning only, not as a universal guard against unauthorized reads.
4. `rename(id, title)`: ID overload checks `write` before updating, then the store **re-verifies** permissions as the mutation executes.
5. If the ID does not exist, `@PreAuthorize` denies access and the method body does not run. `orElseThrow()` is a simple defensive guard in the demo; production services need consistent exception mapping per contract.
6. `SecurityContextHolder` is used inside the service to obtain the real actor from Spring Security. For async/non-web callers, proper propagation is required; never copy context without cleanup.

### 9.8. DocumentController: HTTP Mapping and Input Data

**`src/main/java/com/example/permissiondemo/DocumentController.java`**

~~~java
package com.example.permissiondemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.example.permissiondemo.DocumentStore.Doc;

@RestController
public class DocumentController {

    private final DocumentService service;
    private final DocumentStore store;

    public DocumentController(
            DocumentService service,
            DocumentStore store) {
        this.service = service;
        this.store = store;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/documents/{id}")
    public Doc read(@PathVariable long id) {
        return service.read(id);
    }

    @GetMapping("/api/documents/{id}/object")
    public Doc readObject(@PathVariable long id) {
        // Illustrates object-overload only: data comes from the server store.
        Doc canonical = store.find(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Not found"));
        return service.readServerLoaded(canonical);
    }

    @GetMapping("/api/documents/{id}/post")
    public Doc readPost(@PathVariable long id) {
        return service.readPostChecked(id);
    }

    public record RenameRequest(String title) {
    }

    @PutMapping("/api/documents/{id}/title")
    public Doc rename(
            @PathVariable long id,
            @RequestBody RenameRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

The controller invokes `DocumentService` through a **Spring-managed dependency**. Method security annotations run on the service proxy; avoid `this.securedMethod()` self-invocation inside the same bean.

On `/object`, the controller **loads the object before the method-security check**. This endpoint exists only to show the object overload; production typically prefers the ID overload and scoped queries to avoid fetching sensitive data before authorization. If keeping the object overload, never log, serialize, or emit events from the canonical object before the policy allows it.

In the demo, `RenameRequest` contains only title; the client **cannot modify owner/tenant/locked**. If a controller binds an entity directly from the body and saves it, an attacker can attempt mass assignment; use dedicated DTOs, validation, and mapping for allowed fields only.

### 9.9. MockMvc Integration Tests: Per-Document Permissions, Tenant, Locked, CSRF

**`src/test/java/com/example/permissiondemo/PermissionEvaluatorTests.java`**

~~~java
package com.example.permissiondemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionEvaluatorTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PermissionEvaluator evaluator;

    @Test
    void publicHealthAndAnonymousProtectedRequest() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerReadsOwnDocumentButNotOthers() throws Exception {
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void managerReadsSameTenantButNotAnotherTenant() throws Exception {
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/3")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/3")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void objectOverloadAndPostAuthorizeUseSamePolicy() throws Exception {
        mvc.perform(get("/api/documents/1/object")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1/object")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1/post")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1/post")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerMayRenameUnlockedDocument() throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Revised\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revised"));
    }

    @Test
    void writeDeniedForNonOwnerManagerAndLockedDocument()
            throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("bob", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Not allowed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("manager", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Not allowed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(put("/api/documents/4/title")
                .with(httpBasic("bob", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Locked\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsIndependentOfWritePermission() throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("alice", "demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingDocumentAndUnlistedRouteAreDenied()
            throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownPermissionAndWrongTypeFailClosed() {
        var alice = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

        assertThat(evaluator.hasPermission(
            alice, 1L, "Document", "delete")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, 1L, "Unknown", "read")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, (Object) null, "read")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, 3L, "Document", "read")).isFalse();
    }
}
~~~

**Why are tests more trustworthy than checking a single line of code?**

- Tests exercise HTTP authentication/Servlet security and the **real method proxy**, catching forgotten `@EnableMethodSecurity` or unwired expression handlers.
- They test both **allow** and **deny**, especially same-tenant non-owners and cross-tenant documents.
- They verify managers cannot write even though they can read same-tenant documents.
- Locked documents reject writes even when the caller is the owner.
- They exercise both overloads: ID in `read` and object in `readObject`; `@PostAuthorize` also exercises the object overload.
- They distinguish **403 from missing permission** vs. **403 from CSRF** on PUT.
- Undeclared permissions/types all return false.
- They do not use `@WithMockUser` to bypass password verification in HTTP tests: `httpBasic(...)` sends credentials through the filter chain.
- Test data only modifies document 1's **title**, leaving tenant/owner/locked intact so other permission checks remain valid regardless of test order. With a real DB, roll back or re-seed per test for stronger isolation.

### 9.10. Running Maven and curl

Requires **JDK 17+, Maven**, and initial dependency download access:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Expected result:** Spring context starts, tests pass, and Maven prints `BUILD SUCCESS` when files and environment are right. These instructions describe how to run it yourself; **Maven was not executed here**.

In another terminal:

~~~bash
curl -i http://localhost:8080/health
# Expected 200 {"status":"ok"}

curl -i http://localhost:8080/api/documents/1
# Expected 401 with HTTP Basic challenge

curl -i -u alice:demo-pass http://localhost:8080/api/documents/1
# Expected 200, JSON document 1 owned by alice

curl -i -u alice:demo-pass http://localhost:8080/api/documents/2
# Expected 403

curl -i -u manager:demo-pass http://localhost:8080/api/documents/2
# Expected 200 because manager is in the same tenant

curl -i -u manager:demo-pass http://localhost:8080/api/documents/3
# Expected 403 because different tenant

curl -i -u bob:demo-pass http://localhost:8080/api/documents/4
# Expected 200 for READ, though WRITE is locked

curl -i -u alice:demo-pass http://localhost:8080/api/documents/999
# Expected 403 per the demo's fail-closed policy
~~~

Never test PUT and conclude 403 came from PermissionEvaluator unless the request included a valid CSRF token. MockMvc provides `with(csrf())` to control this precisely. To call PUT via curl with CSRF enabled, you must obtain a token from the `CsrfTokenRepository` and cookie/session context configured by the app; this demo does not proactively expose a CSRF token endpoint for curl clients.

**Real-world safety:** HTTP Basic uses Base64, **which does not encrypt credentials**. Use HTTP only on localhost for learning, and never expose demo users/passwords to the Internet. In real environments, use HTTPS, securely managed credentials, validation, rate limiting, and auditing.

## 10. Defining Permissions and Standardizing Expressions

### 10.1. Do Not Scatter Permission Strings

If code mixes `'read'`, `'READ'`, and `'view'` for the same action without a shared standard, policies easily break or become overly permissive. In multi-module systems, consider defining permission enums/constants and mapping consistently:

~~~java
public enum DocumentPermission {
    READ, WRITE, SHARE, DELETE
}
~~~

This is a standalone snippet (put it in `DocumentPermission.java` if adding to a project), not needed for the string-literal demo. An evaluator supporting enums must validate the permission type and explicitly handle unsupported actions. **Never** cast blindly or default to true when new enum values are added.

### 10.2. Roles and Permissions Are Not Synonyms

`hasRole("MANAGER")` checks `ROLE_MANAGER` by default; `read` permission on document 123 is a **resource-contextual decision**. A manager allowed to view all documents in a tenant may still not be allowed to edit them, view across tenants, or export PII. Capture these distinctions in tests and policy documentation.

### 10.3. Named-Argument SpEL

If you use:

~~~java
@PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
~~~

then `documentId` must be resolvable by Spring Security (for example via the Java compiler `-parameters` metadata or related configuration). Using `#p0` avoids relying on parameter names in the example, though it makes expressions less descriptive. In production code, you can use descriptive parameter names when builds guarantee metadata, backed by integration tests.

### 10.4. Null Targets and ID Formats

Target objects can be null; IDs can have mismatched types (Long vs. UUID vs. String). Define a clear type contract. For documents with UUIDs, the evaluator must use `UUID` as the ID and repositories must guard against enumeration/guessing if resources are sensitive; **UUIDs do not replace authorization**. If an ID does not exist, default-deny or return 404 per the agreed API policy.

## 11. Performance, Databases, and TOCTOU

### 11.1. N+1 Authorization Queries

If an endpoint returns 1,000 documents and calls `hasPermission(document, 'read')` for each one, the evaluator may query metadata/membership 1,000 times. The result is **N+1 queries**, high latency, and DB pool exhaustion.

Solutions:

- For lists/searches, use **repository queries already scoped** by tenant/owner/ACL.
- Batch-load permission metadata when genuinely necessary.
- Use projections/DTOs with only the fields needed for checking.
- Consider EXISTS queries or joins with membership/ACLs.
- Check individual resource IDs at the method level only when an endpoint handles **one** document or a small bounded batch.

### 11.2. Scoping Queries Before Pagination

An illustrative query:

~~~sql
SELECT d.id, d.tenant_id, d.owner_id, d.title, d.locked
FROM documents d
WHERE d.tenant_id = :trustedTenantId
  AND (d.owner_id = :principalId OR :hasTenantManagerRole = TRUE)
  AND d.deleted = FALSE
ORDER BY d.id DESC
LIMIT :limit OFFSET :offset;
~~~

Named parameters must be safely bound from the **server-validated principal and tenant membership**, never concatenated from client SQL. A trusted boolean manager condition must be computed from tenant-scoped authorities; never pass `?isManager=true` directly from the request into the query.

**Important:** apply authorization filters in SQL **before** LIMIT/OFFSET and counting. Never fetch 100,000 records and filter with `@PostFilter` or call hasPermission per record just to return 20 records—doing so wastes DB/network/JVM resources and corrupts pagination/total counts.

### 11.3. Optimizing for Object IDs

When checking a single ID, a query can run:

~~~sql
SELECT d.id, d.tenant_id, d.owner_id, d.locked
FROM documents d
WHERE d.id = :documentId;
~~~

Then the evaluator decides based on owner/tenant/status. However, if a mutation follows, **do not separate "permission check" and "update" too far** transactionally; permissions can change in between. The UPDATE statement should embed protective conditions whenever possible:

~~~sql
UPDATE documents
SET title = :title
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :principalId
  AND locked = FALSE;
~~~

Check `affectedRows == 1` to confirm the operation succeeded under the exact conditions. For complex policies needing ACL/permission joins, use transaction isolation/locks or atomic service authorization. **Pre-method evaluator checks alone do not eliminate TOCTOU**.

### 11.4. Caching Authorization Decisions

Arbitrarily caching by `documentId` is a severe bug: if alice can read doc 1, caching true and then serving bob for doc 1 grants bob access if the key is only ID. If you genuinely cache decisions, keys must include **principal, tenant, resource ID/version, action, and policy version**, with proper expiry/revocation.

In many cases invalidation complexity and risk outweigh caching benefits; an indexed query by user/tenant/resource is easier to get right. When permissions change, never keep stale decisions indefinitely.

### 11.5. Side Effects with @PostAuthorize

`@PostAuthorize` runs after the method body, so if the method writes to the DB, sends a message, or calls a remote API, throwing AccessDeniedException **is not guaranteed to undo all side effects**. For write methods, prefer pre-authorization and re-checking inside the mutation transaction.

### 11.6. Permissions Changing While a Request Is Running

Owner, tenant membership, lock status, and ACLs can change. Decide:
- Must permissions hold at request start or at commit time?
- Does the transaction require specific consistency/locking?
- If permissions are revoked while a session/token is alive, can policies go stale?
- Is auditing required for "who was allowed at what time"?

The in-memory example intentionally re-checks inside a synchronized mutation, but that only works within one JVM; multi-replica production deployments require appropriate DB/distributed mechanisms.

## 12. Error Messages, Privacy, and Auditing

### 12.1. Do Not Leak Data When Denying

If bob calls `GET /api/documents/1`, a 403/404 response must not contain owner email, title, or document contents. Never use an exception message like "Alice's Design document does not belong to you" if bob has no right to know the document exists. Server-side logging must enforce access control, retention, and redaction.

### 12.2. Useful Auditing Without Logging Secrets

On denial, you can log:
- Timestamp, verified caller ID, tenant ID.
- Resource type/ID handled according to privacy policies.
- Action `read/write`, policy version, and deny/allow decision.
- Request correlation ID.

Avoid logging Authorization headers, Bearer tokens, session cookies, passwords, or full bodies containing PII. Consider logging denials, aggregated metrics, and sampling based on volume; avoid log flooding/DoS.

### 12.3. When the Evaluator/Service Cannot Reach the Database

Infrastructure errors must never turn into `permitAll`. Nor should you catch every exception and always return 403 if that masks critical outages. Design a clear fault policy: fail closed on data access, return appropriate 5xx codes when a service fails, log safely, and alert; never return sensitive data as a fallback.

### 12.4. Do Not Offload Policy Enforcement to the Frontend

Hiding an "Edit" button in the UI by role improves UX, **not enforcement**. Clients can call HTTP endpoints directly. Resource permissions must be enforced on the server; API Gateway/HTTP rules and service/DB policies must align.

## 13. Common Mistakes When Implementing PermissionEvaluator

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using only `hasRole('USER')` for `/documents/{id}` | User A can access User B's document | Object-level permission check |
| Creating a PermissionEvaluator bean without configuring expression handler | `hasPermission` may not call the intended evaluator | Wire handler explicitly and test |
| Forgetting `@EnableMethodSecurity` | @PreAuthorize/@PostAuthorize are ignored | Enable and test via Spring proxy |
| Calling annotated method via `this.read(...)` in same bean | Self-invocation can bypass proxy | Separate bean, call via injected service |
| Reading `owner` from JSON body to verify ownership | Client spoofs owner | Read canonical resource server-side |
| Reading tenant from unverified `X-Tenant` header | Cross-tenant leak | Trusted tenant membership |
| Letting manager bypass before checking tenant | Tenant A manager views Tenant B | Check tenant before role |
| `default -> true` for unknown permissions | New actions get implicitly granted | Deny unknown permissions |
| Not handling null target / unknown type | NPE or accidental permit | Validate and fail closed |
| Unscoped ID lookup without type check | Wrong table/resource, type confusion risk | Allowlist targetType |
| Returning 403 before CSRF is controlled in tests | Unclear what caused 403 | Test both with and without `csrf()` |
| Checking permissions only before UPDATE, not at write time | TOCTOU if data changes | Atomic conditional UPDATE / transaction |
| Calling evaluator per record in huge lists | N+1 queries, DB overload | Scope query in DB + pagination |
| Caching results by documentId alone | Alice's access served to Bob | Proper key/expiry/version, or skip cache |
| Using @PostAuthorize on writes expecting rollback | Side effects already occurred | Preauthorization + policy inside mutation |
| Testing only admin happy paths, skipping cross-tenant/locked | Privilege escalation slips through | Negative test matrix |
| Swallowing DB errors and allowing access | Fail open | Fail closed, proper error handling and alerts |
| Confusing object overload with ID overload | Method expression hits wrong policy | Test both signatures |

## 14. Production Test Matrix

Using the demo project's policy:

| Caller | read #1 (alice/a) | read #2 (bob/a) | read #3 (charlie/b) | write #1 | write #4 locked |
| --- | --- | --- | --- | --- | --- |
| alice / tenant-a | 200 | 403 | 403 | allowed if CSRF valid | 403 |
| bob / tenant-a | 403 | 200 | 403 | 403 | 403 |
| manager / tenant-a | 200 | 200 | 403 | 403 | 403 |
| charlie / tenant-b | 403 | 403 | 200 | 403 | 403 |
| Anonymous | 401 | 401 | 401 | 401 or CSRF 403 | 401 or CSRF 403 |

For **GET** in the demo, anonymous requests to `/api/**` receive 401 under Basic auth. For **PUT**, CSRF may run before HTTP authentication/authorization, so an anonymous request without CSRF can receive 403 instead of 401. The table states this explicitly to prevent over-assuming in tests.

Beyond the rows above, test:
- Non-existent IDs.
- Null target object / wrong type.
- Wrong-case or undeclared permissions.
- User with the right role but **wrong tenant**.
- Locked, deleted, archived, or pending-approval resources.
- Membership revoked / owner changed between request start and commit.
- Multiple identities/roles within one tenant.
- Bad/missing JWT/session and session timeout.
- Non-controller entry points (schedulers, messaging).
- Races when concurrent requests update the same object.
- Pagination, batch list/export, and authorization over large datasets.
- Logs and error bodies leaking no unauthorized data.
- Method-security proxy running on real beans without self-invocation bypass.

## 15. Advanced Topics

### 15.1. Do You Need the ACL Framework?

Spring Security also provides ACL (access control list) components for per-object permissions in some stacks/versions. `PermissionEvaluator` is an interface for you to customize; you are **not required to install Spring Security ACL** to use `hasPermission`. Systems needing per-user/per-team document sharing can use an ACL/permission table, provided migrations, indexes, revocation, tenant scoping, and permission semantics are managed properly.

### 15.2. Does RoleHierarchy Replace PermissionEvaluator?

No. `RoleHierarchy` defines **which roles include which roles**, e.g., ADMIN > MANAGER > USER at configured enforcement points. `PermissionEvaluator` decides **whether the current user can perform action X on object Y**. They can work together—an evaluator can inspect expanded authorities or call a separate policy service—but must be configured consistently without assuming ADMIN holds every permission across all tenants.

### 15.3. Do JWT Claims Need Mapping to GrantedAuthorities?

If an API uses JWTs, the resource server must verify tokens and map scopes/roles into trusted authorities. The evaluator can also consult tenant memberships from the DB. Never accept unverified JWT payloads or role fields in self-declared HTTP headers. JWTs can carry stale permissions after a role is revoked; use token expiry, revocation, or request-time policy lookups as needed.

### 15.4. Should Permission Objects Be Strings or Enums?

The interface accepts `Object permission`, so you can use strings or enums per policy. In SpEL, `'read'` is a String. If using enums, expressions must reference the enum constant properly and check types. Never implicitly convert arbitrary objects to strings and risk permitting the wrong action; test strictness.

### 15.5. When to Choose a Custom AuthorizationManager Instead of PermissionEvaluator?

When policies depend on full request context (HTTP method, route, request attributes), a custom `AuthorizationManager<RequestAuthorizationContext>` fits well. When policies bind to method arguments or returnObject via SpEL, `PermissionEvaluator` is a natural choice.

A plain Java policy service can be called from both mechanisms to avoid duplicating logic. Keep owner/tenant/state decisions inside an independently tested domain policy rather than duplicating them across controllers, evaluators, gateways, and repositories.

### 15.6. Can You Filter Large Sets Element-by-Element with hasPermission?

`@PostFilter("hasPermission(filterObject, 'read')")` can filter a small collection after a method returns. However, over tens of thousands or millions of records, doing so causes N+1 permission lookups and inaccurate pages/counts. **Push authorization conditions into queries before pagination**, or use an explicitly designed bulk permission lookup instead of fetching the whole table and post-filtering.

## 16. Implementation Checklist

1. Define `read/write/delete/approve` actions and clear semantics per object type.
2. Separate global roles/authorities from resource-level permissions by owner/tenant/workflow.
3. Verify Authentication via trusted providers/token verifiers; never trust client-declared headers.
4. Configure `@EnableMethodSecurity` and an expression handler that actually uses your custom PermissionEvaluator.
5. Distinguish object vs. ID/type overloads; test exact signatures, nulls, and unknown types/permissions.
6. Rely solely on canonical server-side resource and tenant membership data.
7. Use `@PreAuthorize`/scoped queries to avoid reading unauthorized data whenever possible.
8. Never rely on `@PostAuthorize` to undo side effects.
9. For updates/deletes, verify permission conditions within the transaction or atomic SQL.
10. Test CSRF separately for cookie-based requests; distinguish 401, 403, and 404 by mechanism.
11. Test owner, non-owner, same-tenant manager, cross-tenant manager, locked records, and missing IDs.
12. Check for self-invocation, final/private methods, and non-MVC entry points.
13. Optimize queries by tenant/owner/ACL to avoid N+1 issues on large lists.
14. Never cache permission decisions without principal/tenant/action and policy/resource version.
15. Audit carefully without exposing tokens, session IDs, passwords, or unauthorized resource metadata.
16. Have invalidation/re-authentication strategies when permissions change and test across multiple instances.

## 17. Self-Check Questions

**Question 1. What is `PermissionEvaluator` used for?**

Answer: It is an extension point that evaluates an Authentication's permission on a specific object or ID/type for an action, typically via SpEL `hasPermission` in method security.

**Question 2. How do the two overloads differ?**

Answer: One overload takes the target object, while the other takes `Serializable targetId` + `String targetType`. Passing two or three arguments to `hasPermission` (excluding internal Authentication) selects the matching overload.

**Question 3. Which overload does `hasPermission(#p0, 'Document', 'read')` invoke?**

Answer: The ID/type/action overload. If the first parameter is a primitive long, the evaluator usually receives a boxed Long.

**Question 4. Why shouldn't you trust an owner field in client JSON?**

Answer: The client can modify the field, causing the policy to grant wrong permissions. Always read canonical owner/tenant data from a DB or trusted store.

**Question 5. Can a tenant A manager read every document in tenant B?**

Answer: Not under the demo policy. Tenant membership is checked before roles; the manager role is tenant-scoped.

**Question 6. When the evaluator returns false before a method, does the method body execute?**

Answer: No, for calls guarded by `@PreAuthorize` through the method-security proxy. If self-invocation bypasses the proxy, the annotation may not run.

**Question 7. Does `@PostAuthorize` prevent the DB from reading data before the check?**

Answer: No. The method body already executed; only afterward is the expression evaluated against `returnObject`.

**Question 8. Is declaring `@Component PermissionEvaluator` alone sufficient?**

Answer: Do not assume so. Verify the expression handler actually uses that evaluator and method security is enabled; the demo wires it explicitly via a static `@Bean MethodSecurityExpressionHandler`.

**Question 9. Why must unknown permissions deny by default?**

Answer: If a new action is implicitly permitted, it can create an undesigned, unreviewed privilege escalation.

**Question 10. Why doesn't an HTTP role check replace object authorization?**

Answer: Roles confirm general capabilities, not the owner/tenant/locked state of a specific resource ID.

**Question 11. Why can missing CSRF on PUT return 403 even if the evaluator permits write?**

Answer: The CSRF filter can block the request before method security runs. They are two independent protection layers.

**Question 12. Why can PermissionEvaluator cause N+1 queries?**

Answer: Calling the evaluator per element in a list can trigger a separate metadata/ACL query each time; use scoped queries, batch lookups, and proper pagination.

**Question 13. What is TOCTOU in object authorization?**

Answer: Permissions are checked at an earlier time, while owner/tenant/locked can change before the write occurs. Use transactions, locks, or conditional UPDATEs that re-check conditions during the mutation.

**Question 14. Should you return 403 or 404 for non-existent IDs?**

Answer: It depends on your API contract and anti-disclosure policy; the demo returns 403 via a fail-closed evaluator, while production may consistently return 404.

**Question 15. Does PermissionEvaluator automatically revoke JWTs/sessions when roles change?**

Answer: No. You need token/session expiry, revocation, policy lookups, or mechanisms ensuring updated permissions take effect.

**Question 16. If the frontend hides the Delete button, is the backend safe?**

Answer: No. Clients can call the API directly. The server must still evaluate delete permission on the specific resource and reject undeclared permissions.

**Question 17. To authorize by tenant and owner across millions of records, should you postfilter every record with hasPermission?**

Answer: No. Use scoped queries/database row-level restrictions, counts, and pagination over authorized records; method permission checks serve as an additional layer.

**Remember:** **`PermissionEvaluator` turns `hasPermission` into per-resource action checks. Its two overloads accept an object or ID/type; both must rely on verified Authentication and trusted resource/tenant data. Wire it properly to the method-security handler, deny unknown inputs by default, re-check inside mutations, and use scoped queries for large datasets.**