# GrantedAuthorityDefaults and Component-Level Prefix Scope

> **Scope:** Spring Security Servlet, Spring Boot with Java 17+, focusing on the relationship between `GrantedAuthority`, the `ROLE_` convention, changing the prefix with `GrantedAuthorityDefaults`, and its effective boundaries across individual APIs. Sample code uses APIs available in Spring Security 6.5.x; re-run tests when upgrading major/minor versions.

## 1. Why does changing the role prefix cause 403 errors?

In Spring Security, permissions are assigned to an identity via the `GrantedAuthority` list on `Authentication`. With the common `SimpleGrantedAuthority`, the authority value is an **exact string**. For example, `"ROLE_ADMIN"`, `"APP_ADMIN"`, and `"ADMIN"` are three distinct values.

- `hasAuthority("APP_ADMIN")` requires the **exact string** authority `APP_ADMIN`.
- `hasRole("ADMIN")` relies on the **role prefix convention**; with the default prefix `ROLE_`, most role-checking mechanisms look for `ROLE_ADMIN`.
- `GrantedAuthorityDefaults("APP_")` lets components **that support this configuration** interpret role `ADMIN` as authority `APP_ADMIN`.

Suppose Alice receives `ROLE_ADMIN` upon authentication. The application adds `GrantedAuthorityDefaults("APP_")` and uses `@PreAuthorize("hasRole('ADMIN')")`. If the method expression handler picks up the new prefix, the check looks for `APP_ADMIN` and **denies Alice**, even though Alice authenticated successfully. The fix is to align authority data, policy configuration, and tests; merely defining the bean does not automatically convert `ROLE_ADMIN` into `APP_ADMIN`.

**Distinction:** authentication verifies identity; authorization decides whether that identity has permission for the action/resource in question. A 403 here usually means **missing the expected authority**, whereas missing/invalid login credentials typically triggers the authentication entry point (HTTP Basic may return 401).

## 2. What does `GrantedAuthorityDefaults` do?

The class `org.springframework.security.config.core.GrantedAuthorityDefaults` accepts a `rolePrefix` argument; `getRolePrefix()` returns that value. Its purpose is to define the default prefix for **role-based authorization rules** in components that integrate with the bean.

Minimal configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Configuration
class RolePrefixConfig {
    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }
}
~~~

This is a **configuration class inside a Spring application** (requiring the Spring Security dependency), not a standalone `main` runnable via `java RolePrefixConfig`.

Official documentation recommends `static @Bean` so Spring registers the prefix configuration **early**, before method security configuration is initialized. You can mark the bean as infrastructure with `@Role(BeanDefinition.ROLE_INFRASTRUCTURE)` if the project wants to make the bean's role explicit.

**This bean does not automatically:**

1. Rename strings inside `Authentication#getAuthorities()`, sessions, JWTs, or the database.
2. Rewrite every `hasAuthority("ROLE_ADMIN")` into `hasAuthority("APP_ADMIN")`.
3. Change how `User.UserBuilder.roles(...)` or `@WithMockUser(roles = ...)` generates authorities.
4. Change static factories that hardcode `ROLE_`, such as `AuthorityAuthorizationManager.hasRole(...)`.
5. Change the `SCOPE_` prefix assigned by JWT converters to OAuth2 scopes.
6. Modify literals inside `@Secured`, role hierarchies, or custom authorization managers you configured yourself.

Think of it as a **configuration for consumers**, not a find-and-replace across all of Spring Security.

## 3. Component-by-component scope table

Example: the desired new prefix is `APP_`; the business role is named `ADMIN`.

