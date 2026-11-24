# Prefer Built-in Configuration Before Writing Custom Security Components

## 1. Core Idea

Spring Security is a framework that provides built-in **protection mechanisms, extension strategies, and a DSL to compose them into a configuration**. When a new requirement arises, the first question should be: **Does Spring Security already have a filter, provider, handler, or configuration option that solves this requirement?** Only create a new component when standard configuration and small extension points cannot satisfy the business behavior.

This is an especially important principle in the **Extension Points** topic: knowing how to extend does not mean you must extend. Writing your own `Filter`, parsing JWTs manually, managing sessions yourself, or implementing a custom login flow often brings along responsibilities for filter ordering, exceptions, CSRF protection, session fixation, responses, logging, and security updates that the framework already handles.

**Learning objectives:** identify security needs; choose the right DSL or standard component; distinguish between configuring, swapping a strategy, and writing a new mechanism; understand a runnable sample application; know when a separate `SecurityFilterChain`, `AuthenticationProvider`, `AuthorizationManager`, or custom filter is needed; and evaluate risks before building your own.

The primary runnable example scope is **Spring MVC/Servlet with Java 17 and Spring Boot 3.5.7 (Spring Security 6.x)**. The final section specifies the corresponding configuration names for **WebFlux/reactive**. API syntax can differ across version branches, so for real-world implementation you should use the documentation for the exact version managed by the Spring Boot BOM.

## 2. Understanding the Three Levels of Intervention

| Level | What to do | Examples | Priority |
| --- | --- | --- | --- |
| **1. Use built-in configuration** | Declare policies and enable existing mechanisms | `authorizeHttpRequests`, `httpBasic`, `formLogin`, `oauth2ResourceServer`, `csrf` | Try this first |
| **2. Plug a strategy into an extension point** | Replace the exact component that the framework actively invokes | `UserDetailsService`, `PasswordEncoder`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, `JwtAuthenticationConverter` | When default configuration is not enough |
| **3. Write a new mechanism** | Create a new provider, manager, handler, or filter, defining its contract and position | Custom `AuthenticationProvider`, `OncePerRequestFilter` | Only when a specific requirement is not solved by standard APIs |

The difference: level 1 changes **rules**, level 2 swaps **a strategy**, and level 3 adds **a processing mechanism**. When you only need to change `/admin` from "authenticated" to "requires ADMIN", there is no reason to write an extra filter. When storing users in a database, replacing `UserDetailsService` is usually enough; there is no need to write your own `UsernamePasswordAuthenticationFilter`.

A concise way to picture this:

```text
New security requirement
        |
        v
Can it be expressed with HttpSecurity / ServerHttpSecurity DSL?
        | Yes -> configure DSL -> test
        | No
        v
Is there a suitable standard component and small extension point?
        | Yes -> configure that component -> test
        | No
        v
Define contract, position, error flow, and tests
for the custom mechanism before implementing
```

## 3. Standard Capability Lookup by Requirement

| Need | Choose built-in tool first | Avoid writing yourself right away |
| --- | --- | --- |
| URL authorization by role or HTTP method | `authorizeHttpRequests`, `requestMatchers`, `hasRole`, `hasAuthority`, `access` | Custom filter matching URLs and returning 403 |
| Permissions on service methods | `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` | Adding repeated authorization logic in every controller |
| Login form for browsers | `formLogin` | Custom servlet checking passwords and managing sessions |
| Simple username/password API | `httpBasic` (when appropriate for the requirement, over HTTPS) | Custom filter reading, decoding, and checking the Basic header |
| Accounts from a database | `UserDetailsService` + `PasswordEncoder` + standard provider | Building a custom authentication pipeline just to query the user table |
| Login via OAuth2/OIDC | `oauth2Login` + OAuth2 Client | Handling state, redirects, code exchange, and token validation yourself |
| API accepting Bearer JWT | `oauth2ResourceServer(o -> o.jwt(...))` + `issuer-uri` / `JwtDecoder` | Splitting the JWT string, decoding, and trusting claims yourself |
| API accepting opaque token | Resource Server `opaqueToken` / introspection | Calling the introspection endpoint yourself inside a filter |
| 401, 403, redirect when unauthenticated | `exceptionHandling`, `AuthenticationEntryPoint`, `AccessDeniedHandler` | Catching all exceptions yourself at the start of the chain |
| CSRF protection, security headers | `csrf`, `headers`, and standard configuration | Implementing CSRF tokens yourself or disabling all protection |
| CORS for browser clients | `cors` + `CorsConfigurationSource` / Spring MVC CORS | Custom filter returning `Access-Control-*` headers |
| Session policy, logout, request cache | `sessionManagement`, `logout`, `requestCache` | Manual session management |
| Multiple URL regions with independent policies | Multiple `SecurityFilterChain` beans with `securityMatcher` and `@Order` | One giant filter branching on every path |
| Running WebFlux | `SecurityWebFilterChain` + `ServerHttpSecurity` | Using servlet filters in a reactive pipeline |

