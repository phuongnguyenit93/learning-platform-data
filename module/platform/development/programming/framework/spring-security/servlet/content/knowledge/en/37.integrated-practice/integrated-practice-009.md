# Investigating Filter, Matcher, and SecurityContext Failures from Request Traces in Spring Security Servlet

## 1. Practice Problem: "Same API—Why 401, 403, or the Wrong Handler?"

Suppose a Spring Boot application using Spring Security Servlet hits these issues:

- `GET /api/me` returns **401 Unauthorized** even when valid credentials are sent.
- `POST /api/notes` from a user holding `ROLE_EDITOR` returns **403 Forbidden**.
- `GET /api/admin/audit` returns 403 as expected for normal users, yet similar URLs slip through because of a **broad request matcher** or a different filter chain being selected.
- A controller observes `SecurityContextHolder.getContext().getAuthentication() == null` even though a filter previously authenticated successfully.
- Two consecutive requests or an `@Async` task see different principals.
- Logs print "Securing ..." without clarifying **which chain**, filter, or rule caused the outcome.

This is an **integrated practice**: instead of fixing 403s by adding `permitAll()`, we build a systematic investigation method grounded in **ordered request traces and verifiable evidence**.

Specific objectives:

1. Identify the exact **HTTP method, internal application path, Servlet dispatcher type, authentication mechanism, and correlation ID**.
2. Locate the **selected `SecurityFilterChain`** and understand the difference between `securityMatcher` (selecting a chain) and `requestMatchers` (authorizing inside a chain).
3. Trace key filters: `SecurityContextHolderFilter`, `CsrfFilter`, `BasicAuthenticationFilter` or login filters, `AnonymousAuthenticationFilter`, `ExceptionTranslationFilter`, and `AuthorizationFilter`.
4. Distinguish **authentication failures**, **authorization denials**, **CSRF rejections**, MVC routing issues, **method security** denials, and **SecurityContext lifecycle/propagation** bugs.
5. Build a **Java 17, Spring Boot 3.3.5, Spring Security 6 Servlet** application with two chains, a safe diagnostic filter, role-based endpoints, and `@PreAuthorize`.
6. Reproduce with **MockMvc/JUnit 5** and verify evidence before changing configuration, avoiding accidental privilege widening.

**Boundary:** the example uses `{noop}` passwords and HTTP Basic **for local learning only**. Boot 3.3.5 is a deliberate baseline, **not** a claim about the latest release or a CVE-free production stack. Production requires current dependencies/security advisories, HTTPS, a real PasswordEncoder, a real identity source, object-level ACL checks, and PII-safe observability.

## 2. Map of a Request's Path

In a typical Servlet application, a browser or HTTP client sends requests to the Servlet container. Spring Security integrates via `DelegatingFilterProxy`, forwarding to `FilterChainProxy`. The proxy matches declared `SecurityFilterChain`s in order and invokes the security filters of the **first matching chain**. Only if those filters let the request proceed does execution reach `DispatcherServlet` and Spring MVC handlers.

~~~text
Client: GET /api/me
        |
        v
Servlet container filters
        |
        v
DelegatingFilterProxy("springSecurityFilterChain")
        |
        v
FilterChainProxy
        |
        +-- Chain #1 securityMatcher("/api/**")? ------ YES
        |                                               |
        |                                         Security filters
        |                                               |
        |                                  SecurityContextHolderFilter
        |                                  HeaderWriterFilter
        |                                  [Demo TraceFilter]
        |                                  CsrfFilter
        |                                  BasicAuthenticationFilter
        |                                  AnonymousAuthenticationFilter
        |                                  ExceptionTranslationFilter
        |                                  AuthorizationFilter
        |                                               |
        |                                               v
        |                                        DispatcherServlet
        |                                               |
        |                                               v
        |                                       @RestController / service
        |
        +-- Chain #2 fallback? ---------------- Only if #1 does not match

After processing: response unwinds back through filters;
SecurityContext is cleared per the security chain's lifecycle.
~~~

This is a **simplified diagram**, not an exhaustive list or immutable order for every application. Filter order changes when enabling form login, OAuth2/OIDC, JWT resource server, CORS, logout, request cache, session management, custom filters, or other Spring Security settings.

Three questions **must be answered in order**:

1. **Did the request actually enter Spring Security?** Check filter registration, servlet path, `securityMatcher`, proxy/gateway routing, static resource handlers, and the case where no chain matches.
2. **Where did it stop?** Authentication failure, invalid CSRF, authorization filter denial, method security denial, or an unrelated controller exception?
3. **At the decision point, what was Authentication?** Absent, anonymous, authenticated Basic/session/JWT, wrong principal type, or missing/misnamed authorities?

Checking the HTTP status alone is insufficient: **403** can originate from `CsrfFilter`, `AuthorizationFilter`, `@PreAuthorize`, or a custom `AccessDeniedHandler`. Never apply fixes without evidence pointing to the responsible layer.

## 3. Collecting an "Incident Dossier" from Request Traces

Before changing code, capture a minimal reproducible record:

| Field | Example | Purpose |
| --- | --- | --- |
| Request ID | Server-generated `7f3e...` | Correlate multi-component logs for one request |
| HTTP method | `GET`, `POST`, `PUT`, `DELETE` | Match against matchers and CSRF policy |
| Request path | `/api/notes` | Verify path/servlet mapping behind proxies |
| Dispatcher type | `REQUEST`, `FORWARD`, `ERROR`, `ASYNC` | Check if filters are registered for that dispatch type |
| Authentication source | Basic, session, bearer JWT, OAuth2 Login | Identify which filter/provider is responsible |
| Authentication state | absent / anonymous / verified | Separate 401 from 403 |
| Authorities | `ROLE_EDITOR`, `ROLE_ADMIN` (masked/restricted when logged) | Check hasRole/hasAuthority |
| Expected rule | `POST /api/notes -> ROLE_EDITOR` | Compare against authorization contract |
| CSRF state | required + missing/invalid/valid | Explain 403 on unsafe requests |
| Status + response headers | 401/403/200/201 + `WWW-Authenticate` | Verify entry point/handler |
| Runtime config version | commit, artifact digest, profile | Investigate staging vs. production drift |
| Chain/filter signal | FilterChainProxy logs, trace ID | Pinpoint the specific chain/filter |

**Never collect raw passwords, `Authorization` headers, bearer tokens, CSRF tokens, session cookies, reset links, OIDC ID tokens, or sensitive raw request bodies** into reports or debug logs. When paths include accounts, emails, document IDs, or query secrets, log only the route template (`/api/files/{id}`) or a redacted form.

Example safe record:

~~~text
incident=INC-42
trace=7f3e...
method=POST route=/api/notes dispatcher=REQUEST
identity_state=authenticated principal_kind=User
expected=ROLE_EDITOR csrf_required=true csrf_present=false
status=403
hypothesis=CSRF_FILTER_REJECTED_BEFORE_BASIC_AUTH
verification=repeat request with valid CSRF in an isolated test
~~~

**A hypothesis is not a conclusion**: confirm it against chain/filter logs and controlled tests. If the app moves to a bearer-only API with a different session policy, evaluate CSRF policy per threat model rather than inferring from JSON responses.

### 3.1. Comparing Browser Requests vs. curl

Sometimes the "same URL" differs in key details:

- Browsers send session cookies; curl omits cookies unless explicitly saved and replayed across requests.
- Browsers send `Origin`, `Referer`, and CORS preflight OPTIONS; curl may not.
- Browsers submit forms/JSON via POST with CSRF tokens; curl omits the token.
- Proxies rewrite `/app/api/me` to `/api/me`; external and internal logs show different paths.
- Browsers follow 302 redirects to `/login`; curl by default does not follow redirects, or `-L` hides the initial response.
- Browsers issue retries, prefetches, or parallel requests; one UI click can emit multiple HTTP requests.

Therefore record **request method, normalized internal path, initial status, and cookie/header presence**, not just "I logged in and got rejected".

## 4. FilterChainProxy Selects the Chain Before Checking Permissions

Each `SecurityFilterChain` has a `RequestMatcher` deciding whether that chain handles a request. With multiple chains:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/healthcheck").permitAll()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is a **configuration snippet**, lacking full imports and application wiring; the runnable project is in Section 10.

- `securityMatcher("/api/**")` decides **which requests Chain 1 handles**. It does not permit requests; authorization happens **afterward** inside `authorizeHttpRequests`.
- Chain 2 has no `securityMatcher`, acting as a **fallback** for requests that do not match Chain 1.
- Inside a single chain, `requestMatchers(...)` are evaluated in declaration order: the first matching rule wins.
- `@Order(1)` and `@Order(2)` govern **chain** evaluation order; rule order inside a chain is a separate axis.
- **Chain 1's `anyRequest().denyAll()` does not protect URLs outside `/api/**`.** Without a fallback or another matching chain, unmatched URLs may bypass Spring Security altogether.

### 4.1. Classic Mistake: Mis-Scoped securityMatcher

~~~java
// Problematic if the real API lives under /api/**.
http.securityMatcher("/web/**")
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated());
~~~

The `/api/admin/**` rule inside this chain may **never be evaluated** for `/api/admin/report` because the chain never selects that request. Seeing `hasRole("ADMIN")` in source code does not prove the endpoint is protected.

To investigate, inspect `FilterChainProxy` logs to see which chain matched, then verify which filters ran. If no chain matched, do not try fixing it by tweaking `hasRole` inside an unselected chain.

### 4.2. Classic Mistake: Broad Matcher Swallowing a Narrow Matcher

~~~java
// Dangerous: /api/admin/** also matches /api/**.
auth.requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN");
~~~

Any authenticated user clears the broad rule first. Move specific rules before broader ones:

~~~java
auth.requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll();
~~~

**Rule order and chain order are two orthogonal axes.** Never change both simultaneously during an investigation, or you won't know which change resolved the issue or whether you opened another bypass.

### 4.3. Path Matching Is More Than Wildcards

Inspect differences between `requestURI`, `contextPath`, `servletPath`, `pathInfo`, reverse-proxy prefixes, and MVC-decoded/normalized paths. With multiple `DispatcherServlet`s or custom servlet paths, matcher selection may require explicit configuration (e.g., `MvcRequestMatcher.Builder` and `HandlerMappingIntrospector` where applicable).

Never blindly prepend `server.servlet.context-path` to every matcher; verify matcher semantics and container request attributes. Also test encoded slashes, trailing slashes, path parameters, and HTTP methods if the application accepts them.

## 5. Filter Order Determines What Evidence You See

A typical chain yields these diagnostic signals:

| Component | Role in Investigation | Key Signal |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Supplies context for the request and clears it at completion | Is context loaded/cleared per lifecycle? |
| `HeaderWriterFilter` | Writes security headers | Testing status alone is insufficient; check headers |
| `CorsFilter` (when enabled) | Handles CORS/preflight | OPTIONS may be handled before auth |
| `CsrfFilter` | Validates tokens on unsafe methods per policy | POST fails 403 **before** authentication |
| `LogoutFilter` | Processes logout endpoint | Logout path/method/CSRF |
| `UsernamePasswordAuthenticationFilter` | Performs form login when enabled | POST login, failure/success handlers |
| `BasicAuthenticationFilter` | Parses Basic credentials and authenticates | 401 for missing/wrong credentials per entry point |
| `BearerTokenAuthenticationFilter` | Parses bearer tokens when resource server is enabled | Decoder/introspection errors, signature/issuer/audience |
| `AnonymousAuthenticationFilter` | Sets anonymous token when unauthenticated | Anonymous token can exist yet is not a logged-in user |
| `ExceptionTranslationFilter` | Translates security exceptions to entry point / denied responses | 401 / redirect / 403 |
| `AuthorizationFilter` | Enforces URL authorization | Deny rule, method/path/role mismatch |
| Method security interceptor | Checks `@PreAuthorize` when service proxy is invoked | URL allowed through yet service still denies |

**Never assume every filter runs on every request.** For example, a tokenless POST can stop at `CsrfFilter`, so the downstream Basic authentication filter never runs. Placing a trace filter **after CsrfFilter** and claiming "no trace = request never reached Spring Security" is false.

A helpful demo technique: insert the diagnostic filter **before `CsrfFilter` but after SecurityContext initialization**. It logs requests entering CsrfFilter and records the status unwinding from downstream. Still, logs at an early filter **do not** replace fine-grained traces distinguishing `BasicAuthenticationFilter`, `ExceptionTranslationFilter`, or method security denials.

### 5.1. Why Can Exceptions Turn Into 401 or 403?

Simplified flow:

~~~text
Authorization / Method security throws AccessDeniedException
                         |
                         v
               ExceptionTranslationFilter
                         |
            +------------+-------------+
            |                          |
       Anonymous /                  Authenticated
       no login                     without permission
            |                          |
            v                          v
      AuthenticationEntryPoint    AccessDeniedHandler
      401 or 302 redirect               403

AuthenticationException from authentication flow
            |
            v
      AuthenticationEntryPoint
      401 or redirect /login
~~~

`ExceptionTranslationFilter` does not authenticate requests itself. It translates security exceptions into matching responses or redirects. Authentication filters can also handle failures directly. A `@ControllerAdvice` or custom exception handler can alter status codes too, so inspect **both the filter chain and MVC exception handling**.

