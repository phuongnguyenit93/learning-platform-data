# End-to-End Testing of Login Paths and Fallback Chains in Spring Security

> **Goal:** Test a system with **multiple authentication mechanisms** so that each login flow works properly, invalid paths are properly rejected, privileges are never escalated unexpectedly, requests always hit the intended **SecurityFilterChain**, and fallback chains/providers never accidentally become authentication bypasses. You must distinguish **fallback among `AuthenticationProvider`s** from a **final catch-all chain covering remaining requests**.

## 1. Why Must You Test the Complete Login Path?

An application might let web users sign in with forms, expose APIs to clients using HTTP Basic, serve internal jobs via API keys, or validate IdP-issued bearer tokens. Isolated unit tests can confirm that a password-matching function works, yet still miss high-impact bugs:

- **/api/** picks the web chain by mistake and returns an HTML redirect instead of 401.
- The **/login** endpoint falls outside the SecurityFilterChain containing **UsernamePasswordAuthenticationFilter**, breaking form login.
- A broadly matching, high-priority chain shadows a chain requiring stronger privileges.
- One AuthenticationProvider rejects credentials, yet a later provider accepts the same token under a looser policy.
- A request matches no chain and ends up outside Spring Security protection.
- A client sends an API key header, but no filter converts that header into an Authentication; the provider is never called.
- Mock-identity tests using **@WithMockUser** or **with(user(...))** stay green while real credential verification is broken.
- Login succeeds without persisting the session, logout fails to clear the session, expired tokens are accepted, CSRF is skipped, or sensitive data leaks into logs.

To test the “complete login path”, you must verify **request → chain → filter → manager → provider → SecurityContext → authorization → response**. Also test missing credentials, invalid credentials, valid credentials, identity-store failures, and fallback scenarios.

## 2. Two Types of Fallback That Must Never Be Confused