**Choosing a mechanism by system architecture:**

- Web applications serving HTML and using sessions: typically start with `formLogin`, CSRF protection for state-changing operations, and URL/method policies.
- APIs called only by clients with valid credentials: consider `httpBasic` or, commonly in systems with an identity provider, `oauth2ResourceServer`; design according to the actual protocol.
- OAuth2 APIs validating access tokens: use **Resource Server**, not `oauth2Login` merely because the token has "OAuth2" in its name. `oauth2Login` handles user login via a provider; Resource Server validates Bearer tokens sent to an API.
- A system with both web sessions and REST APIs: evaluate declaring multiple `SecurityFilterChain` beans before adding a custom filter to detect request types.

**Note:** built-in components still need to be configured properly. Do not assume that "having the Spring Security dependency" means endpoints, issuer, CSRF/CORS, and roles already match your requirements.

## 4. What Spring Boot Auto-configures, and Its Limits

When a Servlet application adds `spring-boot-starter-security` without providing its own security configuration, Spring Boot creates a default web configuration based on auto-configuration conditions. In the basic case, requests require authentication; form login and HTTP Basic are enabled; demo environments typically have a default user with a random password logged at startup.

This only gives the application **basic protection**, and does not replace production security design. If you declare your own `@Bean SecurityFilterChain`, Boot's default web policy may be replaced by your chain. Declare the full matchers, authentication mechanisms, exception handling, and appropriate fallback; do not assume all previous defaults continue to exist as before.

The actual filters are selected through `FilterChainProxy` and `SecurityFilterChain`; each filter has a single job and runs in an order managed by Spring Security. Adding a custom filter introduces responsibilities for ordering, errors, lifecycle, and the risk of duplicate execution. In most cases, let Spring Security build the chain from the DSL configuration.

**A common misconception:** `permitAll()` allows a request past the **authorization rule**, while the request still passes through the Spring Security filter chain and may receive security headers, CSRF, or other policies. `web.ignoring()` bypasses the security chain for the specified URLs; this is a broader change and should not be used to "fix 401" for public APIs.

## 5. Runnable Java 17+ Example: Solving Requirements with Standard Configuration Only

**Requirements:** `GET /public` is freely accessible; `GET /profile` requires login; `GET /admin` requires the ADMIN role. The demo user has USER; the API uses HTTP Basic for easy verification with `curl`. All requirements can be solved with standard DSL and `UserDetailsService`, without creating a custom filter.

Directory structure:

```text
built-in-security/
├── pom.xml
└── src/main/java/demo/
    └── BuiltInSecurityApplication.java
```

**`pom.xml`** — Spring Boot 3.5.7 manages compatible dependency versions:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>built-in-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

**`src/main/java/demo/BuiltInSecurityApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BuiltInSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuiltInSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails learner = User.withUsername("learner")
                .password(passwordEncoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/profile")
        String profile() {
            return "profile";
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
```

**Explanation of each choice:**

