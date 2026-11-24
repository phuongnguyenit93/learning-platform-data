# permitAll, denyAll, authenticated, and Anonymous User Permissions in Spring Security Reactive

## 1. Lesson Objectives

When building REST APIs with Spring WebFlux and Spring Security, we must decide **which requests are publicly accessible, which requests require an authenticated identity, and which requests are always blocked**. The three fundamental rules in **ServerHttpSecurity.authorizeExchange(...)** are:

- **permitAll()** — allows everyone access if the request matches the rule, requiring no login.
- **denyAll()** — denies everyone, regardless of whether they are logged in or not.
- **authenticated()** — requires an identity recognized by Spring Security as authenticated, **not accepting anonymous**.

Beyond these three rules, there is an easily misunderstood concept: **anonymous user**. In certain configurations, Spring Security can create an **AnonymousAuthenticationToken** and place it in the Reactor Context. The purpose is to represent an unauthenticated caller with an Authentication object, **not to verify a real identity**.

After this lesson, you will:

1. Distinguish **public**, **anonymous**, **authenticated**, and **authorized**.
2. Write WebFlux rules with **pathMatchers**, **anyExchange**, **permitAll**, **denyAll**, and **authenticated**.
3. Understand **matcher ordering** and the deny-by-default principle.
4. Know when an anonymous Authentication exists, how to enable it explicitly in WebFlux, and why **isAuthenticated()** does not mean "the user is logged in".
5. Understand **401** and **403** in cases of missing credentials, wrong credentials, and insufficient permissions.
6. Build a runnable **Java 17+ / Spring Boot WebFlux** demo with HTTP Basic, a public page, a login-required API, an admin API, a closed endpoint, and an anonymous-only endpoint.
7. Write **WebTestClient** tests to confirm actual behavior rather than merely reading configuration and guessing.

**Core rule:** allow only the defined public URLs, require login for private areas, check permissions for privileged areas, and end with a **denyAll()** policy for the rest if that matches the product's intent.

## 2. How Does Authentication Differ from Authorization?

There are three distinct questions:

1. **Who is calling?** Authentication identifies the principal after the password/token is verified.
2. **Are they allowed to enter the endpoint?** Authorization compares the Authentication against the URL policy.
3. **Are they allowed to read/modify a specific resource?** Check owner, tenant, and business permissions in the service/repository.

For example: `alice` has `ROLE_USER` and is logged in. The **authenticated()** rule allows her to call `GET /api/me`. However, calling `GET /api/admin/report` requires **hasRole("ADMIN")**, and reading order 42 must additionally check ownership.

| Term | Meaning | Example |
| --- | --- | --- |
| **Unauthenticated** | No valid proof of identity yet | No `Authorization` header sent |
| **Anonymous** | Technical representation for a caller who has not logged in | `AnonymousAuthenticationToken` |
| **Authenticated** | Spring Security recognizes an identity from a trusted authentication mechanism | `alice` authenticated via HTTP Basic |
| **Authorized** | Permitted by policy for the requested operation | Alice viewing her own profile |
| **Principal** | Object representing the identity | `alice` or `guest` |
| **GrantedAuthority** | Specific permission held by the Authentication | `ROLE_USER`, `ROLE_ADMIN` |

Remember that **the existence of an Authentication** does not mean **authenticated()** will approve; an `AnonymousAuthenticationToken` is also an `Authentication`. In Spring Security, authorization managers rely on the concept of trust/anonymous rather than simply checking the token's boolean flag.

## 3. Three Key Rules

### 3.1. permitAll(): Public, Yet Still Inside the Security Chain

Example:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
~~~

Every request matching `/public/**` is allowed to **pass this URL authorization step** even without an account. That does not mean:

- Bypassing all security WebFilters.
- Disabling CSRF for write methods.
- Disabling authentication filters, CORS, rate limiting, or custom filters.
- Bypassing method security such as `@PreAuthorize` if the invoked method has its own rules.
- Guaranteeing the controller has no business errors.

For instance, **GET /public/ping without headers** returns 200 per the controller. However, if the caller sends **Authorization: Basic ...** with a wrong password, the authentication filter may process that header and return 401 even though the URL is marked `permitAll`. **permitAll is not "skip authentication mechanisms"**.

For an endpoint with public data that needs personalization, you can read the name if a valid Authentication is present; when there is no identity, return public content. Never escalate privileges on fallback.