### 2.1. FilterChainProxy Fallback: Selecting the First Matching Chain

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +-- @Order(1) chain /api/**        -- match? --> run API chain
    |                                      |
    |                                      +-- 401/403/200: end processing
    |
    +-- @Order(2) chain /web/**,/login -- match? --> run Web chain
    |                                      |
    |                                      +-- redirect/403/200
    |
    +-- @Order(3) catch-all chain      --------> deny everything else
~~~

Spring Security selects the **first matching SecurityFilterChain** for a request. If the API chain was selected and HTTP Basic fails, **FilterChainProxy does not move on to the Web chain** to “try logging in another way”. The catch-all chain is chosen only when earlier matchers **do not match the request**, not when authentication in an earlier chain is rejected.

A **SecurityFilterChain** holds its own filters and policies such as **httpBasic**, **formLogin**, **csrf**, **sessionManagement**, **exceptionHandling**, and **authorizeHttpRequests**. **securityMatcher(...)** scopes where the chain applies; **requestMatchers(...)** sits inside authorization for the already-selected chain. Lacking a final chain can leave requests unprotected by Spring Security.

### 2.2. ProviderManager Fallback: Trying Providers by Token Type and Result

~~~text
BasicAuthenticationFilter
  |
  | UsernamePasswordAuthenticationToken (unauthenticated)
  v
ProviderManager
  |
  +-- Provider A.supports(token.class)?
  |       |
  |       +-- returned authenticated Authentication -> stop; use A's result
  |       +-- returned null ----------------------> try next provider
  |       +-- BadCredentialsException ------> may try next provider
  |       +-- AccountStatusException ------> stop immediately
  |
  +-- Provider B.supports(token.class)?
  |       |
  |       +-- ...
  |
  +-- parent AuthenticationManager (if configured and applicable)
  |
  +-- none authenticated -> AuthenticationException
~~~

**ProviderManager** iterates through AuthenticationProviders. When a later provider succeeds, it can override an earlier provider's **BadCredentialsException**; conversely, an **AccountStatusException** stops provider iteration. **ProviderNotFoundException** indicates no configured provider can handle that Authentication. Behavior must be verified by tests, especially when **two providers both `supports(UsernamePasswordAuthenticationToken.class)`**.

**The difference:** chain fallback selects based on **HttpServletRequest** and matcher priority; provider fallback occurs when a manager processes an **Authentication** inside a chain. They are not two names for the same feature.

## 3. Designing a Test Matrix Before Writing Tests

The first step is listing the **project's actual mechanisms**, URLs, credential types, Authentication-creating filters, managers/providers, session states, privilege levels, and error entry points. The table below illustrates an application with an **HTTP Basic API**, **form-login web**, and **catch-all deny**.

| Path / scenario | Expected chain | Expected HTTP / behavior | Evidence to verify |
| --- | --- | --- | --- |
| GET /api/me without Basic | apiChain | **401**, Basic challenge | Does not run form-login |
| GET /api/me with valid Basic | apiChain | **200**, right principal | Credentials actually verified |
| GET /api/me with wrong Basic | apiChain | **401** | Does not fall over to webChain |
| GET /api/admin with normal user | apiChain | **403** | Authenticated, lacks role |
| GET /web/me unauthenticated | webChain | **302** to /login | Entry point is form login |
| GET /login | webChain | **200 HTML** | Filter-provided page sits inside chain |
| POST /login valid, valid CSRF | webChain | **302** to /web/me | Valid session created |
| POST /login invalid, valid CSRF | webChain | **302** to /login?error | No authenticated session granted |
| POST /login missing/invalid CSRF | webChain | **403** | Blocked before checking credentials |
| GET /web/me with valid session | webChain | **200**, right principal | SecurityContext restored |
| GET /web/me with Basic, no session | webChain | **302** to /login | Basic header does not enable Basic filter |
| POST /logout with session and CSRF | webChain | Configured redirect | Session/logout handled |
| GET /unknown | fallbackChain | **403** | Does not escape SecurityFilterChain |
| GET /unknown even with valid Basic | fallbackChain | **403** | Credentials do not open blocked area |
| API with web cookie, no Basic | apiChain | Per stateless policy, **401** | Does not accidentally use web session |
| Bad/expired API key/JWT if present | Matching chain/filter | **401** | Token fully verified, no weak fallback |
| Identity source unreachable | Matching provider | Fail safely | Never temporarily “accept” or grant default role |

**HTTP status is only part of the test.** Also assert **Location**, **WWW-Authenticate**, Content-Type, principal, authorities, cookies/sessions, CSRF, and which filter/chain actually ran. Cases where multiple mechanisms share status 401 make verifying the chain/filter even more critical to avoid “green tests taking the wrong path”.

### 3.1. Required Branch Checklist

1. **Happy path** for each mechanism: valid credentials, right subject, right permissions, and session/token state.
2. **Invalid evidence**: wrong password, missing credentials, nonexistent API key, bad JWT signature, expired token, mismatched issuer/audience.
3. **Account state**: disabled, locked, expired, revoked, password changed, or key revoked.
4. **Authorization**: logged in yet missing role/scope must get 403; client-supplied roles never become permissions.
5. **Session/CSRF**: login requires valid token when session cookies exist; session fixation; logout; properly scoped cookies; stateless APIs never rely on sessions.
6. **Routing**: overlapping matchers, chain ordering, `/login` and `/logout` endpoints, undefined routes, non-GET methods, error/dispatch, URL gaps.
7. **Provider fallback**: support ordering, returning null, credential errors, AccountStatusException, parent manager, no supporting provider, and data-source outages.
8. **Failure response**: proper 401/403/302, no leaked passwords/stack traces, no “200 with success=false” masking HTTP errors.
9. **Operations**: logging/auditing free of secrets, rate limiting, retries not amplifying attacks, timeout handling.

No single test covers every layer. Combine **isolated provider tests** with **MockMvc integrated against the real FilterChainProxy**, plus deployment-level tests running behind real proxies/TLS.

## 4. Runnable Example: HTTP Basic + Form Login + Fallback Deny

This section provides a **standalone hands-on project** with **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet/MVC)**. Create a Spring Initializr project with **Spring Web**, **Spring Security**, and **Spring Boot Starter Test**; add **spring-security-test** in test scope. The project uses package **com.example.authpaths**.

In **pom.xml**, required dependencies (managed by the Spring Boot parent/BOM):

~~~xml
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
~~~

### 4.1. Application Entry Point

File **src/main/java/com/example/authpaths/AuthPathsApplication.java**:

~~~java
package com.example.authpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthPathsApplication.class, args);
    }
}
~~~

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Never hard-code real passwords in code or committed configuration files. The **demo-pass** value in this lesson is strictly for local development on localhost.

### 4.2. Configuring Three Explicitly Ordered SecurityFilterChains

File **src/main/java/com/example/authpaths/SecurityConfig.java**:

~~~java
package com.example.authpaths;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/web/**", "/login", "/logout")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/web/public", "/login").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(form -> form
                        .defaultSuccessUrl("/web/me", true))
                .logout(logout -> logout
                        .logoutSuccessUrl("/web/public?logout"))
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                        HttpStatus.FORBIDDEN))
                        .accessDeniedHandler((req, res, ex) ->
                                res.sendError(
                                        HttpServletResponse.SC_FORBIDDEN)))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }
}
~~~

Points to understand before running:

- **apiChain** matches **/api/** first and uses HTTP Basic. The sample user has **ROLE_USER**, so calling **/api/admin** returns 403 even with the right password.
- **webChain** matches **/web/** plus **/login** and **/logout**. This is an important detail: the default form login filter handles **POST /login**, serves **GET /login**, and logs out at **/logout**. Leaving these paths out of the matcher could cause login/logout to be blocked by another chain.
- **fallbackChain** sets no securityMatcher and acts as the final chain matching all remaining requests. The sample config denies with **403** and disables Basic/form login. This is a clean testing choice for a demo app with a finite route list.
- The configuration shares **UserDetailsService** and **PasswordEncoder** so Spring Security can verify username/password for both Basic and form login. Having multiple chains does not implicitly prove they share the same AuthenticationManager instance; if sharing the instance is required, wire the manager explicitly.
- **SessionCreationPolicy.STATELESS** on the API ensures the API chain does not use HTTP sessions to retrieve SecurityContext. The web chain still uses sessions to persist logins.
- This lesson keeps default **CSRF** protection intact on web. If HTTP Basic is used from browsers, its interaction with CSRF also needs client-aware evaluation; never disable CSRF reflexively just because APIs are usually machine-called.
- In real environments, endpoints accepting credentials must use HTTPS; the localhost HTTP setup is strictly for learning. Keep password environment variables and credentials out of logs.

