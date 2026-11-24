# permitAll, denyAll, and authenticated in HTTP Access Rules

> **Module:** Spring Security – authorization  
> **Group:** HTTP Authorization  
> **Scope:** The three rules `permitAll()`, `denyAll()`, and `authenticated()` in `authorizeHttpRequests` on the Servlet stack, URL matching order, impact on anonymous/remember-me users, and how to configure, test, and debug safely.

## 1. Starting from a real API

Suppose an invoicing system has the following paths:

| HTTP request | Business intent |
|---|---|
| `GET /public/catalog` | Anyone can view, even without logging in |
| `GET /account/profile` | Only logged-in users can view the profile |
| `GET /api/invoices/101` | Must be logged in **and** have invoice read permission |
| `POST /api/invoices/101/approve` | Must have approval permission and meet business conditions |
| `GET /internal/debug` | Do not allow access over the web, even for admin accounts |
| An undeclared URL | Deny by default to avoid leaving new endpoints exposed |

Three Spring Security rules address **three different requirements**:

- **`permitAll()`**: requires no permission from the *HTTP authorization rule* mechanism for matching requests.
- **`authenticated()`**: requires a principal recognized by the framework as **authenticated, not anonymous**; does not yet check specific roles or permissions.
- **`denyAll()`**: denies every principal at the *HTTP authorization rule*, even users with administrative authorities.

All three are configured inside `authorizeHttpRequests`. They do not automatically replace CSRF protection, authentication filters, method security, or per-record permission checks. Nor does any rule guarantee by itself that an endpoint exists or returns HTTP 200.

Goal of this article: to be able to look at a `SecurityFilterChain` and answer accurately **which requests pass, why, which protective layers still remain active, and how to test them**.

## 2. Distinguishing authentication, authorization, and HTTP policy

In Servlet Spring Security, you can visualize it as:

~~~text
HTTP request
    |
    v
Selected SecurityFilterChain
    |
    +-- Filters handling protection, CSRF, authentication, ...
    |
    +-- AuthorizationFilter
           |
           +-- Match URL/method/dispatcher against declared rules
           |
           +-- Obtain AuthorizationManager of the first matching rule
           |
           +-- Decision: grant / deny
    |
    v
Controller / Service / Method Security / Database
~~~

**Authentication** verifies the principal and creates an `Authentication` containing the principal and authorities. **HTTP authorization** answers whether a request with a given URL, method, and current principal is allowed to proceed past `AuthorizationFilter`.

This is **not the entire security policy**:

- Passing `authenticated()` only proves the *logged-in* condition per the trust resolver; it does not prove having `invoice:read`.
- Passing `hasRole("ADMIN")` only proves a role at the functional level; it does not automatically prove permission to read another tenant's invoice.
- Passing `permitAll()` only means **this HTTP rule does not deny**; the controller/service can still enforce `@PreAuthorize`, validation, and other business logic.
- Being rejected by `denyAll()` means the request cannot proceed past the HTTP rule, while the exact response—401, 403, or redirect—depends on the authentication state and error handler.

Spring Security does not have to load `Authentication` for **every** rule: some decisions do not require an identity. This explains the performance characteristics and effect of `permitAll`/`denyAll` in the sections below.

## 3. `permitAll()`: permitting at the HTTP authorization layer

Configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated()
);
~~~

Meaning: requests matching `/public/**` do not need a role, authority, or login **to pass the `AuthorizationFilter` rule**. Unauthenticated users, logged-in users, and users with other roles all satisfy this condition.

### 3.1. `permitAll` does not mean "bypass all security"

Because the request still enters the selected `SecurityFilterChain`, other applicable parts can still run:

- CORS and CSRF handling if configured;
- Authentication filters and token validation if the request carries credentials;
- Spring Security's security headers;
- Exploit-protection filters and custom filters;
- Method security and checks at the controller/service layer.

For example, a `POST /public/feedback` with a `permitAll()` rule **can still be rejected for lacking a CSRF token** in a session/cookie-based application if CSRF protection is enabled and applies to that endpoint. `permitAll` is **not a way to disable CSRF**.

Similarly, a request to a public URL carrying a malformed or invalid Bearer token may be rejected by an authentication filter before the `permitAll` rule is even evaluated. Never conclude that `permitAll` guarantees every request receives `200 OK`.

### 3.2. Why use `permitAll` for public resources?

Another option is to configure Spring Security to **completely ignore** a URL (e.g., `web.ignoring()`). When doing so, security filters managed by Spring Security may not run for the ignored URL, including logic that adds security headers. Official documentation recommends preferring `permitAll` over `ignoring` for most static/public resources so they continue benefiting from the security chain's protections.

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                "/css/**",
                "/js/**",
                "/images/**",
                "/login",
                "/about"
        ).permitAll()
        .anyRequest().authenticated()
);
~~~

