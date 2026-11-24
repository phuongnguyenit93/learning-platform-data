# Static Resources, Public Pages, and Admin Endpoints in Spring Security

## 1. Problem statement and objectives

A Spring Boot application has HTML pages, CSS, JavaScript, and business APIs. Unauthenticated users must be able to open the homepage, login page, and images/logos so the UI renders; logged-in users can access their profile page; only administrators may access admin pages and admin APIs. If HTTP permission configuration lacks rigor, two opposite problems easily occur:

- **Accidentally blocking public data:** the login page loads, yet CSS/JS return 401/403, breaking the UI; favicon is blocked; users without an account cannot open the signup page.
- **Accidentally exposing internal data:** setting `/api/**.permitAll()` too broadly; placing `/admin/**.hasRole("ADMIN")` after a permissive `/**` matcher; or bypassing the filter chain entirely for a directory containing user-uploaded files.

This lesson focuses on three groups to distinguish:

1. **Static resources**: CSS, JavaScript, images, fonts, favicon, etc. published publicly by the server.
2. **Public pages/endpoints**: homepage, About, GET login, GET register, and specific intentional public APIs.
3. **Administrative endpoints**: viewing users, changing config, approving/exporting reports, and sensitive operations; requiring server-side permissions.

After this lesson, you will know how to use `authorizeHttpRequests`, `requestMatchers`, `permitAll`, `authenticated`, `hasRole`, and `hasAuthority` in proper order; choose `permitAll` over skipping the filter chain when serving static assets; handle login/CSRF/CORS; protect admin endpoints, multiple filter chains, and object-level permissions; and write tests ensuring sensitive APIs are never accidentally exposed.

**Context:** examples use Spring Security on **Servlet/Spring MVC**, Java 17+, and `SecurityFilterChain`/`HttpSecurity` syntax common in Spring Security 6.x/7.x. Spring WebFlux uses a different API; when integrating, check against the exact Spring Security version resolved by your project's BOM/Gradle/Maven.

## 2. Classification table and design principles

| Request type | Example | Baseline HTTP decision | Notes |
| --- | --- | --- | --- |
| Public CSS/JS/images/fonts | `GET /css/site.css`, `GET /js/app.js`, `GET /images/logo.svg` | `permitAll()` | Keep requests inside the security filter chain |
| Public pages | `GET /`, `GET /about` | `permitAll()` | Only published methods/paths |
| Login page | `GET /login` | `permitAll()` | Controller/view must exist when using a custom login page |
| Public signup | `GET /signup`, `POST /signup` | May be `permitAll()` per API contract | POST still needs CSRF checks where applicable, validation, and abuse prevention |
| User pages | `GET /app/profile` | `authenticated()` | Being logged in is not enough to read someone else's profile |
| Admin pages | `GET /admin/users` | `hasRole("ADMIN")` | Requires `ROLE_ADMIN` per default prefix |
| Admin APIs | `GET /api/admin/users` | `hasRole("ADMIN")` and proper policies | Hiding UI buttons never replaces server authorization |
| High-sensitivity export | `GET /api/admin/reports/export` | Role + permission when policy requires both | Conditions should be combined with **AND** |
| Unlisted URLs | `GET /internal/debug` | `denyAll()` | Deny by default instead of opening automatically |

A system should generally not set all of `/api/**` to `authenticated()` and consider protection done: admin routes and sensitive actions need specific permissions. Nor should the ADMIN role automatically bypass tenant or owner boundaries.

### 2.1. Public differs from anonymous-only

`permitAll()` lets both **unauthenticated and logged-in users** pass that authorization condition. If business logic only wants unauthenticated users to open a route (such as a login-intro page), consider `anonymous()`, without confusing it with `permitAll`. In many products, intro pages stay public for everyone while the UI redirects if already logged in.

### 2.2. Passing the rule does not mean content exists

`permitAll()` only allows passing the **authorization check**; it does not create `site.css` or an `/about` controller. If an asset is not packaged or mapped properly, HTTP can return 404 even when authorization is right. If another filter blocks the request (CSRF, CORS, rate limit, etc.), it can still be rejected.

## 3. Static resources: why use permitAll instead of ignoring?