### 4.3. Creating Endpoints to Observe

File **src/main/java/com/example/authpaths/RoutesController.java**:

~~~java
package com.example.authpaths;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RoutesController {

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "admin";
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web " + authentication.getName();
    }

    @GetMapping("/web/public")
    public String publicPage() {
        return "public";
    }
}
~~~

The four endpoints cover every scenario: Basic required, higher role required, web session required, and public. We intentionally omit an **/unlisted** route to test the fallback.

Start on Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

In PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

Test the APIs with curl:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/web/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/unlisted
~~~

Expected statuses in order: **401, 200, 401, 403, 302, 200, 403**. A successful response from **/api/me** returns body **api alice**. The **/login** page is Spring Security's default HTML; **/web/me** without a session redirects to the login page.

With real form flows, the browser must hold the session cookie and send the CSRF token on POST. Never submit a form POST missing CSRF and conclude “the password was rejected”: in that case the request was likely blocked earlier by **CsrfFilter**.

## 5. Integration Testing with MockMvc

File **src/test/java/com/example/authpaths/AuthPathsIntegrationTest.java**:

~~~java
package com.example.authpaths;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.user.password=demo-pass")
@AutoConfigureMockMvc
class AuthPathsIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    private SecurityFilterChain firstMatchingChain(String path) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        return springSecurityFilterChain.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void chainMatchersAndFilterTypesAreCorrect() {
        List<SecurityFilterChain> chains =
                springSecurityFilterChain.getFilterChains();

