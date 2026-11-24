# AuthorizationManager and How Allow/Deny Decisions Are Represented (Spring Security Servlet)

## 1. Why Do We Need an Authorization Decision Model?

In a Spring Security Servlet application, **authentication** answers "who does this request represent?", while **authorization** answers "is that identity allowed to perform this action on this resource?".

Consider a reporting API with these requirements:

- Unauthenticated users can view `GET /public`.
- `lan` can read report `r101` but cannot read `minh`'s report `r202`.
- Users with the `ADMIN` role can view both reports, if other business rules permit.
- Regular accounts cannot access `GET /finance/export`.
- Sensitive actions may require both `ROLE_ADMIN` **and** a fully authenticated state.

If authorization checks are scattered via `if` statements inside every controller, it is easy to miss an endpoint, drift across APIs, and struggle with testing. **`AuthorizationManager<T>`** is Spring Security's abstraction for making **allow or deny decisions** based on the `Authentication` and the protected target object.

Objectives after this article:

1. Understand the `AuthorizationManager<T>` interface, `Supplier<Authentication>`, and the context parameter `T`.
2. Distinguish **granted**, **denied**, and possible **abstain** decisions in Spring Security 6.3.x APIs.
3. Understand the position of `AuthorizationFilter`, `ExceptionTranslationFilter`, and policies in the Servlet filter chain.
4. Know how to use built-in managers and write custom managers checking roles + object ownership.
5. Distinguish "request matches a matcher" from "request is granted permission".
6. Write MockMvc tests proving 200, 401, and 403 responses with real HTTP requests.
7. Understand limitations: CSRF, resource ownership, multi-tenancy, method security, auditing, performance, and race conditions.

**Example scope:** Java 17, Spring Boot 3.3.5, Spring Security 6.3.x on the Servlet stack. API names and additional mechanisms may change in newer Spring Security releases; when upgrading, check the corresponding official documentation.

## 2. The AuthorizationManager<T> Contract

The core interface is `org.springframework.security.authorization.AuthorizationManager<T>`. In Spring Security 6.3.x, the key parts to understand are:

```java
// Conceptual signature; place inside a context with appropriate imports.
// Do not copy this snippet to redefine the library's AuthorizationManager.
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);

void verify(
    Supplier<Authentication> authentication,
    T object
);
```

Key points:

- `authentication` is a **Supplier**: an object that can supply `Authentication` when the manager needs it; it does not always have to be invoked.
- `object` is the protected context, depending on manager type: for HTTP Servlet it is typically `RequestAuthorizationContext`; in other mechanisms it may be another type.
- `check(...)` represents the decision result. With the `AuthorizationDecision` API in this article, `new AuthorizationDecision(true)` represents allow and `new AuthorizationDecision(false)` represents deny.
- Under this API generation's contract, `check(...)` **may return null to abstain** (express no decision). **Null is not an allow decision** and must never be treated as "allow by default".
- `verify(...)` is a helper method to enforce the check; when the result is **deny**, it can throw `AccessDeniedException`. Do not assume a `null` from a manager is a deny decision without checking the combinator/enforcement mechanism.

This snippet is explanatory, not a standalone class. In real Java code, `Supplier` is in `java.util.function`, `Authentication` is in `org.springframework.security.core`, and `AuthorizationDecision`/`AuthorizationManager` are in `org.springframework.security.authorization`.

### 2.1. Meaning of the Generic T

`AuthorizationManager<T>` is not limited to a single endpoint type. The generic `T` indicates **the object being authorized**:

| Policy kind | Common `T` | Context inspected |
| --- | --- | --- |
| HTTP Servlet request | `RequestAuthorizationContext` | `HttpServletRequest`, path variables, relevant HTTP data |
| URL/filter integration in other API versions | May use a different context/filter invocation | Check version specifics |
| Method security | Method invocation context or object | Method, args, return value, annotations per mechanism |
| Custom integration | Application-defined context | Resource, action, tenant, verified attributes |

You cannot arbitrarily take an `AuthorizationManager<RequestAuthorizationContext>` and plug it where an `AuthorizationManager<MethodInvocation>` is required expecting the compiler/framework to convert contexts automatically.

### 2.2. Supplier<Authentication> and Lazy Evaluation

Because the manager receives a supplier, it can **fetch Authentication only when actually needed**:

```java
AuthorizationManager<RequestAuthorizationContext> demoPolicy =
    (authenticationSupplier, context) -> {
        // Only call get() in managers that actually need Authentication.
        Authentication current = authenticationSupplier.get();
        boolean allowed = current != null
            && current.isAuthenticated();

        return new AuthorizationDecision(allowed);
    };
```

This is an **illustrative snippet inside a class with imports**, not a recommendation to rely solely on `isAuthenticated()` for real policies. For anonymous users, `AnonymousAuthenticationToken.isAuthenticated()` can be true; the runnable example below uses `AuthenticationTrustResolver`.

**Why use a supplier?** Some decisions, such as `permitAll` or `denyAll`, do not need to read the principal. Unnecessary `SecurityContext`/`Authentication` lookups can be avoided on those code paths. Do not force `supplier.get()` on every request just because the supplier is passed in.

## 3. AuthorizationDecision: Granted, Denied, and Abstain

### 3.1. Explicit Decisions

In Spring Security 6.3.x:

```java
AuthorizationDecision allow =
    new AuthorizationDecision(true);

AuthorizationDecision deny =
    new AuthorizationDecision(false);

boolean granted = allow.isGranted(); // true
boolean denied = deny.isGranted();   // false
```

`AuthorizationDecision` holds the granted/denied state; it is **not** an object representing an HTTP status code or response body. The same deny decision can produce 302, 401, or 403 depending on authentication and exception-handling configuration.

