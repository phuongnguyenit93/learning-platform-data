# User, Principal, Credentials, Role, and Authority: Terminology Map

> **Context:** Spring Security in Servlet applications, using terminology and APIs common to Spring Security 6 / Spring Boot 3 (Java 17+). The goal of this lesson is to accurately read the meaning of each term when inspecting security configurations, handling login, and checking permissions.

## 1. Five Concepts Commonly Conflated

| Term | Answers the Question | Practical Meaning | Example |
| --- | --- | --- | --- |
| **User** | Who does the system know? | Business object representing a user in the database; can exist even when not logged in. Not required to be a Spring security class. | Record `id=42, username=lan, email=...` |
| **Principal** | Which identity is being presented/verified? | Identity attached to an `Authentication`. Its data type depends on the authentication mechanism: a username string, `UserDetails`, `Jwt`, `OAuth2User`, or a custom type. | `lan`'s `UserDetails` after login |
| **Credentials** | What proof is used to verify the identity? | Secret or proof artifact passed into the authentication process: password, Bearer token, etc. Not an access permission. | Password entered at login, access token sent with a request |
| **Role** | Which permission group does this person belong to? | High-level permission group name, commonly `ADMIN`, `USER`. By Spring Security's default convention, role `ADMIN` is usually represented as authority `ROLE_ADMIN`. | `ADMIN`, `SUPPORT` |
| **Authority** | What is this person allowed to do? | A specific permission/label, represented via `GrantedAuthority#getAuthority()`. Can be a prefixed role or a fine-grained business permission. | `ROLE_ADMIN`, `orders:read`, `reports:export` |

Two supporting objects to remember:

- **`Authentication`** is the Spring Security object describing an authentication request or authentication result: it contains `principal`, `credentials`, the list of `authorities`, and the `isAuthenticated()` status. It is not synonymous with the business user object.
- **`SecurityContext`** is where the current `Authentication` is held; in a normal Servlet flow, application code retrieves it via `SecurityContextHolder`. The context is bound to the request processing scope, not a global variable representing all users.

Short mnemonic: **user** is the business entity; **principal** is the identity seen by the security system; **credentials** prove the identity; **role** groups permissions; **authority** is the actual information matched against authorization rules.

## 2. Before and After Authentication: How Do Fields Change?

Example with username/password login:

1. The client sends username `lan` and password through a login mechanism/HTTP Basic over an HTTPS connection.
2. A Spring Security filter creates or forwards an *unauthenticated* `Authentication` object. At this point `principal` may just be the string `"lan"`, `credentials` is the received password, and `isAuthenticated() == false`.
3. `AuthenticationManager` delegates the request to an appropriate `AuthenticationProvider`. For accounts stored in the system, `DaoAuthenticationProvider` typically uses `UserDetailsService` to load login information and `PasswordEncoder.matches(rawPassword, storedPasswordHash)` to verify the password.
4. When valid, the resulting authenticated `Authentication` carries the identity (for example, a `UserDetails`) and granted `GrantedAuthority` instances. The provider/manager usually erases sensitive credentials when appropriate; **do not assume `getCredentials()` always still holds the password or is always `null` across all mechanisms**.
5. `Authentication` is placed into `SecurityContext`; subsequent authorization steps read the identity and authorities to decide whether to allow or deny the request.

Relationship diagram:

```text
HTTP request + credentials
         |
         v
Security Filter Chain
         |
         v
Authentication (unauthenticated: principal/credentials)
         |
         v
AuthenticationManager -> AuthenticationProvider
                            |-> UserDetailsService (if using internal accounts)
                            |-> PasswordEncoder (if using passwords)
         |
         v
Authentication (authenticated: principal + authorities)
         |
         v
SecurityContextHolder -> SecurityContext -> Authentication
         |
         v
Authorization (hasRole / hasAuthority / other rules)
         |
         v
Controller or HTTP 401/403
```

**Authentication** answers "who are you, and how were you verified?"; **authorization** answers "given the current identity/permissions, are you allowed to perform this action?". Successful authentication does not mean every endpoint is accessible.

