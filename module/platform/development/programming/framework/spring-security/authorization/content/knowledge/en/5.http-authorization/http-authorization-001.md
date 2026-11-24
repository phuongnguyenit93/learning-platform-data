# Configuring SecurityFilterChain and authorizeHttpRequests in Spring Security

**`SecurityFilterChain`** defines the chain of security filters applied to an HTTP request in a Servlet application. **`authorizeHttpRequests`** is the DSL used to define *which requests are allowed access, which require authentication, and which role or authority is required*, based on the URL, HTTP method, and appropriate `RequestMatcher`s. This is the protective layer at the application's entry point; if an endpoint processes data belonging to individual customers, stores, or tenants, permission checks on the **specific business resource** are still required in the service layer.

This article walks through a working configuration in a **Spring Boot 3.x / Spring Security 6.x project with Java 17+** up to match ordering, multiple filter chains, authentication, CSRF, CORS, testing, and common pitfalls. The Spring examples are code intended to be placed in a project with appropriate dependencies; the standalone Java example at the end is run with plain JDK.

## 1. Understanding the three layers: FilterChainProxy, SecurityFilterChain, and authorizeHttpRequests

An HTTP request passes through the Servlet filter mechanism. Spring Security registers **`DelegatingFilterProxy`** delegating to the **`springSecurityFilterChain`** bean, typically **`FilterChainProxy`**. `FilterChainProxy` iterates through the `SecurityFilterChain`s in order and selects the **first chain whose matcher matches the request**. The selected chain contains security filters for authentication, CSRF, exception handling, authorization, and other configured capabilities.

Within that chain, **`AuthorizationFilter`** enforces the authorization requirements from `authorizeHttpRequests` via an `AuthorizationManager`. It relies on the current `Authentication` and the incoming request; the first matching rule in the DSL determines whether to allow proceeding or deny.

~~~text
Client sends request
       |
       v
Servlet container -> DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +-- select the first SecurityFilterChain matching the request
       |       (securityMatcher, @Order, or match every request)
       v
Security filters in the selected chain
       |
       +-- CORS / CSRF / authentication / security context ...
       |
       v
AuthorizationFilter
       |
       +-- authorizeHttpRequests: select the first matching rule
       |       (requestMatchers + permitAll/hasRole/hasAuthority/...)
       +-- ALLOW: proceed to controller
       +-- DENY : exception/entry point/handler -> 401, 403, redirect...
~~~

**Two different levels of "matching":**

| Component | What does it select? | Scope |
| --- | --- | --- |
| `http.securityMatcher(...)` | Does this **SecurityFilterChain** apply to this request? | Chain-wide level. |
| `authorizeHttpRequests(auth -> auth.requestMatchers(...))` | Within the selected chain, which **authorization rule** applies? | Rule level. |
| `anyRequest()` | All remaining requests **within the current chain**. | Fallback rule of the chain. |
| `@Order` on a `SecurityFilterChain` bean | Priority for trying chains when multiple beans exist. | Chain selection order. |

If there is only one `SecurityFilterChain` that does not call `securityMatcher`, its default matcher protects every request. **If multiple chains are configured and no chain matches a path, that path falls outside Spring Security's security filters.** Therefore, having a fallback chain is an important design decision.

## 2. Project setup and the role of the SecurityFilterChain bean

For a Spring MVC/Servlet application, common Gradle Groovy dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **`dependencies` snippet**, not a complete Gradle file. Use the versions managed by Spring Boot and dependencies matching your project's build system; do not arbitrarily mix Spring Security versions.

The recommended configuration approach in Spring Security 6.x is to expose a **`SecurityFilterChain`** bean via `@Bean`, accept `HttpSecurity`, invoke the required DSLs, and then **`return http.build()`**. The legacy `WebSecurityConfigurerAdapter` was removed in Spring Security 6; do not use `extends WebSecurityConfigurerAdapter` or the legacy `authorizeRequests` / `antMatchers` as the foundation for this article.

In Spring Boot, when a user defines a custom `SecurityFilterChain` bean, the default web security configuration provided by Boot **yields to the custom chain**. This does not mean a chain bean automatically creates a user database, grants authorities, or enables JWT on its own: the **authentication provider, `UserDetailsService`, token decoder, and user store** must still be configured appropriately. Do not confuse having a filter chain with having valid accounts.

