# ProviderManager Selects the Wrong Provider or Authentication Mechanism Does Not Run: Spring Security Diagnostic Process

## 1. Goal and How to View the Problem

When Spring Security fails to log in as expected, messages such as **"ProviderManager selects the wrong provider"**, **"My AuthenticationProvider is not called"**, **"form login does not run"**, **"JWT is valid but request still returns 401"**, or **"POST /login returns 404/403"** are often blamed on the same issue. In reality, an HTTP request must pass through several layers before reaching `ProviderManager`.

This lesson belongs to the **Diagnostics** section of the **Spring Security - authentication** module. The focus is not on building another authentication mechanism, but on **pinpointing the exact layer that did not execute, why, and how to prove the fix is correct**.

By the end of this lesson, you will be able to:

1. Distinguish **no SecurityFilterChain selected**, **chain without an authentication filter**, **filter not matching the request**, **filter creating the wrong Authentication token**, **provider not supporting**, **provider returning null/exception**, **parent manager fallback**, and **authentication succeeding but context/session not being saved**.
2. Read startup logs/TRACE and inspect `FilterChainProxy` to know **which chain the request selected and which filters are present**.
3. Distinguish `http.securityMatcher(...)`, `authorizeHttpRequests(...).requestMatchers(...)`, and the **authentication filter's** matcher.
4. Diagnose form login, HTTP Basic, Bearer JWT/opaque, OIDC login, remember-me, and custom filters specifically.
5. Understand the **first-success-wins** rule in `ProviderManager`, exception precedence, and the meaning of a parent `AuthenticationManager`.
6. Avoid dangerous "fixes" like disabling CSRF globally, `permitAll()` everywhere, switching to the `{noop}` password encoder, skipping signature verification, or adding a weaker fallback provider.
7. Build a transparent Servlet configuration and write **MockMvc HTTP tests** and **JUnit/Mockito ProviderManager tests** to catch regressions.
8. Distinguish **Servlet `HttpSecurity`** from **WebFlux `ServerHttpSecurity`** so you do not look for the wrong provider/filter.

**Baseline:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x **Servlet stack**. Configurations may change in Spring Security 7.x; cross-check docs for your exact artifact/version. Token, password, and URL examples are for local/test environments only.

## 2. First Question: Has the Request Reached ProviderManager Yet?

Before modifying an `AuthenticationProvider` bean, trace the actual journey:

```text
HTTP request
   |
   v
Servlet container -> DelegatingFilterProxy
   |
   v
springSecurityFilterChain (FilterChainProxy)
   |
   +-- Select FIRST matching SecurityFilterChain by request matcher/order
   |       |
   |       +-- no chain matched? Spring Security may not protect the request
   |       |
   |       v
   |    Chain's security filters
   |       |
   |       +-- CsrfFilter / CORS / logout / custom filters may stop early
   |       |
   |       v
   |    Authentication filter present?
   |       |
   |       +-- no: nothing invokes an AuthenticationManager for this flow
   |       |
   |       +-- yes, but its RequestMatcher doesn't match:
   |       |        authentication filter skips request
   |       |
   |       v
   |    Build unauthenticated Authentication token (concrete Java class)
   |       |
   |       v
   |    AuthenticationManager.authenticate(token)
   |       |
   |       v
   |    ProviderManager: provider.supports(token.getClass())
   |       |
   |       +-- skips, null, exception, success
   |       +-- optional parent fallback
   |       |
   |       v
   |    Authenticated Authentication result
   |       |
   |       v
   |    Filter stores SecurityContext / saves if required
   |       |
   |       v
   +-- AuthorizationFilter / controller / response
```

**If the filter has not matched, ProviderManager cannot "select the wrong provider"** because it has not even been called yet. If the provider already returned an authenticated result but the next request is still anonymous, the bug likely lies in **SecurityContextRepository/session**, not `supports`.

### 2.1. 60-Second Triage Table

| Symptom | Suspected Layer First | Evidence to Collect |
| --- | --- | --- |
| `GET /api/me` returns 200 even when anonymous | Chain coverage / `permitAll` | Which chain matched; whether authorization rules require auth |
| `POST /login` returns 404 | Wrong processing URL, method, or chain | Is login filter present? Does path/method match filter matcher? Is there a conflicting controller path? |
| `POST /login` returns 403 before user lookup | CSRF / upstream filter | `CsrfFilter` logs; is the CSRF token valid? |
| No provider logs at all | Filter/matcher/manager wiring | TRACE filter chain; breakpoints in filter and manager |
| `ProviderNotFoundException` | Token class vs `supports`, missing provider | Print **class name** of request authentication; inspect provider list |
| Correct username/password still gives `BadCredentials` | DAO/encoder/realm or another provider | Which provider received the token; user source; password encoder; fallback |
| JWT has `Authorization: Bearer ...` but returns 401 | Bearer filter/token decoder/issuer | Right chain? `BearerTokenAuthenticationFilter`? Decoder/introspection error |
| Login returns 302 but next request is anonymous | Context persistence/cookie/session | `SecurityContextRepository`, cookie jar, session policy |
| Browser redirected to login when API is called | Entry point / selected chain | Initial response 302 or client following redirect; which auth mechanism API chain has |
| Valid user gets 403 | Authorization vs Authentication | Does `Authentication` already exist? What are authorities/roles/scopes? |
| Custom filter called twice | Servlet auto-registration outside Spring Security | Is filter bean registered with both container and security chain? |
| Test with `with(user("alice"))` passes but real login fails | Test is bypassing authentication | Test the real `formLogin()`/HTTP Basic/JWT route |

Do not infer the root cause solely from the HTTP status. **A 401/403/302 can be generated at multiple different layers**.

## 3. Safe Evidence Collection Tools

First create a **reproducible** HTTP request keeping the exact URL, method, headers (excluding secrets in reports), body type, cookies/session, and correlation ID. Example:

```bash
# Do not auto-follow redirects: observe the initial status and Location.
curl -i -H 'Accept: text/html' http://localhost:8080/private

# Basic: local demo username/password, do not use over non-TLS production networks.
curl -i -u alice:demo-password http://localhost:8080/api/me

# Check only the GET form-login route.
curl -i http://localhost:8080/login
```

For Bearer tokens, avoid putting raw tokens in shell history or CI logs. Use a secrets-managed HTTP client or secure environment variables; if you need to debug, log "Bearer header present, token length X, issuer Y" instead of the full token.

### 3.1. Enabling Spring Security Logs in Test Environments

In `application-local.yml` or test configuration:

```yaml
logging:
  level:
    org.springframework.security: TRACE
```

Or `application.properties`:

```properties
logging.level.org.springframework.security=TRACE
```

TRACE can show **every filter invoked**; DEBUG at startup typically lists the filter chains. This is useful evidence to distinguish "filter does not exist" from "filter exists but did not match the request". **Enable only in controlled environments and turn off after diagnostics**, because logs may contain request/identity info and expose unnecessary data.

In the logs, look in order for:

1. `DefaultSecurityFilterChain : Will secure ... with [...]` at application startup.
2. `FilterChainProxy : Securing POST /login` and `Invoking ...Filter` for the failing request.
3. Whether `CsrfFilter` or an earlier pre-authentication filter blocked it.
4. Whether `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`, `OAuth2LoginAuthenticationFilter`, or a custom filter is present and actually runs.
5. Traces of `ProviderManager`/`AuthenticationProvider`/`DaoAuthenticationProvider`, exception type, and failure handler.
6. How `AuthorizationFilter`/`ExceptionTranslationFilter` chose redirect/401/403.

**Note:** a log line saying a filter was invoked does not mean the filter **performed authentication**. A filter may run `doFilter` and skip because its request matcher did not match or no credential was present.

### 3.2. Selective Debugging, Without Logging Credentials

Do not write:

```java
// ANTI-PATTERN: do not log raw password/access token/cookie.
log.debug("authentication=" + authentication);
log.debug("password=" + request.getParameter("password"));
log.debug("Authorization=" + request.getHeader("Authorization"));
```

Replace with non-sensitive metadata: `authentication.getClass().getName()`, provider name, provider order, matcher result, correlation ID, verified issuer, error code. Never record passwords, raw tokens, session IDs, cookies, private keys, or verbatim login assertions.