In Servlet, Spring Security manages context lifecycle through the security filter chain. Context can be loaded/saved via `SecurityContextRepository` (such as HTTP session integration), or the system can authenticate a token on every request. Do not assume logging in once gives all subsequent requests the same context without understanding the session/token mechanism. With code that sets `Authentication` manually, saving context for later requests must also be handled properly per configuration; merely setting `SecurityContextHolder` does not guarantee session persistence.

## 3. Domain User, UserDetails, and Principal: Three Different Layers

An application might have a `users` table with `id`, `username`, `email`, `status`, `created_at`, along with group/permission tables. That is the **domain model**: serving business logic, data relationships, and user profiles.

During username/password authentication, Spring Security typically needs `UserDetailsService#loadUserByUsername(...)` to return a `UserDetails` providing username, encoded password, account status, and authorities. `org.springframework.security.core.userdetails.User` is a built-in implementation of `UserDetails`; it is **not by default the application's domain `User` entity**. You can write a custom `UserDetails` or map data from a domain entity to the security object.

After authentication, `Authentication#getPrincipal()` can be that `UserDetails`, though this depends on the provider. With a JWT resource server, the principal is often a `Jwt` or a type created by a converter; with OAuth2 login, it may be an `OAuth2User`. Therefore:

- `authentication.getName()` is suitable when you only need the identifier name under the current mechanism.
- `authentication.getPrincipal()` returns the identity object; only cast to `UserDetails` when certain the provider uses this type.
- `@AuthenticationPrincipal` in a controller extracts the `principal` from `Authentication`; the parameter type must match reality.
- `HttpServletRequest#getUserPrincipal()` refers to the Java `Principal` on the request; the object returned under Spring Security integration may be the `Authentication` itself. Do not confuse this object with the result of `Authentication#getPrincipal()`.

A locked domain user is still an existing user record. Whether they can authenticate depends on account status checks and the provider; whether they can access features also depends on authorization. Do not conflate those three states.

## 4. Role Is a Convention-Based Form of Authority

In Spring Security, `GrantedAuthority` typically provides a string via `getAuthority()`. The `hasAuthority("X")` rule matches authority `X` **exactly** (per the active checking policy). The `hasRole("ADMIN")` rule, under default configuration, looks for authority `ROLE_ADMIN`.

| Authorities on `Authentication` | Check | Default Result | Reason |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Allow | Spring prepends the `ROLE_` prefix when checking roles |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Allow | Exact authority string match |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Deny | `ADMIN` differs from `ROLE_ADMIN` |
| `orders:read` | `hasAuthority("orders:read")` | Allow | Exact business permission match |
| `ROLE_USER` | `hasRole("ADMIN")` | Deny | Missing `ROLE_ADMIN` |
| `ROLE_ADMIN` | `hasAuthority("orders:read")` | Deny | Role ADMIN does not automatically grant `orders:read` |

These results assume no `RoleHierarchy`, custom policy, or configuration changing the prefix. `ROLE_` is a **representation convention inside Spring Security**, not a mandatory rule for database role tables. If a role hierarchy is enabled, a higher-level authority can imply other permissions as configured; it is never the case that every ADMIN role automatically possesses all fine-grained authorities.

**Notes when building `UserDetails`:**

- `User.withUsername("lan").password(...).roles("ADMIN").build()` creates the authority `ROLE_ADMIN`.
- `User.withUsername("lan").password(...).authorities("ROLE_ADMIN", "orders:read").build()` sets both authorities directly, suitable when both roles and fine-grained permissions are needed.
- On the same `UserBuilder`, calling `.roles(...)` and then `.authorities(...)` sequentially is not a safe additive operation; the latter method can replace the previous list. Pass the final list of authorities explicitly or combine collections intentionally.
- When using `hasRole("ADMIN")`, pass `ADMIN` (do not pre-prepend `ROLE_` in the argument). When using `hasAuthority(...)`, pass the exact granted string.

Permission names like `orders:read` are an **application convention**, not built-in permissions automatically recognized by Spring Security. There must be a step to load/convert authorities from the database, token claims, or the corresponding identity source.

## 5. Runnable Servlet Example with Spring Boot 3 and Java 17+