### 3.1. The approach recommended by Spring Security

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/css/**",
        "/js/**",
        "/images/**",
        "/fonts/**",
        "/favicon.ico"
    ).permitAll()
    .anyRequest().authenticated()
);
```

This is a **configuration fragment** for a `SecurityFilterChain`, not a standalone Java file. Patterns must match the application's actual static asset URLs.

With `permitAll`, the request **still passes through the security filter chain**, without requiring a specific access permission at the HTTP authorization step. Chain capabilities such as security headers and configured protections continue working. According to Spring Security documentation, from version 6 onward, `permitAll` does not need to fetch `Authentication` from the session when no permission is required, reducing reasons to optimize by skipping filters.

**Therefore, for public static resources, prefer `permitAll()` by default.**

### 3.2. Why is `web.ignoring()` not equivalent?

An older `WebSecurityCustomizer` configuration might contain:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/css/**", "/js/**");
}
```

This is an **example for recognizing behavior**, not a recommended config for ordinary scenarios. When a request is handled by `ignoring`, Spring Security **skips its security filters** for that request. If the application relies on the chain to add security headers, they may not be applied to ignored resources.

Never argue "CSS is not secret so skipping filters altogether is always safe." Security headers, response configs, and specialized application filters can still matter for public content. Only skip filters for a request set when an analyzed architectural requirement calls for it, not as a quick fix for CSS 403 errors.

| Approach | Authorization rule | Security filter chain | When to consider |
| --- | --- | --- | --- |
| `permitAll()` | Waives auth/permission requirement on this rule | Configured filters **still run** | **Default** for static assets and public pages |
| `web.ignoring()` | Not processed by Spring Security | **Skips** the chain for the matcher | Very specific exceptions with security review |
| Chain-scoping `securityMatcher` | Rule applies only inside matching chain | Requests outside chain may not be protected by it | Only with intentional multi-chain designs and clear fallbacks |

### 3.3. Common static locations in Spring Boot

When using Spring Boot/Spring MVC's default static resource serving, resources are typically served from classpath locations such as:

```text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
```

For example, `src/main/resources/static/css/site.css` is usually accessed at URL `/css/site.css`, **not** `/static/css/site.css`. However, if an app changes the static path pattern, resource handlers, context path, or servlet mappings, actual URLs can differ. Derive URLs from the active configuration and test real requests.

**Do not confuse directory paths with URL paths.** Having a folder named `static` does not mean a `/static/**` matcher protects requests to `/css/**`.

### 3.4. Using Spring Boot's PathRequest utility when appropriate

In **Spring Boot Servlet**, the `PathRequest.toStaticResources().atCommonLocations()` utility recognizes common static locations:

```java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Inside authorizeHttpRequests:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

This utility **belongs to Spring Boot**, not standalone Spring Security core APIs. It only covers location types defined by the utility; it may miss custom resource handler paths, uploads, or project CDNs. If you need explicit control per URL, use concrete matchers like `/css/**`, `/js/**`, `/images/**` and test them.

### 3.5. Never put private files in public areas

If a system has:

```text
/uploads/
  ├─ invoices/customer-17.pdf
  └─ employee-profiles/private-photo.jpg
```

**Do not** add `/uploads/**` to `permitAll` just because files are accessed by URLs resembling static resources. User-uploaded files can hold sensitive information and require user/tenant/resource permissions. Use a download service with object-level authorization, private storage, or time-limited, scoped signed URLs.

Common vulnerability: hiding a link in the UI while letting anyone fetch the URL directly to download data. Hard-to-guess filenames/UUIDs do not replace permission checks. Public static resource rules apply only to assets **intentionally published publicly**.

## 4. Public pages: configuring by path and HTTP method

A public page does not mean every action on the same path is public in business terms. `GET /signup` shows a form, while `POST /signup` creates an account: both may require no login, yet POST still needs CSRF protection when using cookies/sessions, input validation, rate limiting, and abuse prevention.

### 4.1. Exposing exactly the pages that need to be public

```java
.requestMatchers(HttpMethod.GET,
    "/", "/about", "/help", "/login", "/signup"
).permitAll()

.requestMatchers(HttpMethod.POST, "/signup").permitAll()
```

These matchers illustrate:

- Unauthenticated visitors can view the homepage and login/register pages.
- Opening **POST signup publicly is an explicit business decision**; it does not mean skipping validation, CSRF, or anti-spam.
- Unlisted methods on `/signup` do not inherit access from GET/POST matchers when a `denyAll` fallback exists.

### 4.2. Custom login pages need both GET and POST handling

When using form login, the `GET /login` page rendered by the app can be declared public, while the `POST /login` credential submission is usually handled by Spring Security's authentication filter. Example:

```java
http.formLogin(form -> form
    .loginPage("/login")
    .permitAll()
);
```

- `loginPage("/login")` specifies the custom login page URL. **The application must provide a controller/view** to serve this page; otherwise 404 or redirect loops can occur.
- `permitAll()` in form-login config allows access to login-related URLs per that configuration.
- The authentication filter processes credentials; `permitAll` **does not mean** the user is already authenticated.
- When CSRF is enabled, form POST login requires a valid CSRF token. Use template/tag support or send the token matching the repository mechanism rather than disabling CSRF for easy login testing.

If changing `loginProcessingUrl`, update HTML form `action` and test the new route. When form login uses the default login page without custom configuration, Spring Security can generate a default page; do not assume that behavior applies to custom login pages.

### 4.3. Public APIs still need business policies

For example, `GET /api/catalog` publicly reads products; `POST /api/catalog` requires an admin to create products. A frequent mistake is:

```java
.requestMatchers("/api/catalog/**").permitAll()
```

This configuration can open **all HTTP methods** under that URL branch depending on matcher; it does not restrict public access to GET. A safer configuration:

```java
.requestMatchers(HttpMethod.GET, "/api/catalog", "/api/catalog/*")
    .permitAll()
.requestMatchers(HttpMethod.POST, "/api/catalog")
    .hasAuthority("catalog:create")
```

Principle: authorize by **actual action**, not just URL prefix. If GET must be public without exposing HEAD/OPTIONS or child routes, add explicit policies and tests for those methods/URLs.

## 5. Admin endpoints: roles, authorities, and permission scope

### 5.1. Using roles for administrative feature groups

```java
.requestMatchers("/admin", "/admin/**")
    .hasRole("ADMIN")

.requestMatchers("/api/admin", "/api/admin/**")
    .hasRole("ADMIN")
```

Under default convention, `hasRole("ADMIN")` checks for `ROLE_ADMIN`. A user having only `ADMIN` will **not** pass with the default prefix; check the actual `Authentication.getAuthorities()` granted.

These rules target administrative URL groups and do not imply an ADMIN user can access every resource across **all tenants**.

### 5.2. Authorities for higher-sensitivity actions

Inside `/api/admin/**`, different actions may exist:

| Request | Sample condition | Why |
| --- | --- | --- |
| `GET /api/admin/users` | ADMIN role | View admin list |
| `POST /api/admin/users` | ADMIN role and `user:create` when policy requires | Adding users is a write action |
| `DELETE /api/admin/users/u9` | ADMIN role and `user:delete` | Data deletion risk |
| `GET /api/admin/reports/export` | ADMIN role and `report:export` | Exported data may be sensitive |
| `POST /api/admin/config/reload` | Permission and stronger conditions, audited | Operational impact |

Requiring only the ADMIN role for **every** operation may be too coarse. Conversely, if a sensitive route checks only one permission while the business also mandates the ADMIN role, you must **combine both conditions in one policy**.

### 5.3. Avoiding first-match bugs on special endpoints

**Wrong** if export requires ADMIN role **and** permission:

```java
.requestMatchers(HttpMethod.GET, "/api/admin/reports/export")
    .hasAuthority("report:export")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

`authorizeHttpRequests` matchers apply the **first matching rule**. Export requests are handled by the `report:export` rule; the ADMIN role rule below **is not added on**. A user with export permission but without ADMIN role can pass HTTP authorization.

**Right when AND is needed**: combine `AuthorizationManager`s in one rule:

```java
import static org.springframework.security.authorization.AuthorizationManagers.allOf;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasAuthority;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasRole;

// Inside authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/admin/reports/export")
    .access(allOf(hasRole("ADMIN"), hasAuthority("report:export")))
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

This is an integration fragment requiring `AuthorizationManagers` APIs compatible with your app version. `allOf` requires both conditions. If **ADMIN or SUPER_ADMIN** is desired, `hasAnyRole` works per convention; never use OR when business logic requires AND.

### 5.4. ADMIN role is not omnipotent across all objects

In multi-tenant systems, `ROLE_ADMIN` may mean **tenant admin**. For `DELETE /api/admin/users/u9`, the service still needs to verify:

- The actor actually has admin rights over `u9`'s tenant.
- The target account falls within managed scope.
- Self-deletion or deleting the last remaining admin account is prohibited if required.
- Dual approval, re-authentication/MFA, or an action reason is required if applicable.

Owner/tenant/state/SoD checks belong in domain policies and do not appear automatically via `hasRole("ADMIN")`. HTTP protection is a **gate**, not the whole decision.

## 6. Matcher order and default deny

### 6.1. First-match-wins rule

Within an `authorizeHttpRequests` block, Spring Security scans matcher/rule pairs in **declaration order** and applies the **first matching matcher**. It does not combine all rules with overlapping paths.

Wrong:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

`/api/admin/users` already matches `/**` and is made public; the later ADMIN rule has no effect for that request.

Right:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/", "/login").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

### 6.2. Why is `anyRequest().denyAll()` needed?

`denyAll()` denies requests not declared in the allowlist. This prevents:

- New debug/test URLs from accidentally becoming public.
- New admin endpoints from relying only on a broad `authenticated()`.
- Less common HTTP methods (PUT/DELETE/PATCH) from opening automatically by sharing a GET path.
- Nested or newly versioned routes from skipping policy and test reviews.

Some apps want all remaining paths to require `authenticated()` for rapid rollout. That choice is viable only after **reviewing all routes**; it should not be mistaken for safety equivalent to deny-by-default.

### 6.3. Not all URLs starting with /admin behave alike

`/admin`, `/admin/`, `/administrator`, and `/api/admin` are not automatically covered identically. Use explicit matchers for `/admin` and `/admin/**` if the system needs both. Do not guess framework pattern behavior; test real paths, context paths, and servlet paths with the matcher version used.

### 6.4. Where should static rules go?

In an allowlist configuration, static/public matchers can be placed at the top for readability. However, if the app has **overlapping paths** like `/assets/admin/secret`, check how matchers resolve them. Never place overly broad public wildcards that shadow admin URLs; ideally keep public static namespaces separate from privileged data namespaces.

## 7. Reference configuration for a Spring Boot MVC application

The snippet below is **a Java configuration class** for a Spring Boot project with Spring Web, Spring Security, and Java 17+. It assumes an authentication source, controllers, and resources served at the illustrated URLs. CSRF is **not disabled**. This cannot be run directly with `javac` alone; it needs dependencies and the Spring runtime.

Create `WebAuthorizationConfig.java` in package `com.example.security`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebAuthorizationConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth

            // Resources intentionally published publicly.
            .requestMatchers(
                "/css/**",
                "/js/**",
                "/images/**",
                "/fonts/**",
                "/webjars/**",
                "/favicon.ico"
            ).permitAll()

            // Only listed public GET pages.
            .requestMatchers(
                HttpMethod.GET,
                "/", "/about", "/help", "/login", "/signup"
            ).permitAll()

            // Signup requires no login but still goes through CSRF/validation.
            .requestMatchers(HttpMethod.POST, "/signup")
                .permitAll()

            // Sensitive action: must be admin AND have export permission.
            .requestMatchers(
                HttpMethod.GET,
                "/api/admin/reports/export"
            ).access(AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasRole("ADMIN"),
                AuthorityAuthorizationManager.hasAuthority("report:export")
            ))

            // Admin pages and APIs.
            .requestMatchers(
                "/admin", "/admin/**",
                "/api/admin", "/api/admin/**"
            ).hasRole("ADMIN")

            // Section for all logged-in users.
            .requestMatchers("/app", "/app/**")
                .authenticated()

            // Do not open new endpoints automatically.
            .anyRequest().denyAll()
        );

        http.formLogin(form -> form
                .loginPage("/login")
                .permitAll()
        );

        return http.build();
    }
}
```

### 7.1. Reading the configuration in order

1. `GET /css/site.css` matches static matcher → `permitAll`.
2. `GET /about` is viewable without login; `POST /about` has no public rule → denied by fallback.
3. `GET /login` reaches the public login page; form-login config declares the dedicated login URL.
4. `GET /api/admin/reports/export` matches **first** on the rule requiring both `ROLE_ADMIN` and `report:export`.
5. `GET /api/admin/users` hits the admin rule → `hasRole("ADMIN")`.
6. `GET /app/profile` → `authenticated()`.
7. `GET /internal/debug` → `denyAll()`.

**Do not assume a `permitAll` rule makes POST requests skip CSRF automatically**. With cookie-based sessions and CSRF enabled, `POST /signup`/`POST /login` still need proper token handling. `permitAll` only concerns authorization permissions, not bypassing CSRF protection.

### 7.2. Parts to fill in for a real project

- **Authentication source**: form login uses users/passwords from `UserDetailsService` or an equivalent provider; admins must have `ROLE_ADMIN`.
- **Granting report export permission**: `report:export` must be explicitly granted to authorized principals, not inferred from `ROLE_ADMIN`.
- **Controller/View**: custom `GET /login` and `GET /signup` need handlers/templates; otherwise 404 may occur.
- **AuthenticationEntryPoint/AccessDeniedHandler**: APIs may want JSON 401/403, while web apps may redirect to login.
- **Static resources**: match actual directory URLs, never publicly expose private upload folders.
- **Method/object policies**: export, account changes, and accessing specific resources still require tenant/scope and status checks.

### 7.3. Two consistent ways to organize permissions

Option A: grant both roles and permissions in the authentication source:

```text
GrantedAuthorities:
  ROLE_ADMIN
  report:export
```

Option B: roles describe titles only, and a centrally managed mapping layer translates trusted roles or memberships into application permissions. Test that mapping; Spring Security **does not automatically infer** `report:export` from `ROLE_ADMIN`.

With JWT Resource Server, a scope like `reports.export` is typically mapped by the default converter to `SCOPE_reports.export`, which **differs from** `report:export`. When using token scopes, align rules/mappers where `Authentication` is built; never read arbitrary claims from headers to assign roles.

## 8. Login, logout, CSRF, and CORS: public does not mean dropping protection

### 8.1. CSRF still applies to state-changing requests

For example, `POST /signup` requires no login yet still **mutates data**. In web apps with sessions/cookies, CSRF is a separate threat from authorization. Spring Security typically enables CSRF protection by default in Servlet configs; unsafe methods like POST/PATCH/DELETE require valid tokens in cookie models.

- `permitAll` does not disable `CsrfFilter`.
- When testing `POST /signup` with MockMvc, use `.with(csrf())` if CSRF is enabled in the app.
- For pure Bearer-token apps not relying on auto-sent cookies, the CSRF model can differ; decide based on threat modeling, not upon seeing a 403 error.
- Custom login form POSTs require a CSRF token when protection demands it.
- Do not open blanket CSRF exclusions because one signup page fails to submit tokens properly.

### 8.2. Logout is not an arbitrary public GET

In default Servlet Spring Security configs with CSRF enabled, Spring Security typically uses **POST /logout** to perform logout, preventing another site from forcing a user to log out via a GET link/image. Do not create a side-effecting `GET /logout` just to make "logout a public page." For a logout button, use a POST form with a CSRF token.

### 8.3. CORS preflight

Browsers may send an `OPTIONS` request before calling a cross-origin API. Preflights usually do not carry the same authentication as the main request. If CORS is misconfigured, 401/403 can occur before the actual request reaches the API.

- Configure CORS with an allowlist of origins/methods/headers.
- Ensure preflights are handled properly via Spring Security's CORS integration.
- Never turn all of `/api/admin/**` into `permitAll` to work around a CORS error.
- After a valid preflight, the actual request to an admin endpoint **still requires** authentication, roles, permissions, and object policies.

### 8.4. Headers and caching for public resources

Public resources do not mean skipping security headers: `X-Content-Type-Options`, CSP policies, cache-related headers, and other headers can matter. For content-hashed JS/CSS, long-term caching can be appropriate; for HTML or personalized responses, cache cautiously. Caching and content-security decisions are **distinct** from granting `permitAll`.

Never store access tokens or secrets in static JS/CSS, and never expose source maps containing secrets or environment config files. A public endpoint with accurate permissions is still dangerous if its contents should never have been public.

## 9. Places easily overlooked

### 9.1. /error and dispatcher types

When an app renders error pages or views via `FORWARD` or `ERROR` dispatches, Spring Security may run authorization on the secondary dispatch. Some projects need to permit these dispatch types to render error/view pages, e.g.:

```java
import jakarta.servlet.DispatcherType;

// Inside authorizeHttpRequests if appropriate:
.dispatcherTypeMatchers(
    DispatcherType.FORWARD,
    DispatcherType.ERROR
).permitAll()
```

This is **not mandatory for every app**. Apply only when you understand actual forward/error paths and have verified no data-access bypass is introduced. Do not make `/error` or sensitive views public by default just to handle 403/404 easily. Keep minimal error display pages separate from privileged business actions.

### 9.2. /actuator/** should not be public automatically

Spring Boot Actuator can expose health/metrics/operational endpoints; exposed endpoints and their protection depend on Actuator configuration, separate management ports, and app policy.

- A controlled **subset of health** may be exposed if public monitoring is required.
- Never expose all of `/actuator/**` out of habit.
- Protect metrics, env, heap dump, loggers, or other actuator endpoints based on sensitivity.
- If the management server runs on a separate port/context, test the security chain of that runtime, not just main-app URLs.

### 9.3. API docs and internal consoles

Paths like `/swagger-ui/**`, `/v3/api-docs/**`, `/h2-console/**`, or `/internal/**` need environment-specific policies. Publishing API docs can be intentional for public APIs, yet DB consoles and debug endpoints must never be left open publicly just because they are "used during development."

### 9.4. Frontend SPA routes vs asset files

An SPA may need `GET /app-shell` or `GET /` returning public HTML, while underlying API data remains protected separately. Publicly downloadable JS bundles do not mean APIs called by the bundle are open to read. Never lump client-side `/admin` routes into admin API rules without knowing what the server actually serves; distinguish the public app shell from sensitive API data.

### 9.5. File downloads, object storage, and private images

Invoice files, private profile photos, and ticket attachments should generally **not** be served from static public paths. Use download endpoints with object-level authorization, or signed URLs bound to time/object/scope per design. Permission checks cannot be skipped just because a file ends in `.png` or `.pdf`.

## 10. Multiple SecurityFilterChains: chain scoping vs in-chain authorization

Two easily confused concepts:

- `http.securityMatcher("/api/**")` selects **which requests the entire filter chain applies to**.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...))` sets rules **inside the already-selected chain**.

With multiple chains and `@Order`, Spring Security chooses the first chain whose `securityMatcher` matches. Subsequent chains are not merged on. If no chain matches a request, that request may go unprotected by Spring Security.

### 10.1. Structural example

```java
@Bean
@Order(1)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/css/**", "/js/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/", "/about", "/login")
                .permitAll()
            .anyRequest().denyAll())
        .build();
}
```

These are **two bean fragments** in a `@Configuration` class with required imports and proper authentication/form-login configuration. It illustrates chain scope and does not cover every app case. In Spring Boot, `@Order`, `securityMatcher`, login, and other endpoints should be reviewed together.

Big trap:

```java
http.securityMatcher("/api/admin/**")
    .authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
```

The `denyAll` rule above **does not** protect URLs outside `/api/admin/**` if no appropriate fallback chain exists.

### 10.2. Form login and multiple chains

When a custom chain matches only `/admin/**` while you use the default `/login` endpoint, `/login` requests can **fall outside that chain's scope**. Without a chain supporting login, authentication filters or login pages may fail to work as expected. Ensure requests to login/logout endpoints are handled by the chain configured with the matching filters.

### 10.3. Context path and RequestMatcher strategy

When an app runs under context path `/myapp`, external URLs may be `/myapp/admin/users`, yet Servlet matchers usually do not simply prepend `/myapp` to every pattern. Matching behavior depends on servlet path, MVC mappings, and the version's `RequestMatcher` strategy. Never rely on URL guesswork; test with `MockMvc` or the matching integration environment.

## 11. Standalone Java 17: static/public/admin groups and default deny

The following plain Java program simulates **rule ordering** and role/authority checks so learners can see differences among public, authenticated, and admin. It **does not use Spring Security**, does not replace real `RequestMatcher`s, does not simulate CSRF/CORS/filter chains, and does not return HTTP statuses. The demo's assumptions are documented in code.

Create file `EndpointPolicyDemo.java`:

```java
import java.util.Set;

public class EndpointPolicyDemo {

    record User(boolean authenticated, Set<String> authorities) {
        User {
            authorities = authorities == null
                    ? Set.of() : Set.copyOf(authorities);
        }
    }

    static boolean hasAuthority(User user, String authority) {
        return user != null
                && user.authenticated()
                && user.authorities().contains(authority);
    }

    static boolean hasRole(User user, String role) {
        return hasAuthority(user, "ROLE_" + role);
    }

    static boolean isStatic(String path) {
        return path.equals("/favicon.ico")
                || path.startsWith("/css/")
                || path.startsWith("/js/")
                || path.startsWith("/images/");
    }

    static String check(String method, String path, User user) {
        // Public static assets: no authentication required.
        if (isStatic(path)) {
            return "ALLOW";
        }

        // Only declared public GET pages.
        if (method.equals("GET")
                && (path.equals("/") || path.equals("/about")
                    || path.equals("/login") || path.equals("/signup"))) {
            return "ALLOW";
        }

        // Signup POST allowed at the demo's authorization layer.
        if (method.equals("POST") && path.equals("/signup")) {
            return "ALLOW";
        }

        // Special action before general admin group: requires AND.
        if (method.equals("GET")
                && path.equals("/api/admin/reports/export")) {
            return hasRole(user, "ADMIN")
                    && hasAuthority(user, "report:export")
                    ? "ALLOW" : "DENY";
        }

        // General admin group.
        if (path.equals("/admin") || path.startsWith("/admin/")
                || path.equals("/api/admin")
                || path.startsWith("/api/admin/")) {
            return hasRole(user, "ADMIN") ? "ALLOW" : "DENY";
        }

        // App routes only for authenticated users.
        if (path.equals("/app") || path.startsWith("/app/")) {
            return user != null && user.authenticated()
                    ? "ALLOW" : "DENY";
        }

        // Deny-by-default.
        return "DENY";
    }

    public static void main(String[] args) {
        User guest = new User(false, Set.of());
        User member = new User(true, Set.of("ROLE_USER"));
        User admin = new User(true, Set.of("ROLE_ADMIN"));
        User exporter = new User(true, Set.of("report:export"));
        User adminExporter = new User(
                true, Set.of("ROLE_ADMIN", "report:export"));

        System.out.println("guest-css="
                + check("GET", "/css/site.css", guest));
        System.out.println("guest-home="
                + check("GET", "/", guest));
        System.out.println("guest-login="
                + check("GET", "/login", guest));
        System.out.println("guest-admin="
                + check("GET", "/admin/users", guest));
        System.out.println("member-app="
                + check("GET", "/app/profile", member));
        System.out.println("member-admin="
                + check("GET", "/api/admin/users", member));
        System.out.println("admin-admin="
                + check("GET", "/api/admin/users", admin));
        System.out.println("admin-export-without-permission="
                + check("GET", "/api/admin/reports/export", admin));
        System.out.println("export-permission-without-admin="
                + check("GET", "/api/admin/reports/export", exporter));
        System.out.println("admin-export-with-permission="
                + check("GET", "/api/admin/reports/export", adminExporter));
        System.out.println("public-signup-post="
                + check("POST", "/signup", guest));
        System.out.println("post-about="
                + check("POST", "/about", guest));
        System.out.println("unlisted-route="
                + check("GET", "/internal/debug", admin));
    }
}
```

Run with JDK 17+:

```bash
javac EndpointPolicyDemo.java
java EndpointPolicyDemo
```

Stdout output:

```text
guest-css=ALLOW
guest-home=ALLOW
guest-login=ALLOW
guest-admin=DENY
member-app=ALLOW
member-admin=DENY
admin-admin=ALLOW
admin-export-without-permission=DENY
export-permission-without-admin=DENY
admin-export-with-permission=ALLOW
public-signup-post=ALLOW
post-about=DENY
unlisted-route=DENY
```

**Meaning:**

- Static resources and published GET pages require no authentication.
- Logged-in members can enter `/app/profile` yet do not become admins automatically.
- Export requires **ADMIN role and `report:export` authority**. Missing either condition still blocks access.
- `POST /signup` is public **in the authorization simulation**, without implying CSRF/validation are skipped in a Spring app.
- `POST /about` and undeclared routes are denied; public GET patterns do not open every method.

The demo hand-writes `startsWith`/`equals` for simplicity. In real implementations, **always use Spring Security's matchers and real tests**, because context paths, servlet paths, URL encoding, Spring MVC mappings, and matcher selection can change outcomes.

## 12. Testing with Spring Security Test and MockMvc

### 12.1. Recommended behavior matrix

| Request | Principal/authorities | Goal at the authorization layer |
| --- | --- | --- |
| `GET /css/site.css` | Unauthenticated | Passes public rule |
| `GET /js/app.js` | Unauthenticated | Passes public rule |
| `GET /about` | Unauthenticated | Passes public rule |
| `GET /login` | Unauthenticated | Passes public rule |
| `GET /app/profile` | Unauthenticated | Denied/redirected to login per config |
| `GET /app/profile` | Authenticated user | Passes authenticated rule; may still be blocked by other policies |
| `GET /admin/users` | `ROLE_USER` | DENY |
| `GET /admin/users` | `ROLE_ADMIN` | Passes role rule |
| `GET /api/admin/users` | `ROLE_ADMIN` | Passes role rule |
| `GET /api/admin/reports/export` | Only `ROLE_ADMIN` | DENY |
| `GET /api/admin/reports/export` | Only `report:export` | DENY |
| `GET /api/admin/reports/export` | `ROLE_ADMIN` + `report:export` | Passes AND rule |
| `POST /signup` | Guest, valid CSRF token | Passes authorization; validation still runs |
| `POST /signup` | Guest, missing CSRF when CSRF enabled | May be rejected by CsrfFilter |
| `POST /about` | Guest | DENY per remaining rule |
| `GET /internal/debug` | Even `ROLE_ADMIN` | DENY per fallback |
| `GET /uploads/private.pdf` | Guest | DENY if not declared public |

"Passes rule" **does not always equal HTTP 200**. The controller may not exist, may return 404, or a service may block via another policy. Authorization tests should distinguish reaching the filter/controller from the final business result.

### 12.2. @WithMockUser: roles vs authorities

```java
@WithMockUser(roles = "ADMIN")
```

normally creates a test `Authentication` with authority `ROLE_ADMIN`, without automatically adding `report:export`.

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "report:export"})
```

grants both authorities literally. For the export config requiring AND, this is how to simulate a principal with both permissions in tests. However, mock users do not replace testing mappings from an identity provider/JWT or real user store; if production adds permissions via a converter, test that converter both standalone and integrated.

### 12.3. Useful MockMvc test fragments

The snippets below are **test fragments**, requiring a project with `MockMvc`, Spring Security Test, controllers/fixtures, imports, and corresponding security config; they do not run standalone with `javac`:

```java
@Test
@WithMockUser(roles = "USER")
void ordinaryUserCannotEnterAdmin() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
           .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminWithoutExportPermissionIsDenied() throws Exception {
    mockMvc.perform(get("/api/admin/reports/export"))
           .andExpect(status().isForbidden());
}

@Test
@WithMockUser(authorities = {"ROLE_ADMIN", "report:export"})
void adminWithExportPermissionCanReachHandler() throws Exception {
    mockMvc.perform(get("/api/admin/reports/export"))
           .andExpect(status().isOk());
}
```

The third test can only assert `200` if a matching controller exists, fixture data is valid, the handler returns 200, and no additional policy denies access. A permission-focused test should use endpoints/handlers in a test setup with predictable behavior, rather than assuming satisfying `hasAuthority` forces HTTP 200.

Testing public pages and static resources requires real files/controllers; otherwise 404 is returned even if `permitAll` is right. For form POSTs with CSRF enabled:

```java
mockMvc.perform(post("/signup")
        .with(csrf())
        .param("email", "demo@example.test"))
       .andExpect(/* assertion matching the project's signup contract */);
