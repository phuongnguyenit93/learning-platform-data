# AuthorizationWebFilter: Enforcing Authorization Decisions in Spring Security Reactive

## 1. Objectives

In the **Spring WebFlux** security architecture, `AuthorizationWebFilter` is the filter that decides whether a request is allowed to proceed to downstream processing, based on the **configured authorization policy**. After this lesson, you will be able to:

1. Identify the position and responsibilities of `AuthorizationWebFilter` inside `SecurityWebFilterChain`.
2. Explain why a `permitAll`, `authenticated`, `hasRole`, or `denyAll` rule leads to allowing or denying a request.
3. Distinguish **authentication** from **authorization**; understand the roles of `ReactiveAuthorizationManager` and Reactor Context.
4. Explain the error flow from a denied decision to **401** or **403**.
5. Write, run, and verify a WebFlux API using Java 17+.

This lesson focuses on **HTTP request authorization in the reactive stack**. Servlet classes such as `AuthorizationFilter`, `HttpSecurity`, and `SecurityFilterChain` are for Spring MVC/Servlet and do not directly replace the WebFlux classes.

## 2. What Is AuthorizationWebFilter?

`org.springframework.security.web.server.authorization.AuthorizationWebFilter` implements the `org.springframework.web.server.WebFilter` interface. The class's main public method is:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Where:

- `ServerWebExchange` represents the HTTP request/response along with WebFlux's processing context.
- `WebFilterChain` delegates processing to the next filter or handler.
- `Mono<Void>` describes the asynchronous processing task, completing when the filter chain finishes or terminating with an error.
- The filter uses a `ReactiveAuthorizationManager<? super ServerWebExchange>` to check permissions.

**Core responsibility:** receive the request context and current authentication, ask the authorization component for a decision, and either **let the chain continue when granted** or **emit an access-denied error when denied**. This filter **does not verify passwords itself**, **does not parse JWTs itself**, **does not own endpoint business logic**, and **does not directly equate to returning HTTP 403**; translating security errors into HTTP responses belongs to the related exception-handling mechanism.

A WebFlux application typically does not create an `AuthorizationWebFilter` bean manually. When declaring a `SecurityWebFilterChain` via `ServerHttpSecurity.authorizeExchange(...)`, Spring Security constructs and orders the filter together with its corresponding authorization manager.

## 3. Position in the WebFilter Architecture

Conceptual diagram of **a request passing through the matching security chain**:

~~~text
Client HTTP request
        |
        v
WebFlux WebFilterChainProxy
        |
        +-- Select matching SecurityWebFilterChain for the request
        |
        v
Other context / authentication / protection steps
        |
        v
ExceptionTranslationWebFilter
        |
        v
AuthorizationWebFilter   <--  HTTP access-permission check point
        |
        +-- ReactiveAuthorizationManager receives:
        |      Mono<Authentication> + ServerWebExchange
        |                |
        |                v
        |      AuthorizationResult (granted/denied)
        |
        +-- ALLOW ------> chain.filter(exchange) --> Controller/Handler
        |
        +-- DENY -------> AccessDeniedException / denial error
                               |
                               v
                     ExceptionTranslationWebFilter
                     --> entry point or access-denied handler
                     --> response (e.g., 401 / 403)
~~~

This is a **learning diagram**; it does not list every filter and does not assert that every request executes all of those steps. The actual filter list depends on configuration (HTTP Basic, form login, OAuth2 resource server, CSRF, CORS, etc.). In Spring Security, `SecurityWebFiltersOrder` has the anchors `REACTOR_CONTEXT`, `AUTHENTICATION`, `EXCEPTION_TRANSLATION`, and `AUTHORIZATION`; those anchors help understand ordering, rather than inferring a fixed handwritten list.

**Two distinct selection layers:**

1. **Chain selection:** `WebFilterChainProxy` inspects `SecurityWebFilterChain.matches(exchange)` to pick the matching chain. When multiple chains match, priority order matters; only one matching chain is used per the selection mechanism.
2. **In-chain rule selection:** rules declared in `authorizeExchange(...)` are evaluated in order; the first matching matcher determines which authorization manager is invoked.

For instance, a chain dedicated to `/api/**` does not protect other URLs merely by existing. When using multiple chains, you need an explicit policy covering URLs outside the specialized matchers as well.

## 4. Data Flow Used to Decide Access

### 4.1. Authentication and Reactor Context

When a request is authenticated, Spring Security holds an `Authentication` object containing the principal, authentication status, and the set of `GrantedAuthority` instances. In WebFlux, security data is propagated through the **Reactor Context**, where `ReactiveSecurityContextHolder` can read the `SecurityContext` for the processing chain.