The example uses HTTP Basic to make the boundaries between principal/credentials/permissions easy to observe. Prepare a **Spring Boot 3.x project** with Java 17+ and the two dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. Place three files under `src/main/java/demo/security/`. The following snippets are complete classes inside a project that already has Spring Boot build configuration; they cannot be compiled with plain `javac` without Spring dependencies.

**File `SecurityDemoApplication.java`:**

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

**File `SecurityConfig.java`:**

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/orders").hasAuthority("orders:read")
                .anyRequest().authenticated()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "orders:read")
                .build();

        UserDetails minh = User.withUsername("minh")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(lan, minh);
    }
}
```

**File `DemoController.java`:**

```java
package demo.security;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "admin report";
    }

    @GetMapping("/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "principalType",
                    authentication.getPrincipal().getClass().getSimpleName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList()
        );
    }
}
```

Run with `./gradlew bootRun` (or the run command of your configured Spring Boot project). The following verification commands are for a shell with `curl` while the application is running on the default port `8080`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
# 200

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/me
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/admin/report
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u minh:demo123 http://localhost:8080/admin/report
# 403

curl -s -o /dev/null -w '%{http_code}\n' -u lan:demo123 http://localhost:8080/orders
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u minh:demo123 http://localhost:8080/orders
# 403
```