```

The call above is a **pseudocode test fragment**, and the assertion must match the real contract. In production/complete test code, replace the placeholder comment with a concrete `ResultMatcher`; e.g., `status().is3xxRedirection()` if the signup controller redirects on success. Never rely on 403 to conclude only an authority was missing if the request lacked a CSRF token.

### 12.4. Easily forgotten tests

1. **Real static URLs:** `/css/site.css` and `/favicon.ico` with real guests, confirming files are returned with expected headers.
2. **Public 404:** nonexistent files return 404 rather than redirecting to login just because of security.
3. **Login:** GET login public; POST login with CSRF; POST logout works with CSRF.
4. **Admin role:** only `ROLE_ADMIN` enters admin group; raw `ADMIN` is rejected when default prefix disallows it.
5. **AND export:** role+permission; missing role; missing permission; missing both.
6. **Fallback:** `/internal/debug` or new routes do not open automatically.
7. **Ordering:** `/api/admin/**` is not shadowed by `/api/**` or `/**` public matchers.
8. **Multiple chains:** requests outside the admin chain's `securityMatcher` are still handled safely by another chain.
9. **Object scope:** tenant admins cannot affect other tenants unless policy permits.
10. **CORS/CSRF:** test preflights and real requests; never fix CORS errors by widening authorization.

## 13. Troubleshooting: accidental blocking and accidental exposure

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| Login opens but CSS returns 403/redirect | Missing static `permitAll`, wrong URL matcher, another chain selected | Inspect network URL, request matcher, and actual filter chain |
| CSS returns 404 rather than 403 | Missing resource/wrong URL, not purely an authorization bug | Check classpath, resource handlers, context path |
| Guests can view admin APIs | Overly broad `permitAll`/`authenticated` placed before role rule | Check first-match-wins and test admin paths |
| User with `ADMIN` still gets 403 | `hasRole("ADMIN")` requires `ROLE_ADMIN` by default | Inspect actual authorities |
| Admin with `ROLE_ADMIN` still gets 403 on export | Export rule also requires `report:export` or another business policy | Check AND combination and permission-granting source |
| POST signup gets 403 despite being public | Missing CSRF token or another policy | Check CsrfFilter, form token, test with csrf() |
| Login redirect loop | Custom `GET /login` is protected, handler missing, or chain mismatch | Check `formLogin` + public matcher + controller |
| Swagger/H2 console unintentionally public | Broad `/**` matcher or dev paths opened with wildcards | Permit only intentionally, separate by environment |
| Requests outside /api unprotected | Defined `securityMatcher("/api/**")` without fallback | Audit every `SecurityFilterChain` and `@Order` |
| Static assets lose security headers | Used `web.ignoring()` | Prefer `permitAll` inside chain |
| Users read invoices via static URL | Stored private files under public assets | Move to download endpoint with object authorization |
| Public GET works but CORS preflight fails | CORS not integrated properly; preflight lacks auth | Configure CORS and test OPTIONS + real requests |
| ERROR/FORWARD causes 403 on render | Authorization on secondary dispatch not accounted for | Inspect dispatcher types, error policy; do not open blindly |
| Bug missed because only admin was tested | Guest/ordinary users were not tested | Test matrix of multiple principals and methods |

## 14. Implementation and security review checklist

**Before writing configuration:**

- [ ] List actual URL groups: static assets, public pages, login/register, user area, admin UI, admin APIs, Actuator, and internal endpoints.
- [ ] Distinguish **publicly published resources** from private user files/documents even when they share `.png`/`.pdf` extensions.
- [ ] Identify role/permission sources: `ROLE_ADMIN`, `report:export`; verify naming conventions and where authorities are issued.
- [ ] Define policies for sensitive actions: do they need roles, permissions, tenant/owner, MFA, auditing, or dual approval?
- [ ] Choose matchers matching HTTP method, path, servlet context, and version.

**During configuration:**

- [ ] Use `permitAll` for static/public pages so requests stay in the security chain.
- [ ] Use `formLogin(...).loginPage(...).permitAll()` if using custom form login, with a matching GET handler.
- [ ] Place admin/specific-action matchers before general matchers.
- [ ] If a route requires **two permissions simultaneously**, combine AND in one policy; never place two overlapping matchers expecting both to run.
- [ ] Use `denyAll` for unlisted URLs/methods when implementing an allowlist.
- [ ] Never arbitrarily disable CSRF or open CORS/OPTIONS to silence authorization errors.
- [ ] When using multiple filter chains, provide an appropriate fallback chain for requests outside a chain's scope.
- [ ] Keep `/uploads/**`, internal debug/Actuator endpoints, and sensitive consoles out of public allowlists.

**Before release:**

- [ ] Test static assets and public pages with real guests; verify status and security headers.
- [ ] Test ordinary users denied admin; admins with right role reaching handler; exports lacking permission blocked.
- [ ] Test non-GET methods, nested HTTP paths, undeclared routes, near-match URLs, and edge cases.
- [ ] Test CSRF on POST login/signup/logout and CORS preflight if required by the product.
- [ ] Test that other service/job paths cannot bypass object-level policies.
- [ ] Review logs/monitoring for investigability without leaking tokens, secrets, or private data.
- [ ] Verify exact Spring Security/Boot versions and run regression tests after upgrades.

## 15. Self-check questions

**Question 1.** Why should public static resources use `permitAll` instead of `web.ignoring`?

**Answer:** `permitAll` waives the permission requirement at HTTP authorization while keeping the request in the security filter chain; applicable filters/headers continue working. `ignoring` bypasses the chain, which can lose security headers and other safeguards.

**Question 2.** `GET /signup` is public. Does `POST /signup` become public automatically?

**Answer:** No if the matcher is restricted to HTTP method GET. If unauthenticated registration should be allowed, declare POST per its own contract while keeping CSRF where applicable, validation, and abuse prevention.

**Question 3.** Does `hasRole("ADMIN")` require `ADMIN` or `ROLE_ADMIN` in the default configuration?

**Answer:** `ROLE_ADMIN`. `hasRole` uses a default prefix; if a project configures a custom prefix, verify and test thoroughly.

**Question 4.** A GET export request lies under `/api/admin/**` and has two rules: export `hasAuthority("report:export")` placed before admin `hasRole("ADMIN")`. Are both enforced automatically?

**Answer:** No. The first matching matcher decides. If policy requires ADMIN role **and** export permission, express the AND in a single rule or an intentional, tested additional check layer.

**Question 5.** Does `permitAll` for `/css/**` automatically allow downloading invoices at `/uploads/invoice.pdf`?

**Answer:** Not via that matcher. However, if invoices sit under a broadly allowlisted public folder, data exposure is a real risk. Private files must have object-level authorization or an equivalently protected download mechanism.

**Question 6.** An app has a `securityMatcher("/api/admin/**")` chain with `anyRequest().denyAll()`. Is `/internal/debug` guaranteed to be blocked?

**Answer:** No. Requests outside `/api/admin/**` never enter that chain; a fallback chain must protect the rest.

**Question 7.** `POST /signup` has `permitAll` yet receives 403. Should it be changed to a broader `permitAll`?

**Answer:** No. First determine whether the request was rejected by `CsrfFilter`, a matcher, a controller, or another policy. With CSRF enabled, the form must send a valid token. Broadening permissions fails to fix the root cause and can create vulnerabilities.

**Question 8.** Can an administrator with `ROLE_ADMIN` automatically edit every account across every tenant?

**Answer:** No. A role entering admin features is only one condition. Business policies must also check tenant scope, relationship to the target account, status, and other constraints.

**Question 9.** `GET /css/site.css` has a `permitAll` matcher yet returns 404. Does that prove the authorization rule is wrong?

**Answer:** No. `404` can be caused by a missing file, mispackaged asset, or different URL mapping. Distinguish resource serving from authorization.

**Question 10.** Why not put `requestMatchers("/**").permitAll()` at the top and protect admin below?

**Answer:** The first matching matcher rule applies; `/**` shadows all specific rules below and can expose admin endpoints publicly. Write allowlists by path/method, put sensitive rules first, and use a `denyAll` fallback.

**Summary:** Safe HTTP authorization is not just "open CSS, lock admin." Classify resources properly, use `permitAll` inside the filter chain for public assets, declare GET pages and POST actions per contract, guard admin with specific roles/permissions, never confuse first-match with AND, protect private resources, and test both HTTP and business layers.

## References

- Spring Security — Authorize HttpServletRequests (`permitAll`, `hasRole`, `denyAll`, first-match, static resources): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security — Java configuration and multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet architecture, filter chains, and filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF considerations: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot — Static content and Web MVC: https://docs.spring.io/spring-boot/reference/web/servlet.html
