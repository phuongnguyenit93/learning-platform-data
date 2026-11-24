# Filter Ordering and the Relationship Between Context Loading, Authentication, CSRF, and Authorization

> Knowledge lesson in **Filter Architecture** for the Spring Security **Servlet stack**. Content follows Spring Security 6 / Spring Boot 3, Jakarta Servlet, and Java 17+ conventions. The exact filter list varies depending on login mechanisms, session configuration, OAuth2, and custom filters enabled.

## 1. Which layers does an HTTP request pass through?

On the Servlet stack, Spring Security participates in the Servlet container's filter chain via `DelegatingFilterProxy`, usually named `springSecurityFilterChain`. The proxy forwards processing to `FilterChainProxy`. This component finds the **first `SecurityFilterChain` matching the request**, then invokes the security filters in the selected chain in order.

```text
HTTP request
    |
    v
[Servlet container filter chain]
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
            |
            v
        FilterChainProxy
            |
            +-- select the first SecurityFilterChain matching URL/request
            |
            +-- SecurityContextHolderFilter (provides SecurityContext)
            +-- ... infrastructure/CORS filters if configured ...
            +-- CsrfFilter
            +-- LogoutFilter
            +-- ... enabled authentication filters ...
            +-- AnonymousAuthenticationFilter
            +-- ExceptionTranslationFilter
            +-- AuthorizationFilter
            |
            v
        Spring MVC / Servlet / Controller
```

The diagram shows the **relative order of key stages**, not an immutable default list. Some filters may be absent, such as `UsernamePasswordAuthenticationFilter` when form login is not enabled or `BearerTokenAuthenticationFilter` when OAuth2 Resource Server is not configured.

Three types of ordering must be distinguished:

1. **Servlet container order:** the position of `DelegatingFilterProxy` relative to other Servlet filters.
2. **Security filter order:** the position of filters inside a `SecurityFilterChain`; adjusted using `addFilterBefore`, `addFilterAfter`, or corresponding configuration mechanisms.
3. **Authorization rule order:** the order of `requestMatchers(...)` inside `authorizeHttpRequests(...)`; the first matching rule decides the access policy.

`@Order` across multiple `SecurityFilterChain`s determines **which chain is evaluated first**, not the position of each filter inside a chain. `securityMatcher(...)` restricts the chain's scope, unlike `requestMatchers(...)` used for authorization rules inside a chain.

## 2. Roles and ordering of core filters

| Stage | Representative filter | Does | Does not do |
| --- | --- | --- | --- |
| Context loading/preparation | `SecurityContextHolderFilter` | Supplies `SecurityContext` for the current execution, typically fetching via `SecurityContextRepository` when needed. | Does not re-verify username/password by default or always save context at the end of the request. |
| Request forgery protection | `CsrfFilter` | Checks the CSRF token for protected HTTP methods, before many authentication filters. | Does not evaluate `ROLE_ADMIN` permission or read login passwords. |
| Logout | `LogoutFilter` | Processes matching logout requests and may terminate the response. | Does not mean every GET to the logout URL will actually log out. |
| Authentication | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`… | Processes matching credentials/tokens, creates `Authentication`, and updates context when authentication succeeds. | Does not guarantee every request carries credentials or every chain contains all of these filters. |
| Default identity | `AnonymousAuthenticationFilter` | Sets anonymous authentication when no appropriate principal is present yet. | Does not turn an anonymous user into an authenticated user. |
| Security error handling near end of chain | `ExceptionTranslationFilter` | Translates authentication/authorization exceptions from **downstream** filters into entry point or access denied handling. | Does not authenticate itself, and does not cover filters positioned before it. |
| Access decision | `AuthorizationFilter` | Checks `AuthorizationManager` according to configured rules, typically the final gate before the endpoint. | Does not check CSRF or verify passwords itself. |

The most critical relative ordering:

```text
LOAD CONTEXT
     v