## 4. SecurityFilterChain: The First Layer Often Overlooked

An application can declare multiple `SecurityFilterChain` beans:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

The snippet above is a **configuration excerpt**; imports, datasource/user provider, and CSRF/session policies are omitted. The key point: `FilterChainProxy` evaluates chains in `@Order` and **uses only the first matching chain**. It does not merge filters from the API chain with the web chain.

### 4.1. `securityMatcher` vs `requestMatchers`

| DSL | Decides | Consequence When Misconfigured |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | **Does this chain apply to the request or not?** | Request never enters the chain; filters inside do not run |
| `authorizeHttpRequests(a -> a.requestMatchers(...))` | **Within the selected chain**, what authorization does a URL need? | May allow/deny access wrongly, but does not add an authentication filter |
| `formLogin().loginProcessingUrl("/auth")` | Which **POST endpoint** the form-login filter intercepts | POSTing to the wrong path skips the filter |
| `httpBasic()` | Adds the Basic auth mechanism to the chain | No `BasicAuthenticationFilter` if the mechanism is not configured |
| `oauth2ResourceServer().jwt()` | Adds the Bearer token resource-server flow | Does not turn form login into a JWT resource server |
| `@Order` | Chain priority order | A catch-all chain ordered first swallows all requests meant for narrower chains |

**Bug 1 — Catch-all ordered first:**

