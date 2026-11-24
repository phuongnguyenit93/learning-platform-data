# Runtime Privilege Changes and Refresh Policies for Authenticated Identities in Spring Security Servlet

## 1. The Problem: Privileges Changed, Yet Active Login Sessions Still Use Old Privileges

Imagine a project management application using **Spring Security Servlet**. At 09:00, account **learner** logs in with authority **ROLE_USER**. The server verifies the password, creates an **Authentication** object, and stores it in the **SecurityContext** tied to the **HttpSession**. At 09:05, an administrator grants **learner** **ROLE_ADMIN** in the data store. Without logging out, the user reloads **/admin**.

Is the 09:06 request guaranteed to have the new ROLE_ADMIN? **No.** When Spring Security retrieves the saved Authentication from the session, that object can still hold the **ROLE_USER snapshot** captured at login time. Updating the database, `UserDetailsManager`, or role table **does not automatically modify every already-issued Authentication**. The reverse case is even more sensitive: revoking `ROLE_ADMIN` in the database while an old session retains `ROLE_ADMIN` and keeps passing rules that inspect only stale authorities.

This is the **freshness of authenticated identity and authorities** problem, distinct from initial password verification.

This lesson helps you:

1. Distinguish **source privilege state** (database/identity service) from an **Authentication snapshot** inside `SecurityContext`/session or token claims.
2. Understand when Spring Security re-reads **UserDetailsService** vs. when it reuses a stored `Authentication`.
3. Evaluate three policies: **keep snapshot until session end**, **refresh privileges**, and **invalidate session and force re-login**.
4. Implement a **rolesVersion** policy: increment a version on privilege changes, check it on the next request, and invalidate stale sessions before sensitive resources execute.
5. Understand limitations of **SessionRegistry, Spring Session, JWTs, OAuth2 Resource Server, bearer tokens, multi-node**, and in-flight requests.
6. Write and test a **Java 17+, Spring Boot 3.3.13, Spring Security 6** application using **form login + HttpSession + BCrypt + SecurityFilterChain**, with **MockMvc** proving stale sessions are revoked when privileges change.
7. Design tests for **grant, revoke, disabled account, stale session, fail-closed, cache TTL, race conditions, object-level permissions**, and migrating between policies.

**Focus:** Authorization models in **Spring Security Servlet**. Do not treat this as a complete guide to building an IAM/SSO system. Production examples require adaptation for your database, cluster, token issuer, and real threat model.

## 2. Authentication Is a Point-in-Time Verification Result

In Spring Security, **Authentication** typically represents:

- **principal**: verified identity (e.g., `UserDetails` or a JWT subject).
- **authorities**: verified `GrantedAuthority`/roles used for authorization.
- **credentials**: authentication secret, normally erased/hidden after successful authentication.
- **authenticated**: state confirmed by the provider.
- **details**: request metadata when applicable.

Related components:

| Component | Responsibility | Do privileges auto-update when the DB changes? |
| --- | --- | --- |
| **UserDetailsService** | Loads user and authorities from the data store | Only when invoked again |
| **AuthenticationProvider** | Verifies credentials and builds Authentication | During that authentication event |
| **AuthenticationManager** | Coordinates AuthenticationProviders | Does not hunt down existing sessions |
| **SecurityContextHolder** | Holds SecurityContext for the current thread/request | Does not re-read the database automatically |
| **SecurityContextRepository** | Loads/saves SecurityContext, e.g., from HttpSession | Stores a snapshot; does not auto-refresh |
| **AuthorizationFilter** | Evaluates request against Authentication and AuthorizationManager | Depends on provided authorities/policies |
| **Method security** | Enforces checks on method calls | Also needs proper policy and authority sources |
| **JWT decoder/resource server** | Verifies tokens and builds Authentication from claims | Signed claims do not mutate on their own |
| **SessionRegistry/Spring Session** | Tracks/looks up sessions when configured | Can aid revocation, does not sync privileges automatically |

A rule:

~~~java
.requestMatchers("/admin").hasRole("ADMIN")
~~~

only compares the active `Authentication` against **ROLE_ADMIN** under the default convention. That rule **does not query the latest roles table automatically**. This is the core point whenever roles change at runtime.

### SecurityContextHolder and HttpSession Differ

**SecurityContextHolder** lets request-handling code access the current security context. In session-based Servlet applications, a **SecurityContextRepository** can load `Authentication` from **HttpSession** on subsequent requests; not every request re-authenticates from scratch.

In Spring Security 6, when custom code creates an `Authentication`, understand **explicit save**: putting an `Authentication` into `SecurityContextHolder` **is not enough** to persist it for future requests. Standard login filters handle saving via their lifecycle; custom code must pick the repository and save at the right time. This demo uses framework `formLogin` to avoid reimplementing that entire lifecycle.

### Snapshots Are Not Automatically Bugs

Snapshots avoid querying the database for roles on every single request, reducing load and keeping latency predictable. However, they create a **staleness window**. Choose a policy aligned with security requirements: what maximum revocation delay is acceptable, whether forced re-login is acceptable, and which critical actions must check the latest policy right at execution time.

## 3. Two Scenarios to Distinguish: Granting vs. Revoking Privileges

### 3.1. Granting Additional Privileges (Grant)

~~~text
09:00  learner logs in, Authentication has ROLE_USER
09:05  admin grants ROLE_ADMIN in the data source
09:06  learner opens /admin with the old session
~~~

With an unrefreshed session snapshot, **/admin can still return 403** until the user logs in again, the session is refreshed, or authorization consults a live policy. This is usually a UX issue: a user received a new privilege yet cannot use it yet.

However, **you do not always want to auto-elevate an old, long-lived session**. Sensitive operations may require password re-authentication, MFA/step-up, or explicit confirmation before using the newly granted privilege. Automatically refreshing authorities is not always the safest policy.

### 3.2. Revoking Privileges (Revoke)

~~~text
09:00  admin logs in, Authentication has ROLE_ADMIN
09:05  security team revokes ROLE_ADMIN
09:06  old session still holds Authentication containing ROLE_ADMIN
09:07  request POST /admin/export-data
~~~

If authorization relies solely on the stale `Authentication`, the request can succeed even though the database revoked the privilege. This poses a higher security risk than delayed grants.

**Especially:** account status changes such as **disabled/locked/deleted**, password resets, suspected session compromise, or tenant changes may also require invalidating existing Authentications, not just role edits.