Use `curl -u lan:demo123 http://localhost:8080/me` to inspect the authenticated information. With the sample configuration, `name` is `lan`, `principalType` is `User` (Spring Security's implementation), and `authorities` contains `ROLE_ADMIN` and `orders:read`. JSON key order is not a contract; the authorities list is sorted in the sample code.

Explanation:

- `lan` has **two authorities**: `ROLE_ADMIN` and `orders:read`; `minh` only has `ROLE_USER`.
- Spring creates/activates an `Authentication` object after HTTP Basic verifies username/password; the `/me` controller receives information about the logged-in request.
- `/admin/report` is checked by role (authority `ROLE_ADMIN`); `/orders` is checked by business permission `orders:read`.
- `/public` allows access without logging in; other URLs go through `authenticated()`.
- The value `demo123` and in-memory accounts are **for illustration only**. Real applications fetch identity data from a trusted source, store passwords as secure hashes, and manage secrets through dedicated processes. Do not return/log `credentials` in the `/me` endpoint.
- The example only uses GET; for state-changing operations through a browser, CSRF remains an independent verification layer. Do not conclude every 403 error is caused by a missing role.

## 6. Reading the Current User from Application Code

In a protected Servlet controller, accepting `Authentication` directly is a simple way to access the request's identity and permissions (like `/me` above). In other processing layers, you can read `SecurityContextHolder.getContext().getAuthentication()`, but you must account for the possibility of being unauthenticated or anonymous.

```java
// Illustrated inside a method running within the security filter chain.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String displayIdentity = authentication.getName();
    // Check anonymous/trust level further if business logic requires a real login.
}
```

The corresponding imports are `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. The snippet above is an **illustrative fragment**, not a standalone runnable Java class.

An `AnonymousAuthenticationToken` can exist in the context for unauthenticated guests, and **`isAuthenticated()` on that token itself can be `true`**. Therefore, do not treat `authentication != null && authentication.isAuthenticated()` as an absolute criterion that someone is truly logged in. In authorization configuration, use `.authenticated()`, `.anonymous()`, or the corresponding trust resolver/rules provided by Spring Security.

By default in Servlet, `SecurityContextHolder` uses a context bound to the processing thread. When spawning threads/async tasks manually, do not assume the security context automatically propagates to the new thread; use Spring-supported context propagation mechanisms when needed. Never store one request's `Authentication` in a static variable for reuse by another request.

## 7. URL Authorization and Method Authorization

The example's URL rules live in `SecurityFilterChain` and apply before controllers run. Place specific matchers before `anyRequest()` to avoid a catch-all rule shadowing detailed rules.

If a business operation can be called from multiple paths (HTTP, jobs, other services), you can add protection at the method layer using method security. You must enable method security before using `@PreAuthorize`:

```java
// Configuration fragment added to a @Configuration class:
@EnableMethodSecurity

// Fragment on a method of a Spring-managed bean:
@PreAuthorize("hasAuthority('orders:read')")
public OrderSummary viewOrders() {
    // business logic
}
```

These are **two fragments in different locations**, not a complete Java file; `OrderSummary` is merely an illustrative business type name. The corresponding annotations are `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity` and `org.springframework.security.access.prepost.PreAuthorize`. Method security generally relies on Spring AOP/proxies; direct internal calls within the same bean may bypass the proxy. Always test through the real call path.

## 8. Avoiding Confusing Authorization with Adjacent Concepts

- **Identity does not equal permission:** knowing `authentication.getName() == "lan"` does not allow inferring that the person has role ADMIN. Permissions must come from verified authorities or policies.
- **A password hash is not an authority:** the hash in `UserDetails#getPassword()` is data for verifying passwords, not for indicating what the account is allowed to do. For passwords, match with `PasswordEncoder.matches(raw, encoded)`, never compare raw strings.
- **A role does not implicitly contain permissions:** `ROLE_ADMIN` does not automatically satisfy `hasAuthority("orders:read")`; any linkage must be defined by the permission assignment/hierarchy/policy system.
- **Not every principal is `UserDetails`:** switching to JWT/OAuth2 can change the principal type; unchecked casting will lead to a `ClassCastException`.
- **Token authorities are not generated automatically to match app wishes:** `scope`, `roles`, and `permissions` claims must be converted to `GrantedAuthority` properly via a converter. For instance, the default JWT resource server typically converts scopes to `SCOPE_...`; that is not `ROLE_...` unless a mapping is configured.
- **HTTP 401 differs from 403:** 401 typically means a request lacks valid authentication and needs login/proof of identity; 403 means the request has an identity but is rejected by policy. Certain filters (such as CSRF) can also produce 403; inspect the filter chain and controlled logs before concluding.
- **Authorization data needs a trusted source:** do not take `role=ADMIN` from a query param/request body and turn it directly into a `GrantedAuthority`. Permissions must come from an authenticated source and the system's authorization mechanism.
- **Do not leak credentials:** use HTTPS, encode passwords with an appropriate encoder, avoid printing tokens/passwords into logs, metrics, URLs, or JSON responses; consider token and session lifecycle/revocation.
- **Test rejection paths too:** test admin permissions with regular users, auth-required endpoints with anonymous requests, fine-grained permissions with role-only users, and locked account cases.

## 9. Self-Check Exercises

1. An `Authentication` has `ROLE_USER` and `orders:read`. What do `hasRole("USER")`, `hasAuthority("orders:read")`, and `hasRole("ADMIN")` evaluate to respectively? **Answer:** allow, allow, deny (under default configuration).
2. `Authentication#getPrincipal()` returns a `Jwt` instead of `UserDetails`. Is this wrong? **No.** The principal depends on the authentication mechanism; identity-reading code must handle the appropriate type.
3. Why can `ROLE_ADMIN` pass `hasRole("ADMIN")` but fail `hasAuthority("orders:read")`? **Because** the two rules check different authorities, unless you configure an additional policy/hierarchy accordingly.
4. A user submits the correct password but gets 403 when accessing `/admin/report`. First check step? **Inspect the actual authorities on `Authentication` and the matchers/policy**; do not conclude a wrong password solely from 403.
5. Does `isAuthenticated() == true` guarantee a real user login session? **No.** An anonymous token can have that flag; use Spring Security's mechanism for distinguishing anonymous users.

## 10. Memory Map for Reading Code

```text
Domain User (business record)
   | maps/loads login details
   v
UserDetails (a data format for providers; not the only principal type)
   | combined with client-presented credentials
   v
AuthenticationManager/Provider -> Authentication
                                  | principal: who
                                  | credentials: proof (handled securely)
                                  | authorities: actual granted permissions
                                  v
                        SecurityContext (current request)
                                  |
                         hasRole / hasAuthority
                                  |
                            ALLOW or DENY
```

When encountering a "can log in but cannot access" error, follow this order: **check `principal` identity → actual `authorities` list → `hasRole/hasAuthority` rules → filter/method security path**. This sequence helps distinguish authentication errors, authority mapping errors, and authorization policy errors in Spring Security Servlet applications.