1. `SecurityFilterChain` lets Spring Security configure the standard chain. There is no `new JwtFilter()`, `OncePerRequestFilter`, or manually created `AuthenticationManager`.
2. `authorizeHttpRequests` assigns policies from most specific to most general. `permitAll()` for `/public`; `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority; `anyRequest().authenticated()` is the fallback protecting remaining URLs.
3. `httpBasic` uses the built-in HTTP Basic processor. Disabling **only** form login keeps `curl` testing from getting confused with redirects to a login page; this is a choice for the API example, not a recommendation to turn off form login for every application.
4. `UserDetailsService` supplies the user and `PasswordEncoder` handles password hashing; the framework uses the username/password provider. Creating the "learner" user requires no custom authentication filter.
5. The demo **does not alter CSRF** and only has GET endpoints. If you open POST/PUT/DELETE endpoints, design CSRF based on whether clients use cookies/sessions or Bearer tokens, rather than disabling it by default for every endpoint.
6. The password `demo-password` is written directly in **demo code** for testing; real applications must use a secrets source and a secure user store. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder with an id format and supports upgrade strategies, which is better than using `{noop}` for real accounts.

**Test run** (requires Java 17+ and Maven; run from the directory containing `pom.xml`):

```bash
mvn -q -DskipTests package
java -jar target/built-in-security-0.0.1-SNAPSHOT.jar
```

Open a second terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:demo-password http://localhost:8080/profile
curl -i -u learner:demo-password http://localhost:8080/admin
curl -i -u learner:wrong http://localhost:8080/profile
```

| Request | Expected result | Explanation |
| --- | --- | --- |
| `GET /public`, no credentials | `200 OK`, body `public` | `permitAll` rule |
| `GET /profile`, no credentials | `401 Unauthorized` | HTTP Basic requires authentication |
| `GET /profile`, valid credentials | `200 OK`, body `profile` | Default provider authenticates successfully |
| `GET /admin`, user only has USER | `403 Forbidden` | User is authenticated but lacks `ROLE_ADMIN` |
| `GET /profile`, wrong password | `401 Unauthorized` | Invalid credentials |

`curl -i` displays the status and headers. With HTTP Basic, inspect the `WWW-Authenticate` authentication header managed by the standard mechanism. Do not guess the error response body from the status; the framework and configuration may not produce identical bodies.

**Result:** All sample requirements were solved using standard APIs. Writing an extra "check admin" filter would duplicate the built-in authorization check, increasing the number of places to audit and the likelihood of bugs.

## 6. Changing Requirements: Which Configuration to Choose First?

### Scenario A — A web application needing a login UI

If the system uses browsers, sessions, and a login page, use `formLogin`. In the configuration from section 5, replace the `httpBasic/formLogin` part with:

```java
.formLogin(Customizer.withDefaults())
```

This is a **replacement configuration snippet** inside the same `SecurityFilterChain`, not a standalone Java program. When unauthenticated, a protected endpoint typically directs the user to the login page rather than necessarily returning 401 JSON. Keep CSRF protection for state-changing requests. If you have a custom login page, use `formLogin(form -> form.loginPage("/login"))` and ensure the application actually provides a matching page/endpoint; declaring the path does not auto-generate a custom UI page.

### Scenario B — Only needing to query users from a database

Start with `UserDetailsService#loadUserByUsername` (or `ReactiveUserDetailsService` in WebFlux) and `PasswordEncoder`. Convert the user record into `UserDetails`, including account flags and granted authorities. Spring Security provides `DaoAuthenticationProvider` to use those components.

Abbreviated contract example, **not a standalone runnable class**:

```java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    // Look up the user from the application's existing repository.
    // If not found, throw UsernameNotFoundException.
    // Return UserDetails containing the password hash and authorities.
}
```

A user data lookup task **is not enough** to justify implementing a custom `AuthenticationProvider`: the built-in provider already handles password matching, account status checks, and interaction with the manager. If you have an authentication protocol other than username/password, evaluate a custom provider then.

### Scenario C — An API receiving Bearer JWTs from an identity provider

Do not parse JWTs manually in a filter by splitting the string at dots and Base64-decoding. A JWT needs signature verification, algorithm checks, expiration checks, issuer, audience when needed, signing keys, and authority mapping rules. Use Spring Security's **OAuth2 Resource Server**.