For example:

- `new AuthorizationDecision(true)` → the policy allows execution to proceed unless another check blocks it.
- `new AuthorizationDecision(false)` → the policy denies access; the enforcement layer handles the appropriate exception/response.

### 3.2. What Is Null / Abstain?

A custom manager can return `null` to express **no conclusion** under the older contract. This is neither "allow" nor guaranteed to be interpreted by every manager as "deny".

```java
// ILLUSTRATION ONLY of older contract: avoid returning null arbitrarily in terminal policies.
AuthorizationManager<RequestAuthorizationContext> undecided =
    (authenticationSupplier, context) -> null;
```

When combining multiple managers or using another API, how abstain is handled depends on the implementation/combinator. Therefore:

- If a policy is **ultimately responsible** for a resource, return an explicit `AuthorizationDecision(true/false)`.
- When data is missing or context is invalid, a terminal manager should normally return deny.
- When composing multiple policies, explicitly design ordering and "all of / any of" aggregation semantics, including the case where no policy reaches a decision.
- Never write `return null` on a DB error thinking "unknown means pass"; missing information must be handled in a controlled way, typically **fail closed**.

### 3.3. Distinguishing Denied from Runtime Errors

A deny decision is an intentional policy outcome. DB timeouts, network failures, or unexpected exceptions are **execution errors**, not proof that the user lacks privileges. The system must prevent data leaks and avoid failing open, while emitting appropriate logs/metrics/alerts.

Never catch every exception and `return new AuthorizationDecision(true)`. Conversely, do not mask system outages by reporting "wrong password" for every 500.

### 3.4. Newer APIs

Depending on the version, Spring Security includes newer authorization result abstractions, such as `AuthorizationResult` and additional/changed methods alongside `AuthorizationDecision`. Code in this article **pins Spring Boot 3.3.5 / Spring Security 6.3.x**, so it uses `AuthorizationDecision` and `check(...)`. When upgrading, check official signatures and deprecations rather than assuming newer versions share identical APIs.

## 4. Where Does AuthorizationManager Sit in the Servlet Request Flow?

A typical flow:

```text
HTTP request
     |
     v
DelegatingFilterProxy
     |
     v
FilterChainProxy
     |
     v
Selected SecurityFilterChain
     |
     +-- SecurityContext handling / Authentication filters
     |        -> create or restore Authentication
     |
     +-- ExceptionTranslationFilter
     |        -> handle security exceptions appropriately
     |
     +-- AuthorizationFilter
              |
              +-- receives Supplier<Authentication>
              +-- passes request to AuthorizationManager
              +-- matching rule selected
              +-- decision GRANTED / DENIED
              |
              +-- GRANTED -> continue to controller
              +-- DENIED  -> AccessDeniedException / exception handling
```

In modern HTTP Servlet configurations, `AuthorizationFilter` is where `AuthorizationManager` decisions are enforced. `ExceptionTranslationFilter` typically handles authorization/authentication exceptions, choosing the appropriate entry point or access denied handler.

This is a **conceptual model**, not a guarantee of the exact order of every filter an application might register. Some requests can be rejected before `AuthorizationFilter`, for instance by CSRF or the request firewall.

### 4.1. Distinguishing PEP and PDP

Common architectural terms:

- **PEP (Policy Enforcement Point):** where the decision is enforced — in the HTTP example, `AuthorizationFilter` plays this role.
- **PDP (Policy Decision Point):** where the decision is computed — in the example, `AuthorizationManager` plays this role.
- **PIP (Policy Information Point):** source of attributes/data needed by the policy — for example, a report repository telling which report belongs to which user.

Not every application needs to deploy these three as separate services. Separating responsibilities prevents mixing data queries, HTTP response construction, and email sending inside a hard-to-test matcher/policy.

### 4.2. Authorization Granted Does Not Guarantee HTTP 200

Even when `AuthorizationManager` returns granted:

- The controller can return 404 if the resource does not exist.
- Business validation can return 400.
- Method security can deny based on deeper policies.
- An earlier filter may have handled the request differently than expected.
- The controller may fail with 500.
- The CSRF filter may block a POST before authorization runs.

**The manager decides whether to allow proceeding under its policy**, not the final HTTP status code of the entire request.

## 5. RequestMatcher Selects the Rule; AuthorizationManager Decides Access