**401 vs. 403 in the HTTP Basic demo:**

- Anonymous / wrong Basic password on a protected GET → **401**.
- Valid Basic credentials lacking the required role → **403**.
- POST with missing/invalid CSRF → **403** even with the right role; this status does not prove authorization rules ran.
- URL matching no controller but hitting Security's default deny → may return **401/403 instead of 404/405**.
- With form login, an anonymous request may receive a **302 redirect** to login rather than 401.

## 6. SecurityContext: Where Identity Lives and When It Disappears

`SecurityContextHolder` provides access to the **current execution thread's** context according to the configured strategy. In most Servlet apps, the default strategy is `ThreadLocal`-based.

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

This Java snippet requires importing `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`.

Common states:

| `Authentication` | Meaning | Pitfall |
| --- | --- | --- |
| `null` | Not set yet or no authenticated context at read time | Does not prove Basic filter is absent; may be read too early or too late |
| `AnonymousAuthenticationToken` | Anonymous token populated by filter | `isAuthenticated()` can be true, **never** treat it as a successful login |
| `UsernamePasswordAuthenticationToken` | May represent form/Basic/provider auth or an unauthenticated token | Check `isAuthenticated`, authorities, and provider flow |
| `JwtAuthenticationToken` | Identity from verified JWT resource server | Check issuer/audience/scopes/authority mapping; don't trust raw claims |
| `OAuth2AuthenticationToken` | Identity after OAuth2 Login | Distinguish external ID from local user/roles |
| Custom domain principal | Identity mapped from IdP/DB | Test exact class, tenant, account ID, and permissions |

**Specifically:** Spring Security distinguishes anonymous callers from authenticated users; never manually check `authentication != null && authentication.isAuthenticated()` and grant access to an `AnonymousAuthenticationToken`. Use `authenticated()`, `fullyAuthenticated()`, or `AuthenticationTrustResolver` when policy requires it.

### 6.1. SecurityContextHolderFilter and Persistence

In typical Spring Security 6 configurations, `SecurityContextHolderFilter` **supplies the SecurityContext from `SecurityContextRepository` into the holder for the request lifecycle** and clears it at the end. Unlike legacy setups using `SecurityContextPersistenceFilter`, never assume **simply setting the context** in custom auth code automatically persists it into the HTTP session.

If you implement a manual login flow instead of letting a framework-managed authentication filter handle it, configure an appropriate `SecurityContextRepository` and **call `saveContext` at the right moment** to persist authentication across requests. Behavior depends on your exact version/config; never copy legacy session snippets without checking save semantics.

Diagnostic signs:

- Request **A** authenticated cleanly, yet request **B** has no principal: inspect cookies/sessions, `SecurityContextRepository`, session creation policy, logout, save semantics, and whether request B resent credentials.
- `SessionCreationPolicy.STATELESS`: do not expect Basic/JWT auth on request A to create a login session for request B; tokens/credentials must normally accompany each request.
- An empty `SecurityContextHolder.getContext()` on a **non-request thread** does not prove the original request was unauthenticated.
- Once the response is committed or the session is invalidated, manual context saving may have no effect; test with real cookie/session integration tests.

### 6.2. When Is Context Bound and Cleared?

Conceptual lifecycle:

~~~text
Request A begins, thread T1
  -> SecurityContextHolderFilter supplies context
  -> BasicAuthenticationFilter authenticates
  -> AuthorizationFilter permits
  -> Controller sees authenticated principal
  -> response completes
  -> SecurityContextHolderFilter clears holder on T1

Request B begins, thread T2 (could reuse a pooled thread)
  -> New request lifecycle loads its own context
  -> If no saved session/credential, it may be anonymous
~~~

Servlet containers reuse worker threads. **Never store Authentication in a static field** and reuse it across requests. Never call `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` to "fix lost logins"—that leaks principals across different users.

### 6.3. Async, Executors, and Context Propagation

If a controller invokes `@Async`, `CompletableFuture`, spawns threads, or dispatches work to another worker, ThreadLocal context **is not copied across threads by default**. Use Spring Security-supported propagation tools such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, or appropriate executor/context-propagation integration. Carry identity intentionally across boundaries; for long-running jobs, re-check current policies instead of trusting stale security contexts indefinitely.

In async/error/forward dispatches, check `DispatcherType`, filter registration, lifecycle, and security handlers. Never assume `OncePerRequestFilter` runs once across every redispatch without checking: `shouldNotFilterAsyncDispatch`, `shouldNotFilterErrorDispatch`, and container dispatch semantics govern execution.

## 7. Reasoning from Status and Logs: A Safe Decision Tree

~~~text
START: Request returns 401/403/404/302 or null principal
 |
 +-- (A) Evidence request reached the right app/servlet?
 |      No -> proxy, port, DNS, ingress, servlet filter registration
 |      Yes
 |       |
 |       +-- (B) Which chain did FilterChainProxy select?
 |              None -> securityMatcher/fallback or filter bypass
 |              Chain matched
 |               |
 |               +-- (C) Unsafe method with CSRF active?
 |               |      Missing/bad token -> CsrfFilter -> 403
 |               |      Valid / not required
 |               |
 |               +-- (D) Is Authentication valid?
 |               |      Missing/bad credentials -> 401 or login redirect
 |               |      Valid (or anonymous on public route)
 |               |
 |               +-- (E) Which rule did AuthorizationFilter match?
 |               |      Wrong method/path/role -> 403 (or 401 for anon)
 |               |      Permit
 |               |
 |               +-- (F) Controller/service/method security?
 |               |      @PreAuthorize/ACL denies -> 403/404 policy
 |               |      No matching handler -> 404/405
 |               |
 |               +-- (G) Context on another thread / next request?
 |                      Missing -> repository/save/session/async propagation
 |
 END: Reproduced hypothesis and negative regression test.
~~~

**Never jump to conclusions from a single log line.** Seeing `FilterChainProxy: Securing GET /api/me` shows the request entered security processing; **it does not prove** Basic credentials were verified. Seeing `Authenticated user` shows an authentication step; **it does not prove** the request was ultimately authorized to read the object. A 403 after login could be role, CSRF, or ownership.

### 7.1. Why Does a Trace Sometimes Show Authentication "none" in an Early Filter?

A diagnostic filter placed before Basic auth normally logs `auth=none` at request entry because authentication **has not run yet**. After `chain.doFilter`, the same filter can observe the principal if downstream authentication succeeded. If `CsrfFilter` blocked the request before Basic auth ran, both phases may report `none`.

Therefore, logs need at least **phase=before/after** and filter position, never just a timeless "SecurityContext null".

### 7.2. Why See AnonymousAuthenticationToken and Still Get 401?