Add the Maven dependency `spring-boot-starter-oauth2-resource-server`. In application configuration, provide the real issuer that issues tokens:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
```

The URL value above **is only an example**; it must be replaced with the exact issuer of the real system. When defining your own `SecurityFilterChain`, enable resource server on the chain protecting the API:

```java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()))
```

The framework provides mechanisms to fetch public keys and validate tokens per the decoder configuration; for scope-based permissions, rules such as `hasAuthority("SCOPE_read")` apply with the corresponding standard mapping. Only write a custom `JwtAuthenticationConverter` when you need to convert claims/authorities according to custom conventions; if the provider uses **opaque tokens**, choose `opaqueToken`/introspection rather than assuming every token is a JWT.

Do not place an unverified access token into `SecurityContext`. Do not turn the mere presence of an `Authorization` string into proof that the user is authenticated.

### Scenario D — Needing authorization based on business attributes

Try `@EnableMethodSecurity` and `@PreAuthorize` for policies at the service layer. This example is an **illustrative snippet attached to an existing service**, not a standalone program:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
public Invoice readInvoice(String owner, long invoiceId) {
    // After the permission check, verify that invoiceId
    // actually belongs to owner at the data access layer.
    // ...
}
```

The expression only checks the `owner` parameter value against the authenticated user; this example alone **does not yet** prove the user owns the invoice. The data layer must still check the real ownership relationship. When access logic is complex, use a policy bean/`AuthorizationManager` that can be tested independently, rather than writing a filter to inspect data on every request.

### Scenario E — Cross-origin frontend blocked by CORS preflight

Configure `cors(Customizer.withDefaults())` together with `CorsConfigurationSource` or an appropriate Spring MVC CORS configuration. Preflight requests usually do not carry cookies; Spring Security supports integrating CORS in the right order. Before adding a filter just to set headers, check allowed origins, methods, headers, and credentials.

Do not fix CORS with `permitAll("/**")` or by disabling all security. CORS is a browser mechanism; it does not replace server-side authentication and authorization.

### Scenario F — Two regions with different login mechanisms

For example, `/api/**` uses HTTP Basic while the remaining web pages use form login. Spring Security allows **multiple `SecurityFilterChain` beans**. The following snippet is a replacement configuration for the `securityFilterChain(...)` bean in section 5; do not keep the old bean at the same time if it causes unwanted policy overlap.

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

This snippet requires `import org.springframework.core.annotation.Order;` and the imports from the main configuration. `@Order(1)` evaluates the API chain first. `securityMatcher("/api/**")` decides **which chain applies**, whereas `requestMatchers(...)` inside `authorizeHttpRequests` decides **permissions inside the selected chain**. A later chain without `securityMatcher` acts as a fallback for remaining requests. If no chain matches, a request might not be protected by Spring Security. Do not create two chains with the same matcher and expect both to run sequentially.

For a real API configuration, pick the right authentication mechanism (Bearer instead of Basic when using OAuth2), configure CSRF protection appropriate to the client type, and test paths outside `/api/**` as well.

## 7. When Is an Extension Point Truly Necessary?

Replace only the **piece** driven by the requirement, and let the framework perform the rest:

| Requirement differing from default | Suitable customization piece | Why a custom filter is not yet needed |
| --- | --- | --- |
| Accounts fetched from DB, specialized directory | `UserDetailsService` / `ReactiveUserDetailsService` | Framework still handles passwords, login results, and context |
| Password hashing policy | `PasswordEncoder` | Not a request-reading or authorization mechanism |
| Audit log after login | `AuthenticationSuccessHandler`, event listener | Provides an exact hook upon successful login |
| Custom response when unauthenticated or forbidden | `AuthenticationEntryPoint`, `AccessDeniedHandler` | Exception dispatching mechanism already exists |
| Mapping JWT claims to internal authorities | `JwtAuthenticationConverter` or appropriate converter | Resource Server still verifies tokens and enforces policies |
| Permissions depending on object data | Method security, `AuthorizationManager`, or policy bean | Checks business rules without manually managing the filter chain |
| Authenticating with a genuinely new credential/protocol | Custom `AuthenticationConverter` / `AuthenticationProvider` with Spring Security mechanisms | Can leverage standard infrastructure instead of writing everything from scratch |