In `authorizeHttpRequests`, for example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/reports/{reportId}").access(reportAccessPolicy)
    .anyRequest().denyAll()
);
```

There are two layers:

1. `requestMatchers("/reports/{reportId}")` answers "does the HTTP request match this route?".
2. `reportAccessPolicy` answers "does the principal have permission for the specific report requested?".

Do not think that when a route matcher returns true, the user is already granted access. Conversely, an allowing manager does not cause unrelated URLs to match.

### 5.1. First Matching Rule Order

`authorizeHttpRequests` typically applies **the first matching request matcher**. Here is a dangerous mistake:

```java
// INCORRECT when /reports/internal/** needs its own policy:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").permitAll()
    .requestMatchers("/reports/internal/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

The `/reports/**` matcher comes first and already handles the internal URL. Place specific rules before broad ones, and use a custom `AuthorizationManager` when multiple privilege conditions must be combined.

With multiple `SecurityFilterChain` beans, `securityMatcher` picks the first matching **chain**; `requestMatchers` picks the **authorization rule** inside the chosen chain. Do not confuse the two scopes.

### 5.2. Default Should Fail Closed

For endpoints without an explicit policy, a configuration can use `.anyRequest().denyAll()` to prevent new routes from accidentally becoming public. When using this fallback, remember to explicitly configure login, error, static asset, or health paths if the product requires access to them.

In the HTTP Basic API example below, only `/public` is public; business routes are protected by dedicated managers.

## 6. Built-in AuthorizationManagers

Spring Security provides components for common cases:

| API or mechanism | General meaning |
| --- | --- |
| `permitAll()` | Allows matching requests without requiring authentication |
| `denyAll()` | Denies matching requests |
| `authenticated()` | Requires an authentication that is not anonymous per trust resolver |
| `fullyAuthenticated()` | Requires an authentication that is neither anonymous nor remember-me |
| `hasRole("ADMIN")` | Requires authority following the `ROLE_ADMIN` convention |
| `hasAuthority("report:read")` | Requires the exact authority name |
| `AuthorityAuthorizationManager` | Manager checking configured roles/authorities |
| `AuthenticatedAuthorizationManager` | Manager checking authentication trust level |
| `AuthorizationManagers.allOf(...)` | Combines managers with AND-like logic |
| `AuthorizationManagers.anyOf(...)` | Combines managers with OR-like logic |

Practical composition must consider **abstain/deny semantics** for your version. For critical terminal policies, returning an explicit decision and thoroughly testing edge cases matters more than relying solely on combinator names.

### 6.1. Privilege and Trust Level Are Two Axes

For example, `hasRole("ADMIN")` does **not by default** require `fullyAuthenticated`. A user recognized via remember-me can still carry `ROLE_ADMIN`. If a resource is highly sensitive, you can require both simultaneously:

```text
request matches /finance/export
AND AuthenticationTrustResolver.isFullyAuthenticated(current)
AND current has ROLE_ADMIN
AND other business policies (if any)
```

In the example, a custom manager expresses this AND condition explicitly. Even so, `fullyAuthenticated` **does not prove recent MFA**; if step-up/recent authentication is needed, design additional policies.

### 6.2. Authority Checks Are Not Enough for Resource Ownership

`hasRole("READER")` lets users with a reader role through, yet cannot distinguish `lan`'s report from `minh`'s report. Object-level authorization needs a source of truth (repository/domain service) to verify owner/tenant and permitted action.

This is a natural fit for a custom `AuthorizationManager<RequestAuthorizationContext>` or method security depending on architecture.

## 7. RequestAuthorizationContext and Path Variables

For HTTP Servlets, a manager can use `RequestAuthorizationContext`:

```java
// Illustrated inside a class with RequestAuthorizationContext:
HttpServletRequest request = context.getRequest();
String reportId = context.getVariables().get("reportId");
String method = request.getMethod();
```

`getVariables()` carries path variables extracted by matchers that support extraction, such as a Spring MVC-compatible matcher for `/reports/{reportId}`. **Do not assume** every arbitrary matcher always supplies the same variables.

In a Spring MVC application on Spring Security 6.3.x, the DSL:

```java
.requestMatchers("/reports/{reportId}").access(reportAccessPolicy)
```

can use MVC-aware matching when framework conditions align, populating `reportId` in `RequestAuthorizationContext`. Integration tests below directly verify that this variable is actually populated in the target Spring Boot setup.

### 7.1. Path Variables Are Untrusted Input

Even when the matcher extracts `reportId` successfully, that value comes from the client's URL. The manager must look up the ID in a trusted repository rather than deriving ownership from a client-supplied query/header value.

Mistake:

```java
// Unsafe: never derive ownership solely from a client-supplied parameter.
boolean allow = request.getParameter("owner")
    .equals(authentication.get().getName());
```

An attacker can simply change `owner=lan`. A proper policy verifies who actually owns the report in the server store to prevent IDOR/BOLA.

### 7.2. Missing Targets Must Still Yield a Clear Decision

If the path variable is missing, the report ID is invalid, or the repository finds no report, a terminal manager should normally return **deny** or invoke a 404 mechanism aligned with policy—never `return true` or `return null` to "let it slide because data is missing".

Returning 403 vs. 404 for nonexistent resources is also an API design decision that can prevent enumeration. The simple example prioritizes denying in the manager and testing for 403.

## 8. Writing a Well-Scoped Custom AuthorizationManager

A good manager should:

- Accept `Authentication`/context and read only the data **needed** for the decision.
- Return an explicit allow/deny decision.
- Never write business data or perform side effects inside `check`.
- Never trust client-declared headers or query parameters for role/owner.
- Never let DB errors turn into `AuthorizationDecision(true)`.
- Never log passwords, tokens, session IDs, or sensitive principal details.
- Have unit tests for decisions and integration tests through the HTTP filter chain.
- Account for performance, query count, and cache invalidation.
- Stay consistent with service/method policies, especially when controllers touch multiple resources.

### 8.1. Report Policy Model

Definition:

```text
reportOwner("r101") = "lan"
reportOwner("r202") = "minh"

allow(GET /reports/{reportId}) if:
   authentication is valid and not anonymous
   AND reportId exists in server store
   AND (
       username == reportOwner(reportId)
       OR authority == ROLE_ADMIN
   )
```

The admin clause is just a sample business rule. In a multi-tenant system, an admin of tenant A is **not necessarily** allowed to view reports of tenant B. Roles, tenants, scopes, and account states must match real policy.

### 8.2. When Should Authentication Supplier Be Called?

In this manager we need username and authorities to decide, so we call `authenticationSupplier.get()`. On `/public` using `permitAll`, the framework does not need to resolve `Authentication`.

The goal is **purposeful usage**, not avoiding the supplier at all costs. If a request is already denied due to a missing `reportId`, the manager can return deny immediately without loading the principal.

## 9. Complete Spring Boot 3.3.5 + Java 17 Demo

The runnable example includes:

- `GET /public`: public.
- `GET /reports/{reportId}`: owner or admin, using a custom manager.
- `GET /finance/export`: admin and fully authenticated only.
- All other URLs: deny.
- HTTP Basic makes testing 401/403/200 simple; the example does not configure form login or remember-me cookies.

Demo accounts:

| Username | Password (demo only) | Authorities | Owned report |
| --- | --- | --- | --- |
| `lan` | `lan-demo` | `ROLE_USER` | `r101` |
| `minh` | `minh-demo` | `ROLE_USER` | `r202` |
| `admin` | `admin-demo` | `ROLE_ADMIN` | Does not need ownership in sample policy |

**Use only for local testing.** HTTP Basic uses Base64 encoding rather than transport encryption; production requires HTTPS and non-hardcoded real secrets.

### 9.1. Project Structure

```text
authorization-manager-demo/
  pom.xml
  src/
    main/java/example/authorization/
      AuthorizationDemoApplication.java
      SecurityConfig.java
      ReportOwnerStore.java
      ReportAccessPolicy.java
      AdminFullPolicy.java
      DemoController.java
    test/java/example/authorization/
      AuthorizationManagerIntegrationTest.java
```

### 9.2. Maven pom.xml

```xml
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
    <artifactId>authorization-manager-demo</artifactId>
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

### 9.3. Main Class

File `src/main/java/example/authorization/AuthorizationDemoApplication.java`:

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

### 9.4. ReportOwnerStore: Server-Side Ownership Data

File `src/main/java/example/authorization/ReportOwnerStore.java`:

```java
package example.authorization;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ReportOwnerStore {

    private final Map<String, String> owners = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    public String ownerOf(String reportId) {
        return owners.get(reportId);
    }
}
```

Here `Map` is an illustrative data source so the project runs standalone. In real products, query a controlled data store, distinguish `tenantId` and report state, consider filtering by owner/tenant right in SQL, and enforce checks again at the service layer.

### 9.5. ReportAccessPolicy: Custom Resource AuthorizationManager

File `src/main/java/example/authorization/ReportAccessPolicy.java`:

```java
package example.authorization;

import java.util.function.Supplier;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class ReportAccessPolicy
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ReportOwnerStore store;

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public ReportAccessPolicy(ReportOwnerStore store) {
        this.store = store;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        String reportId = context.getVariables().get("reportId");

        // Missing variable or ID absent from store: deny explicitly.
        if (reportId == null) {
            return new AuthorizationDecision(false);
        }

        String owner = store.ownerOf(reportId);
        if (owner == null) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authenticationSupplier.get();

        if (current == null || !trust.isAuthenticated(current)) {
            return new AuthorizationDecision(false);
        }

        boolean isOwner = owner.equals(current.getName());

        boolean isAdmin = current.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        return new AuthorizationDecision(isOwner || isAdmin);
    }
}
```

In this code:

1. `context.getVariables().get("reportId")` reads the path variable from `/reports/{reportId}`. Spring MVC-aware matching is active in the sample environment, and the integration test verifies this behavior.
2. Missing reportId or nonexistent report → `false`, never `null`.
3. `AuthenticationTrustResolver` excludes anonymous tokens even when their `isAuthenticated` flag is true.
4. Ownership comes from the **server-side store**, never from a client-sent `?owner=lan` parameter.
5. Admin access follows **this example's policy**. Multi-tenant apps need additional tenant/scope checks.
6. The manager does not construct HTTP responses; `AuthorizationFilter` and exception handling handle responses.

### 9.6. AdminFullPolicy: Authority Plus Trust Level

File `src/main/java/example/authorization/AdminFullPolicy.java`:

```java
package example.authorization;

