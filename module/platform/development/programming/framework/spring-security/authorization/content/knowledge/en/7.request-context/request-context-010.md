# Separating API, UI, and Admin Scopes Across Filter Chains

## 1. The Problem: One Application Yet Different Zones Requiring Different Protection

A single Spring Boot application may simultaneously serve three kinds of access paths:

- **API**: `/api/**` accepts bearer access tokens, returns JSON, may serve mobile apps or external systems, and usually expects per-request handling without relying on a UI login session.
- **User Interface (UI)**: `/ui/**`, `/login`, and `/logout` use form login and cookies/sessions; state-changing actions from browsers require CSRF protection.
- **Admin**: `/admin/**` is strictly for administrative privileges; it may share the UI session yet enforce stricter permission policies, step-up authentication, and auditing.

Putting every rule into one security chain makes configuration increasingly tangled: JWT and form login can compete on handling paths; APIs return HTML redirects instead of 401; CSRF might get disabled on the UI just because APIs want statelessness; or regular UI users accidentally reach admin functions. Servlet-based Spring Security allows **multiple `SecurityFilterChain`s**, each with its own match scope and filter set.

Yet splitting chains incorrectly also introduces dangerous bugs: a request falls **outside every chain**, an overly broad chain matches ahead of the admin chain, or `/login` is excluded from the chain containing the login-processing filter.

The goal of this lesson is **splitting protection zones deliberately**, understanding each request's context, building consistent configurations, and testing all entry points alongside authentication/authorization boundaries.

### Selection Flow

```text
              HTTP REQUEST
       method + path + headers + ...
                    |
                    v
            FilterChainProxy
                    |
         evaluate in @Order sequence
                    |
        +-----------+-----------+
        |                       |
    /admin/**?               no
        |                       |
       yes                      v
        |                    /api/**?
        v                    /      \
    ADMIN CHAIN             yes       no
    session / admin         |          |
    authority + CSRF        v          v
                       API CHAIN    UI/FALLBACK
                       bearer JWT   CHAIN
                       stateless    form login
                       API rule     session + CSRF
                          |           |
                          +-----+-----+
                                |
                                v
                        ALLOW / DENY
                                |
                                v
                    Service / object policy
                    tenant, owner, state
```

**Only the first matching `SecurityFilterChain` is selected for a single `FilterChainProxy` pass.** Subsequent chains do not run like cumulative authorization layers. Whenever a request is re-dispatched in Servlet, understand filter registration and match scope for that pass; never assume all chains run sequentially.

## 2. Concepts That Must Be Distinguished

| Component | Role | Common misconception |
| --- | --- | --- |
| `SecurityFilterChain` | List of security filters applying to a group of requests | Not a single permission rule |
| `FilterChainProxy` | Tries `SecurityFilterChain`s in order and picks the first match | Does not run every matching chain |
| `HttpSecurity` | DSL building one security filter chain | Each chain bean can be configured differently |
| `securityMatcher(...)` | Determines **which requests enter this chain** | Different from `requestMatchers(...)` inside authorization |
| `authorizeHttpRequests(...)` | Defines HTTP-level policy for requests already inside the chain | Does not automatically check owner/tenant of every object |
| `requestMatchers(...)` | Selects HTTP rules inside the chain | Declaration order can affect outcomes |
| `@Order` | Defines chain precedence order | Not a priority of authorities or user roles |
| `Authentication` | Verified identity and authorities | Should never be built from raw client headers |
| `SessionCreationPolicy.STATELESS` | Policy not creating/using HttpSession for the chain's SecurityContext | Not a guarantee every app filter is stateless |
| `CsrfFilter` | Protects state-changing requests in CSRF-exposed models | Not a business permission check |
| `AuthenticationEntryPoint` | Responds when authentication must start, e.g., 401 or login redirect | Not the same as insufficient-permission handler |
| `AccessDeniedHandler` | Handles permission denial when valid authentication already exists | Should not turn every 403 into a login redirect |
| Method/object authorization | Checks authorities and conditions of actual resources | Necessary even when the HTTP chain allows through |

### 2.1. `securityMatcher` on the Outside, `requestMatchers` on the Inside