        assertEquals(3, chains.size());
        assertSame(chains.get(0), firstMatchingChain("/api/me"));
        assertSame(chains.get(0), firstMatchingChain("/api/admin"));
        assertSame(chains.get(1), firstMatchingChain("/web/me"));
        assertSame(chains.get(1), firstMatchingChain("/login"));
        assertSame(chains.get(1), firstMatchingChain("/logout"));
        assertSame(chains.get(2), firstMatchingChain("/unlisted"));

        assertTrue(chains.get(0).getFilters().stream()
                .anyMatch(f -> f instanceof BasicAuthenticationFilter));
        assertFalse(chains.get(0).getFilters().stream()
                .anyMatch(f -> f instanceof UsernamePasswordAuthenticationFilter));

        assertTrue(chains.get(1).getFilters().stream()
                .anyMatch(f -> f instanceof UsernamePasswordAuthenticationFilter));
        assertFalse(chains.get(1).getFilters().stream()
                .anyMatch(f -> f instanceof BasicAuthenticationFilter));
    }

    @Test
    void basicPathMustValidateRealCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("api alice"));

        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void formAndBasicCannotSwapPaths() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/web/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/login"))
                .andExpect(status().isOk());

        mvc.perform(get("/web/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void validFormLoginPersistsIdentityInSession() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/web/me"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web alice"));

        // Web session is not a Basic credential for the stateless API.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void failedFormLoginStaysFailed() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void missingAndInvalidCsrfAreRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/login")
                        .with(csrf().useInvalidToken())
                        .param("username", "alice")
                        .param("password", "demo-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithValidCsrfHasConfiguredRedirect() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/web/public?logout"));
    }

    @Test
    void catchAllRejectsUnknownPathEvenWithBasic() throws Exception {
        mvc.perform(get("/unlisted"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

In PowerShell use **.\mvnw.cmd test**. All tests are expected to **PASS**; log volume and runtime depend on the environment, so no fabricated stdout is shown.

### 5.1. Why Each Assertion Group Is Needed

- **chainMatchersAndFilterTypesAreCorrect**: directly tests **FilterChainProxy.getFilterChains()**. Rather than inferring the chain from status codes alone, it also verifies the Basic and form filters sit in the right chains.
- **basicPathMustValidateRealCredentials**: sends real credentials via the **httpBasic(...)** processor through the filter and provider. With **@WithMockUser** or **with(user(...))**, a test can pass even if passwords are broken because those inject a mock security context directly.
- **authenticatedUserWithoutAdminRoleGets403**: confirms the distinction between authentication and authorization.
- **formAndBasicCannotSwapPaths**: ensures the form chain is selected, HTTP Basic does not automatically activate on web URLs, and `/login` belongs to the right chain.
- **validFormLoginPersistsIdentityInSession**: tests both the login POST and a **subsequent** request reusing the same session. This catches cases where login returns 302 success yet fails to persist SecurityContext.
- **failedFormLoginStaysFailed**: wrong credentials must stay on the failure branch and redirect to `/login?error`.
- **missingAndInvalidCsrfAreRejected**: ensures CSRF errors are not confused with wrong passwords. `spring-security-test`'s **formLogin()** processor automatically supplies a valid CSRF token; manual POSTs deliberately test missing/invalid tokens.
- **logoutWithValidCsrfHasConfiguredRedirect**: verifies the logout endpoint is handled properly by webChain. In real projects, also assert session/cookie invalidation and that a logged-out session cannot be reused.
- **catchAllRejectsUnknownPathEvenWithBasic**: confirms no path “slips past” the final chain; sending a credential header does not cause the fallback chain to switch to apiChain.

**Limitations:** these tests simulate HTTP with MockMvc and do not validate TLS, reverse proxies, gateway-rewritten headers, or production Secure/SameSite cookies. Those require deployment-level integration tests. The test also assumes **exactly three chains** matching the source; if your app adds actuator or another chain, update assertions to match the designed security layout.

## 6. Testing ProviderManager Fallback Independently

Section 5 verified **request paths and chains**. We need separate tests for how **ProviderManager** iterates through multiple providers, because provider fallback **is not** chain fallback. The example below starts no web server, using only Spring Security Core and JUnit 5 inside **the same project** from section 4.

File **src/test/java/com/example/authpaths/ProviderManagerFallbackTest.java**:

~~~java
package com.example.authpaths;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class ProviderManagerFallbackTest {

    private Authentication request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");
    }

    private Authentication verified(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private AuthenticationProvider stub(
            String name,
            List<String> calls,
            Function<Authentication, Authentication> action) {
        return new AuthenticationProvider() {

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add(name);
                return action.apply(auth);
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };
    }

    @Test
    void firstSuccessStopsFurtherProviders() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("first", calls, auth -> verified("alice")),
                stub("second", calls, auth -> verified("other"))));

        Authentication result = manager.authenticate(request());

        assertEquals("alice", result.getName());
        assertEquals(List.of("first"), calls);
    }

    @Test
    void badCredentialsMayBeOverriddenByLaterSuccess() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("first", calls, auth -> {
                    throw new BadCredentialsException("wrong");
                }),
                stub("second", calls, auth -> verified("alice"))));

        Authentication result = manager.authenticate(request());

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertEquals(List.of("first", "second"), calls);
    }

    @Test
    void accountLockedStopsProviderChain() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("locked", calls, auth -> {
                    throw new LockedException("Account locked");
                }),
                stub("second", calls, auth -> verified("alice"))));

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        assertEquals(List.of("locked"), calls);
    }

    @Test
    void unsupportedTokenFailsWithoutAlternateProvider() {
        List<String> calls = new ArrayList<>();
        var manager = new ProviderManager(List.of(
                stub("password", calls, auth -> verified("alice"))));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(
                        new TestingAuthenticationToken(
                                "alice", "demo-pass")));
        assertTrue(calls.isEmpty());
    }

    @Test
    void parentManagerMayHandleRequestAfterNull() {
        List<String> calls = new ArrayList<>();
        var parent = (org.springframework.security.authentication.AuthenticationManager)
                auth -> {
                    calls.add("parent");
                    return verified("alice");
                };

        var manager = new ProviderManager(
                List.of(stub("child", calls, auth -> null)),
                parent);

        Authentication result = manager.authenticate(request());

        assertEquals("alice", result.getName());
        assertEquals(List.of("child", "parent"), calls);
    }
}
~~~