CSRF CHECK      ---- missing/invalid token ----> 403 (early stop)
     v
AUTHENTICATE if matching credentials are present
     v
ANONYMOUS if no identity yet
     v
EXCEPTION TRANSLATION (wraps downstream processing)
     v
AUTHORIZATION -- insufficient rights ----> 401/302/403 depending on state
     v
ENDPOINT
```

For example, `POST /login` missing a CSRF token can be rejected **before** `UsernamePasswordAuthenticationFilter`; meanwhile `GET /admin` by an authenticated user may pass the initial steps yet be blocked by `AuthorizationFilter`.

## 3. Loading SecurityContext and the Authentication lifecycle

### 3.1. SecurityContext, Authentication, and SecurityContextHolder

`SecurityContext` holds an `Authentication`, representing the principal and authorities used by security components during the current request. It can be read in code executing after the relevant filters:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

The snippet requires importing `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder` in a Spring Security application. **Having an `Authentication` object does not necessarily mean a real login:** `AnonymousAuthenticationFilter` may have placed an `AnonymousAuthenticationToken` into the holder. Therefore, avoid using `authentication != null` as a substitute for the `authenticated()` rule.

By default, `SecurityContextHolder` binds context to the **current thread**. It is not automatically a long-lived login store; creating a new thread/executor manually does not mean the previous request's context is forwarded. With MVC async, appropriate context propagation mechanisms must be used.

### 3.2. Who loads and who saves the context?

`SecurityContextRepository` is responsible for loading/saving context according to the configured mechanism: for example, backed by HTTP session or request attributes. Spring Security 6's `SecurityContextHolderFilter` can prepare a **deferred context** and only retrieve it when actually needed, so you must not assume every request reads the session immediately.

Typical session-backed flow:

```text
Login request:
  UsernamePasswordAuthenticationFilter
    -> authentication succeeds
    -> puts Authentication into SecurityContext
    -> authentication mechanism saves SecurityContext via SecurityContextRepository
    -> client may receive a session cookie

Subsequent request:
  Browser sends session cookie
    -> SecurityContextHolderFilter provides the saved context
    -> AuthorizationFilter reads current Authentication and authorities
    -> permits or denies access
```

In Spring Security 6, the `SecurityContextHolderFilter` model generally requires **explicit saving of context changes**. In a custom authentication filter, merely doing:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

is **not sufficient** to ensure the next request remains logged in. When state must persist, integrate `SecurityContextRepository.saveContext(...)` properly; standard authentication filters handle saving accordingly. Legacy codebases using `SecurityContextPersistenceFilter` have different saving and lifecycle behavior; do not apply rules of one filter to the other.

### 3.3. Stateless still needs SecurityContext

In a stateless Bearer API, requests typically carry their own token; no session is needed to retain login across requests. However, the Bearer filter still validates the token and places `Authentication` in `SecurityContextHolder` for the **current request**, so authorization knows who sent the request.

```text
GET /api/items + Authorization: Bearer <token>
   |
   +-- Initial SecurityContext has no principal yet
   +-- BearerTokenAuthenticationFilter validates token
   +-- Authentication is set for this request
   +-- AuthorizationFilter checks authority/policy