### 3.3. What About Immediately Affecting an In-Flight Request?

Suppose a request passed the `ROLE_ADMIN` check at 09:04:59 and runs an export taking 30 seconds. An admin revokes the privilege at 09:05:00. A filter checking `rolesVersion` **at the start of the request** cannot retroactively undo the check that already passed. If business rules demand immediate consistency, re-check privileges at **the critical operation point**, or design job cancellation/suspension and appropriate transaction/authorization boundaries.

**"Effective on the next request"** differs from **"halt all currently executing tasks immediately"**. The guarantee level must be clearly defined.

## 4. Source Privileges, Session Privileges, and JWT Privileges

Three common sources:

~~~text
Database / IAM:
  learner -> [ROLE_USER, ROLE_ADMIN], rolesVersion=12
                      |
                authentication
                      |
          +-----------+------------+
          |                        |
   HttpSession snapshot       JWT claims snapshot
   roles=[ROLE_USER]          roles=[ROLE_USER]
   version=11                 iat=... / exp=...
          |                        |
      new request             new bearer token?
          |                        |
   context loaded from session  parser builds Authentication
          |                        |
   may still be version 11    old token still has old claims
~~~

**HttpSession:** at login, an `Authentication` with authorities is stored in the context. Changing roles in the DB does not automatically update old contexts. You can invalidate or perform controlled refreshes.

**Self-contained JWT claims:** a valid signature proves the token was issued by a trusted party and has not been tampered with under verification criteria; **it does not prove role claims still match the latest policy**. While the token is unexpired and the resource server trusts those claims, old roles keep working. You can shrink the window with short-lived tokens, revocation/introspection, version checks on the resource server, or keeping volatile privileges out of long-lived tokens.

**Opaque token + introspection:** a resource server can ask the authorization server whether a token is still active and what scopes/roles it holds, though introspection results may also be cached; cache TTL becomes a freshness factor. Token revocation must also be enforced properly.

**HTTP Basic on every request:** if the client sends username/password on each request and the provider loads the user from the current store, authorities can reflect changes on the next authentication. Still, user caches or Authentication caches can delay updates, and you cannot assume every HTTP Basic client stops sending cached credentials after "logout".

**SSO:** the application session and the Identity Provider session are separate. Invalidating the app's `HttpSession` does not automatically trigger global SSO logout or revoke tokens at the IdP.

## 5. Three Common Policies When Privileges Change

| Policy | How it works | Pros | Risks / costs |
| --- | --- | --- | --- |
| **A — Snapshot until session ends** | Session/JWT retains authorities from login | Fewer lookups, simple | Long revoke/grant delay |
| **B — Refresh Authentication** | Issues new Authentication from verified privilege source | Users get updates without logging out | Complexity with sessions, races, step-up, principal integrity |
| **C — Invalidate and force re-authentication** | When version/privilege change is detected, clear session/context and require login | Easy to reason about, reduces stale-role window | UX interruption; must coordinate with frontend/SSO |
| **D — Dynamic authorization against privilege source** | Every sensitive access queries a policy/permission service | Revocation as fast as backend allows | Higher latency, cache/availability concerns; must apply consistently everywhere |
| **E — Centralized token/session revocation** | Actively invalidates affected credentials on change events | Centralized multi-node control | Needs registry/index and event/revocation infrastructure |

No single solution fits every system. You can combine them: **C/E** for revoking sensitive roles, **D** for guarding critical actions, **A** for low-sensitivity permissions, and **B** only when UX and re-authentication rules align.

### Choosing Based on Risk

- **High-impact permissions** (user administration, money transfers, sensitive data exports): never rely solely on long-lived snapshots; check fresh privileges at execution time and support revocation.
- **Granting higher privileges:** consider requiring re-authentication/MFA instead of silently elevating an existing session.
- **Revoking access:** prefer a policy with a provable upper bound on how long old sessions remain valid.
- **Low-sensitivity privileges:** finite TTLs and updating at next login can be acceptable if documented clearly.
- **Multi-node/multi-region:** store versions/registries in a shared store and guarantee event delivery and cache invalidation rather than using an in-JVM Map.

## 6. Why Updating UserDetailsManager Leaves Sessions "Stale"

Consider an in-memory example:

~~~java
// Illustrative fragment: users is an injected InMemoryUserDetailsManager.
UserDetails old = users.loadUserByUsername("learner");
UserDetails updated = User.withUserDetails(old)
    .roles("ADMIN")
    .build();
users.updateUser(updated);
~~~

Calling **updateUser** updates the `UserDetails` inside the JVM's user store, yet it **does not walk every active HttpSession to rewrite stored Authentications**. `UserDetailsService` is not the sole source Spring Security consults on incoming requests.

Conversely, when using form login/session:

~~~text
POST /login -> UserDetailsService -> Authentication(ROLE_USER)
          -> SecurityContextRepository saves Authentication to session

GET /admin -> SecurityContextRepository loads Authentication(ROLE_USER)
           -> hasRole("ADMIN") = false

After users.updateUser(... ROLE_ADMIN ...):
GET /admin -> May still load old Authentication(ROLE_USER)
~~~

Do not patch it by calling **SecurityContextHolder.getContext().getAuthentication().getAuthorities().add(...)**. The collection may be immutable, the principal/Authentication may be referenced elsewhere, and mutating an object stored in session makes thread safety and synchronization fragile. To refresh intentionally, **construct a new verified Authentication, update the context cleanly, and save it to the repository**, or simpler: **invalidate and require re-login**.

### You Cannot "Force All Sessions" via SecurityContextHolder