```java
// WRONG: if this chain has highest priority, /api/** may be
// handled by web form login instead of API Basic/Bearer.
@Bean
@Order(1)
SecurityFilterChain everything(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Fix by placing the specific `/api/**` chain first and the catch-all chain last. Do not merely toggle `401`/`302`: **make sure the right authentication filter** is attached to the chain.

**Bug 2 — Gaps in chain coverage:**

```java
// WARNING: protects only /api/**; all other paths match
// no chain at all if there is no catch-all chain.
http.securityMatcher("/api/**");
```

If no filter chain matches a request, that request may **not be protected by Spring Security**. Do not fix this with `permitAll()` on every URL; define an explicit catch-all chain and verify endpoint coverage.

### 4.2. Account for Context Path, Servlet Mapping, and Proxies

Paths like `/api`, `/api/`, `/api/items`, `/apiary`, and `/myapp/api/items` can be seen differently by Spring depending on `server.servlet.context-path`, Servlet registration, proxy rewriting, and matcher implementation. Check **the exact request as seen by the Servlet**; do not match raw `requestURI` with `startsWith("/api")` because that accidentally matches `/apiary`.

If Spring MVC has multiple Servlets, pick a matcher compatible with the mapping; Spring Security 6.5 selects request matchers based on components present, while Spring Security 7 has more suitable path-pattern APIs. Test with trailing slashes, URL-encoded characters, forwarded prefixes, and POST methods.

## 5. Right Chain, Missing Authentication Filter

`ProviderManager` does not monitor every HTTP request on its own. **An authentication filter must extract credentials and call the manager**. In Spring Security Servlet:

| Mechanism | Typical Filter | Common Enablement |
| --- | --- | --- |
| Form username/password | `UsernamePasswordAuthenticationFilter` | `http.formLogin(...)` |
| HTTP Basic | `BasicAuthenticationFilter` | `http.httpBasic(...)` |
| OAuth Bearer JWT/opaque | `BearerTokenAuthenticationFilter` | `http.oauth2ResourceServer(...)` |
| OAuth2 login/OIDC | `OAuth2LoginAuthenticationFilter` | `http.oauth2Login(...)` |
| Remember-me | `RememberMeAuthenticationFilter` | `http.rememberMe(...)` |
| X.509 client certificate | `X509AuthenticationFilter` | `http.x509(...)` |
| Custom API key | Application-added filter | `http.addFilterBefore/After(...)` at the appropriate position |

Having an `AuthenticationProvider` bean **does not automatically create the corresponding filter**. A provider that knows how to authenticate `ApiKeyAuthenticationToken` is useless if no filter extracts the API key from the request, creates the right token type, and calls the manager.

Conversely, having a filter that is not wired to the manager containing your expected provider also fails. Therefore you must prove **both filter presence and manager/provider wiring**.

### 5.1. When Defining a SecurityFilterChain Manually, Do Not Assume Form Login Appears Automatically

Once you declare a `SecurityFilterChain` bean yourself, enable the desired mechanisms explicitly:

```java
http
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

This is an **excerpt**, not a recommendation to enable both for every endpoint. For a stateless JWT API, do not accidentally enable form login with sessions; for a web browser app, do not expect a bearer filter to appear just by adding the `spring-security-oauth2-resource-server` dependency.

### 5.2. Custom Filter Skipped

If a custom filter overrides `shouldNotFilter(...)`, checks paths manually, or has an internal `RequestMatcher`, verify all of those conditions. With `OncePerRequestFilter`, confirm the URL/method/header **match** the actual request and that the filter was added to the right chain.

Calling `addFilterBefore(custom, UsernamePasswordAuthenticationFilter.class)` or `addFilterAfter(custom, LogoutFilter.class)` does not guarantee invocation on another chain or for requests outside `securityMatcher`. More important than position is that **the filter is actually in the matched chain**, calls `chain.doFilter(...)` properly, and does not swallow the response.

### 5.3. Filter Bean Runs Twice

If a custom `Filter` is both declared as a Spring bean and added to `HttpSecurity`, Spring Boot may auto-register the filter in the **Servlet container chain**, causing it to run **twice** or in an unexpected order. If you need a bean for DI but want it to run only inside the security chain, disable auto-registration:

```java
@Bean
FilterRegistrationBean<MyAuthenticationFilter> disableContainerRegistration(
        MyAuthenticationFilter filter) {
    FilterRegistrationBean<MyAuthenticationFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
```

This is an **excerpt**: `MyAuthenticationFilter` must be defined by your project and already added to `HttpSecurity`. Do not apply this blindly to every application filter; the goal is to avoid double registration.

## 6. Authentication Filter Is Present, but Does Not Process the Request

### 6.1. Form Login: `POST /login`, Not Every GET/POST

With default form-login configuration, `UsernamePasswordAuthenticationFilter` processes:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=demo-password&_csrf=<valid-token>
```

If a user calls `GET /login`, that is a request to **render the login page**, not submit credentials. If the frontend submits JSON via `POST /login` while the backend only has default `UsernamePasswordAuthenticationFilter`, the filter reads `request.getParameter("username")`/`password` and **does not parse JSON bodies automatically**. The result may be empty credentials, not the provider "selecting wrongly".

Customizing URL and fields:

```java
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin/process")
        .usernameParameter("email")
        .passwordParameter("password")
        .permitAll());
```

Then the form must POST to **`/signin/process`** with field `email`, no longer `POST /login`. `GET /signin` must be rendered by your controller/template; do not assume Spring generates that custom page.

### 6.2. CSRF Blocks Before the Login Filter Calls the Manager

Spring Security protects POST requests with CSRF under default Servlet settings. If `POST /login` returns **403** due to a missing CSRF token, `UsernamePasswordAuthenticationFilter` may **never have authenticated**. Evidence is `CsrfFilter` in TRACE/DEBUG logs.

Proper fix: include the CSRF token in the HTML form, or use `.with(csrf())` in tests. **Do not disable CSRF globally just to make login POST "work"**; for cookie-authenticated browser applications, doing so exposes state-changing operations to CSRF risks.

### 6.3. Basic: Without `Authorization: Basic`, the Filter Passes Through

`BasicAuthenticationFilter` handles valid Basic headers. A request without a Basic header continues to authorization, and then `ExceptionTranslationFilter` issues a 401 Basic challenge. In this case, **there is not necessarily any call to `ProviderManager`**, because no credentials were provided to verify.

Similarly for Bearer: a missing Bearer token does not prove `JwtAuthenticationProvider` is broken. Check the header and bearer token resolver first.

### 6.4. CORS Preflight

Browsers send `OPTIONS` preflight requests without credentials. If CORS/CSRF/authorization blocks the preflight, the actual API request never happens. The symptom looks like "authentication filter did not run", but the cause is the **CORS handshake**. Configure CORS at the appropriate layer with specific allowed origins/methods/headers; do not turn business APIs into `permitAll` to make preflight pass.

## 7. The Created Authentication Token Type Determines Which Provider Can Handle It

`ProviderManager` receives an object implementing `Authentication`. Each provider has:

```java
boolean supports(Class<?> authentication);
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

Providers are **not selected magically by bean name**, username, URI, or `@ComponentScan` order. They are evaluated by **provider list order** and `supports(authentication.getClass())`.

Examples:

| Request Token Class | Typically Supporting Provider |
| --- | --- |
| `UsernamePasswordAuthenticationToken` | `DaoAuthenticationProvider`, custom username/password provider |
| `JwtAuthenticationToken` after authentication | A JWT result, not generally the input to `JwtAuthenticationProvider` |
| `BearerTokenAuthenticationToken` in resource-server JWT pipeline | `JwtAuthenticationProvider`, depending on manager resolver |
| `BearerTokenAuthenticationToken` in opaque pipeline | `OpaqueTokenAuthenticationProvider` |
| `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider` |
| `PreAuthenticatedAuthenticationToken` | `PreAuthenticatedAuthenticationProvider` |
| `OAuth2LoginAuthenticationToken` in `oauth2Login` flow | Provider supporting OAuth2 authorization-code login per configuration |
| Custom `ApiKeyAuthenticationToken` | Custom provider where `supports` matches that exact class |
| `OneTimeTokenAuthenticationToken` | One-Time Token provider/service when the OTT mechanism is enabled |

**Be careful with JWT:** `BearerTokenAuthenticationFilter` typically creates **`BearerTokenAuthenticationToken`** (unauthenticated input), while `JwtAuthenticationProvider` returns an authenticated **`JwtAuthenticationToken`**. If a custom provider calls `supports(JwtAuthenticationToken.class)` expecting raw Bearer input, you confused the **input type** with the **output type**.

### 7.1. How Should `supports` Check?

For custom token `ApiKeyAuthenticationToken`:

```java
@Override
public boolean supports(Class<?> authentication) {
    return ApiKeyAuthenticationToken.class
            .isAssignableFrom(authentication);
}
```

This is an **excerpt inside a custom `AuthenticationProvider`**; the token class is defined separately. `supports=true` only states that the provider **can consider** that token type. `authenticate` may still return `null` when the request is outside the provider's scope.

Do not write:

```java
// WRONG for a provider that only handles API keys: swallows every token type.
@Override
public boolean supports(Class<?> authentication) {
    return true;
}
```

An overly broad `supports` placed early can prevent another mechanism from running or produce a wrong authenticated result. Conversely, `authentication.equals(ApiKeyAuthenticationToken.class)` excludes subclasses if you intend to support them; test the type hierarchy per your design.

### 7.2. Never Set `isAuthenticated=true` on Request Input

`UsernamePasswordAuthenticationToken.authenticated(...)` or `new ...(..., authorities)` represents an already-verified result **created by a trusted provider**, not a way for a frontend/controller to legitimize unverified credentials.

A custom filter should construct an **unauthenticated** token and pass it to `AuthenticationManager.authenticate(...)`. If a controller sets an authenticated principal itself without verifying secrets, `ProviderManager` never gets a chance to enforce policy.

## 8. How Does ProviderManager Select a Provider?

Spring Security 6.5 rules:

```text
ProviderManager.authenticate(token)
    lastException = null
    for provider in orderedProviders:
        if not provider.supports(token.class): continue
        try:
            result = provider.authenticate(token)
            if result != null: SUCCESS; stop local traversal
            if result == null: continue
        catch AccountStatusException:
            STOP immediately
        catch InternalAuthenticationServiceException:
            STOP immediately
        catch other AuthenticationException ex:
            lastException = ex; continue
    if no local success and parent exists:
        try parent.authenticate(token)
    if success:
        erase credentials if applicable, publish event as configured
    else:
        throw appropriate last exception or ProviderNotFoundException
```

This diagram is **educational pseudocode**, not a replacement for the exact source code of each version or event-handling logic. The key takeaway is that **a provider returning `supports=true` does not automatically stop traversal**.

### 8.1. State Table and Debugging Meaning

| P1 | P2 | Parent | Result / Investigation |
| --- | --- | --- | --- |
| `supports=false` | success | not called | P1 skipped, P2 wins |
| `supports=true`, returns `null` | success | not called | P1 declines, P2 wins |
| `BadCredentialsException` | success | not called | P2 can recover from P1's failure; review for downgrade |
| success | not called | not called | First-success-wins |
| `BadCredentialsException` | `null` | success | Parent **can** succeed |
| `LockedException` | not called | not called | `AccountStatusException` stops the chain |
| `InternalAuthenticationServiceException` | not called | not called | Internal backend failure stops the chain |
| both providers do not support | — | no parent | `ProviderNotFoundException` |
| all providers return `null` | — | no parent | `ProviderNotFoundException` if no other failure occurred |
| P1 `BadCredentials`, P2 `BadCredentials` | — | no parent | Last exception is thrown |
| child `BadCredentials` | — | parent `ProviderNotFound` | Child's error can be preserved rather than parent's |

Notably: **`BadCredentialsException` does not stop the chain by default**. If a legacy provider sits behind it authenticating with weaker passwords, an account could log in even after the primary provider rejected it. Conversely, do not abuse `LockedException` just to force-stop every bad password: it represents a genuinely locked account status, not an arbitrary "break" primitive.

### 8.2. Meaning of `ProviderNotFoundException`

`ProviderNotFoundException: No AuthenticationProvider found for ...` usually means:

- The filter created a request token class that no provider supports.
- The provider bean you created was not added to **the manager used by the filter**.
- Wrong chain/manager (API chain uses manager A, provider is in manager B).
- Custom provider `supports` checks the wrong class/package or lacks inheritance handling.
- No parent exists, or parent also cannot handle it.
- Mismatch between Servlet and Reactive types.

It **does not** mean the password is definitely wrong. To understand it, capture the concrete class of the input authentication and the list of providers **actually inside the handling manager**.

### 8.3. Reading Authentication Results: Do Not Trust Every Authentication Blindly

`Authentication.isAuthenticated()`, `getPrincipal()`, `getAuthorities()`, and `getCredentials()` are verification data inside the trusted layer. `ProviderManager` erases credentials from the result by default if it implements `CredentialsContainer`, so `getCredentials()==null` after success **does not mean the provider "did not receive the password"**.

An `Authentication` might be anonymous/remember-me/fully authenticated. `isAuthenticated()==true` does not by itself prove recent MFA or WebAuthn UV. Authorization must enforce the appropriate assurance level and authorities.

## 9. Parent AuthenticationManager: A Fallback Boundary Often Misunderstood

You can declare:

```java
AuthenticationManager parent =
        new ProviderManager(List.of(sharedProvider));

AuthenticationManager child =
        new ProviderManager(List.of(localProvider), parent);
```

`parent` is a **fallback authentication manager**, not a BeanFactory parent, superclass, or cache. When the child gets no success from local providers (except early-stopping exceptions), the parent may try the token.

### 9.1. Debugging the Parent Manager

Record safely:

- Which manager does the filter call first? Use bean ID/identity or a test wrapper, never log credentials.
- What is the provider list in child, in exact order?
- Is parent actually wired in the constructor/DSL, or does it merely exist as a bean?
- Does the parent's `supports` handle the same token type?
- Did the local provider return `null`/`BadCredentialsException`, or did it already return an authenticated result?
- Did an `AccountStatusException`/`InternalAuthenticationServiceException` stop before reaching parent?

### 9.2. Fallback Can Be a Vulnerability

If child enforces a new employee policy and parent is an old password provider:

```text
Child: username alice + wrong/expired corporate password
    -> BadCredentialsException
    -> Parent legacy provider accepts an old password
    -> LOGIN SUCCESS (SECURITY DOWNGRADE)
```

That is not necessarily a Spring Security bug; it is **incorrect manager composition policy**. To separate realms, use distinct token types, explicit identity routing, or authoritative backend policies rather than relying on `BadCredentials` to halt the chain.

### 9.3. Never Create Parent-Child Cycles

Do not give manager A parent B while B calls A. Cycles can cause infinite recursion/`StackOverflowError`. If multiple `SecurityFilterChain` instances share a parent, document the graph and unit-test each child separately.

## 10. Bean/Wiring Diagnostics: Provider Exists, but Manager Does Not Know About It

One of the most common causes is **confusing a bean in the Spring ApplicationContext with the configuration of the `AuthenticationManager` actually attached to the filter**.

### 10.1. Configuration Approaches That Mean Different Things

```java
// 1. Provider explicitly referenced in the current chain's HttpSecurity.
http.authenticationProvider(customProvider);

// 2. Manager directly attached to the current chain's HttpSecurity.
http.authenticationManager(explicitManager);

// 3. Standalone manually created manager.
AuthenticationManager explicitManager =
        new ProviderManager(List.of(customProvider));

// 4. Provider bean living in ApplicationContext:
// @Bean AuthenticationProvider customProvider() { ... }
```

**Do not equate all four.** Spring Security has auto-configuration/global managers as well as local per-`HttpSecurity` contexts; how beans/configurers combine can vary by version and provider count. To diagnose, **do not just see that a bean was created and assume the filter uses it**. Record/inspect the **actual manager attached to the request's filter chain**.

### 10.2. `AuthenticationConfiguration.getAuthenticationManager()`

Spring Security provides `AuthenticationConfiguration#getAuthenticationManager()` to obtain the manager from the configuration scope in many cases. However, that does not mean every per-chain custom manager is **the same global singleton**.

If a project has multiple `SecurityFilterChain` beans and calls:

```java
http.authenticationManager(childManager);
```

then test **that specific chain's** flow. Do not grab a manager from the application context in a unit test and assume the HTTP filter calls that exact instance. Prefer explicit configuration and filter-chain integration tests.

### 10.3. Multiple `@Bean`/`@Component` Providers and Order

`ProviderManager` relies on an ordered list. Do not infer authentication order from class names, bean names, or filesystem scanning. If security depends on order, construct the list explicitly:

```java
ProviderManager manager =
        new ProviderManager(List.of(primaryProvider, fallbackProvider));
```

Allow fallback providers only when explicitly justified by domain/policy. Where `ProviderManager.getProviders()` allows reading the list, you can inspect class names/IDs **in test/diagnostic mode**; never use this API to mutate or swap providers dynamically from client input.

## 11. DaoAuthenticationProvider: Inspecting Password/Identity Source Errors Properly

`DaoAuthenticationProvider` processes `UsernamePasswordAuthenticationToken` using `UserDetailsService` and `PasswordEncoder`.

```text
UsernamePasswordAuthenticationFilter
   -> UsernamePasswordAuthenticationToken
   -> ProviderManager
   -> DaoAuthenticationProvider
       -> UserDetailsService.loadUserByUsername
       -> account prechecks (locked, enabled, account expired)
       -> PasswordEncoder.matches(raw, encoded)
       -> credentials/account postchecks
       -> authenticated UsernamePasswordAuthenticationToken
```

If the DAO provider actually runs yet login still fails, check:

1. Which **database/schema/tenant** is `UserDetailsService` querying, and does it load the right user?
2. Does `PasswordEncoder` match the hash format stored in the DB? In particular, `DelegatingPasswordEncoder` typically expects prefixes like `{bcrypt}` or `{pbkdf2}` when configured accordingly.
3. Was the raw password from the form parsed correctly? `POST` vs JSON form, field names, Unicode normalization.
4. Does `UserDetails` return the right `getPassword()` hash; are there disabled/locked/expired flags?
5. Was the password changed while a `UserDetails` cache is still stale?
6. Does the provider enforce the right realm policy; could another provider for the same token class accept weaker credentials?
7. Does the system use LDAP bind, OIDC, or passkeys instead of local passwords? If so, **DAO is not necessarily supposed to be called**.

**Never fix errors with `{noop}` in production** or swap `PasswordEncoder` for one that skips password verification. A prefix/hash mismatch is a migration/encoder configuration problem and must be resolved in line with security policy.

### 11.1. Actual Spring Security 6.5 API

`DaoAuthenticationProvider` has a constructor taking `UserDetailsService`:

```java
DaoAuthenticationProvider dao =
        new DaoAuthenticationProvider(userDetailsService);
dao.setPasswordEncoder(passwordEncoder);
```

This is an excerpt inside a configuration class where valid bean variables exist. The old no-arg constructor/`setUserDetailsService` was deprecated in 6.5; prefer explicit constructor dependency. A runnable Spring Boot example is in Section 16.

### 11.2. `UsernameNotFound` Need Not Be Exposed Externally

`AbstractUserDetailsAuthenticationProvider` can hide `UsernameNotFoundException` as `BadCredentialsException` to mitigate user enumeration. Therefore **"Bad credentials" is not proof that the user exists**. In tests, verify repository/identity lookup safely and keep external browser responses uniform, avoiding overly detailed usernames/PII in logs.

## 12. Distinguishing Authentication Failure, Authorization Failure, and HTTP Response

Answer this before debugging further:

| Situation | Typical Responding Layer | Example |
| --- | --- | --- |
| POST form login wrong password | Form filter's `AuthenticationFailureHandler` | Redirect `/login?error`, not always 401 |
| Anonymous resource request | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | 302 login or 401 Basic/Bearer |
| Authenticated but missing role/scope | `AccessDeniedHandler` | 403 |
| POST missing CSRF | `CsrfFilter` / `AccessDeniedHandler` | 403 before login provider |
| Invalid Bearer header | Bearer filter/failure handler, decoder | 401 `WWW-Authenticate` per RFC 6750 |
| Browser omits session cookie | Context repository/remember-me/entry point | 302 login even after a prior success |
| API route 404 | Servlet routing, security matcher/filter endpoint | Request may not reach auth filter; do not infer `ProviderNotFound` |

**Common mistake:** seeing 401 and adding `.formLogin(...)` to a Bearer API. That can make the API return HTML redirects and add unwanted sessions without **fixing** the missing decoder/manager.

### 12.1. Difference Between "Authenticated" and "Authorized"

A successful `Authentication` lacking `ROLE_ADMIN` is still blocked by `authorizeHttpRequests(...).hasRole("ADMIN")`. That is **not** `ProviderManager` picking the wrong provider. Inspect `getAuthorities()`, scope/role mapping, and object-level authorization.

### 12.2. How to Debug Responses Without Following Redirects

If `curl -L` automatically follows redirects, the final login page may return 200 and trick you into thinking the API succeeded. Use:

```bash
curl -i http://localhost:8080/private
```

and read `HTTP/1.1 302` plus `Location` on the first response. For REST APIs, inspect `WWW-Authenticate`, `Content-Type`, and the raw status rather than only the final body.

## 13. JWT/Opaque/OIDC: Mechanisms That May Not Use DAO

### 13.1. Bearer JWT

A resource-server configuration:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

When active, `BearerTokenAuthenticationFilter` extracts the token from the header, and the manager's JWT decoder/`JwtAuthenticationProvider` verifies signature, issuer, expiry, and configured validators, returning `JwtAuthenticationToken`. `DaoAuthenticationProvider` is not the backend for JWT in normal flows.

If Bearer auth "does not run", ask:

- Does `/api/**` match the API chain with `oauth2ResourceServer` enabled?
- Does the `Authorization` header actually contain a valid `Bearer <token>`?
- Is `BearerTokenAuthenticationFilter` in the chain?
- Are issuer/JWKS/`JwtDecoder` and audience validators configured properly?
- Does `AuthenticationManagerResolver` pick the right issuer/tenant manager?
- Does `JwtAuthenticationConverter` map authorities/scopes properly?
- Is the error a 401 **authentication** failure or a 403 **authorization** failure?

**Do not** "fix" a JWT with the wrong issuer by disabling issuer/signature checks or trusting unverified JWT payloads.

### 13.2. Opaque Tokens and Introspection

With opaque tokens, `OpaqueTokenAuthenticationProvider`/introspector contacts the Authorization Server per config. A 401 can come from an inactive token, AS timeout, bad client auth, or wrong introspection endpoint. Check the manager and introspector types; **do not expect `UserDetailsService` to be called** if the architecture does not use it.

### 13.3. OAuth2 Login / OpenID Connect

`oauth2Login(...)` uses the authorization-code flow with a redirect/callback such as `/login/oauth2/code/{registrationId}`. Misconfigured redirect URIs/client registrations, proxy base URLs, or state cookies/sessions can prevent **the filter from catching the callback**. A password `AuthenticationProvider` will not fix an OIDC callback.

Questions to ask:

- Is the login initiation endpoint accessible?
- Does the callback URL (path, scheme, host) match the IdP configuration?
- Does the request carry the right `code`/`state`, and does the session hold the authorization request?
- Does the chain include `OAuth2LoginAuthenticationFilter`?
- Are OIDC ID token validation/nonce/issuer checks right?
- After a successful callback, do account mapping and local status checks run?

Never use an unverified email claim as a sufficient identifier to auto-provision privileged accounts.

### 13.4. Remember-Me, One-Time Token, and Passkeys

These mechanisms each have dedicated filters/tokens/providers. If you add a service or repository bean without **enabling the DSL** (`rememberMe`, `oneTimeTokenLogin`, `webAuthn`), that mechanism may never be added to the filter chain. A remembered user may be considered authenticated but not **fullyAuthenticated**; do not mistake a re-auth redirect for a non-running provider.

## 14. SecurityContext: Provider Succeeds, but Next Request Loses Login

Suppose logs confirm `DaoAuthenticationProvider` returned an authenticated token. If the browser makes the next request and gets redirected back to login, switch to diagnosing **persistence** instead of continuing to swap providers.

### 14.1. Session vs Stateless

- Form login typically stores the security context in the HTTP session, so the browser must send back the right `JSESSIONID`/`SESSION` cookie.
- Stateless JWT/Basic APIs typically authenticate on every request and do not persist results in an HTTP session.
- `SessionCreationPolicy.STATELESS` has different semantics from browser session login. Do not set stateless on the web chain and expect form-login sessions to survive across requests.
- Reverse proxies, cookie `Secure`/`SameSite`/`Domain`/`Path` attributes, and load balancers/session stores can prevent the session from returning the same data.

### 14.2. Spring Security 6: Explicit Save When Authenticating Manually in a Controller/Filter

If you invoke `AuthenticationManager.authenticate(...)` directly outside a built-in authentication filter and want login to persist across requests, you must save the `SecurityContext` into the appropriate `SecurityContextRepository`:

```java
// Servlet excerpt: inside a trusted login controller/filter,
// requires configured manager, strategy, and repository beans.
Authentication result = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));

SecurityContext context = securityContextHolderStrategy
        .createEmptyContext();
context.setAuthentication(result);
securityContextHolderStrategy.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

These variables are real app dependencies; this is **not** a standalone class. In Spring Security 6, `SecurityContextHolderFilter` generally only **reads** context from the repository; custom code must save explicitly. Do not conclude "the provider did not run" just because a second request is anonymous after a custom login succeeded.

### 14.3. Async/Reactive Context

`SecurityContextHolder` defaults to `ThreadLocal` in Servlet apps. If authentication is created on one thread while business logic executes on another executor, the context may not propagate automatically. Use `DelegatingSecurityContextRunnable/Executor` or the matching context propagation mechanism; never enable `MODE_GLOBAL` in multi-user web apps.

In WebFlux, use Reactor Context/`ReactiveSecurityContextHolder`, do not copy `ThreadLocal` assumptions. The diagnostic question is **where the context lives**, not only which manager was called.

## 15. Provable Step-by-Step Debugging Process

Proceed from outside in, stopping at the **first failing boundary**.

| Step | Check | If It Fails |
| --- | --- | --- |
| 1 | Do URL/method/headers/body/cookies match the reproducible request? | Fix HTTP client/route first |
| 2 | Is `springSecurityFilterChain` registered in the container? | Fix Security config/test setup |
| 3 | Does `FilterChainProxy` select the right `SecurityFilterChain`? | Fix `securityMatcher`/`@Order`/context path |
| 4 | Does the chain contain the expected authentication filter? | Enable DSL/filter configuration |
| 5 | Is the filter invoked and does its internal matcher accept the request? | Fix `loginProcessingUrl`/method/Bearer header/CSRF/CORS |
| 6 | Does the filter create the right concrete `Authentication` type? | Fix token factory/converter |
| 7 | Does the filter call the right `AuthenticationManager`? | Fix per-chain manager binding |
| 8 | Does the manager hold the right providers and order? | Fix explicit list/parent wiring |
| 9 | Does `supports(token.class)` accept properly? | Fix `supports`; test type/subclass |
| 10 | Does the provider return null/exception/success per policy? | Fix provider logic/DB/decoder |
| 11 | Is the parent called under the right rules? | Review fallback/downgrade/short-circuit |
| 12 | Is the authenticated result saved to context when needed? | Fix `saveContext`/cookie/session |
| 13 | Does authorization still block? | Fix role/scope/ownership mapping |
| 14 | Does the HTTP response follow the protocol? | Fix failure handler/entry point/CSRF/CORS |

Keep one piece of evidence per step (redacted log line, test assertion, config snapshot). Only edit code/config after finding the **first failing boundary**. Do not disable CSRF, swap `ProviderManager`, alter user details, and change filter order all at once; otherwise you will not know which change resolved the problem.

## 16. Java 17 Spring Boot Demo: Two Chains, One Explicit Manager

The demo below shows the same `DaoAuthenticationProvider` used explicitly by **two different chains**: `/api/**` uses stateless HTTP Basic; web uses session form login. The goal is to confirm **request matcher/filter separation** before investigating providers.

### 16.1. Dependencies

In a Java 17 Spring Boot 3.5.x project with the Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 16.2. Main Class and SecurityFilterChains

Save `src/main/java/demo/diagnosis/DiagnosticApplication.java`:

```java
package demo.diagnosis;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    DaoAuthenticationProvider passwordProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider dao =
                new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        return dao;
    }

    @Bean
    AuthenticationManager passwordManager(
            DaoAuthenticationProvider dao) {
        return new ProviderManager(List.of(dao));
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(
            HttpSecurity http, AuthenticationManager passwordManager)
            throws Exception {
        return http
                .securityMatcher("/api/**")
                .authenticationManager(passwordManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(
            HttpSecurity http, AuthenticationManager passwordManager)
            throws Exception {
        return http
                .authenticationManager(passwordManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Public";
        }

        @GetMapping("/api/me")
        String api(Authentication authentication) {
            return "API:" + authentication.getName();
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "WEB:" + authentication.getName();
        }
    }
}
```

**Intentional explicit points:**

- `@Order(1)` and `securityMatcher("/api/**")`: the API chain is evaluated first.
- The API chain enables only `httpBasic`, not `formLogin`. There is no Bearer JWT in this demo.
- The catch-all web chain has `formLogin` and does not receive `/api/me` requests because the API chain wins.
- Both chains attach **the exact `passwordManager` bean**, which contains only `DaoAuthenticationProvider` using the Spring Security 6.5 constructor/API.
- `PasswordEncoder` uses BCrypt for illustration; the local password is only a test fixture, not for production.
- The API uses stateless GET; APIs with write operations need tailored CSRF protection based on how clients carry credentials. **Do not globally disable CSRF with `csrf.disable()`**.
- The app has no JWT decoder, LDAP, OIDC client, or custom filter — if you need those mechanisms, add the appropriate filter/manager, not a password provider.
- Login/routing demo only; no user database, rate limiting, audit, persistent session store, HTTPS, or advanced account lifecycle.

### 16.3. Running and Reading Responses

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. With default server port 8080:

```bash
# API without credentials: HTTP 401 + Basic challenge.
curl -i http://localhost:8080/api/me

# API with valid Basic: HTTP 200, body "API:alice".
curl -i -u alice:demo-password http://localhost:8080/api/me

# Browser route when anonymous: HTTP 302 -> /login.
curl -i -H 'Accept: text/html' http://localhost:8080/private

# Public route: HTTP 200, body "Public".
curl -i http://localhost:8080/
```

Expected results:

| Request | Status | Characteristic |
| --- | --- | --- |
| `GET /api/me` without Authorization | 401 | `WWW-Authenticate: Basic...` |
| `GET /api/me` with valid Basic | 200 | Body `API:alice` |
| `GET /api/me` with wrong Basic | 401 | No authenticated principal created |
| `GET /private` anonymous | 302 | `Location` pointing to `/login` |
| `GET /` anonymous | 200 | `Public` |
| `POST /login` via form with CSRF, valid credentials | 302 or success redirect per form config | Browser has a logged-in session |

Use `curl -i` instead of `curl -L` to see the first redirect. Do not confuse `HTTP 401` with `ProviderNotFoundException` when the Basic header is merely missing: requests without credentials may never invoke the manager.

## 17. MockMvc Integration Test: Proving Real Chains and Authentication Filters

Create `src/test/java/demo/diagnosis/DiagnosticWebTest.java`:

```java
package demo.diagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiHasBasicChallengeWithoutCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate",
                        containsString("Basic")));
    }

    @Test
    void apiAuthenticatesBasicCredential() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("API:alice"));
    }

    @Test
    void apiRejectsBadBasicPassword() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void browserRedirectsToLogin() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/login")));
    }

    @Test
    void interactiveFormLoginAuthenticatesAlice() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-password"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void publicPageIsAllowed() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public"));
    }
}
```

Run:

```bash
./gradlew test --tests demo.diagnosis.DiagnosticWebTest
```

Expect **6 PASSING tests** when run on the matching stack/version. MockMvc goes through the Spring Security filter chain thanks to `@AutoConfigureMockMvc`/`spring-security-test`; if you use `MockMvcBuilders.standaloneSetup(...)` manually, attach `springSecurity()` or `FilterChainProxy` properly.

**Warning:** `.with(user("alice"))` is a test fixture that injects an authenticated principal, **bypassing password/provider verification**. It is fine for authorization tests, but it does not prove `ProviderManager`/`DaoAuthenticationProvider` ran. Therefore the example uses `httpBasic(...)` and `formLogin()` to exercise real login mechanisms.

### 17.1. Avoiding False Positives

A test that only calls `GET /private` and gets 302 can PASS even if the login filter **is broken**. You need at least one test that submits **valid credentials** and proves an authenticated result. Likewise, testing that an API returns 401 without Authorization only proves the protected resource/entry point works, not that `DaoAuthenticationProvider` was used.

Reuse the session/cookie from a successful login request if you want to test subsequent requests. If the frontend sends cookies on the wrong path or a load balancer drops sessions, provider unit tests will still PASS — in that case, it is a context/session bug, not a manager bug.

## 18. Unit Testing ProviderManager: Pinpointing Which Provider Receives the Token

When HTTP tests still do not explain the behavior, isolate the manager in a **JUnit/Mockito test** to inspect `supports`, ordering, `null` returns, exceptions, and parent behavior. This is a component test and **does not exercise HTTP filters**.

Create `src/test/java/demo/diagnosis/ProviderSelectionTest.java`:

```java
package demo.diagnosis;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ProviderSelectionTest {

    private static final Class<UsernamePasswordAuthenticationToken> TYPE =
            UsernamePasswordAuthenticationToken.class;

    private Authentication request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-password");
    }

    private Authentication accepted(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "test-secret",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private AuthenticationProvider provider(boolean supports) {
        AuthenticationProvider p = mock(AuthenticationProvider.class);
        when(p.supports(TYPE)).thenReturn(supports);
        return p;
    }

    @Test
    void supportsFalseMeansProviderIsSkipped() {
        AuthenticationProvider p1 = provider(false);
        AuthenticationProvider p2 = provider(true);
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("p2"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("p2", manager.authenticate(request()).getName());

        verify(p1, never()).authenticate(any(Authentication.class));
        verify(p2).authenticate(any(Authentication.class));
    }

    @Test
    void nullMeansTryNextProviderInOrder() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class))).thenReturn(null);
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("p2"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("p2", manager.authenticate(request()).getName());

        InOrder order = inOrder(p1, p2);
        order.verify(p1).supports(TYPE);
        order.verify(p1).authenticate(any(Authentication.class));
        order.verify(p2).supports(TYPE);
        order.verify(p2).authenticate(any(Authentication.class));
    }

    @Test
    void firstAuthenticatedResultStopsTraversal() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class)))
                .thenReturn(accepted("first"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("first", manager.authenticate(request()).getName());

        verify(p2, never()).supports(any());
        verify(p2, never()).authenticate(any(Authentication.class));
    }

    @Test
    void ordinaryBadCredentialsMayFallThrough() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("rejected"));
        when(p2.authenticate(any(Authentication.class)))
                .thenReturn(accepted("second"));

        var manager = new ProviderManager(List.of(p1, p2));
        assertEquals("second", manager.authenticate(request()).getName());
    }

    @Test
    void lockedStopsNextProviderAndParent() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new LockedException("locked"));

        var manager = new ProviderManager(List.of(p1, p2), parent);

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        verify(p2, never()).supports(any());
        verifyNoInteractions(parent);
    }

    @Test
    void internalServiceFailureStopsFallback() {
        AuthenticationProvider p1 = provider(true);
        AuthenticationProvider p2 = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(p1.authenticate(any(Authentication.class)))
                .thenThrow(new InternalAuthenticationServiceException(
                        "backend unavailable"));

        var manager = new ProviderManager(List.of(p1, p2), parent);

        assertThrows(InternalAuthenticationServiceException.class,
                () -> manager.authenticate(request()));
        verify(p2, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void childDeclinesSoParentIsUsed() {
        AuthenticationProvider child = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(child.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        var manager = new ProviderManager(List.of(child), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void noSupportedProviderYieldsProviderNotFound() {
        AuthenticationProvider child = provider(false);
        var manager = new ProviderManager(List.of(child));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        verify(child, never()).authenticate(any(Authentication.class));
    }
}
```

Run:

```bash
./gradlew test --tests demo.diagnosis.ProviderSelectionTest
```

Expect **8 PASSING tests**. This suite proves manager semantics. It does not run LDAP, password encoders, JWT decoders, or filters. To verify application wiring, combine it with the integration tests in Section 17 or tests specifically targeting the bean/manager attached to the chain.

### 18.1. Key Signals in the Tests

- `verify(p1, never()).authenticate(...)` proves `supports=false` leads to skipping.
- `InOrder` verifies **ordering**, avoiding reliance on success status alone.
- `verifyNoInteractions(parent)` verifies exceptions stop early.
- The `BadCredentials` + provider 2 success test highlights fallback risk if two providers have different password policies.
- `ProviderNotFoundException` is a type-support/config error, not necessarily a wrong password.
- A mock provider test with `supports=true` and `authenticate=null` tests **manager traversal**, not a provider bug.

## 19. Custom API-Key Filter Case: Four Points That Must Align

When designing a custom API-key mechanism, verify all four simultaneously:

1. `ApiKeyAuthenticationFilter` is in the right chain.
2. It reads the credential from the right source (header/query/body per policy) and **activates only on the right URL/method**.
3. It creates an unauthenticated `ApiKeyAuthenticationToken` and calls **the manager containing `ApiKeyAuthenticationProvider`**.
4. The provider `supports(ApiKeyAuthenticationToken.class)` and actually verifies token hash, expiry, revocation, and account/tenant status before returning an authenticated `Authentication`.

Illustrative boundary example:

```java
// Excerpt inside a custom authentication filter:
String apiKey = request.getHeader("X-Api-Key");
if (apiKey != null && !apiKey.isBlank()) {
    Authentication unauthenticated =
            new ApiKeyAuthenticationToken(apiKey);
    Authentication accepted =
            authenticationManager.authenticate(unauthenticated);
    // Must use success strategy / context repository per contract.
}
// If the header is missing, policy must decide whether to skip or return 401.
```

`ApiKeyAuthenticationToken`, the filter, and `authenticationManager` are **custom application abstractions**; the snippet does not compile standalone. Do not manually call `SecurityContextHolder.getContext().setAuthentication(...)` and ignore saving/clearing and failure handling. Using `AuthenticationFilter`, a converter, and success/failure handlers where appropriate reduces bugs.

### 19.1. Do Not Register the Filter on Every Chain

If API keys are only valid for `/service/**`, attach the filter only to that chain; when the path does not match, do not handle it. A custom filter present in the browser chain could accidentally accept an API key on admin pages, breaking the trust boundary.

### 19.2. Testing Custom Tokens

Write tests:

```java
assertTrue(apiKeyProvider.supports(ApiKeyAuthenticationToken.class));
assertFalse(apiKeyProvider.supports(
        UsernamePasswordAuthenticationToken.class));
```

This is an excerpt inside a JUnit class where `apiKeyProvider` and `ApiKeyAuthenticationToken` are defined. Then create filter integration tests for missing header, bad header, valid header, revoked key, different tenant, concurrent requests, and context logout. **Do not** test by injecting an authenticated principal and calling the API key verified.

## 20. Common Configuration Traps and How to Fix Them

### 20.1. "Provider bean exists in context, but does not run"

**Most likely:** the filter uses a different `AuthenticationManager`, or a filter/matcher is missing. Check logs for the actual manager, then attach the provider via `http.authenticationProvider(provider)` or build an explicit `ProviderManager` for the chain. Do not fix blindly by adding `@Primary` when multiple manager scopes exist.

### 20.2. "Form login does not run after adding SecurityFilterChain"

A custom chain requires `formLogin(...)` explicitly if form login is desired. Check if `UsernamePasswordAuthenticationFilter` is present; if not, add `formLogin` to the **web chain**, not the stateless Bearer API chain.

### 20.3. "POST /login returns 404"

You may have changed `loginProcessingUrl`, or the web chain does not match `/login`. `UsernamePasswordAuthenticationFilter` only processes matching requests; if no controller/route handles POST, Spring MVC may return 404/405. Do not write a custom controller accepting passwords and forging an authenticated token just to eliminate the 404.

### 20.4. "POST /login returns 403 and there are no provider logs"

`CsrfFilter` may reject the request before the login filter runs. Send a valid CSRF token. With `spring-security-test`, use `formLogin()` or `.with(csrf())`. Do not disable CSRF globally just to make tests green.

### 20.5. "Using POST JSON /login, but provider sees null password"

The default form filter reads form parameters, not arbitrary JSON. Choose `Content-Type: application/x-www-form-urlencoded` or build a JSON `AuthenticationConverter`/filter with valid CSRF and failure handlers. Never log the password to debug.

### 20.6. "Every API request gets 302 to /login"

The API may be falling into the catch-all web chain due to wrong `@Order` or matcher, or only `formLogin` is enabled. For a Bearer resource server, attach the right API chain and `oauth2ResourceServer`. Distinguish the initial 302 response from a final 200 after the client follows redirects.

### 20.7. "Valid JWT gives BadCredentialsException from DAO?"

If a raw Bearer token is turned into `UsernamePasswordAuthenticationToken` or the app routes to a Basic/password chain, that is a wrong mechanism/token type. Check the API chain, bearer filter/decoder, and request converter. DAO is not responsible for verifying JWTs.

### 20.8. "ProviderNotFoundException with custom OTP"

Check the concrete input token class, `supports`, the provider list on the right chain's manager, and whether the custom filter actually calls that manager. Avoid registering a provider bean and forgetting to wire the manager.

### 20.9. "BadCredentials from first provider, yet login succeeds"

A later provider or parent may be succeeding. Audit for security downgrade/legacy fallback. Do not "fix" by throwing a fake `LockedException`; separate token realms or authoritative checks instead.

### 20.10. "LDAP timeout error still falls back to local password"

If infrastructure errors are converted into `BadCredentialsException`, `ProviderManager` can try a fallback. When an authentication backend cannot verify credentials, enforce **fail closed** and throw the appropriate service error (`InternalAuthenticationServiceException` when applicable). Do not open bypass paths during outages.

### 20.11. "Logged in, yet next request is still anonymous"

Inspect response `Set-Cookie`, whether the browser sends the cookie back, `SessionCreationPolicy`, `SecurityContextRepository.saveContext` for custom logins, load balancer, Redis/Spring Session, and context propagation. Do not change providers if the prior request already authenticated successfully.

### 20.12. "Custom filter runs twice"

Check Servlet auto-registration of the `Filter` bean alongside `HttpSecurity.addFilter...`. Disable container registration when the filter belongs only to the security chain. Verify against double events, double OTP consumption, and duplicate logs.

### 20.13. "MockMvc.with(user()) passes, production login fails"

`with(user())` creates a test principal, bypassing the manager. Test `formLogin()`, `httpBasic()`, or real Bearer requests; use the proper Spring Security Test/`FilterChainProxy` setup. Do not extrapolate from authorization tests to authentication tests.

### 20.14. "User has role USER but gets 403 on /admin"

The manager likely authenticated correctly, while `hasRole("ADMIN")` requires `ROLE_ADMIN`. This is **authorization**, not provider selection. Check granted authorities and scope/role mapping.

### 20.15. "Anonymous /login enters a redirect loop"

The custom login page is protected, or the login page URL has no route. Ensure the login page/processing endpoint belongs to the right chain and `permitAll` covers required resources. Do not let an overly broad API chain matcher intercept login callbacks.

### 20.16. "OIDC redirect_uri mismatch"

This is typically client registration/callback chain/proxy URL config, not `DaoAuthenticationProvider`. Inspect `/login/oauth2/code/{registrationId}`, issuer, authorization request session, allowed redirect URIs, and HTTPS forwarded headers.

### 20.17. "Valid Basic header still returns 401 after switching to BCrypt"

The `UserDetails` source/encoder/hash may be mismatched. Verify `PasswordEncoder.matches(raw, encoded)` using a controlled fixture; never switch to a plaintext encoder to cure the error. Check which provider actually handles the Basic token.

### 20.18. "No security logs visible"

Check the active logging profile, presence of `springSecurityFilterChain`, which application/reverse proxy the request traverses, and whether the test setup attaches filters. If behind an API gateway, the gateway may reject before the request hits the service; capture redacted HTTP/network traces from the right hop.

## 21. Diagnostic and Security Test Matrix

| ID | Scenario | Expected Verification Outcome |
| --- | --- | --- |
| D01 | `/api/**` before web catch-all | API chain selected first |
| D02 | Web catch-all ordered ahead of API (negative test) | Catches ordering bug instead of silently returning HTML redirect |
| D03 | No chain matches path | Coverage alert; security policy fails closed via fallback |
| D04 | API Basic request without header | 401 Basic challenge, no fake provider error |
| D05 | API Basic valid password | 200, expected principal/roles |
| D06 | API Basic wrong password | 401, no authenticated result |
| D07 | Browser `GET /private` anonymous | Redirect to login, no privilege change |
| D08 | Form `POST /login` + valid CSRF | Invokes authentication manager, login succeeds |
| D09 | Form `POST /login` missing CSRF | 403, provider need not be called |
| D10 | Form JSON body instead of form params | Catches converter/field mismatch |
| D11 | Changed `loginProcessingUrl` | Filter processes only the new URL |
| D12 | Custom filter bean registered in 2 places | Detects double invocation |
| D13 | Unsupported token type | `ProviderNotFoundException` |
| D14 | Provider `supports=false` | `authenticate` not called on that provider |
| D15 | Provider returns `null` | Tries next provider |
| D16 | Provider 1 succeeds | Provider 2/parent not called |
| D17 | Provider 1 `BadCredentials`, P2 succeeds | P2 wins; evaluate downgrade policy |
| D18 | Provider throws `LockedException` | No fallback |
| D19 | Provider throws `InternalAuthenticationServiceException` | No fallback |
| D20 | Child declines, parent succeeds | Parent called at the right time |
| D21 | Child + parent fail | Version-consistent exception precedence |
| D22 | Circular parent config | Cyclic configuration disallowed |
| D23 | DAO user disabled/locked | Cannot log in via password or other auth paths |
| D24 | Encoder/hash prefix mismatch | Fails closed with clear config error in tests |
| D25 | Bearer JWT missing | 401 Bearer challenge per resource-server policy |
| D26 | Bearer JWT invalid signature/issuer | Rejected, no fallback to password |
| D27 | Bearer authenticated but missing scope | 403 rather than altering provider |
| D28 | Wrong OIDC callback URL | Catches filter/redirect mismatch |
| D29 | Successful custom login without saving context | Next request is anonymous (negative test) |
| D30 | Proper context save/session cookie | Next request uses session |
| D31 | Subsequent stateless API request without token | Does not accidentally retain principal across session |
| D32 | Multiple webapp replicas | Manager/provider/keys/shared-store consistent |
| D33 | Method-security denial | 403 on the right branch, not a login failure |
| D34 | `MockMvc.with(user())` vs `formLogin()` | Proves the former bypasses provider |
| D35 | Filter logs at local TRACE | Right chain, filter order, no leaked secrets |
| D36 | CORS preflight | Preflight obeys policy, not wrongly redirected to login |
| D37 | Context path/proxy forwarding | Matcher aligns with actual path |
| D38 | Spring Security version upgrade regression | Constructors/DSL/provider wiring and errors retested |

To cut debugging time, turn D01–D20 into **automated regression tests** at the right layers: `ProviderManager` unit tests, MockMvc filter-chain tests, and database/AS/IdP integration tests. A test asserting only status 401 does not prove provider selection is right.

## 22. How to Write an Incident Investigation Ticket

A good diagnostic report gives enough detail for others to reproduce without exposing secrets:

```text
Symptom: POST /login returns 403; DaoAuthenticationProvider is never called
Environment: Spring Boot 3.5.x / Spring Security 6.5.x / Servlet
Request: POST /login, form-urlencoded, no csrf token, test account only
Selected chain: web SecurityFilterChain
Observed filters: CsrfFilter before UsernamePasswordAuthenticationFilter
First failing boundary: CSRF validation
Evidence: DEBUG "Invalid CSRF token" (redacted), MockMvc test reproduces
Root cause: frontend omitted CSRF field/header
Fix: include framework-issued CSRF token in form/POST
Validation: formLogin() test passes; POST without CSRF remains 403
Risk review: CSRF remains enabled; no authentication bypass or secret logs
```

A similar report for `ProviderNotFoundException` should state **the input token class name**, manager name, list of provider class names, and `supports` results in order; never print token values. For missing OAuth callbacks, note chain matcher/filter presence without sharing real `code` or `state`.

### 22.1. Incident Closure Criteria

Consider the issue resolved only when:

1. Requests with the right credential type traverse the chain/filter/manager defined by the architecture.
2. Valid credentials authenticate; invalid credentials are rejected.
3. Locked/disabled accounts cannot bypass via a later provider/parent.
4. Authorization still protects endpoints with the right roles/scopes.
5. Session/context persistence matches intent (web has sessions; stateless APIs do not create persistent logins).
6. CSRF/issuer verification/password hashing were not disabled and anonymous access was not opened to "fix 401".
7. Regression tests include negative cases and logs do not leak credentials.

## 23. Plain Java 17 Exercise: Finding the First Failing Boundary

To remember the diagnostic workflow, the program below models **four checkpoints**: chain match, filter match, token class `supports`, and provider result. This is **not** real Spring Security; it is a learning model showing why a manager might never be called.

Save `AuthPipelineDiagnosis.java`:

```java
import java.util.List;

public class AuthPipelineDiagnosis {

    record Request(String path, String method, String tokenType) {}

    interface Provider {
        boolean supports(String type);
        boolean accepts(Request request);
    }

    static String diagnose(Request request, List<Provider> providers) {
        boolean chainMatches = request.path().startsWith("/secure/");
        if (!chainMatches) {
            return "NO_CHAIN";
        }

        boolean loginFilterMatches =
                "/secure/login".equals(request.path())
                && "POST".equals(request.method());
        if (!loginFilterMatches) {
            return "FILTER_SKIPPED";
        }

        for (Provider provider : providers) {
            if (!provider.supports(request.tokenType())) {
                continue;
            }
            if (provider.accepts(request)) {
                return "AUTHENTICATED";
            }
        }
        return "NO_PROVIDER_SUCCESS";
    }

    public static void main(String[] args) {
        Provider passwordProvider = new Provider() {
            public boolean supports(String type) {
                return "PASSWORD".equals(type);
            }

            public boolean accepts(Request request) {
                return true; // simulates a valid fixture, DOES NOT verify passwords.
            }
        };

        List<Provider> providers = List.of(passwordProvider);

        System.out.println(diagnose(
                new Request("/open", "POST", "PASSWORD"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "GET", "PASSWORD"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "POST", "API_KEY"), providers));
        System.out.println(diagnose(
                new Request("/secure/login", "POST", "PASSWORD"), providers));
    }
}
```

Run with JDK 17+:

```bash
javac AuthPipelineDiagnosis.java
java AuthPipelineDiagnosis
```

**Exact stdout:**

```text
NO_CHAIN
FILTER_SKIPPED
NO_PROVIDER_SUCCESS
AUTHENTICATED
```

Each output represents:

- `NO_CHAIN`: the request was not protected by the expected Spring Security chain.
- `FILTER_SKIPPED`: the chain existed, but the request was not a login-processing POST.
- `NO_PROVIDER_SUCCESS`: the filter assumed token submission, but no provider accepted that token type.
- `AUTHENTICATED`: token type matched and the model returned success.

**Do not use this code to authenticate real users.** It does not check passwords, CSRF, sessions, OAuth signatures, account status, or exception precedence; those must be verified with Spring Security unit/integration tests from Sections 17–18.

## 24. Production Checklist and Anti-Misfix Rules

1. **HTTP evidence:** record method, path, redacted headers, content type, cookie presence, and initial status without relying on browser auto-redirects.
2. **Chains:** explicit `@Order` + `securityMatcher`; API matchers before web catch-all, with fallback protecting all required paths.
3. **Filters:** confirm the right filter exists and receives the request; default form handles POST form-urlencoded, Basic/Bearer require `Authorization` headers.
4. **CSRF/CORS:** never disable protection just because login POST returned 403; check CSRF and OPTIONS at the right layer.
5. **Token types:** trace the concrete class of unauthenticated `Authentication`, do not confuse it with result classes; every custom provider `supports` the exact class.
6. **Provider order:** explicit list when security depends on order; never leave a weaker legacy password fallback behind.
7. **Parent:** attach a parent only when policy allows; avoid circular references and surprise fallbacks after `BadCredentials`.
8. **Error semantics:** `Locked`/`Disabled`/`InternalAuthenticationServiceException` must not be turned into `BadCredentials` arbitrarily.
9. **DAO:** verify `UserDetailsService`, encoder, hash format, account status, and caches from the source of truth.
10. **Other mechanisms:** JWT/OIDC/opaque/OTT/passkeys have dedicated filters/providers; never force DAO to handle the wrong request type.
11. **Context:** custom successful authentication must be saved per Spring Security 6 explicit-save contract if persistence is needed; stateless APIs are a different design.
12. **Authorization:** 403 for missing role/authority is not an authentication provider bug.
13. **Tests:** HTTP/MockMvc tests for real login and `ProviderManager` unit tests; `with(user())` is only for bypassing authentication to test authorization.
14. **Observability:** time-boxed DEBUG/TRACE, audit correlation IDs and error categories, never log credentials/JWTs/session IDs.
15. **Regression:** test multiple chains, provider order, exception precedence, callback URLs, proxy paths, stateless/session modes, and version upgrades.

**Summary:** If "`ProviderManager` selects the wrong provider", first prove **the request reached the right manager**. Trace from `FilterChainProxy` through `SecurityFilterChain`, the authentication filter, input token class, `supports`, provider order, and parent fallback, and only then to context/session and authorization. Fixing at the **first failing boundary** is far more accurate and safer than toggling off protections until the request returns 200.

## 25. Official Documentation

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, filters, and context.
- [Spring Security 6.5.11 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider iteration, exception precedence, parent, credential erasure, and events.
- [Spring Security 6.5.11 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`/`authenticate` and returning `null`.
- [Spring Security 6.5 — Multiple HttpSecurity and matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `@Order`, `securityMatcher`, `requestMatchers`, chain coverage.
- [Spring Security — Servlet Architecture / Logging](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, filter order, DEBUG/TRACE logging, custom filter registration.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): login page/POST processing, success/failure handlers.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService`, `PasswordEncoder`, username/password token flow.
- [Spring Security 6.5.11 — DaoAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `DaoAuthenticationProvider(UserDetailsService)` constructor, `setPasswordEncoder`.
- [Spring Security 6.5 — MockMvc setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()` and `FilterChainProxy`.
- [Spring Security — Testing form login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` and CSRF.
- [Spring Security — MockMvc user fixture](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `with(user(...))` and differences from authentication testing.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save, and stateless sessions.
- [Spring Security — OAuth2 Resource Server/JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `BearerTokenAuthenticationFilter`, `JwtDecoder`, JWT/authorities.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): authorization-code flow and callbacks.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `WWW-Authenticate`, 401/403 semantics.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): classifying authentication failures, preventing user enumeration, and protecting credentials.