| Component / API | Relevant mechanism | Notes |
| --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Method security expression handler uses role prefix; standard config can read `GrantedAuthorityDefaults` | Once `APP_` applies, requires `APP_ADMIN` |
| `@PostAuthorize("hasRole('ADMIN')")` | Also a method security expression | Runs after method execution; use only if truly needed |
| `@PreAuthorize("hasAuthority('APP_ADMIN')")` | Matches literal `APP_ADMIN` | Does not add/change prefixes |
| `authorizeHttpRequests().hasRole("ADMIN")` | HTTP DSL creates `AuthorizationManager`; how the prefix is resolved depends on configuration path and version | Verify with HTTP integration tests after changing prefix |
| `authorizeHttpRequests().hasAuthority("APP_ADMIN")` | Literal match | Clear syntax when wanting a custom authority |
| `AuthorityAuthorizationManager.hasRole("ADMIN")` | Static factory of this API prepends `ROLE_` itself | Does not consume the `GrantedAuthorityDefaults` bean by default |
| `AuthorityAuthorizationManager.hasAuthority("APP_ADMIN")` | Literal match | Suitable when constructing managers manually |
| `User.withUsername(...).roles("ADMIN")` | Builder **creates `ROLE_ADMIN`** | Not altered automatically by the `APP_` bean |
| `User.withUsername(...).authorities("APP_ADMIN")` | Creates authority `APP_ADMIN` | Use when a custom prefix is needed |
| `new SimpleGrantedAuthority("APP_ADMIN")` | Stores the exact string passed | No automatic prefix |
| `@WithMockUser(roles = "ADMIN")` | Test annotation usually creates `ROLE_ADMIN` | To test the new prefix, use `authorities = "APP_ADMIN"` |
| `@Secured("APP_ADMIN")` | Annotation uses the declared authority name | Not treated as a `hasRole` SpEL expression; enable `securedEnabled` |
| `@RolesAllowed("ADMIN")` | JSR-250 authorization manager has its own role prefix mechanism, defaulting to `ROLE_` | Enable `jsr250Enabled` and verify config/version |
| `RoleHierarchyImpl.fromHierarchy("APP_ADMIN > APP_USER")` | Hierarchy string contains actual authority names | Prefix bean does not rewrite hierarchy strings |
| `JwtGrantedAuthoritiesConverter` | Scopes map with `SCOPE_` by default | Configure a custom converter if changing conventions |
| `RoleVoter` and legacy mechanisms | Have their own prefix settings | Do not assume modern method-security logic applies to all components |

**Key learning point:** the name `hasRole` may appear across multiple API layers, yet **not every implementation reads its prefix from the same source**. When choosing a custom prefix, always verify the contract of each enforcement component.

### Three steps to distinguish

~~~text
(1) AUTHENTICATION AND AUTHORITY GRANTING
    UserDetailsService / JWT converter / AuthenticationProvider
        -> Authentication.authorities = ["APP_ADMIN"]

(2) TRANSLATING ROLE TO AUTHORITY REQUIREMENT
    @PreAuthorize("hasRole('ADMIN')")
    + role prefix "APP_" in method expression handler
        -> requires "APP_ADMIN"

(3) PERMISSION MATCHING
    Compare required "APP_ADMIN" against authority list
        -> has "APP_ADMIN" => allow
        -> has only "ROLE_ADMIN" => deny
~~~

Getting any step wrong can let an account log in successfully yet be denied during policy enforcement.

## 4. Java 17+ and Spring Boot example: verifying prefixes at method and HTTP layers

The example below uses three users:

- Alice is granted `authorities("APP_ADMIN")`, so her actual authority is `APP_ADMIN`.
- Bob is granted `roles("ADMIN")`, so his actual authority remains `ROLE_ADMIN`.
- Charlie is granted `authorities("APP_USER")`, so his actual authority is `APP_USER`.

The HTTP check using `hasAuthority(...)` keeps the **exact string** explicit. The method check using `hasRole(...)` demonstrates the effect of `GrantedAuthorityDefaults("APP_")` on standard method security.

Create a Spring Boot Maven project using **Java 17+**, **Spring Web**, and **Spring Security** starters. Place the following class in `src/main/java/com/example/prefix/PrefixApplication.java`.

~~~java
package com.example.prefix;