Never assume a reactive request always stays on the same thread. `ThreadLocal`-based `SecurityContextHolder`, familiar from Servlet, is not the right data source for retrieving authentication directly in reactive code.

`AuthorizationWebFilter` does not need an immediately materialized Java `Authentication`. It works with a `Mono<Authentication>` stream so the authorization manager can obtain security information during subscription, in a Reactor-friendly way. Public rules such as `permitAll` can grant access without relying on a logged-in identity.

### 4.2. ReactiveAuthorizationManager

Key interface:

~~~java
public interface ReactiveAuthorizationManager<T> {
    Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication, T object);

    // The interface also has a default verify(...) method.
}
~~~

This is an **abbreviated signature for explanation**, not the full interface source. As of Spring Security 7.1, `authorize(...)` returns `Mono<AuthorizationResult>`; the result indicates whether permission was granted or denied via `isGranted()`. `Mono.empty()` signals no explicit conclusion (abstain), which **should not be relied upon as a safe access-blocking strategy**. Write policies with explicit decisions and include a catch-all rule for unmatched requests.

Common manager or policy types:

| Configuration / Manager | Meaning |
| --- | --- |
| `permitAll()` | Allows the request to proceed without requiring login |
| `denyAll()` | Denies the request |
| `authenticated()` | Requires an authenticated identity under Spring Security's trust strategy |
| `hasRole("ADMIN")` | Checks for authority `ROLE_ADMIN` per the default role-prefix rule |
| `hasAuthority("report:read")` | Checks the exact authority string |
| `access(customManager)` | Uses a custom `ReactiveAuthorizationManager<AuthorizationContext>` |
| `DelegatingReactiveAuthorizationManager` | Delegates to the manager matching the request matchers |

**API version note:** Current Spring Security documentation uses `authorize(...)` and `AuthorizationResult`. Older articles may use `check(...)` and `AuthorizationDecision`. `AuthorizationDecision` remains a useful result type in many examples, but when implementing the API, check the Javadoc for your exact version to avoid relying on deprecated or changed methods.

### 4.3. ServerWebExchange and AuthorizationContext

URL policies do not depend solely on username. A manager may need request details such as path, HTTP method, headers, and URI template variables. When calling `access(...)` on a matcher rule, `AuthorizationContext` provides:

- `getExchange()`: accesses the current `ServerWebExchange`.
- `getVariables()`: URI template variables extracted by the matcher, when present.

For example, a `/members/{username}` rule matcher can extract the `username` variable to compare against the caller's username. Data-ownership authorization also requires checking business data in the service layer, not merely matching URL strings.

## 5. Grant, Denial, and HTTP 401/403 Outcomes

`AuthorizationWebFilter` is the **enforcement** point for declared HTTP authorization. To understand the client-visible outcome, pair it with `ExceptionTranslationWebFilter`:

| Request State | Permission Check | Typical Result Under HTTP Basic Config |
| --- | --- | --- |
| Not logged in, calling `permitAll` public endpoint | Allowed | HTTP 200 if handler succeeds |
| Not logged in, calling endpoint requiring `authenticated` or a role | Insufficient credentials | HTTP **401 Unauthorized**, typically with `WWW-Authenticate` challenge |
| Valid login but missing required authority | Insufficient privileges | HTTP **403 Forbidden** |
| Valid login, sufficient privileges | Allowed | Handler is invoked; status decided by handler |
| Catch-all rule `denyAll` | Denied even for logged-in users | Typically 403 if authenticated; anonymous cases depend on entry point |

**Why can you not say "`AuthorizationWebFilter` always returns 403"?** The filter decides allow/deny and emits an error result when denying; `ExceptionTranslationWebFilter` catches `AccessDeniedException` inside the protected chain. For unauthenticated callers, it can invoke `ServerAuthenticationEntryPoint` to initiate login; for authenticated callers who are denied, it invokes `ServerAccessDeniedHandler`. The final outcome depends on the authentication mechanism: HTTP Basic typically returns 401; form login may redirect to the login page; bearer tokens have their own response/header rules. Wrong username/password can also be rejected by the **authentication** mechanism before authorization is ever reached.

In production environments, the status can also be affected by custom exception handlers, firewalls, CSRF, or application logic. **The 401/403 values in the table are expected outcomes of the illustrative configuration**, not immutable descriptions of every Spring Security system.

## 6. Complete Example: Observing AuthorizationWebFilter Across Requests

### 6.1. Project and Dependencies