import java.util.function.Supplier;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class AdminFullPolicy
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        Authentication current = authenticationSupplier.get();

        boolean full = current != null
            && trust.isFullyAuthenticated(current);

        boolean isAdmin = current != null
            && current.getAuthorities().stream().anyMatch(
                a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return new AuthorizationDecision(full && isAdmin);
    }
}
```

A remembered admin can still hold `ROLE_ADMIN`, yet is not considered fully authenticated. This manager requires **both conditions**; it does not conflate a role with authentication strength.

Even so, for extremely sensitive export endpoints, `fullyAuthenticated` still does not guarantee MFA or recent login. Those requirements need additional policies.

### 9.7. SecurityConfig: Wiring Managers into HTTP Rules

File `src/main/java/example/authorization/SecurityConfig.java`:

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo"))
            .roles("USER")
            .build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(lan, minh, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ReportAccessPolicy reportPolicy,
            AdminFullPolicy adminFullPolicy) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/reports/{reportId}")
                    .access(reportPolicy)
                .requestMatchers("/finance/export")
                    .access(adminFullPolicy)
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Demo only uses GET endpoints; keep default CSRF protection intact.
        return http.build();
    }
}
```

Explanation:

- `.requestMatchers(...).access(reportPolicy)` binds the request matcher to the authorization manager.
- `.access(adminFullPolicy)` assigns the manager for the sensitive route.
- `.anyRequest().denyAll()` avoids exposing any unlisted route.
- `httpBasic` lets us exercise authentication via Basic headers; `STATELESS` and `NullSecurityContextRepository` avoid using HTTP sessions as an Authentication source across requests.
- `NullRequestCache` avoids storing previous URLs in the session merely for form-login redirects.
- `formLogin` is not enabled because this is an API demo. HTTP 401 typically includes `WWW-Authenticate: Basic`; authenticated users lacking access typically receive 403.
- The example only defines **GET** endpoints; adding POST/PUT/DELETE requires evaluating CSRF per client credential mechanism, state-changing authorization, and idempotency. Stateless does not automatically make CSRF irrelevant.

### 9.8. DemoController: Avoid Duplicating Authorization Logic

File `src/main/java/example/authorization/DemoController.java`:

```java
package example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{reportId}")
    String report(@PathVariable String reportId,
                  Authentication authentication) {
        return "report:" + reportId + ":" + authentication.getName();
    }

    @GetMapping("/finance/export")
    String export(Authentication authentication) {
        return "export:" + authentication.getName();
    }
}
```

This demo keeps responses short and easy to test. In real products, the service fetching reports should enforce resource owner/tenant checks at an appropriate trust boundary, rather than assuming every call into the service originates from a protected HTTP controller.

## 10. Testing with MockMvc: Who May View Which Report?

File `src/test/java/example/authorization/AuthorizationManagerIntegrationTest.java`:

```java
package example.authorization;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationManagerIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AdminFullPolicy adminFullPolicy;

    @Test
    void publicRouteWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousReportGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(get("/reports/r101"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge =
            response.getResponse().getHeader("WWW-Authenticate");

        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void ownerLanCanReadHerReport() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101:lan"));
    }

    @Test
    void lanCannotReadMinhReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerMinhCanReadHisReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202:minh"));
    }

    @Test
    void adminCanReadBothReports() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101:admin"));

        mvc.perform(get("/reports/r202")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202:admin"));
    }

    @Test
    void unknownReportIdIsExplicitlyDenied() throws Exception {
        mvc.perform(get("/reports/unknown")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousFinanceExportGets401() throws Exception {
        mvc.perform(get("/finance/export"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void nonAdminFinanceExportGets403() throws Exception {
        mvc.perform(get("/finance/export")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fullAdminCanExport() throws Exception {
        mvc.perform(get("/finance/export")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("export:admin"));
    }

    @Test
    void badBasicPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUrlIsDeniedToAuthenticatedUser()
            throws Exception {
        mvc.perform(get("/private-unlisted")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminFullManagerDeniesRememberMeToken() {
        Authentication remembered =
            new RememberMeAuthenticationToken(
                "demo-key",
                "admin",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            );

        HttpServletRequest request =
            new MockHttpServletRequest("GET", "/finance/export");

        AuthorizationDecision decision = adminFullPolicy.check(
            () -> remembered,
            new RequestAuthorizationContext(request)
        );

        assertNotNull(decision);
        assertFalse(decision.isGranted());
    }
}
```

### 10.1. Why Both HTTP Tests and Direct Manager Checks?

- `mvc.perform(...)` tests go through the **real Spring Security filter chain**. `httpBasic(...)` sends Basic headers so the framework verifies username/password rather than mocking a pre-built principal.
- Owner/other-owner/admin cases test **path variable extraction + resource privileges**. If `context.getVariables()` fails to populate `reportId` on the real matcher, the owner test fails and catches the misconfiguration.
- The 401 vs. 403 cases verify **the distinction between authentication and authorization**.
- `adminFullManagerDeniesRememberMeToken` invokes the manager directly to verify remember-me trust evaluation. This test **does not** test remember-me cookie generation; testing real cookies requires configuring remember-me and logging in accordingly.

### 10.2. Why Not Use .with(user("lan")) to Test Basic?

Spring Security Test provides `.with(user(...))` to inject a test `Authentication`. It is useful when testing controllers/policies without exercising an authentication mechanism, yet **does not prove real username/password handling in the HTTP Basic filter**.

Here `httpBasic("lan", "lan-demo")` passes through `BasicAuthenticationFilter`/`AuthenticationProvider` and the password encoder, which is why the test observes 401 on a wrong password.

### 10.3. Why Does a Nonexistent Report Return 403?

The demo's manager returns `AuthorizationDecision(false)` when the ID does not exist. This is an illustrative fail-closed policy. A real API may choose 404 to avoid disclosing resource existence, but that response must be explicitly designed rather than assuming a manager returning null yields 404.

### 10.4. Why Is postWithoutCsrfIsRejected Valuable Even When Controllers Only Have GET?

The test proves the CSRF filter can reject a POST before reaching another HTTP handler. It **does not** prove a POST API is fully designed. When adding write endpoints, test valid CSRF tokens, operation permissions, and business state transitions separately.

## 11. Running Maven, Calling the API, and Reading Results

JDK 17+ and Maven are required. Inside `authorization-manager-demo`:

```bash
mvn test
mvn spring-boot:run
```

With appropriate dependencies and environment, **14 tests are expected to pass**. This is an expectation from the source code, **not** an executed Maven run; build logs and timings vary by machine.

Try on **localhost**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r202
curl -i -u minh:minh-demo http://localhost:8080/reports/r202
curl -i -u admin:admin-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/finance/export
curl -i -u admin:admin-demo http://localhost:8080/finance/export
```

These usernames/passwords are **placeholders** for local HTTP testing only. **Never** send real credentials over plain HTTP, never log passwords, and be mindful of shell history/process listings when using `curl -u`.

| HTTP request | Expected result | Reason |
| --- | --- | --- |
| Anonymous `GET /public` | 200 `public` | `permitAll` |
| Anonymous `GET /reports/r101` | 401, `WWW-Authenticate: Basic` | Missing authentication |
| Lan `GET /reports/r101` | 200 `report:r101:lan` | Lan is the owner |
| Lan `GET /reports/r202` | 403 | Minh's report |
| Minh `GET /reports/r202` | 200 `report:r202:minh` | Minh is the owner |
| Admin `GET /reports/r101` | 200 `report:r101:admin` | Admin role granted |
| Admin `GET /reports/unknown` | 403 | ID absent from store; policy denies |
| Lan `GET /finance/export` | 403 | Missing ROLE_ADMIN |
| Admin `GET /finance/export` | 200 `export:admin` | Full auth + ROLE_ADMIN |
| Lan with wrong password | 401 | Basic authentication failed |
| Admin `GET /private-unlisted` | 403 | `anyRequest().denyAll()` |

**Note:** 401, 403, and 200 in this table depend on the HTTP Basic setup in this example. With form login, blocked anonymous requests can return a 302 redirect to login instead of 401; that is not a difference in `AuthorizationDecision`.

## 12. Standalone Java 17 Example: Separating Policy from HTTP

To understand the essence of allow/deny decisions without Spring Boot, you can run a plain Java 17 program. The model below only simulates Boolean decisions; **it does not construct a real AuthorizationManager, HttpServletRequest, or SecurityContext**.

Create `PolicyDecisionDemo.java`:

```java
import java.util.Map;

