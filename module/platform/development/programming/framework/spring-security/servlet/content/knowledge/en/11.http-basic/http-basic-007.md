# Combining HTTP Basic for APIs with Form Login in Another SecurityFilterChain

## 1. Goal and Problem Statement

A Spring Security Servlet application sometimes serves **two very different kinds of clients**:

- **API clients** calling `/api/**` with HTTP Basic, sending the `Authorization: Basic ...` header on each request. When unauthenticated, the client should receive **HTTP 401** with the right challenge mechanism, not an HTML redirect to a login form.
- **Browsers** visiting regular web pages, redirected to `/login` when not logged in, then authenticating via **form login**, persisting login state via session, and continuing to use the website.

If a single shared filter chain enables both `httpBasic` and `formLogin` without clear boundaries, responses for browsers and APIs may diverge from expectations. The clean solution in Spring Security Servlet is to define **multiple `SecurityFilterChain`s**, each with its own `securityMatcher`, authentication mechanism, entry point, and session policy.

Learning objectives for this lesson:

1. Understand that `FilterChainProxy` picks **the first chain matching the request**, without merging or running all chains sequentially.
2. Route `/api/**` APIs into an HTTP Basic chain and web pages into a form login chain.
3. Distinguish **`securityMatcher` selecting a chain** from **`requestMatchers` selecting authorization rules inside a chain**.
4. Configure `@Order`, a fallback chain, and login/logout URLs within the right scope.
5. Design sessions, request caching, and CSRF per request group without confusing “stateless” with “CSRF-safe”.
6. Verify HTTP 401/403/302, headers, login/session, and chain boundaries with Spring Boot 3 + Java 17 + MockMvc.

The implementation example in section 8 is **a complete Servlet app for learning**. It uses in-memory accounts to keep the focus on multiple filter chains; production needs a database/identity provider, TLS, secret management, rate limiting, and appropriate security controls.

## 2. What Do Two Chains Mean in the Servlet Architecture?

Conceptual processing path:

```text
HTTP request
     |
     v
Servlet container Filter chain
     |
     v
DelegatingFilterProxy (springSecurityFilterChain)
     |
     v
FilterChainProxy
     |
     +-- SecurityFilterChain @Order(1)
     |     securityMatcher("/api/**")
     |     |-- matches?
     |     |    YES -> API chain only:
     |     |       SecurityContext handling
     |     |       HTTP Basic authentication
     |     |       AuthorizationFilter
     |     |       ...
     |     |-- NO -> try next chain
     |
     +-- SecurityFilterChain @Order(2)
           default matcher: all remaining requests
           |-- Form login filters
           |-- Session-based SecurityContext
           |-- AuthorizationFilter
           |-- ...
     |
     v
Controller/Servlet if checks pass
```

`DelegatingFilterProxy` bridges the Servlet container to a Spring bean; `FilterChainProxy` manages the `SecurityFilterChain`s. Each chain contains the security filters produced by that chain's configuration, along with its own matcher.

**Most importantly:** For each request, `FilterChainProxy` finds the **first `SecurityFilterChain` whose matcher matches**, and executes only that chain's filters. It does **not** forward the request to the web chain after the API chain finishes authenticating. Therefore:

- `GET /api/orders` must enter the API chain.
- `GET /web/profile` must enter the web chain.
- `GET /login` and `POST /login` must also be handled by the web chain if you use Spring Security's default login endpoint.
- `GET /some-other-page` needs a broad enough fallback chain if the app wants that route protected.

Any request **matching no `SecurityFilterChain`** may bypass Spring Security protection. That is why you must never accidentally leave gaps when splitting chains.

### 2.1. Authentication and Authorization in Each Chain

**Authentication** answers “who is this client?”, coming from `BasicAuthenticationFilter` for HTTP Basic and typically `UsernamePasswordAuthenticationFilter` for form login.

**Authorization** answers “is this identity allowed to access the endpoint?”, configured via `authorizeHttpRequests`. In modern configurations it uses `AuthorizationFilter` and corresponding `AuthorizationManager`s.

API and web can share `UserDetailsService`, `PasswordEncoder`, or `AuthenticationProvider` to use a common account store, yet that **does not mean** they must share sessions, request caches, or unauthenticated challenges.

## 3. How securityMatcher Differs from requestMatchers

These two APIs look similar yet operate **at different layers**.

| API | Scope | Effect | Example |
| --- | --- | --- | --- |
| `http.securityMatcher("/api/**")` | Entire `SecurityFilterChain` | Decides **whether the request enters this chain** | API chain accepts only `/api/...` |
| `authorizeHttpRequests(auth -> auth.requestMatchers("/api/public").permitAll())` | Authorization rules of the selected chain | Allows/checks permissions for matching paths **within the chain** | Public API route |
| `anyRequest().authenticated()` | Final rule of the selected chain | Requires authentication for remaining requests **in that chain** | All APIs except `/api/public` |
| `@Order(1)`, `@Order(2)` | Ordering of `SecurityFilterChain` beans | Determines which chain is evaluated first | API first, web fallback second |