Create a project using [Spring Initializr](https://start.spring.io/) with Java **17+**, Maven, package `com.example.authzfilter`, and dependencies **Spring Reactive Web** + **Spring Security**. You can use Spring Boot **4.1.2** with its BOM managing compatible Spring Security and Reactor versions. Complete minimal `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>authz-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

Do not declare separate versions for `spring-security-web`, `spring-webflux`, or `reactor-core`: let the Spring Boot BOM manage them consistently. Do not add the Spring MVC starter in this example.

### 6.2. Java: Single Class Containing Both Configuration and Handler

Create `src/main/java/com/example/authzfilter/AuthzFilterDemoApplication.java` with the following contents:

~~~java
package com.example.authzfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class AuthzFilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthzFilterDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/read").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetails() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        public Mono<String> publicPage() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/api/read")
        public Mono<String> read() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "READ_OK:" + name);
        }

        @GetMapping("/api/admin")
        public Mono<String> admin() {
            return Mono.just("ADMIN_OK");
        }
    }
}
~~~

**Part-by-part breakdown:**

- `@EnableWebFluxSecurity` and the `SecurityWebFilterChain` bean configure the security mechanism for WebFlux; `ServerHttpSecurity` builds the chain containing the corresponding components.
- `authorizeExchange` declares the **policy**; `AuthorizationWebFilter` performs the **evaluation and blocks/allows** according to that policy.
- `/public` allows any request; `/api/read` requires valid authentication; `/api/admin` requires `ROLE_ADMIN`; all unmatched URLs are rejected by `denyAll`.
- `httpBasic` is the username/password **authentication mechanism**, distinct from the authorization step; `formLogin` is disabled to avoid redirecting to a login form in this example.
- `reader` has `ROLE_USER` but not `ROLE_ADMIN`; `admin` has `ROLE_ADMIN`. `hasRole("ADMIN")` does not require writing the `ROLE_` prefix explicitly.
- `ReactiveSecurityContextHolder` is used in the `/api/read` handler to read the identity from Reactor Context after security grants access.
- `"{noop}"` is solely for local exercises to avoid configuring a password encoder; **never use plaintext-stored passwords in production**. Real applications use an appropriate encoder, HTTPS, and a secure identity system.

Because only HTTP **GET** is used, the example does not need to disable CSRF. WebFlux Security's default CSRF remains enabled; if you add POST/PUT/DELETE and test without a token, requests can be blocked by CSRF before authorization, so distinguish those error types.

### 6.3. Run the Project

From the directory containing `pom.xml`, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `.\mvnw.cmd spring-boot:run`. If the project has no Maven wrapper, use an installed Maven via `mvn spring-boot:run`. Once the app is running at `http://localhost:8080`, open a second terminal.

### 6.4. Verify via HTTP

~~~bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/read

curl -i -u reader:reader123 http://localhost:8080/api/read

curl -i -u reader:reader123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/unknown
~~~

Results to observe, in the order above:

| Request | Expected HTTP Status | Notable Body | Explanation |
| --- | --- | --- | --- |
| `GET /public`, anonymous | **200** | `PUBLIC_OK` | `permitAll` |
| `GET /api/read`, anonymous | **401** | Not dependent on body content | `authenticated` denies anonymous; HTTP Basic entry point |
| `GET /api/read`, reader | **200** | `READ_OK:reader` | Valid authentication |
| `GET /api/admin`, reader | **403** | Depends on config | Missing `ROLE_ADMIN` |
| `GET /api/admin`, admin | **200** | `ADMIN_OK` | Has `ROLE_ADMIN` |
| `GET /unknown`, admin | **403** | Depends on config | `anyExchange().denyAll()` blocks before the handler resolves the path |

With `curl -i`, responses also contain headers generated by the HTTP server/security; avoid hardcoding every header into tests. Notably, `GET /unknown` would normally be **404** in an application that does not block paths, whereas here **403** is expected because `denyAll` blocks before the request reaches handler lookup.

If a request to `/public` still returns 401 when sending **invalid credentials**, that may be an **authentication** failure caused by an invalid HTTP Basic header. `permitAll` only describes the authorization policy; it does not disable all other filters.

## 7. Why Does Rule Order Directly Affect AuthorizationWebFilter?

Inspect the following configuration:

~~~java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

This is an **illustrative misconfiguration**, not a standalone Java method. The request `/api/admin` matches `/api/**` first and only requires being logged in; the subsequent `hasRole("ADMIN")` rule has no effect for that path. The cause is not that `AuthorizationWebFilter` "forgot" the rule, but that **policies are evaluated in priority order**.

Correct configuration:

~~~java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/admin").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Order **specific rules before broad rules**, include an explicit catch-all rule, and then test insufficient-privilege cases. Pay special attention to matchers by **HTTP method**: protecting only `GET /reports/**` does not automatically protect `POST /reports/**`. You can declare `pathMatchers(HttpMethod.POST, "/reports/**").hasAuthority("report:write")` with the corresponding `org.springframework.http.HttpMethod` import.

A distinction to remember:

- `securityMatcher(...)` decides **which SecurityWebFilterChain applies**.
- `authorizeExchange(...).pathMatchers(...)` decides **which rule applies inside that chain**.

Confusing these two matcher levels can leave paths unprotected or protect them with an unintended chain.

## 8. Extension: Custom ReactiveAuthorizationManager and AuthorizationContext

Built-in rules like `authenticated` or `hasRole` are usually sufficient for basic URL policies. When context-dependent checks are needed, you can use `access(...)`. For example, for `/members/{username}`, only a user with role `USER` whose name equals the path variable is permitted.

Inside the `authorizeExchange(exchange -> exchange ... )` block, you can add the rule **before the catch-all rule**:

~~~java
.pathMatchers("/members/{username}")
.access((authentication, context) ->
        authentication
                .map(auth -> (AuthorizationResult) new AuthorizationDecision(
                        auth.getName().equals(context.getVariables().get("username"))
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "ROLE_USER".equals(a.getAuthority()))))
                .defaultIfEmpty(new AuthorizationDecision(false)))
~~~

This is a **configuration snippet to insert**, not a standalone program; required imports:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
~~~

Explanation:

1. `pathMatchers("/members/{username}")` matches the URL and extracts the `username` variable.
2. Spring Security passes `Mono<Authentication>` and `AuthorizationContext` to the custom manager.
3. `map(...)` builds an explicit `AuthorizationResult`: **granted** only when both username and authority match.
4. `defaultIfEmpty(new AuthorizationDecision(false))` ensures missing authentication yields an explicit denial decision.
5. For the request to succeed, the application must also define a handler for `/members/{username}`; the snippet above is only a **policy** and does not create an endpoint.

Why is the role check needed here? Comparing only the name against the URL could allow an anonymous principal whose default name happens to match a URL segment to cause unexpected access behavior in some configurations. Combine identity/role checks and, in real business logic, verify resource ownership from a trusted data source.

**Limitation:** path-based checks are insufficient if the client can pick arbitrary IDs or if sensitive data has complex access rules. Record ownership, tenant, and business-state rules must also be enforced at the service/data-access layer. Avoid calling JDBC or blocking APIs directly inside `access(...)` on the event loop; if a policy requires queries, prefer reactive components.

## 9. What Happens When an Authorization Manager Emits No Decision?

A `ReactiveAuthorizationManager` can return:

- `Mono.just(result)` with `result.isGranted() == true`.
- `Mono.just(result)` with `result.isGranted() == false`.
- `Mono.empty()`, meaning **no decision** (abstain).

Never assume `Mono.empty()` implicitly means "deny" in every situation. The `verify(...)` interface uses the authorization result to complete when not denied, or raise an error when denied. In custom security policies, **always produce an explicit decision** for tightly controlled cases; use `defaultIfEmpty(new AuthorizationDecision(false))` when you want fail-closed behavior.

Similarly, configuring `anyExchange().denyAll()` at the end prevents accidentally overlooking a URL. When dealing with complex permissions or multiple security chains, still test that real requests actually enter the right chain and right rule.

## 10. Relationship to Other WebFilters

| Component | Role | Difference from AuthorizationWebFilter |
| --- | --- | --- |
| `WebFilterChainProxy` | Selects `SecurityWebFilterChain` and runs the chain's filters | Coordinates filters; does not evaluate per-URL authorization policies itself |
| `AuthenticationWebFilter` | Reads credentials/tokens per authentication scheme and coordinates with `ReactiveAuthenticationManager` | Answers "who is sending the request?" |
| `ReactorContextWebFilter` | Integrates SecurityContext from repository into Reactor Context | Provides context; does not grant roles itself |
| `SecurityContextServerWebExchangeWebFilter` | Integrates security principal into `ServerWebExchange` | Enables principal access; does not evaluate rules |
| `AnonymousAuthenticationWebFilter` | Supplies an anonymous representation when needed | Anonymous does not mean user-authenticated |
| `ExceptionTranslationWebFilter` | Translates access errors into an entry point or access-denied response | Handles the consequence of denial |
| `AuthorizationWebFilter` | Enforces HTTP authorization policies | Evaluates/enforces access via the manager |
| Reactive method security | Controls method calls when enabled | Another check layer at service/method level; does not replace URL authorization |

**Common misconception:** HTTP requests can be blocked before calling the controller, but that does not automatically make all direct service calls safe. For business permissions at the method level, look into `@EnableReactiveMethodSecurity` and its annotations; in reactive method security, SecurityContext propagation relies on Reactor Context.

## 11. How to Debug Unexpected 401/403 Results

Start from the **actual HTTP request** (path, method, credentials), then determine rule order and the security chain. Suggested diagnostic flow:

1. **401 even when you think you logged in:** check the `Authorization` header, password/token, HTTP Basic/bearer configuration, user status, and credential extraction method. The request may not have been authenticated, so authorization never received a valid identity.
2. **403 for a logged-in user:** print/verify the `GrantedAuthority` set from a trusted source in tests; `hasRole("ADMIN")` requires `ROLE_ADMIN` under default config, while `hasAuthority("ADMIN")` requires exact `ADMIN`.
3. **Admin rule ignored:** check the order of `/api/**` vs. `/api/admin`. A broad matcher placed first prevents the specific rule from ever being evaluated.
4. **A public URL gets blocked:** check the actual path/method, chain `securityMatcher`, `permitAll` rule, and whether another filter (e.g., failed authentication, CSRF) emitted an error.
5. **An endpoint that should be 404 returns 403:** check the catch-all `denyAll` rule. Authorization may block before WebFlux looks up a handler.
6. **Suspected lost context:** check whether logic detached into a processing flow not carrying Reactor Context or is using `ThreadLocal`-based `SecurityContextHolder`.

You can enable security DEBUG logging **in development** via `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Then observe requests and filter/authorization logs; exact logger/message names vary across versions, so do not assume an identical log line will always appear. Do not leave sensitive TRACE logging on indefinitely in production or log credentials, JWTs, or session cookies. When certainty is needed, write integration tests verifying statuses per role rather than only reading console output.

## 12. Comprehension Check Exercises

**Exercise 1.** There are three rules in order: `/admin/** -> hasRole("ADMIN")`, `/api/** -> authenticated`, and finally `denyAll`. User `reader` is authenticated with only `ROLE_USER`. What does `GET /admin/stats` receive?

**Answer:** denied under the `/admin/**` rule. With the HTTP Basic example and an authenticated user, the typical result is **403**. The `/api/**` rule does not apply.

**Exercise 2.** Swap the order: `/api/** -> authenticated` precedes `/api/admin -> hasRole("ADMIN")`. Why can `reader` access `/api/admin`?

**Answer:** the request matches the broad rule first, so the manager only requires `authenticated` and grants access. The specific rule is never evaluated for that URL.

**Exercise 3.** Why can an insufficient-privilege error in `AuthorizationWebFilter` become either 401 or 403?

**Answer:** `ExceptionTranslationWebFilter` selects the entry point for an unauthenticated principal, or the access-denied handler for an authenticated user. HTTP Basic typically produces 401/403; form login may redirect.

**Exercise 4.** To allow `/members/{username}` only when `username` belongs to the logged-in user, where should the data be read?

**Answer:** use reactive authentication and `AuthorizationContext.getVariables()` inside a custom `access(...)`; also verify roles and data ownership at the business layer when needed.

**Exercise 5.** Why does `permitAll` not guarantee a request will reach the controller?

**Answer:** it grants access at the corresponding HTTP authorization step; authentication filters, CSRF, the firewall, route/handler resolution, or other components can still prevent the request from reaching the controller.

## 13. Summary of Rules to Remember

- `AuthorizationWebFilter` **enforces** HTTP permissions; `ReactiveAuthorizationManager` **evaluates** the policy; `ExceptionTranslationWebFilter` **turns errors into responses**.
- Reactive authorization uses `Mono<Authentication>` and Reactor Context; never assume a request stays bound to a single thread.
- `authorizeExchange` order is critical: **specific matchers first, broad matchers last**.
- Clearly distinguish `authenticated`, `hasRole`, and `hasAuthority`; roles use the `ROLE_` prefix under default configuration.
- Treat `Mono.empty()` in custom authorization as **no decision**, not a reliable deny mechanism; when safety requires it, return an explicit denied decision.
- Test anonymous, valid-role, wrong-role, and unconfigured URLs. Security policies must be proven by actual request behavior.
- URL-level authorization is one layer of defense; data, ownership, and tenant permissions must still be enforced where business logic runs.

## 14. Official Documentation

- [Spring Security — Authorize ServerHttpRequest (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security API — AuthorizationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationWebFilter.html)
- [Spring Security API — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security API — AuthorizationContext](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security API — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