`SecurityContextHolder` represents only the current execution context. It is not a database or registry of everyone's sessions. Calling `SecurityContextHolder.clearContext()` when an admin updates a role **clears only the current request's context** (usually the admin's), not the learner's browser session.

To act on another user's sessions, you need a mechanism that tracks **which sessions belong to that user**, such as `SessionRegistry`, Spring Session with an index, a per-request version check, or a revocation service.

## 7. The rolesVersion Model: One Way to Check Freshness

A common design stores a **privilege version** in the data source and a **version bound to the session at authentication time**.

~~~text
UserRoleRecord
  username = "learner"
  authorities = [ROLE_USER]
  rolesVersion = 7

learner's HttpSession
  SecurityContext = Authentication(ROLE_USER)
  AUTH_ROLES_VERSION = 7
~~~

When an admin changes roles, update consistently per policy:

~~~text
UserRoleRecord
  username = "learner"
  authorities = [ROLE_ADMIN]
  rolesVersion = 8

Old HttpSession:
  AUTH_ROLES_VERSION = 7
~~~

Next request:

~~~text
GET /admin with old session
   |
   v
Load Authentication from SecurityContextRepository
   |
   v
Check version 7 != current version 8
   |
   +-- invalidate session
   +-- clear SecurityContext
   +-- HTTP 401 / require re-login
   |
   v
Cannot reach admin endpoint with stale ROLE_USER/ROLE_ADMIN
~~~

Upon logging in again, the provider loads the updated `UserDetails`; the new session gets **rolesVersion=8** and an `Authentication` with the updated roles. This is policy **C — invalidate and re-authenticate**, not silent authority refreshing.

### Why Is Comparing a Version Better Than Comparing Full Role Lists?

- Comparing a single version number is cheaper and cleaner than diffing complex authority sets.
- You can bump the version on role changes, tenant membership changes, direct permission grants, account status changes, or relevant policy updates.
- Versions can be stored alongside user/tenant records in the database and paired with short-lived, controlled caching.
- In multi-node deployments, a shared version lets any node detect stale credentials on the next request.

**Requirement:** versions must **increment reliably** and be read from a trusted data source. If stored only in node A's RAM, node B never sees changes; that is a limitation of our demo and cannot provide cluster-wide revocation.

### Where Should the Version Be Stored?

An **HttpSession attribute** is a simple choice for the form-login demo. Metadata can also live in a custom principal or a server-side session record. Never read a version from a client-supplied request header and trust it as fresh state. With JWTs, a version claim can sit inside the token, yet must still be compared against the current version in a trusted store to provide revocation.

## 8. Demo Design: Forcing Re-Login When Privileges Change

The example uses:

- **Spring Boot 3.3.13 / Java 17+ / Maven**.
- **Spring Security Servlet**, default form login, session cookie, and default CSRF.
- **InMemoryUserDetailsManager** seeding `learner` with `ROLE_USER` and a BCrypt password.
- A **RoleDirectory** for tests/admin actions simulating role changes and incrementing `rolesVersion`.
- **RoleVersionFilter** registered in `SecurityFilterChain`, checking the version before **AuthorizationFilter**.
- If the version mismatches or is missing on an authenticated session, the filter invalidates the session, clears context, and returns **401** so the client re-authenticates.
- Endpoints `GET /public`, `GET /me`, `GET /admin`; role changes are invoked only from **test code**, not a public REST API.

This policy intentionally errs on the side of safety: **never elevate or downgrade privileges inside a live Authentication**. Any session issued before a role update must re-authenticate on its next authenticated request, avoiding ambiguity around privilege elevation.

### Why Not Expose a Public POST /grant-role Endpoint?

An API where callers pass a username and `ROLE_ADMIN` to `updateUser` without governance, authorization, and auditing is a severe vulnerability. To stay focused on freshness, role updates happen by **calling RoleDirectory directly in integration tests**, standing in for an authorized admin action or internal IAM job. Production requires a controlled workflow with logging and dedicated permissions.

### Limitations to Remember

The demo stores versions in an **in-JVM ConcurrentHashMap** with no cluster sync and no durable transactions. Checking version **at the start of a request** does not cancel requests already past authorization or prevent every race between checking and reading data. Production must choose an appropriate source-of-truth DB, revocation events, atomicity, and fail-closed policies.

## 9. Complete Java 17+ Project

### 9.1. Directory Tree

~~~text
role-freshness-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/rolefreshness/
    │   ├── RoleFreshnessApplication.java
    │   ├── SecurityConfig.java
    │   ├── RoleDirectory.java
    │   ├── RoleVersionFilter.java
    │   └── DemoController.java
    └── test/java/com/example/rolefreshness/
        └── RoleFreshnessTest.java
~~~

### 9.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>role-freshness-demo</artifactId>
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

This is a complete Maven file requiring no additional XML snippets. Using the Spring Boot parent keeps Spring Framework and Spring Security versions aligned. When upgrading major versions, filter/security APIs can change: consult the migration guide and re-run tests.

### 9.3. RoleFreshnessApplication.java

~~~java
package com.example.rolefreshness;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleFreshnessApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleFreshnessApplication.class, args);
    }
}
~~~

### 9.4. RoleDirectory.java — Updating Users and Versions

~~~java
package com.example.rolefreshness;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.stereotype.Service;

@Service
public class RoleDirectory {

    private final InMemoryUserDetailsManager users;
    private final Map<String, Long> versions = new ConcurrentHashMap<>();

    public RoleDirectory(InMemoryUserDetailsManager users) {
        this.users = users;
    }

    // Illustrates an in-JVM version store only, not a multi-node source.
    public synchronized long versionOf(String username) {
        return versions.computeIfAbsent(username, name -> 1L);
    }

    // Only called from authorized administrative code or tests.
    public synchronized void assignRole(String username, String role) {
        if (!Set.of("USER", "ADMIN").contains(role)) {
            throw new IllegalArgumentException("Unsupported role");
        }

        UserDetails previous = users.loadUserByUsername(username);

        UserDetails changed = User.withUserDetails(previous)
            .roles(role)
            .build();

        users.updateUser(changed);

        versions.merge(username, 1L, Long::sum);
    }
}
~~~

**Explanation:**

- **InMemoryUserDetailsManager** keeps users/authorities in JVM memory; the demo uses no database.
- **User.withUserDetails(previous)** preserves existing account/password properties and builds a new `UserDetails`; **roles(role)** attaches `ROLE_USER` or `ROLE_ADMIN`.
- **assignRole** accepts roles only from an allowlist, never arbitrary raw authorities from a client.
- After **updateUser**, the version increments by 1. Sessions carrying the old version are flagged as stale when passing through the filter.
- **synchronized** only serializes calls within this instance; it does **not** provide database transactions or atomicity across filters, requests, or multiple JVMs.
- Real systems must update roles and versions atomically in a transaction or via a consistent outbox/revocation mechanism, handling duplicate events and failed updates.

**There is no public HTTP endpoint for assignRole**. In production, administrative operations must verify the actor's grant/revoke permissions, enforce MFA/step-up when needed, and audit all changes.