`AnonymousAuthenticationFilter` can supply an anonymous token to downstream filters. When a protected route requires `authenticated()`, the access decision still denies anonymous callers; the HTTP Basic entry point then sends 401. **An anonymous token does not equal a successful login.**

## 8. Enabling Selective Logging Without Leaking Secrets

In an **isolated test/staging** environment, enable logging on targeted packages. For example, in `application-debug.properties` or runtime args:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept.AuthorizationFilter=TRACE
logging.level.org.springframework.security.web.csrf.CsrfFilter=DEBUG
logging.level.example.tracelab=DEBUG
~~~

These are **diagnostic examples**—never leave broad TRACE logging enabled indefinitely in production. Exact logger names and verbosity can change across releases; if expected events do not appear, check the actual filter chain and active log levels instead of assuming a feature isn't running.

Whenever enabling `org.springframework.security=DEBUG/TRACE`:

- Scope time window, environment, traffic, or sampling; require review if logs could contain sensitive data.
- Configure redaction for Authorization, Cookie, Set-Cookie, CSRF tokens, passwords, query strings with reset/magic links, OIDC codes/states, and private paths.
- Never enable `spring.security.debug=true` in production unreviewed, as the debug filter can dump request headers and sensitive values.
- Ensure log storage enforces ACLs, retention, and auditing; never paste raw logs into public tickets or chats.
- Use **correlation IDs**, but never trust client-supplied IDs without validation/normalization to prevent log injection or header splitting.
- For distributed tracing across proxies/apps/IdPs, use standard trace context with clear trust boundaries; never equate a trace ID with an authenticated identity.

### 8.1. What Makes a "Sufficient Log Snippet"?

~~~text
trace=example-01 phase=before method=POST route=/api/notes
dispatcher=REQUEST authKind=none

trace=example-01 phase=after status=403 authKind=none

Security diagnostics: CSRF rejected request before Basic auth
~~~

This is a plausible **illustrative trace** for a tokenless POST in the demo configuration, **not verbatim required Spring Security log output**. Conclude "CSRF rejected" only after cross-checking `CsrfFilter` logs or comparing against an identical request carrying valid CSRF. Never log token values to prove an error.

For another authorization failure:

~~~text
trace=example-02 method=GET route=/api/admin/audit
authentication=verified role_group=EDITOR
url_authorization=denied
status=403
~~~

In production, review `role_group` against privacy/data-minimization policies; a decision code like `wrong_authority` is usually enough without logging full authority lists.

## 9. Main Lab: States to Reproduce

The sample app defines **two SecurityFilterChains** and six endpoints, with two demo accounts:

- `editor` with `ROLE_EDITOR`.
- `admin` with `ROLE_ADMIN`, **not automatically holding `ROLE_EDITOR`**.

| Method | URL | Chain | URL Rule | Extra Checks |
| --- | --- | --- | --- | --- |
| GET | `/api/public/ping` | API | `permitAll()` | None |
| GET | `/api/me` | API | `authenticated()` | None |
| POST | `/api/notes` | API | `hasRole("EDITOR")` | CsrfFilter |
| GET | `/api/admin/audit` | API | `hasRole("ADMIN")` | None |
| GET | `/api/reports/internal` | API | `authenticated()` | `@PreAuthorize("hasRole('ADMIN')")` on service |
| GET | `/healthcheck` | Fallback | `permitAll()` | None |
| Other URL/method | Any | API or fallback | `denyAll()` | Method/CSRF-dependent |

Purpose of making `/api/reports/internal` differ from `/api/admin/audit`:

- At `/api/admin/audit`, `ROLE_EDITOR` is denied at **URL authorization**.
- At `/api/reports/internal`, `ROLE_EDITOR` **passes the URL `authenticated()` rule**, enters MVC, and is denied when invoking the Spring-managed service guarded by **method security**. Both return 403, so status alone cannot tell which layer rejected the request.

Expected matrix when POST includes **valid CSRF**:

| Scenario | Anonymous | EDITOR | ADMIN |
| --- | ---: | ---: | ---: |
| GET `/api/public/ping` | 200 | 200 | 200 |
| GET `/api/me` | 401 | 200 | 200 |
| POST `/api/notes` + CSRF | 401 | 201 | 403 |
| GET `/api/admin/audit` | 401 | 403 | 200 |
| GET `/api/reports/internal` | 401 | 403 | 200 |
| GET `/healthcheck` | 200 | 200 | 200 |
| GET `/api/unlisted` | 401 | 403 | 403 |
| GET `/outside` | 401 | 403 | 403 |

**Valid CSRF must be supplied on POST before interpreting role results.** Without CSRF, editor also receives 403, but from `CsrfFilter` rather than `AuthorizationFilter`.

## 10. Runnable Project: Java 17, Spring Boot 3.3.5, Spring Security 6

### 10.1. Project Structure

~~~text
security-trace-lab/
├── pom.xml
├── src/main/java/example/tracelab/TraceLabApplication.java
└── src/test/java/example/tracelab/TraceLabTests.java
~~~

No external LDAP, IdP, database, email, or containers needed. HTTP Basic intentionally uses `{noop}` for learning how authentication traces look. **Never** ship this in production release artifacts.

### 10.2. Maven Dependencies

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>security-trace-lab</artifactId>
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
~~~

`spring-security-test` provides MockMvc post-processors such as `httpBasic()` and `csrf()`. `spring-boot-starter-security` provides the filters, configurers, and `@EnableMethodSecurity` for method security. Do not manually pin individual Spring Security modules when the Spring Boot BOM manages baseline-compatible versions.

### 10.3. Complete Java File: Two Chains, Trace Filter, and Method Security

**src/main/java/example/tracelab/TraceLabApplication.java:**