Here public resources stay inside the protection pipeline; only the **login requirement at HTTP authorization** is waived.

### 3.3. Do not set overly broad public rules

The following configuration is dangerous if the application accidentally exposes data under `/api/**`:

~~~java
// WARNING: illustration of an overly broad rule.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

The `/api/**` rule matches first, so the admin rule is **never evaluated**. Never create a "public exception" with a prefix that blankets sensitive endpoints.

The fix is to permit only **specific** public URLs, and protect sensitive endpoints before broad matchers:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

## 4. `denyAll()`: unconditional denial at the HTTP rule

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/internal/**").denyAll()
        .anyRequest().authenticated()
);
~~~

Any request matching `/internal/**` is denied at the HTTP rule, even if `Authentication` contains `ROLE_ADMIN`.

Useful scenarios:

1. **Block internal paths** that must not be exposed via the web application.
2. **Block deprecated endpoints** whose routes still exist in the source code.
3. **Block paths undergoing migration** to reduce the attack surface.
4. **Fail closed**: with `anyRequest().denyAll()`, any undeclared URL is blocked by default.

Example of the allowlist principle:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
);
~~~

In this snippet, URLs outside `/public/**` and `/api/**` are denied; however, `/api/**` only requires login and is **not safe enough** if it contains APIs needing dedicated permissions. `denyAll` at the end limits the risk of forgetting to declare routes outside the known set, rather than fixing an overly broad matcher placed earlier.

### 4.1. `denyAll()` does not mean "admins only"

These are two opposite rules:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
// ADMIN is allowed if no other rule/protective layer denies.

.requestMatchers("/internal/**").denyAll()
// No one is allowed through this rule.
~~~

If an endpoint is genuinely needed for operations, do not put `denyAll` on it and then try to "bypass" it with a special header. Design an explicit administrative policy, strong authentication, network policy, and auditing if needed.

### 4.2. "Denied" does not mean one fixed status code

For an authenticated user who is denied, the application typically returns **403 Forbidden**. For an unauthenticated user, `ExceptionTranslationFilter` may invoke `AuthenticationEntryPoint`: HTTP Basic typically returns **401**; form login typically **redirects** to the login page. Handler policies can be customized.

Therefore, **`denyAll` means a negative access decision**, not a promise that every caller always receives 403. In tests, account for both the authentication mechanism and exception-handling configuration.

## 5. `authenticated()`: login required, not enough to determine functionality

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Spring Security allows requests through this rule when the principal is recognized as **authenticated** by the trust resolver used by the rule, and **not anonymous**. By default:

- Fully logged-in users: **allowed**;
- Users recognized via remember-me: **usually allowed**;
- Anonymous/unauthenticated users: **not allowed**.

**A very common pitfall:** `AnonymousAuthenticationToken.isAuthenticated()` can return `true`. Yet `authenticated()` in Spring Security is not simply calling `authentication != null && authentication.isAuthenticated()` yourself; the framework has logic to distinguish anonymous tokens. Never assume anonymous users pass `authenticated()` just because the token's flag is true.

### 5.1. Compared with `fullyAuthenticated()`, `anonymous()`, and `rememberMe()`

Related rules (when supported by the API/configuration) serve different goals:

| Rule | Purpose |
|---|---|
| `permitAll()` | No login or authority required at the HTTP rule |
| `authenticated()` | Authenticated user, not anonymous; **may include remember-me** |
| `fullyAuthenticated()` | Fully authenticated user, not relying on remember-me |
| `rememberMe()` | Checks remember-me state as interpreted by the framework |
| `anonymous()` | Only requests considered anonymous |
| `denyAll()` | Allows no one past the HTTP rule |

Sensitive transaction applications may need `fullyAuthenticated()` or step-up authentication, but do not assume this automatically enforces MFA; strong authentication/MFA policies are a separate responsibility.

### 5.2. `authenticated()` does not check permissions

Example:

~~~java
.requestMatchers("/api/invoices/**").authenticated()
~~~

This allows **every authenticated user** through at the HTTP level, even those without `invoice:read`. If the business logic requires permissions, apply appropriate rules:

~~~java
.requestMatchers(HttpMethod.GET, "/api/invoices/**")
    .hasAuthority("invoice:read")
.requestMatchers(HttpMethod.POST, "/api/invoices/**")
    .hasAuthority("invoice:write")
~~~

And check the **specific object** in the service/repository: a user with general invoice read permission may not be allowed to read another user's or tenant's invoice.

**Distinction:** `authenticated()` neither determines "which department you belong to" nor applies a role hierarchy by default. It is merely a baseline identity threshold.

## 6. Core decision table

Consider three representative states: anonymous, remember-me, and fully logged in. Assume no other filter blocks the request, no custom trust resolver or extra policy applies, and the URL matches the rule in question.

| Principal state | `permitAll()` | `authenticated()` | `fullyAuthenticated()` | `denyAll()` |
|---|---|---|---|---|
| Anonymous/not logged in | Allow | Deny | Deny | Deny |
| Remember-me | Allow | Allow | Deny | Deny |
| Fully logged in | Allow | Allow | Allow | Deny |
| Fully logged-in Admin | Allow | Allow | Allow | Deny |

**The table only describes the outcome of the stated HTTP rule**, not the final result of the entire request. A `permitAll` request can still be blocked by CSRF protection, an `authenticated` request can still be denied by method security, and a request to a nonexistent route can still return 404.

## 7. A rule-complete Servlet SecurityFilterChain configuration

The example below is for a **Spring Boot 3.x + Spring Security 6.x project on the Servlet stack** with Spring Web and authentication already configured. It illustrates a full set of rules in a `SecurityFilterChain`, but it is **not a standalone Java program**: the project must provide `UserDetailsService`/authentication providers, controllers, and the corresponding dependencies.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                // 1. Public content: no login required.
                .requestMatchers(
                        HttpMethod.GET, "/public/**").permitAll()

                // 2. Public POST may still require a CSRF token.
                .requestMatchers(
                        HttpMethod.POST, "/public/feedback").permitAll()

                // 3. Profile: login is sufficient at the HTTP layer.
                .requestMatchers(
                        HttpMethod.GET, "/account/profile").authenticated()

                // 4. Business data: requires specific permissions.
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")

                .requestMatchers(
                        HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("invoice:write")

                // 5. Administrative functions.
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")

                // 6. Close off internal endpoints.
                .requestMatchers("/internal/**").denyAll()

                // 7. Remaining URLs: deny.
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### Sequential walkthrough

**Request A: `GET /public/catalog` with no credentials.** Rule GET `/public/**` matches → `permitAll`. The request passes HTTP authorization, and then the controller decides the outcome. It does not guarantee the endpoint exists.

**Request B: `GET /account/profile` from user Lan with valid authentication.** The profile rule matches → `authenticated`. No `ROLE_ADMIN` authority is needed. If the user is not logged in, the entry point handles the authentication challenge.

**Request C: `GET /api/invoices/101` with authority `invoice:read`.** Rule GET invoices matches and the authority is satisfied. You still need to check whether Lan is allowed to read invoice 101 specifically.

**Request D: `POST /api/invoices/101` by a user with only `invoice:read`.** Rule POST invoices requires `invoice:write` → denied for lacking the permission. With CSRF enabled, a browser request may be rejected earlier if missing the token.

**Request E: `GET /api/admin/users` by a user with `ROLE_ADMIN`.** Rule `/api/admin/**` requires the ADMIN role. `hasRole("ADMIN")` checks the authority `ROLE_ADMIN` by default, not the raw string `ADMIN`.

**Request F: `GET /internal/debug` by an admin.** Rule `denyAll` matches → denied despite the admin's broad privileges.

**Request G: `GET /undocumented` by a logged-in user.** `anyRequest().denyAll()` applies → denied per the allowlist.

### Important details of the code

- Path `/public/feedback` is only public for **POST**. GET on the same path is not automatically public.
- `GET /public/**` is public; POST `/public/new-item` is not public by default.
- The **first matching** rule is used; therefore declaration order must be intentional.
- `httpBasic` is just an illustrative authentication mechanism; it is not suitable for every architecture. Production must use HTTPS and appropriate account/credential policies.
- A `permitAll` rule does not disable CSRF. Do not disable CSRF globally just to make an example POST succeed; design around the credential source and browser context.
- For applications that need access to health/metrics or login UI, **declare those endpoints deliberately**, because the `denyAll` fallback blocks all unlisted paths.
- Do not take the `invoice:read` example as evidence that Spring Security grants permissions automatically; the application must map/grant that `GrantedAuthority` from a trusted source.

## 8. Which rule is evaluated first? "First match wins"

In `authorizeHttpRequests`, Spring Security evaluates rules in **declaration order**, and applies the **first rule matching the request**. Subsequent rules do not continue "upgrading" or "tightening" the same request.

Putting a broad rule at the top easily nullifies specific rules:

~~~java
// WRONG if admin must be protected by ROLE_ADMIN.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
);
~~~

`GET /api/admin/users` already matches `/api/**` → only requires login, and **never reaches** the admin rule below.

Fix:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
);
~~~

This illustrates rule precedence, **not that `/api/**` is always safe if it only requires login**. In strict applications, declaring specific permissions per API group and using a `denyAll` fallback is generally safer.

### 8.1. The HTTP method is also part of the matcher

~~~java
.requestMatchers(HttpMethod.GET, "/documents/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/documents/**").hasRole("ADMIN")
.anyRequest().denyAll()
~~~

GET and DELETE have different requirements. If `.requestMatchers("/documents/**").authenticated()` is written first, DELETE can also be caught by the general matcher first and pass through without needing the ADMIN role.

Do not forget PUT, PATCH, HEAD, OPTIONS, or custom methods if the application supports them. Some frameworks/APIs handle HEAD or preflight specially; test actual behavior rather than assuming only GET and POST need protection.

### 8.2. Path matchers do not evaluate query parameters automatically

A rule like `.requestMatchers("/reports/**").authenticated()` typically matches the path portion per the `RequestMatcher` used, **not** authorizing based on `?tenantId=...` or `?owner=...`. If a controller takes a resource ID, check owner/tenant at the actual policy layer. Do not treat path patterns as an object-level authorization solution.

### 8.3. Rule order is not the same as filter order

- **Rule order:** determines which URL rule is selected by `AuthorizationManager`.
- **Filter order:** determines where steps like CSRF, authentication, and authorization run in the request lifecycle.
- **SecurityFilterChain order:** when multiple chains exist, determines **which chain** applies to a request before evaluating rules inside that chain.

These are three separate selection levels; one cannot be used to infer another.

## 9. `anyRequest().authenticated()` or `anyRequest().denyAll()`?

Two common fallbacks:

~~~java
// Style 1: unlisted endpoints still require login.
.anyRequest().authenticated()
~~~

~~~java
// Style 2: unlisted endpoints are all closed.
.anyRequest().denyAll()
~~~

| Criterion | `authenticated()` fallback | `denyAll()` fallback |
|---|---|---|
| New endpoint without a rule yet | Logged-in user can enter the HTTP layer | Cannot enter the HTTP layer by default |
| Suitable for | Apps intentionally protecting all content behind login | Sensitive APIs requiring an explicit allowlist |
| Risk | Forgetting a specific permission leaves a resource open to every logged-in user | Forgetting a rule blocks new features until added |
| Mindset | "Everything belongs to logged-in users except exceptions" | "Nothing is allowed unless explicitly granted" |

**No fallback compensates for a wrong rule placed earlier.** If `/api/**` already has overly broad `permitAll` or `authenticated`, `anyRequest().denyAll()` will not block requests matched by the earlier rule.

For sensitive APIs, **deny by default** and testing newly added endpoints are generally recommended. For login-only pages, an `authenticated` fallback can be suitable if that is an intentional policy rather than an omission.

## 10. `permitAll` and reading `Authentication`: optimization, not skipping security

The `authorizeHttpRequests` architecture commonly uses `AuthorizationFilter` and `AuthorizationManager`. Instead of always fetching `Authentication` upfront, the filter builds a `Supplier<Authentication>` and lets the rule call it only when needed.

~~~text
AuthorizationFilter
     |
     +-- Supplier<Authentication> (retrieved from SecurityContextHolder when needed)
     |
     +-- Matcher selects rule
              |
              +-- permitAll --> allow without calling supplier.get()
              |
              +-- denyAll   --> deny without calling supplier.get()
              |
              +-- authenticated --> requires Authentication state
              |
              +-- hasRole/hasAuthority --> requires authorities
~~~

Consequences:

1. `permitAll` and `denyAll` **do not need to look up Authentication** for this decision itself.
2. This avoids unnecessary session loading in many cases, benefiting public resources.
3. Never assume authentication filters do not run. If a request sends broken credentials, a filter may still report an error **before** authorization.
4. Never assume `SecurityContextHolder` inside a controller is guaranteed to be empty after `permitAll`. If authentication was already established by another part of the chain, the controller can still see it.
5. Never store a "current user" result in a singleton bean when the application handles multiple requests. Always retrieve the context for the current request/invocation.

For a custom `AuthorizationManager`, the API accepts a `Supplier<Authentication>`. Only call `supplier.get()` if the policy needs the identity. For constant decisions, querying it is unnecessary.

## 11. Do not confuse `permitAll` with `securityMatcher` and multiple filter chains

An application can declare multiple `SecurityFilterChain`s, each with a `securityMatcher(...)` and `@Order`. Spring Security selects the **first chain whose matcher matches**, and only then evaluates `authorizeHttpRequests` inside that chain.

Conceptual example:

~~~text
FilterChainProxy
  1. SecurityFilterChain A: matcher /api/**
         internal rules: /api/public/** -> permitAll
                         remaining      -> authenticated
  2. SecurityFilterChain B: matcher /**
         internal rules: /docs/**       -> permitAll
                         remaining      -> denyAll
~~~

If `/api/public/faq` matches chain A, `permitAll` only happens **inside chain A**; chain B does not re-evaluate the request on its own.

More importantly, if all filter chains have overly narrow `securityMatcher`s and a URL matches **no** chain at all, that URL may not be protected by Spring Security. Therefore, when splitting chains by API group, you need a fallback strategy covering the application, rather than merely putting `anyRequest().denyAll()` in a chain that never receives that URL.

Cases requiring special review: actuator endpoints, admin paths, CORS preflight, static resources, error handlers, and login paths.

## 12. Being authenticated does not mean operating on every record

Suppose:

~~~java
.requestMatchers(HttpMethod.GET, "/api/invoices/**").authenticated()
~~~

Lan and Binh are both logged in. Lan calls `GET /api/invoices/102`, but invoice 102 belongs to Binh. The HTTP rule still lets Lan through because the condition is only "logged in".

A **horizontal unauthorized access/BOLA** vulnerability occurs if the service fetches the invoice by ID and returns it directly without checking owner/tenant.

Use multi-layered control:

~~~text
HTTP authorization:
    Logged in? Has invoice:read permission?
         |
         v
Service / use-case policy:
    Correct tenant? Is owner? Shared? Valid status?
         |
         v
Repository:
    Query/UPDATE scoped to the authorized data
~~~

An illustrative Spring-managed service method:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('invoice:read') " +
    "and @invoicePolicy.canRead(authentication, #id)"
)
public InvoiceDto readInvoice(long id) {
    return invoiceQueryService.read(id);
}
~~~

This is only an **illustrative method**; it requires enabling `@EnableMethodSecurity` and providing `invoicePolicy`, `InvoiceDto`, and `invoiceQueryService`, while ensuring `#id` is resolved properly. It cannot run with plain JDK. It reminds us that `authenticated` is a minimum threshold, not a policy for sensitive resources.

Conversely, `permitAll` at the HTTP layer does not force the service to drop `@PreAuthorize`. If the service has its own policy, it can still deny after the request passes the HTTP rule. Avoid unintentional conflicts between HTTP and service configurations: align policies with tests.

## 13. CSRF, CORS, and protected resources: other layers still exist

### 13.1. Public POST and CSRF

Suppose:

~~~java
.requestMatchers(HttpMethod.POST, "/public/feedback").permitAll()
~~~

An anonymous user calls `POST /public/feedback`. In a Servlet configuration with CSRF protection enabled for unsafe methods, a request without a matching CSRF token may be rejected.

That **does not prove `permitAll` is broken**. It shows CSRF is a **separate** protective layer from HTTP authorization rules.

Handling decisions depend on the architecture:

- Cookie/session-based browser apps: keep appropriate CSRF protection and supply tokens where needed.
- Header-based Bearer token APIs that do not use browser auto-sent credentials: CSRF can be designed differently, but you must carefully evaluate how clients actually authenticate and the risk of request forgery.
- If an endpoint needs a CSRF exception, configure a narrow exception scope, document the risk, and write negative tests. **Do not disable CSRF globally just to make `permitAll` work for POST.**

### 13.2. CORS preflight

Browsers may send an `OPTIONS` preflight before a cross-origin request. If a rule/chain rejects OPTIONS without valid CORS configuration, the frontend may report errors even when the main GET/POST has the right rules.

Use proper CORS integration with Spring Security and configure origins/methods/headers intentionally. Do not arbitrarily `permitAll` all OPTIONS requests to "fix" an error without reviewing the CORS policy. And **CORS is not authorization**: a non-browser request can still be sent directly to the server.

### 13.3. Static assets and security headers

Prefer `permitAll` for public CSS/JS/images so they continue receiving appropriate security headers. Adding URLs to an ignore list or removing them from the entire filter chain can lose those protections.

### 13.4. `FORWARD`, `ERROR`, and dispatcher forwarding

In Servlets, `AuthorizationFilter` can be applied to multiple dispatcher types, not only the initial request. Spring MVC view forwards and error-handling pages can trigger a new dispatch that requires reviewing rules.

You can configure `dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()` **when the application genuinely needs it**, though opening entire dispatcher types must be weighed carefully so it does not create a bypass path into sensitive internal content. Do not automatically assume every forward is harmless.

## 14. 401, 403, redirect, or 404: reading outcomes accurately

| Scenario | Typical behavior | Notes |
|---|---|---|
| Unauthenticated user hits `authenticated()`, using HTTP Basic | `401 Unauthorized` + challenge | Depends on authentication entry point |
| Unauthenticated user hits `authenticated()`, using form login | Redirect to login | Does not necessarily return 401 JSON |
| Logged-in user lacks `hasAuthority`/`hasRole` | `403 Forbidden` | Depends on access-denied handler |
| Logged-in user hits `denyAll()` | Usually 403 | Cannot pass the rule merely with a higher role |
| Anonymous user hits `denyAll()` | May trigger entry point/401/redirect | Not forced to always return 403 |
| `permitAll()` on a nonexistent route | May return 404 | Passing authorization does not create a controller |
| `permitAll()` on POST missing CSRF token | May return 403 | Blocked by CSRF before authorization |
| `authenticated()` passes, but service denies owner/tenant | May return 403 or 404 | Decided at the business layer |

Debugging requires knowing **which layer** denied the request. A `403` alone does not prove the rejection came from `denyAll`; it could also be due to missing CSRF or method security.

## 15. Testing with Spring Security Test and MockMvc

In a Spring Boot MVC project with Spring Security Test, protected endpoint configs, and valid controllers, test both **allowed** and **denied** cases.

Example template for `GET` paths:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void profileRejectsAnonymous() throws Exception {
        mvc.perform(get("/account/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileAllowsUser() throws Exception {
        mvc.perform(get("/account/profile").with(user("lan")))
            .andExpect(status().isOk());
    }

    @Test
    void internalPathRejectsAdmin() throws Exception {
        mvc.perform(get("/internal/debug")
                    .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownPathIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/unknown")
                    .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Limitations of the template:** requires controllers returning 200 at `/public/catalog` and `/account/profile`; requires Spring Boot Test/Spring Security Test, an HTTP Basic authentication entry point matching the config example, and security filters applied to MockMvc. Without controllers, you may see 404 even when authorization permits it. Unwrap the line-broken `import static` statements so each sits on **one line** in real source code; here they are wrapped to illustrate the package.

For `POST`, tests must account for CSRF:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;

// When CSRF protection is enabled in the application:
mvc.perform(post("/public/feedback"))
    .andExpect(status().isForbidden());

mvc.perform(post("/public/feedback").with(csrf()))
    .andExpect(status().isOk());
~~~

This is an illustrative snippet inside a test method; the endpoint must exist and return 200 on a valid request. **Do not assume every `permitAll` POST returns 403 when missing CSRF**: that depends on CSRF configuration and request type.

### 15.1. Recommended test matrix

| Request | Principal / state | Expected HTTP authorization |
|---|---|---|
| `GET /public/catalog` | Anonymous | Allow |
| `GET /public/catalog` | Logged-in user | Allow |
| `GET /account/profile` | Anonymous | Deny |
| `GET /account/profile` | Logged-in user | Allow |
| `GET /account/profile` | Remember-me, if enabled | Allow by default |
| `GET /api/invoices/1` | User lacking `invoice:read` | Deny |
| `GET /api/invoices/1` | User with `invoice:read` | Allow at HTTP, still needs object policy |
| `POST /api/invoices/1` | User with only `invoice:read` | Deny |
| `GET /api/admin/users` | User with only `ROLE_USER` | Deny |
| `GET /api/admin/users` | User with `ROLE_ADMIN` | Allow at HTTP |
| `GET /internal/debug` | Admin | Deny |
| `GET /unknown` | Admin | Deny due to fallback |
| `POST /public/feedback` missing CSRF | Anonymous, CSRF enforced | Rejected by CSRF even though HTTP rule is Allow |
| `GET /api/admin/users` with broad rule first | Ordinary user | Negative test must catch the ordering bug |

Do not write tests only for admins. When testing matcher order, use a non-admin user to directly hit the admin endpoint. When verifying object-level permissions, use two users with the same role but different owners/tenants.

## 16. Standalone Java 17 program: simulating three decisions and rule ordering

The following example is a **plain Java simulation** for easy execution and observation. It is **not a Spring Security implementation**, and does not simulate authentication filters, CSRF, role hierarchy, exception handlers, or full `RequestMatcher`s. It only expresses the logic of the rules learned, simulates `fullyAuthenticated` for comparison, and demonstrates **stopping at the first matching rule**.

Create file `HttpRuleDemo.java`:

~~~java
import java.util.List;

public class HttpRuleDemo {

    enum Identity {
        ANONYMOUS, REMEMBERED, FULL
    }

    enum Policy {
        PERMIT_ALL, DENY_ALL, AUTHENTICATED, FULLY_AUTHENTICATED
    }

    record Request(String method, String path, Identity identity) {
    }

    record Rule(String method, String prefix, Policy policy) {
        boolean matches(Request request) {
            return ("*".equals(method) || method.equals(request.method()))
                    && request.path().startsWith(prefix);
        }
    }

    static boolean allowed(Identity identity, Policy policy) {
        return switch (policy) {
            case PERMIT_ALL -> true;
            case DENY_ALL -> false;
            case AUTHENTICATED -> identity != Identity.ANONYMOUS;
            case FULLY_AUTHENTICATED -> identity == Identity.FULL;
        };
    }

    static boolean authorize(Request request, List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                return allowed(request.identity(), rule.policy());
            }
        }
        return false;
    }

    static void show(String label, Request request, List<Rule> rules) {
        System.out.println(label + ": " + authorize(request, rules));
    }

    public static void main(String[] args) {
        List<Rule> rules = List.of(
                new Rule("GET", "/public/", Policy.PERMIT_ALL),
                new Rule("GET", "/account/", Policy.AUTHENTICATED),
                new Rule("GET", "/finance/", Policy.FULLY_AUTHENTICATED),
                new Rule("*", "/internal/", Policy.DENY_ALL),
                new Rule("*", "/", Policy.DENY_ALL)
        );

        show("public anonymous",
                new Request("GET", "/public/catalog", Identity.ANONYMOUS),
                rules);

        show("account anonymous",
                new Request("GET", "/account/me", Identity.ANONYMOUS),
                rules);

        show("account remembered",
                new Request("GET", "/account/me", Identity.REMEMBERED),
                rules);

        show("finance remembered",
                new Request("GET", "/finance/pay", Identity.REMEMBERED),
                rules);

        show("finance full",
                new Request("GET", "/finance/pay", Identity.FULL),
                rules);

        show("internal full",
                new Request("GET", "/internal/debug", Identity.FULL),
                rules);

        show("unmatched full",
                new Request("GET", "/other", Identity.FULL),
                rules);

        show("post public anonymous",
                new Request("POST", "/public/catalog", Identity.ANONYMOUS),
                rules);

        List<Rule> badOrder = List.of(
                new Rule("*", "/", Policy.AUTHENTICATED),
                new Rule("GET", "/public/", Policy.PERMIT_ALL)
        );

        show("bad order public anonymous",
                new Request("GET", "/public/catalog", Identity.ANONYMOUS),
                badOrder);
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac --release 17 HttpRuleDemo.java
java HttpRuleDemo
~~~

Expected output:

~~~text
public anonymous: true
account anonymous: false
account remembered: true
finance remembered: false
finance full: true
internal full: false
unmatched full: false
post public anonymous: false
bad order public anonymous: false
~~~

Output explanation:

- **`public anonymous: true`**: public GET hits `PERMIT_ALL`.
- **`account anonymous: false`**: not logged in fails `AUTHENTICATED`.
- **`account remembered: true`**: simulated remember-me is accepted by `AUTHENTICATED`.
- **`finance remembered: false`**: remember-me fails `FULLY_AUTHENTICATED`.
- **`finance full: true`**: full login satisfies the requirement.
- **`internal full: false`**: `DENY_ALL` applies even when fully logged in.
- **`unmatched full: false`**: `DENY_ALL` fallback blocks unlisted URLs.
- **`post public anonymous: false`**: the public rule is GET-only; POST falls through to the fallback.
- **`bad order public anonymous: false`**: catch-all `AUTHENTICATED` comes first, so the public rule below is never evaluated.

**Important note:** here `path.startsWith(prefix)` only illustrates a simple prefix; Spring Security uses concrete `RequestMatcher` implementations with proper path semantics rather than this simple Java function. This exercise helps grasp **first match wins** and the three authentication states, and does not replace Spring integration tests.

## 17. Common configuration mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Putting `/api/**.permitAll()` before admin rules | Broad rule matches first | Narrow public URLs and put specific rules first |
| Setting `/api/**.authenticated()` and assuming resource GET/POST are safe | Login alone lacks permissions | Use `hasAuthority`/`hasRole` and object policies |
| Using `permitAll` to "disable CSRF" | CSRF is a separate protective filter | Manage CSRF tokens or narrow exceptions per architecture |
| Using `web.ignoring()` for every public route | Skips the entire security chain for that route | Prefer `permitAll` whenever possible |
| Using `denyAll` expecting admins to still get in | Deny is unconditional at the rule | Use an appropriate role/permission rule if admins need access |
| Assuming `denyAll` always returns 403 | Unauthenticated calls may trigger entry point | Test status/redirect per auth mechanism |
| Assuming `authenticated` excludes remember-me | Confused with fully-authenticated | Use `fullyAuthenticated` when genuinely required |
| Checking `isAuthenticated()` manually and letting anonymous through | Anonymous token can carry flag true | Use framework `authenticated()`/trust resolver |
| Putting `anyRequest().authenticated()` at the end without reviewing new APIs | Sensitive APIs may expose to every logged-in user | Consider `denyAll` allowlist and tests |
| Protecting only URLs and forgetting method security | Services may be called via other entry points | Enforce policy at service/use-case level |
| Matching only one overly narrow `SecurityFilterChain` | URLs outside all chains may go unprotected | Create a covering fallback chain |
| Ignoring `ERROR/FORWARD` dispatches | View/error flows may be blocked or mis-opened | Design dispatcher policies and test |
| Checking only HTTP status without checking leaked data | May be blocked after leaking info or return wrong data | Test response body, owner/tenant, logs |
| Treating CORS as authorization | Non-browser clients ignore CORS | Use real authentication and authorization |
| Testing only the admin happy path | Fails to catch broad rules/wrong order | Test anonymous, regular user, under-privileged user |

## 18. Practical checklist when reviewing configuration

Before deploying a `SecurityFilterChain` to production, answer each item in order:

1. **Chain scope:** are requests guaranteed to match at least one security filter chain? Could `securityMatcher` or `@Order` leave coverage gaps?
2. **Public paths:** which exact methods + paths need no login? Are any sensitive subpaths accidentally opened?
3. **Login-required APIs:** is `authenticated` sufficient for the business requirement, or are roles/permissions also needed?
4. **Privileged APIs:** do `hasRole`/`hasAuthority` use the exact authority strings actually granted by authentication?
5. **Data objects:** does the service check owner, tenant, relation, and workflow state?
6. **Non-public endpoints:** is `denyAll` explicit where needed? Is the fallback closed or login-only?
7. **Rule order:** have you read top-to-bottom and identified the first matching rule for every endpoint?
8. **Other methods:** have you tested GET, POST, PUT, PATCH, DELETE, and required dispatches?
9. **CSRF/CORS/other filters:** might public POSTs need CSRF; are preflights handled properly without opening authorization too wide?
10. **Error behavior:** do 401/403/redirect/404 match the authentication mechanism and data-hiding policy?
11. **Negative tests:** do regular users try admin endpoints, anonymous try profile, admins try internal, and users lacking permissions try APIs?
12. **Change control:** when a new controller is added, are rule review and test coverage performed immediately?

A simple way to read a configuration:

~~~text
[Which chain matches?]
        |
        v
[First rule matching method + path?]
        |
        +-- permitAll      -> No login required at the HTTP rule
        +-- authenticated  -> Requires non-anonymous user
        +-- hasAuthority   -> Requires specific authority
        +-- hasRole        -> Requires role per prefix convention
        +-- denyAll        -> Always denies at the HTTP rule
        |
        v
[Other protective filters, method policy, object policy still apply?]
        |
        v
[Controller/service returns result]
~~~

## 19. Self-check questions

**1. Does `permitAll()` mean every request to that endpoint always returns 200?**  
No. Authentication filters, CSRF, controllers, method security, and business policies can still deny or return 404/5xx.

**2. Can an admin get past `denyAll()`?**  
No. The rule denies unconditionally; if admins need access, an appropriate privilege rule must be used instead of deny.

**3. Does `authenticated()` check `ROLE_USER` or `invoice:read`?**  
No. It only checks authentication state per framework semantics without requiring specific roles or permissions.

**4. An anonymous authentication token can have `isAuthenticated() == true`, so does it pass `authenticated()`?**  
Normally no, because `authenticated()` has a mechanism to exclude anonymous tokens via the trust resolver.

**5. Does remember-me pass `authenticated()`?**  
Normally yes; if full login is required, consider `fullyAuthenticated()`.

**6. Why is placing `/api/admin/**` after `/api/**.authenticated()` dangerous?**  
The broad rule matches first, preventing the admin rule from being evaluated and turning the admin requirement into "login only".

**7. Does `anyRequest().denyAll()` at the end rescue an earlier `/api/**.permitAll()` rule?**  
No, because the request already matched the broad rule earlier and never reaches the fallback.

**8. `POST /public/feedback` has `permitAll` but returns 403 when missing a CSRF token. Should it be changed to `authenticated`?**  
No. Those are two separate responsibilities: authorization and CSRF protection; design and test CSRF properly.

**9. If chain A's `securityMatcher("/api/**")` does not match `/admin/**` and no other chain exists, does A's `anyRequest().denyAll()` block admin?**  
No. The request never enters chain A, so the fallback inside A is not applied.

**10. After passing `authenticated()`, is a user allowed to read any record by ID?**  
No. Business roles/permissions, owner/tenant, and resource constraints must still be checked.

## 20. References

- Spring Security – **Authorize HttpServletRequests** (rule order, `permitAll`, `denyAll`, deferred authentication lookup): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Anonymous Authentication** (anonymous evaluation and authentication trust resolver): https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – **Authorization Architecture** (authorization managers, distinguishing fully authenticated/remember-me): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – **Servlet Architecture and Filters**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