**Write a custom `AuthenticationProvider`** when you need to define an authentication method not supported by standard providers. The provider must handle the appropriate `Authentication` type (`supports`), verify credentials properly, and return an authenticated result or an exception conforming to the contract. A provider should not return HTTP responses directly from the business layer. Pair the provider with a filter/endpoint matching the client type instead of putting every decision into one class.

**Only write a custom filter** if the requirement truly needs to intercept/process HTTP requests at a specific position and no standard mechanism can replace it (for instance, a bespoke authentication protocol that must extract headers and pass them to a manager). For Servlet, `HttpSecurity` provides `addFilterBefore`, `addFilterAfter`, and `addFilterAt`; the position depends on whether context, authentication, and authorization must already be established. For WebFlux, those are `WebFilter` and `SecurityWebFiltersOrder` in `ServerHttpSecurity`.

Document the contract for filter ordering, handling `AuthenticationException`/`AccessDeniedException`, when to invoke the rest of the chain, thread safety, resource creation/cleanup, and idempotency. A Servlet `Filter` that is a Spring bean may be registered by Boot with the container **and** added to the Spring Security chain, causing it to run twice; manage registration explicitly rather than blindly adding `@Component`.

## 8. Testing Before and After Choosing

A configuration is considered to meet requirements only after at least the relevant scenarios are tested:

1. Anonymous access to public and protected paths: 200/401/redirect matches policy.
2. Valid and invalid credentials/tokens: distinguish authentication failure from authorization denied.
3. Users with and without roles/scopes: 200 or 403 as expected; verify `ROLE_` or `SCOPE_` prefix.
4. Different HTTP methods, nested URLs, requests matching no matcher, fallback chain, and `@Order` ordering.
5. POST/PUT/DELETE in cookie-based applications: valid/invalid CSRF tokens; protection is not accidentally disabled.
6. `OPTIONS` preflight requests from allowed/disallowed origins, if CORS is used.
7. Basic returns the right challenge; Bearer has protocol-compliant status/`WWW-Authenticate` header; form login redirects properly.
8. Test service-level authorization, especially object-ownership permissions; do not check URLs alone.
9. Verify logs/metrics are sufficient for investigation without leaking passwords, bearer tokens, session ids, or stack traces in responses.

Quick check example on `/admin`: a request **without credentials** normally receives 401 with HTTP Basic, whereas a request from a user who only has `ROLE_USER` receives 403. If both return 200, the policy is wrong. If both return 403, inspect CSRF exceptions, matchers, entry point, or authentication state before writing an extra filter.

## 9. Common Mistakes When "Writing Custom Code for Flexibility"

- **Manually parsing and verifying JWTs** in a filter and then trusting `sub` or `roles` without verifying signature, issuer, and expiration. Fix: built-in resource server; customize the converter only when needed.
- **Replacing Boot's `SecurityFilterChain` with an overly minimal bean** and accidentally dropping fallback rules or login mechanisms. Fix: define the final policy for all paths; do not assume Boot's configuration merges into the new bean automatically.
- **Registering a custom filter in both the servlet container and the security chain**, causing double invocation. Fix: manage registration and exact placement; prefer the DSL.
- **Abusing `web.ignoring`** for public URLs. Fix: use `permitAll` when you need to retain Spring Security's other protection layers.
- **Disabling CSRF because every POST returns 403**, even though the app uses cookies/sessions. Fix: check client type, CSRF token, and the root cause of the 403.
- **Handling login, Basic, OAuth2, and Bearer in one "all-purpose" filter**. Fix: use dedicated standard mechanisms and split chains when genuinely needed.
- **Confusing URL authorization with object permissions**: allowing `GET /invoice/42` without checking whether the user owns invoice 42. Fix: check at the service/data-access layer.
- **Calling `hasRole("ROLE_ADMIN")`** instead of `hasRole("ADMIN")` (with the default `ROLE_` prefix). For differently named authorities, consider `hasAuthority(...)` and test the mapping.
- **Copying deprecated APIs** such as `WebSecurityConfigurerAdapter` or `antMatchers` from old tutorials into projects using Spring Security 6/7. Fix: use `SecurityFilterChain` and lambda DSL, and read documentation for the matching version.
- **Using servlet security APIs in WebFlux**, or vice versa. Fix: pick the right runtime and reactive interfaces.