~~~java
package example.tracelab;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
@EnableMethodSecurity
public class TraceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TraceLabApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // For lab only; never use {noop} in production.
        return new InMemoryUserDetailsManager(
                User.withUsername("editor")
                        .password("{noop}demo-pass")
                        .roles("EDITOR")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}demo-pass")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("EDITOR")
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin/audit")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports/internal")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                // Filter before CsrfFilter: also observes CSRF-blocked requests.
                .addFilterBefore(
                        new DiagnosticTraceFilter(), CsrfFilter.class)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                // No securityMatcher: fallback for URLs outside /api/**.
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/healthcheck")
                            .permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        new DiagnosticTraceFilter(), CsrfFilter.class)
                .build();
    }

    @Bean
    ReportService reportService() {
        return new ReportService();
    }

    public static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public String loadInternalReport() {
            return "restricted";
        }
    }

    @RestController
    static class ApiController {

        private final ReportService reports;

        ApiController(ReportService reports) {
            this.reports = reports;
        }

        @GetMapping("/api/public/ping")
        Map<String, String> publicPing() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication auth) {
            return Map.of("username", auth.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            // No DB write: learning endpoint for role + CSRF.
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/api/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "admin-only");
        }

        @GetMapping("/api/reports/internal")
        Map<String, String> report() {
            return Map.of("report", reports.loadInternalReport());
        }

        @GetMapping("/healthcheck")
        Map<String, String> health() {
            return Map.of("status", "up");
        }
    }

    static final class DiagnosticTraceFilter
            extends OncePerRequestFilter {

        private static final Logger log =
                LoggerFactory.getLogger(DiagnosticTraceFilter.class);

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            // Server-generated random ID; never use untrusted headers.
            String trace = UUID.randomUUID().toString();
            response.setHeader("X-Demo-Trace", trace);

            log.debug(
                    "trace={} phase=before method={} path={} " +
                    "dispatch={} authKind={}",
                    trace, request.getMethod(), request.getServletPath(),
                    request.getDispatcherType(), authKind());

            try {
                chain.doFilter(request, response);
            } finally {
                log.debug(
                        "trace={} phase=after status={} authKind={}",
                        trace, response.getStatus(), authKind());
            }
        }

        private static String authKind() {
            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
            return auth == null
                    ? "none"
                    : auth.getClass().getSimpleName();
        }
    }
}
~~~

**Why instantiate `DiagnosticTraceFilter` directly inside the chain without `@Component`?** Declaring a `Filter` as a Spring bean while also adding it to `SecurityFilterChain` causes Spring Boot to auto-register it as a **Servlet container filter** as well as inside the Security chain, running and logging twice in an unexpected order. In the demo, each chain instantiates its filter solely for the **Security chain**.

This filter logs **Authentication class name**, not username, tokens, passwords, request bodies, or full authorities. It logs `servletPath` for learning: in production, if paths carry PII or secret IDs, normalize to a **route template** or omit that field. Enable DEBUG only in lab scope; never collect verbose logs unbounded in production.

**`addFilterBefore(..., CsrfFilter.class)` placement matters:** when POST lacks CSRF, the trace filter still logs before/after because it sits **before** `CsrfFilter`. If placed after `CsrfFilter`, CSRF-rejected requests never reach the trace filter, creating the illusion that requests didn't reach the app. Conversely, if a request is handled **before the custom filter's position** (e.g., by an earlier filter), the trace will still not appear.

Note: importing `DispatcherType` here illustrates Servlet dispatch semantics in the explanation; the filter needs no `DispatcherType` branch because the log calls `request.getDispatcherType()`. Unused imports are valid in Java, though IDEs/linters may flag them; remove the import if clean lint is desired.

### 10.4. What Each of the Two Chains Means During Debugging

- `GET /api/me` → Chain #1 via `/api/**`; checks Basic, then `authenticated()`.
- `POST /api/notes` → Chain #1; `CsrfFilter` can reject before Basic auth runs.
- `GET /api/reports/internal` as EDITOR → URL `authenticated()` permits it; then `ReportService.loadInternalReport()` is rejected by `@PreAuthorize`.
- `GET /healthcheck` → Chain #2, anonymous allowed.
- `GET /outside` → Chain #2, hits deny-all. Anonymous typically gets 401 via Basic entry point; authenticated users lacking permission get 403.
- With method security enabled, Spring manages the `ReportService` bean and wraps it in an AOP proxy. Calling `new ReportService()` directly or via same-bean self-invocation bypasses the interceptor and skips `@PreAuthorize`; tests must invoke the Spring-managed bean.

## 11. MockMvc Test Suite: Proving Root Causes Instead of Guessing

**src/test/java/example/tracelab/TraceLabTests.java:**