## 3. Configuring a SecurityFilterChain: foundational example

Illustrative policy for an order management application:

- `GET /api/catalog/**` is public catalog data.
- `/api/admin/**` is restricted to the `ROLE_ADMIN` role authority.
- `GET /api/orders/**` requires the `ORDER_READ` authority.
- `POST /api/orders` requires the `ORDER_CREATE` authority.
- `/api/profile/**` only requires being authenticated.
- All other requests are **denied by default**.

Create the file **`HttpAuthorizationConfig.java`** in the Java source set of the Spring Boot application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class HttpAuthorizationConfig {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")
                .requestMatchers("/api/profile/**")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a **configuration class that compiles when placed in a Spring Boot project with the stated dependencies**, not a standalone plain Java program run with `javac`; nor does it provide accounts, data, or controllers on its own. `@EnableWebSecurity` explicitly indicates the Servlet security context; in a Boot application with security auto-configuration, this annotation often does not need to be declared manually. `httpBasic(...)` enables HTTP Basic to easily demonstrate unauthenticated results; a real application may choose form login or JWT depending on its architecture.

**Read each line carefully:**

1. `@Bean` registers the `SecurityFilterChain` with Spring; `HttpSecurity` is the chain builder, and `http.build()` is the result placed into `FilterChainProxy`.
2. `authorizeHttpRequests` declares **matcher → authorization requirement** pairs. Specific matches are placed before the fallback rule.
3. `requestMatchers(HttpMethod.GET, "/api/catalog/**")` only allows matching **GET** requests; a `POST` to the same path does not become public because of it.
4. `hasRole("ADMIN")` checks for the `ROLE_ADMIN` authority by default. With `hasAuthority("ORDER_READ")`, the string is matched **literally**, without prepending `ROLE_`.
5. `GET /api/orders/42` passing the `ORDER_READ` rule does not automatically mean Alice is allowed to view order 42: the service still must check **owner, tenant, and status** if required by the business logic.
6. `POST /api/orders` has its own `ORDER_CREATE` rule; for example, it **does not accidentally allow** `POST /api/orders/42/cancel` because no rule has been declared for the cancel action.
7. `anyRequest().denyAll()` prevents requests without an explicit policy from being let through. If a new endpoint needs access, the developer must add a rule in the proper position.

**CSRF remains enabled by default** in this chain. When HTTP Basic is used from a browser, do not mechanically disable CSRF: the browser may automatically send credentials on state-changing requests. If a `POST /api/orders` is sent without a CSRF token, the request can return **403 before reaching AuthorizationFilter**, even if the user has `ORDER_CREATE`. This is **additional protection**, not a bug in `hasAuthority`.

Note that `permitAll` only controls **request authorization**. It neither creates a catalog endpoint nor forces every authentication filter to ignore invalid login credentials. If a controller has no mapping, a permitted request can still return **404 Not Found**.

## 4. Which rule wins? Declaration order and HTTP method

For `authorizeHttpRequests`, each request follows the **first matching matcher**. Matchers **do not accumulate conditions across every matching line**. Therefore, order is a **security-critical** part of the configuration.

An error-prone example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

For `GET /api/admin/users`, the `/api/**` line matches first. The `hasRole("ADMIN")` line is **never applied** to that path; any authenticated user bypasses this HTTP check.

The correct fix for the administrative requirement:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Here `/api/admin/**` is checked first, and only then do other APIs use the broader rule. In cases where `/api/admin/**` has multiple conditions (role **and** permission), the AND must be expressed explicitly via an appropriate manager/policy; two duplicate `requestMatchers` **do not automatically combine** into two conditions.

**The HTTP method is part of the matcher**:

| Request | Rule in section 3 config | Expected behavior of the authorization layer |
| --- | --- | --- |
| `GET /api/catalog/products` | GET catalog → `permitAll` | Allowed to proceed, including anonymous. |
| `POST /api/catalog/products` | No public rule for POST | `denyAll` (other filters may also block earlier). |
| `GET /api/admin/users` | admin → `hasRole("ADMIN")` | Requires the `ROLE_ADMIN` authority. |
| `GET /api/orders/42` | GET orders → `hasAuthority("ORDER_READ")` | Requires `ORDER_READ`; access to Order 42 must still be checked. |
| `POST /api/orders` | POST orders → `hasAuthority("ORDER_CREATE")` | Requires creation permission, and may also require a CSRF token. |
| `DELETE /api/orders/42` | No DELETE orders rule | Denied by default; not inferred from read/create permissions. |
| `GET /api/profile/me` | profile → `authenticated` | Only requires being authenticated. |
| `GET /api/unknown` | `anyRequest().denyAll()` | Denied. |

A matcher like `requestMatchers("/api/orders/**")` **does not restrict the HTTP method** if no `HttpMethod` is passed; use a methodless matcher only when the business logic genuinely wants the same policy for all methods. Avoid accidentally placing `permitAll()` on all of `/api/**` just because one GET needs to be public.

`anyRequest()` must be the last rule in the list; adding rules after it is meaningless because the fallback already catches every request. In applications with multiple servlets or special servlet paths, choose a `RequestMatcher` suited to the actual path and test the matcher instead of guessing how URLs match.

## 5. How is `securityMatcher` different from `requestMatchers`?

Although their names look similar, they operate at **two different layers**. Suppose:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")` limits the **entire chain** to requests under `/api/**`. This chain's filters (CSRF, authentication, authorization, etc.) are only used when the chain is selected.
- `requestMatchers("/api/admin/**")` specifies a **rule inside the chain**. The request `/api/admin/users` requires the ADMIN role.
- `anyRequest().authenticated()` only applies to requests **already filtered into this chain**. It does not automatically protect `/health`, `/login`, or `/admin` outside `/api/**`.

If **this is the only chain** in the application, requests outside `/api/**` may not match any `SecurityFilterChain` at all. As a result, **Spring Security does not protect them**; this is why a fallback chain must be explicitly designed when splitting by URL area.

Distinguish them clearly:

~~~text
FilterChainProxy:
  first matching SecurityFilterChain   <-- securityMatcher + @Order
        |
        v
AuthorizationFilter of that chain:
  first matching authorization rule    <-- requestMatchers + anyRequest
        |
        v
allow / deny
~~~

A `requestMatchers(...).permitAll()` **is not the same** as excluding a path from the security filter chain using `WebSecurityCustomizer.ignoring()`. `permitAll` still lets the request pass through relevant protective filters such as security headers; `ignoring` removes the request from the Spring Security system. For static resources, most applications should prefer `permitAll` in the appropriate chain unless there is a specific measured/operational reason to bypass filters.

## 6. Multiple SecurityFilterChains: Bearer token API and form-login website

When two groups of requests have different authentication mechanisms, **multiple `SecurityFilterChain` beans** can be defined. The following example is **an alternative configuration replacing the single configuration in section 3**; do not copy both sets of beans into the same application without redesigning their ordering.

Example policy:

- API `/api/**` uses **Bearer JWT**, does not use sessions for authentication, and authorizes by scope/authority; allows public catalog access.
- Website outside `/api/**` uses **form login** and sessions.
- `@Order(1)` ensures the API chain is evaluated first; the `@Order(2)` fallback chain covers the remaining paths.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitHttpSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

**Requirements for the API example to work:** needs the OAuth2 Resource Server dependency and a valid JWT decoder configuration (such as issuer URI / JWK Set URI and verification of issuer, signature, and audience per system requirements). The `SCOPE_admin` authority is the **default convention** when the converter reads matching scopes from the JWT, not the `ROLE_ADMIN` role; if the token has another claim, an appropriate converter/mapping is needed. This configuration snippet **does not create a JWT issuer or issue tokens**.

The API policy above requires login for the remaining APIs; it is **not yet a complete business authorization policy** for every action. In practice, add dedicated scopes/permissions per endpoint, method, and resource, replacing `authenticated()` with specific permissions when required by the business logic.

**Why disable CSRF only on the API chain?** This is a choice meant for **APIs that only accept Bearer tokens via headers explicitly sent by the client and do not rely on credentials automatically attached by the browser**. If the API also accepts session cookies, Basic authentication, or browser auto-sent credentials, `STATELESS` **does not make CSRF disappear automatically**; appropriate CSRF protection must be kept or configured. The form-login web chain keeps default CSRF for state-changing operations.

`@Order` selects the **chain**, not the ordering of `requestMatchers` inside a chain. Only **the first matching chain** is selected for a request; other chains do not participate in applying policies together. The fallback chain does not call `securityMatcher`, so by default it receives requests that the API chain does not match; this prevents `/web`, `/login`, and `/assets/**` from falling outside Spring Security.

`formLogin(form -> form.permitAll())` ensures the login endpoint used by form login is accessible despite the general rule requiring authentication. Handling unauthenticated users in the web chain usually redirects to the login page, unlike Bearer APIs which typically return 401.

## 7. `authorizeHttpRequests` does not create an authentication mechanism on its own

Authorization and authentication configurations have related but distinct responsibilities:

| Mechanism | Effect | Example |
| --- | --- | --- |
| `httpBasic(Customizer.withDefaults())` | Reads HTTP Basic credentials to authenticate against available providers. | Client sends `Authorization: Basic ...` header. |
| `formLogin(form -> form.permitAll())` | Configures form/session login per configuration. | Browser is redirected to the login page. |
| `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` | Verifies Bearer JWT, builds Authentication/authorities from JWT. | API receives `Authorization: Bearer ...`. |
| `authorizeHttpRequests(...)` | Checks the request based on `Authentication` and matchers. | `hasRole("ADMIN")`, `authenticated()`. |

For roles, `hasRole("ADMIN")` usually requires `Authentication.getAuthorities()` to contain **`ROLE_ADMIN`**. For `hasAuthority("ORDER_READ")`, it must contain **`ORDER_READ`** verbatim. If a user can log in but receives 403, inspect the authority source and actual rules; do not hastily change `denyAll` to `permitAll`.

In the Basic example in section 3, there is no concrete user store yet; the project needs a `UserDetailsService`, `AuthenticationProvider`, or compatible authentication component with proper password encoding. Do not hard-code sample passwords into production configuration, and do not log tokens or passwords.

With JWT, the `scope`/`scp` claim is normally mapped by the default converter to `SCOPE_...` authorities, whereas a custom claim named `roles` does not automatically become `ROLE_...` in every application. A mapping contract from a trusted issuer must be defined.

`permitAll` does not require fetching `Authentication` to evaluate authorization, but **it does not mean every request carrying invalid credentials is ignored by authentication filters**. A "public" request that sends a malformed or invalid token may still be rejected by an authentication filter, depending on the chain.

## 8. CSRF, CORS, session, and request dispatch still affect the outcome

An HTTP authorization configuration with the right authority names can still return 403 or fail preflight because of other protections.

### CSRF for data-mutating requests

In Servlet applications, Spring Security enables **CSRF protection by default** for potentially state-changing requests (generally other than GET/HEAD/OPTIONS/TRACE). With session cookies or browser auto-sent Basic auth, state-changing operations must be properly protected. `POST /api/orders` with `ORDER_CREATE` can still be rejected by CSRF if the token is missing.

When unit/integration testing a POST request with a valid principal, distinguish carefully:

~~~java
// With a valid CSRF token in MockMvc:
mvc.perform(post("/api/orders")
        .with(user("writer").authorities(
                new SimpleGrantedAuthority("ORDER_CREATE")))
        .with(csrf()));
~~~

This is a **test illustration snippet** requiring `MockMvc`, `spring-security-test`, static imports, and a matching controller; it is not a standalone test class. When testing with CSRF enabled, a 403 from a tokenless request **does not prove** that the `hasAuthority` rule denied it properly.

Only disable CSRF purposefully, typically in **a Bearer-only chain** without browser auto-credentials. If an API supports cookie auth or Basic auth in browsers, arbitrarily disabling CSRF creates risk even if the session policy is STATELESS.

### CORS and OPTIONS preflight

Browsers may send an **OPTIONS preflight** before a cross-origin request. CORS is a different mechanism from user authorization; preflight requests usually **do not contain session cookies**. If CORS protection is misordered, requests may be rejected before the actual endpoint is reached. Configure Spring Security CORS via `.cors(Customizer.withDefaults())` with an appropriate `CorsConfigurationSource` or MVC CORS; only allow trusted origins, methods, and headers.

Do not solve every CORS error by adding `permitAll("/**")`. CORS does not grant permission to read/modify data; the actual request must still go through proper authorization.

### Dispatcher type and error pages

`AuthorizationFilter` may evaluate dispatchers such as `REQUEST`, `ERROR`, and `FORWARD`. An application rendering views or error pages could be denied on the second dispatch if `anyRequest().denyAll()` blocks the error path. When allowed by the application's design, specialized dispatcher rules can be declared **before** other rules:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Only add `permitAll` for dispatchers after evaluating the application; do not treat it as mandatory for every project. The rules in section 3's example are not modified by this snippet unless you actively replace the matcher set.

### Static resources

CSS, JS, images, and public pages should be permitted in the appropriate chain, e.g., `requestMatchers("/assets/**").permitAll()`. `permitAll` is generally preferable to `web.ignoring` because it preserves security headers and related filters. Depending on the application, you must also permit favicon, error pages, login pages, and actual static resources.

## 9. HTTP authorization has limits: a resource ID is not permission

A `GET /api/orders/42` request involves three independent questions:

1. **Does the request enter the configured chain?** Answered by `securityMatcher` or the default matcher of `SecurityFilterChain`.
2. **Is the caller allowed to use the read-order endpoint?** Answered by `authorizeHttpRequests` via `hasAuthority("ORDER_READ")`.
3. **Is the caller allowed to view Order 42 specifically?** Depends on the actual record: owner, tenant, sharing relationship, and status, checked by service/domain policy.

Step 2 returning ALLOW **does not imply** step 3 returns ALLOW. Skipping step 3 easily leads to **IDOR/BOLA**: changing the ID in the URL to view someone else's data despite only having general read permission. In multi-tenant systems, filter queries by tenant/ownership where appropriate and maintain checks at non-HTTP entry points as well.

Example service pattern:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
public OrderDto getOrder(long orderId) {
    Order order = repository.findById(orderId)
            .orElseThrow(NotFoundException::new);
    if (!policy.canRead(currentActor.get(), order)) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(order);
}
~~~

This is **Java-style pseudocode in a Spring-managed service**: `OrderDto`, `repository`, `NotFoundException`, `policy`, `currentActor`, and `mapper` are application components to be implemented; it does not compile as a standalone program. `@PreAuthorize` only takes effect when method security (`@EnableMethodSecurity`) is enabled and the call passes through an appropriate interceptor/proxy. If annotations are not used, the service must still enforce data-level policies itself. For cross-tenant resources, queries can be scoped by tenant directly at the repository level, using a consistent 403/404 strategy to avoid leaking record existence.

In the single-chain example, `AuthorizationFilter` may let `GET /api/orders/42` pass when `ORDER_READ` is present; the service can still deny it afterward if Alice does not own Order 42.

## 10. Expected HTTP outcomes and how to diagnose them

The response also depends on the authentication entry point, access denied handler, other filters, and controller:

| Scenario | Typical outcome | Notes |
| --- | --- | --- |
| Anonymous calls an endpoint requiring a role/authority in an HTTP Basic chain | **401 Unauthorized** | Usually includes a `WWW-Authenticate` header. |
| Anonymous calls an endpoint requiring authentication via form login | **302 Redirect** to login | Another entry point configuration may return 401. |
| Authenticated user lacks role/authority | **403 Forbidden** | Check the actual `GrantedAuthority` strings present. |
| Has role, matches rule, but POST lacks CSRF token | **403 Forbidden** | Caused by the CSRF filter, not necessarily authorizeHttpRequests. |
| `permitAll`, but no controller/handler exists | **404 Not Found** | Passing security does not mean the endpoint exists. |
| No `SecurityFilterChain` matches the request | **Outside Spring Security scope** | Risk that the endpoint is unprotected by security filters. |
| Manager allows at HTTP layer, but service denies owner/tenant | Usually **403/404** | Follows exception mapping and avoids data leakage. |

When investigating a 403 or 401 case, check in order: **which chain matched? which authorization rule won? was authentication created? what authorities exist? did CSRF/CORS filters block it? did service policy deny it?** If there are multiple chains, the very first verification step is **`securityMatcher` and `@Order`**, because selecting the wrong chain puts every rule inside it in the wrong context.

DEBUG logging for `org.springframework.security` can be enabled in test environments to observe filter chains and decisions; avoid sending sensitive information to logging systems, especially tokens and credentials. Do not enable verbose security request logging in production just to track down a matcher bug.

## 11. Testing SecurityFilterChain with MockMvc

When using Spring Boot Test and `spring-security-test`, you can test **DENY cases directly at the HTTP filter level** without depending on a controller. The following test examples assume a Spring Boot project containing the chain bean from section 3:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void orderReaderCannotOpenAdmin() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void orderReaderCannotDeleteOrder() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ORDER_READ")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }
}
~~~