A common misconception:

```java
// Illustrates what does NOT meet chain-splitting requirements:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().authenticated()
);
```

This snippet addresses **authorization only**. It does not automatically enable HTTP Basic exclusively for `/api/**` or form login exclusively for web. If `httpBasic` and `formLogin` are both present in this chain, their filters and entry points remain in the same setup unless customized appropriately.

### 3.1. Why Does @Order Matter?

Suppose you put a web chain matching all requests at `@Order(1)`, and the API chain at `@Order(2)`. When `GET /api/orders` arrives, the web chain matches first. The API chain, even if configured accurately, will **never get chosen**.

Safe ordering in this lesson:

```text
@Order(1): /api/**    -> HTTP Basic
@Order(2): any request -> form login
```

Do not assume the lowest `@Order` is the “highest-privilege” chain; it merely defines **matcher evaluation priority**. In real apps you might add chains for actuator, admin, or OAuth2, yet each chain needs a clear scope and overlap analysis.

### 3.2. securityMatcher Is Not a Permission Check

If the API chain has `securityMatcher("/api/**")`, a request to `/api/admin` enters the chain even when unauthenticated. It will then be **authenticated and authorized inside the chain**, not granted access simply because the matcher matched.

Likewise, `requestMatchers("/api/public").permitAll()` does not skip the entire filter chain. Public requests can still traverse configured security filters, with implications for headers, CSRF, and diagnostics.

## 4. HTTP Basic in the API Chain

HTTP Basic defines an authentication scheme where the client sends Base64-encoded username/password in a header:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64(username:password)>
```

**Base64 is not secure encryption.** HTTPS is needed to protect credentials in transit. Never put real usernames/passwords in URLs or logs, and never use HTTP Basic over unencrypted networks for real systems.

Typical flow:

```text
GET /api/me
     |
     +-- No Authorization header
     |      -> authentication required: HTTP 401
     |         WWW-Authenticate: Basic ...
     |
     +-- Valid Basic header
     |      -> BasicAuthenticationFilter
     |      -> AuthenticationManager/Provider
     |      -> UserDetailsService + PasswordEncoder
     |      -> Valid Authentication
     |      -> AuthorizationFilter
     |      -> Controller returns 200 if authorized
     |
     +-- Invalid credentials
     |      -> Authentication failed
     |      -> HTTP 401
     |
     +-- Valid credentials but missing authority
            -> HTTP 403 on higher-privilege resource
```

These status codes are expected results **under the practice setup**; custom handlers/entry points can change them. Never claim 401 always means “user does not exist” and 403 always means “wrong password”. A wrong password is normally an authentication failure resulting in 401 in a Basic API; an authenticated user lacking permissions normally results in 403.

### 4.1. Client Resends Basic Per Request

In the stateless API example, the client must keep sending `Authorization` on protected requests. Having logged into the website via form login **does not** make the API chain automatically use the website's cookie/session.

Some browsers may automatically resend Basic credentials after authenticating to a challenge; thus you must consider CSRF and credential caching when the API has state-changing requests. Never infer that “not using session cookies” means browsers never auto-attach credentials.

### 4.2. HTTP Basic Does Not Provide Form-Login-Style Session Logout

Website logout typically invalidates/clears the session. Yet a Basic client can resend the exact same `Authorization` on the next request and get re-authenticated. Revoking credentials requires password/account/token management in the authentication system; clearing `SecurityContextHolder` once is not enough.

Hence Basic is usually better suited for simple clients, internal environments, or compatibility needs—with TLS and abuse controls—rather than automatically being the optimal choice for all modern APIs.

## 5. Form Login in the Web Chain

Form login serves browsers:

```text
GET /web/me without authenticated session
    |
    -> web SecurityFilterChain
    -> not yet authenticated
    -> 302 Location: /login
    |
GET /login
    -> default form or custom login page
    |
POST /login
    -> username/password + valid CSRF token
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager
    -> success: saves SecurityContext to session per policy
    -> redirects to saved request or default target
    |
GET /web/me with session cookie after login
    -> restores Authentication from session
    -> 200 if permitted