### 9.5. RoleVersionFilter.java — Rejecting Stale Privilege Snapshots

~~~java
package com.example.rolefreshness;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RoleVersionFilter extends OncePerRequestFilter {

    public static final String SESSION_VERSION =
        RoleVersionFilter.class.getName() + ".rolesVersion";

    private final RoleDirectory roles;

    public RoleVersionFilter(RoleDirectory roles) {
        this.roles = roles;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth != null && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)) {

            HttpSession session = request.getSession(false);
            Object atLogin = session == null
                ? null : session.getAttribute(SESSION_VERSION);

            long currentlyRequired = roles.versionOf(auth.getName());

            if (!(atLogin instanceof Long stored)
                    || stored.longValue() != currentlyRequired) {

                if (session != null) {
                    session.invalidate();
                }
                SecurityContextHolder.clearContext();

                response.setHeader("Cache-Control", "no-store");
                response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication must be renewed");
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
~~~

**Step by step:**

1. This is a **OncePerRequestFilter** on the **Servlet** stack. It has no `@Component` or `@Bean` of its own, so Spring Boot does not accidentally register it twice as a standalone Servlet filter; `SecurityConfig` registers it once in the security chain.
2. The filter reads the current `Authentication` from **SecurityContextHolder**, where the chain already loaded the session's `SecurityContext` for the request.
3. Only **authenticated** principals are checked; anonymous requests continue to normal authorization.
4. It fetches `HttpSession` only if one already exists, never calling `getSession(true)` to create sessions for anonymous requests.
5. If the session lacks a version or differs from the current version, the filter **invalidates** the session and calls **clearContext**, returning 401 to require a fresh login. A missing version is treated **fail-closed** under the demo policy.
6. When versions match, the request proceeds to **AuthorizationFilter** to check the `Authentication`'s roles. The version filter never grants privileges itself.
7. The error response returns **401** per the demo contract (no redirect). This differs from the default `formLogin` entry point where an anonymous `GET /admin` redirects to `/login`.

**Technical limitation:** filtering before `AuthorizationFilter` protects only requests that pass through this filter at check time. A request already past the filter keeps using its snapshot; protecting sensitive writes against concurrent revocation requires checking fresh privileges inside the service/transaction.

**Never catch IOExceptions or database outages and assume "versions match".** When the source of truth is unreadable, high-security policies must fail closed per contract (e.g., 503 or 401 depending on system) with monitoring. Because the demo uses an in-memory lookup, it does not simulate distributed outages.

### 9.6. SecurityConfig.java — formLogin and Session Version

~~~java
package com.example.rolefreshness;

import jakarta.servlet.http.HttpSession;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            RoleDirectory roles) throws Exception {

        RoleVersionFilter versionFilter = new RoleVersionFilter(roles);

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    HttpSession session = request.getSession(true);

                    session.setAttribute(
                        RoleVersionFilter.SESSION_VERSION,
                        roles.versionOf(authentication.getName()));

                    // Demo uses a fixed redirect instead of SavedRequest.
                    response.sendRedirect(
                        request.getContextPath() + "/me");
                }))
            .addFilterBefore(versionFilter, AuthorizationFilter.class);

        return http.build();
    }
}
~~~

**Why does this code use formLogin instead of HTTP Basic?** Form login creates a session holding `Authentication`, making it easy to observe **old authorities surviving across requests**. HTTP Basic usually re-authenticates from raw credentials on each request, which would make demonstrating "session privilege snapshots" harder.

**Why store the version in successHandler?** Upon successful authentication, the provider created `Authentication`; the success handler attaches the version to the same `HttpSession` used to store `SecurityContext`. Subsequent requests compare it against `RoleDirectory`'s current version.

**Why addFilterBefore AuthorizationFilter?** The version filter must check **before URL authorization decides**. If placed after `AuthorizationFilter`, a request carrying a stale `ROLE_ADMIN` could pass the role check before the stale version is detected.

**CSRF:** the config does not disable CSRF. `POST /login` needs a token; integration tests use `with(csrf())` and curl needs the token from the login page. Because the demo only defines GET business endpoints, `/me` and `/admin` need no extra CSRF submission.

**Form login redirect:** the custom `successHandler` here always redirects to `/me` for brevity. It does not preserve the default **SavedRequestAwareAuthenticationSuccessHandler** behavior; in real apps, if you want to return users to their pre-login URL, use the standard handler or delegate to it after storing the version.

**About the login page:** `GET /login` is served by Spring Security's default login page. The `permitAll` rule for `/login` lets anonymous users reach it. `POST /login` is handled by `UsernamePasswordAuthenticationFilter` before `AuthorizationFilter`, with CSRF required by default.

**About filter registration:** `RoleVersionFilter` has neither `@Component` nor `@Bean`, since it is instantiated and wired directly inside `SecurityFilterChain`. This prevents double registration (Servlet container filter + Spring Security filter) that would run version logic out of order.

## 10. Controller Presents Identity Only, Never Mutates Roles

Create **src/main/java/com/example/rolefreshness/DemoController.java**:

~~~java
package com.example.rolefreshness;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities);
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

When `GET /me` runs with an active session, it returns the username and **authorities from the version-checked Authentication**, never passwords, session IDs, or hashes.

Note: the controller returns the authorities used to authorize the request, **not necessarily a live administrative API of latest roles at all times**. In a real system, a "what roles am I currently assigned?" UI may need a separate endpoint reading the current user/permission source, aligned with policy.

## 11. MockMvc: Proving Stale Sessions Are Revoked

Create **src/test/java/com/example/rolefreshness/RoleFreshnessTest.java**:

~~~java
package com.example.rolefreshness;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class RoleFreshnessTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RoleDirectory roles;

    private MockHttpSession loginLearner() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void learnerStartsWithRoleUser() throws Exception {
        MockHttpSession session = loginLearner();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void grantAndRevokeRequireNewLogin() throws Exception {
        try {
            MockHttpSession first = loginLearner();

            mvc.perform(get("/admin").session(first))
                .andExpect(status().isForbidden());

            roles.assignRole("learner", "ADMIN");

            // Old session has stale ROLE_USER/version: must not silently elevate.
            mvc.perform(get("/admin").session(first))
                .andExpect(status().isUnauthorized());

            assertTrue(first.isInvalid());

            // Logging in again loads ROLE_ADMIN from the updated user store.
            MockHttpSession second = loginLearner();

            mvc.perform(get("/admin").session(second))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("admin-ok"));

            // Revoke privilege: the session holding ROLE_ADMIN must be invalidated.
            roles.assignRole("learner", "USER");

            mvc.perform(get("/admin").session(second))
                .andExpect(status().isUnauthorized());

            assertTrue(second.isInvalid());

            MockHttpSession third = loginLearner();

            mvc.perform(get("/admin").session(third))
                .andExpect(status().isForbidden());

            mvc.perform(get("/me").session(third))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities[0]")
                    .value("ROLE_USER"));

        } finally {
            // Reset role so other tests are not affected.
            roles.assignRole("learner", "USER");
        }
    }

    @Test
    void missingSessionVersionFailsClosed() throws Exception {
        MockHttpSession session = loginLearner();

        session.removeAttribute(RoleVersionFilter.SESSION_VERSION);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isUnauthorized());

        assertTrue(session.isInvalid());
    }

    @Test
    void csrfIsRequiredForFormLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

### Invariants Verified

1. Anonymous `GET /public` remains open; the filter does not create a session just for seeing a request.
2. Right after login, `learner` has `ROLE_USER`; `/admin` returns 403 due to insufficient privilege, not a bad password.
3. **Granting ROLE_ADMIN** does not turn the old session into an ADMIN session: the next request with the old session receives **401** and the session is invalidated.
4. **A fresh login** reloads `UserDetails` after the grant so `/admin` succeeds.
5. **Revoking ROLE_ADMIN** causes the old ADMIN session to receive **401** on the next request before stale authorities are consulted; a new login gets only `ROLE_USER`.
6. If an `Authentication` exists yet lacks the `rolesVersion` attribute, the demo policy fails closed by invalidating the session and requiring re-login.
7. Form login uses POST and requires a CSRF token; do not disable CSRF to speed up tests.

**Distinguish status codes clearly:** the first 403 when `learner` has a valid `ROLE_USER` session is an **authorization failure**. The 401 after the version changes is the **demo's forced-renewal policy**. Here 401 is returned by `RoleVersionFilter`, unlike the default form-login response when an anonymous user visits `/admin` (which normally redirects to `/login`).

### Why Doesn't the Test Use @WithMockUser?

`@WithMockUser` injects a mocked `Authentication` into the test request context. That is useful for pure authorization checks, yet **does not test the login flow saving Authentication and rolesVersion in HttpSession**. This test performs **POST /login with CSRF** and carries the **MockHttpSession** into subsequent requests to observe real freshness behavior.

### Why Is try/finally Needed?

`@SpringBootTest` can reuse the `ApplicationContext`. `RoleDirectory` and `InMemoryUserDetailsManager` are singletons with mutable state. A test calling `assignRole("learner", "ADMIN")` without restoring state could affect other tests depending on run order. **`finally`** ensures the role returns to `USER` even if an assertion fails; in production suites, use cleaner fixture isolation and avoid running parallel tests on the same username without locking.

### Testing Limitations

MockMvc verifies logic within one JVM and tests Servlet filter ordering; **it does not prove** multi-node database consistency, event buses, token revocation, open WebSockets, or concurrent in-flight requests. Later sections describe how to test those scenarios in production setups.

## 12. Trying from the Terminal with Form Login and CSRF

Run:

~~~bash
mvn spring-boot:run
~~~

By default the app listens on **http://localhost:8080** if the port is free. To log in manually, open:

~~~text
http://localhost:8080/login
~~~

Use account **learner / learn-pass**. After login, the app redirects to `/me`; JSON will show `ROLE_USER`. `GET /admin` with the same session returns 403.

In this demo app, there is no **public admin API to modify roles**. Grant/revoke steps occur via **RoleDirectory.assignRole(...) calls in tests**, avoiding turning the demo into a self-privilege-escalation endpoint. To observe the full automated behavior, run **mvn test** from Section 11.

To test HTTP via curl without building a separate UI, fetch a valid CSRF token for the same session. Spring Security's default login page includes a hidden **_csrf** form field. You can use browser DevTools or an HTTP client handling cookies and CSRF tokens to send `POST /login`; never submit form login without CSRF and mistake the 403 for a `rolesVersion` error.

**Use plain HTTP on localhost only for learning.** Sending real credentials over the Internet requires HTTPS, and never hardcode passwords in scripts or shell history. Authenticated identities must be verified on the server.

## 13. Plain Java 17 Example to Understand Versioning Without Spring

This is a minimal logical model, not a replacement for real authentication. Create **RoleVersionTimeline.java**:

~~~java
public class RoleVersionTimeline {

    record Snapshot(String username, long rolesVersion) {}

    public static void main(String[] args) {
        long sourceVersion = 1L;
        Snapshot first = new Snapshot("learner", sourceVersion);

        System.out.println("initial: "
            + (first.rolesVersion() == sourceVersion));

        sourceVersion++;
        System.out.println("after-change: "
            + (first.rolesVersion() == sourceVersion));

        Snapshot second = new Snapshot("learner", sourceVersion);
        System.out.println("re-login: "
            + (second.rolesVersion() == sourceVersion));
    }
}
~~~

Compile and run with JDK 17+ in the file's directory:

~~~bash
javac RoleVersionTimeline.java
java RoleVersionTimeline
~~~

**Exact stdout:**

~~~text
initial: true
after-change: false
re-login: true
~~~

Explanation: the first snapshot captures `version=1`. When the source bumps to `2`, the old snapshot does not update itself; the equality check becomes `false`. A new snapshot created after "re-login" stores `version=2` and passes. This example only illustrates equality; it **does not** perform authentication, session management, or authorization and must never be used as a security library.

## 14. What If You Want to Refresh Authentication Instead of Forcing Re-Login?

That is a **different policy** from the demo. Before deciding to auto-refresh, answer:

- **Which authority source is trusted?** `UserDetailsService`, database, policy service, or IdP?
- **Which principal type is held?** `UserDetails`, `OAuth2AuthenticationToken`, `JwtAuthenticationToken`, or a custom `Authentication`?
- **Which data can change?** Authorities, tenant, account status, MFA/assurance level, authentication time?
- **Should elevation happen without re-authentication?** If the user was just granted ADMIN, does policy require MFA or step-up?
- **Where is SecurityContext stored?** `HttpSessionSecurityContextRepository`, request attributes, Spring Session?
- **What detects changes?** Events, version checks, cache TTL, per-request lookups?
- **When is context saved?** In Spring Security 6 with explicit save, you must save via `SecurityContextRepository` for future requests to see the new `Authentication`.
- **Are concurrent requests possible?** Two browser tabs can save conflicting snapshots; last-write-wins races must be handled.
- **What about session fixation and CSRF token lifecycles?** Changing authentication/privilege state may require invoking corresponding session strategies.

Conceptual fragment:

~~~java
// Conceptual illustration ONLY, NOT standalone code.
// Authentication fresh = authenticationService.reauthenticateOrRefresh(...);
// SecurityContext updated = SecurityContextHolder.createEmptyContext();
// updated.setAuthentication(fresh);
// SecurityContextHolder.setContext(updated);
// repository.saveContext(updated, request, response);
~~~

**Never mutate the authorities collection using Java reflection or cast a mutable principal.** A new `Authentication` must be constructed from verified sources with consistent account status, assurance level, tenant, auth time, and policy. Exact APIs vary by `Authentication` type and Spring Security version.

### Cases Where Auto-Refresh Should Be Avoided

- An account was just granted administrative privileges and policy requires MFA/re-authentication.
- The session shows signs of compromise.
- The account was disabled/locked rather than simply changing a role list.
- Auto-refreshing context would bypass user consent or token-issuance checks.
- The app cannot guarantee context consistency under concurrent session writes.

In those cases, **invalidate-and-reauth** is usually easier to reason about and test.

## 15. Dynamic Authorization: Avoid Relying Solely on Role Snapshots

For administrative privileges or resource ownership, "user had `ROLE_ADMIN` at login" can be too coarse. For example, `GET /projects/42` must ask:

- Which tenant does project 42 belong to?
- Is the current user still a member of the project?
- Was the user's project read/write permission revoked?
- Is there an "only owner may download data" rule?
- Does the system check the latest policy after role changes?

One design direction:

~~~text
Authentication -> verified userId
       |
       v
Controller/Service requests action on resourceId
       |
       v
PermissionService checks current privilege source
       |
       +-- allowed -> execute business logic
       |
       +-- denied  -> AccessDeniedException / 403
~~~

Spring Security can enforce policies at URL level via **AuthorizationManager**, at method level via **@PreAuthorize**, or inside services via a verified privilege-checking component. For data-dependent privileges, checks at the **service/domain boundary** are especially important because URL matching does not know who actually owns a project.

**Clear distinction:** `RoleVersionFilter` ensures a session does not reuse an old `rolesVersion` at the start of a request. Yet if a project's owner changes mid-request, a permission check close to the data read/export operation is still required. The two mechanisms cover different scopes.

### Caching Inside PermissionService

Caching permissions reduces DB load but delays revocations. With a cache TTL of 60 seconds, treat that as a potential staleness window; TTL is only one factor alongside event invalidation, replication lag, and in-flight requests. For sensitive actions, shorten TTL or read the privilege source directly inside the transaction. When the privilege source is unreachable, choose **fail-closed** behavior matching the risk.

## 16. Revoking Another User's Sessions: SessionRegistry and Spring Session

An admin revoking `learner`'s `ROLE_ADMIN` may want to terminate **all** of `learner`'s sessions immediately rather than waiting for each session's next filter pass. Tools exist, with important deployment caveats.

### 16.1. SessionRegistry in Spring Security

**SessionRegistry** can track principals/sessions and expose `SessionInformation`. You can call **expireNow()** on `SessionInformation` to mark a session expired. However:

- Session tracking / concurrent session control must be configured properly so the registry knows about active sessions.
- **expireNow()** only flags the session; **ConcurrentSessionFilter** must be wired properly to act on it when the next request enters the chain.
- Default in-memory implementations stay inside one JVM; they do not handle multi-node clusters.
- Principal equality/keying must stay consistent; if principal identity/`equals` changes, user session lookups may misbehave.
- Never assume every existing `HttpSession` is registered in `SessionRegistry` without testing your real config.

Thus **SessionRegistry is not a magic "global invalidateAllUsers()"** just from injecting a bean. Proper setup and end-to-end tests are required.

### 16.2. Spring Session and Shared Session Stores

With Redis/JDBC-backed Spring Session, you can use a repository **indexed by principal** to find a user's sessions and delete them when policy dictates. Conceptual flow:

~~~text
Admin revokes role
  |
  v
Transaction updates role/version in DB
  |
  v
Session revocation service looks up sessions by principalName
  |
  v
Delete/expire sessions in shared store
  |
  v
Request on any node finds the session no longer valid
~~~

Exact APIs and indexes depend on the Spring Session repository type. Do not assume every backend supports looking up all sessions by username, especially if principal indexing is not configured or usernames can change.

### 16.3. Pros and Cons of Proactive Revocation

Pros: terminates multiple sessions early, even idle ones. Cons: requires privileges to enumerate sessions, securing admin actions, handling event retries, session-store availability, and races with sessions being created concurrently. Combining a per-request version check with proactive revocation provides a fallback if event delivery lags, provided the version source is shared.

## 17. JWTs, Access Tokens, and Refresh Tokens on Role Changes

With bearer JWTs, roles often live in claims like `roles` or `scope`. A signed token remains valid **until `exp`** even after database privileges change. You cannot modify claims inside an already-issued JWT while keeping its signature valid.

Practical strategies:

| Strategy | Effect | What to watch |
| --- | --- | --- |
| **Short-lived access tokens** | Limits how long stale roles persist in tokens | Does not immediately revoke already-issued tokens |
| **Refresh token rotation and revocation** | Blocks minting new access tokens from revoked refresh tokens | Existing access tokens can stay valid until `exp` |
| **Token introspection** | Queries token status from the server | Introspection caching/availability affects freshness |
| **Token denylist/jti** | Blocks specific revoked tokens | Requires shared state and checks on relevant requests |
| **rolesVersion/tokenVersion claim** | Compares token version against current version | Effective only if resource servers verify it against a trusted source |
| **Per-action policy lookup** | Does not rely solely on stale role claims | Latency cost and data/replication considerations |

**Never claim:** "Updating roles in the DB automatically revokes old JWTs." The signature remains valid, and claims remain a stale snapshot.