These tests **depend on a Spring Boot project and test dependencies** and do not compile on their own with plain JDK. The first case assumes the Basic entry point from section 3; with form login, the expectation may be a redirect instead of 401. The delete test **includes a valid CSRF token** to prove that `anyRequest().denyAll()` is the actual reason for denial, avoiding a test that passes accidentally due to a missing CSRF token.

To prove an **ALLOW** case, real controller tests are needed, asserting both HTTP status and appropriate body: once filters let the request through, the controller can return 200, 404, or a business error. You should also test undeclared request methods, valid/invalid permissions, specific vs. broad rules, and owner/tenant relationships at the service layer.

If testing the Bearer API from the multi-chain example, use `jwt()` in Spring Security Test or a valid token in an integration test, checking `SCOPE_...` matching the configured converter. `@WithMockUser(roles = "ADMIN")` creates the `ROLE_ADMIN` authority, unlike `@WithMockUser(authorities = "ADMIN")` which uses the literal string `ADMIN`.

## 12. Standalone Java 17+ example: simulating rule ordering

The following example is **not a Spring Security implementation**, but a small model illustrating **first matching rule** and how `hasRole` differs from `hasAuthority`. Path conditions are intentionally simplified with `startsWith`, so never use them instead of real `RequestMatcher`s when implementing security. To mirror the program in section 3, the model checks catalog, admin, GET orders, POST orders in order, and then defaults to DENY.