Two methods often appear close together yet have completely different scopes:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/reports/**")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    );
```

- `securityMatcher("/api/**")`: **only requests matching this pattern are evaluated by the filters in this chain**.
- `requestMatchers("/api/reports/**")`: inside the selected API chain, this policy branch requires the report-reading scope.
- `anyRequest().denyAll()`: denies API requests that entered the chain yet matched no allow branch; **does not** protect paths outside `/api/**` if there is no other chain.

Thus, a configuration containing `denyAll()` can still let `/admin/config` slip through if it **creates a chain only for `/api/**`**.

### 2.2. Chain Scope and Business Scope Are Not the Same

A chain may know that `/admin/users/42` is an admin route; yet it cannot know which organization user 42 belongs to, whether the action is self-locking an account or granting roles, or whether dual approval is required. For sensitive actions, permissions must also be verified in services and data queries.

A person holding `ROLE_ADMIN` in tenant A is not automatically allowed to administer users in tenant B. In multi-tenant/multi-realm systems, model role scope explicitly and always verify server-side.

## 3. Designing Protection Zones Before Writing Java

### 3.1. Requirements Matrix

Suppose the system exposes these endpoints:

| Zone | Example path | Expected identity mechanism | Permissions and principles |
| --- | --- | --- | --- |
| API | `GET /api/reports/17` | JWT access token in `Authorization: Bearer ...` | `SCOPE_reports.read` + document permission |
| API | `POST /api/reports` | JWT access token | `SCOPE_reports.write` + business rules |
| UI | `GET /ui/dashboard` | Login session from form | Authenticated user |
| UI | `POST /ui/profile` | Session + CSRF token | Logged-in user, edits only own profile |
| Auth UI | `GET /login`, `POST /login` | Form authentication | Login page/handler must be accepted by the right chain |
| Auth UI | `POST /logout` | Session + CSRF | Logout path in the right chain |
| Admin | `GET /admin/audit` | Login session plus admin conditions | `ROLE_ADMIN` and audit policy |
| Admin | `POST /admin/users/42/disable` | Session + CSRF, admin rights | `ROLE_ADMIN` + object/step-up checks if needed |
| Public | `GET /`, `GET /assets/...` | No authentication required | `permitAll()`, yet still runs through filter chain via fallback |
| Undefined | `/debug`, `/private/download` | Unclear | Default deny |

This is an **illustrative plan**, not a default Spring Security configuration. Each system must select authentication mechanisms per its client contracts.

### 3.2. Ordering Convention

A clear choice:

```text
@Order(1): ADMIN
  securityMatcher("/admin", "/admin/**")

@Order(2): API
  securityMatcher("/api", "/api/**")

@Order(3): UI + FALLBACK
  unrestricted securityMatcher (matches all requests by default)
```

Why place admin ahead of API/UI? To make privilege levels and protection priorities unmistakable; if admin and API zones do not overlap in paths, order may matter less, yet explicit priority aids code review. **Most importantly, matchers must not unintentionally overlap and the fallback must come last.**

For paths, you often need both `/api` and `/api/**` (likewise `/admin`) if the zone's root has an endpoint. Do not guess that every matcher always treats the root and recursive pattern identically across all versions/path parsers. Write tests for the root, trailing slashes, and unexpected variants.

### 3.3. Never Use Unverified Hostnames or Headers as Permission Proof

If `admin.example.com` exists, you can add host/route-based matchers to select a chain. Yet request-carried hosts/headers can be influenced by clients or reverse proxies. Rely on host only after configuring proxies, routing, and trust boundaries properly. Even when an admin host matches, **Authentication and admin permissions must still be verified**.

Similarly, headers like `X-Internal: true` or `X-Role: ADMIN` must never turn a normal user into an admin. Paths/hosts can help classify requests; authorities must come from verified identity sources.

## 4. Spring Security 6 Configuration: Three SecurityFilterChains

This example targets **Spring Boot 3 / Spring Security Servlet 6.x** using lambda DSL configuration; it is not a standalone Java file runnable with `javac` because it requires dependencies, beans, controllers, and an authentication system. The APIs below illustrate zone-splitting intent and must be combined with real application config.

### 4.1. Java Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
@EnableMethodSecurity
public class MultiZoneSecurityConfig {

    // 1. Admin zone: check role, use UI session and CSRF.
    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/admin", "/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("ROLE_ADMIN")
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint("/login")
                )
            );
        // CSRF is not disabled. Admin needs business protection layer.
        return http.build();
    }

    // 2. API for bearer access tokens; does not use UI session.
    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Disable CSRF only because example ASSUMES pure bearer token API
            // in Authorization header, without cookie auth.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }

    // 3. UI, login, and fallback protecting the remainder.
    @Bean
    @Order(3)
    SecurityFilterChain webFallbackChain(HttpSecurity http)
            throws Exception {
        http
            // Do not call securityMatcher: matches all requests by default
            // not yet matched by a higher-precedence chain.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/", "/assets/**"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/error")
                    .permitAll()
                .requestMatchers("/ui/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout.permitAll());
        // Default CSRF is preserved for the form/session application.
        return http.build();
    }
}
```

### 4.2. Conditions for the Sample to Work as Intended

**Do not merely copy the class and assume everything works.** The application needs:

- A valid UI authentication mechanism, such as `UserDetailsService`, `AuthenticationProvider`, or authentication config matching real users. When using default form login, Spring Security auto-generates a login page under appropriate config.
- A `JwtDecoder` and trust setup for the resource server; typically configuring trusted issuer, API audience, signature, expiration, algorithms, and proper scope claims. Never accept ID tokens as API access tokens.
- Users holding matching authorities: for JWT `scope`/`scp` claims, the default converter usually produces the `SCOPE_` prefix; for admin UI, the principal must hold `ROLE_ADMIN` from a trusted source. These two authority forms **do not convert automatically**.
- Real controllers/routes defined for `/ui/**`, `/api/reports/**`, `/admin/**`, and related operations.
- Appropriate session/cookie storage, timeouts, and cookie flags. If admin requires stronger protection, add MFA/step-up, auditing, or dedicated service policies.
- Tests confirming `/login`, `POST /login` handling, logout, and error pages are matched by the right chain. With form login, `permitAll()` on login/logout **allows reaching authentication endpoints**, not performing admin operations.
- Matching CORS, proxy, and frontend config. Never think `csrf.disable()` replaces CORS or vice versa.

### 4.3. Admin Sharing a Session with UI Does Not Mean They Are One Chain

The admin chain in the example **does not declare its own form login**, yet uses `LoginUrlAuthenticationEntryPoint("/login")` to direct unauthenticated callers to the login path belonging to the web fallback chain. After a user logs in via UI and holds a valid session, requests to the admin chain can restore the corresponding `Authentication` from the shared security context/session under standard configuration, and then verify `ROLE_ADMIN`.

This is a deliberate choice: **UI authentication is handled in one place; admin requests remain governed by their own chain**. However, sharing a session means ordinary logged-in users can attempt admin URLs; the admin chain must **check permissions** rather than only `authenticated()`. Logging in through UI does not automatically turn a user into an administrator.

If high admin security is required, you can use separate accounts/identities, OIDC with assurance/MFA claims, an elevated session, or a separate domain. Those designs require explicit handling for session binding, login entrypoints, logout, and callbacks; never assume adding `@Order(1)` created an isolated identity boundary on its own.

### 4.4. When Does the API Not Use the UI Session?

In the sample configuration, the API chain is designed for bearer tokens and `SessionCreationPolicy.STATELESS`. The goals are:

- Every API request carries an appropriate token; do not accept UI form login as an automatic way to call the API.
- When lacking a valid bearer token, protected APIs return an API-client response (typically 401) instead of an HTML login page.
- When a token has scope yet insufficient permissions, APIs typically return 403.
- HttpSession is not used to create/retrieve SecurityContext for API requests under this chain's standard mechanism.

**Do not infer from `STATELESS` that every component creates no sessions or eliminates all CSRF risk.** Custom filters/controllers can still create sessions; and if an API accepts browser auto-sent credentials (cookies or HTTP Basic), CSRF risk must be re-evaluated.

The reason to **disable CSRF only on the bearer-only API chain** is that the sample app requires actively sending access tokens in the `Authorization` header and does not accept cookie authentication on those endpoints. Web UI and admin keep CSRF for state-changing operations. Final decisions must rest on **how browsers actually send credentials**.

### 4.5. Login Paths Can "Disappear" If Placed in the Wrong Chain

In Spring Security, certain filters create internal endpoints—for example, default form login handles `GET /login` and `POST /login`. If you declare:

```java
http.securityMatcher("/ui/**")
    .formLogin(Customizer.withDefaults());
```

with no other chain handling `/login`, login URLs outside the chain's scope may **not be generated/handled by the login filter**, causing 404s or unexpected behavior.

**Approach:** keep form login in the fallback covering `/login` as in the example, or ensure the security matcher of the chain containing form login explicitly includes `/login` and the login processing URL. With a custom login page, provide a valid controller/view and proper permitAll; never mistake `loginPage("/login")` for the framework auto-generating that HTML page once you switch to a custom page.

Likewise, `/logout`, OAuth2 authorization callbacks, SAML assertion consumers, or CSRF token endpoints—if present—must fall within the scope of the chain hosting the corresponding filter.

## 5. Real Request Routing Table Across the Three Chains

Assuming section 4's configuration and required controllers exist.

| Request | Selected chain | Key rule | Example outcome |
| --- | --- | --- | --- |
| `GET /admin/audit` | Admin | `ROLE_ADMIN` | Admin with role enters route; business logic still checks data |
| `GET /admin/audit` with regular UI user | Admin | Missing `ROLE_ADMIN` | Denied (usually 403 if authenticated) |
| `GET /admin/audit` unauthenticated | Admin | Login required | Redirects to `/login` per entrypoint |
| `POST /admin/users/42/disable` | Admin | Role + CSRF + service policy | Does not rely on role alone |
| `GET /api/reports/17` | API | Bearer JWT + `SCOPE_reports.read` | Allowed if token, scope, and resource permissions hold |
| `POST /api/reports` | API | Bearer JWT + `SCOPE_reports.write` | Allowed if scope and workflow hold |
| `GET /api/reports/17` with UI cookie only | API | Missing bearer token | Does not automatically use UI session to pass API |
| `GET /ui/dashboard` | UI/fallback | `authenticated()` | Logged-in UI user allowed |
| `POST /ui/profile` | UI/fallback | Session + CSRF + object policy | Checks profile ownership |
| `GET /login` | UI/fallback | Form login filter | Login page per config |
| `POST /login` | UI/fallback | Login filter + CSRF | Authenticates, does not invoke API JWT |
| `GET /assets/app.css` | UI/fallback | Public static resource | Permitted |
| `GET /private/debug` | UI/fallback | `denyAll()` | Denied |
| `GET /api-admin/audit` | UI/fallback | Matches neither `/api/**` nor `/admin/**` | Denied |
| `GET /admin` | Admin | Role | Does not accidentally fall through to fallback |

In the table, "allowed" at HTTP does not mean object authorization is complete. A user with `SCOPE_reports.read` still needs permission to view report 17 by tenant, owner, or sharing.

### 5.1. What Is a "Gap" Outside All Chains?

With multiple chains, if **every** chain declares a restrictive `securityMatcher` and there is no fallback:

```text
Chain 1: /admin/**
Chain 2: /api/**
Chain 3: /ui/**

GET /debug
  -> matches no chain
  -> FilterChainProxy does not apply security filters
```

If controller `/debug` exists, it can be accessed without passing through Spring Security. This is not "default 403": **there is no chain to enforce any `denyAll` rule**.

A fallback declaring no `securityMatcher`, ending with `anyRequest().denyAll()` after controlled exceptions, prevents this vulnerability. Also verify filter registrations and cases where frameworks or proxies reroute paths elsewhere.

### 5.2. Overly Broad Chain Placed First

Misconfigured example:

```text
@Order(1) WEB CHAIN
  securityMatcher("/**")
  anyRequest().authenticated()

@Order(2) ADMIN CHAIN
  securityMatcher("/admin/**")
  anyRequest().hasRole("ADMIN")
```

For `GET /admin/audit`, the first WEB chain already matches, so the ADMIN chain never runs. If logged in normally, a user can reach the endpoint unless another gate exists. You cannot expect the later chain's admin rule to "override" the earlier chain.

**Fix:** place narrow/sensitive chains first; catch-all fallback last; test real precedence rather than merely spotting `hasRole("ADMIN")` in source code.

### 5.3. `anyRequest().authenticated()` Is Not a Substitute for `denyAll()`

In the fallback, if you write:

```text
/ui/** -> authenticated
anyRequest -> authenticated
```

any new URL like `/private/export` becomes accessible to every logged-in user. When preferring "default deny", declare approved paths and `denyAll()` the rest.

## 6. Different Authentication and State-Management Mechanisms

### 6.1. API: Access Tokens and Resource Server Scope

A JWT resource server validates tokens via `JwtDecoder`, including signature/issuer settings and required conditions like audience/expiry. After authentication, converters construct `Authentication` and authorities, commonly turning scope `reports.read` into `SCOPE_reports.read`.

A valid token issued for another API must not be treated as permission to access this API merely because its signature is valid. Never trust roles from raw `Authorization` headers before token verification. If an API accepts multiple issuers, explicitly define trust per issuer and corresponding mappings.

When an API requires per-resource permissions, authorities are only a functional prerequisite: methods/services/repositories must still verify tenant, owner, state, and quotas.

### 6.2. UI: Form Login and CSRF

UIs normally use session cookies. Browsers can send cookies automatically with requests, including under certain cross-site triggers; therefore state-changing actions require CSRF controls per application policy.

CSRF tokens help prove requests originated from authorized application flows; **they grant no extra business permissions**. Someone holding a CSRF token without permission to edit a profile must still be blocked by the service. Never assume `GET` is always safe if the app performs writes over GET; design state-changing actions with proper methods and protections.

### 6.3. Admin: Login Is Not Synonymous with Administration

An admin may use the same UI form login yet must hold explicitly granted admin privileges with defined scope and duration. Sensitive operations may also require MFA/step-up authentication, tighter session controls, audit logging, independent approval, and network restrictions where suitable.

Those safeguards do not appear automatically by splitting `/admin/**` into a `SecurityFilterChain`. The admin chain must be configured and tested against your actual threat model.

### 6.4. CORS, CSRF, and Sessions Are Separate Decisions

| Mechanism | What does it solve? | What does it not prove? |
| --- | --- | --- |
| CORS | Browser permission to read cross-origin responses per policy | Does not prove user has permission |
| CSRF | Reduces risk of unwanted browser state-changing requests using auto-sent credentials | Does not replace object authorization |
| Authentication | Verified identity/credentials | Does not automatically permit all actions |
| Authorization | Which functions/resources a user may perform/access | Does not replace input validation |
| Session policy | How sessions are used for SecurityContext | Does not automatically disable all other session logic |
| JWT validation | Verifies token issued by trusted issuer for the API | Does not automatically ensure rights on every object |

Splitting chains helps pick mechanisms fitting each zone, without replacing checks between mechanisms.

## 7. Standalone Java 17 Example: Simulating Selecting Exactly One Chain

Before configuring Spring Security, use plain Java to test intuition about **first matching chain**, three identity sources, and fallback. This example **does not simulate all of Spring Security**, performs no real token or session validation, and uses no libraries outside the JDK.

Save file `FilterChainScopeDemo.java`:

```java
import java.util.Set;

public class FilterChainScopeDemo {
    enum Chain { ADMIN, API, WEB }

    record Request(
        String method,
        String path,
        boolean sessionAuthenticated,
        boolean bearerValidated,
        Set<String> authorities
    ) {}

    static boolean inZone(String path, String zone) {
        return path != null
            && (path.equals(zone) || path.startsWith(zone + "/"));
    }

    // Simulate @Order: admin -> api -> web fallback.
    static Chain selectChain(String path) {
        if (inZone(path, "/admin")) {
            return Chain.ADMIN;
        }
        if (inZone(path, "/api")) {
            return Chain.API;
        }
        return Chain.WEB;
    }

    static boolean allowed(Request request) {
        if (request == null || request.method() == null
                || request.path() == null
                || request.authorities() == null) {
            return false;
        }

        Chain selected = selectChain(request.path());

        return switch (selected) {
            case ADMIN ->
                request.sessionAuthenticated()
                    && request.authorities().contains("ROLE_ADMIN")
                    && "GET".equals(request.method())
                    && "/admin/audit".equals(request.path());

            case API ->
                request.bearerValidated()
                    && (
                        ("GET".equals(request.method())
                            && inZone(request.path(), "/api/reports")
                            && request.authorities()
                                .contains("SCOPE_reports.read"))
                        ||
                        ("POST".equals(request.method())
                            && "/api/reports".equals(request.path())
                            && request.authorities()
                                .contains("SCOPE_reports.write"))
                    );

            case WEB ->
                ("GET".equals(request.method())
                    && "/login".equals(request.path()))
                ||
                ("GET".equals(request.method())
                    && "/ui/dashboard".equals(request.path())
                    && request.sessionAuthenticated());
        };
    }

    static Request req(
            String method, String path,
            boolean session, boolean bearer,
            Set<String> authorities) {
        return new Request(
            method, path, session, bearer, authorities
        );
    }

    static void show(String label, Request request) {
        System.out.println(label + ": " + allowed(request));
    }

    public static void main(String[] args) {
        show("admin with admin session",
            req("GET", "/admin/audit", true, false,
                Set.of("ROLE_ADMIN")));

        show("admin missing role",
            req("GET", "/admin/audit", true, false,
                Set.of("ROLE_USER")));

        show("admin bearer only",
            req("GET", "/admin/audit", false, true,
                Set.of("ROLE_ADMIN")));

        show("api bearer read",
            req("GET", "/api/reports/17", false, true,
                Set.of("SCOPE_reports.read")));

        show("api UI session only",
            req("GET", "/api/reports/17", true, false,
                Set.of("SCOPE_reports.read")));

        show("api read scope cannot write",
            req("POST", "/api/reports", false, true,
                Set.of("SCOPE_reports.read")));

        show("ui session access",
            req("GET", "/ui/dashboard", true, false,
                Set.of("ROLE_USER")));

        show("ui bearer only",
            req("GET", "/ui/dashboard", false, true,
                Set.of("SCOPE_reports.read")));

        show("login page",
            req("GET", "/login", false, false,
                Set.of()));

        show("unknown route",
            req("GET", "/private/debug", true, false,
                Set.of("ROLE_ADMIN")));

        show("lookalike prefix",
            req("GET", "/api-admin/reports", true, true,
                Set.of("ROLE_ADMIN", "SCOPE_reports.read")));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac FilterChainScopeDemo.java
java FilterChainScopeDemo
```

Expected stdout:

```text
admin with admin session: true
admin missing role: false
admin bearer only: false
api bearer read: true
api UI session only: false
api read scope cannot write: false
ui session access: true
ui bearer only: false
login page: true
unknown route: false
lookalike prefix: false
```

Key takeaways:

1. Normal logged-in UI users cannot pass the admin chain because they lack `ROLE_ADMIN`.
2. Even carrying authority string `ROLE_ADMIN`, a request with only bearer identity cannot pass the admin rule **in this model**; admin requires a session. In real apps, check which authentication filters run in each chain and which `Authentication` types they accept.
3. API accepts only assuming `bearerValidated=true`. This is an **illustrative flag representing server-verified results**; never read a client-sent flag instead of validating tokens.
4. Users holding a UI session cannot automatically access the bearer-only API.
5. Path `/api-admin/reports` belongs to neither `/api` nor `/admin` because `inZone` checks `/` boundaries. It falls into fallback and is denied.
6. Unknown paths are denied by default. In real Spring Security, the equivalent condition takes effect **only if a fallback chain covers the request**.
7. The program omits CSRF, JWT decoders, session persistence, proxies, and real tenant/owner checks. It only exercises chain selection and necessary conditions.

### 7.1. Small Practice Exercise on the Java Example

Change `selectChain` ordering to return `WEB` for every request before checking admin/API. Observe the simulation output and explain why placing an overly broad chain first prevents later chains from ever being selected. Then restore the safe order.

Add `GET /admin`, `GET /api`, `POST /admin/audit`, and `GET /api/reports/17?format=csv` by modeling method/path explicitly. For queries, do not append `?format=csv` to the path when matching endpoints by path: Servlet and Spring matchers separate path from query.

## 8. Cross-Chain Authentication Bugs and How to Prevent Them

### 8.1. Unintentionally Reusing Form Login for APIs

If an API chain includes form login instead of a resource server, or uses an improperly separated fallback chain, an API client lacking a token can receive `302 Location: /login` with HTML. Clients expecting a 401 JSON error mishandle it, and there is also risk of session cookies acting as credentials on endpoints not designed for them.

Solution: scope the API chain with `securityMatcher`, configure matching authentication (bearer JWT/introspection), and test that UI cookies cannot pass API policies.

### 8.2. Letting Bearer Tokens into the Admin Chain Without Step-Up

Some systems want administration over API tokens; that can be valid, yet must **explicitly design** scope/audience, authentication strength, resource limits, and revocation. Never allow a generic `SCOPE_reports.read` token to perform admin actions just because it has a claim named `admin` or a client-supplied header.

If administration is strictly via web sessions as in the example, do not blindly add `oauth2ResourceServer` to the admin chain. If a separate admin API is required, consider an explicit namespace like `/api/admin/**` with specific permissions, verify chain ordering, and avoid confusing it with `/admin/**`.

### 8.3. Reaching for "Global Admin" Rights to Fix 403 Errors

A user getting 403 on an admin route could be due to missing `ROLE_ADMIN`, wrong chain, missing CSRF, unauthenticated state, or object policy. Never fix it with `.anyRequest().authenticated()` or adding `permitAll()`.

Identify the actual request: which path, which method, which chain entered, which authorities Authentication holds, whether CSRF is required, and which object is accessed. An HTTP 403 may be the intended outcome of business rules or CSRF, insufficient to diagnose without evidence.

### 8.4. Treating `@Order` as a Permission Level

`@Order(1)` means the chain is evaluated **first**, not "privilege level 1 is higher". Users do not have an "order"; they have Authentications/authorities granted by authentication mechanisms and resource policies. When splitting chains, keep route-selection ordering and permission expressions distinct.

## 9. Request Context and Cases with More Than One Processing Pass

### 9.1. Servlet Dispatches and Internal Targets

An HTTP request can involve `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`, or `INCLUDE` passes depending on Servlet flow. If the filter proxy is invoked again on a dispatch pass, the target path and dispatcher type may differ; chain selection may differ as well.

For example, initial request `/ui/reports` is allowed by the UI chain, then MVC forwards to `/WEB-INF/views/reports.jsp`. The target lies outside `/ui/**`; if the filter proxy processes the FORWARD pass, the fallback chain can apply. An overly broad `denyAll()` can prevent views from rendering even when the original request was valid.

You can design **scoped** exceptions for internal view/error dispatches, or use `dispatcherTypeMatchers(...)` when business logic allows, provided you understand:

- Never use "all FORWARDs permitAll" as a way to bypass permissions on sensitive business handlers.
- Which dispatch passes actually traverse which filters depends on filter registration, `OncePerRequestFilter`, and Servlet/container config.
- Direct `REQUEST` calls to sensitive paths must never be permitted merely because that path was once a FORWARD target.
- Method/object policies must still protect sensitive actions if invoked through another entry point.

### 9.2. Reverse Proxies and Context Paths

If the app is published at `/portal/api/reports`, a proxy may rewrite it to `/api/reports` before reaching Servlet. Or the app may have context path `/portal`. Matchers must understand **the path the real Servlet sees**, not guess from browser URLs.

Test root paths, trailing slashes, URL encoding, servlet mappings, proxy prefixes, and lookalike endpoints such as `/api-admin` or `/administrator`. Never hand-roll matchers with `getRequestURI().startsWith("/api")`: it can match `/api-admin` or break under a context path.

### 9.3. Browsers Can Send Both Cookies and Authorization Headers

A request from a browser can carry both a session cookie and `Authorization: Bearer ...`. Which one is accepted depends on **the selected chain and configured filters**. Never decide permissions from raw headers like "has Authorization means API", because attackers can attach arbitrary headers.

With a bearer-only API policy, test that UI cookies cannot establish API Authentication. With session-only admin, test that bearer tokens cannot substitute for sessions unintentionally. If a single endpoint intentionally supports multiple auth mechanisms, explicitly design ordering, boundaries, and permissions for each rather than leaving it to accidental filter behavior.

## 10. Testing: Proving There Are No Gaps or Permission Crossovers

### 10.1. Critical Matrix

| Request / situation | Expected chain | What must be proven |
| --- | --- | --- |
| `GET /admin/audit` | Admin | Requires admin role; regular user 403 |
| `POST /admin/users/42/disable` | Admin | Role + CSRF + policy |
| `GET /api/reports/17` with valid access token | API | Valid scope, valid tenant |
| Same API carrying UI cookie only | API | Does not treat UI session as bearer authentication |
| Same API without token | API | Does not unintentionally redirect to HTML login |
| API token with wrong issuer/audience | API | Decoder rejects |
| API token with read-only scope calling POST | API | Denied |
| `GET /ui/dashboard` unauthenticated | UI | Redirects to login per UI mechanism |
| `POST /ui/profile` missing CSRF | UI | Blocked, no data mutation |
| `GET /login` | UI | Login page exists per selected mechanism |
| `POST /login` valid/invalid | UI | Handled inside chain containing authentication filter |
| `POST /logout` with matching CSRF | UI | Logs out via proper mechanism |
| `GET /assets/app.css` | UI/fallback | Public yet still covered by general protective filters |
| `GET /unknown` | UI/fallback | Default deny |
| `GET /api-admin/...` | UI/fallback | Does not confuse API prefix |
| `GET /admin` | Admin | Admin zone root does not leak to fallback |
| FORWARD/ERROR requests | Chain per dispatch pass | Does not accidentally bypass sensitive handlers |
| Endpoint invoked from background job instead of HTTP | Bypasses HTTP filters | Service/object policies still enforce |

### 10.2. MockMvc for the Three Identity Sources

Below are **integration test snippets**, assuming the app configured `MockMvc`, controllers, Spring Security Test, data, and matching security beans. They are not standalone programs and do not verify real JWT signatures.

JWT test example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/reports/17")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

In this snippet, `SimpleGrantedAuthority` must be imported from `org.springframework.security.core.authority.SimpleGrantedAuthority`. A 200 result holds only if report 17 fixture falls within the principal's scope, the controller exists, and all other policies permit it. The `jwt()` mock helper **does not prove `JwtDecoder` verified signatures/issuer/audience**; test the decoder layer and real authentication integration separately.

Simulated admin session principal example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/admin/audit")
        .with(user("admin").roles("ADMIN")))
    .andExpect(status().isOk());

mockMvc.perform(get("/admin/audit")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());
```

This example uses a fixture allowing audit access; in reality it can still be blocked by method/data policies. For `POST /admin/**` or `POST /ui/**` requests when CSRF is enabled, add `.with(csrf())` in tests **when isolating authorization conditions**. Keep missing-CSRF-token tests separate. Otherwise 403 may come from CSRF without proving role rules work.

### 10.3. Test Chain Selection, Not Just Responses

You can use Spring Security observability in test environments to verify which filter chain was selected for routes. Writing only "API returns 403" is insufficient; it might return 403 from **web fallback deny** while the intended API chain never applied. Verify exact chain boundaries, authentication filters, and response types.

When testing deliberate misconfigurations:

1. Put a broad fallback matcher at `@Order(1)` and verify tests catch that admin/API are no longer selected.
2. Remove the fallback chain and observe out-of-chain requests being skipped, demonstrating why a real config needs a fallback.
3. Put form login in a chain matching only `/ui/**` without `/login`; check whether login endpoints still work.
4. Send a UI cookie to the API; verify the API rejects it when designed bearer-only.
5. Send a user with `ROLE_USER` and no `ROLE_ADMIN` to admin; verify zero side effects.
6. Test admin root `/admin`, API root `/api`, and lookalikes such as `/api-admin`.

**Never apply deliberate misconfigurations to production.** These are isolated test-environment checks to verify test suite sensitivity.

### 10.4. Testing Authority Sources and Lifecycles

When a user's admin role is revoked, a previously created session may retain old authorities depending on architecture. When a JWT still carries old scopes and remains unexpired, the API may keep accepting it until expiry or until additional revocation kicks in.

Splitting chains does not solve stale-permission problems by itself. For admin rights, enforce session lifetimes, step-up, revocation, or dynamic permission checks commensurate with risk. For APIs, scope tokens, audiences, scopes, signing keys, issuers, and caching policies properly. Test the impact of revoking roles right before a sensitive action.

## 11. Common Configuration Mistakes

| Mistake | Risk | Solution |
| --- | --- | --- |
| No fallback chain | URLs matching no chain skip Spring Security | Place a catch-all fallback last |
| High-precedence `/**` fallback | API/admin chains never get selected | Narrow `@Order` first, fallback last |
| Confusing `securityMatcher` and `requestMatchers` | Assuming denyAll protects outside the chain | Verify each chain's scope separately |
| Using `authenticated()` for all of admin | Regular UI users can enter admin | Require `ROLE_ADMIN` and object policies |
| Unintentionally letting UI cookies auth APIs | Shifts auth boundaries, introduces CSRF risk | Bearer-only API chain, explicit tests |
| Disabling CSRF app-wide because APIs are stateless | Form/admin sessions become vulnerable to CSRF | Disable only on the bearer-only chain |
| Using `STATELESS` to claim the whole app has no sessions | UI/admin need sessions, custom code may create them | Distinguish policies per chain |
| Putting form login in a chain not matching `/login` | Login handler never runs | Chain covers the filter's URLs |
| Tokenless API returning HTML redirect | Clients mishandle error | Use API-appropriate authentication entry point |
| `ADMIN` role not matching `ROLE_ADMIN` | Wrong denials or dangerous workarounds | Standardize GrantedAuthorities |
| Granting `authenticated()` to all unregistered requests | New endpoints unexpectedly open to regular users | Default deny |
| Trusting unvalidated `X-Role` headers or hosts | Spoofing admin boundaries | Authenticate principal and trust proxies properly |
| Checking only HTTP permissions | IDOR/BOLA, background job bypass | Method/object authorization |
| Skipping login/logout/CSRF endpoint tests | Broken login, confusing 403s | Test real authentication flows |
| Skipping root and lookalike prefix tests | `/api`, `/admin`, or `/api-admin` hit wrong chain | Test path boundaries |
| Registering custom filters in both servlet and chain | Duplicate runs or wrong ordering | Check filter registration and chains |
| Concluding the right chain ran from a 403 error | Fallback may be blocking instead of API policy | Verify selected chain and cause |
| Believing tokens/sessions auto-revoke on role change | Stale permissions persist until refresh/revocation | Design lifecycle/revocation |

## 12. Practice Exercises

### Exercise 1 — Drawing the Chain Selection Table

List `/admin`, `/admin/audit`, `/api`, `/api/reports`, `/ui/dashboard`, `/login`, `/logout`, `/assets/app.css`, `/api-admin/foo`, and `/unknown`. With order admin → API → fallback, record the selected chain and matching rule. Explain why `/api-admin/foo` is not treated as API.

### Exercise 2 — Running Java 17

Compile `FilterChainScopeDemo.java` and verify the 11 stdout lines. Add cases for `GET /admin`, `GET /api`, and an admin user holding a bearer token without a session. Modify the model so admin requires both a session and a server-verified step-up flag; test cases with and without step-up.

### Exercise 3 — Implementing Three Chains in Spring

Starting from the sample configuration code, add a UI auth provider, an API JWT decoder, and simple controllers. Confirm each chain handles only its intended scope. Write tests for differing responses when the API lacks a bearer token vs. when UI is unauthenticated.

### Exercise 4 — Preventing Admin Exposure from Fallback

Intentionally put `@Order(1)` on a broad fallback with `anyRequest().authenticated()`, and check whether your tests catch the risk of a regular user accessing admin. Restore proper ordering and use `denyAll()` for unlisted requests.

### Exercise 5 — CSRF and Login Flows

Write tests ensuring `POST /ui/profile` without a CSRF token is blocked; with CSRF yet lacking object permission is also blocked. Test `POST /login` and `POST /logout` against real mechanics and tokens. Explain why disabling CSRF solely for the bearer-only API should not affect web/admin.

### Exercise 6 — Resource-Level Permissions

Create two tenants. A tenant-A admin user tries editing a tenant-B user; an API client with `SCOPE_reports.read` reads another tenant's report; a UI user tries editing another person's profile. Write service/repository policies so all three are denied despite matching HTTP chains and functional authorities.

### Exercise 7 — Upgrade and Reverse-Proxy Deployment Testing

Place the app behind a context path or proxy rewrite; test `/api`/`/admin` roots, trailing slashes, login routes, and error paths. Verify `FilterChainProxy` selects the same policy intent in a production-like environment without relying solely on browser-displayed URLs.

## 13. Pre-Production Checklist

- [ ] Documented API/UI/admin scope map plus paths for auth, callbacks, static assets, and errors.
- [ ] Every route matches a protective chain; fallback always comes last.
- [ ] `@Order` and `securityMatcher` create no unintended overlaps.
- [ ] Zone root paths and path variants are tested.
- [ ] APIs accept the right token mechanism, validate issuer/audience/scope, and never accept UI cookies unintentionally.
- [ ] UI has appropriate form login/session handling, with CSRF active on unsafe methods.
- [ ] Admin requires dedicated roles/permissions and enforces sensitive-action/tenant controls.
- [ ] Login, logout, error, and callback routes are covered by the chains containing their filters.
- [ ] `anyRequest().denyAll()` blocks unapproved endpoints in the fallback.
- [ ] Self-claimed headers/hosts/URLs are never used as permission proof.
- [ ] Service methods and data queries enforce object policies.
- [ ] Tests cover missing auth, wrong role, wrong scope, missing CSRF, and cross-tenant attempts.
- [ ] Verified FORWARD/ERROR/ASYNC dispatches if used by the app.
- [ ] Logs capture request correlation, path/method, chain, and outcome without leaking secrets.
- [ ] Plans exist for token/session revocation, key rotation, auditing, and permission reviews.

## 14. Self-Check Questions

1. **How many chains run when two `SecurityFilterChain`s both match a request?** On a single `FilterChainProxy` pass, only the first matching chain.
2. **How does `securityMatcher` differ from `requestMatchers`?** The first selects the whole chain; the second selects rules inside a chain.
3. **If every chain restricts paths and `/debug` matches none, does `denyAll()` in the API chain protect it?** No; a fallback is required.
4. **Why should the admin chain be selected ahead of the fallback?** An overly broad fallback can intercept requests before admin rules are evaluated.
5. **Does successful UI login automatically grant admin permissions?** No; `ROLE_ADMIN` and business policies are still required.
6. **Should a bearer-only API accept UI cookies?** No, if designed bearer-only; verify with real tests.
7. **Does `SessionCreationPolicy.STATELESS` mean CSRF is disabled everywhere?** No; CSRF depends on browser auto-sent credentials and endpoint scope.
8. **Why must `GET /login` be accepted by the appropriate chain?** The form login filter may render/handle login endpoints; excluding it from the matcher breaks functionality.
9. **Should a tokenless API request return an HTML login page?** Normally no; APIs should use client-appropriate entrypoints/responses such as 401.
10. **Does holding `SCOPE_reports.read` allow reading every report?** No; tenant, owner, and object permissions still apply.
11. **Why test `/api-admin/foo`?** To catch overly broad hand-written prefix matchers and avoid wrong zone selection.
12. **Does a 403 prove the admin chain ran properly?** No; it could be fallback deny or a CSRF failure. Verify the actual chain/rule.
13. **Does `@Order(1)` make a user more privileged?** No; it only prioritizes chain selection.
14. **When adding OAuth2 login callbacks or SAML endpoints, what should you check?** Scope of the chain hosting the auth filter/callback, path/entrypoint, CSRF, and tests.
15. **When admin rights are revoked, can you trust existing sessions to lose roles immediately?** Not by default; implement refresh/revocation/dynamic permission policies.

**Remember:** splitting `SecurityFilterChain`s defines **which zone runs which filters and authentication mechanisms**, not three cumulative "permission layers". A secure design requires **specific chains first, fallback last; proper login entrypoints; fitting mechanisms for API/UI/admin; CSRF neither broadened nor disabled mistakenly; and resource-level permissions enforced in services/data**.

### Official Documentation

- [Spring Security 6.5 – Java Configuration and Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)