public class PolicyDecisionDemo {

    enum Outcome {
        GRANTED, DENIED
    }

    record User(String name, boolean admin) {}

    static final Map<String, String> OWNERS = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    static Outcome canRead(User user, String reportId) {
        String owner = OWNERS.get(reportId);

        if (user == null || owner == null) {
            return Outcome.DENIED;
        }

        boolean allowed = user.admin() || owner.equals(user.name());
        return allowed ? Outcome.GRANTED : Outcome.DENIED;
    }

    public static void main(String[] args) {
        User lan = new User("lan", false);
        User minh = new User("minh", false);
        User admin = new User("admin", true);

        System.out.println("lan r101 -> " + canRead(lan, "r101"));
        System.out.println("lan r202 -> " + canRead(lan, "r202"));
        System.out.println("minh r202 -> " + canRead(minh, "r202"));
        System.out.println("admin r101 -> " + canRead(admin, "r101"));
        System.out.println("admin missing -> " +
            canRead(admin, "missing"));
        System.out.println("anonymous r101 -> " +
            canRead(null, "r101"));
    }
}
```

Compile and run on JDK 17:

```bash
javac PolicyDecisionDemo.java
java PolicyDecisionDemo
```

**Exact** stdout:

```text
lan r101 -> GRANTED
lan r202 -> DENIED
minh r202 -> GRANTED
admin r101 -> GRANTED
admin missing -> DENIED
anonymous r101 -> DENIED
```

This program isolates the decision formula without HTTP Basic, CSRF, method security, or exception handling. The Spring Boot/MockMvc section is what proves the manager runs inside the Servlet filter chain.

## 13. Composing Multiple AuthorizationManagers

Sometimes a decision needs to verify:

```text
GRANT if:
    hasRole("ADMIN")
    AND isFullyAuthenticated()
    AND resource belongs to the right tenant
    AND account is still active
```

There are two common logical combinations:

- **ALL (AND):** every condition must be satisfied.
- **ANY (OR):** at least one branch succeeds.

Spring Security offers utilities like `AuthorizationManagers.allOf` and `AuthorizationManagers.anyOf`. They can reduce boilerplate for built-in managers. However, you must understand how your target version handles denied and abstain results.

### 13.1. A Clear Self-Written Manager

In `AdminFullPolicy` in Section 9, we used:

```java
boolean full = current != null
    && trust.isFullyAuthenticated(current);

boolean isAdmin = current != null
    && current.getAuthorities().stream().anyMatch(
        a -> "ROLE_ADMIN".equals(a.getAuthority()));