Save as **`HttpRuleOrderDemo.java`**:

~~~java
import java.util.Set;

public class HttpRuleOrderDemo {
    record Identity(boolean authenticated, Set<String> authorities) {}

    static boolean hasAuthority(Identity who, String authority) {
        return who != null && who.authenticated()
                && who.authorities().contains(authority);
    }

    static boolean hasRole(Identity who, String role) {
        return hasAuthority(who, "ROLE_" + role);
    }

    static boolean allowed(String method, String path, Identity who) {
        if (method.equals("GET") && path.startsWith("/api/catalog/")) {
            return true;
        }
        if (path.startsWith("/api/admin/")) {
            return hasRole(who, "ADMIN");
        }
        if (method.equals("GET") && path.startsWith("/api/orders/")) {
            return hasAuthority(who, "ORDER_READ");
        }
        if (method.equals("POST") && path.equals("/api/orders")) {
            return hasAuthority(who, "ORDER_CREATE");
        }
        return false;
    }

    public static void main(String[] args) {
        Identity guest = new Identity(false, Set.of());
        Identity reader = new Identity(true, Set.of("ORDER_READ"));
        Identity creator = new Identity(true, Set.of("ORDER_CREATE"));
        Identity admin = new Identity(true, Set.of("ROLE_ADMIN"));

        System.out.println("Public catalog: "
                + allowed("GET", "/api/catalog/item-1", guest));
        System.out.println("Anonymous order: "
                + allowed("GET", "/api/orders/42", guest));
        System.out.println("Reader can read: "
                + allowed("GET", "/api/orders/42", reader));
        System.out.println("Reader cannot admin: "
                + allowed("GET", "/api/admin/users", reader));
        System.out.println("Admin can admin: "
                + allowed("GET", "/api/admin/users", admin));
        System.out.println("Reader cannot create: "
                + allowed("POST", "/api/orders", reader));
        System.out.println("Creator can create: "
                + allowed("POST", "/api/orders", creator));
        System.out.println("Unknown path denied: "
                + allowed("GET", "/unlisted", admin));
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac HttpRuleOrderDemo.java
java HttpRuleOrderDemo
~~~

Expected output:

~~~text
Public catalog: true
Anonymous order: false
Reader can read: true
Reader cannot admin: false
Admin can admin: true
Reader cannot create: false
Creator can create: true
Unknown path denied: false
~~~

Key takeaways:

- Public catalog allows anonymous users to proceed because the first rule allows GET catalog.
- `reader` has `ORDER_READ` but does not have `ROLE_ADMIN`, so it cannot enter `/api/admin/**`.
- `creator` has `ORDER_CREATE` but does not automatically have `ORDER_READ`; the two actions must be authorized separately.
- Paths without a rule are **denied**, even for someone with `ROLE_ADMIN`, because the fallback is DENY rather than "ADMIN accesses every URL by default".

The model only evaluates the authorization decision; it does **not** simulate CSRF, Basic/JWT authentication, Servlet dispatch, or whether a user has permission on individual records. Keep this distinction in mind when using stdout to understand a Spring application.

## 13. Common configuration mistakes and how to fix them

1. **Placing `authenticated()` for `/api/**` before `hasRole()` for `/api/admin/**`.** The broad rule swallows the narrow rule. → Put specific rules first; test admin requests with an ordinary account.
2. **Creating only a chain for `/api/**` with no fallback.** Other URLs are unprotected by Spring Security. → Add a final chain matching all requests with an explicit policy.
3. **Confusing `securityMatcher` and `requestMatchers`.** One selects the entire chain; the other selects a rule inside the chain. → Write a URL → chain → rule table to review.
4. **Using `hasAuthority("ADMIN")` when `ROLE_ADMIN` is actually granted.** By default `hasRole("ADMIN")` checks `ROLE_ADMIN`. → Inspect `Authentication.getAuthorities()` and standardize the mapper.
5. **Allowing all HTTP methods on an endpoint just because GET needs to be public.** → Use matchers with `HttpMethod` and separate policies for POST/PUT/DELETE.
6. **Forgetting `http.build()` or failing to register the `SecurityFilterChain` bean.** → Return the built chain from a `@Bean` method and ensure Spring Boot picks up the configuration.
7. **Assuming authorization config automatically enables the desired authentication.** → Configure `httpBasic`, `formLogin`, OAuth2/JWT, and the corresponding identity/authority source.
8. **Disabling CSRF for all APIs upon seeing 403.** → Determine whether requests use cookies/Basic or browser auto-credentials; adjust only for specific architectures.
9. **Ignoring OPTIONS/CORS preflight.** → Configure CORS with proper origins and ordering without opening all endpoints.
10. **Using `WebSecurityCustomizer.ignoring` for data that needs a policy.** Requests bypass security filters. → Use `permitAll` when you only need public content while keeping chain protections.
11. **Checking only the URL without checking the record.** `ORDER_READ` does not prove ownership of Order 42. → Enforce tenant/owner policies in services and queries.
12. **Ignoring `ERROR`/`FORWARD` dispatches and multi-chain order.** → Test dispatch flows and paths outside `securityMatcher`, with an appropriate fallback.
13. **Treating 403 as sole proof of proper authorization.** → CSRF or mismatched authentication mappings can also cause errors; test with proper security contexts and CSRF.
14. **Using legacy Spring Security 5 APIs** like `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`. → With Spring Security 6, use `SecurityFilterChain` beans and `authorizeHttpRequests`; when upgrading to newer lines, check the migration guide for the version in use.

## 14. Checklist when adding a new endpoint to the configuration

Before opening an endpoint such as `POST /api/orders/{id}/cancel`, answer each item:

1. **Which chain protects that path?** If `securityMatcher` is used, are you sure the actual URL and HTTP method match? Is there a fallback when it does not match?
2. **Which rule wins in `authorizeHttpRequests`?** Is the specific rule before broader rules? Does `anyRequest` block the rest?
3. **What kind of authentication is needed?** Session, Basic, Bearer JWT, or another mechanism? From which trusted source do the principal and authorities come?
4. **Which authority is required?** `ORDER_CANCEL`, `ROLE_ADMIN`, or an intentional combination? Avoid using read permissions to allow data modification.
5. **What resource conditions are needed?** Owner, tenant, order status, limits? Are they enforced in the service/policy?
6. **What are the CSRF and CORS needs?** Do browsers auto-send cookies/Basic auth? Are preflights handled properly?
7. **What happens on denial?** Does the API return 401/403/404 as designed, and does the frontend receive a redirect or JSON? Is record existence across tenants leaked?
8. **Which tests prove safety?** Anonymous, wrong role/permission, wrong method, different ID, different tenant, missing CSRF, fallback chain, and matcher-order regression tests.

**Key takeaway:** `SecurityFilterChain` determines **which security filters run for a request**; `authorizeHttpRequests` determines **which HTTP authorization rules apply within that chain**. Secure design requires **accurate chain selection, specific rules before general ones, deny by default, an appropriate authentication mechanism, and record-level permission checks in the service layer when needed**.

### References

- [Spring Security — Java Configuration and Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture and Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