## 10. Quick Comparison with WebFlux/Reactive

The WebFlux version uses `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange`, and `WebFilter`. The following snippet is only a **configuration bean** placed inside a WebFlux application that already has WebFlux + Spring Security dependencies; it cannot run standalone without the appropriate app/config:

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

The roles remain similar, though API names differ:

| Servlet/MVC | WebFlux/reactive |
| --- | --- |
| `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` |
| `authorizeHttpRequests`, `requestMatchers` | `authorizeExchange`, `pathMatchers` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `AuthenticationEntryPoint`, `AccessDeniedHandler` | `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` |
| Servlet `Filter` / `OncePerRequestFilter` | Reactive `WebFilter` |

Before creating a manual `WebFilter`, try the `httpBasic`, `formLogin`, `oauth2ResourceServer`, `csrf`, `cors` DSLs and server-side handlers. Reactive code should return `Mono`/`Flux` to the processing pipeline; do not call `block()`/`subscribe()` arbitrarily inside authentication handlers. Set request matchers and the order of `SecurityWebFilterChain` beans properly.

## 11. Decision Process for Code Review

When a new security requirement is assigned, answer in order:

1. **What asset is being protected?** URL, method, object, business operation, browser session, or Bearer API?
2. **Which standard authentication flow applies?** HTTP Basic, form, OAuth2 Login/OIDC, Resource Server JWT/opaque, LDAP, X.509… Are there corresponding starters and configs?
3. **Is a rule change enough?** Try matchers, roles, authorities, method security, session/CSRF/CORS/header DSL.
4. **Is a data or mapping change enough?** Try `UserDetailsService`, `PasswordEncoder`, converters, handlers, repositories.
5. **Is a custom component genuinely needed?** Clearly document the contract, security boundary, chain position, errors, and what the framework remains responsible for.
6. **Have failure scenarios been tested?** Invalid credentials, missing permissions, CSRF, expired tokens, bearer challenge, multiple chains, and unmatched URLs.
7. **Can code be reduced while still meeting requirements?** If a custom filter merely replicates standard DSL/provider logic, remove it to shrink the maintenance surface.

Decision example: "The API must accept JWTs with data-read permission" → `spring-boot-starter-oauth2-resource-server` + `issuer-uri` + `oauth2ResourceServer(jwt)` + `hasAuthority("SCOPE_read")`. Only add a converter if the issuer uses a custom permission claim. Writing a `JwtFilter` right from the start bypasses critical steps already built into the framework.

## 12. Self-Practice Questions

1. Why does changing `/admin` to `hasRole("ADMIN")` not require a separate `Filter`?
2. At which step in chain selection and permission checking do `securityMatcher` and `requestMatchers` differ?
3. When users are stored in a database, what are the reasons to choose `UserDetailsService` before writing a custom `AuthenticationProvider`?
4. When an API already receives Bearer JWTs, why is Resource Server safer than a filter that merely Base64-decodes the token?
5. When does `@PreAuthorize` need to be combined with a real ownership check in the database?
6. When adding a custom `SecurityFilterChain`, what must be re-verified regarding auto-configuration and URL fallback?
7. In a WebFlux application, why are `OncePerRequestFilter` and `HttpSecurity` not the right API pair?

## 13. Official Documentation

- [Spring Security — Servlet Architecture / Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)

**Principle to remember:** use the DSL to express policy, use small extension points to alter necessary details, and only write a new mechanism when a requirement truly exceeds standard capabilities. That is how to extend Spring Security while preserving the protection layers tested and maintained by the framework.