Run the provider tests alone:

~~~bash
./mvnw -Dtest=ProviderManagerFallbackTest test
~~~

In PowerShell:

~~~powershell
.\mvnw.cmd '-Dtest=ProviderManagerFallbackTest' test
~~~

These are **behavior tests**, not a recommendation to let bad credentials fail in the first provider and unconditionally succeed in a later one. The second test deliberately demonstrates **fallback risk**: when multiple providers support the same token, a `BadCredentialsException` from an earlier provider **can be overridden** if a later provider succeeds. If policy forbids that, design separate token types, partition identity sources strictly, audit providers sharing `supports`, and test the corresponding blocking branches.

The account-lock test proves **LockedException** (part of **AccountStatusException**) halts further attempts. The parent test proves a **parent AuthenticationManager** is a potential fallback tier; verify whether one is configured in each system.

**Never use a ProviderManager test to conclude requests take the right HTTP filter.** It calls the manager directly, bypassing FilterChainProxy, CSRF, entry points, and SecurityContextRepository. The two test suites complement each other.

## 7. When Using API Keys, Bearer/JWT, OAuth2/OIDC, or JSON Login

The sample model implements only Basic and form login. In real projects with more mechanisms, add corresponding rows to the matrix:

| Mechanism | Happy path | Minimum negative paths | What to observe |
| --- | --- | --- | --- |
| **API key** | Valid key, subject/permissions from key store | Missing, wrong, expired, revoked key, wrong scope | Does custom filter actually create ApiKeyAuthenticationToken and invoke the right provider? |
| **JWT access token** | Valid signature, issuer, audience, timestamps, scope | Forged signature, unknown alg, wrong issuer/audience, expired, future nbf, missing permission | Is token verified or merely payload-decoded? |
| **OIDC login** | Redirects to right IdP, valid state/nonce and callback | Bad state, mismatched nonce, expired/reused code, wrong callback | Are OAuth2LoginAuthenticationFilter, session, and redirect URI correct? |
| **SAML login** | Validly signed assertion bound to right SP | Bad signature, wrong audience/recipient, replay, expired | IdP trust config and replay protection |
| **JSON username/password** | Valid body, AuthenticationManager verifies, session/token persisted properly | Malformed JSON, missing fields, wrong password, bad CSRF, source error | Which controller/filter returns 400/401/403? Are JSON responses consistent? |
| **mTLS** | Valid client cert chain, right identity mapping | Forged cert, revoked cert, missing mapping | Does proof come from verified TLS rather than self-asserted headers? |
| **General fallback** | New routes must be covered explicitly by policy | Unknown path, new method, strange header, overlapping matchers | Does catch-all block it, or does the route sit outside filter chains? |