~~~java
package example.tracelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TraceLabTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiPathIsAvailableToAnonymous() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void fallbackHealthPathIsAvailableToAnonymous() throws Exception {
        mvc.perform(get("/healthcheck"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("up"))
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void anonymousProtectedPathUsesBasicEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validAndInvalidBasicCredentialsBehaveDifferently()
            throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("editor"));

        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void editorCannotCallAdminUrl() throws Exception {
        mvc.perform(get("/api/admin/audit")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminUrl() throws Exception {
        mvc.perform(get("/api/admin/audit")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("admin-only"));
    }

    @Test
    void editorIsDeniedByMethodSecurityAfterUrlPermits()
            throws Exception {
        mvc.perform(get("/api/reports/internal")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/internal")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.report").value("restricted"));
    }

    @Test
    void editorCanCreateNoteWithValidCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("note-1"));
    }

    @Test
    void missingCsrfStopsRequestBeforeBasicAuthentication()
            throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden())
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void invalidCsrfAlsoReturnsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass"))
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillDoesNotGrantMissingRole()
            throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("admin", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiUnknownRouteIsDeniedBeforeMvc404()
            throws Exception {
        mvc.perform(get("/api/unlisted")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void fallbackUnknownRouteIsAlsoDenied()
            throws Exception {
        mvc.perform(get("/outside")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void distinctRequestsDoNotAutomaticallyShareBasicIdentity()
            throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isOk());

        // New request without login header/cookie:
        // must not inherit principal from the previous request.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
mvn -B -ntp clean verify
~~~

**What the tests are expected to verify:** public routes in both chains, 401 on missing/invalid Basic credentials, 403 from URL role, 403 from method security, 403 from CSRF, 201 for valid editor + CSRF, fallback deny-all, and no unintended leakage of Basic identity across requests.

Examining easily misinterpreted tests:

1. **`missingCsrfStopsRequestBeforeBasicAuthentication`** asserts only status/header. Attributing the cause to CSRF comes from the `CsrfFilter` configuration and contrasting it with the identical POST carrying `.with(csrf())`, never from 403 alone.
2. **`editorIsDeniedByMethodSecurityAfterUrlPermits`** is meaningful because the URL rule is `authenticated()` while the service has `@PreAuthorize("hasRole('ADMIN')")`; the hypothesis comes from the code path. If the URL rule were changed to admin-only, the 403 test would still pass even though **the root cause changed**. To pin down the exact layer in large projects, add direct unit/integration tests on the service proxy and inspect trace events.
3. **`distinctRequestsDoNotAutomaticallyShareBasicIdentity`** issues two separate MockMvc requests without sharing login cookies or sessions. It does not test every `SecurityContextRepository`; with form login/sessions, test login and cookie persistence explicitly.
4. **`apiUnknownRouteIsDeniedBeforeMvc404`** shows the Security `denyAll()` rule executes before MVC handler lookup, so 403 is expected for authenticated users; this status does not prove a controller exists.
5. **`X-Demo-Trace`** is a custom header emitted by the diagnostic filter, not a standard Spring Security header. It correlates lab logs, but should never be treated as authentication proof or leak personal data.

**The code was statically reviewed and has not been compiled/executed in this article.** To confirm tests pass, run `mvn test` or `mvn verify` in a project with the exact files and dependencies shown. Servlet/matcher parameters may vary in real apps; never copy expected statuses directly to form login/OIDC/Bearer without verifying entry points.

## 12. How to Reproduce and Read Logs Safely

Run the demo with Maven:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments=--logging.level.example.tracelab=DEBUG
~~~

This command targets Bash/Git Bash with the Maven plugin and one application argument; other shells may require quoting arguments containing dots or equals signs. Enable the loggers from Section 8 in test environments if Spring Security internals are needed.

Try GET requests from another terminal:

~~~bash
# Public route, chain #1.
curl -i http://localhost:8080/api/public/ping

# Protected route without Basic credentials -> 401.
curl -i http://localhost:8080/api/me

# Valid Basic -> 200.
curl -i -u editor:demo-pass http://localhost:8080/api/me

# URL-level denial -> 403.
curl -i -u editor:demo-pass \
  http://localhost:8080/api/admin/audit

# Method-level denial -> 403 (URL authenticated still passes).
curl -i -u editor:demo-pass \
  http://localhost:8080/api/reports/internal

# Fallback chain -> 200 for healthcheck.
curl -i http://localhost:8080/healthcheck

# Fallback deny-all -> 403 once authenticated.
curl -i -u editor:demo-pass http://localhost:8080/outside

# Missing CSRF -> 403; do not use this test to measure EDITOR permissions.
curl -i -u editor:demo-pass -X POST \
  http://localhost:8080/api/notes
~~~

The lab uses **demo passwords**: HTTP Basic over `http://localhost` is unsuitable for production because credentials can be exposed on the network. Real deployments require HTTPS and proper secret/password handling.

### 12.1. Illustrative Log Sequence and How to Read It

With the diagnostic filter placed before CsrfFilter, a tokenless POST can produce a trace structured like:

~~~text
trace=2f1a... phase=before method=POST path=/api/notes
dispatch=REQUEST authKind=none

trace=2f1a... phase=after status=403 authKind=none
~~~

**The ID here is shortened for presentation**, not a real UUID from a run. The before/after events share an ID, showing the request reached the diagnostic filter and ended with 403, yet they **do not** prove by themselves which filter generated the 403. Compare against controlled variants:

- POST with valid CSRF + editor returns **201**.
- POST without CSRF + editor returns **403**.
- POST with valid CSRF + admin returns **403** due to missing ROLE_EDITOR.

Combining those experiments with `CsrfFilter` debug events cleanly separates CSRF denials from role denials. Never log real token values.

### 12.2. AuthKind in Logs Is Not the Source of Truth for Authorization

An `authKind=UsernamePasswordAuthenticationToken` can be either unauthenticated or authenticated depending on constructor/provider; the demo log records only the class name for **data minimization**. For certainty, inspect `isAuthenticated`, trust resolvers, authorities, and AuthorizationManager decisions **inside a safe test**, rather than dumping everything into production logs.

If the custom filter sits **before** `BasicAuthenticationFilter`, `phase=before authKind=none` is normal. Seeing `none` at `phase=after` when CSRF returns 403 is also expected because Basic auth never ran. Never claim `SecurityContextHolder` "was lost" based solely on those two lines.

### 12.3. Reading FilterChainProxy Logs Systematically

With the right loggers enabled, first look for "Securing ..." and filter chain processing. If a request does not appear in logs:

- Verify it reached the right application/port/instance.
- Check servlet filter registration, `spring.security.filter.dispatcher-types`, and proxy-rewritten paths.
- Check whether a static resource handler or CDN served it before reaching the app.
- Check path/chain matching; missing logs may simply mean the logger wasn't enabled or sampled—**never** assume the chain was bypassed.

Do not turn on TRACE on every package and dump raw credential-bearing logs into an issue tracker. Start with a trace ID, a minimal test request, and targeted loggers.

## 13. Six Sample Investigations from Request Traces

### Case A — "POST by EDITOR with the Right Role Still Returns 403"

**Trace:** `method=POST`, `path=/api/notes`, Basic header sent, status 403, log `phase=before authKind=none`.

**Hypothesis:** CSRF is invalid/missing, so Basic auth may not have run. **Experiment:** replay the request in MockMvc first with `.with(httpBasic(...))`, then add `.with(csrf())`. If the second returns 201, inspect the client's CSRF token repository, form/header wiring, and session cookie.

**Do not fix by:** calling `csrf.disable()` across the chain, adding `permitAll("/api/notes")`, or granting ADMIN to the user.

### Case B — "Authenticated GET Still Returns 401"

**Trace:** `GET /api/me`, no principal seen in handler, returns 401 with `WWW-Authenticate`.

**Hypothesis:** missing Basic header, wrong password, proxy stripped the header, app routed to a different chain, or `BasicAuthenticationFilter` was not enabled on the selected chain. **Experiment:** run a valid/wrong credential pair on the exact same route, verify Chain #1 selection, and inspect the provider and entry point.

**Do not fix by:** removing `authenticated()`; inspect the **authentication mechanism** first. If browsers use form login/OIDC, expectations differ from HTTP Basic.

### Case C — "Editor Accesses /api/me Yet Admin Route Returns 403"

**Trace:** same valid credentials, `/api/me` = 200, `/api/admin/audit` = 403.

**Hypothesis:** authentication succeeded, authority does not match `ROLE_ADMIN`. **Experiment:** inspect `UserDetailsService`/mapping and the rule. Remember `hasRole("ADMIN")` checks for `ROLE_ADMIN` with the default prefix; `hasAuthority("ADMIN")` means something different.

**Do not fix by:** granting `ROLE_ADMIN` to all users just to pass tests. Returning 403 may be the exact intended behavior.

### Case D — "URL Check Lets Request Through, Yet Service Throws AccessDeniedException"

**Trace:** `GET /api/reports/internal` as editor, authenticated, URL rule is `authenticated()`, controller invokes `ReportService` with `@PreAuthorize("hasRole('ADMIN')")`.

**Hypothesis:** **method security** denied the call after URL authorization. **Experiment:** test the Spring-managed `ReportService` directly as editor and admin; inspect `@EnableMethodSecurity`, proxy usage, self-invocation, and SpEL. A lone 403 response cannot prove whether URL or method security blocked it; correlate code, logs, and tests.

**Do not fix by:** removing `@PreAuthorize` without checking business policy. URL-level authentication only identifies the user; it does not grant admin privileges.

### Case E — "A New URL Bypasses the Security Chain"

**Trace:** `/api/**` is protected, while `/preview/**` or another servlet never appears in API chain logs and returns data.

**Hypothesis:** `securityMatcher("/api/**")` excludes the new URL and there is no fallback chain; requests may bypass Spring Security. **Experiment:** add anonymous and wrong-role tests on that URL, and inspect total chains, chain order, and filter registration.

**Do not fix by:** placing `anyRequest().denyAll()` **inside the /api chain** and assuming it covers paths outside /api. You need a dedicated/catch-all fallback chain or explicit policy for that route.

### Case F — "Request A Logged In, Request B Is Anonymous Again"

**Trace:** A has authentication, B on another thread sees no context, or the session cookie is missing.

**Hypothesis:** cookies/credentials not sent, `STATELESS`/non-persisting repository, manual auth skipped saving, session invalidated, or async threads didn't propagate context. **Experiment:** inspect cookie jar, `SecurityContextRepository`, session policy, logout, and per-request trace IDs; test login → request with cookie → request without cookie.

**Do not fix by:** storing Authentication in a static field or enabling `MODE_GLOBAL`. That mixes identities across different users.

## 14. Cases That Commonly Lead to Wrong Conclusions

### 14.1. "A 403 Response Means AuthorizationFilter Ran"

False. `CsrfFilter` can halt the request **before** authentication/authorization; `@PreAuthorize` or controller advice can also emit 403. Isolate the cause using controlled test variables.

### 14.2. "`SecurityContextHolder.getContext()` Is Non-Null So the User Is Logged In"

False. The holder normally provides a context object even when `getAuthentication()` is null; an anonymous token can have `isAuthenticated() == true` without being a logged-in user. Use Spring Security's supported predicates instead of inferring from object presence.

### 14.3. "No Filter Log Means the Request Bypassed the Filter Chain"

Not necessarily. The filter may sit behind an earlier filter that blocked the request, the logger may not be enabled, the request may arrive under another dispatcher type, or a custom `OncePerRequestFilter` may skip async/error dispatches. Enable chain-selection logging and place probes properly.

### 14.4. "`permitAll()` Means All Security Filters Are Skipped"

False. `permitAll()` typically allows requests *after* traversing the `SecurityFilterChain`. `web.ignoring()` or excluded filter registrations bypass the security chain; hence for normal public assets, `permitAll` is often preferred to retain security headers.

### 14.5. "Same Path Means Same Request"

False. Method, context path, servlet path, forwarded URI, URL decoding, query strings, cookies, `Origin`, CSRF headers, `DispatcherType`, and chain selection can all differ. Record full redacted metadata.

### 14.6. "`@WithMockUser` Verifies the Login Provider"

False. `@WithMockUser` or `with(user(...))` injects a mock Authentication, suitable for authorization tests. To test Basic credentials, use `with(httpBasic(...))`; to test OIDC/JWT/LDAP, run integration tests exercising the real protocol/decoder/provider rather than mocking the principal.

### 14.7. "Testing `forwardedUrl` Proves the Container Re-Runs SecurityFilterChain"

No. `MockMvc.forwardedUrl(...)` may only verify MVC's forward decision. If authorization depends on FORWARD redispatches or filter registration, run an embedded servlet container integration test over real HTTP. Protect both source/target URLs and enforce method/service policies for sensitive data.

### 14.8. "A Passing Status Test Means Zero Data Leaks"

False. A 200 on `/api/files/123` only proves the request succeeded; it could return someone else's document. Verify object owner/tenant ACLs, response bodies, cache headers, CORS, and all download/preview paths.

## 15. Advanced Investigation Techniques

### 15.1. SecurityContextRepository and Manual Authentication

When a custom filter authenticates manually and sets:

~~~java
SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

This is only a **custom authentication snippet** and does not persist the context to future requests. If the app needs a login session, check repository/explicit-save semantics and the corresponding session strategy:

~~~java
// Conceptual snippet (requires repository, request, response,
// and matching session/security configuration):
securityContextRepository.saveContext(
        context, request, response);
~~~

Never copy this into every custom filter without evaluating session fixation, concurrency, and response commit timing. For stateless bearer-token APIs, **intentionally not retaining a session** can be the right policy.

### 15.2. Multi-Chain + Separate AuthenticationProviders

An app may have a JWT chain for `/api/**` and a form-login chain for browsers. When a request lands in the wrong chain, the filter for its credential type may **not exist** there; an API receiving a Bearer token can return 401 as unauthenticated even with a valid token if the JWT resource-server configurer is enabled only on another chain.

Check thoroughly:

- `@Order` and `securityMatcher` of **every chain**.
- That the expected authentication filter is enabled inside the right chain.
- Provider/decoder, token format, issuer/audience, and principal/authority conversion.
- Per-chain entry points and access-denied handlers.
- Browser CSRF vs. bearer-only API CSRF policy per threat model.
- Which chain handles `/login`, OAuth callbacks, error, actuator, and static resources.

In the lab example, both chains enable HTTP Basic to minimize variables; production setups may differ.

### 15.3. Distributed Tracing and Log Correlation

A request may flow `gateway → BFF → service`. Each hop maintains its own SecurityContext; authentication at the BFF does not automatically prove a downstream service received verified user identity. Never forward client-supplied principal/role headers unless an authenticated trust mechanism and verification exist between services.

Use OpenTelemetry/Micrometer tracing to attach trace/span IDs, remembering **a trace ID is an observability tool, not proof of identity**. In distributed systems, distinguish `401 from gateway`, `403 from downstream service`, and `403 from CSRF at BFF`, logging which hop emitted the status and its context.

### 15.4. Verifying Custom Filter Ordering

A custom token filter needs consistent placement relative to authentication/context filters. Placing a filter **before `SecurityContextHolderFilter`** and setting the context can get overwritten or fail to persist as expected. Placing a diagnostic filter too late misses requests stopped by CSRF or authentication filters.

Use `addFilterBefore`/`addFilterAfter` with clear anchor classes, yet still verify **actual runtime filter order** and multi-chain routing rather than guessing from `.addFilterBefore()` order in source code.

### 15.5. AuthenticationTrustResolver and Anonymous Tokens

When business logic checks "is the user logged in?", do not rely solely on `isAuthenticated()` on the token. Spring Security provides `AuthenticationTrustResolver` and authorization expressions to distinguish anonymous, remember-me, and fully authenticated users. An anonymous request on a public endpoint may hold an Authentication object, yet must never be granted access to private documents.

## 16. Organizing Tests and Observability When Fixing Bugs

A "trace-to-regression-test" workflow:

1. **Minimal reproduction** with exact method, path, and credential presence; generate a server-side trace ID.
2. **Capture baseline:** status, response headers, selected chain, filter phase, authentication kind, and expected policy.
3. **Form a single hypothesis** about filter, chain matcher, CSRF, entry point, role, method security, or context lifecycle.
4. **Vary one variable at a time:** with/without CSRF, valid/wrong password, admin/editor, `/api`/fallback, fresh request with/without cookies.
5. **Write both negative and positive tests** for the same policy: right user passes, wrong user is denied. Never test only failure statuses.
6. **Test the service/proxy separately** if suspecting method security, and test controller/HTTP chains if suspecting URL auth.
7. **Apply the narrowest fix:** never disable CSRF, drop auth, or make URLs public just to clear an error.
8. **Run the full regression suite:** login, logout, sessions, CSRF, roles, CORS, error/forward dispatches, object ACLs, and response payloads where relevant.
9. **Verify in staging behind a real proxy** to catch header/cookie/servlet-mapping differences from MockMvc.
10. **Clean up debug logging** once resolved; archive a redacted report linking tests and artifact versions.

### 16.1. Example Verifiable Investigation Report

~~~text
Title: POST /api/notes rejects EDITOR with 403
Environment: staging, artifact <approved-release-id>
Observed: POST /api/notes, Basic credential supplied, CSRF absent
Selected chain: API chain (securityMatcher /api/**)
Evidence: trace before/after; CsrfFilter rejection in isolated test
Controlled test A: EDITOR + no CSRF -> 403
Controlled test B: EDITOR + valid CSRF -> 201
Controlled test C: ADMIN + valid CSRF -> 403
Cause: request lacked CSRF token; not a missing ROLE_EDITOR
Fix: frontend obtains/submits the configured CSRF token with session
Regression: MockMvc tests for valid/missing/invalid CSRF, wrong role
Sensitive data: omitted from ticket/log
~~~

This is a **hypothetical conclusion template**; replace it with real data after investigating. Specifically, never paste raw HTTP Authorization headers or CSRF tokens into tickets as "proof".

### 16.2. When Are Integration Tests Beyond MockMvc Needed?

- Filter registration across `DispatcherType.FORWARD`, `ASYNC`, `ERROR`, or different embedded containers.
- Session cookie / SameSite / Secure attributes behind HTTPS ingress/reverse proxies.
- OAuth2 Login redirects/callbacks, OIDC state/nonce, real JWT decoders/JWKS, or LDAP binds.
- Multiple servlet paths, gateway rewrites, and forwarded-header trust boundaries.
- Distributed session stores and security-context propagation across executors/threads.
- Caches/CDNs, file downloads, user ownership, and security headers behind proxies.

MockMvc excels at isolating Spring MVC/Security issues, but does not replace container, browser, and upstream/downstream integration behavior.

## 17. Self-Check Questions

**Q1.** Are `securityMatcher("/api/**")` and `requestMatchers("/api/**")` the same?  
**No.** The first selects which SecurityFilterChain runs; the second defines authorization rules inside a selected chain.

**Q2.** A POST request has ROLE_EDITOR yet returns 403. Should we immediately elevate the user's roles?  
**No.** Check CSRF first; replay the exact request with a valid CSRF token to distinguish CSRF from role failure.

**Q3.** Does a null `Authentication` in a filter before `BasicAuthenticationFilter` prove Basic auth is broken?  
**No.** Authentication simply hasn't executed at that point yet.

**Q4.** `AnonymousAuthenticationToken.isAuthenticated()` can return true. Does that equal a successful login?  
**No.** Spring Security uses trust resolvers and authorization semantics to distinguish anonymous users.

**Q5.** If a URL enters the API chain, does `anyRequest().denyAll()` in the fallback chain apply to it?  
**No.** Only the first selected chain applies.

**Q6.** Why can `GET /api/reports/internal` return 403 even when the URL rule is `authenticated()`?  
**Because** the downstream service enforces `@PreAuthorize("hasRole('ADMIN')")`.

**Q7.** Does a passing 200 `@WithMockUser` test prove Basic passwords or JWT signatures work?  
**No.** A mock identity bypasses the real authentication provider/decoder.

**Q8.** Does seeing `FilterChainProxy` log "Securing ..." mean `AuthorizationFilter` will permit the request?  
**No.** It only shows the request entered security processing, not the final authorization decision.

**Q9.** Why can an `@Async` thread fail to see SecurityContext?  
**Because** ThreadLocal context does not propagate automatically. Use proper propagation mechanisms or pass controlled identity/policy explicitly.

**Q10.** Does `denyAll()` on a chain matching `/api/**` protect `/preview/**`?  
**No.** Another chain or fallback is required to cover URLs outside that scope.

**Q11.** A POST without CSRF gets 403 while the same POST with CSRF gets 201. Can we draw a stronger conclusion?  
**Yes**, provided other variables stayed constant and filter logs/config confirm `CsrfFilter` policy ran. You still need to find why the client omitted or mismatched the token.

**Q12.** Does a Request ID prove the user is authenticated?  
**No.** It is strictly a correlation/logging tool.

## 18. Investigation Wrap-Up Checklist and Key Takeaways

- [ ] Verify **method, normalized internal path, context/servlet path, dispatcher, selected instance, and trace ID**.
- [ ] Identify the **selected SecurityFilterChain** (via `@Order` + `securityMatcher`) and verify a fallback protects out-of-scope URLs.
- [ ] Check request matcher ordering, HTTP methods, role/authority prefixes, and any owner/tenant rules on the URL.
- [ ] Distinguish **authentication failures (401/redirect)**, **authorization denials (403)**, **CSRF denials (403)**, and MVC 404/405.
- [ ] Trace `SecurityContextHolderFilter`, authentication filters, `AnonymousAuthenticationFilter`, `AuthorizationFilter`, and method-security proxies at the decision point.
- [ ] Never mistake a null principal **before authentication** or **after request completion** for lost context during the request.
- [ ] Verify `SecurityContextRepository`, session save semantics, and cookies whenever login must span multiple requests.
- [ ] Verify context propagation for `@Async`, executors, and message workers across thread hops.
- [ ] Place trace filters carefully, generate safe correlation IDs, never log credentials/tokens/PII, and disable TRACE when done.
- [ ] Write **positive + negative regression tests**: anonymous, wrong password, wrong role, CSRF, multi-chain, service `@PreAuthorize`, and fresh unauthenticated requests.
- [ ] When proxies/OIDC/LDAP/JWT are present, add integration tests in the real environment rather than relying solely on MockMvc.
- [ ] Modify configuration only after reproducing the hypothesis; never use `permitAll()`/`csrf.disable()` to mask root causes.

**Conclusion:** effective Spring Security Servlet debugging moves systematically from **request trace → chain selection → filter order → authentication/context → URL and method authorization → MVC/service outcome**. A single 401/403 status never tells the whole story. When each hypothesis is verified with controlled comparative requests and regression tests, you can fix bugs precisely without accidentally widening permissions or leaking identities across sessions.