import java.util.stream.Collectors;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.core.GrantedAuthorityDefaults;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class PrefixApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrefixApplication.class, args);
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/http/admin").hasAuthority("APP_ADMIN")
            .requestMatchers("/method/admin", "/method/user",
                "/literal/admin", "/whoami").authenticated()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("APP_ADMIN")
            .build();

        // roles("ADMIN") still creates "ROLE_ADMIN".
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        UserDetails charlie = User.withUsername("charlie")
            .password(encoder.encode("demo789"))
            .authorities("APP_USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, charlie);
    }

    @RestController
    static class Api {
        private final ProtectedService service;

        Api(ProtectedService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/http/admin")
        String httpAdmin() {
            return "http admin";
        }

        @GetMapping("/method/admin")
        String methodAdmin() {
            return service.admin();
        }

        @GetMapping("/method/user")
        String methodUser() {
            return service.user();
        }

        @GetMapping("/literal/admin")
        String literalAdmin() {
            return service.literalAdmin();
        }

        @GetMapping("/whoami")
        String whoami(Authentication authentication) {
            String authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + authorities;
        }
    }

    @Service
    static class ProtectedService {

        @PreAuthorize("hasRole('ADMIN')")
        public String admin() {
            return "method admin";
        }

        @PreAuthorize("hasRole('USER')")
        public String user() {
            return "method user";
        }

        @PreAuthorize("hasAuthority('ROLE_ADMIN')")
        public String literalAdmin() {
            return "literal admin";
        }
    }
}
~~~

Note: `Api` calls the Spring-managed `ProtectedService`, so the method-security proxy can intercept `@PreAuthorize`. Calling `this.admin()` inside the same service typically bypasses advice under proxy-based AOP; do not use self-invocation as an authorization test example.

### Run commands

Run from the Maven project directory:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
~~~