Distinguish “a mechanism **is configured**” from “a mechanism **actually has a filter ingesting credentials**”. Registering an API key provider in a manager does not add a filter reading **X-API-Key**. Registering a JWT decoder does not put **BearerTokenAuthenticationFilter** into every chain. Inspect each chain's filter list and test real requests carrying valid tokens rather than only unit-testing providers.

**For JWT and OIDC**, prefer testing through standard Spring Security components, including the **JwtDecoder**/trust config used in production. Mocks can verify authorization quickly, yet you still need tests with bad signatures, wrong issuers/audiences, and untrusted keys to prove real verification runs. Never treat a Base64-decoded payload as proof of a valid signature.

## 8. Testing Error Paths and Safety Rules

### 8.1. You Must Distinguish 401, 403, and Redirects

- **401 Unauthorized**: HTTP authentication requirement unmet or invalid credentials (typically via AuthenticationEntryPoint). HTTP Basic may include **WWW-Authenticate**.
- **403 Forbidden**: authenticated but lacking privileges, or blocked by CSRF/another denial policy. The fallback chain in the example is configured to return 403 for any request outside permitted zones.
- **302 Found / 303 See Other**: typically part of form login and browsers. Redirecting after a successful POST is normal, whereas on bearer/Basic APIs an unexpected HTML redirect usually indicates the wrong chain was picked.

Do not assume every authentication failure returns 401. In form login, a wrong password typically redirects to **/login?error**. Tests must therefore follow **each mechanism's contract** rather than expecting one uniform status across all flows.

### 8.2. Testing Chain Ordering with Deliberately Misconfigured Chains

**Bug-illustration only**—do not put this into section 4's runnable config:

~~~java
@Bean
@Order(1)
SecurityFilterChain broad(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

The first chain sets no securityMatcher, so it matches **every URL**, including **/api/**. API requests pass through the broad chain with **permitAll**, never protected by the second api chain. Tests must catch this by asserting the **first chain** matching API requests is the api chain and unauthenticated requests are rejected.

You can use a matcher test like **firstMatchingChain("/api/me")** from section 5 to catch this right at startup before frontend integration.

### 8.3. Checking Uncovered Routes

If a configuration only defines **securityMatcher("/api/**")** and **securityMatcher("/web/**")** without a fallback chain, a request to **/health-private** may **bypass Spring Security**. That is not an “implicit 403”; Spring Security's authentication/authorization filters simply will not run for that request.

Tests must verify that **every route needing protection** matches at least one chain and unwanted routes are blocked by the fallback. Specifically cover **/login**, **/logout**, **/error**, actuator, internal paths, websocket handshakes, newly deployed endpoints, and matching precedence for similar URLs.

Do not test only the response of a nonexistent route. A 404 from MVC does not prove Spring Security actually protected that path. Inspect **SecurityFilterChain.matches(...)** or FilterChainProxy traces when needed.

### 8.4. Testing Identity-Source Failures and Account States

Providers may query a database, LDAP, Key Vault, or IdP. Key test cases:

- Source timeout/5xx → **fail closed**, never treat as valid credentials; never fall back to a weaker provider.
- Wrong password → **BadCredentialsException** or appropriate failure branch, never return an authenticated Authentication.
- Locked/disabled account → reject immediately, preventing another provider from sneaking in against policy.
- Updated or revoked privileges → Authorization uses trusted, sufficiently fresh authorities, never client-supplied roles.
- Revoked API key or expired JWT → subsequent requests must be rejected per that credential type's rules.
- Two directories sharing the same username → resolve by namespace, tenant, issuer, or token type; never mix principals/authorities across sources.

Mock the identity source to induce timeouts/invalid statuses; however, run another integration test verifying the adapter over real protocols whenever the system depends on remote connections.

### 8.5. Never Let Mock-User Tests Hide Real Gaps

~~~java
// Useful only when testing authorization for a mock principal:
mvc.perform(get("/api/admin").with(
        org.springframework.security.test.web.servlet.request
            .SecurityMockMvcRequestPostProcessors
            .user("admin").roles("ADMIN")));
~~~

The snippet above does not prove passwords, tokens, keys, or signatures were verified. **with(user(...))** creates a mock user for authorization testing. **@WithMockUser** works similarly: very useful for method security and permission checks, but no substitute for requests proving real credential verification.

To test login, send **httpBasic("alice", "password")**, **formLogin()**, real test bearer tokens with a valid decoder/config, or API keys through your custom filter; then verify principal, status, authorities, and session/token state.

## 9. Running Tests in CI and Diagnosing Failures

### 9.1. Organizing Tests

A maintainable test structure:

~~~text
src/test/java/com/example/authpaths/
  AuthPathsIntegrationTest.java
  ProviderManagerFallbackTest.java
~~~

In larger projects, split further:

- **AuthProviderTest**: credential verification policy, account states, and provider fallback.
- **FilterChainRoutingTest**: chain ordering, RequestMatcher, filter types.
- **LoginFlowIntegrationTest**: Basic, form, JSON, token, logout, CSRF, session.
- **AuthorizationMatrixTest**: roles/permissions/scopes and routes.
- **IdentityServiceFailureTest**: timeouts, revocation, source unavailability.
- **GatewayE2ETest**: HTTPS, forwarding headers, cookie flags, and gateway errors.

When integration tests use a database or mock IdP, each test must set up its own data and clean up state so tests do not depend on execution order. Avoid sharing a session cookie across independent tests. When testing a continuous flow (login → resource → logout), intentionally reuse **the same session** inside **one test** and assert each step.

### 9.2. Test Commands

~~~bash
./mvnw test
./mvnw -Dtest=AuthPathsIntegrationTest test
./mvnw -Dtest=ProviderManagerFallbackTest test
~~~

In Windows PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=AuthPathsIntegrationTest' test
.\mvnw.cmd '-Dtest=ProviderManagerFallbackTest' test
~~~

Note: these are **commands for running the sample project once source files and dependencies are created**, not stdout verified in this environment. In CI, a failed command must fail the pipeline; never report green if a test was skipped or context failed to load properly.

### 9.3. Tracing When Tests Fail

In development or temporary test runs, enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

When deeper detail is needed, use TRACE in a controlled scope. Watch which chain matches the request and which filters participate, then place breakpoints in **FilterChainProxy**, **BasicAuthenticationFilter / UsernamePasswordAuthenticationFilter**, **ProviderManager**, custom providers, and 401/403 handlers. Never log plaintext passwords, API keys, Bearer tokens, session IDs, or Authorization headers. Avoid uploading logs containing secrets to public issue trackers.

### 9.4. Acceptance Checklist

- [ ] Every supported mechanism has tests for **valid, invalid, missing, and revoked/expired** credentials where applicable.
- [ ] APIs without credentials get **401** from the proper entry point; no unexpected HTML form redirects.
- [ ] Unauthenticated web requests redirect to the form; failed login creates no principal; valid login persists context.
- [ ] Login/logout POSTs verify **CSRF** when using session cookies.
- [ ] Users lacking role/scope receive **403** despite valid credentials; privileges are never read from client-supplied bodies/headers.
- [ ] **FilterChainProxy** picks the right first chain; no broader chain shadows a specialized chain.
- [ ] URLs outside earlier chains are denied by the catch-all per policy; no sensitive route sits outside Spring Security.
- [ ] **ProviderManager** tries providers per token and exception rules; BadCredentialsException is not accidentally overridden by a weaker provider.
- [ ] AccountStatusException blocks unauthorized fallback paths.
- [ ] Parent AuthenticationManager introduces no unintended bypass path.
- [ ] Source errors/timeouts **fail closed** with appropriate monitoring.
- [ ] Real login paths are tested through filters, not solely via **@WithMockUser**.
- [ ] Logs, messages, and HTTP responses leak no credentials, stack traces, or internal config.
- [ ] Minimum test suite runs in CI after matcher changes, new providers, route changes, or Spring Security upgrades.

## 10. Common Misconceptions

**“If there are two SecurityFilterChains, the second acts as a backup if login in the first fails.”** False. Chains are selected on the first request match; Spring never moves to another chain on authentication failure.

**“If there are two AuthenticationProviders, they surely check two different login flows.”** False. Two providers can both support the same Authentication type; the HTTP filter creating the token determines which providers may be tried.

**“Adding an API key provider is enough for X-API-Key to work automatically.”** False. You need a filter converting request credentials into a token, invoking the manager, and storing the result in SecurityContext properly.

**“MockMvc returned 200, so security is correct.”** Not necessarily. **with(user(...))** can bypass real credential checking, or a misconfigured **permitAll** chain still returns 200. Test real mechanisms and chain matching.

**“Testing 404 on an unknown URL proves a fallback exists.”** False. An MVC 404 can occur even when a request bypasses Spring Security entirely. Verify the chain and denial policy.

**“Seeing Basic 401 means all requests entered the API chain.”** No. Inspect matchers, actual filters, and status/headers for each path.

**“If the first provider throws BadCredentialsException, later providers never run.”** False for a typical ProviderManager; a later provider may succeed. Test fallback behavior and enforce clear policies.

**“Stateless APIs make all CSRF tests pointless.”** False whenever cookies or browser auto-sent credentials are involved. Evaluate CSRF by **credential transport**, invocation method, and trust model—never guess from a chain's name.

## 11. Official Documentation for Cross-Checking

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, parent manager, and providers.
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): provider ordering, BadCredentialsException, AccountStatusException, and credential erasure.
- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): multiple SecurityFilterChains, @Order, and securityMatcher/requestMatchers.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy running only the first matching chain.
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): httpBasic request processor.
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): formLogin processor with CSRF.
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): csrf(), invalid tokens, and POST testing.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): handling logout, sessions, and CSRF.