### 3.2. denyAll(): Block Regardless of Identity

~~~java
.pathMatchers("/maintenance/**").denyAll()
~~~

Requests matching the rule are denied whether the caller is not logged in, a regular user, or an admin. Especially useful for:

- Deprecated APIs or routes not meant to be exposed.
- Branches not yet approved to open.
- Default policy for unlisted URLs.
- Endpoints needing a temporary lock at the authorization layer.

**denyAll does not mean 404 or guarantee "the route does not exist".** The status is usually 401 if the caller has no accepted identity, or 403 if logged in but denied, depending on the entry point and error handler. What matters is **never returning 2xx and never returning sensitive data**.

Putting `denyAll` on a URL branch never meant to be open does not replace removing controllers/debug endpoints, disabling feature flags, checking the gateway, and protecting underlying backend services.

### 3.3. authenticated(): Logged In, But Not Automatically Authorized for Everything

~~~java
.pathMatchers("/api/**").authenticated()
~~~

The condition is that the caller is considered **authenticated** by Spring Security, not anonymous. However, `authenticated()` **does not require `ROLE_USER`, `ROLE_ADMIN`, a specific tenant, or ownership**.

- No credentials sent → fails the rule.
- Wrong credentials sent → authentication fails, fails the rule.
- Valid regular user credentials sent → passes the rule.
- Valid admin credentials sent → passes the rule.
- `AnonymousAuthenticationToken` → **fails the rule**.

If `/api/orders/{id}` uses `authenticated()`, any logged-in user can pass the URL gate. The service must still restrict records by owner/tenant to prevent **IDOR/BOLA**.

### 3.4. Configuration Comparison

| Rule | Unauthenticated Caller | Anonymous Token | Logged-in User | Logged-in Admin |
| --- | --- | --- | --- | --- |
| **permitAll()** | Allowed | Allowed | Allowed | Allowed |
| **authenticated()** | Denied | Denied | Allowed | Allowed |
| **denyAll()** | Denied | Denied | Denied | Denied |
| **hasRole("ADMIN")** | Denied | Denied | Denied if lacking `ROLE_ADMIN` | Allowed if having `ROLE_ADMIN` |
| **Custom anonymous-only check** | May pass if anonymous representation exists | Allowed | Denied | Denied |

"Allowed" means **permitted past the URL authorization step**, not guaranteeing a 200 response because controllers, method security, or other layers can still deny it.

## 4. Anonymous in WebFlux: Details Easy to Get Wrong

### 4.1. Is AnonymousAuthenticationToken a Real Login?

**No.** It is an `Authentication` type created by the framework to represent an unauthenticated caller within the security context. If anonymous support is enabled, **AnonymousAuthenticationWebFilter** detects that there is no `Authentication` in `ReactiveSecurityContextHolder` and adds an anonymous `Authentication`.

According to the Javadoc of `AnonymousAuthenticationWebFilter`, the default configuration when using the constructor taking a key creates:

- **principal**: `anonymousUser`.
- **authority**: `ROLE_ANONYMOUS`.

The principal/authorities can be customized via **ServerHttpSecurity.anonymous(...)**.

Important: **AnonymousAuthenticationToken.isAuthenticated() can return true** because this object is pre-created in an "authenticated" state per the token contract. That only describes the object inside Spring Security, **not proof that a real person passed login**.