If a multi-node resource server validates JWTs offline, a "role changed" event sent to node A does not automatically make node B reject the token. You need a shared version/denylist store, introspection, or risk-appropriate short token lifetimes.

### Can a Revoked JWT Still Linger in Caches?

Yes, depending on how validation works. Resource servers often cache introspection or permission decisions. When designing for a "5-second revocation target", account for cache TTLs, replication, event propagation delay, clock skew, and in-flight requests. "Access token `exp` is 5 minutes" does not mean "revocation takes 5 seconds".

### Should a New JWT Be Issued Immediately on Role Change?

Not automatically. If the new token carries higher privileges, ensure the user/session meets authentication assurance rules such as MFA. Mint new tokens from the proper issuer with clear elevation policies. On revocation, prioritize preventing old tokens carrying revoked scopes from passing authorization checks.

## 18. Multi-Node, Caching, and Consistency

Because the demo uses an in-JVM Map, it is **not safe as a cluster-wide rolesVersion source**. With two nodes:

~~~text
Node A                        Node B
role change -> version=9      version cache still=8
     |                            |
     v                            v
session on A invalidated      session on B may still pass check
~~~

To enforce a consistent policy:

1. Store versions in a **shared database/identity store**.
2. Update privileges and versions with proper transaction/atomicity semantics to avoid wide inconsistency windows.
3. If caching, design **TTL, event invalidation, bounded staleness, and fail-closed** handling for sensitive endpoints.
4. Use an outbox/event bus for proactive multi-node revocation; handle duplicate and out-of-order events with monotonically increasing versions.
5. Enforce authentication/authorization in the service performing business work, rather than blindly trusting a gateway cache with stale roles.
6. For long-running requests, check privileges at **commit/action points** or support cancellation where needed.
7. For WebSockets, SSE, and background jobs, refresh connection/job authorization state via dedicated lifecycle hooks: HTTP filters do not re-check every message or job step automatically.
8. Measure end-to-end latency from when an admin clicks revoke until every node rejects stale privileges, not just DB write time.

### Race Condition in the Example

Even with `RoleDirectory.assignRole(...)` synchronized, one request can pass the version check right before another thread updates roles, then proceed past `AuthorizationFilter` and execute a sensitive action after the update. The demo **demonstrates session invalidation on the next request after a role change completes**, not strict linearizability across concurrent operations.

If business rules demand "once the revoke transaction commits, no new operation may use old privileges", implement explicit locking/transactions/serialization at the business operation boundary; a Servlet filter checking version at request start **is not enough**.

### When the Version Source Fails

Never catch a DB error and assume `roleVersion` matches. For sensitive privileges, when freshness cannot be verified, deny with 503 or an appropriate code to **fail closed**, accompanied by safe logging, alerting, and circuit breakers. Document this policy in SLAs; a network error must never become an authorization bypass.

## 19. Common Mistakes

| Mistake | Why it is dangerous or wrong | How to handle |
| --- | --- | --- |
| Updating `UserDetails` in DB assuming all sessions update | Stored `Authentication` is a snapshot | Version checks, invalidation, or controlled refresh |
| Calling `SecurityContextHolder.clearContext()` in admin request to log out a user | Clears only the current request context | Session registry/store or per-request target checks |
| Mutating the session's authorities collection directly | Immutability and thread safety are broken | Build a new `Authentication` or revoke the session |
| Checking only `hasRole("ADMIN")` on old JWTs | Role claims in the token can be stale | Revocation, versioning, or policy lookups |
| Adding `ROLE_ADMIN` to an old session without step-up | Elevates session without sufficient assurance | Require re-authentication/MFA per policy |
| Deleting browser cookie while server session/token remains valid | Cookie deletion alone does not revoke server credentials | Invalidate server session / revoke token |
| Invalidating only one `HttpSession` across multiple devices | Other active sessions remain valid | Per-user session enumeration or versioning |
| Using an in-memory version Map in a cluster | Other nodes do not see updates | Shared store and cache invalidation |
| Caching permissions for too long | Slow revocation | Freshness SLOs, short TTLs, event invalidation |
| Ignoring CSRF on privilege-changing endpoints | Browsers auto-send session cookies | Enforce CSRF protection on unsafe methods |
| Testing with `@WithMockUser` assuming session refresh works | Mocked auth skips login and session lifecycle | Test with `MockMvc` `formLogin` / real sessions |
| Ignoring in-flight requests | Filter runs only at request start | Re-check authorization at critical execution points |
| Ignoring WebSockets or long-running jobs | Subsequent messages/steps skip HTTP filters | Dedicated lifecycle revalidation |
| Failing open when version store fails | Errors become authorization bypasses | Enforce fail-closed policy and monitoring |
| Wrong role prefix | `roles("ADMIN")` produces `ROLE_ADMIN` | Align `hasRole` / `hasAuthority` |
| Confusing 401 with 403 | 401 in demo means renew auth; 403 means insufficient privilege | Document clear contract for frontends |
| Auto-refreshing newly granted roles without checking session | An old stolen session gets elevated | Step-up/re-auth on privilege elevation |
| Not rolling back roles in tests | Shared Spring context state mutates | Use `try/finally` or fixture isolation |

### Debugging Workflow

1. Identify the auth mechanism: form login/session, HTTP Basic, JWT, OAuth2/OIDC, remember-me, or custom.
2. Inspect authorities and metadata on the **active Authentication** without logging secret credentials.
3. Check current source privileges and `roleVersion` in the database/IAM.
4. Determine whether the request loads `Authentication` from session/JWT or re-authenticates via `UserDetailsService`.
5. Check which filter/`AuthorizationManager` enforces version/policy, and verify **placement before AuthorizationFilter**.
6. If revocation fails to take effect, inspect the version store, caches, session IDs, and multiple nodes.
7. If grants do not appear, distinguish an intentional re-login policy from a data-source bug.
8. Check user/account status and tenant, not just `ROLE_` lists.
9. For 401, distinguish expired credentials/sessions from forced-renewal messages; for 403, distinguish missing privilege from CSRF.
10. Inspect in-flight requests, background jobs, and WebSockets if immediate revocation is required.
11. Write a reproducing integration test before changing security config.
12. Never "fix" issues with `permitAll`, disabling CSRF, or removing authorization checks.

## 20. Practice Exercises and Answers

### Exercise A — Grant After Login