```

Unlike Basic, form login normally works via an **HTTP session**. `SecurityContextRepository` and the session cookie determine whether later requests restore login state. `RequestCache` can remember the web URL blocked before login; that is not the API chain's job if the API uses `NullRequestCache`.

The example can use Spring Security's **generated login page** when `loginPage(...)` is omitted. With `formLogin(Customizer.withDefaults())`, the web chain must receive requests to the default `/login` path for both GET displaying the form and POST processing login. If the web chain is restricted with `securityMatcher("/web/**")` without including `/login`, the default login endpoint may not be handled by the filters.

### 5.1. Why Is the Web Fallback Left Without a securityMatcher?

In the example:

```text
API: @Order(1), securityMatcher("/api/**")
WEB: @Order(2), no securityMatcher set
```

This lets the web chain cover `/login`, `/logout`, `/`, and other web URLs without listing every single one in the chain's matcher. The web chain's `authorizeHttpRequests` still decides which endpoints are public and which require login.

An alternative design could use a specific web matcher plus a third fallback chain, provided you verify that login/error/static paths are not missed and no request slips outside all chains.

### 5.2. Do Not Enable httpBasic on Web Unless Needed

If `httpBasic` is also added to the web chain, browsers might receive a Basic challenge on paths meant for form login; APIs/browsers might get inconsistent responses depending on request headers. To keep boundaries clear, this lesson's web chain **enables only form login**, and the API chain **enables only HTTP Basic**.

## 6. Session, SecurityContext, and RequestCache: Splitting Policy by Chain

The two chains can share accounts, yet context persistence mechanisms should be explicit.

| Property | API chain | WEB chain |
| --- | --- | --- |
| Matcher | `/api/**` | Remaining requests (fallback) |
| Authentication mechanism | HTTP Basic | Form login |
| Unauthenticated | 401 + Basic challenge | 302 to `/login` |
| Persists login across HTTP requests | No, in the stateless example | Yes, via HTTP session |
| `SecurityContextRepository` | Explicit `NullSecurityContextRepository` | Web default session-aware repository |
| `RequestCache` | Explicit `NullRequestCache` | Request cache for saved URL/login |
| CSRF | Not auto-disabled just for being stateless | Needs protection on state-changing operations per browser model |
| Account lookup | Can share `UserDetailsService` | Can share `UserDetailsService` |
| Authorization | API rules | Web rules |

### 6.1. STATELESS Does Not Mean Unauthenticated

`SessionCreationPolicy.STATELESS` indicates Spring Security neither creates nor uses sessions to retrieve `SecurityContext` for the API chain. Each request is processed using its own authentication data (here, the Basic header). It still establishes `Authentication` **for the duration of the current request** and checks permissions.

Using `NullSecurityContextRepository` demonstrates not persisting context to a session via the repository. Still, a stateless configuration **does not forbid all libraries or business code** from ever creating a session. Test in practice if the product strictly requires zero sessions/cookies.

### 6.2. Why NullRequestCache for API?

A Basic API does not need to remember URLs to redirect back to after form login. `NullRequestCache` avoids storing unauthenticated requests in a session. When an API request is unauthenticated, the server returns HTTP 401 and the client decides the next step.

### 6.3. CSRF Must Be Analyzed by Client Type

**A common mistake:** “The stateless API uses Basic, so CSRF can be disabled unconditionally.”

CSRF concerns browsers **automatically attaching credentials** to requests triggered by another site. Browsers can cache and auto-resend Basic credentials in some scenarios; therefore, the API's CSRF policy must depend on whether clients are browsers, credential delivery mechanisms, cookies/challenges, and endpoints with side effects.

In the runnable example, **default CSRF protection is kept** on both chains, while only GET APIs are defined to avoid introducing a state-changing endpoint without CSRF design. For machine-to-machine APIs using explicitly client-managed headers backed by a threat model, CSRF can be disabled **only on the API chain**—provided you verify requests do not rely on browser auto-sent credentials and other defenses exist.

Example **conditional option, not applied in the runnable SecurityConfig below**:

```java
// Only in apiSecurityChain(...), after thorough CSRF evaluation:
http.csrf(csrf -> csrf.disable());
```

Do not copy this line into the web chain just to make `POST /login` “work easily”. Standard form login normally requires a CSRF token on POST, and tests will supply a valid token.

## 7. Choosing One or Multiple Account Sources?

The core focus is independence between **SecurityFilterChain**s. In the learning app, both chains share one `UserDetailsService` and `PasswordEncoder` bean. That allows `reader` or `admin` to authenticate via either Basic or form login depending on which chain handles the request.

Do not conclude from this that two chains must share the same `AuthenticationManager` in every app. When a product needs separate API accounts or multiple identity providers, configure suitable `AuthenticationProvider`/`AuthenticationManager` beans per chain. Check provider ordering, user sources, caching, and effects when the same username exists in multiple stores.

In the example:

```text
UserDetailsService + PasswordEncoder
        |
        +---- API chain -> HTTP Basic -> DAO authentication
        |
        +---- WEB chain -> Form login -> DAO authentication
```

**Sharing an account store does not mean sharing login sessions.** A form login creating a session only takes effect on chains with a session-backed context; the API chain using `NullSecurityContextRepository` does not treat that session as authentication proof.

### 7.1. Why Not Arbitrarily Define Two AuthenticationManagers?

Defining separate managers/providers helps when domains genuinely differ, yet easily introduces subtle bugs: mismatched password encoders, wrong user stores, differing authority mappings, or wiring one chain's manager into the wrong chain. Start with one consistent user store to prove routing; split providers only when concrete requirements and tests demand it.

## 8. Complete Spring Boot 3.3.5 + Java 17 Example

This example builds and runs with Maven on Java 17. It uses exactly two `SecurityFilterChain`s:

- `@Order(1)`: `/api/**` → HTTP Basic, no context stored in HTTP session, no saved requests stored.
- `@Order(2)`: fallback → form login, normal sessions, default login page.

### 8.1. Directory Structure

```text
dual-chain-security/
  pom.xml
  src/
    main/
      java/example/dual/
        DualChainApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/example/dual/
        DualChainSecurityTest.java
```

### 8.2. pom.xml

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
    <artifactId>dual-chain-security</artifactId>
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

This is a **Spring MVC Servlet** app, not WebFlux. The APIs in code belong to Servlet `org.springframework.security.config.annotation.web.builders.HttpSecurity` and `SecurityFilterChain`.

### 8.3. Startup Class

File `src/main/java/example/dual/DualChainApplication.java`:

```java
package example.dual;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualChainApplication.class, args);
    }
}
```

### 8.4. SecurityConfig with Two SecurityFilterChains

File `src/main/java/example/dual/SecurityConfig.java`:

```java
package example.dual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Keep default CSRF. Example only has GET APIs, no POST/PUT/DELETE.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/web/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Do not set securityMatcher("/web/**") here.
        // This chain is the fallback so GET/POST /login is handled.
        return http.build();
    }
}
```

#### Explaining the Essential Points

**`@Order(1)` and `securityMatcher("/api/**")`:** the API matcher is evaluated first. A `/api/me` request matches and stops at this chain; the web chain never handles it.

**`httpBasic(Customizer.withDefaults())`:** enables Basic authentication and its challenge. The API has no `formLogin` in this chain, so an anonymous client calling `/api/me` is never redirected to an HTML login page.

**`SessionCreationPolicy.STATELESS` + `NullSecurityContextRepository`:** explicitly ensures the API does not read Authentication from an HTTP session across requests. This does not disable authentication within the current request; Basic headers are still processed normally.

**`NullRequestCache`:** the API does not save the original URL in a session just to redirect after login.

**CSRF not disabled in the example:** the API currently has only GET; the web chain still needs CSRF for POST login. If adding POST API endpoints, decide CSRF based on client models and credential delivery. Stateless alone is not enough reason to disable CSRF.

**Web chain has no securityMatcher:** it catches all remaining requests, including `GET /login` and `POST /login`. Because only form login is enabled, anonymous web requests typically redirect instead of receiving a Basic challenge.

**Shared `UserDetailsService`:** accounts are hashed with `BCryptPasswordEncoder`. `roles("READER")` creates `ROLE_READER`, and `roles("ADMIN")` creates `ROLE_ADMIN`; `hasRole("ADMIN")` checks authority `ROLE_ADMIN` by convention.

**Never hardcode credentials in real products:** `reader-pass` and `admin-pass` are sample data only. A real database or secret/identity store requires secure storage, account lifecycle management, TLS, and rate limiting.

### 8.5. Controller Proving Routes Belong to Two Groups

File `src/main/java/example/dual/DemoController.java`:

```java
package example.dual;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/api/public")
    String apiPublic() {
        return "api:public";
    }

    @GetMapping("/api/me")
    String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "api:admin";
    }

    @GetMapping("/web/public")
    String webPublic() {
        return "web:public";
    }

    @GetMapping("/web/me")
    String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/admin")
    String webAdmin() {
        return "web:admin";
    }
}
```

Both `/api/me` and `/web/me` consume an `Authentication` injected into the controller by Spring Security. The difference lies **not in the Java method**, but in which filter chain created the Authentication and how it was loaded for the request.

The controller defines only GET routes to keep the example focused on authentication and authorization policies, avoiding any misleading impression of a production-safe mutating API.

## 9. MockMvc Integration Tests: Verifying Both Chains and Session Boundaries

File `src/test/java/example/dual/DualChainSecurityTest.java`:

```java
package example.dual;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
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
class DualChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousPublicApiWorks() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api:public"));
    }

    @Test
    void anonymousApiGetsBasicChallengeNotLoginRedirect()
            throws Exception {
        MvcResult result = mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge = result.getResponse()
            .getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void validBasicCredentialsWorkOnApi() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void wrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiRequiresAdminAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:admin"));
    }

    @Test
    void anonymousWebRedirectsToFormLogin() throws Exception {
        MvcResult result = mvc.perform(get("/web/me"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String redirect = result.getResponse().getRedirectedUrl();
        assertNotNull(redirect);
        assertTrue(redirect.contains("/login"));
    }

    @Test
    void browserCanLogInAndUseSession() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession rawSession = result.getRequest().getSession(false);
        assertNotNull(rawSession);

        MockHttpSession session = (MockHttpSession) rawSession;
        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:reader"));
    }

    @Test
    void webLoginSessionDoesNotAuthorizeStatelessApi()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        // A web session has Authentication; API does not use it as a source.
        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:reader"));

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());

        // A valid Basic header can still authenticate this API request.
        mvc.perform(get("/api/me")
                .session(session)
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void basicHeaderAloneDoesNotEnableWebBasicFilter()
            throws Exception {
        MvcResult result = mvc.perform(get("/web/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String redirect = result.getResponse().getRedirectedUrl();
        assertNotNull(redirect);
        assertTrue(redirect.contains("/login"));
    }

    @Test
    void webLoginPostRequiresCsrfByDefault() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedReaderCannotVisitWebAdmin()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/admin").session(session))
            .andExpect(status().isForbidden());
    }
}
```

### 9.1. Do the Tests Genuinely Prove HTTP Basic?

Yes: `httpBasic("reader", "reader-pass")` in Spring Security Test generates a Basic Authorization header so the request enters the **real filter chain**. It is **not** equivalent to `.with(user("reader"))`, which pre-populates an authenticated user and can bypass password verification.

When `/api/me` is called without credentials, the test also asserts `WWW-Authenticate` starts with `Basic` instead of merely accepting HTTP 401. That verifies most of the API's intended UX/protocol contract.

### 9.2. What Does the Session Boundary Test Explain?

`webLoginSessionDoesNotAuthorizeStatelessApi` reuses the same `MockHttpSession` across three contrasting requests:

1. `GET /web/me` → 200 with the form-logged-in user.
2. `GET /api/me` with the same session, no Basic header → **401** because the API chain does not use `SecurityContext` from the session.
3. `GET /api/me` with the same session plus a Basic header → **200** because Basic is verified for this API request.

This test proves **differences in mechanism and repository per chain under this specific configuration**, not that no API could ever allow cookie login. Systems wanting cookie-authenticated APIs have their own design and must secure CSRF/sessions properly.

### 9.3. Which Test Verifies Routing When a Basic Header Hits Web?

`basicHeaderAloneDoesNotEnableWebBasicFilter` sends Basic Authorization to `/web/me` yet still expects a redirect to login. That is because the web chain declares only form login and does not use a Basic filter to auto-authenticate. This test catches misconfigurations where both mechanisms are accidentally enabled in the same chain.

### 9.4. The Tests Do Not Fake Timestamps or Session IDs

The tests do not assert specific session IDs because Spring Security may perform session fixation protection. The test retrieves `MockHttpSession` after the login request. Nor do they assert default login HTML strings or fixed realm details that can vary by Spring Security version/config.

## 10. Running the App and HTTP Results

In the `dual-chain-security` directory containing `pom.xml`, with Maven + JDK 17 or newer:

```bash
mvn test
mvn spring-boot:run
```

Given matching dependencies and environment, **all 11 tests are expected to pass**. Never assume a single identical Maven stdout since build logs depend on timestamps/JVM/machine.

You can test with `curl` on **localhost for learning**:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/web/me
```

**Never use `curl -u` with real credentials in shell history or over unencrypted HTTP.** The example runs locally with test accounts only. Deployed environments require HTTPS and proper credential/secret management.

Logical HTTP results:

| Request | Expected result | Meaning |
| --- | --- | --- |
| Anonymous GET `/api/public` | 200, `api:public` | `permitAll` in API chain |
| Anonymous GET `/api/me` | 401 + `WWW-Authenticate: Basic ...` | API requires Basic credentials |
| Valid Basic reader, GET `/api/me` | 200, `api:reader` | API Basic succeeded |
| Wrong Basic reader password, GET `/api/me` | 401 | Authentication failed |
| Valid Basic reader, GET `/api/admin` | 403 | Missing `ROLE_ADMIN` |
| Valid Basic admin, GET `/api/admin` | 200, `api:admin` | Correct authority |
| Anonymous GET `/web/me` | 302 to `/login` | Web form login |
| Form POST `/login` with CSRF and right password | 302 after login | Session-backed login |
| GET `/web/me` with same session after login | 200, `web:reader` | Form session active |
| GET `/api/me` with only web session | 401 | API does not read session authentication |
| GET `/api/me` with Basic and web session | 200 | Basic governs the API request |
| POST `/login` without CSRF | 403 | CSRF on web chain |

Even after a successful web form login, `/web/admin` still returns 403 for reader because authentication and authorization are two separate responsibilities.

## 11. A Standalone Java 17 Example: Understanding First-Match Routing

`FilterChainProxy` matches using Spring Security's `RequestMatcher`s, not plain `String.startsWith`. Still, we can illustrate **first-chain selection** logic with a dependency-free Java 17 program.

Create `FirstMatchChainDemo.java`:

```java
import java.util.List;

public class FirstMatchChainDemo {

    record Chain(int order, String pattern, String mechanism) {
        boolean matches(String path) {
            if ("/**".equals(pattern)) {
                return true;
            }
            // Simple simulation of paths under /api/*.
            if ("/api/**".equals(pattern)) {
                return path.startsWith("/api/");
            }
            return pattern.equals(path);
        }
    }

    static String select(List<Chain> chains, String path) {
        for (Chain chain : chains) {
            if (chain.matches(path)) {
                return chain.mechanism();
            }
        }
        return "NO_CHAIN";
    }

    public static void main(String[] args) {
        List<Chain> correct = List.of(
            new Chain(1, "/api/**", "HTTP_BASIC"),
            new Chain(2, "/**", "FORM_LOGIN")
        );

        System.out.println("/api/orders -> "
            + select(correct, "/api/orders"));
        System.out.println("/web/me -> "
            + select(correct, "/web/me"));
        System.out.println("/login -> "
            + select(correct, "/login"));

        List<Chain> wrong = List.of(
            new Chain(1, "/**", "FORM_LOGIN"),
            new Chain(2, "/api/**", "HTTP_BASIC")
        );
        System.out.println("wrong order /api/orders -> "
            + select(wrong, "/api/orders"));
    }
}
```

Run with JDK 17+:

```bash
javac FirstMatchChainDemo.java
java FirstMatchChainDemo
```

**Exact** stdout:

```text
/api/orders -> HTTP_BASIC
/web/me -> FORM_LOGIN
/login -> FORM_LOGIN
wrong order /api/orders -> FORM_LOGIN
```

This model deliberately simplifies matchers and assumes the list is already sorted by priority. It **does not simulate** authentication filters, CSRF, sessions, Spring PathPattern, Ant matching, or exception handling. Use it to explain why **fallback chains must come after specialized chains**, and use MockMvc tests to verify real Servlet behavior.

## 12. When Do You Need Two Chains and When Don't You?

Two chains are a sound choice when:

- API and web have different **authentication entry points** (401 Basic challenge vs HTML redirect).
- API needs to be **stateless** while web needs sessions.
- Request cache, CSRF, header handling, or exception handling policies differ by endpoint group.
- There are distinct requirements for credential sources or authentication providers.
- You need to prove every URL belongs to a consistent security configuration rather than tangled if/else branches in a custom filter.

You can use **one chain** when all endpoints share the same authentication/session/entry-point mechanism and differ only in access rules. Never add another chain merely because two controllers live in different packages.

Multiple chains clarify configuration when needs truly diverge, yet increase testing requirements for matchers, default endpoints, and fallbacks. Avoid creating numerous chains without distinct responsibilities.

## 13. Common Mistakes and Consequences

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Catch-all web chain at `@Order(1)`, API at `@Order(2)` | `/api/**` gets “swallowed” by web chain, may redirect to login instead of 401 | Place API chain before fallback; verify with MockMvc |
| Using only `requestMatchers("/api/**")` without `securityMatcher` | Creates authorization rules only, not separate filter mechanisms | Use `securityMatcher` on the API chain |
| Locking web chain with `securityMatcher("/web/**")` while keeping default `/login` URL | GET/POST `/login` misses expected chain; login breaks or goes unprotected | Include login URL in matcher or use a web fallback as shown |
| Creating only an API chain with no fallback | Non-API requests may bypass Spring Security | Add a fallback chain and test non-API URLs |
| Enabling both formLogin and httpBasic in API chain | May fail to produce expected 401 JSON/Basic behavior | Enable only HTTP Basic in the API chain as required |
| Enabling Basic in the web chain “for convenience” | Browsers may receive unwanted challenge/credential behavior | Enable only form login in the web chain |
| Using a web-login session to call stateless API without header | API still returns 401; client thinks session is “broken” | Send valid API credentials or intentionally design a cookie-auth API |
| Calling `STATELESS` and assuming no request can create a session | Other code can still create sessions outside security context | Inspect session lifecycle and other components |
| Disabling CSRF on all chains because the API is stateless | Web form POSTs lose essential protection | Assess CSRF per authentication mechanism and client; keep web protected |
| Thinking HTTP Basic Base64 is secure encryption | Credentials easily read on networks without TLS | Require HTTPS and protect credentials |
| Using `roles("ROLE_ADMIN")` instead of `roles("ADMIN")` | Violates prefix/validation convention | Use `roles("ADMIN")` or `authorities("ROLE_ADMIN")` |
| Thinking `permitAll` skips all filters | Misunderstands headers, sessions, CSRF, and filter routing | Distinguish authorization permit from filter bypass |
| Asserting only 401 in API tests | Can miss a missing Basic challenge header | Check `WWW-Authenticate` properly |
| Using `.with(user(...))` and concluding Basic password works | Test can bypass username/password verification | Use `httpBasic(...)` through the filter chain |
| Failing to test nonexistent routes | Endpoints outside matchers might be unprotected | Have fallback `anyRequest().authenticated()` and test 404/auth |
| Putting real passwords in code/curl/logs | Secrets exposed via commits or shell history | Use secrets managers/HTTPS; never log credentials |
| Treating API and web logout with the same expectation | Web session logout does not revoke cached Basic headers | Separate session, password, token, and revocation policies |

### 13.1. Special Mistake: Two Chains Do Not Operate as “First Chain Authenticates, Next Chain Continues”

This mental model leads to dangerous designs: thinking you can write chain 1 solely for Basic auth, chain 2 for form login, and chain 3 for authorization on the same request. **That is not how `FilterChainProxy` selects a `SecurityFilterChain`**. Each chain is a complete filter configuration for the requests it accepts.

If multiple authentication steps or authorization rules are needed for **one group of requests**, configure those filters/providers within **the same chain** or use the appropriate Spring Security mechanism. Never split those filters across chains expecting them to compose sequentially.

## 14. Pre-Production Security Checks

### 14.1. Boundaries and Route Coverage

- Do all real API URLs fall under `/api/**`, including `/api/v2/**`, callbacks, health, and error endpoints?
- Does any API endpoint outside the prefix accidentally receive an HTML form-login redirect?
- Does the fallback chain protect all remaining URLs with `anyRequest().authenticated()`?
- Are actuator endpoints or a management port running separate security configs that need review?
- Could changes to `servletPath`, context path, or reverse-proxy rewrites alter matcher behavior?

### 14.2. Authentication and Credential Protection

- HTTP Basic travels only over HTTPS and credentials/`Authorization` headers are never logged.
- Passwords are stored using dedicated password hashing, never plaintext or reversible encryption.
- Rate limiting/abuse detection is in place before expensive password-checking endpoints.
- Authentication failures and authorization failures are distinguished without leaking user details.
- If APIs need dedicated keys/tokens, have options better than website account passwords been considered?

### 14.3. Sessions and CSRF

- Does web login save sessions properly, logout clear/invalidate sessions, and cookies have Secure/HttpOnly/SameSite per policy?
- Does the stateless API genuinely avoid reading Authentication from web sessions?
- If the API has POST/PUT/DELETE called by browsers, has CSRF been evaluated despite using HTTP Basic?
- Avoid disabling CSRF globally just to make POST login tests pass; pass CSRF tokens in tests and real UIs.
- Test security context handling under concurrent requests and async methods if the app uses them.

### 14.4. Monitoring and Operations

- Dev/staging logs show which chain matched, which mechanism ran, and 401/302/403 outcomes without recording secrets.
- Metrics track request/response counts per API/web group and authentication failure rates.
- Clearly distinguish 401 Basic missing/invalid credentials, 403 policy denial, and 302 form entry point rather than treating all errors as “session expired”.
- Configure reverse-proxy headers and HTTPS redirects cleanly to prevent open redirects or host header poisoning on login/redirects.

## 15. Debugging Guide When Combining HTTP Basic and Form Login Misbehaves

When an API request redirects to `/login` instead of returning 401:

1. Verify the exact URL, including context path and servlet path.
2. Enable Spring Security logging in development to inspect `FilterChainProxy` and filter handling:
   
   ```properties
   logging.level.org.springframework.security=DEBUG
   ```

3. Check `@Order` across all `SecurityFilterChain` beans; never assume Java file declaration order sets priority.
4. Confirm the API chain genuinely defines `securityMatcher("/api/**")`. `requestMatchers` inside `authorizeHttpRequests` **does not replace** it.
5. Check whether a catch-all web chain has a lower order value than the API chain.
6. Confirm the API chain enables `httpBasic` and omits form login as intended.
7. Check whether unauthenticated requests receive `WWW-Authenticate: Basic ...`.
8. On 403, check CSRF on POST and authorities on authenticated requests; never assume every 403 is a wrong password.
9. If web login fails, check which chain receives `GET /login`/`POST /login`, whether the CSRF token is valid, and whether the session survives redirects.
10. If a web session unexpectedly authenticates the API, inspect `SessionCreationPolicy`, `SecurityContextRepository`, and custom filters on the API chain.
11. If valid API Basic credentials still return 401, inspect `UserDetailsService`, `PasswordEncoder`, account flags, and the active provider source.
12. If a protected endpoint turns out public, check chain matchers and authorization rules rather than looking only at controller annotations.

**Debugging does not require printing Authorization headers or passwords.** Use chain info, URL paths, HTTP statuses, filter names, trace IDs, and safe internal error codes.

## 16. Self-Check Exercises

**Exercise 1.** Given two chains:

```text
@Order(1) securityMatcher("/**") + formLogin
@Order(2) securityMatcher("/api/**") + httpBasic
```

Which chain will an anonymous `GET /api/me` enter?

**Answer:** The `@Order(1)` chain matches every request and is chosen first. The second API chain is never evaluated. If policy requires Basic 401, this order is wrong; give the API-specific chain higher priority.

**Exercise 2.** The API chain has `requestMatchers("/api/**").authenticated()` but **no `securityMatcher`**. Has Basic been isolated specifically for the API?

**Answer:** No. That is an authorization rule inside the chain, not a chain-selection condition; the chain's authentication filters still apply per the shared configuration.

**Exercise 3.** Web form login succeeds and the browser holds a session cookie. Calling `/api/me` without an Authorization header against the lesson's API chain returns what?

**Answer:** HTTP 401 and a Basic challenge. The API uses a stateless session policy and `NullSecurityContextRepository`, so it does not read Authentication from the web session.

**Exercise 4.** User `reader` sends a valid Basic header to `/api/admin` and receives 403. Is this a wrong password?

**Answer:** No. Credentials authenticated successfully, yet `reader` lacks the `ROLE_ADMIN` authority. Missing permission leads to authorization denied.

**Exercise 5.** Why can a default `POST /login` without a CSRF token return 403 even with the right password?

**Answer:** The CSRF filter blocks state-changing requests before the authentication filter processes them. Form login in this lesson retains CSRF protection; tests must pass `.with(csrf())`.

**Exercise 6.** You place `securityMatcher("/web/**")` on the web chain while still using the default form login URL. What must you check?

**Answer:** `/login` is not under `/web/**`; GET/POST login requests may miss the web login filters. Expand the matcher to include the login URL or use a fallback web chain and test thoroughly.

**Exercise 7.** When using stateless HTTP Basic, can you disable CSRF without any evaluation?

**Answer:** No. Browsers may automatically resend Basic credentials. Evaluate clients, credential mechanisms, endpoints with side effects, and the threat model. The example keeps default CSRF.

**Exercise 8.** Can an HTTP request run through the API filter chain and then sequentially through the web filter chain like layered middleware?

**Answer:** Not under `FilterChainProxy`'s `SecurityFilterChain` selection: it selects the first matching chain. Every filter needed for the request must live in the selected chain.

**Exercise 9.** Does testing GET `/api/me` only with `.with(user("reader"))` prove Basic username/password and headers work?

**Answer:** No. `user(...)` injects a test security context and can bypass Basic authentication. Real tests must send the header via `httpBasic(...)` or an HTTP client.

## 17. Key Takeaways

- **Multiple `SecurityFilterChain`s** let you separate HTTP Basic policy for APIs and form login for websites within a single Spring Security Servlet application.
- **`securityMatcher` selects the chain**, **`requestMatchers` selects authorization rules within a chain**, and **`@Order` determines first-match precedence**.
- Place `/api/**` with HTTP Basic at higher priority; leave the catch-all web chain later to cover `/login`, `/logout`, and other URLs.
- Basic APIs typically return **401 + `WWW-Authenticate`** for missing/invalid credentials; web browsers typically receive **302 to login**; authenticated users lacking permissions typically receive **403**.
- In the example, the stateless API uses `NullSecurityContextRepository` and `NullRequestCache`; web uses session form login. **Sharing a user store does not mean sharing session authentication**.
- Never treat HTTP Basic Base64 as encryption; use TLS. Never disable CSRF merely because of statelessness; assess whether browsers auto-send credentials.
- Test **both request groups, boundaries, and chain ordering**, especially the login URL, Basic challenge, POST login + CSRF, and that a web session does not become API authentication.