~~~java
// Illustrative Java test example, not authentication from a request.
AnonymousAuthenticationToken guest =
        new AnonymousAuthenticationToken(
                "test-key",
                "guest",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

boolean tokenFlag = guest.isAuthenticated(); // true
~~~

Therefore, the following approach is unsafe if you want to check "logged in":

~~~java
// Wrong when used alone to exclude anonymous:
if (authentication != null && authentication.isAuthenticated()) {
    // grant access to all private data
}
~~~

Instead, prefer **.authenticated()** in the DSL, **AuthenticationTrustResolver** when you must write Java logic, and object-level permission checks in the service.

### 4.2. Anonymous Is Not Enabled by Default per WebFlux Javadoc

The Javadoc for **ServerHttpSecurity.anonymous(...)** in the Spring Security 6.5 branch states that anonymous authentication is **disabled by default**. Therefore, **do not assume every public request always has an `AnonymousAuthenticationToken`** in the Reactor Context.

A **permitAll()** endpoint is still accessible **without** an anonymous token; the public accessibility of a URL comes from the `permitAll` rule, **not depending on whether an anonymous token exists**.

In the demo, we **enable anonymous explicitly**:

~~~java
.anonymous(anon -> anon
        .principal("guest")
        .authorities("ROLE_ANONYMOUS"))
~~~

When a request without an `Authentication` passes through the anonymous filter in this chain, the Reactor Context can contain principal `guest` with `ROLE_ANONYMOUS`. If already authenticated via HTTP Basic, the filter must not overwrite the verified identity with `guest`.

Do not call **anonymous.disable()** as a method to protect private endpoints. Accessibility is determined by **authorization rules**; disabling anonymous only changes how unauthenticated callers are represented.

### 4.3. What Can ROLE_ANONYMOUS Be Used For?

The anonymous authority can help express a separate policy, such as a guide page for unauthenticated users. However:

- **ROLE_ANONYMOUS is not proof that an account exists**.
- Do not use it to allow viewing private data.
- Checking only the `ROLE_ANONYMOUS` authority string does not guarantee the caller is actually anonymous if a custom `Authentication` was mistakenly granted that authority.
- When you truly need "unauthenticated users only", use **AuthenticationTrustResolver.isAnonymous(...)** or a suitable `ReactiveAuthorizationManager`.

In multi-role applications, sometimes `permitAll` is all you need, rendering a `"guest"`/`"alice"` greeting based on the existing `Authentication`. There is no need to create an anonymous-only endpoint unless the product requires it.

### 4.4. Anonymous Does Not Mean Unauthenticated in the Same Way

Cases:

| State | Has SecurityContext? | Has Authentication? | Passes `authenticated()`? |
| --- | --- | --- | --- |
| No context | No | No | No |
| Context with null Authentication | Yes | No | No |
| Anonymous support enabled and no login | Yes (created by filter) | `AnonymousAuthenticationToken` | **No** |
| User authenticated via HTTP Basic | Yes | Trusted `Authentication` | **Yes** |

A handler using `Mono<Principal>` may behave differently from directly reading `ReactiveSecurityContextHolder`, depending on the resolver/chain. If you want to inspect the anonymous object, read the **Reactor Context** inside a publisher subscribed by the framework; do not assume every controller `Principal` argument will always receive `guest`.

## 5. authorizeExchange Order: Specific Rules Before Broad Rules

Good example:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Matchers are evaluated in the configured order: the first matching rule selects the authorization manager for the request.**

If reversed:

~~~java
// WRONG if you want to restrict /api/admin/** specifically:
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Then `/api/admin/report` can match `/api/**` first, causing the subsequent `hasRole("ADMIN")` rule never to be used. Someone who is merely logged in can enter the admin endpoint.

**Ordering checklist:**

1. **Specific and intentional** public path rules.
2. Special deny rules, if any.
3. Admin/role/scope rules on sensitive paths.
4. `authenticated` rule for broad branches.
5. **anyExchange().denyAll()** last for a fail-closed default.

Defaulting to **anyExchange().authenticated()** is also an option when all remaining paths are expected to require login; however, if you want new endpoints not to automatically open to every logged-in user, **denyAll** is safer.

Also remember that **securityMatcher** selects the **SecurityWebFilterChain** before `pathMatchers` inside the chain are evaluated. In a multi-chain application, Spring Security selects a matching chain in order: **a `permitAll` in one chain does not pass the request through other chains to accumulate rules**.

## 6. Distinguishing 401 and 403

**401 Unauthorized** indicates there is no valid authentication proof or credentials were rejected; with HTTP Basic, the response usually carries **WWW-Authenticate: Basic realm="..."**.

**403 Forbidden** usually indicates the caller is authenticated, but the policy does not grant permission. Even if the user has `ROLE_ADMIN`, `denyAll` still forbids access and can return 403.

| Request with HTTP Basic | Policy | Typical Result |
| --- | --- | --- |
| GET `/public/ping` no header | permitAll | 200 |
| GET `/api/profile` no header | authenticated | 401 |
| GET `/api/profile` wrong password | authenticated | 401 |
| GET `/api/profile` valid user | authenticated | 200 |
| GET `/api/admin/dashboard` user with only `ROLE_USER` | hasRole ADMIN | 403 |
| GET `/api/admin/dashboard` admin | hasRole ADMIN | 200 |
| GET `/maintenance/flag` authenticated user | denyAll | 403 |
| GET `/maintenance/flag` unauthenticated | denyAll | Usually 401 with Basic entry point |
| GET `/guest-only` not logged in, anonymous enabled | Anonymous-only policy | 200 |
| GET `/guest-only` logged-in user | Anonymous-only policy | 403 |

Exact status codes also depend on **ServerAuthenticationEntryPoint**, **ServerAccessDeniedHandler**, chains, and authentication mechanisms. From a security standpoint, a `denyAll` case must never return protected data, regardless of how custom JSON status responses are formatted.

Do not use **permitAll** to dodge credential errors, do not use **denyAll** to "hide" a resource's existence completely, and do not let an anonymous token pass **authenticated()** just because `token.isAuthenticated()` is `true`.

## 7. Runnable Java 17+ Demo: WebFlux + HTTP Basic + Custom Anonymous

The demo uses **Spring Boot 3.5.16**, Java 17+, Gradle 8.4+ (e.g., Gradle 8.14), and reactive Spring Security managed by Spring Boot.

**Version lifecycle note:** Spring Boot 3.5.16 is the final OSS release of the 3.5 line; when building new production systems, choose a branch that still receives OSS patches or commercial support, and do not pin old libraries arbitrarily. Here the version is pinned so the example has deterministic dependencies.

Routes:

| Path | Security Intent |
| --- | --- |
| GET `/public/ping` | Public |
| GET `/public/whoami` | Public and safely reports the context principal name |
| GET `/api/profile` | Must be logged in |
| GET `/api/admin/dashboard` | Must have `ROLE_ADMIN` |
| GET `/maintenance/flag` | Nobody allowed |
| GET `/guest-only` | Anonymous only, demonstrating a custom `ReactiveAuthorizationManager` |
| Other paths | `denyAll` |

Demo accounts:

- `alice` / `alice-pass` has **ROLE_USER**.
- `admin` / `admin-pass` has **ROLE_USER**, **ROLE_ADMIN**.

### 7.1. File Structure

~~~text
webflux-authorization-basics/
├── settings.gradle
├── build.gradle
├── src/main/java/example/access/AccessApplication.java
├── src/main/java/example/access/SecurityConfig.java
├── src/main/java/example/access/AccessController.java
└── src/test/java/example/access/AccessPolicyTest.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-authorization-basics'
~~~

### 7.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Only use the WebFlux starter; **do not** add `spring-boot-starter-web` at the same time—the goal is to observe the exact `SecurityWebFilterChain` of the reactive stack.

### 7.4. AccessApplication.java

~~~java
package example.access;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.access;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        return http
                // Explicitly enable anonymous instead of relying on default assumptions.
                .anonymous(anonymous -> anonymous
                        .principal("guest")
                        .authorities("ROLE_ANONYMOUS"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/public/whoami")
                            .permitAll()
                        .pathMatchers("/maintenance/**").denyAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        // The WebFlux DSL does not have an anonymous() method directly
                        // on Access like permitAll/authenticated.
                        .pathMatchers("/guest-only").access(
                                (authentication, context) ->
                                        authentication
                                                .map(trustResolver::isAnonymous)
                                                .map(AuthorizationDecision::new)
                                                .defaultIfEmpty(
                                                        new AuthorizationDecision(
                                                                false)))
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Explanation:**

1. **anonymous(...)** creates a `guest` / `ROLE_ANONYMOUS` representation when no `Authentication` is present. If authentication succeeded, `guest` does not replace `alice`/`admin`.
2. **permitAll()** opens the two public routes; it does not disable Spring Security.
3. **denyAll()** blocks the maintenance route even for `admin`.
4. **hasRole("ADMIN")** runs before **authenticated()** on `/api/**`; thus `ROLE_USER` cannot access the admin endpoint.
5. **authenticated()** blocks anonymous callers and anyone without valid credentials.
6. **guest-only.access(...)** uses a `ReactiveAuthorizationManager`; `AuthenticationTrustResolver` knows how to distinguish an anonymous token. **Mono.empty() is treated as deny** via `defaultIfEmpty(false)` to fail closed.
7. **anyExchange().denyAll()** prevents accidentally opening new URLs.
8. **httpBasic** validates credentials via HTTP Basic; the demo avoids form/session login to prevent redirect side effects.

**Optional imports:** `AnonymousAuthenticationToken` and `Mono` appear in conceptual illustrations elsewhere in the lesson and are not needed in `SecurityConfig.java`; in Java, unused imports are only style warnings, not compilation errors. You can remove these two imports if your IDE enforces clean code.

**Why not just use `hasAuthority("ROLE_ANONYMOUS")`?** Because an authority is a string granted to an `Authentication`. If an application is misconfigured and also grants `ROLE_ANONYMOUS` to an authenticated user, checking the authority string can cause confusion. `TrustResolver` checks the true **anonymous status of the Authentication**, which is a better fit for an "unauthenticated users only" policy. In systems without a guest-only requirement, **permitAll** is the simpler and clearer choice.

### 7.6. AccessController.java

~~~java
package example.access;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AccessController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/public/whoami")
    public Mono<Map<String, String>> whoami() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .map(auth -> Map.of(
                        "name", auth.getName(),
                        "kind", auth instanceof AnonymousAuthenticationToken
                                ? "ANONYMOUS" : "AUTHENTICATED"))
                .defaultIfEmpty(Map.of(
                        "name", "none",
                        "kind", "MISSING"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p -> Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("dashboard", "admin"));
    }

    @GetMapping("/maintenance/flag")
    public Mono<Map<String, String>> disabled() {
        return Mono.just(Map.of("flag", "hidden"));
    }

    @GetMapping("/guest-only")
    public Mono<Map<String, String>> guestOnly() {
        return Mono.just(Map.of("mode", "guest"));
    }
}
~~~

Even though the controller has a `disabled()` method, the `denyAll` rule prevents the `/maintenance/flag` handler from returning data for requests matching the chain. **Do not** treat the existence of a controller as proof that an API is open.

The `/public/whoami` endpoint intentionally returns a **simple** name and identity kind, rather than exposing the entire `Authentication` or principal. In real applications, never return password hashes, tokens, or arbitrary `SecurityContext` contents to clients.

### 7.7. Starting Up

Requires Java 17+, a compatible Gradle version, and Maven Central access:

~~~bash
gradle bootRun
~~~

Unless the port is changed, the application listens on **http://localhost:8080**. Use HTTP localhost for learning; in production, use HTTPS, real password management, and an appropriate identity store policy.

## 8. Using curl to Observe the Rules

Run in a Bash terminal separate from the one running Gradle:

~~~bash
# Public, no header needed.
curl -s http://localhost:8080/public/ping
# {"status":"ok"}

# Anonymous is enabled and represented as guest.
curl -s http://localhost:8080/public/whoami
# {"name":"guest","kind":"ANONYMOUS"}
# (JSON key order is not a contract)

# Public, but a request with valid Basic credentials sees the real user.
curl -s -u alice:alice-pass http://localhost:8080/public/whoami
# {"name":"alice","kind":"AUTHENTICATED"}

# Login-required API, request without credentials.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile
# 401

# Wrong password.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:wrong-pass http://localhost:8080/api/profile
# 401

# Valid regular user.
curl -s -u alice:alice-pass http://localhost:8080/api/profile
# {"username":"alice"}

# User with only ROLE_USER cannot access admin.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/api/admin/dashboard
# 403

# Admin with sufficient permissions.
curl -s -u admin:admin-pass http://localhost:8080/api/admin/dashboard
# {"dashboard":"admin"}

# Even admin is blocked by denyAll.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/maintenance/flag
# 403

# Guest-only allows only anonymous.
curl -s http://localhost:8080/guest-only
# {"mode":"guest"}

curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/guest-only
# 403
~~~

**Explanation:** lines after `#` are expected output, not commands. For JSON `Map`s, key order on the wire is not a contract: clients should compare JSON field values rather than comparing raw strings when multiple fields exist.

On PowerShell, use **curl.exe** and write each command on a single line, because the Bash line continuation symbol **\\** is not used the same way in PowerShell.

An intentional scenario not shown above: a request to `/public/ping` carrying **invalid** `Authorization Basic` credentials may receive 401 from the authentication filter even though the URL is `permitAll`. That does not change the meaning of `permitAll`; it shows that authentication and authorization are two distinct steps in the same security chain. Write separate tests if the application requires a specific policy for bad credentials on public URLs.

## 9. Testing with WebTestClient

The focus of the lesson is **testing real policies over HTTP**, not merely verifying that a `SecurityWebFilterChain` method compiles. Tests run alongside the application without needing a separate server on port 8080.

File **src/test/java/example/access/AccessPolicyTest.java**:

~~~java
package example.access;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccessPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void anonymousRepresentationIsNotARealLogin() {
        client.get().uri("/public/whoami")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("guest")
                .jsonPath("$.kind").isEqualTo("ANONYMOUS");

        AnonymousAuthenticationToken token =
                new AnonymousAuthenticationToken(
                        "unit-test-key",
                        "guest",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_ANONYMOUS")));
        assertTrue(token.isAuthenticated());
    }

    @Test
    void authenticatedRejectsAnonymousAndInvalidPassword() {
        client.get().uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aValidUserCanOpenAuthenticatedRoute() {
        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void roleBasedAdminPolicyRunsBeforeBroadAuthenticatedRule() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.dashboard").isEqualTo("admin");
    }

    @Test
    void denyAllBlocksEvenAnAdmin() {
        client.get().uri("/maintenance/flag")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void guestOnlyDeniesLoggedInUser() {
        client.get().uri("/guest-only")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("guest");

        client.get().uri("/guest-only")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownPathIsNotOpenedByDefault() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** eight tests PASS and Gradle reports BUILD SUCCESSFUL when the application and dependencies are compatible. These tests use a real Spring context, verifying the `WebFilter` chain and authorization, though they are not proof of external proxy/gateway/ingress policies.

**Why can the anonymous token test have `isAuthenticated=true` while `/api/profile` still returns 401?** Because the `authenticated()` authorization rule is built on Spring Security's trust-state distinction and does not treat `AnonymousAuthenticationToken` as a valid login.

**Why not test `denyAll` with "any 4xx status"?** With Basic and the demo's default handler, a denied authenticated user should receive 403. The test's goal is catching regressions: `denyAll` must never accidentally turn into `permitAll`.

## 10. When Multiple SecurityWebFilterChains Coexist

In a WebFlux application, there can be two chains:

~~~text
SecurityWebFilterChain 1 (high priority) -> securityMatcher("/api/**")
    -> API authorizeExchange rules
    -> corresponding HTTP Basic / JWT

SecurityWebFilterChain 2 (low priority) -> matcher for the rest
    -> form login or web policy
~~~

**A request uses the chain selected by matcher/order; it does not run through all chains sequentially to accumulate rules.** Therefore:

- A **permitAll** in the API chain says nothing about URLs belonging only to the web chain.
- An **anyExchange().denyAll()** applies to requests **that entered the chain containing that rule**, not every request across all chains.
- The **@Order** across multiple `SecurityWebFilterChain` beans is a separate axis from the order of `pathMatchers` inside one chain.
- Tests must know which chain a request matches. An overly broad public chain can override the entire policy of an API chain defined after it.

If multiple authentication mechanisms are not required, start with **one clear chain**. Avoid adding complexity until there is a meaningful authentication/URL boundary.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Placing `/api/**.authenticated` before `/api/admin/**.hasRole` | Regular users can pass the admin rule | Specific rules before broad rules |
| Making all URLs **permitAll** for debugging | Bypasses URL authorization | Only make intentional paths public, deny the rest |
| Setting all URLs to **authenticated** and assuming personal data is safe | Any user can try reading another user's resources | Check owner/tenant in service/repository |
| Thinking `denyAll` automatically returns HTTP 404 | Confuses denial with status/obfuscation | Test status, ensure no data is returned |
| Assuming anonymous always exists by default | Reactive Context may be empty | Enable explicitly via `.anonymous(...)` if needed |
| Using `isAuthenticated()` to treat an anonymous token as a real login | Anonymous token can return `true` | DSL `authenticated()` / `AuthenticationTrustResolver` |
| Using `hasAuthority("ROLE_ANONYMOUS")` as the sole check for guest-only | Risk that a custom user was granted that authority string | Check token type / trust resolver |
| Thinking `permitAll` skips security filters | Bad credentials can still be rejected by filters | Separate authentication from authorization |
| Disabling CSRF or CORS carelessly when opening public endpoints | Risk when browsers send cookies automatically | Configure according to credential type, origin, HTTP method |
| Using `NOOP` `PasswordEncoder` for convenience | Passwords stored in plaintext and leak risk | BCrypt / appropriate algorithm |
| Returning the raw `Authentication` in JSON | Leaks principal/credentials/metadata | Map to a DTO with public fields only |
| Adding method security and thinking `permitAll` bypasses it | Method may still deny | Test both URL and service thoroughly |
| Using Servlet-style `ThreadLocal` `SecurityContextHolder` in WebFlux | Wrong context when threads switch | `ReactiveSecurityContextHolder` |
| Missing `anyExchange` fallback | Undecided routes | `denyAll` or explicit `authenticated` per product |
| Testing only in a browser with an active session | Confuses logged-in user with guest | Use separate cookie jar / HTTP client |
| Not testing requests with bad Basic credentials on public URLs | Unexpected 401 responses | Add tests matching auth-filter policy |

## 12. Designing Anonymous Permissions to Fit Real Needs

Most applications only need:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/catalog", "/help").permitAll()
        .pathMatchers("/account/**").authenticated()
        .anyExchange().denyAll())
~~~

In this setup:
- **Guests** can view the catalog/help pages.
- **Logged-in users** can also view public content and access account pages.
- **AnonymousAuthenticationToken** is not a prerequisite for `permitAll` to work.

If you want "only guests can visit the registration intro page", consider UX: returning 403 to logged-in users is not always desirable. Usually redirecting or returning a different status view is friendlier. Only use a guest-only manager like the demo when the policy genuinely requires denying all logged-in users.

If anonymous users need to call an API to view sample data, grant access to **public sample data** via `permitAll` or a restricted read-only policy; do not share the same repository query for private data and impersonate a shared privileged account.

Another example requirement: guest shopping cart. A guest cart cookie should use a session/token separate from authenticated accounts, with proper ownership checks when merging carts. **ROLE_ANONYMOUS is not a password** and cannot replace per-guest cart identification mechanisms.

## 13. Exercises and Self-Check Questions

1. What is the fundamental difference between `permitAll()`, `denyAll()`, and `authenticated()`?
2. Why must `/api/admin/**.hasRole("ADMIN")` be placed before `/api/**.authenticated()`?
3. Will a public request carrying wrong Basic credentials definitely return 200? Why or why not?
4. Why can `AnonymousAuthenticationToken.isAuthenticated()` be `true` while `authenticated()` still denies it?
5. Per the `ServerHttpSecurity` 6.5 Javadoc, should you assume anonymous is enabled by default?
6. Why is `ROLE_ANONYMOUS` not proof that the caller owns an account?
7. If logged-in user `alice` calls `/maintenance/flag`, does `denyAll` permit it?
8. When `denyAll` denies an anonymous request, must the HTTP status always be 403?
9. If an app has multiple `SecurityWebFilterChain` beans, can chain A's `anyExchange().denyAll()` block a URL belonging only to chain B?
10. Can a user who passed `authenticated()` read another user's orders?
11. For a URL that only displays general content, should you use `permitAll` or create an anonymous-only policy?
12. How should you test to detect newly added endpoints that were accidentally left open?

**Suggested Answers:**

1. `permitAll` allows public access, `denyAll` denies all requests, and `authenticated` requires a trusted identity.
2. The first matching rule is used; placing a broad rule first shadows specific rules.
3. Not necessarily; the authentication filter can still process invalid credentials and return 401.
4. An anonymous token is a technical representation; the trust resolver distinguishes anonymous from a real login.
5. No; when an anonymous representation is needed, enable it explicitly via `anonymous(...)`.
6. `ROLE_ANONYMOUS` is merely an authority representing a guest, not evidence of a verified principal.
7. No; `denyAll` denies even admins.
8. No; the entry point may return 401 for unauthenticated callers.
9. No; requests only enter the chain selected by matcher/order.
10. Not automatically; permissions must be checked on owner/tenant/record.
11. Usually use `permitAll` for public content.
12. Write tests for unknown paths using both a logged-in user and an unauthenticated client, ensuring no sensitive data is returned.

## 14. Reference Documentation

- Spring Security Javadoc 6.5 — ServerHttpSecurity: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — AuthorizeExchangeSpec.Access: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security Javadoc — ServerHttpSecurity.AnonymousSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AnonymousSpec.html
- Spring Security Javadoc — AnonymousAuthenticationWebFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AnonymousAuthenticationWebFilter.html
- Spring Security Javadoc — AuthenticationTrustResolver: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Conclusion:** **permitAll** opens public access at the URL layer; **denyAll** blocks all matching requests; **authenticated** requires an `Authentication` recognized by Spring Security as a real login, rejecting anonymous. Anonymous users may be represented by `AnonymousAuthenticationToken` but are not verified identities. Enable anonymous intentionally when needed, order matchers from specific to general, use **anyExchange().denyAll()** as the endpoint when appropriate, and check owner/tenant at the business layer.