Learner logs in with `ROLE_USER`, and an admin grants `ROLE_ADMIN` in the database. Why can `GET /admin` using the old `HttpSession` still return 403?

**Answer:** The session's `Authentication` holds a `ROLE_USER` snapshot. Updating the database does not auto-refresh `Authentication`. Policy must define refresh or re-authentication.

### Exercise B — Revoke Is Riskier Than Delayed Grant

An admin logged in with `ROLE_ADMIN`; the role is revoked, yet the session still holds `ROLE_ADMIN`. Why is `hasRole("ADMIN")` alone insufficient?

**Answer:** The rule checks the authority inside the stale `Authentication`, without consulting the latest version/privileges. Revocation, version checks, or policy lookups are needed per the threat model.

### Exercise C — Changing Roles via UserDetailsManager

Does calling `users.updateUser(updated)` scan every `HttpSession` of that user to update authorities?

**Answer:** No. `UserDetailsManager` updates the user store, not the `SecurityContext` inside active sessions.

### Exercise D — rolesVersion Filter

A session stores `rolesVersion=4`, while the data store is now `version=5`. Under the demo policy, what happens on the next authenticated request?

**Answer:** The filter detects the mismatch, invalidates the session, clears `SecurityContext`, and returns 401 to force re-login. It does not silently elevate the old session.

### Exercise E — Why Place the Filter Before AuthorizationFilter?

What risk arises if `RoleVersionFilter` runs after `AuthorizationFilter`?

**Answer:** Role-based checks could evaluate stale authorities and allow access before the stale version is caught. Freshness filters must run before authorization decisions.

### Exercise F — New Privileges After Re-Login

The data source changed from `ROLE_USER` to `ROLE_ADMIN` and bumped the version. Why does the new session get `ADMIN` access?

**Answer:** On fresh login, `AuthenticationProvider` calls `UserDetailsService` to load updated `UserDetails`. `SuccessHandler` stores the current version in the new session.

### Exercise G — JWT

A JWT has 30 minutes left before expiry and contains `ROLE_ADMIN`. The role was revoked in the database. Does the JWT update its claims automatically?

**Answer:** No. Issued tokens keep static claims; fast revocation requires versioning/denylists/introspection, policy lookups, or appropriately short token lifetimes.

### Exercise H — SessionRegistry

You declare a `SessionRegistry` bean without configuring session tracking or `ConcurrentSessionFilter`. Does `expireNow()` guarantee revoking all `HttpSession`s across a cluster?

**Answer:** No. Proper tracking/filter integration is required so the registry actually tracks sessions, plus a shared backend for multi-node setups.

### Exercise I — Race with In-Flight Requests

A request passes `RoleVersionFilter` right before a role is revoked, then completes a sensitive action. Can the filter guarantee absolute prevention?

**Answer:** No. Checking at request entry does not revoke in-flight requests. You need authorization at the operation/commit point or cancellation/serialization controls.

### Exercise K — MFA When Granting ADMIN

Should an existing session's `Authentication` always be auto-replaced with `ROLE_ADMIN` the instant an admin grants the role without checking assurance level?

**Answer:** Not by default. For elevated privileges, consider requiring re-authentication/MFA/step-up before using the new role.

### Exercise L — Fail-Open vs. Fail-Closed?

If the `rolesVersion` source has a network failure, should a policy protecting a sensitive data export endpoint assume versions match and allow access?

**Answer:** Never fail open. Deny safely, return an appropriate error, and alert; allow only when freshness is verified per policy.

### Exercise M — Two Nodes

Node A increments the version in a local Map, while node B still reads its old Map. Why might requests to node B still succeed?

**Answer:** Two Maps in separate JVMs do not synchronize. Use a shared DB/session store/version source or shared invalidation mechanism.

## 21. Production Deployment Checklist

- [ ] Identified trusted privilege sources: database/IAM/policy service and data owners.
- [ ] Recognized that `Authentication` in `SecurityContext`/session/JWT can be a snapshot.
- [ ] Defined separate policies for **grant**, **revoke**, **account disable**, and tenant changes.
- [ ] Defined the maximum acceptable revocation delay per action category.
- [ ] Never assumed updating `UserDetails` in the store refreshes active sessions.
- [ ] Never mutated session authorities directly; any refresh builds a new verified `Authentication`.
- [ ] For sensitive privileges, considered invalidate-and-reauth/step-up instead of silent elevation.
- [ ] When using `rolesVersion`, ensured versions update atomically with roles and are read from a shared source.
- [ ] Placed freshness filters/policies before authorization or right at sensitive business operations.
- [ ] Handled missing session versions, version-source failures, and disabled accounts fail-closed.
- [ ] Tested stale sessions after grants, revokes, and account-disable events.
- [ ] Tested re-login loading updated authorities, and verified old sessions cannot be reused.
- [ ] If using `SessionRegistry`/Spring Session, verified principal indexing and multi-node behavior.
- [ ] If using JWT/bearer tokens, designed token TTLs, revocation, and stale-claims mitigation.
- [ ] Avoided relying solely on URL `hasRole` when access depends on owner/tenant/resource.
- [ ] Accounted for in-flight requests, WebSockets/SSE, and background jobs.
- [ ] Defined SLOs, monitoring, and regression tests for caches, event delivery, and replication lag.
- [ ] Ensured CSRF, session fixation, cookie attributes, HTTPS, and rate limiting remain intact.
- [ ] Protected admin role-change APIs with authorization, auditing, confirmation, and MFA where needed.
- [ ] Never logged raw passwords, JWTs, session cookies, or secret credentials during debugging.
- [ ] Ensured role-change tests clean up state and avoid order-dependent/parallel races.
- [ ] Documented a clear contract to frontends distinguishing 401 ("must re-login") from 403 ("lacks permission").
- [ ] Tested revoked privileges at **every** sensitive execution point, not just UI screens.

**Conclusion:** Database/IAM privileges and authorities inside a **stored Authentication** are not always identical. When privileges change at runtime, Spring Security Servlet **does not automatically update all active HttpSessions or JWTs**. Choose an explicit policy: accept bounded snapshots, safely refresh `Authentication`, invalidate sessions and require re-authentication, or check live permissions where data is accessed. The **rolesVersion + RoleVersionFilter** example shows how to **force stale sessions to expire on the next request**, while production also requires addressing transactions, multi-node state, caching, token revocation, and in-flight requests for stronger revocation guarantees.