Once the application is running on `localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/method/admin
curl -i -u alice:demo123 http://localhost:8080/whoami
curl -i -u bob:demo456 http://localhost:8080/whoami
curl -i -u alice:demo123 http://localhost:8080/method/admin
curl -i -u bob:demo456 http://localhost:8080/method/admin
curl -i -u charlie:demo789 http://localhost:8080/method/user
curl -i -u alice:demo123 http://localhost:8080/http/admin
curl -i -u bob:demo456 http://localhost:8080/http/admin
curl -i -u bob:demo456 http://localhost:8080/literal/admin
curl -i -u alice:demo123 http://localhost:8080/literal/admin
~~~

| Request | Expected HTTP | Reason |
| --- | --- | --- |
| `/public/ping`, anonymous | 200, `pong` | `permitAll()` |
| `/method/admin`, anonymous | 401 | Route requires authentication; HTTP Basic requests credentials |
| `/whoami`, Alice | 200, `alice:APP_ADMIN` | Alice's actual authority |
| `/whoami`, Bob | 200, `bob:ROLE_ADMIN` | `roles("ADMIN")` still produces `ROLE_ADMIN` |
| `/method/admin`, Alice | 200, `method admin` | Method `hasRole('ADMIN')` looks for `APP_ADMIN` |
| `/method/admin`, Bob | 403 | Bob only has `ROLE_ADMIN` |
| `/method/user`, Charlie | 200, `method user` | Has `APP_USER` |
| `/http/admin`, Alice | 200, `http admin` | HTTP matches literal `APP_ADMIN` |
| `/http/admin`, Bob | 403 | Bob lacks `APP_ADMIN` |
| `/literal/admin`, Bob | 200, `literal admin` | `hasAuthority('ROLE_ADMIN')` is a verbatim match |
| `/literal/admin`, Alice | 403 | Alice lacks `ROLE_ADMIN` |

In the example, missing credentials on a protected resource yields **401** via HTTP Basic; being logged in yet lacking permission yields **403**. If a project uses form login, unauthenticated requests may redirect to the login page. Passwords are for demo purposes only; HTTP Basic must run over HTTPS in real deployments.

## 5. APIs that look similar yet are not equivalent

### 5.1. HTTP DSL `hasRole` vs static `AuthorityAuthorizationManager.hasRole`

These two snippets may look similar:

~~~java
// Fragment placed inside authorizeHttpRequests:
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

~~~java
// Java fragment using the manager directly:
var manager = AuthorityAuthorizationManager.hasRole("ADMIN");
~~~

However, the first goes through HTTP DSL configuration; the second uses a **static factory whose contract prepends `ROLE_` itself**. With custom prefix configuration, do not treat them as equivalent without checking the version and manager creation mechanism.

If you want to check exact `APP_ADMIN`, you can use:

~~~java
// Fragment in HTTP DSL:
.requestMatchers("/admin/**").hasAuthority("APP_ADMIN")

// Or when constructing the manager directly:
var manager = AuthorityAuthorizationManager.hasAuthority("APP_ADMIN");
~~~

The snippets above are **fragments** and do not compile standalone. Import the manager class from `org.springframework.security.authorization.AuthorityAuthorizationManager`.

### 5.2. `@PreAuthorize` and `@Secured`

`@PreAuthorize("hasRole('ADMIN')")` goes through a **SpEL expression** and the default role prefix. In contrast, `@Secured("APP_ADMIN")` expresses an **authority literal** in the annotation handled by `SecuredAuthorizationManager`; do not assume it is an internal `hasRole` SpEL call.

Enable the corresponding option:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

If also using JSR-250:

~~~java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

JSR-250 uses `jakarta.annotation.security.RolesAllowed` with role prefix handling managed by `Jsr250AuthorizationManager`; the API provides `setRolePrefix(...)`. Therefore, during migration, check whether this manager is properly integrated with the custom prefix. Ensure the Jakarta annotation API dependency is present if the runtime does not supply it.

### 5.3. `RoleHierarchy` contains actual authority strings

Example:

~~~java
RoleHierarchy hierarchy =
    RoleHierarchyImpl.fromHierarchy("APP_ADMIN > APP_USER");
~~~

This is a **fragment**; import `org.springframework.security.access.hierarchicalroles.RoleHierarchy` and `RoleHierarchyImpl`. The hierarchy string contains **actual authority names**, and is not rewritten automatically by `GrantedAuthorityDefaults`. Also make sure the authorization layer actually uses the appropriate hierarchy, rather than creating a bean and assuming every custom manager knows about it.

### 5.4. UserDetails, OAuth2, and tests

- `User.withUsername("bob").roles("ADMIN")` creates `ROLE_ADMIN`.
- `User.withUsername("bob").authorities("APP_ADMIN")` creates `APP_ADMIN`.
- `new SimpleGrantedAuthority("APP_ADMIN")` keeps the string `APP_ADMIN` verbatim.
- `@WithMockUser(roles = "ADMIN")` usually creates `ROLE_ADMIN`; to test the new prefix, use `@WithMockUser(authorities = "APP_ADMIN")` and also test the denied path.
- `JwtGrantedAuthoritiesConverter` normally creates `SCOPE_...` from verified JWT scopes. The role-prefix bean does not convert `SCOPE_report.read` into `APP_report.read`. If the IdP provides roles in another claim, you need an explicit converter/mapper and a trusted token source.
- If roles/authorities are stored in sessions/JWTs/caches, changing a bean or database **does not necessarily** update active credentials/sessions immediately. A refresh/revocation strategy is required.

### 5.5. Legacy components and other versions

`RoleVoter`, legacy XML configuration, reactive security, custom expression handlers, and custom `AuthorizationManager` implementations may use different prefix mechanisms. When upgrading from Spring Security 6.x to 7.x, re-check new APIs related to `AuthorizationManagerFactory` and how it receives `rolePrefix`; do not extrapolate from an older version's behavior. Configuration **must be proven with integration tests**, especially when combining URL security, method security, and token converters.

## 6. Diagnosing prefix issues step by step

When an account is logged in yet gets 403:

1. Determine whether the request was blocked at **HTTP authorization** or **method authorization**; check both if present.
2. Inspect the **actual authorities** on `Authentication`: e.g., print `authentication.getAuthorities()` in a test environment. Never log passwords or tokens.
3. Record the **required rule**: `hasRole('ADMIN')`, `hasAuthority('APP_ADMIN')`, `@Secured`, or a custom manager.
4. Find the **prefix source** used by the consumer: default method expression prefix, HTTP DSL prefix, static factory, converter, or role hierarchy.
5. Verify the `GrantedAuthorityDefaults` bean exists and is created early (for method security: `static @Bean`).
6. If the project defines a custom `MethodSecurityExpressionHandler`, `AuthorizationManager`, or `RoleHierarchy`, check whether those components have custom settings overriding/limiting the default.
7. Check stale data from JWTs, SSO, sessions, caches, or the database.
8. Write tests confirming **both allow and deny**, avoiding fixing 403s by opening `permitAll()`.

Example expected matrix for a policy requiring `APP_ADMIN`:

| Input authority | `hasAuthority('APP_ADMIN')` | Method `hasRole('ADMIN')` with `APP_` applied |
| --- | --- | --- |
| `APP_ADMIN` | ALLOW | ALLOW |
| `ROLE_ADMIN` | DENY | DENY |
| `ADMIN` | DENY | DENY |
| `APP_USER` | DENY | DENY |
| No matching authority | DENY | DENY |

This is the **expected matrix when the method component actually receives the `APP_` prefix**. If actual tests differ, locate the cause in the authority producer or consumer config; never alter tests just to hide failures.

## 7. Migrating from `ROLE_` to `APP_`

1. **Finalize the data contract:** decide where logical role `ADMIN` is stored as authority `APP_ADMIN`; keep roles separate from permissions such as `invoice:read`.
2. **Inventory authority producers:** in-memory users, database, LDAP/OIDC, JWT converters, SSO mappings, test fixtures.
3. **Inventory enforcement points:** HTTP DSL, method SpEL, `@Secured`, `@RolesAllowed`, custom `AuthorizationManager`, role hierarchies, legacy voters.
4. **Register `GrantedAuthorityDefaults` early:** use `static @Bean`; in custom handlers/managers, configure directly if needed.
5. **Fix the right authority producers:** do not use `roles("ADMIN")` when intending to grant `APP_ADMIN`; use `authorities("APP_ADMIN")` or a controlled mapper.
6. **Inspect literals:** `hasAuthority("ROLE_ADMIN")`, `@Secured("ROLE_ADMIN")`, and `ROLE_...` hierarchies will not change automatically.
7. **Multi-layer testing:** users with `APP_ADMIN`, only `ROLE_ADMIN`, no permissions, anonymous; test HTTP requests and proxied method calls.
8. **Manage the transition period:** old sessions/JWTs remain alive; choose refresh/revocation or a time-bounded migration so you neither lock out valid users nor retain broad permissions too long.
9. **Monitor after rollout:** 401/403 rates, newly appearing 403 behavior, role mapping audits, and cross-tenant/resource denials.

## 8. Common misconceptions and self-check questions

**Misconception 1 — "`GrantedAuthorityDefaults("APP_")` changes every already-granted `ROLE_ADMIN`."** False. The bean only supplies prefix configuration to compatible consumers; actual authorities remain as originally granted.

**Misconception 2 — "`hasRole("ADMIN")` is equivalent everywhere to `hasAuthority("APP_ADMIN")`."** Cannot be assumed without checking component/version; static `AuthorityAuthorizationManager.hasRole` still uses `ROLE_`.

**Misconception 3 — "`User.withUsername(...).roles("ADMIN")` will generate `APP_ADMIN`."** False. The builder prepends `ROLE_`.

**Misconception 4 — "OAuth2 scopes automatically switch prefix to match the role prefix."** False. The JWT converter has its own prefix, usually `SCOPE_`.

**Misconception 5 — "Testing `@WithMockUser(roles="ADMIN")` proves the custom prefix works."** False if the fixture grants `ROLE_ADMIN` while runtime policy demands `APP_ADMIN`.

**Self-check:**

1. `@PreAuthorize("hasRole('ADMIN')")` has prefix `APP_` actually active on the method. Which authority is required? **`APP_ADMIN`**.
2. Can an account with only `ROLE_ADMIN` pass the method rule above? **No**, absent an extra granting rule.
3. Is `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` rewritten to `APP_ADMIN`? **No**, because it is a literal.
4. Which authority does `AuthorityAuthorizationManager.hasRole("ADMIN")` check for? **`ROLE_ADMIN`** per the static factory contract.
5. Is the `roles("ADMIN")` user builder affected by the custom bean? **No**.
6. What should you pass to `@WithMockUser` to test the new method prefix rule? **`authorities = "APP_ADMIN"`**.
7. Why might HTTP allow access while the method still returns 403? The HTTP rule may check `APP_ADMIN`, while the method-security handler looks for another authority or the account holds an incompatible authority. Inspect **both consumers**.
8. Should you remove the prefix with an empty string? Only after auditing all policies, authority sources, and collision risks between role and permission names. An empty prefix can make the model harder to distinguish.

**Remember:** `GrantedAuthorityDefaults` changes **the role-interpretation convention in supporting components**. Always verify three things: **actual authorities in `Authentication`**, **the exact checking API**, and **the prefix/literal that API uses**.

## Official documentation

- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- `GrantedAuthorityDefaults` API: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/core/GrantedAuthorityDefaults.html
- `AuthorityAuthorizationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- `User.UserBuilder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- `Jsr250AuthorizationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html