return new AuthorizationDecision(full && isAdmin);
```

This is clear, with no null/abstain branches. If the policy also requires tenant checks, add the condition from a trusted data source rather than declaring multiple rules with identical matchers hoping the framework ANDs them.

### 13.2. Avoid Pitfalls When OR-Combining Privileges

For instance, `owner OR admin` makes sense when admins are explicitly permitted to view other users' reports within valid scope. However, "owner OR hasAnyRole(USER, ADMIN)" would let **every USER** read every report whenever that role is present, accidentally voiding ownership.

Tests must include at least one case of a **valid user who does not own the resource**, since anonymous-only tests miss this bug.

### 13.3. Abstain in a Set of Managers

In a composite model, one manager may not apply to a given object. If using `null` to abstain per the older API, clearly define:

- who makes the final decision when all abstain;
- which manager applies to which resource;
- whether a deny can be overridden by another branch's grant in an OR;
- which controls are mandatory and non-bypassable;
- whether a null state can arise from a data error.

**Never design "if all managers abstain, grant by default"** on protected resources unless that is an intentional, audited, and verified policy decision.

## 14. How Is a Deny Decision Turned into an HTTP Response?

### 14.1. Unauthenticated Anonymous Caller

For a `GET /reports/r101` request without a Basic header:

1. The `/reports/{reportId}` rule is selected.
2. The manager finds no authenticated principal and does not grant access.
3. Spring Security determines authentication is needed and invokes the Basic entry point.
4. The client typically receives **401** with `WWW-Authenticate: Basic ...`.

If form login is configured instead of Basic, the exact same deny decision can send a **302 redirect to the login page**. Therefore you cannot read `AuthorizationDecision(false)` and assume the HTTP response is always 403.

### 14.2. Authenticated User Lacking Permission

Lan logs in with valid Basic credentials and sends `GET /reports/r202`:

1. A valid `Authentication` is created.
2. The manager fetches the owner from the store: Minh.
3. Lan is neither the owner nor has `ROLE_ADMIN`.
4. Decision is denied.
5. The HTTP response is typically **403 Forbidden** in an API configuration.

### 14.3. HTTP Status and CSRF Failures

CSRF protection on a POST request can block the request before the manager runs. In that case a 403 response does not prove `ReportAccessPolicy` was called. To identify which policy rejected the request, inspect the security filter flow and write targeted tests.

### 14.4. Authorization Events and Auditing

Some Spring Security configurations can publish authorization grant/deny events via `AuthorizationEventPublisher`. This helps observability when configured properly, yet:

- Do not assume the framework logs every decision by default.
- Never log raw credentials/cookies/session IDs or private resource data.
- Separate **security auditing** from business errors; owner/tenant details must follow privacy policies.
- Never use event listeners with side effects that mutate permissions mid-request as a required part of the decision.

## 15. Performance and Policy Consistency

A custom manager can be invoked frequently. If every check loads large objects or calls external services, latency rises and creates a DoS vector.

Recommendations:

- Optimize lookups to fetch only required columns: `ownerId`, `tenantId`, state, policy version.
- Add proper indexes on privilege tables and report IDs.
- Use caching carefully: recently revoked privileges must not linger beyond SLA.
- Never cache decisions solely by URL while ignoring principal, tenant, action, and timestamp.
- When using distributed authorization, define synchronization lag, timeouts, and fail-closed behavior clearly.
- Watch for race conditions: access checked at the start while resource ownership changes before update. For sensitive writes, re-check inside the transaction at commit time.
- Measure API p95/p99 latency and deny/timeout rates in staging; never assume an authorization manager is "basically free" just because it is a few lines of code.

### 15.1. Multi-Layer Enforcement

Request-level authorization is good for rejecting endpoints early. Yet services may also be invoked from schedulers, message consumers, or other controllers. For sensitive data operations, method security or domain-level checks should serve as an intentional additional layer.

Never put authorization logic in the UI by hiding buttons and assuming the backend is safe. Clients can always send HTTP requests directly to endpoints.

### 15.2. Preventing TOCTOU

TOCTOU (time-of-check to time-of-use) occurs when privilege state changes between policy evaluation and action execution. Example:

```text
T1  request GET /reports/r101: owner verified as lan
T2  report ownership is transferred
T3  service returns r101 contents based on the stale check
```

For simple reads, risk can be reduced by binding owner/tenant constraints directly into the fetch query. For updates with side effects, use transactions, row-level policies, or version/owner conditions. `AuthorizationManager` does not automatically solve all race conditions.

## 16. Common Mistakes

| Mistake | Consequence | Fix direction |
| --- | --- | --- |
| Relying on `Authentication.isAuthenticated()` alone | Anonymous tokens may be treated as real users | Use `AuthenticationTrustResolver` or standard managers |
| Thinking a matching matcher implies granted | Ignores principal and authorities | Separate `RequestMatcher` from `AuthorizationManager` |
| Returning `null` when repository fails | Abstain may be misinterpreted in the pipeline | Return controlled deny/exception; never fail open |
| Returning `true` when `reportId` does not exist | Opens wrong paths, increases data exposure | Fail closed and test missing reports |
| Reading `owner` from client query parameter | Attackers forge query to spoof ownership | Read ownership from server-side store |
| Checking only `ROLE_USER` for all user reports | BOLA/IDOR | Check per-object owner/tenant |
| Thinking `ROLE_ADMIN` implies full login | Remember-me admins still carry the authority | Combine role and trust policy |
| Treating `fullyAuthenticated` as recent MFA | Sensitive actions lack step-up verification | Add recent-auth/MFA controls |
| Putting wildcard `permitAll` before protected rules | Sensitive routes become public | Specific matchers first, deny fallback |
| Adding two rules on the same URL expecting AND | Only the first matching rule applies | Write one combined manager |
| Assuming `AuthorizationDecision(false)` is always HTTP 403 | Actually may be 401 or redirect | Check entry point, authentication, and error handlers |
| Assuming `AuthorizationDecision(true)` means 200 | Controller/service may block or return another status | Distinguish grant from HTTP response |
| Putting heavy DB queries in every matcher | Resource exhaustion, DoS | Put optimized business lookups in policy/service |
| Caching privileges by URL without principal | Cross-user access leaks | Include principal, tenant, action, policy version in cache key |
| Failing to test another owner | Misses IDOR | Maintain a matrix: owner, non-owner, admin, missing |
| Using `with(user(...))` thinking it tests Basic | Bypasses authentication mechanism | Send `httpBasic` through MockMvc |
| Using stateless as an excuse to disable CSRF | Browsers can still auto-send Basic credentials | Evaluate CSRF threat model per API |
| Logging Authorization headers/cookies | Leaks secrets | Audit safe metadata; never log credentials |
| Ignoring multi-node consistency | Slow privilege revocation | Design data/cache/revocation clearly |
| Leaving service calls outside HTTP unprotected | Alternative entry points bypass controller policy | Add method/domain authorization where needed |
| Failing to separate AccessDenied from DB errors | Wrong responses/logs, masks operational failures | Classify exceptions and fail closed |
| Forgetting fallback for new routes | Unprotected endpoints left open | Deny by default and test |

## 17. Debugging When Authorization Differs from Expectations

Check in order:

1. **Right SecurityFilterChain?** Check `securityMatcher` and `@Order` if multiple chains exist.
2. **Which URL rule matched?** Check `requestMatchers` ordering and fallback.
3. **Is Authentication real?** Check Basic header, session, token, or active auth filters.
4. **Who is the current principal?** Watch out for anonymous and remember-me, not just `isAuthenticated`.
5. **Does `T` match the type?** Is `RequestAuthorizationContext` the context the manager expects?
6. **Were path variables extracted?** Does `context.getVariables()` contain `reportId`, matching the MVC matcher?
7. **Where does owner/tenant data come from?** Query the real DB, never client-supplied parameters.
8. **How is AND/OR combined?** Is owner OR admin right for the requirement? Are mandatory conditions bypassed?
9. **What does the manager return?** `AuthorizationDecision(true)`, `false`, `null`, or an exception?
10. **Did the filter enforce the decision?** How do `AuthorizationFilter`, exception translation, and the entry point behave?
11. **401/302 or 403?** Distinguish missing authentication from authenticated user lacking access.
12. **Did CSRF block first?** A POST 403 may be unrelated to the report policy.
13. **Are there more policies in controller/service?** Method security, service ownership, validation, tenancy.
14. **Stale cache or TOCTOU?** Privileges recently changed, request hit another node, ownership transferred.
15. **Spring Security version upgrade?** Check APIs, matchers, `AuthorizationResult`/`AuthorizationDecision`, and exception handling per version.

In development environments you can enable:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log passwords, cookies, Authorization headers, bearer tokens, or real session IDs. Writing a small test from a decision matrix is faster than staring at general logs alone.

## 18. Practice Questions with Answers

**Q1.** What question does `AuthorizationManager<RequestAuthorizationContext>` answer?

**Answer:** It uses `Authentication` and the HTTP context to make an access decision for a matching request. It does not perform password verification, pick the `SecurityFilterChain`, or directly determine the response body/status.

**Q2.** Does `new AuthorizationDecision(false)` always produce HTTP 403?

**Answer:** No. Anonymous Basic API callers can receive 401, and form-login anonymous callers can get a 302 redirect. The response depends on the entry point and exception handling.

**Q3.** What does returning `null` from `check(...)` mean in the Spring Security 6.3.x API?

**Answer:** Abstain/no decision under that contract, never a default grant. Critical terminal policies should return an explicit allow/deny decision.

**Q4.** Why is the first parameter a `Supplier<Authentication>`?

**Answer:** To retrieve `Authentication` lazily only when needed, avoiding dereferencing it in rules like `permitAll`/`denyAll` that do not need a principal.

**Q5.** A request `GET /reports/r202` has owner Minh; Lan has `ROLE_USER`. Will a rule checking only `hasRole("USER")` block Lan?

**Answer:** Not necessarily; if it checks only the role, Lan may get in despite not owning it. Check the specific report's owner/tenant.

**Q6.** Can you trust `?owner=lan` to let Lan read a report?

**Answer:** No. Clients supply query parameters; ownership must come from a trusted server source.

**Q7.** To require both admin role and full authentication on an admin route, can you declare two rules on the same URL expecting both to run?

**Answer:** No; only the first matching rule applies. Use a combined `AuthorizationManager` or composition mechanism with explicit semantics.

**Q8.** Does `AuthorizationDecision(true)` guarantee HTTP will return 200?

**Answer:** No. It only grants access under that policy; controllers, method security, or other filters can still reject or return a different status.

**Q9.** Does a test using `.with(user("lan"))` on the report route prove HTTP Basic passwords work?

**Answer:** No. That injects a pre-built `SecurityContext`. Real Basic testing uses `httpBasic("lan", "lan-demo")` through the filter/provider.

**Q10.** Admin requests a report ID absent from the store; what should the manager do in the demo's fail-closed design?

**Answer:** Return `AuthorizationDecision(false)`; never assume admin may access nonexistent resources. Returning 403 vs. 404 in production requires deliberate API policy design.

**Q11.** Why is testing an authenticated non-owner so important?

**Answer:** It catches BOLA/IDOR flaws that anonymous tests miss. A valid user can still attempt to open another user's resource.

**Q12.** What happens if a policy allows at T1 but resource ownership changes before the service queries at T2?

**Answer:** TOCTOU can occur. Enforce scoped queries/transactions/authorization at the point where data is used, rather than relying solely on an earlier decision.

## 19. Production Checklist

### Before writing a manager

- What resource is protected, which action, and which owner/tenant?
- Is `Authentication` trusted and is the account still active?
- Is the policy ALL or ANY? Can mandatory conditions be bypassed by an OR branch?
- Which manager provides the terminal decision? If abstaining, who handles it?
- Which request inputs are untrusted, and which server data is the authoritative privilege source?
- Can a built-in manager be used instead of custom code?

### Before going to production

- Is there default-deny for unlisted routes?
- Are anonymous, owner, non-owner, admin, unknown ID, and invalid credentials all tested?
- Are 401 vs. 403/redirects verified against the actual entry point?
- Are path variables tested under the deployed `contextPath`/`servletPath`?
- Are CSRF, HTTP methods, rate limiting, and TLS properly configured for the API?
- Are concurrent checks enforced at service/DB level for sensitive operations?
- Are logs/metrics safe without leaking credentials or tenant details?
- Is there a policy for updating/revoking privileges across nodes, caches, and transactions?

## 20. Key Takeaways

- **`AuthorizationManager<T>`** computes authorization decisions from `Supplier<Authentication>` and context `T`.
- **`AuthorizationDecision(true)`** means allow; **`false`** means deny; under the Spring Security 6.3.x contract, `null` can express abstain, **never a default grant**.
- **`RequestMatcher`** determines which rule applies; **`AuthorizationManager`** determines whether the principal is authorized under that rule.
- **`AuthorizationFilter`** enforces decisions in the Servlet chain; exception handling/entry points translate failures into 401, 302, or 403 depending on authentication.
- **`RequestAuthorizationContext`** can provide `HttpServletRequest` and path variables from compatible matchers; path values are untrusted inputs that must be checked against a server-side resource store.
- **Role/authority**, **authentication trust level**, and **object ownership** must be combined properly. Roles do not prove ownership or full/recent MFA.
- **Deny by default**, testing valid non-owner users, and separating policy from HTTP responses are foundational to preventing BOLA/IDOR.
- With Spring Boot 3/Java 17, thoroughly test **anonymous → 401**, **owner/admin → 200**, **non-owner → 403**, **unknown ID → deny**, together with HTTP Basic/CSRF mechanisms to verify policies in the real filter chain.