```

Stateless **does not mean** turning off the Spring Security context or skipping authorization.

## 4. Authentication: when are credentials checked?

**Authentication** answers "who sent the request and what proof verifies it?". Depending on configuration:

- `UsernamePasswordAuthenticationFilter` typically handles POST to the login processing URL when `formLogin` is enabled.
- `BasicAuthenticationFilter` decodes and verifies HTTP Basic credentials.
- `BearerTokenAuthenticationFilter` processes Bearer tokens for OAuth2 Resource Server.
- Other filters may handle remember-me, pre-authentication, or custom login mechanisms.

When a request matches, the authentication filter can create an `Authentication` by calling `AuthenticationManager`/`AuthenticationProvider`, put the result into context, and save the context if the mechanism requires it. On failure, an authentication filter may invoke its failure handler/entry point itself and **not call further** downstream filters. With successful form login, the success handler usually redirects; not every login POST reaches an application controller.

A request already holding an `Authentication` from a session may **not need password re-verification** on every turn. Conversely, a stateless Bearer API can validate the token on every request.

**Authentication differs from authorization:** a user logged in with `ROLE_USER` can still be denied at `/admin/**` if the rule requires `ROLE_ADMIN`. An anonymous principal can still enter a public endpoint with `permitAll()`.

## 5. CSRF comes before authentication/authorization and operates independently

CSRF (Cross-Site Request Forgery) is a scenario where another website tries to trigger a request on a user's behalf when the browser **automatically sends credentials** such as session cookies. `CsrfFilter` requires a valid token for state-changing requests. By default, `GET`, `HEAD`, `OPTIONS`, and `TRACE` are treated as safe methods; `POST`, `PUT`, `PATCH`, and `DELETE` normally require a token.

**Especially important:** `permitAll()` only affects **authorization rules**. It does not disable `CsrfFilter`.

| Request | URL policy | CSRF | Typical result |
| --- | --- | --- | --- |
| `GET /demo/public`, anonymous | `permitAll()` | No token required for default safe method | 200 if handler runs cleanly. |
| `POST /demo/public`, anonymous, missing token | `permitAll()` | Fails at `CsrfFilter` | 403 **before authorization**. |
| `POST /demo/public`, anonymous, valid token | `permitAll()` | Passes CSRF | Can reach handler. |
| `GET /demo/private`, anonymous | `authenticated()` | No token required | Login redirect or 401 depending on mechanism. |
| `GET /demo/private`, logged-in user | `authenticated()` | No token required | Can reach handler. |
| `POST /demo/private`, logged-in user, missing token | `authenticated()` | Fails at `CsrfFilter` | 403 even though user is logged in. |
| `POST /demo/private`, logged-in user, valid token | `authenticated()` | Passes CSRF | Reaches authorization and then handler if permitted. |

### 5.1. Why does login also need CSRF?

A malicious website could try to force a browser to log into an account controlled by someone else (login CSRF). Because `CsrfFilter` sits before `UsernamePasswordAuthenticationFilter`, a login POST request missing or having an invalid token can be blocked **before the password is checked**. Logout also changes state; by default with CSRF enabled, POST logout requires a valid token.

### 5.2. How is the token sent?

HTML forms normally include a hidden `_csrf` input, while AJAX/SPA clients can send a header as configured. `CsrfTokenRepository` determines where the token is stored; `CsrfTokenRequestHandler` determines how the request supplies the token. In Spring Security 6, deferred tokens and token masking (related to BREACH) can affect how an SPA reads the token from a cookie and sends it via a header; client and server must be configured compatibly, never assuming a cookie token always works verbatim across every setup.

### 5.3. Should CSRF be disabled for APIs?

Consider this only after properly assessing the threat model. An API using only Bearer tokens that the client **explicitly** places in the `Authorization` header, without cookies or browser-auto-sent credentials, may need a different CSRF policy. However, a JSON API using session cookies still generally needs CSRF protection. HTTP Basic in browsers must also be evaluated because browsers may resend cached credentials automatically. Simply calling an API "REST" or "stateless" is not enough to skip CSRF checks.

## 6. Authorization and the role of ExceptionTranslationFilter

`AuthorizationFilter` is normally near the end of the default security chain. It enforces the rules in `authorizeHttpRequests(...)`, based on the current Authentication and request:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

This is a DSL **placed inside `HttpSecurity` configuration**, not a full Java class. `hasRole("ADMIN")` typically expects the `ROLE_ADMIN` authority with the default role prefix. Matcher order must go from specific to general to prevent overly broad rules from matching first.

When AuthorizationFilter throws `AccessDeniedException`, the preceding `ExceptionTranslationFilter` can:

- Trigger `AuthenticationEntryPoint` (login redirect or 401) when the sender is deemed unauthenticated.
- Invoke `AccessDeniedHandler` (typically 403) when already authenticated but lacking permissions.

`ExceptionTranslationFilter` **does not perform** password authentication and **only wraps** filters downstream of it. `CsrfFilter` sits before it and has its own `AccessDeniedHandler` path. Therefore, a 403 from CSRF does not prove the request reached `AuthorizationFilter`. Authentication filters also have their own failure handlers and can stop requests earlier.

Beyond URL authorization, code may use method security such as `@PreAuthorize`; passing `AuthorizationFilter` at the URL level does not automatically permit every downstream method execution.

## 7. Scenario comparison by execution order

**Scenario A: Public GET.** `GET /demo/public` needs no CSRF token; even without login it can reach the controller because of the `permitAll()` rule. `AnonymousAuthenticationFilter` may set an anonymous principal before authorization.

**Scenario B: Public POST missing CSRF.** `POST /demo/public` missing a token: `CsrfFilter` blocks it before authorization. Changing `permitAll()` to another rule will not make a missing token valid.

**Scenario C: Login POST.** With form login, CSRF must pass first. Then `UsernamePasswordAuthenticationFilter` receives credentials, authenticates, saves context as appropriate, and redirects. A successful login will not necessarily invoke `AuthorizationFilter` on that same request.

**Scenario D: GET with session.** `SecurityContextHolderFilter` can restore context; no need to re-verify password on every request; `AuthorizationFilter` checks roles.

**Scenario E: POST with session but missing CSRF.** An already logged-in user still receives 403 at CSRF; it is not a missing-role error.

**Scenario F: Bearer API.** The Bearer filter validates the token and puts the principal into the holder; authorization uses that principal. You still must review the chain matcher and actual CSRF policy, especially if a browser might send credentials automatically.

## 8. Runnable example with Java 17, Spring Boot 3, and MockMvc

The following example uses two URLs: `/demo/public` for everyone, `/demo/private` requiring login. CSRF remains at default; tests verify **seven scenarios**. A probe filter runs after `AnonymousAuthenticationFilter` to observe requests that made it close to the authorization step. Because the probe is **after `CsrfFilter`**, requests missing a token are stopped early and will not reach the probe.

### 8.1. Create the project

```text
security-flow/
├── pom.xml
└── src/
    ├── main/java/example/securityflow/
    │   ├── SecurityFlowApplication.java
    │   └── DemoController.java
    └── test/java/example/securityflow/
        └── SecurityFlowApplicationTests.java
```

**`pom.xml`**:

```xml
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
    <artifactId>security-flow</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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

**`src/main/java/example/securityflow/SecurityFlowApplication.java`**:

```java
package example.securityflow;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/demo/public").permitAll()
                    .requestMatchers("/demo/private").authenticated()
                    .anyRequest().denyAll())
            .formLogin(form -> form.permitAll());

        // Probe belongs solely to the Spring Security filter chain.
        // Do not add @Component to the probe to avoid duplicate registration.
        http.addFilterAfter(
                new AuthorizationProbe(),
                AnonymousAuthenticationFilter.class);

        // Keep default CSRF intact, do not call csrf.disable().
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        // "{noop}" is for demo only, DO NOT use for real passwords.
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                    .password("{noop}demo-pass")
                    .roles("USER")
                    .build()
        );
    }

    static final class AuthorizationProbe extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {
            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
            String principal = auth == null ? "(none)" : auth.getName();

            System.out.printf("PROBE %s %s principal=%s%n",
                    request.getMethod(),
                    request.getRequestURI(),
                    principal);

            chain.doFilter(request, response);
        }
    }
}
```

**`src/main/java/example/securityflow/DemoController.java`**:

```java
package example.securityflow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo/public")
    public String publicGet() {
        return "public-get";
    }

    @PostMapping("/demo/public")
    public String publicPost() {
        return "public-post";
    }

    @GetMapping("/demo/private")
    public String privateGet() {
        return "private-get";
    }

    @PostMapping("/demo/private")
    public String privatePost() {
        return "private-post";
    }
}
```

**`src/test/java/example/securityflow/SecurityFlowApplicationTests.java`**:

```java
package example.securityflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFlowApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsAllowed() throws Exception {
        mvc.perform(get("/demo/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-get"));
    }

    @Test
    void publicPostWithoutCsrfIsDenied() throws Exception {
        mvc.perform(post("/demo/public"))
                .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/demo/public").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("public-post"));
    }

    @Test
    void privateGetWithoutLoginRedirects() throws Exception {
        mvc.perform(get("/demo/private")
                        .accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void privateGetWithUserIsAllowed() throws Exception {
        mvc.perform(get("/demo/private").with(user("learner")))
                .andExpect(status().isOk())
                .andExpect(content().string("private-get"));
    }

    @Test
    void privatePostWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(post("/demo/private").with(user("learner")))
                .andExpect(status().isForbidden());
    }

    @Test
    void privatePostWithUserAndCsrfIsAllowed() throws Exception {
        mvc.perform(post("/demo/private")
                        .with(user("learner"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("private-post"));
    }
}
```

Requires JDK 17+ and Maven; run inside `security-flow`:

```bash
mvn test
mvn spring-boot:run
```

The seven tests represent **expected** assertions on this configuration; `mvn test` verifies those values. Once the application is running, try:

```bash
curl -i http://localhost:8080/demo/public
curl -i -X POST http://localhost:8080/demo/public
curl -i -H "Accept: text/html" http://localhost:8080/demo/private
```

Expected HTTP results (ignoring environment-dependent headers): **200**, **403**, **302 login redirect**. A POST wanting to pass CSRF needs a valid token; tests supply a token via `with(csrf())`. `user("learner")` here **simulates an authenticated principal** for a MockMvc request, rather than testing real password login.

**Example** log lines, not representing a fixed test execution order:

```text
PROBE GET /demo/public principal=anonymousUser
PROBE GET /demo/private principal=learner
PROBE POST /demo/private principal=learner
```

A POST request missing a CSRF token will be stopped at `CsrfFilter` before the probe, so no corresponding log appears. An unauthenticated request can reach the probe with `anonymousUser` and then be rejected by `AuthorizationFilter`; the probe logging does not mean the request was allowed. For a successful login POST, the authentication filter may redirect without continuing to the probe.

### 8.2. Viewing actual filter order logs

In a development environment, you can enable:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Place it in `src/main/resources/application.properties`. Inspect the "Invoking ...Filter" logs to see which filters are called, which chain is selected, and where the request stops. Disable TRACE after diagnosing to avoid excessive logs or logging sensitive data.

## 9. Design mistakes and how to avoid them

1. **Confusing `permitAll()` with "bypass all security".** It only changes the authorization policy. CSRF, login filters, and other security filters can still process the request.
2. **Assuming HTTP 403 always comes from `AuthorizationFilter`.** CSRF can reject earlier. Read the logs of the failing filter and test a request with a valid CSRF token.
3. **Checking only `authentication != null` to tell if logged in.** AnonymousAuthenticationFilter can set an anonymous token. Use `authenticated()` rules or proper anonymous checks.
4. **Setting context in a custom filter and forgetting to save it.** With modern `SecurityContextHolderFilter`, integrate `SecurityContextRepository` and explicitly save context as required by design.
5. **Writing data-mutating code too early, before CSRF checks.** Business side effects could occur before the request is rejected; ensure data-mutating paths sit after appropriate controls.
6. **Registering a custom Filter twice.** If a filter is both a `@Component` auto-registered by the container and added via `http.addFilterBefore/After`, it may execute in two places. The demo instantiates the probe directly in configuration to avoid this.
7. **Using `@Order` at the wrong level.** `@Order` across multiple `SecurityFilterChain`s controls chain selection, `addFilter...` controls filter order inside a chain, and `requestMatchers` controls rule order.
8. **Applying rules to the wrong SecurityFilterChain.** `FilterChainProxy` selects the first matching chain; chains are not merged. When having `/api/**` and `/**`, verify the matcher and order of both.
9. **Disabling CSRF just because an API uses JSON.** If a browser can automatically send session cookies or credentials, CSRF risk may still exist.
10. **Assuming `OncePerRequestFilter` always runs once across all dispatchers.** Async/error dispatches and registration dispatcher types affect invocation counts; examine both container and filter mechanisms.
11. **Assuming `ExceptionTranslationFilter` catches all security exceptions.** It primarily handles exceptions from filters downstream of it; CSRF and upstream authentication filters have their own handlers.
12. **Equating session with context.** Session stores state across requests when configured; `SecurityContextHolder` represents context within the current execution scope.

## 10. Workflow for diagnosing blocked requests

1. Record the exact **HTTP method, URI, dispatcher type**, authentication mechanism, and relevant request headers. Never put real passwords/tokens into logs.
2. Identify the **first matching `SecurityFilterChain`** for the request; other chains do not participate for that request.
3. Enable appropriate TRACE logging to find the **filter stopping early**. `CsrfFilter` precedes authorization, and login filters can terminate the request themselves.
4. Inspect `Authentication` at the stage after authentication/anonymous; distinguish null, anonymous, and a real user.
5. For form/session: verify login success saved the context, the session cookie was returned, and the client sent it back.
6. For Bearer/stateless: verify the token was validated and the principal and authorities were constructed properly.
7. Check `authorizeHttpRequests` policy, `requestMatchers` order, role prefix, and method security. If a custom filter is involved, verify its order inside the chain alongside container registration.
8. Write tests for **GET/POST**, with/without CSRF token, anonymous/authenticated, and sufficient/insufficient roles. Read status codes and filter logs together.

## 11. Self-check

**1.** A `POST /public` configured with `permitAll()`, missing a CSRF token, may return what?  
**Answer:** 403 at `CsrfFilter`, before the `permitAll()` rule is evaluated.

**2.** Does a logged-in user loaded from an HTTP session have to re-verify their password on every request?  
**Answer:** No. The context is restored from the repository; password authentication is a separate mechanism.

**3.** Logged in with `ROLE_USER` but `/admin/**` requires `ROLE_ADMIN`, at which step is it blocked?  
**Answer:** Authorization; typically `AuthorizationFilter` triggers denial and `ExceptionTranslationFilter` converts it into the appropriate response.

**4.** Is a non-null `Authentication` guaranteed to be a logged-in user?  
**Answer:** No; it could be an `AnonymousAuthenticationToken`.

**5.** Does merely calling `setAuthentication(...)` in a custom filter guarantee the next request stays logged in?  
**Answer:** No; in the modern mechanism, you must ensure saving the context via the appropriate repository when login persistence is needed.

**6.** Can you fix an API chain's permissions by adding `requestMatchers(...)` to an MVC chain that does not match the API?  
**Answer:** No. `FilterChainProxy` applies the first matching chain, so configuration must be on the right chain.

**7.** Is `ExceptionTranslationFilter` where passwords are read and CSRF tokens are checked?  
**Answer:** No. Authentication filters and `CsrfFilter` have their own responsibilities; exception translation sits near the end of the chain.

**8.** Does a stateless Bearer API need `SecurityContext`?  
**Answer:** Yes, so authorization and downstream code know the principal for the current request, even though login is not saved in a session.

**Key takeaway:** understanding **filter ordering**, **Authentication source**, and **the stage where execution stops** is the key to distinguishing CSRF, authentication, and authorization errors in Spring Security Servlet.